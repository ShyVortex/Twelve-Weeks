"""test_friends13.py - the FRIENDS page / button widgets and the driver agree: every widget path friends13.c writes exists in the built page (or on the button), names are unique,
rows sit inside the canvas and do not overlap, the button sits under the lobby box. No game files needed (a stub of the main menu stands in for the real one).
  python tools/tests/test_friends13.py"""
import json
import os
import re
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "tools", "features"))
import friends13_widgets as fw  # noqa: E402

FAILS = []


def check(cond, what):
    print(("ok   " if cond else "FAIL ") + what)
    if not cond:
        FAILS.append(what)


base = {"guid": 0, "parent": 0, "name": "", "visible": 1, "rotation": 0.0, "depth": 0.0, "color.a": 255, "animation": {"keyframes": {}}}
CLS = {"gameTitle": "Text", "lobbyBg": "Image", "titleUnderline": "Polyline", "onlineDot": "Ellipse", "lobbyPanel": "Group"}
names = ("gameTitle", "lobbyBg", "titleUnderline", "onlineDot", "lobbyPanel", "root", "anim-group", "versionText")
main = {"version": 1, "items": [dict(base, name=n, guid=i + 1, **{"class": CLS.get(n, "Group")}) for i, n in enumerate(names)]}
tmp = tempfile.mkdtemp(prefix="f2fw-")
os.makedirs(os.path.join(tmp, "to1"))
for n in ("main-menu", "find-match-menu"):
    json.dump(main, open(os.path.join(tmp, "to1", n + ".widget.json"), "w"))
check(fw.add_friends13_page(tmp) == 1 and fw.add_friends_button(tmp) == 2, "page + button built (button on main-menu and find-match-menu)")


def paths_of(items):
    by = {i["guid"]: i for i in items}
    out = {}
    for i in items:
        chain, c = [], i
        while c and c["name"] != "root":
            chain.append(c["name"])
            c = by.get(c["parent"])
        out[".".join(reversed(chain))] = i
    return out


page = json.load(open(os.path.join(tmp, "to1", "friends13.widget.json")))
P = paths_of(page["items"])
check(len(P) == len(page["items"]), "every widget path on the page is unique (%d widgets)" % len(P))
src = open(os.path.join(ROOT, "tools", "ext", "friends13.c"), encoding="utf-8").read()
need = set()
for lit in re.findall(r'"(anim-group\.[A-Za-z0-9_.]+)"', src):
    if lit.startswith(("anim-group.friendsBtn", "anim-group.frToast", "anim-group.lobbyPanel", "anim-group.menuList")):      # (the button / toast / the main menu's own widgets)
        continue
    if lit in ("anim-group.frFo", "anim-group.lf.lSec", "anim-group.rt.rSec", "anim-group.rt.rSc"):             # bases of the nrui.c helpers: nr_frame_at / nr_section / nr_scroll_v
        suf = {"anim-group.frFo": "TBLR", "anim-group.rt.rSc": "TH"}.get(lit)
        for sfx in ([c for c in suf] if suf else ["Tx", "Rt", "Rl"]):
            need.add(lit + sfx)
        continue
    need.add(lit)
# the row widgets friends13.c builds with fr_rp / fr_set_row
for col, g, ch, rows in (("lf", "lf", "l", fw.NL), ("rt", "rt", "r", fw.NR)):
    for i in range(rows):
        row = f"anim-group.{g}.{ch}Row{i}"
        need.add(row)
        for leaf in ("Nm", "Yu", "St", "Ac", "Fill", "Ed", "Rk", "Rn", "Hit"):
            need.add(f"{row}.{ch}{leaf}{i}")
        for k in ("Cg", "Ca", "Cw"):                  # the three chips (redesign): friends13.c fr_chip -> <base>Bg / <base>Tx
            need.add(f"{row}.{ch}{k}{i}Bg")
            need.add(f"{row}.{ch}{k}{i}Tx")
miss = sorted(p for p in need if p not in P)
check(not miss, "every path the driver writes exists on the page (%d checked)%s" % (len(need), (": missing " + ", ".join(miss[:6])) if miss else ""))
# geometry: rows inside the canvas, no overlap inside a column
def rect(it):
    return it["pivotAs.x"], it["pivotAs.y"], it["rectSizeDelta.width"], it["rectSizeDelta.height"]


