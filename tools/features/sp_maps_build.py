"""Build step for PvP maps made from single-player sections (re/maps/technical.md, tools/maps/sp_maps.json).

T2R_SP_MAPS=hardware,motel (or "all" = every spec entry with "build": true) adds, per map, on the staged mod tree:
  - level-sets-test.bin: the map's OWN level set (allocate(): one of the 7 leftover dev sets of the pool = a "slot", only its
    arrays pointer repointed - or, past the pool, a fresh entry "tsk-to1-<key>-1" with its entry-table row + modules.bin export)
    with the level list (our spawner pak + the SP art levels) and the to1-all part set (re/maps/technical.md 5k).
  - test-tasks.bin: a new subnode "to1-<key>" under task node "to1-levels" (a copy of to1-custom-map-1, the
    Hospital's, renamed, pointing at the map's own level set), keys / values of the node's map rebuilt sorted
    (binary search); adjacency: chained after the stock tail (stock tail -> new1 -> ... -> %end, one successor per node; T2R_SP_EDGES).
  - pak68.txt: level block for our spawner pak (+ "actor <prop>" lines: the props' actor97 paks load with it).
  - modules.bin sizes of both DC files are returned for build_dll to write.
Without T2R_SP_MAPS nothing changes (the spawner paks still ship but are not registered / loaded).
The daemon needs the same T2R_SP_MAPS so it offers the maps (daemon.py SP_MAPS)."""
import json
import sys
import os
import shutil
import struct

from dcfile import DcFile, fnv

HERE = os.path.dirname(os.path.abspath(__file__))
SPEC = os.path.join(HERE, "..", "maps", "sp_maps.json")
NODE = "to1-levels"
TEMPLATE_SUB = "to1-custom-map-1"           # Hospital's subnode (already repointed by patch_hospital_map)
TEMPLATE_SET = "tsk-to1-forest-1"           # PvP set: arrays block with the to1-all part set
SUB_SIZE = 0x430                            # game-task-subnode incl. its inner structs (tag excluded)
# Train Station (first map with a level-set actor list) loaded its geometry but the player never spawned
# (free camera behind the loading screen, state 3 forever). The proven maps (School with its dumpster blockers,
# Hospital, Hardware) have NO level-set actor list: the pak68.txt "actor <art>" lines alone load the props. So the
# list stays empty unless T2R_SP_LS_ACTORS=1.
# T2R_SP_LEGACY=1: reproduce the output of 114324d (the Hardware-era build that loaded) for any map - the proven baseline
# to bisect from. Differences to the current path (all of them):
#   level set      leftover slot set repointed (no new entry / export)            = the default slot pool (allocate())
#   level-set list actor list (list 2) = the map's prop actors, as 114324d        = T2R_SP_LS_ACTORS=1
#   subnode copy   copied ONCE before the loop (clones 2.. get stale string pointers, clone 1 is identical)
#   task id +0x28  kept from the template (custom-map-1's id; e2cc071 writes fnv("to1-levels-<name>"))
#   edges          chain: stock tail -> new1 -> ... -> %end                         = T2R_SP_EDGES=chain
#   slot           PREFERRED[key] via allocate() (114324d: the map spec's "slot", Hardware = golden-gun)
#   verify()       no task-id / pointer / successor checks
# Everything else (pak68 lines, spawner pak, thumbnails, modules.bin sizes) is unchanged since 114324d (build_dll.py is identical).
LEGACY = os.environ.get("T2R_SP_LEGACY", "") == "1"
LEVEL_SET_ACTORS = LEGACY or os.environ.get("T2R_SP_LS_ACTORS", "") == "1"
ACTOR_ENTRY_TAG = 0xF1567AAA3FA1099E        # tag of level-set actor entries {name, sid} (stock level-sets-rogue.bin)
LEVEL_SET_SIZE = 0x30                       # a level-set struct (tag "level-set" before it); +0x28 = u32 -1 in all 2232 game sets


def specs():
    maps = json.load(open(SPEC, encoding="utf-8"))["maps"]
    only = [x.strip() for x in os.environ.get("T2R_P1_LEVELS", "").split(",") if x.strip()]
    if only:        # isolation builds: stage / register / list only these Part I levels, e.g. T2R_P1_LEVELS=hun-checkpoint-bookstore-facade
        for m in maps:
            lv = m.get("part1", {}).get("levels")
            if lv:
                drop = [x for x in lv if x not in only]
                m["part1"]["levels"] = [x for x in lv if x in only]
                m["levels"] = [x for x in m["levels"] if x not in drop]
    skip = {x.strip() for x in os.environ.get("T2R_P1_SKIP", "").split(",") if x.strip()}
    for m in maps:      # bisect switches (crash hunt): T2R_P1_OUTSIDE=0 drops the map spec's part1.outside levels, T2R_P1_SKIP=a,b drops these
        p1 = m.get("part1", {})
        drop = set(skip) | (set(p1.get("outside", [])) if os.environ.get("T2R_P1_OUTSIDE", "1") == "0" else set())
        if p1.get("levels") and drop & set(p1["levels"]):
            p1["levels"] = [x for x in p1["levels"] if x not in drop]
            m["levels"] = [x for x in m["levels"] if x not in drop]
    for m in maps:      # Part I fire barrels (tools/part1/p1_fires.py): the Forest trash-can fire's particle groups load with the map
        if m.get("part1", {}).get("fires"):
            sys.path.insert(0, os.path.join(os.path.dirname(HERE), "part1"))
            import p1_fires
            P = _p1_particles()
            if P.wanted(m):     # Part I's own fire particles (p1_particles.py): their part levels instead of the Forest can's
                m["levels"] = m["levels"] + [x for x in P.levels(m) if x not in m["levels"]]
            elif p1_fires.on() and p1_fires.DONOR_PARTICLES not in m["levels"]:
                m["levels"] = m["levels"] + [p1_fires.DONOR_PARTICLES]
            fx = _p1_firesfx()      # The fires' looping sound: own small level (region emitters + sound-bank lvl-nor-forest-amb), tools/part1/p1_firesfx.py
            if fx.sfx_fires(m) and fx.level_name(m) not in m["levels"]:
                m["levels"] = m["levels"] + [fx.level_name(m)]
    for m in maps:      # Part I ambient particles that TLOU2 has under the same name ("particles" in the spec): their part-level loads with the map
        pa = m.get("part1", {}).get("particles")
        if pa and os.environ.get("T2R_P1_AMBIENT", "1") != "0" and pa["level"] not in m["levels"]:
            m["levels"] = m["levels"] + [pa["level"]]
    for m in maps:      # Part I Bookstore ambience (tools/part1/p1_audio.py): the audio levels leave the level set when it is off / not converted
        if m.get("part1", {}).get("audio"):
            P = _p1_audio()
            with p1_map_env(m):
                have = P.available(m)
            if not P.on() or not have:
                if P.on() and os.environ.get("T2R_P1_AUDIO") == "1":
                    raise AssertionError(f"{m['key']}: T2R_P1_AUDIO=1 but {P.AUDIO} has no audio.json - run: python tools/part1/p1_audio.py convert <Part I dir>")
                _p1_audio_note(P)
                m["levels"] = [x for x in m["levels"] if x not in P.levels_of(m)]
                m["part1"] = {k: v for k, v in m["part1"].items() if k != "audio"}
    if os.environ.get("T2R_P1_RS", "1") == "0":     # without Part I's render settings: their level leaves the level sets too
        for m in maps:
            rs = m.get("part1", {}).get("rs-level")
            if rs:
                m["levels"] = [x for x in m["levels"] if x != rs]
    return maps


def selected(env=None):
    """Maps built into this DLL: the map spec's "always" maps (No Return arenas such as Train Station: regular pool maps,
    never behind T2R_SP_MAPS) + the SP-section maps T2R_SP_MAPS lists."""
    env = (os.environ.get("T2R_SP_MAPS", "") if env is None else env).strip()
    all_ = specs()
    always = [m for m in all_ if m.get("always")]
    if not env or env in ("0", "none"):
        return _no_old_hospital(always)
    if env in ("1", "all"):
        return _no_old_hospital([m for m in all_ if (m["build"] or m.get("always")) and not m.get("retired")])
    want = [k.strip() for k in env.split(",") if k.strip()]
    by = {m["key"]: m for m in all_}
    bad = [k for k in want if k not in by]
    assert not bad, f"T2R_SP_MAPS: unknown map(s) {bad} (tools/maps/sp_maps.json)"
    gone = [k for k in want if by[k].get("retired")]
    assert not gone, f"T2R_SP_MAPS: retired map(s) {gone} (sp_maps.json \"retired\": true - dropped, never built)"
    out = always + [by[k] for k in want if not by[k].get("always")]
    return _no_old_hospital(out)


def hospital_replaced():
    """The Ellie ground-floor Hospital (sp_maps.json hospital-ellie, "replaces": "to1-custom-map-1") is the Hospital of this build.
    T2R_HOSPITAL_OLD=1 = the old No Return hospital set (fallback if the new level list crashes on load)."""
    return os.environ.get("T2R_HOSPITAL_OLD", "") != "1"


def _no_old_hospital(maps):
    return maps if hospital_replaced() else [m for m in maps if not m.get("replaces")]


def _entries(f):
    cnt = struct.unpack_from("<I", f.data, 0x14)[0]
    eo = struct.unpack_from("<Q", f.data, 0x18)[0]
    return {struct.unpack_from("<Q", f.data, eo + i * 24)[0]: struct.unpack_from("<Q", f.data, eo + i * 24 + 16)[0]
            for i in range(cnt)}


def _cstr(f, o):
    return f.data[o:f.data.index(b"\0", o)].decode("latin1")


# Maps whose levels come from the TLOU Part I install ("part1": {"levels": [...]} in sp_maps.json): the level paks were
# converted to the TLOU2 pak layout by tools/part1/p1_levelset.py convert (<main repo>/re/part1/x/conv, git-ignored) and are
# staged into the mod's pak68 dir + registered here.  Part I content is never committed.
_MAIN = os.environ.get("T2R_MAIN_ROOT", os.path.dirname(os.path.dirname(HERE)).split(os.sep + ".claude" + os.sep)[0])
P1_CONV = os.environ.get("T2R_P1_CONV") or os.path.join(_MAIN, "re", "part1", "x", "conv")


# Two Part I maps in one build (Bookstore + Plaza): each map's converted set, audio set and actor switch come from its own
# tools/part1/data/p1_maps/<key>.json "build" block ({main} = the main checkout, {wt} = $T2R_WT), so the global T2R_P1_CONV /
# T2R_P1_AUDIO_DIR / T2R_P1_ACTORS_CONVERTED only apply to a map without one. T2R_P1_CONV_<KEY> (key upper-case, '-' -> '_') overrides
# a map's conv dir for a test. Every per-map step runs inside p1_map_env(m), which points P1_CONV, p1_audio.AUDIO and the actor switch
# at that map and restores them after.
def p1_rs_renames(m):
    """{old render-settings symbol name: new} the map stages its Part I render settings under (p1_maps json "rs_renames"; Plaza's copy
    of Part I's city-wide base, so it never shares a symbol with the Bookstore's)"""
    f = os.path.join(HERE, "..", "part1", "data", "p1_maps", m["key"] + ".json")
    return dict(json.load(open(f, encoding="utf-8")).get("rs_renames") or {}) if m.get("part1", {}).get("levels") and os.path.exists(f) else {}


