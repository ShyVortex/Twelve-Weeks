#!/usr/bin/env python3
"""Model-based randomized test (stateful fuzz) of the master server's match lifecycle: tools/daemon.py (+ hostmig.py, clan.py).

  python tools/tests/fuzz_match_lifecycle.py --seed 7 --steps 200            one run (reproducible action list)
  python tools/tests/fuzz_match_lifecycle.py --seeds 0-299 --steps 200 -j 3  many seeds, 3 worker processes
  python tools/tests/fuzz_match_lifecycle.py --replay fail.json [--shrink]   re-run / minimise a recorded failing action list
  python tools/tests/fuzz_match_lifecycle.py --quick                         3 short seeds (tools/tests/test_fuzz_match_lifecycle.py)

A REAL daemon process (own free ports, temp DB / log / live-matches.json under --dir, T2R_STATUS_FILE=0) is started per seed. 2-12 fake clients
(sockets, the frames the game sends: Steam-helper 0xF0 / 0xF3, menu login 0x0f+0x0e, FIND MATCH 0x01, polls 0x05, loaded 0x09, result 0x12, leave 0x02,
and the t2r-ext short connections 0xE6 host migration, 0xE3 join-in-progress clock, 0xE2 clan day, 0xE4 side, 0xEC vote) are driven by a seeded random
action list: queue / unqueue / vote / booster / leave during the countdown / load fast-slow-never / crash and reconnect / host freeze + thaw / match
end with scores (by the host, sometimes by a non-host) / leave mid match / join in progress (a queue press while a match runs) / daemon restart
(hard kill or graceful, live-matches.json READOPT) / sim-clock delays. The daemon runs with --accel x time (a launcher patches time.monotonic /
time.sleep / threading.Timer of the daemon process only), so a 200-step run takes ~1-2 minutes.

After every observation (every ~0.5 sim s) the invariants run against the daemon's admin /live + /sizes and the client-visible replies:
  single-membership   a player is in at most one live match and not in a live match and the queue at once
  team-balance        a formed lobby has team sizes within 1; a join in progress never joins a strictly larger team; size <= MATCH_SIZE
  one-host            every match names exactly one host; its 0xE7 host slot is a live slot, and a dead host is replaced within a bound
  migration-live      a migration picks a player that was polling shortly before
  record-consistent   0x04 / 0xE5: slot < n, team == slot % 2, one session id and one map per match (a joiner gets the running match's)
  playing-vanished    a player who started the match and keeps polling is still in it
  stuck               no match of only dead players, no ghost queue entry, nothing left after the final quiesce (all registries empty)
  clan-once           "CLAN day" credited at most once per (player, match), only to members, DB day == credited lines
  log-clean           no Traceback / THREAD-DIED / handler ERR line in the daemon log or stdout, thread count never drops
A failure is shrunk (ddmin over the recorded action list) and printed as a minimal reproduction + saved as JSON (--replay).
Exit code 0 = all seeds clean."""
import argparse, collections, hashlib, http.client, json, os, random, re, select, secrets, socket, struct, subprocess, sys, tempfile, threading, time

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.dirname(HERE)
sys.path.insert(0, TOOLS)

# ---------------------------------------------------------------------------------------------------------------- daemon child (accelerated clock)
if len(sys.argv) > 1 and sys.argv[1] == "--daemon-child":
    import runpy, threading as _th
    _acc = float(os.environ.get("FUZZ_ACCEL", "1"))
    if _acc != 1.0:
        _rm, _rs = time.monotonic, time.sleep
        _m0 = _rm()
        time.monotonic = lambda: _m0 + (_rm() - _m0) * _acc
        time.sleep = lambda s: _rs(max(0.0, s) / _acc)
        _oi = _th.Timer.__init__
        def _ti(self, interval, *a, **k):
            _oi(self, interval / _acc, *a, **k)
        _th.Timer.__init__ = _ti
    sys.argv = [os.path.join(TOOLS, "daemon.py")] + sys.argv[2:]
    sys.path.insert(0, TOOLS)
    runpy.run_path(os.path.join(TOOLS, "daemon.py"), run_name="__main__")
    sys.exit(0)

import t2rtmp  # noqa: E402,F401  (temp hygiene)

STEAM_BASE = 76561197960265728 + 9000


def msg(op, payload=b""):
    body = bytes([op]) + payload
    return len(body).to_bytes(2, "little") + body


def free_port():
    """a free port OUTSIDE the ephemeral range (outgoing connections of parallel runs take ephemeral ports: a restarted daemon found its own port in use)"""
    for _ in range(200):
        p = random.randint(12000, 30000)
        s = socket.socket()
        try:
            s.bind(("127.0.0.1", p)); s.close(); return p
        except OSError:
            s.close()
    raise RuntimeError("no free port")


def read_frames(buf):
    out, i = [], 0
    while len(buf) - i >= 2:
        ln = int.from_bytes(buf[i:i + 2], "little")
        if ln == 0:
            i += 2; continue
        if len(buf) - i < ln + 2: break
        out.append((buf[i + 2], buf[i + 3:i + 2 + ln])); i += 2 + ln
    return out, buf[i:]


def make_token(i, rnd):
    name = "F%d" % i
    raw = b"T2N:" + name.encode() + b"\0"
    return (raw + bytes(rnd.getrandbits(8) for _ in range(32 - len(raw)))).hex(), name


def team_of(slot):
    return slot % 2


# ---------------------------------------------------------------------------------------------------------------- the daemon under test
SIM_ENV = dict(T2R_HOST="127.0.0.1", T2R_STATUS_FILE="0", T2R_MIN_PLAYERS="2", T2R_FILL_WAIT="3", T2R_QUEUE_SETTLE="1", T2R_PRE_COUNTDOWN="1",
               T2R_COUNTDOWN="2", T2R_MAP_VOTE="1", T2R_VOTE_SECS="3", T2R_NEW_TOKENS_PER_10MIN="1000000", T2R_MAX_CONNS="4000", T2R_JIP="1",
               T2R_JIP_MIN_AGE="3", T2R_JIP_MIN_LEFT="60", T2R_JIP_PRE_COUNTDOWN="1", T2R_JIP_REUSE_S="5", T2R_OFFLINE_GRACE="12",
               T2R_PLAYER_DEPART="25", T2R_PRELAUNCH_SILENT="8", T2R_LOAD_TIMEOUT="30", T2R_LOAD_GRACE="10", T2R_ENDED_HOLD="20", T2R_CLAN_GRACE="6",
               T2R_MAX_WAIT="30", T2R_FINAL_WAIT_S="1", T2R_JIP_ACK_MAX="8", T2R_LOG_BURST="100000", T2R_LOG_PER_S="100000", T2R_STATE_GC_S="60",
               T2R_CLAN_EXCUSE_S="30", T2R_LIVE_CLAIM_S="60", T2R_LOG_KEEP="20", PYTHONUNBUFFERED="1")


