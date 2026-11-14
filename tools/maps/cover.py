"""Made-up cover props for a built SP-section map (Jackson Suburbs needs more cover; it must not look like random junk).

  python cover.py plan <key> [--write] [--pak]   # analyse the map, list / draw the props (previews in re/maps/preview/<key>-cover*.png);
                                                 # --write puts them into sp_maps.json ("cover": true entries), --pak rebuilds the spawner pak

Palette = the level's own art that is known to have collision (actor97 paks with COLLISION_DATA_FOREGROUND, measured in tools/maps/data/prop_bounds.json and
already used as the map's boundary dressing, map spec blocker_style jackson-wood): station-wagon-a, san-wood-crate-1x1-blocker-stacked-a, blocker-wood-planks-a.
Placement rules (every prop carries its justification in the map spec, key "why"):
  station wagon  = fills a free slot of an EXISTING parked row: the level's car markers (poi-suburbs-car-N) sit in holes of the navmesh = a car is baked there;
                   the row's axis = the principal axis of that hole's outline; a slot is one car length (6 m) further along the axis; same orientation as its neighbours
  crate pair     = by a wall / house front: 2 stacked crates side by side, back to the nearest navmesh edge (wall), 1 m clear behind them, aligned to the wall
  plank barricade= across a lane of 4.5-8.5 m width (the WLF / Jackson boarded barricade of the level's own boundary dressing), a walkable gap each side
  and for all: on flat ground (footprint spread <= 8 cm / 15 cm for a car), 0.9 m of walkable ground around, >= 3 m from doors / windows, >= 2.5 m from a house
  floor, not in front of a box / on a start / respawn, the map stays connected (grid flood fill from the team 0 start reaches the other start, every box, every respawn).
  Priority = the long sight lines of the play area (nav sight line >= 35 m): a prop that breaks the most of the remaining lines wins, and each box that stands in the open
  gets a crate pair 3-5 m to the side its longest incoming line comes from.
"""
import json
import math
import os
import random
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import layoutlib as L  # noqa: E402
import layoutenv as E  # noqa: E402
import layoutwalk as W  # noqa: E402
from layoutlib import Ctx, yaw_quat  # noqa: E402

PB = json.load(open(os.path.join(HERE, "data", "prop_bounds.json")))
SPEC = L.SPEC
PREV = os.path.join(L.ROOT, "re", "maps", "preview")
ART = {"wagon": "station-wagon-a", "crate": "san-wood-crate-1x1-blocker-stacked-a", "planks": "blocker-wood-planks-a"}
FLAT = {"wagon": 0.20, "crate": 0.10, "planks": 0.15}      # navmesh spread under the footprint; a prop sits on the LOWEST point (sinks, never floats)


def local_box(art):
    b = PB[art]
    return b["min"][0], b["max"][0], b["min"][2], b["max"][2], b["max"][1]


def rot(x, z, yaw):
    c, s = math.cos(yaw), math.sin(yaw)
    return x * c + z * s, -x * s + z * c


def centre_of(art, pos, yaw):
    x0, x1, z0, z1, _ = local_box(art)
    dx, dz = rot((x0 + x1) / 2, (z0 + z1) / 2, yaw)
    return pos[0] + dx, pos[2] + dz


def pos_for(art, centre, yaw):
    """spawner position that puts the prop's footprint centre at `centre`"""
    x0, x1, z0, z1, _ = local_box(art)
    dx, dz = rot((x0 + x1) / 2, (z0 + z1) / 2, yaw)
    return centre[0] - dx, centre[1], centre[2] - dz


def corners(art, centre, yaw, grow=0.0):
    x0, x1, z0, z1, _ = local_box(art)
    hw, hl = (x1 - x0) / 2 + grow, (z1 - z0) / 2 + grow
    out = []
    for sx, sz in ((-1, -1), (1, -1), (1, 1), (-1, 1)):
        dx, dz = rot(sx * hw, sz * hl, yaw)
        out.append((centre[0] + dx, centre[1] + dz))
    return out


def inside_rect(art, centre, yaw, p, grow=0.0):
    x0, x1, z0, z1, _ = local_box(art)
    hw, hl = (x1 - x0) / 2 + grow, (z1 - z0) / 2 + grow
    lx, lz = rot(p[0] - centre[0], p[1] - centre[1], -yaw)
    return abs(lx) <= hw and abs(lz) <= hl