def p1_build_cfg(m):
    """-> {"conv", "audio", "actors_converted"} of a Part I map's p1_maps json "build" block (missing keys left out), or None"""
    if not m.get("part1", {}).get("levels"):
        return None
    f = os.path.join(HERE, "..", "part1", "data", "p1_maps", m["key"] + ".json")
    b = json.load(open(f, encoding="utf-8")).get("build") if os.path.exists(f) else None
    if not b:
        return None
    sub = {"main": _MAIN, "wt": os.environ.get("T2R_WT", "../t2r-wt")}
    out = {k: os.path.normpath(b[k].format(**sub)) for k in ("conv", "audio") if b.get(k)}
    env = os.environ.get("T2R_P1_CONV_" + m["key"].upper().replace("-", "_"))
    if env:
        out["conv"] = env
    if "actors_converted" in b:
        out["actors_converted"] = bool(b["actors_converted"])
    return out


_P1_ENV_LOG = set()
_RS_STAGED = {}         # stage dir -> [(map key, its staged t1x bytes)] in build order (stage_part1_rs merges them)


class p1_map_env:
    """with p1_map_env(m): P1_CONV / p1_audio.AUDIO / T2R_P1_ACTORS_CONVERTED follow map m (no-op for a map without a build block)"""
    def __init__(self, m):
        self.cfg = p1_build_cfg(m) if isinstance(m, dict) else None
        self.key = m.get("key") if isinstance(m, dict) else None

    def __enter__(self):
        global P1_CONV
        if not self.cfg:
            return self
        A = _p1_audio()
        self.saved = (P1_CONV, A.AUDIO, os.environ.get("T2R_P1_ACTORS_CONVERTED"))
        P1_CONV = self.cfg.get("conv", P1_CONV)
        A.AUDIO = self.cfg.get("audio", A.AUDIO)
        if "actors_converted" in self.cfg:
            os.environ["T2R_P1_ACTORS_CONVERTED"] = "1" if self.cfg["actors_converted"] else "0"
        if self.key not in _P1_ENV_LOG:
            _P1_ENV_LOG.add(self.key)
            print(f"sp map {self.key}: Part I inputs conv={P1_CONV} audio={A.AUDIO} actors_converted={os.environ.get('T2R_P1_ACTORS_CONVERTED', '0')}")
        return self

    def __exit__(self, *exc):
        global P1_CONV
        if not self.cfg:
            return False
        A = _p1_audio()
        P1_CONV, A.AUDIO, ac = self.saved
        if ac is None:
            os.environ.pop("T2R_P1_ACTORS_CONVERTED", None)
        else:
            os.environ["T2R_P1_ACTORS_CONVERTED"] = ac
        return False


def _per_map(argi=0):
    """decorator: run the function inside p1_map_env(<its argument argi>)"""
    def deco(fn):
        def w(*a, **k):
            with p1_map_env(a[argi]):
                return fn(*a, **k)
        w.__name__, w.__doc__ = fn.__name__, fn.__doc__
        return w
    return deco


def p1_levels(m):
    return _p1_stage().p1_levels(m)


def p1_rs(m):
    """the map's Part I render-settings level (spec part1 "rs-level", built by p1_levelset.py convert / p1_rsenv.py:
    conv/<rs>-ingame.pak = Part I's render-settings regions over the map, conv/<rs>.t1x.bin = TLOU2's render-settings/t1x
    module + the Part I symbols; re/part1/geometry-upgrade.md s11) or None; T2R_P1_RS=0 = without"""
    if os.environ.get("T2R_P1_RS", "1") == "0":
        return None
    return m.get("part1", {}).get("rs-level")


RS_MODULE = "render-settings/t1x"


def _p1_particles():
    sys.path.insert(0, os.path.join(os.path.dirname(HERE), "part1"))
    sys.path.insert(0, os.path.join(os.path.dirname(HERE), "models"))
    import p1_particles
    return p1_particles


def p1_particle_files(m):
    """mod-relative paths of the map's Part I fire particle set (part level paks + carrier DC modules: Part I map data); [] without it"""
    return [rel for rel, _src in _p1_particles().files(m)]


def _p1_audio():
    sys.path.insert(0, os.path.join(os.path.dirname(HERE), "part1"))
    sys.path.insert(0, os.path.join(os.path.dirname(HERE), "models"))
    import p1_audio
    return p1_audio


_AUDIO_NOTED = []


def _p1_audio_note(P):
    if not _AUDIO_NOTED:
        _AUDIO_NOTED.append(1)
        print(("sp maps: Part I Bookstore ambience OFF (T2R_P1_AUDIO=0)" if not P.on() else
               f"sp maps: Part I Bookstore ambience NOT built: {P.AUDIO}/audio.json missing (python tools/part1/p1_audio.py convert <Part I dir>); T2R_P1_AUDIO=1 makes this an error"))


@_per_map(0)
def p1_audio_files(m):
    """mod-relative paths of the map's Part I ambience (paks, banks, streams, DC carrier modules) for the archive manifest; [] without it"""
    if not m.get("part1", {}).get("audio"):
        return []
    return _p1_audio().manifest_paths(m)


@_per_map(0)
def p1_lut_files(m):
    """mod-relative paths of the map's Part I LUT textures (lut0/..., Part I colour grading) for the archive manifest; [] without or with T2R_P1_RS=0"""
    l = _p1_stage().lut_files(P1_CONV) if p1_rs(m) else []
    return l + ["lut0/files.json"] if l else []


def p1_ingame():
    return _p1_stage().p1_ingame()


def p1_phys(level):
    """stage / register <level>-phys? (p1_stage.p1_phys: conv/phys-status.json; T2R_P1_PHYS=0 never, =1 always; re/part1/havok-collision.md)"""
    return _p1_stage().p1_phys(level, P1_CONV)


FILL_SYM = "*t2r-p1-ambient-fill*"


def fill_on():
    # No TLOU2-value fill, OFF by default (p1_stage.fill_on; T2R_P1_FILL=1 = the old fill symbol)
    return _p1_stage().fill_on()


def _p1_actor_level(m, lvl):
    """True for the Part I level whose -ingame package is our tiny light-actor pak (spec part1.light-actors[].level; T2R_P1_LIGHT_ACTORS=0 off)"""
    # no longer tied to the map having fires (Plaza has Part I lights and no fire barrels); T2R_P1_FIRES=0 still turns them off
    if os.environ.get("T2R_P1_LIGHT_ACTORS", "1") == "0" or not _p1_fires().on():
        return False
    return any(a["level"] == lvl for a in _p1_fires().light_actors(m))


def p1_fires_mod():
    sys.path.insert(0, os.path.join(os.path.dirname(HERE), "part1"))
    import p1_fires
    return p1_fires


def p1_actors_on():
    """List Part I's block `actor` lines (the ones TLOU2 also ships) in the Part I level blocks. A skinned / interactive-BG
    instance (INTERACTIVE_BG_1: the hanging ivy, bushes, grass) or a spawner of an -ingame pak only spawns when its actor pak is in the level's
    block, exactly like the light-skel actor. Nothing in the staged paks names them while INTERACTIVE_BG_1 is dropped (T2R_P1_KEEP_UNKNOWN=1)
    and the -ingame paks are not staged (T2R_P1_INGAME=1), so the default follows those two (KEEP_UNKNOWN is on by default, see p1_convert); T2R_P1_ACTORS=1 / 0 forces it."""
    env = os.environ.get("T2R_P1_ACTORS", "")
    if env in ("0", "1"):
        return env == "1"
    return p1_ingame() or os.environ.get("T2R_P1_KEEP_UNKNOWN", "1") != "0"


def t2_actor_paks():
    """{actor} of TLOU2's actor97/<actor>.pak files (re/game-files.tsv of the main checkout): the actors a Part I block may name that exist here"""
    out = set()
    try:
        for ln in open(os.path.join(_MAIN, "re", "game-files.tsv"), encoding="utf-8"):
            c = ln.rstrip("\n").split("\t")
            if len(c) >= 2 and c[1].startswith("actor97/") and c[1].endswith(".pak"):
                out.add(c[1][8:-4])
    except OSError:
        pass
    return out


@_per_map(0)
def p1_block_actors(m):
    """{level: [actor, ...]} Part I's block actors (conv/actors-part1.json, python p1_levelset.py actors <Part I dir> <key>) that TLOU2 also has;
    {} when off / not written. Part I-only actors (no TLOU2 actor97 pak: books-*, hun-isle-sign-*, ivy-weeds-a-overhanging-a ...) stay out:
    the registry would name a pak that does not exist"""
    if not p1_actors_on():
        return {}
    try:
        import json
        d = json.load(open(os.path.join(P1_CONV, "actors-part1.json")))
    except (OSError, ValueError):
        return {}
    have = t2_actor_paks()
    try:
        if p1_fires_mod().converted_actors_on():
            have |= {f[:-4] for f in os.listdir(os.path.join(P1_CONV, "actors")) if f.endswith(".pak")}      # the converted Part I actors (p1_actors.py), own names
    except OSError:
        pass
    return {lv: [a for a in al if a in have] for lv, al in d.items()}


@_per_map(0)
def p1_blocks(m):
    """registry lines of the map's Part I levels (written by p1_levelset.py convert)"""
    f = os.path.join(P1_CONV, "pak68-part1.txt")
    assert os.path.exists(f), f"{m['key']}: {f} missing - run: python tools/part1/p1_levelset.py convert <Part I dir> {m['key']}"
    rs = p1_rs(m)
    want, out, cur, lvl, blk = set(p1_levels(m)) | ({rs} if rs else set()), [], None, None, 0
    acts = p1_block_actors(m)
    for ln in open(f, encoding="latin1").read().split("\n"):
        if ln.startswith("level-name "):
            lvl = ln[11:].strip()
            cur = lvl in want
            blk = len(out)      # this level's block starts here in out
        if ln.startswith(("upperLeft ", "lowerRight ")):
            continue        # Part I-only keys: TLOU2's pak68.txt has none (0 of 3073 blocks) and its parser does not know them
        if cur and ln and not (lvl != rs and ln.startswith("package ") and ((ln.endswith("-ingame") and not p1_ingame()) or (ln.endswith("-phys") and not p1_phys(lvl)))):
            out.append(ln)
            if ln == f"package {lvl}" and _p1_actor_level(m, lvl):      # the light actors' package (a ProcessDynLight spawns only with its actor pak listed)
                out += [f"package {lvl}-ingame", "actor light-skel"]
            if ln.startswith("level-id ") and lvl != rs:
                out += [f"actor {a}" for a in acts.get(lvl, ()) if f"actor {a}" not in out[blk:]]        # Part I's block actors that TLOU2 ships (T2R_P1_ACTORS); no 2nd light-skel line next to the light-actor package
    if rs and fill_on():        # synthetic ambient-fill render-settings symbol (p1_rsenv.add_fill_symbol), layered via t2r-p1-rs-override.txt
        i = max((k for k, ln in enumerate(out) if ln.startswith("render-settings ")), default=None)
        if i is not None and "render-settings " + FILL_SYM not in out:
            out[i + 1:i + 1] = ["symbol " + FILL_SYM, "render-settings " + FILL_SYM]
    rn = p1_rs_renames(m)
    if rn:              # the map's own copy of a shared Part I symbol (stage_part1_rs renames it in the rs pak and the t1x module)
        out = [(ln.split(" ", 1)[0] + " " + rn[ln.split(" ", 1)[1]]) if ln.startswith(("symbol ", "render-settings ")) and ln.split(" ", 1)[1] in rn else ln
               for ln in out]
    assert not rs or f"level-name {rs}" in out, \
        f"{m['key']}: no {rs} block in {f} - run: python tools/part1/p1_levelset.py convert <Part I dir> {m['key']} (or T2R_P1_RS=0)"
    return out


def _p1_stage():
    for q in (os.path.join(os.path.dirname(HERE), "part1"), os.path.join(os.path.dirname(HERE), "models")):
        if q not in sys.path:
            sys.path.insert(0, q)
    import p1_stage
    return p1_stage


