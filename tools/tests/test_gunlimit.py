"""Offline tests for the per-team gun limit (tools/gunlimit.py + daemon op 0xDE + tools/ext/gunlimit.c table).
Run: python tools/tests/test_gunlimit.py   (plain python; temp DB, free localhost port)."""
import os, re, socket, struct, sys, tempfile, threading, time
import sys as _t2s, os as _t2o; _t2s.path.append(_t2o.path.normpath(_t2o.path.join(_t2o.path.dirname(_t2o.path.abspath(__file__)), ".."))); import t2rtmp  # noqa: E402,F401  (temp hygiene: tools/t2rtmp.py)

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.dirname(HERE)
sys.path.insert(0, TOOLS)
import gunlimit as gl  # noqa: E402

FAILS = []
def check(cond, what):
    print(("ok   " if cond else "FAIL ") + what)
    if not cond:
        FAILS.append(what)

def tok(n): return (n.encode().hex() + "0123456789abcdef" * 8)[:64]
A, B, C, D, E, F = (tok(x) for x in "ABCDEF")
class Clock:
    t = 1000.0
    def __call__(self): return self.t
clk = Clock()
def kv(t): return dict(x.split("=", 1) for x in t.split())

# ------------------------------------------------------------------ pure logic
g = gl.GunLimits(now=clk)
act = {A, B, C, D}
check(g.claim("m", 0, A, 1, act)[0] == 1, "first teammate gets the tac shotgun")
gr, dn, full, held = g.claim("m", 0, C, 1, act)
check(gr == 0 and dn == 1 and held == 0, "second teammate denied")
check(g.claim("m", 0, A, 1, act)[0] == 1, "holder re-claims: keeps it (idempotent)")
check(g.claim("m", 0, C, 0, act)[2] == 1, "a non-holder sees it as full")
check(g.claim("m", 0, A, 1, act)[2] == 0, "the holder does not see it as full for itself")
check(g.claim("m", 1, B, 1, act)[0] == 1, "other team unaffected")
check(g.claim("m", 1, D, 1, act)[1] == 1, "other team has its own limit of 1")
g.claim("m", 0, A, 0, act)
check(g.claim("m", 0, C, 1, act)[0] == 1, "holder switches loadout -> teammate can take it")
check(g.claim("m", 0, A, 1, act)[1] == 1, "...and the old holder is now the one denied")
check(g.claim("m", 0, C, 1, act - {C})[0] == 1, "a leaver still listed in the call re-claims fine (claim itself is not pruned)")
# a player leaving frees the slot (pruned against the active set on the next request)
g2 = gl.GunLimits(now=clk)
g2.claim("m", 0, A, 1, {A, C})
check(g2.claim("m", 0, C, 1, {A, C})[1] == 1, "held while the holder is active")
check(g2.claim("m", 0, C, 1, {C})[0] == 1, "holder left the match -> slot freed")
# stale claims expire
g3 = gl.GunLimits(now=clk, ttl=10)
g3.claim("m", 0, A, 1, {A, C})
clk.t += 11
check(g3.claim("m", 0, C, 1, {A, C})[0] == 1, "claim not refreshed for ttl s -> freed")
g3.end("m"); check("m" not in g3.held, "match end drops the books")
g3.claim("m2", 0, A, 1); g3.release(A); check(g3.claim("m2", 0, C, 1)[0] == 1, "release() frees")
# max > 1 table row
g4 = gl.GunLimits(limits=((("x",), 2, "X GUN"), (("y",), 1, "Y GUN")), now=clk)
r = [g4.claim("m", 0, t, 3)[0] for t in (A, B, C)]
check(r == [3, 1, 0], "max 2 for gun X, 1 for gun Y: A gets both, B gets X, C none")
# threads: 8 simultaneous claimers, exactly one winner
g5 = gl.GunLimits(now=clk); res = []
def w(i):
    res.append(g5.claim("m", 0, tok("p%d" % i), 1)[0])
