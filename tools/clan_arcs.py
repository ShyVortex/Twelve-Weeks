"""Clan story arcs: small state machines that run over several clan days, linked to the bonds of the roster, with branches decided by what really happens
(the day's supplies, morale, who really died, what is on hand).  Text: tools/clan_arcs_text.py (EN + PL).  Called by clan_chronicle.day_rows.

An arc = {id, k kind, n node, t day of the node, d0, c {A: id, B: id}, p {A: [name, gender, role]} (rendering snapshot), v vars, h hash, rel, steps}.
Every day (clan_chronicle -> run): active arcs advance (at most ARC_ROWS rows), then at most ONE new arc may start (cap MAX_ACTIVE running at once, a kind is not
restarted within COOLDOWN days).  The row of a step: kind "chron", lid "arc/<kind>.<node>", text "DAY n: HEADLINE IN CAPITALS. Vignette.", params {"p", "s", "a": arc id,
"n": step number}, style "arc_<kind>"; the clan UI groups the rows of one arc id into a thread.  Arc rows are never shown by toasts / popups: the menu ticker skips them.

What an arc may change in the roster: nothing by itself.  A dark branch needs a real death: the arc "marks" a person (st["ch"]["doom"][id] = cause: bite / walkout);
clan_story's _kill_pick takes a marked person first when the clan rules kill someone that day anyway, and the death line uses the arc's cause.  No real death in the
window -> the arc takes its other branch (found alive, the vote withdrawn, pulled back).  Hunger / sickness numbers are never touched.
People in an arc who are away from camp (st["ch"]["away"]) are not used by any other line (chronicle, A-Life, diary rows naming them are dropped), and a dead person
never acts (the arc is dropped silently when a needed person died outside its own death branch).
"""
import os
import random
import re
import sys
import zlib

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import clan                                                  # noqa: E402
import clan_alife_lex as X                                   # noqa: E402
import clan_story_pl as PLN                                  # noqa: E402
import clan_arcs_text as AT                                  # noqa: E402
import clan_kids as KD                                       # noqa: E402  (kids are never fighters)

MAX_ACTIVE = 3
ARC_ROWS = 2
COOLDOWN = 6
MAX_AGE = 14
LOG_KEEP = 14


def _h(*parts):
    return zlib.crc32("|".join(str(x) for x in parts).encode("utf-8")) & 0xFFFFFFFF


# ------------------------------------------------------------------ conditions (c = _Ctx, a = arc)
def days(c, a):
    return c.day - a["t"]


def dead(L):
    return lambda c, a: not c.alive(a, L)


def alive(L):
    return lambda c, a: c.alive(a, L)


def after(n, *conds):
    return lambda c, a: days(c, a) >= n and all(f(c, a) for f in conds)


def sick(L, yes=True):
    return lambda c, a: (c.state(a, L) == "s") == yes


def sup_ok(c, a):
    return int(c.r.get("supplies", 0)) >= int(c.r.get("needed", 1))


def morale_ge(n):
    return lambda c, a: c.morale >= n


def hmod(m, k):
    return lambda c, a: a["h"] % m == k


def hnot(m, k):
    return lambda c, a: a["h"] % m != k


def both(*fs):
    return lambda c, a: all(f(c, a) for f in fs)


def has_med(c, a):
    return not a["v"].get("treated") and c.med_key() is not None


def ormorale_or_hash(n, m):
    return lambda c, a: c.morale >= n or a["h"] % m != 0


def steals(c, a):
    return a["h"] % 3 == 0 and c.morale <= 55


def h3(k):
    """The arc's own three-way die (independent of hmod): which ending a spore story takes."""
    return lambda c, a: (a["h"] >> 5) % 3 == k


def stranger_ok(c, a):
    """The gate opens when the camp can afford a guest (real supplies and morale), now and then on a hunch."""
    return (c.morale >= 50 and sup_ok(c, a)) or a["h"] % 4 == 0


def has_food(c, a):
    return any(c.cs["inv"].get(k, 0) > 0 for k in ("pine", "beans"))


