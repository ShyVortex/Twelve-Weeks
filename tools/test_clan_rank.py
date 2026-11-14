"""Unit tests of the 2013 Factions rank math (clan.rank_days / rank_of / the sqlite backfill + carry-over).  python test_clan_rank.py"""
import os
import sqlite3
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import clan


def play(total, d0, d1, status=clan.ALIVE):
    return clan.rank_days(total, d0, d1, status)


class RankMath(unittest.TestCase):
    def test_weeks_floor(self):
        self.assertEqual(clan.rank_of({"days_total": 0, "runs_won": 0}), (0, 0))
        self.assertEqual(clan.rank_of({"days_total": 6, "runs_won": 0}), (0, 0))
        self.assertEqual(clan.rank_of({"days_total": 7, "runs_won": 0}), (0, 1))
        self.assertEqual(clan.rank_of({"days_total": 38, "runs_won": 0}), (0, 5))        # 5w3d

    def test_two_losses_carry_over(self):
        # 5 weeks + 3 days, the clan dies, again 5 weeks + 3 days: the days add up across clans (2 x 38 = 76 days = 10 whole weeks)
        t = 0
        for _ in range(2):
            d = 0
            while d < 38:
                t = play(t, d, d + 1)
                d += 1
        self.assertEqual(t, 76)
        self.assertEqual(clan.rank_of({"days_total": t, "runs_won": 0})[1], 10)
        # (the 2013 wiki sentence calls this "number 9": its arithmetic is loose - 9 would need 63..69 days; floor(days / 7) is what the mod books)

    def test_uncounted_day_adds_nothing(self):
        self.assertEqual(play(10, 4, 4), 10)
        self.assertEqual(play(10, 4, 3), 10)           # never negative

    def test_win_books_the_84th_day(self):
        self.assertEqual(play(82, 82, 83, clan.WON), 82 + 1 + 1)
        self.assertEqual(clan.rank_of({"days_total": 84, "runs_won": 1}), (1, 12))

    def test_symbol_is_campaigns_clamped(self):
        for won, sym in ((0, 0), (1, 1), (8, 8), (9, 9), (10, 9), (50, 9)):
            self.assertEqual(clan.rank_of({"days_total": 0, "runs_won": won})[0], sym)

    def test_cap_999(self):
        self.assertEqual(clan.rank_of({"days_total": 999 * 7, "runs_won": 0})[1], 999)
        self.assertEqual(clan.rank_of({"days_total": 10 ** 6, "runs_won": 0})[1], 999)
        self.assertEqual(play(clan.RANK_MAX_DAYS, 3, 4), clan.RANK_MAX_DAYS)
        self.assertEqual(clan.rank_of({"days_total": clan.RANK_MAX_DAYS, "runs_won": 0})[1], 999)

    def test_missing_fields(self):
        self.assertEqual(clan.rank_of({}), (0, 0))
        self.assertEqual(clan.rank_of({"days_total": None, "runs_won": None}), (0, 0))


class Storage(unittest.TestCase):
    def test_old_save_backfill(self):
        c = sqlite3.connect(":memory:")
        c.execute("CREATE TABLE clans(token_id TEXT PRIMARY KEY, faction INT, status INT, day INT, healthy INT, hungry INT, sick INT, "
                  "last_mid TEXT, last_result TEXT, weeks_total INT, runs_won INT, runs_lost INT, created REAL, updated REAL)")
        c.execute("INSERT INTO clans(token_id,faction,status,day,weeks_total,runs_won) VALUES('a',1,1,17,2,0)")      # alive, week 3 day 4: 2 whole weeks + 3 days
        c.execute("INSERT INTO clans(token_id,faction,status,day,weeks_total,runs_won) VALUES('b',1,2,30,4,0)")      # dead: only whole weeks
        c.execute("INSERT INTO clans(token_id,faction,status,day,weeks_total,runs_won) VALUES('w',1,1,10,12,1)")     # won once (the old server booked 11 weeks for it) + restarted, week 2 day 4: (12+1) weeks + 3 days
        clan.ensure(c)
        self.assertEqual(clan.load(c, "a")["days_total"], 17)
        self.assertEqual(clan.load(c, "b")["days_total"], 28)
        self.assertEqual(clan.load(c, "w")["days_total"], 94)
        clan.ensure(c)                                  # second ensure must not backfill again
        self.assertEqual(clan.load(c, "a")["days_total"], 17)

    def test_choose_side_keeps_days(self):
        c = sqlite3.connect(":memory:")
        clan.ensure(c)
        cl = clan.new_clan(clan.WLF)
        cl.update(days_total=40, runs_won=2, runs_lost=1, weeks_total=5, status=clan.DEAD)
        clan.save(c, "t", cl)
        new, ok = clan.choose_side(c, "t", clan.SERAPHITES)
        self.assertTrue(ok)
        self.assertEqual((new["days_total"], new["runs_won"]), (40, 2))
        self.assertEqual(clan.load(c, "t")["days_total"], 40)

    def test_state_text(self):
        t = clan.state_text(dict(clan.new_clan(clan.WLF), days_total=70, runs_won=3, last_mid=""))
        self.assertIn(" wk=10 ", " " + t + " ")
        self.assertIn(" rk=3 ", " " + t + " ")


if __name__ == "__main__":
    unittest.main()
