"""Offline test: ping gate (players are not matched together over the ping limit).
hostmig.ping_fit, the try_form gate, the host pick limit, the join-in-progress block without the majority exception.
Run: python tests/test_ping_gate.py [daemon dir]   (no sockets, temp DB)."""
import os, sys, tempfile, time
D = sys.argv[1] if len(sys.argv) > 1 else os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, D)
FAILS = []
def check(c, w):
    print(("ok   " if c else "FAIL ") + w)
    if not c: FAILS.append(w)

import hostmig as H

# ---- ping_fit (pure)
# two players 16 ms apart, a third 254 / 264 ms to them
P = {frozenset("ID"): 16, frozenset("IK"): 254, frozenset("DK"): 264}
pair = lambda a, b: P.get(frozenset((a, b)))
kept, dropped, h, info = H.ping_fit(list("IKD"), pair, 190)
check(kept == ["I", "D"] and dropped == ["K"] and h == "I", "far player: K dropped, I hosts (%s %s %s %s)" % (kept, dropped, h, info))
kept, dropped, h, info = H.ping_fit(list("KID"), pair, 190)
check(kept == ["I", "D"] and dropped == ["K"], "K first in the queue: still dropped, the 2 that fit stay (%s)" % kept)
kept, dropped, h, _ = H.ping_fit(list("IKD"), pair, 0)
check(dropped == [] and h is None, "limit 0 = off")
kept, dropped, h, info = H.ping_fit(list("IKD"), lambda a, b: None, 190)
check(dropped == [] and info == "no pings known", "no pings known = everybody kept")
# unknown pings are not judged
P2 = {frozenset("ab"): 100, frozenset("ac"): None}
kept, dropped, h, _ = H.ping_fit(list("abc"), lambda a, b: P2.get(frozenset((a, b))), 190)
check(dropped == [], "unknown ping to c is not judged (%s)" % dropped)
# EU host keeps more than a NA host: 3 EU (30 ms apart) + 2 NA (40 apart), EU<>NA 120..260
P3 = {}
for a in "abc":
    for b in "abc":
        if a < b: P3[frozenset((a, b))] = 30
P3[frozenset("xy")] = 40
for e, ms in zip("abc", (120, 200, 260)):
    for n in "xy": P3[frozenset((e, n))] = ms
pair3 = lambda a, b: P3.get(frozenset((a, b)))
kept, dropped, h, info = H.ping_fit(list("xyabc"), pair3, 190)
check(h == "a" and kept == list("xya") + [] or (h == "a" and set(kept) == set("xyabc") - set(dropped)), "best host found: %s keeps %s (%s)" % (h, kept, info))
check(set(dropped) == set() or len(kept) >= 3, "keeps the larger group (%s)" % kept)
# a: x 120, y 120, b 30, c 30 -> a keeps all 5
check(dropped == [] and h == "a", "host a has everybody <= 190: nobody dropped (%s %s)" % (dropped, h))
# party dropped whole: K and a party mate M (M fits the host, K does not)
P4 = dict(P); P4[frozenset("IM")] = 50; P4[frozenset("DM")] = 50; P4[frozenset("KM")] = 195   # (M close to I / D, K far from all: no host keeps K)
kept, dropped, h, _ = H.ping_fit(list("IDKM"), lambda a, b: P4.get(frozenset((a, b))), 190, units_fn=lambda t: ["K", "M"] if t in "KM" else [t])
check(set(dropped) == {"K", "M"} and kept == ["I", "D"], "party K+M dropped together (%s)" % dropped)
# no-host: I may not host -> D hosts, K still dropped
kept, dropped, h, _ = H.ping_fit(list("IKD"), pair, 190, host_ok=lambda t: t != "I")
check(h == "D" and dropped == ["K"], "no-host I: D hosts (%s)" % h)

# ---- daemon: try_form gate, host pick, join in progress
def tok(n): return (n.encode().hex() + "0123456789abcdef" * 8)[:64]
NAMES = ["Sa1", "Sa2", "Eu1", "Eu2", "Eu3", "Eu4"]
T = [tok(n) for n in NAMES]
os.environ.update(T2R_HOST="127.0.0.1", T2R_PORT="0", T2R_MATCH_SIZE="8", T2R_ENGINE_SLOTS="8", T2R_MIN_PLAYERS="2",
                  T2R_QUEUE_SETTLE="0", T2R_FILL_WAIT="0", T2R_JIP="1", T2R_MAP_VOTE="0", T2R_P2P="0")
os.chdir(tempfile.mkdtemp())
import daemon
daemon.DB_PATH = os.path.join(tempfile.mkdtemp(), "daemon.db")
daemon.get_name = lambda t: NAMES[T.index(t)] if t in T else None
MM = daemon.MM
for t in T: daemon.PRES.touch(t, "x")
reg = {"Sa1": "other", "Sa2": "other", "Eu1": "EU", "Eu2": "EU", "Eu3": "EU", "Eu4": "EU"}
for n, t in zip(NAMES, T): daemon.REGION[t] = reg[n]
SA, EU = ("Sa1", "Sa2"), ("Eu1", "Eu2", "Eu3", "Eu4")
def setping(a, b, ms):
    now = time.time()
    for k in ((T[NAMES.index(a)], T[NAMES.index(b)]), (T[NAMES.index(b)], T[NAMES.index(a)])):
        daemon.PING[k] = [ms]; daemon.PING_AT[k] = now
for a in NAMES:
    for b in NAMES:
        if a < b:
            same = (a in SA) == (b in SA)
            setping(a, b, 16 if (a in SA and b in SA) else 40 if same else 260)
