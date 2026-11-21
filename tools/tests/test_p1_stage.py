"""One code path: Part I staging (p1_stage, used by sp_maps_build AND p1conv) gives byte-identical staged files to the pre-lift sp_maps_build.
Needs a converted Part I folder (T2R_P1_CONV, default re/part1/x/conv-abi-mix5 of the main checkout); skipped otherwise.
  python tools/tests/test_p1_stage.py          (T2R_STAGE_BEFORE_REV = the commit holding the pre-lift sp_maps_build, default f29aa9b5)"""
import hashlib
import importlib.util
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
MAIN = os.environ.get("T2R_MAIN_ROOT", r".")
CONV = os.environ.get("T2R_P1_CONV") or os.path.join(MAIN, "re", "part1", "x", "conv-abi-mix5")
LEVEL = "hun-checkpoint-bookstore"          # its base pak gets the fire point lights grafted
BEFORE = os.environ.get("T2R_STAGE_BEFORE_REV", "f29aa9b5")
FEATURES = os.path.join(ROOT, "tools", "features")
os.environ.setdefault("T2R_P1_FIRE_PARTICLES", "0")       # the lift comparison is of the point-record path (the pre-lift build had no p1_particles)


def tree(root):
    out = {}
    for r, _, fs in os.walk(root):
        for f in fs:
            p = os.path.join(r, f)
            out[os.path.relpath(p, root).replace(os.sep, "/")] = hashlib.sha256(open(p, "rb").read()).hexdigest()
    return out


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


@unittest.skipUnless(os.path.isfile(os.path.join(CONV, LEVEL + ".pak")), "no converted Part I folder")
class T(unittest.TestCase):
    def test_same_staged_bytes_before_and_after_the_lift(self):
        os.environ.update(T2R_P1_CONV=CONV, T2R_MAIN_ROOT=MAIN, T2R_P1_RS="0", T2R_P1_LIGHT_NAMES="0")      # (ANIMATED_LIGHTS naming is newer than the lift)
        # the map's "build" block names its own conv dir: point it at CONV; the pre-lift code runs the newer loader check on the
        # unregrouped pak, so the check is off here and the before tree's base pak gets the regroup (p1_convert.regroup_fix) afterwards
        os.environ.update(T2R_P1_CONV_P1_BOOKSTORE=CONV, T2R_P1_PAKCHECK="0")
        sys.path[:0] = [FEATURES] + [os.path.join(ROOT, "tools", d) for d in ("part1", "models", "maps")]
        old_src = subprocess.run(["git", "-C", ROOT, "show", f"{BEFORE}:tools/features/sp_maps_build.py"], capture_output=True, check=True).stdout
        copy = os.path.join(FEATURES, "_sp_maps_build_before_tmp.py")      # next to the real one: its helper imports resolve through HERE
        open(copy, "wb").write(old_src)
        tmp = tempfile.mkdtemp(prefix="t2r-stage-")
        try:
            try:
                old = load(copy, "_sp_before")
            finally:
                os.unlink(copy)
            new = load(os.path.join(FEATURES, "sp_maps_build.py"), "_sp_after")
            outs = {}
            for name, mod in (("before", old), ("after", new)):
                mod.P1_CONV = CONV
                mod.stage_part1_fires = lambda *a, **k: None      # our own spawner pak: not part of the Part I file set
                mod.stage_part1_spawners = lambda *a, **k: None   # (newer than the lift: the grafted Part I spawners, also our own pak)
                m = [x for x in mod.specs() if x["key"] == "p1-bookstore"][0]
                m = dict(m, part1={k: v for k, v in m["part1"].items() if k != "audio"})
                m["part1"]["levels"] = [LEVEL]
                d = os.path.join(tmp, name)
                os.makedirs(os.path.join(d, "pak68"))
                import p1_convert
                lc = p1_convert.loader_check
                if name == "before":        # (the pre-lift code knows no regroup: its one header-piece finding is the one regroup_fix removes)
                    p1_convert.loader_check = lambda *a, **k: [x for x in lc(*a, **k) if "run past header piece" not in x]
                try:
                    mod.stage_part1(d, [m])
                finally:
                    p1_convert.loader_check = lc
                if name == "before":
                    pk = os.path.join(d, "pak68", LEVEL + ".pak")
                    raw = open(pk, "rb").read()
                    open(pk, "wb").write(p1_convert.regroup_fix(raw)[0])
                outs[name] = tree(d)
            self.assertIn("pak68/%s.pak" % LEVEL, outs["after"])
            # (the -ingame pak is staged since the lift too: p1_ingame default on.) The base pak is regrouped BEFORE the fire-light graft
            # now, and the graft lays its pages out by group, so its bytes differ from graft-then-regroup: both must pass the loader mirrors;
            # every other file the pre-lift build staged is identical
            base = "pak68/%s.pak" % LEVEL
            self.assertEqual({k: v for k, v in outs["before"].items() if k != base}, {k: v for k, v in outs["after"].items() if k in outs["before"] and k != base})
            for name in outs:
                pk = os.path.join(tmp, name, *base.split("/"))
                self.assertEqual(p1_convert.loader_check(pk) + p1_convert.lights_check(pk) + p1_convert.trailer_check(pk) + p1_convert.geometry_extent_check(pk), [], name)
            self.assertNotEqual(outs["after"]["pak68/%s.pak" % LEVEL], hashlib.sha256(open(os.path.join(CONV, LEVEL + ".pak"), "rb").read()).hexdigest(),
                                "the fire lights were grafted into the staged base pak")
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