def stage_part1(stage, maps):
    S = _p1_stage()
    for m in maps:
        with p1_map_env(m):
            S.stage_levels(stage, m, P1_CONV)
            if p1_rs(m):
                stage_part1_rs(stage, m, p1_rs(m))
            stage_part1_particles(stage, m)
            stage_part1_fires(stage, m)
            stage_part1_spawners(stage, m)
            stage_part1_light_actors(stage, m)
            if m.get("part1", {}).get("audio"):
                _p1_audio().stage(stage, m)


def _p1_firesfx():
    for q in (os.path.join(os.path.dirname(HERE), "part1"), os.path.join(os.path.dirname(HERE), "models")):
        if q not in sys.path:
            sys.path.insert(0, q)
    import p1_firesfx
    return p1_firesfx


def p1_fire_sfx_files(m):
    """mod-relative paths of the map's fire sound level pak (donor-derived TLOU2 data, not Part I data) for the archive manifest"""
    return _p1_firesfx().files(m)


def _p1_fires():
    sys.path.insert(0, os.path.join(os.path.dirname(HERE), "part1"))
    sys.path.insert(0, os.path.join(os.path.dirname(HERE), "models"))
    import p1_fires
    return p1_fires


@_per_map(1)
def stage_part1_particles(stage, m):
    """Part I's own fire particles (p1_particles.py): the converted part level paks + their DC modules as the carrier part modules, and
    modules.bin: each carrier's size + export list (base-mod edit). T2R_P1_FIRE_PARTICLES=0: off (the Forest can fire instead)"""
    P = _p1_particles()
    if not P.wanted(m):
        return
    import dc_modules
    modules = os.path.join(stage, "bin", "dc1", "modules.bin")
    for name, size, exports in P.stage(stage, m, P1_CONV):
        data = bytearray(open(modules, "rb").read())
        old = dc_modules.set_size(data, name, size)
        open(modules, "wb").write(data)
        n0, n1 = _p1_audio().set_exports(modules, name, exports)
        i0 = i1 = None
        if P.imports_on():          # Part I's import list too, not the dev test module's
            i0, i1 = P.set_imports(modules, name, P.carrier_imports(name))
        print(f"sp map {m['key']}: Part I fire particles: {name}.bin {old} -> {size} bytes, exports {n0} -> {n1}, imports {i0} -> {i1}")


def stage_part1_lights(stage, m, lv):
    """(moved to p1_stage.stage_lights, one code path with p1conv)"""
    _p1_stage().stage_lights(stage, m, lv)


@_per_map(1)
def stage_part1_light_actors(stage, m):
    """Part I's ProcessDynLight actors (Bookstore: the fake-sun projector; Plaza: the plaza / office projectors and spots), cloned from the converted
    Part I -ingame pak of the level that owns their LIGHT_TABLE_1 + ANIMATED_LIGHTS, as pak68/<level>-ingame.pak (one tiny package per level).
    Split out of stage_part1_fires and grouped by level (Plaza's lights sit in two levels and the map has no fires)."""
    F = _p1_fires()
    acts = F.light_actors(m)
    if not acts or not F.on() or not F.light_actors_on():
        return
    by = {}
    for a in acts:
        by.setdefault((a["level"], a["donor"]), []).append(a["name"])
    assert len({lv for lv, _d in by}) == len(by), f"{m['key']}: light-actors name two donors for one level"
    for (lv, dn), names in by.items():
        donor = os.path.join(P1_CONV, dn + ".pak")
        assert os.path.exists(donor), f"{m['key']}: light-actor donor {donor} missing"
        out = os.path.join(stage, "pak68", lv + "-ingame.pak")
        k = F.write_actor_pak(donor, names, out)
        print(f"sp map {m['key']}: {k} Part I light actor(s) {names} from {dn} as pak68/{lv}-ingame.pak "
              f"({os.path.getsize(out)} bytes; the level that owns the light tables)")


@_per_map(1)
def stage_part1_fires(stage, m):
    """Fire barrels (p1_fires.py): the Forest trash can's fire particle spawners at each map spec part1.fires entry, cloned into
    the staged <pak>-ingame.pak (build_dll copied the committed one before sp_maps_build.apply). T2R_P1_FIRES=0: off"""
    F = _p1_fires()
    fs = F.fires(m)
    if not fs:
        return
    pak = os.path.join(stage, "pak68", m["pak"] + "-ingame.pak")
    assert os.path.exists(pak), f"{m['key']}: {pak} not staged before the fires"
    sys.path.insert(0, os.path.join(os.path.dirname(HERE), "maps"))
    import level_edit
    cache = os.path.join(level_edit.CACHE, "p1-fires")      # the donor -ingame pak + its spawner dump
    fx = _p1_firesfx()
    if fx.sfx_fires(m):        # The fires' looping sound: <key>-fire-sfx level pak (emitter copies of the Forest can's sound region)
        fp = os.path.join(stage, "pak68", fx.level_name(m) + "-ingame.pak")
        k = fx.build(fp, fs, cache)
        print(f"sp map {m['key']}: {k} fire sound emitters ({fx.SOUND:#x}, bank {fx.BANK}) in {fx.level_name(m)}-ingame.pak ({os.path.getsize(fp)} bytes)")
    old = os.path.getsize(pak)
    P = _p1_particles()
    if P.wanted(m):     # Part I's own fire spawners (p1_particles.FIRE_SPAWNERS), cloned as they are from the converted Part I -ingame paks
        k = F.graft_level_spawners(pak, P1_CONV, sorted({lv for lv, _n in P.fire_spawners(m)}), set(), os.path.join(level_edit.CACHE, "p1-spawners"),
                                   names={n for _lv, n in P.fire_spawners(m)})
        assert k == len(P.fire_spawners(m)), f"{m['key']}: {k} of {len(P.fire_spawners(m))} Part I fire spawners found in {P1_CONV}"
        print(f"sp map {m['key']}: {k} Part I fire particle spawners in {m['pak']}-ingame.pak ({old} -> {os.path.getsize(pak)} bytes)")
    else:
        k = F.graft(pak, fs, cache)
        print(f"sp map {m['key']}: {k} fire particle spawners ({len(fs)} fires, donor {F.DONOR_LEVEL}) in {m['pak']}-ingame.pak "
              f"({old} -> {os.path.getsize(pak)} bytes)")


@_per_map(1)
def stage_part1_spawners(stage, m):
    """Part I ambient particle spawners + prop spawners (spec part1.particles / part1.spawner-arts), cloned from the converted -ingame paks into
    the staged <pak>-ingame.pak. Split out of stage_part1_fires, which returns early for a map without fires (Plaza): its spawner-arts
    were never grafted although their actor paks were staged."""
    F = _p1_fires()
    pak = os.path.join(stage, "pak68", m["pak"] + "-ingame.pak")
    sys.path.insert(0, os.path.join(os.path.dirname(HERE), "maps"))
    import level_edit
    pa = m.get("part1", {}).get("particles")
    arts = F.spawner_arts(m, P1_CONV)
    if (pa or arts) and not os.path.exists(pak):
        raise AssertionError(f"{m['key']}: {pak} not staged before the Part I spawners")
    if pa and os.environ.get("T2R_P1_AMBIENT", "1") != "0":     # Part I's ambient particle spawners whose particle group TLOU2 also ships (gnats)
        old = os.path.getsize(pak)
        k = F.graft_level_spawners(pak, P1_CONV, p1_levels(m), set(), os.path.join(level_edit.CACHE, "p1-spawners"), prefixes=tuple(pa["spawners"]))
        print(f"sp map {m['key']}: {k} Part I ambient particle spawners {pa['spawners']} (group from {pa['level']}) in {m['pak']}-ingame.pak ({old} -> {os.path.getsize(pak)} bytes)")
    if arts:        # Part I's prop spawners whose art TLOU2 ships identically (p1-bookstore-spawn-arts.json), cloned from the converted -ingame paks
        old = os.path.getsize(pak)
        k = F.graft_level_spawners(pak, P1_CONV, p1_levels(m), set(arts), os.path.join(level_edit.CACHE, "p1-spawners"), {a: F.actor_file(m, a) for a in arts})
        print(f"sp map {m['key']}: {k} Part I prop spawners ({len(arts)} arts) in {m['pak']}-ingame.pak ({old} -> {os.path.getsize(pak)} bytes)")


@_per_map(1)
def stage_part1_rs(stage, m, rs):
    """the map's Part I render settings: the files (p1_stage.stage_rs_files: <rs>-ingame.pak into pak68/, <rs>.t1x.bin as bin/dc1/render-settings/t1x.bin)
    + modules.bin: that module's size + exports (base-mod edit, stays here)"""
    import dc_modules
    dst = _p1_stage().stage_rs_files(stage, m, P1_CONV)
    # Two Part I maps: each conv's t1x is TLOU2's module + that map's symbols; the staged module is the merge of every Part I map of
    # this build so far (p1_rsenv.merge_modules).  Part I's city-wide *t1-rs-hun-const-base* differs per map (its engine-default fill and
    # LUT records depend on the map's own symbols: Plaza's sun has no own red record), so a map's p1_maps json "rs_renames" stages its
    # copy under its own name: the rs pak's region tags, the module symbol, the registry lines (p1_blocks) and the ext row (const_sym).
    import p1_rsenv
    rn = p1_rs_renames(m)
    if rn:
        pk = os.path.join(stage, "pak68", rs + "-ingame.pak")
        new_pk = p1_rsenv.rename_rs_pak(open(pk, "rb").read(), rn)       # (read first: open(..., "wb") truncates)
        open(pk, "wb").write(new_pk)
        print(f"sp map {m['key']}: {rs}-ingame.pak render-settings tags renamed {rn}")
    done = _RS_STAGED.setdefault(os.path.normcase(os.path.abspath(stage)), [])
    done.append((m["key"], open(dst, "rb").read(), {p1_rsenv.fnv(o): p1_rsenv.fnv(n) for o, n in rn.items()}))
    if len(done) > 1 or rn:
        stock = open(os.path.join(_MAIN, "re", "gamebin", "dc1", *RS_MODULE.split("/")) + ".bin", "rb").read()
        merged, conflicts = p1_rsenv.merge_modules(stock, [d for _k, d, _r in done], [r for _k, _d, r in done])
        open(dst, "wb").write(merged)
        print(f"sp map {m['key']}: {RS_MODULE}.bin = stock + {', '.join(k for k, _d, _r in done)} ({len(merged)} bytes); "
              f"shared symbols kept from the first map that has them (a later map's copy differs, unused there): "
              f"{', '.join(f'{x:#x}' for x in conflicts) or 'none'}")
        # a symbol whose records differ keeps the first map's; a later map must not use its dropped copy (its regions' tags, its ext rows)
        for s_, losers in conflicts.items():
            for i in losers:
                k_, _d, _r = done[i]
                mm = next(x for x in specs() if x["key"] == k_)
                with p1_map_env(mm):
                    used = {p1_rsenv.fnv(ln.split(" ", 1)[1]) for ln in p1_blocks(mm) if ln.startswith("render-settings ")}
                (rg, _g), = p1_rsenv.read_pak_regions(open(os.path.join(stage, "pak68", p1_rs(mm) + "-ingame.pak"), "rb").read())
                used |= {p1_rsenv.fnv(p1_rsenv.region_rs(r)) for r in rg if p1_rsenv.region_rs(r)}
                assert s_ not in used, (f"{k_}: render-settings symbol {s_:#x} differs from an earlier Part I map's and {k_} uses it - "
                                        f"add it to tools/part1/data/p1_maps/{k_}.json rs_renames")
    syms = [ln.split(" ", 1)[1] for ln in p1_blocks(m) if ln.startswith("render-settings ")]
    modules = os.path.join(stage, "bin", "dc1", "modules.bin")
    data = bytearray(open(modules, "rb").read())
    old = dc_modules.set_size(data, RS_MODULE, os.path.getsize(dst))
    open(modules, "wb").write(data)
    n0, n1 = add_exports(modules, syms, module=RS_MODULE)
    print(f"sp map {m['key']}: Part I render settings {rs}-ingame.pak + {RS_MODULE}.bin ({old} -> {os.path.getsize(dst)} bytes, "
          f"exports {n0} -> {n1})")
    luts = _p1_stage().lut_files(P1_CONV)
    if luts:        # Part I colour grading: the LUT filename table (render-settings.bin) gets the Part I LUT stems, else the lut-texture-file sid binds nothing (p1_lut.py)
        import p1_lut
        rsb = os.path.join(stage, "bin", "dc1", "render-settings.bin")
        raw = open(rsb if os.path.exists(rsb) else os.path.join(_MAIN, "re", "gamebin", "dc1", "render-settings.bin"), "rb").read()
        new, added = p1_lut.add_entries(raw, luts)
        bad = p1_lut.verify(new, luts)
        assert not bad, f"LUT filename table: {bad[:3]}"
        os.makedirs(os.path.dirname(rsb), exist_ok=True)
        open(rsb, "wb").write(new)
        # lut0/files.json = the engine's LUT list: the Part I names appended (a table name the list lacks is never loaded), then the staged-file checks
        stock_fj = open(os.path.join(_MAIN, "re", "gamebin", "lut0", "files.json"), "rb").read()
        fj = p1_lut.add_files_json(stock_fj, luts)
        os.makedirs(os.path.join(stage, "lut0"), exist_ok=True)
        open(os.path.join(stage, "lut0", "files.json"), "wb").write(fj)
        bad = p1_lut.verify_files(fj, stage, luts)
        assert not bad, f"staged Part I LUTs: {bad[:3]}"
        if added:
            data = bytearray(open(modules, "rb").read())
            o2 = dc_modules.set_size(data, "render-settings", len(new))
            open(modules, "wb").write(data)
            print(f"sp map {m['key']}: Part I LUT filename table: +{', '.join(added)} (render-settings.bin {o2} -> {len(new)} bytes)")


