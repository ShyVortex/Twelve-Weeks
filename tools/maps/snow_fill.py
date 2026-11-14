"""Snow seams the natural way: facing-aware stitch with overlap, tuck-under skirt, door-frame snow tongue (a gap that no Snow Stitch slider
closes; no snow on the ground in the doorway).

  What the level paks allow (measured, re/maps/level-edit.md 13): the render vertex / index buffers of a baked mesh cannot grow (every snow submesh near
  the Supermarket has 0 free vertex slots and 0 degenerate triangles), so a 'fill' op that ADDS render triangles is not possible; collision triangles can be
  added, render ones cannot.  Everything here therefore MOVES existing snow vertices through the standard op "displace" (level_morph.displace_fn: render +
  collision follow one field), i.e. the same entries the Scene Editor writes; the build needs no new machinery.

  facing stitch  The plain pairing of snow_stitch.py failed like this: an open edge that runs ALONG a wall foot has no snow partner at all, but the nearest point
                 of the other mesh's open edge is 1-1.5 m away along the wall, so the wall-foot edge was dragged towards it, the more the larger the max gap.
                 A pair is accepted only when the other edge FACES this one: vector to the partner within 60 deg of this edge's outward normal and the partner
                 edge within 35 deg of parallel.  Both sides move to the midpoint plus OVERLAP (5 cm each; the `lower` mesh 1.5 cm lower), so no hairline crack
                 stays where a vertex meets the middle of the other edge.
  tuck (skirt)   open-edge vertices with no snow partner that face a solid surface (wall / step / floor) within `tuck_max` slide onto it and 6 cm into it (walls)
                 or dive 2 cm under it (floors): the snow edge ends INSIDE the neighbour, no sky or void shows.
  tongue         snow ground carried into a door frame: the open-edge vertices along the door span are pulled `length` m (0.6-1.2, irregular) through the frame,
                 their height falls to the inside floor + 1 cm at the tip, the vertices behind follow with a falloff.  Collision untouched.
"""
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import snow_stitch as ss  # noqa: E402

FACE_COS = 0.5            # cos 60 deg: partner direction vs outward normal
PARALLEL_COS = 0.82       # cos 35 deg: partner edge vs own edge
OVERLAP = 0.05
NEAR_H = 0.5              # m: partners this close are accepted without the parallel test
LOWER = 0.015
DEFAULTS = dict(ss.DEFAULTS, tuck_max=0.5)


def seg_nearest_idx(P, A, B):
    """nearest point on segments A[k]-B[k] to each P -> (points, distances, segment index)"""
    out = np.zeros_like(P)
    dist = np.full(len(P), np.inf)
    idx = np.zeros(len(P), int)
    AB = B - A
    L2 = np.maximum((AB * AB).sum(1), 1e-12)
    for s in range(0, len(P), 128):
        p = P[s:s + 128]
        t = np.clip(((p[:, None, :] - A[None]) * AB[None]).sum(2) / L2[None], 0, 1)
        q = A[None] + t[..., None] * AB[None]
        d = np.linalg.norm(q - p[:, None, :], axis=2)
        k = d.argmin(1)
        r = np.arange(len(p))
        out[s:s + 128], dist[s:s + 128], idx[s:s + 128] = q[r, k], d[r, k], k
    return out, dist, idx


def border_frames(U, T, bv, seg):
    """per border vertex: horizontal unit tangent and outward normal (away from the mesh interior): {id: (t, n)}"""
    cen = U[T].mean(1)
    inc = {}
    for ti, t in enumerate(T):
        for v in t:
            inc.setdefault(int(v), []).append(ti)
    sv = {}
    for a, b in seg:
        sv.setdefault(int(a), []).append(int(b))
        sv.setdefault(int(b), []).append(int(a))
    out = {}
    for v in bv:
        v = int(v)
        tg = np.zeros(2)
        for o in sv.get(v, []):
            d = (U[o] - U[v])[[0, 2]]
            d /= max(np.linalg.norm(d), 1e-9)
            if tg @ d < 0:
                d = -d
            tg += d
        if np.linalg.norm(tg) < 1e-9:
            continue
        tg /= np.linalg.norm(tg)
        n = np.array([-tg[1], tg[0]])
        c = cen[inc[v]].mean(0)[[0, 2]] - U[v][[0, 2]]
        if n @ c > 0:
            n = -n
        out[v] = (tg, n)
    return out


