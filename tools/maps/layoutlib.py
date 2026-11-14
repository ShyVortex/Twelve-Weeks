"""Shared pieces of the map-layout tools (tools/maps/layout.py, tools/tests/test_map_layouts.py):
layout loading, the navmesh occupancy grid (walkable ground, sight lines, clearances), the 2013-derived rules
(re/maps/layout-rules-2013.md) and the layout metrics / checks.

A "layout" = {"intro0": [4 x {pos, quat}], "intro1": [...], "respawns": [...], "boxes": [...], "player": {...}}, the same
shape as tools/maps/data/<key>-spawns.json (consumed by sp_maps.py pak / make_map_pak.ps1).

No collision geometry is available offline, so "sight line" and "walkable" come from the navmesh (see Grid.los).
"""
import heapq
import json
import math
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.dirname(HERE)
ROOT = os.path.dirname(TOOLS)
sys.path.insert(0, HERE)
import nav_plan  # noqa: E402
import layoutenv as E  # noqa: E402
import layoutwalk as W  # noqa: E402

SEEDS = os.path.join(ROOT, "re", "maps", "seeds")
DATA = os.path.join(HERE, "data")
LAYOUTS = os.path.join(HERE, "layouts")
SPAWNS = os.path.join(TOOLS, "spawns")
SPEC = os.path.join(HERE, "sp_maps.json")

# pool (No Return based, hand placed) maps: key -> (level, nav seed name, max_team fallback)
POOL = {
    "forest": ("to1-forest", "forest", 4),
    "gas-station": ("to1-gas-station", "gas-station", 2),
    "school": ("to1-school", "school", 2),
    "shipyard": ("to1-shipyard", "shipyard", 4),
    "resort": ("to1-resort", "resort", 4),
    "seraphite-camp": ("to1-seraphite-camp", "seraphite-camp", 3),
    "rescue-jesse-houses": ("to1-jesse-houses", "houses", 4),
    "hospital": ("to1-custom-map-1", "hospital", 3),
}

# ---------------------------------------------------------------------------------------------- rules (layout-rules-2013.md)
# Every number is tagged with its evidence class in the document: E = read from the 2013 scripts, W = 2013 wiki text,
# P = measured on the hand-placed pool maps (audit), D = design choice.
RULES = {
    "intro_group_min": 1.3,        # P  min spacing inside a team start (pool: 1.5-3.2 m)
    "intro_group_max": 7.0,        # P  max distance of an intro spawn from its group centre
    "intro_enemy_min": 45.0,       # P+D straight distance between the team starts (design-rules 1: 45+ even on the smallest pool maps)
    "intro_path_range": (60.0, 125.0),   # D  path distance, small maps (max_team <= 3) may be 60-90
    "intro_fwd_clear": 4.0,        # D  walkable run in front (the crouch-walk covers ~3 m, intro camera "walk forward")
    "intro_back_clear": 3.0,       # D  room behind for the wide shot (BACK 5-6.8 m, spring arm shrinks it)
    "intro_facing_deg": 80.0,      # D  facing within this angle of the route to the enemy start
    "respawn_min_gap": 8.0,        # P  closest pair of respawns (design 8-10 m; ext picker keeps 12 m between live players)
    "respawn_intro_min": 12.0,     # P  respawn to any intro spawn (sp_maps.py seed uses 12 m)
    "respawn_edge_clear": 0.8,     # D  from the nav boundary (walls, drops)
    "respawn_los_enemy": 45.0,     # E1 the picker's LOS radius: a respawn must not see an enemy start group within this
    "respawn_cover_r": 28.0,       # D  coverage radius (path m): every walkable spot within this of some respawn
    "respawn_cover_min": 0.88,     # D  share of the walkable area covered
    "respawn_side_balance": 2,     # E1 home-side count difference (flip logic needs both sides populated)
    "start_balance": (0.35, 0.65), # D  share of the walkable area nearer (by path) to team 0 than to team 1: equal opportunities
    "box_min": 4,                  # E4 "4 or more regions visited" is the top threshold of the box script
    "box_edge_clear": 1.2,         # D  crate needs room to open
    "box_resp_min": 10.0,          # D  design-rules 7: never on / next to a respawn
    "box_box_min": 12.0,           # D
    "box_side_path": (12.0, 40.0), # D  one box near each team start (path m)
    "box_side_ratio": 0.75,        # D  a side box is at least this much closer to its own team
}


