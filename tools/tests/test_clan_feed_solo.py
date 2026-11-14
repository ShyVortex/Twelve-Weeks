"""The clan feed's narrator follows the clan's size (ONE survivor got "Ingrid isn't talking, isn't eating. We're watching her." and
"Nobody's laughing at dinner. It's like we forgot how."). One alive = first person singular, never we / us / our / nobody / everyone, in English and Polish;
two alive = no crowd words; stored group-voice lines that no longer fit are not shown in the menu.
Run: python tools/tests/test_clan_feed_solo.py   (temp DB only)."""
import json, os, random, re, sqlite3, sys, tempfile
import sys as _t2s, os as _t2o; _t2s.path.append(_t2o.path.normpath(_t2o.path.join(_t2o.path.dirname(_t2o.path.abspath(__file__)), ".."))); import t2rtmp  # noqa: E402,F401  (temp hygiene: tools/t2rtmp.py)

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.dirname(HERE)
sys.path.insert(0, TOOLS)
import clan, clan_story as CS, clan_story_data as D, clan_story_solo as SO, clan_story_pl as PL  # noqa: E402

FAILS = []
def check(cond, what):
    print(("ok   " if cond else "FAIL ") + what)
    if not cond:
        FAILS.append(what)

# the plural voice, written independently of the generator's own filter
EN_PLURAL = re.compile(r"\b(we|we're|we've|we'll|we'd|us|our|ours|ourselves|nobody|everyone|everybody|no one|the others|the new kid|the kids|kids|children|the camp|crowd)\b", re.I)
PL_PLURAL = re.compile(r"\b(my|nas|nam|nami|nasz\w*|nikt|nikogo|nikomu|nikim|wszyscy|wszystkich|wszystkim|wszystkimi|inni|innych|dzieciaki|dzieci|obóz\w*)\b", re.I)
EN_CROWD = re.compile(r"\b(everyone|everybody|nobody|the kids|kids|children|the others|the camp|crowd)\b", re.I)   # ("lost no one" is a count, not a crowd)
PL_CROWD = re.compile(r"\b(inni|innych|dzieciaki|dzieci)\b", re.I)

# ------------------------------------------------------------------ the pools themselves
solo_en = [t for k, v in SO.SOLO.items() for sc, t in v]
check(len(solo_en) >= 100, "solo pools hold %d lines (>= 100)" % len(solo_en))
check(not [t for t in solo_en if SO.GROUP_RE.search(t) or EN_PLURAL.search(t)], "no solo template has a plural-voice word (%s)" %
      [t for t in solo_en if EN_PLURAL.search(t)][:2])
check(not [pl for pool, sc, en, pl in SO.ROWS if pool.startswith(("solo:", "t:solo_")) and PL_PLURAL.search(pl)], "no solo Polish template has a plural-voice word (%s)" %
      [pl for pool, sc, en, pl in SO.ROWS if pool.startswith(("solo:", "t:solo_")) and PL_PLURAL.search(pl)][:2])
check(not [t for k, v in SO.DUO_EN.items() for sc, t in v if EN_CROWD.search(t)], "no duo template has a crowd word")
check(sum(len(v) for v in SO.DUO_EN.values()) >= 15, "duo pools hold %d lines (>= 15)" % sum(len(v) for v in SO.DUO_EN.values()))
for fk, banned in (("W", D.BANNED_WOLF), ("S", D.BANNED_SERA)):
    bad = [t for k, v in list(SO.SOLO.items()) + list(SO.DUO_EN.items()) for sc, t in v if sc in ("*", fk) and any(re.search(re.escape(w.strip()), t, re.I) for w in banned)]
    check(not bad, "faction vocabulary %s in solo / duo lines (%s)" % (fk, bad[:2]))
check(all(len(SO.SOLO["calm"]) >= 24 for _ in [0]) and sum(1 for sc, t in SO.SOLO["calm"] if sc == "W") >= 8 and sum(1 for sc, t in SO.SOLO["calm"] if sc == "S") >= 8,
      "faction flavour: >= 8 WLF and >= 8 Seraphite solo lines")

