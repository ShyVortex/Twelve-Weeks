"""Part I levels as an SP-style PvP map: convert the level paks, write their registry blocks, seed placeholder spawns.

  python p1_levelset.py convert <game dir> <map key> [--tex-drop=N]   # (env T2R_P1_TEXDROP) real textures embedded in the
                                                          # paks, the top N mips dropped; without it: the 64x64 stubs
                                                          # extract + convert the spec's Part I levels (base, -phys,
                                                          # -ingame) to TLOU2 paks under <main>/re/part1/x/conv/ and
                                                          # write conv/pak68-part1.txt (level blocks with Part I's bounds)
                                                          # -phys: the Havok collision is translated to TLOU2 tagfiles
                                                          # (havok_convert.py, checked offline) -> conv/phys-status.json;
                                                          # sp_maps_build stages a level's -phys when it says havok2017 /
                                                          # empty (T2R_P1_PHYS=0 never, =1 always; T2R_P1_PHYS_TRANSLATE=0
                                                          # = old container-only conversion)
                                                          # base paks: the Part I shaders are retargeted to TLOU2's
                                                          # engine-global ABI (p1_abi.py; T2R_P1_ABI=0 = off)
                                                          # --only=<level>[,...]: just these levels (the others' paks and
                                                          # blocks of an earlier convert stay)
                                                          # spec "rs-level": Part I's render settings for the map
                                                          # (p1_rsenv.py: conv/<rs-level>-ingame.pak regions + conv/
                                                          # <rs-level>.t1x.bin symbols + block; T2R_P1_RS=0 = off), s11
  python p1_levelset.py phys <game dir> <map key>         # only the -phys paks (collision translation) + phys-status.json
  python p1_levelset.py floor <map key> [--y=Y --x0= --z0= --x1= --z1=] | --clear   # interim ground: flat invis-collision panels
  python p1_levelset.py seed <map key>                    # placeholder spawns from the levels' bounds ->
                                                          # tools/maps/data/<key>-spawns.json + the spawner pak
                                                          # tools/features/levels/to1-pvp-<key>-ingame.pak (pwsh + SceneEditor)
The map spec (tools/maps/sp_maps.json, "part1": {"levels": [...]}) is built into the mod by sp_maps_build.py
(T2R_SP_MAPS=p1-bookstore): converted paks staged into the mod's pak68 dir + registered.  Part I content only ever lives
under re/part1/x (git-ignored); the spawner pak and the spawns json are our own data (Part I bounds are only used to put
placeholder points inside the level - tune with F8 marks in game as for every map).
"""
import json
import math
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import p1_archive  # noqa: E402
import p1_convert  # noqa: E402

ROOT = os.path.dirname(TOOLS)
MAIN = os.environ.get("T2R_MAIN_ROOT", ROOT.split(os.sep + ".claude" + os.sep)[0])
CONV = os.environ.get("T2R_P1_CONV", os.path.join(MAIN, "re", "part1", "x", "conv"))
SPEC = os.path.join(TOOLS, "maps", "sp_maps.json")
DATA = os.path.join(TOOLS, "maps", "data")
LEVELS = os.path.join(TOOLS, "features", "levels")
MAKE_PAK = os.path.join(TOOLS, "maps", "make_map_pak.ps1")
TEMPLATE = os.path.join(LEVELS, "to1-pvp-hospital-ingame.pak")


def spec(key):
    return next(m for m in json.load(open(SPEC, encoding="utf-8"))["maps"] if m["key"] == key)


def registry_blocks(game):
    """{level: {'upperLeft': str, 'lowerRight': str}} from Part I's pak68.txt"""
    txt = open(os.path.join(game, "build", "pc", "main", "pak68.txt"), encoding="latin1").read().split("\n")
    out, cur = {}, None
    for ln in txt:
        if ln.startswith("level-name "):
            cur = out.setdefault(ln[11:].strip(), {})
        elif cur is not None and ln.startswith(("upperLeft ", "lowerRight ")):
            k, v = ln.split(" ", 1)
            cur[k] = v.strip()
    return out