def maxteam(key):
    """max players per team (daemon.max_team_table); fallback: pool table / spec"""
    lvl = (POOL.get(key) or (None,))[0]
    try:
        spec = {m["key"]: m for m in json.load(open(SPEC, encoding="utf-8"))["maps"]}
        if key in spec:
            return int(spec[key].get("max_team") or 4)
    except (OSError, ValueError):
        pass
    return POOL[key][2] if key in POOL else 4


def spec_of(key):
    try:
        return [m for m in json.load(open(SPEC, encoding="utf-8"))["maps"] if m["key"] == key][0]
    except (OSError, IndexError, ValueError):
        return {}


def floor_index(spec, pos):
    """index of the map spec's `floors` entry (multi-floor maps: a named upper floor / roof = a y band, optionally inside a rectangle
    [x0, x1, z0, z1]) that holds `pos`, else -1. Entries carry the per-floor quotas "respawns" / "boxes" (minimum counts)."""
    for k, f in enumerate(spec.get("floors") or []):
        r = f.get("rect")
        if r and not (r[0] <= pos[0] <= r[1] and r[2] <= pos[2] <= r[3]):
            continue
        if f["y"][0] <= pos[1] <= f["y"][1]:
            return k
    return -1


def keys_in_rotation():
    """pool maps + the built SP-section maps (build true)"""
    specs = json.load(open(SPEC, encoding="utf-8"))["maps"]
    swapped = os.environ.get("T2R_HOSPITAL_OLD", "") != "1" and any(m.get("replaces") == POOL["hospital"][0] and m.get("build") for m in specs)
    ks = [k for k in POOL if not (swapped and k == "hospital")]      # the NoR hospital is replaced by hospital-ellie (T2R_HOSPITAL_OLD=1 = the old one)
    for m in specs:
        if m.get("replaces") and os.environ.get("T2R_HOSPITAL_OLD", "") == "1":
            continue
        if m.get("build") and m["key"] not in ks:
            ks.append(m["key"])
    return ks


# ---------------------------------------------------------------------------------------------- loading
def _quat_yaw(q):
    x, y, z, w = q
    # forward (+z) rotated by q, projected
    fx = 2 * (x * z + w * y)
    fz = 1 - 2 * (x * x + y * y)
    return math.atan2(fx, fz)


def yaw_quat(yaw):
    return [0.0, round(math.sin(yaw / 2), 6), 0.0, round(math.cos(yaw / 2), 6)]


def facing(p):
    return _quat_yaw(p["quat"])


def pool_pak(key):
    return os.path.join(TOOLS, "features", "levels", f"to1-pvp-{key}-ingame.pak")


def _pak_hash(pak):
    import hashlib
    return hashlib.sha1(open(pak, "rb").read()).hexdigest()


def pool_spawners(key, redump=None):
    """the spawner list of a pool map, always from the committed pak: tools/spawns/<key>.json is a gitignored cache of it,
    stamped with the pak's sha1 (<key>.json.sha1); a missing / mismatching stamp re-dumps it (dump_json.ps1) - a stale dump never
    reaches a result. redump: test hook, called as redump(pak, out) instead of the powershell dumper."""
    import subprocess
    pak, out = pool_pak(key), os.path.join(SPAWNS, f"{key}.json")
    stamp = out + ".sha1"
    h = _pak_hash(pak)
    cur = open(stamp).read().strip() if os.path.exists(stamp) else None
    if cur != h or not os.path.exists(out):
        if redump:
            redump(pak, out)
        else:
            subprocess.run(["pwsh", "-NoProfile", "-File", os.path.join(SPAWNS, "dump_json.ps1"), "-Pak", os.path.abspath(pak), "-Out", out],
                           check=True, stdout=subprocess.DEVNULL)
        open(stamp, "w").write(h)
    return json.load(open(out, encoding="utf-8-sig"))


