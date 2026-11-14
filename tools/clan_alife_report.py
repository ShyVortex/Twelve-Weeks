"""Offline harness for the clan A-Life: simulate a clan over weeks against the real 2013 rules (tools/clan.py) in a temp database, measure how repetitive the
feed is, and write the readable sample (re/clan-alife-sample-1019.md).  Never touches a live database: real players are read from a COPY (--db) and only
their faction / size / supply profile is used; names in the output are anonymised.

  python tools/clan_alife_report.py sample --db <copy of t2r.db> --out re/clan-alife-sample-1019.md
  python tools/clan_alife_report.py metrics --db <copy of t2r.db>
"""
import argparse
import collections
import json
import os
import random
import re
import sqlite3
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import clan                                                  # noqa: E402
import clan_story as CS                                      # noqa: E402
import clan_alife as AL                                      # noqa: E402


def simulate(faction, start, days, ratio=1.1, seed=1, alife=True, tid="aa" * 12, lang_check=False, hook=None, parts_fn=None, downs=14):
    """Play `days` clan days. start = (healthy, hungry, sick, day). Returns (conn, tid, log); log[i] = dict(day, clan, r, rows (all feed rows of the day,
    newest last), people (alive snapshot [(i, name, state)]), dead (names), morale)."""
    d = tempfile.mkdtemp(prefix="t2r-tmp-alife-")
    c = sqlite3.connect(os.path.join(d, "t.db"))
    old = os.environ.get("T2R_CLAN_ALIFE")
    os.environ["T2R_CLAN_ALIFE"] = "1" if alife else "0"
    try:
        clan.rng = random.Random(seed)
        h, u, s, day0 = start
        clan.ensure(c)
        cl = clan.new_clan(faction)
        cl.update(healthy=h, hungry=u, sick=s, day=day0)
        clan.save(c, tid, cl)
        log = []
        prng = random.Random(seed * 7 + 1)
        last_id = 0
        for i in range(1, days + 1):
            c0 = clan.load(c, tid)
            if c0["status"] != clan.ALIVE:
                break
            need = clan.needed(c0["healthy"] + c0["hungry"] + c0["sick"])
            if parts_fn:
                parts = parts_fn(i, c0, need)
            else:
                wob = prng.uniform(0.55, 1.6)
                parts = int(max(0, need * ratio * wob) * clan.PARTS_PER_SUPPLY)
            meta = clan.meta_of(c0)
            ev = clan.event_window(c0["day"])
            if meta.get("m") and ev >= 0 and meta["m"].get("ev", -1) != ev:     # a practice mission in the event's way: the player re-picks
                meta.pop("m")
                c0["meta"] = json.dumps(meta, separators=(",", ":"))
                clan.save(c, tid, c0)
            rep = meta.get("rep", {})
            mid = min((1, 2, 3, 4, 5), key=lambda k: (rep.get(str(k), 0), k))      # the least-played of the live missions (a player rotates them)
            if not meta.get("m"):
                clan.mission_choose(c, tid, mid)                # CHOOSE MISSION (an event's tier is settled by it)
            running = (clan.meta_of(clan.load(c, tid)).get("m") or {}).get("id", mid)
            new, r = clan.apply_match(c, tid, "m%d" % i, parts, counts={running: downs})
            if not r:
                continue
            CS.on_day(c, tid, new, r)
            st = CS._load(c, tid)
            rows = [dict(zip(("id", "day", "week", "kind", "mood", "text", "lid", "params"), x)) for x in
                    c.execute("SELECT id,day,week,kind,mood,text,lid,params FROM clan_feed WHERE token_id=? AND id>? ORDER BY id", (tid, last_id))]
            if rows:
                last_id = rows[-1]["id"]
            ent = {"day": int(new["day"]), "clan": new, "r": r, "rows": rows, "people": [(p["i"], p["n"], p["s"]) for p in st["people"]],
                   "dead": [x["n"] for x in st["dead"]], "morale": st["morale"], "st": json.loads(json.dumps(st))}
            log.append(ent)
            if hook:
                hook(c, tid, ent)
            if new["status"] != clan.ALIVE:
                break
        return c, tid, log
    finally:
        if old is None:
            os.environ.pop("T2R_CLAN_ALIFE", None)
        else:
            os.environ["T2R_CLAN_ALIFE"] = old


