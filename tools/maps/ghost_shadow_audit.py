"""Ghost-shadow audit of a map's active Scene Editor geometry edits (winter Supermarket jackson-market).

  python ghost_shadow_audit.py <key> <dir-with-the-edited-paks> [--src]   # per edit: shadow-proxy triangles that are still live in its region

A "shadow proxy" is every submesh whose name contains 'shadow' (the level's world-space '...tfrag-merge-shadows' meshes and the per-asset
'shadowProxy' / 'shadow_proxy' meshes).  A proxy submesh drawn by one placement (or by none: baked, world space) is UNIQUE; a prototype drawn by
several placements is SHARED (each placement draws it through its own matrix).  For every active edit the region is its box (instance / tris
removals: +0.05; flatten: the box + the snap radius in x / z) and the report counts the live (non-degenerate) proxy triangles that meet it:
  inside   wholly inside the box          (a removal's ghost: should be 0)
  partly   meet the box but reach out of it (shared by neighbours; a removal can not cut them)
  above    flatten only: not-near-vertical triangles whose top is more than 5 cm above the flatten height inside the region (the old mound)
Each is split in unique / shared.  The edit's OWN placement (removed instance record) is excluded: it is hidden with its draw entries.
"""
import json
import os
import re
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "models"))
import level_edit as le  # noqa: E402
import ndpak  # noqa: E402
import geoedit  # noqa: E402

SHADOW = re.compile("shadow", re.I)
RADIUS = 0.4


def owners_of(insts):
    """{submesh: [placements drawing it]}: by AABB match (names), else by the record's own prototype (it.subs) for the unmatched ones"""
    owners = {}
    for it in insts:
        ids = [i for _, g in it.names for i in g] or list(it.subs)
        for i in ids:
            owners.setdefault(i, []).append(it)
    return owners


class Proxy:
    """world triangles of every shadow-proxy submesh of one level pak: arrays T (n,3,3), sub (n), own (n, placement offset or -1), shared (n)"""

    def __init__(self, path):
        self.p = p = ndpak.Pak(path)
        self.insts = le.find_instances(p)
        owners = owners_of(self.insts)
        T, S, O, SH, TI = [], [], [], [], []
        for i, sm in enumerate(p.submeshes):
            if not SHADOW.search(sm["name"]) or p.pos_stream(sm) is None or not sm["icount"]:
                continue
            L = le.submesh_tris(p, i)
            I = np.array(p.indices(sm), np.int64).reshape(-1, 3)
            live = I[:, 0] != I[:, 1]
            ow = owners.get(i, [])
            for it in (ow or [None]):
                W = L
                if it is not None:
                    W = (np.concatenate([L, np.ones(L.shape[:2] + (1,))], 2) @ it.M)[:, :, :3]
                if (W.reshape(-1, 3).max(0) - W.reshape(-1, 3).min(0)).max() > 400:
                    continue
                k = np.nonzero(live)[0]
                T.append(W[k]); S.append(np.full(len(k), i)); O.append(np.full(len(k), it.pak_off if it is not None else -1))
                SH.append(np.full(len(k), len(ow) > 1)); TI.append(k)
        cat = lambda a, s: np.concatenate(a) if a else np.zeros(s)
        self.T, self.sub, self.own = cat(T, (0, 3, 3)), cat(S, 0), cat(O, 0)
        self.shared, self.tri = cat(SH, 0).astype(bool), cat(TI, 0)
        self.lo, self.hi = self.T.min(1), self.T.max(1)
        nrm = np.cross(self.T[:, 1] - self.T[:, 0], self.T[:, 2] - self.T[:, 0])
        ln = np.linalg.norm(nrm, axis=1)
        self.steep = (ln > 1e-12) & (np.abs(nrm[:, 1]) < 0.2 * np.maximum(ln, 1e-12))


def render_world(P):
    """world triangles (n,3,3) of every live non-shadow render submesh (placements through their matrices; a hidden placement sits far below)"""
    if hasattr(P, "R"):
        return P.R
    p = P.p
    owners = owners_of(P.insts)
    out = []
    for i, sm in enumerate(p.submeshes):
        if SHADOW.search(sm["name"]) or p.pos_stream(sm) is None or not sm["icount"]:
            continue
        L = le.submesh_tris(p, i)
        I = np.array(p.indices(sm), np.int64).reshape(-1, 3)
        L = L[I[:, 0] != I[:, 1]]
        if not len(L):
            continue
        for it in (owners.get(i) or [None]):
            W = L if it is None else (np.concatenate([L, np.ones(L.shape[:2] + (1,))], 2) @ it.M)[:, :, :3]
            if (W.reshape(-1, 3).max(0) - W.reshape(-1, 3).min(0)).max() > 400:
                continue
            out.append(W)
    P.R = np.concatenate(out)
    return P.R


