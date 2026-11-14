"""Team 0 <-> team 1 intro separation of the ported SP maps on the REAL collision (the two intro groups were pretty much across each other).

  python intro_sight.py check [<key>...|all] [--write]   # straight distance, nav path distance, sight lines head -> head (all 4 x 4 pairs, eye 1.6 m) over the
                                                         # map's collision triangles + placed props; --write stores tools/maps/data/intro-sight.json
  python intro_sight.py candidates <key> <team>          # ground spots far from the other team and out of its sight (for moving a start)

  python intro_sight.py move <key> <team> <x> <z> [--apply]   # re-fit a team start around (x, z) with spawn_intro's intro rules, keep the best fit that the
                                                         # other team cannot see; --apply writes data/<key>-spawns.json (then sp_maps.py pak <key>, layout.py snapshot <key>)

Rule (tools/tests/test_spawn_intro.py): straight distance >= MIN_STRAIGHT, no pair of intro spawns of the two teams sees each other.
Needs the level-edit cache (re/maps/level-edit-cache, main checkout) for the collision; the committed snapshot intro-sight.json is what the test
checks when the cache is absent (it records the positions it was computed for, a moved intro makes it stale = test failure).
"""
import json
import math
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import reach_check as RC  # noqa: E402

DATA = os.path.join(HERE, "data")
SNAP = os.path.join(DATA, "intro-sight.json")
KEYS = ["capitol-shops", "wilds-houses", "into-the-city", "train-station", "overpass", "chase"]
MIN_STRAIGHT = 60.0          # m between the two team centres (maps are 80-120 m long)
EYE = 1.6
# collision that does not stop a bullet / the eye: none removed here, every triangle of the map's levels counts (water is already left out by level_tris)


def load(key):
    m = RC.spec(key)
    b = m["bounds"]
    box = [b[0] - 18, b[1] + 18, b[2] - 18, b[3] + 18]
    T, used = RC.level_tris(key, box)
    P, _ = RC.prop_tris(m.get("props", []))
    return np.concatenate([T, P]) if len(P) else T


def seg_hits(T, a, b):
    """True when the segment a -> b crosses any triangle of T (n, 3, 3) (Moller-Trumbore, vectorised over the triangles whose box meets the segment)"""
    a, b = np.array(a, float), np.array(b, float)
    lo, hi = np.minimum(a, b) - 0.01, np.maximum(a, b) + 0.01
    sel = ((T.max(1) >= lo) & (T.min(1) <= hi)).all(1)
    if not sel.any():
        return False
    t = T[sel]
    d = b - a
    e1, e2 = t[:, 1] - t[:, 0], t[:, 2] - t[:, 0]
    p = np.cross(d, e2)
    det = (e1 * p).sum(1)
    ok = np.abs(det) > 1e-12
    inv = np.where(ok, 1.0 / np.where(ok, det, 1.0), 0.0)
    s = a - t[:, 0]
    u = (s * p).sum(1) * inv
    q = np.cross(s, e1)
    v = (q * d).sum(1) * inv
    tt = (q * e2).sum(1) * inv
    return bool((ok & (u >= 0) & (v >= 0) & (u + v <= 1) & (tt > 1e-4) & (tt < 1 - 1e-4)).any())


def head(p):
    return (p[0], p[1] + EYE, p[2])


def report(key, T=None):
    sp = json.load(open(os.path.join(DATA, f"{key}-spawns.json")))
    i0, i1 = [p["pos"] for p in sp["intro0"]], [p["pos"] for p in sp["intro1"]]
    c0 = [sum(p[k] for p in i0) / 4 for k in range(3)]
    c1 = [sum(p[k] for p in i1) / 4 for k in range(3)]
    out = {"i0": [[round(v, 2) for v in p] for p in i0], "i1": [[round(v, 2) for v in p] for p in i1],
           "straight": round(math.hypot(c0[0] - c1[0], c0[2] - c1[2]), 1),
           "min_pair": round(min(math.hypot(a[0] - b[0], a[2] - b[2]) for a in i0 for b in i1), 1)}
    if T is None:
        try:
            T = load(key)
        except (ValueError, SystemExit, OSError):
            T = None               # no stock collision for this map's levels (Train Station: not in the world archives we read): navmesh sight lines
    if T is not None:
        out["visible_pairs"] = sum(0 if seg_hits(T, head(a), head(b)) else 1 for a in i0 for b in i1)
        out["tris"] = int(len(T))
        out["method"] = "collision"
    else:
        import layoutlib as L
        ctx = L.Ctx(key, sp)
        out["visible_pairs"] = sum(1 for a in i0 for b in i1 if ctx.grid.los(tuple(a), tuple(b)))
        out["tris"] = 0
        out["method"] = "navmesh"
    return out


