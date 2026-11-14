"""Spawn + match-intro placement checker / fixer for every map of the rotation (new spawns and intros, none out of bounds).

  python spawn_intro.py check [<key>...|all]       # every spawner + the intro camera of each team against the map's navmesh grid
  python spawn_intro.py fix <key>... [--apply]     # re-fit the failing team starts (and any spawn/box/respawn nudged onto ground); --apply
                                                   # writes the committed spawner pak + (SP maps) tools/maps/data/<key>-spawns.json
  needs re/maps/seeds/ navmeshes (python pool_nav.py, read-only game extraction).

What "valid" means (the navmesh is the only collision-like data offline; layoutlib.Grid):
  spawn   ground within 0.6 m of its Y, on the main walkable part (play space: inside the bounds), 0.6 m from the nav edge
          (a wall / prop / drop), 6 of 8 points on a 0.5 m ring on ground (not inside a prop or against a wall), headroom
          (no second floor within 2 m above), outside every placed prop.
  intro   (t2r-ext feature_match_intro + intro camera, re/match-intro-2013.md): the player is put INTRO_BACK behind the spot and walks in
          while the camera sits ~4.5 m behind / 3 m above the team centroid looking ahead.  Per team the camera path (wide shot, walk-in
          anchor from -2.2 m to 0) must have ground under every camera sample inside the play space, an unbroken sight line from the head to
          the camera (no wall/prop hole), >= 6 m of ground behind and >= 7 m ahead.
"""
import json
import math
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import layoutlib as L  # noqa: E402
import layoutwalk as W  # noqa: E402
from layoutlib import Ctx, yaw_quat  # noqa: E402

INTRO_BACK = 2.2                       # t2r-ext.c INTRO_BACK
BACK0, BACK1, UP0, UP1 = 4.5, 4.6, 3.4, 2.6    # icam_shot: wide shot eased between
SPAWN_EDGE = 0.6
BOX_EDGE = 0.9
BACK_MIN = 4.2                         # ground behind the spot (error below): INTRO_BACK + a 2 m camera arm; below it the spring arm drops under 1.5 m and the
                                       # intro camera gives up (feature_match_intro swoops into the gameplay camera at once)
BACK_NEED = 6.0                        # good intro (warning below): INTRO_BACK + a camera arm that is not shrunk below ~3.8 m
FWD_MIN = 5.0                          # error below; FWD_NEED = good: look target 3.5 m + the crouch-walk
FWD_NEED = 7.0
CAM_BAD_MAX = 3                        # camera samples (of 9) that may lie off the play space / behind a hole before it is an error
RING_R = 0.5
PROP_PAD = 0.45
# ALL 4 characters must be visible during the whole intro camera sequence
VFOV = math.radians(60.0)              # vertical FOV of the intro camera (16:9)
ASPECT = 16.0 / 9.0
VIS_MARGIN = 0.86                      # head and feet must project inside |ndc| <= this (14% of the half frame kept free at the edges)
BODY_H = 1.8
BODY_R = 0.32                          # a teammate's body radius for the camera-line occlusion test
VIS_K = 13                             # time samples over the walk-in / wide shot


def labelled(lay):
    out = []
    if lay.get("player"):
        out.append(("player", "player", lay["player"]))
    for t in (0, 1):
        for i, p in enumerate(lay[f"intro{t}"]):
            out.append((f"T{t}-{i + 1}", "intro", p))
    for i, p in enumerate(lay["respawns"]):
        out.append((f"R{i + 1}", "respawn", p))
    for i, p in enumerate(lay["boxes"]):
        out.append((f"BOX{i + 1}", "box", p))
    return out


