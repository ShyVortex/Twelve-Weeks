"""Every clan state reply (0xE1) carries the asker's role key ro= (the choose-side reply 0xE4 had none, and the ext's clan_parse,
which rebuilds the whole state from each reply, dropped the lead dev's pink badge and name rim for the rest of the session). Scratch DB, no listener.
Run: python tools/tests/test_role_state_ops.py"""
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
LEAD, OGP, NOBODY = 76561198000000042, 76561190000000001, 76561190000000002
with open(os.path.join(tmp, "devs.txt"), "w") as f:
    f.write("%d lead\n" % LEAD)
with open(os.path.join(tmp, "og-steamids.txt"), "w") as f:
    f.write("%d\n" % OGP)
import daemon  # noqa: E402
import clan  # noqa: E402

TOK = {LEAD: ("aa11" * 16), OGP: ("bb22" * 16), NOBODY: ("cc33" * 16)}
with daemon.db() as c:
    clan.ensure(c)
    for sid, t in TOK.items():
        c.execute("INSERT INTO players(token, name, steamid, last_seen) VALUES(?,?,?,0)", (t, "p%d" % (sid % 1000), sid))
    c.commit()

def kv(frame):
    return dict(x.split("=", 1) for x in frame[3:].decode().split() if "=" in x)

for sid, want in ((LEAD, "4"), (OGP, "1"), (NOBODY, None)):
    t = TOK[sid].encode()
    s0 = kv(daemon.clan_op(0xE0, t))
    check(s0.get("ro") == want, "0xE0 state: ro=%s for %d (got %s)" % (want, sid, s0.get("ro")))
    s4 = kv(daemon.clan_op(0xE4, t + bytes([clan.WLF])))
    check(s4.get("st") == "1" and s4.get("fac") == "1", "0xE4 picks the side for %d" % sid)
    check(s4.get("ro") == want, "0xE4 choose-side reply: ro=%s for %d (got %s)" % (want, sid, s4.get("ro")))
    s2 = kv(daemon.clan_op(0xE2, t + struct.pack("<IIB", 1, 0, 0)))
    check(s2.get("ro") == want, "0xE2 report reply: ro=%s for %d (got %s)" % (want, sid, s2.get("ro")))
print("FAILED: %s" % FAILS if FAILS else "all ok")
sys.exit(1 if FAILS else 0)
