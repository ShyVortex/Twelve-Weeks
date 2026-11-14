"""Copy ND's own invisible-wall spawners out of the SP levels we do NOT load into a map's props (route C2 of
re/maps/collision-editing.md): the *-script levels (and the neighbour levels next to the play space) hold the walls ND placed to close
this very space for the story beats. We skip those levels (scripts), so the walls are lost; here they come back as plain props.

  python nd_walls.py <key> [--margin 20] [--write]

Reads re/maps/seeds/<key>.json and <key>-nb.json (spawner dumps of the loaded + neighbour levels, sp_maps.py extract / sp_bounds.py),
keeps invisible-block-* / invis-collision* spawners of levels that are NOT in the map's level list and lie inside the bounds
(+ margin). --write puts them into sp_maps.json as props with "nd": true (replaced on every run). Scale is 1: every stock placement
of these actors uses Scale (1, 1, 1) (collision-editing.md section 2; the dumps do not carry the scale).
Walls of LOADED levels are already in the level and are not copied; void-blocker cards of skipped levels are not walls and not copied.
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)
import sp_maps  # noqa: E402

WALL_ARTS = ("invisible-block", "invis-collision", "t2r-invis-collision")


def find(key, margin=20.0):
    m = sp_maps.spec(key)
    loaded = {lv + "-ingame" for lv in m["levels"]}
    b = m.get("bounds") or [-1e9, 1e9, -1e9, 1e9]
    out, seen = [], set()
    cents = []                                   # loaded navmesh polygon centres: a wall must stand on / near the play space's floor
    nfn = os.path.join(ROOT, "re", "maps", "seeds", f"{key}-nav.json")
    if os.path.exists(nfn):
        for polys in json.load(open(nfn, encoding="utf-8-sig")).values():
            for q in polys:
                cents.append((sum(v[0] for v in q) / len(q), sum(v[1] for v in q) / len(q), sum(v[2] for v in q) / len(q)))
    for src in (key, key + "-nb"):
        fn = os.path.join(ROOT, "re", "maps", "seeds", f"{src}.json")
        if not os.path.exists(fn):
            continue
        for p in json.load(open(fn)):
            art = p.get("art") or ""
            if not art.startswith(WALL_ARTS) or p["level"] in loaded:
                continue
            x, y, z = p["pos"]
            if not (b[0] - margin <= x <= b[1] + margin and b[2] - margin <= z <= b[3] + margin):
                continue
            if cents and not any(abs(c[0] - x) < 10 and abs(c[2] - z) < 10 and abs(c[1] - y) < 6.0 for c in cents):
                continue                         # no loaded floor within 10 m / 6 m height (e.g. a wall of the cliff above the beach)
            k = (p["level"], p["name"])
            if k in seen:
                continue
            seen.add(k)
            out.append({"art": art, "pos": [round(v, 3) for v in p["pos"]], "quat": [round(v, 6) for v in p["quat"]],
                        "nd": True, "src": f"{p['level'].replace('-ingame', '')}/{p['name']}"})
    return out


def main():
    a = sys.argv[1:]
    if not a:
        print(__doc__)
        return
    key = a[0]
    margin = float(a[a.index("--margin") + 1]) if "--margin" in a else 20.0
    walls = find(key, margin)
    for w in walls:
        print(f"  {w['art']:30s} {w['pos']}  from {w['src']}")
    print(f"{key}: {len(walls)} ND wall spawners from skipped levels")
    if "--write" in a:
        m = sp_maps.spec(key)
        keep = [p for p in m.get("props", []) if not p.get("nd")]
        sp_maps.save_spec_props(key, keep + walls)


if __name__ == "__main__":
    main()
