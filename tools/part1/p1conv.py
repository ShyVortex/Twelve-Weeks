"""p1conv: build the Part I Bookstore file set from the player's own Part I install (the launcher spawns this; PyInstaller one-file: p1conv.spec).

  p1conv convert --part1 <Part I dir> --tlou2 <TLOU2 game dir> --out <dir> [--map p1-bookstore] [--tex-drop N] [--only=<level>,...] [--work <dir>]
  p1conv verify  --out <dir> --against <server manifest json | dir>     # byte compare with a published pack (exit 0 = identical)
  p1conv inputs  --tlou2 <TLOU2 game dir> --out <dir>                   # only extract the donor files (modules.bin, render-settings/t1x.bin)
  p1conv version

stdout is JSON lines ONLY (one object per line), everything else goes to stderr:
  {"event":"hello","version":1,"map":"p1-bookstore"}
  {"event":"stage","name":"levels","i":1,"n":3}
  {"event":"progress","stage":"levels","done":2,"total":27,"label":"hun-checkpoint-maze.pak"}
  {"event":"log","message":"..."}
  {"event":"file","path":"pak68/x.pak","size":N,"sha256":"..."}      one per output file, as it is finished
  {"event":"done","files":N,"bytes":N,"partial":false,"missing":[...]}
  {"event":"error","message":"..."}                                      then exit code 1
Cancel = the launcher kills the process; a restart re-uses finished files (a file whose sha256 line was printed is complete: written to <out> only
after <work> holds it, via a temp name + rename).

Output is the SAME file set the build stages (p1_fileset.bookstore_files) with the SAME bytes, under the in-game paths, so `p1_fileset.py compare`
against the server pack proves the conversion matches. Determinism: the converters take no clock / random input (two runs of the maze levels are
byte-identical, tools/part1 tests); nothing here adds timestamps.

Part I is only ever read. Stages needing TLOU2's own files (render-settings module, audio DC modules, actor paks, light / fire grafts) read the
player's TLOU2 install (--tlou2); without it those stages are reported in "missing" and the result is "partial".
"""
import hashlib
import json
import os
import re
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(TOOLS, "features"))
sys.path.insert(0, os.path.join(TOOLS, "models"))

VERSION = 1
RECIPE_TEX_DROP = 2


def a_tex(a):
    return a.get("tex_drop", os.environ.get("T2R_P1_TEXDROP") or None)
_out = sys.stdout


def emit(**ev):
    _out.write(json.dumps(ev, separators=(",", ":")) + "\n")
    _out.flush()


def sha256_file(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 22), b""):
            h.update(b)
    return h.hexdigest()


class Lines:
    """file-like that turns the converters' print() lines into log events and level progress"""

    def __init__(self, total):
        self.total, self.done, self.buf = total, 0, ""

    def write(self, s):
        self.buf += s
        while "\n" in self.buf:
            ln, self.buf = self.buf.split("\n", 1)
            m = re.match(r"^\s+(\S+?\.pak) [\d.]+ MB", ln)
            if m:
                self.done += 1
                emit(event="progress", stage="levels", done=self.done, total=self.total, label=m.group(1))
            elif ln.strip():
                emit(event="log", message=ln.strip()[:400])
        return len(s)

    def flush(self):
        pass


def install_file(src, dst):
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    tmp = dst + ".part"
    shutil.copyfile(src, tmp)
    os.replace(tmp, dst)


def tlou2_inputs(tlou2, main):
    """the donor inputs the converters read from TLOU2's own install, extracted from the player's bin.psarc into <main>/re/gamebin/dc1/
    (render-settings/t1x.bin, modules.bin: the files the build reads from re/gamebin); T2R_TLOU2_DIR for the audio stage's TLOU2 file listing"""
    import p1_archive
    arc = os.path.join(tlou2, "build", "pc", "main", "bin.psarc")
    if not os.path.isfile(arc):
        raise SystemExit("not a TLOU2 install (build/pc/main/bin.psarc missing): " + tlou2)
    a = p1_archive.Psarc(arc)
    names = ["dc1/modules.bin"] + sorted(n.lstrip("/") for n in a.ent if n.lstrip("/").startswith("dc1/render-settings/") and n.endswith(".bin"))
    for name in names:       # modules.bin + every TLOU2 render-settings module (rs_env reads the whole folder for the key set / engine defaults)
        dst = os.path.join(main, "re", "gamebin", *name.split("/"))
        if not os.path.isfile(dst):
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            with open(dst + ".part", "wb") as f:
                f.write(a.get(name))
            os.replace(dst + ".part", dst)
    os.environ["T2R_TLOU2_DIR"] = tlou2
    return True


