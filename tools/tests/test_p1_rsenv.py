"""p1_rsenv (Part I render settings for converted Part I maps, re/part1/geometry-upgrade.md s11):
  * always: a synthetic REGION_TREE (volume + point regions, sid / int / float / string tags) written, read back and
    written again byte-identical; an -ingame pak around it passes the loader / VRAM-table mirrors;
  * stock TLOU2 render-const -ingame paks (main checkout re/maps/level-edit-cache, git-ignored): every tree the writer
    supports re-writes byte-identical at its own page offset (format proof);
  * the converted map's rs level (conv dir of p1_levelset.py convert): the audit (regions = Part I's minus the task gating,
    every symbol a render-settings map of the t1x module, the 9 stock t1x symbols unchanged)."""
import os
import struct
import sys
import tempfile
import sys as _t2s, os as _t2o; _t2s.path.append(_t2o.path.normpath(_t2o.path.join(_t2o.path.dirname(_t2o.path.abspath(__file__)), ".."))); import t2rtmp  # noqa: E402,F401  (temp hygiene: tools/t2rtmp.py)

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(TOOLS, "part1"))
sys.path.insert(0, os.path.join(TOOLS, "models"))
import p1_convert  # noqa: E402
import p1_rsenv as E  # noqa: E402


def face(x, z, rot_y):
    import math
    c, s = math.cos(rot_y), math.sin(rot_y)
    f = bytearray(112)
    rot = [c, 0, -s, 0, 1, 0, s, 0, c]
    for j in range(3):
        struct.pack_into("<3f", f, 16 * j, *rot[3 * j:3 * j + 3])
    struct.pack_into("<4f", f, 48, x, 1.5, z, 1.0)
    struct.pack_into("<3f", f, 64, rot[2], rot[5], rot[8])
    struct.pack_into("<8f", f, 80, 2, 3, -2, 3, -2, -3, 2, -3)
    return bytes(f)


def corner(x, y, z):
    return struct.pack("<4f", x, y, z, 1.0)


regions = [
    {"name": "rr-test-box-1", "shape": 1, "sflags": 0, "prio": 3, "point": None, "unsupported": None,
     "vols": [[face(10, 20, 0.0), face(12, 20, 1.5707964)], [face(30, 5, 0.3)]],
     "tags": [(E.TAG_OBSERVED_BY, "sid", E.fnv("camera")), (E.TAG_RS, "str", "*test-rs-a*"), (0x795DF0A25D463983, "float", 0x3F800000),
              (0xCAC33F87AAD338B7, "int", 1)],
     "corners": [corner(8, 0, 17), corner(14, 0, 17), corner(14, 0, 23)]},
    {"name": "rr-test-point-1", "shape": 2, "sflags": 0, "prio": 0, "vols": [], "unsupported": None,
     "point": struct.pack("<4f4f2I", -5, 2, 40, 1, 0, 0, 0, 1, 0x40400000, 0),
     "tags": [(E.TAG_RS, "str", "*test-rs-bb*")], "corners": [corner(-5, 0, 40)]},
]
grid = E.fit_grid(regions)
pak = E.make_ingame_pak(regions, grid)
(back, g2), = E.read_pak_regions(pak)
assert [r["name"] for r in back] == [r["name"] for r in regions]
for a, b in zip(regions, back):
    for k in ("shape", "sflags", "prio", "vols", "point", "corners"):
        assert a[k] == b[k], (a["name"], k)
    assert sorted(a["tags"]) == sorted(b["tags"]), a["name"]
assert E.build_tree(back, g2, 0) == E.build_tree(regions, grid, 0)
with tempfile.TemporaryDirectory() as td:
    p = os.path.join(td, "t-ingame.pak")
    open(p, "wb").write(pak)
    assert not p1_convert.loader_check(p) and not p1_convert.vram_check(p), "engine fixup / VRAM table mirrors"
print("ok  synthetic REGION_TREE round trip (volumes, point, string tags) + -ingame pak loader checks")

MAIN = os.environ.get("T2R_MAIN_ROOT", os.path.dirname(TOOLS).split(os.sep + ".claude" + os.sep)[0])
src = os.path.join(MAIN, "re", "maps", "level-edit-cache", "ingame", "src")
n = 0
for fn in ("t2r-rogue-render-opti-const-ingame.pak", "sea-const-texture-adjust-ingame.pak"):
    if os.path.exists(os.path.join(src, fn)):
        bad, k = E.selftest(os.path.join(src, fn))
        assert not bad, bad
        n += k
print("ok  stock render-const trees re-written byte-identical (%d regions)" % n if n else "skip  stock trees (no level-edit-cache)")

sys.path.insert(0, os.path.join(TOOLS, "features"))
import sp_maps_build  # noqa: E402
m = [x for x in sp_maps_build.specs() if x["key"] == "p1-bookstore"][0]
rs = m["part1"].get("rs-level")
pk = os.path.join(sp_maps_build.P1_CONV, "%s-ingame.pak" % rs)
mod = os.path.join(sp_maps_build.P1_CONV, "%s.t1x.bin" % rs)
stock = os.path.join(MAIN, "re", "gamebin", "dc1", "render-settings", "t1x.bin")
if rs and os.path.exists(pk) and os.path.exists(mod):
    bad = E.check(open(pk, "rb").read(), open(mod, "rb").read(), open(stock, "rb").read() if os.path.exists(stock) else None)
    assert not bad, bad
    (rg, _), = E.read_pak_regions(open(pk, "rb").read())
    syms = {E.region_rs(r) for r in rg}
    blk = [ln for ln in sp_maps_build.p1_blocks(m) if ln.startswith("render-settings ")]
    assert sorted(syms) == sorted(ln.split(" ", 1)[1] for ln in blk), "registry block names every region's symbol"
    print("ok  %s: %d regions, %d render-settings symbols in the t1x module, registry block complete" % (rs, len(rg), len(syms)))
else:
    print("skip  converted rs level (python tools/part1/p1_levelset.py convert <Part I dir> p1-bookstore)")
