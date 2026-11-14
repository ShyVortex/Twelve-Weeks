"""Offline tests for the clan system (tools/clan.py + the daemon's clan ops).
Run: python tools/tests/test_clan.py   (plain python, no pytest; never touches tools/t2r.db or
port 7001: the daemon part uses a temp DB and a free localhost port)."""
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

TOK = "54324e3a" + "416c696365" + "00" * 11 + "0123456789abcdef01234567"   # T2N:Alice + id
assert len(TOK) == 64

# ------------------------------------------------------------------ rules
import random, json

class Fixed:
    """Deterministic stand-in for clan.rng: random() = r (a fraction rolls up when r < frac), randrange -> first slot."""
    def __init__(self, r=0.5): self.r = r
    def random(self): return self.r
    def randrange(self, n): return 0
    def choice(self, seq): return seq[0]
clan.rng = Fixed()

check(clan.token_id(TOK) == "0123456789abcdef01234567", "token id = bytes 20..31")
check(clan.needed(5) == 9, "needed(5) = 9 (2013 first launch screenshot)")
check(clan.needed(25) == 25, "needed(25) = 25 (2013 find match screenshot)")
check(clan.needed(38) == 36, "needed(38) = 36 (HUD 21/36: lambdas 5 + 2N and 1.2N are cut to int separately)")
check(clan.needed(7) == 5 + 14 - 8 and clan.needed(100) == 5 + 200 - 120, "needed = 5 + 2N - floor(1.2N)")
check(clan.supplies_of(1449) == 28 and clan.supplies_of(49) == 0 and clan.supplies_of(50) == 1 and clan.supplies_of(150) == 3
      and clan.supplies_of(100, 4) == 6, "supplies = bottles + trunc(parts * 0.02f)")
check(clan.week_day(0) == (1, 1) and clan.week_day(5) == (1, 6) and clan.week_day(83) == (12, 7),
      "week/day display")
check(sorted(d for d, (k, _) in clan.EVENT_DAYS.items() if k == "attack") == [15, 30, 35, 50, 65, 75, 80],
      "attack days = W3D2 W5D3 W6D1 W8D2 W10D3 W11D6 W12D4")
check(sorted(d for d, (k, _) in clan.EVENT_DAYS.items() if k == "growth") == [5, 10, 20, 25, 40, 45, 55, 60, 70],
      "growth days = the wiki's mission calendar")
check(clan.event_window(15) == 15 and clan.event_window(17) == 15 and clan.event_window(18) == -1 and clan.event_window(5) == 5
      and clan.event_window(7) == 5 and clan.event_window(8) == -1, "an event is three matches long")

c0 = clan.new_clan(clan.WLF)
c1, r = clan.resolve_day(c0, 450)                          # 9 supplies = exactly needed
check((c1["healthy"], c1["hungry"], c1["sick"], c1["day"]) == (5, 0, 0, 1), "exact supplies: no change, day+1")
c1, r = clan.resolve_day(c0, 449)                          # 8 supplies: short by 1
check(r["needed"] == 9 and r["supplies"] == 8 and r["new_hungry"] == 0 and c1["hungry"] == 0,
      "short by 1: int(0.75) = 0 go hungry")
