"""Daemon op 0xB6 -> 0xB7 (the in-game CLAN page data, tools/clan_ingame.py) against a temp DB; never port 7001 / tools/t2r.db.
Run: python tools/tests/test_clan_ingame.py"""
import os, sys, tempfile
import sys as _t2s, os as _t2o; _t2s.path.append(_t2o.path.normpath(_t2o.path.join(_t2o.path.dirname(_t2o.path.abspath(__file__)), ".."))); import t2rtmp  # noqa: E402,F401
HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.dirname(HERE)
TMP = tempfile.mkdtemp()
os.environ["T2R_DB"] = os.path.join(TMP, "t.db")
for k in ("T2R_CLAN_CHRONICLE", "T2R_CLAN_SAGA", "T2R_CLAN_STATUS"):
    os.environ[k] = "1"
sys.path.insert(0, TOOLS)
import daemon  # noqa: E402
import clan_demo_seed  # noqa: E402

FAILS = []
def check(cond, what):
    print(("ok   " if cond else "FAIL ") + what)
    if not cond:
        FAILS.append(what)

TOK = "54324e3a" + "416c696365" + "00" * 11 + "0123456789abcdef01234567"
rep = daemon.clan13_op(TOK.encode() + b"\x00\x01")
check(rep and rep[2] == 0xB7 and len(rep) == 3, "no clan yet: an empty 0xB7")
check(daemon.clan13_op(b"short") is None and daemon.clan13_op(b"zz" * 40 + b"\x00\x01") is None, "bad token / short payload: no reply")
daemon.clan_side(TOK, 1)                                     # a fresh clan with no story yet: the op builds its roster from the counts
rep = daemon.clan13_op(TOK.encode() + bytes([0, 1]))
check(rep[2] == 0xB7 and len([l for l in rep[3:].decode().split(chr(10)) if l.startswith("P" + chr(9))]) >= 4, "fresh clan: a roster from the counts (%d bytes)" % len(rep))
for ext in ("", "-wal", "-shm"):
    try:
        os.remove(os.environ["T2R_DB"] + ext)
    except OSError:
        pass
sys.argv = ["x", os.environ["T2R_DB"], "--days", "9", "--token", "0123456789abcdef01234567"]
clan_demo_seed.main()
for lang, name in ((0, "en"), (1, "pl")):
    for sec in (1, 2, 3, 4):
        rep = daemon.clan13_op(TOK.encode() + bytes([lang, sec]))
        text = rep[3:].decode("utf-8")
        lines = text.split("\n")
        check(rep[2] == 0xB7 and int.from_bytes(rep[:2], "little") == len(rep) - 2 and len(rep) < 60000, "%s section %d: %d bytes in %d lines" % (name, sec, len(rep), len(lines)))
        check(lines[0].startswith("H\t") and len(lines[0].split("\t")) == 12, "%s section %d header has 12 fields" % (name, sec))
        kinds = {1: "P", 2: "J", 3: "S", 4: "U"}[sec]
        rows = [l for l in lines if l.startswith(kinds + "\t")]
        check(len(rows) >= (5 if kinds == "S" else 0 if kinds == "U" else 8) and all("\n" not in l for l in lines), "%s section %d rows: %d" % (name, sec, len(rows)))
        nf = {"P": 12, "J": 14, "S": 5, "U": 7}[kinds]
        check(all(len(l.split("\t")) == nf for l in rows), "%s section %d: every %s row has %d fields" % (name, sec, kinds, nf))
rep = daemon.clan13_op(TOK.encode() + bytes([0, 3]))
ms = [l for l in rep[3:].decode().split("\n") if l.startswith("M\t")]
check(ms and all(len(l.split("\t")) == 9 for l in ms), "raid rows: %d matches with 9 fields" % len(ms))
NL, TB = chr(10), chr(9)
rep = daemon.clan13_op(TOK.encode() + bytes([0, 7]))
check(rep[2] == 0xB7 and [l for l in rep[3:].decode().split(NL) if l[:2] in ("E" + TB, "R" + TB)] == [], "end screen section on a living clan: header only")
import sqlite3 as _sq
_c = _sq.connect(os.environ["T2R_DB"])
for _st, _k in ((3, "W"), (2, "L")):
    _c.execute("UPDATE clans SET status=?", (_st,)); _c.commit()
    _ls = daemon.clan13_op(TOK.encode() + bytes([0, 7]))[3:].decode().split(NL)
    _e = [l.split(TB) for l in _ls if l.startswith("E" + TB)]
    _r = [l.split(TB) for l in _ls if l.startswith("R" + TB)]
    check(len(_e) == 1 and len(_e[0]) == 7 and _e[0][1] == _k and int(_e[0][2]) == len(_r) and 0 < len(_r) <= 7 and all(len(r) == 3 and r[2].count("/") == 3 for r in _r),
          "end screen section, status %d: E row + %d faces" % (_st, len(_r)))
    check(_k != "L" or all(r[2].endswith("/dead") for r in _r), "lost clan: the faces are the dead portraits")
