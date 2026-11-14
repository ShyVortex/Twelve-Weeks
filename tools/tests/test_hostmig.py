"""Offline tests for host migration (tools/hostmig.py + the daemon's 0xE6 op and LEAVE handling).
Run: python tools/tests/test_hostmig.py   (plain python, no pytest; never touches tools/t2r.db or
port 7001: the daemon part uses a temp DB and a free localhost port)."""
import os, sys, socket, struct, tempfile, threading, time
import sys as _t2s, os as _t2o; _t2s.path.append(_t2o.path.normpath(_t2o.path.join(_t2o.path.dirname(_t2o.path.abspath(__file__)), ".."))); import t2rtmp  # noqa: E402,F401  (temp hygiene: tools/t2rtmp.py)

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.dirname(HERE)
sys.path.insert(0, TOOLS)
import hostmig  # noqa: E402

FAILS = []
def check(cond, what):
    print(("ok   " if cond else "FAIL ") + what)
    if not cond:
        FAILS.append(what)

def tok(name, n):
    t = (b"T2N:" + name.encode()).hex()
    return (t + "00" * 32)[:40] + ("%024x" % n)

A, B, C, D = tok("Alpha", 1), tok("Bravo", 2), tok("Charlie", 3), tok("Delta", 4)
assert all(len(t) == 64 for t in (A, B, C, D))

class Clock:
    def __init__(self): self.t = 1000.0
    def __call__(self): return self.t
    def adv(self, s): self.t += s

def reply(b):
    return dict(zip(("enabled", "host", "epoch", "alive", "state"), b))

LOG = []
def mk(**kw):
    clk = Clock()
    hm = hostmig.HostMigration(True, now=clk, log=lambda *a: LOG.append(" ".join(map(str, a))), **kw)
    return hm, clk

# ------------------------------------------------------------------ disabled server
hm = hostmig.HostMigration(False)
check(reply(hm.poll(A, 1))["enabled"] == 0, "migration off: reply says disabled")

# ------------------------------------------------------------------ unknown token
hm, clk = mk()
r = reply(hm.poll(A, 0))
check(r["enabled"] == 1 and r["state"] == hostmig.ST_NORMAL and r["alive"] == 0xFF, "no match known for the token (daemon restarted): keep going, never give up")
hm = hostmig.HostMigration(True, unknown_keep_going=False)
check(reply(hm.poll(A, 0))["state"] == hostmig.ST_GIVE_UP, "unknown_keep_going=False keeps the old give-up answer")

# ------------------------------------------------------------------ normal match: nothing happens
hm, clk = mk()
hm.start("m1", [A, B, C, D])
for t in (B, C, D):
    r = reply(hm.poll(t, 0))
check(r == {"enabled": 1, "host": 0, "epoch": 0, "alive": 0b1111, "state": 0}, "running match: host 0, epoch 0, all alive")

# ------------------------------------------------------------------ host moves to the last player left (fd7cb037)
hm, clk = mk()
hm.start("m1", [A, B, C])
for t in (B, C): hm.poll(t, 0)
hm.depart(B)
check(not hm.host_info("m1")["alone"], "two players still in the match: not 'alone'")
hm.depart(A)                                    # the host leaves: only C is left
clk.adv(4.0); hm.poll(C, 0)
hi = hm.host_info("m1")
check(hi["host"] == 2 and hi["epoch"] == 1 and hi["alone"], "host moved to the only player left: host_info says alone (its ext ends the match, no joiner goes in)")

# ------------------------------------------------------------------ host crash, all clients report silence
hm, clk = mk()
hm.start("m1", [A, B, C, D])
for t in (B, C, D): hm.poll(t, 0)              # everyone's ext armed
clk.adv(5)
r = reply(hm.poll(B, 1))
check(r["epoch"] == 0 and r["state"] == hostmig.ST_SUSPECT, "first silence report: suspect, no migration yet")
clk.adv(0.5); hm.poll(C, 1)
clk.adv(0.5); r = reply(hm.poll(D, 1))
check(r["epoch"] == 0 and r["state"] == hostmig.ST_SUSPECT, "all three silent after 1 s: the host's link may still be up - no migration before %.0f s of silence (10-28 hitch)" % hm.min_silent)
for _ in range(int(hm.min_silent / 0.5)):
    clk.adv(0.5)
    for t in (B, C, D): r = reply(hm.poll(t, 1))
check(r["epoch"] == 1, "all three silent for %.0f s (every survivor asked since: picked at once, H1): %r" % (hm.min_silent, r))
clk.adv(hm.collect + 0.1); r = reply(hm.poll(D, 1))
check(r["epoch"] == 1 and r["host"] == 1 and r["alive"] == 0b1110 and r["state"] == 0,
      "all three silent -> host slot 1 (lowest slot, no pings), slot 0 dropped: %r" % r)
