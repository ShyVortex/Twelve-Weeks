"""geo_count.py: how many geometries a level logs in - the engine's global geometry table has 5000 slots.

ResourceTable::LoginGeometry (exe+29118b0 in 1.6.0, resource-table-login-logout.cpp) takes the first free bit of a 5000-bit map for
every ArtItemGeo of a pak that logs in; with none free it writes far out of range (build #19: c0000005 at exe+29119f0 while
the menu world loaded beside the MP level). An ArtItemGeo = one FOREGROUND_SECTION_2 item of a pak ("geo.<part>", "geo.<part>.lod1"
...): a kit pak has 24 (6 parts x 4 LODs) whether its parts are drawn or collapsed, so every copy of a kit costs 24 slots.

  count(pak bytes)                -> number of FOREGROUND_SECTION_2 items
  level_geos(stage, levels)       -> {level: {"actors": {name: n}, "packages": {name: n}, "missing": [...]}}
  python geo_count.py <stage dir> <level> [<level> ...]     per level: the total, the families, the heaviest paks
Paks come from the stage (the mod's own / replaced ones) and else from the game's archives (re/game-files.tsv); the counts of game
paks are cached in tools/local/build-cache/geo-count.json by (archive, path, size)."""
import collections
import json
import os
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.dirname(HERE)
ROOT = os.path.dirname(TOOLS)
sys.path.insert(0, TOOLS)
sys.path.insert(0, os.path.join(TOOLS, "models"))
sys.path.insert(0, os.path.join(TOOLS, "models", "portrait_cast"))
GEO_SLOTS = 5000
CACHE = os.path.join(TOOLS, "local", "build-cache", "geo-count.json")


def count(d):
    """FOREGROUND_SECTION_2 items of a pak (its page item tables; nothing else is read)"""
    u32 = lambda o: struct.unpack_from("<I", d, o)[0]
    n, pt = u32(16), u32(20)
    k = 0
    for i in range(n):
        start = u32(pt + 12 * i)
        cnt = struct.unpack_from("<H", d, start + 18)[0]
        for j in range(cnt):
            io = start + u32(start + 20 + 16 * j + 8)
            t = start + struct.unpack_from("<Q", d, io + 8)[0]
            if d[t:t + 21] == b"FOREGROUND_SECTION_2\0":
                k += 1
    return k


_tsv = None
_arc = {}
_cache = None


def _index():
    global _tsv
    if _tsv is None:
        _tsv = {}
        f = next(p for p in (os.path.join(ROOT, "re", "game-files.tsv"), os.path.join(os.environ.get("T2R_MAIN_ROOT", ROOT), "re", "game-files.tsv")) if os.path.exists(p))
        for l in open(f, encoding="utf-8", errors="replace"):
            a = l.rstrip("\n").split("\t")
            if len(a) >= 3:
                _tsv.setdefault(a[1], (a[0], int(a[2])))
    return _tsv


def _game(path):
    """(count, size) of a game file by its archive path, None when the game has none"""
    global _cache
    e = _index().get(path)
    if e is None:
        return None
    arc, size = e
    if _cache is None:
        try:
            _cache = json.load(open(CACHE))
        except (OSError, ValueError):
            _cache = {}
    key = "%s|%s|%d" % (arc, path, size)
    if key not in _cache:
        import dsar_list
        import texdict
        if arc not in _arc:
            _arc[arc] = dsar_list.open_files(os.path.join(texdict.GAME, "build", "pc", "main", arc))
        d, ent, bs, bsz = _arc[arc]
        _cache[key] = count(dsar_list.extract(d, ent, bs, bsz, path))
    return _cache[key]


def _save():
    if _cache is not None:
        os.makedirs(os.path.dirname(CACHE), exist_ok=True)
        tmp = CACHE + ".tmp%d" % os.getpid()
        json.dump(_cache, open(tmp, "w"))
        os.replace(tmp, CACHE)


def pak_geos(stage, kind, name):
    """kind 'actor97' / 'pak68'; the stage's file wins (the mod's own and replaced paks)"""
    f = os.path.join(stage, kind, name + ".pak")
    if os.path.exists(f):
        return count(open(f, "rb").read())
    return _game("%s/%s.pak" % (kind, name))


REG = None                # another pak68.txt than the stage's (a dry run of a level def that is not staged yet)


