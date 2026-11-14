"""Tests for the daemon's per-connection / accept-loop / clock robustness (soak audit): slowloris after the first frame, read flood,
thread-start failure, admin listener timeout, port re-bind, the steady clock, relay slot cap, host-repick record cleanup.
Run: python tools/tests/test_daemon_conn_limits.py   (free localhost ports, temp DB)."""
import os, sys, socket, struct, subprocess, tempfile, threading, time
import sys as _t2s, os as _t2o; _t2s.path.append(_t2o.path.normpath(_t2o.path.join(_t2o.path.dirname(_t2o.path.abspath(__file__)), ".."))); import t2rtmp  # noqa: E402,F401

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.dirname(HERE)
sys.path.insert(0, TOOLS)
FAILS = []
def check(cond, what):
    print(("ok   " if cond else "FAIL ") + what)
    if not cond: FAILS.append(what)

def free_port():
    s = socket.socket(); s.bind(("127.0.0.1", 0)); p = s.getsockname()[1]; s.close(); return p
port, aport = free_port(), free_port()
tmp = tempfile.mkdtemp()
os.environ.update(T2R_HOST="127.0.0.1", T2R_PORT=str(port), T2R_ADMIN_PORT=str(aport), T2R_STATUS_FILE="0", T2R_ADMIN_TIMEOUT_S="1",
                  T2R_PARTIAL_FRAME_S="1.0", T2R_FLOOD_MAX_RECVS="60", T2R_BIND_RETRY_S="2", T2R_DB=os.path.join(tmp, "t2r.db"))
import daemon  # noqa: E402
daemon.LOG_PATH = os.path.join(tmp, "daemon.log")
threading.Thread(target=daemon.tcp_server, daemon=True).start()
time.sleep(0.4)

def msg(op, pl=b""):
    return struct.pack("<H", len(pl) + 1) + bytes([op]) + pl

def closed_within(c, secs):
    """True when the server closed the socket (recv returns b'' / reset) within secs."""
    c.settimeout(0.2)
    end = time.time() + secs
    while time.time() < end:
        try:
            d = c.recv(4096)
            if d == b"":
                return True
        except socket.timeout:
            continue
        except OSError:
            return True
    return False

# ------------------------------------------------------------------ slowloris after the first frame
c = socket.create_connection(("127.0.0.1", port), timeout=3)
c.sendall(msg(0x15))                                     # a complete frame: the connection is 'live' (120 s idle limit from now on)
c.sendall(struct.pack("<H", 50) + b"\x05")               # half a frame ...
t0 = time.time(); shut = False
while time.time() - t0 < 6 and not shut:
    time.sleep(0.4)
    try: c.sendall(b"\x01")                             # ... and one byte now and then
    except OSError: shut = True
    shut = shut or closed_within(c, 0.01)
check(shut and time.time() - t0 < 5, "a dribbling client is cut after PARTIAL_FRAME_S (%.1f s)" % (time.time() - t0))
c.close()
# a polite client sending a big frame in two segments is not cut
c = socket.create_connection(("127.0.0.1", port), timeout=3)
c.sendall(struct.pack("<H", 40) + b"\x05")
time.sleep(0.3)
c.sendall(b"x" * 39)
time.sleep(0.2)
c.sendall(msg(0x15))
check(not closed_within(c, 1.5), "a frame completed in time keeps the connection")
c.close()
# a frame every 0.5 s forever is fine (the partial timer restarts with progress)
c = socket.create_connection(("127.0.0.1", port), timeout=3)
alive = True
for i in range(6):
    c.sendall(msg(0x15)); time.sleep(0.5)
    if closed_within(c, 0.01): alive = False
check(alive, "regular polls are never mistaken for slowloris")
c.close()

# ------------------------------------------------------------------ read flood
c = socket.create_connection(("127.0.0.1", port), timeout=3)
c.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
shut = False
for i in range(400):
    try:
        c.sendall(msg(0x07)); time.sleep(0.004)
    except OSError:
        shut = True; break
shut = shut or closed_within(c, 1.0)
check(shut, "a connection that sends 400 tiny frames in 2 s is closed after FLOOD_MAX_RECVS reads")
c.close()
c = socket.create_connection(("127.0.0.1", port), timeout=3)
for i in range(10):
    c.sendall(msg(0x07)); time.sleep(0.05)
check(not closed_within(c, 0.5), "10 frames in 0.5 s are fine")
c.close()

