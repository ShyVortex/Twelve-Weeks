"""Collision edits made in the Scene Editor ("Collision edit" mode: move collision vertices, delete triangles, add boxes / quads)
-> the level's Havok collision (-phys.pak).   Offline only (CPU): never starts the game or a GPU tool.

  tools/maps/data/<key>-colledits.json
    {"key": ..., "version": 1, "edits": [
       {"name", "level", "kind": "verts",  "active": true, "moves": [{"from": [x, y, z], "to": [x, y, z]}, ...]},
       {"name", "level", "kind": "delete", "active": true, "tris": [[x0 y0 z0 x1 y1 z1 x2 y2 z2], ...]},
       {"name", "level", "kind": "box",    "active": true, "center": [x, y, z], "size": [w, h, d], "yaw": deg, "like": [x, y, z]},
       {"name", "level", "kind": "quad",   "active": true, "points": [[x, y, z] x4], "thickness": 0.04, "like": [x, y, z]}]}

  Everything is identified by WORLD POSITION (the positions the editor's collision dump shows, i.e. the level's collision after the
  geometry edits), never by vertex index / shape key: those change whenever an earlier edit removes triangles.
    verts   every collision vertex (every Havok item, shared and per-section packed ones) within TOL of "from" is moved by (to - from).
            In place: vertices re-quantised where they are, section boxes grown where a vertex left them (never shrunk), the primitive
            trees, the section tree and the simd tree refitted; same tagfile size, same shape keys.  A packed vertex that leaves its
            section's 11/11/10 bit range makes the section re-quantise all its packed vertices over a bigger box (<= 1.6 cm error).
            A target outside the item's mesh domain is clamped to it (reported).
    delete  the collision triangles whose three vertices are at "tris" (a quad's two halves are separate triangles).  Sections that
            would become empty keep their smallest triangle, shrunk to a speck (level_edit.shrink_kept_triangle), like geoedit removals.
    box     a solid box (12 triangles) joining the collision item of the nearest plain wall triangle (level_edit.add_box_plan rules:
            item needs room for new keys, a growable tagfile page, the box inside the item's mesh domain);
    quad    a flat slab over 4 points (thickness 4 cm, 12 triangles), same item rules.
    clear   (auto file) deletes the collision of ONE level that stands in a ground area (stray ledges, rubble, old surface patches): every triangle
            whose centroid is in "box" [x0, z0, x1, z1], that lies completely inside "rect" (the area the new ground covers), lies between
            ground-0.8 m and ground+"up" (2.2 m) and is not tall (< "tall" 2.2 m: walls stay).  The ground height is the render snow surface.
    ground  (auto file) a render-following ground: a grid over "rect" ("cell" m) whose vertex heights are the render snow height (up-facing triangles of
            the submeshes whose name contains one of "meshes") + "lift" m, the collision material copied from the nearest triangle with the material
            record "mrec" (stock snow, 8 byte hex) near "like".  Stock snow collision is a ~12x decimated copy of the render snow mesh, 5 cm above it.
            "render_levels": the levels whose render pak holds that snow (read from the pipeline's files, so a Scene Editor save moves the ground with it).
  Order per level: deletes, moves, adds (so deleting a triangle and moving its vertices in one go is fine).

  python coll_edit.py show <key>              # the colledit actions the spec turns into
  python coll_edit.py apply <key>             # level_edit.py apply <key> (sp_maps.json edits + geoedits + these) -> re/maps/level-edit-cache/out/
  python coll_edit.py verify <key>            # re-read out/colledit/<level>-phys.pak: moved vertices at their targets, structure valid

  tools/maps/data/<key>-colledits-auto.json   the same format, written by tools/maps/hall_floor.py (never by the Scene Editor); applied in the same pass
            as the Scene Editor file ("clear" / "ground" kinds live here).
Hook: geoedit.edits_for(key) appends {"action": "colledit", "level", "col": <spec edit>} entries; level_edit.build_edits runs
coll_edit.apply_all on them after the ordinary and the morph / detach edits; output <out>/colledit/<level>-phys.pak (the editor
shows the newest pipeline output, but loads the level WITHOUT this folder when it edits collision, so "from" always means the
unedited position).
"""
import copy
import hashlib
import json
import math
import os
import struct
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import level_edit as le  # noqa: E402
import havok_convert as hc  # noqa: E402

VERSION = 1
TOL = 1.2e-3                    # m: position match (the editor welds vertices at 1 mm; float32 export + quantisation of the shared vertices)
DATA = os.path.join(HERE, "data")


def spec_path(key):
    return os.path.join(DATA, f"{key}-colledits.json")


def load(key):
    p = spec_path(key)
    return json.load(open(p, encoding="utf-8")).get("edits", []) if os.path.exists(p) else []


def to_level_edit(g):
    return {"name": g.get("name", "collision edit"), "level": g["level"], "action": "colledit", "col": g}


def auto_path(key):
    return os.path.join(DATA, f"{key}-colledits-auto.json")


def load_auto(key):
    p = auto_path(key)
    return json.load(open(p, encoding="utf-8")).get("edits", []) if os.path.exists(p) else []


def edits_for(key):
    """level_edit-style entries of a map's active collision edits (appended to its edits by geoedit.edits_for): the Scene Editor's file, then the auto file"""
    return [to_level_edit(g) for g in load(key) + load_auto(key) if g.get("active", True)]


def fail(msg):
    raise SystemExit("collision edit: " + msg)


# ================================================================================================ vertex moves
def _near(P, F, tol):
    """for every row of P the index of the first row of F within tol (Chebyshev), else -1.  F is small, P can be large."""
    out = np.full(len(P), -1, np.int64)
    for j, f in enumerate(F):
        hit = (np.abs(P - f) <= tol).all(1) & (out < 0)
        out[hit] = j
    return out


def _pack(P, dmin, dmax):
    ext = np.where(dmax > dmin, dmax - dmin, 1.0)
    maxq = np.array([0x1FFFFF, 0x1FFFFF, 0x3FFFFF], float)
    q = np.clip(np.rint((P - dmin) / ext * maxq), 0, maxq).astype(np.uint64)
    return q[:, 0] | q[:, 1] << np.uint64(21) | q[:, 2] << np.uint64(42)


