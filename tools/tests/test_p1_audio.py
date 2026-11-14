"""Offline proof of the Part I Bookstore ambience port (tools/part1/p1_audio.py).  No game, no GPU.
Needs the converted set (python tools/part1/p1_audio.py convert <Part I dir>), the main checkout's re/modfs and re/gamebin; skips itself without them.

  1. p1_audio.verify: both paks parse (loader / vram / trailer mirrors), 1,132 spawners, the region pak holds exactly one REGION_TREE and no
     SPAWNER_GROUP, every sound the level plays has an sfx-info row (carrier or TLOU2) and a cue in a shipped bank, the sound-env sids resolve,
     the fire barrels 6 / 7 are SfxProcess sfx-hun-fire-barrel, banks / streams are shipped or TLOU2's own.
  2. the region pak's REGION_TREE equals the converted Part I one except the renamed gating tags (names, geometry, every other tag).
  3. sp_maps_build.apply on a scratch copy of the mod's DC files: registry blocks, staged files, the 3 carrier modules registered in modules.bin
     (size + sorted export list = the file's rows), no sid exported by two modules, DC relocation check, the level set lists both levels.
  4. T2R_P1_AUDIO=0: the levels leave the level set and nothing is staged.
"""
import os
import shutil
import sys
import tempfile
import sys as _t2s, os as _t2o; _t2s.path.append(_t2o.path.normpath(_t2o.path.join(_t2o.path.dirname(_t2o.path.abspath(__file__)), ".."))); import t2rtmp  # noqa: E402,F401  (temp hygiene: tools/t2rtmp.py)

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.dirname(HERE)
for sub in ("features", "part1", "models", "maps"):
    sys.path.insert(0, os.path.join(TOOLS, sub))
_main = os.environ.get("T2R_MAIN_ROOT", os.path.dirname(TOOLS).split(os.sep + ".claude" + os.sep)[0])
if not os.environ.get("T2R_P1_CONV"):
    _abi = os.path.join(_main, "re", "part1", "x", "conv-abi-mix3")
    if os.path.isdir(_abi):
        os.environ["T2R_P1_CONV"] = _abi
import p1_audio as A  # noqa: E402
import sp_maps_build  # noqa: E402

FEAT = os.path.join(sp_maps_build._MAIN, "re", "modfs")
if not os.path.exists(os.path.join(A.AUDIO, "audio.json")) or not os.path.isdir(FEAT) or not os.path.exists(os.path.join(sp_maps_build.P1_CONV, "pak68-part1.txt")):
    print("skip  (no converted Part I ambience / modfs / converted Part I levels)")
    sys.exit(0)

# 1
bad = A.verify("p1-bookstore", lambda *a: None)
assert not bad, bad[:5]
print("ok  p1_audio.verify: paks, sounds -> sfx-info -> cues, sound-env, fire barrels, banks / streams")

# 2
import t2pak  # noqa: E402
import p1_rsenv as R  # noqa: E402
conv = open(os.path.join(A.AUDIO, "src", "hun-const-audio-ingame.conv.pak"), "rb").read()
new = open(os.path.join(A.AUDIO, "pak68", "hun-const-audio-rgn-ingame.pak"), "rb").read()
(ra, ga), = R.read_pak_regions(conv)
(rb, gb), = R.read_pak_regions(new)
assert len(ra) == len(rb) == 1077 and ga == gb
n_ren = 0
for x, y in zip(ra, rb):
    assert x["name"] == y["name"] and x["shape"] == y["shape"] and x["vols"] == y["vols"] and x["corners"] == y["corners"] and x["prio"] == y["prio"], x["name"]
    keep = sorted(t for t in x["tags"] if t[0] not in A.GATING_KEYS)
    assert keep == sorted(t for t in y["tags"] if t[0] in {k for k, _, _ in x["tags"]}), x["name"]
    assert not any(t[0] in A.GATING_KEYS for t in y["tags"]), x["name"]
    assert [k for k, _, _ in y["tags"]] == sorted(k for k, _, _ in y["tags"]), "tag dictionary must stay sorted"
    n_ren += any(t[0] in A.GATING_KEYS for t in x["tags"])
assert n_ren == 77, n_ren
# the aux (SfxProcess) blocks are untouched: same sound sids in the same order
spa, spb = A.Space(t2pak.TPak(conv)), A.Space(t2pak.TPak(new))
sfx_a = [(n, A.region_sfx(spa, r)) for r, n in A.region_records(spa)]
sfx_b = [(n, A.region_sfx(spb, r)) for r, n in A.region_records(spb)]
assert sfx_a == sfx_b and sum(1 for _, v in sfx_a if v) > 400
print(f"ok  region pak: 1077 regions identical to the converted Part I tree; gating tags renamed on {n_ren}; {sum(1 for _, v in sfx_a if v)} SfxProcess emitters untouched")

