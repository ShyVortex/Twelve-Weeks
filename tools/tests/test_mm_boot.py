"""Repro tests for re/mm-boot.md, against the real daemon over TCP (in-process, free localhost port,
temp DB). The client side is a small model of winmm's session socket (FUN_180057960 /
FUN_180057110 / page tick FUN_180063370):
  state 1 connecting, 2 connected, 3 searching, 4 matched, 5 closed;
  op 0x0d -> state 5; op 0x03 -> state 3; recv 0 -> state 5;
  FIND MATCH on a connected socket (state 2) just appends op 0x01 and enters state 3;
  state 5 while searching -> the page quits to the TITLE screen.
 1. FIND MATCH right after the MP-menu announce: never a 0x0d, never the title, stays queued
    while it heartbeats (and the old T2R_ANNOUNCE_CLOSE=1 path reproduces the boot).
 2. Pressing FIND MATCH twice / re-queueing: the lobby list never shows the player itself
    ("Alpha" + "Alpha [T1]") and lists every other player once.
Run: python tools/tests/test_mm_boot.py"""
import os, sys, socket, struct, tempfile, threading, time
import sys as _t2s, os as _t2o; _t2s.path.append(_t2o.path.normpath(_t2o.path.join(_t2o.path.dirname(_t2o.path.abspath(__file__)), ".."))); import t2rtmp  # noqa: E402,F401  (temp hygiene: tools/t2rtmp.py)

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
FAILS = []
def check(cond, what):
    print(("ok   " if cond else "FAIL ") + what)
    if not cond: FAILS.append(what)

s = socket.socket(); s.bind(("127.0.0.1", 0)); port = s.getsockname()[1]; s.close()
os.environ.update(T2R_HOST="127.0.0.1", T2R_PORT=str(port), T2R_MATCH_SIZE="4", T2R_MIN_PLAYERS="2",
                  T2R_QUEUE_SETTLE="0", T2R_FILL_WAIT="999", T2R_STEAM_ONLY="0")
import daemon  # noqa: E402
daemon.DB_PATH = os.path.join(tempfile.mkdtemp(), "daemon.db")
LOGS = []
_log = daemon.log
def log(*a):
    LOGS.append(" ".join(str(x) for x in a)); _log(*a)
daemon.log = log
threading.Thread(target=daemon.tcp_server, daemon=True).start()
threading.Thread(target=daemon.matchmaker_loop, daemon=True).start()
time.sleep(0.3)
MM = daemon.MM

def frame(op, pl=b""):
    return struct.pack("<H", len(pl) + 1) + bytes([op]) + pl

