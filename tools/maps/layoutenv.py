"""Floor snapping, cover and interior landmarks of a map's navmesh grid (tools/maps/layoutlib.py Grid / Ctx).
Rules: re/maps/layout-rules-2013.md section 6."""
import json
import math
import os

BOX_R = 0.55           # a supply box footprint (m, radius): the crate is about 1.0 x 0.7 m, 0.33-0.37 m tall
FLAT_MAX = 0.05        # the ground under a box may vary this much (m): floor test, the crate is 0.33-0.37 m tall, more spread and one side floats or sinks
SNAP_DROP = 0.04       # Y = navmesh - 4 cm on flat ground (test on Train Station: dy -0.08 and 0.00 both look right, -0.15 sinks 4/10, +0.10 floats 3/10)
INTERIOR_HINT = ("window", "door", "drawer", "bathroom", "breakroom", "-int-", "interior", "lobby", "shelf")


def foot(grid, x, y, z, r=BOX_R):
    """(lowest, highest) navmesh ground height under a footprint of radius r around (x, z), on the floor the point stands on"""
    ys = []
    pts = [(0.0, 0.0)] + [(r * math.cos(a * math.pi / 6), r * math.sin(a * math.pi / 6)) for a in range(12)] +           [(0.5 * r * math.cos(a * math.pi / 3), 0.5 * r * math.sin(a * math.pi / 3)) for a in range(6)]
    for dx, dz in pts:
        g = grid.ground(x + dx, z + dz, y, 0.9)
        if g:
            ys.append(g[0])
    return (min(ys), max(ys)) if ys else (y, y)


def snap_y(grid, pos, r=BOX_R):
    """Y a box / spawn stands on: lowest ground of its footprint minus SNAP_DROP (the crate sinks a hair rather than floats)"""
    return foot(grid, pos[0], pos[1], pos[2], r)[0] - SNAP_DROP


def flat(grid, pos, r=BOX_R):
    lo, hi = foot(grid, pos[0], pos[1], pos[2], r)
    return hi - lo


def cover(grid, pos, reach=3.0):
    """directions (of 16) blocked within `reach` m: the ground ends (wall / prop / obstacle = a hole in the navmesh)"""
    return sum(1 for a in range(16) if grid.run(pos, a * math.pi / 8, reach, 0.5, 1.0) < reach - 0.5)


def cover_score(n):
    """0..1: something to crouch behind (3..9 of 16 directions blocked), open field 0, a pocket (> 11 blocked: dead end) 0"""
    if n < 1:
        return 0.0
    if n <= 3:
        return n / 4.0
    if n <= 9:
        return 1.0
    return max(0.0, 1.0 - (n - 9) / 5.0)


