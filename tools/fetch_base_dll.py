"""Put the unpatched winmm.dll that tools/features/build_dll.py patches into tools/local/.

The base binary is not in git. Get it from a team member or from a download link they give you, then run:

  python tools/fetch_base_dll.py --from <path to the dll>
  python tools/fetch_base_dll.py --url <https link to the dll>

The script checks the file's SHA-256 and copies it to tools/local/winmm-nocave-127.0.0.1-7001.dll.
A different file (for example the patched winmm.dll from a game install) is refused: the offset-based
patches only fit this exact binary.
"""
import argparse
import hashlib
import os
import shutil
import sys
import tempfile
import urllib.request

SHA256 = "9faa5a0c4ace569fd1eb80e9df62db903b903370f2fb14a7c65f650c25f0d727"
SIZE = 163262464
HERE = os.path.dirname(os.path.abspath(__file__))
DEST = os.path.join(HERE, "local", "winmm-nocave-127.0.0.1-7001.dll")


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--from", dest="path", help="a local copy of the base dll")
    src.add_argument("--url", help="an https link to the base dll")
    a = ap.parse_args()
    tmp = None
    if a.url:
        if not a.url.startswith("https://"):
            sys.exit("only https links are accepted")
        fd, tmp = tempfile.mkstemp(suffix=".dll")
        os.close(fd)
        print("downloading", a.url)
        with urllib.request.urlopen(a.url) as r, open(tmp, "wb") as f:
            shutil.copyfileobj(r, f, 1 << 20)
        path = tmp
    else:
        path = a.path
    try:
        size = os.path.getsize(path)
        got = sha256(path)
        if got != SHA256:
            sys.exit(f"wrong file: SHA-256 {got} ({size} bytes), expected {SHA256} ({SIZE} bytes)")
        os.makedirs(os.path.dirname(DEST), exist_ok=True)
        shutil.copyfile(path, DEST)
        print("ok:", DEST)
    finally:
        if tmp and os.path.exists(tmp):
            os.remove(tmp)


if __name__ == "__main__":
    main()
