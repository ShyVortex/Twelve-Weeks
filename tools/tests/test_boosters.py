"""Offline tests for the one-use boosters (tools/clan.py boosters table + daemon ops 0xE8 / 0xEE).
Run: python tools/tests/test_boosters.py   (plain python; temp DB, free localhost port; never touches
tools/t2r.db or port 7001)."""
import os, sys, socket, sqlite3, struct, tempfile, threading, time
import sys as _t2s, os as _t2o; _t2s.path.append(_t2o.path.normpath(_t2o.path.join(_t2o.path.dirname(_t2o.path.abspath(__file__)), ".."))); import t2rtmp  # noqa: E402,F401  (temp hygiene: tools/t2rtmp.py)

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.dirname(HERE)
sys.path.insert(0, TOOLS)
import clan  # noqa: E402

FAILS = []
def check(cond, what):
    print(("ok   " if cond else "FAIL ") + what)
    if not cond:
        FAILS.append(what)

TOK = "54324e3a" + "426f62" + "00" * 13 + "aabbccddeeff001122334455"
assert len(TOK) == 64
tid = clan.token_id(TOK)

# ------------------------------------------------------------------ storage
tmp = tempfile.mkdtemp()
db = sqlite3.connect(os.path.join(tmp, "t2r.db"))
cnt = clan.booster_counts(db, tid)
check(set(cnt) == set(range(1, 8)) and not any(cnt.values()), "fresh player owns nothing")
check(clan.booster_grant(db, tid, 3) == 1 and clan.booster_counts(db, tid)[3] == 1, "grant one")
check(clan.booster_grant(db, tid, 3, 2) == 2 and clan.booster_counts(db, tid)[3] == 3, "grant two more")
check(clan.booster_grant(db, tid, 99) == 0, "unknown booster id refused")
check(clan.booster_consume(db, tid, 3) and clan.booster_counts(db, tid)[3] == 2, "consume one")
check(not clan.booster_consume(db, tid, 5), "consume one not owned -> False")
check(clan.booster_grant(db, tid, 1, 500) == clan.BOOSTER_MAX and clan.booster_counts(db, tid)[1] == clan.BOOSTER_MAX,
      "count capped at %d" % clan.BOOSTER_MAX)
check(clan.booster_counts(db, "other")[3] == 0, "inventory is per token id")

# ------------------------------------------------------------------ growth milestones
class Rng:                       # deterministic "random": rolls round half up, picks the first slot / first live booster
    @staticmethod
    def choice(seq): return seq[0]
    @staticmethod
    def random(): return 0.5
    @staticmethod
    def randrange(n): return 0
