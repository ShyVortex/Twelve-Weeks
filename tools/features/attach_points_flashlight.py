"""attach-points.bin: the strap flashlight point 'flashlightAttach' for the sets the MP puppets use (the enemy flashlight appeared to be
between the character's feet).

Cause: the FlashlightContainer spawn (ext flashlight.c fls_container_spawn, kind 4, look flashlight-l-military) attaches model + light to the owner's attach point
flashlightAttach. Only the 'player' set has that record (parented to r_clavicle, pos (0.114, 0.085, -0.11), quat (0.6959, -0.1255, 0.6959, 0.1255), re/flashlight-1102.md);
a puppet is an NPC body on the 'joel' / 'npc-common' sets (re/attach-base-male.md), which lack it, so the unresolved point leaves the strap model and light at the
body origin = the feet. base-male-skel has r_clavicle. Same record added to those two sets. Idempotent.

  python attach_points_flashlight.py [attach-points.bin]"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from dcfile import DcFile, fnv  # noqa: E402
import attach_points_base_male as base  # noqa: E402

BIN = os.path.join(HERE, "data", "attach-points.bin")
SETS = ("joel", "npc-common")
POINT, JOINT = "flashlightAttach", "r_clavicle"
POS = (0.114, 0.085, -0.11, 1.0)
QUAT = (0.6958813667297363, -0.12549790740013123, 0.6958804726600647, 0.12549807131290436)


def patch(data: bytes):
    d = DcFile(data)
    for s in SETS:
        obj = base.key_slots(d)[fnv(s)]
        assert d.q(obj + 16) == base.TAG and d.is_ptr(obj + 8), s
        n, p = d.q(obj), d.q(obj + 8)
        keep = b"".join(bytes(d.data[p + 0x50 * i:p + 0x50 * (i + 1)]) for i in range(n) if d.q(p + 0x50 * i) != fnv(POINT))
        blob = keep + base.rec(POINT, JOINT, POS, QUAT)
        at = d.append(blob)
        d.set_q(obj, len(blob) // 0x50)
        d.set_ptr(obj + 8, at)
    return d.save()


def count(data: bytes):
    d = DcFile(data)
    out = {}
    for s in SETS:
        obj = base.key_slots(d)[fnv(s)]
        n, p = d.q(obj), d.q(obj + 8)
        out[s] = sum(1 for i in range(n) if d.q(p + 0x50 * i) == fnv(POINT))
    return out


if __name__ == "__main__":
    path = sys.argv[1] if len(sys.argv) > 1 else BIN
    out = patch(open(path, "rb").read())
    assert count(out) == {s: 1 for s in SETS} and count(patch(out)) == count(out)
    open(path, "wb").write(out)
    print(count(out))
