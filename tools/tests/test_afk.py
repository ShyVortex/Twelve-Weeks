"""Anti-AFK: the ext reports its idle seconds on every 0xE3 clock report ([76] 0xAF [77..78] u16 idle s [79] flags, ext afk.c); at
T2R_AFK_KICK_S (90) the daemon removes the player through the kick path: back to the menu with the AFK text, out of the match like a quit (no win,
left-early clan day), no requeue ticket. Run: python tools/tests/test_afk.py   (no sockets are opened, temp DB)."""
import os, sys, tempfile, time, struct
import sys as _t2s, os as _t2o; _t2s.path.append(_t2o.path.normpath(_t2o.path.join(_t2o.path.dirname(_t2o.path.abspath(__file__)), ".."))); import t2rtmp  # noqa: E402,F401  (temp hygiene: tools/t2rtmp.py)

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
FAILS = []
def check(cond, what):
    print(("ok   " if cond else "FAIL ") + what)
    if not cond: FAILS.append(what)

def tok(name):
    return (name.encode().hex() + "0123456789abcdef" * 8)[:64]
NAMES = ["Alice", "Bob", "Carol", "Dave"]
T = [tok(n) for n in NAMES]
os.environ.update(T2R_HOST="127.0.0.1", T2R_PORT="0", T2R_MATCH_SIZE="8", T2R_ENGINE_SLOTS="8", T2R_MIN_PLAYERS="2", T2R_FILL_RULE="classic",
                  T2R_QUEUE_SETTLE="0", T2R_FILL_WAIT="0", T2R_JIP="1", T2R_MAP_VOTE="0", T2R_P2P="0")
import daemon  # noqa: E402
daemon.DB_PATH = os.path.join(tempfile.mkdtemp(), "daemon.db")
daemon.get_name = lambda t: NAMES[T.index(t)] if t in T else None
LOGS = []
daemon.log = lambda *a, **k: LOGS.append(" ".join(str(x) for x in a))
MM = daemon.MM
check(daemon.AFK_KICK_S == 90.0, "default: removal at 90 s idle")

class FakeConn:
    def __init__(self): self.out = b""
    def sendall(self, b): self.out += b

def running(players, mid, left=400.0, age=300.0):
    for a in ("queue", "seen", "matches", "formed", "settle", "qtime", "departed", "clock", "polled", "joining", "departed_t", "lives", "started_t"):
        getattr(MM, a).clear()
    MM.launched.clear(); MM.ended.clear(); MM.started.clear(); MM.rq.t.clear()
    daemon.MATCH_MAP.clear(); daemon.MATCH_P2P.clear()
    MM.matches[mid] = list(players); MM.launched.add(mid); MM.started.add(mid)
    MM.formed[mid] = time.time() - age - 30; MM.started_t[mid] = time.time() - age
    daemon.MATCH_MAP[frozenset(players)] = daemon.map_pool(players)[0]
    daemon.MATCH_P2P[frozenset(players)] = False
    MM.clock[mid] = (left, 600.0, False, time.time())
    for t in players: daemon.PRES.touch(t, "x")
    LOGS.clear()
    return mid

def e3(t, idle, flags=1, rqcap=True, trailer=True):
    """The ext's 0xE3 clock report with the AFK trailer."""
    pl = t.encode() + bytes([0x11 | (0x20 if rqcap else 0)]) + struct.pack("<ff", 400.0, 600.0) + bytes([0, 20, 20])
    if trailer: pl += bytes([0xAF, idle & 0xff, idle >> 8, flags])
    return daemon.jip_roster_op(pl)

# ---- idle below the limit: nothing
mid = running(T[:4], "a1")
check(e3(T[1], 59) is not None and T[1] not in MM.departed.get(mid, ()), "59 s idle: stays (the ext shows its warning from 60 s)")
check(e3(T[1], 89) is not None and T[1] not in MM.departed.get(mid, ()), "89 s idle: stays")
check(e3(T[1], 0xFFFF) is not None and T[1] not in MM.departed.get(mid, ()), "0xFFFF (unknown / the ext's AFK off): never removed")
check(e3(T[1], 500, trailer=False) is not None and T[1] not in MM.departed.get(mid, ()), "an older ext without the trailer: never removed")
check(T[1] in daemon.RQ_CAP, "flag 0x20 noted (requeue-capable ext)")

