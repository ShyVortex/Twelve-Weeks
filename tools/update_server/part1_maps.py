"""Part I map pack (TEMPORARY playtester download), served separately from the client release.

The release manifest (/manifest.json) never lists these files: they live in their own folder, <data>/part1/,
with their own manifest, so a client publish / gc / rollback can neither include nor delete them.

  <data>/part1/manifest.json    {"pack": "part1-a", "ver": 1, "published": "...", "files": [{"path", "sha256", "size"}]}   path = where the file goes under <game dir>\t2r-maps\part1\ (mirrors the in-game path)
  <data>/part1/blobs/<sha256>   the files, content addressed (raw bytes, HTTP Range)

Endpoints (wired into server.py):
  GET /part1-maps.json            the manifest with "url" per file, or 404 {"error": "no Part I map pack published"}
  GET /part1-files/<sha256>       one file, Range supported (same sender as /files/)

Files are the launcher's <game dir>\\t2r-maps\\ pack: the archive(s) (.psarc) and the pack manifest (.txt, written LAST by the launcher).
Publish with tools/update_server/publish_part1.py.
"""
import json
import os
import re
import time

SHA_RE = re.compile(r"^[0-9a-f]{64}$")
SEG = r"[A-Za-z0-9][A-Za-z0-9._+-]{0,79}"
NAME_RE = re.compile(r"^(?:%s/){0,5}%s$" % (SEG, SEG))      # forward-slash relative path (the in-game path, e.g. pak68/x.pak): every segment starts alphanumeric, so no "..", no absolute path
DIR = "part1"


def root(data):
    return os.path.join(data, DIR)


def blobs_dir(data):
    return os.path.join(root(data), "blobs")


def blob_path(data, sha):
    if not SHA_RE.match(sha or ""):
        return None
    return os.path.join(blobs_dir(data), sha)


def load(data):
    """The published manifest if it is complete and sane (every file name legal, every blob present with its size), else None."""
    p = os.path.join(root(data), "manifest.json")
    m = None
    for i in range(8):                     # publish_part1.py replaces it with os.replace: a Windows reader can hit PermissionError for an instant
        try:
            with open(p, encoding="utf-8") as f:
                m = json.load(f)
            break
        except FileNotFoundError:
            return None
        except (OSError, ValueError):
            if i == 7:
                return None
            time.sleep(0.02 * (i + 1))
    if not isinstance(m, dict) or not isinstance(m.get("files"), list) or not m["files"]:
        return None
    for f in m["files"]:
        if not isinstance(f, dict) or not NAME_RE.match(str(f.get("path", ""))) or not SHA_RE.match(str(f.get("sha256", ""))):
            return None
        if not isinstance(f.get("size"), int) or f["size"] < 0:
            return None
        try:
            if os.path.getsize(blob_path(data, f["sha256"])) != f["size"]:
                return None                # a publish still copying, or a blob damaged by hand: not offered
        except OSError:
            return None
    return m


def public(data, base):
    """What /part1-maps.json answers: the manifest plus absolute urls, or None."""
    m = load(data)
    if not m:
        return None
    out = json.loads(json.dumps(m))
    for f in out["files"]:
        f["url"] = base.rstrip("/") + "/part1-files/" + f["sha256"]
    out["total"] = sum(f["size"] for f in out["files"])
    return out
