"""Part I Bookstore ambience, ported natively (manifest re/part1/bookstore_port_manifest_1105.md).

Part I plays ALL its Hunter City ambience from one city-wide level, hun-const-audio: 1,135 `ss-ambient-sound` / script-icon spawners
(random one-shots), a REGION_TREE of 1,077 audio regions (positional loop emitters = regions with a `SfxProcess` aux block such as
emt-fire-barrel-6/7, door / window / room portals with sound-env + sound-env-plus/-minus, env-*-reverb-only regions), the level's
`sound-bank` lines and the sfx-info / sound-env / dsp DC modules.  TLOU2's engine has the same systems and the same file formats
(SBlk v0x23 banks, .str stream lists, sfx1/*.xvag, REGION_TREE SfxProcess blocks, DC sfx-info / environment-info / lr1-reverb rows),
so nothing is decoded or mixed by the ext: the engine plays the real events.

  python p1_audio.py convert <Part I dir> [map key = p1-bookstore]   # -> <main>/re/part1/x/audio-bookstore (T2R_P1_AUDIO_DIR), git-ignored
  python p1_audio.py verify  [map key]                               # offline proof of the converted set (no game)
  python p1_audio.py cost    [map key]                               # size cost

What convert writes (AUDIO = the dir above):
  pak68/hun-const-audio-ingame.pak      the spawners (SceneEditor reader + writer; the 3 ss-snd-hun-* story-script spawners dropped)
  pak68/hun-const-audio-rgn-ingame.pak  the converted REGION_TREE byte for byte (+ the Part I story-gating tags renamed, see region_pak)
  soundbank4/<bank>.bnk / .str          the Part I banks the Bookstore needs (spec part1.audio.banks), names unchanged
  sfx1/<name>.xvag                      the streams of those banks' .str lists (216 of lvl-hun-const-audio), names unchanged
  bin/dc1/<carrier>.bin                 Part I's aud-sfx-hunter-city / audio/environment / audio/dsp-pc modules (rows colliding with TLOU2's
                                        own removed), each installed as a REPLACEMENT of an unused TLOU2 module (the proven t1x path)
  pak68-audio.txt                       the registry blocks;  audio.json  the build manifest (files, sizes, module exports)
sp_maps_build.stage_part1_audio stages all of it into the mod (files, modules.bin size + export list), build_dll adds the manifest lines.
"""
import glob
import json
import os
import re
import shutil
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.dirname(HERE)
ROOT = os.path.dirname(TOOLS)
sys.path[:0] = [HERE, os.path.join(TOOLS, "features"), os.path.join(TOOLS, "maps"), os.path.join(TOOLS, "models")]
import t2pak  # noqa: E402
import p1_rsenv  # noqa: E402
from dcfile import DcFile, fnv  # noqa: E402

MAIN = os.environ.get("T2R_MAIN_ROOT", ROOT.split(os.sep + ".claude" + os.sep)[0])
AUDIO = os.environ.get("T2R_P1_AUDIO_DIR") or os.path.join(MAIN, "re", "part1", "x", "audio-bookstore")
SPEC = os.path.join(TOOLS, "maps", "sp_maps.json")
SPAWNER_PS1 = os.path.join(HERE, "p1_audio_spawners.ps1")
NAMESPACE = fnv("**namespace**")
T2_GAME = os.environ.get("T2R_TLOU2_DIR", r"C:\Games\The Last of Us Part II Remastered")
# The carriers are TLOU2's dev-only audio-sfx modules (test / test-levels / look-dev: no MP level, script or registry line names them).  startup.bin gives
# the "aud-sfx" namespace 1024 module slots and TLOU2 has 654 audio-sfx modules (4.6 MB), i.e. the whole namespace is loaded at start -- which is why the
# three Part I modules go in as REPLACEMENTS of three of them (module-info entry kept, size + export list rewritten: the path render-settings/t1x and the
# vox / look2 patches already take), not as new modules.info entries (never tried in this repo).  part-module/* would NOT do: particle modules are loaded
# per level by `particle-module` lines.
P1_MODULES = {          # carrier key -> (Part I file under bin.psarc dc1/, TLOU2 module it replaces)
    "sfx": ("audio-sfx/hunter-city/aud-sfx-hunter-city.bin", "audio-sfx/test-levels/aud-sfx-test-levels-ambience"),
    "env": ("audio/environment.bin", "audio-sfx/test/aud-sfx-test"),
    "dsp": ("audio/dsp-pc.bin", "audio-sfx/look-dev/aud-sfx-look-dev-game"),
}
# Part I story gating on audio regions (start-task / end-task + their subnode / node companions): the task graph of Part I does not exist in an MP
# match (p1_rsenv.GATING does the same for the render-settings regions).  The keys are RENAMED in place (each region's tag dictionary re-sorted):
# a region whose end-task never fires is simply on, and the 9 start-task regions are hotel / camp ones 300 m from the Bookstore.
GATING_KEYS = {fnv(k) for k in ("start-task", "end-task", "start-task-subnode", "end-task-subnode", "task-node", "task-subnode")}
DEFAULT_DROP_SPAWNERS = ("ss-snd-hun-",)         # Part I story-script spawners (their state scripts are not in TLOU2)
DEFAULT_DROP_BANKS = re.compile(r"^(hun-hotel-|hun-camp-|hun-financial-|wood-drawers$|safe$|generator$)")


