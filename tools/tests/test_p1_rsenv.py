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
with sp_maps_build.p1_map_env(m):         # (the map's own conv dir: tools/part1/data/p1_maps/<key>.json "build")
    conv = sp_maps_build.P1_CONV
if os.environ.get("T2R_P1_LUT", "0") == "0" and os.path.exists(os.path.join(conv, "nolut", "%s.t1x.bin" % rs)):
    conv = os.path.join(conv, "nolut")     # (what p1_stage.stage_rs_files stages)
pk = os.path.join(conv, "%s-ingame.pak" % rs)
mod = os.path.join(conv, "%s.t1x.bin" % rs)
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

# Two Part I maps in one build: the staged t1x module = TLOU2's stock module + every map's symbols (p1_rsenv.merge_modules); a map
# with p1_maps json "rs_renames" (Plaza) stages Part I's city base under its own name: rs pak tags + module symbol + registry lines
import shutil  # noqa: E402
P1S = sp_maps_build._p1_stage()
mods, keys, rns, paks = [], [], [], []
tmp = tempfile.mkdtemp(prefix="t2r-rsmerge-")
try:
    for key in ("p1-bookstore", "p1-plaza"):
        mm = [x for x in sp_maps_build.specs() if x["key"] == key][0]
        with sp_maps_build.p1_map_env(mm):
            try:
                dst = P1S.stage_rs_files(os.path.join(tmp, key), mm, sp_maps_build.P1_CONV)
            except AssertionError:
                dst = None
            rn = sp_maps_build.p1_rs_renames(mm)
            blk = sp_maps_build.p1_blocks(mm) if dst else []
        if dst:
            mods.append(open(dst, "rb").read())
            keys.append(key)
            rns.append(rn)
            rsl = mm["part1"]["rs-level"]
            paks.append(open(os.path.join(tmp, key, "pak68", rsl + "-ingame.pak"), "rb").read())
            for o, n in rn.items():
                assert "render-settings " + n in blk and "render-settings " + o not in blk, "%s: registry lines renamed" % key
finally:
    shutil.rmtree(tmp, ignore_errors=True)
if len(mods) == 2 and os.path.exists(stock):
    sd = open(stock, "rb").read()
    for key, pk, rn in zip(keys, paks, rns):
        if rn:
            new_pk = E.rename_rs_pak(pk, rn)
            (rg0, _), = E.read_pak_regions(pk)
            (rg1, _), = E.read_pak_regions(new_pk)
            assert [rn.get(E.region_rs(r), E.region_rs(r)) for r in rg0] == [E.region_rs(r) for r in rg1], "%s: renamed rs tags" % key
    sid_rn = [{E.fnv(o): E.fnv(n) for o, n in rn.items()} for rn in rns]
    merged, conflicts = E.merge_modules(sd, mods, sid_rn)
    got = E.read_symbols(merged)
    used = []
    for pk in paks:
        (rg, _g), = E.read_pak_regions(pk)
        used.append({E.fnv(E.region_rs(r)) for r in rg if E.region_rs(r)})
    for sid, losers in conflicts.items():      # a later map's differing copy is dropped only where that map's regions do not use it
        assert all(sid not in used[i] or sid in sid_rn[i] for i in losers), "%#x differs and a later map uses it" % sid
    for i, (key, d, rn) in enumerate(zip(keys, mods, sid_rn)):
        for sid, recs in E.read_symbols(d).items():
            if i == 0 or sid in rn or sid in used[i]:
                assert sorted(got[rn.get(sid, sid)]) == sorted(recs), "%s: symbol %#x not kept as the map has it" % (key, sid)
    assert E.read_symbols(merged).keys() >= E.read_symbols(mods[0]).keys()
    one, c1 = E.merge_modules(sd, mods[:1])
    assert not c1 and E.read_symbols(one) == E.read_symbols(mods[0]), "single-map merge = that map's symbols"
    print("ok  t1x %s: %d symbols (%d bytes), renames %s; first map's copy kept (later copy unused there): %s" % (
        "+".join(keys), len(got), len(merged), [r for r in rns if r], [("%#x" % k) for k in conflicts]))
else:
    print("skip  t1x merge (needs both maps' converted rs levels: %s)" % (keys or "none"))
