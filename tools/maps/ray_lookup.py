"""Resolve the points of the in-game ray diagnostic (Pause/Break in a dev build, t2r-ext.c rayd_*) against the level data.  Offline, CPU only.

  python ray_lookup.py <t2r-ext.log | t2r-ray.jsonl> [--id K] [--key jackson-market] [--out DIR] [--radius 0.5]
  python ray_lookup.py --point -508 18.2 287 [--point x y z ...] [--key jackson-market]     # a synthetic point instead of a log
  python ray_lookup.py --cast x y z dx dy dz [--maxd 10] [--key jackson-market] [--out DIR]  # offline raycast against the shipped collision:
        the first triangles the ray crosses within --maxd (item / section / source STOCK|OURS / render surface near the hit = visible or not),
        plus the colliders in the walking band (0.3-1.8 m above the floor the ray ends over) -- a hit with no render surface = leftover collision

Input: lines `{"type":"hit","id":K,"p":[x,y,z],"chain":"w207",...}` (t2r-ray.jsonl, or the same text after `rayjson ` in the log).  --id picks one
press (default: the newest).  The key defaults to the press's map name when it matches a sp_maps.json key, else jackson-market.

Per hit point (probe chains b0..b15 and the three cast chains that end on the same point are merged) it prints:
  COLLISION  the Havok triangles within --radius of the point in the SHIPPED -phys.pak of every level of the map (<out>/<level>-phys.pak, default the
             newest pipeline output: the latest build / this tree's re/maps/level-edit-cache/out/<key>): level, item, shape key, material tag, distance,
             where it comes from (STOCK = also in the unedited SP pak; OURS = colledits.json #i / colledits-auto.json #i / geoedit morph),
             and whether a render surface lies within 0.35 m of it (none = INVISIBLE collision: the invisible fence/wall case).
  RENDER     level pak instances (placement records) and merged submeshes within --radius: asset (art group), record offset, submesh name; the
             geoedit entries whose box holds the point (file + index in the user's editor json).
  NEAR       spawners / item spots / lockboxes / satchels / medkits / spawn points of data/<key>-*.json within 1 m.
  VERDICT    REMOVED-BUT-DRAWN when a drawn piece belongs to an art group that has other parts removed by an active geoedit nearby (the floating
             jug), with the instance removal to add; and for invisible collision the colledit "delete" triangle to add.
The ray's own result is only the hit fraction (wait-raycast-t): normals / bodies / shape keys come from this lookup, not from the game.
"""
import argparse
import warnings
import glob
import json
import os
import re
import sys
import tempfile

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "models"))
sys.path.insert(0, os.path.join(HERE, "..", "part1"))
warnings.simplefilter("ignore")
import level_edit as le  # noqa: E402
import ndpak  # noqa: E402

DATA = os.path.join(HERE, "data")
REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
CACHE = os.path.join(tempfile.gettempdir(), "ray_lookup_cache")


# ------------------------------------------------------------------ input
def read_records(path):
    recs = []
    for line in open(path, encoding="utf-8", errors="replace"):
        i = line.find("rayjson ")
        s = line[i + 8:] if i >= 0 else line
        s = s.strip()
        if not s.startswith("{"):
            continue
        try:
            recs.append(json.loads(s))
        except ValueError:
            pass
    return recs


def group_points(hits):
    """merge hits closer than 2 cm: [(point, [descriptions])]"""
    out = []
    for h in sorted(hits, key=lambda h: h.get("dist", 0)):
        p = np.array(h["p"], float)
        d = f'{h["chain"]}#{h.get("i", 0)} {h.get("dist", 0):.2f}m mask {h.get("mask", 0):#x}'
        for q in out:
            if np.abs(q[0] - p).max() < 0.02:
                q[1].append(d)
                break
        else:
            out.append((p, [d], h.get("near", [])))
    return out


