"""The clan journal: ONE entry per clan day, written from what that day really did to the clan.

Why (re/clan-journal-overhaul-1109.md has the audit): the old journal was the newest 24 of ~7 feed rows a day from five independent generators (diary, ticker, A-Life,
chronicle / saga, supply perks) glued 3-6 to an "entry" with a random author - unrelated sentences in one paragraph, the same events told three ways, a haul inventory
almost every day, the perk rows ("{n}'s antibiotics kept you on your feet at {map}") over and over, and only the last ~2 weeks kept.

Now: clan_story.on_day calls on_day() here with a snapshot of the roster from before the day.  The entry is composed from the DIFFERENCE (who died and of what, who
fell sick with what, who recovered, who went hungry, who joined - the real members of clan_story's roster, which is reconciled to the clan's real counts) and from the
day's result (the match, supplies against need, the event that started or was settled).  Paragraphs in a fixed order: THE RAID, SUPPLIES, THE CAMP, the EVENT,
NOTES.  Text comes from tools/clan_journal_text.py (+ _pl): every pool has its trigger written next to it, a line is used ONCE per clan run (the used indexes live
in the story state, st["jn"]), and a pool that ran dry gives the plain ledger sentence (pools "f_*"), never a repeat.

Storage: table clan_journal(token_id, day, id, data): day = the clan day the entry is about (1..84, 0 = the founding), id = the feed's message counter at the time
(the client's NEW marker), data = a language-neutral record (template ids + people + numbers), rendered at read time (entries(lang)).  A run owns its rows
(purge()).  The whole run is kept: 85 rows at most.

Also here: the one sentence a used supply perk adds to the day's raid paragraph (add_perk, called by clan_perks.on_day instead of its old feed rows) and the lines of
the STATUS UPDATES cards (status_lines: the journal's own sentence about that member, or a pool line - never the same sentence on two cards).
"""
import json
import random
import re
import sys

import clan
import clan_story as CS
import clan_story_data as D
import clan_story_pl as PLN
import clan_kids as KD
import clan_journal_text as EN
import clan_journal_text_pl as PL

LANG_POOLS = {"en": EN, "pl": PL}
SCHEMA = "CREATE TABLE IF NOT EXISTS clan_journal(token_id TEXT, day INTEGER, id INTEGER, data TEXT, PRIMARY KEY(token_id, day))"
REC_V = 1
MAX_PARAS = 8
CAMP_MAX = 5                       # sentences of THE CAMP paragraph (more changes than that are listed by name in one closing sentence)
NOTE_BELOW = 5                     # a camp-life note is added only to an entry with fewer sentences than this
PLENTY_OVER = 6                    # supplies this far over the need = "plenty" (own choice of the mark, not a 2013 number)
_KEY = re.compile(r"\{(\w+)\}")
_SW = re.compile(r"\{([A-D]+)\?[^|{}]*\|[^|{}]*\}")
_NUM = ("sup", "need", "short", "over", "k", "x", "r", "hs", "dw", "lost", "gain", "n", "size", "week", "more")


# ------------------------------------------------------------------ templates and rendering
def _keys(t):
    """The base placeholders a template needs: {A_he} -> A, {E_gen} -> E, {ill_acc} -> ill, {A?x|y} -> A."""
    k = {x.split("_")[0] for x in _KEY.findall(t)}
    for letters in _SW.findall(t):
        k |= set(letters)
    return k


def _need(pool, i):
    return _keys(EN.POOLS[pool][i][1]) | _keys(PL.POOLS[pool][i])


def _repeatable(pool):
    return pool.startswith(("t_", "f_"))


def _pick(st, rng, pool, fk, have, avoid=(), skip=()):
    """An unused line of the pool for the faction whose placeholders are all there -> index, or None (the pool ran dry / nothing fits).  Titles and ledger
    sentences ("t_*", "f_*") may repeat.  avoid = indexes that must not be chosen now (lines on screen); with avoid given, a spent pool gives its least recently
    used line again instead of None (the status cards)."""
    lines = EN.POOLS.get(pool) or []
    ok = [i for i, (sc, _t) in enumerate(lines) if sc in ("*", fk) and _need(pool, i) <= have and i not in skip]
    if not ok:
        return None
    if _repeatable(pool):
        return rng.choice(ok)
    used = st.setdefault("jn", {}).setdefault("u", {}).setdefault(pool, [])
    fresh = [i for i in ok if i not in used and i not in avoid]
    if fresh:
        i = rng.choice(fresh)
    elif avoid != ():
        old = [i for i in used if i in ok and i not in avoid] or [i for i in ok if i not in avoid] or ok
        i = old[0]
        if i in used:
            used.remove(i)
    else:
        return None
    used.append(i)
    return i


