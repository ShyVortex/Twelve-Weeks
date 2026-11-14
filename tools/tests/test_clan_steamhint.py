"""Daemon clan reads with the launcher's steamid hint (ops 0xE0 / 0xE8 + optional 8-byte steamid). Scratch DB, no listener.
Run: python tools/tests/test_clan_steamhint.py"""
import os, struct, sys, tempfile
import sys as _t2s, os as _t2o; _t2s.path.append(_t2o.path.normpath(_t2o.path.join(_t2o.path.dirname(_t2o.path.abspath(__file__)), ".."))); import t2rtmp  # noqa: E402,F401  (temp hygiene: tools/t2rtmp.py)
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
FAILS = []
def check(cond, what):
    print(("ok   " if cond else "FAIL ") + what)
    if not cond: FAILS.append(what)

tmp = tempfile.mkdtemp()
os.environ.update(T2R_HOST="127.0.0.1", T2R_PORT="0", T2R_DB=os.path.join(tmp, "t2r.db"), T2R_ADMIN_PORT="0")
import daemon  # noqa: E402
import clan  # noqa: E402

SID, OTHER = 76561198000000042, 76561198000000001
T_NEW = ("c3853f30" + "ab" * 28)[:64]           # a fresh install: no steamid known
T_KNOWN = ("11111111" + "cd" * 28)[:64]         # a token whose steamid the daemon knows (OTHER)
with daemon.db() as c:
    clan.ensure(c)
    clan.choose_side(c, "s:%d" % SID, clan.WLF)
    cl = clan.load(c, "s:%d" % SID); cl.update(day=47, healthy=20, hungry=2, sick=1); clan.save(c, "s:%d" % SID, cl)
    c.execute("INSERT INTO players(token, name, steamid, last_seen) VALUES(?,?,?,0)", (T_KNOWN, "known", OTHER))
    c.commit()
def rows():
    with daemon.db() as c:
        return (c.execute("SELECT COUNT(*) FROM clans").fetchone()[0], c.execute("SELECT COUNT(*) FROM players").fetchone()[0], c.execute("SELECT COUNT(*) FROM boosters").fetchone()[0])
before = rows()
def state(token, sid=None):
    pl = token.encode() + (struct.pack("<Q", sid) if sid else b"")
    r = daemon.clan_op(0xE0, pl)
    return dict(kv.split("=") for kv in r[3:].decode().split())
def meta(token, sid=None):
    pl = token.encode() + (struct.pack("<Q", sid) if sid else b"")
    r = daemon.meta_op(0xE8, pl)
    return dict(kv.split("=") for kv in r[3:].decode().split())

s = state(T_NEW); check(s["st"] == "0", "no hint: an unknown install has no clan")
s = state(T_NEW, SID); check(s["st"] == "1" and s["day"] == "47" and s["fac"] == "1", "hint: the account's clan (alive, day 47) is read")
m = meta(T_NEW, SID); check(m["v"] == "1" and "bc1" in m, "0xE8 with the hint answers")
s = state(T_NEW, OTHER + 5); check(s["st"] == "0", "hint for an account with no clan row: no clan (nothing adopted)")
s = state(T_KNOWN, SID); check(s["st"] == "0", "a token that has its own steamid ignores the hint (its own clan, none)")
check(rows() == before, "reads created no clan / player / booster rows %s -> %s" % (before, rows()))
with daemon.db() as c:
    check(c.execute("SELECT steamid FROM players WHERE token=?", (T_NEW,)).fetchone() is None, "the hint never linked the token to the steamid")
    check(c.execute("SELECT COUNT(*) FROM clans WHERE token_id=?", ("c3853f30" + "ab" * 8,)).fetchone()[0] == 0, "no clan row under the install's token id")
print("FAILED: %s" % FAILS if FAILS else "all ok")
sys.exit(1 if FAILS else 0)