clan.rng = Rng
db.execute("DELETE FROM boosters")
st, ok = clan.choose_side(db, tid, clan.WLF)
check(ok and st["boost_hi"] == 1, "new clan of 5: milestone 1 already behind it")
check(clan.booster_next(st) == 5, "5 survivors: 5 more for the next booster")
st, r = clan.apply_match(db, tid, "m1", 450)             # exactly needed: no change
check(r["boosters"] == [] and sum(clan.booster_counts(db, tid).values()) == 0, "no growth, no booster")
st, r = clan.apply_match(db, tid, "m2", 1449)            # surplus 19 -> +2 survivors = 7
check(st["healthy"] == 7 and r["boosters"] == [], "7 survivors: still below 10")
st, r = clan.apply_match(db, tid, "m3", 5000)            # big surplus -> clan jumps past 10
size = st["healthy"] + st["hungry"] + st["sick"]
check(size >= 10 and len(r["boosters"]) == size // 5 - 1, "clan %d: one booster per 5 survivors crossed" % size)
check(r["boosters"] == [2, 3][:len(r["boosters"])], "the size milestones cycle the 2013 booster table: 10 -> Cheaper Ammo, 15 -> Cheaper Armor")
check([clan.threshold_booster(k) in clan.LIVE_BOOSTERS for k in range(1, 36)] == [True] * 35, "every milestone booster is a live one")
check([(k - 1) % 7 + 1 for k in (1, 2, 7, 8)] == [1, 2, 7, 1], "table order: 5 Starting Ammo ... 35 Increased Parts, 40 Starting Ammo again")
check(sum(clan.booster_counts(db, tid).values()) == len(r["boosters"]), "the boosters are in the inventory")
have = sum(clan.booster_counts(db, tid).values())
db.execute("UPDATE clans SET healthy=3 WHERE token_id=?", (tid,))    # shrinks, then grows back
st, r = clan.apply_match(db, tid, "m4", 6000)
check(r["boosters"] == [] or sum(clan.booster_counts(db, tid).values()) - have == len(r["boosters"]),
      "inventory follows the result")
check(all(b in clan.LIVE_BOOSTERS for b in r["boosters"]), "only live boosters are handed out")
st2, r2 = clan.apply_match(db, tid, "m4", 6000)
check(r2 is None, "same match twice: no second grant")
db.execute("UPDATE clans SET healthy=3, hungry=0, sick=0, boost_hi=1, last_mid='' WHERE token_id=?", (tid,))
before = sum(clan.booster_counts(db, tid).values())
st, r = clan.apply_match(db, tid, "m5", 0)               # small clan: never re-grants a size it had
check(sum(clan.booster_counts(db, tid).values()) == before, "shrinking clan: nothing granted")

# ------------------------------------------------------------------ text
db.execute("DELETE FROM boosters")
clan.booster_grant(db, tid, 2, 3)
txt = clan.meta_text(db, tid, pick=2, active=0)
check("bc2=3" in txt and "bc1=0" in txt and "bp=2" in txt and "ba=0" in txt and "bn=" in txt, "meta text: " + txt)
db.close()

# ------------------------------------------------------------------ daemon ops over TCP
s = socket.socket(); s.bind(("127.0.0.1", 0)); port = s.getsockname()[1]; s.close()
os.environ.update(T2R_HOST="127.0.0.1", T2R_PORT=str(port), T2R_CLAN_GRACE="1")
import daemon  # noqa: E402
daemon.DB_PATH = os.path.join(tmp, "daemon.db")
threading.Thread(target=daemon.tcp_server, daemon=True).start()
time.sleep(0.3)

def req(op, payload):
    c = socket.create_connection(("127.0.0.1", port), timeout=3)
    c.sendall(struct.pack("<H", len(payload) + 1) + bytes([op]) + payload)
    data = b""
    while len(data) < 2 or len(data) < 2 + struct.unpack_from("<H", data)[0]:
        b = c.recv(4096)
        if not b:
            break
        data += b
    c.close()
    ln = struct.unpack_from("<H", data)[0]
    return data[2], data[3:2 + ln].decode()

t = TOK.encode()
op, txt = req(0xE8, t)
check(op == 0xE9 and "bc1=0" in txt and "bp=0" in txt, "0xE8 fresh: " + txt)
check(" mf=%d" % daemon.flow_extra_secs() in txt, "0xE8 carries the flow's extra seconds (mf) for the ext's MATCH STARTS IN timer")
op, txt = req(0xEE, t + bytes([4]))
check("bp=0" in txt, "0xEE pick a booster not owned -> Nothing: " + txt)
with daemon._dblock, daemon.db() as c:
    clan.booster_grant(c, clan.token_id(TOK), 4, 2)
    clan.booster_grant(c, clan.token_id(TOK), 7, 1)
op, txt = req(0xEE, t + bytes([4]))
check("bp=4" in txt and "bc4=2" in txt, "0xEE pick owned booster 4: " + txt)
op, txt = req(0xEE, t + bytes([7]))
check("bp=7" in txt, "pick changed to 7: " + txt)
daemon.clan_match_started([TOK], "bm1")
op, txt = req(0xE8, t)
check("bc7=0" in txt and "bp=0" in txt and "ba=7" in txt and "bc4=2" in txt, "match start uses the pick up: " + txt)
daemon.clan_match_started([TOK], "bm2")                      # no pick -> nothing used
op, txt = req(0xE8, t)
check("bc4=2" in txt and "ba=0" in txt, "match start without a pick: nothing used: " + txt)
req(0xEE, t + bytes([4]))
daemon.clan_match_ended([TOK], "bm2")                        # a cancelled match: pick stays, nothing used
op, txt = req(0xE8, t)
check("bp=4" in txt and "bc4=2" in txt and "ba=0" in txt, "match end keeps a pending pick: " + txt)
op, txt = req(0xEE, t + bytes([0]))
check("bp=0" in txt, "pick Nothing clears it")

print()
print("FAILED: %d" % len(FAILS) if FAILS else "all passed")
sys.exit(1 if FAILS else 0)
