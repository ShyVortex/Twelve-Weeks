"""Offline tests for the performance-aware host pick (op 0xCA, hostmig.PerfScores, daemon.best_host_order, host migration).
Run: python tools/tests/test_hostperf.py   (plain python; temp DB, no sockets)."""
import os, sys, tempfile
import sys as _t2s, os as _t2o; _t2s.path.append(_t2o.path.normpath(_t2o.path.join(_t2o.path.dirname(_t2o.path.abspath(__file__)), ".."))); import t2rtmp  # noqa: E402,F401  (temp hygiene: tools/t2rtmp.py)

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.dirname(HERE)
sys.path.insert(0, TOOLS)
os.environ.update(T2R_HOST="127.0.0.1", T2R_PORT="0", T2R_P2P="0")
os.environ.pop("T2R_NO_HOST_PICK", None)
import daemon, hostmig  # noqa: E402
daemon.DB_PATH = os.path.join(tempfile.mkdtemp(), "daemon.db")

FAILS = []
def check(cond, what):
    print(("ok   " if cond else "FAIL ") + what)
    if not cond:
        FAILS.append(what)

NAMES = ["BlueFox", "jay", "BrownOwl", "DeerRun", "ShadeElk", "SK", "alderwood99"]
def tok(n): return (n.encode().hex() + "0123456789abcdef" * 8)[:64]
T = {n: tok(n) for n in NAMES}
daemon.tag = lambda t: next((n for n, x in T.items() if x == t), t[:6])
PINGS = {'BlueFox<>jay': 110, 'BlueFox<>BrownOwl': 42, 'BlueFox<>DeerRun': 107, 'BlueFox<>ShadeElk': 94,
         'BlueFox<>SK': 68, 'BlueFox<>alderwood99': 42, 'jay<>BrownOwl': 113, 'jay<>DeerRun': 43, 'jay<>ShadeElk': 49,
         'jay<>SK': 163, 'jay<>alderwood99': 138, 'BrownOwl<>DeerRun': 109, 'BrownOwl<>ShadeElk': 97, 'BrownOwl<>SK': 74,
         'BrownOwl<>alderwood99': 52, 'DeerRun<>ShadeElk': 44, 'DeerRun<>SK': 159, 'DeerRun<>alderwood99': 130,
         'ShadeElk<>SK': 141, 'ShadeElk<>alderwood99': 121, 'SK<>alderwood99': 62}
daemon.PING.clear()
for k, v in PINGS.items():
    a, b = k.split("<>")
    daemon.PING[(T[a], T[b])] = v
players = [T[n] for n in NAMES]

def report(name, n250, n1000, worst=0, vram=0):
    pl = bytes.fromhex(T[name]) if False else T[name].encode("latin1")
    pl += bytes([1, n250, n1000]) + worst.to_bytes(2, "little") + (170).to_bytes(2, "little") + bytes([vram])
    rep = daemon.perf_op(pl)
    return rep

def host(pl=None):
    out = daemon.best_host_order(list(pl or players))
    return daemon.tag(out[0])

# ---- op parsing / reply
r = report("BlueFox", 0, 0)
check(r is not None and r[2] == 0xCB and r.endswith(b"ok=1"), "op 0xCA answered with 0xCB ok=1")
check(hostmig.parse_perf(b"x" * 10) is None and hostmig.parse_perf(T["jay"].encode() + bytes([9, 0, 0, 0, 0, 0, 0, 0])) is None, "short / wrong-version payload rejected (no reply)")
check(daemon.perf_op(b"short") is None, "perf_op ignores a bad payload")

