"""Snow Stitch (connect): close the gap between two snow meshes (e.g. pat-post-office-alley-snow <-> pat-supermarket-ext-terrain-chunk-b).

  The Scene Editor's Geometry edit window has the same algorithm in C# (SnowStitch.cs); this module is the offline reference and the CLI the
  verification uses.  Both write standard "morph" geoedit entries (op "displace", level_morph.py): the vertices of ONE mesh move by a per-position
  field; every render vertex and every collision vertex of the stitch zone goes through the SAME field function (level_morph.displace_fn), so
  render and collision cannot diverge.

  boundary  open edges of each mesh (triangle edges used once, vertices welded by position).
  pairing   every boundary vertex of A looks for the nearest point on B's open boundary (and vice versa) within max_gap_h (horizontal) and
            max_gap_v (vertical).  The pair meets at the midpoint: delta = (q - a) / 2.  A move longer than max_move is NOT done (reported: gap
            too wide, extend with the snow tool first) - no stretched triangles.
  falloff   vertices of the mesh within `ring` metres (horizontal) of a moved boundary vertex follow with the delta of the nearest moved vertex
            times a smoothstep (no cliff at the end of the blend).
  python snow_stitch.py <key> <levelA> <assetA> <meshA> <levelB> <assetB> <meshB> --render-a PAK --render-b PAK --out entries.json
         [--max-h 1.5 --max-v 0.5 --ring 2 --max-move 1 --n 1]
"""
import json
import os
import re
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

DEFAULTS = {"max_gap_h": 1.5, "max_gap_v": 0.5, "ring": 2.0, "max_move": 1.0, "zone": 0.5}
WELD = 0.002


def weld(W, I):
    """-> (unique positions U, tris over U (live only))"""
    key = np.rint(W / WELD).astype(np.int64)
    _, first, inv = np.unique(key, axis=0, return_index=True, return_inverse=True)
    inv = inv.reshape(-1)
    T = inv[I]
    T = T[(T[:, 0] != T[:, 1]) & (T[:, 1] != T[:, 2]) & (T[:, 0] != T[:, 2])]
    return W[first], T


def boundary(U, T):
    """-> (vertex ids on open edges, segments (S,2) of unique-vertex ids)"""
    E = np.concatenate([T[:, [0, 1]], T[:, [1, 2]], T[:, [2, 0]]])
    E.sort(axis=1)
    e, cnt = np.unique(E, axis=0, return_counts=True)
    seg = e[cnt == 1]
    return np.unique(seg), seg


def nearest_on_segments(P, A, B):
    """nearest point of the segments A[k]-B[k] to each P (chunked) -> (points, distances)"""
    out = np.zeros_like(P)
    dist = np.full(len(P), np.inf)
    AB = B - A
    L2 = np.maximum((AB * AB).sum(1), 1e-12)
    for s in range(0, len(P), 128):
        p = P[s:s + 128]
        t = np.clip(((p[:, None, :] - A[None]) * AB[None]).sum(2) / L2[None], 0, 1)
        q = A[None] + t[..., None] * AB[None]
        d = np.linalg.norm(q - p[:, None, :], axis=2)
        k = d.argmin(1)
        r = np.arange(len(p))
        out[s:s + 128] = q[r, k]
        dist[s:s + 128] = d[r, k]
    return out, dist


