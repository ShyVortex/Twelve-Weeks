"""Live menu ticker (clan_story.live_for_widget / daemon.feed_op): an old clan with no roster and no clan_feed table still gets lines.
Run: python tools/tests/test_clan_feed_live.py   (temp DB only)."""
import os, sqlite3, sys, tempfile
os.environ["T2R_CLAN_ALIFE"] = "0"   # pre-A-Life feed behaviour (A-Life is default ON; its own rules: test_clan_alife.py)
import sys as _t2s, os as _t2o; _t2s.path.append(_t2o.path.normpath(_t2o.path.join(_t2o.path.dirname(_t2o.path.abspath(__file__)), ".."))); import t2rtmp  # noqa: E402,F401  (temp hygiene: tools/t2rtmp.py)

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.dirname(HERE)
TMP = tempfile.mkdtemp()
os.environ["T2R_DB"] = os.path.join(TMP, "t.db")
sys.path.insert(0, TOOLS)
import clan, clan_story as CS, clan_story_data as D  # noqa: E402
import daemon  # noqa: E402

FAILS = []
def check(cond, what):
    print(("ok   " if cond else "FAIL ") + what)
    if not cond:
        FAILS.append(what)

c = sqlite3.connect(os.path.join(TMP, "old.db"))
# an old clan: numbers only, no clan_story / clan_feed tables
check(CS.live_for_widget(c, "nobody", set(), 6) == [], "no clan -> []")
clan.save(c, "old1", {"faction": clan.WLF, "status": 1, "day": 5, "healthy": 3, "hungry": 1, "sick": 1})
check(not c.execute("SELECT name FROM sqlite_master WHERE name='clan_story'").fetchall(), "precondition: no clan_story table")
out = CS.live_for_widget(c, "old1", set(), 6)
check(len(out) == 6 and all(i and t and "{" not in t and "|" not in t for i, t in out), "old clan without roster: 6 lines (%s)" % [t for _, t in out][:2])
st = CS._load(c, "old1")
check(st and len(st["people"]) == 5 and sum(p["s"] == "s" for p in st["people"]) == 1 and st["n"] == 0, "roster created from the numbers (3h/1u/1s), no story message")
check(c.execute("SELECT COUNT(*) FROM clan_feed WHERE token_id='old1'").fetchone()[0] == 0, "live lines are not stored")
names = {p["n"] for p in st["people"]}
check(all(any(n in t for n in names) for _, t in out), "every line is about a roster member")
ids = [p["id"] for p in st["people"]]
CS.live_for_widget(c, "old1", set(), 6)
check(CS._load(c, "old1")["people"] == st["people"], "second call does not touch the roster")
# no repeats across consecutive batches while the pool is large
T0 = 1_800_000_000
seen_txt = []
for k_ in range(4):                                     # the lines are a function of the time slot: successive slots = successive batches
    seen_txt += [t for _, t in CS.live_for_widget(c, "old1", set(), 6, now=T0 + k_ * CS.SLOT_S)]
check(len(seen_txt) == len(set(seen_txt)) or len(set(seen_txt)) >= 0.85 * len(seen_txt), "few repeats over 24 lines (%d unique)" % len(set(seen_txt)))
for k_ in range(30):
    a = [t for _, t in CS.live_for_widget(c, "old1", set(), 6, now=T0 + (10 + 2 * k_) * CS.SLOT_S)]
    b = [t for _, t in CS.live_for_widget(c, "old1", set(), 6, now=T0 + (11 + 2 * k_) * CS.SLOT_S)]
    if a[-1] == b[0]:
        check(False, "consecutive batches never join with the same line")
        break
else:
    check(True, "consecutive batches never join with the same line")
# polish
pl = CS.live_for_widget(c, "old1", set(), 6, lang="pl")
en = CS.live_for_widget(c, "old1", set(), 6, lang="en")
check(len(pl) == 6 and all("{" not in t for _, t in pl) and any(any(ord(ch) > 127 for ch in t) or " jest " in t for _, t in pl), "Polish lines (%s)" % pl[0][1])
check(all(t not in {x for _, x in en} for _, t in pl), "Polish differs from English")
# Seraphite island: no generator lines
clan.save(c, "ser", {"faction": clan.SERAPHITES, "status": 1, "day": 2, "healthy": 4, "hungry": 1, "sick": 0})
for k_ in range(25):
    for _, t in CS.live_for_widget(c, "ser", set(), 6, now=T0 + k_ * CS.SLOT_S):
        if any(k in t for k in D.TICKER_NOT_SERA):
            check(False, "NOT_SERA line on the island: " + t)
            break
check(True, "Seraphite lines pass the NOT_SERA filter")
# empty clan / unfounded
clan.save(c, "empty", {"faction": clan.WLF, "status": 1, "day": 0, "healthy": 0, "hungry": 0, "sick": 0})
check(CS.live_for_widget(c, "empty", set(), 6) == [], "clan with nobody alive -> []")
# stored events first, then live, total n
c2 = sqlite3.connect(os.path.join(TMP, "new.db"))
clan.save(c2, "t1", {"faction": clan.WLF, "status": 1, "day": 0, "healthy": 5, "hungry": 0, "sick": 0})
CS.on_new_run(c2, "t1", clan.WLF)
seen = set()
out = CS.live_for_widget(c2, "t1", seen, 6)
stored = CS.read_feed(c2, "t1")
check(len(out) == 6 and out[0][1] == CS.widget_text(stored[0]["text"]) and not str(out[0][0]).startswith("l"), "stored founding line comes first")
check(all(str(i).startswith("l") for i, _ in out[1:]), "live lines follow with their own ids")
check(c2.execute("SELECT COUNT(*) FROM clan_feed").fetchone()[0] == len(stored), "still nothing live stored")

# daemon op 0xB4: up to 6 lines for an old clan
TOK = "54324e3a" + "416c696365" + "00" * 11 + "0123456789abcdef01234567"
with daemon.db() as d:
    tid = daemon.clan_key(d, TOK)
    clan.save(d, tid, {"faction": clan.WLF, "status": 1, "day": 4, "healthy": 4, "hungry": 2, "sick": 0})
rep = daemon.feed_op(TOK.encode())
assert rep[2] == 0xB5 and int.from_bytes(rep[:2], "little") == len(rep) - 2
head, *lines = rep[3:].decode("utf-8").split("\n")
check(head == "n=6" and len(lines) == 6 and all("|" in ln and len(ln.split("|", 1)[1].encode()) <= 150 for ln in lines), "feed_op: n=6 for an old clan")
check(len(rep) < 1024, "reply under the client's 1024 byte buffer (%d)" % len(rep))
rep = daemon.feed_op(TOK.encode() + b"\x01")
check(rep[3:].decode("utf-8").startswith("n=6"), "feed_op Polish: n=6")
print("\nFAILED: %d" % len(FAILS) if FAILS else "\nall passed")
sys.exit(1 if FAILS else 0)
