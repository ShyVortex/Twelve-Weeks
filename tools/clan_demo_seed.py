"""Seed a THROW-AWAY sqlite database with a real clan story (members, journal, arcs, raids, supplies) for the clan UI demos.
Never point it at the daemon's live t2r.db: it refuses an existing file unless --force (throw-away copy) or --into (adds a clan for a token that has none).

  python tools/clan_demo_seed.py <db path> [--token <24 hex>] [--days 9] [--faction W|S] [--size 17] [--seed 11] [--force | --into]

Uses the same path the daemon uses after a clan day (clan_story.on_day with a result + the match facts), with every clan switch on
(chronicle, saga, status, A-Life). Prints the token id: the launcher / update server read it as  /clan.json?player=<token>  and
daemon op 0xB6 / 0xE0 with a 64-hex token whose last 24 hex digits are this id.
Then:  python tools/update_server/server.py --data <dir> --port 7102 --db <db path>"""
import argparse
import os
import random
import sqlite3
import sys

for k in ("T2R_CLAN_CHRONICLE", "T2R_CLAN_SAGA", "T2R_CLAN_STATUS", "T2R_CLAN_ALIFE"):
    os.environ.setdefault(k, "1")
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import clan                      # noqa: E402
import clan_story as CS          # noqa: E402
import clan_supply               # noqa: E402

MAPS = ["Overpass", "Jackson Suburbs", "Hillside", "Lodge", "Convention Center", "Hospital", "School", "Motel", "Bookstore", "Train Station"]
WEAPONS = ["Bow", "Shotgun", "Revolver", "Pistol", "Rifle", "Shiv", "Melee"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("db")
    ap.add_argument("--token", default="0123456789abcdef01234567")
    ap.add_argument("--days", type=int, default=9)
    ap.add_argument("--faction", default="W")
    ap.add_argument("--size", type=int, default=17)
    ap.add_argument("--seed", type=int, default=11)
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--into", action="store_true", help="add the clan to an EXISTING database (the daemon stopped!): only when the token has no clan row yet, nothing else is touched")
    a = ap.parse_args()
    if os.path.exists(a.db) and not a.force and not a.into:
        sys.exit("refusing to touch an existing file (use a new path, --force for a throw-away copy, or --into to add a clan for a token without one): " + a.db)
    if os.path.exists(a.db) and not a.into:
        os.remove(a.db)
    rng = random.Random(a.seed)
    fac = clan.WLF if a.faction.upper() == "W" else clan.SERAPHITES
    c = sqlite3.connect(a.db)
    clan.ensure(c)
    CS.ensure(c)
    tid = a.token
    if a.into and clan.load(c, tid).get("faction"):
        sys.exit("that token already has a clan in %s: nothing changed" % a.db)
    cl = clan.new_clan(fac)
    h = a.size - 3
    cl.update(healthy=h, hungry=2, sick=1, day=0, status=1)
    clan.save(c, tid, cl)
    CS.on_new_run(c, tid, fac)
    stock = None
    for day in range(1, a.days + 1):
        cl = clan.load(c, tid)
        need = max(3, (cl["healthy"] + cl["hungry"] + cl["sick"]) // 2)
        sup = max(0, int(need * rng.uniform(0.6, 1.5)))
        kills = rng.randrange(2, 16)
        win = rng.random() < 0.55
        parts = sup * 50 + rng.randrange(200)
        stock, sres = clan_supply.book(stock, sup, need, cl["healthy"] + cl["hungry"] + cl["sick"], parts, {1: kills, 3: (a.seed + day) % 3})
        died = 1 if rng.random() < 0.08 else 0
        gained = 1 if rng.random() < 0.2 else 0
        cl["healthy"] = max(3, cl["healthy"] - died + gained)
        cl["day"] = day
        r = {"day": day, "supplies": sup, "needed": need, "parts": parts, "died": died, "gained": gained, "sup": sres,
             "match": {"map": rng.choice(MAPS), "kills": kills, "deaths": rng.randrange(0, 5) + (0 if win else 2), "downs": rng.choice([0, 1, 2, 3]), "win": win,
                       "execs": rng.choice([0, 1, 2]), "revives": rng.choice([0, 1, 2]), "headshots": min(kills, rng.randrange(0, 6)), "weapon": rng.choice(WEAPONS)}}
        cl["last_result"] = __import__("json").dumps(r)
        clan.save(c, tid, cl)
        CS.on_day(c, tid, cl, r)
    c.commit()
    c.close()
    print("seeded %s: clan %s, %d days, token id %s" % (a.db, a.faction.upper(), a.days, tid))


if __name__ == "__main__":
    main()
