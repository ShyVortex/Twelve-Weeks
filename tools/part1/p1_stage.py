"""The Part I file-staging steps, ONE code path for the build (sp_maps_build -> build_dll) and for p1conv (the launcher-side converter).

These steps used to live inside sp_maps_build.py. They only copy / patch FILES of the converted conv dir into a stage tree under the in-game paths:
  stage_levels      conv/<level>[-phys|-ingame].pak -> <stage>/pak68/   (+ the loader-mirror check, + the fire point lights grafted into the base pak)
  stage_rs_files    conv/<rs>-ingame.pak -> <stage>/pak68/, conv/<rs>.t1x.bin -> <stage>/bin/dc1/render-settings/t1x.bin (+ the exposure bisect knobs)
  stage_actors      conv/actors/<a>.pak -> <stage>/actor97/<a>.pak
  stage_audio_files the converted audio set -> <stage> (the files only)
What stays in the build because it edits the client's own files, not Part I files: bin/dc1/modules.bin (size + export list of the t1x module and the audio
carriers) and the pak68.txt registry lines. Every function takes the conv dir explicitly; sp_maps_build passes its P1_CONV.

Pure helpers (no env dependence beyond the documented T2R_P1_* switches): p1_levels, p1_rs, p1_ingame, p1_phys, fill_on, level_files, rs_files.
"""
import json
import os
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.dirname(HERE)
for _p in (HERE, os.path.join(TOOLS, "models"), os.path.join(TOOLS, "maps")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

RS_MODULE = "render-settings/t1x"
FILL_SYM = "*t2r-p1-ambient-fill*"


def p1_levels(m):
    return list(m.get("part1", {}).get("levels", []))


def p1_rs(m):
    """the map's Part I render-settings level (spec part1 "rs-level"); T2R_P1_RS=0 = without"""
    if os.environ.get("T2R_P1_RS", "1") == "0":
        return None
    return m.get("part1", {}).get("rs-level")


def p1_ingame():
    return os.environ.get("T2R_P1_INGAME") == "1"


def p1_phys(level, conv):
    """stage / register <level>-phys?  Default: when conv/phys-status.json says havok2017 / empty for it. T2R_P1_PHYS=0: never, =1: always."""
    env = os.environ.get("T2R_P1_PHYS", "")
    if env in ("0", "1"):
        return env == "1"
    try:
        st = json.load(open(os.path.join(conv, "phys-status.json")))
    except (OSError, ValueError):
        return False
    return st.get(level) in ("havok2017", "empty")


def p1_audio_on():
    return os.environ.get("T2R_P1_AUDIO", "1") != "0"


def fill_on():
    return os.environ.get("T2R_P1_FILL", "0") == "1"


def level_files(m, conv):
    """[(<level><suffix>.pak)] the build stages into pak68/ for the map's Part I levels"""
    out = []
    for lv in p1_levels(m):
        for suf in ("",) + (("-phys",) if p1_phys(lv, conv) else ()) + (("-ingame",) if p1_ingame() else ()):
            out.append(lv + suf + ".pak")
    return out


def rs_files(m):
    """[(stage-relative path, conv-relative source name)] of the render-settings set, or []"""
    rs = p1_rs(m)
    if not rs:
        return []
    return [("pak68/" + rs + "-ingame.pak", rs + "-ingame.pak"), ("bin/dc1/" + RS_MODULE + ".bin", rs + ".t1x.bin")]


def _fires():
    import p1_fires
    return p1_fires


def stage_lights(stage, m, lv):
    """the Forest trash can's point light at each fire whose spec "light-level" is `lv`, appended to the staged base pak's LIGHT_TABLE_1; the result
    must read back and pass the loader mirrors. T2R_P1_FIRES=0: off (fires and lights), T2R_P1_FIRE_LIGHTS=0: the lights only"""
    F = _fires()
    fs = [f for f in F.fires(m) if f.get("light-level") == lv] if os.environ.get("T2R_P1_FIRE_LIGHTS", "1") != "0" else []
    if not fs:
        return
    import p1_convert
    dst = os.path.join(stage, "pak68", lv + ".pak")
    before = open(dst, "rb").read()
    recs = [F.light_record(f["pos"], f.get("light")) for f in fs]
    after = F.add_point_lights(before, recs)
    bad = F.check(before, after, recs)
    assert not bad, f"{m['key']}: fire lights in {lv}.pak: {bad}"
    open(dst, "wb").write(after)
    bad = p1_convert.loader_check(dst) + p1_convert.lights_check(dst) + p1_convert.trailer_check(dst)
    assert not bad, f"{m['key']}: {lv}.pak with the fire lights fails the loader mirrors {bad}"
    print(f"sp map {m['key']}: {len(recs)} fire point lights in {lv}.pak ({len(before)} -> {len(after)} bytes)")


def stage_levels(stage, m, conv):
    """copy the converted level paks into <stage>/pak68 (loader-mirror check on the base paks, fire lights grafted); -> number of paks"""
    n = 0
    os.makedirs(os.path.join(stage, "pak68"), exist_ok=True)
    for lv in p1_levels(m):
        for suf in ("",) + (("-phys",) if p1_phys(lv, conv) else ()) + (("-ingame",) if p1_ingame() else ()):
            src = os.path.join(conv, lv + suf + ".pak")
            assert os.path.exists(src), f"{m['key']}: {src} missing - run: python tools/part1/p1_levelset.py convert <Part I dir> {m['key']}"
            if suf == "" and os.environ.get("T2R_P1_PAKCHECK", "1") != "0":
                # An array cut by a page end (GEOMETRY_1 submeshes, VIS records) crashes the load on every client;
                # the converter's offline mirrors of what the loader walks must be clean before a pak ships
                import p1_convert
                bad = p1_convert.geometry_extent_check(src) + p1_convert.loader_check(src)
                assert not bad, f"{m['key']}: {lv}.pak fails the loader mirrors {bad} - reconvert it (p1_levelset.py convert ... --only={lv})"
            shutil.copyfile(src, os.path.join(stage, "pak68", lv + suf + ".pak"))
            n += 1
            if suf == "":
                stage_lights(stage, m, lv)
    if p1_levels(m):
        print(f"sp map {m['key']}: {len(p1_levels(m))} Part I levels staged ({n} paks, converted TLOU2 layout)")
    return n


def stage_rs_files(stage, m, conv):
    """the map's Part I render settings files: <rs>-ingame.pak into pak68/, <rs>.t1x.bin as bin/dc1/render-settings/t1x.bin (TLOU2's t1x module,
    which no TLOU2 level references, + the Part I symbols). -> the t1x.bin path, or None when the map has no rs level"""
    rs = p1_rs(m)
    if not rs:
        return None
    for src in (os.path.join(conv, rs + "-ingame.pak"), os.path.join(conv, rs + ".t1x.bin")):
        assert os.path.exists(src), \
            f"{m['key']}: {src} missing - run: python tools/part1/p1_levelset.py convert <Part I dir> {m['key']} (or T2R_P1_RS=0)"
    os.makedirs(os.path.join(stage, "pak68"), exist_ok=True)
    shutil.copyfile(os.path.join(conv, rs + "-ingame.pak"), os.path.join(stage, "pak68", rs + "-ingame.pak"))
    dst = os.path.join(stage, "bin", "dc1", *RS_MODULE.split("/")) + ".bin"
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    shutil.copyfile(os.path.join(conv, rs + ".t1x.bin"), dst)
    ev, sp = float(os.environ.get("T2R_P1_RS_EV", "0") or 0), float(os.environ.get("T2R_P1_RS_SP", "0") or 0)
    if ev or sp:        # exposure bisect (p1_rsenv.shift_tonemap): Part I's tonemap range / set point shifted at stage time
        import p1_rsenv
        data, n = p1_rsenv.shift_tonemap(open(dst, "rb").read(), ev, sp)
        open(dst, "wb").write(data)
        print(f"sp map {m['key']}: Part I tonemap shifted by T2R_P1_RS_EV={ev:+g} (range) / T2R_P1_RS_SP={sp:+g} (set point): {n} values")
    if fill_on():       # synthetic ambient-fill symbol (character fake ambient + ambient scales), no reconvert needed
        import p1_rsenv
        data, rep = p1_rsenv.add_fill_symbol(open(dst, "rb").read(), FILL_SYM)
        open(dst, "wb").write(data)
        print(f"sp map {m['key']}: render-settings symbol {FILL_SYM} added ({rep} settings)")
    return dst


def stage_actors(stage, m, conv, actor_paths):
    """the converted Part I actor paks (conv/actors/<name>.pak) as actor97/<name>.pak; actor_paths = the map's mod-relative list (sp_maps_build.p1_actor_files)"""
    n = 0
    for p in actor_paths:
        os.makedirs(os.path.join(stage, "actor97"), exist_ok=True)
        shutil.copyfile(os.path.join(conv, "actors", os.path.basename(p)), os.path.join(stage, p))
        n += 1
    return n


def stage_audio_files(stage, audio_dir, manifest):
    """the converted Part I audio set (audio.json "files") into the stage, files only (modules.bin is the build's)"""
    for f in manifest["files"]:
        src, dst = os.path.join(audio_dir, f["path"]), os.path.join(stage, *f["path"].split("/"))
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        with open(src, "rb") as a, open(dst, "wb") as b:
            while True:
                chunk = a.read(1 << 22)
                if not chunk:
                    break
                b.write(chunk)