def _vars(sym, lang):
    fk = sym.get("f", "W") if sym.get("f") in ("W", "S") else "W"
    v = {k: str(sym[k]) for k in _NUM if k in sym}
    mp = sym.get("map")
    ill = sym.get("ill")
    if lang == "pl":
        e = PLN.ENEMY[fk]
        v.update(E=e[0], E_gen=e[1], E_ins=e[2])
        if mp:
            try:
                import clan_chronicle_maps as MAPN
                v["map"] = MAPN.PL.get(MAPN.EN_SHORT.get(mp, mp), mp)
            except Exception:                                   # noqa: BLE001
                v["map"] = mp
        if ill:
            a = PLN.ILL.get(ill) or PLN.ILL["none"]
            v.update(ill=a[0], ill_gen=a[1], ill_acc=a[2], ill_ins=a[3])
        if sym.get("lack"):
            v["lack"] = PL.LACK.get(sym["lack"], PL.LACK["food"])
        if sym.get("names"):
            v["names"] = _join(sym["names"], PL.AND)
    else:
        v["E"] = D.FACTION[fk]["enemies"]
        if mp:
            try:
                import clan_chronicle_maps as MAPN
                mp = MAPN.EN_SHORT.get(mp, mp)
            except Exception:                                   # noqa: BLE001
                pass
            v["map"] = mp if mp in EN.NO_ARTICLE or mp.lower().startswith("the ") else "the " + mp
        if ill:
            nm, an = (D.ILLNESS[ill][0], D.ILLNESS[ill][1]) if ill in D.ILLNESS else ("sickness", "a sickness")
            v.update(ill=nm, ill_a=an)
        if sym.get("lack"):
            v["lack"] = EN.LACK.get(sym["lack"], EN.LACK["food"])
        if sym.get("names"):
            v["names"] = _join(sym["names"], EN.AND)
    return v


def _join(names, and_):
    names = [str(n) for n in names]
    return names[0] if len(names) == 1 else ", ".join(names[:-1]) + and_ + names[-1]


def render(sent, lang="en"):
    """One stored sentence [lid "jn/<pool>.<index>", params {"p": {letter: [name, gender]}, "s": symbols}] in a language; "" when the line set no longer has it."""
    try:
        lid, params = sent
        pool, i = lid[3:].rsplit(".", 1)
        i = int(i)
        people = {k: {"n": str(v[0]), "g": v[1] if v[1] in CS.PRON else "n"} for k, v in (params.get("p") or {}).items()}
        sym = params.get("s") or {}
        lang = "pl" if PLN.norm_lang(lang) == "pl" else "en"
        if lang == "pl":
            t = PLN.render(PL.POOLS[pool][i], people, _vars(sym, "pl"))
        else:
            t = CS.render(EN.POOLS[pool][i][1], people, _vars(sym, "en"))
        return t[:1].upper() + t[1:]
    except Exception:                                           # noqa: BLE001 - an unreadable sentence is left out, the entry stays
        return ""


class _Writer:
    def __init__(self, st, rng, fk, base):
        self.st, self.rng, self.fk, self.base = st, rng, fk, base

    def s(self, pool, people=None, fb=None, avoid=(), skip=(), **kw):
        """A sentence of the pool (else of the ledger pool `fb`) -> [lid, params] or None."""
        people = {k: p for k, p in (people or {}).items() if p}
        sym = dict(self.base)
        sym.update({k: v for k, v in kw.items() if v is not None})
        have = set(people) | set(sym) | {"E"}
        for pl in (pool, fb):
            if not pl:
                continue
            i = _pick(self.st, self.rng, pl, self.fk, have, avoid, skip if pl == pool else ())
            if i is not None:
                need = _need(pl, i)
                return ["jn/%s.%d" % (pl, i), {"p": {k: [p["n"], p.get("g", "n")] for k, p in people.items() if k in need},
                                               "s": dict({k: v for k, v in sym.items() if k in need}, f=self.fk)}]
        return None


# A raid line must not contradict the day's supplies: a lost raid can still bring enough home (the parts are the player's own), a won one can come home light.
# The lines of a won raid that speak of a good haul are left out on a day that fell short; the lines of a lost raid that speak of empty hands on a day that did not.
_HAUL_WIN = frozenset(i for i, (_s, t) in enumerate(EN.POOLS["raid_win"]) if re.search(r"crates|more than they left|strip|stripped|paid|what they carried|supplies, and we took|hoped for|carrying|packs are full|in the bags|more in the pot", t))
_EMPTY_LOSS = frozenset(i for i, (_s, t) in enumerate(EN.POOLS["raid_loss"]) if re.search(r"empty|nothing|lighter|did not get what|what it costs us|most of what was in it|what they could|without eating", t))


