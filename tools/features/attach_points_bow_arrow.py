"""attach-points.bin: 't2r_arrow_b1' / 't2r_arrow_b2', the arrow nocked on the string for the two shots of the 2013 execution-bow-right (the arrow
positioning in the bow special execution where the character draws the bow and shoots the enemy was wrong).

execution-bow-right is a real draw-and-shoot (GUNEXEC_SHOT 633 / 2300 ms, no GXS_ARROW; the bow-left pair is the arrow STAB, which keeps t2r_arrow_hand).
Decoded baked pair (re/factions2013/t1anim/bow_arrow_measure.py, TLOU2 base-female rig, both halves in the pair's ap space): the bow is in the LEFT hand
(l_hand_prop), the string hand is the RIGHT one: r_hand_prop to l_hand_prop grows 0.16 -> 0.51 m over frames 0..6 (the draw), the first release is f6.3, then
the hand goes back to the quiver (f8..16, 0.9 - 1.4 m away), is at the bow again at f17 (0.20 m), draws to 0.45 m by f23 = the second release (f23).
The old placement (t2r_arrow_hand, shaft along r_hand_prop +Y, a stab grip) pointed the arrow 93 / 117 deg away from the victim and 100 / 119 deg from the bow.
New: nock at the hand-prop origin (the pivot of the arrow model, string hand), shaft = model +Z rotated onto the wanted direction by the shortest arc;
direction (in r_hand_prop axes) = half toward the bow hand (the shaft runs through the grip), half toward the victim's neck (spined / headb midpoint), mean over
the last three frames before each release (f4-6, f21-23). At the release frame (decoded clips):
  shot 1 (f6)   axis vs victim chest 5.9 deg, head 9.0 deg, bow grip 7.6 deg (grip 0.068 m off the axis)    (identity: 22 / 13 / 15 deg, 0.134 m)
  shot 2 (f23)  axis vs victim chest 9.2 deg, head 5.4 deg, bow grip 7.8 deg (grip 0.061 m off the axis)    (identity: 44 / 33 / 34 deg, 0.248 m)
Added to every set a player body can use (player / joel / npc-common and the Ellie / Abby / Lev sets that IsEllie / IsAbby forced female bodies read). Idempotent.

  python attach_points_bow_arrow.py [attach-points.bin]"""
import os
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from dcfile import DcFile, fnv  # noqa: E402
import attach_points_base_male as base  # noqa: E402

BIN = os.path.join(HERE, "data", "attach-points.bin")
JOINT = "r_hand_prop"
SETS = base.SETS + ("ellie", "ellie-santabarbara", "marlene-player", "ellie-16-ultimatum", "abby", "lev")
# (point, wanted shaft direction in r_hand_prop axes, quat x y z w = shortest arc +Z -> that direction), measured as described above
NEW = [
    ("t2r_arrow_b1", (-0.328, -0.149, 0.933), (0.07564, -0.16692, 0.0, 0.98307)),
    ("t2r_arrow_b2", (-0.387, -0.433, 0.814), (0.22742, -0.20327, 0.0, 0.95235)),
]


def qrot(q, v):
    x, y, z, w = q
    ux, uy, uz = x, y, z
    cx, cy, cz = uy * v[2] - uz * v[1], uz * v[0] - ux * v[2], ux * v[1] - uy * v[0]
    c2 = (cx + w * v[0], cy + w * v[1], cz + w * v[2])
    d = (uy * c2[2] - uz * c2[1], uz * c2[0] - ux * c2[2], ux * c2[1] - uy * c2[0])
    return tuple(v[i] + 2 * d[i] for i in range(3))


def check():
    for name, m, q in NEW:
        n = sum(x * x for x in q) ** 0.5
        assert abs(n - 1) < 1e-3, (name, n)
        t = qrot(q, (0, 0, 1))
        mn = sum(x * x for x in m) ** 0.5
        assert sum(t[i] * m[i] for i in range(3)) / mn > 0.999, (name, t, m)      # the shaft (+Z) lands on the wanted direction


def patch(data: bytes):
    check()
    d = DcFile(data)
    drop = {fnv(n) for n, *_ in NEW}
    for s in SETS:
        obj = base.key_slots(d)[fnv(s)]
        assert d.q(obj + 16) == base.TAG and d.is_ptr(obj + 8), s
        n, p = d.q(obj), d.q(obj + 8)
        keep = b"".join(bytes(d.data[p + 0x50 * i:p + 0x50 * (i + 1)]) for i in range(n) if d.q(p + 0x50 * i) not in drop)
        blob = keep + b"".join(base.rec(a, JOINT, (0.0, 0.0, 0.0, 1.0), q) for a, _, q in NEW)
        at = d.append(blob)
        d.set_q(obj, len(blob) // 0x50)
        d.set_ptr(obj + 8, at)
    return d.save()


def readback(data: bytes):
    d = DcFile(data)
    want = {fnv(x[0]): x[0] for x in NEW}
    out = []
    for s in SETS:
        obj = base.key_slots(d)[fnv(s)]
        n, p = d.q(obj), d.q(obj + 8)
        for i in range(n):
            if d.q(p + 0x50 * i) in want:
                assert d.q(p + 0x50 * i + 8) == fnv(JOINT)
                out.append((s, want[d.q(p + 0x50 * i)], [round(x, 5) for x in struct.unpack_from("<8f", d.data, p + 0x50 * i + 16)]))
    return out


if __name__ == "__main__":
    path = sys.argv[1] if len(sys.argv) > 1 else BIN
    out = patch(open(path, "rb").read())
    assert readback(patch(out)) == readback(out) and len(readback(out)) == len(SETS) * len(NEW)
    open(path, "wb").write(out)
    for r in readback(out):
        print(*r)
