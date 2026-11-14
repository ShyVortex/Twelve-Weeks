"""Navmesh analysis and nav-aware spawn planning for the SP-section maps (design rules: re/maps/design-rules.md).

  python nav_plan.py report <key> [--png out.png]   # walkable area, components, spawns on / off the navmesh, path
                                                    # distances (intro to intro, intro to boxes), blocker clearance
  python nav_plan.py layout <key> [<key>...]        # Factions layout screen (nav_layout.py, design-rules.md section 11): PASS / FAIL
  python nav_plan.py seed <key> [--write]           # nav-aware placeholder spawns (replace the spawner-seeded ones):
                                                    # 4 + 4 intros 80-110 m apart BY PATH, 13 respawns in a ring,
                                                    # 6 boxes (2 per side + neutral). --write -> tools/maps/data/<key>-spawns.json

Needs re/maps/seeds/<key>-nav.json (the loaded levels' navmeshes: sp_bounds.py dumps them) and, for nav_family
neighbours, <key>-nb-nav.json. The nav graph: polygons are nodes, two polygons are joined when they share an edge
(vertices within 0.2 m) or, for interiors / doors, when a vertex of one lies within 0.6 m of the other; the path
metric is Dijkstra over polygon centroids (a lower bound of the real path by a few percent).
"""
import heapq
import json
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.dirname(HERE)
ROOT = os.path.dirname(TOOLS)
SPEC = os.path.join(HERE, "sp_maps.json")
DATA = os.path.join(HERE, "data")
SEEDS = os.path.join(ROOT, "re", "maps", "seeds")

CLEAR = 1.0          # spawns / boxes keep this far from the nav boundary (walls, drops)
BLOCKER_CLEAR = 3.0  # and from boundary blockers (design: sp_maps.py seed does the same)


def load_spec(key):
    return [m for m in json.load(open(SPEC, encoding="utf-8"))["maps"] if m["key"] == key][0]


def load_nav(key):
    p = os.path.join(SEEDS, f"{key}-nav.json")
    d = json.load(open(p, encoding="utf-8-sig"))
    polys = []
    for lv, ps in d.items():
        for v in ps:
            polys.append(([tuple(x) for x in v], lv.replace("-ingame", "")))
    return polys


def area_xz(p):
    a = 0.0
    for i in range(len(p)):
        x0, _, z0 = p[i]
        x1, _, z1 = p[(i + 1) % len(p)]
        a += x0 * z1 - x1 * z0
    return abs(a) / 2


def centroid(p):
    n = len(p)
    return (sum(v[0] for v in p) / n, sum(v[1] for v in p) / n, sum(v[2] for v in p) / n)


def seg_dist_xz(px, pz, a, b):
    ax, az, bx, bz = a[0], a[2], b[0], b[2]
    dx, dz = bx - ax, bz - az
    L = dx * dx + dz * dz
    t = 0.0 if L == 0 else max(0.0, min(1.0, ((px - ax) * dx + (pz - az) * dz) / L))
    return math.hypot(px - (ax + t * dx), pz - (az + t * dz))


def inside_xz(p, x, z):
    c = False
    n = len(p)
    for i in range(n):
        a, b = p[i], p[(i + 1) % n]
        if (a[2] > z) != (b[2] > z) and x < (b[0] - a[0]) * (z - a[2]) / (b[2] - a[2]) + a[0]:
            c = not c
    return c


