"""Offline tests for the matchmaking rework: requeue/settle/ended-match races, teams in the lobby list,
parties (real TCP op 0xDA), 2..8 player balancing, ping-minmax host.
Run: python tools/tests/test_mm.py   (free localhost port, temp DB)."""
import os, sys, socket, struct, tempfile, threading, time
import sys as _t2s, os as _t2o; _t2s.path.append(_t2o.path.normpath(_t2o.path.join(_t2o.path.dirname(_t2o.path.abspath(__file__)), ".."))); import t2rtmp  # noqa: E402,F401  (temp hygiene: tools/t2rtmp.py)

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
FAILS = []
def check(cond, what):
    print(("ok   " if cond else "FAIL ") + what)
    if not cond: FAILS.append(what)

def tok(name):
    return (name.encode().hex() + "0123456789abcdef" * 8)[:64]
NAMES = ["Alice", "Bob", "Carol", "Dave", "Eve", "Frank", "Gina", "Hal"]
T = [tok(n) for n in NAMES]

s = socket.socket(); s.bind(("127.0.0.1", 0)); port = s.getsockname()[1]; s.close()
os.environ.update(T2R_HOST="127.0.0.1", T2R_PORT=str(port), T2R_MATCH_SIZE="8", T2R_ENGINE_SLOTS="8", T2R_MIN_PLAYERS="2",
                  T2R_QUEUE_SETTLE="0", T2R_FILL_WAIT="0", T2R_FILL_RULE="classic")      # (the live default is fast; these cases test classic)
import daemon  # noqa: E402
daemon.DB_PATH = os.path.join(tempfile.mkdtemp(), "daemon.db")
daemon.get_name = lambda t: NAMES[T.index(t)] if t in T else None
threading.Thread(target=daemon.tcp_server, daemon=True).start()
time.sleep(0.3)
for t in T: daemon.PRES.touch(t, "x")
MM = daemon.MM

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
    return data[2], dict(kv.split("=", 1) for kv in data[3:2 + ln].decode().split())

def reset():
    for a in ("queue", "seen", "matches", "formed", "left", "settle", "qtime", "departed"):
        getattr(MM, a).clear()
    MM.launched.clear(); MM.ended.clear(); MM.last_arrival = 0
    daemon.PARTIES.of.clear(); daemon.PARTIES.inv.clear()

def fill(tokens):
    """Queue everyone first, then let the matchmaker decide (like players arriving within one tick)."""
    now = time.time()
    for i, t in enumerate(tokens):
        MM.queue[t] = now + i * 0.001; MM.seen[t] = now; MM.settle[t] = 0
    return MM.try_form()

def teams_of(players):
    return {k: [p for j, p in enumerate(players) if daemon.team_of(j) == k] for k in (0, 1)}

def nm(l): return [NAMES[T.index(x)] for x in l]

