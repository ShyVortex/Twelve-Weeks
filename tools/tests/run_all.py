"""Run the whole offline test suite with a per-test time budget and a pass/fail/time summary.

  python tools/tests/run_all.py [--tmp DIR] [--budget SEC] [-j N] [--only SUBSTR] [--no-node] [-v]

Collects tools/tests/test_*.py, any other tools/**/test_*.py, and (if node is on PATH) release/launcher/test/*-test.js
plus selftest.js. Every test runs with TMP/TEMP/TMPDIR pointed at --tmp (default env T2R_TEST_TMP, else
E:\t2tmp_agents\tests when it can be created, else the system temp) so a full system drive cannot break them.
Exit code 0 only when every test passed.
"""
import argparse
import concurrent.futures as cf
import os
import shutil
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.dirname(HERE)
ROOT = os.path.dirname(TOOLS)


def default_tmp():
    t = os.environ.get("T2R_TEST_TMP")
    if t:
        return t
    for cand in (r"E:\t2tmp_agents\tests",):
        try:
            os.makedirs(cand, exist_ok=True)
            return cand
        except OSError:
            pass
    return None


def collect(no_node):
    out = []
    for dp, dn, fn in os.walk(TOOLS):
        dn[:] = [d for d in dn if d not in ("node_modules", "win", "__pycache__", ".git")]
        for f in sorted(fn):
            if f.startswith("test_") and f.endswith(".py"):
                out.append(("py", os.path.join(dp, f)))
    out.sort(key=lambda x: x[1])
    node = shutil.which("node")
    if node and not no_node:
        td = os.path.join(ROOT, "release", "launcher", "test")
        if os.path.isdir(td):
            for f in sorted(os.listdir(td)):
                if f.endswith("-test.js") or f == "selftest.js":
                    out.append(("node", os.path.join(td, f)))
    return out


def run_one(kind, path, tmp, budget):
    env = dict(os.environ)
    if tmp:
        for k in ("TMP", "TEMP", "TMPDIR"):
            env[k] = tmp
    env["PYTHONIOENCODING"] = "utf-8"
    if kind == "py":
        cmd, cwd = [sys.executable, path], ROOT
    else:
        cmd, cwd = [shutil.which("node"), path], os.path.dirname(os.path.dirname(path))
    t0 = time.time()
    try:
        p = subprocess.run(cmd, cwd=cwd, env=env, capture_output=True, timeout=budget)
        st = "PASS" if p.returncode == 0 else "FAIL"
        txt = (p.stdout + b"\n" + p.stderr).decode("utf-8", "replace")
    except subprocess.TimeoutExpired as e:
        st, txt = "TIMEOUT", ((e.stdout or b"") + b"\n" + (e.stderr or b"")).decode("utf-8", "replace")
    return st, time.time() - t0, txt


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tmp", default=default_tmp())
    ap.add_argument("--budget", type=float, default=600.0, help="seconds per test")
    ap.add_argument("-j", type=int, default=3)
    ap.add_argument("--only", default="")
    ap.add_argument("--no-node", action="store_true")
    ap.add_argument("-v", action="store_true", help="show output of passing tests too")
    a = ap.parse_args()
    if a.tmp:
        os.makedirs(a.tmp, exist_ok=True)
    tests = [t for t in collect(a.no_node) if a.only in t[1]]
    print("tmp=%s budget=%ss tests=%d" % (a.tmp, a.budget, len(tests)))
    res = []
    with cf.ThreadPoolExecutor(max_workers=max(1, a.j)) as ex:
        futs = {ex.submit(run_one, k, p, a.tmp, a.budget): (k, p) for k, p in tests}
        for f in cf.as_completed(futs):
            k, p = futs[f]
            st, dt, txt = f.result()
            rel = os.path.relpath(p, ROOT)
            print("%-7s %6.1fs  %s" % (st, dt, rel), flush=True)
            if st != "PASS" or a.v:
                print("\n".join("    | " + l for l in txt.strip().splitlines()[-40:]), flush=True)
            res.append((st, dt, rel))
    res.sort(key=lambda r: r[2])
    bad = [r for r in res if r[0] != "PASS"]
    print("\n==== summary: %d passed, %d failed of %d, %.1fs total test time ====" %
          (len(res) - len(bad), len(bad), len(res), sum(r[1] for r in res)))
    for st, dt, rel in bad:
        print("  %s  %s" % (st, rel))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
