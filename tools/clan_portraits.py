"""Which head a clan member gets: role- and age-aware choice from the head pool (tools/clan_portrait_pool.py, every usable TLOU2 head).
  kid -> kids (and teens), elder -> elders, medic -> doctors / nurses (WLF) or civilians (Seraphites have no doctor look), cook -> kitchen staff, guard -> soldiers,
  scout -> soldiers / Firefly / Duster, scavenger -> civilians / refugees / Rattler-types, mechanic -> gym / civilians / Rattlers, gardener -> civilians (elders welcome),
 radio -> civilians / soldiers. Faction-locked: a WLF clan wears WLF heads only, a Seraphite clan Seraphite heads only; the neutral rows of the pool
  (Jackson, Rattlers, prisoners, Firefly, Duster: faction N) are never picked.
Switch: T2R_PORTRAIT_POOL=0 (or tools/clan_portrait_pool.txt = 0) goes back to the old name-hash model 0..3 of clan_chronicle.PORTRAIT_MODELS. Pure data + hash, no I/O besides the switch.
A pick is stable for a name (same name -> same head)."""
import os
import zlib

HERE = os.path.dirname(os.path.abspath(__file__))
try:
    from clan_portrait_pool import POOL, RENDERED, EXPR
except ImportError:                                              # tools dir not on the path
    import sys
    sys.path.insert(0, HERE)
    from clan_portrait_pool import POOL, RENDERED, EXPR

# role -> ordered preference of (tag, weight) groups; adults only unless the tag says otherwise
PREF = {
    "kid": (("kid", 7), ("teen", 3)),
    "elder": (("elder", 8), ("civilian", 2)),
    "medic": (("medic", 8), ("patient", 1), ("civilian", 2)),
    "cook": (("kitchen", 8), ("civilian", 2)),
    "guard": (("soldier", 8), ("gym", 1), ("raider", 1)),
    "scout": (("soldier", 5), ("scout", 4), ("raider", 1)),
    "scavenger": (("civilian", 5), ("refugee", 2), ("raider", 2), ("soldier", 1)),
    "mechanic": (("gym", 3), ("civilian", 4), ("raider", 2), ("soldier", 1)),
    "gardener": (("civilian", 8), ("elder", 2)),
    "radio": (("civilian", 5), ("soldier", 3), ("scout", 2)),
}
_DEFAULT = (("civilian", 5), ("soldier", 3), ("gym", 1), ("refugee", 1))
_ELDER_OK = ("elder", "gardener", "cook", "radio", "medic")       # roles that may take an elder head by the normal pool


def enabled():
    v = os.environ.get("T2R_PORTRAIT_POOL")
    if v is None:
        try:
            v = open(os.path.join(HERE, "clan_portrait_pool.txt")).read().strip()
        except OSError:
            v = "1"
    return v.strip() not in ("0", "off", "no")


def _h(*parts):
    return zlib.crc32("|".join(str(x) for x in parts).encode("utf-8")) & 0xFFFFFFFF


def _cands(role, sex, fk, sides, sera_civ=False):
    """[(row, weight)] heads of the role among the factions `sides`, own faction weighted 3x.
    sera_civ: the Seraphite raincoat heads also count as civilians (the pool has no Seraphite villager head; without this a Seraphite cook /
    medic / gardener fell back to the bloodied prisoner faces)."""
    out = []
    pref = PREF.get(role, _DEFAULT)
    for row in POOL:
        mid, look, fac, sx, age, tags, rig, tier = row
        if sx != sex or fac not in sides:
            continue
        tg = set(tags.split("+"))
        if sera_civ and fac == "S" and "soldier" in tg:
            tg.add("civilian")
        w = 0
        for tag, wt in pref:
            if tag in tg:
                w = max(w, wt)
        if not w:
            continue
        if role not in _ELDER_OK and "elder" in tg:
            continue
        if role != "kid" and ("kid" in tg or "teen" in tg):
            continue
        if role == "kid" and "kid" not in tg and "teen" not in tg:
            continue
        out.append((row, w * (3 if fac == fk else 1)))
    shown = [x for x in out if x[0][0] in RENDERED]               # a head with a neutral render first: every member gets a picture (none rendered for this role / sex: the silhouette)
    return shown or out


def candidates(role, sex, fk):
    """[(row, weight)] heads for the role, the clan's own faction only (a Seraphite clan had a WLF-looking member)."""
    return _cands(role, sex, fk, (fk,), sera_civ=True)


def _legacy(role, sex, fk):
    """The earlier candidate list (own faction + the neutral rows): only to keep the head a member already wore when it is of the clan's faction."""
    return _cands(role, sex, fk, (fk, "N"))


def _draw(cands, name, salt="head"):
    tot = sum(w for _, w in cands)
    x = _h(salt, name) % tot
    for row, w in cands:
        if x < w:
            return row[0]
        x -= w
    return cands[-1][0][0]


def _pick(name, role, sex, fk, used, cand):
    cands = cand(role, sex, fk) or cand("scavenger" if role != "kid" else "kid", sex, fk)
    if not cands:
        return None
    first = _draw(cands, name)
    if first not in used:
        return first
    free = [(r, w) for r, w in cands if r[0] not in used]
    if free:
        return _draw(free, name, "head2")
    wide = cand("scavenger" if role != "kid" else "kid", sex, fk)
    free = [(r, w) for r, w in wide if r[0] not in used]
    if free:
        return _draw(free, name, "head3")
    return first


def faction_of(model):
    for row in POOL:
        if row[0] == model:
            return row[2]
    return None


def pick(name, role, sex, fk, used=()):
    """The model id (pool row id) for a member, or None when the pool has no head for them (the caller uses the old hash).
    used = heads the earlier members already wear: the name's own pick stands unless it is in `used`; then another head of the role that nobody wears (still by the name's hash),
 then a head of the broad civilian pool nobody wears; only when the whole pool for that sex is taken the first pick is repeated (clan members repeated looks).
 Faction lock with no face churn: the pick the old rule gives is kept when it is of the clan's own faction, so only the members who wore a neutral head
    (Jackson / Rattler / prisoner / Firefly) move, to a head of their clan's faction; nothing is stored, the save keeps name, role and state as they are."""
    old = _pick(name, role, sex, fk, used, _legacy)
    if old is not None and faction_of(old) == fk:
        return old
    new = _pick(name, role, sex, fk, used, candidates)
    return new if new is not None else (old if fk not in ("W", "S") else None)


def look_of(model):
    for row in POOL:
        if row[0] == model:
            return row[1]
    return None


# an expression a head does not have -> its stand-in (approved set: neutral happy sad hungry sick depressed dead; shock and perk are out), then neutral
STAND_IN = {"hurt": "sad", "scared": "sad", "shock": "sad", "perk": "neutral", "injured": "sick", "grieving": "sad"}


def expr_for(model, want):
    have = EXPR.get(model, ())
    if want in have:
        return want
    alt = STAND_IN.get(want, "neutral")
    return alt if alt in have else "neutral"