# ------------------------------------------------------------ (d) 2..8 balancing + start rules
for n in (2, 4, 6, 8):
    reset()
    fill(T[:n])
    ms = list(MM.matches.values())
    check(len(ms) == 1 and len(ms[0]) == n, "%d queued -> one %dv%d match" % (n, n // 2, n // 2))
    tm = teams_of(ms[0]); check(len(tm[0]) == len(tm[1]) == n // 2, "  balanced teams")
reset()
fill(T[:3])
check([len(m) for m in MM.matches.values()] == [3], "3 queued -> one 2v1 match (uneven teams play); queue=%d" % len(MM.queue))
# wait for a full 4v4 first, then step down one player per FILL_WAIT s without a new arrival
_fw = daemon.FILL_WAIT; daemon.FILL_WAIT = 15.0
reset(); MM.last_arrival = time.time() - daemon.FILL_WAIT * 1.5     # one step: 7 wanted
fill(T[:6])
check(not MM.matches, "6 queued, %.0f s quiet -> still waiting for 7+" % (daemon.FILL_WAIT * 1.5))
MM.last_arrival = time.time() - daemon.FILL_WAIT * 2.5               # two steps: 6 wanted
MM.try_form()
check([len(m) for m in MM.matches.values()] == [6], "6 queued, two steps quiet -> one 3v3")
reset(); MM.last_arrival = time.time() - daemon.FILL_WAIT * 1.5
fill(T[:7])
check([len(m) for m in MM.matches.values()] == [7], "7 queued, one step quiet -> one 3v4")
daemon.FILL_WAIT = _fw
reset()
fill(T)
check(len(MM.matches) == 1 and not MM.queue, "8 queued start at once (MATCH_SIZE)")

# ------------------------------------------------------------ (f) fill rules (re/queue-fill-1019.md): classic = default, fast = opt-in
_save = (daemon.FILL_WAIT, daemon.FILL_RULE, daemon.MAX_WAIT, daemon._FILL_FILE, daemon.PRES_TOKENS)
daemon.FILL_WAIT = 15.0; daemon.MAX_WAIT = 150.0
def aged(n, quiet, oldest=None):
    """n queued; the last arrival `quiet` s ago, the oldest searcher queued `oldest` s ago (default = quiet)."""
    reset(); now = time.time(); daemon.PRES_TOKENS = _save[4]; daemon._fill_cache[0] = 0.0
    for i, t in enumerate(T[:n]):
        MM.queue[t] = now - (oldest if oldest is not None else quiet) + i * 0.001; MM.seen[t] = now; MM.settle[t] = 0
    MM.last_arrival = now - quiet
    MM.try_form()
    return [len(m) for m in MM.matches.values()]
daemon._FILL_FILE = os.path.join(tempfile.mkdtemp(), "fill_rule.txt")     # no file -> env value
daemon.FILL_RULE = "classic"
check(daemon.fill_rule() == "classic", "fill rule defaults to classic")
check(aged(2, 20) == [] and aged(2, 89) == [] and aged(2, 91) == [2], "classic: 2 queued wait 90 s since the last arrival (unchanged)")
daemon.FILL_RULE = "fast"; daemon._fill_cache[0] = 0.0
check(aged(2, 20) == [] and aged(2, 50) == [2], "fast: 2 queued, 6 others online -> still waiting for a fuller lobby at 20 s, formed at 50 s")
check(aged(2, 20, oldest=46) == [2], "fast: oldest searcher waited 46 s (FAST_MAX_WAIT 40) -> forms")
check(aged(2, 80) == [2], "fast: 8 s steps: 2 queued form after 48 s quiet (classic 90 s)")
reset(); now = time.time()
for i, t in enumerate(T[:2]): MM.queue[t] = now - 25 + i * 0.001; MM.seen[t] = now; MM.settle[t] = 0
MM.last_arrival = now - 25; daemon.PRES_TOKENS = lambda: list(T[:2]); MM.try_form()
check([len(m) for m in MM.matches.values()] == [2], "fast: nobody else online -> forms 25 s after the last arrival")
reset(); now = time.time()
for i, t in enumerate(T[:2]): MM.queue[t] = now - 10 + i * 0.001; MM.seen[t] = now; MM.settle[t] = 0
MM.last_arrival = now - 10; MM.try_form()
check(not MM.matches, "fast: nobody else online but only 10 s quiet (< FAST_ALONE 15) -> waits")
reset(); now = time.time()
for i, t in enumerate(T[:4]): MM.queue[t] = now - 25 + i * 0.001; MM.seen[t] = now; MM.settle[t] = 0
MM.last_arrival = now - 25; daemon.PRES_TOKENS = lambda: list(T[:5]); MM.try_form()
check(not MM.matches, "fast: a 5th player is online and could still queue -> 4 queued keep waiting at 25 s")
daemon.PRES_TOKENS = _save[4]
# file switch beats env, re-read without a restart
open(daemon._FILL_FILE, "w").write("classic\n"); daemon._fill_cache[0] = 0.0
check(daemon.fill_rule() == "classic", "fill_rule.txt (classic) overrides env fast")
open(daemon._FILL_FILE, "w").write("fast\n"); daemon._fill_cache[0] = 0.0
check(daemon.fill_rule() == "fast", "fill_rule.txt (fast) is picked up after the cache expires")
os.remove(daemon._FILL_FILE)
daemon.FILL_WAIT, daemon.FILL_RULE, daemon.MAX_WAIT, daemon._FILL_FILE, daemon.PRES_TOKENS = _save
daemon._fill_cache[0] = 0.0

# ------------------------------------------------------------ (c) parties over real TCP
reset()
def party(t, sub, name=b""): return req(0xDA, t.encode() + bytes([sub]) + name)
op, r = party(T[0], 1, b"bob")
check(op == 0xDB and r["ok"] == "1", "Alice invites bob (case-insensitive): " + str(r))
op, r = party(T[1], 0)
check(r["inv"] == "Alice", "Bob sees the invite from Alice")
op, r = party(T[2], 2, b"Alice")
check(r["ok"] == "0", "Carol cannot accept an invite she never got")
op, r = party(T[1], 2, b"Alice")
check(r["ok"] == "1" and r["n"] == "2" and sorted(r["m"].split(",")) == ["Alice", "Bob"], "Bob accepts: party " + str(r))
op, r = party(T[0], 1, b"nobody")
check(r["ok"] == "0", "unknown name refused")
fill([T[2], T[0], T[3], T[1]])    # Carol first: queue order alone would split Alice/Bob
pl = next(iter(MM.matches.values()))
tm = teams_of(pl)
same = any({T[0], T[1]} <= set(v) for v in tm.values())
check(len(MM.matches) == 1 and same and len(tm[0]) == len(tm[1]) == 2, "party Alice+Bob on one team: " + str([nm(v) for v in tm.values()]))
party(T[1], 3)
op, r = party(T[0], 0)
check(r["n"] == "0", "leave dissolves a 2-person party")

reset()
daemon.PARTIES.of.update({T[0]: "p", T[1]: "p", T[2]: "p"})
pl = daemon.team_order(T[:6]); tm = teams_of(pl)
check(any({T[0], T[1], T[2]} <= set(v) for v in tm.values()) and len(tm[0]) == len(tm[1]) == 3, "party of 3 in 6: together, 3v3")
daemon.PARTIES.of.update({T[i]: "q" for i in range(4)})
pl = daemon.team_order(T[:4]); tm = teams_of(pl)
check(len(tm[0]) == len(tm[1]) == 2, "party larger than a team is split: 2v2")

# ------------------------------------------------------------ (e) host = minmax ping
reset()
for a in T[:4]:
    for b in T[:4]:
        if a != b: daemon.PING[(a, b)] = __import__('collections').deque([400], maxlen=5)
for o in (T[0], T[1], T[3]):
    daemon.PING[(T[2], o)] = 30; daemon.PING[(o, T[2])] = 30
pl = daemon.team_order(T[:4])
check(pl[0] == T[2], "host (slot 0) = lowest worst-ping player (Carol): " + nm(pl[:1])[0])
tm = teams_of(pl); check(len(tm[0]) == len(tm[1]) == 2, "  teams still 2v2")
daemon.PING.clear()

# ------------------------------------------------------------ (a) back-out / requeue / stale-match races
reset()
daemon.QUEUE_SETTLE = 5
MM.enqueue(T[0]); MM.enqueue(T[1])
check(not MM.matches, "just-queued players are not matched inside the settle window")
daemon.QUEUE_SETTLE = 0
reset()
MM.enqueue(T[0]); MM.enqueue(T[1])
others = MM.cancel(T[0])
check(others == [T[1]] and T[1] in MM.queue and not MM.matches, "back-out: the other returns to the queue")
reset()
MM.enqueue(T[0]); MM.enqueue(T[1])
mid = next(iter(MM.matches))
MM.end(mid)
check(not MM.in_match(T[0]) and MM.players_of(T[0]) == [T[0], T[1]], "ended match: players may queue, scoreboard data still readable")
mid2, pl2 = MM.enqueue(T[0])
check(mid2 is None and T[0] in MM.queue, "re-queue during the scoreboard hold queues (no stale start)")
MM.enqueue(T[1])
new = [m for m in MM.matches if m != mid]
check(len(new) == 1 and MM.mid_of(T[0]) == new[0], "mid_of prefers the new live match")
MM.drop(mid)
check(mid not in MM.matches and new[0] in MM.matches, "the delayed free drops only the old record")
reset()
now = time.time()
MM.queue[T[0]] = now; MM.seen[T[0]] = now - 14
MM.queue[T[1]] = now; MM.seen[T[1]] = now - 40
MM.try_form()
check(T[0] in MM.queue and T[1] not in MM.queue, "queue heartbeat: 14 s silent still queued, 40 s silent dropped")

# ------------------------------------------------------------ (a2) 0x02 leave sharing a segment with other ops
class FakeConn:
    def __init__(self): self.sent = b""
    def sendall(self, b): self.sent += b
    def settimeout(self, t): pass
def leave_batch(extra_ops):
    """0x02 + extra ops in ONE segment through handle_batch: the 2-player match must be cancelled,
    the other player gets op 0x03 (back to searching) and returns to the queue."""
    reset()
    MM.enqueue(T[0]); MM.enqueue(T[1])
    cb = FakeConn(); daemon.SESSIONS.register(T[1], cb)
    st = {"token": T[0], "name": "Alice", "authed": True, "session": True, "is_bridge": False}
    daemon.handle_batch(FakeConn(), ("t", 1), st, [(0x02, b"")] + [(o, b"") for o in extra_ops])
    daemon.SESSIONS.unregister(T[1], cb)
    return cb.sent
for extra in ([], [0x05], [0x15], [0x05, 0x15]):
    sent = leave_batch(extra)
    msg03 = daemon.msg(0x03)
    check(not MM.matches and T[1] in MM.queue and msg03 in sent,
          "leave in the pre-match flow (0x02 + %s): match cancelled, the other gets 0x03 and re-queues" % [hex(o) for o in extra])

# 0x12 match end + 0x02 leave in ONE segment: the result must be recorded before the leave drops the match
reset()
MM.enqueue(T[0]); MM.enqueue(T[1])
mid_e = MM.mid_of(T[0])
st = {"token": T[0], "name": "Alice", "authed": True, "session": True, "is_bridge": False}
daemon.handle_batch(FakeConn(), ("t", 1), st, [(0x12, bytes([0])), (0x02, b"")])
check(mid_e in daemon.CLAN_ENDED, "0x12 + 0x02 in one batch: the match end is seen (not swallowed by the leave)")
# a client report flagged 'the game ended the match' (bit 0) is a normal day even without the host's 0x12
daemon.CLAN_MATCH[T[2]] = "feedbeef"; daemon.CLAN_ENDED.pop("feedbeef", None)
seen = []
_fin = daemon.clan_finalize
daemon.clan_finalize = lambda t: seen.append(daemon.CLAN_PENDING.get(t))
daemon.clan_report(T[2], 5, 2, {})
daemon.clan_finalize = _fin
check(seen and seen[0] is not None, "report with the match-ended flag resolves at once (no grace wait)")

# ------------------------------------------------------------ (b) teams in the lobby list
reset()
for t in T[:4]:
    MM.queue[t] = time.time(); MM.seen[t] = time.time(); MM.settle[t] = time.time() + 99
fr = daemon.searching_frame()
check(fr.count(b"[T1]") == 2 and fr.count(b"[T2]") == 2, "lobby list labels the teams right away (2 + 2)")

# our own team first, the enemy last - for every viewer, 4 and 5 queued (uneven teams)
import re as _re
for nq in (4, 5):
    reset()
    for t in T[:nq]:
        MM.queue[t] = time.time(); MM.seen[t] = time.time(); MM.settle[t] = time.time() + 99
    ok = True
    for v in T[:nq]:
        marks = _re.findall(rb"\[T([12])\]", daemon.searching_frame(v))
        if b"2" in marks and b"1" in marks[marks.index(b"2"):]:
            ok = False
    check(ok, "queue list of %d: the viewer's team ([T1]) is listed before the enemy ([T2]) for every viewer" % nq)

# a player timed out of a running match (the others play on) and matched again must resolve to the NEW match
reset()
MM.matches["old1"] = [T[0], T[1], T[2]]; MM.formed["old1"] = time.time() - 600; MM.launched.add("old1")
MM.departed["old1"] = {T[0]}
MM.matches["new1"] = [T[0], T[3]]; MM.formed["new1"] = time.time()
check(MM.mid_of(T[0]) == "new1", "timed-out player resolves to the new match, not the old one it left")
check(MM.players_of(T[0]) == [T[0], T[3]], "  its players are the new match's")
check(not MM.countdown_over(T[0]), "  the new match's countdown is not 'over' (no late start into the old world)")

print("\n%d failure(s)" % len(FAILS))
sys.exit(1 if FAILS else 0)
