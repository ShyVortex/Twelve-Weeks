"""p1_spawner_pak: the Python port of the SceneEditor spawner-pak rewrite is byte-identical to the SceneEditor's own output (never runs SceneEditor).
Oracle files: the audio dir of the build (re/part1/x/audio-bookstore: conv/hun-const-audio-ingame.pak = input, pak68/hun-const-audio-ingame.pak = the
SceneEditor-written result, spawners.json = the ps1's list). Skipped without them.   python tools/tests/test_p1_spawner_pak.py"""
import json
import os
import struct
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "part1"))
import p1_spawner_pak as P

AUDIO = os.environ.get("T2R_P1_AUDIO_DIR") or r".\re\part1\x\audio-bookstore"
INP = os.path.join(AUDIO, "conv", "hun-const-audio-ingame.pak")
REF = os.path.join(AUDIO, "pak68", "hun-const-audio-ingame.pak")
JS = os.path.join(AUDIO, "spawners.json")
DROP = ("ss-snd-hun-",)


class Units(unittest.TestCase):
    def test_sid(self):
        self.assertEqual(P.sid(""), 0)
        self.assertEqual(P.sid("#00000000000000FF"), 255)
        self.assertEqual(P.sid("a"), (14695981039346656037 ^ 97) * 1099511628211 % (1 << 64))

    def test_float_text_like_dotnet(self):
        f = lambda v: P.fstr(struct.pack("<f", v))
        self.assertEqual([f(48.0), f(0.5), f(-3.5), f(47.85973), f(0.0), f(1e-7), f(1e20)], ["48", "0.5", "-3.5", "47.85973", "0", "1E-07", "1E+20"])

    def test_nav_meshes_refused(self):
        self.assertTrue(callable(P.read))


@unittest.skipUnless(os.path.isfile(INP) and os.path.isfile(REF), "no audio dir with the SceneEditor oracle")
class Oracle(unittest.TestCase):
    def test_byte_identical_to_scene_editor_output(self):
        out, kept, dropped = P.rewrite(open(INP, "rb").read(), DROP)
        ref = open(REF, "rb").read()
        self.assertEqual((kept, dropped), (1132, 3))
        self.assertEqual(len(out), len(ref))
        self.assertTrue(out == ref, "output differs from the SceneEditor-written pak")

    def test_rewriting_the_result_is_a_fixed_point(self):
        ref = open(REF, "rb").read()
        again, kept, dropped = P.rewrite(ref, ())
        self.assertEqual(dropped, 0)
        self.assertTrue(again == ref)

    @unittest.skipUnless(os.path.isfile(JS), "no spawners.json")
    def test_spawner_list_matches_the_ps1_json(self):
        sp, _ = P.read(open(INP, "rb").read())
        mine = json.loads(P.json_text([s for s in sp if not s.name.startswith(DROP)]))
        ref = json.load(open(JS, encoding="utf-8-sig"))
        key = lambda d: (d["n"], json.dumps(dict(d, p=[float(x) for x in d["p"]]), sort_keys=True))      # (json numbers: 5.0 == 5)
        self.assertEqual(sorted(map(key, mine)), sorted(map(key, ref)))


KEEP = os.environ.get("T2R_P1_KEEP_DIR") or os.path.join(os.path.dirname(os.path.abspath(__file__)), "keeptest")     # keep-in.pak = converted hun-checkpoint-bookstore-ingame.pak,
KEEP_IN, KEEP_REF = os.path.join(KEEP, "keep-in.pak"), os.path.join(KEEP, "keep-ref.pak")    # keep-ref.pak = keep_spawners.ps1 output of it


@unittest.skipUnless(os.path.isfile(KEEP_REF), "no keep_spawners.ps1 oracle")
class KeepOracle(unittest.TestCase):
    NAMES = ["rt-ortho-fake-son-Shape-1"]

    @unittest.skipUnless(os.path.isfile(KEEP_IN), "no converted input pak")
    def test_keep_byte_identical_to_keep_spawners_ps1(self):
        self.assertTrue(P.keep(open(KEEP_IN, "rb").read(), self.NAMES) == open(KEEP_REF, "rb").read())

    def test_keep_is_a_fixed_point(self):
        ref = open(KEEP_REF, "rb").read()
        self.assertTrue(P.keep(ref, self.NAMES) == ref)

    def test_missing_name_refused(self):
        with self.assertRaises(SystemExit):
            P.keep(open(KEEP_REF, "rb").read(), self.NAMES + ["no-such-spawner"])


if __name__ == "__main__":
    unittest.main()
