"""Ban check for the launcher (GET /ban-check), read-only: bans.txt next to the daemon's t2r.db + that db's hwids / players tables.

The launcher sends the three hardware hashes it computes the way the game does (tools/ext/hwid.c) and the Steam id(s) it knows; this
answers {"banned": bool, "reason": str}. The rules mirror tools/daemon.py (is_banned / banned_hwid_sets), re-implemented here on purpose
(the daemon is never imported):
  - bans.txt entry = Steam id (15+ digits) | player name (also bans every Steam account that ever used it) | hwid:<24+ hex> | token:<64 hex>
  - '#' starts a comment; "reason: text" inside a comment is the reason shown to the player (other comments are private notes, never sent)
  - a sent Steam id that is banned, or a name-banned account            -> banned
  - a sent hash equal to an explicit hwid: entry (placeholders removed)  -> banned
  - a sent hash (+ the hashes the db knows for the sent Steam ids) that matches >= HWID_MIN_MATCH hashes ever seen with a banned
    account                                                              -> banned
Only an explicit answer bans: any error in the db part is "not banned" (explicit entries still count); the launcher also never bans on
a network failure.
"""
import hashlib
import os
import re
import sqlite3

HWID_HEX = 24
HWID_MIN_MATCH = 2
MAX_HASHES = 8
MAX_IDS = 4
_HEX = re.compile(r"^[0-9a-f]+$")
_REASON = re.compile(r"reason\s*:\s*(.*)$", re.I)


def _placeholders():
    """Same list as daemon.py _hw_placeholders (component hashes of well-known fake serials / UUIDs)."""
    def h(tag, data):
        return hashlib.sha256(b"T2R-HWID1" + bytes([tag]) + data).digest()[:12].hex()
    out = set()
    for s in ("", "To Be Filled By O.E.M.", "To be filled by O.E.M.", "Default string", "Default String", "None", "none", "Unknown", "unknown",
              "N/A", "NA", "Not Specified", "Not Applicable", "System Serial Number", "SerialNumber", "Serial Number", "123456789", "1234567890",
              "0123456789", "00000000", "0000000000", "0", "000000000000", "0000_0000_0000_0000", "0000_0000_0000_0000.", "XXXXXXXX",
              "xxxxxxxx", "INVALID", "Invalid", "OEM", "O.E.M.", "ChangeMe", "default", "Default", "VMware Virtual disk", "QEMU HARDDISK"):
        out.add(h(3, s.encode()))
    for n in (8, 16, 20, 32, 40):
        out.add(h(3, b"0" * n)); out.add(h(3, b"F" * n)); out.add(h(3, b"f" * n)); out.add(h(3, b" " * n))
    for u in (bytes(16), b"\xff" * 16, bytes.fromhex("00020003000400050006000700080009"), bytes.fromhex("03000200040005000006000700080009"),
              bytes.fromhex("11111111111111111111111111111111"), bytes.fromhex("0123456789abcdef0123456789abcdef"),
              bytes.fromhex("fedcba9876543210fedcba9876543210")):
        out.add(h(2, u))
    return out


PLACEHOLDERS = _placeholders()


def parse_bans(path):
    """{"ids": {steamid: reason}, "names": {lower name: reason}, "hw": {hash: reason}, "tok": {token: reason}}; missing file = empty."""
    out = {"ids": {}, "names": {}, "hw": {}, "tok": {}}
    try:
        lines = open(path, encoding="utf-8", errors="ignore").read().splitlines()
    except OSError:
        return out
    for line in lines:
        body, _, comment = line.partition("#")
        e = body.strip()
        if not e:
            continue
        m = _REASON.search(comment.strip())
        reason = m.group(1).strip()[:200] if m else ""
        low = e.lower()
        if low.startswith("token:"):
            t = low[6:].strip()
            if len(t) == 64 and _HEX.match(t):
                out["tok"][t] = reason
        elif low.startswith("hwid:"):
            h = low[5:].strip()
            if len(h) >= HWID_HEX and _HEX.match(h):
                out["hw"][h[:HWID_HEX]] = reason
        elif e.isdigit() and len(e) >= 15:
            out["ids"][e] = reason
        else:
            out["names"][low] = reason
    return out


