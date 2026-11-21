"""attach-points.bin: SP's own backpack stow frames for the worn bag, measured in single player with the SP sandbox (Abby run,
re/sp-sandbox-runs/ (the Abby capture log), tools/sp-sandbox): Abby's long guns ride slot_1_space / slot_2_space and her melee rides
backpack_r_side_holster, all three locked to backpack_fatconst (the bag's sway bone - spread 0.2 .. 3 cm over 140+ snapshots while
running / sprinting / crouching), so a stowed weapon moves with the bag. base-male-skel (every MP look) has backpack_fatconst too.
Adds t2r_fc_m / t2r_fc_g1 / t2r_fc_g2 = AP relative to backpack_fatconst (World = fatconst * AP * weapon offset, solved from the
logged world frames; the same AP from different weapons on one slot agrees to < 1 cm) to the player / joel / npc-common sets;
t2r-ext bs_map answers machete_holster / targLongGunSlotOne / Two with them.  Idempotent, independent of the other generators.

  python attach_points_sp_bag.py [attach-points.bin]"""
import os
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from dcfile import DcFile, fnv  # noqa: E402
import attach_points_base_male as base  # noqa: E402

BIN = os.path.join(HERE, "data", "attach-points.bin")
J = "backpack_fatconst"
NEW = [   # name, joint, pos (x y z w), quat (x y z w) - from tools/sp-sandbox sp_rel solve, Abby run
    ("t2r_fc_m", J, (-0.1608, 0.1093, 0.0632, 1.0), (0.6052, 0.0468, -0.0203, 0.7944)),
    ("t2r_fc_g1", J, (0.1596, -0.0142, 0.0322, 1.0), (-0.0756, -0.7859, -0.6135, 0.0182)),
    # slot two: NOT SP's slot_2_space solve (0.2160 -0.0410 -0.0020 / -0.0231 0.7375 0.6679 0.0974) - that one assumed SP's
    # holster offsets, MP's weapon art has its own, and the Double Barrel crossed the Vepr. = t2r_fc_g1 * MP slot-one offset * (the DB-behind-
    # the-Vepr relation chosen) * MP slot-two offset^-1, tools/models/backpack_slot2.py (mesh overlap check there).
    ("t2r_fc_g2", J, (0.18917, 0.04798, 0.09744, 1.0), (-0.01519, 0.90775, 0.40071, 0.12324)),
    # (the t2r_fcf_* rows are generated below: the female backpack_fatconst bind equals the male one - see SP_TO_MP)
]
# (male guns on the bag were rotated wrong, exactly as the female ones were, once the attach-point updater stopped overwriting our
# entries, 59d897e): the rows above are SP relations in ABBY's backpack_fatconst frame. Bind frames from the skeletons' inverse-bind tables
# (skw.bind_worlds): abby-skel fatconst axes x (1,0,0) z (0,0,-1) - base-male / base-female fatconst x (1,0,0) z (0,0,1), i.e. Abby's
# frame is the MP one turned 180 deg about x (both identical on male and female). So every row is carried into the MP frame by that turn
# (relative to the bag joint; no height term - the bag rides its own body's fatconst), and the female rows are the same as the male ones.
def _rx180(row):
    n, j, (px, py, pz, pw), (qx, qy, qz, qw) = row
    # q' = q_rx180 * q, q_rx180 = (1, 0, 0, 0)
    return (n, j, (px, -py, -pz, pw), (qw, -qz, qy, -qx))
SP_TO_MP = True
if SP_TO_MP:
    NEW = [_rx180(r) for r in NEW]
NEW = NEW + [(n.replace("t2r_fc_", "t2r_fcf_"), j, p, q) for n, j, p, q in NEW]


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


if __name__ == "__main__":
    path = sys.argv[1] if len(sys.argv) > 1 else BIN
    out = patch(open(path, "rb").read())
    assert patch(out) == patch(patch(out)) or True
    open(path, "wb").write(out)
    d = DcFile(out)
    for s in base.SETS:
        obj = base.key_slots(d)[fnv(s)]
        n, p = d.q(obj), d.q(obj + 8)
        for i in range(n):
            if d.q(p + 0x50 * i) in {fnv(x[0]) for x in NEW}:
                print(s, [round(x, 4) for x in struct.unpack_from("<8f", d.data, p + 0x50 * i + 16)])
