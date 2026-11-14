"""Offline tests for the Polish clan feed (tools/clan_story_pl*.py) and its storage / protocol plumbing.
Run: python tools/tests/test_clan_story_pl.py   (plain python; temp DB only, never tools/t2r.db or port 7001)."""
import json, os, random, re, sqlite3, sys, tempfile
import sys as _t2s, os as _t2o; _t2s.path.append(_t2o.path.normpath(_t2o.path.join(_t2o.path.dirname(_t2o.path.abspath(__file__)), ".."))); import t2rtmp  # noqa: E402,F401  (temp hygiene: tools/t2rtmp.py)

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.dirname(HERE)
sys.path.insert(0, TOOLS)
os.environ["T2R_CLAN_CHRONICLE"] = "0"          # these cover the plain diary / A-Life (the chronicle is ON by default: tests/test_clan_continuity.py)
import clan, clan_story as CS, clan_story_data as D, clan_story_pl as PL  # noqa: E402

FAILS = []
def check(cond, what):
    print(("ok   " if cond else "FAIL ") + what)
    if not cond:
        FAILS.append(what)

def hit(text, words):
    return any(re.search(re.escape(w.strip()), text, re.I) for w in words)

# ------------------------------------------------------------------ the registry (every English template has its Polish twin)
check(len(PL.REG) >= 700, "registry covers every template (%d)" % len(PL.REG))
SYM = {"f": "W", "day": 3, "week": 1, "place": "stadium", "inf": "runner", "ago": "yesterday", "ill": "pneumonia", "n": 3, "lost": 2, "gain": 3}
SYM_S = dict(SYM, f="S", place="island", ill="infected_wound", n=2, lost=1, gain=2)

def people(g):
    return {k: {"n": "Mara", "g": g} for k in "ABCD"}

broken, leftovers, letters_bad, vars_bad = [], [], [], []
ENGLISH = re.compile(r"\b(the|and|was|with|his|her|for|are|they|have|has|not|never|you|this|that|from|been|your|our|their)\b", re.I)
mixed = {"A": {"n": "Jan", "g": "m"}, "B": {"n": "Ola", "g": "f"}, "C": {"n": "Jan", "g": "m"}, "D": {"n": "Ola", "g": "f"}}
for pool, scope, en, pl in PL.ROWS:
    sym = SYM_S if scope == "S" else SYM
    for gset in (people("m"), people("f"), people("n"), mixed):
        try:
            out = PL.render(pl, gset, PL.expand(sym))
        except Exception as e:      # noqa: BLE001
            broken.append((pool, pl, repr(e)))
            break
        if re.search(r"[{}|]", out) or "  " in out or not out.strip() or out != out.strip():
            broken.append((pool, pl, out))
            break
        if ENGLISH.search(out):
            leftovers.append((pool, out))
    # the one- / two-survivor voices (clan_story_solo.py) carry the narrator's gender in Polish ({A?łem|łam}) without naming the narrator in English
    narrator_voice = pool.startswith(("solo:", "duo:", "t:solo_"))
    if (PL.tpl_letters(en) > PL.tpl_letters(pl)) if narrator_voice else (PL.tpl_letters(en) != PL.tpl_letters(pl)):
        letters_bad.append((pool, sorted(PL.tpl_letters(en)), sorted(PL.tpl_letters(pl)), pl[:70]))
    if not PL.tpl_vars(pl) <= PL.tpl_vars(en):
        vars_bad.append((pool, PL.tpl_vars(pl) - PL.tpl_vars(en), pl[:70]))
check(not broken, "every Polish template renders for m / f / n / mixed genders, no raw placeholder (%s)" % (broken[:2],))
check(not leftovers, "no English words left in the Polish lines (%s)" % (leftovers[:3],))
check(not letters_bad, "Polish and English templates name the same people (%d differ: %s)" % (len(letters_bad), letters_bad[:3]))
check(not vars_bad, "Polish templates use no variable the English one lacks (%s)" % (vars_bad[:3],))

# the gender switch really changes the verb: a feminine person never gets a masculine past-tense ending in a line with a switch
def has_switch(t): return bool(PL.SW_RE.search(t))
sw_same = [pl for pool, s, en, pl in PL.ROWS if has_switch(pl) and PL.render(pl, people("m"), PL.expand(SYM)) == PL.render(pl, people("f"), PL.expand(SYM))]
check(not sw_same, "m and f renderings differ wherever there is a switch (%s)" % (sw_same[:2],))
fem = [PL.render(pl, people("f"), PL.expand(SYM)) for pool, s, en, pl in PL.ROWS if pool.startswith("t:")]
check(not any(re.search(r"\b(został|zmarł|poszedł|złapał|znalazł|zjadł|schudł|załamał|zachorował|spał|wstał)\b", t) for t in fem),
      "feminine ticker lines carry no masculine past tense")

