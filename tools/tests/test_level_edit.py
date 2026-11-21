"""Offline checks of tools/maps/level_edit.py (baked level geometry / collision edits, re/maps/level-edit.md).
Part 1 needs no game files (Codec3Axis4 tree builder, matrix maths, triangle / box overlap).
Part 2 needs the TLOU2 install (world-santa-barbara.psarc, read only; ~4 s of extraction): the Hillside Houses gate edits.
Skips part 2 when the game is not installed."""
import json
import math
import os
import sys
import tempfile
import sys as _t2s, os as _t2o; _t2s.path.append(_t2o.path.normpath(_t2o.path.join(_t2o.path.dirname(_t2o.path.abspath(__file__)), ".."))); import t2rtmp  # noqa: E402,F401  (temp hygiene: tools/t2rtmp.py)

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(TOOLS, "maps"))
import level_edit as le  # noqa: E402

# ---------------------------------------------------------------- part 1: no game files
rng = np.random.default_rng(7)
for n in (1, 2, 3, 17, 59, 127):
    c = rng.uniform(-5, 5, (n, 3))
    boxes = np.stack([c - rng.uniform(0.05, 0.6, (n, 3)), c + rng.uniform(0.05, 0.6, (n, 3))], 1)
    dmin, dmax = boxes[:, 0].min(0) - 0.01, boxes[:, 1].max(0) + 0.01
    raw = le.build_tree4(boxes, dmin, dmax)
    assert len(raw) == 4 * (2 * n - 1), n
    leaves = le.walk_tree4(raw, dmin, dmax)
    assert sorted(x[0] for x in leaves) == list(range(n)), n
    for pi, node, nmin, nmax in leaves:
        assert (boxes[pi, 0] >= nmin - 1e-9).all() and (boxes[pi, 1] <= nmax + 1e-9).all(), (n, pi)

# row-vector matrices: the rotated matrix places a local point where the rotated world point is
M = np.eye(4)
M[:3, :3] = np.array([[0.8, 0, 0.1], [0, 0.8, 0], [-0.1, 0, 0.8]])
M[3, :3] = [-111.4, 45.7, -167.8]
pt = np.array([3.0, 2.0, 0.1, 1.0])
w0 = (pt @ M)[:3]
for ang in (90.0, -37.0):
    M2 = le.edit_matrix(M, "rotate", pivot=M[3, :3], angle=ang)
    assert np.allclose((pt @ M2)[:3], le.transform_point(w0, "rotate", pivot=M[3, :3], angle=ang), atol=1e-9)
c, s = math.cos(math.radians(90)), math.sin(math.radians(90))
assert np.allclose(le.transform_point([1, 0, 0], "rotate", pivot=[0, 0, 0], angle=90), [0, 0, -1], atol=1e-12)   # +x -> -z
assert np.allclose(le.edit_matrix(M, "move", delta=[1, 2, 3])[3, :3], M[3, :3] + [1, 2, 3])
assert le.edit_matrix(M, "remove", hide_dy=-1000)[3, 1] == M[3, 1] - 1000

T = np.array([[[0, 0, 0], [1, 0, 0], [0, 1, 0]], [[5, 5, 5], [6, 5, 5], [5, 6, 5]], [[-1, 0.5, 0.5], [2, 0.5, 0.5], [0.5, 0.5, 3]]], float)
assert list(le.tri_box_overlap(T, [0.2, 0.2, -0.1], [0.4, 0.4, 0.1])) == [True, False, False]
assert list(le.tri_box_overlap(T, [0, 0, 0.4], [1, 1, 0.6]))[2]
# removed geometry must not keep occluding: every removal edit yields tolerant vis_open edits (VIS_INFO_1 pairs), one per art level
rem = [{"name": "a", "level": "L1", "action": "remove", "box": [0, 0, 0, 2, 3, 2], "render": {}, "collision": {}},
       {"name": "b", "level": "L2", "action": "remove", "box": [1, 0, 1, 3, 3, 3], "render": False, "collision": {"mode": "inside"}},
       {"name": "c", "level": "L1", "action": "remove", "box": [200, 0, 200, 201, 2, 201], "render": {}, "collision": False},
       {"name": "m", "level": "L1", "action": "move", "box": [50, 0, 50, 51, 1, 51]}]
