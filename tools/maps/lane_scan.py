"""Offline blocker scan of the Supermarket hall lane (jackson-market), CPU only.  Complements ray_lookup.py (which looks at one point): this walks the whole lane.

  python lane_scan.py <out-dir> [--phys supermarket-phys.pak override] [--step 0.25] [--reach 0.6]

<out-dir> = a pipeline output dir (re/maps/level-edit-cache/out/jackson-market: <out>/colledit/<level>-phys.pak = the shipped collision, <out>/morph/<level>.pak = the render).
  --phys LEVEL=PATH   use another phys pak for a level (a fresh colledit stage output)
Reports
  STATIC    collision triangles in the lane volume (the ground / clear rects of jackson-market-colledits-auto.json) that
            - are not a walkable surface (|ny| < 0.7) and stand more than 0.08 m over the render snow floor (fins, folds, vertical slivers), or
            - are degenerate (area < 1e-4 m2),
            split into VISIBLE (a render surface lies within 0.35 m: a wall / prop that is drawn) and INVISIBLE (no render surface = leftover collision).
  CAST      horizontal rays (+-x, +-z) at knee (0.45 m) and chest (1.2 m) height over the render floor on a --step grid across the lane, --reach long:
            every collision triangle they cross, again VISIBLE / INVISIBLE.  The numbers that matter are the INVISIBLE ones (expected 0 for the shipped lane).
"""
import argparse
import time
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import coll_edit as ce  # noqa: E402
import ray_lookup as rl  # noqa: E402

KEY = "jackson-market"
FLOOR = ("snow", "terrain-chunk", "-floor")             # render assets that are the FLOOR: they do not count as 'drawn' for a steep triangle standing over it (a fin over the snow is invisible; hall_floor.FLOOR_ASSETS)
LANE = [-515.0, 272.4, -494.4, 295.0]                  # union of the ground / clear rects of the lane (window side, hall, strip, yard, ramp, north exit)


def lane_rects():
    return [g["rect"] for g in ce.load_auto(KEY) if g.get("kind") == "ground" and g["level"] == "pat-jackson-supermarket" and g["rect"][0] < -495]