def convert(a):
    global _out
    game, out = a["part1"], a["out"]
    key = a.get("map", "p1-bookstore")
    work = a.get("work") or os.path.join(out, ".work")
    os.makedirs(work, exist_ok=True)
    os.environ["T2R_P1_CONV"] = work                 # p1_levelset / p1_actors / sp_maps_build all read this
    # the recipe the shipped conv (night70, conv-abi-mix4/5) was made with: textures embedded with the top 2 mips dropped, INTERACTIVE_BG_1 items dropped
    # (T2R_P1_KEEP_UNKNOWN=0). The environment may still override (tests, bisects).
    os.environ.setdefault("T2R_P1_KEEP_UNKNOWN", "0")
    if a_tex(a) is None:
        a["tex_drop"] = RECIPE_TEX_DROP
    os.environ.setdefault("T2R_MAIN_ROOT", work)
    # the converters look archives up in re/part1/game-files.tsv under T2R_MAIN_ROOT: built here from the player's own archives (a listing of
    # their TOCs, written to the work dir, never shipped)
    idx = os.path.join(os.environ["T2R_MAIN_ROOT"], "re", "part1", "game-files.tsv")
    if not os.path.isfile(idx):
        import p1_archive
        emit(event="stage", name="index", i=0, n=3)
        os.makedirs(os.path.dirname(idx), exist_ok=True)
        main = os.path.join(game, "build", "pc", "main")
        lf, tab = chr(10), chr(9)
        with open(idx + ".part", "w", encoding="utf-8", newline=lf) as f:
            for name in sorted(x for x in os.listdir(main) if x.lower().endswith(".psarc")):
                arc = p1_archive.Psarc(os.path.join(main, name))
                for nm, (bi, usz, off) in sorted(arc.ent.items()):
                    f.write(f"{name}{tab}{nm.lstrip('/')}{tab}{usz}{lf}")
        os.replace(idx + ".part", idx)
    tlou2_ok = False
    if a.get("tlou2"):
        tlou2_ok = tlou2_inputs(a["tlou2"], os.environ["T2R_MAIN_ROOT"])
    import p1_levelset
    import p1_stage
    if getattr(sys, "frozen", False):                # PyInstaller: __file__ based paths point into the temp unpack dir
        p1_levelset.SPEC = os.path.join(sys._MEIPASS, "tools", "maps", "sp_maps.json")
        try:
            import sp_maps_build
            sp_maps_build.SPEC = p1_levelset.SPEC
        except Exception:
            pass
    emit(event="hello", version=VERSION, map=key)
    if not os.path.isdir(os.path.join(game, "build", "pc", "main")):
        raise SystemExit("not a Part I install: " + game)
    m = p1_levelset.spec(key)
    levels = m["part1"]["levels"]
    only = a.get("only")
    n = 4
    missing = []
    if m["part1"].get("rs-level") and p1_stage.p1_rs(m) and not tlou2_ok:
        os.environ["T2R_P1_RS"] = "0"                # render settings start from TLOU2's own t1x module: needs --tlou2
        missing += [p for p, _ in p1_stage.rs_files(m)]
        missing_note("render settings", "--tlou2 <TLOU2 game dir> is needed (the module they extend is TLOU2's own)")
    real = sys.stdout
    tidx = os.path.join(os.environ["T2R_MAIN_ROOT"], "re", "part1", "texdict-index.tsv")
    if a.get("tex_drop") is not None and not os.path.isfile(tidx):
        # the texture index (hash -> dict pak / payload range) from the player's own texturedict3 headers (p1_mapstudy.py index), once
        emit(event="stage", name="texindex", i=1, n=n)
        os.environ["T2R_REPO"] = os.environ["T2R_MAIN_ROOT"]
        import p1_mapstudy
        sys.stdout = Lines(1)
        try:
            p1_mapstudy.build_index(game, tidx + ".part")
        finally:
            sys.stdout = real
        os.replace(tidx + ".part", tidx)
    emit(event="stage", name="levels", i=1, n=n)
    sys.stdout = Lines(len(levels) * 3 if not only else len(only) * 3)        # converters print(); keep the real stdout for JSON
    try:
        p1_levelset.convert(game, key, a.get("tex_drop"), only)
    finally:
        sys.stdout = real
    if only:                                          # partial run (tests / one level): stage only what was converted
        m = dict(m, part1=dict(m["part1"], levels=only))
    # audio: p1_audio.convert (banks, streams, DC modules, region tree, spawner pak). The spawner pak is rewritten with the SceneEditor's package
    # writer through pwsh (p1_audio_spawners.ps1): present on the dev PC only
    audio = None
    if m["part1"].get("audio") and p1_stage.p1_audio_on():
        emit(event="stage", name="audio", i=2, n=n)
        if tlou2_ok:
            try:
                os.environ["T2R_P1_AUDIO_DIR"] = os.path.join(work, "audio")
                import p1_audio
                p1_audio.AUDIO = os.environ["T2R_P1_AUDIO_DIR"]
                sys.stdout = Lines(1)
                try:
                    p1_audio.convert(game, key)
                finally:
                    sys.stdout = real
                audio = p1_audio.load_manifest()
            except BaseException as e:               # SystemExit included: the converters raise it for "tool missing"
                if isinstance(e, KeyboardInterrupt):
                    raise
                missing.append("audio set (soundbank4/, sfx1/, audio DC modules, hun-const-audio paks)")
                missing_note("audio", f"{type(e).__name__}: {str(e)[:200]} (the spawner pak needs the SceneEditor package writer via pwsh)")
        else:
            missing.append("audio set (soundbank4/, sfx1/, audio DC modules, hun-const-audio paks)")
            missing_note("audio", "--tlou2 <TLOU2 game dir> is needed")
    # the staging: the SAME functions the build calls (p1_stage), into the output folder = the stage tree
    emit(event="stage", name="stage", i=3, n=n)
    sys.stdout = Lines(1)
    try:
        p1_stage.stage_levels(out, m, work)
        if p1_stage.p1_rs(m):
            p1_stage.stage_rs_files(out, m, work)
        if audio:
            p1_stage.stage_audio_files(out, os.environ["T2R_P1_AUDIO_DIR"], audio)
    finally:
        sys.stdout = real
    rels = ["pak68/" + f for f in p1_stage.level_files(m, work)] + [p for p, _ in p1_stage.rs_files(m)] + ([f["path"] for f in audio["files"]] if audio else [])
    files = []
    for rel in sorted(set(rels)):
        dst = os.path.join(out, *rel.split("/"))
        if rel in missing or not os.path.isfile(dst):
            if rel not in missing:
                missing.append(rel)
            continue
        files.append({"path": rel, "size": os.path.getsize(dst), "sha256": sha256_file(dst)})
        emit(event="file", **files[-1])
    emit(event="stage", name="finish", i=4, n=n)
    emit(event="done", files=len(files), bytes=sum(f["size"] for f in files), partial=bool(missing), missing=missing)
    return 0