av = le.auto_vis_edits(rem, ["L1", "L2", "pat-const-fx", "part-x"])
assert [e["level"] for e in av] == ["L1", "L2"] and all(e["action"] == "vis_open" and e["tolerant"] for e in av), av
assert len(av[0]["pairs"]) == 2, av[0]["pairs"]                      # a+b merge (touching), c is its own cluster; the move is ignored
p0 = av[0]["pairs"][0]
assert p0["box"][0] < p0["outside"][0] < 0 and p0["box"][3] > p0["outside"][3] > 3, p0   # reach box encloses the near box encloses the removal
assert le.auto_vis_edits([e for e in rem if e["action"] != "remove"], ["L1"]) == []
os.environ["T2R_AUTO_VIS"] = "0"
assert le.auto_vis_edits(rem, ["L1"]) == []
del os.environ["T2R_AUTO_VIS"]
# every map with removals gets it by default (edits_for appends them unless the map spec says "auto_vis": false)
spec = json.load(open(le.SPEC, encoding="utf-8"))["maps"]
assert all(m.get("auto_vis", True) is not False for m in spec if m["key"] == "jackson-market")
print("level_edit part 1 OK")

# ---------------------------------------------------------------- part 2: the gate (needs the game)
if not le.world_archives():
    print("skip part 2 (no TLOU2 install)")
    sys.exit(0)
work = tempfile.mkdtemp()
spec = json.load(open(os.path.join(TOOLS, "maps", "sp_maps.json"), encoding="utf-8"))
edits = [m for m in spec["maps"] if m["key"] == "wilds-houses"][0]["edits"]
assert len(edits) >= 1 and edits[0]["action"] == "remove"
LV = edits[0]["level"]
out = os.path.join(work, "out")
files = le.build_edits(edits, work, out, log=lambda *a: None)
assert [os.path.basename(f) for f in files][:2] == [LV + ".pak", LV + "-phys.pak"], files   # (+ the ivy-float edits' -detail pak)
src = os.path.join(work, "src")
assert le.verify_phys(os.path.join(src, LV + "-phys.pak"), os.path.join(out, LV + "-phys.pak"), edits, log=lambda *a: None)
assert le.verify_render(os.path.join(src, LV + ".pak"), os.path.join(out, LV + ".pak"), log=lambda *a: None)
maplv = le.map_levels("wilds-houses")
before = le.clearance(edits[0], maplv, work, out, after=False)
after = le.clearance(edits[0], maplv, work, out, after=True)
assert len(before) >= 10 and not after, (len(before), len(after))
# the gate triangles are gone, nothing else: 32 triangles, same total otherwise
a_items, b_items = le.phys_items(os.path.join(src, LV + "-phys.pak"))[1], le.phys_items(os.path.join(out, LV + "-phys.pak"))[1]
cnt = [(len(le.hc.triangles(x.mesh)[0]), len(le.hc.triangles(y.mesh)[0])) for x, y in zip(a_items, b_items)]
assert sum(a - b for a, b in cnt) == 32 and sum(1 for a, b in cnt if a != b) == 1, cnt
assert all(y.tsz <= x.tsz for x, y in zip(a_items, b_items))
# identity edit (nothing dropped) re-encodes every item byte for byte
for it in a_items:
    m2, km, ch = le.remove_keys(it.mesh, [])
    assert le.hc.encode_t2(m2, it.tag) == it.raw
print("level_edit part 2a (remove) OK")

# rotate 90 deg about the hinge, twice: in place (default: same keys, same tagfile size) and the old remove + re-add
# path ("inplace": false: new sections, the page grew).  Both: the 32 triangles come back rotated, tags / material bits kept.
def bits3(blob, key):
    b = np.unpackbits(np.frombuffer(blob, np.uint8), bitorder="little")
    return int(b[3 * key]) | int(b[3 * key + 1]) << 1 | int(b[3 * key + 2]) << 2


