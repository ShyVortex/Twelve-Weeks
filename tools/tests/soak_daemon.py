#!/usr/bin/env python3
"""Soak test for the master server (tools/daemon.py): starts a REAL daemon process on a free port with a temp DB, drives N fake clients
against it for a configurable time and fails when memory / threads / handles / registries / log size keep growing.

  python tools/tests/soak_daemon.py [--minutes 10] [--clients 50] [--sample 5] [--dir E:\\t2tmp_agents\\soak] [--out report.json] [--quick]

Never touches the live server: the daemon gets its own ports (free ones), its own DB / log / admin secret under --dir, and
T2R_STATUS_FILE=0. Run from anywhere. --quick = 25 s / 8 clients (harness self-test, used by tools/tests/test_soak_harness.py).

Every fake client is what the real game sends (re/ protocol in the daemon docstring):
  * a Steam-helper connection (0xF0 register, 0xF3 keepalive, 0xF4 ping location, 0xF6 ping report)
  * a held menu / session connection (0x0f profile + 0x0e announce, 0x15 / 0x13 menu polls, 0x01 FIND MATCH, 0x05 searching polls)
  * short t2r-ext connections (0xBA notices, 0xB4 clan feed, 0xE0 clan, 0xE8 boosters, 0xCA perf, 0xE3 JIP clock, 0xE6 host migration,
    0xEA vote, 0xDA party, 0xDC interrogation, 0xC6 / 0xC8 map packs, 0xD0 name) - a new TCP connection per poll
  * the match lifecycle: found -> 0x09 loaded -> polls -> 0x12 result -> back to the menu -> queue again; some clients crash mid match
    (sockets just vanish), come back later, sometimes with a brand new token (token churn)
  * UDP 0x03 presence keepalives, from a fresh source port now and then
  * a chaos thread: random bytes, oversized / zero length frames, truncated payloads of every known opcode (fuzz), slowloris holders
    (a frame, then one byte every few seconds), connect-and-drop, UDP source-port sprays, connections from many 127.x source addresses
Measured every --sample seconds: RSS / private bytes, thread count, open handles, CPU %, daemon.log size (+ rotated files), DB size,
the daemon's own registry sizes (admin GET /sizes), and the round-trip time of a probe poll. At the end: growth verdicts + a log-spam table.
Exit code 0 = no growth trend, 1 = a trend / failure."""
import argparse, json, os, random, secrets, select, socket, struct, subprocess, sys, threading, time, ctypes, collections, re, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.dirname(HERE)
sys.path.insert(0, TOOLS)
import t2rtmp  # noqa: E402,F401  (temp hygiene)

STEAM_BASE = 76561197960265728 + 5000


def msg(op, payload=b""):
    body = bytes([op]) + payload
    return len(body).to_bytes(2, "little") + body


def free_port():
    s = socket.socket(); s.bind(("127.0.0.1", 0)); p = s.getsockname()[1]; s.close(); return p