# ---- 90 s idle: removed through the kick path, counts as leaving early
conn = FakeConn()
daemon.SESSIONS.register(T[1], conn)
notes = []
daemon.SOCIAL.note = lambda t, kind, who="": notes.append((t, kind, who))
e3(T[1], 90)
check(T[1] in MM.departed.get(mid, ()), "90 s idle: Bob is out of the match")
check(T[1] in MM.departed_vol, "as a voluntary leave (join in progress does not pull him back into it)")
check((T[1], mid) in daemon.AFK_KICKED, "noted once per match")
check(b"no input for 90 seconds (AFK)" in conn.out and conn.out.endswith(daemon.msg(0x0d, b"\x01")), "kick text + 0x0d back to the menu on his session socket")
check(conn.out.find(b"You got kicked from the match") >= 0, "the text starts like the kick text (the ext shows it as the server toast)")
check(any(n[0] == T[1] and n[1] == "kicked" for n in notes), "the kick notice for the notice poll too")
check(daemon.clan_why_deliberate("left: afk (no input for 90 s)") is True, "the clan sees a deliberate leave (left early)")
check(daemon.clan_leave_excuse(T[1], mid, "left: afk (no input for 90 s)") is None, "no excuse mid-match: a left-early day like a quitter")
check(any(l.startswith("afk:") and "removed from the match" in l for l in LOGS), "'afk:' log line")
check(MM.in_match(T[0]) and T[0] not in MM.departed.get(mid, ()), "the others play on")
n0 = len(conn.out)
e3(T[1], 120)
check(len(conn.out) == n0, "a later report of the same player does nothing more")

# ---- the result: no win for the removed player
import sqlite3
with daemon._dblock, daemon.dbc() as c:
    for t in T[:4]: c.execute("INSERT OR IGNORE INTO players(token, name) VALUES(?, ?)", (t, daemon.get_name(t)))
daemon.record_result(MM.matches[mid], 1, skip=set(MM.departed.get(mid, ())), mid=mid)
with daemon._dblock, daemon.dbc() as c:
    w = dict(c.execute("SELECT token, wins FROM players").fetchall())
check(w.get(T[1], 0) == 0 and w.get(T[3], 0) == 1, "team 1 won: Dave gets the win, Bob (removed, same team) does not (%s)" % {daemon.tag(k): v for k, v in w.items()})

# ---- no requeue ticket for the removed player at the match end
for t in T[:4]: daemon.RQ_CAP[t] = time.time()
MM.end(mid)
check(T[1] not in MM.rq.t and T[0] in MM.rq.t, "match end: tickets for the players still in it, none for the AFK one")

# ---- not before the start, not after the end, not while joining
mid = running(T[:4], "a2")
MM.started.discard(mid)
check(not daemon.afk_report(T[2], 120) and T[2] not in MM.departed.get(mid, ()), "not started yet (lobby / loading): never removed")
MM.started.add(mid); MM.ended.add(mid)
check(not daemon.afk_report(T[2], 120), "match over (scoreboard): never removed")
MM.ended.discard(mid); MM.joining[T[2]] = (mid, time.time())
check(not daemon.afk_report(T[2], 120), "a joiner still loading: never removed")
MM.joining.clear()
daemon.AFK_KICK_S = 0
check(not daemon.afk_report(T[2], 500), "T2R_AFK_KICK_S=0: off")
daemon.AFK_KICK_S = 90.0
check(daemon.afk_report(T[2], 91), "and on again: removed at 91 s")

# ---- the admin kick still works the same after the refactor (kick_token)
mid = running(T[:4], "a3")
c2 = FakeConn(); daemon.SESSIONS.register(T[0], c2)
pid = __import__("hashlib").sha256(T[0].encode()).hexdigest()[:12]
r = daemon.admin_kick(pid, "spam")
check(r.get("ok") and "left match a3" in r.get("did", []) and "sent back to the menu" in r["did"], "admin kick: left the running match, back to the menu (%s)" % r)
check(b'Reason: "spam"' in c2.out, "admin kick text with the reason")
check(daemon.clan_leave_excuse(T[0], mid, "admin kick") is not None, "an admin kick stays excused (not the player's choice)")

print("\n%d failure(s)" % len(FAILS) if FAILS else "\nall ok")
sys.exit(1 if FAILS else 0)