for inplace in (True, False):
    rot = [dict(edits[0], action="rotate", angle=90, pivot="hinge", collision=dict(edits[0].get("collision") or {}, inplace=inplace))]
    rot[0].pop("clear")
    out2 = os.path.join(work, "out2-%s" % inplace)
    le.build_edits(rot, work, out2, log=lambda *a: None)
    assert le.verify_phys(os.path.join(src, LV + "-phys.pak"), os.path.join(out2, LV + "-phys.pak"), rot, log=lambda *a: None)
    plans = le.plan_edits(rot, le.ndpak.Pak(os.path.join(src, LV + ".pak")), os.path.join(src, LV + "-phys.pak"))
    pv = plans[0]["pivot"]
    (k, (keys, T0)), = plans[0]["collision"].items()
    want = np.array([le.transform_point(t, "rotate", pivot=pv, angle=90) for t in T0])
    nb = le.phys_items(os.path.join(out2, LV + "-phys.pak"))[1][k]
    kk, TT, gg = le.hc.triangles(nb.mesh)
    if inplace:
        sel = np.isin(kk, keys)
        assert nb.tsz == a_items[k].tsz and len(nb.mesh.sections) == len(a_items[k].mesh.sections)
    else:
        sel = np.array([x >> 8 >= len(a_items[k].mesh.sections) for x in kk])
    got = TT[sel]
    assert len(got) == len(want) == 32, (inplace, len(got), len(want))
    tol = 3e-4          # shared vertices are quantised over the 100 m domain (2^21 steps)
    for t in want:
        assert min(np.abs(g - t).max() for g in got) < tol
    # per-triangle attributes follow the triangles: 3-bit material table, interior bit, shape tag
    newkeys = kk[sel]
    for i, t in enumerate(want):
        j = int(np.argmin([np.abs(g - t).max() for g in got]))
        assert bits3(nb.blob, int(newkeys[j])) == bits3(a_items[k].blob, int(keys[i]))
        assert le._bits(nb.mesh.words, 32 * len(nb.mesh.words))[int(newkeys[j])] == le._bits(a_items[k].mesh.words, 32 * len(a_items[k].mesh.words))[int(keys[i])]
    tags_old = sorted(le.hc.triangles(a_items[k].mesh)[2][np.isin(le.hc.triangles(a_items[k].mesh)[0], keys)].tolist())
    assert sorted(gg[sel].tolist()) == tags_old
    # every other triangle unchanged
    ka_, Ta_, _ = le.hc.triangles(a_items[k].mesh)
    pos_b = {int(x): t for x, t in zip(kk, TT)}
    if inplace:
        assert all(np.abs(pos_b[int(x)] - t).max() < 1e-6 for x, t in zip(ka_, Ta_) if int(x) not in set(int(y) for y in keys))
print("level_edit part 2b (rotate) OK")

# ---------------------------------------------------------------- part 2c: Into the City (world-flooded-city / ellie-flashback-ultimatum)
# explicit render offsets, oriented-box collision (obb_of), world-space decal cut, no emptied collision sections
mk = [m for m in spec["maps"] if m["key"] == "into-the-city"]
if mk and any("ultimatum" in a or "flooded" in a for a in map(os.path.basename, le.world_archives())):
    ed = mk[0]["edits"]
    assert any((e.get("collision") or {}).get("tags") for e in ed) and any((e.get("render") or {}).get("offsets") for e in ed)
    work2 = tempfile.mkdtemp()
    out3 = os.path.join(work2, "out")
    files3 = le.build_edits(ed, work2, out3, log=lambda *a: None)
    names3 = sorted(os.path.basename(f) for f in files3)
    assert names3 == ["flo-into-the-city-low-phys.pak", "flo-into-the-city-low.pak", "flo-into-the-city-phys.pak", "flo-into-the-city.pak"], names3   # truck back, LOD store interior cut
    s3 = os.path.join(work2, "src")
    L3 = "flo-into-the-city"
    assert le.verify_phys(os.path.join(s3, L3 + "-phys.pak"), os.path.join(out3, L3 + "-phys.pak"), ed, log=lambda *a: None)
    assert le.verify_render(os.path.join(s3, L3 + ".pak"), os.path.join(out3, L3 + ".pak"), log=lambda *a: None)
    assert le.verify_render(os.path.join(s3, L3 + "-low.pak"), os.path.join(out3, L3 + "-low.pak"), log=lambda *a: None)
    a3, b3 = le.phys_items(os.path.join(s3, L3 + "-phys.pak"))[1], le.phys_items(os.path.join(out3, L3 + "-phys.pak"))[1]
    gone = {k: len(le.hc.triangles(x.mesh)[0]) - len(le.hc.triangles(y.mesh)[0]) for k, (x, y) in enumerate(zip(a3, b3))}
    gone = {k: v for k, v in gone.items() if v}
    assert gone == {7: 88}, gone                          # the street door's barricade planks (tag 65); the truck stays
    L4 = L3 + "-low"
    assert le.verify_phys(os.path.join(s3, L4 + "-phys.pak"), os.path.join(out3, L4 + "-phys.pak"), [e for e in ed if e["level"] == L4], log=lambda *a: None)
    a4, b4 = le.phys_items(os.path.join(s3, L4 + "-phys.pak"))[1], le.phys_items(os.path.join(out3, L4 + "-phys.pak"))[1]
    T4 = le.hc.triangles(b4[0].mesh)[1]
    c4 = T4.mean(1)
    assert not ((c4[:, 0] > 359) & (c4[:, 0] < 376) & (c4[:, 2] > 493) & (c4[:, 2] < 510)).any()   # no LOD floor over the pit
    assert all(len(y.mesh.sections) == len(x.mesh.sections) and not getattr(y.mesh, "_dead_sections", None) for x, y in zip(a3, b3))
    mlv = le.map_levels("into-the-city")
    for e in ed:
        if e.get("clear"):
            assert le.clearance(e, mlv, work2, out3, after=False) and not le.clearance(e, mlv, work2, out3, after=True), e["name"]
    print("level_edit part 2c (into-the-city: door barricade, LOD floor over the pit) OK")

