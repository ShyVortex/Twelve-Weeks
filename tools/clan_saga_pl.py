"""Polish side of the clan saga (tools/clan_saga.py): the Polish templates (tools/clan_saga_pl_text*.py, one file per English clan_saga_text*.py, same pools, same order,
same W: / S: scopes, one Polish line for every English line) and the Polish forms of every variable.

The saga picks an ENGLISH template (that choice, the person choice and the variables stay language-neutral); this module renders the parallel Polish template with the Polish
forms of the same variables, so one saga row carries both texts (params["t"] English, params["tp"] Polish) and the clan screens show the one that matches the game language
(like the old Polish rows).  Rules of the Polish templates (as in tools/clan_story_pl.py):
  * people are named in the nominative only; other cases use pronouns {A?go|ją} (letters A-D; masculine | feminine, a neutral name takes the masculine one) and the
    verb endings {A?ł|ła};
  * the player ("you") is addressed without a gender: present tense, impersonal forms, "udało ci się", never "poszedłeś" / "poszłaś";
  * a variable comes in the case the sentence needs: {map} nominative, {map_gen}, {map_at} ("w szpitalu"), {map_to} ("do szpitala"), {map_from} ("ze szpitala"), {map_ins},
    {map_loc} (without the preposition); the same for {place} {place2} {kplace} {prev_map} {kmap} {ymap} {camp}; see expand().
"""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import clan_story_pl as PLN                                  # noqa: E402
import clan_chronicle_maps as MAPN                           # noqa: E402
import clan_saga_pl_data as PD                               # noqa: E402