def inbox(p, box):
    return box is None or (box[0] <= p[0] <= box[3] and box[2] <= p[2] <= box[5])


def facing_pairs(U, T, Uo, To, prm, box=None):
    """-> ({border vertex: partner point}, stats)"""
    bv, seg = ss.boundary(U, T)
    bvo, sego = ss.boundary(Uo, To)
    st = {"border": len(bv), "far": 0, "not_facing": 0, "too_wide": 0, "paired": 0}
    pair = {}
    if not len(bvo) or not len(bv):
        return pair, st
    fr = border_frames(U, T, bv, seg)
    sd = (Uo[sego[:, 1]] - Uo[sego[:, 0]])[:, [0, 2]]
    sd /= np.maximum(np.linalg.norm(sd, axis=1, keepdims=True), 1e-9)
    ids = [int(v) for v in bv if int(v) in fr and inbox(U[v], box)]
    q, _, k = seg_nearest_idx(U[ids], Uo[sego[:, 0]], Uo[sego[:, 1]])
    for j, v in enumerate(ids):
        dq = q[j] - U[v]
        dh = float(np.hypot(dq[0], dq[2]))
        if dh > prm["max_gap_h"] or abs(dq[1]) > prm["max_gap_v"]:
            st["far"] += 1
            continue
        tg, n = fr[v]
        if dh > 0.03:
            u = np.array([dq[0], dq[2]]) / dh
            near = dh <= NEAR_H                      # closing a corner / sliver: any edge direction, it only has to lie in front
            if u @ n < (0.0 if near else FACE_COS) or (not near and abs(sd[k[j]] @ tg) < PARALLEL_COS):
                st["not_facing"] += 1
                continue
        if np.linalg.norm(dq) * 0.5 + OVERLAP > prm["max_move"]:
            st["too_wide"] += 1
            continue
        pair[v] = q[j]
        st["paired"] += 1
    return pair, st


def ring_follow(U, delta, moved, ring):
    from scipy.spatial import cKDTree
    if not len(moved):
        return delta
    d2, j = cKDTree(U[moved][:, [0, 2]]).query(U[:, [0, 2]], k=1, distance_upper_bound=ring)
    r = np.isfinite(d2)
    r[moved] = False
    idx = np.nonzero(r)[0]
    delta[idx] = delta[moved[j[idx]]] * ss.smooth(d2[idx], ring)[:, None]
    return delta


