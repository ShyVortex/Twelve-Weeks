"""Clan member STATUS UPDATES: who changed state since the player last looked - hungry / sad (grief) / sick / dead (also injured, recovered, new).

Read-only observer: it never changes a clan number or a person's state.  clan_chronicle.day_rows calls observe() after the day's rows exist; the snapshot of
every member's status code and the pending events live in st["ch"]["stat"] = {"snap": {id: code}, "ev": [event, ...]}.  An event:
  {"i": id, "n": name, "g": gender, "r": role, "c": code, "f": previous code, "d": day, "ln": the journal line it came from ("" = use the template)}
Events are kept EV_DAYS days (the player is never asked to acknowledge: the launcher and the game remember which ids they showed, key = i:c:d).

Codes: 0 healthy, 1 hungry, 2 sad, 3 sick, 4 dead, 5 injured, 6 recovered (back to healthy), 7 new member, 8 depressed, 9 shock.
Mood chain (tools/clan_loot.update_moods): a hungry / grieving member of a clan that keeps doing badly (fortune score < -0.3 for 2+ days) gets a
depression counter st["ch"]["dep"][id]["n"] (+1 a day); at 4 the member is DEPRESSED (8).  A good day (fortune > 0) lowers it by 2: depressed -> sad -> healthy.  SHOCK (9) is
the day a close member died (grief memory starts that day), then sad.  Deaths stay clan.py's (the supply deficit kills); depression only shows the road there.
On the 0xE1 wire sci<k> carries 0..7 only (8 and 9 go out as 2 = sad: an old ext skips unknown codes, it would drop the event); a new token scx<k>=8|9 carries the real
code and clancard.h (cc_parse_status) prefers it.  The launcher gets the real state names and image ids from public().
Wire (tail of the 0xE1 clan state text; integers first, names last - an old ext stops at the first name, an old daemon sends nothing):
  sc=<n> sci<k>=<code> scd<k>=<day> scg<k>=<0 male / 1 female> scl<k>=<head model 0..3> ... scm<k>=<Name with _ for spaces>
Headshots: image id per member + expression, "<fac>/<sex>/<model>/<neutral|hungry|sad|sick|dead>" (portrait_id of clan_chronicle); the portraits drop in later
without any code change (the launcher shows the silhouette placeholder when a picture is missing).
"""
import os
import re

HEALTHY, HUNGRY, SAD, SICK, DEAD, INJURED, RECOVERED, NEW, DEPRESSED, SHOCK = range(10)
NAMES = ["healthy", "hungry", "sad", "sick", "dead", "injured", "recovered", "new", "depressed", "shock"]
EXPR = {HEALTHY: "neutral", HUNGRY: "hungry", SAD: "sad", SICK: "sick", DEAD: "dead", INJURED: "sick", RECOVERED: "neutral", NEW: "neutral", DEPRESSED: "depressed", SHOCK: "shock"}
DEP_AT = 4                           # depression counter at which a member is depressed (clan_loot.update_moods)
EV_DAYS = 3
EV_MAX = 6
LINES = {
    "en": {HUNGRY: "%s has gone hungry. The rations did not stretch.", SAD: "%s is grieving and barely speaks.", SICK: "%s has fallen sick.", DEAD: "%s did not make it.",
           INJURED: "%s is hurt and on light duty.", RECOVERED: ("%s is back on his feet.", "%s is back on her feet."), NEW: "%s has joined the clan.",
           DEPRESSED: "%s has withdrawn completely and no longer eats at the fire.", SHOCK: "%s is in shock after the loss."},
    "pl": {HUNGRY: ("%s jest głodny. Racji nie starczyło.", "%s jest głodna. Racji nie starczyło."),
           SAD: ("%s pogrążył się w żałobie i prawie się nie odzywa.", "%s pogrążyła się w żałobie i prawie się nie odzywa."), SICK: ("%s zachorował.", "%s zachorowała."),
           DEAD: ("%s nie przeżył.", "%s nie przeżyła."), INJURED: ("%s jest ranny i dostał lżejszą służbę.", "%s jest ranna i dostała lżejszą służbę."),
           RECOVERED: ("%s stanął na nogi.", "%s stanęła na nogi."), NEW: ("%s dołączył do klanu.", "%s dołączyła do klanu."),
           DEPRESSED: ("%s zamknął się w sobie i nie siada już do ogniska.", "%s zamknęła się w sobie i nie siada już do ogniska."),
           SHOCK: ("%s jest w szoku po stracie.", "%s jest w szoku po stracie.")},
}


