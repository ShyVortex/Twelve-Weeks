"""Spawn / box positions for a Part I level set, taken from the CONVERTED collision (the same triangles the game's Havok loads), and the offline
check that every spawn has solid ground under it.

  python p1_spawns.py seed  <key>     # choose positions on the walkable floor of <key>'s -phys paks, write tools/maps/data/<key>-spawns.json
                                      # (then: p1_levelset.py seed-pak <key> / sp_maps build the ingame pak)
  python p1_spawns.py check <key>     # raycast every position of the json against the collision (floor under it, headroom, not in a wall)

Why: the first seed (p1_levelset.seed) put a ring at the centre of the UNION of the three levels' render bounds, y = lowest bound + 0.6
(-2.0): outside / below the collision (floor y -1.2.. at that spot or no floor at all) -> every player fell to death (2-client
Bookstore match: 'spawn pick: slot 0 died at 84.3 -13.3 309.7', floor rays t -1).
"""
import json
import math
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "models"))
import p1_levelset as L  # noqa: E402
import havok_preview as hp  # noqa: E402

MAIN_LEVELS = 2          # floor candidates come from the first levels of the spec (main + rear); the facade is a backdrop
HEAD = 2.3               # clearance above the floor point (player capsule ~1.8 m + margin)
WALL = 0.45              # horizontal clearance around a spawn
STEP = 1.0               # candidate grid


class Tris:
    def __init__(self, t):
        self.t = t
        self.a, self.e1, self.e2 = t[:, 0], t[:, 1] - t[:, 0], t[:, 2] - t[:, 0]
        n = np.cross(self.e1, self.e2)
        ln = np.maximum(np.linalg.norm(n, axis=1), 1e-12)
        self.n = n / ln[:, None]
        self.lo, self.hi = t.min(1), t.max(1)

    def ray(self, o, d, tmax):
        """nearest hit distance of the ray o + t d (0 < t < tmax), Moller-Trumbore, all triangles two-sided; None = no hit"""
        o, d = np.asarray(o, float), np.asarray(d, float)
        e = o + d * tmax
        lo, hi = np.minimum(o, e) - 1e-4, np.maximum(o, e) + 1e-4
        m = ((self.hi >= lo) & (self.lo <= hi)).all(1)
        if not m.any():
            return None
        a, e1, e2 = self.a[m], self.e1[m], self.e2[m]
        p = np.cross(d, e2)
        det = (e1 * p).sum(1)
        ok = np.abs(det) > 1e-12
        inv = np.where(ok, 1.0 / np.where(ok, det, 1.0), 0.0)
        s = o - a
        u = (s * p).sum(1) * inv
        q = np.cross(s, e1)
        v = (q * d).sum(1) * inv
        t = (e2 * q).sum(1) * inv
        hit = ok & (u >= 0) & (v >= 0) & (u + v <= 1) & (t > 1e-6) & (t < tmax)
        return float(t[hit].min()) if hit.any() else None

    def floors_at(self, x, z):
        """heights of the up-facing triangles above (x, z), ascending"""
        m = (self.lo[:, 0] <= x) & (self.hi[:, 0] >= x) & (self.lo[:, 2] <= z) & (self.hi[:, 2] >= z) & (self.n[:, 1] > 0.7)
        idx = np.nonzero(m)[0]
        out = []
        for i in idx:
            a, e1, e2 = self.a[i], self.e1[i], self.e2[i]
            det = e1[0] * e2[2] - e1[2] * e2[0]            # xz projection
            if abs(det) < 1e-12:
                continue
            dx, dz = x - a[0], z - a[2]
            u = (dx * e2[2] - dz * e2[0]) / det
            v = (e1[0] * dz - e1[2] * dx) / det
            if u >= 0 and v >= 0 and u + v <= 1:
                out.append(a[1] + u * e1[1] + v * e2[1])
        return sorted(out)


