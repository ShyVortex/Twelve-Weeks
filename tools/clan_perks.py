"""Clan supply perks: a category's SURPLUS in the clan stock (tools/clan_supply.py, meta["sup"]["stock"]) grants a small passive perk for the
clan's player in every match, credited to the member who brought most of that category.  Spec: re/clan-supply-boosters.md.

  perk      surplus of     what the ext does (tools/ext/clanperk.c)                           per-match cap
  medkit    medicine       a free health kit on every 2nd respawn                              2
  clip      ammo           +1 reserve clip of the primary on a spawn                           3
  parts     materials      a free rag + alcohol (one crafting set) on every 2nd spawn from the 1st   2
  stamina   food           Marathon Runner I sprint recovery (regen x1.15, delay x0.85)        1 draw (when the meter first empties)
  bleed     water          Fortitude I bleed-out time x1.25                                    2 draws (each time it stretches a bleed-out)

  surplus   = stock - RESERVE_DAYS * need of that category (one day always stays in the larder); a perk is active while surplus >= 1, its cap is min(CAP, surplus).
  use       = the ext reports the uses in the match report (op 0xE2 labels 31 / 32, nibbles); clan_finalize draws 1 from the stock per use (floor 0) and the
              saga gets a line ("Tyler's antibiotics kept you on your feet at Hillside").  Shortages have no combat penalty: the perk is simply absent.
  credit    = st["ch"]["pk"]["cr"][cat][member id] += what the day brought in that category (the member is picked by role, deterministic per day); the most credited
              living member is the one named on the card.  Without any credit yet: the role's first living member.
Nothing here changes a clan number or a person's state; every failure is swallowed by the caller."""
import json
import os
import re
import sys
import zlib

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import clan                                                  # noqa: E402
import clan_supply as SUP                                    # noqa: E402
import clan_kids as KD                                      # noqa: E402

# cat -> wire id (the ext's CP_* enum), perk key, per-match cap, roles that bring it
PERKS = (("med", 1, "medkit", 2, ("medic", "elder")),
         ("ammo", 2, "clip", 3, ("scout", "guard")),
         ("mat", 3, "parts", 2, ("mechanic", "scavenger")),
         ("food", 4, "stamina", 1, ("cook", "gardener", "scavenger")),
         ("water", 5, "bleed", 2, ("scout", "gardener", "scavenger")))
WIRE = {p[0]: p[1] for p in PERKS}
CAT_OF_WIRE = {p[1]: p[0] for p in PERKS}
CAP = {p[0]: p[3] for p in PERKS}
ROLES = {p[0]: p[4] for p in PERKS}
RESERVE_DAYS = 1
USE_LABELS = (31, 32)          # op 0xE2 count labels: 31 = med | ammo << 4 | mat << 8, 32 = food | water << 4 (a nibble per category)
MAX_USES = 15

# what a used perk is called in the saga: cat -> (EN thing, PL thing in the accusative, EN verb phrase, PL verb phrase)
ITEM = {"med": ("antibiotics", "antybiotyki"), "ammo": ("rounds", "naboje"), "mat": ("rags and alcohol", "szmaty i spirytus"),
        "food": ("food", "jedzenie"), "water": ("clean water", "czystą wodę")}


def enabled():
    return os.environ.get("T2R_CLAN_PERKS", "1").lower() not in ("0", "off", "false", "no")


def _h(*a):
    return zlib.crc32("|".join(str(x) for x in a).encode("utf-8")) & 0xFFFFFFFF


def need_of(clan_row):
    n = clan_row["healthy"] + clan_row["hungry"] + clan_row["sick"]
    nd = SUP.need_split(clan.needed(n), n)
    nd.update(SUP.use_of(n))
    return nd


def stock_of(clan_row):
    s = (clan.meta_of(clan_row).get("sup") or {}).get("stock") or {}
    return {k: max(0, int(s.get(k, 0) or 0)) for k in SUP.CATS}


