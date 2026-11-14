"""Clan journal continuity (EN + PL): makes the plain diary rows read as one story, and gives a clan that existed before the chronicle a recap to continue from.

Root cause it fixes: the chronicle (saga, arcs, member memory) is the only part of the journal that
refers back to earlier entries, and it ran only behind a switch that defaulted OFF (clan_chronicle.enabled), so a clan's journal held nothing but the templated diary rows -
each one a stand-alone line.  Three things here (read side + one write):

  1. annotate(): READ-time call-backs and thread ids for the diary rows.  An illness chains onset -> worse / medicine -> recovery / death_illness of the same patient; a death
     chains grief / hope_after rows of the same dead member.  A row that continues an earlier one gets a short tail ("Karen has been ill since day 23.", "Reggie died 3 days
     ago.") plus thread / tstep / prev (the id of the entry it continues).  Nothing is stored: old rows get it too, and PL is rendered per language.
  2. recap_rows(): ONE chronicle row ("cn/recap", kind "chron") on the first chronicle day of a clan that already has a diary: who we buried lately (with the day), who is still
     ill (since when).  It is the bridge from the old diary into the saga / arcs; the saga itself already mourns earlier deaths (clan_saga.sync_roster).
  3. render_msg(): re-renders a recap row in either language.

Never changes a number or a person's state; the diary's randomness is untouched (the recap row has kind "chron", which does not advance the diary counter)."""

ILL_KINDS = ("worse", "medicine", "recovery", "death_illness")
MOURN_KINDS = ("grief", "hope_after")
RECAP_MIN_ROWS = 4                       # a clan with fewer diary rows has nothing to recap
RECAP_DEAD, RECAP_SICK, RECAP_DAYS = 3, 3, 21


def _days_ago_en(n):
    return "yesterday" if n == 1 else "%d days ago" % n


def _days_ago_pl(n):
    return "wczoraj" if n == 1 else "%d dni temu" % n


def tail(kind, role, name, a, b, lang):
    """The call-back sentence. role: 'ill' | 'mourn'; a = onset day / death day; b = the row's day. Relative ("for 4 days"), never an absolute clan day: the journal
    shows the day of the WEEK, so "since day 31" next to a "DAY 4" card read as a different calendar."""
    n = int(b) - int(a)
    if n <= 0:
        return ""
    if lang == "pl":
        if role == "ill":
            if kind == "recovery":
                return "%s: choroba zaczęła się %s." % (name, "wczoraj" if n == 1 else "%d dni wcześniej" % n)
            if kind == "death_illness":
                return "%s: choroba trwała %s." % (name, "dzień" if n == 1 else "%d dni" % n)
            return "%s choruje od %s." % (name, "wczoraj" if n == 1 else "%d dni" % n)
        return "%s nie żyje od %s." % (name, "wczoraj" if n == 1 else "%d dni" % n)
    if role == "ill":
        if kind == "recovery":
            return "%s fell ill %s." % (name, "the day before" if n == 1 else "%d days earlier" % n)
        if kind == "death_illness":
            return "%s had been ill for %s." % (name, "a day" if n == 1 else "%d days" % n)
        return "%s has been ill %s." % (name, "since yesterday" if n == 1 else "for %d days" % n)
    return "%s died %s." % (name, _days_ago_en(n))


MATCH_STYLES = {"saga_win": 1, "saga_loss": 0, "saga_down": None, "saga_prep": None}
HAUL_STYLE = "saga_haul"


def _map_pl(name):
    try:
        import clan_chronicle_maps as MAPN
        return MAPN.PL.get(name, name)
    except Exception:                                                          # noqa: BLE001
        return name


def match_tail(prev, m, lang):
    """The call-back of a match story to the previous one on the same map: ' Last time on the Lakeside: day 20, lost.'"""
    won = MATCH_STYLES.get(prev.get("style"))
    d = int(prev.get("day") or 0)
    name = m.get("map", "")
    if lang == "pl":
        return " Poprzednio (%s): dzień %d%s." % (_map_pl(name), d, "" if won is None else (", wygrana" if won else ", porażka"))
    return " Last time on %s: day %d%s." % (name, d, "" if won is None else (", won" if won else ", lost"))


def haul_tail(prev, lang):
    d = int(prev.get("day") or 0)
    return (" Poprzedni łup: dzień %d." if lang == "pl" else " The haul before this one came in on day %d.") % d


def _who(m):
    return m.get("who") or {}


