"""Clan supplies per category (tools/clan_supply.py + clan.apply_match + the /clan.json view + the saga memory).
Run: python tools/tests/test_clan_supply.py   (plain python; temp database only)."""
import json, os, random, sqlite3, sys, tempfile
HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.dirname(HERE)
sys.path.insert(0, TOOLS)
sys.path.insert(0, os.path.join(TOOLS, "update_server"))
os.environ["T2R_SAGA_STRICT"] = "1"
import clan, clan_supply as S, clan_view, clan_chronicle_dump as DUMP, clan_saga as SG   # noqa: E402

FAILS = []
def check(cond, what):
    print(("ok   " if cond else "FAIL ") + what)
    if not cond:
        FAILS.append(what)

# ---- formula pieces
check(S.split(10, [50, 30, 20]) == [5, 3, 2] and sum(S.split(7, [1, 1, 1])) == 7 and S.split(0, [1, 2]) == [0, 0], "split: largest remainder, sums to the total")
for n in (1, 2, 5, 9, 25, 38, 100):
    nd = clan.needed(n)
    ns = S.need_split(nd, n)
    check(sum(ns.values()) == nd, "need split sums to clan.needed(%d) = %d" % (n, nd))
check(S.need_split(9, 5) == {"food": 4, "water": 3, "med": 2}, "need 9 = food 4 / water 3 / medicine 2")
g = S.intake(20, 900, {1: 10, 2: 2, 3: 1, 4: 3, 5: 4, 21: 2})
check(sum(g[k] for k in S.SURVIVAL) == 20 and g["ammo"] == 16 and g["mat"] == 11, "intake: survival goods sum to the supplies; ammo = kills + 2 headshots, materials = parts // 100 + execs")
g2 = S.intake(20, 900, {3: 6})
check(g2["med"] > g["med"] and S.intake(20, 900, {1: 10, 2: 2, 3: 1}, left=True) == {k: 0 for k in S.CATS}, "revives raise medicine; a left match brings nothing")
# ---- one day: the shortage is exactly the engine's deficit, a surplus day has no shortage
rng = random.Random(5)
bad = 0
for _ in range(400):
    n = rng.randrange(3, 40)
    need = clan.needed(n)
    sup = rng.randrange(0, need * 2)
    st0 = {k: rng.randrange(0, 6) for k in S.CATS}
    cnt = {1: rng.randrange(0, 15), 2: rng.randrange(0, 4), 3: rng.randrange(0, 4), 4: rng.randrange(0, 6), 5: rng.randrange(0, 5)}
    new, rec = S.book(st0, sup, need, n, rng.randrange(0, 3000), cnt)
    if sum(rec["short"][k] for k in S.SURVIVAL) != max(0, need - sup) or any(v < 0 for v in new.values()):
        bad += 1
    if sup >= need and any(rec["short"][k] for k in S.SURVIVAL):
        bad += 1
