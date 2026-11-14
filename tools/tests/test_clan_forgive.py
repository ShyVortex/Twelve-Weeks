"""Live matches survive a daemon restart (re/premortem-matchmaking.md H3): offline tests, plain python, temp DB, no sockets.
Run: python tools/tests/test_live_restart.py"""
import os, sys, tempfile, time, json, struct
import sys as _t2s, os as _t2o; _t2s.path.append(_t2o.path.normpath(_t2o.path.join(_t2o.path.dirname(_t2o.path.abspath(__file__)), ".."))); import t2rtmp  # noqa: E402,F401  (temp hygiene: tools/t2rtmp.py)

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
FAILS = []
def check(cond, what):
    print(("ok   " if cond else "FAIL ") + what)
    if not cond: FAILS.append(what)

def tok(name):
    return (name.encode().hex() + "0123456789abcdef" * 8)[:64]
NAMES = ["Alice", "Bob", "Carol", "Dave", "Eve", "Frank"]
T = [tok(n) for n in NAMES]

os.environ.update(T2R_HOST="127.0.0.1", T2R_PORT="0", T2R_MATCH_SIZE="8", T2R_ENGINE_SLOTS="8", T2R_MIN_PLAYERS="2",
                  T2R_FILL_WAIT="0", T2R_P2P="0", T2R_HOST_MIGRATION="1", T2R_LIVE_STATE="1")
import daemon  # noqa: E402
daemon.DB_PATH = os.path.join(tempfile.mkdtemp(), "daemon.db")
daemon.get_name = lambda t: NAMES[T.index(t)] if t in T else None
daemon.tag = lambda t: NAMES[T.index(t)] if t in T else t[:6]
daemon.evt = lambda *a, **k: None
MM, HM, GL = daemon.MM, daemon.HM, daemon.GL
HM.collect = 0.3
with daemon._dblock, daemon.db() as c:
    for t in T:
        c.execute("INSERT OR IGNORE INTO players(token,name,matches,wins,draws,last_seen) VALUES(?,?,1,0,0,?)", (t, "x", time.time()))
LIVE = daemon.live_path()

def wipe(file_too=False):
    """What a daemon restart does to memory."""
    for a in ("queue", "seen", "matches", "formed", "left", "settle", "qtime", "departed", "departed_t", "clock", "polled", "joining",
              "lives", "late_bonus", "late_mult", "started_t"):
        getattr(MM, a).clear()
    MM.launched.clear(); MM.ended.clear(); MM.started.clear(); MM.departed_vol.clear(); MM.timed_out.clear(); MM.ended_at.clear()
    HM.matches.clear(); HM.by_token.clear(); GL.held.clear(); GL.want.clear(); daemon.INT.matches.clear(); daemon.INT.by_token.clear()
    for d in (daemon.CLAN_MATCH, daemon.CLAN_ENDED, daemon.CLAN_PENDING, daemon.CLAN_DUE, daemon.MATCH_MAP, daemon.MATCH_P2P, daemon.SID_KEEP,
              daemon.LOADED_T):
        d.clear()
    daemon.RESULT_BOOKED.clear(); daemon.END_BY_REPORTS.clear(); daemon.CLAN_REPORTED_END.clear()      # (the test reuses one match id across restarts)
    daemon.CLAN_QUITTERS.clear(); daemon.CLAN_EXCUSED.clear(); daemon.LOADED.clear(); daemon.READOPT.clear()
    with daemon.PRES.lock: daemon.PRES.players.clear()
    if file_too and os.path.exists(LIVE): os.remove(LIVE)

def start_match(mid, players, map_idx=3):
    """A started match the way maybe_game_start leaves it."""
    now = time.time()
    with MM.lock:
        MM.matches[mid] = list(players); MM.formed[mid] = now - 120; MM.launched.add(mid); MM.started.add(mid); MM.started_t[mid] = now - 100
        MM.qtime[mid] = {}
    daemon.MATCH_MAP[frozenset(players)] = map_idx; daemon.MATCH_P2P[frozenset(players)] = True
    HM.start(mid, players)
    for t in players:
        daemon.CLAN_MATCH[t] = mid; daemon.LOADED.add(t); daemon.PRES.touch(t, "x")

def e3(t, rem=500.0, dur=900.0):
    return bytes.fromhex("") + t.encode("latin1") + bytes([1]) + struct.pack("<ff", rem, dur)

def poll(t, flags=0, epoch=0):
    r = HM.poll(t, flags, epoch)
    return {"enabled": r[0], "host": r[1], "epoch": r[2], "alive": r[3], "state": r[4]}


def last(t):
    st = daemon.clan_state(t)
    try: r = json.loads(st.get("last_result") or "{}")
    except ValueError: r = {}
    return st, r

def reset():
    wipe(True)
    for d in (daemon.CLAN_DONE, daemon.CLAN_CREDITED, daemon.RESTORED_T, daemon.SESS_LOST, daemon.CLAN_LAST_DEPART, daemon.CLAN_EXCUSE_WHY, daemon.CLAN_REJOINED, daemon.CLAN_LEFT_AT):
        d.clear() if hasattr(d, "clear") else None
    daemon.CLAN_CREDITED.clear()

def play(mid, players, started_ago=300.0, rem=500.0):
    start_match(mid, players)
    with MM.lock:
        MM.started_t[mid] = time.time() - started_ago
        MM.clock[mid] = (rem, 900.0, False, time.time())
    for t in players:
        daemon.clan_side(t, 1)

