"""Offline tests for the level-set slot allocator and fresh level-set entries (tools/features/sp_maps_build.py, re/maps/technical.md 5k).
1. allocate(): every map of a build gets its own level set - the proven slot first, then the pool, then fresh entries; retired maps
   (Lodge) are refused; the 3-map vote build (into-the-city, wilds-houses, p1-bookstore + the always-built train-station) is slots only.
2. The DC patch on a scratch copy of the mod's files (main checkout re/modfs) with a pool of 2: slots + fresh entries mixed. Every
   map's level set has the stock 0x30-byte struct (+0x18 -> struct end, +0x28 = u32 -1), dc_check (the loader's checks) passes,
   sp_maps_build.verify() passes. Skips part 2 when re/modfs is missing.
Run: python tools/tests/test_sp_slots.py"""
import os
import shutil
import sys
import tempfile
import sys as _t2s, os as _t2o; _t2s.path.append(_t2o.path.normpath(_t2o.path.join(_t2o.path.dirname(_t2o.path.abspath(__file__)), ".."))); import t2rtmp  # noqa: E402,F401  (temp hygiene: tools/t2rtmp.py)

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(TOOLS, "features"))
for k in ("T2R_SP_POOL", "T2R_SP_NEW_SETS", "T2R_SP_REUSE_SLOTS", "T2R_SP_LEGACY", "T2R_P1_LEVELS"):
    os.environ.pop(k, None)
import sp_maps_build as B  # noqa: E402
import dc_check  # noqa: E402
from dcfile import DcFile, fnv  # noqa: E402

FAILS = []


def check(cond, what):
    print(("ok   " if cond else "FAIL ") + what)
    if not cond:
        FAILS.append(what)


spec = {m["key"]: m for m in B.specs()}

# ---- 1. allocator
check(len(B.SLOT_POOL) == 7 and len(set(B.SLOT_POOL)) == 7 and not set(B.SLOT_POOL) & B.NOT_SLOTS, "pool: 7 distinct leftover sets, none of the used ones")
check(B.POOL_SIZE == 7, "default pool size = 7")
check(spec["lodge"].get("retired") and "lodge" not in B.PREFERRED, "Lodge retired, holds no slot")
try:
    B.selected("lodge,train-station")
    check(False, "T2R_SP_MAPS=lodge is refused")
except AssertionError:
    check(True, "T2R_SP_MAPS=lodge is refused")
check("lodge" not in [m["key"] for m in B.selected("all")], "'all' never contains a retired map")

_nohosp = lambda ms: [m for m in ms if not m.get("replaces")]     # hospital-ellie replaces the Hospital: its own stock level set, no slot (part 2)
vote = _nohosp(B.selected("into-the-city,wilds-houses,p1-bookstore"))
check([m["key"] for m in vote] == ["train-station", "into-the-city", "wilds-houses", "p1-bookstore"], "vote build selection (+ train-station, always)")
a = B.allocate(vote)
check(len(set(a.values())) == 4 and all(v in B.SLOT_POOL for v in a.values()), f"vote build: 4 distinct proven slots {a}")
check(a["train-station"] == "tsk-pf-mission-forest-golden-gun-1" and a["wilds-houses"] == "tsk-fedra-base-fob"
      and a["p1-bookstore"] == "tsk-pf-mission-jackson-fix-gate-1", "proven maps keep the slot they were tested with")
check(all(B.slotted(m) for m in vote) and B.set_name(vote[1]) == a["into-the-city"], "set_name / slotted answer from the allocation")

five = _nohosp(B.selected("into-the-city,wilds-houses,p1-bookstore,capitol-shops"))
a5 = B.allocate(five)
check(len(set(a5.values())) == 5 and a5["capitol-shops"] == "tsk-pf-mission-seattle-collect-keycards-1", f"5 maps incl. Capitol Hill: distinct, Capitol keeps keycards {a5}")

every = [m for m in B.specs() if not m.get("retired") and not m.get("replaces")]
ae = B.allocate(every)
fresh = [k for k, v in ae.items() if v not in B.SLOT_POOL]
check(len(set(ae.values())) == len(every) and len(every) - len(fresh) == 7 and all(ae[k] == f"tsk-to1-{k}-1" for k in fresh),
      f"every non-retired spec ({len(every)}): 7 slots, {len(fresh)} fresh entries, all distinct")
