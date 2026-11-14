"""Generated respawn points: a player respawned constantly in one spot, so every playable area gets many more spawns
(even ~15 spawn points in one zone).

  python tools/maps/respawn_fill.py gen   <key>... | pool [--write]   candidates on the real collision -> data/<key>-respawns-gen.json
  python tools/maps/respawn_fill.py check <key>... | pool             re-measure every generated (and user) respawn; exit 1 on a failing generated one
  python tools/maps/respawn_fill.py plot  <key>... | pool             top-down PNG -> re/maps/spawns-1104/<key>.png (user vs generated)
  (gen --write runs check + plot too; then `python tools/maps/sp_maps.py pak <key>` puts them into the ingame pak)

The hand-placed respawns (data/<key>-spawns.json "respawns", imported from their Scene Editor saves) are NEVER touched: they stay
to1-spawn-point-1..n. The generated points live in their own file, data/<key>-respawns-gen.json, and the pak build appends them as
to1-spawn-point-<n+1..> (sp_maps.py pak). editor_import.py recognises them in a saved pak by position: untouched ones stay generated, a moved one
becomes the user's, a deleted one leaves the generated list.

Where a point may go (collision = reach_check: every level's Havok triangles with the level edits applied + the props as boxes):
  - a stand-mode floor cell (reach_check flood, 0.5 m cells, step 0.55 m, no climbing) reachable from the team starts or the user's
    respawns / boxes, and reachable from the team starts in prone mode (see Map.__init__)
  - inside the spec's play `bounds` (1 m margin); jackson-market: inside one of loot_place's room clusters
  - the 3 x 3 cells around it reachable at the same height (+-0.2 m): no ledge, stair edge or drop beside it
  - clearance: a 0.7 m radius column from 0.3 to 1.8 m above the floor holds no collision (the ext's spawn check casts 0.6 m side rays)
  - not a pocket: >= 5 of 16 directions free for 4 m at 1.2 m height
  - >= 12 m from every team-start spawn (2013: respawns never inside a start group), >= 3 m from supply boxes, >= 2.5 m from every
    other respawn (user or generated). (Interrogation lockboxes: the ext skips spawners within 10 m of the two live safes at runtime.)
Per zone (room cluster; other maps: k-means zones of ~250 m2 walkable) up to ZONE_N points by farthest-point sampling (even coverage); the
map total (user + generated) is capped at TOTAL_MAX (the ext's SPN_MAX is 192; its ray tester budget is sized for ~160).
Facing: the longest free run of 16 directions at 1.4 m (cap 20 m), leaning to the zone's centre: into the room, not at a wall.
y = the floor under the point + 0.02 (as reach_check --fix does).
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
import reach_check as rc  # noqa: E402

DATA = os.path.join(HERE, "data")
OUT_PNG = os.path.join(ROOT, "re", "maps", "spawns-1104")
POOL = ["jackson-market", "train-station", "wilds-houses", "capitol-shops", "into-the-city", "overpass", "chase", "p1-bookstore"]

ZONE_N = 15
TOTAL_MAX = 160
GAP = 2.5            # m between two respawns
BOX_GAP = 3.0
INTRO_GAP = 12.0
LOCKBOX_GAP = 10.0
CLEAR_R = 0.7
CLEAR_LO, CLEAR_HI = 0.3, 1.8
FLAT_DY = 0.2
OPEN_MIN, OPEN_LEN = 5, 4.0
ZONE_AREA = 250.0
BOUND_MARGIN = 1.0


def yaw_quat(yaw):
    return [0.0, round(math.sin(yaw / 2), 6), 0.0, round(math.cos(yaw / 2), 6)]


def gen_path(key):
    return os.path.join(DATA, f"{key}-respawns-gen.json")


def load_gen(key):
    p = gen_path(key)
    return json.load(open(p)) if os.path.exists(p) else None


class Map:
    """collision world + stand flood of one map (reach_check), built once (~1 min)"""

    def __init__(self, key):
        import loot_place as LP
        self.key = key
        self.m = rc.spec(key)
        b = self.m.get("bounds")
        self.sp = json.load(open(os.path.join(DATA, f"{key}-spawns.json")))
        if not b:                      # no play bounds in the spec: the box around every spawn of the map + 10 m
            P = [p["pos"] for k in ("intro0", "intro1", "respawns", "boxes") for p in self.sp.get(k, [])]
            b = [min(p[0] for p in P) - 10, max(p[0] for p in P) + 10, min(p[2] for p in P) - 10, max(p[2] for p in P) + 10]
            self.bounds_note = "no spec bounds: the spawns' box + 10 m"
        else:
            self.bounds_note = "spec bounds"
        self.bounds = b
        box = [b[0] - 18, b[1] + 18, b[2] - 18, b[3] + 18]
        T, used = rc.level_tris(key, box)
        P, unknown = rc.prop_tris(self.m.get("props", []))
        self.unknown_props = sorted(set(unknown))
        T = np.concatenate([T, P]) if len(P) else T
        self.w = rc.World(T, box)
        self.g = LP.TriGrid(T)
        self.seeds = [tuple(p) for p in self.m.get("reach_seeds", [])] or [tuple(p["pos"]) for p in self.sp["intro0"] + self.sp["intro1"]]
        # Stand mode (0.4..1.75 m column clear, step 0.55 m, no climbing) under-estimates: foliage / tall-grass collision and low sills cut it
        # (Wilds Houses: the whole middle yard, 9 of the 12 hand-placed respawns, unreachable from the starts). So: stand-mode floor reachable from the
        # starts OR from the user's own respawns / supply boxes (known play spots), AND reachable from the starts in prone mode (over-estimate:
        # 0.45..0.85 m column, climbs to 1.6 m) - connected to the starts, no closed-off pocket.
        st = self.w.flood(self.seeds, rc.MODES["stand"])
        known = [tuple(p["pos"]) for p in self.sp["respawns"] + self.sp["boxes"]]
        r = dict(st)
        r.update(self.w.flood(self.seeds + known, rc.MODES["stand"]))
        pr = {(i, j) for (i, j, _) in self.w.flood(self.seeds, rc.MODES["prone"])}
        self.stand, self.stand_strict = {}, {}
        for (i, j, _), h in r.items():
            if (i, j) in pr:
                self.stand.setdefault((i, j), []).append(h)
        for (i, j, _), h in st.items():
            self.stand_strict.setdefault((i, j), []).append(h)
        self.area = len(self.stand) * rc.CELL * rc.CELL
        print(f"{key}: {len(T)} collision triangles, {len(self.stand)} stand-reachable cells ({self.area:.0f} m2), bounds {b} ({self.bounds_note})"
              + (f", props without bounds: {self.unknown_props}" if self.unknown_props else ""))

    def floor_at(self, x, y, z, tol=0.3):
        i, j = int((x - self.w.x0) // rc.CELL), int((z - self.w.z0) // rc.CELL)
        fl = [h for h in self.w.floor_list(i, j) if -0.05 - tol <= y - h <= tol]
        return min(fl, key=lambda h: abs(y - h)) if fl else None

    def reachable(self, x, h, z, strict=False):
        i, j = int((x - self.w.x0) // rc.CELL), int((z - self.w.z0) // rc.CELL)
        return any(abs(q - h) < 0.6 for q in (self.stand_strict if strict else self.stand).get((i, j), []))

    def inb(self, x, z, m=BOUND_MARGIN):
        b = self.bounds
        return b[0] + m <= x <= b[1] - m and b[2] + m <= z <= b[3] - m

    def free_dirs(self, x, h, z, length, n=16, y=1.2):
        out = []
        for k in range(n):
            a = 2 * math.pi * k / n
            t = self.g.seg_t((x, h + y, z), (x + math.sin(a) * length, h + y, z + math.cos(a) * length), 0.02)
            out.append(length if t is None else t)
        return out


def zones_of(M, cells):
    """[(name, member mask)] - jackson-market: loot_place's room clusters; else k-means zones of ~ZONE_AREA m2"""
    import loot_place as LP
    xz = np.array([[c[0], c[2]] for c in cells]) if cells else np.zeros((0, 2))
    if M.key in LP.MAPS and LP.MAPS[M.key].get("rooms"):
        out = []
        taken = np.zeros(len(cells), bool)
        for name, (x0, x1, z0, z1) in LP.MAPS[M.key]["rooms"]:
            m = ~taken & (xz[:, 0] >= x0) & (xz[:, 0] <= x1) & (xz[:, 1] >= z0) & (xz[:, 1] <= z1)
            taken |= m
            out.append((name, m))
        return out
    k = int(np.clip(round(M.area / ZONE_AREA), 3, 10))
    rng = np.random.default_rng(7)
    C = xz[rng.choice(len(xz), k, replace=False)] if len(xz) >= k else xz
    for _ in range(40):
        lab = np.argmin(((xz[:, None, :] - C[None]) ** 2).sum(2), 1)
        C = np.array([xz[lab == i].mean(0) if (lab == i).any() else C[i] for i in range(len(C))])
    lab = np.argmin(((xz[:, None, :] - C[None]) ** 2).sum(2), 1)
    order = np.lexsort((C[:, 0], C[:, 1]))
    return [(f"zone {n + 1} ({C[i][0]:.0f} {C[i][1]:.0f})", lab == i) for n, i in enumerate(order)]