# ------------------------------------------------------------------ the day
def snapshot(st):
    """The roster before the day (clan_story.on_day takes it before story_day): {id: [name, gender, role, state, illness]}."""
    return {"p": {int(p["i"]): [p["n"], p.get("g", "n"), p.get("r", ""), p.get("s", "h"), p.get("il", "")] for p in (st or {}).get("people", [])},
            "n": len((st or {}).get("people", []))}


def _names(ps, limit=4):
    return [p["n"] for p in ps[:limit]]


def _tone_rank(t):
    return {"bad": 3, "warn": 2, "good": 1}.get(t, 0)


def compose(st, before, newc, r, rng):
    """The record of the day just played (see the module doc).  Pure but for the used-line lists in st["jn"]."""
    fk = CS._fkey(st["fac"])
    day = int(r.get("day", int(newc.get("day", 1)) - 1)) + 1                  # the clan day the match was (days done before it + 1)
    week = (day - 1) // 7 + 1
    H, U, S = int(newc["healthy"]), int(newc["hungry"]), int(newc["sick"])
    size = H + U + S
    status = int(newc.get("status", clan.ALIVE))
    m = r.get("match") or {}
    left = bool(r.get("left"))
    sup, need = int(r.get("supplies", 0)), int(r.get("needed", 0))
    mp = str(m.get("map") or "")
    win = 1 if m.get("win") is True else 0 if m.get("win") is False else -1
    k, x, rv, hs, dw = (int(m.get(q, 0) or 0) for q in ("kills", "execs", "revives", "headshots", "downs"))
    W = _Writer(st, rng, fk, {"size": size, "week": week})
    was = before.get("p") or {}
    now = {int(p["i"]): p for p in st["people"]}
    away = {int(i) for i in ((st.get("ch") or {}).get("away") or {})}
    deaths = [d for d in st.get("dead", []) if int(d["i"]) in was and int(d["i"]) not in now]
    joined = [p for i, p in now.items() if i not in was]
    old = [p for i, p in now.items() if i in was]
    new_sick = [p for p in old if p["s"] == "s" and was[int(p["i"])][3] != "s"]
    recovered = [p for p in old if p["s"] != "s" and was[int(p["i"])][3] == "s"]
    new_hungry = [p for p in old if p["s"] == "u" and was[int(p["i"])][3] == "h"]
    fed = [p for p in old if p["s"] == "h" and was[int(p["i"])][3] == "u"]
    evk, evt, evn = int(r.get("evk", 0)), int(r.get("evt", 0)), int(r.get("evn", 0)) % len(EN.EVENT_NAMES)
    evl, evg = int(r.get("evl", 0)), int(r.get("evg", 0))
    horde = evk == clan.EV_ATTACK and int(r.get("evn", 0)) == clan.AN_HORDE    # the attack was a horde of infected (re/clan-events-1117.md)
    per = {}                                                                   # member id -> the sentence about them (the status cards use it)
    paras = []
    tone = "info"

    def worse(t):
        nonlocal tone
        if _tone_rank(t) > _tone_rank(tone):
            tone = t

    # ---- THE RAID
    raid = []
    kw = {"map": mp or None}
    if left:
        raid.append(W.s("raid_left", **kw))
        worse("warn")
    elif int(r.get("parts", 0)) <= 0 and sup <= 0:
        raid.append(W.s("raid_idle", **kw))
        worse("warn")
    elif mp or m:
        pool = "raid_win" if win == 1 else "raid_loss" if win == 0 else "raid_draw"
        raid.append(W.s(pool, skip=_HAUL_WIN if pool == "raid_win" and sup < need else _EMPTY_LOSS if pool == "raid_loss" and sup >= need else (), **kw))                          # (a spent pool: no sentence - the facts line of the entry already says where and how it went; never a repeat)
        deeds = [(x / 2.0, "deed_x", {"x": x}), (rv / 2.0, "deed_r", {"r": rv}), (hs / 4.0, "deed_hs", {"hs": hs}), (dw / 3.0, "deed_dw", {"dw": dw}), (k / 10.0, "deed_k", {"k": k})]
        best = max(deeds, key=lambda q: q[0])
        if best[0] >= 1.0:
            raid.append(W.s(best[1], **best[2]))
        worse("good" if win == 1 else "warn" if win == 0 else "info")
    raid = [q for q in raid if q]
    raid_at = len(paras)
    if raid:
        paras.append(["raid", "", raid])

    # ---- SUPPLIES
    if need > 0:
        sr = r.get("sup") or {}
        lack = str(sr.get("cause") or "") or None
        short, over = max(0, need - sup), max(0, sup - need)
        if sup <= 0:
            pool = "sup_none"
        elif sup >= need + PLENTY_OVER:
            pool = "sup_plenty"
        elif sup >= need:
            pool = "sup_ok"
        elif short * 3 < need:
            pool = "sup_short"
        else:
            pool = "sup_bad"
        q = W.s(pool, sup=sup, need=need, short=short, over=over, lack=lack if lack in EN.LACK else None)
        if q:
            paras.append(["sup", "", [q]])
        worse("bad" if pool in ("sup_bad", "sup_none") else "warn" if pool == "sup_short" else "info")

    # ---- THE CAMP: the members whose state changed
    camp = []
    attack_now = evk == clan.EV_ATTACK

    def person(pool, fb, p, extra=None, **kw2):
        ppl = {"A": p}
        ppl.update(extra or {})
        q = W.s(pool, ppl, fb=fb, **kw2)
        if q:
            camp.append(q)
            per[int(p["i"])] = q
        return q

    if deaths:
        worse("bad")
        if len(deaths) > 3:
            q = W.s("f_dead_names" if attack_now else "death_many", fb="f_dead_names", n=len(deaths), names=_names(deaths, 3))
            if q:
                camp.append(q)
        else:
            for i, d in enumerate(deaths):
                c = str(d.get("c") or "illness")
                pool = {"attack": "death_attack", "illness": "death_illness", "mercy": "death_mercy", "starved": "death_starved", "lost": "death_lost",
                        "walkout": "death_walkout", "suicide": "death_suicide", "bite": "death_bite", "bite_kin": "death_bite", "turned": "death_turned"}.get(c, "death_illness")
                if pool == "death_attack" and horde:
                    pool = "death_horde"
                person(pool, "f_death", d, ill=(d.get("il") or "fever") if pool == "death_illness" else None)
                kin = now.get(int(d.get("k") or 0))
                if i == 0 and kin and int(kin["i"]) not in away:
                    q = W.s("kin", {"A": d, "B": kin})
                    if q:
                        camp.append(q)
    gain_ev = evk == clan.EV_GROWTH and evg > 0
    groups = (("sick", new_sick), ("join", joined), ("recover", recovered), ("hungry", new_hungry), ("fed", fed))
    for kind, ps in groups:
        ps = [p for p in ps if kind == "join" or int(p["i"]) not in away]
        if not ps:
            continue
        room = CAMP_MAX - len(camp)
        if kind == "sick":
            worse("warn")
        elif kind == "hungry":
            worse("warn")
        elif kind in ("join", "recover"):
            worse("good")
        if kind == "fed" and (room < 2 or len(ps) > 2):
            continue                                                             # the least of the news: only when the day has room for it
        many = {"sick": "sick_many", "join": "join_many", "hungry": "hungry_many"}.get(kind)
        fbm = {"sick": "f_more_sick", "join": "f_join_names", "recover": "f_more_recover", "hungry": "f_more_hungry", "fed": None}[kind]
        if kind == "join" and gain_ev:                                          # the event paragraph tells that they came: here only who they are
            q = W.s("f_join_names", names=_names(ps))
            if q:
                camp.append(q)
            continue
        if len(ps) >= 3 or room < len(ps):
            q = W.s(many, fb=fbm, n=len(ps), names=_names(ps)) if many else W.s(fbm, names=_names(ps)) if fbm else None
            if q:
                camp.append(q)
            continue
        for p in ps:
            if kind == "sick":
                person("sick_spores" if p.get("il") == "spores" else "sick", "f_sick", p, ill=p.get("il") or "fever")
            elif kind == "join":
                person("join", "f_join", p)
            elif kind == "recover":
                person("recover", "f_recover", p)
            elif kind == "hungry":
                person("hungry", "f_hungry", p)
            else:
                person("fed", "f_fed", p)
    if camp:
        paras.append(["camp", "", camp])

    # ---- the EVENT: settled today, or starting with the next match
    ev = []
    cap = ""
    if evk == clan.EV_ATTACK:
        cap = "hatk" if horde else "atk"
        ev.append(W.s(cap + "%d" % max(0, min(3, evt)), fb="f_" + cap, lost=evl) if evl else W.s(cap + "_none", avoid=[]))
        worse("bad" if evl else "warn")
    elif evk == clan.EV_GROWTH:
        cap = "g%d" % evn
        ev.append(W.s(("gwin%d" if evg > 0 else "gfail%d") % evn, fb="f_gwin" if evg > 0 else "f_gfail", gain=evg))
        worse("good" if evg > 0 else "info")
    nk, nn = clan.event_today(int(newc.get("day", 0))) if status == clan.ALIVE else (clan.EV_NONE, 0)
    start = None
    if nk == clan.EV_ATTACK:
        start = ("hatk", W.s("hwarn")) if nn == clan.AN_HORDE else ("atk", W.s("warn"))
        worse("warn")
    elif nk == clan.EV_GROWTH:
        start = ("g%d" % (nn % len(EN.EVENT_NAMES)), W.s("gstart%d" % (nn % len(EN.EVENT_NAMES))))
    ev = [q for q in ev if q]
    if ev:
        paras.append(["event", cap, ev])
    if start and start[1]:
        paras.append(["event", start[0], [start[1]]])

    # ---- NOTES: the turn of a week, a size the clan reached, the end; else a line of camp life on a thin day
    note = []
    endcap = "note"
    if status == clan.DEAD:
        note.append(W.s("dead", avoid=[]))
        endcap = "end"
        worse("bad")
    elif status == clan.WON:
        note.append(W.s("won", avoid=[]))
        endcap = "end"
        worse("good")
    else:
        if day > 1 and (day - 1) % 7 == 0 and ("week%d" % week) in EN.POOLS:
            note.append(W.s("week%d" % week))
        sz = st.setdefault("jn", {}).setdefault("sz", [])
        for mark in (10, 20, 30, 50):
            if size >= mark > int(before.get("n", 0)) and mark not in sz:
                sz.append(mark)
                note.append(W.s("size%d" % mark))
        count = sum(len(p[2]) for p in paras) + len([q for q in note if q])
        if count < NOTE_BELOW:
            pool = "note_grim" if (U + S) * 3 >= size and size else "note_tense" if U + S else "note_good"
            able = [p for p in st["people"] if KD.can_fight(p) and p["s"] != "s" and int(p["i"]) not in away and int(p["i"]) not in per]
            rng.shuffle(able)
            note.append(W.s(pool, {"A": able[0] if able else None, "B": able[1] if len(able) > 1 else None}))
    note = [q for q in note if q]
    if note:
        paras.append([endcap, "", note])

    if not paras and (mp or left):                                                # every story line of the day's pools is spent: the plain ledger sentence, so no entry is ever empty
        q = W.s("f_raid_left") if left else W.s("f_raid_win" if win == 1 else "f_raid_loss" if win == 0 else "f_raid_draw", map=mp)
        if q:
            paras.insert(raid_at, ["raid", "", [q]])

    # ---- the headline: the day's strongest fact
    T = W.s
    if status == clan.DEAD:
        title = T("t_dead")
    elif status == clan.WON:
        title = T("t_won")
    elif evk == clan.EV_ATTACK:
        title = T("t_hatk" if horde else "t_atk", lost=evl) if evl else T("t_hatk_none" if horde else "t_atk_none")
    elif len(deaths) > 2:
        title = T("t_death_n", n=len(deaths))
    elif len(deaths) == 2:
        title = T("t_death2", {"A": deaths[0], "B": deaths[1]})
    elif deaths:
        title = T("t_death", {"A": deaths[0]})
    elif evk == clan.EV_GROWTH:
        title = T("t_gwin", gain=evg) if evg > 0 else T("t_gfail")
    elif nk == clan.EV_ATTACK:
        title = T("t_hwarn" if nn == clan.AN_HORDE else "t_warn")
    elif nk == clan.EV_GROWTH:
        title = T("t_gstart%d" % (nn % len(EN.EVENT_NAMES)))
    elif len(joined) > 1:
        title = T("t_join_n", n=len(joined))
    elif joined:
        title = T("t_join", {"A": joined[0]})
    elif len(new_sick) > 1:
        title = T("t_sick_n", n=len(new_sick))
    elif new_sick:
        title = T("t_sick", {"A": new_sick[0]})
    elif need and sup <= 0:
        title = T("t_none")
    elif need and (need - sup) * 3 >= need:
        title = T("t_bad", short=need - sup)
    elif len(new_hungry) > 1:
        title = T("t_hungry", n=len(new_hungry))
    elif recovered:
        title = T("t_recover", {"A": recovered[0]})
    elif left:
        title = T("t_left")
    elif mp and win == 1:
        title = T("t_win", map=mp)
    elif mp and win == 0:
        title = T("t_loss", map=mp)
    elif need and sup >= need + PLENTY_OVER:
        title = T("t_plenty")
    elif mp:
        title = T("t_raid", map=mp)
    else:
        title = T("t_quiet")
    rec = {"v": REC_V, "d": day, "tone": tone, "h": H, "u": U, "s": S, "dn": size - int(before.get("n", size)), "sup": sup, "need": need, "map": mp, "win": win,
           "k": k, "x": x, "r": rv, "hs": hs, "dw": dw, "left": int(left), "ti": title, "pa": paras[:MAX_PARAS]}
    return rec, per