def registry_actors(game):
    """{level: [actor, ...]} from Part I's pak68.txt: the `actor <name>` lines of each level block, in order. A skinned /
    interactive-BG instance or a spawner only draws when its actor pak is listed in the level's registry block; our converted blocks carried
    only the package lines (sp_maps_build.p1_blocks adds the ones TLOU2 also has, from conv/actors-part1.json)"""
    txt = open(os.path.join(game, "build", "pc", "main", "pak68.txt"), encoding="latin1").read().splitlines()
    out, cur = {}, None
    for ln in txt:
        if ln.startswith("level-name "):
            cur = out.setdefault(ln[11:].strip(), [])
        elif cur is not None and ln.startswith("actor "):
            cur.append(ln[6:].strip())
    return out


def write_actors(game, key):
    """conv/actors-part1.json: Part I's block actor lists of the map's levels (python p1_levelset.py actors <game dir> <map key>;
    `convert` writes it too)"""
    ra = registry_actors(game)
    d = {lv: ra.get(lv, []) for lv in spec(key)["part1"]["levels"]}
    os.makedirs(CONV, exist_ok=True)
    json.dump(d, open(os.path.join(CONV, "actors-part1.json"), "w"), indent=1, sort_keys=True)
    print("block actor lists ->", os.path.join(CONV, "actors-part1.json"), {k: len(v) for k, v in d.items()})


def find_archive(game, level):
    """archive holding pak68/<level>.pak (from re/part1/game-files.tsv)"""
    tsv = os.path.join(MAIN, "re", "part1", "game-files.tsv")
    want = f"pak68/{level}.pak"
    for line in open(tsv, encoding="utf-8"):
        p = line.rstrip("\n").split("\t")
        if len(p) == 3 and p[1] == want:
            return p[0]
    raise SystemExit(f"{level}: not in {tsv} (python p1_archive.py list <game>/build/pc/main/*.psarc > it)")


PHYS_STATUS = os.path.join(CONV, "phys-status.json")


def phys_status():
    """{level: 'havok2017' | 'empty' | 'container' | 'failed: ...'} of the last convert (conv/phys-status.json)"""
    try:
        return json.load(open(PHYS_STATUS))
    except (OSError, ValueError):
        return {}


def phys(raw, out_path):
    """Part I -phys pak -> TLOU2 -phys pak with the collision translated to Havok 2017.1 tagfiles (havok_convert.py) and
    checked offline (same triangles / tags, valid trees).  'havok2017' when written, 'empty' for a pak without collision
    (the container conversion is used), else the reason (the caller falls back to the container conversion, not staged)."""
    import havok_convert
    try:
        rep = {}
        out = havok_convert.convert(raw, report=rep)
        if out is None:
            return "empty"
        if not havok_convert.check(raw, out, verbose=False):
            return "failed: offline check"
        open(out_path, "wb").write(out)
        n = sum(len(i["pieces"]) for i in rep["items"])
        print(f"  {os.path.basename(out_path)} {len(out) / 1e6:.1f} MB  collision translated: {len(rep['items'])} Part I shapes -> "
              f"{n} TLOU2 items, {sum(i['keys'] for i in rep['items'])} triangles (check OK)")
        return "havok2017"
    except Exception as e:                       # noqa: BLE001 - keep converting the other levels
        print(f"  {os.path.basename(out_path)}: collision translation failed: {e!r}")
        return "failed: %r" % (e,)