def in_lane(P, rects):
    return any(r[0] <= P[0] <= r[2] and r[1] <= P[2] <= r[3] for r in rects)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("out")
    ap.add_argument("--phys", action="append", default=[])
    ap.add_argument("--step", type=float, default=0.25)
    ap.add_argument("--reach", type=float, default=0.6)
    ap.add_argument("--whole", action="store_true", help="scan the WHOLE map (every level of the key), not only the hall lane: steep standing collision with no non-floor render within --near that stands on floor snow")
    ap.add_argument("--near", type=float, default=0.25)
    ap.add_argument("--only", action="append", default=[], help="--whole: only these levels")
    a = ap.parse_args()
    over = dict(s.split("=", 1) for s in a.phys)
    levels = []
    for lv, ph, sph, rp in rl.level_paths(KEY, a.out):
        levels.append((lv, over.get(lv, ph), sph, rp))
    rects = lane_rects()
    gents = [g for g in ce.load_auto(KEY) if g.get("kind") == "ground" and g["level"] == "pat-jackson-supermarket"]
    meshes = sorted({m for g in gents for m in g["meshes"]})
    rend = {lv: rp for lv, _, _, rp in levels}
    F = ce.ground_field([rend["pat-jackson-supermarket"], rend["pat-jackson-alley"]], meshes, LANE, 19.6, 0.0)
    rps = [rp for _, _, _, rp in levels if os.path.exists(rp)]

    if a.whole:
        return whole([l for l in levels if not a.only or l[0] in a.only], a.near)
    pool = []
    cen = np.array([(LANE[0] + LANE[2]) / 2, 18.5, (LANE[1] + LANE[3]) / 2])
    poolnf = []
    for rp in rps:
        for x in rl.render_near(rp, cen, 17.0):
            if not x["asset"].startswith("dcl-"):
                pool.append(x["tris"])
                if not any(w in x["asset"] for w in FLOOR):
                    poolnf.append(x["tris"])
                else:
                    nq = np.cross(x["tris"][:, 1] - x["tris"][:, 0], x["tris"][:, 2] - x["tris"][:, 0])
                    poolnf.append(x["tris"][nq[:, 1] / np.maximum(np.linalg.norm(nq, axis=1), 1e-12) < 0.5])
    POOL = np.concatenate(pool)
    POOL = POOL[rl.tri_area(POOL) > 1e-7]
    PMN, PMX = POOL.min(1), POOL.max(1)
    NF = np.concatenate(poolnf)
    NF = NF[rl.tri_area(NF) > 1e-7]
    NMN, NMX = NF.min(1), NF.max(1)
    print("render pool: %d triangles (%d without the floor snow)" % (len(POOL), len(NF)))

    def visible(P, r=0.35, steep=False):
        """a drawn surface within r of P; for a steep collision triangle only NON-floor render counts (the snow render under a fin does not draw the fin)"""
        P = np.asarray(P, float)
        mn, mx, T = (NMN, NMX, NF) if steep else (PMN, PMX, POOL)
        m = (mn <= P + r).all(1) & (mx >= P - r).all(1)
        return bool(m.any() and rl.ptri_dist(P, T[m]).min() <= r)

    # ---------------------------------------------------------------- static
    print("STATIC scan")
    nstat = {"fin": [0, 0], "degenerate": [0, 0]}
    cand = []
    for lv, ph, sph, rp in levels:
        K, T, G, I = rl.phys_tris(ph)
        c = T.mean(1)
        box = (c[:, 0] >= LANE[0]) & (c[:, 0] <= LANE[2]) & (c[:, 2] >= LANE[1]) & (c[:, 2] <= LANE[3])
        n = np.cross(T[:, 1] - T[:, 0], T[:, 2] - T[:, 0])
        ln = np.linalg.norm(n, axis=1)
        ar = 0.5 * ln
        ny = np.abs(n[:, 1]) / np.maximum(ln, 1e-12)
        fl = ce.field_at(F, c[:, 0], c[:, 2])
        ymax = T[:, :, 1].max(1)
        ymin = T[:, :, 1].min(1)
        fin = box & (ln > 1e-9) & (ny < 0.7) & (ymax > fl + 0.08) & (ymin < fl + 1.9)
        deg = box & (ar < 1e-4)
        for kind, m in (("fin", fin), ("degenerate", deg)):
            for j in np.nonzero(m)[0]:
                cand.append((kind, lv, int(I[j]), int(K[j]), T[j], float(ar[j]), float(ny[j]), float(ymax[j] - fl[j])))
    seen = {}
    for kind, lv, it, k, t, ar, ny, h in cand:
        if kind == "fin":
            vis = any(visible(p, 0.25, True) for p in (t.mean(0), t[0], t[1], t[2]))
            nstat[kind][0 if vis else 1] += 1
            if not vis:
                print("  INVISIBLE %s  %s item %d key %#x area %.3f |ny| %.2f top %.2f m over floor  %s" % (kind, lv, it, k, ar, ny, h, np.round(t, 2).tolist()))
        else:
            nstat[kind][0] += 1
    print("  steep/fin (|ny|<0.7, > 0.08 m over the floor): %d visible (drawn walls / props), %d INVISIBLE" % tuple(nstat["fin"]))
    print("  degenerate (area < 1e-4 m2) in the lane: %d" % nstat["degenerate"][0])
    # ---------------------------------------------------------------- cast
    print("CAST scan (step %.2f m, reach %.2f m, knee 0.45 / chest 1.2 over the render floor)" % (a.step, a.reach))
    tris = []
    for lv, ph, sph, rp in levels:
        K, T, G, I = rl.phys_tris(ph)
        m = (T[:, :, 0].max(1) >= LANE[0] - 1) & (T[:, :, 0].min(1) <= LANE[2] + 1) & (T[:, :, 2].max(1) >= LANE[1] - 1) & (T[:, :, 2].min(1) <= LANE[3] + 1)
        for k, t, i in zip(K[m], T[m], I[m]):
            tris.append((lv, int(i), int(k), t))
    TT = np.array([x[3] for x in tris])
    hit = {}
    dirs = [(1, 0), (-1, 0), (0, 1), (0, -1)]
    xs = np.arange(LANE[0], LANE[2] + 1e-9, a.step)
    zs = np.arange(LANE[1], LANE[3] + 1e-9, a.step)
    ncast = 0
    for x in xs:
        for z in zs:
            if not in_lane((x, 0, z), rects):
                continue
            fl = float(ce.field_at(F, x, z))
            # standing point must be open space: skip points inside a wall (render floor far below the ground rect's own edge is fine)
            for hh in (0.45, 1.2):
                o = np.array([x, fl + hh, z])
                for dx, dz in dirs:
                    d = np.array([dx, 0.0, dz])
                    ncast += 1
                    end = o + d * a.reach
                    lo, hi = np.minimum(o, end) - 0.05, np.maximum(o, end) + 0.05
                    sel = np.nonzero((TT.max(1) >= lo).all(1) & (TT.min(1) <= hi).all(1))[0]
                    if not len(sel):
                        continue
                    t, ix = rl.seg_tri(o, d, a.reach, TT[sel])
                    for tt, j in zip(t, ix):
                        g = sel[j]
                        if tt < 0.02:                                    # starting inside / on the surface: not a wall in front of the player
                            continue
                        hit.setdefault(g, (tt, o + d * tt, hh))
    invis = []
    for g, (tt, P, hh) in sorted(hit.items()):
        t_ = tris[g][3]
        n_ = np.cross(t_[1] - t_[0], t_[2] - t_[0])
        steep = abs(n_[1]) / max(np.linalg.norm(n_), 1e-12) < 0.7
        if not visible(P, 0.25 if steep else 0.35, steep):
            invis.append((g, tt, P, hh))
    print("  %d rays, %d distinct triangles crossed, %d with NO render surface within 0.35 m" % (ncast, len(hit), len(invis)))
    for g, tt, P, hh in invis[:60]:
        lv, it, k, t = tris[g]
        n = np.cross(t[1] - t[0], t[2] - t[0])
        n = n / max(np.linalg.norm(n), 1e-12)
        print("  BLOCKER %s item %d key %#x at (%.2f %.2f %.2f) h%.2f n(%+.2f %+.2f %+.2f)  %s" % (lv, it, k, P[0], P[1], P[2], hh, n[0], n[1], n[2], np.round(t, 2).tolist()))
    return 0 if not invis else 1