def fx_cake(c, a):
    k = next((k for k in ("pine", "beans") if c.cs["inv"].get(k, 0) > 0), None)
    if k:
        a["v"]["it"] = k
        c.cs["inv"][k] = max(0, c.cs["inv"][k] - 1)
    c.st["morale"] = min(100, int(c.st.get("morale", 50)) + 3)


def fx_trade(c, a):
    c.cs["inv"]["bandage"] = c.cs["inv"].get("bandage", 0) + 2
    c.st["morale"] = min(100, int(c.st.get("morale", 50)) + 2)


def fx_pendant(c, a):
    c.st["morale"] = min(100, int(c.st.get("morale", 50)) + 2)


def fx_spore_end(with_helper):
    """The end of the spore story: the person leaves the roster for good (turned, mercy or a walk into the dark) - the spores never let go (TLOU canon).  The one who
    had to do it carries the guilt, the kin and the helper grieve (clan_story.finish_member); the next days' feed rows are the camp's grief."""
    def fx(c, a):
        import clan_story as CS
        A = c.person(a, "A")
        if A is None:
            return
        B = c.person(a, "B")
        CS.finish_member(c.st, A, c.day, "turned", B if (with_helper and B is not None and not KD.is_kid(B)) else None)
        CS.spare_sick(random.Random(_h("spare", a["id"], c.day)), c.st, c.day)       # (the roster keeps the clan's size and sick count)
        c.byid.pop(A["i"], None)
        c.d.spot.add(A["i"])
    return fx


def fx_treat(c, a):
    k = c.med_key()
    a["v"]["it"] = k
    a["v"]["treated"] = 1
    c.cs["inv"][k] = max(0, c.cs["inv"][k] - 1)


def fx_share(c, a):
    c.st["morale"] = min(100, int(c.st.get("morale", 50)) + 3)


def fx_bandages(c, a):
    c.cs["inv"]["bandage"] = c.cs["inv"].get("bandage", 0) + 2


# node: {"away": letters, "doom": {letter: cause}, "fx": fn, "ok_dead": letters allowed dead, "mood", "nxt": [(cond, node), ...]}  (no nxt = the arc ends here)
def N(nxt=(), away="", doom=None, fx=None, ok_dead="", mood="worried"):
    return {"nxt": list(nxt), "away": away, "doom": doom or {}, "fx": fx, "ok_dead": ok_dead, "mood": mood}


