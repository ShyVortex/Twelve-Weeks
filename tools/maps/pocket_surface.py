"""Ground collision for the Supermarket lane / window pocket (jackson-market, x -509.8..-506, z 282.4..297): hole filler.

Why: the collision there was entirely broken (you either got stuck or fell through the map).  The removals
(pat-walls instance + wall triangles, gate fence, trash piles) take the Havok triangles under them with them: the stock ground collision of
the lane has holes (z 284..286.4 right in front of the window, slits along the wall line, threshold).  The earlier fix was a
render-following surface baked from the render snow of an earlier build plus colledits that deleted the original floor; later
Scene Editor saves (flatten / snow / wall-triangle removals) moved the snow, so the baked surface no longer matched (holes + the deleted
floor of the colledits left more holes: 71 empty cells in the final collision).

This version does not delete anything and does not depend on old heights.  It reads two build stages of the CURRENT edits:
  --base  the level-edit output WITHOUT the pocket edits (python pocket_surface.py base builds it into a scratch dir),
  --render  any stage's render paks (the morph stage holds the flattened / snowed ground),
and adds two triangles for every 0.5 m cell (plus the ring of cells around it) where the base collision has no floor or lies more than 8 cm under
the render snow, at render height + 1.5 cm.  Data -> data/fixes/openings-<key>.json "edits" entry "window pocket snow surface" (read by
openings.py -> level_edit 'add' with explicit triangles); the old colledits (original-floor deletions) are removed.

  python tools/maps/pocket_surface.py base   <key> <dir>             # edits without the pocket entries -> <dir>/out (CPU, ~5 min)
  python tools/maps/pocket_surface.py gen    <key> <dir>             # fill triangles from <dir>/out/morph -> openings json
  python tools/maps/pocket_surface.py check  <key> <out-dir> [stage]  # holes / bumps of a finished build (stage dir name: colledit, morph or '')
Re-run base + gen after a Scene Editor save that touches the lane.  Offline, CPU only.
"""
import json
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import level_edit as le  # noqa: E402

LEVELS = ("pat-jackson-supermarket", "pat-jackson-alley", "pat-jackson-supermarket-int")
REGION = (-509.8, -505.95, 282.4, 297.0)          # x0, x1, z0, z1 of the cells that may be filled
CELL = 0.5
LIFT = 0.015                                      # m above the render snow
MAX_GROUND = 18.75                                # render surfaces above this are not snow ground here (sill ramp, wall tops, props)
UNDER = 0.08                                      # collision this far under the render snow gets a surface too
NAME = "window pocket snow surface"


def is_pocket(e):
    n = e.get("name") or ""
    c = (e.get("col") or {}).get("name", "")
    return n.startswith("window pocket") or c.startswith("window pocket")


def phys_tris(dirs, box):
    """collision triangles of LEVELS inside the xz box; first existing <dir>/<level>-phys.pak of `dirs` per level"""
    out = []
    for lv in LEVELS:
        p = next((os.path.join(d, lv + "-phys.pak") for d in dirs if os.path.exists(os.path.join(d, lv + "-phys.pak"))), None)
        if not p:
            continue
        for it in le.phys_items(p)[1]:
            _, T, _ = le.hc.triangles(it.mesh)
            sel = ((T.max(1)[:, [0, 2]] >= [box[0], box[2]]) & (T.min(1)[:, [0, 2]] <= [box[1], box[3]])).all(1)
            if sel.any():
                out.append(T[sel])
    return np.concatenate(out)


def render_tris(dirs, box):
    import ndpak
    out = []
    for lv in ("pat-jackson-supermarket", "pat-jackson-alley", "pat-jackson-alley-detail", "pat-jackson-wide"):
        p = next((os.path.join(d, lv + ".pak") for d in dirs if os.path.exists(os.path.join(d, lv + ".pak"))), None)
        if not p:
            continue
        T = le.world_submeshes(ndpak.Pak(p), [box[0], -50, box[2], box[1], 80, box[3]])
        if len(T):
            sel = ((T.max(1)[:, [0, 2]] >= [box[0], box[2]]) & (T.min(1)[:, [0, 2]] <= [box[1], box[3]])).all(1) & (T[:, :, 1].min(1) > 10)
            out.append(T[sel])
    return np.concatenate(out)


