"""Loot scatter + interrogation safes for an SP-section map, placed offline on the REAL geometry (Supermarket). Goals:
working safe locations, random util spawns, medkits and many pickupables; each item must lie on
the ground / shelf / contact surface as exactly as possible; the scatter is another placeable group; a realistic, scarce, respawning amount of items in
each set of rooms; half of those ingredients shared and half not.

  python tools/maps/loot_place.py cache  <key>            collision (every loaded level, edited copies when built) + render triangles of the
                                                          geometry levels -> re/maps/level-edit-cache/loot-<key>.npz (gitignored, ~1 min)
  python tools/maps/loot_place.py meshes                  bounds of the pickup meshes (all-standard-pickups / all-ammo-pickups): where each
                                                          mesh's origin sits against its bottom (-> itemspots.c isp_up)
  python tools/maps/loot_place.py plan   <key> [--write]  candidate contact spots -> selection per room -> items / budget; --write puts the
                                                          `group: loot` spots into data/<key>-itemspots.json (hand spots kept) + itemspots.h
  python tools/maps/loot_place.py check  <key>            re-measure every item spot of data/<key>-itemspots.json (moved in the editor?):
                                                          contact gap, footprint, clearance, the runtime ray
  python tools/maps/loot_place.py safes  <key> [--write]  interrogation safe candidates (3 per team): indoors, against a wall, own half, no line
                                                          of sight to ANY enemy candidate -> data/<key>-lockboxes.json (+ interrogation_lockboxes.py)
  python tools/maps/loot_place.py plot   <key> <png>      top-down: rooms, loot spots (shared / unique), safes, respawns, boxes; side views

How an item ends up on its surface in game (tools/ext/itemspots.c): a static-world ray from the spot + 0.25 m down 1.8 m, the FIRST collision hit,
+ spot.dy (visible render surface minus that collision hit, measured here) + isp_up(item) (the pickup mesh's origin is its bottom: 3 mm).
A spot is accepted only when that runtime ray lands on the intended surface, the collision and the render surface under the item's whole
footprint (r 0.13 m, 9 points) are flat (spread <= 1.2 cm) and agree (|dy| <= 4 cm), nothing (collision or render) intrudes into the item's
volume (footprint x 0.30 m above the surface), and a standing player reaches it (a stand-reachable floor cell within 1.3 m whose chest-height
line to the item is clear). Surfaces are horizontal (normal y >= 0.995), so the item's up is the surface normal; the yaw is random per spot.
Offline, CPU only (numpy).
"""
import json
import math
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.dirname(HERE)
ROOT = os.path.dirname(TOOLS)
sys.path.insert(0, HERE)
sys.path.insert(0, TOOLS)
sys.path.insert(0, os.path.join(TOOLS, "models"))
DATA = os.path.join(HERE, "data")


def _rel(p):
    try:
        return os.path.relpath(p, ROOT)
    except ValueError:                       # worktree on another drive than the main checkout (the cache lives there)
        return p

CACHE = os.path.join(ROOT, "re", "maps", "level-edit-cache")

# ------------------------------------------------------------------------------------------------ per-map setup
MAPS = {
    "jackson-market": {
        "box": [-535.0, -460.0, 237.0, 340.0],
        "render_levels": ["pat-jackson-supermarket", "pat-jackson-supermarket-int", "pat-jackson-alley", "pat-jackson-alley-detail", "pat-jackson-wide"],
        # flood seeds: the two starts + every room behind a sill the 0.5 m walk model cannot cross (post office doors)
        "seeds": [[-478.0, 16.94, 321.2], [-522.0, 17.88, 250.0], [-512.75, 17.91, 285.25], [-500.75, 17.93, 297.25], [-498.25, 17.93, 281.75],
                  [-513.1, 17.97, 303.6], [-524.75, 17.92, 303.25], [-504.5, 17.88, 255.6], [-527.75, 17.88, 264.05],
                  [-489.93, 17.946, 258.88], [-478.0, 17.0, 250.0]],   # + the team 2 start (lot south; the wall edits cut it off from the seeds above)
        # room clusters (x0, x1, z0, z1): the sets of rooms a player loots between two supply boxes; first match wins
        "rooms_outdoor": ["lot south", "lot middle", "lot north"],
        "rooms": [
            ("hunting store", (-533.0, -509.5, 297.0, 318.0)),
            ("post office", (-507.5, -493.0, 266.0, 306.0)),
            ("courtyard", (-533.0, -507.5, 283.0, 297.0)),
            ("store back rooms", (-533.0, -501.0, 268.0, 283.0)),
            ("store hall west", (-533.0, -516.0, 237.0, 268.0)),
            ("store hall east", (-516.0, -500.0, 237.0, 268.0)),
            ("lot south", (-500.0, -460.0, 237.0, 276.0)),
            ("lot middle", (-493.0, -460.0, 276.0, 302.0)),
            ("lot north", (-500.0, -460.0, 302.0, 340.0)),
        ],
        "room_spots": {"hunting store": 12, "post office": 12, "courtyard": 6, "store back rooms": 12, "store hall west": 12, "store hall east": 12,
                       "lot south": 10, "lot middle": 2, "lot north": 10},
        # one spot of these rooms turns into a health spot / a util (throwables) spot
        "special": {"medkit": ["store back rooms", "hunting store", "post office", "lot south"], "util": ["store hall west", "post office", "hunting store", "lot north"]},
    },
}

FOOT_R = 0.09          # m: support points: the surface is checked at the centre + 8 points on this circle
CLEAR_R = 0.14         # m: half size of the free box above the surface: the largest pickup turned any way fits (beef jerky 0.164 x 0.221 m -> half diagonal
                       # 0.137; blades / scissors 0.224 m long -> 0.112; health kit 0.168 x 0.137; meshes: python loot_place.py meshes)
FOOT_SPREAD = 0.02     # m: max height spread of the surface under the footprint (collision and render each)
DY_MAX = 0.05          # m: |render - collision| accepted (applied as spot.dy)
CLEAR_H = 0.30         # m: free height above the surface (the tallest pickup, canister / alcohol, is 0.25 m)
RAY_UP, RAY_LEN = 0.25, 1.8      # itemspots.c isp_height
REACH_R = 1.3          # m: a stand cell this close (horizontal)
SHELF_MAX = 1.45       # m above the player's floor
SPACING = 1.7          # m between two floor loot spots
SPACING_RAISED = 1.3   # m between two spots on shelves / counters / low surfaces (raised surfaces are scarce, use them before the floor)
FLOOR_MAX_IN = 1        # floor spots per indoor room at most (only what shelves / counters / crates cannot hold)
FLOOR_MAX_OUT = 3       # per outdoor room (snow lot / courtyard: the ground is the surface there)
SLOPE_MAX = 20.0       # deg: outdoor rooms (MAPS rooms_outdoor): the surface may tilt this much, the item is turned onto it
SNOW_SINK = 0.01       # m: on deformed snow the item sits this deep in the collision plane (the visible snow top), never floating
SNOW_BASE = 0.45       # m: deformed snow: the render base mesh lies at most this far under the collision


