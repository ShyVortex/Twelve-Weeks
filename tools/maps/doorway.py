"""Open a baked SP doorway in the collision: remove whatever stands in the opening and re-close the wall around it.

SP buildings of the Jackson patrol levels have SIMPLIFIED wall collision: a doorway is not a hole, the wall is one flat quad (2
triangles, up to 20 m long, tag 193 / 705 ...) that also covers the door, with a second thin "glass / door" plane in front of it, and
the door leaf itself is a baked render prop with its own few collision boxes.  Hiding the leaf (level_edit remove) is therefore not
enough.  This tool probes the clearance volume of an opening on the real (stock) collision, picks every triangle that touches it,
groups the wall quads by plane, and writes two level_edit edits per opening:

  1. "remove" with explicit shape keys (collision.keys = {phys item: [keys]}): the quads + the door boxes,
  2. "add": solid boxes (0.3 m) that give the wall back on both sides of the opening and over the lintel (the old quad's extent minus
     the opening); the material is copied from the nearest plain wall triangle (level_edit add_box_plan).

  python doorway.py plan <map key> <name> <level> <axis> <cx> <cz> [--hw 0.7] [--y0 17.9] [--h 2.15] [--levels a,b,c] [--write]
        axis x = the wall runs along x (door passes along z); z = the wall runs along z.  (cx, cz) = centre of the opening on the wall.
        --levels: the levels whose collision is probed (default: the one given); the edits are written for each level that has hits.
        --write: append the edits to sp_maps.json (maps[key].edits, replacing edits of the same name).
Offline, CPU only.
"""
import json
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import level_edit as le  # noqa: E402
import reach_check as rc  # noqa: E402

PROBE_PAD = 0.9          # clearance volume half depth across the wall (m)
THICK = 0.3
ALONG = [(-1e9, 1e9)]


def stock_phys(lv):
    return le.fetch(lv, os.path.join(le.CACHE, "src"), None, ("-phys",))["-phys"]


def probe(lv, axis, cx, cz, hw, y0, h):
    """-> list of hits {item, key, tag, T (3x3), n} for every triangle touching the opening's clearance volume (stock collision)"""
    lo = [cx - hw, y0 + 0.45, cz - PROBE_PAD]
    hi = [cx + hw, y0 + h, cz + PROBE_PAD]
    if axis == "z":
        lo = [cx - PROBE_PAD, y0 + 0.45, cz - hw]
        hi = [cx + PROBE_PAD, y0 + h, cz + hw]
    out = []
    items = le.phys_items(stock_phys(lv))[1]
    for k, it in enumerate(items):
        keys, T, tg = le.hc.triangles(it.mesh)
        if not len(T):
            continue
        sel = ((T.max(1) >= lo) & (T.min(1) <= hi)).all(1)
        if not sel.any():
            continue
        ov = le.tri_box_overlap(T[sel], lo, hi)
        for kk, t, g in zip(keys[sel][ov], T[sel][ov], tg[sel][ov]):
            out.append({"item": k, "key": int(kk), "tag": int(g), "T": t})
    return out, items


def quad_group(items, hit, axis):
    """the triangles of the same item on the same plane (+-0.02 m), tag and touching extent as `hit` (the other half of a wall quad)"""
    k = hit["item"]
    keys, T, tg = le.hc.triangles(items[k].mesh)
    pa = 2 if axis == "x" else 0                      # coordinate across the wall
    t0 = hit["T"]
    pc = t0[:, pa].mean()
    sel = (np.abs(T[:, :, pa] - pc).max(1) < 0.02) & (tg == hit["tag"])
    lo, hi = t0.min(0), t0.max(0)
    ext = (T.max(1) >= lo - 0.02).all(1) & (T.min(1) <= hi + 0.02).all(1)
    sel &= ext
    ks = [int(x) for x in keys[sel]]
    if hit["key"] not in ks:
        ks.append(hit["key"])
        return ks, np.concatenate([T[sel], t0[None]]) if sel.any() else t0[None]
    return ks, T[sel]