# verbs whose stem changes in the feminine (-szedł / -szła, -ął / -ęła, ó / o ...): the classic generation mistakes never appear
BAD_F = re.compile(r"\b(wyszedła|poszedła|wszedła|odszedła|przyszedła|przeszedła|zacząła|zginąła|mógła|niósła|przyniósła|przyjąła|ukląkła|cierpliwya)\b")
BAD_M = re.compile(r"\b(odeszł|wyszł|poszł|weszł|przyszł|przeszł|zaczęł|zginęł|mogł|niosł|przyniosł|przyjęł|uklękł|zamiotł)\b")
bad_form = []
for pool, scope, en, pl in PL.ROWS:
    f = PL.render(pl, people("f"), PL.expand(SYM))
    m = PL.render(pl, people("m"), PL.expand(SYM))
    if BAD_F.search(f) or BAD_M.search(m):
        bad_form.append((pool, (BAD_F.search(f) or BAD_M.search(m)).group(0)))
check(not bad_form, "no malformed masculine / feminine verb form (%s)" % (bad_form[:3],))

# faction vocabulary in Polish: the Seraphite voice never uses Wolf-side words and vice versa
BAN_SERA = ["jezu", "chryste", "bóg", "boże", "bogu", "isaac", "stadion", "blizn", "wlf", "punkt kontrolny", "koszar", "radio", "baza", "bazie", "bazy"]
BAN_WOLF = ["prorokin", "jej światł", "serafi", "starsi", "starszy", "wyspa", "wyspy", "wyspie", "wyspę", "uzdrowiciel", "siostry", "bracia", "amen"]
for fk, ban in (("S", BAN_SERA), ("W", BAN_WOLF)):
    bad = []
    for pool, scope, en, pl in PL.ROWS:
        if scope in ("*", fk):
            out = PL.render(pl, people("f"), PL.expand(dict(SYM_S if fk == "S" else SYM)))
            if hit(out, ban):
                bad.append((pool, out[:90]))
    check(not bad, "Polish faction vocabulary %s (%s)" % (fk, bad[:3]))
check(not [1 for pool, scope, en, pl in PL.ROWS if scope == "S" and re.search(r"\bk(urw|urwa|urwa)|pierdol|gówn|chuj|cholern", PL.render(pl, people("f"), PL.expand(SYM_S)), re.I)
           and not pool.startswith("t:")], "Polish Seraphite lines are free of heavy swearing")

# the Seraphite ticker filter keys on the same lines in both languages (the island has no generators, stills, ammunition ...)
en_drop = [i for i, t in enumerate(D.TICKER_HEALTHY) if any(k in t for k in D.TICKER_NOT_SERA)]
pl_drop = [i for i, t in enumerate(PL.TICKER_HEALTHY) if any(k in t for k in PL.TICKER_NOT_SERA)]
check(en_drop and en_drop == pl_drop, "Polish ticker not-Seraphite filter drops the same lines as the English one (%s vs %s)" % (en_drop, pl_drop))

# ------------------------------------------------------------------ variables
check(PL.people_phrase(1, "acc") == "jedną osobę" and PL.people_phrase(2, "acc") == "dwie osoby" and PL.people_phrase(5, "acc") == "pięć osób" and
      PL.people_phrase(3, "gen") == "trzech osób" and PL.people_phrase(0, "acc") == "nikogo" and PL.people_phrase(12, "nom") == "12 osób", "people counts in cases")
check(PL.people_phrase(2, "gen", True) == "dwóch nowych osób" and PL.people_phrase(1, "acc", True) == "jedną nową osobę", "newcomer counts in cases")
check(PL.render("{ago} {A} odesz{A?ł|ła}.", people("f"), PL.expand({"f": "W", "ago": "yesterday"})) == "Wczoraj Mara odeszła.", "sentence-start variable capitalised, feminine verb")
check(PL.render("{A} i {B} {AB?byli|były}.", {"A": {"n": "Ana", "g": "f"}, "B": {"n": "Ola", "g": "f"}}, {}) == "Ana i Ola były." and
      PL.render("{A} i {B} {AB?byli|były}.", {"A": {"n": "Ana", "g": "f"}, "B": {"n": "Jan", "g": "m"}}, {}) == "Ana i Jan byli.", "two-person switch: virile unless all female")
check(all(len(PL.PLACES[p]) == 6 for p in PL.PLACES) and set(PL.PLACES) == set(D.FACTION["W"]["places"]) | set(D.FACTION["S"]["places"]), "every place has its Polish cases")
check(set(PL.INF) == set(D.INFECTED) and set(PL.ILL) == set(D.ILLNESS) | {"none"} and set(PL.CURE) == set(PL.ILL) and
      all(PL.CURE[k][0] for k in PL.CURE), "every infected / illness / cure has Polish forms")