# ----------------------------------------------------------------------------------------------------------- process metrics
class ProcMetrics:
    """RSS / private bytes / threads / handles / cpu seconds of another process (Windows: ctypes; Linux: /proc)."""
    def __init__(self, pid):
        self.pid = pid
        self.win = os.name == "nt"
        if self.win:
            k = ctypes.WinDLL("kernel32", use_last_error=True)
            self.k = k
            k.OpenProcess.restype = ctypes.c_void_p
            self.h = k.OpenProcess(0x1000 | 0x0400 | 0x0010, False, pid)   # QUERY_LIMITED | QUERY | VM_READ
            self.psapi = ctypes.WinDLL("psapi", use_last_error=True)
            self.psapi.GetProcessMemoryInfo.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_ulong]

            class PMC(ctypes.Structure):
                _fields_ = [("cb", ctypes.c_ulong), ("PageFaultCount", ctypes.c_ulong), ("PeakWorkingSetSize", ctypes.c_size_t),
                            ("WorkingSetSize", ctypes.c_size_t), ("QuotaPeakPagedPoolUsage", ctypes.c_size_t), ("QuotaPagedPoolUsage", ctypes.c_size_t),
                            ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t), ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                            ("PagefileUsage", ctypes.c_size_t), ("PeakPagefileUsage", ctypes.c_size_t), ("PrivateUsage", ctypes.c_size_t)]
            self.PMC = PMC

            class TE(ctypes.Structure):
                _fields_ = [("dwSize", ctypes.c_ulong), ("cntUsage", ctypes.c_ulong), ("th32ThreadID", ctypes.c_ulong),
                            ("th32OwnerProcessID", ctypes.c_ulong), ("tpBasePri", ctypes.c_long), ("tpDeltaPri", ctypes.c_long), ("dwFlags", ctypes.c_ulong)]
            self.TE = TE
            k.CreateToolhelp32Snapshot.restype = ctypes.c_void_p
            k.CreateToolhelp32Snapshot.argtypes = [ctypes.c_ulong, ctypes.c_ulong]
            k.Thread32First.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
            k.Thread32Next.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
            k.CloseHandle.argtypes = [ctypes.c_void_p]
            k.GetProcessHandleCount.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
            k.GetProcessTimes.argtypes = [ctypes.c_void_p] * 5

    def sample(self):
        if self.win:
            k = self.k
            pmc = self.PMC(); pmc.cb = ctypes.sizeof(pmc)
            self.psapi.GetProcessMemoryInfo(self.h, ctypes.byref(pmc), pmc.cb)
            hc = ctypes.c_ulong(0); k.GetProcessHandleCount(self.h, ctypes.byref(hc))
            ft = [ctypes.c_ulonglong(0) for _ in range(4)]
            k.GetProcessTimes(self.h, *[ctypes.byref(x) for x in ft])
            cpu = (ft[2].value + ft[3].value) / 1e7
            snap = k.CreateToolhelp32Snapshot(4, 0)
            n = 0
            te = self.TE(); te.dwSize = ctypes.sizeof(te)
            ok = k.Thread32First(snap, ctypes.byref(te))
            while ok:
                if te.th32OwnerProcessID == self.pid:
                    n += 1
                ok = k.Thread32Next(snap, ctypes.byref(te))
            k.CloseHandle(snap)
            return {"rss": pmc.WorkingSetSize, "priv": pmc.PrivateUsage, "handles": hc.value, "threads": n, "cpu_s": cpu}
        d = {}
        with open("/proc/%d/status" % self.pid) as f:
            for ln in f:
                if ln.startswith("VmRSS:"): d["rss"] = int(ln.split()[1]) * 1024
                if ln.startswith("Threads:"): d["threads"] = int(ln.split()[1])
        d["priv"] = d.get("rss", 0)
        d["handles"] = len(os.listdir("/proc/%d/fd" % self.pid))
        with open("/proc/%d/stat" % self.pid) as f:
            p = f.read().rsplit(")", 1)[1].split()
        d["cpu_s"] = (int(p[11]) + int(p[12])) / os.sysconf("SC_CLK_TCK")
        return d


# ----------------------------------------------------------------------------------------------------------- fake clients
KNOWN_OPS = [0x0f, 0x0e, 0x01, 0x05, 0x15, 0x13, 0x09, 0x12, 0x02, 0xF0, 0xF3, 0xF4, 0xF6, 0xD0, 0xD2, 0xE0, 0xE2, 0xE3, 0xE4, 0xE6, 0xE8, 0xEA, 0xEC, 0xEE, 0xEF,
             0xB0, 0xB2, 0xB4, 0xBA, 0xCA, 0xDA, 0xDC, 0xDE, 0xC6, 0xC8, 0xFC]


class Stats:
    def __init__(self):
        self.lock = threading.Lock()
        self.c = collections.Counter()
        self.rtt = []
    def add(self, k, n=1):
        with self.lock: self.c[k] += n
    def probe(self, ms):
        with self.lock:
            self.rtt.append(ms)
            if len(self.rtt) > 20000: self.rtt = self.rtt[-10000:]


def make_token(i, gen=0):
    name = ("S%d" % i + ("g%d" % gen if gen else ""))[:12]
    raw = b"T2N:" + name.encode() + b"\0"
    return (raw + secrets.token_bytes(32 - len(raw))).hex(), name


def read_frames(buf):
    out = []
    i = 0
    while len(buf) - i >= 2:
        ln = int.from_bytes(buf[i:i + 2], "little")
        if ln == 0:
            i += 2; continue
        if len(buf) - i < ln + 2: break
        out.append((buf[i + 2], buf[i + 3:i + 2 + ln])); i += 2 + ln
    return out, buf[i:]


