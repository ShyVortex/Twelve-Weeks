"""Offline test: the layout of every map in the rotation (team starts, respawns, supply boxes) against the 2013-derived rules
(re/maps/layout-rules-2013.md, tools/maps/layout.py validate). Run: python tools/tests/test_map_layouts.py

  - structure / counts / spacing from the committed snapshots (tools/maps/layouts/<key>.json), always
  - every snapshot position is in the map's spawner pak (raw float bytes, as tools/spawns/levels.py finds them)
  - SP-section maps: the snapshot equals tools/maps/data/<key>-spawns.json; generated layouts have 0 errors
  - daemon RESPAWNS (the count winmm picks among) equals the pak's respawn count
  - with the navmesh seeds (re/maps/seeds, gitignored): reachability, sight lines, coverage; hand placed pool maps may not get
    WORSE than their accepted baseline (new warnings / errors fail)
"""
import importlib
import json
import math
import os
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.dirname(HERE)
sys.path.insert(0, TOOLS)
sys.path.insert(0, os.path.join(TOOLS, "maps"))
import layoutlib as L  # noqa: E402
import layoutenv as E  # noqa: E402

FAILS = []
CTX = {}


def check(cond, what):
    print(("ok   " if cond else "FAIL ") + what)
    if not cond:
        FAILS.append(what)


for k in ("T2R_SP_MAPS", "T2R_MAP_POOL", "T2R_MAP", "T2R_MAP_PACKS", "T2R_MAP_PACKS_FILE"):
    os.environ.pop(k, None)
os.environ["T2R_SP_GATE"] = "0"
import daemon  # noqa: E402
d = importlib.reload(daemon)
LEVEL = {k: v[0] for k, v in L.POOL.items()}
for m in json.load(open(L.SPEC, encoding="utf-8"))["maps"]:
    LEVEL.setdefault(m["key"], m["level"])