def _merge(old, rec):
    """A second match on the same clan day (a day that did not count: late join, idle): its paragraphs follow the first match's; the numbers are the latest."""
    out = dict(rec)
    out["pa"] = (list(old.get("pa") or []) + list(rec.get("pa") or []))[:MAX_PARAS]
    out["dn"] = int(old.get("dn", 0)) + int(rec.get("dn", 0))
    if _tone_rank(old.get("tone")) > _tone_rank(rec.get("tone")):
        out["tone"], out["ti"] = old.get("tone"), old.get("ti")
    return out


# ------------------------------------------------------------------ database
def ensure(c):
    c.execute(SCHEMA)


def purge(c, tid):
    try:
        c.execute("DELETE FROM clan_journal WHERE token_id=?", (tid,))
    except Exception:                                           # noqa: BLE001 - no table yet
        pass


def _get(c, tid, day):
    try:
        row = c.execute("SELECT data FROM clan_journal WHERE token_id=? AND day=?", (tid, int(day))).fetchone()
        return json.loads(row[0]) if row else None
    except Exception:                                           # noqa: BLE001
        return None


def _put(c, tid, day, jid, rec):
    c.execute("INSERT OR REPLACE INTO clan_journal(token_id, day, id, data) VALUES(?,?,?,?)", (tid, int(day), int(jid), json.dumps(rec, separators=(",", ":"), ensure_ascii=False)))


