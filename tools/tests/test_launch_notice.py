"""test_launch_notice.py - the launch notice page (tools/features/notice_widgets.py) and its driver (tools/ext/launchnote.c) agree: every widget
path launchnote.c writes exists in the built page, names are unique, the box and the prompt under it sit inside the 3840 x 2160 canvas, text slots
do not overlap, and every English text piece the driver sets (cut at the <font> tags the way the loc layer cuts it) has a Polish entry in
tools/loc/pl/11-notice.txt and in tools/ext/loc_pl.h. No game files needed (a stub of the main menu stands in for the real one).
  python tools/tests/test_launch_notice.py"""
import json
import os
import re
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "tools", "features"))
import notice_widgets as nw  # noqa: E402

FAILS = []


def check(cond, what):
    print(("ok   " if cond else "FAIL ") + what)
    if not cond:
        FAILS.append(what)


base = {"guid": 0, "parent": 0, "name": "", "visible": 1, "rotation": 0.0, "depth": 0.0, "color.a": 255, "animation": {"keyframes": {}}}
CLS = {"gameTitle": "Text", "lobbyBg": "Image", "titleUnderline": "Polyline", "onlineDot": "Ellipse", "lobbyPanel": "Group"}
names = ("gameTitle", "lobbyBg", "titleUnderline", "onlineDot", "lobbyPanel", "root", "anim-group")
main = {"version": 1, "items": [dict(base, name=n, guid=i + 1, **{"class": CLS.get(n, "Group")}) for i, n in enumerate(names)]}
tmp = tempfile.mkdtemp(prefix="lnw-")
os.makedirs(os.path.join(tmp, "to1"))
json.dump(main, open(os.path.join(tmp, "to1", "main-menu.widget.json"), "w"))
check(nw.add_notice_page(tmp) == 1, "page built")
page = json.load(open(os.path.join(tmp, "to1", nw.PAGE + ".widget.json"), encoding="utf-8"))
items = page["items"]
by = {i["guid"]: i for i in items}
root = next(i for i in items if i["name"] == "root")


def path(i):
    p = []
    while i["guid"] != root["guid"]:
        p.append(i["name"])
        i = by[i["parent"]]
    return ".".join(reversed(p))


P = {path(i): i for i in items if i is not root}
nm = [i["name"] for i in items]
check(len(nm) == len(set(nm)), "widget names unique")

src = open(os.path.join(ROOT, "tools", "ext", "launchnote.c"), encoding="utf-8").read()
used = set(re.findall(r'"((?:anim-group|lnDimG)(?:\.[A-Za-z0-9]+)*)"', src))
miss = sorted(u for u in used if u not in P)
check(not miss, "every widget path launchnote.c writes exists (%d paths)%s" % (len(used), (": missing " + ", ".join(miss)) if miss else ""))


def abs_rect(i):
    x, y = 0.0, 0.0
    w, h = i["rectSizeDelta.width"], i["rectSizeDelta.height"]
    j = i
    while j["guid"] != root["guid"]:
        if j.get("anchorMaxN.x", 0.0) == 0.0:      # (the stub's root / anim-group have no rect: the full canvas)
            x += j.get("pivotAs.x", 0.0) - j.get("pivotN.x", 0.0) * j.get("rectSizeDelta.width", 0.0)
            y += j.get("pivotAs.y", 0.0) - j.get("pivotN.y", 0.0) * j.get("rectSizeDelta.height", 0.0)
        j = by[j["parent"]]
    return x, y, w, h


bx, by_, bw, bh = abs_rect(P["anim-group.lnBox"])
check(bx >= 0 and by_ >= 0 and bx + bw <= nw.W and by_ + bh <= nw.H, "box inside the canvas (%d,%d %dx%d)" % (bx, by_, bw, bh))
hx, hy, hw, hh = abs_rect(P["anim-group.lnHint"])
check(hy + hh <= nw.H, "prompt under the box inside the canvas (bottom %d)" % (hy + hh))
check(hy >= by_ + bh, "prompt below the box")
slots = sorted((abs_rect(P["anim-group.lnBox." + n]) for n, _, _ in nw.SLOTS), key=lambda r: r[1])
ov = [k for k in range(len(slots) - 1) if slots[k][1] + slots[k][3] > slots[k + 1][1]]
check(not ov, "text slots do not overlap")
lay = nw.layout()
check(lay["check"] > lay["lnP1"] and lay["btn"] > lay["check"] and lay["h"] > lay["btn"] + 124, "checkbox, then buttons, then the box edge")

