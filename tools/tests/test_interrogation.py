"""Offline tests for the Interrogation game mode (tools/interrogation.py + the daemon's op 0xDC,
mode select at GAME-START, match end) and the lockbox table (tools/interrogation_lockboxes.json).
Run: python tools/tests/test_interrogation.py   (plain python; temp DB, free localhost port)."""
import json, os, random, socket, struct, sys, tempfile, threading, time
import sys as _t2s, os as _t2o; _t2s.path.append(_t2o.path.normpath(_t2o.path.join(_t2o.path.dirname(_t2o.path.abspath(__file__)), ".."))); import t2rtmp  # noqa: E402,F401  (temp hygiene: tools/t2rtmp.py)

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.dirname(HERE)
sys.path.insert(0, TOOLS)
import interrogation as itg  # noqa: E402

FAILS = []
def check(cond, what):
    print(("ok   " if cond else "FAIL ") + what)
    if not cond:
        FAILS.append(what)

def tok(name):
    return (name.encode().hex() + "0123456789abcdef" * 8)[:64]
A, B, C, D = tok("Alice"), tok("Bob"), tok("Carol"), tok("Dave")   # slots 0..3: teams 0 1 0 1

class Clock:
    def __init__(self): self.t = 1000.0
    def __call__(self): return self.t
    def adv(self, s): self.t += s

def kv(text):
    return dict(x.split("=", 1) for x in text.split())

def mk(**kw):
    clk = Clock()
    kw.setdefault("need", 5); kw.setdefault("kills_per_info", 4); kw.setdefault("locate_secs", 0.0)
    g = itg.Interrogation(mode=kw.pop("mode", "interrogation"), now=clk, log=lambda *a: None,
                          rng=random.Random(1), lockboxes={0: (3, 2)}, **kw)
    return g, clk

# ------------------------------------------------------------------ mode select
g, _ = mk(mode="supply-raid")
check(g.start("m1", [A, B]) == "supply-raid", "default mode: supply raid")
check(kv(g.event(A, 0))["on"] == "0", "supply raid match: reply on=0 (ext stays off)")
g, _ = mk(mode="rotate")
check([g.pick_mode() for _ in range(4)] == ["interrogation", "supply-raid"] * 2, "rotate alternates, interrogation first")
os.environ["T2R_MODE"] = "interrogation"
check(itg.Interrogation(log=lambda *a: None).pick_mode() == "interrogation", "T2R_MODE env selects interrogation")
os.environ.pop("T2R_MODE")
check(itg.Interrogation(log=lambda *a: None).pick_mode() == "supply-raid", "no T2R_MODE: supply raid")

# ------------------------------------------------------------------ interrogations reveal the lockbox
g, clk = mk()
check(g.start("m", [A, B, C, D], map_idx=0) == "interrogation", "interrogation match starts")
r = kv(g.event(A, 0))
check(r["on"] == "1" and r["team"] == "0" and kv(g.event(B, 0))["team"] == "1", "teams by slot (0,2 / 1,3)")
check(0 <= int(r["box0"]) < 3 and 0 <= int(r["box1"]) < 2, "lockbox index within the map's candidates")
check(r["rev0"] == "0" and r["rev1"] == "0", "nothing revealed at the start")
r = kv(g.event(A, 1, 1, bytes([2])))
check(r["i0"] == "0", "interrogating a teammate (slot 2) is refused")
for i in range(4):
    r = kv(g.event(A if i % 2 else C, 1, 10 + i, bytes([1 if i % 2 else 3])))
check(r["i0"] == "4" and r["rev0"] == "0", "4 interrogations: not revealed yet")
r = kv(g.event(C, 1, 12, bytes([3])))
check(r["i0"] == "4", "same seq resent: booked once")
r = kv(g.event(C, 1, 14, bytes([3])))
check(r["i0"] == "5" and r["rev0"] == "1" and r["rev1"] == "0", "5th interrogation reveals team 1's lockbox to team 0")

# ------------------------------------------------------------------ kills count too
for i in range(7):
    r = kv(g.event(A if i % 2 else C, 3, 100 + i, bytes([1])))   # team 0 players die 7 times
check(r["k1"] == "7" and r["p1"] == "1" and r["rev1"] == "0", "7 deaths of team 0 = 1 intel for team 1 (kpi 4)")