class Client:
    """winmm session socket model."""
    def __init__(self, name):
        self.name = name
        self.token = daemon.make_token(name)
        self.state = 0
        self.searching = False        # DAT_180189bb3
        self.title = False
        self.own = None               # name from op 0x10 (FUN_18002bb10)
        self.lobby = []               # op 0x17 list
        self.ops = []
        self.buf = b""
        self.sock = None
    def _login(self):
        return frame(0x0f, b"\x1c" + self.token.encode() + b"\x01\x00\x07")
    def _sess(self, op):
        body = b"\x1c" + os.urandom(8) + self.name.encode().ljust(32, b"\x00")
        if op == 0x01: body += bytes(26)
        return frame(op, body)
    def announce(self):               # FUN_180056a10: 0x0f + 0x0e, target state 2
        self.sock = socket.create_connection(("127.0.0.1", port), timeout=3)
        self.sock.setblocking(False)
        self.state = 2
        self.sock.sendall(self._login() + self._sess(0x0e))
    def find_match(self):             # FUN_180057110
        self.searching = True
        if self.state in (3, 4): return
        if self.state in (0, 5):      # fresh socket: 0x0f + 0x01
            self.sock = socket.create_connection(("127.0.0.1", port), timeout=3)
            self.sock.setblocking(False)
            self.sock.sendall(self._login() + self._sess(0x01))
        else:                         # connected: only append 0x01 on the same socket
            self.sock.sendall(self._sess(0x01))
        self.state = 3
    def send(self, op):
        if self.state in (2, 3, 4):
            try: self.sock.sendall(frame(op))
            except OSError: self._closed()
    def _closed(self):
        if self.state != 5:
            self.state = 5
            try: self.sock.close()
            except OSError: pass
    def pump(self, secs=0.3):
        end = time.time() + secs
        while time.time() < end and self.state != 5 and self.sock:
            try:
                d = self.sock.recv(65536)
                if not d: self._closed(); break
                self.buf += d
            except BlockingIOError:
                time.sleep(0.02); continue
            except OSError:
                self._closed(); break
            while len(self.buf) >= 2:
                ln = struct.unpack_from("<H", self.buf)[0]
                if len(self.buf) < ln + 2: break
                op, pl = self.buf[2], self.buf[3:2 + ln]; self.buf = self.buf[2 + ln:]
                self.ops.append(op)
                if op == 0x10: self.own = pl.split(b"\x00")[0].decode()
                elif op == 0x03: self.state = 3; self.lobby = []
                elif op == 0x17:
                    n, i, out = pl[0], 1, []
                    for _ in range(n):
                        k = pl[i]; out.append(pl[i + 1:i + 1 + k].decode()); i += 1 + k
                    self.lobby = out
                elif op == 0x0d: self._closed(); break
        if self.state == 5 and self.searching:
            self.title = True             # page tick: state 5 && searching -> FUN_180065480
    def rows(self):
        """What the lobby panel shows (FUN_180065760): row 0 = own name, then the list
        minus the first entry strcmp-equal to the own name."""
        out, skipped = [self.own], False
        for n in self.lobby:
            if not skipped and n == self.own: skipped = True; continue
            out.append(n)
        return out

def reset():
    for a in ("queue", "seen", "matches", "formed", "left", "settle", "qtime", "departed"):
        getattr(MM, a).clear()
    MM.launched.clear(); MM.ended.clear(); MM.last_arrival = 0

# ------------------------------------------------ 1a. old behaviour reproduces the title boot
reset()
daemon.ANNOUNCE_CLOSE = True
a = Client("Oldie")
a.announce()
time.sleep(0.45)                  # past the daemon's 0.3 s join wait: its 0x0d is on the way
a.find_match()                    # pressed while the socket is still connected (state 2)
a.pump(1.0)
check(0x0d in a.ops and a.title, "repro (T2R_ANNOUNCE_CLOSE=1): FIND MATCH right after the announce -> 0x0d -> TITLE")
check(a.token not in MM.queue, "  ...and the daemon does not queue that dead search (no 20 s ghost)")
time.sleep(0.3)
check(any("after 0x0d" in l for l in LOGS), "  ...logged as 'after 0x0d on this conn'")
if not any("after 0x0d" in l for l in LOGS): print("\n".join(l[:160] for l in LOGS[-8:]))

# ------------------------------------------------ 1b. fixed: announce socket held, press works
reset()
daemon.ANNOUNCE_CLOSE = False
MM.QUEUE_TTL = 4.0
for delay in (0.0, 0.1, 0.45, 1.0, 2.9):
    b = Client("Bravo%d" % int(delay * 10))
    b.announce()
    time.sleep(delay)
    b.pump(0.05)
    b.find_match()
    b.pump(0.8)
    check(0x0d not in b.ops and not b.title and b.state == 3 and b.token in MM.queue,
          "press %.2f s after the announce: no 0x0d, still searching (state %d), queued" % (delay, b.state))
    b.sock.close()

