"""Offline test for the ext's mouse sensitivity guard (tools/ext/t2r-ext.c, "mouse sensitivity guard", re/sens-reset-1019.md).
Cuts the guard out of t2r-ext.c, compiles it against a fake exe image + temp folder (no game, no save folder, no registry) and checks:
  - the six globals at the -1 'never set' sentinel get the values of t2r-sens.txt, a value the profile / player set is never touched
  - a change of a global is followed and written to t2r-sens.txt (and the file never receives the -1 sentinel)
  - a different exe build (loader signature) switches the guard off, as does t2r-no-sens-guard.txt
  - a short / garbage file is ignored
Also, when the game's exe is installed here, checks that the profile loader and saver of the six mouse sensitivities use the very globals
the guard watches (skipped without the exe).
Run: python tools/tests/test_sens_guard.py   (needs gcc: PATH or tools/win/ext/msys64/ucrt64/bin; the C part is skipped without one)."""
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
EXT = os.path.join(TOOLS, "ext", "t2r-ext.c")
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
    for _ in range(5):
        p = os.path.join(root, "tools", "win", "ext", "msys64", "ucrt64", "bin", "gcc.exe")
        if os.path.exists(p):
            return p
        root = os.path.dirname(root)
    return None


src = open(EXT, "rb").read().decode("latin1")
a = src.find("// ---------------------------------------------------------------- mouse sensitivity guard")
b = src.find("// ---------------------------------------------------------------- crash logger")
check(a > 0 and b > a, "guard block found in t2r-ext.c")
block = src[a:b].replace("\r\n", "\n")
check("PF(feature_sens_guard());" in src, "feature_sens_guard is called from the tick")
check(re.search(r"SENS_RVA\[N_SENS\] = \{0x3768728, 0x3768734, 0x3768724, 0x3768730, 0x376872c, 0x3768738\}", block) is not None, "the six global RVAs")
# t2r-ext.c is an LF file (it has been for 30+ commits; a whole-file flip to CRLF would wreck every diff); a few stray CRLF lines from
# editors are tolerated, a flipped or half-flipped file is not
_n_crlf = src.count("\r\n"); _n_lines = src.count("\n")
check(_n_crlf * 100 < _n_lines, "t2r-ext.c keeps its LF line ends (%d of %d lines CRLF)" % (_n_crlf, _n_lines))

HARNESS = r'''
#include <stdio.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>
#include <windows.h>
static uint8_t *g_img;
static int g_frame;
static const char *g_dir;
static void xlog(const char *f, ...) { (void)f; }
static void hook_miss(void *p, int n, const char *w) { (void)p; (void)n; printf("miss: %s\n", w); }
static HMODULE fake_module(void *x) { (void)x; return (HMODULE)g_img; }
#define GetModuleHandleW fake_module
static FILE *exe_side_open(const char *name, const char *mode) {
    char p[600]; snprintf(p, sizeof p, "%s\\%s", g_dir, name);
    if (mode[0] == 'r') { FILE *f = fopen(p, "r"); return f; }
    return fopen(p, mode);
}
#include "block.c"
static float *gl(int i) { return (float *)(g_img + SENS_RVA[i]); }
static void tick(int frames) { for (int k = 0; k < frames; k++) { g_frame++; feature_sens_guard(); } }
int main(int argc, char **argv) {
    (void)argc;
    g_dir = argv[1];
    g_img = calloc(1, 0x3800000);
    for (int i = 0; i < N_SENS; i++) *gl(i) = -1.0f;
    // the loader signature at exe+0x121ce51: vmovss [rip+disp], xmm0 -> SENS_RVA[0]
    uint8_t *st = g_img + 0x121ce51; st[0] = 0xC5; st[1] = 0xFA; st[2] = 0x11; st[3] = 0x05;
    int32_t disp = (int32_t)(SENS_RVA[0] - (0x121ce51 + 8)); memcpy(st + 4, &disp, 4);
    const char *mode = argv[2];
    if (!strcmp(mode, "restore")) {          // file with values, globals unset -> restored; one global already set -> untouched
        *gl(2) = 0.8f;
        tick(31);
        printf("g0=%.3f g1=%.3f g2=%.3f g3=%.3f g4=%.3f g5=%.3f\n", *gl(0), *gl(1), *gl(2), *gl(3), *gl(4), *gl(5));
    } else if (!strcmp(mode, "follow")) {    // the player moves look x: followed, written; unset globals never written as values
        tick(31);
        *gl(0) = 0.7f;
        tick(120);
        printf("g0=%.3f\n", *gl(0));
    } else if (!strcmp(mode, "bulk")) {      // the profile applies the player's values, then the level start writes the defaults to all six
        for (int i = 0; i < N_SENS; i++) *gl(i) = 0.3f + 0.01f * i;
        tick(31);
        for (int i = 0; i < N_SENS; i++) *gl(i) = 0.25f;
        tick(31);
        printf("g0=%.3f g5=%.3f\n", *gl(0), *gl(5));
        *gl(1) = 0.6f;                       // a slider moved afterwards is still followed
        tick(120);
        printf("g1=%.3f\n", *gl(1));
    } else if (!strcmp(mode, "defaults")) {  // the first scan finds all six at the data defaults
        static const float DEF[N_SENS] = {0.5f, 0.5f, 0.5f, 0.5f, 0.25f, 0.25f};   // the data defaults (SENS_DEF since 54714605: look / aim 0.5, scoped 0.25)
        for (int i = 0; i < N_SENS; i++) *gl(i) = DEF[i];
        tick(31);
        printf("g0=%.3f g5=%.3f\n", *gl(0), *gl(5));
    } else if (!strcmp(mode, "badsig")) {
        st[0] = 0x90;
        tick(31);
        printf("g0=%.3f state=%d\n", *gl(0), g_sens_state);
    } else if (!strcmp(mode, "flag")) {
        tick(31);
        printf("g0=%.3f state=%d\n", *gl(0), g_sens_state);
    }
    return 0;
}
'''