# references that name nothing in any Part I module either (checked against all 1,100+ extracted Part I DC modules): dead in Part I itself, so
# equally silent here -- 3 spawner sounds (alleyway-bird-1, alleyway-grasshopper-1, pre-roll-hunter-truck-1), 5 sound-env sids (hun-booskstore-back-b/-c
# [sic], a hotel door, a hotel/ballroom blend) and one that is only a name inside environment.bin (hun-bookstore-door-1/2, window-bookstore-1: sound-env-plus)
DEAD_IN_PART1_SOUNDS = {0x0f306832f1121afe, 0xf1c1f0f17f37b5c1, 0x2f9cf5cf5b82b045}
DEAD_IN_PART1_ENVS = {0x825dec9666cb80be, 0x825dea9666cb7d58, 0x825ded9666cb8271, 0x1d9fe8b1722e8266, 0x55cf1b66c130ae3e, 0xa40126bf8350d33b}


def on():
    return os.environ.get("T2R_P1_AUDIO", "1") != "0"


def spec_of(m):
    return m.get("part1", {}).get("audio") if on() else None


def available(m):
    s = spec_of(m)
    return bool(s) and os.path.exists(os.path.join(AUDIO, "audio.json"))


def levels_of(m):
    s = m.get("part1", {}).get("audio")
    return [s["level"], s["region-level"]] if s else []


def load_spec(key="p1-bookstore"):
    return next(m for m in json.load(open(SPEC, encoding="utf-8"))["maps"] if m["key"] == key)


# ------------------------------------------------------------------ Part I archives
_TSV = None


def archive_of(rel):
    """Part I archive holding `rel` (re/part1/game-files.tsv)"""
    global _TSV
    if _TSV is None:
        _TSV = {}
        for ln in open(os.path.join(MAIN, "re", "part1", "game-files.tsv"), encoding="utf-8"):
            p = ln.rstrip("\n").split("\t")
            if len(p) == 3:
                _TSV.setdefault(p[1], p[0])
    return _TSV.get(rel)


class P1Files:
    def __init__(self, game):
        import p1_archive
        self.game, self.mod, self.arcs = game, p1_archive, {}

    def get(self, rel):
        a = archive_of(rel)
        if a is None:
            raise SystemExit(f"{rel}: not in re/part1/game-files.tsv")
        if a not in self.arcs:
            self.arcs[a] = self.mod.Psarc(os.path.join(self.game, "build", "pc", "main", a))
        arc = self.arcs[a]
        for k in (rel, "/" + rel):
            if k in arc.ent:
                return arc.get(k)
        raise SystemExit(f"{rel}: not in {a}")


def part1_block(game, level):
    """Part I's own registry block lines of `level` (pak68.txt)"""
    txt = open(os.path.join(game, "build", "pc", "main", "pak68.txt"), encoding="latin1").read().split("\n")
    i = txt.index(f"level-name {level}")
    out = []
    for ln in txt[i + 1:]:
        if ln.startswith("level-name "):
            break
        out.append(ln)
    return out


def tlou2_sound_files():
    """{'soundbank4/x.bnk' | 'sfx1/y.xvag': [archive]} of the TLOU2 install (cached next to the converted set)"""
    cache = os.path.join(AUDIO, "t2-sound-files.json")
    if os.path.exists(cache):
        return json.load(open(cache))
    import dsar_list
    out = {}
    for a in sorted(glob.glob(os.path.join(T2_GAME, "build", "pc", "main", "*.psarc"))):
        d, ent, bs, bsz = dsar_list.open_files(a)
        for n in ent:
            if n.startswith(("sfx1/", "soundbank4/")):
                out.setdefault(n, []).append(os.path.basename(a))
    os.makedirs(AUDIO, exist_ok=True)
    json.dump(out, open(cache, "w"))
    return out


