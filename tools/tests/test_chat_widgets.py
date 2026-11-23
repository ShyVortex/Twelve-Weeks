"""chat_widgets.py (in-game chat) on stub widget files: every leaf chat.c finds exists, the geometry mirrors chat.c's constants, the build
is idempotent. Plain script: python tools/tests/test_chat_widgets.py"""
import json
import os
import re
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "tools", "features"))
import chat_widgets as cw  # noqa: E402

FAILS = []


def check(cond, what):
    print(("ok   " if cond else "FAIL ") + what)
    if not cond:
        FAILS.append(what)


base = {"guid": 0, "parent": 0, "name": "", "visible": 1, "rotation": 0.0, "depth": 0.0, "color.a": 255, "animation": {"keyframes": {}}}
CLS = {"gameTitle": "Text", "lobbyBg": "Image", "titleUnderline": "Polyline", "onlineDot": "Ellipse", "lobbyPanel": "Group"}
names = ("gameTitle", "lobbyBg", "titleUnderline", "onlineDot", "lobbyPanel", "root", "anim-group", "versionText")
main = {"version": 1, "items": [dict(base, name=n, guid=i + 1, **{"class": CLS.get(n, "Group")}) for i, n in enumerate(names)]}
tmp = tempfile.mkdtemp(prefix="chatw-")
os.makedirs(os.path.join(tmp, "to1"))
for n in ("main-menu", "currency-hud", "pause-menu"):
    json.dump(main, open(os.path.join(tmp, "to1", n + ".widget.json"), "w"))

nadd = cw.add_chat(tmp)
check(nadd > 40, "chat widgets built (%d)" % nadd)
check(cw.add_chat(tmp) == 0, "second run adds nothing")

src = open(os.path.join(ROOT, "tools", "ext", "chat.c"), encoding="utf-8").read()


def items(page):
    return json.load(open(os.path.join(tmp, "to1", page + ".widget.json"), encoding="utf-8"))["items"]


hud = items("currency-hud")
by = {i["name"]: i for i in hud}
box = by.get("chatBox")
check(box is not None and box["visible"] == 0, "chatBox exists and starts hidden")
check(by["chatBox"]["parent"] == by["chatHud"]["guid"] and by["chatHud"]["parent"] == by["root"]["guid"], "chatHud > chatBox under root")
# every leaf chat.c looks up with hud_widget("chatHud", "chatBox", "<leaf>") or through a "%d" leaf list is a direct child of chatBox
kids = {i["name"] for i in hud if i["parent"] == box["guid"]}
lits = set(re.findall(r'"(ch[A-Z][A-Za-z]*\d?)"', src))
fmts = re.findall(r'"(ch[A-Z][A-Za-z]*)%d"', src)
for f in fmts:
    for k in range(5):
        if (f + str(k)) in kids:
            lits.add(f + str(k))
want = {"chBg", "chBgI", "chLbl", "chFld", "chFtx", "chFch", "chHint", "chIdl"} | {"chT%d" % k for k in range(3)} | {"chU%d" % k for k in range(3)} \
    | {"chFu%d" % k for k in range(3)} | {"chL%d" % k for k in range(5)}
miss = sorted(want - kids)
check(not miss, "HUD leaves under chatBox: missing %s" % miss)
miss = sorted(n for n in lits if n.startswith("ch") and n not in kids and n not in ("chatHud", "chatBox"))
check(not miss, "every literal HUD leaf chat.c names exists (%s)" % miss)
for n in ["chL%d" % k for k in range(5)] + ["chFtx"]:          # the double-buffer twins (chat.c chw_has_twin)
    check(n + "B" in by and by[n + "B"]["parent"] == box["guid"] and by[n + "B"]["visible"] == 0 and by[n + "B"]["text"] == "", "HUD twin %sB hidden + empty" % n)
for n, w_ in (("HB_LINE_PT", "CHB_LINE_PT"), ("HB_W - 2 * HB_LX", "CHB_LINE_W"), ("36", "CHB_FLD_X"), ("HB_W - 36", "CHB_FCH_R"),
                ("HB_SMALL_PT", "CHB_FCH_PT")):
    m = re.search(r"#define %s ([0-9.]+)f" % w_, src)
    check(m is not None and float(m.group(1)) == float(eval(n, vars(cw))), "chat.c %s = widget %s" % (w_, n))