ARCS = {
    "missing": {"n0": N([(after(1, alive("A")), "search")], away="A", mood="afraid"),
                "search": N([(both(dead("A"), hmod(3, 2)), "found_gut"), (dead("A"), "found_dead"), (after(2, alive("A"), sup_ok), "alive"), (after(4, alive("A")), "alive_late")], away="AB", doom={"A": "bite"}, mood="afraid"),
                "found_dead": N([(after(1, alive("B"), hmod(2, 0)), "mercy"), (after(1, alive("B")), "despair")], ok_dead="A", mood="grieving"),
                "mercy": N(ok_dead="A", mood="grieving"),
                "found_gut": N([(after(1, alive("B")), "mercy_gut")], ok_dead="A", mood="grieving"), "mercy_gut": N(ok_dead="A", mood="grieving"),
                "despair": N([(dead("B"), "turned"), (after(3, alive("B")), "pulled")], away="B", doom={"B": "bite"}, ok_dead="A", mood="grieving"),
                "turned": N(ok_dead="AB", mood="grieving"), "pulled": N(ok_dead="A", mood="grieving"),
                "alive": N(mood="hopeful"), "alive_late": N(mood="hopeful")},
    "spore": {"sp0": N([(dead("A"), "remembered"), (after(1, hmod(2, 0)), "hide"), (after(1), "confess")], mood="afraid"),
              "hide": N([(dead("A"), "remembered"), (after(1), "signs")], mood="afraid"),
              "confess": N([(dead("A"), "remembered"), (after(1), "signs")], mood="grieving"),
              "signs": N([(dead("A"), "remembered"), (after(1, h3(0)), "turn"), (after(1, h3(1)), "mercy"), (after(1), "walk")], mood="grim"),
              "turn": N([(after(1, alive("B")), "after")], fx=fx_spore_end(True), ok_dead="A", mood="grieving"),
              "mercy": N([(after(1, alive("B")), "after")], fx=fx_spore_end(True), ok_dead="A", mood="grieving"),
              "walk": N([(after(1, alive("B")), "after")], fx=fx_spore_end(False), ok_dead="A", mood="grieving"),
              "remembered": N([(after(1, alive("B")), "after")], ok_dead="A", mood="grieving"),
              "after": N(ok_dead="A", mood="grieving")},
    "stranger": {"st0": N([(after(1, stranger_ok), "in"), (after(1), "out")], mood="worried"),
                 "in": N([(after(2, hmod(2, 0)), "gift"), (after(2), "cough")], mood="hopeful", fx=fx_share),
                 "gift": N(mood="hopeful"), "cough": N(mood="calm"),
                 "out": N([(after(3), "echo")], mood="grim"), "echo": N(mood="calm")},
    "caravan": {"car0": N([(after(1, sup_ok), "trade"), (after(1, morale_ge(55)), "trade"), (after(1), "poor")], mood="hopeful"),
                "trade": N([(after(2), "news")], fx=fx_trade, mood="cheerful"), "news": N(mood="hopeful"), "poor": N(mood="grim")},
    "pendant": {"fp0": N([(after(1), "tell")], mood="calm", fx=fx_pendant),
                "tell": N([(after(1, morale_ge(50)), "worn"), (after(1), "tin")], mood="calm"),
                "worn": N(mood="hopeful"), "tin": N(mood="calm")},
    "birthday": {"bd0": N([(after(1, has_food), "cake"), (after(1), "promise")], mood="cheerful"),
                 "cake": N(fx=fx_cake, mood="cheerful"),
                 "promise": N([(after(3), "kept")], mood="calm"), "kept": N(mood="hopeful")},
    "sick": {"s0": N([(dead("A"), "death"), (sick("A", False), "recover"), (after(1, sick("A"), has_med), "treat"), (after(2, sick("A")), "hold")]),
             "treat": N([(dead("A"), "death"), (sick("A", False), "recover"), (after(2, sick("A")), "hold")], fx=fx_treat, mood="hopeful"),
             "hold": N([(dead("A"), "death"), (sick("A", False), "recover"), (after(2, sick("A"), has_med), "treat")]),
             "recover": N(mood="hopeful"), "death": N(ok_dead="A", mood="grieving")},
    "hung": {"h0": N([(after(1), "confront")]),
             "confront": N([(after(1, ormorale_or_hash(45, 3)), "forgiven"), (after(1), "banish")]),
             "forgiven": N(mood="hopeful"),
             "banish": N([(dead("A"), "gone"), (after(3, alive("A")), "relent")], doom={"A": "walkout"}, mood="grim"),
             "gone": N(ok_dead="A", mood="grim"), "relent": N(mood="hopeful")},
    "new": {"w0": N([(after(2), "test")], mood="hopeful"),
            "test": N([(after(1, steals), "steals"), (after(1), "trust")]),
            "trust": N(mood="hopeful"),
            "steals": N([(dead("A"), "gone"), (after(3, alive("A")), "returns")], doom={"A": "walkout"}, mood="grim"),
            "gone": N(ok_dead="A", mood="grim"), "returns": N(mood="hopeful")},
    "keep": {"k0": N([(after(2), "found")], mood="cheerful"),
             "found": N([(after(1, morale_ge(50)), "share"), (after(1), "hold")]),
             "share": N(fx=fx_share, mood="cheerful"), "hold": N(mood="calm")},
    "birth": {"b0": N([(after(3), "prep")], mood="hopeful"),
              "prep": N([(after(3, morale_ge(40)), "born"), (after(3), "hard")], mood="hopeful"),
              "born": N(mood="cheerful"), "hard": N(mood="hopeful")},
    "wish": {"o0": N([(after(1), "o1")], mood="calm"),
             "o1": N([(dead("A"), "after"), (after(3, alive("A")), "done")], mood="hopeful"),
             "done": N(mood="cheerful"), "after": N(ok_dead="A", mood="grieving")},
    "blame": {"q0": N([(after(2, sup_ok), "made"), (after(2), "split")], mood="worried"),
              "made": N(mood="hopeful"), "split": N(mood="grim")},
    "betray": {"t0": N([(after(1), "t1")], mood="afraid"),
               "t1": N([(after(1, hmod(2, 0)), "expose"), (after(1), "innocent")], mood="afraid"),
               "expose": N([(dead("A"), "gone"), (after(3, alive("A")), "pardon")], doom={"A": "walkout"}, mood="grim"),
               "gone": N(ok_dead="A", mood="grim"), "pardon": N(mood="calm"), "innocent": N(fx=fx_bandages, mood="calm")}}