def load_layout(key):
    """the layout as built into the pak: pool maps from tools/spawns/<key>.json (dump of the committed pak), SP maps from data"""
    if key not in POOL:
        p = os.path.join(DATA, f"{key}-spawns.json")
        d = json.load(open(p))
        d.pop("_note", None)
        return d
    sp = pool_spawners(key)
    by = {s["name"]: s for s in sp}

    def g(n):
        s = by[n]
        return {"pos": list(s["pos"]), "quat": list(s["quat"])}

    out = {"player": g("player") if "player" in by else None,
           "intro0": [g(f"to1-t0-intro-spawn-point-{i}") for i in range(1, 5)],
           "intro1": [g(f"to1-t1-intro-spawn-point-{i}") for i in range(1, 5)]}
    n = 1
    out["respawns"] = []
    while f"to1-spawn-point-{n}" in by:
        out["respawns"].append(g(f"to1-spawn-point-{n}"))
        n += 1
    out["boxes"] = []
    n = 1
    while f"to1-supplybox-{n}" in by:
        out["boxes"].append(g(f"to1-supplybox-{n}"))
        n += 1
    out["healthkits"] = [g(f"to1-healthkit-{i}") for i in range(1, 9) if f"to1-healthkit-{i}" in by]
    return out


def nav_file(key):
    if key in POOL:
        return os.path.join(SEEDS, f"pool-{POOL[key][1]}-nav.json")
    return os.path.join(SEEDS, f"{key}-nav.json")


def load_nav(key):
    p = nav_file(key)
    if not os.path.exists(p):
        return None
    d = json.load(open(p, encoding="utf-8-sig"))
    polys = []
    for lv, ps in d.items():
        for v in ps:
            polys.append(([tuple(x) for x in v], lv.replace("-ingame", "")))
    for q in spec_of(key).get("nav_stitch") or []:      # spec "nav_stitch": hand quads over a gap the navmeshes do not link (doorway / door-blocked nav); the walk must be verified in game
        polys.append(([tuple(x) for x in q], "stitch"))
    return polys


# ---------------------------------------------------------------------------------------------- navmesh grid
class Grid:
    """0.5 m occupancy grid of the navmesh: cell -> ground heights (one per floor). Used for sight lines and clearances."""
    CELL = 0.5
    xfloor = False                           # multi-floor maps (spec "floors"): sight lines also follow a floor under the line, see los

    def __init__(self, nav):
        self.nav = nav
        c = self.CELL
        self.cells = {}                      # (ix, iz) -> list of (y, poly)
        for pi, p in enumerate(nav.polys):
            pts = np.array(p, dtype=float)
            x0, x1 = pts[:, 0].min(), pts[:, 0].max()
            z0, z1 = pts[:, 2].min(), pts[:, 2].max()
            ix0, ix1 = int(math.floor(x0 / c)), int(math.floor(x1 / c))
            iz0, iz1 = int(math.floor(z0 / c)), int(math.floor(z1 / c))
            if (ix1 - ix0 + 1) * (iz1 - iz0 + 1) > 40000:
                continue                     # absurd polygon (a huge ground plane): skipped, the rest still covers
            xs = (np.arange(ix0, ix1 + 1) + 0.5) * c
            zs = (np.arange(iz0, iz1 + 1) + 0.5) * c
            gx, gz = np.meshgrid(xs, zs, indexing="ij")
            # fan triangles
            for k in range(1, len(pts) - 1):
                a, b, d = pts[0], pts[k], pts[k + 1]
                den = (b[2] - d[2]) * (a[0] - d[0]) + (d[0] - b[0]) * (a[2] - d[2])
                if abs(den) < 1e-9:
                    continue
                l1 = ((b[2] - d[2]) * (gx - d[0]) + (d[0] - b[0]) * (gz - d[2])) / den
                l2 = ((d[2] - a[2]) * (gx - d[0]) + (a[0] - d[0]) * (gz - d[2])) / den
                l3 = 1 - l1 - l2
                m = (l1 >= -1e-6) & (l2 >= -1e-6) & (l3 >= -1e-6)
                if not m.any():
                    continue
                gy = l1 * a[1] + l2 * b[1] + l3 * d[1]
                for i, j in zip(*np.nonzero(m)):
                    self.cells.setdefault((ix0 + int(i), iz0 + int(j)), []).append((float(gy[i, j]), pi))

    def ground(self, x, z, y, dy=1.6):
        """ground height at (x, z) nearest to y within dy; (y, poly) or None"""
        c = self.CELL
        L = self.cells.get((int(math.floor(x / c)), int(math.floor(z / c))))
        if not L:
            return None
        best = min(L, key=lambda t: abs(t[0] - y))
        return best if abs(best[0] - y) <= dy else None

    def walkable(self, x, z, y, dy=1.6):
        return self.ground(x, z, y, dy) is not None

    def run(self, p, yaw, length, step=0.5, dy=1.0):
        """walkable run from p along yaw (m of contiguous ground, heights followed)"""
        x, y, z = p
        fx, fz = math.sin(yaw), math.cos(yaw)
        d = 0.0
        while d < length:
            nx, nz = x + fx * step, z + fz * step
            g = self.ground(nx, nz, y, dy)
            if g is None:
                break
            x, z, y = nx, nz, g[0]
            d += step
        return d

    def los(self, a, b, eye=1.5, gap=2.5, step=0.5):
        """sight line from a to b (positions = feet) over the navmesh. Blocked when the line crosses `gap` m of off-nav
        ground (walls, buildings, obstacles: the navmesh has holes there) or the ground rises above the line (hills, stairs
        up to an upper floor). An approximation: no collision geometry offline; low cover is not seen as blocking."""
        ax, ay, az = a
        bx, by, bz = b
        d = math.hypot(bx - ax, bz - az)
        if d < 0.5:
            return True
        n = max(2, int(d / step))
        off = 0.0
        gy = ay
        for i in range(1, n):
            t = i / n
            x, z = ax + (bx - ax) * t, az + (bz - az) * t
            ry = ay + (by - ay) * t + eye
            g = self.ground(x, z, gy, 1.2)
            if g is None and self.xfloor:       # another floor under / over the line (a stair well or an opening across floors)
                g = self.ground(x, z, ry - eye, 1.2)
            if g is None:
                off += d / n
                if off >= gap:
                    return False
            else:
                off = 0.0
                gy = g[0]
                if g[0] + 1.0 > ry:        # ground (plus a 1 m body) above the sight line
                    return False
        return True


