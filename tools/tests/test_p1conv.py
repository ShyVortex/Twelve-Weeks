"""p1conv offline tests (no conversion): protocol, errors, the TLOU2 donor extraction, verify.  python tools/tests/test_p1conv.py
The TLOU2 extraction test needs a TLOU2 install (T2R_TLOU2_DIR, default C:\Games\The Last of Us Part II Remastered) and is skipped without one; it only READS it."""
import json
import os
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
PART1 = os.path.join(os.path.dirname(HERE), "part1")
TLOU2 = os.environ.get("T2R_TLOU2_DIR", r"C:\Games\The Last of Us Part II Remastered")
AUDIO = os.environ.get("T2R_P1_AUDIO_DIR") or r".\re\part1\x\audio-bookstore"
EXE = os.environ.get("P1CONV_EXE")         # a frozen build to test instead of the python script


def run(*args):
    cmd = [EXE] if EXE else [sys.executable, "-I", os.path.join(PART1, "p1conv.py")]
    r = subprocess.run(cmd + list(args), capture_output=True, text=True, timeout=600)
    ev = [json.loads(x) for x in r.stdout.splitlines() if x.strip()]       # stdout must be JSON lines only
    return r.returncode, ev


class T(unittest.TestCase):
    def test_version_and_usage(self):
        rc, ev = run("version")
        self.assertEqual((rc, ev[0]["event"]), (0, "version"))
        rc, ev = run()
        self.assertEqual(rc, 2)
        self.assertEqual(ev, [])

    def test_errors_are_events(self):
        with tempfile.TemporaryDirectory() as d:
            rc, ev = run("convert", "--part1", os.path.join(d, "nope"), "--out", os.path.join(d, "o"))
            self.assertEqual(rc, 1)
            self.assertEqual(ev[-1]["event"], "error")
            rc, ev = run("convert", "--bogus")
            self.assertEqual((rc, ev[-1]["event"]), (1, "error"))
            rc, ev = run("inputs", "--tlou2", d, "--out", d)
            self.assertEqual((rc, ev[-1]["event"]), (1, "error"))
            self.assertIn("not a TLOU2 install", ev[-1]["message"])

    @unittest.skipUnless(os.path.isfile(os.path.join(TLOU2, "build", "pc", "main", "bin.psarc")), "no TLOU2 install")
    def test_tlou2_donor_extraction(self):
        with tempfile.TemporaryDirectory() as d:
            rc, ev = run("inputs", "--tlou2", TLOU2, "--out", d)
            self.assertEqual(rc, 0, ev)
            m = os.path.join(d, "re", "gamebin", "dc1", "modules.bin")
            t = os.path.join(d, "re", "gamebin", "dc1", "render-settings", "t1x.bin")
            self.assertGreater(os.path.getsize(m), 3_000_000)
            self.assertGreater(os.path.getsize(t), 1000)
            self.assertEqual(open(m, "rb").read(4), open(m, "rb").read(4))
            self.assertFalse([x for x in os.listdir(os.path.dirname(m)) if x.endswith(".part")])

    @unittest.skipUnless(os.path.isfile(os.path.join(AUDIO, "pak68", "hun-const-audio-ingame.pak")), "no audio oracle")
    def test_spawnerpak_matches_scene_editor_output(self):
        with tempfile.TemporaryDirectory() as d:
            out = os.path.join(d, "o.pak")
            rc, ev = run("spawnerpak", "--in", os.path.join(AUDIO, "conv", "hun-const-audio-ingame.pak"), "--out", out, "--drop", "ss-snd-hun-")
            self.assertEqual((rc, ev[-1]["kept"], ev[-1]["dropped"]), (0, 1132, 3))
            self.assertTrue(open(out, "rb").read() == open(os.path.join(AUDIO, "pak68", "hun-const-audio-ingame.pak"), "rb").read())

    def test_verify(self):
        with tempfile.TemporaryDirectory() as d:
            a, b = os.path.join(d, "a"), os.path.join(d, "b")
            for root, extra in ((a, b"x"), (b, b"x")):
                os.makedirs(os.path.join(root, "pak68"))
                open(os.path.join(root, "pak68", "l.pak"), "wb").write(b"level" + extra)
            os.makedirs(os.path.join(a, ".work"))
            open(os.path.join(a, ".work", "junk"), "wb").write(b"j")
            rc, ev = run("verify", "--out", a, "--against", b)
            self.assertEqual((rc, ev[-1]["same"], ev[-1]["different"]), (0, 1, []))
            open(os.path.join(b, "pak68", "l.pak"), "wb").write(b"other")
            rc, ev = run("verify", "--out", a, "--against", b)
            self.assertEqual((rc, ev[-1]["different"]), (1, ["pak68/l.pak"]))
            man = os.path.join(d, "m.json")
            json.dump({"files": [{"path": "pak68/l.pak", "sha256": __import__("hashlib").sha256(b"levelx").hexdigest()}]}, open(man, "w"))
            rc, ev = run("verify", "--out", a, "--against", man)
            self.assertEqual(rc, 0)


if __name__ == "__main__":
    unittest.main()