r = reply(hm.poll(B, 0, 0))
check(r["epoch"] == 1 and r["host"] == 1, "new host learns it on its next poll")
r = reply(hm.poll(A, 0))
check(r["state"] == hostmig.ST_GIVE_UP, "the old host (if it is still running) is told it is out")

# ------------------------------------------------------------------ host's Steam helper gone + one report
hm, clk = mk()
hm.start("m1", [A, B, C, D])
for t in (B, C, D): hm.poll(t, 0)
hm.bridge_gone(A)
check(reply(hm.poll(C, 0))["epoch"] == 0, "helper gone alone does not migrate (no client hears silence yet)")
clk.adv(4.5)
r = reply(hm.poll(C, 1))
clk.adv(hm.collect + 0.1); r = reply(hm.poll(C, 1))
check(r["epoch"] == 1 and r["host"] in (1, 2), "helper gone + a silence report -> migrated")

# ------------------------------------------------------------------ helper link flap: back before the grace / never counted again
hm, clk = mk()
hm.start("m1", [A, B, C, D])
for t in (B, C, D): hm.poll(t, 0)
hm.bridge_gone(A); clk.adv(1); hm.bridge_back(A)
clk.adv(10)
r = reply(hm.poll(C, 1))
check(r["epoch"] == 0, "helper link flap (back again) + one silence report: the host stays host")
hm, clk = mk()
hm.start("m1", [A, B, C, D])
for t in (B, C, D): hm.poll(t, 0)
hm.bridge_gone(A)
r = reply(hm.poll(C, 1))
check(r["epoch"] == 0, "helper gone < grace + a silence report: not yet")

# ------------------------------------------------------------------ host leaves with op 0x02: immediate
hm, clk = mk()
hm.start("m1", [A, B])
hm.poll(B, 0)
hm.depart(A, "left (0x02)")
r = reply(hm.poll(B, 1))
check(r["epoch"] == 1 and r["host"] == 1 and r["alive"] == 0b10, "1v1 host left -> the other is host, alone")

# ------------------------------------------------------------------ host leaves while nobody polled lately
hm, clk = mk()
hm.start("m1", [A, B, C])
hm.depart(A, "left (0x02)")                    # nobody has polled at all
check(any("waiting for a player to ask" in l for l in LOG), "no candidate yet: waits")
r = reply(hm.poll(C, 1))
check(r["epoch"] == 0, "H1: the first player to ask is NOT made host at once (B may still ask): %r" % r)
r = reply(hm.poll(B, 1))
check(r["epoch"] == 1 and r["host"] == 1, "every survivor has asked -> picked at once (lowest slot, no pings): %r" % r)
r = reply(hm.poll(C, 1))
check(r["epoch"] == 1 and r["host"] == 1, "the other one follows the same host")
hm, clk = mk()
hm.start("m1", [A, B, C])
hm.depart(A, "left (0x02)")
reply(hm.poll(C, 1))
clk.adv(hm.collect + 0.1)
r = reply(hm.poll(C, 1))
check(r["epoch"] == 1 and r["host"] == 2, "only C asks for 3 s: C is host (the silent B cannot block the match): %r" % r)

# ------------------------------------------------------------------ H1: the best-ping survivor wins although another one asked first
pings2 = {(B, C): 250, (B, D): 40, (C, D): 60}
pf2 = lambda a, b: pings2.get((a, b), pings2.get((b, a)))
hm, clk = mk(ping=pf2)
hm.start("m1", [A, B, C, D])
for t in (B, C, D): hm.poll(t, 0)
clk.adv(5)
hm.depart(A, "crash")
clk.adv(0.2); reply(hm.poll(C, 1))              # C (260 / 250 ms to the others) asks first
clk.adv(0.8); reply(hm.poll(D, 1))
check(not hm.host_info("m1")["host"] and hm.host_info("m1")["pending"], "H1: two of three asked: still collecting")
clk.adv(0.5); r = reply(hm.poll(B, 1))
check(r["epoch"] == 1 and r["host"] == 3, "H1: all asked -> D (worst 60 ms) hosts, not the first asker C: %r" % r)
# window expiry with only some asking, picked by tick
hm, clk = mk(ping=pf2)
hm.start("m1", [A, B, C, D])
for t in (B, C, D): hm.poll(t, 0)
clk.adv(5)
hm.depart(A, "crash")
clk.adv(0.2); reply(hm.poll(C, 1)); clk.adv(0.2); reply(hm.poll(D, 1))
clk.adv(2.0); hm.tick()
check(hm.host_info("m1")["pending"], "H1: tick inside the window: still pending")
clk.adv(1.0); hm.tick()
check(hm.host_info("m1")["host"] == 2 and not hm.host_info("m1")["pending"], "H1: tick after the window picks among the candidates that asked (C, D tie on ping: lower slot); the silent B is not waited for")
# old clients: they polled up to 3 s before the loss and cannot answer faster: still candidates, the pick waits the window
hm, clk = mk(ping=pf2)
hm.start("m1", [A, B, C, D])
for t in (B, C, D): hm.poll(t, 0)
clk.adv(0.5)
hm.depart(A, "crash")
check(hm.host_info("m1")["pending"], "H1: old clients (polled < 3 s ago): collected, not picked instantly")
clk.adv(3.1); hm.tick()
check(hm.host_info("m1")["host"] == 3, "H1: after the window the best of the recently polled wins (D)")

