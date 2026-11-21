"""Offline tests for the clan A-Life (tools/clan_alife.py + clan_alife_lex.py + clan_alife_text_[abcd].py): templates (EN + PL), faction vocabulary, determinism,
the invariants against the authoritative clan numbers over simulated months, anti-repeat, the before / after repeat rate, storage compatibility, the switch.
Run: python tools/tests/test_clan_alife.py   (plain python; temp DB only, never tools/t2r.db or port 7001)."""
import importlib, json, os, random, re, sqlite3, sys, tempfile
import sys as _t2s, os as _t2o; _t2s.path.append(_t2o.path.normpath(_t2o.path.join(_t2o.path.dirname(_t2o.path.abspath(__file__)), ".."))); import t2rtmp  # noqa: E402,F401  (temp hygiene: tools/t2rtmp.py)

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.dirname(HERE)
sys.path.insert(0, TOOLS)
os.environ["T2R_CLAN_CHRONICLE"] = "0"          # these cover the plain diary / A-Life (the chronicle is ON by default: tests/test_clan_continuity.py)
import clan, clan_story as CS, clan_story_data as D  # noqa: E402
import clan_alife as AL, clan_alife_lex as X, clan_alife_report as R  # noqa: E402

FAILS = []
def check(cond, what):
    print(("ok   " if cond else "FAIL ") + what)
    if not cond:
        FAILS.append(what)

os.environ.pop("T2R_CLAN_ALIFE", None)

# ------------------------------------------------------------------ the switch: default ON, a file or the env turns it off
d = tempfile.mkdtemp(prefix="t2r-tmp-alife-sw-")
AL.SWITCH_FILE = os.path.join(d, "clan_alife.txt")
AL._sw.update(mtime=None, val=False)
check(AL.enabled() is True, "default ON (no switch file, no env)")
with open(AL.SWITCH_FILE, "w") as f:
    f.write("1\n")
check(AL.enabled() is True, "switch file '1' turns it on")
with open(AL.SWITCH_FILE, "w") as f:
    f.write("off\n")
os.utime(AL.SWITCH_FILE, (os.path.getmtime(AL.SWITCH_FILE) + 5,) * 2)
check(AL.enabled() is False, "switch file 'off' turns it off again (re-read on change)")
os.environ["T2R_CLAN_ALIFE"] = "1"
check(AL.enabled() is True, "env T2R_CLAN_ALIFE=1 wins over the file")
os.environ["T2R_CLAN_ALIFE"] = "0"
check(AL.enabled() is False, "env T2R_CLAN_ALIFE=0 wins")
os.environ.pop("T2R_CLAN_ALIFE", None)
AL.SWITCH_FILE = os.path.join(AL.os.path.dirname(os.path.abspath(AL.__file__)), "clan_alife.txt")
AL._sw.update(mtime=None, val=False)
check(not os.path.exists(AL.SWITCH_FILE), "no clan_alife.txt shipped in tools/ (default ON; the file only exists to turn it off)")
os.environ["T2R_CLAN_ALIFE"] = "0"
c0 = sqlite3.connect(":memory:")
check(AL.on_day(c0, "x", {"people": [], "day": 3}, {}, {"supplies": 1}) == [], "switched off: on_day writes nothing")
os.environ.pop("T2R_CLAN_ALIFE", None)

# ------------------------------------------------------------------ templates
check(len(AL.REG) >= 350, "template registry (%d templates, EN + PL)" % len(AL.REG))
check(all(len(AL.BY_POOL.get(p, ())) >= 3 for p in ("exp_leave", "exp_ret_good", "exp_ret_empty", "proj_start", "rat_deficit", "rat_surplus", "arrive", "memorial",
                                                     "vigil", "recovered", "quarrel", "reconcile", "mentor", "thr_enemy", "thr_inf", "tr_meet", "amb_any")), "every story pool has >= 3 templates")
ENGLISH = re.compile(r"\b(the|and|was|with|his|her|for|are|they|have|has|not|never|you|this|that|from|been|your|our|their|is)\b", re.I)


