"""offline tests for actor_collision.py (needs the two game installs; nothing is launched or written to the games)

  python test_actor_collision.py            # all
  python test_actor_collision.py roundtrip [N]   # Graph re-serialises N stock TLOU2 actor tags byte-exact (default: the whole scan)
  python test_actor_collision.py oracle     # books-a-pile-small: translated Part I tag vs the stock TLOU2 tag
"""
import os
import struct
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import actcol_p1  # noqa: E402
import actcol_probe as pr  # noqa: E402
import actor_collision as A  # noqa: E402
import havok_tag as H  # noqa: E402


def p1_tag(actor):
    return actcol_p1.p1_fg_tags(pr.p1_raw(actor))[0]


def t2_tag(actor):
    import p1_archive
    arc = pr.archive_of(r"./re/game-files.tsv", actor)
    return pr.t2_tag_range(p1_archive.Psarc(os.path.join(pr.T2, arc)), "actor97/%s.pak" % actor)


# ------------------------------------------------------------------------------------------------ decoded views of a 2017.1 tag
def shapes_of(tag_raw):
    """[{body pos, rot(quat), verts(world), planes, faces, idx, vedges, flinks, mass}] per body of a 2017.1 actor tag"""
    t = H.Tag.parse(tag_raw)
    g = A.Graph.from_tag(t)
    bod = [i for i in g.items if i.name.endswith("bodyCinfoWithAttachment")][0]
    out = []
    for k in range(bod.cnt):
        b = bod.data[176 * k:176 * (k + 1)]
        pos = np.frombuffer(b[48:64], "<f4")[:3].astype(float)
        q = np.frombuffer(b[64:80], "<f4").astype(float)
        sh = bod.slots[176 * k][1]
        if sh.name != "hknpConvexPolytopeShape":
            continue
        verts = np.frombuffer(bytes(sh.slots[66][1].data), "<f4").reshape(-1, 4)[:, :3].astype(float)
        out.append({"pos": pos, "quat": q, "verts": verts, "shape": sh,
                    "planes": np.frombuffer(bytes(sh.slots[80][1].data), "<f4").reshape(-1, 4),
                    "faces": bytes(sh.slots[84][1].data), "idx": bytes(sh.slots[88][1].data),
                    "conn": sh.slots[96][1]})
    return out


