"""Reproducible build of the Steam P2P helper release/client/steam/t2r-steam.exe from release/client/steam/t2r-steam.c.

  python tools/steam/build_helper.py                    build into <T2R_TMP or temp>/t2r-steam.exe (never touches the committed exe)
  python tools/steam/build_helper.py --out PATH         build to PATH
  python tools/steam/build_helper.py --install          build, overwrite the committed exe and write the stamp file
  python tools/steam/build_helper.py --check            committed exe vs a fresh build of the committed source (normalised compare)
  python tools/steam/build_helper.py --stamp-check      no compiler: committed .c hash must equal the hash in t2r-steam.exe.stamp

Fixed toolchain flags (FLAGS below): MSYS2 UCRT64 gcc, -O2 -s -static, -Wl,--no-insert-timestamp (PE TimeDateStamp = 0, so the same
source + same gcc gives the same bytes). The compare ignores the PE TimeDateStamp and CheckSum anyway, so an exe built by an older
build without the linker flag still compares equal (the committed one is such a build: proven identical to 36a7455d's source).
release/build_release.py only COPIES the committed exe, so after editing t2r-steam.c run --install and commit exe + stamp together.
gcc lookup: env T2R_GCC, <repo>/tools/win/ext/msys64/ucrt64/bin/gcc.exe, the main checkout of this repo (git worktrees do not carry
tools/win), then gcc on PATH. Linux players run the SAME exe through Proton (release/client/t2r-linux.py) - there is no separate build.
"""
import argparse
import hashlib
import os
import struct
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
STEAM = os.path.join(ROOT, "release", "client", "steam")
SRC = os.path.join(STEAM, "t2r-steam.c")
EXE = os.path.join(STEAM, "t2r-steam.exe")
STAMP = os.path.join(STEAM, "t2r-steam.exe.stamp")
FLAGS = ["-O2", "-s", "-static", "-Wl,--no-insert-timestamp"]
LIBS = ["-lws2_32", "-lwinmm"]


def find_gcc():
    cands = [os.environ.get("T2R_GCC")]
    rel = os.path.join("tools", "win", "ext", "msys64", "ucrt64", "bin", "gcc.exe")
    cands.append(os.path.join(ROOT, rel))
    try:  # worktree: the main checkout is the parent of the common git dir
        cd = subprocess.run(["git", "rev-parse", "--git-common-dir"], cwd=ROOT, capture_output=True, text=True).stdout.strip()
        if cd:
            cands.append(os.path.join(os.path.dirname(os.path.abspath(os.path.join(ROOT, cd))), rel))
    except OSError:
        pass
    for c in cands:
        if c and os.path.isfile(c):
            return c
    return None


def src_hash(path=SRC):
    d = open(path, "rb").read().replace(b"\r\n", b"\n")
    return hashlib.sha256(d).hexdigest()


def normalise(b):
    """Zero the build-dependent PE fields: file-header TimeDateStamp, optional-header CheckSum, debug-directory timestamps."""
    b = bytearray(b)
    pe = struct.unpack_from("<I", b, 0x3C)[0]
    assert b[pe:pe + 4] == b"PE\0\0", "not a PE file"
    struct.pack_into("<I", b, pe + 8, 0)
    opt = pe + 24
    struct.pack_into("<I", b, opt + 64, 0)
    magic = struct.unpack_from("<H", b, opt)[0]
    dd = opt + (112 if magic == 0x20B else 96)
    rva, size = struct.unpack_from("<II", b, dd + 6 * 8)
    if rva and size:
        nsec = struct.unpack_from("<H", b, pe + 6)[0]
        soh = struct.unpack_from("<H", b, pe + 20)[0]
        for i in range(nsec):
            s = pe + 24 + soh + i * 40
            vsz, va, rsz, raw = struct.unpack_from("<IIII", b, s + 8)
            if va <= rva < va + max(vsz, rsz):
                o = raw + (rva - va)
                for k in range(size // 28):
                    struct.pack_into("<I", b, o + k * 28 + 4, 0)
                break
    return bytes(b)


def build(out, src=SRC):
    gcc = find_gcc() or "gcc"
    env = dict(os.environ, SOURCE_DATE_EPOCH="0")
    if os.path.isabs(gcc):
        env["PATH"] = os.path.dirname(gcc) + os.pathsep + env.get("PATH", "")
    r = subprocess.run([gcc] + FLAGS + ["-o", out, src] + LIBS, env=env, capture_output=True, text=True, cwd=os.path.dirname(src))
    if r.returncode:
        sys.exit("build failed:\n" + r.stderr)
    return gcc


def same(a, b):
    return normalise(open(a, "rb").read()) == normalise(open(b, "rb").read())


def read_stamp():
    d = {}
    if os.path.isfile(STAMP):
        for ln in open(STAMP, encoding="utf-8"):
            if "=" in ln:
                k, v = ln.strip().split("=", 1)
                d[k] = v
    return d


def stamp_check():
    st = read_stamp()
    if st.get("src_sha256") != src_hash():
        return ("t2r-steam.c changed since the committed t2r-steam.exe was built (stamp %s, source %s): run "
                "python tools/steam/build_helper.py --install and commit exe + stamp" % (st.get("src_sha256", "missing")[:12], src_hash()[:12]))
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out")
    ap.add_argument("--install", action="store_true")
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--stamp-check", action="store_true")
    a = ap.parse_args()
    if a.stamp_check:
        e = stamp_check()
        print(e or "stamp OK")
        sys.exit(1 if e else 0)
    tmp = os.environ.get("T2R_TMP") or tempfile.gettempdir()
    if a.check:
        out = os.path.join(tmp, "t2r-steam-check.exe")
        build(out)
        ok = same(out, EXE)
        print("committed exe %s a fresh build of the committed source" % ("MATCHES" if ok else "DIFFERS from"))
        sys.exit(0 if ok else 1)
    out = EXE if a.install else (a.out or os.path.join(tmp, "t2r-steam.exe"))
    gcc = build(out)
    print("built %s (%d bytes) with %s" % (out, os.path.getsize(out), gcc))
    if a.install:
        open(STAMP, "w", encoding="utf-8").write("src_sha256=%s\nflags=%s\n" % (src_hash(), " ".join(FLAGS + LIBS)))
        print("stamp written:", STAMP)


if __name__ == "__main__":
    main()