reset()
b = Client("Bravo")
b.announce(); b.pump(0.5)
check(b.own == "Bravo" and 0x0d not in b.ops and b.state == 2, "menu announce: 0x10 name, socket stays connected (state 2)")
b.send(0x15); b.pump(0.3)
check(0x16 in b.ops, "held menu socket answers the online-count poll (0x15 -> 0x16)")
b.find_match(); b.pump(0.5)
c = Client("Charlie"); c.find_match(); c.pump(0.5)
drops0 = sum("QUEUE drop" in l for l in LOGS)
t_end = time.time() + 2.5 * MM.QUEUE_TTL         # 10 s of searching, heartbeats every 1.5 s
while time.time() < t_end:
    b.send(0x05); c.send(0x05)
    b.pump(1.5); c.pump(0.01)
check(not b.title and b.state == 3 and b.token in MM.queue and c.token in MM.queue,
      "searching %.0f s (> QUEUE_TTL %.0f s) with heartbeats: both still queued, no title" % (2.5 * MM.QUEUE_TTL, MM.QUEUE_TTL))
check(sum("QUEUE drop" in l for l in LOGS) == drops0, "  no QUEUE drop while the game heartbeats")
c.sock.close(); c.state = 5
time.sleep(MM.QUEUE_TTL + 1.5)
check(c.token not in MM.queue, "a client that really stopped (socket gone, no polls) is still dropped after QUEUE_TTL")

# name changed in game (0xD2) while on the menu: pushed on the held socket
reset()
d = Client("Delta"); d.announce(); d.pump(0.5)
orig = daemon.get_name
daemon.get_name = lambda t: "Delta [WLF]" if t == d.token else orig(t)
d.send(0x05); d.pump(0.4)
daemon.get_name = orig
check(d.own == "Delta [WLF]", "rename reaches the held menu socket (fresh 0x10): own=%r" % d.own)
d.sock.close()

# ------------------------------------------------ 2. no "Alpha" + "Alpha [T1]"
reset()
al = Client("Alpha"); al.announce(); al.pump(0.4)
br = Client("Bravo"); br.announce(); br.pump(0.4)
al.find_match(); al.pump(0.4)
br.find_match(); br.pump(0.4)
al.sock.sendall(al._sess(0x01))           # FIND MATCH again on the same socket (re-queue)
al.pump(0.4)
al.send(0x05); al.pump(0.4)
br.send(0x05); br.pump(0.4)
print("     Alpha sees", al.rows(), " Bravo sees", br.rows())
check(al.rows().count("Alpha") == 1 and not any(r.startswith("Alpha ") for r in al.rows()),
      "Alpha's lobby shows itself once (row 0), no 'Alpha [T1]': %s" % al.rows())
check(sum(r.startswith("Bravo") for r in al.rows()) == 1, "  Bravo listed once for Alpha")
check(sum(r.startswith("Alpha") for r in br.rows()) == 1 and br.rows()[0] == "Bravo"
      and not any(r.startswith("Bravo ") for r in br.rows()), "Bravo's lobby: itself once, Alpha once: %s" % br.rows())
check(list(MM.queue).count(al.token) == 1 and len(MM.queue) == 2, "queue holds Alpha once after the double press")
# re-queue from a fresh socket (backed out, pressed again): still once
al.sock.close(); al.state = 5; al.searching = False; al.title = False
time.sleep(0.2)
al2 = Client("Alpha"); al2.token = al.token
al2.announce(); al2.pump(0.4); al2.find_match(); al2.pump(0.4)
al2.send(0x05); al2.pump(0.4)
check(al2.rows().count("Alpha") == 1 and len(al2.rows()) == 2, "after a re-queue on a new socket: %s" % al2.rows())
# entries that would collide: two queued players with the same shown name stay one line each,
# the same token never twice
lst = daemon.searching_frame(None)
check(lst.count(b"Alpha") == 1 and lst.count(b"Bravo") == 1, "spectator list (no self): each player once")

print("\n%d failure(s)" % len(FAILS))
sys.exit(1 if FAILS else 0)
