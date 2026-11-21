"""p1_lighting_multi.ext_define: generated text compiles (gcc -std=gnu2x -fsyntax-only, as immersion.c includes it) and the table matches the headers.
Run: python tools/tests/test_p1_lighting_multi.py"""
import os, re, subprocess, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "part1"))
import p1_lighting_multi as M

EXT = os.path.join(HERE, "..", "ext")
GCC = os.path.join(HERE, "..", "win", "ext", "msys64", "ucrt64", "bin", "gcc.exe")
BOOK = ("p1-bookstore", None, "*hun-rs-hun-checkpoint-bookstore-base*")
PLAZA = ("p1-plaza", "p1_lighting_p1-plaza.h", "*hun-rs-hun-financial-plaza-base*")


def nreg(hdr):
    return int(re.search(r"#define P1L_NREG (\d+)", open(os.path.join(EXT, hdr or "p1_lighting.h"), encoding="utf-8").read()).group(1))


def compile_check(text, maps):
    n = len(maps)
    tu = text + """
#include <string.h>
#define CHK(c) typedef char chk_##__LINE__[(c) ? 1 : -1]
#ifdef P1M_N
_Static_assert(P1M_N == %d, "n");
_Static_assert(sizeof g_p1m / sizeof g_p1m[0] == P1M_N, "table");
%s
static const char *const lv[] = {P1M_LEVEL_ITEMS, 0};
static const char *const df[][3] = {P1M_DEF_ROWS {0, 0, 0}};
_Static_assert(sizeof lv / sizeof *lv == P1M_N + 1, "levels");
_Static_assert(sizeof df / sizeof *df == P1M_N + 1, "def rows");
static float env[P1L_NREG_MAX];
#endif
int main(void) { return 0; }
""" % (n, "\n".join("_Static_assert(P1M_NREG_%d == %d, \"nreg %d\");" % (i, nreg(m[1]), i) for i, m in enumerate(maps)))
    with tempfile.NamedTemporaryFile("w", suffix=".c", dir=EXT, delete=False) as f:
        f.write(tu)
    try:
        r = subprocess.run([GCC, "-std=gnu2x", "-fsyntax-only", "-Wall", "-Wno-unused-variable", "-Wno-unused-const-variable", "-I", EXT, f.name], cwd=EXT, capture_output=True, text=True,
                           env=dict(os.environ, PATH=os.path.dirname(GCC) + os.pathsep + os.environ["PATH"]))
    finally:
        os.unlink(f.name)
    assert r.returncode == 0, (r.returncode, r.stdout[:500], r.stderr[:2000])
    assert not re.search(r"warning|error", r.stderr), r.stderr[:2000]


def main():
    assert M.ext_define([]) == ""
    for maps in ([BOOK, PLAZA], [PLAZA], [BOOK], [PLAZA, BOOK]):
        t = M.ext_define(maps)
        assert "#define P1M_N %d" % len(maps) in t
        compile_check(t, maps)
        print("ok", [m[0] for m in maps])
    # rs_renames (p1_maps json): the map's header is included as a generated copy with its symbol names replaced, const_sym renamed
    import json
    rn = json.load(open(os.path.join(HERE, "..", "part1", "data", "p1_maps", "p1-plaza.json"), encoding="utf-8")).get("rs_renames") or {}
    if rn:
        maps = [BOOK, PLAZA + (rn,)]
        t = M.ext_define(maps)
        compile_check(t, maps)
        built = open(os.path.join(EXT, "p1_lighting_p1-plaza_built.h"), encoding="utf-8").read()
        src = open(os.path.join(EXT, PLAZA[1]), encoding="utf-8").read()
        for o, n in rn.items():
            assert ('"%s"' % o) not in built and src.count('"%s"' % o) == built.count('"%s"' % n), (o, n)
        assert 'g_p1m_const_1[] = "%s"' % rn["*t1-rs-hun-const-base*"] in t and 'g_p1m_const_0[] = "*t1-rs-hun-const-base*"' in t
        print("ok renamed", sorted(rn))
    # no-op text must still let a TU build (immersion.c falls back to the default header)
    compile_check("", [])
    print("ok []")


if __name__ == "__main__":
    main()