class Nav:
    def __init__(self, polys):
        self.polys = [p for p, _ in polys]
        self.lv = [l for _, l in polys]
        self.cen = [centroid(p) for p in self.polys]
        self.area = [area_xz(p) for p in self.polys]
        n = len(self.polys)
        # vertex hash -> polys (shared vertices within 0.2 m = shared edge)
        cell = 0.5
        vh = {}
        for i, p in enumerate(self.polys):
            for v in p:
                vh.setdefault((round(v[0] / cell), round(v[1] / cell), round(v[2] / cell)), set()).add(i)
        self.adj = [dict() for _ in range(n)]
        for i, p in enumerate(self.polys):
            for v in p:
                k = (round(v[0] / cell), round(v[1] / cell), round(v[2] / cell))
                for dx in (-1, 0, 1):
                    for dy in (-1, 0, 1):
                        for dz in (-1, 0, 1):
                            for j in vh.get((k[0] + dx, k[1] + dy, k[2] + dz), ()):
                                if j != i:
                                    self._link(i, j)
        # grid for point queries
        self.g = {}
        c = 4.0
        self.cellsz = c
        for i, p in enumerate(self.polys):
            xs, zs = [v[0] for v in p], [v[2] for v in p]
            for cx in range(int(min(xs) // c), int(max(xs) // c) + 1):
                for cz in range(int(min(zs) // c), int(max(zs) // c) + 1):
                    self.g.setdefault((cx, cz), []).append(i)
        # boundary edges: edges of a polygon that no other polygon shares (both end vertices)
        ev = {}
        for i, p in enumerate(self.polys):
            for k in range(len(p)):
                a, b = p[k], p[(k + 1) % len(p)]
                key = tuple(sorted(((round(a[0] * 4), round(a[1] * 2), round(a[2] * 4)), (round(b[0] * 4), round(b[1] * 2), round(b[2] * 4)))))
                ev.setdefault(key, []).append((i, a, b))
        self.bedges = [v[0][1:] for v in ev.values() if len(v) == 1]
        owners = [v[0][0] for v in ev.values() if len(v) == 1]
        self._bridge(owners)
        self._join_components(owners)
        self.bgrid = {}
        for a, b in self.bedges:
            for cx in range(int(min(a[0], b[0]) // c) - 1, int(max(a[0], b[0]) // c) + 2):
                for cz in range(int(min(a[2], b[2]) // c) - 1, int(max(a[2], b[2]) // c) + 2):
                    self.bgrid.setdefault((cx, cz), []).append((a, b))

    def _bridge(self, owners):
        """polygons whose free (boundary) edges lie within 1.0 m of each other (and 0.9 m in height) are linked: nav
        sub-meshes of different levels / doors / mantles meet without sharing vertices"""
        mids = []
        for (a, b), o in zip(self.bedges, owners):
            mids.append(((a[0] + b[0]) / 2, (a[1] + b[1]) / 2, (a[2] + b[2]) / 2, o))
        h = {}
        for k, (x, y, z, o) in enumerate(mids):
            h.setdefault((int(x // 1.5), int(z // 1.5)), []).append(k)
        for k, (x, y, z, o) in enumerate(mids):
            cx, cz = int(x // 1.5), int(z // 1.5)
            for dx in (-1, 0, 1):
                for dz in (-1, 0, 1):
                    for q in h.get((cx + dx, cz + dz), ()):
                        x2, y2, z2, o2 = mids[q]
                        if o2 != o and o2 not in self.adj[o] and math.hypot(x - x2, z - z2) < 1.0 and abs(y - y2) < 0.9:
                            d = max(0.5, math.dist(self.cen[o], self.cen[o2]))
                            self.adj[o][o2] = d
                            self.adj[o2][o] = d

    def _join_components(self, owners, max_gap=3.5, min_area=150.0):
        """big components that come within max_gap m of each other (a fence gap, a snow-drift step, a seam between
        two levels) are joined by ONE link at their closest pair of free edges: players cross such seams in game"""
        comp, sizes = self.components()
        mids = [((a[0] + b[0]) / 2, (a[1] + b[1]) / 2, (a[2] + b[2]) / 2, o) for (a, b), o in zip(self.bedges, owners)]
        h = {}
        for k, (x, y, z, o) in enumerate(mids):
            h.setdefault((int(x // 4), int(z // 4)), []).append(k)
        best = {}
        for k, (x, y, z, o) in enumerate(mids):
            if sizes[comp[o]] < min_area:
                continue
            for dx in (-1, 0, 1):
                for dz in (-1, 0, 1):
                    for q in h.get((int(x // 4) + dx, int(z // 4) + dz), ()):
                        x2, y2, z2, o2 = mids[q]
                        if comp[o2] <= comp[o] or sizes[comp[o2]] < min_area or abs(y - y2) > 1.2:
                            continue
                        d = math.hypot(x - x2, z - z2)
                        if d < max_gap and d < best.get((comp[o], comp[o2]), (1e9,))[0]:
                            best[(comp[o], comp[o2])] = (d, o, o2)
        for d, o, o2 in best.values():
            w = max(0.5, math.dist(self.cen[o], self.cen[o2]))
            self.adj[o][o2] = w
            self.adj[o2][o] = w

    def _link(self, i, j):
        d = math.dist(self.cen[i], self.cen[j])
        # same walkable level: vertical gap of the centroids must be small vs distance (no wall-to-roof joins)
        if abs(self.cen[i][1] - self.cen[j][1]) > max(1.2, d * 0.6):
            return
        self.adj[i][j] = d

    def poly_at(self, x, y, z, dy=2.0):
        best, bd = None, 1e9
        for i in self.g.get((int(x // self.cellsz), int(z // self.cellsz)), ()):
            p = self.polys[i]
            if inside_xz(p, x, z):
                h = min(abs(v[1] - y) for v in p)
                if h < dy and h < bd:
                    best, bd = i, h
        return best

    multi = False        # multi-floor map (layoutlib.Ctx sets it for specs with "floors"): edges of another floor do not count

    def edge_clear(self, x, z, y=None):
        """distance from (x, z) to the nearest nav boundary edge. Multi-floor maps (self.multi) with `y`: only edges within 2 m of
        that height (the hole of a shelf on the ground floor is not a wall of the upper floor above it)"""
        c = self.cellsz
        best = 1e9
        flt = self.multi and y is not None
        for dx in (-1, 0, 1):
            for dz in (-1, 0, 1):
                for a, b in self.bgrid.get((int(x // c) + dx, int(z // c) + dz), ()):
                    if flt and min(a[1], b[1]) > y + 2.0 or flt and max(a[1], b[1]) < y - 2.0:
                        continue
                    best = min(best, seg_dist_xz(x, z, a, b))
        return best

    def components(self):
        comp = [-1] * len(self.polys)
        sizes = []
        for s in range(len(self.polys)):
            if comp[s] >= 0:
                continue
            k = len(sizes)
            st, tot = [s], 0.0
            comp[s] = k
            while st:
                u = st.pop()
                tot += self.area[u]
                for v in self.adj[u]:
                    if comp[v] < 0:
                        comp[v] = k
                        st.append(v)
            sizes.append(tot)
        return comp, sizes

    def dijkstra(self, src, comp_only=None):
        dist = {src: 0.0}
        h = [(0.0, src)]
        while h:
            d, u = heapq.heappop(h)
            if d > dist.get(u, 1e18):
                continue
            for v, w in self.adj[u].items():
                nd = d + w
                if nd < dist.get(v, 1e18):
                    dist[v] = nd
                    heapq.heappush(h, (nd, v))
        return dist


def read_spawns(key):
    return json.load(open(os.path.join(DATA, f"{key}-spawns.json")))


def blockers(m):
    return [p["pos"] for p in m.get("props", []) if p.get("auto")]


def report(key, png=None):
    m = load_spec(key)
    nav = Nav(load_nav(key))
    comp, sizes = nav.components()
    big = max(range(len(sizes)), key=lambda k: sizes[k])
    print(f"{key}: {len(nav.polys)} polys, walkable {sum(nav.area):.0f} m2, {len(sizes)} components, largest {sizes[big]:.0f} m2 "
          f"({'; '.join('%.0f' % s for s in sorted(sizes, reverse=True)[:6])})")
    per = {}
    for i, l in enumerate(nav.lv):
        per[l] = per.get(l, 0) + nav.area[i]
    print("  per level m2:", {k: round(v) for k, v in per.items()})
    xs = [v[0] for p in nav.polys for v in p]
    zs = [v[2] for p in nav.polys for v in p]
    print(f"  extent x {min(xs):.0f}..{max(xs):.0f} ({max(xs) - min(xs):.0f} m)  z {min(zs):.0f}..{max(zs):.0f} ({max(zs) - min(zs):.0f} m)")
    try:
        sp = read_spawns(key)
    except OSError:
        return nav
    bl = blockers(m)

    def info(p, what):
        x, y, z = p["pos"]
        i = nav.poly_at(x, y, z)
        if i is None:
            return f"{what} OFF NAV", None
        ec = nav.edge_clear(x, z)
        bd = min((math.dist(p["pos"], b) for b in bl), default=99)
        flags = []
        if comp[i] != big:
            flags.append(f"component {comp[i]} ({sizes[comp[i]]:.0f} m2)")
        if ec < 0.5:
            flags.append(f"{ec:.1f} m from nav edge")
        if bd < 2.0:
            flags.append(f"{bd:.1f} m from a blocker")
        return (what + (" " + ", ".join(flags) if flags else " ok")), i

    bad = 0
    nodes = {}
    for name in ("intro0", "intro1", "respawns", "boxes"):
        for k, p in enumerate(sp[name]):
            s, i = info(p, f"{name}[{k}] ({p['pos'][0]:.0f}, {p['pos'][1]:.0f}, {p['pos'][2]:.0f})")
            nodes[(name, k)] = i
            if "ok" not in s[-3:]:
                bad += 1
                print("  ", s)
    print(f"  spawns/boxes with a problem: {bad} of {sum(len(sp[n]) for n in ('intro0', 'intro1', 'respawns', 'boxes'))}")
    a, b = nodes[("intro0", 0)], nodes[("intro1", 0)]
    if a is not None and b is not None:
        d = nav.dijkstra(a)
        print(f"  intro to intro: straight {math.dist(sp['intro0'][0]['pos'], sp['intro1'][0]['pos']):.0f} m, by path "
              f"{d.get(b, float('nan')):.0f} m (target 80-110)")
        d1 = nav.dijkstra(b)
        for k, p in enumerate(sp["boxes"]):
            i = nodes[("boxes", k)]
            if i is not None:
                print(f"    box {k}: from team0 {d.get(i, -1):.0f} m, team1 {d1.get(i, -1):.0f} m")
    if png:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        from matplotlib.collections import PolyCollection
        fig, ax = plt.subplots(figsize=(12, 12), dpi=80)
        ax.add_collection(PolyCollection([[(v[0], v[2]) for v in p] for p in nav.polys], alpha=0.6, edgecolor="k", linewidth=0.1))
        for nm, c, mk in (("intro0", "r", "o"), ("intro1", "b", "o"), ("respawns", "g", "^"), ("boxes", "y", "s")):
            for p in sp[nm]:
                ax.plot(p["pos"][0], p["pos"][2], c + mk, ms=6, mec="k")
        for b in bl:
            ax.plot(b[0], b[2], "k.", ms=3)
        ax.set_aspect("equal")
        ax.autoscale_view()
        ax.grid(True, lw=0.3)
        fig.savefig(png, bbox_inches="tight")
    return nav


def _yaw_quat(yaw):
    return [0.0, math.sin(yaw / 2), 0.0, math.cos(yaw / 2)]


def seed(key, write=False):
    """Nav-aware spawns. Candidates = centroids of polygons of the largest connected component that are at least
    CLEAR m from the nav boundary and BLOCKER_CLEAR m from every boundary blocker, polygons big enough to stand on.
      team anchors: the farthest-apart-by-path pair of candidates whose path distance is 80-110 m (best: closest to
        95 m, and farthest from the map centre so both sit at the ends); each team = 4 spots within 6 m of its anchor
      respawns: 13, farthest-point sampling by PATH distance from {anchors, previous picks}, min 12 m from intros and 8 m apart
      boxes: 6 = 1 near each team (15-25 m from its anchor) + 4 neutral (far from both anchors, mid-path)"""
    m = load_spec(key)
    nav = Nav(load_nav(key))
    comp, sizes = nav.components()
    big = max(range(len(sizes)), key=lambda k: sizes[k])
    bl = blockers(m)
    # the loaded levels' own bounds (play space): ignore nav outside them
    bnd = m.get("bounds")
    cand = []
    for i, p in enumerate(nav.polys):
        if comp[i] != big or nav.area[i] < 1.2:
            continue
        x, y, z = nav.cen[i]
        if bnd and not (bnd[0] <= x <= bnd[1] and bnd[2] <= z <= bnd[3]):
            continue
        if nav.edge_clear(x, z) < CLEAR:
            continue
        if any(math.dist((x, y, z), b) < BLOCKER_CLEAR for b in bl):
            continue
        if any(seg_dist_xz(x, z, (c["a"][0], 0, c["a"][1]), (c["b"][0], 0, c["b"][1])) < 14.0 for c in m.get("cuts", [])):
            continue                             # cut lines (closures across open ground): nobody starts / spawns / opens a box next to one
        cand.append(i)
    if len(cand) < 40:
        sys.exit(f"{key}: only {len(cand)} spawn candidates on the navmesh")
    print(f"{key}: {len(cand)} spawn candidates of {len(nav.polys)} polys")
    cset = set(cand)
    allx = [nav.cen[i][0] for i in cand]
    allz = [nav.cen[i][2] for i in cand]
    mid = (sum(allx) / len(allx), sum(allz) / len(allz))
    # team anchors: scan candidate pairs coarsely (every 3rd), score = |path - 95| + 0.15 * (nothing near the middle)
    sample = cand[::max(1, len(cand) // 220)]
    best = None
    dcache = {}
    # path range between the team starts: spec "team_path" [min, max]; small-team maps (max_team <= 3) 60-90, default 80-110
    lo_p, hi_p = m.get("team_path") or ([60.0, 90.0] if (m.get("max_team") or 4) <= 3 else [80.0, 110.0])
    mid_p = (lo_p + hi_p) / 2
    pairs = []
    for a in sample:
        d = nav.dijkstra(a)
        dcache[a] = d
        for b in sample:
            if b <= a or b not in d:
                continue
            pd = d[b]
            if not lo_p <= pd <= hi_p or math.dist(nav.cen[a], nav.cen[b]) < 0.6 * pd:
                continue
            # prefer the pair that spans the map (sum of distances from the centre) and sits near the middle of the range
            span = math.hypot(nav.cen[a][0] - mid[0], nav.cen[a][2] - mid[1]) + math.hypot(nav.cen[b][0] - mid[0], nav.cen[b][2] - mid[1])
            straight = math.dist(nav.cen[a], nav.cen[b])
            score = abs(pd - mid_p) * 0.5 - span * 0.5 - straight * 1.0
            pairs.append((score, a, b, pd))
            if best is None or score < best[0]:
                best = (score, a, b, pd)
    if len(pairs) > 1:
        # the best-scoring pairs go through the layout screen (nav_layout.py): prefer a pair with 2+ independent routes and a wide throat
        import nav_layout
        pairs.sort()
        top, seen = [], []
        for pr in pairs:
            if all(math.dist(nav.cen[pr[1]], nav.cen[q[1]]) > 25 or math.dist(nav.cen[pr[2]], nav.cen[q[2]]) > 25 for q in top):
                top.append(pr)
            if len(top) == 8:
                break
        keep = {i for i in cand}
        rank = []
        for pr in top:
            try:
                r = nav_layout.screen(nav, set(range(len(nav.polys))) if not bnd else {i for i in range(len(nav.polys)) if bnd[0] <= nav.cen[i][0] <= bnd[1] and bnd[2] <= nav.cen[i][2] <= bnd[3]},
                                      [nav.cen[pr[1]]], [nav.cen[pr[2]]])
            except Exception:                      # (never block seeding on the screen)
                r = {"routes": 1, "throat": 0}
            rank.append((-(min(r["routes"], 3)), -min(r["throat"], 20.0), pr[0], pr))
        rank.sort(key=lambda t: t[:3])
        best = rank[0][3]
        print(f"{key}: screened {len(top)} team pairs, picked routes {-rank[0][0]} throat {-rank[0][1]:.0f} m")
    if best is None:
        # no pair within 80-110: take the longest path pair (small map) and say so
        far = (0, None, None)
        for a in sample:
            d = nav.dijkstra(a)
            for b in sample:
                if b in d and d[b] > far[0]:
                    far = (d[b], a, b)
        best = (0, far[1], far[2], far[0])
        print(f"{key}: NO team pair within 80-110 m by path; best {far[0]:.0f} m")
    _, a0, b0, pd = best
    print(f"{key}: team anchors {tuple(round(v) for v in nav.cen[a0])} and {tuple(round(v) for v in nav.cen[b0])}, path {pd:.0f} m")
    da, db = nav.dijkstra(a0), nav.dijkstra(b0)

    def team(anchor, d):
        pool = sorted((i for i in cand if d.get(i, 99) <= 8.0 and abs(nav.cen[i][1] - nav.cen[anchor][1]) < 1.2), key=lambda i: d[i])
        pick = []
        for i in pool:
            if all(math.dist(nav.cen[i], nav.cen[j]) >= 1.6 for j in pick):
                pick.append(i)
            if len(pick) == 4:
                break
        while len(pick) < 4:
            pick.append(pick[len(pick) % max(1, len(pick))])
        return pick

    t0, t1 = team(a0, da), team(b0, db)
    cen3 = (mid[0], 0, mid[1])

    def facing(i):
        c = nav.cen[i]
        return _yaw_quat(math.atan2(mid[0] - c[0], mid[1] - c[2]))

    intro = t0 + t1
    dist_to_intro = {}
    for a in (a0, b0):
        for i, v in (da if a == a0 else db).items():
            dist_to_intro[i] = min(dist_to_intro.get(i, 1e9), v)
    # respawns: ring by farthest point sampling on path distance, away from intros
    picks = []
    pool = [i for i in cand if dist_to_intro.get(i, 0) >= 14.0 and all(math.dist(nav.cen[i], nav.cen[j]) >= 12.0 for j in intro)]
    have = {}
    for i in (a0, b0):
        have[i] = nav.dijkstra(i)
    cur = {i: min(have[a0].get(i, 1e9), have[b0].get(i, 1e9)) for i in pool}
    while pool and len(picks) < 13:
        nxt = max(pool, key=lambda i: min(cur[i], 1e9))
        if cur[nxt] < 9.0 and len(picks) >= 8:
            break
        picks.append(nxt)
        d = nav.dijkstra(nxt)
        have[nxt] = d
        for i in pool:
            cur[i] = min(cur[i], d.get(i, 1e9))
        pool = [i for i in pool if math.dist(nav.cen[i], nav.cen[nxt]) >= 8.0]
    resp = picks
    # boxes: from the remaining candidates, 10+ m from every respawn and 12+ m from intros
    rp = set(resp)
    bpool = [i for i in cand if i not in rp and all(math.dist(nav.cen[i], nav.cen[j]) >= 10.0 for j in resp)
             and all(math.dist(nav.cen[i], nav.cen[j]) >= 12.0 for j in intro)]
    boxes = []
    near0 = sorted((i for i in bpool if 15.0 <= da.get(i, 99) <= 28.0), key=lambda i: abs(da[i] - 20.0))
    near1 = sorted((i for i in bpool if 15.0 <= db.get(i, 99) <= 28.0), key=lambda i: abs(db[i] - 20.0))
    for lst in (near0, near1):
        if lst:
            boxes.append(lst[0])
    bpool = [i for i in bpool if all(math.dist(nav.cen[i], nav.cen[j]) >= 14.0 for j in boxes)]
    # neutral boxes: prefer mid path (both teams 25+ m away) and mutually far; relax the separation until 6 are found
    for sep in (18.0, 14.0, 10.0, 7.0, 5.0):
        neut = [i for i in bpool if 25.0 <= da.get(i, 0) <= pd * 0.9 and 25.0 <= db.get(i, 0) <= pd * 0.9 and abs(da[i] - db[i]) <= 0.3 * max(da[i], db[i]) and all(math.dist(nav.cen[i], nav.cen[k]) >= sep for k in boxes)]
        while neut and len(boxes) < 6:
            j = max(neut, key=lambda i: min(math.dist(nav.cen[i], nav.cen[k]) for k in boxes) if boxes else 0)
            boxes.append(j)
            neut = [i for i in neut if math.dist(nav.cen[i], nav.cen[j]) >= sep]
        if len(boxes) >= 6:
            break
    if len(boxes) < 6:       # last resort: any free spot, mid-path first
        rest = sorted((i for i in bpool if all(math.dist(nav.cen[i], nav.cen[k]) >= 10.0 for k in boxes)), key=lambda i: abs(da.get(i, 999) - db.get(i, 999)) + 0.3 * max(da.get(i, 999), db.get(i, 999)))
        for j in rest:
            if len(boxes) >= 6:
                break
            if all(math.dist(nav.cen[j], nav.cen[k]) >= 10.0 for k in boxes):
                boxes.append(j)
    if len(boxes) < 6:
        print(f"{key}: only {len(boxes)} boxes fit the rules")

    def sp_(i):
        return {"pos": [round(c, 3) for c in nav.cen[i]], "quat": facing(i)}

    out = {"_note": "NAV-SEEDED placeholder spawns (tools/maps/nav_plan.py seed): centroids of walkable polygons, 4+4 intros "
                    f"{pd:.0f} m apart by path, ring of respawns, boxes 2 per side + neutral - replace / tune in game",
           "player": sp_(t0[0]), "intro0": [sp_(i) for i in t0], "intro1": [sp_(i) for i in t1],
           "respawns": [sp_(i) for i in resp]}
    while len(out["respawns"]) < 13:                      # the pak has 13 respawn slots
        out["respawns"].append(dict(out["respawns"][len(out["respawns"]) % max(1, len(resp))]))
    out["boxes"] = [{"pos": [round(c, 3) for c in nav.cen[i]], "quat": [0.0, 0.0, 0.0, 1.0]} for i in boxes]
    print(f"{key}: {len(resp)} respawns, {len(boxes)} boxes")
    if write:
        json.dump(out, open(os.path.join(DATA, f"{key}-spawns.json"), "w"), indent=1)
        print(f"{key}: wrote tools/maps/data/{key}-spawns.json (run sp_maps.py pak {key})")
    return out


# ------------------------------------------------------------------ No Return arenas: NoR's own start / spawn data
NOR_START = ("rogue-player-spawner", "player-assault-spawn", "cp-player-start", "cp-street-patrol")
NOR_PRIMARY = ("rogue-player-spawner", "player-assault-spawn")
NOR_ENEMY = ("position-all-enemy-safe-spawn",)
NOR_LOOT = ("rogue-lockbox-spawner",)


def seed_nor(key, write=False):
    """Spawns from No Return's own data (the t2r-*-script levels' spawners, read offline from re/maps/seeds/<key>.json):
      team 0 = NoR's player starts (rogue-player-spawner x4 / player-assault-spawn x4: where NoR puts the player),
      team 1 = the 4 enemy-safe-spawn points around the NoR point farthest from it by path (where the waves come from),
      respawns = NoR's start + enemy safe-spawn positions (farthest-point sampling, 8 m apart), topped up on the navmesh,
      boxes = NoR's lockbox spawners (rl-cache-crate-military loot crates), topped up on the navmesh.
    Everything NoR provides is used as is; only gaps are filled from nav polygons."""
    m = load_spec(key)
    nav = Nav(load_nav(key))
    bnd = m.get("bounds")
    pts = json.load(open(os.path.join(SEEDS, f"{key}.json")))

    def sel(names):
        out, seen = [], set()
        for p in pts:
            if not any(p["name"].startswith(n) for n in names) or p.get("type") == "ItemPickup":
                continue
            x, y, z = p["pos"]
            if bnd and not (bnd[0] <= x <= bnd[1] and bnd[2] <= z <= bnd[3]):
                continue
            k = tuple(round(v, 1) for v in p["pos"])
            if k in seen:
                continue
            seen.add(k)
            out.append(tuple(p["pos"]))
        return out

    starts, enemy, loot = sel(NOR_START), sel(NOR_ENEMY), sel(NOR_LOOT)
    print(f"{key}: NoR data inside the bounds: {len(starts)} player starts, {len(enemy)} enemy safe spawns, {len(loot)} lockboxes")
    if not starts:
        sys.exit(f"{key}: no NoR player start in the seeds")
    comp, sizes = nav.components()

    def poly(p):
        return nav.poly_at(p[0], p[1], p[2], dy=2.5)

    def in_bounds(q):
        return not bnd or (bnd[0] <= q[0] <= bnd[1] and bnd[2] <= q[2] <= bnd[3])

    def around(c, n, taken=()):
        i0 = poly(c)
        near = sorted((i for i in range(len(nav.polys)) if i0 is not None and comp[i] == comp[i0] and nav.area[i] >= 1.0
                       and abs(nav.cen[i][1] - c[1]) < 1.2 and nav.edge_clear(nav.cen[i][0], nav.cen[i][2]) >= 0.8),
                      key=lambda i: math.dist(nav.cen[i], c))
        out = []
        for i in near:
            q = nav.cen[i]
            if all(math.dist(q, t) >= 1.6 for t in list(taken) + out) and math.dist(q, c) <= 8.0:
                out.append(q)
            if len(out) == n:
                break
        return out

    # the primary starts (rogue-player-spawner / player-assault-spawn) are where NoR puts the player; cp-* are scripted checkpoints
    prim = sel(NOR_PRIMARY) if sel(NOR_PRIMARY) else starts
    anchor0 = prim[0]
    ia = poly(anchor0)
    if ia is None:
        sys.exit(f"{key}: the NoR player start {anchor0} is not on the loaded navmesh")
    da = nav.dijkstra(ia)
    t0 = [anchor0] + [p for p in prim[1:] if poly(p) in da and da[poly(p)] <= 12.0]
    t0 = t0[:4]
    if len(t0) < 4:
        t0 += around(anchor0, 4 - len(t0), t0)
    # team 1's anchor: a NoR point (other primary starts, enemy safe spawns) 60-110 m away by path, else the reachable one
    # with the longest path (small arenas), else a navmesh polygon 80-110 m away (NoR gives no far-side point)
    pool = [p for p in prim + enemy if poly(p) in da and math.dist(p, anchor0) > 20.0]
    pool_nav = [nav.cen[i] for i in range(len(nav.polys)) if i in da and nav.area[i] >= 1.2 and in_bounds(nav.cen[i])
                and nav.edge_clear(nav.cen[i][0], nav.cen[i][2]) >= 1.0 and 80.0 <= da[i] <= 110.0]
    ok = [p for p in pool if 60.0 <= da[poly(p)] <= 110.0]
    if ok:
        base1 = max(ok, key=lambda p: math.dist(p, anchor0))
    elif pool_nav:
        base1 = max(pool_nav, key=lambda p: math.dist(p, anchor0))
    elif pool:
        base1 = max(pool, key=lambda p: da[poly(p)])
    else:
        sys.exit(f"{key}: no point to put team 1")
    i1 = poly(base1)
    pd = da[i1]
    t1 = []
    for p in sorted((p for p in enemy + prim if poly(p) is not None and math.dist(p, base1) <= 9.0), key=lambda p: math.dist(p, base1)):
        if all(math.dist(p, q) >= 1.6 for q in t1):
            t1.append(p)
        if len(t1) == 4:
            break
    if len(t1) < 4:
        t1 += around(base1, 4 - len(t1), t1)
    t1 = t1[:4]
    c0 = anchor0
    print(f"{key}: team 0 around {tuple(round(v) for v in c0)}, team 1 around {tuple(round(v) for v in base1)}, path {pd:.0f} m")
    intro = t0 + t1
    boxes = []                       # NoR's own loot crates first (they are where NoR wants loot), spread >= 12 m, off the intros
    lp = [p for p in loot if all(math.dist(p, q) >= 10.0 for q in intro)]
    while lp and len(boxes) < 6:
        nxt = max(lp, key=lambda p: min([math.dist(p, q) for q in boxes] or [999]))
        boxes.append(nxt)
        lp = [p for p in lp if math.dist(p, nxt) >= 12.0]
    nor_box = len(boxes)
    picks = []
    pool = [p for p in enemy + starts if poly(p) is not None and all(math.dist(p, q) >= 10.0 for q in intro + boxes)]
    while pool and len(picks) < 13:
        nxt = max(pool, key=lambda p: min([math.dist(p, q) for q in picks + intro] or [999]))
        if min([math.dist(nxt, q) for q in picks + intro] or [999]) < 8.0:
            break
        picks.append(nxt)
        pool = [p for p in pool if math.dist(p, nxt) >= 8.0]
    nor_resp = len(picks)
    if len(picks) < 13:
        cand = [nav.cen[i] for i in range(len(nav.polys)) if comp[i] == comp[i1] and nav.area[i] >= 1.2
                and nav.edge_clear(nav.cen[i][0], nav.cen[i][2]) >= 1.0 and in_bounds(nav.cen[i])
                and all(math.dist(nav.cen[i], q) >= 10.0 for q in boxes)]
        while cand and len(picks) < 13:
            nxt = max(cand, key=lambda p: min([math.dist(p, q) for q in picks + intro] or [999]))
            if min([math.dist(nxt, q) for q in picks + intro] or [999]) < 8.0:
                break
            picks.append(nxt)
            cand = [p for p in cand if math.dist(p, nxt) >= 8.0]
    if len(boxes) < 6:
        cand = [nav.cen[i] for i in range(len(nav.polys)) if comp[i] == comp[i1] and nav.area[i] >= 1.2
                and nav.edge_clear(nav.cen[i][0], nav.cen[i][2]) >= 1.0 and in_bounds(nav.cen[i])
                and all(math.dist(nav.cen[i], q) >= 10.0 for q in picks) and all(math.dist(nav.cen[i], q) >= 12.0 for q in intro)]
        for sep in (14.0, 10.0, 7.0):
            cand = [p for p in cand if all(math.dist(p, q) >= sep for q in boxes)]
            while cand and len(boxes) < 6:
                nxt = max(cand, key=lambda p: min([math.dist(p, q) for q in boxes] or [999]))
                boxes.append(nxt)
                cand = [p for p in cand if math.dist(p, nxt) >= sep]
    mid = [sum(p[0] for p in intro) / 8, 0, sum(p[2] for p in intro) / 8]

    def sp_(p):
        return {"pos": [round(c, 3) for c in p], "quat": _yaw_quat(math.atan2(mid[0] - p[0], mid[2] - p[2]))}

    resp = [sp_(p) for p in picks]
    while len(resp) < 13:
        resp.append(dict(resp[len(resp) % max(1, len(picks))]))
    out = {"_note": "NoR-SEEDED spawns (nav_plan.py seed: No Return's own player starts / enemy safe spawns / lockboxes; gaps from "
                    "the navmesh) - tune in game", "player": sp_(t0[0]), "intro0": [sp_(p) for p in t0], "intro1": [sp_(p) for p in t1],
           "respawns": resp, "boxes": [{"pos": [round(c, 3) for c in p], "quat": [0.0, 0.0, 0.0, 1.0]} for p in boxes[:6]]}
    print(f"{key}: {len(picks)} respawns ({nor_resp} from NoR), {len(boxes[:6])} boxes ({min(nor_box, 6)} NoR lockboxes)")
    if write:
        json.dump(out, open(os.path.join(DATA, f"{key}-spawns.json"), "w"), indent=1)
        print(f"{key}: wrote tools/maps/data/{key}-spawns.json (run sp_maps.py pak {key})")
    return out


def main():
    a = sys.argv[1:]
    if len(a) < 2 or a[0] not in ("report", "seed", "layout"):
        print(__doc__)
        return
    if a[0] == "layout":                        # Factions layout screen (nav_layout.py): nav_plan.py layout <key> [<key>...] | --pool <name>
        import nav_layout
        nav_layout.run(a[2:], True) if a[1] == "--pool" else nav_layout.run(a[1:])
        return
    if a[0] == "report":
        report(a[1], a[a.index("--png") + 1] if "--png" in a else None)
    elif load_spec(a[1]).get("nor"):
        seed_nor(a[1], "--write" in a)
    else:
        seed(a[1], "--write" in a)


if __name__ == "__main__":
    main()