def scaled_props_of(m):
    """(the map's props with every scaled prop's art swapped for its baked copy (tools/maps/scaled_props.py: the game ignores spawner Scale), {copy: (art, scale)})"""
    import sys
    sys.path.insert(0, os.path.join(HERE, "..", "maps"))
    import scaled_props
    if not m.get("bake_scaled"):                       # opt-in per map (jackson-market): the other maps keep their committed spawner paks with stock art + Scale
        return m.get("props", []), {}
    return scaled_props.map_props(m.get("props", []))


def stage_scaled(stage, maps):
    """actor97/<copy>.pak of every baked scaled prop; -> manifest paths"""
    import sys
    sys.path.insert(0, os.path.join(HERE, "..", "maps"))
    import scaled_props
    bakes = {}
    for m in maps:
        bakes.update(scaled_props_of(m)[1])
    return scaled_props.stage(stage, bakes) if bakes else []


@_per_map(0)
def prop_actors(m):
    out = []
    for p in scaled_props_of(m)[0]:
        if p["art"] not in out:
            out.append(p["art"])
    if m.get("prefabs"):                          # placed vehicle presets (tools/maps/vehicle_presets.py): their actors load like any prop
        sys_path = os.path.join(HERE, "..", "maps")
        if sys_path not in sys.path:
            sys.path.insert(0, sys_path)
        import vehicle_presets
        out += [a for a in vehicle_presets.prefab_actors(m) if a not in out]
    if m.get("part1", {}).get("spawner-arts"):      # The grafted Part I prop spawners need their actor paks in our block (like light-skel)
        sys.path.insert(0, os.path.join(os.path.dirname(HERE), "part1"))
        import p1_fires
        out += [a for a in p1_fires.actor_names(m, P1_CONV) if a not in out]
    return out


@_per_map(0)
def p1_actor_files(m):
    """mod-relative paths of the map's converted Part I actor paks (actor97/<name>.pak): Part I MAP data like the level paks (the release build / zips leave
    them out with the Part I maps; build_dll adds them to the A/B manifest); [] without them"""
    sys.path.insert(0, os.path.join(os.path.dirname(HERE), "part1"))
    import p1_fires
    if not m.get("part1", {}).get("spawner-arts"):
        return []
    return [f"actor97/{a}.pak" for a in p1_fires.actor_names(m, P1_CONV) if os.path.exists(os.path.join(P1_CONV, "actors", a + ".pak"))]      # (the TLOU2-resident arts are only registered)


p1_actor_collision_checked = []


def stage_p1_actors(stage, maps):
    """The Part I actor paks converted by tools/part1/p1_actors.py (<conv>/actors/<name>.pak) as actor97/<name>.pak. They are Part I map files:
    NOT returned as edit paks (build_dll adds p1_actor_files to the manifest next to the Part I levels, so a release build can drop them)"""
    n = size = 0
    for m in maps:
        with p1_map_env(m):
            n += _p1_stage().stage_actors(stage, m, P1_CONV, p1_actor_files(m))
            size += sum(os.path.getsize(os.path.join(stage, p)) for p in p1_actor_files(m))
    F = p1_fires_mod()
    have = t2_actor_paks()
    import struct
    for m in maps:
        with p1_map_env(m):
            if F.converted_actors_on():
                continue
            # INTERACTIVE_BG_1 items by the pak's ITEM LIST (a byte search for the type id also hits the dead header the converter leaves when it drops the item)
            for lv in p1_levels(m):
                f = os.path.join(stage, "pak68", lv + ".pak")
                if not os.path.exists(f):
                    continue
                d = open(f, "rb").read()
                h = F._hdr(d)
                pages = [struct.unpack_from("<III", d, h[5] + 12 * i) for i in range(h[4])]
                if any(t == "INTERACTIVE_BG_1" for _, _, t in F._items(d, pages)):
                    msg = (f"{lv}.pak carries an INTERACTIVE_BG_1 item ({os.path.basename(P1_CONV)}) but the converted Part I actors are not staged (T2R_P1_ACTORS_CONVERTED=0: their Havok 2020.1 "
                           f"collision is untranslated, re/part1/bookstore_missing_objects_1105.md s10). What the item needs from actor paks is not proven: build from a conv dir without "
                           f"the item (conv-abi-mix4), or set T2R_P1_IBG=1 to test it with the TLOU2-resident ivy actors only")
                    assert os.environ.get("T2R_P1_IBG") == "1", f"{m['key']}: {msg}"
                    print(f"sp maps: WARNING (T2R_P1_IBG=1) {lv}: {msg[:90]}")
    for m in maps:      # night69 crash guard: every art of a grafted Part I spawner must resolve to an actor pak (stock TLOU2 or staged here), and a staged one must carry TLOU2's Havok 2017.1 collision
        with p1_map_env(m):
            if not m.get("part1", {}).get("spawner-arts"):
                continue
            for art in F.spawner_arts(m, P1_CONV):
                name = F.actor_file(m, art)
                assert name in have or os.path.exists(os.path.join(stage, "actor97", name + ".pak")),                 f"{m['key']}: grafted Part I spawner art {art!r} -> actor {name!r} is neither a stock TLOU2 actor pak nor staged (night69: unresolved actor = engine assert)"
            for p in p1_actor_files(m):
                d = open(os.path.join(stage, p), "rb").read()
                assert b"SDKV20200100" not in d, f"{p}: still carries Part I's Havok 2020.1 collision tagfile (TLOU2 reads 2017.1: engine assert, night69 exe+1c31515)"
                p1_actor_collision_checked.append(p)
    if n:
        print(f"sp maps: {n} Part I actor paks staged ({size / 1e6:.1f} MB uncompressed)")


def stage_prop_lod(stage, maps):
    """patched copies of the vehicle actor paks the maps' props use (tools/maps/prop_lod.py: LOD1 / LOD2 start at the cull distance, so
    the full body shows at every distance).  T2R_PROP_LOD=0 = ship the stock actors.  -> ["actor97/<art>.pak", ...]"""
    if os.environ.get("T2R_PROP_LOD", "") == "0":
        return []
    import sys
    sys.path.insert(0, os.path.join(HERE, "..", "maps"))
    import prop_lod
    used = [a for a in prop_lod.ARTS if any(a in prop_actors(m) for m in maps)]
    return prop_lod.stage(stage, used) if used else []


# Slots vs fresh level-set entries: see SLOT_POOL / allocate() below (T2R_SP_POOL, T2R_SP_NEW_SETS).
# Edges of the new subnodes in the to1-levels adjacency list (A/B: with T2R_SP_MAPS=all the engine reported the new subnodes -
# Downtown, Jackson, Lodge, Outpost, Train Station - ALL active at once and NONE of the stock ones: "end" edges only (new -> %end)
# leave every new subnode without a predecessor = a root of the graph, and roots come up active; Hardware, chained after the stock
# chain, was the only SP map in its build and worked):
#   chain (DEFAULT): stock tail -> new1 -> new2 -> ... -> %end = the stock layout (one linear chain, every node ONE
#          successor). Playing a subnode activates the successors of its predecessor = only itself (stock: playing to1-forest
#          activates resort's successors = forest alone). 709932f's "playing one map reached its successor" came with the
#          clones' duplicate task id (+0x28, fixed in e2cc071), not with the chain.
#   branch: every new subnode is its own branch off the stock tail: tail -> new_i and new_i -> %end (the stock tail -> %end stays).
#          BROKEN for several maps (A/B, build T2R_SP_MAPS=into-the-city,wilds-houses,p1-bookstore): the stock tail's
#          out-edges are PARALLEL branches - playing any one SP map left ALL FOUR new subnodes active (load diag: "ACTIVE subnode
#          to1-train-station / to1-p1-bookstore / to1-wilds-houses / to1-into-the-city ... 4 active"), so all four level sets were
#          requested at once; the level streamer loaded and dropped levels in a loop (L/S flags flapping, levels-fully-spawned never
#          1): void world, no collision, the player falling to the SP death screen, a half-loaded Ellie fallback body. With 2-3
#          small maps it happened to fit (Train Station + Bookstore, + Hillside + Into the City); Bookstore's
#          383 MB of Part I paks on top of Into the City did not. Kept only as a bisect mode.
#   self:  new -> new and new -> %end: one incoming edge (its own) so it is no root, and no other subnode follows it (untested)
#   end:   new -> %end only (beb55be .. 28f502b): every new subnode is a root = active at once
EDGES = "chain" if (LEGACY or os.environ.get("T2R_SP_CHAIN", "") == "1") else os.environ.get("T2R_SP_EDGES", "chain")
assert EDGES in ("branch", "self", "chain", "end"), "T2R_SP_EDGES: branch | self | chain | end"
CHAIN = EDGES == "chain"
# ---------------------------------------------------------------- level-set slots (re/maps/technical.md section 5k)
# A map's task subnode names ONE level set, found by sid in level-sets-test.bin (the only level-set module the mod ships). Two maps
# of one build can't share a set. Where a map's set comes from:
#   1. a SLOT = a leftover dev set already in the mod's level-sets-test.bin (each referenced only by a dead 'pf' mission task):
#      only its arrays pointer is repointed at our level list (entry row, sid, export, struct untouched) - the Hospital / Hardware /
#      Train Station / Hillside way, proven in game. There are exactly SEVEN (SLOT_POOL); the other 15 sets of the file are the to1
#      maps, the Hospital, the menu scenes (sl), the 'pf' menu sets and the to1-all / pf-all part sets: none of them is free.
#   2. a FRESH entry tsk-to1-<key>-1 = a new level-set struct + entry-table row + modules.bin export (no limit). It hung the
#      load; that build was malformed: a level set is 0x30 bytes (invariant of all 2232 game sets: +0x18 array {ptr =
#      struct end, u32 n, u32 -1}, +0x28 u32 -1) but only 0x28 were copied, so +0x28 held whatever was appended next ("tsk-pf-m"
#      of the string region in the 1-map build) and +0x18 pointed into the template. Fixed in patch_level_sets; still to be
#      confirmed in game (one map per build: T2R_SP_POOL=0 T2R_SP_MAPS=<key>).
# The ALLOCATOR (allocate()) hands slots out PER BUILD: each selected map gets its preferred slot (the one it was built / A/B-tested
# with) when that is free, then the next free slot of the pool; only a build with more than seven SP maps gets fresh entries for the
# rest. Slot names never leave the DLL (server, vote and ext use the subnode / level name to1-<key>), so a map may hold another slot
# in another build. Retired maps ("retired": true in sp_maps.json, e.g. Lodge) are never built and hold nothing.
#   T2R_SP_POOL=<n>   only the first n slots of the pool (0 = a fresh entry for every map: the in-game test of fresh entries)
#   T2R_SP_NEW_SETS=1 / T2R_SP_REUSE_SLOTS=0  = T2R_SP_POOL=0
SLOT_POOL = ["tsk-pf-mission-forest-golden-gun-1", "tsk-fedra-base-fob", "tsk-pf-mission-seattle-collect-keycards-1",
             "tsk-pf-mission-jackson-fix-gate-1", "tsk-pf-mission-dark-forest-scar-loot-1",
             "tsk-pf-mission-general-store-supply-cache-1", "tsk-pf-mission-undercover-scar-1"]