def spec(key):
    return next(m for m in json.load(open(os.path.join(HERE, "sp_maps.json"), encoding="utf-8"))["maps"] if m["key"] == key)


def npz_path(key):
    return os.path.join(CACHE, f"loot-{key}.npz")


# ------------------------------------------------------------------------------------------------ geometry
class TriGrid:
    """triangles bucketed on an xz grid: vertical ray, segment and box queries"""

    def __init__(self, T, B=0.5):
        self.T = np.ascontiguousarray(T, dtype=np.float64)
        self.B = B
        lo, hi = self.T.min(1), self.T.max(1)
        self.lo, self.hi = lo, hi
        bx0 = np.floor(lo[:, 0] / B).astype(np.int64)
        bx1 = np.floor(hi[:, 0] / B).astype(np.int64)
        bz0 = np.floor(lo[:, 2] / B).astype(np.int64)
        bz1 = np.floor(hi[:, 2] / B).astype(np.int64)
        nx, nz = bx1 - bx0 + 1, bz1 - bz0 + 1
        nb = nx * nz
        keep = nb <= 400
        self.big = np.nonzero(~keep)[0]          # big triangles (whole floors): checked by every query
        idx = np.nonzero(keep)[0]
        rep = nb[idx]
        tri = np.repeat(idx, rep)
        off = np.arange(rep.sum()) - np.repeat(np.cumsum(rep) - rep, rep)
        ax = bx0[tri] + off % nx[tri]
        az = bz0[tri] + off // nx[tri]
        key = ax * 1000003 + az
        o = np.argsort(key, kind="stable")
        self.key, self.tri = key[o], tri[o]
        self.ukey, self.start = np.unique(self.key, return_index=True)
        self.end = np.r_[self.start[1:], len(self.key)]
        n = np.cross(self.T[:, 1] - self.T[:, 0], self.T[:, 2] - self.T[:, 0])
        self.ny = n[:, 1] / (np.linalg.norm(n, axis=1) + 1e-12)

    def cell(self, a, b):
        k = a * 1000003 + b
        i = np.searchsorted(self.ukey, k)
        if i < len(self.ukey) and self.ukey[i] == k:
            return self.tri[self.start[i]:self.end[i]]
        return self.tri[:0]

    def near(self, x0, z0, x1, z1):
        B = self.B
        out = [self.cell(a, b) for a in range(int(math.floor(x0 / B)), int(math.floor(x1 / B)) + 1)
               for b in range(int(math.floor(z0 / B)), int(math.floor(z1 / B)) + 1)]
        out = [o for o in out if len(o)]
        if len(self.big):
            b = self.big[(self.hi[self.big, 0] >= x0) & (self.lo[self.big, 0] <= x1) & (self.hi[self.big, 2] >= z0) & (self.lo[self.big, 2] <= z1)]
            if len(b):
                out.append(b)
        return np.unique(np.concatenate(out)) if out else self.tri[:0]

    def heights(self, x, z, ylo=-1e9, yhi=1e9, ids=None):
        """-> (y[], ny[]) of every triangle under (x, z) (vertical line), any winding"""
        ids = self.near(x, z, x, z) if ids is None else ids
        if not len(ids):
            return np.zeros(0), np.zeros(0)
        T = self.T[ids]
        x1, z1 = T[:, 0, 0], T[:, 0, 2]
        x2, z2 = T[:, 1, 0], T[:, 1, 2]
        x3, z3 = T[:, 2, 0], T[:, 2, 2]
        det = (z2 - z3) * (x1 - x3) + (x3 - x2) * (z1 - z3)
        ok = np.abs(det) > 1e-12
        det = np.where(ok, det, 1.0)
        l1 = ((z2 - z3) * (x - x3) + (x3 - x2) * (z - z3)) / det
        l2 = ((z3 - z1) * (x - x3) + (x1 - x3) * (z - z3)) / det
        l3 = 1 - l1 - l2
        e = -2e-4                 # float32 vertices: a point on a shared edge / the quad diagonal must hit one of the two triangles
        inside = ok & (l1 >= e) & (l2 >= e) & (l3 >= e)
        y = l1 * T[:, 0, 1] + l2 * T[:, 1, 1] + l3 * T[:, 2, 1]
        m = inside & (y >= ylo) & (y <= yhi)
        return y[m], np.abs(self.ny[ids][m])

    def ray_down(self, x, z, ytop, length):
        """the first triangle a vertical ray from (x, ytop, z) meets within length -> (y, |ny|) or (None, None)"""
        y, ny = self.heights(x, z, ytop - length, ytop)
        if not len(y):
            return None, None
        k = int(np.argmax(y))
        return float(y[k]), float(ny[k])

    def seg_blocked(self, a, b, eps=0.02):
        return self.seg_t(a, b, eps) is not None

    def seg_t(self, a, b, eps=0.02):
        """distance from a to the first triangle on the segment a-b, or None"""
        a, b = np.asarray(a, float), np.asarray(b, float)
        x0, x1 = sorted((a[0], b[0]))
        z0, z1 = sorted((a[2], b[2]))
        ids = self.near(x0, z0, x1, z1)
        if not len(ids):
            return None
        ylo, yhi = min(a[1], b[1]), max(a[1], b[1])
        m = (self.hi[ids, 1] >= ylo - 0.01) & (self.lo[ids, 1] <= yhi + 0.01)
        m &= (self.hi[ids, 0] >= x0 - 0.01) & (self.lo[ids, 0] <= x1 + 0.01) & (self.hi[ids, 2] >= z0 - 0.01) & (self.lo[ids, 2] <= z1 + 0.01)
        ids = ids[m]
        if not len(ids):
            return None
        T = self.T[ids]
        d = b - a
        L = np.linalg.norm(d)
        d = d / L
        e1, e2 = T[:, 1] - T[:, 0], T[:, 2] - T[:, 0]
        p = np.cross(d, e2)
        det = (e1 * p).sum(1)
        ok = np.abs(det) > 1e-12
        inv = 1.0 / np.where(ok, det, 1.0)
        s = a - T[:, 0]
        u = (s * p).sum(1) * inv
        q = np.cross(s, e1)
        v = (q * d).sum(1) * inv
        t = (q * e2).sum(1) * inv
        hit = ok & (u >= 0) & (v >= 0) & (u + v <= 1) & (t > eps) & (t < L - eps)
        return float(t[hit].min()) if hit.any() else None

    def box_hit(self, lo, hi):
        import level_edit as le
        ids = self.near(lo[0], lo[2], hi[0], hi[2])
        if not len(ids):
            return False
        m = ((self.hi[ids] >= lo) & (self.lo[ids] <= hi)).all(1)
        if not m.any():
            return False
        return bool(le.tri_box_overlap(self.T[ids[m]], lo, hi).any())


