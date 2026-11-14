"""Clan chronicle: small multi-sentence vignettes for the clan feed with real personalities and the player's real match results.  Sits on top of
tools/clan_story.py (roster, diary) and tools/clan_alife.py (threads over days).  It NEVER changes a number or a person's state; it only writes text.

  persona(person, people, fk)      stable personality of one survivor: temperament, habit, past, bond partner + bond type.  A pure function of the name, the
                                   role and the roster (crc32), so it needs no storage and never changes while the person lives.
  tagline(person, fk, lang)        one short line for the roster of the clan screen ("Medic - winds a dead watch every dawn").
  day_rows(st, newc, r, match, used, rng)   the chronicle rows of one clan day.  `match` = {"map","kills","deaths","downs"} of the player's real match or None
                                   (r["match"] is read when `match` is None); without it the match-report vignettes are skipped.
  render_msg(lid, params, lang)    renders a stored row ("ch/<piece ids>") in EN or PL at read time like the other feed rows.

A row = headline (what happened, with the real numbers) + reaction of person A by temperament + (usually) A's habit + (sometimes) a bond touch or a prep line.
The headline is the first sentence and is kept short for the one-line in-game widget (clan_story.short_text shows whole sentences up to 118 chars).
Repeat control: `used` = {piece id: last day}; a piece is not reused within WINDOW_DAYS while another fits.  All of it is deterministic from the rng given.
"""
import os
import re
import sys
import zlib

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import clan                                                  # noqa: E402
import clan_story as CS                                      # noqa: E402
import clan_story_data as D                                  # noqa: E402
import clan_alife_lex as X                                   # noqa: E402
import clan_story_pl as PLN                                  # noqa: E402
import clan_chronicle_text as T                              # noqa: E402
import clan_kids as KD                                       # noqa: E402  (kids are never fighters)

SWITCH_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "clan_chronicle.txt")
WINDOW_DAYS = 24
MAX_ROWS = 3
MAX_TOUCH = 2
TEMPERS = ["calm", "hot", "anxious", "dry", "tender", "stubborn"]
TEMPER_LABEL = {"calm": ("calm", "spokojny", "spokojna"), "hot": ("hot-headed", "porywczy", "porywcza"), "anxious": ("anxious", "lękliwy", "lękliwa"),
                "dry": ("dry-witted", "zgryźliwy", "zgryźliwa"), "tender": ("gentle", "łagodny", "łagodna"), "stubborn": ("stubborn", "uparty", "uparta")}
BOND_TYPES = ["kin", "mentor", "rival", "sweet"]
# short habit phrases for the roster tagline: index = position in the habit pool (T.POOLS["habit"] order); (EN, PL)
HABIT_SHORT = [("winds a dead watch every dawn", "nakręca martwy zegarek co świt"), ("hums the same three bars", "nuci w kółko trzy takty"),
               ("writes inside {his} cap", "pisze wewnątrz czapki"), ("drinks from one tin mug only", "pije tylko z jednego kubka"),
               ("saves the last spoonful for a dog", "zostawia łyżkę dla psa"), ("draws a flower by each name that returns", "rysuje kwiatek przy każdym, kto wraca"),
               ("still makes the bed tight", "wciąż ściele łóżko na sztywno"), ("sleeps with laced boots", "śpi w zawiązanych butach"),
               ("talks to the radio", "rozmawia z radiem"), ("peels apples that are not there", "obiera nieistniejące jabłka"),
               ("salutes the flag each morning", "co rano salutuje fladze"), ("ties a thread for every day survived", "wiąże nitkę za każdy przeżyty dzień"),
               ("keeps bottle caps in a sock", "trzyma kapsle w skarpecie"), ("draws little houses in chalk", "rysuje kredą małe domki"),
               ("sleeps with a dead flashlight", "śpi z latarką bez baterii"), ("whispers to a stone", "szepcze do kamienia"),
               ("tells the weather by a knee", "przepowiada pogodę po kolanie"), ("recites the old street names", "odmawia nazwy dawnych ulic"),
               ("reads every label twice", "czyta każdą etykietę dwa razy"), ("whittles little things and gives them away", "struga drobiazgi i je rozdaje"),
               ("saves ration foil", "chowa folię z racji"), ("counts the stairs aloud", "liczy schody na głos"), ("always sits facing the door", "zawsze siada twarzą do drzwi"),
               ("presses flowers in the ledger", "suszy kwiaty w księdze"), ("taps every doorframe", "stuka we framugi"), ("reads empty tins like a menu", "czyta puste puszki jak menu"),
               ("polishes the same boots on Sundays", "pastuje te same buty w niedziele"), ("knots thread into strangers' sleeves", "wiąże nitki w rękawy obcych"),
               ("sings to the generator", "śpiewa agregatowi"),
               ('patches one jacket forever', 'łata w kółko jedną kurtkę'),
               ('lends pencil stubs', 'pożycza ogryzki ołówków'),
               ('washes the cup three times', 'myje kubek trzy razy'),
               ('walks the wall at dusk', 'obchodzi mur o zmierzchu'),
               ('names the tins by their dents', 'nadaje puszkom imiona'),
               ('reads a coverless book', 'czyta książkę bez okładki'),
               ('whistles at the infirmary door', 'gwiżdże przy izbie chorych'),
               ('keeps a jar of beach sand', 'trzyma słoik piasku z plaży'),
               ("mends other people's laces", 'naprawia cudze sznurowadła'),
               ('writes letters and burns them', 'pisze listy i je pali'),
               ('chews an unlit matchstick', 'żuje niezapaloną zapałkę'),
               ('sets one extra place at the table', 'stawia jedno miejsce więcej przy stole')]
# who may have a habit: (life stage, faction): "any" | "adult" (not a kid) | "kid" | "elder"
HABIT_META = [("any", "*")] * 9 + [("adult", "*"), ("any", "W"), ("any", "S")] + [("kid", "*")] * 4 + [("elder", "*"), ("elder", "*"), ("elder", "*")] + [("any", "*")] * 7 \
    + [("any", "W"), ("any", "S"), ("any", "*")] + [("any", "*")] * 12