class Daemon:
    def __init__(self, work, env_extra, accel):
        self.work, self.accel = work, accel
        self.port, self.aport = free_port(), free_port()
        self.env = dict(os.environ)
        self.env.update(SIM_ENV)
        self.env.update(T2R_PORT=str(self.port), T2R_ADMIN_PORT=str(self.aport), T2R_DB=os.path.join(work, "t2r.db"),
                        T2R_LOG_PATH=os.path.join(work, "daemon.log"), FUZZ_ACCEL=str(accel))
        self.env.update(env_extra)
        self.proc = None
        self.secret = ""
        self.starts = 0
        self.t_start = 0.0

    def start(self):
        self.starts += 1
        out = open(os.path.join(self.work, "daemon.stdout.%d.txt" % self.starts), "wb")
        self.proc = subprocess.Popen([sys.executable, os.path.abspath(__file__), "--daemon-child"], env=self.env, stdout=out, stderr=subprocess.STDOUT, cwd=self.work)
        for _ in range(150):
            try:
                socket.create_connection(("127.0.0.1", self.port), timeout=0.5).close(); break
            except OSError:
                if self.proc.poll() is not None:
                    raise RuntimeError("daemon exited at start (see %s)" % self.work)
                time.sleep(0.1)
        else:
            raise RuntimeError("daemon did not listen (see %s)" % self.work)
        for _ in range(60):
            try:
                with open(os.path.join(self.work, "admin-secret.txt")) as f:
                    self.secret = f.read().strip()
                if self.secret and self.get("/sizes"):
                    break
            except OSError:
                pass
            time.sleep(0.1)
        self.t_start = time.time()

    def get(self, path, post=None):
        try:
            c = http.client.HTTPConnection("127.0.0.1", self.aport, timeout=3)
            if post is None:
                c.request("GET", path, headers={"X-Admin-Secret": self.secret})
            else:
                body = json.dumps(post)
                c.request("POST", path, body, headers={"X-Admin-Secret": self.secret, "Content-Type": "application/json", "Content-Length": str(len(body))})
            r = c.getresponse(); d = r.read(); c.close()
            return json.loads(d) if r.status == 200 else None
        except (OSError, ValueError, http.client.HTTPException):
            return None

    def kill(self):
        if self.proc and self.proc.poll() is None:
            self.proc.kill()
        if self.proc:
            try: self.proc.wait(10)
            except subprocess.TimeoutExpired: pass

    def graceful(self):
        self.get("/shutdown", {"minutes": 0, "reason": "fuzz", "restart": False})
        t0 = time.time()
        while time.time() - t0 < 25 and self.proc.poll() is None:
            time.sleep(0.1)
        if self.proc.poll() is None:
            self.kill()
            return False
        return True

    def alive(self):
        return self.proc is not None and self.proc.poll() is None