def lockbox_points(key):
    p = os.path.join(DATA, f"{key}-lockboxes.json")
    if not os.path.exists(p):
        return []
    d = json.load(open(p))
    return [c["pos"] for t in d.get("teams", []) for c in t]


def candidates(M):
    """every cell centre that passes the per-spot rules (not the spacing ones) -> [(x, h, z)]"""
    intros = [p["pos"] for p in M.sp["intro0"] + M.sp["intro1"]]
    boxes = [p["pos"] for p in M.sp["boxes"]]
    out = []
    cnt = {"cells": 0, "bounds": 0, "start": 0, "box": 0, "flat": 0, "clear": 0}
    for (i, j), hs in M.stand.items():
        x, z = M.w.cell_xz(i, j)
        for h in hs:
            cnt["cells"] += 1
            if not M.inb(x, z):
                cnt["bounds"] += 1
                continue
            if any(math.dist((x, z), (p[0], p[2])) < INTRO_GAP for p in intros):
                cnt["start"] += 1
                continue
            if any(math.dist((x, z), (p[0], p[2])) < BOX_GAP for p in boxes):
                cnt["box"] += 1
                continue
            flat = True
            for di in (-1, 0, 1):
                for dj in (-1, 0, 1):
                    if not any(abs(q - h) <= FLAT_DY for q in M.stand.get((i + di, j + dj), [])):
                        flat = False
            if not flat:
                cnt["flat"] += 1
                continue
            if not M.w.clear(x - CLEAR_R, h + CLEAR_LO, z - CLEAR_R, x + CLEAR_R, h + CLEAR_HI, z + CLEAR_R):
                cnt["clear"] += 1
                continue
            out.append((x, h, z))
    print(f"   candidate cells: {len(out)} of {cnt['cells']} (dropped: outside bounds {cnt['bounds']}, near a start {cnt['start']}, "
          f"near a box {cnt['box']}, not flat {cnt['flat']}, no clearance {cnt['clear']})")
    return out


