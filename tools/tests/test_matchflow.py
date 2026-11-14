"""Offline tests for the 2013 match flow (map vote ops, countdown steps, ext-side code table).
Run: python tools/tests/test_matchflow.py   (plain python; free localhost port, no tools/t2r.db, no port 7001)."""
import os as _os_mt
_os_mt.environ.setdefault("T2R_MAX_TEAM", "0")   # the max-team filter has its own test (test_max_team.py)
import os, sys, socket, struct, tempfile, threading, time
import sys as _t2s, os as _t2o; _t2s.path.append(_t2o.path.normpath(_t2o.path.join(_t2o.path.dirname(_t2o.path.abspath(__file__)), ".."))); import t2rtmp  # noqa: E402,F401  (temp hygiene: tools/t2rtmp.py)

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.dirname(HERE)
sys.path.insert(0, TOOLS)

FAILS = []
def check(cond, what):
    print(("ok   " if cond else "FAIL ") + what)
    if not cond:
        FAILS.append(what)

def tok(name):
    return (name.encode().hex() + "0123456789abcdef" * 8)[:64]

A, B, C, D, E = tok("Alice"), tok("Bob"), tok("Carol"), tok("Dave"), tok("Eve")
s = socket.socket(); s.bind(("127.0.0.1", 0)); port = s.getsockname()[1]; s.close()
os.environ.update(T2R_HOST="127.0.0.1", T2R_PORT=str(port), T2R_MAP_VOTE="1")
import daemon  # noqa: E402
daemon.DB_PATH = os.path.join(tempfile.mkdtemp(), "daemon.db")
threading.Thread(target=daemon.tcp_server, daemon=True).start()
time.sleep(0.3)

def req(op, payload):
    c = socket.create_connection(("127.0.0.1", port), timeout=3)
    c.sendall(struct.pack("<H", len(payload) + 1) + bytes([op]) + payload)
    data = b""
    while len(data) < 2 or len(data) < 2 + struct.unpack_from("<H", data)[0]:
        b = c.recv(4096)
        if not b:
            break
        data += b
    c.close()
    ln = struct.unpack_from("<H", data)[0]
    return data[2], dict(kv.split("=", 1) for kv in data[3:2 + ln].decode().split())

# ------------------------------------------------------------------ steps
off = daemon.countdown_steps(5, 10, False, flow=False)
check(off[0] == (1, 0) and off[-2:] == [(2, 1), (2, 0)] and (2, 110) in off and (2, 102) in off and (2, 101) not in off
      and not any(130 <= n < 230 for _, n in off), "vote off: the old flow (5..1, CHOOSE LOADOUT 110..102, 1, 0)")
lo, bo, ld = daemon.flow_stage_secs(10)
check(lo == 5 and bo == 5 and ld == daemon.LOADING_SECS, "CHOOSE LOADOUT halved (5 s), the booster pick gets the other 5 s: %s" % ((lo, bo, ld),))
on = daemon.countdown_steps(5, 10, True)
ns = [n for _, n in on]
check(on[0] == (1, 0) and on[-2:] == [(2, 1), (2, 0)], "vote on: starts at MATCH FOUND, ends 1, 0")
i_v, i_l, i_b = ns.index(160 + daemon.VOTE_SECS), ns.index(100 + lo), ns.index(130 + bo)
check(ns[:5] == [0, 5, 4, 3, 2] and i_v < i_l < i_b, "vote on: pre-countdown -> vote -> loadout -> booster")
check(ns[i_l:i_l + lo] == list(range(100 + lo, 100, -1)) and ns[i_b:i_b + bo] == list(range(130 + bo, 130, -1)),
      "loadout 105..101 then booster 135..131 (no gap)")
check((ld > 0) == any(200 <= n < 230 for n in ns) and (ld == 0 or ns.index(200 + ld) > i_b), "LOADING stage only with T2R_LOADING_SECS")
check(sum(1 for n in ns if 100 <= n < 160 or 200 <= n < 230) == lo + bo + ld and lo + bo == 10, "the stages after the vote take the old 10 s window")
check(all(0 <= n < 256 for n in ns), "every step fits the 0x0c byte")
fl = daemon.countdown_steps(5, 10, False, flow=True)
check(not any(160 <= n < 200 for _, n in fl) and (2, 100 + lo) in fl and (2, 130 + bo) in fl, "T2R_MATCH_FLOW: the stages without the vote")
check(daemon.flow_extra_secs() == bo + ld + 1, "mf = booster + loading + the final 1 (%d)" % daemon.flow_extra_secs())
check(abs(daemon.countdown_seconds(5, 10) - (2 + len(on))) < 1e-9, "countdown_seconds = 2 s pause + one second per step (%d)" % len(on))
check(daemon.MM.countdown_over(A) is False, "countdown_over: no match = False")

