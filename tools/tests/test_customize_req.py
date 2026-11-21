"""The CUSTOMIZE unlock requirement card (the unlock requirement text cut into other elements and was bad design ... some
requirements are impossible since maps like chase arent in the pool").

Checks:
  - the card (customize_widgets.build_req) stays left of the prompt row and above the screen edge, at the grid's width;
  - every challenge line, at every number it can show and on every map, in English and Polish, wraps to REQ_MAX_LINES at most;
  - customize.c repeats the card's numbers and the wrap estimate (CZ_REQ_* = REQ_*, cz_req_cw = _cw);
  - the old one-line hint is gone (pHint carries only refusals), the CHALLENGES tip hides the card;
  - every map a map-wins challenge names is in the shipped pool (no Chase, no School / Gas Station, no Part I DLC map).

Run: python tools/tests/test_customize_req.py   (plain python, no game files)."""
import glob
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.dirname(HERE)
ROOT = os.path.dirname(TOOLS)
sys.path.insert(0, os.path.join(TOOLS, "features"))
sys.path.insert(0, TOOLS)
import customize_items as CI  # noqa: E402
import customize_widgets as CW  # noqa: E402

FAILS = []


def check(cond, what):
    print(("ok   " if cond else "FAIL ") + what)
    if not cond:
        FAILS.append(what)


def read(*p):
    return open(os.path.join(ROOT, *p), encoding="utf-8", errors="replace").read()


cz = read("tools", "ext", "customize.c")
czc = read("tools", "ext", "customize_challenges.c")

# ---- geometry: the grid's width, under the grid, left of every prompt, above the bottom edge
gw = CW.COLS * CW.CARD_W + (CW.COLS - 1) * CW.GAP
check(CW.REQ_X0 == CW.GRID_X and CW.REQ_X1 - CW.REQ_X0 == gw, "card spans the grid's width (%d .. %d)" % (CW.REQ_X0, CW.REQ_X1))
check(CW.REQ_Y >= CW.GRID_Y + CW.ROWS * CW.CARD_H + (CW.ROWS - 1) * CW.GAP + 20, "card starts under the grid")
prompt_x0 = min(gx for _, _, _, gx, _, _ in CW.prompt_boxes())
ch_kx = CW.prompt_boxes()[-1][3] - 80 - CW.CH_W - 16 - CW.CH_KEY          # the CHALLENGES key box (build_page)
check(CW.REQ_X1 + 200 < min(prompt_x0, ch_kx), "card ends left of the prompt row (card %d, first prompt %d)" % (CW.REQ_X1, min(prompt_x0, ch_kx)))
bottom = CW.req_bar_y(CW.REQ_MAX_LINES) + CW.REQ_BAR_H / 2 + 30                # the count text's lower half
check(bottom <= 2160 - 20, "card with %d description lines stays on screen (bottom %d)" % (CW.REQ_MAX_LINES, bottom))

# ---- every line, every number, every map, EN + PL
pl = {}
for f in glob.glob(os.path.join(ROOT, "tools", "loc", "pl", "*.txt")):
    for ln in open(f, encoding="utf-8"):
        if " => " in ln and not ln.lstrip().startswith("#"):
            k, v = ln.rstrip("\n").split(" => ", 1)
            pl[k.strip()] = v.strip()
worst = (0, "")
missing = []
for key, (kind, arg, title, line, nums, lo) in CI.U_CHAL.items():
    for t in (title, line):
        if t not in pl:
            missing.append(t)
    for n in set(nums):
        maps = CI.U_MAPS if "%s" in line else [(None, None)]
        for _, mname in maps:
            en = line if "%" not in line else line % ((n, mname) if mname else n)
            if key == "safes" and n == 1:
                en = "CRACK 1 SAFE IN INTERROGATION"
            outs = [en]
            tpl = pl.get(line)
            if tpl:
                outs.append(tpl.replace("{1}", str(n)).replace("{2}", pl.get(mname, mname or "")))
            for s in outs:
                L = CW.req_lines(s)
                if L > worst[0]:
                    worst = (L, s)