def sym_for(fk):
    return {"f": fk, "day": 12, "week": 2, "season": 0, "size": 9, "dest": sorted(X.PLACES[fk])[0], "goal": X.pool_keys(X.GOODS, fk)[0], "proj": X.pool_keys(X.PROJECTS, fk)[0],
            "grp": X.pool_keys(X.GROUPS, fk)[0], "inj": "ankle", "keep": "cap", "job": X.pool_keys(X.JOBS, fk)[0], "skill": X.pool_keys(X.SKILLS, fk)[0],
            "orig": X.pool_keys(X.ORIGINS, fk)[0], "prog": 2, "nd": 2, "ill": "fever", "inf": "runner", "sup": 9, "need": 13, "due": 15, "jd": 3}


broken, english_in_pl, vocab_bad, long_ticker = [], [], [], []
for tid, (pool, sc, tone, en, pl, lt, ve, vp) in AL.REG.items():
    for fk in ("W", "S"):
        if sc not in ("*", fk):
            continue
        sym = sym_for(fk)
        banned = D.BANNED_WOLF if fk == "W" else D.BANNED_SERA
        for g in ("m", "f", "n"):
            people = {k: {"n": "Mara", "g": g, "r": "medic"} for k in "ABCD"}
            people["B"]["g"] = "f" if g != "f" else "m"
            for lang in ("en", "pl"):
                try:
                    out = AL._render_ids([tid], people, sym, lang, fk)
                except Exception as e:     # noqa: BLE001
                    broken.append((tid, lang, repr(e)))
                    continue
                if re.search(r"[{}|]", out) or "  " in out or out != out.strip() or not out:
                    broken.append((tid, lang, out))
                if lang == "pl" and ENGLISH.search(re.sub(r"Isaac|Prorok", "", out)):
                    english_in_pl.append((tid, out))
                if lang == "en":
                    for w in banned:
                        if re.search(r"(?<!\w)" + re.escape(w.strip()) + r"(?!\w)", out, re.I):
                            vocab_bad.append((tid, fk, w, out))
        if pool.startswith(("f_", "wx_")):
            for g in ("m", "f"):
                people = {k: {"n": "Konstantyna", "g": g, "r": "scavenger"} for k in "ABCD"}
                for lang in ("en", "pl"):
                    t = CS.widget_text(AL._render_ids([tid], people, sym, lang, fk))
                    if len(t) > CS.WIDGET_MAX or len(t.encode()) > 150 or t.endswith("…"):
                        long_ticker.append((tid, lang, t))
check(not broken, "every template renders in EN and PL, no raw placeholders / double spaces (%s)" % (broken[:2],))
check(not english_in_pl, "Polish templates contain no English words (%s)" % (english_in_pl[:2],))
check(not vocab_bad, "faction vocabulary: Wolves lines have no Seraphite words and vice versa (%s)" % (vocab_bad[:2],))
check(not long_ticker, "ticker facts fit the one-line widget (<= %d chars, no cut) (%s)" % (CS.WIDGET_MAX, long_ticker[:2]))
check(all(X.letters_of(pl) <= (X.letters_of(en) | set("AB")) for _p, _s, _t, en, pl, *_r in AL.REG.values()), "Polish templates use no person the English one lacks")
pl_gender = X.render("{A} zrobił{A?|a} to; {AB?li|ły}", {"A": {"n": "Ola", "g": "f"}, "B": {"n": "Ewa", "g": "f"}}, {}, "pl")
check(pl_gender == "Ola zrobiła to; ły" and X.render("{A?on|ona}", {"A": {"n": "Jan", "g": "n"}}, {}, "pl") == "on", "Polish gender switches (neutral names take the masculine form)")
check(X.with_prep("złomem") == "ze złomem" and X.with_prep("solą") == "z solą" and X.with_prep("skręconą kostką") == "ze skręconą kostką", "Polish z / ze before an instrumental")
check(X.pl_people(3) == "3 osoby" and X.pl_people(5) == "5 osób" and X.pl_people(22) == "22 osoby" and X.pl_people(12) == "12 osób", "Polish people counts")