FIRST = {"missing": "n0", "sick": "s0", "hung": "h0", "new": "w0", "keep": "k0", "birth": "b0", "wish": "o0", "blame": "q0", "betray": "t0",
         "spore": "sp0", "stranger": "st0", "caravan": "car0", "pendant": "fp0", "birthday": "bd0"}
for _k, _nodes in ARCS.items():                              # every node has text, every target exists
    for _n, _d in _nodes.items():
        assert "%s.%s" % (_k, _n) in AT.TEXT, "no text for arc node %s.%s" % (_k, _n)
        for _c, _t in _d["nxt"]:
            assert _t in _nodes, "arc %s: unknown target %s" % (_k, _t)
    assert FIRST[_k] in _nodes
GENDER_F = ("birth",)
# kids are no fighters (clan_kids.py): the letters of an arc whose node texts (EN or PL) read as combat, raid, patrol or danger may only be grown people
ARC_FIGHT = {}
for _k, _nodes in ARCS.items():
    _l = set()
    for _n in _nodes:
        for _t, _lg in zip(AT.TEXT["%s.%s" % (_k, _n)], ("en", "pl", "en", "pl")):
            if KD.combat_text(_t, _lg):
                _l |= KD.letters_in(_t)
    ARC_FIGHT[_k] = _l


# ------------------------------------------------------------------ the day's context
class _Ctx:
    def __init__(self, d, st, newc, r, match, cs):
        self.d, self.st, self.newc, self.r, self.match, self.cs = d, st, newc, r or {}, match, cs
        self.day = int(newc["day"])
        self.morale = int(st.get("morale", 50))
        self.byid = {p["i"]: p for p in st["people"]}

    def person(self, a, L):
        return self.byid.get(a["c"].get(L))

    def alive(self, a, L):
        return a["c"].get(L) in self.byid

    def state(self, a, L):
        p = self.person(a, L)
        return p["s"] if p else None

    def med_key(self):
        for k, n in sorted(self.cs["inv"].items()):
            if n > 0 and k in ("abx", "bandage", "alcohol"):
                return k
        return None


def rel_key(A, B, bt):
    """What A is to B (their bond type is symmetric): kin splits by life stage, mentor by rank, sweet = partner."""
    rank = {"kid": 0, "adult": 1, "elder": 2}

    def stage(p):
        return "kid" if p["r"] == "kid" else "elder" if p["r"] == "elder" else "adult"
    if bt == "kin":
        a, b = rank[stage(A)], rank[stage(B)]
        return "sibling" if a == b else ("parent" if a > b else "child")
    if bt == "mentor":
        a, b = rank[stage(A)], rank[stage(B)]
        return "mentor" if a > b else "apprentice" if a < b else "friend"
    if bt == "sweet":
        return "partner"
    return "friend"


def _adult(p):
    return p["r"] not in ("kid", "elder")


can_fight = KD.can_fight                                     # the shared check (clan_kids.py): kids are never cast as fighters


# ------------------------------------------------------------------ starting an arc
def _free(c, exclude=(), pred=lambda p: True):
    busy = {i for a in c.cs["arcs"] for i in a["c"].values()}
    return [p for p in c.st["people"] if p["i"] not in busy and p["i"] not in exclude and str(p["i"]) not in c.cs["away"] and pred(p)]