class _Near:
    """nearest-triangle test for many points: small triangles (edges <= 0.8 m) through a KD tree on their centroids (then the exact point-triangle distance of the few close ones), the
    few large ones (walls, floors) by bounding box + exact distance."""
    def __init__(self, T):
        from scipy.spatial import cKDTree
        e = np.maximum.reduce([np.linalg.norm(T[:, 1] - T[:, 0], axis=1), np.linalg.norm(T[:, 2] - T[:, 1], axis=1), np.linalg.norm(T[:, 0] - T[:, 2], axis=1)]) if len(T) else np.zeros(0)
        self.S = T[e <= 0.8]
        self.L = T[e > 0.8]
        self.tree = cKDTree(self.S.mean(1)) if len(self.S) else None
        self.Lmn, self.Lmx = (self.L.min(1), self.L.max(1)) if len(self.L) else (np.zeros((0, 3)), np.zeros((0, 3)))

    def within(self, P, r):
        P = np.asarray(P, float)
        if self.tree is not None:
            ix = self.tree.query_ball_point(P, r + 0.55)
            if ix and rl.ptri_dist(P, self.S[ix]).min() <= r:
                return True
        if len(self.L):
            m = (self.Lmn <= P + r).all(1) & (self.Lmx >= P - r).all(1)
            if m.any() and rl.ptri_dist(P, self.L[m]).min() <= r:
                return True
        return False