def props_of(key, ctx):
    """placed props that block: (x, z, half-extent-ish radius, y lo, y hi). SP maps: sp_maps.json props; pool: the pak's blockers."""
    out = []
    try:
        pb = json.load(open(os.path.join(L.DATA, "prop_bounds.json")))
    except OSError:
        pb = {}
    for p in ctx.spec.get("props", []) or []:
        b = pb.get(p.get("art"))
        r = (max(b["size"][0], b["size"][2]) / 2 if b else 1.0) * max(p.get("scale", 1) if isinstance(p.get("scale", 1), (int, float)) else 1, 1)
        pos = p.get("pos")
        if pos:
            out.append((pos[0], pos[2], r, pos[1] - 0.5, pos[1] + (b["size"][1] if b else 2.0)))
    if key in L.POOL:
        try:
            sp = L.pool_spawners(key)
        except (OSError, subprocess.CalledProcessError):
            sp = []
        for s in sp:
            if "blocker" in s["name"] and "itempos" not in s["name"]:
                b = pb.get(s.get("art"))
                r = (max(b["size"][0], b["size"][2]) / 2 if b else 1.2)
                out.append((s["pos"][0], s["pos"][2], r, s["pos"][1] - 0.5, s["pos"][1] + (b["size"][1] if b else 2.0)))
    return out


def point_problems(ctx, props, mutual, kind, pos):
    """-> [(severity, text)] of one spawner position"""
    nav, grid = ctx.nav, ctx.grid
    x, y, z = pos
    out = []
    g = grid.ground(x, z, y, 0.6)
    if g is None:
        g3 = grid.ground(x, z, y, 6.0)
        return [("ERR", "no ground within 0.6 m of its Y" + (f" (nearest {g3[0] - y:+.1f} m: floating / under the floor)" if g3 else " (off the navmesh: void / inside a wall)"))]
    if g[1] not in ctx.play:
        out.append(("ERR", "not on the main walkable part of the map (outside the play space)"))
    elif g[1] not in mutual and kind != "player":
        out.append(("WARN", "on a one-way part (a drop you cannot climb back from)"))
    if not ctx.inb(x, z):
        out.append(("ERR", "outside the map bounds"))
    need = BOX_EDGE if kind == "box" else SPAWN_EDGE
    ec = nav.edge_clear(x, z, g[0])
    if ec < need:
        out.append(("ERR", f"{ec:.2f} m from the nav edge (wall / prop / drop; need {need})"))
    ring = sum(1 for a in range(8) if grid.ground(x + RING_R * math.cos(a * math.pi / 4), z + RING_R * math.sin(a * math.pi / 4), g[0], 0.7))
    if ring < 6:
        out.append(("ERR", f"only {ring}/8 ring points on ground (inside / against geometry)"))
    for yy, pi in grid.cells.get((int(math.floor(x / grid.CELL)), int(math.floor(z / grid.CELL))), []):
        if g[0] + 0.6 < yy < g[0] + 2.0:
            out.append(("WARN", f"another floor {yy - g[0]:.1f} m above (low headroom)"))
            break
    for px, pz, r, lo, hi in props:
        if math.hypot(x - px, z - pz) < r + PROP_PAD and lo - 0.3 < y < hi:
            out.append(("ERR", f"inside a prop footprint at ({px:.1f}, {pz:.1f})"))
            break
    return out


def spawn_issues(key, ctx, lay):
    """-> [(label, severity, text)]"""
    props = props_of(key, ctx)
    mutual = W.mutual_region(ctx)
    return [(lab, sev, txt) for lab, kind, p in labelled(lay) for sev, txt in point_problems(ctx, props, mutual, kind, p["pos"])]


def team_frame(pts):
    c = L.centre(pts)
    fx = sum(math.sin(L.facing(p)) for p in pts)
    fz = sum(math.cos(L.facing(p)) for p in pts)
    return c, math.atan2(fx, fz)


def cam_samples(c, yaw):
    """camera positions (x, y, z) of the intro, before the swoop: wide shot eased over the walk-in (anchor from INTRO_BACK behind to the spot)"""
    d = (math.sin(yaw), math.cos(yaw))
    out = []
    for k in range(0, 9):
        w = k / 8.0
        w = w * w * (3 - 2 * w)
        back = BACK0 + (BACK1 - BACK0) * w
        up = UP0 + (UP1 - UP0) * w
        walk = INTRO_BACK * (1 - k / 8.0)
        a = (c[0] - d[0] * walk, c[1], c[2] - d[1] * walk)
        out.append(((a[0] - d[0] * back, a[1] + up, a[2] - d[1] * back), a))
    return out


