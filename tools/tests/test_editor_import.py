"""Offline test of tools/maps/editor_import.py (SceneEditor-saved pak -> spawns / props / medkits json), all on scratch copies:
  1. round trip: the committed Capitol Hill pak imports with ZERO differences, and so does a pak rebuilt from the json (sp_maps.pak)
  2. synthetic edit (scratch pak, SceneEditor Core DLL headless): one prop moved 1 m + a respawn moved + a medkit added (with the 4 generated kits
     carried over) -> the diff lists exactly those; --apply writes spawns / props / medkits json + header; the rebuilt pak imports with zero diff;
     medkits.py gen keeps the hand placed kits
  3. a lone medkit spawner = the pak is the truth: the other kits show as removed; props: art swap / delete / add are told apart
  4. random item spots: `random-` spawner stacks cluster into spots (0.5 m / parent chain), diff + apply write data/<key>-itemspots.json + itemspots.h,
     the rebuilt pak carries none of them and imports without item spot changes; a moved spot shows as moved
Run: python tools/tests/test_editor_import.py   (skips when the SceneEditor DLL is absent)"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import sys as _t2s, os as _t2o; _t2s.path.append(_t2o.path.normpath(_t2o.path.join(_t2o.path.dirname(_t2o.path.abspath(__file__)), ".."))); import t2rtmp  # noqa: E402,F401  (temp hygiene: tools/t2rtmp.py)

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.dirname(HERE)
MAPS = os.path.join(TOOLS, "maps")
sys.path.insert(0, MAPS)
sys.path.insert(0, os.path.join(TOOLS, "spawns"))
import editor_import as EI  # noqa: E402
import itemspots as IS  # noqa: E402
import medkits as MK  # noqa: E402
import sp_maps as SM  # noqa: E402

KEY = "capitol-shops"
PAK = os.path.join(TOOLS, "features", "levels", "to1-pvp-capitol-shops-ingame.pak")
DLL = r".\tools\local\SceneEditor\unpacked\TLOUSceneEditor.dll"
FAILS = []


def check(cond, what):
    print(("ok   " if cond else "FAIL ") + what)
    if not cond:
        FAILS.append(what)


if not os.path.exists(DLL):
    print("skip  SceneEditor Core DLL not found")
    sys.exit(0)

td = tempfile.mkdtemp(prefix="editor_import_")
data = os.path.join(td, "data")
os.makedirs(data)
for f in (f"{KEY}-spawns.json", f"{KEY}-medkits.json"):
    shutil.copyfile(os.path.join(MAPS, "data", f), os.path.join(data, f))
spec_path = os.path.join(td, "sp_maps.json")
shutil.copyfile(os.path.join(MAPS, "sp_maps.json"), spec_path)
header = os.path.join(td, "medkits.h")
SM.SPEC, SM.DATA = spec_path, data
MK.DATA, MK.HEADER = data, header
EI.SPEC, EI.DATA = spec_path, data
ihead = os.path.join(td, "itemspots.h")
IS.DATA, IS.HEADER = data, ihead


def imp(pak):
    return EI.run(KEY, pak, spec_path, data)


def edit(src, dst, ops):
    o = os.path.join(td, "ops.json")
    json.dump(ops, open(o, "w"))
    subprocess.run(["pwsh", "-NoProfile", "-File", EI.EDIT, "-In", src, "-Out", dst, "-Ops", o], check=True, stdout=subprocess.DEVNULL)


# ---- 1. round trip
df, plan, _, _ = imp(PAK)
check(df.n == 0, f"committed pak imports with zero differences ({df.n})")
rebuilt = os.path.join(td, "rebuilt.pak")
SM.pak(KEY, out=rebuilt)
df, plan, _, _ = imp(rebuilt)
check(df.n == 0, f"pak rebuilt from the json imports with zero differences ({df.n})")

spec0 = json.load(open(spec_path, encoding="utf-8"))["maps"]
m0 = next(m for m in spec0 if m["key"] == KEY)
props0 = m0["props"]
sp0 = json.load(open(os.path.join(data, f"{KEY}-spawns.json")))
mk0 = json.load(open(os.path.join(data, f"{KEY}-medkits.json")))
dump = EI.read_pak(PAK)
p5 = next(s for s in dump if s["name"] == "to1-prop-5")
r2 = next(s for s in dump if s["name"] == "to1-spawn-point-2")

# ---- 2. synthetic edit: prop 5 moved 1 m, respawn 2 moved 2 m, one medkit added (+ the 4 generated ones carried over)
kits = [{"name": f"to1-healthkit-{i + 1}", "pos": k["pos"], "quat": [0, 0, 0, 1]} for i, k in enumerate(mk0["kits"])]
new_kit = {"name": "to1-healthkit-5", "pos": [mk0["kits"][0]["pos"][0] + 6.0, mk0["kits"][0]["pos"][1], mk0["kits"][0]["pos"][2]], "quat": [0, 0, 0, 1]}
edited = os.path.join(td, "edited.pak")
edit(PAK, edited, {"move": [{"name": "to1-prop-5", "pos": [p5["pos"][0] + 1.0, p5["pos"][1], p5["pos"][2]]},
                            {"name": "to1-spawn-point-2", "pos": [r2["pos"][0], r2["pos"][1], r2["pos"][2] + 2.0]}],
                   "add_medkits": kits + [new_kit]})
df, plan, spawns, _ = imp(edited)
df.show()
check(len(df.lines.get("props", [])) == 1 and "moved 1.00 m" in df.lines["props"][0], "prop diff: exactly one prop, moved 1.00 m")
check(len(df.lines.get("respawns", [])) == 1 and "moved 2.00 m" in df.lines["respawns"][0] and "respawn 2 " in df.lines["respawns"][0], "respawn diff: exactly respawn 2, moved 2.00 m")
check(len(df.lines.get("medkits", [])) == 1 and df.lines["medkits"][0].startswith("+ added kit"), "medkit diff: exactly one added kit")
check(df.n == 3 and not any(k in df.lines for k in ("player", "intro0", "intro1", "boxes")), "nothing else differs")
check(len(plan["props"]) == len(props0) and plan["props"][4].get("auto") == props0[4].get("auto") and plan["props"][4].get("note") == props0[4].get("note"),
      "moved prop keeps its metadata (auto / note)")
EI.apply(KEY, df, plan, spawns, spec_path, data)
spec1 = next(m for m in json.load(open(spec_path, encoding="utf-8"))["maps"] if m["key"] == KEY)
check(abs(spec1["props"][4]["pos"][0] - (props0[4]["pos"][0] + 1.0)) < 0.002 and spec1["props"][:4] == props0[:4] and spec1["props"][5:] == props0[5:],
      "sp_maps.json: only prop 5 changed")
sp1 = json.load(open(os.path.join(data, f"{KEY}-spawns.json")))
check(abs(sp1["respawns"][1]["pos"][2] - (sp0["respawns"][1]["pos"][2] + 2.0)) < 0.002 and sp1["respawns"][0] == sp0["respawns"][0]
      and sp1["boxes"] == sp0["boxes"] and sp1["intro0"] == sp0["intro0"], "spawns json: only respawn 2 changed")
mk1 = json.load(open(os.path.join(data, f"{KEY}-medkits.json")))
check(mk1["hand_placed"] and len(mk1["kits"]) == len(mk0["kits"]) + 1 and mk1["kits"][:len(mk0["kits"])] == mk0["kits"] and mk1["map_index"] == mk0["map_index"]
      and set(mk1) == set(mk0) | {"hand_placed"}, "medkits json: same format + hand_placed, old kits untouched, 1 added")
h = open(header).read()
check("MK_CAPITOL_SHOPS[]" in h and f"{{19, MK_CAPITOL_SHOPS, {len(mk1['kits'])}}}" in h, "medkits.h regenerated with the capitol kits")
check(MK.hand_placed(KEY) and MK.gen_map(KEY)["kits"] == mk1["kits"], "medkits.py gen keeps hand placed kits")
rebuilt2 = os.path.join(td, "rebuilt2.pak")
SM.pak(KEY, out=rebuilt2)
df, _, _, _ = imp(rebuilt2)
check(df.n == 0 or all(k == "medkits" for k in df.lines), "pak rebuilt after --apply: spawns + props round trip with zero differences")
check(not df.lines.get("props") and not df.lines.get("respawns"), "  (a rebuilt pak carries no kits: the ext spawns them from medkits.h)")
df, _, _, _ = imp(edited)
check(df.n == 0, f"the edited pak now differs by nothing from the imported json ({df.n})")

# ---- 3. a lone medkit; art swap, delete, add
a_prop = next(s for s in dump if s["name"] == "to1-prop-8")
d_prop = next(s for s in dump if s["name"] == "to1-prop-9")
swap_art = "san-wood-crate-1x1-blocker-a" if a_prop["art"] != "san-wood-crate-1x1-blocker-a" else "invis-collision"
shutil.copyfile(os.path.join(MAPS, "sp_maps.json"), spec_path)
for f in (f"{KEY}-spawns.json", f"{KEY}-medkits.json"):
    shutil.copyfile(os.path.join(MAPS, "data", f), os.path.join(data, f))
lone = os.path.join(td, "lone.pak")
far_kit = dict(new_kit, pos=[new_kit["pos"][0] + 40.0, new_kit["pos"][1], new_kit["pos"][2]])
edit(PAK, lone, {"add_medkits": [far_kit], "remove": [d_prop["name"]], "set_art": [{"name": a_prop["name"], "art": swap_art}]})
df, _, _, _ = imp(lone)
nk0 = len(mk0["kits"])
check(len(df.lines.get("medkits", [])) == nk0 + 1 and sum(1 for l in df.lines["medkits"] if l.startswith("- removed")) == nk0,
      "a pak with one medkit is the truth for all kits: all old removed + 1 added")
pl = df.lines.get("props", [])
check(len(pl) == 2 and sum(l.startswith("- removed") for l in pl) == 1 and sum(l.startswith("~") and f"art {a_prop['art']} -> {swap_art}" in l for l in pl) == 1,
      "deleted prop shows as removed, art swap as art changed")

# ---- 4. random item spots
shutil.copyfile(os.path.join(MAPS, "sp_maps.json"), spec_path)
for f in (f"{KEY}-spawns.json", f"{KEY}-medkits.json"):
    shutil.copyfile(os.path.join(MAPS, "data", f), os.path.join(data, f))
q = [0, 0.3910527, 0, 0.9203683]
A = [-67.57, -6.80, -228.60]
rs = [{"name": "random-util-1-molotov", "art": "molotov", "pos": A, "quat": q},
      {"name": "random-util-2-pipebomb", "art": "pipe-bomb", "pos": [A[0] + 0.3, A[1] - 0.03, A[2]], "quat": q},
      {"name": "random-util-2-shiv", "art": "knife-shiv", "pos": [A[0], A[1], A[2] + 0.4], "quat": q},
      {"name": "random-util-2-shiv-1", "art": "knife-shiv", "pos": A, "quat": q},                      # a duplicate on the same spot: one candidate
      {"name": "random-util-3-stun", "art": "stun-bomb", "pos": [A[0] + 8, A[1], A[2]], "quat": q},    # 8 m away: its own spot, one candidate
      {"name": "random-ammo-pistol-1-a", "art": "ammo-pistol", "pos": [A[0], A[1], A[2] + 20], "quat": q},
      {"name": "random-ammo-pistol-2-b", "art": "ammo-rifle", "pos": [A[0] + 0.1, A[1], A[2] + 20], "quat": q},
      {"name": "random-util-9-x", "art": "molotov", "pos": [A[0], A[1], A[2] + 20.2], "quat": q}]       # other family at the ammo spot: stays apart
rpak = os.path.join(td, "random.pak")
edit(PAK, rpak, {"add_random": rs})
df, plan, spawns, _ = imp(rpak)
df.show()
its = df.lines.get("itemspots", [])
check(len(its) == 4 and all(l.startswith("+ added item spot") for l in its), "random- stacks: 4 spots added (util stack, util single, ammo pair, util at the ammo place)")
check(not any("random-" in n for n in df.info if n.startswith("UNRECOGNISED")), "random- spawners are no longer unrecognised")
check(any("only 1 candidate" in n for n in df.info), "single-candidate spot is flagged")
sp = {(s["family"], len(s["arts"])): s for s in plan["spots"]}
check(("util", 3) in sp and set(sp[("util", 3)]["arts"]) == {"molotov", "pipe-bomb", "knife-shiv"}, "util stack: 3 candidates (duplicate shiv deduped)")
check(("ammo-pistol", 2) in sp, "family = the name after random- up to the next -<digit> (ammo-pistol)")
check(df.n == 4, f"nothing else differs ({df.n})")
EI.apply(KEY, df, plan, spawns, spec_path, data)
ij = json.load(open(os.path.join(data, f"{KEY}-itemspots.json")))
check(ij["map_index"] == 19 and len(ij["spots"]) == 4, "itemspots json written (map index 19, 4 spots)")
h = open(ihead).read()
check("ISP_CAPITOL_SHOPS[]" in h and '"molotov", "pipe-bomb", "shiv"' in h and '"ammo-pistol", "ammo-rifle"' in h and "{19, ISP_CAPITOL_SHOPS" in h,
      "itemspots.h: spots with game item ids (knife-shiv -> shiv, ammo arts as ids)")
rebuilt3 = os.path.join(td, "rebuilt3.pak")
SM.pak(KEY, out=rebuilt3)
check(not any(s["name"].startswith("random-") for s in EI.read_pak(rebuilt3)), "the generated pak carries no random- spawner (the ext spawns them)")
df, plan, _, _ = imp(rebuilt3)
check(not df.lines.get("itemspots") and plan["spots"] is None and any("item spot(s)" in n for n in df.info),
      "a pak without random- spawners leaves the spots alone")
df, plan, _, _ = imp(rpak)
check(df.n == 0, f"the random pak now imports with zero differences ({df.n})")
moved_pak = os.path.join(td, "random-moved.pak")
edit(rpak, moved_pak, {"move": [{"name": "random-util-3-stun", "pos": [A[0] + 10, A[1], A[2]]}], "remove": ["random-util-9-x"]})
df, plan, _, _ = imp(moved_pak)
il = df.lines.get("itemspots", [])
check(len(il) == 2 and sum("moved 2.00 m" in l for l in il) == 1 and sum(l.startswith("- removed") for l in il) == 1, "moved + removed spot are told apart")
# parent chains join members further apart than 0.5 m; other families never join
cs = EI.cluster_spots([{"name": "random-util-1-a", "art": "molotov", "pos": [0, 0, 0], "quat": q, "parent": None},
                       {"name": "random-util-2-b", "art": "knife-shiv", "pos": [3, 0, 0], "quat": q, "parent": "random-util-1-a"},
                       {"name": "random-ammo-1-c", "art": "ammo-pistol", "pos": [0, 0, 0.1], "quat": q, "parent": None}])
check(len(cs) == 2 and any(c["family"] == "util" and len(c["arts"]) == 2 for c in cs), "parented members form one spot, other families stay apart")

shutil.rmtree(td, ignore_errors=True)
print("ALL OK" if not FAILS else f"{len(FAILS)} FAILED")
sys.exit(1 if FAILS else 0)