def build_nav(key):
    polys = load_nav(key)
    if polys is None:
        return None, None
    nav = nav_plan.Nav(polys)
    return nav, Grid(nav)


def dijkstra_pred(nav, src, limit=1e9):
    dist = {src: 0.0}
    pred = {}
    h = [(0.0, src)]
    while h:
        d, u = heapq.heappop(h)
        if d > dist.get(u, 1e18) or d > limit:
            continue
        for v, w in nav.adj[u].items():
            nd = d + w
            if nd < dist.get(v, 1e18):
                dist[v] = nd
                pred[v] = u
                heapq.heappush(h, (nd, v))
    return dist, pred


def path_points(nav, pred, dst, src):
    out = [dst]
    u = dst
    while u != src and u in pred:
        u = pred[u]
        out.append(u)
    return out[::-1]


def pdist(p, q):
    return math.dist(p["pos"], q["pos"])


def hdist(p, q):
    return math.hypot(p["pos"][0] - q["pos"][0], p["pos"][2] - q["pos"][2])


def centre(ps):
    return [sum(p["pos"][i] for p in ps) / len(ps) for i in range(3)]


def ang_diff(a, b):
    d = (a - b + math.pi) % (2 * math.pi) - math.pi
    return abs(d)


# ---------------------------------------------------------------------------------------------- measurement
def main_component(nav, bounds=None):
    comp, sizes = nav.components()
    big = max(range(len(sizes)), key=lambda k: sizes[k])
    return comp, big


