"""Journal rules (seen in game): a clan on day 1 must never show entries of later days (a previous run's diary stayed in clan_feed), and the journal keeps
only written stories as cards, the one-liners as timeline lines between them.  Temp DBs only.  Run: python tools/tests/test_clan_journal_days.py"""
import os, sqlite3, sys, tempfile
import sys as _t2s, os as _t2o; _t2s.path.append(_t2o.path.normpath(_t2o.path.join(_t2o.path.dirname(_t2o.path.abspath(__file__)), ".."))); import t2rtmp  # noqa: E402,F401
TOOLS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for k in ("T2R_CLAN_CHRONICLE", "T2R_CLAN_SAGA", "T2R_CLAN_STATUS", "T2R_CLAN_ALIFE"):
    os.environ[k] = "1"
sys.path.insert(0, TOOLS)
import clan  # noqa: E402
import clan_demo_seed  # noqa: E402
import clan_story as CS  # noqa: E402

FAILS = []
def check(cond, what):
    print(("ok   " if cond else "FAIL ") + what)
    if not cond:
        FAILS.append(what)

TID = "0123456789abcdef01234567"
TMP = tempfile.mkdtemp()
def seed(days):
    p = os.path.join(TMP, "s%d.db" % days)
    sys.argv = ["x", p, "--days", str(days), "--token", TID]
    clan_demo_seed.main()
    return sqlite3.connect(p)

# 1. a new clan: only real stories as cards (the founding + at most DAY_STORIES per day), the one-liners are timeline lines; none from a later day
c1 = seed(1)
f = CS.read_feed(c1, TID, 100, 0, "en", callbacks=True, fold=True)
jr = CS.journal(f)
check(0 < len(jr) <= 3, "day-1 clan: %d journal cards (founding + <= 2 stories)" % len(jr))
check(all(m["day"] <= 1 for m in f), "day-1 clan: no entry of a later day")
check(len(f) == len(CS.read_feed(c1, TID, 100, 0, "en", callbacks=True)), "nothing is merged or dropped: every row is still served (card flag only)")
check(all(e["card"]["kind"] == "founding" or len(CS._sentences(e["card"]["text"])) >= 2 for e in jr), "a card is never a one-liner (>= 2 sentences, the founding line excepted)")
check(any(not m["card"] for m in f) and all(m.get("line") for m in f if not m["card"]), "the small rows are lines with a one-row text")
check(all(len(m["line"]) <= CS.LINE_MAX + 3 for m in f if not m["card"]), "a line fits one row")

# 2. a day-7 clan: <= DAY_STORIES stories per day (+ deaths / arrivals), chronological lines under the story they follow
c7 = seed(7)
f7 = CS.read_feed(c7, TID, 100, 0, "en", callbacks=True, fold=True)
j7 = CS.journal(f7, max_lines=99)
per = {}
for e in j7:
    k = e["card"]
    if CS._story_rank(k) != 0:                                   # deaths, arrivals, the founding: events, not counted against the day's stories
        per[k["day"]] = per.get(k["day"], 0) + 1
check(all(m["day"] <= 7 for m in f7) and max(per.values()) <= CS.DAY_STORIES, "day-7 clan: %d cards, stories per day %s" % (len(j7), sorted(per.items())))
check(sum(1 for m in f7 if m["card"]) < len(f7) / 2, "most rows are lines, not cards (%d cards of %d rows)" % (len(j7), len(f7)))
ok = True
for e in j7:
    ids = [int(x["id"]) for x in e["lines"]]
    ok = ok and ids == sorted(ids) and all(i > int(e["card"]["id"]) for i in ids)       # a line follows its story in time (the oldest card also takes lines older than itself)
nxt = {int(e["card"]["id"]): int(j7[i - 1]["card"]["id"]) if i else 10 ** 9 for i, e in enumerate(j7)}
ok2 = all(int(x["id"]) < nxt[int(e["card"]["id"])] for e in j7 for x in e["lines"])
check(ok and ok2, "lines are in time order and sit under the story they follow, before the next story")
check(all(not x["card"] for e in j7 for x in e["lines"]), "a line is never a card")
check(sum(len(e["lines"]) + e["more"] for e in CS.journal(f7)) == sum(1 for m in f7 if not m["card"]), "every line sits under a story (shown + more)")
import clan_ingame  # noqa: E402
txt = ("\n").join(clan_ingame._journal_rows({"roster": []}, f7, "en"))
check(txt.startswith("J\t") and ("\nL\t" not in txt) and txt.count("\nJ\t") + 1 <= clan_ingame.MAX_JOURNAL, "in-game section 2: J rows only (11-02: the one-liners live inside the multi-event entries)")

# 3. the reader guard: rows of days the clan has not reached are never served (clans.day rolled back = a reset clan)
c7.execute("UPDATE clans SET day=2 WHERE token_id=?", (TID,))
check(all(m["day"] <= 2 for m in CS.read_feed(c7, TID, 100, 0, "en", callbacks=True, fold=True)) and all(m["day"] <= 2 for m in CS.read_feed(c7, TID, 100, 0, "en")), "clan on day 2: nothing of days 3-7 served")

# 4. the root cause: a new run (CHOOSE YOUR SIDE after the old clan died) drops the old run's rows
c = seed(5)
cl = clan.load(c, TID)
cl["status"] = clan.DEAD if hasattr(clan, "DEAD") else 2
clan.save(c, TID, cl)
c.commit()
st, ok = clan.choose_side(c, TID, clan.SERAPHITES)
CS.on_new_run(c, TID, clan.SERAPHITES)
f = CS.read_feed(c, TID, 100, 0, "en", callbacks=True, fold=True)
check(ok and len(f) == 1 and f[0]["day"] == 0, "new run: only the founding line (%d rows)" % len(f))

print("FAILED: %s" % FAILS if FAILS else "all ok")
sys.exit(1 if FAILS else 0)
