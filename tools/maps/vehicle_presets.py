"""Vehicle presets for MP maps: a standalone actor (render + its own collision) + the SP car's vault / cover records fitted onto it.

  python vehicle_presets.py build [--prefabs DIR] [--resources FILE]
        reads <prefabs>/index.json, pairing.json, <name>.json (vehicle_prefabs.py extract + vehicle_pair.py), keeps the best prefab per actor
        (fit good/ok, has traversal records), maps every record from the SP car frame into the ACTOR's own local frame and writes
            <prefabs>/presets.json                 the library (python tools)
            <resources FILE>                       the same for the Scene Editor (default tools/local/SceneEditor/resources/prefabs.json)
  python vehicle_presets.py expand <spec.json> <out.json>
        spec  {"prefabs": [{"preset": "sedan-big-a", "pos": [x,y,z], "yaw": deg | "quat": [x,y,z,w], "name": "optional"}]}
        out   {"props": [{"art","pos","quat","auto":true,"name"}], "featuredb": {"edges":[...], "posts":[...], "outlines":[...]}}  (WORLD coordinates)
              make_map_pak.ps1 reads both ("props" become SimpleObject spawners, "featuredb" is appended to the pak's FEATURE_DB_2).

Placement rule (the only thing an editor needs): the preset is an actor; "pos" / quat are the actor spawner's position / rotation (the actor's own
origin, exactly like any other prop).  Every record point q (actor-local) goes to  world = q @ R(quat) + pos  (row vectors); normals only rotate.
"""
import argparse
import json
import math
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.dirname(HERE)
ROOT = os.path.dirname(TOOLS)
sys.path.insert(0, HERE)
DEFAULT_DIR = os.path.join(HERE, "data", "prefabs")
DEFAULT_RES = os.path.join(TOOLS, "local", "SceneEditor", "resources", "prefabs.json")
FIT_RANK = {"good": 0, "ok": 1, "poor": 2}


def Ry(deg):
    c, s = math.cos(math.radians(deg)), math.sin(math.radians(deg))
    return np.array([[c, 0, -s], [0, 1, 0], [s, 0, c]])


def quat_to_R(q):
    """row-vector rotation matrix of quaternion (x,y,z,w):  world = local @ R"""
    x, y, z, w = q
    n = math.sqrt(x * x + y * y + z * z + w * w)
    x, y, z, w = x / n, y / n, z / n, w / n
    m = np.array([[1 - 2 * (y * y + z * z), 2 * (x * y + z * w), 2 * (x * z - y * w)],
                  [2 * (x * y - z * w), 1 - 2 * (x * x + z * z), 2 * (y * z + x * w)],
                  [2 * (x * z + y * w), 2 * (y * z - x * w), 1 - 2 * (x * x + y * y)]])
    return m


def yaw_quat(deg):
    h = math.radians(deg) / 2
    return [0.0, math.sin(h), 0.0, math.cos(h)]


def r4(a):
    return [round(float(x), 4) for x in np.asarray(a).ravel()]


def fit_map(c, p):
    """prefab (car frame) -> actor-local: point and normal transforms for pairing candidate c"""
    sc = np.array(c["scale_actor_to_car"])
    ca, aa, th = np.array(c["car_anchor"]), np.array(c["actor_anchor"]), c["theta_deg"]
    Rt = Ry(th)

    def pt(P):
        return ((np.asarray(P, float) - ca) / sc + aa) @ Rt

    def nv(N):
        n = (np.asarray(N, float) * sc) @ Rt                 # inverse-transpose of the diagonal scale
        l = np.linalg.norm(n)
        return n / l if l > 1e-9 else n
    return pt, nv


# SP baked car prototype -> standalone actors that are the SAME model (names: the prototype family; a size check follows in rigid_fit)
FAMILY = {"military-truck-modern": ("military-truck-modern-a", "military-truck-modern-b"),
          "compact-sedan-a": ("compact-sedan-a-rear-rig", "sle-compact-sedan-a"),
          "sedan-big-a": ("sle-sedan-big-a", "sle-sedan-big-taxi-smallboard", "wat-traps-sedan-big-a-police"),
          "station-wagon-a": ("station-wagon-a", "res-jesse-station-wagon-a")}