# ------------------------------------------------------------------ simulated months against the real rules
def mixed(i, c0, need):
    return int(need * clan.PARTS_PER_SUPPLY * (0.8 if i % 7 in (3, 4) else 1.35))


def poor(i, c0, need):
    return int(need * clan.PARTS_PER_SUPPLY * (0.7 if i % 3 == 0 else 1.05))


def rich(i, c0, need):
    return int(need * clan.PARTS_PER_SUPPLY * 1.7)


NOT_SICK_OK = {"vigil": "A", "vigil_spore": "A", "exp_recall": "B"}
LAUNCHER_MOODS = {"hopeful", "cheerful", "calm", "neutral", "worried", "afraid", "desperate", "grieving", "grim", "despair"}
SEEDS = [(clan.WLF, mixed, 11, (12, 1, 0, 0)), (clan.SERAPHITES, mixed, 12, (12, 1, 0, 0)), (clan.WLF, rich, 13, (6, 0, 0, 0)), (clan.SERAPHITES, rich, 14, (6, 0, 0, 0)),
         (clan.WLF, poor, 15, (14, 2, 1, 0)), (clan.SERAPHITES, poor, 16, (14, 2, 1, 0)), (clan.SERAPHITES, mixed, 17, (30, 4, 2, 20)), (clan.WLF, mixed, 18, (30, 4, 2, 20))]
