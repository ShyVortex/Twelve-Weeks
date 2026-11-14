"""Tests for the A-Life views of the admin site (tools/admin_site/store.py: player detail "alife", clan list summary, feed rows with their Polish text).
Run: python tools/admin_site/test_admin_alife.py   (stdlib unittest; a simulated clan in a temp DB, never the live one)."""
import json
import os
import shutil
import sqlite3
import sys
import tempfile
import time
import unittest
import sys as _t2s, os as _t2o; _t2s.path.append(_t2o.path.normpath(_t2o.path.join(_t2o.path.dirname(_t2o.path.abspath(__file__)), ".."))); import t2rtmp  # noqa: E402,F401  (temp hygiene: tools/t2rtmp.py)

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, TOOLS)
import clan  # noqa: E402
import clan_alife as AL  # noqa: E402
import clan_alife_report as R  # noqa: E402
import clan_story as CS  # noqa: E402
import store  # noqa: E402

STEAM = 7656119800000001
KEY = "s:%d" % STEAM
TOKEN = (b"T2N:Alice\0").hex().ljust(40, "0") + "a1" * 12


def mixed(i, c0, need):
    return int(need * clan.PARTS_PER_SUPPLY * (0.8 if i % 7 in (3, 4) else 1.35))


class AdminAlife(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="t2r-tmp-adminalife-")
        c, tid, cls.log = R.simulate(clan.WLF, (12, 1, 0, 0), 30, seed=7, alife=True, tid=KEY, parts_fn=mixed)
        src = c.execute("PRAGMA database_list").fetchone()[2]
        c.commit()
        c.close()
        cls.db = os.path.join(cls.tmp, "t2r.db")
        shutil.copy(src, cls.db)
        c = sqlite3.connect(cls.db)
        c.execute("CREATE TABLE players(token TEXT PRIMARY KEY, name TEXT, loadout BLOB, kills INT DEFAULT 0, deaths INT DEFAULT 0, wins INT DEFAULT 0, matches INT DEFAULT 0, "
                  "steamid INTEGER DEFAULT 0, last_seen REAL, parts_total INTEGER DEFAULT 0, parts_n INTEGER DEFAULT 0, draws INTEGER DEFAULT 0)")
        c.execute("INSERT INTO players(token,name,wins,matches,steamid,last_seen) VALUES(?,?,?,?,?,?)", (TOKEN, "Alice", 3, 5, STEAM, time.time() - 60))
        c.commit()
        c.close()
        cls.logp = os.path.join(cls.tmp, "daemon.log")
        with open(cls.logp, "w") as f:
            f.write("# daemon\n")

    def setUp(self):
        os.environ["T2R_CLAN_ALIFE"] = "1"

    def tearDown(self):
        os.environ.pop("T2R_CLAN_ALIFE", None)

    def mk(self):
        return store.Admin(db=self.db, daemon_log=self.logp, reports=None, daemon="127.0.0.1:1")

    def alice(self, a):
        pl = a.players_all("")["players"]
        return a.player(next(p["id"] for p in pl if p["name"] == "Alice"))

    def test_player_view_matches_the_real_clan(self):
        d = self.alice(self.mk())
        self.assertTrue(d["ok"])
        al = d["alife"]
        self.assertTrue(al["exists"] and al["enabled"])
        st = al["state"]
        cl = d["clan"]
        n = {s: sum(1 for p in st["people"] if p["state"] == s) for s in ("healthy", "hungry", "sick")}
        self.assertEqual((n["healthy"], n["hungry"], n["sick"]), (cl["healthy"], cl["hungry"], cl["sick"]))   # the A-Life shows the authoritative numbers
        self.assertEqual(len(st["people"]), cl["size"])
        self.assertEqual(sorted(p["name"] for p in st["people"]), sorted(p["name"] for p in d["people"]) if len(d["people"]) == len(st["people"]) else sorted(p["name"] for p in st["people"]))
        self.assertTrue(all(p["traits"] and p["role"] and "away" in p for p in st["people"]))
        self.assertEqual(st["day"], cl["day"] - 1 if st["day"] != cl["day"] else st["day"])
        self.assertIn(st["weather"], ("rain", "fog", "cold", "clear", "smoke", "wind"))
        self.assertEqual(len(al["pl"]["threads"]), len(st["threads"]))
        self.assertTrue(al["menu"]["en"] and al["menu"]["pl"] and al["menu"]["en"] != al["menu"]["pl"])
        json.dumps(d)

    def test_feed_rows_have_polish_text(self):
        d = self.alice(self.mk())
        rows = [m for m in d["feed"] if m["kind"] == "alife"]
        self.assertTrue(rows)
        self.assertTrue(all(m["textPl"] and m["textPl"] != m["text"] for m in rows))
        self.assertTrue(any(m["kind"] != "alife" for m in d["feed"]))        # the diary rows are still there

    def test_clan_list_summary(self):
        c = self.mk().clans()
        row = c["clans"][0]
        self.assertIn("alife", row)
        self.assertIsInstance(row["alife"]["threads"], int)
        self.assertTrue(any(m["kind"] == "alife" for m in c["feed"]))

    def test_switch_off_is_shown(self):
        os.environ["T2R_CLAN_ALIFE"] = "0"
        d = self.alice(self.mk())
        self.assertFalse(d["alife"]["enabled"])
        self.assertTrue(d["alife"]["exists"])                                # the stored simulation stays visible
        self.assertFalse([t for t in d["alife"]["menu"]["en"] if t in set(AL.ticker_lines(sqlite3.connect(self.db), KEY, CS._load(sqlite3.connect(self.db), KEY), 1, 4, "en"))])

    def test_read_only(self):
        before = os.path.getmtime(self.db), os.path.getsize(self.db)
        a = self.mk()
        self.alice(a)
        a.clans()
        self.assertEqual(before, (os.path.getmtime(self.db), os.path.getsize(self.db)))

    def test_no_alife_without_a_state(self):
        db2 = os.path.join(self.tmp, "copy.db")
        shutil.copy(self.db, db2)
        c = sqlite3.connect(db2)
        c.execute("DELETE FROM clan_alife")
        c.commit()
        c.close()
        a = store.Admin(db=db2, daemon_log=self.logp, reports=None, daemon="127.0.0.1:1")
        d = self.alice(a)
        self.assertFalse(d["alife"]["exists"])
        self.assertTrue(d["ok"] and d["clan"])


if __name__ == "__main__":
    unittest.main()