def find_host(levels, parts, axis, plane, strict=True):
    """-> (level, top y limit, bottom y limit, plane, needs_room) of the first level with a phys item that can take new triangles for these wall
    pieces (level_edit.add_box_plan conditions: the pieces inside the mesh domain, a free section slot, key-table room, and - strict - a tagfile
    page that can grow; non-strict skips the page test: the edit then carries a dummy "room" and the write relies on the triangles the same
    edit removes from the item), else (None, None, None, None, False)"""
    for lv in levels:
        items = le.phys_items(stock_phys(lv))[1]
        for it in items:
            m = it.mesh
            dmin, dmax = m.domain()
            if len(m.sections) + 1 >= 1 << (m.keybits - 8) or len(it.blob) * 8 < 3 * (1 << m.keybits):
                continue
            grow = True
            try:
                le._grow_tag_page(None, it.pak, it, it.tsz + 100000)
            except ValueError:
                grow = False
            if strict and not grow:
                continue
            ytop = float(dmax[1]) - 0.1
            ybot = float(dmin[1]) + 0.05
            pc = 2 if axis == "x" else 0
            plane_c = min(max(plane, float(dmin[pc]) + THICK / 2 + 0.02), float(dmax[pc]) - THICK / 2 - 0.02)
            if abs(plane_c - plane) > 0.3:
                continue
            ok = True
            la_ = 0 if axis == "x" else 2
            for nm, p0, p1, y_lo, y_hi in parts:
                y_lo = max(y_lo, ybot)
                if p0 < float(dmin[la_]) + 0.02 and float(dmin[la_]) + 0.02 - p0 > 0.8:
                    ok = False
                if p1 > float(dmax[la_]) - 0.02 and p1 - (float(dmax[la_]) - 0.02) > 0.8:
                    ok = False
                p0 = max(p0, float(dmin[la_]) + 0.02)
                p1 = min(p1, float(dmax[la_]) - 0.02)
                lo = [p0, y_lo, plane_c - THICK / 2] if axis == "x" else [plane_c - THICK / 2, y_lo, p0]
                hi = [p1, min(y_hi, ytop), plane_c + THICK / 2] if axis == "x" else [plane_c + THICK / 2, min(y_hi, ytop), p1]
                if (np.array(lo) < dmin).any() or (np.array(hi) > dmax).any():
                    ok = False
            if ok:
                ALONG[0] = (float(dmin[la_]) + 0.02, float(dmax[la_]) - 0.02)
                return lv, ytop, ybot, plane_c, not grow
    return None, None, None, None, False


