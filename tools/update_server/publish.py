#!/usr/bin/env python3
"""Publish a built client folder to the update server's data dir.

  python tools/update_server/publish.py <client folder> --data <dir> --channel stable --version 74
         [--launcher <installer.exe> --launcher-version 1.0.0] [--no-promote]

Every file is hashed (sha256) and stored once under <data>/blobs/<sha256> (identical files across versions or paths share
one blob). A manifest <data>/manifests/<channel>/<version>.json is written and, unless --no-promote, the channel points at it.
Old manifests and blobs are kept so a rollback is `--promote-only --version OLD`. `--gc N` drops blobs not used by the
newest N versions of any channel (off by default).

Compressed transfer: next to each blob that compresses by >= 5 % a <sha256>.gz (gzip -9) or <sha256>.br (brotli q9, 16 MiB window,
when the python `brotli` module is installed; `--codec gzip` forces gzip) is written and the manifest entry gains
{"zsize": N, "enc": "gzip"|"br"}; the server adds "zurl". Blobs that do not shrink get an empty <sha256>.nz marker (so they are not
retried). `--recompress` adds compressed blobs + manifest fields to every already published version (no folder needed).
Raw blobs and the old manifest fields are untouched, so old launchers keep working. --no-compress turns it off.
"""
import argparse
import hashlib
import json
import os
import shutil
import sys
import time
import zlib

try:
    import brotli
except ImportError:
    brotli = None

SKIP_NAMES = {"t2r-play.log", "Thumbs.db", ".DS_Store", "linux-config.json", "t2r-client.json"}