def surface_points(T, step=0.15, cap=40):
    """points on the triangles T (n,3,3): barycentric grid, about every `step` m, at most cap x cap per triangle"""
    pts = []
    e = np.maximum(np.linalg.norm(T[:, 1] - T[:, 0], axis=1), np.linalg.norm(T[:, 2] - T[:, 0], axis=1))
    k = np.clip(np.ceil(e / step).astype(int), 1, cap)
    for kk in np.unique(k):
        m = k == kk
        A, B, C = T[m, 0], T[m, 1], T[m, 2]
        for i in range(kk + 1):
            for j in range(kk + 1 - i):
                u, v = i / kk, j / kk
                pts.append(A + (B - A) * u + (C - A) * v)
    return np.concatenate(pts)


def tri_dist(p, T):
    """exact distance from point p (3,) to each triangle of T (n,3,3) (closest point on triangle, Ericson 5.1.5)"""
    a, b, c = T[:, 0], T[:, 1], T[:, 2]
    ab, ac, ap = b - a, c - a, p - a
    d1, d2 = (ab * ap).sum(1), (ac * ap).sum(1)
    bp = p - b
    d3, d4 = (ab * bp).sum(1), (ac * bp).sum(1)
    cp = p - c
    d5, d6 = (ab * cp).sum(1), (ac * cp).sum(1)
    va, vb, vc = d3 * d6 - d5 * d4, d5 * d2 - d1 * d6, d1 * d4 - d3 * d2
    den = va + vb + vc
    den = np.where(np.abs(den) > 1e-30, den, 1e-30)
    v, w = vb / den, vc / den
    q = a + ab * v[:, None] + ac * w[:, None]                    # interior projection
    def edge(o, e, t):
        return o + e * np.clip(t, 0, 1)[:, None]
    e_ab = edge(a, ab, d1 / np.where(np.abs(d1 - d3) > 1e-30, d1 - d3, 1e-30))
    e_ac = edge(a, ac, d2 / np.where(np.abs(d2 - d6) > 1e-30, d2 - d6, 1e-30))
    bc = c - b
    e_bc = edge(b, bc, ((d4 - d3) / np.where(np.abs((d4 - d3) + (d5 - d6)) > 1e-30, (d4 - d3) + (d5 - d6), 1e-30)))
    inside = (va >= 0) & (vb >= 0) & (vc >= 0)
    best = np.where(inside, np.linalg.norm(q - p, axis=1), np.inf)
    for e in (e_ab, e_ac, e_bc):                                  # the nearest point on the 3 edges (points of the triangle: never below the true distance)
        best = np.minimum(best, np.linalg.norm(e - p, axis=1))
    return best


def orphans(P, lo, hi, near=0.5, step=None):
    """mask over P's proxy triangles: CENTROID inside [lo, hi] and no visible render surface within `near` m of it (exact point-triangle distance):
    a ghost, the thing it shadowed is gone.  Sun came through the Supermarket ceiling because the old test (triangle merely meets the box, render
    surface sampled at most 40 x 40 points per triangle) cut real casters of standing walls - the walls-grouped proxy's east wall / z wall / x -509
    wall faces and SP's only back-room roof cap (all far bigger than the removal / snow boxes they touch, their 58 m render walls sampled 1.4 m apart).
    A removed prop's own proxy lies inside its box, so the centroid rule keeps every real ghost."""
    meet = (P.hi >= lo).all(1) & (P.lo <= hi).all(1)
    if not meet.any():
        return meet
    R = render_world(P)
    if not hasattr(P, "_rbox"):                                 # per-pak caches: the sweep calls this once per edit box (night52: ~1 h on min/max alone)
        P._rbox = (R.min(1), R.max(1))
        P._cent = P.T.mean(1)
    cen = P._cent
    cand = meet & (cen >= lo).all(1) & (cen <= hi).all(1)
    out = np.zeros(len(meet), bool)
    if not cand.any():
        return out
    from scipy.spatial import cKDTree
    rl, rh = P._rbox
    sel = (rh >= lo - near - 1).all(1) & (rl <= hi + near + 1).all(1)
    if not sel.any():
        out[cand] = True
        return out
    Rs, sl, sh = R[sel], rl[sel], rh[sel]
    idx = np.nonzero(cand)[0]
    d, _ = cKDTree(surface_points(Rs, step or 0.15)).query(cen[idx], distance_upper_bound=near)
    for k in idx[~np.isfinite(d)]:                              # samples are ON render surfaces: a hit is proof; a miss gets the exact test
        c = cen[k]
        m = (sh >= c - near).all(1) & (sl <= c + near).all(1)
        out[k] = not m.any() or tri_dist(c, Rs[m]).min() > near
    return out


