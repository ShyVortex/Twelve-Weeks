"""T2R_P1_SIDE=1: Part I-derived files leave the winmm blob and go to a side tree (re/launcher/part1-dlc.md s7.3, re/part1/side-files.md).

Why: the blob (embedded in the winmm image) is near the image-size limit, and the mod ships no Part I-derived bytes. The launcher puts the
side tree at <game dir>/t2r-maps/part1/ (path under it == the in-game relative path, e.g. pak68/hun-checkpoint-bookstore.pak).

  build side   extract(stage, rel_paths, paths, order, outdir)  moves the files out of the staged mod tree, drops them from the archive
               manifest lists (build_dll's `paths` / `order`) and writes <outdir>/manifest.txt (+ manifest.json) LAST.
               verify_blob(paths, order, entries)  -> problems (a Part I path still in the blob, a manifest entry without a file ...)
  manifest.txt one line per file, tab separated, header first:   p1side 1 <n files> <total bytes>
                                                                <rel path>\t<size>\t<sha256 hex>
               (a text file so the ext reads it without a JSON parser; the ext checks existence + size of every entry and the CRC-32 of the
               manifest text itself against the value baked into the DLL build, tools/ext/p1side_built.h)
  kept in blob bin/dc1/*.bin (the render-settings t1x module, the three audio carrier modules): modules.bin registers their size and export
               lists at boot, so a missing file would change DC loading for EVERY player. They stay in the blob unless T2R_P1_SIDE_MODULES=1
               (only once the side serving is proven to be live before the DC modules load).
"""
import hashlib
import json
import os
import shutil
import zlib

MANIFEST = "manifest.txt"
MANIFEST_JSON = "manifest.json"
VERSION = 1


def enabled():
    return os.environ.get("T2R_P1_SIDE", "") in ("1", "virt", "tree")


def virt():
    """T2R_P1_SIDE=1 (or virt): the Part I data becomes the cut-off tail of the mod archive, shipped as part1.dat and mapped behind the blob by the
    winmm cave (p1_side_map.py). T2R_P1_SIDE=tree: loose files in a side tree (extract(); nothing serves them yet)"""
    return enabled() and os.environ.get("T2R_P1_SIDE") != "tree"


def modules_too():
    return os.environ.get("T2R_P1_SIDE_MODULES", "") == "1"


def out_dir(root):
    return os.environ.get("T2R_P1_SIDE_OUT") or os.path.join(root, "tools", "local", "p1side")


def is_module(rel):
    return rel.startswith("bin/dc1/")


def split(rel_paths, modules=None):
    """(side, kept): rel paths that go to the side tree / stay in the blob (modules unless T2R_P1_SIDE_MODULES=1); sorted, unique"""
    side, kept = [], []
    for p in sorted(set(rel_paths)):
        (kept if is_module(p) and not (modules_too() if modules is None else modules) else side).append(p)
    return side, kept


def _sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            b = f.read(1 << 22)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


def manifest_text(entries):
    """entries: [(rel, size, sha256)] -> the manifest.txt text (sorted by path, LF, trailing newline)"""
    entries = sorted(entries)
    lines = [f"p1side {VERSION} {len(entries)} {sum(e[1] for e in entries)}"]
    lines += [f"{p}\t{s}\t{h}" for p, s, h in entries]
    return "\n".join(lines) + "\n"


def parse_manifest(text):
    """-> [(rel, size, sha256)]; raises ValueError on a malformed manifest (header count / total, bad line, duplicate, unsafe path)"""
    lines = text.split("\n")
    if lines and lines[-1] == "":
        lines.pop()
    hd = lines[0].split(" ") if lines else []
    if len(hd) != 4 or hd[0] != "p1side" or hd[1] != str(VERSION):
        raise ValueError("bad header")
    out, seen = [], set()
    for ln in lines[1:]:
        c = ln.split("\t")
        if len(c) != 3 or not c[1].isdigit() or len(c[2]) != 64:
            raise ValueError("bad line: " + ln[:80])
        p = c[0]
        if not p or p.startswith("/") or "\\" in p or ".." in p.split("/") or ":" in p or p in seen:
            raise ValueError("bad path: " + p)
        seen.add(p)
        out.append((p, int(c[1]), c[2]))
    if len(out) != int(hd[2]) or sum(e[1] for e in out) != int(hd[3]):
        raise ValueError("header count / total do not match the lines")
    return out


def manifest_crc(text):
    return zlib.crc32(text.encode("utf-8")) & 0xFFFFFFFF