# the game's own Polish words (core.psarc text2/pol.common): Serafici, Wilki, Blizny, Biegacz, Klikacz, Czyhacz, Człapacz, Purchlak
check(PL.ENEMY["S"][0] == "Wilki" and PL.ENEMY["W"][0] == "Blizny" and PL.INF["bloater"][0] == "purchlak" and PL.INF["shambler"][0] == "człapacz", "faction / infected names as in the game's Polish text")

# ------------------------------------------------------------------ whole runs: stored language-neutral, rendered in both languages
def run_clan(seed, faction, policy):
    d = tempfile.mkdtemp()
    c = sqlite3.connect(os.path.join(d, "t.db"))
    clan.rng = random.Random(seed)
    tid = "0123456789abcdef01234567"
    clan.choose_side(c, tid, faction)
    CS.on_new_run(c, tid, faction)
    for i in range(1, 90):
        c0 = clan.load(c, tid)
        if c0["status"] != clan.ALIVE:
            break
        new, r = clan.apply_match(c, tid, "m%d" % i, policy(i, c0))
        if r:
            CS.on_day(c, tid, new, r)
    return c, tid

def poor(i, c0): return 400
def mixedp(i, c0): return 400 if (i // 5) % 2 else 2500
total = rendered = 0
bad_pl, same_en, bad_roundtrip, kinds = [], [], [], set()
for fac, fk in ((clan.WLF, "W"), (clan.SERAPHITES, "S")):
    for pol in (poor, mixedp):
        for seed in range(4):
            c, tid = run_clan(seed, fac, pol)
            en = CS.read_feed(c, tid, 60)
            pl = CS.read_feed(c, tid, 60, lang="pl")
            check(len(en) == len(pl) and [m["id"] for m in en] == [m["id"] for m in pl], "%s seed %d: same messages in both languages" % (fk, seed))
            for a, b in zip(en, pl):
                total += 1
                kinds.add(a["kind"])
                if b.get("lang") == "pl":
                    rendered += 1
                    if re.search(r"[{}|]", b["text"]) or ENGLISH.search(b["text"]) or b["text"] == a["text"]:
                        bad_pl.append((a["kind"], b["text"]))
                    banned = BAN_SERA if fk == "S" else BAN_WOLF
                    if hit(b["text"], banned):
                        bad_pl.append(("vocab", b["text"]))
                    if any(n not in b["text"] for n in a["names"]):
                        same_en.append((a["text"], b["text"]))
                    # the English line re-rendered from (lid, params) is the stored English text
                    row = c.execute("SELECT lid, params FROM clan_feed WHERE token_id=? AND id=?", (tid, a["id"])).fetchone()
                    if CS.render_msg(row[0], json.loads(row[1]), "en") != a["text"]:
                        bad_roundtrip.append((a["text"], CS.render_msg(row[0], json.loads(row[1]), "en")))
            c.close()
check(total > 200 and rendered == total, "every new message has a Polish rendering (%d / %d)" % (rendered, total))
check(not bad_pl, "stored Polish lines: no placeholder, no English, faction vocabulary kept (%s)" % (bad_pl[:2],))
check(not same_en, "every name of the English line is in the Polish line (%s)" % (same_en[:2],))
check(not bad_roundtrip, "English re-rendered from (lid, params) equals the stored English text (%s)" % (bad_roundtrip[:2],))
check(len(kinds) >= 20, "the runs cover %d message kinds" % len(kinds))

# widget text: Polish diacritics survive the wire cut (<= 150 bytes, no pipe), the cut never splits a letter
for pool, scope, en, pl in PL.ROWS:
    t = PL.render(pl, people("f"), PL.expand(SYM))
    w = CS.widget_text(t)
    try:
        w.encode("utf-8").decode("utf-8")
        ok = len(w.encode("utf-8")) <= 150 and "|" not in w and "\n" not in w and len(w) <= CS.WIDGET_MAX
    except UnicodeError:
        ok = False
    if not ok:
        check(False, "widget cut of %s" % t[:60])
        break
else:
    check(True, "every Polish line cuts to a valid one-line widget text (<= 150 bytes)")
alld = "".join(PL.render(pl, people("f"), PL.expand(SYM)) + PL.render(pl, people("m"), PL.expand(SYM)) for _p, _s, _e, pl in PL.ROWS)
check(all(ch in alld for ch in "ąćęłńóśźżŚŻŁĆ"), "the lines use the Polish diacritics (ąćęłńóśźż ...)")

# ------------------------------------------------------------------ additive migration of a clan_feed table from before the language-neutral columns
d = tempfile.mkdtemp()
old = sqlite3.connect(os.path.join(d, "old.db"))
old.execute("CREATE TABLE clan_feed(token_id TEXT, id INTEGER, ts REAL, day INTEGER, week INTEGER, kind TEXT, mood TEXT, faction INTEGER, text TEXT, names TEXT, "
            "PRIMARY KEY(token_id, id))")
old.execute("CREATE TABLE clan_story(token_id TEXT PRIMARY KEY, state TEXT, updated REAL)")
for i in range(1, 6):
    old.execute("INSERT INTO clan_feed VALUES(?,?,?,?,?,?,?,?,?,?)", ("t1", i, 100.0 + i, i, 1, "ticker", "neutral", 1, "Old line %d." % i, '["Jeff"]'))
old.commit()
rows0 = old.execute("SELECT * FROM clan_feed ORDER BY id").fetchall()
CS.ensure(old); CS.ensure(old); old.commit()                      # twice: idempotent
cols = [r[1] for r in old.execute("PRAGMA table_info(clan_feed)")]
check(cols[-2:] == ["lid", "params"] and len(cols) == 12, "legacy table gained exactly lid + params (%s)" % cols[-3:])
rows1 = old.execute("SELECT token_id,id,ts,day,week,kind,mood,faction,text,names FROM clan_feed ORDER BY id").fetchall()
check(rows1 == rows0 and old.execute("SELECT COUNT(*) FROM clan_feed WHERE lid IS NULL AND params IS NULL").fetchone()[0] == 5, "no old row rewritten, new columns NULL")
check([m["text"] for m in CS.read_feed(old, "t1", 5, lang="pl")] == ["Old line %d." % i for i in (5, 4, 3, 2, 1)] and
      all(m["lang"] == "en" for m in CS.read_feed(old, "t1", 5, lang="pl")), "old rows read back in English whatever language is asked")
# a new message lands next to the old ones and is rendered in both
st0 = CS.new_state("t1", clan.WLF); st0["n"] = 5; CS._save(old, "t1", st0)      # the daemon keeps counting message ids after the old rows
CS.on_new_run(old, "t1", clan.WLF)
mm = CS.read_feed(old, "t1", 1, lang="pl")[0]
check(mm["lang"] == "pl" and CS.read_feed(old, "t1", 1)[0]["lang"] == "en" and mm["text"] != CS.read_feed(old, "t1", 1)[0]["text"], "new rows next to old rows: Polish and English both served")
# the update server's read-only connection (never migrates) copes with a table that has no new columns yet
ro_before = sqlite3.connect(os.path.join(d, "old.db"))
check(CS.read_feed(ro_before, "t1", 3, lang="pl") != [], "read_feed works on the migrated table")
ro_before.close()

# a stored message whose template is gone (an edited line set) or whose params are damaged stays readable in English
c9 = sqlite3.connect(os.path.join(d, "bad.db"))
CS.ensure(c9)
c9.execute("INSERT INTO clan_feed(token_id,id,ts,day,week,kind,mood,faction,text,names,lid,params) VALUES('t9',1,1,1,1,'calm','calm',1,'English text A.','[]','calm/deadbeef','{\"p\":{}}')")
c9.execute("INSERT INTO clan_feed(token_id,id,ts,day,week,kind,mood,faction,text,names,lid,params) VALUES('t9',2,2,1,1,'calm','calm',1,'English text B.','[]',?,'{broken')",
           (PL.lid("calm", CS.LINES["calm"][0][1]),))
rows9 = CS.read_feed(c9, "t9", 5, lang="pl")
check([(m["text"], m["lang"]) for m in rows9] == [("English text B.", "en"), ("English text A.", "en")], "unknown template id / broken params: the English text is served")

# the launcher's generated ticker.js agrees with the generator (stale file = FAIL: run release/launcher/scripts/gen-ticker.py)
tj = open(os.path.join(TOOLS, "..", "release", "launcher", "src", "ticker.js"), encoding="utf-8").read()
m_pl = re.search(r"const TICKER_PL = (\{.*?\});\n", tj, re.S)
tpl = json.loads(m_pl.group(1)) if m_pl else {}
m_en = re.search(r"const TICKER = (\{.*?\});\n", tj, re.S)
ten = json.loads(m_en.group(1)) if m_en else {}
check(tpl.get("healthy") == PL.TICKER_HEALTHY and tpl.get("sick") == PL.TICKER_SICK and tpl.get("hungry") == PL.TICKER_HUNGRY and
      ten.get("healthy") == D.TICKER_HEALTHY and set(ten) <= set(tpl), "release/launcher/src/ticker.js has TICKER and TICKER_PL up to date, same keys")
check(all(tpl["gender"].get(n) in ("m", "f", "n") for n in tpl.get("namesW", []) + tpl.get("namesS", [])), "TICKER_PL.gender covers every launcher name")

print("\nFAILED: %d" % len(FAILS) if FAILS else "\nall passed")
sys.exit(1 if FAILS else 0)