def _rng(st, salt):
    return random.Random("jn:%s:%s:%s:%s" % (st.get("seed"), st.get("run"), st.get("n"), salt))


def on_new_run(c, tid, st):
    """The founding entry (day 0) of a new clan; the old run's entries go."""
    ensure(c)
    purge(c, tid)
    fk = CS._fkey(st["fac"])
    st.pop("jn", None)
    W = _Writer(st, _rng(st, "new"), fk, {"size": len(st["people"]), "week": 1})
    q = W.s("founding")
    n = len(st["people"])
    rec = {"v": REC_V, "d": 0, "tone": "info", "h": n, "u": 0, "s": 0, "dn": 0, "sup": 0, "need": 0, "map": "", "win": -1, "k": 0, "x": 0, "r": 0, "hs": 0, "dw": 0, "left": 0,
           "ti": W.s("t_founding"), "pa": [["start", "", [q]]] if q else []}
    _put(c, tid, 0, st.get("n", 0), rec)
    return rec


def on_day(c, tid, st, before, newc, r):
    """After clan_story wrote the day's feed rows: compose the day's entry, store it, give the status cards their lines.  Returns the record."""
    ensure(c)
    have = c.execute("SELECT COUNT(*) FROM clan_journal WHERE token_id=?", (tid,)).fetchone()[0]
    if not have and int(newc.get("day", 0)) > 1:
        try:
            backfill(c, tid, st)
        except Exception as ex:                                 # noqa: BLE001 - the backfill is a courtesy
            sys.stderr.write("clan_journal backfill failed: %r\n" % (ex,))
    rng = _rng(st, "day%s" % newc.get("day"))
    rec, per = compose(st, before, newc, r, rng)
    old = _get(c, tid, rec["d"])
    if old and not int(r.get("counted", 1)) or (old and old.get("open")):
        rec = _merge(old, rec)
    if not int(r.get("counted", 1)):
        rec["open"] = 1                                         # the clan day is not over: the next match of it is added to this entry
    _put(c, tid, rec["d"], st.get("n", 0), rec)
    try:
        status_lines(st, per, rng)
    except Exception as ex:                                     # noqa: BLE001
        sys.stderr.write("clan_journal status lines failed: %r\n" % (ex,))
    return rec