def _pair(c, A, kinds_ok=None, fight=False):
    """The bonded partner of A (from the persona ring) when free, else any other free adult."""
    import clan_chronicle as CH
    fk = c.d.fk
    ps = CH.persona(A, c.st["people"], fk, c.st)
    free = {p["i"]: p for p in _free(c, {A["i"]})}
    B = free.get(ps["bond"])
    if B is not None and fight and not can_fight(B):
        B = None                                             # (a search party is grown people)
    bt = ps["bt"] or "kin"
    if B is None:
        pool = [p for p in free.values() if p["s"] != "s" and _adult(p)]
        if not pool:
            return None, None
        B = sorted(pool, key=lambda p: _h("pairb", A["n"], p["n"]))[0]
        bt = CH.BOND_TYPES[_h("bond", *sorted((A["n"], B["n"]))) % 4]
    return B, bt


def _make(c, kind, A, B, bt, **v):
    c.cs["arc_n"] = c.cs.get("arc_n", 0) + 1
    rel = rel_key(A, B, bt) if B is not None else "friend"
    if rel in ("sibling", "parent", "child") and B is not None:
        B["l"] = A["l"]                                      # family: the same surname
    a = {"id": "a%d" % c.cs["arc_n"], "k": kind, "n": None, "t": c.day, "d0": c.day, "c": {"A": A["i"]}, "p": {"A": [A["n"], A["g"], A["r"]]}, "v": v,
         "h": _h(c.st.get("seed", ""), kind, c.cs["arc_n"], A["n"]), "rel": rel, "steps": 0}
    if B is not None:
        a["c"]["B"] = B["i"]
        a["p"]["B"] = [B["n"], B["g"], B["r"]]
    a["v"].setdefault("task", a["h"] % len(AT.TASKS))
    a["v"].setdefault("place", (a["h"] >> 4) % len(AT.PLACES))
    a["v"].setdefault("wish", (a["h"] >> 8) % len(AT.WISHES))
    return a


def _start(c, kind, rng):
    a = _start0(c, kind, rng)
    if a is not None:
        byid = {p["i"]: p for p in c.st["people"]}
        if any(not can_fight(byid[a["c"][L]]) for L in ARC_FIGHT.get(kind, ()) if L in a["c"] and a["c"][L] in byid):
            return None                                      # a kid in a combat arc: the arc does not start
    return a


