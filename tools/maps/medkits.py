"""Health-kit (medkit) spots for the added maps: python medkits.py [gen|list] [key ...]  ->  tools/maps/data/<key>-medkits.json + tools/ext/medkits.h

2013 evidence (re/maps/medkits-2013.md): every launch Factions level (PS3 disc 1.00, coop-*-pak-ingame12.pak) carries a pool of 7-8 medkit spawners
`pos-pickup-spawn-medkit-N` (art `medkit`); ss-coop-spawn-pickups.dc spawns 6 of them in Supply Raid (tdm), 4 in `objective`, 0 in Survivors
(elimination).  The pools sit on maps whose pickup extent is 4900-14000 m2 (median 7900 m2): ~0.76 active kits per 1000 m2.  The client's own maps
carry 4 each on 4400-5500 m2 (spawn extent + 10 m margin), which the same density rounds to (3.3-4.2 -> 4).  So

    count = clamp(round(6 * A / 7900), 4, 12)       A = hull of the map's intro / respawn / box points, grown by a 10 m margin

Placement (measured on the 2013 pools and the client's four-kit maps): kits >= 14 m apart (2013 median nearest neighbour 16-24 m, client maps 12-30 m),
>= 8 m from a team start, >= 5 m from a respawn / supply box, split evenly between the two team halves (an odd kit sits in the middle).
Surfaces: REAL level collision (reach_check's World = every level's Havok triangles + the map's props): a flat horizontal surface 0.55-1.40 m above a
floor the players walk on (stand mode flood from the team starts), at most 1.5 m from that floor, 0.4 m clear above, flat to 4 cm over the kit's
footprint, preferring surfaces indoors (a ceiling within 5 m) and next to a wall (shelves, counters, tables, crates).  y = the surface itself.

  python medkits.py gen [key ...]    # compute (default: every shipped added map), write the json files + the header, print a report
  python medkits.py list              # the counts only (no collision needed)
"""
import json
import math
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.dirname(HERE)
sys.path.insert(0, HERE)
DATA = os.path.join(HERE, "data")
HEADER = os.path.join(TOOLS, "ext", "medkits.h")
MAIN = os.environ.get("T2R_MAIN_ROOT", os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")))

# map key -> map-list index (daemon MAPS / ext MF_MAPS = containers.h CL_MAP)
INDEX = {"forest": 0, "hospital": 7, "train-station": 12, "downtown": 13, "jackson-suburbs": 15, "outpost": 16, "wilds-houses": 18,
         "capitol-shops": 19, "into-the-city": 20, "overpass": 21, "p1-bookstore": 17}
SP_KEYS = ["train-station", "downtown", "jackson-suburbs", "outpost", "wilds-houses", "capitol-shops", "into-the-city", "overpass"]
# spawners of the client's own maps (art `medkit`, to1-healthkit-N): respawn only, no new spots
SPEC_HAS = {"gas-station": 4, "school": 4, "shipyard": 4, "resort": 4, "seraphite-camp": 4, "rescue-jesse-houses": 4}

ACTIVE_2013, AREA_2013 = 6, 7900.0          # Supply Raid: 6 kits on a median 7900 m2 map
MARGIN = 10.0
MIN_N, MAX_N = 4, 12
KIT_GAP, INTRO_GAP, RESP_GAP, BOX_GAP = 14.0, 8.0, 5.0, 5.0
H_MIN, H_MAX, REACH_XZ = 0.55, 1.40, 1.5
FOOT = 0.20                                  # half footprint of the kit (0.4 m square)


def hull(P):
    pts = sorted(set((round(x, 3), round(z, 3)) for x, z in P))
    if len(pts) < 3:
        return [], 0.0, 0.0

    def cr(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])
    lo = []
    for p in pts:
        while len(lo) >= 2 and cr(lo[-2], lo[-1], p) <= 0:
            lo.pop()
        lo.append(p)
    up = []
    for p in reversed(pts):
        while len(up) >= 2 and cr(up[-2], up[-1], p) <= 0:
            up.pop()
        up.append(p)
    h = lo[:-1] + up[:-1]
    a = sum(h[i][0] * h[(i + 1) % len(h)][1] - h[(i + 1) % len(h)][0] * h[i][1] for i in range(len(h))) / 2.0
    per = sum(math.dist(h[i], h[(i + 1) % len(h)]) for i in range(len(h)))
    return h, abs(a), per


