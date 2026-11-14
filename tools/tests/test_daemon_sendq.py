"""Tests for the per-connection outbound queue (daemon.OutConn, re/daemon-sendpath-1019.md):
 1. unit: sendall never blocks on a peer that does not read, order / bytes are exact once it reads, droppable frames are shed first, overflow and
    a stalled peer close the connection, close() flushes.
 2. integration (real daemon process, free ports, temp DB): a fake client that logs in, queues for a match and then NEVER reads (tiny SO_RCVBUF, flooded
    with polls so the daemon's send buffer toward it is full) must not delay matchmaking / the match start of the other players.
Run: python tools/tests/test_daemon_sendq.py [--old <daemon.py>]   (--old runs part 2 against another daemon file to show the old behaviour)."""
import os, sys, socket, struct, subprocess, tempfile, threading, time
import sys as _t2s, os as _t2o; _t2s.path.append(_t2o.path.normpath(_t2o.path.join(_t2o.path.dirname(_t2o.path.abspath(__file__)), ".."))); import t2rtmp  # noqa: E402,F401

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.dirname(HERE)
sys.path.insert(0, TOOLS); sys.path.insert(0, HERE)
FAILS = []
def check(cond, what):
    print(("ok   " if cond else "FAIL ") + what, flush=True)
    if not cond: FAILS.append(what)

def free_port():
    s = socket.socket(); s.bind(("127.0.0.1", 0)); p = s.getsockname()[1]; s.close(); return p

OLD = None
if "--old" in sys.argv: OLD = sys.argv[sys.argv.index("--old") + 1]

