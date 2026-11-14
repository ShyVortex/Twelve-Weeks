"""Vehicle prefabs from the SP levels: render parts + collision triangles + the traversal / cover data that belongs to one parked car,
all in car-local coordinates.  Offline, CPU only.  Spec + findings: re/maps/vehicle-prefabs.md

  python vehicle_prefabs.py extract <level>... [--work DIR] [--out DIR]
        fetch <level>.pak / -phys.pak / -ingame.pak from the game's world psarc (read only), find every parked vehicle (level_edit.prop_group),
        pick its collision (oriented boxes of its render instances, level_edit._tri_sel_obb) and its FEATURE_DB_2 edges / posts / outlines
        (those within 12 cm of that collision), express everything in the car frame and write
            <out>/<prefab>.json  and  <out>/<prefab>.col  (zlib: float32 vertices, uint32 indices, uint16 tags)
        plus <out>/index.json.  Default out = tools/maps/data/prefabs

Car frame ("yaw-only"): origin = centre of the car's collision box in x/z, lowest collision vertex in y; +Y up; +X = the heading of the
anchor render instance's local X axis projected on the ground plane; Z = X cross Y.  world = local @ R + O (row vectors), R rows = (ex, ey, ez).
"""
import argparse
import json
import math
import os
import re
import subprocess
import sys
import zlib

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import level_edit as L  # noqa: E402

DEFAULT_OUT = os.path.join(HERE, "data", "prefabs")
DUMP_PS = os.path.join(HERE, "dump_featuredb.ps1")
VEH = re.compile(r"truck|suv|humvee|van-|sedan|wagon|bus-|ambul|jeep|pickup|taxi|tractor|compact|wheel|tire|chassis|car-|hatchback|minivan|rv-|semi")
NOT_VEH = re.compile(r"sign|wheelchair|rocks|tarp|kit-leaf|bush|decal|ivy|weed|grass|moss|vine|tfrag|merge")


def pwsh():
    for c in ("pwsh", "C:/Program Files/PowerShell/7/pwsh.exe"):
        try:
            subprocess.run([c, "-NoProfile", "-Command", "1"], capture_output=True, check=True)
            return c
        except Exception:
            pass
    raise SystemExit("PowerShell 7 (pwsh) not found: the editor DLL is net9")


def dump_fdb(pak, out):
    if not os.path.exists(out):
        r = subprocess.run([pwsh(), "-NoProfile", "-File", DUMP_PS, "-Pak", pak, "-Out", out], capture_output=True, text=True)
        if r.returncode:
            raise SystemExit("dump_featuredb failed: " + r.stderr[-400:])
    return json.load(open(out, encoding="utf-8-sig"))


def pt_tri_dist(P, T):
    """distance of every point P[n,3] to the nearest triangle of T[m,3,3] (vectorised over the triangles)"""
    a, b, c = T[:, 0], T[:, 1], T[:, 2]
    n = np.cross(b - a, c - a)
    nl = np.linalg.norm(n, axis=1)
    nl = np.where(nl < 1e-12, 1e-12, nl)
    n = n / nl[:, None]
    d = np.empty(len(P))
    for i, p in enumerate(P):
        dist = ((p - a) * n).sum(1)
        q = p - dist[:, None] * n                               # projection on the plane
        # inside test with barycentric signs
        s0 = (np.cross(b - a, q - a) * n).sum(1) >= 0
        s1 = (np.cross(c - b, q - b) * n).sum(1) >= 0
        s2 = (np.cross(a - c, q - c) * n).sum(1) >= 0
        best = np.where(s0 & s1 & s2, np.abs(dist), np.inf)
        for u0, u1 in ((a, b), (b, c), (c, a)):
            e = u1 - u0
            t = np.clip(((p - u0) * e).sum(1) / np.maximum((e * e).sum(1), 1e-12), 0, 1)
            best = np.minimum(best, np.linalg.norm(p - (u0 + e * t[:, None]), axis=1))
        d[i] = best.min()
    return d