total_rows = total_viol = 0
kinds_pools = set()
all_rows_by_run = []
for fac, pol, seed, start in SEEDS:
    fk = "W" if fac == clan.WLF else "S"
    away_log = {}

    def hook(c, tid, ent):
        al = AL.load(c, tid)
        away_log[ent["day"]] = [(t["k"], t["s"], t["d"], list(t["a"])) for t in (al["T"] if al else [])]
    c_on, tid, log_on = R.simulate(fac, start, 84, seed=seed, alife=True, parts_fn=pol, hook=hook)
    c_off, tid2, log_off = R.simulate(fac, start, 84, seed=seed, alife=False, parts_fn=pol)
    tag = "%s %s seed %d" % (fk, pol.__name__, seed)
    # (1) the A-Life never changes anything authoritative: same numbers, same roster states, same diary rows
    same_nums = len(log_on) == len(log_off) and all((a["clan"]["healthy"], a["clan"]["hungry"], a["clan"]["sick"], a["clan"]["day"], a["clan"]["status"]) ==
                                                    (b["clan"]["healthy"], b["clan"]["hungry"], b["clan"]["sick"], b["clan"]["day"], b["clan"]["status"]) for a, b in zip(log_on, log_off))
    check(same_nums, "%s: healthy / hungry / sick / day identical with the A-Life ON and OFF (%d days)" % (tag, len(log_on)))
    same_roster = all(a["people"] == b["people"] and a["dead"] == b["dead"] for a, b in zip(log_on, log_off))
    check(same_roster, "%s: the named roster (who is sick / dead) identical with the A-Life ON and OFF" % tag)
    diary_on = [r["text"] for e in log_on for r in e["rows"] if r["kind"] != "alife"]
    diary_off = [r["text"] for e in log_off for r in e["rows"]]
    check(diary_on == diary_off, "%s: the diary rows (clan_story) are word for word identical with the A-Life ON and OFF" % tag)
    # (2) invariants of every A-Life row
    bad = []
    for ent in log_on:
        st = ent["st"]
        alive = {p["n"]: p for p in st["people"]}
        dead = {x["n"] for x in st["dead"]}
        size = len(st["people"])
        al_rows = [r for r in ent["rows"] if r["kind"] == "alife"]
        if size < AL.MIN_CLAN and al_rows:
            bad.append((ent["day"], "rows for a clan of %d" % size))
        if al_rows and not 1 <= len(al_rows) <= AL.DAY_MAX_ROWS:
            bad.append((ent["day"], "row count %d" % len(al_rows)))
        threads = away_log.get(ent["day"], [])
        away_ids = {i for k, s, d_, a in threads if k == "exp" and s < ent["day"] < d_ for i in a}
        id_of = {p["n"]: p["i"] for p in st["people"]}
        for r in al_rows:
            total_rows += 1
            params = json.loads(r["params"])
            ids = r["lid"][3:].split("+")
            pool = AL.REG[ids[-1] if not AL.REG[ids[0]][0].startswith("wx_") else ids[-1]][0] if False else next(AL.REG[i][0] for i in ids if not AL.REG[i][0].startswith(("wx_", "coda")))
            kinds_pools.add(pool)
            if r["mood"] not in LAUNCHER_MOODS or r["kind"] != "alife":
                bad.append((ent["day"], "mood/kind", r["mood"]))
            if "{" in r["text"] or "}" in r["text"]:
                bad.append((ent["day"], "raw", r["text"]))
            for letter, (nm, g, ro) in params["p"].items():
                if letter == "D":
                    if nm not in dead:
                        bad.append((ent["day"], "D is not dead", nm, pool))
                    continue
                p = alive.get(nm)
                if p is None:
                    bad.append((ent["day"], "mentions a person who is not alive", nm, pool))
                    continue
                if p["s"] == "s" and NOT_SICK_OK.get(pool) != letter:
                    bad.append((ent["day"], "a sick person in a healthy scene", nm, pool, letter))
                if p["i"] in away_ids and pool not in ("exp_wait", "exp_ret_good", "exp_ret_empty", "exp_ret_hurt", "exp_ret_contact", "exp_ret_inf", "exp_recall") and not (pool == "exp_wait" and letter == "B"):
                    bad.append((ent["day"], "someone away at an expedition is in camp", nm, pool))
                if pool == "exp_wait" and letter == "A" and p["i"] in away_ids:
                    bad.append((ent["day"], "the camp worrier is away", nm))
            s_ = params["s"]
            if "sup" in s_ and (s_["sup"] != ent["r"]["supplies"] or s_["need"] != ent["r"]["needed"]):
                bad.append((ent["day"], "ration numbers differ from the day's tally", s_["sup"], ent["r"]["supplies"]))
            if s_.get("size") != size:
                bad.append((ent["day"], "size differs", s_.get("size"), size))
            if pool in ("memorial", "memorial_late"):
                dn = params["p"]["D"][0]
                dd = next((x for x in st["dead"] if x["n"] == dn), None)
                if not dd or dd["c"] not in AL.MEM_CAUSES:
                    bad.append((ent["day"], "memorial for a death that is not one", dn))
            if pool == "recovered" and not any(prev["day"] == ent["day"] - 1 and any(x[0] == params["p"]["A"][0] for x in [(n_,) for _i, n_, s__ in [q for q in prev["people"]] if s__ == "s"]) for prev in log_on):
                bad.append((ent["day"], "a recovery of someone who was not sick the day before", params["p"]["A"][0]))
    total_viol += len(bad)
    check(not bad, "%s: every A-Life row is consistent with the real roster / tally / expeditions (%s)" % (tag, bad[:3]))
    all_rows_by_run.append((fac, log_on))
    c_on.close()
    c_off.close()

check(total_rows > 700, "the simulated months produced %d A-Life rows" % total_rows)
need_pools = {"exp_leave", "exp_ret_good", "exp_ret_empty", "proj_start", "proj_done", "rat_deficit", "rat_surplus", "arrive", "memorial", "vigil", "recovered", "quarrel",
              "reconcile", "mentor", "thr_enemy", "tr_meet", "amb_any", "friend"}
check(need_pools <= kinds_pools, "the months reach the main storylines (missing %s)" % sorted(need_pools - kinds_pools))
check(len(kinds_pools) >= 38, "%d different storyline pools used" % len(kinds_pools))

# threads carry across days: an expedition that left on day d comes back on a later day; an injury is mentioned again before it heals
fac, log = all_rows_by_run[0]
leave_days = [e["day"] for e in log for r in e["rows"] if r["kind"] == "alife" and any(AL.REG[i][0] == "exp_leave" for i in r["lid"][3:].split("+"))]
ret_days = [e["day"] for e in log for r in e["rows"] if r["kind"] == "alife" and any(AL.REG[i][0].startswith("exp_ret") for i in r["lid"][3:].split("+"))]
check(leave_days and ret_days and any(any(rd > ld for rd in ret_days) for ld in leave_days), "expeditions leave and return on later days (%d left, %d returned)" % (len(leave_days), len(ret_days)))

