"""The rich good-state ticker (happy members often had very short statuses without much connection or detail).
Rows: tools/clan_story_good_rich.py (EN + PL side by side).   Run: python tools/tests/test_clan_story_rich.py   (no DB needed for most checks)."""
import itertools, os, re, sqlite3, sys, tempfile
import sys as _t2s, os as _t2o; _t2s.path.append(_t2o.path.normpath(_t2o.path.join(_t2o.path.dirname(_t2o.path.abspath(__file__)), ".."))); import t2rtmp  # noqa: E402,F401  (temp hygiene: tools/t2rtmp.py)

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.dirname(HERE)
sys.path.insert(0, TOOLS)
import clan, clan_story as CS, clan_story_data as D, clan_story_good_rich as RG, clan_story_pl as PL, clan_story_solo as SO  # noqa: E402

FAILS = []
def check(cond, what):
    print(("ok   " if cond else "FAIL ") + what)
    if not cond:
        FAILS.append(what)

ROWS = RG.ROWS
check(len(ROWS) >= 150, "%d rich good-state templates (>= 150)" % len(ROWS))
check(len({e for _s, e, _p in ROWS}) == len(ROWS) and len({p for _s, _e, p in ROWS}) == len(ROWS), "every English and Polish template is unique")
check(not [e for _s, e, _p in ROWS if re.search(r"\bis healthy\b", e)] and not [p for _s, _e, p in ROWS if "jest zdrow" in p], "no bare \"X is healthy.\" in the rich pool")
check(all(PL.lid("t:g", e) in PL.REG for _s, e, _p in ROWS), "every row is in the Polish registry (pool t:g)")
# the people a row names are the same in both languages, the variables of the Polish one exist in the English one
bad = [e for _s, e, p in ROWS if PL.tpl_letters(e) != PL.tpl_letters(p) or not PL.tpl_vars(p) <= PL.tpl_vars(e)]
check(not bad, "EN / PL name the same people and use the same variables (%s)" % bad[:2])
need_b = sum(1 for _s, e, _p in ROWS if "B" in PL.tpl_letters(e))
check(need_b >= 0.9 * len(ROWS), "%d / %d rows link the member to another member (B)" % (need_b, len(ROWS)))
check(sum(1 for _s, e, _p in ROWS if "C" in PL.tpl_letters(e)) >= 10 and sum(1 for _s, e, _p in ROWS if "D" in PL.tpl_letters(e)) >= 8, "story links: >= 10 rows with a third member, >= 8 that remember the dead")
check(sum(1 for _s, e, _p in ROWS if "{day}" in e or "{week}" in e) >= 12, ">= 12 rows carry the day / week number")
check(sum(1 for s, _e, _p in ROWS if s == "W") >= 12 and sum(1 for s, _e, _p in ROWS if s == "S") >= 12, ">= 12 Wolf-only and >= 12 Seraphite-only rows")

# lengths: worst case names (longest in the pools), both languages, every gender mix; Polish gender switches must also render
names = sorted({*D.FIRST_2013, *[n for n, _g in D.EXTRA_WLF], *[n for n, _g in D.EXTRA_SERA]}, key=len)[-6:]
SYMS = [{"f": "W", "day": 188, "week": 27, "place": "pharmacy block", "inf": "bloater"}, {"f": "S", "day": 188, "week": 27, "place": "weaving house", "inf": "bloater"},
        {"f": "W", "day": 188, "week": 27, "place": "east barracks", "inf": "stalker"}, {"f": "W", "day": 99, "week": 14, "place": "loading dock", "inf": "clicker"}]
over, broken = [], []
for scope, en, pl in ROWS:
    for sym in SYMS:
        if scope not in ("*", sym["f"]):
            continue
        for gs in itertools.product("mf", repeat=2):
            ppl = {k: {"n": names[i], "g": gs[i % 2], "i": i} for i, k in enumerate("ABCD")}
            ppl_en = {k: {"n": v["n"], "g": v["g"]} for k, v in ppl.items()}
            e = CS.render(en, ppl_en, CS.expand_en(sym))
            p = PL.render(pl, ppl_en, PL.expand(sym))
            if "{" in e + p or "}" in e + p or "|" in e + p or "?" in p.replace("?\"", "").replace("?”", "") and "{A?" in p:
                broken.append((en[:40], e, p))
            if len(e) > CS.WIDGET_MAX or len(p) > CS.WIDGET_MAX:
                over.append((len(e), len(p), e if len(e) >= len(p) else p))
check(not broken, "all rows render in EN and PL with no placeholder left (%s)" % broken[:2])
check(not over, "every rendering fits the widget (<= %d chars) with the longest names: %d over (%s)" % (CS.WIDGET_MAX, len(over), sorted(over)[-3:]))

# faction vocabulary in English (the Polish side is checked by test_clan_story_pl.py over the registry)
def banned(text, words):
    t = " " + text.lower() + " "
    return [w for w in words if w in t]
bad_s = [(e[:50], banned(e, D.BANNED_SERA)) for s, e, _p in ROWS if s in ("*", "S") and banned(e, D.BANNED_SERA)]
bad_w = [(e[:50], banned(e, D.BANNED_WOLF)) for s, e, _p in ROWS if s in ("*", "W") and banned(e, D.BANNED_WOLF)]
check(not bad_s and not bad_w, "faction vocabulary in the rich rows (%s)" % (bad_s + bad_w)[:3])