class Field:
    """vertical ray tests on a triangle soup: top-most hit below `maxy` of faces whose |normal.y| >= ny (up-facing only when up)"""

    def __init__(self, T, maxy, ny=0.5, up=False):
        n = np.cross(T[:, 1] - T[:, 0], T[:, 2] - T[:, 0])
        l = np.linalg.norm(n, axis=1)
        ok = l > 1e-12
        ok &= (n[:, 1] > ny * l) if up else (np.abs(n[:, 1]) > ny * l)
        self.T = T[ok]
        self.maxy = maxy
        self.lo = self.T[:, :, [0, 2]].min(1)
        self.hi = self.T[:, :, [0, 2]].max(1)

    def top(self, x, z):
        s = (self.lo[:, 0] <= x) & (self.hi[:, 0] >= x) & (self.lo[:, 1] <= z) & (self.hi[:, 1] >= z)
        if not s.any():
            return None
        T = self.T[s]
        a, b, c = T[:, 0][:, [0, 2]], T[:, 1][:, [0, 2]], T[:, 2][:, [0, 2]]
        v0, v1, v2 = b - a, c - a, np.array([x, z]) - a
        d = v0[:, 0] * v1[:, 1] - v1[:, 0] * v0[:, 1]
        ok = np.abs(d) > 1e-12
        dd = np.where(ok, d, 1.0)
        u = (v2[:, 0] * v1[:, 1] - v1[:, 0] * v2[:, 1]) / dd
        w = (v0[:, 0] * v2[:, 1] - v2[:, 0] * v0[:, 1]) / dd
        m = ok & (u >= -1e-9) & (w >= -1e-9) & (u + w <= 1 + 1e-9)
        if not m.any():
            return None
        y = (T[:, 0, 1] + u * (T[:, 1, 1] - T[:, 0, 1]) + w * (T[:, 2, 1] - T[:, 0, 1]))[m]
        y = y[y < self.maxy]
        return float(y.max()) if len(y) else None


def fill_cells(base, ren):
    """-> (cells [(i, j)], vertex heights {(i, j): y}) of the grid over REGION that needs ground"""
    x0, x1, z0, z1 = REGION
    nx, nz = int(round((x1 - x0) / CELL)), int(round((z1 - z0) / CELL))
    need = np.zeros((nz, nx), bool)
    for i in range(nz):
        for j in range(nx):
            xs = [x0 + (j + f) * CELL for f in (0.08, 0.5, 0.92)]
            zs = [z0 + (i + f) * CELL for f in (0.08, 0.5, 0.92)]
            for x in xs:
                for z in zs:
                    r = ren.top(x, z)
                    if r is None:
                        continue
                    c = base.top(x, z)
                    if c is None or c < r - UNDER:
                        need[i, j] = True
    pad = np.pad(need, 1)                                # the ring of neighbours: a hole thinner than the sample step cannot slip through
    grow = np.zeros_like(need)
    for di in (0, 1, 2):
        for dj in (0, 1, 2):
            grow |= pad[di:di + nz, dj:dj + nx]
    H = {}
    for i in range(nz + 1):
        for j in range(nx + 1):
            if (grow[max(i - 1, 0):i + 1, max(j - 1, 0):j + 1]).any():
                x, z = x0 + j * CELL, z0 + i * CELL
                ys = [y for y in (ren.top(x + dx, z + dz) for dx in (-0.02, 0.02) for dz in (-0.02, 0.02)) if y is not None]
                if ys:
                    H[(i, j)] = float(np.mean(ys))
    # a vertex without render ground borrows the mean of its neighbours
    for k in list(set((i, j) for i in range(nz + 1) for j in range(nx + 1) if grow[max(i - 1, 0):i + 1, max(j - 1, 0):j + 1].any()) - set(H)):
        nb = [H[(k[0] + a, k[1] + b)] for a in (-1, 0, 1) for b in (-1, 0, 1) if (k[0] + a, k[1] + b) in H]
        if nb:
            H[k] = float(np.mean(nb))
    cells = [(i, j) for i in range(nz) for j in range(nx) if grow[i, j] and all(k in H for k in ((i, j), (i + 1, j), (i, j + 1), (i + 1, j + 1)))]
    return cells, H


def triangles(cells, H):
    x0, _, z0, _ = REGION
    tris = []
    for i, j in cells:
        P = lambda a, b: [round(x0 + (j + b) * CELL, 3), round(H[(i + a, j + b)] + LIFT, 3), round(z0 + (i + a) * CELL, 3)]
        p00, p01, p10, p11 = P(0, 0), P(0, 1), P(1, 0), P(1, 1)
        tris += [[p00, p10, p11], [p00, p11, p01]]                   # counter-clockwise seen from +y (see check)
    return tris


