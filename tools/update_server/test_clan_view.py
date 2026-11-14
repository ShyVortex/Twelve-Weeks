"""python tools/update_server/test_clan_view.py : /clan.json view against a throw-away database (the live t2r.db is never touched)."""
import json, os, sqlite3, sys, tempfile
import sys as _t2s, os as _t2o; _t2s.path.append(_t2o.path.normpath(_t2o.path.join(_t2o.path.dirname(_t2o.path.abspath(__file__)), ".."))); import t2rtmp  # noqa: E402,F401  (temp hygiene: tools/t2rtmp.py)
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import clan, clan_view

d = tempfile.mkdtemp()
db = os.path.join(d, "t2r.db")
c = sqlite3.connect(db)
tid = "0123456789abcdef01234567"
clan.choose_side(c, tid, clan.WLF)
cl = clan.load(c, tid)
cl.update(day=17, healthy=12, hungry=2, sick=1, weeks_total=3, runs_won=4, runs_lost=2,
          last_result=json.dumps({"day": 16, "parts": 1310, "supplies": 26, "needed": 14, "gained": 1, "died": 0}))
clan.save(c, tid, cl)
clan.mission_choose(c, tid, 1)
c.commit(); c.close()
v = clan_view.view(db, tid)
assert v["ok"] and v["hasClan"] and v["factionName"] == "WLF" and v["size"] == 15 and v["needed"] == clan.needed(15), v
assert v["week"] == 3 and v["dayOfWeek"] == 4 and v["event"]["kind"] == "attack" and v["event"]["dayOfEvent"] == 3, v     # day 17: the attack that started on day 15
assert v["mission"]["name"] == "Down Enemies" and v["lastMatch"]["parts"] == 1310 and len(v["boosters"]) == 7, v
assert clan_view.view(db, "f" * 24) == {"ok": True, "hasClan": False}
assert not clan_view.view(db, "nope")["ok"]
assert clan_view.view(db, "aa" * 20 + tid)["size"] == 15            # full 64-hex token: its last 24 chars
before = os.path.getmtime(db)
clan_view.view(db, tid)
assert os.path.getmtime(db) == before
print("clan view OK")
