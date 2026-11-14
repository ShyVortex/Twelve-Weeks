"""Part I actor paks (the props the Bookstore's SPAWNER_GROUPs place) -> TLOU2 actor paks.

  python p1_actors.py list                          # the actors to convert (spawner-arts json 'diff' + Part I-only arts of the Part I -ingame spawners)
  python p1_actors.py convert <Part I dir> [name...] [--tex-drop=N]   # -> <conv>/actors/<name>.pak (+ sizes); default = the whole list

Same converter as the level paks (p1_convert.convert: Part I page layout -> TLOU2, item headers, submesh records 176 -> 192, VRAM descriptors with the
textures embedded from the Part I dictionaries, top N mips dropped) + the shader ABI retarget (p1_abi.fix_pak) + the loader mirrors
(geometry_extent_check / loader_check / vram_check). The converted pak is a normal actor97 pak: sp_maps_build stages it as actor97/<name>.pak
and the spawner / level block names it. An actor that TLOU2 also has under the same name (spawner-arts 'diff': same name, other art) REPLACES the
stock actor in the mod, for every map: the name is the art key of the spawner. Corpse props (6 MB each) are held back (SKIP).
Part I content stays under re/part1 (git-ignored)."""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(TOOLS, "models"))
ROOT = os.path.dirname(TOOLS)
MAIN = os.environ.get("T2R_MAIN_ROOT", ROOT.split(os.sep + ".claude" + os.sep)[0])
CONV = os.environ.get("T2R_P1_CONV", os.path.join(MAIN, "re", "part1", "x", "conv"))
ARTS = os.path.join(TOOLS, "maps", "data", "p1-bookstore-spawn-arts.json")
SKIP_PREFIX = ("corpse-",)          # 4.8 - 6 MB each: ask first
NO_ART = {"binding-duct", "cover-ap-372", "pistol-ammo-box", "invisible-cube", "light-skel"}


def actors_dir():
    return os.path.join(CONV, "actors")


def wanted():
    """[actor, ...] converted from Part I: the spawner-arts json's `convert` list (written by `collect`)"""
    d = json.load(open(ARTS, encoding="utf-8"))
    return [a for a in d.get("convert", []) if not a.startswith(SKIP_PREFIX)]


def find_archive(game, actor):
    tsv = os.path.join(MAIN, "re", "part1", "game-files.tsv")
    want = f"actor97/{actor}.pak"
    for line in open(tsv, encoding="utf-8"):
        p = line.rstrip("\n").split("\t")
        if len(p) == 3 and p[1] == want:
            return p[0]
    raise SystemExit(f"{actor}: not in {tsv}")


def renames():
    """{old art: p1-renamed art} for the arts whose TLOU2 actor of the same name carries other art ('diff' in the spawner-arts json): the converted pak must not
    shadow the stock actor in the other maps. Same length (rename_pak), 'p1' as the first three letters (p1-); the grafted spawners, the level
    block and the staged actor97 file use the new name"""
    d = json.load(open(ARTS, encoding="utf-8"))
    return dict(d.get("rename", {}))


def translate_collision(out, raw, actor):
    """The converted pak's COLLISION_DATA_FOREGROUND tag is Part I's Havok 2020.1 image; TLOU2 reads 2017.1 only. Translate it
    (actor_collision.py, on a stock TLOU2 actor with the same classes as template) and move the item to its own page (actor_pak.py).
    Actors whose collision classes are not translated yet (hknpSphereShape / hknpCapsuleShape / compound / mesh shapes) raise Unsupported."""
    import actcol_p1
    import actor_collision
    import actor_pak
    import actor_templates
    tags = actcol_p1.p1_fg_tags(raw)
    if not tags:
        return out
    tmpl = actor_templates.template_for(actor)
    if tmpl is None:
        raise actor_collision.Unsupported(f"{actor}: no TLOU2 template actor for its collision classes (actor-col-templates.json)")
    res = actor_pak.replace_fg(out, [actor_collision.translate(t, tmpl) for t in tags])
    assert b"SDKV20200100" not in res and b"SDKV20170100" in res, f"{actor}: collision tag is not Havok 2017.1"
    return res


def convert_one(game, actor, tex, tex_drop):
    import p1_abi
    import p1_archive
    import p1_convert
    arc = p1_archive.Psarc(os.path.join(game, "build", "pc", "main", find_archive(game, actor)))
    raw = arc.get(f"actor97/{actor}.pak")
    rep = {}
    out = p1_convert.convert(raw, rep, tex, tex_drop, actor)
    arep = {}
    out = p1_abi.fix_pak(out, report=arep)
    new = renames().get(actor)
    if new:
        import rename_pak
        out, n = rename_pak.rename(out, actor, new, items=True)
        assert n >= 2, f"{actor} -> {new}: {n} names renamed"
    out = translate_collision(out, raw, actor)
    dst = os.path.join(actors_dir(), (new or actor) + ".pak")
    os.makedirs(actors_dir(), exist_ok=True)
    open(dst, "wb").write(out)
    bad = p1_convert.geometry_extent_check(dst) + p1_convert.loader_check(dst) + p1_convert.vram_check(dst)
    assert not bad, f"{actor}.pak: {bad[:3]}"
    return len(raw), len(out), rep, new


def convert(game, names=None, tex_drop=2):
    import p1_textures
    tex = p1_textures.P1Textures(game)
    names = names or wanted()
    tot = 0
    for a in names:
        try:
            src, size, rep, new = convert_one(game, a, tex, tex_drop)
        except (AssertionError, Exception) as e:    # noqa: BLE001 - report every actor, keep going
            print(f"  {a}: FAILED {e!r}"[:300])
            continue
        tot += size
        print(f"  {a}{' -> ' + new if new else ''}.pak {src} -> {size} bytes  textures {rep.get('textures embedded', 0)} (+{rep.get('textures kept as stubs', 0)} stubs)", flush=True)
    print(f"{len(names)} actors, {tot / 1e6:.1f} MB converted -> {actors_dir()}")


def main(argv):
    if len(argv) >= 2 and argv[1] == "list":
        print("\n".join(wanted()))
    elif len(argv) >= 3 and argv[1] == "convert":
        drop = next((int(a.split("=")[1]) for a in argv if a.startswith("--tex-drop=")), 2)
        names = [a for a in argv[3:] if not a.startswith("--")]
        convert(argv[2], names, drop)
    else:
        print(__doc__)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
