"""Offline test for the ext's crash-diag block (tools/ext/crashdiag.h) and its reader (tools/reports/cdiag_rings.py).
Compiles tools/tests/crashdiag_harness.c (checks the ring code + per-event cost), parses the raw block it writes, compares the reader's layout and
content with the C side, and finds the block in a synthetic minidump memory image (as WER dumps hold it).
Run: python tools/tests/test_crashdiag.py   (plain python; needs gcc: PATH or tools/win/ext/msys64/ucrt64/bin; skips the C part without one)."""
import io
import os
import re
import shutil
import struct
import subprocess
import sys
import tempfile
import sys as _t2s, os as _t2o; _t2s.path.append(_t2o.path.normpath(_t2o.path.join(_t2o.path.dirname(_t2o.path.abspath(__file__)), ".."))); import t2rtmp  # noqa: E402,F401

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(TOOLS, "reports"))
import cdiag_rings as cr  # noqa: E402

FAILS = []


def check(cond, what):
    print(("ok   " if cond else "FAIL ") + what)
    if not cond:
        FAILS.append(what)


def find_gcc():
    g = shutil.which("gcc")
    if g:
        return g
    root = os.path.dirname(TOOLS)
    for _ in range(5):      # the repo root, or the main checkout above a git worktree (the MSYS2 toolchain is not tracked)
        p = os.path.join(root, "tools", "win", "ext", "msys64", "ucrt64", "bin", "gcc.exe")
        if os.path.exists(p):
            return p
        root = os.path.dirname(root)
    return None


class Seg:
    def __init__(self, start, data):
        self.start_virtual_address, self.size, self.end_virtual_address = start, len(data), start + len(data)
        self.data = data

    def inrange(self, a):
        return self.start_virtual_address <= a < self.end_virtual_address

    def read(self, a, n, fh):
        o = a - self.start_virtual_address
        assert o >= 0 and o + n <= self.size
        return self.data[o:o + n]


class Mod:
    def __init__(self, name, base, size):
        self.name, self.baseaddress, self.size = name, base, size


