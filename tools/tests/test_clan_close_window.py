"""Closing the game window in a match (Alt+F4 / the X) is the player's own leave, and crash / lost-connection excuses are capped per player.
The ext sends op 0xBC sub 3 just before its window closes; a session lost after it counts as left early (the grace windows still apply).
Run: python tests/test_clan_close_window_1123.py"""
import os, socket, sys, time
import sys as _t2s, os as _t2o; _t2s.path.append(_t2o.path.normpath(_t2o.path.join(_t2o.path.dirname(_t2o.path.abspath(__file__)), ".."))); import t2rtmp  # noqa: E402,F401

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
FAILS = []
def check(cond, what):
    print(("ok   " if cond else "FAIL ") + what)
    if not cond:
        FAILS.append(what)

s = socket.socket(); s.bind(("127.0.0.1", 0)); port = s.getsockname()[1]; s.close()
os.environ.update(T2R_HOST="127.0.0.1", T2R_PORT=str(port))
os.environ.pop("T2R_CLAN_NO_PENALTY", None)
import daemon  # noqa: E402
daemon.CLAN_NO_PENALTY = False
daemon.update_target = lambda: None

def tok(n):
    return "54324e3a" + "436c6f" + "00" * 13 + ("%024x" % (0x2000 + n))

def running(mid, age=600.0):
    with daemon.MM.lock:
        daemon.MM.started_t[mid] = time.time() - age
        daemon.MM.clock.pop(mid, None)

LOST = "session lost"
a = tok(1)
for i in range(daemon.CLAN_LOST_EXCUSE_MAX):
    mid = "a%07x" % i
    running(mid)
    r = daemon.clan_leave_excuse(a, mid, LOST)
    check(r is not None and "crash" in r, "lost connection %d of %d is excused (%s)" % (i + 1, daemon.CLAN_LOST_EXCUSE_MAX, r))
running("a-over")
check(daemon.clan_leave_excuse(a, "a-over", LOST) is None, "one more lost connection in the same day counts as left early")
check(daemon.clan_leave_excuse(a, "a-over", LOST) is None, "asking again for the same leave gives the same answer")
check(daemon.clan_leave_excuse(a, "a-over", "left (0x02)") is None, "a menu leave is still left early")

b = tok(2)
running("b1")
check(daemon.clan_leave_excuse(b, "b1", LOST) is not None, "a lost connection without a closing notice is excused (under the cap)")
running("b2")
pl = b.encode("latin1") + bytes([3, 0])
daemon.modeq_op(pl)
check(b in daemon.CLAN_CLOSING, "op 0xBC sub 3 records the closing notice")
check(daemon.clan_leave_excuse(b, "b2", LOST) is None, "a session lost right after the closing notice counts as left early")
daemon.CLAN_CLOSING[b] = (time.time() - daemon.CLAN_CLOSING_S - 5, None)
running("b3")
check(daemon.clan_leave_excuse(b, "b3", LOST) is not None, "an old closing notice does not count")

c = tok(3)
running("c1", age=10.0)
daemon.CLAN_CLOSING[c] = (time.time(), "c1")
r = daemon.clan_leave_excuse(c, "c1", LOST)
check(r is not None and "match start" in r, "a closed window in the start grace is still excused (%s)" % r)
running("c2")
daemon.CLAN_CLOSING[c] = (time.time(), "c-other")
check(daemon.clan_leave_excuse(c, "c2", LOST) is not None, "a closing notice from another match does not count")

# The verdict on a lost session comes SESSION_GRACE_S (60 s) after the drop, long after CLAN_CLOSING_S
d, e = tok(4), tok(5)
running("d1")
with daemon.MM.lock:
    daemon.MM.launched.add("d1"); daemon.MM.started.add("d1"); daemon.MM.ended.discard("d1")
    daemon.MM.matches["d1"] = [e, d]
conn = object()
_conn, _mid = daemon.SESSIONS.conn, daemon.MM.mid_of
daemon.SESSIONS.conn = lambda t: conn
daemon.MM.mid_of = lambda t: "d1"
try:
    daemon.CLAN_CLOSING[d] = (time.time() - 3, "d1")
    daemon.CLAN_MATCH[d] = "d1"; daemon.CLAN_MATCH[e] = "d1"
    check(daemon.note_session_lost(d, conn), "the session drop 3 s after the notice is noted")
    check(daemon.CLAN_PENDING.get(d) == ("d1", 0, 0, {}) and d in daemon.CLAN_DUE and (d, "d1") in daemon.CLAN_QUITTERS,
          "a closed game sends no report: the server books its left-early day (0 parts)")
    check((d, "d1") in daemon.CLAN_CLOSE_DROPS, "... and marked as a closed window")
    daemon.note_session_lost(e, conn)
    check((e, "d1") not in daemon.CLAN_CLOSE_DROPS, "a drop without a notice is not marked")
    check(e not in daemon.CLAN_PENDING, "a drop without a notice books nothing (a crash)")
finally:
    daemon.SESSIONS.conn, daemon.MM.mid_of = _conn, _mid
daemon.CLAN_CLOSING[d] = (time.time() - 63, "d1")           # the verdict, 60 s later
check(daemon.clan_leave_excuse(d, "d1", LOST) is None, "the verdict 60 s after a closed-window drop is still left early")
check(daemon.clan_leave_excuse(e, "d1", LOST) is not None, "the other lost player is excused as a crash")
ok = daemon.abort_award("d1", [d, e], None, "everyone else left (left (0x02))")
check(ok and (d, "d1") not in getattr(daemon, "CLAN_ABORTED", ()) and (d, "d1") in daemon.CLAN_QUITTERS, "the abort award is not for the player who closed its window: left early")
check((e, "d1") not in daemon.CLAN_QUITTERS, "the abort award still covers the others (no left-early day)")
running("d2")
with daemon.MM.lock:
    daemon.MM.started.add("d2"); daemon.MM.ended.discard("d2")
daemon.CLAN_CLOSE_DROPS.add((d, "d2"))
check(daemon.abort_award("d2", [d], None, "everyone else left (left (0x02))") is False and (d, "d2") in daemon.CLAN_QUITTERS,
      "closer alone left over: no award at all, left early")

print("ALL OK" if not FAILS else "FAILED: %d" % len(FAILS))
sys.exit(1 if FAILS else 0)
