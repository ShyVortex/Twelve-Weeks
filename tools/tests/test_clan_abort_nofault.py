"""A match the abort award ended for the players left behind (everyone else left / host left, no migration) never penalises them:
0 parts = no day at all, parts > 0 = parts count, deficit forgiven (one match: a 0-part day killed 2, made 48 hungry, 19 sick).
Run: python tools/tests/test_clan_abort_nofault.py"""
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


def full(tok):
    with daemon.dbc() as db:
        return dict(clan.load(db, clan.token_id(tok)))

def via_abort(n, parts, why="everyone else left (left (0x02))", quitter=None):
    tok, mid = fresh(n), "abort%d" % n
    others = [tok]
    daemon.clan_match_started([tok] + ([quitter] if quitter else []), mid)
    with daemon.MM.lock:
        daemon.MM.matches[mid] = list(others) + ([quitter] if quitter else [])
        daemon.MM.started.add(mid)
        daemon.MM.started_t[mid] = time.time() - 300
    ok = daemon.abort_award(mid, others, quitter, why)
    before = full(tok)
    daemon.CLAN_PENDING[tok] = (mid, parts, 0, {})
    daemon.clan_finalize(tok)
    return ok, before, full(tok), tok, mid

ok, b, a, tok, mid = via_abort(1, 0)
check(ok and (tok, mid) in daemon.CLAN_ABORTED, "abort_award ran and marked the player (%s)" % ok)
check((a["day"], a["healthy"], a["hungry"], a["sick"]) == (b["day"], b["healthy"], b["hungry"], b["sick"]),
      "0 parts after everyone else left: no day, nobody hungry / sick / dead (%s)" % ({k: (b[k], a[k]) for k in ("day", "healthy", "hungry", "sick")},))
ok, b, a, tok, mid = via_abort(2, 900, why="host left (left (0x02)), no migration")
check(a["hungry"] == b["hungry"] and a["sick"] == b["sick"] and a["healthy"] + a["hungry"] + a["sick"] >= b["healthy"] + b["hungry"] + b["sick"],
      "900 parts after the host left: parts count, no deficit (%s)" % ({k: (b[k], a[k]) for k in ("day", "healthy", "hungry", "sick")},))
# control: the same 0-part report in a match that ended normally still books the normal (idle) day
tok, mid = fresh(3), "normal3"
daemon.clan_match_started([tok], mid)
daemon.CLAN_ENDED[mid] = time.time()
b = full(tok)
daemon.CLAN_PENDING[tok] = (mid, 0, 0, {})
daemon.clan_finalize(tok)
a = full(tok)
check((a["hungry"], a["sick"], a["healthy"]) != (b["hungry"], b["sick"], b["healthy"]), "control: a normal match end with 0 parts keeps the old rule (deficit applied)")

print()
print("FAILED: %d" % len(FAILS) if FAILS else "all passed")
sys.exit(1 if FAILS else 0)