# pasts: (faction, life stage, EN, PL masculine, PL feminine); stage "adult" fits grown survivors and elders, "kid" only kids, "elder" only old-timers
PASTS = [("W", "adult", "ex-line soldier", "żołnierz liniowy z dawnych lat", "żołnierka liniowa z dawnych lat"),
         ("W", "adult", "came over from the Scars", "przeszedł od Blizn", "przeszła od Blizn"),
         ("W", "adult", "grew up in the QZ", "dorastał w strefie kwarantanny", "dorastała w strefie kwarantanny"),
         ("S", "adult", "Wolf deserter", "dezerter z Wilków", "dezerterka z Wilków"),
         ("S", "adult", "born on the island", "urodzony na wyspie", "urodzona na wyspie"),
         ("S", "adult", "convert from the city", "nawrócony z miasta", "nawrócona z miasta"),
         ("*", "adult", "former teacher", "dawny nauczyciel", "dawna nauczycielka"),
         ("*", "adult", "nurse's apprentice", "uczeń pielęgniarki", "uczennica pielęgniarki"),
         ("*", "adult", "lost a whole family", "stracił całą rodzinę", "straciła całą rodzinę"),
         ("*", "adult", "ran away at fourteen", "uciekł w wieku czternastu lat", "uciekła w wieku czternastu lat"),
         ("W", "kid", "born in the quarantine zone", "urodzony w strefie kwarantanny", "urodzona w strefie kwarantanny"),
         ("W", "kid", "carried in on a mother's back", "wniesiony na plecach matki", "wniesiona na plecach matki"),
         ("S", "kid", "born on the island", "urodzony na wyspie", "urodzona na wyspie"),
         ("S", "kid", "found by the Sisters at the shore", "znaleziony przez Siostry na brzegu", "znaleziona przez Siostry na brzegu"),
         ("*", "kid", "found in a ruin at four", "znaleziony w ruinach w wieku czterech lat", "znaleziona w ruinach w wieku czterech lat"),
         ("*", "kid", "orphaned at six", "osierocony w wieku sześciu lat", "osierocona w wieku sześciu lat"),
         ("*", "kid", "never saw the old world", "nie widział dawnego świata", "nie widziała dawnego świata"),
         ("*", "elder", "remembers the old world", "pamięta dawny świat", "pamięta dawny świat"),
         ("*", "elder", "buried a spouse the first winter", "pochował żonę pierwszej zimy", "pochowała męża pierwszej zimy"),
         ("*", "elder", "taught half the camp their letters", "nauczył pół obozu liter", "nauczyła pół obozu liter"),
         ("*", "elder", "walked here from another state", "przyszedł tu pieszo z innego stanu", "przyszła tu pieszo z innego stanu")]
WHENS = [("tomorrow", "jutro"), ("in two days", "za dwa dni"), ("before the week is out", "przed końcem tygodnia")]
import clan_chronicle_maps as MAPN           # noqa: E402  (EN display name -> the game's Polish map name, from tools/ext/loc_pl.h)


def map_name(en, lang="en"):
    en = str(en or "")
    en = MAPN.EN_SHORT.get(en, en)
    return MAPN.PL.get(en, en) if lang == "pl" else en
MOODS = {"match_kills": "calm", "match_strong": "cheerful", "match_even": "calm", "match_bad": "worried", "match_downs": "worried", "haul_good": "cheerful", "haul_short": "worried",
         "ration": "worried", "raid_prep": "afraid", "mourn": "grieving", "lastwords": "grieving", "sick_watch": "worried", "hunger": "worried",
         "newcomer": "hopeful", "kids": "cheerful", "quarrel": "worried", "quiet": "calm"}

# ------------------------------------------------------------------ loot
# Practical goods carry a quantity.  (cat, EN one, EN many, PL nominative one, PL accusative one, PL few (2-4), PL many (5+), morale when found)
USE = {
    "pine": ("food", "a can of pineapple", "cans of pineapple", "puszka ananasa", "puszkę ananasa", "puszki ananasa", "puszek ananasa", 1),
    "beans": ("food", "a can of beans", "cans of beans", "puszka fasoli", "puszkę fasoli", "puszki fasoli", "puszek fasoli", 1),
    "bandage": ("med", "a bandage", "bandages", "bandaż", "bandaż", "bandaże", "bandaży", 1),
    "abx": ("med", "a pack of antibiotics", "packs of antibiotics", "opakowanie antybiotyków", "opakowanie antybiotyków", "opakowania antybiotyków", "opakowań antybiotyków", 2),
    "alcohol": ("med", "a bottle of alcohol", "bottles of alcohol", "butelka spirytusu", "butelkę spirytusu", "butelki spirytusu", "butelek spirytusu", 1),
    "r38": ("ammo", "a .38 round", ".38 rounds", "nabój .38", "nabój .38", "naboje .38", "naboi .38", 0),
    "box9": ("ammo", "a box of 9mm", "boxes of 9mm", "pudełko 9 mm", "pudełko 9 mm", "pudełka 9 mm", "pudełek 9 mm", 0),
    "filter": ("tool", "a water filter", "water filters", "filtr do wody", "filtr do wody", "filtry do wody", "filtrów do wody", 2),
    "battery": ("tool", "a battery", "batteries", "bateria", "baterię", "baterie", "baterii", 1),
    "scissors": ("tool", "a pair of scissors", "pairs of scissors", "para nożyczek", "parę nożyczek", "pary nożyczek", "par nożyczek", 1),
    "rags": ("tool", "a rag", "rags", "szmata", "szmatę", "szmaty", "szmat", 0),
}
# Keepsakes (morale): key -> (EN, PL accusative, morale)
KEEP = {"chess": ("a chessboard", "szachownicę", 5), "guitar": ("a guitar string", "strunę gitarową", 4), "comic": ("a comic book", "komiks", 4),
        "teddy": ("a teddy bear", "pluszowego misia", 6), "seeds": ("a pouch of seeds", "woreczek nasion", 4), "cards": ("a deck of cards", "talię kart", 4),
        "harmonica": ("a harmonica", "harmonijkę", 5)}
CAT_POOL = {"food": "use_food", "med": "use_med", "ammo": "use_ammo", "tool": "use_tool"}
# portrait ids for the UI: faction/sex/model/expression (pictures land in work/portraits/<faction>/<sex>/<model>_<expression>.png)
EXPRESSIONS = ["happy", "neutral", "sad", "sick", "hurt", "scared", "hungry", "dead"]