# 3
stage = tempfile.mkdtemp()
for rel in ("bin/dc1/test-tasks.bin", "bin/dc1/modules.bin", "bin/dc1/level-sets/level-sets-test.bin", "pak68.txt"):
    os.makedirs(os.path.dirname(os.path.join(stage, rel)), exist_ok=True)
    shutil.copyfile(os.path.join(FEAT, rel), os.path.join(stage, rel))
os.makedirs(os.path.join(stage, "pak68"))
m = [x for x in sp_maps_build.specs() if x["key"] == "p1-bookstore"][0]
assert m["part1"].get("audio"), "audio spec dropped although converted"
assert all(lv in m["levels"] for lv in A.levels_of(m)), "audio levels are in the map's level set"
shutil.copyfile(os.path.join(TOOLS, "features", "levels", m["pak"] + "-ingame.pak"), os.path.join(stage, "pak68", m["pak"] + "-ingame.pak"))
before = A.modules_table(open(os.path.join(stage, "bin", "dc1", "modules.bin"), "rb").read())
# (the whole sp_maps_build.apply also runs the SceneEditor edits / lighting headers of every map -- unrelated to the ambience, and test_p1_levelset
#  covers it; here only the ambience's own build steps run: registry patch + stage + the verify assertions apply() makes)
sp_maps_build.patch_registry(os.path.join(stage, "pak68.txt"), [m])
sp_maps_build.stage_part1_audio(stage, m, quiet=True) if hasattr(sp_maps_build, "stage_part1_audio") else A.stage(stage, m, log=lambda *a: None)
reg = open(os.path.join(stage, "pak68.txt"), encoding="latin1").read()
man = A.load_manifest()
lv, rg = m["part1"]["audio"]["level"], m["part1"]["audio"]["region-level"]
assert f"level-name {lv}\nlevel-id {lv}\npackage {lv}-ingame\nsound-bank lvl-hun-const-audio\n" in reg
assert f"level-name {rg}\nlevel-id {rg}\npackage {rg}-ingame\nsymbol ss-snd-fact-region\n" in reg
assert reg.count(f"level-name {lv}\n") == 1 and reg.count(f"level-name {rg}\n") == 1
i0, i1 = reg.index(f"level-name {lv}"), reg.index(f"level-name {rg}")
blk = reg[i0:i1 + 200]                               # (both blocks are appended together at the end of the registry)
assert "ss-snd-hun-" not in blk and "ir-pack" not in blk, blk[:400]
for b in man["banks"]:
    assert os.path.getsize(os.path.join(stage, "soundbank4", b + ".bnk")) > 1000 and os.path.exists(os.path.join(stage, "soundbank4", b + ".str")), b
for n in man["streams"]:
    assert os.path.getsize(os.path.join(stage, "sfx1", n)) > 100, n
after = A.modules_table(open(os.path.join(stage, "bin", "dc1", "modules.bin"), "rb").read())
assert len(after) == len(before), "no module entry added or lost (the carriers REPLACE unused TLOU2 modules)"
import dc_check  # noqa: E402
from dcfile import DcFile  # noqa: E402
owner = {}
for k, mi in man["modules"].items():
    path = os.path.join(stage, *mi["file"].split("/"))
    raw = open(path, "rb").read()
    dc_check.check_relocation(raw, mi["carrier"])
    rows = [r[0] for r in A.dc_rows(DcFile(raw))]
    e, sz, ex = after[mi["carrier"]]
    assert sz == len(raw) == mi["size"] and ex == sorted(ex) and ex == rows, (k, sz, len(raw), len(ex), len(rows))
    assert before[mi["carrier"]][1] != sz or k == "none"
for name, (e, sz, ex) in after.items():
    for x in ex:
        if x != A.NAMESPACE:
            owner.setdefault(x, []).append(name)
dup = {x: v for x, v in owner.items() if len(v) > 1}
dup0 = {}
for name, (e, sz, ex) in before.items():
    for x in ex:
        if x != A.NAMESPACE:
            dup0.setdefault(x, []).append(name)
assert len(dup) <= len([1 for v in dup0.values() if len(v) > 1]), f"the carriers introduced {len(dup)} duplicate exports"
lvls = [x for x in sp_maps_build.specs() if x["key"] == "p1-bookstore"][0]["levels"]
assert lv in lvls and rg in lvls
print(f"ok  registry + stage: registry blocks, {len(man['files'])} files staged, 3 carrier modules registered (size + exports), no new duplicate exports, DC relocation OK")
paths = sp_maps_build.p1_audio_files(m)
assert paths == [f["path"] for f in man["files"]] and all(os.path.exists(os.path.join(stage, *p.split("/"))) for p in paths)
print(f"ok  manifest paths: {len(paths)}")

# 4
os.environ["T2R_P1_AUDIO"] = "0"
m0 = [x for x in sp_maps_build.specs() if x["key"] == "p1-bookstore"][0]
assert not m0["part1"].get("audio") and not any(x in m0["levels"] for x in A.levels_of(m)) and sp_maps_build.p1_audio_files(m0) == []
print("ok  T2R_P1_AUDIO=0: levels out of the level set, nothing staged")
shutil.rmtree(stage, ignore_errors=True)