def surplus(clan_row):
    """{cat: units above RESERVE_DAYS of that category's need} (0 or more)."""
    nd, st = need_of(clan_row), stock_of(clan_row)
    return {k: max(0, st[k] - RESERVE_DAYS * nd[k]) for k in SUP.CATS}


def credit_of(story, cat):
    """The member credited with `cat` (a story person dict) or None: the most credited living one, else the role's first living member."""
    if not story:
        return None
    alive = {p["i"]: p for p in story.get("people", []) if KD.can_fight(p)}     # (a kid never provides: clan_kids.py; credit booked before that rule is skipped)
    cr = (((story.get("ch") or {}).get("pk") or {}).get("cr") or {}).get(cat) or {}
    best = sorted(((n, -int(i)) for i, n in cr.items() if int(i) in alive and n > 0), reverse=True)
    if best:
        return alive[-best[0][1]]
    for role in ROLES[cat]:
        for p in story.get("people", []):
            if p["r"] == role and p.get("s", "h") != "d" and KD.can_fight(p):
                return p
    grown = [p for p in story.get("people", []) if p.get("s", "h") != "d" and KD.can_fight(p)]
    return next((p for p in grown if p["r"] == "scavenger"), None) or next((p for p in grown if not _owns_other(p, cat)), None) or (grown[0] if grown else None)


def _owns_other(p, cat):
    """True when the member's role is the trade of another perk category only (a medic bringing ammo reads wrong)."""
    return any(p["r"] in roles for c, roles in ROLES.items() if c != cat) and p["r"] not in ROLES[cat]


def active(clan_row, story=None):
    """[{cat, wire, key, cap, who: {n, r, g, look, i} or None}] for a living clan, in PERKS order; [] when off / no clan / no surplus."""
    if not enabled() or not clan_row or clan_row.get("status") != clan.ALIVE:
        return []
    sp = surplus(clan_row)
    out = []
    for cat, wire, key, cap, _roles in PERKS:
        if sp[cat] < 1:
            continue
        who = credit_of(story, cat)
        w = None
        if who:
            sex = 1 if who.get("g") == "f" else 0 if who.get("g") == "m" else _h("sex", who["n"]) & 1
            w = {"n": who["n"], "r": who["r"], "g": sex, "look": _h("model", who["n"]) % 4, "i": who["i"]}
            try:                                      # the card's portrait: the member's clan-journal head, happy (fitted to the expressions it has)
                import clan_chronicle
                fk = "S" if (story.get("fac") if story.get("fac") is not None else clan_row.get("fac")) == clan.SERAPHITES else "W"
                pid = clan_chronicle.portrait_id(who, fk, state="h", morale=100, members=list(story.get("people") or []) + list(story.get("dead") or []))
                w["pid"] = "_".join(pid.split("/")[2:4])          # '<model>_<expression>' = the c13p-<model>_<expression>.png icon
            except Exception:                                     # noqa: BLE001 - no portrait: the card keeps its silhouette
                pass
        out.append({"cat": cat, "wire": wire, "key": key, "cap": min(cap, sp[cat]), "who": w})
    return out


def loss_streak(story):
    """Consecutive lost matches at the end of the clan's recent results (a plain/unknown day is skipped: it neither counts nor breaks the streak).
    Source: story["ch"]["sg_hist"] (clan_saga, last 14 days, "win" True/False/None), else story["ch"]["log"] (clan_loot's raid log, same "win" field).  0 when unknown."""
    cs = (story or {}).get("ch") or {}
    hist = cs.get("sg_hist") or cs.get("log") or []
    n = 0
    for h in reversed(hist):
        w = h.get("win") if isinstance(h, dict) else None
        if w is False:
            n += 1
        elif w is True:
            break
    return min(n, 9)