def move_vertices(m, F, D, tol=TOL, label=""):
    """Mesh m with every vertex at a row of F (n,3) moved by the matching row of D (n,3).
    -> (new mesh, shared vertices moved, packed vertices moved, clamped vertices)"""
    F = np.asarray(F, float).reshape(-1, 3)
    D = np.asarray(D, float).reshape(-1, 3)
    n = copy.deepcopy(m)
    dmin, dmax = m.domain()
    sv = hc.shared_positions(m)
    prims = np.frombuffer(m.prims, np.uint8).reshape(-1, 4)
    clamped = 0
    # ---- shared vertices
    mi = _near(sv, F, tol) if len(sv) else np.zeros(0, np.int64)
    gs = np.nonzero(mi >= 0)[0]
    if len(gs):
        P = sv[gs] + D[mi[gs]]
        Pc = np.minimum(np.maximum(P, dmin), dmax)
        clamped += int((np.abs(Pc - P) > 1e-6).any(1).sum())
        sh = n.shared.astype(np.uint64).copy()
        sh[gs] = _pack(Pc, dmin, dmax)
        n.shared = sh
    gset = {int(x) for x in gs}
    sv2 = hc.shared_positions(n)
    # ---- packed (per-section) vertices
    pk_moved = {}                                             # section -> local packed indices moved
    npk = 0
    for si, s in enumerate(n.sections):
        if not s.npv:
            continue
        cp = np.frombuffer(s.codec, np.float32).astype(np.float64).copy()
        q = n.packed[s.fp:s.fp + s.npv].astype(np.int64)
        V = cp[:3] + cp[3:] * np.stack([q & 0x7FF, (q >> 11) & 0x7FF, q >> 22], 1)
        pm = _near(V, F, tol)
        idx = np.nonzero(pm >= 0)[0]
        if not len(idx):
            continue
        V2 = V.copy()
        P = V[idx] + D[pm[idx]]
        Pc = np.minimum(np.maximum(P, dmin), dmax)
        clamped += int((np.abs(Pc - P) > 1e-6).any(1).sum())
        V2[idx] = Pc
        maxq = np.array([2047.0, 2047.0, 1023.0])
        qn = np.rint((V2 - cp[:3]) / np.where(cp[3:] > 0, cp[3:], 1.0))
        recon = cp[:3] + cp[3:] * np.clip(qn, 0, maxq)
        requant = bool((np.abs(recon - V2) > cp[3:] * 0.51 + 1e-6).any())          # outside the packed range (or a zero-scale section, e.g. one packed vertex)
        if requant:              # left the section's packed range: re-quantise every packed vertex over a bigger box
            lo, hi = V2.min(0), V2.max(0)
            sc = np.where(hi > lo, (hi - lo) / maxq, 1e-4)
            cp[:3], cp[3:] = lo, sc
            qn = np.rint((V2 - lo) / sc)
            s.codec = cp.astype(np.float32).tobytes()
            # decode with the float32 codec the game will read, and fix up rounding at the edges
            cp32 = np.frombuffer(s.codec, np.float32).astype(np.float64)
            qn = np.rint((V2 - cp32[:3]) / cp32[3:])
        qn = np.clip(qn, 0, maxq).astype(np.int64)
        n.packed = n.packed.copy()
        n.packed[s.fp:s.fp + s.npv] = (qn[:, 0] | qn[:, 1] << 11 | qn[:, 2] << 22).astype(np.uint32)
        pk_moved[si] = {int(i) for i in idx} if not requant else set(range(s.npv))      # a new codec shifts every packed vertex a little: all their primitives are refitted
        npk += len(idx)
    if not gset and not pk_moved:
        return n, 0, 0, 0
    # ---- refit boxes / trees of every section that holds a moved vertex
    sec_changed, moved_prims = set(), {}
    for si, s in enumerate(n.sections):
        nv = s.npv + s.nsh
        svi = [int(x) for x in n.svi[s.so:s.so + s.nsh]]
        pkm = pk_moved.get(si, set())
        if not pkm and not (gset and gset.intersection(svi)):
            continue
        sec_changed.add(si)
        mp = set()
        for p_ in range(s.npr):
            for v in {int(x) for x in prims[s.po + p_]}:
                if v < s.npv:
                    if v in pkm:
                        mp.add(p_)
                        break
                elif v < nv and svi[v - s.npv] in gset:
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
        lo = np.where(V.min(0) >= old[0, :3] - 1e-5, old[0, :3], lo)           # a section box never shrinks and only grows on the axes where a vertex left it
        hi = np.where(V.max(0) <= old[1, :3] + 1e-5, old[1, :3], hi)
        lo = np.maximum(lo, dmin.astype(np.float32))
        hi = np.minimum(hi, dmax.astype(np.float32))
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
        pb[~okp] = old_box                                  # ND filler primitive (never hit)
        mp = moved_prims[si]
        s.nodes = le._refit_codec_tree(s.nodes, 4, nb[0], nb[1], lambda d, pb=pb, mp=mp: (pb[d, 0], pb[d, 1], d in mp), old_root=(old_box[0], old_box[1]))

    def sec_leaf(d):
        b = np.frombuffer(n.sections[d].dom, np.float32).reshape(2, 4)[:, :3].astype(np.float64)
        return b[0], b[1], d in sec_changed
    n.tree5 = le._refit_codec_tree(n.tree5, 5, dmin, dmax, sec_leaf)
    pbox = {}
    for si in sec_changed:
        s = n.sections[si]
        V = hc.section_vertices(n, s, sv2)
        nv = s.npv + s.nsh
        for p in moved_prims[si]:
            r = prims[s.po + p].astype(np.int64)
            if (r < nv).all():
                pbox[si << 8 | p << 1] = (V[r].min(0), V[r].max(0))
    movedp = set(pbox)
    simd = bytearray(n.simd)

    def refit(i):
        f = np.frombuffer(bytes(simd[112 * i:112 * i + 96]), np.float32).reshape(6, 4).copy()
        data = np.frombuffer(bytes(simd[112 * i + 96:112 * i + 112]), "<u4")
        lo_all, hi_all, any_c = np.full(3, np.inf), np.full(3, -np.inf), False
        for j in range(4):
            if f[0, j] > f[1, j]:
                continue
            if data[j] & 1:
                k = int(data[j] >> 1)
                c = k in movedp
                if c:
                    lo, hi = pbox[k]
            else:
                lo, hi, c = refit(int(data[j] >> 1))
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
    return n, len(gset), npk, clamped


# ================================================================================================ triangle selection / shapes
def _match_triangles(mesh, tris, tol=TOL):
    """shape keys of the triangles of `mesh` whose three vertices lie at the given (n,3,3) world triangles (any vertex order)"""
    keys, T, _ = hc.triangles(mesh)
    if not len(T) or not len(tris):
        return []
    cen = T.mean(1)
    order = np.argsort(cen[:, 0], kind="stable")
    xs = cen[order, 0]
    out = []
    for t in tris:
        c = t.mean(0)
        a, b = np.searchsorted(xs, c[0] - 2 * tol), np.searchsorted(xs, c[0] + 2 * tol)
        for i in order[a:b]:
            if (np.abs(cen[i] - c) <= 2 * tol).all():
                d = np.linalg.norm(T[i][:, None, :] - t[None, :, :], axis=2)     # 3x3 vertex distances
                if (d.min(1) <= tol).all() and (d.min(0) <= tol).all():
                    out.append(int(keys[i]))
    return out


def _whole_prims(mesh, keys):
    """quad primitives are two triangles (keys k and k|1) that the trees treat as one primitive: a half cannot go alone, so a selected half takes its mate"""
    have = {int(k) for k in hc.triangles(mesh)[0]}
    out = set(keys)
    out |= {k ^ 1 for k in keys if (k ^ 1) in have}
    return sorted(out)


def thick_quad(P, thickness=0.04):
    """12 triangles of a slab over the 4 points P (in order around the quad), `thickness` m thick, centred on the quad's plane"""
    P = np.asarray(P, float).reshape(4, 3)
    n = np.cross(P[2] - P[0], P[3] - P[1])
    ln = np.linalg.norm(n)
    if ln < 1e-9:
        fail("quad points are collinear")
    n = n / ln * (thickness / 2)
    W = np.vstack([P - n, P + n])                           # 0..3 bottom, 4..7 top
    quads = [(0, 3, 2, 1), (4, 5, 6, 7), (0, 1, 5, 4), (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7)]
    out = []
    for a, b, c, d in quads:
        out += [[W[a], W[b], W[c]], [W[a], W[c], W[d]]]
    T = np.array(out)
    ctr = W.mean(0)
    for i, t in enumerate(T):
        if np.dot(np.cross(t[1] - t[0], t[2] - t[0]), t.mean(0) - ctr) < 0:
            T[i] = t[[0, 2, 1]]
    return T


# ================================================================================================ render-following ground
STEP = 0.05
_FIELDS = {}


