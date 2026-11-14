"""Offline audit of converted Part I level paks against stock TLOU2 level paks and the engine's loader (see p1_convert.full_audit).

  python p1_audit.py [conv dir] [stock dir]     (defaults: <main>/re/part1/x/conv, <main>/re/part1/x/t2ref)

Everything here was learnt from the first in-game load attempts of the Bookstore: each crash was a field the loader
reads that the conversion did not provide.  The audit compares per item type, so the NEXT such mismatch shows up before a run."""
import collections
import glob
import os
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "models"))

# loader item-registration switch (tlou-ii.exe 0x141b993d0; type id -> case via 0x141b9b7a0), emulated from the exe
LOADER_CASE = {"TEXTURE_TABLE": 1, "BACKGROUND_SECTION": 4, "FOREGROUND_SECTION_2": 6, "COLLISION_DATA_BACKGROUND": 7,
               "COLLISION_DATA_FOREGROUND": 8, "COLLISION_DATA_CLOTH": 9, "SPAWNER_GROUP": 12, "REGION_TREE": 14, "SPLINE_TABLE": 16,
               "LIGHT_TABLE_1": 18, "MATERIAL_TABLE_1": 19, "EFFECT_TABLE": 20, "GEOMETRY_1": 25, "VIS_INFO_1": 32, "NAV_MESH_1": 33,
               "FEATURE_DB_2": 35, "TAG_INT": 38, "TAG_FLOAT": 39, "TAG_VEC4": 40, "ANIM": 41, "ANIM_GROUP": 42, "JOINT_HIERARCHY": 43,
               "COLLISION_DATA_HAVOK_BG": 44, "SOUND_BANK_TABLE": 49, "AMBSHADOWS_OCCLUDER_INFO": 55, "JSON_DOC": 57, "LEVEL_INFO_3": 59,
               "LEVEL_INFO_4": 60, "TEXTURE_DICTIONARY": 64, "LEVEL_BOUNDING_BOX_DATA": 66, "KD_TREE_2": 69, "POPULATOR_1": 71,
               "ACTOR_FLAGS": 74, "SPECULAR_CUBEMAPSET": 61, "UI_TEXTURES_METADATA": 75, "NAV_MESH_HEIGHT_MAP_TEX_1": 76}


def type_profile(paths):
    import bisect
    import ndpak
    prof = {}
    for path in paths:
        p = ndpak.Pak(path)
        d = p.d
        fixa = sorted(p.fix)
        for name, typ, pi, io in p.items:
            sz = struct.unpack_from("<I", d, io + 16)[0]
            e = prof.setdefault(typ, {"n": 0, "sizes": collections.Counter(), "slots": collections.defaultdict(collections.Counter),
                                      "named": 0})
            e["n"] += 1
            e["sizes"][sz] += 1
            if name:
                e["named"] += 1
            lo = io + 0x30
            fs = set(fixa[bisect.bisect_left(fixa, lo):bisect.bisect_left(fixa, lo + sz)])
            for a in fs:
                e["slots"][sz][a - lo] += 1
            if sz <= 4096:                        # field classes per qword: P pointer (fixup), Z zero, V other value
                cl = e.setdefault("cls", {}).setdefault(sz, collections.defaultdict(collections.Counter))
                for o in range(0, sz - 7, 8):
                    a = lo + o
                    cl[o]["P" if a in fs else ("Z" if d[a:a + 8] == bytes(8) else "V")] += 1
    return prof