def annotate(ctx, dead, sick_since=None, lang_req="en"):
    """ctx = the feed rows, NEWEST FIRST (read_feed shape, with "who" = {letter: name}); dead = clan_story state["dead"] ([{n, d}]); sick_since = {name: day} of the
    members who are ill right now (fallback for an onset older than the kept feed).  Adds, in place, to every diary row that continues an earlier one:
    text tail, "thread" (id), "tstep" (position in the thread, 1 = the first row we know), "prev" (id of the entry it continues)."""
    sick_since = sick_since or {}
    death_day = {}
    for d in dead or []:
        death_day[str(d.get("n"))] = int(d.get("d", 0))
    rows = sorted(ctx, key=lambda m: m["id"])                                  # oldest first
    open_ill = {}                                                              # patient -> [onset day, thread id, last row id, step]
    open_mourn = {}                                                            # dead name -> [death day, thread id, last row id, step]
    out = []
    last_map, last_haul = {}, None                                             # map -> the previous match story on it; the previous haul story
    for m in rows:
        kind, day, w = m.get("kind", ""), int(m.get("day") or 0), _who(m)
        sty = m.get("style")
        lang = m.get("lang") or lang_req                                       # a row that could only be rendered in English gets an English tail
        if sty in MATCH_STYLES and m.get("map"):                               # a match story: calls back the previous one on the same map
            pv = last_map.get(m["map"])
            if pv and int(pv.get("day") or 0) < day:
                m["text"] = m["text"].rstrip() + match_tail(pv, m, lang)
                m["thread"], m["prev"], m["tstep"] = "raid-%s" % m["map"], pv["id"], pv.get("tstep", 1) + 1
                if "thread" not in pv:
                    pv["thread"], pv["tstep"], pv["prev"] = m["thread"], 1, 0
            last_map[m["map"]] = m
            continue
        if sty == HAUL_STYLE:
            if last_haul and int(last_haul.get("day") or 0) < day and last_haul.get("week") == m.get("week"):
                m["text"] = m["text"].rstrip() + haul_tail(last_haul, lang)
                m["thread"], m["prev"], m["tstep"] = "haul-w%s" % m.get("week"), last_haul["id"], last_haul.get("tstep", 1) + 1
                if "thread" not in last_haul:
                    last_haul["thread"], last_haul["tstep"], last_haul["prev"] = "haul-w%s" % m.get("week"), 1, 0
            last_haul = m
            continue
        if sty:
            continue                                                           # other chronicle / saga / arc / perk rows carry their own continuity
        if kind == "sick" and w.get("A"):
            open_ill[w["A"]] = [day, "ill-%s-%d" % (w["A"], day), m["id"], 1]
            m["_first"] = open_ill[w["A"]]
            continue
        if kind in ILL_KINDS and w.get("A"):
            name = w["A"]
            t = open_ill.get(name)
            if t is None and name in sick_since and int(sick_since[name]) < day:
                t = open_ill[name] = [int(sick_since[name]), "ill-%s-%d" % (name, int(sick_since[name])), 0, 0]
            if t is None:
                continue
            ln = tail(kind, "ill", name, t[0], day, lang)
            if ln and "day %d" % t[0] not in m["text"] and "dnia %d" % t[0] not in m["text"]:
                m["text"] = m["text"].rstrip() + " " + ln
            m["thread"], m["prev"], m["tstep"] = t[1], t[2], t[3] + 1
            t[2], t[3] = m["id"], t[3] + 1
            if kind in ("recovery", "death_illness"):
                open_ill.pop(name, None)
            continue
        if kind.startswith("death_") or kind.startswith("loss"):
            for nm in m.get("names") or []:
                if str(nm) in death_day and death_day[str(nm)] == day:
                    open_mourn[str(nm)] = [day, "mourn-%s" % nm, m["id"], 1]
                    m["_first"] = open_mourn[str(nm)]
                    break
            continue
        if kind in MOURN_KINDS and w.get("D"):
            name = w["D"]
            dd = death_day.get(name)
            if dd is None or dd >= day:
                continue
            t = open_mourn.setdefault(name, [dd, "mourn-%s" % name, 0, 0])
            ln = tail(kind, "mourn", name, dd, day, lang)
            if ln and "day %d" % dd not in m["text"] and "dnia %d" % dd not in m["text"]:
                m["text"] = m["text"].rstrip() + " " + ln
            m["thread"], m["prev"], m["tstep"] = t[1], t[2], t[3] + 1
            t[2], t[3] = m["id"], t[3] + 1
    # the first row of a thread that did continue (onset / the death) is a thread member too
    ids = {}
    for m in rows:
        if m.get("thread"):
            ids.setdefault(m["thread"], []).append(m)
    for m in rows:
        f = m.pop("_first", None)
        if f and f[1] in ids:
            m["thread"], m["tstep"], m["prev"] = f[1], 1, 0
    for m in rows:
        if m.get("thread") and m.get("prev") and m["prev"] not in {x["id"] for x in rows}:
            m["prev"] = 0
    return rows


