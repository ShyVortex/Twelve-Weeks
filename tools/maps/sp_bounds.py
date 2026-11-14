"""Boundary openings of an SP-section map from the levels' navmeshes, and blocker props for them.

A play space cut out of a single-player area has openings where the walkable ground of a LOADED level
continues into a level we do NOT load (no collision there: players fall into the void). The navmeshes
show both: every boundary edge of the loaded navmesh that touches a neighbour level's navmesh is a gap.

  python sp_bounds.py <key> [--write] [--invisible]
                                         # report openings (coordinates, width, prop count); --write puts the
                                         # blocker props into sp_maps.json (props with "auto": true, replaced
                                         # on every run; hand-placed props are kept). --invisible: close the
                                         # openings with invisible collision walls (invisible-block-050x300x200,
                                         # collision_walls.py) instead of dumpsters

Needs the levels' *-ingame paks (navmeshes live there): extracted read-only from the game psarcs into
re/maps/paks/<key>/ (loaded levels, sp_maps.py extract) and re/maps/paks/<key>-nb/ (neighbours: every level
of the spec's "nav_family" prefixes that is not loaded). Navmesh dump: dump_nav.ps1 (SceneEditor reader).
"""
import json
import math
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.dirname(HERE)
ROOT = os.path.dirname(TOOLS)
sys.path.insert(0, HERE)
sys.path.insert(0, TOOLS)
import sp_levels  # noqa: E402
import sp_maps  # noqa: E402

BLOCKER = "drag-dumpster-noclimb"   # NoR arena blocker that can't be climbed (world-rogue actor97)
STEP = 2.1                            # metres between blockers: the dumpster is 2.2 m long on its local X (prop_bounds.py), laid along the edge
INSET = 0.7                          # blockers stand this far inside the loaded side of the opening
INVISIBLE = "--invisible" in sys.argv  # invisible walls (collision_walls.piece) instead of dumpsters
if INVISIBLE:
    STEP, INSET = 2.0, 0.3            # the block is 2 m long: pieces end to end; a thin wall can stand closer to the edge
MIN_GAP = 1.0                        # openings narrower than this are ignored (a player capsule is ~0.6 m)


def nav_json(key, sub, levels):
    """{level: [polys]} for the -ingame paks of `levels` (extracting the missing ones read-only)."""
    d = os.path.join(ROOT, "re", "maps", "paks", sub)
    want = [lv for lv in levels if not os.path.exists(os.path.join(d, lv + "-ingame.pak"))]
    if want:
        sp_maps.extract(sub, [], want)
    out = os.path.join(ROOT, "re", "maps", "seeds", f"{sub}-nav.json")
    paks = [os.path.join(d, lv + "-ingame.pak") for lv in levels if os.path.exists(os.path.join(d, lv + "-ingame.pak"))]
    os.makedirs(os.path.dirname(out), exist_ok=True)
    subprocess.run(["pwsh", "-NoProfile", "-File", os.path.join(HERE, "dump_nav.ps1"), "-Paks", ";".join(paks), "-Out", out],
                   check=True, stdout=subprocess.DEVNULL)
    return {k.replace("-ingame", ""): v for k, v in json.load(open(out, encoding="utf-8-sig")).items()}


def neighbours(m):
    fam = m.get("nav_family") or []
    have = set(m["levels"])
    names = set()
    for line in open(sp_levels.FILES_TSV, encoding="utf-8", errors="replace"):
        p = line.rstrip("\n").split("\t")
        if len(p) < 3 or not p[1].startswith("pak68/") or not p[1].endswith("-ingame.pak"):
            continue
        lv = p[1][6:-len("-ingame.pak")]
        if lv not in have and any(lv.startswith(f) for f in fam) and sp_levels.tag(lv) in ("GEO", "FX"):
            names.add(lv)
    # spec "nb_extra": SCRIPT-tagged levels that carry navmesh of the next area (wat-explore-checkpoint = the way to the TV station)
    names.update(lv for lv in m.get("nb_extra", []) if lv not in have)
    return sorted(names)


