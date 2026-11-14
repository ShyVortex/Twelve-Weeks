"""Roof shadow caps: sun shadow casters under the roofs SP never needed to shadow (winter Supermarket, jackson-market).

Why: every static sun caster of a level is a shadow-blocker submesh (material lib-shadowblocker: tfrag-merge-shadows, per-asset shadowProxy;
render surfaces cast no sun shadow, re/maps/level-edit.md 14).  SP switches the sun off inside the Supermarket (interior zones rgbi-i 2.8 -> 0),
so its artists never capped the store hall, the pharmacy or the truck bay: pat-supermarket-walls-grouped's proxy is three thin walls plus one
cap over the back rooms only.  Our door sun (immersion.c, 4e425049 / aa99536f) keeps the outdoor sun on in the rooms that see out through the
3 opened doors, so sunlight went straight through the hall roof onto the back-room / bakery walls.

What: the spec (data/shadow-caps.json, per level) names one unique (single placement) shadow-blocker submesh and DONOR triangles of it whose
loss changes no shadow (top / bottom / end faces of 8 cm thin walls: a ray through such a wall always crosses its big faces too).  The donors'
vertices (used by no other triangle) are moved to form the CAP quads: horizontal caps just under the roof sheets / interior ceilings, and the
sun-facing outer walls (south, west) that have no blocker.  Every cap lies inside the building envelope (under the roof, inside the walls), so
no outdoor surface can be newly shadowed (a sunlit exterior point's sun ray leaves the building).  Two donors sharing one vertex make one quad
(the shared vertex is the quad corner both triangles share); a third donor on that vertex collapses onto it (zero area).
Caps face the sun (+y, or outward on the sun side) like SP's own back-room cap (triangles 44 / 45, +y only).
Written in place into the level's built render pak(s) (level_edit.build_edits, after the ghost proxy sweep); idempotent; verified after write.
  python shadow_caps.py apply <pak>...      # cap (and verify) built paks by hand
  python shadow_caps.py check <pak>...      # report only
"""
import json
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "models"))
SPEC = os.path.join(HERE, "data", "shadow-caps.json")
TOL = 0.004                       # metres: a donor vertex this close to its cap corner is already capped (stream step <= 1.7 mm here)
MAX_DONOR_AREA = 3.0              # m2: a donor that is still in its original place must be a thin-wall face, never a real caster face


def load_spec():
    return json.load(open(SPEC, encoding="utf-8")) if os.path.exists(SPEC) else {}


def cap_quad(c):
    """cap spec -> (tA, tB) world triangles, each (3, 3): tA = (p01, p11, p00), tB = (p11, p10, p00), normal along c['face']"""
    if c["kind"] == "h":
        x0, z0, x1, z1, y = c["x0"], c["z0"], c["x1"], c["z1"], c["y"]
        p00, p10, p11, p01 = (x0, y, z0), (x1, y, z0), (x1, y, z1), (x0, y, z1)
    elif c["kind"] == "x":
        x, a0, a1, y0, y1 = c["x"], c["a0"], c["a1"], c["y0"], c["y1"]
        p00, p10, p11, p01 = (x, y0, a0), (x, y0, a1), (x, y1, a1), (x, y1, a0)
    elif c["kind"] == "z":
        z, a0, a1, y0, y1 = c["z"], c["a0"], c["a1"], c["y0"], c["y1"]
        p00, p10, p11, p01 = (a0, y0, z), (a1, y0, z), (a1, y1, z), (a0, y1, z)
    else:
        raise SystemExit("shadow caps: unknown cap kind %r" % c["kind"])
    tA = np.array([p01, p11, p00], float)
    tB = np.array([p11, p10, p00], float)
    want = np.array(c["face"], float)
    if np.cross(tA[1] - tA[0], tA[2] - tA[0]) @ want < 0:             # mirror the quad (swap p10 / p01): same corners, the other face
        tA = np.array([p10, p11, p00], float)
        tB = np.array([p11, p01, p00], float)
    for t in (tA, tB):
        assert np.cross(t[1] - t[0], t[2] - t[0]) @ want > 0
    return tA, tB