def map_area(P):
    h, a, per = hull(P)
    return a + per * MARGIN + math.pi * MARGIN * MARGIN


def count_for(area):
    return max(MIN_N, min(MAX_N, int(math.floor(ACTIVE_2013 * area / AREA_2013 + 0.5))))


def layout(key):
    p = os.path.join(DATA, f"{key}-spawns.json")
    if os.path.exists(p):
        d = json.load(open(p, encoding="utf-8-sig"))
    else:
        import layoutlib
        d = layoutlib.pool_spawners(key)          # pak dump, never stale
    if isinstance(d, list):               # a pak dump (forest, hospital)
        by = [s for s in d]
        g = lambda rx: [s["pos"] for s in by if __import__("re").search(rx, s["name"])]
        return {"intro0": g(r"^to1-t0-intro-spawn-point-\d+$"), "intro1": g(r"^to1-t1-intro-spawn-point-\d+$"),
                "respawns": g(r"^to1-spawn-point-\d+$"), "boxes": g(r"^to1-supplybox-\d+$")}
    return {k: [q["pos"] for q in d.get(k, [])] for k in ("intro0", "intro1", "respawns", "boxes")}


def heights(w, x, z, tol=0.08):
    """sorted heights of the horizontal-ish collision surfaces over (x, z); neighbours closer than tol merge"""
    ids = w.near(x, z, x, z)
    if not len(ids):
        return []
    ids = ids[w.up[ids]]
    if not len(ids):
        return []
    T = w.T[ids]
    (x1, z1), (x2, z2), (x3, z3) = T[:, 0][:, [0, 2]].T, T[:, 1][:, [0, 2]].T, T[:, 2][:, [0, 2]].T
    det = (z2 - z3) * (x1 - x3) + (x3 - x2) * (z1 - z3)
    ok = np.abs(det) > 1e-9
    det = np.where(ok, det, 1)
    l1 = ((z2 - z3) * (x - x3) + (x3 - x2) * (z - z3)) / det
    l2 = ((z3 - z1) * (x - x3) + (x1 - x3) * (z - z3)) / det
    l3 = 1 - l1 - l2
    inside = ok & (l1 >= -1e-6) & (l2 >= -1e-6) & (l3 >= -1e-6)
    y = l1 * T[:, 0, 1] + l2 * T[:, 1, 1] + l3 * T[:, 2, 1]
    out = []
    for h in sorted(y[inside]):
        if not out or h - out[-1] > tol:
            out.append(float(h))
    return out


def has_surface(hs, h, tol=0.04):
    return any(abs(q - h) <= tol for q in hs)


def candidates(w, key, reach_stand):
    """[{pos, h_floor, indoor, wall, score}] flat surfaces 0.55-1.4 m over a reachable floor"""
    import reach_check as RC
    floors = {}
    for (i, j, _), h in reach_stand.items():
        floors.setdefault((i, j), []).append(h)
    out = []
    seen = set()
    R = int(math.ceil(REACH_XZ / RC.CELL))
    x0, z0, nx, nz = w.x0, w.z0, w.nx, w.nz
    n = 0
    for (i, j), fl in floors.items():
        for a in range(max(0, i - R), min(nx, i + R + 1)):
            for b in range(max(0, j - R), min(nz, j + R + 1)):
                if (a, b) in seen:
                    continue
                seen.add((a, b))
                cx, cz = w.cell_xz(a, b)
                hs = heights(w, cx, cz)
                for hsurf in hs:
                    # player floor nearby (within the cell reach) that this surface stands above
                    best = None
                    for aa in range(max(0, a - R), min(nx, a + R + 1)):
                        for bb in range(max(0, b - R), min(nz, b + R + 1)):
                            for hf in floors.get((aa, bb), ()):
                                d = hsurf - hf
                                if H_MIN <= d <= H_MAX and math.dist((cx, cz), w.cell_xz(aa, bb)) <= REACH_XZ:
                                    if best is None or abs(d - 0.9) < abs(best - 0.9):
                                        best = d
                    if best is None:
                        continue
                    if any(abs(hsurf - q) < 0.2 for q in floors.get((a, b), ())):
                        continue                                   # a floor the players walk on, not a shelf
                    out.append((cx, hsurf, cz, best))
        n += 1
    return out