# never slots: the mod's own tasks / part sets use them (the first all-maps run loaded the pf menu sets)
NOT_SLOTS = {"tsk-pf-main-menu-1", "pf-all", "ls-dialogue-reviewer", "to1-all", "tsk-sl-main-menu-1", "tsk-sl-t2-main-menu",
             "tsk-pf-mission-nor-hospital-generators-1", "tsk-to1-main-menu"}
# the slot each map was built / tested with so far (kept when free, so a proven map's build stays byte-identical)
PREFERRED = {"train-station": "tsk-pf-mission-forest-golden-gun-1", "hardware": "tsk-pf-mission-forest-golden-gun-1",
             "wilds-houses": "tsk-fedra-base-fob", "capitol-shops": "tsk-pf-mission-seattle-collect-keycards-1",
             "p1-bookstore": "tsk-pf-mission-jackson-fix-gate-1", "downtown": "tsk-pf-mission-dark-forest-scar-loot-1",
             "jackson-suburbs": "tsk-pf-mission-general-store-supply-cache-1", "outpost": "tsk-pf-mission-undercover-scar-1"}
# stock map (task subnode) -> the level set its subnode already loads (patch_hospital_map); a replacing map rewrites that set's level list
# (arrays pointer, like a slot) and adds no subnode, so the Hospital keeps its name, index 4, thumbnail and max team
REPLACE_SETS = {"to1-custom-map-1": "tsk-pf-mission-nor-hospital-generators-1"}
_POOL_ENV = os.environ.get("T2R_SP_POOL", "").strip()
if (os.environ.get("T2R_SP_NEW_SETS", "") == "1" or os.environ.get("T2R_SP_REUSE_SLOTS", "") == "0") and not LEGACY:
    POOL_SIZE = 0
else:
    POOL_SIZE = max(0, min(len(SLOT_POOL), int(_POOL_ENV))) if _POOL_ENV and not LEGACY else len(SLOT_POOL)
REUSE_SLOTS = POOL_SIZE > 0                 # (old name)
_ALLOC = {}                                 # key -> level-set name in the current build (allocate())


def allocate(maps, pool_size=None, remember=True):
    """{key: level-set name} for one build's selection: the preferred slot if free, then the next free pool slot, then a fresh
    entry tsk-to1-<key>-1. Deterministic. remember: set_name() / slotted() answer from it."""
    pool = SLOT_POOL[:POOL_SIZE if pool_size is None else pool_size]
    assert not set(SLOT_POOL) & NOT_SLOTS
    out, used = {}, set()
    for m in maps:                                         # pass 0: a map that REPLACES a stock map reuses that map's own level set
        if m.get("replaces"):
            out[m["key"]] = REPLACE_SETS[m["replaces"]]
    for m in maps:                                         # pass 1: proven assignments
        p = PREFERRED.get(m["key"])
        if p in pool and p not in used:
            out[m["key"]] = p
            used.add(p)
    for m in maps:                                         # pass 2: the rest of the pool, then fresh entries
        if m["key"] not in out:
            free = [s for s in pool if s not in used]
            out[m["key"]] = free[0] if free else f"tsk-to1-{m['key']}-1"
            used.add(out[m["key"]])
    if remember:
        _ALLOC.clear()
        _ALLOC.update(out)
    return out


def set_name(m):
    """the level set this map's subnode loads in the current build (allocate(); a map outside it is allocated alone)"""
    return _ALLOC.get(m["key"]) or allocate([m], remember=False)[m["key"]]


def slotted(m):
    """this map takes over a leftover level set (else it gets its own fresh entry)"""
    return set_name(m) in SLOT_POOL or bool(m.get("replaces"))


MODULE = "level-sets/level-sets-test"


