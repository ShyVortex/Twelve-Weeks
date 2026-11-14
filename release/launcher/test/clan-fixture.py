"""Fixture for the CLAN screen preview (test/clan-preview.html): a fake clan from the REAL chronicle generator -> a JS file defining window.FIXTURE =
{clan, feed} in the shapes of /clan.json and /clanfeed.json.  Nothing touches a database or the network.

  python -I test/clan-fixture.py <out fixture.js> [tools dir]      (tools dir default: <repo>/tools; seed / days via T2R_FX_SEED / T2R_FX_DAYS)
"""
import json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
out = sys.argv[1]
tools = sys.argv[2] if len(sys.argv) > 2 else os.path.join(HERE, "..", "..", "..", "tools")
sys.path.insert(0, tools)
import clan_chronicle as CH, clan_chronicle_dump as D, clan_story as CS  # noqa: E402

seed, ndays = int(os.environ.get("T2R_FX_SEED", "11")), int(os.environ.get("T2R_FX_DAYS", "9"))
st, days = D.fake_week("W", ndays, seed, 14)
CS._load = lambda c, t: st
pub = CH.public(None, "x", "en")
for _k, _r in enumerate([r for r in pub["roster"] if r["state"] == "healthy"][:2]):     # preview: one depressed, one in shock (the two newer states)
    _r["state"] = ("depressed", "shock")[_k]
feed, rid = [], 0
for day, newc, r, match, rows in days:
    for m in rows:
        rid += 1
        lid = m.get("lid", "")
        row = {"id": rid, "week": (day - 1) // 7 + 1, "day": (day - 1) % 7 + 1, "ts": 1790000000 + rid, "kind": "chron", "mood": m.get("mood"), "text": m["text"],
               "style": lid.split("/")[1].split("~")[0] if lid.startswith("ch/") else ""}
        if lid.startswith("arc/"):          # like clan_story.read_feed: a story arc step = style arc_<kind>, arc id + step number (the thread view of the clan screen)
            row["style"] = "arc_" + lid[4:].split(".")[0]
            row["arc"], row["step"] = (m.get("params") or {}).get("a"), (m.get("params") or {}).get("n")
        feed.append(row)
# member status updates (tools/clan_status.py): four members change state on the last day - hungry, grieving, sick, dead - picked among those the journal names
import copy, re  # noqa: E402
import clan_status as CST  # noqa: E402
s2 = copy.deepcopy(st)
s2.setdefault("ch", {}).pop("stat", None)
s2["ch"]["mem"] = {}
for p in s2["people"]:
    p["il"] = ""; p["s"] = "h"
CST.observe(s2)
txt = " ".join(m["text"] for m in feed)
named = [p for p in s2["people"] if re.search(r"%s" % re.escape(p["n"]), txt)] or list(s2["people"])
for p in s2["people"]:
    p["il"] = ""
    p["s"] = "h"
CST.observe(s2)
s2["day"] = days[-1][0]
pick = named[:4]
pick[0]["s"] = "u"; pick[1]["s"] = "h"; pick[2]["s"] = "s"
s2["ch"].setdefault("mem", {})[str(pick[1]["i"])] = {"grief": {"for": 99, "d": s2["day"], "until": s2["day"] + 8}}
CS._remove(s2, pick[3], s2["day"], "illness")
CST.observe(s2)
pub["status"] = CST.public(s2, "W", "en")
day, newc, r, match, rows = days[-1]
lm = {"day": day - 1, "parts": r["parts"], "supplies": r["supplies"], "needed": r["needed"], "gained": r["gained"], "died": r["died"], "newHungry": 1, "newSick": 0,
      "healed": 1, "leftEarly": False}
_n = len(pub["roster"])
_cnt = lambda st: sum(1 for q in pub["roster"] if q["state"] == st)
newc = {"healthy": _n - _cnt("hungry") - _cnt("sick"), "hungry": _cnt("hungry"), "sick": _cnt("sick")}      # (the roster is the truth; depressed / shock count as healthy in the clan dial)
r["needed"] = 5 + 2 * _n - int(1.2 * _n)
size = _n
clan = {"ok": True, "hasClan": True, "status": "alive", "faction": 1, "factionName": "WLF", "week": (day - 1) // 7 + 1, "weeks": 12, "dayOfWeek": (day - 1) % 7 + 1,
        "daysDone": day, "daysTotal": 84, "size": size, "healthy": newc["healthy"], "hungry": newc["hungry"], "sick": newc["sick"], "needed": r["needed"],
        "maxSize": 17, "runsWon": 1, "runsLost": 2, "boosterNext": 80, "eventToday": None, "event": None, "lastMatch": lm,
        "mission": {"name": "Down Enemies", "inEvent": False, "progress": 8, "goals": [6, 12, 18], "daysLeft": 2},
        "lastMission": {"name": "Down Enemies", "progress": 14, "tier": 2, "boostersEarned": 1},
        "boosters": [{"id": i, "name": n, "count": c} for i, (n, c) in enumerate([("", 0), ("Ammo Pack", 1), ("Armour Plate", 0), ("Med Kit", 2), ("Scope", 0), ("", 0), ("", 0), ("Double Parts", 1)])]}
fx = {"clan": clan, "feed": {"ok": True, "hasClan": True, "source": "http", "feed": feed, "morale": {"value": int(st["morale"]), "label": "steady"}, "chron": pub,
                             "alife": {"ongoing": ["Peter is rationing the last tins.", "Ava is teaching Hector to play chess."]}}}
open(out, "w", encoding="utf-8").write("window.FIXTURE = " + json.dumps(fx, ensure_ascii=False) + ";\n")
print("fixture:", out, len(feed), "rows,", len(pub["roster"]), "members,", len(pub["matches"]), "matches")