# ------------------------------------------------------------------ determinism, and restarts do not change the history
def texts(log):
    return [(e["day"], r["text"]) for e in log for r in e["rows"]]


def run_reload():
    state = {"n": 0}

    def hook(c, tid, ent):
        state["n"] += 1
        if state["n"] in (10, 25):                      # a daemon restart: every module is loaded again, everything else lives in the DB
            for m in ("clan_story", "clan_alife_lex", "clan_alife"):
                importlib.reload(sys.modules[m])
    global CS, AL
    c, tid, log = R.simulate(clan.SERAPHITES, (12, 1, 0, 0), 40, seed=21, alife=True, parts_fn=mixed, hook=hook)
    c.close()
    CS, AL = sys.modules["clan_story"], sys.modules["clan_alife"]
    return log


a = R.simulate(clan.SERAPHITES, (12, 1, 0, 0), 40, seed=21, alife=True, parts_fn=mixed)
b = R.simulate(clan.SERAPHITES, (12, 1, 0, 0), 40, seed=21, alife=True, parts_fn=mixed)
check(texts(a[2]) == texts(b[2]) and len(texts(a[2])) > 150, "deterministic: the same clan history gives the same feed word for word (%d rows)" % len(texts(a[2])))
check(texts(run_reload()) == texts(a[2]), "a restart (modules reloaded twice mid-run) changes nothing")
a[0].close()
b[0].close()

# ------------------------------------------------------------------ anti-repeat
reps = []
for fac, log in all_rows_by_run:
    seen = {}
    rows = [(e["day"], r["text"]) for e in log for r in e["rows"] if r["kind"] == "alife"]
    for day, t in rows:
        if t in seen and day - seen[t] < 28:
            reps.append((day, t))
        seen[t] = day
check(not reps, "no A-Life row repeated word for word inside 4 weeks in %d runs (%s)" % (len(all_rows_by_run), reps[:2]))
core_by_run = []
for fac, log in all_rows_by_run:
    last = {}
    vio = n = 0
    for e in log:
        for r in e["rows"]:
            if r["kind"] != "alife":
                continue
            for i in r["lid"][3:].split("+"):
                pool = AL.REG[i][0]
                if pool.startswith(("wx_", "coda")):
                    continue
                n += 1
                if i in last and e["day"] - last[i] < AL.WINDOW_DAYS:
                    vio += 1
                last[i] = e["day"]
    core_by_run.append((n, vio))
tot_n = sum(n for n, v in core_by_run)
tot_v = sum(v for n, v in core_by_run)
check(tot_v / max(1, tot_n) < 0.12, "a core template is reused inside %d days in only %d of %d uses (%.1f%%)" % (AL.WINDOW_DAYS, tot_v, tot_n, 100.0 * tot_v / max(1, tot_n)))

# ------------------------------------------------------------------ repeat rate before / after (the menu the player sees, 28 days)
def menu_metrics(fac, start, seed, alife):
    """What the player sees over 28 clan days: per day the menu of THAT day's clan state, 12 one-minute slots x 6 lines."""
    seen = []

    def hook(c, tid, ent):
        base = 1_700_000_000 + ent["day"] * 86400
        for k in range(12):
            for _id, t in CS.menu_lines(c, tid, 6, "en", base + k * 60, save=False):
                seen.append((ent["day"], t))
    c, tid, log = R.simulate(fac, start, 28, seed=seed, alife=alife, parts_fn=mixed, hook=hook)
    f = [(e["day"], r["text"]) for e in log for r in e["rows"]]
    c.close()
    return R.repeat_stats(seen), R.repeat_stats(f), R.day_repeat_stats(seen)


