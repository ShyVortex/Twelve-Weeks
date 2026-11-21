"""Player roles for the rank badge colour and the lead developer's nametag.

Role codes (sent as the 4th field of every rank table entry, tools/rankbadge.py wire(); t2r-ext rankbadge.c):
    0 none, 1 OG, 2 admin, 3 dev, 4 lead dev.
A player with several roles gets the highest code (lead > dev > admin > OG).

Sources, all Steam64 ids, one per line, '#' starts a comment, re-read when the file changes (no restart):
    <data dir>/og-steamids.txt   OG: every Steam id that played before the public release, frozen from the players table by
                                 `python tools/roles.py freeze-og <db>` on release day.
    <data dir>/web-admins.txt    admin: the website / admin panel list. A line whose comment contains TEMP (a temporary admin) gets no role.
    <data dir>/devs.txt          dev: '<steamid> [lead] # name'; the word 'lead' after the id marks the lead developer.
<data dir> = the folder of the daemon's DB (T2R_DB), the same place web.py and the admin site read web-admins.txt from.
"""
import os
import sqlite3
import sys

NONE, OG, ADMIN, DEV, LEAD = 0, 1, 2, 3, 4
FILES = {"og": "og-steamids.txt", "admin": "web-admins.txt", "dev": "devs.txt"}


def parse_ids(text, skip_temp=False):
    """{steamid: [words after the id]} from a list file; bad lines are ignored."""
    out = {}
    for line in (text or "").splitlines():
        body, _, comment = line.partition("#")
        words = body.split()
        if not words or not words[0].isdigit():
            continue
        if skip_temp and "TEMP" in comment:
            continue
        sid = int(words[0])
        if sid > 0:
            out[sid] = [w.lower() for w in words[1:]]
    return out


class Roles:
    def __init__(self, data_dir):
        self.data_dir = data_dir
        self._stamp = {}
        self._lists = {"og": {}, "admin": {}, "dev": {}}

    def _refresh(self):
        for k, fn in FILES.items():
            p = os.path.join(self.data_dir, fn)
            try:
                st = os.stat(p)
                stamp = (st.st_mtime_ns, st.st_size)
            except OSError:
                stamp = None
            if self._stamp.get(k, "?") == stamp:
                continue
            self._stamp[k] = stamp
            text = ""
            if stamp is not None:
                try:
                    with open(p, encoding="utf-8", errors="ignore") as f:
                        text = f.read()
                except OSError:
                    text = ""
            self._lists[k] = parse_ids(text, skip_temp=(k == "admin"))

    def role_of(self, steamid):
        """Role code of a Steam64 id (0 for none / unknown / 0)."""
        try:
            sid = int(steamid or 0)
        except (TypeError, ValueError):
            return NONE
        if sid <= 0:
            return NONE
        self._refresh()
        dev = self._lists["dev"].get(sid)
        if dev is not None:
            return LEAD if "lead" in dev else DEV
        if sid in self._lists["admin"]:
            return ADMIN
        if sid in self._lists["og"]:
            return OG
        return NONE


def freeze_og(db_path, out_path, before=None):
    """Write every Steam id in the players table (optionally only last_seen < before, a unix time) to out_path. Returns the count."""
    c = sqlite3.connect("file:%s?mode=ro" % db_path, uri=True)
    try:
        q = "SELECT DISTINCT steamid FROM players WHERE steamid > 0"
        args = ()
        if before is not None:
            q += " AND last_seen < ?"
            args = (float(before),)
        ids = sorted(r[0] for r in c.execute(q, args).fetchall())
    finally:
        c.close()
    tmp = out_path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write("# OG: every Steam id that played before the public release (tools/roles.py freeze-og)\n")
        for sid in ids:
            f.write("%d\n" % sid)
    os.replace(tmp, out_path)
    return len(ids)


if __name__ == "__main__":
    if len(sys.argv) >= 3 and sys.argv[1] == "freeze-og":
        db = sys.argv[2]
        out = sys.argv[3] if len(sys.argv) > 3 else os.path.join(os.path.dirname(os.path.abspath(db)), FILES["og"])
        print("OG ids written:", freeze_og(db, out), "->", out)
    else:
        print("usage: roles.py freeze-og <t2r.db> [out file]")