def candidates(key, team):
    """ground spots (nav polygon centres of the play space) far from the other team's centre, ordered by straight distance, with whether the other team sees them"""
    sys.path.insert(0, HERE)
    import layoutlib as L
    lay = L.load_layout(key)
    ctx = L.Ctx(key, lay)
    T = load(key)
    oc = L.centre(lay[f"intro{1 - team}"])
    rows = []
    for i in ctx.play:
        x, y, z = ctx.nav.cen[i]
        if ctx.nav.edge_clear(x, z, y) < 2.0:
            continue
        rows.append((math.hypot(x - oc[0], z - oc[2]), x, y, z))
    rows.sort(reverse=True)
    seen = []
    for d, x, y, z in rows:
        if any(math.hypot(x - sx, z - sz) < 8 for sx, sz in seen):
            continue
        seen.append((x, z))
        vis = not seg_hits(T, head(oc), head((x, y, z)))
        print("  straight %5.1f  (%7.1f, %6.2f, %7.1f)  %s" % (d, x, y, z, "SEEN from the other start" if vis else "hidden"))
        if len(seen) >= 12:
            break


def move(key, team, tx, tz, apply=False):
    import layoutlib as L
    import spawn_intro as S
    lay = L.load_layout(key)
    ctx = L.Ctx(key, lay)
    T = load(key)
    old = lay[f"intro{team}"]
    c, _ = S.team_frame(old)
    shifted = [{"pos": [p["pos"][0] + tx - c[0], p["pos"][1], p["pos"][2] + tz - c[2]], "quat": p["quat"]} for p in old]
    trial = dict(lay)
    trial[f"intro{team}"] = shifted
    other = [p["pos"] for p in lay[f"intro{1 - team}"]]
    oc = L.centre(lay[f"intro{1 - team}"])
    e0, w0, _m = L.check(key, lay, ctx, strict=True)
    base = ({S._norm(x) for x in e0}, {S._norm(x) for x in w0})
    best = None
    for relax, rad in ((0, 8.0), (1, 10.0), (2, 14.0)):
        for sc, cc, yaw, pts, rep in S._fit_team(ctx, trial, team, rad, relax):
            lay2 = dict(lay)
            lay2[f"intro{team}"] = pts
            vis = sum(0 if seg_hits(T, head(a["pos"]), head(b)) else 1 for a in pts for b in other)
            if vis:
                continue                    # seen by the other team: skip before the slow whole-map check
            ne, nw, m = S._newness(key, ctx, lay2, base)
            dist = math.hypot(cc[0] - oc[0], cc[2] - oc[2])
            print("  relax %d  centre (%.1f, %.1f) yaw %4.0f  back %.1f fwd %.1f  straight %.1f  in sight %d/16  new errors %d warnings %d" %
                  (relax, cc[0], cc[2], math.degrees(yaw), rep["back"], rep["fwd"], dist, vis, len(ne), len(nw)), [x[:110] for x in ne + nw])
            if vis == 0 and all('from an intro spawn' in x for x in ne) and (best is None or (len(nw), -sc) < (len(best[0]), -best[1])):
                best = (nw, sc, cc, yaw, pts)
        if best:
            break
    if not best:
        print("no fit")
        return 1
    nw, sc, cc, yaw, pts = best
    print("best: centre (%.1f, %.1f) yaw %.0f, warnings %s" % (cc[0], cc[2], math.degrees(yaw), nw))
    if apply:
        pth = os.path.join(DATA, f"{key}-spawns.json")
        d = json.load(open(pth))
        d[f"intro{team}"] = [{"pos": [round(v, 3) for v in p["pos"]], "quat": p["quat"]} for p in pts]
        if team == 0 and d.get("player"):
            d["player"] = {"pos": d["intro0"][0]["pos"], "quat": d["intro0"][0]["quat"]}
        if d.get("_anchors"):
            d["_anchors"][team] = [round(cc[0], 3), round(cc[1], 4), round(cc[2], 4), round(yaw, 5)]
        for r in d["respawns"]:       # a respawn a hair inside the 12 m rule of the new start: pushed straight away from the start centre
            for _ in range(40):
                ds = min(math.hypot(r["pos"][0] - q["pos"][0], r["pos"][2] - q["pos"][2]) for q in d[f"intro{team}"])
                if ds >= 12.2 or ds < 8:
                    break
                dx, dz = r["pos"][0] - cc[0], r["pos"][2] - cc[2]
                n = math.hypot(dx, dz) or 1
                r["pos"][0] = round(r["pos"][0] + dx / n * 0.1, 3)
                r["pos"][2] = round(r["pos"][2] + dz / n * 0.1, 3)
        json.dump(d, open(pth, "w"), indent=1)
        print("written", pth)
    return 0


def main(argv):
    cmd = argv[1] if len(argv) > 1 else "check"
    if cmd == "move":
        rest = [a for a in argv[2:] if not a.startswith("--")]
        return move(rest[0], int(rest[1]), float(rest[2]), float(rest[3]), "--apply" in argv)
    rest = [a for a in argv[2:] if not a.startswith("--")]
    if cmd == "candidates":
        candidates(rest[0], int(rest[1]))
        return 0
    keys = KEYS if not rest or rest == ["all"] else rest
    snap = json.load(open(SNAP)) if os.path.exists(SNAP) else {}
    bad = 0
    for k in keys:
        r = report(k)
        snap[k] = r
        ok = r["straight"] >= MIN_STRAIGHT and r["visible_pairs"] == 0
        bad += not ok
        print("%-14s straight %5.1f m  nearest pair %5.1f m  pairs in sight %d/16  (%s)  %s" % (k, r["straight"], r["min_pair"], r["visible_pairs"], r["method"], "OK" if ok else "FAIL"))
    if "--write" in argv:
        json.dump(snap, open(SNAP, "w"), indent=1)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