def load(key):
    m = L.spec(key)
    lv = m["part1"]["levels"]
    t = hp.collision_tris([os.path.join(L.CONV, f"{x}-phys.pak") for x in lv])
    if not len(t):
        raise SystemExit(f"{key}: no converted collision in {L.CONV} (python p1_levelset.py convert / phys first)")
    return Tris(t), m


def ok_point(tr, p):
    """(floor_y, reason) for a position: ground within 0.6 m below, HEAD m free above, nothing within WALL m sideways"""
    x, y, z = p
    t = tr.ray((x, y + 0.6, z), (0, -1, 0), 1.2)
    if t is None:
        return None, "no ground within 0.6 m below"
    gy = y + 0.6 - t
    if tr.ray((x, gy + 0.05, z), (0, 1, 0), HEAD) is not None:
        return gy, "ceiling / obstacle within %.1f m above" % HEAD
    for dy in (0.4, 1.0, 1.6):
        for k in range(8):
            a = k * math.pi / 4
            if tr.ray((x, gy + dy, z), (math.cos(a), 0, math.sin(a)), WALL) is not None:
                return gy, "wall within %.2f m (height +%.1f, dir %d deg)" % (WALL, dy, k * 45)
    return gy, None


def walkable_cells(tr, lo, hi):
    """{(i, j): [floor y...]} on a STEP grid, only cells with a clean standing point"""
    cells = {}
    nx, nz = int((hi[0] - lo[0]) / STEP) + 1, int((hi[2] - lo[2]) / STEP) + 1
    for i in range(nx):
        for j in range(nz):
            x, z = lo[0] + i * STEP, lo[2] + j * STEP
            for fy in tr.floors_at(x, z):
                gy, why = ok_point(tr, (x, fy + 0.05, z))
                if why is None:
                    cells.setdefault((i, j), []).append(round(fy, 3))
    return cells


def components(cells):
    """connected sets of (i, j, k) nodes: 4-neighbours with a floor height within 0.45 m"""
    seen, comps = set(), []
    for (i, j), ys in cells.items():
        for k in range(len(ys)):
            if (i, j, k) in seen:
                continue
            comp, stack = [], [(i, j, k)]
            seen.add((i, j, k))
            while stack:
                a, b, c = stack.pop()
                comp.append((a, b, c))
                y0 = cells[(a, b)][c]
                for da, db in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                    n = (a + da, b + db)
                    for k2, y2 in enumerate(cells.get(n, [])):
                        if (n[0], n[1], k2) not in seen and abs(y2 - y0) < 0.45:
                            seen.add((n[0], n[1], k2))
                            stack.append((n[0], n[1], k2))
            comps.append(comp)
    return sorted(comps, key=len, reverse=True)


def yaw_quat_to(dx, dz):
    th = math.atan2(dx, dz) / 2          # +Z is forward at the identity rotation
    return [0.0, round(math.sin(th), 6), 0.0, round(math.cos(th), 6)]