def add_perk(c, tid, st, day, cat, who, mapname=""):
    """A supply perk was used in the match of clan day `day` (clan_perks.on_day): ONE sentence, once a day, appended to that entry's raid paragraph.  Returns True
    when a sentence was added (a spent pool adds nothing: the perk worked, the journal just does not say it twice)."""
    rec = _get(c, tid, day)
    if not rec or rec.get("pk"):
        return False
    pool = "perk_" + {"med": "med", "ammo": "ammo", "mat": "mat", "food": "food", "water": "water"}.get(cat, "")
    if pool not in EN.POOLS or not who:
        return False
    W = _Writer(st, _rng(st, "pk%s%s" % (day, cat)), CS._fkey(st["fac"]), {})
    q = W.s(pool, {"A": who}, map=mapname or None)
    if not q:
        return False
    for p in rec.get("pa") or []:
        if p[0] == "raid":
            p[2].append(q)
            break
    else:
        rec.setdefault("pa", []).insert(0, ["raid", "", [q]])
    rec["pk"] = 1
    row = c.execute("SELECT id FROM clan_journal WHERE token_id=? AND day=?", (tid, int(day))).fetchone()
    _put(c, tid, day, row[0] if row else st.get("n", 0), rec)
    return True


# ------------------------------------------------------------------ the STATUS UPDATES cards (tools/clan_status.py)
_ST_POOL = {1: ("hungry", "f_hungry"), 2: ("st_sad", None), 3: ("sick", "f_sick"), 4: (None, "f_death"), 5: ("st_injured", None), 6: ("recover", "f_recover"),
            7: ("join", "f_join"), 8: ("st_depressed", None), 9: ("st_shock", None)}