def wire_text(perks, streak=0):
    """The tail of the clan state reply (op 0xE1/0xE9 state text): integers first (an old ext stops at the first non-integer value), the names last.
    pk=<n> pkc<i>=<wire cat> pkn<i>=<cap> pkg<i>=<0 male / 1 female> pkl<i>=<head model 0..3> pkr<i>=<role id> ... pkm<i>=<Name with _ for spaces> ... pkp<i>=<portrait model_expression>"""
    if not perks:
        return ""
    roles = list(__import__("clan_story_data").ROLES)
    f = ["pk=%d" % len(perks)]
    if streak > 0:                                    # pks=<clan loss streak>: the ext lets the help come sooner (re/clan-supply-boosters.md, section 7); an old ext ignores it
        f.append("pks=%d" % min(9, int(streak)))
    for i, p in enumerate(perks):
        w = p["who"] or {}
        f += ["pkc%d=%d" % (i, p["wire"]), "pkn%d=%d" % (i, p["cap"]), "pkg%d=%d" % (i, w.get("g", 0)), "pkl%d=%d" % (i, w.get("look", 0)),
              "pkr%d=%d" % (i, roles.index(w["r"]) if w.get("r") in roles else 0)]
    for i, p in enumerate(perks):
        if p["who"]:
            f.append("pkm%d=%s" % (i, "".join(ch if (ch.isalnum() and ord(ch) < 128) or ch in "-'" else "_" for ch in p["who"]["n"])[:20]))
    for i, p in enumerate(perks):                     # pkp<i>=<model>_<expression>: the member's portrait (an older ext ignores it)
        if p["who"] and p["who"].get("pid"):
            f.append("pkp%d=%s" % (i, "".join(ch for ch in p["who"]["pid"] if ch.isalnum() or ch in "_-")[:20]))
    return " ".join(f)


def uses_of(counts):
    """{cat: n} from the op 0xE2 count labels 31 / 32 (nibbles), clamped."""
    c = counts or {}
    a, b = int(c.get(31, 0) or 0), int(c.get(32, 0) or 0)
    u = {"med": a & 15, "ammo": (a >> 4) & 15, "mat": (a >> 8) & 15, "food": b & 15, "water": (b >> 4) & 15}
    return {k: min(v, CAP[k]) for k, v in u.items() if v > 0}


def _pick_bringer(story, cat, day):
    people = [p for p in story.get("people", []) if p.get("s", "h") != "d" and KD.can_fight(p)]       # kids never provide a perk (the lines read as the fighter's supplies); grown people only
    pool = ([p for r in ROLES[cat] for p in people if p["r"] == r] or [p for p in people if p["r"] == "scavenger"]
            or [p for p in people if not _owns_other(p, cat)] or people)          # role fit first (medics bring health kits, not ammo)
    return pool[_h("bring", story.get("n", 0), day, cat) % len(pool)] if pool else None


def credit_day(story, got, day):
    """Book what the day brought in each category to a member (by role); mutates story["ch"]["pk"]."""
    if not story or not story.get("people"):
        return
    cr = story.setdefault("ch", {}).setdefault("pk", {}).setdefault("cr", {})
    for cat in SUP.CATS:
        n = int((got or {}).get(cat, 0) or 0)
        p = _pick_bringer(story, cat, day) if n > 0 else None
        if p:
            d = cr.setdefault(cat, {})
            d[str(p["i"])] = d.get(str(p["i"]), 0) + n


# ---- saga lines (EN + PL), one per used perk; {n} the member, {map}
LINES = {
    "med": (("{n}'s antibiotics kept you on your feet at {map}.", "{n}'s bandages were in your pack at {map}, and you used them."),
            ("{n} dał ci antybiotyki. Postawiły cię na nogi: {map}.", "{n} schował ci bandaże w plecaku. Przydały się: {map}.")),
    "ammo": (("{n} pressed a spare clip into your hands before {map}.", "The rounds {n} brought home were in your belt at {map}."),
             ("{n} wcisnął ci zapasowy magazynek przed {map}.", "{n} dosypał ci nabojów do pasa. Starczyło ich: {map}.")),
    "mat": (("{n}'s rags and spirit let you patch yourself up twice at {map}.", "{n} left a crafting kit by your bed. It paid off at {map}."),
            ("{n} zostawił ci szmaty i spirytus. Przydały się: {map}.", "{n} podrzucił ci zestaw do składania. Opłaciło się: {map}.")),
    "food": (("The food {n} found kept you running at {map}.", "{n}'s cooking was still in your legs at {map}."),
             ("{n} podzielił się jedzeniem. Starczyło sił na bieg: {map}.", "{n} zrobił ci prowiant. Nogi niosły dalej: {map}.")),
    "water": (("{n}'s clean water bought you time at {map}.", "{n} filled your canteen before {map}. You needed every drop."),
              ("{n} napełnił ci manierkę. Czysta woda dała ci czas: {map}.", "{n} przyniósł czystą wodę. Przydała się każda kropla: {map}.")),
}


