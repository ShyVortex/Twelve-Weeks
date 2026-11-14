"""Hermetic tests: admin clan reset / restore (tools/clan_reset.py), the admin site's forwarding (store.clan_reset) and the multi-PT-folder log reading
(logindex.prior_daemon_logs).  Run: python tools/tests/test_clan_reset.py   (temp dirs / temp DB only, no sockets, never the live data)."""
import json
import os
import shutil
import sqlite3
import sys
import tempfile
import time
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.join(HERE, "..")
sys.path.insert(0, TOOLS)
sys.path.insert(0, os.path.join(TOOLS, "admin_site"))
import clan  # noqa: E402
import clan_reset as CR  # noqa: E402
import logindex  # noqa: E402

SID = 76561198000000001
TOK = "ab" * 32
TID = clan.token_id(TOK)
OTHER = "s:76561198000000002"


def make(path):
    c = sqlite3.connect(path)
    c.execute("CREATE TABLE players(token TEXT PRIMARY KEY, name TEXT, loadout BLOB, kills INT DEFAULT 0, deaths INT DEFAULT 0, wins INT DEFAULT 0, matches INT DEFAULT 0, "
              "steamid INTEGER DEFAULT 0, last_seen REAL, parts_total INTEGER DEFAULT 0, parts_n INTEGER DEFAULT 0, draws INTEGER DEFAULT 0)")
    c.execute("INSERT INTO players(token,name,steamid,matches,last_seen) VALUES(?,?,?,?,?)", (TOK, "Tester", SID, 9, time.time()))
    clan.ensure(c)
    for k in ("s:%d" % SID, TID, OTHER):
        c.execute("INSERT INTO clans(token_id,faction,status,day,healthy,weeks_total,created,updated) VALUES(?,1,1,20,6,2,1,1)", (k,))
        c.execute("INSERT INTO boosters VALUES(?,1,3)", (k,))
        c.execute("CREATE TABLE IF NOT EXISTS clan_story(token_id TEXT PRIMARY KEY, state TEXT, updated REAL)")
        c.execute("INSERT INTO clan_story VALUES(?,'{}',1)", (k,))
        c.execute("CREATE TABLE IF NOT EXISTS clan_feed(token_id TEXT, id INTEGER, ts REAL, day INTEGER, week INTEGER, kind TEXT, mood TEXT, faction INTEGER, text TEXT, names TEXT, lid TEXT, params TEXT)")
        c.execute("INSERT INTO clan_feed(token_id,id,text) VALUES(?,1,'hello')", (k,))
        c.execute("CREATE TABLE IF NOT EXISTS clan_alife(token_id TEXT PRIMARY KEY, state TEXT, updated REAL)")
        c.execute("INSERT INTO clan_alife VALUES(?,'{}',1)", (k,))
    c.execute("CREATE TABLE names(token_id TEXT PRIMARY KEY, name TEXT, tag TEXT, updated REAL)")
    c.execute("INSERT INTO names VALUES(?,?,?,0)", ("s:%d" % SID, "Wolves", "WLF"))
    c.commit()
    return c


def count(c, tab, key):
    return c.execute("SELECT COUNT(*) FROM %s WHERE token_id=?" % tab, (key,)).fetchone()[0]


