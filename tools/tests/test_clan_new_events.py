"""INFECTED HORDE and SPOILED SUPPLIES (re/clan-events-1117.md): stories of the 2013 event calendar. Offline, temp DBs only.
They are on by default, move no number, and every text the player reads about them (diary feed, journal entry, EN + PL) tells the right story:
a horde names no enemy faction, spoiled supplies has its own lines; switched off, those days read as the 2013 events again.
Run: python tools/tests/test_clan_new_events.py"""
import os, re, sys
import sys as _t2s, os as _t2o; _t2s.path.append(_t2o.path.normpath(_t2o.path.join(_t2o.path.dirname(_t2o.path.abspath(__file__)), ".."))); import t2rtmp  # noqa: E402,F401

TOOLS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, TOOLS)
os.environ["T2R_CLAN_CHRONICLE"] = "0"
os.environ.pop("T2R_CLAN_NEW_EVENTS", None)
import clan, clan_story as CS, clan_journal as CJ  # noqa: E402
import clan_journal_text as EN, clan_journal_text_pl as PL  # noqa: E402
import clan_story_pl as PLN  # noqa: E402
import clan_alife_report as R  # noqa: E402

FAILS = []
def check(cond, what):
    print(("ok   " if cond else "FAIL ") + what)
    if not cond:
        FAILS.append(what)

ENEMY_RE = re.compile(r"\b(Scars?|Wolves|Wolf|WLF|Seraphites?|Blizn\w*|Wilk\w*|Serafi\w*)\b")
HORDE_KINDS = {"event_warn_h", "event_hold_h", "event_heavy_h", "event_massacre_h", "death_horde", "death_horde_many"}
ENEMY_KINDS = {"event_warn", "event_hold", "event_heavy", "event_massacre", "death_attack", "death_attack_many"}

# ------------------------------------------------------------------ text sets: EN and PL side by side, the right placeholders
for k in ("hwarn", "hatk0", "hatk1", "hatk2", "hatk3", "hatk_none", "death_horde", "gstart5", "gwin5", "gfail5", "t_hatk", "t_hatk_none", "t_hwarn", "t_gstart5", "f_hatk"):
    en, pl = EN.TEXT.get(k) if hasattr(EN, "TEXT") else None, None
    src_en = next((getattr(EN, n) for n in dir(EN) if isinstance(getattr(EN, n), dict) and k in getattr(EN, n)), None)
    src_pl = next((getattr(PL, n) for n in dir(PL) if isinstance(getattr(PL, n), dict) and k in getattr(PL, n)), None)
    check(src_en is not None and src_pl is not None and len(src_en[k]) == len(src_pl[k]) >= 1, "journal text %s: EN and PL, the same number of lines" % k)
    if src_en is not None and src_pl is not None:
        check(all(not ENEMY_RE.search(t if isinstance(t, str) else t[1]) and "{E}" not in (t if isinstance(t, str) else t[1]) for t in list(src_en[k]) + list(src_pl[k])),
              "journal text %s names no enemy faction" % k)
check(len(EN.EVENT_NAMES) == len(PL.EVENT_NAMES) == 6 and EN.EVENT_NAMES[clan.GN_SPOIL] == "SPOILED SUPPLIES" and EN.HORDE_NAME == clan.ATTACK_NAMES[clan.AN_HORDE],
      "captions: SPOILED SUPPLIES is growth name 5, INFECTED HORDE is attack name 1 (EN + PL)")
for k in sorted(HORDE_KINDS):
    en = CS.LINES.get(k) or []
    check(len(en) >= 2 and all(not ENEMY_RE.search(t) and "{enem" not in t for _sc, t in en) and all(sc == "*" for sc, _t in en), "diary lines %s: generic, no enemy faction (%d)" % (k, len(en)))
    check(all(PLN.REG.get(PLN.lid(k, t)) for _sc, t in en), "diary lines %s have their Polish twins" % k)
    check(k in CS.KIND_MOOD, "diary kind %s has a mood" % k)


def run(fac, start, days, seed, parts_mult):
    return R.simulate(fac, start, days, seed=seed, alife=False, parts_fn=lambda i, c0, need: int(need * clan.PARTS_PER_SUPPLY * parts_mult))


def rows_of(log, kinds):
    return [(e, r) for e in log for r in e["rows"] if r["kind"] in kinds]


