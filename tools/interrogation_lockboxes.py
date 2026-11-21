"""Interrogation mode: lockbox candidate positions per map, from the level spawner dumps.

Input: tools/spawns/<pak map>.json (written by tools/spawns/levels.py / dump_json.ps1: every
spawner of a level pak with name, position, rotation). Output (both committed):
  tools/interrogation_lockboxes.json   daemon: number of candidates per map / team (+ positions)
  tools/ext/lockboxes.h                t2r-ext: the positions, indexed like the daemon's MAPS

Rule (re/interrogation.md): a team's lockbox stands in its own half of the map. Candidates are the
level's respawn points (to1-spawn-point-N) that are
  * much closer to the team's intro spawns (centroid of to1-t<team>-intro-spawn-point-1..4) than to
    the enemy's: d_own < 0.8 * d_enemy,
  * at least 4 m from the intro centroid (not on top of the match start pile),
  * at least 3 m from every supply box (hold E at a lockbox must not also open a box),
nearest first, at most 3. No candidate -> the team's intro spawn point 1 (always exists).
The daemon picks one candidate per team per match (random) and tells the clients its index.

SP-section maps (the maps that actually ship; daemon index 8.. = SP_MAPS order) are planned from their NAVMESH by
tools/maps/box_place.py lockboxes (a lockbox is the NR military crate, placed like a supply box: flush against a wall / corner tuck, in a
room of the team's own half, off the main road, >= 10 m from the intro spawns, >= 7 m from respawns, >= 8 m from supply boxes and satchels;
box_place.lockboxes), cached in tools/maps/data/<key>-lockboxes.json (committed; `--replan` recomputes, needs numpy/scipy + the seeds navmeshes).
A map without a navmesh dump (Part I bookstore, downtown, ...) uses the respawn-point rule above on its layout.

  python tools/interrogation_lockboxes.py [spawns dir]     (default: tools/spawns; the base maps 0..6 keep their committed rows)
  python tools/interrogation_lockboxes.py --replan         (re-run the navmesh planner for the SP-section maps first)
"""
import json
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
# daemon MAPS order (tools/daemon.py) -> spawner dump name (tools/spawns/<name>.json)
MAP_PAKS = ["forest", "gas-station", "school", "shipyard", "resort", "seraphite-camp",
            "rescue-jesse-houses", "hospital"]
# index (= daemon MAPS / ext MF_MAPS index) -> (key, source). 7 = the Hospital slot (to1-custom-map-1), now the Ellie ground-floor map
# (T2R_HOSPITAL_OLD=1 hosts keep the old NR hospital: its row below is replaced, Interrogation on that rarely used switch uses the Ellie spots)
SP_ROWS = {7: "hospital-ellie", 12: "train-station", 13: "downtown", 15: "jackson-suburbs", 16: "outpost", 17: "p1-bookstore",
           18: "wilds-houses", 19: "capitol-shops", 20: "into-the-city", 21: "overpass", 22: "chase", 23: "jackson-market", 24: "p1-plaza"}
# base maps 0..6 -> key of their hand placed data/<key>-lockboxes.json (SceneEditor, editor_stock.py); used instead of the generated row when present
BASE_KEYS = ["forest", "gas-station", "school", "shipyard", "resort", "seraphite-camp", "houses"]
LB_MAPS = 25
DATA = os.path.join(HERE, "maps", "data")
MAX_CAND = 6                  # was 3 - Hospital / Capitol Hill have 5-6 hand-placed safes per team
MIN_FROM_INTRO = 4.0
MIN_FROM_BOX = 3.0
OWN_HALF = 0.8


def dist(a, b):
    return math.sqrt(sum((x - y) ** 2 for x, y in zip(a, b)))


def centroid(ps):
    return [sum(p[i] for p in ps) / len(ps) for i in range(3)]


def candidates(spawners):
    """spawners: list of {name, pos} -> [team0 list, team1 list] of (name, pos)."""
    by = {s["name"]: [float(v) for v in s["pos"]] for s in spawners}
    intro = [[by[n] for n in sorted(by) if n.startswith(f"to1-t{t}-intro-spawn-point-")] for t in (0, 1)]
    if not intro[0] or not intro[1]:
        return None
    cen = [centroid(intro[0]), centroid(intro[1])]
    boxes = [p for n, p in by.items() if n.startswith("to1-supplybox-") and "itempos" not in n]
    resp = [(n, p) for n, p in by.items() if n.startswith("to1-spawn-point-")]
    out = []
    for t in (0, 1):
        own, enemy = cen[t], cen[1 - t]
        c = [(dist(p, own), n, p) for n, p in resp
             if dist(p, own) < OWN_HALF * dist(p, enemy) and dist(p, own) >= MIN_FROM_INTRO
             and all(dist(p, b) >= MIN_FROM_BOX for b in boxes)]
        c.sort()
        lst = [(n, [round(v, 3) for v in p]) for _, n, p in c[:MAX_CAND]]
        if not lst:
            n = f"to1-t{t}-intro-spawn-point-1"
            lst = [(n, [round(v, 3) for v in by[n]])]
        out.append(lst)
    return out


def layout_spawners(lay):
    """a maps layout (tools/maps/data/<key>-spawns.json) as the spawner list candidates() reads"""
    out = []
    for t in (0, 1):
        out += [{"name": f"to1-t{t}-intro-spawn-point-{k + 1}", "pos": p["pos"]} for k, p in enumerate(lay[f"intro{t}"])]
    out += [{"name": f"to1-spawn-point-{k + 1}", "pos": p["pos"]} for k, p in enumerate(lay["respawns"])]
    out += [{"name": f"to1-supplybox-{k + 1}", "pos": p["pos"]} for k, p in enumerate(lay["boxes"])]
    return out