class Ctx:
    """nav + grid + play space of one map, built once. Play space = the connected part of the navmesh (inside the bounds) that
    holds the team 0 start: spec bounds for the SP maps, placed points + 25 m for the pool maps (nav_layout.py does the same)."""

    def __init__(self, key, lay=None):
        self.key = key
        self.nav, self.grid = build_nav(key)
        self.spec = spec_of(key)
        if self.grid is not None and self.spec.get("floors"):
            self.grid.xfloor = True
            self.nav.multi = True
        lay = lay or load_layout(key)
        self.bounds = self.spec.get("bounds")
        if not self.bounds and key in POOL:
            pts = [p["pos"] for n in ("intro0", "intro1", "respawns", "boxes") for p in lay.get(n, [])]
            self.bounds = [min(p[0] for p in pts) - 25, max(p[0] for p in pts) + 25, min(p[2] for p in pts) - 25, max(p[2] for p in pts) + 25]
        self.rects = ([list(self.bounds)] + [list(r) for r in self.spec.get("bounds_extra", [])]) if self.bounds else []
        self.blockers = [p["pos"] for p in self.spec.get("props", []) if p.get("auto")]
        self.cuts = self.spec.get("cuts", [])
        self.play = set()
        self.comp = self.big = None
        if self.nav:
            nav = self.nav
            keep = {i for i in range(len(nav.polys)) if not self.bounds or self.inb(nav.cen[i][0], nav.cen[i][2])}
            for z in self.spec.get("dead_zones", []):       # ground the navmesh shows but players cannot get back onto (A/B: the market roof): not play space
                keep = {i for i in keep if not (z["rect"][0] <= nav.cen[i][0] <= z["rect"][1] and z["rect"][2] <= nav.cen[i][2] <= z["rect"][3]
                                                and z["y"][0] <= nav.cen[i][1] <= z["y"][1])}
            a = nav.poly_at(*lay["intro0"][0]["pos"], dy=3.0)
            if a is None or a not in keep:            # the seed start lies outside the bounds (a moved play area): the biggest connected part inside them
                best, done = (0.0, None), set()
                for s0 in keep:
                    if s0 in done:
                        continue
                    comp, st = {s0}, [s0]
                    while st:
                        u = st.pop()
                        for v in nav.adj[u]:
                            if v in keep and v not in comp:
                                comp.add(v)
                                st.append(v)
                    done |= comp
                    ar = sum(nav.area[i] for i in comp)
                    if ar > best[0]:
                        best = (ar, s0)
                a = best[1]
            seen, st = {a}, [a]
            while st:
                u = st.pop()
                for v in nav.adj[u]:
                    if v in keep and v not in seen:
                        seen.add(v)
                        st.append(v)
            self.play = seen

    def inb(self, x, z, m=0.0):
        """inside the play area: the map spec's rectangle `bounds` or one of its `bounds_extra` rectangles (m = tolerance)"""
        return any(r[0] - m <= x <= r[1] + m and r[2] - m <= z <= r[3] + m for r in self.rects) if self.rects else True

    def poly_at(self, pos):
        return self.nav.poly_at(*pos, dy=2.5) if self.nav else None

    def on_main(self, pos):
        return self.poly_at(pos) in self.play


