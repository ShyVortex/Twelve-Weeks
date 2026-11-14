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
MAIN = os.environ.get("T2R_MAIN_ROOT", os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")))
CONV = os.environ.get("T2R_P1_CONV") or os.path.join(MAIN, "re", "part1", "x", "conv-abi-mix5")
LEVEL = "hun-checkpoint-bookstore"          # its base pak gets the fire point lights grafted
BEFORE = os.environ.get("T2R_STAGE_BEFORE_REV", "f29aa9b5")
FEATURES = os.path.join(ROOT, "tools", "features")


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
@unittest.skipUnless(subprocess.run(["git", "-C", ROOT, "cat-file", "-e", BEFORE + "^{commit}"], capture_output=True).returncode == 0,
                     "the pre-lift commit (T2R_STAGE_BEFORE_REV) is not in this repository")
class T(unittest.TestCase):
    def test_same_staged_bytes_before_and_after_the_lift(self):
        os.environ.update(T2R_P1_CONV=CONV, T2R_MAIN_ROOT=MAIN, T2R_P1_RS="0")
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
                m = [x for x in mod.specs() if x["key"] == "p1-bookstore"][0]
                m = dict(m, part1={k: v for k, v in m["part1"].items() if k != "audio"})
                m["part1"]["levels"] = [LEVEL]
                d = os.path.join(tmp, name)
                os.makedirs(os.path.join(d, "pak68"))
                mod.stage_part1(d, [m])
                outs[name] = tree(d)
            self.assertIn("pak68/%s.pak" % LEVEL, outs["after"])
            self.assertEqual(outs["before"], outs["after"])
            self.assertNotEqual(outs["after"]["pak68/%s.pak" % LEVEL], hashlib.sha256(open(os.path.join(CONV, LEVEL + ".pak"), "rb").read()).hexdigest(),
                                "the fire lights were grafted into the staged base pak")
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