for ch, rows in (("l", fw.NL), ("r", fw.NR)):
    g = "lf" if ch == "l" else "rt"
    rs = [rect(P[f"anim-group.{g}.{ch}Row{i}"]) for i in range(rows)]
    check(all(0 <= x and x + w <= 3840 and 0 <= y and y + h <= 2160 for x, y, w, h in rs), f"{ch}: rows inside the canvas")
    check(all(rs[i][1] + rs[i][3] <= rs[i + 1][1] for i in range(rows - 1)), f"{ch}: rows do not overlap")
    check(rs[-1][1] + rs[-1][3] < fw.MSG_Y, f"{ch}: the last row ends above the status line")
check(fw.MSG_Y + 60 <= fw.KEY_Y and fw.KEY_Y + 44 < 1880, "status line, key hint line and the footer prompts stack without touching")
# the button
btn = json.load(open(os.path.join(tmp, "to1", "find-match-menu.widget.json")))
B = paths_of(btn["items"])
for p in ("anim-group.friendsBtn", "anim-group.friendsBtn.frKey", "anim-group.friendsBtn.frLabel", "anim-group.friendsBtn.frSub", "anim-group.friendsBtn.frBadge",
          "anim-group.friendsBtn.frBadgeBg", "anim-group.friendsBtn.frFill", "anim-group.friendsBtn.frHit"):
    check(p in B, "button widget " + p)
check(B["anim-group.friendsBtn"]["visible"] == 0, "the button starts hidden (the ext shows it on the menus)")
x, y, w, h = rect(B["anim-group.friendsBtn"])
check((x, y, w, h) == (2500.0, 1560.0, 1182.0, 120.0), "button strip at the lobby box's bottom-left (2500, 1560, 1182 x 120)")
check(y > 1530 and y + h < 1980, "button below the lobby box (ends y 1530) and above the footer line (y 1980)")
cc = re.search(r"cx >= 2500.0f && cx <= 3682.0f && cy >= 1560.0f && cy <= 1680.0f", src)
check(cc is not None, "the driver's cursor box = the button rect")
w2 = open(os.path.join(ROOT, "tools", "features", "widgets_patch.py"), encoding="utf-8").read()
check("add_friends13_page" in w2 and "add_friends_button" in w2, "widgets_patch builds the page and the button")
# the toast card (friends13.c ft_p leaves, FT_X / FT_Y / FT_W / FT_H, the chip boxes)
check(fw.add_friends_toast(tmp) == 2, "toast built on main-menu and find-match-menu")
btn = json.load(open(os.path.join(tmp, "to1", "main-menu.widget.json")))
B = paths_of(btn["items"])
leaves = set(re.findall(r'ft_p\("([A-Za-z]+)"\)', src)) | set(f"tAc{k}" for k in range(5)) | {f"{a}{c}" for a in ("tKe", "tKt", "tLb") for c in "YN"}
for lf in sorted(leaves):
    check("anim-group.frToast." + lf in B, "toast widget " + lf)
x, y, w, h = rect(B["anim-group.frToast"])
for nm, v in (("FT_X", x), ("FT_Y", y), ("FT_W", w), ("FT_H", h)):
    m = re.search(r"#define %s ([0-9.]+)f" % nm, src)
    check(m is not None and float(m.group(1)) == v, "driver %s = widget %s" % (nm, v))
check(x + w <= 3840 - 100 and y >= 1680 and y + h <= 1980, "toast: inset from the right edge, below the FRIENDS strip (ends y 1680), above the footer prompts (y 1880+)")
for n in "YN":
    cx, cy, cw, ch = rect(B["anim-group.frToast.tFill" + n])
    check(cx + cw <= w and cy + ch <= h, "chip %s inside the card" % n)
check(B["anim-group.frToast"]["visible"] == 0, "the toast starts hidden")
fld = P["anim-group.rt.inp"]
fx, fy, fw_, fh = rect(fld)
check((fx, fy, fw_, fh) == (fw.RX, fw.RY0, fw.RW, fw.RH), "the text field covers the first right row")
print("FAILED: %d" % len(FAILS) if FAILS else "all ok")
sys.exit(1 if FAILS else 0)