def plan_facing(U, T, Uo, To, lower, prm=None, solids=None, box=None):
    """facing stitch + overlap (+ tuck against solids = (points (M,3), normals (M,3)) of non-snow surfaces) -> plan dict (snow_stitch.plan_side keys + stats)"""
    prm = dict(DEFAULTS, **(prm or {}))
    pair, st = facing_pairs(U, T, Uo, To, prm, box)
    bv0, seg0 = ss.boundary(U, T)
    fr0 = border_frames(U, T, bv0, seg0)
    delta = np.zeros((len(U), 3))
    moved = []
    for v, q in pair.items():
        dq = q - U[v]
        mv = dq * 0.5
        n = fr0[v][1]
        mv = mv + np.array([n[0], 0, n[1]]) * OVERLAP        # overlap along the edge's own outward normal (stable where both edges coincide)
        if lower:
            mv = mv + [0, -LOWER, 0]
        delta[v] = mv
        moved.append(v)
    moved = np.array(moved, int)
    tucked = []
    if solids is not None and len(solids[0]):
        from scipy.spatial import cKDTree
        P, N = solids
        tree = cKDTree(P)
        bv, seg = ss.boundary(U, T)
        fr = border_frames(U, T, bv, seg)
        for v in bv:
            v = int(v)
            if v in pair or v not in fr or not inbox(U[v], box):
                continue
            d, j = tree.query(U[v], k=1, distance_upper_bound=prm["tuck_max"])
            if not np.isfinite(d):
                continue
            dq = P[j] - U[v]
            hl = float(np.hypot(dq[0], dq[2]))
            tg, n = fr[v]
            if hl > 0.02 and (np.array([dq[0], dq[2]]) / hl) @ n < FACE_COS:
                continue
            if abs(N[j][1]) < 0.5:                       # wall: slide onto it and 6 cm into it, height kept
                u = np.array([dq[0], dq[2]]) / hl if hl > 1e-6 else -N[j][[0, 2]] / max(np.linalg.norm(N[j][[0, 2]]), 1e-9)
                delta[v] = [dq[0] + u[0] * 0.06, 0.0, dq[2] + u[1] * 0.06]
            else:                                        # floor / step top: end 2 cm under its surface
                delta[v] = [dq[0], dq[1] - 0.02, dq[2]]
            tucked.append(v)
    allm = np.concatenate([moved, np.array(tucked, int)]) if tucked else moved
    delta = ring_follow(U, delta, allm.astype(int), prm["ring"])
    st["tucked"] = len(tucked)
    return {"delta": delta, "moved": moved, "tucked": np.array(tucked, int), "stats": st, "seam": len(moved), "too_wide": st["too_wide"]}


def tongue_plan(U, T, p0, p1, direction, length, floor_y, seed=7, ring=1.0, jitter=0.25, band=0.35, solids=None):
    """door-frame tongue along the open edge between the xz points p0 and p1 (the door span); direction = inward unit xz vector"""
    bv, _ = ss.boundary(U, T)
    p0, p1, dr = np.asarray(p0, float), np.asarray(p1, float), np.asarray(direction, float)
    ab = p1 - p0
    L = float(np.linalg.norm(ab))
    ab /= L
    ph = np.random.RandomState(seed).rand(2) * 6.28
    delta = np.zeros((len(U), 3))
    moved = []
    ftree = fy = None
    if solids is not None and len(solids[0]):
        from scipy.spatial import cKDTree
        up = solids[1][:, 1] > 0.5
        if up.any():
            ftree, fy = cKDTree(solids[0][up][:, [0, 2]]), solids[0][up][:, 1]
    for v in bv:
        rel = U[v][[0, 2]] - p0
        s = float(rel @ ab)
        off = abs(float(rel @ np.array([-ab[1], ab[0]])))
        if s < -0.05 or s > L + 0.05 or off > band:
            continue
        w = float(np.sin(np.pi * np.clip(s / L, 0, 1)) ** 0.6)        # full length mid span, tapering to 0 at the jambs
        ln = length * w * (1 + jitter * (np.sin(s * 5.1 + ph[0]) * 0.6 + np.sin(s * 11.3 + ph[1]) * 0.4))
        if ln < 0.05:
            continue
        fl = floor_y                                           # the floor under the tip (lowest up-facing surface within 15 cm of the tip, below the snow)
        if ftree is not None:
            tip = U[v][[0, 2]] + dr * ln
            nb = [i for i in ftree.query_ball_point(tip, 0.15) if fy[i] < U[v][1] + 0.02]
            if nb:
                fl = float(np.max(fy[nb]))
        delta[v] = [dr[0] * ln, (fl + 0.01 - U[v][1]) * min(1.0, ln / max(length * 0.5, 1e-6)), dr[1] * ln]
        moved.append(v)
    moved = np.array(moved, int)
    delta = ring_follow(U, delta, moved, ring)
    return {"delta": delta, "moved": np.array([], int), "seam": 0, "too_wide": 0, "tongue_verts": len(moved)}