def skeleton(text):
    """A line without names / numbers, to measure how repetitive the wording is."""
    t = re.sub(r"\b[A-Z][a-z]+(?: [A-Z][a-z]+)?\b(?=[ ,.'’:;!?])", "N", text)
    return re.sub(r"\d+", "#", t)


def menu_sample(c, tid, days_log, sessions_per_day=12, lang="en"):
    """The lines a player sees in the menu: per clan day `sessions_per_day` one-minute slots x 6 lines (the game asks every 45-60 s). Returns [(day, text)]."""
    out = []
    for ent in days_log:
        base = 1_700_000_000 + ent["day"] * 86400
        for k in range(sessions_per_day):
            for _id, t in CS.menu_lines(c, tid, 6, lang, base + k * 60, save=False):
                out.append((ent["day"], t))
    return out


def repeat_stats(items, window_days=28):
    """items = [(day, text)] in order. Returns total, distinct, share of lines whose exact text was already shown within window_days, share whose skeleton was,
    the maximum times one text was shown."""
    seen, seen_sk = {}, {}
    rep = rep_sk = 0
    cnt = collections.Counter()
    for day, t in items:
        sk = skeleton(t)
        if t in seen and day - seen[t] <= window_days:
            rep += 1
        if sk in seen_sk and day - seen_sk[sk] <= window_days:
            rep_sk += 1
        seen[t] = day
        seen_sk[sk] = day
        cnt[t] += 1
    n = len(items) or 1
    return {"total": len(items), "distinct": len(cnt), "repeatShare": round(rep / n, 3), "skeletonRepeatShare": round(rep_sk / n, 3),
            "maxShown": max(cnt.values()) if cnt else 0}


def day_repeat_stats(items, window_days=28):
    """items = [(day, text)]: the repeat rate by DAY - per day only the distinct lines count, and a line counts as a repeat when it was already shown on an
    EARLIER day inside the window (a ticker that shows its lines several times a day is no problem; the same line again tomorrow is the boredom)."""
    by_day = collections.OrderedDict()
    for day, t in items:
        by_day.setdefault(day, [])
        if t not in by_day[day]:
            by_day[day].append(t)
    last, last_sk = {}, {}
    n = rep = rep_sk = 0
    for day, lines in by_day.items():
        today, today_sk = {}, {}
        for t in lines:
            n += 1
            sk = skeleton(t)
            if t in last and day - last[t] <= window_days:
                rep += 1
            if sk in last_sk and day - last_sk[sk] <= window_days:
                rep_sk += 1
            today[t] = day
            today_sk[sk] = day
        last.update(today)
        last_sk.update(today_sk)
    return {"distinctPerDay": n, "repeatShare": round(rep / max(1, n), 3), "skeletonRepeatShare": round(rep_sk / max(1, n), 3)}


def real_profiles(db_path):
    """(faction, healthy, hungry, sick, day, supply ratio) of the real clans in a DB copy, newest first; ratios from last_result."""
    c = sqlite3.connect("file:%s?mode=ro" % os.path.abspath(db_path).replace("\\", "/"), uri=True)
    try:
        out = []
        for fac, h, u, s, day, lr in c.execute("SELECT faction,healthy,hungry,sick,day,last_result FROM clans WHERE status=1 AND faction IN (1,2) ORDER BY updated DESC"):
            try:
                r = json.loads(lr or "{}")
                ratio = (r.get("supplies", 0) / r["needed"]) if r.get("needed") else 1.1
            except (ValueError, TypeError):
                ratio = 1.1
            out.append((fac, h, u, s, day, max(0.7, min(1.6, ratio))))
        return out
    finally:
        c.close()


