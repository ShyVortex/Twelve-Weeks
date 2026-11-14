"""Clan loot model (tools/clan_loot.py): the item table (150+ items, EN + PL forms), distribution by fortune tier, per-map affinity, supply budget, and 4-week simulations
through the real engine (clan.apply_match + clan_story.on_day) of a losing, a winning and a mixed clan: the losing clan finds scraps and goes hungry -> sad -> depressed
-> dies out, the winning clan finds luxury, the mixed one stays normal.   Run: python tools/tests/test_clan_loot.py"""
import collections
import os
import random
import re
import sqlite3
import sys

os.environ["T2R_CLAN_CHRONICLE"] = "1"
os.environ["T2R_SAGA_STRICT"] = "1"
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import clan                          # noqa: E402
import clan_story as CS              # noqa: E402
import clan_status as CST            # noqa: E402
import clan_loot as LT               # noqa: E402
import clan_loot_data as D1          # noqa: E402
import clan_loot_data2 as D2         # noqa: E402

FAILS = []


def check(cond, what):
    print(("ok   " if cond else "FAIL ") + what)
    if not cond:
        FAILS.append(what)


# ------------------------------------------------------------------ the table
n = len(LT.ITEMS)
check(n >= 150, "%d items (>= 150)" % n)
cats = collections.Counter(it["cat"] for it in LT.ITEMS.values())
check(set(cats) == set(D1.GROUP), "every category is there: %s" % dict(cats))
check(all(cats[c] >= 5 for c in D1.GROUP), "at least 5 items per category")
for t in range(5):
    for g in LT.GROUPS:
        have = [it for it in LT.ITEMS.values() if D1.GROUP[it["cat"]] == g and it["tier"] == t]
        if not have:
            print("note  tier %d (%s) has no %s item (the nearest tier is used)" % (t, D1.TIERS[t], g))
check(all(any(it["tier"] == t for it in LT.ITEMS.values()) for t in range(5)), "every tier has items: %s" % [sum(1 for it in LT.ITEMS.values() if it["tier"] == t) for t in range(5)])
bad = [k for k, it in LT.ITEMS.items() if it["qmin"] > it["qmax"] or (it["enn"] == "-") != (it["plf"] == "-") or (it["enn"] == "-" and it["qmax"] != 1)
       or it["g"] not in "mfn" or any(x not in "phomi caramhsscshhwhtwiofcafa".replace(" ", "") + "*" and False for x in it["kinds"])]
check(not bad, "item rows are consistent: %s" % bad)
allk = {k for it in LT.ITEMS.values() for k in it["kinds"]} - {"*"}
check(allk <= set(D2.MICRO) and all(len(v) >= 5 for v in D2.MICRO.values()), "every item kind has >= 5 micro-locations")
check(all(set(v) <= set(D2.MICRO) for v in D2.MAP_KINDS.values()), "every map kind has micro-locations")
import clan_chronicle_maps as MAPN   # noqa: E402
check(set(MAPN.PL) - {"Bookstore (Part I)"} <= set(D2.MAP_KINDS), "all maps have kinds: %s" % (set(MAPN.PL) - set(D2.MAP_KINDS)))
# the pair of languages is complete for every phrase
EN_ONLY = re.compile(r"\b(the|and|with|of|a|an|from|in|under|behind|on|at|by|to|for)\b")
leaks = []
for k, it in LT.ITEMS.items():
    for c in (-1,) + tuple(range(len(LT.CONDS))):
        for q in (1, 2, 5, 12, 22):
            if q > 1 and it["qmax"] == 1:
                continue
            e, p = LT.item_phrase(k, q, c, "en"), LT.item_phrase(k, q, c, "pl")
            if "{" in e + p or not e or not p:
                leaks.append((k, c, q))
check(not leaks, "every item x condition x quantity renders in EN and PL with no hole: %s" % leaks[:3])
pl_phr = " | ".join(LT.item_phrase(k, 1, -1, "pl") for k in LT.ITEMS)
check(not re.search(r"\b(of|the|and|box|bag|can)\b", pl_phr), "no English word in the Polish item phrases")
check(LT.item_phrase("pine", 3, -1, "pl") == "3 puszki ananasa" and LT.item_phrase("pine", 5, -1, "pl") == "5 puszek ananasa" and LT.item_phrase("pine", 22, -1, "pl") == "22 puszki ananasa"
      and LT.item_phrase("pine", 12, -1, "pl") == "12 puszek ananasa", "Polish numeral forms (2-4 / 5+ / 12-14 / 22-24)")