# ------------------------------------------------------------------ the live ticker with ONE survivor
def make_clan(c, tid, faction, state, dead=(), morale=50):
    clan.save(c, tid, {"faction": faction, "status": 1, "day": 9, "healthy": 1 if state == "h" else 0, "hungry": 1 if state == "u" else 0,
                       "sick": 1 if state == "s" else 0})
    st = CS.ensure_roster(c, tid)
    p = st["people"][0]
    p["n"] = "Ingrid"
    if state == "s":
        p["il"], p["is"] = "fever", 1
    st["morale"] = morale
    st["dead"] = [{"i": 100 + i, "n": n, "g": g, "r": "scavenger", "d": 5, "c": cause, "il": "", "k": 0} for i, (n, g, cause) in enumerate(dead)]
    CS._save(c, tid, st)
    return p

DEAD = [("Lev", "m", "starved"), ("Tobias", "m", "attack"), ("Yara", "f", "illness"), ("Mara", "f", "mercy"), ("Silas", "m", "lost"), ("Ruth", "f", "walkout")]
d = tempfile.mkdtemp()
c = sqlite3.connect(os.path.join(d, "solo.db"))
all_en, all_pl, bad_en, bad_pl, named = set(), set(), [], [], []
n = 0
for fac in (clan.WLF, clan.SERAPHITES):
    for state in "hus":
        for morale in (20, 50, 80):
            tid = "solo%d%s%d" % (fac, state, morale)
            p = make_clan(c, tid, fac, state, DEAD, morale)
            for lang in ("en", "pl"):
                lines = []
                for k_ in range(12):
                    lines += [t for _, t in CS.live_lines(c, tid, 6, lang, now=1_800_000_000 + k_ * CS.SLOT_S)]
                n += len(lines)
                for t in lines:
                    (all_en if lang == "en" else all_pl).add(t)
                    if "{" in t or "}" in t or "|" in t:
                        bad_en.append(t)
                    if (EN_PLURAL if lang == "en" else PL_PLURAL).search(t):
                        (bad_en if lang == "en" else bad_pl).append(t)
                    if lang == "en" and p["n"] in t:
                        named.append(t)
check(n >= 200, "sampled %d live lines (EN + PL, both factions, 3 states, 3 moods)" % n)
check(not bad_en, "EN live lines: no plural-voice word, no placeholder (%s)" % bad_en[:3])
check(not bad_pl, "PL live lines: no plural-voice word (%s)" % bad_pl[:3])
check(not named, "the survivor is never named in the third person (%s)" % named[:2])
check(len(all_en) >= 30 and len(all_pl) >= 30, "distinct live lines: %d EN, %d PL (>= 30)" % (len(all_en), len(all_pl)))

# several minutes without repeats: a healthy survivor, 6 lines every few seconds
tid = "solo-long"
make_clan(c, tid, clan.WLF, "h", DEAD, 70)
T0 = 1_800_000_000 - 1_800_000_000 % CS.ANCHOR_S if hasattr(CS, 'ANCHOR_S') else 1_800_000_000
seq = []
for k_ in range(10):
    seq += [t for _, t in CS.live_lines(c, tid, 6, now=T0 + k_ * CS.SLOT_S)]
check(len(seq) == 60 and len(set(seq)) >= 50, "60 live lines in a row (10 widget refreshes): at most a few repeats (%d unique)" % len(set(seq)))
seq2 = []
for k_ in range(40):
    seq2 += [t for _, t in CS.live_lines(c, tid, 6, now=T0 + (10 + k_) * CS.SLOT_S)]
gaps = [i - j for i, t in enumerate(seq2) for j in [max([k for k in range(i) if seq2[k] == t], default=-99)] if j >= 0]
check(not gaps or min(gaps) >= 20, "240 more lines: a line never comes back within 20 lines (closest repeat: %s)" % (min(gaps) if gaps else "none"))
grief = [t for t in seq + seq2 if any(x[0] in t for x in DEAD)]
check(grief, "the ticker mourns the actual dead (%s)" % (grief[:1],))
# grief for a named dead member reflects the cause
make_clan(c, "solo-cause", clan.SERAPHITES, "h", [("Lev", "m", "starved")], 60)
cause_lines = set()
for k_ in range(60):
    cause_lines |= {t for _, t in CS.live_lines(c, "solo-cause", 6, now=T0 + k_ * CS.SLOT_S) if "Lev" in t}