def clean_hashes(values):
    out = []
    for v in values[:MAX_HASHES]:
        v = v.strip().lower()
        if len(v) == HWID_HEX and _HEX.match(v) and v not in out:
            out.append(v)
    return out


def clean_ids(values):
    out = []
    for v in values[:MAX_IDS]:
        v = v.strip()
        if v.isdigit() and 15 <= len(v) <= 20 and v not in out:
            out.append(v)
    return out


def _connect(db_path):
    uri = "file:" + db_path.replace("\\", "/") + "?mode=ro"
    return sqlite3.connect(uri, uri=True, timeout=2)


def check(db_path, ban_path, hashes, steamids, tokens=()):
    """-> {"banned": bool, "reason": str}. hashes: 24-hex strings, steamids: digit strings, tokens: 64-hex strings (all already cleaned)."""
    bans = parse_bans(ban_path)
    if not any(bans.values()):
        return {"banned": False, "reason": ""}
    for t in tokens:
        if t in bans["tok"]:
            return {"banned": True, "reason": bans["tok"][t]}
    for s in steamids:
        if s in bans["ids"]:
            return {"banned": True, "reason": bans["ids"][s]}
    mine = set(hashes) - PLACEHOLDERS
    for h in mine:
        if h in bans["hw"]:
            return {"banned": True, "reason": bans["hw"][h]}
    if not db_path or not (bans["ids"] or bans["names"]):
        return {"banned": False, "reason": ""}
    try:
        c = _connect(db_path)
    except sqlite3.Error:
        return {"banned": False, "reason": ""}
    try:
        banned_ids = dict(bans["ids"])                   # steamid -> reason; name entries add every account that used the name
        for n, why in bans["names"].items():
            for (sid,) in c.execute("SELECT steamid FROM players WHERE lower(name)=? AND steamid", (n,)):
                banned_ids.setdefault(str(sid), why)
        for s in steamids:
            if s in banned_ids:
                return {"banned": True, "reason": banned_ids[s]}
        derived = {}                                     # hardware hash seen with a banned account -> that ban's reason
        toks = {}
        for sid, why in banned_ids.items():
            for (t,) in c.execute("SELECT token FROM players WHERE steamid=?", (int(sid),)):
                toks.setdefault(t, why)
            for (h,) in c.execute("SELECT hash FROM hwids WHERE steamid=?", (int(sid),)):
                derived.setdefault(h, why)
        for n, why in bans["names"].items():
            for (t,) in c.execute("SELECT token FROM hwids WHERE lower(name)=?", (n,)):
                toks.setdefault(t, why)
        for t, why in toks.items():
            for (h,) in c.execute("SELECT hash FROM hwids WHERE token=?", (t,)):
                derived.setdefault(h, why)
        for s in steamids:                               # what the db already knows about the sent Steam accounts (the daemon does the same)
            mine |= {r[0] for r in c.execute("SELECT hash FROM hwids WHERE steamid=?", (int(s),))}
        mine -= PLACEHOLDERS
        for h in mine:
            if h in bans["hw"]:
                return {"banned": True, "reason": bans["hw"][h]}
        hits = [h for h in mine if h in derived and h not in PLACEHOLDERS and h not in bans["hw"]]
        if len(hits) >= HWID_MIN_MATCH:
            return {"banned": True, "reason": derived[hits[0]]}
    except (sqlite3.Error, ValueError):
        pass
    finally:
        c.close()
    return {"banned": False, "reason": ""}


def route(db_path, query):
    """query = parse_qs dict -> response dict. ?h=<hash,hash,...>&s=<steamid,...>&t=<token,...>"""
    def vals(k):
        return [x for v in query.get(k, []) for x in v.split(",") if x][:16]
    tokens = [t.lower() for t in vals("t")[:2] if len(t) == 64 and _HEX.match(t.lower())]
    return check(db_path, os.path.join(os.path.dirname(os.path.abspath(db_path)), "bans.txt") if db_path else "",
                 clean_hashes(vals("h")), clean_ids(vals("s")), tokens)
