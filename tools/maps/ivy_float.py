"""Floating ivy on SP-ported maps: find it, and turn in-game picks into level edits.  Offline (CPU only).
Notes: re/maps/ivy-float.md.   Uses level_edit.py (render placements, collision, the edit pipeline).

  python tools/maps/ivy_float.py scan  <map key> [--write] [--json=FILE]
        every ivy / foliage item of the levels the map loads: ivy, vine, leaf-kit, branch, bush ... placements (whole), and the
        ivy cards of merged level-section meshes (per connected piece).  Support = everything else drawn (after the map's other
        edits: a hidden gate holds nothing) + the collision of the loaded levels.  An item floats when no support is within GAP
        (0.25 m) of ANY of its vertices (it touches nothing), or when it is a flat ivy sheet that no wall / ledge / ground
        touches (verdict(): stands 0.25 m+ in front of its wall, among bushes or in an opening).  Far LOD tree cards are
        listed, never removed.  Floating items are re-tested with the SP levels of that
        section the map does not load (the root cause, if one of them holds it).  --write puts them into sp_maps.json maps[key].edits as "auto": "ivy-float"
        entries (re-running replaces those; hand picks and hand edits stay).
  python tools/maps/ivy_float.py picks <map key> <t2r-ivy-picks.txt> [--write]
        in-game picks (t2r-ext: t2r-ivy-pick.txt next to the exe, aim, press the pick key) -> the ivy / foliage item the camera ray
        goes through first before its world hit -> "auto": "ivy-pick" remove edits (added to the earlier picks).
  python tools/maps/ivy_float.py list  <map key>
  python tools/maps/ivy_float.py drop  <map key> <offset|name substring>...     take ivy edits out again
Previews by eye: tools/maps/ivy_preview.py.
"""
import json
import os
import re
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import level_edit as le  # noqa: E402
import ndpak  # noqa: E402

IVY = re.compile(r"ivy|vine|creeper|kit-leaf|wall-root|strand")                           # placement prototypes that are ivy
IVY_SUB = re.compile(r"\|[^|]*(ivy|vine|creeper)[^|]*\|", re.I)                            # ivy cards inside merged meshes
FOLIAGE = re.compile(r"ivy|vine|creeper|leaf|leaves|grass|bush|tree|plant|palm|olive|agave|weed|shrub|cactus|fern|twig|canopy|"
                     r"flower|branch|sapling|foliage|moss", re.I)
NEAR = 0.30            # m: a vertex this close to support counts as attached
PAD = 1.0              # m: support search margin around an item
MAXV = 600             # vertices sampled per item
MINTRI = 4             # merged ivy pieces smaller than this are ignored
GAP = 0.25             # m: an item floats when nothing drawn (and no collision) is this close to ANY of its vertices
SHEET_GAP = 0.25       # m: a flat ivy sheet floats when its median vertex is this far from a hard surface ...
SHEET_TOUCH = 0.05     # ... and less than this share of its vertices is within 0.15 m of one
FLAT = re.compile(r"creeper|hanging-flat|growing|wall-root|wall-clumps|strand")
BACKDROP = re.compile(r"^wide-|treecards|tree-cards|mad-mid-trees")   # far LOD tree cards: free by design (backdrop), never removed

# SP levels of the same section that the MP map does not load: used only to name the root cause
SP_EXTRA = {
    "wilds-houses": ["san-infected-wilds-overlook", "san-infected-wilds-overlook-slope", "san-infected-wilds-overlook-trees",
                     "san-infected-wilds-beach", "san-infected-wilds-suburbs-wide", "san-infected-wilds-accessibility",
                     "san-infected-wilds-pickups", "san-infected-wilds-script", "san-infected-wilds-suburbs-script"],
}