def ground_field(render_paths, meshes, rect, max_y=19.6, pad=1.0):
    """(xs, zs, H): highest up-facing render snow height on a STEP m grid over rect (x0, z0, x1, z1) + pad, from the submeshes (of the render paks)
    whose name contains one of `meshes`; holes filled from the nearest cell.  Cached per (paks, meshes, rect)."""
    key = (tuple(render_paths), tuple(meshes), tuple(rect), max_y)
    if key in _FIELDS:
        return _FIELDS[key]
    import level_morph as lm
    x0, z0, x1, z1 = rect[0] - pad, rect[1] - pad, rect[2] + pad, rect[3] + pad
    xs = np.arange(x0, x1 + 1e-9, STEP)
    zs = np.arange(z0, z1 + 1e-9, STEP)
    H = np.full((len(zs), len(xs)), -np.inf)
    ntri = 0
    for path in render_paths:
        R = lm.Render(path)
        for j, sm in enumerate(R.p.submeshes):
            nm = sm["name"]
            if not any(m in nm for m in meshes) or "shadow" in nm.lower():
                continue
            try:
                sub = R.sub(j)
            except SystemExit:
                continue
            W = sub.world()
            if not len(W) or W[:, 0].max() < x0 or W[:, 0].min() > x1 or W[:, 2].max() < z0 or W[:, 2].min() > z1:
                continue
            I, live = sub.live_tris()
            for t in W[I[live]]:
                if t[:, 0].max() < x0 or t[:, 0].min() > x1 or t[:, 2].max() < z0 or t[:, 2].min() > z1 or t[:, 1].min() > max_y:
                    continue
                n = np.cross(t[1] - t[0], t[2] - t[0])
                if n[1] <= 0.5 * np.linalg.norm(n):
                    continue
                ntri += 1
                i0, i1 = np.searchsorted(xs, t[:, 0].min()), np.searchsorted(xs, t[:, 0].max(), "right")
                j0, j1 = np.searchsorted(zs, t[:, 2].min()), np.searchsorted(zs, t[:, 2].max(), "right")
                if i0 >= i1 or j0 >= j1:
                    continue
                X, Z = np.meshgrid(xs[i0:i1], zs[j0:j1])
                a, b, c = t
                d = (b[2] - c[2]) * (a[0] - c[0]) + (c[0] - b[0]) * (a[2] - c[2])
                if abs(d) < 1e-12:
                    continue
                l1 = ((b[2] - c[2]) * (X - c[0]) + (c[0] - b[0]) * (Z - c[2])) / d
                l2 = ((c[2] - a[2]) * (X - c[0]) + (a[0] - c[0]) * (Z - c[2])) / d
                l3 = 1 - l1 - l2
                m = (l1 >= -1e-9) & (l2 >= -1e-9) & (l3 >= -1e-9)
                Y = l1 * a[1] + l2 * b[1] + l3 * c[1]
                sl = H[j0:j1, i0:i1]
                sl[m] = np.maximum(sl[m], Y[m])
        del R
    if not ntri:
        fail("ground: no render snow triangles (meshes %s) over %s in %s" % (list(meshes), list(rect), [os.path.basename(p) for p in render_paths]))
    hole = ~np.isfinite(H)
    if hole.any():
        from scipy.ndimage import distance_transform_edt
        _, (iz, ix) = distance_transform_edt(hole, return_indices=True)
        H = H[iz, ix]
    _FIELDS[key] = (xs, zs, H)
    return _FIELDS[key]


_SMOOTH = {}


def smooth_field(F, open_r=0.4, max_slope=0.5):
    """a walkable version of the render height field: (1) a grey opening with a (2 open_r) square removes ridges / spikes narrower than that (a removed wall's footing,
    a snow lip), (2) the slope is limited to max_slope (rise / run) by lowering the high side (two chamfer sweeps over the whole field, so a plateau
    beside a bank is cut from the bank's foot, never with a jump).  Cached per field object."""
    k = (id(F), open_r, max_slope)
    if k in _SMOOTH:
        return _SMOOTH[k]
    from scipy.ndimage import grey_opening
    xs, zs, H = F
    n = max(1, int(round(open_r / STEP)))
    H = grey_opening(H, size=(2 * n + 1, 2 * n + 1), mode="nearest")
    H = H.copy()
    dy = max_slope * STEP
    dd = dy * 1.41421356
    nz, nx = H.shape
    for _ in range(2):
        for j in range(nz):                                          # forward sweep
            for i in range(nx):
                h = H[j, i]
                if i and H[j, i - 1] + dy < h: h = H[j, i - 1] + dy
                if j:
                    if H[j - 1, i] + dy < h: h = H[j - 1, i] + dy
                    if i and H[j - 1, i - 1] + dd < h: h = H[j - 1, i - 1] + dd
                    if i + 1 < nx and H[j - 1, i + 1] + dd < h: h = H[j - 1, i + 1] + dd
                H[j, i] = h
        for j in range(nz - 1, -1, -1):                              # backward sweep
            for i in range(nx - 1, -1, -1):
                h = H[j, i]
                if i + 1 < nx and H[j, i + 1] + dy < h: h = H[j, i + 1] + dy
                if j + 1 < nz:
                    if H[j + 1, i] + dy < h: h = H[j + 1, i] + dy
                    if i + 1 < nx and H[j + 1, i + 1] + dd < h: h = H[j + 1, i + 1] + dd
                    if i and H[j + 1, i - 1] + dd < h: h = H[j + 1, i - 1] + dd
                H[j, i] = h
    _SMOOTH[k] = (xs, zs, H)
    return _SMOOTH[k]


def field_at(F, x, z):
    xs, zs, H = F
    i = np.clip(np.rint((np.asarray(x) - xs[0]) / STEP).astype(int), 0, len(xs) - 1)
    j = np.clip(np.rint((np.asarray(z) - zs[0]) / STEP).astype(int), 0, len(zs) - 1)
    return H[j, i]


def _cell_tris(F, xa, xb, za, zb, lift):
    """the two up-facing triangles over one rectangle (heights = render + lift at its corners), the diagonal that follows the render at the centre better"""
    ya, yb, yc, yd = (float(field_at(F, x, z)) + lift for x, z in ((xa, za), (xb, za), (xb, zb), (xa, zb)))
    a, b, c, d = (xa, ya, za), (xb, yb, za), (xb, yc, zb), (xa, yd, zb)
    cy = float(field_at(F, (xa + xb) / 2, (za + zb) / 2)) + lift
    quad = ([a, d, c], [a, c, b]) if abs((ya + yc) / 2 - cy) <= abs((yb + yd) / 2 - cy) else ([a, d, b], [b, d, c])
    out = []
    for t in quad:
        t = np.array(t, float)
        if np.cross(t[1] - t[0], t[2] - t[0])[1] < 0:
            t = t[[0, 2, 1]]
        out.append(t)
    return out


def _cell_err(F, tris, xa, xb, za, zb, lift):
    """largest |triangle height - (render + lift)| over a 0.1 m sample grid of the cell"""
    worst = 0.0
    for x in np.linspace(xa, xb, max(2, int(round((xb - xa) / 0.1)) + 1)):
        for z in np.linspace(za, zb, max(2, int(round((zb - za) / 0.1)) + 1)):
            for t in tris:
                a, b, c = t
                d = (b[2] - c[2]) * (a[0] - c[0]) + (c[0] - b[0]) * (a[2] - c[2])
                l1 = ((b[2] - c[2]) * (x - c[0]) + (c[0] - b[0]) * (z - c[2])) / d
                l2 = ((c[2] - a[2]) * (x - c[0]) + (a[0] - c[0]) * (z - c[2])) / d
                if min(l1, l2, 1 - l1 - l2) >= -1e-9:
                    worst = max(worst, abs(l1 * a[1] + l2 * b[1] + (1 - l1 - l2) * c[1] - (float(field_at(F, x, z)) + lift)))
                    break
    return worst