def _norm3(v):
    n = math.sqrt(sum(a * a for a in v)) or 1.0
    return [a / n for a in v]


def _cross(a, b):
    return [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]]


def vis_problems(ctx, pts, yaw, c):
    """-> (problems, worst ndc) all 4 bodies (head + feet) of a team inside the intro camera frustum with a margin, not hidden behind a wall
    (camera -> body line over the navmesh) nor behind a teammate (head / chest ray vs the other bodies), at VIS_K samples of the walk-in."""
    grid = ctx.grid
    d = (math.sin(yaw), math.cos(yaw))
    th, tw = math.tan(VFOV / 2), math.tan(VFOV / 2) * ASPECT
    out_frame, hidden_wall, hidden_mate = set(), set(), set()
    worst = 0.0
    for k in range(VIS_K):
        u = k / (VIS_K - 1.0)
        w = u * u * (3 - 2 * u)
        back = BACK0 + (BACK1 - BACK0) * w
        up = UP0 + (UP1 - UP0) * w
        ahead = 1.0 + 2.5 * w
        look = 0.3 + 0.3 * w
        walk = INTRO_BACK * (1 - u)
        a = (c[0] - d[0] * walk, c[1], c[2] - d[1] * walk)
        cam = (a[0] - d[0] * back, a[1] + up, a[2] - d[1] * back)
        tgt = (a[0] + d[0] * ahead, a[1] + look, a[2] + d[1] * ahead)
        f = _norm3([tgt[i] - cam[i] for i in range(3)])
        r = _norm3(_cross(f, [0, 1, 0]))
        uu = _cross(r, f)
        bodies = []
        for p in pts:
            pos = p["pos"]
            bodies.append((pos[0] - d[0] * walk, pos[1], pos[2] - d[1] * walk))
        for i, b in enumerate(bodies):
            for hy in (0.0, BODY_H):
                v = [b[0] - cam[0], b[1] + hy - cam[1], b[2] - cam[2]]
                z = sum(v[j] * f[j] for j in range(3))
                if z < 0.5:
                    out_frame.add(i)
                    worst = 9.0
                    continue
                nx = sum(v[j] * r[j] for j in range(3)) / z / tw
                ny = sum(v[j] * uu[j] for j in range(3)) / z / th
                m = max(abs(nx), abs(ny))
                worst = max(worst, m)
                if m > VIS_MARGIN:
                    out_frame.add(i)
            # wall / prop between the camera and the body: a hole (no ground) of >= 1.2 m on the line, or the ground rising above the line
            n = max(2, int(math.hypot(cam[0] - b[0], cam[2] - b[2]) / 0.5))
            off, gy = 0.0, b[1]
            for s_ in range(1, n):
                t = s_ / n
                x, z_ = b[0] + (cam[0] - b[0]) * t, b[2] + (cam[2] - b[2]) * t
                g = grid.ground(x, z_, gy, 1.2)
                if g is None:
                    off += 0.5
                    if off >= 1.2:
                        hidden_wall.add(i)
                        break
                else:
                    off, gy = 0.0, g[0]
                    if g[0] > b[1] + BODY_H * 0.5 + (cam[1] - b[1] - BODY_H * 0.5) * t + 0.05:
                        hidden_wall.add(i)
                        break
            # a teammate in front: the camera -> head / chest ray passes through another body
            for hy in (BODY_H - 0.1, 1.1):
                tp = (b[0], b[1] + hy, b[2])
                for j, o in enumerate(bodies):
                    if j == i:
                        continue
                    for s_ in range(1, 40):
                        t = s_ / 40.0 * 0.96
                        px, py, pz = cam[0] + (tp[0] - cam[0]) * t, cam[1] + (tp[1] - cam[1]) * t, cam[2] + (tp[2] - cam[2]) * t
                        if o[1] - 0.1 < py < o[1] + BODY_H and math.hypot(px - o[0], pz - o[2]) < BODY_R:
                            hidden_mate.add(i)
                            break
    probs = []
    if out_frame:
        probs.append(("ERR", f"{len(out_frame)}/4 characters leave the intro camera frame (head / feet within {int(VIS_MARGIN * 100)}% of the half frame; worst {worst:.2f})"))
    if hidden_wall:
        probs.append(("ERR", f"{len(hidden_wall)}/4 characters hidden behind a wall / prop from the intro camera"))
    if hidden_mate:
        probs.append(("ERR", f"{len(hidden_mate)}/4 characters hidden behind a teammate in the intro camera"))
    return probs, worst


