"""Static-analysis gate for the ext: compile the unity build (t2r-ext.c) with a strict warning set and fail on warnings that
are not in the checked-in baseline (tools/ext/tests/warn_baseline.txt).

  python tools/ext/tests/warn_check.py [--update] [--release] [--keep]

Only bug-class warnings are gated (format, shadow, null-deref, bounds, stringop, uninitialised, logical-op, duplicated-cond,
fallthrough, string-compare, sizeof, aliasing, type-limits); style noise (unused-*, missing-field-initializers, sign-compare,
misleading-indentation, cast-function-type) is not. A warning's identity is (file, flag, message) with line/column dropped, so
code moving around does not cause churn; the baseline stores how many of each are accepted. --update rewrites the baseline
after you triaged new warnings as benign. No object is linked; output goes to the temp folder.
"""
import argparse
import collections
import os
import re
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
EXT = os.path.dirname(HERE)
ROOT = os.path.dirname(os.path.dirname(EXT))
BASE = os.path.join(HERE, "warn_baseline.txt")

FLAGS = ["-Wall", "-Wextra", "-Wformat=2", "-Wshadow=local", "-Wnull-dereference", "-Warray-bounds=2",
         "-Wstringop-overflow=4", "-Wmaybe-uninitialized", "-Wduplicated-cond", "-Wlogical-op"]
GATED = re.compile(r"\[-W(format|shadow|null-dereference|array-bounds|stringop|maybe-uninitialized|uninitialized|logical-op|"
                   r"duplicated-cond|implicit-fallthrough|string-compare|sizeof|strict-aliasing|type-limits|address|"
                   r"restrict|overflow|return-type|int-conversion|incompatible|pointer)")


def find_gcc():
    for cand in (os.path.join(ROOT, "tools", "win", "ext", "msys64", "ucrt64", "bin"),
                 os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(ROOT))), "tools", "win", "ext", "msys64", "ucrt64", "bin")):
        if os.path.isfile(os.path.join(cand, "gcc.exe")):
            return cand
    return None


def build(release):
    bindir = find_gcc()
    env = dict(os.environ)
    if bindir:
        env["PATH"] = bindir + os.pathsep + env["PATH"]
    obj = os.path.join(tempfile.gettempdir(), "t2r-warn-check.o")
    gcc = os.path.join(bindir, "gcc.exe") if bindir else "gcc"   # (CreateProcess searches the parent's PATH, not env's)
    cmd = [gcc, "-std=gnu2x", "-O2", "-c", "-o", obj] + FLAGS + (["-DT2R_RELEASE"] if release else []) + ["t2r-ext.c"]
    p = subprocess.run(cmd, cwd=EXT, env=env, capture_output=True, text=True, errors="replace")
    try:
        os.remove(obj)
    except OSError:
        pass
    return p.returncode, p.stderr


def parse(stderr):
    c = collections.Counter()
    for l in stderr.splitlines():
        m = re.match(r"^([^:\s][^:]*):(\d+):(\d+): warning: (.*)$", l)
        if not m or not GATED.search(m.group(4)):
            continue
        msg = re.sub(r"\s+", " ", m.group(4))
        c["%s|%s" % (os.path.basename(m.group(1)), msg)] += 1
    return c


def load_base():
    c = collections.Counter()
    if os.path.isfile(BASE):
        for l in open(BASE, encoding="utf-8"):
            l = l.rstrip("\r\n")
            if l and not l.startswith("#"):
                n, _, k = l.partition("\t")
                c[k] = int(n)
    return c


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--update", action="store_true")
    ap.add_argument("--release", action="store_true", help="check the -DT2R_RELEASE variant instead of the dev one")
    a = ap.parse_args()
    rc, err = build(a.release)
    if rc != 0:
        print("BUILD FAILED rc=%d\n%s" % (rc, err[-3000:]))
        return 1
    cur = parse(err)
    if a.update:
        with open(BASE, "w", encoding="utf-8", newline="\n") as f:
            f.write("# accepted (triaged benign) warnings: count<TAB>file|message; see re/ext-static-analysis-1019.md\n")
            for k in sorted(cur):
                f.write("%d\t%s\n" % (cur[k], k))
        print("baseline updated: %d warnings, %d distinct" % (sum(cur.values()), len(cur)))
        return 0
    base = load_base()
    new = [(k, n - base.get(k, 0)) for k, n in cur.items() if n > base.get(k, 0)]
    if new:
        print("NEW warnings (not in %s):" % os.path.relpath(BASE, ROOT))
        for k, n in sorted(new):
            print("  +%d  %s" % (n, k))
        print("fix them, or triage as benign and run: python tools/ext/tests/warn_check.py --update")
        return 1
    print("ok: %d gated warnings, none new (baseline %d)" % (sum(cur.values()), sum(base.values())))
    return 0


if __name__ == "__main__":
    sys.exit(main())
