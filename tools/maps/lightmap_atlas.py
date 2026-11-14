"""Baked lightmap ("nova mesh atlas") access for level paks.  Offline, CPU only.

Measured (jackson-market, pat-jackson-supermarket.pak):
  placement record (level_edit.find_instances, matrix at o):
    o + 0x98  -> draw-item array, stride 0x70; o + 0xD4 = item count (the store: 27 = its 27 submeshes)
  draw item e:
    e + 0x00  local AABB (min, max, min, max)          e + 0x40 -> per-submesh info      e + 0x48 u32 submesh index (GEOMETRY_1)
    e + 0x50 -> per-INSTANCE light block b (0x80 bytes, one per draw item, also for merged world meshes)
  light block b:
    b + 0x00, b + 0x40: two 64-byte vertex stream descriptors in the GEOMETRY_1 layout (light_streams): the lightmap UV (UV2, type 5 =
    raw half2 or 69 = bit-quantised, raw * scale + off) = atlas uv in [0,1] over the whole atlas; props without a chart carry per-vertex
    BentNormalAndAngle / Basis3Luminance instead, most charted items a constant BakedSunShadow (type 82, 0 bits)
The UV is NOT in the submesh's own vertex streams (that is why an earlier 'walls / snow have no atlas UV' note found none): it is per
placement, so a shared prototype gets one chart per placement.  Atlas = the level's lightmap0 textures (ndpak.textures paths
'.../lightmap0/<level>/...basis1_lightColor.nova_mesh_atlas_dir_0.exr'), the pak has a 64x64 / 128x64 VRAM stub, the real
4096x2048 (supermarket) / 2048x2048 (int) BC6H / BC7 mips live in the texture dict (texdict.find)."""
import os
import struct
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "models"))
import level_edit as le  # noqa: E402

LM_KINDS = ("basis1_lightColor", "basis1_baseColor", "basis1_lightDir", "bentNormal")


def draw_items(p, it):
    """[(item offset, submesh index, light block offset)] of a placement record"""
    o = it.pak_off
    arr, n = p.ptr(o + 0x98), p.u32(o + 0xD4)
    out = []
    if not arr or n > 4096:
        return out
    for k in range(n):
        e = arr + 0x70 * k
        idx = p.u32(e + 0x48)
        b = p.ptr(e + 0x50)
        if idx < len(p.submeshes):
            out.append((e, idx, b))
    return out


def light_streams(p, b):
    """the per-instance vertex streams of a light block: up to 2 GEOMETRY_1-style 64-byte stream descriptors at b, b + 0x40
    (ndpak stream dicts: buf, vcount, size, type, bits, scale, off).  Types seen (exe attribute ids, +64 = bit-quantised):
    5 / 69 = UV2 = the lightmap atlas uv, 82 = BakedSunShadow (18), 83 = BentNormalAndAngle (19), 89 = Basis3Luminance (25)"""
    out = []
    if not b:
        return out
    for so in (b, b + 0x40):
        n = p.u32(so + 8)
        if not n or n > 1 << 22:
            continue
        out.append({"offset": so, "buf": p.ptr(so), "vcount": n, "size": p.u32(so + 16), "type": p.d[so + 20],
                    "bits": list(p.d[so + 24:so + 28]), "scale": struct.unpack_from("<4f", p.d, so + 32),
                    "off": struct.unpack_from("<4f", p.d, so + 48)})
    return out


def decode(p, st, n):
    """(n, k) float values of a light stream (raw half2 for type < 64 with 32 bits, else bit-quantised raw * scale + off)"""
    import bakedao_scan as bs
    if st["type"] < 64 and sum(st["bits"]) == 32:
        return np.frombuffer(p.d, "<f2", 2 * n, st["buf"]).reshape(n, 2).astype(np.float64)
    bits = st["bits"]
    if not st["buf"] or not sum(bits):
        return np.tile(np.array(st["off"], np.float64), (n, 1))
    raw = bs.unpack_bits(p.d, st["buf"], n, bits).astype(np.float64)
    return raw * np.array(st["scale"]) + np.array(st["off"])


def lm_uv(p, b, vcount):
    """(vcount, 2) atlas uv of one draw item's light block (stream type 5 / 69 = UV2), or None"""
    for st in light_streams(p, b):
        if st["type"] & 63 == 5 and st["vcount"] == vcount and st["buf"]:
            return decode(p, st, vcount)[:, :2]
    return None


def lightmap_textures(p):
    """{kind: VRAM_DESC dict} of a level pak's lightmap atlas"""
    import ndpak
    out = {}
    for t in ndpak.textures(p):
        if "/lightmap0/" not in t["path"]:
            continue
        for k in LM_KINDS:
            if "/" + k + "." in t["path"]:
                out[k] = t
    return out


def world_items(p, box, insts=None):
    """every drawn submesh of placements meeting box: [(record, item off, submesh, world verts (n,3), tri idx (m,3), atlas uv (n,2) or None)]"""
    lo, hi = np.array(box[:3]), np.array(box[3:])
    insts = insts if insts is not None else le.find_instances(p)
    out = []
    for it in insts:
        if (it.whi < lo).any() or (it.wlo > hi).any():
            continue
        for e, i, b in draw_items(p, it):
            sm = p.submeshes[i]
            P = le._qpos(p, sm)
            if P is None or not sm["icount"]:
                continue
            W = (np.c_[P, np.ones(len(P))] @ it.M)[:, :3]
            if (W.max(0) < lo).any() or (W.min(0) > hi).any():
                continue
            I = np.array(p.indices(sm), np.int64).reshape(-1, 3)
            out.append((it, e, i, W, I, lm_uv(p, b, sm["vcount"])))
    return out
