"""Matchmaking pre-mortem S1-S3 (non-loader / mid-load leaver / silent countdown player) and J3 (joiner into an empty match).
Offline, plain python, temp DB, no sockets.  Run: python tools/tests/test_mm_loadjoin.py"""
import os, sys, tempfile, time

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
os.environ.update(T2R_HOST="127.0.0.1", T2R_PORT="0", T2R_MATCH_SIZE="8", T2R_ENGINE_SLOTS="8", T2R_MIN_PLAYERS="2", T2R_P2P="0")
import daemon  # noqa: E402
daemon.DB_PATH = os.path.join(tempfile.mkdtemp(), "daemon.db")
daemon.get_name = lambda t: NAMES[T.index(t)] if t in T else None
daemon.tag = lambda t: NAMES[T.index(t)] if t in T else t[:6]
MM = daemon.MM
CD = daemon.countdown_seconds()

def reset():
    for a in ("queue", "seen", "matches", "formed", "left", "settle", "qtime", "departed", "departed_t", "joining", "clock", "polled"):
        getattr(MM, a).clear()
    for a in ("launched", "ended", "started", "timed_out"):
        getattr(MM, a).clear()
    daemon.LOADED.clear(); daemon.LOADED_T.clear()
    for t in T: daemon.PRES.touch(t, "x")

def mk(mid, players, age, launched=True):
    MM.matches[mid] = list(players); MM.formed[mid] = time.time() - age
    MM.qtime[mid] = {t: time.time() - 100 for t in players}
    if launched: MM.launched.add(mid)

def loaded(t, ago):
    daemon.LOADED.add(t); daemon.LOADED_T[t] = time.time() - ago

# ---- S1: one player never loads; the others are loaded for > LOAD_GRACE
reset()
mk("m1", T[:4], CD + 60)
for t in T[:3]: loaded(t, daemon.LOAD_GRACE + 5)
done = daemon.reap_matches()
check(("m1", "load-timeout") in done, "S1: 3 of 4 loaded %d s ago -> the match starts at age CD+60 s (< hard %d s): %s" % (daemon.LOAD_GRACE + 5, daemon.LOAD_TIMEOUT, done))
check("m1" in MM.started, "S1: GAME-START went out")
check(T[3] in MM.departed.get("m1", ()) and not any(t in MM.departed.get("m1", ()) for t in T[:3]), "S1: only the non-loader is dropped")
check(MM.mid_of(T[3]) is None, "S1: the dropped player is free to queue again (JIP possible)")

reset()
mk("m2", T[:4], CD + 60)
for t in T[:3]: loaded(t, 10)
done = daemon.reap_matches()
check("m2" not in MM.started and not done, "S1: others loaded only 10 s ago -> still waiting (a loader is legitimately slow)")

reset()
mk("m3", T[:4], CD + 60)
loaded(T[0], daemon.LOAD_GRACE + 5)
done = daemon.reap_matches()
check("m3" not in MM.started, "S1: 1 of 4 loaded, 3 still loading = a majority loading: no soft drop")
reset()
mk("m3b", T[:2], CD + 60)
loaded(T[0], daemon.LOAD_GRACE + 5)
done = daemon.reap_matches()
check("m3b" not in MM.started and not done, "S1: 1 v 1: no soft drop - the missing one may be the host, it gets the full LOAD_TIMEOUT")
reset()
mk("m3c", T[:2], CD + daemon.LOAD_TIMEOUT + 5)
loaded(T[0], daemon.LOAD_GRACE + 5)
done = daemon.reap_matches()
check(("m3c", "abort-solo") in done and "m3c" not in MM.started and MM.mid_of(T[0]) is None and MM.mid_of(T[1]) is None,
      "S1: 1 v 1 past LOAD_TIMEOUT, one never loaded -> called off, both free (no GAME-START for one player, R-75SX): %s" % done)
reset()
mk("m3d", T[:3], CD + daemon.LOAD_TIMEOUT + 5)
loaded(T[0], 5); loaded(T[1], 5)
done = daemon.reap_matches()
check(("m3d", "load-timeout") in done and "m3d" in MM.started, "S1: 2 of 3 loaded past LOAD_TIMEOUT -> starts without the third (unchanged)")

