"""Offline check (a player spawned beyond the closed-off areas of Capitol Hill and got stuck): every spawn kind of the SP-section
maps (team start / intro spawns, player, respawns, supply boxes) must lie in the PLAYABLE part of the map:
  - inside the spec bounds and on the right side of every spec 'cut' (the closed-off exits), 0.5 m margin
  - not in a 'dead_zone' (ground the navmesh shows but you cannot get back onto)
  - not inside / on the far side of the placed invisible walls (props 'invisible-block-*' / 'invis-collision'): navmesh flood from team 0's start where
    every navmesh edge crossing a wall footprint is cut; every point must be reached from team 0's start AND team 1's start.
Run: python tools/tests/test_closed_areas.py [key...]   (needs re/maps/seeds/<key>-nav.json; maps without it are listed and skipped)"""
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "maps"))
import layoutlib as L  # noqa: E402

KEYS = ["capitol-shops"]
# rooms sealed with solid collision (x0, x1, z0, z1, y0, y1): nothing may spawn inside. Capitol: none now (the first-floor north room became playable: hall doorway open, west doorway / windows / north hole sealed, a respawn inside)
SEALED = {"capitol-shops": []}
MARGIN = 0.5
FAILS = []


def check(cond, what):
    print(("ok   " if cond else "FAIL ") + what)
    if not cond:
        FAILS.append(what)


def walls(spec):
    """[(ax, az, bx, bz, ylo, yhi)] footprints (centre line of the long side) of the placed invisible walls"""
    out = []
    for p in spec.get("props", []):
        art = p["art"]
        if art.startswith("invisible-block"):
            yaw = 2 * math.atan2(p["quat"][1], p["quat"][3])
            c, s = math.cos(yaw), math.sin(yaw)
            lx, lz = 0.25, 1.0                     # local centre of the 0.5 x 2 footprint (origin = bottom corner)
            cx, cz = p["pos"][0] + lx * c + lz * s, p["pos"][2] - lx * s + lz * c
            dx, dz, half = s, c, 1.0               # long side = local +Z
            y0, y1 = p["pos"][1], p["pos"][1] + 3.0
        elif art == "invis-collision":
            yaw = 2 * math.atan2(p["quat"][1], p["quat"][3])
            c, s = math.cos(yaw), math.sin(yaw)
            cx, cz = p["pos"][0], p["pos"][2]
            dx, dz, half = c, -s, 1.5              # long side = local +X
            y0, y1 = p["pos"][1] - 1.5, p["pos"][1] + 1.5
        else:
            continue
        out.append((cx - dx * half, cz - dz * half, cx + dx * half, cz + dz * half, y0, y1))
    return out


def seg_hit(ax, az, bx, bz, cx, cz, dx, dz):
    def cr(ux, uz, vx, vz):
        return ux * vz - uz * vx
    r, s = (bx - ax, bz - az), (dx - cx, dz - cz)
    den = cr(*r, *s)
    if abs(den) < 1e-9:
        return False
    t = cr(cx - ax, cz - az, *s) / den
    u = cr(cx - ax, cz - az, *r) / den
    return 0 <= t <= 1 and 0 <= u <= 1


def reach(ctx, ws, start):
    nav = ctx.nav
    seen, st = {start}, [start]
    while st:
        u = st.pop()
        for v in nav.adj[u]:
            if v in seen or v not in ctx.play:
                continue
            ya, yb = nav.cen[u][1], nav.cen[v][1]
            if any(seg_hit(nav.cen[u][0], nav.cen[u][2], nav.cen[v][0], nav.cen[v][2], *w[:4]) and min(ya, yb) - 0.5 < w[5] and max(ya, yb) + 1.0 > w[4] for w in ws):
                continue
            seen.add(v)
            st.append(v)
    return seen


skipped = []
for key in (sys.argv[1:] or KEYS):
    lay = L.load_layout(key)
    spec = L.spec_of(key)
    pts = [("player", lay["player"])] if lay.get("player") else []
    pts += [(f"T0-{i + 1}", p) for i, p in enumerate(lay["intro0"])] + [(f"T1-{i + 1}", p) for i, p in enumerate(lay["intro1"])]
    pts += [(f"R{i + 1}", p) for i, p in enumerate(lay["respawns"])] + [(f"BOX{i + 1}", p) for i, p in enumerate(lay["boxes"])]
    b = spec["bounds"]
    for lab, p in pts:
        x, y, z = p["pos"]
        check(b[0] + MARGIN <= x <= b[1] - MARGIN and b[2] + MARGIN <= z <= b[3] - MARGIN, f"{key} {lab}: inside the bounds (x {x:.1f}, z {z:.1f})")
        for c in spec.get("cuts", []):                      # closed-off exit: `out` is the outward direction of the line a-b
            d = (x - c["a"][0]) * c["out"][0] + (z - c["a"][1]) * c["out"][1]
            check(d <= -MARGIN, f"{key} {lab}: on the playable side of the cut at {c['a']} ({d:+.1f} m)")
        for r in SEALED.get(key, []):
            check(not (r[0] <= x <= r[1] and r[2] <= z <= r[3] and r[4] <= y <= r[5]), f"{key} {lab}: not inside the sealed room {r[:4]}")
        for dz in spec.get("dead_zones", []):
            r = dz["rect"]
            check(not (r[0] <= x <= r[1] and r[2] <= z <= r[3] and dz["y"][0] <= y <= dz["y"][1]), f"{key} {lab}: not in dead zone '{dz['name'][:30]}'")
    if not os.path.exists(L.nav_file(key)):
        skipped.append(key)
        continue
    ctx = L.Ctx(key, lay)
    ws = walls(spec)
    for t in (0, 1):
        s0 = ctx.poly_at(lay[f"intro{t}"][0]["pos"])
        check(s0 is not None, f"{key}: team {t} start is on the navmesh")
        if s0 is None:
            continue
        ok = reach(ctx, ws, s0)
        print(f"      team {t}: {len(ok)} of {len(ctx.play)} play-space polys reachable past the walls")
        for lab, p in pts:
            q = ctx.poly_at(p["pos"])
            check(q is not None and q in ok, f"{key} {lab}: reachable from team {t} start without crossing a closed-off wall ({len(ws)} wall pieces)")
if skipped:
    print("skip  no navmesh seed: " + ", ".join(skipped))
print("ALL OK" if not FAILS else f"{len(FAILS)} FAILED")
sys.exit(1 if FAILS else 0)
