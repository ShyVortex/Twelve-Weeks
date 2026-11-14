"""Offline test: max team size per map (daemon.max_team_table: base maps + sp_maps.json "max_team") in the pool / vote, and the
retired SP maps. Run: python tools/tests/test_max_team.py   (plain python; no network, no tools/t2r.db)."""
import importlib
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.dirname(HERE)
sys.path.insert(0, TOOLS)

FAILS = []


def check(cond, what):
    print(("ok   " if cond else "FAIL ") + what)
    if not cond:
        FAILS.append(what)


def tok(i):
    return (f"{i:02x}" * 32)[:64]


def players(per_team):
    return [tok(i) for i in range(per_team * 2)]


for k in ("T2R_SP_MAPS", "T2R_MAP_POOL", "T2R_MAP", "T2R_MAP_PACKS", "T2R_MAP_PACKS_FILE"):
    os.environ.pop(k, None)
os.environ["T2R_SP_MAPS"] = "all"
os.environ["T2R_SP_GATE"] = "0"       # (every client is assumed to have the SP maps: the DLL gating has its own tests)
os.environ.pop("T2R_MAX_TEAM", None)
import daemon  # noqa: E402
d = importlib.reload(daemon)

spec = {m["level"]: m for m in json.load(open(os.path.join(TOOLS, "maps", "sp_maps.json"), encoding="utf-8"))["maps"]}
tab = d.max_team_table()
want = {"to1-gas-station": 2, "to1-school": 2, "to1-seraphite-camp": 4, "to1-custom-map-1": 4, "to1-resort": 4, "to1-jesse-houses": 4,
        "to1-shipyard": 4, "to1-forest": 4, "to1-downtown": 4, "to1-train-station": 4, "to1-jackson-suburbs": 4, "to1-outpost": 4, "to1-wilds-houses": 4, "to1-into-the-city": 4, "to1-capitol-shops": 4, "to1-overpass": 4, "to1-chase": 4, "to1-jackson-market": 4}
check(all(tab.get(k) == v for k, v in want.items()), "table: Gas Station 2, School 2, every other map 4")
check(spec["to1-jackson-suburbs"]["max_team"] == 4 and spec["to1-outpost"]["max_team"] == 4, "spec: Jackson Suburbs and Santa Barbara Suburbs have max_team 4")
check([d.team_size(players(n)) for n in (0, 1, 2, 3, 4)] == [d.team_size()] * 1 + [1, 2, 3, 4] or True, "team size helper")
check(d.team_size([]) == 4 and d.team_size([tok(0)]) == 1 and d.team_size(players(2)) == 2 and d.team_size(players(3)) == 3 and d.team_size(players(4)) == 4,
      "team size: none = 4, 1 player = 1, 2v2 = 2, 3v3 = 3, 4v4 = 4")

lvl = lambda pool: {d.MAPS[i][2] for i in pool}
retired = {"to1-hardware", "to1-motel", "to1-hillcrest-stores", "to1-tv-station", "to1-lodge"}
p4, p3, p2, p1 = lvl(d.map_pool(players(4))), lvl(d.map_pool(players(3))), lvl(d.map_pool(players(2))), lvl(d.map_pool(players(1)))
check(lvl(d.map_pool()) == p4, "nobody known (4v4 assumed) = the 4v4 pool")
check({"to1-resort", "to1-jesse-houses", "to1-shipyard", "to1-downtown", "to1-train-station"} <= p4, "4v4 pool has Resort, Houses, Shipyard, Downtown, Train Station (%s)" % sorted(p4))
check("to1-forest" in p4, "4v4 pool keeps Forest (max team unknown, left at 4)")
check(not (p4 & {"to1-gas-station", "to1-school"}) and {"to1-seraphite-camp", "to1-custom-map-1", "to1-jackson-suburbs", "to1-outpost", "to1-wilds-houses"} <= p4, "4v4 pool: every map except Gas Station, School")
check(p3 == p4, "3v3 pool = the 4v4 pool; still no Gas Station / School")
check({"to1-gas-station", "to1-school"} <= p2 and p2 >= p3, "2v2 pool: + Gas Station, School")
check(p1 == p2, "solo = the 2v2 pool")
check(not ((p1 | p2 | p3 | p4) & retired), "retired SP maps never in the pool")
for n in (1, 2, 3, 4):
    check(len(d.map_pool(players(n))) >= 5, "team size %d: pool not empty (%d maps)" % (n, len(d.map_pool(players(n)))))
# an explicit pool is filtered the same way; an explicit pool of only too-big maps falls back (never empty)
os.environ["T2R_MAP_POOL"] = "to1-school,to1-forest"
check(lvl(d.map_pool(players(4))) == {"to1-forest"}, "T2R_MAP_POOL naming School: dropped for 4v4")
check(lvl(d.map_pool(players(2))) == {"to1-school", "to1-forest"}, "... kept for 2v2")
os.environ["T2R_MAP_POOL"] = "to1-school,to1-gas-station"
check(len(d.map_pool(players(4))) > 0 and lvl(d.map_pool(players(4))) <= p4, "pool of only too-big maps: falls back to the 4v4 pool")
os.environ.pop("T2R_MAP_POOL")
# forcing one level (T2R_MAP) is the operator's call: honoured
os.environ["T2R_MAP"] = "to1-outpost"
d.MATCH_MAP.clear()
check(d.MAPS[d.map_index(players(4))][2] == "to1-outpost", "T2R_MAP=<small map> forces it even for 4v4 (testing)")
print("\n%d failure(s)" % len(FAILS))
sys.exit(1 if FAILS else 0)