# ================================================================================================= geometry
def pt_tri_dist(P, T):
    """min distance of each point P (n,3) to the triangles T (m,3,3) (Ericson closest point, vectorised)"""
    out = np.full(len(P), np.inf)
    if not len(T) or not len(P):
        return out
    A, B, C = T[:, 0], T[:, 1], T[:, 2]
    AB, AC = B - A, C - A
    step = max(1, 600000 // max(1, len(T)))
    for s in range(0, len(P), step):
        p = P[s:s + step, None, :]
        AP, BP, CP = p - A, p - B, p - C
        d1, d2 = (AB * AP).sum(-1), (AC * AP).sum(-1)
        d3, d4 = (AB * BP).sum(-1), (AC * BP).sum(-1)
        d5, d6 = (AB * CP).sum(-1), (AC * CP).sum(-1)
        va, vb, vc = d3 * d6 - d5 * d4, d5 * d2 - d1 * d6, d1 * d4 - d3 * d2
        den = va + vb + vc
        den = np.where(np.abs(den) < 1e-12, 1e-12, den)
        v, w = vb / den, vc / den
        Q = A + AB * v[..., None] + AC * w[..., None]                       # interior
        # edge regions, then vertex regions override the interior point (the regions are disjoint)
        sd = lambda x: np.where(np.abs(x) < 1e-12, 1e-12, x)  # noqa: E731
        Qab = A + AB * np.clip(d1 / sd(d1 - d3), 0, 1)[..., None]
        Qac = A + AC * np.clip(d2 / sd(d2 - d6), 0, 1)[..., None]
        Qbc = B + (C - B) * np.clip((d4 - d3) / sd((d4 - d3) + (d5 - d6)), 0, 1)[..., None]
        Q = np.where(((vc <= 0) & (d1 >= 0) & (d3 <= 0))[..., None], Qab, Q)
        Q = np.where(((vb <= 0) & (d2 >= 0) & (d6 <= 0))[..., None], Qac, Q)
        Q = np.where(((va <= 0) & ((d4 - d3) >= 0) & ((d5 - d6) >= 0))[..., None], Qbc, Q)
        Q = np.where(((d1 <= 0) & (d2 <= 0))[..., None], np.broadcast_to(A, Q.shape), Q)
        Q = np.where(((d3 >= 0) & (d4 <= d3))[..., None], np.broadcast_to(B, Q.shape), Q)
        Q = np.where(((d6 >= 0) & (d5 <= d6))[..., None], np.broadcast_to(C, Q.shape), Q)
        out[s:s + step] = np.sqrt(((p - Q) ** 2).sum(-1)).min(1)
    return out


def ray_tris(o, d, T):
    """Moller-Trumbore: distance along the ray (d unit) to each triangle, inf if missed"""
    if not len(T):
        return np.zeros(0)
    e1, e2 = T[:, 1] - T[:, 0], T[:, 2] - T[:, 0]
    pv = np.cross(d, e2)
    det = (e1 * pv).sum(1)
    ok = np.abs(det) > 1e-12
    inv = np.where(ok, 1.0 / np.where(ok, det, 1), 0)
    tv = o - T[:, 0]
    u = (tv * pv).sum(1) * inv
    qv = np.cross(tv, e1)
    v = (qv * d).sum(1) * inv
    t = (e2 * qv).sum(1) * inv
    hit = ok & (u >= 0) & (v >= 0) & (u + v <= 1) & (t > 0)
    return np.where(hit, t, np.inf)


def seg_dist(P, o, d, tmax):
    """distance of points P to the segment o .. o + d tmax, and the ray parameter of the closest point"""
    t = np.clip(((P - o) * d).sum(1), 0, tmax)
    return np.linalg.norm(P - (o + t[:, None] * d), axis=1), t


def components(I):
    """connected pieces of a triangle list (shared vertex indices) -> list of triangle index arrays"""
    n = int(I.max()) + 1 if len(I) else 0
    par = np.arange(n)

    def find(x):
        while par[x] != x:
            par[x] = par[par[x]]
            x = par[x]
        return x
    for a, b, c in I:
        ra, rb, rc = find(a), find(b), find(c)
        par[rb] = ra
        par[find(rc)] = ra
    roots = np.array([find(a) for a in I[:, 0]]) if len(I) else np.zeros(0, int)
    return [np.nonzero(roots == r)[0] for r in np.unique(roots)]


# ================================================================================================= levels
class Level:
    def __init__(self, name, work=None):
        work = work or os.path.join(le.CACHE, "src")
        self.name = name
        self.src = le.fetch(name, work, suffixes=("",))[""]
        self.p = ndpak.Pak(self.src)
        self.insts = le.find_instances(self.p)
        self.users = {}
        for it in self.insts:
            for i in self._subs(it):
                self.users.setdefault(i, []).append(it)
        self._tri = {}
        self.hidden, self.cut = set(), {}
        self._coll = None

    def coll(self):
        """collision triangles of the level (-phys.pak), with their boxes"""
        if self._coll is None:
            T = np.zeros((0, 3, 3))
            try:
                ph = le.fetch(self.name, os.path.join(le.CACHE, "src"), suffixes=("-phys",))["-phys"]
                Ts = [x for x in (le.hc.triangles(it.mesh)[1] for it in le.phys_items(ph)[1]) if len(x)]
                if Ts:
                    T = np.concatenate(Ts).astype(float)
            except SystemExit:
                pass
            self._coll = (T, T.min(1) if len(T) else np.zeros((0, 3)), T.max(1) if len(T) else np.zeros((0, 3)))
        return self._coll

    @staticmethod
    def _subs(it):
        return list(it.subs) or [i for _, ids in it.names for i in ids]     # the record's own prototype first (AABB names can pick two assets)

    def apply_edits(self, edits):
        """the map's other (non-ivy) edits of this level, as the game will see them: hidden placements and cut triangles leave
        the support set (the gate edit took the iron gate the ivy beside it may have hung on)"""
        mine = [e for e in edits if e["level"] == self.name and e.get("auto") not in ("ivy-float", "ivy-pick")]
        if not mine:
            return
        for pl in le.plan_edits(mine, self.p, None):
            for it in pl["render"]:
                self.hidden.add(it.pak_off)
            for si, tr in pl["cut"].items():
                self.cut.setdefault(si, set()).update(int(t) for t in tr)
        print("  %s: %d placements hidden, %d submeshes cut by the map's other edits" % (self.name, len(self.hidden), len(self.cut)))

    def subname(self, i):
        return self.p.submeshes[i]["name"]

    def tris(self, i):
        if i not in self._tri:
            self._tri[i] = le.submesh_tris(self.p, i)
        return self._tri[i]

    def world(self, it, ids, edited=False, sel=None):
        out = []
        for i in ids:
            T = self.tris(i)
            if sel is not None:
                T = T[sel]
            if edited and i in self.cut:
                T = T[[k for k in range(len(T)) if k not in self.cut[i]]]
            if len(T):
                out.append((np.concatenate([T, np.ones(T.shape[:2] + (1,))], 2) @ it.M)[:, :, :3])
        return np.concatenate(out) if out else np.zeros((0, 3, 3))

    def item_world(self, item):
        kind, it, ids, sel = item
        return self.world(it, ids, sel=sel)


def proto_base(it):
    return (it.proto or "").split("/")[-1] or ", ".join(n for n, _ in it.names) or "(unnamed)"


def lod0(lv, ids):
    """the highest detail submeshes only (no LOD_1.., shadow proxies)"""
    keep = [i for i in ids if not re.search(r"LOD_?[1-9]|lod[1-9]|shadow_?proxy|_LOD[1-9]", lv.subname(i), re.I)]
    return keep or ids


def is_ivy_inst(it):
    return bool(IVY.search(proto_base(it).lower()))


def items_of(lv, foliage=False):
    """ivy items of a level: ('inst', it, ids, None) = a whole ivy placement; ('cut', it, [i], tris) = one connected piece of the
    ivy cards of a merged mesh (submesh i, triangle indices tris).  foliage: every foliage placement too (branches, leaves, bushes)"""
    out = []
    for it in lv.insts:
        ids = Level._subs(it)
        if not ids or it.pak_off in lv.hidden:
            continue
        if is_ivy_inst(it) or (foliage and FOLIAGE.search(proto_base(it)) and "level-section" not in (it.proto or "")):
            out.append(("inst", it, lod0(lv, ids), None))
            continue
        for i in lod0(lv, [i for i in ids if IVY_SUB.search(lv.subname(i) + "|")]):
            sm = lv.p.submeshes[i]
            I = np.array(lv.p.indices(sm), np.int64).reshape(-1, 3)
            live = np.nonzero((I[:, 0] != I[:, 1]) & (I[:, 1] != I[:, 2]))[0]
            if i in lv.cut:
                live = np.array([t for t in live if t not in lv.cut[i]], int)
            for comp in components(I[live]):
                if len(comp) >= MINTRI:
                    out.append(("cut", it, [i], live[comp]))
    return out


def support_tris(levels, lo, hi, item=None, mode="ivy"):
    """support triangles of these levels in the box, after the map's edits (shadow-caster copies are never drawn):
      "strict": everything drawn except the item itself (ivy and other foliage too) + the collision triangles
      "ivy":    render triangles that are not ivy
      "hard":   render triangles that are neither ivy nor other foliage (walls, ledges, ground, props)"""
    out = []
    for lv in levels:
        if mode == "strict":
            T, tlo, thi = lv.coll()
            m = (thi >= lo).all(1) & (tlo <= hi).all(1) if len(T) else np.zeros(0, bool)
            if m.any():
                out.append(T[m])
        for it in lv.insts:
            if (it.whi < lo).any() or (it.wlo > hi).any() or it.pak_off in lv.hidden or "tfrag-merge-shadows" in (it.proto or ""):
                continue
            base = proto_base(it)
            if mode != "strict" and is_ivy_inst(it):
                continue
            if mode == "hard" and FOLIAGE.search(base) and "level-section" not in (it.proto or ""):
                continue
            own = item is not None and item[1] is it and lv is item[4]
            ids = []
            for i in lod0(lv, Level._subs(it)):
                nm = lv.subname(i)
                if "shadow" in nm.lower() or (own and (item[3] is None or i in item[2])):
                    continue
                if mode != "strict" and IVY_SUB.search(nm + "|"):
                    continue
                if mode == "hard" and FOLIAGE.search(nm.split("|", 1)[-1]):
                    continue
                ids.append(i)
            W = lv.world(it, ids, edited=True)
            if len(W):
                m = (W.max(1) >= lo).all(1) & (W.min(1) <= hi).all(1)
                if m.any():
                    out.append(W[m])
    return np.concatenate(out) if out else np.zeros((0, 3, 3))


def attached(lv, item, levels, mode="strict"):
    """frac = share of the item's vertices within NEAR of support, near15 = within 0.15 m, dmin = the closest approach
    (inf: nothing within PAD), med = the median vertex distance"""
    W = lv.item_world(item)
    if not len(W):
        return None
    V = np.unique(W.reshape(-1, 3).round(4), axis=0)
    if len(V) > MAXV:
        V = V[np.linspace(0, len(V) - 1, MAXV).astype(int)]
    lo, hi = W.reshape(-1, 3).min(0), W.reshape(-1, 3).max(0)
    S = support_tris(levels, lo - PAD, hi + PAD, tuple(item) + (lv,), mode)
    d = pt_tri_dist(V, S)
    return {"frac": float((d <= NEAR).mean()), "near15": float((d <= 0.15).mean()), "dmin": float(d.min()) if len(d) else 9e9,
            "med": float(np.median(d)) if len(d) else 9e9, "lo": lo, "hi": hi, "nv": len(V), "ntri": len(W), "V": V, "d": d}


def verdict(lv, item, levels):
    """-> (floats?, reason, strict metrics).  Two rules:
      free:  no support at all (strict: anything drawn, collision) within GAP of any vertex - hangs in the air;
      sheet: a flat ivy sheet (creeper / hanging-flat / growing / wall-root / strand placement, made to lie on a surface) that
             no hard surface (wall, ledge, ground: not foliage, not ivy) touches: under SHEET_TOUCH of its vertices within
             0.15 m and its median vertex SHEET_GAP or more away (stands in front of the wall, in bushes or in an opening)"""
    r = attached(lv, item, levels, "strict")
    if r is None:
        return False, "", None
    if r["dmin"] > GAP:
        return True, "free (nearest support %.2f m)" % min(r["dmin"], 99), r
    if item[0] == "inst" and FLAT.search(proto_base(item[1]).lower()):
        h = attached(lv, item, levels, "hard")
        r["hard"] = h
        if h["near15"] < SHEET_TOUCH and h["med"] >= SHEET_GAP:
            return True, "sheet off its wall (median %.2f m from the nearest hard surface, %.0f%% of it within 15 cm)" % (
                min(h["med"], 99), 100 * h["near15"]), r
    return False, "", r


def edit_for(lv, item, why, auto):
    kind, it, ids, sel = item
    W = lv.item_world(item)
    lo, hi = W.reshape(-1, 3).min(0), W.reshape(-1, 3).max(0)
    c = (lo + hi) / 2
    nm = proto_base(it).replace(".ma", "")
    sub = lv.subname(ids[0]).split("|", 1)[1] if kind == "cut" else ""
    e = {"name": "%s: %s @%#x (%.1f, %.1f, %.1f)%s" % (auto, nm if kind == "inst" else "%s ivy %s (%d tris)" % (nm, sub.split("|")[0], len(sel)),
                                                       it.pak_off, c[0], c[1], c[2], (" - " + why) if why else ""),
         "level": lv.name, "box": [round(float(v), 2) for v in np.concatenate([np.floor((lo - 0.05) * 100) / 100, np.ceil((hi + 0.05) * 100) / 100])],
         "action": "remove", "collision": False, "auto": auto}
    if kind == "inst":
        e["render"] = {"offsets": ["%#x" % it.pak_off]}
    else:
        e["render"] = {"world": True, "cut_name": nm, "cut_sub": re.escape(sub) + "$", "cut_tris": [int(t) for t in sel]}
    return e


def cut_ok(lv, item):
    kind, it, ids, sel = item
    return kind == "inst" or all(len(lv.users.get(i, [])) <= 1 for i in ids)


def same_target(a, b):
    return a["level"] == b["level"] and a["render"] == b["render"]


# ================================================================================================= spec I/O
def load_spec():
    return json.load(open(le.SPEC, encoding="utf-8"))


def save_spec(d):
    with open(le.SPEC, "w", encoding="utf-8", newline="\r\n") as f:
        json.dump(d, f, indent=1, ensure_ascii=False)
        f.write("\n")


def map_entry(d, key):
    return next(x for x in d["maps"] if x["key"] == key)


def put_edits(key, new, auto):
    """replace the map's edits tagged auto with new (minus targets another edit already removes) -> number written"""
    d = load_spec()
    m = map_entry(d, key)
    keep = [e for e in m.get("edits", []) if e.get("auto") != auto]
    add = []
    for e in new:
        if not any(same_target(e, k) for k in keep + add):
            add.append(e)
    m["edits"] = keep + add
    save_spec(d)
    return len(add)


# ================================================================================================= commands
def load_levels(names):
    out = []
    for n in names:
        try:
            out.append(Level(n))
        except SystemExit as e:
            print("  (level %s skipped: %s)" % (n, e))
    return out


def map_level_objs(key):
    levels = load_levels(le.map_levels(key))
    for lv in levels:
        lv.apply_edits(le.spec_edits(key))
    return levels


def cmd_scan(key, write=False, js=None):
    print("map %s" % key)
    levels = map_level_objs(key)
    res = []
    for lv in levels:
        its = items_of(lv, foliage=True)
        if its:
            print("level %s: %d items (%d ivy / foliage placements, %d merged ivy pieces)" % (
                lv.name, len(its), sum(1 for x in its if x[0] == "inst"), sum(1 for x in its if x[0] == "cut")))
        for item in its:
            fl, why, r = verdict(lv, item, levels)
            if r is not None and fl:
                res.append((lv, item, why, r))
    print("\n%d floating items (rules: free / sheet, see verdict())" % len(res))
    extra = load_levels(SP_EXTRA[key]) if res and SP_EXTRA.get(key) else []
    edits, rows = [], []
    for lv, item, why, r in sorted(res, key=lambda x: (bool(BACKDROP.search(proto_base(x[1][1]))), -x[3]["dmin"])):
        kind, it, ids, sel = item
        c = (r["lo"] + r["hi"]) / 2
        what = proto_base(it)[:40] if kind == "inst" else "%s|%s" % (proto_base(it)[:20], lv.subname(ids[0]).split("|", 2)[1][:19])
        back = bool(BACKDROP.search(proto_base(it)))
        gain = [] if back else [x.name for x in extra if not verdict(lv, item, levels + [x])[0]]
        cause = ("its support is in %s, which the map does not load" % "/".join(gain)) if gain else \
            "no support in the section's other SP levels either (authored that way / support never shipped)"
        row = {"level": lv.name, "kind": kind, "offset": "%#x" % it.pak_off, "proto": it.proto, "what": what, "tris": r["ntri"],
               "center": [round(float(v), 2) for v in c], "why": why, "cause": cause, "removed": not back and cut_ok(lv, item)}
        rows.append(row)
        tag = "BACKDROP (kept)" if back else "REMOVE" if cut_ok(lv, item) else "shared mesh (kept)"
        print("%-15s %-34s %-4s @%#08x %-40s %5d tris (%7.1f %5.1f %7.1f) %s; %s" % (
            tag, lv.name, kind, it.pak_off, what, r["ntri"], c[0], c[1], c[2], why, cause))
        if row["removed"]:
            edits.append(edit_for(lv, item, why, "ivy-float"))
    if js:
        json.dump(rows, open(js, "w"), indent=1)
    print("\n%d remove edits" % len(edits))
    for e in edits:
        print("  ", e["name"])
    if write:
        n = put_edits(key, edits, "ivy-float")
        print("sp_maps.json %s: %d ivy-float edits written (old ivy-float entries replaced)" % (key, n))
    return edits


PICK = re.compile(r"cam\s+(\S+)\s+(\S+)\s+(\S+)\s+dir\s+(\S+)\s+(\S+)\s+(\S+)\s+t\s+(\S+)(?:\s+hit\s+(\S+)\s+(\S+)\s+(\S+))?")


def parse_picks(path):
    out = []
    for ln in open(path, encoding="utf-8", errors="replace"):
        m = PICK.search(ln)
        if not m:
            continue
        v = [float(x) if x is not None else None for x in m.groups()]
        o, d = np.array(v[0:3]), np.array(v[3:6])
        d /= np.linalg.norm(d) or 1
        hit = np.array(v[7:10]) if v[7] is not None else None
        dist = float(np.linalg.norm(hit - o)) if hit is not None else 200.0
        mp = re.search(r"\bmap\s+(\S+)", ln)
        out.append({"o": o, "d": d, "dist": dist, "map": mp.group(1) if mp else None, "line": ln.strip()})
    return out


def pick_item(levels, pk, reach=0.6):
    """the ivy / foliage item the ray goes through first (before the world hit + 0.5 m); else the one passing closest (< reach m)"""
    o, d, tmax = pk["o"], pk["d"], pk["dist"] + 0.5
    best, near = None, None
    for lv in levels:
        cand = items_of(lv) + [("inst", it, Level._subs(it), None) for it in lv.insts
                               if FOLIAGE.search(proto_base(it)) and not is_ivy_inst(it) and it.pak_off not in lv.hidden]
        for item in cand:
            it = item[1]
            lo, hi = it.wlo - reach, it.whi + reach
            with np.errstate(divide="ignore", invalid="ignore"):          # slab test of the placement box against the segment
                t1, t2 = (lo - o) / d, (hi - o) / d
            tn, tf = np.nanmax(np.minimum(t1, t2)), np.nanmin(np.maximum(t1, t2))
            if tn > tf or tf < 0 or tn > tmax:
                continue
            W = lv.item_world(item)
            if not len(W):
                continue
            pri = 0 if item[0] == "cut" or is_ivy_inst(it) else 1          # ivy before other foliage at the same distance
            t = ray_tris(o, d, W).min()
            if t <= tmax and (best is None or (t + 0.25 * pri) < best[0]):
                best = (t + 0.25 * pri, lv, item, t)
            ds, tt = seg_dist(W.reshape(-1, 3), o, d, tmax)
            k = int(ds.argmin())
            if ds[k] <= reach and (near is None or ds[k] + 0.1 * pri < near[0]):
                near = (float(ds[k]) + 0.1 * pri, lv, item, float(tt[k]), float(ds[k]))
    if best:
        return best[1], best[2], "the ray goes through it %.1f m from the camera" % best[3]
    if near:
        return near[1], near[2], "the ray passes %.2f m from it, %.1f m from the camera" % (near[4], near[3])
    return None


def cmd_picks(key, path, write=False):
    pks = parse_picks(path)
    m = map_entry(load_spec(), key)
    want = {m["level"], key, "to1-" + key}
    pks2 = [p for p in pks if not p["map"] or p["map"] in want]
    print("%s: %d picks, %d on %s" % (path, len(pks), len(pks2), key))
    levels = map_level_objs(key)
    edits = []
    for pk in pks2:
        r = pick_item(levels, pk)
        if not r:
            print("  nothing ivy / foliage on the ray: %s" % pk["line"])
            continue
        lv, item, why = r
        if not cut_ok(lv, item):
            print("  %s @%#x: a merged mesh other placements share - cannot remove one copy (%s)" % (lv.name, item[1].pak_off, pk["line"]))
            continue
        e = edit_for(lv, item, "picked in game", "ivy-pick")
        if any(same_target(x, e) for x in edits):
            continue
        edits.append(e)
        print("  %s  <- %s" % (e["name"], why))
    if write and edits:
        old = [e for e in map_entry(load_spec(), key).get("edits", []) if e.get("auto") == "ivy-pick"]
        new = [e for e in edits if not any(same_target(e, x) for x in old)]
        n = put_edits(key, old + new, "ivy-pick")
        print("sp_maps.json %s: %d ivy-pick edits (%d new)" % (key, n, len(new)))
    return edits


def cmd_list(key):
    for e in map_entry(load_spec(), key).get("edits", []):
        print("%-10s %s" % (e.get("auto", "hand"), e["name"]))


def cmd_drop(key, what):
    d = load_spec()
    m = map_entry(d, key)
    keep = []
    for e in m.get("edits", []):
        r = e.get("render") if isinstance(e.get("render"), dict) else {}
        offs = [o.lower() for o in r.get("offsets") or []]
        if e.get("auto") in ("ivy-float", "ivy-pick") and any(w.lower() in e["name"].lower() or w.lower() in offs for w in what):
            print("dropped:", e["name"])
        else:
            keep.append(e)
    m["edits"] = keep
    save_spec(d)


def main(argv):
    a = [x for x in argv[1:] if not x.startswith("--")]
    o = {x.split("=")[0]: (x.split("=", 1)[1] if "=" in x else True) for x in argv[1:] if x.startswith("--")}
    if len(a) < 2:
        print(__doc__)
        return 1
    if a[0] == "scan":
        cmd_scan(a[1], bool(o.get("--write")), o.get("--json"))
    elif a[0] == "picks" and len(a) > 2:
        cmd_picks(a[1], a[2], bool(o.get("--write")))
    elif a[0] == "list":
        cmd_list(a[1])
    elif a[0] == "drop":
        cmd_drop(a[1], a[2:])
    else:
        print(__doc__)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