def missing_note(what, why):
    emit(event="log", message=f"{what}: not produced - {why}")


def verify(a):
    """every file under --out (except the work dir and temp names) against a server manifest json / another folder"""
    import p1_fileset
    mine = {}
    for r, ds, fs in os.walk(a["out"]):
        ds[:] = [d for d in ds if d != ".work"]
        for f in fs:
            if f.endswith(".part") or f == "files.json":
                continue
            rel = os.path.relpath(os.path.join(r, f), a["out"]).replace(os.sep, "/")
            mine[rel] = sha256_file(os.path.join(r, f))
    if os.path.isdir(a["against"]):                   # a folder (a stage tree): every file of it, not only the ones we have
        other = {}
        for r, ds, fs in os.walk(a["against"]):
            for f in fs:
                if not f.endswith(".part") and f != "files.json":
                    other[os.path.relpath(os.path.join(r, f), a["against"]).replace(os.sep, "/")] = sha256_file(os.path.join(r, f))
    else:
        other = p1_fileset.load_side(a["against"], sorted(mine))
    same, oa, ob, diff = p1_fileset.compare(mine, other)
    emit(event="verify", same=len(same), only_out=oa, only_against=ob, different=diff)
    return 0 if not (oa or ob or diff) and same else 1


def parse(argv):
    a, rest = {"cmd": argv[1] if len(argv) > 1 else ""}, argv[2:]
    i = 0
    while i < len(rest):
        k = rest[i]
        if k.startswith("--only="):
            a["only"] = k.split("=", 1)[1].split(",")
        elif k in ("--part1", "--out", "--map", "--work", "--tex-drop", "--against", "--tlou2", "--in", "--drop") and i + 1 < len(rest):
            i += 1
            a[k[2:].replace("-", "_")] = int(rest[i]) if k == "--tex-drop" else rest[i]
        else:
            raise SystemExit("unknown argument " + k)
        i += 1
    return a


def main(argv):
    global _out
    _out = sys.stdout
    try:
        a = parse(argv)
        if a["cmd"] == "version":
            emit(event="version", version=VERSION)
            return 0
        if a["cmd"] == "convert" and a.get("part1") and a.get("out"):
            return convert(a)
        if a["cmd"] == "inputs" and a.get("tlou2") and a.get("out"):          # only the TLOU2 donor extraction (tests, support)
            tlou2_inputs(a["tlou2"], a["out"])
            emit(event="done", files=2, inputs=[os.path.join(a["out"], "re", "gamebin", "dc1", x) for x in ("modules.bin", "render-settings/t1x.bin")])
            return 0
        if a["cmd"] == "spawnerpak" and a.get("in") and a.get("out"):        # the audio spawner-pak rewrite alone (tests / support)
            import p1_spawner_pak
            data, kept, dropped = p1_spawner_pak.rewrite(open(a["in"], "rb").read(), tuple(x for x in a.get("drop", "").split(",") if x))
            open(a["out"], "wb").write(data)
            emit(event="done", kept=kept, dropped=dropped)
            return 0
        if a["cmd"] == "verify" and a.get("out") and a.get("against"):
            return verify(a)
        sys.stderr.write(__doc__)
        return 2
    except SystemExit as e:
        if isinstance(e.code, str):
            emit(event="error", message=e.code)
            return 1
        return e.code or 0
    except Exception as e:
        emit(event="error", message=f"{type(e).__name__}: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
