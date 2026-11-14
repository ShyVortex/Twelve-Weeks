"""Scene Editor "Morph" and "Detach" geometry edits, applied for real to a level's render pak, its Havok collision pak and the shadow proxies.

  tools/maps/data/<key>-geoedits.json entries (geoedit.py hands them to level_edit.build_edits as actions "morph" / "detach"; level_edit.build_edits
  runs them AFTER the ordinary edits of the level, on their output, and writes its paks to <out>/morph/):

  {"kind": "morph", "version": 1, "name", "level": "pat-jackson-supermarket", "asset": "<asset or empty>", "mesh": "<submesh name tail>",
   "verts": [vertex indices of that submesh],         # the selection (render vertex ids)
   "check": [[x, y, z], ...],                         # up to 6 of their world positions: the build refuses to run when they do not match the pak
   "op": "flatten" | "translate" | "snow" | "displace",  "y": 12.3 | "delta": [dx, dy, dz],
   "field": {"v": [[x y z dx dy dz]..], "t": [[i j k]..]},        # op "displace" (Snow Stitch): see displace_fn; "cfield" + "cbox" the same for the collision surface
   "bank_h": 0.25, "bank_w": 1.5, "rough": 0.03, "seed": 123,   # op "snow" only (y = the picked base level), see snow_fn
   "collision": "match" | "box" | "none",             # match = collision vertices on the same positions, box = every collision vertex inside `box`
   "box": [x0 y0 z0 x1 y1 z1],                        # world AABB of the selected vertices
   "tol": 0.0025, "active": true}

  {"kind": "detach", "version": 1, "name", "level", "asset", "mesh", "tris": [triangle indices], "check": [...],
   "transform": {"pivot": [x y z], "rotation": [qx qy qz qw], "translation": [dx dy dz]},   # p' = R (p - pivot) + pivot + translation
   "collision": "inside" | "centroid" | "overlap" | "none", "box": [...], "active": true}

What is changed (all offline, CPU only; every failure raises, nothing broken is ever written):
  render   every vertex of every WORLD-SPACE submesh (merged / baked, one placement, the shadow proxies included) that sits on a selected position
           (tol) is moved: bit-packed position streams are re-encoded in place; when a coordinate leaves the stream's range the stream is
           shifted by whole quantisation steps (untouched vertices stay bit exact) or, if that is not enough, re-scaled; submesh AABB and the
           owning record's AABB only grow.  A vertex shared with a neighbour moves with both (the weld is by position, so seams stay closed).
  collision the shared Havok vertices on the same positions (or inside the box) are re-quantised, every primitive that uses one gets its box,
           the section codec trees, the section tree and the simd tree are refitted (move_in_place's machinery, per vertex instead of per
           primitive).  Moving out of the mesh domain raises.
  detach   the selected triangles of the render mesh move as a rigid piece; vertices shared with the rest of the mesh are first cloned into
           free vertex slots (vertices no live triangle uses); no free slots -> the build fails and says how many are missing.  The same
           triangles of the other world-space submeshes (shadow proxy) follow, or are cut if they cannot.  Collision: the Havok triangles
           selected by the mode move in place (rigid), the ones sharing vertices with the rest are removed and re-added.
Limits (see re/maps/level-edit.md section 13): normals / tangents / baked lighting of a rotated piece are not recomputed; the level's KD_TREE_2 /
VIS_INFO_1 are not re-derived (a piece moved out of its record's box is logged); there is no separate occluder item in the level paks (the
occluders are the shadow proxy submeshes, handled like render)."""
import hashlib
import json
import math
import os
import re
import struct
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.dirname(HERE)
sys.path.insert(0, TOOLS)
sys.path.insert(0, os.path.join(TOOLS, "part1"))
sys.path.insert(0, os.path.join(TOOLS, "models"))
sys.path.insert(0, HERE)
import havok_convert as hc  # noqa: E402
import ndpak  # noqa: E402
import level_edit as le  # noqa: E402

ACTIONS = ("morph", "detach")
VERSION = 1
SNAP_RADIUS = 0.4                 # metres: collision vertices this close to a selected render vertex follow it (collision "match"; the hull is coarser than the render mesh)
_SHADOW_RX = __import__("re").compile(r"shadow", __import__("re").I)   # shadow-proxy submesh names (tfrag-merge-shadows, shadowProxy)
TOL = 0.0025                      # metres: two positions closer than this are the same point (position streams step 0.02 .. 2 mm)


class MorphError(SystemExit):
    pass


def fail(msg):
    raise MorphError("level morph: " + msg)