def reset():
    for a in ("queue", "seen", "matches", "formed", "settle", "qtime", "departed", "clock", "polled", "joining", "departed_t", "lives", "late_bonus"):
        getattr(MM, a).clear()
    MM.launched.clear(); MM.ended.clear(); MM.started.clear()
    daemon.MATCH_MAP.clear(); daemon.MATCH_P2P.clear(); daemon.SID_KEEP.clear()
def search(t, ago=0.0):
    now = time.time(); MM.queue[t] = now - ago; MM.seen[t] = now; MM.settle[t] = 0
def names(pl): return [daemon.get_name(t) for t in pl]

check(daemon.MM_PING_GATE, "gate on by default")
reset()
for i, n in enumerate(("Sa1", "Eu1", "Sa2")): search(T[NAMES.index(n)], ago=30 - i)
MM.try_form()
pl = list(MM.matches.values())[0] if MM.matches else []
check(set(names(pl)) == {"Sa1", "Sa2"} and T[2] in MM.queue, "far-player replay: Sa1 + Sa2 formed, Eu1 stays searching (%s)" % names(pl))
reset()
for i, n in enumerate(("Sa1", "Eu1", "Sa2")): search(T[NAMES.index(n)], ago=30 - i)
daemon.MM_PING_GATE = False
MM.try_form()
pl = list(MM.matches.values())[0] if MM.matches else []
check(len(pl) == 3, "gate off: all 3 formed as before (%s)" % names(pl))
daemon.MM_PING_GATE = True
# lone Eu1 + Sa1: never matched together
reset()
search(T[0], 30); search(T[2], 29)
MM.try_form()
check(not MM.matches, "2 searchers 260 ms apart: no match (%s)" % [names(p) for p in MM.matches.values()])
# 4 EU + 2 SA: EU group forms (largest fitting group), SA wait
reset()
for i, t in enumerate(T): search(t, ago=60 - i)
MM.try_form()
pl = list(MM.matches.values())[0] if MM.matches else []
check(set(names(pl)) == set(EU), "6 searchers: the 4 EU formed, SA kept searching (%s)" % names(pl))
# then SA form their own on the next pass
MM.try_form()
check(len(MM.matches) == 2 and any(set(names(p)) == set(SA) for p in MM.matches.values()), "next pass: SA pair forms its own match")

# host pick: 3 players, region majority would pick an EU host whose worst ping is over the limit
# a lobby Eu1, Eu2, Sa1 with Eu1<>Sa1 180, Eu2<>Sa1 260, Eu1<>Eu2 40 -> only Eu1 keeps everyone <= 190
setping("Eu1", "Sa1", 180)
order = daemon.best_host_order([T[3], T[0], T[2]])
check(order[0] == T[2], "host pick: Eu1 (worst 180) hosts, not Eu2 (worst 260) (%s)" % names(order))
setping("Eu1", "Sa1", 260)

# join in progress: SA-host match where one EU player is already in at 254 ms -> another EU joiner at 280 ms is refused
reset()
mp = [T[0], T[2], T[1]]
MM.matches["m1"] = list(mp); MM.launched.add("m1"); MM.started.add("m1")
daemon.MATCH_MAP[frozenset(mp)] = daemon.map_pool(mp)[0]; daemon.MATCH_P2P[frozenset(mp)] = False
MM.clock["m1"] = (400.0, 600.0, False, time.time())
setping("Eu1", "Sa1", 254); setping("Eu2", "Sa1", 280)
ms = daemon.jip_ping_block(T[3], "m1", T[0], [T[0], T[2]], set(), time.time())
check(ms == 280, "joiner at 280 ms refused although the one other non-host player is high too (%s)" % ms)
daemon.MM_PING_GATE = False
ms = daemon.jip_ping_block(T[3], "m1", T[0], [T[0], T[2]], set(), time.time())
check(ms is None, "gate off: old majority exception lets it in (%s)" % ms)
daemon.MM_PING_GATE = True
search(T[3]); why = []
r = MM._jip_pick(T[3], why)
check(r is None and any("ping limit" in w for w in why), "_jip_pick refuses Eu2 with the ping reason (%s %s)" % (r, why))

# ping_check: a stale (unknown) reading does not restart the 60 s timer 
reset()
mp = [T[0], T[2], T[1]]
MM.matches["m2"] = list(mp); MM.launched.add("m2"); MM.started.add("m2"); MM.formed["m2"] = time.time() - 600
setping("Eu1", "Sa1", 255); setping("Sa2", "Sa1", 16)
t0 = time.time()
daemon.PING_HIGH.clear(); daemon.PING_KICKED.clear()
kicked = []
daemon.kick_token = lambda tok, *a, **k: (kicked.append(tok), ["kicked"])[1]
daemon.ping_check(t0)
check((T[2], "m2") in daemon.PING_HIGH, "timer starts at a fresh 255 ms")
for k in ((T[2], T[0]), (T[0], T[2])): daemon.PING_AT[k] = t0 - 200      # reading goes stale
daemon.ping_check(t0 + 30)
check(daemon.PING_HIGH.get((T[2], "m2")) == t0, "stale reading keeps the timer (%s)" % daemon.PING_HIGH.get((T[2], "m2")))
for k in ((T[2], T[0]), (T[0], T[2])): daemon.PING_AT[k] = t0 + 61         # fresh high reading again
r = daemon.ping_check(t0 + 61)
check(T[2] in r and kicked == [T[2]], "removed at 61 s on the next fresh high reading (%s)" % names(r))
print("FAILS:", FAILS)
sys.exit(1 if FAILS else 0)
