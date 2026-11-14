"""Invisible collision walls for PvP maps: the stock game's invisible-collision actors placed as props in our spawner
pak (SimpleObject + AutoSpawn, the same mechanism the props / dumpster blockers use). Background and evidence:
re/maps/collision-editing.md.

  python collision_walls.py measure                       # collision box of each invisible actor, read from the
                                                         # game's actor97 paks (read only; cached in re/maps/paks/_base)
  python collision_walls.py line <key> <x1> <z1> <x2> <z2> --y <floor y> [--height 3] [--art block|panel] [--no-pak]
                                                         # a wall from (x1,z1) to (x2,z2) standing on y; height in
                                                         # 3 m layers; props tagged "wall": true in sp_maps.json
  python collision_walls.py test <key> [--dist 6] [--width 6] [--scale] [--no-pak]
                                                         # experiment: a wall across team 0 intro 1's facing, dist m
                                                         # ahead; --scale adds one block with Scale (1,1,3) 4 m past it
                                                         # (6 m long if the engine scales its collision, 2 m if not)
  python collision_walls.py clear <key> [--no-pak]        # drop the wall props of a map

After line / test / clear the map's spawner pak is rebuilt (sp_maps.pak) unless --no-pak; the build adds the
"actor <art>" line to the map's pak68 block (sp_maps_build.prop_actors), which is what loads the actor.
"""
import json
import math
import os
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import sp_maps  # noqa: E402

# Box of each actor in its own space (min, max), measured from the hknp convex hull + body position in its
# COLLISION_DATA_FOREGROUND item (measure()). All in sp-common.psarc, which every map mounts.
ACTORS = {
    # 0.5 thick (X) x 3 tall (Y, from the floor) x 2 long (Z); origin = bottom corner. ND's own arena closer:
    # fob-on-foot-store-script obj-fob-store-enter-blocker-1/2, t2r-fob-on-foot-store-interior-kitchen-exit obj-17592.
    "block": ("invisible-block-050x300x200", (0.0, 0.0, 0.0), (0.5, 3.0, 2.0)),
    # 3 wide (X) x 3 tall (Y) x 0.1 thick (Z), centred on its origin. SP's wall panel (san-streets-train-station
    # ic-538..541: four in a row = a 12 m invisible wall at the Train Station).
    "panel": ("invis-collision", (-1.5, -1.5, -0.05), (1.5, 1.5, 0.05)),
}
LONG = {"block": 2.0, "panel": 3.0}       # length of one piece along the wall
TALL = 3.0


def measure(name):
    """(min, max) of the actor's collision box: hull vertices (DATA+0x280, 8 x vec4) + body position (DATA+0x190)
    of the Havok 2017.1 tagfile (hknpPhysicsSystemData) inside COLLISION_DATA_FOREGROUND."""
    import prop_bounds
    d = open(prop_bounds.actor_pak(name), "rb").read()
    t0 = d.index(b"TAG0") - 4
    data = t0 + 0x10 + 0x10                       # TAG0 header (8) + SDKV (16) -> DATA header (8)
    assert d[data - 4:data] == b"DATA", name
    pos = struct.unpack_from("<3f", d, data + 0x190)
    vs = [struct.unpack_from("<3f", d, data + 0x280 + 16 * i) for i in range(8)]
    radius = struct.unpack_from("<f", d, data + 0x238)[0]   # convex radius, added around the hull
    lo = [round(min(v[i] for v in vs) + pos[i] - radius, 3) for i in range(3)]
    hi = [round(max(v[i] for v in vs) + pos[i] + radius, 3) for i in range(3)]
    return lo, hi


def _quat(yaw):
    return [0.0, round(math.sin(yaw / 2), 6), 0.0, round(math.cos(yaw / 2), 6)]


def _rot(yaw, v):
    """rotate (x, z) of v about +Y by yaw (right-handed, like the spawner quaternions)"""
    c, s = math.cos(yaw), math.sin(yaw)
    return (v[0] * c + v[2] * s, v[1], -v[0] * s + v[2] * c)


def piece(kind, cx, y, cz, dx, dz):
    """one piece whose footprint is CENTRED on (cx, cz), long side along (dx, dz), bottom on y"""
    art, lo, hi = ACTORS[kind]
    if kind == "block":
        yaw = math.atan2(dx, dz)                  # local +Z (the 2 m side) along the wall
    else:
        yaw = math.atan2(-dz, dx)                 # local +X (the 3 m side) along the wall
    centre = [(lo[i] + hi[i]) / 2 for i in range(3)]
    off = _rot(yaw, (centre[0], 0.0, centre[2]))
    return {"art": art, "pos": [round(cx - off[0], 3), round(y - lo[1], 3), round(cz - off[2], 3)],
            "quat": _quat(yaw), "wall": True}