def measure(key, lay, ctx=None):
    """all numbers the checks / reports use"""
    ctx = ctx or Ctx(key, lay)
    nav, grid = ctx.nav, ctx.grid
    m = {"key": key, "max_team": maxteam(key), "counts": {"intro0": len(lay["intro0"]), "intro1": len(lay["intro1"]),
                                                          "respawns": len(lay["respawns"]), "boxes": len(lay["boxes"])}}
    c0, c1 = centre(lay["intro0"]), centre(lay["intro1"])
    m["intro_straight"] = round(math.dist(c0, c1), 1)
    m["intro_spread"] = [round(max(math.dist(p["pos"], c) for p in lay[t]), 1) for t, c in (("intro0", c0), ("intro1", c1))]
    m["intro_min_gap"] = [round(min(pdist(p, q) for i, p in enumerate(lay[t]) for q in lay[t][i + 1:]), 2) for t in ("intro0", "intro1")]
    R = lay["respawns"]
    m["resp_min_gap"] = round(min((pdist(p, q) for i, p in enumerate(R) for q in R[i + 1:]), default=0), 1)
    intro = lay["intro0"] + lay["intro1"]
    m["resp_intro_min"] = round(min((pdist(p, q) for p in R for q in intro), default=0), 1)
    B = lay["boxes"]
    m["box_min_gap"] = round(min((pdist(p, q) for i, p in enumerate(B) for q in B[i + 1:]), default=0), 1)
    m["box_resp_min"] = round(min((pdist(p, q) for p in B for q in R), default=0), 1)
    m["box_intro_min"] = round(min((pdist(p, q) for p in B for q in intro), default=0), 1)
    m["box_on_resp"] = sum(1 for p in B if any(pdist(p, q) < 6.0 for q in R))
    m["box_near_resp"] = sum(1 for p in B if any(6.0 <= pdist(p, q) < RULES["box_resp_min"] for q in R))
    if nav is None:
        return m
    # on navmesh / main component / edge clearance
    off = []
    for nm in ("intro0", "intro1", "respawns", "boxes"):
        for k, p in enumerate(lay[nm]):
            i = ctx.poly_at(p["pos"])
            if i is None:
                off.append((nm, k, "off navmesh"))
            elif i not in ctx.play:
                off.append((nm, k, "not in the main walkable part"))
            elif nav.edge_clear(p["pos"][0], p["pos"][2], p["pos"][1]) < (0.25 if nm == "boxes" else 0.4):   # boxes stand against a wall (box_place.py: centre 0.32 m off the nav edge)
                off.append((nm, k, "%.1f m from the nav edge" % nav.edge_clear(p["pos"][0], p["pos"][2], p["pos"][1])))
    m["problems"] = off
    # path distances between the team starts
    a, b = ctx.poly_at(lay["intro0"][0]["pos"]), ctx.poly_at(lay["intro1"][0]["pos"])
    if a is not None and b is not None:
        da, pa = dijkstra_pred(nav, a)
        db, pb = dijkstra_pred(nav, b)
        m["intro_path"] = round(da.get(b, float("nan")), 1)
        m["start_balance"] = round(start_balance(ctx, a, b), 2)
    else:
        da = db = {}
    # LOS: team start vs team start, respawns vs both start groups
    m["intro_los"] = sum(1 for p in lay["intro0"] for q in lay["intro1"] if grid.los(p["pos"], q["pos"]) and pdist(p, q) < 120)
    seen = []
    for k, p in enumerate(R):
        n0 = any(grid.los(p["pos"], q["pos"]) and pdist(p, q) < RULES["respawn_los_enemy"] for q in lay["intro0"])
        n1 = any(grid.los(p["pos"], q["pos"]) and pdist(p, q) < RULES["respawn_los_enemy"] for q in lay["intro1"])
        if n0 or n1:
            seen.append((k + 1, "T0" if n0 else "", "T1" if n1 else ""))
    m["resp_seen_by_start"] = seen
    # home side counts (path)
    side = [0, 0, 0]
    for p in R:
        i = ctx.poly_at(p["pos"])
        if i is None:
            continue
        x, y = da.get(i, 1e9), db.get(i, 1e9)
        side[0 if x + 12 < y else 1 if y + 12 < x else 2] += 1
    m["resp_sides"] = side
    # intro facing & clearances
    fw, bk, face = [], [], []
    for t, ct, co in (("intro0", c0, c1), ("intro1", c1, c0)):
        for p in lay[t]:
            yw = facing(p)
            fw.append(round(grid.run(p["pos"], yw, 8.0), 1))
            bk.append(round(grid.run(p["pos"], yw + math.pi, 8.0), 1))
        tw = math.atan2(co[0] - ct[0], co[2] - ct[2])
        face.append(round(math.degrees(ang_diff(facing(lay[t][0]), tw))))
    m["intro_fwd_clear"] = fw
    m["intro_back_clear"] = bk
    m["intro_facing_off_deg"] = face
    # coverage (4 m sample of the main component, polygon centroids weighted by area)
    cov = coverage(ctx, [ctx.poly_at(p["pos"]) for p in R], RULES["respawn_cover_r"])
    m["resp_cover"] = round(cov, 3)
    # boxes by path
    bx = []
    for p in B:
        i = ctx.poly_at(p["pos"])
        bx.append((round(da.get(i, -1)), round(db.get(i, -1))) if i is not None else None)
    m["box_path"] = bx
    m["walk_area"] = round(sum(nav.area[i] for i in ctx.play))
    if ctx.spec.get("floors"):                 # per-floor counts (upper floors / roofs of the map spec's `floors`)
        m["floors"] = []
        for k, f in enumerate(ctx.spec["floors"]):
            rc = f.get("rect")
            m["floors"].append({"name": f["name"], "respawns": sum(1 for p in R if floor_index(ctx.spec, p["pos"]) == k),
                                "boxes": sum(1 for p in B if floor_index(ctx.spec, p["pos"]) == k),
                                "intros": sum(1 for p in lay["intro0"] + lay["intro1"] if floor_index(ctx.spec, p["pos"]) == k),
                                "area": round(sum(nav.area[i] for i in ctx.play if f["y"][0] <= nav.cen[i][1] <= f["y"][1] and
                                                  (not rc or (rc[0] <= nav.cen[i][0] <= rc[1] and rc[2] <= nav.cen[i][2] <= rc[3])))),
                                "need_respawns": int(f.get("respawns", 0)), "need_boxes": int(f.get("boxes", 0))})
    return m


def start_balance(ctx, p0, p1):
    """share of the walkable area (area weighted polygons of the play space) that is nearer to team 0's start than to team 1's"""
    nav = ctx.nav
    d0, _ = dijkstra_pred(nav, p0)
    d1, _ = dijkstra_pred(nav, p1)
    a0 = tot = 0.0
    for i in ctx.play:
        tot += nav.area[i]
        if d0.get(i, 1e9) < d1.get(i, 1e9):
            a0 += nav.area[i]
    return a0 / tot if tot else 0.5


