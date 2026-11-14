#!/usr/bin/env python3
"""build_ext.py - compile tools/ext/t2r-ext.c (the unity build) into a DLL.  Replaces the raw gcc line:

    cd tools/ext && gcc -std=gnu2x -O2 -s -shared -static -o OUT t2r-ext.c

usage:  python tools/ext/build_ext.py OUT.dll [--mode release|fast|dev|lto] [--jobs N] [--no-cache] [--src t2r-ext.c]
        env T2R_EXT_MODE sets the default mode (argument wins).  Exit code = gcc's.

modes
  release  today's exact flags (-O2).  The default.  Output is the same bytes the raw gcc line gives.
  fast     -O1: about 2x faster, A/B test builds.  Behaviour equal, code a bit slower/larger.  NOT for the shipped PT/live DLL.
  dev      -O0: about 4x faster, smoke tests only (slow code, game may stutter).
  lto      -O2 + -flto=auto with a parallel LTRANS driver (ltomake.c, built on demand next to this file).  Experimental: same
           source and flags, but not byte-identical to release; not the default.

content cache (all modes, on by default): key = hash(gcc version + flags + every file the preprocessor reads for t2r-ext.c).  If the
key matches an earlier build, the DLL is copied instead of recompiled (0.5 s).  So a build whose ext sources did not change - most
PT repacks after a data/asset-only edit - skips the compile completely.  Cache dir: T2R_EXT_CACHE, else ../t2r-wt/_extcache when
../t2r-wt exists, else tools/ext/.build_cache; the 3 newest entries are kept (a DLL is ~120 MB).
"""
import argparse, hashlib, os, shutil, subprocess, sys, time

HERE = os.path.dirname(os.path.abspath(__file__))
MAIN = os.environ.get("T2R_MAIN_ROOT", os.path.abspath(os.path.join(HERE, "..", "..")))
KEEP = 3

BASE = ["-std=gnu2x"]
MODES = {
    "release": ["-O2", "-s", "-shared", "-static"],
    "fast":    ["-O1", "-s", "-shared", "-static"],
    "dev":     ["-O0", "-s", "-shared", "-static"],
    "lto":     ["-O2", "-flto=auto", "-s", "-shared", "-static"],
}


def find_bindir():
    cands = [os.path.join(HERE, "..", "win", "ext", "msys64", "ucrt64", "bin"),
             os.path.join(MAIN, "tools", "win", "ext", "msys64", "ucrt64", "bin"),
             os.path.join(os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")), "tools/win/ext/msys64/ucrt64/bin")]
    for c in cands:
        if os.path.isfile(os.path.join(c, "gcc.exe")):
            return os.path.abspath(c)
    raise SystemExit("build_ext: gcc.exe (msys64 ucrt64) not found")


def deps(gcc, env, src):
    """every file the preprocessor reads for src (gcc -MM would skip <system> headers: -M keeps them, so a toolchain change is hashed too)."""
    r = subprocess.run([gcc] + BASE + ["-M", "-MG", src], cwd=HERE, env=env, capture_output=True, text=True)
    if r.returncode:
        raise SystemExit("build_ext: dependency scan failed:\n" + r.stderr[-2000:])
    toks = r.stdout.replace("\\\r\n", " ").replace("\\\n", " ").split()
    out = []
    i = 1                                           # [0] is 'src.o:'
    cur = ""
    for t in toks[1:]:
        cur = (cur + " " + t) if cur else t
        if cur.endswith("\\"):                      # escaped space inside a path
            cur = cur[:-1]
            continue
        out.append(cur)
        cur = ""
    return sorted(set(os.path.abspath(os.path.join(HERE, p)) for p in out if p))


def cache_dir():
    d = os.environ.get("T2R_EXT_CACHE")
    if not d:
        d = os.path.join(wt, "_extcache") if os.path.isdir(wt := os.environ.get("T2R_WT", os.path.join(HERE, "..", "..", "..", "t2r-wt"))) else os.path.join(HERE, ".build_cache")
    os.makedirs(d, exist_ok=True)
    return d


def build_ltomake(gcc, env):
    exe = os.path.join(HERE, "ltomake.exe")
    srcf = os.path.join(HERE, "ltomake.c")
    if not os.path.isfile(exe) or os.path.getmtime(exe) < os.path.getmtime(srcf):
        subprocess.check_call([gcc, "-O1", "-s", "-o", exe, srcf], env=env)
    return exe


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("out")
    ap.add_argument("--mode", default=os.environ.get("T2R_EXT_MODE", "release"), choices=sorted(MODES))
    ap.add_argument("--jobs", type=int, default=int(os.environ.get("T2R_LTO_JOBS", "8")))
    ap.add_argument("--no-cache", action="store_true")
    ap.add_argument("--src", default="t2r-ext.c")
    a = ap.parse_args()
    bindir = find_bindir()
    gcc = os.path.join(bindir, "gcc.exe")
    env = dict(os.environ, PATH=bindir + os.pathsep + os.environ["PATH"])
    flags = BASE + MODES[a.mode]
    if a.mode != "release":
        print(f"build_ext: mode {a.mode} (NOT the release flags)")
    out = os.path.abspath(a.out)
    os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
    t0 = time.perf_counter()

    key = None
    if not a.no_cache:
        h = hashlib.sha256()
        h.update(" ".join(flags).encode())
        h.update(subprocess.run([gcc, "-dumpfullversion"], capture_output=True, text=True).stdout.encode())
        for p in deps(gcc, env, a.src):
            h.update(p.replace("\\", "/").rsplit("/tools/", 1)[-1].encode() if "/tools/" in p.replace("\\", "/") else os.path.basename(p).encode())
            with open(p, "rb") as f:
                h.update(hashlib.sha256(f.read()).digest())
        key = h.hexdigest()[:24]
        cached = os.path.join(cache_dir(), f"ext-{a.mode}-{key}.dll")
        if os.path.isfile(cached):
            shutil.copyfile(cached, out)
            os.utime(cached, None)
            print(f"build_ext: cache hit {key} ({time.perf_counter() - t0:.1f} s)")
            return 0

    tmp = out + ".tmp"
    if a.mode == "lto":
        env["MAKE"] = build_ltomake(gcc, env)
        env["T2R_LTO_JOBS"] = str(a.jobs)
    t1 = time.perf_counter()
    rc = subprocess.call([gcc] + flags + ["-o", tmp, a.src], cwd=HERE, env=env)
    if rc:
        if os.path.exists(tmp):
            os.remove(tmp)
        return rc
    os.replace(tmp, out)
    print(f"build_ext: {a.mode} compile {time.perf_counter() - t1:.1f} s")
    if key:
        d = cache_dir()
        shutil.copyfile(out, os.path.join(d, f"ext-{a.mode}-{key}.dll"))
        old = sorted((os.path.join(d, f) for f in os.listdir(d) if f.startswith("ext-") and f.endswith(".dll")), key=os.path.getmtime, reverse=True)
        for f in old[KEEP:]:
            try:
                os.remove(f)
            except OSError:
                pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