# ------------------------------------------------------------------ one client silent, others fine: lone_wait
hm, clk = mk()
hm.start("m1", [A, B, C])
hm.poll(B, 0); hm.poll(C, 0)
hm.poll(B, 1)
for _ in range(10):
    clk.adv(1.0); hm.poll(A, 0); r = reply(hm.poll(B, 1))
check(r["epoch"] == 0, "one client hears silence, the host's ext still polls: no migration (that client's problem)")
for _ in range(7):
    clk.adv(1.0); r = reply(hm.poll(B, 1))
check(r["epoch"] == 1 and r["host"] == 1, "silence for lone_wait and the host's ext quiet too -> host lost (C never answered)")

# ------------------------------------------------------------------ a silent report that recovers
hm, clk = mk()
hm.start("m1", [A, B, C])
hm.poll(B, 0); hm.poll(C, 0)
hm.poll(B, 1)
clk.adv(0.5); r = reply(hm.poll(B, 0))
check(r["state"] == 0 and r["epoch"] == 0, "the host came back for that client: suspicion cleared")

# ------------------------------------------------------------------ ping-based pick
pings = {(B, C): 40, (B, D): 200, (C, D): 60}
pf = lambda a, b: pings.get((a, b), pings.get((b, a)))
hm, clk = mk(ping=pf)
hm.start("m1", [A, B, C, D])
for t in (B, C, D): hm.poll(t, 0)
hm.depart(A, "crash")
r = reply(hm.poll(D, 1))
check(r["host"] == 2, "ping pick: Charlie (worst 60 ms) beats Bravo (200) and Delta (200): %r" % r)

# ------------------------------------------------------------------ second migration
hm, clk = mk()
hm.start("m1", [A, B, C, D])
for t in (B, C, D): hm.poll(t, 0)
hm.depart(A, "left")
hm.poll(B, 1)
check(reply(hm.poll(C, 1))["host"] == 1, "first migration -> slot 1")
hm.depart(B, "left")
r = reply(hm.poll(C, 1, 1))
check(r["epoch"] == 2 and r["host"] == 2 and r["alive"] == 0b1100, "new host leaves too -> slot 2, epoch 2: %r" % r)

# ------------------------------------------------------------------ settling after a migration
hm, clk = mk()
hm.start("m1", [A, B, C])
hm.poll(B, 0); hm.poll(C, 0)
hm.depart(A, "left")
hm.poll(B, 1); hm.poll(C, 1)                    # both learn: host slot 1, epoch 1
clk.adv(1.0); r = reply(hm.poll(C, 1, 1))       # C switched, the new host is not through yet
check(r["epoch"] == 1 and r["state"] == 0, "silence right after a migration is not counted (settle)")
clk.adv(2.5); r = reply(hm.poll(C, 1, 1))
for _ in range(int(hm.min_silent / 0.5) + 1):
    clk.adv(0.5); r = reply(hm.poll(C, 1, 1))
check(r["epoch"] == 2 and r["host"] == 2, "after settle the new host's silence counts again (it never took over)")

# ------------------------------------------------------------------ everybody gone: give up
hm, clk = mk()
hm.start("m1", [A, B])
hm.depart(B, "left")
hm.depart(A, "left")
check(any("nobody left to host" in l for l in LOG), "last player gone: give up")

# ------------------------------------------------------------------ daemon over TCP
tmp = tempfile.mkdtemp()
s = socket.socket(); s.bind(("127.0.0.1", 0)); port = s.getsockname()[1]; s.close()
os.environ.update(T2R_HOST="127.0.0.1", T2R_PORT=str(port), T2R_HOST_MIGRATION="1", T2R_STEAM_ONLY="0")
import daemon  # noqa: E402
daemon.DB_PATH = os.path.join(tmp, "daemon.db")
daemon.LOG_PATH = os.path.join(tmp, "daemon.log")
threading.Thread(target=daemon.tcp_server, daemon=True).start()
time.sleep(0.3)

