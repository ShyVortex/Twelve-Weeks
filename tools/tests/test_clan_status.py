"""Clan member status updates (tools/clan_status.py): delta maths on a simulated clan, payload (launcher public view + wire text), daemon round trip.
Temp DB only. Run: python tools/tests/test_clan_status.py"""
import os, sys, tempfile, json
import sys as _t2s, os as _t2o; _t2s.path.append(_t2o.path.normpath(_t2o.path.join(_t2o.path.dirname(_t2o.path.abspath(__file__)), ".."))); import t2rtmp  # noqa: E402,F401
TOOLS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, TOOLS)
os.environ["T2R_DB"] = os.path.join(tempfile.mkdtemp(), "t.db")
import clan_status as CST, clan_chronicle as CH, clan_chronicle_dump as D, clan_story as CS, clan  # noqa: E402

FAILS = []
def check(cond, what):
    print(("ok   " if cond else "FAIL ") + what)
    if not cond:
        FAILS.append(what)

st, days = D.fake_week("W", 1, 5, 10, death=0)
p = st["people"]
st["day"] = 1
check(CST.observe(st) == [], "first call seeds the snapshot: no events for the whole camp")
for q in p:
    q["s"] = "h"
CST.observe(st)
st["day"] = 2
p[0]["s"] = "u"; p[1]["s"] = "s"
ev = CST.observe(st)
codes = {e["n"]: e["c"] for e in ev}
check(codes == {p[0]["n"]: CST.HUNGRY, p[1]["n"]: CST.SICK}, "hungry and sick members produce events: %r" % codes)
check(CST.observe(st) == [], "no change -> no new event (idempotent)")
st["day"] = 3
p[0]["s"] = "h"
ev = CST.observe(st)
check(len(ev) == 1 and ev[0]["c"] == CST.RECOVERED, "back to healthy = recovered")
st.setdefault("ch", {}).setdefault("mem", {})[str(p[2]["i"])] = {"grief": {"for": 99, "d": 2, "until": 11}}
ev = CST.observe(st)
check(len(ev) == 1 and ev[0]["c"] == CST.SAD, "grief memory = sad")
check(CST.code_of(dict(st, day=2), p[2]) == CST.SHOCK, "the day a close member died the grieving one is in shock (then sad)")
st["ch"].setdefault("dep", {})[str(p[1]["i"])] = {"n": 5, "d": 3, "up": -1, "rec": False}
check(CST.code_of(st, p[1]) == CST.DEPRESSED and CST.NAMES[CST.DEPRESSED] == "depressed" and CST.EXPR[CST.DEPRESSED] == "depressed", "depression counter >= 4 = depressed (image id 'depressed')")
del st["ch"]["dep"][str(p[1]["i"])]
st["day"] = 4
gone = p[1]["n"]
CS._remove(st, p[1], 4, "illness")
ev = CST.observe(st)
check(any(e["c"] == CST.DEAD and e["n"] == gone and e["f"] == CST.SICK for e in ev), "death produces a dead event from sick")
newp = CS.new_person(__import__("random").Random(1), st, state="h", join_day=4)
st["people"].append(newp)
ev = CST.observe(st)
check(any(e["c"] == CST.NEW for e in ev), "new member event")
st["day"] = 9
check(CST.pending(st) == [] or all(9 - e["d"] < CST.EV_DAYS for e in CST.pending(st)), "old events expire after %d days" % CST.EV_DAYS)
check(len(st["ch"]["stat"]["ev"]) <= CST.EV_MAX, "event list capped")
# payload
st["day"] = 4
CST.observe(st)
pub = CST.public(st, "W", "en")
check(pub and all(k in pub[0] for k in ("id", "name", "code", "state", "img", "line", "expr")), "public view has id/name/state/img/line")
check(set(pub[0]["img"]) == {"neutral", "hungry", "sad", "sick", "dead", "depressed", "shock"} and pub[0]["img"]["dead"].endswith("/dead"), "image ids per expression (headshot hook)")
pl = CST.public(st, "W", "pl")
check(pl and pl[0]["line"] != pub[0]["line"], "Polish story line differs")
fm = {"i": 1, "n": "Rosa", "g": "f", "r": "cook", "c": CST.SICK, "f": 0, "d": 4, "ln": ""}
ml = dict(fm, g="m", n="Marek")
check(CST.story_line(fm, "pl").startswith("Rosa zachorowa") and "zachorowała" in CST.story_line(fm, "pl") and "zachorował." in CST.story_line(ml, "pl"), "Polish story line follows the gender")
w = CST.wire_text(st)
toks = w.split()
firstname = next(i for i, t in enumerate(toks) if t.startswith("scm"))
check(toks[0].startswith("sc=") and all(t.split("=")[1].lstrip("-").isdigit() for t in toks[:firstname]) and all(t.startswith("scm") for t in toks[firstname:]), "wire: integers first, names last: " + w)
check(CST.wire_text({"people": [], "ch": {}}) == "", "nothing pending -> empty tail (old behaviour)")
os.environ["T2R_CLAN_STATUS"] = "0"
check(CST.observe(st) == [] and CST.wire_text(st) == "" and CST.public(st, "W") == [], "T2R_CLAN_STATUS=0 switches everything off")
del os.environ["T2R_CLAN_STATUS"]
# chronicle public()
_orig_load = CS._load
CS._load = lambda c, t: st
pubc = CH.public(None, "x", "en")
check(pubc.get("status") and pubc["status"][0]["id"], "clan_chronicle.public carries 'status'")
# daemon round trip
CS._load = _orig_load
import daemon  # noqa: E402
TOK = "54324e3a" + "416c696365" + "00" * 11 + "0123456789abcdef01234567"
daemon.clan_op(0xE0, TOK.encode())
daemon.clan_side(TOK, 1)
fr = daemon.clan_op(0xE0, TOK.encode())
txt = fr[3:].decode()
check("lmh=" in txt and " sc=" not in txt, "fresh clan: the old state text, no status tail")
with daemon._dblock, daemon.dbc() as c:
    key = daemon.clan_key(c, TOK)
    story = daemon.clan_story._load(c, key)
    if story:
        CST.observe(story)
        story["people"][0]["s"] = "u"
        CST.observe(story)
        daemon.clan_story._save(c, key, story)
txt = daemon.clan_op(0xE0, TOK.encode())[3:].decode()
check(story is not None and " sc=1 " in txt and "scm0=" in txt, "daemon state reply carries the status tail: " + txt[-90:])
print("\nall passed" if not FAILS else "\n%d FAILED" % len(FAILS))
sys.exit(1 if FAILS else 0)
