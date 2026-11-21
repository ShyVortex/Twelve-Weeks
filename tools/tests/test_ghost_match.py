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



PL = T[:4]
def play(mid, players):
    start_match(mid, players)
    with MM.lock:
        MM.clock[mid] = (500.0, 900.0, False, time.time())
    for t in players: daemon.clan_side(t, 1)

# (1) restart re-adopted the match; all four players' games already left it and send their final report (flags 0): the match must not live on
wipe(True); daemon.CLAN_DONE.clear(); daemon.CLAN_CREDITED.clear(); daemon.CLAN_LEFT_AT.clear()
play("gh1", PL)
for t in PL: daemon.CLAN_MATCH[t] = "gh1"
for t in PL: daemon.clan_report(t, 100, 0)
check(all(MM.mid_of(t) is None for t in PL), "final reports of all players take them out of the match")
check("gh1" not in MM.matches or all(t in MM.departed.get("gh1", ()) for t in PL), "a match whose players all reported is gone / fully departed (no ghost)")

# a report with flags 2 (the game saw the match end) does NOT depart: the host's 0x12 / the end-by-reports closer still handle it
wipe(True)
play("gh2", PL)
for t in PL: daemon.CLAN_MATCH[t] = "gh2"
daemon.clan_report(PL[0], 100, 2)
check(MM.mid_of(PL[0]) == "gh2", "an end report (flags 2) leaves the player listed (normal match end path)")

# (2) host lost, nobody asks for a successor: after HOSTMIG_NOCAND_S the match ends instead of blocking join in progress forever
wipe(True)
play("gh3", PL)
with HM.lock: HM.matches['gh3']['seen'] = {}          # nobody polls (their games left)
HM.leave(PL[0], "session lost") if hasattr(HM, "leave") else HM.depart(PL[0], "session lost")
hi = HM.host_info("gh3")
check(hi and hi["pending"], "(setup) host lost: migration pending")
daemon.reap_matches()
check("gh3" not in MM.ended, "pending only seconds: the match is not ended yet")
with HM.lock: HM.matches["gh3"]["lost"] = time.time() - 60
daemon.reap_matches()
check("gh3" in MM.ended and "gh3" in daemon.ABORT_AWARDED, "pending with nobody asking for 45+ s: ghost match ended (abort award)")

print("%d failure(s)" % len(FAILS))
sys.exit(1 if FAILS else 0)