def interiors(ctx, seed_file=None):
    """big enclosed spaces of the play area: [{area, centre, cells, bbox, hints}], best first. A cell is enclosed when the
    ground ends within 9 m in >= 12 of 16 directions (walls all around); neighbouring enclosed cells (1 m lattice) form one
    space. No collision offline, so open alleys can qualify: spaces are ranked by area and by how many window / door / drawer /
    bathroom spawners of the level lie in them (the level's own marks of a building)."""
    if getattr(ctx, "_interiors", None) is not None:
        return ctx._interiors
    g = ctx.grid
    step = 2 if sum(ctx.nav.area[i] for i in ctx.play) < 12000 else 4        # 1 m / 2 m lattice (big maps: coarser, they are slow)
    enc = {}
    for (ix, iz), lst in g.cells.items():
        if ix % step or iz % step:
            continue
        for y, pi in lst:
            if pi not in ctx.play:
                continue
            x, z = (ix + .5) * g.CELL, (iz + .5) * g.CELL
            n = sum(1 for a in range(16) if g.run((x, y, z), a * math.pi / 8, 10.0) < 9.0)
            if n >= 12:
                enc[(ix // step, iz // step, round(y / 2.0))] = (x, y, z)
    seen, out = set(), []
    for k0 in enc:
        if k0 in seen:
            continue
        comp, st = [], [k0]
        seen.add(k0)
        while st:
            c = st.pop()
            comp.append(enc[c])
            for dx in (-1, 0, 1):
                for dz in (-1, 0, 1):
                    for dy in (-1, 0, 1):
                        n2 = (c[0] + dx, c[1] + dz, c[2] + dy)
                        if n2 in enc and n2 not in seen:
                            seen.add(n2)
                            st.append(n2)
        area = len(comp) * (step * g.CELL) ** 2
        if area < 80:
            continue
        out.append({"area": area, "cells": comp, "hints": 0,
                    "centre": (sum(p[0] for p in comp) / len(comp), sum(p[1] for p in comp) / len(comp), sum(p[2] for p in comp) / len(comp)),
                    "bbox": (min(p[0] for p in comp), max(p[0] for p in comp), min(p[2] for p in comp), max(p[2] for p in comp))})
    if seed_file and os.path.exists(seed_file) and out:
        for s in json.load(open(seed_file)):
            nm = (s["name"] + " " + (s.get("art") or "")).lower()
            if any(h in nm for h in INTERIOR_HINT):
                x, y, z = s["pos"]
                for c in out:
                    b = c["bbox"]
                    if b[0] - 3 <= x <= b[1] + 3 and b[2] - 3 <= z <= b[3] + 3:
                        c["hints"] += 1
    for c in out:
        c["rank"] = c["area"] * (1 + 0.04 * c["hints"])
    out.sort(key=lambda c: -c["rank"])
    ctx._interiors = out
    return out


def in_interior(c, pos, margin=2.5):
    return any(math.hypot(p[0] - pos[0], p[2] - pos[2]) <= margin and abs(p[1] - pos[1]) < 1.6 for p in c["cells"])


def interior_index(ints, min_area=80.0):
    """-> inside(pos): index of the enclosed space (in `ints`, best first) containing pos (within 1.5 m of one of its cells, same
    floor), -1 outside. Fast: the cells are hashed on a 2 m lattice."""
    h = {}
    for i, c in enumerate(ints):
        if c["area"] < min_area:
            continue
        for p in c["cells"]:
            h.setdefault((int(p[0] // 2), int(p[2] // 2)), []).append((p[1], i))

    def inside(pos):
        kx, kz = int(pos[0] // 2), int(pos[2] // 2)
        best = -1
        for dx in (-1, 0, 1):
            for dz in (-1, 0, 1):
                for y, i in h.get((kx + dx, kz + dz), ()):
                    if abs(y - pos[1]) < 1.6 and (best < 0 or i < best):
                        best = i
        return best
    return inside


LANDMARK_WORDS = ("container", "bridge", "track", "rail", "perch", "tower", "vantage", "train", "overpass", "stairs", "ladder-")


def landmarks(ctx, ints, seed_file=None):
    """points people would walk to: the enclosed spaces' centres and level spawners named like a container / bridge / track / perch / tower"""
    out = [(c["centre"][0], c["centre"][2]) for c in ints if c["area"] >= 80.0]
    if seed_file and os.path.exists(seed_file):
        seen = set()
        for s in json.load(open(seed_file)):
            nm = (s["name"] + " " + (s.get("art") or "")).lower()
            if any(w in nm for w in LANDMARK_WORDS):
                k = (round(s["pos"][0] / 6), round(s["pos"][2] / 6))
                if k not in seen:
                    seen.add(k)
                    out.append((s["pos"][0], s["pos"][2]))
    if ctx.bounds:
        b = ctx.bounds
        out = [p for p in out if b[0] - 5 <= p[0] <= b[1] + 5 and b[2] - 5 <= p[1] <= b[3] + 5]
    return out


def box_exclusions(ctx, seed_file=None):
    """[(x, z, r)] where no supply box may stand: inside vehicles / boxcars (and navmesh only reachable through their doors), and the boxcar -> ladder -> resort
    route area of Train Station (treat as out of bounds, it is to be blocked off). From the level's own spawners (boxcar / railcar art, train
    door / train exit / resort reveal names) plus the map spec's "box_exclude": [{"x", "z", "r"}]"""
    out = [(e["x"], e["z"], e["r"]) for e in (ctx.spec.get("box_exclude") or [])]
    if seed_file and os.path.exists(seed_file):
        seen = set()
        for s in json.load(open(seed_file)):
            nm = (s["name"] + " " + (s.get("art") or "")).lower()
            r = 8.0 if any(w in nm for w in ("boxcar", "railcar", "rail-car", "train-car")) else \
                10.0 if any(w in nm for w in ("train-exit", "opens-train-door", "resort-reveal")) else 0.0
            if r:
                k = (round(s["pos"][0] / 4), round(s["pos"][2] / 4), r)
                if k not in seen:
                    seen.add(k)
                    out.append((s["pos"][0], s["pos"][2], r))
    if ctx.bounds:
        b = ctx.bounds
        out = [e for e in out if b[0] - 15 <= e[0] <= b[1] + 15 and b[2] - 15 <= e[1] <= b[3] + 15]
    return out