class Client(threading.Thread):
    def __init__(self, idx, port, stats, stop, rnd_seed, match_secs=(25, 55), crash_p=0.15):
        super().__init__(daemon=True)
        self.idx, self.port, self.stats, self.stop_ev = idx, port, stats, stop
        self.rnd = random.Random(rnd_seed)
        self.gen = 0
        self.match_secs, self.crash_p = match_secs, crash_p
        self.tok, self.name = make_token(idx)
        self.steamid = STEAM_BASE + idx * 10
        self.bridge = self.sess = None
        self.rb = self.rs = b""
        self.state = "menu"
        self.due = {}
        self.udp = None
        self.first_login = True

    # -- plumbing
    def conn(self):
        s = socket.create_connection(("127.0.0.1", self.port), timeout=3)
        s.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        return s

    def close_all(self):
        for a in ("bridge", "sess"):
            s = getattr(self, a)
            if s:
                try: s.close()
                except OSError: pass
            setattr(self, a, None)
        self.rb = self.rs = b""

    def send(self, s, data):
        try:
            s.sendall(data); return True
        except OSError:
            self.stats.add("send-err"); return False

    def name32(self):
        return self.name.encode().ljust(32, b"\0")[:32]

    def ext_poll(self, op, payload, want_reply=True):
        t0 = time.time()
        try:
            s = socket.create_connection(("127.0.0.1", self.port), timeout=3)
            s.sendall(msg(op, payload))
            if want_reply:
                s.settimeout(2.0)
                s.recv(4096)
            s.close()
            self.stats.add("ext-poll")
            return time.time() - t0
        except (OSError, socket.timeout):
            self.stats.add("ext-err")
            return None

    # -- protocol bits
    def register_bridge(self):
        t = self.tok.encode()
        nm = self.name.encode()
        pl = t + struct.pack("<Q", self.steamid) + bytes([len(nm)]) + nm + struct.pack("<H", 30000 + self.idx)
        self.bridge = self.conn()
        self.send(self.bridge, msg(0xF0, pl))

    def login(self):
        self.sess = self.conn()
        login = bytes([0x1c]) + self.tok.encode() + b"\x01\x02\x07"
        if self.first_login:
            login = login + os.urandom(346 - len(login) - 32) + self.name32()      # the 346 B profile with the loadout blob
            self.first_login = False
        ann = bytes([0x1c]) + os.urandom(8) + self.name32()
        self.send(self.sess, msg(0x0f, login) + msg(0x0e, ann))
        self.state = "menu"

    def find_match(self):
        ann = bytes([0x1c]) + os.urandom(8) + self.name32()
        if self.send(self.sess, msg(0x01, ann)):
            self.state = "queue"; self.stats.add("find-match")

    def drain(self):
        for attr, sock in (("rb", self.bridge), ("rs", self.sess)):
            if not sock: continue
            try:
                while select.select([sock], [], [], 0)[0]:
                    d = sock.recv(8192)
                    if not d:
                        if attr == "rs": self.sess = None
                        else: self.bridge = None
                        break
                    setattr(self, attr, getattr(self, attr) + d)
            except OSError:
                if attr == "rs": self.sess = None
                else: self.bridge = None
        fr, self.rs = read_frames(self.rs)
        for op, pl in fr:
            if op == 0x04 and self.state == "queue":
                self.on_match()
            elif op == 0x0d and self.state in ("queue", "match") and False:
                pass
        _, self.rb = read_frames(self.rb)

    def on_match(self):
        self.state = "match"
        self.stats.add("match-start")
        now = time.time()
        dur = self.rnd.uniform(*self.match_secs)
        self.m_loaded = now + self.rnd.uniform(1, 4)
        self.m_end = now + dur
        self.m_crash = (now + self.rnd.uniform(3, dur)) if self.rnd.random() < self.crash_p else None
        self.m_sent_loaded = self.m_sent_end = False

    def new_identity(self):
        self.gen += 1
        self.tok, self.name = make_token(self.idx, self.gen)
        self.first_login = True

    def ext_tick(self, now):
        t = self.tok.encode()
        def every(k, secs, jitter=0.3):
            if now >= self.due.get(k, 0):
                self.due[k] = now + secs * self.rnd.uniform(1 - jitter, 1 + jitter)
                return True
            return False
        if every("notice", 6): self.ext_poll(0xBA, t + bytes([1, 0]))
        if every("feed", 20): self.ext_poll(0xB4, t + bytes([self.rnd.randint(0, 1)]))
        if every("clan", 30): self.ext_poll(0xE0, t)
        if every("boost", 40): self.ext_poll(0xE8, t)
        if every("perf", 30): self.ext_poll(0xCA, t + bytes([1, 0, 0]) + struct.pack("<HH", 120, 166) + b"\x00")
        if every("name", 60): self.ext_poll(0xD0, t)
        if every("party", 45): self.ext_poll(0xDA, t + b"\x00")
        if every("vote", 25): self.ext_poll(0xEA, t)
        if every("int", 30): self.ext_poll(0xDC, t + b"\x00" + struct.pack("<H", 1))
        if every("packs", 60): self.ext_poll(0xC6, t + bytes([0]))
        if every("sp", 60): self.ext_poll(0xC8, t + struct.pack("<I", 0xFF))
        if every("ver", 120): self.ext_poll(0xB0, bytes([6]) + b"soak-1" + t)
        if self.state == "match":
            if every("hm", 2): self.ext_poll(0xE6, t + bytes([0, 0]))
            if every("jip", 3):
                left = max(0.0, self.m_end - now)
                self.ext_poll(0xE3, t + bytes([1]) + struct.pack("<ff", left, 600.0) + bytes([self.idx & 1, 20, 20]))
        elif every("hm_idle", 15):
            self.ext_poll(0xE6, t + bytes([0, 0]))

    def tick(self, now):
        # bridge
        if self.bridge is None:
            self.register_bridge(); self.due["bka"] = now + 3
        if now >= self.due.get("bka", 0) and self.bridge:
            self.due["bka"] = now + 3
            self.send(self.bridge, msg(0xF3))
        if now >= self.due.get("loc", 0) and self.bridge:
            self.due["loc"] = now + 20
            self.send(self.bridge, msg(0xF4, b"sto=%d,ams=%d,waw=%d" % (self.rnd.randint(20, 90), self.rnd.randint(10, 60), self.rnd.randint(5, 30))))
        if now >= self.due.get("rep", 0) and self.bridge:
            self.due["rep"] = now + 10
            self.send(self.bridge, msg(0xF6, struct.pack("<Qi", STEAM_BASE + self.rnd.randint(0, 300) * 10, self.rnd.randint(15, 140))))
        # session
        if self.sess is None:
            self.login(); self.due["menu"] = now + 3; self.due["q_at"] = now + self.rnd.uniform(3, 8)
        if self.state == "menu":
            if now >= self.due.get("menu", 0):
                self.due["menu"] = now + 3
                self.send(self.sess, msg(0x15) + (msg(0x13) if self.rnd.random() < 0.1 else b""))
            if now >= self.due.get("q_at", 0):
                self.find_match(); self.due["qp"] = now + 1.5
        elif self.state == "queue":
            if now >= self.due.get("qp", 0):
                self.due["qp"] = now + 1.5
                self.send(self.sess, msg(0x05))
            if now - self.due.get("q_at", now) > 240 and self.rnd.random() < 0.05:        # gave up searching (backs out)
                self.send(self.sess, msg(0x02)); self.close_all(); self.state = "menu"
        elif self.state == "match":
            if now >= self.due.get("kp", 0):
                self.due["kp"] = now + 3
                self.send(self.sess, msg(0x05))
            if self.m_crash and now >= self.m_crash:
                self.stats.add("crash")
                self.close_all(); self.state = "crashed"
                self.due["back"] = now + self.rnd.uniform(15, 90)
                if self.rnd.random() < 0.4: self.new_identity()
                return
            if not self.m_sent_loaded and now >= self.m_loaded:
                self.m_sent_loaded = True; self.send(self.sess, msg(0x09))
            if not self.m_sent_end and now >= self.m_end:
                self.m_sent_end = True; self.send(self.sess, msg(0x12, bytes([self.rnd.randint(0, 2)])))
                self.due["after_end"] = now + 11
            if self.m_sent_end and now >= self.due.get("after_end", 1e18):
                self.send(self.sess, msg(0x02))
                self.close_all(); self.state = "menu"; self.due["after_end"] = 1e18
        elif self.state == "crashed":
            if now >= self.due.get("back", 0):
                self.state = "menu"
            return
        # udp presence
        if now >= self.due.get("udp", 0):
            self.due["udp"] = now + 3
            try:
                if self.udp is None or self.rnd.random() < 0.15:
                    if self.udp: self.udp.close()
                    self.udp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                self.udp.sendto(b"\x03" + struct.pack("<I", int(now) & 0xFFFFFFFF), ("127.0.0.1", self.port))
            except OSError:
                self.stats.add("udp-err")
        self.ext_tick(now)
        self.drain()

    def run(self):
        time.sleep(self.rnd.uniform(0, 3))
        while not self.stop_ev.is_set():
            try:
                self.tick(time.time())
            except Exception as e:  # a client bug must not stop the soak
                self.stats.add("client-exc")
                self.close_all(); self.state = "menu"; self.sess = None
                time.sleep(0.5)
            time.sleep(0.15)
        self.close_all()


