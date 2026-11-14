"""weapon-straps.bin: rifle sling offsets for the MP looks (re/weapon-straps.md).

The sling of a long gun is its own process (ProcessWeaponStrap, spawned by the weapon's init 0x141188820 from the weapon art's
+0x50 / +0x58 strap look). While the gun is stowed the strap's middle joints copy the CHARACTER's strap chain - slot one:
rifle_strap_straight_01..15, slot two: rifle_strap_def_01..15 (name table exe 0x143600360, 0x78 per slot) - plus a per-look
offset per joint from *weapon-strap-offsets-looks* (this file; strap process +0x12c8, looked up by the character's look name
= vfunc +0x390). Each joint offset is {pos.xyz, pad, quat.xyzw} in the strap joint's own frame: the game's entries push the
sling OUT of the body along the joint's local +z (militia -backpack looks up to 6.5 cm over the bag), joint 0 and the last
one or two stay 0 (the ends sit on the gun). A look with no entry gets no push: the sling lies on the bare body, i.e. inside
the backpack / armour.

weapon-strap-offsets = {A: slot one, B: slot two} (pointers, B may be null); weapon-strap-joint-offsets = {array, u32 n, u32 k}
where k > 0 overrides the strap collision preset (exe 0x14117b1a0: 5 jerry, 6 abby / ellie, 7 every other skeleton).

Every MP pool look (male + female, and the '-t2r-arm' armoured twins) gets an entry copied from the closest SP look of the
same faction / bag (STRAP_SRC), the twins pushed TWIN_PUSH further out (plate carrier), and a B set for slot two: base-male-skel /
base-female-skel only have the straight chain (the ext points slot two at it), whose ends sit on the SLOT-ONE gun's swivels. B = SLOT2_DELTA (+) A
(+ B_PUSH along +z on the inner joints): SLOT2_DELTA carries the chain's ends onto the slot-two gun (the Double Barrel stacked behind the Vepr,
attach_points_sp_bag t2r_fc_g2) and tapers to half of that at the shoulder, per chain joint in its own frame (tools/models/backpack_slot2.py,
from the SP sandbox's stowed strap captures). Before (an earlier build: B = A + 1.2 cm) the DB's sling ran from the DB to the Vepr's swivels:
too short, through the bag, twisted near the ends.

  python weapon_straps.py dump <weapon-straps.bin> [look-substring]
  python weapon_straps.py make <game weapon-straps.bin> <out dir>
"""
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from dcfile import DcFile, fnv  # noqa: E402

SYMBOL = "*weapon-strap-offsets-looks*"
# MP look -> SP look whose offsets it takes (same faction, a backpack look of the same build)
STRAP_SRC = {
    "militia-male-11-backpack": "militia-male-08-backpack",
    "militia-male-08-backpack": "militia-male-08-backpack",
    "militia-male-12-backpack": "militia-male-08-backpack",
    "militia-male-05-backpack": "militia-male-05-backpack",
    "militia-male-13-backpack": "militia-male-05-backpack",
    "militia-male-14-backpack": "militia-male-05-backpack",
    "scar-male-13": "scar-male-13", "scar-male-01": "scar-male-13", "scar-male-12": "scar-male-13",
    "scar-male-06": "scar-male-13", "scar-male-09": "scar-male-13", "scar-male-02": "scar-male-13",
    "militia-female-13-backpack": "militia-female-04-backpack",
    "militia-female-12-backpack": "militia-female-04-backpack",
    "scar-female-11": "scar-female-10", "scar-female-09": "scar-female-10",
}
TWIN_SUFFIX = "-t2r-arm"          # = dc_data_patches.ARMOUR_LOOK_SUFFIX
TWIN_PUSH = 0.015                 # m along the joint's +z: the Rattler plate carrier under the sling
B_PUSH = 0.012                    # m along +z: slot two's sling on top of slot one's where they share the shoulder (inner joints)
# per chain joint (= offset entry 0..14 = rifle_strap_straight_01..15): dx dy dz (m, joint frame), quat xyzw - python tools/models/backpack_slot2.py re/sp-sandbox-runs/2026-10-12-round2-abby-ellie.log (Vepr + DB at SP's places, section 4)
SLOT2_DELTA = [
    (+0.0254, +0.0327, +0.0357, +0.0322, +0.0414, +0.0380, +0.9979),   # 0  (on the gun: the barrel swivel)
    (+0.0226, +0.0280, +0.0326, +0.0270, +0.0370, +0.0349, +0.9983),
    (+0.0169, +0.0255, +0.0300, +0.0186, +0.0347, +0.0319, +0.9987),
    (+0.0107, +0.0216, +0.0291, +0.0109, +0.0307, +0.0304, +0.9990),
    (+0.0042, +0.0190, +0.0273, +0.0033, +0.0279, +0.0275, +0.9992),
    (+0.0001, +0.0195, +0.0234, -0.0017, +0.0280, +0.0215, +0.9994),
    (-0.0051, +0.0214, +0.0182, -0.0075, +0.0289, +0.0136, +0.9995),
    (-0.0139, +0.0239, +0.0038, -0.0146, +0.0276, -0.0051, +0.9995),   # 7  (the shoulder)
    (-0.0172, +0.0220, +0.0000, -0.0163, +0.0211, -0.0183, +0.9995),
    (-0.0217, +0.0189, +0.0000, -0.0215, +0.0131, -0.0232, +0.9994),
    (-0.0316, +0.0015, +0.0000, -0.0291, -0.0127, -0.0211, +0.9993),
    (-0.0344, -0.0095, +0.0000, -0.0287, -0.0274, -0.0177, +0.9991),
    (+0.0081, -0.0155, +0.0000, +0.0025, -0.0364, -0.0345, +0.9987),
    (+0.0213, -0.0190, +0.0000, +0.0093, -0.0430, -0.0365, +0.9984),
    (+0.0339, -0.0152, -0.0517, +0.0210, -0.0457, -0.0404, +0.9979),   # 14 (on the gun: the stock swivel)
]
JOINT_ENTRY = 32                  # vec4 pos + quat