NW = ["no", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten"]
_ZE = re.compile(r"^(s|z|ś|ź|ż|w[bcćdfghjklłmnńprsśtwzźż])", re.I)


_WE = re.compile(r"^[wf][bcćdfghjklłmnńprsśtwzźż]", re.I)


def _prep(prep, loc):
    """'w' -> 'we' before a word that begins with w / f and a consonant ('we wschodnich koszarach')."""
    return "we" if prep == "w" and _WE.match(loc) else prep


def _from(gen):
    return ("ze " if _ZE.match(gen) else "z ") + gen


def _num(word):
    """'five' -> 5, '12' -> 12."""
    w = str(word).strip().lower()
    if w in NW:
        return NW.index(w)
    return int(w)


def _few(n):
    return 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14


def times(n):
    """'raz' / 'dwa razy' / 'pięć razy' / '12 razy'."""
    if n == 1:
        return "raz"
    return "%s razy" % (PD.NUM_M[n] if n <= 10 else n)


def count(n, one, few, many, fem=False):
    """A counted noun in the nominative / accusative of things: 'jeden nabój', 'dwa naboje', 'pięć naboi', '12 naboi', '22 naboje'."""
    num = (PD.NUM_F if fem else PD.NUM_M)[n] if n <= 10 else str(n)
    return "%s %s" % (num, one if n == 1 else few if _few(n) else many)


def ex_phrase(n, case):
    """executions: nom / acc / gen (feminine: egzekucja)."""
    if case == "gen":
        num = ("jednej" if n == 1 else PD.NUM_GEN[n]) if n <= 10 else str(n)
        return "%s %s" % (num, "egzekucji")
    if n == 1:
        return "jedną egzekucję" if case == "acc" else "jedna egzekucja"
    return "%s %s" % (PD.NUM_F[n] if n <= 10 else n, "egzekucje" if _few(n) else "egzekucji")


def hs_phrase(n, case):
    """headshots: 'jeden strzał w głowę', 'dwa strzały w głowę', 'pięć strzałów w głowę'; gen 'jednego strzału w głowę'."""
    if case == "gen":
        num = PD.NUM_GEN[n] if n <= 10 else str(n)
        return "%s %s" % (num, "strzału w głowę" if n == 1 else "strzałów w głowę")
    return count(n, "strzał w głowę", "strzały w głowę", "strzałów w głowę")


def unit_phrase(n, case):
    """units (feminine: jednostka): nom / acc / gen."""
    if case == "gen":
        return "%s jednostek" % (("jednej" if n == 1 else PD.NUM_GEN[n]) if n <= 10 else n) if n != 1 else "jednej jednostki"
    if n == 1:
        return "jedną jednostkę" if case == "acc" else "jedna jednostka"
    return "%s %s" % (PD.NUM_F[n] if n <= 10 else n, "jednostki" if _few(n) else "jednostek")


def ago(en):
    """'yesterday' / 'today' / 'three days ago' -> 'wczoraj' / 'dzisiaj' / 'trzy dni temu'."""
    if en == "yesterday":
        return "wczoraj"
    if en == "today":
        return "dzisiaj"
    n = _num(en.split(" ")[0])
    return "%s dni temu" % (PD.NUM_M[n] if n <= 10 else n)


def gone(en):
    """'gone since yesterday' / 'gone three days' -> 'od wczoraj' / 'od trzech dni'."""
    if "yesterday" in en:
        return "od wczoraj"
    n = _num(en.split(" ")[1])
    return "od %s dni" % (PD.NUM_GEN[n] if n <= 10 else n)


def losses(en):
    n = _num(en)
    return "%s %s" % (PD.NUM_F[n] if n <= 10 else n, "porażki" if _few(n) else "porażek")


def _put(out, src, key, val, en):
    out[key] = val
    src[key] = en


def _acc(nom):
    if nom in PD.ACC:
        return PD.ACC[nom]
    if nom.startswith("mapa "):
        return "mapę " + nom[5:]
    return nom


def _group(out, src, pre, spec, en):
    """(nom, gen, prep, loc, ins) -> pre pre_gen pre_loc pre_at pre_to pre_from pre_ins."""
    nom, gen, prep, loc, ins = spec
    _put(out, src, pre, nom, en)
    _put(out, src, pre + "_gen", gen, en)
    _put(out, src, pre + "_acc", _acc(nom), en)
    _put(out, src, pre + "_loc", loc, en)
    _put(out, src, pre + "_at", _prep(prep, loc) + " " + loc, en)
    _put(out, src, pre + "_to", "do " + gen, en)
    _put(out, src, pre + "_from", _from(gen), en)
    _put(out, src, pre + "_ins", ins, en)


def _map_spec(val):
    """EN 'the Hospital' / 'Downtown' / a fallback place -> the Polish group."""
    name = val[4:] if val.startswith("the ") else val
    name = MAPN.EN_SHORT.get(name, name)
    if name in PD.MAPS:
        return PD.MAPS[name]
    if val in PD.PLACES:
        return PD.PLACES[val]
    pl = MAPN.PL.get(name)
    if pl:
        return ("mapa " + pl, "mapy " + pl, "na", "mapie " + pl, "mapą " + pl)
    raise KeyError("no Polish map name for %r" % val)


def _sg(out, src, pre, spec, en, names):
    for nm, val in zip(names, spec):
        _put(out, src, pre + nm, val, en)


def expand(v, people=None, fk="W", over=None):
    """English variables of a saga entry -> (Polish variables, {Polish key: English key it comes from}).  KeyError for a value the tables do not know."""
    out, src = {}, {}
    people = people or {}
    for key, val in v.items():
        if val is None:
            continue
        if key in ("map", "prev_map", "kmap", "ymap"):
            _group(out, src, key, _map_spec(str(val)), key)
        elif key == "place_gen":
            continue                                 # an English variable no template uses; the name is the Polish genitive of {place} here
        elif key in ("place", "place2", "place3", "kplace"):
            _group(out, src, key, PD.PLACES[str(val)], key)
        elif key == "camp":
            _group(out, src, key, PD.CAMPS[str(val)], key)
        elif key == "leader":
            _sg(out, src, "leader", PD.LEADERS[str(val)], key, ("", "_gen", "_ins"))
        elif key in ("enemies", "enemy"):
            e = PD.ENEMIES[str(val) if str(val).startswith("the ") else "the " + str(val)]
            _sg(out, src, key, e[:5], key, ("", "_gen", "_ins", "_dat", "_loc"))
        elif key == "enemy_n":
            _put(out, src, "enemy_n", PD.ENEMIES["the " + ("Scars" if val == "Scar" else "Wolves")][5], key)
        elif key in ("smell", "sound", "air"):
            m = re.match(r"the (smell|sound) of (.*)$", str(val))
            noun = "zapach" if m.group(1) == "smell" else "dźwięk"
            g = PD.AIR[m.group(2)]
            _put(out, src, key, "%s %s" % (noun, g), key)
            _put(out, src, key + "_gen", "%s %s" % (noun + "u", g), key)
            _put(out, src, key + "_ins", "%s %s" % (noun + "em", g), key)
        elif key == "k":
            n = int(val)
            _put(out, src, "k", str(n), key)
            _put(out, src, "k_dn", "%d powalon%s" % (n, "y" if n == 1 else "ych"), key)
        elif key == "ex_p":
            n = _num(str(val).split(" ")[0])
            for c in ("nom", "acc", "gen"):
                _put(out, src, "ex_" + c, ex_phrase(n, c), key)
        elif key == "ex_t":
            n = _num(str(val).split(" ")[0]) if str(val)[0].isalpha() and str(val) not in ("once", "twice") else 0
            n = 1 if val == "once" else 2 if val == "twice" else n
            _put(out, src, "ex_t", times(n), key)
        elif key in ("dn_p", "dt_p"):
            n = 1 if val == "once" else 2 if val == "twice" else _num(str(val).split(" ")[0])
            _put(out, src, key, times(n), key)
        elif key == "rv_p":
            n = _num(str(val).split(" ")[0])
            for c in ("nom", "acc", "gen"):
                _put(out, src, "rv_" + c, PLN.people_phrase(n, c) + " z drużyny", key)
        elif key == "hs_p":
            n = _num(str(val).split(" ")[0])
            for c in ("nom", "acc", "gen"):
                _put(out, src, "hs_" + c, hs_phrase(n, "nom" if c == "acc" else c), key)
        elif key == "wpn":
            _sg(out, src, "wpn", PD.WEAPONS[str(val)], key, ("", "_acc", "_gen", "_ins"))
        elif key in ("site", "ysite", "dsite"):
            nom, gen, acc, loc, ins = PD.SITES[str(val)]
            _put(out, src, key, nom, key)
            _put(out, src, key + "_gen", gen, key)
            _put(out, src, key + "_from", _from(gen), key)
            _put(out, src, key + "_acc", acc, key)
            _put(out, src, key + "_w", "w " + acc, key)
            _put(out, src, key + "_loc", loc, key)
            _put(out, src, key + "_at", "na " + loc, key)
            _put(out, src, key + "_ins", ins, key)
        elif key in ("cloth", "dcloth"):
            _sg(out, src, key, PD.CLOTHS[str(val)], key, ("", "_gen", "_ins"))
        elif key == "cause":
            from clan_saga_data import CAUSES
            en_n = "Scar" if fk == "W" else "Wolf"
            idx = [c.format(enemy_n=en_n) for c in CAUSES].index(str(val))
            e = PD.ENEMIES["the Scars" if fk == "W" else "the Wolves"][5]
            acc, gen, ins = (x.format(e=e) for x in PD.CAUSES[idx])
            _put(out, src, "cause", acc, key)
            _put(out, src, "cause_acc", acc, key)
            _put(out, src, "cause_gen", gen, key)
            _put(out, src, "cause_ins", ins, key)
        elif key == "job":
            _sg(out, src, "job", PD.JOBS[str(val)], key, ("", "_neg"))
        elif key in ("poss", "dpos", "dposx"):
            _sg(out, src, key, PD.POSS[str(val)], key, ("", "_acc", "_gen", "_ins"))
        elif key == "poss_short":
            nom = None
            for en, spec in PD.POSS.items():
                if en.split(" ", 1)[-1] == str(val) or en == str(val):
                    nom = spec[0]
                    break
            _put(out, src, key, nom if nom is not None else str(val), key)
        elif key in ("kitem", "kitem_a"):
            k = str(val).split(" ", 1)[1] if str(val).split(" ", 1)[0] in ("a", "an") else str(val)
            _sg(out, src, key, PD.KEEPS[k], key, ("", "_acc", "_gen", "_ins"))
        elif key == "fear":
            _put(out, src, "fear", PD.FEARS[str(val)][0], key)
        elif key == "fear_what":
            _put(out, src, "fear_what", _fear_what()[str(val)], key)
        elif key == "past":
            g = (people.get("A") or {}).get("g", "m")
            pp = past_pl(val, g)
            if pp is None:
                raise KeyError("no Polish past for %r" % val)
            _put(out, src, "past", pp, key)
        elif key == "lack_n":
            n = _num(str(val).split(" ")[0])
            for c in ("nom", "acc", "gen"):
                _put(out, src, "lack_n" + ("" if c == "nom" else "_" + c), unit_phrase(n, c), key)
        elif key == "lack_days":
            n = _num(str(val).split(" ")[0])
            _put(out, src, key, count(n, "dzień", "dni", "dni"), key)
        elif key == "dgo":
            _put(out, src, "dgo", gone(str(val)), key)
        elif key in ("kd_ago", "ago"):
            _put(out, src, key, ago(str(val)), key)
        elif key == "nth":
            _put(out, src, "nth", PD.NTH[str(val)], key)
        elif key == "lossw":
            _put(out, src, "lossw", losses(str(val)), key)
        elif key == "prev_res":
            _put(out, src, "prev_res", PD.PREV_RES[str(val)], key)
        elif key == "n_left":
            _put(out, src, "n_left", "nic nie zostało" if str(val).startswith("none") else "zostało %s" % str(val).split(" ")[0], key)
        elif key == "ammo_n":
            _put(out, src, key, count(_num(str(val).split(" ")[0]), "nabój", "naboje", "naboi"), key)
        elif key == "food_n":
            _put(out, src, key, count(_num(str(val).split(" ")[0]), "puszka", "puszki", "puszek", fem=True), key)
        elif key in ("item_pl", "item_short"):
            nom, gen = _items()[str(val)]
            _put(out, src, key, nom, key)
            _put(out, src, key + "_gen", gen, key)
        elif key == "AW":
            g = (people.get("B") or {}).get("g", "m")
            fem = g == "f"
            _put(out, src, "AW", str(val), key)
            _put(out, src, "AW_go", "ją" if fem else "go", key)
            _put(out, src, "AW_niego", "nią" if fem else "niego", key)
            _put(out, src, "AW_mu", "jej" if fem else "mu", key)
            _put(out, src, "AW_jego", "jej" if fem else "jego", key)
        elif key in ("kd", "yd", "n", "day"):
            _put(out, src, key, str(val), key)
        else:
            _put(out, src, key, str(val), key)
    out.update(over or {})
    return out, src


_FW = {}
_IT = {}


def _fear_what():
    if not _FW:
        import clan_saga_data as SD
        for en, what in SD.FEARS:
            _FW[what] = PD.FEARS[en][1]
    return _FW


def _items():
    if not _IT:
        import clan_chronicle as CH
        for e in CH.USE.values():
            _IT[e[2]] = (e[5], e[6])
    return _IT


def past_pl(en_past, g):
    """The Polish past of a member in the right gender, from the chronicle's PASTS table (English text -> the m / f Polish pair)."""
    import clan_chronicle as CH
    for p in CH.PASTS:
        if p[2].lower() == str(en_past).lower():
            return p[4] if g == "f" else p[3]
    return None


# ------------------------------------------------------------------ the Polish template registry
def _flat(text):
    out, cur = [], None
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        if line.startswith("== "):
            cur = line[3:].strip()
            continue
        scope = "*"
        if line[:2] in ("W:", "S:"):
            scope, line = line[0], line[2:].strip()
        out.append((cur, scope, line))
    return out


def _build():
    import clan_saga_text as T1, clan_saga_text2 as T2, clan_saga_text3 as T3, clan_saga_text4 as T4, clan_saga_text_sup as T5
    import clan_saga_pl_text as P1, clan_saga_pl_text2 as P2, clan_saga_pl_text3 as P3, clan_saga_pl_text4 as P4, clan_saga_pl_text_sup as P5
    reg = {}
    for en_mod, pl_mod in ((T1, P1), (T2, P2), (T3, P3), (T4, P4), (T5, P5)):
        en, pl = _flat(en_mod.TEXT), _flat(pl_mod.TEXT)
        if len(en) != len(pl):
            raise ValueError("%s has %d lines, %s has %d" % (en_mod.__name__, len(en), pl_mod.__name__, len(pl)))
        for i, (e, p) in enumerate(zip(en, pl)):
            if e[0] != p[0] or e[1] != p[1]:
                raise ValueError("%s line %d: pool/scope %s/%s but the English has %s/%s: %s" % (pl_mod.__name__, i + 1, p[0], p[1], e[0], e[1], p[2][:50]))
            reg.setdefault((e[0], e[2]), p[2])
    return reg


REG = _build()


def template(pool, en_text):
    return REG[(pool, en_text)]


def render(tpl, people, vp):
    """Fill a Polish template (people = {"A": {"n","g"}}; vp = expand()'s dict)."""
    pp = {k: {"n": str(p["n"]), "g": p["g"] if p.get("g") in ("m", "f") else "n"} for k, p in people.items()}
    return PLN.render(tpl, pp, vp)


def fam_ok(pl_tpl, en_tpl, src):
    """Test helper: the English keys a Polish template needs must be a subset of those the English template needs (so the Polish line is eligible whenever the English is).
    Returns the offending keys."""
    en_keys = set(re.findall(r"\{(\w+)\}", en_tpl))
    en_keys |= {k for k in en_keys}
    bad = []
    for k in re.findall(r"\{(\w+)\}", pl_tpl):
        if re.fullmatch(r"[A-D]", k):
            if k not in en_keys and not re.search(r"\{%s_\w+\}" % k, en_tpl) and not _en_letters(en_tpl) >= {k}:
                bad.append(k)
            continue
        s = src.get(k, k)
        if s not in en_keys:
            bad.append(k)
    for m in PLN.SW_RE.finditer(pl_tpl):
        for ch in m.group(1):
            if ch not in _en_letters(en_tpl):
                bad.append(ch + "?")
    return bad


def _en_letters(tpl):
    return set(re.findall(r"\{([A-D])(?:_\w+)?\}", tpl))
