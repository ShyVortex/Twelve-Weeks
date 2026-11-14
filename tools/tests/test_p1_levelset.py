"""Offline check of the Part I test map (p1-bookstore): sp_maps_build.apply on a scratch copy of the mod's DC files + pak68.txt.
Needs the main checkout's re/modfs_feat and the converted paks (python tools/part1/p1_levelset.py convert <Part I dir> p1-bookstore);
skips itself when either is missing."""
import os
import shutil
import sys
import tempfile
import sys as _t2s, os as _t2o; _t2s.path.append(_t2o.path.normpath(_t2o.path.join(_t2o.path.dirname(_t2o.path.abspath(__file__)), ".."))); import t2rtmp  # noqa: E402,F401  (temp hygiene: tools/t2rtmp.py)

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(TOOLS, "features"))
if not os.environ.get("T2R_P1_CONV"):         # the shipped Part I set is the retargeted conv-abi (geometry-upgrade.md s10); it also holds the -rs render-settings pak
    _main = os.environ.get("T2R_MAIN_ROOT", os.path.dirname(TOOLS).split(os.sep + ".claude" + os.sep)[0])
    _abi = os.path.join(_main, "re", "part1", "x", "conv-abi")
    if os.path.isdir(_abi):
        os.environ["T2R_P1_CONV"] = _abi
import sp_maps_build  # noqa: E402

MAIN = sp_maps_build._MAIN
FEAT = os.path.join(MAIN, "re", "modfs")      # (the unpatched mod files: re/modfs_feat already carries every built map's subnodes)
if not os.path.isdir(FEAT):
    FEAT = os.path.join(MAIN, "re", "modfs_feat")
if not os.path.isdir(FEAT) or not os.path.exists(os.path.join(sp_maps_build.P1_CONV, "pak68-part1.txt")):
    print("skip  (no re/modfs_feat or no converted Part I paks)")
    sys.exit(0)
stage = tempfile.mkdtemp()
for rel in ("bin/dc1/test-tasks.bin", "bin/dc1/modules.bin", "bin/dc1/level-sets/level-sets-test.bin", "pak68.txt"):
    os.makedirs(os.path.dirname(os.path.join(stage, rel)), exist_ok=True)
    shutil.copyfile(os.path.join(FEAT, rel), os.path.join(stage, rel))
os.makedirs(os.path.join(stage, "pak68"))
m = [x for x in sp_maps_build.specs() if x["key"] == "p1-bookstore"][0]
shutil.copyfile(os.path.join(TOOLS, "features", "levels", m["pak"] + "-ingame.pak"), os.path.join(stage, "pak68", m["pak"] + "-ingame.pak"))
sizes = sp_maps_build.apply(stage, [m])
assert sizes and sizes["level-sets"] and sizes["test-tasks"]
reg = open(os.path.join(stage, "pak68.txt"), encoding="latin1").read()
for lv in m["part1"]["levels"]:
    if sp_maps_build.p1_phys(lv):                  # collision translated by p1_levelset convert (conv/phys-status.json)
        assert f"level-name {lv}\nlevel-id {lv}\npackage {lv}\npackage {lv}-phys\n" in reg, lv
        assert os.path.getsize(os.path.join(stage, "pak68", lv + "-phys.pak")) > 100
    else:
        assert f"level-name {lv}\nlevel-id {lv}\npackage {lv}\n" in reg, lv  # no -phys / -ingame by default
    assert os.path.getsize(os.path.join(stage, "pak68", lv + ".pak")) > 1000
assert "upperLeft" not in reg and "lowerRight" not in reg, "Part I-only keys must not reach TLOU2's registry"
rs = sp_maps_build.p1_rs(m)
if rs:                                             # Part I render settings (re/part1/geometry-upgrade.md s11)
    assert f"level-name {rs}\nlevel-id {rs}\npackage {rs}-ingame\nsymbol *" in reg, rs
    assert os.path.getsize(os.path.join(stage, "pak68", rs + "-ingame.pak")) > 1000
    assert os.path.exists(os.path.join(stage, "bin", "dc1", "render-settings", "t1x.bin"))
    assert rs in m["levels"], "the rs level is in the map's level set"
sys.path.insert(0, os.path.join(TOOLS, "part1"))
sys.path.insert(0, os.path.join(TOOLS, "models"))
import p1_convert  # noqa: E402
for fn in sorted(os.listdir(os.path.join(stage, "pak68"))):
    if fn.startswith(("hun-", "sky-hun-")):       # Part I levels (+ the map's Part I sky, + its render-settings level)
        bad = p1_convert.loader_check(os.path.join(stage, "pak68", fn)) + p1_convert.vram_check(os.path.join(stage, "pak68", fn)) + p1_convert.vram_sort_check(os.path.join(stage, "pak68", fn)) + p1_convert.trailer_check(os.path.join(stage, "pak68", fn)) + p1_convert.lights_check(os.path.join(stage, "pak68", fn)) + p1_convert.pointer_pattern_check(os.path.join(stage, "pak68", fn)) + p1_convert.geometry_extent_check(os.path.join(stage, "pak68", fn))
        assert not bad, (fn, bad[:3])      # the engine's fixup walk (exe+12e4460)
        if not fn.endswith(("-phys.pak", "-ingame.pak")) and os.environ.get("T2R_P1_ABI", "1") != "0":
            import p1_abi                  # Part I shaders on TLOU2's engine-global ABI (re/part1/geometry-upgrade.md s10)
            bad, _st, _rows = p1_abi.check(os.path.join(stage, "pak68", fn))
            assert not bad, (fn, bad[:3], "reconvert: p1_levelset.py convert <Part I dir> p1-bookstore --tex-drop=2")
print("ok  p1-bookstore: level set + subnode + registry + staged converted paks (verify passed)")
import p1_spawns  # noqa: E402
_bad = p1_spawns.check("p1-bookstore", quiet=True)
assert not _bad, ("spawn / box without ground on the converted collision", _bad[:3])
print("ok  p1-bookstore: every spawn / box has ground, headroom and wall clearance on the converted collision")