def frame(op, payload=b""):
    return struct.pack("<H", len(payload) + 1) + bytes([op]) + payload

def frames_of(data):
    out = []
    while len(data) >= 3:
        ln = struct.unpack_from("<H", data)[0]
        out.append((data[2], data[3:2 + ln])); data = data[2 + ln:]
    return out

def poll(t, flags=0, epoch=0):
    c = socket.create_connection(("127.0.0.1", port), timeout=3)
    c.sendall(frame(0xE6, t.encode() + bytes([flags, epoch])))
    data = b""
    while len(data) < 2 or len(data) < 2 + struct.unpack_from("<H", data)[0]:
        b = c.recv(4096)
        if not b: break
        data += b
    c.close()
    (op, pl), = frames_of(data)
    return op, reply(pl)

def session(t):
    """A logged-in session conn (0x0f), like the game's: returns the socket."""
    c = socket.create_connection(("127.0.0.1", port), timeout=3)
    c.sendall(frame(0x0f, bytes([0x1c]) + t.encode() + b"\x01\x00\x07"))
    time.sleep(0.6)
    c.settimeout(0.5)
    try: c.recv(65536)
    except OSError: pass
    return c

players = [A, B, C, D]
mid = "tcpmatch"
with daemon.MM.lock:
    daemon.MM.matches[mid] = list(players)
    daemon.MM.formed[mid] = time.time() - 300
    daemon.MM.launched.add(mid); daemon.MM.started.add(mid)
daemon.LOADED.update(players)
daemon.HM.start(mid, players)                  # what GAME-START does

op, r = poll(B)
check(op == 0xE7 and r["enabled"] == 1 and r["host"] == 0 and r["epoch"] == 0, "TCP 0xE6 -> 0xE7 host 0: %r" % r)
for t in (C, D): poll(t)

sa = session(A)
sa.sendall(frame(0x02))                         # the host quits the match
time.sleep(0.4)
check(daemon.MM.players_of(B) == players, "host left: the match record stays for the others")
check(not daemon.MM.in_match(A), "the host that left can queue again")
poll(D, 1); poll(B, 1)                          # every survivor asks (the ext pulls its ask forward when the host goes quiet)
op, r = poll(C, 1)
check(r["epoch"] == 1 and r["host"] == 1 and r["alive"] == 0b1110, "TCP: migrated to slot 1: %r" % r)
op, r = poll(B, 0, 0)
check(r["host"] == 1 and r["epoch"] == 1, "TCP: slot 1 learns it is the host")

# the old host is gone from the match: a late 0x12 from it is not the result
sa.sendall(frame(0x12, bytes([0])))
time.sleep(0.4)
check(any("MATCH-END ignored" in l for l in list(daemon._q)), "0x12 from the replaced host is ignored")
# the new host ends the match: results + the record goes after the scoreboard
sb = session(B)
sb.sendall(frame(0x12, bytes([1])))
time.sleep(0.4)
check(any("MATCH-END" in l and "winner team 1" in l for l in list(daemon._q)), "new host's 0x12 is the match end")
time.sleep(9.2)
check(daemon.MM.players_of(B) is None and not daemon.HM.has(B), "match + migration record freed after the scoreboard")

# ------------------------------------------------------------------ legacy: migration off keeps old behaviour
daemon.HM.enabled = False
with daemon.MM.lock:
    daemon.MM.matches["legacy"] = [A, B]
    daemon.MM.formed["legacy"] = time.time() - 300
    daemon.MM.launched.add("legacy")
    daemon.MM.started.add("legacy")             # (a running match: a host leaving a match that never started calls it off, prestart_host_lost)
daemon.LOADED.update([A, B])
sa.sendall(frame(0x02))
time.sleep(0.4)
check(daemon.MM.players_of(A) is None and daemon.MM.players_of(B) == [A, B], "migration off: a leave frees the leaver, the others keep their match (no orphaned record)")
op, r = poll(B)
check(r["enabled"] == 0, "migration off: 0xE7 says disabled")

# ------------------------------------------------------------------ default on + abort award safety net
check('"T2R_HOST_MIGRATION", "1") == "1"' in open(os.path.join(TOOLS, "daemon.py"), encoding="utf-8").read(),
      "host migration is ON by default (PT52: it was off, every host leave aborted the match)")
def mk_started(m, pl):
    with daemon.MM.lock:
        daemon.MM.matches[m] = list(pl)
        daemon.MM.formed[m] = time.time() - 300
        daemon.MM.launched.add(m); daemon.MM.started.add(m)
    for t in pl: daemon.CLAN_MATCH[t] = m
