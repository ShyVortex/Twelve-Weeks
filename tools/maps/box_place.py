"""Supply box placement planner: boxes against walls / cars / cover, spread over ROOMS instead of hallways, spaced apart.

  python box_place.py plan <key>... | all      # analyse + propose: re/maps/boxplace/<key>.json, <key>.png (old red, new green, spawns blue,
                                               #   walls grey) and <key>-rooms.png (rooms tinted by traffic, box counts per room)
  python box_place.py apply <key>... | all     # write the proposal into tools/maps/data/<key>-spawns.json, the committed pak
                                               #   (tools/features/levels/to1-pvp-<key>-ingame.pak, boxes + their item positions patched in
                                               #   place), the map spec's fixed_boxes (sp_maps.json) and the layout snapshot
  python box_place.py navs                     # (re)dump the navmeshes the planner needs (re/maps/seeds/<key>-nav.json, headless reader)

Offline only: the map's navmesh (tools/maps/layoutlib.py Ctx: walkable play space, one-way ground excluded), the map spec's props and the
level's spawner dump (doors / gates) - no game, no GPU.  There is no collision geometry offline, so a WALL is a navmesh boundary edge that
has no ground just beyond it (a seam between two navmeshes, a doorway bridge, is not a wall); cars, counters and furniture are holes in
the navmesh, so they are boundary edges too.

Model of the crate (NoR rl-cache-crate-military, measured in re/nr-supply-box.md: 1.314 x 0.493 m, hinge/back -z, interact +z, >= 0.9 m free in front, >= 0.3 m behind - the navmesh edge already stands ~0.3 m off the wall): CRATE_L x CRATE_W = 1.314 x 0.493 m footprint, the
long side along local X, the front (the side you open it from) on local +Z, origin in the middle.  A box against a wall therefore has its
yaw = the wall normal (pointing into the room), its centre CRATE_W / 2 + 0.07 m off the navmesh edge.  Change CRATE_L / CRATE_W (or the
env T2R_CRATE=LxW) when the real numbers arrive; the planner then re-runs.

What it does, per map
 1. RASTER: the walkable play space as a 0.5 m node graph (floors kept apart), clearance = distance to the nearest non-walkable cell.
 2. ROOMS: watershed of the clearance field (basins with a prominence < ROOM_PROM merge): a room is a clearance peak, a doorway a saddle.
    Regions are classified room / hallway (narrow and long) and given a TRAFFIC index = share of the weighted shortest paths between
    the team starts and the respawns that run through them.
 3. CANDIDATES: every navmesh wall edge sampled every 0.5 m (+ corner tucks): crate fully on flat ground, back face flush with the wall,
    no ground just behind it, 2.4 m of open floor in front (not a corridor choke), no door / gap next to it, clear of the map spec's props.
    Quality q = flush 0.55 + corner 0.25 + both ends tucked 0.05 + depth bonus, minus penalties for a doorway-ish side / shallow front.
 4. CHOICE: the old boxes are the starting point (each snapped to the best wall spot near it); a swap search then maximises
       3 q  +  room coverage (+2.5..5.5 per room with a box)  -  extra boxes in one room  -  hallway / traffic  -  unfair distance to the
       teams  -  movement  +  keep bonus for hand-placed boxes
    under the hard rules: path distance between boxes >= SPACING (20 m, relaxed in 2 m steps if a small map cannot hold it), >= 8 m from
    intro spawns, >= 6 m from respawns, floors quotas of the map spec, in the main interior when it has one.
 5. Old boxes are flagged: OPEN (no wall within ~0.6 m of the crate), PAIR (another box closer than SPACING), INTRO (close to a team
    start), HALL (in a hallway / high traffic), and compared with the new set (kept / aligned / moved / moved to another room).
"""
import json
import math
import os
import re
import subprocess
import sys

import numpy as np
from scipy.sparse import csr_matrix
from scipy.sparse.csgraph import dijkstra
from scipy.spatial import cKDTree
from scipy.optimize import linear_sum_assignment

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.dirname(HERE))
import layoutlib as L  # noqa: E402
import layoutenv as E  # noqa: E402
import layoutwalk as W  # noqa: E402
from layoutlib import Ctx, yaw_quat  # noqa: E402

ROOT = L.ROOT
OUT = os.path.join(ROOT, "re", "maps", "boxplace")
MAPS = ["train-station", "hospital-ellie", "wilds-houses", "capitol-shops", "into-the-city", "overpass"]
SAT_MAPS = MAPS + ["chase", "jackson-market"]
LB_MAPS = SAT_MAPS + ["p1-bookstore"]      # Interrogation lockbox maps (lockboxes())
SAT_L, SAT_W, SAT_FRONT = 0.45, 0.30, 1.6   # supply satchel footprint; open floor in front from its centre (0.6 m free + half depth + margin)
SAT_BOX_MIN, SAT_SPREAD, SAT_INTRO = 14.0, 20.0, 8.0

_cr = os.environ.get("T2R_CRATE", "1.314x0.493").lower().split("x")
CRATE_L, CRATE_W = float(_cr[0]), float(_cr[1])
BACK_GAP = 0.07            # crate back face to the navmesh edge (the navmesh edge itself already stands ~0.3 m off the real wall)
SPACING = 20.0             # path metres between two boxes (10 m was far too close)
EUC_MIN = 12.0             # and straight metres (a box right above another one on the next floor)
INTRO_MIN = 8.0            # box to any intro spawn (straight)
RESP_MIN = 6.0             # box to any respawn (straight); < 10 m costs a little
FRONT_MIN = 2.4            # open floor in front of the wall, from the crate centre
FLAT = 0.07                # ground spread under the crate
ROOM_PROM = 1.0            # watershed prominence (m of clearance) for two rooms to stay separate
HOLD = 0.9                 # a hand placed box within this of a valid wall spot is kept (aligned to the wall)
OPEN_FLAG = 1.2            # old box: navmesh edge farther than this from the centre = "in the open"
DOORLIKE = ("door", "gate", "ladder", "vault", "mantle", "stair", "shutter", "garage")


# ------------------------------------------------------------------------------------------------ small helpers
def yaw_of(q):
    return L._quat_yaw(q)


def unit(yaw):
    return math.sin(yaw), math.cos(yaw)


def seed_file(key):
    return os.path.join(L.SEEDS, f"{key}.json")


def user_boxes(key, ctx):
    """indices of boxes placed by hand: the map spec's fixed_boxes whose note says user, hospital-ellie's first 6 (the NoR hospital's
    hand-placed boxes, spawns file note)"""
    out = set()
    lay = L.load_layout(key)
    fixed = ctx.spec.get("fixed_boxes") or []
    for k, b in enumerate(lay["boxes"]):
        for fb in fixed:
            if abs(fb["pos"][0] - b["pos"][0]) < 0.05 and abs(fb["pos"][2] - b["pos"][2]) < 0.05 and "user" in fb.get("note", ""):
                out.add(k)
    if key == "hospital-ellie":
        out |= set(range(6))
    return out