# the tab slots / underline line mirror chat.c
m = re.search(r"#define CHB_TABS_R ([0-9.]+)f", src)
check(m is not None and float(m.group(1)) == cw.HB_TABS_R == cw.HB_W - cw.HB_LX, "chat.c CHB_TABS_R = widget HB_TABS_R = HB_W - HB_LX")
m = re.search(r"#define CH_TAB_GAP ([0-9.]+)f", src)
check(m is not None and float(m.group(1)) == cw.TAB_GAP_EM, "chat.c CH_TAB_GAP = widget TAB_GAP_EM")
m = re.search(r"#define CHB_IDLE_DY ([0-9.]+)f", src)
check(m is not None and float(m.group(1)) == cw.HB_IDLE_DY, "chat.c CHB_IDLE_DY = widget HB_IDLE_DY")
m = re.search(r"#define CHB_UL_Y ([0-9.]+)f", src)
check(m is not None and float(m.group(1)) == cw.HB_UL_Y, "chat.c CHB_UL_Y = widget HB_UL_Y")
m = re.search(r"#define CHB_TAB_PT ([0-9.]+)f", src)
check(m is not None and float(m.group(1)) == cw.HB_TAB_PT, "chat.c CHB_TAB_PT = widget HB_TAB_PT")
check(cw.HB_X + cw.HB_W < 1920 and cw.HB_Y + cw.HB_HINT_Y + 48 < 2160, "HUD box on screen, left half")

pz = items("pause-menu")
pb = {i["name"]: i for i in pz}
g = pb.get("pzChat")
check(g is not None and g["visible"] == 0 and g["parent"] == pb["anim-group"]["guid"], "pzChat under anim-group, hidden")
pk = {i["name"] for i in pz if i["parent"] == g["guid"]}
want = {"pcSecTx", "pcSecRt", "pcSecRl", "pcBg", "pcFld", "pcFtx", "pcFch"} | {"pcT%d" % k for k in range(3)} | {"pcU%d" % k for k in range(3)} \
    | {"pcFu%d" % k for k in range(3)} | {"pcL%d" % k for k in range(4)}
miss = sorted(want - pk)
check(not miss, "ESC leaves under pzChat: missing %s" % miss)
check("pzPBadge" in pb and {"pzPBadgeBg", "pzPBadgeTx"} <= {i["name"] for i in pz if i["parent"] == pb["pzPBadge"]["guid"]}, "P badge group + leaves")
m = re.search(r"#define PC_TABS_R ([0-9.]+)f", src)
check(m is not None and float(m.group(1)) == cw.PC_W, "chat.c PC_TABS_R = widget PC_W")
m = re.search(r"#define PC_TAB_PT ([0-9.]+)f", src)
check(m is not None and float(m.group(1)) == cw.PC_TAB_PT, "chat.c PC_TAB_PT = widget PC_TAB_PT")
m = re.search(r"#define PC_UL_Y ([0-9.]+)f", src)
check(m is not None and float(m.group(1)) == cw.PC_UL_Y, "chat.c PC_UL_Y = widget PC_UL_Y")
m = re.search(r"#define PC_TABS_X0 ([0-9.]+)f", src)
check(m is not None and float(m.group(1)) == cw.PC_TABS_X0, "chat.c PC_TABS_X0 = widget PC_TABS_X0")
for n in ["pcL%d" % k for k in range(4)] + ["pcFtx"]:
    check(n + "B" in pb and pb[n + "B"]["parent"] == g["guid"] and pb[n + "B"]["visible"] == 0, "ESC twin %sB hidden" % n)
for n, w_ in (("34", "PC_FLD_X"), ("PC_W - 26", "PC_FCH_R")):
    m = re.search(r"#define %s ([0-9.]+)f" % w_, src)
    check(m is not None and float(m.group(1)) == float(eval(n, vars(cw))), "chat.c %s = widget %s" % (w_, n))
rl = pb["pcSecRl"]
check(abs(rl["pivotAs.x"] + rl["scale.x"] * 1000 - cw.PC_TABS_X0) < 40, "CHAT section rule ends near the tabs")
for k in range(3):
    check(pb["pcU%d" % k]["visible"] == int(k == 1) and by["chU%d" % k]["visible"] == int(k == 1), "only TEAM underline shown in the template (%d)" % k)

print("FAILED: %d" % len(FAILS) if FAILS else "all ok")
sys.exit(1 if FAILS else 0)