def vet(w, c):
    """-> (x, y, z, indoor, wall, flat_dev) or None: the 0.4 m footprint is flat to 4 cm, clear 0.4 m above, and the surface carries it"""
    x, y, z, d = c
    pts = [(x, z), (x - FOOT, z - FOOT), (x + FOOT, z - FOOT), (x - FOOT, z + FOOT), (x + FOOT, z + FOOT)]
    ys = []
    for px, pz in pts:
        hs = heights(w, px, pz)
        m = [q for q in hs if abs(q - y) <= 0.05]
        if not m:
            return None
        ys.append(min(m, key=lambda q: abs(q - y)))
    if max(ys) - min(ys) > 0.04:
        return None
    y = sum(ys) / len(ys)
    if not w.clear(x - FOOT, y + 0.03, z - FOOT, x + FOOT, y + 0.45, z + FOOT):
        return None
    indoor = not w.clear(x - 0.3, y + 2.2, z - 0.3, x + 0.3, y + 5.0, z + 0.3)
    wall = 0
    for k in range(8):
        a = k * math.pi / 4
        for r in (0.6, 1.0):
            if not w.clear(x + r * math.sin(a) - 0.1, y + 0.2, z + r * math.cos(a) - 0.1, x + r * math.sin(a) + 0.1, y + 1.0, z + r * math.cos(a) + 0.1):
                wall += 1
                break
    return (x, y, z, indoor, wall, max(ys) - min(ys), d)


