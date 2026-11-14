"""Admin live team switch: a moved player re-enters its running match on the OTHER team (daemon admin_move_team / MM.move_team).
Run: python tools/tests/test_team_move.py   (no sockets are opened, temp DB)."""
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
NAMES = ["Alice", "Bob", "Carol", "Dave", "Eve", "Frank", "Gina", "Hal", "Ivy"]
T = [tok(n) for n in NAMES]
os.environ.update(T2R_HOST="127.0.0.1", T2R_PORT="0", T2R_MATCH_SIZE="8", T2R_ENGINE_SLOTS="8", T2R_MIN_PLAYERS="2",
                  T2R_QUEUE_SETTLE="0", T2R_FILL_WAIT="0", T2R_JIP="1", T2R_MAP_VOTE="0", T2R_P2P="0")
import daemon  # noqa: E402
daemon.DB_PATH = os.path.join(tempfile.mkdtemp(), "daemon.db")
daemon.get_name = lambda t: NAMES[T.index(t)] if t in T else None
MM = daemon.MM
for t in T: daemon.PRES.touch(t, "x")

def running(players, mid="m1", left=400.0, map_idx=None):
    """A launched + started match whose clock was just reported."""
    for a in ("queue", "seen", "matches", "formed", "settle", "qtime", "departed", "clock", "polled", "joining", "departed_t", "lives", "late_bonus"):
        getattr(MM, a).clear()
    MM.launched.clear(); MM.ended.clear(); MM.started.clear()
    daemon.MATCH_MAP.clear(); daemon.MATCH_P2P.clear(); daemon.SID_KEEP.clear()
    MM.matches[mid] = list(players)
    MM.launched.add(mid); MM.started.add(mid)
    pool = daemon.map_pool(players)
    daemon.MATCH_MAP[frozenset(players)] = pool[0] if map_idx is None else map_idx
    daemon.MATCH_P2P[frozenset(players)] = False
    MM.clock[mid] = (left, 600.0, False, time.time())
    return mid

def search(t):
    now = time.time()
    MM.queue[t] = now; MM.seen[t] = now; MM.settle[t] = 0

# ---- 2v2 (slots 0 2 = team 0, 1 3 = team 1): Dave (slot 3, team 1) is moved to team 0
mid = running(T[:4])
MM.departed.setdefault(mid, set()).add(T[3]); MM.departed_t[T[3]] = time.time()
MM.move_team[T[3]] = (mid, 0, time.time() + 180)
search(T[3]); why = []
r = MM.jip_join(T[3], why)
check(r is not None and r[0] == mid, "moved player re-enters its match (%s)" % why)
check(r and r[1] % 2 == 0, "on the other team: slot %s is even (team 0)" % (r and r[1]))
pl = MM.matches[mid]
check(pl.count(T[3]) == 1, "listed once")
check(pl[3] != T[3] and pl[3] in MM.departed[mid], "its old slot 3 is a gone placeholder")
check(T[3] not in MM.move_team, "the move is used up")
# ---- another running match is not taken while a move is pending
mid = running(T[:4], mid="m2")
MM.matches["m3"] = [T[4], T[5]]; MM.launched.add("m3"); MM.started.add("m3")
daemon.MATCH_MAP[frozenset([T[4], T[5]])] = daemon.map_pool([T[4], T[5]])[0]; daemon.MATCH_P2P[frozenset([T[4], T[5]])] = False
MM.clock["m3"] = (400.0, 600.0, False, time.time())
MM.departed.setdefault("m2", set()).add(T[1]); MM.departed_t[T[1]] = time.time()
MM.move_team[T[1]] = ("m2", 0, time.time() + 180)
search(T[1]); r = MM.jip_join(T[1])
check(r is not None and r[0] == "m2" and r[1] % 2 == 0, "pending move: only its own match, team 0 (%s)" % (r,))
# ---- a returning player (expired / no move) with a ghost slot must not make a 3 v 1
import hostmig
for expired in (False, True):
    ph = hostmig.placeholder(1)
    mid = running([T[0], ph, T[2], T[3], T[4]], mid="m4")
    old = time.time() - 600
    MM.departed["m4"] = {ph, T[2]}; MM.departed_t[ph] = old; MM.departed_t[T[2]] = old
    if expired: MM.move_team[T[2]] = ("m4", 1, time.time() - 5)
    search(T[2]); why = []
    r = MM.jip_join(T[2], why)
    check(r is not None and r[1] % 2 == 1, "returning player joins the smaller team 1 (slot %s) %s" % (r and r[1], why))
    pl = MM.matches["m4"]; dep = MM.departed["m4"]
    cnt = [sum(1 for i, t in enumerate(pl) if t not in dep and i % 2 == k) for k in (0, 1)]
    check(cnt == [2, 2] and pl.count(T[2]) == 1, "2 v 2 live players %s, listed once" % cnt)