def coverage(ctx, polys, radius):
    nav = ctx.nav
    src = [i for i in polys if i is not None]
    if not src:
        return 0.0
    best = {}
    for s in src:
        d, _ = dijkstra_pred(nav, s, radius + 1)
        for u, v in d.items():
            if v < best.get(u, 1e9):
                best[u] = v
    tot = cov = 0.0
    for i in ctx.play:
        tot += nav.area[i]
        if best.get(i, 1e9) <= radius:
            cov += nav.area[i]
    return cov / tot if tot else 0.0


# ---------------------------------------------------------------------------------------------- checks
def check(key, lay, ctx=None, strict=True):
    """-> (errors, warnings, metrics). strict: hand placed pool maps only get warnings for soft rules."""
    ctx = ctx or Ctx(key, lay)
    m = measure(key, lay, ctx)
    R = RULES
    err, warn = [], []
    mt = m["max_team"]
    cnt = m["counts"]
    if cnt["intro0"] != 4 or cnt["intro1"] != 4:
        err.append(f"intro spawns {cnt['intro0']}+{cnt['intro1']} (need 4+4)")
    if cnt["respawns"] < 2 * mt + 4:
        warn.append(f"only {cnt['respawns']} respawns for max_team {mt} (rule: >= {2 * mt + 4})")
    if cnt["boxes"] < R["box_min"]:
        err.append(f"only {cnt['boxes']} supply boxes (rule: >= {R['box_min']})")
    if cnt["respawns"] > 32:
        err.append(f"{cnt['respawns']} respawns (the ext's spawn picker holds 32)")
    elif cnt["respawns"] > 16:
        warn.append(f"{cnt['respawns']} respawns: more than the 16 the pool maps were played with (the picker holds 32)")
    if cnt["boxes"] > 12:
        err.append(f"{cnt['boxes']} supply boxes (winmm's box table holds 12)")
    if m["intro_straight"] < R["intro_enemy_min"]:
        warn.append(f"team starts only {m['intro_straight']} m apart")
    if min(m["intro_min_gap"]) < R["intro_group_min"]:
        err.append(f"intro spawns {min(m['intro_min_gap'])} m apart in one group (need >= {R['intro_group_min']})")
    if max(m["intro_spread"]) > R["intro_group_max"]:
        warn.append(f"intro group spread {max(m['intro_spread'])} m")
    if m["resp_min_gap"] < R["respawn_min_gap"]:
        (warn if not strict else err).append(f"two respawns {m['resp_min_gap']} m apart (rule >= {R['respawn_min_gap']})")
    if m["resp_intro_min"] < R["respawn_intro_min"]:
        (warn if not strict else err).append(f"a respawn {m['resp_intro_min']} m from an intro spawn (rule >= {R['respawn_intro_min']})")
    if m["box_on_resp"]:
        (warn if not strict else err).append(f"{m['box_on_resp']} supply boxes within 6 m of a respawn")
    if m["box_near_resp"] and strict:
        warn.append(f"{m['box_near_resp']} supply boxes 6-{R['box_resp_min']:.0f} m from a respawn (accepted inside buildings)")
    if m["box_min_gap"] < R["box_box_min"] * 0.5:
        warn.append(f"two supply boxes {m['box_min_gap']} m apart")
    if ctx.nav is None:
        warn.append("no navmesh seed (re/maps/seeds): reachability, sight lines and coverage not checked")
        return err, warn, m
    for nm, k, why in m["problems"]:
        err.append(f"{nm}[{k}]: {why}")
    if strict and key not in POOL:
        mut = W.mutual_region(ctx)
        oneway = [f"{nm}{k + 1}" for nm in ("intro0", "intro1", "respawns", "boxes") for k, p in enumerate(lay[nm]) if ctx.poly_at(p["pos"]) not in mut]
        if oneway:
            err.append("on one-way ground (a ledge you can drop from but not climb back): " + ", ".join(oneway))
        sb = ctx.spec.get("bounds")
        if sb:
            outb = [f"{nm}{k + 1}" for nm in ("intro0", "intro1", "respawns", "boxes") for k, p in enumerate(lay[nm])
                    if not ctx.inb(p["pos"][0], p["pos"][2], 3.0)]
            if outb:
                err.append("outside the play area (spec bounds): " + ", ".join(outb))
    # floor: a box floats when its footprint is not flat or its Y is above the snapped floor (strict maps: errors)
    fl = []
    fixed = [fb["pos"] for fb in (ctx.spec.get("fixed_boxes") or [])]
    for k, p in enumerate(lay["boxes"]):
        if any(abs(p["pos"][0] - f[0]) < 0.05 and abs(p["pos"][2] - f[2]) < 0.05 for f in fixed):
            continue                           # a hand placed F8 mark: its Y is the floor the placer stood on
        up = p["pos"][1] - E.snap_y(ctx.grid, p["pos"])
        fat = E.flat(ctx.grid, p["pos"])
        if up > 0.05:
            fl.append(f"B{k + 1} ({up:+.2f} m above the snapped floor, ground varies {fat:.2f} m)")
    if fl:
        (err if strict else warn).append("supply boxes floating: " + ", ".join(fl))
    ints = E.interiors(ctx, os.path.join(SEEDS, (f"pool-{POOL[key][1]}" if key in POOL else key) + ".json"))
    if ints and ints[0]["area"] >= 150:
        if not any(E.in_interior(ints[0], p["pos"], 1.5) for p in lay["boxes"]):
            (err if strict else warn).append("no supply box inside the main interior (%.0f m2 around %.0f, %.0f)" % (
                ints[0]["area"], ints[0]["centre"][0], ints[0]["centre"][2]))
    inside = E.interior_index(ints)
    m["inside"] = {"boxes": [sum(1 for p in lay["boxes"] if inside(p["pos"]) >= 0), len(lay["boxes"])],
                   "respawns": [sum(1 for p in lay["respawns"] if inside(p["pos"]) >= 0), len(lay["respawns"])]}
    m["main_interior"] = [round(ints[0]["area"]), [round(v) for v in ints[0]["centre"]]] if ints else None
    open_boxes = [k + 1 for k, p in enumerate(lay["boxes"]) if E.cover(ctx.grid, p["pos"]) == 0]
    if len(open_boxes) > len(lay["boxes"]) // 3:
        warn.append(f"supply boxes in open field (no cover within 3 m): B{', B'.join(map(str, open_boxes))}")
    m["box_cover"] = [E.cover(ctx.grid, p["pos"]) for p in lay["boxes"]]
    if m["intro_los"] and strict:
        err.append(f"the team starts see each other ({m['intro_los']} pairs, nav sight line)")
    elif m["intro_los"]:
        warn.append(f"the team starts see each other ({m['intro_los']} pairs, nav sight line)")
    if m["resp_seen_by_start"]:
        (err if ctx.spec.get("respawn_hide") else warn).append("respawns in sight of a team start group (nav sight line, <45 m): " + ", ".join(
            f"R{k}" + ("/T0" if a else "") + ("/T1" if b else "") for k, a, b in m["resp_seen_by_start"]))
    if min(m["intro_fwd_clear"]) < R["intro_fwd_clear"]:
        warn.append(f"an intro spawn has only {min(m['intro_fwd_clear'])} m of walkable ground ahead")
    if max(m["intro_facing_off_deg"]) > R["intro_facing_deg"]:
        warn.append(f"an intro group faces {max(m['intro_facing_off_deg'])} deg off the other team")
    if m["resp_cover"] < R["respawn_cover_min"]:
        warn.append(f"respawns cover {m['resp_cover']:.0%} of the walkable area within {R['respawn_cover_r']:.0f} m (rule >= {R['respawn_cover_min']:.0%})")
    if not R["start_balance"][0] <= m.get("start_balance", 0.5) <= R["start_balance"][1]:
        warn.append(f"start positions unbalanced: {m['start_balance']:.0%} of the map is nearer team 0 (rule {R['start_balance'][0]:.0%}-{R['start_balance'][1]:.0%})")
    for f in m.get("floors", []):              # per-floor quotas (spec "floors"): spawns and supply boxes on the upper floors too
        if f["respawns"] < f["need_respawns"]:
            err.append(f"floor '{f['name']}': {f['respawns']} respawns (quota {f['need_respawns']})")
        if f["boxes"] < f["need_boxes"]:
            err.append(f"floor '{f['name']}': {f['boxes']} supply boxes (quota {f['need_boxes']})")
    s0, s1, sm = m["resp_sides"]
    if abs(s0 - s1) > R["respawn_side_balance"]:
        warn.append(f"respawn home sides unbalanced: T0 {s0} / T1 {s1} / middle {sm}")
    return err, warn, m