# ------------------------------------------------------------------ vote
check(daemon.map_vote_on(), "T2R_MAP_VOTE=1 switches it on")
daemon.MM.matches["m1"] = [A, B, C]
opts = daemon.vote_start([A, B, C])
check(len(opts) == 3 and len(set(opts)) == 3 and all(o in daemon.map_pool() for o in opts), "three distinct pool maps: %s" % opts)
check(daemon.MATCH_MAP[frozenset([A, B, C])] == opts[0], "placeholder map = first option")
op, st = req(0xEA, A.encode())
check(op == 0xEB and st["st"] == "1" and st["n"] == "3" and st["m0"] == str(opts[0]) and st["w"] == "-1" and st["my"] == "-1"
      and st["pc"] == "3", "0xEA state: " + str(st))
op, st = req(0xEC, A.encode() + bytes([2]))
check(st["v2"] == "1" and st["my"] == "2" and st["pv0"] == "1" and st["pv1"] == "0", "0xEC vote counted, shown to the voter")
op, st = req(0xEC, B.encode() + bytes([2]))
op, st = req(0xEC, C.encode() + bytes([1]))
check(st["v2"] == "2" and st["v1"] == "1" and st["v0"] == "0", "tally 0/1/2")
op, st = req(0xEC, C.encode() + bytes([9]))
check(st["v1"] == "1", "bad option ignored")
op, st = req(0xEC, C.encode() + bytes([0]))
check(st["v0"] == "1" and st["v1"] == "0", "a vote can be changed")
req(0xEC, C.encode() + bytes([2]))
check(daemon.vote_close([A, B, C]) == opts[2] and daemon.MATCH_MAP[frozenset([A, B, C])] == opts[2], "majority wins")
op, st = req(0xEA, B.encode())
check(st["st"] == "2" and st["w"] == str(opts[2]), "state after close: decided, winner")
req(0xEC, A.encode() + bytes([0]))
op, st = req(0xEA, A.encode())
check(st["v0"] == "0" and st["my"] == "2", "no votes after the close")
check(daemon.vote_close([A, B, C]) == opts[2], "closing twice keeps the winner")

# tie / no votes: random among the leaders, never an outsider
daemon.MM.matches["m2"] = [D, E]
daemon.vote_start([D, E])
daemon.vote_cast(D, 0); daemon.vote_cast(E, 1)
seen = set()
for _ in range(40):
    v = daemon.VOTES[frozenset([D, E])]; v["winner"] = -1
    seen.add(daemon.vote_close([D, E]))
o2 = daemon.VOTES[frozenset([D, E])]["opts"]
check(seen == {o2[0], o2[1]}, "tie 1:1 -> random between the two leaders")
daemon.VOTES[frozenset([D, E])]["votes"].clear()
seen = set()
for _ in range(80):
    daemon.VOTES[frozenset([D, E])]["winner"] = -1
    seen.add(daemon.vote_close([D, E]))
check(seen == set(o2), "no votes -> random of the options")

# no match / no vote
op, st = req(0xEA, tok("Nobody").encode())
check(st == {"st": "0"}, "player outside a match: st=0")
check(daemon.vote_op(0xEA, b"zz" * 32) is None and daemon.vote_op(0xEA, b"ab") is None, "bad token / short payload refused")

# few maps in the pool
os.environ["T2R_MAP_POOL"] = "to1-forest,to1-school"
check(len(daemon.vote_options()) == 2, "pool of 2 -> 2 options")
os.environ.pop("T2R_MAP_POOL")

# ------------------------------------------------------------------ ext / widget texts agree
sys.path.insert(0, os.path.join(TOOLS, "features"))
import matchflow_widgets as mw  # noqa: E402
ext = open(os.path.join(TOOLS, "ext", "t2r-ext.c"), encoding="utf-8").read()
check(all('"%s"' % t in ext for _, t in mw.TIPS) and all('"%s"' % c in ext for c, _ in mw.TIPS) and len(mw.TIPS) == 16,
      "the 16 loading tips are the same in the ext and the widget script")
check(all('"%s"' % n in ext and '"%s"' % d in ext for n, d in mw.BOOSTER_LIST), "boosters: names and texts in the ext")
check(all('{"%s", "%s"}' % (nm, img) in ext for nm, img, _ in daemon.MAPS), "ext map table = daemon MAPS")
check("t2r-no-matchflow.txt" in ext and "code >= 200 ? 3 : code >= 160 ? 1 : code >= 130 ? 2 : 0" in ext,
      "ext: off switch and the same stage codes as countdown_steps (160 vote / 130 booster / 200 loading)")

print("\n%d failure(s)" % len(FAILS))
sys.exit(1 if FAILS else 0)
