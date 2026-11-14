"""Pair each vehicle prefab (vehicle_prefabs.py) with the standalone actor that can stand in for it in a map pak.

The SP cars are baked into the level (render record + -phys triangles): copying such a record over a donor crashes the game
(re/maps/level-edit.md), so a NEW car in an MP map is an actor97 prop (SimpleObject spawner: render + its own collision).  The
actor is not the same model as the SP car (except the military trucks), so the traversal / cover records of the prefab are fitted to it:
the actor's render vertices are matched to the prefab's collision surface (4 headings x centre/bottom alignment, symmetric median chamfer)
and the prefab's records are scaled per axis onto the actor's box.

  python vehicle_pair.py [--prefabs DIR] [--work DIR] [--top 3]   # writes <prefabs>/pairing.json
Output per prefab: candidates [{actor, theta_deg, t (actor-local offset), scale (x,y,z), chamfer_m, size_actor}]; best first.
Convention (row vectors, Ry(d) = [[c,0,-s],[0,1,0],[s,0,c]]): car-frame point p -> actor-local point
    a = ((p - car_anchor) / scale_actor_to_car + actor_anchor) @ Ry(theta_deg)
(car_anchor / actor_anchor = centre-bottom of the box in the car frame / of the heading-rotated actor; scale_actor_to_car = prefab box / actor box).
"""
import argparse
import json
import math
import os
import re
import sys
import zlib

import numpy as np
from scipy.spatial import cKDTree

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.dirname(HERE)
ROOT = os.path.dirname(TOOLS)
sys.path.insert(0, HERE)
sys.path.insert(0, TOOLS)
sys.path.insert(0, os.path.join(TOOLS, "models"))
import ndpak  # noqa: E402
import dsar_list  # noqa: E402

GAME = os.environ.get("T2_GAME", "C:/Games/The Last of Us Part II Remastered")
BAD = re.compile(r"glass|mirror|door|hatch|windshield|kick|bush|handles|hood-edge|trigger|broken|blocker|slidingdoor|fence|boat|carriage|pushcart|elevator|net-")


def Ry(deg):
    c, s = math.cos(math.radians(deg)), math.sin(math.radians(deg))
    return np.array([[c, 0, -s], [0, 1, 0], [s, 0, c]])


def load_col(path):
    b = zlib.decompress(open(path, "rb").read())
    assert b[:4] == b"T2RC"
    nv, nt = np.frombuffer(b, "<u4", 2, 4)
    v = np.frombuffer(b, "<f4", nv * 3, 12).reshape(-1, 3).astype(float)
    idx = np.frombuffer(b, "<u4", nt * 3, 12 + nv * 12).reshape(-1, 3)
    return v[idx]


def sample_tris(T, n=5000, seed=1):
    rng = np.random.default_rng(seed)
    a = np.linalg.norm(np.cross(T[:, 1] - T[:, 0], T[:, 2] - T[:, 0]), axis=1) / 2
    if a.sum() <= 0:
        return T.reshape(-1, 3)
    i = rng.choice(len(T), n, p=a / a.sum())
    u, v = rng.random(n), rng.random(n)
    f = u + v > 1
    u[f], v[f] = 1 - u[f], 1 - v[f]
    return T[i, 0] + (T[i, 1] - T[i, 0]) * u[:, None] + (T[i, 2] - T[i, 0]) * v[:, None]


_rows = None


def actor_rows():
    global _rows
    if _rows is None:
        _rows = {}
        for l in open(os.path.join(ROOT, "re", "game-files.tsv"), encoding="utf-8", errors="replace"):
            a, p, s = l.rstrip("\n").split("\t")[:3]
            if p.startswith("actor97/") and p.endswith(".pak"):
                _rows[p[8:-4]] = (a, p)
    return _rows


def actor_verts(name, work):
    os.makedirs(work, exist_ok=True)
    f = os.path.join(work, "actor-" + name + ".npy")
    if os.path.exists(f):
        return np.load(f)
    a, p = actor_rows()[name]
    d, ent, bs, bsz = dsar_list.open_files(os.path.join(GAME, "build", "pc", "main", a))
    tmp = os.path.join(work, "actor-" + name + ".pak")
    open(tmp, "wb").write(dsar_list.extract(d, ent, bs, bsz, p))
    pk = ndpak.Pak(tmp)
    subs = pk.submeshes
    lod0 = [s for s in subs if "LOD0" in s["name"].upper()] or [s for s in subs if "LOD" not in s["name"].upper()] or subs
    pts = [pk.positions(s) for s in lod0]
    pts = np.concatenate([x for x in pts if x is not None])
    os.remove(tmp)
    np.save(f, pts)
    return pts