def whole(levels, near):
    """every level of the key: steep (|ny| < 0.7) collision triangles that stand 0.08 .. 2.2 m high ON floor snow (lowest vertex within 0.3 m of an up-facing floor render surface), have no
    non-floor drawn surface within `near` m (KD tree on the small render triangles) of any vertex / the centroid, and are not degenerate.  Lists each (STOCK / OURS).  20 m tiles."""
    rend = [rp for _, _, _, rp in levels if os.path.exists(rp)]
    CELL = 20.0
    tot = 0
    for lv, ph, sph, rp in levels:
        K, T, G, I = rl.phys_tris(ph)
        stock = {rl.tri_key(x) for x in rl.phys_tris(sph)[1]} if os.path.exists(sph) else set()
        n = np.cross(T[:, 1] - T[:, 0], T[:, 2] - T[:, 0])
        ln = np.linalg.norm(n, axis=1)
        ny = np.abs(n[:, 1]) / np.maximum(ln, 1e-12)
        h = T[:, :, 1].max(1) - T[:, :, 1].min(1)
        cand = np.nonzero((ln > 2e-4) & (ny < 0.7) & (h > 0.08) & (h < 2.2))[0]
        cell = np.floor(T[cand].mean(1)[:, [0, 2]] / CELL).astype(int)
        rows = []
        print("%s: %d steep standing candidates in %d tiles" % (lv, len(cand), len({tuple(x) for x in cell})), flush=True)
        for cx, cz in sorted({tuple(x) for x in cell}):
            sel = cand[(cell[:, 0] == cx) & (cell[:, 1] == cz)]
            t0 = time.time()
            cen = np.array([(cx + 0.5) * CELL, 18.5, (cz + 0.5) * CELL])
            FL, NF = [], []
            for r_ in rend:
                for p in rl.render_near(r_, cen, CELL * 0.75 + 1.0):
                    if p["asset"].startswith("dcl-"):
                        continue
                    if any(w in p["asset"] for w in FLOOR):                  # floor assets: the up-facing triangles are the floor, the steep ones (snow banks) are drawn surface
                        nq = np.cross(p["tris"][:, 1] - p["tris"][:, 0], p["tris"][:, 2] - p["tris"][:, 0])
                        up = nq[:, 1] / np.maximum(np.linalg.norm(nq, axis=1), 1e-12) >= 0.5
                        FL.append(p["tris"][up])
                        NF.append(p["tris"][~up])
                    else:
                        NF.append(p["tris"])
            if not FL:
                continue
            FL = np.concatenate(FL)
            FL = FL[rl.tri_area(FL) > 1e-7]
            nn = np.cross(FL[:, 1] - FL[:, 0], FL[:, 2] - FL[:, 0])
            FL = FL[nn[:, 1] / np.maximum(np.linalg.norm(nn, axis=1), 1e-12) > 0.5]
            NF = np.concatenate(NF) if NF else np.zeros((0, 3, 3))
            NF = NF[rl.tri_area(NF) > 1e-7] if len(NF) else NF
            print("  tile %d,%d: %d candidates, render %d floor / %d other tris (%.0f s)" % (cx, cz, len(sel), len(FL), len(NF), time.time() - t0), flush=True)
            kf = _Near(FL)
            kn = _Near(NF) if len(NF) else None
            for j in sel:
                t = T[j]
                if not kf.within(t[np.argmin(t[:, 1])], 0.3):
                    continue                                          # does not stand on the floor snow (a roof, a wall of a drawn prop, an air-borne trim)
                if kn is not None and any(kn.within(p, near) for p in (t.mean(0), t[0], t[1], t[2])):
                    continue
                rows.append(j)
        print("%s: %d steep standing triangles on floor snow with no drawn non-floor surface within %.2f m" % (lv, len(rows), near), flush=True)
        for j in rows:
            print("  %s item %d key %#x %s  ny %.2f area %.3f h %.2f  %s" % (lv, int(I[j]), int(K[j]), "STOCK" if rl.tri_key(T[j]) in stock else "OURS ", ny[j], ln[j] / 2, h[j], np.round(T[j], 2).tolist()), flush=True)
        tot += len(rows)
    return 1 if tot else 0


if __name__ == "__main__":
    sys.exit(main())