def region(g):
    b = np.array(g["box"], float)
    if g["kind"] == "morph":
        r = float(g.get("collision_radius", RADIUS)) if min(b[3] - b[0], b[5] - b[2]) >= 0.5 else 0.05
        return b[:3] - [r, 0.05, r], b[3:] + [r, 0.05, r]
    return b[:3] - 0.05, b[3:] + 0.05


def audit_edit(P, g, skip=()):
    lo, hi = region(g)
    meet = (P.hi >= lo).all(1) & (P.lo <= hi).all(1) & ~np.isin(P.own, list(skip))
    inside = meet & (P.lo >= lo).all(1) & (P.hi <= hi).all(1)
    r = {}
    for nm, m in (("inside", inside), ("partly", meet & ~inside)):
        r[nm] = (int((m & ~P.shared).sum()), int((m & P.shared).sum()))
    if g["kind"] == "morph" and g.get("op") == "flatten":
        ab = meet & ~P.steep & (P.hi[:, 1] > float(g["y"]) + 0.05)
        r["above"] = (int((ab & ~P.shared).sum()), int((ab & P.shared).sum()))
        r["_above_mask"] = ab
    r["_mask"] = meet
    orp = orphans(P, lo, hi)
    r["orphan"] = (int((orp & ~P.shared).sum()), int((orp & P.shared).sum()))
    r["_orphan_mask"] = orp
    r["subs"] = sorted({(int(s), bool(sh)) for s, sh in zip(P.sub[meet], P.shared[meet])})
    return r


def run(key, d):
    edits = [g for g in geoedit.load(key) if g.get("active", True)]
    res = []
    cache = {}
    for g in edits:
        if g["kind"] not in ("morph", "instance", "tris", "detach"):
            continue
        lv = g["level"]
        if lv not in cache:
            f = os.path.join(d, lv + ".pak")
            if not os.path.exists(f):                                   # levels without a morph edit: the plain edited pak one directory up
                f = os.path.join(os.path.dirname(d.rstrip("/\\")), lv + ".pak") if os.path.basename(d.rstrip("/\\")) == "morph" else f
            cache[lv] = Proxy(f)
        P = cache[lv]
        skip = [int(g["record"], 16)] if g.get("record") else []
        res.append((g, audit_edit(P, g, skip)))
    return res, cache


def fmt(r, k):
    u, s = r.get(k, (0, 0))
    return "%d/%d" % (u, s)

