"""attach-points.bin: the second-sidearm holster points (tools/models/second_holster.py -> data/second_holster.json).
  t2r_pistol_second     weapon-art slot two's own point: a copy of the male thigh point (r_twist_11). It was in no set, so a second sidearm
                        only found a place through t2r-ext's swap and its entry was never patched when the look became known; now the
                        resolver's table patch (pist_patch_table) covers it like the slot-one points
  t2r_bw_<group>        WLF back holster (Abby's holster_back on the back of the belt), on spinea, per look group
  t2r_cr_m / t2r_cr_f   Seraphite chest rig holster (left chest), on m_twist_03
Added to the player / joel / npc-common sets. Idempotent, independent of the other generators.

  python attach_points_second_holster.py [attach-points.bin]"""
import os
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "models"))
from dcfile import DcFile, fnv  # noqa: E402
import attach_points_base_male as base  # noqa: E402

BIN = os.path.join(HERE, "data", "attach-points.bin")
U8_LIMIT = 250          # the engine keeps a point index in a u8 (t2r-ext pist_resolve: past 254 the swap is refused)


def new_points():
    import second_holster
    return [("t2r_pistol_second", base.THIGH_JOINT, base.THIGH[0], base.THIGH[1])] + second_holster.attach_points()


def patch(data: bytes, NEW):
    d = DcFile(data)
    drop = {fnv(n) for n, *_ in NEW}
    for s in base.SETS:
        obj = base.key_slots(d)[fnv(s)]
        assert d.q(obj + 16) == base.TAG and d.is_ptr(obj + 8), s
        n, p = d.q(obj), d.q(obj + 8)
        keep = b"".join(bytes(d.data[p + 0x50 * i:p + 0x50 * (i + 1)]) for i in range(n) if d.q(p + 0x50 * i) not in drop)
        blob = keep + b"".join(base.rec(a, j, pos, q) for a, j, pos, q in NEW)
        assert len(blob) // 0x50 <= U8_LIMIT, f"{s}: {len(blob) // 0x50} points - past the engine's u8 point index"
        at = d.append(blob)
        d.set_q(obj, len(blob) // 0x50)
        d.set_ptr(obj + 8, at)
    return d.save()


def readback(data: bytes, NEW):
    d = DcFile(data)
    want = {fnv(x[0]): x for x in NEW}
    out = []
    for s in base.SETS:
        obj = base.key_slots(d)[fnv(s)]
        n, p = d.q(obj), d.q(obj + 8)
        for i in range(n):
            a = d.q(p + 0x50 * i)
            if a in want:
                assert d.q(p + 0x50 * i + 8) == fnv(want[a][1]), (s, want[a][0])
                out.append((s, want[a][0], want[a][1], [round(x, 5) for x in struct.unpack_from("<8f", d.data, p + 0x50 * i + 16)]))
        out.append((s, "count", n))
    return out


if __name__ == "__main__":
    path = sys.argv[1] if len(sys.argv) > 1 else BIN
    NEW = new_points()
    out = patch(open(path, "rb").read(), NEW)
    assert readback(patch(out, NEW), NEW) == readback(out, NEW)
    assert sum(1 for r in readback(out, NEW) if r[1] != "count") == len(base.SETS) * len(NEW)
    open(path, "wb").write(out)
    for r in readback(out, NEW):
        print(*r)