# migration ON: the host leaving hands the match over, no abort award
daemon.HM.enabled = True
mk_started("ab_on", [A, B, C]); daemon.HM.start("ab_on", [A, B, C])
daemon.leave_running_match(A, "left (0x02)")
check("ab_on" not in daemon.ABORT_AWARDED and "ab_on" not in daemon.CLAN_ENDED, "migration on: host leave is a hand-over, not an abort")
daemon.HM.end("ab_on")
# migration OFF: host leaves -> the others are awarded as if the match ended
daemon.HM.enabled = False
mk_started("ab_off", [A, B, C])
daemon.CLAN_PENDING[A] = ("ab_off", 40, 0, {}); daemon.CLAN_PENDING[B] = ("ab_off", 30, 0, {})
daemon.leave_running_match(B, "left (0x02)")          # a client leaving is no abort
check("ab_off" not in daemon.ABORT_AWARDED, "a client leaving does not abort the match")
daemon.leave_running_match(A, "left (0x02)")          # the host leaves
check("ab_off" in daemon.ABORT_AWARDED and "ab_off" in daemon.CLAN_ENDED, "host left without migration: abort award ran, clan match marked ended")
check("ab_off" in daemon.MM.ended, "aborted match is marked ended (scoreboard / requeue as after a 0x12)")
check(("%s" % A, "ab_off") in daemon.CLAN_QUITTERS and (B, "ab_off") not in daemon.CLAN_QUITTERS, "only the host that left stays 'left early'")
check(any("ABORT-AWARD" in l for l in list(daemon._q)), "ABORT-AWARD logged")
# the remaining player's report resolves as a normal day (not left early)
daemon.CLAN_MATCH[C] = "ab_off"
got = []
_log = daemon.clan_finalize
daemon.clan_report(C, 25, 0, {})
check(C not in daemon.CLAN_PENDING, "remaining player's clan report resolves at once after the abort (normal day)")
daemon.HM.enabled = True

for c in (sa, sb):
    c.close()

# ------------------------------------------------------------------ join in progress after a migration: a joiner learns the new host
hm, clk = mk()
hm.start("m1", [A, B, C])
for t in (B, C): hm.poll(t, 0)
hm.depart(A, "crashed")                        # host leaves -> migration at once
hi = hm.host_info("m1")
check(hi["host"] != 0 and hi["epoch"] == 1 and not hi["pending"], "host_info: migrated, new host slot %s" % hi["host"])
hm.add_player("m1", D, 3)                      # a joiner
r = reply(hm.poll(D, 0, 0))
check(r["host"] == hi["host"] and r["epoch"] == 1 and r["alive"] >> 3 & 1 and not r["alive"] & 1, "joiner's first poll: new host slot, epoch 1, itself alive, slot 0 gone")
hm.add_player("m1", A, 4)                      # the crashed old host comes back as a client
m = hm.matches["m1"]
check(m["players"][0] == hostmig.placeholder(0) and m["players"][4] == A and 4 not in m["gone"] and 0 in m["gone"], "old host re-added in slot 4, slot 0 a placeholder")
check(hm.host_token(A) is not None and hm.host_token(A) != A, "old host is a client of the migrated host")
# ------------------------------------------------------------------ fuzz seed 249: a stale candidate (asked at the loss, died, 16 s of silence) is not picked
hm, clk = mk()
hm.start("m9", [A, B, C])
for t in (A, B, C): hm.poll(t, 0)
clk.adv(1.0)
hm.depart(A, "crashed")                        # host lost: pending, B and C polled shortly before = candidates
hm.poll(B, 0, 0)                               # B asks, then dies for good
clk.adv(16.0)                                  # nobody polls for 16 s ...
r = reply(hm.poll(C, 0, 0))                    # ... then C (alive) polls
hi = hm.host_info("m9")
check(hi["host"] == 2 and hi["epoch"] == 1, "the stale candidate B is not made host, the live asker C is (host slot %s epoch %s)" % (hi["host"], hi["epoch"]))
# the periodic tick does not pick a stale candidate either: the host stays 'pending' until a live player asks
hm, clk = mk()
hm.start("m10", [A, B, C])
for t in (A, B, C): hm.poll(t, 0)
clk.adv(1.0)
hm.depart(A, "crashed"); hm.poll(B, 0, 0)
clk.adv(16.0); hm.tick()
hi = hm.host_info("m10")
check(hi["pending"] and hi["epoch"] == 0, "tick with only a stale candidate: still pending, nobody picked (pending %s epoch %s)" % (hi["pending"], hi["epoch"]))
hm.poll(C, 0, 0)
hi = hm.host_info("m10")
check(hi["host"] == 2 and hi["epoch"] == 1 and not hi["pending"], "the live player that asks then becomes host")
# ------------------------------------------------------------------ a01884cd: 1v1, a polling host is never replaced off one early report
hm, clk = mk()
hm.start("m11", [A, B])
hm.poll(A, 0); hm.poll(B, 0)
clk.adv(3.0); hm.poll(A, 0)                    # host polls (heartbeat)
r = reply(hm.poll(B, 1))
check(r["epoch"] == 0 and r["state"] == hostmig.ST_SUSPECT, "1v1: one silence report 3 s in -> suspect only")
clk.adv(0.5); hm.poll(A, 0); hm.poll(B, 1)
clk.adv(hm.collect + 0.1); hm.poll(A, 0); r = reply(hm.poll(B, 1))
check(r["epoch"] == 0 and r["host"] == 0 and r["alive"] == 0b11, "1v1: host still polling -> no migration (would leave one player = instant win): %r" % r)
check(any("still polls" in l for l in LOG), "1v1: the refusal is logged")
# same 1v1, host really gone (ext quiet for more than the alive window): migrates as before
clk.adv(10.0); r = reply(hm.poll(B, 1))
clk.adv(hm.collect + 0.1); r = reply(hm.poll(B, 1))
check(r["epoch"] == 1 and r["host"] == 1, "1v1: host stopped polling + silence reports -> migration still happens: %r" % r)
# 3 players, all silent in the first seconds while the host polls: grace; after the grace they may replace it
hm, clk = mk()
hm.start("m12", [A, B, C])
for t in (A, B, C): hm.poll(t, 0)
clk.adv(3.0); hm.poll(A, 0); hm.poll(B, 1); r = reply(hm.poll(C, 1))
clk.adv(hm.collect + 0.1); hm.poll(A, 0); hm.poll(B, 1); r = reply(hm.poll(C, 1))
check(r["epoch"] == 0, "3 players, host polling, first %.0f s: no migration" % hm.START_GRACE)
clk.adv(hm.START_GRACE); hm.poll(A, 0); hm.poll(B, 1); r = reply(hm.poll(C, 1))
for _ in range(int(hm.min_silent / 0.5)):
    clk.adv(0.5); hm.poll(A, 0); hm.poll(B, 1); r = reply(hm.poll(C, 1))