def ground_tris(g, F, stock=None):
    """up-facing triangles of the render-following ground of spec entry g, heights from field F.  "cell" m grid; with "root" (m) and "tol" (m) a quadtree:
    root cells that the two triangles follow the render within tol stay whole, the others split in halves down to "cell" (fewer triangles = a smaller tagfile).
    The vertices a small cell puts on a bigger cell's edge are welded to that edge (linear interpolation), so the surface has no cracks (T-junctions).
    stock: optional function (x, z) -> height of the stock collision just outside the rect (or None); with it the ground meets the stock snow at the rect's
    W / S / N edges (g["seam"] sides) and blends back to the render over g["blend"] m (default 1.0)."""
    x0, z0, x1, z1 = g["rect"]
    cell = float(g.get("cell", 0.4))
    lift = float(g.get("lift", 0.05))
    root = float(g.get("root", cell))
    tol = float(g.get("tol", 0.0))
    if stock is not None:
        F = _seam_field(F, g, stock)
    nx, nz = max(1, int(math.ceil((x1 - x0) / root - 1e-9))), max(1, int(math.ceil((z1 - z0) / root - 1e-9)))
    gx, gz = np.linspace(x0, x1, nx + 1), np.linspace(z0, z1, nz + 1)
    rects = []

    def cell_(xa, xb, za, zb):
        tr = _cell_tris(F, xa, xb, za, zb, lift)
        if tol and (xb - xa) / 2 >= cell * 0.99 and (zb - za) / 2 >= cell * 0.99 and _cell_err(F, tr, xa, xb, za, zb, lift) > tol:
            xm, zm = (xa + xb) / 2, (za + zb) / 2
            for xs_ in ((xa, xm), (xm, xb)):
                for zs_ in ((za, zm), (zm, zb)):
                    cell_(xs_[0], xs_[1], zs_[0], zs_[1])
        else:
            rects.append((xa, xb, za, zb))
    for j in range(nz):
        for i in range(nx):
            cell_(gx[i], gx[i + 1], gz[j], gz[j + 1])
    H = {}
    key = lambda x, z: (round(x, 4), round(z, 4))
    order = sorted(rects, key=lambda r: -(r[1] - r[0]) * (r[3] - r[2]))
    for r in order:
        area = (r[1] - r[0]) * (r[3] - r[2])
        for x, z in ((r[0], r[2]), (r[1], r[2]), (r[1], r[3]), (r[0], r[3])):
            k = key(x, z)
            if k in H:
                continue
            h = None
            for q in order:
                if (q[1] - q[0]) * (q[3] - q[2]) <= area * 1.01:
                    break
                if (abs(z - q[2]) < 1e-6 or abs(z - q[3]) < 1e-6) and q[0] + 1e-6 < x < q[1] - 1e-6:
                    ha, hb = H[key(q[0], z)], H[key(q[1], z)]
                    h = ha + (hb - ha) * (x - q[0]) / (q[1] - q[0])
                    break
                if (abs(x - q[0]) < 1e-6 or abs(x - q[1]) < 1e-6) and q[2] + 1e-6 < z < q[3] - 1e-6:
                    ha, hb = H[key(x, q[2])], H[key(x, q[3])]
                    h = ha + (hb - ha) * (z - q[2]) / (q[3] - q[2])
                    break
            H[k] = h if h is not None else float(field_at(F, x, z)) + lift
    out = []
    for xa, xb, za, zb in rects:
        ya, yb, yc, yd = H[key(xa, za)], H[key(xb, za)], H[key(xb, zb)], H[key(xa, zb)]
        a, b, c, d = (xa, ya, za), (xb, yb, za), (xb, yc, zb), (xa, yd, zb)
        cy = float(field_at(F, (xa + xb) / 2, (za + zb) / 2)) + lift
        quad = ([a, d, c], [a, c, b]) if abs((ya + yc) / 2 - cy) <= abs((yb + yd) / 2 - cy) else ([a, d, b], [b, d, c])
        for t in quad:
            t = np.array(t, float)
            if np.cross(t[1] - t[0], t[2] - t[0])[1] < 0:
                t = t[[0, 2, 1]]
            out.append(t)
    return np.array(out)


def _seam_field(F, g, stock):
    """F with the stock collision's height offset (stock - render - lift) blended in along the rect's seam sides ("seam": any of "W", "S", "N", "E")"""
    xs, zs, H = F
    x0, z0, x1, z1 = g["rect"]
    lift = float(g.get("lift", 0.05))
    blend = float(g.get("blend", 1.0))
    sides = g.get("seam", "WSN")
    out = H.copy()
    X, Z = np.meshgrid(xs, zs)
    num = np.zeros_like(H)
    wsum = np.zeros_like(H)
    for sd in sides:
        if sd in "WE":
            xe = x0 if sd == "W" else x1
            sgn = -1.0 if sd == "W" else 1.0
            ts = np.arange(z0, z1 + 1e-9, 0.25)
            pts = [(xe, t, xe + sgn * 0.15, t) for t in ts]
            dist = np.abs(X - xe)
            along = Z
        else:
            ze = z0 if sd == "S" else z1
            sgn = -1.0 if sd == "S" else 1.0
            ts = np.arange(x0, x1 + 1e-9, 0.25)
            pts = [(t, ze, t, ze + sgn * 0.15) for t in ts]
            dist = np.abs(Z - ze)
            along = X
        off = []
        for bx, bz, sx, sz in pts:
            hs = stock(sx, sz)
            off.append(0.0 if hs is None else float(np.clip(hs - (float(field_at(F, bx, bz)) + lift), -0.1, 0.35)))
        off = np.array(off)
        if len(off) > 2:
            off = np.convolve(np.pad(off, 1, mode="edge"), np.ones(3) / 3, mode="valid")
        o = np.interp(along, ts, off)
        w = np.clip(1.0 - dist / blend, 0.0, 1.0)
        num += w * o
        wsum += w
    out = out + num / np.maximum(1.0, wsum)
    return xs, zs, out


def stock_sampler(items, F, rect, margin=1.0, band=0.6):
    """function (x, z) -> highest up-facing stock collision height within [render - 0.15, render + band] (None: nothing) from the phys items near rect"""
    x0, z0, x1, z1 = rect
    tris = []
    for it in items:
        keys, T, _ = hc.triangles(it.mesh)
        if not len(T):
            continue
        m = (T[:, :, 0].max(1) >= x0 - margin) & (T[:, :, 0].min(1) <= x1 + margin) & (T[:, :, 2].max(1) >= z0 - margin) & (T[:, :, 2].min(1) <= z1 + margin)
        T = T[m]
        n = np.cross(T[:, 1] - T[:, 0], T[:, 2] - T[:, 0])
        tris.append(T[n[:, 1] > 0.5 * np.linalg.norm(n, axis=1)])
    T = np.vstack(tris) if tris else np.zeros((0, 3, 3))

    def f(x, z):
        best = None
        base = float(field_at(F, x, z))
        for t in T:
            if t[:, 0].max() < x or t[:, 0].min() > x or t[:, 2].max() < z or t[:, 2].min() > z:
                continue
            a, b, c = t
            d = (b[2] - c[2]) * (a[0] - c[0]) + (c[0] - b[0]) * (a[2] - c[2])
            if abs(d) < 1e-12:
                continue
            l1 = ((b[2] - c[2]) * (x - c[0]) + (c[0] - b[0]) * (z - c[2])) / d
            l2 = ((c[2] - a[2]) * (x - c[0]) + (a[0] - c[0]) * (z - c[2])) / d
            if min(l1, l2, 1 - l1 - l2) < -1e-9:
                continue
            y = l1 * a[1] + l2 * b[1] + (1 - l1 - l2) * c[1]
            if base - 0.15 <= y <= base + band and (best is None or y > best):
                best = y
        return best
    return f


