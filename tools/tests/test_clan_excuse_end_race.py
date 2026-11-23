"""An excused leave that is itself the last departure: the abort award ends the match in the same second, so CLAN_ENDED is set before
the leaver's report resolves. The excuse must still apply (no 0-supply day).   Run: python tests/test_clan_excuse_end_race.py"""
import os, socket, sys, tempfile, threading, time
import sys as _t2s, os as _t2o; _t2s.path.append(_t2o.path.normpath(_t2o.path.join(_t2o.path.dirname(_t2o.path.abspath(__file__)), ".."))); import t2rtmp  # noqa: E402,F401

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import clan  # noqa: E402

FAILS = []
def check(cond, what):
    print(("ok   " if cond else "FAIL ") + what)
    if not cond:
        FAILS.append(what)

tmp = tempfile.mkdtemp()
s = socket.socket(); s.bind(("127.0.0.1", 0)); port = s.getsockname()[1]; s.close()
os.environ.update(T2R_HOST="127.0.0.1", T2R_PORT=str(port), T2R_CLAN_GRACE="1")
import daemon  # noqa: E402
daemon.DB_PATH = os.path.join(tmp, "daemon.db")
threading.Thread(target=daemon.tcp_server, daemon=True).start()
time.sleep(0.3)

def fresh(n):
    tok = "54324e3a" + "4d6973" + "00" * 13 + ("%024x" % (0x1000 + n))
    with daemon.dbc() as db:
        db.execute("INSERT INTO players(token) VALUES(?)", (tok,))
    with daemon._dblock, daemon.dbc() as db:
        clan.choose_side(db, clan.token_id(tok), clan.WLF)
    return tok

def state(tok):
    with daemon.dbc() as db:
        cl = clan.load(db, clan.token_id(tok))
    return cl["day"], cl["hungry"], cl["sick"]

def run(n, parts, excused, left_dt):
    tok, mid = fresh(n), "race%d" % n
    daemon.clan_match_started([tok], mid)
    t = time.time()
    daemon.CLAN_LEFT_AT[(tok, mid)] = t + left_dt
    if excused:
        daemon.CLAN_EXCUSED.add((tok, mid))
        daemon.CLAN_EXCUSE_WHY[(tok, mid)] = "host lost (migration pending)"
    daemon.CLAN_ENDED[mid] = t                       # abort award in the same second
    before = state(tok)
    daemon.CLAN_PENDING[tok] = (mid, parts, 0, {})
    daemon.clan_finalize(tok)
    return before, state(tok)

b, a = run(1, 0, True, 0.0)
check(a == b, "excused leave + same-second end, 0 parts: no day booked %s -> %s" % (b, a))
b, a = run(2, 600, True, 0.0)
check(a[1] == b[1] and a[2] == b[2], "excused leave + same-second end, 600 parts: parts count, nobody new hungry / sick %s -> %s" % (b, a))
b, a = run(3, 0, False, 0.0)
check(a[0] == b[0] + 1 or a != b, "not excused: unchanged rule (normal day) %s -> %s" % (b, a))
b, a = run(4, 0, True, 30.0)
check(a != b, "excused but left 30 s after the end (post-match): unchanged rule (normal day) %s -> %s" % (b, a))

print()
print("FAILED: %d" % len(FAILS) if FAILS else "all passed")
sys.exit(1 if FAILS else 0)
