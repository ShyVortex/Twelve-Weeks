"""Which head a clan member gets: role- and age-aware choice from the head pool (tools/clan_portrait_pool.py, every usable TLOU2 head).
  kid -> kids (and teens), elder -> elders, medic -> doctors / nurses (WLF) or civilians (Seraphites have no doctor look), cook -> kitchen staff, guard -> soldiers,
  scout -> soldiers / Firefly / Duster, scavenger -> civilians / refugees / Rattler-types, mechanic -> gym / civilians / Rattlers, gardener -> civilians (elders welcome),
  radio -> civilians / soldiers.  A faction's own heads come first; neutral heads (Jackson, Rattlers, prisoners, Firefly) fit either side.
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


def candidates(role, sex, fk):
    """[(row, weight)] heads for the role, own faction heads weighted 3x over the neutral ones, never the other faction's."""
    out = []
    pref = PREF.get(role, _DEFAULT)
    for row in POOL:
        mid, look, fac, sx, age, tags, rig, tier = row
        if sx != sex or fac not in (fk, "N"):
            continue
        tg = set(tags.split("+"))
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


def _draw(cands, name, salt="head"):
    tot = sum(w for _, w in cands)
    x = _h(salt, name) % tot
    for row, w in cands:
        if x < w:
            return row[0]
        x -= w
    return cands[-1][0][0]


def pick(name, role, sex, fk, used=()):
    """The model id (pool row id) for a member, or None when the pool has no head for them (the caller uses the old hash).
    used = heads the earlier members already wear: the name's own pick stands unless it is in `used`; then another head of the role that nobody wears (still by the name's hash),
    then a head of the broad civilian pool nobody wears; only when the whole pool for that sex is taken the first pick is repeated (clan members repeated looks)."""
    cands = candidates(role, sex, fk) or candidates("scavenger" if role != "kid" else "kid", sex, fk)
    if not cands:
        return None
    first = _draw(cands, name)
    if first not in used:
        return first
    free = [(r, w) for r, w in cands if r[0] not in used]
    if free:
        return _draw(free, name, "head2")
    wide = candidates("scavenger" if role != "kid" else "kid", sex, fk)
    free = [(r, w) for r, w in wide if r[0] not in used]
    if free:
        return _draw(free, name, "head3")
    return first


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