# ------------------------------------------------------------------ steal
r = kv(g.event(B, 2, 1, bytes([1])))
check(r["st1"] == "0", "stage refused for a team without intel")
r = kv(g.event(A, 2, 220, bytes([2])))
check(r["st0"] == "0", "skipping stage 1 is ignored")
r = kv(g.event(A, 2, 221, bytes([1])))
check(r["st0"] == "1" and r["win"] == "-1", "stage 1 done")
check(float(r["hold"]) == 18.0 and r["sp"] == "0", "hold at the start: 18 s per stage for one unlocker")
clk.adv(700)
check(float(kv(g.event(A, 0))["hold"]) == 18.0, "no speed step before 720 s")
clk.adv(30)
r = kv(g.event(A, 0))
check(r["sp"] == "1" and float(r["hold"]) == round(18 / 1.12, 2), "first Unlock speed increased! step at ~720 s")
clk.adv(90)
check(kv(g.event(A, 0))["sp"] == "2", "a step every 90 s")
clk.adv(5000)
check(kv(g.event(A, 0))["sp"] == "4" and float(kv(g.event(A, 0))["hold"]) == round(18 / 1.48, 2), "speed steps are capped")
g.event(C, 2, 230, bytes([2]))
r = kv(g.event(A, 2, 222, bytes([3])))
check(r["st0"] == "3" and r["win"] == "0", "stage 3: team 0 wins")
r = kv(g.event(B, 1, 205, bytes([0])))
check(r["i1"] == "0" and r["win"] == "0", "no events booked after the win")

# ------------------------------------------------------------------ the reveal comes 20 s after the intel is complete
g2, clk2 = mk(locate_secs=20.0)
g2.start("m2", [A, B, C, D], map_idx=0)
for i in range(5):
    r = kv(g2.event(A, 1, 300 + i, bytes([1])))
check(r["p0"] == "5" and r["rev0"] == "0", "intel complete: not located yet (Locating lockbox...)")
clk2.adv(19)
check(kv(g2.event(A, 0))["rev0"] == "0", "19 s later: still locating")
clk2.adv(2)
check(kv(g2.event(A, 0))["rev0"] == "1", "20 s after the intel: located")
r = kv(g2.event(A, 2, 400, bytes([1])))
check(r["st0"] == "1", "stage accepted once located")

# ------------------------------------------------------------------ end / keep / drop
g.end("m", 0)
clk.adv(10)
check(kv(g.event(D, 0))["ended"] == "1", "ended match still answers polls")
clk.adv(30)
check(kv(g.event(D, 0))["on"] == "0", "ended match forgotten after keep")
g, clk = mk()
g.start("x", [A, B])
g.end("x", 1)
check(kv(g.event(A, 0))["win"] == "1", "timer end: the host's winner is kept")
check(g.parse_request(b"zz") is None and g.parse_request(A.encode() + b"\x01\x05\x00\x01")[1:] == (1, 5, b"\x01"),
      "request parse")

# ------------------------------------------------------------------ lockbox table
tab = json.load(open(os.path.join(TOOLS, "interrogation_lockboxes.json"), encoding="utf-8"))
check(len(tab) >= 8 and all(len(e["teams"]) == 2 for e in tab), "lockbox table: every row has 2 teams")
check({7, 12, 17, 18, 19, 20, 21, 22, 23} <= {e["map"] for e in tab}, "lockbox rows for the shipped SP-section maps")
check(all(1 <= len(t) <= 6 for e in tab for t in e["teams"]), "every map/team has 1..6 candidates (LB_MAX)")
def d(a, b): return sum((x - y) ** 2 for x, y in zip(a, b)) ** 0.5
check(all(d(a["pos"], b["pos"]) > 8 for e in tab for a in e["teams"][0] for b in e["teams"][1]),
      "team lockboxes are > 8 m apart")
hdr = open(os.path.join(TOOLS, "ext", "lockboxes.h"), encoding="utf-8").read()
check("LOCKBOXES[LB_MAPS][2]" in hdr and hdr.count("},   //") == 24, "ext header matches the table")
tab2 = [e for e in tab if e["map"] == 2][0]
check(itg.load_lockboxes()[2] == (len(tab2["teams"][0]), len(tab2["teams"][1])), "daemon reads candidate counts")