_POOLS = {}


def render_pool(render_paths, rect, pad=1.0, skip=()):
    """(min, max, tris) of EVERY drawn render triangle (all submeshes + prop instances, decals excluded) around rect: what 'no_render' tests collision against.  Cached."""
    key = (tuple(render_paths), tuple(rect), pad, tuple(skip))
    if key not in _POOLS:
        import ray_lookup as rl
        c = np.array([(rect[0] + rect[2]) / 2, 18.5, (rect[1] + rect[3]) / 2])
        r = 0.5 * max(rect[2] - rect[0], rect[3] - rect[1]) + pad + 2.0
        tl = []
        for rp in render_paths:
            for x in rl.render_near(rp, c, r):
                if x["asset"].startswith("dcl-"):
                    continue
                tr = x["tris"]
                if any(w in x["asset"] for w in skip):      # skip: asset-name parts whose UP-FACING triangles do not count as drawn (the floor snow: a fin standing over it is still invisible; steep snow banks are drawn)
                    nn = np.cross(tr[:, 1] - tr[:, 0], tr[:, 2] - tr[:, 0])
                    tr = tr[nn[:, 1] / np.maximum(np.linalg.norm(nn, axis=1), 1e-12) < 0.5]
                tl.append(tr)
        T = np.concatenate(tl) if tl else np.zeros((0, 3, 3))
        T = T[rl.tri_area(T) > 1e-7] if len(T) else T
        _POOLS[key] = (T.min(1) if len(T) else T.reshape(0, 3), T.max(1) if len(T) else T.reshape(0, 3), T)
    return _POOLS[key]


def drawn(pool, P, r):
    """True when a drawn render surface lies within r of point P"""
    import ray_lookup as rl
    mn, mx, T = pool
    if not len(T):
        return False
    m = (mn <= P + r).all(1) & (mx >= P - r).all(1)
    return bool(m.any() and rl.ptri_dist(np.asarray(P, float), T[m]).min() <= r)


def clear_keys(it, g, F, pool=None):
    """shape keys of one phys item's triangles that spec entry g ("clear") removes"""
    keys, T, _ = hc.triangles(it.mesh)
    if not len(T):
        return []
    bx = g["box"]
    rx0, rz0, rx1, rz1 = g["rect"]
    c = T.mean(1)
    sel = (c[:, 0] >= bx[0]) & (c[:, 0] <= bx[2]) & (c[:, 2] >= bx[1]) & (c[:, 2] <= bx[3])
    sel &= (T[:, :, 0].min(1) >= rx0) & (T[:, :, 0].max(1) <= rx1) & (T[:, :, 2].min(1) >= rz0) & (T[:, :, 2].max(1) <= rz1)
    if not sel.any():
        return []
    fl = field_at(F, c[:, 0], c[:, 2])
    ymin, ymax = T[:, :, 1].min(1), T[:, :, 1].max(1)
    sel &= (ymax > fl - float(g.get("down", 0.8))) & (ymin < fl + float(g.get("up", 2.2))) & ((ymax - ymin) < float(g.get("tall", 2.2)))
    if "min_above" in g:                         # optional: only triangles reaching more than min_above m over the render snow (invisible plateaus, mounds)
        sel &= ymax > fl + float(g["min_above"])
    if "below" in g:                             # optional: only triangles wholly more than "below" m under the render snow (collapsed slivers under the floor)
        sel &= ymax < fl - float(g["below"])
    if "min_ny" in g or "max_area" in g:        # optional filter: only up-facing triangles (min_ny) and / or tiny slivers of any orientation (max_area, m2); walls stay
        nrm = np.cross(T[:, 1] - T[:, 0], T[:, 2] - T[:, 0])
        nl = np.linalg.norm(nrm, axis=1) + 1e-12
        keep = np.zeros(len(T), bool)
        if "min_ny" in g:
            keep |= nrm[:, 1] / nl >= float(g["min_ny"])
        if "max_area" in g:
            keep |= 0.5 * nl <= float(g["max_area"])
        sel &= keep
    if "and_max_ny" in g:                        # optional: only triangles that are not up-facing (ny <= value): collapsed slivers, walls
        nrm2 = np.cross(T[:, 1] - T[:, 0], T[:, 2] - T[:, 0])
        sel &= nrm2[:, 1] / (np.linalg.norm(nrm2, axis=1) + 1e-12) <= float(g["and_max_ny"])
    if "no_render" in g and pool is not None:   # optional: only collision with NO drawn surface within no_render m of any vertex / its centroid (fins, folds, leftovers; drawn walls and props stay)
        r_ = float(g["no_render"])
        for j in np.nonzero(sel)[0]:
            if any(drawn(pool, P, r_) for P in (T[j].mean(0), T[j][0], T[j][1], T[j][2])):
                sel[j] = False
    return [int(k) for k in keys[sel]]


def plan_add_surface(phys, TB, like, mrec, name="", like_max=40.0):
    """like plan_add for a GROUND: (item index, key) of the up-facing triangle with the 8-byte material record `mrec` nearest to `like`, in an item with
    room for new keys whose mesh domain holds TB"""
    best = None
    lo, hi = TB.reshape(-1, 3).min(0), TB.reshape(-1, 3).max(0)
    for k, it in enumerate(phys):
        m_ = it.mesh
        dmin_, dmax_ = m_.domain()
        if (lo < dmin_).any() or (hi > dmax_).any():
            continue
        if len(m_.sections) + 2 + len(TB) // 100 >= 1 << (m_.keybits - 8) or len(it.blob) * 8 < 3 * (1 << m_.keybits):
            continue
        try:
            le._grow_tag_page(None, it.pak, it, it.tsz + 100000)
        except ValueError:
            continue
        ridx = le._recs(it).get(mrec.lower())
        if ridx is None:
            continue
        keys, T, tg = hc.triangles(m_)
        if not len(T):
            continue
        nrm = np.cross(T[:, 1] - T[:, 0], T[:, 2] - T[:, 0])
        nl = np.linalg.norm(nrm, axis=1)
        ok = (tg >> 6 == ridx) & (nrm[:, 1] > 0.8 * nl) & (0.5 * nl > 0.02)
        if not ok.any():
            continue
        d = np.linalg.norm(T[ok].mean(1) - like, axis=1)
        j = int(np.argmin(d))
        if best is None or d[j] < best[0]:
            best = (float(d[j]), k, int(keys[ok][j]))
    if best is None or best[0] > like_max:
        fail("%r: no collision item with room has an up-facing triangle with material record %s within %.0f m of %s" % (name, mrec, like_max, np.round(like, 2).tolist()))
    return best[1], best[2], best[0]


