"""The post-match scoreboard's day key: the client asks op 0xB6 section 5 for the day it just played, formula of clan13.c cl13_post_open
(xs_day = days-done-before-the-match + 1; t2r-ext g_pm.day = clan_t.day before the match). The daemon books a match under the clan's day AFTER it
(clan_chronicle log "d" = newc["day"]). Books a match through the real finalize path and queries it. Run: python tools/tests/test_clan_post_day.py"""
import os, sys, tempfile
import sys as _t2s, os as _t2o; _t2s.path.append(_t2o.path.normpath(_t2o.path.join(_t2o.path.dirname(_t2o.path.abspath(__file__)), ".."))); import t2rtmp  # noqa: E402,F401
TOOLS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.environ["T2R_DB"] = os.path.join(tempfile.mkdtemp(), "t.db")
for k in ("T2R_CLAN_CHRONICLE", "T2R_CLAN_SAGA", "T2R_CLAN_STATUS"):
    os.environ[k] = "1"
sys.path.insert(0, TOOLS)
import daemon  # noqa: E402
import clan_ingame as ci  # noqa: E402

FAILS = []
def check(c, w):
    print(("ok   " if c else "FAIL ") + w)
    if not c:
        FAILS.append(w)

TOK = "54324e3a" + "416c696365" + "00" * 11 + "0123456789abcdef01234567"
daemon.clan_side(TOK, 1)
for played in range(3):                                          # three matches in a row: the clan's day before them = 0, 1, 2
    before = daemon.clan_state(TOK)["day"]                       # = t2r-ext clan_t.day when the match starts = g_pm.day
    mid = "mid%d" % played
    daemon.CLAN_MATCH[TOK] = mid
    daemon.CLAN_MAP[mid] = "Hill"
    daemon.CLAN_PENDING[TOK] = (mid, 400, 2, {1: 3})              # flags bit 1 = the game ended the match normally
    daemon.CLAN_ENDED[mid] = __import__("time").time()
    with daemon._dblock, daemon.dbc() as c:
        ci.stats_roster(c, mid, "Hill", [(TOK, "Alice", 0, False)], 0)
        ci.stats_report(c, mid, TOK, "Alice", 0, {1: 3, 2: 1}, False)
        ci.stats_parts(c, mid, TOK, 400)
    daemon.clan_finalize(TOK)
    after = daemon.clan_state(TOK)["day"]
    xs_day = before + 1                                          # clan13.c cl13_post_open(g_pm.day + 1 ...): what the client sends
    rep = daemon.clan13_op(TOK.encode() + bytes([0, 5, 0, 0, 0, 0]) + xs_day.to_bytes(2, "little") + b"")
    rows = [l.split(chr(9)) for l in rep[3:].decode().split(chr(10)) if l[:2] in ("X" + chr(9), "Q" + chr(9))]
    check(after == before + 1, "match %d: clan day %d -> %d" % (played, before, after))
    check(rows and rows[0][0] == "X" and rows[0][1] == str(xs_day) and rows[0][2] == "Hill" and rows[0][4] == "1",
          "match %d: scoreboard asked with day %d (before + 1) finds its stats (%s)" % (played, xs_day, rows[:1]))
    if played == 0:                                              # the 0-based day (the old client formula) finds nothing: that was the bug
        rows0 = daemon.clan13_op(TOK.encode() + bytes([0, 5, 0, 0, 0, 0]) + before.to_bytes(2, "little") + b"")[3:].decode().split(chr(10))
        rows0 = next(l for l in rows0 if l.startswith("X" + chr(9))).split(chr(9))
        check(rows0[-1] == "0", "match 0: asking day %d (days done before, 0-based) finds nothing (%s)" % (before, rows0))
print("FAILED %d" % len(FAILS) if FAILS else "all ok")
sys.exit(1 if FAILS else 0)
