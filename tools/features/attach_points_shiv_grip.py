"""attach-points.bin: per-clip shiv / knife grips on r_hand_prop (the shiv pointed wrong in some animations, most notably the
front one that is a single stab: the shiv pointed upwards).

The ext attached the shiv (and the female ground-execution knife) to 'rightHand' = r_hand_prop with the identity offset for every clip. Every
shiv / knife model (actor97 shiv-a, knife-survival-mel, dagger-scar-lev) has its blade along model +Z (shiv-a: handle z -0.08..0.05, blade z 0.05..0.246,
flat in X, tip at +Z), so the blade points along r_hand_prop +Z. The baked 2013 shiv clips (re/factions2013/t1anim/baked/t1mx-*) drive r_hand_prop
with a different frame per clip, so identity pointed the blade at the victim in some clips only.

Derivation (re/factions2013/t1anim, both baked halves in the pair's ap space, the decoder of measure_contacts.py): per frame the direction from the
attacker's r_hand_prop to the nearest victim torso / head joint (headb neck spined spinea pelvis l/r_shoulder), in r_hand_prop axes, over the frames the
hand is within 0.30 m of it (the stabs); robust mean (outliers > 50 deg dropped). Angle between that direction and the identity blade (+Z), mean over
those frames, and after the grip below (blade +Z -> mean direction by the shortest arc, then rolled about it so the blade's wide axis, model Y, is as
horizontal in the world as it gets = flat blade between the ribs):
  clip                          mean dir in r_hand_prop            identity   after
  fist-insta-shiv-stand-front   (-0.14 -0.16 +0.98)                 20 deg    (keeps identity)
  fist-insta-shiv-stand-back    (-0.47 -0.67 +0.58)                 59 deg    29 deg   t2r_shiv_ib
  shiv-stealth-back             (-0.15 +0.32 +0.94)                 27 deg    15 deg   t2r_shiv_sb
  shiv-stealth-front            (-0.52 +0.84 +0.12)                 83 deg     3 deg   t2r_shiv_sf  (identity: blade world-up +0.73 = pointing up)
  shiv-ground-execution-left    (-0.10 +0.10 +0.99)                 40 deg    (keeps identity)
  shiv-ground-execution-right   (-0.96 +0.02 -0.28)                 92 deg    40 deg   t2r_shiv_gr  (identity: blade world-up +0.70)
The point: pos = 0 (the model origin stays on the hand-prop origin, as with 'rightHand'), quat (x y z w) = the rotation that takes model axes to
r_hand_prop axes (the convention of t2r_arrow_hand: model +Z -> prop +Y is (-S 0 0 S)). Added to the player / joel / npc-common sets. Idempotent.

  python attach_points_shiv_grip.py [attach-points.bin]"""
import os
import struct
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from dcfile import DcFile, fnv  # noqa: E402
import attach_points_base_male as base  # noqa: E402

BIN = os.path.join(HERE, "data", "attach-points.bin")
JOINT = "r_hand_prop"
# a female body's attach set is not always player / joel / npc-common (female knife lives run IsEllie / IsAbby forced, the engine then reads the
# ellie / abby sets) - the point was missing there and the female ground-shiv knife attached to nothing. Every set a player body can use gets it.
SETS = base.SETS + ("ellie", "ellie-santabarbara", "marlene-player", "ellie-16-ultimatum", "abby", "lev")
# (point, mean victim direction in r_hand_prop axes (the blade's wanted direction), quat x y z w measured as described above)
NEW = [
    ("t2r_shiv_ib", (-0.469, -0.667, 0.579), (0.11786, -0.44339, 0.57115, 0.68066)),
    ("t2r_shiv_sb", (-0.146, 0.316, 0.937), (-0.06839, -0.16320, -0.66493, 0.72564)),
    # t2r_shiv_sf re-fitted (round 2: + a blade-reach term, the blade segment must reach the victim's neck at the contact frames: 8.2 -> 6.7 cm miss) so the handle runs THROUGH the fist (blade within 25 deg of the knuckle line,
    # towards the victim, roll + origin from re/factions2013/t1anim/shiv_grip_fit.py: fingers 0-2 cm off the handle, was 3.5 / pinky hovering; blade 0 deg off the victim): the
    # 4th field = the model origin in r_hand_prop axes. The other five clips bake the fitted pose as their r_hand_prop row instead (shiv_prop_rows.py) and attach to rightHand;
    # their t2r_shiv_* points below are no longer used by the ext (shiv_grip_point), only this one is.
    ("t2r_shiv_sf", None, (0.04102, 0.75453, 0.62428, -0.19820), (-0.0004, 0.0532, 0.0219)),
    ("t2r_shiv_gr", (-0.959, 0.023, -0.284), (0.18847, -0.77879, -0.15485, 0.57792)),
    # (the shiv was held upright / sideways, not into the neck, on the stunned front shiv): fit to the NECK (the stab lands there) over the stab
    # frames 4..11 of the 10 fps baked fist-insta-shiv-stand-front (0.4 - 1.1 s; 2013 stabs at 300 / 530 / 820 / 1100 ms): mean neck direction in
    # r_hand_prop axes (-0.23 0.85 0.473), shortest arc from +Z, no roll. Identity: blade 62 deg off the neck (max 79); with this point 17 deg (max 27).
    # (The first fit above used the TORSO joints = 20 deg for identity; the neck is what the blade has to reach.)
    ("t2r_shiv_if", (-0.230, 0.850, 0.473), (-0.49541, -0.13405, 0.0, 0.85826)),
]


def qrot(q, v):
    x, y, z, w = q
    u = np.array([x, y, z])
    v = np.asarray(v, float)
    return v + 2 * np.cross(u, np.cross(u, v) + w * v)


def check():
    for name, m, q, *_ in NEW:
        n = np.linalg.norm(q)
        assert abs(n - 1) < 1e-3, (name, n)
        if m is None:
            continue
        m = np.asarray(m) / np.linalg.norm(m)
        t = qrot(q, (0, 0, 1))
        assert np.dot(t, m) > 0.995, (name, t, m)       # the blade (+Z) lands on the wanted direction


def patch(data: bytes):
    check()
    d = DcFile(data)
    drop = {fnv(n[0]) for n in NEW}
    for s in SETS:
        obj = base.key_slots(d)[fnv(s)]
        assert d.q(obj + 16) == base.TAG and d.is_ptr(obj + 8), s
        n, p = d.q(obj), d.q(obj + 8)
        keep = b"".join(bytes(d.data[p + 0x50 * i:p + 0x50 * (i + 1)]) for i in range(n) if d.q(p + 0x50 * i) not in drop)
        blob = keep + b"".join(base.rec(r[0], JOINT, tuple(r[3] if len(r) > 3 else (0.0, 0.0, 0.0)) + (1.0,), r[2]) for r in NEW)
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
