"""Clan A-Life: an offline, server-side simulation of each player's clan that narrates and enriches the authoritative 2013 clan numbers.
Design + rules: re/clan-alife-1019.md. Switch: tools/clan_alife.txt (next to daemon.py; default ON since, 'off' / '0' turns it off) or env T2R_CLAN_ALIFE=1/0.

What it is.  tools/clan.py decides how many survivors are healthy / hungry / sick and how many die or join; tools/clan_story.py names them and writes
a diary line or two per clan day.  This module adds the life AROUND those numbers, per player, persistent in the DB (table clan_alife):
  * people get persistent personalities (two traits, a past, bonds, a skill) and a role-based routine;
  * stories run across DAYS as threads: expeditions that leave and come back (with a haul, empty-handed, hurt, short of one), minor injuries on
    light duty that heal, building projects that advance on good days and stall on bad ones, trade meetings announced days before, threats seen
    on the watch that escalate or pass, quarrels that end in a reconciliation, a mentor and an apprentice, the dead remembered a week later;
  * the real day feeds in: a deficit / surplus tally ({sup}/{need} are the real numbers) drives the ration politics, a real join is welcomed with a
    past, a real death is mourned, a real recovery is credited to the one who sat up with the patient, a real attack is followed by a night of watch.
It NEVER changes a number or a person's health state: it reads clan_story's roster (st["people"], st["dead"], st["morale"], st["ss"] / ["ds"]) and
the day's result r, and only writes text.  Sick people are never sent anywhere, injuries are "light duty" (the person stays healthy and counted
healthy), nobody is mentioned as alive after dying, nobody is in camp while out on an expedition.

Output.  (1) one to three feed rows per clan day, kind "alife" (stored in clan_feed next to the diary rows: same fields, so the launcher, the
update server view and the admin site show them unchanged; the Polish form is rendered at read time from lid + params like every other row);
(2) menu ticker lines (menu_lines of clan_story mixes TICKER_SHARE of them in): single sentences about CURRENT facts of the simulated life.
Text: tools/clan_alife_text_[a-f].py (EN + PL side by side: weather opener + core, lexicon in clan_alife_lex.py).
Anti-repeat: per player, in the DB state: every template id has [last day, count]; a template (core or weather opener) is used ONCE per clan
run: when its pool is spent the event writes nothing (no repeated sentence anywhere in the clan text). No stock codas: a row is
[weather opener] + core, the opener only on a day the weather turned.  Determinism: everything is a pure function of (token id, run, day, state): restarts change nothing.
"""
import json
import os
import random
import re
import sys
import time
import zlib

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import clan                                                  # noqa: E402
import clan_story as CS                                      # noqa: E402
import clan_story_data as D                                  # noqa: E402
import clan_alife_lex as X                                   # noqa: E402
import clan_kids as KD                                       # noqa: E402  (kids are never fighters)
import clan_alife_text_a as TA                               # noqa: E402
import clan_alife_text_b as TB                               # noqa: E402
import clan_alife_text_c as TC                               # noqa: E402
import clan_alife_text_d as TD                               # noqa: E402
import clan_alife_text_e as TE                               # noqa: E402
import clan_alife_text_f as TF                               # noqa: E402 (creativity pass)
import clan_alife_text_g as TG                               # noqa: E402 (camp incidents: re/clan-events-1117.md)

STATE_V = 1
WINDOW_DAYS = 999                   # once per run (a run is at most 85 days): a spent pool writes nothing
OPENER_DAYS = 999
OPENER_P = 0.5                      # chance of a weather opener on a day the weather turned (at most one a day)
DAY_MIN_ROWS, DAY_MAX_ROWS = 2, 3   # feed rows per clan day
TICKER_SHARE = 3                    # of the menu's 6 ticker lines this many come from the A-Life facts (2 stored events, 1 classic 2013 line)
MIN_CLAN = 3                        # below this the clan_story solo / duo voices own the feed
INCIDENTS = os.environ.get("T2R_CLAN_INCIDENTS", "1") != "0"   # the camp incidents of re/clan-events-1117.md (text only; tests switch it to compare)
MEM_CAUSES = ("illness", "starved", "mercy", "bite", "bite_kin", "attack", "turned")
SWITCH_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "clan_alife.txt")

TRAIT_IDS = ["stubborn", "joker", "quiet", "superstitious", "generous", "hoarder", "hothead", "tinkerer", "storyteller", "nervous", "optimist", "grumbler"]
TRAIT_LABEL = {"stubborn": ("stubborn", "uparty"), "joker": ("a joker", "dowcipniś"), "quiet": ("quiet", "małomówny"), "superstitious": ("superstitious", "przesądny"),
               "generous": ("generous", "hojny"), "hoarder": ("a hoarder", "chomik"), "hothead": ("hot-headed", "popędliwy"), "tinkerer": ("a tinkerer", "majsterkowicz"),
               "storyteller": ("a storyteller", "gawędziarz"), "nervous": ("nervous", "nerwowy"), "optimist": ("an optimist", "optymista"), "grumbler": ("a grumbler", "maruda")}

POOLS = {}
for _m in (TA, TB, TC, TD, TG):
    POOLS.update({k: list(v) for k, v in _m.POOLS.items()})
for _m in (TE, TF):                                         # parts E and F widen pools of A-D (E also adds the role / trait ticker lines)
    for _pool, _rows in _m.POOLS.items():
        POOLS.setdefault(_pool, []).extend(_rows)


def _tid(pool, en):
    return "%s~%08x" % (pool, zlib.crc32(en.encode("utf-8")) & 0xFFFFFFFF)


REG = {}                            # template id -> (pool, scope, tone, en, pl, letters, en vars, pl vars)
for _pool, _rows in POOLS.items():
    for _sc, _tone, _en, _pl in _rows:
        _id = _tid(_pool, _en)
        if _id in REG:
            raise ValueError("duplicate A-Life template " + _id)
        REG[_id] = (_pool, _sc, _tone, _en, _pl, X.letters_of(_en) | X.letters_of(_pl), X.vars_of(_en), X.vars_of(_pl))
BY_POOL = {}
for _id, _e in REG.items():
    BY_POOL.setdefault(_e[0], []).append(_id)


# ------------------------------------------------------------------ the switch
_sw = {"mtime": None, "val": False}


def enabled():
    """Default ON. env T2R_CLAN_ALIFE=1/0 wins; else the first word of tools/clan_alife.txt
    (0 / off / false / no turns it off; anything else, or no file, is on)."""
    e = os.environ.get("T2R_CLAN_ALIFE")
    if e is not None and e.strip():
        return e.strip().lower() in ("1", "on", "true", "yes")
    try:
        m = os.path.getmtime(SWITCH_FILE)
    except OSError:
        return True
    if _sw["mtime"] != m:
        try:
            with open(SWITCH_FILE, encoding="utf-8", errors="ignore") as f:
                w = (f.read().split() or [""])[0].strip().lower()
        except OSError:
            w = ""
        _sw.update(mtime=m, val=w not in ("0", "off", "false", "no"))
    return _sw["val"]


def _fk(st):
    return "S" if st["fac"] == clan.SERAPHITES else "W"


def _tone_ok(tone, morale):
    return (tone == "*" or (tone == "g" and morale >= 55) or (tone == "n" and 35 <= morale <= 70) or (tone == "b" and morale <= 45))


def _pp(p):
    return {"n": p["n"], "g": p["g"], "r": p["r"], "i": p["i"]}


# ------------------------------------------------------------------ storage
SCHEMA = "CREATE TABLE IF NOT EXISTS clan_alife(token_id TEXT PRIMARY KEY, state TEXT, updated REAL)"


def ensure(c):
    c.execute(SCHEMA)


def _new(tid, st):
    return {"v": STATE_V, "seed": tid, "run": st["run"], "fac": st["fac"], "day": -1, "P": {}, "T": [], "nid": 0, "mem": {}, "D": [], "done": [],
            "lastdest": [], "cool": {}, "stat": {"lines": 0, "rep": 0, "days": 0}, "ls": {}}


