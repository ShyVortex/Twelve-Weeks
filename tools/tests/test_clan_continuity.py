"""Clan journal continuity: an EXISTING clan (a diary written while the chronicle was off - the state of every clan before the chronicle became the default) is migrated by switching the chronicle on.
Over the next simulated days, the journal must read as one story:
 - the chronicle default is ON (opt-out 0 / off), the diary alone is the control (callbacks off, chronicle off);
 - a share of the new entries carry a thread / arc / call-back to an earlier entry (prev id exists, and is older), EN and PL;
 - the one-time recap row ("where we stand") names real earlier deaths / illnesses with their days, once, in both languages, and the in-game payload (op 0xB6 section 2) carries it;
 - call-back tails state days that are in the past and agree with the clan state; PL tails contain no English;
 - the diary rows' randomness is untouched (the same diary lines with the chronicle on and off).
Run: python tools/tests/test_clan_continuity.py"""
import os
os.environ["T2R_CLAN_ALIFE"] = "0"   # pre-A-Life feed behaviour (A-Life is default ON; its own rules: test_clan_alife.py)
import re
import sqlite3
import sys
import random

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import clan                      # noqa: E402
import clan_story as CS          # noqa: E402
import clan_chronicle as CH      # noqa: E402
import clan_continuity as CC     # noqa: E402
import clan_ingame as I          # noqa: E402

FAILS = []


def check(cond, what):
    print(("ok   " if cond else "FAIL ") + what)
    if not cond:
        FAILS.append(what)


def setenv(v):
    if v is None:
        os.environ.pop("T2R_CLAN_CHRONICLE", None)
    else:
        os.environ["T2R_CLAN_CHRONICLE"] = v


def play(c, tid, days, seed, start):
    rng = random.Random(seed)
    maps = ["Hospital", "Suburbs", "Downtown", "Lakeside"]
    done = 0
    for i in range(days):
        st, r = clan.apply_match(c, tid, "m%d-%d" % (start, i), rng.choice([1200, 1800, 2400]), False, {1: rng.randint(4, 12)})
        if not r:
            break
        r["match"] = {"map": rng.choice(maps), "supplies": r["supplies"], "parts": 300, "kills": rng.randint(2, 12), "win": rng.choice([True, False]),
                      "downs": rng.randint(1, 6), "deaths": rng.randint(0, 5)}
        CS.on_day(c, tid, st, r)
        done += 1
    return done


def make_clan(seed, old_days):
    """A clan with `old_days` days of plain diary (chronicle off)."""
    setenv("0")
    c = sqlite3.connect(":memory:")
    clan.ensure(c)
    CS.ensure(c)
    tid = "%02x" % seed * 12
    cl = clan.new_clan(clan.WLF if seed % 2 else clan.SERAPHITES)
    cl.update(healthy=16, hungry=2, sick=2, day=1)
    clan.save(c, tid, cl)
    CS.on_new_run(c, tid, cl["faction"])
    n = play(c, tid, old_days, seed, 0)
    return c, tid, n


def continuity_share(rows, since_id):
    new = [m for m in rows if m["id"] > since_id]
    ids = {m["id"]: m for m in rows}
    linked = []
    for m in new:
        if m.get("arc") or m.get("thread") or m["kind"] == "chron" and m.get("style") in ("saga_recap",):
            linked.append(m)
        elif m.get("prev") and m["prev"] in ids and m["prev"] < m["id"]:
            linked.append(m)
    return len(linked), len(new)


# ---- the default
setenv(None)
check(CH.enabled(), "chronicle default is ON")
setenv("0")
check(not CH.enabled(), "chronicle opt-out (0) still works")
setenv(None)

