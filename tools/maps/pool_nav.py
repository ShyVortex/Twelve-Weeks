"""Navmeshes of the pool maps (offline checker input): python pool_nav.py [<key>...]

Reads the level list of every pool map from the mod's level-sets-test.bin (the hospital from the stock mission set, the SP-section maps
from sp_maps.json), extracts the levels' -ingame paks READ-ONLY from the game psarcs into re/maps/paks/_pool/ and dumps their navmeshes
with dump_nav.ps1 (headless SceneEditor reader) to re/maps/seeds/pool-<name>-nav.json (pool maps) or <key>-nav.json (SP-section maps).
Env: T2R_GAMEBIN (stock level-set dumps), T2R_MAIN_ROOT (re/modfs_feat), T2_GAME (game dir, default C:/Games/The Last of Us Part II Remastered).
"""
import json
import os
import struct
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.dirname(HERE)
ROOT = os.path.dirname(TOOLS)
MAIN = os.environ.get("T2R_MAIN_ROOT", os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")))
os.environ.setdefault("T2R_GAMEBIN", os.path.join(MAIN, "re", "gamebin"))
sys.path.insert(0, HERE)
sys.path.insert(0, TOOLS)
sys.path.insert(0, os.path.join(TOOLS, "features"))
import layoutlib as L  # noqa: E402
import sp_levels  # noqa: E402

SETS = {"school": "tsk-to1-school-1", "forest": "tsk-to1-forest-1", "gas-station": "tsk-to1-gas-station-1", "shipyard": "tsk-to1-shipyard-1",
        "resort": "tsk-to1-resort-1", "seraphite-camp": "tsk-to1-seraphite-camp-1", "rescue-jesse-houses": "tsk-to1-rescue-jesse-houses-1"}
HOSPITAL_SET = "tsk-pf-mission-nor-hospital-generators-1"
OUT_PAKS = os.path.join(ROOT, "re", "maps", "paks", "_pool")


def bin_levels():
    import sp_maps_build as B
    f = B.DcFile(open(os.path.join(MAIN, "re", "modfs_feat", "bin", "dc1", "level-sets", "level-sets-test.bin"), "rb").read())
    out = {}
    for sid, off in B._entries(f).items():
        try:
            nm = B._cstr(f, f.q(off))
            arr = f.q(off + 0x10)
            lo, cnt = f.q(arr), struct.unpack_from("<I", f.data, arr + 8)[0]
            out[nm] = [B._cstr(f, f.q(f.q(lo + 8 * i))) for i in range(cnt)]
        except Exception:
            pass
    return out


def levels_of(key, binsets):
    if key in SETS:
        return [x for x in binsets[SETS[key]] if not x.startswith("to1-pvp")]
    if key == "hospital":
        return [x for x in binsets[HOSPITAL_SET] if not x.startswith("to1-pvp")]
    m = [x for x in json.load(open(L.SPEC, encoding="utf-8"))["maps"] if x["key"] == key][0]
    return [x for x in m["levels"] if x != m["pak"]]


def packages():
    """level name -> its own package (pak68.txt registry: to1-rescue-jesse-houses-layout-1 -> t2r-res-neighborhood-fight-houses-layout-1)"""
    out, cur = {}, None
    for line in open(os.path.join(MAIN, "re", "modfs_feat", "pak68.txt"), encoding="latin1"):
        line = line.rstrip()
        if line.startswith("level-name "):
            cur = line[11:]
        elif line.startswith("package ") and cur and cur not in out:
            out[cur] = line[8:]
        elif not line:
            cur = None
    return out


def extract(levels):
    import dsar_list
    pk = packages()
    levels = [pk.get(x, x).replace("-ingame", "") for x in levels]
    found = sp_levels.where([x + "-ingame" for x in levels])
    main = os.path.join(os.environ.get("T2_GAME", "C:/Games/The Last of Us Part II Remastered"), "build", "pc", "main")
    os.makedirs(OUT_PAKS, exist_ok=True)
    by_arc = {}
    for lv, hits in found.items():
        if not os.path.exists(os.path.join(OUT_PAKS, lv + ".pak")):
            by_arc.setdefault(hits[0][0], []).append(lv)
    for arc, lvs in sorted(by_arc.items()):
        d, ent, bs, bsz = dsar_list.open_files(os.path.join(main, arc))
        for lv in lvs:
            open(os.path.join(OUT_PAKS, lv + ".pak"), "wb").write(dsar_list.extract(d, ent, bs, bsz, f"pak68/{lv}.pak"))
    return [os.path.join(OUT_PAKS, x + "-ingame.pak") for x in levels if os.path.exists(os.path.join(OUT_PAKS, x + "-ingame.pak"))]


def main(keys):
    binsets = bin_levels()
    for key in keys:
        paks = extract(levels_of(key, binsets))
        out = L.nav_file(key)
        os.makedirs(os.path.dirname(out), exist_ok=True)
        subprocess.run(["pwsh", "-NoProfile", "-File", os.path.join(HERE, "dump_nav.ps1"), "-Paks", ";".join(paks), "-Out", out], check=True)


if __name__ == "__main__":
    main(sys.argv[1:] or list(L.POOL) + ["train-station"])