def status_lines(st, per, rng):
    """Every status event of today gets its own sentence e["jl"] = [lid, params]: the journal's sentence about that member when the entry has one, else a line of
 the state's pool. No two pending cards carry the same line."""
    S = ((st.get("ch") or {}).get("stat")) or {}
    day = int(st.get("day", 0) or 0)
    ev = S.get("ev") or []
    fk = CS._fkey(st["fac"])
    W = _Writer(st, rng, fk, {})
    shown = {}                                                  # pool -> indexes on the pending cards
    for e in ev:
        if e.get("jl"):
            pool, i = e["jl"][0][3:].rsplit(".", 1)
            shown.setdefault(pool, set()).add(int(i))
    sick = {int(p["i"]): p.get("il") or "fever" for p in st.get("people", []) if p.get("s") == "s"}
    for e in ev:
        if int(e.get("d", -1)) != day or e.get("jl"):
            continue
        q = per.get(int(e["i"]))
        if not q:
            pool, fb = _ST_POOL.get(int(e.get("c", 0)), (None, None))
            who = {"n": e["n"], "g": e.get("g", "n")}
            ill = sick.get(int(e["i"])) if int(e.get("c", 0)) == 3 else None
            if int(e.get("c", 0)) == 4:                           # a death the entry only counted (a day with many dead): the line of how THIS member died
                d = next((x for x in st.get("dead", []) if int(x["i"]) == int(e["i"])), {})
                c = str(d.get("c") or "illness")
                pool = {"attack": "death_attack", "illness": "death_illness", "mercy": "death_mercy", "starved": "death_starved", "lost": "death_lost", "walkout": "death_walkout",
                        "suicide": "death_suicide", "bite": "death_bite", "bite_kin": "death_bite", "turned": "death_turned"}.get(c, "death_illness")
                if pool == "death_attack" and clan.attack_story(int(d.get("d", -9))) == clan.AN_HORDE:
                    pool = "death_horde"
                ill = (d.get("il") or "fever") if pool == "death_illness" else None
            q = W.s(pool, {"A": who}, fb=fb, avoid=shown.get(pool, set()), ill=ill) if pool else W.s(fb, {"A": who}) if fb else None
        if q:
            e["jl"] = q
            e["ln"] = ""
            pool, i = q[0][3:].rsplit(".", 1)
            shown.setdefault(pool, set()).add(int(i))