# every text piece the driver sets has a Polish entry (the loc layer cuts at tags and trims blanks)
texts = re.findall(r'ui_text(?:_db)?\("[^"]+",\s*((?:"(?:[^"\\]|\\.)*"\s*(?:LN_EM\s*)?)+)\)', src)
texts += re.findall(r'snprintf\(b, sizeof b, ("(?:[^"\\]|\\.)*")', src)
texts += re.findall(r'locked \? ("[^"]+") : ticked \? ("[^"]+") : ("[^"]+")', src)[0] if re.search(r'locked \? "', src) else []
for t in re.findall(r'ui_text_db\("([^"]+)"', src):
    check(t + "B" in P, "double-buffer twin %sB exists (the timer flicker fix)" % t)
pieces = set()
for t in texts:
    t = t.replace("LN_EM", '"<font>"')                 # (the emphasis macro = a tag: the loc layer cuts there)
    s = "".join(re.findall(r'"((?:[^"\\]|\\.)*)"', t)).replace('\\"', '"')
    for p in re.split(r"<[^>]*>", s):
        p = p.strip()
        if re.search(r"[A-Za-z]{2}", p):
            pieces.add(p)
pl = {}
for line in open(os.path.join(ROOT, "tools", "loc", "pl", "11-notice.txt"), encoding="utf-8").read().splitlines():
    if " => " in line and not line.startswith("#"):
        k, v = line.split(" => ", 1)
        pl[k.strip()] = v.strip()
hdr = open(os.path.join(ROOT, "tools", "ext", "loc_pl.h"), encoding="utf-8").read()
miss = sorted(p for p in pieces if p not in pl and p != "SELECT")
check(not miss, "every English piece has a Polish line in 11-notice.txt (%d pieces)%s" % (len(pieces), (": " + " | ".join(miss)) if miss else ""))
miss_h = sorted(k for k in pl if '{"%s", ' % k.replace('"', '\\"') not in hdr)
check(not miss_h, "every 11-notice.txt line is in loc_pl.h%s" % ((": " + " | ".join(miss_h)) if miss_h else ""))
check("I ACKNOWLEDGE (%d)" in pl, "the countdown label has a template entry")
# ---- kick box (to1/kick-notice, kicknote.c)
check(nw.add_kick_page(tmp) == 1, "kick page built")
kp = json.load(open(os.path.join(tmp, "to1", nw.KICK_PAGE + ".widget.json"), encoding="utf-8"))["items"]
kby = {i["guid"]: i for i in kp}
kroot = next(i for i in kp if i["name"] == "root")


def kpath(i):
    p = []
    while i["guid"] != kroot["guid"]:
        p.append(i["name"])
        i = kby[i["parent"]]
    return ".".join(reversed(p))


KP = {kpath(i) for i in kp if i is not kroot}
ksrc = open(os.path.join(ROOT, "tools", "ext", "kicknote.c"), encoding="utf-8").read()
kused = set(re.findall(r'"((?:anim-group|knDimG)(?:\.[A-Za-z0-9]+)*)"', ksrc))
kmiss = sorted(u for u in kused if u not in KP)
check(not kmiss, "every widget path kicknote.c writes exists (%d paths)%s" % (len(kused), (": missing " + ", ".join(kmiss)) if kmiss else ""))
kpieces = set()
for f in re.findall(r'(?:ui_text\("[^"]+",\s*|snprintf\(out, n, )("(?:[^"\\]|\\.)*")', ksrc):
    for piece in re.split(r"<[^>]*>", f.strip('"').replace('\\"', '"')):
        piece = piece.strip()
        if re.search(r"[A-Za-z]{2}", piece) and piece != "%s":
            kpieces.add(piece)
kmissp = sorted(p for p in kpieces if p not in pl)
check(not kmissp, "every kick box text piece has a Polish line (%d pieces)%s" % (len(kpieces), (": " + " | ".join(kmissp)) if kmissp else ""))
print("FAILED: %d" % len(FAILS) if FAILS else "all ok")
sys.exit(1 if FAILS else 0)
