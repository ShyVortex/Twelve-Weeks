"""The clan as people, and the 2013-style clan feed ("[TEXT] is gnawing on rat bones." and much more).

tools/clan.py keeps the clan as four numbers (healthy / hungry / sick, day). This module gives every survivor a stable name, gender, role,
mood and (when sick) a specific illness, and writes short diary lines about how the clan is doing. It runs at each clan state change:
  on_new_run(c, tid, faction)         first day of a new clan                      (daemon.clan_side)
  on_day(c, tid, clan_state, result)  after clan.apply_match resolved a day         (daemon.clan_finalize)
Everything it says is derived from the real numbers (clan.resolve_day's result dict): who is sick is really sick, who dies matches
`died`, who joins matches `gained` + `evg`, the morale follows supply surplus / deficit streaks, deaths, sickness and event outcomes.
Storage (own tables, created on first use; the daemon works without them):
  clan_story(token_id PK, state TEXT json, updated)         roster, morale, streaks, which lines were used (no repeats until a pool is empty)
  clan_feed(token_id, id, ts, day, week, kind, mood, faction, text, names)    the last FEED_MAX messages per player
  clan_feed also has lid + params (added later, additive: ensure() ALTERs old tables): the template id and the people / variables as keys, so a stored message
  can be rendered in any language at read time (read_feed(lang="pl"), tools/clan_story_pl.py); `text` stays the English rendering. Rows written before
  that have no lid and read back in English in every language.
Message object (see release/launcher/API.md and docs/clan-feed-format.md): {id, day, week, kind, mood, faction, text, names, ts, lang}.
Faction voices: scope "W" lines are Wolves only (WLF, calls Seraphites "Scars"), "S" lines Seraphites only (calls WLF "Wolves"),
"*" lines both; tools/tests/test_clan_story.py checks the vocabulary.
"""
import json
import os
import random
import re
import sys
import time
import zlib

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import clan                                                 # noqa: E402
import clan_story_data as D                                 # noqa: E402
import clan_story_lines_good as LG                          # noqa: E402
import clan_story_lines_dark as LD                          # noqa: E402
import clan_story_solo as SO                          # noqa: E402  (the one- and two-survivor voices)
import clan_story_spores as SPR                         # noqa: E402  (spores: no cure, no recovery; TLOU canon)
import clan_story_good_rich as RG                           # noqa: E402  (rich good-state ticker rows, EN + PL)
import clan_story_pl as PLN                                 # noqa: E402  (the Polish twin of every template + the language plumbing)
import clan_kids as KD                                      # noqa: E402  (kids are never fighters: no combat lore for them)

FEED_MAX = 60                  # messages kept per player (feed_max(): 100 while the A-Life switch is on, its rows come on top of the diary)
DAY_MAX_MSGS = 4               # messages written per clan day
WIDGET_MAX = 118               # the in-game widget is one line (ext shows <= 120 chars; the wire allows 150 bytes)
STATE_V = 1

LINES = {}
LINES.update(LG.LINES)
LINES.update(LD.LINES)
LINES.update(SPR.LINES)

KIND_MOOD = {
    "chron": "calm",
    "hope": "hopeful", "plenty": "cheerful", "calm": "calm", "join": "hopeful", "recovery": "hopeful", "event_hold": "hopeful",
    "event_growth": "hopeful", "founding": "hopeful", "clan_won": "cheerful", "hope_after": "hopeful", "hunger": "worried", "starving": "desperate",
    "sick": "worried", "medicine": "worried", "worse": "afraid", "event_warn": "afraid", "event_heavy": "grim", "event_massacre": "grim",
    "event_nojoin": "grim", "clan_dead": "grim", "despair": "despair", "guilt": "grieving", "grief": "grieving", "grief_mercy": "grieving",
    "loss_many": "grieving", "death_illness": "grieving", "death_mercy": "grieving", "death_starved": "grieving", "death_lost": "grieving",
    "death_walkout": "grieving", "death_suicide": "grieving", "death_bite": "grieving", "death_bite_kin": "grieving", "death_attack": "grieving",
    "death_attack_many": "grieving", "death_turned": "grieving", "grief_turned": "grieving", "spore_worse": "afraid", "spore_hold": "worried",
    # the attack told as a horde of infected (clan.AN_HORDE; re/clan-events-1117.md)
    "event_warn_h": "afraid", "event_hold_h": "hopeful", "event_heavy_h": "grim", "event_massacre_h": "grim", "death_horde": "grieving", "death_horde_many": "grieving"}

# Messages about how someone feels / is doing RIGHT NOW (present tense): the menu shows them only while that person (names[0]) is alive.
# Everything else is a happening (a death, falling sick, a join, an event) and stays news even after the person died (a member getting sick or dying
# stays news, but "sad over someone leaving" about a dead member does not).
FEELING_KINDS = {"hope", "plenty", "calm", "hope_after", "hunger", "starving", "despair", "guilt", "grief", "grief_mercy", "grief_turned", "spore_worse", "spore_hold", "ticker", "alife"}

def _pn(**kw):
    kw["is"] = kw.pop("is_")
    return kw


