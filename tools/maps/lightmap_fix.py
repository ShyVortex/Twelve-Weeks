"""Baked-lightmap repair for removed / moved level geometry (winter Supermarket jackson-market: "dark patches" on the post-office walls
where we lowered the snow, on the snow where trash / walls stood, on the hall floor under removed shelves).

Cause (measured, re/maps/darkfix/README.md): every charted BG surface reads its baked lighting from the level's nova lightmap atlas
(basis1_lightColor / basis1_baseColor BC6H, basis1_lightDir / bentNormal BC7) through a PER-PLACEMENT UV2 stream (lightmap_atlas.py).  The atlas was baked
with the stock geometry, so texels that were buried under the stock snow or under / inside a prop are black (lightColor = baseColor = 0,
bentNormal cone closed).  Our edits expose them: the black texels become visible = the dark patches.

Repair (build step, after level_edit's edits + morphs + the ghost-proxy sweep, cached):
  1. G = "gone" triangles: every stock render triangle (all written levels, shadow proxies excluded) that the shipped paks no longer draw at that
     place (hidden placements, cut triangles, morphed vertices: the OLD position).
  2. texels: every atlas texel of every charted draw item (shipped positions) within REACH of G, with its world point and face normal.
  3. invalid weight per texel: buried (a vertical ray up from the texel hits a near-horizontal G triangle within BURY m: under the old snow / a removed
     prop) -> 1; else the fraction of 32 cosine-weighted hemisphere rays (length HEMI) that hit G, ramped 0.15 -> 0.5.  A texel's own draw item
     (same placement + submesh) is never its own occluder, so lowered snow does not 'bury' itself.
  4. fill: invalid texels get the normal-aware, distance-weighted mean of the valid (weight 0) texels around them in WORLD space (any chart: the lit
     wall band above the old snow line, the snow / floor ring around a footprint); new = lerp(old, fill, weight).  All four atlas layers alike.
  5. gutter texels (no chart) within 2 px of a changed texel follow (bilinear filtering reads them); changed 4x4 blocks are re-encoded (bc6h.py mode
     11 / mp_snow_pak.bc7_blocks mode 6), every other block keeps its bytes.
  6. the repaired full-res atlas is injected into the level pak (VRAM payload appended, descriptor w / h / size / offset, hash + 1 = no texture-dict
     entry wins; the same layout pak_editor_cli inject-texture writes, BC6H included).  Levels whose atlas is not in the MP-mounted dicts (alley:
     world-patrol.psarc, MP drew its 64x64 stub) get their full-res atlas this way too.
CLI:  python lightmap_fix.py run <out dir> [--src <stock dir>] [--png DIR]     (offline unit run on a level-edit output dir, writes <out>/lmfix/)
Env:  T2R_NO_LIGHTMAP_FIX=1 skips the build step."""
import hashlib
import json
import os
import struct
import sys
import time

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "models"))
import level_edit as le  # noqa: E402
import ndpak  # noqa: E402
import lightmap_atlas as la  # noqa: E402
import probe_fix  # noqa: E402

VERSION = 43          # 43: probe floor for every black probe (probe_fix v2).  42: + reflection-probe cubemap brightening (probe_fix.py: the lane / hall probes were black = black character ambient)
REACH = 2.5          # texels farther than this from every gone triangle are never touched
BURY = 2.5           # vertical reach of the buried test
HEMI = 1.0           # hemisphere ray length
NDIR = 32
FILL_R = 2.5         # source search radius (m)
FILL_S = 0.45        # distance falloff (m)
FILL_FAR = 10.0      # last pass: a whole wall behind a removed wall / deep under a long snow bank
TRAILER_LIMIT = 1 << 27


# ------------------------------------------------------------------------------------------------ geometry
def _item_world(p, it, i):
    sm = p.submeshes[i]
    P = le._qpos(p, sm)
    if P is None or not sm["icount"]:
        return None, None
    I = np.array(p.indices(sm), np.int64).reshape(-1, 3)
    W = (np.c_[P, np.ones(len(P))] @ it.M)[:, :3] if it is not None else P
    if it is not None and np.linalg.det(it.M[:3, :3]) < 0:
        I = I[:, [0, 2, 1]]
    return W, I


def _is_shadow(p, i):
    return "shadow" in p.submeshes[i]["name"].lower()


def _stream_bytes(p, i):
    sm = p.submeshes[i]
    st = p.pos_stream(sm)
    pos = bytes(p.d[st["buf"]:st["buf"] + st["size"]]) if st and st["size"] else b""
    return pos + bytes(p.d[sm["index"]:sm["index"] + 2 * sm["icount"]]) + bytes(p.d[st["offset"]:st["offset"] + 64] if st else b"")


def gone_triangles(lv, ship, stock):
    """stock render triangles the shipped pak no longer draws where they were -> (T (n,3,3), owner keys [(lv, rec, sub)], per-tri owner index)"""
    si = {it.pak_off: it for it in le.find_instances(stock)}
    hi = {it.pak_off: it for it in le.find_instances(ship)}
    T, own, oid = [], [], []
    for o, a in si.items():
        b = hi.get(o)
        items_a = la.draw_items(stock, a)
        items_b = {i: e for e, i, _ in la.draw_items(ship, b)} if b is not None else {}
        same_m = b is not None and np.array_equal(a.M, b.M)
        for e, i, _ in items_a:
            if _is_shadow(stock, i):
                continue
            if same_m and i in items_b and _stream_bytes(stock, i) == _stream_bytes(ship, i):
                continue
            Wa, Ia = _item_world(stock, a, i)
            if Wa is None:
                continue
            live_a = (Ia[:, 0] != Ia[:, 1]) & (Ia[:, 1] != Ia[:, 2])
            Ta = Wa[Ia]
            if b is not None and i in items_b:
                Wb, Ib = _item_world(ship, b, i)
                if Wb is not None and len(Ib) == len(Ia):
                    live_b = (Ib[:, 0] != Ib[:, 1]) & (Ib[:, 1] != Ib[:, 2])
                    moved = (np.abs(Wb[Ib] - Ta).max((1, 2)) > 0.01) | ~live_b
                else:
                    moved = np.ones(len(Ia), bool)
            else:
                moved = np.ones(len(Ia), bool)
            g = live_a & moved
            if g.any():
                own.append((lv, o, i))
                T.append(Ta[g])
                oid.append(np.full(int(g.sum()), len(own) - 1))
    if not T:
        return np.zeros((0, 3, 3)), [], np.zeros(0, int)
    return np.concatenate(T), own, np.concatenate(oid)


# ------------------------------------------------------------------------------------------------ texels
def raster(U, I, tri_ok=None):
    """texel centres inside the UV triangles: U (n,2) in texel units (x, y), I (m,3) -> (tri index, x, y, l1, l2) arrays"""
    A, B, C = U[I[:, 0]], U[I[:, 1]], U[I[:, 2]]
    lo = np.floor(np.minimum(np.minimum(A, B), C) - 0.5).astype(np.int64) + 1
    hi = np.floor(np.maximum(np.maximum(A, B), C) - 0.5).astype(np.int64)
    w, h = hi[:, 0] - lo[:, 0] + 1, hi[:, 1] - lo[:, 1] + 1
    ok = (w > 0) & (h > 0) & (w * h < 1 << 20)
    if tri_ok is not None:
        ok &= tri_ok
    k = np.nonzero(ok)[0]
    if not len(k):
        z = np.zeros(0, np.int64)
        return z, z, z, np.zeros(0), np.zeros(0)
    cnt = (w[k] * h[k])
    t = np.repeat(k, cnt)
    start = np.repeat(np.cumsum(cnt) - cnt, cnt)
    j = np.arange(cnt.sum()) - start
    x = lo[t, 0] + j % w[t]
    y = lo[t, 1] + j // w[t]
    px, py = x + 0.5, y + 0.5
    e1, e2 = B[t] - A[t], C[t] - A[t]
    det = e1[:, 0] * e2[:, 1] - e1[:, 1] * e2[:, 0]
    good = np.abs(det) > 1e-12
    det = np.where(good, det, 1)
    qx, qy = px - A[t, 0], py - A[t, 1]
    l1 = (qx * e2[:, 1] - qy * e2[:, 0]) / det
    l2 = (e1[:, 0] * qy - e1[:, 1] * qx) / det
    ins = good & (l1 >= -1e-6) & (l2 >= -1e-6) & (l1 + l2 <= 1 + 1e-6)
    return t[ins], x[ins], y[ins], l1[ins], l2[ins]


class Texels:
    """atlas texels of the charted draw items of one level near a set of boxes"""

    def __init__(self, p, W, H, lo, hi, insts=None, near_fn=None):
        insts = insts if insts is not None else le.find_instances(p)
        X, Y, P, N, OWN, KEY = [], [], [], [], [], []
        self.items = []
        for it in insts:
            if (it.whi < lo).any() or (it.wlo > hi).any():
                continue
            for e, i, b in la.draw_items(p, it):
                if _is_shadow(p, i):
                    continue
                sm = p.submeshes[i]
                uv = la.lm_uv(p, b, sm["vcount"])
                if uv is None:
                    continue
                Wv, I = _item_world(p, it, i)
                if Wv is None:
                    continue
                T = Wv[I]
                tl, th = T.min(1), T.max(1)
                near = (th >= lo).all(1) & (tl <= hi).all(1) & (I[:, 0] != I[:, 1])
                if near.any() and near_fn is not None:
                    near[near] = near_fn(T[near])
                if not near.any():
                    continue
                U = uv * [W, H]
                t, x, y, l1, l2 = raster(U, I, near)
                if not len(t):
                    continue
                pts = T[t, 0] + (T[t, 1] - T[t, 0]) * l1[:, None] + (T[t, 2] - T[t, 0]) * l2[:, None]
                fn = np.cross(T[:, 1] - T[:, 0], T[:, 2] - T[:, 0])
                fn /= np.maximum(np.linalg.norm(fn, axis=1, keepdims=True), 1e-12)
                X.append(x); Y.append(y); P.append(pts); N.append(fn[t])
                self.items.append((it.pak_off, i))
                OWN.append(np.full(len(t), len(self.items) - 1))
        cat = lambda a, s: np.concatenate(a) if a else np.zeros(s)
        self.x, self.y = cat(X, 0).astype(np.int64), cat(Y, 0).astype(np.int64)
        self.P, self.N, self.own = cat(P, (0, 3)), cat(N, (0, 3)), cat(OWN, 0).astype(np.int64)
        ok = (self.x >= 0) & (self.x < W) & (self.y >= 0) & (self.y < H)
        lin = self.y * W + self.x
        _, first = np.unique(np.where(ok, lin, -1), return_index=True)
        keep = np.zeros(len(lin), bool)
        keep[first] = True
        keep &= ok
        for a in ("x", "y", "P", "N", "own"):
            setattr(self, a, getattr(self, a)[keep])


def coverage(p, W, H, box_uv, insts=None):
    """bool (H, W) mask of the atlas texels covered by any chart whose UV box meets box_uv (x0, y0, x1, y1 in texels)"""
    insts = insts if insts is not None else le.find_instances(p)
    m = np.zeros((H, W), bool)
    for it in insts:
        for e, i, b in la.draw_items(p, it):
            sm = p.submeshes[i]
            uv = la.lm_uv(p, b, sm["vcount"])
            if uv is None:
                continue
            U = uv * [W, H]
            if U[:, 0].max() < box_uv[0] or U[:, 0].min() > box_uv[2] or U[:, 1].max() < box_uv[1] or U[:, 1].min() > box_uv[3]:
                continue
            I = np.array(p.indices(sm), np.int64).reshape(-1, 3)
            t, x, y, _, _ = raster(U, I, I[:, 0] != I[:, 1])
            ok = (x >= 0) & (x < W) & (y >= 0) & (y < H)
            m[y[ok], x[ok]] = True
    return m


# ------------------------------------------------------------------------------------------------ occlusion
def _dirs(n=NDIR):
    k = np.arange(n) + 0.5
    r = np.sqrt(k / n)
    phi = k * np.pi * (3 - np.sqrt(5))
    return np.stack([r * np.cos(phi), r * np.sin(phi), np.sqrt(1 - r * r)], 1)      # cosine-weighted, z = up


def _basis(nrm):
    a = np.where(np.abs(nrm[:, 1:2]) < 0.9, np.array([[0, 1.0, 0]]), np.array([[1.0, 0, 0]]))
    t = np.cross(a, nrm)
    t /= np.maximum(np.linalg.norm(t, axis=1, keepdims=True), 1e-12)
    return t, np.cross(nrm, t)


