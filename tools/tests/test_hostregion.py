"""Offline tests for the performance-aware host pick (op 0xCA, hostmig.PerfScores, daemon.best_host_order, host migration).
Run: python tools/tests/test_hostperf.py   (plain python; temp DB, no sockets)."""
import os, sys, tempfile, itertools
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


JAY_SID = 76561198000000042
SID = {T["jay"]: JAY_SID, T["BrownOwl"]: 1001, T["DeerRun"]: 1002, T["ShadeElk"]: 1003, T["SK"]: 1004, T["alderwood99"]: 1005, T["BlueFox"]: 1006}
daemon.BRIDGES.steamid = lambda t: SID.get(t, 0)
EU, NA = "fra=22+2,ams=27+3,lhr=35", "iad=14+1,ord=30,atl=25"
def locs(**kw):
    daemon.PING_LOC.clear()
    for n, v in kw.items():
        daemon.PING_LOC[T[n]] = v
def host(pl=None):
    return daemon.tag(daemon.best_host_order(list(pl or players))[0])
daemon.PERF.by_token.clear(); daemon.PERF.by_steam.clear()

# ---- decode
check(hostmig.region_of("fra=22+2,ams=27+3") == "EU" and hostmig.region_of("iad=14+1,ord=30") == "NA-east", "region_of: EU / NA-east")
check(hostmig.region_of("sea=20,lax=30") == "NA-west" and hostmig.region_of("sgp=10,hkg=40") == "other", "region_of: NA-west / other")
check(hostmig.region_of("lhr=90,iad=20") == "NA-east", "region_of: lowest-ping data centre decides")
check(hostmig.region_of("") is None and hostmig.region_of("zzz=5") is None and hostmig.region_of(None) is None, "region_of: unknown -> None")
check(hostmig.parse_pins("76561198000000042:EU, 5:NA-east") == {JAY_SID: "EU", 5: "NA-east"}, "parse_pins")

# ---- no pin: majority region
hostmig.PINS = {}
locs(jay=EU, DeerRun=EU, ShadeElk=EU, SK=NA, alderwood99=NA, BrownOwl=NA, BlueFox=NA)
check(host() == "BlueFox", "no pin, NA majority (4 vs 3): best NA candidate (Blue, worst 110)")
check(host([T[n] for n in NAMES if n != "BlueFox"]) == "ShadeElk", "3 EU vs 3 NA tie: EU has the lower combined ping (136 vs 188) -> EU, ShadeElk (141)")
locs(jay=EU, DeerRun=EU, ShadeElk=EU, SK=NA, alderwood99=NA, BrownOwl=NA, BlueFox=EU)
check(host() == "BlueFox", "no pin, 4 EU (incl. Blue) vs 3 NA: Blue (110) hosts from EU")
# stuttering Blue in the EU pool: next EU candidate by rule
daemon.PERF.report(T["BlueFox"], {"n250": 12, "n1000": 4, "worst": 2000, "avg_ms": 17.0, "vram": 0}, 1006)
check(host() == "ShadeElk", "stuttering Blue (110+80) loses to ShadeElk (141) inside the EU pool")
daemon.PERF.by_token.clear(); daemon.PERF.by_steam.clear()

# ---- pin: owner in the match -> EU whatever the majority
hostmig.PINS = hostmig.parse_pins("76561198000000042:EU")
locs(jay=EU, DeerRun=EU, ShadeElk=EU, SK=NA, alderwood99=NA, BrownOwl=NA, BlueFox=NA)
check(host() == "ShadeElk", "pin EU, NA majority 4 vs 3: EU host anyway (ShadeElk, worst 141)")
no_jas = [T[n] for n in NAMES if n != "jay"]
check(host(no_jas) == "BlueFox", "owner not in the match: pin inactive, NA majority -> Blue")
locs(jay=NA, DeerRun=NA, ShadeElk=NA, SK=NA, alderwood99=NA, BrownOwl=NA, BlueFox=NA)
check(host() == "BlueFox", "pin EU but nobody is EU: everyone is a candidate")

# ---- too many unknown regions: old rule
locs(jay=EU, DeerRun=EU)
hostmig.PINS = {}
check(host() == "BlueFox", "5 of 7 regions unknown: plain worst-ping rule")
locs()
check(host() == "BlueFox", "no locations at all: plain rule")

# ---- log
LOGS = []
real_log = daemon.log
daemon.log = lambda *a: LOGS.append(" ".join(map(str, a)))
hostmig.PINS = hostmig.parse_pins("76561198000000042:EU")
locs(jay=EU, DeerRun=EU, ShadeElk=EU, SK=NA, alderwood99=NA, BrownOwl=NA, BlueFox=NA)
host()
daemon.log = real_log
check(any(l.startswith("HOST-PICK region: region pin EU (3 of 7)") for l in LOGS), "HOST-PICK logs the region decision: " + next((l for l in LOGS if "region" in l), "-")[:150])
check(sum(l.startswith("HOST-PICK candidate") for l in LOGS) == 3, "only the EU pool is listed as candidates")

# ---- migration follows region + pin
def migrated(order, pins):
    hostmig.PINS = pins
    hm = hostmig.HostMigration(True, now=lambda: 1000.0, log=lambda *a: None, ping=lambda a, b: daemon.pair_ping(a, b),
                               perf=daemon.perf_penalty, pool=lambda ts: daemon.host_pool(ts))
    hm.start("m", order)
    for t in order[1:]:
        hm.poll(t, 0)
    hm.depart(order[0], "crashed")
    return daemon.tag(order[hm.host_info("m")["host"]])
order = [T["ShadeElk"], T["jay"], T["BrownOwl"], T["SK"], T["BlueFox"]]     # ShadeElk (EU) leaves
check(migrated(order, hostmig.parse_pins("76561198000000042:EU")) == "jay", "migration with owner pin: the only EU survivor (jay) takes over")
check(migrated(order, {}) == "BlueFox" or migrated(order, {}) == "BrownOwl", "migration without pin: NA majority survivors (Blue / BrownOwl)")

print("\n%d failure(s)" % len(FAILS))
sys.exit(1 if FAILS else 0)