def convert_phys(game, key):
    """only the -phys paks of the map's levels (translated collision) + conv/phys-status.json; the base / -ingame
    paks of an earlier convert stay as they are"""
    m = spec(key)
    os.makedirs(CONV, exist_ok=True)
    status = phys_status()
    for level in m["part1"]["levels"]:
        arc = p1_archive.Psarc(os.path.join(game, "build", "pc", "main", find_archive(game, level)))
        name = f"pak68/{level}-phys.pak"
        if name not in arc.ent and "/" + name not in arc.ent:
            print(f"  {level}-phys: not in the archive")
            continue
        raw = arc.get(name)
        out = os.path.join(CONV, f"{level}-phys.pak")
        status[level] = phys(raw, out)
        if status[level] != "havok2017":
            open(out, "wb").write(p1_convert.convert(raw, {}))
            print(f"  {level}-phys.pak: {status[level]} (container conversion written, staged only for 'empty')")
    json.dump(status, open(PHYS_STATUS, "w"), indent=1, sort_keys=True)
    print("collision status ->", PHYS_STATUS, status)


def convert(game, key, tex_drop=None, only=None):
    """only = [level, ...]: convert just these (the other levels' paks and registry blocks of an earlier convert stay)"""
    m = spec(key)
    tex = None
    if tex_drop is not None:
        import p1_textures
        tex = p1_textures.P1Textures(game)
    lv = m["part1"]["levels"]
    os.makedirs(CONV, exist_ok=True)
    reg = registry_blocks(game)
    blocks = []
    status = phys_status()
    for level in lv:
        if only is not None and level not in only:
            blocks.append((level, None))         # keep its block of the earlier convert
            continue
        arc = p1_archive.Psarc(os.path.join(game, "build", "pc", "main", find_archive(game, level)))
        for suf in ("", "-phys", "-ingame"):
            name = f"pak68/{level}{suf}.pak"
            if name not in arc.ent and "/" + name not in arc.ent:
                print(f"  {level}{suf}: not in the archive")
                continue
            rep = {}
            raw = arc.get(name)
            if suf == "-phys" and os.environ.get("T2R_P1_PHYS_TRANSLATE", "1") != "0":
                st = phys(raw, os.path.join(CONV, f"{level}{suf}.pak"))
                status[level] = st
                if st == "havok2017":
                    continue                 # "empty" (no collision item): the container conversion below is all there is
            out = p1_convert.convert(raw, rep, tex, tex_drop or 0, level + suf)
            if os.environ.get("T2R_P1_ABI", "1") != "0":
                # Part I material shaders -> TLOU2 engine-global ABI (per-frame / view cbuffers, global SRV table):
                # p1_abi.py, re/part1/geometry-upgrade.md s10.  T2R_P1_ABI=0 = Part I shaders as converted.
                import p1_abi
                arep = {}
                out = p1_abi.fix_pak(out, report=arep)
                if arep:
                    print(f"  {level}{suf}: shader ABI retarget {dict(arep)}")
            open(os.path.join(CONV, f"{level}{suf}.pak"), "wb").write(out)
            # maze / barricade shipped with the GEOMETRY_1 submesh array cut by a page end (crash exe+173c2d0 on load)
            bad = p1_convert.geometry_extent_check(os.path.join(CONV, f"{level}{suf}.pak")) + p1_convert.loader_check(os.path.join(CONV, f"{level}{suf}.pak"))
            assert not bad, f"{level}{suf}.pak: {bad}"
            print(f"  {level}{suf}.pak {len(out) / 1e6:.1f} MB  items {rep['items listed']}/{rep['items found']}"
                  f"  unknown types {rep['unknown types'] or '-'}"
                  + (f"  textures {rep['textures embedded']} (+{rep['textures kept as stubs']} stubs)" if tex else ""))
        b = reg.get(level, {})
        blocks.append((level, b))
    json.dump(status, open(PHYS_STATUS, "w"), indent=1, sort_keys=True)
    print("collision status ->", PHYS_STATUS, status)
    old = _blocks_by_level()
    lines = []
    for level, b in blocks:
        if b is None:
            assert level in old, f"{level}: no block from an earlier convert (convert it: drop --only)"
            lines += old[level]
            continue
        # sp_maps_build keeps -phys when its collision was translated (phys-status.json), see sp_maps_build.p1_phys
        lines += [f"level-name {level}", f"level-id {level}", f"package {level}", f"package {level}-phys"]
        lines += [f"package {level}-ingame"] if os.environ.get("T2R_P1_INGAME") == "1" else []
        lines += [f"{k} {b[k]}" for k in ("upperLeft", "lowerRight") if k in b]
    rs = m["part1"].get("rs-level")
    if rs and os.environ.get("T2R_P1_RS", "1") != "0":
        lines += rs_env(game, m, reg)
    write_actors(game, key)
    with open(os.path.join(CONV, "pak68-part1.txt"), "w", encoding="latin1", newline="\n") as f:
        f.write("".join(ln + "\n" for ln in lines))
    print("registry blocks ->", os.path.join(CONV, "pak68-part1.txt"))