keys = L.keys_in_rotation()
check(len(keys) >= 12, f"{len(keys)} maps in the rotation: {', '.join(keys)}")
for key in keys:
    sp = os.path.join(L.LAYOUTS, f"{key}.json")
    check(os.path.exists(sp), f"{key}: layout snapshot exists")
    if not os.path.exists(sp):
        continue
    snap = json.load(open(sp))
    lay = snap["layout"]
    n = {k2: len(lay[k2]) for k2 in ("intro0", "intro1", "respawns", "boxes")}
    check(n["intro0"] == 4 and n["intro1"] == 4, f"{key}: 4+4 team start spawns")
    check(snap["max_team"] == L.maxteam(key), f"{key}: snapshot max_team {snap['max_team']} = the map's max_team")
    check(2 * L.maxteam(key) + 4 <= n["respawns"] <= 32, f"{key}: {n['respawns']} respawns for max_team {L.maxteam(key)} (>= {2 * L.maxteam(key) + 4})")
    check(L.RULES["box_min"] <= n["boxes"] <= 12, f"{key}: {n['boxes']} supply boxes (4..12)")
    check(d.RESPAWNS.get(LEVEL[key]) == n["respawns"], f"{key}: daemon RESPAWNS {d.RESPAWNS.get(LEVEL[key])} = {n['respawns']}")
    pak = os.path.join(TOOLS, "features", "levels", f"to1-pvp-{key}-ingame.pak")
    b = open(pak, "rb").read()
    miss = [(nm, i) for nm in ("intro0", "intro1", "respawns", "boxes") for i, p in enumerate(lay[nm])
            if b.find(struct.pack("<3f", *p["pos"])) < 0]
    check(not miss, f"{key}: every snapshot position is in the pak" + (f" (missing {miss[:4]})" if miss else ""))
    if key not in L.POOL:
        data = json.load(open(os.path.join(L.DATA, f"{key}-spawns.json")))
        same = all(data[nm] == lay[nm] for nm in ("intro0", "intro1", "respawns", "boxes"))
        check(same, f"{key}: snapshot = tools/maps/data/{key}-spawns.json")
    err, warn, m = L.check(key, lay, CTX.setdefault(key, L.Ctx(key, lay)) if os.path.exists(L.nav_file(key)) else None, strict=key not in L.POOL)
    nav = os.path.exists(L.nav_file(key))
    ft = key not in L.POOL and "_boxes_before_floortest" in json.load(open(os.path.join(L.DATA, f"{key}-spawns.json")))
    if ft:
        print(f"note {key}: FLOOR TEST build (layout.py floortest): box checks skipped")
    if nav and key not in L.POOL and not ft:
        ctx = CTX.setdefault(key, L.Ctx(key, lay))
        fx = [fb["pos"] for fb in (ctx.spec.get("fixed_boxes") or [])]        # hand-placed F8 marks keep their Y (the floor the placer stood on)
        up = [round(p["pos"][1] - E.snap_y(ctx.grid, p["pos"]), 3) for p in lay["boxes"]
              if not any(abs(p["pos"][0] - f[0]) < 0.05 and abs(p["pos"][2] - f[2]) < 0.05 for f in fx)]
        check(all(abs(u) <= 0.05 for u in up), f"{key}: every box Y within 5 cm of the snapped floor {up}")
        ex = E.box_exclusions(ctx, os.path.join(L.SEEDS, key + ".json"))
        bad = [i + 1 for i, p in enumerate(lay["boxes"]) if any(math.hypot(p["pos"][0] - x, p["pos"][2] - z) < r for x, z, r in ex)]
        check(not bad, f"{key}: no supply box inside a boxcar / vehicle / blocked-off route zone ({len(ex)} zones)" + (f" B{bad}" if bad else ""))
        ints = E.interiors(ctx, os.path.join(L.SEEDS, key + ".json"))
        if ints and ints[0]["area"] >= 150:
            check(any(E.in_interior(ints[0], p["pos"], 1.5) for p in lay["boxes"]), f"{key}: a supply box inside the main interior ({ints[0]['area']:.0f} m2)")
    if ft:
        err = [e for e in err if "box" not in e.lower()]
    if key in L.POOL:
        new = [e for e in err + warn if e not in snap["accepted_errors"] + snap["accepted_warnings"] and "no navmesh seed" not in e]
        check(not new, f"{key}: no rule violation beyond the accepted baseline" + (f" {new}" if new else ""))
    else:
        gen = "LAYOUT-GENERATED" in json.load(open(os.path.join(L.DATA, f"{key}-spawns.json"))).get("_note", "")
        if gen:
            check(not err, f"{key}: generated layout has no rule errors" + (f" {err}" if err else ""))
        else:
            print(f"note {key}: seeded placeholder layout (not generated): {len(err)} rule errors tolerated")
    if not nav:
        print(f"note {key}: no navmesh seed here - sight lines / reachability / coverage not re-checked")

# a stale tools/spawns dump (gitignored cache of the committed pak) can never produce results: pool_spawners re-dumps on a pak hash mismatch
import tempfile
_old_sp = L.SPAWNS
with tempfile.TemporaryDirectory() as _td:
    L.SPAWNS = _td
    _k = next(iter(L.POOL))
    _calls = []
    def _fake(pak, out):
        _calls.append(pak)
        json.dump([{"name": "fresh", "pos": [0, 0, 0], "quat": [0, 0, 0, 1]}], open(out, "w"))
    json.dump([{"name": "stale", "pos": [1, 1, 1], "quat": [0, 0, 0, 1]}], open(os.path.join(_td, _k + ".json"), "w"))
    open(os.path.join(_td, _k + ".json.sha1"), "w").write("deadbeef")
    check(L.pool_spawners(_k, redump=_fake)[0]["name"] == "fresh" and len(_calls) == 1, "stale dump (pak hash mismatch) is re-dumped, not used")
    L.pool_spawners(_k, redump=_fake)
    check(len(_calls) == 1, "up-to-date dump is reused")
    os.remove(os.path.join(_td, _k + ".json.sha1"))
    L.pool_spawners(_k, redump=_fake)
    check(len(_calls) == 2, "dump without a stamp is re-dumped")
L.SPAWNS = _old_sp

print()
print("FAILED: " + "; ".join(FAILS) if FAILS else "all ok")
sys.exit(1 if FAILS else 0)
