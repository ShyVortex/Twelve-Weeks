"""Offline test of the launcher <-> game loadout files (tools/ext/loadjson.c, release/launcher/lib/loadoutfile.js, API.md "Loadout files").
Checks: the skill keys of the ext match skills.h and the launcher data; every launcher weapon id is a weapon id of the mod; the ext's JSON reader
(compiled from loadjson.c itself) reads a file written by the launcher library exactly as written, and refuses broken files.
Run: python tools/tests/test_loadjson.py   (plain python + node + gcc if found; scratch folder only, no game files)."""
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import sys as _t2s, os as _t2o; _t2s.path.append(_t2o.path.normpath(_t2o.path.join(_t2o.path.dirname(_t2o.path.abspath(__file__)), ".."))); import t2rtmp  # noqa: E402,F401  (temp hygiene: tools/t2rtmp.py)

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
FAILS = []
def check(cond, what):
    print(("ok   " if cond else "FAIL ") + what)
    if not cond:
        FAILS.append(what)
def read(*p):
    return open(os.path.join(ROOT, *p), encoding="utf-8", errors="replace", newline="").read()

ljc = read("tools", "ext", "loadjson.c")
skh = read("tools", "ext", "skills.h")
ext = read("tools", "ext", "t2r-ext.c")
gd = read("release", "launcher", "src", "gamedata.js")
G = json.loads(gd[gd.index("= ") + 2: gd.rindex(";")])

# ---- skill keys: LJ_SK[] (ext) = the SK_ enum (skills.h) = the launcher's G.skills keys
enum = re.search(r"enum \{\s*SK_NONE,(.*?)SK_COUNT", skh, re.S).group(1)
enum_keys = re.findall(r"SK_[A-Z]+", re.sub(r"//[^\n]*", "", enum))
lj_keys = re.findall(r"LJ_K\((SK_[A-Z]+)\)", ljc)
check(lj_keys == enum_keys, "loadjson.c LJ_SK[] lists every SK_ key of skills.h in order (%d)" % len(enum_keys))
check([s["key"] for s in G["skills"]] == enum_keys, "launcher gamedata skills = skills.h enum (same keys, same order)")

# ---- weapon ids
ids = [w["id"] for ws in G["weapons"].values() for w in ws]
missing = [i for i in ids if '"%s"' % i not in ext]
check(not missing, "every launcher weapon id is a weapon id in t2r-ext.c (%d ids)%s" % (len(ids), " missing: %s" % missing if missing else ""))

# ---- wiring in t2r-ext.c
check('#include "loadjson.c"' in ext and "lj_tick(0)" in ext and "lj_tick(1)" in ext, "t2r-ext.c includes loadjson.c and ticks it from feature_loadout_persist")
check("lo_write_obj(lo_of(g_lo_active));" in ljc and "lo_save();" in ljc and "sk4_save();" in ljc, "an applied launcher file takes the in-game save path (t2r-loadout.txt, t2r-skills.txt, lobby object)")
check("lj_gate_open" in ljc and "g_lo_state != LO_NONE) return 0" in ljc and "g_lo_pending = g_lo_active + 1" in ljc, "a launcher file waits while a loadout page is open; mid-match it becomes the pending pick for the next spawn")

# ---- the reader, compiled from loadjson.c's own text
gcc = shutil.which("gcc")
if not gcc:
    for c in (os.path.join(ROOT, "tools", "win", "ext", "msys64", "ucrt64", "bin", "gcc.exe"), r".\tools\win\ext\msys64\ucrt64\bin\gcc.exe"):
        if os.path.exists(c):
            gcc = c
            break
node = shutil.which("node")
if not gcc or not node:
    print("skip the compiled reader test (gcc / node not found)")
