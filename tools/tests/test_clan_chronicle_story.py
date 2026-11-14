"""Chronicle through the real clan_story path (switch on): a day result carrying r["match"] (what daemon.clan_finalize fills) gives stored 'chron' rows with a style,
read back in EN and PL; without r["match"] the day still works.   Run: python tools/tests/test_clan_chronicle_story.py"""
import os
import sqlite3
import sys

os.environ["T2R_CLAN_CHRONICLE"] = "1"
os.environ["T2R_CLAN_SAGA"] = "0"             # these tests cover the legacy match / haul rows (the saga has tools/tests/test_clan_saga.py)
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import clan                      # noqa: E402
import clan_story as CS          # noqa: E402

FAILS = []


def check(cond, what):
    print(("ok   " if cond else "FAIL ") + what)
    if not cond:
        FAILS.append(what)


c = sqlite3.connect(":memory:")
clan.ensure(c)
CS.ensure(c)
tid = "ab" * 12
cl = clan.new_clan(clan.WLF)
cl.update(healthy=14, hungry=1, sick=1, day=3)
clan.save(c, tid, cl)
CS.on_new_run(c, tid, clan.WLF)
newc = clan.load(c, tid)
r = {"day": 3, "supplies": 9, "needed": 8, "died": 0, "gained": 0, "parts": 420, "match": {"map": "Hospital", "kills": 6, "supplies": 9, "parts": 420}}
CS.on_day(c, tid, newc, r)
en = CS.read_feed(c, tid, 20)
pl = CS.read_feed(c, tid, 20, lang="pl")
ch = [m for m in en if m["kind"] == "chron"]
check(len(ch) >= 2 and all(m.get("style") for m in ch), "%d chronicle rows with a style" % len(ch))
check(any("Hospital" in m["text"] for m in ch), "the match row names the map")
chp = [m for m in pl if m["kind"] == "chron"]
check(chp and all(m["lang"] == "pl" for m in chp) and any("Szpital" in m["text"] for m in chp), "PL rows use the game's Polish map name")
check(CS.feed_max() == 100, "feed keeps 100 rows with the chronicle on")
r2 = {"day": 4, "supplies": 4, "needed": 8, "died": 0, "gained": 0, "parts": 90}
newc2 = dict(newc, day=4)
clan.save(c, tid, newc2)                                       # like the daemon: the clan's day is saved before the story's on_day (the journal never serves a day the clan has not reached)
CS.on_day(c, tid, newc2, r2)
check(len(CS.read_feed(c, tid, 40)) > len(en), "a day without r['match'] still writes rows")
st = CS._load(c, tid)
check(st["ch"]["log"] and st["ch"]["inv"], "match log + stock persisted in the clan state")
print("\n%d failed" % len(FAILS) if FAILS else "\nall ok")
sys.exit(1 if FAILS else 0)