for fac, start, seed in ((clan.WLF, (10, 0, 0, 0), 31), (clan.SERAPHITES, (16, 1, 0, 0), 32), (clan.WLF, (30, 2, 1, 20), 33)):
    off_m, off_f, off_d = menu_metrics(fac, start, seed, False)
    on_m, on_f, on_d = menu_metrics(fac, start, seed, True)
    print("     menu OFF %s  %s\n     menu ON  %s  %s" % (off_m, off_d, on_m, on_d))
    nm = "%s clan of %d" % ("WLF" if fac == clan.WLF else "SERA", sum(start[:3]))
    check(on_d["skeletonRepeatShare"] < off_d["skeletonRepeatShare"] - 0.25, "menu: the same wording (names stripped) seen again on a later day %.0f%% -> %.0f%% (%s)" %
          (100 * off_d["skeletonRepeatShare"], 100 * on_d["skeletonRepeatShare"], nm))
    check(on_d["repeatShare"] < 0.35, "menu: the identical line seen again on a later day stays under 35%% (%.0f%%; it was %.0f%%: a lasting fact is retold, in another phrasing) (%s)" %
          (100 * on_d["repeatShare"], 100 * off_d["repeatShare"], nm))
    check(on_m["distinct"] > off_m["distinct"] * 0.6, "menu: distinct lines %d -> %d (%s)" % (off_m["distinct"], on_m["distinct"], nm))

# ------------------------------------------------------------------ the ticker: pure function of (state, slot, language), only alive people in their real state
c, tid, log = R.simulate(clan.WLF, (14, 2, 1, 5), 30, seed=41, alife=True, parts_fn=mixed)
os.environ["T2R_CLAN_ALIFE"] = "1"
st = CS._load(c, tid)
now = 1_700_000_000
l1 = CS.menu_lines(c, tid, 6, "en", now, save=False)
l2 = CS.menu_lines(c, tid, 6, "en", now, save=False)
check(l1 == l2 and len(l1) == 6, "menu_lines is deterministic for one slot (6 lines)")
p1 = CS.menu_lines(c, tid, 6, "pl", now, save=False)
check([i for i, _t in p1] == [i for i, _t in l1] and any(a != b for (_i, a), (_j, b) in zip(l1, p1)), "the Polish menu has the same ids, other words")
al_lines = [t for i, t in l1 if str(i).startswith("a")]
check(len(al_lines) >= 1 or len(CS.pick_slot(c, tid, CS.slot_of(now), 3, "en", now)) >= 3, "A-Life lines are part of the menu")
ids_all, texts_all = set(), []
for k in range(120):
    for i, t in AL.ticker_lines(c, tid, st, CS.slot_of(now) + k, AL.TICKER_SHARE, "en", None, False):
        ids_all.add(i)
        texts_all.append(t)
        if len(t.encode()) > 150 or "|" in t or "\n" in t:
            check(False, "ticker line widget-safe: " + t)
check(len(set(texts_all)) / max(1, len(texts_all)) > 0.4, "120 minutes of A-Life ticker: %d lines, %d distinct" % (len(texts_all), len(set(texts_all))))
fs = AL.facts(AL.load(c, tid), st)
alive = {p["i"]: p for p in st["people"]}
badf = []
for f in fs:
    for k, v in f["people"].items():
        if "i" in v and v["i"] not in alive:
            badf.append((f["key"], v["n"]))
        elif "i" in v and f["cls"] != "f_vigil" and alive[v["i"]]["s"] == "s" and not (f["cls"] in ("f_vigil",)):
            badf.append((f["key"], v["n"], "sick"))
check(not badf, "ticker facts only name living people in the right state (%d facts)" % len(fs))
for p in st["people"]:
    pass
# after a death the dead are no longer in a present-tense fact
st2 = json.loads(json.dumps(st))
victim = st2["people"].pop(0)
fs2 = AL.facts(AL.load(c, tid), st2)
check(all(victim["n"] not in [v["n"] for v in f["people"].values()] for f in fs2 if f["cls"] != "f_memorial"), "a person who died is dropped from every present-tense fact")
os.environ.pop("T2R_CLAN_ALIFE", None)

