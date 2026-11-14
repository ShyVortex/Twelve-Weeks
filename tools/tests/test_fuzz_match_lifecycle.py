"""Quick mode of the match-lifecycle stateful fuzz (tools/tests/fuzz_match_lifecycle.py): a few short seeds against a REAL daemon process (own ports /
temp DB under the temp dir, 12x accelerated clock). The long runs (300 seeds x 200 steps) are `python tools/tests/fuzz_match_lifecycle.py --seeds 0-299 -j 3`.
Run: python tools/tests/test_fuzz_match_lifecycle.py"""
import os, sys, tempfile
import sys as _t2s, os as _t2o; _t2s.path.append(_t2o.path.normpath(_t2o.path.join(_t2o.path.dirname(_t2o.path.abspath(__file__)), ".."))); import t2rtmp  # noqa: E402,F401

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import fuzz_match_lifecycle as fz  # noqa: E402

FAILS = []
def check(cond, what):
    print(("ok   " if cond else "FAIL ") + what)
    if not cond: FAILS.append(what)

check(fz.parse_seeds("1,3-5") == [1, 3, 4, 5], "parse_seeds")
check(fz.read_frames(b"\x02\x00\x04\x01\x00\x00\x03\x00\x09")[0] == [(4, b"\x01")], "read_frames")
work = tempfile.mkdtemp()
for seed in (101, 102, 103):
    r = fz.run_seed(seed, 40, work, accel=12.0)
    check(r["ok"], "seed %d (%d clients, match size %d, %d actions, %d matches): %s" % (seed, r["nclients"], r["match_size"], len(r["actions"]), r["matches"], r["violation"]))
    if not r["ok"]:
        for n in r["notes"][-15:]: print("     ", n)
print("\n%d failure(s)" % len(FAILS) if FAILS else "\nall ok")
sys.exit(1 if FAILS else 0)