a0 = B.allocate(vote, pool_size=0)
check(all(v == f"tsk-to1-{k}-1" for k, v in a0.items()), "pool 0 (T2R_SP_POOL=0): fresh entries for every map")

# ---- 2. DC patch: slots + fresh entries mixed
MAIN = B._MAIN
SRC = os.path.join(MAIN, "re", "modfs")
if not os.path.isdir(SRC):
    print("skip part 2 (no re/modfs)")
else:
    stage = tempfile.mkdtemp()
    for rel in ("bin/dc1/test-tasks.bin", "bin/dc1/modules.bin", "bin/dc1/level-sets/level-sets-test.bin", "pak68.txt"):
        os.makedirs(os.path.dirname(os.path.join(stage, rel)), exist_ok=True)
        shutil.copyfile(os.path.join(SRC, rel), os.path.join(stage, rel))
    os.makedirs(os.path.join(stage, "pak68"))
    maps = [m for m in B.specs() if not m.get("retired") and not m.get("part1")
            and os.path.exists(os.path.join(TOOLS, "features", "levels", m["pak"] + "-ingame.pak"))]
    for m in maps:
        shutil.copyfile(os.path.join(TOOLS, "features", "levels", m["pak"] + "-ingame.pak"), os.path.join(stage, "pak68", m["pak"] + "-ingame.pak"))
    al = B.allocate(maps, pool_size=2)
    nslot = sum(v in B.SLOT_POOL for v in al.values())
    lsp = os.path.join(stage, "bin", "dc1", "level-sets", "level-sets-test.bin")
    import dc_data_patches  # noqa: E402
    dc_data_patches.patch_hospital_map(stage)      # the replacing map (hospital-ellie) rewrites the Hospital's own level set
    check(any(m.get("replaces") for m in maps) and B.set_name([m for m in maps if m.get("replaces")][0]) == B.REPLACE_SETS["to1-custom-map-1"],
          "hospital-ellie replaces the Hospital: it keeps tsk-pf-mission-nor-hospital-generators-1 (no slot, no new subnode)")
    B.patch_level_sets(lsp, maps)
    newsets = [B.set_name(m) for m in maps if not B.slotted(m)]
    B.add_exports(os.path.join(stage, "bin", "dc1", "modules.bin"), newsets)
    B.patch_tasks(os.path.join(stage, "bin", "dc1", "test-tasks.bin"), maps)
    B.patch_registry(os.path.join(stage, "pak68.txt"), maps)
    B.verify(stage, maps)
    check(True, f"verify(): {len(maps)} maps, {nslot} slots + {len(newsets)} fresh entries")
    f = DcFile(open(lsp, "rb").read())
    ent = B._entries(f)
    bad = [B.set_name(m) for m in maps if not B.level_set_struct_ok(f, ent[fnv(B.set_name(m))])]
    check(not bad, f"every map's level set has the stock 0x30-byte layout {bad}")
    allbad = [hex(s) for s in ent if not B.level_set_struct_ok(f, ent[s])]
    check(not allbad, "every entry of the patched file (stock ones too) has the stock layout")
    t = ent[fnv(newsets[0])]
    check(f.q(t + 0x28) == 0xFFFFFFFF and f.q(t + 0x18) == t + 0x30, "fresh set: +0x28 = u32 -1, +0x18 -> its own end (10-12 fix)")
    # module sizes as build_dll writes them (dc_modules.set_size), then the loader checks
    import dc_modules  # noqa: E402
    mp = os.path.join(stage, "bin", "dc1", "modules.bin")
    mdata = bytearray(open(mp, "rb").read())
    for name, rel in dc_check.MODULES:
        dc_modules.set_size(mdata, name, os.path.getsize(os.path.join(stage, rel)))
    open(mp, "wb").write(bytes(mdata))
    try:
        res = dc_check.check_mod_tree(stage)
        check(res["level-sets/level-sets-test"][0] == 22 + len(newsets), f"dc_check: {res}")
    except AssertionError as e:
        check(False, f"dc_check: {e}")
    shutil.rmtree(stage, ignore_errors=True)

print("\n%d failure(s)" % len(FAILS) if FAILS else "\nall ok")
sys.exit(1 if FAILS else 0)