def rigid_fit(pdir, pf, actor, work):
    """UNSCALED fit of an actor onto a prefab's collision: 4 headings, centre/bottom of the boxes aligned.  -> dict(theta_deg, car_anchor, actor_anchor, size_dev, chamfer_m)"""
    import vehicle_pair as VPR
    from scipy.spatial import cKDTree
    T = VPR.load_col(os.path.join(pdir, pf["name"] + ".col"))
    S = VPR.sample_tris(T)
    lo, hi = S.min(0), S.max(0)
    ca = np.array([(lo[0] + hi[0]) / 2, lo[1], (lo[2] + hi[2]) / 2])
    V = VPR.actor_verts(actor, work)
    V = V[np.isfinite(V).all(1)]
    if len(V) > 6000:
        V = V[np.random.default_rng(2).choice(len(V), 6000, replace=False)]
    tree = cKDTree(S)
    best = None
    for th in (0, 90, 180, 270):
        A = V @ Ry(th).T
        alo, ahi = A.min(0), A.max(0)
        aa = np.array([(alo[0] + ahi[0]) / 2, alo[1], (alo[2] + ahi[2]) / 2])
        ch = VPR.chamfer(A - aa + ca, tree, S)[0]
        dev = float(np.abs((ahi - alo) / np.maximum(hi - lo, 1e-6) - 1).max())
        if best is None or ch < best["chamfer_m"]:
            best = dict(theta_deg=th, actor_size=r4(ahi - alo), car_anchor=r4(ca), actor_anchor=r4(aa), size_dev=round(dev, 3), chamfer_m=round(ch, 3))
    return best


def build_exact(pdir, work):
    """presets whose actor is the same model as the SP car: rigid fit (scale 1) so the SP collision and the records line up with the actor"""
    import re
    idx = json.load(open(os.path.join(pdir, "index.json")))["prefabs"]
    out = {}
    for pf in idx:
        fam = re.sub(r"-v\d+$", "", pf["name"])
        n = pf["edges"] + pf["posts"] + pf["outlines"]
        if fam not in FAMILY or pf["tris"] < 1000 or n < 8 or not os.path.exists(os.path.join(pdir, pf["name"] + ".colattr")):
            continue
        for actor in FAMILY[fam]:
            f = rigid_fit(pdir, pf, actor, work)
            if f["size_dev"] > 0.10:
                continue
            if actor not in out or (-n, f["chamfer_m"]) < (out[actor][2], out[actor][1]["chamfer_m"]):
                out[actor] = (pf, f, -n)
    return {a: (v[0], v[1]) for a, v in out.items()}


