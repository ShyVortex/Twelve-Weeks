"""attach-points.bin: Ellie's switchblade put-away point 'switch_blade' for the MP bodies (militia-female-13: the knife stuck to
the hand despite a secondary being out).

The female looks melee with Ellie's switchblade (t2r-ext female knife mode). When a gun is drawn the engine puts the knife away through the
weapon's holster point 'switch_blade' (SP sandbox round 3: ProcessWeaponBase::PutInHolster -> switch_blade, table entry 13, joint
index 0xa0 = r_switchblade of ellie-skel, identity locator, weapon offset (0.002, -0.023, -0.025) q (0.8157, -0.4989, 0.2727, 0.1065); the
holster move is ellie-switchblade-holster-pocket: her right BACK pocket). 'switch_blade' only exists in the Ellie sets (ellie,
ellie-santabarbara, marlene-player, ellie-16-ultimatum); the sets an MP body gets (player / joel / npc-common) have none, and base-male /
base-female-skel have no r_switchblade / knife_holster_jnt joint either, so the attach point was not found, the holster attach was skipped
and the knife stayed in the right hand next to the drawn gun.

The point: r_switchblade's bind frame relative to its parent pelvis_helper on ellie-skel (skw.bind_worlds: pure translation, same axes as
pelvis_helper: (-0.098, 0.0923, -0.0801) in pelvis_helper space = model (-0.098, 0.865, -0.083), 8 cm below and 9 cm behind the pelvis, right
back pocket), scaled by the body size (MP pelvis height 1.0303 / Ellie's 0.9455 = 1.090, the same as the hip-width ratio 0.0971 / 0.0891),
on pelvis_helper of base-female / base-male (same name, same bind orientation; both MP skeletons share the pelvis bind). The weapon's own
switch_blade offset is the SP one, so the knife lands where Ellie's sits, at the MP body's size: model (-0.107, 0.943, -0.090), 1.5-3.5 cm
inside the back of the female trousers (militia-female-d / a legs z -0.105..-0.126, scar-female legs -0.105..-0.110 under the coat cloth
-0.12) = in the pocket. Draw back to the hand on melee: the engine's own switchblade unholster from this point (IsEllie on at the press).
Added to the player / joel / npc-common sets. Idempotent.

  python attach_points_knife_holster.py [attach-points.bin]"""
import os
import struct
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from dcfile import DcFile, fnv  # noqa: E402
import attach_points_base_male as base  # noqa: E402

BIN = os.path.join(HERE, "data", "attach-points.bin")
JOINT = "pelvis_helper"
# solve (see the docstring): python attach_points_knife_holster.py --solve
ELLIE_REL = (-0.0980, 0.0923, -0.0801)          # r_switchblade in pelvis_helper space, ellie-skel bind
SCALE = 1.0303 / 0.9455                          # MP pelvis_helper height / Ellie's
POS = tuple(round(c * SCALE, 5) for c in ELLIE_REL) + (1.0,)
QUAT = (0.0, 0.0, 0.0, 1.0)
NEW = [("switch_blade", JOINT, POS, QUAT)]


def solve():
    import skw
    R = "./re/uc4ps4/t2/"
    E = skw.bind_worlds(R + "ellie-skel.pak")
    rel = np.linalg.inv(E["pelvis_helper"]) @ E["r_switchblade"]
    print("ellie r_switchblade in pelvis_helper:", np.round(rel[:3, 3], 4), "rot identity:", np.allclose(rel[:3, :3], np.eye(3), atol=1e-3))
    for sk in ("base-female-skel", "base-male-skel"):
        B = skw.bind_worlds(R + sk + ".pak")
        print(sk, "pelvis_helper", np.round(B["pelvis_helper"][:3, 3], 4), "-> knife point model",
              np.round((B["pelvis_helper"] @ np.append(np.array(POS[:3]), 1.0))[:3], 4))


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
                assert d.q(p + 0x50 * i + 8) == fnv(JOINT)
                out.append((s, want[d.q(p + 0x50 * i)], [round(x, 5) for x in struct.unpack_from("<8f", d.data, p + 0x50 * i + 16)]))
    return out


if __name__ == "__main__":
    if sys.argv[1:] == ["--solve"]:
        solve()
        sys.exit(0)
    path = sys.argv[1] if len(sys.argv) > 1 else BIN
    out = patch(open(path, "rb").read())
    assert readback(patch(out)) == readback(out) and len(readback(out)) == len(base.SETS) * len(NEW)
    open(path, "wb").write(out)
    for r in readback(out):
        print(*r)