def plan_add(phys, TB, like, name="", like_max=40.0):
    """(phys item index, reference shape key) for new triangles TB: the item holding the nearest plain wall triangle to `like` that has
    room for new keys and a growable tagfile page, the new triangles lying inside its mesh domain (level_edit.add_box_plan rules)"""
    best = None
    lo, hi = TB.reshape(-1, 3).min(0), TB.reshape(-1, 3).max(0)
    for k, it in enumerate(phys):
        m_ = it.mesh
        dmin_, dmax_ = m_.domain()
        if (lo < dmin_).any() or (hi > dmax_).any():
            continue
        if len(m_.sections) + 1 >= 1 << (m_.keybits - 8) or len(it.blob) * 8 < 3 * (1 << m_.keybits):
            continue
        try:
            le._grow_tag_page(None, it.pak, it, it.tsz + 100000)
        except ValueError:
            continue
        keys, T, tg = hc.triangles(it.mesh)
        if not len(T):
            continue
        nrm = np.cross(T[:, 1] - T[:, 0], T[:, 2] - T[:, 0])
        nl = np.linalg.norm(nrm, axis=1)
        b_ = it.io + 48
        ro_, nr_ = it.pak.ptr(b_ + 80), struct.unpack_from("<I", it.pak.d, b_ + 60)[0]
        plain = {i for i in range(nr_) if it.pak.d[ro_ + 8 * i] == 1 and it.pak.d[ro_ + 8 * i + 2] == 0 and it.pak.d[ro_ + 8 * i + 3] == 0}
        okm = np.isin(tg >> 6, np.array(sorted(plain), np.int64))
        wall = okm & (np.abs(nrm[:, 1]) < 0.3 * nl + 1e-12) & (0.5 * nl > 0.25)
        if not wall.any():
            wall = okm & (0.5 * nl > 0.05)                  # no wall in this item: any plain surface will do
        if not wall.any():
            continue
        d = np.linalg.norm(T[wall].mean(1) - like, axis=1)
        j = int(np.argmin(d))
        if best is None or d[j] < best[0]:
            best = (float(d[j]), k, int(keys[wall][j]))
    if best is None or best[0] > like_max:
        fail("%r: no collision item with room for new triangles has a plain surface within %.0f m of %s (the new shape must lie inside an item's mesh "
             "domain, and the item needs a free section slot and a tagfile page that can grow); place an invis-collision prop instead" % (name, like_max, np.round(like, 2).tolist()))
    return best[1], best[2], best[0]


# ================================================================================================ one level
def _protect_empty_sections(m, drop, log, k):
    """drop minus the smallest triangle of every section the drop would empty -> (keys to drop, [(section, kept key)])"""
    kall, Tall, _ = hc.triangles(m)
    left = {}
    for kk in kall:
        left.setdefault(int(kk) >> 8, set()).add(int(kk))
    drop = set(int(x) for x in drop)
    kept = []
    for si_, ks_ in sorted(left.items()):
        if ks_ <= drop:
            cand = {int(kk): 0.5 * float(np.linalg.norm(np.cross(t[1] - t[0], t[2] - t[0]))) for kk, t in zip(kall, Tall) if int(kk) >> 8 == si_}
            pool = [c for c in cand if cand[c] >= 0.01 and not c & 1] or [c for c in cand if not c & 1] or list(cand)
            keep = min(pool, key=cand.get)
            drop.discard(keep)
            kept.append((si_, keep))
            log("  item %d: section %d would be emptied; kept its smallest triangle (key %#x)" % (k, si_, keep))
    return sorted(drop), kept


def _fold_kept(m, key, log, k, tall=0.08):
    """A triangle kept alive only because its section would be emptied, that stands more than `tall` m high and could not be parked: fold it flat by moving its highest vertex onto its
    lowest one (a zero-area edge at floor level, no vertical span).  Skipped when another triangle shares that vertex (it would be dragged along).  -> (from, delta) or None"""
    keys, T, _ = hc.triangles(m)
    j = np.nonzero(keys == key)[0]
    if not len(j):
        return None
    t = T[j[0]]
    if t[:, 1].max() - t[:, 1].min() <= tall:
        return None
    hi, lo = t[np.argmax(t[:, 1])], t[np.argmin(t[:, 1])]
    others = np.delete(np.arange(len(keys)), j)
    if (np.abs(T[others] - hi).max(2) < 2e-3).any():
        log("  item %d: kept triangle %#x stays standing (its top vertex is shared)" % (k, key))
        return None
    log("  item %d: kept triangle %#x folded flat (%.2f m high)" % (k, key, hi[1] - lo[1]))
    return hi.copy(), lo - hi


def colledit_level(lv, entries, phys_in, out_phys, log=print, render=None):
    """apply the colledit spec entries of ONE level to phys_in -> out_phys.  -> (moved shared, moved packed, deleted, added triangles)"""
    post = [g for g in entries if g.get("post")]            # "post": true entries run on the result of the others (after the vertex moves: collapsed slivers)
    if post:
        entries = [g for g in entries if not g.get("post")]
        tmp = out_phys + ".stage1"
        st1 = colledit_level(lv, entries, phys_in, tmp, log, render) if entries else (0, 0, 0, 0)
        src2 = tmp if os.path.exists(tmp) else phys_in
        if os.path.exists(out_phys):
            os.remove(out_phys)
        st2 = colledit_level(lv, [dict(g, post=False) for g in post], src2, out_phys, log, render)
        if not os.path.exists(out_phys) and os.path.exists(tmp):
            os.replace(tmp, out_phys)
        elif os.path.exists(tmp):
            os.remove(tmp)
        return tuple(a + b for a, b in zip(st1, st2))
    pp, items = le.phys_items(phys_in)
    buf = le.PakBuf(pp.d)
    per = {k: {"del": [], "F": [], "D": [], "add": []} for k in range(len(items))}
    for g in entries:
        if int(g.get("version", VERSION)) > VERSION:
            fail("%r: edit version %s is newer than this build (%d)" % (g.get("name"), g.get("version"), VERSION))
        kind, nm = g.get("kind"), g.get("name")
        if kind == "verts":
            for mv in g["moves"]:
                d = np.array(mv["to"], float) - np.array(mv["from"], float)
                for k in per:
                    per[k]["F"].append(mv["from"])
                    per[k]["D"].append(d)
        elif kind == "delete":
            tr = np.array(g["tris"], float).reshape(-1, 3, 3)
            total = 0
            for k, it in enumerate(items):
                ks = _whole_prims(it.mesh, _match_triangles(it.mesh, tr))
                per[k]["del"].extend(ks)
                total += len(ks)
            if total < len(tr):
                log("  %r: %d of %d triangles found in the collision (the others no longer exist at those positions)" % (nm, total, len(tr)))
        elif kind in ("clear", "ground"):
            if not render or not all(r in render for r in g["render_levels"]):
                fail("%r: needs the render paks of %s (render map: %s)" % (nm, g["render_levels"], sorted(render or {})))
            F = ground_field([render[r] for r in g["render_levels"]], g["meshes"], g["rect"], float(g.get("max_y", 19.6)))
            if kind == "ground" and g.get("smooth"):                 # {"rect": [x0, z0, x1, z1], "open": m, "slope": rise/run}: one smoothed field over a bigger rect, shared by the entries of a lane (no seams between them)
                sm = g["smooth"]
                F = smooth_field(ground_field([render[r] for r in g["render_levels"]], g["meshes"], sm["rect"], float(g.get("max_y", 19.6)), 0.0), float(sm.get("open", 0.4)), float(sm.get("slope", 0.5)))
            if kind == "clear":
                total = 0
                pool = render_pool([render[r] for r in g["render_levels"]], g["rect"], skip=tuple(g.get("no_render_skip", ()))) if "no_render" in g else None
                for k, it in enumerate(items):
                    ks = _whole_prims(it.mesh, clear_keys(it, g, F, pool))
                    per[k]["del"].extend(ks)
                    total += len(ks)
                log("  %r: %d triangles cleared" % (nm, total))
            else:
                TB = ground_tris(g, F, stock_sampler(items, F, g["rect"]) if g.get("seam") else None)
                k, key, dist = plan_add_surface(items, TB, np.array(g["like"], float), g["mrec"], nm, float(g.get("like_max", 40.0)))
                per[k]["add"].append((key, TB))
                log("  ground %r: %d triangles -> collision item %d, material of key %#x (%.1f m away)" % (nm, len(TB), k, key, dist))
        elif kind in ("box", "quad"):
            if kind == "box":
                TB = le.box_tris(np.array(g["center"], float), g["size"], float(g.get("yaw", 0.0)))
            else:
                TB = thick_quad(g["points"], float(g.get("thickness", 0.04)))
            like = np.array(g.get("like") or (g["center"] if kind == "box" else np.mean(g["points"], 0)), float)
            k, key, dist = plan_add(items, TB, like, nm, float(g.get("like_max", 40.0)))
            per[k]["add"].append((key, TB))
            log("  %s %r -> collision item %d, material of key %#x (%.1f m away)" % (kind, nm, k, key, dist))
        else:
            fail("%r: unknown kind %r" % (nm, kind))
    stats = [0, 0, 0, 0]
    for k, it in sorted(enumerate(items), key=lambda kv: -kv[1].tag_off):      # high file offsets first: growing a page moves only later pages
        d = per[k]
        if not (d["del"] or d["F"] or d["add"]):
            continue
        m, blob = it.mesh, it.blob
        adds = []
        for key, TB in d["add"]:                                   # attributes from the item as it was, before keys change
            attr = le.tri_attrs(it.mesh, [key] * len(TB))
            bl = np.unpackbits(np.frombuffer(it.blob, np.uint8), bitorder="little")
            bv = [int(bl[3 * key]) | int(bl[3 * key + 1]) << 1 | int(bl[3 * key + 2]) << 2] * len(TB)
            adds.append((TB, attr, bv))
        if d["del"]:
            keys, kept = _protect_empty_sections(m, sorted(set(d["del"])), log, k)
            m2, keymap, changed = le.remove_keys(m, keys)
            for si_, kk_ in kept:
                r_ = le.shrink_kept_triangle(m2, si_)
                if r_ is not None:
                    m2 = r_[0]
                else:                                              # not parkable (shares vertices): a kept tall sliver (the fin the morph stage left) is folded flat instead
                    ex_ = _fold_kept(m2, kk_, log, k)
                    if ex_ is not None:
                        d["F"].append(ex_[0])
                        d["D"].append(ex_[1])
            blob = le.remap_key_table(it.blob, it.nbits, keymap, set(keys), changed)
            m = m2
            stats[2] += len(keys)
            log("  item %d: %d triangles deleted" % (k, len(keys)))
        if d["F"]:
            m, ns, npk, nclamp = move_vertices(m, d["F"], d["D"], TOL, "item %d" % k)
            stats[0] += ns
            stats[1] += npk
            if ns or npk:
                log("  item %d: %d shared + %d packed vertices moved%s" % (k, ns, npk, (", %d clamped to the item's domain" % nclamp) if nclamp else ""))
        for TB, attr, bv in adds:
            m, blob, nk = le.add_triangles(m, TB, attr, bv, blob)
            stats[3] += len(nk)
        buf, ntag = le.write_item(buf, it, m, blob)
        log("  item %d tagfile %d -> %d bytes" % (k, it.tsz, ntag))
    if sum(stats) == 0:
        return tuple(stats)
    os.makedirs(os.path.dirname(out_phys), exist_ok=True)
    open(out_phys, "wb").write(bytes(buf))
    return tuple(stats)


