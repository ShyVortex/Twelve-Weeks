"""Offline test: same-region matchmaking priority - hostmig.region_first, the try_form overflow sort, the JIP same-region host
preference, the 190 ms ping limit default. Run: python tools/tests/test_region_mm.py [daemon dir]   (no sockets, temp DB)."""
import os, sys, tempfile, time
D = sys.argv[1] if len(sys.argv) > 1 else os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, D)
FAILS = []
def check(c, w):
    print(("ok   " if c else "FAIL ") + w)
    if not c: FAILS.append(w)

import hostmig as H
reg = {"a": "EU", "b": "NA-east", "c": "EU", "d": None, "e": "other", "f": "NA-east", "g": "NA-east"}
o, lead = H.region_first(list("abcdefg"), reg.get)
check(lead == "NA-east" and o == list("bfgacde"), "majority NA-east first, stable order: %s %s" % (lead, o))
o, lead = H.region_first(list("abcd"), reg.get)
check(lead == "EU" and o == list("acbd"), "tie EU 2 / NA 1 -> EU: %s" % o)
o, lead = H.region_first(list("abcf"), reg.get)
check(lead == "EU" and o == list("acbf"), "tie 2/2 -> earliest searcher's region (EU): %s" % o)
o, lead = H.region_first(list("de"), reg.get)
check(lead is None and o == list("de"), "no known region -> unchanged")
o, lead = H.region_first(list("abcfg"), reg.get, waited_fn=lambda t: 100 if t == "a" else 0, max_wait=90)
check(o == list("abfgc") or o[0] == "a", "long waiter keeps place: %s" % o)
party = {"d": ["d", "c"], "c": ["d", "c"]}
o, lead = H.region_first(list("bdfc"), reg.get, members_fn=lambda t: party.get(t, [t]))
check(lead == "NA-east" and o == list("bfdc"), "party d+c counts as EU (c), NA first: %s" % o)

def tok(n): return (n.encode().hex() + "0123456789abcdef" * 8)[:64]
NAMES = ["E%d" % i for i in range(6)] + ["N%d" % i for i in range(5)]
T = [tok(n) for n in NAMES]
os.environ.update(T2R_HOST="127.0.0.1", T2R_PORT="0", T2R_MATCH_SIZE="8", T2R_ENGINE_SLOTS="8", T2R_MIN_PLAYERS="2",
                  T2R_QUEUE_SETTLE="0", T2R_FILL_WAIT="0", T2R_JIP="1", T2R_MAP_VOTE="0", T2R_P2P="0")
os.chdir(tempfile.mkdtemp())
import daemon
daemon.DB_PATH = os.path.join(tempfile.mkdtemp(), "daemon.db")
daemon.get_name = lambda t: NAMES[T.index(t)] if t in T else None
MM = daemon.MM
for t in T: daemon.PRES.touch(t, "x")
for n, t in zip(NAMES, T): daemon.REGION[t] = "EU" if n[0] == "E" else "NA-east"
check(daemon.PING_KICK_MS == 190, "ping limit default 190 (%d)" % daemon.PING_KICK_MS)

def reset():
    for a in ("queue", "seen", "matches", "formed", "settle", "qtime", "departed", "clock", "polled", "joining", "departed_t", "lives", "late_bonus"):
        getattr(MM, a).clear()
    MM.launched.clear(); MM.ended.clear(); MM.started.clear()
    daemon.MATCH_MAP.clear(); daemon.MATCH_P2P.clear(); daemon.SID_KEEP.clear()
def add_match(mid, players, left=400.0):
    MM.matches[mid] = list(players); MM.launched.add(mid); MM.started.add(mid)
    daemon.MATCH_MAP[frozenset(players)] = daemon.map_pool(players)[0]
    daemon.MATCH_P2P[frozenset(players)] = False
    MM.clock[mid] = (left, 600.0, False, time.time())
def search(t, ago=0.0):
    now = time.time(); MM.queue[t] = now - ago; MM.seen[t] = now; MM.settle[t] = 0

# JIP: EU-host match of 3 (fuller) vs NA-host match of 2 -> NA joiner takes the NA match, EU joiner the EU match
reset()
add_match("mEU", [T[0], T[1], T[2]]); add_match("mNA", [T[6], T[7]])
search(T[8]); why = []
r = MM._jip_pick(T[8], why)
check(r is not None and r[1] == "mNA", "NA joiner -> NA-host match despite the fuller EU one (%s %s)" % (r and r[1], why))
search(T[3]); r = MM._jip_pick(T[3], [])
check(r is not None and r[1] == "mEU", "EU joiner -> EU-host match (%s)" % (r and r[1]))
daemon.MM_REGION_ON = False
r = MM._jip_pick(T[8], [])
check(r is not None and r[1] == "mEU", "region off -> fullest match as before (%s)" % (r and r[1]))
daemon.MM_REGION_ON = True

# formation: 10 searchers, 4 NA waited longest, then 6 EU -> lead region EU (6 v 4): all 6 EU + the 2 longest NA; without the rule 4 NA + 4 EU
def form(order, ages):
    reset()
    for t, a in zip(order, ages): search(t, ago=a)
    MM.try_form()
    return MM.matches and list(MM.matches.values())[0] or []
order = T[6:10] + T[0:6]
ages = [60 - i for i in range(10)]
pl = form(order, ages)
print("formed:", [daemon.get_name(t) for t in pl])
check(len(pl) == 8 and set(T[0:6]) <= set(pl) and set(T[6:8]) <= set(pl), "overflow: 6 EU + the 2 longest-waiting NA")
daemon.MM_REGION_ON = False
pl = form(order, ages)
check(len(pl) == 8 and set(T[6:10]) <= set(pl), "region off -> queue order (4 NA + 4 EU)")
daemon.MM_REGION_ON = True
ages2 = [120, 119] + ages[2:]
pl = form(order, ages2)
print("formed:", [daemon.get_name(t) for t in pl])
check(len(pl) == 8 and set(T[6:8]) <= set(pl) and T[8] not in pl and T[9] not in pl and set(T[0:6]) <= set(pl), "NA waiting >= 90 s keep their place, other NA wait")
print("FAILS:", FAILS)
sys.exit(1 if FAILS else 0)