# ---------------------------------------------------------------- part 2d: strip_parts (Capitol Hill garage door floor rails)
mk = [m for m in spec["maps"] if m["key"] == "capitol-shops"]
if mk:
    sp = [e for e in mk[0]["edits"] if e["action"] == "strip_parts"]
    assert len(sp) == 1 and sp[0]["parts"] == ["game5"] and sp[0]["render"]["offsets"] == ["0x39bb40"]
    try:
        work4 = tempfile.mkdtemp()
        out4 = os.path.join(work4, "out")
        le.build_edits(sp, work4, out4, log=lambda *a: None)
    except SystemExit as ex:
        print("skip part 2d:", ex)
    else:
        L5 = sp[0]["level"]
        sa, sb = os.path.join(work4, "src", L5 + ".pak"), os.path.join(out4, L5 + ".pak")
        assert le.verify_render(sa, sb, log=lambda *a: None)
        pa5, pb5 = le.ndpak.Pak(sa), le.ndpak.Pak(sb)
        assert os.path.getsize(sa) == os.path.getsize(sb)
        it5 = [i for i in le.find_instances(pa5) if i.pak_off == 0x39bb40][0]
        n_rail = 0
        for si in sorted(set(it5.subs) | {i for _, ids in it5.names for i in ids}):
            nm = pa5.submeshes[si]["name"]
            ta = le.submesh_tris(pa5, si)
            tb = le.submesh_tris(pb5, si)
            area = lambda T: 0.5 * np.linalg.norm(np.cross(T[:, 1] - T[:, 0], T[:, 2] - T[:, 0]), axis=1)
            if "game5" in nm:                              # the two floor rails: every triangle gone
                n_rail += len(ta)
                assert len(ta) and area(tb).max() == 0.0, nm
            else:                                          # slats / frame / header box: untouched
                assert np.array_equal(ta, tb), nm
        assert n_rail == 28, n_rail                        # LOD0 22 + LOD1 6
        print("level_edit part 2d (strip_parts: garage door rails degenerate, rest of the door untouched) OK")

# Scene Editor Morph / Detach (tools/maps/level_morph.py): its own test file, run as part of this one
import runpy  # noqa: E402
runpy.run_path(os.path.join(HERE, "test_level_morph.py"), run_name="test_level_morph")

# ---------------------------------------------------------------- part 3: Bookstore garage door (cut_index)
# The garage door in front of one of the spawns is removed - the rolling door is submesh 243 of hun-checkpoint-bookstore-rear and 292 of
# hun-alley-courtyard (converted Part I paks have no submesh names, so the spec cuts by index).  The spec part needs no game files.
_maps = json.load(open(os.path.join(TOOLS, "maps", "sp_maps.json"), encoding="utf-8"))["maps"]
_bk = [m for m in _maps if m["key"] == "p1-bookstore"][0]
_gd = {e["level"]: e for e in _bk["edits"] if "garage door" in e["name"]}
assert {k: v["render"]["cut_index"] for k, v in _gd.items()} == {"hun-checkpoint-bookstore-rear": [243], "hun-alley-courtyard": [292]}, _gd
for _e in _gd.values():
    assert _e["action"] == "remove" and _e["render"]["world"] and _e["render"]["instances"] is False and _e["collision"]["mode"] == "inside"
    assert _e["box"][3] - _e["box"][0] < 1.0 and _e["box"][5] - _e["box"][2] < 7.0          # the door only (0.5 m thick, 6 m wide), never the wall around it
_conv = os.environ.get("T2R_P1_CONV") or os.path.join(os.path.dirname(os.path.dirname(HERE)), "re", "part1", "x", "conv-abi-mix4")
if os.path.exists(os.path.join(_conv, "hun-checkpoint-bookstore-rear.pak")):
    import ndpak  # noqa: E402
    sys.path.insert(0, os.path.join(TOOLS, "models"))
    for _lv, _e in _gd.items():
        _p = ndpak.Pak(os.path.join(_conv, _lv + ".pak"))
        _i = _e["render"]["cut_index"][0]
        _cut = le.world_cut(_p, _e["box"], "inside", None, None, None, None, hide=[], index=[_i])
        assert list(_cut) == [_i] and len(_cut[_i]) == _p.submeshes[_i]["icount"] // 3, (_lv, {k: len(v) for k, v in _cut.items()})
    print("garage door cut_index: ok")