def cache(key):
    import ndpak
    import level_edit as le
    import reach_check as rc
    cfg = MAPS[key]
    box = cfg["box"]
    C, used = rc.level_tris(key, box)
    P, unk = rc.prop_tris(spec(key).get("props", []))
    print(f"collision {len(C)} triangles + props {len(P)} (no bounds: {sorted(set(unk))})")
    R = []
    for lv in cfg["render_levels"]:
        cand = [os.path.join(le.CACHE, "out", key, lv + ".pak"), os.path.join(le.CACHE, "out", lv + ".pak"), os.path.join(le.CACHE, "src", lv + ".pak")]
        p = next((c for c in cand if os.path.exists(c)), None)
        if not p:
            p = le.fetch(lv, os.path.join(le.CACHE, "src"), None, ("",))[""]
        T = le.world_submeshes(ndpak.Pak(p), [box[0], -50, box[2], box[1], 80, box[3]])
        sel = ((T.max(1)[:, [0, 2]] >= [box[0], box[2]]) & (T.min(1)[:, [0, 2]] <= [box[1], box[3]])).all(1) if len(T) else np.zeros(0, bool)
        print(f"render {lv}: {int(sel.sum())} triangles ({_rel(p)})")
        if sel.any():
            R.append(T[sel].astype(np.float32))
    np.savez_compressed(npz_path(key), C=np.concatenate([C, P]).astype(np.float32) if len(P) else C.astype(np.float32), R=np.concatenate(R))
    print("->", npz_path(key))


class Geo:
    def __init__(self, key):
        d = np.load(npz_path(key))
        self.C = TriGrid(d["C"])
        R = d["R"]
        cfg = MAPS[key]
        self.R = TriGrid(R[R.min(1)[:, 1] < 40.0])
        self.key = key
        self.cfg = cfg
        self._flood = None

    def flood(self):
        """stand-reachable floor cells {(i, j): y} (reach_check walk model, 0.5 m) + the World"""
        if self._flood is None:
            import reach_check as rc
            fp = os.path.join(CACHE, f"loot-{self.key}-flood.json")
            box = self.cfg["box"]
            w = rc.World(self.C.T, box)
            if os.path.exists(fp) and os.path.getmtime(fp) > os.path.getmtime(npz_path(self.key)):
                cells = {tuple(map(int, k.split(","))): v for k, v in json.load(open(fp)).items()}
            else:
                r = w.flood([tuple(s) for s in self.cfg["seeds"]], rc.MODES["stand"])
                cells = {}
                for (i, j, _), h in r.items():
                    cells.setdefault((i, j), []).append(h)
                json.dump({f"{i},{j}": v for (i, j), v in cells.items()}, open(fp, "w"))
            self._flood = (w, cells)
        return self._flood

    def room_of(self, x, z):
        for name, (x0, x1, z0, z1) in self.cfg["rooms"]:
            if x0 <= x <= x1 and z0 <= z <= z1:
                return name
        return None

    def outdoor(self, x, z):
        """a room of MAPS[key]['rooms_outdoor']: sloped / deformed-snow surfaces allowed"""
        return self.room_of(x, z) in self.cfg.get("rooms_outdoor", ())

    def indoor(self, x, y, z):
        y2, _ = self.C.heights(x, z, y + 1.6, y + 12.0)
        return bool(len(y2))


# ------------------------------------------------------------------------------------------------ contact check of one spot
def plane_fit(pts, ys, x, z):
    """least-squares plane y = gx dx + gz dz + c through (dx, dz, y) -> (normal, max residual, c)"""
    P = np.asarray(pts, float)
    A = np.c_[P[:, 0] - x, P[:, 1] - z, np.ones(len(P))]
    sol = np.linalg.lstsq(A, ys, rcond=None)[0]
    res = float(np.abs(A @ sol - ys).max())
    n = np.array([-sol[0], 1.0, -sol[1]])
    return n / np.linalg.norm(n), res, float(sol[2])


def contact(g, x, z, ys, foot=FOOT_R, slope_ok=False):
    """-> (ok, info) for an item resting at height ys (collision surface) under (x, z).
    slope_ok (outdoor rooms): the surface may tilt up to SLOPE_MAX (the item is turned onto the normal), and deformed snow - whose
    render base mesh lies under the collision (the shader displaces it up to the collision top) - counts as a surface: the item
    sits SNOW_SINK into the collision plane."""
    info = {}
    ny_min = math.cos(math.radians(SLOPE_MAX)) if slope_ok else 0.995
    yr, nyr = g.C.ray_down(x, z, ys + RAY_UP, RAY_LEN)
    if yr is None or abs(yr - ys) > 0.004 or nyr < ny_min:
        return False, {"why": f"runtime ray lands on {yr if yr is None else round(yr - ys, 3)} (ny {nyr})"}
    pts = [(x, z)] + [(x + foot * math.cos(a), z + foot * math.sin(a)) for a in np.arange(8) * math.pi / 4]
    reach_y = foot * math.tan(math.radians(SLOPE_MAX)) + 0.02 if slope_ok else 0.05
    cy, ry = [], []
    for (px, pz) in pts:
        y1, n1 = g.C.ray_down(px, pz, ys + reach_y, 2 * reach_y)
        if y1 is None or n1 < ny_min - 0.01:
            return False, {"why": "collision footprint off the surface"}
        cy.append(y1)
        y2, n2 = g.R.heights(px, pz, y1 - 0.06, y1 + 0.06)
        y2 = y2[n2 > ny_min - 0.03]
        ry.append(float(y2.max()) if len(y2) else None)
    cy = np.array(cy)
    cn, cres, _ = plane_fit(pts, cy, x, z)
    if not slope_ok and cy.max() - cy.min() > FOOT_SPREAD or cres > FOOT_SPREAD:
        return False, {"why": f"uneven (collision {cy.max() - cy.min():.3f}, plane residual {cres:.3f})"}
    snow = False
    if any(v is None for v in ry):
        if not slope_ok:
            return False, {"why": "no render surface under the footprint"}
        # deformed snow? the render base must lie under the collision at every footprint point (never above: that would be a visible lip)
        for (px, pz), y1 in zip(pts, cy):
            y2, n2 = g.R.heights(px, pz, y1 - SNOW_BASE, y1 + 0.06)
            if not len(y2) or (y2 > y1 - 0.03).any():
                return False, {"why": "no render surface under the footprint"}
        snow, ry, nrm, dy = True, cy - SNOW_SINK, cn, -SNOW_SINK
    else:
        ry = np.array(ry)
        nrm, rres, rc0 = plane_fit(pts, ry, x, z)
        if (not slope_ok and ry.max() - ry.min() > FOOT_SPREAD) or rres > FOOT_SPREAD:
            return False, {"why": f"uneven (render spread {ry.max() - ry.min():.3f}, plane residual {rres:.3f})"}
        if nrm[1] < ny_min:
            return False, {"why": f"render slope {math.degrees(math.acos(nrm[1])):.0f} deg"}
        dy = float(rc0 - ys)
        if abs(dy) > DY_MAX:
            return False, {"why": f"render {dy:+.3f} m off the collision"}
    top = max(float(np.max(ry)), float(cy.max())) + 0.012
    lo, hi = np.array([x - CLEAR_R, top, z - CLEAR_R]), np.array([x + CLEAR_R, ys + CLEAR_H, z + CLEAR_R])
    if g.C.box_hit(lo, hi):
        return False, {"why": "collision in the item volume"}
    if g.R.box_hit(lo, hi):
        return False, {"why": "render geometry in the item volume"}
    gap = float(np.max(ry) - (ys + dy)) if not snow else 0.0
    info.update(dy=round(dy, 3), spread=round(float(np.max(ry) - np.min(ry)), 4), gap=round(gap, 4), normal=[round(float(v), 5) for v in nrm],
                slope=round(math.degrees(math.acos(min(1.0, nrm[1]))), 1), snow=snow)
    return True, info


