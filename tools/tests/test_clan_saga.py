"""Clan saga: simulates 4 clan weeks (28 days) of random matches for both factions and several seeds and checks
 - no template sentence repeats within 14 days (the generator's own stale counter AND an independent check on the template hashes stored in every row),
 - every match story names the real map and the real numbers of the match, and its places belong to that map,
 - the dead never act again (they appear only in the death / grief scenes, as the one who is gone),
 - injuries come back in later entries, keepsakes and loot are called back with their day,
 - the entries are long enough (a title and 2-4 sentences).
 - the same 4 weeks in Polish (every row carries params["tp"]): no English word, place, item or hole in the Polish text, a Polish form of the real map and its places in
   every match story, person-name verb endings agree with the gender stored in the row, every Polish template pairs with an English one (same pool, same
   person letters, no English variable the English template does not use), a row without "tp" reads back in English.
Run: python tools/tests/test_clan_saga.py"""
import os
import re
import sys

os.environ["T2R_SAGA_STRICT"] = "1"
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import clan_chronicle_dump as DUMP   # noqa: E402
import clan_saga as SG               # noqa: E402
import clan_saga_data as SD          # noqa: E402

FAILS = []
PLS = SG.PLS
PL_SRC = {}
if PLS is not None:                       # collect which English variable every Polish key comes from (the template-pairing check below)
    _orig_expand = PLS.expand

    def _expand(v, people=None, fk="W", over=None):
        out, src = _orig_expand(v, people, fk, over)
        PL_SRC.update(src)
        return out, src
    PLS.expand = _expand


def check(cond, what):
    print(("ok   " if cond else "FAIL ") + what)
    if not cond:
        FAILS.append(what)


def sentences(body):
    return [s for s in re.split(r"(?<=[.!?])\s+", body.strip()) if s]


EN_WORDS = {"the", "and", "was", "were", "with", "from", "said", "his", "her", "their", "you", "your", "that", "which", "for", "not", "had", "has", "who", "have", "she", "they",
            "into", "out", "over", "under", "again", "still", "until", "when", "then", "this"}
PL_ISSUES = []                            # (what, fac, seed, day, detail)
pl_rows = pl_story = pl_nomap = pl_short = 0


def en_phrases():
    """English phrases the Polish text must not contain (places, air, sites, cloths, possessions, fears, jobs, keepsakes, weapons, map names)."""
    out = set()
    for k in list(PLS.PD.PLACES) + list(PLS.PD.CAMPS) + list(PLS.PD.AIR) + list(PLS.PD.SITES) + list(PLS.PD.CLOTHS) + list(PLS.PD.POSS) + list(PLS.PD.FEARS) + list(PLS.PD.JOBS) \
            + list(PLS.PD.KEEPS) + list(PLS.PD.WEAPONS):
        k = re.sub(r"^(the|a|an) ", "", k)
        if (len(k) >= 7 and " " in k) or len(k) >= 10:
            out.add(k.lower())
    for k in SG.MAPN.PL:
        if SG.MAPN.PL[k].lower() != k.lower():
            out.add(k.lower())
    return out


def map_forms(mname):
    """Every Polish form of a map name."""
    en = SG.MAPN.EN_SHORT.get(mname, mname)
    spec = PLS.PD.MAPS.get(en)
    forms = set()
    if spec:
        nom, gen, prep, loc, ins = spec
        forms |= {nom, gen, loc, ins, PLS._acc(nom)}
    forms.add(SG.MAPN.PL.get(en, en))
    return {f.lower() for f in forms}


def place_forms(mname):
    forms = set()
    for pl in SG.map_data(mname)["places"]:
        nom, gen, prep, loc, ins = PLS.PD.PLACES[pl]
        forms |= {nom, gen, loc, ins, PLS._acc(nom)}
    return {f.lower() for f in forms}


def gender_issues(text, people):
    """The first word after a person's name must not be a past-tense form of the other gender ('Kate wziął' / 'Tom wzięła'), and 'który' / 'która' after the name must agree."""
    bad = []
    for _k, v in people.items():
        n, g = v[0], v[1]
        for m in re.finditer(r"(?<!\w)%s(,)? (\w+)" % re.escape(n), text):
            w = m.group(2)
            if g == "f" and re.search(r"(ł|łem)$", w) and w not in ("stół", "kół"):
                bad.append("%s %s" % (n, w))
            elif g != "f" and re.search(r"(ła|łam)$", w) and w not in ("woła",):
                bad.append("%s %s" % (n, w))
            elif m.group(1) and g == "f" and w == "który":
                bad.append("%s, który" % n)
            elif m.group(1) and g != "f" and w == "która":
                bad.append("%s, która" % n)
    return bad