def choose(cands, lay, n):
    t0 = [(p[0], p[2]) for p in lay["intro0"]]
    t1 = [(p[0], p[2]) for p in lay["intro1"]]
    c0 = (sum(p[0] for p in t0) / len(t0), sum(p[1] for p in t0) / len(t0))
    c1 = (sum(p[0] for p in t1) / len(t1), sum(p[1] for p in t1) / len(t1))
    sep = math.dist(c0, c1)
    intros = t0 + t1
    resp = [(p[0], p[2]) for p in lay["respawns"]]
    boxes = [(p[0], p[2]) for p in lay["boxes"]]
    pts = []
    for (x, y, z, indoor, wall, dev, d) in cands:
        s = (math.dist((x, z), c0) - math.dist((x, z), c1)) / max(sep, 1.0)       # < 0: team 0's half
        score = (1.0 if indoor else 0.0) + 0.35 * min(wall, 3) + 0.6 * (1.0 - min(abs(d - 0.9) / 0.5, 1.0)) - 4.0 * dev
        pts.append({"pos": (x, y, z), "side": s, "score": score, "indoor": indoor, "wall": wall, "d": d})
    want = {"t0": n // 2, "t1": n // 2, "mid": n % 2}
    # grow the gaps down only when a pass found nothing
    chosen = []
    for gap_scale in (1.0, 0.75, 0.55, 0.4):
        kit, intro, rsp, box = KIT_GAP * gap_scale, INTRO_GAP * gap_scale, RESP_GAP * gap_scale, BOX_GAP * gap_scale
        for side, key in (("t0", lambda s: s < -0.12), ("t1", lambda s: s > 0.12), ("mid", lambda s: abs(s) <= 0.12)):
            while sum(1 for c in chosen if c["slot"] == side) < want[side]:
                best = None
                for p in pts:
                    if not key(p["side"]) or p in chosen:
                        continue
                    xz = (p["pos"][0], p["pos"][2])
                    if any(math.dist(xz, q) < intro for q in intros) or any(math.dist(xz, q) < rsp for q in resp) \
                            or any(math.dist(xz, q) < box for q in boxes):
                        continue
                    dk = min([math.dist(xz, (c["pos"][0], c["pos"][2])) for c in chosen] or [1e9])
                    if dk < kit:
                        continue
                    # farthest-point spread, weighted by the surface quality
                    val = p["score"] + 0.04 * min(dk, 60.0)
                    if best is None or val > best[0]:
                        best = (val, p)
                if best is None:
                    break
                best[1]["slot"] = side
                chosen.append(best[1])
        if all(sum(1 for c in chosen if c["slot"] == s) >= want[s] for s in want):
            break
    # a side that stayed short (no surface of its own half): take it from the other halves, still spaced
    k = 0
    while len(chosen) < n and k < 4:
        k += 1
        best = None
        for p in pts:
            if p in chosen:
                continue
            xz = (p["pos"][0], p["pos"][2])
            if any(math.dist(xz, q) < INTRO_GAP * 0.5 for q in intros):
                continue
            dk = min([math.dist(xz, (c["pos"][0], c["pos"][2])) for c in chosen] or [1e9])
            if dk < KIT_GAP * 0.4:
                continue
            val = p["score"] + 0.04 * min(dk, 60.0)
            if best is None or val > best[0]:
                best = (val, p)
        if best:
            best[1]["slot"] = "mid"
            chosen.append(best[1])
    return chosen, c0, c1


def pool_spec(key):
    """forest / hospital are not in sp_maps.json: their level list comes from the level sets (pool_nav), bounds from the placed points"""
    import pool_nav as PN
    lay = layout(key)
    sets = PN.bin_levels()
    lv = sets[PN.SETS[key] if key in PN.SETS else PN.HOSPITAL_SET]
    xs = [p[0] for v in lay.values() for p in v]
    zs = [p[2] for v in lay.values() for p in v]
    return {"key": key, "pak": "to1-pvp-" + key if key == "forest" else "to1-pvp-hospital", "levels": lv,
            "bounds": [min(xs), max(xs), min(zs), max(zs)], "props": []}


def hand_placed(key):
    """True when data/<key>-medkits.json came from the SceneEditor (editor_import.py): `gen` keeps it"""
    p = os.path.join(DATA, f"{key}-medkits.json")
    return os.path.exists(p) and bool(json.load(open(p)).get("hand_placed"))


def hand_json(key, kits, old=None):
    """The json of hand placed kits [{pos, quat?}] in the exact format gen_map writes (+ hand_placed). Kits that match an old kit
    (same position) keep its half / indoor / wall_dirs / above_floor."""
    lay = layout(key)
    area = map_area([(p[0], p[2]) for k2 in ("intro0", "intro1", "respawns", "boxes") for p in lay[k2]])
    t0 = [(p[0], p[2]) for p in lay["intro0"]]
    t1 = [(p[0], p[2]) for p in lay["intro1"]]
    c0 = (sum(p[0] for p in t0) / len(t0), sum(p[1] for p in t0) / len(t0))
    c1 = (sum(p[0] for p in t1) / len(t1), sum(p[1] for p in t1) / len(t1))
    sep = max(math.dist(c0, c1), 1.0)
    olds = list((old or {}).get("kits", []))
    out = []
    for k in kits:
        pos = [round(float(v), 3) for v in k["pos"]]
        o = next((q for q in olds if math.dist(q["pos"], pos) < 0.01), None)
        if o:
            out.append(dict(o, pos=pos))
            continue
        s = (math.dist((pos[0], pos[2]), c0) - math.dist((pos[0], pos[2]), c1)) / sep
        out.append({"pos": pos, "half": "t0" if s < -0.12 else "t1" if s > 0.12 else "mid", "indoor": False, "wall_dirs": 0,
                    "above_floor": 0.0})
    return {"key": key, "map_index": INDEX[key], "area_m2": round(area), "count_wanted": len(out), "hand_placed": True,
            "rule": "hand placed in the SceneEditor (tools/maps/editor_import.py); `medkits.py gen` keeps it", "kits": out}


def save_hand(key, kits):
    p = os.path.join(DATA, f"{key}-medkits.json")
    old = json.load(open(p)) if os.path.exists(p) else None
    out = hand_json(key, kits, old)
    json.dump(out, open(p, "w"), indent=1)
    write_header()
    return out


def gen_map(key):
    if hand_placed(key):
        print(f"{key}: hand placed kits kept (data/{key}-medkits.json has hand_placed; delete the flag to regenerate)", flush=True)
        return json.load(open(os.path.join(DATA, f"{key}-medkits.json")))
    import reach_check as RC
    if key in ("forest", "hospital"):
        spec = pool_spec(key)
        orig = RC.spec
        RC.spec = lambda k: spec if k == key else orig(k)
    m = RC.spec(key)
    b = m["bounds"]
    box = [b[0] - 18, b[1] + 18, b[2] - 18, b[3] + 18]
    T, used = RC.level_tris(key, box)
    P, unknown = RC.prop_tris(m.get("props", []))
    print(f"{key}: {len(T)} collision triangles, {len(P) // 12} prop boxes", flush=True)
    w = RC.World(np.concatenate([T, P]) if len(P) else T, box)
    lay = layout(key)
    seeds = [tuple(p) for p in m.get("reach_seeds", [])] or [tuple(p) for p in lay["intro0"]] + [tuple(p) for p in lay["intro1"]]
    reach = w.flood(seeds, RC.MODES["stand"])
    stand = {k: h for k, h in reach.items()}
    print(f"  stand reach: {len({(k[0], k[1]) for k in stand})} cells", flush=True)
    raw = candidates(w, key, stand)
    print(f"  {len(raw)} raw surface cells", flush=True)
    vetted = []
    seen = set()
    for c in raw:
        k = (round(c[0] / 0.5), round(c[1] / 0.1), round(c[2] / 0.5))
        if k in seen:
            continue
        seen.add(k)
        v = vet(w, c)
        if v:
            vetted.append(v)
    print(f"  {len(vetted)} candidate surfaces (flat, clear, 0.55-1.4 m over a walkable floor)", flush=True)
    area = map_area([(p[0], p[2]) for k2 in ("intro0", "intro1", "respawns", "boxes") for p in lay[k2]])
    n = count_for(area)
    chosen, c0, c1 = choose(vetted, lay, n)
    out = {"key": key, "map_index": INDEX[key], "area_m2": round(area), "count_wanted": n,
           "rule": "round(6 * area / 7900) clamped 4..12 (re/maps/medkits-2013.md)",
           "kits": [{"pos": [round(c["pos"][0], 3), round(c["pos"][1], 3), round(c["pos"][2], 3)], "half": c["slot"], "indoor": bool(c["indoor"]),
                     "wall_dirs": int(c["wall"]), "above_floor": round(c["d"], 2)} for c in chosen]}
    json.dump(out, open(os.path.join(DATA, f"{key}-medkits.json"), "w"), indent=1)
    print(f"  -> {len(chosen)}/{n} kits (area {area:.0f} m2): " + ", ".join(
        f"({c['pos'][0]:.1f} {c['pos'][1]:.2f} {c['pos'][2]:.1f} {c['slot']}{' in' if c['indoor'] else ''} h{c['d']:.2f})" for c in chosen), flush=True)
    return out


def write_header(keys=None):
    rows = []
    for key in INDEX:
        p = os.path.join(DATA, f"{key}-medkits.json")
        if os.path.exists(p):
            rows.append(json.load(open(p)))
    L = ["// generated by tools/maps/medkits.py - health-kit spots of the added maps (flat collision surfaces 0.55-1.4 m over a walkable floor)",
         "// per map-list index (daemon MAPS / ext MF_MAPS); y = the surface itself. Count rule: re/maps/medkits-2013.md.",
         "typedef struct { float p[3]; } mk_pt_t;"]
    for r in rows:
        nm = r["key"].upper().replace("-", "_")
        L.append(f"static const mk_pt_t MK_{nm}[] = {{   // map {r['map_index']} ({r['key']}): {len(r['kits'])} kits, area {r['area_m2']} m2")
        for k in r["kits"]:
            L.append("    {{%.3ff, %.3ff, %.3ff}}, // %s%s" % (k["pos"][0], k["pos"][1], k["pos"][2], k["half"], ", indoor" if k["indoor"] else ""))
        L.append("};")
    L.append("static const struct { int map; const mk_pt_t *p; int n; } MK_TAB[] = {")
    for r in rows:
        nm = r["key"].upper().replace("-", "_")
        L.append(f"    {{{r['map_index']}, MK_{nm}, {len(r['kits'])}}},")
    L.append("};")
    open(HEADER, "w", newline="\n").write("\n".join(L) + "\n")
    print(f"{HEADER}: {len(rows)} maps")


def main(argv):
    cmd = argv[1] if len(argv) > 1 else "gen"
    keys = argv[2:] or (SP_KEYS + ["forest", "hospital"])
    if cmd == "list":
        for k in keys:
            area = map_area([(p[0], p[2]) for v in layout(k).values() for p in v])
            print(f"{k:20s} area {area:7.0f} m2 -> {count_for(area)} kits")
        return
    for k in keys:
        gen_map(k)
    write_header()


if __name__ == "__main__":
    main(sys.argv)
