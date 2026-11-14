"""python tools/update_server/test_clanfeed_view.py : /clanfeed.json view and the HTTP route against a throw-away database (live t2r.db never touched)."""
import json, os, random, sqlite3, sys, tempfile, threading, urllib.request, urllib.error
import sys as _t2s, os as _t2o; _t2s.path.append(_t2o.path.normpath(_t2o.path.join(_t2o.path.dirname(_t2o.path.abspath(__file__)), ".."))); import t2rtmp  # noqa: E402,F401  (temp hygiene: tools/t2rtmp.py)
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ["T2R_CLAN_CHRONICLE"] = "0"   # these cover the plain diary / A-Life rows (chronicle is ON by default)
import server  # (before the tools/ import path: tools/server.py exists too)
import clan, clan_story, clanfeed_view

d = tempfile.mkdtemp()
db = os.path.join(d, "t2r.db")
tid = "0123456789abcdef01234567"
c = sqlite3.connect(db)
clan.rng = random.Random(4)
clan.choose_side(c, tid, clan.WLF)
clan_story.on_new_run(c, tid, clan.WLF)
for i in range(1, 12):
    new, r = clan.apply_match(c, tid, "m%d" % i, 500 if i % 3 else 3000)
    clan_story.on_day(c, tid, new, r)
c.commit(); c.close()

v = clanfeed_view.view(db, tid)
assert v["ok"] and v["hasClan"] and v["factionName"] == "WLF" and v["feed"], v
assert set(v["feed"][0]) - {"thread", "prev", "tstep", "style", "arc", "step", "map"} == {"id", "day", "week", "kind", "mood", "faction", "text", "names", "ts", "short", "lang"}, v["feed"][0]
assert v["feed"][0]["id"] > v["feed"][-1]["id"] and v["morale"]["label"] in ("hopeful", "steady", "strained", "grim"), v
assert v["people"] and {"name", "role", "gender", "state", "mood", "illness"} <= set(v["people"][0]), v["people"][0]
newest = v["feed"][0]["id"]
assert clanfeed_view.view(db, tid, since=newest)["feed"] == []
assert len(clanfeed_view.view(db, tid, limit=3)["feed"]) == 3
assert clanfeed_view.view(db, "aa" * 20 + tid)["feed"], "64-hex token"
assert clanfeed_view.view(db, "f" * 24) == {"ok": True, "hasClan": False, "feed": []}
assert not clanfeed_view.view(db, "nope")["ok"] and not clanfeed_view.view(db, tid, limit="x")["ok"]
# a database that has a clan but no feed tables (older daemon): empty feed, no error, nothing created
db2 = os.path.join(d, "old.db")
c = sqlite3.connect(db2); clan.choose_side(c, tid, clan.SERAPHITES); c.commit(); c.close()
v2 = clanfeed_view.view(db2, tid)
assert v2["ok"] and v2["hasClan"] and v2["feed"] == [], v2
c = sqlite3.connect(db2); assert not c.execute("select 1 from sqlite_master where name='clan_feed'").fetchall(); c.close()
before = os.path.getmtime(db); clanfeed_view.view(db, tid); assert os.path.getmtime(db) == before
# Polish (lang=pl): same messages, rendered from the stored template ids; the roster gets Polish display words next to the machine keys
vp = clanfeed_view.view(db, tid, lang="pl")
assert vp["lang"] == "pl" and [m["id"] for m in vp["feed"]] == [m["id"] for m in v["feed"]], vp["lang"]
assert all(m["lang"] == "pl" and m["text"] != e["text"] and len(m["short"].encode("utf-8")) <= 150 for m, e in zip(vp["feed"], v["feed"])), vp["feed"][0]
assert vp["people"][0]["state"] == v["people"][0]["state"] and {"roleText", "stateText", "moodText"} <= set(vp["people"][0]) and vp["morale"]["text"], vp["people"][0]
assert clanfeed_view.view(db, tid, lang="xx")["feed"][0]["lang"] == "en" and clanfeed_view.view(db, tid)["lang"] == "en"
# a feed table from before the language-neutral columns: read-only readers still serve it (English, whatever language is asked)
db3 = os.path.join(d, "pre.db")
c = sqlite3.connect(db3); clan.choose_side(c, tid, clan.WLF)
c.execute("CREATE TABLE clan_feed(token_id TEXT, id INTEGER, ts REAL, day INTEGER, week INTEGER, kind TEXT, mood TEXT, faction INTEGER, text TEXT, names TEXT, PRIMARY KEY(token_id, id))")
c.execute("INSERT INTO clan_feed VALUES(?,?,?,?,?,?,?,?,?,?)", (tid, 1, 1.0, 1, 1, "calm", "calm", 1, "An old line.", "[]")); c.commit(); c.close()
vo = clanfeed_view.view(db3, tid, lang="pl")
assert vo["feed"] and vo["feed"][0]["text"] == "An old line." and vo["feed"][0]["lang"] == "en", vo

# the HTTP route
srv = server.make_server(os.path.join(d, "data"), host="127.0.0.1", port=0, db=db)
threading.Thread(target=srv.serve_forever, daemon=True).start()
r = json.load(urllib.request.urlopen("http://127.0.0.1:%d/clanfeed.json?player=%s&limit=5" % (srv.server_address[1], tid)))
assert r["ok"] and len(r["feed"]) == 5, r
srv.shutdown()
srv2 = server.make_server(os.path.join(d, "data"), host="127.0.0.1", port=0)
threading.Thread(target=srv2.serve_forever, daemon=True).start()
try:
    urllib.request.urlopen("http://127.0.0.1:%d/clanfeed.json?player=%s" % (srv2.server_address[1], tid))
    assert False
except urllib.error.HTTPError as e:
    assert e.code == 503
srv2.shutdown()
print("clanfeed view OK")