# ------------------------------------------------------------------------------------------------ raster + rooms
class Raster:
    """0.5 m node graph of the play space (mutual region: no one-way ground), clearance field, rooms, traffic"""

    def __init__(self, ctx):
        self.ctx = ctx
        g, nav = ctx.grid, ctx.nav
        try:
            ok = set(ctx.play) & set(W.mutual_region(ctx))
        except Exception:
            ok = set(ctx.play)
        self.ok = ok
        nodes, idx, cellnodes = [], {}, {}
        for (ix, iz), lst in g.cells.items():
            seen = []
            for k, (y, pi) in enumerate(lst):
                if pi not in ok or any(abs(y - s) < 0.12 for s in seen):
                    continue
                seen.append(y)
                nid = len(nodes)
                nodes.append((ix, iz, y, pi))
                cellnodes.setdefault((ix, iz), []).append((nid, y))
        self.n = n = len(nodes)
        c = g.CELL
        self.X = np.array([(a[0] + 0.5) * c for a in nodes])
        self.Z = np.array([(a[1] + 0.5) * c for a in nodes])
        self.Y = np.array([a[2] for a in nodes])
        self.poly = [a[3] for a in nodes]
        rows, cols, w = [], [], []
        boundary = np.zeros(n, bool)
        nb = [[] for _ in range(n)]
        for nid, (ix, iz, y, pi) in enumerate(nodes):
            for dx in (-1, 0, 1):
                for dz in (-1, 0, 1):
                    if dx == 0 and dz == 0:
                        continue
                    lst = cellnodes.get((ix + dx, iz + dz))
                    best = None
                    if lst:
                        best = min(lst, key=lambda t: abs(t[1] - y))
                        if abs(best[1] - y) > 0.6:
                            best = None
                    if best is None:
                        if dx == 0 or dz == 0:
                            boundary[nid] = True
                        continue
                    d = c * (1.4142 if dx and dz else 1.0)
                    rows.append(nid)
                    cols.append(best[0])
                    w.append(math.hypot(d, best[1] - y))
                    nb[nid].append(best[0])
        # the navmesh links polygons the 0.5 m cells do not touch (mantles, door seams, stitched gaps): join the raster components along them
        from scipy.sparse.csgraph import connected_components
        G0 = csr_matrix((w, (rows, cols)), shape=(n, n))
        ncomp, comp = connected_components(G0, directed=False)
        bypoly = {}
        for nid, a in enumerate(nodes):
            bypoly.setdefault(a[3], []).append(nid)
        added = set()
        for u in ok:
            for v in nav.adj[u]:
                if v not in ok or u not in bypoly or v not in bypoly:
                    continue
                cu, cv = comp[bypoly[u][0]], comp[bypoly[v][0]]
                if cu == cv or (min(cu, cv), max(cu, cv)) in added:
                    continue
                best = None
                for a_ in bypoly[u]:
                    for b_ in bypoly[v]:
                        dd = math.hypot(self.X[a_] - self.X[b_], self.Z[a_] - self.Z[b_], (self.Y[a_] - self.Y[b_]) * 1.0)
                        if best is None or dd < best[0]:
                            best = (dd, a_, b_)
                if best and best[0] < 5.0:
                    added.add((min(cu, cv), max(cu, cv)))
                    for x_, y_ in ((best[1], best[2]), (best[2], best[1])):
                        rows.append(x_)
                        cols.append(y_)
                        w.append(max(best[0], 0.5))
                        nb[x_].append(y_)
        self.nb = nb
        self.graph = csr_matrix((w, (rows, cols)), shape=(n, n))
        src = np.nonzero(boundary)[0]
        if len(src):
            self.clear = dijkstra(self.graph, directed=True, indices=src, min_only=True) + 0.25
        else:
            self.clear = np.full(n, 5.0)
        self.clear[~np.isfinite(self.clear)] = 5.0
        self.tree = cKDTree(np.c_[self.X, self.Z, self.Y * 1.5])
        self._rooms()

    def node_at(self, pos, maxd=1.2):
        d, i = self.tree.query([pos[0], pos[2], pos[1] * 1.5])
        return int(i) if d <= maxd * 1.0 + 0.0 else None

    # --- watershed rooms
    def _rooms(self):
        n, cl, nb = self.n, self.clear, self.nb
        order = np.argsort(-cl)
        lab = np.full(n, -1)
        parent, peak = [], []

        def find(a):
            while parent[a] != a:
                parent[a] = parent[parent[a]]
                a = parent[a]
            return a
        for u in order:
            roots = {}
            for v in nb[u]:
                if lab[v] >= 0:
                    r = find(lab[v])
                    roots[r] = peak[r]
            if not roots:
                lab[u] = len(parent)
                parent.append(len(parent))
                peak.append(cl[u])
                continue
            top = max(roots, key=lambda r: roots[r])
            lab[u] = top
            for r, pk in roots.items():
                if r != top and pk - cl[u] < ROOM_PROM:
                    parent[r] = top
        lab = np.array([find(a) for a in lab])
        # compact ids, merge small regions into the neighbour sharing the longest border
        ids = {r: k for k, r in enumerate(sorted(set(lab.tolist())))}
        lab = np.array([ids[a] for a in lab])
        cell_a = L.Grid.CELL ** 2
        for _ in range(8):
            cnt = np.bincount(lab, minlength=lab.max() + 1) * cell_a
            small = [r for r in range(len(cnt)) if 0 < cnt[r] < 9.0]
            if not small:
                break
            changed = False
            for r in small:
                border = {}
                for u in np.nonzero(lab == r)[0]:
                    for v in nb[u]:
                        if lab[v] != r:
                            border[lab[v]] = border.get(lab[v], 0) + 1
                if border:
                    tgt = max(border, key=lambda k: border[k])
                    lab[lab == r] = tgt
                    changed = True
            if not changed:
                break
        ids = {r: k for k, r in enumerate(sorted(set(lab.tolist())))}
        self.lab = np.array([ids[a] for a in lab])
        self.nreg = len(ids)
        self.regions = []
        for r in range(self.nreg):
            m = np.nonzero(self.lab == r)[0]
            area = len(m) * cell_a
            pk = float(self.clear[m].max())
            mean = float(self.clear[m].mean())
            width = 2 * max(pk, 0.4)
            length = area / width
            hall = width < 3.6 and length > 3.0 * width
            self.regions.append({"id": r, "area": round(area, 1), "peak": round(pk, 2), "mean": round(mean, 2), "hall": bool(hall),
                                 "cx": float(self.X[m].mean()), "cz": float(self.Z[m].mean()), "y": float(np.median(self.Y[m])),
                                 "n": int(len(m)), "traffic": 0.0, "boxes": 0})

    # --- distances / traffic
    def dist_from(self, nid):
        return dijkstra(self.graph, directed=True, indices=nid)

    def traffic(self, lay):
        """weighted shortest paths between the starts and the respawns, share per region (0..1, 1 = the busiest region)"""
        pts = []
        for tag, w in (("intro0", 3.0), ("intro1", 3.0)):
            c = L.centre(lay[tag])
            i = self.node_at(c, 3.0)
            if i is not None:
                pts.append((i, w, tag))
        for r in lay["respawns"]:
            i = self.node_at(r["pos"], 2.0)
            if i is not None:
                pts.append((i, 1.0, "resp"))
        tot = np.zeros(self.nreg)
        srcs = [p[0] for p in pts]
        D, P = dijkstra(self.graph, directed=True, indices=srcs, return_predecessors=True)
        for a in range(len(pts)):
            for b in range(a + 1, len(pts)):
                ia, wa, ta = pts[a]
                ib, wb, tb = pts[b]
                if ta == "resp" and tb == "resp":
                    w = 0.4
                elif ta != "resp" and tb != "resp":
                    w = 6.0
                else:
                    w = 1.0
                if not np.isfinite(D[a][ib]):
                    continue
                u, seen = ib, set()
                while u >= 0 and u != ia:
                    seen.add(int(self.lab[u]))
                    u = P[a][u]
                seen.add(int(self.lab[ia]))
                for r in seen:
                    tot[r] += w
        mx = np.percentile(tot[tot > 0], 90) if (tot > 0).any() else 1.0
        for r in self.regions:
            r["traffic"] = round(float(min(1.0, tot[r["id"]] / max(mx, 1e-9))), 3)
        self.d_start = [D[0], D[1]] if len(pts) >= 2 and pts[0][2] == "intro0" and pts[1][2] == "intro1" else None


# ------------------------------------------------------------------------------------------------ candidates
class Cand:
    __slots__ = ("pos", "yaw", "q", "node", "reg", "poly", "corner", "front", "note", "d0", "d1", "dist_old")


def wall_edges(ctx, ok):
    nav = ctx.nav
    ev = {}
    for i, p in enumerate(nav.polys):
        for k in range(len(p)):
            a, b = p[k], p[(k + 1) % len(p)]
            key = tuple(sorted(((round(a[0] * 4), round(a[1] * 2), round(a[2] * 4)), (round(b[0] * 4), round(b[1] * 2), round(b[2] * 4)))))
            ev.setdefault(key, []).append((i, a, b))
    out = []
    for v in ev.values():
        if len(v) == 1 and v[0][0] in ok:
            i, a, b = v[0]
            out.append((i, a, b))
    return out