reset()
mk("m4", T[:3], CD + daemon.LOAD_TIMEOUT + 5)
done = daemon.reap_matches()
check(not done and "m4" not in MM.started, "S1: nobody loaded at all: nothing to start (unchanged)")

reset()
mk("m4b", T[:3], CD + daemon.LOAD_TIMEOUT + daemon.LOAD_GRACE + daemon.NOLOAD_MARGIN + 5)
done = daemon.reap_matches()
check(("m4b", "abort-noload") in done and MM.mid_of(T[0]) is None and "m4b" not in MM.started, "S1b: nobody ever loaded past LOAD_TIMEOUT+GRACE+margin -> match called off, players free")
reset()
mk("m4c", T[:3], CD + daemon.LOAD_TIMEOUT + daemon.LOAD_GRACE + daemon.NOLOAD_MARGIN + 5)
loaded(T[0], 5)
done = daemon.reap_matches()
check(("m4c", "abort-noload") not in done and ("m4c", "abort-solo") in done, "S1b: one loaded player -> never the no-load abort (one left = abort-solo)")

# ---- S2: back out (0x02) during the level load
reset()
mk("m5", T[:3], CD + 40)
for t in T[:2]: loaded(t, 5)
st = {"token": T[2], "name": "Carol"}
daemon.handle_leave(("127.0.0.1", 1), st)
check(T[2] in MM.departed.get("m5", ()), "S2: a 0x02 40 s after the level start removes the player (not held 120 s)")
check("m5" in MM.started, "S2: the others were all loaded -> GAME-START at once")
reset()
mk("m6", T[:3], CD + 5)
st = {"token": T[2], "name": "Carol"}
daemon.handle_leave(("127.0.0.1", 1), st)
check(T[2] not in MM.departed.get("m6", ()), "S2: a 0x02 5 s after the level start (dying conn) is still kept")

# ---- S3: a countdown player goes silent
reset()
mk("m7", T[:3], 20, launched=False)
with daemon.PRES.lock:
    daemon.PRES.players[T[2]]["last"] = time.time() - daemon.PRELAUNCH_SILENT - 5
done = daemon.reap_matches()
check(("m7", "abort-silent") in done, "S3: a player silent > %d s in the countdown calls the match off: %s" % (daemon.PRELAUNCH_SILENT, done))
check("m7" not in MM.matches, "S3: the match record is gone")
check(T[2] not in MM.queue and T[0] in MM.queue and T[1] in MM.queue, "S3: the others are back in the queue, the crashed one is not")
reset()
mk("m8", T[:3], 20, launched=False)
done = daemon.reap_matches()
check("m8" in MM.matches and not done, "S3: everybody present: the countdown goes on")

# ---- J3: joiner into an empty match
reset()
mk("j1", T[:2], 300); MM.started.add("j1"); MM.started_t["j1"] = time.time() - 280
MM.departed["j1"] = {T[0], T[1]}
MM.matches["j1"].append(T[2]); MM.joining[T[2]] = ("j1", time.time() - 30)
loaded(T[2], 1)
ok = daemon.maybe_game_start(T[2])
check(ok is False and T[2] not in MM.joining, "J3: all established players left: no GAME-START for the joiner")
check(MM.mid_of(T[2]) is None, "J3: the joiner is out of the dead match (free to search)")
reset()
mk("j2", T[:3], 300); MM.started.add("j2"); MM.started_t["j2"] = time.time() - 280
MM.departed["j2"] = {T[0], T[1]}
MM.joining[T[2]] = ("j2", time.time() - 30)
done = daemon.reap_matches()
check(("j2", "jip-empty") in done, "J3: the reaper also sends a still-loading joiner back: %s" % done)
reset()
mk("j3", T[:3], 300); MM.started.add("j3"); MM.started_t["j3"] = time.time() - 280
MM.departed["j3"] = {T[0]}
MM.joining[T[2]] = ("j3", time.time() - 30)
loaded(T[2], 1)
daemon.maybe_game_start(T[2])
check(T[2] not in MM.departed.get("j3", ()), "J3: one established player left (Bob remains): the joiner is NOT sent away")

print("FAILED: %s" % FAILS if FAILS else "all passed")
sys.exit(1 if FAILS else 0)