def _blocks_by_level():
    """{level: [lines]} of the current conv/pak68-part1.txt"""
    out, cur = {}, None
    try:
        txt = open(os.path.join(CONV, "pak68-part1.txt"), encoding="latin1").read().split("\n")
    except OSError:
        return out
    for ln in txt:
        if ln.startswith("level-name "):
            cur = out.setdefault(ln[11:].strip(), [])
        if cur is not None and ln:
            cur.append(ln)
    return out


RS_T1X = os.path.join(MAIN, "re", "gamebin", "dc1", "render-settings", "t1x.bin")      # TLOU2's own module (extracted game files)


def rs_env(game, m, reg):
    """Part I's render settings for the map (p1_rsenv.py, re/part1/geometry-upgrade.md s11): conv/<rs-level>-ingame.pak
    (the Part I render-settings regions over the map's levels) + conv/<rs-level>.t1x.bin (TLOU2's render-settings/t1x module
    + the Part I symbols they name; sp_maps_build stages it as bin/dc1/render-settings/t1x.bin).  -> the level's registry
    block lines"""
    import p1_rsenv
    rs = m["part1"]["rs-level"]
    const = m["part1"].get("rs-const", "hun-const") + "-ingame"
    arc = p1_archive.Psarc(os.path.join(game, "build", "pc", "main", find_archive(game, const)))
    const_raw = arc.get(f"pak68/{const}.pak")
    binarc = p1_archive.Psarc(os.path.join(game, "build", "pc", "main", "bin.psarc"))
    mods = {n.split("/")[-1]: binarc.get(n) for n in sorted(binarc.ent)
            if n.lstrip("/").startswith("dc1/render-settings/") and n.endswith(".bin")}
    pts = []
    for level in m["part1"]["levels"]:
        if level.startswith("sky-"):
            continue                              # (a sky level's bounds are the whole world)
        for k in ("upperLeft", "lowerRight"):
            if k in reg.get(level, {}):
                pts.append([float(x) for x in reg[level][k].split()])
    box = (min(p[0] for p in pts), min(p[2] for p in pts), max(p[0] for p in pts), max(p[2] for p in pts))
    if m["part1"].get("rs-box"):
        # spec "rs-box" [x0, z0, x1, z1]: the render-settings area stays the store's own (its 23 regions) when the map grows by
        # big street / LOD levels whose bounds would pull in the underpass / approach regions (story-gated in Part I, off at the store)
        box = tuple(m["part1"]["rs-box"])
    t1x = open(RS_T1X, "rb").read()
    rep = {}
    pak, t1x_new, syms = p1_rsenv.build_env(const_raw, mods, t1x, os.path.dirname(RS_T1X), box, rep)
    (src, _grid), = p1_rsenv.read_p1_regions(const_raw)
    bad = p1_rsenv.check(pak, t1x_new, t1x, src)
    if bad:
        raise SystemExit(f"{rs}: render-settings environment check failed: {bad[:4]}")
    open(os.path.join(CONV, f"{rs}-ingame.pak"), "wb").write(pak)
    open(os.path.join(CONV, f"{rs}.t1x.bin"), "wb").write(t1x_new)
    for k in ("loader_check", "vram_check"):
        b = getattr(p1_convert, k)(os.path.join(CONV, f"{rs}-ingame.pak"))
        if b:
            raise SystemExit(f"{rs}-ingame.pak: {k}: {b[:3]}")
    dropped = sum(len(v[2]) for v in rep["symbols"].values())
    print(f"  {rs}-ingame.pak {len(pak)} bytes: {len(rep['regions'])} Part I render-settings regions over x {box[0]:.0f}..{box[2]:.0f} "
          f"z {box[1]:.0f}..{box[3]:.0f} (from {const}; skipped {len(rep['skipped'])}); {rs}.t1x.bin {len(t1x)} -> {len(t1x_new)} "
          f"bytes: {len(syms)} symbols, {sum(v[1] for v in rep['symbols'].values())} settings ({dropped} dropped: LUT / keys "
          f"TLOU2 never uses); check OK")
    return p1_rsenv.registry_block(rs, syms)


