"""Admin clan reset: wipe one player's clan to a fresh start with an automatic
backup, and undo it again.  Called by the daemon's loopback admin listener (POST /clan/reset, /clan/restore, GET /clan/backups); the admin site only forwards.

What "the clan" is in the database: the progress row (clans: faction, status, day, survivors, weeks, runs, missions/meta), the one-use boosters, the
survivor roster + diary state (clan_story), the diary (clan_feed) and the A-Life simulation (clan_alife).  They are keyed by the clan key "s:<steamid>"
AND by the per-install token ids (clan.token_id) of the same person: clan_key() ADOPTS the furthest-along old install's clan when the Steam key has no
row, so wiping only the Steam key would bring the old clan straight back.  All keys of the person are cleared.
The chosen clan NAME / TAG (names table) is kept unless names=True.

The client holds no clan state of its own (the ext keeps the last 0xE1 reply in memory and replaces it with every poll; the launcher asks the
daemon / update server each time), so after the wipe the next poll reads "no clan" -> CHOOSE YOUR SIDE, exactly like a new player.
Pure logic on an open sqlite connection; tests: tools/tests/test_clan_reset.py."""
import json
import os
import re
import time

TABLES = (("clans", "token_id"), ("boosters", "token_id"), ("clan_story", "token_id"), ("clan_feed", "token_id"), ("clan_alife", "token_id"))
NAMES_TABLE = ("names", "token_id")
HEX24 = re.compile(r"^[0-9a-f]{24}$")


def keys_for(steamid, token_ids=()):
    """Every clan key of one person: 's:<steamid>' plus the (24 hex) install ids. Anything malformed is ignored."""
    ks = []
    try:
        sid = int(steamid or 0)
    except (TypeError, ValueError):
        sid = 0
    if sid > 0:
        ks.append("s:%d" % sid)
    for t in token_ids or ():
        t = str(t).lower()
        if HEX24.match(t) and t not in ks:
            ks.append(t)
    return ks


def _tables(c):
    return {r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'")}


def snapshot(c, keys, names=False):
    """{table: [row dicts]} for the keys (only tables that exist)."""
    have = _tables(c)
    out = {}
    for tab, col in TABLES + ((NAMES_TABLE,) if names else ()):
        if tab not in have or not keys:
            continue
        cur = c.execute("SELECT * FROM %s WHERE %s IN (%s)" % (tab, col, ",".join("?" * len(keys))), list(keys))
        cols = [d[0] for d in cur.description]
        rows = [dict(zip(cols, r)) for r in cur.fetchall()]
        if rows:
            out[tab] = rows
    return out


def _safe(name):
    return re.sub(r"[^A-Za-z0-9._-]+", "_", name or "player")[:40] or "player"


def write_backup(backup_dir, name, steamid, keys, snap, reason="admin reset", now=None):
    now = time.time() if now is None else now
    os.makedirs(backup_dir, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S", time.localtime(now))
    base = "%s-%s-%s" % (stamp, _safe(name), _safe(str(steamid or "nosteam")))
    path = os.path.join(backup_dir, base + ".json")
    n = 1
    while os.path.exists(path):
        n += 1
        path = os.path.join(backup_dir, "%s-%d.json" % (base, n))
    doc = {"v": 1, "ts": now, "reason": reason, "name": name, "steamid": int(steamid or 0), "keys": keys, "tables": snap}
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(doc, f, ensure_ascii=False, separators=(",", ":"))
    os.replace(tmp, path)
    return path


def audit(backup_dir, line, now=None):
    now = time.time() if now is None else now
    os.makedirs(backup_dir, exist_ok=True)
    with open(os.path.join(backup_dir, "audit.log"), "a", encoding="utf-8") as f:
        f.write("%s %s\n" % (time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(now)), line.replace("\n", " ")))


def reset(c, backup_dir, name, steamid, token_ids=(), names=False, now=None):
    """Back up and wipe. Returns {"ok", "backup", "keys", "rows": {table: n}, "had_clan"}; the caller commits (daemon: inside `with dbc()`)."""
    keys = keys_for(steamid, token_ids)
    if not keys:
        return {"ok": False, "error": "no clan key for this player"}
    snap = snapshot(c, keys, names)
    had = bool(snap.get("clans"))
    path = write_backup(backup_dir, name, steamid, keys, snap, "admin reset", now)
    have = _tables(c)
    for tab, col in TABLES + ((NAMES_TABLE,) if names else ()):
        if tab in have:
            c.execute("DELETE FROM %s WHERE %s IN (%s)" % (tab, col, ",".join("?" * len(keys))), keys)
    rows = {t: len(r) for t, r in snap.items()}
    audit(backup_dir, "RESET %s steam=%s keys=%d rows=%s names=%s backup=%s" % (name, steamid, len(keys), rows, bool(names), os.path.basename(path)), now)
    return {"ok": True, "backup": os.path.basename(path), "keys": keys, "rows": rows, "had_clan": had}


def list_backups(backup_dir, steamid=None):
    out = []
    try:
        fs = sorted(f for f in os.listdir(backup_dir) if f.endswith(".json"))
    except OSError:
        return out
    for fn in fs:
        try:
            with open(os.path.join(backup_dir, fn), encoding="utf-8") as f:
                d = json.load(f)
        except (OSError, ValueError):
            continue
        if steamid and int(d.get("steamid") or 0) != int(steamid):
            continue
        out.append({"file": fn, "ts": d.get("ts"), "name": d.get("name"), "steamid": d.get("steamid"), "reason": d.get("reason"),
                    "rows": {t: len(r) for t, r in (d.get("tables") or {}).items()}})
    return out


def restore(c, backup_dir, fname, now=None):
    """Put a backup back (what is there now is backed up first, so a restore is undoable too). Returns {"ok", ...}."""
    if not re.match(r"^[A-Za-z0-9._-]+\.json$", fname or "") or fname.startswith("."):
        return {"ok": False, "error": "bad backup name"}
    try:
        with open(os.path.join(backup_dir, fname), encoding="utf-8") as f:
            d = json.load(f)
    except (OSError, ValueError):
        return {"ok": False, "error": "backup not found"}
    keys = [k for k in d.get("keys", []) if isinstance(k, str)]
    cur = snapshot(c, keys, names="names" in (d.get("tables") or {}))
    pre = write_backup(backup_dir, d.get("name"), d.get("steamid"), keys, cur, "before restore of " + fname, now)
    have = _tables(c)
    n = 0
    for tab, rows in (d.get("tables") or {}).items():
        if tab not in have or tab not in {t for t, _ in TABLES + (NAMES_TABLE,)}:
            continue
        col = dict(TABLES + (NAMES_TABLE,))[tab]
        c.execute("DELETE FROM %s WHERE %s IN (%s)" % (tab, col, ",".join("?" * len(keys))), keys)
        for r in rows:
            cols = [k for k in r if re.match(r"^[a-z_]+$", k)]
            c.execute("INSERT OR REPLACE INTO %s(%s) VALUES(%s)" % (tab, ",".join(cols), ",".join("?" * len(cols))), [r[k] for k in cols])
            n += 1
    audit(backup_dir, "RESTORE %s steam=%s from=%s rows=%d (previous state saved as %s)" % (d.get("name"), d.get("steamid"), fname, n, os.path.basename(pre)), now)
    return {"ok": True, "restored": n, "name": d.get("name"), "before": os.path.basename(pre)}