# ---- an even match keeps the returning player in its old slot
mid = running(T[:4], mid="m5")
MM.departed["m5"] = {T[2]}; MM.departed_t[T[2]] = time.time() - 600
search(T[2]); r = MM.jip_join(T[2])
check(r is not None and r[1] == 2, "balanced: back into its own slot (%s)" % (r and r[1]))
# ---- in-match swap: the mover's ext polls with flag 0x10 -> its team changes IN the match (no kick, no move ticket)
def poll(t, flags=0x11):
    pl = t.encode() + bytes([flags]) + struct.pack("<ff", 300.0, 600.0) + bytes([0, 5, 5])
    rep = daemon.jip_roster_op(pl)
    ln = rep[0] | rep[1] << 8
    body = rep[3:2 + ln]
    n = body[1]
    ros = {body[2 + i * 0x32]: body[2 + i * 0x32 + 0x31] for i in range(n)}
    tail = body[2 + n * 0x32 + 1:]
    return ros, tail
kicked = []
real_kick = daemon.admin_kick
daemon.admin_kick = lambda pid, move=False: kicked.append(pid) or {"ok": True}
daemon.TEAM_SWAP.clear(); daemon.TS_CAP.clear(); MM.move_team.clear()
mid = running(T[:4], mid="s1")
for t in T[:4]: poll(t)                                   # every ext in the match polled once with the capability bit
r = daemon.admin_move_team(daemon._pid_of(T[3]))
check(r.get("ok") and r.get("mode") == "in-match" and r.get("to_team") == 0, "in-match swap accepted (%s)" % r)
check(not kicked and T[3] not in MM.move_team, "no kick, no move ticket")
check(MM.matches["s1"][3] == T[3] and T[3] not in MM.departed.get("s1", ()), "the mover keeps its slot 3, still in the match")
ros, tail = poll(T[0])
check(ros.get(3) == 0 and ros.get(1) == 1 and ros.get(0) == 0, "0xE5 roster: slot 3 now team 0 (%s)" % ros)
check(tail == bytes([0xA7, 1, 3, 0]), "swap block for a capable ext: [A7][1][slot 3 team 0] (%s)" % tail.hex())
ros_old, tail_old = poll(T[1], flags=0x01)
check(ros_old.get(3) == 0 and tail_old == b"", "older ext (no 0x10): new team in the roster, NO trailing block (its buffer is exact)")
check(daemon.team_in("s1", 3) == 0 and daemon.team_in("s1", 1) == 1, "team_in: swapped slot 3 = 0, slot 1 = 1")
with daemon.dbc() as c:
    for t in T[:4]: c.execute("INSERT OR IGNORE INTO players(token,name,matches,last_seen) VALUES(?,?,1,0)", (t, "x"))
daemon.record_result(MM.matches["s1"], 0, mid="s1")
with daemon.dbc() as c:
    w = dict(c.execute("SELECT token, wins FROM players").fetchall())
