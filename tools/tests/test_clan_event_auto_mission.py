"""An event played with no mission chosen gets the event's own training (Down Enemies), so its matches count."""
import os, sys, sqlite3, json, random
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import clan
print("clan from", clan.__file__)
FAILS = []
def check(ok, what):
    print(("ok   " if ok else "FAIL ") + what)
    if not ok: FAILS.append(what)

def fresh(day, size, meta=None):
    c = sqlite3.connect(":memory:"); clan.ensure(c)
    tid = "s:1"
    cl = dict(clan.new_clan(2), day=day, healthy=size, last_mid="", last_result="")
    cl["meta"] = json.dumps(meta or {"sup": {"stock": {"food": 999, "water": 999, "med": 999, "ammo": 999, "mat": 999}}})
    clan.save(c, tid, cl)
    return c, tid

def play(c, tid, mid, downs, parts=3000):
    clan.rng.seed(1)
    return clan.apply_match(c, tid, mid, parts, False, {1: downs})

# 1. day-35 attack, no mission, 6 downs a match: auto mission, progress 18 >= 3/6/9 -> tier 3 (-20 %)
c, tid = fresh(35, 34)
_, r1 = play(c, tid, "m1", 6)
m = clan.meta_of(clan.load(c, tid)).get("m")
check(m and m["id"] == 1 and m.get("auto") == 1 and m["prog"] == 6 and m["left"] == 2 and m["ev"] == 35, "first event match: auto Down Enemies set, 6 counted (%r)" % m)
check(r1.get("mi") == 1 and r1.get("mp") == 6, "result shows the mission")
ok, _ = clan.mission_choose(c, tid, 2)[1], None
check(not clan.mission_choose(c, tid, 2)[1], "a second choice is refused while the auto mission runs")
play(c, tid, "m2", 6)
st, r3 = play(c, tid, "m3", 6)
check(r3["evt"] == 3 and r3["evk"] == clan.EV_ATTACK and st["status"] == clan.ALIVE, "settled at tier 3 (evt=%r evl=%r status=%r)" % (r3["evt"], r3.get("evl"), st["status"]))
check(r3["evl"] <= 8, "tier 3 = 20 %% of ~34 (lost %d)" % r3["evl"])
check(not clan.meta_of(st).get("m") and clan.meta_of(st).get("rep", {}).get("1") == 1, "mission cleared, completion counted")

# 2. no downs at all: still tier 0 (the auto mission never gives a free pass)
c, tid = fresh(35, 34)
for i in range(3): st, r = play(c, tid, "z%d" % i, 0)
check(r["evt"] == 0 and st["status"] == clan.DEAD, "0 downs in 3 matches: tier 0 as before (evt=%r)" % r["evt"])

# 3. player-chosen mission: unchanged (no auto flag, its own id)
c, tid = fresh(35, 34)
clan.mission_choose(c, tid, 4)
play(c, tid, "p1", 6)
m = clan.meta_of(clan.load(c, tid)).get("m")
check(m and m["id"] == 4 and "auto" not in m, "chosen mission kept (%r)" % m)

# 4. mission chosen on the 2nd event day after an auto first day: auto mission blocks it (counts kept)
# 5. practice day (no event): no mission is set
c, tid = fresh(23, 20)
play(c, tid, "q1", 6)
check(not clan.meta_of(clan.load(c, tid)).get("m"), "no event: no auto mission")
c, tid = fresh(23, 20); clan.mission_choose(c, tid, 1)
play(c, tid, "q2", 6)
m = clan.meta_of(clan.load(c, tid)).get("m")
check(m and m["ev"] == -1 and m["left"] == 2, "practice mission unchanged (%r)" % m)

# 6. growth event day 40, no mission: auto mission, growth paid by tier
c, tid = fresh(40, 30)
for i in range(3): st, r = play(c, tid, "g%d" % i, 6)
check(r["evk"] == clan.EV_GROWTH and r["evt"] == 3 and r["evg"] > 0, "growth event: tier 3 paid (evt=%r evg=%r)" % (r["evt"], r.get("evg")))

# 7. rep >= 5 on Down Enemies: fallback to another non-execution mission
check(clan.auto_event_mission({"rep": {"1": 5}}) not in (1,) and clan.auto_event_mission({"rep": {"1": 5}}) not in clan.EXEC_POOL, "rep 5 fallback = %r" % clan.auto_event_mission({"rep": {"1": 5}}))
check(clan.auto_event_mission({}) == 1, "default = Down Enemies")

# 8. joining an event mid-window (day 36, no mission): left = 2 -> settles on day 37
c, tid = fresh(36, 34)
play(c, tid, "w1", 6)
m = clan.meta_of(clan.load(c, tid)).get("m")
check(m and m["left"] == 1 and m["prog"] == 6, "mid-window start: left 1 (%r)" % m)
st, r = play(c, tid, "w2", 6)
check(r["evt"] >= 2, "settled on day 37 with 12 downs (evt=%r)" % r["evt"])

# 9. state_text / meta_text still build
c, tid = fresh(35, 34); play(c, tid, "s1", 3)
check("mi=1" in clan.meta_text(c, tid) and clan.state_text(clan.load(c, tid)).startswith("v=1"), "state/meta text")

print("\n%d failure(s)" % len(FAILS)); sys.exit(1 if FAILS else 0)