# ------------------------------------------------------------------ a clan that lived before the journal: plain ledger entries of the days the old data still holds
def backfill(c, tid, st):
    """Entries for the past days of a running clan, from what is still stored: the chronicle's match log (map, verdict, supplies) and the diary rows that name who
    died / fell sick / recovered / joined.  Ledger sentences only (pools f_*): nothing is invented and no story line is spent."""
    import clan_chronicle as CH
    fk = CS._fkey(st["fac"])
    W = _Writer(st, random.Random(0), fk, {})
    days = {}
    try:
        for m in (CH.public(c, tid, "en") or {}).get("matches") or []:
            days.setdefault(int(m.get("d", 0)), {})["m"] = m
    except Exception:                                           # noqa: BLE001
        pass
    try:
        rows = c.execute("SELECT id, day, kind, params FROM clan_feed WHERE token_id=? ORDER BY id", (tid,)).fetchall()
    except Exception:                                           # noqa: BLE001
        rows = []
    for i, day, kind, params in rows:
        k = str(kind or "")
        pool = "f_death" if k.startswith("death_") else "f_join" if k == "join" else "f_sick" if k == "sick" else "f_recover" if k == "recovery" else None
        if not pool or not params:
            continue
        try:
            pj = json.loads(params)
            a = (pj.get("p") or {}).get("A")
            if not a:
                continue
            ill = (pj.get("s") or {}).get("ill")
            d = days.setdefault(int(day), {})
            d.setdefault("p", []).append((pool, {"n": a[0], "g": a[1]}, ill if ill in D.ILLNESS else "fever"))
            d["id"] = max(int(d.get("id", 0)), int(i))
        except (ValueError, TypeError, IndexError):
            continue
    cur = int(st.get("day", 0))
    for day, d in sorted(days.items()):
        if day <= 0 or day >= cur:                              # (today's entry is written by on_day)
            continue
        m = d.get("m") or {}
        paras = []
        mp = str(m.get("map") or "")
        win = 1 if m.get("win") is True else 0 if m.get("win") is False else -1
        if mp:
            paras.append(["raid", "", [W.s("f_raid_win" if win == 1 else "f_raid_loss" if win == 0 else "f_raid_draw", map=mp)]])
        sup, need = int(m.get("sup", 0) or 0), int(m.get("need", 0) or 0)
        if need:
            paras.append(["sup", "", [W.s("f_sup", sup=sup, need=need)]])
        camp = [W.s(pool, {"A": who}, ill=ill if pool == "f_sick" else None) for pool, who, ill in (d.get("p") or [])[:CAMP_MAX]]
        if camp:
            paras.append(["camp", "", [q for q in camp if q]])
        dead = [who for pool, who, _ in d.get("p") or [] if pool == "f_death"]
        title = W.s("t_death", {"A": dead[0]}) if dead else W.s("t_win", map=mp) if mp and win == 1 else W.s("t_loss", map=mp) if mp and win == 0 else W.s("t_raid", map=mp) if mp else W.s("t_quiet")
        rec = {"v": REC_V, "d": day, "tone": "bad" if dead else "info", "h": -1, "u": -1, "s": -1, "dn": 0, "sup": sup, "need": need, "map": mp, "win": win,
               "k": 0, "x": 0, "r": 0, "hs": 0, "dw": 0, "left": 0, "ti": title, "pa": paras, "old": 1}
        _put(c, tid, day, int(d.get("id", 0)), rec)


# ------------------------------------------------------------------ reading
def entries(c, tid, lang="en", days_done=None):
    """The clan's journal, oldest day first, rendered: [{"day", "week", "dow", "id", "title", "tone", "map", "win", "sup", "need", "h", "u", "s", "size", "dn", "k",
    "x", "r", "hs", "dw", "left", "paras": [(caption, text)]}].  [] without a table / rows.  Never a day the clan has not reached (a restored booking)."""
    lang = "pl" if PLN.norm_lang(lang) == "pl" else "en"
    T = LANG_POOLS[lang]
    try:
        rows = c.execute("SELECT day, id, data FROM clan_journal WHERE token_id=? ORDER BY day", (tid,)).fetchall()
    except Exception:                                           # noqa: BLE001
        return []
    if days_done is None:
        days_done = CS._days_done(c, tid)
    out = []
    for day, jid, data in rows:
        if days_done is not None and int(day) > int(days_done) + 1:
            continue
        try:
            rec = json.loads(data)
        except ValueError:
            continue
        fk = "W"
        paras = []
        for kind, cap, sents in rec.get("pa") or []:
            text = " ".join(t for t in (render(q, lang) for q in sents) if t)
            if not text:
                continue
            for q in sents:
                fk = (q[1].get("s") or {}).get("f", fk)
            if cap == "hatk":
                caption = T.HORDE_NAME
            elif cap == "atk":
                en = PLN.ENEMY[fk][0] if lang == "pl" else D.FACTION[fk]["enemies"]
                caption = T.ATTACK_NAME.replace("{E}", en).upper()
            elif cap.startswith("g") and cap[1:].isdigit():
                caption = T.EVENT_NAMES[int(cap[1:]) % len(T.EVENT_NAMES)]
            else:
                caption = T.CAPTIONS.get(kind, "")
            paras.append((caption, text))
        d = int(day)
        h, u, s = int(rec.get("h", -1)), int(rec.get("u", -1)), int(rec.get("s", -1))
        out.append({"day": d, "week": (max(d, 1) - 1) // 7 + 1, "dow": (d - 1) % 7 + 1 if d > 0 else 0, "id": int(jid or 0), "title": render(rec.get("ti"), lang) if rec.get("ti") else "",
                    "tone": rec.get("tone", ""), "map": _vars({"map": rec.get("map")}, "pl").get("map", "") if lang == "pl" and rec.get("map") else rec.get("map", ""),
                    "win": int(rec.get("win", -1)), "sup": int(rec.get("sup", 0)), "need": int(rec.get("need", 0)), "h": h, "u": u, "s": s, "size": h + u + s if h >= 0 else -1,
                    "dn": int(rec.get("dn", 0)), "k": int(rec.get("k", 0)), "x": int(rec.get("x", 0)), "r": int(rec.get("r", 0)), "hs": int(rec.get("hs", 0)),
                    "dw": int(rec.get("dw", 0)), "left": int(rec.get("left", 0)), "paras": paras})
    return out