def frame_of(anchor_M, pts):
    """-> R (rows ex, ey, ez), O: car frame"""
    ex = np.array([anchor_M[0, 0], 0.0, anchor_M[0, 2]])
    if np.linalg.norm(ex) < 1e-6:                       # anchor's X points up: use Z
        ex = np.array([anchor_M[2, 0], 0.0, anchor_M[2, 2]])
    ex /= np.linalg.norm(ex)
    ey = np.array([0.0, 1.0, 0.0])
    ez = np.cross(ex, ey)
    R = np.stack([ex, ey, ez])
    loc = pts @ R.T
    lo, hi = loc.min(0), loc.max(0)
    Ol = np.array([(lo[0] + hi[0]) / 2, lo[1], (lo[2] + hi[2]) / 2])
    return R, Ol @ R


def to_local(P, R, O):
    return (np.asarray(P, float) - O) @ R.T


def vec_local(V, R):
    return np.asarray(V, float) @ R.T


def r4(a):
    return [round(float(x), 4) for x in np.asarray(a).ravel()]


def car_name(parts):
    names = [re.sub(r"\.ma$", "", p["name"].split("/")[-1]) for p in parts if not re.search(r"wheel|tire", p["name"])]
    base = sorted(names, key=len)[0] if names else "vehicle"
    return re.sub(r"-(body|chassis|cab|undercarriage|interior|frame|engine|glass.*|hardtop.*|rear-body|trailer.*|cab-body)$", "", base)


def exact_attrs(pit, keys, tg):
    """per selected triangle of phys item pit: interior bit, 3-bit material value of its key, the 8-byte material record of its tag"""
    attr = L.tri_attrs(pit.mesh, keys)
    bl = np.unpackbits(np.frombuffer(pit.blob, np.uint8), bitorder="little")
    bv = [int(bl[3 * int(x)]) | int(bl[3 * int(x) + 1]) << 1 | int(bl[3 * int(x) + 2]) << 2 for x in keys]
    b_ = pit.io + 48
    ro_ = pit.pak.ptr(b_ + 80)
    mrec = [bytes(pit.pak.d[ro_ + 8 * (int(t) >> 6):ro_ + 8 * (int(t) >> 6) + 8]).hex() for t in tg]
    return dict(inter=np.array([a[1] for a in attr]), bv=np.array(bv), mrec=mrec)


def corners(x):
    return np.array([[a, b, c] for a in (x.wlo[0], x.whi[0]) for b in (x.wlo[1], x.whi[1]) for c in (x.wlo[2], x.whi[2])])