# ------------------------------------------------------------------ geometry
def ptri_dist(p, T):
    """distance from point p to each triangle of T (n,3,3) (Ericson, closest point on triangle)"""
    a, b, c = T[:, 0], T[:, 1], T[:, 2]
    ab, ac, ap = b - a, c - a, p - a
    d1, d2 = (ab * ap).sum(1), (ac * ap).sum(1)
    bp = p - b
    d3, d4 = (ab * bp).sum(1), (ac * bp).sum(1)
    cp = p - c
    d5, d6 = (ab * cp).sum(1), (ac * cp).sum(1)
    vc = d1 * d4 - d3 * d2
    vb = d5 * d2 - d1 * d6
    va = d3 * d6 - d5 * d4
    with np.errstate(all="ignore"):
        den = va + vb + vc
        v = np.where(den != 0, vb / den, 0)
        w = np.where(den != 0, vc / den, 0)
        q = a + ab * v[:, None] + ac * w[:, None]
        # edge / vertex regions
        t_ab = np.clip(d1 / (d1 - d3), 0, 1)
        t_ac = np.clip(d2 / (d2 - d6), 0, 1)
        t_bc = np.clip((d4 - d3) / ((d4 - d3) + (d5 - d6)), 0, 1)
    q = np.where(((vc <= 0) & (d1 >= 0) & (d3 <= 0))[:, None], a + ab * t_ab[:, None], q)
    q = np.where(((vb <= 0) & (d2 >= 0) & (d6 <= 0))[:, None], a + ac * t_ac[:, None], q)
    q = np.where(((va <= 0) & ((d4 - d3) >= 0) & ((d5 - d6) >= 0))[:, None], b + (c - b) * t_bc[:, None], q)
    q = np.where(((d1 <= 0) & (d2 <= 0))[:, None], a, q)
    q = np.where(((d3 >= 0) & (d4 <= d3))[:, None], b, q)
    q = np.where(((d6 >= 0) & (d5 <= d6))[:, None], c, q)
    return np.linalg.norm(q - p, axis=1)


def tri_area(T):
    return 0.5 * np.linalg.norm(np.cross(T[:, 1] - T[:, 0], T[:, 2] - T[:, 0]), axis=1)


def tri_key(t):
    return tuple(sorted(tuple(int(round(float(x) * 500)) for x in v) for v in t))     # 2 mm grid