check(not missing, "every challenge title / line has a Polish line (%s)" % missing[:3])
check(worst[0] <= CW.REQ_MAX_LINES, "every requirement wraps to %d lines at most (worst %d: %s)" % (CW.REQ_MAX_LINES, worst[0], worst[1]))
check(CW.req_lines("NIECH DRUŻYNA POWALI OZNACZONYCH PRZEZ CIEBIE WROGÓW: 750") == 2, "the longest Polish line takes 2 lines")
check(CW.req_lines("SURVIVE 4 WEEKS") == 1, "a short line takes 1 line")

# ---- customize.c repeats the widget numbers and the estimate
def cdef(name):
    m = re.search(r"#define %s ([0-9.]+)f?\b" % name, cz)
    return float(m.group(1)) if m else None


check(cdef("CZ_REQ_DS_PT") == CW.REQ_DS_PT, "CZ_REQ_DS_PT = REQ_DS_PT (%s)" % CW.REQ_DS_PT)
check(cdef("CZ_REQ_N_PT") == CW.REQ_N_PT, "CZ_REQ_N_PT = REQ_N_PT (%s)" % CW.REQ_N_PT)
check(cdef("CZ_REQ_LINE_H") == CW.REQ_LINE_H, "CZ_REQ_LINE_H = REQ_LINE_H")
check(cdef("CZ_REQ_MAX_LINES") == CW.REQ_MAX_LINES, "CZ_REQ_MAX_LINES = REQ_MAX_LINES")
check(cdef("CZ_REQ_BAR_H") == CW.REQ_BAR_H, "CZ_REQ_BAR_H = REQ_BAR_H")
check("+ 36.0f + 56.0f)" in cz and CW.REQ_Y - (CW.GRID_Y + CW.ROWS * CW.CARD_H + (CW.ROWS - 1) * CW.GAP) == 36 and CW.REQ_DS_Y - CW.REQ_Y == 56,
      "CZ_REQ_DS_Y = REQ_DS_Y (36 under the grid + 56)")
check("lines * CZ_REQ_LINE_H + 22.0f" in cz and "min(lines, REQ_MAX_LINES) * REQ_LINE_H + 22" in read("tools", "features", "customize_widgets.py"),
      "the bar sits 22 under the last line in both")
cw = re.search(r"cz_req_cw\(unsigned char c\) \{ return c == ' ' \? ([0-9.]+)f : \(c >= 'a' && c <= 'z'\) \? ([0-9.]+)f : ([0-9.]+)f; \}", cz)
check(cw is not None and tuple(float(x) for x in cw.groups()) == (CW._cw(" "), CW._cw("a"), CW._cw("A")), "cz_req_cw = customize_widgets._cw")
check("lim = w * 0.96f" in cz and "1.06f" in cz, "cz_req_lines uses the same slack (4 %) and tracking (+6 %)")

# ---- the old hint line, the tip
check(re.search(r'ui_text\("anim-group\.pHint", msg \? CZ\.msg : ""\)', cz) is not None, "pHint shows only refusals / notes now")
check("cz_lock_text(fac, sex, cat, foc, b" not in cz, "the one-line requirement is no longer written to pHint")
check('"pHint", "req",' in czc, "the CHALLENGES tip hides the card")
check("!g_czc_tip" in cz, "cz_fill keeps the card hidden while the tip is up")

# ---- the maps a challenge names are all playable
daemon = read("tools", "daemon.py")
base = re.findall(r'^\s+\("[^"]+", "([a-z0-9-]+)", "to1-[a-z0-9-]+"\),', daemon[daemon.index("MAPS = ["):daemon.index("SP_MAPS = [")], re.M)
sp = dict(re.findall(r'^\s+\("[^"]+", "([a-z0-9-]+)", "to1-[a-z0-9-]+", "([a-z0-9-]+)"\)', daemon, re.M))
ship = re.search(r'SHIP_SP_MAPS = "([^"]+)"', read("release", "build_release.py")).group(1).split(",")
excluded = {"school", "gas-station"}                       # not in the pool (T2R_MAP_EXCLUDE)
for key, name in CI.U_MAPS:
    ok = (key in base and key not in excluded) or (key in sp and sp[key] in ship)
    check(ok, "map-wins map %s (%s) is in the shipped pool" % (name, key))
check(all(k != "chase" for k, _ in CI.U_MAPS), "no map-wins challenge names Chase")

print("all ok" if not FAILS else "FAILED: %d" % len(FAILS))
sys.exit(1 if FAILS else 0)