def _start0(c, kind, rng):
    import clan_chronicle as CH
    adults = lambda p: _adult(p) and p["s"] != "s"                      # noqa: E731
    S, U = int(c.newc.get("sick", 0)), int(c.newc.get("hungry", 0))
    deficit = int(c.r.get("supplies", 0)) < int(c.r.get("needed", 0))
    import clan_saga                                                    # the saga memory decides who fits the arc (a wounded one does not go on a raid, a grieving one fits a last wish)
    pick = lambda pool: (sorted(pool, key=lambda p: (clan_saga.fit(c.cs, kind, p), c.d.used.get("P%d" % p["i"], -999), _h("arcst", c.day, p["n"])))[0] if pool else None)   # noqa: E731
    if kind == "missing":
        if c.day < 2 or len(c.st["people"]) < 6:
            return None
        A = pick(_free(c, pred=lambda p: _adult(p) and p["s"] in ("h", "u")))
        if A is None:
            return None
        B, bt = _pair(c, A, fight=True)
        return _make(c, kind, A, B, bt) if B else None
    if kind == "spore":                                                     # only a member who really is sick with the spores (no cure: the story ends the person's life)
        A = pick(_free(c, pred=lambda p: p["s"] == "s" and p.get("il") == "spores" and not KD.is_kid(p)))
        if A is None:
            return None
        B, bt = _pair(c, A)
        a = _make(c, kind, A, B, bt) if B else None
        if a:
            a["v"]["spot"] = a["h"] % len(AT.SPOTS)
        return a
    if kind == "stranger":
        if len(c.st["people"]) < 5:
            return None
        A = pick(_free(c, pred=lambda p: _adult(p) and p["s"] != "s" and can_fight(p)))
        B = pick(_free(c, {A["i"]} if A else (), pred=lambda p: _adult(p) and p["s"] != "s")) if A else None
        return _make(c, kind, A, B, "friend") if A and B else None
    if kind == "caravan":
        if not (c.match and c.match.get("map")) or len(c.st["people"]) < 5:
            return None
        A = pick(_free(c, pred=lambda p: _adult(p) and p["s"] != "s"))
        B = pick(_free(c, {A["i"]} if A else (), pred=lambda p: _adult(p) and p["s"] != "s")) if A else None
        return _make(c, kind, A, B, "friend") if A and B else None
    if kind == "pendant":
        if not (c.match and c.match.get("map")) or len(c.st["people"]) < 5:
            return None
        A = pick(_free(c, pred=lambda p: _adult(p) and p["s"] != "s"))
        B = pick(_free(c, {A["i"]} if A else (), pred=lambda p: p["r"] in ("elder", "medic", "radio", "cook") and p["s"] != "s")) if A else None
        return _make(c, kind, A, B, "friend") if A and B else None
    if kind == "birthday":
        A = pick(_free(c, pred=lambda p: p["r"] == "kid" and p["s"] != "s"))
        B = pick(_free(c, {A["i"]} if A else (), pred=lambda p: _adult(p) and p["s"] != "s")) if A else None
        return _make(c, kind, A, B, "mentor") if A and B else None
    if kind == "sick":
        A = pick(_free(c, pred=lambda p: p["s"] == "s" and p.get("il") != "spores"))
        if A is None:
            return None
        B, bt = _pair(c, A)
        return _make(c, kind, A, B, bt) if B else None
    if kind == "hung":
        if not (U and deficit):
            return None
        A = pick(_free(c, pred=lambda p: _adult(p) and p["s"] == "u"))
        B = pick(_free(c, {A["i"]} if A else (), pred=lambda p: p["r"] in ("cook", "guard", "medic") and p["s"] != "s")) if A else None
        return _make(c, kind, A, B, "friend") if A and B else None
    if kind == "new":
        A = pick(_free(c, pred=lambda p: p["jd"] == c.day and p["s"] != "s"))
        if A is None:
            return None
        B = pick(_free(c, {A["i"]}, pred=lambda p: _adult(p) and p["s"] != "s"))
        return _make(c, kind, A, B, "friend") if B else None
    if kind == "keep":
        old = [k for k, v in c.cs["keep"].items() if v["d"] < c.day]
        if not old:
            return None
        A = pick(_free(c, pred=lambda p: p["r"] == "kid"))
        B = pick(_free(c, {A["i"]} if A else (), pred=lambda p: p["r"] in ("elder", "guard", "cook", "medic", "scout"))) if A else None
        k = sorted(old)[_h(c.day, "kp") % len(old)]
        return _make(c, kind, A, B, "mentor", keep=k) if A and B else None
    if kind == "birth":
        if c.morale < 55 or len(c.st["people"]) < 10:
            return None
        for A in sorted(_free(c, pred=lambda p: p["g"] == "f" and _adult(p) and p["s"] == "h"), key=lambda p: _h("birth", c.day, p["n"])):
            ps = CH.persona(A, c.st["people"], c.d.fk, c.st)
            B = next((p for p in _free(c, {A["i"]}) if p["i"] == ps["bond"] and ps["bt"] == "sweet" and _adult(p) and p["g"] != "f"), None)
            if B:
                return _make(c, kind, A, B, "sweet")
        return None
    if kind == "wish":
        A = pick(_free(c, pred=lambda p: p["r"] == "elder" and p["s"] != "s"))
        if A is None:
            return None
        B, bt = _pair(c, A)
        return _make(c, kind, A, B, bt) if B else None
    if kind == "blame":
        m = c.match
        if not (m and m.get("map")):
            return None
        bad = (m.get("deaths") is not None and m["deaths"] > int(m.get("kills") or 0)) or (m.get("deaths") is None and deficit and int(m.get("kills") or 0) <= 3)
        if not bad:
            return None
        A = pick(_free(c, pred=lambda p: _adult(p) and p["s"] != "s"))
        B = pick(_free(c, {A["i"]} if A else (), pred=lambda p: _adult(p) and p["s"] != "s")) if A else None
        return _make(c, kind, A, B, "rival") if A and B else None
    if kind == "betray":
        recent = [x for x in c.st["dead"] if x["d"] >= c.day - 3]
        if c.morale > 45 or not recent or len(c.st["people"]) < 6:
            return None
        A = pick(_free(c, pred=lambda p: _adult(p) and p["s"] != "s"))
        B = pick(_free(c, {A["i"]} if A else (), pred=lambda p: _adult(p) and p["s"] != "s")) if A else None
        return _make(c, kind, A, B, "friend") if A and B else None
    return None