def plan(key, name, lv, axis, cx, cz, hw, y0, h, levels, pad=None, room=None):
    global PROBE_PAD
    if pad:
        PROBE_PAD = pad
    pa = 2 if axis == "x" else 0                      # across the wall
    la = 0 if axis == "x" else 2                      # along the wall
    removes, walls = {}, []                           # removes[level][item] = keys ; walls = [(level, plane, a0, a1, bot, top)]
    for plv in levels:
        hits, items = probe(plv, axis, cx, cz, hw, y0, h)
        taken = set()
        npieces = 0
        for hit in hits:
            if (hit["item"], hit["key"]) in taken:
                continue
            t = hit["T"]
            n = np.cross(t[1] - t[0], t[2] - t[0])
            if n[1] / (np.linalg.norm(n) + 1e-12) > 0.5 and (0.5 * np.linalg.norm(n) > 0.8 or t[:, 1].max() < y0 + 0.35):
                continue                                 # a floor / ramp / roof surface of real size, or any walkable surface below 0.35 m (sills, snow, curbs): never part of the opening
            wallish = abs(n[pa]) / (np.linalg.norm(n) + 1e-12) > 0.9
            ks, TT = quad_group(items, hit, axis) if wallish else ([hit["key"]], t[None])
            for kk in ks:
                taken.add((hit["item"], kk))
            removes.setdefault(plv, {}).setdefault(str(hit["item"]), set()).update(ks)
            lo, hi = TT.reshape(-1, 3).min(0), TT.reshape(-1, 3).max(0)
            if wallish and (hi[la] - lo[la]) > 2 * hw:
                walls.append((plv, float(TT[:, :, pa].mean()), float(lo[la]), float(hi[la]), float(lo[1]), float(hi[1])))
            else:
                npieces += 1
        print("  [%s] %d triangles in the clearance volume, %d wall quads (>= %.1f m), %d pieces" % (
            plv, len(hits), sum(1 for w in walls if w[0] == plv), 2 * hw, npieces))
    edits = []
    boxes = []
    if walls:
        # one solid layer per opening: the union of the wall quads' extents (planes within 0.6 m = the same wall)
        pl = sum(w[1] for w in walls) / len(walls)
        grp = [w for w in walls if abs(w[1] - pl) < 0.6]
        plane = float(np.mean([w[1] for w in grp]))
        a0, a1 = min(w[2] for w in grp), max(w[3] for w in grp)
        bot, top = min(w[4] for w in grp), max(w[5] for w in grp)
        lintel_y = y0 + h
        ca = cx if axis == "x" else cz
        host = None
        parts = []
        if ca - hw - a0 > 0.15:
            parts.append(("left", a0, ca - hw, bot, top))
        if a1 - (ca + hw) > 0.15:
            parts.append(("right", ca + hw, a1, bot, top))
        if top - lintel_y > 0.15:
            parts.append(("lintel", ca - hw, ca + hw, lintel_y, top))
        pp_ = [(nm, p0, p1, y_lo, y_hi) for nm, p0, p1, y_lo, y_hi in parts]
        host, ymax, ymin, plane2, need_room = find_host(levels, pp_, axis, plane)
        if host is None:
            host, ymax, ymin, plane2, need_room = find_host(levels, pp_, axis, plane, strict=False)
        if host is None:
            print("  NO level / phys item can take the wall boxes (free section + key room, the box inside the mesh domain)")
            host, ymax, ymin, plane2, need_room = levels[0], top, bot, plane, False
            parts = []
        plane = plane2
        parts = [(nm, max(p0, ALONG[0][0]), min(p1, ALONG[0][1]), y_lo, y_hi) for nm, p0, p1, y_lo, y_hi in parts]
        parts = [(nm, p0, p1, max(y_lo, ymin), min(y_hi, ymax)) for nm, p0, p1, y_lo, y_hi in parts]
        parts = [pp for pp in parts if pp[4] - pp[3] > 0.15]
        for nm, p0, p1, y_lo, y_hi in parts:
            ctr = [0, (y_lo + y_hi) / 2, 0]
            ctr[la] = (p0 + p1) / 2
            ctr[pa] = plane
            boxes.append({"name": "%s %s wall" % (name, nm), "center": [round(v, 3) for v in ctr],
                          "size": [round(p1 - p0, 3), round(y_hi - y_lo, 3), THICK], "yaw": 0 if axis == "x" else 90,
                          "like": [round(v, 3) for v in ctr]})
        print("  wall layer plane %.2f along %.2f..%.2f y %.2f..%.2f (host level %s%s): %d boxes" % (plane, a0, a1, bot, top, host, ", room trick" if need_room else "", len(boxes)))
    for plv, rem in removes.items():
        rem = {k: sorted(v) for k, v in rem.items()}
        box = [cx - hw - 0.1, y0 + 0.4, cz - PROBE_PAD, cx + hw + 0.1, y0 + h, cz + PROBE_PAD] if axis == "x" else               [cx - PROBE_PAD, y0 + 0.4, cz - hw - 0.1, cx + PROBE_PAD, y0 + h, cz + hw + 0.1]
        edits.append({"name": "doorway %s: opening cleared (%s)" % (name, plv), "level": plv, "action": "remove", "box": box,
                      "render": False, "collision": {"keys": rem}})
    if boxes:
        ea = {"name": "doorway %s: wall re-closed around the opening (%s)" % (name, host), "level": host, "action": "add",
              "box": [cx - 25, y0 - 2, cz - 25, cx + 25, y0 + 12, cz + 25], "render": False, "collision": {}, "like_max": 30.0, "boxes": boxes}
        if need_room:
            ea["room"] = room or [[1.0e6, 0.0, 1.0e6, 1.0e6 + 1, 1.0, 1.0e6 + 1]]       # --room box (triangles fully inside it are dropped to pay for the new ones) or a dummy: the edit's own removals pay
        edits.append(ea)
    return edits


def main():
    a = sys.argv[1:]
    if len(a) < 7 or a[0] != "plan":
        print(__doc__)
        return
    key, name, lv, axis, cx, cz = a[1], a[2], a[3], a[4], float(a[5]), float(a[6])
    opt = {"--hw": 0.7, "--y0": 17.9, "--h": 2.15, "--pad": 0.5}
    levels = [lv]
    write = False
    room = None
    i = 7
    while i < len(a):
        if a[i] == "--write":
            write = True
        elif a[i] == "--levels":
            i += 1
            levels = a[i].split(",")
        elif a[i] == "--room":
            i += 1
            room = [[float(v) for v in a[i].split(",")]]
        elif a[i] in opt:
            i += 1
            opt[a[i - 1]] = float(a[i])
        i += 1
    ed = plan(key, name, lv, axis, cx, cz, opt["--hw"], opt["--y0"], opt["--h"], levels, opt["--pad"], room)
    for e in ed:
        print("  " + e["name"], e["action"], sum(len(v) for v in e["collision"].get("keys", {}).values()) if e["action"] == "remove" else len(e["boxes"]))
    if write and ed:
        p = le.SPEC
        d = json.load(open(p, encoding="utf-8"))
        m = next(x for x in d["maps"] if x["key"] == key)
        m["edits"] = [e for e in m.get("edits", []) if not e["name"].startswith("doorway %s:" % name)] + ed
        open(p, "w", encoding="utf-8", newline="").write(json.dumps(d, indent=1).replace("\n", "\r\n") + "\r\n")
        print("written", len(ed), "edits")


if __name__ == "__main__":
    main()