def _hits(O, D, T, L):
    """(r,) bool: ray O + s D (s in (0, L]) hits any of T (m,3,3); O, D (r,3)"""
    if not len(T) or not len(O):
        return np.zeros(len(O), bool)
    out = np.zeros(len(O), bool)
    step = max(1, int(1e6 // max(len(T), 1)))
    e1, e2 = T[:, 1] - T[:, 0], T[:, 2] - T[:, 0]
    for a in range(0, len(O), step):
        o, d = O[a:a + step, None, :], D[a:a + step, None, :]
        pv = np.cross(d, e2[None])
        det = (e1[None] * pv).sum(2)
        ok = np.abs(det) > 1e-12
        inv = 1.0 / np.where(ok, det, 1)
        tv = o - T[None, :, 0]
        u = (tv * pv).sum(2) * inv
        qv = np.cross(tv, e1[None])
        v = (qv * d).sum(2) * inv
        s = (e2[None] * qv).sum(2) * inv
        out[a:a + step] = (ok & (u >= 0) & (v >= 0) & (u + v <= 1) & (s > 1e-4) & (s <= L)).any(1)
    return out


class Caster:
    """Embree (embreex) scene of the gone triangles; rays skip the triangles of one owner (a texel's own draw item) and, optionally, steep ones"""

    def __init__(self, T, owner):
        from embreex import rtcore_scene as rs
        from embreex.mesh_construction import TriangleMesh
        self.s = rs.EmbreeScene()
        TriangleMesh(self.s, np.ascontiguousarray(T, np.float32))
        self.owner = np.asarray(owner, np.int64)
        n = np.cross(T[:, 1] - T[:, 0], T[:, 2] - T[:, 0])
        self.flat = np.abs(n[:, 1]) > 0.5 * np.maximum(np.linalg.norm(n, axis=1), 1e-12)

    def hits(self, O, D, L, own, flat_only=False):
        """(r,) bool: ray O + s D, s in (0, L], hits a triangle whose owner != own (r,) (and flat when flat_only)"""
        O = np.ascontiguousarray(O, np.float32).copy()
        D = np.ascontiguousarray(D, np.float32)
        rem = np.full(len(O), L, np.float64)
        out = np.zeros(len(O), bool)
        act = np.arange(len(O))
        for _ in range(8):
            if not len(act):
                break
            r = self.s.run(O[act], D[act], output=1)
            pid, tf = r["primID"], r["tfar"].astype(np.float64)
            hit = (pid >= 0) & (tf <= rem[act])
            pidc = np.where(hit, pid, 0)
            skip = hit & ((self.owner[pidc] == own[act]) | ((~self.flat[pidc]) if flat_only else False))
            out[act[hit & ~skip]] = True
            nxt = act[skip]
            adv = tf[skip] + 1e-4
            O[nxt] += D[nxt] * adv[:, None].astype(np.float32)
            rem[nxt] -= adv
            act = nxt
        return out


def invalid_weight(tx, gT, goid, log=print):
    """per texel weight in [0, 1]: 1 = baked with now-gone geometry on top of / around it"""
    n = len(tx.P)
    w, frac, bur = np.zeros(n), np.zeros(n), np.zeros(n, bool)
    if not len(gT) or not n:
        return w, frac, bur
    t0 = time.time()
    C = Caster(gT, goid)
    own = tx.gid[tx.own]
    O = tx.P + tx.N * 0.01
    up = C.hits(O, np.tile([0, 1.0, 0], (n, 1)), BURY, own, flat_only=True) & (tx.N[:, 1] > -0.5)
    dirs = _dirs()
    t, b = _basis(tx.N)
    for a in range(0, n, 50000):
        sl = slice(a, a + 50000)
        R = dirs[None, :, 0:1] * t[sl, None] + dirs[None, :, 1:2] * b[sl, None] + dirs[None, :, 2:3] * tx.N[sl, None]
        h = C.hits(np.repeat(O[sl], NDIR, 0), R.reshape(-1, 3), HEMI, np.repeat(own[sl], NDIR)).reshape(-1, NDIR)
        frac[sl] = h.mean(1)
    bur = up
    w = np.maximum(up.astype(float), np.clip((frac - 0.15) / 0.35, 0, 1))
    log("    occlusion: %d texels, %d buried, %d with weight > 0 (%.0f s)" % (n, int(bur.sum()), int((w > 0).sum()), time.time() - t0))
    return w, frac, bur


# ------------------------------------------------------------------------------------------------ textures
def _cache_dir(work):
    d = os.path.join(work, "lightmap-fix")
    os.makedirs(d, exist_ok=True)
    return d


def full_textures(p, work, log=print):
    """{kind: (desc, fmt, w, h, mip0 bytes)} of a level's atlas: mounted dicts first, else any world archive (cached in <work>/lightmap-fix/tex)"""
    import texdict
    import glob
    lm = la.lightmap_textures(p)
    out = {}
    cd = os.path.join(_cache_dir(work), "tex")
    os.makedirs(cd, exist_ok=True)
    need = []
    for k, t in lm.items():
        f = os.path.join(cd, "%016x.bin" % t["hash"])
        if os.path.exists(f):
            hdr = json.load(open(f + ".json"))
            out[k] = (t, hdr["fmt"], hdr["w"], hdr["h"], open(f, "rb").read())
        else:
            need.append((k, t))
    if need:
        hs = [t["hash"] for _, t in need]
        got = texdict.find(hs)
        rest = [h for h in hs if h not in got]
        if rest:
            saved = texdict.ARCHIVES
            texdict.ARCHIVES = tuple(sorted(os.path.basename(x) for x in glob.glob(os.path.join(texdict.GAME, "build", "pc", "main", "world-*.psarc"))))
            try:
                got.update(texdict.find(rest))
            finally:
                texdict.ARCHIVES = saved
        for k, t in need:
            if t["hash"] not in got:
                log("    %s: %016x not in any texture dict, skipped" % (k, t["hash"]))
                continue
            fmt, w, h, data = got[t["hash"]]
            bpb = 16
            data = bytes(data[:(w // 4) * (h // 4) * bpb])
            f = os.path.join(cd, "%016x.bin" % t["hash"])
            open(f, "wb").write(data)
            json.dump({"fmt": fmt, "w": w, "h": h}, open(f + ".json", "w"))
            out[k] = (t, fmt, w, h, data)
    return out


def decode_tex(fmt, w, h, data):
    if fmt in (95, 96):
        import bc6h
        return bc6h.decode(data, w, h)
    import texture2ddecoder as t2d
    return np.frombuffer(t2d.decode_bc7(bytes(data), w, h), np.uint8).reshape(h, w, 4)[:, :, [2, 1, 0, 3]].astype(np.float32)


def encode_blocks(fmt, w, h, data, img, bx, by):
    if fmt in (95, 96):
        import bc6h
        return bc6h.patch(data, w, h, img, bx, by)
    import mp_snow_pak
    import bc6h
    px = bc6h.blocks_of(np.clip(np.rint(img), 0, 255).astype(np.uint8), bx, by)        # (n, 16, 4)
    strip = px.reshape(-1, 4, 4, 4).transpose(1, 0, 2, 3).reshape(4, -1, 4)             # blocks side by side
    enc = mp_snow_pak.bc7_blocks(np.ascontiguousarray(strip))
    out = bytearray(data)
    nbx = w // 4
    for k, (x, y) in enumerate(zip(bx, by)):
        o = (int(y) * nbx + int(x)) * 16
        out[o:o + 16] = enc[16 * k:16 * k + 16]
    return bytes(out)


def inject(buf, desc, old_hash, fmt, w, h, mips, payload, log=print):
    """append payload as the texture of VRAM_DESC `desc` (pak_editor_cli inject-texture layout) and bump its hash -> new bytes"""
    b = bytearray(buf)
    p = ndpak.Pak.__new__(ndpak.Pak)
    trailer = struct.unpack_from("<I", b, 32)[0]
    n, pt = struct.unpack_from("<II", b, 16)
    raw = max(sum(struct.unpack_from("<II", b, pt + 12 * i)) for i in range(n))
    if raw + trailer != len(b):
        raise SystemExit("lightmap_fix inject: pak layout unexpected (raw %d + trailer %d != %d)" % (raw, trailer, len(b)))
    if trailer + len(payload) > TRAILER_LIMIT:
        raise SystemExit("lightmap_fix inject: VRAM trailer would exceed 2^27 bytes")
    struct.pack_into("<I", b, desc + 40, trailer)
    struct.pack_into("<I", b, desc + 48, len(payload))
    struct.pack_into("<I", b, desc + 80, mips)
    struct.pack_into("<I", b, desc + 84, w)
    struct.pack_into("<I", b, desc + 88, h)
    ob, nb = struct.pack("<Q", old_hash), struct.pack("<Q", (old_hash + 1) & (2 ** 64 - 1))
    cnt, i = 0, 0
    head = bytes(b[:raw])
    while True:
        i = head.find(ob, i)
        if i < 0:
            break
        b[i:i + 8] = nb
        cnt += 1
        i += 8
    struct.pack_into("<I", b, 32, trailer + len(payload))
    b += payload
    del p
    return bytes(b), cnt


def patch_vertex(buf, vtx, which=1):
    """write the per-vertex light patches (which = 1 new, 2 old bytes) in place; the bytes there must be the other side's"""
    b = bytearray(buf)
    for e in vtx:
        o, want, have = e[0], bytes.fromhex(e[which]), bytes.fromhex(e[3 - which]) if len(e) > 2 else None
        if have is not None and bytes(b[o:o + len(have)]) != have:
            raise SystemExit("lightmap fix: vertex-light stream at 0x%x is not what the repair was computed from" % o)
        b[o:o + len(want)] = want
    return bytes(b)


def verify_injected(buf, res, vtx=()):
    """re-read the pak: every repaired layer's descriptor has the full size, hash + 1, and its payload bytes are ours; geometry pages untouched"""
    import tempfile
    with tempfile.NamedTemporaryFile(delete=False, suffix=".pak") as fh:
        fh.write(buf)
        tmp = fh.name
    try:
        p = ndpak.Pak(tmp)
        by = {t["desc"]: t for t in ndpak.textures(p)}
        for k, (desc, h, fmt, w, hh, data, *_mp) in res.items():
            t = by[desc]
            assert t["hash"] == h + 1 and t["w"] == w and t["h"] == hh and t["size"] == len(data), (k, t)
            assert p.d[t["data"]:t["data"] + t["size"]] == data, k
        for o, new, _old in vtx:
            assert p.d[o:o + len(new) // 2] == bytes.fromhex(new), hex(o)
    finally:
        os.remove(tmp)


def restore(buf, undo):
    """undo inject(): cut the appended payloads, put the descriptor fields and hashes back"""
    b = bytearray(buf)
    n, pt = struct.unpack_from("<II", b, 16)
    raw = max(sum(struct.unpack_from("<II", b, pt + 12 * i)) for i in range(n))
    del b[raw + undo["trailer"]:]
    for o, old in undo.get("vtx", []):
        ob = bytes.fromhex(old)
        b[o:o + len(ob)] = ob
    struct.pack_into("<I", b, 32, undo["trailer"])
    for d, hx, h in undo["descs"]:
        b[d + 40:d + 92] = bytes.fromhex(hx)
        ob, nb = struct.pack("<Q", (h + 1) & (2 ** 64 - 1)), struct.pack("<Q", h)
        head = bytes(b[:raw])
        i = 0
        while True:
            i = head.find(ob, i)
            if i < 0:
                break
            b[i:i + 8] = nb
            i += 8
    return bytes(b)


# ------------------------------------------------------------------------------------------------ the repair
NW = 2.0             # KD space (position, normal * NW): sources face the same way
PASSES = ((FILL_R, FILL_S), (2 * FILL_R, 3 * FILL_S), (FILL_FAR, FILL_FAR / 3), (2 * FILL_FAR, 2 * FILL_FAR / 3))
OPEN_NEAR = 1.0      # black texels this close to a repaired area are tested against the geometry that still stands
OPEN_MIN = 0.25      # ... and join the repair when at least this fraction of their hemisphere sees the SKY (SKY_LEN rays against
OPEN_MIN_WALL = 0.12  #     every written level of the map: roofs and ceilings count; indoor floors were brightened otherwise)
SKY_LEN = 40.0
LOS_LIFT = 0.05      # a fill source must see the hole texel (segment between the two, lifted off both surfaces, through what still stands)
FEATHER = 1.2        # repair delta blurred in atlas space within each chart (texels): no texel stair-steps at the repair's edge
GROW = 0.4           # dark leftovers (unlit, unmarked) touching a repaired area join it up to this far (m): floor line, chart edges, slivers
MIRROR = (1.0, 0.6, 0.35, 0.15, 0.0)
COLUMN = 2.5        # wall column search reach (m)
SNOW_DIM = 0.85     # open snow within SNOW_DIM_R of a hole and darker than this share of the snow around (within SNOW_DIM_REF) joins the hole
SNOW_DIM_R = 1.0
SNOW_DIM_REF = 3.0
ROOF_SRC_MIN = 4    # a roofed hole texel's cap = 25th percentile of its ROOFED sources when it has at least this many
CONTACT_MAX = 1.5   # wall hole texels up to this high above the floor (what still stands below) take the contact shade at the foot...
CONTACT_H = 0.25    # ... = median of the UNREPAIRED wall foot texels (this high, facing the same way) around
CONTACT_R = 3.0     #     within this reach (twice it when fewer than 4 there), in front of the wall; it ramps (smoothstep) up to the fill at the hole's top in that column
                    #     (snow wall case: under removed trash bags the fill copied the lit wall above down to the floor)


def _gather(SP, SN, slum, P, N, passes=PASSES, tree=None, los=None):
    """normal-aware Gaussian weights of the sources around each point: (wt (n,48), jj (n,48), ok (n,)); los(A, NA, B, NB) -> visible
    drops sources that do not see the point (the other side of a wall, outdoor snow for an indoor floor)"""
    from scipy.spatial import cKDTree
    tree = tree if tree is not None else cKDTree(np.c_[SP, SN * NW])
    n = len(P)
    wt, jj, ok = np.zeros((n, 48)), np.zeros((n, 48), np.int64), np.zeros(n, bool)
    for rad, fall in passes:                                                   # wider passes for texels deep inside a big footprint
        todo = np.nonzero(~ok)[0]
        if not len(todo):
            break
        for a in range(0, len(todo), 200000):
            t = todo[a:a + 200000]
            d6, j = tree.query(np.c_[P[t], N[t] * NW], k=48, distance_upper_bound=rad + NW * 0.6)
            valid = np.isfinite(d6)
            jv = np.where(valid, j, 0)
            d = np.linalg.norm(SP[jv] - P[t][:, None], axis=2)
            nd = np.einsum("nkc,nc->nk", SN[jv], N[t])
            behind = np.einsum("nkc,nc->nk", SP[jv] - P[t][:, None], N[t])
            valid &= (d <= rad) & (nd > 0.5) & (behind > -0.08)             # never from behind the surface (the other side of a wall)
            ls = slum[jv]
            wv = np.where(valid, np.exp(-(d / fall) ** 2) * np.clip(nd, 0, 1) ** 8 * (ls / (ls + 0.05)) ** 2, 0)   # prefer lit sources
            if los is not None:
                r_, c_ = np.nonzero(wv > 0)
                if len(r_):
                    vis = los(P[t][r_], N[t][r_], SP[jv[r_, c_]], SN[jv[r_, c_]])
                    wv[r_[~vis], c_[~vis]] = 0
            wt[t], jj[t] = wv, jv
            ok[t] = wv.sum(1) > 1e-6
    return wt, jj, ok


def _mean(V, wt, jj):
    return (V[jj] * wt[..., None]).sum(1) / np.maximum(wt.sum(1), 1e-12)[:, None]


def _smooth_fill(tx, w, imgs, dst, src, res, ok, smooth, W):
    """open snow / terrain: the hole is a membrane (Laplace) fill in the chart's own atlas grid from the clean texels around it, so the
    light runs smoothly across the footprint (no mirrored shadow pieces, no Gaussian-pass steps), times a fine grain matching the
    measured texel-to-texel grain of the same chart's clean snow.  Changes res in place; -> texels refilled"""
    import scipy.sparse as sps
    import scipy.sparse.linalg as spl
    sel = np.nonzero(smooth[dst] & ok)[0]
    if not len(sel):
        return 0
    srcm = np.zeros(len(w), bool)
    srcm[src] = True
    kinds = list(imgs)
    done = 0
    for oi in np.unique(tx.own[dst[sel]]):
        us = sel[tx.own[dst[sel]] == oi]                                    # positions in dst
        ukey = tx.y[dst[us]] * W + tx.x[dst[us]]
        uk, first = np.unique(ukey, return_index=True)
        kn = np.nonzero(srcm & (tx.own == oi))[0]
        kkey = tx.y[kn] * W + tx.x[kn]
        kk, kf = np.unique(kkey, return_index=True)
        drop = np.isin(kk, uk)
        kk, kn = kk[~drop], kn[kf[~drop]]
        n = len(uk)
        rows, cols, deg = [], [], np.zeros(n)
        bsum = {k: np.zeros((n, imgs[k].shape[2])) for k in kinds}
        kval = {k: imgs[k][tx.y[kn], tx.x[kn]].astype(np.float64) for k in kinds}
        for dk in (1, -1, W, -W):
            q = uk + dk
            iu = np.searchsorted(uk, q); iu = np.minimum(iu, n - 1)
            hu = uk[iu] == q
            if dk in (1, -1):                                              # no wrap across atlas rows
                hu &= (q // W) == (uk // W)
            rows.append(np.nonzero(hu)[0]); cols.append(iu[hu]); deg += hu
            if len(kk):
                ik = np.minimum(np.searchsorted(kk, q), len(kk) - 1)
                hk = kk[ik] == q
                if dk in (1, -1):
                    hk &= (q // W) == (uk // W)
                deg += hk
                for k in kinds:
                    bsum[k][hk] += kval[k][ik[hk]]
        r_, c_ = np.concatenate(rows), np.concatenate(cols)
        eps = 1e-3                                                          # ties a texel with no path to a clean one to the low frequency
        A = sps.csc_matrix((np.r_[deg + eps, -np.ones(len(r_))], (np.r_[np.arange(n), r_], np.r_[np.arange(n), c_])), shape=(n, n))
        lu = spl.splu(A)
        # grain of the clean snow of this chart: log luminance against its 4-neighbour mean
        L = imgs["basis1_lightColor"][tx.y[kn], tx.x[kn]].astype(np.float64).sum(1) if "basis1_lightColor" in imgs else None
        sg = 0.0
        if L is not None and len(kk) > 50:
            nb = np.zeros(len(kk)); cnt = np.zeros(len(kk))
            for dk in (1, -1, W, -W):
                ik = np.minimum(np.searchsorted(kk, kk + dk), len(kk) - 1)
                h = kk[ik] == kk + dk
                nb[h] += L[ik[h]]; cnt[h] += 1
            full = (cnt == 4) & (L > 1e-3)
            if full.sum() > 30:
                r = np.log(L[full]) - np.log(np.maximum(nb[full] / 4, 1e-6))
                sg = float(min(np.std(r) / np.sqrt(1.25), 0.15))            # white grain s gives residual std s*sqrt(1 + 1/4)
        rec, sub = tx.items[oi]
        rng = np.random.default_rng((int(rec) * 4099 + int(sub)) & 0xFFFFFFFF)
        grain = np.exp(rng.standard_normal(n) * sg)
        inv = np.searchsorted(uk, ukey)                                     # every hole entry (duplicates too) -> its grid unknown
        pos = dst[us]
        for k in kinds:
            low = np.zeros((n, imgs[k].shape[2]))
            low[:] = res[k][us][first]                                      # the current fill as the tie for isolated texels
            u = lu.solve(bsum[k] + eps * low)
            if k.endswith("Color"):
                u = u * grain[:, None]
            old = imgs[k][tx.y[pos], tx.x[pos]].astype(np.float64)
            ww = w[pos][:, None]
            res[k][us] = old * (1 - ww) + u[inv] * ww
        done += len(us)
    return done


def _contact_shade(tx, w, lum, dst, res, wall, up_d, floor_fn):
    """wall hole texels near the floor: never the lit wall above copied down to the floor.  Each takes the stock contact shade of
    the unrepaired wall feet around it (same facing: a floor faces the sky / a lamp differently), ramping (smoothstep) to its fill value at the top of the hole in its column
    (up_d = distance up to the first untouched lit texel of the column, inf when none).  Only darkens.  Changes res; -> texels changed"""
    from scipy.spatial import cKDTree
    q = np.nonzero(wall)[0]
    if not len(q) or floor_fn is None:
        return 0
    h = floor_fn(tx.P[dst[q]] + tx.N[dst[q]] * 0.05)
    q, h = q[h <= CONTACT_MAX], h[h <= CONTACT_MAX]
    if not len(q):
        return 0
    # seam samples: unrepaired, not black wall feet (CONTACT_H above the floor)
    near = cKDTree(tx.P[dst[q]]).query(tx.P, distance_upper_bound=2 * CONTACT_R + 0.5)[0]
    cand = np.nonzero(np.isfinite(near) & (w <= 0) & (lum > 3e-3))[0]
    wall_c = cand[np.abs(tx.N[cand, 1]) < 0.5]
    S_ = np.zeros(0, np.int64)
    if len(wall_c):
        hf = floor_fn(tx.P[wall_c] + tx.N[wall_c] * 0.05)
        S_ = wall_c[hf <= CONTACT_H]
    if not len(S_):
        return 0
    st = cKDTree(tx.P[S_])
    P, N = tx.P[dst[q]], tx.N[dst[q]]
    seam = np.full(len(q), np.nan)
    for rad in (CONTACT_R, 2 * CONTACT_R):                # a whole aisle foot under the hole: the seam farther along it
        todo = np.nonzero(~np.isfinite(seam))[0]
        if not len(todo):
            break
        lst = st.query_ball_point(P[todo], rad)
        for i, js in zip(todo, lst):
            if not js:
                continue
            js = np.asarray(js, np.int64)
            Sp = tx.P[S_[js]]
            keep = ((Sp - P[i]) @ N[i] > -0.1) & (np.abs(Sp[:, 1] - (P[i, 1] - h[i])) < 0.6)   # not behind this wall, at its floor
            keep &= tx.N[S_[js]] @ N[i] > 0.7                                                  # facing the same way
            if keep.sum() >= 4:
                seam[i] = np.median(lum[S_[js[keep]]])
    g = np.isfinite(seam)
    q, h, seam = q[g], h[g], seam[g]
    if not len(q):
        return 0
    ht = np.minimum(h + up_d[q], CONTACT_MAX)
    t = np.clip(h / np.maximum(ht, 1e-3), 0, 1)
    s = t * t * (3 - 2 * t)
    new_l = res["basis1_lightColor"][q].sum(1)
    tgt = seam + (new_l - seam) * s
    fac = np.where((new_l > tgt) & (new_l > 1e-9), tgt / np.maximum(new_l, 1e-9), 1.0)
    for k in res:
        if k.endswith("Color") and res[k] is not None:
            res[k][q] *= fac[:, None]
    return int((fac < 0.999).sum())


def fill_values(tx, w, imgs, log=print, open_fn=None, smooth=None, los=None, floor_fn=None):
    """structure-continuing fill.  -> (dst, {kind: (k,c) new values}, ok); w is updated in place for the grown leftovers.

    low frequency: normal-aware Gaussian mean of the lit untouched texels around (matches the surroundings' brightness).
    detail: on walls each hole texel copies the first lit texel straight above it (same facing, same plane) = its stripe's column, so the
    vertical streaks continue down into the old snow band without repeating horizontal features; elsewhere (snow, floors) the texel MIRRORED
    across the nearest lit boundary texel, so the grain continues across a footprint.  Both scaled by low(hole) / low(source).  Directional layers (BC7 lightDir / bentNormal) take the mirrored source as is (consistent with its light)."""
    from scipy.spatial import cKDTree
    lc = imgs.get("basis1_lightColor")
    lum = lc[tx.y, tx.x].astype(np.float64).sum(1) if lc is not None else np.ones(len(w))
    lit = lum > 3e-3
    if lc is not None:                                      # and not far darker than its own surface's untouched texels (near-buried ones)
        base = (w <= 0) & lit
        for oi in np.unique(tx.own[base]):
            m = base & (tx.own == oi)
            lit[m] &= lum[m] >= 0.3 * np.median(lum[m])
    # grow: unlit unmarked texels touching a marked area (floor line, chart borders, triangle-edge slivers) are the same bake artefact
    seed = w >= 0.5
    grown = 0
    if seed.any():
        cand = np.nonzero((w < 0.5) & ~lit)[0]
        if len(cand):
            ct = cKDTree(np.c_[tx.P[cand], tx.N[cand] * NW])
            cur = np.nonzero(seed)[0]
            got = np.zeros(len(cand), bool)
            for _ in range(int(GROW / 0.1)):
                hits = ct.query_ball_point(np.c_[tx.P[cur], tx.N[cur] * NW], 0.12)
                new = np.unique(np.concatenate([np.asarray(h, np.int64) for h in hits])) if len(hits) else np.zeros(0, np.int64)
                new = new[~got[new]]
                if not len(new):
                    break
                got[new] = True
                cur = cand[new]
            w[cand[got]] = 1.0
            grown = int(got.sum())
    opened = 0
    if open_fn is not None and seed.any():                  # black, unmarked, near a repaired area and NOT occluded by what still stands:
        cand = np.nonzero((w < 0.5) & ~lit)[0]              # it was baked under something that is gone (a board, a threshold, trash)
        if len(cand):
            d, _ = cKDTree(tx.P[w >= 0.5]).query(tx.P[cand], distance_upper_bound=OPEN_NEAR)
            cand = cand[np.isfinite(d)]
        if len(cand):
            op = open_fn(tx.P[cand], tx.N[cand])
            o = cand[op >= np.where(np.abs(tx.N[cand, 1]) < 0.5, OPEN_MIN_WALL, OPEN_MIN)]   # a wall texel at the floor line sees the ground
            w[o] = 1.0
            opened = len(o)
    dimmed = 0
    if smooth is not None and seed.any():                   # open snow: the dim remains of a gone thing's soft shadow around its footprint join the hole
        hole = (w >= 0.5) & smooth
        if hole.any():
            th = cKDTree(tx.P[hole])
            cand = np.nonzero(smooth & (w < 0.5))[0]
            dh, _ = th.query(tx.P[cand], distance_upper_bound=SNOW_DIM_R)
            near = cand[np.isfinite(dh)]
            ring = cand[np.isfinite(th.query(tx.P[cand], distance_upper_bound=SNOW_DIM_REF)[0])]
            for oi in np.unique(tx.own[near]):
                r = ring[(tx.own[ring] == oi) & lit[ring]]
                if len(r) < 20:
                    continue
                ref = np.percentile(lum[r], 75)                 # open snow level (soft shadows only pull values down)
                m = near[(tx.own[near] == oi) & (lum[near] < SNOW_DIM * ref)]
                if len(m) and open_fn is not None:              # not the contact shadow of something that still stands (a wall foot)
                    m = m[open_fn(tx.P[m], tx.N[m]) >= OPEN_MIN]
                w[m] = 1.0
                dimmed += len(m)
    src = np.nonzero((w <= 0) & lit)[0]                     # sources: untouched AND lit (a black texel is buried under geometry that is still there)
    dst = np.nonzero(w > 0)[0]
    res = {k: None for k in imgs}
    if not len(dst) or not len(src):
        return dst, res, np.zeros(len(dst), bool)
    SP, SN, slum = tx.P[src], tx.N[src], lum[src]
    tree = cKDTree(np.c_[SP, SN * NW])
    wt, jj, ok = _gather(SP, SN, slum, tx.P[dst], tx.N[dst], tree=tree, los=los)
    low = {k: _mean(img[tx.y[src], tx.x[src]].astype(np.float64), wt, jj) for k, img in imgs.items()}
    # texels with no source at all: diffuse from the repaired ones (3 rounds)
    for _ in range(3):
        if ok.all() or not ok.any():
            break
        a, b = np.nonzero(ok)[0], np.nonzero(~ok)[0]
        llum = low["basis1_lightColor"][a].sum(1) if lc is not None else np.ones(len(a))
        wt2, jj2, ok2 = _gather(tx.P[dst[a]], tx.N[dst[a]], llum, tx.P[dst[b]], tx.N[dst[b]], los=los)
        for k in low:
            low[k][b[ok2]] = _mean(low[k][a], wt2[ok2], jj2[ok2])
        ok[b[ok2]] = True
    # detail source: mirror across the nearest lit boundary texel, same plane + facing
    P, N = tx.P[dst], tx.N[dst]
    _, b0 = tree.query(np.c_[P, N * NW], k=1)
    b0 = np.minimum(b0, len(src) - 1)
    ds = np.full(len(dst), -1, np.int64)
    wall = np.abs(N[:, 1]) < 0.5                                                # walls: lit texels straight up the wall = the stripe's column
    KH = 8
    hits = np.full((len(dst), KH), -1, np.int64)
    nh = np.zeros(len(dst), np.int64)
    up_d = np.full(len(dst), np.inf)                                            # distance up the column to its first lit texel
    for k in range(1, int(COLUMN / 0.04) + 1):
        todo = np.nonzero(wall & (nh < KH))[0]
        if not len(todo):
            break
        M = P[todo] + np.array([0, 0.04 * k, 0])
        dd, j = tree.query(np.c_[M, N[todo] * NW], k=1, distance_upper_bound=0.07 + NW * 0.3)
        good = np.isfinite(dd)
        j = np.where(good, j, 0)
        good &= np.linalg.norm(SP[j] - M, axis=1) <= 0.07
        good &= np.einsum("nc,nc->n", SN[j], N[todo]) > 0.9
        good &= np.abs(np.einsum("nc,nc->n", SP[j] - P[todo], N[todo])) < 0.08
        t = todo[good]
        new_ = j[good] != hits[t, np.maximum(nh[t] - 1, 0)]
        t, jg = t[new_], j[good][new_]
        up_d[t[nh[t] == 0]] = 0.04 * k
        hits[t, nh[t]] = jg
        nh[t] += 1
    hw = np.nonzero(nh > 0)[0]
    if len(hw):                                                                 # the run's MEDIAN detail, not the first texel: a sill / trim band
        uh = np.unique(hits[hw][hits[hw] >= 0])                                 # right above the hole is not repeated down the wall
        wl, jl, _ = _gather(SP, SN, slum, SP[uh], SN[uh], passes=PASSES[:1], tree=tree)
        lw = _mean(slum[:, None], wl, jl)[:, 0]
        rat = np.full(len(src), np.nan)
        rat[uh] = slum[uh] / np.maximum(lw, 1e-6)
        R = np.where(hits[hw] >= 0, rat[np.maximum(hits[hw], 0)], np.nan)
        med = np.nanmedian(R, axis=1)
        pick = np.nanargmin(np.abs(R - med[:, None]), axis=1)
        ds[hw] = hits[hw, pick]
    for f in MIRROR:                                                            # elsewhere (snow, floors, walls with nothing lit above): mirror
        todo = np.nonzero(ds < 0)[0]
        if not len(todo):
            break
        M = SP[b0[todo]] + (SP[b0[todo]] - P[todo]) * f
        dd, j = tree.query(np.c_[M, N[todo] * NW], k=1, distance_upper_bound=0.15 + NW * 0.3)
        good = np.isfinite(dd)
        j = np.where(good, j, 0)
        good &= np.linalg.norm(SP[j] - M, axis=1) <= 0.15
        good &= np.einsum("nc,nc->n", SN[j], N[todo]) > 0.9
        good &= np.abs(np.einsum("nc,nc->n", SP[j] - P[todo], N[todo])) < 0.08
        ds[todo[good]] = j[good]
    if los is not None and (ds >= 0).any():                                    # a detail source behind a wall is no detail source
        q = np.nonzero(ds >= 0)[0]
        ds[q[~los(P[q], N[q], SP[ds[q]], SN[ds[q]])]] = -1
    has = ds >= 0
    # low frequency at each detail source (same falloff as the first pass, from the sources around it)
    us = np.unique(ds[has])
    wts, jjs, _ = _gather(SP, SN, slum, SP[us], SN[us], passes=PASSES[:1], tree=tree)
    pos = np.searchsorted(us, ds[has])
    for k, img in imgs.items():
        sv = img[tx.y[src], tx.x[src]].astype(np.float64)
        old = img[tx.y[dst], tx.x[dst]].astype(np.float64)
        out = low[k].copy()
        if has.any():
            if k.endswith("Color"):                                            # HDR light: source detail, low-frequency of the hole
                ls = _mean(sv, wts, jjs)[pos].sum(1)
                ld = low[k][has].sum(1)
                sc = np.clip(ld / np.maximum(ls, 1e-6), 0.3, 3.0)
                out[has] = sv[ds[has]] * sc[:, None]
            else:
                out[has] = sv[ds[has]]
        ww = (w[dst] * ok)[:, None]
        res[k] = old * (1 - ww) + out * ww
    sm = 0
    if smooth is not None:                                  # open snow / terrain: membrane fill + measured grain instead of mirrored detail
        sm = _smooth_fill(tx, w, imgs, dst, src, res, ok, smooth, next(iter(imgs.values())).shape[1])
    contact = _contact_shade(tx, w, lum, dst, res, wall & ok, up_d, floor_fn) if lc is not None else 0
    roofed = 0
    if open_fn is not None and lc is not None and len(dst):    # under a roof: never brighter than the shade (25th percentile) around it
        sky = open_fn(tx.P[dst], tx.N[dst])                  # (the lit-preferring mean pulls a sun spill from a door across the floor)
        rf = np.nonzero((sky < OPEN_MIN) & ok)[0]          # floors, walls and roofed snow (hall floor under the removed bags)
        if len(rf):
            # the shade around = the ROOFED sources only (a roofed snow footprint next to the open strip took the lit row)
            sv_ = np.where(wt[rf] > 0, jj[rf], -1)
            us_ = np.unique(sv_[sv_ >= 0])
            rs_ = np.zeros(len(src), bool)
            if len(us_):
                rs_[us_] = open_fn(SP[us_], SN[us_]) < OPEN_MIN
            sl_ = np.where(sv_ >= 0, slum[np.maximum(sv_, 0)], np.nan)
            rsel = (sv_ >= 0) & rs_[np.maximum(sv_, 0)]
            med_r = np.nanpercentile(np.where(rsel, sl_, np.nan), 25, axis=1) if rsel.any() else np.full(len(rf), np.nan)
            med_a = np.nanpercentile(sl_, 25, axis=1)
            med = np.where(rsel.sum(1) >= ROOF_SRC_MIN, med_r, med_a)            # too few roofed sources: all of them, as before
            med = np.where(np.isfinite(med), med, 0.0)
            old_l = lum[dst[rf]]
            new_l = res["basis1_lightColor"][rf].sum(1)
            cap = np.maximum(old_l, med)
            fac = np.where(new_l > cap, cap / np.maximum(new_l, 1e-9), 1.0)
            s_ = np.clip(sky[rf] / OPEN_MIN, 0, 1)
            fac = fac + (1 - fac) * (s_ * s_ * (3 - 2 * s_))        # fades out toward the open sky: no hard edge at the threshold
            for k in res:
                if k.endswith("Color") and res[k] is not None:
                    res[k][rf] *= fac[:, None]
            roofed = int((fac < 1).sum())
    log("    fill: %d grown leftovers, %d black but open now, %d dim snow around holes, %d with a mirrored detail source, %d open snow texels membrane-filled, %d wall texels at the contact shade of the floor seam, %d roofed texels capped at the shade around" % (
        grown, opened, dimmed, int(has.sum()), sm, contact, roofed))
    return dst, res, ok


# ------------------------------------------------------------------------------------------------ per-vertex lit props
VTX_TYPES = (19, 25)
VTX_KEY = "__vertex__"  # repair_level result entry: [(buf offset, new hex, old hex)] in-place light-stream patches  # light-block streams of props without an atlas chart: BentNormalAndAngle, Basis3Luminance (type & 63)


def _pack_rows(orig, base, n, bits, rows, raw):
    """write raw ints (len(rows), len(bits)) of vertex rows into a copy of the stream's bytes (LSB-first, stride sum(bits)) -> bytes"""
    stride = sum(bits)
    nb = (n * stride + 7) // 8
    b = bytearray(orig[base:base + nb])
    for r, vals in zip(rows, raw):
        bo = int(r) * stride
        for c, bw in enumerate(bits):
            if bw:
                v = int(vals[c]) if c < len(vals) else 0
                for k in range(bw):
                    q = bo + k
                    if (v >> k) & 1:
                        b[q >> 3] |= 1 << (q & 7)
                    else:
                        b[q >> 3] &= ~(1 << (q & 7)) & 0xFF
            bo += bw
    return bytes(b)


def _decode_raw(st, raw):
    bits = st["bits"]
    return raw.astype(np.float64) * np.array(st["scale"][:len(bits)]) + np.array(st["off"][:len(bits)])


class _Pts:
    pass


def _vertex_calibration(p, insts, items, gtree, env, log, n=40):
    """(k, cap): k = median over clean lit vertex-lit props (not near the edits) of median(Basis3Luminance sum) / median(surrounding atlas
    lightColor sum, normal-matched); cap = 90th percentile of their vertex light"""
    import bakedao_scan as bs
    rng = np.random.default_rng(1)
    cand = []
    for it in insts:
        for e, i, b in la.draw_items(p, it):
            sts = [st for st in la.light_streams(p, b) if st["type"] & 63 == 25 and st["buf"] and sum(st["bits"]) and st["vcount"] == p.submeshes[i]["vcount"]]
            if sts:
                cand.append((it, i, sts[0]))
    rng.shuffle(cand)
    ks, vals = [], []
    for it, i, st in cand:
        if len(ks) >= n:
            break
        Wv, I = _item_world(p, it, i)
        if Wv is None or len(Wv) > 20000:
            continue
        dg, _ = gtree.query(Wv, distance_upper_bound=REACH + 1)
        if np.isfinite(dg).any():
            continue
        v = _decode_raw(st, bs.unpack_bits(p.d, st["buf"], len(Wv), st["bits"]))[:, :3].sum(1)
        if np.median(v) <= 1e-3:
            continue
        fn = np.cross(Wv[I[:, 1]] - Wv[I[:, 0]], Wv[I[:, 2]] - Wv[I[:, 0]])
        Nv = np.zeros_like(Wv)
        for c in range(3):
            np.add.at(Nv, I[:, c], fn)
        Nv /= np.maximum(np.linalg.norm(Nv, axis=1, keepdims=True), 1e-12)
        sub = rng.choice(len(Wv), min(200, len(Wv)), replace=False)
        e = env(Wv[sub], Nv[sub])
        if not np.isfinite(e).any() or np.nanmedian(e) <= 1e-4:
            continue
        ks.append(np.median(v) / np.nanmedian(e))
        vals.append(v)
    if len(ks) < 5:
        log("    vertex light: calibration failed (%d clean props)" % len(ks))
        return None
    k, cap = float(np.median(ks)), float(np.percentile(np.concatenate(vals), 90))
    log("    vertex light: calibration from %d clean props: k %.3f (iqr %.3f..%.3f), cap %.3f" % (len(ks), k, np.percentile(ks, 25), np.percentile(ks, 75), cap))
    return k, cap


def vertex_repair(lv, p, insts, gT, gkey, goid, log=print, env=None):
    """baked per-vertex light of props with no atlas chart (door frames, trim, boards) buried under / inside now-gone geometry: the same
    occlusion weight as the atlas texels; new values from the lit vertices of the SAME draw item facing the same way (its lit upper part),
    their mean capped at the item's own lit mean.  A prop with no lit vertex of its own is left alone (no light borrowed from the snow).  Streams are rewritten in place (same bit layout, untouched vertices keep their exact bits).
    -> ([(stream buf offset, new bytes hex, old bytes hex)], diag or None)"""
    import bakedao_scan as bs
    from scipy.spatial import cKDTree
    import ghost_shadow_audit as gsa
    lo, hi = gT.reshape(-1, 3).min(0) - REACH, gT.reshape(-1, 3).max(0) + REACH
    gtree = cKDTree(gsa.surface_points(gT, 0.25))
    items = []
    for it in insts:
        if (it.whi < lo).any() or (it.wlo > hi).any():
            continue
        for e, i, b in la.draw_items(p, it):
            if _is_shadow(p, i):
                continue
            sm = p.submeshes[i]
            sts = [st for st in la.light_streams(p, b) if st["type"] & 63 in VTX_TYPES and st["vcount"] == sm["vcount"] and st["buf"] and sum(st["bits"])]
            if not sts:
                continue
            W, I = _item_world(p, it, i)
            if W is None:
                continue
            d, _ = gtree.query(W, distance_upper_bound=REACH)
            if not np.isfinite(d).any():
                continue
            fn = np.cross(W[I[:, 1]] - W[I[:, 0]], W[I[:, 2]] - W[I[:, 0]])
            N = np.zeros_like(W)
            for k in range(3):
                np.add.at(N, I[:, k], fn)
            N /= np.maximum(np.linalg.norm(N, axis=1, keepdims=True), 1e-12)
            raws = {st["type"] & 63: bs.unpack_bits(p.d, st["buf"], len(W), st["bits"]) for st in sts}
            items.append({"rec": it.pak_off, "sub": i, "W": W, "N": N, "I": I, "sts": {st["type"] & 63: st for st in sts}, "raw": raws})
    if not items:
        return [], None
    pt = _Pts()
    pt.P = np.concatenate([x["W"] for x in items])
    pt.N = np.concatenate([x["N"] for x in items])
    pt.own = np.concatenate([np.full(len(x["W"]), k) for k, x in enumerate(items)])
    start = np.r_[0, np.cumsum([len(x["W"]) for x in items])]
    kid = {k: j for j, k in enumerate(gkey)}
    pt.gid = np.array([kid.get((lv, x["rec"], x["sub"]), -1) for x in items], np.int64)
    w, frac, bur = invalid_weight(pt, gT, np.asarray(goid), lambda m: log(m.replace("texels", "vertices")))
    # light value per vertex = Basis3Luminance (else the bent-normal stream) sum
    lum = np.zeros(len(pt.P))
    for k, x in enumerate(items):
        t = 25 if 25 in x["raw"] else 19
        v = _decode_raw(x["sts"][t], x["raw"][t])
        lum[start[k]:start[k + 1]] = v[:, :3].sum(1) if t == 25 else 1.0
    lit = lum > 1e-3
    for k in range(len(items)):
        sl = slice(start[k], start[k + 1])
        m = (w[sl] <= 0) & lit[sl]
        if m.any():
            lit[sl] &= lum[sl] >= 0.3 * np.median(lum[sl][m])
    seed = np.nonzero(w >= 0.5)[0]                          # unlit vertices of a marked item near its marked ones = same artefact
    if len(seed):
        cand = np.nonzero((w < 0.5) & ~lit)[0]
        if len(cand):
            ct = cKDTree(pt.P[cand])
            hits = ct.query_ball_point(pt.P[seed], GROW)
            for s_, h in zip(seed, hits):
                for a in h:
                    if pt.own[cand[a]] == pt.own[s_]:
                        w[cand[a]] = 1.0
    for k in np.unique(pt.own[w >= 0.5]):                  # an item with no lit vertex at all and a buried part: all of it is the artefact
        m = pt.own == k
        if not (lit[m] & (w[m] <= 0)).any():
            w[m] = np.maximum(w[m], 1.0)
    dst = np.nonzero(w > 0)[0]
    src = np.nonzero((w <= 0) & lit)[0]
    if not len(dst):
        log("    vertex light: %d vertex-lit draw items, nothing to repair" % len(items))
        return [], None
    types = sorted({t for x in items for t in x["raw"]})
    V = {}
    for t in types:
        A = np.zeros((len(pt.P), 4))
        for k, x in enumerate(items):
            if t in x["raw"]:
                v = _decode_raw(x["sts"][t], x["raw"][t])
                A[start[k]:start[k + 1], :v.shape[1]] = v
        V[t] = A
    fill = {t: np.zeros((len(dst), 4)) for t in types}
    ok = np.zeros(len(dst), bool)
    own_src = np.zeros(len(dst), bool)
    for k in np.unique(pt.own[dst]):                        # same draw item first
        sel = np.nonzero(pt.own[dst] == k)[0]
        ss = src[pt.own[src] == k]
        if not len(ss):
            continue
        wt, jj, g = _gather(pt.P[ss], pt.N[ss], np.ones(len(ss)), pt.P[dst[sel]], pt.N[dst[sel]])
        for t in types:
            fill[t][sel[g]] = _mean(V[t][ss], wt[g], jj[g])
        if 25 in items[k]["raw"]:                           # never brighter on average than the item's own lit part
            fl = fill[25][sel[g], :3].sum(1)
            cap = lum[ss].mean()
            if len(fl) and fl.mean() > cap:
                fill[25][sel[g]] *= cap / fl.mean()
        ok[sel[g]] = True
        own_src[sel[g]] = True
    # props with no (or hardly any) lit vertex of their own (a trash can buried to the lid): the per-vertex MEDIAN of the lit placements of
    # the same prototype elsewhere in the level, scaled by the repaired light of the surfaces around this one vs around those (never brighter)
    def template(x):
        others = []
        for it in insts:
            if it.pak_off == x["rec"]:
                continue
            for e, i, b in la.draw_items(p, it):
                if i != x["sub"]:
                    continue
                sts = {st["type"] & 63: st for st in la.light_streams(p, b) if st["type"] & 63 in x["sts"] and st["vcount"] == len(x["W"]) and st["buf"] and sum(st["bits"])}
                if set(sts) != set(x["sts"]):
                    continue
                Wo, _ = _item_world(p, it, i)
                if Wo is None:
                    continue
                dg, _ = gtree.query(Wo, distance_upper_bound=REACH)
                if np.isfinite(dg).any():                   # itself near the edits: not a clean reference
                    continue
                vv = {t: _decode_raw(st, bs.unpack_bits(p.d, st["buf"], len(Wo), st["bits"])) for t, st in sts.items()}
                lm = vv[25][:, :3].sum(1) if 25 in vv else np.ones(len(Wo))
                if np.median(lm) > 1e-3:
                    others.append((Wo, vv))
        if not others:
            return None
        scale = 1.0
        if env is not None:
            e0 = env(x["W"])
            eo = [v for v in (env(Wo) for Wo, _ in others) if v]
            if e0 is not None and eo:
                scale = float(np.clip(e0 / np.median(eo), 0.1, 1.0))
        M = {t: np.median(np.stack([vv[t] for _, vv in others]), axis=0) for t in x["sts"]}
        if 25 in M:
            M[25] = M[25] * scale
        return M, scale, len(others)

    tpl = 0
    for k in np.unique(pt.own[dst]):
        x = items[k]
        if 25 not in x["sts"]:
            continue
        sel = np.nonzero(pt.own[dst] == k)[0]
        own_l = fill[25][sel[ok[sel]], :3].sum(1).mean() if ok[sel].any() else 0.0
        if ok[sel].all() and own_l > 0.05:                  # clearly lit by its own upper part: keep the own-item fill
            continue
        tp = template(x)
        if tp is None:
            continue
        M, scale, n = tp
        rows = dst[sel] - start[k]
        tl = M[25][rows, :3].sum(1).mean()
        if ok[sel].all() and own_l >= 0.25 * tl:
            continue
        for t in x["sts"]:
            fill[t][sel, :M[t].shape[1]] = M[t][rows]
        ok[sel] = True
        tpl += 1
        log("    vertex light: %s rec 0x%x: own lit part too dark (%.3f), median of %d lit placements of the prototype x %.2f = %.3f" % (
            p.submeshes[x["sub"]]["name"].split("|")[0].split("/")[-1], x["rec"], own_l, n, scale, tl))
    # still (nearly) black, and its prototype is dark everywhere too (an indoor trash can behind boards we removed): light it from the
    # REPAIRED surfaces it stands against / on, per vertex (normal-matched atlas texels around it), in vertex-light units through a
    # level calibration (median Basis3Luminance / surrounding atlas light of clean lit vertex-lit props), capped at the 90th percentile
    # of the level's lit vertex-lit props
    calib = None
    envd = 0
    for k in np.unique(pt.own[dst]):
        x = items[k]
        if env is None or 25 not in x["sts"]:
            continue
        sel = np.nonzero(pt.own[dst] == k)[0]
        cur = fill[25][sel[ok[sel]], :3].sum(1).mean() if ok[sel].any() else 0.0
        if ok[sel].all() and cur > 0.05:                    # lit by its own upper part / its prototype already
            continue
        e = env(x["W"][dst[sel] - start[k]], x["N"][dst[sel] - start[k]])
        if not np.isfinite(e).any():
            continue
        if calib is None:
            calib = _vertex_calibration(p, insts, items, gtree, env, log)
            if calib is None:
                break
        kk, cap = calib
        tgt = np.clip(np.where(np.isfinite(e), e, np.nanmedian(e)) * kk, 0, cap)
        if cur >= 0.5 * tgt.mean():                         # its own / prototype fill is fine: only the rows nothing filled
            keep = ~ok[sel]
            if not keep.any():
                continue
            sel, tgt = sel[keep], tgt[keep]
        st = x["sts"][25]
        share = np.array([1 / 3.0] * 3)
        fill[25][sel, :3] = tgt[:, None] * share
        if fill[25].shape[1] > 3:
            fill[25][sel, 3] = _decode_raw(st, x["raw"][25])[dst[sel] - start[k], 3] if len(st["bits"]) > 3 else 0
        for t in x["sts"]:
            if t != 25 and not ok[sel].all():
                fill[t][sel, :len(x["sts"][t]["bits"])] = _decode_raw(x["sts"][t], x["raw"][t])[dst[sel] - start[k]]
        ok[sel] = True
        envd += 1
        log("    vertex light: %s rec 0x%x: from the repaired surfaces around it, %.4f -> %.4f (k %.3f, cap %.3f)" % (
            p.submeshes[x["sub"]]["name"].split("|")[0].split("/")[-1], x["rec"], cur, tgt.mean(), kk, cap))
    after = lum.copy()
    patches = []
    for k, x in enumerate(items):
        m = (pt.own[dst] == k) & ok
        if not m.any():
            continue
        rows = dst[m] - start[k]
        ww = w[dst[m]][:, None]
        for t, st in x["sts"].items():
            c = len(st["bits"])
            old_v = _decode_raw(st, x["raw"][t])[rows]
            nv = old_v * (1 - ww) + fill[t][m][:, :c] * ww
            sc, of = np.array(st["scale"][:c]), np.array(st["off"][:c])
            mx = np.array([(1 << b_) - 1 if b_ else 0 for b_ in st["bits"]], np.float64)
            raw = np.clip(np.round((nv - of) / np.where(sc == 0, 1, sc)), 0, mx)
            raw = np.where(sc == 0, x["raw"][t][rows], raw).astype(np.int64)
            n = len(x["W"])
            nbytes = (n * sum(st["bits"]) + 7) // 8
            old = bytes(p.d[st["buf"]:st["buf"] + nbytes])
            nb = _pack_rows(p.d, st["buf"], n, st["bits"], rows, raw)
            chk = bs.unpack_bits(nb + bytes(8), 0, n, st["bits"])
            keep = np.setdiff1d(np.arange(n), rows)
            assert (chk[keep] == x["raw"][t][keep]).all() and (chk[rows] == raw).all(), "vertex light repack"
            if nb != old:
                patches.append((int(st["buf"]), nb.hex(), old.hex()))
            if t == (25 if 25 in x["sts"] else 19) and t == 25:
                after[start[k] + rows] = _decode_raw(st, raw)[:, :3].sum(1)
    log("    vertex light: %d vertex-lit draw items, %d vertices repaired (%d from their own item, %d items from their prototype), %d stream patches" % (
        len(items), int(ok.sum()), int((ok & own_src).sum()), tpl, len(patches)))
    tris = np.concatenate([x["I"] + start[k] for k, x in enumerate(items)])
    return patches, {"P": pt.P, "N": pt.N, "w": w, "before": lum, "after": after, "own": pt.own, "tris": tris,
                     "items": [(x["rec"], x["sub"], p.submeshes[x["sub"]]["name"]) for x in items]}


# ------------------------------------------------------------------------------------------------ seams between levels' snow
SEAM_KEYS = ("snow", "terrain")    # charted ground meshes of different levels that meet (post-office alley snow vs courtyard terrain snow)
SEAM_TOUCH = 0.3         # texels of two sides closer than this (xz, and 0.25 m in y) are seam points
SEAM_BAND = (0.3, 1.5)   # the ratio of the two bakes is measured this far from the seam (the seam edge itself is often darkened)
SEAM_MAX_SHARE = 0.35  # a seam is an edge: at most this share of either side's texels (in the shared box) touches the other
SEAM_MAX_RATIO = 3.0  # two bakes of the same open snow differ by less than this
SEAM_EDGE = 1.5          # the whole chart of the smaller side takes the gain; it fades to 1 over this distance where the chart meets OTHER ground
SEAM_FAR = 25.0          # ... and beyond this distance from the seam (not seen together with the other side any more), over SEAM_EDGE
SEAM_STRIP = 0.25        # the smaller chart is a strip / patch inside the other's ground when it has at most this share of its texels
SEAM_LOCAL = (0.3, 1.0)  # two big charts: local ratio per seam point in this band, both sides meet at the geometric mean over SEAM_D
SEAM_D = 1.5
SEAM_RESID_MAX = 1.5    # the post-repair residual step at a strip's seam is closed up to this ratio
SEAM_LIFT = 2.0          # the chart gain fades (smoothstep) to 1 over this distance from the seam, not across the whole chart
SEAM_CAP_R = 1.0         # the seam gain is capped per texel by its local level (log mean within this reach) against the partner's band level
SEAM_CONT = 1.6          # the fade toward other ground only where the stock bake ran on continuously (within this ratio) across that edge


def _seam_items(p, insts):
    """[(rec, sub, world AABB lo, hi, it)] charted, up-facing ground draw items whose name matches SEAM_KEYS"""
    out = []
    for it in insts:
        for e, i, b in la.draw_items(p, it):
            nm = p.submeshes[i]["name"].lower()
            if _is_shadow(p, i) or not any(k in nm for k in SEAM_KEYS):
                continue
            if la.lm_uv(p, b, p.submeshes[i]["vcount"]) is None:
                continue
            Wv, I = _item_world(p, it, i)
            if Wv is None:
                continue
            out.append((it.pak_off, i, Wv.min(0), Wv.max(0), it))
    return out


def _ground(lv_p, lv_img, lv, lo, hi, insts=None, key=None):
    """up-facing charted texels of a level in a box -> (P, lum, x, y, (rec, sub) per texel)"""
    p = lv_p[lv]
    img, W, H = lv_img[lv]
    tt = Texels(p, W, H, lo, hi, insts)
    m = tt.N[:, 1] > 0.5
    if key is not None:
        m &= np.array([tt.items[o] == key for o in tt.own], bool) if len(tt.own) else np.zeros(0, bool)
    k = [tt.items[o] for o in tt.own[m]]
    return tt.P[m], img[tt.y[m], tt.x[m]].astype(np.float64).sum(1), tt.x[m], tt.y[m], k


def seam_table(paks, srcd, game, work, log=print):
    """seams between the written levels' snow charts, measured on the STOCK atlases (deterministic, independent of the repair).
    One bake ratio per seam (median of each side's band texels); the SMALLER side's whole contiguous chart is scaled to the other side,
    fading to 1 only where that chart meets other ground (or far from the seam).  -> {level: [(xs, ys, gain)]}"""
    from scipy.spatial import cKDTree
    lv_items, lv_img, lv_p, lv_ins = {}, {}, {}, {}
    for f in paks:
        lv = _level_name(f)
        p = ndpak.Pak(f)
        tex = full_textures(p, work, lambda m: None)
        if "basis1_lightColor" not in tex:
            continue
        ins = le.find_instances(p)
        its = _seam_items(p, ins)
        if its:
            lv_items[lv], lv_p[lv], lv_ins[lv] = its, p, ins
            t, fmt, W, H, data = tex["basis1_lightColor"]
            lv_img[lv] = (decode_tex(fmt, W, H, data), W, H)
    full = {}

    def chart(lv, rec, sub, it):                                    # the item's whole up-facing chart
        if (lv, rec, sub) not in full:
            full[(lv, rec, sub)] = _ground(lv_p, lv_img, lv, it.wlo - 0.5, it.whi + 0.5, [it], (rec, sub))
        return full[(lv, rec, sub)]

    pairs, local = [], []
    lvs = sorted(lv_items)
    for a in range(len(lvs)):
        for b in range(a + 1, len(lvs)):
            A, B = lvs[a], lvs[b]
            if A + "-low" == B or B + "-low" == A:              # a distant LOD of the same ground, not a neighbour
                continue
            for ra, sa, loa, hia, ita in lv_items[A]:
                for rb, sb, lob, hib, itb in lv_items[B]:
                    lo, hi = np.maximum(loa, lob) - SEAM_TOUCH, np.minimum(hia, hib) + SEAM_TOUCH
                    if (lo > hi).any():
                        continue
                    blo, bhi = lo - SEAM_BAND[1] - 0.5, hi + SEAM_BAND[1] + 0.5
                    sides = []
                    for lv, rec, sub, it in ((A, ra, sa, ita), (B, rb, sb, itb)):
                        P, L, _x, _y, _k = chart(lv, rec, sub, it)
                        m = (P >= blo).all(1) & (P <= bhi).all(1)
                        sides.append((P[m], L[m]))
                    (PA, LA), (PB, LB) = sides
                    if len(PA) < 20 or len(PB) < 20:
                        continue
                    tb, ta = cKDTree(PB[:, [0, 2]]), cKDTree(PA[:, [0, 2]])
                    dA, jA = tb.query(PA[:, [0, 2]])
                    seam = (dA < SEAM_TOUCH) & (np.abs(PA[:, 1] - PB[jA, 1]) < 0.25)
                    if seam.sum() < 10:
                        continue
                    dB, _ = ta.query(PB[:, [0, 2]])
                    if seam.mean() > SEAM_MAX_SHARE or (dB < SEAM_TOUCH).mean() > SEAM_MAX_SHARE:
                        continue                                # the two cover the same ground (overlap / LOD copy), not an edge
                    SP = 0.5 * (PA[seam] + PB[jA[seam]])
                    sk = cKDTree(SP[:, [0, 2]])
                    bandA = (dA >= SEAM_BAND[0]) & (dA < SEAM_BAND[1]) & (sk.query(PA[:, [0, 2]])[0] < SEAM_BAND[1])
                    bandB = (dB >= SEAM_BAND[0]) & (dB < SEAM_BAND[1]) & (sk.query(PB[:, [0, 2]])[0] < SEAM_BAND[1])
                    if bandA.sum() < 10 or bandB.sum() < 10:
                        continue
                    lg = float(np.log(max(np.median(LB[bandB]), 1e-5) / max(np.median(LA[bandA]), 1e-5)))
                    if abs(lg) > np.log(SEAM_MAX_RATIO):    # a real light difference (roof edge, indoors), not two bakes
                        log("lightmap fix: seam %s s%d x %s s%d: ratio %.2f, left alone" % (A, sa, B, sb, float(np.exp(lg))))
                        continue
                    nA, nB = len(chart(A, ra, sa, ita)[0]), len(chart(B, rb, sb, itb)[0])
                    # local ratio per seam point (band texels of each side within SEAM_D along the seam)
                    kA, kB = cKDTree(PA[(dA >= SEAM_LOCAL[0]) & (dA < SEAM_LOCAL[1])]), cKDTree(PB[(dB >= SEAM_LOCAL[0]) & (dB < SEAM_LOCAL[1])])
                    LbA, LbB = LA[(dA >= SEAM_LOCAL[0]) & (dA < SEAM_LOCAL[1])], LB[(dB >= SEAM_LOCAL[0]) & (dB < SEAM_LOCAL[1])]
                    lp = np.full(len(SP), np.nan)
                    if kA.n and kB.n:
                        for q, (ha, hb) in enumerate(zip(kA.query_ball_point(SP, SEAM_D), kB.query_ball_point(SP, SEAM_D))):
                            if len(ha) >= 3 and len(hb) >= 3:
                                lp[q] = np.log(max(np.median(LbB[hb]), 1e-5) / max(np.median(LbA[ha]), 1e-5))
                    good = np.isfinite(lp)
                    if min(nA, nB) > SEAM_STRIP * max(nA, nB):      # two big grounds: a local feather at the seam, both sides halfway
                        if good.sum() < 5 or abs(np.median(lp[good])) > np.log(SEAM_MAX_RATIO):
                            continue
                        lp = np.clip(lp[good], -np.log(SEAM_MAX_RATIO), np.log(SEAM_MAX_RATIO))
                        local.append((A, ra, sa, ita, SP[good], +0.5 * lp))
                        local.append((B, rb, sb, itb, SP[good], -0.5 * lp))
                        log("lightmap fix: seam %s s%d x %s s%d (both big): %d seam points, local ratio %.2f (median), feathered %.1f m both sides" % (
                            A, sa, B, sb, int(good.sum()), float(np.exp(np.median(lp))), SEAM_D))
                        continue
                    if nA <= nB:                                # the smaller chart is scaled to the bigger one's bake
                        pairs.append((A, ra, sa, ita, +lg, SP, (B, rb, sb), (B, rb, sb, itb), float(np.median(LB[bandB]))))
                    else:
                        pairs.append((B, rb, sb, itb, -lg, SP, (A, ra, sa), (A, ra, sa, ita), float(np.median(LA[bandA]))))
                    log("lightmap fix: seam %s s%d (%d texels) x %s s%d (%d texels): %d seam points, bake ratio %s / %s = %.2f (band medians); %s s%d scaled x%.2f" % (
                        A, sa, nA, B, sb, nB, len(SP), B, A, float(np.exp(lg)), pairs[-1][0], pairs[-1][2], float(np.exp(pairs[-1][4]))))
    # per scaled chart: its seams (a chart with two seams takes, per texel, the gain of the nearest one)
    by = {}
    for lv, rec, sub, it, lg, SP, partner, pit, lvl in pairs:
        by.setdefault((lv, rec, sub), [it, []])[1].append((lg, SP, partner, pit, lvl))
    gain_of = {k: float(np.median([s[0] for s in v[1]])) for k, v in by.items()}
    out = {}
    for (lv, rec, sub), (it, ss) in sorted(by.items(), key=lambda kv: (kv[0][0], kv[0][1], kv[0][2])):
        P, L, xs, ys, _k = chart(lv, rec, sub, it)
        SPall = np.concatenate([s[1] for s in ss])
        lgs = np.concatenate([np.full(len(s[1]), s[0]) for s in ss])
        lvs_ = np.concatenate([np.full(len(s[1]), s[4]) for s in ss])     # the partner's band level at each seam point
        dS, jS = cKDTree(SPall[:, [0, 2]]).query(P[:, [0, 2]])
        lgt = lgs[jS]
        # contiguous with the seam: connected texels (xz, 2.5 texel spacings) that reach a seam point
        sp = float(np.median(cKDTree(P).query(P[:: max(1, len(P) // 2000)], k=2)[0][:, 1]))
        from scipy.sparse import coo_matrix
        from scipy.sparse.csgraph import connected_components
        pr = cKDTree(P).query_pairs(2.5 * sp, output_type="ndarray")
        g_ = coo_matrix((np.ones(len(pr)), (pr[:, 0], pr[:, 1])), shape=(len(P), len(P)))
        nc, lab = connected_components(g_, directed=False)
        keep = np.isin(lab, np.unique(lab[dS < SEAM_TOUCH + 2.5 * sp]))
        # far edges: this chart's texels next to OTHER up-facing ground (any level, not a seam partner, not a chart with the same gain)
        lo, hi = P[keep].min(0) - 1.0, P[keep].max(0) + 1.0
        partners = {s[2] for s in ss}
        prec = {(a, b) for a, b, _c in partners}
        OP, OL, ON = [], [], []
        own = cKDTree(P)
        for olv in lvs:
            Q, QL, _x, _y, kq = _ground(lv_p, lv_img, olv, lo, hi, lv_ins[olv])
            if not len(Q):
                continue
            keys = sorted(set(kq))
            ki = np.array([keys.index(k) for k in kq]) if len(kq) else np.zeros(0, np.int64)
            dq, _ = own.query(Q, distance_upper_bound=sp)
            for n_, key in enumerate(keys):
                mk = ki == n_
                full_key = (olv,) + key
                if (olv, key[0]) in prec or (olv == lv and key[0] == rec):
                    continue                                    # the seam partner's placement (any of its draw items), or its own
                if abs(gain_of.get(full_key, 0.0) - float(np.median(lgs))) <= 0.25:
                    continue                                    # scaled the same way: no step to fade into
                if np.isfinite(dq[mk]).mean() > 0.5:
                    continue                                    # a layer drawn over the same surface (decal / duplicate), not a neighbour
                OP.append(Q[mk]); OL.append(QL[mk]); ON.extend(["%s s%d" % (olv[12:], key[1])] * int(mk.sum()))
        OP = np.concatenate(OP) if OP else np.zeros((0, 3))
        OL = np.concatenate(OL) if OL else np.zeros(0)
        f = np.ones(len(P))
        if len(OP):
            d, j = cKDTree(OP).query(P, distance_upper_bound=SEAM_TOUCH + 2 * sp)
            hit = np.isfinite(d)
            j = np.minimum(j, len(OP) - 1)
            hit &= np.abs(OP[j, 1] - P[:, 1]) < 0.25
            rr = np.log(np.maximum(L, 1e-5) / np.maximum(OL[j], 1e-5))
            hit &= np.abs(rr) < np.log(SEAM_CONT)                     # an interior floor / roofed ground that was already darker: no fade
            if hit.any():
                nm_, c_ = np.unique(np.array(ON)[j[hit]], return_counts=True)
                log("lightmap fix: seam %s s%d: fades at its edge with %s" % (lv, sub, ", ".join("%s (%d)" % (a, b) for a, b in sorted(zip(nm_, c_), key=lambda x: -x[1])[:4])))
                de, _ = cKDTree(P[hit][:, [0, 2]]).query(P[:, [0, 2]])
                f = np.clip(de / SEAM_EDGE, 0, 1)
        f = np.minimum(f, np.clip((SEAM_FAR + SEAM_EDGE - dS) / SEAM_EDGE, 0, 1))
        f = np.minimum(f, np.clip(1 - (dS - SEAM_TOUCH) / SEAM_LIFT, 0, 1))   # only the seam's own band lifts (the hall strip
                                                                               # 2-6 m inside s528 is SP's real shade between buildings)
        f = f * f * (3 - 2 * f)                                            # smoothstep: no kink where the fade ends
        g = np.exp(lgt * f)
        m = keep & (f > 0)
        # the residual step at the seam itself is measured AFTER the repair (the partner's footprint shadows are filled by then):
        # own band texels and the partner's, each with its nearest seam point; closed over SEAM_D on this side only
        fs = np.clip(1 - dS / SEAM_D, 0, 1)
        fs = (fs * fs * (3 - 2 * fs)) * f
        band = keep & (dS >= SEAM_LOCAL[0]) & (dS < SEAM_D)
        par = []
        for plv, prec, psub, pit in sorted({(s[3][0], s[3][1], s[3][2]): s[3] for s in ss}.values(), key=lambda s: s[:3]):
            Q, _QL, qx, qy, _kq = chart(plv, prec, psub, pit)
            dq, jq = cKDTree(SPall[:, [0, 2]]).query(Q[:, [0, 2]])
            dpo = cKDTree(P[:, [0, 2]]).query(Q[:, [0, 2]])[0]
            mq = (dpo >= SEAM_LOCAL[0]) & (dpo < SEAM_D) & (dq < SEAM_D)
            par.append((plv, qx[mq], qy[mq], jq[mq]))
        tm = fs > 0
        out.setdefault("__resid__", []).append({"lv": lv, "sub": sub, "SP": SPall, "own": (xs[band], ys[band], jS[band]),
                                                "par": par, "tex": (xs[tm], ys[tm], jS[tm], fs[tm], P[tm])})
        out.setdefault(lv, []).append((xs[m], ys[m], g[m], P[m], lvs_[jS][m]))
        log("lightmap fix: seam %s s%d: %d of %d chart texels scaled (gain %.2f, %d at full gain, faded at %d texels of other ground)" % (
            lv, sub, int(m.sum()), len(P), float(np.exp(np.median(lgs))), int((keep & (f >= 0.999)).sum()), len(OP)))
    for lv, rec, sub, it, SP, lp in local:
        if (lv, rec, sub) in by:
            continue                                                       # already scaled as a whole
        P, L, xs, ys, _k = chart(lv, rec, sub, it)
        d, j = cKDTree(SP).query(P)
        f = np.clip(1 - d / SEAM_D, 0, 1)
        f = f * f * (3 - 2 * f)
        m = f > 0
        out.setdefault(lv, []).append((xs[m], ys[m], np.exp(lp[j] * f)[m], P[m]))
    return out


def seam_gains(p, W, H, insts, seams):
    """this level's scaled seam-chart texels -> (x, y, gain, world position, partner level (nan: no cap)) arrays"""
    if not seams:
        return np.zeros(0, np.int64), np.zeros(0, np.int64), np.zeros(0), np.zeros((0, 3)), np.zeros(0)
    X = np.concatenate([s[0] for s in seams]).astype(np.int64)
    Y = np.concatenate([s[1] for s in seams]).astype(np.int64)
    G = np.concatenate([s[2] for s in seams])
    P = np.concatenate([s[3] for s in seams])
    T = np.concatenate([s[4] if len(s) > 4 else np.full(len(s[0]), np.nan) for s in seams])
    key = Y * W + X                                                    # a texel drawn by two triangles: one gain
    _, first = np.unique(key, return_index=True)
    return X[first], Y[first], G[first], P[first], T[first]


def _seam_cap(lum, P, g, lvl):
    """the chart gain only lifts (or lowers) a texel's LOCAL level (log mean within SEAM_CAP_R) toward the partner's band level, never past
    it: snow the stock bake already lit to the partner's level keeps its stock value (hall open strip at x1.81)"""
    if not len(g):
        return g
    from scipy.spatial import cKDTree
    ll = np.log(np.maximum(lum, 1e-5))
    hb = cKDTree(P).query_ball_point(P, SEAM_CAP_R)
    loc = np.exp(np.array([ll[h].mean() for h in hb]))
    r = np.where(np.isfinite(lvl), lvl / np.maximum(loc, 1e-5), g)
    return np.where(g >= 1, np.minimum(g, np.maximum(r, 1.0)), np.maximum(g, np.minimum(r, 1.0)))


def _sky_gate(open_fn, P):
    """seam gains only where the snow is under the sky: a snow chart running on under a building (snow in the bakery
    kitchen) keeps its stock bake there -> (n,) factor on the log gain"""
    if not len(P):
        return np.zeros(0)
    s = np.clip(open_fn(P + [0, 0.02, 0], np.tile([0.0, 1.0, 0.0], (len(P), 1))) / OPEN_MIN, 0, 1)
    return s * s * (3 - 2 * s)


def _standing_scene(paths, lo, hi):
    """Embree scene of everything the shipped levels draw in a box (all written levels of the map: a roof can be in another one)"""
    import darkfix_ray as dr
    T = []
    for f in paths:
        q = f if isinstance(f, ndpak.Pak) else ndpak.Pak(f)
        T += [t for _i, _r, _ids, t in dr.level_tris(q, list(lo) + list(hi))]
    if not T:
        return None
    T = np.concatenate(T)
    c = T.mean(1)
    T = T[((c >= lo - 2) & (c <= hi + 2)).all(1)]
    return Caster(T, np.zeros(len(T), np.int64)) if len(T) else None


def _feather(tx, dst, moved, img, W, H):
    """soften the repair's edge in atlas space: texels within 2 of the hole boundary (both sides, same chart) take the Gaussian
    (FEATHER texels) mean of the chart's REPAIRED values around them - the texel stair-step of the hole mask becomes a ramp, without
    a halo (it averages real values, it does not spread the change).  img is changed in place; -> texels changed"""
    import scipy.ndimage as ndi
    n = 0
    r = int(np.ceil(3 * FEATHER)) + 2
    for oi in np.unique(tx.own[dst[moved]]):
        sel = np.nonzero(tx.own == oi)[0]
        hm = moved & (tx.own[dst] == oi)
        hx, hy = tx.x[dst[hm]], tx.y[dst[hm]]
        x0, y0 = max(hx.min() - r, 0), max(hy.min() - r, 0)
        x1, y1 = min(hx.max() + r + 1, W), min(hy.max() + r + 1, H)
        xs, ys = tx.x[sel], tx.y[sel]
        inb = (xs >= x0) & (xs < x1) & (ys >= y0) & (ys < y1)
        xs, ys = xs[inb], ys[inb]
        cov = np.zeros((y1 - y0, x1 - x0), bool)
        cov[ys - y0, xs - x0] = True
        hole = np.zeros_like(cov)
        hole[hy - y0, hx - x0] = True
        band = (ndi.binary_dilation(hole, iterations=2) & ~ndi.binary_erosion(hole, iterations=2, border_value=1)) & cov
        if not band.any():
            continue
        V = img[y0:y1, x0:x1].astype(np.float64)
        cb = ndi.gaussian_filter(cov.astype(np.float64), FEATHER, mode="constant")
        sm = np.stack([ndi.gaussian_filter(np.where(cov, V[:, :, c], 0), FEATHER, mode="constant") for c in range(V.shape[2])], 2)
        sm /= np.maximum(cb, 1e-9)[:, :, None]
        by, bx = np.nonzero(band)
        img[y0 + by, x0 + bx] = sm[by, bx].astype(img.dtype)
        n += len(by)
    return n


# ------------------------------------------------------------------------------------------------ hall region rules
# (a) the baked shadow on the lane / courtyard floor at the lane's south mouth is stair-stepped (low-res bake edge); a
# flat fill of the lane floor made it brighter and flatter = worse; (b) the bakery kitchen showed full-bright snow: the alley's snow chart
# runs on under the bakery roof (sky fraction 0) with the OPEN-SKY bake (L 0.7-0.9, the kitchen floor itself is 0.002-0.02).
HALL_LV = ("pat-jackson-supermarket", "pat-jackson-alley")
HALL_SMOOTH = (                                              # (level, submesh-name part, x0, z0, x1, z1): floor charts whose stair-stepped shadow edges are blurred
    ("pat-jackson-supermarket", "alleyshape", -510.0, 272.5, -504.3, 287.0),          # the lane floor chart (s528)
    ("pat-jackson-supermarket", "snow_chunk_render", -506.0, 266.0, -496.0, 280.0),   # the courtyard snow at the lane's mouth
)
HALL_SIGMA = 6.0                                             # texels (~0.5-0.65 m): bigger than the bake's stair step
HALL_FEATHER = 1.0                                           # m: the blur fades in over this at the box edge
HALL_HOLE_R = 1.0                                            # m: a floor texel under HALL_HOLE_K x the median of its lit floor neighbours within this is a rim / seam hole
HALL_HOLE_K = 0.45
HALL_HOLE_MIN = 0.03                                         # ... when that median is at least this (a really dark area has no holes)
HALL_UNLIT = 0.01                                            # a floor texel below this is unlit (buried in the bake): a hole whatever its neighbours are
HALL_LIT_MIN = 3e-3                                          # unlit (black chart rim / buried) texels neither feed nor take the blur
BRICK_BOX = (-511.5, 273.3, -500.5, 273.9)                   # x0, z0, x1, z1: the brick wall closing the lane at its south end (supermarket pPlaneShape90, faces +z): baked ~0.01 = pitch black in game
BRICK_SRC_R = 12.0                                           # m: lit +z-facing wall texels this close feed its fill (Gaussian BRICK_SIGMA)
BRICK_SIGMA = 4.0
BRICK_MIN = 0.05                                             # a wall texel darker than this is the unlit bake
SEAM_N = (-509.2, 286.5, -506.2, 287.6)                       # x0, z0, x1, z1: the alley snow (chunk-b, alley level) just north of the lane chart s528's north end (z 286.4)
SEAM_N_LEN = 2.4                                             # m: s528 is brought up to chunk-b's level (per channel, lightColor AND baseColor) over its last 2.4 m
SEAM_N_MAX = 1.6                                             # the gain never exceeds this (two bakes of one open snow are within this)
KITCHEN_BOX = (-516.0, 276.0, -508.5, 283.0)                 # the bakery (x0, z0, x1, z1); the alley snow chart (wall plane z 282.5) pokes under its roof
KITCHEN_LEVEL = 0.02                                         # indoor light of the bakery floor / mat (measured 0.002 .. 0.021, sum of lightColor): roofed snow takes it
KITCHEN_SKY = (0.05, 0.25)                                   # sky fraction: fully indoor below the first, the cap fades out to the second


def _hall_rule(lv, p, insts, W, H, new_imgs, open_fn=None, log=print, seam_ref=None):
    """-> bool mask (H, W) of the texels written.
    (a) stair smoothing: per floor chart of HALL_SMOOTH the texels inside the box get a normalised Gaussian blur (HALL_SIGMA, within that
        chart's own lit texels) on all 4 layers, faded in over HALL_FEATHER at the box edge: the step edge of a baked shadow becomes a ramp, the
        chart's gradient and mean stay (no flat value).
    (b) kitchen snow: snow texels of the alley chart inside KITCHEN_BOX whose sky fraction is below KITCHEN_SKY take the indoor level
        (lightColor / baseColor scaled down to KITCHEN_LEVEL), fading out with the sky fraction."""
    import scipy.ndimage as ndi
    ch = np.zeros((H, W), bool)
    if lv not in HALL_LV or "basis1_lightColor" not in new_imgs:
        return ch
    mine = [h for h in HALL_SMOOTH if h[0] == lv]
    if mine:
        # (0) seam / rim holes: the two floor charts meet along x -504.9..-504.5 (z 273.4..276), where the bake left unlit and half-lit rim texels = dark
        # blob + dashes (v37 check).  Such a texel takes the Gaussian mean (world space, across both charts) of its lit neighbours on all 4 layers.
        from scipy.spatial import cKDTree
        bx0 = min(h[2] for h in mine); bz0 = min(h[3] for h in mine); bx1 = max(h[4] for h in mine); bz1 = max(h[5] for h in mine)
        tx = Texels(p, W, H, np.array([bx0 - 0.1, 17.3, bz0 - 0.1]), np.array([bx1 + 0.1, 23.0, bz1 + 0.1]), insts)
        nm = [p.submeshes[i]["name"].lower() for _o, i in tx.items]
        keys = [h[1] for h in mine]
        fl = np.array([any(k in nm[o] for k in keys) for o in tx.own], bool) if len(tx.own) else np.zeros(0, bool)
        fl &= (tx.N[:, 1] > 0.6) & (tx.P[:, 1] < 19.6)
        ii = np.nonzero(fl)[0]
        if len(ii) > 50:
            Lh = new_imgs["basis1_lightColor"][tx.y[ii], tx.x[ii]].astype(np.float64).sum(1)
            tree = cKDTree(tx.P[ii])
            nb = tree.query_ball_point(tx.P[ii], HALL_HOLE_R)
            lit_ = Lh >= HALL_UNLIT
            med = np.array([np.median(Lh[[j for j in h if lit_[j]]]) if any(lit_[j] for j in h) else 0.0 for h in nb])
            hole = (~lit_) | ((Lh < HALL_HOLE_K * med) & (med >= HALL_HOLE_MIN))      # unlit = the bake's buried-texel signature (README), whatever its neighbours are
            ok = ~hole & lit_ & (Lh >= 0.6 * med)                                      # sources: at least 0.6 x the local lit median (not the half-dark rim next to a hole)
            hh = np.nonzero(hole)[0]
            n = 0
            for a in hh:
                src = [j for j in nb[a] if ok[j]]
                if len(src) < 3:
                    src = [j for j in tree.query_ball_point(tx.P[ii[a]], 2.5 * HALL_HOLE_R) if ok[j]]
                if len(src) < 3:
                    continue
                d = np.linalg.norm(tx.P[ii[src]] - tx.P[ii[a]], axis=1)
                wv = np.exp(-(d / 0.5) ** 2) + 1e-6
                for k, img in new_imgs.items():
                    v = (img[tx.y[ii[src]], tx.x[ii[src]]].astype(np.float64) * wv[:, None]).sum(0) / wv.sum()
                    img[tx.y[ii[a]], tx.x[ii[a]]] = v.astype(img.dtype)
                ch[tx.y[ii[a]], tx.x[ii[a]]] = True
                n += 1
            log("    hall holes: %d rim / seam texels (< %.2f x the lit floor around) of %d floor texels refilled from their neighbours" % (n, HALL_HOLE_K, len(ii)))
    for lv_, key, x0, z0, x1, z1 in HALL_SMOOTH:
        if lv_ != lv:
            continue
        tx = Texels(p, W, H, np.array([x0 - 0.1, 17.3, z0 - 0.1]), np.array([x1 + 0.1, 23.0, z1 + 0.1]), insts)
        nm = [p.submeshes[i]["name"].lower() for _o, i in tx.items]
        sel = np.array([key in nm[o] for o in tx.own], bool) if len(tx.own) else np.zeros(0, bool)
        sel &= (tx.N[:, 1] > 0.6) & (tx.P[:, 0] >= x0) & (tx.P[:, 0] <= x1) & (tx.P[:, 2] >= z0) & (tx.P[:, 2] <= z1)
        if sel.sum() < 50:
            continue
        L = new_imgs["basis1_lightColor"][tx.y, tx.x].astype(np.float64).sum(1)
        use = sel & (L > HALL_LIT_MIN)
        e = np.minimum(np.minimum(tx.P[:, 0] - x0, x1 - tx.P[:, 0]), np.minimum(tx.P[:, 2] - z0, z1 - tx.P[:, 2]))
        wgt = np.clip(e / HALL_FEATHER, 0, 1)
        wgt = wgt * wgt * (3 - 2 * wgt)
        wgt = np.maximum(wgt, 0.0)
        # per chart (own item) so charts never bleed into each other
        for oi in np.unique(tx.own[use]):
            m = use & (tx.own == oi)
            xs, ys = tx.x[m], tx.y[m]
            r = int(3 * HALL_SIGMA) + 2
            ax0, ay0 = max(xs.min() - r, 0), max(ys.min() - r, 0)
            ax1, ay1 = min(xs.max() + r + 1, W), min(ys.max() + r + 1, H)
            cov = np.zeros((ay1 - ay0, ax1 - ax0), np.float64)
            cov[ys - ay0, xs - ax0] = 1.0
            cb = ndi.gaussian_filter(cov, HALL_SIGMA, mode="constant")
            for k, img in new_imgs.items():
                V = img[ay0:ay1, ax0:ax1].astype(np.float64)
                sm = np.stack([ndi.gaussian_filter(V[:, :, c] * cov, HALL_SIGMA, mode="constant") for c in range(V.shape[2])], 2) / np.maximum(cb, 1e-9)[:, :, None]
                old = V[ys - ay0, xs - ax0]
                new = old + (sm[ys - ay0, xs - ax0] - old) * wgt[m][:, None]
                img[ys, xs] = new.astype(img.dtype)
            ch[ys, xs] = True
            log("    hall smooth: %s: %d texels blurred (sigma %.0f texels), lightColor %.3f -> %.3f mean" % (nm[oi][-24:], int(m.sum()), HALL_SIGMA, float(L[m].mean()), float(new_imgs["basis1_lightColor"][ys, xs].astype(np.float64).sum(1).mean())))
    if lv == HALL_LV[0] and seam_ref is not None:
        # (d) the lane chart's north end meets the alley's snow (another level, another bake): s528 runs 0.92 against 1.15 there (colour and brightness step,
        # visible as "snow blending").  seam_ref = {kind: (3,) median of chunk-b's stock bake just north of the seam}; s528's own median in its last metre gives the per-channel gain.
        tx = Texels(p, W, H, np.array([SEAM_N[0], 17.3, SEAM_N[1] - SEAM_N_LEN - 0.2]), np.array([SEAM_N[2], 19.6, SEAM_N[1]]), insts)
        nm = [p.submeshes[i]["name"].lower() for _o, i in tx.items]
        isb = (np.array([("alley" in nm[o]) for o in tx.own], bool) if len(tx.own) else np.zeros(0, bool)) & (tx.N[:, 1] > 0.6)
        isb &= (tx.P[:, 0] >= SEAM_N[0]) & (tx.P[:, 0] <= SEAM_N[2])
        band = isb & (tx.P[:, 2] >= SEAM_N[1] - 1.2) & (tx.P[:, 2] <= SEAM_N[1])
        if band.sum() >= 30:
            gz = np.clip((tx.P[:, 2] - (SEAM_N[1] - SEAM_N_LEN)) / SEAM_N_LEN, 0, 1)
            gz = gz * gz * (3 - 2 * gz)
            idx = np.nonzero(isb & (gz > 0))[0]
            for k in ("basis1_lightColor", "basis1_baseColor"):
                if k not in seam_ref or k not in new_imgs:
                    continue
                mine = np.median(new_imgs[k][tx.y[band], tx.x[band]].astype(np.float64)[:, :3], axis=0)
                gain = np.clip(seam_ref[k] / np.maximum(mine, 1e-6), 1.0, SEAM_N_MAX)
                g = 1 + (gain[None, :] - 1) * gz[idx, None]
                img = new_imgs[k]
                v = img[tx.y[idx], tx.x[idx]].astype(np.float64)
                v[:, :3] *= g
                img[tx.y[idx], tx.x[idx]] = v.astype(img.dtype)
                ch[tx.y[idx], tx.x[idx]] = True
                log("    seam north: %s s528 %s -> chunk-b %s, gain %s over the last %.1f m (%d texels)" % (k[6:], mine.round(3), np.asarray(seam_ref[k]).round(3), gain.round(3), SEAM_N_LEN, len(idx)))
    if lv == HALL_LV[0]:
        # (c) the lane's south brick wall: the whole chart is unlit (0.01).  Fill every layer from the lit +z-facing walls around (same facing, Gaussian in world space)
        from scipy.spatial import cKDTree
        x0, z0, x1, z1 = BRICK_BOX
        tx = Texels(p, W, H, np.array([x0 - BRICK_SRC_R, 17.3, z0 - BRICK_SRC_R]), np.array([x1 + BRICK_SRC_R, 22.5, z1 + BRICK_SRC_R]), insts)
        if len(tx.P):
            Lw = new_imgs["basis1_lightColor"][tx.y, tx.x].astype(np.float64).sum(1)
            face = (tx.N[:, 2] > 0.8) & (np.abs(tx.N[:, 1]) < 0.4)
            tgt = np.nonzero(face & (Lw < BRICK_MIN) & (tx.P[:, 0] >= x0) & (tx.P[:, 0] <= x1) & (tx.P[:, 2] >= z0) & (tx.P[:, 2] <= z1))[0]
            src = np.nonzero(face & (Lw > 0.1) & (tx.P[:, 1] < 21.5) & ~((tx.P[:, 0] >= x0) & (tx.P[:, 0] <= x1) & (tx.P[:, 2] >= z0) & (tx.P[:, 2] <= z1)))[0]
            if len(tgt) and len(src) >= 10:
                tree = cKDTree(tx.P[src])
                nb = tree.query_ball_point(tx.P[tgt], BRICK_SRC_R)
                done = 0
                for a, h in zip(tgt, nb):
                    if len(h) < 5:
                        continue
                    d = np.linalg.norm(tx.P[src[h]] - tx.P[a], axis=1)
                    wv = np.exp(-(d / BRICK_SIGMA) ** 2) + 1e-6
                    for k, img in new_imgs.items():
                        img[tx.y[a], tx.x[a]] = ((img[tx.y[src[h]], tx.x[src[h]]].astype(np.float64) * wv[:, None]).sum(0) / wv.sum()).astype(img.dtype)
                    ch[tx.y[a], tx.x[a]] = True
                    done += 1
                log("    brick wall: %d unlit texels (%.3f) of the lane's south wall filled from %d lit +z walls (lightColor %.3f)" % (
                    done, float(np.median(Lw[tgt])), len(src), float(np.median(new_imgs["basis1_lightColor"][tx.y[tgt], tx.x[tgt]].astype(np.float64).sum(1)))))
    if lv == HALL_LV[1] and open_fn is not None:
        x0, z0, x1, z1 = KITCHEN_BOX
        tx = Texels(p, W, H, np.array([x0, 17.3, z0]), np.array([x1, 20.5, z1]), insts)
        if len(tx.P):
            nm = [p.submeshes[i]["name"].lower() for _o, i in tx.items]
            snow = np.array([("snow" in nm[o]) for o in tx.own], bool)
            sel = snow & (tx.N[:, 1] > 0.5) & (tx.P[:, 0] >= x0) & (tx.P[:, 0] <= x1) & (tx.P[:, 2] >= z0) & (tx.P[:, 2] <= z1)
            idx = np.nonzero(sel)[0]
            if len(idx):
                sky = open_fn(tx.P[idx], tx.N[idx])
                a, b = KITCHEN_SKY
                s_ = np.clip((sky - a) / (b - a), 0, 1)
                s_ = s_ * s_ * (3 - 2 * s_)                      # 0 = indoors, 1 = open sky
                L = new_imgs["basis1_lightColor"][tx.y[idx], tx.x[idx]].astype(np.float64).sum(1)
                fac = np.where(L > KITCHEN_LEVEL, KITCHEN_LEVEL / np.maximum(L, 1e-9), 1.0)
                fac = fac + (1 - fac) * s_
                n = int((fac < 0.999).sum())
                for k, img in new_imgs.items():
                    if k.endswith("Color"):
                        img[tx.y[idx], tx.x[idx]] = (img[tx.y[idx], tx.x[idx]].astype(np.float64) * fac[:, None]).astype(img.dtype)
                ch[tx.y[idx[fac < 0.999]], tx.x[idx[fac < 0.999]]] = True
                log("    kitchen snow: %d of %d snow texels under the bakery roof taken to the indoor level %.3f" % (n, len(idx), KITCHEN_LEVEL))
    return ch


def repair_level(lv, ship_path, stock_path, gT, gkey, goid, work, log=print, png=None, seams=None, resid=None, scene_paks=None):
    """-> {kind: (desc, fmt, w, h, new mip0 bytes)} or {} when nothing near the gone geometry has a chart"""
    p = ndpak.Pak(ship_path)
    insts = le.find_instances(p)
    tex = full_textures(p, work, log)
    if not tex or not len(gT):
        vtx, vdiag = vertex_repair(lv, p, insts, gT, gkey, goid, log) if len(gT) else ([], None)
        return ({VTX_KEY: vtx} if vtx else {}), ({"vtx": vdiag} if vdiag else None)
    kinds = sorted(tex)
    _, _, W, H, _ = tex[kinds[0]]
    lo, hi = gT.reshape(-1, 3).min(0) - REACH - FILL_FAR, gT.reshape(-1, 3).max(0) + REACH + FILL_FAR
    from scipy.spatial import cKDTree
    import ghost_shadow_audit as gsa
    gtree = cKDTree(gsa.surface_points(gT, 0.25))
    reach = REACH + FILL_FAR

    def near_fn(T):
        c = T.mean(1)
        r = np.linalg.norm(T - c[:, None], axis=2).max(1)
        d, _ = gtree.query(c, distance_upper_bound=reach + 0.2 + r.max())
        return d <= reach + 0.2 + r

    tx = Texels(p, W, H, lo, hi, insts, near_fn)
    d, _ = gtree.query(tx.P, distance_upper_bound=reach + 0.2) if len(tx.P) else (np.zeros(0), None)
    keep = d <= reach + 0.2
    for a in ("x", "y", "P", "N", "own"):
        setattr(tx, a, getattr(tx, a)[keep])
    kid = {k: j for j, k in enumerate(gkey)}
    tx.gid = np.array([kid.get((lv, o, i), -1) for o, i in tx.items], np.int64)
    log("  %s: atlas %dx%d, %d charted texels near %d gone triangles" % (lv, W, H, len(tx.P), len(gT)))
    w, frac, bur = invalid_weight(tx, gT, np.asarray(goid), log)
    imgs = {k: decode_tex(tex[k][1], W, H, tex[k][4]) for k in kinds}
    bb = tx.P if len(tx.P) else np.concatenate([s[3] for s in (seams or [])] or [np.zeros((1, 3))])
    slo = bb.min(0) - [FILL_FAR + SKY_LEN / 2, 1.0, FILL_FAR + SKY_LEN / 2]
    shi = bb.max(0) + [FILL_FAR + SKY_LEN / 2, SKY_LEN, FILL_FAR + SKY_LEN / 2]
    scene = _standing_scene([p] + [f for f in (scene_paks or []) if os.path.abspath(f) != os.path.abspath(ship_path)], slo, shi)

    def open_fn(Pq, Nq):                                    # SKY fraction of the hemisphere against everything the shipped levels still draw
        if scene is None:
            return np.ones(len(Pq))
        out = np.zeros(len(Pq))
        dirs = _dirs(32)
        for a in range(0, len(Pq), 50000):
            P_, N_ = Pq[a:a + 50000], Nq[a:a + 50000]
            t_, b_ = _basis(N_)
            R = dirs[None, :, 0:1] * t_[:, None] + dirs[None, :, 1:2] * b_[:, None] + dirs[None, :, 2:3] * N_[:, None]
            h = scene.hits(np.repeat(P_ + N_ * 0.02, 32, 0), R.reshape(-1, 3), SKY_LEN, np.full(len(P_) * 32, -1)).reshape(-1, 32)
            out[a:a + 50000] = 1 - h.mean(1)
        return out

    def los(A, NA, B, NB):                                  # source B sees hole texel A through what still stands
        vis = np.ones(len(A), bool)
        if scene is None or not len(A):
            return vis
        A_, B_ = A + NA * LOS_LIFT, B + NB * LOS_LIFT
        D = B_ - A_
        L = np.linalg.norm(D, axis=1)
        idx = np.nonzero(L > 0.15)[0]
        for a in range(0, len(idx), 400000):
            q = idx[a:a + 400000]
            r = scene.s.run(np.ascontiguousarray(A_[q], np.float32), np.ascontiguousarray(D[q] / L[q, None], np.float32), output=1)
            vis[q] = ~((r["primID"] >= 0) & (r["tfar"] < L[q] - 0.05))
        return vis

    def floor_fn(Pq):                                       # distance straight down to what still stands (inf past CONTACT_MAX + 0.5)
        out = np.full(len(Pq), np.inf)
        if scene is None or not len(Pq):
            return out
        for a in range(0, len(Pq), 400000):
            r = scene.s.run(np.ascontiguousarray(Pq[a:a + 400000], np.float32),
                            np.ascontiguousarray(np.tile([0.0, -1.0, 0.0], (len(Pq[a:a + 400000]), 1)), np.float32), output=1)
            hit = (r["primID"] >= 0) & (r["tfar"] <= CONTACT_MAX + 0.5)
            out[a:a + 400000][hit] = r["tfar"][hit]
        return out

    nm = [p.submeshes[i]["name"].lower() for _o, i in tx.items]
    snowy = np.array([any(k in s for k in SEAM_KEYS) for s in nm], bool)
    smooth = (snowy[tx.own] if len(tx.own) else np.zeros(0, bool)) & (tx.N[:, 1] > 0.5)
    dst, vals, ok = fill_values(tx, w, imgs, log, open_fn, smooth, los, floor_fn)
    log("    fill: %d texels changed (%d without a source)" % (int(ok.sum()), int((~ok).sum())))
    new_imgs = {k: imgs[k].copy() for k in kinds}
    nfe = 0
    for k in kinds:
        if vals[k] is not None:
            new_imgs[k][tx.y[dst], tx.x[dst]] = vals[k].astype(np.float32)
            moved = np.abs(vals[k] - imgs[k][tx.y[dst], tx.x[dst]]).max(1) > 1e-6
            if moved.any():
                nfe = max(nfe, _feather(tx, dst, moved, new_imgs[k], W, H))
    log("    feather: repair edge smoothed over %.1f texels within each chart (%d texels)" % (FEATHER, nfe))

    def env(Pq, Nq=None, r=0.75):
        """repaired lightColor of the charted surfaces (walls / ground) around points: per point the mean of the texels within r that face
        the same way (dot > 0.3) -> (n,) with nan where none; Nq None -> one number, the mean over the box"""
        from scipy.spatial import cKDTree as KD
        blo, bhi = Pq.min(0) - r, Pq.max(0) + r
        tt = Texels(p, W, H, blo, bhi, insts)
        if not len(tt.P):
            return None if Nq is None else np.full(len(Pq), np.nan)
        L = new_imgs["basis1_lightColor"][tt.y, tt.x].astype(np.float64).sum(1)
        if Nq is None:
            m = (tt.P >= blo).all(1) & (tt.P <= bhi).all(1)
            return float(L[m].mean()) if m.any() else None
        hits = KD(tt.P).query_ball_point(Pq, r)
        out = np.full(len(Pq), np.nan)
        for q, h in enumerate(hits):
            if h:
                h = np.asarray(h)
                g = h[tt.N[h] @ Nq[q] > 0.3]
                if len(g):
                    out[q] = L[g].mean()
        return out

    vtx, vdiag = vertex_repair(lv, p, insts, gT, gkey, goid, log, env if "basis1_lightColor" in new_imgs else None)
    ch = np.zeros((H, W), bool)
    ch[tx.y[dst[ok]], tx.x[dst[ok]]] = True
    for k in kinds:                                         # the feather ring around the holes changed too
        ch |= np.any(new_imgs[k] != imgs[k], axis=2)
    if seams:                                               # meet the neighbouring level's snow bake at the seam (after the repair)
        sx, sy, sg, sP, sT = seam_gains(p, W, H, insts, seams)
        g0 = sg
        sg = _seam_cap(new_imgs["basis1_lightColor"][sy, sx].astype(np.float64).sum(1), sP, sg, sT)
        log("    seam: %d texels already at the partner's level (gain capped, median x%.2f -> x%.2f)" % (
            int((np.abs(np.log(np.maximum(sg, 1e-6) / np.maximum(g0, 1e-6))) > 0.01).sum()), float(np.median(g0)) if len(g0) else 1, float(np.median(sg)) if len(sg) else 1))
        gate = _sky_gate(open_fn, sP)
        sg = np.exp(np.log(np.maximum(sg, 1e-6)) * gate)
        log("    seam: %d texels roofed over (sky < %.2f), kept at their stock bake" % (int((gate < 0.5).sum()), OPEN_MIN / 2))
        for k in kinds:
            if k.endswith("Color"):
                new_imgs[k][sy, sx] = (new_imgs[k][sy, sx].astype(np.float64) * sg[:, None]).astype(np.float32)
        ch[sy, sx] = True
        log("    seam: %d texels feathered (gain %.2f..%.2f)" % (len(sx), sg.min() if len(sg) else 1, sg.max() if len(sg) else 1))
    for spec, pv in (resid or []):                         # what the chart gain leaves right at the seam, against the partner's REPAIRED bake
        from scipy.spatial import cKDTree as KD
        nb = KD(spec["SP"][:, [0, 2]]).query_ball_point(spec["SP"][:, [0, 2]], SEAM_D)
        ox, oy, oq = spec["own"]
        ol = new_imgs["basis1_lightColor"][oy, ox].astype(np.float64).sum(1)
        pq = np.concatenate([q for _l, _x, _y, q in spec["par"]]) if spec["par"] else np.zeros(0, np.int64)
        pl = np.concatenate(pv) if pv else np.zeros(0)
        r = np.full(len(spec["SP"]), np.nan)
        os_ = [np.nonzero(np.isin(oq, h))[0] for h in nb] if len(oq) else []
        for q, h in enumerate(nb):
            a, b = os_[q] if os_ else [], np.isin(pq, h)
            if len(a) >= 5 and b.sum() >= 5:
                r[q] = np.log(max(np.median(pl[b]), 1e-5) / max(np.median(ol[a]), 1e-5))
        if not np.isfinite(r).any():
            continue
        r = np.clip(np.where(np.isfinite(r), r, np.nanmedian(r)), -np.log(SEAM_RESID_MAX), np.log(SEAM_RESID_MAX))
        tx_, ty_, tq, tf, tP = spec["tex"]
        k_ = ty_ * W + tx_
        _, first = np.unique(k_, return_index=True)
        tx_, ty_, gg = tx_[first], ty_[first], np.exp(r[tq[first]] * tf[first] * _sky_gate(open_fn, tP[first]))
        for k in kinds:
            if k.endswith("Color"):
                new_imgs[k][ty_, tx_] = (new_imgs[k][ty_, tx_].astype(np.float64) * gg[:, None]).astype(np.float32)
        ch[ty_, tx_] = True
        log("    seam s%d: residual at the seam vs the repaired partner x%.2f (median, %.2f..%.2f), closed over %.1f m" % (
            spec["sub"], float(np.exp(np.median(r))), float(np.exp(r.min())), float(np.exp(r.max())), SEAM_D))
    seam_ref = None
    if lv == HALL_LV[0]:
        ap = [g for g in (scene_paks or []) if _level_name(g) == HALL_LV[1]]
        if ap:
            try:
                pa = ndpak.Pak(ap[0])
                ta = full_textures(pa, work, lambda *a: None)
                if not ta or "basis1_lightColor" not in ta:              # the partner is already injected (hash + 1, not in the dicts): its own payload is the repaired atlas
                    ta = {k: (t, t["fmt"], t["w"], t["h"], bytes(pa.d[t["data"]:t["data"] + t["size"]])) for k, t in la.lightmap_textures(pa).items() if t["size"] >= t["w"] * t["h"]}
                if ta and "basis1_lightColor" in ta:
                    Wa, Ha = ta["basis1_lightColor"][2], ta["basis1_lightColor"][3]
                    txa = Texels(pa, Wa, Ha, np.array([SEAM_N[0], 17.3, SEAM_N[1]]), np.array([SEAM_N[2], 19.6, SEAM_N[3]]), le.find_instances(pa))
                    na = [pa.submeshes[i]["name"].lower() for _o, i in txa.items]
                    sel = (np.array([("snow" in na[o]) for o in txa.own], bool) if len(txa.own) else np.zeros(0, bool)) & (txa.N[:, 1] > 0.6)
                    if sel.sum() >= 30:
                        seam_ref = {k: np.median(decode_tex(ta[k][1], Wa, Ha, ta[k][4])[txa.y[sel], txa.x[sel]].astype(np.float64)[:, :3], axis=0) for k in ("basis1_lightColor", "basis1_baseColor") if k in ta}
            except Exception as e:                                   # the seam match is a refinement: never fails the build
                log("    seam north: skipped (%s)" % e)
    ch |= _hall_rule(lv, p, insts, W, H, new_imgs, open_fn, log, seam_ref)   # last: the seam gains above must not undo it
    if ch.any():
        ys, xs = np.nonzero(ch)
        cov = coverage(p, W, H, (xs.min() - 4, ys.min() - 4, xs.max() + 4, ys.max() + 4), insts)
        cov[tx.y, tx.x] = True
        import scipy.ndimage as ndi
        ring = ndi.binary_dilation(ch, iterations=2) & ~cov
        for k in kinds:                                                         # gutter: mean of the covered 5x5 neighbours (new values)
            img = new_imgs[k]
            c = img.shape[2]
            sm = np.stack([ndi.uniform_filter(np.where(cov, img[:, :, j], 0), 5) for j in range(c)], 2)
            cn = ndi.uniform_filter(cov.astype(np.float32), 5)
            r = ring & (cn > 1e-6)
            img[r] = sm[r] / cn[r][:, None]
        blk = np.zeros((H // 4, W // 4), bool)
        yy, xx = np.nonzero(ch | ring)
        blk[yy // 4, xx // 4] = True
        by, bx = np.nonzero(blk)
    else:
        by = bx = np.zeros(0, np.int64)
    out = {VTX_KEY: vtx} if vtx else {}
    if not len(bx):
        log("    nothing to repair in the atlas")
        return out, ({"vtx": vdiag} if vdiag else None)
    for k in kinds:
        t, fmt, w_, h_, data = tex[k]
        out[k] = (t, fmt, w_, h_, encode_blocks(fmt, W, H, data, new_imgs[k], bx, by) if len(bx) else data)
    log("    %d 4x4 blocks re-encoded per layer" % len(bx))
    diag = {"gT": gT, "tx": tx, "w": w, "frac": frac, "bur": bur, "imgs": imgs, "new": new_imgs, "W": W, "H": H, "dst": dst, "ok": ok, "vtx": vdiag}
    return out, diag


def map_levels_of(written):
    """the written render paks this repair applies to.  Not the Part I levels (p1-bookstore): their converted paks carry the full-size
    Part I lightmaps natively (the 'injected layer' test would take them for ours) and have no TLOU2 texture-dict atlas to repair."""
    import p1_src
    return [f for f in written if f.endswith(".pak") and not f.endswith("-phys.pak") and not p1_src.is_part1_level(_level_name(f))]


def _level_name(f):
    return os.path.basename(f)[:-4]


def _sha(f):
    h = hashlib.sha1()
    with open(f, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 24), b""):
            h.update(chunk)
    return h.hexdigest()


def _injected_layers(buf):
    """lightmap layers of a pak that already carry a full-size payload of ours (inject() puts the whole atlas mip0 in the pak; a stock
    level pak only holds a 128x64-class preview, the full atlas comes from the texture dicts) -> [kind]"""
    out = []
    pk = ndpak.Pak(buf) if not isinstance(buf, ndpak.Pak) else buf
    for k, tt in la.lightmap_textures(pk).items():
        d = tt["desc"]
        size, w, h = struct.unpack_from("<I", pk.d, d + 48)[0], struct.unpack_from("<I", pk.d, d + 84)[0], struct.unpack_from("<I", pk.d, d + 88)[0]
        if max(w, h) >= 1024 and size >= (w // 4) * (h // 4) * 16:          # stock in-pak copy: a 128x64 preview
            out.append(k)
    return out


def _rec_path(f):
    """the undo record of ONE pak lives right next to it (<pak>.lmfix.json): it travels with the file, and parallel map builds (one process per
    map, all with the same work dir) never rewrite each other's records.  The shared done.json they used to update (whole-dict read-modify-write) lost
    records to a concurrent writer, so a rerun found an injected pak with no record (build-165b)"""
    return os.path.abspath(f) + ".lmfix.json"


def _save_rec(f, rec):
    p = _rec_path(f)
    with open(p + ".tmp", "w") as fh:
        json.dump(rec, fh, indent=1)
    os.replace(p + ".tmp", p)


def _drop_rec(f):
    try:
        os.remove(_rec_path(f))
    except OSError:
        pass


def _load_done(paks, donef):
    """{abspath: record} of the given paks: their sidecar records, over the legacy shared done.json (read only, entries for these paks)"""
    done = {}
    if os.path.exists(donef):
        try:
            done = json.load(open(donef))
        except ValueError:
            done = {}
    for f in paks:
        a = os.path.abspath(f)
        if os.path.exists(_rec_path(f)):
            try:
                done[a] = json.load(open(_rec_path(f)))
            except ValueError:
                done.pop(a, None)
    return done


def _clean_input(f, done, donef, log):
    """a written pak that already carries our injection but has no matching record under its own path (copied from another work dir,
    or the stage step did not rebuild it): undo it with the record whose 'after' sha it matches, else stop -> never inject twice"""
    a = os.path.abspath(f)
    s = _sha(f)
    d = done.get(a)
    if d and d.get("after") == s:
        return
    inj = _injected_layers(ndpak.Pak(f))
    if not inj:
        return
    for k, v in list(done.items()):
        if v.get("after") == s:
            buf0 = restore(open(f, "rb").read(), v["undo"])
            if hashlib.sha1(buf0).hexdigest() != v["before"]:
                break
            open(f, "wb").write(buf0)
            done.pop(a, None)
            _drop_rec(f)
            log("lightmap fix: %s already carried an injection (same bytes as %s): undone to its stage output" % (_level_name(f), k))
            return
    raise SystemExit("lightmap fix: %s already carries an injected lightmap (%s) and no undo record matches it; delete it so the "
                     "stage step rebuilds it clean" % (f, ", ".join(sorted(inj))))


def apply(written, edits=None, work_dir=None, game=None, log=print, png=None, src_dir=None):
    """build step: repair + inject the atlas of every written render pak whose charted texels meet gone geometry.  In place; idempotent via
    <pak>.lmfix.json next to each pak (sha1 after injection, sha1 before, undo)."""
    if os.environ.get("T2R_NO_LIGHTMAP_FIX"):
        return {}
    work = work_dir or le.CACHE
    cd = _cache_dir(work)
    srcd = src_dir or os.path.join(work, "src")
    donef = os.path.join(cd, "done.json")
    paks = map_levels_of(written)
    done = _load_done(paks, donef)
    for f in paks:                                                  # an input that is ours already: undo it from its record, or stop
        _clean_input(f, done, donef, log)
    pre = {}
    for f in paks:                                                  # sha1 of the geometry-carrying pak before any injection of ours
        s = _sha(f)
        d = done.get(os.path.abspath(f))
        pre[f] = d["before"] if d and d.get("after") == s else s
        if d and d.get("after") == s:
            pre[f + "#done"] = True
    sig = hashlib.sha1(json.dumps([VERSION, probe_fix.spec_sig(), bool(os.environ.get("T2R_PROBE_FIX")), "probe-default-off", os.environ.get("T2R_LMFIX_SALT", ""), sorted((_level_name(f), pre[f]) for f in paks)]).encode()).hexdigest()[:16]
    if all(pre.get(f + "#done") for f in paks) and all(done.get(os.path.abspath(f), {}).get("sig") == sig for f in paks):
        log("lightmap fix: up to date (%s)" % sig)
        return {}
    for f in paks:                                                  # injected by an older run with other inputs: undo that first (exact)
        a = os.path.abspath(f)
        if pre.get(f + "#done") and done[a].get("sig") != sig:
            buf0 = restore(open(f, "rb").read(), done[a]["undo"])
            open(f, "wb").write(buf0)
            if _sha(f) != pre[f]:
                raise SystemExit("lightmap fix: undo of the older injection of %s did not give the stage output back" % f)
            done.pop(a)
            pre.pop(f + "#done")
            _drop_rec(f)
            log("lightmap fix: %s: older injection undone" % _level_name(f))
    # gone geometry over all written levels (cached per signature)
    gf = os.path.join(cd, "gone.%s.npz" % sig)
    if os.path.exists(gf):
        z = np.load(gf, allow_pickle=True)
        gT, gkey, goid = z["T"], [tuple(k) for k in z["key"].tolist()], z["oid"]
        log("lightmap fix: %d gone triangles (cached)" % len(gT))
        paks_g = []
    else:
        paks_g = paks
        gT, gkey, goid = [], [], []
    for f in paks_g:
        lv = _level_name(f)
        src = le.fetch(lv, srcd, game, ("",))[""]
        T, own, oid = gone_triangles(lv, ndpak.Pak(f), ndpak.Pak(src))
        if len(T):
            gT.append(T); goid.append(oid + len(gkey)); gkey += own
            log("lightmap fix: %s: %d gone triangles in %d draw items" % (lv, len(T), len(own)))
    if paks_g:
        if not gT:
            return {}
        gT, goid = np.concatenate(gT), np.concatenate(goid)
        np.savez(gf, T=gT, key=np.array(gkey, dtype=object), oid=goid)
    if not len(gT):
        return {}
    sf = os.path.join(cd, "seams.%s.npz" % sig)
    if os.path.exists(sf):
        seams = np.load(sf, allow_pickle=True)["s"].item()
    else:
        seams = seam_table([f for f in paks if not (pre.get(f + "#done") and done.get(os.path.abspath(f), {}).get("sig") == sig)] and paks, srcd, game, work, log)
        np.savez(sf, s=np.array(seams, dtype=object))
    rep = {}
    specs = seams.get("__resid__", [])
    strip_lvs = {s["lv"] for s in specs}
    samples = {}                                            # (level, spec index) -> partner's repaired lightColor at its band texels
    for f in sorted(paks, key=lambda f: _level_name(f) in strip_lvs):   # seam partners first: their repaired bake is the target
        lv = _level_name(f)
        cf = os.path.join(cd, "%s.%s.npz" % (lv, sig))
        want = [(i, j, x, y) for i, s in enumerate(specs) for j, (plv, x, y, _q) in enumerate(s["par"]) if plv == lv]
        if pre.get(f + "#done") and done.get(os.path.abspath(f), {}).get("sig") == sig:
            if want and os.path.exists(cf):
                samples.update(np.load(cf, allow_pickle=True)["smp"].item())
            continue
        if os.path.exists(cf):
            z = np.load(cf, allow_pickle=True)
            res = z["res"].item()
            samples.update(z["smp"].item())
        else:
            src = le.fetch(lv, srcd, game, ("",))[""]
            mine = [(s, [samples.get((i, j)) for j in range(len(s["par"]))]) for i, s in enumerate(specs) if s["lv"] == lv]
            mine = [(s, pv) for s, pv in mine if all(v is not None for v in pv)]
            res, diag = repair_level(lv, f, src, gT, gkey, goid, work, log, png, seams.get(lv), mine,
                                     [g for g in paks if not _level_name(g).endswith("-low")])
            smp = {}
            if want:
                if diag is not None and "new" in diag:
                    img = diag["new"]["basis1_lightColor"]
                else:
                    tx_ = full_textures(ndpak.Pak(f), work, log).get("basis1_lightColor")
                    img = decode_tex(tx_[1], tx_[2], tx_[3], tx_[4]) if tx_ else None
                if img is not None:
                    smp = {(i, j): img[y, x].astype(np.float64).sum(1) for i, j, x, y in want}
            samples.update(smp)
            if png and diag is not None:
                import darkfix_images
                try:                                                    # review pictures never fail the build
                    darkfix_images.level_images(lv, diag, png)
                except OSError as e:
                    log("    images skipped: %s" % e)
            res = {k: (v if k == VTX_KEY else (int(v[0]["desc"]), int(v[0]["hash"])) + tuple(v[1:])) for k, v in res.items()}
            np.savez(cf, res=np.array(res, dtype=object), smp=np.array(smp, dtype=object))
        res.update(probe_fix.layers(ndpak.Pak(f), _level_name(f), work, log))       # probe cubemaps of the hall (character ambient), same inject / undo
        if not res:
            continue
        buf = open(f, "rb").read()
        n0 = len(buf)
        vtx = res.pop(VTX_KEY, [])
        undo = {"trailer": struct.unpack_from("<I", buf, 32)[0], "descs": [[int(d), buf[d + 40:d + 92].hex(), int(h)] for _k, (d, h, *_r) in sorted(res.items())],
                "vtx": [[o, old] for o, _new, old in vtx]}
        buf = patch_vertex(buf, vtx)
        for k, (desc, h, fmt, w, hh, data, *mp) in sorted(res.items()):
            buf, cnt = inject(buf, desc, h, fmt, w, hh, mp[0] if mp else 1, data, log)
        verify_injected(buf, res, vtx)
        rec = {"before": pre[f], "after": hashlib.sha1(buf).hexdigest(), "sig": sig, "undo": undo}
        _drop_rec(f)                                                # no record may outlive the bytes it describes, whatever stops us between the two writes
        with open(f + ".tmp", "wb") as fh:
            fh.write(buf)
        os.replace(f + ".tmp", f)
        _save_rec(f, rec)
        done[os.path.abspath(f)] = rec
        rep[f] = len(buf) - n0
        log("lightmap fix %s: %d atlas layers injected (+%.1f MB), %d vertex-light streams rewritten" % (lv, len(res), (len(buf) - n0) / 1048576, len(vtx)))
    return rep


def main(argv):
    if argv and argv[0] == "run":
        out = argv[1]
        opt = lambda k, d=None: argv[argv.index(k) + 1] if k in argv else d
        src = opt("--src", os.path.join(out, "..", "..", "src"))
        png = opt("--png")
        work = opt("--work", os.path.join(out, "lmfix"))
        import darkfix_ray as dr
        dst = opt("--dst", os.path.join(work, "paks"))
        os.makedirs(dst, exist_ok=True)
        lvs = [lv for lv in dr.LEVELS if os.path.exists(os.path.join(out, "morph", lv + ".pak")) or os.path.exists(os.path.join(out, lv + ".pak"))]
        import shutil
        written = []
        for lv in lvs:
            f = dr.shipped(out, src, lv)
            g = os.path.join(dst, lv + ".pak")
            if not os.path.exists(g) or os.path.getmtime(g) < os.path.getmtime(f):
                shutil.copyfile(f, g)
            written.append(g)
        apply(written, None, work, None, print, png, src)
        return
    print(__doc__)


if __name__ == "__main__":
    main(sys.argv[1:])