def extract(levels, work, out):
    os.makedirs(out, exist_ok=True)
    os.makedirs(work, exist_ok=True)
    cars = []
    for lv in levels:
        src = L.fetch(lv, os.path.join(work, "src"), suffixes=("", "-phys"))
        try:
            src.update(L.fetch(lv, os.path.join(work, "src"), suffixes=("-ingame",)))
        except SystemExit:
            print("%s: no -ingame pak (no traversal data)" % lv)
        p = L.ndpak.Pak(src[""])
        insts = L.find_instances(p)
        ps, items = L.phys_items(src["-phys"])
        fdb = dump_fdb(src["-ingame"], os.path.join(work, lv + "-fdb.json")) if "-ingame" in src else dict(edges=[], posts=[], outlines=[], markers=[])
        veh = []
        for i in insts:
            nm = ", ".join(n for n, _ in i.names).lower() or i.proto.lower()
            if VEH.search(nm) and not NOT_VEH.search(nm) and not ((i.whi - i.wlo) > 15).any():
                veh.append(i)
        used = set()
        arr = lambda k, f: np.array([[*e[f[0]], *e[f[1]]] for e in fdb[k]]) if fdb[k] else np.zeros((0, 6))
        E, PS, OU = arr("edges", ("p0", "p1")), arr("posts", ("p0", "p1")), arr("outlines", ("p0", "p1"))
        for it in veh:
            if id(it) in used:
                continue
            g = L.prop_group(veh, it)
            for x in g:
                used.add(id(x))
            if all(re.search(r"wheel|tire", (", ".join(n for n, _ in x.names) or x.proto).lower()) for x in g):
                continue                                            # loose wheels, not a car
            if g and not any(re.search(r"body|cab|chassis|undercarriage|rear|trailer", (", ".join(n for n, _ in x.names) or x.proto).lower()) for x in g):
                continue
            tris, tags, xat = [], [], []
            for pit in items:
                keys, T_, tg_ = L.hc.triangles(pit.mesh)
                if len(T_) == 0:
                    continue
                k, Ts = L._tri_sel_obb(pit.mesh, g, margin=0.1)
                if len(Ts):
                    sel = np.isin(keys, k)
                    tris.append(T_[sel])
                    tags.append(tg_[sel])
                    xat.append(exact_attrs(pit, keys[sel], tg_[sel]))
            T = np.concatenate(tris) if tris else np.zeros((0, 3, 3))
            tg = np.concatenate(tags) if tags else np.zeros(0, int)
            if not len(T):
                continue                                            # no baked collision (backdrop car): not a prefab
            body = max(g, key=lambda x: np.prod(x.hi - x.lo))
            allw = T.reshape(-1, 3) if len(T) else np.concatenate([corners(x) for x in g])
            R, O = frame_of(body.M, allw)
            lc = to_local(T.reshape(-1, 3), R, O).reshape(-1, 3, 3) if len(T) else np.zeros((0, 3, 3))
            lo = lc.reshape(-1, 3).min(0) if len(T) else np.zeros(3)
            hi = lc.reshape(-1, 3).max(0) if len(T) else np.zeros(3)
            wlo, whi = allw.min(0) - 0.6, allw.max(0) + 0.6

            def pick(A, snap=0.12):
                if not len(A) or not len(T):
                    return []
                near = np.nonzero(((A[:, :3] >= wlo) & (A[:, :3] <= whi)).all(1) & ((A[:, 3:] >= wlo) & (A[:, 3:] <= whi)).all(1))[0]
                if not len(near):
                    return []
                Tn = T[((T.max(1) >= wlo) & (T.min(1) <= whi)).all(1)]
                d0 = pt_tri_dist(A[near, :3], Tn)
                d1 = pt_tri_dist(A[near, 3:], Tn)
                return [int(i) for j, i in enumerate(near) if d0[j] <= snap and d1[j] <= snap]
            ie, ip, io = pick(E), pick(PS), pick(OU)
            emap = {i: n for n, i in enumerate(ie)}
            edges = [dict(p0=r4(to_local(fdb["edges"][i]["p0"], R, O)), p1=r4(to_local(fdb["edges"][i]["p1"], R, O)),
                          nup=r4(vec_local(fdb["edges"][i]["nup"], R)), nf=r4(vec_local(fdb["edges"][i]["nf"], R)), f=fdb["edges"][i]["f"],
                          prev=emap.get(fdb["edges"][i]["prev"], 65535), next=emap.get(fdb["edges"][i]["next"], 65535), src=i) for i in ie]
            posts = [dict(p0=r4(to_local(fdb["posts"][i]["p0"], R, O)), p1=r4(to_local(fdb["posts"][i]["p1"], R, O)), n0=r4(vec_local(fdb["posts"][i]["n0"], R)),
                          n1=r4(vec_local(fdb["posts"][i]["n1"], R)), f=fdb["posts"][i]["f"], src=i) for i in ip]
            outl = [dict(p0=r4(to_local(fdb["outlines"][i]["p0"], R, O)), p1=r4(to_local(fdb["outlines"][i]["p1"], R, O)), n=r4(vec_local(fdb["outlines"][i]["n"], R)),
                         t=fdb["outlines"][i]["t"], src=i) for i in io]
            mk = []
            for m in fdb["markers"]:
                if (np.array(m["pos"]) >= wlo - 0.4).all() and (np.array(m["pos"]) <= whi + 0.4).all():
                    mk.append(dict(name=m["name"], pos=r4(to_local(m["pos"], R, O)), pos_world=r4(m["pos"]), quat_world=r4(m["quat"]), props=m["props"]))
            parts = []
            for x in g:
                Mc = np.eye(4)
                Mc[:3, :3] = x.M[:3, :3] @ R.T
                Mc[3, :3] = to_local(x.M[3, :3], R, O)
                parts.append(dict(name=(x.names[0][0] if x.names else x.proto), off=hex(x.pak_off), lo=r4(x.lo), hi=r4(x.hi), M_world=r4(x.M), M_car=r4(Mc)))
            yaw = math.degrees(math.atan2(-R[0, 2], R[0, 0]))
            xa = dict(inter=np.concatenate([a["inter"] for a in xat]) if xat else np.zeros(0, int),
                      bv=np.concatenate([a["bv"] for a in xat]) if xat else np.zeros(0, int),
                      mrec=[m for a in xat for m in a["mrec"]])
            cars.append(dict(name=car_name(parts), _xa=xa, level=lv, world_origin=r4(O), world_yaw_deg=round(yaw, 3), R=r4(R), box_local=dict(lo=r4(lo), hi=r4(hi)),
                             size=r4(hi - lo), n_tris=int(len(T)), tags=sorted({int(t) for t in tg}), parts=parts, edges=edges, posts=posts, outlines=outl,
                             markers=mk, _T=lc, _tg=tg))
    sig = {}
    for c in cars:
        s = c["name"] + "|" + "x".join(str(round(v * 2) / 2) for v in c["size"])
        sig.setdefault(s, []).append(c)
    index = []
    for s, lst in sig.items():
        lst.sort(key=lambda c: -(len(c["edges"]) + len(c["posts"]) + len(c["outlines"]) + (c["n_tris"] > 0)))
        rep = lst[0]
        nm = rep["name"]
        k = 2
        while any(i["name"] == nm for i in index):
            nm = "%s-v%d" % (rep["name"], k)
            k += 1
        rep["name"] = nm
        T, tg = rep.pop("_T"), rep.pop("_tg")
        xa = rep.pop("_xa")
        for c in lst[1:]:
            c.pop("_T")
            c.pop("_tg")
            c.pop("_xa")
        rep["signature"] = s
        rep["instances"] = [dict(level=c["level"], world_origin=c["world_origin"], world_yaw_deg=c["world_yaw_deg"], edges=len(c["edges"]), posts=len(c["posts"]),
                                 outlines=len(c["outlines"]), tris=c["n_tris"]) for c in lst]
        if len(T):
            vv, inv = np.unique(np.round(T.reshape(-1, 3), 4), axis=0, return_inverse=True)
        else:
            vv, inv = np.zeros((0, 3)), np.zeros(0, int)
        blob = zlib.compress(b"T2RC" + np.array([len(vv), len(T)], "<u4").tobytes() + vv.astype("<f4").tobytes() + inv.reshape(-1).astype("<u4").tobytes()
                             + np.asarray(tg, "<u2").tobytes(), 9)
        open(os.path.join(out, nm + ".col"), "wb").write(blob)
        mats = sorted(set(xa["mrec"]))
        open(os.path.join(out, nm + ".colattr"), "wb").write(zlib.compress(json.dumps(dict(
            note="per triangle of <name>.col (same order): interior bit, 3-bit material value of the shape key, 8-byte material record (hex) of the source item",
            inter=[int(x) for x in xa["inter"]], bv=[int(x) for x in xa["bv"]], materials=mats, mat_index=[mats.index(m) for m in xa["mrec"]])).encode(), 9))
        rep["collision_attr_file"] = nm + ".colattr"
        rep["collision_file"] = nm + ".col"
        rep["collision_format"] = "zlib( 'T2RC' u32 nverts u32 ntris | float32[nverts*3] | u32[ntris*3] | u16 tag[ntris] ), car-local metres"
        json.dump(rep, open(os.path.join(out, nm + ".json"), "w"), separators=(",", ":"))
        index.append(dict(name=nm, level=rep["level"], size=rep["size"], edges=len(rep["edges"]), posts=len(rep["posts"]), outlines=len(rep["outlines"]),
                          tris=rep["n_tris"], markers=[m["name"] for m in rep["markers"]], instances=len(lst)))
    json.dump(dict(prefabs=index), open(os.path.join(out, "index.json"), "w"), indent=1)
    for i in index:
        print("%-34s size %s edges %3d posts %3d outl %3d tris %5d markers %2d (x%d)" % (i["name"], i["size"], i["edges"], i["posts"], i["outlines"], i["tris"],
                                                                                    len(i["markers"]), i["instances"]))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd")
    ap.add_argument("levels", nargs="*")
    ap.add_argument("--work", default=os.path.join(os.environ.get("TEMP", "C:/Temp"), "t2r-vehprefab"))
    ap.add_argument("--out", default=DEFAULT_OUT)
    a = ap.parse_args()
    if a.cmd == "extract":
        extract(a.levels, a.work, a.out)