def load(c, tid):
    try:
        row = c.execute("SELECT state FROM clan_alife WHERE token_id=?", (tid,)).fetchone()
    except Exception:                                                   # noqa: BLE001 - no table yet
        return None
    if not row:
        return None
    try:
        al = json.loads(row[0])
    except ValueError:
        return None
    return al if isinstance(al, dict) and al.get("v") == STATE_V else None


def save(c, tid, al):
    cut = al["day"] - 120
    al["mem"] = {k: v for k, v in al["mem"].items() if v[0] >= cut}
    c.execute("INSERT INTO clan_alife(token_id,state,updated) VALUES(?,?,?) ON CONFLICT(token_id) DO UPDATE SET state=excluded.state,updated=excluded.updated",
              (tid, json.dumps(al, separators=(",", ":")), time.time()))


def reset(c, tid):
    """A new clan run (CHOOSE YOUR SIDE): the old simulation goes."""
    try:
        c.execute("DELETE FROM clan_alife WHERE token_id=?", (tid,))
    except Exception:                                                   # noqa: BLE001
        pass


# ------------------------------------------------------------------ people
def _rec(al, p, fk, fresh=False):
    """The persistent extras of one survivor (created on first sight, deterministic from the seed)."""
    k = str(p["i"])
    r = al["P"].get(k)
    if r is None:
        rng = random.Random("%s:%s:p%d" % (al["seed"], al["run"], p["i"]))
        jobs = X.pool_keys(X.JOBS, fk)
        origs = X.pool_keys(X.ORIGINS, fk)
        if p.get("r") == "kid":                                      # a kid's past is no fighter's past: no Scars, no raids, no patrols
            origs = [o for o in origs if not (KD.combat_text(X.ORIGINS[o][1], "en") or KD.combat_text(X.ORIGINS[o][2], "pl"))] or origs
            jobs = [j for j in jobs if not (KD.combat_text(X.JOBS[j][1], "en") or KD.combat_text(X.JOBS[j][2], "pl"))] or jobs
        r = {"t": rng.sample(range(len(TRAIT_IDS)), 2), "job": rng.choice(jobs), "orig": rng.choice(origs), "f": 0, "rv": 0, "pa": 0, "sk": 0, "lm": -99,
             "vg": -99, "ls": p["s"], "seen": 0}
        al["P"][k] = r
    return r


def _trait(r, n=0):
    return TRAIT_IDS[r["t"][n]]


# ------------------------------------------------------------------ choosing and composing text
def _avail(sym):
    return set(X.expand_en(sym)), set(X.expand_pl(sym))


def _choose(al, pool, fk, morale, letters, av_en, av_pl, rng, day, window=WINDOW_DAYS, exclude=(), tones=None, record=True, people=None):
    """One template id of `pool` that fits the faction, the clan's mood and the people / variables at hand; never one used inside `window` days when
    another fits (the DB memory al["mem"]); None when nothing fits."""
    cands = []
    for tid in BY_POOL.get(pool, ()):
        _p, sc, tone, _en, _pl, lt, ve, vp = REG[tid]
        if sc not in ("*", fk) or tid in exclude or not (tone in tones if tones else _tone_ok(tone, morale)):
            continue
        if not lt <= letters or not ve <= av_en or not vp <= av_pl:
            continue
        if people and not KD.kid_safe(_en, people, _pl):                  # a kid is never in a combat, raid, patrol or weapon line
            continue
        cands.append(tid)
    if not cands:
        return None
    mem = al["mem"]
    fresh = [t for t in cands if t not in mem or day - mem[t][0] >= window]
    if not fresh:                                                   # the pool is spent for this run: nothing, never a repeat
        if record:
            sp = al["stat"].setdefault("spent", {})
            sp[pool] = sp.get(pool, 0) + 1
        return None
    never = [t for t in fresh if t not in mem]
    pick = rng.choice(never if never and rng.random() < 0.7 else fresh)
    if record:
        _note(al, pick, day)
    return pick


def _note(al, tid, day):
    m = al["mem"].get(tid)
    al["mem"][tid] = [day, (m[1] if m else 0) + 1]


def _render_ids(ids, people, sym, lang, fk):
    parts = []
    ve = vp = None
    for tid in ids:
        _p, _sc, _tone, en, pl, _lt, _ve, _vp = REG[tid]
        if lang == "pl":
            vp = vp or X.expand_pl(sym)
            parts.append(X.render(pl, people, vp, "pl", fk))
        else:
            ve = ve or X.expand_en(sym)
            parts.append(X.render(en, people, ve, "en", fk))
    return " ".join(parts)


def render_msg(lid, params, lang="en"):
    """A stored A-Life row (lid "al/<template ids joined by +>", params {"p": people, "s": sym}) in a language; None when a template is unknown."""
    if not lid or not lid.startswith("al/") or not isinstance(params, dict):
        return None
    ids = lid[3:].split("+")
    if any(i not in REG for i in ids):
        return None
    people = {k: {"n": str(v[0]), "g": v[1] if v[1] in CS.PRON else "n", "r": (v[2] if len(v) > 2 else "scavenger")} for k, v in params.get("p", {}).items()}
    sym = params.get("s", {})
    return _render_ids(ids, people, sym, "pl" if CS.PLN.norm_lang(lang) == "pl" else "en", sym.get("f", "W"))


def _base_sym(al, st, day):
    fk = _fk(st)
    week = clan.week_day(day)[0]
    return {"f": fk, "day": day, "week": week, "size": len(st["people"]), "season": X.season_of(week)}


