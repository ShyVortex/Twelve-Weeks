"""Offline play-space check of an SP-section map on the REAL collision (Havok triangles of every loaded level, the level edits applied,
plus the map's props as boxes): where can a player get to, are the closures tight, do spawns / boxes stand on clear floor.

  python reach_check.py <key> [--png FILE] [--json FILE] [--fix]
                       --fix: failing spawns / boxes move to the nearest passing spot (<= 3 m, boxes 5 m, same floor band, 1.2 m from the others),
                       every point's y snaps onto its floor (+0.02); tools/maps/data/<key>-spawns.json rewritten (then sp_maps.py pak)

Collision: <level>-phys.pak of every level of sp_maps.json "levels" (edited copies from level-edit-cache/out/<key> when they exist,
stock ones otherwise, read only), plus every prop as an oriented box (tools/maps/data/prop_bounds.json, the invisible actors from
collision_walls.ACTORS; props without known bounds are reported).
Walk model on a 0.5 m grid (floors = upward triangles under the cell centre; a cell is standable when its 0.5 x 0.5 m column from
floor + LO to floor + HI holds no triangle; 4-neighbour moves, step up <= STEP, drops of any height):
  prone  LO 0.45 HI 0.85, climbs up to 1.6 m allowed  -> an OVER-estimate of where a player can get (leak test of the closures)
  stand  LO 0.40 HI 1.75, step 0.55, no climbing      -> where a player surely walks (spawns / boxes must lie in it)
Checks:
  leaks     reachable (prone mode) cells inside the spec's "reach_forbid" rectangles ({name, rect [x0, x1, z0, z1], y [lo, hi]})
  seeds     the spec's "reach_seeds" [[x, y, z], ...] (floor points inside the play space), else the team starts
            (spec fixed_boxes whose note says "user" = F8 marks: never moved, findings reported as USER-PLACED, not failures)
  points    every intro / respawn / box of tools/maps/data/<key>-spawns.json: floor under it (|dy| <= 0.35), reachable in stand mode from the
            seeds, capsule clear (radius 0.45, 0.4..1.75 m above the floor, spawns) / box volume + 0.35 m apron clear (boxes, 0.1..0.9 m)
Exit code 1 on a leak or a failing point.
"""
import json
import math
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import level_edit as le  # noqa: E402

CELL = 0.5
MODES = {"prone": dict(lo=0.45, hi=0.85, step=0.6, climb=1.6), "stand": dict(lo=0.40, hi=1.75, step=0.55, climb=0.0)}
BOX_HALF = (0.45, 0.35)          # supply box footprint half extents (m) checked around a box spawner (~0.9 x 0.7 m crate)


def spec(key):
    return next(m for m in json.load(open(le.SPEC, encoding="utf-8"))["maps"] if m["key"] == key)


def phys_path(key, lv):
    out = os.path.join(le.CACHE, "out", key, lv + "-phys.pak")
    if os.path.exists(out):
        return out
    out = os.path.join(le.CACHE, "out", lv + "-phys.pak")          # level_edit.py apply (default out dir)
    edited = any(e["level"] == lv for e in spec(key).get("edits", []))
    if edited and os.path.exists(out):
        return out
    if lv in spec(key).get("part1", {}).get("levels", []):        # converted Part I level (p1_levelset.py convert; the build stages the same file)
        sys.path.insert(0, os.path.join(os.path.dirname(HERE), "part1"))
        import p1_levelset
        p = os.path.join(p1_levelset.CONV, lv + "-phys.pak")
        return p if os.path.exists(p) else None
    try:
        return le.fetch(lv, os.path.join(le.CACHE, "src"), None, ("-phys",))["-phys"]
    except SystemExit:
        return None


WATER_TAG = 65535      # water surfaces (flo-*-water levels): swum / waded through, not stood on


