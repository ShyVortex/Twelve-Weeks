"""Clan loot model: what a raid really brings home - small findings, each a scene: WHO found it, WHERE exactly (place + micro-location), its CONDITION,
quantity and sometimes a tiny story hook.  Data: clan_loot_data.py (items), clan_loot_data2.py (places, conditions, hooks).  EN + PL.

It NEVER changes a clan number: the engine's supplies and clan_supply's categories stay as they are.  The findings are drawn from the day's real supplies:
  budget   = r["sup"]["got"] per supply group (food water med ammo mat; tools / clothing / fuel / weapon parts count as 'mat', seeds and animals as 'food'), each piece costs its
             'value' (clan_loot_data.ITEMS) - a find uses up the group's budget, so a rich day brings more and larger finds.  Without r["sup"] the groups are
             derived from the match (clan_supply.intake).  Trinkets and books cost nothing (morale finds).
  count    = 2 + supplies // 7 (+1 after a win), 2..6 findings per raid, groups short on supplies served first.

FORTUNE (momentum score in -1..+1) decides the TIER of the findings (0 scraps, 1 poor, 2 normal, 3 good, 4 luxurious):
  score = 0.45 * W + 0.35 * S + 0.20 * M          over the last 7 raids including this one
      W = mean of win +1 / loss -1 / unknown 0        (win / loss streak)
      S = mean of clamp((supplies - needed) / needed, -1, 1)      (supply balance)
      M = (clan morale - 50) / 50, clamped                          (morale before this raid's loot)
  base tier = 2 + round(2 * score)   (-1 -> 0 scraps ... 0 -> 2 normal ... +1 -> 4 luxurious);  every finding rolls its own tier: base (60 %), base - 1 (20 %), base + 1 (20 %).
  A clan doing badly finds scraps even after a win (its W is dragged down by the earlier losses); a clan on a streak finds a little luxury - still grounded: real items only.
  st["ch"]["fort"] = {"s": score, "d": day, "low": consecutive days with score < -0.3, "hi": consecutive days with score > 0.3}  (clan_status reads it: depression).
Affinity: an item belongs to place kinds (pharmacy, hospital, military, camp, rail, marine, house, school, shop, hardware, hotel, wild, office, farm); a map has kinds
(clan_loot_data2.MAP_KINDS); weight = 1 + 5 * (item has one of the map's kinds) (x2 for the map's first kind), 'any' items weight 2; rarity 1 -> x0.5, 2 -> x0.2.
Stored find (st["ch"]["log"][-1]["finds"] and the callbacks): {"k": item key, "n", "c": condition index or -1, "w": finder's name, "g": finder gender, "m": map, "kd": kind, "mi": micro
index, "pl": saga place or "", "h": hook index or -1, "ha": hook argument, "v": sentence variant, "t": tier, "d": day}.
"""
import math
import zlib

import clan_kids as KD
import clan_loot_data as D1
import clan_loot_data2 as D2

LAUNCHER_ICONS = frozenset("alcohol ammo arrow binding canister coins explosive food gasmask healthbar journal keepsake key killfeed-skull materials medicine molotov parts person "
                           "pills pipebomb pistolammo rag rifleammo scissors shiv shotgunammo water wrench".split())      # release/launcher/src/clan-icons.js
KEYS = ("key", "cat", "tier", "rar", "qmin", "qmax", "val", "kinds", "icon", "g", "en1", "enn", "pln", "pla", "plf", "plm")
ITEMS = {}
for _ln in D1.ITEMS.strip().splitlines():
    _f = _ln.split("|")
    if len(_f) != 15:
        raise ValueError("clan_loot_data row: %r" % _ln)
    _q = _f[4].split("-")
    ITEMS[_f[0]] = {"key": _f[0], "cat": _f[1], "tier": int(_f[2]), "rar": int(_f[3]), "qmin": int(_q[0]), "qmax": int(_q[1]), "val": int(_f[5]), "kinds": tuple(_f[6].split(",")),
                    "icon": _f[7], "g": _f[8], "en1": _f[9], "enn": _f[10], "pln": _f[11], "pla": _f[12], "plf": _f[13], "plm": _f[14]}
GROUP = D1.GROUP
TIERS = D1.TIERS
CONDS = D2.CONDS
GROUPS = ("food", "water", "med", "ammo", "mat")


