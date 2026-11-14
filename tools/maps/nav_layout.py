"""Factions layout screen for a map candidate, on its navmesh (design rules: re/maps/design-rules.md section 11).

  python nav_layout.py <key> [<key>...]          # added maps (re/maps/seeds/<key>-nav.json, starts tools/maps/data/<key>-spawns.json)
  python nav_layout.py --pool gas-station ...    # a stock PvP map (re/maps/seeds/pool-<name>-nav.json + tools/spawns/<map>.json)
  (also via nav_plan.py layout <key>)

Factions maps are roughly square or rectangular with loops: several routes between the teams, no single narrow throat,
no long corridors, no chain of rooms joined by one passage.

FLOOR-AWARE: the navmesh is rasterised into a graph of (1 m cell, polygon) nodes. Two floors that overlap in plan
(an interior under a roof, a bridge over a street) are separate nodes; two nodes are joined only if their polygons share an edge
(stairs, ramps and slopes are continuous navmesh, so they are connections) or are bridged (navmesh seams, a ladder / mantle /
door gap <= 1 m; big parts that come within 3.5 m are joined by ONE link, as in nav_plan.py). A transition-room chain shows up
as a narrow cut. Metrics (largest connected part inside the bounds):
  area     walkable area, all floors
  fill     plan area (union of floors) / minimum-area rotated bounding box
  aspect   long / short side of that box
  throat   min cut between the two team starts (flow over 8-connected nodes, metres): the narrowest cross-section
  routes   independent routes between the starts: shortest path, then block 8 m around it (same floor, the starts excepted),
           repeat; routes <= 1.8 x the shortest path count
  chokes   balanced chokepoints: narrow cuts (< 8 m) that split the space into two parts of 15-85 % (40 sampled seed pairs, clustered 15 m)
  corridor longest stretch under 4 m wide on every route between the starts (the shortest of the routes' worst stretches), metres
PASS / FAIL against THRESH (derived from the reference maps, see design-rules.md section 11).
"""
import json
import math
import os
import sys

import numpy as np
from scipy.sparse import csr_matrix
from scipy.sparse.csgraph import connected_components, dijkstra, maximum_flow, shortest_path
from scipy.spatial import cKDTree

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import nav_plan as NP  # noqa: E402

CELL = 1.0
# derived from the stock pool maps (design-rules.md section 11): fill 0.44-0.69, aspect 1.0-1.6, throat 13-71 m (Forest 2 m: its navmesh is fragmented, see design-rules.md), chokes 0, corridor 7-30 m, area 2800-7200 m2
THRESH = {"fill": 0.35, "aspect_max": 2.2, "throat": 10.0, "area": 2000.0, "routes_warn": 2, "chokes_max": 1, "corridor_max": 40.0}

# stock PvP maps: (nav seeds name, spawn dump) - the spawner dumps are tools/spawns/<name>.json (untracked)
POOL = {"forest": "forest", "gas-station": "gas-station", "school": "school", "resort": "resort", "seraphite-camp": "seraphite-camp",
        "houses": "rescue-jesse-houses", "hospital": "hospital", "shipyard": "shipyard"}


def _plane(p):
    """y(x, z) of a polygon: least-squares plane through its vertices (flat polygons: the mean)"""
    a = np.array([[v[0], v[2], 1.0] for v in p])
    b = np.array([v[1] for v in p])
    if len(p) < 3 or np.ptp(b) < 0.05:
        return 0.0, 0.0, float(b.mean())
    sol = np.linalg.lstsq(a, b, rcond=None)[0]
    return float(sol[0]), float(sol[1]), float(sol[2])


