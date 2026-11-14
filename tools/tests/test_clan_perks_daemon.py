"""Clan supply perks through the daemon: op 0xE0/0xE2 replies carry the perk tail, the match report's labels 31/32 draw the stock, the saga line lands.
Temp DB only. Run: python tools/tests/test_clan_perks_daemon.py"""
import json, os, sys, tempfile
import sys as _t2s, os as _t2o; _t2s.path.append(_t2o.path.normpath(_t2o.path.join(_t2o.path.dirname(_t2o.path.abspath(__file__)), ".."))); import t2rtmp  # noqa: E402,F401
HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.dirname(HERE)
TMP = tempfile.mkdtemp()
os.environ["T2R_DB"] = os.path.join(TMP, "t.db")
sys.path.insert(0, TOOLS)
import daemon  # noqa: E402

FAILS = []
def check(cond, what):
    print(("ok   " if cond else "FAIL ") + what)
    if not cond:
        FAILS.append(what)

TOK = "54324e3a" + "416c696365" + "00" * 11 + "0123456789abcdef01234567"
def op_e0():
    fr = daemon.clan_op(0xE0, TOK.encode())
    return fr[3:].decode() if fr else ""   # (msg(): 1 op + 2 len bytes ahead of the text - checked below)
fr = daemon.clan_op(0xE0, TOK.encode())
check(fr is not None, "0xE0 answers (no clan yet)")
body = fr[3:].decode() if fr[0] == 0xE1 else fr.decode("latin1")
daemon.clan_side(TOK, 1)
daemon.clan_match_started([TOK], "mid1")
with daemon._dblock, daemon.dbc() as c:
    try: c.execute("INSERT OR IGNORE INTO players (token) VALUES (?)", (TOK,))
    except Exception as e: print("note: players insert", e)
daemon.CLAN_MAP["mid1"] = "Hillside"
daemon.clan_report(TOK, 2400, 2, {1: 12, 2: 2, 3: 3, 4: 5})
txt = daemon.clan_op(0xE0, TOK.encode())[3:].decode()
check("pk=" in txt, "state reply carries the perk tail after a surplus day: " + txt[-140:])
check(txt.index("lmh=") < txt.index("pk="), "the perk keys come after every old key (old ext unaffected)")
with daemon._dblock, daemon.dbc() as c:
    key = daemon.clan_key(c, TOK)
    cl = daemon.clan.load(c, key)
    st0 = dict(daemon.clan_perks.stock_of(cl))
    nd = daemon.clan_perks.need_of(cl)
    m = daemon.clan.meta_of(cl)
    m["sup"] = {"stock": {"food": 0, "water": 0, "med": nd["med"] + 5, "ammo": 0, "mat": 0}}
    cl["meta"] = json.dumps(m); daemon.clan.save(c, key, cl)
txt = daemon.clan_op(0xE0, TOK.encode())[3:].decode()
check("pkc0=1 pkn0=2" in txt and "pk=1 " in txt, "only medicine has a surplus now -> one perk (medkit x2): " + txt[-100:])
# loss streak on the wire: the last 3 saga days lost -> pks=3 right after pk=1
with daemon._dblock, daemon.dbc() as c:
    key = daemon.clan_key(c, TOK)
    stq = daemon.clan_story._load(c, key)
    check(stq is not None, "a saga exists for the streak test")
    stq.setdefault("ch", {})["sg_hist"] = [{"d": 1, "map": "x", "win": True}, {"d": 2, "map": "x", "win": False}, {"d": 3, "map": "x", "win": False}, {"d": 4, "map": "x", "win": False}]
    daemon.clan_story._save(c, key, stq)
txt = daemon.clan_op(0xE0, TOK.encode())[3:].decode()
check("pk=1 pks=3 pkc0=1" in txt, "loss streak on the wire: " + txt[-110:])
daemon.clan_match_started([TOK], "mid2")
daemon.CLAN_MAP["mid2"] = "Hillside"
daemon.clan_report(TOK, 100, 2, {1: 1, 31: 2})
with daemon._dblock, daemon.dbc() as c:
    cl = daemon.clan.load(c, daemon.clan_key(c, TOK))
    after = daemon.clan_perks.stock_of(cl)
    n_rows = c.execute("SELECT COUNT(*) FROM clan_feed WHERE token_id=? AND lid='pk/use'", (daemon.clan_key(c, TOK),)).fetchone()[0]
check(after["med"] <= nd["med"] + 5 - 2 + 20, "the stock was drawn (med %d)" % after["med"])
check(n_rows == 0, "a used perk writes no feed row any more (%d)" % n_rows)
with daemon._dblock, daemon.dbc() as c:
    n_pk = sum(1 for (d,) in c.execute("SELECT data FROM clan_journal WHERE token_id=?", (daemon.clan_key(c, TOK),)) if json.loads(d).get("pk"))
check(n_pk == 1, "the day's journal entry carries the perk sentence (%d)" % n_pk)
# old daemon behaviour: perks switched off = no keys at all
os.environ["T2R_CLAN_PERKS"] = "0"
txt = daemon.clan_op(0xE0, TOK.encode())[3:].decode()
check("pk=" not in txt, "T2R_CLAN_PERKS=0: the reply is exactly the old state text")
print("\nall passed" if not FAILS else "\n%d FAILED" % len(FAILS))
sys.exit(1 if FAILS else 0)