def real_feed_stats(db_path):
    """How repetitive the stored clan feed of the REAL players is (read-only copy of the DB): per player the rows, the distinct texts, the distinct template ids (lid) and the
    share of rows whose template was already used earlier in the same week / in an earlier week of the player's feed."""
    c = sqlite3.connect("file:%s?mode=ro" % os.path.abspath(db_path).replace("\\", "/"), uri=True)
    try:
        out = []
        toks = [r[0] for r in c.execute("SELECT token_id FROM clan_feed GROUP BY token_id ORDER BY COUNT(*) DESC")]
        for k, tok in enumerate(toks):
            rows = c.execute("SELECT week,text,lid,kind FROM clan_feed WHERE token_id=? ORDER BY id", (tok,)).fetchall()
            seen, rep_week, rep_before, per_week = {}, 0, 0, collections.Counter()
            seen_text = collections.Counter()
            for week, text, lid, kind in rows:
                key = lid or text
                per_week[week] += 1
                if key in seen:
                    if seen[key] == week:
                        rep_week += 1
                    else:
                        rep_before += 1
                seen[key] = week
                seen_text[text] += 1
            out.append({"player": "Player %s" % chr(65 + k), "rows": len(rows), "distinctTexts": len(seen_text), "distinctTemplates": len({(lid or t) for _w, t, lid, _k in rows}),
                        "repeatedTemplateSameWeek": rep_week, "repeatedTemplateEarlierWeek": rep_before, "weeks": len(per_week),
                        "maxRowsPerWeek": max(per_week.values()) if per_week else 0})
        return out
    finally:
        c.close()


def sim_pair(fac, start, days, seed, parts_fn=None, ratio=1.1):
    """The same clan history twice (A-Life OFF, ON): feed rows and the menu of every day. Returns {mode: dict(feed, menu, log)}."""
    res = {}
    for mode in (False, True):
        menu = []

        def hook(c, tid, ent, menu=menu):
            base = 1_700_000_000 + ent["day"] * 86400
            for k in range(12):
                for _id, t in CS.menu_lines(c, tid, 6, "en", base + k * 60, save=False):
                    menu.append((ent["day"], t))
        c, tid, log = simulate(fac, start, days, ratio, seed=seed, alife=mode, parts_fn=parts_fn, hook=hook)
        feed = [(e["day"], r["text"]) for e in log for r in e["rows"]]
        res[mode] = {"feed": feed, "menu": menu, "log": log, "conn": c, "tid": tid}
    return res


def metrics(db, days):
    prof = real_profiles(db)
    print("REAL FEED (read-only DB copy)")
    for r in real_feed_stats(db):
        print("  ", r)
    print("SIMULATED, %d clan days, the real clans' profiles (A-Life OFF -> ON)" % days)
    rows = []
    for k, (fac, h, u, s, day, ratio) in enumerate(prof[:8]):
        def pol(i, c0, need, ratio=ratio):
            return int(need * clan.PARTS_PER_SUPPLY * (ratio + (0.35 if i % 7 not in (3, 4) else -0.25)))
        pr = sim_pair(fac, (max(h, 3), u, s, day), days, 100 + k, parts_fn=pol)
        line = {"player": "Player %s" % chr(65 + k), "faction": "WLF" if fac == clan.WLF else "SERAPHITES", "size": h + u + s}
        for mode, name in ((False, "off"), (True, "on")):
            line[name] = {"feed": repeat_stats(pr[mode]["feed"]), "menuDay": day_repeat_stats(pr[mode]["menu"])}
            pr[mode]["conn"].close()
        rows.append(line)
        print(json.dumps(line))
    return rows


def _day_header(e):
    r = e["r"]
    cl = e["clan"]
    wk, dw = clan.week_day(e["day"] - 1)
    return "**Day %d** (week %d, day %d) &middot; clan %d healthy / %d hungry / %d sick &middot; supplies %d of %d needed &middot; morale %d" % (
        e["day"], wk, dw, cl["healthy"], cl["hungry"], cl["sick"], r.get("supplies", 0), r.get("needed", 0), e["morale"])