def _h(*parts):
    return zlib.crc32("|".join(str(x) for x in parts).encode("utf-8")) & 0xFFFFFFFF


# ------------------------------------------------------------------ icons
def icon_wanted(key):
    return ITEMS[key]["icon"]


def icon_for(key):
    """The icon id to show: the item's own icon when the launcher has it, else its category's."""
    it = ITEMS[key]
    return it["icon"] if it["icon"] in LAUNCHER_ICONS else D1.FALLBACK_ICON[it["cat"]]


def missing_icons():
    """Icon ids the items would like that clan-icons.js lacks: {icon id: [item keys]}."""
    out = {}
    for k, it in ITEMS.items():
        if it["icon"] not in LAUNCHER_ICONS:
            out.setdefault(it["icon"], []).append(k)
    return out


# ------------------------------------------------------------------ phrases
def _art(w):
    return "an" if w[:1].lower() in "aeiou" else "a"


def _adj_forms(adj):
    s = adj[:-1]
    return {"m": adj, "f": s + "ą", "n": s + "e", "few": s + "e", "many": s + "ych"}


def _plural_kind(n):
    few = 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14
    return "few" if few else "many"


def item_phrase(key, n, cond=-1, lang="en"):
    """'3 rusted cans of pineapple' / 'zardzewiałą puszkę ananasa' (accusative, the object of 'found')."""
    it = ITEMS[key]
    n = max(1, int(n))
    if it["enn"] == "-":
        n = 1
    c = CONDS[cond] if 0 <= cond < len(CONDS) else None
    if lang == "pl":
        if n == 1:
            noun, ad = it["pla"], "m" if it["g"] != "f" and it["g"] != "n" else it["g"]
        else:
            k = _plural_kind(n)
            noun, ad = (it["plf"] if k == "few" else it["plm"]), k
        pre = "%s%s " % (c[1], _adj_forms(c[2])[ad]) if c else ""
        return ("%d " % n if n > 1 else "") + pre + noun
    if n == 1:
        word = (c[0] + " " if c else "") + it["en1"]
        return "%s %s" % (_art(word), word)
    return "%d %s%s" % (n, (c[0] + " ") if c else "", it["enn"])


def noun_phrase(key, lang="en"):
    """The bare name of the item (singular, nominative; EN with a/an)."""
    it = ITEMS[key]
    return it["pln"] if lang == "pl" else "%s %s" % (_art(it["en1"]), it["en1"])


def join_list(items, lang):
    if len(items) <= 1:
        return "".join(items)
    return ", ".join(items[:-1]) + (" i " if lang == "pl" else " and ") + items[-1]


def _cap(s):
    return s[:1].upper() + s[1:]


# ------------------------------------------------------------------ fortune
def fortune(st, cs, hist=None):
    """Momentum score -1..+1 of the clan (module doc); updates cs["fort"] once per day.  `hist` = raid log entries (default cs["log"])."""
    log = (hist if hist is not None else cs.get("log", []))[-7:]
    day = int(st.get("day", 0) or 0)
    fo = cs.setdefault("fort", {"s": 0.0, "d": -1, "low": 0, "hi": 0})
    if not log:
        return float(fo.get("s", 0.0))
    W = sum(1 if e.get("win") is True else -1 if e.get("win") is False else 0 for e in log) / float(len(log))
    S = sum(max(-1.0, min(1.0, (int(e.get("sup", 0)) - int(e.get("need", 0))) / float(max(1, int(e.get("need", 0)))))) for e in log) / float(len(log))
    M = max(-1.0, min(1.0, (int(st.get("morale", 50)) - 50) / 50.0))
    score = round(0.45 * W + 0.35 * S + 0.20 * M, 3)
    if fo.get("d") != day:
        fo["low"] = fo["low"] + 1 if score < -0.3 else 0
        fo["hi"] = fo["hi"] + 1 if score > 0.3 else 0
        fo["d"] = day
    fo["s"] = score
    return score


def base_tier(score):
    return max(0, min(4, 2 + int(round(2 * score))))


def roll_tier(rng, base):
    r = rng.random()
    t = base if r < 0.6 else base - 1 if r < 0.8 else base + 1
    return max(0, min(4, t))


DEP_AT = 4