def bounds(key):
    """union of the levels' bounds from conv/pak68-part1.txt: (min xyz, max xyz)"""
    txt = open(os.path.join(CONV, "pak68-part1.txt"), encoding="latin1").read()
    pts = []
    for ln in txt.split("\n"):
        if ln.startswith(("upperLeft ", "lowerRight ")):
            pts.append([float(x) for x in ln.split()[1:4]])
    lo = [min(p[i] for p in pts) for i in range(3)]
    hi = [max(p[i] for p in pts) for i in range(3)]
    return lo, hi


def yaw_quat(deg):
    h = math.radians(deg) / 2
    return [0.0, math.sin(h), 0.0, math.cos(h)]


def seed(key):
    lo, hi = bounds(key)
    cx, cz = (lo[0] + hi[0]) / 2, (lo[2] + hi[2]) / 2
    y = lo[1] + 0.6                      # just above the lowest bound: ground level guess
    rx, rz = (hi[0] - lo[0]) / 2, (hi[2] - lo[2]) / 2
    r = min(rx, rz) * 0.35

    def pt(a, rad, yaw):
        return {"pos": [round(cx + rad * math.cos(math.radians(a)), 3), round(y, 3), round(cz + rad * math.sin(math.radians(a)), 3)],
                "quat": yaw_quat(yaw)}
    body = {"_note": "PLACEHOLDER spawns from the Part I level bounds (p1_levelset.py seed): ring around the centre, ground height "
                     "guessed - place real ones with F8 marks (tools/maps/sp_maps.py / levels.py), then rebuild",
            "player": pt(0, r, 180),
            "intro0": [pt(180 + 8 * i, r, 0) for i in range(4)],
            "intro1": [pt(0 + 8 * i, r, 180) for i in range(4)],
            "respawns": [pt(i * 360 / 13, r * 0.7, 180 + i * 360 / 13) for i in range(13)],
            "boxes": [pt(30 + i * 60, r * 0.4, 0) for i in range(6)]}
    os.makedirs(DATA, exist_ok=True)
    sp = os.path.join(DATA, f"{key}-spawns.json")
    json.dump(body, open(sp, "w"), indent=1)
    print("spawns ->", sp)
    m = spec(key)
    dst = os.path.join(LEVELS, m["pak"] + "-ingame.pak")
    js = os.path.join(DATA, f"{key}-pak.json")
    json.dump(dict(body, props=m.get("props", [])), open(js, "w"), indent=1)
    subprocess.run(["pwsh", "-NoProfile", "-File", MAKE_PAK, "-Template", TEMPLATE, "-Spec", os.path.abspath(js),
                    "-Out", os.path.abspath(dst)], check=True)
    print("spawner pak ->", dst)