def facing(M, x, h, z, cx, cz):
    runs = M.free_dirs(x, h, z, 20.0, 16, 1.4)
    to_c = math.atan2(cx - x, cz - z)
    best, by = -1e9, 0.0
    for k, r in enumerate(runs):
        a = 2 * math.pi * k / 16
        s = r + 4.0 * math.cos(a - to_c)
        if s > best:
            best, by = s, a
    return by


def generate(M):
    user = [p["pos"] for p in M.sp["respawns"]]
    cand = candidates(M)
    zs = zones_of(M, cand)
    room = TOTAL_MAX - len(user)
    pts = []
    taken = [tuple(u) for u in user]
    stats = []
    open_fail = 0
    C = np.array(cand) if cand else np.zeros((0, 3))
    for name, mask in zs:
        idx = np.nonzero(mask)[0]
        if not len(idx):
            stats.append((name, 0, 0, 0))
            continue
        zc = C[idx]
        cx, cz = float(zc[:, 0].mean()), float(zc[:, 2].mean())
        nu = sum(1 for u in user if any(math.dist((u[0], u[2]), (c[0], c[2])) < 0.75 for c in zc))
        want = min(ZONE_N, room - len(pts))             # the GAP spacing decides how many a small zone holds
        dmin = np.full(len(idx), 1e9)
        for t in taken:
            dmin = np.minimum(dmin, np.hypot(zc[:, 0] - t[0], zc[:, 2] - t[2]) + np.where(np.abs(zc[:, 1] - t[1]) > 2.5, 1e3, 0.0))
        alive = np.ones(len(idx), bool)
        got = 0
        while got < want:
            sc = np.where(alive & (dmin >= GAP), dmin, -1.0)
            k = int(np.argmax(sc))
            if sc[k] < 0:
                break
            x, h, z = map(float, zc[k])
            alive[k] = False
            if sum(1 for r in M.free_dirs(x, h, z, OPEN_LEN) if r >= OPEN_LEN - 0.05) < OPEN_MIN:
                open_fail += 1
                continue
            yaw = facing(M, x, h, z, cx, cz)
            p = {"pos": [round(x, 3), round(h + 0.02, 3), round(z, 3)], "quat": yaw_quat(yaw), "zone": name}
            pts.append(p)
            taken.append(tuple(p["pos"]))
            dmin = np.minimum(dmin, np.hypot(zc[:, 0] - x, zc[:, 2] - z) + np.where(np.abs(zc[:, 1] - h) > 2.5, 1e3, 0.0))
            got += 1
        stats.append((name, len(idx), nu, got))
    for name, n, nu, got in stats:
        print(f"   {name:<34} {n * 0.25:7.0f} m2 candidate floor, user respawns {nu:2d}, generated {got:2d}")
    print(f"   {len(pts)} generated ({open_fail} rejected as pockets), user {len(user)}, total {len(pts) + len(user)}")
    return pts, stats