def solids_from(tris, is_snow, lo, hi, step=0.12):
    """sample points + normals on the non-snow triangles (dicts with name, T (n,3,3)) inside the box"""
    P, N = [], []
    rng = np.random.RandomState(1)
    for t in tris:
        if is_snow(t["name"]):
            continue
        T = t["T"]
        T = T[((T.mean(1) >= lo) & (T.mean(1) <= hi)).all(1)]
        if not len(T):
            continue
        n = np.cross(T[:, 1] - T[:, 0], T[:, 2] - T[:, 0])
        ar = np.linalg.norm(n, axis=1)
        ok = ar > 1e-8
        T, n, ar = T[ok], n[ok] / ar[ok, None], ar[ok]
        k = np.clip((ar / 2 / (step * step)).astype(int) + 1, 1, 40)
        for rep in range(int(k.max())):
            sel = k > rep
            r = rng.rand(int(sel.sum()), 2)
            fl = r.sum(1) > 1
            r[fl] = 1 - r[fl]
            a, b, c = T[sel, 0], T[sel, 1], T[sel, 2]
            P.append(a + (b - a) * r[:, :1] + (c - a) * r[:, 1:])
            N.append(n[sel])
    return (np.concatenate(P), np.concatenate(N)) if P else (np.zeros((0, 3)), np.zeros((0, 3)))


# =============================================================================================== jackson-market auto edits
LEVEL = "pat-jackson-supermarket"
A_ASSET, A_MESH = "pat-supermarket-ext-terrain-chunk-c", "snow_chunk_renderShape_shader0_merged_partition0"
B_ASSET, B_MESH = "pat-post-office-alley-snow", "alleyShape_shader0_merged_partition0"
# (name, p0 xz, p1 xz, inward direction xz, length m, inside floor height): door spans on the open edge of the alley snow (x = -506.03 hall doorway, x = -509.02 gate)
TONGUES = [("hall doorway snow tongue", (-506.03, 280.17), (-506.03, 282.17), (1.0, 0.0), 0.95, 18.08, 11),
           ("gate doorway snow tongue", (-509.02, 279.7), (-509.02, 282.3), (-1.0, 0.0), 0.9, 17.88, 23)]
SEAM_BOX = (-507.0, 0.0, 272.9, -503.0, 0.0, 276.6)
HALL_S = ((-512.6, 282.55), (-509.0, 282.55))
CORNER_BOX = (-509.3, 0.0, 285.9, -508.4, 0.0, 286.7)


def region_tris(pak, lo, hi):
    import level_morph as lm
    import struct
    R = lm.Render(pak)
    out = []
    for i, sm in enumerate(R.p.submeshes):
        if R.p.pos_stream(sm) is None or len(R.owners.get(i, [])) > 1 or "shadow" in sm["name"].lower():
            continue
        o = sm["offset"]
        a, b = np.array(struct.unpack_from("<3f", R.p.d, o)), np.array(struct.unpack_from("<3f", R.p.d, o + 16))
        ow = R.owners.get(i, [])
        if ow:
            c = np.array([[x, y, z, 1.0] for x in (a[0], b[0]) for y in (a[1], b[1]) for z in (a[2], b[2])]) @ ow[0].M
            a, b = c[:, :3].min(0), c[:, :3].max(0)
        if (b < lo).any() or (a > hi).any() or (b - a).max() > 400:
            continue
        s = R.sub(i)
        W = s.world()
        I, live = s.live_tris()
        T = W[I[live]]
        if len(T):
            out.append({"name": sm["name"], "T": T})
    return out


