"""Offline tests for match 8bb74ec7: the uneven-team host fallback (host_from_team) and the join-in-progress ping gate (jip_ping_block,
_jip_pick, the queue hold).
Run: python tools/tests/test_jip_ping.py   (no sockets are opened, temp DB)."""
import os, sys, tempfile, time
os.environ.setdefault("T2R_LOBBY_BOOK", "0")   # these cases test the queue without the stable search lobbies (tools/lobbybook.py)
import sys as _t2s, os as _t2o; _t2s.path.append(_t2o.path.normpath(_t2o.path.join(_t2o.path.dirname(_t2o.path.abspath(__file__)), ".."))); import t2rtmp  # noqa: E402,F401  (temp hygiene: tools/t2rtmp.py)

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
FAILS = []
def check(cond, what):
    print(("ok   " if cond else "FAIL ") + what)
    if not cond: FAILS.append(what)

def tok(name):
    return (name.encode().hex() + "0123456789abcdef" * 8)[:64]
NAMES = ["Mid", "Eu", "Na1", "Na2", "Na3", "Na4"]
T = [tok(n) for n in NAMES]
MIDEAST, EU, NA1, NA2, NA3, NA4 = T
os.environ.update(T2R_HOST="127.0.0.1", T2R_PORT="0", T2R_MATCH_SIZE="8", T2R_ENGINE_SLOTS="8", T2R_MIN_PLAYERS="2",
                  T2R_QUEUE_SETTLE="0", T2R_FILL_WAIT="0", T2R_JIP="1", T2R_MAP_VOTE="0", T2R_P2P="0", T2R_PING_KICK_MS="205")
import daemon  # noqa: E402
daemon.DB_PATH = os.path.join(tempfile.mkdtemp(), "daemon.db")
daemon.get_name = lambda t: NAMES[T.index(t)] if t in T else None
daemon.HM.enabled = False
MM = daemon.MM
for t in T: daemon.PRES.touch(t, "x")

def setping(a, b, ms, age=0.0):
    daemon.PING[(a, b)] = ms
    daemon.PING_AT[(a, b)] = time.time() - age

def clear_pings():
    daemon.PING.clear(); daemon.PING_AT.clear()

# ---- host_from_team: match 8bb74ec7 numbers. Middle East + EU (bigger team) v NA; the overall pick is the NA player (smaller team)
clear_pings()
setping(MIDEAST, NA1, 225); setping(MIDEAST, EU, 188); setping(NA1, EU, 205)
h = daemon.host_from_team([MIDEAST, EU], [MIDEAST, NA1, EU])
check(h == EU, "bigger team host = the one with the best pings to every player (EU worst 205, not the queue's first, worst 225)")
h = daemon.host_from_team([EU, MIDEAST], [MIDEAST, NA1, EU])
check(h == EU, "same pick whatever the queue order")
daemon.PING.pop((NA1, EU)); daemon.PING_AT.pop((NA1, EU))
h = daemon.host_from_team([MIDEAST, EU], [MIDEAST, NA1, EU])
check(h == MIDEAST, "a ping unknown: old fallback (queue order)")

# ---- jip_ping_block
clear_pings()
now = time.time()
act = [MIDEAST, EU, NA1]
setping(EU, MIDEAST, 182); setping(NA1, MIDEAST, 195); setping(NA2, MIDEAST, 233)
check(daemon.jip_ping_block(NA2, "m1", MIDEAST, act, set(), now) == 233, "joiner over the limit while most are under it: blocked (233 ms)")
setping(NA2, MIDEAST, 200)
check(daemon.jip_ping_block(NA2, "m1", MIDEAST, act, set(), now) is None, "joiner under the limit: not blocked")
setping(NA2, MIDEAST, 233, age=200.0)
check(daemon.jip_ping_block(NA2, "m1", MIDEAST, act, set(), now) is None, "stale ping (not fresh): not blocked")
setping(NA2, MIDEAST, 233); setping(EU, MIDEAST, 240); setping(NA1, MIDEAST, 250)
check(daemon.jip_ping_block(NA2, "m1", MIDEAST, act, set(), now) is None, "most players high to the host (the kick rule removes nobody): not blocked")
setping(EU, MIDEAST, 182); setping(NA1, MIDEAST, 195)
check(daemon.jip_ping_block(MIDEAST, "m1", MIDEAST, act, set(), now) is None, "the host itself: never blocked")
keep = daemon.PING_KICK_MS
daemon.PING_KICK_MS = 0
check(daemon.jip_ping_block(NA2, "m1", MIDEAST, act, set(), now) is None, "ping limit off: not blocked")
daemon.PING_KICK_MS = keep

# ---- _jip_pick / jip_join with the gate
def running(players, mid="m1", left=400.0):
    for a in ("queue", "seen", "matches", "formed", "settle", "qtime", "departed", "clock", "polled", "joining", "departed_t", "lives", "late_bonus"):
        getattr(MM, a).clear()
    MM.launched.clear(); MM.ended.clear(); MM.started.clear()
    daemon.MATCH_MAP.clear(); daemon.MATCH_P2P.clear(); daemon.SID_KEEP.clear()
    MM.matches[mid] = list(players)
    MM.launched.add(mid); MM.started.add(mid)
    daemon.MATCH_MAP[frozenset(players)] = daemon.map_pool(players)[0]
    daemon.MATCH_P2P[frozenset(players)] = False
    MM.clock[mid] = (left, 600.0, False, time.time())
    return mid

def search(t):
    n = time.time()
    MM.queue[t] = n; MM.seen[t] = n; MM.settle[t] = 0

mid = running([MIDEAST, EU, NA1])
setping(NA2, MIDEAST, 233)
search(NA2); why = []
check(MM.jip_join(NA2, why) is None and "ping limit" in " ".join(why), "join in progress refuses a joiner the ping check would remove (%s)" % why)
setping(NA2, MIDEAST, 190)
why = []
r = MM.jip_join(NA2, why)
check(r is not None, "the same joiner under the limit is put in (%s)" % why)

# a player removed for its ping comes back: refused while still over the limit
mid = running([MIDEAST, EU, NA1, NA2])
MM.departed[mid] = {NA2}; MM.departed_t[NA2] = time.time() - 120
daemon.PING_KICKED.add((NA2, mid))
setping(NA2, MIDEAST, 233)
search(NA2); why = []
check(MM.jip_join(NA2, why) is None and "ping limit" in " ".join(why), "a player removed for its ping is not let back over the limit (%s)" % why)
daemon.PING_KICKED.discard((NA2, mid))

# ---- queue hold: a running match nobody in the queue may join for ping does not hold the searchers
keep_second = daemon.SECOND_MATCH_MIN
daemon.SECOND_MATCH_MIN = 6
def hold_case(ms3, ms4):
    mid = running([MIDEAST, EU, NA1])
    MM.formed[mid] = time.time() - 300; MM.last_arrival = 0.0; MM._hold_since = 0.0
    setping(NA3, MIDEAST, ms3); setping(NA4, MIDEAST, ms4); setping(NA3, NA4, 40)
    search(NA3); search(NA4)
    return MM.try_form()
r = hold_case(150, 160)
check(r[0] is None, "control: searchers under the limit wait for the running match (queue hold)")
r = hold_case(240, 250)
check(r[0] is not None, "searchers all over the limit to its host are not held: they form their own match (%r)" % (r,))
daemon.SECOND_MATCH_MIN = keep_second

print("\n%d failed" % len(FAILS) if FAILS else "\nall ok")
sys.exit(1 if FAILS else 0)
