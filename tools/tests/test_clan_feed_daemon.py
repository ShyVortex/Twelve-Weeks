"""Daemon side of the clan feed: finalize hook -> clan_story -> feed_op (op 0xB4 reply). Temp DB only; never port 7001 / tools/t2r.db.
Run: python tools/tests/test_clan_feed_daemon.py"""
import os, sys, tempfile
os.environ["T2R_CLAN_ALIFE"] = "0"   # pre-A-Life feed behaviour (A-Life is default ON; its own rules: test_clan_alife.py)
import sys as _t2s, os as _t2o; _t2s.path.append(_t2o.path.normpath(_t2o.path.join(_t2o.path.dirname(_t2o.path.abspath(__file__)), ".."))); import t2rtmp  # noqa: E402,F401  (temp hygiene: tools/t2rtmp.py)

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.dirname(HERE)
TMP = tempfile.mkdtemp()
os.environ["T2R_DB"] = os.path.join(TMP, "t.db")
sys.path.insert(0, TOOLS)
import daemon  # noqa: E402

FAILS = []
def check(cond, what):
    print(("ok   " if cond else "FAIL ") + what)
    if not cond:
        FAILS.append(what)

TOK = "54324e3a" + "416c696365" + "00" * 11 + "0123456789abcdef01234567"
check(daemon.feed_latest(TOK) == [], "no clan yet: empty feed")
daemon.clan_side(TOK, 1)
lines = daemon.feed_latest(TOK)
check(len(lines) == 6 and "{" not in lines[0][1] and not str(lines[0][0]).startswith("l") and str(lines[1][0]).startswith("l"), "new clan: founding line first, then live ticker up to 6 (%s)" % (lines[0][1] if lines else None))
daemon.clan_match_started([TOK], "mid1")
daemon.clan_report(TOK, 900, 2)               # flags bit 1: the client's match ended -> resolved at once
rep = daemon.feed_op(TOK.encode())
check(rep is not None and rep[0:1] != b"", "feed_op answers")
body = rep[-600:]
seen_ids = set()
for _ in range(4):
    for i, t in daemon.feed_latest(TOK):
        check(len(t.encode()) <= 150 and "|" not in t and "\n" not in t and len(t) <= 118, "line %s fits the widget" % i)
        seen_ids.add(i)
check(len(seen_ids) >= 2, "the widget cycles through several lines (%d)" % len(seen_ids))
# language byte of op 0xB4: none / 0 = English (old clients), 1 = Polish, anything else = English
def feed_reply(extra=b"", tok=TOK):
    rep = daemon.feed_op(tok.encode() + extra)
    assert rep[2] == 0xB5 and int.from_bytes(rep[:2], "little") == len(rep) - 2
    text = rep[3:].decode("utf-8")                       # (valid UTF-8 or this raises)
    head, *lines = text.split("\n")
    assert head == "n=%d" % len(lines), text
    return [tuple(ln.split("|", 1)) for ln in lines]
daemon.FEED_SEEN.clear()
en = feed_reply()
check(en and all(i and t for i, t in en) and not any(ord(ch) > 127 for _, t in en for ch in t.replace("…", "")), "no language byte: English lines")
check(feed_reply(b"\x00") and feed_reply(b"\x07"), "language 0 and an unknown language: still answered (English)")
daemon.FEED_SEEN.clear()
pl = feed_reply(b"\x01")
daemon.FEED_SEEN.clear()
en2 = feed_reply()
check(pl and [i for i, _ in pl] == [i for i, _ in en2] and all(a != b for (_, a), (_, b) in zip(pl, en2)), "language 1: the same messages (same ids), rendered in Polish")
check(all(len(t.encode("utf-8")) <= 150 and "|" not in t and "{" not in t for _, t in pl), "Polish lines fit the wire (<= 150 bytes, no pipe, no placeholder)")
allpl = ""
for _ in range(6):
    daemon.FEED_SEEN.clear()
    allpl += "".join(t for _, t in feed_reply(b"\x01"))
check(any(ord(ch) > 127 for ch in allpl), "the Polish reply carries diacritics through the protocol (%s)" % allpl[:40].encode("unicode_escape").decode())
# every Polish diacritic survives the wire cut and a UTF-8 round trip
alll = "Zażółć gęślą jaźń. ZAŻÓŁĆ GĘŚ LĄ JAŹŃ."
w = daemon.clan_story.widget_text(alll)
check(w == alll and daemon.msg(0xB5, w.encode("utf-8"))[3:].decode("utf-8") == alll, "all 18 Polish diacritics round trip through widget_text and the frame")
# mixed-language: a second player (other faction) asked in Polish while the first one was asked in English
TOK2 = "54324e3a" + "426f6200" + "00" * 12 + "0123456789abcdef01234568"
daemon.clan_side(TOK2, 2)
check(feed_reply(b"\x01", TOK2), "a second clan is answered in Polish independently of the first")
# a broken story module never breaks the clan day
orig = daemon.clan_story.on_day
daemon.clan_story.on_day = lambda *a, **k: 1 / 0
daemon.clan_match_started([TOK], "mid2")
daemon.clan_report(TOK, 900, 2)
check(daemon.clan_state(TOK)["day"] == 2, "clan day still resolves when the feed fails")
daemon.clan_story.on_day = orig
# extended report labels 21..24 (times downed, deaths, best streak, weapon class) travel in the op 0xE2 count tail; the daemon keeps them in the pending counts
import struct
TOK3 = "54324e3a" + "43617200" + "00" * 12 + "0123456789abcdef01234569"
daemon.clan_side(TOK3, 1)
daemon.clan_match_started([TOK3], "mid3")
tail = [(1, 7), (4, 2), (21, 3), (22, 2), (23, 5), (24, 6)]
pl = TOK3.encode() + struct.pack("<IIB", 77, 500, 0) + bytes([len(tail)]) + b"".join(struct.pack("<BH", a, b) for a, b in tail)
check(daemon.clan_op(0xE2, pl) is not None, "op 0xE2 with the extended labels is answered")
pend = daemon.CLAN_PENDING.get(TOK3)
check(pend is not None and pend[3] == dict(tail), "labels 1,4 and 21..24 are kept as sent in the pending counts (%s)" % (pend[3] if pend else None))
pl2 = TOK3.encode() + struct.pack("<IIB", 78, 500, 0) + bytes([1]) + struct.pack("<BH", 1, 1)
check(daemon.clan_op(0xE2, pl2) is not None, "old-style tail without the extended labels still parses")
print("\nFAILED: %d" % len(FAILS) if FAILS else "\nall passed")
sys.exit(1 if FAILS else 0)
