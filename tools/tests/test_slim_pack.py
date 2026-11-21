"""T2SLIM02 round trip on a synthetic stage (no game files needed): pack a few files into the original mod DLL, write the slim DLL + .dat
with the xz pack stream, run the helper exe (t2r-slim.exe built into a temp dir) and compare its output with the full DLL byte for byte.
Also: a damaged pack stream / wrong DLL must be refused (nothing written).

  tools/win/.venv/Scripts/python tools/tests/test_slim_pack.py

Needs: the original winmm.dll (extracted/InstallerFiles/winmm.dll, T2R_BASE_DLL), MSYS2 gcc (tools/win/ext/msys64/ucrt64/bin, T2R_SLIM_GCCDIR).
Skips (exit 0, SKIP) when either is missing."""
import hashlib
import os
import random
import shutil
import subprocess
import sys
import tempfile
import sys as _t2s, os as _t2o; _t2s.path.append(_t2o.path.normpath(_t2o.path.join(_t2o.path.dirname(_t2o.path.abspath(__file__)), ".."))); import t2rtmp  # noqa: E402,F401  (temp hygiene: tools/t2rtmp.py)

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.dirname(HERE)
ROOT = os.path.dirname(TOOLS)
sys.path.insert(0, TOOLS)
sys.path.insert(0, os.path.join(TOOLS, "features"))


def find(*c):
    return next((p for p in c if p and os.path.exists(p)), None)


def main():
    base = find(os.environ.get("T2R_BASE_DLL"), os.path.join(ROOT, "extracted", "InstallerFiles", "winmm.dll"),
                os.path.join(ROOT, "..", "..", "..", "extracted", "InstallerFiles", "winmm.dll"))
    gccdir = find(os.environ.get("T2R_SLIM_GCCDIR"), os.path.join(TOOLS, "win", "ext", "msys64", "ucrt64", "bin"),
                  os.path.join(ROOT, "..", "..", "..", "tools", "win", "ext", "msys64", "ucrt64", "bin"))
    if not base or not gccdir:
        print("SKIP test_slim_pack: base DLL or gcc not found")
        return 0
    os.environ["T2R_SLIM_GCCDIR"] = gccdir
    import slim
    import t2r_pack
    bad = []

    def check(name, ok):
        print(("ok   " if ok else "FAIL ") + name)
        if not ok:
            bad.append(name)

    with tempfile.TemporaryDirectory() as td:
        os.environ["T2R_SLIM_CACHE"] = os.path.join(td, "cache")
        os.environ["T2R_SLIM_TMP"] = os.path.join(td, "tmp")
        stage = os.path.join(td, "stage")
        rnd = random.Random(7)
        files = {
            "a/random.bin": bytes(rnd.getrandbits(8) for _ in range(700_000)),            # incompressible (literal-only lz4 blocks)
            "a/text.txt": (b"the quick brown fox jumps over the lazy dog\n" * 40000)[:1_300_000],
            "b/exact.pak": bytes((i * 7) & 0xFF for i in range(2 * slim.DSAR_CHUNK)),    # exact multiple of the chunk size
            "b/zeros.bin": b"\0" * 900_000,
            "b/tiny.txt": b"x",
            "c.common": b"".join(hashlib.sha1(str(i).encode()).digest() for i in range(30000)),
        }
        for p, d in files.items():
            fp = os.path.join(stage, p)
            os.makedirs(os.path.dirname(fp), exist_ok=True)
            with open(fp, "wb") as f:
                f.write(d)
        paths = sorted(files)
        with open(os.path.join(stage, "_t2r_manifest.txt"), "w", newline="\n") as f:
            f.write("flags=0 trail=0\n" + "\n".join(paths) + "\n--order--\n" + "\n".join(paths) + "\n")
        full = os.path.join(td, "full.dll")
        with open(full, "wb") as f:
            f.write(t2r_pack.pack_bytes(base, stage))
        pl = dict(entries=[], drop=[], gamedir=td, stage=stage)
        slim_dll, dat = full + ".slim", full + ".slim.dat"
        extra_src = os.path.join(td, "extra-src.bin")
        extra = bytes(rnd.getrandbits(8) for _ in range(300_000)) + b"A" * 700_000
        open(extra_src, "wb").write(extra)
        r = slim.emit(full, pl, slim_dll, dat, extras=[("tlou-ii-mp/sidbase.bin", extra_src)])
        check("emit packed every staged file + the extra", r["packed"] == len(files) and r["patched"] == 0 and r["extras"] == 1)
        exe = slim.build_helper(os.path.join(td, "t2r-slim.exe"))
        try:
            slim.check(full, slim_dll, dat, td, exe)
            check("helper output is byte-identical to the full DLL", True)
            # a normal run (as T2R-Play does it) writes the extra file; a second run leaves it alone
            p1 = subprocess.run([exe, slim_dll, dat, td, os.path.join(td, "again.dll")], capture_output=True, text=True)
            check("the extra file was written into the game folder",
                  p1.returncode == 0 and open(os.path.join(td, "tlou-ii-mp", "sidbase.bin"), "rb").read() == extra)
            p2 = subprocess.run([exe, slim_dll, dat, td, os.path.join(td, "again.dll")], capture_output=True, text=True)
            check("second run: extra file left alone", p2.returncode == 0 and "up to date" in p2.stdout)
        except SystemExit as e:
            check("helper output is byte-identical to the full DLL (%s)" % e, False)

        # the build's own check run (T2R_SLIM_SKIP_EXTRAS) must not write extra files into the game folder
        ng = os.path.join(td, "game2")
        os.makedirs(ng)
        p3 = subprocess.run([exe, slim_dll, dat, ng, os.path.join(td, "skip.dll")], capture_output=True, text=True, env=dict(os.environ, T2R_SLIM_SKIP_EXTRAS="1"))
        check("T2R_SLIM_SKIP_EXTRAS: no extra file written", p3.returncode == 0 and not os.path.exists(os.path.join(ng, "tlou-ii-mp")))

        # damaged pack stream: refused, no output file left behind
        bad_dat = os.path.join(td, "bad.dat")
        b = bytearray(open(dat, "rb").read())
        b[-200] ^= 0x55
        open(bad_dat, "wb").write(b)
        out = os.path.join(td, "out-bad.dll")
        p = subprocess.run([exe, slim_dll, bad_dat, td, out], capture_output=True, text=True)
        check("a damaged .dat is refused (exit %d)" % p.returncode, p.returncode != 0 and not os.path.exists(out) and not os.path.exists(out + ".tmp"))
        # wrong-size DLL
        short = os.path.join(td, "short.dll")
        open(short, "wb").write(open(slim_dll, "rb").read(1 << 20))
        p = subprocess.run([exe, short, dat, td, out], capture_output=True, text=True)
        check("a DLL of the wrong size is refused", p.returncode != 0 and not os.path.exists(out))
        shutil.rmtree(stage, ignore_errors=True)
    print("\n%d problem(s)" % len(bad))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