# ------------------------------------------------------------------ 1. unit
def part1():
    tmp = tempfile.mkdtemp()
    os.environ.update(T2R_HOST="127.0.0.1", T2R_PORT=str(free_port()), T2R_ADMIN_PORT=str(free_port()), T2R_STATUS_FILE="0", T2R_DB=os.path.join(tmp, "t2r.db"))
    import daemon
    daemon.LOG_PATH = os.path.join(tmp, "daemon.log")
    def pair(rcv=2048):
        ls = socket.socket(); ls.bind(("127.0.0.1", 0)); ls.listen(1)
        cl = socket.socket(); cl.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, rcv); cl.connect(ls.getsockname())
        sv, _ = ls.accept(); ls.close()
        sv.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, 4096); sv.settimeout(120)
        return daemon.OutConn(sv), cl
    # order + exactness through a reader that starts late
    oc, cl = pair()
    blob = [os.urandom(900) for _ in range(120)]           # ~108 KB: far more than the kernel buffers toward a non-reader
    t0 = time.monotonic()
    for b in blob: oc.sendall(b)
    dt = time.monotonic() - t0
    check(dt < 1.0, "sendall to a non-reading peer returns at once (%d frames, %.3f s)" % (len(blob), dt))
    got = b""; cl.settimeout(3); want = b"".join(blob)
    while len(got) < len(want):
        d = cl.recv(65536)
        if not d: break
        got += d
    check(got == want, "all %d B arrive in order once the peer reads" % len(want))
    oc.close(); cl.close()
    # droppable frames are shed first, the rest survives, the stream stays intact
    old = (daemon.SENDQ_MAX_BYTES, daemon.SENDQ_MAX_FRAMES)
    daemon.SENDQ_MAX_BYTES, daemon.SENDQ_MAX_FRAMES = 30000, 512
    oc, cl = pair()
    keep = [b"K%03d" % i + os.urandom(400) for i in range(8)]
    for i in range(200):
        oc.sendall(b"D%03d" % i + os.urandom(400), drop=True)     # state pushes
        if i < len(keep): oc.sendall(keep[i])                      # must-deliver
    check(daemon.SENDQ_STATS["dropped"] > 0, "droppable frames were shed on overflow (%d dropped)" % daemon.SENDQ_STATS["dropped"])
    got = b""; cl.settimeout(1.0)
    try:
        while True:
            d = cl.recv(65536)
            if not d: break
            got += d
    except socket.timeout: pass
    check(all(k in got for k in keep), "every non-droppable frame was delivered after shedding")
    check(len(got) > 0 and got.count(b"D") + got.count(b"K") >= 8, "stream carries whole frames (%d B)" % len(got))
    oc.close(); cl.close()
    # overflow with nothing droppable closes the connection (sender gets an error, the peer sees EOF)
    daemon.SENDQ_MAX_BYTES = 20000
    oc, cl = pair()
    err = None
    try:
        for i in range(200): oc.sendall(os.urandom(1000))
    except OSError as e: err = e
    check(err is not None, "overflow of must-deliver frames raises to the sender and closes (%r)" % (err,))
    cl.settimeout(2); eof = False
    try:
        while True:
            if not cl.recv(65536): eof = True; break
    except OSError: eof = True
    check(eof, "the peer is disconnected after an overflow")
    try: oc.sendall(b"x"); check(False, "send after kill raises")
    except OSError: check(True, "send after kill raises")
    oc.close(); cl.close()
    daemon.SENDQ_MAX_BYTES, daemon.SENDQ_MAX_FRAMES = old
    # a peer that accepts nothing for SENDQ_STALL_S is dropped by the writer
    st = daemon.SENDQ_STALL_S; daemon.SENDQ_STALL_S = 1.0
    oc, cl = pair()
    for i in range(60): oc.sendall(os.urandom(1000))
    t0 = time.monotonic(); dead = False
    while time.monotonic() - t0 < 6:
        if oc._dead: dead = True; break
        time.sleep(0.1)
    check(dead and time.monotonic() - t0 < 4, "stalled peer dropped after ~SENDQ_STALL_S (%.1f s)" % (time.monotonic() - t0))
    daemon.SENDQ_STALL_S = st
    oc.close(); cl.close()
    # close() flushes queued data first
    oc, cl = pair()
    blob = os.urandom(60000); oc.sendall(blob); oc.close()
    got = b""; cl.settimeout(3)
    try:
        while len(got) < len(blob):
            d = cl.recv(65536)
            if not d: break
            got += d
    except socket.timeout: pass
    check(got == blob, "close() flushes the queued bytes before closing (%d/%d)" % (len(got), len(blob)))
    cl.close()
    # writer-exit race (pm81d): a frame queued in the instant the writer thread is leaving must not be stranded. The lock is wrapped so the
    # writer thread pauses 80 ms right after every critical section that finds the queue empty (the old code left `_writer` set across that gap).
    class SlowExitLock:
        def __init__(self, oc, owner): self.l = threading.Lock(); self.oc = oc; self.owner = owner
        def __enter__(self): self.l.acquire(); self.entry_empty = not self.oc._q; return self
        def __exit__(self, *a):
            empty = not self.oc._q and getattr(self, 'entry_empty', False)     # the writer's 'queue empty -> leave' check, not its pop
            self.l.release()
            if empty and threading.get_ident() != self.owner: time.sleep(0.08)
        def acquire(self, *a, **k): return self.l.acquire(*a, **k)
        def release(self): self.l.release()
    oc, cl = pair(rcv=4096)
    oc._lock = SlowExitLock(oc, threading.get_ident())
    big = os.urandom(225000)
    for i in range(250): oc.sendall(big[i * 900:(i + 1) * 900])                 # a non-reading peer: the kernel buffers fill -> writer thread
    got = bytearray(); cl.settimeout(0.05); stopr = threading.Event()
    def rd():
        while not stopr.is_set():
            try:
                d = cl.recv(65536)
                if not d: break
                got.extend(d)
            except socket.timeout: pass
            except OSError: break
    th = threading.Thread(target=rd); th.start()
    t0 = time.monotonic()
    while oc._q and time.monotonic() - t0 < 5: time.sleep(0.001)      # queue just drained: the writer is inside its 80 ms exit gap
    oc.sendall(b"TAILFRAME")
    time.sleep(1.5); stopr.set(); th.join()
    check(bytes(got) == big + b"TAILFRAME", "a frame queued while the writer thread is leaving is delivered (%d/%d B)" % (len(got), len(big) + 9))
    oc.close(); cl.close()
    # fast path starts no thread
    n0 = threading.active_count()
    oc, cl = pair()
    for i in range(50): oc.sendall(b"hello")
    check(threading.active_count() == n0, "small sends to a reading peer use no writer thread")
    oc.close(); cl.close()

# ------------------------------------------------------------------ 2. integration
def msg(op, pl=b""): return struct.pack("<H", len(pl) + 1) + bytes([op]) + pl

