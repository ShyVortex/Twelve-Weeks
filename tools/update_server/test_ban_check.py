import os
import sqlite3
import tempfile
import unittest

import ban_check as b

H1, H2, H3 = "a" * 24, "b" * 24, "c" * 24
X1, X2 = "1" * 24, "2" * 24


class T(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()
        self.db = os.path.join(self.d, "t2r.db")
        c = sqlite3.connect(self.db)
        c.execute("CREATE TABLE hwids(hash TEXT, token TEXT, steamid INTEGER, name TEXT, first_seen REAL, last_seen REAL)")
        c.execute("CREATE TABLE players(token TEXT, steamid INTEGER, name TEXT)")
        for h in (H1, H2, H3):
            c.execute("INSERT INTO hwids VALUES(?,?,?,?,0,0)", (h, "tok1", 76561198000000001, "Cheater"))
        c.execute("INSERT INTO players VALUES('tok1',76561198000000001,'Cheater')")
        c.commit()
        c.close()

    def bans(self, text):
        with open(os.path.join(self.d, "bans.txt"), "w") as f:
            f.write(text)

    def q(self, **kw):
        return b.route(self.db, {k: [v] for k, v in kw.items()})

    def test_steamid(self):
        self.bans("76561198000000009  # note: private, reason: cheating\n")
        self.assertEqual(self.q(s="76561198000000009"), {"banned": True, "reason": "cheating"})
        self.assertFalse(self.q(s="76561198000000008")["banned"])

    def test_private_comment_not_leaked(self):
        self.bans("76561198000000009  # hct1co\n")
        self.assertEqual(self.q(s="76561198000000009"), {"banned": True, "reason": ""})

    def test_explicit_hwid(self):
        self.bans("hwid:%s  # reason: ban evasion\n" % H2)
        self.assertTrue(self.q(h=X1 + "," + H2)["banned"])
        self.assertFalse(self.q(h=X1 + "," + X2)["banned"])

    def test_new_steam_account_same_pc(self):
        self.bans("76561198000000001  # reason: aimbot\n")
        r = self.q(h=H1 + "," + H3 + "," + X1, s="76561198000000777")
        self.assertEqual(r, {"banned": True, "reason": "aimbot"})
        self.assertFalse(self.q(h=H1 + "," + X1, s="76561198000000777")["banned"])    # one shared component alone: no (clone images)

    def test_name_entry(self):
        self.bans("cheater\n")
        self.assertTrue(self.q(s="76561198000000001")["banned"])

    def test_placeholders_ignored(self):
        ph = sorted(b.PLACEHOLDERS)[0]
        self.bans("hwid:%s\n" % ph)
        self.assertFalse(self.q(h=ph)["banned"])

    def test_junk_and_missing(self):
        self.assertEqual(self.q(h="zz", s="abc"), {"banned": False, "reason": ""})        # no bans.txt
        self.bans("76561198000000009\n")
        self.assertFalse(self.q(h="zz")["banned"])
        os.remove(self.db)
        self.assertFalse(b.route(self.db, {"s": ["76561198000000001"]})["banned"])

    def test_token(self):
        t = "ab" * 32
        self.bans("token:%s # reason: x\n" % t)
        self.assertTrue(self.q(t=t)["banned"])


if __name__ == "__main__":
    unittest.main()
