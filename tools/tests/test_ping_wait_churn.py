"""Ping wait (ping_wait_judge): the formation hold for unknown pair pings ends once the longest-waiting unknown player has waited
PING_WAIT_S, even while new searchers with unknown pings keep arriving (a busy queue never formed).
Run: python tools/tests/test_ping_wait_churn.py"""
import os, sys, tempfile
sys.path.insert(0, os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")))
os.environ.update(T2R_HOST="127.0.0.1", T2R_PORT="0", T2R_MIN_PLAYERS="2")
os.chdir(tempfile.mkdtemp())
import daemon  # noqa: E402

fails = 0
def check(ok, what):
    global fails
    print(("ok   " if ok else "FAIL ") + what)
    fails += 0 if ok else 1

W = daemon.PING_WAIT_S
known = {}
def pair(a, b):
    return known.get(frozenset((a, b)))
helper = lambda t: True
daemon.PING_WAIT_SINCE.clear()

# 4 players with all pings known: no hold
P = ["a", "b", "c", "d"]
for i, x in enumerate(P):
    for y in P[i + 1:]:
        known[frozenset((x, y))] = 50
hold, out = daemon.ping_wait_judge(P, "a", pair, 0.0, helper=helper)
check(not hold and not out, "all pings known: no hold")

# a new player e with unknown pings arrives at t=0: hold for up to W
hold, out = daemon.ping_wait_judge(P + ["e"], "a", pair, 0.0, helper=helper)
check(hold, "new unknown player: hold")
hold, out = daemon.ping_wait_judge(P + ["e"], "a", pair, W / 2, helper=helper)
check(hold, "still holding at W/2")

# churn: a new unknown player arrives every 2 s; the old rule held as long as any of them was new
t = W / 2
players = P + ["e"]
held_until = None
for k in range(20):
    t += 2.0
    players = players + ["n%d" % k]
    hold, out = daemon.ping_wait_judge(players, "a", pair, t, helper=helper)
    if not hold:
        held_until = t
        break
check(held_until is not None and held_until <= W + 2.0, "churn: the hold ends once the first unknown player waited W (ended at %s s, W %s)" % (held_until, W))
check(out is not None and "a" not in out and {"b", "c", "d"}.isdisjoint(out) and "e" in out,
      "the players with unknown pings to the host are left out, the known ones stay (out %s)" % sorted(out or []))

# the left-out players' pings arrive: no hold, nobody left out
for x in players:
    for y in players:
        if x != y:
            known[frozenset((x, y))] = 60
hold, out = daemon.ping_wait_judge(players, "a", pair, t + 1, helper=helper)
check(not hold and not out, "pings arrived: no hold, nobody left out")

print("ALL OK" if not fails else "%d failure(s)" % fails)
sys.exit(1 if fails else 0)