def check(M, gen):
    """-> (n_fail generated, lines). floor ray within 0.3 m, capsule (r 0.45, 0.4..1.75) clear, reachable on foot from the team starts"""
    lines, bad = [], 0
    rows = [("R%d" % (i + 1), "user", p) for i, p in enumerate(M.sp["respawns"])] + \
           [("R%d" % (len(M.sp["respawns"]) + i + 1), "gen", p) for i, p in enumerate(gen)]
    for lab, kind, p in rows:
        x, y, z = p["pos"]
        fy, _ = M.g.ray_down(x, z, y + 0.25, 0.55)          # downward ray from 0.25 m above: the first hit must be within 0.3 m under the point
        probs = []
        if fy is None or y - fy > 0.3 or y - fy < -0.25:
            probs.append("no floor within 0.3 m under it (ray hit %s)" % (None if fy is None else round(fy, 2)))
            fy = y
        if not rc.capsule_clear(M.w, x, fy, z):
            probs.append("capsule touches collision")
        if not M.reachable(x, fy, z):
            probs.append("not reachable from the team starts (stand mode from starts / own respawns / boxes AND prone mode from the starts)")
        elif kind == "gen" and not M.reachable(x, fy, z, strict=True):
            M.n_loose = getattr(M, "n_loose", 0) + 1
        if kind == "gen":
            bad += bool(probs)
        lines.append((lab, kind, p, probs))
    return bad, lines


def plot(M, gen, png, lines=None):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    w = M.w
    img = np.full((w.nz, w.nx, 3), 1.0)
    for (i, j) in M.stand:
        img[j, i] = (0.80, 0.90, 0.80)
    fig, ax = plt.subplots(figsize=(13, max(6, 13 * w.nz / w.nx)))
    ax.imshow(img, extent=(w.x0, w.x0 + w.nx * rc.CELL, w.z0 + w.nz * rc.CELL, w.z0), interpolation="nearest")
    b = M.bounds
    ax.add_patch(plt.Rectangle((b[0], b[2]), b[1] - b[0], b[3] - b[2], fill=False, ec="0.4", lw=1, ls="--"))
    bad = {lab for lab, _, _, pr in (lines or []) if pr}
    for p in gen:
        x, z = p["pos"][0], p["pos"][2]
        yaw = 2 * math.atan2(p["quat"][1], p["quat"][3])
        ax.plot([x, x + 0.9 * math.sin(yaw)], [z, z + 0.9 * math.cos(yaw)], "-", c="#c06000", lw=0.8)
        ax.plot(x, z, "o", ms=4, c="#ff9a2e", mec="#7a3c00", mew=0.5)
    n0 = len(M.sp["respawns"])
    for i, p in enumerate(M.sp["respawns"]):
        x, z = p["pos"][0], p["pos"][2]
        ax.plot(x, z, "s", ms=7, c="#1f6fd1", mec="k", mew=0.7)
        ax.text(x + 0.5, z - 0.5, "R%d" % (i + 1), fontsize=7, color="#0b3a75")
    for k, c in (("intro0", "#2040ff"), ("intro1", "#e02020")):
        for p in M.sp[k]:
            ax.plot(p["pos"][0], p["pos"][2], "^", ms=8, c=c, mec="k")
    for p in M.sp["boxes"]:
        ax.plot(p["pos"][0], p["pos"][2], "D", ms=6, c="#e8d000", mec="k")
    for lab in bad:
        i = int(lab[1:]) - 1
        p = M.sp["respawns"][i] if i < n0 else gen[i - n0]
        ax.plot(p["pos"][0], p["pos"][2], "x", ms=10, c="r", mew=2)
    ax.set_title(f"{M.key}: user respawns (blue squares, R1-R{n0}) {n0}, generated (orange) {len(gen)}; starts = triangles, "
                 f"boxes = yellow; red x = fails floor / capsule / reach check", fontsize=9)
    ax.grid(True, alpha=0.25)
    os.makedirs(os.path.dirname(png), exist_ok=True)
    plt.savefig(png, dpi=80, bbox_inches="tight")
    plt.close(fig)