def enabled():
    v = os.environ.get("T2R_CLAN_STATUS", "")
    return v.strip().lower() not in ("0", "off", "no")


def code_of(st, p):
    """Status code of a living member: sick > hungry > sad (grief memory still running) > injured > healthy."""
    s = p.get("s", "h")
    day = int(st.get("day", 0) or 0)
    mem = ((st.get("ch") or {}).get("mem") or {}).get(str(p["i"])) or {}
    dep = ((st.get("ch") or {}).get("dep") or {}).get(str(p["i"])) or {}
    if int(dep.get("n", 0)) >= DEP_AT:
        return DEPRESSED
    g0 = mem.get("grief")
    if g0 and int(g0.get("d", -1)) == day:
        return SHOCK
    if s == "s":
        return SICK
    if s == "u":
        return HUNGRY
    g = mem.get("grief")
    if g and int(g.get("until", -1)) >= day:
        return SAD
    if dep.get("rec") and int(dep.get("n", 0)) > 0:
        return SAD                                                   # on the way back from depression: depressed -> sad -> healthy
    if (mem.get("inj") or p.get("il")) and p.get("r") != "kid":      # a kid is never "hurt and on light duty" (no fight wounds, no duty: clan_kids.py)
        return INJURED
    return HEALTHY


def _line(row_text, names=()):
    """The headline of a chronicle row 'DAY n: HEAD. Body' as the short story line (falls back to the first sentence)."""
    m = re.match(r"^(?:DAY|DZIEŃ) \d+: ([^.]*)\.\s*([\s\S]*)$", row_text or "")
    if not (m and m.group(1).strip()):
        return ""
    t = m.group(1).strip().capitalize()
    try:                                                             # names and map names keep their capitals ("picked Hillside", never "hillside")
        import clan_continuity
        t = clan_continuity.restore_case(t, clan_continuity.proper_nouns(names))
    except Exception:                                                # noqa: BLE001
        pass
    return t + "."


def observe(st, rows=None):
    """Compare every member with the snapshot of the last call; new events go to st["ch"]["stat"]["ev"].  The first call only seeds the snapshot (a fresh
    install is not told about the whole camp).  Returns the new events."""
    if not enabled() or not st:
        return []
    cs = st.setdefault("ch", {})
    try:
        import clan_loot
        clan_loot.update_moods(st, cs)                               # no-op when the chronicle already did it today
    except Exception:                                                # noqa: BLE001 - the mood chain never breaks the status events
        pass
    S = cs.setdefault("stat", {"snap": {}, "ev": []})
    day = int(st.get("day", 0) or 0)
    seeded = bool(S.get("seeded"))
    snap = S["snap"]
    new = []
    names = {}
    for r in rows or []:
        for n in r.get("names") or []:
            names.setdefault(n, r.get("text") or "")

    def add(p, c, f):
        new.append({"i": p["i"], "n": p["n"], "g": p.get("g", "n"), "r": p.get("r", ""), "c": c, "f": f, "d": day, "ln": _line(names.get(p["n"], ""), [x["n"] for x in st.get("people", [])] + [x["n"] for x in st.get("dead", [])])})
    alive = set()
    for p in st.get("people", []):
        k = str(p["i"])
        alive.add(k)
        c = code_of(st, p)
        was = snap.get(k)
        if seeded:
            if was is None:
                add(p, NEW, 0)
            elif c != was:
                add(p, RECOVERED if c == HEALTHY else c, was)
        snap[k] = c
    for dd in st.get("dead", []):
        k = str(dd["i"])
        if snap.get(k) != DEAD:
            if seeded and k in snap:
                add({"i": dd["i"], "n": dd["n"], "g": dd.get("g", "n"), "r": dd.get("r", "")}, DEAD, snap.get(k, 0))
            snap[k] = DEAD
    for k in [k for k in snap if k not in alive and snap[k] != DEAD]:
        del snap[k]
    for k in [k for k, v in snap.items() if v == DEAD][:-30]:
        del snap[k]
    S["seeded"] = 1
    ev = [e for e in S["ev"] if day - e["d"] < EV_DAYS] + new
    S["ev"] = ev[-EV_MAX:]
    return new


