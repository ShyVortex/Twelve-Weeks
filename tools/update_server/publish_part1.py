#!/usr/bin/env python3
"""Publish the prebuilt Part I Bookstore file set for the launcher's "Download from server (temporary)" button. Publishes nothing else.

  python tools/update_server/publish_part1.py --stage <staged mod tree> --map p1-bookstore --data <update data dir> [--conv <conv dir>] [--pack part1-a] [--ver N]
  python tools/update_server/publish_part1.py <folder> --data <dir> [--pack ..]      # every file under <folder>, paths relative to it
  python tools/update_server/publish_part1.py --data <dir> --remove                  # take the pack offline (blobs kept until --gc)
  python tools/update_server/publish_part1.py --data <dir> --gc                      # delete blobs the manifest no longer names

The file set is the one sp_maps_build stages for the map (tools/part1/p1_fileset.py asks the build itself: the converted level paks, -phys / -ingame
as configured, the render-settings pak + bin/dc1/render-settings/t1x.bin, the audio paks / banks / streams / DC modules, the converted actor paks). The
bytes are read from the STAGED tree (the build patches lights / fires into the staged paks, so the conv dir alone is not the shipped set). Paths mirror
the in-game paths; the launcher writes them under <game dir>\\t2r-maps\\part1\\. Files are copied to <data>/part1/blobs/<sha256>, and
<data>/part1/manifest.json is written LAST (a half publish is invisible). Release manifests and blobs are not touched. Stdlib only.
"""
import argparse
import hashlib
import json
import os
import shutil
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import part1_maps


def sha256_file(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def tree_files(folder):
    out = []
    for r, _, names in os.walk(folder):
        for n in names:
            out.append(os.path.relpath(os.path.join(r, n), folder).replace(os.sep, "/"))
    return sorted(out)


def stage_files(stage, key, conv=None):
    """the build's own list for the map (needs tools/features importable: sp_maps_build + tools/part1)"""
    here = os.path.dirname(os.path.abspath(__file__))
    tools = os.path.dirname(here)
    sys.path.insert(0, os.path.join(tools, "part1"))
    sys.path.insert(0, os.path.join(tools, "features"))
    if conv:
        os.environ["T2R_P1_CONV"] = conv
    import p1_fileset
    return p1_fileset.bookstore_files(key)


def publish(folder, data, files=None, pack="part1-a", ver=1):
    """folder = tree the paths are relative to; files = the relative paths (default: all files under folder)"""
    files = sorted(files if files is not None else tree_files(folder))
    if not files:
        raise SystemExit("no files to publish")
    ents = []
    for rel in files:
        if not part1_maps.NAME_RE.match(rel):
            raise SystemExit("illegal path %r (relative, forward slashes, [A-Za-z0-9._+-] segments)" % rel)
        if not os.path.isfile(os.path.join(folder, *rel.split("/"))):
            raise SystemExit("missing file %s under %s" % (rel, folder))
    os.makedirs(part1_maps.blobs_dir(data), exist_ok=True)
    for rel in files:
        src = os.path.join(folder, *rel.split("/"))
        sha = sha256_file(src)
        dst = part1_maps.blob_path(data, sha)
        if not os.path.exists(dst) or sha256_file(dst) != sha:          # content check, not size: a damaged blob of the right size is replaced
            tmp = dst + ".tmp"
            try:
                shutil.copyfile(src, tmp)
                os.replace(tmp, dst)
            except BaseException:
                try:
                    os.unlink(tmp)
                except OSError:
                    pass
                raise
        ents.append({"path": rel, "sha256": sha, "size": os.path.getsize(src)})
    man = {"pack": pack, "ver": ver, "published": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "files": ents}
    out = os.path.join(part1_maps.root(data), "manifest.json")
    with open(out + ".tmp", "w", encoding="utf-8") as f:
        json.dump(man, f, indent=1)
    os.replace(out + ".tmp", out)                            # LAST
    return man


def remove(data):
    p = os.path.join(part1_maps.root(data), "manifest.json")
    if os.path.exists(p):
        os.unlink(p)


def gc(data, grace_hours=24):
    """Deletes blobs the manifest no longer names. Aborts (SystemExit) when the manifest is unreadable (a publish may be mid-replace: nothing is deleted
    on a guess) and leaves blobs younger than grace_hours (a publish writes its blobs before its manifest; a client may be mid-download)."""
    mp = os.path.join(part1_maps.root(data), "manifest.json")
    keep = set()
    if os.path.exists(mp):
        try:
            with open(mp, encoding="utf-8") as f:
                keep = {x["sha256"] for x in json.load(f)["files"]}
        except (OSError, ValueError, KeyError, TypeError):
            raise SystemExit("gc aborted: %s is unreadable, nothing deleted" % mp)
    n = 0
    now = time.time()
    d = part1_maps.blobs_dir(data)
    for b in os.listdir(d) if os.path.isdir(d) else []:
        p = os.path.join(d, b)
        if b in keep or b.endswith(".tmp") and now - os.path.getmtime(p) < 3600:
            continue
        if now - os.path.getmtime(p) < grace_hours * 3600:
            continue
        os.unlink(p)
        n += 1
    return n


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("folder", nargs="?")
    ap.add_argument("--data", required=True)
    ap.add_argument("--stage", help="staged mod tree of a build (with --map)")
    ap.add_argument("--map", default="p1-bookstore")
    ap.add_argument("--conv", help="conv dir the build used (T2R_P1_CONV)")
    ap.add_argument("--pack", default="part1-a")
    ap.add_argument("--ver", type=int, default=1)
    ap.add_argument("--remove", action="store_true")
    ap.add_argument("--gc", action="store_true")
    ap.add_argument("--gc-grace-hours", type=float, default=24)
    a = ap.parse_args()
    if a.remove:
        remove(a.data)
        print("Part I map pack taken offline")
    elif a.gc:
        print("removed %d unused Part I blobs" % gc(a.data, a.gc_grace_hours))
    elif a.stage:
        m = publish(a.stage, a.data, stage_files(a.stage, a.map, a.conv), a.pack, a.ver)
        print("published %s v%s: %d files, %d bytes" % (m["pack"], m["ver"], len(m["files"]), sum(f["size"] for f in m["files"])))
    else:
        if not a.folder:
            ap.error("folder or --stage required")
        m = publish(a.folder, a.data, None, a.pack, a.ver)
        print("published %s v%s: %d files, %d bytes" % (m["pack"], m["ver"], len(m["files"]), sum(f["size"] for f in m["files"])))


if __name__ == "__main__":
    main()