def plan(p, sm_i, spec):
    """-> {vertex: world target}; raises when the donors are not what the spec expects"""
    sm = p.submeshes[sm_i]
    I = np.array(p.indices(sm), np.int64).reshape(-1, 3)
    if len(I) != spec["tris"]:
        raise SystemExit("shadow caps: %s has %d triangles, spec expects %d" % (spec["submesh"][-60:], len(I), spec["tris"]))
    groups, caps = spec["donors"], spec["caps"]
    if len(caps) > len(groups):
        raise SystemExit("shadow caps: %d caps but only %d donor groups" % (len(caps), len(groups)))
    uses = np.bincount(I.ravel(), minlength=sm["vcount"])
    tgt = {}
    for g, c in zip(groups, caps):
        gv = I[g].ravel()
        if any(uses[v] != (gv == v).sum() for v in set(gv.tolist())):
            raise SystemExit("shadow caps: donor group %s shares vertices with kept triangles" % g)
        a, b = I[g[0]].tolist(), I[g[1]].tolist()
        sh = set(a) & set(b)
        if len(sh) > 1:
            raise SystemExit("shadow caps: donors %s share an edge" % g)
        sv = sh.pop() if sh else None
        if sv is not None:                                              # rotate (winding kept) so the shared vertex is p00 (last) in both
            while a[2] != sv:
                a = a[1:] + a[:1]
            while b[2] != sv:
                b = b[1:] + b[:1]
        tA, tB = cap_quad(c)
        for vs, t in ((a, tA), (b, tB)):
            for v, P in zip(vs, t):
                if v in tgt and np.abs(tgt[v] - P).max() > 1e-9:
                    raise SystemExit("shadow caps: vertex %d of donors %s needs two positions" % (v, g))
                tgt[v] = P
        for k in g[2:]:                                                 # extra donors on the shared vertex collapse onto it (zero area)
            vs = I[k].tolist()
            if sv is None or sv not in vs:
                raise SystemExit("shadow caps: donor %d of %s is not on the group's shared vertex" % (k, g))
            for u in vs:
                if u not in tgt:
                    tgt[u] = tA[2]
    return tgt


def apply_pak(path, spec, fix=True, log=print):
    """cap one built render pak in place.  -> number of vertices moved (0 = already capped)"""
    import level_morph as lm
    R = lm.Render(path)
    hit = [i for i, sm in enumerate(R.p.submeshes) if sm["name"].endswith(spec["submesh"])]
    if len(hit) != 1:
        raise SystemExit("shadow caps %s: submesh %r found %d times" % (os.path.basename(path), spec["submesh"][-60:], len(hit)))
    s = R.sub(hit[0])
    tgt = plan(R.p, hit[0], spec)
    vids = np.array(sorted(tgt), np.int64)
    W = s.world(vids)
    T = np.array([tgt[int(v)] for v in vids])
    todo = np.abs(W - T).max(1) > TOL
    if not todo.any():
        log("roof shadow caps %s: %d caps in place (%d vertices of %s)" % (os.path.basename(path), len(spec["caps"]), len(vids), spec["submesh"].split("|")[0][-40:]))
        return 0
    I = np.array(R.p.indices(R.p.submeshes[hit[0]]), np.int64).reshape(-1, 3)
    L = s.world()
    for g in spec["donors"][:len(spec["caps"])]:                       # a donor not yet moved must still be a thin-wall face
        for k in g:
            if (np.abs(L[I[k]] - np.array([tgt[int(v)] for v in I[k]])).max(1) > TOL).any():
                ar = 0.5 * np.linalg.norm(np.cross(L[I[k][1]] - L[I[k][0]], L[I[k][2]] - L[I[k][0]]))
                if ar > MAX_DONOR_AREA:
                    raise SystemExit("shadow caps %s: donor triangle %d has %.1f m2 - not a thin-wall face, the source pak changed" % (os.path.basename(path), k, ar))
    if not fix:
        log("roof shadow caps %s: %d of %d cap vertices NOT in place" % (os.path.basename(path), int(todo.sum()), len(vids)))
        return int(todo.sum())
    loc = s.to_local(T)
    for v, P in zip(vids, loc):
        s.moved[int(v)] = P
    lm.flush_render(R, log)
    with open(path, "wb") as fh:
        fh.write(R.rb)
    R2 = lm.Render(path)                                                # verify the written pak
    W2 = R2.sub(hit[0]).world(vids)
    err = np.abs(W2 - T).max()
    if err > TOL:
        raise SystemExit("shadow caps %s: written caps off by %.4f m" % (os.path.basename(path), err))
    log("roof shadow caps %s: %d caps written (%d vertices moved, max error %.4f m)" % (os.path.basename(path), len(spec["caps"]), int(todo.sum()), err))
    return int(todo.sum())


def protected(path, p=None):
    """{submesh index: set(donor triangle ids)} of the pak's level spec (the ghost proxy sweep never cuts them)"""
    lv = os.path.basename(path)[:-4]
    spec = load_spec().get(lv)
    if not spec:
        return {}
    if p is None:
        import ndpak
        p = ndpak.Pak(path)
    hit = [i for i, sm in enumerate(p.submeshes) if sm["name"].endswith(spec["submesh"])]
    if len(hit) != 1:
        return {}
    return {hit[0]: {k for g in spec["donors"][:len(spec["caps"])] for k in g}}


def apply_all(written, log=print, fix=True):
    """build hook: every written render pak whose level has a spec"""
    spec = load_spec()
    out = {}
    for f in written:
        lv = os.path.basename(f)[:-4] if f.endswith(".pak") else None
        if lv in spec and not lv.endswith("-phys"):
            out[f] = apply_pak(f, spec[lv], fix, log)
    return out


def main(argv):
    if len(argv) < 2 or argv[0] not in ("apply", "check"):
        print(__doc__)
        return 2
    apply_all(argv[1:], fix=argv[0] == "apply")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