def raster(tris, x0, z0, nx, nz, CELL):
    """top-most height per cell of (N,3,3) triangles (barycentric on xz) -> (nz, nx) with nan = no triangle; layers: also a second array with the lowest height"""
    top = np.full((nz, nx), -np.inf)
    low = np.full((nz, nx), np.inf)
    for t in tris:
        xs, zs = t[:, 0], t[:, 2]
        i0, i1 = int(np.floor((xs.min() - x0) / CELL)), int(np.ceil((xs.max() - x0) / CELL))
        j0, j1 = int(np.floor((zs.min() - z0) / CELL)), int(np.ceil((zs.max() - z0) / CELL))
        i0, j0, i1, j1 = max(i0, 0), max(j0, 0), min(i1, nx - 1), min(j1, nz - 1)
        if i0 > i1 or j0 > j1:
            continue
        den = (t[1, 0] - t[0, 0]) * (t[2, 2] - t[0, 2]) - (t[2, 0] - t[0, 0]) * (t[1, 2] - t[0, 2])
        if abs(den) < 1e-12:
            continue
        gx = x0 + (np.arange(i0, i1 + 1) + 0.5) * CELL
        gz = z0 + (np.arange(j0, j1 + 1) + 0.5) * CELL
        X, Z = np.meshgrid(gx, gz)
        v = ((X - t[0, 0]) * (t[2, 2] - t[0, 2]) - (t[2, 0] - t[0, 0]) * (Z - t[0, 2])) / den
        w = ((t[1, 0] - t[0, 0]) * (Z - t[0, 2]) - (X - t[0, 0]) * (t[1, 2] - t[0, 2])) / den
        u = 1 - v - w
        e = -1e-4
        ins = (u >= e) & (v >= e) & (w >= e)
        if not ins.any():
            continue
        Y = u * t[0, 1] + v * t[1, 1] + w * t[2, 1]
        sub_t = top[j0:j1 + 1, i0:i1 + 1]
        sub_l = low[j0:j1 + 1, i0:i1 + 1]
        sub_t[ins] = np.maximum(sub_t[ins], Y[ins])
        sub_l[ins] = np.minimum(sub_l[ins], Y[ins])
    top[~np.isfinite(top)] = np.nan
    low[~np.isfinite(low)] = np.nan
    return top, low


def smooth(d, R):
    s = np.clip(1.0 - d / R, 0.0, 1.0)
    return s * s * (3 - 2 * s)


def plan_side(U, T, Uo, To, prm):
    """moves for mesh (U, T) against the other mesh (Uo, To) -> dict(delta (n,3) for every vertex of U, moved ids, too_wide, seam)"""
    bv, _ = boundary(U, T)
    bvo, sego = boundary(Uo, To)
    delta = np.zeros((len(U), 3))
    moved = []
    too_wide = 0
    if not len(bvo) or not len(bv):
        return {"delta": delta, "moved": np.array([], int), "too_wide": 0, "seam": 0}
    q, _ = nearest_on_segments(U[bv], Uo[sego[:, 0]], Uo[sego[:, 1]])
    dh = np.linalg.norm((q - U[bv])[:, [0, 2]], axis=1)
    dv = np.abs(q[:, 1] - U[bv][:, 1])
    cand = (dh <= prm["max_gap_h"]) & (dv <= prm["max_gap_v"])
    for k in np.nonzero(cand)[0]:
        mv = (q[k] - U[bv[k]]) * 0.5
        if np.linalg.norm(mv) > prm["max_move"]:
            too_wide += 1
            continue
        delta[bv[k]] = mv
        moved.append(bv[k])
    moved = np.array(moved, int)
    if len(moved):
        from scipy.spatial import cKDTree
        d2, j = cKDTree(U[moved][:, [0, 2]]).query(U[:, [0, 2]], k=1, distance_upper_bound=prm["ring"])
        ring = np.isfinite(d2)
        ring[moved] = False
        idx = np.nonzero(ring)[0]
        delta[idx] = delta[moved[j[idx]]] * smooth(d2[idx], prm["ring"])[:, None]
    return {"delta": delta, "moved": moved, "too_wide": too_wide, "seam": len(moved)}


def plan_pair(WA, IA, WB, IB, prm=None):
    prm = dict(DEFAULTS, **(prm or {}))
    UA, TA = weld(WA, IA)
    UB, TB = weld(WB, IB)
    return (UA, TA, plan_side(UA, TA, UB, TB, prm)), (UB, TB, plan_side(UB, TB, UA, TA, prm)), prm