def update_moods(st, cs):
    """Depression counters (module doc of clan_status): once per day.  A hungry or grieving member of a clan with fortune < -0.3 for 2+ days gets +1; a day with fortune > 0 gives -2
    (and marks the way back: rec); 4+ = depressed (clan_status.DEPRESSED).  Dead members' counters are dropped.  Returns {member id: counter}."""
    day = int(st.get("day", 0) or 0)
    fo = cs.setdefault("fort", {"s": 0.0, "d": -1, "low": 0, "hi": 0})
    dep = cs.setdefault("dep", {})
    alive = {str(p["i"]) for p in st.get("people", [])}
    for k in [k for k in dep if k not in alive]:
        del dep[k]
    mem = cs.get("mem") or {}
    for p in st.get("people", []):
        e = dep.setdefault(str(p["i"]), {"n": 0, "d": -1, "up": -1, "rec": False})
        if e["d"] == day:
            continue
        e["d"] = day
        g = (mem.get(str(p["i"])) or {}).get("grief")
        bad = p.get("s") == "u" or bool(g and int(g.get("until", -1)) >= day)
        if fo.get("low", 0) >= 2 and (bad or e["n"] > 0) and fo.get("s", 0) < -0.3:
            e["n"] += 1
            e["rec"] = False
        elif fo.get("s", 0) > 0.0 and e["n"] > 0:
            prev = e["n"]
            e["n"] = max(0, e["n"] - 2)
            e["rec"] = e["n"] > 0
            if prev >= DEP_AT and e["n"] < DEP_AT:
                e["up"] = day
    return {k: v["n"] for k, v in dep.items()}


# ------------------------------------------------------------------ choosing
def kinds_of(mapname):
    import clan_chronicle_maps as MAPN
    en = MAPN.EN_SHORT.get(str(mapname or ""), str(mapname or ""))
    return D2.MAP_KINDS.get(en, D2.GENERIC_KINDS)


def affinity(it, mk):
    if "*" in it["kinds"]:
        return 2.0
    w = 0.2
    for i, k in enumerate(mk):
        if k in it["kinds"]:
            w += 5.0 * (2.0 if i == 0 else 1.0)
    return w


def candidates(cats, tier, mk, rar_ok=2, avoid=()):
    """Items of the categories at the nearest tier that has any (tier, tier-1, tier+1, ...), with their weights.  When the nearest tier has nothing that belongs to the map
    (best weight below 1), a tier one step away that does is preferred (no 9mm boxes in the Seraphite smokehouse)."""
    fallback = None
    for dt in (0, -1, 1, -2, 2, -3, 3, -4, 4):
        t = tier + dt
        if not 0 <= t <= 4:
            continue
        pool = [it for it in ITEMS.values() if it["cat"] in cats and it["tier"] == t and it["rar"] <= rar_ok]
        if not pool:
            continue
        ws = [affinity(it, mk) * (1.0, 0.5, 0.2)[it["rar"]] * (0.15 if it["key"] in avoid else 1.0) for it in pool]
        if fallback is None:
            fallback = (pool, ws)
        if max(ws) >= 1.0:
            return pool, ws
        if abs(dt) >= 2:
            break
    return fallback or ([], [])


def form_of(it):
    """What the thing is made of / how it is kept (clan_loot_data2.CAT_FORM / FORM_OF)."""
    return D2.FORM_OF.get(it["key"]) or D2.CAT_FORM[it["cat"]]


def cond_ok(it, ci):
    """May this item have condition CONDS[ci]?  By category, by form (rusted = metal, sealed = packaged, half-full = bottles / cans / jars ...) and the item's own bans."""
    c = CONDS[ci]
    if it["key"] in D2.NO_COND or c[0] in D2.COND_BAN.get(it["key"], ()):
        return False
    if not (c[4] == "*" or it["cat"] in c[4]):
        return False
    if form_of(it) not in D2.COND_FORMS.get(c[0], ()):
        return False
    return c[0] != "fully stocked" or it["key"] in ("firstaid", "trauma")


def hook_ok(it, hi):
    """May story hook HOOKS[hi] be told about this item (a name is scratched only on metal / wood / plastic, written only on a label, a note goes in a container ...)?"""
    forms = D2.HOOK_FORMS[hi] if hi < len(D2.HOOK_FORMS) else None
    return forms is None or form_of(it) in forms