def part2():
    import soak_daemon as sd
    work = tempfile.mkdtemp(); port, aport = free_port(), free_port()
    env = dict(os.environ)
    env.update(T2R_HOST="127.0.0.1", T2R_PORT=str(port), T2R_ADMIN_PORT=str(aport), T2R_DB=os.path.join(work, "t2r.db"), T2R_LOG_PATH=os.path.join(work, "daemon.log"),
               T2R_STATUS_FILE="0", T2R_MATCH_SIZE="2", T2R_MIN_PLAYERS="2", T2R_FILL_WAIT="1", T2R_QUEUE_SETTLE="1", T2R_PRE_COUNTDOWN="1", T2R_COUNTDOWN="2",
               T2R_STEAM_ONLY="0", T2R_TCP_SNDBUF="2048", T2R_SENDQ_FRAMES="100000", T2R_SENDQ_BYTES="4000000", T2R_SENDQ_STALL_S="60", T2R_FLOOD_MAX_RECVS="10000000", T2R_MAP_VOTE="0", T2R_NEW_TOKENS_PER_10MIN="100000", PYTHONUNBUFFERED="1")
    script = OLD or os.path.join(TOOLS, "daemon.py")
    if OLD: env["PYTHONPATH"] = TOOLS
    dout = open(os.path.join(work, "stdout.txt"), "wb")
    proc = subprocess.Popen([sys.executable, script], env=env, stdout=dout, stderr=subprocess.STDOUT, cwd=work)
    stats = sd.Stats(); stop = threading.Event()
    try:
        for _ in range(100):
            try: socket.create_connection(("127.0.0.1", port), timeout=0.5).close(); break
            except OSError: time.sleep(0.2)
        def mk(i):
            c = sd.Client(i, port, stats, stop, i, crash_p=0)
            c.login(); return c
        def wait_match(cs, secs):
            t0 = time.monotonic(); got = {}
            while time.monotonic() - t0 < secs and len(got) < len(cs):
                for c in cs:
                    if c in got: continue
                    c.drain()
                    if c.state == "match": got[c] = time.monotonic() - t0
                time.sleep(0.02)
            return got
        # baseline pair
        a, b = mk(1), mk(2); time.sleep(0.5)
        a.find_match(); b.find_match()
        base = wait_match([a, b], 20)
        check(len(base) == 2, "baseline pair is matched (%s)" % ({c.idx: round(t, 2) for c, t in base.items()},))
        base_t = max(base.values()) if base else 20
        # the staller: logs in, queues, then never reads while the daemon's replies to its polls fill its (tiny) receive window
        st = socket.socket(); st.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 1024); st.connect(("127.0.0.1", port))
        tok, name = sd.make_token(900)
        login = bytes([0x1c]) + tok.encode() + b"\x01\x02\x07" + os.urandom(346 - 70 - 32) + name.encode().ljust(32, b"\0")
        ann = bytes([0x1c]) + os.urandom(8) + name.encode().ljust(32, b"\0")
        st.sendall(msg(0x0f, login) + msg(0x0e, ann)); time.sleep(0.3)
        st.sendall(msg(0x01, ann)); time.sleep(0.3)
        st.setblocking(False); sent = 0; t0 = time.monotonic(); full_for = 0
        poll = msg(0x05) * 200
        while time.monotonic() - t0 < 20 and full_for < 30:           # until the daemon stops reading us: its writes toward us are blocked
            try: sent += st.send(poll); full_for = 0
            except (BlockingIOError, InterruptedError): full_for += 1; time.sleep(0.1)
            except OSError: break
        print("staller flooded %d KB of polls; its receive window is full: %s" % (sent // 1024, full_for >= 30), flush=True)
        x = mk(3); time.sleep(0.5); x.find_match()                    # pairs with the staller: the match start is pushed to its stuck socket
        time.sleep(2.5)
        y, z = mk(4), mk(5); time.sleep(0.3)
        y.find_match(); z.find_match()
        res = wait_match([y, z], 40)
        lat = max(res.values()) if len(res) == 2 else 40
        print("others matched in %.2f s (baseline %.2f s) with a stuck client in the queue" % (lat, base_t), flush=True)
        check(len(res) == 2, "the other players are matched while a client does not read")
        check(lat < base_t + 6, "matchmaking latency for the others stays normal (%.2f s vs baseline %.2f s)" % (lat, base_t))
        st.close()
    finally:
        stop.set()
        proc.terminate()
        try: proc.wait(10)
        except Exception: pass
        dout.close()
    lp = os.path.join(work, "daemon.log")
    log = open(lp, errors="replace").read() if os.path.exists(lp) else ""
    print("SENDQ log lines:", [l for l in log.splitlines() if "SENDQ" in l][:3])
    if os.environ.get("DBG"): print(chr(10).join(l[:180] for l in log.splitlines()[-40:]))

if __name__ == "__main__":
    if not OLD: part1()
    part2()
    print("\nFAILED: %s" % FAILS if FAILS else "\nall ok")
    sys.exit(1 if FAILS else 0)