def full_audit(conv_paths, ref_paths, out=print):
    import p1_convert as pc
    problems = []
    ours, ref = type_profile(conv_paths), type_profile(ref_paths)
    out("%-28s %6s %6s  %-5s %s" % ("type", "ours", "stock", "case", "findings"))
    for typ in sorted(set(ours) | set(ref)):
        o, r = ours.get(typ), ref.get(typ)
        notes = []
        if o and not r:
            notes.append("ONLY IN OURS: " + ("loader has a case -> needs conversion" if typ in LOADER_CASE else "no loader case"))
            if typ in LOADER_CASE:
                problems.append(f"{typ}: in our paks, not in the {len(ref_paths)} stock paks, loader case {LOADER_CASE[typ]}")
        elif r and not o:
            notes.append("only in stock" + (" (loader case %d)" % LOADER_CASE[typ] if typ in LOADER_CASE else ""))
        else:
            new_sizes = sorted(set(o["sizes"]) - set(r["sizes"]))
            if new_sizes and len(r["sizes"]) > 4:        # (a type with many sizes in stock is variable-sized: a new size means nothing)
                new_sizes = []
            if new_sizes:
                notes.append("sizes not in stock: %s (%d items)" % (new_sizes, sum(o["sizes"][s] for s in new_sizes)))
                problems.append(f"{typ}: payload sizes {new_sizes} never seen in stock paks")
            for sz in sorted(set(o["sizes"]) & set(r["sizes"])):
                extra = sorted(set(o["slots"][sz]) - set(r["slots"][sz]))
                if extra:
                    notes.append("size %d: pointer slots not in stock %s" % (sz, [hex(x) for x in extra][:6]))
                    problems.append(f"{typ} size {sz}: our pointer slots {[hex(x) for x in extra][:6]} do not exist in stock")
                for off, cnt in r["slots"][sz].items():
                    if cnt >= 0.9 * r["sizes"][sz] and o["slots"][sz].get(off, 0) < 0.5 * o["sizes"][sz]:
                        notes.append("size %d: slot +%#x in %d%% of stock, %d%% of ours" % (sz, off, 100 * cnt // r["sizes"][sz], 100 * o["slots"][sz].get(off, 0) // o["sizes"][sz]))
                        problems.append(f"{typ} size {sz}: pointer slot +{off:#x} mostly missing")
            for sz in sorted(set(o.get("cls", {})) & set(r.get("cls", {}))):
                no, nr = o["sizes"][sz], r["sizes"][sz]
                if no < 3 or nr < 3:
                    continue
                flagged = []
                for off, rc in r["cls"][sz].items():
                    oc = o["cls"][sz].get(off, collections.Counter())
                    for k, what in (("P", "pointer"), ("Z", "zero")):
                        if rc[k] >= 0.95 * nr and oc[k] < 0.5 * no:
                            flagged.append("+%#x stock %s %d%% ours %d%%" % (off, what, 100 * rc[k] // nr, 100 * oc[k] // no))
                if flagged:
                    notes.append("size %d field classes: %s" % (sz, "; ".join(flagged[:4]) + (" ..." if len(flagged) > 4 else "")))
                    problems.append(f"{typ} size {sz}: {len(flagged)} fields differ in class from stock (e.g. {flagged[0]})")
            if r["named"] > 0.5 * r["n"] and o["named"] < 0.5 * o["n"]:
                notes.append("names: stock %d%% named, ours %d%%" % (100 * r["named"] // r["n"], 100 * o["named"] // o["n"]))
                problems.append(f"{typ}: stock items carry a name string, ours are unnamed")
        out("%-28s %6d %6d  %-5s %s" % (typ, o["n"] if o else 0, r["n"] if r else 0, LOADER_CASE.get(typ, "-"), "; ".join(notes) or "ok"))
    for path in conv_paths:
        bn = os.path.basename(path)
        for fn in (pc.loader_check, pc.vram_check, pc.vram_sort_check, pc.trailer_check, pc.lights_check, pc.pointer_pattern_check, pc.geometry_extent_check):
            try:
                bad = fn(path)
            except Exception as ex:   # noqa: BLE001
                bad = [f"{fn.__name__} raised {ex!r}"]
            for b in bad:
                problems.append(f"{bn}: {fn.__name__}: {b}")
        if not path.endswith(("-phys.pak", "-ingame.pak")):
            import p1_abi                 # Part I shaders on TLOU2's engine-global ABI (geometry-upgrade.md s10)
            for b in p1_abi.check(path)[0]:
                problems.append(f"{bn}: p1_abi.check: {b}")
    out("")
    out("%d problems" % len(problems))
    for pr in problems:
        out("  " + pr)
    return problems


def main(argv):
    root = os.path.normpath(os.path.join(HERE, "..", ".."))
    root = root.split(os.sep + ".claude" + os.sep)[0]
    conv_dir = argv[0] if argv else os.path.join(root, "re", "part1", "x", "conv")
    ref_dir = argv[1] if len(argv) > 1 else os.path.join(root, "re", "part1", "x", "t2ref")
    conv = [f for f in sorted(glob.glob(os.path.join(conv_dir, "hun-checkpoint-bookstore*.pak"))) if "script" not in f]
    ref = [f for f in sorted(glob.glob(os.path.join(ref_dir, "*.pak"))) if not f.endswith(("-dict.pak", "_tmp.pak"))]
    print(len(conv), "converted paks,", len(ref), "stock paks")
    return 1 if full_audit(conv, ref) else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
