"""Read-only clan view for the launcher's CLAN tab: GET /clan.json?player=<install id>.

Opens the daemon's t2r.db with mode=ro (never writes, never migrates: tools/clan.py load()/ensure() would ALTER TABLE, so the row is read
directly) and turns it into JSON with the rules/names of tools/clan.py (needed per day, week/day, event calendar, missions, boosters).
`player` = the 12-byte install id (24 hex chars; the last 24 chars of the 64-hex name token also work), the key of the clans table.
"""
import json
import os
import re
import sqlite3
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import clan  # noqa: E402  (tools/clan.py: pure rules, no DB access at import)
import clan_supply  # noqa: E402

ID_RE = re.compile(r"^[0-9a-fA-F]{24}$|^[0-9a-fA-F]{64}$")
STATUS = {0: "none", clan.ALIVE: "alive", clan.DEAD: "dead", clan.WON: "won"}


def _json(s, default):
    try:
        v = json.loads(s or "")
        return v if isinstance(v, type(default)) else default
    except ValueError:
        return default


def resolve_key(c, tid):
    """The clans-table key the DAEMON uses for this install (daemon.clan_key): "s:<steamid>" when the install's token is linked to a Steam account that
    has a clan row, else the install id. Read-only (the daemon's adoption of an older install's clan is not replayed: until the account row exists
    the install's own row is shown). Without a players table / steamid: tid."""
    try:
        for (sid,) in c.execute("SELECT DISTINCT steamid FROM players WHERE substr(token,41,24)=? AND steamid>0", (tid,)).fetchall():
            key = "s:%d" % int(sid)
            if c.execute("SELECT 1 FROM clans WHERE token_id=?", (key,)).fetchone():
                return key
    except sqlite3.Error:
        pass
    return tid


def view(db_path, player, key=None):
    """`key` (admin site): the clans-table key itself ("s:<steamid>" or an install id), used as is: no id check, no steam resolve."""
    if key is None and not ID_RE.match(player or ""):
        return {"ok": False, "error": "bad player id"}
    tid = key if key is not None else clan.token_id(player)
    try:
        c = sqlite3.connect("file:%s?mode=ro" % os.path.abspath(db_path).replace("\\", "/"), uri=True, timeout=2)
    except sqlite3.Error as e:
        return {"ok": False, "error": "database unavailable: %s" % e}
    try:
        c.row_factory = sqlite3.Row
        if key is None:
            tid = resolve_key(c, tid)
        try:
            row = c.execute("SELECT * FROM clans WHERE token_id=?", (tid,)).fetchone()
        except sqlite3.Error:
            row = None
        boosters = {}
        try:
            for bid, n in c.execute("SELECT bid, n FROM boosters WHERE token_id=?", (tid,)):
                boosters[int(bid)] = int(n)
        except sqlite3.Error:
            pass
    finally:
        c.close()
    if not row:
        return {"ok": True, "hasClan": False}
    k = dict(row)
    g = lambda name, d=0: k.get(name) if k.get(name) is not None else d  # noqa: E731
    healthy, hungry, sick = int(g("healthy")), int(g("hungry")), int(g("sick"))
    size = healthy + hungry + sick
    day, status = int(g("day")), int(g("status"))
    meta = _json(g("meta", ""), {})
    last = _json(g("last_result", ""), {})
    alive = status == clan.ALIVE
    out = {"ok": True, "hasClan": status != 0, "faction": int(g("faction")), "factionName": clan.FACTION_NAMES.get(int(g("faction")), ""),
           "status": STATUS.get(status, "none"), "daysDone": day, "daysTotal": clan.WIN_DAY, "weeksTotal": int(g("weeks_total")),
           "size": size, "healthy": healthy, "hungry": hungry, "sick": sick, "needed": clan.needed(size), "maxSize": max(int(meta.get("max", 0)), size),
           "runsWon": int(g("runs_won")), "runsLost": int(g("runs_lost"))}
    if alive:
        wk, dw = clan.week_day(day)
        out.update(week=wk, dayOfWeek=dw, weeks=clan.WEEKS)
        s = clan.event_window(day)
        ev = None
        if s >= 0:
            kind, _tab = clan.EVENT_DAYS[s]
            ev = {"kind": kind, "name": "ATTACK" if kind == "attack" else clan.GROWTH_NAMES[(s // 5) % len(clan.GROWTH_NAMES)],
                  "startDay": s, "dayOfEvent": day - s + 1, "length": clan.EVENT_LEN}
        out["event"] = ev
        ek, en = clan.event_today(day)
        out["eventToday"] = ({"kind": "attack" if ek == clan.EV_ATTACK else "growth", "name": "ATTACK" if ek == clan.EV_ATTACK else clan.GROWTH_NAMES[en]}
                             if ek else None)
        m = meta.get("m")
        if m and int(m.get("id", 0)) in clan.MISSIONS:
            mid = int(m["id"])
            out["mission"] = {"id": mid, "name": clan.MISSIONS[mid][0], "progress": int(m.get("prog", 0)), "daysLeft": int(m.get("left", 0)),
                              "goals": list(clan.mission_goals(mid, meta.get("rep", {}).get(str(mid), 0))), "inEvent": int(m.get("ev", -1)) >= 0}
        else:
            out["mission"] = None
        out["boosterNext"] = clan.booster_next({"healthy": healthy, "hungry": hungry, "sick": sick, "boost_hi": int(g("boost_hi", 0))})
    out["boosters"] = [{"id": b, "name": n, "count": boosters.get(b, 0)} for b, n in sorted(clan.BOOSTERS.items())]
    if last:
        out["lastMatch"] = {"day": last.get("day", -1), "parts": last.get("parts", 0), "supplies": last.get("supplies", 0), "needed": last.get("needed", 0),
                            "gained": last.get("gained", 0), "died": last.get("died", 0), "newHungry": last.get("new_hungry", 0),
                            "newSick": last.get("new_sick", 0), "healed": last.get("healed", 0), "leftEarly": bool(last.get("left", 0))}
        sup = last.get("sup")
        if isinstance(sup, dict) and sup.get("need"):             # supplies per category (tools/clan_supply.py); absent in an old result: the launcher models it
            out["supplies"] = {"cats": list(clan_supply.CATS), "got": sup.get("got", {}), "need": sup.get("need", {}), "short": sup.get("short", {}),
                               "drawn": sup.get("drawn", {}), "net": sup.get("net", {}), "stock": sup.get("stock", {}), "days": sup.get("days", {}),
                               "cause": sup.get("cause", "")}
        if last.get("mi"):
            mi = int(last["mi"])
            out["lastMission"] = {"id": mi, "name": clan.MISSIONS.get(mi, ("?",))[0], "progress": last.get("mp", 0), "tier": last.get("mt", 0),
                                  "boostersEarned": len(last.get("boosters", []))}
    return out
