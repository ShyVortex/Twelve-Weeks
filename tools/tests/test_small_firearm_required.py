"""A loadout always has a small firearm (NO SECONDARY is not an option: a secondary has to be picked).

Checks every place a loadout is made or read:
  - GEAR UP (tools/ext/gearup13.c): the SMALL FIREARM list has no NONE row; the LARGE FIREARM list keeps its NONE row.
  - the saved file (tools/ext/t2r-ext.c lo_load): a custom loadout without a small firearm gets the free 9mm (row 0, the same
    default as a new / RESET custom and the launcher's blank one), logged once per loadout, and the file is saved again.
  - the launcher file the game reads (tools/ext/loadjson.c): an empty small firearm is refused (allow_none 0).
  - the launcher itself (release/launcher): the small row has no "none" entry, a blank loadout holds the 9mm, and a wire
    loadout with small = null decodes to a gun (node, when it is installed).
  - the pre-made classes: each one has a small firearm, and the 9mm (row 0) costs 0 LP.
  - the daemon stores the login profile blob verbatim and never reads a loadout out of it, so it has no small firearm to check.

Run: python tools/tests/test_small_firearm_required.py   (plain python, no game files)."""
import json
import os
import re
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.dirname(HERE)
ROOT = os.path.dirname(TOOLS)
sys.path.insert(0, TOOLS)
import classes_src  # noqa: E402

FAILS = []


def check(cond, what):
    print(("ok   " if cond else "FAIL ") + what)
    if not cond:
        FAILS.append(what)


def read(*p):
    return open(os.path.join(ROOT, *p), encoding="utf-8", errors="replace").read()


def body(src, head):
    """The text of the C function that starts with `head` (up to its closing brace at column 0)."""
    i = src.index(head)
    j = src.index("\n}\n", i)
    return src[i:j]


gu = read("tools", "ext", "gearup13.c")
ext = read("tools", "ext", "t2r-ext.c")
lj = read("tools", "ext", "loadjson.c")

# ---- GEAR UP option list
opts = body(gu, "static void gu_build_opts(int s)")
check(re.search(r"if \(s != GS_SMALL\) gu_add\(GO_NONE", opts) is not None, "GEAR UP: the NONE row is added for every slot except SMALL FIREARM")
check(len(re.findall(r"gu_add\(GO_NONE", opts)) == 1, "GEAR UP: one NONE row at most (LARGE FIREARM, purchasable and skills keep theirs)")

# ---- saved custom loadouts
fix = body(ext, "static int lo_fix_small(loadout_t *l, int idx)")
check("l->w[1] = 0;" in fix and "revolver" not in fix, "lo_fix_small gives the 9mm (row 0), the default of a new / RESET custom")
check("{{0xffffffffu, 0, 0xffffffffu}" in body(ext, "static void lo_load(void)"), "a new custom (lo_load default) holds the 9mm (row 0)")
reset = body(gu, "static void gu_reset(void)")
check("d.w[1] = 0;" in reset, "RESET LOADOUT holds the 9mm (row 0)")
check("l->w[1] != 0xffffffffu) return 0" in fix, "lo_fix_small only touches a loadout without a small firearm")
check("logged >> idx & 1" in fix and "xlog(" in fix, "lo_fix_small logs once per loadout")
load = body(ext, "static void lo_load(void)")
a, b = load.find("lo_fix_small(&l, i)"), load.find("if (lo_valid(&l)) g_lo[i] = l;")
check(0 <= a < b, "lo_load fixes the small firearm before lo_valid takes the loadout")
check("if (fixed_small) lo_save();" in load, "lo_load saves the file after a fix")

# ---- the launcher file the game reads
check(re.search(r'lj_pick_w\(1, lj_get\(n, "small"\), 0,', lj) is not None, "loadjson.c: an empty small firearm from the launcher is refused")
pick = body(lj, "static int lj_pick_w(")
check("if (!allow_none)" in pick, "loadjson.c: lj_pick_w keeps the slot when none is not allowed")

# ---- classes
classes = classes_src.parse()
check(len(classes) == 8, "8 pre-made classes")
for c in classes:
    check(bool(c["w"][1]), "class %s has a small firearm (%s)" % (c["name"], c["w"][1]))

# ---- launcher
model = read("release", "launcher", "src", "loadout-model.js")
check(re.search(r"\{ k: 'small', t: 'SMALL FIREARM', none: null \}", model) is not None, "launcher: the SMALL FIREARM row has no none entry")
gd = read("release", "launcher", "src", "gamedata.js")
G = json.loads(gd[gd.index("= ") + 2: gd.rindex(";")])
small = {w["id"]: w for w in G["weapons"]["small"]}
check(G["weapons"]["small"][0]["id"] == "pistol-beretta" and G["weapons"]["small"][0]["lp"] == 0, "small firearm row 0 is the free 9mm (pistol-beretta)")
node = shutil.which("node")
if node:
    js = r"""
const fs = require('fs'), path = require('path');
const L = path.join(process.argv[1], 'release', 'launcher');
const lof = require(path.join(L, 'lib', 'loadoutfile'));
const G = new Function(fs.readFileSync(path.join(L, 'src', 'gamedata.js'), 'utf8') + '\nreturn GAMEDATA;')();
const r = lof.fromWire(G, { format: 1, rev: 1, active: { kind: 'custom', i: 0 },
  custom: [{ small: null, large: null, purch: null, skills: [] }, { small: { id: 'no-such-gun' }, large: null, purch: null, skills: [] }] });
console.log(JSON.stringify({ blank: lof.blank(G).small, a: r.state.custom[0].small, b: r.state.custom[1].small }));
"""
    out = subprocess.run([node, "-e", js, ROOT], capture_output=True, text=True)
    try:
        res = json.loads(out.stdout.strip().splitlines()[-1])
    except Exception:
        res = None
        print(out.stdout, out.stderr)
    check(res is not None, "launcher: fromWire ran under node")
    if res:
        check(bool(res["blank"]) and res["blank"]["id"] in small, "launcher: a blank loadout holds a small firearm")
        check(bool(res["a"]) and res["a"]["id"] in small, "launcher: small = null decodes to a small firearm")
        check(bool(res["b"]) and res["b"]["id"] in small, "launcher: an unknown small firearm decodes to a small firearm")
else:
    print("skip launcher fromWire (no node)")

# ---- daemon
dm = read("tools", "daemon.py")
save = dm[dm.index("def save_loadout(token, blob):"):]
save = save[:save.index("\ndef ")]
check("blob" in save and not re.search(r"blob\[\d", save), "daemon: save_loadout stores the profile blob verbatim (no loadout fields read)")
check(re.search(r"\bsmall\b|secondary|sidearm", save) is None, "daemon: no small firearm field on the server to check")

print("all ok" if not FAILS else "FAILED: %d" % len(FAILS))
sys.exit(1 if FAILS else 0)
