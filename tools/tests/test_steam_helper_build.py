"""The committed Steam helper exe must be the build of the committed source (build_release.py only copies the exe, so an edited
t2r-steam.c that was not rebuilt silently never ships).

 1. stamp: release/client/steam/t2r-steam.exe.stamp holds the sha256 of the t2r-steam.c the exe was built from; fails when the .c
    was edited without `python tools/steam/build_helper.py --install` (no compiler needed, instant).
 2. rebuild: when the repo gcc is found, a fresh build of the committed source equals the committed exe (PE timestamp / checksum
    ignored), and two builds are byte-identical (deterministic flags). Skipped without gcc (stamp check still runs).
Run: python tools/tests/test_steam_helper_build.py"""
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "steam"))
import build_helper as bh  # noqa: E402

fails = []
raw = open(bh.EXE, "rb").read()
n = bh.normalise(raw)
if len(n) != len(raw) or bh.normalise(n) != n:
    fails.append("normalise is not idempotent / size-preserving")
e = bh.stamp_check()
if e:
    fails.append(e)
if bh.find_gcc():
    tmp = os.environ.get("T2R_TMP") or tempfile.gettempdir()
    a, b = os.path.join(tmp, "t2r-steam-t1.exe"), os.path.join(tmp, "t2r-steam-t2.exe")
    bh.build(a)
    bh.build(b)
    if open(a, "rb").read() != open(b, "rb").read():
        fails.append("two builds of the same source differ byte-for-byte (non-deterministic flags)")
    if not bh.same(a, bh.EXE):
        fails.append("committed t2r-steam.exe differs from a fresh build of the committed t2r-steam.c (rebuild with --install)")
else:
    print("note: no gcc found, rebuild comparison skipped (stamp check only)")
if fails:
    print("FAIL\n  " + "\n  ".join(fails))
    sys.exit(1)
print("steam helper build: OK")