# ---------------------------------------------------------------------------------------------------------------- fake client
class FC:
    def __init__(self, run, idx):
        self.run, self.idx = run, idx
        self.token, self.name = make_token(idx, run.rnd)
        self.pid = hashlib.sha256(self.token.encode()).hexdigest()[:12]
        self.steamid = STEAM_BASE + idx * 10
        self.bridge = self.sess = None
        self.rb = self.rs = b""
        self.mode = "off"                # off | on | frozen
        self.ui = "off"                  # off menu queue found level playing score
        self.due = {}
        self.rec = None                  # last 0x04 record
        self.load_mode = "fast"
        self.load_at = None
        self.load_sent = False
        self.t_play = None
        self.score_at = None
        self.leave_at = None
        self.give_up_at = None
        self.host_slot = None            # last 0xE7
        self.epoch = 0
        self.mask = 0
        self.e7_state = 0
        self.e7_t = 0.0
        self.mid = None                  # live match (not left, not ended)
        self.mid_any = None              # incl. an ended one
        self.mstate = None
        self.slot = None
        self.dead_t = None               # sim time it stopped polling (freeze / crash / off)
        self.queued_t = None
        self.reports = []                # (t, mid, parts, flags)
        self.ghost = False               # playing in a match the restarted daemon forgot (exempt from playing-vanished)
        self.seq = 0
        self.n_match = 0
        self.vanish_t = None
        self.ejected = None
        self.first_on = True
        self.ghost_q = -1e9

    # ---- plumbing
    def now(self): return self.run.now()

    def conn(self):
        s = socket.create_connection(("127.0.0.1", self.run.d.port), timeout=2)
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
        except (OSError, AttributeError):
            return False

    def ext(self, op, payload, reply=True):
        """one t2r-ext short connection; returns the reply payload (without framing) or None"""
        try:
            s = socket.create_connection(("127.0.0.1", self.run.d.port), timeout=2)
            s.setsockopt(socket.SOL_SOCKET, socket.SO_LINGER, struct.pack("ii", 1, 0))
            s.sendall(msg(op, payload))
            rep = None
            if reply:
                s.settimeout(2.0)
                buf = b""
                while True:
                    fr, buf2 = read_frames(buf)
                    if fr:
                        rep = fr[0][1]; break
                    d = s.recv(4096)
                    if not d: break
                    buf += d
            s.close()
            return rep
        except (OSError, socket.timeout):
            return None

    def name32(self): return self.name.encode().ljust(32, b"\0")[:32]
    def ann(self): return bytes([0x1c]) + b"\0" * 8 + self.name32()

    def register_bridge(self):
        t, nm = self.token.encode(), self.name.encode()
        pl = t + struct.pack("<Q", self.steamid) + bytes([len(nm)]) + nm + struct.pack("<H", 30000 + self.idx)
        try:
            self.bridge = self.conn()
        except OSError:
            self.bridge = None; return
        self.send(self.bridge, msg(0xF0, pl))
        self.send(self.bridge, msg(0xF4, b"sto=%d,ams=%d,waw=%d" % (20 + self.idx * 7, 30 + self.idx * 3, 10 + self.idx)))

    def login(self):
        try:
            self.sess = self.conn()
        except OSError:
            self.sess = None; return False
        login = bytes([0x1c]) + self.token.encode() + b"\x01\x02\x07"
        return self.send(self.sess, msg(0x0f, login) + msg(0x0e, self.ann()))

    # ---- state transitions (called by actions)
    def go_online(self):
        self.close_all()
        self.mode = "on"; self.ui = "menu"; self.dead_t = None; self.queued_t = None
        self.rec = None; self.load_at = self.score_at = self.leave_at = self.give_up_at = None; self.host_slot = None
        self.ghost = False
        self.register_bridge()
        self.login()
        self.due = {"bka": self.now() + 3, "menu": self.now() + 3}
        if self.first_on:
            self.first_on = False
            self.ext(0xE4, self.token.encode() + bytes([1 + (self.idx % 2)]))

    def go_off(self):
        if self.ui in ("queue", "found", "level"):
            self.ghost_q = self.now()               # its queue entry lives on in the daemon for QUEUE_TTL
        self.close_all()
        if self.mode != "off" and self.dead_t is None:
            self.dead_t = self.now()
        self.mode = "off"
        if self.ui in ("menu", "queue", "found", "level"):
            self.ui = "off"
        elif self.ui in ("playing", "score"):
            self.ui = "off"

    def press_queue(self):
        if self.ui != "menu" or self.mode != "on":
            return False
        if self.sess is None and not self.login():
            return False
        if self.send(self.sess, msg(0x01, self.ann())):
            self.ui = "queue"; self.queued_t = self.now(); self.due["qp"] = self.now() + 1.5
            return True
        return False

    def unqueue(self):
        if self.ui != "queue": return False
        self.send(self.sess, msg(0x02)); self.ui = "menu"; self.queued_t = None; return True

    def report(self, flags):
        self.seq += 1
        parts = 100 + (self.idx * 37 + self.seq * 11) % 2900
        self.reports.append((self.now(), self.mid_any, parts, flags))
        self.ext(0xE2, self.token.encode() + struct.pack("<IIB", self.seq, parts, flags))

    def leave(self):
        if self.ui not in ("found", "level", "playing", "score") or self.mode == "off": return False
        if self.ui == "playing":
            self.report(1)
        if self.sess is None: self.login()
        if self.sess: self.send(self.sess, msg(0x02))
        self.ui = "menu"; self.mid = self.mid_any = None; self.t_play = None
        self.load_at = self.score_at = self.leave_at = self.give_up_at = None
        return True

    def send_end(self, winner):
        if self.sess is None and self.ui != "off":
            self.login()
        if self.sess and self.send(self.sess, msg(0x12, bytes([winner]))):
            return True
        return False

    # ---- frames from the daemon
    def on_frame(self, op, pl):
        run, now = self.run, self.now()
        if op == 0x04 and len(pl) >= 0x1b + 0x32:
            n, slot, team, sid, mp = pl[0x18], pl[0x17], pl[0x1a], struct.unpack_from("<I", pl, 0x12)[0], pl[0x16]
            roster = [(pl[0x1b + i * 0x32], pl[0x1b + i * 0x32 + 0x31]) for i in range(n) if len(pl) >= 0x1b + (i + 1) * 0x32]
            self.rec = dict(n=n, slot=slot, team=team, sid=sid, map=mp, roster=roster, t=now)
            run.check_record(self)
            if self.ui in ("menu", "queue"):
                self.ui = "found"; self.n_match += 1; self.load_at = None; self.load_sent = False; self.t_found = now
                self.queued_t = None
        elif op == 0x0c and len(pl) >= 2:
            if pl[0] == 2 and pl[1] == 0 and self.ui == "found":
                self.ui = "level"
                d = {"fast": 0.5 + (self.idx % 3) * 0.7, "slow": 8 + (self.idx % 5) * 3.0, "never": None}[self.load_mode]
                self.load_at = now + d if d is not None else None
                if self.load_mode == "never":
                    self.give_up_at = now + 40 + (self.idx * 13) % 60
        elif op == 0x0a:
            if self.ui in ("level", "found"):
                self.ui = "playing"; self.t_play = now; self.give_up_at = None
        elif op == 0x0d:
            if self.ui in ("found", "level", "playing"):
                self.ejected = (now, "0x0d")
                self.ui = "menu"; self.mid = self.mid_any = None
        elif op == 0x03:
            if self.ui in ("found", "level"):
                self.ui = "queue"; self.queued_t = now; self.load_at = None

    def drain(self):
        for attr, sock in (("rb", self.bridge), ("rs", self.sess)):
            if not sock: continue
            try:
                while select.select([sock], [], [], 0)[0]:
                    d = sock.recv(16384)
                    if not d:
                        self.on_dropped(attr); break
                    setattr(self, attr, getattr(self, attr) + d)
            except OSError:
                self.on_dropped(attr)
        fr, self.rs = read_frames(self.rs)
        for op, pl in fr:
            self.on_frame(op, pl)
        _, self.rb = read_frames(self.rb)

    def on_dropped(self, attr):
        if attr == "rs":
            self.sess = None
            if self.ui in ("queue", "found", "level") and self.mode == "on":
                self.ui = "menu"                       # the session died (daemon restart): back to the menu
        else:
            self.bridge = None

    # ---- ticking
    def tick(self, now):
        if self.mode == "off":
            return
        frozen = self.mode == "frozen"
        if self.bridge is None and self.run.d.alive() and now >= self.due.get("bretry", 0):
            self.due["bretry"] = now + 2
            self.register_bridge(); self.due["bka"] = now + 3
        if self.bridge and now >= self.due.get("bka", 0):
            self.due["bka"] = now + 3
            self.send(self.bridge, msg(0xF3))
        if frozen:
            return
        self.drain()
        t = self.token.encode()
        if self.sess is None and self.ui in ("menu", "queue", "found", "level") and self.run.d.alive() and now >= self.due.get("lretry", 0):
            self.due["lretry"] = now + 2
            self.login()
        if self.ui == "menu":
            if now >= self.due.get("menu", 0) and self.sess:
                self.due["menu"] = now + 3
                self.send(self.sess, msg(0x15))
        elif self.ui == "queue":
            if now >= self.due.get("qp", 0) and self.sess:
                self.due["qp"] = now + 1.5
                self.send(self.sess, msg(0x05))
        elif self.ui in ("found", "level", "playing", "score"):
            if now >= self.due.get("kp", 0) and self.sess:
                self.due["kp"] = now + 3
                self.send(self.sess, msg(0x05))
        if self.ui == "level":
            if self.load_at is not None and now >= self.load_at and not self.load_sent:
                self.load_sent = True
                if self.sess is None: self.login()
                if self.sess: self.send(self.sess, msg(0x09))
            if self.give_up_at and now >= self.give_up_at:
                self.run.note("client %d never loaded: gives up (crash)" % self.idx)
                self.go_off()
        if self.ui in ("playing", "score") and self.mode == "on":
            if now >= self.due.get("e6", 0):
                self.due["e6"] = now + 2
                self.poll_e6(now)
            if now >= self.due.get("e3", 0):
                self.due["e3"] = now + 3
                self.poll_e3(now)
        if self.score_at is not None and now >= self.score_at and self.ui == "playing":
            self.score_at = None
            self.ui = "score"
            self.report(2)
            self.leave_at = now + 8 + (self.idx % 4)
        if self.leave_at is not None and now >= self.leave_at and self.ui == "score":
            self.leave_at = None
            if self.sess is None: self.login()
            if self.sess: self.send(self.sess, msg(0x02))
            self.ui = "menu"; self.mid = self.mid_any = None; self.t_play = None

    def host_dead_view(self, now):
        """does this client's ext hear the host? the model knows who stopped polling (a real ext: no heartbeat from the host peer)"""
        if self.host_slot is None or self.host_slot == 0xFF: return False
        h = self.run.client_at(self.mid_any, self.host_slot)
        if h is None: return True
        if h is self: return False
        if h.mode in ("off", "frozen") and h.dead_t is not None and now - h.dead_t >= 1.5: return True
        return h.ui in ("menu", "queue", "off")

    def poll_e6(self, now):
        flags = 1 if (self.host_dead_view(now) and self.ui == "playing") else 0
        rep = self.ext(0xE6, self.token.encode() + bytes([flags, self.epoch & 0xFF]))
        if rep and len(rep) >= 5:
            self.run.on_e7(self, rep, now)

    def poll_e3(self, now):
        mid = self.mid_any
        t0 = self.run.m_t0.get(mid, self.t_play or now)
        rem = max(0.0, 600.0 - (now - t0))
        pl = self.token.encode() + bytes([1 | (4 if self.n_match and self.rec and self.rec.get("joined") else 0)]) + struct.pack("<ff", rem, 600.0) + bytes([self.idx & 1, 0xFF, 0xFF])
        rep = self.ext(0xE3, pl)
        if rep: self.run.on_e5(self, rep)


# ---------------------------------------------------------------------------------------------------------------- the run
class Violation(Exception):
    def __init__(self, name, detail):
        super().__init__("%s: %s" % (name, detail)); self.name, self.detail = name, detail