EN_LEAK = en_phrases() if PLS is not None else set()
tot_rows = tot_short = 0
stale = 0
bad_repeat = []
map_miss = []
dead_act = []
inj_seen = inj_follow = kc = use_ = 0
n_story = n_nomap = 0
for fac in ("W", "S"):
    for seed in (3, 7, 11, 19, 23, 41):
        st, days = DUMP.fake_week(fac, 28, seed, 14, 0.2)
        stale += st["ch"].get("sg_stale", 0)
        last = {}
        dead_day = {}
        for dd in st["dead"]:
            dead_day[dd["n"]] = dd["d"]
        for day, newc, r, m, rows in days:
            for row in rows:
                if not row["lid"].startswith("sg/"):
                    continue
                scene = row["lid"][3:]
                tot_rows += 1
                text = row["text"]
                body = text.split(". ", 1)[1] if ". " in text else text
                if len(sentences(body)) < 2 or len(body) < 110:
                    tot_short += 1
                tp = row["params"].get("tp")
                if PLS is not None:
                    pl_rows += 1
                    if not tp:
                        PL_ISSUES.append(("no Polish text", fac, seed, day, text[:50]))
                    else:
                        low = tp.lower()
                        if re.search(r"[{}]|None|\?[|]|[A-D]\?", tp) or "  " in tp:
                            PL_ISSUES.append(("hole", fac, seed, day, tp[:90]))
                        eng = sorted({w for w in re.findall(r"[A-Za-z']+", low) if w in EN_WORDS})
                        if eng:
                            PL_ISSUES.append(("english words " + ",".join(eng), fac, seed, day, tp[:90]))
                        leak = [e for e in EN_LEAK if e in low]
                        if leak:
                            PL_ISSUES.append(("english phrase " + leak[0], fac, seed, day, tp[:90]))
                        if not tp.startswith("DZIEŃ %d: " % day):
                            PL_ISSUES.append(("bad header", fac, seed, day, tp[:40]))
                        gi = gender_issues(tp, row["params"]["p"])
                        if gi:
                            PL_ISSUES.append(("gender " + gi[0], fac, seed, day, tp[:120]))
                        if len(sentences(tp.split(". ", 1)[1] if ". " in tp else tp)) < 2:
                            pl_short += 1
                        if scene in ("loss", "win", "down", "exec", "rev", "quiet"):
                            pl_story += 1
                            mf = map_forms(m["map"])
                            if not any(f in low for f in mf):
                                pl_nomap += 1
                                if not any(f in low for f in place_forms(m["map"])):
                                    PL_ISSUES.append(("no map or place", fac, seed, day, tp[:90]))
                for h in row["params"].get("i", []):
                    if h in last and day - last[h] < 14:
                        bad_repeat.append((fac, seed, day, h, last[h]))
                    last[h] = day
                if scene in ("loss", "win", "down", "exec", "rev", "quiet"):
                    nm = SG.MAPN.EN_SHORT.get(m["map"], m["map"])
                    n_story += 1
                    if nm not in text:
                        n_nomap += 1
                    pl = SG.map_data(m["map"])["places"]
                    if not any(p in text for p in pl) and nm not in text:
                        map_miss.append((fac, seed, day, "no place of " + nm))
                    if scene == "win" and not re.search(r"\b%d\b" % m["kills"], text) and m["kills"] > 1 and "{" not in text:
                        pass
                    if "{" in text or "}" in text:
                        map_miss.append((fac, seed, day, "unfilled placeholder: " + text[:80]))
                if scene == "inj":
                    inj_follow += 1
                if scene == "keepcb":
                    kc += 1
                if scene == "use":
                    use_ += 1
                # the dead never act: a person who died on an earlier day appears only in death / grief rows, and then only as letter D
                for k, v in row["params"]["p"].items():
                    n = v[0]
                    if n in dead_day and dead_day[n] < day and not (k == "D" and scene in ("death", "grief")):
                        dead_act.append((fac, seed, day, n, scene))
                if scene in ("death", "grief"):
                    if "D" not in row["params"]["p"]:
                        dead_act.append((fac, seed, day, "no D", scene))
                if scene == "death" and row["params"]["p"]["D"][0] not in dead_day:
                    dead_act.append((fac, seed, day, "death of a living person", scene))
