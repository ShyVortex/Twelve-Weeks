"""Offline proof that the converted Part I Bookstore (p1-bookstore) opens and edits in the SceneEditor like jackson-market.  CPU only; NO GUI, NO GPU:
the editor's own parser (TLOUSceneEditor.Core.PackageReader) is driven headless through tools/maps/editor_loadtest.ps1, everything else runs on scratch copies.
  1. LOAD      every near Bookstore level (all part1 levels with --all): groups / meshes / vertices / triangles > 0, no index outside its vertex list
  2. COLLISION the -phys.pak of every level converts (phys_dump.py mirror) to > 0 triangles
  3. LAYOUT    markers: the pak built from data/p1-bookstore-spawns.json imports with zero differences; a moved box + moved respawn + a random item spot import
               (apply on scratch json) and the rebuilt pak imports with the edits in place
  4. GEOEDIT   a dummy instance removal + collision box / delete (data/p1-bookstore-geoedits.json / -colledits.json format, scratch data dir) runs through
               level_edit.build_edits on the Part I paks: the removed record leaves the render bbox, the edited -phys.pak has the expected triangle count
Run: python tools/tests/test_p1_bookstore_editor.py [--all]"""
import glob
import json
import os
import shutil
import subprocess
import sys
import tempfile
import sys as _t2s, os as _t2o; _t2s.path.append(_t2o.path.normpath(_t2o.path.join(_t2o.path.dirname(_t2o.path.abspath(__file__)), ".."))); import t2rtmp  # noqa: E402,F401

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.dirname(HERE)
MAPS = os.path.join(TOOLS, "maps")
sys.path.insert(0, MAPS)
sys.path.insert(0, os.path.join(TOOLS, "spawns"))
sys.path.insert(0, os.path.join(TOOLS, "models"))
import numpy as np  # noqa: E402
import p1_src  # noqa: E402
import editor_import as EI  # noqa: E402
import itemspots as IS  # noqa: E402
import sp_maps as SM  # noqa: E402

KEY = "p1-bookstore"
NEAR = ["hun-checkpoint-bookstore", "hun-checkpoint-bookstore-rear", "hun-checkpoint-bookstore-facade", "hun-checkpoint-maze"]
SE = r".\tools\local\SceneEditor"
DLLS = [os.path.join(SE, d) for d in ("build-next41", "unpacked")]        # build-next41 = PackageReader with the Part I (GEOMETRY_1 0x37) fix
DLL = next((d for d in DLLS if os.path.exists(os.path.join(d, "TLOUSceneEditor.dll"))), None)
FAILS = []


def check(cond, what):
    print(("ok   " if cond else "FAIL ") + what)
    if not cond:
        FAILS.append(what)


conv = p1_src.conv_dir()
if not DLL or not conv:
    print("skip  SceneEditor Core DLL or converted Part I folder not found")
    sys.exit(0)
td = tempfile.mkdtemp(prefix="p1ed_")
ALL = "--all" in sys.argv
levels = [lv for lv in p1_src.levels_of(KEY) if not lv.startswith("sky-")] if ALL else NEAR


def loadtest(paks):
    out = os.path.join(td, "load.json")
    subprocess.run(["pwsh", "-NoProfile", "-File", os.path.join(MAPS, "editor_loadtest.ps1"), "-Dll", DLL, "-Out", out, "-Pak", "|".join(paks)], check=True, stdout=subprocess.DEVNULL)
    r = json.load(open(out, encoding="utf-8-sig"))
    return r if isinstance(r, list) else [r]


# ---- 1. load
rows = {r["pak"]: r for r in loadtest([os.path.join(conv, lv + ".pak") for lv in levels])}
tot = [0, 0, 0]
for lv in levels:
    r = rows[lv + ".pak"]
    ok = not r.get("error") and r["groups"] > 0 and r["vertices"] > 0 and r["triangles"] > 0 and r["bad_indices"] == 0
    tot[0] += r["groups"]
    tot[1] += r["vertices"]
    tot[2] += r["triangles"]
    check(ok, f"load {lv}: {r.get('error') or ''} {r['groups']} groups, {r['meshes']} meshes, {r['vertices']} vertices, {r['triangles']} triangles")