# ------------------------------------------------------------------ data sources
def find_out_dir(key, given=None):
    if given:
        return given
    cands = [os.path.join(r, "re", "maps", "level-edit-cache", "out", key) for r in [REPO] + glob.glob(os.path.join(os.environ.get("T2R_WT", os.path.join(os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")), "..", "t2r-wt")), "*"))]
    cands = [c for c in cands if glob.glob(os.path.join(c, "colledit", "*-phys.pak")) or glob.glob(os.path.join(c, "*-phys.pak"))]
    if not cands:
        sys.exit("no pipeline output dir for " + key + " (use --out)")
    return max(cands, key=lambda c: max((os.path.getmtime(f) for f in glob.glob(os.path.join(c, "*-phys.pak")) + glob.glob(os.path.join(c, "colledit", "*-phys.pak"))), default=0))


def src_dir(out):
    base = os.path.dirname(os.path.dirname(out))
    d = os.path.join(base, "src")
    return d if os.path.isdir(d) else os.path.join(REPO, "re", "maps", "level-edit-cache", "src")


def level_paths(key, out):
    """[(level, shipped phys, stock phys, shipped render pak)] for the levels the map loads that have a pak in `out`"""
    res = []
    lv = le.map_levels(key)
    # the pipeline also writes supermarket-int / alley etc. that sp_maps lists; keep every level with a shipped phys
    for l in lv:
        ph = os.path.join(out, "colledit", l + "-phys.pak")      # the SHIPPED collision = the colledit stage's output (the top-level -phys.pak is the stage before the colledits)
        if not os.path.exists(ph):
            ph = os.path.join(out, l + "-phys.pak")
        if not os.path.exists(ph):
            continue
        res.append((l, ph, os.path.join(src_dir(out), l + "-phys.pak"), (os.path.join(out, "morph", l + ".pak") if os.path.exists(os.path.join(out, "morph", l + ".pak")) else os.path.join(out, l + ".pak"))))
    return res


def phys_tris(path):
    """(keys, T, tags, item index) of every collision triangle of a -phys.pak, cached as npz"""
    os.makedirs(CACHE, exist_ok=True)
    cf = os.path.join(CACHE, re.sub(r"[^A-Za-z0-9]+", "_", os.path.abspath(path)) + f"_{int(os.path.getmtime(path))}.npz")
    if os.path.exists(cf):
        z = np.load(cf)
        return z["k"], z["T"], z["g"], z["i"]
    K, T, G, I = [], [], [], []
    for n, it in enumerate(le.phys_items(path)[1]):
        k, t, g = le.hc.triangles(it.mesh)
        if len(t):
            K.append(k); T.append(t); G.append(g); I.append(np.full(len(k), n))
    r = (np.concatenate(K), np.concatenate(T), np.concatenate(G), np.concatenate(I)) if K else (np.zeros(0, np.int64), np.zeros((0, 3, 3)), np.zeros(0, np.int64), np.zeros(0, np.int64))
    np.savez(cf, k=r[0], T=r[1], g=r[2], i=r[3])
    return r


def load_json(path):
    return json.load(open(path, encoding="utf-8")) if os.path.exists(path) else {}


def spec_files(key, kind):
    """[(label, edits list)] for <key>-<kind>.json, -auto, -restore (indices = the position in the file's own "edits")"""
    out = []
    for suf in ("", "-auto", "-restore"):
        p = os.path.join(DATA, f"{key}-{kind}{suf}.json")
        if os.path.exists(p):
            out.append((os.path.basename(p), load_json(p).get("edits", [])))
    return out


def in_box(p, box, pad=0.0):
    b = np.array(box, float)
    return (p >= b[:3] - pad).all() and (p <= b[3:] + pad).all()


def attribute_ours(centroid, tri, key, level=None):
    """which colledit spec made a collision triangle that is not in the stock pak"""
    c = np.asarray(centroid)
    hits = []
    for fn, edits in spec_files(key, "colledits"):
        for i, e in enumerate(edits):
            if not e.get("active", True) or (level and e.get("level") != level):
                continue
            k = e.get("kind")
            if k == "verts":
                tos = np.array([m["to"] for m in e["moves"]], float)
                if any((np.abs(tos - v).max(1) < 2e-3).any() for v in tri):
                    hits.append(f"{fn}#{i} '{e['name']}' (vertex move)")
            elif k in ("box", "quad"):
                pts = np.array(e["points"], float) if k == "quad" else None
                if k == "box":
                    ctr, sz = np.array(e["center"], float), np.array(e["size"], float)
                    ok = np.abs(c - ctr).max() <= sz.max() * 0.75 + 0.1
                else:
                    ok = (c >= pts.min(0) - 0.1).all() and (c <= pts.max(0) + 0.1).all()
                if ok:
                    hits.append(f"{fn}#{i} '{e['name']}' ({k})")
            elif k == "ground":
                r = e["rect"]
                if r[0] <= c[0] <= r[2] and r[1] <= c[2] <= r[3]:
                    hits.append(f"{fn}#{i} '{e['name']}' (ground grid)")
    for fn, edits in spec_files(key, "geoedits"):
        for i, e in enumerate(edits):
            if e.get("kind") in ("morph", "detach", "restore") and e.get("active", True) and e.get("box") and (not level or e.get("level") == level) and in_box(c, e["box"], 0.3):
                hits.append(f"{fn}#{i} '{e.get('name')}' ({e['kind']})")
    return hits


# ------------------------------------------------------------------ render
_render_cache = {}


def render_pieces(path):
    """(Pak, instances, instance submesh ids) of a level pak, cached"""
    if path not in _render_cache:
        p = ndpak.Pak(path)
        insts = le.find_instances(p)
        _render_cache[path] = (p, insts, {i for it in insts for _, ids in it.names for i in ids})
    return _render_cache[path]


def render_near(path, P, r):
    """pieces within r of P: dicts (kind inst|sub, asset, name, off, dist, tris)"""
    p, insts, inst_sub = render_pieces(path)
    out = []
    lo, hi = P - r - 0.2, P + r + 0.2
    for it in insts:
        if (it.whi < lo).any() or (it.wlo > hi).any():
            continue
        for g, ids in it.names:
            Ts = []
            for i in ids:
                T = le.submesh_tris(p, i)
                if len(T):
                    Ts.append((np.concatenate([T, np.ones(T.shape[:2] + (1,))], 2) @ it.M)[:, :, :3])
            if not Ts:
                continue
            T = np.concatenate(Ts)
            T = T[tri_area(T) > 1e-7]
            if not len(T):
                continue
            d = ptri_dist(P, T)
            if d.min() <= r:
                out.append(dict(kind="inst", asset=g, name=p.submeshes[ids[0]]["name"], off=it.pak_off, dist=float(d.min()), tris=T, proto=it.proto))
    import struct
    for i, sm in enumerate(p.submeshes):
        if i in inst_sub:
            continue
        o = sm["offset"]
        a, b = np.array(struct.unpack_from("<3f", p.d, o)), np.array(struct.unpack_from("<3f", p.d, o + 16))
        if (b < lo).any() or (a > hi).any() or (b - a).max() > 400:
            continue
        T = le.submesh_tris(p, i)
        T = T[tri_area(T) > 1e-7] if len(T) else T
        if not len(T):
            continue
        d = ptri_dist(P, T)
        if d.min() <= r:
            out.append(dict(kind="sub", asset=sm["name"].split("|")[0], name=sm["name"], off=i, dist=float(d.min()), tris=T[d <= r + 1.0], proto=""))
    return out


def geo_hits(key, P, piece=None):
    """geoedit entries (file, index, entry) whose box holds P (0.5 m pad) or whose record is `piece`'s placement"""
    out = []
    for fn, edits in spec_files(key, "geoedits"):
        for i, e in enumerate(edits):
            b = e.get("box")
            rec = e.get("record")
            by_rec = piece and piece["kind"] == "inst" and rec and int(rec, 16) == piece["off"]
            if by_rec or (b and len(b) == 6 and in_box(P, b, 0.5)):
                out.append((fn, i, e))
    return out


def removed_siblings(key, asset, P, within=14.0):
    """active removal entries of the same art group close to P: the other parts of the prop were removed"""
    out = []
    a = (asset or "").split("/")[-1]
    for fn, edits in spec_files(key, "geoedits"):
        for i, e in enumerate(edits):
            if e.get("kind") not in ("instance", "tris") or not e.get("active", True):
                continue
            ea = (e.get("asset") or "").split("/")[-1]
            if not ea or (ea != a and not a.startswith(ea) and not ea.startswith(a)):
                continue
            b = e.get("box")
            if b and len(b) == 6:
                c = np.array([(b[0] + b[3]) / 2, (b[1] + b[4]) / 2, (b[2] + b[5]) / 2])
                if np.linalg.norm(c - P) <= within + np.linalg.norm(np.array(b[3:]) - np.array(b[:3])) / 2:
                    out.append((fn, i, e))
    return out


def spawn_near(key, P, r=1.0):
    res = []

    def walk(o, label, fn):
        if isinstance(o, dict):
            pos = o.get("pos") or o.get("position") or o.get("center")
            if isinstance(pos, list) and len(pos) == 3 and all(isinstance(x, (int, float)) for x in pos):
                d = float(np.linalg.norm(np.array(pos, float) - P))
                if d <= r:
                    nm = o.get("name") or o.get("item") or o.get("room") or o.get("kind") or ""
                    items = ",".join(x.get("item", "?") for x in o.get("items", []) if isinstance(x, dict)) if isinstance(o.get("items"), list) else ""
                    res.append((d, f"{fn} {label} {nm} {items}".strip()))
            for k, v in o.items():
                walk(v, f"{label}/{k}", fn)
        elif isinstance(o, list):
            for j, v in enumerate(o):
                walk(v, f"{label}[{j}]", fn)
    for f in sorted(glob.glob(os.path.join(DATA, key + "-*.json"))):
        bn = os.path.basename(f)
        if any(s in bn for s in ("geoedits", "colledits", "spedits", "sealremove", "-pak.json")) and "pak.json" not in bn:
            continue
        walk(load_json(f), "", bn)
    return sorted(res)


# ------------------------------------------------------------------ offline cast
def seg_tri(o, d, maxd, T):
    """Moller-Trumbore, double sided: (t, idx) of every triangle of T (n,3,3) the ray o + t*d (|d|=1) crosses for 0 <= t <= maxd"""
    e1, e2 = T[:, 1] - T[:, 0], T[:, 2] - T[:, 0]
    pv = np.cross(d, e2)
    det = (e1 * pv).sum(1)
    with np.errstate(all="ignore"):
        inv = 1.0 / det
        tv = o - T[:, 0]
        u = (tv * pv).sum(1) * inv
        qv = np.cross(tv, e1)
        v = (qv * d).sum(1) * inv
        t = (e2 * qv).sum(1) * inv
    ok = (np.abs(det) > 1e-12) & (u >= -1e-6) & (v >= -1e-6) & (u + v <= 1 + 1e-6) & (t >= 0) & (t <= maxd)
    idx = np.nonzero(ok)[0]
    return t[idx], idx


def cast(o, d, key, out, maxd=10.0, quiet=False, levels_override=None):
    """first collision hits of the ray along the shipped paks; returns [(t, level, item, key, tag, tri)] sorted by t"""
    d = np.array(d, float)
    d = d / np.linalg.norm(d)
    o = np.array(o, float)
    hits = []
    for lv, ph, sph, rp in (levels_override or level_paths(key, out)):
        K, T, G, I = phys_tris(ph)
        if not len(T):
            continue
        end = o + d * maxd
        lo, hi = np.minimum(o, end) - 0.05, np.maximum(o, end) + 0.05
        sel = np.nonzero((T.max(1) >= lo).all(1) & (T.min(1) <= hi).all(1))[0]
        if not len(sel):
            continue
        t, ix = seg_tri(o, d, maxd, T[sel])
        for tt, j in zip(t, ix):
            g = sel[j]
            hits.append((float(tt), lv, int(I[g]), int(K[g]), int(G[g]), T[g], ph, sph, rp))
    hits.sort(key=lambda h: h[0])
    return hits


def cast_report(o, d, key, out, maxd, nmax=12):
    o = np.array(o, float)
    d = np.array(d, float) / np.linalg.norm(d)
    print(f"\n=== CAST from {o.round(3).tolist()} dir {d.round(4).tolist()} up to {maxd:g} m   key {key}  (out {out})")
    hits = cast(o, d, key, out, maxd)
    if not hits:
        print("  the ray crosses no collision triangle")
        return hits
    stock = {}
    all_rp = [x[3] for x in level_paths(key, out) if os.path.exists(x[3])]
    for h in hits[:nmax]:
        t, lv, item, k, tag, tri, ph, sph, rp = h
        if lv not in stock:
            stock[lv] = {tri_key(x) for x in phys_tris(sph)[1]} if os.path.exists(sph) else set()
        n = np.cross(tri[1] - tri[0], tri[2] - tri[0])
        ln = np.linalg.norm(n)
        n = n / ln if ln > 1e-9 else n
        P = o + d * t
        c = tri.mean(0)
        pcs = [x for r_ in all_rp for x in render_near(r_, P, 0.6)]      # the render of EVERY level of the map (a level's collision can be drawn by another level's pak)
        pcs = [x for x in pcs if not x["asset"].startswith("dcl-")]
        vis = min((x["dist"] for x in pcs), default=None)
        src = "STOCK" if tri_key(tri) in stock[lv] else "OURS " + ("; ".join(attribute_ours(c, tri, key, lv)) or "(edited vertices / morph)")
        print(f"  t {t:6.3f} m  y {P[1]:7.3f}  at ({P[0]:.3f} {P[1]:.3f} {P[2]:.3f})  {lv} item {item} key {k:#x} (section {k >> 8} prim {(k >> 1) & 0x7f}) tag {tag:#x}  n ({n[0]:+.2f} {n[1]:+.2f} {n[2]:+.2f})  {src}")
        print("        render within 0.6 m: " + (", ".join(f"{x['asset']}@{x['dist']:.2f}" for x in sorted(pcs, key=lambda x: x['dist'])[:4]) if pcs else "NONE -> INVISIBLE COLLISION"))
    return hits


# ------------------------------------------------------------------ main
def resolve(P, key, out, radius, info=()):
    print(f"\n=== point {P[0]:.3f} {P[1]:.3f} {P[2]:.3f}   key {key}")
    for d in info:
        print("   ray:", d)
    verdict = []
    levels = level_paths(key, out)
    # render near (all levels), needed for the invisible-collision test
    pieces = []
    for lv, ph, sph, rp in levels:
        if os.path.exists(rp):
            for pc in render_near(rp, P, max(radius, 1.5)):
                pc["level"] = lv
                pieces.append(pc)
    allr = np.concatenate([pc["tris"] for pc in pieces]) if pieces else np.zeros((0, 3, 3))

    print("COLLISION (shipped", out + "; levels " + ", ".join(l[0] for l in levels) + ")")
    nfound = 0
    for lv, ph, sph, rp in levels:
        K, T, G, I = phys_tris(ph)
        if not len(T):
            continue
        lo, hi = P - radius, P + radius
        sel = np.nonzero((T.max(1) >= lo).all(1) & (T.min(1) <= hi).all(1))[0]
        if not len(sel):
            continue
        d = ptri_dist(P, T[sel])
        order = sel[np.argsort(d)]
        d = np.sort(d)
        stock = set()
        if os.path.exists(sph):
            sk, sT, _, _ = phys_tris(sph)
            m = (sT.max(1) >= lo - 1).all(1) & (sT.min(1) <= hi + 1).all(1)
            stock = {tri_key(t) for t in sT[m]}
        for j, (ti, dist) in enumerate(zip(order, d)):
            if dist > radius or j >= 8:
                break
            t = T[ti]
            n = np.cross(t[1] - t[0], t[2] - t[0])
            ln = np.linalg.norm(n)
            if ln < 1e-9:
                continue
            n = n / ln
            c = t.mean(0)
            is_stock = tri_key(t) in stock
            src = "STOCK" if is_stock else "OURS " + ("; ".join(attribute_ours(c, t, key, lv)) or "(edited vertices / morph, no spec match)")
            vis = float(ptri_dist(c, allr).min()) if len(allr) else None
            invisible = vis is None or vis > 0.35
            nfound += 1
            print(f"  {lv} item {int(I[ti])} key {int(K[ti]):#x} (section {int(K[ti]) >> 8} prim {(int(K[ti]) >> 1) & 0x7f} half {int(K[ti]) & 1}) tag {int(G[ti]):#x}  d {dist:.3f} m  "
                  f"n ({n[0]:+.2f} {n[1]:+.2f} {n[2]:+.2f})  area {ln/2:.2f}  {src}")
            print(f"      verts {' '.join('(%.4f %.4f %.4f)' % tuple(v) for v in t)}")
            print(f"      render surface within {'?' if vis is None else '%.2f m' % vis}{'  -> INVISIBLE COLLISION' if invisible else ''}")
            if invisible and dist <= 0.15:
                verdict.append(f"colledit delete (level {lv}): tri [{' '.join('%.5f' % x for x in t.reshape(-1))}]  -> colledits.json edit {{kind: delete, level: {lv}, tris: [[...]]}}")
    if not nfound:
        print("  no collision triangle within %.2f m (a hit with no triangle: the point is off the shipped level paks, or --radius too small)" % radius)

    print("RENDER (shipped level paks)")
    if not pieces:
        print("  nothing drawn within %.2f m" % max(radius, 1.5))
    for pc in sorted(pieces, key=lambda x: x["dist"]):
        if pc["dist"] > radius or pc["asset"].startswith("dcl-"):     # decals (blood / dirt projections) overlap everything
            continue
        what = f"instance record {pc['off']:#x}" if pc["kind"] == "inst" else f"merged submesh #{pc['off']}"
        print(f"  {pc['level']}: {what}  art group {pc['asset']}  ({pc['name']})  d {pc['dist']:.3f} m" + (f"  proto {pc['proto']}" if pc["proto"] else ""))
        gh = geo_hits(key, P, pc)
        for fn, i, e in gh:
            print(f"      geoedit {fn} #{i} '{e.get('name')}' kind {e.get('kind')} active {e.get('active', True)} level {e.get('level')}")
        sib = removed_siblings(key, pc["asset"], P)
        if sib:
            names = ", ".join(f"{fn}#{i}" for fn, i, e in sib[:6])
            print(f"      REMOVED-BUT-DRAWN: {len(sib)} other part(s) of art group '{pc['asset']}' were removed nearby ({names}) but this piece is still drawn")
            if pc["kind"] == "inst":
                verdict.append(f"remove instance record {pc['off']:#x} ({pc['asset']}) in level {pc['level']}  (geoedit kind instance, level {pc['level']}, record \"{pc['off']:#x}\"); its siblings {names} are removed")
            else:
                verdict.append(f"remove submesh #{pc['off']} '{pc['name']}' in level {pc['level']} near this point (geoedit kind tris, asset {pc['asset']}, box around {P.round(2).tolist()}); siblings {names} are removed")
    held = geo_hits(key, P)
    if held:
        print("  geoedit entries whose box holds the point:")
        for fn, i, e in held[:10]:
            print(f"      {fn} #{i} '{e.get('name')}' kind {e.get('kind')} level {e.get('level')} active {e.get('active', True)}")
    ce = []
    for fn, edits in spec_files(key, "colledits"):
        for i, e in enumerate(edits):
            if not e.get("active", True):
                continue
            k = e.get("kind")
            pts = None
            if k == "delete":
                pts = np.array(e["tris"], float).reshape(-1, 3)
            elif k == "quad":
                pts = np.array(e["points"], float)
            elif k == "box":
                pts = np.array([e["center"]], float) + np.array([[-1, -1, -1], [1, 1, 1]]) * np.array(e["size"], float) / 2
            elif k in ("clear", "ground"):
                r = e.get("rect") or e.get("box")
                if r and r[0] <= P[0] <= r[2] and r[1] <= P[2] <= r[3]:
                    ce.append(f"{fn}#{i} '{e['name']}' ({k}, level {e['level']})")
                continue
            if pts is not None and len(pts) and (P >= pts.min(0) - 0.6).all() and (P <= pts.max(0) + 0.6).all():
                ce.append(f"{fn}#{i} '{e['name']}' ({k}, level {e['level']})")
    if ce:
        print("COLLEDIT entries touching the point:")
        for c in ce:
            print("   ", c)

    print("NEAR (1 m)")
    nr = spawn_near(key, P)
    for d, s in nr[:12]:
        print(f"  {d:.2f} m  {s}")
    if not nr:
        print("  none")
    print("VERDICT")
    for v in dict.fromkeys(verdict):
        print("  *", v)
    if not verdict:
        print("  nothing to fix found: collision there is stock/ours and has a render surface; check the colledit/geoedit entries listed above")


def main(argv):
    cast = None
    if "--cast" in argv:                        # argparse reads a negative number after --cast as an option: take the 6 values by hand
        i = argv.index("--cast")
        cast = [float(x) for x in argv[i + 1:i + 7]]
        argv = argv[:i] + argv[i + 7:]
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("input", nargs="?")
    ap.add_argument("--id", type=int)
    ap.add_argument("--key")
    ap.add_argument("--out")
    ap.add_argument("--radius", type=float, default=0.5)
    ap.add_argument("--point", nargs=3, type=float, action="append")
    ap.add_argument("--maxd", type=float, default=10.0)
    a = ap.parse_args(argv)
    if cast:
        key = a.key or "jackson-market"
        cast_report(cast[:3], cast[3:], key, find_out_dir(key, a.out), a.maxd)
        return 0
    pts = []
    key = a.key
    if a.point:
        pts = [(np.array(p, float), ["synthetic"], []) for p in a.point]
        key = key or "jackson-market"
    elif a.input:
        recs = read_records(a.input)
        ids = sorted({r["id"] for r in recs if "id" in r})
        if not ids:
            sys.exit("no rayjson records in " + a.input)
        k = a.id if a.id is not None else ids[-1]
        press = next((r for r in recs if r.get("type") == "press" and r["id"] == k), {})
        hits = [r for r in recs if r.get("type") == "hit" and r["id"] == k]
        mp = (press.get("map") or (hits[0].get("map") if hits else "") or "").lower()
        print(f"press id {k}: map '{mp}' cam {press.get('cam')} dir {press.get('dir')} player {press.get('player')}  {len(hits)} hits")
        if not key:
            keys = [m["key"] for m in json.load(open(os.path.join(HERE, "sp_maps.json"), encoding="utf-8"))["maps"]]
            norm = re.sub(r"[^a-z0-9]", "", mp)
            key = next((x for x in keys if re.sub(r"[^a-z0-9]", "", x) == norm), None) or next((x for x in keys if norm and norm in re.sub(r"[^a-z0-9]", "", x)), None) or "jackson-market"
        pts = group_points(hits)
    else:
        ap.print_help()
        return 2
    out = find_out_dir(key, a.out)
    for P, info, near in pts:
        resolve(P, key, out, a.radius, info + (["in-game nearest: " + ", ".join(near)] if near else []))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