def build(pdir, res):
    from vehicle_pair import load_col
    idx = json.load(open(os.path.join(pdir, "index.json")))["prefabs"]
    pairing = json.load(open(os.path.join(pdir, "pairing.json")))
    pb = json.load(open(os.path.join(HERE, "data", "prop_bounds.json")))
    best = {}
    for pf in idx:
        pr = pairing.get(pf["name"])
        if not pr or not pr["candidates"]:
            continue
        n = pf["edges"] + pf["posts"] + pf["outlines"]
        c = pr["candidates"][0]
        if c["fit"] == "poor" or c["max_scale_dev"] > 0.25 or n < 8 or pf["tris"] < 1000 or max(pf["size"]) > 8.0 or max(pf["size"]) < 3.0:
            continue
        key = c["actor"]
        score = (FIT_RANK[c["fit"]], -n)
        if key not in best or score < best[key][0]:
            best[key] = (score, pf, c)
    exact = build_exact(pdir, os.path.join(os.environ.get("TEMP", "C:/Temp"), "t2r-vehpair"))
    for actor, (pf, f) in exact.items():
        best[actor] = ((-1,), pf, dict(f, scale_actor_to_car=[1.0, 1.0, 1.0], max_scale_dev=f["size_dev"], fit="exact"))
    presets = []
    for actor, (_, pf, c) in sorted(best.items()):
        p = json.load(open(os.path.join(pdir, pf["name"] + ".json")))
        pt, nv = fit_map(c, p)
        edges = []
        remap = {i: i for i in range(len(p["edges"]))}
        for e in p["edges"]:
            edges.append(dict(p0=r4(pt(e["p0"])), p1=r4(pt(e["p1"])), nup=r4(nv(e["nup"])), nf=r4(nv(e["nf"])), f=e["f"], prev=e["prev"], next=e["next"]))
        posts = [dict(p0=r4(pt(q["p0"])), p1=r4(pt(q["p1"])), n0=r4(nv(q["n0"])), n1=r4(nv(q["n1"])), f=q["f"]) for q in p["posts"]]
        outl = [dict(p0=r4(pt(q["p0"])), p1=r4(pt(q["p1"])), n=r4(nv(q["n"])), t=q["t"]) for q in p["outlines"]]
        T = load_col(os.path.join(pdir, p["collision_file"]))
        Ta = pt(T.reshape(-1, 3)).reshape(-1, 3, 3)
        ab = pb.get(actor)
        presets.append(dict(
            id=actor, same_model=c["fit"] == "exact",
            collision=(dict(mode="sp-exact", prefab=pf["name"], theta_deg=c["theta_deg"], car_anchor=c["car_anchor"], actor_anchor=c["actor_anchor"],
                            note="write the SP triangles with level_edit action 'cars' (expand_map does) and strip the actor's own collision (vehicle_norcol.py)")
                       if c["fit"] == "exact" else dict(mode="actor")),
            label="%s (SP %s vault/cover)" % (actor, pf["name"]), art=actor, fit=c["fit"], chamfer_m=c["chamfer_m"], max_scale_dev=c["max_scale_dev"],
            source=dict(prefab=pf["name"], level=p["level"], instances=pf["instances"], sp_size=p["size"]),
            actor_size=c["actor_size"], actor_bounds=ab,
            records_bbox=dict(lo=r4(Ta.reshape(-1, 3).min(0)), hi=r4(Ta.reshape(-1, 3).max(0))),
            counts=dict(edges=len(edges), posts=len(posts), outlines=len(outl)),
            edges=edges, posts=posts, outlines=outl,
            ai_markers=[dict(name=m["name"], pos=r4(pt(m["pos"])), props=m["props"]) for m in p["markers"]],
            note="records are in the ACTOR's local frame (apply the spawner transform); ai_markers = SP tap-* / cover-ap spawners next to the car, AI only, not written by default"))
    lib = dict(version=1, frame="actor-local; world = q @ R(quat) + pos (row vectors, y up)", flags_note="Flags0..3 / post Flags / outline Type are copied unchanged from the SP records (re/maps/vehicle-prefabs.md)", presets=presets)
    json.dump(lib, open(os.path.join(pdir, "presets.json"), "w"), separators=(",", ":"))
    if res:
        os.makedirs(os.path.dirname(res), exist_ok=True)
        json.dump(lib, open(res, "w"), separators=(",", ":"))
    for q in presets:
        print("%-26s actor %-28s fit %-4s dev %.2f  edges %3d posts %2d outl %2d" % (q["id"], q["art"], q["fit"], q["max_scale_dev"], q["counts"]["edges"], q["counts"]["posts"], q["counts"]["outlines"]))
    print(len(presets), "presets ->", pdir, res or "")


def car_pose(q, pos, yaw):
    """actor spawner pose (pos, yaw deg) -> pose of the SP car frame that its collision uses:  c @ Ry(psi_c) + P_c  with psi_c = yaw + theta, P_c = pos + (aa - ca) @ Ry(psi_c)"""
    col = q["collision"]
    psi = yaw + col["theta_deg"]
    Pc = np.asarray(pos, float) + (np.array(col["actor_anchor"]) - np.array(col["car_anchor"])) @ Ry(psi)
    return Pc, psi