class Reset(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="t2r-tmp-clanreset-")
        self.c = make(os.path.join(self.tmp, "t.db"))
        self.bk = os.path.join(self.tmp, "clan-resets")

    def tearDown(self):
        self.c.close()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_wipes_every_key_of_the_person_only(self):
        r = CR.reset(self.c, self.bk, "Tester", SID, [TID])
        self.assertTrue(r["ok"])
        self.assertTrue(r["had_clan"])
        for tab in ("clans", "boosters", "clan_story", "clan_feed", "clan_alife"):
            for k in ("s:%d" % SID, TID):
                self.assertEqual(count(self.c, tab, k), 0, (tab, k))
            self.assertEqual(count(self.c, tab, OTHER), 1, tab)             # another player is untouched
        self.assertEqual(count(self.c, "names", "s:%d" % SID), 1)           # the clan name / tag stays by default
        st = clan.load(self.c, "s:%d" % SID)
        self.assertEqual(st["status"], 0)                                   # reads as a brand-new player: no clan
        self.assertEqual(clan.state_text(st).split()[1], "fac=0")

    def test_old_install_clan_is_not_readopted(self):
        # daemon.clan_key adopts the furthest-along old install when the Steam key has no row: the install key must be gone too
        CR.reset(self.c, self.bk, "Tester", SID, [TID])
        left = self.c.execute("SELECT token_id FROM clans WHERE token_id IN (?,?)", ("s:%d" % SID, TID)).fetchall()
        self.assertEqual(left, [])

    def test_names_option(self):
        CR.reset(self.c, self.bk, "Tester", SID, [TID], names=True)
        self.assertEqual(count(self.c, "names", "s:%d" % SID), 0)

    def test_backup_audit_and_restore(self):
        r = CR.reset(self.c, self.bk, "Tes/ter ..", SID, [TID])
        self.assertTrue(os.path.isfile(os.path.join(self.bk, r["backup"])))
        self.assertNotIn("/", r["backup"])
        self.assertIn("RESET", open(os.path.join(self.bk, "audit.log"), encoding="utf-8").read())
        lst = CR.list_backups(self.bk, SID)
        self.assertEqual(len(lst), 1)
        self.assertEqual(lst[0]["rows"]["clans"], 2)
        self.c.execute("INSERT INTO clans(token_id,faction,status,day) VALUES(?,2,1,1)", ("s:%d" % SID,))   # the player started over meanwhile
        out = CR.restore(self.c, self.bk, r["backup"])
        self.assertTrue(out["ok"])
        st = clan.load(self.c, "s:%d" % SID)
        self.assertEqual((st["faction"], st["day"], st["weeks_total"]), (1, 20, 2))
        self.assertEqual(count(self.c, "clan_feed", TID), 1)
        self.assertEqual(len(CR.list_backups(self.bk)), 2)                  # the pre-restore state was saved as well (undoable)

    def test_bad_inputs(self):
        self.assertFalse(CR.reset(self.c, self.bk, "x", 0, ["nothex", "../x"])["ok"])
        self.assertFalse(CR.restore(self.c, self.bk, "../../etc/passwd")["ok"])
        self.assertFalse(CR.restore(self.c, self.bk, "missing.json")["ok"])
        self.assertEqual(count(self.c, "clans", OTHER), 1)

    def test_player_without_clan(self):
        self.c.execute("DELETE FROM clans WHERE token_id=?", ("s:%d" % SID,))
        self.c.execute("DELETE FROM clans WHERE token_id=?", (TID,))
        r = CR.reset(self.c, self.bk, "Tester", SID, [TID])
        self.assertTrue(r["ok"])
        self.assertFalse(r["had_clan"])


class AdminForward(unittest.TestCase):
    def test_store_requires_typed_name_and_forwards(self):
        import store
        tmp = tempfile.mkdtemp(prefix="t2r-tmp-clanreset2-")
        try:
            make(os.path.join(tmp, "t.db")).close()
            a = store.Admin(os.path.join(tmp, "t.db"))
            calls = []
            a.admin_call = lambda path, data=None, timeout=1.5: (calls.append((path, data)) or {"ok": True, "backup": "b.json"})
            pid = next(iter(a.player_groups()))
            self.assertFalse(a.clan_reset(pid, "wrong")["ok"])
            self.assertEqual(calls, [])                                    # nothing reaches the daemon without the typed name
            r = a.clan_reset(pid, " [wlf] wolves ")
            self.assertTrue(r["ok"])
            path, data = calls[0]
            self.assertEqual(path, "/clan/reset")
            self.assertEqual(data["steamid"], SID)
            self.assertIn(TID, data["tokenIds"])
            self.assertNotIn(TOK, json.dumps(data))                        # the secret token never travels
            self.assertFalse(a.clan_reset("nosuch", "x")["ok"])
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


class PriorLogs(unittest.TestCase):
    def test_older_pt_folders_are_read(self):
        tmp = tempfile.mkdtemp(prefix="t2r-tmp-priorlogs-")
        try:
            hdr = "# daemon %s\n" % time.strftime("%a %b %d %H:%M:%S %Y")
            for i, pt in enumerate(("playtest84", "playtest85")):
                d = os.path.join(tmp, pt, "host")
                os.makedirs(d)
                p = os.path.join(d, "daemon.log")
                with open(p, "w") as f:
                    f.write(hdr + "[01:00:0%d] EVT match-formed m%d players ['A', 'B'] host A net x ping-ms {}\n" % (i, i))
                os.utime(p, (time.time() - 100 + i * 50,) * 2)
            li = logindex.LogIndex("auto:" + tmp)
            li.refresh(0)
            self.assertTrue(li.path.endswith(os.path.join("playtest85", "host", "daemon.log")))
            ids = [e["body"].split()[0] for e in li.events if e["kind"] == "match-formed"]
            self.assertEqual(ids, ["m0", "m1"])                            # the older build's match is still in the history
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