ts = [threading.Thread(target=w, args=(i,)) for i in range(8)]
[t.start() for t in ts]; [t.join() for t in ts]
check(sum(res) == 1, "8 simultaneous claims -> exactly one granted")
check(g.parse_request(b"zz") is None and g.parse_request(A.encode() + b"\x01\x00") == (A, 1), "request parse")

# ------------------------------------------------------------------ pre-match: ranked + settled
def pre(g, tk, slot, mask=1, act=None, w=True):
    return g.claim("pm", 0, tk, mask, act or {A, B, C, D}, pre=True, slot=slot, with_pend=w)
gp = gl.GunLimits(now=clk)
r = pre(gp, C, 2)
check(r[4] == 1 and r[0] == 0 and r[1] == 0, "pre-match: a fresh claim is pending (not decided inside the settle window)")
clk.t += 0.4
r = pre(gp, A, 0)
check(r[4] == 1, "pre-match: second claim pending too")
clk.t += gl.SETTLE
r = pre(gp, C, 2)
check(r[0] == 1 and r[1] == 0, "pre-match: earliest claim (C) is granted once settled, although A has the lower slot")
r = pre(gp, A, 0)
check(r[0] == 0 and r[1] == 1, "pre-match: the later claim (A) is denied")
# a tie inside one bucket: lowest slot wins whatever the arrival order
gt = gl.GunLimits(now=clk); clk.t = 5000.0
pre(gt, C, 2); clk.t += 0.05; pre(gt, A, 0); clk.t += gl.SETTLE + 0.05
ra, rc = pre(gt, A, 0), pre(gt, C, 2)
check(ra[0] == 1 and rc[1] == 1, "pre-match: claims in the same bucket tie -> lowest slot wins")
# the denied player switches class (claims 0) and the holder keeps it
rd = pre(gt, C, 2, 0)
check(rd[0] == 0 and rd[1] == 0 and rd[2] == 1, "pre-match: denied player switched (claim 0): sees it full")
check(pre(gt, A, 0)[0] == 1, "pre-match: holder keeps the gun")
# the other team is ranked separately
check(gt.claim("pm", 1, B, 1, {A, B, C, D}, pre=True, slot=1, with_pend=True)[4] == 1, "pre-match: other team has its own ranking (pending first)")
# a holder leaving frees it for the next ranked wanter
gl2 = gl.GunLimits(now=clk); clk.t = 6000.0
pre(gl2, A, 0); clk.t += 0.3; pre(gl2, C, 2); clk.t += gl.SETTLE + 0.1
check(pre(gl2, A, 0)[0] == 1 and pre(gl2, C, 2)[1] == 1, "pre-match: A granted, C denied")
check(pre(gl2, C, 2, 1, {C})[0] == 1, "pre-match: A left (not active) -> C granted on its next claim")
# after the game start the old immediate rule applies
check(gl2.claim("pm", 0, B, 1, {A, B, C, D}, pre=False)[1] in (0, 1), "post-start claims are immediate (no pend)")
assert gl.GunLimits.text(1, 0, 0, 0, 0, 0, 1).endswith("pend=1")

# ext table == daemon table (bit order)
src = open(os.path.join(TOOLS, "ext", "gunlimit.c"), encoding="utf-8").read()
m = re.search(r"GL_TABLE\[\]\s*=\s*\{(.*?)\n\};", src, re.S)
rows = re.findall(r'\{\{([^}]*)\},\s*(\d+),\s*"([^"]+)"\}', m.group(1))
ext = [([x.strip().strip('"') for x in r[0].split(",") if x.strip()], int(r[1]), r[2]) for r in rows]
check(ext == [(list(i), mx, n) for i, mx, n in gl.LIMITS], "ext/gunlimit.c table == tools/gunlimit.py LIMITS")