# =============================================================================================== small maths
def quat_matrix(q):
    """3x3 rotation matrix (column vectors) of the quaternion (x, y, z, w)"""
    x, y, z, w = (float(v) for v in q)
    n = math.sqrt(x * x + y * y + z * z + w * w) or 1.0
    x, y, z, w = x / n, y / n, z / n, w / n
    return np.array([[1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
                     [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
                     [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)]])


def detach_fn(tr):
    """p' = R (p - pivot) + pivot + translation for (N,3) arrays; tr = the entry's "transform" """
    R = quat_matrix(tr.get("rotation") or [0, 0, 0, 1])
    pv = np.array(tr.get("pivot") or [0, 0, 0], float)
    t = np.array(tr.get("translation") or [0, 0, 0], float)
    return lambda P: (np.asarray(P, float) - pv) @ R.T + pv + t


SNOW_DEFAULTS = {"bank_h": 0.22, "bank_w": 1.4, "rough": 0.08, "bank_p": 3.0}   # fitted to the authored Jackson snow, re/maps/snow-morph-1103.md
SNOW_EDGE_FADE = 0.75             # metres inside the selection boundary over which the snow blends back to the original height
SNOW_STEEP = 0.5                  # |normal.y| below this = wall / prop side (not snow ground)


def snow_seed(g):
    """32-bit seed of a snow edit: the stored "seed", else FNV-1a of the edit name (the editor writes the same value)"""
    if g.get("seed") is not None:
        return int(g["seed"]) & 0xFFFFFFFF
    h = 2166136261
    for ch in str(g.get("name", "")).encode("utf-8"):
        h = ((h ^ ch) * 16777619) & 0xFFFFFFFF
    return h


def snow_waves(seed):
    """three plane waves (kx, kz, phase) from xorshift32(seed): wavelength 2..4 m, random heading (the editor ports this exactly)"""
    x = (seed & 0xFFFFFFFF) or 0x9E3779B9
    out = []

    def nxt():
        nonlocal x
        x ^= (x << 13) & 0xFFFFFFFF
        x ^= x >> 17
        x ^= (x << 5) & 0xFFFFFFFF
        return x / 4294967296.0
    for _ in range(3):
        ang, lam, ph = nxt() * 2 * math.pi, 2.0 + 2.0 * nxt(), nxt() * 2 * math.pi
        out.append((math.cos(ang) / lam * 2 * math.pi, math.sin(ang) / lam * 2 * math.pi, ph))
    return out


def snow_rough(x, z, seed):
    """deterministic low-frequency noise in [0, 1] (3 plane waves, wavelength 2..4 m)"""
    t = sum(np.sin(kx * x + kz * z + ph) for kx, kz, ph in snow_waves(seed))
    return 0.5 + 0.5 * np.clip(t / 2.0, -1.0, 1.0)


def snow_bank(d, bank_h, bank_w, bank_p=SNOW_DEFAULTS["bank_p"]):
    """drift profile: bank_h at the obstacle, bank_h * (1 - d/bank_w)^bank_p = steepest at the wall, long taper to 0 at bank_w
    (the authored snow fits h 0.23 m, W 1.4 m, p 3.0 on its mean profile)"""
    u = np.clip(1.0 - np.asarray(d, float) / max(bank_w, 1e-6), 0.0, 1.0)
    return bank_h * u ** bank_p


def snow_params(g):
    return (float(g.get("bank_h", SNOW_DEFAULTS["bank_h"])), float(g.get("bank_w", SNOW_DEFAULTS["bank_w"])),
            float(g.get("rough", SNOW_DEFAULTS["rough"])))


def snow_wall_samples(walls, base, lo_xz, hi_xz, margin, step=0.1):
    """walls: (N,3,3) world collision triangles -> (M,2) xz sample points on the projected edges of the near-vertical ones that touch the snow level"""
    if walls is None or not len(walls):
        return np.zeros((0, 2))
    n = np.cross(walls[:, 1] - walls[:, 0], walls[:, 2] - walls[:, 0])
    ln = np.linalg.norm(n, axis=1)
    steep = (ln > 1e-12) & (np.abs(n[:, 1]) < SNOW_STEEP * np.maximum(ln, 1e-12))
    y0, y1 = walls[:, :, 1].min(1), walls[:, :, 1].max(1)
    x0, x1 = walls[:, :, 0].min(1), walls[:, :, 0].max(1)
    z0, z1 = walls[:, :, 2].min(1), walls[:, :, 2].max(1)
    keep = (steep & (y1 >= base - 0.1) & (y0 <= base + 0.8) & (x1 >= lo_xz[0] - margin) & (x0 <= hi_xz[0] + margin)
            & (z1 >= lo_xz[1] - margin) & (z0 <= hi_xz[1] + margin))
    T = walls[keep][:, :, [0, 2]]
    pts = []
    for a, b in ((0, 1), (1, 2), (2, 0)):
        A, B = T[:, a], T[:, b]
        L = np.linalg.norm(B - A, axis=1)
        cls = np.clip(np.ceil(np.log2(np.maximum(L / step, 1.0))), 0, 11).astype(int)      # power-of-two sample counts per length class
        for c in np.unique(cls):
            m = cls == c
            t = np.linspace(0.0, 1.0, (1 << int(c)) + 1)
            pts.append((A[m][:, None, :] + (B - A)[m][:, None, :] * t[None, :, None]).reshape(-1, 2))
    P = np.concatenate(pts) if pts else np.zeros((0, 2))
    return np.unique(np.round(P, 3), axis=0) if len(P) else P


def snow_context(g, items):
    """per-entry context shared by render, shadow and collision: kd-tree of the wall samples (from the level's collision, None = no obstacles)"""
    from scipy.spatial import cKDTree
    box = g["box"]
    base = float(g["y"])
    bank_h, bank_w, rough = snow_params(g)
    tris = []
    for it in items or []:
        T = hc.triangles(it.mesh)[1]
        if len(T):
            m = ((T[:, :, 0].max(1) >= box[0] - bank_w - 1) & (T[:, :, 0].min(1) <= box[3] + bank_w + 1)
                 & (T[:, :, 2].max(1) >= box[2] - bank_w - 1) & (T[:, :, 2].min(1) <= box[5] + bank_w + 1))
            tris.append(T[m])
    walls = np.concatenate(tris) if tris else None
    S = snow_wall_samples(walls, base, (box[0], box[2]), (box[3], box[5]), bank_w + 1)
    return {"walls": cKDTree(S) if len(S) else None, "n_wall_samples": len(S), "bnd": None}


def snow_boundary(s, verts):
    """xz of the selected vertices that share a live triangle with an unselected vertex (= where the edit meets untouched snow)"""
    I, live = s.live_tris()
    T = I[live]
    sel = np.zeros(s.n, bool)
    sel[verts] = True
    ins = sel[T]
    mixed = ins.any(1) & ~ins.all(1)
    b = np.unique(T[mixed][ins[mixed]])
    W = s.world(b) if len(b) else np.zeros((0, 3))
    return W[:, [0, 2]]


def snow_fn(g, ctx):
    """snow top: y = base + bank(d to the nearest wall / prop) + rough(x, z), blended with the vertex's own height over SNOW_EDGE_FADE m inside the
    selection boundary.  target is never below base and never above base + bank_h + rough."""
    from scipy.spatial import cKDTree
    base = float(g["y"])
    bank_h, bank_w, rough = snow_params(g)
    seed = snow_seed(g)
    ctx = ctx if ctx is not None else {"walls": None, "bnd": None}
    bt = [None, None]

    def f(P):
        P = np.array(P, float)
        if not len(P):
            return P
        xz = P[:, [0, 2]]
        d = np.full(len(P), 1e9)
        if ctx.get("walls") is not None:
            d = ctx["walls"].query(xz, k=1, distance_upper_bound=bank_w)[0]
            d = np.where(np.isfinite(d), d, 1e9)
        tgt = base + snow_bank(d, bank_h, bank_w, float(g.get("bank_p", SNOW_DEFAULTS["bank_p"]))) + rough * snow_rough(P[:, 0], P[:, 2], seed)
        w = np.ones(len(P))
        bnd = ctx.get("bnd")
        if bnd is not None and len(bnd):
            if bt[0] is not bnd:
                bt[0], bt[1] = bnd, cKDTree(bnd)
            db = bt[1].query(xz, k=1)[0]
            t = np.clip(db / SNOW_EDGE_FADE, 0.0, 1.0)
            w = t * t * (3 - 2 * t)
        P[:, 1] = P[:, 1] + (tgt - P[:, 1]) * w
        return P
    return f


DISPLACE_YTOL = 0.6               # m: a point takes the field of a surface triangle only when it lies this close to it vertically (a wall / roof above the snow stays put)


def displace_fn(g, key="field", ytol=DISPLACE_YTOL):
    """op "displace" (Scene Editor Snow Stitch): g["field"] = {"v": [[x, y, z, dx, dy, dz], ...], "t": [[i, j, k], ...]} = the ORIGINAL surface triangles of the stitched
    mesh that touch a moving vertex, with the per-vertex move.  A point is moved by the barycentric blend (horizontal position) of the triangle under it, so the
    render vertices and the (coarser, differently placed) collision vertices of the zone follow the SAME surface displacement and cannot diverge.  Points under no
    triangle (or not near its height) do not move."""
    F = g[key]
    V = np.array(F["v"], float).reshape(-1, 6)
    T = np.array(F["t"], np.int64).reshape(-1, 3)
    A, B, C = V[T[:, 0]], V[T[:, 1]], V[T[:, 2]]
    ax, az = A[:, 0], A[:, 2]
    e1x, e1z = B[:, 0] - ax, B[:, 2] - az
    e2x, e2z = C[:, 0] - ax, C[:, 2] - az
    den = e1x * e2z - e2x * e1z
    ok_t = np.abs(den) > 1e-12
    den = np.where(ok_t, den, 1.0)

    def f(P):
        P = np.array(P, float).reshape(-1, 3)
        out = P.copy()
        ysurf = np.full(len(P), np.nan)          # the ORIGINAL surface height under each point (f.last_surface after the call)
        f.last_surface = ysurf
        if not len(P) or not len(T):
            return out
        for s0 in range(0, len(P), 256):
            p = P[s0:s0 + 256]
            dx, dz = p[:, 0:1] - ax[None], p[:, 2:3] - az[None]
            v = (dx * e2z[None] - e2x[None] * dz) / den[None]
            w = (e1x[None] * dz - dx * e1z[None]) / den[None]
            u = 1.0 - v - w
            ins = (u >= -1e-3) & (v >= -1e-3) & (w >= -1e-3) & ok_t[None]
            yi = u * A[None, :, 1] + v * B[None, :, 1] + w * C[None, :, 1]
            dy = np.abs(p[:, 1:2] - yi)
            ins &= dy <= ytol
            score = np.where(ins, dy, np.inf)
            k = score.argmin(1)
            r = np.arange(len(p))
            has = np.isfinite(score[r, k])
            uu, vv, ww = (np.clip(x[r, k], 0, None) for x in (u, v, w))
            sm = np.maximum(uu + vv + ww, 1e-12)
            d = (uu / sm)[:, None] * A[k, 3:6] + (vv / sm)[:, None] * B[k, 3:6] + (ww / sm)[:, None] * C[k, 3:6]
            out[s0:s0 + 256] += np.where(has[:, None], d, 0.0)
            ysurf[s0:s0 + 256] = np.where(has, yi[r, k], np.nan)
        f.last_surface = ysurf
        return out
    f.is_field = True
    return f


CFIELD_YTOL = 0.03                # m: collision vertices ARE the corners of the collision field's triangles, nothing above / below them follows
STITCH_SNAP_R = 1.0               # m: a collision boundary vertex this close (horizontally) to the stitched seam curve is put ON it
STITCH_SNAP_DY = 0.8              # m: ... and this close vertically
STITCH_FLAT = 1.5                # m: collision vertices this close to the seam curve are blended onto the stitched render surface height (full at the curve)
STITCH_MAX_DY = 0.8               # m: largest height change of such a vertex beyond the render field
STITCH_BLEND = 1.0                # m: the snap's extra move fades into the neighbouring collision vertices over this distance


def displace_collision(g, items, log=print):
    """Snow Stitch collision field.  The collision hull is coarser than the render mesh and has its OWN open edge (offset from the render edge, raised lips), so
    following the render displacement alone (or snapping vertices within 0.4 m of render vertices - the old flatten 'match') leaves holes and steps at the seam.
    Here: (1) every walkable collision vertex over the stitched region follows the render field; (2) every vertex of the collision's open edge that lies within
    STITCH_SNAP_R of the stitched seam curve (g["seam_segs"], both meshes meet on it) is moved ONTO that curve, so both hulls end on the same line at the render
    height; (3) the extra move of (2) fades into the other collision vertices within STITCH_BLEND.  -> {"cfield", "cbox"} (the vertices carry their own move)"""
    import snow_stitch as ss
    from scipy.spatial import cKDTree
    F = np.array(g["field"]["v"], float).reshape(-1, 6)
    seg = np.array(g.get("seam_segs") or [], float).reshape(-1, 2, 3)
    if not len(seg):
        return {}
    lo = F[:, :3].min(0) - [1.0, 0.8, 1.0]
    hi = F[:, :3].max(0) + [1.0, 0.8, 1.0]
    tf = cKDTree(F[:, [0, 2]])
    out = []
    for it in items:
        _, T, _ = hc.triangles(it.mesh)
        if not len(T):
            continue
        T = T[(T.max(1) >= lo).all(1) & (T.min(1) <= hi).all(1)]
        if not len(T):
            continue
        nrm = np.cross(T[:, 1] - T[:, 0], T[:, 2] - T[:, 0])
        ln = np.linalg.norm(nrm, axis=1)
        T = T[(ln > 1e-9) & (nrm[:, 1] / np.maximum(ln, 1e-9) > 0.5)]
        if len(T):
            out.append(T)
    if not out:
        return {}
    T = np.concatenate(out)
    cen = T.mean(1)
    d, j = tf.query(cen[:, [0, 2]], k=1, distance_upper_bound=1.2)
    keep = np.isfinite(d)
    keep[keep] = np.abs(cen[keep, 1] - F[j[keep], 1]) < 0.8           # over the stitched surface, not a roof / wall / floor below it
    T = T[keep]
    if not len(T):
        return {}
    U, CT = ss.weld(T.reshape(-1, 3), np.arange(len(T) * 3).reshape(-1, 3))
    fn0 = displace_fn(g)
    base = fn0(U) - U
    ysurf = fn0.last_surface.copy()
    bv, _ = ss.boundary(U, CT)
    delta = base.copy()
    snapped = []
    if len(bv):
        q, _ = ss.nearest_on_segments(U[bv] + base[bv], seg[:, 0], seg[:, 1])
        P1 = U[bv] + base[bv]
        dh = np.linalg.norm((q - P1)[:, [0, 2]], axis=1)
        ok = (dh <= STITCH_SNAP_R) & (np.abs(q[:, 1] - P1[:, 1]) <= STITCH_SNAP_DY)
        for k in np.nonzero(ok)[0]:
            mv = q[k] - U[bv[k]]
            if np.linalg.norm(mv) <= 1.0:
                delta[bv[k]] = mv
                snapped.append(bv[k])
    snapped = np.array(snapped, int)
    if len(snapped):
        extra = delta[snapped] - base[snapped]
        d2, j2 = cKDTree(U[snapped][:, [0, 2]]).query(U[:, [0, 2]], k=1, distance_upper_bound=STITCH_BLEND)
        r = np.isfinite(d2)
        r[snapped] = False
        idx = np.nonzero(r)[0]
        delta[idx] = base[idx] + extra[j2[idx]] * ss.smooth(d2[idx], STITCH_BLEND)[:, None]
    # (4) the render surface is the truth near the seam: every other collision vertex within STITCH_FLAT of the curve is blended to the height of the stitched render surface
    #     (the hull has raised lips / piles of its own: a 0.4 m step across the seam otherwise)
    q2, _ = ss.nearest_on_segments(np.c_[U[:, 0], np.zeros(len(U)), U[:, 2]], np.c_[seg[:, 0, 0], np.zeros(len(seg)), seg[:, 0, 2]], np.c_[seg[:, 1, 0], np.zeros(len(seg)), seg[:, 1, 2]])
    dseam = np.linalg.norm((q2 - np.c_[U[:, 0], np.zeros(len(U)), U[:, 2]])[:, [0, 2]], axis=1)
    w = ss.smooth(dseam, STITCH_FLAT)
    w[snapped] = 0.0
    tgt = ysurf + base[:, 1]
    use = np.isfinite(tgt) & (w > 0)
    dy_new = delta[:, 1] + w * (tgt - (U[:, 1] + delta[:, 1]))
    dy_new = np.clip(dy_new, base[:, 1] - STITCH_MAX_DY, base[:, 1] + STITCH_MAX_DY)
    delta[use, 1] = dy_new[use]
    mv = (np.linalg.norm(delta, axis=1) > 1e-5)
    if not mv.any():
        return {}
    ts = CT[mv[CT].any(1)]
    used, inv = np.unique(ts, return_inverse=True)
    pad = np.array([0.1, 0.8, 0.1])
    log("  stitch %r: collision field: %d vertices on %d triangles, %d open-edge vertices put on the seam" % (g.get("name"), len(used), len(ts), len(snapped)))
    return {"cfield": {"v": np.c_[U[used], delta[used]].tolist(), "t": inv.reshape(-1, 3).tolist()},
            "cbox": np.r_[U[used].min(0) - pad, U[used].max(0) + pad].tolist()}


def morph_fn(g, ctx=None):
    op = g.get("op", "flatten")
    if op == "displace":
        return displace_fn(g)
    if op == "snow":
        return snow_fn(g, ctx)
    if op == "flatten":
        y = float(g["y"])

        def f(P):
            P = np.array(P, float)
            P[:, 1] = y
            return P
        return f
    if op == "translate":
        d = np.array(g["delta"], float)
        return lambda P: np.asarray(P, float) + d
    fail("%r: unknown morph op %r" % (g.get("name"), op))


def near_mask(A, B, tol):
    """bool mask over rows of A: a row of B lies within tol (max-norm distance <= tol is enough: A and B are metres, tol is mm)"""
    if not len(A) or not len(B):
        return np.zeros(len(A), bool)
    from scipy.spatial import cKDTree
    d, _ = cKDTree(B).query(A, k=1, distance_upper_bound=tol * 1.7321)
    return np.isfinite(d)


# =============================================================================================== render side
def _stride_bits(st):
    s = sum(st["bits"])
    return s if s else (st["size"] * 8 // max(st["vcount"], 1))


def raw_positions(p, st, n):
    """integer coordinates (n,3) of a bit-packed (type 64) position stream"""
    bits, stride = st["bits"], sum(st["bits"])
    buf = np.frombuffer(p.d, np.uint8)
    bo = st["buf"] * 8 + np.arange(n, dtype=np.int64) * stride
    out = np.zeros((n, 3), np.int64)
    for c in range(3):
        byte = bo >> 3
        wv = np.zeros(n, np.uint64)
        for k in range(8):
            wv |= buf[np.minimum(byte + k, len(buf) - 1)].astype(np.uint64) << np.uint64(8 * k)
        wv >>= (bo & 7).astype(np.uint64)
        out[:, c] = (wv & np.uint64((1 << bits[c]) - 1)).astype(np.int64)
        bo = bo + bits[c]
    return out


def _put_bits(rb, bit_off, nbits, val):
    byte, sh = bit_off >> 3, bit_off & 7
    nb = (sh + nbits + 7) // 8
    cur = int.from_bytes(rb[byte:byte + nb], "little")
    mask = ((1 << nbits) - 1) << sh
    cur = (cur & ~mask) | ((int(val) << sh) & mask)
    rb[byte:byte + nb] = cur.to_bytes(nb, "little")


def _get_bits(rb, bit_off, nbits):
    byte, sh = bit_off >> 3, bit_off & 7
    nb = (sh + nbits + 7) // 8
    return (int.from_bytes(rb[byte:byte + nb], "little") >> sh) & ((1 << nbits) - 1)


class Sub:
    """one world-space submesh the edit touches: decoded positions + write-back with range handling"""

    def __init__(self, p, i, M, owner):
        self.p, self.i, self.sm, self.M, self.owner = p, i, p.submeshes[i], M, owner
        self.st = p.pos_stream(self.sm)
        if self.st is None:
            fail("submesh #%d has no position stream" % i)
        self.n = self.sm["vcount"]
        self.local = le._qpos(p, self.sm)
        self.Minv = np.linalg.inv(M)
        self.moved = {}                                      # vertex -> new local position

    def world(self, idx=None):
        L = self.local if idx is None else self.local[idx]
        return (np.concatenate([L, np.ones((len(L), 1))], 1) @ self.M)[:, :3]

    def to_local(self, W):
        return (np.concatenate([W, np.ones((len(W), 1))], 1) @ self.Minv)[:, :3]

    def live_tris(self):
        I = np.array(self.p.indices(self.sm), np.int64).reshape(-1, 3)
        return I, I[:, 0] != I[:, 1]

    def write(self, rb, log):
        """write self.moved into rb (bytearray of the pak); returns the new local AABB or None"""
        if not self.moved:
            return None
        st, p = self.st, self.p
        ids = np.array(sorted(self.moved), np.int64)
        newl = np.array([self.moved[int(v)] for v in ids], float)
        if st["type"] == 0:
            for v, P in zip(ids, newl):
                struct.pack_into("<3f", rb, st["buf"] + 12 * int(v), *[float(c) for c in P])
            allp = self.local.copy()
            allp[ids] = newl
            return allp.min(0), allp.max(0)
        bits, stride = st["bits"], sum(st["bits"])
        scale = np.array(st["scale"][:3], np.float32).astype(np.float64)
        off = np.array(st["off"][:3], np.float32).astype(np.float64)
        maxv = np.array([(1 << b) - 1 for b in bits[:3]], np.int64)
        raw = raw_positions(p, st, self.n)
        sc1 = np.where(scale > 0, scale, 1.0)
        fl = (newl - off) / sc1                                # float raw coordinate of the moved vertices
        fl[:, scale == 0] = 0.0
        rest = np.ones(self.n, bool)
        rest[ids] = False
        lo = np.minimum(fl.min(0), raw[rest].min(0)) if rest.any() else fl.min(0)
        hi = np.maximum(fl.max(0), raw[rest].max(0)) if rest.any() else fl.max(0)
        shift = np.zeros(3, np.int64)
        resc = np.zeros(3, bool)
        for c in range(3):
            if scale[c] == 0:
                if (np.abs(newl[:, c] - off[c]) > 1e-6).any():
                    fail("submesh #%d %s: channel %d is constant (scale 0), cannot move it" % (self.i, self.sm["name"][-50:], c))
                continue
            kneed = int(math.ceil(hi[c] - maxv[c] - 0.5 - 1e-9))     # smallest shift that makes the top fit
            kmax = int(math.floor(lo[c] + 0.5 + 1e-9))               # largest shift that keeps the bottom >= 0 after rounding
            if kneed > kmax:
                resc[c] = True
            else:
                shift[c] = min(max(0, kneed), kmax)
        allp = self.local.copy()
        allp[ids] = newl
        ns, no = scale.copy(), off + shift * scale
        raw2 = raw - shift
        raw2[ids] = np.clip(np.rint(fl - shift), 0, maxv)
        if resc.any():
            vlo, vhi = allp.min(0), allp.max(0)
            for c in np.nonzero(resc)[0]:        # only the channels that do not fit are re-scaled; the others stay bit exact
                ns[c] = np.float32((vhi[c] - vlo[c]) / maxv[c] * (1 + 1e-6))
                no[c] = np.float32(vlo[c])
                raw2[:, c] = np.clip(np.rint((allp[:, c] - no[c]) / ns[c]), 0, maxv[c])
            how = "RE-SCALED channels %s (scale %s -> %s)" % (np.nonzero(resc)[0].tolist(), np.round(scale[resc], 6).tolist(), np.round(ns[resc], 6).tolist())
            self._store(rb, raw2.astype(np.int64), ns, no, log, how, None)
        elif shift.any():
            self._store(rb, raw2.astype(np.int64), ns, no, log, "shifted by %s steps" % shift.tolist(), None)
        else:
            self._store(rb, raw2.astype(np.int64), ns, no, log, "in range", ids)
        allp = self.local.copy()
        allp[ids] = newl
        return allp.min(0), allp.max(0)

    def _store(self, rb, raw, scale, off, log, how, only=None):
        st = self.st
        bits, stride = st["bits"], sum(st["bits"])
        base = st["buf"] * 8
        for v in (range(self.n) if only is None else [int(x) for x in only]):
            bo = base + v * stride
            for c in range(3):
                _put_bits(rb, bo, bits[c], raw[v, c])
                bo += bits[c]
        so = st["offset"]
        if only is None:
            for c in range(3):
                struct.pack_into("<f", rb, so + 32 + 4 * c, float(scale[c]))
                struct.pack_into("<f", rb, so + 48 + 4 * c, float(off[c]))
        log("    submesh #%d stream %s" % (self.i, how))


def _grow_aabb(rb, sub, lohi, log):
    """submesh AABB + the AABBs of the record that owns it only ever grow"""
    lo, hi = lohi
    sm = sub.sm
    a = np.array(struct.unpack_from("<3f", rb, sm["offset"]), float)
    b = np.array(struct.unpack_from("<3f", rb, sm["offset"] + 16), float)
    na = np.where(lo < a - 1e-6, lo - 1e-4, a)
    nb = np.where(hi > b + 1e-6, hi + 1e-4, b)
    if (na < a).any() or (nb > b).any():
        struct.pack_into("<3f", rb, sm["offset"], *[float(x) for x in na])
        struct.pack_into("<3f", rb, sm["offset"] + 16, *[float(x) for x in nb])
        log("    submesh #%d AABB grown" % sub.i)
        it = sub.owner
        if it is not None:
            o = it.pak_off
            for k in (0, 32):                                  # the record holds its local AABB twice
                ra = np.array(struct.unpack_from("<3f", rb, o + 64 + k), float)
                rbx = np.array(struct.unpack_from("<3f", rb, o + 80 + k), float)
                struct.pack_into("<3f", rb, o + 64 + k, *[float(x) for x in np.minimum(ra, na)])
                struct.pack_into("<3f", rb, o + 80 + k, *[float(x) for x in np.maximum(rbx, nb)])
            log("    record @%#x AABB grown (KD_TREE_2 / VIS_INFO_1 cells are not re-derived)" % o)


class Render:
    def __init__(self, path):
        self.path = path
        self.p = ndpak.Pak(path)
        self.rb = bytearray(self.p.d)
        self.insts = le.find_instances(self.p)
        self.owners = {}
        for it in self.insts:
            for _, ids in it.names:
                for i in ids:
                    self.owners.setdefault(i, []).append(it)
        self.cache = {}

    def sub(self, i):
        if i not in self.cache:
            ow = self.owners.get(i, [])
            if len(ow) > 1:
                fail("submesh #%d (%s) is a prop prototype used by %d placements: cannot be morphed for one" % (i, self.p.submeshes[i]["name"][-60:], len(ow)))
            M = ow[0].M if ow else np.eye(4)
            self.cache[i] = Sub(self.p, i, M, ow[0] if ow else None)
        return self.cache[i]

    def world_candidates(self, box, tol):
        """submeshes (not shared prototypes) whose world AABB meets the box"""
        lo, hi = np.array(box[:3]) - tol, np.array(box[3:]) + tol
        out = []
        for i, sm in enumerate(self.p.submeshes):
            if len(self.owners.get(i, [])) > 1 or self.p.pos_stream(sm) is None:
                continue
            o = sm["offset"]
            a, b = np.array(struct.unpack_from("<3f", self.p.d, o)), np.array(struct.unpack_from("<3f", self.p.d, o + 16))
            ow = self.owners.get(i, [])
            if ow:
                M = ow[0].M
                c = np.array([[x, y, z, 1.0] for x in (a[0], b[0]) for y in (a[1], b[1]) for z in (a[2], b[2])]) @ M
                a, b = c[:, :3].min(0), c[:, :3].max(0)
            if (b < lo).any() or (a > hi).any() or (b - a).max() > 400:
                continue
            out.append(i)
        return out

    def find_primary(self, g, pts_idx, box, tol):
        """the submesh of entry g: name tail + asset, and the check positions must match (loud failure otherwise)"""
        mesh, asset = g.get("mesh") or "", g.get("asset") or ""
        rx = re.compile("(^|\\|)" + re.escape(mesh) + "$")
        cands = [i for i in self.world_candidates(box, 0.5) if rx.search(self.p.submeshes[i]["name"])]
        if asset:
            c2 = [i for i in cands if asset in self.p.submeshes[i]["name"] or any(asset in n for it in self.owners.get(i, []) for n, ids in it.names if i in ids)]
            cands = c2 or cands
        chk = np.array(g.get("check") or [], float).reshape(-1, 3)
        good = []
        for i in cands:
            s = self.sub(i)
            if pts_idx is not None and (max(pts_idx) >= s.n if len(pts_idx) else False):
                continue
            if len(chk):
                if not near_mask(chk, s.world(), max(tol, 0.01)).all():
                    continue
            good.append(i)
        if not good and len(chk):
            # an earlier entry of this build may have flattened / moved vertices this entry shares (the editor recorded the check positions
            # before it): flatten / translate keep x, z of the others, so accept a match in the horizontal plane
            for i in cands:
                s = self.sub(i)
                if pts_idx is not None and (max(pts_idx) >= s.n if len(pts_idx) else False):
                    continue
                if near_mask(chk[:, [0, 2]], s.world()[:, [0, 2]], max(tol, 0.01)).all():
                    good.append(i)
        if not good:
            fail("%r: no submesh %r (asset %r) near %s matches the recorded vertex positions - the level geometry changed since the edit was made "
                 "(open the map in the editor and redo it)" % (g.get("name"), mesh, asset, np.round(box, 2).tolist()))
        if len(good) > 1:
            # several equal candidates (LODs with the same name): the one whose selected vertices match best
            good.sort(key=lambda i: -near_mask(chk, self.sub(i).world(), 0.003).sum())
        return good[0]


def _spatial(P, tol):
    from scipy.spatial import cKDTree
    return cKDTree(P)


def apply_morph_render(R, g, log, ctx=None):
    """-> (moved world points (old positions), per-submesh counts)"""
    tol = float(g.get("tol", TOL))
    box = g["box"]
    verts = np.array(g["verts"], np.int64)
    i0 = R.find_primary(g, verts, box, tol)
    s0 = R.sub(i0)
    if len(verts) and (verts.max() >= s0.n):
        fail("%r: vertex index %d outside submesh #%d (%d vertices)" % (g.get("name"), int(verts.max()), i0, s0.n))
    if g.get("op") == "snow":
        if ctx is None:
            ctx = {"walls": None, "bnd": None}
        ctx["bnd"] = snow_boundary(s0, verts)
    fn = morph_fn(g, ctx)
    P0 = s0.world(verts)
    # every world-space vertex of any candidate submesh on one of these positions
    from scipy.spatial import cKDTree
    tree = cKDTree(P0)
    total = 0
    per = {}
    shadow_radius = None
    if g.get("collision", "match") == "match" and min(box[3] - box[0], box[5] - box[2]) >= 0.5:
        shadow_radius = float(g.get("collision_radius", SNAP_RADIUS))   # a thin (wall / frame) selection drags nothing nearby
        shadow_lo = np.array(box[:3], float) - [shadow_radius, 0.05, shadow_radius]
        shadow_hi = np.array(box[3:], float) + [shadow_radius, 0.05, shadow_radius]
    for i in R.world_candidates(box, shadow_radius or tol):
        s = R.sub(i)
        W = s.world()
        d, _ = tree.query(W, k=1, distance_upper_bound=tol * 1.7321)
        hit = np.nonzero(np.isfinite(d))[0]
        if i == i0:
            hit = np.union1d(hit, verts)
        elif shadow_radius and _SHADOW_RX.search(R.p.submeshes[i]["name"]):
            # shadow proxies (tfrag-merge-shadows, shadowProxy) are decimated copies with their own vertices: exact matches miss most of
            # a flattened snow mound and its old shadow stays on the walls around it.  Same rule as collision "match":
            # every proxy vertex within shadow_radius of a selected position and inside the selection box (+radius in x / z) follows.
            dn, _ = tree.query(W, k=1, distance_upper_bound=shadow_radius)
            near = np.isfinite(dn) & ((W >= shadow_lo) & (W <= shadow_hi)).all(1)
            # never drag a wall's proxy down with the snow: a vertex follows only if none of its live triangles is near vertical
            I, live = s.live_tris()
            T = I[live]
            if len(T):
                nrm = np.cross(W[T[:, 1]] - W[T[:, 0]], W[T[:, 2]] - W[T[:, 0]])
                ln = np.linalg.norm(nrm, axis=1)
                steep = (ln > 1e-12) & (np.abs(nrm[:, 1]) < 0.2 * np.maximum(ln, 1e-12))
                wall_v = np.zeros(len(W), bool)
                wall_v[T[steep].ravel()] = True
                near &= ~wall_v
            n_ex = int(np.isfinite(d).sum())
            hit = np.union1d(hit, np.nonzero(near)[0])
            if len(hit) > n_ex:
                log("    shadow proxy submesh #%d: %d vertices follow the morph (%d exact)" % (i, len(hit), n_ex))
        if not len(hit):
            continue
        NW = fn(W[hit])
        newl = s.to_local(NW)
        for v, pl in zip(hit, newl):
            s.moved[int(v)] = pl
        per[i] = len(hit)
        total += len(hit)
    if not per:
        fail("%r: no render vertex found" % g.get("name"))
    log("  morph %r: %d render vertices in %d submesh(es) (%s)" % (g.get("name"), total, len(per), ", ".join("#%d:%d" % kv for kv in sorted(per.items()))))
    if g.get("op") == "flatten" and os.environ.get("T2R_SNOW_FLAT_BAKE", "1") != "0":
        for i in sorted(per):
            clean_baked_streams(R, R.sub(i), box, float(g["y"]), log)
    return P0, per


BAKE_STREAM_TYPES = (90, 130)     # snow terrain: per-vertex 2x11 bit UV (lightmap-like, shared offset / scale) and a 32-bit stream, both baked with the old mound
FLAT_NY = 0.97                    # a "flat snow" source vertex: every live triangle around it has |ny| >= this
FLAT_DY = 0.35                    # ... and lies within this of the flatten height


_WALL_RX = re.compile(r"(?i)wall|facade|exterior|bldg|building|siding|pillar")   # submesh names of building walls
WALL_PAD = 1.0                    # m: wall vertices within this of a flatten box footprint (x / z) are checked
WALL_HI_PAD = 0.1                 # m above the old drift top still counts as drift AO; sources are above that
WALL_SRC_H = 1.6                  # m: clean source vertices lie within this above the drift top
WALL_SRC_R = 2.0                  # m: and within this horizontally


def clean_wall_bake(R, g, log):
    """A ~1 m black band (screenshot ab.png B) along the base of the building wall where the flattened snow meets it = the old drift's
    contact AO baked into the WALL's per-vertex stream (type 130, type 90 if present).  For every world-space (merged, no placement) steep-faced
    submesh near the flatten box: the vertices between the new snow height and the old drift top (box top) inside the box footprint + WALL_PAD
    take those streams from the nearest steep vertex of the same submesh just above the drift top (same horizontal position).  Runs for the
    flatten entries of every level, in every level of the map that has morph edits (the wall can live in the neighbour level).  T2R_SNOW_FLAT_BAKE=0 = off."""
    from scipy.spatial import cKDTree
    box, y, top = g["box"], float(g["y"]), float(g["box"][4])
    if top <= y + 0.05:
        return 0
    lo = [box[0] - WALL_PAD, y - 0.5, box[2] - WALL_PAD]
    hi = [box[3] + WALL_PAD, top + WALL_SRC_H + 0.2, box[5] + WALL_PAD]
    tot = 0
    for i in R.world_candidates(lo + hi, 0.0):
        sm = R.p.submeshes[i]
        if _SHADOW_RX.search(sm["name"]) or not _WALL_RX.search(sm["name"].split("|")[-1]):
            continue                                    # only wall / building submeshes (not cars, dumpsters, trash, snow, shadow proxies)
        sts = [st for st in sm["streams"] if st["type"] in BAKE_STREAM_TYPES and st["buf"] and st["vcount"] >= sm["vcount"]]
        if not any(st["type"] == 130 for st in sts) or R.p.pos_stream(sm) is None:
            continue
        s = R.sub(i)
        if getattr(s, "baked_done", None) is None:
            s.baked_done = set()
        W = s.world()
        I, live = s.live_tris()
        T = I[live]
        if not len(T):
            continue
        nrm = np.cross(W[T[:, 1]] - W[T[:, 0]], W[T[:, 2]] - W[T[:, 0]])
        ln = np.maximum(np.linalg.norm(nrm, axis=1), 1e-12)
        steep = np.abs(nrm[:, 1]) / ln < 0.5
        wall_v = np.zeros(s.n, bool)
        wall_v[T[steep].ravel()] = True
        foot = (W[:, 0] >= box[0] - WALL_PAD) & (W[:, 0] <= box[3] + WALL_PAD) & (W[:, 2] >= box[2] - WALL_PAD) & (W[:, 2] <= box[5] + WALL_PAD)
        aff = np.nonzero(wall_v & foot & (W[:, 1] >= y - 0.25) & (W[:, 1] <= top + WALL_HI_PAD))[0]
        src = np.nonzero(wall_v & (W[:, 1] > top + WALL_HI_PAD) & (W[:, 1] <= top + WALL_SRC_H))[0]
        aff = np.array([v for v in aff if int(v) not in s.baked_done], np.int64)
        if not len(aff) or not len(src):
            continue
        d, j = cKDTree(W[src][:, [0, 2]]).query(W[aff][:, [0, 2]], k=1, distance_upper_bound=WALL_SRC_R)
        okm = np.isfinite(d)
        for v, sv in zip(aff[okm], src[j[okm]]):
            for st in sts:
                sb = _stride_bits(st)
                _put_bits_big(R.rb, st["buf"] * 8 + int(v) * sb, sb, _get_bits_big(R.rb, st["buf"] * 8 + int(sv) * sb, sb))
            s.baked_done.add(int(v))
        n = int(okm.sum())
        if n:
            tot += n
            log("    wall baked streams (types %s) of submesh #%d (%s): %d vertices below the old drift top (y %.2f..%.2f) take the values just above it" % (
                "/".join(str(st["type"]) for st in sts), i, sm["name"][-40:], n, y - 0.25, top + WALL_HI_PAD))
    return tot


def clean_baked_streams(R, s, box, y, log):
    """A flattened snow mound keeps the baked AO / shadow of the old mound.  Positions move but the baked per-vertex streams
    (type 90 / 130) stay.  Every moved vertex of a submesh that has them takes those two streams (bit exact) from the nearest UNMOVED flat
    snow vertex of the same submesh outside the box (so it points at a clean texel).  T2R_SNOW_FLAT_BAKE=0 turns it off."""
    sts = [st for st in s.sm["streams"] if st["type"] in BAKE_STREAM_TYPES and st["buf"] and st["vcount"] >= s.n]
    if len(sts) < len(BAKE_STREAM_TYPES) or not s.moved:      # both streams = snow terrain (walls / props carry only type 130)
        return 0
    from scipy.spatial import cKDTree
    W = s.world()
    I, live = s.live_tris()
    T = I[live]
    if not len(T):
        return 0
    nrm = np.cross(W[T[:, 1]] - W[T[:, 0]], W[T[:, 2]] - W[T[:, 0]])
    ln = np.maximum(np.linalg.norm(nrm, axis=1), 1e-12)
    flat_t = np.abs(nrm[:, 1]) / ln >= FLAT_NY
    ok = np.zeros(s.n, bool)
    ok[T.ravel()] = True
    ok[T[~flat_t].ravel()] = False
    pad = 0.5
    inb = ((W[:, 0] >= box[0] - pad) & (W[:, 0] <= box[3] + pad) & (W[:, 2] >= box[2] - pad) & (W[:, 2] <= box[5] + pad))
    moved = np.zeros(s.n, bool)
    moved[list(s.moved)] = True
    cand = np.nonzero(ok & ~inb & ~moved & (np.abs(W[:, 1] - y) <= FLAT_DY))[0]
    mv = np.array(sorted(v for v in s.moved if inb[v] or True), np.int64)
    if not len(cand):
        log("    baked streams of submesh #%d: no flat unmoved snow vertex near y %.2f (left as is)" % (s.i, y))
        return 0
    done = getattr(s, "baked_done", None)
    if done is None:
        done = s.baked_done = set()
    mv = np.array([v for v in mv if int(v) not in done], np.int64)
    if not len(mv):
        return 0
    _, j = cKDTree(W[cand][:, [0, 2]]).query(W[mv][:, [0, 2]], k=1)
    for v, src in zip(mv, cand[j]):
        for st in sts:
            sb = _stride_bits(st)
            val = _get_bits_big(R.rb, st["buf"] * 8 + int(src) * sb, sb)
            _put_bits_big(R.rb, st["buf"] * 8 + int(v) * sb, sb, val)
        done.add(int(v))
    log("    baked streams (types %s) of submesh #%d: %d moved vertices take the values of %d clean flat snow vertices" % (
        "/".join(str(st["type"]) for st in sts), s.i, len(mv), len(set(cand[j].tolist()))))
    return len(mv)


def flush_render(R, log):
    n = 0
    for i, s in sorted(R.cache.items()):
        lohi = s.write(R.rb, log)
        if lohi is not None:
            _grow_aabb(R.rb, s, lohi, log)
            n += 1
    return n


# ----------------------------------------------------------------------------------------------- detach (render)
def _copy_vertex(rb, sm, src, dst):
    """copy every stream's data of vertex src to slot dst (bit exact)"""
    for st in sm["streams"]:
        if not st["buf"] or st["vcount"] <= max(src, dst):
            continue
        sb = _stride_bits(st)
        if sb <= 0:
            continue
        v = _get_bits_big(rb, st["buf"] * 8 + src * sb, sb)
        _put_bits_big(rb, st["buf"] * 8 + dst * sb, sb, v)


def _get_bits_big(rb, bit_off, nbits):
    byte, sh = bit_off >> 3, bit_off & 7
    nb = (sh + nbits + 7) // 8
    return (int.from_bytes(rb[byte:byte + nb], "little") >> sh) & ((1 << nbits) - 1)


def _put_bits_big(rb, bit_off, nbits, val):
    _put_bits(rb, bit_off, nbits, val)


def detach_in_submesh(R, s, tris, fn, log, label):
    """move triangles `tris` of submesh s rigidly through fn (world -> world).  -> (mode, #vertices moved)"""
    I, live = s.live_tris()
    tris = np.array(sorted(set(int(t) for t in tris)), np.int64)
    if len(tris) and tris.max() >= len(I):
        fail("%s: triangle %d outside the submesh (%d)" % (label, int(tris.max()), len(I)))
    tris = tris[live[tris]]
    if not len(tris):
        fail("%s: only degenerate (already removed) triangles selected" % label)
    sel = np.zeros(len(I), bool)
    sel[tris] = True
    vs = np.unique(I[sel].ravel())
    used_other = np.unique(I[live & ~sel].ravel())
    shared = np.intersect1d(vs, used_other)
    used_any = np.unique(I[live].ravel())
    free = np.setdiff1d(np.arange(s.n), used_any)
    base = R.p.submeshes[s.i]["index"]
    mapping = {}
    if len(shared):
        if len(free) < len(shared):
            fail("%s: %d of the selected vertices are shared with triangles that stay, and the mesh has only %d free vertex slots (needs %d): "
                 "the render vertex buffer cannot grow in place. Select a closed piece (a whole connected part), or cut the piece along existing "
                 "seams." % (label, len(shared), len(free), len(shared)))
        for b, f in zip(shared, free):
            mapping[int(b)] = int(f)
            _copy_vertex(R.rb, s.sm, int(b), int(f))
            s.local[int(f)] = s.local[int(b)]
        for t in tris:
            for k in range(3):
                v = int(I[t, k])
                if v in mapping:
                    struct.pack_into("<H", R.rb, base + 6 * int(t) + 2 * k, mapping[v])
    pv = sorted(set(int(v) for v in vs if int(v) not in mapping) | set(mapping.values()))
    W = s.world(np.array(pv, np.int64))
    NL = s.to_local(fn(W))
    for v, pl in zip(pv, NL):
        s.moved[v] = pl
    return ("cloned %d boundary vertices" % len(shared) if len(shared) else "closed piece"), len(pv)


def apply_detach_render(R, g, log):
    tol = float(g.get("tol", TOL))
    fn = detach_fn(g["transform"])
    tris = np.array(g["tris"], np.int64)
    box = g["box"]
    i0 = R.find_primary(g, None, box, tol)
    s0 = R.sub(i0)
    label = "%r submesh #%d" % (g.get("name"), i0)
    I0, live0 = s0.live_tris()
    # identical triangles of the other world-space submeshes (shadow proxy): found BEFORE the primary moves
    Wv = s0.world(np.unique(I0[tris[tris < len(I0)]].ravel()))
    mode, nv = detach_in_submesh(R, s0, tris, fn, log, label)
    log("  detach %r: submesh #%d %d triangles, %s, %d vertices moved" % (g.get("name"), i0, len(tris), mode, nv))
    from scipy.spatial import cKDTree
    tree = cKDTree(Wv)
    for i in R.world_candidates(box, tol):
        if i == i0:
            continue
        s = R.sub(i)
        I, live = s.live_tris()
        W = s.world()
        d, _ = tree.query(W, k=1, distance_upper_bound=tol * 1.7321)
        ok = np.isfinite(d)
        m = live & ok[I[:, 0]] & ok[I[:, 1]] & ok[I[:, 2]]
        t2 = np.nonzero(m)[0]
        if not len(t2):
            continue
        try:
            mode2, nv2 = detach_in_submesh(R, s, t2, fn, log, "%r submesh #%d" % (g.get("name"), i))
            log("    copy in submesh #%d (%s): %d triangles, %s" % (i, s.sm["name"].split("|")[-1][:40], len(t2), mode2))
        except MorphError as ex:
            from level_edit import cut_triangles
            cut_triangles(R.rb, R.p, i, t2)
            log("    copy in submesh #%d (%s): %d triangles CUT instead (%s)" % (i, s.sm["name"].split("|")[-1][:40], len(t2), str(ex).split(":", 2)[-1].strip()[:90]))
    return Wv


# =============================================================================================== collision side
def _phys_vertex_move(m, pts, fn, tol, box=None, label="", radius=None, rbox=None, only=None):
    """Move every shared Havok vertex on one of pts (or inside box) through fn.  -> (new mesh, #vertices)
    radius (+ rbox, the selection's world AABB): the collision mesh is NOT the render mesh (its own, coarser vertices), so exact matches
    miss most of a snow mound; every collision vertex within `radius` of a selected render position and inside rbox (+ radius in x / z, y exact) moves too."""
    import copy
    sv = hc.shared_positions(m)
    if only is not None:                       # explicit shared-vertex ids (restore: several vertices may sit on the same position with different targets); fn gets them in id order
        hit = np.zeros(len(sv), bool)
        hit[np.asarray(only, np.int64)] = True
    elif box is not None:
        lo, hi = np.array(box[:3]), np.array(box[3:])
        hit = ((sv >= lo) & (sv <= hi)).all(1)
    else:
        hit = near_mask(sv, pts, tol)
        if radius:
            rl, rh = np.array(rbox[:3], float) - [0.05, tol, 0.05], np.array(rbox[3:], float) + [0.05, tol, 0.05]
            hit |= near_mask(sv, pts, radius) & ((sv >= rl) & (sv <= rh)).all(1)
    # a packed (per-section) vertex on a selected position cannot be moved here: refuse rather than leave a crack
    for si, s in enumerate(m.sections):
        if s.npv:
            q = m.packed[s.fp:s.fp + s.npv].astype(np.int64)
            cp = np.frombuffer(s.codec, np.float32).astype(np.float64)
            V = cp[:3] + cp[3:] * np.stack([q & 0x7FF, (q >> 11) & 0x7FF, q >> 22], 1)
            bad = (((V >= np.array(box[:3])) & (V <= np.array(box[3:]))).all(1) if box is not None and only is None else near_mask(V, pts, tol))
            if bad.any() and getattr(fn, "is_field", False):          # a field (stitch) only matters where it really moves the vertex
                bad &= np.abs(fn(V) - V).max(1) > 1e-4
            if bad.any():
                fail("%s: collision section %d keeps %d selected vertices as packed per-section vertices (not movable in place)" % (label, si, int(bad.sum())))
    gs = np.nonzero(hit)[0]
    if not len(gs):
        return m, 0
    n = copy.deepcopy(m)
    prims = np.frombuffer(m.prims, np.uint8).reshape(-1, 4)
    dmin, dmax = m.domain()
    P = np.asarray(fn(sv[gs]), float)
    if getattr(fn, "is_field", False):         # stitch field: a vertex on the hull's domain edge stays on it (the domain cannot grow in place)
        P = np.clip(P, dmin, dmax)
    if (P < dmin - 1e-4).any() or (P > dmax + 1e-4).any():
        fail("%s: the moved collision vertices leave the collision mesh domain %s .. %s (an in-place edit cannot grow it)" % (label, np.round(dmin, 2), np.round(dmax, 2)))
    ext = np.where(dmax > dmin, dmax - dmin, 1.0)
    maxq = np.array([0x1FFFFF, 0x1FFFFF, 0x3FFFFF], float)
    q = np.clip(np.rint((P - dmin) / ext * maxq), 0, maxq).astype(np.uint64)
    sh = n.shared.astype(np.uint64).copy()
    sh[gs] = q[:, 0] | q[:, 1] << np.uint64(21) | q[:, 2] << np.uint64(42)
    n.shared = sh
    gset = set(int(x) for x in gs)
    sv2 = hc.shared_positions(n)
    sec_changed = set()
    moved_prims = {}
    for si, s in enumerate(n.sections):
        if not s.nsh:
            continue
        nv = s.npv + s.nsh
        svi = [int(x) for x in n.svi[s.so:s.so + s.nsh]]
        if not gset.intersection(svi):
            continue
        sec_changed.add(si)
        mp = set()
        for p_ in range(s.npr):
            r = prims[s.po + p_]
            for v in set(int(x) for x in r):
                if s.npv <= v < nv and svi[v - s.npv] in gset:
                    mp.add(p_)
                    break
        moved_prims[si] = mp
    for si in sorted(sec_changed):
        s = n.sections[si]
        V = hc.section_vertices(n, s, sv2)
        old = np.frombuffer(s.dom, np.float32).reshape(2, 4).copy()
        old_box = old[:, :3].astype(np.float64)
        lo = np.nextafter((V.min(0) - 1e-4).astype(np.float32), np.float32(-np.inf))
        hi = np.nextafter((V.max(0) + 1e-4).astype(np.float32), np.float32(np.inf))
        lo = np.maximum(lo, dmin.astype(np.float32))
        hi = np.minimum(hi, dmax.astype(np.float32))
        lo = np.where(V.min(0) >= old[0, :3] - 1e-5, old[0, :3], lo)       # a section box never shrinks and only grows where a vertex left it:
        hi = np.where(V.max(0) <= old[1, :3] + 1e-5, old[1, :3], hi)       # an unchanged box keeps every untouched tree node byte for byte
        dom = old.copy()
        dom[0, :3], dom[1, :3] = lo, hi
        s.dom = dom.astype(np.float32).tobytes()
        nb = dom[:, :3].astype(np.float64)
        nv = s.npv + s.nsh
        pr = prims[s.po:s.po + s.npr].astype(np.int64)
        okp = (pr < nv).all(1)
        pb = np.zeros((s.npr, 2, 3))
        if okp.any():
            pb[okp, 0] = V[pr[okp]].min(1)
            pb[okp, 1] = V[pr[okp]].max(1)
        pb[~okp] = old_box
        mp = moved_prims[si]
        s.nodes = le._refit_codec_tree(s.nodes, 4, nb[0], nb[1], lambda d, pb=pb, mp=mp: (pb[d, 0], pb[d, 1], d in mp), old_root=(old_box[0], old_box[1]))

    def sec_leaf(d):
        b = np.frombuffer(n.sections[d].dom, np.float32).reshape(2, 4)[:, :3].astype(np.float64)
        return b[0], b[1], d in sec_changed
    n.tree5 = le._refit_codec_tree(n.tree5, 5, dmin, dmax, sec_leaf)
    pbox, movedp = {}, set()
    for si in sec_changed:
        s = n.sections[si]
        V = hc.section_vertices(n, s, sv2)
        nv = s.npv + s.nsh
        for p_ in range(s.npr):
            r = prims[s.po + p_].astype(np.int64)
            if (r < nv).all():
                pbox[si << 8 | p_ << 1] = (V[r].min(0), V[r].max(0))
                if p_ in moved_prims[si]:
                    movedp.add(si << 8 | p_ << 1)
    simd = bytearray(n.simd)

    def refit(i):
        f = np.frombuffer(bytes(simd[112 * i:112 * i + 96]), np.float32).reshape(6, 4).copy()
        data = struct.unpack_from("<4I", simd, 112 * i + 96)
        lo_all, hi_all, any_c = np.full(3, np.inf), np.full(3, -np.inf), False
        for j in range(4):
            if f[0, j] > f[1, j]:
                continue
            if data[j] & 1:
                k = data[j] >> 1
                c = k in movedp
                if c:
                    lo, hi = pbox[k]
            else:
                lo, hi, c = refit(data[j] >> 1)
            if c:
                f[0::2, j] = np.nextafter((np.asarray(lo) - 1e-4).astype(np.float32), np.float32(-np.inf))
                f[1::2, j] = np.nextafter((np.asarray(hi) + 1e-4).astype(np.float32), np.float32(np.inf))
                any_c = True
            lo_all = np.minimum(lo_all, f[0::2, j].astype(np.float64))
            hi_all = np.maximum(hi_all, f[1::2, j].astype(np.float64))
        if any_c:
            simd[112 * i:112 * i + 96] = f.astype(np.float32).tobytes()
        return lo_all, hi_all, any_c
    if len(simd) // 112 > 1:
        refit(1)
    n.simd = bytes(simd)
    return n, len(gs)


def _phys_quat_fn(fn):
    return lambda P: fn(np.asarray(P, float).reshape(-1, 3)).reshape(-1, 3)


FIN_LOG = []                     # world triangles (9 floats) the collision morph left as fins in the current level (morph_level resets / writes it: <out_phys>.fins.json)
FIN_MIN_H = 0.08                  # m: a fin stands at least this high
FIN_MOVED = 0.02                  # m: a vertex counts as moved by the morph when it changed by more than this


def morph_fins(m_old, m_new):
    """Collision triangles a vertex move turned into FINS: walkable before (ny >= 0.7), steep after (ny < 0.7), standing more than FIN_MIN_H high, and moved only in PART (some
    vertices pulled onto the new snow surface while another stays at its old height: a 0.1-0.9 m 'fin' standing in the walking floor, no render surface; Supermarket hall: keys
    0x3a00 / 0x6400).  The in-place morph cannot delete triangles, so they are written to <out_phys>.fins.json and coll_edit.apply_all deletes them (the 'delete' kind, whole-section
    protection included).  Same shape keys in both meshes (an in-place edit).  -> [[9 floats]]"""
    k0, T0, _ = hc.triangles(m_old)
    k1, T1, _ = hc.triangles(m_new)
    if len(k0) != len(k1) or not len(k0) or not (k0 == k1).all():
        return []
    mv = np.abs(T1 - T0).max(2) > FIN_MOVED                      # (n, 3) which vertices moved
    part = mv.any(1) & ~mv.all(1)
    if not part.any():
        return []

    def ny(T):
        n = np.cross(T[:, 1] - T[:, 0], T[:, 2] - T[:, 0])
        return n[:, 1] / np.maximum(np.linalg.norm(n, axis=1), 1e-12)
    h = T1[:, :, 1].max(1) - T1[:, :, 1].min(1)
    sel = part & (ny(T0) >= 0.7) & (ny(T1) < 0.7) & (h > FIN_MIN_H)
    return [[round(float(x), 5) for x in t.ravel()] for t in T1[sel]]


def apply_morph_phys(items, buf, g, old_points, log, ctx=None):
    """items: PhysItem list of the phys pak, buf: its bytearray.  Returns (buf, vertices moved)"""
    mode = g.get("collision", "match")
    if mode == "none":
        return buf, 0
    tol = float(g.get("tol", TOL))
    fn = morph_fn(g, ctx)
    if g.get("op") == "displace":       # stitch: EVERY collision vertex in the zone box goes through the field (no 0.4 m snap radius); "cfield" = the field of the
        mode = "box"                    # collision surface itself (its open edge is not the render's), without it the render field is used
        if g.get("cfield"):
            fn = displace_fn(g, "cfield", CFIELD_YTOL)
    total = 0
    radius = float(g.get("collision_radius", SNAP_RADIUS)) if mode == "match" else None
    bx = g["box"]
    if radius and min(bx[3] - bx[0], bx[5] - bx[2]) < 0.5:
        radius = None                   # a thin (wall / door-frame) selection: only exact matches, nothing nearby may be dragged along
    for k, it in sorted(enumerate(items), key=lambda kv: -kv[1].tag_off):
        zb = g.get("cbox") or g["box"]
        box = [c - tol for c in zb[:3]] + [c + tol for c in zb[3:]] if mode == "box" else None
        m2, nv = _phys_vertex_move(it.mesh, old_points, fn, tol, box, "%r collision item %d" % (g.get("name"), k), radius, g["box"])
        if not nv:
            continue
        fins = morph_fins(it.mesh, m2)
        if fins:
            FIN_LOG.extend(fins)
            log("  morph %r: collision item %d: %d partly moved triangles are now fins (listed for coll_edit to delete)" % (g.get("name"), k, len(fins)))
        buf, ntag = le.write_item(buf, it, m2, it.blob)
        log("  morph %r: collision item %d: %d shared vertices moved (%s), tagfile %d -> %d bytes" % (g.get("name"), k, nv, mode, it.tsz, ntag))
        total += nv
    return buf, total


def apply_detach_phys(items, buf, g, log):
    mode = g.get("collision", "inside")
    if mode == "none":
        return buf, 0
    fn = detach_fn(g["transform"])
    box = [float(v) for v in g["box"]]
    total = 0
    for k, it in sorted(enumerate(items), key=lambda kv: -kv[1].tag_off):
        if g.get("items") is not None and k not in g["items"]:
            continue
        keys, T = le._tri_sel(it.mesh, box, None, mode)
        if not len(keys):
            continue
        ka, Ta, ga = hc.triangles(it.mesh)
        pos = {int(x): i for i, x in enumerate(ka)}
        have = {int(x) for x in keys}
        extra = [int(x) ^ 1 for x in keys if (int(x) ^ 1) not in have and (int(x) ^ 1) in pos]
        if extra:                                           # whole primitives only (quad halves)
            keys = np.concatenate([keys, np.array(sorted(set(extra)), np.int64)])
        keys = np.array(sorted(int(x) for x in keys), np.int64)
        T = Ta[[pos[int(x)] for x in keys]]
        try:
            m, done, rest = le.move_in_place(it.mesh, keys, lambda P: fn(np.asarray(P, float).reshape(-1, 3)).reshape(-1, 3))
        except ValueError as ex:
            fail("%r collision item %d: %s" % (g.get("name"), k, ex))
        blob = it.blob
        if rest:
            rs = set(rest)
            idx = [i for i, x in enumerate(keys) if int(x) in rs]
            left = {}
            for kk in ka:
                left.setdefault(int(kk) >> 8, set()).add(int(kk))
            dropped = set(int(x) for x in rest)
            for si_, ks_ in left.items():
                if ks_ <= dropped:
                    fail("%r collision item %d: removing the %d shared-vertex triangles would empty section %d (select the whole piece or less)" % (g.get("name"), k, len(rest), si_))
            attr = le.tri_attrs(it.mesh, np.array(rest, np.int64))
            bl = np.unpackbits(np.frombuffer(it.blob, np.uint8), bitorder="little")
            bv = [int(bl[3 * int(x)]) | int(bl[3 * int(x) + 1]) << 1 | int(bl[3 * int(x) + 2]) << 2 for x in rest]
            new = fn(T[idx].reshape(-1, 3)).reshape(-1, 3, 3)
            m2, keymap, changed = le.remove_keys(m, sorted(int(x) for x in rest))
            blob = le.remap_key_table(it.blob, it.nbits, keymap, set(int(x) for x in rest), changed)
            m2, blob, nk = le.add_triangles(m2, new, attr, bv, blob)
            m = m2
        try:
            buf, ntag = le.write_item(buf, it, m, blob)
        except ValueError as ex:
            fail("%r collision item %d: %s (%d triangles share vertices with triangles that stay and had to be removed + re-added)" % (g.get("name"), k, ex, len(rest)))
        log("  detach %r: collision item %d: %d triangles moved in place, %d removed + re-added; tagfile %d -> %d" % (g.get("name"), k, len(done), len(rest), it.tsz, ntag))
        total += len(keys)
    return buf, total


# =============================================================================================== driver
def _digest(edits, paths):
    h = hashlib.sha1(json.dumps(edits, sort_keys=True).encode())
    for p in paths:
        h.update(str(os.path.getsize(p)).encode())
        h.update(hashlib.sha1(open(p, "rb").read()).digest())      # the CONTENT of the input pak: a same-size edit upstream (in-place tagfile edits) left stale output (window pocket)
    here = os.path.dirname(os.path.abspath(__file__))
    for fn in sorted(("level_morph.py", "geoedit.py", "snow_fill.py", "snow_stitch.py", "level_edit.py", "coll_edit.py")):       # the CODE too: a pipeline fix must rebuild the cached morphed paks
        fp = os.path.join(here, fn)
        if os.path.exists(fp):
            h.update(open(fp, "rb").read())
    return h.hexdigest()[:12]


def check_entry(g):
    if int(g.get("version", 1)) > VERSION:
        fail("%r: edit version %s is newer than this build (%d)" % (g.get("name"), g.get("version"), VERSION))
    if g.get("kind") == "restore":
        for k in ("asset", "plane", "box"):
            if k not in g:
                fail("%r: restore needs %r" % (g.get("name"), k))
        for k in ("normal", "d"):
            if k not in g["plane"]:
                fail("%r: restore plane needs %r" % (g.get("name"), k))
    elif g.get("kind") == "morph":
        for k in ("verts", "box", "op"):
            if k not in g:
                fail("%r: morph needs %r" % (g.get("name"), k))
        if (g["op"] in ("flatten", "snow") and "y" not in g) or (g["op"] == "translate" and "delta" not in g) or (g["op"] == "displace" and "field" not in g):
            fail("%r: morph %s needs its parameter" % (g.get("name"), g["op"]))
    else:
        for k in ("tris", "box", "transform"):
            if k not in g:
                fail("%r: detach needs %r" % (g.get("name"), k))


WALL_FLATTENS = set()             # (level, name) of flatten entries that were skipped because they only selected wall faces


def wall_only_flatten(R, g, log):
    """In the Supermarket (screenshot wall-A.png) the editor's flatten 'pat-bldg-runner-store flatten 1' selected the 0.9 m high wall strip under a window
    (entrance_door_walls + exterior_wall, x -499.5..-497.5, z 275.9, y 17.93..18.83) - every vertex of it is a vertical wall face - and squashed it to y 18.224:
    the wall below the sill vanished (dark void) and the baked snow streams copied onto it drew a flat white plank.  A flatten lowers SNOW; a selection
    that holds only vertices of steep (wall) triangles of a wall submesh is a mis-selection and is left out (render, collision and wall-bake)."""
    if g.get("op") != "flatten" or not g.get("verts"):
        return False
    verts = np.array(g["verts"], np.int64)
    try:
        i0 = R.find_primary(g, verts, g["box"], float(g.get("tol", TOL)))
    except SystemExit:
        return False
    if not _WALL_RX.search(R.p.submeshes[i0]["name"].split("|")[-1]):
        return False
    s0 = R.sub(i0)
    if verts.max() >= s0.n:
        return False
    W = s0.world()
    I, live = s0.live_tris()
    T = I[live]
    nrm = np.cross(W[T[:, 1]] - W[T[:, 0]], W[T[:, 2]] - W[T[:, 0]])
    ln = np.maximum(np.linalg.norm(nrm, axis=1), 1e-12)
    wall_v = np.zeros(s0.n, bool)
    wall_v[T[np.abs(nrm[:, 1]) / ln < 0.5].ravel()] = True
    if wall_v[verts].mean() < 0.9:
        return False
    WALL_FLATTENS.add((g.get("level"), g.get("name")))
    log("  morph %r: SKIPPED - all %d selected vertices are wall faces of %s (a flatten must not squash a wall)" % (g.get("name"), len(verts), R.p.submeshes[i0]["name"][-40:]))
    return True


RESTORE_SLAB = 0.15               # m: default thickness (behind / in front of the plane) of a restore selection
RESTORE_DOT = 0.5                 # a triangle belongs to the wall when its normal dot the plane normal is at least this


def restore_selection(S, g):
    """stock world-space Sub: -> (vertex ids, stock world positions, selected triangle ids)
    = the vertices of the live stock triangles that face along plane.normal, lie within `slab` of the plane (n . p = d) and have their centroid inside g["box"]"""
    pl = g["plane"]
    n = np.array(pl["normal"], float)
    n /= np.linalg.norm(n)
    slab = float(pl.get("slab", RESTORE_SLAB))
    W = S.world()
    I, live = S.live_tris()
    T = I[live]
    tid = np.nonzero(live)[0]
    if not len(T):
        return np.zeros(0, np.int64), W, np.zeros(0, np.int64)
    nrm = np.cross(W[T[:, 1]] - W[T[:, 0]], W[T[:, 2]] - W[T[:, 0]])
    ln = np.maximum(np.linalg.norm(nrm, axis=1), 1e-12)
    c = W[T].mean(1)
    b = np.array(g["box"], float)
    ok = (((nrm / ln[:, None]) @ n) >= float(pl.get("min_dot", RESTORE_DOT))) & (np.abs(c @ n - float(pl["d"])) <= slab) \
        & (c >= b[:3]).all(1) & (c <= b[3:]).all(1)
    return np.unique(T[ok].ravel()), W, tid[ok]


def restore_render(R, S, g, log):
    """reset the selected wall's vertices (positions + every other per-vertex stream) of the asset's world-space submeshes to the stock pak.
    -> (stock positions of the vertices that really differed, #vertices selected, #stream values restored)"""
    out = []
    nsel = nstream = ncut = 0
    for i in R.world_candidates(g["box"], 0.5):
        names = [nm for it in R.owners.get(i, []) for nm, ids in it.names if i in ids]
        if len(R.owners.get(i, [])) != 1 or not any(g["asset"] in nm for nm in names):
            continue
        sm, sm0 = R.p.submeshes[i], S.p.submeshes[i]
        if sm["name"] != sm0["name"] or sm["vcount"] != sm0["vcount"]:
            fail("%r: submesh #%d differs from the stock pak (%s / %d vs %s / %d)" % (g.get("name"), i, sm["name"][-40:], sm["vcount"], sm0["name"][-40:], sm0["vcount"]))
        s0 = S.sub(i)
        v, W0, tids = restore_selection(s0, g)
        if not len(v):
            continue
        s = R.sub(i)
        d = np.abs(s.world(v) - W0[v]).max(1)
        bad = v[d > 1e-4]
        for k in bad:
            s.moved[int(k)] = s.to_local(W0[int(k):int(k) + 1])[0]
        if len(bad):
            out.append(W0[bad])
        I1, live1 = s.live_tris()                                    # triangles other edits cut (tris edits keep indices, make them degenerate)
        I0, live0 = s0.live_tris()
        ncut += int((live0[tids] & ~live1[tids]).sum())
        ch = 0
        for st, st0 in zip(sm["streams"], sm0["streams"]):           # baked per-vertex streams (wall AO etc.): bit exact from the stock pak
            if st["type"] == 64 or not st.get("buf") or st["type"] != st0["type"] or _stride_bits(st) != _stride_bits(st0) or st["vcount"] < s.n:
                continue
            sb = _stride_bits(st)
            for k in v:
                a = _get_bits_big(R.rb, st["buf"] * 8 + int(k) * sb, sb)
                b = _get_bits_big(S.rb, st0["buf"] * 8 + int(k) * sb, sb)
                if a != b:
                    _put_bits_big(R.rb, st["buf"] * 8 + int(k) * sb, sb, b)
                    ch += 1
        nstream += ch
        nsel += len(v)
        log("    restore %r submesh #%d %s: %d wall vertices, %d positions differed, %d stream values differed" % (g.get("name"), i, sm["name"].split("|")[-1][:36], len(v), len(bad), ch))
    if ncut:
        log("    restore %r: %d wall triangles are cut (degenerate) by other edits and stay cut (tris edits remove triangles, they do not move vertices)" % (g.get("name"), ncut))
    return (np.concatenate(out) if out else np.zeros((0, 3))), nsel, nstream


def restore_phys(items, items0, buf, g, log):
    """reset collision vertices on the wall (stock vertex inside the plane slab + box) that differ from the stock phys pak.  -> (buf, #vertices)"""
    pl = g["plane"]
    n = np.array(pl["normal"], float)
    n /= np.linalg.norm(n)
    slab = float(pl.get("slab", RESTORE_SLAB)) + float(pl.get("phys_slab", 0.0))
    b = np.array(g["box"], float)
    total = 0
    if len(items) != len(items0):
        fail("%r: collision item count %d differs from the stock pak (%d)" % (g.get("name"), len(items), len(items0)))
    for k, (it, it0) in sorted(enumerate(zip(items, items0)), key=lambda kv: -kv[1][0].tag_off):
        sv, sv0 = hc.shared_positions(it.mesh), hc.shared_positions(it0.mesh)
        if len(sv) != len(sv0):
            # an 'add' edit (boxes) appended vertices: the stock vertices are the prefix, if (nearly) all of them still sit where they were
            if len(sv) > len(sv0) and (np.abs(sv[:len(sv0)] - sv0).max(1) < 1e-4).mean() > 0.9:
                log("    restore %r: collision item %d has %d shared vertices vs stock %d: the stock ones are the prefix" % (g.get("name"), k, len(sv), len(sv0)))
                sv = sv[:len(sv0)]
            else:
                log("    restore %r: collision item %d has %d shared vertices vs stock %d (skipped)" % (g.get("name"), k, len(sv), len(sv0)))
                continue
        sel = (np.abs(sv0 @ n - float(pl["d"])) <= slab) & (sv0 >= b[:3]).all(1) & (sv0 <= b[3:]).all(1)
        hit = np.nonzero(sel & (np.abs(sv - sv0).max(1) > 1e-4))[0]
        if not len(hit):
            continue
        tgt = sv0[hit]                                  # hit is ascending = the order _phys_vertex_move hands its vertices to fn

        def fn(P, tgt=tgt):
            return tgt
        m2, nv = _phys_vertex_move(it.mesh, sv[hit], fn, 1e-6, None, "%r collision item %d" % (g.get("name"), k), only=hit)
        if not nv:
            continue
        buf, ntag = le.write_item(buf, it, m2, it.blob)
        log("    restore %r: collision item %d: %d shared vertices back to stock, tagfile %d -> %d bytes" % (g.get("name"), k, nv, it.tsz, ntag))
        total += nv
    return buf, total


def restore_level(lv, restores, R, items, pbuf, out_phys, log):
    """the LAST stage of a level: every 'restore' entry resets its wall to the stock paks (render of the asset + collision).
    Runs after all other morph / detach edits and after the wall bake.  -> (render changed, phys changed, pbuf)"""
    if R is None:
        fail("restore: level %s has no render pak" % lv)
    R.p = _reparse(R)
    R.cache.clear()
    src = le.fetch(lv, os.path.join(le.CACHE, "src"), None, ("", "-phys"))
    S = Render(src[""])
    items0 = le.phys_items(src["-phys"])[1] if items is not None and src.get("-phys") else None
    rchg = pchg = False
    for g in restores:
        if not g.get("active", True):
            continue
        pts, nsel, nstr = restore_render(R, S, g, log)
        if len(pts) or nstr:
            rchg = True
        flush_render(R, log)
        R.cache.clear()
        R.p = _reparse(R)
        log("  restore %r: %d wall vertices selected, %d reset, %d baked stream values reset" % (g.get("name"), nsel, len(pts), nstr))
        if items is not None and items0 is not None and g.get("collision", "match") != "none":
            pbuf, nv = restore_phys(items, items0, pbuf, g, log)
            if nv:
                pchg = True
                os.makedirs(os.path.dirname(out_phys), exist_ok=True)
                open(out_phys, "wb").write(bytes(pbuf))
                pp, items = le.phys_items(out_phys)
                pbuf = le.PakBuf(pp.d)
    return rchg, pchg, pbuf


def morph_level(lv, entries, render_in, phys_in, out_render, out_phys, log=print, foreign=()):
    """apply the entries (geoedit dicts) of ONE level to render_in / phys_in (paths or None) -> (render changed, phys changed)"""
    R = Render(render_in) if render_in else None
    del FIN_LOG[:]
    pp = pbuf = items = None
    if phys_in:
        pp, items = le.phys_items(phys_in)
        pbuf = le.PakBuf(pp.d)
    rchg = pchg = False
    restores = [g for g in entries if g.get("kind") == "restore"]
    for g in entries:
        check_entry(g)
        nm = g.get("name")
        if g["kind"] == "restore":
            continue                                             # applied last, after every other edit and the wall bake (restore_level)
        if R is None:
            fail("%r: level %s has no render pak" % (nm, lv))
        if g["kind"] == "morph":
            if wall_only_flatten(R, g, log):
                R.cache.clear()
                continue
            ctx = None
            if g.get("op") == "snow":
                ctx = snow_context(g, items)
                log("  snow %r: %d wall / prop samples from the level's collision" % (nm, ctx["n_wall_samples"]))
            P0, per = apply_morph_render(R, g, log, ctx)
            rchg = True
            if g.get("op") == "displace" and items is not None and g.get("collision", "match") != "none" and not g.get("cfield"):
                g = dict(g, **displace_collision(g, items, log))
            if items is not None and g.get("collision", "match") != "none":
                pbuf, nv = apply_morph_phys(items, pbuf, g, P0, log, ctx)
                pchg |= nv > 0
                if g.get("collision", "match") == "match" and not nv:
                    log("  morph %r: no collision vertex on the selected positions (collision left alone; use collision 'box' to move the hull too)" % nm)
        else:
            apply_detach_render(R, g, log)
            rchg = True
            if items is not None and g.get("collision", "inside") != "none":
                pbuf, nt = apply_detach_phys(items, pbuf, g, log)
                pchg |= nt > 0
                if not nt:
                    log("  detach %r: no collision triangle in the box (collision left alone)" % nm)
        # later entries see the earlier ones: items / render caches are rebuilt when the buffers changed
        if pchg:
            os.makedirs(os.path.dirname(out_phys), exist_ok=True)
            open(out_phys, "wb").write(bytes(pbuf))
            pp, items = le.phys_items(out_phys)
            pbuf = le.PakBuf(pp.d)
        flush_render(R, log)
        R.cache.clear()
        R.p = _reparse(R)
    if R is not None and os.environ.get("T2R_SNOW_FLAT_BAKE", "1") != "0":
        nw = 0
        for g in list(entries) + list(foreign):
            if g.get("kind") == "morph" and g.get("op") == "flatten" and g.get("active", True) and (g.get("level"), g.get("name")) not in WALL_FLATTENS:
                nw += clean_wall_bake(R, g, log)
        if nw:
            rchg = True
            R.cache.clear()
    if restores:
        rc2, pc2, pbuf = restore_level(lv, restores, R, items, pbuf, out_phys, log)
        rchg |= rc2
        pchg |= pc2
    if rchg and out_render:
        os.makedirs(os.path.dirname(out_render), exist_ok=True)
        open(out_render, "wb").write(bytes(R.rb))
    if pchg and out_phys:
        os.makedirs(os.path.dirname(out_phys), exist_ok=True)
        open(out_phys, "wb").write(bytes(pbuf))
        if FIN_LOG:
            json.dump({"level": lv, "tris": list(FIN_LOG)}, open(out_phys + ".fins.json", "w"))
    return rchg, pchg


def _reparse(R):
    """positions are re-read from the edited bytes for the next entry (the Pak object reads from .d)"""
    R.p.d = bytes(R.rb)
    # the Pak object parsed the position streams once: a re-scaled / shifted stream (Sub.write) left its scale / offset stale here, so the next entry on the same
    # submesh decoded every vertex wrongly (check positions off by cm..dm, snow_fill door tongues).  Re-read them from the bytes.
    for sm in R.p.submeshes:
        for st in sm["streams"]:
            if st["type"] == 64 and "offset" in st:
                o = st["offset"]
                st["scale"] = list(struct.unpack_from("<3f", R.p.d, o + 32)) + list(st["scale"][3:])
                st["off"] = list(struct.unpack_from("<3f", R.p.d, o + 48)) + list(st["off"][3:])
    return R.p


def _morph_stale(lv, gl, fg, rin, pin, sig, mdir, log=print):
    """apply_all's body for one stale level -> [files written]"""
    log("level %s: %d morph / detach edit(s)" % (lv, len(gl)))
    o_r = os.path.join(mdir, lv + ".pak")
    o_p = os.path.join(mdir, lv + "-phys.pak")
    for f in (o_r, o_p, o_p + ".fins.json"):
        if os.path.exists(f):
            os.remove(f)
    rc, pc = morph_level(lv, gl, rin, pin, o_r, o_p, log, fg)
    files = [f for f, c in ((o_r, rc), (o_p, pc)) if c]
    os.makedirs(mdir, exist_ok=True)
    json.dump({"sig": sig, "files": files}, open(os.path.join(mdir, lv + ".stamp"), "w"))
    return files


def apply_all(morph_edits, std_files, work_dir, out_dir, game=None, log=print):
    """called by level_edit.build_edits with the morph / detach edits (action dicts from geoedit.to_level_edit) and the files the
    ordinary edits wrote.  -> the new file list (a level's paks replaced by their morphed versions in <out_dir>/morph/)"""
    by_name = {os.path.basename(f): f for f in std_files}
    mdir = os.path.join(out_dir, "morph")
    result = dict(by_name)
    levels = []
    for e in morph_edits:
        if e["level"] not in levels:
            levels.append(e["level"])
    jobs = []                                       # the stale levels: independent (own paks in, own paks out) -> child interpreters (parjobs.py; T2R_PAR_JOBS=1 = serial)
    plan = []
    for lv in levels:
        gl = [e["geo"] for e in morph_edits if e["level"] == lv]
        fg = [e["geo"] for e in morph_edits if e["level"] != lv and e["geo"].get("kind") == "morph" and e["geo"].get("op") == "flatten"]
        src = le.fetch(lv, os.path.join(work_dir, "src"), game, ("", "-phys"))
        rin = by_name.get(lv + ".pak") or src.get("")
        pin = by_name.get(lv + "-phys.pak") or src.get("-phys")
        sig = _digest(gl + fg + [os.environ.get("T2R_SNOW_FLAT_BAKE", "1")], [x for x in (rin, pin) if x])
        stamp = os.path.join(mdir, lv + ".stamp")
        if os.path.exists(stamp):
            try:
                st = json.load(open(stamp))
            except ValueError:
                st = {}
            if st.get("sig") == sig and all(os.path.exists(f) for f in st.get("files", [])):
                log("level %s: morphed paks up to date (%s)" % (lv, sig))
                plan.append((lv, st["files"]))
                continue
        plan.append((lv, None))
        jobs.append(("level_morph", "_morph_stale", (lv, gl, fg, rin, pin, sig, mdir), {}))
    if jobs:
        import parjobs
        built = iter(parjobs.run(jobs, log=log))
    for lv, files in plan:
        for f in (files if files is not None else next(built)):
            result[os.path.basename(f)] = f
    return list(result.values())


# =============================================================================================== verification (tests, `verify`)
def render_positions(path):
    """{submesh index: (n,3) local positions} of every submesh of a pak (for before / after comparisons)"""
    p = ndpak.Pak(path)
    return p, {i: le._qpos(p, sm) for i, sm in enumerate(p.submeshes) if p.pos_stream(sm) is not None}


def verify_phys_valid(path):
    """structural validation of every Havok item (validate_mesh + check_tree4); -> number of problems"""
    bad = 0
    for it in le.phys_items(path)[1]:
        b = hc.validate_mesh(it.mesh)
        b.update(le.check_tree4(it.mesh))
        if b:
            bad += 1
    return bad


if __name__ == "__main__":
    print(__doc__)
