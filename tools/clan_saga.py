"""Clan saga: the long, match-tied entries of the clan chronicle (EN + PL), with a persistent memory per member.  Called by clan_chronicle.day_rows; it NEVER changes a
clan number or a person's state (hunger / sickness / death stay clan.py's and clan_story's), it only writes text and keeps its own memory in st["ch"].

What an entry is made of (see re/clan-chronicle-sample-w.md):
  * the player's real match (r["match"], filled by daemon.clan_finalize): map and its places (clan_saga_data.MAPS), kills, executions, revives, headshots, times downed,
    deaths, win / loss, weapon, kill streak - every field that is absent is simply not mentioned (a template needing it is skipped);
  * the loot of the match with the PLACE it was found in, remembered (st["ch"]["sg_stock"] / ["sg_keep"]) and called back on later days;
  * the memory of every member (st["ch"]["mem"][id]): injury (site, cloth, day, healing day -> scar), grief, possession, fear, relationship levels (rival / sweet / mentor /
    kin, progressed one stage per scene), last day in the spotlight; and of the player (st["ch"]["you"]): the stitched wound, the results of the last days;
  * the previous days: loss streaks, the same map again, the stitched wound, a keepsake that turns up again, the ones still out in a story arc.
Variety guard: a template sentence is not used again within WINDOW (14) days while another one fits (st["ch"]["sg_used"]).
Row: kind "chron", lid "sg/<scene>", params {"p": people, "s": {f, day, map}, "t": the finished text, "a": thread id}, text "DAY n: TITLE. body".  Dead people never
act again: they appear only in the death and grief scenes, as the one who is gone (letter D).
"""
import os
import re
import sys
import zlib

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import clan_story as CS                                      # noqa: E402
import clan_kids as KD                                       # noqa: E402  (kids are never fighters)
import clan_story_data as D                                  # noqa: E402
import clan_saga_data as SD                                  # noqa: E402
import clan_saga_text as ST                                  # noqa: E402
import clan_saga_text2 as ST2                                # noqa: E402
import clan_saga_text3 as ST3                                # noqa: E402
import clan_saga_text4 as ST4                                # noqa: E402
import clan_saga_text_sup as STS                             # noqa: E402
import clan_chronicle_maps as MAPN                           # noqa: E402
try:                                                         # the Polish templates and word forms (tools/clan_saga_pl.py); a broken Polish table never takes the English saga down
    import clan_saga_pl as PLS                               # noqa: E402
except Exception as _ex:                                     # noqa: BLE001
    if os.environ.get("T2R_SAGA_STRICT"):
        raise
    sys.stderr.write("clan_saga_pl unavailable: %r" % (_ex,) + chr(10))
    PLS = None