# ------------------------------------------------------------------ nothing leaks after a storm of connections
time.sleep(1.5)
base_threads = threading.active_count()
socks = []
for i in range(150):
    try:
        s = socket.create_connection(("127.0.0.1", port), timeout=3)
        if i % 3 == 0: s.sendall(msg(0x15))
        if i % 3 == 1: s.sendall(b"\xff\xff" + os.urandom(100))
        socks.append(s)
    except OSError:
        pass
mid_threads = threading.active_count()
for s in socks:
    try: s.close()
    except OSError: pass
time.sleep(2.0)
check(daemon._tcp_live[0] == 0 and not daemon._tcp_per_ip, "all connection slots released (%d live, per-ip %s)" % (daemon._tcp_live[0], dict(daemon._tcp_per_ip)))
check(threading.active_count() <= base_threads + 3, "handler threads exit: %d -> %d (mid %d)" % (base_threads, threading.active_count(), mid_threads))

# ------------------------------------------------------------------ thread start failure keeps the accept loop and the counters
real_start = threading.Thread.start
fail_left = [3]
def flaky_start(self):
    if getattr(self._target, "__name__", "") == "run" and fail_left[0] > 0:
        fail_left[0] -= 1
        raise RuntimeError("can't start new thread")
    return real_start(self)
threading.Thread.start = flaky_start
try:
    for i in range(3):
        try:
            s = socket.create_connection(("127.0.0.1", port), timeout=3); s.settimeout(1.0)
            try: s.recv(10)
            except (socket.timeout, OSError): pass
            s.close()
        except OSError:
            pass
    time.sleep(0.5)
finally:
    threading.Thread.start = real_start
check(daemon._tcp_live[0] == 0 and not daemon._tcp_per_ip, "a failed thread start releases its slot (live %d)" % daemon._tcp_live[0])
s = socket.create_connection(("127.0.0.1", port), timeout=3)
s.sendall(msg(0xB0, bytes([2, 0x30, 0x30])))
s.settimeout(2)
try:
    r = s.recv(4096)
except OSError:
    r = b""
check(r[2:3] == b"\xb1", "the accept loop still serves after the failures")
s.close()

# ------------------------------------------------------------------ admin listener: idle connection is closed
daemon.admin_start()
time.sleep(0.6)
a = socket.create_connection(("127.0.0.1", aport), timeout=3)
a.sendall(b"GET /sta")                                 # never finishes its request line
check(closed_within(a, 4.0), "an admin connection that stalls is closed (T2R_ADMIN_TIMEOUT_S)")
a.close()
import urllib.request
check(b'"ok": true' in urllib.request.urlopen("http://127.0.0.1:%d/status" % aport, timeout=3).read(), "admin /status still answers")

# ------------------------------------------------------------------ steady clock
orig = time.time
check(abs(daemon.time.time() - orig()) < 1.0, "daemon.time.time() tracks the wall clock at start")
time.time = lambda: orig() + 3600.0                     # an NTP step / manual change of +1 h
try:
    daemon.PRES.touch("clockjump", "x")
    d_jump = daemon.time.time()
    online = [p for p in daemon.PRES.online() if p["name"] == "x"]
finally:
    time.time = orig
check(abs(d_jump - orig()) < 1.0 and online, "a +1 h wall clock step does not move daemon.time (players stay online, timeouts do not fire)")
time.time = lambda: orig() - 7200.0
try:
    d_back = daemon.time.time()
finally:
    time.time = orig
check(abs(d_back - orig()) < 1.0, "a -2 h step neither")
time.time = lambda: orig() + 3600.0
try:
    check(abs(daemon.wall_time() - orig() - 3600.0) < 1.0 and abs(daemon.time.time() - orig()) < 1.0,
          "wall_time() (status file ts, admin /live) follows the REAL clock: the update server / admin site compare it with their own (pre-mortem 10-19)")
finally:
    time.time = orig
check(daemon.time.strftime("%H") and daemon.time.monotonic() > 0 and daemon.time.sleep, "daemon.time still behaves like the time module")
check(daemon.HM.now is daemon.time.time or getattr(daemon.HM.now, "__func__", None) is daemon._SteadyTime.time, "host migration / notices / perf use the steady clock too")