class Chaos(threading.Thread):
    """Malformed / hostile traffic. Must never hurt the daemon."""
    def __init__(self, port, stats, stop, per_sec=6.0, seed=1):
        super().__init__(daemon=True)
        self.port, self.stats, self.stop_ev, self.per_sec = port, stats, stop, per_sec
        self.rnd = random.Random(seed)
        self.holders = []     # (socket, closes at)
        self.can_vary_ip = True

    def sock(self):
        s = socket.socket()
        if self.can_vary_ip and self.rnd.random() < 0.5:
            try:
                s.bind(("127.%d.%d.%d" % (self.rnd.randint(1, 250), self.rnd.randint(0, 250), self.rnd.randint(1, 250)), 0))
            except OSError:
                self.can_vary_ip = False; s.close(); s = socket.socket()
        s.settimeout(2)
        s.connect(("127.0.0.1", self.port))
        return s

    def one(self):
        r = self.rnd
        kind = r.choice(["rand", "huge", "zero", "fuzz", "fuzz", "fuzz", "drop", "holder", "udpspray", "badlogin", "partial"])
        if kind == "udpspray":
            for _ in range(r.randint(5, 40)):
                u = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                u.sendto(r.choice([b"\x03", b"\x03\0\0\0\0", os.urandom(r.randint(1, 60)), b"\x00" + os.urandom(5), b"\x02" + os.urandom(20)]), ("127.0.0.1", self.port))
                u.close()
            self.stats.add("chaos-udp"); return
        s = self.sock()
        try:
            if kind == "rand":
                s.sendall(os.urandom(r.randint(1, 3000)))
            elif kind == "huge":
                s.sendall(struct.pack("<H", 0xFFFF) + os.urandom(r.randint(1, 5000)))
            elif kind == "zero":
                s.sendall(b"\0\0" * r.randint(1, 3000))
            elif kind == "fuzz":
                for _ in range(r.randint(1, 5)):
                    op = r.choice(KNOWN_OPS)
                    body = os.urandom(r.randint(0, 120)) if r.random() < 0.5 else (bytes([0x1c]) if r.random() < 0.3 else b"") + secrets.token_hex(32).encode()[:r.randint(0, 64)] + os.urandom(r.randint(0, 40))
                    s.sendall(msg(op, body))
                    time.sleep(0.02)
                try:
                    s.settimeout(0.3); s.recv(4096)
                except (OSError, socket.timeout):
                    pass
            elif kind == "badlogin":
                s.sendall(msg(0x0f, bytes([0x1c]) + secrets.token_hex(32).encode() + os.urandom(r.randint(0, 400))))
                time.sleep(0.4)
            elif kind == "partial":     # a complete frame (so the connection counts as live), then half a frame and silence
                s.sendall(msg(0x15) + struct.pack("<H", 50) + b"\x05")
                self.holders.append((s, time.time() + r.uniform(5, 40))); self.stats.add("holders"); return
            elif kind == "holder":      # connect, send nothing / one byte
                if r.random() < 0.5: s.sendall(b"\x05")
                self.holders.append((s, time.time() + r.uniform(5, 25))); self.stats.add("holders"); return
            self.stats.add("chaos-" + kind)
        except (OSError, socket.timeout):
            self.stats.add("chaos-err")
        finally:
            if not any(h[0] is s for h in self.holders):
                try: s.close()
                except OSError: pass

    def run(self):
        while not self.stop_ev.is_set():
            try:
                self.one()
            except Exception:
                self.stats.add("chaos-exc")
            now = time.time()
            keep = []
            for s, t in self.holders:
                if now >= t or len(self.holders) > 150:
                    try: s.close()
                    except OSError: pass
                else:
                    if self.rnd.random() < 0.05:           # the slowloris dribble
                        try: s.sendall(b"\x01")
                        except OSError: continue
                    keep.append((s, t))
            self.holders = keep
            time.sleep(self.rnd.expovariate(self.per_sec))
        for s, _ in self.holders:
            try: s.close()
            except OSError: pass