def pick_cond(rng, it, tier):
    cs_ = [i for i in range(len(CONDS)) if cond_ok(it, i)]
    if not cs_ or rng.random() > 0.72:
        return -1
    wq = {0: {-1: 3, 0: 1, 1: 0.2}, 1: {-1: 2, 0: 1.5, 1: 0.5}, 2: {-1: 1, 0: 1.5, 1: 1}, 3: {-1: 0.4, 0: 1, 1: 2}, 4: {-1: 0.1, 0: 0.6, 1: 3}}[tier]
    return rng.choices(cs_, weights=[wq[CONDS[i][3]] for i in cs_])[0]


def pick_member(rng, st, it, lo=None, day=0):
    """The finder, weighted by role fit (cook for food, medic for medicine, guard / scout for ammo, mechanic for materials, kids for toys and books) AND recency (whoever has not
    found anything for longer is likelier), and never the same member twice in one raid (lo["raid"]) while the roster allows it."""
    ppl = list(st.get("people", []))
    ppl = [p for p in ppl if KD.can_fight(p)]                       # kids never go on the raid: grown people find the loot (a clan of only kids has no raid: "someone")
    if not ppl:
        return "", "n"
    want = {"food": ("cook", "scavenger"), "seed": ("cook", "scavenger"), "anim": ("cook", "scavenger"), "water": ("cook", "scavenger"), "med": ("medic",),
            "ammo": ("guard", "scout"), "mat": ("mechanic", "scavenger"), "tool": ("mechanic", "scavenger"), "part": ("mechanic", "guard"), "cloth": ("scavenger",),
            "fuel": ("mechanic", "scavenger"), "trink": ("kid", "scavenger"), "book": ("kid", "scavenger")}.get(it["cat"], ())
    lo = lo if lo is not None else {}
    taken = set(lo.get("raid", ()))
    pool = [p for p in ppl if p["n"] not in taken] or ppl
    last = lo.get("finders", {})
    ws = []
    for p in pool:
        fit = 3.0 if p.get("r") in want else 1.0
        if p.get("r") == "kid" and it["cat"] not in ("trink", "book"):
            fit = 0.25
        gap = min(12, max(0, day - last.get(p["n"], day - 12)))
        ws.append(fit * (0.4 + gap / 4.0))
    p = rng.choices(pool, weights=ws)[0]
    lo.setdefault("raid", []).append(p["n"])
    lo.setdefault("finders", {})[p["n"]] = day
    return p["n"], p.get("g", "n")


def place_for(rng, mapname):
    try:
        import clan_saga_data as SD
        import clan_chronicle_maps as MAPN
        en = MAPN.EN_SHORT.get(str(mapname or ""), str(mapname or ""))
        pl = SD.MAPS.get(en, SD.GENERIC)["places"]
        return rng.choice(pl)
    except Exception:                                               # noqa: BLE001
        return ""


def budget_of(r, match):
    """Supplies per group of this raid: r["sup"]["got"], else derived from the engine's supplies and the match (clan_supply.intake)."""
    sp = (r or {}).get("sup")
    if isinstance(sp, dict) and isinstance(sp.get("got"), dict):
        return {g: max(0, int(sp["got"].get(g, 0))) for g in GROUPS}, {g: max(0, int((sp.get("short") or {}).get(g, 0))) for g in GROUPS}
    import clan_supply
    c = {1: int((match or {}).get("kills") or 0), 2: int((match or {}).get("execs") or 0), 3: int((match or {}).get("revives") or 0),
         4: int((match or {}).get("headshots") or 0), 21: int((match or {}).get("downs") or 0)}
    got = clan_supply.intake(int((r or {}).get("supplies", 0)), int((r or {}).get("parts", 0)), c, bool((r or {}).get("left")))
    return {g: int(got.get(g, 0)) for g in GROUPS}, {g: 0 for g in GROUPS}


CATS_OF = {"food": (("food", 8), ("seed", 1), ("anim", 1)), "water": (("water", 1),), "med": (("med", 1),), "ammo": (("ammo", 1),),
           "mat": (("mat", 3), ("tool", 3), ("part", 1), ("fuel", 1), ("cloth", 1))}
STALE_DAYS = 14


def _recent(cs):
    lo = cs.setdefault("loot", {})
    lo.setdefault("recent", [])
    lo.setdefault("seen", {})
    lo.setdefault("leads", [])
    return lo