# ---------------------------------------------------------------- a real clan: what a healthy member says, and how often
tmp = tempfile.mkdtemp()
c = sqlite3.connect(os.path.join(tmp, "r.db"))
def make(tid, fac, h, u, s, dead=()):
    clan.save(c, tid, {"faction": fac, "status": 1, "day": 12, "healthy": h, "hungry": u, "sick": s})
    st = CS.ensure_roster(c, tid)
    st["dead"] = [{"i": 100 + i, "n": n, "g": g, "r": "scavenger", "d": 5, "c": cause, "il": "", "k": 0} for i, (n, g, cause) in enumerate(dead)]
    CS._save(c, tid, st)
    return st
T0 = 1_800_000_000
seen_all = []
for fac, tid in ((clan.WLF, "w1"), (clan.SERAPHITES, "s1")):
    make(tid, fac, 7, 1, 1, [("Lev", "m", "starved")])
    for lang in ("en", "pl"):
        lines = []
        for k in range(60):
            lines += [t for _i, t in CS.live_lines(c, tid, 6, lang, now=T0 + k * CS.SLOT_S)]
        seen_all += lines
        check(not [t for t in lines if re.search(r"\bis healthy\b|\bjest zdrow", t)], "%s %s: no bare healthy line in %d ticker lines" % (tid, lang, len(lines)))
        check(all(len(t) <= CS.WIDGET_MAX and "…" not in t and "{" not in t for t in lines), "%s %s: every line within the widget limit, nothing cut" % (tid, lang))
        check(len({t for t in lines}) >= 0.85 * len(lines), "%s %s: %d distinct of %d ticker lines" % (tid, lang, len({t for t in lines}), len(lines)))
long_healthy = [t for t in seen_all if len(t) >= 60]
check(len(long_healthy) >= 0.55 * len(seen_all), "most ticker lines are detailed (>= 60 chars): %d / %d" % (len(long_healthy), len(seen_all)))
# the lines name real companions: every name in a line is a living member or the dead one
st = CS.ensure_roster(c, "w1")
alive = {p["n"] for p in st["people"]}
known = alive | {"Lev"}
all_names = {*D.FIRST_2013, *[n for n, _g in D.EXTRA_WLF], *[n for n, _g in D.EXTRA_SERA]}
stray = []
for k in range(40):
    for _i, t in CS.live_lines(c, "w1", 6, "en", now=T0 + k * CS.SLOT_S):
        for w in re.findall(r"[A-Z][a-z]+", t):
            if w in all_names and w not in known:
                stray.append((w, t))
check(not stray, "every person a line mentions is in the clan (%s)" % stray[:2])

# no template repeats inside a short window per clan: the healthy class cycles a pool of > 100 templates
st = make("w2", clan.WLF, 9, 0, 0)
keys, rows = [], []
for k in range(120):
    for r in CS._slot_recs(st, "w2", T0 // 60 + k):
        keys.append(r["key"])
last, gaps = {}, []
for i, key in enumerate(keys):
    if key in last:
        gaps.append(i - last[key])
    last[key] = i
check(len(set(keys)) >= 100, "720 healthy-clan lines use %d different templates" % len(set(keys)))
check(not gaps or min(gaps) >= 24, "a template never comes back within 24 lines (closest repeat: %s)" % (min(gaps) if gaps else "none"))
# determinism
a = [(r["key"], r["people"]["A"]["n"]) for r in CS._slot_recs(st, "w2", 12345)]
b = [(r["key"], r["people"]["A"]["n"]) for r in CS._slot_recs(CS.ensure_roster(c, "w2"), "w2", 12345)]
check(a == b, "the same slot gives the same lines")
# a clan of two or three: rows that need a third member / the dead are never drawn; crowd words never in a clan of two
for h in (2, 3):
    st = make("tiny%d" % h, clan.WLF, h, 0, 0)
    got = [r for k in range(40) for r in CS._slot_recs(st, "tiny%d" % h, T0 // 60 + k)]
    check(all(("C" not in r["people"]) or h >= 3 for r in got) and all("D" not in r["people"] for r in got), "clan of %d: no third member / no dead in a line" % h)
    if h == 2:
        check(not [r for r in got if SO.CROWD_RE.search(r["tpl"])], "clan of 2: no crowd words")
# a sick or hungry member keeps the 2013 sick / hungry lines (dark states still work) and they never name a sick companion as healthy
st = make("mix", clan.WLF, 3, 2, 2)
pools = {r["pool"] for k in range(60) for r in CS._slot_recs(st, "mix", T0 // 60 + k)}
check({"t:g", "t:s", "t:u"} <= pools, "mixed clan uses rich healthy lines AND the sick / hungry pools (%s)" % sorted(pools))
comp_sick = []
for k in range(60):
    for r in CS._slot_recs(st, "mix", T0 // 60 + k):
        for key in "BC":
            if key in r["people"] and r["people"][key]["s"] != "h":
                comp_sick.append(r["tpl"])
check(not comp_sick, "companions in a good-state line are healthy members")
print("\nFAILED: %d" % len(FAILS) if FAILS else "\nall passed")
sys.exit(1 if FAILS else 0)