def local_tangent(nav, x, z, y, r=0.8):
    """wall direction at (x, z): length weighted mean of the boundary edges within r (folded to a half plane)"""
    cs = nav.cellsz
    sx = sz = 0.0
    for dx in (-1, 0, 1):
        for dz in (-1, 0, 1):
            for a, b in nav.bgrid.get((int(x // cs) + dx, int(z // cs) + dz), ()):
                if abs((a[1] + b[1]) / 2 - y) > 1.3:
                    continue
                ex, ez = b[0] - a[0], b[2] - a[2]
                ln = math.hypot(ex, ez)
                if ln < 1e-3:
                    continue
                t = max(0.0, min(1.0, ((x - a[0]) * ex + (z - a[2]) * ez) / (ln * ln)))
                if math.hypot(x - (a[0] + t * ex), z - (a[2] + t * ez)) > r:
                    continue
                ux, uz = ex / ln, ez / ln
                if ux < 0 or (abs(ux) < 1e-9 and uz < 0):
                    ux, uz = -ux, -uz
                # double the angle so antiparallel edges add up
                ang = math.atan2(uz, ux)
                sx += ln * math.cos(2 * ang)
                sz += ln * math.sin(2 * ang)
    if abs(sx) + abs(sz) < 1e-6:
        return None
    ang = 0.5 * math.atan2(sz, sx)
    return math.cos(ang), math.sin(ang)


def make_candidates(key, ctx, ras, lay):
    nav, grid = ctx.nav, ctx.grid
    ok = ras.ok
    props = [(p["pos"][0], p["pos"][2], 1.8 if "invis" in p.get("art", "") or "block" in p.get("art", "") else 1.5) for p in ctx.spec.get("props", [])]
    door_pts = []
    if os.path.exists(seed_file(key)):
        for s in json.load(open(seed_file(key), encoding="utf-8-sig")):
            nm = ((s.get("name") or "") + " " + (s.get("art") or "")).lower()
            if any(h in nm for h in DOORLIKE):
                door_pts.append((s["pos"][0], s["pos"][1], s["pos"][2]))
    dtree = cKDTree([(p[0], p[2]) for p in door_pts]) if door_pts else None
    edges = wall_edges(ctx, ok)
    hl, hw = CRATE_L / 2, CRATE_W / 2
    pts = [(u, v) for u in (-hl, -hl / 2, 0.0, hl / 2, hl) for v in (-hw, 0.0, hw)]
    cands, seen = [], {}
    rej = {}

    def walk(x, z, y, dy=0.7):
        p = nav.poly_at(x, y, z, dy)
        return p if p is not None and p in ok else None

    for (pi, a, b) in edges:
        ex, ez = b[0] - a[0], b[2] - a[2]
        ln = math.hypot(ex, ez)
        if ln < 0.35:
            continue
        mx, mz = (a[0] + b[0]) / 2, (a[2] + b[2]) / 2
        cen = nav.cen[pi]
        # inward normal of this edge's polygon (rough), the local tangent refines the direction
        nx, nz = -ez / ln, ex / ln
        if nx * (cen[0] - mx) + nz * (cen[2] - mz) < 0:
            nx, nz = -nx, -nz
        offs = [s for s in np.arange(0.2, ln, 0.5)] if ln > 0.4 else [ln / 2]
        if ln > 1.5:
            offs += [0.62, ln - 0.62]
        for s in offs:
            bx, bz = a[0] + ex / ln * s, a[2] + ez / ln * s
            by = a[1] + (b[1] - a[1]) * (s / ln)
            tg = local_tangent(nav, bx, bz, by)
            if tg is None:
                tg = (ex / ln, ez / ln)
            tx, tz = tg
            # normal toward the polygon side
            n2x, n2z = -tz, tx
            if n2x * nx + n2z * nz < 0:
                n2x, n2z = -n2x, -n2z
            nxx, nzz = n2x, n2z
            yaw = math.atan2(nxx, nzz)
            ck = (round(bx * 2), round(bz * 2), round(by))
            if ck in seen:
                continue
            seen[ck] = 1
            off = hw + BACK_GAP
            cx, cz = bx + nxx * off, bz + nzz * off
            # the edge point may not be the closest wall point (curved walls): re-anchor on the exact distance
            if walk(cx, cz, by) is None:
                rej["centre off nav"] = rej.get("centre off nav", 0) + 1
                continue
            if not (ctx.inb(cx, cz, -2.0)):
                rej["bounds"] = rej.get("bounds", 0) + 1
                continue
            if any(math.hypot(cx - px, cz - pz) < pr for px, pz, pr in props):
                rej["prop"] = rej.get("prop", 0) + 1
                continue
            if dtree is not None:
                dd, di = dtree.query([cx, cz])
                if dd < 1.3 and abs(door_pts[di][1] - by) < 2.5:
                    rej["door"] = rej.get("door", 0) + 1
                    continue
            # footprint fully walkable (exact polygons) and flat
            ys = []
            bad = False
            for (u, v) in pts:
                px = cx + tx * u + nxx * v
                pz = cz + tz * u + nzz * v
                if walk(px, pz, by) is None:
                    bad = True
                    break
                g = grid.ground(px, pz, by, 0.5)
                if g:
                    ys.append(g[0])
            if bad:
                rej["footprint off nav"] = rej.get("footprint off nav", 0) + 1
                continue
            if ys and max(ys) - min(ys) > FLAT:
                rej["slope"] = rej.get("slope", 0) + 1
                continue
            # back face flush with the wall
            flush = max(nav.edge_clear(cx - nxx * hw + tx * u, cz - nzz * hw + tz * u, by) for u in (-hl, 0.0, hl))
            if flush > 0.32:
                rej["not flush"] = rej.get("not flush", 0) + 1
                continue
            # nothing walkable right behind the edge (a seam between navmeshes / a doorway is not a wall)
            seam = False
            for back in (0.3, 0.55):
                if walk(bx - nxx * back, bz - nzz * back, by, 0.6) is not None:
                    seam = True
                    break
            if seam:
                rej["seam"] = rej.get("seam", 0) + 1
                continue
            # open floor in front
            front = grid.run((cx, by, cz), yaw, 8.0, 0.25, 0.6)
            if front < FRONT_MIN:
                rej["front"] = rej.get("front", 0) + 1
                continue
            # both sides: wall continues (a gap = doorway / passage next to the crate)
            gap = 0
            corner = 0
            for sgn in (-1, 1):
                for dist, wgt in ((hl + 0.3, 2), (hl + 1.0, 1)):
                    sx, sz = cx + tx * sgn * dist, cz + tz * sgn * dist
                    if walk(sx, sz, by) is None:
                        if dist == hl + 0.3:
                            corner += 1
                        break
                    if nav.edge_clear(sx - nxx * (hw + BACK_GAP) + nxx * 0, sz - nzz * (hw + BACK_GAP), by) > 0.6 and \
                       nav.edge_clear(sx, sz, by) > off + 0.45:
                        gap += wgt
                        break
            if gap >= 2:
                rej["door next to"] = rej.get("door next to", 0) + 1
                continue
            # tucked into a corner: ground ends right beside a crate end
            tuck = 0
            for sgn in (-1, 1):
                if walk(cx + tx * sgn * (hl + 0.22), cz + tz * sgn * (hl + 0.22), by) is None:
                    tuck += 1
            q = 0.55 + 0.25 * min(tuck, 1) + 0.05 * (tuck >= 2)
            q += 0.08 if front >= 4.5 else 0.0
            q -= 0.12 if front < 3.2 else 0.0
            q -= 0.10 * gap
            q -= 0.15 * (flush > 0.2)
            n = ras.node_at((cx, by, cz), 0.9)
            if n is None:
                rej["no raster node"] = rej.get("no raster node", 0) + 1
                continue
            cd = Cand()
            cd.pos = (cx, E.snap_y(grid, (cx, by, cz)), cz)
            cd.yaw, cd.q, cd.node, cd.reg, cd.poly = yaw, q, n, int(ras.lab[n]), walk(cx, cz, by)
            cd.corner, cd.front, cd.note = tuck, front, ""
            cands.append(cd)
    # thin: one per 0.6 m cell and yaw bucket, best q
    best = {}
    for c in cands:
        k = (round(c.pos[0] / 0.6), round(c.pos[2] / 0.6), round(c.pos[1]), round(c.yaw / 0.6))
        if k not in best or c.q > best[k].q:
            best[k] = c
    out = list(best.values())
    return out, rej


# ------------------------------------------------------------------------------------------------ analysis of the OLD boxes
def analyse_old(key, ctx, ras, lay, users):
    nav = ctx.nav
    intro = [p["pos"] for t in ("intro0", "intro1") for p in lay[t]]
    resp = [p["pos"] for p in lay["respawns"]]
    B = lay["boxes"]
    nodes = [ras.node_at(b["pos"], 1.5) for b in B]
    rows = []
    for k, b in enumerate(B):
        p = b["pos"]
        edge = nav.edge_clear(p[0], p[2], p[1])
        reg = int(ras.lab[nodes[k]]) if nodes[k] is not None else -1
        R = ras.regions[reg] if reg >= 0 else None
        flags = []
        if edge > OPEN_FLAG:
            flags.append("OPEN")
        pair = []
        for j, q in enumerate(B):
            if j == k:
                continue
            d = math.dist(p, q["pos"])
            pd = None
            if nodes[k] is not None and nodes[j] is not None:
                pd = float(ras.dist_from(nodes[k])[nodes[j]])
            if (pd is not None and np.isfinite(pd) and pd < SPACING) or d < EUC_MIN:
                pair.append((j + 1, round(d, 1), round(pd, 1) if pd is not None and np.isfinite(pd) else None))
        if pair:
            flags.append("PAIR")
        di = min(math.dist(p, q) for q in intro)
        if di < INTRO_MIN * 1.25:
            flags.append("INTRO")
        if R and (R["hall"] or R["traffic"] > 0.75):
            flags.append("HALL")
        rows.append({"box": k + 1, "pos": [round(v, 2) for v in p], "edge": round(edge, 2), "region": reg,
                     "region_area": R["area"] if R else None, "region_hall": bool(R and R["hall"]), "traffic": R["traffic"] if R else None,
                     "to_intro": round(di, 1), "to_resp": round(min(math.dist(p, q) for q in resp), 1), "pairs": pair, "flags": flags,
                     "user": k in users})
    per = {}
    for r in rows:
        per[r["region"]] = per.get(r["region"], 0) + 1
    for r in rows:
        R = ras.regions[r["region"]] if r["region"] >= 0 else None
        if R and per[r["region"]] > 1 + int(R["area"] // 160):
            r["flags"].append("EXCESS")
    return rows


# ------------------------------------------------------------------------------------------------ selection
class Chooser:
    def __init__(self, key, ctx, ras, lay, cands, users, spacing, rows):
        self.key, self.ctx, self.ras, self.lay, self.cands, self.users = key, ctx, ras, lay, cands, users
        self.spacing = spacing
        self.old = lay["boxes"]
        self.N = len(self.old)
        self.intro = [p["pos"] for t in ("intro0", "intro1") for p in lay[t]]
        self.resp = [p["pos"] for p in lay["respawns"]]
        self.dcache = {}
        self.ccache = {}
        # team distances for fairness
        self.d0 = self.d1 = None
        i0 = ras.node_at(L.centre(lay["intro0"]), 3.0)
        i1 = ras.node_at(L.centre(lay["intro1"]), 3.0)
        if i0 is not None and i1 is not None:
            self.d0, self.d1 = ras.dist_from(i0), ras.dist_from(i1)
        self.floors = ctx.spec.get("floors") or []
        self.oldp = np.array([b["pos"] for b in self.old], float)
        self.cp = np.array([c.pos for c in cands], float)
        self.flagged = np.array([1.0 if set(r["flags"]) - {"OPEN"} else 0.0 for r in rows])
        self.creg = np.array([c.reg for c in cands])
        self.oreg = np.array([(int(ras.lab[ras.node_at(b["pos"], 1.5)]) if ras.node_at(b["pos"], 1.5) is not None else -1) for b in self.old])
        self.userw = np.array([1.0 if k in users else 0.0 for k in range(self.N)])
        self.cxz = np.array([(c.pos[0], c.pos[2]) for c in cands])
        self.ints = None
        try:
            self.ints = E.interiors(ctx, seed_file(key))
            self.inside = E.interior_index(self.ints)
            self.main_int = bool(self.ints and self.ints[0]["area"] >= 150)
        except Exception:
            self.main_int = False
        self.hard_ok = []
        for c in cands:
            ok = min(math.dist(c.pos, q) for q in self.intro) >= INTRO_MIN and min(math.dist(c.pos, q) for q in self.resp) >= RESP_MIN
            self.hard_ok.append(ok)
        self.inside_c = [(self.inside(c.pos) >= 0 and self.ints and self.ints[0] and self.inside(c.pos) == 0) if self.main_int else False for c in cands]

    def dist(self, node):
        if node not in self.dcache:
            self.dcache[node] = self.ras.dist_from(node)
        return self.dcache[node]

    COVER_R = 20.0
    COVER_W = 40.0

    def cover(self, ci):
        c = self.cands[ci]
        if c.node not in self.ccache:
            d = dijkstra(self.ras.graph, directed=True, indices=c.node, limit=self.COVER_R)
            self.ccache[c.node] = d <= self.COVER_R
        return self.ccache[c.node]

    def spacing_ok(self, ci, others):
        c = self.cands[ci]
        for oj in others:
            o = self.cands[oj]
            if math.dist(c.pos, o.pos) < EUC_MIN:
                return False
            d = self.dist(o.node)[c.node]
            if not np.isfinite(d) or d < self.spacing:
                return False
        return True

    def score(self, state, anchors):
        """state: list of candidate indices (slot i = old box i)"""
        cs = [self.cands[i] for i in state]
        regs = self.ras.regions
        J = 0.0
        count = {}
        for slot, c in enumerate(cs):
            J += 3.0 * c.q
            R = regs[c.reg]
            count[c.reg] = count.get(c.reg, 0) + 1
            if R["hall"]:
                J -= 1.5
            J -= 3.0 * R["traffic"]
            if self.d0 is not None:
                a, b = self.d0[c.node], self.d1[c.node]
                if np.isfinite(a) and np.isfinite(b) and a + b > 1:
                    J -= 1.5 * abs(a - b) / (a + b)
        # movement: cheapest assignment old box -> new spot (the slot identity of a set is arbitrary)
        cost = self.move_cost(state)
        r_, c_ = linear_sum_assignment(cost)
        J -= float(cost[r_, c_].sum())
        for r, k in count.items():
            R = regs[r]
            if R["hall"] or R["area"] < 15:
                continue
            J += 1.5 + 3.0 * min(1.0, R["area"] / 100.0)
            allow = 1 + int(R["area"] // 160)
            if k > allow:
                J -= 2.5 * (k - allow)
        # rooms without a box that are big (reported by the caller)
        # balance between the teams
        if self.d0 is not None:
            sd = tot = 0.0
            for c in cs:
                a, b = self.d0[c.node], self.d1[c.node]
                if np.isfinite(a) and np.isfinite(b):
                    sd += a - b
                    tot += a + b
            if tot > 0:
                J -= 4.0 * abs(sd) / tot
        for k, f in enumerate(self.floors):
            need = int(f.get("boxes", 0))
            if need:
                have = sum(1 for c in cs if L.floor_index(self.ctx.spec, c.pos) == k)
                if have < need:
                    J -= 40.0 * (need - have)
        if self.main_int and not any(self.inside_c[i] for i in state):
            J -= 4.0
        cov = np.zeros(self.ras.n, bool)
        for i in state:
            cov |= self.cover(i)
        J += self.COVER_W * float(cov.mean())
        return J

    def run(self):
        anchors = [dict(pos=b["pos"]) for b in self.old]
        xz = self.cxz
        state = []
        # 1. snap every old box to the best valid wall spot near it
        order = sorted(range(self.N), key=lambda k: -(k in self.users))
        taken = {}
        for slot in order:
            p = self.old[slot]["pos"]
            d = np.hypot(xz[:, 0] - p[0], xz[:, 1] - p[2])
            idx = np.argsort(d)
            best = None
            for rad in ((6.0 if slot in self.users else 10.0), 16.0, 28.0, 50.0, 1e9):
                bs = -1e9
                for i in idx:
                    if d[i] >= rad:
                        break
                    if not self.hard_ok[i] or abs(self.cands[i].pos[1] - p[1]) > (1.5 if rad < 1e9 else 1e9):
                        continue
                    if not self.spacing_ok(i, [v for v in taken.values() if v is not None]):
                        continue
                    s = self.cands[i].q * 3 - 0.15 * d[i]
                    if s > bs:
                        best, bs = i, s
                if best is not None:
                    break
            taken[slot] = best
        state = [taken.get(s) for s in range(self.N)]
        if any(s is None for s in state):
            return None
        # 2. swap search
        cur = self.score(state, anchors)
        if os.environ.get("BP_DEBUG"):
            print("stage1", round(cur, 2), [(round(self.cands[i].pos[0]), round(self.cands[i].pos[2])) for i in state])
        for sweep in range(12):
            improved = False
            for slot in range(self.N):
                others = [state[k] for k in range(self.N) if k != slot]
                best, bj = state[slot], cur
                ranked = range(len(self.cands))
                for i in ranked:
                    if i == state[slot] or not self.hard_ok[i]:
                        continue
                    if slot in self.users and math.dist(self.cands[i].pos, self.old[slot]["pos"]) < HOLD and False:
                        pass
                    # cheap pre-test: spacing
                    if not self.spacing_ok(i, others):
                        continue
                    st = state[:slot] + [i] + state[slot + 1:]
                    j = self.score(st, anchors)
                    if j > bj + 1e-6:
                        best, bj = i, j
                if best != state[slot]:
                    state[slot] = best
                    cur = bj
                    improved = True
            if os.environ.get("BP_DEBUG"):
                print("sweep", sweep, round(cur, 2), [(round(self.cands[i].pos[0]), round(self.cands[i].pos[2])) for i in state])
            if not improved:
                break
        return state, cur

    def move_cost(self, state):
        """(old box, new spot) cost: a few metres along a wall is nearly free, a move inside the same room is cheap, a jump to another room
        pays a fixed price (more for a hand placed box)"""
        st = np.array(state)
        D = np.linalg.norm(self.oldp[:, None, :] - self.cp[st][None, :, :], axis=2)
        same = self.oreg[:, None] == self.creg[st][None, :]
        near = 0.05 * D
        room = np.minimum(1.5, 0.15 + 0.08 * D)
        jump = np.where(self.flagged[:, None] > 0, 1.2 + np.minimum(2.0, 0.04 * D), 9.0) + 1.5 * self.userw[:, None]
        return np.where(D <= 3.0, near, np.where(same, room, jump))

    def assign(self, state):
        """old slot -> candidate index (cheapest total movement)"""
        cost = self.move_cost(state)
        r_, c_ = linear_sum_assignment(cost)
        out = [None] * self.N
        for a, b in zip(r_, c_):
            out[a] = state[b]
        return out

    def score_partial(self, st, anchors):
        saved = self.N
        # a partial state is scored with the slots it has (anchors by position in the list)
        return self.score_n(st, anchors)

    def score_n(self, st, anchors):
        old = self.N
        try:
            self.N = len(st)
            return self.score(st, anchors[:len(st)] + [None] * max(0, len(st) - len(anchors)))
        finally:
            self.N = old


# ------------------------------------------------------------------------------------------------ plan
def plan(key, quiet=False):
    lay = L.load_layout(key)
    ctx = Ctx(key, lay)
    ras = Raster(ctx)
    ras.traffic(lay)
    users = user_boxes(key, ctx)
    old_rows = analyse_old(key, ctx, ras, lay, users)
    cands, rej = make_candidates(key, ctx, ras, lay)
    if not quiet:
        print(f"{key}: raster {ras.n} nodes, {ras.nreg} regions ({sum(1 for r in ras.regions if r['hall'])} hallways), "
              f"{len(cands)} wall spots (rejected {rej})")
    res = None
    spacing = SPACING
    while res is None and spacing >= 10.0:
        ch = Chooser(key, ctx, ras, lay, cands, users, spacing, old_rows)
        res = ch.run()
        if res is None:
            spacing -= 2.0
    if res is None:
        raise SystemExit(f"{key}: no feasible box set")
    state, J = res
    state = ch.assign(state)
    new = []
    for slot, ci in enumerate(state):
        c = cands[ci]
        o = lay["boxes"][slot]
        dm = math.dist(c.pos, o["pos"])
        oreg = old_rows[slot]["region"]
        if dm < 0.35 and abs(((c.yaw - yaw_of(o["quat"]) + math.pi) % (2 * math.pi)) - math.pi) < 0.3:
            how = "kept"
        elif dm < 3.0:
            how = "aligned"
        elif c.reg == oreg:
            how = "moved"
        else:
            how = "moved to another room"
        new.append({"box": slot + 1, "pos": [round(c.pos[0], 3), round(c.pos[1], 3), round(c.pos[2], 3)], "quat": yaw_quat(c.yaw),
                    "yaw_deg": round(math.degrees(c.yaw) % 360, 1), "q": round(c.q, 2), "region": c.reg, "how": how, "moved_m": round(dm, 1),
                    "user": slot in users, "tuck": c.corner, "front": round(c.front, 1)})
    for R in ras.regions:
        R["boxes"] = sum(1 for n in new if n["region"] == R["id"])
    cov_old = coverage_nodes(ras, [ras.node_at(b["pos"], 1.5) for b in lay["boxes"]])
    cov_new = coverage_nodes(ras, [cands[ci].node for ci in state])
    oreg = {r["region"] for r in old_rows}
    big = [r for r in ras.regions if not r["hall"] and r["area"] >= 40 and r["traffic"] < 0.6]
    quiet_old = sum(1 for r in big if r["id"] in oreg)
    quiet_new = sum(1 for r in big if r["boxes"])
    lay2 = dict(lay)
    lay2["boxes"] = [{"pos": n["pos"], "quat": n["quat"]} for n in new]
    err, warn, m = L.check(key, lay2, ctx, strict=True)
    err0, warn0, m0 = L.check(key, lay, ctx, strict=True)
    mine = {"key": key, "crate": [CRATE_L, CRATE_W], "spacing": spacing, "score": round(J, 2), "old": old_rows, "new": new,
            "rooms": ras.regions, "rejected": rej,
            "coverage": {"radius_m": Chooser.COVER_R, "old": round(cov_old, 3), "new": round(cov_new, 3)},
            "quiet_rooms": {"count": len(big), "with_box_old": quiet_old, "with_box_new": quiet_new}, "check_errors": err, "check_warnings": warn, "check_errors_before": err0}
    return mine, ctx, ras, lay, lay2


def coverage_nodes(ras, nodes):
    cov = np.zeros(ras.n, bool)
    for nd in nodes:
        if nd is not None:
            cov |= dijkstra(ras.graph, directed=True, indices=nd, limit=Chooser.COVER_R) <= Chooser.COVER_R
    return float(cov.mean())


def summarize(mine):
    mv = {}
    for n in mine["new"]:
        mv[n["how"]] = mv.get(n["how"], 0) + 1
    q = mine["quiet_rooms"]
    return mv, q["count"], q["with_box_old"], q["with_box_new"]


# ------------------------------------------------------------------------------------------------ pictures
def draw(key, mine, ctx, ras, lay, lay2, rooms_png=False):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.collections import PolyCollection, LineCollection
    nav = ctx.nav
    fig, ax = plt.subplots(figsize=(12, 12), dpi=90)
    play = [[(v[0], v[2]) for v in nav.polys[i]] for i in ras.ok]
    if rooms_png:
        cmap = plt.get_cmap("YlOrRd")
        # tint every raster cell by its region's traffic
        cs = ctx.grid.CELL
        for R in ras.regions:
            m = ras.lab == R["id"]
            col = "#bdbdbd" if R["hall"] and False else cmap(0.1 + 0.8 * R["traffic"])
            ax.scatter(ras.X[m], ras.Z[m], s=3.5, marker="s", color=col, linewidths=0, alpha=0.9)
        for R in ras.regions:
            lbl = f"{R['id']}{'h' if R['hall'] else ''}\n{R['area']:.0f}m2 t{R['traffic']:.2f}\nB{R['boxes']}"
            if R["area"] >= 12:
                ax.text(R["cx"], R["cz"], lbl, fontsize=5.5, ha="center", va="center", color="k")
    else:
        ax.add_collection(PolyCollection(play, facecolor="#e4e8ea", edgecolor="#b0bec5", linewidth=0.1))
    walls = [[(a[0], a[2]), (b[0], b[2])] for _, a, b in wall_edges(ctx, ras.ok)]
    ax.add_collection(LineCollection(walls, colors="#616161", linewidths=0.7, zorder=3))
    for pr in ctx.spec.get("props", []):
        ax.plot(pr["pos"][0], pr["pos"][2], ".", color="#9e9e9e", ms=2, zorder=3)

    def crate(pos, yaw, fc, ec, z=6):
        hl, hw = CRATE_L / 2, CRATE_W / 2
        tx, tz = math.cos(yaw), -math.sin(yaw)        # local X in world (yaw about +Y, forward = (sin, cos))
        nx, nz = math.sin(yaw), math.cos(yaw)
        pts = [(pos[0] + tx * u + nx * v, pos[2] + tz * u + nz * v) for u, v in ((-hl, -hw), (hl, -hw), (hl, hw), (-hl, hw))]
        ax.add_patch(plt.Polygon(pts, closed=True, fc=fc, ec=ec, lw=0.6, zorder=z, alpha=0.9))
        ax.plot([pos[0], pos[0] + nx * 1.1], [pos[2], pos[2] + nz * 1.1], color=ec, lw=0.8, zorder=z)
    for p in lay["intro0"] + lay["intro1"]:
        ax.plot(p["pos"][0], p["pos"][2], "o", color="#1565c0", ms=5, zorder=5)
    for p in lay["respawns"]:
        ax.plot(p["pos"][0], p["pos"][2], "o", color="#64b5f6", ms=3.2, zorder=5)
    for k, (o, n) in enumerate(zip(lay["boxes"], mine["new"])):
        ax.plot([o["pos"][0], n["pos"][0]], [o["pos"][2], n["pos"][2]], color="#8e24aa", lw=0.6, ls=":", zorder=4)
        crate(o["pos"], yaw_of(o["quat"]), "#ef9a9a", "#c62828", 6)
        ax.text(o["pos"][0], o["pos"][2], f"{k + 1}", fontsize=6, color="#b71c1c", zorder=8, ha="center", va="center")
    for k, n in enumerate(mine["new"]):
        crate(n["pos"], math.radians(n["yaw_deg"]), "#a5d6a7", "#1b5e20", 7)
        ax.text(n["pos"][0] + 0.9, n["pos"][2] + 0.9, f"{n['box']}", fontsize=7, color="#1b5e20", zorder=8, weight="bold")
    pts = [p["pos"] for t in ("intro0", "intro1", "respawns", "boxes") for p in lay[t]] + [n["pos"] for n in mine["new"]]
    ax.set_xlim(min(p[0] for p in pts) - 15, max(p[0] for p in pts) + 15)
    ax.set_ylim(min(p[2] for p in pts) - 15, max(p[2] for p in pts) + 15)
    ax.set_aspect("equal")
    mv, nr, e0, e1 = summarize(mine)
    ax.set_title(f"{key}  boxes: old red / new green (crate {CRATE_L}x{CRATE_W}, front line = opening side)  "
                 f"intro blue, respawn light blue  | {mv}  quiet rooms {nr}: with box {e0} -> {e1}, coverage {mine['coverage']['old']:.2f} -> {mine['coverage']['new']:.2f}", fontsize=8)
    os.makedirs(OUT, exist_ok=True)
    fn = os.path.join(OUT, f"{key}-rooms.png" if rooms_png else f"{key}.png")
    fig.savefig(fn, bbox_inches="tight")
    plt.close(fig)
    return fn


def write_plan(key):
    mine, ctx, ras, lay, lay2 = plan(key)
    os.makedirs(OUT, exist_ok=True)
    json.dump(mine, open(os.path.join(OUT, f"{key}.json"), "w", newline="\n"), indent=1)
    f1 = draw(key, mine, ctx, ras, lay, lay2, False)
    f2 = draw(key, mine, ctx, ras, lay, lay2, True)
    mv, nr, e0, e1 = summarize(mine)
    print(f"{key}: {mv}; quiet rooms (>=40 m2, traffic<0.6) {nr}: with a box {e0} -> {e1}; coverage {mine['coverage']['old']} -> {mine['coverage']['new']}; spacing {mine['spacing']:.0f} m; "
          f"check errors {len(mine['check_errors'])} (before {len(mine['check_errors_before'])}) -> {f1}")
    for o, n in zip(mine["old"], mine["new"]):
        print(f"  B{n['box']}: {','.join(o['flags']) or 'ok':16s} {'USER ' if o['user'] else '     '}{n['how']:22s} moved {n['moved_m']:5.1f} m "
              f"-> {n['pos'][0]:.1f},{n['pos'][2]:.1f} yaw {n['yaw_deg']:5.1f} q {n['q']}")
    for e in mine["check_errors"]:
        print("  ERROR", e)
    return mine


# ------------------------------------------------------------------------------------------------ apply
def _eol(path):
    return "\r\n" if b"\r\n" in open(path, "rb").read() else "\n"


def patch_pak(key, new_boxes, old_boxes):
    """move the pak's supply boxes (and their item positions) in place, like tools/spawns/levels.py apply"""
    sys.path.insert(0, os.path.join(L.TOOLS, "spawns"))
    import levels as lv
    m = L.spec_of(key)
    pak = os.path.join(L.TOOLS, "features", "levels", m["pak"] + "-ingame.pak")
    out = os.path.join(OUT, f"{key}-pakdump.json")
    os.makedirs(OUT, exist_ok=True)
    subprocess.run(["pwsh", "-NoProfile", "-File", os.path.join(L.TOOLS, "spawns", "dump_json.ps1"), "-Pak", os.path.abspath(pak),
                    "-Out", os.path.abspath(out)], check=True, stdout=subprocess.DEVNULL)
    sp = json.load(open(out, encoding="utf-8-sig"))
    by = {s["name"]: s for s in sp}
    b = bytearray(open(pak, "rb").read())
    offs = lv.find_offsets(b, sp)
    moves = []
    for i, nb in enumerate(new_boxes, 1):
        box = by[f"to1-supplybox-{i}"]
        dq = lv.qmul(tuple(nb["quat"]), lv.qconj(tuple(box["quat"])))
        moves.append((box["name"], tuple(nb["pos"]), tuple(nb["quat"])))
        for s in sp:
            if s["name"].startswith(f"to1-supplybox-{i}-itempos-"):
                rel = [s["pos"][j] - box["pos"][j] for j in range(3)]
                r = lv.qrot(dq, rel)
                moves.append((s["name"], tuple(nb["pos"][j] + r[j] for j in range(3)), lv.qmul(dq, tuple(s["quat"]))))
    import struct
    for name, pos, quat in moves:
        o = offs[name]
        struct.pack_into("<3f", b, o, *pos)
        struct.pack_into("<4f", b, o + 16, *quat)
    open(pak, "wb").write(b)
    os.remove(out)
    return len(moves)


def patch_fixed_boxes(key, new_boxes, old_boxes, how):
    """sp_maps.json fixed_boxes of the map: entries that sat on an old box follow it to the new place (text edit: the file is not a
    lossless json round trip)"""
    path = L.SPEC
    raw = open(path, "rb").read().decode("utf-8")
    eol = "\r\n" if "\r\n" in raw else "\n"
    txt = raw.replace("\r\n", "\n")
    m = re.search(r'\n   "key": "%s",' % re.escape(key), txt)
    if not m:
        return 0
    start = m.start()
    nxt = txt.find('\n  {', start + 10)
    nxt = len(txt) if nxt < 0 else nxt
    seg = txt[start:nxt]
    fm = re.search(r'\n   "fixed_boxes": \[', seg)
    if not fm:
        return 0
    i0 = fm.end() - 1
    depth, j = 0, i0
    while True:
        ch = seg[j]
        depth += ch == "["
        depth -= ch == "]"
        if depth == 0:
            break
        j += 1
    block = json.loads(seg[i0:j + 1])
    changed = 0
    for fb in block:
        for k, ob in enumerate(old_boxes):
            if abs(fb["pos"][0] - ob["pos"][0]) < 0.05 and abs(fb["pos"][2] - ob["pos"][2]) < 0.05:
                nb = new_boxes[k]
                if how[k] == "kept":
                    break
                fb["pos"], fb["quat"] = list(nb["pos"]), list(nb["quat"])
                was = fb.get("note", "")
                fb["note"] = f"box_place 11-02 ({how[k]}; against the wall, yaw from the wall normal); was: {was}"
                changed += 1
                break
    text = json.dumps(block, indent=1).replace("\n", "\n   ")
    seg2 = seg[:i0] + text + seg[j + 1:]
    txt2 = txt[:start] + seg2 + txt[nxt:]
    open(path, "wb").write(txt2.replace("\n", eol).encode("utf-8"))
    return changed


def apply(key):
    sys.path.insert(0, HERE)
    mine, ctx, ras, lay, lay2 = plan(key, quiet=True)
    new = [{"pos": n["pos"], "quat": n["quat"]} for n in mine["new"]]
    how = [n["how"] for n in mine["new"]]
    # data file (original newlines)
    dp = os.path.join(L.DATA, f"{key}-spawns.json")
    eol = _eol(dp)
    raw = json.load(open(dp))
    raw["boxes"] = new
    note = raw.get("_note", "")
    if "box_place" not in note:
        raw["_note"] = note + " | supply boxes re-placed 11-02 by tools/maps/box_place.py (against walls, spread over rooms, 20 m apart)"
    open(dp, "wb").write(json.dumps(raw, indent=1).replace("\n", eol).encode("utf-8"))
    n = patch_pak(key, new, lay["boxes"])
    fx = patch_fixed_boxes(key, new, lay["boxes"], how)
    # snapshot (layout.py), same newline style as the committed file
    import layout
    sp = layout.snapshot_path(key)
    eol2 = _eol(sp) if os.path.exists(sp) else "\r\n"
    lay3 = L.load_layout(key)
    layout.snapshot(key, lay3)
    t = open(sp, "rb").read().decode("utf-8").replace("\r\n", "\n")
    open(sp, "wb").write(t.replace("\n", eol2).encode("utf-8"))
    print(f"{key}: data + pak ({n} transforms) + snapshot written, {fx} fixed_boxes updated")
    return mine


def navs():
    sys.path.insert(0, os.path.dirname(HERE))
    import sp_bounds
    import sp_maps
    import sp_levels
    for key in LB_MAPS:
        if os.path.exists(L.nav_file(key)):
            continue
        m = sp_maps.spec(key)
        geo = [lv for lv in m["levels"] if lv != m["pak"] and sp_levels.tag(lv) == "GEO"]
        r = sp_bounds.nav_json(key, key, geo)
        print(key, sum(len(v) for v in r.values()), "polys")


def satchels(key, want=3):
    """fixed supply satchel spots (tools/maps/satchels.py): flush against a wall / cover on the navmesh floor, in rooms that see traffic but
    are not hallways, >= SAT_BOX_MIN path from every supply box, >= SAT_SPREAD from each other, >= SAT_INTRO from the intro spawns.
    -> [{"pos", "quat", "yaw_deg", "region", "traffic", "q"}]"""
    global CRATE_L, CRATE_W, FRONT_MIN, BACK_GAP
    lay = L.load_layout(key)
    ctx = Ctx(key, lay)
    ras = Raster(ctx)
    ras.traffic(lay)
    saved = (CRATE_L, CRATE_W, FRONT_MIN)
    CRATE_L, CRATE_W, FRONT_MIN = SAT_L, SAT_W, SAT_FRONT
    try:
        cands, rej = make_candidates(key, ctx, ras, lay)
    finally:
        CRATE_L, CRATE_W, FRONT_MIN = saved
    intro = [p["pos"] for t in ("intro0", "intro1") for p in lay[t]]
    boxn = [ras.node_at(b["pos"], 1.5) for b in lay["boxes"]]
    bd = [ras.dist_from(n) for n in boxn if n is not None]
    ok = []
    for c in cands:
        R = ras.regions[c.reg]
        if R["hall"] or R["area"] < 12 or min(math.dist(c.pos, q) for q in intro) < SAT_INTRO:
            continue
        if any(d[c.node] < SAT_BOX_MIN for d in bd) or any(math.dist(c.pos, b["pos"]) < SAT_BOX_MIN * 0.7 for b in lay["boxes"]):
            continue
        # traffic: some, not the main road (peak 0.35)
        c.note = R["traffic"]
        c.q = c.q + 0.5 - 1.2 * abs(R["traffic"] - 0.35) + (0.1 if R["area"] >= 30 else 0.0)
        ok.append(c)
    out = []
    dcache = {}
    while len(out) < want and ok:
        best = None
        for c in ok:
            if any(math.dist(c.pos, o.pos) < 12 for o in out):
                continue
            far = True
            for o in out:
                if o.node not in dcache:
                    dcache[o.node] = ras.dist_from(o.node)
                if dcache[o.node][c.node] < SAT_SPREAD:
                    far = False
                    break
            if not far:
                continue
            # prefer another room than the ones taken, and spread (distance to the nearest taken spot)
            sc = c.q + (0.6 if all(o.reg != c.reg for o in out) else -0.5) + 0.01 * min([math.dist(c.pos, o.pos) for o in out] + [40.0])
            if best is None or sc > best[0]:
                best = (sc, c)
        if best is None:
            break
        out.append(best[1])
        ok.remove(best[1])
    res = []
    for c in out:
        y = E.foot(ctx.grid, c.pos[0], c.pos[1] + 0.05, c.pos[2], 0.3)[0] + 0.02
        res.append({"pos": [round(c.pos[0], 3), round(y, 3), round(c.pos[2], 3)], "quat": yaw_quat(c.yaw), "yaw_deg": round(math.degrees(c.yaw) % 360, 1),
                    "region": c.reg, "traffic": round(ras.regions[c.reg]["traffic"], 2), "q": round(c.q, 2)})
    return res, ctx, ras, lay


def draw_satchels(key, sats, ctx, ras, lay):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.collections import PolyCollection, LineCollection
    fig, ax = plt.subplots(figsize=(12, 12), dpi=90)
    ax.add_collection(PolyCollection([[(v[0], v[2]) for v in ctx.nav.polys[i]] for i in ras.ok], facecolor="#e4e8ea", edgecolor="#b0bec5", linewidth=0.1))
    ax.add_collection(LineCollection([[(a[0], a[2]), (b[0], b[2])] for _, a, b in wall_edges(ctx, ras.ok)], colors="#616161", linewidths=0.7, zorder=3))
    for p in lay["intro0"] + lay["intro1"]:
        ax.plot(p["pos"][0], p["pos"][2], "o", color="#1565c0", ms=5, zorder=5)
    for p in lay["respawns"]:
        ax.plot(p["pos"][0], p["pos"][2], "o", color="#64b5f6", ms=3, zorder=5)
    for b in lay["boxes"]:
        ax.plot(b["pos"][0], b["pos"][2], "s", color="#2e7d32", ms=5, zorder=6)
    for k, s in enumerate(sats):
        yaw = math.radians(s["yaw_deg"])
        ax.plot(s["pos"][0], s["pos"][2], "D", color="#ff6f00", ms=8, zorder=8)
        ax.plot([s["pos"][0], s["pos"][0] + math.sin(yaw) * 1.5], [s["pos"][2], s["pos"][2] + math.cos(yaw) * 1.5], color="#e65100", lw=1.2, zorder=8)
        ax.add_patch(plt.Circle((s["pos"][0], s["pos"][2]), SAT_BOX_MIN, fill=False, ec="#2e7d32", lw=0.4, ls=":", zorder=4))
        ax.text(s["pos"][0] + 1, s["pos"][2] + 1, f"S{k + 1}", color="#e65100", weight="bold", fontsize=9, zorder=9)
    pts = [p["pos"] for t in ("intro0", "intro1", "respawns", "boxes") for p in lay[t]]
    ax.set_xlim(min(p[0] for p in pts) - 15, max(p[0] for p in pts) + 15)
    ax.set_ylim(min(p[2] for p in pts) - 15, max(p[2] for p in pts) + 15)
    ax.set_aspect("equal")
    ax.set_title(f"{key}: satchel spots orange (line = facing out of the wall), supply boxes green squares (14 m ring), intro dark blue, respawn light blue", fontsize=8)
    os.makedirs(OUT, exist_ok=True)
    fn = os.path.join(OUT, f"{key}-satchels.png")
    fig.savefig(fn, bbox_inches="tight")
    plt.close(fig)
    return fn


# ------------------------------------------------------------------------------------------------ Interrogation lockboxes
LB_MAX = 3                  # candidates per team (tools/interrogation_lockboxes.py; the daemon picks one per match)
LB_MIN_INTRO = 10.0         # straight m from every intro spawn (not on the match-start pile)
LB_MIN_RESP = 7.0           # from respawns: a lockbox in the respawn ring would be camped by the respawning team
LB_MIN_BOX = 8.0            # from supply boxes and satchels (hold E at a lockbox must never also open a crate)
LB_MIN_OWN_PATH = 14.0      # path m from the own start
LB_OWN_HALF = 0.75          # own path < 0.75 * enemy path = the team's half
LB_SPREAD = 12.0            # candidates of one team: path m apart


def lockboxes(key):
    """Interrogation lockbox spots, 2013 style: the crate stands flush against a wall (corner tucks preferred) in a ROOM (not a hallway) of
    the team's own half, off the main road (traffic), away from the intro spawns, respawns, supply boxes and satchels.
    -> ([team 0 spots, team 1 spots], ctx, ras, lay): spot = {"pos", "yaw_deg", "region", "traffic", "own", "enemy", "q"}"""
    lay = L.load_layout(key)
    ctx = Ctx(key, lay)
    ras = Raster(ctx)
    ras.traffic(lay)
    cands, rej = make_candidates(key, ctx, ras, lay)
    intro = [[p["pos"] for p in lay[t]] for t in ("intro0", "intro1")]
    start = [ras.node_at(L.centre(lay[t]), 4.0) for t in ("intro0", "intro1")]
    if None in start:
        start = [ras.node_at(i[0], 4.0) for i in intro]
    dist = [ras.dist_from(n) for n in start]
    others = [b["pos"] for b in lay["boxes"]]
    sp = os.path.join(L.DATA, f"{key}-satchels.json")
    if os.path.exists(sp):
        sd = json.load(open(sp))
        others += [s["pos"] for s in sd.get("spots", [])]
    resp = [r["pos"] for r in lay["respawns"]]
    out = []
    for t in (0, 1):
        own, foe = dist[t], dist[1 - t]
        best = []
        for slack in (0, 1, 2, 3):                      # relax: hallways/traffic, then distances, then the half
            lo_intro, lo_box, lo_resp = LB_MIN_INTRO - 2 * slack, LB_MIN_BOX - 2 * slack, LB_MIN_RESP - slack
            half = LB_OWN_HALF + 0.07 * slack
            ok = []
            for c in cands:
                R = ras.regions[c.reg]
                if not np.isfinite(own[c.node]) or not np.isfinite(foe[c.node]):
                    continue
                if R["area"] < 10 or (R["hall"] and slack < 2) or (R["traffic"] > 0.45 + 0.2 * slack):
                    continue
                if own[c.node] >= half * foe[c.node] or own[c.node] < LB_MIN_OWN_PATH - 3 * slack:
                    continue
                if min(math.dist(c.pos, q) for q in intro[0] + intro[1]) < lo_intro:
                    continue
                if resp and min(math.dist(c.pos, q) for q in resp) < lo_resp:
                    continue
                if others and min(math.dist(c.pos, q) for q in others) < lo_box:
                    continue
                # defensible: tucked into a corner, a calm room, a back area of the own half (farther from the enemy = safer)
                sc = (c.q + 0.35 * min(c.corner, 2) - 1.2 * R["traffic"] + (0.2 if R["area"] >= 25 else 0.0)
                      + 0.015 * min(foe[c.node] - own[c.node], 40.0)
                      - 0.025 * max(0.0, own[c.node] - 50.0))      # not deep in a far corner of a long map (the team must defend it)
                ok.append((sc, c))
            if ok:
                best = sorted(ok, key=lambda a: -a[0])
                break
        picked = []
        dc = {}
        for sc, c in best:
            if len(picked) >= LB_MAX:
                break
            far = True
            for o in picked:
                if o[1].node not in dc:
                    dc[o[1].node] = ras.dist_from(o[1].node)
                if math.dist(c.pos, o[1].pos) < LB_SPREAD or dc[o[1].node][c.node] < LB_SPREAD:
                    far = False
                    break
            if far:
                picked.append((sc, c))
        spots = []
        for sc, c in picked:
            y = E.foot(ctx.grid, c.pos[0], c.pos[1] + 0.05, c.pos[2], 0.3)[0] + 0.02
            spots.append({"pos": [round(c.pos[0], 3), round(y, 3), round(c.pos[2], 3)], "yaw_deg": round(math.degrees(c.yaw) % 360, 1),
                          "region": c.reg, "traffic": round(ras.regions[c.reg]["traffic"], 2), "own": round(float(own[c.node]), 1),
                          "enemy": round(float(foe[c.node]), 1), "q": round(sc, 2)})
        out.append(spots)
    return out, ctx, ras, lay


def draw_lockboxes(key, spots, ctx, ras, lay):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.collections import PolyCollection, LineCollection
    fig, ax = plt.subplots(figsize=(12, 12), dpi=90)
    ax.add_collection(PolyCollection([[(v[0], v[2]) for v in ctx.nav.polys[i]] for i in ras.ok], facecolor="#e4e8ea", edgecolor="#b0bec5", linewidth=0.1))
    ax.add_collection(LineCollection([[(a[0], a[2]), (b[0], b[2])] for _, a, b in wall_edges(ctx, ras.ok)], colors="#616161", linewidths=0.7, zorder=3))
    for t, col in ((0, "#1565c0"), (1, "#c62828")):
        for p in lay["intro%d" % t]:
            ax.plot(p["pos"][0], p["pos"][2], "o", color=col, ms=5, zorder=5)
        for k, s in enumerate(spots[t]):
            yaw = math.radians(s["yaw_deg"])
            ax.plot(s["pos"][0], s["pos"][2], "*", color=col, ms=14, zorder=8)
            ax.plot([s["pos"][0], s["pos"][0] + math.sin(yaw) * 1.5], [s["pos"][2], s["pos"][2] + math.cos(yaw) * 1.5], color=col, lw=1.2, zorder=8)
            ax.text(s["pos"][0] + 1, s["pos"][2] + 1, f"L{t}.{k}", color=col, weight="bold", fontsize=9, zorder=9)
    for b in lay["boxes"]:
        ax.plot(b["pos"][0], b["pos"][2], "s", color="#2e7d32", ms=5, zorder=6)
    pts = [p["pos"] for t in ("intro0", "intro1", "respawns", "boxes") for p in lay[t]]
    ax.set_xlim(min(p[0] for p in pts) - 15, max(p[0] for p in pts) + 15)
    ax.set_ylim(min(p[2] for p in pts) - 15, max(p[2] for p in pts) + 15)
    ax.set_aspect("equal")
    ax.set_title(f"{key}: Interrogation lockbox candidates (stars, team 0 blue / team 1 red, line = lid side), supply boxes green", fontsize=8)
    os.makedirs(OUT, exist_ok=True)
    fn = os.path.join(OUT, f"{key}-lockboxes.png")
    fig.savefig(fn, bbox_inches="tight")
    plt.close(fig)
    return fn


if __name__ == "__main__":
    a = sys.argv[1:]
    if not a or a[0] not in ("plan", "apply", "navs", "satchels", "lockboxes"):
        print(__doc__)
        sys.exit(1)
    if a[0] == "navs":
        navs()
        sys.exit(0)
    if a[0] == "lockboxes":
        for k in (LB_MAPS if a[1:] == ["all"] else a[1:]):
            s, c_, r_, l_ = lockboxes(k)
            print(k, draw_lockboxes(k, s, c_, r_, l_), [[(x["pos"], x["own"], x["enemy"], x["traffic"]) for x in t] for t in s])
        sys.exit(0)
    if a[0] == "satchels":
        for k in (SAT_MAPS if a[1:] == ["all"] else a[1:]):
            s, c_, r_, l_ = satchels(k)
            print(k, draw_satchels(k, s, c_, r_, l_), [(x["pos"][0], x["pos"][2], x["traffic"]) for x in s])
        sys.exit(0)
    keys = MAPS if a[1:] == ["all"] else a[1:]
    for k in keys:
        write_plan(k) if a[0] == "plan" else apply(k)