# ------------------------------------------------------------------ a horde: days 27 .. 34 (the attack of day 30 settles on its third match)
for fac, fk in ((clan.WLF, "W"), (clan.SERAPHITES, "S")):
    for seed, mult in ((3, 1.3), (4, 0.75)):
        tag = "%s seed %d" % (fk, seed)
        os.environ.pop("T2R_CLAN_NEW_EVENTS", None)
        c, tid, log = run(fac, (24, 2, 1, 27), 8, seed, mult)
        os.environ["T2R_CLAN_NEW_EVENTS"] = "0"
        c0, tid0, log0 = run(fac, (24, 2, 1, 27), 8, seed, mult)
        os.environ.pop("T2R_CLAN_NEW_EVENTS", None)
        nums = lambda lg: [(e["clan"]["healthy"], e["clan"]["hungry"], e["clan"]["sick"], e["clan"]["day"], e["clan"]["status"], e["r"].get("evk"), e["r"].get("evt"), e["r"].get("evl")) for e in lg]
        check(nums(log) == nums(log0), "%s: the horde moves no number (healthy / hungry / sick / day / tier / lost identical on and off)" % tag)
        settled = [e for e in log if e["r"].get("evk") == clan.EV_ATTACK]
        check(len(settled) == 1 and settled[0]["r"].get("evn") == clan.AN_HORDE, "%s: the attack of day 30 settles as a horde" % tag)
        h = rows_of(log, HORDE_KINDS)
        en_ = [(e, r) for e, r in rows_of(log, ENEMY_KINDS)                      # (the warning of the NEXT attack, day 35, is the enemy's and stays theirs)
               if not (r["kind"] == "event_warn" and clan.event_today(e["day"]) == (clan.EV_ATTACK, clan.AN_ENEMY))]
        solo = any(len(e["people"]) <= 1 for e in log)
        check(len(h) >= 1 and (not en_ or solo), "%s: the diary tells the horde in its own lines (%d rows; enemy-attack rows %d)" % (tag, len(h), len(en_)))
        check(all(not ENEMY_RE.search(r["text"]) for _e, r in h), "%s: no horde row names an enemy faction" % tag)
        check(all((CS.render_msg(r["lid"], __import__("json").loads(r["params"]) if isinstance(r["params"], str) else r["params"], "pl") or "{") .count("{") == 0 for _e, r in h),
              "%s: every horde row renders in Polish" % tag)
        check(not rows_of(log0, HORDE_KINDS) and rows_of(log0, ENEMY_KINDS), "%s: switched off, the same days tell the enemy's attack" % tag)
        # the journal entry of the day the horde came, and of the day it was announced
        je = {int(x["day"]): x for x in CJ.entries(c, tid, "en")}
        jp = {int(x["day"]): x for x in CJ.entries(c, tid, "pl")}
        sd = int(settled[0]["day"]) if settled else -1
        ent = je.get(sd) or {}
        caps = [cap for cap, _t in ent.get("paras", [])]
        body = " ".join(t for _c, t in ent.get("paras", []))
        check(EN.HORDE_NAME in caps and re.search(r"horde|infected", body, re.I) and not any(re.search(r"\bATTACK$", cp) for cp in caps),
              "%s: journal, the day it came: caption INFECTED HORDE, the horde in the text (%s)" % (tag, caps))
        check("horde" in (ent.get("title") or "").lower() or settled[0]["clan"]["status"] != clan.ALIVE or len(ent.get("title") or "") > 0, "%s: the entry has a title (%s)" % (tag, ent.get("title")))
        pent = jp.get(sd) or {}
        check(PL.HORDE_NAME in [cap for cap, _t in pent.get("paras", [])] and "{" not in " ".join(t for _c, t in pent.get("paras", [])), "%s: the same entry in Polish" % tag)
        warn = [x for d, x in je.items() if d < sd and EN.HORDE_NAME in [cap for cap, _t in x.get("paras", [])]]
        check(len(warn) >= 1, "%s: the journal announces the horde before it comes" % tag)

# ------------------------------------------------------------------ spoiled supplies: days 43 .. 49 (the growth event of day 45)
for fac, fk in ((clan.WLF, "W"), (clan.SERAPHITES, "S")):
    for seed, mult in ((5, 1.5), (6, 0.9)):
        tag = "%s seed %d" % (fk, seed)
        os.environ.pop("T2R_CLAN_NEW_EVENTS", None)
        c, tid, log = run(fac, (22, 1, 0, 43), 7, seed, mult)
        os.environ["T2R_CLAN_NEW_EVENTS"] = "0"
        c0, tid0, log0 = run(fac, (22, 1, 0, 43), 7, seed, mult)
        os.environ.pop("T2R_CLAN_NEW_EVENTS", None)
        nums = lambda lg: [(e["clan"]["healthy"], e["clan"]["hungry"], e["clan"]["sick"], e["clan"]["day"], e["r"].get("evk"), e["r"].get("evt"), e["r"].get("evg")) for e in lg]
        check(nums(log) == nums(log0), "%s: spoiled supplies moves no number" % tag)
        settled = [e for e in log if e["r"].get("evk") == clan.EV_GROWTH]
        check(len(settled) == 1 and settled[0]["r"].get("evn") == clan.GN_SPOIL and [e["r"].get("evn") for e in log0 if e["r"].get("evk") == clan.EV_GROWTH] == [4],
              "%s: the growth event of day 45 is SPOILED SUPPLIES (off: MARAUDER ATTACK)" % tag)
        je = {int(x["day"]): x for x in CJ.entries(c, tid, "en")}
        jp = {int(x["day"]): x for x in CJ.entries(c, tid, "pl")}
        capd = [d for d, x in je.items() if "SPOILED SUPPLIES" in [cap for cap, _t in x.get("paras", [])]]
        check(len(capd) >= 2, "%s: the journal announces it and settles it under SPOILED SUPPLIES (days %s)" % (tag, sorted(capd)))
        text = " ".join(t for d in capd for _c, t in je[d]["paras"])
        check(re.search(r"spoil|tins?|stores?|store room", text, re.I) and not re.search(r"marauder", text, re.I), "%s: its text is about the spoiled stores, not marauders" % tag)
        check(all("ZEPSUTE ZAPASY" in [cap for cap, _t in jp[d]["paras"]] and "{" not in " ".join(t for _c, t in jp[d]["paras"]) for d in capd), "%s: the same entries in Polish" % tag)

print("\nFAILED: %d" % len(FAILS) if FAILS else "\nall new clan event tests passed")
sys.exit(1 if FAILS else 0)