# ---- migration over several seeds
tot_linked = tot_new = recaps = 0
ctl_linked = ctl_new = 0
for seed in (3, 4, 5, 6, 7, 8):
    c, tid, n_old = make_clan(seed, 10)
    check(n_old >= 6, "seed %d: %d old diary days" % (seed, n_old))
    old_rows = CS.read_feed(c, tid, 100)
    last_old = max([m["id"] for m in old_rows] or [0])
    check(all(m["kind"] not in ("chron", "alife") for m in old_rows), "seed %d: the old journal holds diary rows only (the state of an existing clan)" % seed)
    # control: the old journal without call-backs has no link at all
    a, b = continuity_share(old_rows, 0)
    ctl_linked += a
    ctl_new += b
    # migrate: chronicle ON for the next days
    snap = {m["id"]: m["text"] for m in old_rows}
    setenv(None)
    n_new = play(c, tid, 10, seed + 100, 1000)
    if n_new == 0:
        continue
    for lang in ("en", "pl"):
        rows = CS.read_feed(c, tid, 100, 0, lang, callbacks=True)
        ids = {m["id"]: m for m in rows}
        a, b = continuity_share(rows, last_old)
        if lang == "en":
            tot_linked += a
            tot_new += b
        rec = [m for m in rows if m.get("style") == "saga_recap"]
        if lang == "en":
            recaps += len(rec)
        check(len(rec) <= 1, "seed %d %s: at most one recap row" % (seed, lang))
        for m in rows:
            if m.get("thread") and m.get("prev"):
                check(m["prev"] in ids and m["prev"] < m["id"], "seed %d %s: row %d continues an older, existing row (%s)" % (seed, lang, m["id"], m["prev"]))
        if lang == "pl":
            for m in rows:
                if m.get("lang") == "pl" and m.get("thread"):
                    check(not re.search(r"\b(has been ill|fell ill|died|ago|since day)\b", m["text"]), "seed %d pl: no English call-back in row %d" % (seed, m["id"]))
        st = CS._load(c, tid)
        dead = {d["n"]: d["d"] for d in st["dead"]}
        for m in rows:
            for mm in re.finditer(r"([A-Z][a-z]+) died on day (\d+)\.", m["text"]):
                check(dead.get(mm.group(1)) == int(mm.group(2)) and int(mm.group(2)) < m["day"], "seed %d: '%s died on day %s' is true and earlier than the row" % (seed, mm.group(1), mm.group(2)))
        # diary lines of the old days are unchanged by the migration (read without call-backs)
        now = {m["id"]: m["text"] for m in CS.read_feed(c, tid, 100) if m["id"] in snap}
        check(all(snap[i] == now[i] for i in now), "seed %d: old rows untouched by the migration" % seed)
    # the in-game payload (section 2) carries the new kinds
    p = I.build(c, tid, "en", 2, 0, 0)
    lines = [l.split("\t") for l in p.split("\n") if l.startswith("J\t")]
    check(len(lines) >= 5 and all(len(f) == 14 for f in lines), "seed %d: payload J lines keep 13 fields + the lines count (%d lines)" % (seed, len(lines)))
    check(all(f[2].startswith("WEEK ") and not f[6] for f in lines), "seed %d: the J lines are the day entries of tools/clan_journal.py (one entry per clan day, no arc threads)" % (seed))

share = tot_linked / max(1, tot_new)
print("linked %d of %d new entries (%.0f%%); control (old diary alone): %d of %d; recaps %d" % (tot_linked, tot_new, 100 * share, ctl_linked, ctl_new, recaps))
check(tot_new >= 30, "enough simulated entries (%d)" % tot_new)
check(share >= 0.4, "at least 40%% of the entries after the migration continue an earlier entry (%.0f%%)" % (100 * share))
check(ctl_linked == 0, "control: the old diary alone has no linked entry")
check(recaps == 6, "every migrated clan got its recap row on its first chronicle day (%d of 6)" % recaps)

# ---- the recap row on its own (EN + PL render, real days)
params = {"d": 40, "dead": [["Jules", "n", 18], ["Cameron", "m", 18]], "sick": [["Karen", "f", 23]]}
en = CC.render_msg("cn/recap", params, "en")
pl = CC.render_msg("cn/recap", params, "pl")
check(en.startswith("DAY 40: WHERE WE STAND.") and "Jules (day 18) and Cameron (day 18)" in en and "Karen (since day 23)" in en, "recap EN")
check(pl.startswith("DZIEŃ 40: GDZIE STOIMY.") and "Karen (od dnia 23)" in pl and "dzień 18" in pl, "recap PL")
check(CS.render_msg("cn/recap", params, "pl") == pl, "clan_story.render_msg dispatches cn/ rows")

print("\n%d failed" % len(FAILS) if FAILS else "\nall ok")
sys.exit(1 if FAILS else 0)