# ----------------------------------------------------------------------------------------------------------- analysis
def mean(a):
    return sum(a) / len(a) if a else 0.0


def window(series, lo, hi):
    n = len(series)
    return series[int(n * lo):max(int(n * hi), int(n * lo) + 1)]


def trend(series, rel_tol=0.08, abs_tol=0.0, use="mean"):
    """Compare the last 20 % with the 30-50 % window (after warm-up). Returns (growth, mid, last, bad)."""
    if len(series) < 10:
        return 0.0, 0.0, 0.0, False
    f = mean if use == "mean" else max
    mid, last = f(window(series, 0.3, 0.5)), f(window(series, 0.8, 1.0))
    g = last - mid
    return g, mid, last, (g > abs_tol and g > rel_tol * max(mid, 1e-9))


def log_spam(paths, top=12):
    c = collections.Counter(); n = 0
    pat = re.compile(r"^\[\d\d:\d\d:\d\d\] (\S+(?: \S+)?)")
    for p in paths:
        try:
            with open(p, encoding="utf-8", errors="replace") as f:
                for ln in f:
                    n += 1
                    m = pat.match(ln)
                    if m:
                        k = re.sub(r"[0-9a-f]{8,}|\d+", "#", m.group(1))
                        k = re.sub(r"\('127\.0\.0\.1', #\)", "", k)
                        c[k] += 1
        except OSError:
            pass
    return n, c.most_common(top)