def build_nodes(nav, keep):
    """Graph of (1 m cell, height band) nodes for the polygons in `keep`. Each cell keeps one node per floor (height bands
    > 1.2 m apart: an interior under a roof is a separate node). Neighbouring cells are joined when their heights differ by
    <= 0.9 m (stairs / ramps / slopes are continuous navmesh, so they connect; floors 2.5 m apart do not). Navmesh T-junctions
    need no shared vertices this way. Big parts that come within 3.5 m (seams between level paks, fence gaps, ladder / mantle /
    door gaps) are joined by one link."""
    from matplotlib.path import Path
    cells = {}
    for i in sorted(keep):
        p = nav.polys[i]
        px = [v[0] for v in p]
        pz = [v[2] for v in p]
        i0, i1 = int(math.floor(min(px) / CELL)), int(math.floor(max(px) / CELL))
        j0, j1 = int(math.floor(min(pz) / CELL)), int(math.floor(max(pz) / CELL))
        gx, gz = np.meshgrid(np.arange(i0, i1 + 1), np.arange(j0, j1 + 1))
        gx, gz = gx.ravel(), gz.ravel()
        pts = np.column_stack([(gx + 0.5) * CELL, (gz + 0.5) * CELL])
        path = Path(np.array([(v[0], v[2]) for v in p]))
        ins = np.zeros(len(gx), bool)
        for ox, oz in ((0, 0), (0.45, 0), (-0.45, 0), (0, 0.45), (0, -0.45), (0.4, 0.4), (-0.4, 0.4), (0.4, -0.4), (-0.4, -0.4)):
            ins |= path.contains_points(pts + [ox, oz])           # a cell counts when any of 9 samples is inside (covers 0.4 m seams between polygons)
        a, b, c = _plane(p)
        for cx, cz in zip(gx[ins].tolist(), gz[ins].tolist()):
            y = a * (cx + 0.5) * CELL + b * (cz + 0.5) * CELL + c
            lst = cells.setdefault((cx, cz), [])
            if all(abs(y - ny) > 1.2 for ny in lst):
                lst.append(y)
    xs, zs, ys = [], [], []
    node = {}
    for (cx, cz), lst in cells.items():
        for k, y in enumerate(lst):
            node[(cx, cz, k)] = len(xs)
            xs.append((cx + 0.5) * CELL)
            zs.append((cz + 0.5) * CELL)
            ys.append(y)
    rows, cols, caps = [], [], []
    for (cx, cz), lst in cells.items():
        for dx, dz, c in ((1, 0, 10), (0, 1, 10), (1, 1, 7), (1, -1, 7)):
            o = cells.get((cx + dx, cz + dz))
            if not o:
                continue
            for k, y in enumerate(lst):
                for k2, y2 in enumerate(o):
                    if abs(y - y2) <= 0.9:
                        a_, b_ = node[(cx, cz, k)], node[(cx + dx, cz + dz, k2)]
                        rows += [a_, b_]
                        cols += [b_, a_]
                        caps += [c, c]
    x, z, y = np.array(xs), np.array(zs), np.array(ys)
    rows, cols, caps = np.array(rows, int), np.array(cols, int), np.array(caps, int)
    n = len(x)
    # join big parts that nearly touch (one link per pair of parts, at their closest nodes)
    adjm = csr_matrix((np.ones(len(rows)), (rows, cols)), shape=(n, n))
    nc, lab = connected_components(adjm, directed=False)
    sizes = np.bincount(lab)
    bigc = [k for k in range(nc) if sizes[k] >= 150]
    tree = cKDTree(np.column_stack([x, z]))
    best = {}
    for u in range(n):
        if sizes[lab[u]] < 150:
            continue
        for v in tree.query_ball_point([x[u], z[u]], 3.5):
            if lab[v] > lab[u] and sizes[lab[v]] >= 150 and abs(y[u] - y[v]) <= 1.2:
                d = math.hypot(x[u] - x[v], z[u] - z[v])
                if d < best.get((lab[u], lab[v]), (1e9,))[0]:
                    best[(lab[u], lab[v])] = (d, u, v)
    for d, u, v in best.values():
        rows = np.append(rows, [u, v])
        cols = np.append(cols, [v, u])
        caps = np.append(caps, [10, 10])
    return {"x": x, "z": z, "y": y, "rows": rows, "cols": cols, "caps": caps}


def min_area_box(x, z):
    pts = np.column_stack([x, z])
    best = None
    for a in range(0, 90, 3):
        t = math.radians(a)
        r = pts @ np.array([[math.cos(t), -math.sin(t)], [math.sin(t), math.cos(t)]])
        d = r.max(0) - r.min(0) + 1
        if best is None or d[0] * d[1] < best[0]:
            best = (d[0] * d[1], max(d), min(d))
    return best