def leave_and_report(t, why, parts, flags=0, mid=None):
    daemon.leave_running_match(t, why)
    daemon.CLAN_MATCH[t] = mid
    daemon.clan_report(t, parts, flags)
    daemon.clan_finalize(t)

PL = T[:4]
# (1) game crash: the session socket is lost and never comes back
reset(); play("c1", PL)
d0 = daemon.clan_state(PL[0])["day"]
leave_and_report(PL[0], "session lost", 400, mid="c1")
st, r = last(PL[0])
check((PL[0], "c1") in daemon.CLAN_EXCUSED and st["day"] - d0 == 1 and not r.get("left"), "crash (session lost): excused, parts count, normal day, no left-early")
check("crash" in daemon.CLAN_EXCUSE_WHY.get((PL[0], "c1"), ""), "crash: the reason is logged as a crash")

# (2) timeout (no packets from the player / host never reachable)
reset(); play("c2", PL)
leave_and_report(PL[1], "timed out", 250, mid="c2")
st, r = last(PL[1])
check((PL[1], "c2") in daemon.CLAN_EXCUSED and not r.get("left") and r.get("parts") == 250, "timeout: excused, parts 250 booked as a normal day")

# (3) never loaded: nothing earned = no day, no penalty
reset(); play("c3", PL)
d0 = daemon.clan_state(PL[2])["day"]
leave_and_report(PL[2], "never loaded", 0, mid="c3")
check(daemon.clan_state(PL[2])["day"] == d0 and (PL[2], "c3") in daemon.CLAN_EXCUSED, "never loaded: excused, no clan day at all")
reset(); play("c3b", PL)
leave_and_report(PL[2], "jip never loaded", 0, mid="c3b")
check(daemon.clan_state(PL[2])["day"] == d0 and (PL[2], "c3b") in daemon.CLAN_EXCUSED, "jip never loaded: excused")

# (4) a deliberate quit mid-round counts as left early (supplies 0)
reset(); play("c4", PL)
leave_and_report(PL[0], "left (0x02)", 400, mid="c4")
st, r = last(PL[0])
check((PL[0], "c4") not in daemon.CLAN_EXCUSED and r.get("left") == 1 and r.get("supplies") == 0, "deliberate quit (0x02) mid-round: left-early day, supplies 0")
reset(); play("c4b", PL)
leave_and_report(PL[1], "searching again", 400, mid="c4b")
st, r = last(PL[1])
check(r.get("left") == 1, "deliberate 'searching again' mid-round: left early")

# (5) grace: first seconds of the match / last seconds of the round
reset(); play("g1", PL, started_ago=20.0)
leave_and_report(PL[0], "left (0x02)", 0, mid="g1")
check((PL[0], "g1") in daemon.CLAN_EXCUSED and "start" in daemon.CLAN_EXCUSE_WHY.get((PL[0], "g1"), ""), "0x02 within 45 s of the match start: excused (could not reach the host)")
reset(); play("g2", PL, rem=12.0)
leave_and_report(PL[0], "left (0x02)", 900, mid="g2")
st, r = last(PL[0])
check((PL[0], "g2") in daemon.CLAN_EXCUSED and not r.get("left"), "0x02 in the last 30 s of the round: excused, normal day")

# (6) reconnect: left (crash), came back into the running match, played on
def come_back(mid, t):
    with MM.lock: MM.departed.get(mid, set()).discard(t)
    daemon.CLAN_MATCH[t] = mid

reset(); play("r1", PL)
d0 = daemon.clan_state(PL[0])["day"]
daemon.leave_running_match(PL[0], "session lost"); daemon.CLAN_MATCH[PL[0]] = "r1"
daemon.clan_report(PL[0], 300, 0)
come_back("r1", PL[0])
daemon.clan_finalize(PL[0])                                   # the 20 s grace is over: it is back in the match
check(daemon.clan_state(PL[0])["day"] == d0 and PL[0] in daemon.CLAN_PENDING, "reconnected player: the first report is held, nothing booked yet")
check((PL[0], "r1") not in daemon.CLAN_EXCUSED, "reconnected player: the crash excuse is void (the next leave decides)")
daemon.clan_report(PL[0], 200, 2)                              # played on to the match end: flags 2
st, r = last(PL[0])
check(st["day"] - d0 == 1 and not r.get("left") and r.get("parts") == 500, "reconnect then played to the end: one normal day with both halves (300 + 200 parts)")

# (7) quit after a reconnect: it came back, then really quit -> now it is left early (the excuse did not stick)
reset(); play("r2", PL)
d0 = daemon.clan_state(PL[1])["day"]
daemon.leave_running_match(PL[1], "timed out"); daemon.CLAN_MATCH[PL[1]] = "r2"
daemon.clan_report(PL[1], 300, 0)
come_back("r2", PL[1])
daemon.clan_finalize(PL[1])
leave_and_report(PL[1], "left (0x02)", 100, mid="r2")
st, r = last(PL[1])
check(st["day"] - d0 == 1 and r.get("left") == 1, "quit after a reconnect: a single left-early day (no second day, the earlier crash excuse is void)")

# (8) the host crashes with no migration: its own day is not 'left early'; a deliberate host quit still is
reset(); play("h1", PL)
with MM.lock: MM.matches["h1"] = list(PL)
daemon.HM.enabled and None
daemon.leave_running_match(PL[0], "session lost")
check((PL[0], "h1") not in daemon.CLAN_QUITTERS, "host that crashed is no 'quitter'")

print("%d failure(s)" % len(FAILS))
sys.exit(1 if FAILS else 0)