def extract(stage, rel_paths, paths, order, outdir, log=print):
    """move the Part I files out of the staged mod tree `stage` into `outdir`, remove them from the `paths` / `order` lists in place,
    write outdir/manifest.txt (+ .json) last. -> {"entries": [...], "kept": [...], "crc": int, "bytes": int}"""
    side, kept = split(rel_paths)
    if os.path.isdir(outdir):
        shutil.rmtree(outdir)           # a side tree is exactly one build's files
    os.makedirs(outdir)
    entries = []
    for rel in side:
        src = os.path.join(stage, *rel.split("/"))
        if not os.path.exists(src):
            raise FileNotFoundError(f"p1 side: {rel} is in the Part I file set but not in the staged mod tree")
        dst = os.path.join(outdir, *rel.split("/"))
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.move(src, dst)
        entries.append((rel, os.path.getsize(dst), _sha256(dst)))
        for lst in (paths, order):
            while rel in lst:
                lst.remove(rel)
    text = manifest_text(entries)
    with open(os.path.join(outdir, MANIFEST_JSON), "w", newline="\n") as f:
        json.dump({"version": VERSION, "files": [{"path": p, "size": s, "sha256": h} for p, s, h in sorted(entries)],
                   "kept-in-blob": kept}, f, indent=1)
    with open(os.path.join(outdir, MANIFEST), "w", newline="\n", encoding="utf-8") as f:
        f.write(text)
    tot = sum(e[1] for e in entries)
    log(f"p1 side: {len(entries)} Part I files ({tot / 1e6:.1f} MB) moved out of the blob into {outdir}; {len(kept)} DC modules kept in the blob; manifest crc {manifest_crc(text):08x}")
    return {"entries": entries, "kept": kept, "crc": manifest_crc(text), "bytes": tot}


def verify_blob(paths, order, entries, stage=None):
    """problems (empty = OK): a side entry still in the archive manifest lists / the staged tree, or a duplicate"""
    bad = []
    for rel, _s, _h in entries:
        for name, lst in (("paths", paths), ("order", order)):
            if rel in lst:
                bad.append(f"{rel} still in the blob manifest ({name})")
        if stage and os.path.exists(os.path.join(stage, *rel.split("/"))):
            bad.append(f"{rel} still staged")
    return bad


def verify_tree(outdir, deep=True):
    """problems of a finished side tree: manifest parses, every file exists with its size (and sha256 when deep), no stray files"""
    bad = []
    try:
        text = open(os.path.join(outdir, MANIFEST), encoding="utf-8", newline="").read()
        entries = parse_manifest(text)
    except (OSError, ValueError) as e:
        return [f"manifest: {e}"]
    want = set()
    for rel, size, sha in entries:
        f = os.path.join(outdir, *rel.split("/"))
        want.add(rel)
        if not os.path.exists(f):
            bad.append(f"missing {rel}")
        elif os.path.getsize(f) != size:
            bad.append(f"size {rel}")
        elif deep and _sha256(f) != sha:
            bad.append(f"sha256 {rel}")
    for dp, _dn, fn in os.walk(outdir):
        for n in fn:
            rel = os.path.relpath(os.path.join(dp, n), outdir).replace("\\", "/")
            if rel not in want and rel not in (MANIFEST, MANIFEST_JSON):
                bad.append(f"stray {rel}")
    return bad


def audit_entries(stage, rel_paths):
    """[(rel, size, sha256)] of the staged side files (virt mode: the files stay in the stage; they are split off at pack time)"""
    out = []
    for rel in sorted(rel_paths):
        f = os.path.join(stage, *rel.split("/"))
        if not os.path.exists(f):
            raise FileNotFoundError(f"p1 side: {rel} is in the Part I file set but not in the staged mod tree")
        out.append((rel, os.path.getsize(f), _sha256(f)))
    return out