c1, r = clan.resolve_day(c0, 1449)                         # 28 supplies: surplus 19 -> 0.1 * 19 = 1.9 -> 1 + a 90 % second one (Fixed 0.5: yes)
check(r["supplies"] == 28 and r["gained"] == 2 and c1["healthy"] == 7, "surplus 19 -> +2 survivors (1.9 rolled up)")
clan.rng = Fixed(0.99)
c1, r = clan.resolve_day(c0, 1449)
check(r["gained"] == 1 and c1["healthy"] == 6, "surplus 19 -> +1 survivor (1.9 rolled down)")
clan.rng = Fixed()
c1, r = clan.resolve_day(c0, 1)                            # deficit 9: int(0.75 * 9) = 6 healthy -> hungry, only 5 exist; then |0.3 * 9| = 2.7 rolled
check(r["new_hungry"] == 5 and r["supplies"] == 0, "deficit 9: all 5 go hungry")
check(c1["healthy"] == 0 and c1["hungry"] + c1["sick"] + r["died"] == 5, "deficit 9: nobody is healthy any more")
# the hungry -> sick step picks among ALL members (a pick on somebody already sick is wasted and costs a death)
cs = dict(c0, healthy=0, hungry=0, sick=3, meta="")
cs2, r = clan.resolve_day(cs, 1)                           # clan of 3 sick: spiral guard needs 5+; 2.7 -> 3 picks on sick members: all wasted
check(r["new_sick"] == 0 and r["died"] == 3, "3 sick, deficit: ceil(0.6 + 3 wasted picks) = 4 -> everybody dies, none is new sick")
# 2013 deaths: ceiling(0.2 * sick), so ONE sick member dies on a deficit day (the old half-up rounding let it live)
dying = dict(c0, healthy=0, hungry=0, sick=1, meta="")
c6, r = clan.resolve_day(dying, 1)
check(r["died"] == 1 and c6["status"] == clan.DEAD, "1 sick, deficit: ceil(0.2) = 1 dies")
two = dict(c0, healthy=3, hungry=0, sick=2, meta="")
c6, r = clan.resolve_day(two, 1)
check(r["died"] >= 1, "2 sick, deficit: ceil(0.4) = at least 1 dies")
# a day without a deficit kills nobody
c6, r = clan.resolve_day(dict(c0, healthy=3, hungry=0, sick=2, meta=""), 450)
check(r["died"] == 0, "no deficit: nobody dies")
big = dict(c0, healthy=0, hungry=0, sick=100, meta="")
c8, r = clan.resolve_day(big, 1)
check(r["died"] == 10 and r["new_sick"] == 0, "ceil(20) = 20 deaths clamp to 10; everybody sick: nothing new")
spiral = dict(c0, healthy=1, hungry=5, sick=94, meta="")
c9, r = clan.resolve_day(spiral, 1)
check(r["new_sick"] == 0, "90%+ sick: no new sick (downward spiral guard)")
# surplus heals: heal hungry 0.35 s, heal sick max(1, 0.3 s), both rolled, then growth 0.1 s
ill = dict(c0, healthy=0, hungry=5, sick=0, day=0, meta="")
c4, r = clan.resolve_day(ill, 1000)                        # 20 supplies, need 9 -> 11: 0.35 * 11 = 3.85 -> 3 + roll (Fixed 0.5: up)
check(r["healed"] == 4 and c4["hungry"] == 1 and c4["healthy"] == 4 + r["gained"], "surplus 11 heals 4 hungry (3.85 rolled up)")
ill = dict(c0, healthy=0, hungry=0, sick=5, meta="")
c4, r = clan.resolve_day(ill, 400)                         # 8 supplies: short by 1 (clan of 5 needs 9) -> nothing heals
check(r["healed"] == 0, "no surplus: no healing")
c4, r = clan.resolve_day(ill, 550)                         # 11 supplies: surplus 2: 0.3 * 2 = 0.6 -> at least one sick is cured
check(r["healed"] == 1 and c4["sick"] == 4, "tiny surplus cures one sick member (min 1)")
# sick AND hungry: a sick member who is also hungry stays hungry after the cure
both = dict(c0, healthy=0, hungry=0, sick=5, meta=json.dumps({"sh": 5}))
clan.rng = Fixed(0.99)
c4, r = clan.resolve_day(both, 550)
clan.rng = Fixed()
check(c4["sick"] == 4 and c4["hungry"] == 1 and json.loads(c4["meta"]).get("sh") == 4, "cured sick+hungry member is hungry again, the other 4 stay sick+hungry")
# a left match: ProcessClanDay(0, 0): the day still counts, supplies are 0
c5, r = clan.resolve_day(c0, 5000, left_early=True)
check(r["supplies"] == 0 and r["left"] == 1 and c5["hungry"] + c5["sick"] + r["died"] == 5 and c5["day"] == 1,
      "left early: the day counts with 0 supplies")
