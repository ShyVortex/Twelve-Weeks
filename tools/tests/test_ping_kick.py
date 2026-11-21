"""test_ping_kick.py - the ping limit (daemon.ping_check) and the no-penalty rule for kicks (CLAN_KICKED).
  python tools/tests/test_ping_kick.py"""
import os
import sys
import tempfile

TOOLS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TMP = tempfile.mkdtemp(prefix="pingkick-")
os.environ["T2R_DB"] = os.path.join(TMP, "t.db")
os.environ["T2R_STATUS_FILE"] = "0"
sys.path.insert(0, TOOLS)
import daemon  # noqa: E402

FAILS = []


def check(cond, what):
    print(("ok   " if cond else "FAIL ") + what)
    if not cond:
        FAILS.append(what)


kicked = []
daemon.kick_token = lambda tok, why, ktxt, kind="admin-kick", reason="", keep_out=False, no_penalty=False: kicked.append((tok, ktxt, kind, keep_out, no_penalty)) or ["left match"]
H, A, B, C = "h" * 64, "a" * 64, "b" * 64, "c" * 64
T0 = 1000000.0
snap = [("m1", [H, A, B, C], T0 - 100, True, False, 0.0, set())]
daemon.MM.snapshot = lambda: snap
daemon.HM.enabled = False
daemon.MM.started.update({"m1", "m2", "m3"})      # (GAME-START went out: a player is judged only after it)


def setp(a, b, ms, at):
    daemon.PING[(a, b)] = [ms]
    daemon.PING_AT[(a, b)] = at


lim = daemon.PING_KICK_MS
check(lim == 190, "default limit 190 ms")
# A high, B / C fine: A is removed only after PING_KICK_S of it
for t in (0, 30, 59):
    now = T0 + t
    setp(A, H, 260, now); setp(B, H, 80, now); setp(C, H, 120, now)
    daemon.ping_check(now)
check(not kicked, "not removed before %d s over the limit" % daemon.PING_KICK_S)
now = T0 + 61
setp(A, H, 255, now); setp(B, H, 80, now); setp(C, H, 120, now)
daemon.ping_check(now)
check(len(kicked) == 1 and kicked[0][0] == A, "removed after the limit time")
check(kicked and kicked[0][2] == "ping-kick" and kicked[0][3] and kicked[0][4], "ping-kick kind, kept out of the match, no penalty")
check(kicked and "255 ms" in kicked[0][1] and "(limit 190 ms)" in kicked[0][1], "text carries the ping and the limit: %r" % (kicked[0][1] if kicked else ""))
daemon.ping_check(now + 10)
check(len(kicked) == 1, "once per match")
# a dip under the limit restarts the clock
kicked.clear(); daemon.PING_HIGH.clear(); daemon.PING_KICKED.clear()
for t, ms in ((0, 250), (40, 150), (50, 250), (100, 250)):
    now = T0 + 200 + t
    setp(B, H, ms, now); setp(A, H, 80, now); setp(C, H, 90, now)
    daemon.ping_check(now)
check(not kicked, "a dip under the limit restarts the clock (50 s high since the dip)")
# most players high to the host: the host's link, nobody removed
kicked.clear(); daemon.PING_HIGH.clear(); daemon.PING_KICKED.clear()
for t in (0, 70):
    now = T0 + 500 + t
    setp(A, H, 300, now); setp(B, H, 280, now); setp(C, H, 90, now)
    daemon.ping_check(now)
check(not kicked, "2 of 3 high to the host: nobody removed")
# stale measurements count for nothing; match grace
kicked.clear(); daemon.PING_HIGH.clear(); daemon.PING_KICKED.clear()
for t in (0, 70):
    now = T0 + 900 + t
    setp(A, H, 300, T0); setp(B, H, 80, now); setp(C, H, 90, now)
    daemon.ping_check(now)
check(not kicked, "a stale measurement removes nobody")
snap[0] = ("m2", [H, A, B, C], T0 + 2000 - 10, True, False, 0.0, set())
for t in (0, 5):
    now = T0 + 2000 + t
    setp(A, H, 400, now); setp(B, H, 80, now); setp(C, H, 90, now)
    daemon.ping_check(now)
check(not daemon.PING_HIGH, "nothing counted in the first %d s of a match" % daemon.PING_GRACE_S)
# a player still on the loading screen (no GAME-START yet) is never kicked, and its timer starts only after the start
kicked.clear(); daemon.PING_HIGH.clear(); daemon.PING_KICKED.clear()
snap[0] = ("m3", [H, A, B, C], T0 + 3000 - 100, True, False, 0.0, set())
daemon.MM.started.discard("m3")
for t in (0, 40, 80, 120):
    now = T0 + 3000 + t
    setp(A, H, 400, now); setp(B, H, 80, now); setp(C, H, 90, now)
    daemon.ping_check(now)
check(not kicked and not daemon.PING_HIGH, "match not started (loading screen): nobody removed, no timer")
daemon.MM.started.add("m3")
now = T0 + 3200
setp(A, H, 400, now); setp(B, H, 80, now); setp(C, H, 90, now)
daemon.ping_check(now)
check(not kicked and (A, "m3") in daemon.PING_HIGH, "timer starts at the GAME-START, not before")
setp(A, H, 400, now + 30); setp(B, H, 80, now + 30); setp(C, H, 90, now + 30)
daemon.ping_check(now + 30)
check(not kicked, "still under the time %d s after the start" % daemon.PING_KICK_S)
now2 = now + 62
setp(A, H, 400, now2); setp(B, H, 80, now2); setp(C, H, 90, now2)
daemon.ping_check(now2)
check(len(kicked) == 1 and kicked[0][0] == A, "removed once the time ran after the start")
# a joiner of a running match waits for its own GAME-START
kicked.clear(); daemon.PING_HIGH.clear(); daemon.PING_KICKED.clear()
daemon.MM.joining[A] = ("m3", T0)
for t in (0, 40, 80, 120):
    now = T0 + 4000 + t
    setp(A, H, 400, now); setp(B, H, 80, now); setp(C, H, 90, now)
    daemon.ping_check(now)
check(not kicked and (A, "m3") not in daemon.PING_HIGH, "a joiner without its GAME-START is not judged")
daemon.MM.joining.pop(A, None)
# texts
en = daemon.srv_text("ping_kicked", "en", ms=250, s=61, lim=190)
pl = daemon.srv_text("ping_kicked", "pl", ms=250, s=61, lim=190)
check(en.startswith("You got kicked from the match") and pl.startswith("Wyrzucono ci"), "EN / PL texts start like the kick text (the ext's msg_is_kick)")
print("FAILED: %d" % len(FAILS) if FAILS else "all ok")
sys.exit(1 if FAILS else 0)
