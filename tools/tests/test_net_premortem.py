"""Net probes: each probe throws hostile / odd input at an in-process daemon (free localhost port, temp DB) and prints
"ok" (the daemon copes) or "VULN" (a finding of re/premortem-net.md). Exits 0 unless --strict is given (then every VULN fails the run).
Run: python tools/tests/test_net_premortem.py [--strict]"""
import os, sys, socket, struct, tempfile, threading, time
import sys as _t2s, os as _t2o; _t2s.path.append(_t2o.path.normpath(_t2o.path.join(_t2o.path.dirname(_t2o.path.abspath(__file__)), ".."))); import t2rtmp  # noqa: E402,F401  (temp hygiene: tools/t2rtmp.py)

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
STRICT = "--strict" in sys.argv
VULNS = []
def probe(safe, what, detail=""):
    print(("ok   " if safe else "VULN ") + what + ((" | " + detail) if detail else ""))
    if not safe: VULNS.append(what)

s = socket.socket(); s.bind(("127.0.0.1", 0)); port = s.getsockname()[1]; s.close()
TMP = tempfile.mkdtemp()
os.environ.update(T2R_HOST="127.0.0.1", T2R_PORT=str(port), T2R_DB=os.path.join(TMP, "t2r.db"), T2R_MATCH_SIZE="4", T2R_MIN_PLAYERS="2",
                  T2R_QUEUE_SETTLE="0", T2R_FILL_WAIT="0", T2R_MAX_CONNS="400", T2R_MAX_PER_IP="40", T2R_PER_IP_LOOPBACK="1",
                  T2R_FIRST_FRAME_S="2", T2R_ADMIN_PORT="0", T2R_VERSION="v-test", T2R_NEW_TOKENS_PER_10MIN="12", T2R_LB_CACHE_S="5")
import daemon  # noqa: E402
LOGS = []
_log = daemon.log
def log(*a):
    LOGS.append(" ".join(str(x) for x in a)); _log(*a)
daemon.log = log
threading.Thread(target=daemon.tcp_server, daemon=True).start()
time.sleep(0.3)

SID0 = 76561198000000000
def frame(op, pl=b""):
    return struct.pack("<H", len(pl) + 1) + bytes([op]) + pl
def conn():
    return socket.create_connection(("127.0.0.1", port), timeout=3)