check(bad == 0, "400 random days: gross shortage == max(0, needed - supplies), a surplus day short of nothing, stock never negative")
# ---- stock: banked on surplus, consumed (drawn) on shortage, ammo / materials used up by the people
n = 10
need = clan.needed(n)
s1, r1 = S.book({}, need + 10, need, n, 0, {})
check(sum(s1[k] for k in S.SURVIVAL) > 0 and all(s1[k] <= 3 * r1["need"][k] for k in S.SURVIVAL), "a surplus day banks leftovers (cap 3 days of that need)")
s2, r2 = S.book(s1, 0, need, n, 0, {})
check(sum(r2["drawn"].values()) > 0 and sum(r2["net"][k] for k in S.SURVIVAL) < sum(r2["short"][k] for k in S.SURVIVAL), "a dry day draws the stock first; the net shortage is smaller")
check(all(s2[k] <= s1[k] for k in S.SURVIVAL), "the stock shrinks on a dry day")
a1, ra = S.book({"ammo": 10, "mat": 5}, need, need, n, 0, {})
check(ra["need"]["ammo"] == (n + 2) // 3 and a1["ammo"] == 10 - ra["need"]["ammo"] and a1["mat"] == 5 - ra["need"]["mat"], "the people use up ammo (ceil(N/3)) and materials (ceil(N/4)) per day")
a2, rb = S.book({}, need, need, n, 0, {})
check(rb["short"]["ammo"] == rb["need"]["ammo"] and a2["ammo"] == 0, "no ammo on hand: a shortage, never below zero")
d_days = S.book({"food": 20, "water": 20, "med": 20}, need, need, n, 0, {})[1]["days"]
check(d_days["food"] >= 1 and d_days["food"] == min(20, 3 * r1["need"]["food"]) // r1["need"]["food"], "days left = stock // need")
# ---- apply_match: the result carries r["sup"], the stock persists in meta, old results stay valid
d = tempfile.mkdtemp()
db = os.path.join(d, "t2r.db")
c = sqlite3.connect(db)
tid = "0123456789abcdef01234567"
clan.choose_side(c, tid, clan.WLF)
clan.rng = random.Random(1)
cl, r = clan.apply_match(c, tid, 101, 1800, False, {1: 8, 3: 1})            # 36 supplies vs 9 needed: surplus, stock banked
check("sup" in r and sum(r["sup"]["got"][k] for k in S.SURVIVAL) == r["supplies"] == 36, "apply_match: r['sup'].got survival goods sum to the engine's supplies")
stock = clan.meta_of(cl).get("sup", {}).get("stock", {})
check(sum(stock.get(k, 0) for k in S.SURVIVAL) > 0, "the clan's stock persists in meta['sup']")
cl2, r2 = clan.apply_match(c, tid, 102, 0, False, {})                         # idle day: 0 supplies, deficit
cl2 = clan.load(c, tid)
stock2 = clan.meta_of(cl2).get("sup", {}).get("stock", {})
check(r2["sup"]["drawn"]["food"] + r2["sup"]["drawn"]["water"] + r2["sup"]["drawn"]["med"] > 0 and stock2["food"] <= stock["food"], "the next, dry day consumes the stock")
c.commit()
# ---- the payload (backward compatible: a result without sup has no 'supplies')
v = clan_view.view(db, tid)
check(v["lastMatch"]["supplies"] == r2["supplies"] and v["supplies"]["cats"] == list(S.CATS) and v["supplies"]["need"] == r2["sup"]["need"] and v["supplies"]["stock"] == r2["sup"]["stock"],
      "payload: /clan.json carries supplies (got / need / short / drawn / net / stock / days / cause)")
cc = sqlite3.connect(db)
row = clan.load(cc, tid)
old = json.loads(row["last_result"]); old.pop("sup", None)
row["last_result"] = json.dumps(old)
clan.save(cc, tid, row); cc.commit(); cc.close()
check("supplies" not in clan_view.view(db, tid) and clan_view.view(db, tid)["lastMatch"]["supplies"] == r2["supplies"], "payload: an old result without sup has no 'supplies' key (the launcher models it)")
c.close()
# ---- saga: shortage -> hungry / sick members remember what ran short, stories mention it
seen_lack = rows_lack = 0
for fac in ("W", "S"):
    for seed in (3, 7, 11):
        st, days = DUMP.fake_week(fac, 28, seed, 14, 0.2)
        mem = st["ch"]["mem"]
        seen_lack += sum(1 for m in mem.values() if m.get("lack"))
        for day, newc, rr, m, rows in days:
            for row in rows:
                if row["lid"] == "sg/lack":
                    rows_lack += 1
                    check("{" not in row["text"] and row["text"].startswith("DAY %d:" % day), "lack scene text is finished: " + row["text"][:60]) if rows_lack <= 2 else None
check(seen_lack > 0, "hungry / sick members carry m['lack'] (the category that ran short) in the saga memory")
check(rows_lack > 0, "shortage days produce 'lack' scenes in the saga (%d)" % rows_lack)
print("\n%d failure(s)" % len(FAILS))
sys.exit(1 if FAILS else 0)