START_W = {"missing": 3.0, "sick": 4.0, "hung": 3.0, "new": 5.0, "keep": 3.0, "birth": 1.5, "wish": 2.0, "blame": 3.0, "betray": 2.0,
           "spore": 12.0, "stranger": 2.0, "caravan": 2.0, "pendant": 1.5, "birthday": 1.5}


# ------------------------------------------------------------------ writing a step
DARK = {"found_gut", "mercy_gut", "found_dead", "mercy", "despair", "turned", "death", "after", "banish", "gone", "expose", "turn", "walk", "remembered"}


def _release(c, a):
    for L in list(a["v"].get("am", [])):
        c.cs["away"].pop(str(a["c"].get(L)), None)
    for i in list(a["v"].get("dm", [])):
        c.cs["doom"].pop(str(i), None)
    a["v"]["am"], a["v"]["dm"] = [], []


def _enter(c, a, node):
    nd = ARCS[a["k"]][node]
    _release(c, a)
    for L in nd["away"]:
        if L in a["c"]:
            c.cs["away"][str(a["c"][L])] = a["id"]
            a["v"]["am"].append(L)
    for L, cause in nd["doom"].items():
        if L in a["c"]:
            c.cs["doom"][str(a["c"][L])] = cause
            a["v"]["dm"].append(a["c"][L])
    if nd["fx"]:
        nd["fx"](c, a)
    a["n"], a["t"] = node, c.day
    a["steps"] += 1


def row_for(c, a, node):
    sym = {"f": c.d.fk, "day": c.day, "sup": int(c.r.get("supplies", 0)), "need": int(c.r.get("needed", 0)), "rel": a["rel"], "task": a["v"]["task"], "place": a["v"]["place"],
           "wish": a["v"]["wish"]}
    if c.match and c.match.get("map"):
        sym["map"] = str(c.match["map"])
    if a["v"].get("keep"):
        sym["keep"] = a["v"]["keep"]
    if "spot" in a["v"]:
        sym["spot"] = a["v"]["spot"]
    if a["v"].get("it"):
        sym["it"], sym["itn"] = a["v"]["it"], 1
    lid = "arc/%s.%s" % (a["k"], node)
    params = {"p": a["p"], "s": sym, "a": a["id"], "n": a["steps"]}
    text = render_msg(lid, params, "en")
    return {"kind": "chron", "mood": ARCS[a["k"]][node]["mood"], "text": text, "names": [v[0] for v in a["p"].values() if re.search(r"(?<!\w)" + re.escape(v[0]) + r"(?!\w)", text)],
            "lid": lid, "params": params}


def _vars(sym, people, lang):
    import clan_chronicle as CH
    v = CH._vars(sym, lang)
    pl = lang == "pl"
    ag = "f" if people.get("A", {}).get("g") == "f" else "m"
    if sym.get("rel") in AT.REL:
        e = AT.REL[sym["rel"]][ag]
        v["rel"] = e[1] if pl else e[0]
        v["rel_nom"], v["rel_acc"], v["rel_gen"] = e[1], e[2], e[3]
    t = AT.TASKS[sym.get("task", 0) % len(AT.TASKS)]
    pc = AT.PLACES[sym.get("place", 0) % len(AT.PLACES)]
    w = AT.WISHES[sym.get("wish", 0) % len(AT.WISHES)]
    sp = AT.SPOTS[sym.get("spot", 0) % len(AT.SPOTS)]
    v["spot"] = sp[1] if pl else sp[0]
    v["task"] = t[1] if pl else t[0]
    v["place"] = pc[1] if pl else pc[0]
    v["place_gen"] = pc[1]
    v["wish"] = w[1] if pl else w[0]
    if sym.get("keep") in AT.KEEPS:
        k = AT.KEEPS[sym["keep"]]
        v["keep"] = k[1] if pl else k[0]
        v["keep_acc"], v["keep_ins"], v["keep_gen"] = k[1], k[2], k[3]
    v.setdefault("map", "")
    return v