def _map(f):
    D = f.data
    n, eo = struct.unpack_from("<I", D, 0x14)[0], f.q(0x18)
    for i in range(n):
        if f.q(eo + 24 * i) == fnv(SYMBOL):
            return f.q(eo + 24 * i + 16)
    raise KeyError(SYMBOL)


def entries(f):
    """{look sid: (A list of 8-float tuples, kA, B list or None, kB)}"""
    m = _map(f)
    n, kp, vp = f.q(m) & 0xffffffff, f.q(m + 8), f.q(m + 16)
    out = {}
    for i in range(n):
        v = f.q(vp + 8 * i)
        sets = []
        for s in (f.q(v), f.q(v + 8)):
            if not s:
                sets += [None, 0]
                continue
            arr, cnt, k = f.q(s), struct.unpack_from("<I", f.data, s + 8)[0], struct.unpack_from("<I", f.data, s + 12)[0]
            sets += [[struct.unpack_from("<8f", f.data, arr + JOINT_ENTRY * j) for j in range(cnt)], k]
        out[f.q(kp + 8 * i)] = tuple(sets)
    return out


def pushed(rows, dz):
    """rows with +dz on every joint the source pushes (the ends - zero offset in the game's data - stay on the gun)"""
    out = []
    for r in rows:
        moved = any(abs(x) > 1e-6 for x in r[:3]) or abs(r[7] - 1) > 1e-6
        out.append((r[0], r[1], r[2] + (dz if moved else 0.0)) + tuple(r[3:]))
    return out


def _qmul(a, b):
    ax, ay, az, aw = a
    bx, by, bz, bw = b
    return (aw * bx + ax * bw + ay * bz - az * by, aw * by - ax * bz + ay * bw + az * bx,
            aw * bz + ax * by - ay * bx + az * bw, aw * bw - ax * bx - ay * by - az * bz)


def _qrot(q, v):
    x, y, z, w = q
    t = (2 * (y * v[2] - z * v[1]), 2 * (z * v[0] - x * v[2]), 2 * (x * v[1] - y * v[0]))
    return (v[0] + w * t[0] + y * t[2] - z * t[1], v[1] + w * t[1] + z * t[0] - x * t[2], v[2] + w * t[2] + x * t[1] - y * t[0])


def slot_two(rows_a):
    """B rows: SLOT2_DELTA composed with the look's A rows (the engine: pos += R(joint) * off.xyz, rot = rot * off.quat)"""
    out = []
    for i, (r, d) in enumerate(zip(rows_a, SLOT2_DELTA)):
        p = _qrot(d[3:], r[:3])
        q = _qmul(d[3:], r[4:8])
        z = B_PUSH if 0 < i < len(rows_a) - 1 else 0.0
        out.append((d[0] + p[0], d[1] + p[1], d[2] + p[2] + z, 1.0) + tuple(q))
    return out


