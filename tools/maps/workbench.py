"""Remove the single-player WORKBENCH (the crafting / weapon-upgrade bench) from a ported SP map (all collectibles and the
workbench go, but crafting parts / pickups stay).  Generic: works on every key of sp_maps.json.

Where a workbench lives in a SP level:
  - the bench prop itself: a render instance of the level's art pak (`<level>.pak`), asset name '...workbench...' (Overpass: afm-radiotower-workbench.ma
    in afm-scar-island-radiotower), plus its collision triangles in `<level>-phys.pak`;
  - the interaction: a `ConversationPiece` spawner (art `invisible-workbench`, names `workbench-64`, `wat-explore-gas-workbench-1`) in a level's
    -ingame pak - parked at y=-3000 by tools/maps/collectibles.py (COLLECT "SP workbench interaction"), exactly like the collectibles.
  Crafting SUPPLY pickups (rag / alcohol / blade / binding / explosive / canister item-pickup-*) are never touched here.

The prop is removed by the level-edit pipeline (tools/maps/level_edit.py, edits applied at build time):
  python workbench.py scan  <key>...        # list the bench props of the map's levels (level, offset, world box, asset)
  python workbench.py apply <key>...        # write them into sp_maps.json maps[key].edits as "auto": "workbench" (render hidden + the collision triangles inside
                                            # the prop's oriented boxes removed), replacing earlier auto workbench edits; then level_edit.py apply <key> / verify <key>
  python workbench.py apply all             # every map of the spec (the 5 maps: train-station, wilds-houses, capitol-shops, into-the-city, overpass)

Reusable from other tools:  workbench.apply_to_spec(key) -> number of edits written;  workbench.edits(key) -> the edit dicts;  workbench.find(key).
Offline, CPU only (same level-pak reader as level_edit.py): no game, no GPU tool.
"""
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import level_edit as le  # noqa: E402
import ndpak  # noqa: E402

AUTO = "workbench"
# render asset names that are a workbench (not 'benchtop' / 'workbench-lights' shop props: those are plain decoration)
BENCH = re.compile(r"workbench", re.I)
SKIP = re.compile(r"workbench-lights|audio-workbench|part-actor-workbench", re.I)


def levels(key):
    """art levels of the map that have a render pak in the game archives (script / audio / FX levels have none)"""
    return le.map_levels(key)


def find(key, work=None):
    """-> [(level, Instance, asset name)] of every workbench render instance in the map's levels"""
    work = work or os.path.join(le.CACHE, "src")
    out = []
    for lv in levels(key):
        try:
            src = le.fetch(lv, work, None, ("",))
        except SystemExit:
            continue                                    # no render pak for this level (script / const level)
        p = ndpak.Pak(src[""])
        for it in le.find_instances(p):
            names = [n for n, _ in it.names] + ([it.proto.split("/")[-1]] if it.proto else [])
            hit = [n for n in names if BENCH.search(n) and not SKIP.search(n)]
            if hit:
                out.append((lv, it, hit[0]))
    return out


def edits(key, work=None):
    """spec edits (level_edit.py format) removing every workbench prop of the map: render instance hidden, collision triangles inside its oriented boxes removed"""
    res = []
    for lv, it, nm in find(key, work):
        pad = 0.05
        box = [round(float(v) - pad, 3) for v in it.wlo] + [round(float(v) + pad, 3) for v in it.whi]
        res.append({"name": "%s: %s @%#x (%.1f, %.1f, %.1f) - SP workbench removed" % (AUTO, nm, it.pak_off, *[(a + b) / 2 for a, b in zip(it.wlo, it.whi)]),
                    "level": lv, "box": box, "action": "remove",
                    "collision": {"obb_of": ["%#x" % it.pak_off], "margin": 0.05},
                    "render": {"offsets": ["%#x" % it.pak_off]}, "auto": AUTO})
    return res


def apply_to_spec(key, work=None):
    """put the map's workbench edits into sp_maps.json (replacing earlier "auto": "workbench" ones; other edits stay) -> number written"""
    new = edits(key, work)
    d = json.load(open(le.SPEC, encoding="utf-8"))
    m = next(x for x in d["maps"] if x["key"] == key)
    keep = [e for e in m.get("edits", []) if e.get("auto") != AUTO]
    if keep or new:
        m["edits"] = keep + new
    with open(le.SPEC, "w", encoding="utf-8", newline="\n") as f:
        json.dump(d, f, indent=1)
        f.write("\n")
    return len(new)


def main(argv):
    if len(argv) < 3 or argv[1] not in ("scan", "apply"):
        raise SystemExit(__doc__)
    keys = argv[2:]
    if keys == ["all"]:
        keys = [m["key"] for m in json.load(open(le.SPEC, encoding="utf-8"))["maps"] if m.get("build")]
    for key in keys:
        if argv[1] == "scan":
            for lv, it, nm in find(key):
                print("%-12s %-40s @%#x  %s .. %s  %s" % (key, lv, it.pak_off, [round(float(v), 2) for v in it.wlo], [round(float(v), 2) for v in it.whi], nm))
            print("%s: scanned %d level(s)" % (key, len(levels(key))))
        else:
            print("%s: %d workbench edit(s) written" % (key, apply_to_spec(key)))


if __name__ == "__main__":
    main(sys.argv)