gcc = find_gcc()
if not gcc:
    print("skip C part: no gcc")
else:
    tmp = tempfile.mkdtemp(prefix="t2r-sens-")
    try:
        open(os.path.join(tmp, "block.c"), "w").write(block)
        open(os.path.join(tmp, "h.c"), "w").write(HARNESS)
        exe = os.path.join(tmp, "h.exe")
        env = dict(os.environ)
        env["PATH"] = os.path.dirname(gcc) + os.pathsep + env.get("PATH", "")
        r = subprocess.run([gcc, "-std=gnu2x", "-O1", "-o", exe, os.path.join(tmp, "h.c"), "-I", tmp], capture_output=True, text=True, env=env)
        check(r.returncode == 0, "harness compiles" + ("" if r.returncode == 0 else ": " + r.stderr[-600:]))
        if r.returncode == 0:
            def run(mode, files):
                d = tempfile.mkdtemp(prefix="g-", dir=tmp)
                for n, c in files.items():
                    open(os.path.join(d, n), "w").write(c)
                o = subprocess.run([exe, d, mode], capture_output=True, text=True, env=env).stdout
                return d, o
            # 1 restore
            d, o = run("restore", {"t2r-sens.txt": "0.25 0.3 0.35 0.4 0.45 0.5 \n# x\n"})
            check("g0=0.250 g1=0.300 g2=0.800 g3=0.400 g4=0.450 g5=0.500" in o, "unset globals restored from the file, a set one untouched: " + o.strip())
            # 2 no file: nothing invented
            d, o = run("restore", {})
            check("g0=-1.000 g1=-1.000 g2=0.800 g3=-1.000" in o, "no file: unset globals stay unset: " + o.strip())
            # 3 follow + write
            d, o = run("follow", {"t2r-sens.txt": "0.25 0.3 0.35 0.4 0.45 0.5 \n"})
            vals = open(os.path.join(d, "t2r-sens.txt")).read().split("\n")[0].split()
            check(abs(float(vals[0]) - 0.7) < 1e-6 and abs(float(vals[1]) - 0.3) < 1e-6 and len(vals) == 6, "a player change is written, the other copies kept: " + " ".join(vals))
            # 4 follow with no file: only the set value is stored, the rest -1
            d, o = run("follow", {})
            vals = open(os.path.join(d, "t2r-sens.txt")).read().split("\n")[0].split()
            check(abs(float(vals[0]) - 0.7) < 1e-6 and all(float(v) == -1.0 for v in vals[1:]), "no file: only the set value is stored, never a -1 'value': " + " ".join(vals))
            # 5 garbage / short file
            d, o = run("restore", {"t2r-sens.txt": "0.25 0.3\n"})
            check("g0=-1.000 g1=-1.000" in o, "a short file is ignored: " + o.strip())
            d, o = run("restore", {"t2r-sens.txt": "nan inf -5 5000 abc 1\n"})
            check("g0=-1.000" in o and "g1=-1.000" in o, "garbage values are ignored: " + o.strip())
            # 5b a bulk write of the defaults after the start is not the player: the copy comes back, a slider move is followed
            d, o = run("bulk", {"t2r-sens.txt": "0.1 0.1 0.1 0.1 0.1 0.1\n"})
            check("g0=0.300 g5=0.350" in o and "g1=0.600" in o, "bulk default write reverted, later slider move followed: " + o.strip().replace("\n", " | "))
            vals = open(os.path.join(d, "t2r-sens.txt")).read().split("\n")[0].split()
            check(abs(float(vals[0]) - 0.3) < 1e-6 and abs(float(vals[1]) - 0.6) < 1e-6, "the file never took the defaults: " + " ".join(vals))
            check(os.path.exists(os.path.join(d, "t2r-sens.prev.txt")), "the replaced copy is kept as t2r-sens.prev.txt")
            d, o = run("defaults", {"t2r-sens.txt": "0.12 0.12 0.08 0.08 0.09 0.09\n"})
            check("g0=0.120 g5=0.090" in o, "first scan with all six at the default and another copy: copy wins: " + o.strip())
            d, o = run("defaults", {"t2r-sens.txt": "0.5 0.5 0.5 0.5 0.25 0.25\n"})
            check("g0=0.500 g5=0.250" in o, "defaults and a default copy: untouched: " + o.strip())
            d, o = run("defaults", {})
            check("g0=0.500 g5=0.250" in o, "defaults and no copy: adopted: " + o.strip())
            # 6 other exe build, flag
            d, o = run("badsig", {"t2r-sens.txt": "0.25 0.3 0.35 0.4 0.45 0.5\n"})
            check("g0=-1.000 state=2" in o and "miss:" in o, "other exe build: guard off, nothing written: " + o.strip())
            d, o = run("flag", {"t2r-sens.txt": "0.25 0.3 0.35 0.4 0.45 0.5\n", "t2r-no-sens-guard.txt": "x"})
            check("g0=-1.000 state=2" in o, "t2r-no-sens-guard.txt turns it off: " + o.strip())
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