def run_min(grid, c, yaw, length, d_yaw):
    """shortest walkable run from c along yaw, over three lateral offsets (the group is 4 m wide)"""
    best = 1e9
    rx, rz = math.cos(yaw), -math.sin(yaw)
    for off in (-1.2, 0.0, 1.2):
        p = (c[0] + rx * off, c[1], c[2] + rz * off)
        g = grid.ground(p[0], p[2], p[1], 1.0)
        if g is None:
            continue
        best = min(best, grid.run((p[0], g[0], p[2]), yaw + d_yaw, length))
    return best if best < 1e8 else 0.0


def intro_report(ctx, pts, other):
    """camera-path / run metrics of one team start -> dict + list of problems"""
    grid = ctx.grid
    c, yaw = team_frame(pts)
    oc = L.centre(other)
    probs = []
    back = run_min(grid, c, yaw, 10.0, math.pi)
    fwd = run_min(grid, c, yaw, 12.0, 0.0)
    if back < BACK_NEED:
        probs.append(("ERR" if back < BACK_MIN else "WARN", f"only {back:.1f} m of ground behind the team (the walk-in starts {INTRO_BACK} m back and the camera 4.5 m behind that; need {BACK_NEED}, error below {BACK_MIN})"))
    if fwd < FWD_NEED:
        probs.append(("ERR" if fwd < FWD_MIN else "WARN", f"only {fwd:.1f} m of ground ahead (need {FWD_NEED}, error below {FWD_MIN})"))
    bad_ground = bad_sight = bad_out = 0
    for (cx, cy, cz), a in cam_samples(c, yaw):
        hg = grid.ground(cx, cz, c[1], 4.0)
        if hg is None or hg[1] not in ctx.play:
            bad_ground += 1
        if not ctx.inb(cx, cz):
            bad_out += 1
        # sight line head -> camera over the nav: a hole of >= 1.2 m is a wall / prop between
        hx, hz = a[0], a[2]
        n = max(2, int(math.hypot(cx - hx, cz - hz) / 0.5))
        off, hole = 0.0, False
        gy = c[1]
        for i in range(1, n + 1):
            t = i / n
            g = grid.ground(hx + (cx - hx) * t, hz + (cz - hz) * t, gy, 1.2)
            if g is None:
                off += 0.5
                if off >= 1.2:
                    hole = True
                    break
            else:
                off, gy = 0.0, g[0]
        bad_sight += hole
    if bad_ground:
        probs.append(("ERR" if bad_ground > CAM_BAD_MAX else "WARN", f"{bad_ground}/9 camera positions are over no ground of the play space (camera outside the map)"))
    if bad_out:
        probs.append(("ERR" if bad_out > 0 else "WARN", f"{bad_out}/9 camera positions outside the map bounds"))
    if bad_sight:
        probs.append(("ERR" if bad_sight > CAM_BAD_MAX else "WARN", f"{bad_sight}/9 camera sight lines cross a wall / prop (camera inside geometry)"))
    vp, vworst = vis_problems(ctx, pts, yaw, c)
    probs += vp
    toward = math.atan2(oc[0] - c[0], oc[2] - c[2])
    off = math.degrees(L.ang_diff(yaw, toward))
    return {"vis_worst": round(vworst, 2), "centre": [round(v, 2) for v in c], "yaw": round(math.degrees(yaw), 1), "back": round(back, 1), "fwd": round(fwd, 1),
            "cam_ground_bad": bad_ground, "cam_sight_bad": bad_sight, "facing_off_enemy": round(off)}, probs


