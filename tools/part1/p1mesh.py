"""Part I PC geometry + skeleton reader (read-only), producing the mesh dicts `tools/models/mesh_replace.py` takes.

Layout (verified on t1x-pistol-shotgun / t1x-pistol-uber-t1, see re/part1/day-one-results.md):
  GEOMETRY_1 item (payload at +48): u32 +8 submesh count, ptr +40 submesh array, 176-byte submeshes (TLOU2: 192)
  submesh: bbox +0, stream descs ptr +0x30 (64-byte records exactly as TLOU2: buf ptr, count, size, type byte +20,
  bit widths +24..27, scale +32, offset +48), index ptr +0x40 (u16), material ptr +0x48, skin ptr +0x58,
  counts +0x80 / +0x84 / +0x88 (verts, indices, streams)
  streams: 64 position, 65 / 75 / 76 UV sets (bit-packed, quantized), 130 tangent frame (u32 quaternion record),
  type 4 = half4 vertex colour: R / G / B weight the material's extra layers (BaseColor05 / 03 / 02), see p1_guns.py;
  other types (6, 20, 68, 70) blend extras - ignored here
  skin: ptr +16 per-vertex (count, byte offset) pairs, ptr +24 u32 weights (joint << 22 | 22-bit weight)
  JOINT_HIERARCHY (payload +48): u32 +20 joint count, ptr +32 transforms, ptr +56 names (16-byte records, name ptr at +8)
Joint indices of a gun pak refer to the shared base skeleton (`pistol-base.pak` / `t1x-rifle-base.pak`), not to the gun pak.

  python p1mesh.py <pak> [<base pak>]      # submesh table with LOD guess, materials, joints used
"""
import collections
import os
import struct
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "models"))
import ndpak  # noqa: E402
import p1_pak  # noqa: E402
from mesh_replace import _frame_decode  # noqa: E402

PAD = p1_pak.PAD
UVS = (65, 75, 76)


class P1Mesh(p1_pak.P1Pak):
    def geometry_items(self):
        return [self.pages[pg][0] + off for pg, off in self.of_type("GEOMETRY_1")]

    def submesh_table(self):
        """[{offset, vcount, icount, nstreams, material, skin, streams[{buf, type, bits, scale, off, nv}]}]"""
        out = []
        for io in self.geometry_items():
            base = io + PAD
            cnt, arr = self.u32(base + 8), self.ptr(base + 40)
            for i in range(cnt):
                o = arr + 176 * i
                sm = {"offset": o, "vcount": self.u32(o + 0x80), "icount": self.u32(o + 0x84),
                      "nstreams": self.u32(o + 0x88), "material": self.ptr(o + 0x48), "skin": self.ptr(o + 0x58),
                      "index": self.ptr(o + 0x40), "streams": []}
                sa = self.ptr(o + 0x30)
                for j in range(min(sm["nstreams"], 16)):
                    so = sa + 64 * j
                    sm["streams"].append({"buf": self.ptr(so), "nv": self.u32(so + 8), "type": self.d[so + 20],
                                          "bits": list(self.d[so + 24:so + 28]),
                                          "scale": struct.unpack_from("<4f", self.d, so + 32),
                                          "off": struct.unpack_from("<4f", self.d, so + 48)})
                out.append(sm)
        return out

    def lods(self, table=None):
        """submesh indices per LOD: a LOD starts when a material repeats non-adjacently (materials appear once per LOD, split partitions are adjacent)"""
        table = table or self.submesh_table()
        seq, cur, seen, prev = [], [], set(), None
        for i, t in enumerate(table):
            m = t["material"]
            if m in seen and m != prev:       # a material seen before, not an adjacent partition: next LOD
                seq.append(cur)
                cur, seen = [], set()
            cur.append(i)
            seen.add(m)
            prev = m
        seq.append(cur)
        return seq

    def mesh(self, sm):
        """-> dict P (n,3) N T (n,3) UV [(n,2)...] I (m,3) J (n,) W (n,) (first influence only), tri index arrays"""
        n = sm["vcount"]
        out = {"UV": [None, None, None]}
        for st in sm["streams"]:
            s = {"buf": st["buf"], "bits": st["bits"], "scale": st["scale"], "off": st["off"]}
            if st["type"] == 64:
                out["P"] = np.array(ndpak.Pak.decode_quantized(self, s, n, 3), float)
            elif st["type"] == 0 and "P" not in out:        # raw float3 positions (some foreground meshes)
                out["P"] = np.frombuffer(self.d, "<f4", n * 3, st["buf"]).reshape(n, 3).astype(float)
            elif st["type"] in UVS:
                out["UV"][UVS.index(st["type"])] = np.array(ndpak.Pak.decode_quantized(self, s, n, 2), float)
            elif st["type"] == 4 and sum(st["bits"]) == 64:     # half4 vertex colour = material layer weights (R, G, B)
                out["C"] = np.frombuffer(self.d, np.float16, n * 4, st["buf"]).reshape(n, 4).astype(float)
            elif st["type"] == 130:
                recs = np.frombuffer(self.d, np.uint32, n, st["buf"])
                T = np.zeros((n, 3))
                N = np.zeros((n, 3))
                H = np.ones(n)
                for v, r in enumerate(recs):
                    T[v], N[v] = _frame_decode(int(r))
                    H[v] = 1.0 if int(r) & 0x80000000 else -1.0
                out["T"], out["N"], out["H"] = T, N, H
        out["I"] = np.frombuffer(self.d, np.uint16, sm["icount"], sm["index"]).reshape(-1, 3).astype(np.int64)
        if sm["skin"]:
            imap, wts = self.ptr(sm["skin"] + 16), self.ptr(sm["skin"] + 24)
            J = np.zeros(n, np.int64)
            Wt = np.zeros(n)
            for v in range(n):
                c, at = struct.unpack_from("<II", self.d, imap + 8 * v)
                best = 0.0
                for k in range(c):
                    w = self.u32(wts + at + 4 * k)
                    f = (w & 0x3FFFFF) / 0x3FFFFF
                    if f >= best:
                        best, J[v] = f, w >> 22
                Wt[v] = best
            out["J"], out["W"] = J, Wt
        return out

    def material_textures(self, mat):
        """{'g_tNdFetchBaseColor01Map': vram hash, ...} of a material record (same layout as TLOU2)"""
        texl = self.ptr(mat + 32)
        tc = self.u32(mat + 64 + 208 + 4)
        out = {}
        for j in range(min(tc, 64)):
            e = texl + 48 * j
            nm, td = self.ptr(e), self.ptr(e + 24)
            if nm and td:
                out[self.cstr(nm)] = self.u64(td + 8)
        return out

    def material_name(self, mat):
        return self.cstr(self.ptr(mat))


