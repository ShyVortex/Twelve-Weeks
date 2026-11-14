"""Scaled copies of actor paks for the spawner props whose Scale is not 1.

The game IGNORES a spawner's Scale (git 92a447ee: Capitol / Overpass window boards), the Scene Editor applies it along the prop's own axes before the
rotation (MainWindow.Unity convertprop: Matrix4x4.Decompose of S * R).  So a prop that was stretched / shrunk (a fence stretched into a wall, a gate leaf
shrunk to the pocket width) is baked here: the actor pak is copied under a new name (same length, rename_pak), every LOD's vertex positions get the scale
per local axis, the tangent frames the inverse transpose (normal / s, tangent * s), the submesh and level boxes the scale, and the Havok collision shape the
scale; the spawner then references the copy with scale 1.

  sp_maps.py pak           props -> scaled_props.map_props(props): art swapped, scale dropped
  sp_maps_build            prop_actors() lists the copies in the registry, stage_scaled() writes actor97/<copy>.pak
  python scaled_props.py <actor> <sx> <sy> <sz> <out.pak>      one copy by hand + a read-back report

What is scaled, measured on efg-outer-wall-gate-door-lf (5 submeshes, 2 joints, one hknpConvexPolytopeShape box):
  GEOMETRY_1 positions (type 64, all LODs, re-quantised in place over the new range), tangent frames (type 130), submesh AABB (+0 / +16);
  LEVEL_BOUNDING_BOX_DATA min / max (+64 / +80); COLLISION_DATA_FOREGROUND: hknpConvexPolytopeShape vertices, the body offset (hknpPhysicsSystemData
  body cinfo position), the plane offsets (recomputed from the scaled vertices); COLLISION_DATA_BACKGROUND box floats.
Not scaled: skeleton bind poses (rest pose: the joints cancel, the props are static), texture coordinates (they stretch with the surface, like in the editor),
AMBSHADOWS_OCCLUDER_INFO.  Collision shapes other than a convex polytope make bake() raise (so a prop is never shipped with an unscaled shape).
"""
import hashlib
import os
import struct
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.dirname(HERE)
for _p in (HERE, os.path.join(TOOLS, "models"), os.path.join(TOOLS, "part1")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

TOL = 1e-3


def is_scaled(p):
    s = p.get("scale")
    return bool(s) and max(abs(v - 1.0) for v in s) > TOL


def new_name(art, scale):
    """same length as `art` (rename_pak), a-z 0-9 '-', unique per (art, rounded scale)"""
    key = "%s|%.4f|%.4f|%.4f" % (art, *scale)
    h = hashlib.sha1(key.encode()).hexdigest()[:5]
    return art[:len(art) - 6] + "-" + h


_CACHE = {}


def baked(art, scale, game=None):
    """the baked actor pak bytes of (art, scale) or None when it cannot be built (a warning is printed; the prop then keeps its stock art: the game ignores Scale)"""
    key = (art, tuple(round(float(v), 4) for v in scale))
    if key not in _CACHE:
        try:
            import prop_lod
            _CACHE[key] = bake(prop_lod.stock_pak(art, game), key[1], art, new_name(art, key[1]))
        except BaseException as ex:                      # never fail a build over a prop: SystemExit (stock_pak: art not in the game) included
            if isinstance(ex, KeyboardInterrupt):
                raise
            print("  scaled_props WARNING: %s x %s not baked (%s: %s): the prop stays at its stock size" % (art, list(key[1]), type(ex).__name__, ex))
            _CACHE[key] = None
    return _CACHE[key]


def map_props(props):
    """-> (props with every scaled prop's art swapped for its baked copy and the scale dropped, {copy name: (art, scale)}); a prop that cannot be baked is left as it is"""
    out, bakes = [], {}
    for p in props:
        if not is_scaled(p):
            out.append(p)
            continue
        s = [round(float(v), 4) for v in p["scale"]]
        if baked(p["art"], s) is None:
            out.append(p)
            continue
        nn = new_name(p["art"], s)
        bakes[nn] = (p["art"], s)
        n = dict(p)
        n["art"] = nn
        n.pop("scale", None)
        out.append(n)
    return out, bakes


def _scale_items(d, p, s):
    """bounding boxes: LEVEL_BOUNDING_BOX_DATA min / max (+64 / +80, w = 1)"""
    n = 0
    for name, typ, _, o in p.items:
        if typ == "LEVEL_BOUNDING_BOX_DATA":
            for off in (64, 80):
                v = np.array(struct.unpack_from("<3f", d, o + off)) * s
                struct.pack_into("<3f", d, o + off, *v)
            n += 1
    return n


def _scale_render(d, p, s):
    import mesh_replace as mr
    done = set()
    inv = 1.0 / s
    for sm in p.submeshes:
        n = sm["vcount"]
        P = None
        for st in sm["streams"]:
            if st["type"] == mr.POS:
                P = np.array(p.decode_quantized(st, n, 3)) * s
                if st["buf"] in done:
                    continue
                raw, sc, of = mr._quantize(P, st["bits"], st["scale"], st["off"])
                payload = mr._pack_bits(raw, st["bits"])
                assert len(payload) <= st["size"], "position stream grew"
                d[st["buf"]:st["buf"] + len(payload)] = payload
                struct.pack_into("<4f", d, st["offset"] + 32, *sc)
                struct.pack_into("<4f", d, st["offset"] + 48, *of)
                done.add(st["buf"])
            elif st["type"] == mr.FRAME and st["buf"] not in done:
                recs = np.frombuffer(bytes(d[st["buf"]:st["buf"] + 4 * n]), "<u4")
                out = np.zeros(n, np.uint32)
                for v, rec in enumerate(recs):
                    tg, nm = mr._frame_decode(int(rec))
                    nm = nm * inv                                   # inverse transpose of a diagonal scale
                    tg = tg * s
                    out[v] = mr.frame_encode(tg, nm, 1.0 if rec & 0x80000000 else -1.0)
                d[st["buf"]:st["buf"] + 4 * n] = out.tobytes()
                done.add(st["buf"])
        if P is not None:
            struct.pack_into("<3f", d, sm["offset"], *P.min(0))
            struct.pack_into("<3f", d, sm["offset"] + 16, *P.max(0))


def _qmat(q):
    x, y, z, w = q
    return np.array([[1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
                     [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
                     [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)]])


def _scale_collision(d, p, s):
    """COLLISION_DATA_FOREGROUND: a Havok tagfile with N hknpConvexPolytopeShape bodies (N = 1: the gate leaves / the crate, N = 18: the window boards).  Body k
    (hknpPhysicsSystemData body cinfo, 176 bytes each: position +0x30, orientation quaternion +0x40) owns the k-th vertex array (hkVector4f) and plane array
    (hkVector4).  Actor space = R v + pos; scaled: S (R v + pos) = R v' + pos' with v' = (R^T S R) v, pos' = S pos; planes n' = normalize(M^-T n), d' from the
    scaled vertices.  COLLISION_DATA_EMPTY (no collision, void-blocker) is fine; the BACKGROUND box floats are scaled too.  -> number of shapes scaled (0 = none);
    anything this does not understand raises ValueError (bake() then ships the render-scaled copy with the stock collision and says so)."""
    import level_edit as le
    n = 0
    for name, typ, _, o in p.items:
        if typ == "COLLISION_DATA_BACKGROUND":
            f = np.frombuffer(bytes(d[o + 48:o + 48 + 12 * 4]), "<f4").copy().reshape(-1, 3)
            if len(f):
                nz = (np.abs(f).sum(1) > 0)
                f[nz] *= s
                d[o + 48:o + 48 + f.size * 4] = f.astype("<f4").tobytes()
            continue
        if typ != "COLLISION_DATA_FOREGROUND":
            continue
        b = o + 48
        tsz = struct.unpack_from("<I", d, b + 88)[0]
        t0 = bytes(d).find(b"TAG0", o) - 4
        if not (t0 > 0 and struct.unpack_from(">I", d, t0)[0] & 0x3FFFFFFF == tsz):
            raise ValueError("collision tagfile not found")
        raw = bytearray(d[t0:t0 + tsz])
        T = le.hc.havok_tag.Tag.parse(bytes(raw))
        names = ["-"] + [T.tname(it[0]) for it in T.items[1:]]
        if "hknpCompressedMeshShape" in names or not names.count("hknpConvexPolytopeShape"):
            raise ValueError("collision shapes are not convex polytopes: %s" % sorted(set(names)))
        shapes = [i for i, nm in enumerate(names) if nm == "hknpConvexPolytopeShape"]
        vs = [i for i, nm in enumerate(names) if nm == "hkVector4f"]
        ps = [i for i, nm in enumerate(names) if nm == "hkVector4"]
        bi = [i for i, nm in enumerate(names) if nm == "hknpPhysicsSystemData::bodyCinfoWithAttachment"]
        if len(vs) != len(shapes) or len(ps) != len(shapes) or len(bi) != 1 or T.items[bi[0]][3] != len(shapes):
            raise ValueError("shape / vertex / plane / body counts differ (%d %d %d %d)" % (len(shapes), len(vs), len(ps), T.items[bi[0]][3] if bi else -1))
        D = T.data
        base = bytes(raw).find(bytes(D[T.items[vs[0]][2]:T.items[vs[0]][2] + 16 * T.items[vs[0]][3]]))
        assert base >= 0 and bytes(raw).count(bytes(D[T.items[vs[0]][2]:T.items[vs[0]][2] + 16 * T.items[vs[0]][3]])) == 1, "collision data not located inside the tagfile"
        base -= T.items[vs[0]][2]
        bo, cnt = T.items[bi[0]][2], T.items[bi[0]][3]
        stride = 176
        S = np.diag(s)
        for k in range(cnt):
            ro = base + bo + k * stride
            pos = np.frombuffer(bytes(raw[ro + 0x30:ro + 0x3C]), "<f4").astype(float)
            q = np.frombuffer(bytes(raw[ro + 0x40:ro + 0x50]), "<f4").astype(float)
            if abs(np.linalg.norm(q) - 1.0) > 0.02:
                raise ValueError("body %d orientation is not a unit quaternion %s" % (k, q))
            R = _qmat(q)
            M = R.T @ S @ R
            Mit = np.linalg.inv(M).T
            raw[ro + 0x30:ro + 0x3C] = (S @ pos).astype("<f4").tobytes()
            vo, vc = T.items[vs[k]][2], T.items[vs[k]][3]
            V = np.frombuffer(bytes(raw[base + vo:base + vo + 16 * vc]), "<f4").reshape(-1, 4).copy()
            V[:, :3] = V[:, :3] @ M.T
            raw[base + vo:base + vo + 16 * vc] = V.astype("<f4").tobytes()
            po, pc = T.items[ps[k]][2], T.items[ps[k]][3]
            Pl = np.frombuffer(bytes(raw[base + po:base + po + 16 * pc]), "<f4").reshape(-1, 4).copy()
            for j in range(pc):
                nrm = Mit @ Pl[j, :3].astype(float)
                nrm /= np.linalg.norm(nrm)
                Pl[j, :3] = nrm
                Pl[j, 3] = -float((V[:, :3] @ nrm).max())
            raw[base + po:base + po + 16 * pc] = Pl.astype("<f4").tobytes()
            n += 1
        d[t0:t0 + tsz] = bytes(raw)
    return n


def bake(data, scale, art=None, name=None):
    """-> patched actor pak bytes (renamed to `name` when given)"""
    import armour_paks as AP
    import rename_pak
    s = np.array(scale, float)
    assert (s > 0).all(), "negative scale (mirroring) is not baked"
    d = bytearray(data)
    p = AP._load(data)
    _scale_render(d, p, s)
    _scale_items(d, p, s)
    d2 = bytearray(d)
    try:
        ncol = _scale_collision(d2, p, s)
        d = d2
    except (ValueError, AssertionError) as ex:
        print("  scaled_props WARNING: %s: collision NOT scaled (%s): the render-scaled copy keeps the stock collision" % (art or name, ex))
    out = bytes(d)
    if name:
        out, n = rename_pak.rename(out, art, name, items=True)
        assert n >= 2, "rename: %d names" % n
    return out


def stage(stage_dir, bakes, game=None, log=print):
    """write actor97/<copy>.pak for every {copy: (art, scale)}; -> manifest paths"""
    import prop_lod
    os.makedirs(os.path.join(stage_dir, "actor97"), exist_ok=True)
    out = []
    for nn, (art, s) in sorted(bakes.items()):
        data = baked(art, s, game)
        if data is None:
            continue
        open(os.path.join(stage_dir, "actor97", nn + ".pak"), "wb").write(data)
        log("  scaled prop copy %s = %s x %s" % (nn, art, s))
        out.append("actor97/%s.pak" % nn)
    return out


def report(path):
    """read-back: LOD0 position box + collision box of a (baked) actor pak"""
    import armour_paks as AP
    import level_edit as le
    data = open(path, "rb").read()
    p = AP._load(data)
    lo = np.min([p.positions(sm).min(0) for sm in p.submeshes], 0)
    hi = np.max([p.positions(sm).max(0) for sm in p.submeshes], 0)
    print("render box", lo.round(3).tolist(), hi.round(3).tolist())
    for name, typ, _, o in p.items:
        if typ == "COLLISION_DATA_FOREGROUND":
            t0 = data.find(b"TAG0", o) - 4
            tsz = struct.unpack_from("<I", data, o + 48 + 88)[0]
            T = le.hc.havok_tag.Tag.parse(data[t0:t0 + tsz])
            nms = ["-"] + [T.tname(it[0]) for it in T.items[1:]]
            iv = nms.index("hkVector4f")
            vo, vc = T.items[iv][2], T.items[iv][3]
            V = np.frombuffer(bytes(T.data[vo:vo + 16 * vc]), "<f4").reshape(-1, 4)[:, :3]
            ib = nms.index("hknpPhysicsSystemData::bodyCinfoWithAttachment")
            pos = np.frombuffer(bytes(T.data[T.items[ib][2] + 0x30:T.items[ib][2] + 0x3C]), "<f4")
            print("collision box", (pos + V.min(0)).round(3).tolist(), (pos + V.max(0)).round(3).tolist())


if __name__ == "__main__":
    a = sys.argv[1:]
    if len(a) != 5:
        print(__doc__)
        sys.exit(1)
    import prop_lod
    art, sc, out = a[0], [float(v) for v in a[1:4]], a[4]
    nn = new_name(art, sc)
    open(out, "wb").write(bake(prop_lod.stock_pak(art), sc, art, nn))
    print(nn)
    report(out)