def _reg(stage):
    return open(REG or os.path.join(stage, "pak68.txt"), encoding="latin1").read().split("\n")


def level_geos(stage, levels):
    reg = _reg(stage)
    out, cur = {}, None
    for l in reg:
        if l.startswith("level-name "):
            nm = l[11:].strip()
            cur = out.setdefault(nm, {"actors": {}, "packages": {}, "missing": []}) if nm in levels else None
        elif cur is not None:
            kw, _, v = l.partition(" ")
            v = v.strip()
            if kw in ("actor", "cutscene", "package"):
                kind, grp = ("actor97", "actors") if kw != "package" else ("pak68", "packages")
                n = pak_geos(stage, kind, v)
                if n is None and kw == "package":
                    n = pak_geos(stage, "actor97", v)
                if n is None:
                    cur["missing"].append(kw + " " + v)
                else:
                    cur[grp][v] = n
    _save()
    return out


def resident(stage, levels):
    """geometries of a set of levels resident together: every pak once"""
    g = level_geos(stage, levels)
    paks = {}
    for lv in g.values():
        for grp in ("actors", "packages"):
            for k, n in lv[grp].items():
                paks[(grp, k)] = n
    return sum(paks.values()), g


GEO_LIMIT = 4600          # the build stops above this for the worst resident set (the engine's table: GEO_SLOTS)
MP_LEVEL = "starlight-mp-test"


def map_levels():
    """{map key: [levels]} of every map the build can ship (tools/maps/sp_maps.json, tools/part1/data/p1_maps/*.json)"""
    out = {}
    for m in json.load(open(os.path.join(TOOLS, "maps", "sp_maps.json")))["maps"]:
        lv = [x for x in (m.get("levels") or []) if isinstance(x, str)] + [m[k] for k in ("level", "pak") if isinstance(m.get(k), str)]
        out[m["key"]] = list(dict.fromkeys(lv))
    pd = os.path.join(TOOLS, "part1", "data", "p1_maps")
    for fn in sorted(os.listdir(pd)) if os.path.isdir(pd) else ():
        if fn.endswith(".json"):
            j = json.load(open(os.path.join(pd, fn)))
            lv = [x for x in (j.get("play_levels") or []) if isinstance(x, str)] + ([j["primary_level"]] if isinstance(j.get("primary_level"), str) else [])
            out[j.get("key", fn[:-5])] = list(dict.fromkeys(out.get(j.get("key", fn[:-5]), []) + lv))
    return out


def menu_levels():
    """{scene: [levels]} of the menu worlds (menu_scenes.MENU_SCENES: the scene's stock levels + its own level)"""
    sys.path.insert(0, HERE)
    import menu_scenes
    return {sc["name"]: list(sc["levels"]) + [sc["pak"]] for sc in menu_scenes.MENU_SCENES}


def worst(stage, maps=None):
    """the worst set of geometries resident at once: the MP level + the largest of
       - a map's levels + the largest menu scene (a match load: the menu world is still logged in while the map's levels log in;
 Supermarket at 4506 map-only crashed at exe+29119f0 in ~1 of 10 loads, 4506 + its menu = 4720-4769, while the
         largest map that never crashed sits at 4539 with the menu - the limit 4600 sits between them),
       - TWICE a menu scene (the menu world reloads when multiplayer is entered: the old scene is still logged in while the
         new one logs in - build #19 died there).
    -> dict(mp=, worst=, what=, sets={name: geometries added to the MP level})"""
    names = set(l[11:].strip() for l in _reg(stage) if l.startswith("level-name "))
    mp, _g = resident(stage, [MP_LEVEL])
    sets = {}
    menus = {k: [x for x in lv if x in names] for k, lv in menu_levels().items()}
    menus = {k: lv for k, lv in menus.items() if lv}
    ml = map_levels()
    for k in (maps if maps is not None else ml):
        lv = [x for x in ml.get(k, []) if x in names]
        if lv:
            add, menu = max(((resident(stage, [MP_LEVEL] + lv + mlv)[0] - mp, mk) for mk, mlv in menus.items()), default=(resident(stage, [MP_LEVEL] + lv)[0] - mp, "-"))
            sets["map " + k + " + menu " + menu] = add
    for k, lv in menus.items():
        sets["menu " + k + " x2"] = 2 * (resident(stage, [MP_LEVEL] + lv)[0] - mp)
    what = max(sets, key=sets.get) if sets else "-"
    return dict(mp=mp, worst=mp + (sets[what] if sets else 0), what=what, sets=sets)