check(len(cause_lines) >= 4 and all("Lev" in t for t in cause_lines), "grief for Lev: %d different lines" % len(cause_lines))

# ------------------------------------------------------------------ generated day messages with one (and two) survivors
def day_messages(seed, size_before, fac):
    """A clan of size_before alive, a death day if it is 2, then 40 days: returns [(alive_after, message)] with the Polish rendering added."""
    rng = random.Random(seed)
    st = CS.new_state("t%d" % seed, fac)
    CS._populate(random.Random(seed), st, size_before, 0, 0, 0)
    out = []
    for day in range(1, 41):
        alive = len(st["people"])
        if alive == 0:
            break
        died = 1 if (day == 1 and size_before > 1) else 0
        deficit = rng.random() < 0.5
        r = {"supplies": 0 if deficit else 30, "needed": 10, "died": died, "gained": 0, "healed": 0, "evk": 0, "evt": 0, "evl": 0, "evg": 0}
        if day % 6 == 0:
            r.update(evk=clan.EV_ATTACK, evt=rng.choice([2, 3]), evl=0)
        size = alive - died
        kind = rng.choice("hus") if size == 1 else "h"
        newc = {"day": day, "status": clan.ALIVE, "healthy": size if kind == "h" else 0, "hungry": size if kind == "u" else 0, "sick": size if kind == "s" else 0}
        if size > 1:
            newc["healthy"], newc["hungry"], newc["sick"] = size - 1, 1, 0
        before = len(st["people"])
        msgs = CS.story_day(st, rng, newc, r)
        for m in msgs:
            m["pl"] = CS.render_msg(m["lid"], m["params"], "pl")
            m["en2"] = CS.render_msg(m["lid"], m["params"], "en")
            out.append((len(st["people"]), m))
    return out

solo_msgs, duo_msgs = [], []
for fac in (clan.WLF, clan.SERAPHITES):
    for seed in range(60):
        for alive, m in day_messages(seed, 2, fac):
            if alive == 1:
                solo_msgs.append(m)
            elif alive == 2:
                duo_msgs.append(m)
        for alive, m in day_messages(1000 + seed, 1, fac):
            if alive == 1:
                solo_msgs.append(m)
        for alive, m in day_messages(2000 + seed, 3, fac):       # 3 -> 2 on day 1, a duo from then on
            if alive == 2:
                duo_msgs.append(m)
check(len(solo_msgs) >= 200, "generated %d one-survivor day messages" % len(solo_msgs))
solo_kinds = {m["kind"] for m in solo_msgs}
check({"hunger", "ticker", "calm"} <= solo_kinds and any(k.startswith("death_") for k in solo_kinds), "solo messages cover the kinds (%s)" % sorted(solo_kinds))
bad = [m["text"] for m in solo_msgs if EN_PLURAL.search(m["text"]) or "{" in m["text"]]
check(not bad, "EN one-survivor day messages: no plural voice (%s)" % bad[:3])
bad = [m["pl"] for m in solo_msgs if not m["pl"] or PL_PLURAL.search(m["pl"]) or re.search(r"[{}|]", m["pl"])]
check(not bad, "PL one-survivor day messages: no plural voice, all rendered (%s)" % bad[:3])
check(all(m["en2"] == m["text"] for m in solo_msgs), "English re-rendered from (lid, params) equals the stored text")
check(len({m["text"] for m in solo_msgs}) >= 30, "%d distinct one-survivor day messages (>= 30)" % len({m["text"] for m in solo_msgs}))
bad = [(m["kind"], m["names"], m["text"][:80]) for m in solo_msgs if m["names"] and not (m["kind"].startswith(("death_", "grief", "guilt", "hope_after")) or m["kind"] == "loss_many")]
check(not bad, "a solo message names only the dead (never the narrator) (%s)" % bad[:3])
check(len(duo_msgs) >= 100, "generated %d two-survivor day messages" % len(duo_msgs))
bad = [m["text"] for m in duo_msgs if EN_CROWD.search(m["text"])]
check(not bad, "EN two-survivor messages: no crowd words (%s)" % bad[:3])
bad = [m["pl"] for m in duo_msgs if m["pl"] and PL_CROWD.search(m["pl"])]
check(not bad, "PL two-survivor messages: no crowd words (%s)" % bad[:3])
check(any(m["lid"].startswith("duo:") for m in duo_msgs), "duo lines are used")
# the live ticker of a duo
for fac in (clan.WLF, clan.SERAPHITES):
    tid = "duo%d" % fac
    clan.save(c, tid, {"faction": fac, "status": 1, "day": 4, "healthy": 1, "hungry": 1, "sick": 0})
    ls = []
    for lang in ("en", "pl"):
        for k_ in range(60):
            ls += [(lang, t) for _, t in CS.live_lines(c, tid, 6, lang, now=T0 + k_ * CS.SLOT_S)]
    check(not [t for lang, t in ls if (EN_CROWD if lang == "en" else PL_CROWD).search(t)], "duo live ticker %d: no crowd lines" % fac)

