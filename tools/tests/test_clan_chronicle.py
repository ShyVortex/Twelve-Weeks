"""Clan chronicle (tools/clan_chronicle.py + clan_chronicle_text.py): templates, languages, factions, loot, repeats, stability.   Run: python tools/tests/test_clan_chronicle.py"""
import itertools
import os
import re
import sys

os.environ["T2R_CLAN_SAGA"] = "0"             # this test covers the legacy match / haul rows; the saga has tools/tests/test_clan_saga.py
HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.dirname(HERE)
sys.path.insert(0, TOOLS)
import clan_chronicle as CH            # noqa: E402
import clan_chronicle_dump as DUMP     # noqa: E402
import clan_story as CS                # noqa: E402
import clan_story_data as D            # noqa: E402

FAILS = []


def check(cond, what):
    print(("ok   " if cond else "FAIL ") + what)
    if not cond:
        FAILS.append(what)


check(len(CH.REG) >= 110, "%d chronicle pieces (>= 110)" % len(CH.REG))
# every piece renders in both languages, every gender mix, both factions it is scoped to, and nothing is left unresolved
SYM = {"f": "W", "day": 20, "when": 1, "map": "Hillside", "sup": 9, "need": 7, "kills": 11, "deaths": 3, "downs": 2,
       "loot": [["pine", 3], ["r38", 15], ["chess", 1]], "it": "r38", "itn": 15}
bad, same = [], []
for pid, (pool, sc, tone, en, pl, letters, ve, vp) in CH.REG.items():
    for fk in ("W", "S"):
        if sc not in ("*", fk):
            continue
        for gs in itertools.product("mfn", repeat=len(letters) or 1):
            people = {l: {"n": "Name" + l, "g": g, "r": "medic"} for l, g in zip(sorted(letters or "A"), gs)}
            sym = dict(SYM, f=fk)
            for lang in ("en", "pl"):
                t = CH._render_ids([pid], people, sym, lang)
                if re.search(r"[{}]", t) or "  " in t:
                    bad.append((pid, lang, t[:80]))
            if sc != "x" and CH._render_ids([pid], people, sym, "en") == CH._render_ids([pid], people, sym, "pl"):
                same.append(pid)
check(not bad, "no unresolved placeholder / double space in any rendering (%s)" % bad[:2])
check(not same, "Polish differs from English everywhere (%s)" % same[:2])
# faction vocabulary (raw templates)
leak = []
for pid, (pool, sc, tone, en, pl, *_r) in CH.REG.items():
    low = en.lower()
    if sc == "W" and any(w in low for w in D.BANNED_WOLF):
        leak.append(pid)
    if sc == "S" and any(w in low for w in D.BANNED_SERA):
        leak.append(pid)
    if sc == "*" and any(w in low for w in D.BANNED_SHARED if w.strip() not in ("stadium", "fob", "checkpoint", "barracks")):
        leak.append(pid)
check(not leak, "faction vocabulary clean (%s)" % leak[:3])
# headline sentence fits the one-line widget
long_ = []
for pool in ("match_strong", "match_even", "match_bad", "match_downs", "haul_good", "haul_short", "ration", "raid_prep", "mourn", "lastwords", "sick_watch", "hunger",
             "newcomer", "kids", "quarrel", "quiet"):
    for i in CH.BY_POOL[pool]:
        for lang, tpl in (("en", CH.REG[i][3]), ("pl", CH.REG[i][4])):
            t = CH._render_ids([i], {"A": {"n": "Alexander", "g": "m", "r": "cook"}, "B": {"n": "Katherine", "g": "f", "r": "elder"}, "D": {"n": "Bartholomew", "g": "m", "r": "guard"}},
                               dict(SYM, f="S" if CH.REG[i][1] == "S" else "W"), lang)
            first = re.split(r"(?<=[.!?])\s", t)[0]
            if len(first) > 175:
                long_.append((i, lang, len(first)))
check(not long_, "every headline's first sentence <= 175 chars with the longest names (%d over)" % len(long_))
# quantities and Polish plural forms
check([CH.qty("pine", n, "pl") for n in (1, 2, 5, 12, 22)] == ["puszkę ananasa", "2 puszki ananasa", "5 puszek ananasa", "12 puszek ananasa", "22 puszki ananasa"], "PL plurals 1 / 2 / 5 / 12 / 22")
check(CH.qty("r38", 15, "en") == "15 .38 rounds" and CH.qty("r38", 1, "en") == "a .38 round", "EN quantities")
# the week: deterministic, loot persists and comes back, repeats are rare
st1, w1 = DUMP.fake_week("W", 30, 5, 14)
st2, w2 = DUMP.fake_week("W", 30, 5, 14)
t1 = [[r["text"] for r in rows] for *_x, rows in w1]
check(t1 == [[r["text"] for r in rows] for *_x, rows in w2], "deterministic: the same clan and days give the same text")
texts = [r["text"] for *_x, rows in w1 for r in rows]
check(len(texts) >= 60 and len(texts) - len(set(texts)) <= 3, "%d rows over 30 days, %d repeats (window %d days)" % (len(texts), len(texts) - len(set(texts)), CH.WINDOW_DAYS))
pieces = [i for *_x, rows in w1 for r in rows for i in r["lid"][3:].split("+")]
share = max(pieces.count(i) for i in set(pieces)) / len(pieces)
check(share < 0.06, "most used piece is %.1f%% of all pieces (< 6%%)" % (share * 100))
check(any(r["lid"].find("loot_use_") >= 0 or r["lid"].find("use_") >= 0 for *_x, rows in w1 for r in rows), "stored loot comes back in later stories")
check(CH.ch_state(st1)["log"] and CH.match_log(st1, "pl")[0]["loot_text"], "match log with loot text in PL")
# round trip through the stored form
row = w1[0][4][0]
check(CH.render_msg(row["lid"], row["params"], "en") == row["text"] and CH.render_msg(row["lid"], row["params"], "pl") != row["text"], "stored row renders in EN and PL")
check(CS.render_msg(row["lid"], row["params"], "pl") == CH.render_msg(row["lid"], row["params"], "pl"), "clan_story.render_msg routes ch/ rows")
# persona stability
ppl = st1["people"]
p0 = ppl[0]
check(CH.persona(p0, ppl, "W") == CH.persona(dict(p0), list(reversed(ppl)), "W"), "persona is a stable function of name / role / roster")
check(CH.tagline(p0, ppl, "W", "pl") != CH.tagline(p0, ppl, "W", "en"), "tagline in both languages")
check(all(CH.portrait_id(p, "W").count("/") == 3 for p in ppl), "portrait ids faction/sex/model/expression")
check(CH.enabled() or os.environ.get("T2R_CLAN_CHRONICLE"), "switch default ON (since 10-25)")