def gate(stage, maps=None):
    """Stops the build when the worst resident set is over GEO_LIMIT; prints the counts (beside check_level_caps' lines).
    T2R_GEO_OFFPOOL = map keys the server does not offer (left out of its T2R_MAP_POOL): built, but never loaded, so not gated."""
    off = {k.strip() for k in os.environ.get("T2R_GEO_OFFPOOL", "").split(",") if k.strip()}
    if off:
        maps = [k for k in (maps if maps is not None else map_levels()) if k not in off]
        print("level caps: geometries: not gated (out of the server's map pool): %s" % ", ".join(sorted(off)))
    w = worst(stage, maps)
    top = sorted(w["sets"].items(), key=lambda x: -x[1])[:4]
    print("level caps: geometries: %s %d; worst resident set %d of %d (%s; limit %d, %d free under the engine's table) - adds: %s" % (
        MP_LEVEL, w["mp"], w["worst"], GEO_SLOTS, w["what"], GEO_LIMIT, GEO_SLOTS - w["worst"], ", ".join("%s +%d" % kv for kv in top)))
    if w["worst"] > GEO_LIMIT:
        raise SystemExit("level caps: %d geometries resident at once (%s + %s) - over the build's limit %d; the engine's table holds %d "
                         "(ResourceTable::LoginGeometry writes out of range beyond it: build #19). Every FOREGROUND_SECTION_2 item of a "
                         "listed pak counts, drawn or not." % (w["worst"], MP_LEVEL, w["what"], GEO_LIMIT, GEO_SLOTS))
    return w


FAMILIES = (("hand tint (t2r-wh-)", "t2r-wh-"), ("bare-head copies (t2r-fh-)", "t2r-fh-"), ("hats (t2r-hw-)", "t2r-hw-"), ("gas masks (t2r-gm-/gu-)", ("t2r-gm-", "t2r-gu-")),
            ("KELLIE (t2r-kl-)", "t2r-kl-"), ("rebuilt Seraphite garments (scar-t2r-)", "scar-t2r-"), ("armour / pushed copies (-arm1-/-farm01-)", ("-arm1-", "-farm01-")),
            ("winter (wlf-winter / scar-winter)", ("wlf-winter", "scar-winter", "-winter-")), ("WLF kits (militia-*-kit)", "militia-"), ("Seraphite (scar-)", "scar-"))


def family(name):
    for lab, pre in FAMILIES:
        pre = pre if isinstance(pre, tuple) else (pre,)
        if any((name.startswith(p) if not p.startswith("-") else p in name) for p in pre):
            return lab
    return "other"


def main():
    if "--reg" in sys.argv:
        global REG
        REG = sys.argv.pop(sys.argv.index("--reg") + 1)
        sys.argv.remove("--reg")
    if len(sys.argv) == 3 and sys.argv[2] == "--gate":
        gate(sys.argv[1], [k for k in os.environ.get("T2R_SP_MAPS", "").split(",") if k] or None)
        return
    stage, levels = sys.argv[1], sys.argv[2:]
    tot, g = resident(stage, levels)
    for lv in levels:
        if lv not in g:
            print("%s: no such level" % lv)
            continue
        a, p = g[lv]["actors"], g[lv]["packages"]
        print("%s: %d geometries (%d actors %d, %d packages %d)%s" % (lv, sum(a.values()) + sum(p.values()), len(a), sum(a.values()), len(p), sum(p.values()),
                                                                  "; NOT FOUND: %s" % g[lv]["missing"][:6] if g[lv]["missing"] else ""))
        fam = collections.Counter()
        cnt = collections.Counter()
        for k, n in a.items():
            fam[family(k)] += n
            cnt[family(k)] += 1
        for lab, n in fam.most_common():
            print("    %-44s %5d geometries in %3d paks" % (lab, n, cnt[lab]))
        print("    heaviest:", ", ".join("%s %d" % (k, n) for k, n in sorted(list(a.items()) + list(p.items()), key=lambda x: -x[1])[:8]))
    print("TOGETHER: %d of %d slots (%d free)" % (tot, GEO_SLOTS, GEO_SLOTS - tot))


if __name__ == "__main__":
    main()
