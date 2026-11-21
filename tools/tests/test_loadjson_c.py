"""Offline test of the SERIALISED launcher <-> game loadout files (tools/ext/loadjson.c compiled with engine stubs: tools/ext/tests/loadjson_test.c).
test_loadjson.py checks the READER against a launcher-written file; this one checks what the game WRITES (t2r-loadout.json, the lj_body bug:
the file was cut after '"custom":[' and the launcher saw no loadouts) and what it does with hostile launcher files:
  * export: 0 / 1 / 6 populated loadouts, long / Polish / quote-backslash-control-char ids -> valid JSON (json.loads), every field round-trips,
    an id that cannot be quoted safely becomes null, an oversize body writes nothing (and leaves the old file alone), the size boundary stays valid
  * the launcher's own reader (release/launcher/lib/loadoutfile.js readGame, run in node) gets every loadout out of the game's file
  * import: a launcher-written file is applied row for row; an older cut t2r-loadout.json still yields its launcher_rev
  * fuzz: garbled / truncated / oversized / deeply nested launcher files never fault (guard page behind the buffer), never apply an invalid loadout
  * mutation: the pre-fix lj_body (sizeof on a pointer) makes the export test fail, so the test would have caught it
Run: python tools/tests/test_loadjson_c.py   (plain python + gcc + node; scratch folder only, no game files)."""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import sys as _t2s, os as _t2o; _t2s.path.append(_t2o.path.normpath(_t2o.path.join(_t2o.path.dirname(_t2o.path.abspath(__file__)), ".."))); import t2rtmp  # noqa: E402,F401  (temp hygiene: tools/t2rtmp.py)

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
EXT = os.path.join(ROOT, "tools", "ext")
FAILS = []


def check(cond, what):
    print(("ok   " if cond else "FAIL ") + what)
    if not cond:
        FAILS.append(what)


gcc = shutil.which("gcc")
if not gcc:
    for c in (os.path.join(ROOT, "tools", "win", "ext", "msys64", "ucrt64", "bin", "gcc.exe"), r".\tools\win\ext\msys64\ucrt64\bin\gcc.exe"):
        if os.path.exists(c):
            gcc = c
            break
node = shutil.which("node")
if not gcc or not node or os.name != "nt":
    print("skip: gcc / node not found (or not Windows: the harness includes windows.h)")
    sys.exit(0)
ENV = dict(os.environ, PATH=os.path.dirname(gcc) + os.pathsep + os.environ["PATH"])
tmp = tempfile.mkdtemp(prefix="lj-c-test-")


def build(src_dir, exe):
    r = subprocess.run([gcc, "-std=gnu2x", "-O1", "-Wall", "-Wno-unused-function", "-Wno-unused-variable", "-o", exe, os.path.join(src_dir, "loadjson_test.c")], env=ENV, capture_output=True, text=True)
    return r


def run(exe, *args, timeout=300):
    return subprocess.run([exe, *args], env=ENV, capture_output=True, text=True, timeout=timeout)


def js(code):
    return subprocess.run([node, "-e", code], capture_output=True, text=True, check=True).stdout


GD = os.path.join(ROOT, "release", "launcher", "src", "gamedata.js")
LOF = os.path.join(ROOT, "release", "launcher", "lib", "loadoutfile.js")
G = json.loads(js("process.stdout.write(JSON.stringify(new Function(require('fs').readFileSync(%s,'utf8')+'\\nreturn GAMEDATA;')()))" % json.dumps(GD)))
SLOT = {0: "large", 1: "small", 2: "purch"}      # engine slot -> launcher slot
NP = 6


def write_tables(path, ids):                       # ids: {engine slot: [id, ...]}
    with open(path, "wb") as f:
        for s, lst in ids.items():
            for i in lst:
                f.write(b"%d " % s + i.encode("utf-8") + b"\n")


def expected(ids, np_, active_kind="custom", active_i=1):
    """What loadjson_test.c builds (see its export mode) as the wire form lj_body must produce."""
    out = []
    keys = [k["key"] for k in G["skills"]]
    for i in range(NP):
        c = {"small": None, "large": None, "purch": None, "skills": [None] * 4}
        if i < np_:
            def sel(slot, idx):
                lst = ids[slot]
                if not lst:
                    return None
                v = lst[idx % len(lst)]
                if any(ch in v for ch in '"\\') or any(ord(ch) < 0x20 for ch in v):
                    return None
                supp = v.endswith("-supp")
                return {"id": v[:-5] if supp else v, "supp": 1 if supp else 0}
            c["small"] = sel(1, i)
            c["large"] = sel(0, i * 5 + 1)
            c["purch"] = sel(2, i * 7 + 2) if i % 3 != 2 else None
            for j in range(4):
                c["skills"][j] = {"id": keys[(i * 4 + j) % 26], "lv": 1 + (i + j) % 2 if j < 3 else 1 + i % 2}
        out.append(c)
    return out