def main():
    tmp = tempfile.mkdtemp(prefix="cdiag-")
    try:
        gcc = find_gcc()
        img = os.path.join(tmp, "cdiag.bin")
        if gcc:
            exe = os.path.join(tmp, "h.exe")
            env = dict(os.environ)
            env["PATH"] = os.path.dirname(gcc) + os.pathsep + env.get("PATH", "")
            r = subprocess.run([gcc, "-std=gnu2x", "-O2", "-o", exe, os.path.join(HERE, "crashdiag_harness.c")], capture_output=True, text=True, env=env)
            check(r.returncode == 0, "harness compiles (%s)" % r.stderr[-200:])
            r = subprocess.run([exe, img], capture_output=True, text=True, env=env, timeout=120)
            check(r.returncode == 0 and "HARNESS OK" in r.stdout, "C ring checks pass")
            m = re.search(r"COST ns/event: body event ([\d.]+), set test \(miss\) ([\d.]+), compaction begin\+end ([\d.]+), world sample \(512 B\) ([\d.]+)", r.stdout)
            check(bool(m), "cost line printed: %s" % (m.group(0) if m else r.stdout[-200:]))
            lay = re.search(r"LAYOUT magic@0 self@(\d+) cm@(\d+) be@(\d+) hk@(\d+) pup@(\d+) cm_i@(\d+) be_i@(\d+) hk_i@(\d+) pup_i@(\d+) cm_active@(\d+) cm_frame@(\d+) size (\d+)", r.stdout)
            check(bool(lay), "layout line printed")
            if lay:
                s_, cm_, be_, hk_, pup_, cmi, bei, hki, pupi, act, cmf, size = map(int, lay.groups())
                L = cr.layout()
                check((cm_, be_, hk_, pup_, size) == (L["cm"], L["be"], L["hk"], L["pup"], L["size"]), "reader offsets = C offsets (cm %d be %d hk %d pup %d size %d)" % (cm_, be_, hk_, pup_, size))
                check((cmi, bei, hki, pupi) == (L["cm_i"], L["be_i"], L["hk_i"], L["pup_i"]), "reader index offsets = C")
                check(cr.HDR.size == cm_ - 8 * cr.BE_SET, "header size")
            raw = open(img, "rb").read()
            h = cr.parse_block(raw)
            check(h["cm_active"] == 1 and h["cm_frame"] == 9999 and h["cm_calls"] == 70 and h["cm_moves"] == 7, "compaction state parsed (active, frame, counts)")
            check(h["be_i"] == 148 and h["be"][148 & 127][4] == 0xA000 + 148, "body event ring parsed")
            check(h["hk_i"] == 40 and h["hk"][40 & 31][3 + 5] == 1039, "havok sample parsed")
            check(h["pup"][2][3] == 4 and h["pup"][2][7] == 0xBEEF0000, "puppet event parsed")
            names = {0x1111: "kill-entity", 0x2222: "spawn-object"}
            lines = cr.report(h, names)
            txt = "\n".join(lines)
            check("COMPACTION WAS RUNNING" in txt and "kill-entity (1111)" in txt and "attach table registered" in txt and "world+028" in txt and "CHANGED" in txt, "reader report has the same sections as the C report")
            c_txt = open(img + ".txt").read()
            frames_c = re.findall(r"frame (\d+)", c_txt)
            frames_p = re.findall(r"frame (\d+)", txt)
            check(frames_c and sorted(frames_c) == sorted(frames_p) or set(frames_c) == set(frames_p), "frames in the C report = frames in the reader report")
            # a synthetic memory image holding the block at a fake address inside the ext module (what a WER dump with data segments looks like)
            base = 0x7ff800000000
            addr = base + 0x1230000
            blk = bytearray(raw)
            struct.pack_into("<Q", blk, 16, addr)
            seg = Seg(addr - 0x2000, b"\0" * 0x2000 + bytes(blk) + b"\0" * 0x1000)
            other = Seg(base + 0x2000000, b"\xaa" * 0x1000)

            class RD:
                memory_segments = [seg, other]
                file_handle = io.BytesIO()

            class MD:
                class modules:
                    modules = [Mod("C:\\x\\t2r-ext.dll", base, 0x31f0000)]

                @staticmethod
                def get_reader():
                    return RD

            got = cr.find_in_dump(MD)
            check(got is not None and got[1] == addr and got[0][:8] == b"T2RCDG01", "block found by magic + self pointer inside the ext module's segments")
            # a copy of the image elsewhere (self pointer differs) must not be taken for the live block
            blk2 = bytearray(raw)
            RD.memory_segments = [Seg(base + 0x1000, bytes(blk2))]
            check(cr.find_in_dump(MD) is None, "a stale copy (self pointer differs) is rejected")
            # the crash handler's own file (tools/ext/crashbin.h): written by cb_write from a fake exception record, parsed back
            bd = os.path.join(tmp, "bin")
            os.mkdir(bd)
            bexe = os.path.join(tmp, "cb.exe")
            r = subprocess.run([gcc, "-std=gnu2x", "-O2", "-o", bexe, os.path.join(HERE, "crashbin_harness.c")], capture_output=True, text=True, env=env)
            check(r.returncode == 0, "crashbin harness compiles (%s)" % r.stderr[-200:])
            r = subprocess.run([bexe, bd], capture_output=True, text=True, env=env, timeout=60)
            m = re.search(r"HARNESS OK pid (\d+)", r.stdout)
            check(r.returncode == 0 and bool(m), "crashbin harness passes: %s" % r.stdout[-200:])
            # when the report runs (tools/ext/crashfilter.h): handled exceptions write nothing, a real unhandled AV writes the file once and chains the game's filter
            fd = os.path.join(tmp, "cf")
            os.mkdir(fd)
            fexe = os.path.join(tmp, "cf.exe")
            r = subprocess.run([gcc, "-std=gnu2x", "-O2", "-o", fexe, os.path.join(HERE, "crashfilter_harness.c")], capture_output=True, text=True, env=env)
            check(r.returncode == 0, "crashfilter harness compiles (%s)" % r.stderr[-200:])
            r = subprocess.run([fexe, fd], capture_output=True, text=True, env=env, timeout=120)
            check(r.returncode == 0 and "HARNESS OK" in r.stdout, "crashfilter harness passes (handled = no evidence, fatal = evidence once + chained): %s" % r.stdout[-300:])
            if m:
                pid = int(m.group(1))
                left = sorted(os.listdir(bd))
                check(left == ["t2r-crash-%d-1.bin" % pid, "t2r-crash-1001-1.bin", "t2r-crash-1002-1.bin", "t2r-crash-notes.txt"] or
                      left == sorted(["t2r-crash-%d-1.bin" % pid, "t2r-crash-1001-1.bin", "t2r-crash-1002-1.bin", "t2r-crash-notes.txt"]),
                      "startup keeps the newest 3 t2r-crash-*.bin (2 old + this process's), ignores other files: %s" % left)
                data = open(os.path.join(bd, "t2r-crash-%d-1.bin" % pid), "rb").read()
                check(len(data) <= 128 + 30 * 1024 + 20 * 1024 + 64 * 220 + 4096, "file size is bounded (%d)" % len(data))
                f, hb, rd2 = cr.parse_bin(data)
                check(f["pid"] == pid and f["tid"] == 77 and f["code"] == 0xC0000005 and f["addr"] == 0x1415f52b0 and f["info1"] == 0x1f0 and f["frame"] == 4321,
                      "header: pid / tid / code / address / info / frame (one shot: the second call wrote nothing)")
                check(f["build"] == "Oct 19 2026 12:34:56 (release)" and f["ctime"] > 0, "header: build stamp and process create time")
                check(hb["be_i"] == 140 and hb["be"][140 & 127][4] == 0xA000 + 140, "block inside the file parses (body event ring)")
                lines = "\n".join(cr.report(hb, {}, rd2))
                check("native ring" in lines and "a0 b258" in lines and "log line 700" in lines and "log line 661" in lines and "log line 660" not in lines,
                      "native ring and the last 40 log lines read back from the file")
                try:
                    cr.parse_bin(data[:5000])
                    check(False, "a truncated file is rejected")
                except ValueError:
                    check(True, "a truncated file is rejected")
        else:
            print("skip C harness: no gcc")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    print("%d failed" % len(FAILS) if FAILS else "ALL OK")
    return 1 if FAILS else 0


if __name__ == "__main__":
    sys.exit(main())