def sweep(written, edits, log=print, fix=True):
    """Build-time ghost-proxy sweep (dark patches on walls / snow / floor = shadows of things that are gone).
    For every written render pak and every removal / morph / detach box of the map (any level: the boxes are world coordinates, a neighbour level can
    hold the removed prop's shadow proxy): cut every UNIQUE shadow-proxy triangle whose centroid lies in the box (region(); restore boxes skipped, shadow_caps donors
    kept) and has no visible render surface within 0.5 m of its centroid (orphans(): the thing it shadowed is gone - a proxy whose prop still stands, e.g. the electrical-meter set inside the pat-walls
    box, is a live shadow caster and stays).  Idempotent (cut triangles are degenerate = not live).  Afterwards the audit is run again and the build
    FAILS if any orphan proxy triangle is left.  fix=False only audits.  -> {pak: cut}; env T2R_NO_PROXY_SWEEP=1 skips (offline experiments)."""
    if os.environ.get("T2R_NO_PROXY_SWEEP"):
        return {}
    boxes = []
    for e in edits:
        if e.get("action") not in ("remove", "morph", "detach") or not e.get("box"):
            continue
        g = e.get("geo") or {"kind": "instance", "box": e["box"]}
        if g.get("kind") == "restore":                              # puts a wall BACK (geoedits-restore.json): nothing is gone there (its box cut SP's back-room roof cap)
            continue
        if g.get("kind") not in ("morph", "instance", "tris", "detach"):
            g = dict(g, kind="instance")
        boxes.append((e.get("name", "?"), g))
    out = {}
    todo = [f for f in written if not (f.endswith("-phys.pak") or not f.endswith(".pak") or not boxes)]
    # the paks are independent (own file, read-only boxes): one child interpreter each (parjobs.py; T2R_PAR_JOBS=1 = serial); log lines replayed in order
    import parjobs
    res = parjobs.run([("ghost_shadow_audit", "sweep_pak", (f, boxes, fix), {}) for f in todo], log=log)
    for f, (n, lines) in zip(todo, res):
        for ln in lines:
            log(ln)
        out[f] = n
        log("ghost shadow proxy sweep %s: %d cut" % (os.path.basename(f), n))
    return out


def sweep_pak(f, boxes, fix=True):
    """one pak of sweep() -> (cut triangles, [log lines])"""
    lines = []
    log = lines.append
    if True:
        P = Proxy(f)
        mask = np.zeros(len(P.T), bool)
        who = {}
        for nm, g in boxes:
            lo, hi = region(g)
            orp = orphans(P, lo, hi) & ~P.shared
            for k in np.nonzero(orp & ~mask)[0]:
                who[int(k)] = nm
            mask |= orp
        import shadow_caps                                              # roof shadow caps (shadow_caps.py) are built casters, never ghosts
        for si, tris in shadow_caps.protected(f, P.p).items():
            mask &= ~((P.sub == si) & np.isin(P.tri, list(tris)))
        n = int(mask.sum())
        per = {}
        for k in np.nonzero(mask)[0]:
            per[who[int(k)]] = per.get(who[int(k)], 0) + 1
        for nm, c in sorted(per.items()):
            log("  ghost shadow proxy: %s: %d orphan proxy triangle(s) %s" % (nm, c, "cut" if fix else "found"))
        if n and fix:
            buf = bytearray(P.p.d)
            for si in np.unique(P.sub[mask]):
                le.cut_triangles(buf, P.p, int(si), P.tri[mask & (P.sub == si)])
            with open(f, "wb") as fh:
                fh.write(buf)
            P = Proxy(f)                                                  # re-audit the written pak
            left = 0
            prot = shadow_caps.protected(f, P.p)
            keep = np.zeros(len(P.T), bool)
            for si, tris in prot.items():
                keep |= (P.sub == si) & np.isin(P.tri, list(tris))
            for nm, g in boxes:
                lo, hi = region(g)
                left += int((orphans(P, lo, hi) & ~P.shared & ~keep).sum())
            if left:
                raise SystemExit("ghost shadow proxy sweep: %d orphan proxy triangles still live in %s" % (left, f))
    return n, lines


def sweep_to(written, edits, out_dir, log=print):
    """Like sweep(fix=True) but NEVER edits an input pak: a pak with orphan proxy triangles is written, cut, to <out_dir>/swept/<name> and that path replaces the
    input in the returned list (paks without orphans stay as they are).  The earlier in-place sweep changed the cached morph outputs behind the stamps of the
    later stages (the collision pass keys on the render paks), so a second build recomputed them from different inputs than the first.  The result per input pak
    is remembered (<out>.sig = hash of the pak, the boxes and this code): an unchanged pak is neither audited nor cut again.  -> new list of paths"""
    if os.environ.get("T2R_NO_PROXY_SWEEP"):
        return list(written)
    boxes = []
    for e in edits:
        if e.get("action") not in ("remove", "morph", "detach") or not e.get("box"):
            continue
        g = e.get("geo") or {"kind": "instance", "box": e["box"]}
        if g.get("kind") not in ("morph", "instance", "tris", "detach"):
            g = dict(g, kind="instance")
        boxes.append((e.get("name", "?"), g))
    sdir = os.path.join(out_dir, "swept")
    todo = [f for f in written if not (f.endswith("-phys.pak") or not f.endswith(".pak") or not boxes)]
    import parjobs
    res = parjobs.run([("ghost_shadow_audit", "sweep_pak_to", (f, boxes, os.path.join(sdir, os.path.basename(f))), {}) for f in todo], log=log)
    new = {}
    for f, (n, lines, path) in zip(todo, res):
        for ln in lines:
            log(ln)
        log("ghost shadow proxy sweep %s: %d cut" % (os.path.basename(f), n))
        new[f] = path
    return [new.get(f, f) for f in written]


