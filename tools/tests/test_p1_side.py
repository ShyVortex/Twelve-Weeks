"""T2R_P1_SIDE: build-mode extraction + manifest (tools/features/p1_side.py) and the ext's side-file check (tools/ext/p1side.h via a gcc harness).
Offline, fake stage tree only. Run: python tools/tests/test_p1_side.py   (the C part is skipped when gcc is not found)"""
import hashlib
import os
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "features"))
import p1_side  # noqa: E402

GCC = next((c for c in (os.path.join(os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")), "tools/win/ext/msys64/ucrt64/bin/gcc.exe"),
                        os.path.join(HERE, "..", "win", "ext", "msys64", "ucrt64", "bin", "gcc.exe")) if os.path.isfile(c)), None)


def make_stage(root):
    files = {"pak68/hun-a.pak": b"AAAA" * 100, "pak68/hun-a-phys.pak": b"BB" * 50, "soundbank4/hun.bnk": b"snd" * 30,
             "actor97/books.pak": b"act", "bin/dc1/render-settings/t1x.bin": b"mod" * 9,
             "pak68/to1-pvp-p1-bookstore-ingame.pak": b"OURS", "pak68/other.pak": b"X"}
    for rel, d in files.items():
        p = os.path.join(root, *rel.split("/"))
        os.makedirs(os.path.dirname(p), exist_ok=True)
        open(p, "wb").write(d)
    return files


class SideBuild(unittest.TestCase):
    def setUp(self):
        self.td = tempfile.TemporaryDirectory()
        self.stage, self.out = os.path.join(self.td.name, "stage"), os.path.join(self.td.name, "side")
        self.files = make_stage(self.stage)
        self.paths = sorted(self.files)
        self.order = list(reversed(self.paths))
        os.environ.pop("T2R_P1_SIDE_MODULES", None)
        self.rel = ["pak68/hun-a.pak", "pak68/hun-a-phys.pak", "soundbank4/hun.bnk", "actor97/books.pak", "bin/dc1/render-settings/t1x.bin"]

    def tearDown(self):
        self.td.cleanup()

    def test_blob_has_no_part1_and_manifest_complete(self):
        r = p1_side.extract(self.stage, self.rel, self.paths, self.order, self.out, log=lambda *a: None)
        side = {e[0] for e in r["entries"]}
        self.assertEqual(side, {"pak68/hun-a.pak", "pak68/hun-a-phys.pak", "soundbank4/hun.bnk", "actor97/books.pak"})
        self.assertEqual(r["kept"], ["bin/dc1/render-settings/t1x.bin"])           # DC modules stay by default
        self.assertEqual(p1_side.verify_blob(self.paths, self.order, r["entries"], self.stage), [])
        for rel in side:
            self.assertNotIn(rel, self.paths)
            self.assertNotIn(rel, self.order)
            self.assertFalse(os.path.exists(os.path.join(self.stage, *rel.split("/"))))
        self.assertIn("pak68/to1-pvp-p1-bookstore-ingame.pak", self.paths)         # our own spawner pak stays
        self.assertIn("bin/dc1/render-settings/t1x.bin", self.paths)
        self.assertEqual(p1_side.verify_tree(self.out), [])
        ents = p1_side.parse_manifest(open(os.path.join(self.out, "manifest.txt"), newline="").read())
        self.assertEqual({e[0] for e in ents}, side)
        for rel, size, sha in ents:
            d = self.files[rel]
            self.assertEqual((size, sha), (len(d), hashlib.sha256(d).hexdigest()))

    def test_modules_move_on_request(self):
        os.environ["T2R_P1_SIDE_MODULES"] = "1"
        try:
            r = p1_side.extract(self.stage, self.rel, self.paths, self.order, self.out, log=lambda *a: None)
        finally:
            os.environ.pop("T2R_P1_SIDE_MODULES")
        self.assertIn("bin/dc1/render-settings/t1x.bin", {e[0] for e in r["entries"]})
        self.assertEqual(r["kept"], [])

    def test_missing_staged_file_fails(self):
        with self.assertRaises(FileNotFoundError):
            p1_side.extract(self.stage, self.rel + ["pak68/ghost.pak"], self.paths, self.order, self.out, log=lambda *a: None)

    def test_tree_checks_catch_damage(self):
        p1_side.extract(self.stage, self.rel, self.paths, self.order, self.out, log=lambda *a: None)
        open(os.path.join(self.out, "pak68", "stray.pak"), "wb").write(b"1")
        self.assertTrue(any("stray" in b for b in p1_side.verify_tree(self.out)))
        os.remove(os.path.join(self.out, "pak68", "stray.pak"))
        with open(os.path.join(self.out, "pak68", "hun-a.pak"), "ab") as f:
            f.write(b"!")
        self.assertTrue(any("size pak68/hun-a.pak" in b for b in p1_side.verify_tree(self.out)))

    def test_header_modes(self):
        h = os.path.join(self.td.name, "p1side_built.h")
        p1_side.write_ext_header(h)
        self.assertIn("T2R_P1_SIDE_BUILT 0", open(h).read())
        p1_side.write_ext_header(h, 0xDEADBEEF, 4, 1234, 0x0200)
        t = open(h).read()
        self.assertIn("T2R_P1_SIDE_BUILT 1", t)
        self.assertIn("0xdeadbeefu", t)
        self.assertIn("T2R_P1_SIDE_MASK 0x0200u", t)

    def test_parse_rejects_bad(self):
        h = "0" * 64
        for t in ["", "p1side 1 1 5\n", f"p1side 1 1 5\n../x\t5\t{h}\n", f"p1side 1 2 5\na\t5\t{h}\n", f"p1side 1 1 5\n/a\t5\t{h}\n",
                  f"p1side 1 2 10\na\t5\t{h}\na\t5\t{h}\n", f"p1side 1 1 6\na\t5\t{h}\n"]:
            with self.assertRaises(ValueError, msg=t):
                p1_side.parse_manifest(t)


@unittest.skipUnless(GCC, "gcc (msys64 ucrt64) not found")
class ExtCheck(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.td = tempfile.TemporaryDirectory()
        cls.exe = os.path.join(cls.td.name, "h.exe")
        env = dict(os.environ, PATH=os.path.dirname(GCC) + os.pathsep + os.environ["PATH"])
        r = subprocess.run([GCC, "-std=gnu2x", "-O1", "-Wall", "-Wextra", "-Wno-unused-function", "-o", cls.exe, os.path.join(HERE, "p1side_harness.c")],
                           capture_output=True, text=True, env=env)
        assert r.returncode == 0, r.stderr

    @classmethod
    def tearDownClass(cls):
        cls.td.cleanup()

    def run_h(self, side, crc, ok, rel=None):
        a = [self.exe, side, "%08x" % crc, str(ok)] + ([rel] if rel else [])
        env = dict(os.environ, PATH=os.path.dirname(GCC) + os.pathsep + os.environ["PATH"])
        return subprocess.run(a, capture_output=True, text=True, env=env)

    def test_descriptor_reader(self):
        exe = os.path.join(self.td.name, "d.exe")
        env = dict(os.environ, PATH=os.path.dirname(GCC) + os.pathsep + os.environ["PATH"])
        r = subprocess.run([GCC, "-std=gnu2x", "-O1", "-Wall", "-Wextra", "-Wno-unused-function", "-o", exe, os.path.join(HERE, "p1side_desc_harness.c")],
                           capture_output=True, text=True, env=env)
        self.assertEqual(r.returncode, 0, r.stderr)
        r = subprocess.run([exe], capture_output=True, text=True, env=env)
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertIn("OK 2 1 5 2 1111 2222 absent", r.stdout)
        self.assertTrue(r.stdout.rstrip().endswith("NONE"))

    def test_check_and_serve(self):
        td = tempfile.mkdtemp(dir=self.td.name)
        stage, out = os.path.join(td, "stage"), os.path.join(td, "side")
        files = make_stage(stage)
        paths = sorted(files)
        r = p1_side.extract(stage, ["pak68/hun-a.pak", "soundbank4/hun.bnk"], paths, list(paths), out, log=lambda *a: None)
        res = self.run_h(out, r["crc"], 1, "pak68/hun-a.pak")
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)
        self.assertIn("CHECK 1", res.stdout)
        self.assertIn("BADREFUSED 8", res.stdout)
        self.assertIn("FIND 400 read 8 41 41 41 41 41 41 41 41", res.stdout)
        self.assertIn("TAIL 4 41 41 41 41", res.stdout)
        self.assertIn("PASTEND 0", res.stdout)
        self.assertIn("NOFIND-OK", res.stdout)
        # another build's manifest, a wrong size, a missing file, no manifest: all refused
        self.assertIn("CHECK 0", self.run_h(out, r["crc"] ^ 1, 0).stdout)
        f = os.path.join(out, "soundbank4", "hun.bnk")
        with open(f, "ab") as fh:
            fh.write(b"x")
        self.assertIn("size mismatch soundbank4/hun.bnk", self.run_h(out, r["crc"], 0).stdout)
        os.remove(f)
        self.assertIn("missing soundbank4/hun.bnk", self.run_h(out, r["crc"], 0).stdout)
        self.assertIn("no manifest", self.run_h(os.path.join(td, "nothing"), 0, 0).stdout)


class SplitPayload(unittest.TestCase):
    """T2R_P1_SIDE_VIRT layout: blob payload + side file == the one unsplit archive (re/part1/side-files.md, t2r_pack.split_payload)"""

    def test_split_roundtrip_and_alignment(self):
        sys.path.insert(0, os.path.join(HERE, ".."))
        import t2r_pack as T
        files = {f"pak68/m{i}.pak": os.urandom(5000 + i * 3000) for i in range(6)}
        files["pak68/side-a.pak"] = os.urandom(300000)
        files["soundbank4/side-b.bnk"] = os.urandom(100000)
        paths = sorted(files)
        meta = {"flags": 12, "paths": paths, "data_order": paths, "trail": False}
        for delta in (0, 0x1234, 0xFFF8):
            phys, side, info = T.split_payload(meta, files, ["pak68/side-a.pak", "soundbank4/side-b.bnk"], delta)
            self.assertEqual((delta + info["cut"]) % 0x10000, 0)
            self.assertEqual(len(phys), info["cut"])
            dec = T.keystream_xor(phys + side)
            self.assertEqual(dec, info["dsar"])
            m, f = T.psarc_read(T.dsar_read(dec))
            self.assertEqual((f, m["paths"]), (files, paths))
            self.assertGreater(len(side), 400000 - 10)          # the side files' chunks are all behind the cut
            self.assertLess(len(phys), len(side))

    def test_archive_form(self):
        td = tempfile.TemporaryDirectory()
        self.addCleanup(td.cleanup)
        stage, out = os.path.join(td.name, "s"), os.path.join(td.name, "o")
        files = make_stage(stage)
        paths = sorted(files)
        p1_side.extract(stage, ["pak68/hun-a.pak", "soundbank4/hun.bnk"], paths, list(paths), out, log=lambda *a: None)
        a = os.path.join(td.name, "part1-a.psarc")
        info = p1_side.pack_archive(out, a, log=lambda *x: None)
        self.assertEqual(open(a, "rb").read(4), b"DSAR")
        self.assertEqual(os.path.getsize(a), info["size"])
        mp = os.path.join(td.name, "part1-a.txt")
        p1_side.write_pack_manifest(mp, "part1-a", 1, "part1-a.psarc", info, [("to1-p1-bookstore", "Bookstore", "p1-bookstore")])
        t = open(mp).read()
        self.assertIn("file=part1-a.psarc", t)
        self.assertIn("size=%d" % info["size"], t)
        self.assertIn("hash=%08x" % info["crc32"], t)


if __name__ == "__main__":
    unittest.main(verbosity=2)