# an idle player (0 parts) gets the 2.0 multiplier: the hunger still applies but the day does not count
c5, r = clan.resolve_day(c0, 0)
check(c5["day"] == 0 and r["counted"] == 0 and c5["hungry"] + c5["sick"] + r["died"] == 5, "0 parts, played to the end: no day counted, deficit applies")
# late joiner: supplies x multiplier, a day above 1.6 does not count, a deficit is forgiven
c5, r = clan.resolve_day(c0, 300, mult=2.5, forgive=True)  # 6 supplies x 2.5 = 15: surplus 6
check(r["supplies"] == 15 and r["counted"] == 0 and c5["day"] == 0, "late join x2.5: more supplies, day not counted")
c5, r = clan.resolve_day(c0, 100, mult=1.5, forgive=True)  # 2 x 1.5 = 3 < 9: forgiven
check(r["counted"] == 1 and c5["hungry"] == 0 and c5["day"] == 1, "late join: a deficit is forgiven")
won = with_mission_late = dict(c0, day=82, meta=json.dumps({"m": {"id": 1, "prog": 9, "ev": 80, "left": 1}}))
c10, r = clan.resolve_day(won, 450)
check(c10["status"] == clan.WON and c10["day"] == 83, "83 days done = clan survived (story entry 83 = clan won)")
c10, r = clan.resolve_day(dict(c0, day=81), 450)
check(c10["status"] == clan.ALIVE, "day 82 done: still going")

# ------------------------------------------------------------------ clan events (3 matches, settled by the mission)
check(clan.event_today(15) == (clan.EV_ATTACK, 0) and clan.event_today(5)[0] == clan.EV_GROWTH
      and clan.event_today(6) == (0, 0), "event calendar lookup (announced on the start day)")
def with_mission(clan_, mid, prog, ev, left=1):
    return dict(clan_, meta=json.dumps({"m": {"id": mid, "prog": prog, "ev": ev, "left": left, "sz": 20}}))
g = dict(c0, day=7, healthy=20)                            # growth event 5, its third match; Down Enemies goals 3 / 6 / 9, need 21
g0, r = clan.resolve_day(with_mission(g, 1, 2, 5), 1500)   # 30 supplies, 2 downs: tier 0
check(r["evk"] == clan.EV_GROWTH and r["evt"] == 0 and r["evg"] == 0, "growth event, tier 0: nobody joins")
for prog, tier, join in ((3, 1, 1), (6, 2, 2), (9, 3, 2)):
    g1, r = clan.resolve_day(with_mission(g, 1, prog - 1, 5), 1050, counts={1: 1})   # exactly the 21 supplies a clan of 20 needs
    check(r["evt"] == tier and r["evg"] == join,
          "growth event: %d downs = tier %d -> ceil(clan x pct) = %d join (got %d)" % (prog, tier, join, r["evg"]))
check(clan.resolve_day(dict(g, meta=""), 1500)[1]["evt"] == 0, "no mission picked: tier 0")
mid_ev = dict(c0, day=6, healthy=20)
m1, r = clan.resolve_day(with_mission(mid_ev, 1, 0, 5, left=2), 1500, counts={1: 9})
check(r["evk"] == 0 and r["mp"] == 9 and r["ml"] == 1, "second match of the event: progress booked, nothing settled yet")
a = dict(c0, day=17, healthy=20)                           # early attack, third match: -60/-40/-20/-10 % of the clan after the day
a0, r = clan.resolve_day(with_mission(a, 1, 0, 15), 1100)  # fed exactly (22 sup >= 21): the clan stays 20
check(r["evk"] == clan.EV_ATTACK and r["evl"] == 12 and r["evt"] == 0, "attack, mission failed: lose 60 %")
a3, r = clan.resolve_day(with_mission(a, 1, 8, 15), 1100, counts={1: 1})
check(r["evt"] == 3 and r["evl"] == 2, "attack, tier 3: lose 10 %")
a1, r = clan.resolve_day(with_mission(a, 1, 2, 15), 1100, counts={1: 1})
check(r["evt"] == 1 and r["evl"] == 8, "attack, tier 1: lose 40 %")
a0, r = clan.resolve_day(dict(a, meta=""), 1100)
check(r["evl"] == 12 and r["evt"] == 0, "attack with no mission picked = no defence")
# casualties go to the weak first, 25 x 0.6f = 15.0000006 -> 16 in single precision
a25, r = clan.resolve_day(dict(c0, day=17, healthy=20, hungry=0, sick=5,
                               meta=json.dumps({"m": {"id": 1, "prog": 0, "ev": 15, "left": 1}})), 1500)