def targets():
    """{look name: (A rows-source look, extra push A)}"""
    t = {}
    for look, src in STRAP_SRC.items():
        t[look] = (src, 0.0)
        t[look + TWIN_SUFFIX] = (src, TWIN_PUSH)
    import dc_data_patches as dcp
    if dcp.WINTER_ON:            # the winter looks (+ their armoured twins) sling like the pool look they copy (they had no entry)
        for w, (base, _p, _m) in dcp.WINTER_LOOKS.items():
            t[w] = (STRAP_SRC[base], 0.0)
            t[w + TWIN_SUFFIX] = (STRAP_SRC[base], TWIN_PUSH)
    return t


def make(game_bin, out_dir):
    f = DcFile(open(game_bin, "rb").read())
    have = entries(f)
    m = _map(f)
    n, kp, vp = f.q(m) & 0xffffffff, f.q(m + 8), f.q(m + 16)
    keys = [f.q(kp + 8 * i) for i in range(n)]
    vals = [f.q(vp + 8 * i) for i in range(n)]
    new = {}
    for look, (src, dz) in targets().items():
        a, ka = have[fnv(src)][0], have[fnv(src)][1]
        rows_a = pushed(a, dz) if dz else list(a)
        rows_b = slot_two(rows_a)
        ptrs = []
        for rows, k in ((rows_a, ka), (rows_b, ka)):
            arr = f.append(b"".join(struct.pack("<8f", *r) for r in rows), tag="array")
            jo = f.append(struct.pack("<QII", arr, len(rows), k), ptr_slots=(0,), tag="weapon-strap-joint-offsets")
            ptrs.append(jo)
        # (append shifts nothing below the string region: the earlier blocks keep their offsets)
        new[fnv(look)] = f.append(struct.pack("<QQ", *ptrs), ptr_slots=(0, 8), tag="weapon-strap-offsets")
    table = dict(zip(keys, vals))
    replaced = sum(1 for k in new if k in table)
    table.update(new)
    order = sorted(table)                                   # the engine binary-searches the keys (0x141176a30)
    ka = f.append(b"".join(struct.pack("<Q", k) for k in order), tag="array")
    va = f.append(b"".join(struct.pack("<Q", table[k]) for k in order), ptr_slots=tuple(8 * i for i in range(len(order))), tag="array")
    m = _map(f)
    struct.pack_into("<I", f.data, m, len(order))
    f.set_ptr(m + 8, ka)
    f.set_ptr(m + 16, va)
    os.makedirs(out_dir, exist_ok=True)
    p = os.path.join(out_dir, "weapon-straps.bin")
    open(p, "wb").write(f.save())
    print(f"weapon-straps: {len(new)} MP look entries (A + B slings; {replaced} replaced game entries), {len(order)} looks")
    verify(p)
    return p


def verify(path):
    f = DcFile(open(path, "rb").read())
    e = entries(f)
    m = _map(f)
    n, kp = f.q(m) & 0xffffffff, f.q(m + 8)
    keys = [f.q(kp + 8 * i) for i in range(n)]
    assert keys == sorted(keys) and len(set(keys)) == n, "weapon-straps: keys not sorted / unique"
    for look, (src, dz) in targets().items():
        a, ka, b, kb = e[fnv(look)]
        assert b is not None and len(a) == len(b) == 15, look
        s = e[fnv(src)][0]
        for ra, rs in zip(a, s):
            assert abs(ra[2] - rs[2]) < 1e-6 or abs(ra[2] - rs[2] - dz) < 1e-6, look
        for rb, rw in zip(b, slot_two(a)):
            assert max(abs(x - y) for x, y in zip(rb, rw)) < 1e-5, look
    return True


def dump(path, sub=""):
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
    import sid
    sd, t = sid.load()

    def name(h):
        o = t.get(h)
        return sd[o:sd.index(b"\0", o)].decode() if o is not None else f"{h:#x}"
    names = {fnv(n): n for n in targets()}
    for k, (a, ka, b, kb) in sorted(entries(DcFile(open(path, "rb").read())).items(), key=lambda kv: names.get(kv[0]) or name(kv[0])):
        nm = names.get(k) or name(k)
        if sub not in nm:
            continue
        def s(rows, kk):
            if rows is None:
                return "-"
            return f"k{kk} " + " ".join(f"{r[2] * 100:.1f}" for r in rows)
        print(f"{nm:40s} A z cm: {s(a, ka)}\n{'':40s} B z cm: {s(b, kb)}")


if __name__ == "__main__":
    if sys.argv[1] == "dump":
        dump(sys.argv[2], sys.argv[3] if len(sys.argv) > 3 else "")
    elif sys.argv[1] == "make":
        make(sys.argv[2], sys.argv[3])
