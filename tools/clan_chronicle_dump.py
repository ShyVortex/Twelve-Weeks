"""Prints a sample week (or more) of the clan chronicle for a fake clan, EN or PL, so the feed can be read as a whole.

  python tools/clan_chronicle_dump.py [--faction W|S] [--days 7] [--lang en|pl|both] [--seed 1] [--size 14] [--out file.md]

Fake clan: a roster from clan_story, random real-style day results (supplies vs need, a death now and then, a sick one, a newcomer) and a fake match per day
(map, kills, deaths, downs).  Nothing here touches a database.
"""
import argparse
import os
import random
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import clan                                                  # noqa: E402
import clan_story as CS                                      # noqa: E402
import clan_chronicle as CH                                  # noqa: E402

MAPS = ["Train Station", "Hillside", "Overpass", "Hospital", "School", "Bookstore", "Forest", "Gas Station", "Shipyard", "Resort", "Houses", "Motel", "Downtown", "Lodge",
        "TV Station", "Hardware Store", "Jackson Suburbs", "Capitol Hill Shops", "Convention Center", "Seraphite Camp"]
WEAPONS = ["bow", "revolver", "shorty", "hunting", "semi", "burst", "pistol", "crossbow", "melee"]


def fake_week(faction, days, seed, size, death=0.15):
    rng = random.Random(seed)
    st = CS.new_state("dump%d" % seed, clan.WLF if faction == "W" else clan.SERAPHITES)
    CS._populate(rng, st, size - 3, 2, 1, 0)
    rows_by_day = []
    for day in range(1, days + 1):
        need = max(3, len(st["people"]) // 2)
        sup = max(0, int(need * rng.uniform(0.5, 1.6)))
        died = 1 if rng.random() < death and len(st["people"]) > 6 else 0
        gained = 1 if rng.random() < 0.2 else 0
        for _ in range(died):
            CS._remove(st, CS._kill_pick(rng, st), day, "illness")
        for _ in range(gained):
            st["people"].append(CS.new_person(rng, st, state="h", join_day=day))
        for p in st["people"]:                                   # a little churn of states
            if rng.random() < 0.05:
                p["s"] = rng.choice("hus")
        st["day"] = day
        st["morale"] = max(5, min(95, st["morale"] + (6 if sup >= need else -7)))
        cnt = {s: sum(1 for p in st["people"] if p["s"] == s) for s in "hus"}
        newc = {"day": day, "healthy": cnt["h"], "hungry": cnt["u"], "sick": cnt["s"]}
        r = {"day": day, "supplies": sup, "needed": need, "parts": sup * 50 + rng.randrange(200), "died": died, "gained": gained}
        kills = rng.randrange(0, 18)
        win = rng.random() < 0.55
        import clan_supply
        st["_stock"], r["sup"] = clan_supply.book(st.get("_stock"), sup, need, len(st["people"]), r["parts"], {1: kills, 3: (seed + day) % 3})   # supplies per category (the daemon does it in clan.apply_match)
        match = {"map": rng.choice(MAPS), "kills": kills, "deaths": rng.randrange(0, 6) + (0 if win else 2), "downs": rng.choice([0, 0, 1, 2, 3, 4]), "win": win,
                 "execs": rng.choice([0, 0, 0, 1, 2, 3]), "revives": rng.choice([0, 0, 1, 2, 3]), "headshots": min(kills, rng.randrange(0, 8)),
                 "weapon": rng.choice(WEAPONS), "streak": rng.randrange(0, max(1, kills))}
        st.setdefault("_snaps", {})[day] = {q["n"] for q in st["people"]} | {q["n"] for q in st["dead"]}
        away_names = {q["n"] for q in st["people"] if str(q["i"]) in (st.get("ch") or {}).get("away", {})}
        rows_day = CH.day_rows(st, newc, r, match, rng=random.Random(seed * 100 + day))
        st.setdefault("_away", {})[day] = away_names
        st.setdefault("_alive", {})[day] = {q["n"] for q in st["people"]}
        st.setdefault("_act", {})[day] = len(st["ch"]["arcs"])
        rows_by_day.append((day, newc, r, match, rows_day))
    return st, rows_by_day


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--faction", default="W")
    ap.add_argument("--days", type=int, default=7)
    ap.add_argument("--lang", default="both")
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--size", type=int, default=14)
    ap.add_argument("--grim", action="store_true", help="more real deaths, so the dark branches of the arcs show")
    ap.add_argument("--out")
    a = ap.parse_args()
    st, days = fake_week(a.faction, a.days, a.seed, a.size, 0.4 if a.grim else 0.15)
    fk = a.faction
    L = ["# Clan chronicle sample (%s, %d days, seed %d)\n" % ("WLF" if fk == "W" else "Seraphites", a.days, a.seed)]
    L.append("## Roster at the end of the week (people who died or joined during it appear in the days they lived)\n")
    for p in st["people"]:
        L.append("- **%s** - %s" % (p["n"], CH.tagline(p, st["people"], fk, "en", st)))
        if a.lang in ("pl", "both"):
            L.append("  - PL: " + CH.tagline(p, st["people"], fk, "pl", st))
    L.append("")
    for day, newc, r, m, rows in days:
        L.append(("## Day %d - %s (%s): %d down, %d executions, %d revives, %d headshots, you died %d and went down %d times; supplies %d of %d, parts %d" + chr(10)) % (
            day, m["map"], "won" if m["win"] else "lost", m["kills"], m["execs"], m["revives"], m["headshots"], m["deaths"], m["downs"], r["supplies"], r["needed"], r["parts"]))
        for row in rows:
            if a.lang in ("en", "both"):
                L.append("- " + row["text"])
            if a.lang in ("pl", "both"):
                L.append(("  - PL: " if a.lang == "both" else "- ") + CH.render_msg(row["lid"], row["params"], "pl"))
        L.append("")
    arcs = {}
    for dn, _nc, _r, _m, rows in days:
        for row in rows:
            if row["lid"].startswith("arc/"):
                arcs.setdefault(row["params"]["a"], []).append((dn, row))
    if arcs:
        L.append("## Story arcs (threads)\n")
        for aid, steps in arcs.items():
            L.append("### %s - %s (%d steps)\n" % (aid, steps[0][1]["lid"][4:].split(".")[0].upper(), len(steps)))
            for dn, row in steps:
                L.append("- " + row["text"])
                if a.lang in ("pl", "both"):
                    L.append("  - PL: " + CH.CS.render_msg(row["lid"], row["params"], "pl"))
            L.append("")
    inv, keep = CH.inventory(st, "en")
    L.append("## On hand at the end\n\n- supplies: %s\n- keepsakes: %s\n" % (", ".join(inv) or "none", ", ".join(keep) or "none"))
    text = "\n".join(L)
    if a.out:
        open(a.out, "w", encoding="utf-8").write(text)
    else:
        sys.stdout.buffer.write(text.encode("utf-8"))


if __name__ == "__main__":
    main()