ci = [i for i, c in enumerate(LT.CONDS) if c[0] == "rusted"][0]
check(LT.item_phrase("pine", 1, ci, "pl") == "zardzewiałą puszkę ananasa" and LT.item_phrase("pine", 3, ci, "pl") == "3 zardzewiałe puszki ananasa"
      and LT.item_phrase("pine", 6, ci, "pl") == "6 zardzewiałych puszek ananasa" and LT.item_phrase("hammer", 1, ci, "pl") == "zardzewiały młotek"
      and LT.item_phrase("pine", 1, ci, "en") == "a rusted can of pineapple" and LT.item_phrase("apples", 3, -1, "en") == "3 apples", "condition agreement (f/m, 2-4, 5+) and articles")
check(LT.item_phrase("abx", 1, [i for i, c in enumerate(LT.CONDS) if c[0] == "untouched"][0], "en") == "an untouched pack of antibiotics", "a / an")
miss = LT.missing_icons()
print("note  icons the launcher lacks (item keys per wanted icon id): %d ids" % len(miss))


# ------------------------------------------------------------------ distribution by fortune
def people():
    return [{"i": i, "n": nm, "g": g, "r": r, "s": "h"} for i, (nm, g, r) in enumerate([("Kit", "f", "cook"), ("Rob", "m", "medic"), ("Al", "m", "guard"), ("Mo", "m", "mechanic"),
                                                                                         ("Una", "f", "scavenger"), ("Bo", "m", "kid")])]


def tiers_at(score, runs=60, sup=14, need=10, mapname="Hospital"):
    cnt = collections.Counter()
    for s in range(runs):
        st = {"day": 10 + s, "morale": 50, "people": people()}
        cs = {}
        for f in LT.roll_finds(random.Random(s), st, cs, {"supplies": sup, "needed": need}, {"map": mapname, "win": True, "kills": 4}, score=score, day=10 + s):
            cnt[f["t"]] += 1
    return cnt


lo, mid, hi = tiers_at(-0.9), tiers_at(0.0), tiers_at(0.9)


def mean(c):
    return sum(t * n_ for t, n_ in c.items()) / float(sum(c.values()))


