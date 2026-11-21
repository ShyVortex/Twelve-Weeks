"""Offline test of the 2013 GEAR UP page (tools/features/gearup13_widgets.py <-> tools/ext/gearup13.c).
Every widget path the ext driver writes / hit-tests ("anim-group.<group>.<name>") must exist in the page JSON build_page produces (a path that does not
exist is silently skipped by ui_w == 0 in game: a dead label, an unclickable row), the row counts of the C side must match the page, and the
entry points that replaced picker-skill must be wired. Plain python, no game files: the Builder templates come from a stub main-menu.
Run: python tools/tests/test_gearup13.py"""
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.dirname(HERE)
ROOT = os.path.dirname(TOOLS)
sys.path.insert(0, TOOLS)
sys.path.insert(0, os.path.join(TOOLS, "features"))
import gearup13_widgets as gw  # noqa: E402

FAILS = []
def check(cond, what):
    print(("ok   " if cond else "FAIL ") + what)
    if not cond:
        FAILS.append(what)

def read(*p):
    return open(os.path.join(ROOT, *p), encoding="utf-8", errors="replace").read()

def stub_main():
    base = {"guid": 0, "parent": 0, "name": "", "visible": 1, "rotation": 0.0, "depth": 0.0, "color.a": 255, "animation": {"keyframes": {}}}
    names = ("gameTitle", "lobbyBg", "titleUnderline", "onlineDot", "lobbyPanel", "root", "anim-group")
    return {"version": 1, "items": [dict(base, name=n) for n in names]}

page = gw.build_page(stub_main())
items = page["items"]
by_guid = {i["guid"]: i for i in items}
def path_of(i):
    out = []
    while i and i["name"] not in ("root",):
        out.append(i["name"])
        i = by_guid.get(i["parent"])
    return ".".join(reversed(out))
PATHS = {path_of(i) for i in items}
check("anim-group.lst" in PATHS and "anim-group.ed" in PATHS and "anim-group.ed.dt" in PATHS, "page has the list / edit / detail groups")
check(len(PATHS) == len(items), "every widget path is unique (%d widgets)" % len(items))

c = read("tools", "ext", "gearup13.c")
ext = read("tools", "ext", "t2r-ext.c")

# ---- the paths the driver uses
lits = sorted(set(re.findall(r'"(anim-group\.[A-Za-z0-9_.%]+)"', c)))
check(len(lits) > 40, "the driver references %d widget path patterns" % len(lits))
# the old layout in the new style: LIST_W list rows (the custom window of LIST_VISC + the 8 classes), OPT_ROWS option rows, 4 stat bars, 2 suppressor boxes
NL, NO = gw.LIST_W, gw.OPT_ROWS
RANGES = {"lsRow": NL, "ls": NL, "lsName": NL, "lsTag": NL, "lsHit": NL, "lgIc": 3, "lgNm": 3, "lskIc": 4, "lskNm": 4,
          "sl": 7, "slB": 7, "slRuB": 7, "slRuT": 7, "slIc": 7, "slNm": 7, "slCo": 7, "slArrow": 7, "slHit": 7,
          "op": NO, "opNm": NO, "opCo": NO, "opIc": NO, "opEq": NO, "opHit": NO,
          "st": 4, "stN": 4, "stF": 4, "lvHd": 3, "lvTx": 3, "lvHit": 3,
          "pre": 96, "tg": 2, "tgNm": 2, "tgCo": 2, "tgEq": 2, "tgHit": 2}      # UNSUPPRESSED / SUPPRESSED toggle cards (tgB<k>.tg*<k>)
# patterns composed with %s: expand them over the name lists the driver builds them from (SUB for the option rows, PV / PV2 for the list panel leaves)
def names(arr):
    m = re.search(arr + r'\[\] = \{([^}]*)\}', c)
    return re.findall(r'"(\w+)"', m.group(1)) if m else []
SUB, PV = names("SUB"), names("PV") + names("PV2")
exp = []
for pat in lits:
    if "%s" in pat:
        lst = SUB if pat.startswith("anim-group.ed.op%d.") else PV if pat == "anim-group.lst.%s" else []
        check(len(lst) >= 5, "%s pattern %s expands over its name list (%d names)" % ("%s", pat, len(lst)))
        exp += [pat.replace("%s", s) for s in lst]
    else:
        exp.append(pat)
# %c runs over the two list rows (lsScC / lsScL)
lits = sorted({q for pat in exp for q in ([pat.replace("%c", ch) for ch in "CL"] if "%c" in pat else [pat])})
# a frame helper base (nr_section / nr_chip / nr_scroll_*: the driver names the base, the page holds <base>Bg / Tx / Rl / T / H ...)
def exists(q):
    return q in PATHS or any(x.startswith(q) and "." not in x[len(q):] for x in PATHS)