def sweep_pak_to(f, boxes, dst):
    """one pak of sweep_to -> (cut triangles, [log lines], path of the pak to use)"""
    import hashlib
    h = hashlib.sha1()
    with open(f, "rb") as fh:
        for b in iter(lambda: fh.read(1 << 22), b""):
            h.update(b)
    h.update(json.dumps(boxes, sort_keys=True, default=str).encode())
    h.update(open(__file__.replace(".pyc", ".py"), "rb").read())
    h.update(open(os.path.join(HERE, "level_edit.py"), "rb").read())
    key = h.hexdigest()
    sig = dst + ".sig"
    if not os.environ.get("T2R_NO_BUILD_CACHE") and os.path.exists(sig):
        try:
            m = json.load(open(sig))
            if m["key"] == key and (not m["n"] or os.path.exists(dst)):
                return m["n"], m["lines"], dst if m["n"] else f
        except (OSError, ValueError, KeyError):
            pass
    lines = []
    log = lines.append
    P = Proxy(f)
    mask = np.zeros(len(P.T), bool)
    who = {}
    for nm, g in boxes:
        lo, hi = region(g)
        orp = orphans(P, lo, hi) & ~P.shared
        for k in np.nonzero(orp & ~mask)[0]:
            who[int(k)] = nm
        mask |= orp
    n = int(mask.sum())
    per = {}
    for k in np.nonzero(mask)[0]:
        per[who[int(k)]] = per.get(who[int(k)], 0) + 1
    for nm, c in sorted(per.items()):
        log("  ghost shadow proxy: %s: %d orphan proxy triangle(s) cut" % (nm, c))
    if os.path.exists(dst):
        os.remove(dst)
    if n:
        buf = bytearray(P.p.d)
        for si in np.unique(P.sub[mask]):
            le.cut_triangles(buf, P.p, int(si), P.tri[mask & (P.sub == si)])
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        with open(dst, "wb") as fh:
            fh.write(buf)
        P = Proxy(dst)                                                  # re-audit the written pak
        left = 0
        for nm, g in boxes:
            lo, hi = region(g)
            left += int((orphans(P, lo, hi) & ~P.shared).sum())
        if left:
            os.remove(dst)
            raise SystemExit("ghost shadow proxy sweep: %d orphan proxy triangles still live in %s" % (left, f))
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    json.dump({"key": key, "n": n, "lines": lines}, open(sig, "w"))
    return n, lines, dst if n else f


def main(argv):
    key, d = argv[0], argv[1]
    if argv[0] == "sweep":                                           # python ghost_shadow_audit.py sweep <key> <dir-with-paks> [--fix]
        import level_edit
        fs = [os.path.join(argv[2], n) for n in os.listdir(argv[2]) if n.endswith(".pak") and not n.endswith("-phys.pak")]
        sweep(fs, [le_e for le_e in __import__("geoedit").edits_for(argv[1]) if le_e.get("action") != "colledit"], fix="--fix" in argv)
        return
    res, _ = run(key, d)
    print("%-62s %-26s %9s %9s %9s %9s  (unique/shared live proxy triangles)" % ("edit", "level", "inside", "partly", "above", "orphan"))
    tot = np.zeros(8, int)
    for g, r in res:
        tot += [*r["inside"], *r["partly"], *r.get("above", (0, 0)), *r["orphan"]]
        if not any(r[k][0] + r[k][1] for k in ("inside", "partly", "above", "orphan") if k in r):
            continue
        print("%-62s %-26s %9s %9s %9s %9s" % (g["name"][:62], g["level"][4:], fmt(r, "inside"), fmt(r, "partly"), fmt(r, "above"), fmt(r, "orphan")))
    print("TOTAL inside %d/%d partly %d/%d above %d/%d orphan %d/%d over %d edits" % (*tot, len(res)))


if __name__ == "__main__":
    main(sys.argv[1:])