def make_entry(name, level, asset, mesh, W, U, T, plan, prm):
    """W: world positions of every vertex of the render submesh; U, T (welded positions + triangles) and plan from plan_pair.
    The entry carries the ORIGINAL surface triangles that touch a moving vertex with the per-vertex move ("field", level_morph.displace_fn)."""
    delta = plan["delta"]
    mv = (np.abs(delta) > 1e-5).any(1)
    if not mv.any():
        return None
    from scipy.spatial import cKDTree
    tsel = T[mv[T].any(1)]
    used, inv = np.unique(tsel, return_inverse=True)
    inv = inv.reshape(-1, 3)
    pts = U[mv]
    d, _ = cKDTree(pts).query(W, k=1, distance_upper_bound=2 * WELD)
    verts = np.nonzero(np.isfinite(d))[0]
    lo = U[used].min(0) - [prm["zone"], 0.8, prm["zone"]]
    hi = U[used].max(0) + [prm["zone"], 0.8, prm["zone"]]
    chk = pts[np.linspace(0, len(pts) - 1, min(6, len(pts))).astype(int)]
    field = {"v": np.round(np.c_[U[used], delta[used]], 4).tolist(), "t": inv.tolist()}
    e = {"kind": "morph", "version": 1, "name": name, "level": level, "asset": asset, "mesh": mesh, "verts": [int(v) for v in verts],
         "check": np.round(chk, 4).tolist(), "op": "displace", "field": field,
         "seam": np.round(U[plan["moved"]], 3).tolist(),                       # the moved open-boundary vertices (information: preview / verification)
         "box": np.round(np.r_[lo, hi], 3).tolist(), "collision": "match", "collision_triangles": 0, "active": True}
    # the stitched seam curve (boundary edges whose both ends moved, at their NEW positions): level_morph derives the collision field from it at build time
    _, bseg = boundary(U, T)
    ismv = np.zeros(len(U), bool)
    ismv[plan["moved"]] = True
    sg = bseg[ismv[bseg].all(1)]
    P1 = U + plan["delta"]
    e["seam_segs"] = np.round(np.stack([P1[sg[:, 0]], P1[sg[:, 1]]], 1), 4).tolist()
    return e


def load_sub(render_pak, asset, mesh, near=None):
    """-> (world positions, live triangles, submesh index) of the (largest / nearest-to-`near`) non-shadow submesh of that asset + mesh name"""
    import level_morph as lm
    R = lm.Render(render_pak)
    rx = re.compile("(^|\\|)" + re.escape(mesh) + "$")
    best = None
    for i, sm in enumerate(R.p.submeshes):
        if not rx.search(sm["name"]) or R.p.pos_stream(sm) is None or len(R.owners.get(i, [])) > 1 or "shadow" in sm["name"].lower():
            continue
        if asset and asset not in sm["name"] and not any(asset in nm for it in R.owners.get(i, []) for nm, ids in it.names if i in ids):
            continue
        s = R.sub(i)
        W = s.world()
        I, live = s.live_tris()
        sc = -len(W) if near is None else float(np.linalg.norm(W.mean(0) - near))
        if best is None or sc < best[0]:
            best = (sc, i, W, I[live])
    if best is None:
        raise SystemExit("no submesh %s / %s in %s" % (asset, mesh, render_pak))
    return best[2], best[3], best[1]


def main(a):
    o, pos = {}, []
    it = iter(a)
    for x in it:
        if x.startswith("--"):
            o[x[2:]] = next(it)
        else:
            pos.append(x)
    _key, la, aa, ma, lb, ab, mb = pos
    prm = {k2: float(o[k1]) for k1, k2 in (("max-h", "max_gap_h"), ("max-v", "max_gap_v"), ("ring", "ring"), ("max-move", "max_move"), ("zone", "zone")) if k1 in o}
    WA, IA, _ = load_sub(o["render-a"], aa, ma)
    WB, IB, _ = load_sub(o["render-b"], ab, mb, near=WA.mean(0))
    (UA, TA, pa), (UB, TB, pb), prm = plan_pair(WA, IA, WB, IB, prm)
    print("A moved %d (too wide %d), B moved %d (too wide %d)" % (pa["seam"], pa["too_wide"], pb["seam"], pb["too_wide"]))
    out = []
    for (lv, asset, mesh, W, U, T, pl) in ((la, aa, ma, WA, UA, TA, pa), (lb, ab, mb, WB, UB, TB, pb)):
        e = make_entry("%s stitch %s" % (asset, o.get("n", "1")), lv, asset, mesh, W, U, T, pl, prm)
        if e:
            out.append(e)
    json.dump(out, open(o["out"], "w"), indent=1)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