for pat in lits:
    n = pat.count("%d")
    if not n:
        check(exists(pat), "path exists: %s" % pat)
        continue
    parts = pat.split(".")
    ok = True
    # the index of each %d runs over its widget family (all the same i, except stF%d_%d = stat 0..3 x bar 0..9)
    stat = parts[-1].startswith("stF")
    for i in range(10 if not stat else 4):
        for j in (range(10) if stat else [None]):
            q = pat
            if stat:
                q = pat.replace("%d", str(i), 1).replace("%d", str(j), 1)
            else:
                fam = re.match(r"[A-Za-z]+", parts[-1] if "%d" in parts[-1] else parts[-2]).group(0)
                lim = RANGES.get(fam)
                if lim is None:
                    ok = False
                    print("   unknown family for", pat, fam)
                    continue
                if i >= lim:
                    continue
                q = pat.replace("%d", str(i))
            if not exists(q):
                ok = False
                print("   missing", q)
    check(ok, "every index of: %s" % pat)

# ---- counts shared by both sides
check(("#define GU_VISC %d" % gw.LIST_VISC) in c and gw.LIST_W == gw.LIST_VISC + gw.N_CLS and ("#define GU_N_ROWW (GU_VISC + %d)" % gw.N_CLS) in c,
      "%d custom rows on screen + %d class rows" % (gw.LIST_VISC, gw.N_CLS))
check(("#define GU_ROW_Y0 %.1ff" % gw.ROW_Y[0]) in c and ("#define GU_ROW_Y1 %.1ff" % (gw.ROW_Y[0] + gw.ROW_P * (gw.LIST_VISC - 1) + gw.ROW_H)) in c
      and ("#define GU_LSB_X %.1ff" % gw.LSB_X) in c and ("#define GU_LX1 %.1ff" % gw.LX1) in c, "custom window scroll bar / list column on both sides")
check(("%.1ff, \"CLASSES\"" % gw.SEC_Y[1]) in c and ("%.1ff, \"CUSTOM LOADOUTS\"" % gw.SEC_Y[0]) in c, "list section lines on both sides")
check(("#define GU_GNM_W %.1ff" % (gw.GX1 - gw.GX0 - gw.GTX - 40)) in c, "gear name box on both sides")
check(("nr_bar(\"anim-group.lst.lsLBF\", %.1ff, %.1ff, %.1ff" % (gw.LB_X0, gw.LB_X1, gw.LB_Y + 3)) in c, "the LP bar on both sides")
check("#define N_CUSTOM 6" in ext and len(re.findall(r'^    \{"[A-Z]+", "', ext, re.M)) >= 8, "6 custom loadouts + 8 classes")
check(gw.SLOTS == 7 and "#define GU_SLOTS 7" in c, "7 slots")
check(("#define GU_OPT_ROWS %d" % gw.OPT_ROWS) in c, "%d option rows on both sides" % gw.OPT_ROWS)
check(gw.LEVELS == 3, "three skill level lines")
check("nr_prompts(" in c and "nr_prompt_hover" in c, "boxed prompts through the shared frame (nr_prompts / nr_prompt_hover)")

# ---- wiring in t2r-ext.c
check("#include \"gearup13.c\"" in ext and ext.index('#include "gearup13.c"') > ext.index('#include "skills.c"') and ext.index('#include "gearup13.c"') > ext.index('#include "gunlimit.c"'),
      "gearup13.c is included after skills.c and gunlimit.c")
check("PF(feature_gearup13())" in ext and ext.index("PF(feature_gearup13())") > ext.index("PROF(25, feature_gearup_flow())"), "ticked after feature_gearup_flow")
check("t2r-no-gearup13.txt" in ext, "opt-out file")
check("to1/gearup13" in ext and "PAGE_LIST_NAME" in ext and ext.count("PAGE_LIST_NAME") >= 5, "entry points push the list page through PAGE_LIST_NAME")
check("hit = gu13_scan();" in ext, "click gate hit-tests the page (an empty-space click selects nothing)")
check("!lo_r3() && !g_gu13_up" in ext, "ui_prop_due dedups alpha / visibility / pivot on the page")
check("top == PAGE_GU13" in ext, "matchflow treats the page as a loadout page")
check("gearup13_widgets.add_gearup13_page" in read("tools", "features", "widgets_patch.py"), "page registered in widgets_patch")
# log prefix
check(all(m.startswith("gearup13:") for m in re.findall(r'xlog\("([^"]*)"', c)), "every xlog line of the driver has the gearup13: prefix")

print("\n%s" % ("FAILED: %d" % len(FAILS) if FAILS else "all ok"))
sys.exit(1 if FAILS else 0)
