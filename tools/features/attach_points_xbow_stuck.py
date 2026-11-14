"""attach-points.bin: 't2r_xb_stuck', an IDENTITY point on r_shoulder in every set a player body can use (crossbow bolt in the shoulder).

Why: SP's stuck-arrow points (targRArrowStuck on r_clavicle, arrowShoulderLeft / Right on r_shoulder_arrow_attach, arrowOne..Four, arrowTrailer, leftHandAttach,
rightHandAttach90C) exist ONLY in the 'player' (Ellie) set. 'joel' (the faction looks' set) and 'npc-common' have none of them, so the instant attach 0x141cd2140
(it searches the owner's table with 0x1415f5200 and returns 0 on a miss) failed for every faction look: "bolt re-attached to targRArrowStuck -> 0" on the own body and on
puppets, the bolt stayed on the r_shoulder joint with the joint's identity frame (shaft along the upper arm, through the torso). Dump (sets x names):

    python tools/features/attach_points_xbow_stuck.py --dump

t2r-ext (xbs_tick) attaches the bolt to this point with a closed-loop offset (composite = joint * point * offset, verified from the bolt process' world transform), so the
point itself carries no placement: identity on r_shoulder, which every skeleton (base-male, Ellie, Abby, Lev) has. Idempotent.

  python attach_points_xbow_stuck.py [attach-points.bin]"""
import os
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from dcfile import DcFile, fnv  # noqa: E402
import attach_points_base_male as base  # noqa: E402

BIN = os.path.join(HERE, "data", "attach-points.bin")
JOINT = "r_shoulder"
SETS = base.SETS + ("ellie", "ellie-santabarbara", "marlene-player", "ellie-16-ultimatum", "abby", "lev")
POINT = "t2r_xb_stuck"
IDENT = ((0.0, 0.0, 0.0, 1.0), (0.0, 0.0, 0.0, 1.0))


def patch(data: bytes):
    d = DcFile(data)
    drop = {fnv(POINT)}
    for s in SETS:
        obj = base.key_slots(d)[fnv(s)]
        assert d.q(obj + 16) == base.TAG and d.is_ptr(obj + 8), s
        n, p = d.q(obj), d.q(obj + 8)
        keep = b"".join(bytes(d.data[p + 0x50 * i:p + 0x50 * (i + 1)]) for i in range(n) if d.q(p + 0x50 * i) not in drop)
        blob = keep + base.rec(POINT, JOINT, *IDENT)
        at = d.append(blob)
        d.set_q(obj, len(blob) // 0x50)
        d.set_ptr(obj + 8, at)
    return d.save()


def readback(data: bytes):
    d = DcFile(data)
    out = []
    for s in SETS:
        obj = base.key_slots(d)[fnv(s)]
        n, p = d.q(obj), d.q(obj + 8)
        for i in range(n):
            if d.q(p + 0x50 * i) == fnv(POINT):
                assert d.q(p + 0x50 * i + 8) == fnv(JOINT)
                out.append((s, POINT, [round(x, 5) for x in struct.unpack_from("<8f", d.data, p + 0x50 * i + 16)]))
    return out


def dump(data: bytes):
    d = DcFile(data)
    names = ["targRArrowStuck", "arrowShoulderLeft", "arrowShoulderRight", "arrowOne", "arrowTwo", "arrowThree", "arrowFour", "arrowTrailer", "leftHandAttach",
             "rightHandAttach90C", "leftHand", "rightHand", POINT]
    for s in SETS:
        obj = base.key_slots(d)[fnv(s)]
        n, p = d.q(obj), d.q(obj + 8)
        have = {d.q(p + 0x50 * i) for i in range(n)}
        print(f"{s:20s} {n:4d} points ", " ".join(f"{x}={'Y' if fnv(x) in have else '-'}" for x in names))


if __name__ == "__main__":
    if "--dump" in sys.argv:
        dump(open(BIN, "rb").read())
        sys.exit(0)
    path = sys.argv[1] if len(sys.argv) > 1 else BIN
    out = patch(open(path, "rb").read())
    assert readback(patch(out)) == readback(out) and len(readback(out)) == len(SETS)
    open(path, "wb").write(out)
    for r in readback(out):
        print(*r)
