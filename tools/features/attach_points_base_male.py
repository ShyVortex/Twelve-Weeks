"""attach-points.bin: sidearm / machete attach points on joints base-male-skel really has (the holstered
pistol was still on the BACK, the holstered machete sat inside the backpack).

Root cause (re/attach-base-male.md has the evidence): every faction look is on base-male-skel (857 joints,
actor97/base-male-skel.pak, common.psarc). The attach-points.bin sets that hold the holster points were authored for the
Ellie / Abby skeletons: 'player' has thigh_pistol_holster / targPistolSlotTwo -> r_leg_holster (a joint ONLY ellie-skel has)
and no machete_holster at all; 'abby' has machete_holster -> backpack_r_side_holster (abby / manny / jesse skeletons only);
'joel' (the faction looks' skeleton name) and 'npc-common' have none of the four. A joint / point the skeleton lacks leaves
the weapon at the model origin (back / inside the bag). base-male-skel carries the NPC holster frames instead:
r_thigh_holster_attach (the game's own NPC pistol point, key 'mike': 8586aac0 -> r_thigh_holster_attach, pos
(-0.0006, -0.0378, -0.0152), quat (0.0836, 0, 0, 0.9965)) and r_backpack_holster_attach (right side of the bag, the
counterpart of Abby's backpack_r_side_holster).

This rewrites the four records (gun_holster, thigh_pistol_holster, targPistolSlotTwo, machete_holster) in the sets
'player', 'joel' and 'npc-common' (whichever the engine picks for a base-male look) to those joints: an extended copy of
the set's record array is appended and the key repointed. Idempotent (an already patched set is rebuilt the same).

  python attach_points_base_male.py [attach-points.bin]       # patches in place, prints a read-back
"""
import os
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from dcfile import DcFile, fnv  # noqa: E402

BIN = os.path.join(HERE, "data", "attach-points.bin")
NKEYS, KEYS_AT, PTRS_AT, TAG = 32, 0x170, 0x68, 0x8f61a86ce475e88d
# (pistols went to a holster spot on models without one, with the rotation wrong, upside down and facing the
# wrong way): the NPC helper joint r_thigh_holster_attach has no bind frame (runtime-driven aim / up constraints), and the supplied pistol
# holster offsets (weapon-art slot objects: pos (0.016, -0.043, 0.032), quat 180 deg about Y) were authored for Abby's thigh frame, which
# turns out to be the plain thigh bone's: r_upper_leg's bind frame * Ry180 puts the pistol muzzle DOWN (-y), its top (sights) forward (+z).
# So the pistol points now sit on REAL bones with measured frames: composite world = Joint * AP * WO (checked on young Abby's record:
# AP (0.022, -0.01, -0.042, Ry180) * WO_gun (0.017, -0.035, -0.068, id) = Abby's AP identity * WO_thigh to 1 cm).
# AP = Joint^-1 * T_des * WO^-1 (tools/features/ap_calc.py, re/attach-base-male.md), T_des from the holster meshes / the back:
#   thigh: muzzle down, sights forward, pistol origin (grip) at model (-0.215, 0.83, 0.065) = in the right thigh pouch of the d-holster
#          (militia-male/female-d-holster: pouch x -0.25..-0.18, y 0.60..0.86, z 0.06..0.15), joint r_upper_leg
#   waist: muzzle down, sights facing back, origin (-0.09, 1.07, -0.07) = tucked in the belt at the right-back hip (pants back z -0.10), joint pelvis
# per-look sidearm points (tools/models/pistol_points.py -> data/pistol_points.json): thigh holster (male / female pouch) and one
# waistband point per look ('t2r_pw_<look row>': right hip, solved from the look's own meshes), all with the supplied offset compensated.
import json as _json
_PP = _json.load(open(os.path.join(HERE, "data", "pistol_points.json")))
THIGH = (tuple(_PP["thigh"]["m"]["pos"]), tuple(_PP["thigh"]["m"]["quat"]))
THIGH_F = (tuple(_PP["thigh"]["f"]["pos"]), tuple(_PP["thigh"]["f"]["quat"]))
BAG = ((0.0, 0.0, 0.0, 1.0), (0.0, 0.0, 0.0, 1.0))
# the thigh points ride the pouch's own skin joint (r_twist_11, pistol_points.THIGH_JOINT), not r_upper_leg: a pistol on r_upper_leg
# rolled with the whole thigh and left the pouch (crouched)
THIGH_JOINT = _PP["thigh"]["m"].get("joint", "r_upper_leg")
THIGH_JOINT_F = _PP["thigh"]["f"].get("joint", "r_upper_leg")
NEW = [      # (point, base-male joint, pos+w, quat)
    ("gun_holster", THIGH_JOINT, THIGH),
    ("thigh_pistol_holster", THIGH_JOINT, THIGH),
    ("targPistolSlotTwo", THIGH_JOINT, THIGH),
    ("t2r_pt_f", THIGH_JOINT_F, THIGH_F),           # the female pouch (t2r-ext pistol_resolve swaps the sid on female looks)
] + [(f"t2r_pw_{i}", "pelvis", (tuple(_PP["waist"][l]["pos"]), tuple(_PP["waist"][l]["quat"]))) for i, l in enumerate(_PP["order"])] + [
    (f"t2r_pw2_{i}", "pelvis", (tuple(_PP["waist2"][l]["pos"]), tuple(_PP["waist2"][l]["quat"]))) for i, l in enumerate(_PP["order"])] + [
    ("machete_holster", "r_backpack_holster_attach", BAG),
]
OBSOLETE = ("t2r_pistol_waist",)
SETS = ("player", "joel", "npc-common")