WINDOW = 14
NW = ["no", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten"]
ORD = {2: "second", 3: "third", 4: "fourth", 5: "fifth", 6: "sixth", 7: "seventh"}
KEY_RE = CS.KEY_RE
PERSON_RE = CS.PERSON_RE
CAMPS = {"W": ["the east barracks", "the FOB mess", "the old gym", "the pharmacy block", "the stadium tunnel"],
         "S": ["the long house", "the kitchen house", "the weaving house", "the shore camp", "the harbor hut"]}
MOODS = {"loss": "worried", "down": "worried", "win": "cheerful", "exec": "worried", "rev": "hopeful", "quiet": "calm", "haul": "cheerful", "keepcb": "cheerful", "keepfind": "cheerful", "dep": "grieving",
         "use": "calm", "inj": "worried", "grief": "grieving", "death": "grieving", "prep": "afraid", "lack": "worried", "rel": "hopeful", "prof": "calm"}


def _h(*parts):
    return zlib.crc32("|".join(str(x) for x in parts).encode("utf-8")) & 0xFFFFFFFF


def pools():
    """{pool name: [(scope, text, person letters, variable keys)]} parsed from clan_saga_text.TEXT."""
    out, cur = {}, None
    for line in (ST.TEXT + ST2.TEXT + ST3.TEXT + ST4.TEXT + STS.TEXT).splitlines():
        line = line.strip()
        if not line:
            continue
        if line.startswith("== "):
            cur = out.setdefault(line[3:].strip(), [])
            continue
        scope = "*"
        if line[:2] in ("W:", "S:"):
            scope, line = line[0], line[2:].strip()
        pk, vk = set(), set()
        for k in KEY_RE.findall(line):
            m = PERSON_RE.match(k)
            if m:
                pk.add(m.group(1))
            else:
                vk.add(k)
        cur.append((scope, line, frozenset(pk), frozenset(vk)))
    return out


POOLS = pools()


def _nw(n):
    return NW[n] if 0 <= n <= 10 else str(n)


def times_p(n):
    return "once" if n == 1 else "twice" if n == 2 else "%s times" % _nw(n)


def count_p(n, one, many):
    return "%s %s" % (_nw(n), one if n == 1 else many)


def ago(d0, d1):
    n = d1 - d0
    return "yesterday" if n == 1 else "today" if n <= 0 else "%s days ago" % _nw(n)


def map_art(name):
    """'the Hospital' for a map the English calls by a noun, 'Downtown' / 'Hillside' / 'Hillcrest' without an article."""
    en = MAPN.EN_SHORT.get(str(name or ""), str(name or ""))
    if not en:
        return ""
    return en if en in ("Downtown", "Hillside", "Hillcrest", "Houses", "Suburbs") else "the " + en


def map_data(name):
    en = MAPN.EN_SHORT.get(str(name or ""), str(name or ""))
    return SD.MAPS.get(en, SD.GENERIC)


_NOT_VERB = {"always", "perhaps", "afterwards", "towards", "besides", "sometimes", "thus", "upstairs", "downstairs", "this", "its", "as", "us", "across", "less", "unless", "is_", "was_"}
_THEY = re.compile(r"\b([Tt]hey) ([a-z]+)\b")


def they_fix(text):
    """'they mentions' -> 'they mention' (a gender-neutral survivor is rendered with 'they' by clan_story.render; the templates conjugate for he / she)."""
    def sub(m):
        w = m.group(2)
        if w == "is":
            return m.group(1) + " are"
        if w == "was":
            return m.group(1) + " were"
        if w == "has":
            return m.group(1) + " have"
        if w == "does":
            return m.group(1) + " do"
        if w == "goes":
            return m.group(1) + " go"
        if w in _NOT_VERB or not w.endswith("s") or w.endswith("ss") or w.endswith("us"):
            return m.group(0)
        if w.endswith("ies") and len(w) > 5:
            return m.group(1) + " " + w[:-3] + "y"
        if w.endswith(("shes", "ches", "xes", "sses", "zes")):
            return m.group(1) + " " + w[:-2]
        return m.group(1) + " " + w[:-1]
    return _THEY.sub(sub, text)


def fit(cs, kind, p):
    """How well survivor p fits a story arc of `kind` (lower = better), from the saga memory: a person with a fresh wound does not go on a raid (arc 'missing'), a grieving
    one is the natural one for a last wish or a betrayal of trust, a rival for a blame arc, and so on.  clan_arcs._start sorts its candidates by this first."""
    m = (cs.get("mem") or {}).get(str(p["i"])) or {}
    inj, grief = bool(m.get("inj")), bool(m.get("grief"))
    s = 0
    if kind == "missing":
        s += 5 if inj else 0
        s -= 2 if p["r"] in ("scout", "scavenger", "guard") else 0
        s -= 1 if m.get("rel") else 0
    elif kind == "sick":
        s -= 2 if inj else 0
    elif kind in ("wish", "betray"):
        s -= 3 if grief else 0
    elif kind == "blame":
        s -= 2 if m.get("bt") == "rival" else 0
    elif kind == "keep":
        s -= 1 if m.get("poss") else 0
    elif kind == "new":
        s -= 1 if m.get("bond") else 0
    return s


def new_mem():
    return {"inj": None, "scars": [], "grief": None, "poss": None, "fear": None, "rel": {}, "last": -99, "bond": None, "bt": None}


def facts(match):
    """The player's real match as the saga reads it (every field optional)."""
    m = match or {}
    f = {"map": str(m.get("map") or "")}
    for k_in, k_out in (("kills", "k"), ("execs", "ex"), ("revives", "rv"), ("headshots", "hs"), ("downs", "dn"), ("deaths", "dt"), ("streak", "streak")):
        v = m.get(k_in)
        if v is not None:
            f[k_out] = int(v)
    if m.get("win") in (True, False):
        f["win"] = bool(m["win"])
    if m.get("weapon") in SD.WEAPONS:
        f["weapon"] = m["weapon"]
    return f


class Saga:
    def __init__(self, d, st, cs, r, match, rng, CH):
        self.d, self.st, self.cs, self.r, self.rng, self.CH = d, st, cs, r, rng, CH
        self.day, self.fk = d.day, d.fk
        self.f = facts(match) if match else {}
        for k, dv in (("mem", {}), ("gone", {}), ("you", {"inj": None, "streak": 0}), ("sg_used", {}), ("sg_stock", []), ("sg_keep", {}), ("sg_hist", []), ("sg_mourned", []),
                      ("sg_last", ""), ("sg_thread", 0), ("sg_kf", [])):
            cs.setdefault(k, dv)
        self.mem, self.gone, self.you, self.used = cs["mem"], cs["gone"], cs["you"], cs["sg_used"]
        self.F = D.FACTION[self.fk]
        self.base = {"camp": CAMPS[self.fk][_h("camp", st.get("tid", ""))  % 5], "leader": "Command" if self.fk == "W" else "the Prophet",
                     "enemy": self.F["enemy"], "enemies": "the " + self.F["enemies"], "enemy_n": "Scar" if self.fk == "W" else "Wolf"}
        self.rows, self.tids = [], []
        self.sync_roster()
        self.note_lack()

    # ------------------------------------------------------------ memory
    def M(self, p):
        m = self.mem.setdefault(str(p["i"]), new_mem())
        if m["poss"] is None or (KD.is_kid(p) and KD.combat_text(m["poss"], "en")):       # a kid's keepsake is never a bullet or a knife
            h = _h("poss", p["n"], p["r"])
            ok = [x for x in SD.POSSESSIONS if not (KD.is_kid(p) and KD.combat_text(x, "en"))]
            m["poss"] = ok[h % len(ok)]
            m["fear"] = m["fear"] if m["fear"] is not None else h >> 9
        return m

    def fear_of(self, p):
        i = self.M(p)["fear"] % len(SD.FEARS)
        return SD.FEARS[i]

    def sync_roster(self):
        """Memory follows the roster: the persona bond is cached, a member who died since the last day goes to cs["gone"] (grief for the close ones)."""
        CH, st = self.CH, self.st
        alive = {str(p["i"]) for p in st["people"]}
        for p in st["people"]:
            m = self.M(p)
            ps = CH.persona(p, st["people"], self.fk, st)
            m["bond"], m["bt"] = ps["bond"], ps["bt"]
            m["temper"] = ps["temper"]
            m["past"] = CH.PASTS[ps["past"]][2]
        for dd in st["dead"]:
            k = str(dd["i"])
            if k in self.cs["sg_mourned"]:
                continue
            self.cs["sg_mourned"].append(k)
            del self.cs["sg_mourned"][:-40]
            m = self.mem.pop(k, None) or new_mem()
            self.gone[k] = {"n": dd["n"], "g": dd["g"], "r": dd["r"], "d": dd["d"], "m": m}
            for p in st["people"]:
                mp = self.M(p)
                if mp["bond"] == dd["i"] or dd.get("k") == p["i"] or str(dd["i"]) in mp["rel"]:
                    mp["grief"] = {"for": dd["i"], "d": dd["d"], "until": dd["d"] + 8, "echo": -99}
        for k in [k for k in self.mem if k not in alive]:
            self.mem.pop(k, None)
        for k in list(self.gone):
            if self.day - self.gone[k]["d"] > 60:
                del self.gone[k]

    def note_lack(self):
        """A shortage day (r["sup"], tools/clan_supply.py) goes into the memory of the hungry / sick: m["lack"] = {c: the category that ran short, d: day}; a member who is
        healthy again forgets it.  Numbers stay clan.py's: this only remembers what the engine already did."""
        sup = self.r.get("sup") or {}
        cat = sup.get("cause") or ""
        for p in self.st["people"]:
            m = self.M(p)
            if p["s"] == "h":
                m.pop("lack", None)
            elif cat:
                c = "med" if (p["s"] == "s" and (sup.get("short") or {}).get("med")) else cat
                if c == "med" and p["s"] != "s":
                    c = next((k for k in ("food", "water") if (sup.get("short") or {}).get(k)), cat)
                m["lack"] = {"c": c, "d": self.day}

    def scene_lack(self):
        """A hungry or sick member whose trouble the memory ties to the day's shortage: a small scene that names the missing goods and what the larder holds."""
        sup = self.r.get("sup") or {}
        if not sup.get("cause"):
            return None
        pool = [p for p in self.d.alive if p["s"] in ("u", "s") and p["i"] not in self.d.spot and (self.M(p).get("lack") or {}).get("d") == self.day]
        pool.sort(key=lambda p: (self.d.used.get("P%d" % p["i"], -999), _h("lack", self.day, p["n"])))
        if not pool:
            return None
        A = pool[0]
        c = self.M(A)["lack"]["c"]
        v = {"lack_n": count_p(int(sup["short"].get(c, 0)) or 1, "unit", "units"), "lack_days": count_p(int((sup.get("days") or {}).get(c, 0)), "day", "days")}
        v["stock_n"] = int((sup.get("stock") or {}).get(c, 0))
        return self.entry("lack", "lack.title", [("lack." + c, True), ("lack.tail", False)], {"A": A, "B": self.partner(A)} if self.partner(A) else {"A": A}, v,
                          mood="worried")

    # ------------------------------------------------------------ text
    def has_fresh(self, *pools):
        """True when every pool still has a template not used inside the variety window (the new scenes skip a day rather than repeat a sentence)."""
        return all(any(self.day - self.used.get(str(_h(text)), -999) >= WINDOW for scope, text, _pk, _vk in POOLS.get(pool, ()) if scope in ("*", self.fk)) for pool in pools)

    def pl_text(self, pool, text):
        """The Polish twin of a template ('' without a Polish table) for the kid check."""
        try:
            return PLS.REG.get((pool, text), "") if PLS is not None else ""
        except Exception:                                                   # noqa: BLE001
            return ""

    def line(self, pool, people, vars_, must=True):
        """One English sentence of the pool (None when nothing fits); the Polish twin of it is left in self.pl_last (None when it could not be made)."""
        self.pl_last = None
        cands = []
        for scope, text, pk, vk in POOLS.get(pool, ()):
            if scope in ("*", self.fk) and pk <= people.keys() and vk <= vars_.keys():
                if text not in cands and KD.kid_safe(text, people, self.pl_text(pool, text)) and (not KD.any_kid(people) or KD.kid_text_ok(they_fix(CS.render(text, people, vars_)), people)):
                    cands.append(text)
        if not cands:
            return None
        fresh = [t for t in cands if self.day - self.used.get(str(_h(t)), -999) >= WINDOW]
        if not fresh:
            if not must:
                return None
            fresh = sorted(cands, key=lambda t: (self.used.get(str(_h(t)), -999), t))[:1]
        t = self.rng.choice(sorted(fresh))
        if self.day - self.used.get(str(_h(t)), -999) < WINDOW:
            sp = self.cs.setdefault("sg_stale_pools", {})
            sp[pool] = sp.get(pool, 0) + 1
            self.cs["sg_stale"] = self.cs.get("sg_stale", 0) + 1            # no fresh template was left: the least recently used one repeats
        self.used[str(_h(t))] = self.day
        self.tids.append(_h(t))
        self.pl_last = self.pl_line(pool, t, people, vars_)
        return they_fix(CS.render(t, people, vars_))

    def pl_line(self, pool, en_tpl, people, vars_):
        """The Polish rendering of the English template `en_tpl` of `pool` with the same people and variables; None when there is no Polish table (or, outside the strict test mode, a hole)."""
        if PLS is None:
            return None
        try:
            over = {"loot_list": vars_["loot_list_pl"]} if "loot_list_pl" in vars_ else {}
            for k_ in ("finds_text", "kfind"):                          # the rich loot model gives its own Polish text (tools/clan_loot.py)
                if k_ + "_pl" in vars_:
                    over[k_] = vars_[k_ + "_pl"]
            over = over or None
            vp, _src = PLS.expand(vars_, people, self.fk, over)
            return PLS.render(PLS.REG[(pool, en_tpl)], people, vp)
        except Exception:                                                   # noqa: BLE001 - the English row is still written
            if os.environ.get("T2R_SAGA_STRICT"):
                raise
            return None

    def prune(self):
        if len(self.used) > 900:
            for k in [k for k, v in self.used.items() if self.day - v > 3 * WINDOW]:
                del self.used[k]

    TAILS = {"inj": "tail.bad", "grief": "tail.bad", "death": "tail.bad", "loss": "tail.bad", "rel": "tail.calm", "use": "tail.calm", "keepcb": "tail.good", "keepfind": "tail.good", "dep": "tail.bad", "prof": "tail.calm",
             "haul": "tail.good", "prep": "tail.calm", "lack": "tail.bad", "quiet": "tail.calm", "win": "tail.good", "down": "tail.calm", "exec": "tail.bad", "rev": "tail.good"}

    def entry(self, scene, title, parts, people, extra, mood=None, thread=None):
        """title = pool; parts = [(pool, must)]; people = {"A": person, ..}; extra = vars.  None when the title or the body has nothing to say."""
        v = dict(self.base, **{k: x for k, x in extra.items() if x is not None})
        self.tids = []
        t = self.line(title, people, v)
        if not t:
            return None
        t_pl = self.pl_last
        body, body_pl = [], []
        for pool, must in parts:
            s = self.line(pool, people, v, must)
            if s:
                body.append(s)
                body_pl.append(self.pl_last)
        if not body:
            return None
        nsent = sum(len(re.split(r"(?<=[.!?])\s+", b.strip())) for b in body)
        if nsent < 3 and (nsent < 2 or self.rng.random() < 0.5):                     # the memory scenes are short: a tail makes them a small scene
            if "B" not in people and "A" in people:
                b = self.partner(people["A"], fight=scene in KD.COMBAT_SCENES_SAGA)
                if b is not None and b["i"] not in {x.get("i") for x in people.values()}:
                    people = dict(people, B=b)
            tl = self.line(self.TAILS.get(scene, "tail.calm"), people, v, False)
            if tl:
                body.append(tl)
                body_pl.append(self.pl_last)
        t = t.rstrip(".!? ")
        text = "DAY %d: %s. %s" % (self.day, t.upper(), " ".join(body))
        text_pl = None
        if t_pl and all(body_pl):
            text_pl = "DZIEŃ %d: %s. %s" % (self.day, t_pl.rstrip(".!? ").upper(), " ".join(body_pl))
        pp = {k: [x["n"], x["g"], x.get("r", "scavenger")] for k, x in people.items()}
        names = [x["n"] for x in people.values() if re.search(r"(?<!\w)" + re.escape(x["n"]) + r"(?!\w)", text)]
        s = {"f": self.fk, "day": self.day}
        if self.f.get("map"):
            s["map"] = self.f["map"]
        params = {"p": pp, "s": s, "t": text, "i": list(self.tids)}
        if text_pl:
            params["tp"] = text_pl                                                  # the Polish text of the same row (clan screens in Polish)
        if thread:
            params["a"] = thread
        for x in people.values():
            if "i" in x:
                self.d.used["P%d" % x["i"]] = self.day
                self.d.spot.add(x["i"])
                mm = self.M(x)
                mm["last"] = self.day
                mm["thread"] = {"k": scene, "d": self.day, "a": thread}
        return {"kind": "chron", "mood": mood or MOODS.get(scene, "calm"), "text": text, "names": names, "lid": "sg/" + scene, "params": params}

    # ------------------------------------------------------------ vars
    def match_vars(self):
        f, md = self.f, map_data(self.f.get("map"))
        pl = list(md["places"])
        self.rng.shuffle(pl)
        air = self.rng.choice(md["air"])
        v = {"map": map_art(f.get("map")), "place": pl[0], "place2": pl[1], "place3": pl[2],
             "air": ("the smell of " if air[0] == "s" else "the sound of ") + air[1]}
        sm = [a for a in md["air"] if a[0] == "s"] or md["air"]
        sd = [a for a in md["air"] if a[0] == "h"] or md["air"]
        v["smell"] = "the smell of " + self.rng.choice(sm)[1]
        v["sound"] = "the sound of " + self.rng.choice(sd)[1]
        if f.get("k"):
            v["k"] = f["k"]
        if f.get("ex"):
            v["ex_p"] = count_p(f["ex"], "execution", "executions")
            v["ex_t"] = times_p(f["ex"])
        if f.get("rv"):
            v["rv_p"] = count_p(f["rv"], "teammate", "teammates")
        if f.get("hs"):
            v["hs_p"] = count_p(f["hs"], "headshot", "headshots")
        if f.get("dn"):
            v["dn_p"] = times_p(f["dn"])
        if f.get("dt"):
            v["dt_p"] = times_p(f["dt"])
        if f.get("weapon"):
            v["wpn"] = SD.WEAPONS[f["weapon"]][0]
        if self.f.get("map"):
            v["place_gen"] = pl[0]
        return v

    def person(self, roles=(), exclude=(), states=("h", "u", "s"), fight=False):
        """The member who stars in a scene (spotlight-fair).  fight=True: a match, raid, haul, patrol or weapon scene - grown people only, never a kid (clan_kids.py)."""
        d = self.d
        pool = [p for p in d.alive if p["s"] in states and p["i"] not in d.spot and p["i"] not in exclude and (not fight or KD.can_fight(p))]
        if not pool:
            return None
        pref = [p for p in pool if p["r"] in roles]
        pool = pref or pool
        pool.sort(key=lambda p: (d.used.get("P%d" % p["i"], -999), self.M(p)["last"], _h("sg", self.day, p["n"])))
        return pool[0]

    def partner(self, A, exclude=(), fight=False):
        b = self.M(A)["bond"]
        q = next((p for p in self.d.alive if p["i"] == b), None)
        if q and q["i"] not in self.d.spot and q["i"] not in exclude and (not fight or KD.can_fight(q)):
            return q
        return self.person(exclude=set(exclude) | {A["i"]}, fight=fight)

    # ------------------------------------------------------------ the match story
    def match_story(self, loot):
        f, rng, day = self.f, self.rng, self.day
        v = self.match_vars()
        hist = self.cs["sg_hist"]
        prev = hist[-1] if hist else None
        win = f.get("win")
        kinds = []
        if win is False:
            kinds.append(("loss", 5))
        if f.get("dn", 0) >= 2:
            kinds.append(("down", 5 if win is not False else 3))
        if f.get("ex", 0) >= 1:
            kinds.append(("exec", 3 + min(3, f["ex"])))
        if f.get("rv", 0) >= 2:
            kinds.append(("rev", 3))
        if win is True:
            kinds.append(("win", 4))
        if not kinds:
            kinds.append(("quiet", 3))
        if self.cs["sg_last"] and len(kinds) > 1:
            kinds = [x for x in kinds if x[0] != self.cs["sg_last"]] or kinds
        scene = rng.choices([k for k, _ in kinds], weights=[w for _, w in kinds])[0]
        self.cs["sg_last"] = scene
        role = {"down": ("medic",), "loss": ("cook", "elder", "guard"), "win": ("cook", "elder"), "exec": ("medic", "elder", "cook"), "rev": ("scout", "medic"),
                "quiet": ("cook", "guard", "scavenger")}[scene]
        A = self.person(role, fight=True)
        if A is None:
            return None
        B = self.partner(A, fight=True)
        people = {"A": A}
        if B is not None:
            people["B"] = B
        # the previous days
        hist_maps = [h["map"] for h in hist if day - h["d"] <= 7 and h["map"] == f.get("map")]
        if prev:
            v["prev_map"] = map_art(prev["map"])
            v["prev_res"] = "a win" if prev.get("win") else "a loss" if prev.get("win") is False else "a plain day"
        if len(hist_maps) >= 1 and f.get("map"):
            v["nth"] = ORD.get(len(hist_maps) + 1, "again")
        lose_n = 0
        for h in reversed(hist):
            if h.get("win") is False:
                lose_n += 1
            else:
                break
        if win is False:
            lose_n += 1
        if lose_n >= 2:
            v["lossw"] = _nw(lose_n)
        yi = self.you["inj"]
        if yi and day - yi["d"] >= 1 and day - yi["d"] <= 12:
            v["ysite"], v["ymap"], v["yd"] = yi["site"], map_art(yi["map"]), yi["d"]
        site = rng.choice(SD.SITES)
        cloth = rng.choice(SD.CLOTHS)
        v["site"], v["cloth"] = site, cloth
        mood = None
        parts = [(scene + ".event", True)]
        if scene == "down":
            parts.append(("down.care", True))
            parts.append(("down.you" if "ysite" in v and rng.random() < 0.6 else "down.after", True))
        elif scene == "loss":
            parts.append(("loss.camp", True))
            parts.append(("loss.streak" if lose_n >= 2 else "loss.b", True))
            if lose_n < 2 and rng.random() < 0.4 and "ysite" in v:
                parts.append(("down.you", False))
        elif scene == "win":
            parts.append(("win.hs" if f.get("hs") else "win.camp", True))
            if prev and prev.get("win") is False and "prev_map" in v:
                parts.append(("win.after_loss", True))
            else:
                parts.append(("win.camp", True))
        elif scene == "exec":
            parts.append(("exec.react", True))
        elif scene == "rev":
            parts.append(("rev.react", True))
        else:
            parts.append(("quiet.camp", True))
        if win is not None and scene not in ("win", "loss") and rng.random() < 0.5:
            parts.insert(1, ("res.win" if win else "res.loss", False))
        if "nth" in v and rng.random() < 0.5:
            parts.append(("bridge.same_map", False))
        elif "ysite" in v and scene not in ("down", "loss") and rng.random() < 0.3:
            parts.append(("bridge.you_scar", False))
        # a raider is hurt on a bad day: the injury goes into the memory and comes back in later entries
        hurt = None
        if (win is False or f.get("dn", 0) >= 2 or f.get("dt", 0) >= 3) and rng.random() < 0.7:
            cand = [p for p in self.d.alive if p["i"] != A["i"] and p["r"] not in ("kid", "elder") and p["i"] not in self.d.spot and not self.M(p)["inj"] and p["s"] != "s"]
            if cand:
                hurt = rng.choice(sorted(cand, key=lambda p: p["i"]))
        if hurt is not None:
            people["B"] = hurt
            cause = rng.choice(SD.CAUSES).format(enemy_n=self.base["enemy_n"])
            v["cause"], v["job"] = cause, SD.JOBS.get(hurt["r"], "work")
            parts.insert(2, ("hurt.line", True))
        elif rng.random() < 0.3 and "B" in people:
            parts.append(("mark.line", False))
        if rng.random() < 0.28:
            tem = self.M(A).get("temper", "calm")
            parts.append(("quip.%s.%s" % ("good" if win is True or scene in ("win", "rev") else "bad", tem), False))
        row = self.entry(scene, scene + ".title", parts, people, v, mood=mood)
        if row is None:
            return None
        if hurt is not None:
            heal = day + rng.randint(3, 6)
            self.M(hurt)["inj"] = {"site": site, "cloth": cloth, "d": day, "heal": heal, "map": f.get("map", ""), "cause": v.get("cause", "")}
        if scene == "down" or (f.get("dn", 0) >= 2):
            self.you["inj"] = {"site": site, "d": day, "map": f.get("map", "")}
        self.cs["sg_hist"].append({"d": day, "map": f.get("map", ""), "win": f.get("win"), "dn": f.get("dn")})
        del self.cs["sg_hist"][:-14]
        return row

    # ------------------------------------------------------------ loot
    def book_loot(self, loot):
        """Remember where the loot was found: sg_stock (practical goods) and sg_keep (keepsakes)."""
        pl = list(map_data(self.f.get("map"))["places"])
        out = []
        for key, n in loot:
            where = self.rng.choice(pl)
            if key in self.CH.KEEP:
                self.cs["sg_keep"][key] = {"d": self.day, "m": self.f.get("map", ""), "p": where, "by": None}
            else:
                self.cs["sg_stock"].append({"k": key, "n": int(n), "d": self.day, "m": self.f.get("map", ""), "p": where})
            out.append((key, n, where))
        del self.cs["sg_stock"][:-24]
        return out

    def haul_story(self, loot_places):
        CH = self.CH
        v = self.match_vars()
        if loot_places:
            v["place"] = loot_places[0][2]
            if len(loot_places) > 1:
                v["place2"] = loot_places[1][2]
        v["loot_list"] = CH.join_list([CH.loot_phrase(k, n, "en") for k, n, _p in loot_places], "en")
        v["loot_list_pl"] = CH.join_list([CH.loot_phrase(k, n, "pl") for k, n, _p in loot_places], "pl")
        cats = {CH.USE[k][0] for k, _n, _p in loot_places if k in CH.USE}
        keeps = [k for k, _n, _p in loot_places if k in CH.KEEP]
        role = ("cook",) if "food" in cats else ("medic",) if "med" in cats else ("scout", "guard") if "ammo" in cats else ("mechanic",)
        A = self.person(role, fight=True)
        if A is None:
            return None
        B = self.partner(A, fight=True)
        people = {"A": A}
        if B is not None:
            people["B"] = B
        parts = [("haul.found", True)]
        for cat, pool in (("food", "haul.food"), ("med", "haul.med"), ("ammo", "haul.ammo"), ("tool", "haul.tool")):
            if cat in cats:
                parts.append((pool, False))
                break
        fl = list(getattr(self.d, "finds", None) or [])
        if fl:                                                          # the rich findings of the raid: who found what where, in what state (tools/clan_loot.py)
            import clan_loot as LT
            v["finds_text"], v["finds_text_pl"] = LT.finds_story(fl, "en"), LT.finds_story(fl, "pl")
            v["loot_list"], v["loot_list_pl"] = LT.items_text(fl, "en"), LT.items_text(fl, "pl")
            for f_ in LT.keepsakes(fl)[:2]:
                self.cs["sg_kf"].append({"k": f_["k"], "d": self.day, "m": self.f.get("map", ""), "w": f_.get("w", "")})
            del self.cs["sg_kf"][:-12]
            parts.insert(1, ("haul.finds", False))
        if keeps:
            v["kitem_a"] = CH.KEEP[keeps[0]][0]
            parts.append(("keep." + keeps[0], True))
            parts.append(("haul.keep", True))
        return self.entry("haul", "haul.title", parts, people, v, mood="cheerful" if self.f.get("win") is not False else "worried")

    # ------------------------------------------------------------ memory scenes
    def scene_injury(self):
        day = self.day
        for p in self.d.alive:
            m = self.M(p)
            inj = m["inj"]
            if not inj or p["i"] in self.d.spot or day - inj["d"] < 1:
                continue
            healed = day >= inj["heal"]
            v = {"site": inj["site"], "cloth": inj["cloth"], "kmap": map_art(inj["map"]) or "raid", "kd": inj["d"], "kd_ago": ago(inj["d"], day),
                 "job": SD.JOBS.get(p["r"], "work")}
            people = {"A": p}
            pool = "inj.healed" if healed else ("inj.mid")
            row = self.entry("inj", "inj.title", [(pool, True)], people, v, mood="hopeful" if healed else "worried", thread="sg-inj-%d-%d" % (p["i"], inj["d"]))
            if row:
                if healed:
                    m["scars"].append({"site": inj["site"], "map": inj["map"], "d": inj["d"]})
                    m["inj"] = None
                return row
        return None

    def scene_scar(self):
        for p in self.d.alive:
            m = self.M(p)
            if m["scars"] and p["i"] not in self.d.spot and self.day - m["scars"][-1]["d"] >= 6 and self.rng.random() < 0.5:
                s = m["scars"][-1]
                return self.entry("inj", "inj.title", [("scar.cb", True)], {"A": p}, {"site": s["site"], "kmap": map_art(s["map"]) or "raid"}, mood="calm")
        return None

    def scene_grief(self):
        day = self.day
        for p in self.d.alive:
            m = self.M(p)
            g = m["grief"]
            if not g or p["i"] in self.d.spot:
                continue
            if day > g["until"]:
                m["grief"] = None
                continue
            if day - g["echo"] < 2:
                continue
            dead = self.gone.get(str(g["for"]))
            if not dead:
                m["grief"] = None
                continue
            Dp = {"n": dead["n"], "g": dead["g"], "r": dead["r"]}
            dm = dead["m"]
            n = day - dead["d"]
            v = {"dgo": ("gone since yesterday" if n <= 1 else "gone %s days" % _nw(n)), "dpos": dm["poss"] or "a small keepsake"}
            people = {"A": p, "D": Dp}
            row = self.entry("grief", "grief.title", [("grief.line", True)], people, v, thread="sg-grief-%d" % g["for"])
            if row:
                g["echo"] = day
                return row
        return None

    def scene_rel(self):
        cand = []
        for p in self.d.alive:
            if p["i"] in self.d.spot:
                continue
            m = self.M(p)
            q = next((x for x in self.d.alive if x["i"] == m["bond"]), None)
            if q is None or q["i"] in self.d.spot or not m["bt"]:
                continue
            lvl = m["rel"].get(str(q["i"]), 0)
            if lvl >= 4:
                continue
            cand.append((p, q, m["bt"], lvl + 1))
        if not cand:
            return None
        cand.sort(key=lambda x: (self.M(x[0])["last"], _h("rel", self.day, x[0]["n"])))
        p, q, bt, lvl = cand[0]
        pool = "rel.%s.%d" % (bt, lvl)
        if pool not in POOLS:
            return None
        v = self.match_vars() if self.f.get("map") else {"map": "the yard"}
        row = self.entry("rel", "rel.title", [(pool, True)], {"A": p, "B": q}, v, thread="sg-rel-%d-%d" % (min(p["i"], q["i"]), max(p["i"], q["i"])))
        if row:
            self.M(p)["rel"][str(q["i"])] = lvl
            self.M(q)["rel"][str(p["i"])] = lvl
        return row

    def scene_keep_callback(self):
        olds = [(k, e) for k, e in self.cs["sg_keep"].items() if e["d"] < self.day and self.day - e["d"] <= 30]
        if not olds:
            return None
        k, e = self.rng.choice(sorted(olds))
        pool = "keepcb." + k
        if pool not in POOLS:
            return None
        role = ("kid",) if k in ("chess", "teddy", "comic") else ()
        A = self.person(role)
        if A is None:
            return None
        B = self.partner(A)
        people = {"A": A}
        if B is not None:
            people["B"] = B
        v = {"kd": e["d"], "kmap": map_art(e["m"]) or "a raid", "kplace": e["p"], "kitem": self.CH.KEEP[k][0].split(" ", 1)[1]}
        return self.entry("keepcb", "keepcb.title", [(pool, True)], people, v)

    def scene_keep_find(self):
        """A trinket or book found on an earlier raid (clan_loot keepsakes) comes back in a small scene."""
        import clan_loot as LT
        if not self.has_fresh("keepfind.title", "keepfind.line"):
            return None
        olds = [e for e in self.cs["sg_kf"] if 0 < self.day - e["d"] <= 30 and e["k"] in LT.ITEMS]
        if not olds:
            return None
        e = self.rng.choice(olds)
        A = self.person(("kid",) if LT.ITEMS[e["k"]]["cat"] in ("trink", "book") and self.rng.random() < 0.4 else ())
        if A is None:
            return None
        B = self.partner(A)
        people = {"A": A}
        if B is not None:
            people["B"] = B
        v = {"kd": e["d"], "kmap": map_art(e["m"]) or "a raid", "kfind": LT.ITEMS[e["k"]]["en1"], "kfind_pl": LT.ITEMS[e["k"]]["pln"]}
        return self.entry("keepfind", "keepfind.title", [("keepfind.line", True)], people, v)

    def scene_depressed(self):
        """A member who is depressed (clan_loot.update_moods) - or one who has just come back from it - gets a quiet scene."""
        dep = self.cs.get("dep") or {}
        if not self.has_fresh("dep.title"):
            return None
        cand = []
        for p in self.d.alive:
            e = dep.get(str(p["i"]))
            if not e or p["i"] in self.d.spot:
                continue
            m = self.M(p)
            if e["n"] >= 4 and self.day - m.get("depd", -99) >= 4:
                cand.append((p, "dep.line"))
            elif e.get("up") == self.day and m.get("depd", -99) != self.day:
                cand.append((p, "dep.up"))
        if not cand:
            return None
        cand = [c for c in cand if self.has_fresh(c[1])]
        if not cand:
            return None
        cand.sort(key=lambda c: (c[1] != "dep.up", self.d.used.get("P%d" % c[0]["i"], -999), c[0]["i"]))
        A, pool = cand[0]
        self.M(A)["depd"] = self.day
        B = self.partner(A)
        people = {"A": A}
        if B is not None:
            people["B"] = B
        return self.entry("dep", "dep.title", [(pool, True)], people, {}, mood="grieving" if pool == "dep.line" else "hopeful")

    def scene_use(self):
        cands = [e for e in self.cs["sg_stock"] if e["n"] > 0 and e["d"] < self.day]
        if not cands:
            return None
        e = self.rng.choice(cands)
        CH = self.CH
        cat = CH.USE[e["k"]][0]
        role = {"food": ("cook",), "med": ("medic",), "ammo": ("scout", "guard"), "tool": ("mechanic",)}[cat]
        A = self.person(role, fight=cat in ("ammo", "tool"))
        if A is None:
            return None
        use = self.rng.randint(3, 7) if e["k"] == "r38" else 1
        use = min(use, e["n"])
        left = e["n"] - use
        v = {"item_pl": CH.USE[e["k"]][2], "item_short": CH.USE[e["k"]][2], "kd": e["d"], "kmap": map_art(e["m"]) or "a raid", "kplace": e["p"], "kd_ago": ago(e["d"], self.day), "n": use,
             "n_left": "%d left" % left if left else "none left"}
        if e["k"] == "r38":
            v["item_pl"] = ".38 rounds"
        row = self.entry("use", "use.title", [("use." + cat, True)], {"A": A}, v)
        if row:
            e["n"] = left
            if cat in ("food", "med") and e["k"] in self.cs["inv"]:
                self.cs["inv"][e["k"]] = max(0, self.cs["inv"][e["k"]] - 1)
        return row

    def scene_prep(self):
        A = self.person(("scout", "guard"), fight=True)
        if A is None:
            return None
        f = self.f
        v = self.match_vars() if f.get("map") else {}
        if not v:
            md = SD.GENERIC
            v = {"map": "the next map", "place": md["places"][0], "place2": md["places"][1]}
        hist = self.cs["sg_hist"]
        prev = hist[-2] if len(hist) >= 2 else None       # hist[-1] is today's match
        if prev:
            v["prev_map"] = map_art(prev["map"])
            v["prev_res"] = "a win" if prev.get("win") else "a loss" if prev.get("win") is False else "a plain day"
        away = [self.d.byid[int(i)] for i in self.cs.get("away", {}) if int(i) in self.d.byid and KD.can_fight(self.d.byid[int(i)])]
        people = {"A": A}
        parts = [("prep.event", True)]
        if away:
            people["B"] = away[0]
            v["AW"] = away[0]["n"]
            parts.append(("prep.away", True))
        stock = [e for e in self.cs["sg_stock"] if e["n"] > 0]
        inv = self.cs["inv"]
        if stock:
            e = self.rng.choice(stock)
            v.update({"item_pl": self.CH.USE[e["k"]][2], "kplace": e["p"], "n": max(1, e["n"] // 2)})
            parts.append(("prep.stock", False))
        ammo = sum(n for k, n in inv.items() if self.CH.USE[k][0] == "ammo")
        food = sum(n for k, n in inv.items() if self.CH.USE[k][0] == "food")
        v["ammo_n"], v["food_n"] = count_p(ammo, "round", "rounds"), count_p(food, "can", "cans")
        if prev and "prev_map" in v:
            parts.append(("prep.recent", False))
        row = self.entry("prep", "prep.title", parts, people, v)
        if row and away:
            row["names"] = [x for x in row["names"]]
        return row

    def scene_profile(self):
        A = self.person()
        if A is None:
            return None
        m = self.M(A)
        fear, fwhat = self.fear_of(A)
        people = {"A": A}
        v = {"poss": m["poss"], "poss_short": m["poss"].split(" ", 1)[1] if m["poss"].split(" ", 1)[0] in ("a", "an") else m["poss"], "fear": fear,
             "fear_what": fwhat, "past": (m.get("past") or "survivor").lower()}
        parts = [(self.rng.choice(["prof.poss", "prof.fear", "prof.past"]), True)]
        if self.rng.random() < 0.7:
            parts.append(("prof." + m.get("temper", "calm"), False))
        return self.entry("prof", "prof.title", parts, people, v)

    def scene_death(self, died_now):
        dd = died_now[0]
        k = str(dd["i"])
        dead = self.gone.get(k)
        if not dead:
            return None
        mem = dead["m"]
        Dp = {"n": dead["n"], "g": dead["g"], "r": dead["r"]}
        q = next((p for p in self.d.alive if p["i"] == mem.get("bond")), None)
        A = q or self.person(("elder", "medic", "cook"))
        if A is None:
            return None
        B = self.person(exclude={A["i"]})
        people = {"A": A, "D": Dp}
        if B is not None:
            people["B"] = B
        inj = mem.get("inj")
        v = {"kplace": self.rng.choice(map_data(self.f.get("map"))["places"]) if self.f.get("map") else "the east wall", "dposx": mem["poss"] or "boots"}
        if inj:
            v["dsite"], v["dcloth"] = inj["site"], inj["cloth"]
        if mem.get("poss"):
            v["dpos"] = mem["poss"]
        parts = [("death.line", True), ("death.line", True)]
        row = self.entry("death", "death.title", parts, people, v, mood="grieving", thread="sg-grief-%d" % dd["i"])
        return row

    # ------------------------------------------------------------ the day
    def tie_arcs(self, arc_rows):
        """One sentence that ties a story arc's step to today's match (the arc text is stored by node; the tie rides along in params["tie"], English only)."""
        if not self.f.get("map") or not arc_rows:
            return
        for row in arc_rows:
            if self.rng.random() > 0.65:
                continue
            p = row["params"]["p"]
            who = p.get("A") or next(iter(p.values()), None)
            if not who:
                continue
            people = {"A": {"n": who[0], "g": who[1], "r": who[2] if len(who) > 2 else "scavenger"}}
            v = dict(self.base, **self.match_vars())
            self.tids = []
            t = self.line("arc.tie", people, v, False)
            if t:
                row["params"]["tie"] = t
                row["text"] = row["text"] + " " + t
                if self.pl_last:
                    row["params"]["tie_pl"] = self.pl_last

    def run(self, loot, died_now, arc_rows=()):
        rows = []
        self.tie_arcs(arc_rows)
        self.d.spot |= {int(i) for i in self.cs.get("away", {})}
        if self.f.get("map"):
            lp = self.book_loot(loot or [])
            row = self.match_story(loot)
            if row:
                rows.append(row)
            if loot and lp:
                row = self.haul_story(lp)
                if row:
                    rows.append(row)
        extra = None
        if died_now:
            extra = self.scene_death(died_now)
        if extra is None:
            opts = []
            for name, fn, w in (("inj", self.scene_injury, 5), ("grief", self.scene_grief, 5), ("scar", self.scene_scar, 1), ("rel", self.scene_rel, 3),
                                ("lack", self.scene_lack, 4), ("keepcb", self.scene_keep_callback, 3), ("keepfind", self.scene_keep_find, 3), ("dep", self.scene_depressed, 9), ("use", self.scene_use, 3), ("prep", self.scene_prep, 3), ("prof", self.scene_profile, 2)):
                opts.append((fn, w))
            order = []
            pool = list(opts)
            while pool:
                fn = self.rng.choices([f for f, _ in pool], weights=[w for _, w in pool])[0]
                order.append(fn)
                pool = [(f, w) for f, w in pool if f is not fn]
            for fn in order:
                extra = fn()
                if extra:
                    break
        if extra:
            rows.append(extra)
        self.prune()
        return rows


SWITCH_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "clan_saga.txt")


def enabled():
    """Switch: env T2R_CLAN_SAGA=0/1, else tools/clan_saga.txt containing 0 / off; default ON (the saga only runs inside the chronicle, which is itself switched)."""
    v = os.environ.get("T2R_CLAN_SAGA")
    if v is None:
        try:
            v = open(SWITCH_FILE, encoding="utf-8").read().strip()
        except OSError:
            return True
    return v.lower() not in ("0", "off", "false", "no")


def run(d, st, newc, r, match, cs, rng, CH, loot, died_now, arc_rows=()):
    """The saga rows of one clan day (at most 3); [] when the roster is too small."""
    if len(d.alive) < 3 or not enabled():
        return []
    return Saga(d, st, cs, r, match, rng, CH).run(loot, died_now, arc_rows)


def render_msg(lid, params, lang="en"):
    """A stored saga row: the finished text in the language of the clan screen - English params["t"], Polish params["tp"] (None for a row written before the Polish table existed:
    the feed then shows the English row)."""
    if not lid or not lid.startswith("sg/") or not isinstance(params, dict):
        return None
    if lang == "pl" or str(lang).lower().startswith("pl"):
        return params.get("tp")
    return params.get("t")