def _make(rng, st, cs, it, tier, mapname, kind_hint, day, avoid_sent):
    """One finding record of item `it` (quantity chosen by the caller in 'n' later)."""
    f = {"k": it["key"], "n": 1, "c": pick_cond(rng, it, tier), "m": str(mapname), "t": it["tier"], "d": day}
    f["w"], f["g"] = "", "n"                                       # the finder is chosen once the raid's findings are final (roll_finds)
    mk = kinds_of(mapname)
    own = [k for k in mk if k in it["kinds"] or "*" in it["kinds"]]
    kd = rng.choice(own or list(mk))
    f["kd"] = kd
    f["mi"] = rng.randrange(len(D2.MICRO[kd]))
    f["pl"] = place_for(rng, mapname) if rng.random() < 0.5 else ""
    f["v"] = rng.randrange(4)
    f["h"], f["ha"] = -1, 0
    if rng.random() < 0.33:
        ok = [hi for hi in range(len(D2.HOOKS)) if hook_ok(it, hi)]
        f["h"] = rng.choice(ok)
        f["ha"] = rng.randrange(1000)
    return f


def _sent_key(f):
    return render_find(f, "en")


def _unique(f, seen):
    """Change the sentence variant / micro-location until the finding's sentence is not one told in the last 14 days (a few tries)."""
    for i in range(10):
        if _sent_key(f) not in seen:
            return f
        if i % 2 == 0:
            f["v"] = (f["v"] + 1) % 4
        else:
            f["mi"] = (f["mi"] + 1) % len(D2.MICRO[f["kd"]])
    return f