PRON = {
    "m": _pn(he="he", him="him", his="his", hes="he's", himself="himself", is_="is", has="has", was="was", title="Brother"),
    "f": _pn(he="she", him="her", his="her", hes="she's", himself="herself", is_="is", has="has", was="was", title="Sister"),
    "n": _pn(he="they", him="them", his="their", hes="they're", himself="themself", is_="are", has="have", was="were", title="Friend"),
}
NUMS = ["no", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten"]
NUMW = ["no one", "one person", "two people", "three people", "four people", "five people", "six people", "seven people", "eight people",
        "nine people", "ten people"]
GAINW = ["no one", "one new person", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten"]
KEY_RE = re.compile(r"\{(\w+)\}")
PERSON_RE = re.compile(r"^([ABCD])(?:_(\w+))?$")


# ------------------------------------------------------------------ text
def _numword(n, words):
    return words[n] if 0 <= n < len(words) else ("%d people" % n if words is NUMW else str(n))


def line_keys(tpl):
    return set(KEY_RE.findall(tpl))


def render(tpl, people, vars_):
    """Fill a template. people = {"A": person, ...}; {A} = name, {A_he} / {A_He} / {A_him} / {A_his} / {A_hes} / {A_himself} / {A_is} / {A_has} /
    {A_was} / {A_title} = pronouns and verbs by gender; vars_ = the plain keys ({day} {place} {enemy} {inf} {ill} ...)."""
    def sub(m):
        key = m.group(1)
        pm = PERSON_RE.match(key)
        if pm:
            p = people[pm.group(1)]
            if not pm.group(2):
                return p["n"]
            w = pm.group(2)
            r = PRON[p["g"]][w.lower()]
            return r[:1].upper() + r[1:] if w[:1].isupper() else r
        val = str(vars_[key])
        before = tpl[:m.start()].rstrip()
        if val[:1].islower() and (not before or before[-1] in ".!?\"'"):      # a variable at the start of a sentence
            val = val[:1].upper() + val[1:]
        return val
    return KEY_RE.sub(sub, tpl)


def short_text(text, limit=WIDGET_MAX):
    """The in-game widget shows one line: whole sentences up to `limit` chars (the first sentence cut at a clause when it is longer)."""
    if len(text) <= limit:
        return text
    parts = re.findall(r"[^.!?]*[.!?]+(?:\s+|$)|[^.!?]+$", text)
    out = ""
    for p in parts:
        if len(out) + len(p.rstrip()) <= limit:
            out += p
        else:
            break
    out = out.strip()
    if out:
        return out
    cut = text[:limit - 1]
    k = max(cut.rfind(","), cut.rfind(";"), cut.rfind(" "))
    return (cut[:k] if k > 40 else cut).rstrip(" ,;") + "…"


def line_id(text):
    return "%08x" % (zlib.crc32(text.encode("utf-8")) & 0xFFFFFFFF)


# ------------------------------------------------------------------ people
def _fkey(faction):
    return "S" if faction == clan.SERAPHITES else "W"


def _name_pool(fk):
    pool = []
    for n in D.FIRST_2013:
        g = "f" if n in D.FEMALE_2013 else "m"
        pool.append((n, g, 1 if fk == "W" else 0.3))
    for n, g in (D.EXTRA_WLF if fk == "W" else D.EXTRA_SERA):
        pool.append((n, g, 1 if fk == "W" else 1.6))
    for n, g in (D.EXTRA_SERA if fk == "W" else D.EXTRA_WLF):
        pool.append((n, g, 0.1))
    return pool


_POOLS = {}


def new_person(rng, st, role=None, state="h", join_day=0):
    fk = _fkey(st["fac"])
    pool = _POOLS.get(fk) or _POOLS.setdefault(fk, _name_pool(fk))
    taken = {p["n"] for p in st["people"]} | {d["n"] for d in st["dead"]}
    for _ in range(40):
        nm, g, _w = rng.choices(pool, weights=[w for _, _, w in pool])[0]
        if nm not in taken:
            break
    else:
        nm = nm + " " + rng.choice(D.LAST_2013)
    if nm.split()[0] in D.NEUTRAL_2013 and rng.random() < 0.3:
        g = "n"
    roles = list(D.ROLES)
    if role is None:
        role = rng.choices(roles, weights=[D.ROLES[r][2] for r in roles])[0]
    st["pid"] += 1
    return {"i": st["pid"], "n": nm, "l": rng.choice(D.LAST_2013), "g": g, "r": role, "s": state, "il": "", "is": 0, "id": 0, "k": 0, "jd": join_day,
            "gr": 0, "gl": 0}


def _link_kin(rng, st, p):
    if rng.random() < 0.35:
        free = [q for q in st["people"] if not q["k"] and q["i"] != p["i"]]
        if free:
            q = rng.choice(free)
            p["k"], q["k"] = q["i"], p["i"]


def _alive(st, pred=lambda p: True):
    return [p for p in st["people"] if pred(p)]


def _by_id(st, i):
    for p in st["people"]:
        if p["i"] == i:
            return p
    return None


def mood_of(st, p):
    if p["s"] == "s":
        return "ill"
    if p["s"] == "u":
        return "hungry"
    if p["gr"] > st["day"]:
        return "grieving"
    m = st["morale"]
    return "cheerful" if m >= 70 else "steady" if m >= 50 else "tired" if m >= 30 else "hollow"


def morale_label(m):
    return "hopeful" if m >= 70 else "steady" if m >= 50 else "strained" if m >= 30 else "grim"


# ------------------------------------------------------------------ state
def new_state(tid, faction, run=1):
    return {"v": STATE_V, "fac": faction, "run": run, "seed": "%s:%d" % (tid, run), "day": 0, "morale": 55, "ds": 0, "ss": 0, "pid": 0, "n": 0,
            "people": [], "dead": [], "used": {}, "atk": -99, "warned": -1, "suic": -99, "boot": 0}


def _populate(rng, st, h, u, s, day):
    for state, n in (("h", h), ("u", u), ("s", s)):
        for _ in range(n):
            p = new_person(rng, st, state=state, join_day=day)
            if state == "s":
                p["il"] = _pick_illness(rng, st, True, p)
                p["id"] = day
            _link_kin(rng, st, p)
            st["people"].append(p)


def _pick_illness(rng, st, hunger, p=None):
    after_fight = st["day"] - st["atk"] <= 3
    keys = list(D.ILLNESS)
    if p is not None and KD.is_kid(p):                  # a kid's wound is never a fight wound, and a kid is never sent where the spores are
        keys = [k for k in keys if k not in ("infected_wound", "spores")]
    w = [D.ILLNESS[k][4 if after_fight else 3] for k in keys]
    if "spores" in keys and has_mask(st):               # a mask on the shelf: the cellars are still bad, but not every run ends in a cough
        w[keys.index("spores")] = max(1, w[keys.index("spores")] // 4)
    return rng.choices(keys, weights=w)[0]


def has_mask(st):
    """The clan found a gas mask in one of its last raids (tools/clan_loot.py finds; stored in the chronicle log)."""
    for e in ((st.get("ch") or {}).get("log") or [])[-12:]:
        if any(f.get("k") == "gasmask" for f in (e.get("finds") or [])):
            return True
    return False


# ------------------------------------------------------------------ line picking
_PL_BY_EN = {}
_KID_PLAIN = {"h": ("{A} is healthy.", "t:h"), "u": ("{A} is starving.", "t:u"), "s": ("{A} is sick.", "t:s")}     # what a kid's ticker says when nothing else fits


def _pl_twin(t):
    """The Polish twin of an English template of the registry ('' when it has none), for the kid check."""
    if not _PL_BY_EN:
        for _pool, _sc, e, p in PLN.ROWS:
            _PL_BY_EN.setdefault(e, p)
    return _PL_BY_EN.get(t, "")


def _companion_ok(st, p, t):
    """True when template t (English) can be filled with companions for subject p: a B / C needs that many healthy others, and a combat line needs them grown (kids are no fighters)."""
    letters = PLN.tpl_letters(t)
    if "D" in letters and st["dead"] and st["dead"][-1].get("r") == "kid" and (KD.combat_text(t, "en") or KD.combat_text(_pl_twin(t), "pl")):
        return False                                    # (the latest dead was a kid: no fight line names them)
    need = len(letters & {"B", "C"})
    if not need:
        return True
    others = [q for q in st["people"] if q["i"] != p["i"] and q["s"] == "h"]
    if KD.combat_text(t, "en") or KD.combat_text(_pl_twin(t), "pl"):
        others = [q for q in others if KD.can_fight(q)]
    return len(others) >= need


def pick_line(rng, st, kind, fk, people, vars_, pool=None):
    """One unused line of `kind` for faction key fk whose placeholders can all be filled; the used list of the kind resets when it is
    exhausted (no repeats until the pool is spent). Returns the rendered text or None."""
    r = _pick(rng, st, kind, fk, people, vars_, pool)
    return r[0] if r else None


def _pick(rng, st, kind, fk, people, vars_, pool=None):
    """pick_line's work: (rendered text, the English template chosen) or None."""
    lines = pool if pool is not None else LINES.get(kind, [])
    avail = set(people) | set(vars_)
    for letter in list(people):
        avail |= {letter + "_" + k for k in ("he", "He", "him", "his", "hes", "himself", "is", "has", "was", "title")}
    cand = []
    for scope, t in lines:
        if scope not in ("*", fk):
            continue
        if line_keys(t) <= avail and KD.kid_safe(t, people, _pl_twin(t)):
            cand.append(t)
    if cand and KD.any_kid(people):                              # the filled-in line (a keepsake, a place, an item) must not make a kid a fighter either
        cand = [t for t in cand if KD.kid_text_ok(render(t, people, vars_), people)]
    if not cand:
        return None
    used = st["used"].setdefault(kind, [])
    fresh = [t for t in cand if line_id(t) not in used]
    if not fresh:
        keep = used[-1:] if used else []
        used[:] = [x for x in keep]
        fresh = [t for t in cand if line_id(t) not in used] or cand
    t = rng.choice(fresh)
    used.append(line_id(t))
    del used[:-400]
    return render(t, people, vars_), t


class Writer:
    """Collects one clan day's messages."""

    def __init__(self, rng, st, day, week):
        self.rng, self.st, self.day, self.week = rng, st, day, week
        self.fk = _fkey(st["fac"])
        self.out = []

    def base_vars(self, **kw):
        F = D.FACTION[self.fk]
        v = {"day": self.day, "week": self.week, "place": self.rng.choice(F["places"]), "enemy": F["enemy"], "enemies": F["enemies"],
             "leader": F["leader"], "faction": F["plural"], "inf": self.rng.choice(D.INFECTED)}
        v["infs"] = v["inf"] + "s"
        v.update(kw)
        return v

    def add(self, kind, people, mood=None, pool=None, ill_of=None, pname=None, cause=None, **kw):
        """kw = the symbolic variables of the line: ill = illness key / "none", n / lost / gain = integers, ago = the English key ("yesterday" ...).
        They are kept as keys in the stored message (lid + params) so the line can be rendered in any language later.
        The narrator's voice follows the clan's size (clan_story_solo.py): 1 alive = the survivor writes in first person singular (kinds without a
        solo pool are not written), 2 alive = "we" but no crowd words. `cause` = how the dead person of a grief message died."""
        size = len(self.st["people"])
        used_key = kind
        duo_pool = None
        if size == 1 and kind != "clan_dead":
            sp = SO.solo_pool(kind, cause)
            if not sp:
                return False
            surv = self.st["people"][0]
            np_ = {"A": surv}
            if kind.startswith("death_"):
                np_["D"] = people["A"]                  # A is the one who died; the narrator is the survivor
            elif "D" in people:
                np_["D"] = people["D"]
            people, pool, used_key = np_, sp, "solo:" + kind
            ill_of = "A" if ill_of else None
        elif size == 2 and kind != "clan_dead":
            base = pool if pool is not None else LINES.get(kind, [])
            pool = [(sc, t) for sc, t in base if not SO.CROWD_RE.search(t)] or base
            duo = SO.DUO_EN.get(kind)
            a = people.get("A")
            if duo and a is not None and a.get("i") is not None:
                others = [q for q in self.st["people"] if q["i"] != a["i"]]
                if others:
                    people = dict(people, B=others[0])
                    if self.rng.random() < 0.6:
                        duo_pool = duo
        v = self.base_vars()
        sym = {"f": self.fk, "day": self.day, "week": self.week, "place": v["place"], "inf": v["inf"]}
        p = people.get(ill_of) if ill_of else None
        ill = kw.pop("ill", None)
        if ill is None and p and p.get("il"):
            ill = p["il"]
        if ill is not None:
            sym["ill"] = ill
        for k in ("n", "lost", "gain"):
            if k in kw:
                sym[k] = int(kw.pop(k))
        if "ago" in kw:
            sym["ago"] = kw.pop("ago")
        v.update(expand_en(sym))
        got = _pick(self.rng, self.st, "duo:" + kind, self.fk, people, v, duo_pool) if duo_pool else None
        if not got:
            got = _pick(self.rng, self.st, used_key, self.fk, people, v, pool)
        if not got:
            return False
        text, tpl = got
        names = [people[k]["n"] for k in "ABCD" if k in people and re.search(r"(?<!\w)" + re.escape(people[k]["n"]) + r"(?!\w)", text)]
        self.out.append({"kind": kind, "mood": mood or KIND_MOOD.get(kind, "calm"), "text": text, "names": names,
                         "lid": PLN.lid(SO.TPL_POOL.get(tpl) or pname or kind, tpl), "params": _params(people, sym)})
        return True


def expand_en(sym):
    """Symbolic variables -> the English words the templates use (the Polish twin is clan_story_pl.expand)."""
    F = D.FACTION[sym.get("f", "W")]
    v = {"day": sym.get("day", 0), "week": sym.get("week", 1), "enemy": F["enemy"], "enemies": F["enemies"], "leader": F["leader"], "faction": F["plural"]}
    if "place" in sym:
        v["place"] = sym["place"]
    if "inf" in sym:
        v["inf"], v["infs"] = sym["inf"], sym["inf"] + "s"
    if "ill" in sym:
        if sym["ill"] in D.ILLNESS:
            nm, an, cure, _a, _b = D.ILLNESS[sym["ill"]]
            v.update(ill=nm, ill_a=an, cure=cure)
        else:
            v.update(ill="the sickness", ill_a="the sickness", cure="medicine")
    if "n" in sym:
        v["n"] = _numword(sym["n"], NUMS)
    if "lost" in sym:
        v["lost"] = _numword(sym["lost"], NUMW)
    if "gain" in sym:
        v["gain"] = _numword(sym["gain"], GAINW)
    if "ago" in sym:
        v["ago"] = sym["ago"]
    return v


def _params(people, sym):
    return {"p": {k: [people[k]["n"], people[k]["g"]] for k in "ABCD" if k in people}, "s": sym}


def render_msg(lid, params, lang="en"):
    """A stored message (lid + params) in a language ("en" | "pl"); None when the template is unknown (an older / newer line set)."""
    if lid and lid.startswith("al/"):                       # a clan A-Life row (tools/clan_alife.py)
        import clan_alife
        return clan_alife.render_msg(lid, params, lang)
    if lid and lid.startswith("cn/"):                       # the recap row of a migrated clan (tools/clan_continuity.py)
        import clan_continuity
        return clan_continuity.render_msg(lid, params, lang)
    if lid and lid.startswith("arc/"):                      # a story arc step (tools/clan_arcs.py)
        import clan_arcs
        return clan_arcs.render_msg(lid, params, lang)
    if lid and lid.startswith("pk/"):                       # a clan supply perk was used (tools/clan_perks.py)
        import clan_perks
        return clan_perks.render_msg(lid, params, lang)
    if lid and lid.startswith("sg/"):                       # a clan saga row (tools/clan_saga.py, English only)
        import clan_saga
        return clan_saga.render_msg(lid, params, lang)
    if lid and lid.startswith("ch/"):                       # a clan chronicle row (tools/clan_chronicle.py)
        import clan_chronicle
        return clan_chronicle.render_msg(lid, params, lang)
    ent = PLN.REG.get(lid)
    if not ent or not isinstance(params, dict):
        return None
    _scope, en_tpl, pl_tpl = ent
    people = {k: {"n": str(v[0]), "g": v[1] if v[1] in PRON else "n"} for k, v in params.get("p", {}).items()}
    sym = params.get("s", {})
    if PLN.norm_lang(lang) == "pl":
        return PLN.render(pl_tpl, people, PLN.expand(sym))
    return render(en_tpl, people, expand_en(sym))


# ------------------------------------------------------------------ the day
def _kill_pick(rng, st, fight=False):
    """clan.Crowd.kill: a sick member, else a hungry one, else anybody. When the clan is broken, the grieving and the guilty go first.
    fight=True (a death of the attack): never a kid (kids are no fighters), unless the clan has nobody else."""
    people = st["people"]
    if fight:
        people = [p for p in people if KD.can_fight(p)] or people
    doom = (st.get("ch") or {}).get("doom") or {}
    marked = [p for p in people if str(p["i"]) in doom and KD.can_fight(p)]          # a story arc marked this person (tools/clan_arcs.py): the clan rules kill someone today anyway
    if marked:
        return marked[0]
    for state in ("s", "u", "h"):
        group = [p for p in people if p["s"] == state]
        if group:
            if st["morale"] <= 25:
                weak = [p for p in group if p["gl"] or p["gr"] > st["day"]]
                if weak and rng.random() < 0.6:
                    return rng.choice(weak)
            return rng.choice(group)
    return None


def finish_member(st, p, day, cause, helper=None):
    """A member leaves the roster for good outside the clan's own death rules (a story arc's end: tools/clan_arcs.py "spore"): the dead record, the grief of the
    kin and of the one who had to do it, the guilt of the helper."""
    _remove(st, p, day, cause)
    k = _by_id(st, p["k"]) if p["k"] else None
    for m in {id(x): x for x in (k, helper) if x}.values():
        m["gr"] = max(m["gr"], day + 6)
    if cause in ("mercy", "bite_kin", "turned") and helper:
        helper["gl"] = day + 12


def spare_sick(rng, st, day):
    """A quiet newcomer with a flu takes the place in the roster of a spore carrier who left (the game's numbers - the clan's size and its sick count - do not know
    about the story's end, so the roster keeps them)."""
    q = new_person(rng, st, state="s", join_day=0)
    q["il"], q["id"] = "flu", day
    st["people"].append(q)
    return q


def _remove(st, p, day, cause):
    st["people"].remove(p)
    k = _by_id(st, p["k"]) if p["k"] else None
    if k:
        k["k"] = 0
    st["dead"].append({"i": p["i"], "n": p["n"], "g": p["g"], "r": p["r"], "d": day, "c": cause, "il": p["il"], "k": k["i"] if k else 0})
    del st["dead"][:-30]


def _mourner(rng, st, dead_p):
    k = _by_id(st, dead_p["k"]) if dead_p["k"] else None
    if k:
        return k
    others = [q for q in st["people"] if q is not dead_p]
    return rng.choice(others) if others else None


def _apply_morale(st, r, size_after, sick_after):
    sup, need = int(r.get("supplies", 0)), int(r.get("needed", 0))
    d = sup - need
    m = st["morale"]
    if d >= 0:
        st["ss"] += 1
        st["ds"] = 0
        m += 2 + min(6, d // 3) + (3 if st["ss"] >= 3 else 0)
    else:
        st["ds"] += 1
        st["ss"] = 0
        m += -3 + max(-8, d // 2) - (2 if st["ds"] >= 2 else 0)
    m -= min(15, 5 * int(r.get("died", 0)))
    m += min(9, 3 * int(r.get("gained", 0)) + 3 * int(r.get("evg", 0)))
    m += min(6, 2 * int(r.get("healed", 0)))
    if size_after:
        m -= int(round(10 * sick_after / size_after))
    if r.get("evk") == clan.EV_ATTACK:
        m += {0: -8, 1: -4, 2: 1, 3: 6}.get(int(r.get("evt", 0)), 0)
    elif r.get("evk") == clan.EV_GROWTH and int(r.get("evt", 0)) >= 1:
        m += 4
    st["morale"] = max(0, min(100, m))
    return d


def story_day(st, rng, newc, r):
    """Advance the roster to the clan state `newc` (counts after the day) using the day's result `r`, and write the day's messages.
    Returns the list of message dicts (kind, mood, text, names)."""
    day = int(newc["day"])
    week = clan.week_day(day)[0]
    fk = _fkey(st["fac"])
    H, U, S = int(newc["healthy"]), int(newc["hungry"]), int(newc["sick"])
    size = H + U + S
    w = Writer(rng, st, day, week)
    died, evl = int(r.get("died", 0)), int(r.get("evl", 0))
    evk, evt = int(r.get("evk", 0)), int(r.get("evt", 0))
    gained = int(r.get("gained", 0)) + int(r.get("evg", 0))
    st["day"] = day
    prev_sick = {p["i"] for p in st["people"] if p["s"] == "s"}
    deficit_day = int(r.get("supplies", 0)) < int(r.get("needed", 0))
    surplus_day = not deficit_day
    if evk == clan.EV_ATTACK:
        st["atk"] = day
    atk_lag = day - st["atk"]

    _apply_morale(st, r, size, S)
    # --- deaths (clan.resolve_day: the deficit's deaths first, then the attack's)
    deaths = []                                              # (person, cause, helper)
    for k in range(died):
        p = _kill_pick(rng, st, fight=k >= died - evl)
        if not p:
            break
        cause = "attack" if k >= died - evl and KD.can_fight(p) else None
        helper = None
        if cause is None:
            recent = sum(1 for d in st["dead"] if day - d["d"] <= 6) + len(deaths)
            gate = st["morale"] <= 22 and (st["ds"] >= 3 or recent >= 2) and day - st["suic"] >= 5
            mourner = _mourner(rng, st, p) if len(st["people"]) > 1 else None   # (never the victim itself)
            hint = ((st.get("ch") or {}).get("doom") or {}).get(str(p["i"]))
            if hint:
                cause, helper = hint, mourner
                st["ch"]["doom"].pop(str(p["i"]), None)
            elif p["s"] == "s" and p["il"] == "spores":
                cause, helper = "turned", mourner                  # canon: the spores never let go - the person turns, or the clan chooses the end (mercy, a walk into the dark)
            elif p["s"] == "s":
                ill = p["il"] or "fever"
                if 1 <= atk_lag <= 3 and rng.random() < 0.5:
                    kin = _by_id(st, p["k"]) if p["k"] else None
                    cause, helper = ("bite_kin", kin) if kin and rng.random() < 0.7 else ("bite", mourner)
                elif gate and rng.random() < 0.3:
                    cause, helper = "suicide", mourner
                    st["suic"] = day
                elif p["is"] >= 2 and rng.random() < 0.4 or (ill == "spores" and rng.random() < 0.3):
                    cause, helper = "mercy", mourner
                elif st["morale"] <= 30 and rng.random() < 0.18:
                    cause, helper = "walkout", mourner
                else:
                    cause, helper = "illness", mourner
            elif p["s"] == "u":
                if gate and rng.random() < 0.25:
                    cause, helper = "suicide", mourner
                    st["suic"] = day
                elif st["morale"] <= 30 and rng.random() < 0.2:
                    cause, helper = "walkout", mourner
                else:
                    cause, helper = "starved", mourner
            else:
                if gate and rng.random() < 0.2:
                    cause, helper = "suicide", mourner
                    st["suic"] = day
                else:
                    cause, helper = "lost", mourner
        if cause in ("mercy", "bite", "bite_kin", "turned") and KD.is_kid(helper):               # whoever ends a life or carries the shame is grown
            alt = [q for q in st["people"] if q is not p and KD.can_fight(q)]
            helper = rng.choice(alt) if alt else None
            if helper is None:
                cause = "illness"
        if KD.is_kid(p) and cause not in ("illness", "starved", "mercy"):       # a kid dies of sickness or hunger, never of the fight, the road, the bite or by its own hand
            cause = "starved" if p["s"] == "u" else "illness"
            helper = helper or (_mourner(rng, st, p) if len(st["people"]) > 1 else None)
        deaths.append((p, cause, helper))
        _remove(st, p, day, cause)
    for p, cause, helper in deaths:                          # grief / guilt flags
        k = _by_id(st, p["k"]) if p["k"] else None
        for m in {id(x): x for x in (k, helper) if x}.values():
            m["gr"] = max(m["gr"], day + 6)
        if cause in ("mercy", "bite_kin", "turned") and helper:
            helper["gl"] = day + 12
    for p in st["people"]:
        if p["gl"] and p["gl"] < day:
            p["gl"] = 0

    # --- joins
    joined = []
    for _ in range(gained):
        p = new_person(rng, st, state="h", join_day=day)
        _link_kin(rng, st, p)
        st["people"].append(p)
        joined.append(p)

    # --- hunger / sickness / healing, reconciled to the real counts
    new_sick, recovered, new_hungry = [], [], []
    for p in st["people"]:
        if p["s"] == "s" and p["i"] in prev_sick and deficit_day:
            p["is"] = min(3, p["is"] + 1)
    def count(state): return sum(1 for p in st["people"] if p["s"] == state)
    for _ in range(max(0, count("h") + count("u") + count("s") - size)):     # roster longer than the clan (a bootstrap mismatch): drop silently
        v = rng.choice(st["people"])
        st["people"].remove(v)
    while count("h") + count("u") + count("s") < size:                       # roster shorter: silent filler
        st["people"].append(new_person(rng, st, state="h", join_day=day))
    while count("s") > S:
        sick_all = [p for p in st["people"] if p["s"] == "s"]
        cures = [p for p in sick_all if p["il"] != "spores"]
        if not cures:                                        # only spore carriers are left over: nobody recovers from the spores - the clan's last day with one of them
            v = rng.choice(sick_all)
            helper = _mourner(rng, st, v) if len(st["people"]) > 1 else None
            helper = helper if helper is not None and not KD.is_kid(helper) else next((q for q in st["people"] if q is not v and KD.can_fight(q)), None)
            finish_member(st, v, day, "turned", helper)
            st["people"].append(new_person(rng, st, state="h", join_day=day))     # (a quiet newcomer keeps the roster at the clan's size)
            continue
        v = rng.choice(cures)
        v.update(s="h", il="", **{"is": 0})
        recovered.append(v)
    while count("s") < S:
        pool = [p for p in st["people"] if p["s"] in ("h", "u")]
        v = rng.choice(pool)
        v["s"], v["il"], v["is"], v["id"] = "s", _pick_illness(rng, st, deficit_day, v), 0, day
        new_sick.append(v)
    while count("u") > U:
        v = rng.choice([p for p in st["people"] if p["s"] == "u"])
        v["s"] = "h"
    while count("u") < U:
        v = rng.choice([p for p in st["people"] if p["s"] == "h"])
        v["s"] = "u"
        new_hungry.append(v)
    busy = {int(i) for a in ((st.get("ch") or {}).get("arcs") or []) for i in a["c"].values()}
    for v in [p for p in st["people"] if p["s"] == "s" and p["il"] == "spores" and day - int(p.get("id") or day) >= 9 and p["i"] not in busy]:
        helper = _mourner(rng, st, v) if len(st["people"]) > 1 else None             # the spores do not wait for ever: nobody is sick with them for more than a week and a half
        helper = helper if helper is not None and not KD.is_kid(helper) else next((q for q in st["people"] if q is not v and KD.can_fight(q)), None)
        finish_member(st, v, day, "turned", helper)
        spare_sick(rng, st, day)
    sick_now = [p for p in st["people"] if p["s"] == "s"]

    morale = st["morale"]

    # --- messages, in the order of importance
    status = int(newc["status"])
    people_now = st["people"]
    def two(exclude=(), fight=False):
        pool = [p for p in people_now if p["i"] not in {e["i"] for e in exclude}]
        if fight:                                           # the attack, the warning, the siege: grown people only
            pool = [p for p in pool if KD.can_fight(p)] or pool
        return rng.sample(pool, min(2, len(pool)))
    if deaths:
        ordered = deaths[:2]
        attack_deaths = [d for d in deaths if d[1] == "attack"]
        other = [d for d in deaths if d[1] != "attack"]
        horde = evk == clan.EV_ATTACK and int(r.get("evn", 0)) == clan.AN_HORDE      # the attack was a horde of infected
        if len(attack_deaths) >= 2:
            ppl = {"A": attack_deaths[0][0], "B": attack_deaths[1][0]}
            if not (horde and w.add("death_horde_many", ppl, n=len(attack_deaths), lost=len(attack_deaths))):
                w.add("death_attack_many", ppl, n=len(attack_deaths), lost=len(attack_deaths))
            ordered = other[:1]
        elif len(deaths) >= 4 and not attack_deaths:
            ppl = {"A": deaths[0][0], "B": deaths[1][0]}
            w.add("loss_many", ppl, n=len(deaths), lost=len(deaths))
            ordered = []
        for p, cause, helper in ordered:
            kind = {"attack": "death_attack", "illness": "death_illness", "mercy": "death_mercy", "starved": "death_starved", "lost": "death_lost",
                    "walkout": "death_walkout", "suicide": "death_suicide", "bite": "death_bite", "bite_kin": "death_bite_kin", "turned": "death_turned"}[cause]
            if kind == "death_attack" and horde:
                kind = "death_horde"
            ppl = {"A": p}
            if cause in ("attack", "bite", "bite_kin", "turned") and KD.is_kid(helper):
                helper = None
            if helper:
                ppl["B"] = helper
            elif people_now:
                ppl["B"] = rng.choice(([q for q in people_now if KD.can_fight(q)] if cause in ("attack", "bite", "bite_kin", "turned") else []) or people_now)
            extra = {}
            if cause in ("bite", "bite_kin"):
                extra["ago"] = "yesterday" if atk_lag == 1 else "the other night" if atk_lag == 2 else "a few days back"
            v = dict(extra)
            v["ill"] = p["il"] if p["il"] else "none"
            if kind == "death_bite_kin" and "B" not in ppl:
                kind = "death_bite"
            if not w.add(kind, ppl, **v):
                if kind == "death_horde":                       # (a lone survivor has no horde voice: the attack's own death line)
                    w.add("death_attack", ppl, **v)
                elif kind in ("death_bite_kin", "death_mercy", "death_walkout", "death_suicide", "death_turned"):
                    w.add("death_illness", ppl, **v)
    # event outcome
    if evk == clan.EV_ATTACK:
        ppl = {k: v for k, v in zip("AB", two(fight=True))}
        lost = evl
        hz = "_h" if int(r.get("evn", 0)) == clan.AN_HORDE else ""             # (a horde: its own lines; a lone survivor has no voice for it and writes nothing)
        if evt >= 3:
            w.add("event_hold" + hz, ppl, lost=lost)
        elif evt == 2:
            w.add("event_heavy" + hz, ppl, lost=lost)
        elif status != clan.DEAD:
            w.add("event_massacre" + hz, ppl, lost=lost)
    elif evk == clan.EV_GROWTH:
        if int(r.get("evg", 0)) > 0 and joined:
            ppl = {"A": joined[0]}
            others = [p for p in people_now if p not in joined]
            if others:
                ppl["B"] = rng.choice(others)
            w.add("event_growth", ppl, gain=int(r.get("evg", 0)))
            joined = joined[int(r.get("evg", 0)):] if len(joined) > int(r.get("evg", 0)) else []
        else:
            w.add("event_nojoin", {k: v for k, v in zip("A", two())}, mood="grim")
    if status == clan.DEAD:
        last = deaths[-1][0] if deaths else None
        w.add("clan_dead", {"A": last} if last else {"A": {"n": "Someone", "g": "n"}}, mood="grim")
    if status == clan.WON:
        w.add("clan_won", {k: v for k, v in zip("AB", two())})
    # next event warning
    if status == clan.ALIVE and clan.event_today(day)[0] == clan.EV_ATTACK and st["warned"] != day:
        st["warned"] = day
        w.add("event_warn_h" if clan.event_today(day)[1] == clan.AN_HORDE else "event_warn", {k: v for k, v in zip("A", two(fight=True))})
    if joined and status == clan.ALIVE and len(w.out) < DAY_MAX_MSGS:
        ppl = {"A": joined[0]}
        others = [p for p in people_now if p not in joined]
        if others:
            ppl["B"] = rng.choice(others)
        w.add("join", ppl)
    if status == clan.ALIVE:
        # the darkest consequences first, gated by the state; then the day's condition
        recent_dead = [d for d in st["dead"] if day - d["d"] <= 8]
        for p in new_sick[:2]:
            if len(w.out) >= DAY_MAX_MSGS:
                break
            ppl = {"A": p}
            medics = [q for q in people_now if q["r"] == "medic" and q is not p and q["s"] != "s"]
            others = medics or [q for q in people_now if q is not p]
            if others:
                ppl["B"] = rng.choice(others)
            pool = LINES_SICK[p["il"]]
            w.add("sick", ppl, pool=pool, pname="onset:" + p["il"], ill=p["il"])
        worse = [p for p in sick_now if p["i"] in prev_sick and p["is"] >= 1 and deficit_day]
        if worse and len(w.out) < DAY_MAX_MSGS and rng.random() < 0.7:
            p = max(worse, key=lambda q: q["is"])
            others = [q for q in people_now if q is not p]
            if p["il"] == "spores":
                w.add("worse", {"A": p, **({"B": rng.choice(others)} if others else {})}, pool=SPR.LINES["spore_worse"], pname="spore_worse", ill_of="A")
            else:
                w.add("worse", {"A": p, **({"B": rng.choice(others)} if others else {})}, ill_of="A")
        elif sick_now and deficit_day and morale <= 55 and len(w.out) < DAY_MAX_MSGS and rng.random() < 0.6:
            p = rng.choice(sick_now)
            others = [q for q in people_now if q is not p]
            if p["il"] == "spores":
                w.add("medicine", {"A": p, **({"B": rng.choice(others)} if others else {})}, pool=SPR.LINES["spore_hold"], pname="spore_hold", ill_of="A")
            else:
                w.add("medicine", {"A": p, **({"B": rng.choice(others)} if others else {})}, ill_of="A")
        if recovered and len(w.out) < DAY_MAX_MSGS:
            p = recovered[0]
            others = [q for q in people_now if q is not p]
            ppl = {"A": p, **({"B": rng.choice(others)} if others else {})}
            w.add("recovery", ppl, ill="none")
        # grief and guilt of the days just lived through
        mourners = [p for p in people_now if p["gr"] > day and p["s"] != "s"]
        if recent_dead and mourners and len(w.out) < DAY_MAX_MSGS and (deaths or rng.random() < 0.3):
            p = None
            for dd in reversed(recent_dead):
                p = _by_id(st, dd["k"]) if dd["k"] else None
                if p:
                    break
            p = p or rng.choice(mourners)
            dd = next((d for d in reversed(recent_dead) if d["k"] == p["i"]), recent_dead[-1])
            ppl = {"A": p, "D": {"n": dd["n"], "g": dd["g"], "r": dd.get("r", "")}}
            kind = "grief_mercy" if dd["c"] in ("mercy", "bite_kin") and rng.random() < 0.8 else "grief"
            if dd["c"] == "turned" and len(people_now) >= 3 and rng.random() < 0.85:       # the spores took {D}: its own grief pool
                kind = "grief_turned"
            w.add(kind, ppl, cause=dd["c"])
        guilty = [p for p in people_now if p["gl"] and recent_dead]
        if guilty and len(w.out) < DAY_MAX_MSGS and rng.random() < 0.5 and not deaths:
            dd = recent_dead[-1]
            others = [q for q in people_now if q is not guilty[0]]
            ppl = {"A": guilty[0], "D": {"n": dd["n"], "g": dd["g"], "r": dd.get("r", "")}}
            if others:
                ppl["B"] = rng.choice(others)
            w.add("guilt", ppl)
        if len(w.out) < DAY_MAX_MSGS:
            hungry_now = [p for p in people_now if p["s"] == "u"]
            kind = None
            if deficit_day and U + S >= max(2, size // 3) and rng.random() < 0.8:
                kind = "starving" if U >= max(2, size // 3) else "hunger"
            elif deficit_day and rng.random() < 0.7:
                kind = "hunger"
            elif morale <= 25 and rng.random() < 0.8:
                kind = "despair"
            elif surplus_day and recent_dead and morale >= 45 and rng.random() < 0.8:
                kind = "hope_after"
            elif surplus_day and int(r.get("supplies", 0)) - int(r.get("needed", 0)) >= 6 and rng.random() < 0.6:
                kind = "plenty"
            elif surplus_day and morale >= 60 and rng.random() < 0.75:
                kind = "hope"
            elif rng.random() < 0.5:
                kind = "calm"
            if kind:
                ppl = {}
                base = hungry_now if kind in ("hunger", "starving") and hungry_now else people_now
                if base:
                    a = rng.choice(base)
                    ppl["A"] = a
                    rest = [q for q in people_now if q is not a]
                    if rest:
                        ppl["B"] = rng.choice(rest)
                if kind == "hope_after":
                    dd = recent_dead[-1]
                    ppl["D"] = {"n": dd["n"], "g": dd["g"], "r": dd.get("r", "")}
                if ppl:
                    w.add(kind, ppl)
        # the 2013 ticker: one small line about one person's real state (one survivor: the diary voice, two: no crowd lines)
        if people_now and len(w.out) < DAY_MAX_MSGS - 1 and rng.random() < 0.75:
            p = rng.choice(people_now)
            solo = len(people_now) == 1
            used = st["used"].setdefault(("ticker_solo_" if solo else "ticker_") + p["s"], [])
            if solo:
                pool_t = [t for _sc, t in SO.solo_ticker(p["s"])]
                fresh = [t for t in pool_t if line_id(t) not in used] or pool_t
                t = rng.choice(fresh)
                used.append(line_id(t))
                del used[:-200]
                w.out.append({"kind": "ticker", "mood": "neutral", "text": render(t, {"A": p}, {}), "names": [], "lid": PLN.lid(SO.TPL_POOL[t], t),
                              "params": _params({"A": p}, {"f": fk, "day": day, "week": week})})
            else:
                # one line about one member's real state (rare joke for sick ones); a healthy member gets a rich line (clan_story_good_rich.py)
                # with a living companion, the day, the latest dead - never a bare "X is healthy."
                t, tpool, ppl = ticker_for(rng, st, p, set(used))
                used.append(line_id(t))
                del used[:-200]
                sym = dict(_sym(rng, st), day=day, week=week)
                w.out.append({"kind": "ticker", "mood": "neutral", "text": render(t, ppl, expand_en(sym)), "names": [ppl[k]["n"] for k in "ABC" if k in ppl],
                              "lid": PLN.lid(tpool, t), "params": _params(ppl, sym)})
    return w.out


LINES_SICK = LD.ONSET     # per-illness onset pools


# ------------------------------------------------------------------ database
SCHEMA = ("CREATE TABLE IF NOT EXISTS clan_story(token_id TEXT PRIMARY KEY, state TEXT, updated REAL)",
          "CREATE TABLE IF NOT EXISTS clan_feed(token_id TEXT, id INTEGER, ts REAL, day INTEGER, week INTEGER, kind TEXT, mood TEXT, "
          "faction INTEGER, text TEXT, names TEXT, lid TEXT, params TEXT, PRIMARY KEY(token_id, id))")
# additive migration of a clan_feed table created before the language-neutral columns existed: new columns only, no row is rewritten
NEW_COLUMNS = (("lid", "TEXT"), ("params", "TEXT"))


def ensure(c):
    for s in SCHEMA:
        c.execute(s)
    have = {r[1] for r in c.execute("PRAGMA table_info(clan_feed)")}
    for col, typ in NEW_COLUMNS:
        if col not in have:
            c.execute("ALTER TABLE clan_feed ADD COLUMN %s %s" % (col, typ))


def _load(c, tid):
    try:
        row = c.execute("SELECT state FROM clan_story WHERE token_id=?", (tid,)).fetchone()
    except Exception:
        return None
    if not row:
        return None
    try:
        st = json.loads(row[0])
        return st if isinstance(st, dict) and st.get("v") == STATE_V else None
    except ValueError:
        return None


def _save(c, tid, st):
    c.execute("INSERT INTO clan_story(token_id,state,updated) VALUES(?,?,?) ON CONFLICT(token_id) DO UPDATE SET state=excluded.state,updated=excluded.updated",
              (tid, json.dumps(st, separators=(",", ":")), time.time()))


def _store(c, tid, st, msgs, faction, day, week):
    now = time.time()
    for m in msgs:
        if "sn" not in st:
            st["sn"] = st["n"]
        st["n"] += 1
        if m.get("kind") not in ("alife", "chron"):
            st["sn"] += 1
        m.update(id=st["n"], day=day, week=week, faction=faction, ts=round(now, 3))
        c.execute("INSERT OR REPLACE INTO clan_feed(token_id,id,ts,day,week,kind,mood,faction,text,names,lid,params) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                  (tid, m["id"], m["ts"], day, week, m["kind"], m["mood"], faction, m["text"], json.dumps(m["names"]), m.get("lid"),
                  json.dumps(m["params"], separators=(",", ":"), ensure_ascii=False) if m.get("params") else None))
    c.execute("DELETE FROM clan_feed WHERE token_id=? AND id<=?", (tid, st["n"] - feed_max()))


def _alife():
    """tools/clan_alife.py when it exists and its switch is on (default off), else None. Never raises."""
    try:
        import clan_alife
        return clan_alife if clan_alife.enabled() else None
    except Exception:                                      # noqa: BLE001 - the A-Life is optional
        return None


def _chronicle():
    try:
        import clan_chronicle
        return clan_chronicle if clan_chronicle.enabled() else None
    except Exception:                                       # noqa: BLE001
        return None


def feed_max():
    return 100 if (_alife() or _chronicle()) else FEED_MAX


def _rng(st, salt):
    # st["sn"] counts the DIARY rows only (st["n"] counts every row incl. the A-Life rows, tools/clan_alife.py): the diary's randomness - who falls sick, who
    # is named - must not depend on whether the A-Life switch was on. Without A-Life rows sn == n (and a state without "sn" uses n): nothing changes.
    return random.Random("%s:%s:%d:%s" % (st["seed"], st["run"], st.get("sn", st["n"]), salt))


def _purge_feed(c, tid):
    """Seen in game (JOURNAL tab, a brand-new clan): on day 1 the journal had lore up to day 4. ROOT CAUSE: CHOOSE YOUR SIDE after a dead / won clan
    (clan.choose_side -> on_new_run) and the reset-clan path of on_day started a new run (day 0) but never removed the previous run's clan_feed rows, which stay
    under the same clan key (ids keep counting) - so the new clan's journal showed the old run's days 1-4 above its own founding line. A run owns its rows."""
    try:
        c.execute("DELETE FROM clan_feed WHERE token_id=?", (tid,))
    except Exception:                                      # noqa: BLE001 - no table yet = nothing to purge
        pass
    try:
        import clan_journal
        clan_journal.purge(c, tid)                         # the journal entries (one per clan day, tools/clan_journal.py) belong to the run as well
    except Exception:                                      # noqa: BLE001
        pass


def on_new_run(c, tid, faction, run=None):
    """First day of a clan (CHOOSE YOUR SIDE): five survivors and the founding line."""
    ensure(c)
    old = _load(c, tid)
    st = new_state(tid, faction, (old["run"] + 1) if old else 1)
    st["n"] = old["n"] if old else 0          # message ids keep counting across runs
    _purge_feed(c, tid)                       # ... but the OLD run's rows go (a brand-new clan on day 1 showed lore up to day 4 - the previous run's diary)
    rng = _rng(st, "new")
    _populate(rng, st, clan.START_SURVIVORS, 0, 0, 0)
    w = Writer(rng, st, 0, 1)
    ppl = {k: p for k, p in zip("ABC", st["people"])}
    w.add("founding", ppl)
    _store(c, tid, st, w.out, faction, 0, 1)
    try:
        import clan_journal
        clan_journal.on_new_run(c, tid, st)                # the journal's first page (day 0)
    except Exception as ex:                                # noqa: BLE001 - the journal never breaks the clan
        sys.stderr.write("clan_journal (new run) failed: %r" % (ex,) + chr(10))
    _save(c, tid, st)
    try:
        import clan_alife
        clan_alife.reset(c, tid)                           # a new run: the old simulation goes (the table is only touched when it exists)
    except Exception:                                      # noqa: BLE001
        pass
    return w.out


def on_day(c, tid, newc, r):
    """After clan.apply_match: update the roster and write the day's messages. `newc` = the clan dict after the day, `r` = its result."""
    if not r or not newc or int(newc.get("faction", 0)) not in (clan.WLF, clan.SERAPHITES):
        return []
    ensure(c)
    st = _load(c, tid)
    faction = int(newc["faction"])
    if not st or st["fac"] != faction:
        if st:
            _purge_feed(c, tid)                              # a different faction = a new run: the old run's diary rows must not mix into it
        st = new_state(tid, faction, (st["run"] + 1) if st else 1)
        rng = _rng(st, "boot")
        # a clan that existed before the feed: rebuild the roster from the counts as they were before this day
        h, u, s = int(newc["healthy"]), int(newc["hungry"]), int(newc["sick"])
        st["day"] = int(r.get("day", newc["day"]))
        st["boot"] = 1
        h_before = max(0, h + int(r.get("died", 0)) - int(r.get("gained", 0)) - int(r.get("evg", 0)))
        _populate(rng, st, h_before, u, s, st["day"])
    elif int(newc["day"]) < st["day"]:                       # a reset clan that never went through on_new_run
        n = st["n"]
        _purge_feed(c, tid)                                  # the reset clan's old rows (days beyond its new day) go with the old run
        st = new_state(tid, faction, st["run"] + 1)
        st["n"] = n
        rng = _rng(st, "reset")
        _populate(rng, st, int(newc["healthy"]), int(newc["hungry"]), int(newc["sick"]), 0)
    rng = _rng(st, "day%d" % int(newc["day"]))
    jsnap = None
    try:
        import clan_journal
        jsnap = clan_journal.snapshot(st)                  # the roster before the day: the journal entry is written from what the day changed
    except Exception:                                      # noqa: BLE001
        pass
    msgs = story_day(st, rng, newc, r)
    away = {p["n"] for p in st["people"] if str(p["i"]) in ((st.get("ch") or {}).get("away") or {})}
    if away:                                               # somebody in a story arc is away from camp: no diary line names them (deaths excepted)
        msgs = [m for m in msgs if not (set(m["names"]) & away) or m["kind"].startswith("death_") or m["kind"].startswith("loss")]
    al = _alife()
    if al:                                                 # the A-Life rows of the day come after the diary rows (it never changes a number or a state)
        try:
            msgs = msgs + al.on_day(c, tid, st, newc, r, msgs)
        except Exception as ex:                            # noqa: BLE001 - the diary never breaks because of the A-Life
            sys.stderr.write("clan_alife failed: %r\n" % (ex,))
    ch = _chronicle()
    if ch:                                                 # the chronicle (multi-sentence vignettes, match results, loot): switch tools/clan_chronicle.txt, default OFF
        try:
            msgs = msgs + ch.day_rows(st, newc, r)
            try:
                import clan_continuity
                msgs = msgs + clan_continuity.recap_rows(c, tid, st, newc)      # a clan with an older diary: one "where we stand" row, the bridge into the saga
            except Exception as ex:                        # noqa: BLE001
                sys.stderr.write("clan_continuity (recap) failed: %r" % (ex,) + chr(10))
        except Exception as ex:                            # noqa: BLE001
            sys.stderr.write("clan_chronicle failed: %r\n" % (ex,))
    _store(c, tid, st, msgs, faction, int(newc["day"]), clan.week_day(int(newc["day"]))[0])
    if jsnap is not None:
        try:
            clan_journal.on_day(c, tid, st, jsnap, newc, r)    # ONE journal entry for the clan day, and the status cards' lines
        except Exception as ex:                            # noqa: BLE001 - the journal never breaks the clan
            sys.stderr.write("clan_journal (day) failed: %r" % (ex,) + chr(10))
    _save(c, tid, st)
    return msgs


# ------------------------------------------------------------------ reading (also used read-only by the update server)
def read_feed(c, tid, limit=30, since=0, lang="en", callbacks=False, _who=False, fold=False):
    """Newest first. Works on any sqlite connection (a missing table = [], a table without the lid / params columns = English only).
    lang "pl": every message that was stored with its template id is rendered in Polish (m["lang"] == "pl"); older ones stay English (m["lang"] == "en").
    fold=True (with callbacks, the journal screens): story_rows() - every row gets m["card"] (True = a story, False = a one-liner for the timeline); nothing is merged.
    callbacks=True (the journal screens, not the toasts): the diary rows that continue an earlier entry get a call-back tail and thread / tstep / prev (tools/clan_continuity.py)."""
    if callbacks:
        full = read_feed(c, tid, feed_max(), 0, lang, _who=True)
        try:
            import clan_continuity
            st = _load(c, tid) or {}
            clan_continuity.annotate(full, st.get("dead", []), {p["n"]: p.get("id", 0) for p in st.get("people", []) if p.get("s") == "s" and p.get("id")}, PLN.norm_lang(lang))
        except Exception as ex:                                # noqa: BLE001 - the journal never breaks because of the call-backs
            sys.stderr.write("clan_continuity failed: %r" % (ex,) + chr(10))
        for m in full:
            m.pop("who", None)
        if fold:
            full = story_rows(full)                            # the journal screens (in game + launcher): every row marked card (a story) / line (a one-liner between the stories)
        return [m for m in full if m["id"] > int(since)][:max(1, min(int(limit), feed_max()))]
    limit = max(1, min(int(limit), feed_max()))
    lang = PLN.norm_lang(lang)
    try:
        rows = c.execute("SELECT id,day,week,kind,mood,faction,text,names,ts,lid,params FROM clan_feed WHERE token_id=? AND id>? ORDER BY id DESC LIMIT ?",
                         (tid, int(since), limit)).fetchall()
    except Exception:
        try:
            rows = [r + (None, None) for r in c.execute("SELECT id,day,week,kind,mood,faction,text,names,ts FROM clan_feed WHERE token_id=? AND id>? "
                                                          "ORDER BY id DESC LIMIT ?", (tid, int(since), limit)).fetchall()]
        except Exception:
            return []
    out = []
    for i, day, week, kind, mood, fac, text, names, ts, lid, params in rows:
        try:
            nm = json.loads(names or "[]")
        except ValueError:
            nm = []
        used = "en"
        if lang == "pl" and lid and params:
            try:
                t = render_msg(lid, json.loads(params), "pl")
                if t:
                    text, used = t, "pl"
            except Exception:                                  # noqa: BLE001 - an unreadable row stays English
                pass
        m = {"id": i, "day": day, "week": week, "kind": kind, "mood": mood, "faction": fac, "text": text, "names": nm, "ts": ts, "lang": used}
        if _who and params and not (lid or "").startswith(("ch/", "sg/", "arc/", "pk/", "al/", "cn/")):          # diary rows: who is who (letters A / D), for the call-backs
            try:
                m["who"] = {k: v[0] for k, v in json.loads(params).get("p", {}).items() if k in "AD"}
            except (ValueError, AttributeError, TypeError, IndexError, KeyError):
                pass
        if lid and lid.startswith("ch/"):                      # chronicle rows: the first piece's pool = the entry's style (band colour / icon) in the clan screens
            m["style"] = lid[3:].split("+")[0].split("~")[0]
        elif lid and lid.startswith("cn/"):                    # the one-time recap of a clan that had a diary before the chronicle (tools/clan_continuity.py)
            m["style"] = "saga_recap"
        elif lid and lid.startswith("pk/"):                    # a clan supply perk was used (tools/clan_perks.py)
            m["style"] = "perk"
        elif lid and lid.startswith("sg/"):                    # a saga row: style saga_<scene>; rows of one person's thread (injury, grief, relationship) share "arc" = thread id
            m["style"] = "saga_" + lid[3:]
            try:
                pj = json.loads(params or "{}")
                if pj.get("a"):
                    m["arc"] = pj["a"]
                if (pj.get("s") or {}).get("map"):
                    m["map"] = pj["s"]["map"]                  # the match's map (the call-backs of clan_continuity: "last time on ...")
            except ValueError:
                pass
        elif lid and lid.startswith("arc/"):                   # a story arc step: style arc_<kind>, arc id + step for the thread view of the clan screens
            m["style"] = "arc_" + lid[4:].split(".")[0]
            try:
                pj = json.loads(params or "{}")
                m["arc"], m["step"] = pj.get("a"), pj.get("n")
            except ValueError:
                pass
        out.append(m)
    done = _days_done(c, tid)
    if done is not None:                                       # never serve a day the clan has not reached (rows of an older run / a reset clan, see _purge_feed)
        out = [m for m in out if int(m["day"] or 0) <= done]
    return out


def _days_done(c, tid):
    """The clan's day counter (days done) from the clans table, None when there is no clan row (tests, a missing table)."""
    try:
        r = c.execute("SELECT day FROM clans WHERE token_id=?", (tid,)).fetchone()
        return int(r[0]) if r and r[0] is not None else None
    except Exception:                                          # noqa: BLE001
        return None


_SENT = re.compile(r"(?<=[.!?])\s+(?=[A-Z\"'(])")
_HEAD = re.compile(r"^(?:DAY|DZIEŃ) \d+: [^.]*\.\s*")
_HEAD_NUM = re.compile(r"^(?:DAY|DZIEŃ) \d+: ")
_WB = r"(?<!\w)%s(?!\w)"


def _sentences(t, names=()):
    """The plain sentences of a journal text. The "DAY n: HEADLINE." prefix of an arc / saga row (the headline is the event itself, in capitals) becomes the first
    sentence in sentence case, names and places with their capital again (taken from the row's names and from the capitalised words of its own body)."""
    t = str(t or "").strip()
    m = _HEAD.match(t)
    if m:
        head = _HEAD_NUM.sub("", m.group(0)).strip().rstrip(".")
        body = t[m.end():]
        low = head.lower()
        caps = set(names) | set(re.findall(r"(?<=[a-z,;] )[A-Z][a-z]+", body)) | set(re.findall(r"[A-Z][a-z]+(?= [A-Z][a-z]+)", body))
        for w in sorted(caps, key=len, reverse=True):
            low = re.sub(_WB % re.escape(w.lower()), w, low)
        t = (low[:1].upper() + low[1:] + ". " + body).strip()
    return [x.strip() for x in _SENT.split(t) if x.strip()]


STORY_MIN_CHARS = 150                                          # a journal card is a written piece: at least this long and at least two sentences (the founding line excepted)
DAY_STORIES = 2                                                # story cards per clan day (not so cluttered); deaths and arrivals do not count against it; the overflow becomes timeline lines
LINE_MAX = 96                                                  # chars of a timeline line (one row in the launcher, one small row in game)
# chronicle styles that are camp colour, not a story: always a timeline line (their first sentence), never a card
_MINOR_STYLES = ("saga_keepcb", "saga_use", "saga_lack", "kids", "quiet", "sick_watch", "saga_prep", "saga_keepfind", "saga_rel", "saga_prof")
# the strongest stories first: when a day has more than DAY_STORIES, the first of these keep their card, the rest give it up (a line)
_STORY_ORDER = ("arc_", "saga_win", "saga_down", "saga_exec", "saga_rev", "saga_inj", "saga_grief", "saga_haul")


def _story_rank(m):
    """None = a one-liner (never a card); else 0 founding / a death / an arrival (always a card), 1 arcs and saga pieces."""
    k, st, txt = str(m.get("kind") or ""), str(m.get("style") or ""), str(m.get("text") or "")
    if k == "founding":
        return 0
    n = len(_sentences(txt, m.get("names") or ()))
    if n < 2 or (len(txt) < STORY_MIN_CHARS and not k.startswith(("death_", "loss", "join"))):
        return None
    if k.startswith(("death_", "loss", "join")) or st in ("saga_death", "saga_loss", "saga_recap", "arc_new", "arc_birth", "arc_spore"):
        return 0
    if st in _MINOR_STYLES:
        return None
    if st.startswith(("arc_", "saga_")):
        return 1
    return None                                                # diary and A-Life rows (camp log, feelings, weather, a sick member, tickers ...): lines


def story_rows(rows):
    """The journal is reserved for high quality stories; the 1 liners go in between the stories. rows = newest first
    (read_feed shape). Every row gets m["card"]: True = a story (a written piece of the chronicle / saga / arcs, a death, an arrival, the founding), False = a
    one-liner for the timeline between the stories. A one-liner is never a card; a day with more than DAY_STORIES stories keeps the strongest ones as cards and the
    rest become lines. Nothing is merged or dropped; returns the same rows (copies) in the same order."""
    days = {}
    for m in rows:
        days.setdefault((int(m.get("week") or 0), int(m.get("day") or 0)), []).append(m)
    demote = set()
    for grp in days.values():
        ranked = sorted((m for m in grp if _story_rank(m) not in (None, 0)), key=lambda m: (next((i for i, o in enumerate(_STORY_ORDER) if str(m.get("style") or "").startswith(o)), 99), -int(m["id"])))
        for m in ranked[DAY_STORIES:]:
            demote.add(m["id"])
    out = []
    for m in rows:
        card = _story_rank(m) is not None and m["id"] not in demote
        out.append(dict(m, card=True) if card else dict(m, card=False, line=line_text(m)))
    return out


def line_text(m):
    """The timeline line of a row: its first sentence(s) in one row of at most LINE_MAX chars."""
    raw = str(m.get("text") or "")
    hd = re.match(r"\s*(?:DAY|DZIEŃ)\s+\d+:\s*([^a-ząćęłńóśźż]+?)[.!?]\s+(?=\S)", raw)
    if hd:                                                     # a saga row "DAY n: TITLE. body": as a line the title alone ("The two at the end of the table.") says nothing
        raw = raw[hd.end():]
    ss = _sentences(raw, m.get("names") or ()) or [raw]
    t = ss[0]
    for x in ss[1:]:                                           # whole sentences while they fit ("The two at the end of the table." alone says nothing)
        if len(t) + 1 + len(x) > LINE_MAX:
            break
        t += " " + x
    t = re.sub(r"[" + chr(92) + "r" + chr(92) + "n" + chr(92) + "t]+", " ", t).strip()
    if len(t) <= LINE_MAX:
        return t
    return t[:LINE_MAX].rsplit(" ", 1)[0].rstrip(",;:") + "..."


def journal(rows, max_lines=3):
    """The journal model of the clan screens: [{"card": row, "lines": [rows], "more": n}] newest story first. A one-liner belongs to the story it FOLLOWS (the newest
    card with a smaller id); lines older than every card attach to the oldest card. Each card carries its first max_lines lines in time order (+ "more" = the rest).
    rows come from story_rows (newest first)."""
    cards = sorted((m for m in rows if m.get("card")), key=lambda m: int(m["id"]))
    if not cards:
        return []
    by = {m["id"]: {"card": m, "lines": [], "more": 0} for m in cards}
    ids = [int(m["id"]) for m in cards]
    import bisect
    for m in sorted((m for m in rows if not m.get("card")), key=lambda m: int(m["id"])):
        i = max(0, bisect.bisect_right(ids, int(m["id"])) - 1)
        ent = by[cards[i]["id"]]
        if len(ent["lines"]) < max_lines:
            ent["lines"].append(m)
        else:
            ent["more"] += 1
    return [by[m["id"]] for m in reversed(cards)]


def latest(c, tid, n=5, since=0, lang="en"):
    """For the in-game toast widget (the daemon's clan op handler): the newest `n` lines with id > since, OLDEST first, text cut to one
    line (<= WIDGET_MAX chars at a sentence boundary), plain UTF-8, no markup. Fields: id, day, week, kind, mood, faction, text."""
    rows = read_feed(c, tid, n, since, lang)
    return [{"id": m["id"], "day": m["day"], "week": m["week"], "kind": m["kind"], "mood": m["mood"], "faction": m["faction"],
             "text": short_text(m["text"])} for m in reversed(rows)]


def read_people(c, tid, limit=80, lang="en"):
    """Roster summary for the CAMP view (alive members): name, role, gender, state, mood, illness. Plus morale. {} when there is no story.
    lang "pl" adds the Polish display words next to the machine keys (roleText / stateText / moodText / illnessText, morale.text); the English keys stay."""
    st = _load(c, tid)
    if not st:
        return {}
    fk = _fkey(st["fac"])
    pl = PLN.norm_lang(lang) == "pl"
    people = []
    for p in st["people"][:limit]:
        il = D.ILLNESS.get(p["il"])
        e = {"name": p["n"], "gender": p["g"], "role": D.ROLES[p["r"]][0 if fk == "W" else 1],
             "state": {"h": "healthy", "u": "hungry", "s": "sick"}[p["s"]], "mood": mood_of(st, p), "illness": il[0] if il else ""}
        if pl:
            e.update(PLN.people_labels(fk, p["g"], p["r"], p["s"], mood_of(st, p), p["il"]))
        people.append(e)
    morale = {"value": st["morale"], "label": morale_label(st["morale"])}
    if pl:
        morale["text"] = PLN.MORALE[morale["label"]]
    return {"morale": morale, "people": people, "alive": len(st["people"]), "dead": [{"name": d["n"], "day": d["d"]} for d in st["dead"][-8:]]}


def widget_text(text):
    """One in-game line: <= WIDGET_MAX chars, <= 150 bytes, no '|' and no newline (the wire format of op 0xB4)."""
    t = short_text(text.replace("\n", " ").replace("|", "/"), WIDGET_MAX)
    while len(t.encode("utf-8")) > 150:
        t = t[:-2].rstrip() + "…"
    return t


# plural voice in either language (the menu text is rendered in the player's language): English via SO.GROUP_RE, Polish pronouns / "nikt" /
# "wszyscy" and first-person-plural verb endings (-my / -śmy)
_PL_GROUP_RE = re.compile(r"(?<!\w)(my|nas|nam|nami|nasz\w*|nikt\w*|wszyscy|wszystkich|\w+(?:śmy|emy|imy|amy|ymy))(?!\w)", re.I)
_SOLO_DEATH = {   # (EN, PL male, PL female)
    "death": ("{A} is gone.", "{A} nie żyje.", "{A} nie żyje."),
    "death_starved": ("{A} starved to death.", "{A} umarł z głodu.", "{A} umarła z głodu."),
    "death_illness": ("The sickness took {A}.", "Choroba zabrała {A}.", "Choroba zabrała {A}."),
    "death_lost": ("{A} never came back.", "{A} nie wrócił.", "{A} nie wróciła."),
    "death_walkout": ("{A} walked away and never came back.", "{A} odszedł i nie wrócił.", "{A} odeszła i nie wróciła."),
    "death_attack": ("{A} was killed in the attack.", "{A} zginął w ataku.", "{A} zginęła w ataku."),
    "death_bite": ("{A} was bitten.", "{A} został ugryziony.", "{A} została ugryziona.")}
def _plural(t):
    return bool(SO.GROUP_RE.search(t) or _PL_GROUP_RE.search(t))


def _widget_keep(c, tid, st, rows, lang):
    """The rows of the stored feed the widget may show for the clan state st (alive subjects only, voice that fits the clan's size, this run only)."""
    alive = {p.get("n") for p in st.get("people", [])}
    try:
        r0 = c.execute("SELECT MAX(id) FROM clan_feed WHERE token_id=? AND kind='founding'", (tid,)).fetchone()[0] or 0
    except Exception:                                # noqa: BLE001
        r0 = 0
    lids = {}
    try:
        for i_, l_ in c.execute("SELECT id,lid FROM clan_feed WHERE token_id=? AND id>=?", (tid, min([m["id"] for m in rows] or [0]))).fetchall():
            lids[i_] = l_
    except Exception:                                # noqa: BLE001 - a table without the lid column: every row counts as group voice
        pass
    n_alive = len(alive)
    def keep(m):
        k = m.get("kind") or ""
        if m["id"] < r0:
            return False
        voice = SO.voice_of_lid(lids.get(m["id"]))
        text = m.get("text") or ""
        # the narrator's voice must fit the clan's size NOW (one survivor, yet "We're watching her" / "Nobody's laughing at dinner"):
        # a first-person-singular line is the survivor's, a "we" line needs two or more, crowd words need three or more
        if voice == "solo":
            return n_alive == 1
        if voice == "duo":
            return n_alive == 2
        if n_alive == 1 and k in FEELING_KINDS:
            return False                              # group voice: a feeling about the one who is now the narrator
        if n_alive == 1 and _plural(text):
            # a happening told in the group's voice ("Ezra broke his leg. Nobody says it."): the news stays, the plural-voice sentences go;
            # when the news sentence itself is plural the line is hidden
            parts = [x for x in re.split(r"(?<=[.!?])\s+", text) if x]
            if not parts or _plural(parts[0]):
                nm = m.get("names") or []
                if not (k.startswith("death") and nm):
                    return False
                # a death told as "We have lost Lev to want.": the news itself must still reach the survivor - plain fact instead
                g = next((d.get("g") for d in st.get("dead", []) if d.get("n") == nm[0]), "m")
                col = 0 if PLN.norm_lang(lang) != "pl" else (2 if g == "f" else 1)
                m["text"] = _SOLO_DEATH.get(k, _SOLO_DEATH["death"])[col].format(A=nm[0])
                return True
            m["text"] = " ".join(x for x in parts if not _plural(x))
        if n_alive == 2 and SO.CROWD_RE.search(text):
            return False
        if k not in FEELING_KINDS:                  # a happening: deaths, getting sick / worse / better, joins, events, founding
            return True
        nm = m.get("names") or []                 # a feeling / state right now: only while the one it's about is alive
        if k == "ticker":
            return not nm or all(x in alive for x in nm)      # a ticker line names its companions too: all of them must still be alive
        return not nm or nm[0] in alive
    rows = [m for m in rows if keep(m)]
    return rows


def pick_for_widget(c, tid, seen, n=3, window=12, lang="en"):
    """Legacy per-reader picker (a `seen` set kept by the caller; the menu now uses the deterministic pick_slot instead): up to n of the newest `window`
    messages, newest unseen first; when everything recent was shown the cycle starts over. Returns [(id, text), ...] oldest first."""
    rows = read_feed(c, tid, window, lang=lang)
    # With one survivor left, texts about other members must not show; descriptions in the present tense only concern characters that are still alive.
    # Past-tense kinds (deaths, losses, the founding,
    # the clan's end) always show; any other message only while its subject (names[0], the one the text is about) is alive. Messages from an
    # earlier run (before this run's founding message) never show.
    st = _load(c, tid)
    if st:
        rows = _widget_keep(c, tid, st, rows, lang)
    if not rows:
        return []
    fresh = [m for m in rows if m["id"] not in seen]
    if not fresh:
        seen.clear()
        fresh = list(rows)
    take = sorted(fresh[:n], key=lambda m: m["id"])
    for m in take:
        seen.add(m["id"])
    if len(seen) > 200:
        seen.clear()
    return [(m["id"], widget_text(m["text"])) for m in take]


# ------------------------------------------------------------------ the menu ticker: ONE deterministic source for the game widget AND the launcher
# The clan notifications in the launcher were mismatched from the ones in game. Cause: the game (daemon op 0xB4) drew its live lines from
# an unseeded random.Random() on every request with a per-token seen-set and an in-process no-repeat memory, while the launcher (/clanfeed.json) served
# only the stored day events and, when empty, its own JS ticker - two generators, no shared ids, and the view keyed the clan by install id while the
# daemon keys by "s:<steamid>".  Now the whole reply is a pure function of (clan key, clan state, time slot, language):
#   menu_lines(c, tid, now, n, lang) = stored events picked by slot rotation + live lines from a generator seeded by (key, run, day, state, slot).
# The slot is SLOT_S seconds long (the game re-asks every 45 s); the same slot gives the same ids and, per language, the same text on every path
# (daemon op 0xB4, /clanfeed.json "menu", the launcher over the daemon). The no-repeat memory is derived, not stored: a slot avoids the templates
# of the previous two slots (recomputed the same way), so nothing is written and nothing depends on which process answered.
# The only DB write: a clan with no clan_story roster gets one created lazily (ensure_roster, save=True); the read-only view builds the same roster
# in memory (same seed), so both agree before and after that write.
SLOT_S = 60
LIVE_N = 6                                                # lines generated per slot (the game shows up to 6, FEED_MAX of t2r-ext)
FRESH_S = 900                                             # a stored event younger than this goes first in the rotation


def slot_of(now=None):
    return int((time.time() if now is None else now) // SLOT_S)


def ensure_roster(c, tid, save=True):
    """The clan's story state, created from the clan's current numbers when missing or of another faction (additive: an existing roster is
    never touched, no feed message is written). None for a player without a WLF / Seraphite clan (or an empty one). save=False (the read-only
    view): the same roster is built in memory and nothing is written."""
    try:
        cl = clan.load(c, tid)
    except Exception:                                    # noqa: BLE001
        return None
    faction = int(cl.get("faction", 0))
    if faction not in (clan.WLF, clan.SERAPHITES):
        return None
    st = _load(c, tid)
    if st and st["fac"] == faction and st["people"]:
        return st
    h, u, s = int(cl["healthy"]), int(cl["hungry"]), int(cl["sick"])
    if h + u + s <= 0:
        return None
    if save:
        ensure(c)
    n = st["n"] if st else 0
    st = new_state(tid, faction, (st["run"] + 1) if st else 1)
    st["n"] = n
    st["day"] = int(cl.get("day", 0))
    st["boot"] = 1
    _populate(_rng(st, "lazy"), st, h, u, s, st["day"])
    if save:
        _save(c, tid, st)
    return st


# --- the rich good-state ticker: who a healthy member is with, what they do, what the clan went through
_RICH_ROWS = [(sc, en, PLN.tpl_letters(en)) for sc, en, _pl in RG.ROWS]


def rich_for(st, p, fk):
    """[(English template, pool)] of the good-state lines person p can be the subject of right now: every row of clan_story_good_rich whose people
    exist (B / C = other HEALTHY living members, D = the latest dead member), scope-filtered, island-filtered, no crowd words in a clan of two."""
    others = [q for q in st["people"] if q["i"] != p["i"] and q["s"] == "h"]
    two = len(st["people"]) == 2
    out = []
    for scope, en, letters in _RICH_ROWS:
        if scope not in ("*", fk):
            continue
        if ("B" in letters and not others) or ("C" in letters and len(others) < 2) or ("D" in letters and not st["dead"]):
            continue
        if fk == "S" and any(k in en for k in D.TICKER_NOT_SERA):
            continue
        if two and SO.CROWD_RE.search(en):
            continue
        out.append((en, "t:g"))
    return out


def _bare_2013_healthy(fk, two):
    """The 2013 healthy lines that say something (not the 13 bare "X is healthy.") - the fallback when no rich row fits."""
    pool = list(dict.fromkeys(t for t in D.TICKER_HEALTHY if t != "{A} is healthy."))
    if fk == "S":
        pool = [t for t in pool if not any(k in t for k in D.TICKER_NOT_SERA)]
    if two:
        pool = [t for t in pool if not SO.CROWD_RE.search(t)]
    return pool


def ticker_for(rng, st, p, avoid):
    """One ticker line about p's real state: (English template, pool id, people dict). `avoid` = template ids (line_id) not to repeat now;
    when everything fits it is ignored. Healthy: a rich row (rich_for) about p and its companions; sick: the 2013 sick lines (rare joke 1.5%);
    hungry: the 2013 hungry lines."""
    fk = _fkey(st["fac"])
    two = len(st["people"]) == 2
    if p["s"] == "s" and rng.random() < D.TICKER_RARE_CHANCE and not KD.is_kid(p):
        return D.TICKER_RARE_SICK, "t:r", {"A": p}
    if p["s"] == "h":
        cands = rich_for(st, p, fk)
        if not cands:
            cands = [(t, "t:h") for t in _bare_2013_healthy(fk, two)]
    else:
        pool_t = D.TICKER_SICK if p["s"] == "s" else D.TICKER_HUNGRY
        pool_id = "t:s" if p["s"] == "s" else "t:u"
        if fk == "S":
            pool_t = [t for t in pool_t if not any(k in t for k in D.TICKER_NOT_SERA)]
        if two:
            pool_t = [t for t in pool_t if not SO.CROWD_RE.search(t)]
        cands = [(t, pool_id) for t in pool_t]
    cands = [x for x in cands if _companion_ok(st, p, x[0])] or [_KID_PLAIN[p["s"]]]
    if KD.is_kid(p):                                    # a kid's ticker line is never combat, raid, patrol or weapon lore
        cands = [x for x in cands if not KD.combat_text(x[0], "en") and not KD.combat_text(_pl_twin(x[0]), "pl")] or [_KID_PLAIN[p["s"]]]
    fresh = [x for x in cands if line_id(x[0]) not in avoid]
    t, tpool = rng.choice(fresh or cands)
    people = {"A": p}
    letters = PLN.tpl_letters(t)
    if "B" in letters or "C" in letters:
        others = [q for q in st["people"] if q["i"] != p["i"] and q["s"] == "h"]
        if KD.combat_text(t, "en") or KD.combat_text(_pl_twin(t), "pl"):         # a fight line names grown people only
            others = [q for q in others if KD.can_fight(q)] or others
        rng.shuffle(others)
        people["B"] = others[0]
        if "C" in letters:
            people["C"] = others[1]
    if "D" in letters and st["dead"]:
        dd = st["dead"][-1]
        people["D"] = {"n": dd["n"], "g": dd["g"], "r": dd.get("r", "")}
    return t, tpool, people


def _sym(rng, st):
    fk = _fkey(st["fac"])
    return {"f": fk, "day": st["day"], "week": clan.week_day(st["day"])[0], "place": rng.choice(D.FACTION[fk]["places"]), "inf": rng.choice(D.INFECTED)}


def _solo_candidates(rng, st, p, fk):
    """Every diary line the ONE survivor p could say right now: [(pool name, template, people, line key)]. Ticker lines of the state, the quiet / lonely /
    faction-flavour lines, the mood of the day, and grief for the dead (one dead member at a time, by cause)."""
    morale = st["morale"]
    out = []
    def add(pairs, extra=None, tag=""):
        for sc, t in pairs:
            if sc in ("*", fk) and KD.kid_safe(t, {"A": p}, _pl_twin(t)):
                out.append((SO.TPL_POOL[t], t, dict(extra or {}, A=p), line_id(t) + (tag if "{D}" in t else "")))
    add(SO.solo_ticker(p["s"]))
    add(SO.SOLO["calm"])                                 # the quiet / lonely / faction-flavour lines fit every state
    if p["s"] == "u":
        add(SO.SOLO["hunger"]); add(SO.SOLO["starving"])
    elif p["s"] == "s":
        add(SO.SOLO["sick"])
        if p["is"] >= 1:
            add(SO.SOLO["worse"]); add(SO.SOLO["medicine"])
    else:
        add(SO.SOLO["hope"])
        if morale >= 60:
            add(SO.SOLO["plenty"])
        if morale <= 30:
            add(SO.SOLO["despair"])
    dead = st["dead"][-8:]
    if dead:
        dd = rng.choice(dead)
        d = {"n": dd["n"], "g": dd["g"], "r": dd.get("r", "")}
        add(SO.solo_pool("grief_mercy" if dd["c"] in ("mercy", "bite_kin") else "grief", dd["c"]), {"D": d}, dd["n"])
        if p["s"] == "h":
            add(SO.SOLO["hope_after"], {"D": d}, dd["n"])
        if p["gl"]:
            add(SO.SOLO["guilt"], {"D": d}, dd["n"])
    return out


def _fp(st):
    """The part of the clan state a live line depends on, as a short string (a change of who is sick / dead / how morale stands moves the lines for every reader)."""
    raw = ",".join("%d%s%s%d%d" % (p["i"], p["s"], p["il"], p["is"], 1 if p.get("gl") else 0) for p in st["people"])
    raw += "/" + ",".join("%s%s" % (d["n"], d.get("c", "")) for d in st["dead"][-8:]) + "/%d" % st["morale"]
    return "%08x" % (zlib.crc32(raw.encode()) & 0xFFFFFFFF)


WINDOW = 24                                               # lines of one class (healthy / sick / hungry / the lone survivor) between two uses of a template
_PERMS = {}


def _perm(items, seed, e):
    """Epoch e of the class's shuffled template cycle: a pure function of (items, seed, e)."""
    k = (seed, e, len(items))
    r = _PERMS.get(k)
    if r is None:
        if len(_PERMS) > 400:
            _PERMS.clear()
        r = list(items)
        random.Random("%s:%d" % (seed, e)).shuffle(r)
        _PERMS[k] = r
    return r


def _cycle_pick(items, seed, k):
    """The template for line number k of a class: walk the class's pool in shuffled epochs of len(items) (no template twice inside an epoch) and, at an epoch
    border, swap the head templates that were in the previous epoch's tail with templates from the middle of the epoch, so the same template never comes
    back within min(WINDOW, len/3) lines of its class - exact for every reader, nothing stored, nothing remembered."""
    m = len(items)
    if m == 1:
        return items[0]
    e, j = divmod(k, m)
    cur = _perm(items, seed, e)
    w = min(WINDOW, (m - 1) // 3)
    if e == 0 or w <= 0:
        return cur[j]
    tail = {x[0] for x in _perm(items, seed, e - 1)[-w:]}
    cur = list(cur)
    t = w
    for jj in range(w):
        if cur[jj][0] in tail:
            while t < m - w and cur[t][0] in tail:
                t += 1
            if t >= m - w:
                break
            cur[jj], cur[t] = cur[t], cur[jj]
            t += 1
    return cur[j]


def _class_items(st, p, fk):
    """The template pool (key, template, pool id) of the class person p belongs to right now; the same for every member of that class."""
    two = len(st["people"]) == 2
    if p["s"] == "h":
        c = [(t, pid) for t, pid in rich_for(st, p, fk)] or [(t, "t:h") for t in _bare_2013_healthy(fk, two)]
    else:
        pool_t = D.TICKER_SICK if p["s"] == "s" else D.TICKER_HUNGRY
        pid = "t:s" if p["s"] == "s" else "t:u"
        if fk == "S":
            pool_t = [t for t in pool_t if not any(k in t for k in D.TICKER_NOT_SERA)]
        if two:
            pool_t = [t for t in pool_t if not SO.CROWD_RE.search(t)]
        c = [(t, pid) for t in pool_t]
    return [(line_id(t), t, pid) for t, pid in c]


def _gen_line(st, tid, k):
    """Line number k (= slot * LIVE_N + index) of the clan's ticker, language-neutral. Subjects go round-robin over a shuffled roster per round; the template of
    the line is the next one of the subject's class cycle (_cycle_pick)."""
    fk = _fkey(st["fac"])
    base = "%s:%s:%s:%d" % (tid, st["run"], _fp(st), st["day"])
    n = len(st["people"])
    rnd, idx = divmod(k, n)
    order = list(st["people"])
    random.Random("order:%s:%d" % (base, rnd)).shuffle(order)
    p = order[idx]
    rng = random.Random("line:%s:%d" % (base, k))
    sym = _sym(rng, st)
    if n == 1:
        cands = _solo_candidates(random.Random("solo:" + base), st, p, fk)
        items = [(key, t, pool, people) for pool, t, people, key in cands]
        key, t, pool, people = _cycle_pick(items, "solo:" + base, k)
        sym["ill"] = p["il"] or "none"
        return {"key": key, "tpl": t, "pool": pool, "people": people, "sym": sym}
    if p["s"] == "s" and rng.random() < D.TICKER_RARE_CHANCE and not KD.is_kid(p):
        return {"key": line_id(D.TICKER_RARE_SICK), "tpl": D.TICKER_RARE_SICK, "pool": "t:r", "people": {"A": p}, "sym": sym}
    items = _class_items(st, p, fk)
    cls = p["s"]
    if any(KD.is_kid(q) for q in st["people"]) or (st["dead"] and st["dead"][-1].get("r") == "kid"):
        items = [x for x in items if _companion_ok(st, p, x[1])] or [(line_id(_KID_PLAIN[p["s"]][0]),) + _KID_PLAIN[p["s"]]]
        cls += "c"
    if KD.is_kid(p):                                    # a kid's lines are never combat, raid, patrol or weapon lore (a class of their own)
        items = [x for x in items if not KD.combat_text(x[1], "en") and not KD.combat_text(_pl_twin(x[1]), "pl")] or [(line_id(_KID_PLAIN[p["s"]][0]),) + _KID_PLAIN[p["s"]]]
        cls += "k"
    key, t, pool = _cycle_pick(items, "cls%s:%s" % (cls, base), k)
    people = {"A": p}
    letters = PLN.tpl_letters(t)
    if "B" in letters or "C" in letters:
        others = [q for q in st["people"] if q["i"] != p["i"] and q["s"] == "h"]
        if KD.combat_text(t, "en") or KD.combat_text(_pl_twin(t), "pl"):
            others = [q for q in others if KD.can_fight(q)] or others
        rng.shuffle(others)
        people["B"] = others[0]
        if "C" in letters:
            people["C"] = others[1]
    if "D" in letters and st["dead"]:
        dd = st["dead"][-1]
        people["D"] = {"n": dd["n"], "g": dd["g"], "r": dd.get("r", "")}
    return {"key": key, "tpl": t, "pool": pool, "people": people, "sym": sym}


def _slot_recs(st, tid, slot):
    """The LIVE_N ticker lines of one time slot, language-neutral. A pure function of (clan key, state, slot): identical on every path / process."""
    return [_gen_line(st, tid, slot * LIVE_N + i) for i in range(LIVE_N)]


def _render_rec(rec, lang):
    people, sym = rec["people"], rec["sym"]
    text = render(rec["tpl"], people, expand_en(sym))
    if PLN.norm_lang(lang) == "pl":
        try:
            text = render_msg(PLN.lid(rec["pool"], rec["tpl"]), _params(people, sym), "pl") or text
        except Exception:                                # noqa: BLE001 - the English line goes out
            pass
    return text


def live_lines(c, tid, n=6, lang="en", now=None, save=True):
    """n generated ticker lines [(id, text)] about the clan's survivors for the time slot of `now` (roster created lazily when save): the SAME lines for the
    same (clan, slot, language) whoever asks. Ids "l<slot><index>" are stable within the slot. One survivor: that survivor's diary (first person, clan_story_solo.py);
    two: no crowd lines; healthy members get the rich good-state lines (clan_story_good_rich.py). [] without a clan."""
    st = ensure_roster(c, tid, save)
    if not st or not st["people"]:
        return []
    slot = slot_of(now)
    recs = _slot_recs(st, tid, slot)[:max(0, n)]
    return [("l%d%02d" % (slot % 100000, i), widget_text(_render_rec(r, lang))) for i, r in enumerate(recs)]


def _stored_rows(c, tid, lang):
    """The stored day events the widget may show (newest first): the filter of pick_for_widget, see there."""
    rows = [m for m in read_feed(c, tid, 24, lang=lang) if not str(m.get("style", "")).startswith("arc_")][:12]   # (arc steps live in the clan screen only, never in tickers / toasts)
    st = _load(c, tid)
    if st:
        rows = _widget_keep(c, tid, st, rows, lang)
    return rows


def pick_slot(c, tid, slot, n=3, lang="en", now=None):
    """Deterministic stored-event picks for a time slot [(id, text)] oldest first: events younger than FRESH_S first (newest first), the rest by a
    rotation (slot * n) over the kept events - so every reader at the same time sees the same ones, with no per-reader seen-set."""
    rows = _stored_rows(c, tid, lang)
    if not rows:
        return []
    now = time.time() if now is None else now
    fresh = [m for m in rows if now - float(m.get("ts") or 0) < FRESH_S][:n]
    rest = [m for m in rows if m not in fresh]
    take = list(fresh)
    if rest and len(take) < n:
        start = (slot * n) % len(rest)
        for k in range(min(n - len(take), len(rest))):
            take.append(rest[(start + k) % len(rest)])
    take.sort(key=lambda m: m["id"])
    return [(m["id"], widget_text(m["text"])) for m in take]


def menu_lines(c, tid, n=6, lang="en", now=None, save=True):
    """THE menu / ticker reply for a clan at a time: stored real events first (<= 3, pick_slot), then live ticker lines up to n in total. [(id, text)].
    Used by the daemon (op 0xB4) and by the update server (/clanfeed.json "menu"), so the game and the launcher show the same lines."""
    al = _alife()
    out = pick_slot(c, tid, slot_of(now), min(n, 2 if al else 3), lang, now)      # (with the A-Life on: 2 stored events, 3 simulated-life lines, the rest the classic 2013 ticker)
    if len(out) < n:
        if al:                                           # the simulated life: single-sentence facts about the people, expeditions, injuries, projects ...
            try:
                st = ensure_roster(c, tid, save)
                if st:
                    out += al.ticker_lines(c, tid, st, slot_of(now), min(al.TICKER_SHARE, n - len(out)), lang, now, save)
            except Exception:                            # noqa: BLE001 - the classic lines still go out
                pass
        try:
            out += live_lines(c, tid, n - len(out), lang, now, save)
        except Exception:                                # noqa: BLE001 - the stored lines still go out
            pass
    return out[:n]


def live_for_widget(c, tid, seen, n=6, lang="en", now=None):
    """Op 0xB4 reply lines (kept signature; `seen` is no longer used: the reply is a pure function of clan, time slot and language, see menu_lines)."""
    return menu_lines(c, tid, n, lang, now)