def joints(pak):
    """-> [{name, parent, pos(3), world(3)}] of the first JOINT_HIERARCHY in a Part I or TLOU2 pak (P1Pak / ndpak.Pak)"""
    if isinstance(pak, p1_pak.P1Pak):
        io = pak.pages[pak.of_type("JOINT_HIERARCHY")[0][0]][0] + pak.of_type("JOINT_HIERARCHY")[0][1]
        u64 = pak.u64
    else:
        io = [i for _n, t, _p, i in pak.items if t == "JOINT_HIERARCHY"][0]
        u64 = pak.q
    b = io + PAD
    n = pak.u32(b + 20)
    xf, names = pak.ptr(b + 32), pak.ptr(b + 56)
    xcount = struct.unpack_from("<H", pak.d, xf + 18)[0]
    hsize = pak.u32(xf + 32)
    hier = pak.u32(xf + 60)
    tstart = xf + hsize
    loc = []
    for i in range(min(xcount, n)):
        o = tstart + 48 * i
        q = struct.unpack_from("<4f", pak.d, o + 16)
        p = struct.unpack_from("<3f", pak.d, o + 32)
        loc.append((q, p))
    hs = pak.u32(xf + hier + 20)
    pstart = xf + hier + 20 + 4 + hs - 24
    out = []
    for i in range(n):
        par = struct.unpack_from("<4i", pak.d, pstart + 16 * i)[1]
        nm = pak.ptr(names + 16 * i + 8)
        out.append({"name": pak.cstr(nm) if nm else "?", "parent": par,
                    "pos": loc[i][1] if i < len(loc) else (0, 0, 0)})
    return out


def main(argv):
    k = P1Mesh(argv[1])
    t = k.submesh_table()
    names = [j["name"] for j in joints(P1Mesh(argv[2]))] if len(argv) > 2 else None
    for li, lod in enumerate(k.lods(t)):
        print("LOD", li, lod)
    for i, s in enumerate(t):
        m = k.mesh(s)
        jc = collections.Counter(m["J"].tolist()) if "J" in m else {}
        lab = {(names[j] if names and j < len(names) else j): c for j, c in list(jc.most_common(5))}
        print(i, s["vcount"], s["icount"] // 3, hex(s["material"]), k.material_name(s["material"]).split(":")[0].split("/")[-1], lab)


if __name__ == "__main__":
    main(sys.argv)
