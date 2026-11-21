"""matchmaking / JIP fixes (see the matchmaking notes under re/): offline tests, plain python, temp DB, no sockets.
Run: python tools/tests/test_mm_premortem.py"""
import os, sys, tempfile, time
import sys as _t2s, os as _t2o; _t2s.path.append(_t2o.path.normpath(_t2o.path.join(_t2o.path.dirname(_t2o.path.abspath(__file__)), ".."))); import t2rtmp  # noqa: E402,F401  (temp hygiene: tools/t2rtmp.py)

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
FAILS = []
def check(cond, what):
    print(("ok   " if cond else "FAIL ") + what)
    if not cond: FAILS.append(what)

def tok(name):
    return (name.encode().hex() + "0123456789abcdef" * 8)[:64]
NAMES = ["Alice", "Bob", "Carol", "Dave", "Eve", "Frank", "Gina", "Hal"]
T = [tok(n) for n in NAMES]

os.environ.update(T2R_HOST="127.0.0.1", T2R_PORT="0", T2R_MATCH_SIZE="8", T2R_ENGINE_SLOTS="8", T2R_MIN_PLAYERS="2",
                  T2R_FILL_WAIT="0", T2R_QUEUE_SETTLE="3", T2R_P2P="0")
import daemon  # noqa: E402
import hostmig  # noqa: E402
daemon.DB_PATH = os.path.join(tempfile.mkdtemp(), "daemon.db")
daemon.get_name = lambda t: NAMES[T.index(t)] if t in T else None
daemon.tag = lambda t: NAMES[T.index(t)] if t in T else t[:6]
for t in T: daemon.PRES.touch(t, "x")
MM = daemon.MM

def reset():
    for a in ("queue", "seen", "matches", "formed", "left", "settle", "qtime", "departed", "departed_t"):
        getattr(MM, a).clear()
    MM.launched.clear(); MM.ended.clear(); MM.started.clear(); MM.last_arrival = 0; MM._hold_since = 0.0
    daemon.PARTIES.of.clear(); daemon.PARTIES.inv.clear()

# ------------------------------------------------------------ (1) a player still settling holds the formation
reset()
now = time.time()
for i in (0, 1, 2):                      # three ready searchers, one of them waited for ever (MAX_WAIT -> want = 2)
    MM.queue[T[i]] = now - 200; MM.seen[T[i]] = now; MM.settle[T[i]] = 0
MM.queue[T[3]] = now - 0.5; MM.seen[T[3]] = now; MM.settle[T[3]] = now + 2.0      # backed out / queued 1 s ago: settles in 2 s
mid, pl = MM.try_form()
check(mid is None, "3 ready + 1 settling: formation held (the 4th player is 2 s from matchable)")
MM.settle[T[3]] = now - 0.1              # he settled
mid, pl = MM.try_form()
check(mid is not None and len(pl) == 4, "the settling player is in the match once he settled: %s" % (len(pl) if pl else pl))

reset()
now = time.time()
for i in (0, 1):
    MM.queue[T[i]] = now - 200; MM.seen[T[i]] = now; MM.settle[T[i]] = 0
MM.queue[T[2]] = now - 0.2; MM.seen[T[2]] = now; MM.settle[T[2]] = now + 2.8
mid, pl = MM.try_form()
check(mid is None, "hold #1 starts")
MM._hold_since = now - (daemon.QUEUE_SETTLE + 2.5)       # held for longer than the bound: never starve a lobby behind one slow settler
mid, pl = MM.try_form()
check(mid is not None and len(pl) == 2, "the hold is bounded (QUEUE_SETTLE + 2 s): the ready players start")

reset()
now = time.time()
for i in range(8):
    MM.queue[T[i]] = now - 5; MM.seen[T[i]] = now; MM.settle[T[i]] = 0
mid, pl = MM.try_form()
check(mid is not None and len(pl) == 8, "a full lobby is never held")