else:
    region = ljc[ljc.index("// ---- a tiny JSON reader"): ljc.index("// ---- paths, files")]
    harness = ("#include <stdio.h>\n#include <string.h>\n#include <stdlib.h>\n" + region + r"""
static void sel(const lj_n *n) {
    if (!n || n->t == 'z') { printf("-"); return; }
    const lj_n *i = lj_get(n, "id"), *s = lj_get(n, "supp"), *l = lj_get(n, "lv");
    printf("%s", i ? i->s : "?");
    if (s) printf(":s%d", (int)s->num);
    if (l) printf(":l%d", (int)l->num);
}
int main(int argc, char **argv) {
    static char buf[65536];
    FILE *f = fopen(argv[1], "rb");
    size_t n = f ? fread(buf, 1, sizeof buf - 1, f) : 0;
    buf[n] = 0;
    lj_n *r = lj_parse(buf);
    if (!r) { puts("ERR"); return 0; }
    const lj_n *rv = lj_get(r, "rev"), *ac = lj_get(r, "active"), *cu = lj_get(r, "custom");
    printf("rev %lld active %s %d\n", rv ? (long long)rv->num : -1, lj_get(ac, "kind")->s, (int)lj_get(ac, "i")->num);
    for (int i = 0; i < 6; i++) {
        const lj_n *c = lj_idx(cu, i);
        printf("c%d ", i); sel(lj_get(c, "small")); printf(" "); sel(lj_get(c, "large")); printf(" "); sel(lj_get(c, "purch"));
        for (int j = 0; j < 4; j++) { printf(" "); sel(lj_idx(lj_get(c, "skills"), j)); }
        printf(" lp%d\n", (int)lj_get(c, "lp")->num);
    }
    return 0;
}
""")
    tmp = tempfile.mkdtemp(prefix="lj-test-")
    try:
        hc, exe = os.path.join(tmp, "h.c"), os.path.join(tmp, "h.exe")
        open(hc, "w").write(harness)
        env = dict(os.environ, PATH=os.path.dirname(gcc) + os.pathsep + os.environ["PATH"])
        rc = subprocess.run([gcc, "-std=gnu2x", "-O1", "-Wall", "-Werror", "-o", exe, hc], env=env, capture_output=True, text=True)
        check(rc.returncode == 0, "the JSON reader of loadjson.c compiles standalone, no warnings" + (rc.stderr[:300] if rc.returncode else ""))
        if rc.returncode == 0:
            js = (
                "const lof=require(%s);const G=new Function(require('fs').readFileSync(%s,'utf8')+'\\nreturn GAMEDATA;')();"
                "const sk=(k,l)=>({id:G.skills.findIndex(s=>s.key===k),lv:l});const st={v:2,active:{kind:'class',i:3},custom:Array.from({length:6},()=>lof.blank(G))};"
                "st.custom[0]={small:{id:'pistol-beretta',supp:1},large:{id:'rifle-mpx5',supp:1},purch:{id:'shotgun-baserri-over-under',supp:0},skills:[sk('SK_REVIVER',2),sk('SK_COVERT',1),null,sk('SK_FORT',1)]};"
                "st.custom[3]={small:{id:'shotgun-shorty',supp:0},large:{id:'bow-ellie',supp:0},purch:null,skills:[null,sk('SK_LETHAL',2),null,null]};"
                "process.stdout.write(JSON.stringify(lof.toWire(G,st,1760000000123)));"
            ) % (json.dumps(os.path.join(ROOT, "release", "launcher", "lib", "loadoutfile.js")), json.dumps(os.path.join(ROOT, "release", "launcher", "src", "gamedata.js")))
            wire = subprocess.run([node, "-e", js], capture_output=True, text=True, check=True).stdout
            wf = os.path.join(tmp, "launcher.json")
            for name, text, expect_err in (("pretty", json.dumps(json.loads(wire), indent=1), False), ("compact", wire, False),
                                           ("truncated", wire[: len(wire) // 2], True), ("empty", "", True), ("garbage", "[1,2", True), ("not an object", "[1]", True)):
                open(wf, "w", newline="").write(text)
                out = subprocess.run([exe, wf], capture_output=True, text=True).stdout.splitlines()
                if expect_err:
                    check(out == ["ERR"], "reader refuses a %s file" % name)
                    continue
                w = json.loads(text)
                def fmt(s):
                    return "-" if not s else s["id"] + (":s%d" % s["supp"] if "supp" in s else "") + (":l%d" % s["lv"] if "lv" in s else "")
                want = ["rev %d active %s %d" % (w["rev"], w["active"]["kind"], w["active"]["i"])]
                for i, c in enumerate(w["custom"]):
                    want.append("c%d %s %s %s %s lp%d" % (i, fmt(c["small"]), fmt(c["large"]), fmt(c["purch"]), " ".join(fmt(s) for s in c["skills"]), c["lp"]))
                check(out == want, "the ext reader reads the launcher's %s file exactly (rev, active, 6 loadouts, skills)" % name)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

print("\n%d failure(s)" % len(FAILS))
sys.exit(1 if FAILS else 0)