def export(exe, name, ids, np_, kind="custom", ai=1, expect_file=True):
    d = os.path.join(tmp, name)
    os.makedirs(d, exist_ok=True)
    tf = os.path.join(d, "tables.txt")
    write_tables(tf, ids)
    r = run(exe, "export", d, kind, str(ai), str(np_), tf)
    p = os.path.join(d, "t2r-loadout.json")
    return d, r, p


def strip_lp(custom):
    return [{k: v for k, v in c.items() if k != "lp"} for c in custom]


# ---------------------------------------------------------------- build
exe = os.path.join(tmp, "lj.exe")
r = build(os.path.join(EXT, "tests"), exe)
check(r.returncode == 0, "loadjson.c compiles with the engine stubs, no warnings" + ("\n" + r.stderr[:600] if r.returncode else ""))
if r.returncode:
    shutil.rmtree(tmp, ignore_errors=True)
    sys.exit(1)

real = {0: [w["id"] for w in G["weapons"]["large"]], 1: [w["id"] for w in G["weapons"]["small"]], 2: [w["id"] for w in G["weapons"]["purch"]]}
# supp rows exist in the engine tables as "<id>-supp": add one for every suppressible small/large gun
for slot, lname in ((0, "large"), (1, "small")):
    real[slot] = real[slot] + [w["id"] + "-supp" for w in G["weapons"][lname] if w.get("supIcon")]

# ---------------------------------------------------------------- export: valid JSON, all fields, 0 / 1 / 6 loadouts
for np_ in (0, 1, 6):
    for kind, ai in (("custom", 0), ("custom", 5), ("class", 3)):
        d, r, p = export(exe, "real-%d-%s%d" % (np_, kind, ai), real, np_, kind, ai)
        try:
            txt = open(p, "rb").read().decode("utf-8")
            w = json.loads(txt)
        except Exception as e:
            check(False, "export %d populated, active %s %d: valid JSON (%s)" % (np_, kind, ai, e))
            continue
        ok = (w.get("format") == 1 and isinstance(w.get("rev"), int) and w.get("launcher_rev") == 1234567890123 and w["active"] == {"kind": kind, "i": ai}
              and len(w["custom"]) == 6 and strip_lp(w["custom"]) == expected(real, np_) and txt.endswith("}\n"))
        check(ok, "export %d populated loadouts, active %s %d: valid JSON, header + 6 customs + every field round-trips" % (np_, kind, ai))
        if not ok:
            print(json.dumps(w["custom"][:1])[:300], json.dumps(expected(real, np_)[:1])[:300])

# ---------------------------------------------------------------- long / Polish / quote / backslash / control-char ids
nasty = {
    1: ["pistol-" + "x" * 150, "pistol-zażółć-gęślą-jaźń", "pi\"stol", "pi\\stol", "pistol\x07bell", "pistol-beretta-supp", "pistol-ąęść-supp"],
    0: ["rifle-" + "y" * 200, "strzelba-Żółć-ŁÓDŹ", "ri\\\"fle", "rifle-ok", "karabin-日本語-supp", "rifle-" + "z" * 120 + "-supp"],
    2: ["shotgun-\u0142\u00f3d\u017a", "shot\"gun", "shot\\gun\\", "shotgun-" + "w" * 180, "x"],
}
for np_ in (0, 1, 6):
    d, r, p = export(exe, "nasty-%d" % np_, nasty, np_)
    try:
        txt = open(p, "rb").read().decode("utf-8")
        w = json.loads(txt)
        ok = strip_lp(w["custom"]) == expected(nasty, np_) and len(w["custom"]) == 6
    except Exception as e:
        ok = False
        print("   ", e)
    check(ok, "export %d populated with long / Polish / quote / backslash / control-char ids: valid JSON, safe ids verbatim, unsafe ids null" % np_)
    if np_ == 6 and ok:
        used = [c[s]["id"] for c in w["custom"] for s in ("small", "large", "purch") if c[s]]
        check(any(not u.isascii() for u in used) and any(len(u) > 100 for u in used), "  ... and the Polish / non-ASCII and the 100+ character ids were really exercised (%d ids)" % len(used))

# ---------------------------------------------------------------- size limits: the boundary stays valid JSON, over it nothing is written and the old file stays
def body_ok(n):
    ids = {0: ["r" * n], 1: ["p" * n], 2: ["s" * n]}
    d, r, p = export(exe, "size-%d" % n, ids, 6)
    return os.path.exists(p) and os.path.getsize(p) > 0, p, ids