# ------------------------------------------------------------------ the menu filter on stored messages
c2 = sqlite3.connect(os.path.join(d, "menu.db"))
tid = "menu1"
CS.ensure(c2)
clan.save(c2, tid, {"faction": clan.SERAPHITES, "status": 1, "day": 3, "healthy": 5, "hungry": 0, "sick": 0})
CS.on_new_run(c2, tid, clan.SERAPHITES)
st = CS._load(c2, tid)
ing = dict(st["people"][0], n="Ingrid", g="f")
st["people"] = [ing]
st["dead"] = [{"i": 90, "n": "Lev", "g": "m", "r": "kid", "d": 2, "c": "starved", "il": "", "k": 0}]
CS._save(c2, tid, st)
def put(i, kind, text, names, lid=None):
    c2.execute("INSERT INTO clan_feed(token_id,id,ts,day,week,kind,mood,faction,text,names,lid,params) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
               (tid, i, 1.0 + i, 3, 1, kind, "calm", 2, text, json.dumps(names), lid, None))
put(900, "hunger", "Ingrid isn't talking, isn't eating. We're watching her.", ["Ingrid"])
put(901, "calm", "Nobody's laughing at dinner. It's like we forgot how.", [])
put(902, "ticker", "Ingrid is starving.", ["Ingrid"])
put(903, "death_starved", "Lev starved. Ingrid held his hand.", ["Lev", "Ingrid"])
put(904, "death_illness", "We buried Lev behind the long house. We stood there a long time.", ["Lev"])
sample = SO.SOLO["grief"][0][1]
put(905, "grief", "I still set out two cups in the morning. Then I remember Lev and put one back.", ["Lev"], PL.lid("solo:grief", sample))
put(906, "hope", "We fixed the roof today, Ingrid and I.", ["Ingrid"], PL.lid("duo:hope", SO.DUO_EN["hope"][0][1]))
c2.commit()
got = [t for _, t in CS.pick_for_widget(c2, tid, set(), n=10, window=20)]
check(not any("watching her" in t or "Nobody's laughing" in t or "starving" in t or "buried Lev" in t or "fixed the roof" in t for t in got),
      "menu with 1 alive hides stored we / nobody / third-person-feeling / duo lines (%s)" % got)
check(any("Lev starved" in t for t in got) and any("two cups" in t for t in got), "...but keeps the death news and the solo grief line (%s)" % got)
# two alive: crowd lines out, "we" lines in; the duo line in; the solo line out
st = CS._load(c2, tid)
st["people"].append(dict(ing, i=ing["i"] + 1, n="Rafe", g="m"))
CS._save(c2, tid, st)
got = [t for _, t in CS.pick_for_widget(c2, tid, set(), n=10, window=20)]
check(not any("Nobody's laughing" in t for t in got) and any("fixed the roof" in t for t in got) and not any("two cups" in t for t in got),
      "menu with 2 alive: no crowd line, duo line shown, solo line hidden (%s)" % got)
st = CS._load(c2, tid)
st["people"].append(dict(ing, i=ing["i"] + 2, n="Ola", g="f"))
CS._save(c2, tid, st)
got = [t for _, t in CS.pick_for_widget(c2, tid, set(), n=10, window=20)]
check(any("Nobody's laughing" in t or "watching her" in t for t in got) and not any("two cups" in t or "fixed the roof" in t for t in got),
      "menu with 3 alive: group lines are back, the diary / duo lines are gone (%s)" % got)

print("\nFAILED: %d" % len(FAILS) if FAILS else "\nall passed")
sys.exit(1 if FAILS else 0)