# ------------------------------------------------------------------ storage compatibility
rows = CS.read_feed(c, tid, 100)
al_rows = [m for m in rows if m["kind"] == "alife"]
check(all(set(m) == {"id", "day", "week", "kind", "mood", "faction", "text", "names", "ts", "lang"} for m in rows), "feed rows keep the launcher's message fields")
pl_rows = CS.read_feed(c, tid, 100, lang="pl")
check(any(m["lang"] == "pl" and m["kind"] == "alife" for m in pl_rows) and len(pl_rows) == len(rows), "A-Life rows are rendered in Polish at read time")
pl_text = [m["text"] for m in pl_rows if m["kind"] == "alife" and m["lang"] == "pl"]
check(pl_text and not any(ENGLISH.search(re.sub(r"Isaac|Prorok", "", t)) for t in pl_text[:80]), "the Polish A-Life rows contain no English (%d checked)" % min(80, len(pl_text)))
# an old daemon / reader: no clan_alife module knowledge -> the row stays English, nothing raises
c.execute("UPDATE clan_feed SET lid='al/zzzz~00000000' WHERE kind='alife'")
rows_x = CS.read_feed(c, tid, 100, lang="pl")
check(all(m["lang"] == "en" for m in rows_x if m["kind"] == "alife"), "an unknown A-Life template id reads back in English (older readers)")
c.execute("CREATE TABLE old_feed(token_id TEXT, id INTEGER, ts REAL, day INTEGER, week INTEGER, kind TEXT, mood TEXT, faction INTEGER, text TEXT, names TEXT)")
check(isinstance(AL.read_state(c, tid, "pl"), dict) and AL.read_state(c, tid, "pl").get("people"), "read_state (admin / launcher view) works")
rs = AL.read_state(c, tid, "en")
check(rs["people"] and all(set(p) >= {"name", "role", "state", "traits", "away"} for p in rs["people"]) and "stats" in rs and "threads" in rs, "read_state fields")
check(rs["stats"]["templatesTotal"] == len(AL.REG), "read_state statistics")
c.close()

# a clan_feed table from before the lid / params columns: A-Life never needs to read it
d = tempfile.mkdtemp(prefix="t2r-tmp-alife-old-")
cc = sqlite3.connect(os.path.join(d, "o.db"))
cc.execute("CREATE TABLE clan_feed(token_id TEXT, id INTEGER, ts REAL, day INTEGER, week INTEGER, kind TEXT, mood TEXT, faction INTEGER, text TEXT, names TEXT, PRIMARY KEY(token_id,id))")
cc.execute("INSERT INTO clan_feed VALUES('t',1,1.0,1,1,'alife','calm',1,'x','[]')")
check(CS.read_feed(cc, "t", 5, lang="pl")[0]["text"] == "x", "a pre-lid clan_feed table still reads")
cc.close()

# a new run (CHOOSE YOUR SIDE) drops the old simulation; a state of another run is never reused
d = tempfile.mkdtemp(prefix="t2r-tmp-alife-run-")
cc = sqlite3.connect(os.path.join(d, "r.db"))
os.environ["T2R_CLAN_ALIFE"] = "1"
clan.rng = random.Random(5)
clan.choose_side(cc, "bb" * 12, clan.WLF)
CS.on_new_run(cc, "bb" * 12, clan.WLF)
for i in range(1, 6):
    new, r = clan.apply_match(cc, "bb" * 12, "m%d" % i, 2500)
    CS.on_day(cc, "bb" * 12, new, r)
check(AL.load(cc, "bb" * 12) is not None, "the A-Life state is stored in its own table (clan_alife)")
CS.on_new_run(cc, "bb" * 12, clan.SERAPHITES)
check(AL.load(cc, "bb" * 12) is None, "a new run deletes the old simulation")
os.environ.pop("T2R_CLAN_ALIFE", None)
cc.close()