def check(key, lay=None, ctx=None):
    lay = lay or L.load_layout(key)
    ctx = ctx or Ctx(key, lay)
    if not ctx.nav:
        return None
    issues = spawn_issues(key, ctx, lay)
    intro = {}
    for t in (0, 1):
        rep, probs = intro_report(ctx, lay[f"intro{t}"], lay[f"intro{1 - t}"])
        intro[t] = rep
        for sev, txt in probs:
            issues.append((f"intro T{t}", sev, txt))
    return {"issues": issues, "intro": intro, "n": len(labelled(lay))}


# ---------------------------------------------------------------------------------------------- fixing
def _norm(x):
    return re.sub(r"[\d.]+", "#", x)[:34]


def _newness(key, ctx, lay, base):
    """(new errors, new warnings) of the full layout check vs the sets of the layout as it stands (texts compared by their first 28 chars)"""
    e, w, m = L.check(key, lay, ctx, strict=key not in L.POOL)
    be, bw = base
    return [x for x in e if _norm(x) not in be], [x for x in w if _norm(x) not in bw], m


def fit_team(ctx, lay, t, radius=18.0, key=None):
    """top local candidates (strict first; relax 1: a start 7 m nearer the enemy; relax 2: also a camera arm down to 3.4 m behind and a wider search),
    each judged by the whole-map check (new errors / warnings, start balance): -> (pen, centre, yaw, pts, rep, relax) or None"""
    key = key or ctx.key
    e0, w0, m0 = L.check(key, lay, ctx, strict=key not in L.POOL)
    base = ({_norm(x) for x in e0}, {_norm(x) for x in w0})
    best = None
    for relax, rad in ((0, radius), (1, radius), (2, radius + 8.0)):
        for sc, c, yaw, pts, rep in _fit_team(ctx, lay, t, rad, relax):
            trial = dict(lay)
            trial[f"intro{t}"] = pts
            ne, nw, m = _newness(key, ctx, trial, base)
            bal = m.get("start_balance", 0.5)
            old_bal = m0.get("start_balance", 0.5)
            pen = 10 * len(ne) + sum(6 if re.search(r'only .* apart|unbalanced|see each other', x) else 3 for x in nw) - 0.6 * sc + 25 * max(0.0, abs(bal - 0.5) - max(0.15, abs(old_bal - 0.5)))
            if best is None or pen < best[0]:
                best = (pen, c, yaw, pts, rep, relax, [x[:60] for x in ne + nw])
        if best and best[0] < 10:
            break
    return best


# (right, forward) offsets of the 4 spawns, best-looking first (penalty = score cost).  The intro camera sits behind the group, so nobody may stand
# in line with a teammate (the rear one would hide the lead): the wedge's rear man is the one that usually fails, the others keep every body side by side.
FORMS = [
    (0.0, [(0.0, 0.8), (-1.9, -0.7), (1.9, -0.7), (0.0, -2.3)]),               # the original wedge
    (0.4, [(-0.8, 0.7), (0.8, 0.7), (-2.0, -0.5), (2.0, -0.5)]),               # tight V, arms back and out
    (0.8, [(-2.4, 0.4), (-0.8, -0.4), (0.8, 0.4), (2.4, -0.4)]),               # staggered line
    (1.2, [(-2.2, 0.0), (-0.75, 0.0), (0.75, 0.0), (2.2, 0.0)]),               # line abreast
    (1.6, [(-1.8, 0.0), (-0.6, 0.0), (0.6, 0.0), (1.8, 0.0)]),                 # tight line (>= 1.2 m apart)
    (2.0, [(-0.7, 0.9), (0.7, 0.3), (-0.7, -0.3), (0.7, -0.9)]),               # alleys / doorways: zig-zag column
    (2.5, [(0.6, 1.6), (-0.6, 0.3), (0.6, -1.0), (-0.6, -2.3)]),
]

