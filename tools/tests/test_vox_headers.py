"""Generated voice headers: ext/vox_lines*.h, vox_words.h and vox_avail.h must match tools/features/data/vox_lines*.json (vox_avail.h was
once stale, 635/625 entries for 649/645 lines, so t2r-ext read past the table in Polish).
Run: python tools/tests/test_vox_headers.py   (plain python, no game needed; vox_avail.h is only length-checked: regenerating it needs the
game's speech archives, `python tools/features/vox_lines.py genavail`)."""
import json, os, re, sys, tempfile
import sys as _t2s, os as _t2o; _t2s.path.append(_t2o.path.normpath(_t2o.path.join(_t2o.path.dirname(_t2o.path.abspath(__file__)), ".."))); import t2rtmp  # noqa: E402,F401  (temp hygiene: tools/t2rtmp.py)

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(TOOLS, "features"))
import vox_lines as V  # noqa: E402

FAILS = []
def check(cond, what):
    print(("ok   " if cond else "FAIL ") + what)
    if not cond:
        FAILS.append(what)

def read(p): return open(p, encoding="utf-8").read()
EXT = os.path.join(TOOLS, "ext")
male = V.load()
fem = json.load(open(V.FDATA))
with tempfile.TemporaryDirectory() as td:
    V.HEADER = os.path.join(td, "m.h"); V.FHEADER = os.path.join(td, "f.h")
    V.write_header(male)
    check(read(V.HEADER) == read(os.path.join(EXT, "vox_lines.h")), "vox_lines.h = data/vox_lines.json")
    V.write_female_header(fem["lines"], fem["effort"])
    check(read(V.FHEADER) == read(os.path.join(EXT, "vox_lines_female.h")), "vox_lines_female.h = data/vox_lines_female.json")
avail = read(os.path.join(EXT, "vox_avail.h"))
want = {"M": len(male), "F": len(fem["lines"]), "E": len(fem["effort"])}
for m in re.finditer(r"VXA_(\w+)_([MFE])\[\] = \{([^}]*)\}", avail):
    n = len([x for x in m.group(3).split(",") if x.strip()])
    check(n == want[m.group(2)], "vox_avail.h %s_%s has %d entries, the table has %d" % (m.group(1), m.group(2), n, want[m.group(2)]))
words = read(os.path.join(EXT, "vox_words.h"))
for nm, n in (("VX_WORD", len(male)), ("VXF_WORD", len(fem["lines"]))):
    m = re.search(r"%s\[\] = \{([^}]*)\}" % nm, words)
    check(bool(m) and len(m.group(1).split(",")) == n, "vox_words.h %s has %d entries" % (nm, n))
print("FAILED: %d" % len(FAILS) if FAILS else "all passed")
sys.exit(1 if FAILS else 0)