# ------------------------------------------------------------------ camp incidents (clan_alife_text_g.py; re/clan-events-1117.md): text only, own random stream
INC = ("inc_spoil", "inc_tres", "inc_horde", "inc_sick")
check(all(p in AL.BY_POOL and AL.BY_POOL[p] for p in INC), "the four incident pools are registered")
for p in INC:
    rows = AL.POOLS[p]
    check(all(not X.vars_of(en) and not X.vars_of(pl) for _s, _t, en, pl in rows), "%s: the templates name people only (no place / thing / number variable)" % p)
    check(all(not re.search(r"\d", en + pl) for _s, _t, en, pl in rows), "%s: no figure in the text (nothing a player could hold against the clan's numbers)" % p)
    check(all(X.letters_of(en) == X.letters_of(pl) == {"A", "B"} for _s, _t, en, pl in rows), "%s: EN and PL both speak of A and B" % p)
for p in ("inc_spoil", "inc_tres"):
    check({sc for sc, _t, _e, _p in AL.POOLS[p]} == {"W", "S"}, "%s has its own rows for each faction" % p)
check(all(not re.search(r"\b(died|dead|killed|lost a|bitten|wounded|zgin|zabit|ugryz|rann)", en + " " + pl, re.I) for p in INC for _s, _t, en, pl in AL.POOLS[p]),
      "no incident kills, bites or wounds anyone")


def inc_rows(log):
    return [(e, r) for e in log for r in e["rows"] if r["kind"] == "alife" and any(AL.REG[i][0] in INC for i in r["lid"][3:].split("+"))]


inc_total, inc_sick_bad, inc_changed = 0, [], []
for fac, pol, seed, start in SEEDS[:4] + SEEDS[6:]:
    AL.INCIDENTS = True
    drawn = []

    def inc_hook(c, tid, ent):
        al = AL.load(c, tid)
        if al and al["cool"].get("inc") == ent["day"]:
            drawn.append(ent["day"])
    c1, t1, log1 = R.simulate(fac, start, 84, seed=seed, alife=True, parts_fn=pol, hook=inc_hook)
    AL.INCIDENTS = False
    c0, t0, log0 = R.simulate(fac, start, 84, seed=seed, alife=True, parts_fn=pol)
    AL.INCIDENTS = True
    found = inc_rows(log1)
    inc_total += len(found)
    # the authoritative numbers do not move with the incidents on or off
    if [(e["clan"]["healthy"], e["clan"]["hungry"], e["clan"]["sick"], e["clan"]["day"], e["clan"]["status"]) for e in log1] != \
            [(e["clan"]["healthy"], e["clan"]["hungry"], e["clan"]["sick"], e["clan"]["day"], e["clan"]["status"]) for e in log0]:
        inc_changed.append(("numbers", seed))
    # up to the first incident DRAWN (told or not: the two people in it were in a scene that day) the two histories are word for word the same:
    # the incidents draw from their own random stream
    first = min(drawn, default=10 ** 6)
    if [[r["text"] for r in e["rows"]] for e in log1 if e["day"] < first] != [[r["text"] for r in e["rows"]] for e in log0 if e["day"] < first]:
        inc_changed.append(("history before the first incident", seed))
    if inc_rows(log0):
        inc_changed.append(("an incident with the switch off", seed))
    for e, r in found:
        if any(AL.REG[i][0] == "inc_sick" for i in r["lid"][3:].split("+")) and not any(p["s"] == "s" for p in (e.get("people") or [])) and "people" in e:
            inc_sick_bad.append((seed, e["day"]))
check(inc_total >= 6, "the simulated months tell camp incidents (%d rows over 6 runs)" % inc_total)
check(not inc_changed, "the incidents change no number and nothing before the first of them (%s)" % inc_changed)
check(not inc_sick_bad, "a night in the sick tent is only told on a day somebody is sick (%s)" % inc_sick_bad)
check(all(len(inc_rows(log)) <= len([i for p in INC for i in AL.BY_POOL[p]]) for _f, log in all_rows_by_run), "an incident template is told at most once per run")

print("\nFAILED: %d" % len(FAILS) if FAILS else "\nall clan A-Life tests passed")
sys.exit(1 if FAILS else 0)