def _fem(t):
    """Polish: the past-tense verb right after the member's name ('{n} dal') takes the feminine ending."""
    a, b = t.split("{n} ", 1)
    w, rest = b.split(" ", 1)
    return a + "{n} " + (w[:-1] + chr(0x142) + "a" if w.endswith(chr(0x142)) else w) + " " + rest


def line(cat, who, mapname, lang="en", day=0):
    """The saga line of one used perk. No map name: the place phrase is left out. Polish: the verb after the name takes the member's gender."""
    en, pl = LINES[cat]
    t = (pl if lang == "pl" else en)[_h("pkline", who["n"], day, cat) % 2]
    if lang == "pl" and who.get("g") in ("f", 1):
        t = _fem(t)
    if mapname:
        t = t.replace("{map}", mapname)
    else:
        t = re.sub(r"(: | at | before )\{map\}", "", t)
        t = re.sub(r" \{map\}", "", t)
    return t.replace("{n}", who["n"])


def render_msg(lid, params, lang="en"):
    """A stored perk row (lid "pk/use"): params {"t": EN text, "tp": PL text}."""
    if not lid or not lid.startswith("pk/") or not isinstance(params, dict):
        return None
    return params.get("tp") if str(lang).lower().startswith("pl") else params.get("t")


def on_day(c, tid, newc, r, counts, match=None):
    """After clan.apply_match + clan_story.on_day: credit the day's goods to members, draw the perk uses from the stock, write the saga lines.
    Returns the list of (cat, n) drawn."""
    import clan_story as CS
    if not enabled() or not r or not newc:
        return []
    sup = r.get("sup") or {}
    story = CS._load(c, tid)
    day = int(r.get("day", newc.get("day", 0)))
    if story:
        credit_day(story, sup.get("got"), day)
    used = uses_of(counts)
    drawn = []
    if used:
        cl = clan.load(c, tid)
        meta = clan.meta_of(cl)
        stock = dict((meta.get("sup") or {}).get("stock") or {})
        for cat, n in used.items():
            have = max(0, int(stock.get(cat, 0) or 0))
            d = min(n, have)
            stock[cat] = have - d
            drawn.append((cat, n))
        meta["sup"] = dict(meta.get("sup") or {}, stock=stock)
        cl["meta"] = json.dumps(meta, separators=(",", ":"))
        clan.save(c, tid, cl)
        if story:
            msgs = []
            mp = str((match or {}).get("map") or "")
            try:
                import clan_chronicle_maps as MAPN
                mp_pl = MAPN.PL.get(mp, mp)
            except Exception:                                        # noqa: BLE001
                mp_pl = mp
            # - every match with a perk use wrote up to two feed rows out of ten
            # templates. No feed rows any more: a used perk is ONE sentence a day in that day's journal entry (tools/clan_journal.add_perk), from pools whose
            # lines are used once per clan run; when they are spent the journal says nothing rather than the same thing again.
            for cat, _n in drawn:
                who = credit_of(story, cat)
                if not who:
                    continue
                try:
                    import clan_journal
                    if clan_journal.add_perk(c, tid, story, day + 1, cat, who, mp):      # (day = days done before the match; the entry is the day played)
                        break
                except Exception:                                    # noqa: BLE001 - the journal never breaks the perks
                    break
            if msgs:
                CS._store(c, tid, story, msgs, int(newc["faction"]), day, clan.week_day(day)[0])
    if story:
        CS._save(c, tid, story)
    return drawn