check(r["evl"] == 16 and a25["sick"] == 0, "25 survivors, -60 %: ceil(25 x 0.6f) = 16, the sick go first")
f = dict(c0, day=37, healthy=5)
f0, r = clan.resolve_day(with_mission(f, 1, 0, 35), 450)
check(f0["status"] == clan.DEAD, "late attack, mission failed: -100 % ends the clan")
f1, r = clan.resolve_day(with_mission(f, 1, 9, 35), 450, counts={1: 1})
check(f1["status"] == clan.ALIVE and f1["healthy"] == 4, "late attack, tier 3 (20 %): ceil(1.0) = 1 of 5 dies")
# repeating a mission moves its tier goals up the 2013 list
check(clan.mission_goals(1) == (3, 6, 9) and clan.mission_goals(1, 1) == (6, 9, 15) and clan.mission_goals(1, 4) == (20, 25, 35),
      "Down Enemies: 3 6 9 -> 6 9 15 -> ... -> 20 25 35 (the list, not a multiplier)")
check(clan.mission_goals(5) == (7, 14, 21) and clan.mission_goals(2) == (2, 4, 7) and clan.mission_goals(4) == (2, 4, 6),
      "2013 first-run goals: marks 7/14/21, executions 2/4/7, headshots 2/4/6")
check(clan.mission_goals(1, 3, 100) == clan.mission_goals(1, 3), "goals do not scale with the clan size")
ds = dict(c0, day=35, healthy=5, meta='{"max":12}', status=clan.DEAD, runs_lost=1)
check("mx=12" in clan.state_text(ds) and "rl=1" in clan.state_text(ds) and "ev=0" in clan.state_text(ds),
      "end state: max survivors + run history in state_text")
check("ev=2" in clan.state_text(dict(c0, day=15)) and "ev=0" in clan.state_text(dict(c0, day=14)),
      "state_text announces today's event")

# --- statistics of the rolled rules (fixed seed)
clan.rng = random.Random(7)
tot, n = 0, 400
for _ in range(n):
    _, r = clan.resolve_day(dict(c0, healthy=40, hungry=0, sick=0, meta=""), 2000)     # 40 supplies vs need 37 -> surplus 3 -> 0.3 new
    tot += r["gained"]
check(0.15 < tot / n < 0.5, "surplus 3: 0.3 survivors on average (rolled): %.2f" % (tot / n))
clan.rng = Fixed()

# ------------------------------------------------------------------ storage + migration
tmp = tempfile.mkdtemp()
dbp = os.path.join(tmp, "t2r.db")
db = sqlite3.connect(dbp)
db.execute("""CREATE TABLE players(token TEXT PRIMARY KEY, name TEXT, loadout BLOB, kills INT DEFAULT 0,
    deaths INT DEFAULT 0, wins INT DEFAULT 0, matches INT DEFAULT 0, last_seen REAL)""")   # an old DB
db.execute("INSERT INTO players(token,name) VALUES(?,?)", (TOK, "Alice"))
db.execute("CREATE TABLE clans(token_id TEXT PRIMARY KEY, faction INT, status INT, day INT, healthy INT, "
           "hungry INT, sick INT, created REAL, updated REAL)")                          # an older clans table
db.commit()
tid = clan.token_id(TOK)
st = clan.load(db, tid)
check(st["status"] == 0 and st["faction"] == 0, "no clan yet -> status 0 (CHOOSE YOUR SIDE)")
cols = {r[1] for r in db.execute("PRAGMA table_info(clans)")}
check({"last_mid", "last_result", "weeks_total"} <= cols, "older clans table migrated")
check(db.execute("SELECT name FROM players").fetchone()[0] == "Alice", "players table untouched")
st, ok = clan.choose_side(db, tid, clan.SERAPHITES)
check(ok and st["faction"] == clan.SERAPHITES and st["healthy"] == 5, "choose side -> 5 healthy Seraphites")
st, ok = clan.choose_side(db, tid, clan.WLF)
check(not ok and st["faction"] == clan.SERAPHITES, "side locked while the clan lives")
st, r = clan.apply_match(db, tid, "m1", 1449)
check(r and st["day"] == 1 and st["healthy"] == 7, "apply_match resolves a day")
st, r = clan.apply_match(db, tid, "m1", 99999)
check(r is None and st["day"] == 1, "same match id twice: ignored")
txt = clan.state_text(clan.load(db, tid))
check("fac=2" in txt and "day=1" in txt and "h=7" in txt and "need=11" in txt and "lsup=28" in txt, "state text: " + txt)
db.execute("UPDATE clans SET healthy=0,hungry=0,sick=0,status=?", (clan.DEAD,)); db.commit()
st, ok = clan.choose_side(db, tid, clan.WLF)
check(ok and st["faction"] == clan.WLF and st["day"] == 0, "dead clan: choose again, new clan")
db.close()