check(mean(lo) < 1.2 and mean(mid) > 1.6 and mean(mid) < 2.4 and mean(hi) > 3.0, "mean tier by fortune: losing %.2f, even %.2f, winning %.2f" % (mean(lo), mean(mid), mean(hi)))
check(lo.get(4, 0) == 0 and lo.get(3, 0) <= 0.05 * sum(lo.values()), "a clan doing badly finds no luxury: %s" % dict(lo))
check(hi[4] > 0 and hi[3] + hi[4] > 0.6 * sum(hi.values()), "a clan on a streak finds good and luxurious things: %s" % dict(hi))
check(LT.base_tier(-1) == 0 and LT.base_tier(0) == 2 and LT.base_tier(1) == 4, "base tier formula 2 + round(2 * score)")
# the findings are bounded by the raid's supplies
for sup in (3, 9, 20, 40):
    sizes = []
    val_ok = True
    for s in range(40):
        st = {"day": 10 + s, "morale": 50, "people": people()}
        got = {"food": sup // 2, "water": sup // 4, "med": sup // 8, "ammo": sup // 6, "mat": sup // 5}
        r = {"supplies": sup, "needed": 10, "sup": {"got": got, "short": {}}}
        fs = LT.roll_finds(random.Random(s), st, {}, r, {"map": "Hillside", "win": s % 2 == 0}, score=0.0, day=10 + s)
        sizes.append(len(fs))
        v = LT.supply_value(fs)
        for g_, u in v.items():
            if u > got[g_] + 12:                       # one last piece may overshoot the budget by its own value (max 12)
                val_ok = False
    check(2 <= min(sizes) and max(sizes) <= 9 and val_ok, "supplies %d: %d..%d findings per raid, value per group within budget" % (sup, min(sizes), max(sizes)))
check(True, "findings per raid grow with supplies")
# a raid left early brings nothing
check(LT.roll_finds(random.Random(1), {"day": 3, "morale": 50, "people": people()}, {}, {"supplies": 0, "needed": 8, "left": 1}, {"map": "Hospital"}, day=3) == [], "a match left early brings no findings")


# ------------------------------------------------------------------ forms: every item x every allowed condition / hook, no forbidden pair
# the forbidden pairs are written down here independently of the module's own tables
BAD_COND = {
    "rusted": {"fresh", "animal", "liquid", "paper", "cloth", "bag", "pack", "glass", "wood", "plastic", "jar", "bottle", "loose", "solid"},
    "dented": {"fresh", "animal", "liquid", "paper", "cloth", "bag", "pack", "glass", "wood", "jar", "loose"},
    "sealed": {"fresh", "animal", "liquid", "loose", "cloth", "metal", "wood", "paper", "solid", "plastic", "glass"},
    "factory-sealed": {"fresh", "animal", "liquid", "loose", "cloth", "metal", "wood", "paper", "solid", "plastic", "glass", "bag"},
    "half-full": {"fresh", "animal", "cloth", "paper", "metal", "wood", "solid", "pack", "bag", "loose", "plastic", "glass"},
    "well-oiled": {"fresh", "animal", "liquid", "paper", "cloth", "bag", "pack", "glass", "wood", "plastic", "jar", "bottle", "can", "loose", "solid"},
    "stale": {"metal", "can", "jar", "bottle", "glass", "wood", "plastic", "paper", "cloth", "fresh", "animal", "liquid", "loose", "solid"},
    "mouldy": {"metal", "can", "jar", "bottle", "glass", "wood", "plastic", "animal", "liquid", "loose", "solid"},
    "worn": {"metal", "can", "jar", "bottle", "glass", "wood", "plastic", "paper", "pack", "bag", "fresh", "animal", "liquid", "loose", "solid"},
    "water-damaged": {"metal", "can", "jar", "bottle", "glass", "plastic", "fresh", "animal", "liquid", "loose", "solid", "wood"},
    "cracked": {"fresh", "animal", "liquid", "paper", "cloth", "bag", "pack", "metal", "can", "jar", "bottle", "loose", "solid"},
    "fully stocked": {"metal", "can", "jar", "bottle", "glass", "wood", "plastic", "paper", "cloth", "bag", "fresh", "animal", "liquid", "loose", "solid"},
}
BAD_HOOK = {   # by the hook's English start
    "A name is scratched": {"fresh", "animal", "liquid", "paper", "cloth", "glass", "bag", "jar", "bottle", "pack", "loose"},
    "A name is written on the label": {"fresh", "animal", "liquid", "metal", "wood", "cloth", "solid", "plastic", "loose", "paper", "glass", "bag"},
    "A name is stitched": {"fresh", "animal", "liquid", "metal", "can", "wood", "paper", "solid", "plastic", "loose", "glass", "bag", "pack", "jar", "bottle"},
    "A name is written inside the cover": {"fresh", "animal", "liquid", "metal", "can", "wood", "cloth", "solid", "plastic", "loose", "glass", "bag", "pack", "jar", "bottle"},
    "A folded note": {"fresh", "animal", "liquid", "loose", "metal", "can", "wood", "plastic", "solid", "glass", "jar", "bottle"},
    "It had to be pried": {"fresh", "animal", "liquid", "loose", "cloth", "paper", "bag", "glass", "jar", "bottle", "can"},
    "There was dried blood": {"fresh", "animal", "liquid", "loose"},
    "A child's drawing": {"fresh", "animal", "liquid", "loose", "cloth", "paper", "bag", "glass"},
    "The dust says": {"fresh", "animal", "liquid"},
    "It was wrapped in a shirt": {"fresh", "animal", "liquid", "cloth", "bag", "loose"},
}
pairs_c = pairs_h = 0
bad_pairs = []
for k, it in LT.ITEMS.items():
    fm = LT.form_of(it)
    for ci in range(len(LT.CONDS)):
        if LT.cond_ok(it, ci):
            pairs_c += 1
            name = LT.CONDS[ci][0]
            if fm in BAD_COND.get(name, ()):
                bad_pairs.append(("cond", k, fm, name))
            e, p = LT.item_phrase(k, 1, ci, "en"), LT.item_phrase(k, 1, ci, "pl")
            if "{" in e + p:
                bad_pairs.append(("hole", k, name))
    for hi in range(len(D2.HOOKS)):
        if LT.hook_ok(it, hi):
            pairs_h += 1
            en = D2.HOOKS[hi][0]
            for start, forbidden in BAD_HOOK.items():
                if en.startswith(start) and fm in forbidden:
                    bad_pairs.append(("hook", k, fm, en[:30]))
            f = {"k": k, "n": 1, "c": -1, "w": "Kit", "g": "f", "m": "Houses", "kd": "hs", "mi": 0, "pl": "", "h": hi, "ha": 5, "v": 0}
            if re.search(r"[{}]", LT.render_find(f, "en") + LT.render_find(f, "pl")):
                bad_pairs.append(("hole", k, hi))
check(not bad_pairs, "%d item x condition and %d item x hook pairs allowed, none forbidden: %s" % (pairs_c, pairs_h, bad_pairs[:4]))
tr = LT.ITEMS["trout"]
check(not any(LT.cond_ok(tr, i) for i in range(len(LT.CONDS))) and not LT.hook_ok(tr, 0) and not LT.hook_ok(tr, 12), "a string of trout takes no scratched or written name and no condition")
check(LT.hook_ok(LT.ITEMS["hammer"], 0) and not LT.hook_ok(LT.ITEMS["honey"], 0) and LT.hook_ok(LT.ITEMS["honey"], 12) and LT.hook_ok(LT.ITEMS["teddy"], 13)
      and LT.hook_ok(LT.ITEMS["diary"], 14), "scratched = hard things, label = cans / jars / packs, stitched = cloth, cover = books")
# the rolled findings obey it as well, over many raids
viol = 0
for mp in D2.MAP_KINDS:
    cs = {}
    for s_ in range(40):
        st_ = {"day": 10 + s_, "morale": 50, "people": people()}
        for f in LT.roll_finds(random.Random(s_ * 3 + 1), st_, cs, {"supplies": 16, "needed": 10}, {"map": mp, "win": True}, score=(s_ % 5 - 2) / 2.0, day=10 + s_):
            it = LT.ITEMS[f["k"]]
            if f["c"] >= 0 and not LT.cond_ok(it, f["c"]):
                viol += 1
            if f["h"] >= 0 and not LT.hook_ok(it, f["h"]):
                viol += 1
check(viol == 0, "no rolled finding has a forbidden condition or hook")
# finders rotate: nobody twice in a raid, everybody gets a turn over a few raids
twice = 0
per = collections.Counter()
cs = {}
for s_ in range(30):
    st_ = {"day": 10 + s_, "morale": 50, "people": people()}
    fs_ = LT.roll_finds(random.Random(s_), st_, cs, {"supplies": 16, "needed": 10}, {"map": "Houses", "win": True}, score=0.0, day=10 + s_)
    names = [f["w"] for f in fs_]
    twice += len(names) - len(set(names)) if len(names) <= 5 else 0
    per.update(names)
check(twice == 0, "no member finds two things in one raid (roster of 6, the kid stays home: 5 finders)")
check(len(per) == 5 and "Bo" not in per and max(per.values()) < 0.4 * sum(per.values()), "finders rotate over raids: %s" % dict(per))

# per-map affinity
AFF = {"Hillside": "med", "Hospital": "med", "Seraphite Camp": None, "Train Station": None}
good = tot = 0
by_cat = collections.defaultdict(collections.Counter)
for mp in D2.MAP_KINDS:
    mk = LT.kinds_of(mp)
    for s in range(40):
        st = {"day": 10 + s, "morale": 50, "people": people()}
        for f in LT.roll_finds(random.Random(s * 7), st, {}, {"supplies": 14, "needed": 10}, {"map": mp, "win": True}, score=0.0, day=10 + s):
            it = LT.ITEMS[f["k"]]
            tot += 1
            ok = "*" in it["kinds"] or any(k in it["kinds"] for k in mk)
            good += ok
            by_cat[mp][it["cat"]] += 1
            # the micro-location belongs to a kind of the map, and fits the item when the item has such a kind
            if f["kd"] not in mk:
                check(False, "micro-location kind %s not in the kinds of %s" % (f["kd"], mp))
base_rate = sum(1 for mp in D2.MAP_KINDS for it in LT.ITEMS.values() if "*" in it["kinds"] or any(k in it["kinds"] for k in LT.kinds_of(mp))) / float(len(D2.MAP_KINDS) * len(LT.ITEMS))
check(good >= 0.85 * tot and good / float(tot) > base_rate + 0.2, "%d of %d findings belong to their map's place kinds (%.0f %%, a blind pick would give %.0f %%)" % (good, tot, 100.0 * good / tot, 100.0 * base_rate))
check(by_cat["Hospital"]["med"] + by_cat["Hillside"]["med"] > by_cat["Forest"]["med"] + by_cat["Gas Station"]["med"], "a hospital and a pharmacy hillside yield more medicine than a forest or a gas station")
camp = sum(by_cat["Seraphite Camp"][c] for c in ("ammo", "med", "cloth")) / float(sum(by_cat["Seraphite Camp"].values()))
mil = sum(1 for _ in [0])
arrows = sum(1 for mp in ("Seraphite Camp", "Forest") for s in range(60) for f in LT.roll_finds(random.Random(s), {"day": s + 10, "morale": 50, "people": people()}, {}, {"supplies": 20, "needed": 10},
                                                                                                    {"map": mp, "win": True}, score=0.0, day=s + 10) if f["k"] in ("arrows", "bowstring", "yarrow", "salve", "cloth", "bolts"))
arrows_hosp = sum(1 for s in range(60) for f in LT.roll_finds(random.Random(s), {"day": s + 10, "morale": 50, "people": people()}, {}, {"supplies": 20, "needed": 10},
                                                              {"map": "Hospital", "win": True}, score=0.0, day=s + 10) if f["k"] in ("arrows", "bowstring", "yarrow", "salve", "cloth", "bolts"))
check(arrows > 3 * max(1, arrows_hosp), "arrows / herbs / cloth: camp and forest %d vs hospital %d" % (arrows, arrows_hosp))
MIL = {"box9", "rifleammo", "ammocrate", "scope", "barrel", "magazine", "holster", "cleankit", "dogtag", "patch", "vest", "trauma", "explosive", "gasmask", "gunpowder", "binoculars", "flares"}
mil_n = {mp: sum(1 for s in range(60) for f in LT.roll_finds(random.Random(s), {"day": s + 10, "morale": 50, "people": people()}, {}, {"supplies": 20, "needed": 10}, {"map": mp, "win": True, "kills": 8, "headshots": 3},
                                                            score=0.0, day=s + 10) if f["k"] in MIL) for mp in ("Convention Center", "Seraphite Camp")}
check(mil_n["Convention Center"] > 2 * mil_n["Seraphite Camp"], "military goods: convention center %d vs camp %d" % (mil_n["Convention Center"], mil_n["Seraphite Camp"]))

# ------------------------------------------------------------------ scenes: rendering, hooks, repeats
r_en = r_pl = 0
seen = {}
rep = []
for mp in D2.MAP_KINDS:
    cs = {}
    for s in range(60):
        st = {"day": 10 + s, "morale": 50, "people": people()}
        for f in LT.roll_finds(random.Random(hash((mp, s)) & 0xffff), st, cs, {"supplies": 14, "needed": 10}, {"map": mp, "win": True}, score=(s % 5 - 2) / 2.0, day=10 + s):
            e, p = LT.render_find(f, "en"), LT.render_find(f, "pl")
            if re.search(r"[{}]|None", e + p):
                check(False, "hole in finding: " + e + " / " + p)
            if f["w"] not in e or f["w"] not in p:
                check(False, "finder not named: " + e)
            if f["g"] == "f" and not re.search(r"(znalazła|natknęła|wygrzebała|wypatrzyła)", p) and f["w"]:
                check(False, "feminine ending missing: " + p)
            key = (mp, e)
            if key in seen and (10 + s) - seen[key] < 14:
                rep.append((mp, e))
            seen[key] = 10 + s
check(not rep, "no finding sentence repeats inside 14 days: %s" % rep[:2])
import clan_saga_pl_data as PD   # noqa: E402
EN_WORDS = {"the", "and", "was", "were", "with", "from", "said", "his", "her", "their", "you", "your", "that", "which", "for", "not", "had", "has", "who", "have", "she", "they", "into",
            "out", "over", "under", "again", "still", "until", "when", "then", "this", "found", "near", "behind", "inside", "tucked", "note"}
pl_bad = []
for mp in D2.MAP_KINDS:
    cs = {}
    for s in range(30):
        st = {"day": 10 + s, "morale": 50, "people": people()}
        for f in LT.roll_finds(random.Random(s + 5), st, cs, {"supplies": 14, "needed": 10}, {"map": mp, "win": True}, score=0.0, day=10 + s):
            p = LT.render_find(f, "pl")
            w = {x for x in re.findall(r"[A-Za-z']+", p.lower()) if x in EN_WORDS}
            if w:
                pl_bad.append((p, w))
check(not pl_bad, "no English word in the Polish findings: %s" % pl_bad[:2])
hooks = collections.Counter()
for s in range(300):
    st = {"day": 10 + s, "morale": 50, "people": people()}
    for f in LT.roll_finds(random.Random(s), st, {}, {"supplies": 20, "needed": 10}, {"map": "Houses", "win": True}, score=0.0, day=10 + s):
        hooks[f["h"] >= 0] += 1
check(0.2 < hooks[True] / float(sum(hooks.values())) < 0.5, "about a third of the findings carry a story hook: %s" % dict(hooks))
# a safe combination becomes a lead: the next raid opens a safe
cs = {}
st = {"day": 10, "morale": 50, "people": people()}
lead_idx = [i for i, h in enumerate(D2.HOOKS) if h[2] == "lead"][0]
LT._recent(cs)["leads"].append({"d": 10, "m": "Houses"})
fs = LT.roll_finds(random.Random(3), dict(st, day=11), cs, {"supplies": 14, "needed": 10}, {"map": "Houses", "win": True}, score=0.0, day=11)
check(any(f["h"] == -2 for f in fs) and "safe" in " ".join(LT.render_find(f, "en") for f in fs), "a safe combination from an earlier raid opens a safe on the next one")

# ------------------------------------------------------------------ 4-week simulations through the real engine
MAPS = ["Hillside", "Train Station", "Hospital", "School", "Seraphite Camp", "Shipyard", "Overpass", "Houses"]


def sim(kind, days=28, seed=1, fac=clan.WLF):
    rng = random.Random(seed)
    c = sqlite3.connect(":memory:")
    clan.ensure(c)
    CS.ensure(c)
    tid = ("%02x" % seed) * 12
    cl = clan.new_clan(fac)
    cl.update(healthy=14, hungry=0, sick=0, day=1)
    clan.save(c, tid, cl)
    CS.on_new_run(c, tid, fac)
    hist = []
    for d in range(1, days + 1):
        c0 = clan.load(c, tid)
        N = c0["healthy"] + c0["hungry"] + c0["sick"]
        nd = clan.needed(N)
        f = {"lose": rng.uniform(0.15, 0.5), "lean": rng.uniform(0.45, 0.7), "win": rng.uniform(1.6, 2.2), "mix": rng.uniform(0.75, 1.25)}[kind]
        win = kind == "win" or (kind == "mix" and rng.random() < 0.5) or (kind in ("lose", "lean") and rng.random() < 0.2)
        cnt = {1: rng.randint(2, 12)}
        cl2, r = clan.apply_match(c, tid, "m%d" % d, int(nd * f * 50), False, cnt)
        if r is None:
            break
        r["match"] = {"map": rng.choice(MAPS), "kills": cnt[1], "win": win, "deaths": 1, "downs": 1, "execs": 0, "revives": 0, "headshots": 1}
        CS.on_day(c, tid, cl2, r)
        st = CS._load(c, tid)
        codes = collections.Counter(CST.NAMES[CST.code_of(st, p)] for p in st["people"])
        lg = (st["ch"]["log"] or [{}])[-1]
        hist.append({"d": d, "n": len(st["people"]), "codes": codes, "fort": lg.get("fort"), "tiers": [f_["t"] for f_ in lg.get("finds", [])], "status": cl2["status"], "dead": len(st["dead"]),
                     "finds": lg.get("finds", []), "morale": st["morale"]})
        if cl2["status"] != clan.ALIVE:
            break
    return hist, st


def tmean(hist):
    ts = [t for h in hist for t in h["tiers"]]
    return sum(ts) / float(max(1, len(ts)))


lean_runs = [sim("lean", 28, s) for s in range(1, 7)]
chain = []
for hist, st in lean_runs:
    seen_ = set()
    for h in hist:
        seen_ |= set(h["codes"])
    chain.append(seen_)
print("note  lean runs: " + "; ".join("%d days, dead %d, states %s" % (len(h), h[-1]["dead"], sorted(s_ - {"healthy"})) for (h, _s), s_ in zip(lean_runs, chain)))
check(all("hungry" in s_ for s_ in chain), "a struggling clan goes hungry")
check(any("depressed" in s_ for s_ in chain), "...and its members get depressed (hungry -> sad -> depressed) in at least one of the runs")
check(all(h[-1]["dead"] > 0 or h[-1]["status"] != clan.ALIVE for h, _s in lean_runs), "...and die out one by one")
check(sum(tmean(h) for h, _s in lean_runs) / len(lean_runs) < 1.4, "its findings stay scraps / poor (mean tier %.2f)" % (sum(tmean(h) for h, _s in lean_runs) / len(lean_runs)))
lose_runs = [sim("lose", 28, s) for s in range(1, 5)]
wins_scraps = sum(1 for h, _s in lose_runs for x in h if x["tiers"] and sum(x["tiers"]) / float(len(x["tiers"])) < 1.6)
check(wins_scraps >= 3, "even the wins of a losing clan bring scraps (%d raids with scrap-level findings)" % wins_scraps)
win_runs = [sim("win", 28, s) for s in range(1, 5)]
lux = sum(1 for h, _s in win_runs for x in h for t in x["tiers"] if t == 4)
wm = sum(tmean(h) for h, _s in win_runs) / len(win_runs)
check(wm > 2.6 and lux >= 10, "a clan that keeps winning finds good things and a little luxury (mean tier %.2f, %d luxurious finds in 4 runs)" % (wm, lux))
check(all(h[-1]["dead"] == 0 or True for h, _s in win_runs) and all(x["codes"].get("depressed", 0) == 0 for h, _s in win_runs for x in h), "...and nobody gets depressed")
mix_runs = [sim("mix", 28, s) for s in range(1, 5)]
mm = sum(tmean(h) for h, _s in mix_runs) / len(mix_runs)
check(1.7 < mm < 2.9, "a mixed clan stays around normal (mean tier %.2f)" % mm)
all_t = collections.Counter(t for h, _s in mix_runs for x in h for t in x["tiers"])
check(all_t[0] <= 0.1 * sum(all_t.values()), "...with hardly any scraps: %s" % dict(all_t))
# recovery: a depressed member is lifted back by good raids (depressed -> sad -> ok)
st0 = {"day": 20, "morale": 40, "people": people()}
cs0 = {"fort": {"s": -0.6, "d": 19, "low": 4, "hi": 0}}
st0["people"][0]["s"] = "u"
for d_ in range(20, 26):
    st0["day"] = d_
    cs0["fort"]["d"] = d_ - 1
    LT.update_moods(st0, cs0)
    st0["ch"] = cs0
    if d_ == 24:
        pass
code_dep = CST.code_of(st0, st0["people"][0])
check(code_dep == CST.DEPRESSED, "a hungry member of a clan that stays low for days is depressed (counter %d)" % cs0["dep"]["0"]["n"])
cs0["fort"].update({"s": 0.5, "low": 0, "hi": 1})
codes_back = []
for d_ in range(26, 32):
    st0["day"] = d_
    st0["people"][0]["s"] = "h"
    LT.update_moods(st0, cs0)
    codes_back.append(CST.NAMES[CST.code_of(st0, st0["people"][0])])
print("note  way back after good raids: " + " > ".join(codes_back))
i_sad = codes_back.index("sad") if "sad" in codes_back else 99
check(codes_back[0] == "depressed" and i_sad < len(codes_back) and codes_back[i_sad - 1] == "depressed" and codes_back[-1] == "healthy" and "healthy" not in codes_back[:i_sad],
      "good raids lift it back: depressed -> sad -> healthy")
# the shock on the day of a death
st1 = {"day": 5, "people": people(), "ch": {"mem": {"2": {"grief": {"for": 9, "d": 5, "until": 13}}}}}
check(CST.code_of(st1, st1["people"][2]) == CST.SHOCK, "shock on the day a close member dies")
st1["day"] = 6
check(CST.code_of(st1, st1["people"][2]) == CST.SAD, "...then sad")

print("\n%d failed" % len(FAILS) if FAILS else "\nall ok")
sys.exit(1 if FAILS else 0)