def level_tris(key, box, soft=False):
    """collision triangles of the map's levels in the box; water (tag 65535) and the spec's "reach_ignore_tags" are left out
    (soft=True: only the reach_ignore_tags triangles: they are ground the player stands on - tag 449 is the terrain layer, the
    only floor of the street at e.g. 322.75 490 and of the sunken park - but their 0.45 m relief does not block a body)"""
    m = spec(key)
    skip = {WATER_TAG} | set(m.get("reach_ignore_tags", []))
    want = set(m.get("reach_ignore_tags", [])) if soft else None
    L = []
    used = []
    for lv in [x for x in m["levels"] if x != m["pak"]]:
        p = phys_path(key, lv)
        if not p:
            continue
        n = 0
        for it in le.phys_items(p)[1]:
            keys, T, tg = le.hc.triangles(it.mesh)
            sel = ((T.max(1)[:, [0, 2]] >= [box[0], box[2]]) & (T.min(1)[:, [0, 2]] <= [box[1], box[3]])).all(1)
            sel &= np.isin(tg, list(want)) if soft else ~np.isin(tg, list(skip))
            if sel.any():
                L.append(T[sel].astype(np.float64))
                n += int(sel.sum())
        used.append((lv, os.path.basename(os.path.dirname(p)), n))
    return (np.concatenate(L) if L else np.zeros((0, 3, 3))), used


def _quat_yaw(q):
    return 2.0 * math.atan2(q[1], q[3])


def prop_tris(props):
    import collision_walls as CW
    db = json.load(open(os.path.join(HERE, "data", "prop_bounds.json")))
    inv = {a: (lo, hi) for a, lo, hi in CW.ACTORS.values()}
    out, unknown = [], []
    for p in props:
        if p["art"] in inv:
            lo, hi = inv[p["art"]]
        elif p["art"] in db:
            lo, hi = db[p["art"]]["min"], db[p["art"]]["max"]
        else:
            unknown.append(p["art"])
            continue
        s = p.get("scale", [1.0, 1.0, 1.0])
        lo = np.array(lo) * s
        hi = np.array(hi) * s
        v = np.array([[x, y, z] for x in (lo[0], hi[0]) for y in (lo[1], hi[1]) for z in (lo[2], hi[2])])
        yaw = _quat_yaw(p["quat"])
        c, sn = math.cos(yaw), math.sin(yaw)
        w = np.stack([v[:, 0] * c + v[:, 2] * sn, v[:, 1], -v[:, 0] * sn + v[:, 2] * c], 1) + np.array(p["pos"])
        f = [(0, 1, 3), (0, 3, 2), (4, 6, 7), (4, 7, 5), (0, 4, 5), (0, 5, 1), (2, 3, 7), (2, 7, 6), (0, 2, 6), (0, 6, 4), (1, 5, 7), (1, 7, 3)]
        out.append(w[np.array(f)])
    return (np.concatenate(out) if out else np.zeros((0, 3, 3))), unknown