def place(lib, spec):
    byid = {q["id"]: q for q in lib["presets"]}
    props, E, P, O = [], [], [], []
    cars, norcol = [], set()
    for k, it in enumerate(spec["prefabs"]):
        q = byid[it["preset"]]
        quat = it.get("quat") or yaw_quat(it.get("yaw", 0.0))
        R = quat_to_R(quat)
        pos = np.array(it["pos"], float)
        w = lambda a: (np.asarray(a, float) @ R + pos)
        n = lambda a: np.asarray(a, float) @ R
        if q["collision"]["mode"] == "sp-exact" and it.get("collision", "sp") == "sp":      # "collision": "actor" on a placement = the actor's own hull only, no -phys triangles
            if abs(quat[0]) > 1e-4 or abs(quat[2]) > 1e-4:
                raise SystemExit("preset %s: sp-exact collision needs a pure yaw rotation" % q["id"])
            Pc, psi = car_pose(q, pos, 2 * math.degrees(math.atan2(quat[1], quat[3])))
            cars.append(dict(prefab=q["collision"]["prefab"], pos=r4(Pc), yaw=round(psi, 4), name=it.get("name") or "t2r-car-%d-%s" % (k + 1, q["id"])))
            norcol.add(q["art"])
        props.append(dict(art=q["art"], pos=r4(pos), quat=r4(quat), auto=True, name=it.get("name") or "t2r-car-%d-%s" % (k + 1, q["id"])))
        base = len(E)
        for e in q["edges"]:
            E.append(dict(p0=r4(w(e["p0"])), p1=r4(w(e["p1"])), nup=r4(n(e["nup"])), nf=r4(n(e["nf"])), f=e["f"],
                          prev=e["prev"] if e["prev"] == 65535 else e["prev"] + base, next=e["next"] if e["next"] == 65535 else e["next"] + base))
        for e in q["posts"]:
            P.append(dict(p0=r4(w(e["p0"])), p1=r4(w(e["p1"])), n0=r4(n(e["n0"])), n1=r4(n(e["n1"])), f=e["f"]))
        for e in q["outlines"]:
            O.append(dict(p0=r4(w(e["p0"])), p1=r4(w(e["p1"])), n=r4(n(e["n"])), t=e["t"]))
    return dict(props=props, featuredb=dict(edges=E, posts=P, outlines=O), cars=cars, norcol=sorted(norcol))


def _room(m, margin=6.0):
    """phys triangles wholly outside the map's play area (bounds [x0, x1, z0, z1] + margin) may be dropped from an item whose tagfile cannot grow, to pay for a car"""
    b = m.get("bounds")
    if not b:
        return []
    x0, x1, z0, z1 = b[0] - margin, b[1] + margin, b[2] - margin, b[3] + margin
    H = 1e4
    return [[-H, -H, -H, x0, H, H], [x1, -H, -H, H, H, H], [-H, -H, -H, H, H, z0], [-H, -H, z1, H, H, H]]


def expand_map(m, pdir=DEFAULT_DIR):
    """sp_maps.json map entry with "prefabs": [{"preset", "pos", "yaw" | "quat", "name"?}] -> {"props": [...], "featuredb": {...}} (world coordinates)"""
    lib = json.load(open(os.path.join(pdir, "presets.json")))
    out = place(lib, {"prefabs": m.get("prefabs", [])})
    out["car_edits"] = []
    if out["cars"]:
        print("WARNING map %s: %d car(s) get the SP collision in -phys, but their actors still carry their own hull (tools/maps/vehicle_norcol.py is an untested "
              "A/B experiment): until a render-only actor is staged the car collides twice" % (m["key"], len(out["cars"])))
        import level_edit
        levels = m.get("prefab_levels") or ([m["prefab_level"]] if m.get("prefab_level") else []) + [x for x in m.get("levels", [])[1:] if x.startswith(("nor-", "wat-", "flo-", "afm-", "san-", "sle-", "pat-"))]
        for lv, cs in level_edit.assign_car_levels(levels, out["cars"], _room(m), log=lambda *a: None):
            out["car_edits"].append({"action": "cars", "name": "placed vehicle presets (exact SP collision)", "level": lv, "cars": cs, "room": _room(m)})
    out["car_edit"] = out["car_edits"][0] if out["car_edits"] else None
    for p in out["props"]:
        p["name"] = "%s-%s" % (m["key"], p["name"])
    return out


def prefab_actors(m):
    return sorted({q["art"] for q in json.load(open(os.path.join(DEFAULT_DIR, "presets.json")))["presets"] if q["id"] in {p["preset"] for p in m.get("prefabs", [])}})


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd")
    ap.add_argument("args", nargs="*")
    ap.add_argument("--prefabs", default=DEFAULT_DIR)
    ap.add_argument("--resources", default=DEFAULT_RES)
    a = ap.parse_args()
    if a.cmd == "build":
        build(a.prefabs, a.resources)
    elif a.cmd == "expand":
        lib = json.load(open(os.path.join(a.prefabs, "presets.json")))
        json.dump(place(lib, json.load(open(a.args[0]))), open(a.args[1], "w"), indent=1)