# ================================================================================================ resolved auto edits (for the Scene Editor)
def resolved_path(key):
    return os.path.join(DATA, f"{key}-colledits-auto.resolved.json")


def resolve_auto(key, phys_by_level, render_by_level, log=print):
    """The exact world triangles the auto file's entries delete ('clear', whole primitives like the build) and add ('ground'), as 9-float triangles, written to
    data/<key>-colledits-auto.resolved.json.  The Scene Editor's Collision view reads ONLY this file (read-only) so it shows what the game gets.
    phys_by_level / render_by_level: level -> pak path (the same inputs the build stage uses)."""
    out = []
    for g in load_auto(key):
        if not g.get("active", True) or g.get("kind") not in ("clear", "ground"):
            continue
        F = ground_field([render_by_level[r] for r in g["render_levels"]], g["meshes"], g["rect"], float(g.get("max_y", 19.6)))
        if g["kind"] == "ground":
            tris = ground_tris(g, F, stock_sampler(le.phys_items(phys_by_level[g["level"]])[1], F, g["rect"]) if g.get("seam") else None).reshape(-1, 9)
        else:
            rows = []
            pool = render_pool([render_by_level[r] for r in g["render_levels"]], g["rect"], skip=tuple(g.get("no_render_skip", ()))) if "no_render" in g else None
            for it in le.phys_items(phys_by_level[g["level"]])[1]:
                ks = set(_whole_prims(it.mesh, clear_keys(it, g, F, pool)))
                if not ks:
                    continue
                keys, T, _ = hc.triangles(it.mesh)
                rows.append(T[np.isin(keys, list(ks))].reshape(-1, 9))
            tris = np.vstack(rows) if rows else np.zeros((0, 9))
        out.append({"name": g.get("name", ""), "level": g["level"], "kind": g["kind"], "active": True, "tris": [[round(float(x), 4) for x in t] for t in tris]})
        log("  resolved %r: %d triangles" % (g.get("name"), len(tris)))
    p = resolved_path(key)
    json.dump({"_comment": "Written by coll_edit.resolve_auto on every build (do not edit): the exact triangles of the auto edits, read by the Scene Editor.", "key": key,
               "version": 1, "edits": out}, open(p, "w", encoding="utf-8", newline="\n"))
    return p


def _resolve_auto_memo(key, auto, phys_by_level, render_by_level, log=print):
    """resolve_auto, skipped when its inputs (the auto edits, the content of the phys / render paks they read, this file's code) are the ones of the run that wrote
    the view file now on disk (marker tools/local/build-cache/resolved/<key>-<digest>.sha = sha1 of that view file; ~25 s a build otherwise)"""
    h = hashlib.sha1(json.dumps(auto, sort_keys=True).encode())
    for g in auto:
        for pth in [phys_by_level[g["level"]]] + [render_by_level[r] for r in g["render_levels"]]:
            h.update(hashlib.sha1(open(pth, "rb").read()).digest())
    h.update(open(__file__.replace(".pyc", ".py"), "rb").read())
    h.update(open(os.path.join(HERE, "level_edit.py"), "rb").read())
    d = os.path.join(os.path.dirname(HERE), "local", "build-cache", "resolved")
    marker = os.path.join(d, "%s-%s.sha" % (key, h.hexdigest()[:20]))
    view = resolved_path(key)
    if not os.environ.get("T2R_NO_BUILD_CACHE") and os.path.exists(marker) and os.path.exists(view):
        if hashlib.sha1(open(view, "rb").read()).hexdigest() == open(marker).read().strip():
            log("  resolved auto file %s up to date" % key)
            return view
    resolve_auto(key, phys_by_level, render_by_level, log)
    if not os.environ.get("T2R_NO_BUILD_CACHE"):
        os.makedirs(d, exist_ok=True)
        open(marker, "w").write(hashlib.sha1(open(view, "rb").read()).hexdigest())
    return view


def _auto_keys():
    return sorted(f[:-len("-colledits-auto.json")] for f in os.listdir(DATA) if f.endswith("-colledits-auto.json"))


# ================================================================================================ pipeline hook
def _digest(edits, paths):
    h = hashlib.sha1(json.dumps(edits, sort_keys=True).encode())
    for p in paths:
        h.update(str(os.path.getsize(p)).encode())
        h.update(hashlib.sha1(open(p, "rb").read()).digest())      # the CONTENT of the input pak: a same-size edit upstream (in-place tagfile edits) left stale output (window pocket)
    h.update(open(__file__, "rb").read())
    return h.hexdigest()[:12]


def _colledit_stale(lv, gl, pin, sig, cdir, render, log=print):
    """apply_all's body for one stale level -> [files written]"""
    outp = os.path.join(cdir, lv + "-phys.pak")
    log("level %s: %d collision edit(s)" % (lv, len(gl)))
    if os.path.exists(outp):
        os.remove(outp)
    st = colledit_level(lv, gl, pin, outp, log, render)
    files = [outp] if os.path.exists(outp) else []
    os.makedirs(cdir, exist_ok=True)
    json.dump({"sig": sig, "files": files}, open(os.path.join(cdir, lv + ".stamp"), "w"))
    log("  -> %d shared + %d packed vertices moved, %d triangles deleted, %d added" % st)
    return files