def roll_finds(rng, st, cs, r, match, score=None, day=None, left=False):
    """The findings of one raid (module doc).  Updates cs["loot"] (recent items, sentence memory, safe leads) and returns the list of stored find dicts."""
    day = int(day if day is not None else st.get("day", 0) or 0)
    mapname = str((match or {}).get("map") or "")
    if not mapname or left or (r or {}).get("left"):
        return []
    lo = _recent(cs)
    score = fortune(st, cs) if score is None else score
    base = base_tier(score)
    got, short = budget_of(r, match)
    sup = int((r or {}).get("supplies", 0))
    total = max(2, min(6, 2 + sup // 7 + (1 if (match or {}).get("win") else 0)))
    lo["recent"] = [x for x in lo["recent"] if day - x[1] <= STALE_DAYS]
    lo["raid"] = []
    for n_ in [n_ for n_, d_ in lo.setdefault("finders", {}).items() if day - d_ > 40]:
        del lo["finders"][n_]
    avoid = {x[0] for x in lo["recent"]}
    mk = kinds_of(mapname)
    out, used = [], set()
    groups = sorted((g for g in GROUPS if got.get(g, 0) > 0), key=lambda g: (-short.get(g, 0), -got[g], g))
    if not groups:
        groups = ["food", "mat"]                                      # a day with nothing counted still brings a scrap or two home
        got = dict(got, food=1, mat=1)
    left_ = dict(got)
    for g in groups * 2:
        if len(out) >= total:
            break
        if left_.get(g, 0) <= 0 or sum(1 for f in out if GROUP[ITEMS[f["k"]]["cat"]] == g) >= 2:
            continue
        cats = CATS_OF[g]
        t0 = roll_tier(rng, base)
        okc = [(c, w) for c, w in cats if any(abs(it["tier"] - t0) <= 1 and it["cat"] == c for it in ITEMS.values())] or list(cats)     # (no hens for a clan on scraps)
        cat = rng.choices([c for c, _w in okc], weights=[w for _c, w in okc])[0]
        for _try in range(8):
            tier = t0 if _try == 0 else roll_tier(rng, base)
            pool, ws = candidates((cat,), tier, mk, 1, avoid | used)
            if not pool:
                pool, ws = candidates((cat,), tier, mk, 2, avoid | used)
            it = rng.choices(pool, weights=ws)[0]
            f = _make(rng, st, cs, it, tier, mapname, None, day, None)
            qmax = max(it["qmin"], min(it["qmax"], int(math.ceil(left_[g] / float(max(1, it["val"]))))))
            f["n"] = rng.randint(it["qmin"], qmax) if it["enn"] != "-" else 1
            s = _sent_key(f)
            if s not in lo["seen"] and it["key"] not in used:
                break
            f["v"] = (f["v"] + 1) % 4
            s = _sent_key(f)
            if s not in lo["seen"] and it["key"] not in used:
                break
        left_[g] = max(0, left_[g] - f["n"] * max(1, it["val"]))
        used.add(it["key"])
        out.append(f)
    # morale finds: a trinket or a book
    if len(out) < 6 and rng.random() < 0.55:
        cat = "trink" if rng.random() < 0.7 else "book"
        tier = roll_tier(rng, base)
        pool, ws = candidates((cat,), tier, mk, 1, avoid | used)
        if pool:
            it = rng.choices(pool, weights=ws)[0]
            f = _make(rng, st, cs, it, tier, mapname, None, day, None)
            f["n"] = rng.randint(it["qmin"], max(it["qmin"], min(it["qmax"], 2))) if it["enn"] != "-" else 1
            out.append(f)
            used.add(it["key"])
    while len(out) < 2:                                               # never fewer than two findings: a small thing or two
        cat = rng.choice(("trink", "book", "mat"))
        pool, ws = candidates((cat,), roll_tier(rng, min(base, 1)), mk, 1, avoid | used)
        it = rng.choices(pool, weights=ws)[0]
        f = _make(rng, st, cs, it, it["tier"], mapname, None, day, None)
        f["n"] = rng.randint(it["qmin"], max(it["qmin"], min(it["qmax"], 2))) if it["enn"] != "-" else 1
        out.append(f)
        used.add(it["key"])
    # a rare find now and then (more often on a good streak)
    if rng.random() < 0.05 + (0.10 if score > 0.4 else 0.0) and len(out) < 7:
        pool = [it for it in ITEMS.values() if it["rar"] == 2 and it["key"] not in used and abs(it["tier"] - base) <= 1]
        if pool:
            it = rng.choices(pool, weights=[affinity(x, mk) for x in pool])[0]
            f = _make(rng, st, cs, it, it["tier"], mapname, None, day, None)
            f["n"] = 1
            f["rare"] = 1
            out.append(f)
    # a safe seen on an earlier day opens now
    leads = [x for x in lo["leads"] if 0 < day - x["d"] <= 12]
    lo["leads"] = leads[1:] if leads else []
    if leads:
        pool, ws = candidates(("trink", "med", "ammo", "tool", "food"), max(3, base), mk, 2, used)
        it = rng.choices(pool, weights=ws)[0]
        f = _make(rng, st, cs, it, 3, mapname, None, day, None)
        f["n"] = 1
        f["h"], f["ha"] = -2, leads[0]["d"]
        f["kd"], f["mi"] = "of", 2
        out.append(f)
    # the finders: role fit x recency, nobody twice in a raid; then every sentence is made unique
    for f in out:
        f["w"], f["g"] = pick_member(rng, st, ITEMS[f["k"]], lo, day)
        _unique(f, lo["seen"])
    # bookkeeping
    for f in out:
        lo["recent"].append([f["k"], day])
        lo["seen"][_sent_key(f)] = day
        if f["h"] >= 0 and D2.HOOKS[f["h"]][2] == "lead":
            lo["leads"].append({"d": day, "m": mapname})
    for s in [s for s, d in lo["seen"].items() if day - d > STALE_DAYS]:
        del lo["seen"][s]
    del lo["recent"][:-60]
    del lo["leads"][:-3]
    return out


# ------------------------------------------------------------------ rendering
def _hook_text(f, lang):
    if f.get("h", -1) == -2:
        return ("The combination from day %d opened a safe." if lang == "en" else "Kombinacja z dnia %d otworzyła sejf.") % f.get("ha", 0)
    if f.get("h", -1) < 0:
        return ""
    en, pl, _flag = D2.HOOKS[f["h"]]
    h = f.get("ha", 0)
    d = {"name": D2.NAMES[h % len(D2.NAMES)], "combo": "%d-%d-%d" % (h % 40 + 1, (h // 7) % 40 + 1, (h // 11) % 40 + 1),
         "note": D2.NOTES[h % len(D2.NOTES)][0 if lang == "en" else 1]}
    return (en if lang == "en" else pl).format(**d)


def loc_phrase(f, lang="en", with_place=True):
    """'in the baggage cage, near the platform' / 'w klatce bagażowej, w pobliżu peronu'."""
    en, pl = D2.MICRO[f["kd"]][f["mi"] % len(D2.MICRO[f["kd"]])]
    txt = en if lang == "en" else pl
    if with_place and f.get("pl"):
        if lang == "en":
            txt += ", near " + f["pl"]
        else:
            try:
                import clan_saga_pl_data as PD
                txt += ", w pobliżu " + PD.PLACES[f["pl"]][1]
            except Exception:                                       # noqa: BLE001
                pass
    return txt


def render_find(f, lang="en", hook=True):
    """The finding as a small scene: the sentence (4 variants) + the story hook."""
    it = ITEMS[f["k"]]
    ph = item_phrase(f["k"], f["n"], f.get("c", -1), lang)
    loc = loc_phrase(f, lang, f.get("v", 0) % 4 == 0)
    who = f.get("w") or ("Ktoś" if lang == "pl" else "Someone")
    if lang == "pl":
        s = D2.SENT_PL[f.get("v", 0) % 4].format(who=who, item=ph, loc=loc, Loc=_cap(loc), a="a" if f.get("g") == "f" else "", natknal="natknęła" if f.get("g") == "f" else "natknął")
    else:
        s = D2.SENT_EN[f.get("v", 0) % 4].format(who=who, item=ph, loc=loc, Loc=_cap(loc))
    if hook:
        h = _hook_text(f, lang)
        if h:
            s += " " + h
        elif f.get("rare"):
            s += " " + ("Nobody in the camp has seen one in years." if lang == "en" else "Nikt w obozie nie widział takiego od lat.")
    return s


def items_text(finds, lang="en"):
    """'3 cans of pineapple, a sealed pack of antibiotics and a deck of cards' (the RAIDS 'brought home' list)."""
    return join_list([item_phrase(f["k"], f["n"], f.get("c", -1), lang) for f in finds], lang)


def public(finds, lang="en"):
    """The launcher / game view of the findings: a list of dicts with the icon id."""
    out = []
    for f in finds or []:
        if f.get("k") not in ITEMS:
            continue
        it = ITEMS[f["k"]]
        out.append({"k": f["k"], "n": f["n"], "icon": icon_for(f["k"]), "icon_want": it["icon"], "cat": it["cat"], "tier": f.get("t", it["tier"]), "tier_name": TIERS[it["tier"]],
                    "item": item_phrase(f["k"], f["n"], f.get("c", -1), lang), "text": render_find(f, lang), "who": f.get("w", ""), "where": loc_phrase(f, lang, False),
                    "rare": bool(f.get("rare")) or it["rar"] >= 2, "keep": it["cat"] in ("trink", "book")})
    return out


def supply_value(finds):
    """What the findings are worth per supply group (clan_supply categories): {food, water, med, ammo, mat} (units)."""
    out = {g: 0 for g in GROUPS}
    for f in finds or []:
        it = ITEMS[f["k"]]
        g = GROUP[it["cat"]]
        if g:
            out[g] += f["n"] * it["val"]
    return out


def keepsakes(finds):
    """Findings that become keepsakes of the clan (trinkets / books): the saga calls them back later."""
    return [f for f in finds or [] if ITEMS[f["k"]]["cat"] in ("trink", "book")]


def finds_story(finds, lang="en", limit=2):
    """The first `limit` findings as sentences for a saga entry."""
    return " ".join(render_find(f, lang, hook=(i == 0)) for i, f in enumerate((finds or [])[:limit]))


# the chronicle's older goods (clan_chronicle.USE / KEEP keys): same key, or the new item that stands for the old keepsake
_OLD_KEEP = {"chess": "chess", "guitar": "guitar", "comic": "comic", "teddy": "teddy", "deck": "cards", "harmonica": "harmonica", "mixedseed": "seeds"}


def legacy_loot(finds, have=()):
    """The findings as the chronicle's old [[key, n]] loot list (practical goods by their key, keepsakes by the old keepsake key): feeds st["ch"]["inv"] / ["keep"]."""
    import clan_chronicle as CH
    out, seen = [], set()
    for f in finds or []:
        k = f["k"]
        if k in _OLD_KEEP:
            k, n = _OLD_KEEP[k], 1
            if k in have:
                continue                                              # the clan owns that keepsake already (the chronicle's keepsake lines tell it once)
        elif k in CH.USE:
            n = f["n"]
        else:
            continue
        if k not in seen:
            seen.add(k)
            out.append([k, int(n)])
    return out