lo, hi = 10, 700
while lo < hi - 1:
    mid = (lo + hi) // 2
    if body_ok(mid)[0]:
        lo = mid
    else:
        hi = mid
okb, p, ids = body_ok(lo)
w = json.loads(open(p, "rb").read().decode("utf-8"))
check(okb and strip_lp(w["custom"]) == expected(ids, 6) and 100 < lo < 700, "largest id length still exported (%d chars x 18 ids): valid JSON, %d bytes" % (lo, os.path.getsize(p)))
d, r, p2 = export(exe, "size-over-seed", {0: ["a"], 1: ["b"], 2: ["c"]}, 1)
seed_bytes = open(p2, "rb").read()
tf = os.path.join(d, "tables2.txt")
write_tables(tf, {0: ["r" * hi], 1: ["p" * hi], 2: ["s" * hi]})
r2 = run(exe, "export", d, "custom", "0", "6", tf)
check(r2.returncode == 0 and open(p2, "rb").read() == seed_bytes, "an oversize body (ids %d chars) writes nothing and leaves the previous file untouched" % hi)

# ---------------------------------------------------------------- the launcher's own reader gets every loadout out of the game's file
for np_ in (0, 1, 6):
    d, r, p = export(exe, "launcher-%d" % np_, real, np_, "custom", 2)
    out = js("const lof=require(%s);const G=new Function(require('fs').readFileSync(%s,'utf8')+'\\nreturn GAMEDATA;')();"
             "process.stdout.write(JSON.stringify(lof.readGame(G,%s)))" % (json.dumps(LOF), json.dumps(GD), json.dumps(d)))
    g = json.loads(out)
    w = json.loads(open(p, "rb").read().decode("utf-8"))
    ex = expected(real, np_)
    # launcher state -> wire (same helper the launcher uses to save) and compare to the file
    wire = json.loads(js("const lof=require(%s);const G=new Function(require('fs').readFileSync(%s,'utf8')+'\\nreturn GAMEDATA;')();"
                         "const st=JSON.parse(process.argv[1]);process.stdout.write(JSON.stringify(lof.toWire(G,st,0)))" % (json.dumps(LOF), json.dumps(GD)) if False else
                         "const lof=require(%s);const G=new Function(require('fs').readFileSync(%s,'utf8')+'\\nreturn GAMEDATA;')();"
                         "const r=lof.readGame(G,%s);process.stdout.write(JSON.stringify(lof.toWire(G,r.state,0)))" % (json.dumps(LOF), json.dumps(GD), json.dumps(d))))
    got = strip_lp(wire["custom"])
    # the launcher turns a null small gun into the free 9mm (it always has a sidearm); everything else must be identical
    want = [dict(c, small=c["small"] or {"id": G["weapons"]["small"][0]["id"], "supp": 0}) for c in ex]
    check(g.get("found") is True and g.get("rev") == w["rev"] and g.get("launcherRev") == 1234567890123 and got == want and g["state"]["active"] == {"kind": "custom", "i": 2},
          "launcher readGame on the game's file (%d populated): found, rev + launcher_rev, active, and all 6 customs equal" % np_)
    check(not [x for x in g.get("problems", []) if "unknown" in x or "missing" in x], "  ... with no launcher complaints about it (%s)" % g.get("problems"))

# ---------------------------------------------------------------- a cut file: the launcher sees nothing (and says so), the game keeps launcher_rev
cut_dir = os.path.join(tmp, "cut"); os.makedirs(cut_dir, exist_ok=True)
full = open(export(exe, "cut-src", real, 6)[2], "rb").read().decode()
cut = full[: full.index('"custom":[') + len('"custom":[')]
open(os.path.join(cut_dir, "t2r-loadout.json"), "w", newline="").write(cut)
out = json.loads(js("const lof=require(%s);const G=new Function(require('fs').readFileSync(%s,'utf8')+'\\nreturn GAMEDATA;')();"
                    "process.stdout.write(JSON.stringify(lof.readGame(G,%s)))" % (json.dumps(LOF), json.dumps(GD), json.dumps(cut_dir))))
check(out.get("found") is False and out.get("error") == "unreadable", "launcher readGame on the PT80 cut file: not found, error 'unreadable' (what PT80 players got)")
r = run(exe, "state", cut_dir)
check(r.stdout.strip() == "1234567890123", "the game recovers launcher_rev from the PT80 cut file (got %s)" % r.stdout.strip())
d2 = os.path.join(tmp, "empty"); os.makedirs(d2, exist_ok=True)
check(run(exe, "state", d2).stdout.strip() == "0", "no t2r-loadout.json: launcher_rev 0")
open(os.path.join(d2, "t2r-loadout.json"), "w").write('{"format":1,"rev":5,"launcher_rev":77,"active":{"kind":"custom","i":0},"custom":[]}\n')
check(run(exe, "state", d2).stdout.strip() == "77", "a whole file: launcher_rev read as before")

