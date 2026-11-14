"""python tools/update_server/test_clanfeed_alife.py : the A-Life through the launcher's feed path (/clanfeed.json): the rows keep the launcher's fields, the Polish text is
rendered at read time, "alife" (what is happening in camp) is present only while the switch is on, and the database is never written."""
import json, os, random, sqlite3, sys, tempfile, threading, urllib.request
import sys as _t2s, os as _t2o; _t2s.path.append(_t2o.path.normpath(_t2o.path.join(_t2o.path.dirname(_t2o.path.abspath(__file__)), ".."))); import t2rtmp  # noqa: E402,F401  (temp hygiene: tools/t2rtmp.py)
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ["T2R_CLAN_CHRONICLE"] = "0"   # these cover the plain diary / A-Life rows (chronicle is ON by default)
import server  # (before the tools/ import path: tools/server.py exists too)
import clan, clan_story, clanfeed_view

d = tempfile.mkdtemp(prefix="t2r-tmp-clanfeed-alife-")
db = os.path.join(d, "t2r.db")
tid = "0123456789abcdef01234567"
c = sqlite3.connect(db)
clan.rng = random.Random(4)
os.environ["T2R_CLAN_ALIFE"] = "1"
clan.choose_side(c, tid, clan.SERAPHITES)
clan_story.on_new_run(c, tid, clan.SERAPHITES)
for i in range(1, 16):
    new, r = clan.apply_match(c, tid, "m%d" % i, 2500 if i % 4 else 900)
    clan_story.on_day(c, tid, new, r)
c.commit()
c.close()
before = (os.path.getmtime(db), os.path.getsize(db))

v = clanfeed_view.view(db, tid, limit=100)
al_rows = [m for m in v["feed"] if m["kind"] == "alife"]
assert v["ok"] and al_rows, "A-Life rows reach the launcher feed"
assert all(set(m) - {"thread", "prev", "tstep"} == {"id", "day", "week", "kind", "mood", "faction", "text", "names", "ts", "short", "lang"} for m in v["feed"]), v["feed"][0]
assert v["feed"][0]["id"] > v["feed"][-1]["id"], "newest first"
assert all(m["mood"] in ("hopeful", "cheerful", "calm", "neutral", "worried", "afraid", "desperate", "grieving", "grim", "despair") for m in v["feed"]), "moods the launcher colours"
assert all(len(m["short"].encode("utf-8")) <= 150 for m in v["feed"]), "toast form fits the wire"
assert v["alife"]["ongoing"] is not None and v["alife"]["weather"] and v["alife"]["season"], v.get("alife")
vp = clanfeed_view.view(db, tid, limit=100, lang="pl")
pl_rows = [m for m in vp["feed"] if m["kind"] == "alife"]
assert [m["id"] for m in pl_rows] == [m["id"] for m in al_rows] and all(m["lang"] == "pl" and m["text"] != e["text"] for m, e in zip(pl_rows, al_rows)), "Polish rows"
assert vp["alife"]["season"] != v["alife"]["season"], "the season is told in the asked language"
# the menu (same ids and text as the game's widget)
assert v["menu"] and any(str(m["id"]).startswith("a") for m in v["menu"]) or len(v["menu"]) == 6, v["menu"]
# the switch off: the stored rows stay (history), no "alife" block, no new A-Life lines
os.environ["T2R_CLAN_ALIFE"] = "0"
vo = clanfeed_view.view(db, tid, limit=100)
assert "alife" not in vo and any(m["kind"] == "alife" for m in vo["feed"]), "history stays, live block gone"
assert not any(str(m["id"]).startswith("a") for m in vo["menu"]), "no A-Life ticker lines while off"
assert (os.path.getmtime(db), os.path.getsize(db)) == before, "read-only: the database was not written"
# the HTTP route
os.environ["T2R_CLAN_ALIFE"] = "1"
srv = server.make_server(os.path.join(d, "data"), host="127.0.0.1", port=0, db=db)
threading.Thread(target=srv.serve_forever, daemon=True).start()
r = json.load(urllib.request.urlopen("http://127.0.0.1:%d/clanfeed.json?player=%s&limit=60&lang=pl" % (srv.server_address[1], tid)))
srv.shutdown()
assert r["ok"] and r["alife"]["ongoing"] is not None and any(m["kind"] == "alife" and m["lang"] == "pl" for m in r["feed"]), r.keys()
os.environ.pop("T2R_CLAN_ALIFE", None)
print("clanfeed A-Life tests OK (%d A-Life rows of %d)" % (len(al_rows), len(v["feed"])))