# ----------------------------------------------------------------------------------------------------------- main
def admin_get(port, secret, path):
    req = urllib.request.Request("http://127.0.0.1:%d%s" % (port, path), headers={"X-Admin-Secret": secret})
    with urllib.request.urlopen(req, timeout=5) as r:
        return json.loads(r.read())


def run_soak(minutes, clients, sample, workdir, out=None, env_extra=None, chaos_rate=6.0, verbose=True, trends=True):
    os.makedirs(workdir, exist_ok=True)
    work = os.path.join(workdir, "run-%d" % int(time.time()))
    os.makedirs(work)
    port, aport = free_port(), free_port()
    logp = os.path.join(work, "daemon.log")
    env = dict(os.environ)
    env.update(T2R_HOST="127.0.0.1", T2R_PORT=str(port), T2R_ADMIN_PORT=str(aport), T2R_DB=os.path.join(work, "t2r.db"), T2R_LOG_PATH=logp,
               T2R_STATUS_FILE="0", T2R_MATCH_SIZE="4", T2R_MIN_PLAYERS="2", T2R_FILL_WAIT="4", T2R_QUEUE_SETTLE="1", T2R_PRE_COUNTDOWN="1",
               T2R_COUNTDOWN="2", T2R_NEW_TOKENS_PER_10MIN="1000000", T2R_MAX_CONNS="2000", T2R_STATE_TTL_S="90", T2R_STATE_GC_S="20", T2R_RELAY_IDLE_S="120",
               T2R_LOG_MAX_BYTES=str(2 * 1024 * 1024), T2R_LOG_KEEP="3", T2R_MAP_VOTE="1", PYTHONUNBUFFERED="1")
    env.update(env_extra or {})
    dout = open(os.path.join(work, "daemon.stdout.txt"), "wb")
    proc = subprocess.Popen([sys.executable, os.path.join(TOOLS, "daemon.py")], env=env, stdout=dout, stderr=subprocess.STDOUT, cwd=work)
    stop = threading.Event()
    stats = Stats()
    try:
        for _ in range(100):
            try:
                socket.create_connection(("127.0.0.1", port), timeout=0.5).close(); break
            except OSError:
                time.sleep(0.2)
        else:
            raise RuntimeError("daemon did not start (see %s)" % work)
        secret = ""
        for _ in range(50):
            try:
                secret = open(os.path.join(work, "admin-secret.txt")).read().strip()
                if secret: break
            except OSError:
                pass
            time.sleep(0.2)
        pm = ProcMetrics(proc.pid)
        cl = [Client(i, port, stats, stop, 1000 + i) for i in range(clients)]
        for c in cl: c.start()
        ch = Chaos(port, stats, stop, per_sec=chaos_rate); ch.start()

        probe_tok = secrets.token_hex(32)
        def prober():
            while not stop.is_set():
                t0 = time.perf_counter()
                try:
                    s = socket.create_connection(("127.0.0.1", port), timeout=5)
                    s.sendall(msg(0xBA, probe_tok.encode() + bytes([1, 0])))
                    s.settimeout(5); s.recv(4096); s.close()
                    stats.probe((time.perf_counter() - t0) * 1000)
                except (OSError, socket.timeout):
                    stats.add("probe-fail")
                time.sleep(1.0)
        threading.Thread(target=prober, daemon=True).start()

        samples = []
        t_start = time.time(); t_end = t_start + minutes * 60
        last_cpu = (t_start, pm.sample()["cpu_s"])
        while time.time() < t_end and proc.poll() is None:
            time.sleep(sample)
            now = time.time()
            m = pm.sample()
            cpu_pct = 100.0 * (m["cpu_s"] - last_cpu[1]) / max(1e-6, now - last_cpu[0])
            last_cpu = (now, m["cpu_s"])
            logbytes = sum(os.path.getsize(p) for p in [logp] + ["%s.%d" % (logp, i) for i in range(1, 8)] if os.path.exists(p))
            dbb = sum(os.path.getsize(os.path.join(work, f)) for f in os.listdir(work) if f.startswith("t2r.db") and os.path.isfile(os.path.join(work, f)))
            try:
                sizes = admin_get(aport, secret, "/sizes").get("sizes", {})
            except Exception:
                sizes = {}
            sm = {"t": now - t_start, "rss_mb": m["rss"] / 1048576, "priv_mb": m["priv"] / 1048576, "threads": m["threads"], "handles": m["handles"],
                  "cpu_pct": cpu_pct, "log_kb": logbytes / 1024, "db_kb": dbb / 1024, "sizes": sizes}
            samples.append(sm)
            if verbose:
                print("t=%4.0fs rss=%6.1fMB threads=%3d handles=%4d cpu=%5.1f%% log=%7.0fKB db=%5.0fKB  registry-entries=%d matches-started=%s" % (
                    sm["t"], sm["rss_mb"], sm["threads"], sm["handles"], cpu_pct, sm["log_kb"], sm["db_kb"], sum(v for k, v in sizes.items() if k not in ("threads", "tcp_live", "log_queue", "_caps")),
                    dict(stats.c).get("match-start", 0)), flush=True)
        alive = proc.poll() is None
        stop.set()
        time.sleep(1.0)
        res = analyse(samples, stats, alive, [logp] + ["%s.%d" % (logp, i) for i in range(1, 8)], clients, minutes, env, trends)
        res["workdir"] = work
        if out:
            with open(out, "w") as f: json.dump(res, f, indent=1, default=str)
        return res
    finally:
        stop.set()
        try:
            if proc.poll() is None:
                proc.terminate(); proc.wait(10)
        except Exception:
            try: proc.kill()
            except Exception: pass
        dout.close()