# ---------------------------------------------------------------- import: the launcher's file applied row for row
imp = os.path.join(tmp, "imp"); os.makedirs(imp, exist_ok=True)
wirejs = ("const lof=require(%s);const G=new Function(require('fs').readFileSync(%s,'utf8')+'\\nreturn GAMEDATA;')();"
          "const sk=(k,l)=>({id:G.skills.findIndex(s=>s.key===k),lv:l});const st={v:2,active:{kind:'custom',i:2},custom:Array.from({length:6},()=>lof.blank(G))};"
          "st.custom[0]={small:{id:'pistol-beretta',supp:1},large:{id:'rifle-mpx5',supp:0},purch:{id:'shotgun-shorty',supp:0},skills:[sk('SK_REVIVER',2),sk('SK_COVERT',1),null,sk('SK_FORT',1)]};"
          "st.custom[3]={small:{id:'pistol-beretta',supp:0},large:{id:'bow-ellie',supp:0},purch:null,skills:[null,sk('SK_LETHAL',2),null,null]};"
          "process.stdout.write(JSON.stringify(lof.toWire(G,st,1760000000123),null,1))") % (json.dumps(LOF), json.dumps(GD))
wire = js(wirejs)
wf = os.path.join(imp, "wire.json"); open(wf, "w").write(wire)
r = run(exe, "import", imp, wf)
lines = r.stdout.splitlines()
SKV = lambda i, lv: "%x" % (0x4000000000000000 | (i << 40) | (lv << 36))
kidx = {k["key"]: n + 1 for n, k in enumerate(G["skills"])}
c0 = "c0 1 0 0 %s %s 0 %s" % (SKV(kidx["SK_REVIVER"], 2), SKV(kidx["SK_COVERT"], 1), SKV(kidx["SK_FORT"], 1))
c3 = "c3 0 2 -1 0 %s 0 0" % (SKV(kidx["SK_LETHAL"], 2))
check(lines[:2] == ["applied 1", "active 2"] and lines[2] == c0 and lines[5] == c3, "import: the launcher's file applied row for row (guns by id, supp row, 4 skills, active pick)" + ("" if lines[:2] == ["applied 1", "active 2"] and lines[2] == c0 and lines[5] == c3 else "\n%s\n%s %s" % (r.stdout, c0, c3)))

# ---------------------------------------------------------------- fuzz: hostile / garbled / oversized launcher files
for rngseed in (1, 2, 3):
    r = run(exe, "fuzz", imp, wf, "1500", str(rngseed))
    check(r.returncode == 0 and "fuzz ok" in r.stdout, "fuzz seed %d: 1500 hostile launcher files, no fault, no invalid loadout applied (%s)" % (rngseed, (r.stdout.strip() or "rc %d" % r.returncode)[:120]))

# ---------------------------------------------------------------- mutation: the pre-fix LJ_LEFT (sizeof of a pointer) must make this test fail
mut = os.path.join(tmp, "mut"); os.makedirs(os.path.join(mut, "tests"), exist_ok=True)
for f in os.listdir(EXT):
    if f.endswith((".h", ".c")) and os.path.isfile(os.path.join(EXT, f)) and f != "t2r-ext.c":
        shutil.copy(os.path.join(EXT, f), os.path.join(mut, f))
shutil.copy(os.path.join(EXT, "tests", "loadjson_test.c"), os.path.join(mut, "tests", "loadjson_test.c"))
lj = open(os.path.join(mut, "loadjson.c"), "rb").read().decode()
old = "#define LJ_LEFT(o) ((size_t)(o) < n ? n - (size_t)(o) : (size_t)0)"
check(old in lj, "mutation: LJ_LEFT found in loadjson.c")
open(os.path.join(mut, "loadjson.c"), "wb").write(lj.replace(old, "#define LJ_LEFT(o) ((size_t)(o) < sizeof(b) ? sizeof(b) - (size_t)(o) : (size_t)0)").encode())
mexe = os.path.join(mut, "lj.exe")
if build(os.path.join(mut, "tests"), mexe).returncode == 0:
    d, r, p = export(mexe, "mutant", real, 6)
    try:
        json.loads(open(p, "rb").read().decode("utf-8"))
        broke = False
    except Exception:
        broke = True
    check(broke, "mutation: with the pre-fix lj_body the exported file is NOT valid JSON (this test would have caught the PT80 bug)")
else:
    check(False, "mutation: the mutant compiles")

shutil.rmtree(tmp, ignore_errors=True)
print("\n%d failure(s)" % len(FAILS))
sys.exit(1 if FAILS else 0)
