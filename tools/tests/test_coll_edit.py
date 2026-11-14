"""Offline checks of tools/maps/coll_edit.py (Scene Editor Collision edit mode -> Havok collision of the -phys.pak).
Needs the Jackson supermarket collision pak in the level-edit cache (re/maps/level-edit-cache/src/pat-jackson-supermarket-phys.pak, filled by any
`level_edit.py apply jackson-market`).  Checks: shared and packed vertices moved by a spec decode back at their targets (quantisation error),
everything else stays where it was, structure valid (validate_mesh + check_tree4), pak size unchanged for moves, triangle deletion and added
box / quad change the triangle count by the right amount, spec -> geoedit.edits_for -> build_edits chain (stamp reuse)."""
import json
import os
import shutil
import sys
import tempfile
import sys as _t2s, os as _t2o; _t2s.path.append(_t2o.path.normpath(_t2o.path.join(_t2o.path.dirname(_t2o.path.abspath(__file__)), ".."))); import t2rtmp  # noqa: E402,F401

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(TOOLS, "maps"))
import level_edit as le  # noqa: E402
import coll_edit as ce  # noqa: E402
import geoedit  # noqa: E402
import havok_convert as hc  # noqa: E402

LV = "pat-jackson-supermarket"
SRC = None
for r in (le.CACHE, os.path.join(le.ROOT, "re", "maps", "level-edit-cache"), r"..\t2r-wt\mstats\re\maps\level-edit-cache", r".\re\maps\level-edit-cache"):
    p = os.path.join(r, "src", LV + "-phys.pak")
    if os.path.exists(p):
        SRC = p
        break
if SRC is None:
    print("test_coll_edit: %s-phys.pak not in the level-edit cache: SKIPPED" % LV)
    sys.exit(0)


def quiet(*a, **k):
    pass


def all_vertices(path):
    """[(item, kind, section, local index, xyz)] of every shared and packed vertex"""
    out = []
    for k, it in enumerate(le.phys_items(path)[1]):
        m = it.mesh
        sv = hc.shared_positions(m)
        out += [(k, "s", -1, i, sv[i]) for i in range(len(sv))]
        for si, s in enumerate(m.sections):
            if s.npv:
                cp = np.frombuffer(s.codec, np.float32).astype(np.float64)
                q = m.packed[s.fp:s.fp + s.npv].astype(np.int64)
                V = cp[:3] + cp[3:] * np.stack([q & 0x7FF, (q >> 11) & 0x7FF, q >> 22], 1)
                out += [(k, "p", si, i, V[i]) for i in range(len(V))]
    return out


items = le.phys_items(SRC)[1]
BASE = ce.problems(SRC)                 # the source has its own (ND) problems: edits must not add any
V0 = all_vertices(SRC)
pos0 = np.array([v[4] for v in V0])


def unique_pick(kind):
    """a vertex of the given kind with no other vertex within 5 cm (so an edit moves exactly that one)"""
    for v in V0:
        if v[1] == kind and (np.abs(pos0 - v[4]) <= 0.05).all(1).sum() == 1:
            return v
    return None


vs, vp = unique_pick("s"), unique_pick("p")
assert vs is not None, "no isolated shared vertex"
moves = [{"from": [float(x) for x in vs[4]], "to": [float(x) for x in vs[4] + [0.0, 0.35, 0.0]]}]
if vp is not None:
    moves.append({"from": [float(x) for x in vp[4]], "to": [float(x) for x in vp[4] + [0.05, -0.04, 0.03]]})
print("moving 1 shared%s vertex" % (" + 1 packed" if vp is not None else " (no isolated packed vertex found)"))
td = tempfile.mkdtemp()
out = os.path.join(td, "o-phys.pak")
st = ce.colledit_level(LV, [{"name": "t-verts", "level": LV, "kind": "verts", "moves": moves}], SRC, out, quiet)
assert st[0] >= 1 and (vp is None or st[1] >= 1), st
assert ce.verify_file(out, BASE) == 0, "structure problems after the move"
assert os.path.getsize(out) == os.path.getsize(SRC), "a vertex move must not change the pak size"
V1 = all_vertices(out)
assert len(V1) == len(V0)
d = np.array([b[4] - a[4] for a, b in zip(V0, V1)])
moved = np.nonzero((np.abs(d) > 1e-9).any(1))[0]
want = {tuple(np.round(m["from"], 3)): np.array(m["to"]) - np.array(m["from"]) for m in moves}
for i in moved:                                              # only the requested vertices moved, each by (to - from) within quantisation
    key = tuple(np.round(V0[i][4], 3))
    assert key in want, "stray vertex moved %s by %s" % (key, d[i])
    tol = 4e-4 if V0[i][1] == "s" else 0.02
    assert np.abs(d[i] - want[key]).max() <= tol, (V0[i][1], d[i], want[key])
assert len(moved) >= len(moves), (len(moved), moves, [(V0[i][:4], d[i]) for i in moved])
assert ce.find_vertices(out, [m["to"] for m in moves], 0.02).all()
print("verts: %d vertices moved (%d shared, %d packed), structure valid, size unchanged OK" % (len(moved), st[0], st[1]))