# ------------------------------------------------------------------ port re-bind
hold = socket.socket(); hold.setsockopt(socket.SOL_SOCKET, getattr(socket, "SO_EXCLUSIVEADDRUSE", socket.SO_REUSEADDR), 1)
bp = free_port(); hold.bind(("127.0.0.1", bp)); hold.listen(1)
old_port = daemon.PORT
daemon.PORT = bp
threading.Timer(0.8, hold.close).start()
ns = socket.socket(); t0 = time.time()
daemon.bind_exclusive(ns, "TCP")
check(0.5 < time.time() - t0 < 2.0, "bind_exclusive waits for a port the previous process still holds (%.1f s)" % (time.time() - t0))
ns.close(); daemon.PORT = old_port
# the FATAL exit 3 remains when the port stays taken: a second daemon on a taken port
hold2 = socket.socket(); hold2.setsockopt(socket.SOL_SOCKET, getattr(socket, "SO_EXCLUSIVEADDRUSE", socket.SO_REUSEADDR), 1)
p2 = free_port(); hold2.bind(("127.0.0.1", p2)); hold2.listen(1)
env = dict(os.environ, T2R_PORT=str(p2), T2R_ADMIN_PORT="0", T2R_BIND_RETRY_S="1", T2R_DB=os.path.join(tmp, "other.db"), T2R_LOG_PATH=os.path.join(tmp, "other.log"))
t0 = time.time()
r = subprocess.run([sys.executable, os.path.join(TOOLS, "daemon.py")], env=env, capture_output=True, text=True, timeout=30, cwd=tmp)
check(r.returncode == 3 and "already in use" in r.stdout and 0.8 < time.time() - t0 < 12, "a really taken port: FATAL exit code 3 after the retry window (rc %s, %.1f s)" % (r.returncode, time.time() - t0))
hold2.close()
# a daemon restarted right after a daemon that served connections binds at once (TIME_WAIT must not block it)
p3 = free_port()
env = dict(os.environ, T2R_PORT=p3 and str(p3), T2R_ADMIN_PORT="0", T2R_DB=os.path.join(tmp, "r.db"), T2R_LOG_PATH=os.path.join(tmp, "r.log"), T2R_STATUS_FILE="0")
def start_daemon():
    return subprocess.Popen([sys.executable, os.path.join(TOOLS, "daemon.py")], env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, cwd=tmp)
def wait_up(p, secs=15):
    end = time.time() + secs
    while time.time() < end and p.poll() is None:
        try:
            socket.create_connection(("127.0.0.1", p3), timeout=0.3).close(); return True
        except OSError:
            time.sleep(0.15)
    return False
d1 = start_daemon()
up1 = wait_up(d1)
for i in range(30):
    try:
        s = socket.create_connection(("127.0.0.1", p3), timeout=2); s.sendall(msg(0xB0, bytes([1, 0x31]))); s.settimeout(1); s.recv(100); s.close()
    except OSError:
        pass
d1.terminate(); d1.wait(10)
t0 = time.time()
d2 = start_daemon()
up2 = wait_up(d2)
check(up1 and up2 and time.time() - t0 < 8, "a daemon restarted straight after another one that served connections is up again in %.1f s" % (time.time() - t0))
d2.terminate(); d2.wait(10)

# ------------------------------------------------------------------ relay slot cap + host-repick records
sent = []
U = daemon.UdpRelay(lambda d, a: sent.append(a))
daemon.RELAY.clear(); daemon.RELAY_TS.clear()
for i in range(U.RELAY_MAX + 500):
    U.handle(b"\x00" + struct.pack("<I", i) + b"\x01", ("3.3.%d.%d" % (i // 250, i % 250), 4000), now=1000.0 + i * 0.001)
check(len(daemon.RELAY) <= U.RELAY_MAX and len(daemon.RELAY) == len(daemon.RELAY_TS), "junk HELLOs cannot grow the relay table past %d (%d)" % (U.RELAY_MAX, len(daemon.RELAY)))
U.handle(b"\x00" + struct.pack("<I", 0xFFFFFF) + b"\x00", ("4.4.4.4", 1), now=3000.0)
check((0xFFFFFF, 0) in daemon.RELAY and len(daemon.RELAY) < 10, "when the table is full the idle slots go first")
rs = daemon.RELAY_IDLE_S
daemon.RELAY_TS[(0xFFFFFF, 0)] = 3000.0 - rs - 5
U.last_prune = 0.0
U.handle(b"\x03\x00\x00\x00\x01", ("4.4.4.4", 1), now=3000.0 + 70)
check((0xFFFFFF, 0) not in daemon.RELAY, "an idle relay slot is pruned after RELAY_IDLE_S")

daemon.REPICK.recs["old-match"] = {"x": 1}; daemon.REPICK.last_text["old-match"] = "x"
daemon.REPICK.mode = 1
daemon.repick_tick()
check("old-match" not in daemon.REPICK.recs and "old-match" not in daemon.REPICK.last_text, "repick_tick forgets the records of matches that left host migration")

print("\n%d failure(s)" % len(FAILS) if FAILS else "\nall ok")
sys.exit(1 if FAILS else 0)