# zig-zag columns / pairs of any width for tight places: two rails w m either side of the axis, the men staggered along it
for _w in (0.65, 0.8, 1.0, 1.3, 1.7):
    for _s in (0.4, 0.8, 1.2):
        for _m in (1, -1):
            FORMS.append((2.2 + _w * 0.3 + _s * 0.2, [(-_m * _w, 1.5 * _s), (_m * _w, 0.5 * _s), (-_m * _w, -0.5 * _s), (_m * _w, -1.5 * _s)]))


def fit_form(ctx, centre, yaw, form):
    """the 4 spawn positions of a formation at centre facing yaw (every one on mutual play-space ground, 0.8 m from the nav edge) or None"""
    import layout as LY
    nav, grid = ctx.nav, ctx.grid
    mut = W.mutual_region(ctx)
    cand = []
    for r, f in form:
        x, z = LY.at(centre, yaw, r, f)
        g = grid.ground(x, z, centre[1], 0.7)
        if g is None or g[1] not in ctx.play or nav.edge_clear(x, z, g[0]) < 0.65 or g[1] not in mut or (ctx.bounds and not ctx.inb(x, z)):
            return None
        cand.append((x, g[0], z))
    if not all(math.dist(p, q) >= L.RULES["intro_group_min"] for i, p in enumerate(cand) for q in cand[i + 1:]):
        return None
    return cand


def _fit_team(ctx, lay, t, radius, relax):
    """local candidates for team t that pass the intro report -> up to 14 of (score, centre, yaw, pts, rep), best first, one per 4 m cell"""
    import layout as LY
    grid, nav = ctx.grid, ctx.nav
    pts0, other = lay[f"intro{t}"], lay[f"intro{1 - t}"]
    c0, y0 = team_frame(pts0)
    oc = L.centre(other)
    oy = other and team_frame(other)
    p_o = ctx.poly_at(oc)
    found = []
    steps = range(-int(radius), int(radius) + 1, 2 if relax < 2 else 1)
    for dx in steps:
        for dz in steps:
            if dx * dx + dz * dz > radius * radius:
                continue
            x, z = c0[0] + dx, c0[2] + dz
            g = grid.ground(x, z, c0[1], 3.0)
            if not g or g[1] not in ctx.play or nav.edge_clear(x, z, g[0]) < 1.2:
                continue
            c = (x, g[0], z)
            toward = math.atan2(oc[0] - x, oc[2] - z)
            base = []
            if p_o is not None:
                r = LY.route_dir(ctx, g[1], p_o)
                if r is not None:
                    base.append(r)
            base += [toward, y0]
            seen = set()
            for b in base:
                for dy in (0, 0.25, -0.25, 0.5, -0.5, 0.8, -0.8):
                    yaw = b + dy
                    k = round(yaw, 2)
                    if k in seen:
                        continue
                    seen.add(k)
                    for fpen, form in FORMS:
                        fp = fit_form(ctx, c, yaw, form)
                        if fp is None:
                            continue
                        pts = [{"pos": list(p), "quat": yaw_quat(yaw)} for p in fp]
                        rep, probs = intro_report(ctx, pts, other)
                        if any(sv == "ERR" and not (relax >= 2 and "ground behind" in tx and rep["back"] >= 3.4) for sv, tx in probs):
                            continue
                        if rep["facing_off_enemy"] > 80:
                            continue
                        dist_e = math.hypot(rep["centre"][0] - oc[0], rep["centre"][2] - oc[2])
                        if dist_e < L.RULES["intro_enemy_min"] - (7.0 if relax else 0.0):
                            continue
                        # near a respawn: bad (a fresh spawn in the middle of a start); close to the old spot: good (it was placed by hand for a reason)
                        near_r = min((math.dist((x, z), (r["pos"][0], r["pos"][2])) for r in lay["respawns"]), default=99)
                        sc = -3.0 * len(probs) + min(rep["fwd"], 12) * 0.4 + min(rep["back"], 10) * 0.5 - 0.3 * math.hypot(dx, dz) - 3.0 * abs(dy) \
                            - (4.0 if near_r < 6 else 0.0) - 0.05 * rep["facing_off_enemy"] - fpen - 6.0 * max(0.0, rep["vis_worst"] - 0.7)
                        found.append((sc, c, yaw, pts, rep))
    found.sort(key=lambda f: -f[0])
    out, cells = [], set()
    for f in found:
        cell = (round(f[1][0] / 4), round(f[1][2] / 4), round(f[2], 0))
        if cell in cells:
            continue
        cells.add(cell)
        out.append(f)
        if len(out) >= 14:
            break
    return out


