"""Offline tests for the one-way inbound alarm (re/oneway-p2p-1019.md): op 0xCA alarm trailer -> hostcap.parse_oneway, HostCap.oneway_note/get,
daemon.perf_op / oneway_note logging and the HOST-PICK log line.  Run: python tools/tests/test_oneway.py  (plain python; temp DB, no sockets)."""
import os, sys, tempfile
import sys as _t2s, os as _t2o; _t2s.path.append(_t2o.path.normpath(_t2o.path.join(_t2o.path.dirname(_t2o.path.abspath(__file__)), ".."))); import t2rtmp  # noqa: E402,F401

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
os.environ.update(T2R_HOST="127.0.0.1", T2R_PORT="0", T2R_P2P="0")
os.environ.pop("T2R_NO_HOST_PICK", None)
os.environ.pop("T2R_HOST_CAP", None)
import daemon, hostmig, hostcap  # noqa: E402
daemon.DB_PATH = os.path.join(tempfile.mkdtemp(), "daemon.db")

FAILS = []
def check(cond, what):
    print(("ok   " if cond else "FAIL ") + what)
    if not cond:
        FAILS.append(what)

def tok(n): return (n.encode().hex() + "0123456789abcdef" * 8)[:64]
T = {n: tok(n) for n in "ABC"}
daemon.tag = lambda t: next((n for n, x in T.items() if x == t), t[:6])
logs = []
daemon.log = lambda *a: logs.append(" ".join(str(x) for x in a))
daemon.evt = lambda *a: None

def body(flags, token="A"):
    return T[token].encode("latin1") + bytes([1, 0, 0]) + (0).to_bytes(2, "little") + (170).to_bytes(2, "little") + bytes([flags])
CAP = bytes([1]) + (300).to_bytes(2, "little") + (400).to_bytes(2, "little") + bytes([0, 3])
def alarm(quiet=5, rx=0, tx=120, secs=6):
    return bytes([1, quiet]) + rx.to_bytes(2, "little") + tx.to_bytes(2, "little") + bytes([secs])

p = body(2) + CAP + alarm()
check(len(p) == 86, "payload layout: 72 + 7 + 7 bytes")
check(hostcap.parse_oneway(p) == {"quiet_s": 5, "rx_pkts": 0, "tx_kb": 120, "in_match_s": 6}, "alarm decoded")
check(hostcap.parse_oneway(body(0) + CAP + alarm()) is None, "flag bit1 clear: no alarm even with trailing bytes")
check(hostcap.parse_oneway(body(2) + CAP) is None, "flag set but no trailer 2 (short): ignored")
check(hostcap.parse_oneway(body(2)) is None, "old ext (no trailers): ignored")
check(hostcap.parse_oneway(body(2) + CAP + bytes([2]) + alarm()[1:]) is None, "unknown alarm version ignored")
check(hostmig.parse_perf(p) is not None and hostmig.parse_perf(p)[1]["vram"] == 0, "the old performance parser accepts it; bit1 is not 'vram over budget'")
check(hostcap.parse_cap(p) is not None, "the capacity trailer still decodes")

clock = [1000000.0]
hc = hostcap.HostCap(lambda: daemon.db(), now=lambda: clock[0], log=lambda *a: None)
check(hc.oneway_get(T["A"]) == (0, 0), "no record: (0, 0), table missing is fine")
check(hc.oneway_note(T["A"], "m1", True) == (1, 1), "first alarm as host")
check(hc.oneway_note(T["A"], "m2", False) == (2, 1), "second alarm as client")
check(hc.oneway_get(T["A"]) == (2, 1) and hc.oneway_get(T["B"]) == (0, 0), "per token")
clock[0] += 31 * 86400
check(hc.oneway_get(T["A"]) == (0, 0), "older than 30 days counts as nothing")
clock[0] -= 31 * 86400

# --- daemon wiring: perf_op with an alarm; the match is known to the match maker / host migration
daemon.HOSTCAP = hc
players = [T["A"], T["B"], T["C"]]
daemon.MM.active_of = lambda t: ("m9", players)
daemon.HM.snapshot = lambda mid: (0.0, list(players), [0, 1, 2], 0)
daemon.MATCH_P2P[frozenset(players)] = True
logs.clear()
r = daemon.perf_op(p)
check(r is not None, "perf_op still answers")
check(any(l.startswith("ONEWAY A HOST slot 0 match m9 net steam-p2p") for l in logs), "ONEWAY log: host, slot, match, transport")
check(any("sent 120 KB and got nothing for 5 s (0 datagrams in 6 s" in l for l in logs), "ONEWAY log carries the numbers")
check(hc.oneway_get(T["A"])[1] >= 1, "recorded as a host alarm")
logs.clear()
daemon.perf_op(body(0, "B") + CAP)
check(not any("ONEWAY" in l for l in logs), "a normal report logs nothing")
logs.clear()
daemon.perf_op(body(2, "B") + CAP + alarm(7, 3, 50, 20))
check(any(l.startswith("ONEWAY B client slot 1") for l in logs), "a client alarm is labelled client")

# a broken record must never break the report
def bad(*a): raise RuntimeError("db down")
hc.oneway_note = bad
logs.clear()
check(daemon.perf_op(p) is not None and any("ONEWAY ERR" in l for l in logs), "an error in the record is logged and the report is still answered")

print("FAILS:", len(FAILS))
sys.exit(1 if FAILS else 0)