def rec(point, joint, pos, quat):
    return struct.pack("<QQ4f4f", fnv(point), fnv(joint), *pos, *quat) + bytes(0x20)


def key_slots(d):
    keys = [d.q(KEYS_AT + 8 * i) for i in range(NKEYS)]
    return {k: d.q(PTRS_AT + 8 * i) for i, k in enumerate(keys)}


def patch(data: bytes):
    d = DcFile(data)
    drop = {fnv(p) for p, _, _ in NEW} | {fnv(p) for p in OBSOLETE}
    for s in SETS:
        obj = key_slots(d)[fnv(s)]
        assert d.q(obj + 16) == TAG and d.is_ptr(obj + 8), s
        n, p = d.q(obj), d.q(obj + 8)
        keep = b"".join(bytes(d.data[p + 0x50 * i:p + 0x50 * (i + 1)]) for i in range(n) if d.q(p + 0x50 * i) not in drop)
        blob = keep + b"".join(rec(a, j, pos, q) for a, j, (pos, q) in NEW)
        at = d.append(blob)
        d.set_q(obj, len(blob) // 0x50)
        d.set_ptr(obj + 8, at)
    return d.save()


def readback(data: bytes):
    d = DcFile(data)
    names = {fnv(p): p for p, _, _ in NEW}
    joints = {fnv(j): j for _, j, _ in NEW}
    out = {}
    for s in SETS:
        obj = key_slots(d)[fnv(s)]
        n, p = d.q(obj), d.q(obj + 8)
        out[s] = [(names[d.q(p + 0x50 * i)], joints.get(d.q(p + 0x50 * i + 8), hex(d.q(p + 0x50 * i + 8))),
                   [round(x, 4) for x in struct.unpack_from("<8f", d.data, p + 0x50 * i + 16)])
                  for i in range(n) if d.q(p + 0x50 * i) in names]
    return out


if __name__ == "__main__":
    path = sys.argv[1] if len(sys.argv) > 1 else BIN
    out = patch(open(path, "rb").read())
    again = patch(out)
    assert readback(out) == readback(again)
    open(path, "wb").write(out)
    for s, v in readback(out).items():
        print(s)
        for x in v:
            print("  ", x)