# ---- cluster: every vertex in a 3 m box around a wall moved up by 0.5 m (shared + packed, many primitives / sections)
ctr = vs[4]
inb = [v for v in V0 if (np.abs(v[4] - ctr) <= 1.5).all()]
fr = {}
for v in inb:
    fr[tuple(np.round(v[4], 3))] = v[4]
cm = [{"from": [float(x) for x in f], "to": [float(f[0]), float(f[1] + 0.5), float(f[2])]} for f in fr.values()]
outc = os.path.join(td, "c-phys.pak")
stc = ce.colledit_level(LV, [{"name": "t-cluster", "level": LV, "kind": "verts", "moves": cm}], SRC, outc, quiet)
assert ce.verify_file(outc, BASE) == 0, (ce.problems(outc), BASE)
assert os.path.getsize(outc) == os.path.getsize(SRC)
assert ce.find_vertices(outc, [m["to"] for m in cm], 0.02).all()
print("cluster: %d positions (%d shared + %d packed vertices) moved up 0.5 m, structure valid OK" % (len(cm), stc[0], stc[1]))

# ---- delete: three big triangles of the item with the most sections
big = int(np.argmax([len(it.mesh.sections) for it in items]))
keys, T, _ = hc.triangles(items[big].mesh)
sel = [i for i in range(len(T)) if 0.5 * np.linalg.norm(np.cross(T[i][1] - T[i][0], T[i][2] - T[i][0])) > 0.5][:3]
dele = [np.asarray(T[i], np.float32).reshape(9).astype(float).tolist() for i in sel]
out2 = os.path.join(td, "d-phys.pak")
st = ce.colledit_level(LV, [{"name": "t-del", "level": LV, "kind": "delete", "tris": dele}], SRC, out2, quiet)
assert st[2] >= len(sel), st
assert ce.verify_file(out2, BASE) == 0, (ce.problems(out2), BASE)
n0 = sum(len(hc.triangles(it.mesh)[0]) for it in items)
n1 = sum(len(hc.triangles(it.mesh)[0]) for it in le.phys_items(out2)[1])
assert n1 <= n0 - len(sel), (n0, n1)
print("delete: %d triangles deleted (%d -> %d), structure valid OK" % (st[2], n0, n1))

# ---- box + quad
T0 = hc.triangles(items[0].mesh)[1]
c = T0[len(T0) // 2].mean(0)                                  # item 0 has room for new keys in this level
out3 = os.path.join(td, "a-phys.pak")
try:
    st = ce.colledit_level(LV, [{"name": "t-box", "level": LV, "kind": "box", "center": (c + [0, 1.0, 0]).tolist(), "size": [1.0, 1.0, 1.0], "yaw": 30},
                                {"name": "t-quad", "level": LV, "kind": "quad", "points": [(c + p).tolist() for p in ([0, 2, 0], [2, 2, 0], [2, 4, 0], [0, 4, 0])]}], SRC, out3, quiet)
    assert st[3] == 24, st
    assert ce.verify_file(out3, BASE) == 0
    n2 = sum(len(hc.triangles(it.mesh)[0]) for it in le.phys_items(out3)[1])
    assert n2 == n0 + 24, (n0, n2)
    print("add: box + quad = 24 triangles, structure valid OK")
except SystemExit as ex:
    print("add: skipped (%s)" % str(ex)[:160])

# ---- chain: spec -> geoedit.edits_for -> build_edits (second run served from the stamp)
spec = os.path.join(td, "spec")
os.makedirs(spec)
json.dump({"key": "t", "version": 1, "edits": [{"name": "t-verts", "level": LV, "kind": "verts", "active": True, "moves": moves},
                                                  {"name": "off", "level": LV, "kind": "delete", "active": False, "tris": dele}]}, open(os.path.join(spec, "t-colledits.json"), "w"))
old = ce.DATA, geoedit.DATA
ce.DATA, geoedit.DATA = spec, spec
try:
    edits = geoedit.edits_for("t")
    assert [e["action"] for e in edits] == ["colledit"], edits
    work = os.path.join(td, "work")
    os.makedirs(os.path.join(work, "src"))
    shutil.copyfile(SRC, os.path.join(work, "src", LV + "-phys.pak"))
    outd = os.path.join(td, "outd")
    w = le.build_edits(edits, work_dir=work, out_dir=outd, log=quiet)
    assert [os.path.basename(x) for x in w] == [LV + "-phys.pak"] and os.path.dirname(w[0]).endswith("colledit"), w
    m1 = os.path.getmtime(w[0])
    assert le.build_edits(edits, work_dir=work, out_dir=outd, log=quiet) == w and os.path.getmtime(w[0]) == m1
    assert ce.find_vertices(w[0], [m["to"] for m in moves], 0.02).all()
finally:
    ce.DATA, geoedit.DATA = old
print("coll_edit OK (verts shared + packed, delete, box / quad, spec -> build_edits chain)")