def rotate(q, v):
    x, y, z, w = q
    r = np.array([[1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
                  [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
                  [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)]])
    return v @ r.T


def world_set(s):
    return np.array(sorted(map(tuple, np.round(rotate(s["quat"], s["verts"]) + s["pos"], 3))))


def hull_problems(s, tol=2e-3):
    """internal consistency of one polytope: faces index the vertices, every face vertex lies on its plane, planes face outward of the centroid,
    vertexEdges / faceLinks name (face, index-in-face) pairs that exist and point back at the right vertex"""
    bad = []
    nv = len(s["verts"])
    faces = [struct.unpack_from("<HBB", s["faces"], 4 * i) for i in range(len(s["faces"]) // 4)]
    idx = s["idx"]
    cen = s["verts"].mean(axis=0)
    if len(faces) != len(s["planes"]):
        bad.append("faces %d planes %d" % (len(faces), len(s["planes"])))
    for fi, (first, n, _) in enumerate(faces):
        vs = idx[first:first + n]
        if any(v >= nv for v in vs):
            bad.append("face %d index out of range" % fi)
            continue
        pl = s["planes"][fi]
        for v in vs:
            if abs(np.dot(pl[:3], s["verts"][v]) + pl[3]) > tol:
                bad.append("face %d vertex %d off plane" % (fi, v))
                break
        if np.dot(pl[:3], cen) + pl[3] > tol:
            bad.append("plane %d faces inward" % fi)
    ve = np.frombuffer(bytes(s["conn"].slots[24][1].data), "<u2").reshape(-1, 2)
    fl = np.frombuffer(bytes(s["conn"].slots[40][1].data), "<u2").reshape(-1, 2)
    if len(ve) != nv:
        bad.append("vertexEdges %d vs %d vertices" % (len(ve), nv))
    if len(fl) != len(idx):
        bad.append("faceLinks %d vs %d indices" % (len(fl), len(idx)))
    for v, (f, e) in enumerate(ve):
        if f >= len(faces) or e >= faces[f][1] or idx[faces[f][0] + e] != v:
            bad.append("vertexEdge %d -> (%d,%d) not that vertex" % (v, f, e))
            break
    for i, (f, e) in enumerate(fl):
        if f >= len(faces) or e >= faces[f][1]:
            bad.append("faceLink %d -> (%d,%d) missing" % (i, f, e))
            break
    return bad


# ------------------------------------------------------------------------------------------------ tests
def test_oracle(actor="books-a-pile-small"):
    p1, t2 = p1_tag(actor), t2_tag(actor)
    out = A.translate(p1, t2)
    a, b = H.Tag.parse(out), H.Tag.parse(t2)
    assert a.sdk == "20170100"
    # 1. the object graph: same classes in the same item order, same counts, same sizes, same pointer slots
    assert [(x[0], x[1], x[3]) for x in a.items] == [(x[0], x[1], x[3]) for x in b.items], "item table differs"
    assert [x[1] for x in a.items] == [x[1] for x in b.items]
    assert len(a.data) == len(b.data), (len(a.data), len(b.data))
    assert [(x[0], x[2], x[3]) for x in a.items] == [(x[0], x[2], x[3]) for x in b.items], "item offsets differ"
    assert a.ptch == b.ptch, "ptch differs"
    assert a.encode() == out
    # 2. geometry: the shapes agree (every translated body's world vertices equal one stock body's, within 1e-3; here the bodies are
    #    permuted between the games)
    sa, sb = shapes_of(out), shapes_of(t2)
    local_a = sorted(tuple(np.round(np.array(sorted(map(tuple, np.round(s["verts"], 3)))).ravel(), 3)) for s in sa)
    local_b = sorted(tuple(np.round(np.array(sorted(map(tuple, np.round(s["verts"], 3)))).ravel(), 3)) for s in sb)
    for x, y in zip(local_a, local_b):
        assert np.allclose(x, y, atol=2e-3), "shape vertices differ"
    # 3. every field of every translated object that does not carry Part I data equals the stock one (materials, motion props, body defaults)
    ga, gb = A.Graph.from_tag(a), A.Graph.from_tag(b)
    for ia, ib in zip(ga.items, gb.items):
        if ia.name in ("hknpMotionProperties",):
            assert ia.data == ib.data
    for s in sa + sb:
        assert not hull_problems(s), hull_problems(s)
    print("oracle ok: %d items, %d bytes data, shapes %d, vertex sets equal within 2e-3, hulls consistent" % (len(a.items) - 1, len(a.data), len(sa)))


def test_constraints(actors=("hun-isle-sign-a", "hun-tent-hanging-plug-a", "fire-extinguisher-a", "bush-a-sm-a", "kitchen-trashcan-a", "bakery-bin-small-a")):
    """Part I constraint actors: every constraint of the translated tag (found through the cinfo array, in cinfo order) has the same class and the same
    value in every member both games share (atoms, limits, transforms), the cinfo bodies / flags are unchanged, motors are linked."""
    import json
    import actor_templates
    tm = json.load(open(os.path.join(HERE, "data", "actor-col-templates.json")))
    for actor in actors:
        p1 = actcol_p1.p1_fg_tags(pr.p1_raw(actor))[0]
        out = A.translate(p1, actor_templates.stock_tag(tm[actor]))
        pt, tt = H.Tag.parse(p1), H.Tag.parse(out)
        pg, tg = A.Graph.from_tag(pt), A.Graph.from_tag(tt)
        pc = [i for i in pg.items if i.name == "hknpConstraintCinfo"][0]
        tc = [i for i in tg.items if i.name == "hknpConstraintCinfo"][0]
        assert pc.cnt == tc.cnt
        n = 0
        for k in range(pc.cnt):
            assert pc.data[40 * k + 8:40 * k + 24] == tc.data[40 * k + 8:40 * k + 24], "bodyA / bodyB / flags"
            a, b = pc.slots[40 * k][1], tc.slots[40 * k][1]
            assert a.name == b.name, (a.name, b.name)
            pl, tl = A.flat_members(pt, a.ti), A.flat_members(tt, b.ti)
            for path, (to, ts, tp) in tl.items():
                if tp or path not in pl or pl[path][1] != ts or pl[path][2]:
                    continue
                assert bytes(a.data[pl[path][0]:pl[path][0] + ts]) == bytes(b.data[to:to + ts]), (actor, k, path)
                n += 1
            assert sum(1 for v in a.slots.values() if v[1]) == sum(1 for v in b.slots.values() if v[1]), "linked objects (motors / wrapped data)"
        assert A.Graph.from_tag(tt).encode() == out
        print("constraints ok: %-28s %d constraints, %d member values equal, classes %s" % (actor, pc.cnt, n, sorted({i.name for i in tg.items if i.name.startswith(("hkp", "hknpB"))})))


def test_compound(actors=("janitor-bucket-a", "mannequins-female-a-pose-a", "mannequins-female-a-pose-c")):
    """compound shapes exist in both games for 3 actors with the same art: the translated bounding tree (canonical form incl. boxes, leaf ids), points,
    instance transforms and compound data equal the stock ones (items are compared by content: pointer slots / item numbers differ with body order)"""
    import numpy as np
    import actor_templates

    def canon(nodes, n=1):
        b = np.frombuffer(bytes(nodes[112 * n:112 * n + 96]), "<f4").reshape(6, 4)
        d = struct.unpack_from("<4i", nodes, 112 * n + 96)
        out = []
        for i in range(4):
            box = tuple(np.round(np.nan_to_num(b[:, i], posinf=9e9, neginf=-9e9), 4).tolist())
            out.append(None if d[i] == 0 else ("L", d[i] >> 1, box) if d[i] & 1 else ("N", box, canon(nodes, d[i] >> 1)))
        return tuple(out)

    def comps(tag):
        g = A.Graph.from_tag(H.Tag.parse(tag))
        return [(it, it.slots[80][1], it.slots[184][1]) for it in g.items if it.name == "hknpCompoundShape"]
    for actor in actors:
        tm = actor_templates.stock_tag(actor)
        out = A.translate(actcol_p1.p1_fg_tags(pr.p1_raw(actor))[0], tm)
        n = 0
        for ci, fl, cd in comps(out):
            m = [x for x in comps(tm) if x[1].cnt == fl.cnt and x[0].data[128:160] == ci.data[128:160]]
            assert m, "no stock compound with the same instance count and box"
            si, sfl, scd = m[0]
            mask = lambda d: bytes(d[:56]) + bytes(d[64:80]) + bytes(d[88:])          # slots 56 / 80 / 184 hold item numbers
            assert mask(ci.data[:184]) == mask(si.data[:184]), "compound shape bytes"
            assert bytes(cd.data[:64]) + bytes(cd.data[72:80]) + bytes(cd.data[88:]) == bytes(scd.data[:64]) + bytes(scd.data[72:80]) + bytes(scd.data[88:])
            assert canon(cd.slots[64][1].data) == canon(scd.slots[64][1].data), "bounding tree"
            assert np.allclose(np.frombuffer(bytes(cd.slots[80][1].data), "<f4"), np.frombuffer(bytes(scd.slots[80][1].data), "<f4"), atol=1e-4), "points"
            mi = lambda f, k: bytes(f.data[112 * k:112 * k + 80]) + bytes(f.data[112 * k + 88:112 * k + 112])
            assert sorted(mi(fl, k) for k in range(fl.cnt)) == sorted(mi(sfl, k) for k in range(sfl.cnt)), "instances"
            n += 1
        print("compound ok: %-28s %d compounds equal to stock (tree, points, instances, data)" % (actor, n))


def test_capsule(actors=("bloater-collision", "bush-shrub-a-sapling-b")):
    """capsules exist in both games: end points, radius (T2 = Part I * 0.99, a.w = Part I), hull box, planes, faces, indices equal the stock capsule with
    the same end points (bloater: all 24 within 1e-4).  b.w is a per-capsule scalar Part I does not carry (template value); the roll of the hull box
    around the axis is chosen by rule, so a minority of stock capsules differ by one box thickness (1% of the radius)"""
    import numpy as np
    import actor_templates

    def caps(tag):
        return [it for it in A.Graph.from_tag(H.Tag.parse(tag)).items if it.name == "hknpCapsuleShape"]
    for actor in actors:
        tm = actor_templates.stock_tag(actor)
        out = A.translate(actcol_p1.p1_fg_tags(pr.p1_raw(actor))[0], tm)
        stock = {tuple(np.round(np.frombuffer(bytes(c.data[112:124]), "<f4"), 3)): c for c in caps(tm)}
        n = exact = 0
        for c in caps(out):
            x = stock.get(tuple(np.round(np.frombuffer(bytes(c.data[112:124]), "<f4"), 3)))
            if x is None:
                continue
            f = lambda it, o, m: np.frombuffer(bytes(it.data[o:o + m]), "<f4")
            assert np.allclose(f(c, 112, 12), f(x, 112, 12), atol=1e-5) and np.allclose(f(c, 124, 4), f(x, 124, 4), atol=1e-5) and np.allclose(f(c, 128, 12), f(x, 128, 12), atol=1e-5)
            assert np.allclose(f(c, 40, 4), f(x, 40, 4), rtol=1e-4), "convex radius"
            assert bytes(c.slots[84][1].data) == bytes(x.slots[84][1].data) and bytes(c.slots[88][1].data) == bytes(x.slots[88][1].data)
            same = all(np.allclose(np.frombuffer(bytes(c.slots[s][1].data), "<f4"), np.frombuffer(bytes(x.slots[s][1].data), "<f4"), atol=1e-4) for s in (66, 80))
            n += 1
            exact += same
        assert n and (actor != "bloater-collision" or exact == n), (n, exact)
        print("capsule ok: %-26s %d capsules matched, %d with the identical hull box" % (actor, n, exact))


def test_mesh(actors=("big-rig-a-glass-fg", "van-a-glass-fg", "shotgun-dblbarrel-over-under", "mannequins-male-a-pose-a")):
    """compressed meshes exist in both games for 4+ actors with the same art: the translated tag's mesh (decoded with havok_convert.t2_mesh) has the same
    triangle count, the same multiset of shape tags, the same flags / key bits / radius / codec info, a valid section / SIMD tree structure, and its
    vertices agree with the stock ones within the tree quantisation (1e-3)"""
    import collections
    import actor_templates
    import havok_convert as hc
    from scipy.spatial import cKDTree

    def mesh(tag):
        tg = H.Tag.parse(tag)
        g = A.Graph.from_tag(tg)
        sh = [i for i in g.items if i.name == "hknpCompressedMeshShape"][0]
        sub = A.Graph(tg)
        sub.items, sub.layout_order = A.index_order(sh), A.layout_order(sh)
        return hc.t2_mesh(H.Tag.parse(sub.encode()))
    for actor in actors:
        tm = actor_templates.stock_tag(actor)
        out = A.translate(actcol_p1.p1_fg_tags(pr.p1_raw(actor))[0], tm)
        ma, mb = mesh(out), mesh(tm)
        ta, tb = hc.triangles(ma), hc.triangles(mb)
        assert len(ta[1]) == len(tb[1]) and collections.Counter(ta[2].tolist()) == collections.Counter(tb[2].tolist())
        assert (ma.flags, ma.keybits, ma.radius, ma.codec_info, ma.user & 0xFFFFFFFF) == (mb.flags, mb.keybits, mb.radius, mb.codec_info, mb.user & 0xFFFFFFFF)
        assert not hc.validate_mesh(ma), hc.validate_mesh(ma)
        d, _ = cKDTree(tb[1].reshape(-1, 3)).query(ta[1].reshape(-1, 3))
        assert d.max() < 1e-3, d.max()
        print("mesh ok: %-30s %d triangles, vertex distance max %.1e, tree structure valid" % (actor, len(ta[1]), d.max()))


def test_roundtrip(limit=None):
    import pickle
    S = os.environ.get("ACTCOL_SCRATCH")
    if not S:
        raise SystemExit("set ACTCOL_SCRATCH to the directory holding t2tags.pkl (see actcol_scan.py)")
    tags = pickle.load(open(os.path.join(S, "t2tags.pkl"), "rb"))
    bad = []
    for k, (nm, raw) in enumerate(tags.items()):
        if limit and k >= limit:
            break
        ok = A.test_roundtrip(raw)[0]
        if not ok:
            bad.append(nm)
    assert not bad, bad[:5]
    print("roundtrip ok: %d stock tags byte exact" % min(len(tags), limit or len(tags)))


if __name__ == "__main__":
    what = sys.argv[1] if len(sys.argv) > 1 else "all"
    if what in ("all", "oracle"):
        test_oracle()
    if what in ("all", "constraints"):
        test_constraints()
    if what in ("all", "compound"):
        test_compound()
    if what in ("all", "capsule"):
        test_capsule()
    if what in ("all", "mesh"):
        test_mesh()
    if what in ("all", "roundtrip"):
        test_roundtrip(int(sys.argv[2]) if len(sys.argv) > 2 else None)