print(f"     total {tot[0]} groups, {tot[1]} vertices, {tot[2]} triangles")

# ---- 2. collision
import level_edit as le  # noqa: E402
for lv in levels:
    f = os.path.join(conv, lv + "-phys.pak")
    if not os.path.exists(f):
        check(False, f"collision {lv}: no -phys.pak")
        continue
    _, items = le.phys_items(f)
    n = sum(len(le.hc.triangles(it.mesh)[1]) for it in items)
    st = json.load(open(os.path.join(conv, "phys-status.json"))).get(lv) if os.path.exists(os.path.join(conv, "phys-status.json")) else None
    check(n > 0 or st == "empty", f"collision {lv}: {len(items)} items, {n} triangles" + (" (converter status: empty, no collision in Part I)" if n == 0 else ""))

# ---- 3. layout round trip (scratch copies of the data)
data = os.path.join(td, "data")
os.makedirs(data)
for f in glob.glob(os.path.join(MAPS, "data", KEY + "-*.json")):
    shutil.copyfile(f, os.path.join(data, os.path.basename(f)))
spec_path = os.path.join(td, "sp_maps.json")
shutil.copyfile(os.path.join(MAPS, "sp_maps.json"), spec_path)
SM.SPEC, SM.DATA = spec_path, data
EI.SPEC, EI.DATA = spec_path, data
IS.DATA, IS.HEADER = data, os.path.join(td, "itemspots.h")


def imp(pak):
    return EI.run(KEY, pak, spec_path, data)


def edit(src, dst, ops):
    o = os.path.join(td, "ops.json")
    json.dump(ops, open(o, "w"))
    subprocess.run(["pwsh", "-NoProfile", "-File", EI.EDIT, "-In", src, "-Out", dst, "-Ops", o], check=True, stdout=subprocess.DEVNULL)


base = os.path.join(td, "base.pak")
SM.pak(KEY, out=base)
df, plan, spawns, _ = imp(base)
check(df.n == 0, f"pak built from the data imports with zero differences ({df.n})")
dump = EI.read_pak(base)
box1 = next(s for s in dump if s["name"] == "to1-supplybox-1")
r2 = next(s for s in dump if s["name"] == "to1-spawn-point-2")
q = [0, 0, 0, 1]
A = [box1["pos"][0] + 3.0, box1["pos"][1], box1["pos"][2] + 3.0]
moved = os.path.join(td, "moved.pak")
edit(base, moved, {"move": [{"name": "to1-supplybox-1", "pos": [box1["pos"][0] + 1.0, box1["pos"][1], box1["pos"][2]]},
                            {"name": "to1-spawn-point-2", "pos": [r2["pos"][0], r2["pos"][1], r2["pos"][2] + 2.0]}],
                    "add_random": [{"name": "random-util-1-molotov", "art": "molotov", "pos": A, "quat": q},
                                   {"name": "random-util-1-pipebomb", "art": "pipe-bomb", "pos": A, "quat": q}]})
df, plan, spawns, _ = imp(moved)
df.show()
check(len(df.lines.get("boxes", [])) >= 1 and len(df.lines.get("respawns", [])) == 1 and len(df.lines.get("itemspots", [])) == 1,
      "diff: box 1 moved, respawn 2 moved, 1 item spot added")