def sample(db, out, days):
    """re/clan-alife-sample-1019.md: 4 weeks of three real players' clan profiles (names anonymised) in both factions, EN + PL."""
    prof = real_profiles(db)
    picks = []
    for p in sorted(prof, key=lambda p: -(p[1] + p[2] + p[3])):          # three different sizes: a big (<= 45), a middle, a small clan
        if len(picks) < 3 and p[1] + p[2] + p[3] <= 45 and all(abs((p[1] + p[2] + p[3]) - (q[1] + q[2] + q[3])) >= 6 for q in picks):
            picks.append(p)
    while len(picks) < 3:
        picks.append(prof[len(picks) % len(prof)])
    L = ["# Clan A-Life sample, 4 weeks, three players, both factions (EN + PL)", "",
         "Generated by `python tools/clan_alife_report.py sample --db <copy of t2r.db> --out re/clan-alife-sample-1019.md` (tools/clan_alife_report.py). The three players' clans are real "
         "profiles read from a READ-ONLY COPY of the live database (faction mix, clan size, how well they feed it); names of players and tokens are not used anywhere - the survivors' "
         "names are the generator's own (2013 list + extras). Each player's clan is played through the real 2013 rules (tools/clan.py) for 28 clan days in BOTH factions, with the "
         "A-Life switch on: every row below is exactly what `clan_feed` would hold for that player (the diary of tools/clan_story.py, marked `diary`, and the A-Life rows, marked "
         "`A-LIFE`). The Polish line under each row is what a player on the Polish text sees. The numbers in the day header are the authoritative clan numbers; no A-Life row "
         "changes them.", ""]
    for k, (fac0, h, u, s, day, ratio) in enumerate(picks):
        name = "Player %s" % chr(65 + k)
        for fac, fname in ((clan.WLF, "WLF"), (clan.SERAPHITES, "Seraphites")):
            def pol(i, c0, need, ratio=min(ratio, 1.15)):          # a decent week with a lean stretch in it (days 4-5 of every 7)
                return int(need * clan.PARTS_PER_SUPPLY * (ratio + (0.1 if i % 7 not in (3, 4) else -0.4)))
            c, tid, log = simulate(fac, (max(h, 4), u, s, day), days, ratio, seed=500 + k * 7 + (0 if fac == clan.WLF else 1), alife=True, parts_fn=pol, tid="%02x" % (k + 1) * 12)
            L += ["", "## %s as %s (clan of %d at the start, week %d)" % (name, fname, max(h, 4) + u + s, clan.week_day(day)[0]), ""]
            for e in log:
                L += [_day_header(e), ""]
                for r in e["rows"]:
                    en = r["text"]
                    try:
                        pl = CS.render_msg(r["lid"], json.loads(r["params"]), "pl") if r["lid"] and r["params"] else None
                    except Exception:                                                       # noqa: BLE001
                        pl = None
                    tag = "A-LIFE" if r["kind"] == "alife" else "diary"
                    L.append("- `%s` %s" % (tag, en))
                    L.append("  - PL: %s" % (pl or "(no Polish form)"))
                L.append("")
            os.environ["T2R_CLAN_ALIFE"] = "1"
            try:
                menu_en = CS.menu_lines(c, tid, 6, "en", 1_700_000_000, save=False)
                menu_pl = CS.menu_lines(c, tid, 6, "pl", 1_700_000_000, save=False)
            finally:
                os.environ.pop("T2R_CLAN_ALIFE", None)
            L += ["### The in-game menu / launcher ticker on the last day (6 lines, EN then PL)", ""]
            L += ["- %s" % t for _i, t in menu_en] + [""] + ["- %s" % t for _i, t in menu_pl] + [""]
            os.environ["T2R_CLAN_ALIFE"] = "1"
            try:
                rs = AL.read_state(c, tid, "en")
            finally:
                os.environ.pop("T2R_CLAN_ALIFE", None)
            L += ["### What the simulation is tracking at the end (what the admin site shows)", ""]
            L += ["- %s" % t["text"] for t in rs.get("threads", [])] or ["- (no storyline running)"]
            L += ["- %d survivors with traits / pasts / bonds; %d remembered; templates used %d of %d, window repeats %d" % (len(rs["people"]), len(rs["memorial"]),
                                                                                                                         rs["stats"]["templatesUsed"], rs["stats"]["templatesTotal"], rs["stats"]["windowRepeats"]), ""]
            c.close()
    with open(out, "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(L) + "\n")
    print("wrote", out, "(%d lines)" % len(L))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("what", choices=("sample", "metrics"))
    ap.add_argument("--db", required=True)
    ap.add_argument("--out", default="")
    ap.add_argument("--days", type=int, default=28)
    a = ap.parse_args()
    if a.what == "metrics":
        metrics(a.db, a.days)
    else:
        sample(a.db, a.out, a.days)


if __name__ == "__main__":
    main()