def write_virt_outputs(outdir, entries, kept, side_bytes, log=print):
    """virt mode deliverables: part1.dat (the side file), manifest.txt (the launcher's: ONE entry, part1.dat with its size and sha256),
    files.txt / files.json (audit: the logical Part I files inside it)"""
    os.makedirs(outdir, exist_ok=True)
    dat = os.path.join(outdir, "part1.dat")
    with open(dat, "wb") as f:
        f.write(side_bytes)
    sha = hashlib.sha256(side_bytes).hexdigest()
    text = manifest_text([("part1.dat", len(side_bytes), sha)])
    with open(os.path.join(outdir, MANIFEST), "w", newline="\n", encoding="utf-8") as f:
        f.write(text)
    with open(os.path.join(outdir, "files.txt"), "w", newline="\n", encoding="utf-8") as f:
        f.write(manifest_text(entries))
    with open(os.path.join(outdir, "files.json"), "w", newline="\n") as f:
        json.dump({"version": VERSION, "files": [{"path": p, "size": s, "sha256": h} for p, s, h in sorted(entries)], "kept-in-blob": kept}, f, indent=1)
    log(f"p1 side: {dat}: {len(side_bytes) / 1e6:.1f} MB, {len(entries)} Part I files inside; manifest crc {manifest_crc(text):08x}")
    return {"sha256": sha, "size": len(side_bytes), "crc": manifest_crc(text)}


def write_ext_header(path, crc=None, n=0, total=0, mask=0, virt=False):
    """tools/ext/p1side_built.h (generated, git-ignored): what THIS build expects of the side tree. Written on EVERY build; without side mode
    T2R_P1_SIDE_BUILT is 0 and the ext's Part I guard is inert (the maps, if any, are in the blob)."""
    text = ("// generated by tools/features/p1_side.py - do not edit, do not commit\n"
            f"#define T2R_P1_SIDE_BUILT {2 if virt else (1 if crc is not None else 0)}   // 0 off, 1 loose side tree (manifest crc), 2 virtual region (winmm .t2rps descriptor)\n"
            f"#define T2R_P1_SIDE_CRC 0x{(crc or 0):08x}u    // CRC-32 of <game dir>\\t2r-maps\\part1\\manifest.txt\n"
            f"#define T2R_P1_SIDE_FILES {n}\n"
            f"#define T2R_P1_SIDE_BYTES {total}ull\n"
            f"#define T2R_P1_SIDE_MASK 0x{mask:04x}u    // bit k = map-list index 8 + k: the SP-section maps whose levels are in the side tree\n")
    old = open(path, encoding="utf-8").read() if os.path.exists(path) else None
    if old != text:
        with open(path, "w", encoding="utf-8", newline="\n") as f:
            f.write(text)


# ------------------------------------------------------------------ native archive form (re/part1/side-files.md "Mounting")
def pack_archive(outdir, archive, log=print):
    """Pack the side tree (outdir, manifest.txt) into ONE stock-format archive: PSARC (raw 64 KiB blocks, TOC by MD5(path)) inside DSAR (lz4
    chunks, tag 0x...503, never stored chunks) = exactly the layers of the blob and of the game's own build/pc/main/*.psarc, WITHOUT the
    T2ME wrapper / keystream / file-offset rebase (a real file: the DSAR offsets are file offsets, so the engine reads it natively).
    -> {"size", "crc32", "sha256", "paths"}; round-trip checked."""
    import sys
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
    import t2r_pack
    entries = parse_manifest(open(os.path.join(outdir, MANIFEST), encoding="utf-8", newline="").read())
    paths = sorted(e[0] for e in entries)
    files = {}
    for p in paths:
        with open(os.path.join(outdir, *p.split("/")), "rb") as f:
            files[p] = f.read()
    meta = {"flags": 12, "paths": paths, "data_order": paths, "trail": False}
    psar, cuts = t2r_pack.psarc_write(meta, files)
    dsar = t2r_pack.dsar_write(psar, cuts)
    m2, f2 = t2r_pack.psarc_read(t2r_pack.dsar_read(dsar))
    assert f2 == files and m2["paths"] == paths, "p1 side archive: round trip mismatch"
    with open(archive, "wb") as f:
        f.write(dsar)
    log(f"p1 side: {archive}: {len(paths)} files, {len(dsar) / 1e6:.1f} MB (psarc in dsar, lz4)")
    return {"size": len(dsar), "crc32": zlib.crc32(dsar) & 0xFFFFFFFF, "sha256": hashlib.sha256(dsar).hexdigest(), "paths": paths}


def write_pack_manifest(path, pack_id, ver, archive_name, info, maps):
    """<id>.txt in tools/map_packs format (re/part1/map-packs.md s2): id/ver/hash(CRC-32 hex of the archive)/file/size/map=<level>|<name>|<img key>.
    Written LAST, after the archive."""
    lines = [f"id={pack_id}", f"ver={ver}", f"hash={info['crc32']:08x}", f"file={archive_name}", f"size={info['size']}"]
    lines += [f"map={lv}|{name}|{img}" for lv, name, img in maps]
    with open(path, "w", newline="\n", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