def pending(st):
    """The events still on offer (oldest first)."""
    if not enabled() or not st:
        return []
    S = ((st.get("ch") or {}).get("stat")) or {}
    day = int(st.get("day", 0) or 0)
    return [e for e in S.get("ev", []) if day - e["d"] < EV_DAYS]


def event_id(e):
    return "%s:%s:%s" % (e["i"], e["c"], e["d"])


def sex_of(e):
    from clan_chronicle import _h
    return "f" if e.get("g") == "f" else "m" if e.get("g") == "m" else ("f" if _h("sex", e["n"]) & 1 else "m")


def look_of(e):
    from clan_chronicle import _h
    return _h("model", e["n"]) % 4


def images(e, fk, st=None):
    """Per member + expression image ids {neutral, hungry, sad, sick, dead} (the hook for real headshots)."""
    import clan_chronicle as CH
    sex, model = CH.head_model({"n": e["n"], "g": e.get("g", "n"), "r": e.get("r", "")}, fk, members=(list(st["people"]) + list(st.get("dead") or [])) if st else None)       # the SAME head as the roster card
    return {x: "%s/%s/%d/%s" % (fk, sex, model, CH.fit_expr(model, x)) for x in ("neutral", "hungry", "sad", "sick", "dead", "depressed", "shock")}


def story_line(e, lang="en"):
    if e.get("jl"):                                                  # the journal's own sentence about the member (tools/clan_journal.status_lines): no two cards read the same
        try:
            import clan_journal
            t = clan_journal.render(e["jl"], lang)
            if t:
                return t
        except Exception:                                            # noqa: BLE001
            pass
    if e.get("ln"):
        return e["ln"]
    t = LINES["pl" if lang == "pl" else "en"].get(e["c"], "%s")
    if isinstance(t, tuple):
        t = t[1 if sex_of(e) == "f" else 0]
    return t % e["n"]


def public(st, fk, lang="en"):
    """For the launcher / clanfeed 'chron.status': the pending events with image ids, story line and the colour state names."""
    out = []
    for e in pending(st):
        out.append({"id": event_id(e), "name": e["n"], "role": e.get("r", ""), "code": e["c"], "state": NAMES[e["c"]], "from": NAMES[e.get("f", 0)], "day": e["d"],
                    "expr": EXPR[e["c"]], "img": images(e, fk, st), "line": story_line(e, lang), "ln": bool(e.get("ln"))})
    return out


def wire_text(st):
    """The tail for the 0xE1 state text ('' when nothing is pending)."""
    ev = pending(st)[-4:]
    if not ev:
        return ""
    f = ["sc=%d" % len(ev)]
    for k, e in enumerate(ev):
        f += ["sci%d=%d" % (k, e["c"] if e["c"] < 8 else SAD)] + (["scx%d=%d" % (k, e["c"])] if e["c"] >= 8 else []) + [ "scd%d=%d" % (k, e["d"]), "scg%d=%d" % (k, 1 if sex_of(e) == "f" else 0), "scl%d=%d" % (k, look_of(e))]
    for k, e in enumerate(ev):
        f.append("scm%d=%s" % (k, "".join(ch if (ch.isalnum() and ord(ch) < 128) or ch in "-'" else "_" for ch in e["n"])[:20]))
    return " ".join(f)
