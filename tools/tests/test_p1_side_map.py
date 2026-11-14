"""The winmm side-file cave (tools/features/p1_side_map.py) EXECUTED in a fake image by tools/tests/p1s_cave_harness.c: present / absent / wrong size /
bad geometry / missing winmm.dll / side path unusable / nothing baked. Also: IAT slots vs the base DLL's imports, hook bytes vs the base DLL.
Run: python tools/tests/test_p1_side_map.py   (needs the msys64 gcc; skipped without it)"""
import os
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "features"))
import p1_side_map as M  # noqa: E402

GCC = next((c for c in (os.path.join(os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")), "tools/win/ext/msys64/ucrt64/bin/gcc.exe"),
                        os.path.join(HERE, "..", "win", "ext", "msys64", "ucrt64", "bin", "gcc.exe")) if os.path.isfile(c)), None)
BASE_DLL = next((c for c in (os.path.join(os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")), "tools/local/winmm-nocave-127.0.0.1-7001.dll"),
                             os.path.join(HERE, "..", "local", "winmm-nocave-127.0.0.1-7001.dll")) if os.path.isfile(c)), None)
SEC_VA = 0x200000
DELTA = 0x1230
FO = 0x30000 + DELTA
SIZE1 = 3 * 0x10000 - DELTA           # (DELTA + SIZE1) % 64 KiB == 0
SIZE2 = 150000
BID = bytes(range(16))


@unittest.skipUnless(BASE_DLL, "unpatched winmm dll not found")
class BaseDll(unittest.TestCase):
    def test_iat_and_hook(self):
        import pefile
        pe = pefile.PE(BASE_DLL, fast_load=True)
        pe.parse_data_directories([pefile.DIRECTORY_ENTRY["IMAGE_DIRECTORY_ENTRY_IMPORT"]])
        have = {}
        for e in pe.DIRECTORY_ENTRY_IMPORT:
            for i in e.imports:
                if i.name:
                    have[i.name.decode()] = i.address
        for n, va in M.IAT.items():
            self.assertEqual(have.get(n), va, n)
        d = open(BASE_DLL, "rb").read()
        off = pe.get_offset_from_rva(M.HOOK_VMA - M.IMAGE_BASE)
        self.assertEqual(d[off:off + 6], M.HOOK_ORIG)
        out = M.add(d, SIZE2)
        va = M.check(out)
        self.assertGreater(va, 0)
        off2 = pe.get_offset_from_rva(M.HOOK_VMA - M.IMAGE_BASE)
        self.assertEqual(out[off2], 0xE9)
        with self.assertRaises(SystemExit):
            M.add(out, SIZE2)                          # twice: refused


@unittest.skipUnless(GCC, "gcc (msys64 ucrt64) not found")
class Cave(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.td = tempfile.TemporaryDirectory()
        cls.exe = os.path.join(cls.td.name, "h.exe")
        cls.env = dict(os.environ, PATH=os.path.dirname(GCC) + os.pathsep + os.environ["PATH"])
        r = subprocess.run([GCC, "-std=gnu2x", "-O1", "-Wall", "-Wno-cast-function-type", "-o", cls.exe, os.path.join(HERE, "p1s_cave_harness.c")],
                           capture_output=True, text=True, env=cls.env)
        assert r.returncode == 0, r.stderr

    @classmethod
    def tearDownClass(cls):
        cls.td.cleanup()

    def scenario(self, size2_baked=SIZE2, side=True, side_size=SIZE2, dll=True, size1=SIZE1, side_is_dir=False, trailer=BID):
        d = tempfile.mkdtemp(dir=self.td.name)
        if dll:
            with open(os.path.join(d, "fake.dll"), "wb") as f:
                f.write(os.urandom(FO + SIZE1 + 0x5000))
        os.makedirs(os.path.join(d, "t2r-maps", "part1"))
        sp = os.path.join(d, "t2r-maps", "part1", "part1.dat")
        if side_is_dir:
            os.mkdir(sp)
        elif side:
            with open(sp, "wb") as f:
                f.write(os.urandom(side_size) + trailer)
        sec, entry, _ = M.build_section(SEC_VA, size2_baked, BID)
        sb = os.path.join(d, "sec.bin")
        with open(sb, "wb") as f:
            f.write(sec)
        r = subprocess.run([self.exe, sb, "%x" % (M.IMAGE_BASE + SEC_VA), "%x" % entry, d, str(size1), str(FO), str(size2_baked)],
                           capture_output=True, text=True, env=self.env, timeout=60)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        out = r.stdout
        kv = dict(x.split("=") for x in out.split("RESULT ")[1].split("\n")[0].split())
        return kv, out

    def test_present(self):
        kv, out = self.scenario()
        self.assertEqual((kv["status"], kv["layout"], kv["ret"], kv["d8"]), ("1", "3", "1", str(SIZE1 + SIZE2)), out)
        self.assertIn("MEM full-ok", out)

    def test_absent(self):
        kv, out = self.scenario(side=False)
        self.assertEqual((kv["status"], kv["layout"], kv["ret"], kv["d8"]), ("2", "1", "1", str(SIZE1 + SIZE2)), out)
        self.assertIn("MEM view1-ok-hole-reserved", out)

    def test_wrong_size(self):
        kv, out = self.scenario(side_size=SIZE2 - 1)
        self.assertEqual((kv["status"], kv["layout"], kv["step"], kv["err"], kv["ret"]), ("3", "1", "6", "ffff0003", "1"), out)
        self.assertIn("MEM view1-ok-hole-reserved", out)

    def test_other_build_id(self):
        kv, out = self.scenario(trailer=bytes(16))
        self.assertEqual((kv["status"], kv["layout"], kv["step"], kv["err"], kv["ret"]), ("3", "1", "7", "ffff0004", "1"), out)
        self.assertIn("MEM view1-ok-hole-reserved", out)

    def test_bad_geometry(self):
        kv, out = self.scenario(size1=SIZE1 + 8)           # the build asserts alignment; if it were broken the mount must still pass
        self.assertEqual((kv["status"], kv["step"], kv["ret"], kv["d8"]), ("3", "9", "1", str(SIZE1 + 8 + SIZE2)), out)
        self.assertNotIn("BAD", out)

    def test_dll_missing(self):
        kv, out = self.scenario(dll=False)
        self.assertEqual((kv["status"], kv["layout"], kv["step"], kv["ret"], kv["d8"]), ("3", "2", "3", "1", str(SIZE1 + SIZE2)), out)
        self.assertIn("MEM d0-unchanged", out)

    def test_side_path_unusable(self):
        kv, out = self.scenario(side_is_dir=True)
        self.assertEqual((kv["status"], kv["layout"], kv["ret"]), ("3", "1", "1"), out)
        self.assertIn("MEM view1-ok-hole-reserved", out)

    def test_nothing_baked(self):
        kv, out = self.scenario(size2_baked=0)
        self.assertEqual((kv["status"], kv["layout"], kv["ret"], kv["d8"]), ("0", "0", "1", str(SIZE1)), out)


@unittest.skipUnless(GCC and BASE_DLL, "gcc and the unpatched winmm dll needed")
class EndToEnd(unittest.TestCase):
    """pack_split_bytes on a real base DLL + a small stage, the finished image and part1.dat fed to the cave harness: the engine's view
    (view1 + view2, payload pointer d0, size d8) decodes to exactly the files that were packed"""

    def test_split_dll_maps_and_decodes(self):
        sys.path.insert(0, os.path.join(HERE, ".."))
        import t2r_pack as T
        td = tempfile.mkdtemp()
        stage = os.path.join(td, "stage")
        files = {}
        for i in range(5):
            files[f"pak68/m{i}.pak"] = os.urandom(20000 + i * 7000)
        files["pak68/p1-a.pak"] = os.urandom(400000)
        files["soundbank4/p1-b.bnk"] = os.urandom(200000)
        for p, d in files.items():
            fp = os.path.join(stage, *p.split("/"))
            os.makedirs(os.path.dirname(fp), exist_ok=True)
            with open(fp, "wb") as f:
                f.write(d)
        paths = sorted(files)
        with open(os.path.join(stage, "_t2r_manifest.txt"), "w", newline="\n") as f:
            f.write("flags=12 trail=0\n" + "\n".join(paths) + "\n--order--\n" + "\n".join(paths) + "\n")
        base = open(BASE_DLL, "rb").read()
        probe = T.write_dll(base, T.build_t2me(bytes(4096)))
        delta = T.payload_file_offset(probe) % 0x10000
        out, side, info = T.pack_split_bytes(base, stage, ["pak68/p1-a.pak", "soundbank4/p1-b.bnk"], delta)
        fo = T.payload_file_offset(out)
        self.assertEqual((fo + info["size1"]) % 0x10000, 0)
        self.assertEqual(len(side), info["size2"] + 16)
        self.assertEqual(side[-16:], info["build_id"])
        sec, entry, _ = M.build_section(SEC_VA, info["size2"], info["build_id"])
        d = os.path.join(td, "run")
        os.makedirs(os.path.join(d, "t2r-maps", "part1"))
        with open(os.path.join(d, "fake.dll"), "wb") as f:
            f.write(out)
        with open(os.path.join(d, "t2r-maps", "part1", "part1.dat"), "wb") as f:
            f.write(side)
        with open(os.path.join(td, "sec.bin"), "wb") as f:
            f.write(sec)
        h = os.path.join(td, "h.exe")
        env = dict(os.environ, PATH=os.path.dirname(GCC) + os.pathsep + os.environ["PATH"])
        r = subprocess.run([GCC, "-std=gnu2x", "-O1", "-o", h, os.path.join(HERE, "p1s_cave_harness.c")], capture_output=True, text=True, env=env)
        self.assertEqual(r.returncode, 0, r.stderr)
        dump = os.path.join(td, "view.bin")
        r = subprocess.run([h, os.path.join(td, "sec.bin"), "%x" % (M.IMAGE_BASE + SEC_VA), "%x" % entry, d, str(info["size1"]), str(fo),
                            str(info["size2"]), dump], capture_output=True, text=True, env=env, timeout=120)
        self.assertIn("status=1 layout=3", r.stdout, r.stdout + r.stderr)
        self.assertIn("MEM full-ok", r.stdout)
        view = open(dump, "rb").read()
        self.assertEqual(len(view), info["size1"] + info["size2"])
        m, f2 = T.psarc_read(T.dsar_read(T.keystream_xor(view)))
        self.assertEqual((f2, m["paths"]), (files, paths))


if __name__ == "__main__":
    unittest.main(verbosity=2)