# ------------------------------------------------------------------ daemon ops over TCP
s = socket.socket(); s.bind(("127.0.0.1", 0)); port = s.getsockname()[1]; s.close()
os.environ.update(T2R_HOST="127.0.0.1", T2R_PORT=str(port), T2R_CLAN_GRACE="1")
import daemon  # noqa: E402
daemon.DB_PATH = os.path.join(tmp, "daemon.db")
daemon.AC = None                    # this file tests the clan arithmetic with instant 1500-part reports
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
op, txt = req(0xE0, t)
check(op == 0xE1 and "st=0" in txt, "0xE0 fresh player -> st=0: " + txt)
op, txt = req(0xE4, t + bytes([1]))
check("fac=1" in txt and "st=1" in txt and "h=5" in txt and "need=9" in txt, "0xE4 WLF: " + txt)
op, txt = req(0xE2, t + struct.pack("<IIB", 1, 1500, 0))
check("day=0" in txt, "0xE2 without a started match: no day")
daemon.clan_match_started([TOK], "mid1")
op, txt = req(0xE2, t + struct.pack("<IIB", 2, 1500, 0))        # report first, end after
daemon.clan_match_ended([TOK], "mid1")
op, txt = req(0xE0, t)
check("day=1" in txt and "lsup=30" in txt and "lleft=0" in txt and "h=7" in txt, "report then match end: " + txt)
daemon.clan_match_started([TOK], "mid2")
op, txt = req(0xE2, t + struct.pack("<IIB", 3, 1500, 1))        # no match end follows: left early
time.sleep(1.6)
op, txt = req(0xE0, t)
check("day=2" in txt and "lleft=1" in txt and "lsup=0" in txt, "no match end within the grace: left early: " + txt)
daemon.clan_match_started([TOK], "mid3")
daemon.clan_match_ended([TOK], "mid3")
op, txt = req(0xE2, t + struct.pack("<IIB", 4, 600, 0))         # end first, report after
check("day=3" in txt, "match end then report: resolved at once (reply already has day 3)")
op, txt = req(0xE2, t + struct.pack("<IIB", 5, 600, 0))
check("day=3" in txt, "a second report for the same match: ignored")
op, txt = req(0xE0, t)
check("day=3" in txt and "lparts=600" in txt, "match end then report: " + txt)

# a late joiner (daemon MM.late_mult): its day is x2.5 (above 1.6: no day counted), the supplies are scaled
daemon.clan_match_started([TOK], "mid4")
daemon.MM.late_mult[TOK] = ("mid4", 2.5)
daemon.clan_match_ended([TOK], "mid4")
op, txt = req(0xE2, t + struct.pack("<IIB", 6, 300, 0))
op, txt = req(0xE0, t)
check("day=3" in txt and "lsup=15" in txt and "lparts=300" in txt, "late join x2.5: supplies 6 x 2.5 = 15, no day counted: " + txt)
check(daemon.MM.late_mult_take(TOK, "mid4") == 1.0, "the late multiplier is used once")

# the player's own link died (report flag 4), no match end seen by the server: no left-early day
daemon.clan_match_started([TOK], "mid5")
op, txt = req(0xE2, t + struct.pack("<IIB", 7, 900, 4))
time.sleep(1.6)
op, txt = req(0xE0, t)
check("lleft=0" in txt and "lparts=900" in txt, "link lost (flag 4): parts count, not booked as left early: " + txt)

print()
print("FAILED: %d" % len(FAILS) if FAILS else "all passed")
sys.exit(1 if FAILS else 0)
