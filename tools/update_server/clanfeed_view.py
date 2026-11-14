"""Read-only clan feed for the launcher's CAMP journal and corner toasts: GET /clanfeed.json?player=<install id>[&limit=30][&since=<id>][&lang=pl].

Same rules as clan_view.py: the daemon's t2r.db is opened with mode=ro (never written, never migrated), `player` = the 12-byte install id
(24 hex chars; the last 24 chars of the 64-hex name token also work). The feed itself is written by the daemon (tools/clan_story.py);
a database without the clan_feed / clan_story tables simply gives an empty feed.
"""
import os
import sqlite3
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import clan  # noqa: E402
import clan_story  # noqa: E402
from clan_view import ID_RE, STATUS, resolve_key  # noqa: E402


def view(db_path, player, limit=30, since=0, lang="en", now=None, key=None):
    """`key` (admin site): the clans-table key itself, used as is (no id check, no steam resolve)."""
    if key is None and not ID_RE.match(player or ""):
        return {"ok": False, "error": "bad player id"}
    tid = key if key is not None else clan.token_id(player)
    try:
        limit = max(1, min(int(limit), clan_story.feed_max()))
        since = max(0, int(since))
    except (TypeError, ValueError):
        return {"ok": False, "error": "bad limit / since"}
    try:
        c = sqlite3.connect("file:%s?mode=ro" % os.path.abspath(db_path).replace("\\", "/"), uri=True, timeout=2)
    except sqlite3.Error as e:
        return {"ok": False, "error": "database unavailable: %s" % e}
    try:
        if key is None:
            tid = resolve_key(c, tid)                            # the key the daemon uses (s:<steamid> when linked): game and launcher read the same clan
        try:
            row = c.execute("SELECT faction, status, day FROM clans WHERE token_id=?", (tid,)).fetchone()
        except sqlite3.Error:
            row = None
        feed = clan_story.read_feed(c, tid, limit, since, lang, callbacks=True, fold=True)
        for m in feed:
            m["short"] = clan_story.widget_text(m["text"])      # the one-line form (toasts, in-game widget)
        camp = clan_story.read_people(c, tid, lang=lang) if row else {}
        try:                                                     # the simulated life (tools/clan_alife.py, switch off by default): what is happening in camp now
            import clan_alife                                     # noqa: PLC0415
            alife = clan_alife.public(c, tid, lang) if row else {}
        except Exception:                                         # noqa: BLE001 - optional
            alife = {}
        try:                                                     # the chronicle (tools/clan_chronicle.py): roster taglines + portraits, match summaries with loot
            import clan_chronicle                                 # noqa: PLC0415
            chron = clan_chronicle.public(c, tid, lang) if row else {}
        except Exception:                                         # noqa: BLE001 - optional
            chron = {}
        # the SAME reply the game's menu widget gets (daemon op 0xB4): clan_story.menu_lines is a pure function of (clan, time slot, language), so the
        # launcher's toasts (main.js uses "menu" when the daemon is not reachable) carry the game's ids and texts. Read-only: save=False.
        menu = clan_story.menu_lines(c, tid, 6, lang, now, save=False) if row and row[1] else []
    finally:
        c.close()
    if not row or not row[1]:
        return {"ok": True, "hasClan": False, "feed": []}
    out = {"ok": True, "hasClan": True, "lang": clan_story.PLN.norm_lang(lang), "faction": int(row[0]), "factionName": clan.FACTION_NAMES.get(int(row[0]), ""),
           "status": STATUS.get(int(row[1]), "none"), "daysDone": int(row[2]), "feed": feed,
           "menu": [{"id": str(i), "text": t} for i, t in menu], "slot": clan_story.slot_of(now)}
    out.update(camp)
    if alife:
        out["alife"] = alife
    if chron and (chron.get("matches") or (key is not None and chron.get("roster"))):      # the admin site shows a roster even before the first raid is logged
        out["chron"] = chron
    return out