# ---- no reports = unknown = plain ping pick
daemon.PERF.by_token.clear(); daemon.PERF.by_steam.clear()
check(host() == "BlueFox", "no stall reports: best ping wins (BlueFox, worst 110)")
# ---- clean machine reports do not change it
for n in NAMES: report(n, 0, 0)
check(host() == "BlueFox", "everyone reports 0 stalls: BlueFox stays host")
# ---- Blue stutters: loses to the other host (worst 113 <= 110 + 40)
report("BlueFox", 12, 4, 2400)
check(hostmig.perf_penalty(daemon.PERF.get(T["BlueFox"])) == 80, "12 stalls / 4 over 1 s = severe: penalty 80 ms")
check(host() == "BrownOwl", "Blue stuttering: BrownOwl (worst 113) takes host")
report("BlueFox", 1, 2, 1500)
check(hostmig.perf_penalty(daemon.PERF.get(T["BlueFox"])) == 40 and host() == "BrownOwl", "2 stalls >= 1 s: penalty 40, BrownOwl takes host")
report("BlueFox", 1, 1, 1100)
check(host() == "BlueFox", "one 1 s stall alone is not stuttering")
report("BlueFox", 6, 0, 400)
check(host() == "BrownOwl", "6 stalls >= 250 ms count too")
# ---- a candidate more than the penalty away keeps losing: penalised player's rival worse by > 40
report("BlueFox", 2, 2, 1200)
daemon.PING[(T["BrownOwl"], T["jay"])] = 160            # the other host's worst now 160 > 110 + 40
check(host() == "alderwood99", "BrownOwl now worse than Blue+40: alderwood99 (worst 138 < 150) takes it instead")
daemon.PING[(T["BrownOwl"], T["jay"])] = 113
# ---- the stuttering one is not penalised when the whole lobby stutters equally
for n in NAMES: report(n, 12, 4, 2400)
check(host() == "BlueFox", "everyone stutters equally: ping decides again")
for n in NAMES: report(n, 0, 0)
# ---- stale report = unknown
report("BlueFox", 12, 4, 2400)
daemon.PERF.now = lambda: __import__("time").time() + hostmig.PERF_FRESH_S + 5
check(host() == "BlueFox", "stale report (older than %d s) is ignored" % hostmig.PERF_FRESH_S)
daemon.PERF.now = __import__("time").time
# ---- per Steam account: a new token of the same account inherits the report
sid = 76561198000000001
daemon.PERF.by_token.clear(); daemon.PERF.by_steam.clear()
daemon.PERF.report(T["BlueFox"], {"n250": 12, "n1000": 4, "worst": 2000, "avg_ms": 17.0, "vram": 0}, sid)
check(daemon.PERF.penalty("brand-new-token", sid) == 80 and daemon.PERF.penalty("brand-new-token", 0) == 0, "steam-account fallback for a token without a report")
daemon.PERF.by_token.clear(); daemon.PERF.by_steam.clear()
# ---- opt out
report("BlueFox", 12, 4, 2400)
hostmig.PERF_ON = False
check(host() == "BlueFox", "T2R_HOSTPERF=0 (PERF_ON False): no penalty")
hostmig.PERF_ON = True
# ---- log lines
LOGS = []
real_log = daemon.log
daemon.log = lambda *a: LOGS.append(" ".join(map(str, a)))
host()
daemon.log = real_log
cl = [l for l in LOGS if l.startswith("HOST-PICK candidate BlueFox")]
check(len(cl) == 1 and "penalty 80" in cl[0] and "worst 110" in cl[0], "HOST-PICK logs each candidate with ping, stalls and penalty: " + (cl[0] if cl else "-"))
check(sum(l.startswith("HOST-PICK candidate") for l in LOGS) == 7, "one candidate line per player")

# ---- host migration among the survivors uses the same penalty
clk = [1000.0]
hm = hostmig.HostMigration(True, now=lambda: clk[0], log=lambda *a: None, ping=lambda a, b: daemon.pair_ping(a, b), perf=daemon.perf_penalty)
# slot order: A hosts, then B, C, D, E (A leaves)
order = [T["jay"], T["BlueFox"], T["BrownOwl"], T["ShadeElk"], T["DeerRun"]]
def migrated(blue_bad):
    daemon.PERF.by_token.clear()
    report("BlueFox", 12 if blue_bad else 0, 4 if blue_bad else 0, 2000)
    hm2 = hostmig.HostMigration(True, now=lambda: clk[0], log=lambda *a: None, ping=lambda a, b: daemon.pair_ping(a, b), perf=daemon.perf_penalty)
    hm2.start("m", order)
    for t in order[1:]:
        hm2.poll(t, 0)
    hm2.depart(order[0], "crashed")
    return daemon.tag(order[hm2.host_info("m")["host"]])
# survivors: B worst 107 (E), C 109, D 97 -> D
check(migrated(False) == "ShadeElk", "migration without stalls: lowest worst ping (ShadeElk)")

print("\n%d failure(s)" % len(FAILS))
sys.exit(1 if FAILS else 0)