def seed_positions(key):
    tr, m = load(key)
    # candidate area: the collision of the first MAIN_LEVELS levels (the facade is a distant backdrop)
    main = hp.collision_tris([os.path.join(L.CONV, f"{x}-phys.pak") for x in m["part1"]["levels"][:MAIN_LEVELS]])
    lo, hi = main.reshape(-1, 3).min(0), main.reshape(-1, 3).max(0)
    cells = walkable_cells(tr, lo, hi)
    comps = components(cells)
    if not comps:
        raise SystemExit("no walkable floor found")
    comp = comps[0]
    pts = np.array([(lo[0] + a * STEP, cells[(a, b)][c], lo[2] + b * STEP) for a, b, c in comp])
    print(f"walkable: {len(cells)} cells, {len(comps)} components, largest {len(comp)} cells "
          f"x {pts[:, 0].min():.1f}..{pts[:, 0].max():.1f} z {pts[:, 2].min():.1f}..{pts[:, 2].max():.1f} y {pts[:, 1].min():.1f}..{pts[:, 1].max():.1f}")
    ctr = pts[:, [0, 2]].mean(0)
    # principal axis of the walkable area: team 0 at one end, team 1 at the other
    u, s, vt = np.linalg.svd(pts[:, [0, 2]] - ctr, full_matrices=False)
    ax = vt[0]
    pr = (pts[:, [0, 2]] - ctr) @ ax

    def pick(target, avoid=(), mind=0.0):
        d = np.linalg.norm(pts[:, [0, 2]] - np.asarray(target), axis=1)
        for i in np.argsort(d):
            p = pts[i]
            if all(np.linalg.norm(p[[0, 2]] - q[[0, 2]]) >= mind for q in avoid):
                return p
        return pts[int(np.argmin(d))]

    def line(end, sign):
        """4 points in a row near one end of the area, spaced ~2 m, facing the centre"""
        sel = np.nonzero(pr * sign >= np.percentile(pr * sign, 88))[0]
        base = pts[sel[np.argmax(pr[sel] * sign)]]
        out = [base]
        for _ in range(3):
            out.append(pick(out[-1][[0, 2]] + np.array([-ax[1], ax[0]]) * 2.0, out, 1.7))
        return out

    def face(p, to):
        return yaw_quat_to(to[0] - p[0], to[1] - p[2])
    i0, i1 = line(0, -1), line(1, 1)
    # respawns: farthest-point sampling over the area, 13 points >= 5 m apart, biased to keep spacing
    resp, cand = [], pts
    first = pick(ctr, (), 0)
    resp.append(first)
    while len(resp) < 13:
        d = np.min([np.linalg.norm(cand[:, [0, 2]] - r[[0, 2]], axis=1) for r in resp], axis=0)
        resp.append(cand[int(np.argmax(d))])
    boxes = []
    for a in np.linspace(-0.6, 0.6, 6):
        boxes.append(pick(ctr + ax * (a * (pr.max() - pr.min()) / 2) , boxes + i0 + i1, 3.0))

    def rec(p, to=ctr):
        return {"pos": [round(float(p[0]), 3), round(float(p[1]) + 0.05, 3), round(float(p[2]), 3)], "quat": face(p, to)}
    body = {"_note": "seeded on the converted collision (p1_spawns.py seed): team ends of the walkable area, respawns spread over it; "
                     "tune with F8 marks, then rebuild",
            "player": rec(i1[0]),
            "intro0": [rec(p) for p in i0], "intro1": [rec(p) for p in i1],
            "respawns": [rec(p) for p in resp], "boxes": [rec(p) for p in boxes]}
    return body, tr


def check(key, body=None, tr=None, quiet=False):
    """every position of the json has ground / headroom / wall clearance on the converted collision; returns problems"""
    if tr is None:
        tr, _ = load(key)
    if body is None:
        body = json.load(open(os.path.join(L.DATA, f"{key}-spawns.json")))
    bad, n = [], 0
    for name, v in body.items():
        if name.startswith("_"):
            continue
        for i, e in enumerate(v if isinstance(v, list) else [v]):
            n += 1
            gy, why = ok_point(tr, e["pos"])
            if why:
                bad.append(f"{name}[{i}] at {e['pos']}: {why}")
    if not quiet:
        print(f"{key}: {n} positions checked against the converted collision, {len(bad)} problems")
        for b in bad[:20]:
            print("  ", b)
    return bad


def main(argv):
    if len(argv) >= 3 and argv[1] == "seed":
        body, tr = seed_positions(argv[2])
        bad = check(argv[2], body, tr)
        assert not bad, "seeded positions failed their own check"
        os.makedirs(L.DATA, exist_ok=True)
        json.dump(body, open(os.path.join(L.DATA, f"{argv[2]}-spawns.json"), "w"), indent=1)
        print("spawns ->", os.path.join(L.DATA, f"{argv[2]}-spawns.json"))
        return 0
    if len(argv) >= 3 and argv[1] == "check":
        return 1 if check(argv[2]) else 0
    print(__doc__)
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