def sp_row(key, replan=False):
    """-> ([team 0 cands], [team 1 cands]) of {"name", "pos"[, "yaw_deg"]} for an SP-section map: committed navmesh plan (data/<key>-lockboxes.json),
    else the respawn-point rule on the layout"""
    cache = os.path.join(DATA, f"{key}-lockboxes.json")
    if replan or not os.path.exists(cache):
        sys.path.insert(0, os.path.join(HERE, "maps"))
        plan = None
        try:
            import layoutlib
            if os.path.exists(layoutlib.nav_file(key)):
                import box_place
                spots = box_place.lockboxes(key)[0]
                plan = [[{"name": f"lockbox-{t}-{k}", "pos": s["pos"], "yaw_deg": s["yaw_deg"], "traffic": s["traffic"], "own_path": s["own"],
                          "enemy_path": s["enemy"]} for k, s in enumerate(spots[t])] for t in (0, 1)]
                if not all(plan):
                    plan = None
        except ImportError:
            pass
        if plan is None:
            if os.path.exists(cache):
                return json.load(open(cache))["teams"]
            import layoutlib
            c = candidates(layout_spawners(layoutlib.load_layout(key)))
            plan = [[{"name": n, "pos": p} for n, p in t] for t in c]
        json.dump({"key": key, "method": "navmesh wall/corner crate spots (box_place.lockboxes)" if "yaw_deg" in plan[0][0] else "respawn points of the layout",
                   "teams": plan}, open(cache, "w", newline="\n"), indent=1)
        open(cache, "a", newline="\n").write("\n")
    return json.load(open(cache))["teams"]


def build(spawns_dir, replan=False):
    table = []
    old = {}
    try:
        old = {e["map"]: e for e in json.load(open(os.path.join(HERE, "interrogation_lockboxes.json"), encoding="utf-8"))}
    except (OSError, ValueError):
        pass
    for i, m in enumerate(MAP_PAKS):
        if i in SP_ROWS:
            continue
        path = os.path.join(spawns_dir, m + ".json")
        cand = None
        hp = os.path.join(DATA, f"{BASE_KEYS[i]}-lockboxes.json") if i < len(BASE_KEYS) else ""
        if hp and os.path.exists(hp):
            hd = json.load(open(hp, encoding="utf-8"))
            if hd.get("hand_placed") and all(hd.get("teams", [[], []])):
                table.append({"map": i, "pak": m, "teams": [t[:MAX_CAND] for t in hd["teams"]]})
                continue
        if i in old and not os.path.exists(path):
            table.append(old[i])        # committed row (the base maps' spawner dumps are a gitignored cache of the paks)
            continue
        if os.path.abspath(spawns_dir) == os.path.join(HERE, "spawns"):      # the default dump dir: always checked against the pak
            sys.path.insert(0, os.path.join(HERE, "maps"))
            import layoutlib
            cand = candidates(layoutlib.pool_spawners(m))
        elif os.path.exists(path):
            cand = candidates(json.load(open(path, encoding="utf-8-sig")))
        table.append({"map": i, "pak": m, "teams": [[{"name": n, "pos": p} for n, p in t] for t in cand]
                      if cand else [[], []]})
    for i, key in sorted(SP_ROWS.items()):
        table.append({"map": i, "pak": key, "teams": [t[:MAX_CAND] for t in sp_row(key, replan)]})
    return sorted(table, key=lambda e: e["map"])


def write_header(table, path):
    byidx = {e["map"]: e for e in table}
    lines = ["// generated by tools/interrogation_lockboxes.py - Interrogation lockbox candidates per map",
             "// (daemon MAPS index) and team; the daemon picks the index (reply field box0 / box1). yaw = crate lid side (wall normal), 1000 = unset.",
             "#define LB_MAPS %d" % LB_MAPS, "#define LB_MAX %d" % MAX_CAND,
             "static const struct { int n; float pos[LB_MAX][3]; float yaw[LB_MAX]; } LOCKBOXES[LB_MAPS][2] = {"]
    for i in range(LB_MAPS):
        e = byidx.get(i)
        row = []
        for t in (e["teams"] if e else [[], []]):
            ps = ", ".join("{%.3ff, %.3ff, %.3ff}" % tuple(c["pos"]) for c in t) or "{0}"
            ys = ", ".join("%.5ff" % math.radians(c["yaw_deg"]) if "yaw_deg" in c else "1000.0f" for c in t) or "0"
            row.append("{%d, {%s}, {%s}}" % (len(t), ps, ys))
        lines.append("    {%s},   // %d %s" % (", ".join(row), i, e["pak"] if e else "-"))
    lines.append("};")
    open(path, "w", newline="\n").write("\n".join(lines) + "\n")


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    spawns_dir = args[0] if args else os.path.join(HERE, "spawns")
    table = build(spawns_dir, "--replan" in sys.argv)
    json.dump(table, open(os.path.join(HERE, "interrogation_lockboxes.json"), "w", newline="\n"), indent=1)
    write_header(table, os.path.join(HERE, "ext", "lockboxes.h"))
    for e in table:
        print(e["map"], e["pak"], [len(t) for t in e["teams"]],
              [[c["name"] for c in t] for t in e["teams"]])


if __name__ == "__main__":
    main()