# ------------------------------------------------------------------ the recap of a clan that existed before the chronicle
def _lst(items, lang, fmt):
    parts = [fmt % (n, d) for n, d in items]
    if len(parts) <= 1:
        return "".join(parts)
    return ", ".join(parts[:-1]) + (" i " if lang == "pl" else " and ") + parts[-1]


def render_msg(lid, params, lang="en"):
    if lid != "cn/recap" or not isinstance(params, dict):
        return None
    day = int(params.get("d", 0))
    dead = [(x[0], int(x[2])) for x in params.get("dead", [])]
    sick = [(x[0], int(x[2])) for x in params.get("sick", [])]
    if lang == "pl":
        s = []
        if dead:
            s.append("Ostatni, których pochowaliśmy: %s." % _lst(dead, lang, "%s (dzień %d)"))
        if sick:
            s.append("Wciąż leżą: %s." % _lst(sick, lang, "%s (od dnia %d)"))
        if not dead and not sick and params.get("alive"):
            s.append("Wciąż jest nas %d." % int(params["alive"]))
        s.append("Zapiski idą dalej od dnia %d." % day)
        return "DZIEŃ %d: GDZIE STOIMY. %s" % (day, " ".join(s))
    s = []
    if dead:
        s.append("The last we buried: %s." % _lst(dead, lang, "%s (day %d)"))
    if sick:
        s.append("Still down: %s." % _lst(sick, lang, "%s (since day %d)"))
    if not dead and not sick and params.get("alive"):
        s.append("%d of us are still here." % int(params["alive"]))
    s.append("The ledger goes on from day %d." % day)
    return "DAY %d: WHERE WE STAND. %s" % (day, " ".join(s))


def recap_rows(c, tid, st, newc, mood="worried"):
    """[] or ONE chronicle row; marks st["ch"]["cn"] either way (it is a one-time bridge)."""
    cs = st.setdefault("ch", {})
    if cs.get("cn"):
        return []
    cs["cn"] = int(newc["day"])
    day = int(newc["day"])
    try:
        n = c.execute("SELECT COUNT(*) FROM clan_feed WHERE token_id=? AND kind NOT IN ('chron','alife')", (tid,)).fetchone()[0]
    except Exception:                                               # noqa: BLE001
        return []
    if n < RECAP_MIN_ROWS:
        return []
    dead = [d for d in sorted(st.get("dead", []), key=lambda d: -int(d.get("d", 0))) if day - int(d.get("d", 0)) <= RECAP_DAYS and int(d.get("d", 0)) < day][:RECAP_DEAD]
    sick = [p for p in st.get("people", []) if p.get("s") == "s" and 0 < int(p.get("id") or 0) < day][:RECAP_SICK]
    params = {"alive": len(st.get("people", [])), "d": day, "dead": [[d["n"], d.get("g", "n"), int(d["d"])] for d in reversed(dead)], "sick": [[p["n"], p.get("g", "n"), int(p["id"])] for p in sick]}
    text = render_msg("cn/recap", params, "en")
    return [{"kind": "chron", "mood": mood, "text": text, "names": [x[0] for x in params["dead"]] + [x[0] for x in params["sick"]], "lid": "cn/recap", "params": params}]


# ------------------------------------------------------------------ proper nouns in lower-cased headlines (status cards / LATELY)
def proper_nouns(extra=()):
    """Member names (extra) + every map display name (EN and PL): a headline that is lower-cased into a sentence must get them back with their capitals."""
    out = [str(x) for x in extra if x]
    try:
        import clan_chronicle_maps as MAPN
        out += list(MAPN.PL) + list(MAPN.PL.values()) + list(MAPN.EN_SHORT.values())
    except Exception:                                                          # noqa: BLE001
        pass
    return sorted({x for x in out if x}, key=len, reverse=True)


def restore_case(text, names):
    import re
    for n in names:
        text = re.sub(r"(?<!\w)%s(?!\w)" % re.escape(n.lower()), lambda m, n=n: n, text, flags=re.I) if n.lower() in text.lower() else text
    return text