_c.execute("UPDATE clans SET status=1"); _c.commit(); _c.close()
rep = daemon.clan13_op(TOK.encode() + bytes([0, 9]))
check(rep[2] == 0xB7 and len(rep) == 3, "unknown section: empty reply")
rep = daemon.clan13_op(TOK.encode() + bytes([0, 2]) + (10 ** 6).to_bytes(4, "little"))
check(all(l.split("\t")[12] == "0" for l in rep[3:].decode().split("\n") if l.startswith("J\t")), "seen id above the newest: nothing is NEW")
import clan_portrait_pool as _pp
_root = os.path.normpath(os.path.join(TOOLS, ".."))
_looks = {r[0]: r[1] for r in _pp.POOL}
check(len(_pp.RENDERED) > 50 and all(os.path.exists(os.path.join(_root, "re", "clan-portraits", "img", "%s_%s.png" % (_looks[m], e))) and os.path.exists(os.path.join(_root, "release", "launcher", "assets", "portraits", "%d_%s.png" % (m, e))) for m, es in _pp.EXPR.items() for e in es), "every EXPR image exists (game source + launcher asset): %d heads" % len(_pp.RENDERED))
import clan_chronicle as _ch
_ppl = [{"n": "N%d" % k, "g": "mf"[k % 2], "r": r, "s": ["h", "u", "s"][k % 3]} for k, r in enumerate(["kid", "elder", "medic", "cook", "guard", "scout", "scavenger", "mechanic", "gardener", "radio"] * 4)]
_ok = True
for _p in _ppl:
    for _fk in "WS":
        _a = _ch.portrait_id(_p, _fk).split("/")
        _ok &= int(_a[2]) in _pp.RENDERED and _a[3] in _pp.EXPR[int(_a[2])]
check(_ok, "every member gets a head with a render and an expression that head has")
check(_ch.fit_expr(143, "shock") == "neutral" and _ch.fit_expr(143, "hurt") in _pp.EXPR[143], "an expression a head lacks falls back (shock -> neutral)")
# roster row = status card (members shown HEALTHY wore a depressed face)
import clan_ingame as _ci  # noqa: E402
_st = {"day": 5, "morale": 96, "ch": {"dep": {"1": {"n": 4}}, "mem": {"2": {"grief": {"until": 9, "d": 1}}}}}
_row = lambda i, s: {"i": i, "n": "M%d" % i, "s": s, "r": "guard"}
check([_ch._roster_state(_st, _row(i, s)) for i, s in ((1, "h"), (2, "h"), (3, "h"), (4, "u"), (5, "s"))] == ["depressed", "sad", "healthy", "hungry", "sick"], "roster state follows the status code")
_r = [{"name": "A", "role": "guard", "roleText": "GUARD", "icon": "x", "state": "sad", "portrait": "W/m/124/neutral", "bond": "", "bondLabel": "", "tagline": ""}]
_l = _ci._person_rows({"roster": _r}, [], "en")[0].split(chr(9))
check(_l[3] == "d" and _l[4] == "GRIEVING", "a grieving member: grey-blue letter + its own word (%s %s)" % (_l[3], _l[4]))
check(_ch.fit_expr(100, "shock") == "sad" and _ch.fit_expr(143, "shock") == "neutral", "shock stands in as sad where the head has it")
# MATCH STATS of a raid (section 5): roster at the match end + each player's own report, the asker's team first, absent stats = -1, an unknown raid = header only
import sqlite3 as _sq  # noqa: E402
_c = _sq.connect(":memory:")
_ci.stats_roster(_c, "m1", "Hill", [("a", "Ann", 0, False), ("b", "Bob", 1, False), ("c", "Cy", 1, True)], 1)
_ci.stats_report(_c, "m1", "b", "Bob", -1, {1: 5, 2: 1, 3: 2, 4: 1, 21: 3, 22: 2}, False)
_ci.stats_parts(_c, "m1", "b", 320)
_ci.stats_report(_c, "m1", "a", "Ann", 0, {}, False)
_pub = {"matches": [{"d": 3, "map": "Hill", "win": True, "mid": "m1"}]}
_x = [r.split(chr(9)) for r in _ci._stats_rows(_c, _pub, 3, "b")]
check(_x[0] == ["X", "3", "Hill", "1", "3"] and [r[1] for r in _x[1:]] == ["Bob", "Cy", "Ann"], "match stats: header + the asker's team first (%s)" % [r[1] for r in _x[1:]])
check(_x[1][2:12] == ["1", "1", "5", "3", "2", "2", "1", "1", "320", "0"] and _x[3][4:9] == ["-1"] * 5 and _x[2][11] == "1", "match stats: own counts, unreported = -1, leaver flagged (%s)" % _x[1])
# the 13th field = the face (pool model id) of each player: stable per token, never shared in a match, every head has all the faces the list shows
_hd = [int(r[12]) for r in _x[1:]]
_pool = _ci.stats_head_pool()
check(len(_pool) >= 20 and all(len(r) == 13 for r in _x[1:]), "match stats: head pool %d heads, rows carry a head id" % len(_pool))
check(len(set(_hd)) == 3 and all(h in {m for m, _, _ in _pool} for h in _hd), "match stats: three players, three distinct pool heads (%s)" % _hd)
_h1 = _ci.stats_heads([("tok1", 0), ("tok2", 1)]); _h2 = _ci.stats_heads([("tok1", 0), ("tok9", 1), ("tok2", 1)])
check(_h1["tok1"] == _h2["tok1"] and len(set(_h2.values())) == 3, "a player's face is the same in the next match (%s %s)" % (_h1, _h2))
from clan_portrait_pool import EXPR as _EX  # noqa: E402
check(all(all(e in _EX[m] for e in _ci.MATCH_EXPR) for m, _, _ in _pool), "every pool head has neutral / happy / dead / angry / perk")
check(_ci._stats_rows(_c, _pub, 9, "b") == ["X" + chr(9) + "9" + chr(9) + chr(9) + "-" + chr(9) + "0"], "match stats: a raid with no recorded match = header only")
print("\n%d failed" % len(FAILS) if FAILS else "\nall ok")
sys.exit(1 if FAILS else 0)