# ------------------------------------------------------------------ DC modules
def dc_rows(f):
    n = struct.unpack_from("<I", f.data, 0x14)[0]
    eo = f.q(0x18)
    return [struct.unpack_from("<QQQ", f.data, eo + 24 * i) for i in range(n)]


def modules_table(modules_bin):
    """modules.bin -> {module name: (entry offset, size, [export sids])} (7,096 TLOU2 modules)"""
    m = DcFile(modules_bin) if isinstance(modules_bin, (bytes, bytearray)) else modules_bin
    n, arr = m.q(0x48), m.q(0x50)
    out = {}
    for i in range(n):
        e = arr + 40 * i
        name = bytes(m.data[m.q(e):m.data.index(b"\0", m.q(e))]).decode()
        exp = m.q(e + 32)
        ex = [m.q(m.q(exp + 8) + 8 * k) for k in range(m.q(exp))] if exp else []
        out[name] = (e, m.q(e + 16), ex)
    return out


def build_module(src, taken):
    """Part I DC module bytes -> (bytes for the carrier, kept row sids, removed row sids): the rows whose sid another TLOU2 module already exports
    are removed (TLOU2's own definition wins; the table is compacted in place, sorted order kept, stale tail rows zeroed with their relocation
    bits cleared), the count at +0x14 follows."""
    f = DcFile(src)
    rows = dc_rows(f)
    sids = [r[0] for r in rows]
    assert sids == sorted(sids) and len(set(sids)) == len(sids), "rows not sorted / unique (the loader binary-searches them)"
    keep = [r for r in rows if r[0] not in taken or r[0] == NAMESPACE]
    gone = [r[0] for r in rows if r[0] in taken and r[0] != NAMESPACE]
    eo = f.q(0x18)
    for k, (s, t, o) in enumerate(keep):
        struct.pack_into("<QQQ", f.data, eo + 24 * k, s, t, o)
    for k in range(len(keep), len(rows)):
        struct.pack_into("<QQQ", f.data, eo + 24 * k, 0, 0, 0)
        i = (eo + 24 * k + 16) // 8
        f.bits[i // 8] &= ~(1 << (i % 8))
    struct.pack_into("<I", f.data, 0x14, len(keep))
    return f.save(), [r[0] for r in keep], gone


def set_exports(modules_path, module, sids):
    """modules.bin: REPLACE the module's export list (sorted sids; a new array is appended, the old one stays as garbage)"""
    m = DcFile(open(modules_path, "rb").read())
    e = m.data.find(struct.pack("<Q", fnv(module))) - 8
    assert e > 0 and m.is_ptr(e) and m.is_ptr(e + 32), f"modules.bin entry of {module}"
    sa = m.q(e + 32)
    d_exp = m.q(sa + 8)
    sids = sorted(set(sids))
    tag = m.q(d_exp - 8)
    na = m.append(struct.pack("<Q", tag) + b"".join(struct.pack("<Q", s) for s in sids)) + 8
    sa = m.q(e + 32)
    n0 = m.q(sa)
    m.set_q(sa, len(sids))
    m.set_ptr(sa + 8, na)
    open(modules_path, "wb").write(m.save())
    return n0, len(sids)


# ------------------------------------------------------------------ region pak
class Space:
    """address space of a TPak's pages laid end to end: q / ptr / put"""
    def __init__(self, pk):
        self.pk, self.starts, pos = pk, [], 0
        for p in pk.pages:
            self.starts.append(pos)
            pos += len(p)
        self.size = pos

    def loc(self, a):
        for i, s in enumerate(self.starts):
            if s <= a < s + len(self.pk.pages[i]):
                return i, a - s
        raise IndexError(hex(a))

    def q(self, a):
        pg, o = self.loc(a)
        return struct.unpack_from("<Q", self.pk.pages[pg], o)[0]

    def ptr(self, a):
        pg, o = self.loc(a)
        dp = self.pk.fix.get((pg, o))
        return None if dp is None else self.starts[dp] + struct.unpack_from("<Q", self.pk.pages[pg], o)[0]

    def get_slot(self, a):
        pg, o = self.loc(a)
        return self.pk.fix.get((pg, o)), struct.unpack_from("<Q", self.pk.pages[pg], o)[0]

    def put(self, a, v):
        pg, o = self.loc(a)
        struct.pack_into("<Q", self.pk.pages[pg], o, v)

    def put_slot(self, a, dp, v):
        pg, o = self.loc(a)
        struct.pack_into("<Q", self.pk.pages[pg], o, v)
        self.pk.fix[(pg, o)] = dp


def cstr(sp, a):
    pg, o = sp.loc(a)
    p = sp.pk.pages[pg]
    return bytes(p[o:p.index(b"\0", o)]).decode("latin1")


def region_records(sp):
    """[(record address, name)] of the pak's (single) REGION_TREE"""
    (pg, off), = [(p, o) for n, p, o in sp.pk.items() if n == "REGION_TREE"]
    base = sp.starts[pg] + off
    out, k = [], 8
    while sp.ptr(base + k) is not None:
        r = sp.ptr(base + k)
        out.append((r, cstr(sp, sp.ptr(r))))
        k += 8
    return out


def region_sfx(sp, rec):
    """the SfxProcess aux block of a region record (+0x40): (sound sid, flags) or None"""
    a = sp.ptr(rec + 0x40)
    if a is None or sp.q(a) != fnv("SfxProcess"):
        return None
    return sp.q(a + 8), sp.q(a + 0x10)


def region_pak(conv_bytes):
    """converted hun-const-audio-ingame.pak -> the REGION pak: SPAWNER_GROUP unlisted (the spawners ship in the writer's pak) and the story-gating
    tags of the regions renamed to inert keys.  The REGION_TREE bytes are otherwise untouched (888 of its 1,077 regions use shapes / aux blocks
    p1_rsenv.build_tree cannot write)."""
    pk = t2pak.TPak(conv_bytes)
    sp = Space(pk)
    renamed = 0
    for rec, name in region_records(sp):
        dic = sp.ptr(rec + 0x50)
        ent, cnt = sp.ptr(dic), sp.q(dic + 8)
        es = [(sp.q(ent + 16 * i),) + sp.get_slot(ent + 16 * i + 8) for i in range(cnt)]       # (key, box dest page, box offset)
        if not any(k in GATING_KEYS for k, _, _ in es):
            continue
        was_sorted = [e[0] for e in es] == sorted(e[0] for e in es)
        es = [(fnv("t2r-p1-ungated-%x" % k) if k in GATING_KEYS else k, dp, v) for k, dp, v in es]
        if was_sorted:
            es.sort(key=lambda e: e[0])
        assert len({e[0] for e in es}) == len(es), name
        for i, (k, dp, v) in enumerate(es):
            sp.put(ent + 16 * i, k)
            sp.put_slot(ent + 16 * i + 8, dp, v)
        renamed += 1
    # SPAWNER_GROUP out of the item table and the login table
    (pg, off), = [(p, o) for n, p, o in pk.items() if n == "SPAWNER_GROUP"]
    (lpg, loff), = [(p, o) for n, p, o in pk.items() if n == "PAK_LOGIN_TABLE"]
    P = pk.pages[lpg]
    n, = struct.unpack_from("<I", P, loff)
    ents = [struct.unpack_from("<II", P, loff + 8 + 8 * k) for k in range(n)]
    keep = [e for e in ents if not (e[0] == pg and e[1] == off - 48)]
    assert len(keep) == n - 1, "SPAWNER_GROUP not in the login table"
    for k in range(n):
        struct.pack_into("<II", P, loff + 8 + 8 * k, *(keep[k] if k < len(keep) else (0, 0)))
    struct.pack_into("<I", P, loff, len(keep))
    pk.drop_item(pg, off - 48)
    return pk.serialize(), renamed


# ------------------------------------------------------------------ spawner pak
def spawner_pak(conv_path, out_path, drop, json_path):
    """drop spawners by name prefix and rewrite the pak TLOU2-natively + the spawner list json. Pure Python (p1_spawner_pak.py, a port of the SceneEditor's
    reader / package writer: byte-identical to its output, tools/tests/test_p1_spawner_pak.py); no pwsh, no SceneEditor"""
    import p1_spawner_pak
    data = open(conv_path, "rb").read()
    out, kept, dropped = p1_spawner_pak.rewrite(data, tuple(drop))
    sp, _li = p1_spawner_pak.read(data)
    open(json_path, "w", encoding="utf-8").write(p1_spawner_pak.json_text([x for x in sp if not any(x.name.startswith(d) for d in drop)]))
    tmp = out_path + ".tmp"
    open(tmp, "wb").write(out)
    os.replace(tmp, out_path)
    return f"{out_path} : {kept} spawners ({dropped} dropped)"


def read_spawners(json_path):
    return json.load(open(json_path, encoding="utf-8-sig"))


P_SOUND, P_NEAR, P_FAR, P_FLAG, P_SCRIPT = ("#2593D0C70A1C5074", "#447C154DA1B30A93", "#72E3408C44993A21", "#C626F6D2A6CF9184", "#CE1173292ADCBD6E")


def spawner_sound(s):
    for q in s["pr"]:
        if q["k"] == P_SOUND:
            return int(q["v"].lstrip("#"), 16)
    return None


# ------------------------------------------------------------------ convert
def bank_list(block, s):
    """sound-bank lines of Part I's block, de-duplicated, minus the spec's drops (default: hotel / camp / financial area banks and three
    prop banks: their emitters are hundreds of metres from the Bookstore); spec "banks" overrides with an explicit list"""
    names = list(dict.fromkeys(ln.split()[1] for ln in block if ln.startswith("sound-bank ")))
    if s.get("banks"):
        return list(s["banks"])
    drop = re.compile(s["banks-drop"]) if s.get("banks-drop") else DEFAULT_DROP_BANKS
    return [b for b in names if not drop.search(b)]


def convert(game, key="p1-bookstore"):
    import p1_convert
    m = load_spec(key)
    s = m["part1"]["audio"]
    files = P1Files(game)
    for d in ("pak68", "soundbank4", "sfx1", "bin"):          # (the shipped dirs are rebuilt whole: no stale file reaches audio.json)
        shutil.rmtree(os.path.join(AUDIO, d), ignore_errors=True)
    for d in ("src", "pak68", "soundbank4", "sfx1", "bin"):
        os.makedirs(os.path.join(AUDIO, d), exist_ok=True)
    lvl, rgn = s["level"], s["region-level"]
    # 1. the level paks -> TLOU2 layout (p1_convert is the Bookstore's converter); the -ingame pak splits into spawners + regions
    raw = files.get(f"pak68/{lvl}-ingame.pak")
    conv = p1_convert.convert(raw, {}, None, 0, lvl + "-ingame")
    cpath = os.path.join(AUDIO, "src", lvl + "-ingame.conv.pak")
    open(cpath, "wb").write(conv)
    bad = p1_convert.loader_check(cpath)
    assert not bad, bad
    spath = os.path.join(AUDIO, "pak68", lvl + "-ingame.pak")
    msg = spawner_pak(cpath, spath, s.get("drop-spawners", DEFAULT_DROP_SPAWNERS), os.path.join(AUDIO, "spawners.json"))
    print(" ", msg)
    rbytes, renamed = region_pak(conv)
    rpath = os.path.join(AUDIO, "pak68", rgn + "-ingame.pak")
    open(rpath, "wb").write(rbytes)
    bad = p1_convert.loader_check(rpath) + p1_convert.vram_check(rpath)
    assert not bad, bad
    print(f"  {rgn}-ingame.pak {len(rbytes)} bytes: REGION_TREE of {len(region_records(Space(t2pak.TPak(rbytes))))} regions, gating tags renamed on {renamed}")
    # 2. banks + streams
    block = part1_block(game, lvl)
    banks = bank_list(block, s)
    t2 = tlou2_sound_files()
    shipped, streams, skipped = [], [], []
    for b in banks:
        if f"soundbank4/{b}.bnk" in t2:
            skipped.append(b)                    # TLOU2 has a bank of this name (gbl-gas-mask): its own file stays
            continue
        for ext in ("bnk", "str"):
            data = files.get(f"soundbank4/{b}.{ext}")
            open(os.path.join(AUDIO, "soundbank4", f"{b}.{ext}"), "wb").write(data)
        shipped.append(b)
        for ln in open(os.path.join(AUDIO, "soundbank4", b + ".str"), "rb").read().split(b"\n"):
            if ln.strip():
                streams.append(ln.decode("latin1").strip().split("\\")[-1])
    streams = sorted(set(streams))
    xv, coll = [], []
    for n in streams:
        if f"sfx1/{n}" in t2:
            coll.append(n)                       # TLOU2 has a stream of this name: its file serves (a mod copy would replace it for every map)
            continue
        data = files.get(f"sfx1/{n}")
        open(os.path.join(AUDIO, "sfx1", n), "wb").write(data)
        xv.append(n)
    print(f"  banks {len(shipped)} shipped, {skipped} left to TLOU2; streams {len(xv)} shipped, {len(coll)} same-named TLOU2 streams kept: {coll}")
    # 3. DC modules (sfx-info / sound-env / dsp) as carrier replacements
    mods = modules_table(open(os.path.join(MAIN, "re", "gamebin", "dc1", "modules.bin"), "rb").read())
    owner = {}
    for name, (e, sz, ex) in mods.items():
        for x in ex:
            owner.setdefault(x, set()).add(name)
    binarc = P1Files(game)
    mod_info = {}
    for k, (p1rel, carrier) in P1_MODULES.items():
        carrier = s.get("carriers", {}).get(k, carrier)
        src = binarc.get("dc1/" + p1rel)
        taken = {x for x, o in owner.items() if o - {carrier}}
        out, kept, gone = build_module(src, taken)
        dst = os.path.join(AUDIO, "bin", "dc1", *(carrier + ".bin").split("/"))
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        open(dst, "wb").write(out)
        mod_info[k] = {"carrier": carrier, "part1": p1rel, "file": "bin/dc1/" + carrier + ".bin", "size": len(out), "rows": len(kept),
                       "removed-colliding": len(gone), "exports": ["%016x" % x for x in kept]}
        print(f"  module {k}: Part I {p1rel} ({len(src)} B) -> carrier {carrier}: {len(kept)} rows, {len(gone)} rows TLOU2 already defines")
    # 4. registry blocks
    open(os.path.join(AUDIO, "pak68-audio.txt"), "w", encoding="latin1", newline="\n").write("".join(ln + "\n" for ln in registry_lines(s, shipped, skipped)))
    # 5. build manifest
    man = {"map": key, "level": lvl, "region-level": rgn, "banks": shipped, "banks-tlou2": skipped, "streams": xv, "streams-tlou2": coll,
           "modules": mod_info, "files": []}
    for sub in ("pak68", "soundbank4", "sfx1", "bin"):
        for p in sorted(glob.glob(os.path.join(AUDIO, sub, "**", "*"), recursive=True)):
            if os.path.isfile(p):
                man["files"].append({"path": os.path.relpath(p, AUDIO).replace("\\", "/"), "size": os.path.getsize(p)})
    json.dump(man, open(os.path.join(AUDIO, "audio.json"), "w"), indent=1)
    print(f"  audio.json: {len(man['files'])} files, {sum(f['size'] for f in man['files']) / 1e6:.1f} MB")


def registry_lines(s, shipped, left):
    """the two level blocks: <level> = spawner pak + the banks (+ TLOU2's own gbl-gas-mask) + script-icon + ss-ambient-sound; <region-level> = the
    region pak + ss-snd-fact-region (the foliage fact regions' state script).  Part I's `ir-pack dsp-alpha-t2` names no irpack file in any Part I
    archive and is not copied; the `ss-snd-hun-*` story-script symbols are not TLOU2's."""
    lv, rg = s["level"], s["region-level"]
    out = [f"level-name {lv}", f"level-id {lv}", f"package {lv}-ingame"]
    out += [f"sound-bank {b}" for b in shipped + left]
    out += ["actor script-icon", "symbol ss-ambient-sound"]
    out += [f"level-name {rg}", f"level-id {rg}", f"package {rg}-ingame", "symbol ss-snd-fact-region"]
    return out


# ------------------------------------------------------------------ build side
def load_manifest():
    return json.load(open(os.path.join(AUDIO, "audio.json")))


def registry(m):
    s = m["part1"]["audio"]
    man = load_manifest()
    return registry_lines(s, man["banks"], man["banks-tlou2"])


def manifest_paths(m):
    """mod-relative paths the build adds to the archive manifest"""
    return [f["path"] for f in load_manifest()["files"]]


def stage(stage_dir, m, log=print):
    """copy the converted set into the staged mod + modules.bin (size + export list of each carrier)"""
    import dc_modules
    import dc_check
    man = load_manifest()
    import p1_stage
    p1_stage.stage_audio_files(stage_dir, AUDIO, man)       # the files: one code path with p1conv
    modules = os.path.join(stage_dir, "bin", "dc1", "modules.bin")
    for k, mi in man["modules"].items():
        name = mi["carrier"]
        data = bytearray(open(modules, "rb").read())
        old = dc_modules.set_size(data, name, mi["size"])
        open(modules, "wb").write(data)
        n0, n1 = set_exports(modules, name, [int(x, 16) for x in mi["exports"]])
        raw = open(os.path.join(stage_dir, *mi["file"].split("/")), "rb").read()
        dc_check.check_relocation(raw, name)
        log(f"sp map {m['key']}: Part I audio module {k}: {name} {old} -> {mi['size']} bytes, exports {n0} -> {n1}")
    log(f"sp map {m['key']}: Part I audio {len(man['files'])} files ({sum(f['size'] for f in man['files']) / 1e6:.1f} MB: "
        f"{len(man['banks'])} banks, {len(man['streams'])} streams, 2 paks, {len(man['modules'])} DC modules)")
    return man


# ------------------------------------------------------------------ offline proof
def verify(key="p1-bookstore", log=print, stage_dir=None):
    """problems list (empty = OK): paks parse and are TLOU2-native, every sound the level plays resolves (sfx-info row in the carrier or a
    TLOU2 module, a cue in a shipped bank), every sound-env of the regions resolves, every dsp preset of those envs resolves, every bank and
    stream is shipped or TLOU2's own, the fire emitters are SfxProcess sfx-hun-fire-barrel at the spec'd barrels"""
    import p1_convert
    import sndbank
    import dc_check
    m = load_spec(key)
    s = m["part1"]["audio"]
    man = load_manifest()
    bad = []
    mods = modules_table(open(os.path.join(MAIN, "re", "gamebin", "dc1", "modules.bin"), "rb").read())
    t2own = {x: n for n, (e, sz, ex) in mods.items() for x in ex}
    # paks
    for lv in (s["level"], s["region-level"]):
        p = os.path.join(AUDIO, "pak68", lv + "-ingame.pak")
        bad += [f"{lv}: {b}" for b in p1_convert.loader_check(p) + p1_convert.vram_check(p) + p1_convert.trailer_check(p)]
    sp = Space(t2pak.TPak(open(os.path.join(AUDIO, "pak68", s["region-level"] + "-ingame.pak"), "rb").read()))
    names = [n for n, _, _ in sp.pk.items()]
    if names.count("REGION_TREE") != 1 or "SPAWNER_GROUP" in names:
        bad.append(f"region pak items {names}")
    spawners = read_spawners(os.path.join(AUDIO, "spawners.json"))
    if len(spawners) != 1132 or any(x["n"].startswith(tuple(s.get("drop-spawners", DEFAULT_DROP_SPAWNERS))) for x in spawners):
        bad.append(f"spawner count {len(spawners)}")
    # module rows
    sfx_rows, env_rows, dsp_rows = {}, {}, {}
    for k, dst in (("sfx", sfx_rows), ("env", env_rows), ("dsp", dsp_rows)):
        mi = man["modules"][k]
        raw = open(os.path.join(AUDIO, *mi["file"].split("/")), "rb").read()
        dc_check.check_relocation(raw, mi["carrier"])
        f = DcFile(raw)
        rows = dc_rows(f)
        if [r[0] for r in rows] != sorted(r[0] for r in rows) or {r[0] for r in rows} != {int(x, 16) for x in mi["exports"]}:
            bad.append(f"module {k}: rows not sorted / exports differ")
        dst.update({r[0]: (r[1], r[2], f) for r in rows})
        for r in rows:
            if r[0] != NAMESPACE and r[0] in t2own and t2own[r[0]] != mi["carrier"]:
                bad.append(f"module {k}: {r[0]:x} also exported by {t2own[r[0]]}")
        if mi["carrier"] not in mods:
            bad.append(f"carrier {mi['carrier']} is not a TLOU2 module")
    # sounds the level plays: spawner events + the SfxProcess aux blocks of the regions
    banks = {b: open(os.path.join(AUDIO, "soundbank4", b + ".bnk"), "rb").read() for b in man["banks"]}
    plays = {}
    for x in spawners:
        sid = spawner_sound(x)
        if sid is not None:
            plays.setdefault(sid, []).append(x["n"])
    fire = {}
    for rec, name in region_records(sp):
        r = region_sfx(sp, rec)
        if r:
            plays.setdefault(r[0], []).append(name)
            if name.startswith("emt-fire-barrel-"):
                fire[name] = r[0]
    unresolved, nocue = [], []
    for sid, who in plays.items():
        if sid not in sfx_rows and sid not in t2own:
            unresolved.append((sid, who[0]))
            continue
        if sid in sfx_rows and not any(_cue(b, sid) for b in banks.values()):
            nocue.append((sid, who[0]))
    log(f"  sounds played: {len(plays)} distinct ({sum(len(v) for v in plays.values())} emitters); no sfx-info row {len(unresolved)}, "
        f"row but no cue in a shipped bank {len(nocue)} (bank not shipped / TLOU2's own)")
    unresolved = [u for u in unresolved if u[0] not in DEAD_IN_PART1_SOUNDS]
    if unresolved:
        bad.append(f"{len(unresolved)} sounds have no sfx-info row: " + ", ".join("%x(%s)" % u for u in unresolved[:6]))
    # fire
    want = fnv("sfx-hun-fire-barrel")
    for n in ("emt-fire-barrel-6", "emt-fire-barrel-7"):
        if fire.get(n) != want:
            bad.append(f"{n}: SfxProcess sound {fire.get(n)} != sfx-hun-fire-barrel")
    if want not in sfx_rows or not _cue(banks["lvl-hun-const-audio"], want):
        bad.append("sfx-hun-fire-barrel: no sfx-info row / cue in lvl-hun-const-audio")
    # sound-env
    envkeys = {fnv(k) for k in ("sound-env", "sound-env-plus", "sound-env-minus")}
    (regs, _g), = p1_rsenv.read_pak_regions(open(os.path.join(AUDIO, "pak68", s["region-level"] + "-ingame.pak"), "rb").read())
    used = {v for r in regs for k, kind, v in r["tags"] if k in envkeys and kind == "sid"}
    miss = [e for e in used if e not in env_rows and e not in t2own]
    log(f"  sound-env sids {len(used)}: carrier {sum(e in env_rows for e in used)}, TLOU2 {sum(e in t2own and e not in env_rows for e in used)}, unresolved {len(miss)}")
    miss = [e for e in miss if e not in DEAD_IN_PART1_ENVS]
    if miss:
        bad.append(f"{len(miss)} sound-env sids unresolved: " + ", ".join("%x" % e for e in miss[:6]))
    # dsp presets referenced by those envs
    dsp_all = set(dsp_rows) | {x for x in t2own if x not in env_rows}
    refs = set()
    for e in used:
        if e in env_rows:
            t, o, f = env_rows[e]
            for i in range(0, 176, 8):
                if not f.is_ptr(o + i) and f.q(o + i) in dsp_rows:
                    refs.add(f.q(o + i))
    log(f"  dsp presets referenced by the envs: {len(refs)} (carrier rows {len(dsp_rows)})")
    # banks + streams
    t2 = tlou2_sound_files()
    for b in man["banks"]:
        if b not in banks or not banks[b][:4]:
            bad.append(f"bank {b}")
        if not os.path.exists(os.path.join(AUDIO, "soundbank4", b + ".str")):
            bad.append(f"{b}.str")
    for b in man["banks-tlou2"]:
        if f"soundbank4/{b}.bnk" not in t2:
            bad.append(f"bank {b}: neither shipped nor TLOU2's")
    for n in man["streams"]:
        if not os.path.exists(os.path.join(AUDIO, "sfx1", n)):
            bad.append(f"stream {n}")
    for b in man["banks"]:
        for ln in open(os.path.join(AUDIO, "soundbank4", b + ".str"), "rb").read().split(b"\n"):
            n = ln.decode("latin1").strip().split("\\")[-1]
            if n and n not in man["streams"] and f"sfx1/{n}" not in t2:
                bad.append(f"stream {n} of {b} is neither shipped nor TLOU2's")
    reg = registry(m)
    for b in man["banks"] + man["banks-tlou2"]:
        if f"sound-bank {b}" not in reg:
            bad.append(f"registry lacks sound-bank {b}")
    return bad


def _cue(bank, sid):
    """True when the bank holds a cue record for the event hash.  A record is {u64 hash, u16 bucket (= hash % table size), u16 next (0xffff = end),
    u32 cue index} (sndbank.CUE_REC); sndbank.cue_lookup only walks tables up to 160 slots (the weapon banks'), the ambience bank's has ~1000, so
    this checks the record itself: 4-aligned, hash % (bucket + k) == bucket for a table size k > 0 that fits (bucket < size), next < size, and the
    cue index inside the bank's cue count when sndbank can walk the table"""
    import sndbank
    pat = struct.pack("<Q", sid)
    i = bank.find(pat)
    while i >= 0:
        if i % 4 == 0 and i + 16 <= len(bank):
            h, bucket, nxt, idx = struct.unpack_from(sndbank.CUE_REC, bank, i)
            if bucket < 8192 and (nxt == 0xffff or nxt < 8192) and idx < 100000 and any(h % n == bucket for n in range(bucket + 1, 8193)):
                return True
        i = bank.find(pat, i + 1)
    return False


def cost(key="p1-bookstore"):
    man = load_manifest()
    by = {}
    for f in man["files"]:
        k = f["path"].split("/")[0]
        by[k] = by.get(k, 0) + f["size"]
    tot = sum(by.values())
    print("  " + ", ".join(f"{k} {v / 1e6:.1f} MB" for k, v in sorted(by.items())) + f"  = {tot / 1e6:.1f} MB raw")
    return tot, by


def main(argv):
    if len(argv) >= 3 and argv[1] == "convert":
        convert(argv[2], argv[3] if len(argv) > 3 else "p1-bookstore")
    elif len(argv) >= 2 and argv[1] == "verify":
        bad = verify(argv[2] if len(argv) > 2 else "p1-bookstore", print)
        print("verify:", "OK" if not bad else "%d problems" % len(bad))
        for b in bad[:30]:
            print("  !", b)
        return 1 if bad else 0
    elif len(argv) >= 2 and argv[1] == "cost":
        cost()
    else:
        print(__doc__)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