def reach(g, x, ys, z):
    """-> (floor y, stand distance) of the nearest stand-reachable cell that sees the item, or (None, None)"""
    import reach_check as rc
    w, cells = g.flood()
    i0, j0 = int((x - w.x0) // rc.CELL), int((z - w.z0) // rc.CELL)
    best = None
    k = int(math.ceil(REACH_R / rc.CELL)) + 1
    for i in range(i0 - k, i0 + k + 1):
        for j in range(j0 - k, j0 + k + 1):
            for h in cells.get((i, j), []):
                cx, cz = w.cell_xz(i, j)
                d = math.hypot(cx - x, cz - z)
                if d > REACH_R or not (-0.05 <= ys - h <= SHELF_MAX):
                    continue
                if best and d >= best[1]:
                    continue
                if g.C.seg_blocked((cx, h + 1.2, cz), (x, ys + 0.08, z)):
                    continue
                best = (h, d)
    return best if best else (None, None)


# ------------------------------------------------------------------------------------------------ candidate search
def candidates(g, step=0.25):
    import reach_check as rc
    w, cells = g.flood()
    floors = {}
    for (i, j), hs in cells.items():
        floors[(i, j)] = hs
    xs = set()
    k = int(math.ceil(REACH_R / rc.CELL))
    for (i, j) in cells:
        for a in range(-k, k + 1):
            for b in range(-k, k + 1):
                xs.add((i + a, j + b))
    out = []
    sub = int(round(rc.CELL / step))
    rng = np.random.default_rng(7)
    for (i, j) in sorted(xs):
        cx, cz = w.cell_xz(i, j)
        for a in range(sub):
            for b in range(sub):
                x = cx - rc.CELL / 2 + (a + 0.5) * step
                z = cz - rc.CELL / 2 + (b + 0.5) * step
                if not g.room_of(x, z):
                    continue
                ys, ny = g.C.heights(x, z, 10.0, 24.0)
                nmin = math.cos(math.radians(SLOPE_MAX)) if g.outdoor(x, z) else 0.995
                for y in sorted(set(np.round(ys[ny >= nmin], 3))):
                    out.append((x, float(y), z))
    print(f"{len(out)} raw surface points", flush=True)
    good = []
    for n, (x, y, z) in enumerate(out):
        ok, info = contact(g, x, z, y, slope_ok=g.outdoor(x, z))
        if not ok:
            continue
        h, d = reach(g, x, y, z)
        if h is None:
            continue
        lift = y - h
        kind = "floor" if lift < 0.12 else "low" if lift < 0.35 else "shelf"
        if info.get("snow") and kind != "floor":     # deformed snow is ground only (see select)
            continue
        if kind == "floor":     # floor items only against something (a wall / shelf foot within 0.45 m at shin height), never in the middle of a room
            if not g.C.box_hit(np.array([x - 0.6, y + 0.08, z - 0.6]), np.array([x + 0.6, y + 0.45, z + 0.6])):
                continue
        good.append({"pos": [round(x, 3), round(y, 3), round(z, 3)], "dy": info["dy"], "normal": info["normal"], "lift": round(lift, 2), "kind": kind,
                     "room": g.room_of(x, z), "indoor": g.indoor(x, y, z), "gap": info["gap"]})
        if len(good) % 200 == 0:
            print(f"  {len(good)} good of {n + 1}", flush=True)
    print(f"{len(good)} contact-checked candidate points")
    return good


# ------------------------------------------------------------------------------------------------ items and budget
# per-spot candidate pools (weights). Units: an ingredient pickup = 2 units (itemspots.c isp_count), a recipe needs 4 of each ingredient
# (TLOU2 crafting-system.bin): shiv = binding 4 + blade 4, molotov = alcohol 4 + rag 4 -> one pickup = a quarter of a molotov / shiv.
POOLS = {
    # ammo-pistol / ammo-rifle are ammo CLASSES (itemspots.c isp_ammo_for_me): the pistol / long gun ammo of the player who sees the pickup; no
    # ammo-shotgun / vepr / mpx5 here (a fixed ammo type was a placeholder box for most players)
    "shelf": {"rag": 4, "alcohol": 4, "binding": 3, "blade": 3, "canister": 2, "explosive": 2, "health-small": 1, "ammo-pistol": 1},
    "low":   {"rag": 4, "alcohol": 3, "binding": 3, "blade": 3, "canister": 2, "explosive": 2, "ammo-pistol": 1, "ammo-rifle": 1},
    "floor": {"rag": 3, "alcohol": 3, "binding": 3, "blade": 3, "canister": 2, "explosive": 2, "ammo-pistol": 2, "ammo-rifle": 2},
    "medkit": {"health-kit": 2, "health-small": 3},
    "util": {"molotov": 2, "smoke-bomb": 2, "shiv": 2, "pipe-bomb": 1},
}
FILL = {"shelf": 30, "low": 30, "floor": 30, "medkit": 45, "util": 25}       # % per roll
RESP = {"shelf": 90, "low": 90, "floor": 90, "medkit": 120, "util": 150}     # s until the spot rolls again


def budget(spots):
    """expected pickups per room: molotov / shiv worth (expected and 'lucky' = every spot of the room filled, ingredients in the pool's mix)"""
    rows = {}
    for s in spots:
        r = rows.setdefault(s["room"], {"spots": 0, "shared": 0, "exp_items": 0.0, "mol": 0.0, "shiv": 0.0, "mol_max": 0.0, "shiv_max": 0.0, "heal": 0.0, "ammo": 0.0})
        pool = POOLS[s["pool"]]
        tot = sum(pool.values())
        f = FILL[s["pool"]] / 100.0
        r["spots"] += 1
        r["shared"] += 1 if s.get("shared") else 0
        r["exp_items"] += f
        pm = (pool.get("rag", 0) + pool.get("alcohol", 0)) / tot
        ps = (pool.get("binding", 0) + pool.get("blade", 0)) / tot
        r["mol"] += f * pm * 0.25            # one pickup = 2 units = 1/4 molotov
        r["shiv"] += f * ps * 0.25
        r["mol_max"] += pm * 0.25
        r["shiv_max"] += ps * 0.25
        r["heal"] += f * (pool.get("health-kit", 0) + pool.get("health-small", 0)) / tot
        r["ammo"] += f * sum(v for k, v in pool.items() if k.startswith("ammo")) / tot
    return rows


def lucky(spots, room, q=0.9, n=20000, seed=3):
    """q-quantile of the molotov / shiv worth found when every spot of the room is visited once (Monte Carlo of the rolls)"""
    rng = np.random.default_rng(seed)
    S = [s for s in spots if s["room"] == room]
    mol, shv = np.zeros(n), np.zeros(n)
    for s in S:
        pool = POOLS[s["pool"]]
        items, w = list(pool), np.array(list(pool.values()), float)
        fill = rng.random(n) < FILL[s["pool"]] / 100.0
        pick = rng.choice(len(items), n, p=w / w.sum())
        for k, it in enumerate(items):
            m = fill & (pick == k)
            if it in ("rag", "alcohol"):
                mol += m * 0.25
            if it in ("binding", "blade"):
                shv += m * 0.25
    return float(np.quantile(mol, q)), float(np.quantile(shv, q)), float(mol.mean()), float(shv.mean())


def select(g, cand, plan_rooms):
    """per room: `want` spots, shelves / counters first, then low surfaces, the floor (against something) only for what is left; farthest-point
    sampling inside each kind (spread over the room), never closer than SPACING_RAISED / SPACING m to another loot spot"""
    chosen = []
    for room, want in plan_rooms.items():
        C = [c for c in cand if c["room"] == room]
        if not C:
            print(f"  {room}: no candidates")
            continue
        by = {k: [c for c in C if c["kind"] == k] for k in ("shelf", "low", "floor")}
        sel = []

        def take(kind, n):
            got = 0
            pool = list(by[kind])
            spacing = SPACING if kind == "floor" else SPACING_RAISED
            while got < n and pool:
                P = np.array([c["pos"] for c in pool])[:, [0, 2]]
                others = np.array([c["pos"] for c in chosen + sel])[:, [0, 2]] if chosen or sel else None
                if others is None:
                    dmin = np.full(len(pool), 99.0)
                else:
                    dmin = np.sqrt(((P[:, None, :] - others[None, :, :]) ** 2).sum(2)).min(1)
                ok = dmin >= spacing
                if not ok.any():
                    break
                score = np.where(ok, np.minimum(dmin, 6.0) - 20.0 * np.abs([c["gap"] for c in pool]), -1e9)
                k = int(np.argmax(score))
                c = pool.pop(k)
                x, y, z = c["pos"]
                yr, _ = g.C.ray_down(x, z, y + RAY_UP, RAY_LEN)        # re-validated with the current rules (the candidate cache may be older)
                ok, info = contact(g, x, z, yr, slope_ok=g.outdoor(x, z)) if yr is not None and abs(yr - y) <= 0.002 else (False, {})
                if not ok or (info.get("snow") and c["kind"] != "floor"):      # deformed snow is ground only: on a car / crate a render surface under
                    continue                                                      # the collision is a coarse hull, the item would float above the art
                c = dict(c, dy=info["dy"], normal=info["normal"], gap=info["gap"])
                sel.append(c)
                got += 1
            return got
        # Spots were mostly on the ground. Shelves / counters first, then low surfaces (crates, cars), the floor (against a wall) only for
        # what the raised surfaces of the room cannot hold
        # A/B (loot spawns were still on the floor): the floor only tops up a room by FLOOR_MAX_IN (indoors) / FLOOR_MAX_OUT
        # (the snow lot: ground is all there is) - a room with few raised surfaces gets fewer items instead of a floor full of them
        out_room = sum(1 for c in C if g.outdoor(c["pos"][0], c["pos"][2])) * 2 > len(C)
        got = {}
        for k in ("shelf", "low", "floor"):
            n = want - len(sel)
            if k == "floor":
                n = min(n, FLOOR_MAX_OUT if out_room else FLOOR_MAX_IN)
            got[k] = take(k, n)
        print(f"  {room}: {len(sel)} of {want} wanted ({len(C)} candidates; shelf {got['shelf']}, low {got['low']}, floor {got['floor']})")
        chosen += sel
    return chosen


def yaw_quat(yaw, normal=None):
    """yaw about world up, then tilted so the item's up is the surface normal (q = tilt * yaw)"""
    qy = np.array([0.0, math.sin(yaw / 2), 0.0, math.cos(yaw / 2)])
    if normal is not None:
        n = np.asarray(normal, float)
        ax = np.cross([0.0, 1.0, 0.0], n)
        sn = np.linalg.norm(ax)
        if sn > 1e-6:
            ang = math.atan2(sn, n[1])
            ax = ax / sn * math.sin(ang / 2)
            qt = np.array([ax[0], ax[1], ax[2], math.cos(ang / 2)])
            x1, y1, z1, w1 = qt
            x2, y2, z2, w2 = qy
            qy = np.array([w1 * x2 + x1 * w2 + y1 * z2 - z1 * y2, w1 * y2 - x1 * z2 + y1 * w2 + z1 * x2,
                           w1 * z2 + x1 * y2 - y1 * x2 + z1 * w2, w1 * w2 - x1 * x2 - y1 * y2 - z1 * z2])
    return [round(float(v), 6) for v in qy]


def plan(key, write=False, want=None):
    g = Geo(key)
    cp = os.path.join(CACHE, f"loot-{key}-cand.json")
    if os.path.exists(cp) and os.path.getmtime(cp) > os.path.getmtime(npz_path(key)):
        cand = json.load(open(cp))
    else:
        cand = candidates(g)
        json.dump(cand, open(cp, "w"))
    from collections import Counter
    print("candidates per room / kind:", dict(Counter((c["room"], c["kind"]) for c in cand)))
    want = want or {r: n for r, n in MAPS[key].get("room_spots", {}).items()} or {name: 10 for name, _ in MAPS[key]["rooms"]}
    sel = select(g, cand, want)
    rng = np.random.default_rng(23)
    spots = []
    # medkit / util spots: the most sheltered shelf / low spot of the rooms named in the map setup, else nothing
    special = MAPS[key].get("special", {})
    for c in sel:
        spots.append(dict(c, pool=c["kind"]))
    for sp_pool, rooms in special.items():
        for room in rooms:
            cands = sorted([s for s in spots if s["room"] == room and s["pool"] in ("shelf", "low", "floor")],
                           key=lambda s: (not s["indoor"], s["pool"] == "floor", abs(s["gap"])))
            if cands:
                cands[0]["pool"] = sp_pool
    # shared / unique: half of the ingredient spots of each room shared, alternating by a shuffled order
    for room in {s["room"] for s in spots}:
        S = [s for s in spots if s["room"] == room and s["pool"] in ("shelf", "low", "floor")]
        rng.shuffle(S)
        for k, s in enumerate(S):
            s["shared"] = k % 2 == 0
    out = []
    for s in spots:
        pool = POOLS[s["pool"]]
        yaw = float(rng.uniform(-math.pi, math.pi))
        out.append({"pos": s["pos"], "quat": yaw_quat(yaw, s.get("normal")), "items": [{"item": it, "weight": w} if w != 1 else {"item": it} for it, w in pool.items()],
                    "group": "loot", "room": s["room"], "shared": bool(s.get("shared")), "fill": FILL[s["pool"]], "resp": RESP[s["pool"]],
                    "dy": s["dy"], "surface": f"{s['kind']} {s['lift']:+.2f} m", "pool": s["pool"]})
    B = budget(out)
    print(f"\n{len(out)} loot spots")
    print(f"{'room':18s} spots shared  E[items]  E[molotov] lucky90  E[shiv] lucky90   heal  ammo")
    for room, r in sorted(B.items()):
        l_m, l_s, _, _ = lucky(out, room)
        print(f"{room:18s} {r['spots']:5d} {r['shared']:6d} {r['exp_items']:8.2f} {r['mol']:10.2f} {l_m:7.2f} {r['shiv']:8.2f} {l_s:7.2f} {r['heal']:6.2f} {r['ammo']:5.2f}")
    if write:
        import itemspots as IS
        p = os.path.join(DATA, f"{key}-itemspots.json")
        old = json.load(open(p))["spots"] if os.path.exists(p) else []
        hand = [s for s in old if s.get("group") != "loot"]
        for s in out:
            s.pop("pool")
        IS.save(key, hand + out)
        print(f"wrote {_rel(p)}: {len(hand)} hand spot(s) + {len(out)} loot spot(s); tools/ext/itemspots.h")
    return out


def check(key, fix=False):
    """every spot of data/<key>-itemspots.json measured again; fix=True writes the measured contact correction (dy) of the spots that pass"""
    import itemspots as IS
    g = Geo(key)
    p = os.path.join(DATA, f"{key}-itemspots.json")
    d = json.load(open(p))
    bad, fixed = 0, 0
    for n, s in enumerate(d["spots"]):
        x, y, z = s["pos"]
        yr, _ = g.C.ray_down(x, z, y + RAY_UP, RAY_LEN)
        if yr is None:
            print(f"spot {n + 1} {s['pos']}: the runtime ray finds no surface")
            bad += 1
            continue
        ok, info = contact(g, x, z, yr, slope_ok=g.outdoor(x, z))
        h, dd = reach(g, x, yr, z)
        msg = f"spot {n + 1:3d} {s.get('room', ''):18s} {s.get('surface', ''):14s} ray {yr - y:+.3f}  "
        if ok and h is not None and fix and abs((s.get("dy") or 0) - info["dy"]) > 0.0005:
            s["dy"] = info["dy"]
            fixed += 1
        if not ok or h is None or abs((s.get("dy") or 0) - info.get("dy", 0)) > 0.003:
            bad += 1
            print(msg + f"PROBLEM {info.get('why', '')} {'' if h is not None else 'unreachable'} dy stored {s.get('dy')} measured {info.get('dy')}")
    print(f"{len(d['spots'])} spots, {bad} problem(s)")
    if fixed:
        IS.save(key, d["spots"])
        print(f"{fixed} contact correction(s) re-measured -> {_rel(p)} + tools/ext/itemspots.h")
    return bad


# ------------------------------------------------------------------------------------------------ interrogation safes
CRATE = (0.657, 0.254, 0.491)      # rl-cache-crate-military half x, half z, height (front = +z, back against the wall)


def team_starts(key):
    """centroid of each team's intro spawn points (data/<key>-spawns.json intro0 / intro1)"""
    sp = json.load(open(os.path.join(DATA, f"{key}-spawns.json")))
    return [list(np.mean([p["pos"] for p in sp[f"intro{t}"]], 0)) for t in (0, 1)]


def safe_candidates(g, team):
    """crate spots of a team's half: stand floor, sheltered (a roof, or walls on three sides), back flush against a wall (2 cm), footprint +
    kneel apron clear, floor flat under the four corners"""
    w, cells = g.flood()
    st = team_starts(g.key)
    out = []
    for (i, j), hs in cells.items():
        cx0, cz0 = w.cell_xz(i, j)
        for h in hs:
            d_own = math.hypot(cx0 - st[team][0], cz0 - st[team][2])
            d_en = math.hypot(cx0 - st[1 - team][0], cz0 - st[1 - team][2])
            if not (d_own < 0.8 * d_en and d_own > 12.0):
                continue
            for yaw in (0.0, math.pi / 2, math.pi, -math.pi / 2):
                fx, fz = round(math.sin(yaw), 6), round(math.cos(yaw), 6)          # front (lid / kneel side) direction; the back goes against the wall
                rx, rz = fz, -fx
                ts = [g.C.seg_t((cx0 + rx * o, h + y0, cz0 + rz * o), (cx0 + rx * o - fx * 1.0, h + y0, cz0 + rz * o - fz * 1.0)) for o in (-0.55, 0.0, 0.55) for y0 in (0.25, 0.8)]
                if any(t is None for t in ts) or max(ts) - min(ts) > 0.04:
                    continue                                                        # no straight wall behind the whole crate
                back = min(ts) - CRATE[1] - 0.02
                cx, cz = cx0 - fx * back, cz0 - fz * back
                corners = [(cx + rx * a * CRATE[0] + fx * b * CRATE[1], cz + rz * a * CRATE[0] + fz * b * CRATE[1]) for a in (-1, 1) for b in (-1, 1)]
                fl = [g.C.ray_down(px, pz, h + 0.3, 0.6)[0] for px, pz in corners]
                if any(f is None or abs(f - h) > 0.04 for f in fl):
                    continue
                lo = np.array([min(c[0] for c in corners) + 0.02, h + 0.08, min(c[1] for c in corners) + 0.02])
                hi = np.array([max(c[0] for c in corners) - 0.02, h + CRATE[2] + 0.4, max(c[1] for c in corners) - 0.02])
                if g.C.box_hit(lo, hi):
                    continue
                ap = (cx + fx * (CRATE[1] + 0.6), cz + fz * (CRATE[1] + 0.6))       # where the player kneels
                if g.C.box_hit(np.array([ap[0] - 0.35, h + 0.3, ap[1] - 0.35]), np.array([ap[0] + 0.35, h + 1.7, ap[1] + 0.35])):
                    continue
                roof = g.indoor(cx, h, cz)
                sides = sum(g.C.seg_blocked((cx, h + 1.0, cz), (cx + dx * 4.0, h + 1.0, cz + dz * 4.0)) for dx, dz in ((rx, rz), (-rx, -rz), (fx, fz)))
                if not roof and sides < 2:
                    continue
                out.append({"pos": [round(cx, 3), round(h, 3), round(cz, 3)], "yaw": yaw, "d_own": d_own, "d_en": d_en, "room": g.room_of(cx, cz),
                            "roof": roof, "sides": int(sides)})
    return out


def safes(key, write=False):
    g = Geo(key)
    sp = json.load(open(os.path.join(DATA, f"{key}-spawns.json")))
    boxes = [b["pos"] for b in sp["boxes"]]
    resp = [r["pos"] for r in sp["respawns"]]
    C = [safe_candidates(g, t) for t in (0, 1)]
    for t in (0, 1):
        C[t] = [c for c in C[t] if c["roof"]]
        C[t] = [c for c in C[t] if min(math.dist(c["pos"], b) for b in boxes) >= 6.0 and min(math.dist(c["pos"], r) for r in resp) >= 4.0]
        print(f"team {t}: {len(C[t])} wall-tucked indoor candidates")

    def sees(a, b):
        for ha in (0.5, 1.0, 1.6):
            for hb in (0.5, 1.0, 1.6):
                if not g.C.seg_blocked((a[0], a[1] + ha, a[2]), (b[0], b[1] + hb, b[2])):
                    return True
        return False
    # pick 3 per team, different rooms when possible, far apart, and no line of sight to any pick of the other team
    rng = np.random.default_rng(5)
    picks = [[], []]
    for rnd in range(3):
        for t in (0, 1):
            best = None
            for c in C[t]:
                if any(math.dist(c["pos"], p["pos"]) < 7.0 for p in picks[t]):
                    continue
                if any(sees(c["pos"], p["pos"]) for p in picks[1 - t]):
                    continue
                rooms = {p["room"] for p in picks[t]}
                sc = (c["d_en"] - c["d_own"]) * 0.5 + (10.0 if c["room"] not in rooms else 0.0) + min(min((math.dist(c["pos"], p["pos"]) for p in picks[t]), default=0), 25.0) * 0.4                     + (6.0 if c["roof"] else 0.0) + 2.0 * c["sides"]
                if best is None or sc > best[0]:
                    best = (sc, c)
            if best:
                picks[t].append(best[1])
    for t in (0, 1):
        for p in picks[t]:
            p["sees_enemy"] = [k for k, q in enumerate(picks[1 - t]) if sees(p["pos"], q["pos"])]
            print(f"team {t} safe {p['pos']} yaw {math.degrees(p['yaw']):.0f} {p['room']}: own start {p['d_own']:.0f} m, enemy start {p['d_en']:.0f} m, sees enemy safes {p['sees_enemy']}")
    if write:
        lp = os.path.join(DATA, f"{key}-lockboxes.json")
        d = json.load(open(lp)) if os.path.exists(lp) else {"key": key}
        d["method"] = "tools/maps/loot_place.py safes: indoors, back flush to a wall, own half, >= 6 m from boxes, >= 4 m from respawns, no line of sight to any enemy candidate (collision rays 0.5/1.0/1.6 m)"
        d["teams"] = [[{"name": f"lockbox-{t}-{k}", "pos": p["pos"], "yaw_deg": round(math.degrees(p["yaw"]) % 360, 1), "room": p["room"],
                        "own_start_m": round(p["d_own"], 1), "enemy_start_m": round(p["d_en"], 1)} for k, p in enumerate(picks[t])] for t in (0, 1)]
        with open(lp, "w", newline="\n") as f:
            json.dump(d, f, indent=1)
        print("wrote", _rel(lp))
    return picks


# ------------------------------------------------------------------------------------------------ mesh bounds
def meshes():
    import ndpak
    import prop_bounds as pb
    rows = {}
    for a in ("all-standard-pickups", "all-ammo-pickups"):
        pk = ndpak.Pak(pb.actor_pak(a))
        for sm in pk.submeshes:
            P = pk.positions(sm)
            if P is None or "LOD1" in sm["name"]:
                continue
            n = sm["name"].split("|")
            k = a + ": " + "|".join(n[:3])[-70:]
            lo, hi = P.min(0), P.max(0)
            r = rows.setdefault(k, [lo, hi])
            r[0], r[1] = np.minimum(r[0], lo), np.maximum(r[1], hi)
    for k, (lo, hi) in sorted(rows.items()):
        print(f"{k:95s} y {lo[1]:+.3f} .. {hi[1]:+.3f}  x {hi[0] - lo[0]:.3f}  z {hi[2] - lo[2]:.3f}")


# ------------------------------------------------------------------------------------------------ plot
def plot(key, png):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.patches import Rectangle
    g = Geo(key)
    w, cells = g.flood()
    cfg = MAPS[key]
    fig = plt.figure(figsize=(16, 13))
    ax = fig.add_axes([0.03, 0.04, 0.55, 0.92])
    import reach_check as rc
    xs = [w.cell_xz(i, j) for (i, j) in cells]
    ax.scatter([p[0] for p in xs], [p[1] for p in xs], s=4, c="#cfd8dc", marker="s", linewidths=0, zorder=1)
    for name, (x0, x1, z0, z1) in cfg["rooms"]:
        ax.add_patch(Rectangle((x0, z0), x1 - x0, z1 - z0, fill=False, ec="#7e57c2", lw=0.8, ls="--", zorder=2))
        ax.text(x0 + 0.4, z1 - 1.2, name, fontsize=7, color="#5e35b1", zorder=6)
    d = json.load(open(os.path.join(DATA, f"{key}-itemspots.json")))
    col = {"shelf": "#2e7d32", "low": "#f9a825", "floor": "#6d4c41"}
    for s in d["spots"]:
        x, y, z = s["pos"]
        it = {i["item"] for i in s["items"]}
        if "health-kit" in it:
            c, m = "#e53935", "P"
        elif "molotov" in it:
            c, m = "#ff6f00", "*"
        else:
            c, m = col.get((s.get("surface") or "shelf").split()[0], "#2e7d32"), "o"
        ax.scatter([x], [z], s=46 if m != "o" else 26, c=c if s.get("shared") or m != "o" else "white", edgecolors=c, linewidths=1.4, marker=m, zorder=5)
    sat = json.load(open(os.path.join(DATA, f"{key}-satchels.json"))).get("spots", []) if os.path.exists(os.path.join(DATA, f"{key}-satchels.json")) else []
    for s in sat:
        ax.scatter([s["pos"][0]], [s["pos"][2]], s=40, c="#8d6e63", marker="D", zorder=5)
    sp = json.load(open(os.path.join(DATA, f"{key}-spawns.json")))
    for b in sp["boxes"]:
        ax.scatter([b["pos"][0]], [b["pos"][2]], s=90, c="#ffb300", marker="s", edgecolors="k", zorder=6)
    for r in sp["respawns"]:
        ax.scatter([r["pos"][0]], [r["pos"][2]], s=60, c="#43a047", marker="^", edgecolors="k", zorder=6)
    for t, c in ((0, "#d32f2f"), (1, "#1565c0")):
        for p in sp[f"intro{t}"]:
            ax.scatter([p["pos"][0]], [p["pos"][2]], s=40, c=c, marker="o", edgecolors="k", zorder=6)
    lb = json.load(open(os.path.join(DATA, f"{key}-lockboxes.json")))
    for t, c in ((0, "#d32f2f"), (1, "#1565c0")):
        for p in lb["teams"][t]:
            ax.scatter([p["pos"][0]], [p["pos"][2]], s=170, c=c, marker="h", edgecolors="k", linewidths=1.5, zorder=7)
            ax.text(p["pos"][0] + 0.8, p["pos"][2] + 0.5, f"safe T{t}", fontsize=8, color=c, weight="bold", zorder=7)
    ax.set_aspect("equal")
    b = cfg["box"]
    ax.set_xlim(b[0], b[1])
    ax.set_ylim(b[2], b[3])
    ax.grid(alpha=0.25)
    loot = [s for s in d["spots"] if s.get("group") == "loot"]
    ax.set_title(f"{key}: {len(loot)} loot spots (filled = shared, hollow = unique; green shelf, yellow low surface, brown floor), "
                 f"red + = health kit, orange * = util, diamonds = satchels,\nsquares = supply boxes, triangles = respawns, hexagons = interrogation safes", fontsize=9)
    # side views: 6 spots, the render triangles of a 1.2 m slab around the spot, x/y
    picks = []
    for kind in ("shelf", "shelf", "low", "floor", "shelf", "low"):
        for s in loot:
            if (s.get("surface") or "").startswith(kind) and s not in picks:
                picks.append(s)
                break
    for k, s in enumerate(picks[:6]):
        a2 = fig.add_axes([0.62 + (k % 2) * 0.19, 0.69 - (k // 2) * 0.31, 0.17, 0.26])
        x, y, z = s["pos"]
        lo, hi = np.array([x - 0.6, y - 0.4, z - 0.04]), np.array([x + 0.6, y + 0.6, z + 0.04])
        ids = g.R.near(lo[0], lo[2], hi[0], hi[2])
        T = g.R.T[ids]
        m = ((T.max(1) >= lo) & (T.min(1) <= hi)).all(1)
        from matplotlib.collections import PolyCollection
        a2.add_collection(PolyCollection([t[:, [0, 1]] for t in T[m]], facecolors="#b0bec5", edgecolors="#78909c", linewidths=0.2))
        idc = g.C.near(lo[0], lo[2], hi[0], hi[2])
        TC = g.C.T[idc]
        mc = ((TC.max(1) >= lo) & (TC.min(1) <= hi)).all(1)
        for t in TC[mc]:
            a2.plot(list(t[:, 0]) + [t[0, 0]], list(t[:, 1]) + [t[0, 1]], color="#e53935", lw=0.5)
        ys = y + (s.get("dy") or 0) + 0.003
        a2.add_patch(Rectangle((x - 0.084, ys), 0.168, 0.056, fc="#ffd54f", ec="k", lw=0.8, zorder=5))     # the health-kit / ingredient box size
        a2.add_patch(Rectangle((x - 0.043, ys), 0.086, 0.201, fc="none", ec="#6a1b9a", lw=0.8, ls="--", zorder=5))   # the tallest (alcohol) outline
        a2.set_xlim(x - 0.45, x + 0.45)
        a2.set_ylim(y - 0.25, y + 0.45)
        a2.set_aspect("equal")
        a2.set_title(f"{s.get('room')} {s.get('surface')}\n({x:.2f}, {z:.2f}) dy {s.get('dy', 0):+.3f}", fontsize=7)
        a2.tick_params(labelsize=6)
    fig.text(0.62, 0.05, "side views (x / y, 8 cm slab): grey = render, red = collision, yellow = 17 x 6 cm pickup, purple dashed = the 20 cm alcohol bottle", fontsize=7)
    fig.savefig(png, dpi=110)
    print("->", png)


if __name__ == "__main__":
    a = sys.argv[1:]
    if not a:
        print(__doc__)
    elif a[0] == "cache":
        cache(a[1])
    elif a[0] == "meshes":
        meshes()
    elif a[0] == "plan":
        plan(a[1], "--write" in a)
    elif a[0] == "check":
        sys.exit(1 if check(a[1], "--fix" in a) else 0)
    elif a[0] == "safes":
        safes(a[1], "--write" in a)
    elif a[0] == "plot":
        plot(a[1], a[2])