class Run:
    def __init__(self, seed, work, nclients=None, accel=5.0, actions=None, steps=200, verbose=False, env_extra=None, match_size=None):
        self.seed, self.work, self.accel, self.verbose = seed, work, accel, verbose
        self.rnd = random.Random(seed * 7919 + 13)
        n0, m0 = self.rnd.randint(2, 12), self.rnd.choice([4, 4, 6, 8])
        self.nclients = nclients or n0
        self.steps = steps
        self.match_size = match_size or m0
        self.cfg = {"T2R_MATCH_SIZE": str(self.match_size), "T2R_ENGINE_SLOTS": "8", "T2R_MAX_TEAM": "0"}
        self.cfg.update(env_extra or {})
        self.d = Daemon(work, self.cfg, accel)
        self.clients = []
        self.t0 = None
        self.actions = actions
        self.done_actions = []
        self.notes = []
        self.m_t0 = {}                   # mid -> sim time of its first GAME-START seen
        self.members_ever = collections.defaultdict(set)   # mid -> {pid}
        self.mid_first = {}              # mid -> sim time first seen
        self.prev = {}                   # mid -> {pid: slot} active in the previous snapshot
        self.sid_of = {}                 # mid -> session id
        self.snap = None
        self.next_check = 0.0
        self.host_dead_since = {}        # mid -> sim time the host client died
        self.epoch_seen = {}             # mid -> (epoch, since)
        self.pending_restart = None      # {"t", "pre": {mid: [pid]}}
        self.sizes0 = None
        self.violation = None
        self.max_thr = 0
        self.stuck_load_notes = set()
        self.pid2c = {}
        self.hist = {}
        self.host_first_seen = {}
        self.ended_first = {}
        self.last_restart_t = -1e9
        self.kills = 0
        self.epoch_first = {}
        self.admin_fail = 0
        self.q_over = 0

    # ---- clock
    def now(self):
        return (time.monotonic() - self.t0) * self.accel

    def note(self, s):
        self.notes.append("%7.1f %s" % (self.now() if self.t0 else 0.0, s))
        if self.verbose: print(self.notes[-1], flush=True)

    def client_at(self, mid, slot):
        """the client at `slot` of match `mid` in the last snapshot; None = not known (the caller treats that as 'no verdict' unless it knows the match)"""
        if mid is None or self.snap is None: return None
        for m in self.snap.get("matches", []):
            if m["id"] == mid:
                pl = m["players"]
                if 0 <= slot < len(pl):
                    return self.pid2c.get(pl[slot]["pid"])
        return None

    def fail(self, name, detail):
        if self.violation is None:
            self.violation = Violation(name, detail)
            self.note("VIOLATION " + name + ": " + detail)
        raise self.violation

    # ---- client-visible reply checks
    def check_record(self, c):
        r = c.rec
        if not (0 <= r["slot"] < r["n"] <= 8):
            self.fail("record-consistent", "client %d got a 0x04 with slot %d of n=%d" % (c.idx, r["slot"], r["n"]))
        if r["team"] != team_of(r["slot"]) and not os.environ.get("T2R_TEST_ONE_TEAM"):
            self.fail("record-consistent", "client %d slot %d got local team %d" % (c.idx, r["slot"], r["team"]))
        for s, tm in r["roster"]:
            if tm != team_of(s):
                self.fail("record-consistent", "client %d roster slot %d has team %d" % (c.idx, s, tm))
        if r["sid"] == 0:
            self.fail("record-consistent", "client %d got session id 0" % c.idx)

    def on_e5(self, c, rep):
        if len(rep) < 2: return
        en, n = rep[0], rep[1]
        if not en: return
        if n > 8 or len(rep) < 2 + n * 0x32:
            self.fail("record-consistent", "0xE5 roster of client %d: n=%d len=%d" % (c.idx, n, len(rep)))
        slots = [rep[2 + i * 0x32] for i in range(n)]
        if len(set(slots)) != len(slots):
            self.fail("record-consistent", "0xE5 roster of client %d lists a slot twice: %s" % (c.idx, slots))
        for i in range(n):
            if rep[2 + i * 0x32 + 0x31] != team_of(slots[i]):
                self.fail("record-consistent", "0xE5 roster of client %d: slot %d team %d" % (c.idx, slots[i], rep[2 + i * 0x32 + 0x31]))

    def on_e7(self, c, rep, now):
        en, host, epoch, mask, state = rep[0], rep[1], rep[2], rep[3], rep[4]
        if not en: return
        prev = (c.host_slot, c.epoch)
        c.host_slot, c.epoch, c.mask, c.e7_state, c.e7_t = host, epoch, mask, state, now
        if host == 0xFF:
            return                                   # a poll for a match the daemon does not know (restart): keep going
        if state == 2 and c.ui == "playing":
            # give up: the host is gone and nobody can host / the match is unknown: winmm ends the match for this client
            self.note("client %d: host migration gave up -> leaves" % c.idx)
            c.leave_at = None
            if c.sess is None: c.login()
            if c.sess: c.send(c.sess, msg(0x02))
            c.report(1)
            c.ui = "menu"; c.mid = c.mid_any = None; c.t_play = None
            return
        first = c.mid_any and epoch > 0 and (c.mid_any, epoch) not in self.epoch_first
        if first:
            self.epoch_first[(c.mid_any, epoch)] = now          # judged when the FIRST client sees the new epoch (= right after the pick)
        if first and prev[0] is not None and prev[0] != 0xFF and epoch > prev[1]:
            h = self.client_at(c.mid_any, host)
            if h is None:
                if self.mplayers(c.mid_any) is not None:
                    self.fail("migration-live", "match %s epoch %d -> host slot %d names nobody (players %s)" % (c.mid_any, epoch, host, self.mplayers(c.mid_any)))
                return
            if h is not c and h.dead_t is not None and now - h.dead_t > 10.0:
                self.fail("migration-live", "match %s epoch %d: new host slot %d = client %d, dead for %.1f s" % (c.mid_any, epoch, host, h.idx, now - h.dead_t))

    def mplayers(self, mid):
        for m in (self.snap or {}).get("matches", []):
            if m["id"] == mid:
                return [(p["name"], "L" if p["left"] else "", "H" if p["host"] else "") for p in m["players"]]
        return None

    # ---- observing + invariants
    def observe(self):
        if not self.d.alive():
            return
        r = self.d.get("/live")
        sz = self.d.get("/sizes")
        if not r or not sz:
            self.note("admin endpoint did not answer")
            self.admin_fail = getattr(self, "admin_fail", 0) + 1
            if self.admin_fail > 6 and self.d.alive():
                self.fail("stuck", "the admin /live did not answer 6 times in a row while the daemon runs (a daemon thread hung?)")
            return
        self.admin_fail = 0
        snap = r.get("live") or {}
        if not snap:
            return
        self.snap = snap
        now = self.now()
        self.pid2c = {c.pid: c for c in self.clients}
        for c in self.clients:
            c.mid = c.mid_any = c.mstate = c.slot = None
        active = collections.defaultdict(list)
        for m in snap["matches"]:
            for i, p in enumerate(m["players"]):
                c = self.pid2c.get(p["pid"])
                if not c: continue
                self.members_ever[m["id"]].add(p["pid"])
                if not p["left"]:
                    if m["state"] != "ended":
                        active[p["pid"]].append(m["id"])
                        c.mid, c.slot = m["id"], i
                    c.mid_any, c.mstate = m["id"], m["state"]
                    if c.slot is None: c.slot = i
            self.mid_first.setdefault(m["id"], now)
            if m["state"] == "running":
                self.m_t0.setdefault(m["id"], now - (m.get("clock") or {}).get("age_s", 0))
        for c in self.clients:
            if c.ui == "playing" and c.mstate == "ended" and c.score_at is None and c.mode == "on":
                c.score_at = now + 1 + (c.idx % 3)     # the scoreboard shows (a result came in, or the daemon ended the match for the last player)
        self.inv_membership(snap, active)
        self.inv_teams(snap, now)
        self.inv_host(snap, now)
        self.inv_clients(snap, now)
        self.inv_stuck(snap, sz, now)
        self.inv_threads(sz)
        self.inv_restart(snap, now)
        for m in snap["matches"]:
            self.prev_update(m)

    def prev_update(self, m):
        self.prev[m["id"]] = {p["pid"]: i for i, p in enumerate(m["players"]) if not p["left"]}
        self.hist.setdefault(m["id"], set()).update(p["pid"] for p in m["players"])

    def inv_membership(self, snap, active):
        for pid, mids in active.items():
            if len(mids) > 1:
                self.fail("single-membership", "player %s (client %d) is active in matches %s" % (pid, self.pid2c[pid].idx, mids))
        queued = {p["pid"] for p in snap["players"] if p.get("queued")}
        for pid in queued:
            if pid in active:
                self.fail("single-membership", "player %s (client %d) is queued AND in match %s" % (pid, self.pid2c[pid].idx, active[pid]))
        pids = [p["pid"] for p in snap["players"]]
        if len(pids) != len(set(pids)):
            self.fail("single-membership", "a player is listed twice in /live players")

    def inv_teams(self, snap, now):
        seen_ids = set()
        for m in snap["matches"]:
            seen_ids.add(m["id"])
            pl = m["players"]
            act = [(i, p) for i, p in enumerate(pl) if not p["left"]]
            cnt = [sum(1 for i, _ in act if i % 2 == k) for k in (0, 1)]
            for i, p in enumerate(pl):
                if p["team"] != team_of(i):
                    self.fail("team-balance", "match %s slot %d reports team %d" % (m["id"], i, p["team"]))
            if len(act) > self.match_size:
                self.fail("team-balance", "match %s has %d active players > MATCH_SIZE %d" % (m["id"], len(act), self.match_size))
            if m["state"] == "loading" and not any(p["left"] for p in pl) and abs(cnt[0] - cnt[1]) > 1 and m["id"] not in self.prev:
                self.fail("team-balance", "formed lobby %s has teams %d v %d" % (m["id"], cnt[0], cnt[1]))
            # a join in progress never joins a strictly larger team
            pv = self.prev.get(m["id"])
            if pv is not None and m["state"] != "ended":
                now_a = {p["pid"]: i for i, p in act}
                fresh = [pid for pid in now_a if pid not in pv and pid not in self.hist.get(m["id"], ())]
                gone = [pid for pid in pv if pid not in now_a]
                arrivals = [pid for pid in now_a if pid not in pv]
                if len(fresh) == 1 and len(arrivals) == 1 and not gone:
                    i = now_a[fresh[0]]
                    before = [sum(1 for s in pv.values() if s % 2 == k) for k in (0, 1)]
                    if before[i % 2] > before[1 - i % 2]:
                        self.fail("team-balance", "join in progress put %s into the larger team %d (%d v %d) of %s" % (fresh[0], i % 2, before[0], before[1], m["id"]))
                    if cnt[i % 2] > cnt[1 - i % 2] + 1 and before[i % 2] <= before[1 - i % 2] and cnt[1 - i % 2] > 0 and len(act) > 2:
                        pass

    def inv_host(self, snap, now):
        for m in snap["matches"]:
            if m["state"] == "ended": continue
            pl = m["players"]
            hosts = [i for i, p in enumerate(pl) if p["host"]]
            if len(hosts) != 1:
                self.fail("one-host", "match %s lists %d hosts: %s" % (m["id"], len(hosts), hosts))
            mid, h = m["id"], hosts[0]
            if m["state"] != "running":
                self.host_dead_since.pop(mid, None); continue
            hc = self.pid2c.get(pl[h]["pid"])
            self.host_first_seen.setdefault((mid, pl[h]["pid"]), now)
            if self.host_dead_since.get(mid, (None,))[0] != pl[h]["pid"]:
                self.host_dead_since.pop(mid, None)
            survivors = [c for c in self.clients if c.mid == mid and c.mode == "on" and c.ui == "playing" and c.slot is not None and c.slot != h]
            hdead = hc is None or hc.mode != "on" or hc.ui not in ("playing", "score")
            if hdead and survivors and not pl[h]["left"]:
                since = self.host_dead_since.setdefault(mid, (pl[h]["pid"], max(hc.dead_t if (hc and hc.dead_t is not None) else now, self.host_first_seen.get((mid, pl[h]["pid"]), 0.0))))[1]
                since = max(since, self.last_restart_t, min((c.t_play or now) for c in survivors))        # (the oldest surviving poller has been polling since its GAME-START)
                if now - since > 24.0:
                    self.fail("one-host", "match %s: host slot %d (client %s) has been dead for %.0f s, %d survivors poll, no migration" % (
                        mid, h, hc.idx if hc else "?", now - since, len(survivors)))
            else:
                self.host_dead_since.pop(mid, None)

    def inv_clients(self, snap, now):
        for c in self.clients:
            if c.ui == "playing" and c.mode == "on" and not c.ghost and c.mid is None and c.mid_any is None:
                c.vanish_t = c.vanish_t or now
                if now - c.vanish_t > 9.0 and c.t_play and now - c.t_play > 4.0:
                    self.fail("playing-vanished", "client %d plays (GAME-START at %.1f) but the daemon has no live match for it for %.1f s (ejected: %s)" % (
                        c.idx, c.t_play, now - c.vanish_t, c.ejected))
            else:
                c.vanish_t = None
        # session id / map of one match agree across its players (after the vote closed)
        by_mid = collections.defaultdict(list)
        for c in self.clients:
            if c.mid and c.rec and c.ui in ("level", "playing") and c.mstate == "running":
                by_mid[c.mid].append(c)
        for mid, cs in by_mid.items():
            sids = {c.rec["sid"] for c in cs}
            maps = {c.rec["map"] for c in cs}
            if len(sids) > 1:
                self.fail("record-consistent", "match %s: players hold different session ids %s" % (mid, sorted(sids)))
            if len(maps) > 1:
                self.fail("record-consistent", "match %s: players hold different maps %s (clients %s)" % (mid, sorted(maps), [(c.idx, c.rec["map"]) for c in cs]))
            for c in cs:
                if c.slot is not None and c.rec["slot"] != c.slot:
                    self.fail("record-consistent", "match %s: client %d holds slot %d in its 0x04 but is listed at %d" % (mid, c.idx, c.rec["slot"], c.slot))
        # host slot of the clients' 0xE7 replies is a live slot
        for c in self.clients:
            if c.ui == "playing" and c.mid and c.host_slot not in (None, 0xFF) and now - c.e7_t < 1.0:
                m = next((m for m in snap["matches"] if m["id"] == c.mid), None)
                if m and c.host_slot >= len(m["players"]):
                    self.fail("one-host", "client %d got 0xE7 host slot %d, match %s has %d slots" % (c.idx, c.host_slot, c.mid, len(m["players"])))

    def inv_stuck(self, snap, sz, now):
        for m in snap["matches"]:
            pl = m["players"]
            cl = [self.pid2c.get(p["pid"]) for p in pl if not p["left"]]
            known = [c for c in cl if c is not None]
            if known and len(known) == len(cl) and all(c.mode != "on" and c.dead_t is not None for c in known):
                last = max(c.dead_t for c in known)
                if now - last > 70.0 and m["state"] != "ended":
                    self.fail("stuck", "match %s (%s) has had only dead players for %.0f s: %s" % (m["id"], m["state"], now - last, [(p["name"], p["left"]) for p in pl]))
            if m["state"] != "ended":
                self.ended_first.pop(m["id"], None)
            if m["state"] == "ended":
                t_end = self.ended_first.setdefault(m["id"], now)
                if now - t_end > 100.0:
                    self.fail("stuck", "ended match %s is still listed %.0f s after its result" % (m["id"], now - t_end))
            if m["state"] == "loading" and m["age_s"] > 25 and m["age_s"] > 0:
                alive = [c for c in cl if c is not None and c.mode == "on" and c.ui in ("level", "found")]
                nl = [c for c in alive if c.load_sent]
                if alive and not nl and len(alive) == len([c for c in cl if c is not None]) and all(c.load_mode == "never" for c in alive) and m["age_s"] > 200:
                    self.fail("stuck", "match %s: nobody ever loads but all keep polling, age %s s (MATCH-ABORT nobody loaded should have ended it)" % (m["id"], m["age_s"]))
        # ghost queue entries: more queued in the daemon than the model can explain
        q_daemon = sz["sizes"].get("MatchMaker.queue", 0)
        poss = 0
        for c in self.clients:
            if c.ui in ("queue", "found", "level") or now - c.ghost_q < 45.0:
                poss += 1
        if q_daemon > poss + 0:
            self.q_over = getattr(self, "q_over", 0) + 1
            if self.q_over > 8:
                self.fail("stuck", "daemon queue holds %d entries, model explains %d" % (q_daemon, poss))
        else:
            self.q_over = 0

    def inv_threads(self, sz):
        self.max_thr = max(self.max_thr, sz["sizes"].get("threads", 0))

    def inv_restart(self, snap, now):
        pr = self.pending_restart
        if not pr: return
        if now - pr["t"] < 14.0:
            return
        by_id = {m["id"]: m for m in snap["matches"]}
        for mid, pids in pr["pre"].items():
            alive = [self.pid2c[p] for p in pids if p in self.pid2c and self.pid2c[p].mode == "on" and self.pid2c[p].ui == "playing"]
            m = by_id.get(mid)
            if m is None and alive:
                self.fail("restart-readopt", "match %s (players %s) ran for >= 14 s before the daemon restart and its %d players still poll, but it was not re-adopted" % (
                    mid, pids, len(alive)))
            if m is not None:
                cur = [p["pid"] for p in m["players"]]
                if cur[:len(pids)] != pids[:len(cur)] and not any(p["left"] for p in m["players"]):
                    self.fail("restart-readopt", "match %s came back with another player order: %s vs %s" % (mid, cur, pids))
        for c in self.clients:
            if c.ui == "playing" and c.mid_any is None:
                c.ghost = True
        self.pending_restart = None

    # ---- actions
    def gen_action(self):
        r, cs = self.rnd, self.clients
        by = lambda ui: [c for c in cs if c.ui == ui and c.mode == "on"]
        playing = by("playing")
        menu, queue = by("menu"), by("queue")
        off = [c for c in cs if c.mode == "off"]
        found, level = by("found"), by("level")
        running = [m for m in (self.snap or {}).get("matches", []) if m["state"] == "running"]
        dt = r.choice([0.2, 0.4, 0.8, 1, 1.5, 2, 3, 4, 6, 9]) if r.random() < 0.92 else r.choice([15, 25])
        w = []
        def add(k, n, f):
            if n > 0 and f: w.append((n, k, f))
        add("online", 6, off)
        add("queue", 10 + (6 if running else 0), menu)
        add("unqueue", 2, queue)
        add("vote", 4, found)
        add("booster", 2, found + level)
        add("loadmode", 3, [c for c in cs if c.ui in ("menu", "queue", "found", "level") and c.mode == "on"])
        add("leave_cd", 2, found + level)
        add("leave", 2, playing)
        add("crash", 3, [c for c in cs if c.mode == "on" and c.ui != "menu"] + ([c for c in menu] if r.random() < 0.3 else []))
        add("freeze", 2, playing)
        add("thaw", 4, [c for c in cs if c.mode == "frozen"])
        hostc = [c for c in playing if c.host_slot is not None and c.slot is not None and c.host_slot == c.slot]
        add("end", 3, hostc)
        add("end_any", 1, playing)
        add("restart", 1 if self.restarts_done < 3 else 0, [True])
        add("idle", 5, [True])
        tot = sum(n for n, _, _ in w)
        x = r.uniform(0, tot)
        for n, k, f in w:
            x -= n
            if x <= 0: break
        c = r.choice(f) if isinstance(f, list) and f and f[0] is not True else None
        a = {"dt": dt, "a": k, "c": c.idx if c else None}
        if k == "vote": a["x"] = r.randint(0, 2)
        if k == "booster": a["x"] = r.randint(1, 7)
        if k == "loadmode": a["x"] = r.choice(["fast", "fast", "fast", "slow", "never"])
        if k in ("end", "end_any"): a["x"] = r.choice([0, 1, 2, 0, 1, 2, 3])
        if k == "restart": a["x"] = r.choice(["kill", "kill", "graceful"])
        return a

    def execute(self, a):
        k, c = a["a"], (self.clients[a["c"]] if a.get("c") is not None and a["c"] < len(self.clients) else None)
        self.note("%s %s %s" % (k, ("c%d" % c.idx) if c else "", a.get("x", "")))
        try:
            if k == "online" and c and c.mode == "off": c.go_online()
            elif k == "queue" and c: c.press_queue()
            elif k == "unqueue" and c: c.unqueue()
            elif k == "vote" and c and c.ui == "found": c.ext(0xEC, c.token.encode() + bytes([a["x"]]))
            elif k == "booster" and c and c.mode == "on": c.ext(0xEE, c.token.encode() + bytes([a["x"]]))
            elif k == "loadmode" and c: c.load_mode = a["x"]
            elif k == "leave_cd" and c and c.ui in ("found", "level"): c.leave()
            elif k == "leave" and c and c.ui == "playing": c.leave()
            elif k == "crash" and c and c.mode != "off": c.go_off()
            elif k == "freeze" and c and c.ui == "playing" and c.mode == "on":
                c.mode = "frozen"; c.dead_t = self.now()
            elif k == "thaw" and c and c.mode == "frozen":
                if self.now() - (c.dead_t or 0) > 20.0 or c.mstate != "running":
                    c.ghost = True                    # timed out of the match by the daemon (PLAYER_DEPART): its game plays on alone
                c.mode = "on"; c.dead_t = None
            elif k in ("end", "end_any") and c and c.ui == "playing" and c.mode == "on":
                if c.send_end(a["x"]):
                    self.note("c%d sent result winner=%d" % (c.idx, a["x"]))
                    for o in self.clients:
                        if o.mid_any is not None and o.mid_any == c.mid_any and o.ui == "playing" and o.score_at is None and o.mode == "on":
                            o.score_at = self.now() + 1 + (o.idx % 3)
            elif k == "restart":
                self.restart_daemon(a.get("x", "kill"))
        except Violation:
            raise
        except Exception as e:  # noqa: BLE001 - a fake-client bug must show, not hide
            self.note("client action error %r" % (e,))
            raise

    restarts_done = 0

    def restart_daemon(self, how):
        now = self.now()
        self.restarts_done += 1
        pre = {}
        for m in (self.snap or {}).get("matches", []):
            if m["state"] == "running" and m["age_s"] >= 16 and not any(p["left"] for p in m["players"]):
                pre[m["id"]] = [p["pid"] for p in m["players"]]
        # let a status-loop pass (live_save every 10 sim s) happen right before the kill: the saved file is current
        if how == "graceful":
            self.d.graceful()
        else:
            self.kills += 1
            self.d.kill()
        self.note("daemon %s; restarting (pre-matches %s)" % (how, list(pre)))
        self.snap = None
        self.d.start()
        self.admin_fail = 0
        self.pending_restart = {"t": self.now(), "pre": pre}
        self.last_restart_t = self.now()
        for c in self.clients:
            if c.mode != "off":
                c.close_all()
                if c.ui in ("queue", "found", "level"): c.ui = "menu"
                c.due.pop("bretry", None); c.due.pop("lretry", None)
        self.prev.clear()

    # ---- main loop
    def advance(self, dt):
        end = self.now() + dt
        while True:
            now = self.now()
            for c in self.clients:
                c.tick(now)
            if now >= self.next_check:
                self.next_check = now + 0.5
                self.observe()
            if self.d.proc.poll() is not None:
                self.fail("log-clean", "the daemon process exited by itself (rc %s)" % self.d.proc.returncode)
            if now >= end:
                return
            time.sleep(0.01)

    def run(self):
        os.makedirs(self.work, exist_ok=True)
        self.d.start()
        self.t0 = time.monotonic()
        sz0 = self.d.get("/sizes")
        self.sizes0 = (sz0 or {}).get("sizes", {}).get("threads", 0)
        self.clients = [FC(self, i) for i in range(self.nclients)]
        try:
            for c in self.clients[: max(2, self.nclients // 2)]:
                c.go_online()
            acts = self.actions
            n = 0
            while True:
                if acts is not None:
                    if n >= len(acts): break
                    a = acts[n]
                else:
                    if n >= self.steps: break
                    a = self.gen_action()
                n += 1
                self.advance(a["dt"])
                self.done_actions.append(a)
                self.execute(a)
            self.advance(1.0)
            self.quiesce()
            self.final_checks()
        except Violation:
            pass
        finally:
            for c in self.clients: c.close_all()
            self.d.kill()
        if self.violation is None:
            try:
                self.log_checks()
            except Violation:
                pass
        return self.violation

    # ---- end of run
    def quiesce(self):
        """every client stops (sockets closed, no polls); the reaper / timers must resolve everything"""
        for c in self.clients:
            if c.mode != "off":
                c.go_off()
        t0 = self.now()
        self.note("quiesce")
        self.advance(90.0)
        r = self.d.get("/live"); sz = self.d.get("/sizes")
        self.snap = None
        if not r or not sz:
            self.fail("stuck", "no /live answer after the quiesce")
        live = r["live"]
        if live.get("matches"):
            self.fail("stuck", "after 90 s without any client: matches left: %s" % [(m["id"], m["state"], m["age_s"], [(p["name"], p["left"]) for p in m["players"]]) for m in live["matches"]])
        if live.get("queue"):
            self.fail("stuck", "after 90 s without any client the queue still holds %d" % len(live["queue"]))
        s = sz["sizes"]
        for k in ("MatchMaker.queue", "MatchMaker.matches", "MatchMaker.departed", "MatchMaker.launched", "MatchMaker.started", "MatchMaker.ended",
                  "MatchMaker.joining", "MatchMaker.clock", "MatchMaker.formed", "MatchMaker.qtime", "HostMigration.matches", "HostMigration.by_token",
                  "Interrogation.matches", "GunLimits.held", "READOPT"):
            if s.get(k):
                self.fail("stuck", "after the quiesce %s still holds %s entries" % (k, s[k]))
        for k in ("VOTES", "MATCH_MAP", "TIMING", "MATCH_P2P", "SID_KEEP", "LOADED", "CD_GOT", "_SILENT", "JIP_STARTED", "CLAN_PENDING", "CLAN_DUE"):
            if s.get(k):
                self.note("FINDING leftover after the quiesce: %s holds %s entries (gc_state clears it later)" % (k, s[k]))
        if self.sizes0 and s.get("threads", 0) < self.sizes0:
            self.fail("log-clean", "thread count dropped to %s (daemon start: %s): a daemon thread died" % (s.get("threads"), self.sizes0))
        if s.get("threads", 0) > (self.sizes0 or 0) + 12:
            self.note("FINDING thread count after the quiesce %s (daemon start %s)" % (s.get("threads"), self.sizes0))

    def final_checks(self):
        pass

    LOG_BAD = re.compile(r"Traceback|THREAD-DIED|HANDLER ERR|MATCHMAKER-ERR|COUNTDOWN-ERR|STATUS-ERR|ADMIN-ERR|jip: ERR|jip: COUNTDOWN-ERR|jip: REPUSH ERR|HOSTMIG ERR|"
                         r"CLAN ERR|NAMES ERR|VOTE ERR|LIVE-SNAPSHOT-ERR|LIVE-STATE re-adopt|LIVE-STATE record skipped|LIVE hm export|LIVE-STATE not saved|"
                         r"MATCH-END ERR|DB-ERR|Exception in thread|Error\b.*line \d+")
    CLAN_LINE = re.compile(r"CLAN day (\S+) mid (\S+) parts (\d+)(?: left)?\s+-> (\{|None)")

    def logs(self):
        out = []
        for fn in sorted(os.listdir(self.work)):
            if fn.startswith("daemon.log") or fn.startswith("daemon.stdout"):
                try:
                    with open(os.path.join(self.work, fn), "r", encoding="utf-8", errors="replace") as f:
                        out.append((fn, f.read()))
                except OSError:
                    pass
        return out

    COV = ("match-formed", "game-start", "jip-join", "jip-start", "match-end", "abort-award", "load-timeout", "cancel", "readopt ", "timeout", "left ",
           "host lost", "planned handover", "reaped", "CLAN day", "jip-timeout", "queue-drop")

    def coverage(self):
        cov = collections.Counter()
        for fn, txt in self.logs():
            for k in self.COV:
                cov[k.strip()] += txt.count("EVT " + k) if k[0].islower() and k not in ("host lost", "planned handover", "CLAN day") else (len(re.findall(r"HOSTMIG \S+ host slot \d+ lost .*-> new host", txt)) if k == "host lost" else txt.count(k))
        return dict(cov)

    def log_checks(self):
        self.cov = self.coverage()
        credited = collections.Counter()
        by_tag = collections.defaultdict(set)
        for fn, txt in self.logs():
            for ln in txt.splitlines():
                if self.LOG_BAD.search(ln) and "START-MATCH" not in ln and "PUSH-PEER" not in ln:
                    self.fail("log-clean", "%s: %s" % (fn, ln.strip()[:300]))
                m = self.CLAN_LINE.search(ln)
                if m and m.group(4) == "{":
                    credited[(m.group(1), m.group(2))] += 1
                    by_tag[m.group(1)].add(m.group(2))
        names = {c.name: c for c in self.clients}
        for (tg, mid), n in credited.items():
            if n > 1:
                self.fail("clan-once", "clan day of %s for match %s credited %d times" % (tg, mid, n))
            c = names.get(tg)
            if c is None:
                continue
            if c.pid not in self.members_ever.get(mid, ()) and mid in self.mid_first:
                self.fail("clan-once", "clan day of %s credited for match %s it was never listed in (members %s)" % (tg, mid, sorted(self.members_ever[mid])))
        # DB: day == credited lines (alive clans)
        import sqlite3
        try:
            db = sqlite3.connect("file:%s?mode=ro" % os.path.join(self.work, "t2r.db").replace("\\", "/"), uri=True, timeout=5)
            for c in self.clients:
                row = db.execute("SELECT day, status FROM clans WHERE token_id=?", ("s:%d" % c.steamid,)).fetchone()
                got = len(by_tag.get(c.name, ()))
                if row is None:
                    if got:
                        self.fail("clan-once", "%s has %d credited days in the log but no clan row" % (c.name, got))
                    continue
                # (a hard kill loses the log lines of the last ~0.5 s: one credited day per kill may be unlogged)
                if not (got <= row[0] <= got + self.kills):
                    self.fail("clan-once", "%s: clans.day = %d but the log credits %d distinct matches %s" % (c.name, row[0], got, sorted(by_tag.get(c.name, ()))))
                reps = len(c.reports)
                if got > reps:
                    self.fail("clan-once", "%s was credited %d days but reported only %d times" % (c.name, got, reps))
            db.close()
        except sqlite3.Error as e:
            self.note("db read failed %r" % (e,))


# ---------------------------------------------------------------------------------------------------------------- shrink + CLI
def run_seed(seed, steps, work_root, accel=5.0, actions=None, verbose=False, nclients=None, keep=False, env_extra=None, match_size=None):
    work = os.path.join(work_root, "s%d-%x" % (seed, secrets.randbits(24)))
    r = Run(seed, work, nclients=nclients, accel=accel, actions=actions, steps=steps, verbose=verbose, env_extra=env_extra, match_size=match_size)
    v = r.run()
    res = dict(seed=seed, ok=v is None, violation=(v.name, v.detail) if v else None, actions=r.done_actions, notes=r.notes, nclients=r.nclients,
               match_size=r.match_size, work=work, max_threads=r.max_thr, matches=len(r.mid_first), restarts=r.restarts_done,
               cfg=r.cfg, cov=getattr(r, "cov", {}))
    if v is None and not keep:
        import shutil
        shutil.rmtree(work, ignore_errors=True)
    return res


def shrink(seed, res, work_root, accel, budget=30, log=print):
    """ddmin over the recorded action list: keep a candidate when the SAME invariant still fails"""
    want = res["violation"][0]
    acts = list(res["actions"])
    nc = res["nclients"]
    tries = [0]
    def fails(sub):
        if tries[0] >= budget: return False
        tries[0] += 1
        r = run_seed(seed, 0, work_root, accel, actions=sub, nclients=nc, match_size=res["match_size"])
        return (not r["ok"]) and r["violation"][0] == want
    n = 2
    while len(acts) >= 2 and tries[0] < budget:
        chunk = max(1, len(acts) // n)
        subs = [acts[i:i + chunk] for i in range(0, len(acts), chunk)]
        reduced = False
        for i in range(len(subs)):
            comp = [a for j, s in enumerate(subs) if j != i for a in s]
            if comp and fails(comp):
                acts = comp; n = max(n - 1, 2); reduced = True; break
        if not reduced:
            if n >= len(acts): break
            n = min(len(acts), n * 2)
    log("shrunk %d -> %d actions in %d replays" % (len(res["actions"]), len(acts), tries[0]))
    return acts


def show(res, shrunk=None):
    print("---- seed %d FAILED: %s: %s" % (res["seed"], *res["violation"]))
    print("clients=%d match_size=%d work=%s" % (res["nclients"], res["match_size"], res["work"]))
    acts = shrunk or res["actions"]
    print("%s action list (%d):" % ("minimal" if shrunk else "full", len(acts)))
    for a in acts[-60:] if not shrunk else acts:
        print("   ", json.dumps(a))
    print("last notes:")
    for n in res["notes"][-25:]:
        print("   ", n)


def parse_seeds(s):
    out = []
    for part in s.split(","):
        if "-" in part:
            a, b = part.split("-"); out += list(range(int(a), int(b) + 1))
        else:
            out.append(int(part))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int)
    ap.add_argument("--seeds", default="")
    ap.add_argument("--steps", type=int, default=200)
    ap.add_argument("--accel", type=float, default=5.0)
    ap.add_argument("-j", type=int, default=1)
    ap.add_argument("--dir", default=os.environ.get("T2R_TEST_TMP") or r"E:\t2tmp_agents\fuzz")
    ap.add_argument("--replay")
    ap.add_argument("--shrink", action="store_true")
    ap.add_argument("--quick", action="store_true")
    ap.add_argument("-v", action="store_true")
    ap.add_argument("--keep", action="store_true", help="keep the work dir of passing runs too")
    ap.add_argument("--out", default="")
    a = ap.parse_args()
    os.makedirs(a.dir, exist_ok=True)
    if a.replay:
        d = json.load(open(a.replay))
        res = run_seed(d["seed"], 0, a.dir, a.accel, actions=d["actions"], verbose=a.v, nclients=d["nclients"], keep=True, match_size=d["match_size"])
        print("replay:", "ok" if res["ok"] else "FAILED %s" % (res["violation"],))
        return 0 if res["ok"] else 1
    if a.quick:
        seeds, steps = [101, 102, 103], 40
    elif a.seeds:
        seeds, steps = parse_seeds(a.seeds), a.steps
    else:
        seeds, steps = [a.seed if a.seed is not None else 1], a.steps
    bad = []
    t0 = time.time()
    def one(sd):
        return run_seed(sd, steps, a.dir, a.accel, verbose=a.v, keep=a.keep)
    results = []
    if a.j <= 1 or len(seeds) == 1:
        for sd in seeds:
            r = one(sd); results.append(r)
            print("seed %d: %s (%d clients, size %d, %d actions, %d matches, %d restarts, %.0fs)" % (sd, "ok" if r["ok"] else "FAIL " + r["violation"][0], r["nclients"], r["match_size"], len(r["actions"]), r["matches"], r["restarts"], time.time() - t0), flush=True)
            if not r["ok"]: bad.append(r)
    else:
        import concurrent.futures as cf
        with cf.ThreadPoolExecutor(max_workers=a.j) as ex:
            futs = {ex.submit(subprocess.run, [sys.executable, os.path.abspath(__file__), "--seed", str(sd), "--steps", str(steps), "--accel", str(a.accel), "--dir", a.dir,
                                                "--out", os.path.join(a.dir, "res-%d.json" % sd)], capture_output=True): sd for sd in seeds}
            for f in cf.as_completed(futs):
                sd = futs[f]
                p = f.result()
                try:
                    r = json.load(open(os.path.join(a.dir, "res-%d.json" % sd)))
                except (OSError, ValueError):
                    r = dict(seed=sd, ok=False, violation=("harness", (p.stdout + p.stderr).decode("utf-8", "replace")[-400:]), actions=[], notes=[], nclients=0, match_size=0, work="")
                print("seed %d: %s" % (sd, "ok" if r["ok"] else "FAIL %s: %s" % tuple(r["violation"])[:2]), flush=True)
                if not r["ok"]: bad.append(r)
                results.append(r)
    if a.out and len(seeds) == 1:
        with open(a.out, "w") as f:
            json.dump({k: v for k, v in results[0].items()}, f)
    if bad and not a.out:
        for r in bad[:3]:
            sh = shrink(r["seed"], r, a.dir, a.accel) if a.shrink and r.get("actions") else None
            show(r, sh)
            fn = os.path.join(a.dir, "fail-%d.json" % r["seed"])
            with open(fn, "w") as f:
                json.dump({"seed": r["seed"], "actions": sh or r["actions"], "nclients": r["nclients"], "match_size": r["match_size"], "violation": r["violation"]}, f)
            print("saved", fn, "(replay: --replay %s)" % fn)
    tot = collections.Counter()
    for r in results:
        tot.update(r.get("cov") or {})
    if tot:
        print("coverage (events over all seeds):", dict(tot))
    print("%d seed(s), %d failed, %.0f s" % (len(seeds), len(bad), time.time() - t0))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