def samples(art, centre, yaw, grow=0.0, step=0.4):
    x0, x1, z0, z1, _ = local_box(art)
    hw, hl = (x1 - x0) / 2 + grow, (z1 - z0) / 2 + grow
    out = []
    nx, nz = max(1, int(2 * hw / step)), max(1, int(2 * hl / step))
    for i in range(nx + 1):
        for j in range(nz + 1):
            dx, dz = rot(-hw + 2 * hw * i / nx, -hl + 2 * hl * j / nz, yaw)
            out.append((centre[0] + dx, centre[1] + dz))
    return out


class Site:
    def __init__(self, key):
        self.key = key
        self.lay = L.load_layout(key)
        self.ctx = Ctx(key, self.lay)
        self.grid, self.nav = self.ctx.grid, self.ctx.nav
        self.mutual = W.mutual_region(self.ctx)
        sf = os.path.join(L.SEEDS, key + ".json")
        self.seeds = json.load(open(sf))
        self.bounds = self.ctx.spec["bounds"]
        self.doors = [(s["pos"][0], s["pos"][2]) for s in self.seeds
                      if any(w in (s["name"] + " " + (s.get("art") or "")).lower() for w in ("door", "window", "garage", "gate")) and self._inb(s["pos"])]
        self.cars = [(s["pos"][0], s["pos"][1], s["pos"][2]) for s in self.seeds if s["name"].startswith("poi-suburbs-car") and self._inb(s["pos"])]
        ints = E.interiors(self.ctx, sf)
        self.inside = E.interior_index(ints)
        self.int_cells = [(p[0], p[2]) for c in ints if c["area"] >= 80 for p in c["cells"]]
        self.placed = []                   # dicts: kind, art, centre, yaw, corners
        self.blocked = set()
        self.walk = {}                     # lattice node -> y
        self._lattice()
        pts = {"s0": self.lay["intro0"][0]["pos"], "s1": self.lay["intro1"][0]["pos"]}
        self.refs = [self.node_at(p["pos"]) for nm in ("intro0", "intro1", "respawns", "boxes") for p in self.lay[nm]]
        self.refs = [r for r in self.refs if r is not None]
        self.base_reach = self.flood(set())

    def _inb(self, p):
        b = self.bounds
        return b[0] - 3 <= p[0] <= b[1] + 3 and b[2] - 3 <= p[2] <= b[3] + 3

    # --- walk lattice (0.5 m cells, one node per floor)
    def _lattice(self):
        g = self.grid
        for (ix, iz), lst in g.cells.items():
            for k, (y, pi) in enumerate(lst):
                if pi in self.mutual:
                    self.walk[(ix, iz, k)] = y

    def node_at(self, pos):
        g = self.grid
        ix, iz = int(math.floor(pos[0] / g.CELL)), int(math.floor(pos[2] / g.CELL))
        best = None
        for k, (y, pi) in enumerate(g.cells.get((ix, iz), [])):
            if (ix, iz, k) in self.walk and (best is None or abs(y - pos[1]) < best[0]):
                best = (abs(y - pos[1]), (ix, iz, k))
        return best[1] if best and best[0] < 2.0 else None

    def flood(self, extra_blocked):
        src = self.node_at(self.lay["intro0"][0]["pos"])
        blocked = self.blocked | extra_blocked
        seen = {src}
        st = [src]
        g = self.grid
        while st:
            ix, iz, k = st.pop()
            y = self.walk[(ix, iz, k)]
            for dx in (-1, 0, 1):
                for dz in (-1, 0, 1):
                    if not dx and not dz:
                        continue
                    for k2, (y2, pi) in enumerate(g.cells.get((ix + dx, iz + dz), [])):
                        n = (ix + dx, iz + dz, k2)
                        if n in seen or n not in self.walk or n in blocked or abs(y2 - y) > 0.5:
                            continue
                        seen.add(n)
                        st.append(n)
        return seen

    def cells_in(self, art, centre, yaw, grow):
        """lattice nodes under the (grown) footprint"""
        g = self.grid
        pts = corners(art, centre, yaw, grow)
        xs, zs = [p[0] for p in pts], [p[1] for p in pts]
        out = set()
        for ix in range(int(math.floor(min(xs) / g.CELL)), int(math.floor(max(xs) / g.CELL)) + 1):
            for iz in range(int(math.floor(min(zs) / g.CELL)), int(math.floor(max(zs) / g.CELL)) + 1):
                c = ((ix + .5) * g.CELL, (iz + .5) * g.CELL)
                if inside_rect(art, centre, yaw, c, grow):
                    for k in range(len(g.cells.get((ix, iz), []))):
                        if (ix, iz, k) in self.walk:
                            out.add((ix, iz, k))
        return out

    # --- placement tests
    def ground_ref(self, centre):
        g = self.grid.ground(centre[0], centre[1], self.lay["intro0"][0]["pos"][1], 6.0)
        return g

    def fits(self, kind, centre2, y_ref, yaw, others_ok=True):
        """-> (ok, y_floor, reason)"""
        art = ART[kind]
        g = self.grid
        ys = []
        for p in samples(art, centre2, yaw):
            r = g.ground(p[0], p[1], y_ref, 0.8)
            if r is None or r[1] not in self.mutual:
                return False, 0, "footprint off the walkable ground"
            ys.append(r[0])
        if max(ys) - min(ys) > FLAT[kind]:
            return False, 0, "slope"
        wv = None
        if kind == "crate":                                   # crates may stand against a wall: the ring may be off the ground on the wall side only
            th, bp, wd = wall_dir(self, centre2[0], centre2[1], 4.0)
            if bp is not None and wd < 2.8:
                wv = (bp[0] - centre2[0], bp[1] - centre2[1])
        for p in samples(art, centre2, yaw, 0.75, 0.7):       # 0.75 m of ground all around: no wall / hole touching the prop (except the wall behind a crate)
            r = g.ground(p[0], p[1], y_ref, 1.0)
            if r is None and not (wv and (p[0] - centre2[0]) * wv[0] + (p[1] - centre2[1]) * wv[1] > 0):
                return False, 0, "no free ground around it"
        for d in self.doors:
            if any(math.hypot(c[0] - d[0], c[1] - d[1]) < 3.0 for c in corners(art, centre2, yaw)) or math.hypot(centre2[0] - d[0], centre2[1] - d[1]) < 3.0 + 1.0:
                return False, 0, "door / window"
        if any(math.hypot(centre2[0] - x, centre2[1] - z) < 2.5 for x, z in self.int_cells[::2]):
            return False, 0, "house floor"
        for b in self.lay["intro0"] + self.lay["intro1"]:
            if math.hypot(centre2[0] - b["pos"][0], centre2[1] - b["pos"][2]) < 6.0:
                return False, 0, "start"
        for r in self.lay["respawns"]:
            if math.hypot(centre2[0] - r["pos"][0], centre2[1] - r["pos"][2]) < 3.5:
                return False, 0, "respawn"
        for b in self.lay["boxes"]:
            dx, dz = centre2[0] - b["pos"][0], centre2[1] - b["pos"][2]
            d = math.hypot(dx, dz)
            fy = L.facing(b)
            if d < 2.4 or (d < 4.2 and math.cos(math.atan2(dx, dz) - fy) > 0.5):          # not on the box / in front of its lid
                return False, 0, "box"
        for q in self.placed:
            if math.hypot(centre2[0] - q["centre"][0], centre2[1] - q["centre"][1]) < q["r"] + (2.4 if kind == "wagon" else 1.8) + (3.0 if q["kind"] != kind else 0):
                return False, 0, "other prop"
        for c in self.cars:
            if math.hypot(centre2[0] - c[0], centre2[1] - c[2]) < (4.2 if kind != "wagon" else 4.8):
                return False, 0, "existing car"
        b = self.bounds
        if not all(b[0] + 1 <= p[0] <= b[1] - 1 and b[2] + 1 <= p[1] <= b[3] - 1 for p in corners(art, centre2, yaw, 1.0)):
            return False, 0, "outside the play area"
        # the map stays connected
        extra = self.cells_in(art, centre2, yaw, 0.4)
        reach = self.flood(extra)
        if not all(r in reach or r in extra for r in self.refs) or len(reach) < 0.985 * (len(self.base_reach) - len(extra) - len(self.blocked)):
            return False, 0, "would cut a route"
        return True, min(ys), ""

    def _wall_side(self, centre, yaw, p):
        return True

    def add(self, kind, centre2, y_floor, yaw, why):
        art = ART[kind]
        x0, x1, z0, z1, h = local_box(art)
        pos = pos_for(art, (centre2[0], y_floor, centre2[1]), yaw)
        self.placed.append({"kind": kind, "art": art, "centre": centre2, "yaw": yaw, "r": max(x1 - x0, z1 - z0) / 2, "pos": [round(pos[0], 3), round(y_floor - 0.02, 3), round(pos[2], 3)],
                            "why": why, "corners": corners(art, centre2, yaw), "h": h})
        self.blocked |= self.cells_in(art, centre2, yaw, 0.4)

    # --- sight lines
    def lines(self, n=9000, lo=35.0, hi=95.0, seed=7):
        rnd = random.Random(seed)
        g = self.grid
        b = self.bounds
        pts = []
        for (ix, iz, k), y in self.walk.items():
            if ix % 8 == 0 and iz % 8 == 0:
                x, z = (ix + .5) * g.CELL, (iz + .5) * g.CELL
                if b[0] + 2 <= x <= b[1] - 2 and b[2] + 2 <= z <= b[3] - 2:
                    pts.append((x, y, z))
        out = []
        for _ in range(n * 3):
            a, c = rnd.choice(pts), rnd.choice(pts)
            d = math.hypot(a[0] - c[0], a[2] - c[2])
            if lo <= d <= hi and abs(a[1] - c[1]) < 2.0 and g.los(a, c):
                out.append((a[0], a[2], c[0], c[2]))
            if len(out) >= n:
                break
        return np.array(out)

    @staticmethod
    def broken(lines, art, centre, yaw):
        """boolean mask of the lines a prop footprint (grown 0.15 m) intersects"""
        cs = corners(art, centre, yaw, 0.15)
        hit = np.zeros(len(lines), bool)
        for i in range(4):
            p, q = np.array(cs[i]), np.array(cs[(i + 1) % 4])
            hit |= _seg_inter(lines[:, :2], lines[:, 2:], p, q)
        # a line that starts / ends inside also counts
        return hit


