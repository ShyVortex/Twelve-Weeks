"""Listening-socket startup of the daemon (TCP + UDP relay + admin HTTP) and the update server: exclusive bind (no port stealing on
Windows), bounded retry, loud exit 3, quick restart after a hard kill. Real subprocesses on PRIVATE ports 7300-7399 only.
Run: python tools/tests/test_bind_restart.py"""
import os, sys, socket, subprocess, tempfile, time, signal
import sys as _t2s, os as _t2o; _t2s.path.append(_t2o.path.normpath(_t2o.path.join(_t2o.path.dirname(_t2o.path.abspath(__file__)), ".."))); import t2rtmp  # noqa: E402,F401

HERE = os.path.dirname(os.path.abspath(__file__)); TOOLS = os.path.dirname(HERE)
FAILS = []
def check(cond, what):
    print(("ok   " if cond else "FAIL ") + what)
    if not cond: FAILS.append(what)

TMP = tempfile.mkdtemp()
PROCS = []

def free(p):
    s = socket.socket()
    try: s.bind(("127.0.0.1", p)); return True
    except OSError: return False
    finally: s.close()

def spawn(args, env_extra, tag):
    env = dict(os.environ, **env_extra)
    out = open(os.path.join(TMP, "%s-%d.log" % (tag, len(PROCS))), "w+")
    flags = subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0
    p = subprocess.Popen([sys.executable, "-u"] + args, stdout=out, stderr=subprocess.STDOUT, env=env, cwd=TOOLS, creationflags=flags)
    p._out = out; PROCS.append(p); return p

def text(p):
    p._out.flush(); return open(p._out.name, errors="replace").read()

def daemon_env(extra=None):
    e = dict(T2R_HOST="127.0.0.1", T2R_PORT=str(PORT), T2R_ADMIN_PORT=str(ADMIN), T2R_DB=os.path.join(TMP, "d.db"), T2R_STATUS_FILE="0",
             T2R_LIVE_STATE="0", T2R_BIND_RETRY_S="30", T2R_LOG_PATH=os.path.join(TMP, "daemon.log"))   # never rotate tools/daemon.log (the A/B test daemon writes there)
    e.update(extra or {}); return e

def tcp_up(port, timeout=20, p=None):
    t0 = time.time()
    while time.time() - t0 < timeout:
        if p is not None and p.poll() is not None: return False
        try: socket.create_connection(("127.0.0.1", port), 0.5).close(); return True
        except OSError: time.sleep(0.1)
    return False

def hard_kill(p):
    p.kill(); p.wait(10)

def pick():
    """Three ports in 7300-7399 that are free for TCP and UDP right now (other processes may hold some)."""
    import random
    c = list(range(7300, 7400)); random.shuffle(c); got = []
    for q in c:
        u = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try: u.bind(("127.0.0.1", q)); ok = free(q)
        except OSError: ok = False
        finally: u.close()
        if ok: got.append(q)
        if len(got) == 3: return got
    raise SystemExit("no free private ports")
PORT, ADMIN, UPD = pick()

try:

    # --- daemon: kill -9 then immediate restart
    d1 = spawn(["daemon.py"], daemon_env(), "d")
    check(tcp_up(PORT, p=d1), "daemon starts on private port")
    hard_kill(d1)
    t0 = time.time(); d2 = spawn(["daemon.py"], daemon_env(), "d")
    up = tcp_up(PORT, p=d2)
    check(up, "daemon restarted right after kill -9 comes up (%.1fs)" % (time.time() - t0))
    check(d2.poll() is None, "restarted daemon is alive (not exit 3)")
    # --- double start must fail loudly, must not steal
    d3 = spawn(["daemon.py"], daemon_env(dict(T2R_BIND_RETRY_S="2")), "d")
    try: rc = d3.wait(30)
    except subprocess.TimeoutExpired: rc = None
    check(rc == 3, "second instance on the same port exits 3 (rc=%s)" % rc)
    check("FATAL" in text(d3) and "already in use" in text(d3), "second instance logs FATAL already in use")
    check(d2.poll() is None and tcp_up(PORT), "first instance still alive and serving after the double start")
    # the second one must not have shared UDP or admin either
    u = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try: u.bind(("127.0.0.1", PORT)); ubound = True
    except OSError: ubound = False
    finally: u.close()
    check(not ubound, "UDP relay port is exclusively held (a plain bind fails)")
    # SO_REUSEADDR on Windows must not be able to steal TCP either
    s = socket.socket(); s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try: s.bind(("127.0.0.1", PORT)); stolen = True
    except OSError: stolen = False
    finally: s.close()
    check(not stolen, "SO_REUSEADDR bind cannot steal the TCP port")
    s = socket.socket(); s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try: s.bind(("127.0.0.1", ADMIN)); stolen = True
    except OSError: stolen = False
    finally: s.close()
    check(not stolen, "SO_REUSEADDR bind cannot steal the admin port")

    # --- retry: new instance started while the old one is still up, old one dies 3 s later -> new one takes over
    d4 = spawn(["daemon.py"], daemon_env(), "d")
    time.sleep(3.0)
    check(d4.poll() is None, "waiting instance is retrying (still alive) while the port is busy")
    hard_kill(d2)
    ok = False; t0 = time.time()
    while time.time() - t0 < 25:
        if d4.poll() is not None: break
        if tcp_up(PORT, 1): ok = True; break
    check(ok and d4.poll() is None, "waiting instance takes over once the port is released")
    check("busy" in text(d4) and "ok after" in text(d4), "retry and success are logged")
    hard_kill(d4)

    # --- graceful stop (CTRL_BREAK) then restart
    d5 = spawn(["daemon.py"], daemon_env(), "d")
    check(tcp_up(PORT, p=d5), "daemon up for graceful test")
    if os.name == "nt": d5.send_signal(signal.CTRL_BREAK_EVENT)
    else: d5.terminate()
    try: d5.wait(15)
    except subprocess.TimeoutExpired: hard_kill(d5)
    d6 = spawn(["daemon.py"], daemon_env(), "d")
    check(tcp_up(PORT, p=d6), "restart after graceful stop comes up")
    hard_kill(d6)

    # --- update server
    data = os.path.join(TMP, "upd"); os.makedirs(data)
    uargs = [os.path.join("update_server", "server.py"), "--data", data, "--host", "127.0.0.1", "--port", str(UPD)]
    u1 = spawn(uargs, {}, "u")
    check(tcp_up(UPD, p=u1), "update server starts")
    hard_kill(u1)
    u2 = spawn(uargs, {}, "u")
    check(tcp_up(UPD, p=u2), "update server restarted right after kill -9 comes up")
    u3 = spawn(uargs, dict(T2R_BIND_RETRY_S="2"), "u")
    try: rc = u3.wait(30)
    except subprocess.TimeoutExpired: rc = None
    check(rc == 3 and "FATAL" in text(u3), "second update server exits 3 with FATAL (rc=%s)" % rc)
    check(u2.poll() is None and tcp_up(UPD), "first update server still serving")
    s = socket.socket(); s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try: s.bind(("127.0.0.1", UPD)); stolen = True
    except OSError: stolen = False
    finally: s.close()
    check(not stolen, "SO_REUSEADDR bind cannot steal the update server port")
    hard_kill(u2)
finally:
    for p in PROCS:
        try:
            if p.poll() is None: p.kill(); p.wait(5)
        except Exception: pass
        try: p._out.close()
        except Exception: pass
    import shutil; shutil.rmtree(TMP, ignore_errors=True)
print("\n%d failed" % len(FAILS) if FAILS else "\nall passed")
sys.exit(1 if FAILS else 0)
