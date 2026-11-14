"""T2R_P1_SIDE=1 end to end WITHOUT the 20-minute stage: build_dll.build() with stage_modfs replaced by a tiny prebuilt stage, on the real unpatched winmm.
Checks the finished winmm (all patches + the .t2rps cave) + part1.dat + manifest: the blob holds no Part I bytes, the payload file offset + cut is
64 KiB aligned, the cave maps the pair (offline harness) and the engine's view decodes to every packed file.
Run: python tools/tests/test_p1_side_build.py   (needs the msys64 gcc and the unpatched winmm dll; ~1-2 min)"""
import os
import subprocess
import sys
import tempfile
import types
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "features"))
sys.path.insert(0, os.path.join(HERE, ".."))

GCC = next((c for c in (os.path.join(os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")), "tools/win/ext/msys64/ucrt64/bin/gcc.exe"),
                        os.path.join(HERE, "..", "win", "ext", "msys64", "ucrt64", "bin", "gcc.exe")) if os.path.isfile(c)), None)
BASE = next((c for c in (os.path.join(os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")), "tools/local/winmm-nocave-127.0.0.1-7001.dll"),
                         os.path.join(HERE, "..", "local", "winmm-nocave-127.0.0.1-7001.dll")) if os.path.isfile(c)), None)


@unittest.skipUnless(GCC and BASE, "gcc and the unpatched winmm dll needed")
class SideBuild(unittest.TestCase):
    def test_build(self):
        import build_dll as B
        import p1_side
        import p1_side_map as M
        import t2r_pack as T
        td = tempfile.mkdtemp()
        stage = os.path.join(td, "stage")
        files = {f"pak68/m{i}.pak": os.urandom(30000 + i * 9000) for i in range(6)}
        files["pak68/p1-lvl.pak"] = os.urandom(500000)
        files["soundbank4/p1-snd.bnk"] = os.urandom(250000)
        big = bool(os.environ.get("T2R_TEST_SHRINK"))        # T2R_TEST_SHRINK=1: a >162 MB payload, so the blob leaves the resource and shrink_rsrc runs like in a real build
        if big:
            blk = os.urandom(1 << 20)
            files["pak68/m-big.pak"] = b"".join(blk[i:] + blk[:i] for i in range(0, 170 * 4096, 4096))
        files["bin/dc1/render-settings/t1x.bin"] = os.urandom(5000)        # a DC module: stays in the blob
        for p, d in files.items():
            fp = os.path.join(stage, *p.split("/"))
            os.makedirs(os.path.dirname(fp), exist_ok=True)
            with open(fp, "wb") as f:
                f.write(d)
        paths = sorted(files)
        with open(os.path.join(stage, "_t2r_manifest.txt"), "w", newline="\n") as f:
            f.write("flags=12 trail=0\n" + "\n".join(paths) + "\n--order--\n" + "\n".join(paths) + "\n")
        side_rel, kept = p1_side.split(["pak68/p1-lvl.pak", "soundbank4/p1-snd.bnk", "bin/dc1/render-settings/t1x.bin"])
        self.assertEqual(kept, ["bin/dc1/render-settings/t1x.bin"])
        outdir = os.path.join(td, "side-out")
        os.environ["T2R_P1_SIDE_OUT"] = outdir
        os.environ["T2R_FAST_PACK"] = "1"
        os.environ["T2R_SHRINK_RSRC"] = "1" if big else "0"        # (the tiny test payload fits the original resource; shrink_rsrc only runs on real, large payloads)

        def fake_stage(salt=0):
            B._P1_VIRT = {"paths": side_rel, "kept": kept, "entries": p1_side.audit_entries(stage, side_rel)}
        B.stage_modfs = fake_stage
        B.STAGE = stage
        B.BASE_DLL = BASE
        B.start_ext_compile = lambda *a, **k: None
        dll = os.path.join(td, "winmm.dll")
        B.build(types.SimpleNamespace(out=dll, port=7001, ext=None), 0)
        # ---- deliverables
        self.assertEqual(p1_side.verify_tree.__name__, "verify_tree")
        data = open(dll, "rb").read()
        side = open(os.path.join(outdir, "part1.dat"), "rb").read()
        man = p1_side.parse_manifest(open(os.path.join(outdir, "manifest.txt"), newline="").read())
        self.assertEqual([(m[0], m[1]) for m in man], [("part1.dat", len(side))])
        self.assertEqual(len(p1_side.parse_manifest(open(os.path.join(outdir, "files.txt"), newline="").read())), 2)
        M.check(data)
        # ---- the blob holds none of the Part I data
        phys, _h = T.read_t2me(data)
        view = T.keystream_xor(phys + side[:-16])
        m, f2 = T.psarc_read(T.dsar_read(view))
        self.assertEqual(f2, files)
        for p in side_rel:
            self.assertNotIn(files[p][:4096], T.keystream_xor(phys))      # (random data: its first 4 KiB cannot occur in the cut-off blob)
        self.assertLess(len(phys), len(view) - 700000)
        fo = T.payload_file_offset(data)
        self.assertEqual((fo + len(phys)) % 0x10000, 0)
        # ---- run the cave on the finished image
        sec_rva = M.check(data)
        size2 = len(side) - 16
        import struct
        pe = struct.unpack_from("<I", data, 0x3C)[0]
        nsec = struct.unpack_from("<H", data, pe + 6)[0]
        optsz = struct.unpack_from("<H", data, pe + 20)[0]
        sec = None
        for i in range(nsec):
            b = pe + 24 + optsz + 40 * i
            if data[b:b + 8].rstrip(b"\0") == M.NAME:
                vs, va, rs, rp = struct.unpack_from("<IIII", data, b + 8)
                sec = data[rp:rp + rs]
        sec_bin = os.path.join(td, "sec.bin")
        with open(sec_bin, "wb") as f:
            f.write(sec)
        entry = M.build_section(sec_rva, size2, side[-16:])[1]
        self.assertEqual(sec, M.build_section(sec_rva, size2, side[-16:])[0].ljust(len(sec), b"\0"))
        run = os.path.join(td, "run")
        os.makedirs(os.path.join(run, "t2r-maps", "part1"))
        with open(os.path.join(run, "fake.dll"), "wb") as f:
            f.write(data)
        with open(os.path.join(run, "t2r-maps", "part1", "part1.dat"), "wb") as f:
            f.write(side)
        h = os.path.join(td, "h.exe")
        env = dict(os.environ, PATH=os.path.dirname(GCC) + os.pathsep + os.environ["PATH"])
        r = subprocess.run([GCC, "-std=gnu2x", "-O1", "-o", h, os.path.join(HERE, "p1s_cave_harness.c")], capture_output=True, text=True, env=env)
        self.assertEqual(r.returncode, 0, r.stderr)
        dump = os.path.join(td, "view.bin")
        r = subprocess.run([h, sec_bin, "%x" % (M.IMAGE_BASE + sec_rva), "%x" % entry, run, str(len(phys)), str(fo), str(size2), dump],
                           capture_output=True, text=True, env=env, timeout=300)
        self.assertIn("status=1 layout=3", r.stdout, r.stdout + r.stderr)
        self.assertIn("MEM full-ok", r.stdout)
        m, f3 = T.psarc_read(T.dsar_read(T.keystream_xor(open(dump, "rb").read())))
        self.assertEqual(f3, files)


if __name__ == "__main__":
    unittest.main(verbosity=2)