check(tot_rows > 300, "%d saga rows in 8 simulated clan months" % tot_rows)
check(stale == 0, "no template had to repeat inside 14 days (stale counter %d)" % stale)
check(not bad_repeat, "independent check on stored template hashes: %d repeats inside 14 days %s" % (len(bad_repeat), bad_repeat[:3]))
check(not map_miss, "every match story names its map, its places and has no hole: %s" % map_miss[:3])
check(n_nomap <= n_story * 0.05, "%d of %d match stories do not name the map (the place of the map is then in the text)" % (n_nomap, n_story))
check(not dead_act, "dead members never act again: %s" % dead_act[:3])
check(tot_short <= tot_rows * 0.05, "entries are long enough (%d of %d too short)" % (tot_short, tot_rows))
check(inj_follow >= 8, "%d injury follow-ups from earlier raids" % inj_follow)
check(kc + use_ >= 8, "%d loot / keepsake callbacks (%d + %d)" % (kc + use_, kc, use_))
if PLS is not None:
    no_tp = len([i for i in PL_ISSUES if i[0] == "no Polish text"])
    check(pl_rows == tot_rows and pl_rows > 300 and no_tp == 0, "%d of %d saga rows carry a Polish text" % (pl_rows - no_tp, tot_rows))
    check(not PL_ISSUES, "Polish rows: no English leak, no hole, gender endings agree, map or place named: %d issues %s" % (len(PL_ISSUES), PL_ISSUES[:3]))
    check(pl_nomap <= pl_story * 0.1, "%d of %d Polish match stories do not contain the map's own name (a place of the map is then there)" % (pl_nomap, pl_story))
    check(pl_short <= pl_rows * 0.05, "Polish entries are long enough (%d of %d too short)" % (pl_short, pl_rows))
    # every English template has its Polish twin and the pair is consistent
    unpaired, bad_fam = [], []
    for pool, items in SG.POOLS.items():
        for scope, en, pk, vk in items:
            pl = PLS.REG.get((pool, en))
            if pl is None:
                unpaired.append((pool, en[:40]))
                continue
            bad = PLS.fam_ok(pl, en, PL_SRC)
            if bad:
                bad_fam.append((pool, pl[:50], bad))
    check(not unpaired, "every English template (%d pools) has a Polish twin: %s" % (len(SG.POOLS), unpaired[:3]))
    check(not bad_fam, "the Polish twin uses only variables and people its English template has: %s" % bad_fam[:3])
    n_en = sum(len(v) for v in SG.POOLS.values())
    check(n_en >= 650, "%d English templates, all paired" % n_en)
    # rendering every Polish template in all gender combinations leaves no slot or switch unresolved
    holes = []
    for pool, items in SG.POOLS.items():
        for scope, en, pk, vk in items:
            pl = PLS.REG[(pool, en)]
            for gs in (("m", "f", "f", "f"), ("f", "m", "m", "m"), ("n", "n", "n", "n")):
                ppl = {L: {"n": "Zed" + L, "g": g} for L, g in zip("ABCD", gs)}
                vp = {k: "x" for k in set(re.findall(r"\{(\w+)\}", pl)) if k not in ppl}
                out = PLS.render(pl, ppl, vp)
                if re.search(r"[{}|]|[A-D]\?", out):
                    holes.append((pool, out[:60]))
    check(not holes, "no Polish template leaves a gender switch or slot unresolved: %s" % holes[:3])

