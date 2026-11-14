"""Container loot data: python container_loot.py [--no-dump]  ->  tools/ext/containers.h  (+ a per-map listing on stdout)

Every MP map is a set of single-player level paks. The interactable furniture of those paks (drawers, cabinets, lockers, shelves, caches)
is spawned as `OpenableObject` spawners (SceneEditor PackageReader ProcessType; script ss-t2/ss-openable-drawer / -cabinet, tag
`pre-placed-pickup`, see tools/ext/containers.c). This tool lists them for the pool maps, READ-ONLY and offline:
  1. the map's level list (pool_nav.levels_of: level-sets-test.bin / sp_maps.json) -> the -ingame paks, extracted from the game psarcs
     into re/maps/paks/_pool/ (pool_nav.extract, existing files are kept);
  2. every pak's spawners dumped to JSON with the headless SceneEditor reader (dump_spawners.ps1) next to it;
  3. OpenableObject spawners kept when the nearest respawn / intro / supply box of the map is within MAX_SPAWN_DIST metres (furniture
     in SP rooms the match never uses is dropped);
  4. tools/ext/containers.h: per map-list index (daemon MAPS / ext MF_MAPS) the container name, world position and the pickup lift
     (metres above the spawner origin: on top of low furniture, mid-height inside tall units).
Env: T2R_MAIN_ROOT (default: the repo root: re/gamebin, re/modfs_feat), T2_GAME (game dir). --no-dump: reuse the JSON dumps."""
import json
import math
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.dirname(HERE)
ROOT = os.path.dirname(TOOLS)
MAIN = os.environ.get("T2R_MAIN_ROOT", os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")))
os.environ.setdefault("T2R_GAMEBIN", os.path.join(MAIN, "re", "gamebin"))
sys.path.insert(0, HERE)
sys.path.insert(0, TOOLS)
sys.path.insert(0, os.path.join(TOOLS, "features"))
sys.path.insert(0, os.path.join(TOOLS, "spawns"))
import pool_nav as P  # noqa: E402

DUMP = os.path.join(HERE, "dump_spawners.ps1")
MAX_SPAWN_DIST = 30.0
# map key -> (map-list index = daemon MAPS / ext MF_MAPS, spawn source: pak dump json relative to MAIN)
MAPS = [
    ("forest", 0, "tools/spawns/forest.json"), ("gas-station", 1, "tools/spawns/gas-station.json"),
    ("school", 2, "tools/spawns/school.json"), ("shipyard", 3, "tools/spawns/shipyard.json"),
    ("resort", 4, "tools/spawns/resort.json"), ("seraphite-camp", 5, "tools/spawns/seraphite-camp.json"),
    ("rescue-jesse-houses", 6, "tools/spawns/rescue-jesse-houses.json"), ("hospital", 7, "tools/spawns/hospital.json"),
    ("train-station", 12, "tools/maps/data/train-station-spawns.json"), ("downtown", 13, "tools/maps/data/downtown-spawns.json"),
    ("jackson-suburbs", 15, "tools/maps/data/jackson-suburbs-spawns.json"), ("outpost", 16, "tools/maps/data/outpost-spawns.json"),
    ("wilds-houses", 18, "tools/maps/data/wilds-houses-spawns.json"),
]
# pickup lift above the spawner origin (first match wins): low furniture = its top surface (+ a hand), tall units = mid height inside
LIFT = [
    (r"locker|bookshelf|shelf-system|cabinet-metal-tall|filing-cabinet-tall|bookcase", 1.0),
    (r"nightstand", 0.68), (r"tv-stand", 0.62), (r"desk", 0.85), (r"dresser", 1.0), (r"vanity", 0.92),
    (r"counter", 1.05), (r"kitchen|cab-short|cabinet", 0.98), (r"filing-cabinet", 0.8), (r"cache", 0.3),
    (r"drawer", 0.9),
]


def lift_of(name):
    for rx, v in LIFT:
        if re.search(rx, name):
            return v
    return 0.9


def spawn_points(path):
    if path.startswith("tools/spawns/"):
        import layoutlib
        d = layoutlib.pool_spawners(os.path.basename(path)[:-5])      # pak dump, never stale
    else:
        d = json.load(open(os.path.join(MAIN, path), encoding="utf-8-sig"))
    pts = []
    if isinstance(d, list):
        pts = [p["pos"] for p in d if re.search(r"spawn-point|intro|supplybox", p["name"])]
    else:
        for key in ("intro0", "intro1", "respawns", "boxes"):
            pts += [p["pos"] if isinstance(p, dict) else p for p in d.get(key, [])]
    return pts


def dump(pak):
    js = pak[:-4] + ".json"
    if not os.path.exists(js):
        subprocess.run(["pwsh", "-NoProfile", "-File", DUMP, "-Pak", pak, "-Out", js], check=False)
    if not os.path.exists(js):
        return []
    return json.load(open(js, encoding="utf-8-sig")) or []


def main():
    binsets = P.bin_levels()
    out = {}
    for key, idx, spf in MAPS:
        paks = P.extract(P.levels_of(key, binsets))
        pts = spawn_points(spf)
        cont, dropped = [], []
        for pk in paks:
            for s in dump(pk):
                if s["type"] != "OpenableObject":
                    continue
                d = min(math.hypot(s["pos"][0] - q[0], s["pos"][2] - q[2]) for q in pts)
                (cont if d <= MAX_SPAWN_DIST else dropped).append((s["name"], s["pos"], d))
        cont.sort(key=lambda c: c[0])
        out[key] = (idx, cont)
        print("%-20s idx %2d  %2d containers  (%d dropped: farther than %.0f m from every spawn)" % (key, idx, len(cont), len(dropped), MAX_SPAWN_DIST))
        for n, p, d in cont:
            print("    %-72s %8.2f %7.2f %8.2f  d%3.0f  lift %.2f" % (n, p[0], p[1], p[2], d, lift_of(n)))
        for n, p, d in dropped:
            print("    (dropped) %-62s d%3.0f" % (n, d))
    with open(os.path.join(TOOLS, "ext", "containers.h"), "w", newline="\n") as f:
        f.write("// generated by tools/maps/container_loot.py - interactable containers (OpenableObject spawners of the map's level paks)\n")
        f.write("// per map-list index (daemon MAPS / MF_MAPS); name = the spawner name, pos = its world position, lift = pickup height above it.\n")
        f.write("// Containers farther than %.0f m from every respawn / intro / box of the map are left out (SP rooms the match does not use).\n" % MAX_SPAWN_DIST)
        f.write("typedef struct { const char *name; float p[3]; float lift; } cl_cont_t;\n")
        for key, (idx, cont) in out.items():
            if not cont:
                continue
            f.write("static const cl_cont_t CL_%s[] = {   // map %d (%s)\n" % (key.upper().replace("-", "_"), idx, key))
            for n, p, d in cont:
                f.write('    {"%s", {%.3ff, %.3ff, %.3ff}, %.2ff},\n' % (n, p[0], p[1], p[2], lift_of(n)))
            f.write("};\n")
        f.write("#define CL_NMAPS 19\n")
        f.write("static const struct { const cl_cont_t *c; int n; } CL_MAP[CL_NMAPS] = {\n")
        by_idx = {idx: (key, cont) for key, (idx, cont) in out.items()}
        for i in range(19):
            if i in by_idx and by_idx[i][1]:
                k = by_idx[i][0].upper().replace("-", "_")
                f.write("    [%d] = {CL_%s, %d},   // %s\n" % (i, k, len(by_idx[i][1]), by_idx[i][0]))
        f.write("};\n")
    print("-> tools/ext/containers.h")


if __name__ == "__main__":
    main()
