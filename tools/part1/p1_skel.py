"""JOINT_HIERARCHY reader for Part I (0xA7D) and TLOU2 (0xA79) skeleton paks: joint names, parents, bind pose.

Same item layout in both games (re/uc4ps4/tools/t2skel.py for TLOU2; p1mesh.joints): only the pak container differs, so
this takes either and exposes the T2Skel interface that re/uc4ps4/tools/retarget.Target expects:
  .nj, .names, .parent, .bind (xform rows: scale xyz,pad | quat xyzw | pos xyz,pad, one per ANIMATED joint),
  .xform_count, .sig (hierarchy signature = ClipData +4 of clips authored on this rig, when found)
  python p1_skel.py <skel.pak>      joints, parents, animated count, groups"""
import os
import struct
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path[:0] = [HERE, os.path.join(os.path.dirname(HERE), "models")]
import ndpak  # noqa: E402
import p1_pak  # noqa: E402

PAD = 48


def open_pak(path):
    v = struct.unpack_from("<I", open(path, "rb").read(4))[0]
    if v in (2685, 68221):
        return p1_pak.P1Pak(path)
    return ndpak.Pak(path)


class Skel:
    def __init__(self, path):
        p = self.p = open_pak(path)
        d = p.d
        if isinstance(p, p1_pak.P1Pak):
            pg, off = p.of_type("JOINT_HIERARCHY")[0]
            io = p.pages[pg][0] + off
            ptr = p.ptr
        else:
            io = [x for x in p.items if x[1] == "JOINT_HIERARCHY"][0][3]

            def ptr(a):
                return p.pages[p.fix[a]][0] + struct.unpack_from("<Q", d, a)[0]
        base = io + PAD
        u32 = lambda o: struct.unpack_from("<I", d, o)[0]   # noqa: E731
        self.nj = u32(base + 20)
        xo = ptr(base + 32)
        no = ptr(base + 56)
        node_count, xform_count = struct.unpack_from("<2H", d, xo + 16)
        hdr = struct.unpack_from("<10I", d, xo + 24)
        header_size, hier_off = hdr[2], hdr[9]
        self.xform_count = xform_count
        self.hier_sig = u32(xo + 4)
        ts = xo + header_size
        self.bind = np.frombuffer(d, dtype=np.float32, count=xform_count * 12, offset=ts).reshape(xform_count, 12).copy()
        ho = xo + hier_off + 20
        ps = ho + 4 + u32(ho) - 24
        self.parent4 = [struct.unpack_from("<4i", d, ps + 16 * b) for b in range(self.nj)]
        self.parent = [t[1] for t in self.parent4]
        self.names = []
        for b in range(self.nj):
            sp = ptr(no + 16 * b + 8)
            self.names.append(d[sp:d.index(b"\0", sp)].decode("latin1"))
        self.xo = xo

    def animated(self):
        """joint indices in animated (xform / clip row) order: the joints under the root, index order (as Target.bm)"""
        par = self.parent

        def root_of(i):
            while par[i] != -1:
                i = par[i]
            return i
        return [b for b in range(self.nj) if root_of(b) == 0]


if __name__ == "__main__":
    s = Skel(sys.argv[1])
    bm = s.animated()
    print(f"joints {s.nj}, xforms {s.xform_count}, animated (under root) {len(bm)}, hier word {s.hier_sig:08x}")
    for i in range(s.nj):
        print(i, s.names[i], s.parent[i])