# ------------------------------------------------------------ (2) host region: a tie is not alphabetical, the region never costs 60+ ms
EU, NAE, NAW = "fra=22+2,ams=27+3", "iad=14+1,ord=30", "sea=20,lax=30"
regs = {"a": "EU", "b": "NA-east", "c": "NA-east"}
def region(t): return regs[t]
pings = {("a", "b"): 205, ("a", "c"): 272, ("b", "c"): 83}
def pair(x, y): return pings.get((x, y), pings.get((y, x)))
pool, info = hostmig.region_pool(["a", "b", "c"], region, lambda t: 0, pair, pins={})
check(set(pool) == {"b", "c"}, "majority NA-east (2 v 1): pool = NA-east players (%s)" % info)
regs = {"a": "EU", "b": "NA-east", "c": "other"}
pool, info = hostmig.region_pool(["a", "b", "c"], region, lambda t: 0, pair, pins={})
check(set(pool) == {"a", "b", "c"}, "1/1/1 regions: no region filter, not 'EU because E < N' (%s)" % info)
regs = {"a": "EU", "b": "NA-east"}
pings = {("a", "b"): 205}
pool, info = hostmig.region_pool(["a", "b"], region, lambda t: 0, pair, pins={})
check(set(pool) == {"a", "b"}, "1 v 1 tie: both can host (%s)" % info)
# a mixed-region case: regions EU(player A) NA-east(player B) NA-east(player C, no-host) -> NA-east pool has player B
regs = {"des": "EU", "pee": "NA-east", "mer": "NA-east"}
pings = {("des", "pee"): 205, ("des", "mer"): 272, ("pee", "mer"): 83}
pool, info = hostmig.region_pool(["des", "pee"], region, lambda t: 0, pair, pins={})
check(set(pool) == {"des", "pee"}, "no-host player removed first (2 candidates EU + NA-east tie): both stay (%s)" % info)
regs = {"des": "EU", "pee": "NA-east", "mer": "NA-east"}
pool, info = hostmig.region_pool(["des", "pee"], region, lambda t: 0, pair, pins={}, everyone=["des", "pee", "mer"])
check(pool == ["pee"], "(a player who may not host but counts): NA-east majority 2 v 1 -> a host hosts, not des (%s)" % info)
# a majority region whose best host is far worse than the overall best loses its priority
regs = {"a": "EU", "b": "EU", "c": "NA-east", "d": "NA-east", "e": "NA-east"}
pings = {("a", "b"): 20, ("c", "d"): 190, ("c", "e"): 200, ("d", "e"): 190,
         ("a", "c"): 120, ("a", "d"): 120, ("a", "e"): 120, ("b", "c"): 120, ("b", "d"): 120, ("b", "e"): 120}
pool, info = hostmig.region_pool(list("abcde"), region, lambda t: 0, pair, pins={})
check(set(pool) == set("abcde"), "majority region (NA-east 3) has a worst-case 200 ms host while an EU player has 120 ms: all can host (%s)" % info)
pings = {("a", "b"): 20, ("c", "d"): 40, ("c", "e"): 50, ("d", "e"): 45,
         ("a", "c"): 110, ("a", "d"): 110, ("a", "e"): 110, ("b", "c"): 110, ("b", "d"): 110, ("b", "e"): 110}
pool, info = hostmig.region_pool(list("abcde"), region, lambda t: 0, pair, pins={})
check(set(pool) == set("cde"), "majority region with a good host keeps the region rule (%s)" % info)
# the owner's pin is untouched
regs = {"a": "EU", "b": "NA-east", "c": "NA-east"}
pings = {("a", "b"): 205, ("a", "c"): 272, ("b", "c"): 83}
pool, info = hostmig.region_pool(["a", "b", "c"], region, lambda t: {"a": 7}.get(t, 0), pair, pins={7: "EU"})
check(set(pool) == {"a"}, "an owner pin still forces its region (%s)" % info)

# ------------------------------------------------------------ (3) the result only credits players who were still in the match
import sqlite3
def wins(t):
    with daemon._dblock, daemon.db() as c:
        r = c.execute("SELECT wins, draws FROM players WHERE token=?", (t,)).fetchone()
    return tuple(r) if r else (0, 0)
with daemon._dblock, daemon.db() as c:
    for t in T[:4]:
        c.execute("INSERT OR IGNORE INTO players(token,name,matches,wins,draws,last_seen) VALUES(?,?,1,0,0,?)", (t, "x", time.time()))
daemon.record_result(T[:4], 0, skip={T[2]})       # slots 0,2 = team 0 win; Carol (slot 2) had left
check(wins(T[0]) == (1, 0) and wins(T[2]) == (0, 0) and wins(T[1]) == (0, 0), "winner team 0: Alice +1, Carol (left early) +0, Bob (loser) +0")
daemon.record_result(T[:4], 2, skip={T[1]})
check(wins(T[0]) == (1, 1) and wins(T[1]) == (0, 0) and wins(T[3]) == (0, 1), "draw: everybody but the one who left gets it")
daemon.record_result(T[:4], 1)                    # old call shape: nobody skipped
check(wins(T[1]) == (1, 0) and wins(T[3]) == (1, 1), "old call signature still works")

# ------------------------------------------------------------ (4) a helper that cannot take its 0xF2 slot table = server relay for the match
class FakeConn:
    def __init__(self, ok=True): self.ok, self.sent = ok, []
    def sendall(self, b):
        if not self.ok: raise OSError("link down")
        self.sent.append(bytes(b))
os.environ["T2R_P2P"] = "1"
conns = {t: FakeConn(ok=(t != T[1])) for t in T[:3]}
for i, t in enumerate(T[:3]):
    daemon.BRIDGES.register(t, conns[t], 76561198000000100 + i, 7777 + i)
daemon.push_peers(T[:3])
check(daemon.MATCH_P2P.get(frozenset(T[:3])) is False, "one helper link down while the table is pushed: the match uses the server relay")
conns = {t: FakeConn() for t in T[:3]}
for i, t in enumerate(T[:3]):
    daemon.BRIDGES.register(t, conns[t], 76561198000000100 + i, 7777 + i)
daemon.push_peers(T[:3])
check(daemon.MATCH_P2P.get(frozenset(T[:3])) is True and all(len(c.sent) == 1 for c in conns.values()), "all helpers reachable: Steam P2P, one 0xF2 each")
daemon.MATCH_P2P.clear()

print("%d failure(s)" % len(FAILS))
sys.exit(1 if FAILS else 0)
