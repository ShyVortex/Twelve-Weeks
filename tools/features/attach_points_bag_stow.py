"""attach-points.bin: three attach points on the real bone spinec for weapons stowed on the WORN backpack (stowed melee
weapons pivoted around the TOP of the backpack, swung with the bag's top and clipped through the bottom strap loops).

Root cause and the measurement basis: tools/models/backpack_stow.py (module docstring). Short version: machete_holster resolves to the NPC
helper joint r_backpack_holster_attach and targLongGunSlotOne / Two to slot_1_space (a root_helper child), runtime-driven constraint joints
with no bind pose, so a stowed weapon neither rides the bag nor sits in its strap loops. The bag body is skinned to spinec (fatconst /
squash helpers on spinec_helper).

Adds t2r_bs_m / t2r_bs_g1 / t2r_bs_g2 (template points, joint spinec) and the per-look points t2r_bm_<row> / t2r_bg1_<row> / t2r_bg2_<row> (row = t2r-ext look 0..15, joint = the bone carrying that look's bag mesh: spinec or spinea; t2r-ext bs_map swaps the engine's sid for them in the attach-point resolver, so the engine builds their joint binding with the table) ( AP = bind(spinec)^-1 * Abby's authored frame, from data/bag_stow.json) to the sets
player, joel and npc-common. t2r-ext (bp_worn_fix) swaps a worn weapon's attach sid onto them per look; nothing else points at them.
Idempotent, independent of attach_points_base_male.py (each only rewrites its own records, in either order).

  python tools/models/backpack_stow.py            first (writes data/bag_stow.json + tools/ext/bp_stow.h)
  python attach_points_bag_stow.py [attach-points.bin]"""
import json
import os
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from dcfile import DcFile, fnv  # noqa: E402
import attach_points_base_male as base  # noqa: E402

BIN = os.path.join(HERE, "data", "attach-points.bin")
SPEC = json.load(open(os.path.join(HERE, "data", "bag_stow.json")))
NEW = [(name, v.get("joint", SPEC["joint"]), tuple(v["pos"]), tuple(v["quat"])) for name, v in sorted(SPEC["points"].items())]


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
    names = {fnv(n): n for n, *_ in NEW}
    out = {}
    for s in base.SETS:
        obj = base.key_slots(d)[fnv(s)]
        n, p = d.q(obj), d.q(obj + 8)
        out[s] = [(names[d.q(p + 0x50 * i)], d.q(p + 0x50 * i + 8) == fnv(dict((n, j) for n, j, *_ in NEW)[names[d.q(p + 0x50 * i)]]),
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