def wall(x1, z1, x2, z2, y, height=TALL, kind="block"):
    """pieces covering the segment end to end (evenly spread, slight overlap), layered up to height"""
    ln = math.hypot(x2 - x1, z2 - z1)
    assert ln > 0.05, "wall too short"
    dx, dz = (x2 - x1) / ln, (z2 - z1) / ln
    n = max(1, math.ceil(ln / LONG[kind] - 1e-6))
    out = []
    for layer in range(max(1, math.ceil(height / TALL - 1e-6))):
        for i in range(n):
            s = LONG[kind] / 2 if n == 1 else LONG[kind] / 2 + i * (ln - LONG[kind]) / (n - 1)
            if ln < LONG[kind]:
                s = ln / 2
            out.append(piece(kind, x1 + dx * s, y + layer * TALL, z1 + dz * s, dx, dz))
    return out


def _add(key, props, pak=True):
    m = sp_maps.spec(key)
    sp_maps.save_spec_props(key, list(m.get("props", [])) + props)
    print(f"{key}: +{len(props)} wall pieces ({len(m.get('props', [])) + len(props)} props in all)")
    for p in props:
        print(f"  {p['art']:30s} pos {p['pos']} quat {p['quat']}" + (f" scale {p['scale']}" if "scale" in p else ""))
    if pak:
        sp_maps.pak(key)


def test(key, dist=6.0, width=6.0, scale=False, pak=True):
    s = json.load(open(os.path.join(sp_maps.DATA, f"{key}-spawns.json")))
    t = s["intro0"][0]
    x, y, z = t["pos"]
    qy, qw = t["quat"][1], t["quat"][3]
    yaw = 2 * math.atan2(qy, qw)
    fx, fz = math.sin(yaw), math.cos(yaw)        # facing = local +Z
    rx, rz = fz, -fx                             # across the facing
    cx, cz = x + fx * dist, z + fz * dist
    props = wall(cx - rx * width / 2, cz - rz * width / 2, cx + rx * width / 2, cz + rz * width / 2, y)
    print(f"{key}: test wall {width} m wide, {dist} m ahead of to1-t0-intro-spawn-point-1 at {t['pos']} "
          f"(facing {math.degrees(yaw):.0f} deg)")
    if scale:
        sx, sz = x + fx * (dist + 4), z + fz * (dist + 4)
        p = piece("block", sx, y, sz, rx, rz)
        p["pos"][0] = round(p["pos"][0] - rx * 2.0, 3)     # origin end: centred again once 3x as long
        p["pos"][2] = round(p["pos"][2] - rz * 2.0, 3)
        p["scale"] = [1.0, 1.0, 3.0]
        p["scale_test"] = True
        props.append(p)
        print(f"  scale test: block centred {dist + 4} m ahead, Scale (1,1,3): 6 m wide if collision scales, 2 m if not")
    _add(key, props, pak)


def clear(key, pak=True):
    m = sp_maps.spec(key)
    keep = [p for p in m.get("props", []) if not p.get("wall")]
    print(f"{key}: {len(m.get('props', [])) - len(keep)} wall pieces removed")
    sp_maps.save_spec_props(key, keep)
    if pak:
        sp_maps.pak(key)


def _opt(a, name, default, cast=float):
    return cast(a[a.index(name) + 1]) if name in a else default


def main():
    a = sys.argv[1:]
    if not a:
        print(__doc__)
        return
    pak = "--no-pak" not in a
    if a[0] == "measure":
        for kind, (art, lo, hi) in ACTORS.items():
            m = measure(art)
            print(f"{kind:6s} {art:30s} measured {m}  table {(list(lo), list(hi))}")
        for art in ("invisible-block-050x150x100", "invisible-cube", "t2r-invis-collision"):
            print(f"       {art:30s} measured {measure(art)}")
    elif a[0] == "line":
        key, x1, z1, x2, z2 = a[1], *map(float, a[2:6])
        _add(key, wall(x1, z1, x2, z2, _opt(a, "--y", None), _opt(a, "--height", TALL),
                       _opt(a, "--art", "block", str)), pak)
    elif a[0] == "test":
        test(a[1], _opt(a, "--dist", 6.0), _opt(a, "--width", 6.0), "--scale" in a, pak)
    elif a[0] == "clear":
        clear(a[1], pak)
    else:
        print(__doc__)


if __name__ == "__main__":
    main()