class World:
    def __init__(self, T, box, soft=None):
        self.T = T
        self.soft = np.zeros(len(T), bool) if soft is None else soft      # floor-only triangles (never block a body)
        self.x0, self.z0 = box[0], box[2]
        self.nx = int(math.ceil((box[1] - box[0]) / CELL))
        self.nz = int(math.ceil((box[3] - box[2]) / CELL))
        B = 2.0
        self.B = B
        self.buckets = {}
        lo, hi = T.min(1), T.max(1)
        bx0 = np.floor((lo[:, 0] - self.x0) / B).astype(int)
        bx1 = np.floor((hi[:, 0] - self.x0) / B).astype(int)
        bz0 = np.floor((lo[:, 2] - self.z0) / B).astype(int)
        bz1 = np.floor((hi[:, 2] - self.z0) / B).astype(int)
        for i in range(len(T)):
            for a in range(max(bx0[i], -1), min(bx1[i], int(self.nx * CELL / B) + 1) + 1):
                for b in range(max(bz0[i], -1), min(bz1[i], int(self.nz * CELL / B) + 1) + 1):
                    self.buckets.setdefault((a, b), []).append(i)
        self.buckets = {k: np.array(v) for k, v in self.buckets.items()}
        n = np.cross(T[:, 1] - T[:, 0], T[:, 2] - T[:, 0])
        self.up = (n[:, 1] / (np.linalg.norm(n, axis=1) + 1e-12)) > 0.5
        self.up |= (n[:, 1] / (np.linalg.norm(n, axis=1) + 1e-12)) < -0.5      # either winding: a horizontal-ish surface
        self.floors = {}

    def near(self, x0, z0, x1, z1):
        B = self.B
        ids = []
        for a in range(int(math.floor((x0 - self.x0) / B)), int(math.floor((x1 - self.x0) / B)) + 1):
            for b in range(int(math.floor((z0 - self.z0) / B)), int(math.floor((z1 - self.z0) / B)) + 1):
                v = self.buckets.get((a, b))
                if v is not None:
                    ids.append(v)
        return np.unique(np.concatenate(ids)) if ids else np.zeros(0, int)

    def cell_xz(self, i, j):
        return self.x0 + (i + 0.5) * CELL, self.z0 + (j + 0.5) * CELL

    def floor_list(self, i, j):
        k = (i, j)
        if k in self.floors:
            return self.floors[k]
        x, z = self.cell_xz(i, j)
        ids = self.near(x, z, x, z)
        ids = ids[self.up[ids]] if len(ids) else ids
        hs = []
        if len(ids):
            T = self.T[ids]
            (x1, z1), (x2, z2), (x3, z3) = T[:, 0][:, [0, 2]].T, T[:, 1][:, [0, 2]].T, T[:, 2][:, [0, 2]].T
            det = (z2 - z3) * (x1 - x3) + (x3 - x2) * (z1 - z3)
            ok = np.abs(det) > 1e-9
            det = np.where(ok, det, 1)
            l1 = ((z2 - z3) * (x - x3) + (x3 - x2) * (z - z3)) / det
            l2 = ((z3 - z1) * (x - x3) + (x1 - x3) * (z - z3)) / det
            l3 = 1 - l1 - l2
            inside = ok & (l1 >= -1e-6) & (l2 >= -1e-6) & (l3 >= -1e-6)
            y = l1 * T[:, 0, 1] + l2 * T[:, 1, 1] + l3 * T[:, 2, 1]
            for h in sorted(y[inside]):
                if not hs or h - hs[-1] > 0.25:
                    hs.append(float(h))
                else:
                    hs[-1] = float(h)
        self.floors[k] = hs
        return hs

    def clear(self, x0, y0, z0, x1, y1, z1):
        ids = self.near(x0, z0, x1, z1)
        if not len(ids):
            return True
        ids = ids[~self.soft[ids]]
        if not len(ids):
            return True
        T = self.T[ids]
        cand = ((T.max(1) >= [x0, y0, z0]) & (T.min(1) <= [x1, y1, z1])).all(1)
        if not cand.any():
            return True
        return not le.tri_box_overlap(T[cand], [x0, y0, z0], [x1, y1, z1]).any()

    def standable(self, i, j, h, mode, cache):
        k = (i, j, round(h, 2))
        if k in cache:
            return cache[k]
        x, z = self.cell_xz(i, j)
        e = CELL / 2 + 0.01
        r = self.clear(x - e, h + mode["lo"], z - e, x + e, h + mode["hi"], z + e)
        cache[k] = r
        return r

    def flood(self, seeds, mode, limit=None):
        """-> {(i, j): h} reachable from the seed points"""
        cache = {}
        seen = {}
        st = []
        for (x, y, z) in seeds:
            i, j = int((x - self.x0) // CELL), int((z - self.z0) // CELL)
            fl = [h for h in self.floor_list(i, j) if abs(h - y) < 0.6]
            if fl and self.standable(i, j, fl[0], mode, cache):
                seen[(i, j, round(fl[0], 1))] = fl[0]
                st.append((i, j, fl[0]))
        while st:
            i, j, h = st.pop()
            for di, dj in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                a, b = i + di, j + dj
                if not (0 <= a < self.nx and 0 <= b < self.nz):
                    continue
                for h2 in self.floor_list(a, b):
                    if h2 - h > max(mode["step"], mode["climb"]) or h - h2 > 12.0:
                        continue
                    key = (a, b, round(h2, 1))
                    if key in seen:
                        continue
                    if not self.standable(a, b, h2, mode, cache):
                        continue
                    if h2 - h > mode["step"]:            # a climb: the column above the higher floor must be clear from the lower one up
                        x, z = self.cell_xz(i, j)
                        e = CELL / 2 - 0.05
                        if not self.clear(x - e, h + mode["lo"], z - e, x + e, h2 + mode["hi"], z + e):
                            continue
                    if h - h2 > 0.3:                     # a drop: the fall column of the lower cell must be clear up to the body on the higher floor
                        x, z = self.cell_xz(a, b)
                        e = CELL / 2 - 0.05
                        if not self.clear(x - e, h2 + mode["lo"], z - e, x + e, h + mode["hi"], z + e):
                            continue
                    seen[key] = h2
                    st.append((a, b, h2))
        return seen


def capsule_clear(w, x, y, z, r=0.45, lo=0.4, hi=1.75):
    return w.clear(x - r, y + lo, z - r, x + r, y + hi, z + r)


def point_problems(w, stand, kind, x, y, z, yaw):
    """-> (floor y, [problems]) of a spawn / box spawner at (x, y, z)"""
    i, j = int((x - w.x0) // CELL), int((z - w.z0) // CELL)
    fl = [h for h in w.floor_list(i, j) if abs(h - y) <= 0.35]
    probs = []
    if not fl:
        probs.append("no floor within 0.35 m (floors here %s)" % [round(h, 2) for h in w.floor_list(i, j)])
        h = y
    else:
        h = min(fl, key=lambda q: abs(q - y))
    if (i, j) not in stand or abs(stand[(i, j)] - h) > 0.6:
        probs.append("not reachable on foot from the seeds")
    if kind == "spawn":
        if not capsule_clear(w, x, h, z):
            probs.append("capsule (r 0.45, 0.4..1.75 m) touches collision")
    else:
        hx, hz = BOX_HALF
        ex = abs(hx * math.cos(yaw)) + abs(hz * math.sin(yaw))
        ez = abs(hx * math.sin(yaw)) + abs(hz * math.cos(yaw))
        if not w.clear(x - ex, h + 0.1, z - ez, x + ex, h + 0.9, z + ez):
            probs.append("box volume touches collision")
        if not w.clear(x - ex - 0.35, h + 0.4, z - ez - 0.35, x + ex + 0.35, h + 1.6, z + ez + 0.35):
            probs.append("no 0.35 m apron around the box (wall / prop against it)")
        dev = []
        for cx, cz in [(x + sx * ex, z + sz * ez) for sx in (-1, 1) for sz in (-1, 1)]:
            ci, cj = int((cx - w.x0) // CELL), int((cz - w.z0) // CELL)
            f2 = [q for q in w.floor_list(ci, cj) if abs(q - h) < 0.6]
            dev.append(min((abs(q - h) for q in f2), default=9.9))
        if max(dev) > 0.15:
            probs.append("uneven floor under the box (corner dy %.2f m)" % max(dev))
        stack = []
        for cx, cz in [(x + sx * ex, z + sz * ez) for sx in (-1, 0, 1) for sz in (-1, 0, 1)]:
            ci, cj = int((cx - w.x0) // CELL), int((cz - w.z0) // CELL)
            stack += [q for q in w.floor_list(ci, cj) if 0.2 < h - q < 0.7]
        if stack:
            probs.append("another surface %.2f m below the box floor (it sits on a slab / curb / prop top, not on the ground)" % (h - max(stack)))
    return h, probs


def nudge(w, stand, kind, x, y, z, yaw, others, rmax=3.0):
    """nearest position (rings of 0.25 m up to rmax) on the same floor (box 0.5 m, spawn 0.35 m of y) that passes every check and keeps 1.2 m from the
    other points -> (x, floor y + 0.02, z) or None.  Without problems it only snaps y onto the floor."""
    h, probs = point_problems(w, stand, kind, x, y, z, yaw)
    if not probs:
        return (round(x, 3), round(h + 0.02, 3), round(z, 3))
    for r in np.arange(0.25, rmax + 1e-6, 0.25):
        n = max(8, int(2 * math.pi * r / 0.25))
        best = None
        for k in range(n):
            a = 2 * math.pi * k / n
            cx, cz = x + r * math.sin(a), z + r * math.cos(a)
            ci, cj = int((cx - w.x0) // CELL), int((cz - w.z0) // CELL)
            for fh in w.floor_list(ci, cj):
                if abs(fh - y) > (0.5 if kind == "box" else 0.35):      # the same floor (boxes: the slab / prop-top check keeps them on the ground)
                    continue
                if any(math.dist((cx, cz), (o[0], o[2])) < 1.2 for o in others):
                    continue
                hh, pr = point_problems(w, stand, kind, cx, fh, cz, yaw)
                if not pr:
                    best = (round(cx, 3), round(hh + 0.02, 3), round(cz, 3))
                    break
            if best:
                return best
    return None


def run(key, png=None, js=None, fix=False):
    m = spec(key)
    b = m["bounds"]
    box = [b[0] - 18, b[1] + 18, b[2] - 18, b[3] + 18]
    T, used = level_tris(key, box)
    P, unknown = prop_tris(m.get("props", []))
    print("%s: %d collision triangles from %d levels, %d prop boxes%s" % (key, len(T), len([u for u in used if u[2]]), len(P) // 12,
                                                                     (", props without bounds: %s" % sorted(set(unknown))) if unknown else ""))
    for lv, where, n in used:
        if n:
            print("   %-40s %7d  (%s)" % (lv, n, where))
    Ts, _ = level_tris(key, box, soft=True)
    allT = np.concatenate([T, Ts] + ([P] if len(P) else []))
    w = World(allT, box, np.concatenate([np.zeros(len(T), bool), np.ones(len(Ts), bool), np.zeros(len(allT) - len(T) - len(Ts), bool)]))
    print("   + %d floor-only triangles (reach_ignore_tags: ground relief that does not block)" % len(Ts))
    sp = json.load(open(os.path.join(HERE, "data", f"{key}-spawns.json")))
    seeds = [tuple(p) for p in m.get("reach_seeds", [])] or [tuple(p["pos"]) for p in sp["intro0"]] + [tuple(p["pos"]) for p in sp["intro1"]]
    res = {"key": key, "leaks": {}, "points": []}
    bad = 0
    reach = {}
    for name, mode in MODES.items():
        reach[name] = w.flood(seeds, mode)
        area = len({(k[0], k[1]) for k in reach[name]}) * CELL * CELL
        print("%s mode: %d floor cells reachable (%.0f m2)" % (name, len(reach[name]), area))
    for z in m.get("reach_forbid", []):
        r, yl = z["rect"], z.get("y", [-1e9, 1e9])
        hit = []
        for (i, j, _), h in reach["prone"].items():
            x, zz = w.cell_xz(i, j)
            if r[0] <= x <= r[1] and r[2] <= zz <= r[3] and yl[0] <= h <= yl[1]:
                hit.append((round(x, 2), round(h, 2), round(zz, 2)))
        res["leaks"][z["name"]] = hit
        print("  forbid %-60s %s" % (z["name"], "OK (unreachable)" if not hit else "LEAK: %d cells, e.g. %s" % (len(hit), hit[:4])))
        bad += bool(hit)
    stand = {(k[0], k[1]): h for k, h in reach["stand"].items()}
    groups = [("T0-%d" % (i + 1), "spawn", p) for i, p in enumerate(sp["intro0"])] + \
             [("T1-%d" % (i + 1), "spawn", p) for i, p in enumerate(sp["intro1"])] + \
             [("R%d" % (i + 1), "spawn", p) for i, p in enumerate(sp["respawns"])] + \
             [("BOX%d" % (i + 1), "box", p) for i, p in enumerate(sp["boxes"])]
    moved = []
    user = [f["pos"] for f in m.get("fixed_boxes", []) if "user" in f.get("note", "")]
    for lab, kind, p in groups:
        x, y, z = p["pos"]
        yaw = _quat_yaw(p["quat"])
        h, probs = point_problems(w, stand, kind, x, y, z, yaw)
        mine = kind == "box" and any(math.dist(p["pos"], u) < 0.01 for u in user)
        if mine and probs:                  # the user's own spot (F8 mark): kept as placed, reported, not a failure
            print("  %-6s %-6s (%7.2f %6.2f %7.2f) floor %6.2f  USER-PLACED, kept: %s" % (lab, kind, x, y, z, h, "; ".join(probs)))
            res["points"].append({"label": lab, "kind": kind, "pos": [round(v, 3) for v in p["pos"]], "floor": round(h, 3), "user_kept": probs})
            continue
        if fix and (probs or abs(h - y) > 0.08) and not mine:
            others = [q["pos"] for _, _, q in groups if q is not p]
            got = nudge(w, stand, kind, x, y, z, yaw, others, 5.0 if kind == "box" else 3.0)
            if got:
                nx, nh, nz = got
                moved.append((lab, [round(x, 2), round(y, 2), round(z, 2)], [nx, nh, nz]))
                p["pos"] = [nx, nh, nz]
                x, y, z = p["pos"]
                h, probs = point_problems(w, stand, kind, x, y, z, yaw)
        res["points"].append({"label": lab, "kind": kind, "pos": [round(v, 3) for v in p["pos"]], "floor": round(h, 3), "problems": probs})
        print("  %-6s %-6s (%7.2f %6.2f %7.2f) floor %6.2f  %s" % (lab, kind, x, y, z, h, "OK" if not probs else "; ".join(probs)))
        bad += bool(probs)
    if fix and moved:
        if sp.get("player"):
            sp["player"] = {"pos": list(sp["intro0"][0]["pos"]), "quat": list(sp["intro0"][0]["quat"])}
        with open(os.path.join(HERE, "data", f"{key}-spawns.json"), "w") as f:
            json.dump(sp, f, indent=1)
        for lab, a, b in moved:
            print("  moved %-6s %s -> %s (%.2f m)" % (lab, a, b, math.dist((a[0], a[2]), (b[0], b[2]))))
    if png:
        draw(w, reach, m, sp, png)
    if js:
        json.dump(res, open(js, "w"), indent=1)
    print("REACH CHECK", "OK" if not bad else "FAILED (%d)" % bad)
    return bad


def draw(w, reach, m, sp, png):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    img = np.full((w.nz, w.nx, 3), 1.0)
    for (i, j, _), h in reach["prone"].items():
        img[j, i] = (1.0, 0.75, 0.75)
    for (i, j, _), h in reach["stand"].items():
        img[j, i] = (0.6, 0.85, 0.6)
    fig, ax = plt.subplots(figsize=(14, 14 * w.nz / w.nx))
    ax.imshow(img, extent=(w.x0, w.x0 + w.nx * CELL, w.z0 + w.nz * CELL, w.z0), interpolation="nearest")
    for z in m.get("reach_forbid", []):
        r = z["rect"]
        ax.add_patch(plt.Rectangle((r[0], r[2]), r[1] - r[0], r[3] - r[2], fill=False, ec="r", lw=1.5, ls="--"))
    for p in m.get("props", []):
        ax.plot(p["pos"][0], p["pos"][2], "m.", ms=4)
    for k, c in (("intro0", "b"), ("intro1", "r"), ("respawns", "g"), ("boxes", "y")):
        for i, p in enumerate(sp.get(k, [])):
            ax.plot(p["pos"][0], p["pos"][2], c + "o", ms=7, mec="k")
            ax.text(p["pos"][0] + 0.5, p["pos"][2] + 0.5, ("%s%d" % ({"intro0": "A", "intro1": "B", "respawns": "R", "boxes": "X"}[k], i + 1)), fontsize=7)
    ax.set_title("%s: green = walkable (stand), pink = only prone / climbing, red dashed = must stay unreachable" % m["key"])
    ax.grid(True, alpha=0.3)
    plt.savefig(png, dpi=70, bbox_inches="tight")


if __name__ == "__main__":
    a = sys.argv[1:]
    if not a:
        print(__doc__)
        sys.exit(0)
    png = a[a.index("--png") + 1] if "--png" in a else None
    js = a[a.index("--json") + 1] if "--json" in a else None
    sys.exit(1 if run(a[0], png, js, "--fix" in a) else 0)