# ------------------------------------------------------------------ the daemon over TCP
s = socket.socket(); s.bind(("127.0.0.1", 0)); port = s.getsockname()[1]; s.close()
os.environ.update(T2R_HOST="127.0.0.1", T2R_PORT=str(port), T2R_MATCH_SIZE="4", T2R_MIN_PLAYERS="4",
                  T2R_QUEUE_SETTLE="0", T2R_FILL_WAIT="0")
import daemon  # noqa: E402
daemon.DB_PATH = os.path.join(tempfile.mkdtemp(), "daemon.db")
threading.Thread(target=daemon.tcp_server, daemon=True).start()
time.sleep(0.3)
def req(token, mask):
    pl = token.encode() + struct.pack("<H", mask)
    c = socket.create_connection(("127.0.0.1", port), timeout=3)
    c.sendall(struct.pack("<H", len(pl) + 1) + bytes([0xDE]) + pl)
    data = b""
    while len(data) < 2 or len(data) < 2 + struct.unpack_from("<H", data)[0]:
        b = c.recv(4096)
        if not b: break
        data += b
    c.close()
    ln = struct.unpack_from("<H", data)[0]
    return data[2], kv(data[3:2 + ln].decode())
op, r = req(A, 1)
check(op == 0xDF and r["on"] == "0", "daemon: no match -> on=0")
now = time.time()
for t in (A, B, C, D):
    daemon.PRES.touch(t, "x"); daemon.MM.queue[t] = now; daemon.MM.seen[t] = now; daemon.MM.settle[t] = 0
mid, players = daemon.MM.try_form()
check(bool(mid) and len(players) == 4, "daemon: 4-player match formed")
team = {t: daemon.roster_team(i) for i, t in enumerate(players)}
mates = [t for t in players if team[t] == team[players[0]]]
others = [t for t in players if team[t] != team[players[0]]]
p1, p2 = mates; o1 = others[0]
# pre-match over the wire: the game start has not gone out (mid not in MM.started)
op, r = req(p1, 1)
check(r["on"] == "1" and r["pend"] == "1" and r["grant"] == "0", "daemon pre-match: first claim pending")
time.sleep(0.05)
op, r = req(p2, 1)
check(r["pend"] == "1", "daemon pre-match: second claim pending")
time.sleep(gl.SETTLE + 0.1)
op, r = req(p1, 1)
check(r["grant"] == "1" and r["deny"] == "0" and r["pend"] == "0", "daemon pre-match: earliest claim (p1) granted")
op, r = req(p2, 1)
check(r["grant"] == "0" and r["deny"] == "1", "daemon pre-match: p2 denied (switched before the first spawn)")
op, r = req(p2, 0)
check(r["full"] == "1", "daemon pre-match: p2 sees TOO MANY after switching")
op, r = req(p1, 0)
daemon.GL.release(p2)
daemon.MM.started.add(mid)                       # game start sent: the live rules from here
op, r = req(p1, 1)
check(r["on"] == "1" and r["grant"] == "1" and r["deny"] == "0", "daemon: teammate 1 granted")
op, r = req(p2, 1)
check(r["grant"] == "0" and r["deny"] == "1" and r["full"] == "1", "daemon: teammate 2 denied, shown full")
op, r = req(o1, 1)
check(r["grant"] == "1", "daemon: other team unaffected")
op, r = req(p2, 0)
check(r["full"] == "1" and r["mask"] == "0", "daemon: teammate 2 polling sees it taken")
op, r = req(p1, 0)
op, r = req(p2, 1)
check(r["grant"] == "1", "daemon: holder released by a loadout switch -> teammate gets it")
daemon.MM.depart(p2, voluntary=True)
op, r = req(p1, 1)
check(r["grant"] == "1", "daemon: holder left (departed) -> the other teammate gets it at once")
daemon.leave_running_match(p1, "left")
op, r = req(p1, 1)
check(r["on"] == "0", "daemon: a player that left the match gets on=0")

print("\n%d failure(s)" % len(FAILS))
os._exit(1 if FAILS else 0)