def _seg_inter(a, b, p, q):
    def cross(o, u, v):
        return (u[..., 0] - o[..., 0]) * (v[..., 1] - o[..., 1]) - (u[..., 1] - o[..., 1]) * (v[..., 0] - o[..., 0])
    P, Q = np.broadcast_to(p, a.shape), np.broadcast_to(q, a.shape)
    d1, d2 = cross(a, b, P), cross(a, b, Q)
    d3, d4 = cross(P, Q, a), cross(P, Q, b)
    return (d1 * d2 < 0) & (d3 * d4 < 0)


# ---------------------------------------------------------------------------------------------- planning
def wall_dir(site, x, z, rad=6.0):
    """direction (unit vector x, z) of the navmesh edges (walls / holes) around (x, z), length weighted, doubled angle mean + the nearest edge point"""
    nav = site.nav
    c = nav.cellsz
    sx = sy = 0.0
    best, bp = 1e9, None
    for dx in range(-2, 3):
        for dz in range(-2, 3):
            for a, b in nav.bgrid.get((int(x // c) + dx, int(z // c) + dz), ()):
                mx, mz = (a[0] + b[0]) / 2, (a[2] + b[2]) / 2
                d = math.hypot(mx - x, mz - z)
                if d > rad:
                    continue
                ex, ez = b[0] - a[0], b[2] - a[2]
                ln = math.hypot(ex, ez)
                if ln < 0.3:
                    continue
                th = math.atan2(ex, ez)
                w = ln / (1 + d)
                sx += w * math.cos(2 * th)
                sy += w * math.sin(2 * th)
                dd = L.nav_plan.seg_dist_xz(x, z, a, b)
                if dd < best:
                    best = dd
                    t = max(0.0, min(1.0, ((x - a[0]) * ex + (z - a[2]) * ez) / (ex * ex + ez * ez or 1)))
                    bp = (a[0] + t * ex, a[2] + t * ez)
    if best > 1e8:
        return None, None, 1e9
    th = 0.5 * math.atan2(sy, sx)
    return th, bp, best


def lane_width(site, x, y, z, th):
    """walkable run to both sides across the lane axis th (yaw of the axis)"""
    px, pz = math.cos(th), -math.sin(th)          # perpendicular
    g = site.grid
    a = g.run((x, y, z), math.atan2(px, pz), 10.0, 0.25, 0.8)
    b = g.run((x, y, z), math.atan2(-px, -pz), 10.0, 0.25, 0.8)
    return a, b


def plan(key, quiet=False):
    S = Site(key)
    g = S.grid
    rnd = random.Random(11)
    lines = S.lines()
    if not quiet:
        print(f"{key}: {len(lines)} long sight lines (35-95 m), {len(S.cars)} car markers, {len(S.doors)} doors / windows, {len(S.int_cells)} house cells")
    L0 = len(lines)
    alive = np.ones(len(lines), bool)

    def heat(art, centre, yaw):
        return int((S.broken(lines[alive], art, centre, yaw)).sum())

    def kill(art, centre, yaw):
        h = S.broken(lines, art, centre, yaw)
        alive[:] = alive & ~h

    # 1. wagons: free slots of the parked rows
    slots = []
    for cx, cy, cz in S.cars:
        th, bp, d = wall_dir(S, cx, cz, 3.8)
        if th is None:
            continue
        for k in (-2, -1, 1, 2):
            slots.append((cx + k * 6.1 * math.sin(th), cz + k * 6.1 * math.cos(th), th, (cx, cz), cy))
    cand = []
    for x, z, th, mk, cy in slots:
        for yaw in (th, th + math.pi):
            ok, yf, why = S.fits("wagon", (x, z), cy, yaw)
            if ok:
                cand.append((heat(ART["wagon"], (x, z), yaw), x, z, yaw, yf, mk))
                break
    cand.sort(reverse=True)
    nw = 0
    for h, x, z, yaw, yf, mk in cand:
        if nw >= 4:
            break
        ok, yf, why = S.fits("wagon", (x, z), yf + 0.02, yaw)
        if not ok:
            continue
        S.add("wagon", (x, z), yf, yaw, f"parked next to the level's own car at ({mk[0]:.0f}, {mk[1]:.0f}), same axis, a free slot of the existing parked row (cars one length apart)")
        kill(ART["wagon"], (x, z), yaw)
        nw += 1

    # 2. boxes in the open: a crate pair 3-5 m to the side the longest line comes from
    for bi, b in enumerate(S.lay["boxes"]):
        if S.inside(b["pos"]) >= 0:
            continue
        bx, bz = b["pos"][0], b["pos"][2]
        near = lines[alive]
        near = near[(np.hypot(near[:, 0] - bx, near[:, 1] - bz) < 3.0) | (np.hypot(near[:, 2] - bx, near[:, 3] - bz) < 3.0)]
        dirs = []
        for l in near:
            far = (l[2], l[3]) if math.hypot(l[0] - bx, l[1] - bz) < 3.0 else (l[0], l[1])
            dirs.append(math.atan2(far[0] - bx, far[1] - bz))
        order = sorted(set(round(d, 1) for d in dirs), key=lambda d: -sum(1 for q in dirs if abs(q - d) < 0.4)) if dirs else [0.0, 1.6, -1.6, 3.1]
        done = False
        for ang in order[:4] + [a * 0.8 for a in range(8)]:
            for dist in (3.6, 4.4, 5.2):
                x, z = bx + dist * math.sin(ang), bz + dist * math.cos(ang)
                r = g.ground(x, z, b["pos"][1], 1.0)
                if r is None:
                    continue
                th, bp, d = wall_dir(S, x, z, 5.0)
                yaw = (th if th is not None else ang)
                for pair in (0,):
                    cs = [(x, z)]
                    ok, yf, why = S.fits("crate", (x, z), r[0], yaw)
                    if ok:
                        S.add("crate", (x, z), yf, yaw, f"cover for box B{bi + 1} against the sight line from bearing {math.degrees(ang):.0f} deg, 3-5 m from the box, beside its lid")
                        kill(ART["crate"], (x, z), yaw)
                        # second crate beside the first, along the wall direction
                        ex, ez = math.sin(yaw), math.cos(yaw)
                        x2, z2 = x + 1.2 * math.cos(yaw), z - 1.2 * math.sin(yaw)
                        ok2, yf2, w2 = S.fits("crate", (x2, z2), yf, yaw)
                        if ok2:
                            S.add("crate", (x2, z2), yf2, yaw, "second crate of the pair (a 2 m cover wall), same yaw")
                            kill(ART["crate"], (x2, z2), yaw)
                        done = True
                        break
                if done:
                    break
            if done:
                break

    # 3. hot spots on the remaining long lines: crate pairs at walls, plank barricades across narrow lanes
    cells = {}
    for (ix, iz, k), y in S.walk.items():
        if ix % 2 == 0 and iz % 2 == 0:
            cells[(ix, iz, k)] = y
    pts = np.array([[(ix + .5) * g.CELL, (iz + .5) * g.CELL] for (ix, iz, k) in cells])
    ys = np.array(list(cells.values()))
    n_c = sum(1 for p in S.placed if p["kind"] == "crate")
    n_p = 0
    tries = 0
    while tries < 400 and (n_p < 4 or n_c < 12) and alive.sum() > 0.25 * L0:
        tries += 1
        A, B = lines[alive][:, :2], lines[alive][:, 2:]
        # heat of every candidate cell = lines passing within 0.9 m
        d = B - A
        ln = np.maximum(np.hypot(d[:, 0], d[:, 1]), 1e-6)
        pa = pts[None, :, :] - A[:, None, :]
        t = np.clip((pa[..., 0] * d[:, None, 0] + pa[..., 1] * d[:, None, 1]) / (ln[:, None] ** 2), 0, 1)
        dist = np.hypot(pa[..., 0] - t * d[:, None, 0], pa[..., 1] - t * d[:, None, 1])
        hot = (dist < 0.9).sum(0)
        order = np.argsort(-hot)
        placed_now = False
        for i in order[:60]:
            if hot[i] < 4:
                break
            x, z = pts[i]
            y = ys[i]
            th, bp, wd = wall_dir(S, x, z, 7.0)
            if th is None:
                continue
            w1, w2 = lane_width(S, x, y, z, th)
            width = w1 + w2
            if 4.5 <= width <= 8.5 and n_p < 4:
                # plank barricade across the lane: centred a bit toward the wall that is closer, gaps both sides
                off = (w1 - w2) / 2
                px, pz = math.cos(th), -math.sin(th)
                cx, cz = x + px * off * 0.0, z + pz * off * 0.0
                for yaw in (th, th + 0.12, th - 0.12):
                    ok, yf, why = S.fits("planks", (cx, cz), y, yaw)
                    if ok:
                        S.add("planks", (cx, cz), yf, yaw, f"boarded barricade across a {width:.1f} m lane (chicane, walkable gap each side), breaks {int(hot[i])} of the remaining sight lines")
                        kill(ART["planks"], (cx, cz), yaw)
                        n_p += 1
                        placed_now = True
                        break
            elif wd < 3.6 and n_c < 12:
                # crate pair at a wall: back to the wall, 1.7 m off it
                bx, bz = bp
                vx, vz = x - bx, z - bz
                vl = math.hypot(vx, vz) or 1
                cx, cz = bx + vx / vl * 1.7, bz + vz / vl * 1.7
                yaw = th
                ok, yf, why = S.fits("crate", (cx, cz), y, yaw)
                if ok:
                    S.add("crate", (cx, cz), yf, yaw, f"crates stacked against the wall / hole edge (aligned to it, 1 m walkway behind), breaks {int(hot[i])} sight lines")
                    kill(ART["crate"], (cx, cz), yaw)
                    cx2, cz2 = cx + 1.2 * math.sin(yaw + math.pi / 2) * 1.0, cz + 1.2 * math.cos(yaw + math.pi / 2) * 1.0
                    ok2, yf2, w2_ = S.fits("crate", (cx2, cz2), yf, yaw)
                    if ok2:
                        S.add("crate", (cx2, cz2), yf2, yaw, "second crate of the pair, same yaw")
                        kill(ART["crate"], (cx2, cz2), yaw)
                        n_c += 1
                    n_c += 1
                    placed_now = True
            if placed_now:
                break
        if not placed_now:
            break
    broken = 100 * (1 - alive.sum() / L0)
    if not quiet:
        print(f"{key}: {len(S.placed)} props ({sum(1 for p in S.placed if p['kind'] == 'wagon')} wagons, {sum(1 for p in S.placed if p['kind'] == 'crate')} crates, "
              f"{sum(1 for p in S.placed if p['kind'] == 'planks')} plank barricades); {broken:.0f}% of the long sight lines broken")
    return S, lines, alive


def draw(S, lines, alive, path):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.collections import PolyCollection, LineCollection
    fig, ax = plt.subplots(figsize=(15, 8.5), dpi=85)
    ax.add_collection(PolyCollection([[(v[0], v[2]) for v in S.nav.polys[i]] for i in S.ctx.play], facecolor="#e3e8ea", edgecolor="#b8c4c8", linewidth=0.2))
    ax.add_collection(LineCollection([[(l[0], l[1]), (l[2], l[3])] for l in lines[~alive][:250]], colors="#90caf9", linewidths=0.25, alpha=0.35))
    ax.add_collection(LineCollection([[(l[0], l[1]), (l[2], l[3])] for l in lines[alive][:250]], colors="#ef5350", linewidths=0.3, alpha=0.35))
    col = {"wagon": "#1565c0", "crate": "#8d6e63", "planks": "#ef6c00"}
    for i, p in enumerate(S.placed):
        ax.add_patch(plt.Polygon(p["corners"], closed=True, fc=col[p["kind"]], ec="k", lw=0.6, alpha=0.9, zorder=5))
        ax.text(p["centre"][0], p["centre"][1] + 1.6, str(i + 1), fontsize=6, ha="center", zorder=6)
    for c in S.cars:
        ax.plot(c[0], c[2], "x", color="r", ms=5)
    for nm, m, c in (("intro0", "o", "r"), ("intro1", "o", "b"), ("respawns", "^", "g"), ("boxes", "s", "y")):
        for q in S.lay[nm]:
            ax.plot(q["pos"][0], q["pos"][2], c + m, ms=7, mec="k", zorder=4)
    b = S.bounds
    ax.add_patch(plt.Rectangle((b[0], b[2]), b[1] - b[0], b[3] - b[2], fill=False, ec="#8e24aa", lw=1.4))
    ax.set_xlim(b[0] - 3, b[1] + 3); ax.set_ylim(b[2] - 3, b[3] + 3); ax.set_aspect("equal"); ax.grid(True, lw=0.3)
    ax.set_title(f"{S.key}: {len(S.placed)} cover props (blue wagon, brown crates, orange plank barricade); long sight lines: blue = broken, red = left;  x = level's own car markers")
    fig.savefig(path, bbox_inches="tight")
    plt.close(fig)


def write_spec(key, S):
    d = json.load(open(SPEC, encoding="utf-8"))
    m = [x for x in d["maps"] if x["key"] == key][0]
    keep = [p for p in m.get("props", []) if not p.get("cover")]
    for p in S.placed:
        keep.append({"art": p["art"], "pos": p["pos"], "quat": yaw_quat(p["yaw"]), "cover": True, "why": p["why"]})
    m["props"] = keep
    json.dump(d, open(SPEC, "w", encoding="utf-8"), indent=1, ensure_ascii=False)


def main(argv):
    if len(argv) < 3 or argv[1] != "plan":
        print(__doc__)
        return 1
    key = argv[2]
    S, lines, alive = plan(key)
    os.makedirs(PREV, exist_ok=True)
    draw(S, lines, alive, os.path.join(PREV, f"{key}-cover.png"))
    for i, p in enumerate(S.placed):
        print(f"  {i + 1:2d} {p['art']:42s} at ({p['pos'][0]:.1f}, {p['pos'][1]:.2f}, {p['pos'][2]:.1f}) yaw {math.degrees(p['yaw']):.0f}: {p['why']}")
    if "--write" in argv:
        write_spec(key, S)
        print("spec updated")
        if "--pak" in argv:
            sys.path.insert(0, HERE)
            import sp_maps
            sp_maps.pak(key)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
