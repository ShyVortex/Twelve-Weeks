"""Intersect camera rays (the in-game ray presses) with the shipped render geometry of a map's levels.  Offline, CPU only.

  python darkfix_ray.py <out dir> [--src <stock src dir>] [--ray cx cy cz dx dy dz ...] [--box x0 y0 z0 x1 y1 z1]

Per ray: the nearest hits (level, submesh index + name, triangle, world point, distance, owner instance), drawn submeshes and
shadow proxies listed apart.  The shipped pak per level = <out>/morph/<level>.pak, else <out>/<level>.pak, else the stock one."""
import os
import struct
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "models"))
import level_edit as le  # noqa: E402
import ndpak  # noqa: E402

LEVELS = ["pat-jackson-supermarket", "pat-jackson-supermarket-int", "pat-jackson-alley", "pat-jackson-alley-detail", "pat-jackson-wide",
          "pat-jackson-library-path", "pat-jackson-library-path-low"]


def shipped(out, src, lv):
    for p in (os.path.join(out, "morph", lv + ".pak"), os.path.join(out, lv + ".pak"), os.path.join(src, lv + ".pak")):
        if os.path.exists(p):
            return p


def level_tris(p, box):
    """[(sub index, owner record offset or -1, tri ids, (n,3,3) world tris)] of every submesh / instance meeting box"""
    lo, hi = np.array(box[:3]), np.array(box[3:])
    insts = le.find_instances(p)
    inst_sub = {i for it in insts for _, ids in it.names for i in ids} | {i for it in insts for i in it.subs}
    out = []
    for i, sm in enumerate(p.submeshes):
        if i in inst_sub or not sm["vcount"]:
            continue
        o = sm["offset"]
        a, b = np.array(struct.unpack_from("<3f", p.d, o)), np.array(struct.unpack_from("<3f", p.d, o + 16))
        if (b < lo).any() or (a > hi).any() or (b - a).max() > 400:
            continue
        T = le.submesh_tris(p, i)
        if len(T):
            out.append((i, -1, np.arange(len(T)), T))
    for it in insts:
        if (it.whi < lo).any() or (it.wlo > hi).any():
            continue
        ids = sorted({i for _, s in it.names for i in s} or set(it.subs))
        for i in ids:
            T = le.submesh_tris(p, i)
            if len(T):
                T4 = np.concatenate([T, np.ones(T.shape[:2] + (1,))], 2) @ it.M
                out.append((i, it.pak_off, np.arange(len(T)), T4[:, :, :3]))
    return out


def ray_tris(o, d, T, eps=1e-9):
    """Moller-Trumbore, vectorised -> (t, u, v) arrays (t = inf for a miss)"""
    e1, e2 = T[:, 1] - T[:, 0], T[:, 2] - T[:, 0]
    pv = np.cross(d, e2)
    det = (e1 * pv).sum(1)
    ok = np.abs(det) > eps
    inv = np.where(ok, 1.0 / np.where(ok, det, 1), 0)
    tv = o - T[:, 0]
    u = (tv * pv).sum(1) * inv
    qv = np.cross(tv, e1)
    v = (qv * d).sum(1) * inv
    t = (e2 * qv).sum(1) * inv
    hit = ok & (u >= 0) & (v >= 0) & (u + v <= 1) & (t > 1e-4)
    return np.where(hit, t, np.inf), u, v


def cast(geo, o, d, k=6):
    hits = []
    for lv, p, items in geo:
        for i, rec, ids, T in items:
            t, u, v = ray_tris(o, d, T)
            for j in np.nonzero(np.isfinite(t))[0]:
                hits.append((t[j], lv, i, rec, int(ids[j]), u[j], v[j], p))
    hits.sort(key=lambda h: h[0])
    return hits[:k]


def main(argv):
    out = argv[0]
    src = argv[argv.index("--src") + 1] if "--src" in argv else os.path.join(out, "..", "..", "src")
    box = [float(x) for x in argv[argv.index("--box") + 1:argv.index("--box") + 7]] if "--box" in argv else [-545, 5, 265, -480, 40, 315]
    rays = []
    if "--ray" in argv:
        a = argv[argv.index("--ray") + 1:]
        while len(a) >= 6 and all(x.lstrip("-").replace(".", "").isdigit() for x in a[:6]):
            rays.append([float(x) for x in a[:6]])
            a = a[6:]
    geo = []
    for lv in LEVELS:
        pth = shipped(out, src, lv)
        if not pth:
            continue
        p = ndpak.Pak(pth)
        geo.append((lv, p, level_tris(p, box)))
    for n, r in enumerate(rays):
        o, d = np.array(r[:3]), np.array(r[3:]) / np.linalg.norm(r[3:])
        print("ray %d  o %s  d %s" % (n + 1, r[:3], r[3:]))
        for t, lv, i, rec, j, u, v, p in cast(geo, o, d):
            pt = o + d * t
            nm = p.submeshes[i]["name"]
            print("   t %6.2f  %-28s s%-5d tri %-6d rec %-9s  p (%.2f %.2f %.2f)  %s" % (
                t, lv, i, j, hex(rec) if rec >= 0 else "world", pt[0], pt[1], pt[2], nm[-80:]))


if __name__ == "__main__":
    main(sys.argv[1:])
