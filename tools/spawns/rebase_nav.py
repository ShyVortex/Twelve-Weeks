"""Move a map's placed spawners onto the mod's original level pak, in place.

The SceneEditor writer (add_spawners.ps1) keeps only spawners: rebuilding Shipyard dropped the
navmesh the client ships in it (to1-pvp-shipyard-ingame.pak: NAV_MESH_1 + nav-* tiles + height maps,
1.4 MB -> 59 KB), and the climbing ("verticality") block came back. This starts again from the
mod's pak (re/modfs/pak68) and writes our transforms into its spawner records (same names),
nothing rebuilt. Spawners only ours has (added with add_spawners) are reported and left out.
  python rebase_nav.py <map>
"""
import os
import shutil
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import levels  # noqa: E402

ROOT = os.path.join(levels.HERE, "..", "..")


def main(m):
    ours_pak = levels.pak_path(m)
    orig = os.path.join(ROOT, "re", "modfs", "pak68", f"to1-pvp-{m}-ingame.pak")
    ours = {s["name"]: s for s in levels.spawners(m)}
    bak = ours_pak + ".pre-nav.bak"
    if not os.path.exists(bak):
        shutil.copy(ours_pak, bak)
    shutil.copy(orig, ours_pak)                   # the mod's pak, navmesh included
    sp = levels.spawners(m)
    b = bytearray(open(ours_pak, "rb").read())
    offs = levels.find_offsets(b, sp)
    n = 0
    for s in sp:
        o = ours.get(s["name"])
        if not o or s["name"] not in offs:
            continue
        struct.pack_into("<3f", b, offs[s["name"]], *o["pos"])
        struct.pack_into("<4f", b, offs[s["name"]] + 16, *o["quat"])
        n += 1
    open(ours_pak, "wb").write(b)
    lost = sorted(set(ours) - {s["name"] for s in sp})
    print(f"{m}: {n} spawners placed on the original pak ({os.path.getsize(ours_pak)} bytes); "
          f"not in it (dropped): {lost}")


if __name__ == "__main__":
    main(sys.argv[1])