def _insert_entries(f, new):
    """Add entry-table rows {sid, level-set tag, ptr} for new [(name, struct offset)] (table sorted by sid at
    header +0x18, count u32 at +0x14); everything after the table moves (as dc_data_patches._insert_look_rows)."""
    n_ent = struct.unpack_from("<I", f.data, 0x14)[0]
    ent = f.q(0x18)
    rows = [struct.unpack_from("<QQQ", f.data, ent + 24 * i) for i in range(n_ent)]
    tag = rows[0][1]
    add = len(new) * 24
    tab_end = ent + 24 * n_ent
    rows += [(fnv(nm), tag, o) for nm, o in new]
    rows.sort()
    assert len({r[0] for r in rows}) == len(rows), "level-set name collides with an existing entry"
    for i in range(0, len(f.data), 8):
        if f.is_ptr(i) and f.q(i) >= tab_end:
            f.set_q(i, f.q(i) + add)
    old_ptrs = [i for i in range(tab_end, len(f.data), 8) if f.is_ptr(i)]
    for i in range(tab_end, len(f.bits) * 64, 8):
        if f.is_ptr(i):
            f.bits[(i // 8) // 8] &= ~(1 << ((i // 8) % 8))
    table = b"".join(struct.pack("<QQQ", s, t, p + add if p >= tab_end else p) for s, t, p in rows)
    f.data[ent:tab_end] = table
    for i in old_ptrs:
        f._mark(i + add)
    for k in range(len(rows)):
        f._mark(ent + 24 * k + 16)
    f.strings += add
    struct.pack_into("<I", f.data, 0x14, len(rows))


def add_exports(modules_path, names, module=MODULE):
    """modules.bin: the module's export list (sorted sids) gets the new level-set names."""
    m = DcFile(open(modules_path, "rb").read())
    key = struct.pack("<Q", fnv(module))
    e = m.data.find(key) - 8
    assert e > 0 and m.is_ptr(e) and m.is_ptr(e + 32), f"modules.bin entry of {module}"
    sa = m.q(e + 32)
    n_exp, d_exp = m.q(sa), m.q(sa + 8)
    sids = [m.q(d_exp + 8 * k) for k in range(n_exp)]
    assert sids == sorted(sids), f"{module} exports not sorted"
    sids = sorted(set(sids) | {fnv(nm) for nm in names})
    tag = m.q(d_exp - 8)
    na = m.append(struct.pack("<Q", tag) + b"".join(struct.pack("<Q", s) for s in sids)) + 8
    sa = m.q(e + 32)
    m.set_q(sa, len(sids))
    m.set_ptr(sa + 8, na)
    open(modules_path, "wb").write(m.save())
    return n_exp, len(sids)


# ------------------------------------------------------------------ level-sets-test.bin
def patch_level_sets(path, maps):
    f = DcFile(open(path, "rb").read())
    ent = _entries(f)
    tmpl = ent[fnv(TEMPLATE_SET)]
    assert _cstr(f, f.q(tmpl)) == TEMPLATE_SET
    marr = f.q(tmpl + 0x10)
    names = []                                   # (entry offset, name): strings go last
    new_sets = []
    for m in maps:
        if slotted(m):
            assert fnv(set_name(m)) in ent, f"slot {set_name(m)} not in level-sets-test.bin"
        else:
            assert fnv(set_name(m)) not in ent, f"{set_name(m)} already in level-sets-test.bin"
        lst = []
        for lv in m["levels"]:
            e = f.append(struct.pack("<QQII", 0, fnv(lv), 3, 7), ptr_slots=(0,), tag="level-entry")
            lst.append(e)
            names.append((e, lv))
        lo = f.append(struct.pack(f"<{len(lst)}Q", *lst), ptr_slots=tuple(range(0, 8 * len(lst), 8)))
        acts = []
        for a in (prop_actors(m) if LEVEL_SET_ACTORS else []):
            e = f.append(struct.pack("<QQQ", ACTOR_ENTRY_TAG, 0, fnv(a)), ptr_slots=(8,)) + 8
            acts.append(e)
            names.append((e, a))
        blob, slots = f.copy_block(marr, 0x70)
        blob = bytearray(blob)
        struct.pack_into("<QI", blob, 0x00, lo, len(lst))            # list 0: levels
        if acts:                                                     # list 2: actors
            ao = f.append(struct.pack(f"<{len(acts)}Q", *acts), ptr_slots=tuple(range(0, 8 * len(acts), 8)))
            struct.pack_into("<QI", blob, 0x20, ao, len(acts))
        else:
            struct.pack_into("<I", blob, 0x28, 0)
        arr = f.append(bytes(blob), ptr_slots=slots, tag="level-set-arrays")
        if slotted(m):                                 # the leftover set keeps its entry / name / sid: only its arrays pointer moves
            slot = ent[fnv(set_name(m))]
            f.set_ptr(slot + 0x10, arr)
            continue
        # the level set itself, LEVEL_SET_SIZE (0x30) bytes like every stock set: +0 name, +8 sid, +0x10 arrays,
        # +0x18 empty array {ptr = the struct's own end, u32 0, u32 -1}, +0x28 u32 -1 (+ pad). (Earlier only 0x28 bytes were
        # copied: +0x28 read the next appended bytes and +0x18 pointed into tsk-to1-forest-1.)
        sb = bytearray(LEVEL_SET_SIZE)
        struct.pack_into("<QQQQIIQ", sb, 0, 0, fnv(set_name(m)), 0, 0, 0, 0xFFFFFFFF, 0xFFFFFFFF)
        st = f.append(bytes(sb), ptr_slots=(0, 0x10, 0x18), tag="level-set")
        f.set_ptr(st + 0x10, arr)
        names.append((st, set_name(m)))
        new_sets.append((set_name(m), st))
    for _, st in new_sets:                       # +0x18 -> the struct's end, as stock (set after every append(): a pointer equal to
        f.set_ptr(st + 0x18, st + LEVEL_SET_SIZE)    # the string-region start would be shifted along with the strings)
    for e, name in names:                        # after every append(): nothing moves them now
        f.set_ptr(e, len(f.data))
        f.data += name.encode() + b"\0"
    f.data += bytes((-len(f.data)) % 8)
    if new_sets:
        _insert_entries(f, new_sets)             # entry rows (sid-sorted); moves everything after the table
    out = f.save()
    open(path, "wb").write(out)
    return len(out)


# ------------------------------------------------------------------ test-tasks.bin
def _find_named(f, name):
    """offset of the struct whose [0] = ptr to `name` and [8] = fnv(name)"""
    key = struct.pack("<Q", fnv(name))
    i = f.data.find(key)
    while i >= 8:
        if f.is_ptr(i - 8) and f.q(i - 8) < len(f.data) and _cstr(f, f.q(i - 8)) == name:
            return i - 8
        i = f.data.find(key, i + 1)
    raise AssertionError(f"{name} not found")


def node_map(f):
    node = _find_named(f, NODE)
    mp, adj = f.q(node + 0x20), f.q(node + 0x28)
    n = struct.unpack_from("<I", f.data, mp)[0]
    keys = [f.q(f.q(mp + 8) + 8 * i) for i in range(n)]
    vals = [f.q(f.q(mp + 0x10) + 8 * i) for i in range(n)]
    return node, mp, adj, keys, vals


def patch_tasks(path, maps):
    f = DcFile(open(path, "rb").read())
    node, mp, adj, keys, vals = node_map(f)
    assert keys == sorted(keys), "to1-levels keys not sorted"
    have = dict(zip(keys, vals))
    tv = have[fnv(TEMPLATE_SUB)]
    assert _cstr(f, f.q(tv)) == TEMPLATE_SUB
    src = tv - 8                                 # the subnode's type tag + the subnode
    names, new = [], []
    if LEGACY:
        blob0, slots0 = f.copy_block(src, SUB_SIZE + 8)        # 114324d: ONE copy for all clones
    for m in maps:
        if m.get("replaces"):                    # the stock subnode stays (name, sid, task id, edges); its level set's list is rewritten
            sub = have[fnv(m["replaces"])]
            assert _cstr(f, f.q(sub + 0x140)) == set_name(m) and f.q(f.q(sub + 0xB8)) == fnv(set_name(m)),                 f"{m['replaces']} does not load {set_name(m)} (patch_hospital_map first)"
            continue
        sid = fnv(m["level"])
        assert sid not in have, f"{m['level']} already a subnode of {NODE}"
        # copied AFTER the previous append: its pointers into the (moving) string region must be current.
        # (one copy for all clones left +0x1A8 / +0x3B8 of clones 2.. pointing at stale offsets.)
        blob, slots = (blob0, slots0) if LEGACY else f.copy_block(src, SUB_SIZE + 8)
        blob = bytearray(blob)
        inner = {}
        for sl in slots:
            t = struct.unpack_from("<Q", blob, sl)[0]
            if src <= t < src + SUB_SIZE + 8:
                inner[sl] = t - src
                struct.pack_into("<Q", blob, sl, 0)          # set after the append (append shifts >= strings)
        at = f.append(bytes(blob), ptr_slots=slots)
        for sl, rel in inner.items():
            f.set_q(at + sl, at + rel)
        sub = at + 8
        f.set_q(sub + 0x08, sid)
        # +0x28 = the task's global id, fnv("<node>-<subnode>") (to1-levels-to1-forest etc.; checked on every stock
        # subnode). The clones had kept custom-map-1's id -> 8 tasks with one id: the engine resolved the wrong
        # one (Downtown for Train Station, then a hang at match state 3).
        if not LEGACY:
            f.set_q(sub + 0x28, fnv(f"{NODE}-{m['level']}"))
        names.append((sub + 0x00, m["level"]))
        names.append((sub + 0x140, set_name(m)))
        arrd = f.q(sub + 0xB8)
        assert at <= arrd < at + SUB_SIZE + 8, "level-set sid array not inside the copied subnode"
        f.set_q(arrd, fnv(set_name(m)))                     # the level set the task loads (by sid)
        new.append((sid, sub))
    pairs = sorted(list(zip(keys, vals)) + new)
    n = len(pairs)
    ko = f.append(struct.pack(f"<{n}Q", *[k for k, _ in pairs]), tag="array")
    vo = f.append(struct.pack(f"<{n}Q", *[v for _, v in pairs]), ptr_slots=tuple(range(0, 8 * n, 8)), tag="array")
    _, mp, adj, _, _ = node_map(f)               # (offsets before the strings don't move, re-read anyway)
    struct.pack_into("<I", f.data, mp, n)
    f.set_ptr(mp + 8, ko)
    f.set_ptr(mp + 0x10, vo)
    # adjacency (EDGES above): default chain = the stock layout, stock tail -> new1 -> ... -> %end, every node exactly one
    # successor. NOT branch: several out-edges of one node are parallel branches, all of them active at once (A/B).
    cnt = struct.unpack_from("<I", f.data, adj)[0]
    d = f.q(adj + 8)
    edges = [(f.q(d + 16 * i), f.q(d + 16 * i + 8)) for i in range(cnt)]
    end = fnv("%end")
    if CHAIN:       # default: the new subnodes chained after the last stock one (709932f's layout, with unique task ids now)
        tail = [i for i, (a, b) in enumerate(edges) if b == end]
        assert len(tail) == 1, "stock chain has one tail edge"
        last = edges[tail[0]][0]
        chain = [last] + [sid for sid, _ in new] + [end]
        edges[tail[0]:tail[0] + 1] = [(chain[i], chain[i + 1]) for i in range(len(chain) - 1)]
    elif EDGES == "branch":
        tail = [i for i, (a, b) in enumerate(edges) if b == end]
        assert len(tail) == 1, "stock chain has one tail edge"
        last = edges[tail[0]][0]
        for sid, _ in new:
            edges += [(last, sid), (sid, end)]
    elif EDGES == "self":
        for sid, _ in new:
            edges += [(sid, sid), (sid, end)]
    else:
        edges += [(s, end) for s, _ in new]
    eo = f.append(b"".join(struct.pack("<QQ", a, b) for a, b in edges), tag="array")
    struct.pack_into("<I", f.data, adj, len(edges))
    f.set_ptr(adj + 8, eo)
    for o, name in names:
        f.set_ptr(o, len(f.data))
        f.data += name.encode() + b"\0"
    f.data += bytes((-len(f.data)) % 8)
    out = f.save()
    open(path, "wb").write(out)
    return len(out)


# ------------------------------------------------------------------ pak68.txt
def patch_registry(path, maps):
    lines = open(path, encoding="latin1").read().split("\n")
    while lines and not lines[-1]:
        lines.pop()
    for m in maps:
        with p1_map_env(m):
            p = m["pak"]
            if f"level-name {p}" in lines:          # rebuilt block (props may have changed)
                i = lines.index(f"level-name {p}")
                j = i + 1
                while j < len(lines) and not lines[j].startswith("level-name "):
                    j += 1
                del lines[i:j]
            lines += [f"level-name {p}", f"level-id {p}", f"package {p}-ingame"] + [f"actor {a}" for a in prop_actors(m)]
            if m.get("part1", {}).get("fires"):     # The fires' sound level (p1_firesfx): drop a stale block, append ours (its bank loads with this map only)
                fx = _p1_firesfx()
                if f"level-name {fx.level_name(m)}" in lines:
                    i = lines.index(f"level-name {fx.level_name(m)}")
                    j = i + 1
                    while j < len(lines) and not lines[j].startswith("level-name "):
                        j += 1
                    del lines[i:j]
                if fx.sfx_fires(m):
                    lines += fx.registry(m)
            if p1_levels(m):                        # Part I levels: drop stale blocks, append ours
                for lv in p1_levels(m) + ([p1_rs(m)] if p1_rs(m) else []) + (_p1_audio().levels_of(m) if m.get("part1", {}).get("audio") else []) + _p1_particles().levels(m):
                    if f"level-name {lv}" in lines:
                        i = lines.index(f"level-name {lv}")
                        j = i + 1
                        while j < len(lines) and not lines[j].startswith("level-name "):
                            j += 1
                        del lines[i:j]
                lines += p1_blocks(m)
                lines += _p1_particles().registry(m)       # Part I fire particles: package <part level> + particle-module <carrier>
    # Part I ambience: every Part I map's audio set uses the same two levels (hun-const-audio + -rgn) with its own bank list; one block per
    # level pair carries the union of the banks of every map of the build (each map's stale-block pass above already dropped old blocks)
    lines += p1_audio_registry(maps)
    open(path, "w", encoding="latin1", newline="\n").write("\n".join(lines) + "\n")


def p1_audio_registry(maps):
    """pak68.txt blocks of the Part I ambience levels: per (level, region-level) pair one block (p1_audio.registry_lines) with the union of the
    banks of every map that uses it, in build order (the 3 carrier DC modules and the 235 shared files are byte-identical between Bookstore and Plaza)"""
    A, pairs = _p1_audio(), {}
    for m in maps:
        s = m.get("part1", {}).get("audio")
        if not s:
            continue
        with p1_map_env(m):
            man = A.load_manifest()
        _spec, shipped, left = pairs.setdefault((s["level"], s["region-level"]), (s, [], []))
        shipped += [b for b in man["banks"] if b not in shipped]
        left += [b for b in man["banks-tlou2"] if b not in left]
    out = []
    for spec, shipped, left in pairs.values():
        out += A.registry_lines(spec, shipped, [b for b in left if b not in shipped])
    return out


# ------------------------------------------------------------------ verify (read back)
def level_set_struct_ok(f, s):
    """the stock level-set layout (all 2232 sets of the game's level-sets-*.bin): tag before it, name / sid, +0x10 arrays and
    +0x18 array pointer relocated, +0x18 -> the struct's end, +0x20 = {u32 n, u32 -1}, +0x28 = u32 -1 + pad"""
    return (f.q(s - 8) == fnv("level-set") and f.is_ptr(s) and fnv(_cstr(f, f.q(s))) == f.q(s + 8)
            and f.is_ptr(s + 0x10) and f.is_ptr(s + 0x18) and f.q(s + 0x18) == s + LEVEL_SET_SIZE
            and f.q(s + 0x20) >> 32 == 0xFFFFFFFF and f.q(s + 0x28) == 0xFFFFFFFF and not f.is_ptr(s + 0x28))


def verify(stage, maps):
    tt = DcFile(open(os.path.join(stage, "bin", "dc1", "test-tasks.bin"), "rb").read())
    _, _, adj, keys, vals = node_map(tt)
    assert keys == sorted(keys)
    by = dict(zip(keys, vals))
    ls = DcFile(open(os.path.join(stage, "bin", "dc1", "level-sets", "level-sets-test.bin"), "rb").read())
    ent = _entries(ls)
    cnt = struct.unpack_from("<I", tt.data, adj)[0]
    d = tt.q(adj + 8)
    chain = [tt.q(d + 16 * i + 8) for i in range(cnt)]
    for m in maps:
        sub = by[fnv(m["level"])]
        assert _cstr(tt, tt.q(sub)) == m["level"] and tt.q(sub + 8) == fnv(m["level"])
        assert _cstr(tt, tt.q(sub + 0x140)) == set_name(m) and tt.q(tt.q(sub + 0xB8)) == fnv(set_name(m))
        inc = [tt.q(d + 16 * i) for i in range(cnt) if tt.q(d + 16 * i + 8) == tt.q(sub + 8)]      # who points at this subnode
        tails = [tt.q(d + 16 * i) for i in range(cnt) if tt.q(d + 16 * i + 8) == fnv("%end")]
        stock_tail = [t for t in tails if t not in {fnv(x["level"]) for x in maps}]
        assert CHAIN or EDGES == "branch" or set(inc) <= {tt.q(sub + 8)}, "new subnode is somebody else's successor"
        assert EDGES != "self" or inc == [tt.q(sub + 8)], "self mode: exactly one incoming edge, its own"
        assert EDGES != "branch" or (len(stock_tail) == 1 and inc == [stock_tail[0]]), "branch mode: exactly one incoming edge, from the stock tail"
        outs = [tt.q(d + 16 * i + 8) for i in range(cnt) if tt.q(d + 16 * i) == tt.q(sub + 8)]
        assert EDGES not in ("branch", "end") or outs == [fnv("%end")], "branch / end mode: the only successor is %end"
        assert tt.q(sub + 0xF8) > sub and tt.is_ptr(sub + 0xF8), "task-manager-info pointer"
        assert CHAIN or (fnv(m["level"]), fnv("%end")) in [(tt.q(d + 16 * i), tt.q(d + 16 * i + 8)) for i in range(cnt)], "adjacency"
        assert not CHAIN or (len(inc) == 1 and len(outs) == 1), "chain mode: exactly one predecessor and one successor"
        s = ent[fnv(set_name(m))]
        assert _cstr(ls, ls.q(s)) == set_name(m)
        assert level_set_struct_ok(ls, s), (m["key"], set_name(m), "level-set struct differs from the stock layout")
        arr = ls.q(s + 0x10)
        lv = [_cstr(ls, ls.q(ls.q(ls.q(arr) + 8 * i))) for i in range(struct.unpack_from("<I", ls.data, arr + 8)[0])]
        assert lv == m["levels"], (m["key"], lv)
        na = struct.unpack_from("<I", ls.data, arr + 0x28)[0]
        acts = [_cstr(ls, ls.q(ls.q(ls.q(arr + 0x20) + 8 * i))) for i in range(na)]
        assert acts == (prop_actors(m) if LEVEL_SET_ACTORS else []), (m["key"], acts)
        pc = [ls.q(ls.q(ls.q(arr + 0x50) + 8 * i)) for i in range(struct.unpack_from("<I", ls.data, arr + 0x58)[0])]
        assert pc == [fnv("to1-all")], (m["key"], "part set")
    # the existing subnodes still resolve; every subnode's task id (+0x28) is fnv("<node>-<name>") and unique;
    # the clones' string pointers read the same strings as the template's (no stale offsets)
    tmpl = by[fnv(TEMPLATE_SUB)]
    if LEGACY:
        return _verify_registry(stage, maps)
    if EDGES != "branch":                        # stock invariant: no node of to1-levels has two successors (= parallel branches,
        srcs = [tt.q(d + 16 * i) for i in range(cnt)]    # all active together: the void-world bug)
        assert len(srcs) == len(set(srcs)), "to1-levels: a node with several out-edges (parallel branches)"
        assert chain.count(fnv("%end")) == 1, "to1-levels: one tail edge"
    ids = []
    for k, v in by.items():
        assert tt.q(v + 8) == k, hex(k)
        name = _cstr(tt, tt.q(v))
        assert tt.q(v + 0x28) == fnv(f"{NODE}-{name}"), f"{name}: task id"
        ids.append(tt.q(v + 0x28))
    assert len(set(ids)) == len(ids), "duplicate task ids"
    for m in maps:
        v = by[fnv(m["level"])]
        for off in range(0, SUB_SIZE, 8):
            if off in (0x0, 0x140) or not tt.is_ptr(v + off):
                continue
            p, q = tt.q(v + off), tt.q(tmpl + off)
            if tmpl - 8 <= q < tmpl + SUB_SIZE:
                assert p - v == q - tmpl, f"{m['level']} +{off:#x}: inner pointer"
            else:
                assert _cstr(tt, p) == _cstr(tt, q), f"{m['level']} +{off:#x}: '{_cstr(tt, p)}' != '{_cstr(tt, q)}'"
    _verify_registry(stage, maps)


def _verify_registry(stage, maps):
    reg = open(os.path.join(stage, "pak68.txt"), encoding="latin1").read().split("\n")
    for m in maps:
        with p1_map_env(m):
            assert f"level-name {m['pak']}" in reg and f"package {m['pak']}-ingame" in reg
            assert os.path.exists(os.path.join(stage, "pak68", m["pak"] + "-ingame.pak")), f"{m['pak']}-ingame.pak not staged"
            for lv in p1_levels(m):
                assert os.path.exists(os.path.join(stage, "pak68", lv + ".pak")) and f"level-name {lv}" in reg, f"Part I level {lv} not staged / registered"
            if m.get("part1", {}).get("audio"):
                P = _p1_audio()
                for lv in P.levels_of(m):
                    assert os.path.exists(os.path.join(stage, "pak68", lv + "-ingame.pak")) and f"level-name {lv}" in reg and f"package {lv}-ingame" in reg, f"Part I ambience level {lv} not staged / registered"
                for b in P.load_manifest()["banks"]:
                    assert os.path.exists(os.path.join(stage, "soundbank4", b + ".bnk")) and f"sound-bank {b}" in reg, f"Part I bank {b} not staged / registered"
                mods = P.modules_table(open(os.path.join(stage, "bin", "dc1", "modules.bin"), "rb").read())
                for k, mi in P.load_manifest()["modules"].items():
                    sz = os.path.getsize(os.path.join(stage, *mi["file"].split("/")))
                    assert mods[mi["carrier"]][1] == sz == mi["size"] and sorted(mods[mi["carrier"]][2]) == sorted(int(x, 16) for x in mi["exports"]), f"Part I audio module {k} ({mi['carrier']}): modules.bin size / exports differ from the staged file"
            PP = _p1_particles()
            if PP.wanted(m):        # Part I fire particles: blocks registered, files staged, modules.bin carrier size / exports = the staged module
                mods = _p1_audio().modules_table(open(os.path.join(stage, "bin", "dc1", "modules.bin"), "rb").read())
                assert all(ln in reg for ln in PP.registry(m)), f"{m['key']}: Part I fire particle blocks not registered"
                assert p1_fires_mod().DONOR_PARTICLES not in m["levels"], f"{m['key']}: Forest can particles loaded next to Part I's"
                for rel, _src in PP.files(m):
                    f = os.path.join(stage, *rel.split("/"))
                    assert os.path.exists(f), f"{m['key']}: {rel} not staged"
                    if rel.startswith("bin/dc1/"):
                        name = rel[len("bin/dc1/"):-4]
                        ex = sorted({r[0] for r in PP.Module(open(f, "rb").read()).rows})
                        assert mods[name][1] == os.path.getsize(f) and mods[name][2] == ex, f"{m['key']}: {name}: modules.bin size / exports differ from the staged file"
                        assert not PP.imports_on() or PP.module_imports(open(os.path.join(stage, "bin", "dc1", "modules.bin"), "rb").read(), name) == PP.carrier_imports(name), \
                            f"{m['key']}: {name}: modules.bin imports are not Part I's"
            rs = p1_rs(m)
            if rs:
                assert os.path.exists(os.path.join(stage, "pak68", rs + "-ingame.pak")) and f"level-name {rs}" in reg and \
                    f"package {rs}-ingame" in reg, f"Part I render-settings level {rs} not staged / registered"
                mod = DcFile(open(os.path.join(stage, "bin", "dc1", *RS_MODULE.split("/")) + ".bin", "rb").read())
                have = {struct.unpack_from("<Q", mod.data, mod.q(0x18) + 24 * i)[0] for i in range(struct.unpack_from("<I", mod.data, 0x14)[0])}
                for sym in [ln.split(" ", 1)[1] for ln in p1_blocks(m) if ln.startswith("render-settings ")]:
                    assert fnv(sym) in have and f"render-settings {sym}" in reg, f"{sym} not in the staged {RS_MODULE}.bin / registry"


EXT_HEADER = os.path.join(HERE, "..", "ext", "sp_maps_built.h")
SP_BASE = 8                                 # first map-list index of an SP-section map (= map_packs.SP_BASE = t2r-ext MF_MAPS[8])


def built_mask(maps):
    """Bit (index - SP_BASE) per built map: the client's report of which SP maps its DLL contains (map_packs.SpSupport)."""
    mask = 0
    for m in maps:
        idx = m.get("index")
        if idx is not None and SP_BASE <= idx < SP_BASE + 32:      # u32 report (map_packs.SP_MAX)
            mask |= 1 << (idx - SP_BASE)
    return mask


def p1_fire_spawner_names(maps):
    """the full names of the fire particle spawners this build stages (the engine keeps only 31 characters of a process name, as
    "<first 14>...<last 14>"; the ext diag expands them by this list): Part I's own spawners with the Part I particle set, else the
    Forest-can graft names t2r-<fire>-<donor spawner>"""
    out = []
    for m in maps:
        if not m.get("part1", {}).get("fires"):
            continue
        if _p1_particles().wanted(m):
            out += [n for _lv, n in _p1_particles().fire_spawners(m)]
        else:
            F = _p1_fires()
            out += [e["name"] for e in F.spawner_entries(F.fires(m), [{"name": n, "pos": list(F.DONOR_ANCHOR), "quat": [0, 0, 0, 1]} for n in F.DONOR_SPAWNERS])]
    return sorted(set(out))


def p1_lighting_define(maps):
    """the ext replays the render-settings regions of the loaded Part I map (immersion.c, table g_p1m[] keyed by the loaded level).
    Every Part I map of the build gets an entry (tools/part1/p1_lighting_multi.py); a map whose config
    (tools/part1/data/p1_maps/<key>.json) has an "ext" block names its own generated header and base symbol, else the default
    tools/ext/p1_lighting.h (the Bookstore). No Part I map = "" (immersion.c falls back to p1_lighting.h)."""
    sys.path.insert(0, os.path.join(HERE, "..", "part1"))
    import p1_lighting_multi
    rows = []
    for m in maps:
        if not m.get("part1", {}).get("levels"):
            continue
        cfg = os.path.join(HERE, "..", "part1", "data", "p1_maps", m["key"] + ".json")
        ext = (json.load(open(cfg, encoding="utf-8")).get("ext") or {}) if os.path.exists(cfg) else {}
        rows.append((m["key"], ext.get("header"), ext.get("base_sym"), p1_rs_renames(m)))
    return p1_lighting_multi.ext_define(rows)


def write_ext_header(maps):
    """tools/ext/sp_maps_built.h (generated, git-ignored): the SP maps THIS build contains, baked into the next t2r-ext compile.
    The ext reports it to the server (0xC8); a runtime scan of the task graph is only a cross-check (the node lookup by hash
    does not work in game, A/B). Written on EVERY build, also with no map (mask 0). Callers that build the DLL and then
    compile the ext (deploy_test.sh, build_release.py) pick it up."""
    text = ("// generated by tools/features/sp_maps_build.py - do not edit, do not commit\n"
            "#define T2R_SP_BUILT_MASK 0x%04xu   // bit k = map-list index %d + k: %s\n" %
            (built_mask(maps), SP_BASE, ",".join(m["key"] for m in maps) or "none") +
            # 1 = a map of this build ships the Part I fire particle set (p1_particles.wanted): no fire point-light records are staged,
            # so the ext's p1_fire_flicker.c record search is off (it would walk the region manager forever)
            "#define T2R_P1_FIRE_PARTICLES %d\n" % (1 if any(_p1_particles().wanted(m) for m in maps) else 0) +
            "#define T2R_P1_FIRE_SPAWNER_NAMES %s   // (each followed by a comma; empty = none)\n" % "".join('"%s", ' % n for n in p1_fire_spawner_names(maps)) +
            p1_lighting_define(maps))
    old = open(EXT_HEADER, encoding="utf-8").read() if os.path.exists(EXT_HEADER) else None
    if old != text:
        open(EXT_HEADER, "w", encoding="utf-8", newline="\n").write(text)


def ensure_layouts(maps):
    """layout hook (re/maps/layout-rules-2013.md): every selected map without a generated layout gets one (team starts, respawns,
    supply boxes from its navmesh, pak rebuilt), then the layout rules are checked. Needs re/maps/seeds/<key>-nav.json; without it
    the map keeps its placeholder spawns (message only). T2R_LAYOUT_STRICT=1 fails the build on rule errors; T2R_LAYOUT=0 skips."""
    if os.environ.get("T2R_LAYOUT", "") == "0":
        return
    import sys
    sys.path.insert(0, os.path.join(HERE, "..", "maps"))
    try:
        import layout
    except ImportError as e:
        print(f"sp maps: layout tool unavailable ({e})")
        return
    for m in maps:
        layout.ensure(m["key"])


CACHE_PARTS = None      # build_dll sets the step-cache parts every cached step shares (its _env()); None = no caching (standalone use / tests)


_STRIP_SPEC_KEYS = ("key", "pak", "level", "levels", "edits", "park_spawners", "part1", "prefabs", "auto_vis", "auto_vis_grow_rule", "retired", "always")


def _strip_spec(key):
    """what the collectible / workbench strip reads of sp_maps.json: this map's entry (levels, park_spawners, edits, ...), not the other
    maps' entries or this map's props / boxes / respawn data - so editing one map rebuilds only its own strip (buildcache.Code skip_data
    keeps the whole file out of the code key) - plus the map's data/<key>-*.json files (seal removals, geo edits)"""
    m = next((x for x in json.load(open(SPEC, encoding="utf-8"))["maps"] if x["key"] == key), None)
    d = os.path.join(os.path.dirname(SPEC), "data")
    side = sorted(os.path.join(d, n) for n in os.listdir(d) if n.startswith(key + "-") and not n.endswith(".resolved.json")) if os.path.isdir(d) else []     # (*.resolved.json = the Scene Editor view that coll_edit writes on every build: an OUTPUT, keying on it rebuilt the strip each time)
    import buildcache as bc
    return [json.dumps({k: m[k] for k in _STRIP_SPEC_KEYS if k in m}, sort_keys=True) if m else "no-map-entry", [bc.File(f) for f in side]]


def _strip_step(collectibles, key):
    """collectibles.sp_strip_collectibles_workbench(key), remembered by content: it scans the map's level paks (pwsh dumps + the
    workbench instance search, ~15 s a map) and is a pure function of the game's level paks, the tools code and the T2R_* switches.
    The cache holds the edited -ingame paks' bytes, they are written back into the level-edit cache only when they differ (as
    build_key does), so nothing is deleted or rewritten under a concurrent reader."""
    if CACHE_PARTS is None:
        return collectibles.sp_strip_collectibles_workbench(key)
    import buildcache as bc
    import re as _re
    parts = [bc.Code("collectibles", skip_data=("sp_maps.json",)), CACHE_PARTS, key, _strip_spec(key)]
    import spedit                                  # the cached strip output must follow the Scene Editor spawner edits
    parts.append(bc.File(spedit.spec_path(key)) if os.path.exists(spedit.spec_path(key)) else "no-spedits")
    try:                                           # the SceneEditor library the spawner dumps load (path inside dump_spawners.ps1)
        m = _re.search(r'\$u\s*=\s*"([^"]+)"', open(collectibles.DUMP, encoding="utf-8").read())
        parts.append(bc.Stat(m.group(1)) if m and os.path.isdir(m.group(1)) else "no-scene-editor")
    except OSError:
        parts.append("no-dump-script")

    def run():
        r = collectibles.sp_strip_collectibles_workbench(key)
        r["spawner_paks"] = [(os.path.basename(f), open(f, "rb").read()) for f in r["spawner_paks"]]
        return r
    r = dict(bc.cached("sp-strip-" + key, parts, run))
    out_dir = os.path.join(collectibles.WORK, "out", key)
    os.makedirs(out_dir, exist_ok=True)
    paths = []
    for name, data in r["spawner_paks"]:
        dst = os.path.join(out_dir, name)
        if not os.path.exists(dst) or open(dst, "rb").read() != data:
            with open(dst, "wb") as f:
                f.write(data)
        paths.append(dst)
    r["spawner_paks"] = paths
    return r


def _auto_vis_on(key, m=None):
    """T2R_AUTO_VIS_MAPS=a,b limits the automatic VIS_INFO_1 opening to those maps (every opened level ships whole: opening all maps at once pushed
    the winmm image to 1.95 GB, which Windows refuses to load - 0xC000007B). Unset = every map.
    A map with "auto_vis_always": true in sp_maps.json is opened whatever the env says: release/build_release.py defaults the env to
    jackson-market only, which left the Bookstore garage opening (74a0b7b1) occluded - the Part I levels are DLC side data, not winmm image."""
    if m and m.get("auto_vis_always"):
        return True
    only = os.environ.get("T2R_AUTO_VIS_MAPS", "").strip()
    return not only or key in [k.strip() for k in only.split(",")]


def stage_edits(stage, maps):
    """Edited copies of stock SP level paks (a map's optional "edits" list in sp_maps.json, tools/maps/level_edit.py,
    re/maps/level-edit.md): baked geometry / collision removed, moved or rotated inside a world box.  The paks keep the
    stock level names: they go into the staged mod tree's pak68/ and shadow the originals (like every other stock pak the
    mod replaces, e.g. actor97/rifle-autorifle4.pak).  T2R_LEVEL_EDITS=0 = ship the stock levels.
    -> ["pak68/<level>.pak", ...] for the manifest (build_dll adds them)."""
    if os.environ.get("T2R_LEVEL_EDITS", "") == "0":
        return []
    import sys
    sys.path.insert(0, os.path.join(HERE, "..", "maps"))
    staged = []
    strip = os.environ.get("T2R_KEEP_COLLECTIBLES", "") != "1"
    bench = {}                                               # map key -> generated workbench-strip edits (merged with the map's own)
    if strip:       # MP has no SP collectibles / workbenches (collectibles.sp_strip_collectibles_workbench, every SP map)
        import collectibles
        for m in maps:
            res = _strip_step(collectibles, m["key"])
            bench[m["key"]] = res["edits"]
            print(f"sp map {m['key']}: stripped {sum(res['collectibles'].values())} collectible spawner(s), "
                  f"{len(res['workbench'])} workbench placement(s)")
            for f in res["spawner_paks"]:                  # edited <level>-ingame.pak copies
                p = "pak68/" + os.path.basename(f)
                if p in staged:
                    continue                                   # a level shared by two maps: same bytes (the park edit is per level)
                shutil.copyfile(f, os.path.join(stage, p))
                staged.append(p)
    if os.environ.get("T2R_SP_LIGHTING", "") != "0":         # SP lighting by task state (tools/maps/sp_lighting.py, spec "sp_lighting"): gated render-settings regions made always-on
        import sp_lighting
        for m in maps:
            if not m.get("sp_lighting"):
                continue
            def _base(lv, _s=stage):                          # the collectible-stripped copy staged above, else the stock pak
                f = os.path.join(_s, "pak68", lv + "-ingame.pak")
                return open(f, "rb").read() if os.path.exists(f) else None
            for f in sp_lighting.build(m, base_for=_base):
                p = "pak68/" + os.path.basename(f)
                shutil.copyfile(f, os.path.join(stage, p))
                if p not in staged:
                    staged.append(p)
        sp_lighting.header([m["key"] for m in maps])          # tools/ext/sp_lighting.h (built maps only: an unbuilt map's region data is not staged) for the next ext compile (imm_winter_exposure_tick)
    import geoedit                                           # Scene Editor geometry removals (tools/maps/data/<key>-geoedits.json), applied on the original SP paks
    import level_edit
    todo = [(m, m.get("edits", []) + bench.get(m["key"], []) + geoedit.edits_for(m["key"]) + level_edit.prefab_car_edits(m)) for m in maps]
    todo = [(m, ed + (level_edit.auto_vis_edits(ed, [x for x in m.get("auto_vis_levels", m["levels"]) if x != m["pak"]], grow_rule=m.get("auto_vis_grow_rule")) if m.get("auto_vis", True) and _auto_vis_on(m["key"], m) else [])) for m, ed in todo]      # removed geometry must not keep occluding (VIS_INFO_1); spec "auto_vis_levels" = only these levels (p1-bookstore: the far Part I levels would ship whole for nothing)
    todo = [(m, ed) for m, ed in todo if ed]
    if not todo:
        return staged
    # the maps are independent (own edit list, own out dir; the shared source-pak cache is written atomically): up to 3 maps at a time in child interpreters, each with
    # its share of the workers for its own levels (parjobs.py; T2R_PAR_JOBS=1 = serial). Logs are replayed map by map.
    import parjobs
    outer = max(1, min(len(todo), 3, parjobs.workers_default()))
    inner = max(1, parjobs.workers_default() // outer)
    built = parjobs.run([("level_edit", "build_edits", (edits,), {"out_dir": os.path.join(level_edit.CACHE, "out", m["key"])}) for m, edits in todo],
                        workers=outer, child_env={"T2R_PAR_JOBS": str(inner)})
    for (m, edits), files in zip(todo, built):
        for f in files:
            shutil.copyfile(f, os.path.join(stage, "pak68", os.path.basename(f)))
            p = "pak68/" + os.path.basename(f)
            if p not in staged:
                staged.append(p)
        print(f"sp map {m['key']}: {len(edits)} level edit(s) -> {', '.join(os.path.basename(f) for f in files)}")
    return staged


def apply(stage, maps=None):
    """-> {"level-sets": size, "test-tasks": size, "edit-paks": [manifest paths]} or None when no map is selected."""
    maps = selected() if maps is None else maps
    write_ext_header(maps)
    if not maps:
        return None
    assert not [m["key"] for m in maps if m.get("retired")], "sp maps: a retired map in the selection"
    allocate(maps)                               # each map its own level set (slot pool first, fresh entries after it)
    for what, vals in (("key", [m["key"] for m in maps]), ("level", [m["level"] for m in maps]),
                       ("pak", [m["pak"] for m in maps]), ("level set", [set_name(m) for m in maps])):
        assert len(set(vals)) == len(vals), f"sp maps: duplicate {what} in the selection {vals}"   # a repeated subnode / set would be added twice
    ls = patch_level_sets(os.path.join(stage, "bin", "dc1", "level-sets", "level-sets-test.bin"), maps)
    fresh = [set_name(m) for m in maps if not slotted(m)]
    if any(slotted(m) for m in maps):
        print(f"sp maps: leftover level sets reused: {', '.join(set_name(m) for m in maps if slotted(m))}")
    if fresh:
        n0, n1 = add_exports(os.path.join(stage, "bin", "dc1", "modules.bin"), fresh)
        print(f"sp maps: {MODULE} new sets {fresh}: exports {n0} -> {n1}"
              + (f" (slot pool of {POOL_SIZE} full: fresh level-set entries are not proven in game yet)" if POOL_SIZE else ""))
    print(f"sp maps: slot pool {sum(slotted(m) for m in maps)} / {POOL_SIZE} used, {POOL_SIZE - sum(slotted(m) for m in maps)} free in this build")
    tt = patch_tasks(os.path.join(stage, "bin", "dc1", "test-tasks.bin"), maps)
    patch_registry(os.path.join(stage, "pak68.txt"), maps)
    stage_part1(stage, maps)
    stage_p1_actors(stage, maps)
    edit_paks = stage_edits(stage, maps) + stage_prop_lod(stage, maps) + stage_scaled(stage, maps)
    verify(stage, maps)
    for m in maps:
        print(f"sp map {m['key']}: task {NODE}/{m['level']} -> level set {set_name(m)} ({len(m['levels'])} levels, "
              f"{len(m.get('props', []))} props)")
    return {"level-sets": ls, "test-tasks": tt, "edit-paks": edit_paks}