def write_pak(key, moves):
    """moves: {spawner name: (pos, quat)} written into tools/features/levels/to1-pvp-<pak>-ingame.pak in place (levels.py find_offsets)"""
    import struct
    sys.path.insert(0, L.SPAWNS)
    import levels
    short = key if key in L.POOL else "train-station" if key == "train-station" else key
    sp = levels.spawners(short)
    path = levels.pak_path(short)
    b = bytearray(open(path, "rb").read())
    offs = levels.find_offsets(b, sp)
    by = {x["name"]: x for x in sp}
    extra = {}
    for name, (pos, quat) in moves.items():
        if name.startswith("to1-supplybox-"):              # a box takes its item positions along (translation only)
            old = by[name]["pos"]
            for x in sp:
                if x["name"].startswith(name + "-itempos-"):
                    extra[x["name"]] = ([x["pos"][j] + pos[j] - old[j] for j in range(3)], x["quat"])
    moves = dict(moves, **extra)
    for name, (pos, quat) in sorted(moves.items(), key=lambda kv: kv[0] not in ("player", "camera")):
        if name in ("player", "camera") and name not in by:
            continue
        if name in ("player", "camera"):         # they share one transform (and spawn-point-1 at times): patch every record with the old bytes
            op, oq = struct.pack("<3f", *by[name]["pos"]), struct.pack("<4f", *by[name]["quat"])
            i = b.find(op)
            while i >= 0:
                if b[i + 16:i + 32] == oq:
                    struct.pack_into("<3f", b, i, *pos)
                    struct.pack_into("<4f", b, i + 16, *quat)
                i = b.find(op, i + 1)
            continue
        struct.pack_into("<3f", b, offs[name], *pos)
        struct.pack_into("<4f", b, offs[name] + 16, *quat)
    open(path, "wb").write(b)