clk.adv(hm.collect + 0.1); hm.poll(A, 0); hm.poll(B, 1); r = reply(hm.poll(C, 1))
check(r["epoch"] == 1 and r["host"] == 1, "3 players all silent after the grace although the host polls: migrates as before: %r" % r)

# ------------------------------------------------------------------ 07a228ac: a 2 s host hitch is no host loss
hm, clk = mk()
hm.start("h1", [A, B, C])
for t in (A, B, C): hm.poll(t, 0)
clk.adv(hm.START_GRACE + 1); hm.poll(A, 0)
clk.adv(2.0)                                    # the host's frame stalls 2.09 s: no host poll, both clients hear silence after 1.5 s
hm.poll(B, 1); r = reply(hm.poll(C, 1))
clk.adv(0.5); hm.poll(B, 1); r = reply(hm.poll(C, 1))
check(r["epoch"] == 0 and r["state"] == hostmig.ST_SUSPECT, "hitch: every client reports silence, host link up: suspect only, no migration: %r" % r)
check(any("waiting until the silence lasts" in l for l in LOG), "hitch: the hold is logged")
clk.adv(0.5); hm.poll(A, 0); hm.poll(B, 0); r = reply(hm.poll(C, 0))
check(r["epoch"] == 0 and r["state"] == hostmig.ST_NORMAL, "hitch over: clients hear the host again, it stays host: %r" % r)
r = reply(hm.poll(A, 0))
check(r["state"] != hostmig.ST_GIVE_UP and r["alive"] == 0b111, "hitch: the host is never told 'give up': %r" % r)
check(hm.replaced_age(A) is None, "hitch: the host was never replaced")
# a longer silence (the host link really is broken although its socket is up) still migrates after min_silent
hm, clk = mk()
hm.start("h2", [A, B, C])
for t in (A, B, C): hm.poll(t, 0)
clk.adv(hm.START_GRACE + 1)
t_first = clk.t
while clk.t - t_first < hm.min_silent - 0.6:
    hm.poll(B, 1); r = reply(hm.poll(C, 1)); clk.adv(0.5)