def _weather(al, st, day):
    fk = _fk(st)
    season = X.season_of(clan.week_day(day)[0])
    w = {0: (4, 2, 1, 2, 1, 2), 1: (2, 2, 4, 2, 1, 1), 2: (3, 2, 1, 3, 1, 2)}[season]   # rain fog cold clear smoke wind
    rng = random.Random("%s:%s:wx:%d" % (al["seed"], al["run"], day // 2))
    return rng.choices(X.WEATHER, weights=w)[0]


MOODS = {"memorial": "grieving", "memorial_late": "grieving", "exp_lost": "grieving", "thr_enemy": "afraid", "thr_inf": "afraid", "thr_smoke": "afraid",
         "thr_up": "afraid", "thr_after": "grim", "rat_deficit": "worried", "rat_mild": "calm", "rat_streak_bad": "worried", "rat_surplus": "cheerful", "rat_streak_good": "hopeful",
         "arrive": "hopeful", "vigil": "worried", "vigil_spore": "afraid", "recovered": "hopeful", "proj_done": "cheerful", "exp_ret_good": "cheerful", "exp_recall": "worried"}


def _compose(al, st, ev, rng, day, wx, opener_ok=True):
    """One feed row from an event {pool, people{A..}, sym{...}, mood?}: [weather opener] + core. None when no core template fits (or its pool is spent)."""
    fk = _fk(st)
    morale = st["morale"]
    people = ev["people"]
    sym = dict(_base_sym(al, st, day), **ev.get("sym", {}))
    letters = set(people)
    av_en, av_pl = _avail(sym)
    # the core: never a template whose wording (with these very people) was already published inside the window - tried again with another template
    tried = set()
    core = None
    for _attempt in range(5):
        core = _choose(al, ev["pool"], fk, morale, letters, av_en, av_pl, rng, day, exclude=tried, record=False, people=people)
        if core is None:
            break
        text0 = _render_ids([core], people, sym, "en", fk)
        h0 = zlib.crc32(text0.encode("utf-8")) & 0xFFFFFFFF
        if KD.any_kid(people) and not (KD.kid_text_ok(text0, people) and KD.kid_text_ok(_render_ids([core], people, sym, "pl", fk), people, "pl")):
            tried.add(core)                                          # the filled-in line (an origin, a past, a keepsake) makes a kid a fighter: another template
            core = None
            continue
        if any(h == h0 and day - d0 < WINDOW_DAYS for h, d0 in al.get("tx", ())) and len(tried) < 4:
            tried.add(core)
            continue
        break
    if core is None:
        return None
    _note(al, core, day)
    ids = [core]
    wo = al.setdefault("wxo", [-99, ""])                            # [day, weather] of the last opener: one a day, only when the weather turned
    if opener_ok and ev.get("opener", True) and wo[0] != day and wo[1] != wx and rng.random() < OPENER_P:
        op = _choose(al, "wx_" + wx, fk, morale, set(), av_en, av_pl, rng, day, OPENER_DAYS)
        if op:
            ids.insert(0, op)
            al["wxo"] = [day, wx]
    text = _render_ids(ids, people, sym, "en", fk)
    tx = al.setdefault("tx", [])
    tx.append([zlib.crc32(_render_ids([core], people, sym, "en", fk).encode("utf-8")) & 0xFFFFFFFF, day])
    del tx[:-160]
    names = [people[k]["n"] for k in "ABCD" if k in people and re.search(r"(?<!\w)" + re.escape(people[k]["n"]) + r"(?!\w)", text)]
    mood = ev.get("mood") or MOODS.get(ev["pool"]) or ("hopeful" if morale >= 60 else "grim" if morale < 35 else "calm")
    al["stat"]["lines"] += 1
    return {"kind": "alife", "mood": mood, "text": text, "names": names, "lid": "al/" + "+".join(ids),
            "params": {"p": {k: [v["n"], v["g"], v.get("r", "scavenger")] for k, v in people.items()}, "s": sym}}


# ------------------------------------------------------------------ the day
class Day:
    """One simulated clan day. All randomness comes from rng (seeded by token, run, day): same inputs -> same day."""

    def __init__(self, al, st, newc, r, rng, story_msgs=()):
        self.al, self.st, self.rng = al, st, rng
        # the diary rows of the day (clan_story): whoever they name is in camp today; whoever got a "recovery" row needs no second recovery scene
        self.named = {n for m in story_msgs for n in (m.get("names") or [])}
        self.recovered_named = {n for m in story_msgs if m.get("kind") == "recovery" for n in (m.get("names") or [])}
        self.fk = _fk(st)
        self.day = int(st["day"])
        self.r = r or {}
        self.sup, self.need = int(self.r.get("supplies", 0)), int(self.r.get("needed", 0))
        self.deficit = self.sup < self.need
        self.alive = {p["i"]: p for p in st["people"]}
        self.events = []                                     # (drama, event dict)
        self.used = set()                                    # ids spotlighted today
        self.wx = _weather(al, st, self.day)

    # --- helpers
    def rec(self, p):
        return _rec(self.al, p, self.fk)

    def threads(self, kind):
        return [t for t in self.al["T"] if t["k"] == kind]

    def away(self):
        out = set()
        for t in self.threads("exp"):
            if t["d"] > self.day or t["s"] == self.day:
                out |= {i for i in t["a"] if i in self.alive}
        return out

    def hurt(self):
        return {t["a"][0] for t in self.threads("inj")}

    def free(self, role=None, exclude=(), states=("h", "u"), fight=False):
        """Survivors who are in camp, not on light duty, not already spotlighted today, in one of the given real states (default healthy or hungry - a hungry
        person still sits at the fire and argues about the bread; never a sick one). Expeditions, building and the watch ask for ("h",) only."""
        away, hurt = self.away(), self.hurt()
        away = away | {p["i"] for p in self.st["people"] if str(p["i"]) in ((self.st.get("ch") or {}).get("away") or {})}   # away in a story arc (tools/clan_arcs.py)
        out = [p for p in self.st["people"] if p["s"] in states and p["i"] not in away and p["i"] not in hurt and p["i"] not in self.used
               and p["i"] not in exclude and (role is None or p["r"] == role) and (not fight or KD.can_fight(p))]
        return out

    def pick(self, k, role_w=None, role=None, exclude=(), states=("h", "u"), fight=False):
        """k distinct free survivors, spotlight-fair: the longer since someone was last in a line the likelier they are.  fight=True (threats, watches, projects on the
        defences, trade meetings outside the wall, the attack's aftermath): grown people only, never a kid."""
        pool = self.free(role, exclude, states, fight)
        out = []
        while pool and len(out) < k:
            w = [(1.0 + min(14, self.day - self.rec(p)["lm"])) * ((role_w or {}).get(p["r"], 1.0)) for p in pool]
            q = self.rng.choices(pool, weights=w)[0]
            pool.remove(q)
            out.append(q)
        return out

    def person(self, i):
        return self.alive.get(i)

    def mark(self, *ps):
        for p in ps:
            if p is not None and "s" in p:                  # a living survivor (the dead are plain name dicts)
                self.used.add(p["i"])
                self.rec(p)["lm"] = self.day

    def add(self, drama, pool, people, sym=None, mood=None, opener=True, coda=True):
        letters = "ABCD"
        pe = {}
        for k, p in zip(letters, people):
            if p is not None:
                pe[k] = p
        ev = {"pool": pool, "people": {k: (_pp(v) if "s" in v else {"n": v["n"], "g": v["g"], "r": v.get("r", "scavenger")}) for k, v in pe.items()},
              "sym": sym or {}, "mood": mood, "opener": opener, "coda": coda}
        self.events.append((drama + self.rng.random() * 12, ev))
        self.mark(*people)

    def days_gone(self, t):
        return max(1, self.day - t["s"])

    # --- sync with the real roster
    def sync(self):
        al, st, day = self.al, self.st, self.day
        for p in st["people"]:
            self.rec(p)
        # the dead of today
        for d in st["dead"]:
            if d["d"] == day and not any(x["i"] == d["i"] for x in al["D"]):
                keep = self.rng.choice(sorted(k for k in X.KEEPS if not (d.get("r") == "kid" and KD.combat_text(X.KEEPS[k][0], "en"))))     # (a dead kid leaves no knife)
                al["D"].append({"i": d["i"], "n": d["n"], "g": d["g"], "r": d["r"], "c": d.get("c"), "d": day, "keep": keep, "k": d.get("k", 0)})
                self.dead_today = getattr(self, "dead_today", []) + [al["D"][-1]]
        del al["D"][:-10]
        for t in list(al["T"]):
            gone = [i for i in t["a"] if i not in self.alive]
            if not gone:
                continue
            if t["k"] == "exp":
                for i in gone:
                    d = next((x for x in al["D"] if x["i"] == i), None)
                    if d and d["c"] in ("lost", "walkout"):
                        t["x"].setdefault("lost", []).append(i)
                t["a"] = [i for i in t["a"] if i in self.alive]
                if not t["a"]:
                    al["T"].remove(t)
            elif t["k"] == "mem":
                pass
            else:
                t["a"] = [i for i in t["a"] if i in self.alive]
                if not t["a"] or t["k"] in ("inj", "men", "qrl"):
                    al["T"].remove(t)
        # a party member the day's diary rows put in camp: the party is home today (the return is narrated like any other)
        for t in self.threads("exp"):
            if t["s"] < day < t["d"] and any(self.alive[i]["n"] in self.named for i in t["a"] if i in self.alive):
                t["d"] = day
        # an expedition member who fell sick: the party is recalled today
        for t in self.threads("exp"):
            sick = [i for i in t["a"] if self.alive[i]["s"] == "s"]
            if sick and t["d"] >= day and t["s"] < day:
                t["d"] = day
                t["x"]["recall"] = sick[0]
        # injured people who fell ill or were unlucky: the injury thread ends silently
        for t in self.threads("inj"):
            p = self.alive.get(t["a"][0])
            if p is None or p["s"] != "h":
                al["T"].remove(t)

    # --- events from the real day
    def real_day(self):
        al, st, r, day = self.al, self.st, self.r, self.day
        newc_evk = int(r.get("evk", 0))
        # a real attack: the aftermath, and the threats that were being watched are over
        if newc_evk == clan.EV_ATTACK:
            for t in self.threads("thr"):
                al["T"].remove(t)
            a = self.pick(2, fight=True)
            if len(a) >= 2:
                self.add(88, "thr_after", a)
            elif a:
                pass
        # joins
        if getattr(self, "arrivals_ok", False) and day >= al["cool"].get("arr", -99) + 2 and (len(st["people"]) < 8 or self.rng.random() < 0.6):   # not every newcomer
            for p in [q for q in self.new_ids if q["s"] == "h"][:1]:
                al["cool"]["arr"] = day
                rec = self.rec(p)
                helper = self.pick(1, exclude={p["i"]})
                if helper:
                    self.add(80, "arrive", [p, helper[0]], {"orig": rec["orig"], "job": rec["job"]})
                    al["T"].append({"i": self._nid(), "k": "arr", "s": day, "d": day + 2, "a": [p["i"]], "x": {}})
                    self.used.add(p["i"])
        # deaths remembered
        for d in getattr(self, "dead_today", [])[:1]:
            if d["c"] not in MEM_CAUSES or day < al["cool"].get("mem", -99) + 3:         # after a massacre one scene, not twelve
                continue
            al["cool"]["mem"] = day
            k = self.alive.get(d.get("k")) if d.get("k") else None
            mourner = k if (k and k["i"] not in self.used and k["i"] not in self.away() and k["s"] != "s") else (self.pick(1) or [None])[0]
            if mourner is None:
                continue
            dp = {"n": d["n"], "g": d["g"], "r": d["r"]}
            self.add(85, "memorial", [mourner, None, None, dp], {"keep": d["keep"]}, opener=False)
            if self.rng.random() < 0.75:
                al["T"].append({"i": self._nid(), "k": "mem", "s": day, "d": day + self.rng.randint(5, 8), "a": [mourner["i"]], "x": {"dead": d["i"]}})
        # a recovery: the real state went from sick to well
        for p in st["people"]:
            rec = self.rec(p)
            if rec["ls"] == "s" and p["s"] != "s":
                tender = self.pick(1, role_w={"medic": 5.0}, exclude={p["i"]})
                if tender and p["i"] not in self.used and p["n"] not in self.recovered_named:
                    self.add(72, "recovered", [p, tender[0]], {"ill": p.get("il") or "fever"}, coda=False)
                    self.used.add(p["i"])
        # the sick tended
        sick = [p for p in st["people"] if p["s"] == "s" and day - self.rec(p)["vg"] >= 2 and p["i"] not in self.used]
        if sick and self.rng.random() < 0.7:
            p = self.rng.choice(sick)
            tender = self.pick(1, role_w={"medic": 6.0}, exclude={p["i"]})
            if tender:
                self.rec(p)["vg"] = day
                self.add(64, "vigil_spore" if p.get("il") == "spores" else "vigil", [p, tender[0]], {"ill": p.get("il") or "fever"}, coda=False)     # (the spore-sick: a vigil without hope talk, canon)
                self.used.add(p["i"])
        # rations
        a = self.pick(2)
        if len(a) == 2:
            sym = {"sup": self.sup, "need": self.need}
            if self.deficit and self.rng.random() < 0.72:
                pool = "rat_streak_bad" if st["ds"] >= 3 and self.rng.random() < 0.5 else "rat_deficit"
                if pool == "rat_deficit" and self.sup >= 0.85 * self.need:      # a small shortfall gets a small line (no famine talk at 23 of 24)
                    pool = "rat_mild"
                self.add(75, pool, a, sym if pool in ("rat_deficit", "rat_mild") else {})
            elif not self.deficit and self.need > 0 and self.rng.random() < 0.4:
                pool = "rat_streak_good" if st["ss"] >= 3 and self.rng.random() < 0.5 else "rat_surplus"
                self.add(50, pool, a, sym if pool == "rat_surplus" else {})

    def _nid(self):
        self.al["nid"] += 1
        return self.al["nid"]

    # --- the threads
    def advance(self):
        al, day, rng = self.al, self.day, self.rng
        for t in list(al["T"]):
            k = t["k"]
            if k == "exp":
                self._exp(t)
            elif k == "inj":
                self._inj(t)
            elif k == "proj":
                self._proj(t)
            elif k == "trade":
                self._trade(t)
            elif k == "thr":
                self._thr(t)
            elif k == "qrl":
                self._qrl(t)
            elif k == "men":
                self._men(t)
            elif k == "mem":
                if day >= t["d"]:
                    p = self.person(t["a"][0])
                    if p and (p["i"] in self.away() or p["i"] in self.used or p["s"] == "s") and t["x"].get("wait", 0) < 3:
                        t["x"]["wait"] = t["x"].get("wait", 0) + 1            # the mourner is away / busy / ill: tomorrow
                        t["d"] = day + 1
                        continue
                    al["T"].remove(t)
                    d = next((x for x in al["D"] if x["i"] == t["x"]["dead"]), None)
                    if p and d and p["i"] not in self.used and p["s"] != "s" and p["i"] not in self.away():
                        self.add(40, "memorial_late", [p, None, None, {"n": d["n"], "g": d["g"], "r": d["r"]}], {"keep": d["keep"]}, opener=False)
            elif k == "arr":
                if day >= t["d"]:
                    al["T"].remove(t)
                    p = self.person(t["a"][0])
                    h = self.pick(1, exclude={t["a"][0]})
                    if p and p["s"] == "h" and h and p["i"] not in self.used and p["i"] not in self.away():
                        self.add(42, "arrive_follow", [p, h[0]])

    def _exp(self, t):
        al, day, rng = self.al, self.day, self.rng
        party = [self.alive[i] for i in t["a"] if i in self.alive]
        lost = [x for x in al["D"] if x["i"] in t["x"].get("lost", [])]
        if day < t["d"]:
            if day > t["s"] and party and rng.random() < 0.55:
                camp = self.pick(1, fight=True)
                if camp:
                    self.add(34, "exp_wait", [camp[0], party[0]], {"dest": t["x"]["dest"], "nd": self.days_gone(t)}, coda=False)
            return
        al["T"].remove(t)
        if not party:
            return
        x = t["x"]
        sym = {"dest": x["dest"], "goal": x["goal"], "nd": max(1, day - t["s"])}
        for p in party:
            self.used.add(p["i"])
        if lost:
            d = lost[0]
            self.add(90, "exp_lost", [party[0], None, None, {"n": d["n"], "g": d["g"], "r": d["r"]}], sym)
            return
        if x.get("recall"):
            sick = self.alive.get(x["recall"])
            if sick and len(party) >= 2:
                lead = next((p for p in party if p["i"] != sick["i"]), party[0])
                self.add(66, "exp_recall", [lead, sick], sym, mood="worried")
                return
        A, B = party[0], (party[1] if len(party) > 1 else party[0])
        if len(party) < 2:
            return
        roll = rng.random()
        morale = self.st["morale"]
        p_good = 0.5 + 0.2 * (1 if morale >= 55 else -1 if morale < 35 else 0) + 0.05 * min(3, self.st["ss"])
        ppl = [A, B] + ([party[2]] if len(party) > 2 else [])
        if roll < 0.12:
            hurt = rng.choice(party)
            others = [p for p in party if p["i"] != hurt["i"]]
            inj = rng.choice(sorted(X.INJURIES))
            self.add(60, "exp_ret_hurt", [hurt, others[0]], dict(sym, inj=inj))
            al["T"].append({"i": self._nid(), "k": "inj", "s": day, "d": day + rng.randint(2, 4), "a": [hurt["i"]], "x": {"inj": inj}})
        elif roll < 0.22:
            self.add(62, "exp_ret_contact", ppl, sym)
        elif roll < 0.30:
            self.add(58, "exp_ret_inf", ppl, dict(sym, inf=rng.choice(D.INFECTED)))
        elif roll < 0.30 + p_good * 0.7:
            self.add(70, "exp_ret_good", ppl, sym)
        else:
            self.add(52, "exp_ret_empty", ppl, sym)

    def _inj(self, t):
        day, rng = self.day, self.rng
        p = self.person(t["a"][0])
        if p is None or p["s"] != "h":
            self.al["T"].remove(t)
            return
        if day >= t["d"]:
            self.al["T"].remove(t)
            b = self.pick(1, exclude={p["i"]}, fight=True)
            if p["i"] not in self.used:
                self.add(45, "inj_heal", [p] + b, {"inj": t["x"]["inj"]})
        elif day > t["s"] and rng.random() < 0.4 and p["i"] not in self.used:
            b = self.pick(1, exclude={p["i"]}, fight=True)
            self.add(30, "inj_mid", [p] + b, {"inj": t["x"]["inj"]})

    def _proj(self, t):
        al, day, rng = self.al, self.day, self.rng
        x = t["x"]
        workers = [self.alive[i] for i in t["a"] if i in self.alive]
        ok = [p for p in workers if p["s"] == "h" and p["i"] not in self.away() and p["i"] not in self.hurt() and p["i"] not in self.used]
        if day == t["s"]:
            return
        if self.deficit or len(ok) < 2:
            if len(ok) >= 2 and rng.random() < 0.6:
                self.add(35, "proj_stall", ok[:2], {"proj": x["proj"]})
            elif len(ok) < 2:
                extra = self.pick(2 - len(ok), exclude={p["i"] for p in ok}, states=("h",), fight=True)
                t["a"] = [p["i"] for p in ok + extra] or t["a"]
            return
        x["p"] += 1
        if x["p"] >= x["n"]:
            al["T"].remove(t)
            al["done"].append(x["proj"])
            del al["done"][:-8]
            self.add(60, "proj_done", ok[:2], {"proj": x["proj"]})
            return
        prog = min(3, int(4 * x["p"] / x["n"]))
        if prog != x.get("last") and rng.random() < 0.85:
            x["last"] = prog
            self.add(40, "proj_prog", ok[:2], {"proj": x["proj"], "prog": prog})

    def _trade(self, t):
        al, day, rng = self.al, self.day, self.rng
        x = t["x"]
        if day < t["d"]:
            return
        al["T"].remove(t)
        a = self.pick(2, fight=True)
        if len(a) < 2:
            return
        sym = {"grp": x["grp"], "dest": x["dest"], "goal": x["goal"], "due": t["d"]}
        self.add(50, "tr_meet", a, sym)
        good = rng.random() < (0.35 + (0.25 if self.st["morale"] >= 55 else 0))
        al["T"].append({"i": self._nid(), "k": "tradeend", "s": day, "d": day + 1, "a": [a[0]["i"]], "x": dict(x, good=good)})

    def _thr(self, t):
        al, day, rng = self.al, self.day, self.rng
        x = t["x"]
        if day == t["s"]:
            return
        stage = x.get("st", 0)
        a = self.pick(2, fight=True)
        if day >= t["d"]:
            al["T"].remove(t)
            if len(a) >= 2:
                self.add(46, "thr_down", a, {"dest": x["dest"]})
            return
        if stage == 0 and len(a) >= 2 and rng.random() < 0.55:
            x["st"] = 1
            self.add(58, "thr_up", a, {"dest": x["dest"]})

    def _qrl(self, t):
        al, day = self.al, self.day
        if day >= t["d"]:
            if {t["a"][0], t["a"][1]} & self.away():          # one of them is out on an expedition: the making-up waits for the return
                t["d"] = day + 1
                return
            al["T"].remove(t)
            a, b = self.person(t["a"][0]), self.person(t["a"][1])
            if a and b and a["i"] not in self.used and b["i"] not in self.used and a["s"] != "s" and b["s"] != "s":
                self.add(44, "reconcile", [a, b])
                self.rec(a)["rv"] = 0
                self.rec(b)["rv"] = 0

    def _men(self, t):
        al, day = self.al, self.day
        a, b = self.person(t["a"][0]), self.person(t["a"][1])
        if day >= t["d"]:
            al["T"].remove(t)
            if b:
                self.rec(b)["sk"] += 1
            if a and b and a["i"] not in self.used and b["i"] not in self.used and a["s"] == "h" and b["s"] == "h" and not ({a["i"], b["i"]} & self.away()):
                self.add(38, "mentor", [a, b], {"skill": t["x"]["skill"]})

    # --- new threads and ambient scenes
    def spawn(self):
        al, day, rng, st = self.al, self.day, self.rng, self.st
        morale, size = st["morale"], len(st["people"])
        cool = al["cool"]

        def ready(k, n):
            return day >= cool.get(k, -99) + n
        sick_n = sum(1 for p in st["people"] if p["s"] == "s")
        hungry_n = sum(1 for p in st["people"] if p["s"] == "u")
        # an expedition
        n_exp = len(self.threads("exp"))
        if day >= 1 and n_exp < 1 + size // 16 and ready("exp", 2) and rng.random() < (0.2 if morale <= 25 else 0.55):
            eligible = self.free(states=("h",))
            eligible = [p for p in eligible if p["r"] not in ("kid", "elder")]
            if len(eligible) >= 2 and len(self.free()) >= 3:
                rw = {"scout": 3.0, "scavenger": 3.0, "guard": 2.0, "mechanic": 1.0, "medic": 0.6, "cook": 0.4, "gardener": 0.4, "radio": 0.3}
                k = 3 if (size >= 10 and len(eligible) >= 4 and rng.random() < 0.4) else 2
                party = []
                pool = list(eligible)
                while pool and len(party) < k:
                    w = [(1 + min(14, day - self.rec(p)["lm"])) * rw.get(p["r"], 1.0) for p in pool]
                    q = rng.choices(pool, weights=w)[0]
                    pool.remove(q)
                    party.append(q)
                dests = [d for d in X.PLACES[self.fk] if d not in al["lastdest"][-3:]]
                dest = rng.choice(dests or list(X.PLACES[self.fk]))
                al["lastdest"] = (al["lastdest"] + [dest])[-6:]
                goals = X.pool_keys(X.GOODS, self.fk)
                pref = ["antibiotics", "bandages"] if sick_n else ["cans", "salt"] if hungry_n else []
                goal = rng.choice([g for g in pref if g in goals] if pref and rng.random() < 0.6 else goals)
                nd = rng.choices([1, 2, 3], weights=[45, 40, 15])[0]
                cool["exp"] = day
                al["T"].append({"i": self._nid(), "k": "exp", "s": day, "d": day + nd, "a": [p["i"] for p in party], "x": {"dest": dest, "goal": goal}})
                self.add(55, "exp_leave", party, {"dest": dest, "goal": goal, "nd": nd}, opener=True)
        # a project
        if len(self.threads("proj")) < 1 + size // 20 and ready("proj", 4) and morale >= 30 and rng.random() < 0.35:
            keys = [k for k in X.pool_keys(X.PROJECTS, self.fk) if k not in al["done"] and k not in [t["x"]["proj"] for t in self.threads("proj")]]
            w = self.pick(2, states=("h",), fight=True)            # the building crew works on the walls and towers: grown people
            if keys and len(w) == 2:
                proj = rng.choice(keys)
                cool["proj"] = day
                al["T"].append({"i": self._nid(), "k": "proj", "s": day, "d": day + 30, "a": [p["i"] for p in w], "x": {"proj": proj, "p": 0, "n": rng.randint(4, 6)}})
                self.add(54, "proj_start", w, {"proj": proj})
        # a trade
        if not self.threads("trade") and not self.threads("tradeend") and day >= 3 and ready("trade", 8) and rng.random() < 0.16:
            a = self.pick(1, states=("h",), fight=True)           # the trade meeting is outside the wall
            if a:
                grp = rng.choice(X.pool_keys(X.GROUPS, self.fk))
                dest = rng.choice(list(X.PLACES[self.fk]))
                goals = X.pool_keys(X.GOODS, self.fk)
                due = day + rng.randint(2, 4)
                cool["trade"] = day
                al["T"].append({"i": self._nid(), "k": "trade", "s": day, "d": due, "a": [a[0]["i"]], "x": {"grp": grp, "dest": dest, "goal": rng.choice(goals)}})
                self.add(36, "tr_rumor", a, {"grp": grp, "dest": dest, "due": due})
        for t in self.threads("tradeend"):                      # the day after a meeting: how it went
            al["T"].remove(t)
            a = self.person(t["a"][0])
            b = self.pick(1, exclude={t["a"][0]}, fight=True)
            if a and a["s"] != "s" and a["i"] not in self.used:
                x = t["x"]
                pool = "tr_good" if x["good"] else "tr_bad"
                self.add(40, pool, [a] + b, {"grp": x["grp"], "dest": x["dest"], "goal": x["goal"]})
        # a threat
        if not self.threads("thr") and ready("thr", 4) and rng.random() < 0.22:
            a = self.pick(2, states=("h",), fight=True)
            if len(a) == 2:
                sub = rng.choices(["thr_enemy", "thr_inf", "thr_smoke"], weights=[4, 3, 1])[0]
                dest = rng.choice(list(X.PLACES[self.fk]))
                cool["thr"] = day
                al["T"].append({"i": self._nid(), "k": "thr", "s": day, "d": day + rng.randint(2, 3), "a": [p["i"] for p in a], "x": {"dest": dest, "sub": sub}})
                self.add(56, sub, a, {"dest": dest, "inf": rng.choice(D.INFECTED)})
        # relationships
        if rng.random() < 0.34:
            self._social()
        # a rumour
        if rng.random() < 0.18:
            a = self.pick(2)
            if len(a) == 2:
                self.add(28, "rumor", a)
        # a small camp incident (re/clan-events-1117.md, tools/clan_alife_text_g.py): damp in the stores, strangers at the wall, a horde passing in the
        # night, a night in the sick tent (only when someone really is sick). Text only: nothing is lost, nobody is hurt, no number moves. Drawn last, so
        # the day's other threads take their people first.
        # It has its own random stream (seed, run, day): the day's other draws stay exactly what they were before these incidents existed.
        irng = random.Random("%s:%s:inc:%d" % (al["seed"], al["run"], day))
        if INCIDENTS and ready("inc", 6) and irng.random() < 0.2:
            kinds = ["inc_spoil", "inc_tres", "inc_horde"] + (["inc_sick"] if sick_n else [])
            self.rng = irng
            try:
                a = self.pick(2, states=("h",), fight=True)
                if len(a) == 2:
                    cool["inc"] = day
                    self.add(34, irng.choice(kinds), a)
            finally:
                self.rng = rng

    def _social(self):
        """One relationship beat. Bonds are persistent: a friendship can sour into a quarrel (and end in a reconciliation days later), grow into a romance,
        and a mentor teaches an apprentice a skill over a few days."""
        al, day, rng = self.al, self.day, self.rng
        free = self.free()
        if len(free) < 2:
            return
        ids = {p["i"]: p for p in free}
        bonded = []                                             # free friends (A's friend is B, both free)
        for p in free:
            q = ids.get(self.rec(p)["f"])
            if q and p["i"] < q["i"]:
                bonded.append((p, q))
        opts = [("friend", 3), ("mentor", 2)]
        if bonded:
            opts += [("quarrel", 3)]
            if day - al["cool"].get("rom", -99) >= 6:
                opts += [("romance", 1)]
        kind = rng.choices([k for k, _w in opts], weights=[w for _k, w in opts])[0]
        if kind in ("quarrel", "romance"):
            cand = [b for b in bonded if kind == "quarrel" or (not self.rec(b[0])["pa"] and not self.rec(b[1])["pa"])]
            if not cand:
                kind = "friend"
            else:
                A, B = rng.choice(cand)
                ra, rb = self.rec(A), self.rec(B)
                if kind == "quarrel":
                    ra["rv"], rb["rv"] = B["i"], A["i"]
                    al["T"].append({"i": self._nid(), "k": "qrl", "s": day, "d": day + rng.randint(2, 4), "a": [A["i"], B["i"]], "x": {}})
                    self.add(42, "quarrel", [A, B])
                else:
                    ra["pa"], rb["pa"] = B["i"], A["i"]
                    al["cool"]["rom"] = day
                    self.add(38, "romance", [A, B])
                return
        a = self.pick(2)
        if len(a) < 2:
            return
        A, B = a
        ra, rb = self.rec(A), self.rec(B)
        if kind == "friend" and not ra["f"] and not rb["f"]:
            ra["f"], rb["f"] = B["i"], A["i"]
            self.add(40, "friend", [A, B])
            return
        busy = {t["a"][1] for t in self.threads("men")} | {t["a"][0] for t in self.threads("men")}
        if A["i"] in busy or B["i"] in busy:
            return
        mentor, app = (A, B) if (A["r"] == "elder" or B["r"] == "kid" or ra["sk"] >= rb["sk"]) else (B, A)
        skills = X.pool_keys(X.SKILLS, self.fk)
        if KD.is_kid(A) or KD.is_kid(B):                         # a kid learns a trade, never a weapon: no rifle, no bow, no clicker lore
            skills = [k for k in skills if not (KD.combat_text(X.SKILLS[k][1], "en") or KD.combat_text(X.SKILLS[k][2], "pl"))] or ["knot"]
        skill = rng.choice(skills)
        al["T"].append({"i": self._nid(), "k": "men", "s": day, "d": day + 3, "a": [mentor["i"], app["i"]], "x": {"skill": skill}})
        self.add(38, "mentor", [mentor, app], {"skill": skill})

    def ambient(self):
        """Fill the day: a camp scene by role or a general one."""
        rng = self.rng
        a = self.pick(3)
        if not a:
            return
        role_pool = "amb_" + a[0]["r"]
        if role_pool in POOLS and rng.random() < 0.55:
            others = a[1:2]
            self.add(20, role_pool, [a[0]] + others)
        else:
            self.add(20, "amb_any", a)

    # --- the whole day
    def run(self, newcomers):
        self.arrivals_ok = bool(newcomers)
        self.new_ids = newcomers
        self.sync()
        self.real_day()
        self.advance()
        self.spawn()
        want = DAY_MIN_ROWS + (1 if self.rng.random() < 0.4 else 0)
        guard = 0
        while len(self.events) < want and guard < 4:
            self.ambient()
            guard += 1
        self.events.sort(key=lambda e: -e[0])
        out, pools = [], set()
        for _d, ev in self.events:
            if len(out) >= want:
                break
            if ev["pool"] in pools:
                continue
            msg = _compose(self.al, self.st, ev, self.rng, self.day, self.wx)
            if msg:
                out.append(msg)
                pools.add(ev["pool"])
        for p in self.st["people"]:                      # the real states, for tomorrow's transitions (a recovery)
            self.rec(p)["ls"] = p["s"]
        return out


def on_day(c, tid, st, newc, r, story_msgs=()):
    """Called by clan_story.on_day AFTER the roster was advanced to the clan state `newc` for the day result `r`. Returns the A-Life feed rows of the day
    (dicts like clan_story's: kind "alife", mood, text, names, lid, params); they are stored by clan_story._store. [] when switched off / clan too small."""
    if not enabled() or not st or not r:
        return []
    ensure(c)
    al = load(c, tid)
    new = False
    if al is None or al["run"] != st["run"] or al["fac"] != st["fac"] or st["day"] < al["day"]:
        al, new = _new(tid, st), True
    if al["day"] == st["day"]:
        return []
    fk = _fk(st)
    for p in st["people"]:
        _rec(al, p, fk)
    rng = random.Random("%s:%s:%d:day" % (tid, st["run"], st["day"]))
    out = []
    if len(st["people"]) >= MIN_CLAN:
        # the newcomers of today: unseen before, joined today (never on the very first sight of a clan: those are its founders)
        newcomers = [] if new else [p for p in st["people"] if not al["P"][str(p["i"])].get("seen") and p["jd"] == st["day"]]
        out = Day(al, st, newc, r, rng, story_msgs).run(newcomers)
    for p in st["people"]:
        al["P"][str(p["i"])]["seen"] = 1
    al["day"] = st["day"]
    al["stat"]["days"] += 1
    save(c, tid, al)
    return out


# ------------------------------------------------------------------ the menu ticker: facts of the simulated life, one sentence each
FACT_W = {"f_exp": 3, "f_inj": 2, "f_proj": 2, "f_trade": 2, "f_friend": 2, "f_rival": 2, "f_romance": 2, "f_mentor": 2, "f_trait": 3, "f_job": 2, "f_origin": 1,
          "f_memorial": 2, "f_vigil": 2, "wx": 2, "f_season": 1, "f_rat_good": 1, "f_rat_bad": 1, "f_count": 1, "f_role": 1}


def _byid(st, i):
    for p in st["people"]:
        if p["i"] == i:
            return p
    return None


def facts(al, st):
    """The current facts of the clan's simulated life that may be told: [(class, key, pool, people, sym)], validated against the live roster (alive, right state)."""
    fk = _fk(st)
    out = []
    day = st["day"]
    base = _base_sym(al, st, day)
    away = set()
    for t in al["T"]:
        if t["k"] == "exp":
            away |= set(t["a"])
    for t in al["T"]:
        ps = [_byid(st, i) for i in t["a"]]
        if any(p is None for p in ps) or not ps:
            continue
        k, x = t["k"], t["x"]
        if k == "exp" and t["d"] > day and all(p["s"] == "h" for p in ps):
            out.append(("f_exp", "exp%d" % t["i"], "f_exp", {"A": _pp(ps[0]), "B": _pp(ps[-1])}, {"dest": x["dest"], "goal": x["goal"], "nd": max(1, t["d"] - day)}))
        elif k == "inj" and ps[0]["s"] == "h":
            out.append(("f_inj", "inj%d" % t["i"], "f_inj", {"A": _pp(ps[0])}, {"inj": x["inj"]}))
        elif k == "proj" and len(ps) >= 2:
            prog = min(3, int(4 * x["p"] / x["n"]))
            out.append(("f_proj", "proj%d" % t["i"], "f_proj", {"A": _pp(ps[0]), "B": _pp(ps[1])}, {"proj": x["proj"], "prog": prog}))
        elif k == "trade" and t["d"] >= day:
            out.append(("f_trade", "trade%d" % t["i"], "f_trade", {"A": _pp(ps[0])}, {"grp": x["grp"], "dest": x["dest"], "due": t["d"]}))
        elif k == "qrl" and len(ps) >= 2:
            out.append(("f_rival", "qrl%d" % t["i"], "f_rival", {"A": _pp(ps[0]), "B": _pp(ps[1])}, {}))
        elif k == "men" and len(ps) >= 2 and all(p["s"] == "h" for p in ps) and not (any(KD.is_kid(p) for p in ps) and KD.combat_text(X.SKILLS[x["skill"]][1], "en")):
            out.append(("f_mentor", "men%d" % t["i"], "f_mentor", {"A": _pp(ps[0]), "B": _pp(ps[1])}, {"skill": x["skill"]}))
    seen_pairs = set()
    for p in st["people"]:
        r = al["P"].get(str(p["i"]))
        if not r:
            continue
        if p["i"] in away:
            continue
        pe = {"A": _pp(p)}
        if p["s"] in ("h", "u"):
            for n in (0, 1):
                out.append(("f_trait", "tr%d_%d" % (p["i"], n), "f_trait:" + _trait(r, n), pe, {}))
            out.append(("f_job", "job%d" % p["i"], "f_job", pe, {"job": r["job"]}))
            rpool = "f_role:" + p["r"]
            out.append(("f_role", "role%d" % p["i"], rpool if rpool in BY_POOL else "f_role", pe, {}))
            if p["jd"] > 0 and p["jd"] >= st["day"] - 20:
                out.append(("f_origin", "orig%d" % p["i"], "f_origin", pe, {"orig": r["orig"], "jd": p["jd"]}))
            for key, pool in (("f", "f_friend"), ("pa", "f_romance")):
                q = _byid(st, r.get(key, 0)) if r.get(key) else None
                pair = tuple(sorted((p["i"], q["i"]))) if q else None
                if q and q["s"] in ("h", "u") and (pool, pair) not in seen_pairs and (pool != "f_friend" or not r.get("pa")):
                    seen_pairs.add((pool, pair))
                    out.append((pool, "%s%d_%d" % (pool, pair[0], pair[1]), pool, {"A": _pp(p), "B": _pp(q)}, {}))
        elif p["s"] == "s":
            tend = [q for q in st["people"] if q["s"] == "h" and q["i"] != p["i"] and q["i"] not in away]
            if tend:
                tend.sort(key=lambda q: (q["r"] != "medic", q["i"]))
                out.append(("f_vigil", "vig%d" % p["i"], "f_vigil", {"A": _pp(p), "B": _pp(tend[0])}, {"ill": p.get("il") or "fever"}))
    for d in al["D"]:
        if day - d["d"] <= 20 and d["c"] in MEM_CAUSES:
            k = _byid(st, d.get("k")) if d.get("k") else None
            if k and k["s"] == "h" and k["i"] not in away:
                out.append(("f_memorial", "mem%d" % d["i"], "f_memorial", {"A": _pp(k), "D": {"n": d["n"], "g": d["g"], "r": d["r"]}}, {"keep": d["keep"]}))
    wx = _weather(al, st, day)
    out.append(("wx", "wx%d" % day, "wx_" + wx, {}, {}))
    out.append(("f_season", "season", "f_season", {}, {}))
    out.append(("f_count", "count", "f_count", {}, {}))
    if st["ss"] >= 2:
        out.append(("f_rat_good", "ratg", "f_rat_good", {}, {}))
    if st["ds"] >= 2:
        out.append(("f_rat_bad", "ratb", "f_rat_bad", {}, {}))
    return [dict(cls=c_, key=k_, pool=p_, people=pe_, sym=dict(base, **sy_)) for c_, k_, p_, pe_, sy_ in out]


TAIL_OK = ("f_trait", "f_job", "f_role", "f_origin", "f_friend", "f_season", "f_count", "wx", "f_proj", "f_trade", "f_mentor", "f_exp")   # facts a light aside may follow
PERSISTENT = ("f_trait", "f_job", "f_role", "f_origin", "f_friend", "f_romance")      # facts that are true every day: a rotating share of them is told each day
DAILY_FACTS = 30


def daily_facts(al, st, tid):
    """The facts of today's ticker: everything that is happening (expeditions, injuries, projects, trade, the sick, the dead remembered, weather ...) plus a
    day-specific sample of the lasting ones (traits, pasts, bonds, roles), so the same person is not described the same way day after day."""
    fs = facts(al, st)
    dyn = [f for f in fs if f["cls"] not in PERSISTENT]
    per = sorted((f for f in fs if f["cls"] in PERSISTENT), key=lambda f: f["key"])
    k = max(0, min(len(per), DAILY_FACTS - len(dyn)))
    pick = random.Random("sub:%s:%s:%d" % (tid, st["run"], st["day"])).sample(per, k) if per else []
    return dyn + pick


def _rows(pool, fk, morale, letters, av_en, av_pl, people=None):
    out = []
    for tid in BY_POOL.get(pool, ()):
        _p, sc, tone, _en, _pl, lt, ve, vp = REG[tid]
        if sc in ("*", fk) and _tone_ok(tone, morale) and lt <= letters and ve <= av_en and vp <= av_pl and (not people or KD.kid_safe(_en, people, _pl)):
            out.append(tid)
    return out


def _deck(fs, seed, epoch):
    """The shuffled deck of one epoch: every fact w times (its class weight), no two of one class in a row where avoidable."""
    items = []
    for f in sorted(fs, key=lambda f: f["key"]):
        items += [(f, m) for m in range(FACT_W.get(f["cls"], 1))]
    random.Random("%s:%d" % (seed, epoch)).shuffle(items)
    for j in range(1, len(items)):
        prev = items[j - 1][0]["cls"]
        if items[j][0]["cls"] == prev:
            nxt = items[j + 1][0]["cls"] if j + 1 < len(items) else None
            for q in range(j + 1, len(items)):
                if items[q][0]["cls"] not in (prev, nxt):
                    items[j], items[q] = items[q], items[j]
                    break
    return items


def _variant(rows, key, n):
    """The n-th phrasing of a fact: a seeded permutation of its rows, so the same fact is told in all its phrasings before any repeats."""
    perm = list(rows)
    random.Random("v:" + key).shuffle(perm)
    return perm[n % len(perm)]


def state_for_read(c, tid, st, persist=False):
    """The A-Life state of a clan for the ticker / views: the stored one, else a deterministic fresh one from the live roster (in memory, or stored when
    persist). None when switched off."""
    if not enabled():
        return None
    fk = _fk(st)
    al = load(c, tid)
    if al is None or al["run"] != st["run"] or al["fac"] != st["fac"]:
        al = _new(tid, st)
        al["day"] = st["day"]
        for p in st["people"]:
            _rec(al, p, fk)["seen"] = 1
        if persist:
            try:
                ensure(c)
                save(c, tid, al)
            except Exception:                                              # noqa: BLE001 - the in-memory state is the same
                pass
    else:
        for p in st["people"]:                     # members who joined while the switch was off
            if str(p["i"]) not in al["P"]:
                _rec(al, p, fk)["seen"] = 1
    return al


def ticker_lines(c, tid, st, slot, n, lang="en", now=None, save=False):
    """n ticker lines [(id, text)] of the simulated life for a time slot: a pure function of (clan, state, slot, language). [] when switched off / too small.
    (save = also create the stored state when it is missing; a read-only caller passes False and gets the same lines.)"""
    if n <= 0 or not st or len(st["people"]) < MIN_CLAN:
        return []
    al = state_for_read(c, tid, st, save)
    if al is None:
        return []
    fk = _fk(st)
    fs = daily_facts(al, st, tid)
    if not fs:
        return []
    seed = "%s:%s:%d" % (tid, st["run"], st["day"])
    morale = st["morale"]
    L = len(_deck(fs, seed, 0))
    decks = {}
    pl = CS.PLN.norm_lang(lang) == "pl"
    out = []
    for i in range(n):
        k = slot * TICKER_SHARE + i
        for attempt in range(8):                           # a fact with no phrasing for the mood is skipped (rare)
            e, j = divmod(k + attempt, L)
            deck = decks.get(e) or decks.setdefault(e, _deck(fs, seed, e))
            f, m = deck[j]
            av_en, av_pl = _avail(f["sym"])
            rows = _rows(f["pool"], fk, morale, set(f["people"]), av_en, av_pl, f["people"]) or _rows(f["pool"], fk, 50, set(f["people"]), av_en, av_pl, f["people"])
            if rows:
                break
        else:
            continue
        tid_ = _variant(rows, "%s:%s" % (tid, f["key"]), st["day"] + e * FACT_W.get(f["cls"], 1) + m)
        ids = [tid_]
        trng = random.Random("tail:%s:%d:%d:%d" % (tid, st["day"], slot, i))
        if f["cls"] in TAIL_OK and trng.random() < 0.5:
            wx = _weather(al, st, st["day"])
            tpool = "f_tail_" + wx if trng.random() < 0.3 else "f_tail"
            tails = _rows(tpool, fk, morale, set(), set(), set())
            if tails:
                tl = trng.choice(tails)
                head = _render_ids([tid_], f["people"], f["sym"], "pl" if pl else "en", fk)
                if len(head) + 1 + len(_render_ids([tl], {}, f["sym"], "pl" if pl else "en", fk)) <= CS.WIDGET_MAX:
                    ids.append(tl)
        text = _render_ids(ids, f["people"], f["sym"], "pl" if pl else "en", fk)
        if KD.any_kid(f["people"]) and not KD.kid_text_ok(text, f["people"], "pl" if pl else "en"):
            continue                                                 # (a kid's fact that came out as combat is not told)
        out.append(("a%d%02d" % (slot % 100000, i), CS.widget_text(text)))
    return out


# ------------------------------------------------------------------ read-only views (admin site, update server)
def read_state(c, tid, lang="en"):
    """A JSON-able view of the clan's simulation for the admin site and the launcher: people with their extras, the running threads, today's weather, the
    variety statistics. {} without a state."""
    st = CS._load(c, tid)
    al = load(c, tid)
    if not st or not al or al["run"] != st["run"]:
        return {}
    pl = CS.PLN.norm_lang(lang) == "pl"
    fk = _fk(st)
    people = []
    away = set()
    for t in al["T"]:
        if t["k"] == "exp":
            away |= set(t["a"])
    for p in st["people"]:
        r = al["P"].get(str(p["i"]), {})
        tr = [TRAIT_LABEL[_trait(r, n)][1 if pl else 0] for n in (0, 1)] if r else []
        def nm(i):
            q = _byid(st, i) if i else None
            return q["n"] if q else ""
        job = X.JOBS.get(r.get("job"))
        orig = X.ORIGINS.get(r.get("orig"))
        people.append({"name": p["n"], "role": D.ROLES[p["r"]][0 if fk == "W" else 1], "state": {"h": "healthy", "u": "hungry", "s": "sick"}[p["s"]],
                       "traits": tr, "friend": nm(r.get("f")), "rival": nm(r.get("rv")), "partner": nm(r.get("pa")), "skill": r.get("sk", 0),
                       "away": p["i"] in away, "past": job[1] if job else "", "origin": orig[1] if orig else "", "since": p["jd"]})
    threads = []
    for f in facts(al, st):
        if f["cls"] in ("f_exp", "f_inj", "f_proj", "f_trade", "f_rival", "f_mentor"):
            rows = _rows(f["pool"], fk, 50, set(f["people"]), *_avail(f["sym"]))
            if rows:                                                    # one phrasing per thread and day (not always the pool's first line)
                pick = rows[zlib.crc32(("%s:%s:%d" % (al["seed"], f["key"], st["day"])).encode("utf-8")) % len(rows)]
                text = _render_ids([pick], f["people"], f["sym"], "pl" if pl else "en", fk)
                threads.append({"kind": f["cls"][2:], "text": text})
    mem = al["mem"]
    cores = sum(1 for t in mem if not t.startswith("wx_"))
    return {"enabled": enabled(), "day": al["day"], "weather": _weather(al, st, st["day"]), "season": X.SEASONS[X.season_of(clan.week_day(st["day"])[0])][1 if pl else 0],
            "people": people, "threads": threads, "memorial": [{"name": d["n"], "day": d["d"], "cause": d["c"]} for d in al["D"]],
            "stats": {"rows": al["stat"]["lines"], "days": al["stat"]["days"], "windowRepeats": al["stat"]["rep"], "templatesUsed": len(mem), "coreTemplatesUsed": cores,
                      "templatesTotal": len(REG)},
            "ticker": [t for _i, t in ticker_lines(c, tid, st, CS.slot_of(), TICKER_SHARE, lang, None, False)]}


def summary(c, tid):
    """One line about a clan's simulation for lists (admin site): {} without a state."""
    al = load(c, tid)
    if not al:
        return {}
    return {"day": al["day"], "threads": len(al["T"]), "people": len(al["P"]), "rows": al["stat"]["lines"], "templatesUsed": len(al["mem"])}


def public(c, tid, lang="en"):
    """What the launcher shows next to the journal (update server /clanfeed.json "alife"): {} unless the switch is on and a simulation exists.
    {"day", "weather", "season", "ongoing": [<= 4 one-line texts of what is happening now: expeditions, injuries, building, trade, quarrels, lessons]}."""
    if not enabled():
        return {}
    try:
        rs = read_state(c, tid, lang)
    except Exception:                                                   # noqa: BLE001
        return {}
    if not rs:
        return {}
    return {"day": rs["day"], "weather": rs["weather"], "season": rs["season"], "ongoing": [t["text"] for t in rs["threads"]][:4]}


def view(c, tid):
    """Everything the admin site shows about one clan's A-Life, in both languages, read-only: the switch, the simulation state (read_state), and the lines the
    player's menu shows right now. {"enabled", "exists", "state" (EN), "pl": {"threads", "season", "traits": {name: [...]}}, "menu": {"en": [...], "pl": [...]}}."""
    out = {"enabled": enabled(), "exists": False}
    try:
        en = read_state(c, tid, "en")
    except Exception:                                                   # noqa: BLE001 - a view never breaks the page
        en = {}
    if not en:
        return out
    pl = read_state(c, tid, "pl")
    out.update(exists=True, state=en, pl={"threads": [t["text"] for t in pl.get("threads", [])], "season": pl.get("season"),
                                          "traits": {p["name"]: p["traits"] for p in pl.get("people", [])}})
    try:
        out["menu"] = {lang: [t for _i, t in CS.menu_lines(c, tid, 6, lang, None, save=False)] for lang in ("en", "pl")}
    except Exception:                                                   # noqa: BLE001
        out["menu"] = {"en": [], "pl": []}
    return out