def fix(key, apply=False):
    lay = L.load_layout(key)
    ctx = Ctx(key, lay)
    res = check(key, lay, ctx)
    teams = [t for t in (0, 1) if any((lab == f"intro T{t}" or lab.startswith(f"T{t}-")) and sev == "ERR" for lab, sev, _ in res["issues"])]
    moves, notes = {}, []
    for t in teams:
        b = fit_team(ctx, lay, t, key=key)
        if b is None:
            notes.append(f"T{t}: no passing start within reach - left as is")
            continue
        sc, c, yaw, pts, rep, relax, why = b
        old_c, old_y = team_frame(lay[f"intro{t}"])
        notes.append(f"T{t}: ({old_c[0]:.0f}, {old_c[2]:.0f}) {math.degrees(old_y):.0f} deg -> ({c[0]:.0f}, {c[2]:.0f}) {math.degrees(yaw):.0f} deg  back {rep['back']} fwd {rep['fwd']}" + (f"  (relaxed {relax})" if relax else "") + (f"  new: {why}" if why else ""))
        for i, p in enumerate(pts):
            lay[f"intro{t}"][i] = {"pos": [round(v, 3) for v in p["pos"]], "quat": p["quat"]}
            moves[f"to1-t{t}-intro-spawn-point-{i + 1}"] = (lay[f"intro{t}"][i]["pos"], p["quat"])
    # respawns / boxes that fail on their own (on a wall edge, off the play space, in a prop): the nearest valid spot (<= 12 m), same facing
    props, mutual = props_of(key, ctx), W.mutual_region(ctx)
    for kind, name_fmt, lst in (("respawn", "to1-spawn-point-{}", lay["respawns"]), ("box", "to1-supplybox-{}", lay["boxes"])):
        for i, p in enumerate(lst):
            if not any(sv == "ERR" for sv, _ in point_problems(ctx, props, mutual, kind, p["pos"])):
                continue
            best = None
            for r10 in range(2, 121, 3):
                for a in range(16):
                    x, z = p["pos"][0] + r10 / 10 * math.cos(a * math.pi / 8), p["pos"][2] + r10 / 10 * math.sin(a * math.pi / 8)
                    cells = [c for c in ctx.grid.cells.get((int(math.floor(x / ctx.grid.CELL)), int(math.floor(z / ctx.grid.CELL))), []) if c[1] in ctx.play]
                    if not cells:
                        continue
                    g = min(cells, key=lambda c: abs(c[0] - p["pos"][1]))      # the main floor nearest in height (a spawn on a cut-off upper floor drops to it)
                    q = (x, g[0], z)
                    pr = point_problems(ctx, props, mutual, kind, q)
                    if not any(sv == "ERR" for sv, _ in pr) and min(
                            (math.dist(q, o["pos"]) for j, o in enumerate(lst) if j != i), default=99) >= (L.RULES["box_box_min"] if kind == "box" else 5.0):
                        best = q
                        break
                if best:
                    break
            lab = ("BOX" if kind == "box" else "R") + str(i + 1)
            if best is None:
                notes.append(f"{lab}: no valid spot within 12 m - left as is")
                continue
            notes.append(f"{lab}: ({p['pos'][0]:.1f}, {p['pos'][2]:.1f}) -> ({best[0]:.1f}, {best[2]:.1f})  {math.dist(p['pos'], best):.1f} m")
            newpos = [round(best[0], 3), round(best[1] - (0.04 if kind == "box" else 0.0), 3), round(best[2], 3)]
            moves[name_fmt.format(i + 1)] = (newpos, p["quat"])
            lst[i] = {"pos": newpos, "quat": p["quat"]}
    if moves and lay.get("player"):
        t0 = lay["intro0"][0]
        lay["player"] = {"pos": t0["pos"], "quat": t0["quat"]}
        moves["player"] = (t0["pos"], t0["quat"])
        moves["camera"] = (t0["pos"], t0["quat"])
    for n in notes:
        print("  " + n)
    if apply and moves:
        write_pak(key, moves)
        if key not in L.POOL:
            p = os.path.join(L.DATA, f"{key}-spawns.json")
            d = json.load(open(p))
            for k in ("intro0", "intro1", "player"):
                d[k] = lay[k]
            json.dump(d, open(p, "w"), indent=1)
        if key in L.POOL:
            import subprocess
            subprocess.run(["pwsh", "-NoProfile", "-File", os.path.join(L.SPAWNS, "dump_json.ps1"), "-Pak", os.path.abspath(os.path.join(L.TOOLS, "features", "levels", f"to1-pvp-{key}-ingame.pak")),
                            "-Out", os.path.join(L.SPAWNS, f"{key}.json")], check=True, stdout=subprocess.DEVNULL)
    return notes


def keys_arg(a):
    return L.keys_in_rotation() if not a or a == ["all"] else a


def main(argv):
    if len(argv) < 2 or argv[1] not in ("check", "fix"):
        print(__doc__)
        return 0
    apply = "--apply" in argv
    keys = keys_arg([a for a in argv[2:] if not a.startswith("--")])
    bad = 0
    for k in keys:
        if argv[1] == "fix":
            print(f"== {k}")
            fix(k, apply)
            continue
        r = check(k)
        if r is None:
            print(f"== {k}: no navmesh seed (python pool_nav.py {k})")
            continue
        errs = [i for i in r["issues"] if i[1] == "ERR"]
        bad += len(errs)
        print(f"== {k}: {r['n']} spawners, {len(errs)} errors, {len(r['issues']) - len(errs)} warnings   intro T0 {r['intro'][0]}   T1 {r['intro'][1]}")
        for lab, sev, txt in r["issues"]:
            print(f"   {sev:4} {lab}: {txt}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