sp0 = json.load(open(os.path.join(data, KEY + "-spawns.json")))
EI.apply(KEY, df, plan, spawns, spec_path, data)
sp1 = json.load(open(os.path.join(data, KEY + "-spawns.json")))
check(abs(sp1["respawns"][1]["pos"][2] - (sp0["respawns"][1]["pos"][2] + 2.0)) < 0.002 and sp1["intro0"] == sp0["intro0"], "spawns json: respawn 2 moved, intros untouched")
check(sp1["boxes"] != sp0["boxes"], "spawns json: supply box 1 moved")
ij = os.path.join(data, KEY + "-itemspots.json")
check(os.path.exists(ij) and len(json.load(open(ij))["spots"]) == 1, "itemspots json written with the new spot")
rebuilt = os.path.join(td, "rebuilt.pak")
SM.pak(KEY, out=rebuilt)
df, _, _, _ = imp(rebuilt)
check(not df.lines.get("boxes") and not df.lines.get("respawns"), "pak rebuilt after apply imports without box / respawn differences")

# ---- 4. geoedit + colledit on the Part I paks (scratch data + scratch level-edit dir)
import geoedit  # noqa: E402
import coll_edit  # noqa: E402
import ndpak  # noqa: E402
le.CACHE = os.path.join(td, "lec")
geoedit.DATA = coll_edit.DATA = os.path.join(td, "gdata")
os.makedirs(geoedit.DATA)
LV = "hun-checkpoint-bookstore"
src = le.fetch(LV, os.path.join(le.CACHE, "src"), None, ("", "-phys"))
ins = [i for i in le.find_instances(ndpak.Pak(src[""])) if i.wlo is not None and 0.3 < max(np.array(i.whi) - np.array(i.wlo)) < 1.2]
check(len(ins) > 0, f"{LV}: {len(ins)} small prop instances found in the converted pak (level_edit.find_instances)")
g = ins[0]
box = [float(x) for x in list(np.array(g.wlo) - 0.05) + list(np.array(g.whi) + 0.05)]
json.dump({"key": KEY, "edits": [{"name": "test prop", "level": LV, "kind": "instance", "asset": "x", "record": "0x%x" % g.pak_off, "box": box, "collision": "inside", "active": True}]},
          open(os.path.join(geoedit.DATA, KEY + "-geoedits.json"), "w"))
tris = np.array([t for it in le.phys_items(src["-phys"])[1] for t in np.asarray(le.hc.triangles(it.mesh)[1], float).reshape(-1, 9)]).reshape(-1, 3, 3)
n0 = len(tris)
c = tris[len(tris) // 2].mean(0)
w = tris[len(tris) // 3]
json.dump({"key": KEY, "version": 1, "edits": [
    {"name": "test box", "level": LV, "kind": "box", "active": True, "center": [float(c[0]), float(c[1]) + 1.0, float(c[2])], "size": [1, 1, 1], "yaw": 0.0, "like": [float(x) for x in c]},
    {"name": "test delete", "level": LV, "kind": "delete", "active": True, "tris": [[float(x) for x in w.reshape(-1)]]}]},
    open(os.path.join(geoedit.DATA, KEY + "-colledits.json"), "w"))
ed = geoedit.edits_for(KEY)
check({e["action"] for e in ed} >= {"remove", "colledit"}, f"geoedit.edits_for: {sorted({e['action'] for e in ed})}")
files = le.build_edits(ed, out_dir=os.path.join(td, "out"))
rp = next(f for f in files if os.path.basename(f) == LV + ".pak")
pp = next(f for f in files if f.replace("\\", "/").endswith("colledit/" + LV + "-phys.pak"))
r = loadtest([rp])[0]
check(r["triangles"] == rows.get(LV + ".pak", r)["triangles"] and r["bbox_lo"][1] < -900,
      f"edited render pak loads in the editor parser ({r['triangles']} triangles); the removed record is at y {r['bbox_lo'][1]:.0f} (hidden)")
_, items = le.phys_items(pp)
n1 = sum(len(le.hc.triangles(it.mesh)[1]) for it in items)
check(n1 > n0 + 6, f"edited -phys.pak: {n0} -> {n1} triangles (+12 box, - deleted)")

shutil.rmtree(td, ignore_errors=True)
print("ALL OK" if not FAILS else f"{len(FAILS)} FAILED")
sys.exit(1 if FAILS else 0)
