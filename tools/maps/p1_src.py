"""Where the converted Part I level paks live, for the Scene Editor pipeline (editor_geometry.py, level_edit.py fetch / extract).

Maps with a "part1": {"levels": [...]} entry in sp_maps.json (p1-bookstore) do not load their levels from the game's psarc archives:
tools/part1/p1_levelset.py convert writes them to re/part1/x/<conv dir> (git-ignored, lives in the MAIN checkout) and the build stages them from
$T2R_P1_CONV.  The editor-side tools use the same folder:

  1. $T2R_P1_CONV                      (the build scripts export it, e.g. re/part1/x/conv-abi-mix2)
  2. else the newest re/part1/x/conv* folder that has pak68-part1.txt and a .pak for EVERY level of every part1 map
     (a half-converted folder of an unfinished run is skipped)
"""
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
SPEC = os.path.join(HERE, "sp_maps.json")
ROOTS = [os.environ.get("T2R_MAIN_ROOT", ""), os.path.dirname(os.path.dirname(HERE)).split(os.sep + ".claude" + os.sep)[0], os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))]

_spec = None


def part1_maps():
    """{map key: [level, ...]} of the maps whose levels come from Part I"""
    global _spec
    if _spec is None:
        d = json.load(open(SPEC, encoding="utf-8"))
        ms = d.get("maps", d)
        ms = ms.values() if isinstance(ms, dict) else ms
        _spec = {m["key"]: list(m["part1"]["levels"]) for m in ms if isinstance(m, dict) and m.get("part1", {}).get("levels")}
    return _spec


def levels_of(key):
    return part1_maps().get(key, [])


def is_part1_level(level):
    return any(level in lv for lv in part1_maps().values())


def conv_dir():
    e = os.environ.get("T2R_P1_CONV")
    if e:
        return e
    need = sorted({lv for v in part1_maps().values() for lv in v})
    best = None
    for r in ROOTS:
        x = os.path.join(r, "re", "part1", "x") if r else ""
        if not os.path.isdir(x):
            continue
        for n in os.listdir(x):
            d = os.path.join(x, n)
            if not (n.startswith("conv") and os.path.isfile(os.path.join(d, "pak68-part1.txt"))):
                continue
            if all(os.path.isfile(os.path.join(d, lv + ".pak")) for lv in need):
                t = os.path.getmtime(os.path.join(d, "pak68-part1.txt"))
                if best is None or t > best[0]:
                    best = (t, d)
        if best:
            return best[1]
    return None


def source(level, suffix=""):
    """path of <conv>/<level><suffix>.pak or None (not a Part I level / not converted)"""
    if not is_part1_level(level):
        return None
    d = conv_dir()
    f = os.path.join(d, level + suffix + ".pak") if d else None
    return f if f and os.path.isfile(f) else None


if __name__ == "__main__":
    print("conv dir:", conv_dir())
    for k, v in part1_maps().items():
        print(k, len(v), "levels")