def sha256_file(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for c in iter(lambda: f.read(1 << 20), b""):
            h.update(c)
    return h.hexdigest()


def store_blob(data, src):
    sha = sha256_file(src)
    dst = os.path.join(data, "blobs", sha)
    new = not os.path.exists(dst) or os.path.getsize(dst) != os.path.getsize(src)     # (a blob of the wrong size is rewritten)
    if new:
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        tmp = dst + ".tmp"
        try:
            shutil.copyfile(src, tmp)
            os.replace(tmp, dst)
        except BaseException:                  # disk full / interrupted: no half blob under its final name, no stray temp
            try:
                os.remove(tmp)
            except OSError:
                pass
            raise
    return sha, os.path.getsize(src), new


MIN_SAVING = 0.05
EXT_OF = {"gzip": ".gz", "br": ".br"}


def _compress_to(src, dst, codec):
    """Streams src -> dst (deterministic bytes), returns the compressed size."""
    if codec == "gzip":
        c = zlib.compressobj(9, zlib.DEFLATED, 31)          # wbits 31 = gzip container
    else:
        c = brotli.Compressor(quality=9, lgwin=24)
    with open(src, "rb") as i, open(dst, "wb") as o:
        for chunk in iter(lambda: i.read(1 << 22), b""):
            o.write(c.compress(chunk) if codec == "gzip" else c.process(chunk))
        o.write(c.flush() if codec == "gzip" else c.finish())
    return os.path.getsize(dst)           # (after the with: closed and flushed)


def pick_codec(codec="auto"):
    if codec == "auto":
        return "br" if brotli else "gzip"
    if codec == "br" and not brotli:
        raise SystemExit("--codec br needs: pip install brotli")
    return codec


def ensure_compressed(data, sha, src, codec="auto"):
    """Makes <blobs>/<sha>.<ext> if it saves >= 5 %; returns (zsize, enc) or None. Idempotent (existing .gz/.br/.nz are reused)."""
    base = os.path.join(data, "blobs", sha)
    for enc, ext in EXT_OF.items():
        if os.path.exists(base + ext):
            return os.path.getsize(base + ext), enc
    if os.path.exists(base + ".nz"):
        return None
    size = os.path.getsize(src)
    if size == 0:
        return None
    enc = pick_codec(codec)
    dst = base + EXT_OF[enc]
    tmp = dst + ".tmp"
    zsize = _compress_to(src, tmp, enc)
    if zsize > size * (1 - MIN_SAVING):
        os.remove(tmp)
        open(base + ".nz", "wb").close()
        return None
    os.replace(tmp, dst)
    return zsize, enc


def write_json(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, indent=1)
    for i in range(10):                        # Windows: a reader (the server) holding the file for a moment makes the replace fail
        try:
            os.replace(tmp, path)
            return
        except PermissionError:
            if i == 9:
                raise
            time.sleep(0.1 * (i + 1))


def publish(folder, data, channel, version, promote=True, compress=True, codec="auto"):
    files, added, reused = [], 0, 0
    for root, dirs, names in os.walk(folder):
        dirs.sort()
        for n in sorted(names):
            if n in SKIP_NAMES:
                continue
            full = os.path.join(root, n)
            rel = os.path.relpath(full, folder).replace(os.sep, "/")
            sha, size, new = store_blob(data, full)
            ent = {"path": rel, "size": size, "sha256": sha}
            z = ensure_compressed(data, sha, full, codec) if compress else None
            if z:
                ent["zsize"], ent["enc"] = z
            files.append(ent)
            added += new
            reused += not new
    if not files:
        raise SystemExit("no files in %s" % folder)
    write_json(os.path.join(data, "manifests", channel, version + ".json"),
               {"version": version, "channel": channel, "files": files})
    if promote:
        promote_version(data, channel, version)
    return {"files": len(files), "new_blobs": added, "reused_blobs": reused}


def recompress(data, codec="auto"):
    """Adds compressed blobs + zsize/enc to every published manifest (raw blobs are the source)."""
    mdir = os.path.join(data, "manifests")
    done = {}
    n = 0
    for ch in sorted(os.listdir(mdir)):
        for fn in sorted(os.listdir(os.path.join(mdir, ch))):
            if not fn.endswith(".json"):
                continue
            mp = os.path.join(mdir, ch, fn)
            m = json.load(open(mp, encoding="utf-8"))
            for ent in m["files"]:
                sha = ent["sha256"]
                if sha not in done:
                    raw = os.path.join(data, "blobs", sha)
                    done[sha] = ensure_compressed(data, sha, raw, codec) if os.path.exists(raw) else None
                    n += bool(done[sha])
                z = done[sha]
                if z:
                    ent["zsize"], ent["enc"] = z
                else:
                    ent.pop("zsize", None)
                    ent.pop("enc", None)
            write_json(mp, m)
    return {"compressed_blobs": n, "manifests_updated": True}


def verify_version(data, channel, version):
    """Every blob the manifest names must exist with the manifest's size, or the channel must not point at it."""
    mp = os.path.join(data, "manifests", channel, version + ".json")
    if not os.path.exists(mp):
        raise SystemExit("no such version %s in channel %s" % (version, channel))
    with open(mp, encoding="utf-8") as f:
        m = json.load(f)
    bad = []
    for ent in m["files"]:
        p = os.path.join(data, "blobs", ent["sha256"])
        if not os.path.isfile(p) or os.path.getsize(p) != ent["size"]:
            bad.append(ent["path"])
    if bad:
        raise SystemExit("not promoting %s/%s: %d blob(s) missing or the wrong size (%s)" % (channel, version, len(bad), ", ".join(bad[:5])))


def promote_version(data, channel, version):
    verify_version(data, channel, version)
    p = os.path.join(data, "channels.json")
    cur = {}
    if os.path.exists(p):
        with open(p, encoding="utf-8") as f:
            cur = json.load(f)
    cur[channel] = version
    write_json(p, cur)


def set_launcher(data, installer, version):
    sha, size, _ = store_blob(data, installer)
    write_json(os.path.join(data, "launcher.json"),
               {"version": version, "sha256": sha, "size": size, "file": os.path.basename(installer)})


def gc(data, keep, grace_hours=24):
    """Drops blobs no longer needed. Kept: the newest `keep` versions per channel, the version each channel POINTS AT (a rollback makes an old
    one current), any version dropped less than grace_hours ago (a client may still be mid-download of it), launcher.json's blob, and every blob
    younger than grace_hours (a publish in progress has its blobs before its manifest). Never fails on a blob a download holds open."""
    used = set()
    now = time.time()
    grace = grace_hours * 3600
    mdir = os.path.join(data, "manifests")
    cur = {}
    try:
        with open(os.path.join(data, "channels.json"), encoding="utf-8") as f:
            cur = json.load(f)
    except (OSError, ValueError):
        pass
    for ch in os.listdir(mdir):
        d = os.path.join(mdir, ch)
        names = [n for n in os.listdir(d) if n.endswith(".json")]
        names.sort(key=lambda n: os.path.getmtime(os.path.join(d, n)))
        vs = set(names[-keep:])
        if cur.get(ch) and cur[ch] + ".json" in names:
            vs.add(cur[ch] + ".json")
        vs |= {n for n in names if now - os.path.getmtime(os.path.join(d, n)) < grace}
        for v in vs:
            used |= {f["sha256"] for f in json.load(open(os.path.join(d, v), encoding="utf-8"))["files"]}
    la = os.path.join(data, "launcher.json")
    if os.path.exists(la):
        used.add(json.load(open(la))["sha256"])
    n = 0
    for b in os.listdir(os.path.join(data, "blobs")):
        p = os.path.join(data, "blobs", b)
        if b.split(".")[0] not in used:
            try:
                if now - os.path.getmtime(p) < grace:
                    continue
                os.remove(p)
                n += 1
            except OSError:
                pass
    return n


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("folder", nargs="?")
    ap.add_argument("--data", required=True)
    ap.add_argument("--channel", default="stable")
    ap.add_argument("--version")
    ap.add_argument("--no-promote", action="store_true")
    ap.add_argument("--promote-only", action="store_true", help="point the channel at an already published --version (rollback)")
    ap.add_argument("--no-compress", action="store_true", help="do not write compressed blobs")
    ap.add_argument("--codec", default="auto", choices=["auto", "gzip", "br"])
    ap.add_argument("--recompress", action="store_true", help="add compressed blobs/manifest fields to all published versions")
    ap.add_argument("--launcher", help="launcher installer to publish (served as manifest.launcher)")
    ap.add_argument("--launcher-version")
    ap.add_argument("--gc", type=int, default=0, help="delete blobs unused by the newest N versions per channel")
    ap.add_argument("--gc-grace-hours", type=float, default=24, help="gc keeps blobs and versions younger than this (clients may be mid-download, a publish may be running)")
    a = ap.parse_args()
    os.makedirs(os.path.join(a.data, "blobs"), exist_ok=True)
    if a.launcher:
        if not a.launcher_version:
            sys.exit("--launcher needs --launcher-version")
        set_launcher(a.data, a.launcher, a.launcher_version)
        print("launcher %s published" % a.launcher_version)
    if a.recompress:
        print(recompress(a.data, a.codec))
    if a.promote_only:
        if not a.version:
            sys.exit("--promote-only needs --version")
        promote_version(a.data, a.channel, a.version)
        print("%s -> %s" % (a.channel, a.version))
    elif a.folder:
        if not a.version:
            vf = os.path.join(a.folder, "version.txt")
            if not os.path.exists(vf):
                sys.exit("--version missing and no version.txt in the folder")
            a.version = open(vf, encoding="utf-8").read().strip()
        print(publish(a.folder, a.data, a.channel, a.version, not a.no_promote, not a.no_compress, a.codec))
    if a.gc:
        print("gc removed %d blobs" % gc(a.data, a.gc, a.gc_grace_hours))


if __name__ == "__main__":
    main()