def chamfer(A, B_tree, B):
    """symmetric median nearest distance between point sets A and B"""
    d1 = cKDTree(A).query(B)[0]
    d2 = B_tree.query(A)[0]
    return float((np.median(d1) + np.median(d2)) / 2), float((np.percentile(d1, 85) + np.percentile(d2, 85)) / 2)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--prefabs", default=os.path.join(HERE, "data", "prefabs"))
    ap.add_argument("--work", default=os.path.join(os.environ.get("TEMP", "C:/Temp"), "t2r-vehpair"))
    ap.add_argument("--top", type=int, default=3)
    a = ap.parse_args()
    os.makedirs(a.work, exist_ok=True)
    idx = json.load(open(os.path.join(a.prefabs, "index.json")))["prefabs"]
    cat = []
    for l in open(os.path.join(ROOT, "re", "maps", "house-actors-catalog.tsv"), encoding="utf-8").read().splitlines()[1:]:
        c = l.split("\t")
        if c[1] in ("vehicle-big", "vehicle-car") and "F" in c[5] + c[5] or c[1] in ("vehicle-big", "vehicle-car") and "B" in c[5]:
            if not BAD.search(c[0]):
                cat.append((c[0], sorted(float(x) for x in c[2:5])))
    out = {}
    for pf in idx:
        p = json.load(open(os.path.join(a.prefabs, pf["name"] + ".json")))
        if pf["tris"] < 200:
            continue
        T = load_col(os.path.join(a.prefabs, p["collision_file"]))
        S = sample_tris(T)
        tree = cKDTree(S)
        size = sorted(p["size"])
        res = []
        for name, asz in cat:
            if any(abs(asz[i] - size[i]) > 0.4 * size[i] + 0.3 for i in range(3)):
                continue
            try:
                V = actor_verts(name, a.work)
            except Exception:
                continue
            V = V[np.isfinite(V).all(1)]
            if len(V) > 6000:
                V = V[np.random.default_rng(2).choice(len(V), 6000, replace=False)]
            lo, hi = S.min(0), S.max(0)
            best = None
            for th in (0, 90, 180, 270):
                A = V @ Ry(th).T                       # actor -> car frame rotated: a = p @ Ry(th)  =>  p = a @ Ry(th)^-1 = a @ Ry(th).T
                alo, ahi = A.min(0), A.max(0)
                sc = (hi - lo) / np.maximum(ahi - alo, 1e-6)        # actor box -> prefab box per axis (reported, applied to the prefab records the other way)
                A2 = (A - np.array([(alo[0] + ahi[0]) / 2, alo[1], (alo[2] + ahi[2]) / 2])) * sc + np.array([(lo[0] + hi[0]) / 2, lo[1], (lo[2] + hi[2]) / 2])
                ch = chamfer(A2, tree, S)
                dev = float(np.abs(np.log(sc)).max())
                if best is None or ch[0] + 0.25 * dev < best["score"]:
                    t_car = np.array([(lo[0] + hi[0]) / 2, lo[1], (lo[2] + hi[2]) / 2])
                    t_act = np.array([(alo[0] + ahi[0]) / 2, alo[1], (alo[2] + ahi[2]) / 2])
                    best = dict(actor=name, theta_deg=th, score=ch[0] + 0.25 * dev, max_scale_dev=round(math.exp(dev) - 1, 3), chamfer_m=round(ch[0], 3), chamfer85_m=round(ch[1], 3), scale_actor_to_car=np.round(sc, 4).tolist(),
                                actor_size=np.round(ahi - alo, 3).tolist(), car_anchor=np.round(t_car, 4).tolist(), actor_anchor=np.round(t_act, 4).tolist())
            if best:
                res.append(best)
        res.sort(key=lambda r: r["score"])
        for r in res:
            r["fit"] = "good" if r["max_scale_dev"] <= 0.18 and r["chamfer_m"] <= 0.12 else ("ok" if r["max_scale_dev"] <= 0.35 else "poor")
            r.pop("score")
        out[pf["name"]] = dict(size=p["size"], candidates=res[:a.top])
        print(pf["name"], p["size"], [(r["actor"], r["theta_deg"], r["chamfer_m"], r["fit"]) for r in res[:a.top]], flush=True)
    json.dump(out, open(os.path.join(a.prefabs, "pairing.json"), "w"), indent=1)


if __name__ == "__main__":
    main()