# --- review: names, pasts by life stage, unique habits, maps, kill-only matches
import clan_story_data as _D
allnames = {*_D.FIRST_2013, *[n for n, _g in _D.EXTRA_WLF], *[n for n, _g in _D.EXTRA_SERA]}
stray = []
for fk0, sd in (("W", 5), ("S", 6), ("W", 7)):
    stx, wx = DUMP.fake_week(fk0, 20, sd, 14)
    for dayn, _nc, _r, _m, rows in wx:
        ok_names = stx["_snaps"][dayn]
        for r in rows:
            for en_pl in (r["text"], CH.render_msg(r["lid"], r["params"], "pl")):
                found = {n for n in allnames if re.search(r"(?<!\w)" + re.escape(n) + r"(?!\w)", en_pl)}
                stray += [(dayn, n) for n in found - ok_names]
check(not stray, "every name in every row (EN and PL) is a living roster member or a recently dead one (%s)" % stray[:3])
check(not any(re.search(r"\bIsaac\b", r["text"]) for *_x, rows in w1 for r in rows), "no fixed leader name in the feed")
bad_past = []
for fk0 in ("W", "S"):
    stx, _w = DUMP.fake_week(fk0, 2, 9, 40)
    for p in stx["people"]:
        pa = CH.PASTS[CH.persona(p, stx["people"], fk0, stx)["past"]]
        if p["r"] == "kid" and pa[1] != "kid":
            bad_past.append((p["r"], pa[2]))
        if p["r"] != "kid" and pa[1] == "kid":
            bad_past.append((p["r"], pa[2]))
        if p["r"] == "elder" and pa[1] == "kid":
            bad_past.append((p["r"], pa[2]))
check(not bad_past, "kids have kid pasts, adults and elders never do (%s)" % bad_past[:3])
dups = []
for fk0, sd in (("W", 1), ("S", 2), ("W", 3)):
    stx, _w = DUMP.fake_week(fk0, 15, sd, 22)
    CH.assign_habits(stx, fk0)
    hv = [CH.persona(p, stx["people"], fk0, stx)["habit"] for p in stx["people"]]
    dups.append(len(hv) - len(set(hv)))
    kidbad = [p for p in stx["people"] if p["r"] == "kid" and CH.HABIT_META[CH.persona(p, stx["people"], fk0, stx)["habit"]][0] in ("elder",)]
    check(not kidbad, "no elder habit on a kid")
check(max(dups) == 0 and len(CH.HABIT_SHORT) >= 28 and len(CH.BY_POOL["habit"]) == len(CH.HABIT_SHORT) == len(CH.HABIT_META), "habits unique inside a 22-person clan, pool of %d" % len(CH.HABIT_SHORT))
# maps: the Polish names are the game's own (tools/ext/loc_pl.h)
import clan_chronicle_maps as _MN
_loc = dict(re.findall(r'\{"([^"]+)",\s*"([^"]+)"\}', open(os.path.join(TOOLS, "ext", "loc_pl.h"), encoding="utf-8").read()))
check(all(_loc.get(en) == pl or en == "Bookstore" for en, pl in _MN.PL.items()) and CH.map_name("Hospital", "pl") == "Szpital" and CH.map_name("Bookstore (Part I)", "en") == "Bookstore",
      "map names: PL from loc_pl.h, EN display names")
# a match with only the kill count (what the daemon knows): rows still tell the match, no deaths / downs anywhere
stk = DUMP.fake_week("W", 1, 4, 12)[0]
import random as _r
ncx = {"day": 1, "healthy": 12, "hungry": 0, "sick": 0}
rows_k = CH.day_rows(stk, ncx, {"supplies": 8, "needed": 6, "parts": 400, "match": {"map": "Hospital", "kills": 7}}, rng=_r.Random(1))
mk = [r for r in rows_k if "Hospital" in r["text"] and "7" in r["text"]]
check(mk, "kill-only match row: " + (mk[0]["text"][:70] if mk else "none"))
print("\n%d failed" % len(FAILS) if FAILS else "\nall ok")
sys.exit(1 if FAILS else 0)