def apply_all(col_edits, std_files, work_dir, out_dir, game=None, log=print):
    """called by level_edit.build_edits with the colledit actions and the files the earlier stages wrote.
    -> the new file list (a level's -phys.pak replaced by <out_dir>/colledit/<level>-phys.pak)"""
    by_name = {os.path.basename(f): f for f in std_files}
    cdir = os.path.join(out_dir, "colledit")
    result = dict(by_name)
    seen_phys, seen_render = {}, {}
    levels = []
    for e in col_edits:
        if e["level"] not in levels:
            levels.append(e["level"])
    for fn_, f_ in sorted(by_name.items()):                      # levels whose morph left fins (level_morph.morph_fins -> <phys>.fins.json) get their deletes even without colledit entries
        if fn_.endswith("-phys.pak") and os.path.exists(f_ + ".fins.json") and fn_[:-9] not in levels:
            levels.append(fn_[:-9])
    jobs, plan = [], []                              # stale levels: independent -> child interpreters (parjobs.py; T2R_PAR_JOBS=1 = serial)
    for lv in levels:
        gl = [e["col"] for e in col_edits if e["level"] == lv]
        src = le.fetch(lv, os.path.join(work_dir, "src"), game, ("-phys",))
        pin = by_name.get(lv + "-phys.pak") or src.get("-phys")
        if pin and os.path.exists(pin + ".fins.json"):            # the morph stage's fins (partly moved snow triangles, steep + standing): deleted first, same machinery as a 'delete' entry
            fj = json.load(open(pin + ".fins.json"))
            if fj.get("tris"):
                gl.insert(0, {"name": "morph fins: partly moved snow triangles removed (level_morph.morph_fins)", "level": lv, "kind": "delete", "active": True, "tris": fj["tris"]})
        need = sorted({r for g in gl if g.get("kind") in ("clear", "ground") for r in g["render_levels"]})
        render = {}
        for r in need:                                          # the render snow the auto ground follows: the pipeline's pak, else the stock one
            render[r] = by_name.get(r + ".pak") or le.fetch(r, os.path.join(work_dir, "src"), game, ("",))[""]
        seen_phys[lv] = pin
        seen_render.update(render)
        sig = _digest(gl, [pin] + [render[r] for r in need])
        stamp = os.path.join(cdir, lv + ".stamp")
        if os.path.exists(stamp):
            try:
                st = json.load(open(stamp))
            except ValueError:
                st = {}
            if st.get("sig") == sig and all(os.path.exists(f) for f in st.get("files", [])):
                log("level %s: collision edits up to date (%s)" % (lv, sig))
                plan.append((lv, st["files"]))
                continue
        plan.append((lv, None))
        jobs.append(("coll_edit", "_colledit_stale", (lv, gl, pin, sig, cdir, render), {}))
    if jobs:
        import parjobs
        built = iter(parjobs.run(jobs, log=log))
    for lv, files in plan:
        for f in (files if files is not None else next(built)):
            result[os.path.basename(f)] = f
    names = {e["col"].get("name") for e in col_edits}
    for key in _auto_keys():                                       # regenerate the Scene Editor's read-only view of the auto edits on every build
        auto = [g for g in load_auto(key) if g.get("active", True) and g.get("kind") in ("clear", "ground")]
        if auto and all(g.get("name") in names for g in auto) and all(g["level"] in seen_phys and all(r in seen_render for r in g["render_levels"]) for g in auto):
            try:
                _resolve_auto_memo(key, auto, seen_phys, seen_render, log)
            except Exception as ex:                                # a view file must never break the build
                log("  resolved auto file NOT written: %s" % ex)
    return list(result.values())


# ================================================================================================ verification
def problems(path):
    """{item index: {problem: count}} of the structural validation (validate_mesh + check_tree4) of every Havok item"""
    out = {}
    for k, it in enumerate(le.phys_items(path)[1]):
        b = hc.validate_mesh(it.mesh)
        b.update(le.check_tree4(it.mesh))
        if b:
            out[k] = b
    return out


def verify_file(path, baseline=None):
    """number of items with structure problems that the source (`baseline` = its problems()) did not have already"""
    now = problems(path)
    base = baseline or {}
    return sum(1 for k, b in now.items() if any(b[x] > base.get(k, {}).get(x, 0) for x in b))


def find_vertices(path, P, tol):
    """for each row of P (n,3): True when some collision vertex (any item) lies within tol (per axis)"""
    P = np.asarray(P, float).reshape(-1, 3)
    found = np.zeros(len(P), bool)
    for it in le.phys_items(path)[1]:
        m = it.mesh
        sv = hc.shared_positions(m)
        allv = [sv] if len(sv) else []
        for s in m.sections:
            if s.npv:
                cp = np.frombuffer(s.codec, np.float32).astype(np.float64)
                q = m.packed[s.fp:s.fp + s.npv].astype(np.int64)
                allv.append(cp[:3] + cp[3:] * np.stack([q & 0x7FF, (q >> 11) & 0x7FF, q >> 22], 1))
        if allv:
            V = np.vstack(allv)
            for i, p in enumerate(P):
                if not found[i] and (np.abs(V - p) <= tol).all(1).any():
                    found[i] = True
    return found


def main(argv):
    if len(argv) == 2 and argv[0] == "show":
        print(json.dumps({"edits": edits_for(argv[1])}, indent=1))
        return 0
    if len(argv) == 2 and argv[0] == "resolve":
        work = os.path.join(le.CACHE, "src")
        phys, ren = {}, {}
        for g in load_auto(argv[1]):
            for r in g.get("render_levels", []):
                if r not in ren:
                    mp = os.path.join(le.CACHE, "out", "morph", r + ".pak")
                    ren[r] = mp if os.path.exists(mp) else le.fetch(r, work, None, ("",))[""]
            lv = g["level"]
            if lv not in phys:
                cp = os.path.join(le.CACHE, "out", "colledit", lv + "-phys.pak")
                phys[lv] = le.fetch(lv, work, None, ("-phys",))["-phys"]
        print("wrote", resolve_auto(argv[1], phys, ren))
        return 0
    if len(argv) == 2 and argv[0] == "apply":
        import subprocess
        return subprocess.call([sys.executable, os.path.join(HERE, "level_edit.py"), "apply", argv[1]])
    if len(argv) == 2 and argv[0] == "verify":
        ok = True
        out = os.path.join(le.CACHE, "out", "colledit")
        for lv in sorted({g["level"] for g in load(argv[1]) if g.get("active", True)}):
            p = os.path.join(out, lv + "-phys.pak")
            if not os.path.exists(p):
                print("level %s: no %s (nothing changed it, or apply not run)" % (lv, p))
                continue
            bad = verify_file(p, problems(os.path.join(le.CACHE, "src", lv + "-phys.pak")) if os.path.exists(os.path.join(le.CACHE, "src", lv + "-phys.pak")) else None)
            moves = [mv for g in load(argv[1]) if g.get("active", True) and g["level"] == lv and g.get("kind") == "verts" for mv in g["moves"]]
            miss = 0
            if moves:
                miss = int((~find_vertices(p, [mv["to"] for mv in moves], 0.02)).sum())
            print("level %s: %d item(s) with structure problems, %d of %d moved vertices not found at their target" % (lv, bad, miss, len(moves)))
            ok &= bad == 0 and miss == 0
        print("VERIFY", "OK" if ok else "FAILED")
        return 0 if ok else 1
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
