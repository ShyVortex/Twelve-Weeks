"""Offline checks of tools/maps/level_morph.py (Scene Editor Morph / Detach geometry edits).
Part 1 needs no game files: quaternion / transform maths and the bit-packed position stream writer (in range, shifted by whole
steps - untouched vertices bit exact -, re-scaled).
Part 2 needs the Jackson supermarket level paks in the level-edit cache (re/maps/level-edit-cache/src, filled by any `level_edit.py apply
jackson-market`): vertex flatten / translate on the snow mesh, detach of a closed render piece, loud failure for a piece that shares
vertices with the rest, collision vertex morph and collision detach on closed Havok pieces (structure validated, rigid, nothing else moves),
and the whole chain geoedit -> level_edit.build_edits (stamp reuse)."""
import json
import math
import os
import struct
import sys
import tempfile
import sys as _t2s, os as _t2o; _t2s.path.append(_t2o.path.normpath(_t2o.path.join(_t2o.path.dirname(_t2o.path.abspath(__file__)), ".."))); import t2rtmp  # noqa: E402,F401

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(TOOLS, "maps"))
import level_edit as le  # noqa: E402
import level_morph as lm  # noqa: E402
import havok_convert as hc  # noqa: E402

# ---------------------------------------------------------------- part 1
R90 = lm.quat_matrix([0, math.sin(math.pi / 4), 0, math.cos(math.pi / 4)])           # +90 deg about +Y: x -> -z (same as level_edit "rotate")
assert np.allclose(R90 @ [1, 0, 0], [0, 0, -1], atol=1e-12)
assert np.allclose(lm.quat_matrix([0, 0, 0, 2]), np.eye(3))                           # unnormalised input is normalised
f = lm.detach_fn({"pivot": [10, 0, 0], "rotation": [0, math.sin(math.pi / 4), 0, math.cos(math.pi / 4)], "translation": [0, 1, 0]})
assert np.allclose(f([[11, 0, 0]]), [[10, 1, -1]], atol=1e-12)
assert np.allclose(lm.morph_fn({"op": "flatten", "y": 3.5})([[1, 9, 2], [0, -4, 0]]), [[1, 3.5, 2], [0, 3.5, 0]])
assert np.allclose(lm.morph_fn({"op": "translate", "delta": [1, 2, 3]})([[0, 0, 0]]), [[1, 2, 3]])
try:
    lm.morph_fn({"op": "twist", "name": "x"})
    raise AssertionError("unknown op accepted")
except SystemExit:
    pass
assert lm.near_mask(np.array([[0, 0, 0.001], [5, 5, 5]]), np.array([[0, 0, 0.0]]), 0.0025).tolist() == [True, False]