WINDOWED = {"UDP_STATS", "RELAY_STATS", "RELAY_TYPES", "UdpRelay.sizes", "UdpRelay.pk_in", "UdpRelay.pk_out", "log_queue", "tcp_live", "threads"}   # per-status-tick counters / checked elsewhere


def analyse(samples, stats, alive, logpaths, clients, minutes, env, trends=True):
    fails, notes = [], []
    if not alive: fails.append("daemon process died during the soak")
    if len(samples) < 6: fails.append("too few samples (%d)" % len(samples))
    S = lambda k: [s[k] for s in samples]
    verdict = {}
    for key, rel, ab, label in (("rss_mb", 0.08, 6.0, "RSS"), ("priv_mb", 0.08, 6.0, "private bytes"), ("threads", 0.15, 8, "threads"), ("handles", 0.15, 25, "handles")):
        g, mid, last, bad = trend(S(key), rel, ab)
        verdict[key] = {"mid": round(mid, 1), "last": round(last, 1), "growth": round(g, 1), "bad": bad}
        if bad: fails.append("%s keeps growing: %.1f -> %.1f" % (label, mid, last))
    cpu = S("cpu_pct")
    verdict["cpu_pct_mean"] = round(mean(cpu), 2)
    g, mid, last, bad = trend(cpu, 0.5, 5.0)
    if bad: fails.append("CPU rises over time: %.1f%% -> %.1f%%" % (mid, last))
    # log size: bounded by LOG_MAX_BYTES * (KEEP + 1) + one flush interval
    cap = int(env["T2R_LOG_MAX_BYTES"]) * (int(env["T2R_LOG_KEEP"]) + 1) / 1024 * 1.1 + 512
    verdict["log_kb_max"] = round(max(S("log_kb") or [0]))
    verdict["log_cap_kb"] = round(cap)
    if verdict["log_kb_max"] > cap: fails.append("log files exceed the cap: %d KB > %d KB" % (verdict["log_kb_max"], cap))
    # log rate: lines per second per client (spam indicator)
    nlines, top = log_spam(logpaths)
    secs = max(1.0, samples[-1]["t"] if samples else 1.0)
    verdict["log_lines"] = nlines
    verdict["log_lines_per_s"] = round(nlines / secs, 1)
    verdict["log_lines_per_s_per_client"] = round(nlines / secs / max(1, clients), 2)
    verdict["log_top"] = top
    # registries
    growing, bounded = {}, {}
    keys = set()
    caps = {}
    for s in samples:
        keys |= set(s["sizes"]); caps.update(s["sizes"].get("_caps") or {})
    for k in sorted(keys):
        if k == "_caps" or k in WINDOWED:
            continue
        ser = [s["sizes"].get(k, 0) for s in samples]
        g, mid, last, bad = trend(ser, 0.25, 30, use="max")
        if bad and last > 60:
            if k in caps and max(ser) <= caps[k]:
                bounded[k] = (mid, last, caps[k])          # still filling a table with a hard cap: not a leak
            else:
                growing[k] = (mid, last)
    verdict["capped_tables"] = bounded
    verdict["growing_registries"] = growing
    for k, (mid, last) in growing.items():
        fails.append("registry %s keeps growing: %d -> %d" % (k, mid, last))
    pr = sorted(stats.rtt)
    if pr:
        verdict["probe_ms"] = {"n": len(pr), "p50": round(pr[len(pr) // 2], 1), "p99": round(pr[int(len(pr) * 0.99)], 1), "max": round(pr[-1], 1)}
        if verdict["probe_ms"]["p99"] > 1500: fails.append("probe poll p99 %.0f ms" % verdict["probe_ms"]["p99"])
    verdict["probe_fail"] = stats.c.get("probe-fail", 0)
    if stats.c.get("probe-fail", 0) > max(3, 0.02 * len(pr)): fails.append("%d probe polls failed" % stats.c["probe-fail"])
    verdict["client_counters"] = dict(stats.c)
    if stats.c.get("match-start", 0) == 0 and clients >= 4 and minutes >= 0.3:
        fails.append("no match ever formed (the fake clients never matched)")
    if not trends:       # a quick run is too short for trend verdicts (warm-up dominates): they stay in the numbers only
        fails = [f for f in fails if not (f.startswith(("RSS", "private", "threads", "handles", "CPU", "registry")))]
    return {"ok": not fails, "fails": fails, "verdict": verdict, "clients": clients, "minutes": minutes, "samples": samples}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--minutes", type=float, default=10)
    ap.add_argument("--clients", type=int, default=50)
    ap.add_argument("--sample", type=float, default=5)
    ap.add_argument("--dir", default=os.environ.get("T2R_TEST_TMP") or os.environ.get("T2R_TMP") or r"E:\t2tmp_agents\soak")
    ap.add_argument("--out")
    ap.add_argument("--quick", action="store_true")
    ap.add_argument("--chaos", type=float, default=6.0, help="chaos events per second")
    a = ap.parse_args()
    if a.quick:
        a.minutes, a.clients, a.sample = 0.4, 8, 2
    res = run_soak(a.minutes, a.clients, a.sample, a.dir, a.out, chaos_rate=a.chaos, trends=not a.quick)
    v = res["verdict"]
    print("\n=== soak result: %s (%d clients, %.1f min) ===" % ("PASS" if res["ok"] else "FAIL", a.clients, a.minutes))
    for k in ("rss_mb", "priv_mb", "threads", "handles"):
        print("  %-9s mid-window %-8s last-window %-8s growth %s%s" % (k, v[k]["mid"], v[k]["last"], v[k]["growth"], "  <-- GROWING" if v[k]["bad"] else ""))
    print("  cpu mean %.2f %%   log max %d KB (cap %d KB)   log lines %d (%.1f/s, %.2f/s per client)" % (
        v["cpu_pct_mean"], v["log_kb_max"], v["log_cap_kb"], v["log_lines"], v["log_lines_per_s"], v["log_lines_per_s_per_client"]))
    print("  probe poll ms:", v.get("probe_ms"), "failed:", v["probe_fail"])
    print("  growing registries:", v["growing_registries"] or "none", "| filling capped tables:", v.get("capped_tables") or "none")
    print("  clients:", v["client_counters"])
    print("  top log prefixes:", v["log_top"])
    for f in res["fails"]: print("FAIL", f)
    sys.exit(0 if res["ok"] else 1)


if __name__ == "__main__":
    main()