def _maxflow(n, rows, cols, caps, src, snk):
    big = 10 ** 6
    r = np.concatenate([rows, np.full(len(src), n), snk])
    c = np.concatenate([cols, src, np.full(len(snk), n + 1)])
    k = np.concatenate([caps, np.full(len(src), big), np.full(len(snk), big)])
    g = csr_matrix((k.astype(np.int32), (r, c)), shape=(n + 2, n + 2))
    g.sum_duplicates()
    return maximum_flow(g, n, n + 1), g


def _source_side(res, g, n):
    resid = (g - res.flow).tocsr()
    resid.data = (resid.data > 0).astype(np.int8)
    resid.eliminate_zeros()
    seen = np.zeros(n + 2, bool)
    seen[n] = True
    st = [n]
    ip, ind = resid.indptr, resid.indices
    while st:
        u = st.pop()
        for v in ind[ip[u]:ip[u + 1]]:
            if not seen[v]:
                seen[v] = True
                st.append(v)
    return seen[:n]


def screen(nav, keep, starts0, starts1):
    """nav = NP.Nav, keep = poly ids (the largest part inside the bounds), starts = [(x, y, z)]"""
    G = build_nodes(nav, keep)
    n = len(G["x"])
    # connected part of the node graph that holds most nodes
    adjm = csr_matrix((np.ones(len(G["rows"])), (G["rows"], G["cols"])), shape=(n, n))
    nc, lab = connected_components(adjm, directed=False)
    big = np.argmax(np.bincount(lab))
    sel = np.where(lab == big)[0]
    remap = -np.ones(n, int)
    remap[sel] = np.arange(len(sel))
    m = (remap[G["rows"]] >= 0) & (remap[G["cols"]] >= 0)
    rows, cols, caps = remap[G["rows"][m]], remap[G["cols"][m]], G["caps"][m]
    x, z, y = G["x"][sel], G["z"][sel], G["y"][sel]
    n = len(sel)
    tree = cKDTree(np.column_stack([x, z]))
    area = n * CELL * CELL
    plan = len({(int(a // CELL), int(b // CELL)) for a, b in zip(x, z)}) * CELL * CELL
    box, long_, short = min_area_box(x, z)
    out = {"area": area, "fill": plan / box, "aspect": long_ / max(short, 1.0), "floors": round(area / max(plan, 1.0), 2)}

    def snap(p):
        d, i = tree.query([p[0], p[2]], k=12)
        cand = [j for j in np.atleast_1d(i) if j < n]
        return int(min(cand, key=lambda j: abs(y[j] - p[1]) * 3 + math.hypot(x[j] - p[0], z[j] - p[2])))

    s0 = [snap(p) for p in starts0]
    s1 = [snap(p) for p in starts1]

    def disc(centres, r):
        out_ = set()
        for c in centres:
            for j in tree.query_ball_point([x[c], z[c]], r):
                if abs(y[j] - y[c]) < 3.0:
                    out_.add(j)
        return out_

    A, B = disc(s0, 6.0), disc(s1, 6.0)
    sa, sb = np.array(sorted(A - B), int), np.array(sorted(B - A), int)
    res, _ = _maxflow(n, rows, cols, caps, sa, sb)
    out["throat"] = res.flow_value / 10.0
    # independent routes
    w = np.where(caps == 10, 1.0, 1.414)
    routes, paths = [], []
    blocked = np.zeros(n, bool)
    keepn = np.zeros(n, bool)
    keepn[list(disc(s0 + s1, 12.0))] = True
    first = None
    for _ in range(6):
        ok = ~blocked[rows] & ~blocked[cols]
        gm = csr_matrix((w[ok], (rows[ok], cols[ok])), shape=(n, n))
        d, pred = shortest_path(gm, indices=s0[0], return_predecessors=True)
        if not math.isfinite(d[s1[0]]):
            break
        if first is None:
            first = d[s1[0]]
        if d[s1[0]] > 1.8 * first:
            break
        routes.append(d[s1[0]])
        u = s1[0]
        path = []
        while u != s0[0] and u >= 0:
            path.append(u)
            u = pred[u]
        paths.append(path[::-1])
        for u in path:
            for j in tree.query_ball_point([x[u], z[u]], 8.0):
                if abs(y[j] - y[u]) < 3.0 and not keepn[j]:
                    blocked[j] = True
    out["routes"] = len(routes)
    out["route_lengths"] = [round(r) for r in routes]
    # balanced chokes
    rng = np.random.default_rng(1)
    found = []
    for _ in range(40):
        a = int(rng.integers(n))
        dd = (x - x[a]) ** 2 + (z - z[a]) ** 2
        far = np.argsort(-dd)[: max(10, n // 8)]
        b = int(far[rng.integers(len(far))])
        SA, SB = disc([a], 5.0), disc([b], 5.0)
        sa_, sb_ = np.array(sorted(SA - SB), int), np.array(sorted(SB - SA), int)
        if not len(sa_) or not len(sb_):
            continue
        r_, g_ = _maxflow(n, rows, cols, caps, sa_, sb_)
        width = r_.flow_value / 10.0
        if width >= 8.0:
            continue
        side = _source_side(r_, g_, n)
        frac = side.sum() / n
        if not 0.15 <= frac <= 0.85:
            continue
        ok = side[rows] & ~side[cols]
        if not ok.any():
            continue
        cx, cz = x[rows[ok]].mean(), z[rows[ok]].mean()
        if all(math.hypot(cx - f[0], cz - f[1]) > 15 for f in found):
            found.append((cx, cz, width, frac))
    out["chokes"] = len(found)
    out["choke_list"] = [(round(f[0]), round(f[1]), round(f[2], 1), round(f[3], 2)) for f in found]
    # corridor: along each independent route, the longest stretch whose clearance (m to the nearest navmesh edge / hole) is
    # under 2.0 m (a passage under 4 m wide); the worst route counts as the map's corridor only if ALL routes have one
    deg = np.bincount(rows, minlength=n)
    edgey = np.where(deg < 8)[0]
    gu = csr_matrix((np.where(caps == 10, 1.0, 1.414), (rows, cols)), shape=(n, n))
    clear = dijkstra(gu, indices=edgey, min_only=True) * CELL
    per = []
    for path in paths:
        best_, cur = 0.0, 0.0
        for a_, b_ in zip(path, path[1:]):
            step = math.hypot(x[a_] - x[b_], z[a_] - z[b_])
            cur = cur + step if clear[b_] < 2.0 else 0.0
            best_ = max(best_, cur)
        per.append(best_)
    longest = min(per) if per else 0.0
    out["corridor_routes"] = [round(v) for v in per]
    out["corridor"] = longest
    return out


def verdict(r, spec=None):
    """spec "screen": {"chokes_max": n, ...} overrides THRESH for one map (multi-floor maps: the entrances of an upper floor / roof pocket count as
    chokes; the spec carries the reason in "screen_note")"""
    t = dict(THRESH)
    t.update((spec or {}).get("screen") or {})
    fails = []
    if r["area"] < t["area"]:
        fails.append(f"area {r['area']:.0f} m2 < {t['area']:.0f}")
    if r["fill"] < t["fill"]:
        fails.append(f"fill {r['fill']:.2f} < {t['fill']}")
    if r["aspect"] > t["aspect_max"]:
        fails.append(f"aspect {r['aspect']:.1f} > {t['aspect_max']}")
    if r["throat"] < t["throat"]:
        fails.append(f"throat {r['throat']:.0f} m < {t['throat']:.0f}")
    if r["routes"] < t["routes_warn"]:
        fails.append(f"WARN routes {r['routes']}")
    if r["chokes"] > t["chokes_max"]:
        fails.append(f"chokes {r['chokes']} > {t['chokes_max']}")
    if r["corridor"] > t["corridor_max"]:
        fails.append(f"corridor {r['corridor']:.0f} m > {t['corridor_max']:.0f}")
    return fails


def _word(v):
    hard = [f for f in v if not f.startswith("WARN")]
    if hard:
        return "FAIL: " + "; ".join(v)
    return "PASS (" + "; ".join(v) + ")" if v else "PASS"


def _teams(sp_list):
    t0 = [tuple(s["pos"]) for s in sp_list if s.get("name", "").startswith("to1-t0-intro")]
    t1 = [tuple(s["pos"]) for s in sp_list if s.get("name", "").startswith("to1-t1-intro")]
    return t0, t1


def inputs(key, pool=False):
    """-> nav, keep (poly ids), starts0, starts1 (x, y, z)"""
    R = os.path.join(NP.ROOT, "re", "maps", "seeds")
    if pool:
        d = json.load(open(os.path.join(R, f"pool-{key}-nav.json"), encoding="utf-8-sig"))
        nav = NP.Nav([([tuple(v) for v in p], lv) for lv, ps in d.items() for p in ps])
        import layoutlib
        sp = layoutlib.pool_spawners(POOL.get(key, key))        # pak dump, never stale
        sp = sp if isinstance(sp, list) else sp.get("spawners", sp)
        t0, t1 = _teams(sp)
        allp = [s["pos"] for s in sp if s.get("name", "").startswith("to1-") and "spawn-point" in s.get("name", "") or s.get("name", "").startswith("to1-supplybox")]
        bnd = None
        if allp:    # the play space = the placed spawns / boxes + 25 m (the pool maps have no explicit bounds)
            bnd = [min(p[0] for p in allp) - 25, max(p[0] for p in allp) + 25, min(p[2] for p in allp) - 25, max(p[2] for p in allp) + 25]
    else:
        m = NP.load_spec(key)
        nav = NP.Nav(NP.load_nav(key))
        bnd = m.get("bounds")
        sp = NP.read_spawns(key) if os.path.exists(os.path.join(NP.DATA, f"{key}-spawns.json")) else None
        if not sp:
            return nav, None, None, None
        t0, t1 = [tuple(q["pos"]) for q in sp["intro0"]], [tuple(q["pos"]) for q in sp["intro1"]]
    keep = {i for i in range(len(nav.polys)) if not bnd or (bnd[0] <= nav.cen[i][0] <= bnd[1] and bnd[2] <= nav.cen[i][2] <= bnd[3])}
    # the connected part (poly graph incl. bridges) that holds the team starts
    if not t0 or not t1:
        return nav, keep, None, None
    i0 = nav.poly_at(t0[0][0], t0[0][1], t0[0][2], dy=3.0)
    if i0 is None:
        i0 = min(keep, key=lambda i: math.dist(nav.cen[i], t0[0]))
    seen = {i0}
    st = [i0]
    while st:
        u = st.pop()
        for v in nav.adj[u]:
            if v in keep and v not in seen:
                seen.add(v)
                st.append(v)
    return nav, seen, t0, t1


def run(keys, pool=False):
    rows = []
    for k in keys:
        try:
            nav, keep, t0, t1 = inputs(k, pool)
        except (OSError, KeyError, ValueError, IndexError) as e:
            rows.append((k, None, f"no navmesh / spawns ({type(e).__name__})"))
            continue
        if not t0 or not t1:
            rows.append((k, None, "no team starts"))
            continue
        r = screen(nav, keep, t0, t1)
        rows.append((k, r, verdict(r, None if pool else NP.load_spec(k))))
    print(f"{'map':18s} {'area m2':>8s} {'floors':>6s} {'fill':>5s} {'aspect':>6s} {'throat m':>8s} {'routes':>6s} {'chokes':>6s} {'corridor m':>10s}  verdict")
    for k, r, v in rows:
        if r is None:
            print(f"{k:18s} {'-':>8s} {'-':>6s} {'-':>5s} {'-':>6s} {'-':>8s} {'-':>6s} {'-':>6s} {'-':>10s}  {v}")
            continue
        print(f"{k:18s} {r['area']:8.0f} {r['floors']:6.2f} {r['fill']:5.2f} {r['aspect']:6.1f} {r['throat']:8.0f} {r['routes']:6d} {r['chokes']:6d} "
              f"{r['corridor']:10.0f}  {_word(v)}")
        if r["chokes"]:
            print(f"{'':18s} chokes at (x, z, width m, share): {r['choke_list']}")
    return rows


if __name__ == "__main__":
    a = sys.argv[1:]
    if a and a[0] == "--pool":
        run(a[1:] or list(POOL), True)
    else:
        run(a)