def cmd_base(key, d):
    out = os.path.join(d, "out")
    os.makedirs(out, exist_ok=True)
    src = os.path.join(d, "src")
    if not os.path.exists(src):
        os.symlink(le.CACHE + "/src", src) if os.name != "nt" else os.system('mklink /J "%s" "%s"' % (src, os.path.join(le.CACHE, "src").replace("/", "\\")))
    edits = [e for e in le.edits_for(key, {}) if not is_pocket(e)]
    le.build_edits(edits, d, out, None)


def cmd_gen(key, d):
    import openings
    base = Field(phys_tris([os.path.join(d, "out", "morph"), os.path.join(d, "out")], (REGION[0] - 1, REGION[1] + 1, REGION[2] - 1, REGION[3] + 1)), 19.3, 0.2, True)
    ren = Field(render_tris([os.path.join(d, "out", "morph"), os.path.join(d, "out")], (REGION[0] - 1, REGION[1] + 1, REGION[2] - 1, REGION[3] + 1)), MAX_GROUND, 0.5, False)
    cells, H = fill_cells(base, ren)
    tris = triangles(cells, H)
    print("cells to fill: %d (%d triangles)" % (len(cells), len(tris)))
    p = openings.path(key)
    f = json.load(open(p, encoding="utf-8"))
    for e in f["edits"]:
        if (e.get("name") or "").startswith(NAME):
            e["name"] = NAME + " (hole filler: render snow heights of the built paks + 1.5 cm where the ground collision is missing or under the snow; pocket_surface.py)"
            b = e["boxes"][0]
            b["tris"] = tris
            xs = [v[0] for t in tris for v in t]
            ys = [v[1] for t in tris for v in t]
            zs = [v[2] for t in tris for v in t]
            e["box"] = [min(xs) - 0.1, min(ys) - 0.2, min(zs) - 0.1, max(xs) + 0.1, max(ys) + 0.2, max(zs) + 0.1]
            b["center"] = [round((min(xs) + max(xs)) / 2, 3), round((min(ys) + max(ys)) / 2, 3), round((min(zs) + max(zs)) / 2, 3)]
    f["colledits"] = []                                   # the original floor stays: nothing is deleted any more
    f["_comment"] = f["_comment"] + " 11-03 night 39: the surface is now a HOLE FILLER (pocket_surface.py) and the colledits that deleted the original floor are gone (they and the user's later flatten / wall removals left holes)."
    json.dump(f, open(p, "w", encoding="utf-8", newline="\n"), indent=1)


def cmd_check(key, out, stage):
    box = (REGION[0] - 2, REGION[1] + 0.5, REGION[2] - 0.5, REGION[3] + 1)
    dirs = [os.path.join(out, stage), out] if stage else [out]
    col = Field(phys_tris(dirs, box), 19.3, 0.2, True)
    ren = Field(render_tris([os.path.join(out, "morph"), out], box), MAX_GROUND, 0.5, False)
    holes, bumps, unders, n = [], [], [], 0
    for x in np.arange(box[0] + 0.05, box[1], 0.1):
        for z in np.arange(box[2] + 0.05, box[3], 0.1):
            r = ren.top(x, z)
            if r is None:
                continue
            n += 1
            c = col.top(x, z)
            if c is None:
                holes.append((round(x, 2), round(z, 2)))
            elif c > r + 0.3 and x < -506.1:
                bumps.append((round(x, 2), round(z, 2), round(c - r, 2)))
            elif c < r - 0.12:
                unders.append((round(x, 2), round(z, 2), round(c - r, 2)))
    print("samples %d: ground holes %d, collision >30 cm over the render snow %d, collision >12 cm under it %d" % (n, len(holes), len(bumps), len(unders)))
    for h in holes[:40]:
        print("  hole", h)
    return len(holes)


if __name__ == "__main__":
    a = sys.argv[1:]
    if len(a) >= 3 and a[0] == "base":
        cmd_base(a[1], a[2])
    elif len(a) >= 3 and a[0] == "gen":
        cmd_gen(a[1], a[2])
    elif len(a) >= 3 and a[0] == "check":
        sys.exit(1 if cmd_check(a[1], a[2], a[3] if len(a) > 3 else "") else 0)
    else:
        print(__doc__)