class Grid:
    """xz hash of polygon edges for 'is this point on / near a polygon' queries"""

    def __init__(self, polys, cell=4.0):
        self.cell, self.g, self.polys = cell, {}, polys
        for i, p in enumerate(polys):
            xs, zs = [v[0] for v in p], [v[2] for v in p]
            for cx in range(int(min(xs) // cell), int(max(xs) // cell) + 1):
                for cz in range(int(min(zs) // cell), int(max(zs) // cell) + 1):
                    self.g.setdefault((cx, cz), []).append(i)

    def near(self, x, y, z, r=0.8, dy=1.6):
        c = self.cell
        for i in self.g.get((int(x // c), int(z // c)), ()):
            p = self.polys[i]
            if min(abs(v[1] - y) for v in p) > dy:
                continue
            if _inside(p, x, z) or _dist_poly(p, x, z) <= r:
                return i
        return None


def _inside(p, x, z):
    n, ins = len(p), False
    for i in range(n):
        x1, z1, x2, z2 = p[i][0], p[i][2], p[(i + 1) % n][0], p[(i + 1) % n][2]
        if (z1 > z) != (z2 > z) and x < (x2 - x1) * (z - z1) / (z2 - z1 + 1e-12) + x1:
            ins = not ins
    return ins


def _seg_d(px, pz, x1, z1, x2, z2):
    dx, dz = x2 - x1, z2 - z1
    t = max(0.0, min(1.0, ((px - x1) * dx + (pz - z1) * dz) / (dx * dx + dz * dz + 1e-12)))
    return math.hypot(px - (x1 + t * dx), pz - (z1 + t * dz))


def _dist_poly(p, x, z):
    return min(_seg_d(x, z, p[i][0], p[i][2], p[(i + 1) % len(p)][0], p[(i + 1) % len(p)][2]) for i in range(len(p)))


def boundary_edges(polys):
    """edges of the loaded navmesh that no other loaded polygon covers on the outside"""
    grid = Grid(polys, 4.0)
    out = []
    for i, p in enumerate(polys):
        cx, cz = sum(v[0] for v in p) / len(p), sum(v[2] for v in p) / len(p)
        for k in range(len(p)):
            a, b = p[k], p[(k + 1) % len(p)]
            ln = math.hypot(b[0] - a[0], b[2] - a[2])
            if ln < 0.05:
                continue
            mx, my, mz = (a[0] + b[0]) / 2, (a[1] + b[1]) / 2, (a[2] + b[2]) / 2
            # outward normal (away from this polygon's centre)
            nx, nz = (b[2] - a[2]) / ln, -(b[0] - a[0]) / ln
            if nx * (mx - cx) + nz * (mz - cz) < 0:
                nx, nz = -nx, -nz
            ox, oz = mx + nx * 0.35, mz + nz * 0.35       # just outside the edge
            hit = grid.near(ox, my, oz, r=0.05)
            if hit is not None and hit != i:
                continue                                  # another loaded polygon continues there
            out.append({"a": a, "b": b, "m": (mx, my, mz), "n": (nx, nz), "len": ln})
    return out


def overlap_variants(loaded, nb):
    """neighbour levels that cover the SAME ground as the loaded ones (alternate versions: basement on / off,
    the t2r copy of an SP level, ...) - not continuations, so they are left out of the opening test"""
    lg = Grid([p for v in loaded.values() for p in v], 4.0)
    out = set()
    for lv, polys in nb.items():
        sample = polys[:: max(1, len(polys) // 200)]
        inside = sum(1 for p in sample if lg.near(sum(v[0] for v in p) / len(p), sum(v[1] for v in p) / len(p),
                                                  sum(v[2] for v in p) / len(p), r=0.3) is not None)
        if sample and inside / len(sample) > 0.3:
            out.add(lv)
    return out


def openings(loaded, nb):
    """boundary edges of the loaded navmesh whose outside touches a neighbour's navmesh, clustered"""
    lp = [p for v in loaded.values() for p in v]
    skip = overlap_variants(loaded, nb)
    if skip:
        print("  overlapping neighbour versions ignored:", ", ".join(sorted(skip)))
    lg = Grid(lp, 4.0)
    # neighbour ground that the loaded navmesh does not already cover (an overlapping SP version of the same
    # street - e.g. san-infected-wilds-beach over the outpost suburbs - is not a way out)
    npolys = [p for lv, v in nb.items() if lv not in skip for p in v
              if lg.near(sum(q[0] for q in p) / len(p), sum(q[1] for q in p) / len(p), sum(q[2] for q in p) / len(p),
                         r=0.5) is None]
    ng = Grid(npolys, 4.0)
    gaps = []
    for e in boundary_edges(lp):
        mx, my, mz = e["m"]
        ox, oz = mx + e["n"][0] * 0.8, mz + e["n"][1] * 0.8
        if ng.near(ox, my, oz, r=0.6) is not None or ng.near(mx, my, mz, r=0.4) is not None:
            gaps.append(e)
    # cluster: edges sharing (nearly) an endpoint
    cl = []
    for e in gaps:
        pts = [(e["a"][0], e["a"][2]), (e["b"][0], e["b"][2])]
        home = [c for c in cl if any(math.dist(p, q) < 1.0 for p in pts for q in c["pts"])]
        if home:
            c = home[0]
            for o in home[1:]:
                c["edges"] += o["edges"]
                c["pts"] += o["pts"]
                cl.remove(o)
            c["edges"].append(e)
            c["pts"] += pts
        else:
            cl.append({"edges": [e], "pts": pts})
    out = []
    for c in cl:
        width = sum(e["len"] for e in c["edges"])
        if width < MIN_GAP:
            continue
        ys = [e["m"][1] for e in c["edges"]]
        cx = sum(e["m"][0] * e["len"] for e in c["edges"]) / width
        cz = sum(e["m"][2] * e["len"] for e in c["edges"]) / width
        out.append({"centre": [round(cx, 2), round(sum(ys) / len(ys), 2), round(cz, 2)], "width": round(width, 1),
                    "edges": c["edges"]})
    return sorted(out, key=lambda o: -o["width"])


# ---- blocker art per world (design-rules.md section 12): rows of props laid along a closure line. A row = (offset m
# toward the play space from the line, [(art, along-axis, gap m)] pattern repeated along the line). along-axis = which local
# axis of the actor runs along the line ("x" or "z"); footprints come from data/prop_bounds.json (visual bounds).
STYLES = {
    # Seattle (WLF / FEDRA-era roadblocks): chain-link fence panels behind, jersey barriers and wrecks (station wagon) in front
    "seattle-wlf": [(1.1, [("res-fence-chainlink-6m-a", "x", 0.05)]),
                    (0.0, [("station-wagon-a", "z", 0.25), ("jersey-barrier-concrete-b", "x", 0.05), ("jersey-barrier-concrete-b", "x", 0.05)])],
    # Jackson (snow, wood): plank barricade panels behind, stacked crates and a snowed-in car in front
    "jackson-wood": [(1.0, [("blocker-wood-planks-a", "x", 0.05)]),
                     (0.0, [("san-wood-crate-1x1-blocker-stacked-a", "x", 0.1), ("san-wood-crate-1x1-blocker-stacked-a", "x", 0.1),
                            ("station-wagon-a", "z", 0.25)])],
    # Santa Barbara (Rattler / slaver barricades): chain-link behind, stacked crates + plank panels + a car in front
    "sb-rattler": [(1.1, [("fob-fence-chainlink-5m-a", "x", 0.05)]),
                   (0.0, [("san-wood-crate-1x1-blocker-stacked-a", "x", 0.1), ("blocker-wood-planks-a", "x", 0.1),
                          ("san-wood-crate-1x1-blocker-stacked-a", "x", 0.1), ("station-wagon-a", "z", 0.25)])],
}


def _bounds_db():
    import prop_bounds
    return prop_bounds.load()


def lay_chain(segs, style, db, ygrid=None):
    """segs = [((a, b), (nx, nz))...] one chain (a, b = (x, y, z)); n = outward normal. -> props"""
    props = []
    lens = [math.dist((a[0], a[2]), (b[0], b[2])) for (a, b), _ in segs]
    total = sum(lens)
    rows_ = style if total >= 12.0 else style[-1:]          # short gaps: the front row only (fewer actors; 49 small openings at the outpost)
    for offset, pattern in rows_:
        s, k = 0.0, 0
        while s < total - 0.3:
            art, axis, gap = pattern[k % len(pattern)]
            k += 1
            bb = db[art]
            ext = bb["size"][0] if axis == "x" else bb["size"][2]
            cl = (bb["min"][0] + bb["max"][0]) / 2, (bb["min"][2] + bb["max"][2]) / 2       # local centre of the footprint
            c = min(s + ext / 2, total - 0.01)
            t = c
            for ((a, b), (nx, nz)), ln in zip(segs, lens):
                if t <= ln or (a, b) == segs[-1][0]:
                    u = min(1.0, t / ln) if ln else 0.0
                    x, y, z = (a[i] + (b[i] - a[i]) * u for i in range(3))
                    dx, dz = ((b[0] - a[0]) / ln, (b[2] - a[2]) / ln) if ln else (1.0, 0.0)
                    break
                t -= ln
            px, pz = x - nx * (INSET + offset), z - nz * (INSET + offset)             # footprint centre on the row line
            th = math.atan2(-dz, dx) if axis == "x" else math.atan2(dx, dz)
            ox = cl[0] * math.cos(th) + cl[1] * math.sin(th)                           # local centre -> world offset
            oz = -cl[0] * math.sin(th) + cl[1] * math.cos(th)
            props.append({"art": art, "pos": [round(px - ox, 3), round(y, 3), round(pz - oz, 3)],
                          "quat": [0.0, round(math.sin(th / 2), 5), 0.0, round(math.cos(th / 2), 5)], "auto": True,
                          "fp": [round(ext, 2), round(bb["size"][2] if axis == "x" else bb["size"][0], 2), round(math.degrees(th), 1),
                                 round(px, 2), round(pz, 2), axis]})
            s += ext + gap
    return props


VIS_MIN = 10.0        # mixed mode: openings (chains) at least this long also get the world-style props (a player sees a street, not a 3 m gap)
VOID_RUN = 30.0       # a void-blocker card pair per this much closure line


def wall_panels(segs):
    """invisible 3 x 3 m collision panels (invis-collision, ND's own closer) along a chain, overlapping 0.1 m, on the loaded side"""
    import collision_walls
    out = []
    lens = [math.dist((a[0], a[2]), (b[0], b[2])) for (a, b), _ in segs]
    total = sum(lens)
    k = max(1, math.ceil(total / 2.9))
    for j in range(k):
        t = (j + 0.5) * total / k
        for ((a, b), (nx, nz)), ln in zip(segs, lens):
            if t <= ln or (a, b) == segs[-1][0]:
                u = min(1.0, t / ln) if ln else 0.0
                x, y, z = (a[i] + (b[i] - a[i]) * u for i in range(3))
                dx, dz = ((b[0] - a[0]) / ln, (b[2] - a[2]) / ln) if ln else (1.0, 0.0)
                pc = collision_walls.piece("panel", x - nx * INSET, y, z - nz * INSET, dx, dz)
                pc.pop("wall", None)
                pc["auto"] = True
                pc["fp"] = [3.0, 0.1, round(math.degrees(math.atan2(-dz, dx)), 1), round(x - nx * INSET, 2), round(z - nz * INSET, 2), "x"]
                out.append(pc)
                break
            t -= ln
    return out


def void_cards(segs):
    """black void-blocker cards (ND hides the void past its loaded art with them: scaled quads, 1 x 1 m at scale 1) just OUTSIDE the
    closure, one back-to-back pair per VOID_RUN m (which way the card is visible from is UNVERIFIED, hence two)"""
    out = []
    lens = [math.dist((a[0], a[2]), (b[0], b[2])) for (a, b), _ in segs]
    total = sum(lens)
    if total < 15.0:
        return out
    k = max(1, math.ceil(total / VOID_RUN))
    for j in range(k):
        t0, t1 = j * total / k, (j + 1) * total / k
        pts = []
        for tt in (t0, (t0 + t1) / 2, t1):
            t = tt
            for ((a, b), (nx, nz)), ln in zip(segs, lens):
                if t <= ln or (a, b) == segs[-1][0]:
                    u = min(1.0, t / ln) if ln else 0.0
                    pts.append(tuple(a[i] + (b[i] - a[i]) * u for i in range(3)) + (nx, nz))
                    break
                t -= ln
        (xa, ya, za, _, _), (xm, ym, zm, nx, nz), (xb, yb, zb, _, _) = pts
        ln_ = math.hypot(xb - xa, zb - za)
        if ln_ < 2.0:
            continue
        dx, dz = (xb - xa) / ln_, (zb - za) / ln_
        th = math.atan2(-dz, dx)
        for flip in (0, 1):
            ang = th + math.pi * flip
            off = 1.5 + 0.05 * flip
            out.append({"art": "void-blocker", "pos": [round(xm + nx * off, 3), round(min(ya, yb) + 4.0, 3), round(zm + nz * off, 3)],
                        "quat": [0.0, round(math.sin(ang / 2), 6), 0.0, round(math.cos(ang / 2), 6)], "scale": [round(ln_ + 1.0, 2), 10.0, 1.0],
                        "auto": True, "void": True, "fp": [round(ln_, 1), 0.2, round(math.degrees(th), 1), round(xm + nx * off, 2), round(zm + nz * off, 2), "x"]})
    return out


def mixed_chain(segs, style, db, void):
    """invisible panels along the chain; world-style front row where the chain is long enough to be a visible street; void cards"""
    props = wall_panels(segs)
    total = sum(math.dist((a[0], a[2]), (b[0], b[2])) for (a, b), _ in segs)
    if style and total >= VIS_MIN:
        props += lay_chain(segs, STYLES[style][-1:], db)
    if void:
        props += void_cards(segs)
    return props


def blockers(op, style=None, mixed=False, void=False):
    """props along the opening's edge chains, resampled every STEP m of arc length (so short navmesh edges don't
    leave gaps), INSET inside the loaded side, the dumpster's long side (local X) along the chain"""
    key = lambda v: (round(v[0] / 0.25), round(v[2] / 0.25))
    adj = {}
    for i, e in enumerate(op["edges"]):
        adj.setdefault(key(e["a"]), []).append(i)
        adj.setdefault(key(e["b"]), []).append(i)
    used, chains = set(), []
    for start in sorted(range(len(op["edges"])), key=lambda i: min(len(adj[key(op["edges"][i]["a"])]),
                                                                    len(adj[key(op["edges"][i]["b"])]))):
        if start in used:
            continue
        e = op["edges"][start]
        used.add(start)
        chain = [(e, False)]
        for fwd in (True, False):                 # grow both ways
            tip = e["b"] if fwd else e["a"]
            while True:
                nxt = [i for i in adj.get(key(tip), []) if i not in used]
                if not nxt:
                    break
                i = nxt[0]
                used.add(i)
                n = op["edges"][i]
                flip = key(n["b"]) == key(tip)
                if fwd:
                    chain.append((n, flip))
                else:
                    chain.insert(0, (n, not flip))
                tip = (n["a"] if flip else n["b"]) if fwd else (n["b"] if not flip else n["a"])
        chains.append(chain)
    props = []
    if mixed:
        db = _bounds_db() if style else None
        for chain in chains:
            segs = [((e["b"], e["a"]) if flip else (e["a"], e["b"]), e["n"]) for e, flip in chain]
            props += mixed_chain(segs, style, db, void)
        return props
    if style and not INVISIBLE:
        db = _bounds_db()
        for chain in chains:
            segs = [((e["b"], e["a"]) if flip else (e["a"], e["b"]), e["n"]) for e, flip in chain]
            props += lay_chain(segs, STYLES[style], db)
        return props
    for chain in chains:
        segs = [((e["b"], e["a"]) if flip else (e["a"], e["b"]), e["n"]) for e, flip in chain]
        total = sum(math.dist((a[0], a[2]), (b[0], b[2])) for (a, b), _ in segs)
        k = max(1, math.ceil(total / STEP))
        for j in range(k):
            s = (j + 0.5) * total / k
            for (a, b), (nx, nz) in segs:
                ln = math.dist((a[0], a[2]), (b[0], b[2]))
                if s <= ln or (a, b) == segs[-1][0]:
                    t = min(1.0, s / ln) if ln else 0.0
                    x, y, z = (a[i] + (b[i] - a[i]) * t for i in range(3))
                    dx, dz = ((b[0] - a[0]) / ln, (b[2] - a[2]) / ln) if ln else (1.0, 0.0)
                    yaw = math.atan2(-dz, dx)
                    if INVISIBLE:
                        import collision_walls
                        p = collision_walls.piece("block", x - nx * INSET, y, z - nz * INSET, dx, dz)
                        p.pop("wall")
                        p["auto"] = True
                        props.append(p)
                    else:
                        props.append({"art": BLOCKER, "pos": [round(x - nx * INSET, 3), round(y, 3), round(z - nz * INSET, 3)],
                                      "quat": [0.0, round(math.sin(yaw / 2), 5), 0.0, round(math.cos(yaw / 2), 5)], "auto": True})
                    break
                s -= ln
    out = []                                      # chains meeting at corners: drop props that overlap
    for p in props:
        if INVISIBLE or all(math.dist(p["pos"], o["pos"]) > STEP * 0.75 for o in out):   # walls: overlap is harmless
            out.append(p)
    return out


def run(key, write=False):
    m = sp_maps.spec(key)
    if m.get("nor") and "--force" not in sys.argv:       # No Return arenas ship as they are, no extra props / actors
        print(f"{key}: a No Return arena (\"nor\": true) - no boundary blockers (use --force to compute anyway)")
        if write:
            sp_maps.save_spec_props(key, [p for p in m.get("props", []) if not p.get("auto")])
        return [], []
    geo = [lv for lv in m["levels"] if lv != m["pak"] and sp_levels.tag(lv) == "GEO"]
    loaded = nav_json(key, key, geo)
    nbs = neighbours(m)
    nb = nav_json(key, key + "-nb", nbs)
    print(f"{key}: loaded navmesh {sum(len(v) for v in loaded.values())} polys in {len(loaded)} levels; "
          f"neighbours with navmesh {len(nb)} of {len(nbs)}")
    ops = openings(loaded, nb)
    style = m.get("blocker_style")
    mixed = m.get("wall_mode") == "mixed"       # invisible panels everywhere + world-style props on the long openings + void cards
    bnd = m.get("bounds")
    if bnd and m.get("cuts"):                    # the play space ends inside the loaded art (cuts): openings beyond it are not ours
        ops = [o for o in ops if bnd[0] - 12 <= o["centre"][0] <= bnd[1] + 12 and bnd[2] - 12 <= o["centre"][2] <= bnd[3] + 12]
    allp = []
    for o in ops:
        bl = blockers(o, style, mixed, m.get("void_cards"))
        allp += bl
        print(f"  opening at {o['centre']}  width {o['width']} m  -> {len(bl)} props "
              f"({'invisible-block-050x300x200' if INVISIBLE else (style or BLOCKER)})")
    if m.get("cuts"):
        # cut lines {"a": [x, z], "b": [x, z], "out": [nx, nz]}: a closure across open ground inside the loaded art; props only
        # where the loaded navmesh is within 2.5 m of the line
        lp = [p for v in loaded.values() for p in v]
        g = Grid(lp, 4.0)
        db = _bounds_db() if style else None
        for c in m["cuts"]:
            (ax, az), (bx, bz) = c["a"], c["b"]
            ln = math.hypot(bx - ax, bz - az)
            segs = []
            nstep = int(ln)
            n = tuple(c["out"])
            nn = math.hypot(*n)
            # sample the line; at every sample each FLOOR within reach (navmesh heights split where > 2.2 m apart: street, upper
            # floor, roof) continues a run of its own, so a cut across a building closes the upper floors too (spec cut "floors": true
            # needed; default = the old behaviour: the lowest floor only - the street level is the lowest big one)
            multi = c.get("floors", False)
            runs, done = [], []                       # runs = open stretches [[points], last y]
            for i in range(nstep + 1):
                x, z = ax + (bx - ax) * i / max(nstep, 1), az + (bz - az) * i / max(nstep, 1)
                polys = [lp[j] for j in g.g.get((int(x // 4), int(z // 4)), ())]
                ys = sorted(sum(v[1] for v in pp) / len(pp) for pp in polys if _inside(pp, x, z) or _dist_poly(pp, x, z) <= 2.5)
                floors = []
                for y in ys:
                    if floors and y - floors[-1][-1] <= 2.2:
                        floors[-1].append(y)
                    else:
                        floors.append([y])
                fy = [min(f) for f in floors] if multi else ([min(ys)] if ys else [])
                nxt = []
                for y in fy:
                    hit = next((r for r in runs if abs(r[1] - y) <= 1.6 and r not in nxt), None)
                    if hit is None:
                        hit = [[], y]
                    hit[0].append((x, y, z))
                    hit[1] = y
                    nxt.append(hit)
                done += [r for r in runs if r not in nxt]
                runs = nxt
            done += runs
            for r in done:                            # contiguous stretches with ground -> chains of one segment each
                cur = r[0]
                if len(cur) >= 3:
                    segs.append([((cur[0][0], cur[0][1], cur[0][2]), (cur[-1][0], cur[-1][1], cur[-1][2])), (n[0] / nn, n[1] / nn)])
            cp = []
            for sg in segs:
                if mixed:
                    cp += mixed_chain([tuple(sg)], style, db, m.get("void_cards"))
                elif style:
                    cp += lay_chain([tuple(sg)], STYLES[style], db)
                else:                                 # invisible-only (walls invisible, props placed by hand later)
                    cp += wall_panels([tuple(sg)])
            allp += cp
            print(f"  cut {c['a']} -> {c['b']}  ({ln:.0f} m, {len(segs)} stretches) -> {len(cp)} props")
    sj = os.path.join(HERE, "data", f"{key}-spawns.json")
    if os.path.exists(sj):                       # never wall in a spawn point or a supply box
        s = json.load(open(sj))
        pts = [p["pos"] for k in ("intro0", "intro1", "respawns", "boxes") for p in s.get(k, [])]
        near = [p for p in allp if any(math.dist(p["pos"], q) < 2.0 for q in pts)]
        if near:
            print(f"  {len(near)} blockers dropped: within 2 m of a spawn / box (move that spawn, then re-run)")
            allp = [p for p in allp if p not in near]
    print(f"{key}: {len(ops)} openings, {len(allp)} blockers")
    if write:
        keep = [p for p in m.get("props", []) if not p.get("auto")]      # (hand-placed props and ND's copied walls: nd_walls.py)
        sp_maps.save_spec_props(key, keep + allp)
    return ops, allp


if __name__ == "__main__":
    run(sys.argv[1], "--write" in sys.argv)
