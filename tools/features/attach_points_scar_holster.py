"""attach-points.bin: the Seraphite back-of-belt holster's pistol points (tools/models/scar_back_holster.py).
t2r_pb_m (base-male-skel looks) / t2r_pb_f (base-female-skel looks) on pelvis = data/scar_holster.json "points": the reference Glock with MP's
weapon-art offset lands where SP's Glock sits in Abby's back holster (pelvis_gun_holster_attach * SP offset, measured in the SP sandbox),
moved with the holster outside the coat / under the bag. Added to the player / joel / npc-common sets; t2r-ext pist_map answers a Seraphite
look's first sidearm (gun_holster / thigh_pistol_holster / targPistolSlotTwo) with them. Idempotent, independent of the other generators.

  python attach_points_scar_holster.py [attach-points.bin]"""
import json
import os
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from dcfile import DcFile, fnv  # noqa: E402
import attach_points_base_male as base  # noqa: E402

BIN = os.path.join(HERE, "data", "attach-points.bin")
_J = json.load(open(os.path.join(HERE, "data", "scar_holster.json")))
NEW = [(_J["point_names"][g], _J["joint"], tuple(_J["points"][g]["pos"]), tuple(_J["points"][g]["quat"])) for g in ("m", "f")] + [
    # the male thigh point under its own sid: on a Seraphite look the engine's thigh_pistol_holster entry is rewritten to the back holster (the
    # FIRST sidearm asks for it), so the second sidearm keeps the thigh (its mode 1 place) through this copy
    ("t2r_pt_m", base.THIGH_JOINT, base.THIGH[0], base.THIGH[1])]
# sidearms with their own back-holster point (the Enforcer hung below the tube - its holster_fit t is the thigh pouch's):
# t2r_ph_<art> = the thigh point under the sid the build gives that gun's slot-one attach object (dc_data_patches.alias_sidearm_slot_one), so
# it sits exactly as before on every non-Seraphite look / with the resolver off; t2r_pbm_ / t2r_pbf_<art> = its centred back-holster point
for _art, _e in sorted(_J.get("guns", {}).items()):
    NEW += [("t2r_ph_" + _art, base.THIGH_JOINT, base.THIGH[0], base.THIGH[1]),
            ("t2r_pbm_" + _art, _J["joint"], tuple(_e["m"]["pos"]), tuple(_e["m"]["quat"])),
            ("t2r_pbf_" + _art, _J["joint"], tuple(_e["f"]["pos"]), tuple(_e["f"]["quat"]))]


def patch(data: bytes):
    d = DcFile(data)
    drop = {fnv(n) for n, *_ in NEW}
    for s in base.SETS:
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
    for s in base.SETS:
        obj = base.key_slots(d)[fnv(s)]
        n, p = d.q(obj), d.q(obj + 8)
        for i in range(n):
            if d.q(p + 0x50 * i) in want:
                assert d.q(p + 0x50 * i + 8) in (fnv(_J["joint"]), fnv(base.THIGH_JOINT))
                out.append((s, want[d.q(p + 0x50 * i)], [round(x, 5) for x in struct.unpack_from("<8f", d.data, p + 0x50 * i + 16)]))
    return out


if __name__ == "__main__":
    path = sys.argv[1] if len(sys.argv) > 1 else BIN
    out = patch(open(path, "rb").read())
    assert readback(patch(out)) == readback(out) and len(readback(out)) == len(base.SETS) * len(NEW)
    open(path, "wb").write(out)
    for r in readback(out):
        print(*r)
