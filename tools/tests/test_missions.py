"""Offline tests for the daily missions (tools/clan.py MISSIONS + daemon ops 0xEF / 0xE2 counts / 0xE8).
Run: python tools/tests/test_missions.py   (plain python; temp DB, free localhost port; never touches
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

class Rng:                       # rolls round half up, picks the first slot / first live booster
    @staticmethod
    def choice(seq): return seq[0]
    @staticmethod
    def random(): return 0.5
    @staticmethod
    def randrange(n): return 0
clan.rng = Rng

TOK = "54324e3a" + "4d6973" + "00" * 13 + "112233445566778899aabbcc"
assert len(TOK) == 64
tid = clan.token_id(TOK)

# ------------------------------------------------------------------ data (net-10.bin *net-missions*, PS4 v1.11)
check(clan.mission_goals(1) == (3, 6, 9), "Down Enemies base goals 3 / 6 / 9 (eachdaymissions.png)")
check(clan.mission_goals(1, 3) == (15, 20, 25), "3 completions: the next three entries of the 2013 list")
check(clan.mission_goals(1, 1) == (6, 9, 15), "1 completion: goals shift one place up the list")
check(clan.mission_goals(1, 99) == (45, 45, 45), "completions past the list stay on its last entry")
check(clan.mission_goals(1, 2, 100) == clan.mission_goals(1, 2), "no clan size scaling")
check(clan.tier_reward(1, 5) == (1, 1) and clan.tier_reward(2, 10) == (1, 1) and clan.tier_reward(3, 20) == (2, 2),
      "growth event tiers: ceil(clan x 5 / 7 / 10 %) survivors, 1 / 1 / 2 boosters on the first run")
check(clan.tier_reward(0, 20) == (0, 0), "tier 0: nothing")
check(clan.GROWTH == (0.0, 0.05, 0.07, 0.10) and clan.TIER_PCT == (0.05, 0.07, 0.10), "growth tiers 5 / 7 / 10 % (missions.md; the game data's 7.5 % is overruled)")
check(clan.tier_reward(2, 100) == (7, 1), "tier 2 of 100 survivors = 7")
check(clan.GROWTH_NAMES == ("FRIENDLY SURVIVORS", "DYSENTERY OUTBREAK", "MALARIA OUTBREAK", "RESCUE ALLIES", "MARAUDER ATTACK"),
      "the five growth events of missions.md")
check({clan.event_today(d)[1] for d in range(5, 81, 5) if clan.event_today(d)[0] == clan.EV_GROWTH} == {0, 1, 2, 3, 4, 5},
      "every growth event name comes up in the calendar (with SPOILED SUPPLIES, name 5)")
# ---- (re/clan-events-1117.md): INFECTED HORDE and SPOILED SUPPLIES are stories on the 2013 calendar: default on, no number moves
os.environ.pop("T2R_CLAN_NEW_EVENTS", None)
check(clan.new_events() is True, "the horde / spoiled supplies stories are on by default")
check([d for d in range(0, 85) if clan.event_today(d) == (clan.EV_ATTACK, clan.AN_HORDE)] == [30, 65], "INFECTED HORDE: the story attacks of days 30 and 65")
check([d for d in range(0, 85) if clan.event_today(d) == (clan.EV_GROWTH, clan.GN_SPOIL)] == [45, 70], "SPOILED SUPPLIES: the growth events of days 45 and 70")
check(clan.EVENT_DAYS[30] == ("attack", clan.ATTACK_EARLY) and clan.EVENT_DAYS[65] == ("attack", clan.ATTACK) and clan.EVENT_DAYS[45] == clan.EVENT_DAYS[70] == ("growth", clan.GROWTH),
      "their numbers are the calendar's: horde 60/40/20/10 % (day 30) and 100/60/40/20 % (day 65) lost, spoiled supplies +5/7/10 %")
check(clan.event_name(clan.EV_ATTACK, clan.AN_HORDE) == "INFECTED HORDE" and clan.event_name(clan.EV_GROWTH, clan.GN_SPOIL) == "SPOILED SUPPLIES"
      and clan.event_name(clan.EV_ATTACK, 0) == "ATTACK" and clan.event_name(clan.EV_GROWTH, 4) == "MARAUDER ATTACK", "event names")
_cal_on = [(d, clan.event_today(d)[0]) for d in range(0, 85)]
os.environ["T2R_CLAN_NEW_EVENTS"] = "0"
check(clan.new_events() is False and all(clan.event_today(d)[1] != clan.AN_HORDE for d in (30, 65)) and clan.event_today(45) == (clan.EV_GROWTH, 4)
      and clan.event_today(70) == (clan.EV_GROWTH, 4), "switched off (env T2R_CLAN_NEW_EVENTS=0): the 2013 names on those days")
check(_cal_on == [(d, clan.event_today(d)[0]) for d in range(0, 85)], "on or off: the same event kind on every day")
os.environ.pop("T2R_CLAN_NEW_EVENTS", None)
import tempfile as _tf
_d = _tf.mkdtemp(prefix="t2r-tmp-newev-")
_f0 = clan.NEW_EVENTS_FILE
clan.NEW_EVENTS_FILE = os.path.join(_d, "clan_events.txt"); clan._ne.update(mtime=None, val=True)
open(clan.NEW_EVENTS_FILE, "w").write("off\n")
check(clan.new_events() is False, "switched off by the file tools/clan_events.txt")
clan.NEW_EVENTS_FILE = _f0; clan._ne.update(mtime=None, val=True)
check(clan.attack_story(32) == clan.AN_HORDE and clan.attack_story(33) == clan.AN_HORDE and clan.attack_story(37) == clan.AN_ENEMY and clan.attack_story(12) == clan.AN_ENEMY,
      "a death's day tells which attack it was")
check(clan.ATTACK_PARTS_BONUS == 0.10, "attack event: +10 % parts")
src = open(os.path.join(TOOLS, "ext", "t2r-ext.c"), encoding="utf-8", errors="replace").read()
check('award(ab, slot, "Attack Bonus")' in src and "ev_attack_now()" in src and src.count('strcmp(lab, "Attack Bonus")') >= 3,
      "ext: the attack bonus is booked as an award row (and excluded from other bonus rows)")
check("mis_down_book(w, victim)" in src and '"Shiv Kill"' in src and "MIS_LONG_RANGE_M" in src, "ext: weapon-bound down missions are counted")
check(all(len(g[2]) == 8 for g in clan.MISSIONS.values()), "every mission has the 8 goals of the 2013 list")
check(clan.BOOSTER_ROWS[:4] == (1, 1, 2, 2) and max(clan.BOOSTER_ROWS) == 3, "boosters per tier grow with the completions: 1 1 2 2 3 ...")

# ------------------------------------------------------------------ storage + a practice mission (no event: pays nothing)
tmp = tempfile.mkdtemp()
db = sqlite3.connect(os.path.join(tmp, "t2r.db"))
st, ok = clan.choose_side(db, tid, clan.WLF)
check(clan.mission_choose(db, tid, 99) == (clan.load(db, tid), False), "unknown mission refused")
st, ok = clan.mission_choose(db, tid, 6)
check(ok and clan.meta_of(st)["m"]["id"] == 6, "Heal Teammates is live (always listed): choosable")
db.execute("UPDATE clans SET meta='' WHERE token_id=?", (tid,))
st, ok = clan.mission_choose(db, tid, 8)
check(not ok, "a pool mission (Down with Molotovs) is refused when it is not in the rolled pool")
import collections
sizes = collections.Counter()
for _ in range(200):
    db.execute("UPDATE clans SET meta='' WHERE token_id=?", (tid,))
    t = clan.meta_text(db, tid)
    sizes[len([x for x in t.split() if x[0] == "p" and x[1].isdigit()])] += 1
check(set(sizes) == {1, 2, 3}, "200 rolls give pools of 1, 2 and 3 (never more): %s" % dict(sizes))
check(len(clan.EXEC_POOL) == 13 and all(clan.MISSIONS[i][3] for i in clan.EXEC_POOL), "13 gun missions: every primary / secondary gun of GEAR UP")
# missions.md: ids 6..20 are live; ids 7..20 join the gun-execution missions in the random pool
check(all(clan.MISSIONS[i][3] for i in range(1, 21)), "missions 1..20 are all live (missions.md)")
check(clan.OFFER_POOL == tuple(range(7, 21)) + clan.EXEC_POOL and 6 not in clan.OFFER_POOL, "the pool holds 7..20 + the gun executions; 6 is always listed")
check(clan.MISSIONS[8][0] == "Down with Molotovs" and clan.MISSIONS[9][0] == "Down with Nail Bombs" and clan.MISSIONS[10][0] == "Give Crafting Items",
      "names follow missions.md")
seen = set()
for _ in range(300):
    db.execute("UPDATE clans SET meta='' WHERE token_id=?", (tid,))
    t = clan.meta_text(db, tid)
    seen |= {int(x[x.index("=") + 1:]) for x in t.split() if x[0] == "p" and x[1].isdigit() and "=" in x}
check(set(range(7, 21)) <= seen and seen <= set(clan.OFFER_POOL), "300 rolled pools offer every new mission and nothing outside the pool: %s" % sorted(seen))
for mid in range(7, 21):
    db.execute("UPDATE clans SET meta=? WHERE token_id=?", ('{"pool":[%d]}' % mid, tid))
    st, ok = clan.mission_choose(db, tid, mid)
    check(ok and clan.meta_of(st)["m"]["id"] == mid, "mission %d (%s) chosen from its pool" % (mid, clan.MISSIONS[mid][0]))
    st, r = clan.apply_match(db, tid, "n%d" % mid, 450, counts={mid: 4})
    check(r["mi"] == mid and r["mp"] == 4, "mission %d: the ext's label-%d count is booked as progress" % (mid, mid))
    db.execute("UPDATE clans SET meta='', day=0 WHERE token_id=?", (tid,))
st, ok = clan.mission_choose(db, tid, 1)
check(ok, "choose Down Enemies")
txt = clan.meta_text(db, tid)
check("mi=1" in txt and "mp=0" in txt and "ml=3" in txt and "mg1=3 mg2=6 mg3=9" in txt and "mev=0" in txt, "meta text: " + txt)
st, ok = clan.mission_choose(db, tid, 2)
check(not ok and "mi=1" in clan.meta_text(db, tid), "a second mission while one runs: refused")

st, r = clan.apply_match(db, tid, "a1", 450, counts={1: 2})
check(r["mi"] == 1 and r["mp"] == 2 and r["ml"] == 2 and r["mt"] == 0, "match 1: progress 2, 2 left")
check("lmi=1" in clan.meta_text(db, tid) and "lmp=2" in clan.meta_text(db, tid), "last-match mission fields")
st, r = clan.apply_match(db, tid, "a2", 450, left_early=True, counts={1: 1})
check(clan.meta_of(st)["m"]["prog"] == 3 and clan.meta_of(st)["m"]["left"] == 1 and st["day"] == 2,
      "a match left early: its progress counts and the day is used (ProcessClanDay(0, 0))")
st, r = clan.apply_match(db, tid, "a3", 450, counts={1: 6, 2: 9})        # other labels are ignored; 3 + 6 = 9 downs
check(r["mp"] == 9 and r["mt"] == 3 and r.get("mdone") == 1 and r["ms"] == 0 and r["mb"] == 0,
      "a practice mission ends after its third match and pays nothing")
check("m" not in clan.meta_of(st) and not clan.meta_of(st).get("rep"), "practice: no mission left, no completion counted")
check(clan.mission_choose(db, tid, 1)[1], "a new mission can be chosen")

# ------------------------------------------------------------------ an event mission (day 5 growth event: three matches)
db.execute("UPDATE clans SET day=5, healthy=20, hungry=0, sick=0, meta='' WHERE token_id=?", (tid,))
st, ok = clan.mission_choose(db, tid, 1)
mm = clan.meta_of(st)["m"]
check(ok and mm["ev"] == 5 and mm["left"] == 3, "chosen on the event's first day: bound to the event, three matches")
txt = clan.meta_text(db, tid)
check("mev=1" in txt and "ml=3" in txt, "meta text: " + txt)
st, r = clan.apply_match(db, tid, "b1", 1050, counts={1: 4})
st, r = clan.apply_match(db, tid, "b2", 1050, counts={1: 3})
check(r["evk"] == 0 and r["mp"] == 7 and r["ml"] == 1, "two matches in: nothing settled yet")
boost0 = sum(clan.booster_counts(db, tid).values())
st, r = clan.apply_match(db, tid, "b3", 1050, counts={1: 0})             # 7 downs: tier 2 (goal 6)
check(r["evk"] == clan.EV_GROWTH and r["evt"] == 2 and r["mt"] == 2 and r["evg"] == 2 and r["ms"] == 2,
      "third match: 7 downs = tier 2 -> ceil(20 x 7 %) = 2 join")
check(st["healthy"] == 22 and r["mb"] == 1 and sum(clan.booster_counts(db, tid).values()) >= boost0 + 1, "tier 2 pays a booster")
check("m" not in clan.meta_of(st) and clan.meta_of(st)["rep"] == {"1": 1}, "mission over, repeat count 1")
check(clan.mission_goals(1, 1) == (6, 9, 15), "Down Enemies now asks for 6 / 9 / 15")
txt = clan.meta_text(db, tid)
check("mi=0" in txt and "mr1=1" in txt and "lms=2" in txt, "meta text after: " + txt)
check(clan.mission_choose(db, tid, 1)[1], "a new mission can be chosen")

# an event nobody trained for: nothing joins, no completion counted
db.execute("UPDATE clans SET day=10, healthy=20, hungry=0, sick=0, meta='' WHERE token_id=?", (tid,))
clan.mission_choose(db, tid, 3)
st, r = clan.apply_match(db, tid, "c1", 1050, counts={})
st, r = clan.apply_match(db, tid, "c2", 1050, counts={})
st, r = clan.apply_match(db, tid, "c3", 1050, counts={3: 1})
check(r["mt"] == 0 and r["ms"] == 0 and r["evg"] == 0 and not clan.meta_of(st).get("rep"), "failed event mission: nothing")

# a mission completed five times is greyed out (the 2013 list)
db.execute("UPDATE clans SET day=20, meta=? WHERE token_id=?", ('{"rep":{"1":5}}', tid))
check(not clan.mission_choose(db, tid, 1)[1] and clan.mission_choose(db, tid, 2)[1], "Down Enemies greyed out after 5 completions")

# a practice mission that runs into an event is dropped: the picker comes back for the event's mission
db.execute("UPDATE clans SET day=3, healthy=20, hungry=0, sick=0, meta='' WHERE token_id=?", (tid,))
clan.mission_choose(db, tid, 3)
st, r = clan.apply_match(db, tid, "d1", 1050, counts={3: 1})
st, r = clan.apply_match(db, tid, "d2", 1050, counts={3: 1})              # day 5 starts next: the practice mission goes
check("m" not in clan.meta_of(st) and st["day"] == 5, "a practice mission is dropped when an event starts")

# clan dies mid-mission: mission void; new clan has none
clan.mission_choose(db, tid, 3)
db.execute("UPDATE clans SET healthy=0, hungry=0, sick=1 WHERE token_id=?", (tid,))
st, r = clan.apply_match(db, tid, "e1", 1, counts={3: 5})
st2 = clan.load(db, tid)
check(st2["status"] == clan.DEAD and not clan.meta_of(st2).get("m"), "a dead clan has no mission")
st, ok = clan.choose_side(db, tid, clan.SERAPHITES)
check(ok and not clan.meta_of(st).get("m"), "new clan after death: no mission")
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
op, txt = req(0xEF, t + bytes([1]))
check(op == 0xE9 and "mi=0" in txt, "0xEF with no clan: refused: " + txt)
req(0xE4, t + bytes([1]))
op, txt = req(0xEF, t + bytes([1]))
check("mi=1" in txt and "ml=3" in txt, "0xEF choose Down Enemies: " + txt)
op, txt = req(0xEF, t + bytes([2]))
check("mi=1" in txt, "0xEF second mission refused: " + txt)

def report(mid, seq, counts):
    daemon.clan_match_started([TOK], mid)
    tail = bytes([len(counts)]) + b"".join(struct.pack("<BH", k, v) for k, v in counts.items())
    req(0xE2, t + struct.pack("<IIB", seq, 450, 0) + tail)
    daemon.clan_match_ended([TOK], mid)
    return req(0xE8, t)[1]

txt = report("d1", 1, {1: 4, 3: 1})
check("mi=1" in txt and "mp=4" in txt and "ml=2" in txt, "0xE2 with counts: progress 4: " + txt)
txt = report("d2", 2, {1: 3})
check("mp=7" in txt and "ml=1" in txt, "progress 7: " + txt)
txt = report("d3", 3, {})                                   # old-style report without a tail is fine too
check("mi=0" in txt and "lmt=2" in txt and "lms=0" in txt, "practice mission over after 3 matches (pays nothing): " + txt)
daemon.clan_match_started([TOK], "d4")
req(0xE2, t + struct.pack("<IIB", 4, 450, 0))              # 9-byte payload (no tail) still parses
daemon.clan_match_ended([TOK], "d4")
op, txt = req(0xE0, t)
check("day=4" in txt, "old 0xE2 payload still resolves the day: " + txt)

print()
print("FAILED: %d" % len(FAILS) if FAILS else "all passed")
sys.exit(1 if FAILS else 0)