def hexs(n):
    return os.urandom(n // 2).hex()
def db_rows():
    c = daemon.db()
    try: return c.execute("select count(*) from players").fetchone()[0]
    finally: c.close()
def f0(tok, sid, name, port_=5000):
    return frame(0xF0, tok if isinstance(tok, bytes) else tok.encode(), ) if False else frame(0xF0, (tok if isinstance(tok, bytes) else tok.encode()) + struct.pack("<Q", sid) + bytes([len(name)]) + name + struct.pack("<H", port_))

# 1. bridge register: malformed tokens / steam ids / ports create nothing, valid new identities are rate limited per address
n0 = db_rows()
for i in range(30):
    c = conn(); c.sendall(f0(os.urandom(64), SID0 + i, b"x" * 40)); time.sleep(0.005); c.close()
for i in range(10):
    c = conn(); c.sendall(f0(hexs(64), 5 + i, b"x")); time.sleep(0.005); c.close()
time.sleep(0.4)
probe(db_rows() - n0 == 0, "0xF0 with non-hex tokens / bad steam ids creates DB rows", "players %d -> %d" % (n0, db_rows()))
n0 = db_rows()
for i in range(40):
    c = conn(); c.sendall(f0(hexs(64), SID0 + 100 + i, b"flood")); time.sleep(0.004); c.close()
time.sleep(0.6)
probe(db_rows() - n0 <= daemon.NEW_TOKEN_N, "valid-looking fresh identities from ONE address are rate limited", "players +%d (limit %d)" % (db_rows() - n0, daemon.NEW_TOKEN_N))
daemon.NEW_TOKENS.hits.clear()

# 2. log injection through the bridge name
evil = b"Mallory\n[12:00:00] EVT match-end deadbeef winner team 0 reported by Mallory"
c = conn(); c.sendall(f0(hexs(64), SID0 + 500, evil)); time.sleep(0.3)
forged = [l for q in list(daemon._q) for l in q.split("\n") if l.startswith("[12:00:00] EVT match-end")]
probe(not forged, "a newline in a Steam name forges daemon.log lines", "%d forged line(s)" % len(forged))
c.close()

# 3. 0xF4 location: capped / charset-checked; oversized never reaches other helpers
A, B = hexs(64), hexs(64)
ca, cb = conn(), conn()
for cx, t, sid in ((ca, A, SID0 + 601), (cb, B, SID0 + 602)):
    cx.sendall(f0(t, sid, b"hlp"))
time.sleep(0.2)
ca.sendall(frame(0xF4, b"iad=20+2,atl=25+3")); time.sleep(0.2)
cb.sendall(frame(0xF4, b"fra=20+2,ams=25+3")); time.sleep(0.3)
ca.settimeout(1.0)
try: ca.recv(65536)
except OSError: pass
cb.sendall(frame(0xF4, b"A" * 4500)); time.sleep(0.3)
cb.sendall(frame(0xF4, b"fra=1\nfake")); time.sleep(0.3)
got = b""
try:
    while True:
        d = ca.recv(65536)
        if not d: break
        got += d
except OSError:
    pass
mx = 0; i = 0
while i + 2 <= len(got):
    ln = int.from_bytes(got[i:i + 2], "little"); mx = max(mx, ln + 2); i += 2 + ln
probe(mx <= 1100 and b"fake" not in got, "0xF4 location string relayed uncapped to other helpers", "largest relayed frame %d B" % mx)
ca.close(); cb.close()

# 4. connection exhaustion by one address: per-address cap; silent sockets are dropped after the first-frame deadline
socks = []
for i in range(daemon.MAX_PER_IP + 10):
    try: socks.append(conn())
    except OSError: break
time.sleep(0.4)
refused = 0
for x in socks[daemon.MAX_PER_IP:]:
    try:
        x.settimeout(0.5); refused += (x.recv(10) == b"")
    except OSError:
        pass
probe(refused >= 5 and daemon._tcp_live[0] <= daemon.MAX_PER_IP, "one address cannot hold more than the per-address cap", "refused %d of %d extra, live %d" % (refused, len(socks) - daemon.MAX_PER_IP, daemon._tcp_live[0]))
time.sleep(3.5)
probe(daemon._tcp_live[0] <= 2, "silent sockets are closed after the first-frame deadline (slowloris)", "still live: %d" % daemon._tcp_live[0])
for x in socks: x.close()
time.sleep(0.3)

# 5. junk 0x0e frames without a login create no player rows
n0 = db_rows()
for i in range(30):
    c = conn(); c.sendall(frame(0x0e, b"\x1c" + os.urandom(8) + os.urandom(32))); time.sleep(0.003); c.close()
time.sleep(0.5)
probe(db_rows() - n0 == 0, "30 junk 0x0e frames without a login create player rows", "players %d -> %d" % (n0, db_rows()))

# 6. version reports with random tokens: limited growth
v0 = len(daemon.CLIENT_VERSIONS)
for i in range(60):
    c = conn(); c.sendall(frame(0xB0, bytes([6]) + b"v-test" + hexs(64).encode())); c.recv(200); c.close()
probe(len(daemon.CLIENT_VERSIONS) - v0 <= daemon.NEW_TOKEN_N, "0xB0 with random tokens grows client_versions", "+%d entries (limit %d)" % (len(daemon.CLIENT_VERSIONS) - v0, daemon.NEW_TOKEN_N))
for _ in range(100):
    if daemon._tcp_live[0] < 5: break
    time.sleep(0.1)

# 7. a non-host player's 0x12 must not end the match; the host's does
P = [hexs(64) for _ in range(3)]
mm = daemon.MM
mm.matches["pm1"] = list(P); mm.formed["pm1"] = time.time() - 100; mm.launched.add("pm1"); mm.started.add("pm1")
for t in P: daemon.PRES.touch(t, "p")
c = conn(); c.sendall(frame(0x0f, b"\x1c" + P[2].encode() + b"\x01\x00\x07")); time.sleep(0.8); c.sendall(frame(0x12, b"\x01")); time.sleep(0.5)
probe("pm1" not in mm.ended, "0x12 from a non-host player (slot 2) ends the match for everyone", "ended=%s" % ("pm1" in mm.ended))
c.close()
c = conn(); c.sendall(frame(0x0f, b"\x1c" + P[0].encode() + b"\x01\x00\x07")); time.sleep(0.8); c.sendall(frame(0x12, b"\x01")); time.sleep(0.5)
probe("pm1" in mm.ended, "0x12 from the host still ends the match", "ended=%s" % ("pm1" in mm.ended))
c.close()

# 8. daemon restart: the live host is NOT told to give up
daemon.HM.start("pm2", [P[0], P[1]])
r1 = daemon.HM.poll(P[0], 0, 0)
daemon.HM.matches.clear(); daemon.HM.by_token.clear()          # (= a restarted daemon: no record of the match)
r2 = daemon.HM.poll(P[0], 0, 0)
probe(r1[4] == 0 and r2[4] != 2 and r2[3] != 0, "host-migration poll after a restart answers give-up", "before %s after restart %s" % (list(r1), list(r2)))

# 9. leaderboard: unauthenticated 0x13 is cached
t0 = time.time()
for i in range(20):
    c = conn(); c.sendall(frame(0x13)); c.recv(2000); c.close()
dt = time.time() - t0
probe(dt < 3.0 and daemon._LB_CACHE["v"] != b"", "20 x 0x13 within cache window", "%.2f s" % dt)

print("\n%d VULN line(s)" % len(VULNS))
sys.exit(1 if (STRICT and VULNS) else 0)