def build_auto(out_dir, log=print):
    """the auto entries of jackson-market from the level-edit output (out_dir/morph/<level>.pak = the state the entries apply on)"""
    pak = os.path.join(out_dir, "morph", LEVEL + ".pak")
    if not os.path.exists(pak):
        pak = os.path.join(out_dir, LEVEL + ".pak")
    WA, IA, _ = ss.load_sub(pak, A_ASSET, A_MESH)
    WB, IB, ib = ss.load_sub(pak, B_ASSET, B_MESH)
    UA, TA = ss.weld(WA, IA)
    UB, TB = ss.weld(WB, IB)
    lo, hi = np.array((-508.0, 17.0, 272.0)), np.array((-502.0, 20.0, 278.0))
    tris = region_tris(pak, lo - 1, hi + 1)
    tris2 = region_tris(pak, np.array((-512.0, 16.0, 277.0)), np.array((-503.0, 20.0, 285.0)))
    solids = solids_from(tris, lambda n: "snow" in n.lower() or "terrain" in n.lower(), lo, hi)
    prm = dict(DEFAULTS)
    entries = []
    pa = plan_facing(UA, TA, UB, TB, False, prm, solids, SEAM_BOX)
    pb = plan_facing(UB, TB, UA, TA, True, prm, solids, SEAM_BOX)
    log("seam chunk-c <-> alley snow: A %s  B %s" % (pa["stats"], pb["stats"]))
    for nm, asset, mesh, W, U, T, pl in (("chunk-c seam overlap", A_ASSET, A_MESH, WA, UA, TA, pa), ("alley snow seam overlap", B_ASSET, B_MESH, WB, UB, TB, pb)):
        e = ss.make_entry(nm, LEVEL, asset, mesh, W, U, T, pl, dict(ss.DEFAULTS))
        if e:
            e["collision"] = "none"      # the overlap is <= 20 cm; moving the Havok vertices of the seam hit a packed per-section vertex (build refused), the hull is coarser than that anyway
            e["seam_segs"] = []
            e["auto"] = "snow_fill facing stitch + overlap + tuck"
            entries.append(e)
    # the corner where the alley snow meets chunk-b (alley level) leaves a 0.2 x 0.1 m void at (-508.95, 286.35): one-sided close (only the alley snow moves,
    # chunk-b belongs to another level and the hand-made stitch entries), full move to the partner edge + 3 cm overlap
    apak = os.path.join(out_dir, "morph", "pat-jackson-alley.pak")
    if not os.path.exists(apak):
        apak = os.path.join(out_dir, "pat-jackson-alley.pak")
    if os.path.exists(apak):
        WK, IK, _ = ss.load_sub(apak, "pat-supermarket-ext-terrain-chunk-b", "snowShape_shader1_merged_partition0")
        UK, TK = ss.weld(WK, IK)
        pair, st = facing_pairs(UB, TB, UK, TK, dict(DEFAULTS, max_move=0.6), CORNER_BOX)
        delta = np.zeros((len(UB), 3))
        mv = []
        bvb, segb = ss.boundary(UB, TB)
        frb = border_frames(UB, TB, bvb, segb)
        for v, q in pair.items():
            dq = q - UB[v]
            if np.hypot(dq[0], dq[2]) < 0.004:
                continue
            n = frb[v][1]
            delta[v] = dq + np.array([n[0], -0.01, n[1]]) * 0.03
            mv.append(v)
        log("corner close vs chunk-b: %s, %d vertices moved" % (st, len(mv)))
        if mv:
            delta = ring_follow(UB, delta, np.array(mv, int), 0.6)
            e = ss.make_entry("alley snow corner close", LEVEL, B_ASSET, B_MESH, WB, UB, TB, {"delta": delta, "moved": np.array([], int)}, dict(ss.DEFAULTS))
            if e:
                e["collision"] = "none"
                e["seam_segs"] = []
                e["auto"] = "snow_fill one-sided corner close"
                entries.append(e)
    tlo, thi = np.array((-511.5, 17.0, 278.0)), np.array((-503.5, 19.0, 284.0))
    tsol = solids_from(tris2, lambda n: "snow" in n.lower() or "terrain" in n.lower(), tlo, thi, 0.06)
    import level_morph as lm
    seam = [e for e in entries if e["mesh"] == B_MESH or e["mesh"] == A_MESH]
    if seam:                                            # later entries are planned on the REAL state the earlier ones leave (their check positions must match in the build)
        R = lm.Render(pak)
        for e in seam:
            lm.apply_morph_render(R, e, lambda *a: None, None)
            lm.flush_render(R, lambda *a: None)
            R.cache.clear()
            R.p = lm._reparse(R)
        s = R.sub(ib)
        WB = s.world()
        I, live = s.live_tris()
        IB = I[live]
    UB, TB = ss.weld(WB, IB)
    # hall south edge (the removed wall at z 282.5, x -512..-509): the alley-level snow ends in a 0.4 m cliff above the post-office floor (17.88) with a 10 cm slit
    # in front of it: ramp the snow's south edge 0.9 m over the floor (same tongue, direction -z), tip = floor + 1 cm
    if os.path.exists(apak):
        UK2, TK2 = ss.weld(WK, IK)
        ipak = os.path.join(out_dir, "morph", "pat-jackson-supermarket-int.pak")
        if not os.path.exists(ipak):
            ipak = os.path.join(out_dir, "pat-jackson-supermarket-int.pak")
        itris = region_tris(ipak, np.array((-513.0, 16.0, 279.0)), np.array((-508.0, 20.0, 283.0))) if os.path.exists(ipak) else []
        fsol = solids_from(itris + tris2, lambda n: "snow" in n.lower() or "terrain" in n.lower(), np.array((-513.0, 17.0, 280.0)), np.array((-508.0, 19.0, 283.0)), 0.06)
        pl = tongue_plan(UK2, TK2, HALL_S[0], HALL_S[1], (0.0, -1.0), 0.9, 17.88, 31, solids=fsol)
        log("hall south ramp: %d edge vertices pulled" % pl["tongue_verts"])
        e = ss.make_entry("hall south edge snow ramp", "pat-jackson-alley", "pat-supermarket-ext-terrain-chunk-b", "snowShape_shader1_merged_partition0", WK, UK2, TK2, pl, dict(ss.DEFAULTS))
        if e:
            e["collision"] = "none"
            e["seam_segs"] = []
            e["auto"] = "snow_fill hall south ramp"
            entries.append(e)
    for nm, p0, p1, d, ln, fy, seed in TONGUES:
        pl = tongue_plan(UB, TB, p0, p1, d, ln, fy, seed, solids=tsol)
        e = ss.make_entry(nm, LEVEL, B_ASSET, B_MESH, WB, UB, TB, pl, dict(ss.DEFAULTS))
        log("%s: %d edge vertices pulled" % (nm, pl["tongue_verts"]))
        if e:
            e["collision"] = "none"
            e["seam_segs"] = []
            e["auto"] = "snow_fill door tongue"
            entries.append(e)
    return entries


if __name__ == "__main__":
    import json
    a = sys.argv[1:]
    if a and a[0] == "auto":
        d = a[a.index("--dir") + 1] if "--dir" in a else os.path.join(os.path.dirname(os.path.dirname(HERE)), "re", "maps", "level-edit-cache", "out")
        ent = build_auto(d)
        dst = os.path.join(HERE, "data", "jackson-market-geoedits-auto.json")
        json.dump({"key": "jackson-market", "note": "written by snow_fill.py auto (re-run after a Scene Editor save that touches the Supermarket snow); never edited by the editor", "edits": ent},
                  open(dst, "w", encoding="utf-8"), indent=1)
        print("wrote %s: %d entries" % (dst, len(ent)))
    else:
        print(__doc__)