# the real exe, when installed: loader and saver use the globals the guard watches
EXE = r"C:\Games\The Last of Us Part II Remastered\tlou-ii.exe"
try:
    import pefile
    import capstone
    have = os.path.exists(EXE)
except Exception:
    have = False
if not have:
    print("skip exe check: no game exe / pefile / capstone")
else:
    pe = pefile.PE(EXE, fast_load=True)
    base = pe.OPTIONAL_HEADER.ImageBase
    code = pe.get_data(0x121ce51, 8)
    check(code[:4] == b"\xc5\xfa\x11\x05" and 0x121ce51 + 8 + struct.unpack("<i", code[4:])[0] == 0x3768728, "exe: loader stores mouse-look-sensitivity-x into 0x3768728")
    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
    seen = set()
    for i in md.disasm(pe.get_data(0x1225000, 0x3000), base + 0x1225000):
        m = re.search(r"rip \+ (0x[0-9a-f]+)", i.op_str)
        if i.mnemonic == "vmovss" and m:
            seen.add(i.address + i.size + int(m.group(1), 16) - base)
    want = {0x3768728, 0x3768734, 0x3768724, 0x3768730, 0x376872c, 0x3768738}
    check(want <= seen, "exe: the profile saver reads all six globals")
    init = pe.get_data(0x3768724, 24)
    check(all(struct.unpack("<f", init[k:k + 4])[0] == -1.0 for k in range(0, 24, 4)), "exe: the six start at the -1 'never set' sentinel")

print("FAILED: %d" % len(FAILS) if FAILS else "all ok")
sys.exit(1 if FAILS else 0)