def floor(key, y=None, x0=None, z0=None, x1=None, z1=None):
    """Interim walkable ground: a grid of flat `invis-collision` panels (3 x 3 m, stock actor of sp-common) as props of the map, because
    Part I's own collision is not loadable yet.  Ground y / area are guesses from the Part I bounds of the first level - give --y after
    standing on the level.  Tagged "floor": true in sp_maps.json; python p1_levelset.py floor <key> --clear removes them."""
    m = spec(key)
    lo, hi = bounds_of(m["part1"]["levels"][:1])
    x0 = lo[0] if x0 is None else x0
    x1 = hi[0] if x1 is None else x1
    z0 = lo[2] if z0 is None else z0
    z1 = hi[2] if z1 is None else z1
    y = lo[1] + 0.4 if y is None else y
    q = [-0.70711, 0.0, 0.0, 0.70711]              # the panel stands in XY: lay it into XZ
    props = [p for p in m.get("props", []) if not p.get("floor")]
    nx, nz = int(math.ceil((x1 - x0) / 3.0)), int(math.ceil((z1 - z0) / 3.0))
    for i in range(nx):
        for j in range(nz):
            props.append({"art": "invis-collision", "pos": [round(x0 + 1.5 + 3 * i, 3), round(y - 0.05, 3), round(z0 + 1.5 + 3 * j, 3)],
                          "quat": q, "floor": True})
    save_props(key, props)
    make_pak(key)
    print(f"{key}: {nx * nz} floor panels at y {y:.2f} over x {x0:.1f}..{x1:.1f}, z {z0:.1f}..{z1:.1f}")


def save_props(key, props):
    """write the map's props back to sp_maps.json keeping its line endings (sp_maps.save_spec_props rewrites the whole file with LF)"""
    raw = open(SPEC, encoding="utf-8", newline="").read()
    d = json.loads(raw)
    for m in d["maps"]:
        if m["key"] == key:
            m["props"] = props
    out = json.dumps(d, indent=1, ensure_ascii=False) + "\n"
    open(SPEC, "w", encoding="utf-8", newline="").write(out.replace("\n", "\r\n") if "\r\n" in raw else out)


def make_pak(key):
    sys.path.insert(0, os.path.join(TOOLS, "maps"))
    import sp_maps
    sp_maps.pak(key)


def bounds_of(levels):
    txt = open(os.path.join(CONV, "pak68-part1.txt"), encoding="latin1").read().split("\n")
    pts, cur = [], False
    for ln in txt:
        if ln.startswith("level-name "):
            cur = ln[11:].strip() in levels
        elif cur and ln.startswith(("upperLeft ", "lowerRight ")):
            pts.append([float(x) for x in ln.split()[1:4]])
    return [min(p[i] for p in pts) for i in range(3)], [max(p[i] for p in pts) for i in range(3)]


def main(argv):
    if len(argv) >= 4 and argv[1] == "convert":
        drop = next((int(a.split("=")[1]) for a in argv if a.startswith("--tex-drop=")), None)
        if drop is None and os.environ.get("T2R_P1_TEXDROP", "") != "":
            drop = int(os.environ["T2R_P1_TEXDROP"])
        only = next((a.split("=", 1)[1].split(",") for a in argv if a.startswith("--only=")), None)
        convert(argv[2], argv[3], drop, only)
    elif len(argv) >= 4 and argv[1] == "actors":
        write_actors(argv[2], argv[3])
    elif len(argv) >= 4 and argv[1] == "phys":
        convert_phys(argv[2], argv[3])
    elif len(argv) >= 3 and argv[1] == "floor":
        opt = {a.split("=")[0]: float(a.split("=")[1]) for a in argv[3:] if a.startswith("--") and "=" in a}
        if "--clear" in argv:
            save_props(argv[2], [p for p in spec(argv[2]).get("props", []) if not p.get("floor")])
            make_pak(argv[2])
        else:
            floor(argv[2], opt.get("--y"), opt.get("--x0"), opt.get("--z0"), opt.get("--x1"), opt.get("--z1"))
    elif len(argv) >= 3 and argv[1] == "seed":
        seed(argv[2])
    else:
        print(__doc__)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