check(r["epoch"] == 0, "silence just under %.0f s: still the old host" % hm.min_silent)
clk.adv(1.0); hm.poll(B, 1); r = reply(hm.poll(C, 1))
check(r["epoch"] == 1 and r["host"] == 1, "silence past %.0f s from every survivor: migrated: %r" % (hm.min_silent, r))
r = reply(hm.poll(A, 0))
check(r["state"] == hostmig.ST_GIVE_UP and not (r["alive"] & 1), "the replaced host hears 'give up' (its ext leaves the match)")
check(hm.replaced_age(A) is not None and hm.replaced_age(A) < 1.0, "replaced_age: the old host was replaced (and told) just now")
clk.adv(hostmig.REPLACED_EXCUSE_S + 1)
check(hm.replaced_age(A) > hostmig.REPLACED_EXCUSE_S, "replaced_age grows: a leave much later is not excused")
check(hm.replaced_age(B) is None, "replaced_age: None for a player that was never replaced")
# confirmed-dead host link: no min_silent wait
dead = set()
hm, clk = mk(link_alive=lambda t: t not in dead)
hm.start("h3", [A, B, C])
for t in (A, B, C): hm.poll(t, 0)
clk.adv(hm.START_GRACE + 1)
dead.add(A)                                     # its session socket is gone
hm.poll(B, 1); r = reply(hm.poll(C, 1))
check(r["epoch"] == 1 and r["host"] == 1, "host session socket gone + every survivor silent: migrated at once (no %.0f s wait): %r" % (hm.min_silent, r))
hm, clk = mk()
hm.start("h4", [A, B, C])
for t in (A, B, C): hm.poll(t, 0)
clk.adv(hm.START_GRACE + 1)
hm.bridge_gone(A)
hm.poll(B, 1); r = reply(hm.poll(C, 1))
check(r["epoch"] == 1 and r["host"] == 1, "host Steam helper gone + every survivor silent: migrated at once: %r" % r)
hm, clk = mk()
hm.start("h5", [A, B, C])
for t in (B, C): hm.poll(t, 0)
hm.depart(A, "left (0x02)")
check(hm.replaced_age(A) is None, "a host that left itself was not 'replaced' (no excuse from this path)")
# export / import keeps the replaced stamp (daemon restart)
hm, clk = mk()
hm.start("h6", [A, B, C])
for t in (A, B, C): hm.poll(t, 0)
clk.adv(hm.START_GRACE + 1)
for _ in range(int(hm.min_silent / 0.5) + 1):
    clk.adv(0.5); hm.poll(B, 1); hm.poll(C, 1)
rec = hm.export_match("h6")
import json as _json
hm2 = hostmig.HostMigration(True, now=clk, log=lambda *a: None)
hm2.import_match("h6", _json.loads(_json.dumps(rec)))
check(hm2.replaced_age(A) is not None, "replaced stamp survives export/import (JSON string keys)")

# fresh tokens for the daemon cases below (A..D still sit in earlier test matches)
HA, HB, HC, HD = tok("Hotel", 11), tok("India", 12), tok("Juliet", 13), tok("Kilo", 14)
# ------------------------------------------------------------------ daemon: 07a228ac clan excuse for a host replaced by a migration
mk_started("rp1", [HA, HB, HC]); daemon.HM.start("rp1", [HA, HB, HC])
with daemon.HM.lock:
    m = daemon.HM.matches["rp1"]
    m["gone"].add(0); m["host"] = 1; m["epoch"] = 1; m["replaced"] = {0: time.time() - 1}
daemon.leave_running_match(HA, "left (0x02)")
check((HA, "rp1") in daemon.CLAN_EXCUSED, "host replaced by a migration 1 s before leaves (0x02): excused, no left-early penalty")
check(any("CLAN excuse" in l and "replaced as host" in l for l in list(daemon._q)), "excuse logged as 'replaced as host'")
daemon.HM.end("rp1"); daemon.MM.drop("rp1")
mk_started("rp2", [HA, HB, HC]); daemon.HM.start("rp2", [HA, HB, HC])
with daemon.HM.lock:
    m = daemon.HM.matches["rp2"]
    m["gone"].add(0); m["host"] = 1; m["epoch"] = 1; m["replaced"] = {0: time.time() - hostmig.REPLACED_EXCUSE_S - 5}
daemon.CLAN_LAST_DEPART.pop("rp2", None)
daemon.leave_running_match(HA, "left (0x02)")
check((HA, "rp2") not in daemon.CLAN_EXCUSED, "host replaced long before its leave: a normal deliberate leave")
for k in ("rp1", "rp2"):
    daemon.HM.end(k); daemon.MM.drop(k)