def render_msg(lid, params, lang="en"):
    """A stored arc row ("arc/<kind>.<node>") as "DAY n: HEADLINE. Vignette." in a language; None for an unknown node."""
    if not lid or not lid.startswith("arc/") or not isinstance(params, dict):
        return None
    key = lid[4:]
    if key not in AT.TEXT:
        return None
    lang = "pl" if PLN.norm_lang(lang) == "pl" else "en"
    people = {k: {"n": str(v[0]), "g": v[1] if v[1] in ("m", "f", "n") else "n", "r": (v[2] if len(v) > 2 else "scavenger")} for k, v in params.get("p", {}).items()}
    sym = params.get("s", {})
    he, hp, be, bp = AT.TEXT[key]
    fk = sym.get("f", "W")
    vars_ = _vars(sym, people, lang)
    head = X.render(hp if lang == "pl" else he, people, vars_, lang, fk).upper()
    body = X.render(bp if lang == "pl" else be, people, vars_, lang, fk)
    tie = params.get("tie_pl") if lang == "pl" else params.get("tie")       # one sentence from the saga that ties the step to the day's match (a row without a Polish tie shows none)
    if tie:
        body = body + " " + tie
    return "%s %d: %s. %s" % ("DZIEŃ" if lang == "pl" else "DAY", int(sym.get("day", 0)), head, body)


# ------------------------------------------------------------------ the daily run
def run(d, st, newc, r, match, cs, rng):
    """Advance the running arcs and maybe start one; returns the day's arc rows (at most ARC_ROWS).  d = the chronicle's _Day."""
    for k, dv in (("arcs", []), ("away", {}), ("doom", {}), ("arc_hist", {}), ("arc_log", [])):
        cs.setdefault(k, dv)
    c = _Ctx(d, st, newc, r, match, cs)
    rows = []
    for a in list(cs["arcs"]):
        if a["t"] == c.day and a["steps"] >= 1 and a["n"] is not None and a["d0"] == c.day:
            continue                                         # started today
        nd = ARCS[a["k"]][a["n"]]
        fired = next((t for cond, t in nd["nxt"] if cond(c, a)), None)
        if fired is None:
            need_dead = [L for L in a["c"] if not c.alive(a, L) and L not in nd["ok_dead"]]
            if need_dead or c.day - a["d0"] > MAX_AGE:       # a needed person died outside the arc's own death branch: the arc is dropped quietly
                _release(c, a)
                cs["arcs"].remove(a)
            continue
        if len(rows) >= ARC_ROWS:
            continue
        _enter(c, a, fired)
        rows.append(row_for(c, a, fired))
        for L, i in a["c"].items():
            d.used["P%d" % i] = c.day
        if not ARCS[a["k"]][fired]["nxt"]:                   # the arc ends with this step
            _release(c, a)
            cs["arcs"].remove(a)
            cs["arc_log"].append({"id": a["id"], "k": a["k"], "d0": a["d0"], "d1": c.day, "A": a["p"]["A"][0], "B": a["p"].get("B", [""])[0], "end": fired})
            del cs["arc_log"][:-LOG_KEEP]
    if len(cs["arcs"]) < MAX_ACTIVE and len(rows) < ARC_ROWS and rng.random() < (0.55 if not cs["arcs"] else 0.35):
        kinds = [k for k in START_W if c.day - cs["arc_hist"].get(k, -99) >= COOLDOWN and not any(a["k"] == k for a in cs["arcs"])]
        rng.shuffle(kinds)
        order = sorted(kinds, key=lambda k: -rng.random() * START_W[k])
        for k in order:
            a = _start(c, k, rng)
            if a is None:
                continue
            cs["arcs"].append(a)
            cs["arc_hist"][k] = c.day
            _enter(c, a, FIRST[k])
            rows.append(row_for(c, a, FIRST[k]))
            for L, i in a["c"].items():
                d.used["P%d" % i] = c.day
            break
    return rows


def thread(st, arc_id, lang="en"):
    """Not stored separately: the UI builds a thread from the feed rows that carry the same params["a"]; this lists finished arcs for the clan screen."""
    return [e for e in (st.get("ch") or {}).get("arc_log", []) if e["id"] == arc_id]
