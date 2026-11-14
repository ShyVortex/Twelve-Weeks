"""Rejoin rebook ("No word from the camp"): a player left a running match (day booked), joined the SAME match again (join in progress) and played on; its
second report was dropped as "already booked" and the post-match page waited for a day that never came. Design: leave + rejoin must NOT farm
days - the second stint's report REPLACES the first booking: one day per match, the final result (stints summed), persisted over a daemon restart.
Temp DB only. Run: python tools/tests/test_clan_rejoin_rebook.py"""
import os, sys, tempfile
import sys as _t2s, os as _t2o; _t2s.path.append(_t2o.path.normpath(_t2o.path.join(_t2o.path.dirname(_t2o.path.abspath(__file__)), ".."))); import t2rtmp  # noqa: E402,F401
TOOLS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.environ["T2R_DB"] = os.path.join(tempfile.mkdtemp(), "t.db")
sys.path.insert(0, TOOLS)
import daemon  # noqa: E402
FAILS = []
def check(cond, what):
    print(("ok   " if cond else "FAIL ") + what)
    if not cond: FAILS.append(what)
def tok(n): return "54324e3a" + "416c696365" + "00" * 11 + ("%024x" % n)
def new(n):
    t = tok(n)
    daemon.clan_side(t, 1)
    with daemon._dblock, daemon.dbc() as c:
        c.execute("INSERT OR IGNORE INTO players (token) VALUES (?)", (t,))
    return t
def clanrow(t):
    with daemon._dblock, daemon.dbc() as c:
        r = daemon.clan.load(c, daemon.clan_key(c, t))
    return r
def players(t):
    with daemon._dblock, daemon.dbc() as c:
        r = c.execute("SELECT parts_total, parts_n FROM players WHERE token=?", (t,)).fetchone()
    return tuple(r)
def core(t):
    r = clanrow(t); return (r["day"], r["healthy"] + r["hungry"] + r["sick"], r["last_mid"], r["boost_hi"], r["meta"])

# control: the whole match in ONE report
ctl = new(1)
daemon.clan_match_started([ctl], "9ae893e8"); daemon.clan_report(ctl, 425, 2)

# A: leave (45 parts) + rejoin + final report (380 parts)
a = new(2)
daemon.clan_match_started([a], "9ae893e8")
daemon.clan_report(a, 45, 2)
d1 = clanrow(a)["day"]
daemon.clan_report(a, 380, 2)
check(clanrow(a)["day"] == d1, "without the rejoin hook the second report is ignored (the bug: day stays %d)" % d1)
daemon.clan_rejoin_after_booking(a, "9ae893e8")
daemon.clan_report(a, 380, 2)
check(clanrow(a)["day"] == d1, "leave + rejoin: still exactly one day (%d)" % clanrow(a)["day"])
check(core(a) == core(ctl), "the clan equals one report of both stints (425 parts): day, clan size, stock and mission identical")
check(players(a) == players(ctl) == (425, 1), "players parts_total / parts_n %s: booked once, both stints" % (players(a),))
check(clanrow(a)["last_mid"] == "9ae893e8" and clanrow(a)["last_result"] != "", "last_result written for the match (the client sees a changed lday/lmh)")
daemon.clan_report(a, 380, 2)
check(core(a) == core(ctl), "a re-send of the final report changes nothing")

# B: leave + rejoin + leave again + rejoin + final: three stints, still one day
b = new(3)
daemon.clan_match_started([b], "9ae893e8")
daemon.clan_report(b, 45, 2); daemon.clan_rejoin_after_booking(b, "9ae893e8")
daemon.clan_report(b, 100, 2); daemon.clan_rejoin_after_booking(b, "9ae893e8")
daemon.clan_report(b, 280, 2)
check(core(b) == core(ctl) and players(b) == (425, 1), "three stints (45 + 100 + 280): one day, 425 parts, players %s" % (players(b),))

# C: a daemon restart between the stints (memory marks gone, DB snapshot stays)
c_ = new(4)
daemon.clan_match_started([c_], "9ae893e8")
daemon.clan_report(c_, 45, 2)
daemon.CLAN_DONE.clear(); daemon.CLAN_REBOOK.clear(); daemon.CLAN_CREDITED.clear()
daemon.clan_rejoin_after_booking(c_, "9ae893e8")
daemon.CLAN_REBOOK.clear()
daemon.clan_report(c_, 380, 2)
check(core(c_) == core(ctl) and players(c_) == (425, 1), "restart between the stints: the persisted snapshot still replaces the booking")

# D: a replay of a booked report with no rejoin since is ignored; the next match books normally and replaces the snapshot
r = new(5)
daemon.clan_match_started([r], "aaaa0001"); daemon.clan_report(r, 100, 2)
daemon.CLAN_DONE.clear(); daemon.CLAN_CREDITED.clear()
before = core(r); daemon.clan_report(r, 100, 2)
check(core(r) == before, "a replayed report (no rejoin) is not booked again")
daemon.clan_match_started([r], "aaaa0002"); daemon.clan_report(r, 100, 2)
check(clanrow(r)["day"] == before[0] + 1 and clanrow(r)["last_mid"] == "aaaa0002", "the next match books its own day")
print("\nall passed" if not FAILS else "\n%d FAILED" % len(FAILS)); sys.exit(1 if FAILS else 0)