# ------------------------------------------------------------------ the daemon: op 0xDC over TCP, GAME-START, 0x12
s = socket.socket(); s.bind(("127.0.0.1", 0)); port = s.getsockname()[1]; s.close()
os.environ.update(T2R_HOST="127.0.0.1", T2R_PORT=str(port), T2R_MODE="interrogation", T2R_MAP="to1-school",
                  T2R_INT_LOCATE_SECS="0", T2R_MATCH_SIZE="2", T2R_MIN_PLAYERS="2", T2R_QUEUE_SETTLE="0", T2R_FILL_WAIT="0")
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
        if not b: break
        data += b
    c.close()
    ln = struct.unpack_from("<H", data)[0]
    return data[2], kv(data[3:2 + ln].decode())

op, r = req(0xDC, A.encode() + b"\x00\x00\x00")
check(op == 0xDD and r["on"] == "0", "daemon: no match -> 0xDD on=0")
check(daemon.INT.mode_env == "interrogation", "daemon reads T2R_MODE")
# a running match as the matchmaker would have it, then GAME-START (both 0x09)
now = time.time()
for t in (A, B):
    daemon.PRES.touch(t, "x"); daemon.MM.queue[t] = now; daemon.MM.seen[t] = now; daemon.MM.settle[t] = 0
mid, players = daemon.MM.try_form()
check(bool(mid) and sorted(players) == sorted([A, B]), "daemon: match formed")
st = {"token": None, "name": "x", "session": False, "authed": True, "is_bridge": False}
class FakeConn:
    def sendall(self, b): pass
for t in players:
    st["token"] = t
    daemon.handle_batch(FakeConn(), ("127.0.0.1", 1), st, [(0x09, b"")])
op, r = req(0xDC, players[0].encode() + b"\x00\x00\x00")
check(r["on"] == "1" and r["map"] == "2", "daemon: GAME-START made it an Interrogation match on the map")
for i in range(5):
    op, r = req(0xDC, players[0].encode() + bytes([1]) + struct.pack("<H", i + 1) + b"\x01")
check(r["rev0"] == "1", "daemon: 5 interrogations over TCP reveal the lockbox")
for stg in (1, 2, 3):
    op, r = req(0xDC, players[0].encode() + bytes([2]) + struct.pack("<H", 10 + stg) + bytes([stg]))
check(r["win"] == "0", "daemon: lockbox stolen -> win=0 in the reply")
st["token"] = players[0]
daemon.handle_batch(FakeConn(), ("127.0.0.1", 1), st, [(0x12, b"\x00")])
op, r = req(0xDC, players[1].encode() + b"\x00\x00\x00")
check(r["ended"] == "1" and r["win"] == "0", "daemon: host 0x12 ends the interrogation record")

# ------------------------------------------------------------------ live unlock progress (safe marker rings)
g, clk = mk()
g.start("lh", [A, B, C, D], map_idx=0)
r = kv(g.event(A, 0))
check(r["h0"] == "0" and r["h1"] == "0", "no unlock in progress at the start (h0 / h1 = 0)")
r = kv(g.event(C, 0, 0, bytes([40])))
check(r["h0"] == "40" and r["h1"] == "0", "a poll with a hold percent shows as that team's live progress")
g.event(A, 0, 0, bytes([55]))
check(kv(g.event(B, 0))["h0"] == "55", "the highest fresh report of the team wins, the other team sees it too")
clk.adv(4.0)
check(kv(g.event(B, 0))["h0"] == "0", "a report older than 3 s is dropped")
g.event(C, 0, 0, bytes([70]))
r = kv(g.event(C, 0, 0, bytes([0])))
check(r["h0"] == "0", "a 0 report clears that client's hold")

# join in progress: a joiner in slot 4 (team 0) is booked for team 0 and its interrogation counts
g.start("jp", [A, B, C, D], map_idx=0)
E = tok("Erin")
g.roster("jp", [A, B, C, D, E])
check(g.matches["jp"]["team"][E] == 0 and g.by_token[E] == "jp", "a joiner gets its slot team and the match")
before = g.matches["jp"]["intel"][0]
g.event(E, 1, 1, bytes([1]))
check(g.matches["jp"]["intel"][0] == before + 1, "the joiner's interrogation of an enemy counts for its team")

print("\n%d failure(s)" % len(FAILS))
os._exit(1 if FAILS else 0)