class FakePak:
    """just enough of ndpak.Pak for level_morph.Sub: one submesh, one bit-packed (13/12/14) position stream"""
    def __init__(self, P, scale, off, bits=(13, 12, 14)):
        self.n = len(P)
        stride = sum(bits)
        d = bytearray(64 + (self.n * stride + 7) // 8 + 16)
        raw = np.rint((P - off) / scale).astype(np.int64)
        for v in range(self.n):
            bo = 64 * 8 + v * stride
            for c in range(3):
                lm._put_bits(d, bo, bits[c], raw[v, c])
                bo += bits[c]
        for c in range(3):
            struct.pack_into("<f", d, 32 + 4 * c, scale[c])
            struct.pack_into("<f", d, 48 + 4 * c, off[c])
        self.d = bytes(d)
        st = {"offset": 0, "buf": 64, "vcount": self.n, "size": (self.n * stride + 7) // 8, "type": 64, "bits": list(bits),
              "scale": struct.unpack_from("<4f", self.d, 32), "off": struct.unpack_from("<4f", self.d, 48)}
        self.submeshes = [{"offset": 0, "name": "x", "vcount": self.n, "streams": [st], "index": 0, "icount": 0}]

    def pos_stream(self, sm):
        return sm["streams"][0]


rng = np.random.default_rng(3)
scale = np.array([0.002, 0.002, 0.002])
off = np.array([-10.0, 5.0, 100.0])
P = off + rng.integers(0, [7000, 3000, 16000], (200, 3)) * scale
for label, delta, expect in (("in range", [0, 0.5, 0], "in range"), ("shifted", [-0.8, 0, 0], "shifted"), ("rescaled", [0, 0, 40.0], "RE-SCALED")):
    fp = FakePak(P, scale, off)
    s = lm.Sub(fp, 0, np.eye(4), None)
    ids = np.arange(0, 200, 4)
    for v in ids:
        s.moved[int(v)] = P[v] + delta
    rb = bytearray(fp.d)
    msgs = []
    s.write(rb, msgs.append)
    assert expect in msgs[0], (label, msgs)
    fp2 = FakePak.__new__(FakePak)
    fp2.d = bytes(rb)
    fp2.submeshes = [dict(fp.submeshes[0], streams=[dict(fp.submeshes[0]["streams"][0], scale=struct.unpack_from("<4f", rb, 32), off=struct.unpack_from("<4f", rb, 48))])]
    Q = le._qpos(fp2, fp2.submeshes[0])
    step = np.array(fp2.submeshes[0]["streams"][0]["scale"][:3])
    exp = P.copy()
    exp[ids] += delta
    assert (np.abs(Q - exp) <= step * 0.51 + 1e-6).all(), (label, np.abs(Q - exp).max())
    if label != "rescaled":                              # in range / shifted: untouched vertices are bit exact (the same decoded floats)
        rest = np.setdiff1d(np.arange(200), ids)
        assert np.abs(Q[rest] - le._qpos(fp, fp.submeshes[0])[rest]).max() < 1e-4, label
print("level_morph part 1 (maths, position stream writer: in range / shifted / re-scaled) OK")

# ---------------------------------------------------------------- part 2
SRC = os.environ.get("T2R_LEVEL_EDIT_SRC") or os.path.join(le.CACHE, "src")
LV = "pat-jackson-supermarket"


def part2():
    RP, PP = os.path.join(SRC, LV + ".pak"), os.path.join(SRC, LV + "-phys.pak")
    quiet = lambda *a: None
    R = lm.Render(RP)
    SNOW = "shelf_snowShape5_shader20_merged_partition0"
    everywhere = [-1e5] * 3 + [1e5] * 3
    i_snow = next(i for i in R.world_candidates(everywhere, 0) if SNOW in R.p.submeshes[i]["name"])
    s = R.sub(i_snow)
    W = s.world()
    sel = np.nonzero(W[:, 1] > np.median(W[:, 1]))[0]
    box = (W[sel].min(0) - 0.003).tolist() + (W[sel].max(0) + 0.003).tolist()
    tmp = tempfile.mkdtemp()
    p0, pos0 = lm.render_positions(RP)

    def diff(path):
        p1, pos1 = lm.render_positions(path)
        assert len(p1.submeshes) == len(p0.submeshes) and len(p1.d) == len(p0.d)
        return pos1, {i: int((np.abs(pos0[i] - pos1[i]).max(1) > 1e-5).sum()) for i in pos0 if len(pos0[i]) and (np.abs(pos0[i] - pos1[i]).max(1) > 1e-5).any()}

    def world_of(pos, i, M, n):
        return (np.concatenate([pos[i], np.ones((n, 1))], 1) @ M)[:, :3]

    # (a) flatten: exactly the selected vertices move, onto the height; the rest of the level is byte-identical
    g = {"kind": "morph", "name": "t flatten", "level": LV, "asset": "", "mesh": SNOW, "verts": [int(v) for v in sel], "check": W[sel[:6]].tolist(),
         "op": "flatten", "y": float(W[sel, 1].min()), "collision": "none", "box": box}
    out = os.path.join(tmp, "a.pak")
    assert lm.morph_level(LV, [g], RP, PP, out, os.path.join(tmp, "a-phys.pak"), quiet) == (True, False)
    pos1, ch = diff(out)
    assert set(ch) == {i_snow} and 0 < ch[i_snow] <= len(sel), ch               # (selected vertices already at the height do not change)
    w1 = world_of(pos1, i_snow, s.M, len(W))
    assert np.abs(w1[sel, 1] - g["y"]).max() < 0.0025
    assert np.abs(np.delete(w1, sel, 0) - np.delete(W, sel, 0)).max() == 0.0
    assert np.abs(w1[sel][:, [0, 2]] - W[sel][:, [0, 2]]).max() < 0.0025
    # (b) wrong check positions: refused, nothing written
    bad = dict(g, check=(W[sel[:3]] + 5).tolist())
    try:
        lm.morph_level(LV, [bad], RP, PP, os.path.join(tmp, "b.pak"), os.path.join(tmp, "b-phys.pak"), quiet)
        raise AssertionError("stale check accepted")
    except SystemExit as ex:
        assert "no submesh" in str(ex), ex
    assert not os.path.exists(os.path.join(tmp, "b.pak"))
    # (c) translate beyond the stream range: a re-scaled channel, selected vertices land, neighbours stay within one new step
    g2 = dict(g, name="t far", op="translate", delta=[0.0, 20.0, 0.0])
    out = os.path.join(tmp, "c.pak")
    lm.morph_level(LV, [g2], RP, PP, out, os.path.join(tmp, "c-phys.pak"), quiet)
    pos1, ch = diff(out)
    w1 = world_of(pos1, i_snow, s.M, len(W))
    assert np.abs(w1[sel, 1] - (W[sel, 1] + 20)).max() < 0.006 and np.abs(np.delete(w1, sel, 0) - np.delete(W, sel, 0)).max() < 0.006
    # (d) detach of a closed render piece (an index-connected part of a big merged mesh): rigid, nothing else moves; partial piece: loud failure
    BIG = "snowsShape_shader0_merged_partition0"
    i_big = next(i for i in R.world_candidates(everywhere, 0) if BIG in R.p.submeshes[i]["name"])
    sb = R.sub(i_big)
    I, live = sb.live_tris()
    up = list(range(sb.n))

    def find(a):
        while up[a] != a:
            up[a] = up[up[a]]
            a = up[a]
        return a
    for a, b, c in I[live]:
        up[find(a)] = find(b)
        up[find(a)] = find(c)
    comp = {}
    for t in range(len(I)):
        if live[t]:
            comp.setdefault(find(I[t, 0]), []).append(t)
    tris = sorted(comp.values(), key=len)[len(comp) // 2]
    Wb = sb.world()
    vs = np.unique(I[tris].ravel())
    tr = {"pivot": Wb[vs].mean(0).tolist(), "rotation": [0, math.sin(math.radians(20)), 0, math.cos(math.radians(20))], "translation": [1.0, 0.5, -0.7]}
    gd = {"kind": "detach", "name": "t detach", "level": LV, "asset": "", "mesh": BIG, "tris": [int(t) for t in tris],
          "check": Wb[vs[:6]].tolist(), "transform": tr, "collision": "none", "box": (Wb[vs].min(0) - 0.02).tolist() + (Wb[vs].max(0) + 0.02).tolist()}
    out = os.path.join(tmp, "d.pak")
    lm.morph_level(LV, [gd], RP, PP, out, os.path.join(tmp, "d-phys.pak"), quiet)
    pos1, ch = diff(out)
    assert i_big in ch, ch
    w1 = world_of(pos1, i_big, sb.M, sb.n)
    assert np.abs(w1[vs] - lm.detach_fn(tr)(Wb[vs])).max() < 0.004
    oth = np.setdiff1d(np.arange(sb.n), vs)
    assert np.abs(w1[oth] - Wb[oth]).max() == 0.0
    assert np.linalg.norm(lm.detach_fn(tr)(Wb[vs]) - Wb[vs], axis=1).min() > 0.3      # the rigid piece really moved
    gp = dict(gd, name="t partial", tris=[int(t) for t in tris[:len(tris) // 2]])
    try:
        lm.morph_level(LV, [gp], RP, PP, os.path.join(tmp, "e.pak"), os.path.join(tmp, "e-phys.pak"), quiet)
        raise AssertionError("partial piece accepted without free vertex slots")
    except SystemExit as ex:
        assert "free vertex slots" in str(ex), ex
    # (e) collision: vertex morph by position keeps every key / tag and moves exactly those vertices; detach of a closed piece is rigid
    pp, items = le.phys_items(PP)
    base_bad = [(len(hc.validate_mesh(it.mesh)), sum(le.check_tree4(it.mesh, 5e-4).values())) for it in items]
    k = 1
    ka, Ta, ga = hc.triangles(items[k].mesh)
    sec = [i for i, x in enumerate(ka) if int(x) >> 8 in (5, 6)]
    pts = np.unique(Ta[sec].reshape(-1, 3).round(5), axis=0)
    buf = bytearray(pp.d)
    buf, nv = lm.apply_morph_phys(items, buf, {"name": "pm", "collision": "match", "op": "translate", "delta": [0, 0.3, 0], "box": [0] * 6}, pts, quiet)
    assert nv >= len(pts)
    outp = os.path.join(tmp, "m-phys.pak")
    open(outp, "wb").write(bytes(buf))
    pp2, it2 = le.phys_items(outp)
    assert len(buf) == len(pp.d)
    for kk, x in enumerate(it2):
        assert (len(hc.validate_mesh(x.mesh)), sum(le.check_tree4(x.mesh, 5e-4).values())) == base_bad[kk], kk
    ka2, Ta2, ga2 = hc.triangles(it2[k].mesh)
    assert (ka == ka2).all() and (ga == ga2).all()
    from scipy.spatial import cKDTree
    on = np.isfinite(cKDTree(pts).query(Ta.reshape(-1, 3), distance_upper_bound=0.004)[0])
    dd = (Ta2 - Ta).reshape(-1, 3)
    assert np.abs(dd[on] - [0, 0.3, 0]).max() < 1e-4 and np.abs(dd[~on]).max() == 0.0
    tested = 0
    for k, it in enumerate(items):                       # detach of a closed collision piece (a vertex-connected part, 20..300 triangles)
        ka, Ta, ga = hc.triangles(it.mesh)
        Pq = np.round(Ta.reshape(-1, 3), 4)
        u, inv = np.unique(Pq, axis=0, return_inverse=True)
        inv = inv.reshape(-1, 3)
        up[:] = list(range(len(u)))
        comp = {}
        for a, b, c in inv:
            up[find(a)] = find(b)
            up[find(a)] = find(c)
        for t in range(len(ka)):
            comp.setdefault(find(inv[t, 0]), []).append(t)
        for tl in comp.values():
            if not 20 <= len(tl) <= 300:
                continue
            lo, hi = Ta[tl].reshape(-1, 3).min(0) - 0.003, Ta[tl].reshape(-1, 3).max(0) + 0.003
            if len(le._tri_sel(it.mesh, lo.tolist() + hi.tolist(), None, "inside")[0]) != len(tl):
                continue
            tr = {"pivot": ((lo + hi) / 2).tolist(), "rotation": [0, math.sin(math.radians(12)), 0, math.cos(math.radians(12))], "translation": [0.05, 0.02, 0.04]}
            buf = bytearray(pp.d)
            buf, nt = lm.apply_detach_phys(items, buf, {"name": "dc", "items": [k], "collision": "inside", "transform": tr, "box": lo.tolist() + hi.tolist()}, quiet)
            outp = os.path.join(tmp, "dc-phys.pak")
            open(outp, "wb").write(bytes(buf))
            it3 = le.phys_items(outp)[1][k]
            assert (len(hc.validate_mesh(it3.mesh)), sum(le.check_tree4(it3.mesh, 5e-4).values())) == base_bad[k]
            ka3, Ta3, ga3 = hc.triangles(it3.mesh)
            assert (ka == ka3).all() and (ga == ga3).all() and nt == len(tl)
            exp = lm.detach_fn(tr)(Ta[tl].reshape(-1, 3)).reshape(-1, 3, 3)
            assert np.abs(Ta3[tl] - exp).max() < 1e-4
            assert int((np.abs(Ta3 - Ta).max((1, 2)) > 1e-4).sum()) == len(tl)
            tested += 1
            break
        if tested >= 2:
            break
    assert tested, "no closed collision piece found"
    # (f) the whole chain: geoedit spec -> level_edit.build_edits, the second run is served from the stamp
    import geoedit
    spec_dir = tempfile.mkdtemp()
    json.dump({"key": "t", "edits": [g, gd]}, open(os.path.join(spec_dir, "t-geoedits.json"), "w"))
    old = geoedit.DATA
    geoedit.DATA = spec_dir
    try:
        edits = geoedit.edits_for("t")
        assert [e["action"] for e in edits] == ["morph", "detach"]
        outd = os.path.join(spec_dir, "out")
        w = le.build_edits(edits, out_dir=outd, log=quiet)
        assert [os.path.basename(x) for x in w] == [LV + ".pak"] and os.path.dirname(w[0]).endswith("morph")
        m1 = os.path.getmtime(w[0])
        assert le.build_edits(edits, out_dir=outd, log=quiet) == w and os.path.getmtime(w[0]) == m1
        pos1, ch = diff(w[0])
        assert set(ch) == {i_snow, i_big}, ch
    finally:
        geoedit.DATA = old
    # (g) snow: y = base + bank(d to the nearest wall) + rough, blended with the original height near the selection boundary
    ALLEY = "alley_snow_ground|alley|alleyShape_shader0_merged_partition0"
    i_al = next((i for i in R.world_candidates(everywhere, 0) if R.p.submeshes[i]["name"].endswith(ALLEY)), None)
    assert i_al is not None
    sa = R.sub(i_al)
    Wa = sa.world()
    sela = np.nonzero((Wa[:, 2] > 275) & (Wa[:, 2] < 284))[0]
    boxa = (Wa[sela].min(0) - 0.003).tolist() + (Wa[sela].max(0) + 0.003).tolist()
    ga = {"kind": "morph", "name": "t snow", "level": LV, "asset": "", "mesh": ALLEY, "verts": [int(v) for v in sela], "check": Wa[sela[:6]].tolist(),
          "op": "snow", "y": float(np.percentile(Wa[sela, 1], 10)), "collision": "match", "box": boxa, "bank_h": 0.22, "bank_w": 1.4, "rough": 0.08, "seed": 77}
    outs = os.path.join(tmp, "s.pak")
    outsp = os.path.join(tmp, "s-phys.pak")
    assert lm.morph_level(LV, [ga], RP, PP, outs, outsp, quiet) == (True, True)
    pos1, ch = diff(outs)
    assert i_al in ch, ch
    w1 = world_of(pos1, i_al, sa.M, len(Wa))
    unsel = np.setdiff1d(np.arange(len(Wa)), sela)
    other = {i: v for i, v in ch.items() if i != i_al}           # (shadow proxies may follow; nothing else)
    assert np.abs(w1[unsel] - Wa[unsel]).max() == 0.0, "unselected snow vertices changed"
    assert np.abs(w1[sela][:, [0, 2]] - Wa[sela][:, [0, 2]]).max() < 0.0025
    ctx = lm.snow_context(ga, items)
    assert ctx["n_wall_samples"] > 0
    bnd = lm.snow_boundary(sa, sela)
    assert len(bnd)
    from scipy.spatial import cKDTree
    dwall = ctx["walls"].query(Wa[sela][:, [0, 2]])[0]
    dbnd = cKDTree(bnd).query(Wa[sela][:, [0, 2]])[0]
    ynew = w1[sela, 1]
    inner = dbnd >= lm.SNOW_EDGE_FADE                                # fully snow-shaped vertices
    base = ga["y"]
    assert inner.sum() > 30
    # never below the picked level, never more than bank_h + rough above it
    assert (ynew[inner] >= base - 0.006).all() and (ynew[inner] <= base + 0.22 + 0.08 + 0.006).all(), (ynew[inner].min(), ynew[inner].max())
    near, far = inner & (dwall < 0.15), inner & (dwall > 0.5)
    assert near.sum() >= 5 and far.sum() >= 5, (near.sum(), far.sum())
    assert ynew[near].mean() - ynew[far].mean() > 0.05, (ynew[near].mean(), ynew[far].mean())      # higher on contact with the wall, lower in between
    # the formula (what the build writes) is what the pak holds; boundary vertices keep their height (continuity with the unedited snow)
    exp = lm.morph_fn(ga, dict(ctx, bnd=bnd))(Wa[sela])[:, 1]
    assert np.abs(exp - ynew).max() < 0.006
    onb = dbnd < 1e-6
    assert onb.any() and np.abs(ynew[onb] - Wa[sela][onb, 1]).max() < 0.006
    ramp = dbnd < 0.2
    assert np.abs(ynew[ramp] - Wa[sela][ramp, 1]).max() <= (np.abs(exp - Wa[sela, 1])[ramp].max() + 0.006)
    # determinism: the same entry builds the same bytes; another seed gives another surface; default parameters
    outs2 = os.path.join(tmp, "s2.pak")
    lm.morph_level(LV, [ga], RP, PP, outs2, os.path.join(tmp, "s2-phys.pak"), quiet)
    assert open(outs, "rb").read() == open(outs2, "rb").read()
    assert open(outsp, "rb").read() == open(os.path.join(tmp, "s2-phys.pak"), "rb").read()
    xs = np.random.default_rng(1).uniform(-509, -505, (200, 2))
    assert (lm.snow_rough(xs[:, 0], xs[:, 1], 77) == lm.snow_rough(xs[:, 0], xs[:, 1], 77)).all()
    assert np.abs(lm.snow_rough(xs[:, 0], xs[:, 1], 77) - lm.snow_rough(xs[:, 0], xs[:, 1], 78)).max() > 0.05
    r = lm.snow_rough(xs[:, 0], xs[:, 1], 77)
    assert r.min() >= 0 and r.max() <= 1
    assert lm.snow_params({"op": "snow"}) == (0.22, 1.4, 0.08)
    assert lm.snow_seed({"name": "a"}) == lm.snow_seed({"name": "a"}) != lm.snow_seed({"name": "b"})
    b = lm.snow_bank(np.array([0.0, 0.3, 0.75, 1.4, 3.0]), 0.25, 1.4)
    assert abs(b[0] - 0.25) < 1e-12 and b[3] == 0 and b[4] == 0 and (np.diff(b) <= 0).all() and (b[0] - b[1]) > (b[2] - b[3]) and b[1] < 0.25 * 0.9   # steepest at the wall, taper
    # old flatten entries behave identically (no "op" key at all, and the explicit flatten result is the same function)
    assert np.allclose(lm.morph_fn({"y": 3.5})([[1, 9, 2]]), [[1, 3.5, 2]])
    # collision follows through the same function: structure still valid
    pps, itss = le.phys_items(outsp)
    for kk, x in enumerate(itss):
        assert (len(hc.validate_mesh(x.mesh)), sum(le.check_tree4(x.mesh, 5e-4).values())) == base_bad[kk], kk
    print("level_morph part 2 (snow, flatten / translate / re-scale, stale-check refusal, closed render detach, shared-vertex refusal, collision morph + detach, geoedit chain) OK")


if os.path.exists(os.path.join(SRC, LV + ".pak")) and os.path.exists(os.path.join(SRC, LV + "-phys.pak")):
    part2()
else:
    print("skip level_morph part 2: no %s in %s" % (LV, SRC))