check(w.get(T[3]) == 1 and not w.get(T[1]), "result booked by the swapped team (mover wins with team 0): %s" % [w.get(t) for t in T[:4]])
MM.departed.setdefault("s1", set())
search(T[4]); why = []
r = MM.jip_join(T[4], why)
check(r is not None and r[1] % 2 == 1, "joiner balances the SWAPPED teams (3 v 1 -> team 1, slot %s) %s" % (r and r[1], why))
r = daemon.admin_move_team(daemon._pid_of(T[3]))
ros, tail = poll(T[0])
check(r.get("mode") == "in-match" and ros.get(3) == 1 and tail == bytes([0xA7, 1, 3, 1]), "moved back: slot 3 team 1, still listed (%s)" % tail.hex())
r = daemon.admin_move_team(daemon._pid_of(T[0]))
check(r.get("ok") and r.get("mode") == "in-match" and r.get("to_team") == 1, "host moved in the match (%s)" % r)
ros, _ = poll(T[2])
check(ros.get(0) == 1, "host slot 0 now team 1 in the roster")
rec = daemon.match_start_frame(T[0], MM.matches["s1"])
check(rec[3 + 0x1a] == 1 and rec[3 + 0x1b + 0x31] == 1, "0x04 match record: own team + roster entry use the swap")
daemon.TS_CAP.clear(); daemon.TEAM_SWAP.clear(); kicked.clear()
mid = running(T[:4], mid="s2")
r = daemon.admin_move_team(daemon._pid_of(T[1]))
check(r.get("ok") and r.get("mode") == "rejoin" and kicked and MM.move_team.get(T[1], (None,))[0] == "s2", "old ext: kick + rejoin ticket (%s)" % r)
r = daemon.admin_move_team(daemon._pid_of(T[0]))
check(not r.get("ok") and "too old" in r.get("error", ""), "old host: refused with a reason (%s)" % r.get("error"))
daemon.admin_kick = real_kick
# ---- auto balance: every AUTO_BALANCE_S, a difference of 2+ players is evened out in the match; 1 is never touched
def balance(players, mid, cap=True):
    running(players, mid=mid)
    daemon.TEAM_SWAP.clear(); daemon.TS_CAP.clear(); daemon.AB_NEXT.clear(); MM.joining.clear()
    if cap:
        for t in players: daemon.TS_CAP[t] = time.time()
    daemon.AB_NEXT[mid] = time.time() - 1                 # its 1.5 min check is due
    daemon.auto_balance_tick()
    return daemon.team_counts_in(mid, MM.matches[mid], set(MM.departed.get(mid, ())))
ph = hostmig.placeholder
check(balance([T[0], ph(1), T[2], ph(3), T[4]], "b1") == [2, 1], "3 v 0 (gone slots) -> 2 v 1")
check(balance([T[0], T[1], T[2], ph(3), T[4]], "b2") == [2, 2], "3 v 1 -> 2 v 2")
sw = daemon.TEAM_SWAP.get("b2", {})
check(list(sw) == [T[4]] and T[0] not in sw, "3 v 1: the newest arrival (slot 4) moved, never the host (%s)" % [daemon.tag(t) for t in sw])
check(balance([T[0], T[1], T[2]], "b3") == [2, 1] and not daemon.TEAM_SWAP.get("b3"), "2 v 1 untouched")
check(balance([T[0], T[1], T[2], T[3], T[4]], "b4") == [3, 2] and not daemon.TEAM_SWAP.get("b4"), "3 v 2 untouched")
check(balance([T[0], T[1], T[2], T[3], T[4], T[5], T[6]], "b5") == [4, 3] and not daemon.TEAM_SWAP.get("b5"), "4 v 3 untouched")
check(balance([T[0], ph(1), T[2], ph(3), T[4], ph(5), T[6]], "b6") == [2, 2], "4 v 0 -> 2 v 2 (two moves)")
check(balance([T[0], T[1], T[2], ph(3), T[4]], "b7", cap=False) == [3, 1] and not daemon.TEAM_SWAP.get("b7"), "older exts: nobody kicked / moved for balance")
running([T[0], T[1], T[2], ph(3), T[4]], mid="b8")
daemon.TEAM_SWAP.clear(); daemon.AB_NEXT.clear()
for t in T[:5]: daemon.TS_CAP[t] = time.time()
daemon.auto_balance_tick()
check(daemon.AB_NEXT.get("b8", 0) > time.time() + 80 and not daemon.TEAM_SWAP.get("b8"), "a new match: first check only after 90 s")
MM.joining[T[5]] = ("b9", time.time())
running([T[0], T[1], T[2], ph(3), T[4]], mid="b9"); MM.joining[T[5]] = ("b9", time.time())
daemon.TEAM_SWAP.clear(); daemon.AB_NEXT.clear(); daemon.AB_NEXT["b9"] = time.time() - 1
daemon.auto_balance_tick()
check(not daemon.TEAM_SWAP.get("b9"), "a joiner loading into the match: no balance move yet")
MM.joining.clear()
print("\n%d failure(s)" % len(FAILS))
sys.exit(1 if FAILS else 0)