def run(key, mode, write):
    M = Map(key)
    if mode == "gen":
        pts, stats = generate(M)
        doc = {"_note": "GENERATED by tools/maps/respawn_fill.py gen (many more respawn points per zone). NOT the user's respawns: those "
                        "are data/<key>-spawns.json 'respawns' (R1..R%d). The pak build appends these as to1-spawn-point-%d.. ; editor_import "
                        "keeps untouched ones here, a moved one becomes the user's, a deleted one leaves this list." % (len(M.sp["respawns"]), len(M.sp["respawns"]) + 1),
               "key": key, "user_respawns": len(M.sp["respawns"]),
               "rules": {"zone_n": ZONE_N, "total_max": TOTAL_MAX, "gap": GAP, "box_gap": BOX_GAP, "intro_gap": INTRO_GAP, "lockbox_gap": LOCKBOX_GAP,
                         "clear_r": CLEAR_R, "flat_dy": FLAT_DY, "open": [OPEN_MIN, OPEN_LEN], "bounds": M.bounds},
               "zones": [{"name": n, "floor_m2": round(c * 0.25), "user": u, "generated": g} for n, c, u, g in stats],
               "respawns": pts}
        gen = pts
        if write:
            with open(gen_path(key), "w", newline="\n") as f:
                json.dump(doc, f, indent=1)
            print("   wrote", os.path.relpath(gen_path(key), ROOT))
    else:
        d = load_gen(key)
        gen = d["respawns"] if d else []
    bad, lines = check(M, gen)
    for lab, kind, p, probs in lines:
        if probs:
            print(f"   {'USER (kept as placed)' if kind == 'user' else 'GENERATED FAIL'} {lab} {p['pos']}: {'; '.join(probs)}")
    print(f"   check: {len(gen) - bad} of {len(gen)} generated pass (floor ray <= 0.3 m, capsule clear, reachable from the starts); "
          f"user respawns flagged {sum(1 for l in lines if l[1] == 'user' and l[3])} of {len(M.sp['respawns'])} (not changed); "
          f"{getattr(M, 'n_loose', 0)} generated lie on floor the strict stand walk from the starts does not reach (foliage / sills)")
    if mode in ("plot", "gen") and (mode == "plot" or write):
        png = os.path.join(OUT_PNG, f"{key}.png")
        plot(M, gen, png, lines)
        print("   plot", os.path.relpath(png, ROOT))
    return bad


def main():
    a = sys.argv[1:]
    if len(a) < 2 or a[0] not in ("gen", "check", "plot"):
        print(__doc__)
        return 0
    keys = POOL if a[1] == "pool" else [k for k in a[1:] if not k.startswith("--")]
    bad = 0
    for k in keys:
        try:
            bad += run(k, a[0], "--write" in a)
        except (SystemExit, Exception) as e:          # a map whose collision cannot be read (Part I levels ...): reported, the others go on
            print(f"{k}: SKIPPED ({type(e).__name__}: {e})")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
