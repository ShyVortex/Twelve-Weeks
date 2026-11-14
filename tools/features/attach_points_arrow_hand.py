"""attach-points.bin: 't2r_arrow_hand', where the TLOU2 arrow model sits in the attacker's right hand during the 2013 bow execution (previously:
the arrow was visible but its position and rotation in the hand were entirely wrong).

2013 has no arrow data (the bow prop clips are 4 joints, no arrow channel; re/factions2013/exec-weapon-anims.md), so the placement is derived from the
2013 hand pose in the baked execution-bow-left pair (re/factions2013/t1anim decode of t1gx-execution-bow-left--atk / --vic, both bodies in the pair's
ap space, TLOU2 base-female rig, r_hand_prop frame): from the first stab (0.6 s) to the last (2.9 s) the direction from the right hand-prop joint to
the victim's chest (spined) is, in the r_hand_prop axes (x, y, z), (-0.05..0.26, 0.73..1.00, -0.18..0.67): +Y of r_hand_prop points at the victim in
every frame (>= 0.94 in 19 of 24), at 0.40-0.59 m. So the stab is an icepick grip with the arrow's tip out of the +Y side of the fist (the forearm
sits ~45 deg off it: forearm in prop axes (-0.1, 0.6, 0.75)). execution-bow-right decodes with its victim far from both hands in the same space
(1.1-1.6 m), so it gives no independent contact; its hand-prop frame vs forearm is the same, and it is mirrored from the left pair.
TLOU2 arrow model (actor97/arrow-scar.pak, sp-common.psarc): ONE mesh, shaft along +Z, nock / fletching end at z = -0.014 (vanes 0.07 wide), broadhead
tip at z = 0.815 (0.83 m long), pivot at the NOCK (origin), same axes as the arrow nocked on bow-scar (z forward). The old attach ('rightHand' =
r_hand_prop, identity) therefore put the nock at the palm with the shaft along +Z of the hand = the forearm direction (r_hand_prop z . forearm = 0.98
at bind): the shaft ran along the forearm, tip beyond the hand, as seen in game.
Placement: model +Z -> r_hand_prop +Y (rotation -90 deg about X: model Y -> prop -Z), the fist closed on the shaft 0.36 m in front of the nock, i.e. the
tip stands 0.455 m out of the hand (the 2013 hand-to-chest distance of 0.40-0.59 m minus a little penetration). Added to the player / joel / npc-common
sets on r_hand_prop (the frame 'rightHand' of the player set uses). Idempotent.

  python attach_points_arrow_hand.py [attach-points.bin]"""
import os
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from dcfile import DcFile, fnv  # noqa: E402
import attach_points_base_male as base  # noqa: E402

BIN = os.path.join(HERE, "data", "attach-points.bin")
GRIP_Z = 0.36                      # arrow-scar model z that sits at the hand-prop origin
S = 0.70710678
# the female sets too (IsEllie / IsAbby forced female bodies read them; the point was missing there)
SETS = base.SETS + ("ellie", "ellie-santabarbara", "marlene-player", "ellie-16-ultimatum", "abby", "lev")
# the stab hand is now the tight fist (bake_t1 GRIP_HANDS execution-bow-left, was the string pinch with the
# fingers 1-4 cm off the shaft) and the arrow is fitted to it by re/factions2013/t1anim/arrow_grip_fit.py: shaft 7 deg off the old +Y direction (the knuckle line is 16 deg off it),
# fist still 0.36 m from the nock (the tip keeps its reach); index / middle / ring close on the shaft within 0.6-1.8 cm, pinky 2.9 cm. (Before: pos (0, -GRIP_Z, 0), quat (-S 0 0 S)
# = shaft along +Y exactly.)
NEW = [("t2r_arrow_hand", "r_hand_prop", (-0.0397, -0.3209, 0.0458, 1.0), (0.44087, 0.58966, 0.57425, -0.35800))]


def patch(data: bytes):
    d = DcFile(data)
    drop = {fnv(n) for n, *_ in NEW}
    for s in SETS:
        obj = base.key_slots(d)[fnv(s)]
        assert d.q(obj + 16) == base.TAG and d.is_ptr(obj + 8), s
        n, p = d.q(obj), d.q(obj + 8)
        keep = b"".join(bytes(d.data[p + 0x50 * i:p + 0x50 * (i + 1)]) for i in range(n) if d.q(p + 0x50 * i) not in drop)
        blob = keep + b"".join(base.rec(a, j, pos, q) for a, j, pos, q in NEW)
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
                assert d.q(p + 0x50 * i + 8) == fnv(NEW[0][1])
                out.append((s, want[d.q(p + 0x50 * i)], [round(x, 5) for x in struct.unpack_from("<8f", d.data, p + 0x50 * i + 16)]))
    return out


if __name__ == "__main__":
    path = sys.argv[1] if len(sys.argv) > 1 else BIN
    out = patch(open(path, "rb").read())
    assert readback(patch(out)) == readback(out) and len(readback(out)) == len(SETS) * len(NEW)
    open(path, "wb").write(out)
    for r in readback(out):
        print(*r)