# ------------------------------------------------------------------ daemon: a player on an older build leaves (the ext closes the game after the 'u' notice)
HE, HF = tok("Lima", 15), tok("Mike", 16)
_tsave = dict(daemon._target)
daemon._target.update(t=time.time() + 1e6, v="5e5e5e5e")    # a published build (update_target caches 30 s)
_tv = daemon.update_target()
mk_started("up1", [HE, HF]); daemon.HM.start("up1", [HE, HF])
daemon.CLIENT_VERSIONS[HE] = "0ldb01d0"
daemon.leave_running_match(HE, "left (0x02)")
check((HE, "up1") in daemon.CLAN_EXCUSED, "older build than the published one (%s) leaves (0x02): excused" % _tv)
check(any("CLAN excuse" in l and "older build after an update was published" in l for l in list(daemon._q)), "update excuse logged")
daemon.HM.end("up1"); daemon.MM.drop("up1")
mk_started("up2", [HE, HF]); daemon.HM.start("up2", [HE, HF])
daemon.CLIENT_VERSIONS[HE] = _tv
daemon.CLAN_LAST_DEPART.pop("up2", None)
daemon.leave_running_match(HE, "left (0x02)")
check((HE, "up2") not in daemon.CLAN_EXCUSED, "current build leaves (0x02): a normal deliberate leave")
daemon.HM.end("up2"); daemon.MM.drop("up2")
daemon._target.clear(); daemon._target.update(_tsave)

# ------------------------------------------------------------------ daemon: 32804413 host lost during the level load
def mk_loading(m, pl):
    with daemon.MM.lock:
        daemon.MM.matches[m] = list(pl)
        daemon.MM.formed[m] = time.time() - 60
        daemon.MM.launched.add(m)
        daemon.MM.qtime[m] = {t: time.time() - 100 - i for i, t in enumerate(pl)}
for t in (HA, HB, HC, HD):
    with daemon.MM.lock:
        daemon.MM.queue.pop(t, None)
mk_loading("ps1", [HA, HB, HC])
daemon.LOADED.discard(HA); daemon.LOADED.update([HB, HC])
daemon.leave_running_match(HA, "session lost")   # the reaper's 'session socket lost, never came back'
n0 = len(daemon._q)
started = daemon.maybe_game_start(HB)
q = list(daemon._q)[n0:]
check(not started and not any("GAME-START 0x0a" in l for l in q), "host gone before the start: no GAME-START to the survivors")
check(daemon.MM.players_of_mid("ps1") is None and "ps1" not in daemon.MM.started, "the hostless match is called off")
with daemon.MM.lock:
    inq = {t: daemon.MM.queue.get(t) for t in (HA, HB, HC)}
check(inq[HB] is not None and inq[HC] is not None and inq[HA] is None, "survivors back in the queue, the lost host not")
check(inq[HB] is not None and inq[HB] < time.time() - 90, "survivors keep their old queue place (front)")
check(any("MATCH-ABORT host lost before the start" in l for l in q), "logged MATCH-ABORT host lost before the start")
check(HB not in daemon.LOADED and HC not in daemon.LOADED, "survivors' LOADED marks cleared (the next match loads fresh)")
check(not daemon.HM.has(HB), "no host-migration record for the called-off match")
for t in (HA, HB, HC):
    with daemon.MM.lock:
        daemon.MM.queue.pop(t, None)
# a client lost during the load: unchanged (the host starts the rest)
mk_loading("ps2", [HA, HB, HC])
daemon.LOADED.update([HA, HB]); daemon.LOADED.discard(HC)
daemon.leave_running_match(HC, "session lost")
started = daemon.maybe_game_start(HA)
check(started and "ps2" in daemon.MM.started, "a client lost during the load: the others still start (the host is there)")
daemon.HM.end("ps2"); daemon.MM.drop("ps2")
# host backs out (0x02) during the load while the survivors are still loading: called off at once over TCP
mk_loading("ps3", [HA, HB, HC])
daemon.LOADED.discard(HA); daemon.LOADED.discard(HB); daemon.LOADED.discard(HC)
_srv3, sb3 = socket.socketpair()                # HB's session conn (what its matchmaking login registers)
daemon.SESSIONS.register(HB, _srv3)
sha = session(HA)
sha.sendall(frame(0x02))
time.sleep(0.5)
check(daemon.MM.players_of_mid("ps3") is None, "host 0x02 during the load: match called off without waiting for the others' load")
sb3.settimeout(1.0)
data = b""
try:
    while True:
        b = sb3.recv(65536)
        if not b: break
        data += b
except OSError:
    pass
ops = [o for o, _ in frames_of(data)]
check(0x11 in ops and 0x03 in ops, "survivor got the notice (0x11) and the searching frame (0x03): %r" % [hex(o) for o in ops])
sb3.close(); daemon.SESSIONS.unregister(HB, _srv3); _srv3.close()

print("\n%d failure(s)" % len(FAILS))
sys.exit(1 if FAILS else 0)