def qty(key, n, lang="en"):
    """'15 .38 rounds' / '15 naboi .38' (accusative); n == 1 -> 'a .38 round' / 'nabój .38'."""
    e = USE[key]
    n = max(1, int(n))
    if lang == "pl":
        if n == 1:
            return e[4]
        few = 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14
        return "%d %s" % (n, e[5] if few else e[6])
    return e[1] if n == 1 else "%d %s" % (n, e[2])


def loot_phrase(key, n, lang="en"):
    if key in KEEP:
        return KEEP[key][1 if lang == "pl" else 0]
    return qty(key, n, lang)


def join_list(items, lang):
    if len(items) <= 1:
        return "".join(items)
    return ", ".join(items[:-1]) + (" i " if lang == "pl" else " and ") + items[-1]


def roll_loot(rng, r, match, newc, have=()):
    """Loot of one match: [[key, n], ...] - 1-2 practical goods (what the clan needs most, qty by the match's supplies and performance) + a keepsake 55 %."""
    sup, need = int(r.get("supplies", 0)), max(1, int(r.get("needed", 1)))
    k = int(match.get("kills") or 0)
    perf = 1.0 + min(1.0, k / 12.0) - 0.4 * min(1.0, int(match.get("deaths") or 0) / 8.0)
    units = max(1, int(round((1 + sup / 6.0) * perf)))
    cats = []
    if int(newc.get("sick", 0)):
        cats.append("med")
    if sup < need or int(newc.get("hungry", 0)):
        cats.append("food")
    cats += rng.sample(["ammo", "tool", "food", "med"], 2)
    out, seen = [], set()
    for c in cats:
        if c in seen or len(out) >= 2:
            continue
        seen.add(c)
        key = rng.choice([x for x, e in USE.items() if e[0] == c])
        n = units * (rng.choice([4, 5, 6, 8]) if c == "ammo" and key == "r38" else 1)
        if key in ("box9", "filter", "scissors", "abx"):
            n = max(1, units // 3)
        out.append([key, n])
    if rng.random() < 0.4:                                          # a keepsake: one the clan does not own yet while there is one
        out.append([rng.choice([k for k in sorted(KEEP) if k not in have] or sorted(KEEP)), 1])
    return out


REG = {}
BY_POOL = {}
for _pool, _rows in T.POOLS.items():
    for _sc, _tone, _en, _pl in _rows:
        _id = "%s~%08x" % (_pool, zlib.crc32(_en.encode("utf-8")) & 0xFFFFFFFF)
        if _id in REG:
            raise ValueError("duplicate chronicle piece " + _id)
        REG[_id] = (_pool, _sc, _tone, _en, _pl, X.letters_of(_en) | X.letters_of(_pl), X.vars_of(_en), X.vars_of(_pl))
        BY_POOL.setdefault(_pool, []).append(_id)


def enabled():
    """Switch: env T2R_CLAN_CHRONICLE=1/0, else tools/clan_chronicle.txt containing 0 / off to turn it off; default ON (it was OFF: without it the journal held only
    unconnected diary rows - no saga, arcs, member memory)."""
    v = os.environ.get("T2R_CLAN_CHRONICLE")
    if v is None:
        try:
            v = open(SWITCH_FILE, encoding="utf-8").read().strip()
        except OSError:
            return True
    return v.strip().lower() not in ("0", "off", "false", "no")


def _h(*parts):
    return zlib.crc32("|".join(str(x) for x in parts).encode("utf-8")) & 0xFFFFFFFF


# ------------------------------------------------------------------ personas
def _stage(p):
    return "kid" if p["r"] == "kid" else "elder" if p["r"] == "elder" else "adult"


def _habit_ok(i, p, fk):
    cls, sc = HABIT_META[i]
    if KD.is_kid(p) and (KD.combat_text(HABIT_SHORT[i][0], "en") or KD.combat_text(HABIT_SHORT[i][1], "pl")):       # a kid has no fighter's habit (sharpening a blade, counting rounds ...)
        return False
    return sc in ("*", fk) and (cls == "any" or cls == _stage(p) or (cls == "adult" and _stage(p) == "elder"))


def habit_pref(p, fk):
    """The person's habits in their own stable order of preference (a pure function of name and role)."""
    ok = [i for i in range(len(HABIT_SHORT)) if _habit_ok(i, p, fk)]
    return sorted(ok, key=lambda i: _h("habit", p["n"], p["r"], i))


def assign_habits(st, fk):
    """Habits are unique inside a clan while the pool allows: every living member keeps the one assigned (st["ch"]["hab"], by person id); a new member takes the
    first habit of their own preference order that no living member has.  Persisted with the story state."""
    hab = ch_state(st).setdefault("hab", {})
    alive = {str(p["i"]) for p in st["people"]}
    for k in [k for k in hab if k not in alive]:
        del hab[k]
    taken = set(hab.values())
    for p in sorted(st["people"], key=lambda q: q["i"]):
        if str(p["i"]) in hab and (not KD.is_kid(p) or _habit_ok(hab[str(p["i"])], p, fk)):
            continue
        pref = habit_pref(p, fk)
        free = [i for i in pref if i not in taken]
        hab[str(p["i"])] = (free or pref)[0]
        taken.add(hab[str(p["i"])])
    return hab


def persona(p, people, fk, st=None):
    """Stable personality of survivor p among `people` (the living roster): temperament, habit index, past, bond partner id + bond type.  With the clan story
    state `st` the habit is the clan-unique assigned one (assign_habits); without it the person's first preference."""
    h = _h("persona", p["n"], p["r"], p["g"])
    pasts = [i for i, x in enumerate(PASTS) if x[0] in ("*", fk) and (x[1] == _stage(p) or (x[1] == "adult" and _stage(p) == "elder"))]
    hab = None
    if st is not None:
        hab = ch_state(st).get("hab", {}).get(str(p["i"]))
        if hab is None:
            hab = assign_habits(st, fk).get(str(p["i"]))
    out = {"temper": TEMPERS[h % 6], "habit": hab if hab is not None else habit_pref(p, fk)[0], "past": pasts[(h >> 8) % len(pasts)], "bond": None, "bt": None}
    others = sorted((q for q in people if q["i"] != p["i"]), key=lambda q: _h("ring", p["n"], q["n"]))
    if others:
        q = others[0]
        pair = tuple(sorted((p["n"], q["n"])))
        bt = BOND_TYPES[_h("bond", *pair) % 4]
        if "kid" in (p["r"], q["r"]) and bt == "sweet":
            bt = "kin"
        if p["r"] == "kid" and q["r"] == "elder" or (p["r"] == "elder" and q["r"] == "kid"):
            bt = "mentor"
        out["bond"], out["bt"] = q["i"], bt
    return out


def tagline(p, people, fk, lang="en", st=None):
    """Roster tagline: 'Medic, gentle. Nurse's apprentice. Winds a dead watch every dawn.' (no personal names)."""
    ps = persona(p, people, fk, st)
    pl = lang == "pl"
    g = p["g"]
    role = X.role_word(p, fk, "pl" if pl else "en")
    te = TEMPER_LABEL[ps["temper"]]
    t = te[2] if (pl and g == "f") else te[1] if pl else te[0]
    ha = HABIT_SHORT[ps["habit"]][1 if pl else 0].replace("{his}", {"m": "his", "f": "her"}.get(g, "their"))
    past = PASTS[ps["past"]]
    pa = (past[4] if g == "f" else past[3]) if pl else past[2]
    return "%s, %s. %s. %s." % (role[:1].upper() + role[1:], t, pa[:1].upper() + pa[1:], ha[:1].upper() + ha[1:])


# ------------------------------------------------------------------ text variables
def _vars(sym, lang):
    fk = sym["f"]
    F = D.FACTION[fk]
    v = {k: sym.get(k, 0) for k in ("sup", "need", "kills", "deaths", "downs")}
    v["n"] = max(0, sym.get("need", 0) - sym.get("sup", 0))
    v["leader"] = ("Command" if fk == "W" else "the Prophet") if lang == "en" else ("Dowództwo" if fk == "W" else "Prorok")   # a title: stories name only roster members
    lt = sym.get("loot") or []
    v["loot_list"] = join_list([loot_phrase(k, n, lang) for k, n in lt], lang)
    if sym.get("finds"):                                            # the rich loot model (tools/clan_loot.py): the raid's real findings
        import clan_loot
        v["loot_list"] = clan_loot.items_text(sym["finds"], lang)
    it = sym.get("it")
    if it in USE:
        v["item"] = qty(it, sym.get("itn", 1), lang)
        v["thing"] = qty(it, 1, lang)
        if lang == "en":
            v["thing"] = "the " + v["thing"][2:] if v["thing"].startswith("a ") else v["thing"]
    wen, wpl = WHENS[sym.get("when", 0) % 3]
    v["when"] = wpl if lang == "pl" else wen
    v["map"] = map_name(sym.get("map", ""), lang)
    if lang == "pl":
        e = PLN.ENEMY[fk]
        v["enemy"], v["enemy_gen"], v["enemy_ins"] = e[0], e[1], e[2]
        v["enemies"] = e[1]
    else:
        v["enemy"] = F["enemy"]
        v["enemies"] = "the " + F["enemies"]
    return v


def _render_ids(ids, people, sym, lang):
    fk = sym["f"]
    vars_ = _vars(sym, lang)
    parts = []
    for i in ids:
        _p, _sc, _t, en, pl, *_ = REG[i]
        parts.append(X.render(pl if lang == "pl" else en, people, vars_, lang, fk))
    return " ".join(parts)


def render_msg(lid, params, lang="en"):
    """A stored chronicle row (lid "ch/<piece ids joined by +>", params {"p": {letter: [name, gender, role]}, "s": sym}); None when a piece is unknown."""
    if lid and lid.startswith("arc/"):
        import clan_arcs
        return clan_arcs.render_msg(lid, params, lang)
    if lid and lid.startswith("sg/"):
        import clan_saga
        return clan_saga.render_msg(lid, params, lang)
    if not lid or not lid.startswith("ch/") or not isinstance(params, dict):
        return None
    ids = lid[3:].split("+")
    if any(i not in REG for i in ids):
        return None
    people = {k: {"n": str(v[0]), "g": v[1] if v[1] in CS.PRON else "n", "r": (v[2] if len(v) > 2 else "scavenger")} for k, v in params.get("p", {}).items()}
    sym = params.get("s", {})
    return _render_ids(ids, people, sym, "pl" if PLN.norm_lang(lang) == "pl" else "en")


# ------------------------------------------------------------------ choosing
def _scope_ok(sc, fk):
    return sc in ("*", fk)


def _tone_ok(tone, morale):
    return tone in ("*", "temper") or (tone == "g" and morale >= 45) or (tone == "b" and morale <= 60) or (tone == "n" and 30 <= morale <= 75)


def _pick(pool, fk, morale, letters, rng, used, day, temper=None, tone_force=None, avail=None, people=None):
    cands = []
    for i in BY_POOL.get(pool, []):
        _p, sc, tone, en, pl, lt, *_ = REG[i]
        if not _scope_ok(sc, fk) or not lt <= letters:
            continue
        if people and not KD.kid_safe(en, people, pl):                  # a kid is never in a combat line
            continue
        if avail is not None and not (REG[i][6] | REG[i][7]) <= avail:
            continue
        if temper is not None and tone != temper:
            continue
        if temper is None and not _tone_ok(tone, morale) and tone_force != tone:
            continue
        cands.append(i)
    if not cands:
        return None
    fresh = [i for i in cands if day - used.get(i, -999) >= WINDOW_DAYS]
    pool_ = fresh or sorted(cands, key=lambda i: used.get(i, -999))[:max(1, len(cands) // 2)]
    return rng.choice(sorted(pool_))


def _pp(p):
    return [p["n"], p["g"], p["r"]]


class _Day:
    def __init__(self, st, newc, r, match, used, rng):
        self.st, self.newc, self.r, self.match, self.used, self.rng = st, newc, r, match, used, rng
        self.fk = "S" if st["fac"] == clan.SERAPHITES else "W"
        self.day = int(newc["day"])
        self.alive = list(st["people"])
        self.byid = {p["i"]: p for p in self.alive}
        self.morale = int(st.get("morale", 50))
        self.spot = {p["i"] for p in self.alive if str(p["i"]) in (st.get("ch") or {}).get("away", {})}      # away in a story arc: no other line uses them
        self.rows = []
        self.finds = []

    def person(self, role=None, states=("h", "u", "s"), exclude=(), fight=False):
        """fight=True (a match, raid, haul or weapon line): grown people only, never a kid (clan_kids.py)."""
        c = [p for p in self.alive if p["s"] in states and p["i"] not in self.spot and p["i"] not in exclude and (role is None or p["r"] == role)
             and (not fight or KD.can_fight(p))]
        if not c:
            return None
        # spotlight-fair: the person who has been in the chronicle the longest ago comes first
        c.sort(key=lambda p: (self.used.get("P%d" % p["i"], -999), _h("sp", self.day, p["n"])))
        return c[0]

    def compose(self, kind, A, B=None, C=None, D_=None, sym_extra=None, react=True, habit=0.6, bond=0.35, prep=False, extra_pools=()):
        fk, rng, day = self.fk, self.rng, self.day
        people = {"A": A}
        if B is not None:
            people["B"] = B
        if C is not None:
            people["C"] = C
        if D_ is not None:
            people["D"] = D_
        letters = set(people)
        sym = {"f": fk, "day": day, "when": self.rng.randrange(3)}
        if self.match:
            sym.update({k: int(self.match[k]) for k in ("kills", "deaths", "downs") if self.match.get(k) is not None})
            sym["map"] = str(self.match.get("map", ""))
        sym["sup"], sym["need"] = int(self.r.get("supplies", 0)), int(self.r.get("needed", 0))
        sym.update(sym_extra or {})
        avail = {"sup", "need", "n", "leader", "when", "enemy", "enemies", "enemy_gen", "enemy_ins"} | {k for k in ("kills", "deaths", "downs", "map") if k in sym}
        if sym.get("loot") or sym.get("finds"):
            avail.add("loot_list")
        if sym.get("it"):
            avail |= {"item", "thing"}
        head = _pick(kind, fk, self.morale, letters, rng, self.used, day, avail=avail, people=people)
        if not head:
            return None
        ids = [head]
        tone = REG[head][2]
        pers = persona(A, self.alive, fk, self.st)
        for ep in extra_pools:
            xp = _pick(ep, fk, self.morale, letters, rng, self.used, day, avail=avail, people=people)
            if xp:
                ids.append(xp)
        opt = []                                                    # optional touches; at most MAX_TOUCH of them, in random order
        if react and rng.random() < 0.6:
            rp = _pick("react_g" if tone == "g" or (tone in ("*", "n") and self.morale >= 55) else "react_b", fk, self.morale, letters, rng, self.used, day,
                       temper=pers["temper"], people=people)
            if rp:
                opt.append(rp)
        if prep and B is not None:
            pp = _pick("prep", fk, self.morale, letters, rng, self.used, day, people=people)
            if pp:
                opt.append(pp)
        hb = BY_POOL["habit"][pers["habit"]]
        if rng.random() < habit and day - self.used.get(hb, -999) >= 12:
            opt.append(hb)
        if B is not None and "B" not in REG[head][5] and rng.random() < bond:
            bp = _pick("bond_" + (pers["bt"] or "kin"), fk, self.morale, {"A", "B"}, rng, self.used, day, people=people)
            if bp:
                opt.append(bp)
        rng.shuffle(opt)
        ids += opt[:MAX_TOUCH]
        for i in ids:
            self.used[i] = day
        for p in people.values():
            if "i" in p:
                self.used["P%d" % p["i"]] = day
                self.spot.add(p["i"])
        msg_people = {k: _pp(v) for k, v in people.items()}
        lid = "ch/" + "+".join(ids)
        params = {"p": msg_people, "s": sym}
        text = render_msg(lid, params, "en")
        if KD.any_kid(people) and not (KD.kid_text_ok(text, people) and KD.kid_text_ok(render_msg(lid, params, "pl"), people, "pl")):
            return None                                             # the filled-in line makes a kid a fighter: no row (the caller tries again without the partner)
        names = [v["n"] for v in people.values() if re.search(r"(?<!\w)" + re.escape(v["n"]) + r"(?!\w)", text)]
        return {"kind": "chron", "mood": MOODS.get(kind, "calm"), "text": text, "names": names, "lid": lid, "params": params}

    def partner(self, A):
        b = self.byid.get(persona(A, self.alive, self.fk, self.st)["bond"])
        return b if b and b["i"] != A["i"] else None


def ch_state(st):
    """The chronicle's own persistent state, inside the clan_story state (saved with it): repeat control, loot on hand, keepsakes, the match log."""
    c = st.setdefault("ch", {})
    c.setdefault("used", {})
    c.setdefault("inv", {})            # practical goods: key -> quantity
    c.setdefault("keep", {})           # keepsakes: key -> {"d": day found, "m": map}
    c.setdefault("log", [])            # last matches: {"d","map","sup","need","parts","kills","deaths","downs","loot":[[key, n]]}
    return c


def match_log(st, lang="en", limit=20):
    """The browsable match summaries for the UI (newest first): dicts with the numbers and the loot text in the language."""
    out = []
    for e in reversed(ch_state(st)["log"][-limit:]):
        row = dict(e, loot_text=join_list([loot_phrase(k, n, lang) for k, n in e["loot"]], "pl" if lang == "pl" else "en"))
        if e.get("finds"):                                          # rich findings (tools/clan_loot.py): 'finds' = items with icon id + story, loot_text = their item list; 'loot' stays as it was
            import clan_loot
            row["loot_text_basic"] = row["loot_text"]
            row["finds"] = clan_loot.public(e["finds"], "pl" if lang == "pl" else "en")
            row["loot_text"] = clan_loot.items_text(e["finds"], "pl" if lang == "pl" else "en")
        out.append(row)
    return out


def inventory(st, lang="en"):
    c = ch_state(st)
    return ([qty(k, n, lang) for k, n in sorted(c["inv"].items()) if n > 0], [loot_phrase(k, 1, lang) for k in sorted(c["keep"])])


def day_rows(st, newc, r, match=None, used=None, rng=None):
    """The chronicle rows of the clan day; also records the members' status changes (tools/clan_status.py, read-only)."""
    rows = _day_rows(st, newc, r, match, used, rng)
    try:
        import clan_status
        clan_status.observe(st, rows)
    except Exception as ex:                                         # noqa: BLE001 - the status updates never break the chronicle
        sys.stderr.write("clan_status failed: %r" % (ex,) + chr(10))
    return rows


def _day_rows(st, newc, r, match=None, used=None, rng=None):
    """The chronicle rows of the clan day (kind "chron"); [] when the clan is too small (fewer than 3 alive).  Updates st["ch"] in place (loot, log, repeat
    control) and nudges st["morale"] for keepsakes and practical loot - the story mood only, never a clan number."""
    import random
    cs = ch_state(st)
    assign_habits(st, "S" if st["fac"] == clan.SERAPHITES else "W")
    used = used if used is not None else cs["used"]
    r = r or {}
    match = match if match is not None else r.get("match")
    rng = rng or random.Random(_h("chron", st.get("tid", ""), newc["day"]))
    d = _Day(st, newc, r, match, used, rng)
    if len(d.alive) < 3:
        return []
    out = []
    died_now = [x for x in st["dead"] if x["d"] == d.day]
    loot = []
    if match and match.get("map"):                                  # the match's loot goes on hand now
        loot = roll_loot(rng, r, match, newc, have=cs["keep"])
        finds = []
        try:                                                        # the findings of the raid (tools/clan_loot.py), drawn from the raid's real supplies and the clan's fortune
            import clan_loot
            cur = {"win": match.get("win"), "sup": int(r.get("supplies", 0)), "need": int(r.get("needed", 0))}
            fo_st = dict(st, morale=int(st.get("morale", 50)))        # morale before this raid's loot
            score = clan_loot.fortune(fo_st, cs, hist=cs["log"][-6:] + [cur])
            finds = clan_loot.roll_finds(random.Random(_h("loot", st.get("tid", ""), d.day)), st, cs, r, match, score=score, day=d.day)
            legacy = clan_loot.legacy_loot(finds, have=cs["keep"])                   # the practical goods and keepsakes among them feed the clan's stock (inv / keep) as before
            if legacy:
                loot = legacy
            d.finds = finds
        except Exception as ex:                                     # noqa: BLE001 - the loot detail never breaks the clan
            if os.environ.get("T2R_SAGA_STRICT"):
                raise
            sys.stderr.write("clan_loot failed: %r" % (ex,) + chr(10))
        gain = 0
        for k, n in loot:
            if k in KEEP:
                cs["keep"][k] = {"d": d.day, "m": str(match["map"])}
                gain += KEEP[k][2]
            else:
                cs["inv"][k] = cs["inv"].get(k, 0) + n
                gain += USE[k][7]
        st["morale"] = min(100, int(st.get("morale", 50)) + gain)
        d.morale = int(st["morale"])
        cs["log"].append({"d": d.day, "map": str(match["map"]), "sup": int(r.get("supplies", 0)), "need": int(r.get("needed", 0)), "parts": int(r.get("parts", 0)),
                          "kills": int(match.get("kills") or 0), "deaths": match.get("deaths"), "downs": match.get("downs"), "loot": loot,
                          "execs": match.get("execs"), "revives": match.get("revives"), "win": match.get("win"), "mid": str(match.get("mid") or "")})      # mid: the key of the match's player stats (clan_ingame section 5)
        sp = r.get("sup")
        if isinstance(sp, dict) and sp.get("need"):                 # supplies per category of that day (tools/clan_supply.py): the UI's raid rows show the real split
            cs["log"][-1]["cat"] = {k: sp.get(k, {}) for k in ("got", "need", "short", "drawn")}
        if finds:
            cs["log"][-1]["finds"] = finds
            cs["log"][-1]["fort"] = cs["fort"]["s"]
        clan_loot_mod = sys.modules.get("clan_loot")
        if clan_loot_mod:
            clan_loot_mod.update_moods(st, cs)
        del cs["log"][:-30]
    import clan_arcs
    arc_rows = clan_arcs.run(d, st, newc, r, match, cs, rng)
    out.extend(arc_rows)
    d.spot |= {i for a in cs["arcs"] for i in a["c"].values()} | {int(i) for i in cs["away"]}     # people in a running arc are in no other line
    sg_rows = []
    try:                                                            # the saga (tools/clan_saga.py): long, match-tied entries with per-member memory
        import clan_saga
        sg_rows = clan_saga.run(d, st, newc, r, match, cs, rng, sys.modules[__name__], loot, died_now, arc_rows)
    except Exception as ex:                                         # noqa: BLE001 - the chronicle never breaks the clan
        if os.environ.get("T2R_SAGA_STRICT"):
            raise
        sys.stderr.write("clan_saga failed: %r" % (ex,) + chr(10))
    out.extend(sg_rows)
    plan = []
    if match and match.get("map") and not sg_rows:                  # 1. what the player's match did (the saga tells it when it ran)
        k = int(match.get("kills") or 0)
        de, dn = match.get("deaths"), match.get("downs")
        if de is None:                                              # the daemon only knows the Downed Enemy count (op 0xE2 label 1): kill-only lines
            plan.append("match_kills")
        elif dn is not None and dn >= 3 and rng.random() < 0.5:
            plan.append("match_downs")
        elif k >= max(3, 1.5 * de) and de <= 4:
            plan.append("match_strong")
        elif de > k:
            plan.append("match_bad")
        else:
            plan.append("match_even")
    if sg_rows:                                                     # 2. (the saga already told the haul, the loss and the funeral)
        pass
    elif died_now:                                                  # 2. the day's real event
        plan.append("mourn" if rng.random() < 0.6 else "lastwords")
    elif int(r.get("supplies", 0)) < int(r.get("needed", 0)):
        plan.append("haul_short" if rng.random() < 0.6 else "ration")
    else:
        plan.append("haul_good")
    if len(plan) < MAX_ROWS:                                        # 3. a life scene
        S, U = int(newc.get("sick", 0)), int(newc.get("hungry", 0))
        gained = int(r.get("gained", 0)) + int(r.get("evg", 0))
        opts = []
        if gained:
            opts.append("newcomer")
        if S:
            opts.append("sick_watch")
        if U:
            opts.append("hunger")
        opts += ["kids", "quiet"] + ([] if sg_rows else ["raid_prep", "raid_prep"]) + ([] if d.morale >= 55 else ["quarrel"])
        old_keep = [] if sg_rows else [k for k, v in cs["keep"].items() if v["d"] < d.day]
        have = {c: [k for k, n in cs["inv"].items() if n > 0 and USE[k][0] == c] for c in CAT_POOL}
        for c, ks in ({} if sg_rows else have).items():
            if ks:
                opts += ["use:" + c] * (2 if (c == "food" and U) or (c == "med" and S) or (c == "ammo") else 1)
        opts += ["keep:" + k for k in old_keep] * 3                  # a keepsake from an earlier match comes back in a story
        plan.append(rng.choice(opts))
    for kind in plan[:max(1, MAX_ROWS - len(arc_rows) - len(sg_rows))]:
        extra, pool, role, extra_ids = {}, kind, None, []
        A = B = D_ = None
        if kind.startswith("use:"):
            cat = kind[4:]
            key = rng.choice(sorted(k for k, n in cs["inv"].items() if n > 0 and USE[k][0] == cat))
            extra = {"it": key, "itn": cs["inv"][key]}
            pool, role = CAT_POOL[cat], {"food": "cook", "med": "medic", "ammo": "scout", "tool": "mechanic"}[cat]
        elif kind.startswith("keep:"):
            key = kind[5:]
            extra = {"map": cs["keep"][key]["m"]}
            pool, role = "loot_use_" + key, ("kid" if key in ("chess", "teddy", "comic") and any(p["r"] == "kid" for p in d.alive) else None)
        elif kind == "sick_watch":
            nsp = {p["i"] for p in d.alive if p.get("il") == "spores"}                  # (a spore-sick member is no "up and walking" scene: canon, no recovery)
            A = d.person(states=("s",), exclude=nsp) or d.person(exclude=nsp) or d.person()
        elif kind == "newcomer":
            A = max(d.alive, key=lambda p: p["jd"])
        elif kind == "hunger":
            role = rng.choice(["cook", "elder", "medic"])
        elif kind == "kids":
            role = rng.choice(["elder", "guard", "cook", "medic"])
        elif kind in ("mourn", "lastwords"):
            if not died_now:
                continue
            A, D_ = d.person(states=("h", "u")), died_now[0]
        else:
            role = {"match_downs": "medic", "match_kills": "scout", "haul_good": "cook", "haul_short": "cook", "ration": "cook", "raid_prep": "scout"}.get(kind)
        fight = kind in KD.COMBAT_POOLS_CHRON or kind == "use:ammo" or kind.startswith("match_") or (kind.startswith("use:") and USE[extra["it"]][0] == "ammo")
        if A is not None and fight and not KD.can_fight(A):
            A = None
        if A is None:
            A = (d.person(role=role, fight=fight) if role else None) or d.person(fight=fight)
        if A is None:
            continue
        B = d.partner(A)
        if B is None or B["i"] in d.spot or (fight and not KD.can_fight(B)):
            B = d.person(exclude={A["i"]}, states=("h", "u"), fight=fight)
        if kind.startswith("match_") and loot:
            extra = dict(extra, loot=loot, finds=getattr(d, "finds", None) or None)
            extra_ids = ["loot_found"]
        row = d.compose(pool, A, B, D_=D_, prep=(kind == "raid_prep"), sym_extra=extra, extra_pools=extra_ids,
                        react=not (kind.startswith("use:") or kind.startswith("keep:")))
        if row is None and B is not None:
            row = d.compose(pool, A, None, D_=D_, sym_extra=extra, extra_pools=extra_ids)
        if row:
            out.append(row)
            if kind.startswith("use:") and USE[extra["it"]][0] in ("food", "med"):
                cs["inv"][extra["it"]] = max(0, cs["inv"][extra["it"]] - 1)
    return out


# ------------------------------------------------------------------ the UI side: portraits, roster, public view (launcher /clanfeed.json "chron", in-game clan screen)
PORTRAIT_MODELS = 4          # models per faction and sex the portrait set is expected to have (portraits/index.json overrides it)
STATE_EXPR = {"h": "neutral", "u": "hungry", "s": "sick"}


BOND_LABEL = {"en": {"kin": "FAMILY", "mentor": "MENTOR", "apprentice": "APPRENTICE", "rival": "RIVAL", "partner": "PARTNER"},
              "pl": {"kin": "RODZINA", "mentor": "MENTOR", "apprentice": "UCZEŃ", "rival": "RYWAL", "partner": "PARTNER"}}
BOND_LABEL_F = {"pl": {"mentor": "MENTORKA", "apprentice": "UCZENNICA", "rival": "RYWALKA", "partner": "PARTNERKA"}}


def bond_label(b, a, bt, lg="en"):
    """What the bonded person b is to a, as a UI word (never the raw key): kin FAMILY, mentor / apprentice by rank (b the older = MENTOR), rival, sweet = PARTNER;
    Polish by b's gender (PARTNERKA ...). '' without a bond."""
    if not bt:
        return ""
    rank = {"kid": 0, "adult": 1, "elder": 2}
    st = lambda p: "kid" if p.get("r") == "kid" else "elder" if p.get("r") == "elder" else "adult"
    key = {"sweet": "partner", "rival": "rival", "kin": "kin"}.get(bt)
    if bt == "mentor":
        x, y = rank[st(b)], rank[st(a)]
        key = "mentor" if x >= y else "apprentice"
    if not key:
        return ""
    if b.get("g") == "f" and key in BOND_LABEL_F.get(lg, {}):
        return BOND_LABEL_F[lg][key]
    return BOND_LABEL[lg][key]


_HEADS = {}


def _heads(members, fk):
    """{name: (sex, model)} for a whole clan (people + the dead, oldest id first): each member keeps the head their name picks unless an EARLIER member wears it, then they get a
    free head of the pool; a head is repeated only when the pool for that sex has run out. Deterministic, so the roster, the status cards and the launcher agree."""
    key = (fk, tuple((m.get("i", 0), m["n"], m.get("g"), m.get("r", "")) for m in members))
    if key in _HEADS:
        return _HEADS[key]
    out, used = {}, {"m": set(), "f": set()}
    for m in sorted(members, key=lambda m: m.get("i", 0)):
        sex, model = head_model(m, fk, dedup=False)
        try:
            import clan_portraits
            if clan_portraits.enabled() and model in used[sex]:
                m2 = clan_portraits.pick(m["n"], m.get("r", ""), sex, fk, used[sex])
                if m2 is not None:
                    model = m2
        except Exception:                                           # noqa: BLE001
            pass
        used[sex].add(model)
        out[m["n"]] = (sex, model)
    if len(_HEADS) > 64:
        _HEADS.clear()
    _HEADS[key] = out
    return out


def head_model(p, fk, models=PORTRAIT_MODELS, members=None, dedup=True):
    """(sex, model id) of a member's head: the role- and age-aware pool pick (tools/clan_portraits.py, only heads with a render), else the old name hash 0..models-1.
    members = the whole clan (people + dead): no two members wear the same head while the pool has free ones (_heads)."""
    if members and dedup and p.get("n") in {m["n"] for m in members}:
        return _heads(members, fk)[p["n"]]
    sex = "f" if p["g"] == "f" else "m" if p["g"] == "m" else ("f" if _h("sex", p["n"]) & 1 else "m")
    model = _h("model", p["n"]) % max(1, models)
    try:                                                            # T2R_PORTRAIT_POOL=0 = the old hash
        import clan_portraits
        if clan_portraits.enabled():
            m2 = clan_portraits.pick(p["n"], p.get("r", ""), sex, fk)
            if m2 is not None:
                model = m2
    except Exception:                                               # noqa: BLE001 - the pool is optional
        pass
    return sex, model


def fit_expr(model, expr):
    """The expression the head HAS: the asked one, else its approved stand-in, else neutral (tools/clan_portraits.expr_for)."""
    try:
        import clan_portraits
        return clan_portraits.expr_for(model, expr)
    except Exception:                                               # noqa: BLE001
        return expr


def portrait_id(p, fk, state=None, morale=50, models=PORTRAIT_MODELS, members=None):
    """faction/sex/model/expression of a survivor's portrait ('W/f/2/sick'); the picture is portraits/<faction>/<sex>/<model>_<expression>.png (the game / launcher read the
    model + expression only: c13p-<model>_<expression>.png). Expression from the real state (healthy: happy in a good camp, scared in a broken one, else neutral; i = light duty
    -> hurt; d -> dead), then fitted to the expressions that head has."""
    sex, model = head_model(p, fk, models, members)
    st = state or p.get("s", "h")
    expr = "dead" if st == "d" else "hurt" if st == "i" else "happy" if (st == "h" and morale >= 70) else "scared" if (st == "h" and morale <= 25) else STATE_EXPR.get(st, "neutral")
    return "%s/%s/%d/%s" % (fk, sex, model, fit_expr(model, expr))


def _roster_state(st, p):
    """The state of a roster row: the status card's own state (clan_status.code_of: hungry, sick, sad, injured, depressed, shock), so a member's picture, word and colour agree
    (members shown HEALTHY wore a depressed face - the row knew only healthy / hungry / sick while the portrait followed the status code). Recovered / new = healthy."""
    base = {"h": "healthy", "u": "hungry", "s": "sick"}[p["s"]]
    try:
        import clan_status
        name = clan_status.NAMES[clan_status.code_of(st, p)]
        return name if name in ("hungry", "sick", "sad", "injured", "depressed", "shock") else base
    except Exception:                                               # noqa: BLE001 - the status look is optional
        return base


def _roster_portrait(st, p, fk):
    """The roster portrait id: the status card's expression (clan_status.code_of: depressed, shock, sad, sick, hungry, injured -> sick) when the member is not healthy, else
    portrait_id's own happy / scared / neutral rule by the camp's morale."""
    pid = portrait_id(p, fk, morale=int(st.get("morale", 50)), members=list(st["people"]) + list(st.get("dead") or []))
    try:
        import clan_status
        code = clan_status.code_of(st, p)
        if code != clan_status.HEALTHY:
            head = pid.rsplit("/", 1)[0]
            return head + "/" + fit_expr(int(head.rsplit("/", 1)[1]), clan_status.EXPR[code])
    except Exception:                                               # noqa: BLE001 - the status look is optional
        pass
    return pid


ICON = {"scavenger": "bag", "medic": "cross", "cook": "pot", "guard": "shield", "mechanic": "wrench", "scout": "eye", "gardener": "leaf", "kid": "star",
        "elder": "cane", "radio": "radio"}


def public(c, tid, lang="en", limit=40):
    """Read-only view for the launcher / game clan screen: {"roster": [...], "matches": [...], "inv": [...], "keep": [...]} ({} without a story)."""
    st = CS._load(c, tid)
    if not st:
        return {}
    fk = "S" if st["fac"] == clan.SERAPHITES else "W"
    lg = "pl" if PLN.norm_lang(lang) == "pl" else "en"
    roster = []
    for p in st["people"][:limit]:
        ps = persona(p, st["people"], fk, st)
        b = next((q for q in st["people"] if q["i"] == ps["bond"]), None)
        roster.append({"name": p["n"], "role": p["r"], "roleText": X.role_word(p, fk, lg), "icon": ICON.get(p["r"], "star"),
                       "state": _roster_state(st, p), "tagline": tagline(p, st["people"], fk, lg, st),
                       "bond": b["n"] if b else "", "bondType": ps["bt"] or "", "bondLabel": bond_label(b, p, ps["bt"], lg) if b else "", "portrait": _roster_portrait(st, p, fk)})
    inv, keep = inventory(st, lg)
    out = {"roster": roster, "matches": match_log(st, lg), "inv": inv, "keep": keep}
    try:                                                            # status updates (tools/clan_status.py): pending hungry / sad / sick / dead ... events, absent = none
        import clan_status
        stat = clan_status.public(st, fk, lg)
        if stat:
            out["status"] = stat
    except Exception:                                               # noqa: BLE001 - optional
        pass
    return out