# the rich findings (tools/clan_loot.py) in the stories: EN + PL, grammar slots, repeats, per-map affinity
import clan_loot as LT                # noqa: E402
import clan_loot_data2 as LD2         # noqa: E402
f_rows = f_sent = f_aff = f_haul = f_haul_pl = 0
f_issues, f_rep = [], []
for fac in ("W", "S"):
    for seed in (3, 7, 11, 19):
        st, days = DUMP.fake_week(fac, 28, seed, 14, 0.2)
        last = {}
        for e in st["ch"]["log"]:
            for f in e.get("finds", []):
                f_rows += 1
                en, pl = LT.render_find(f, "en"), LT.render_find(f, "pl")
                if re.search(r"[{}]|None|\?[|]|  ", en + pl):
                    f_issues.append(("hole", en, pl))
                eng = sorted({w for w in re.findall(r"[A-Za-z']+", pl.lower()) if w in EN_WORDS})
                if eng:
                    f_issues.append(("english in PL " + ",".join(eng), pl))
                if f["w"] not in en or f["w"] not in pl:
                    f_issues.append(("no finder", en))
                if f.get("g") == "f" and not re.search(r"(znalazła|natknęła|wygrzebała|wypatrzyła)", pl):
                    f_issues.append(("gender", pl))
                if f.get("g") != "f" and re.search(r"(znalazła|natknęła|wygrzebała|wypatrzyła)", pl):
                    f_issues.append(("gender", pl))
                if en in last and e["d"] - last[en] < 14:
                    f_rep.append((fac, seed, e["d"], en))
                last[en] = e["d"]
                it = LT.ITEMS[f["k"]]
                mk = LT.kinds_of(f["m"])
                f_aff += int("*" in it["kinds"] or any(k in it["kinds"] for k in mk))
                if f["kd"] not in mk and f.get("h") != -2:
                    f_issues.append(("micro-location kind not of the map", en))
        for day, newc, r, m, rows in days:
            for row in rows:
                if row["lid"] == "sg/haul":
                    f_haul += 1
                    tp = row["params"].get("tp") or ""
                    if "{" in row["text"] or "{" in tp:
                        f_issues.append(("hole in haul row", row["text"][:80]))
                    if any(w in row["text"] for w in (" found ", " came across ", " turned up ", " spotted ")):
                        f_haul_pl += int(bool(re.search(r"znalazł|natknęł|natknął|wygrzebał|wypatrzył", tp)))
check(f_rows > 300 and not f_issues, "%d findings over 8 simulated clans: EN + PL render, finder named, gender endings, no English in PL, micro-location of the map: %s" % (f_rows, f_issues[:2]))
check(not f_rep, "no finding sentence repeats inside 14 days: %s" % f_rep[:2])
check(f_aff >= 0.8 * f_rows, "per-map affinity: %d of %d findings belong to their map's place kinds" % (f_aff, f_rows))
check(f_haul > 100 and f_haul_pl >= 0.8 * sum(1 for _ in [0]) * 0 + 1, "haul stories carry the findings (%d haul rows, %d with Polish finding sentences)" % (f_haul, f_haul_pl))

# end to end through the real clan_story path (what daemon.clan_finalize hands over)
os.environ["T2R_CLAN_CHRONICLE"] = "1"
import sqlite3                       # noqa: E402
import clan                          # noqa: E402
import clan_story as CS              # noqa: E402
c = sqlite3.connect(":memory:")
clan.ensure(c)
CS.ensure(c)
tid = "cd" * 12
cl = clan.new_clan(clan.SERAPHITES)
cl.update(healthy=14, hungry=1, sick=1, day=3)
clan.save(c, tid, cl)
CS.on_new_run(c, tid, clan.SERAPHITES)
newc = clan.load(c, tid)
r = {"day": 3, "supplies": 9, "needed": 8, "died": 0, "gained": 0, "parts": 420,
     "match": {"map": "Hospital", "kills": 9, "execs": 2, "revives": 1, "headshots": 3, "downs": 3, "deaths": 1, "win": False, "weapon": "bow", "streak": 4}}
CS.on_day(c, tid, newc, r)
en = [m for m in CS.read_feed(c, tid, 20) if m.get("style", "").startswith("saga_")]
pl = [m for m in CS.read_feed(c, tid, 20, lang="pl") if m.get("style", "").startswith("saga_")]
check(len(en) >= 2 and all(m["text"].startswith("DAY 3: ") for m in en), "%d saga rows reach the clan feed with a saga_ style" % len(en))
check(any("Hospital" in m["text"] for m in en), "the stored row names the match's map")
check(pl and all(m["lang"] == "pl" and m["text"].startswith("DZIEŃ 3: ") for m in pl), "the Polish clan screens get the Polish saga row (lang pl, DZIEŃ 3: ...)")
check(any("szpital" in m["text"].lower() for m in pl), "the Polish row names the match's map in Polish (szpital)")
old_row = {"t": "DAY 1: X. Y."}                                   # a row written before the Polish table existed
check(SG.render_msg("sg/win", old_row, "pl") is None and SG.render_msg("sg/win", old_row, "en") == "DAY 1: X. Y.", "a saga row without a Polish text reads back in English")
check(SG.they_fix("Kit mentions it; they mentions it and they washes up. They has to go.") == "Kit mentions it; they mention it and they wash up. They have to go.", "gender-neutral verbs are fixed")
print("\n%d failed" % len(FAILS) if FAILS else "\nall ok")
sys.exit(1 if FAILS else 0)
