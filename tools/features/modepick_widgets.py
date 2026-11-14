"""FIND MATCH mode choice ON the MP main menu (sketch re/modepick-sketch-1102.jpg): FIND MATCH opens, right next to its row, an arrow and a
box open on the right with the modes stacked in it. The main menu stays fully visible (no page is pushed). Also adds the CLAN row to the MP menu list
(the way into the in-game CLAN page, t2r-ext clan13.c, replacing the old F key + its hint).

to1/main-menu (anim-group):
  menuList.FindMatch   its tags.action (push to1/find-match-menu) is REMOVED: t2r-ext (modepick.c) catches select / click on it and opens the box
  menuList.Clan        new row after FIND MATCH (same native button, source menu/components/button-default_autobright.widget); the rows below move 106 down
  modeBox              hidden group (t2r-ext shows it): panel (the survivors box's look: blur + dark rect + thin lines, left / top / bottom edges only, open on
                       the right), modeBox.modeList = a native vertical Menu2::Container with one NATIVE button per mode (Mode<k>, the same widget as FIND MATCH,
                       text from tools/modes.json) and modeBox.cnt<k> = plain native-style text "<n> SEARCHING" (the online count's face / effect, smaller, dim)
  modeArrow            the arrow before the box (shown with it)
to1/find-match-menu: the Clan row too (first row; the rows below move 106 down).
Widget space 3840 x 2160, y down. FIND MATCH row: x 180.., y 524..580."""
import copy
import json
import os
import t2guid

from clan_widgets import Builder, _templates

BOX = "modeBox"
ROW_CY = 552                 # centre of the FIND MATCH row (y 524..580)
STEP = 106.0                 # the menu list's row pitch
BTN_H = 56.0
BX = 720                     # box left edge (the closed side); the arrow sits right before it
BW = 940                     # box width (open on the right: no right edge)
PADY = 40
PADX = 36
CNT_X = 500                  # where the count text starts inside the buttons' row
DIM = 0xFF8C8C8C             # the online label's grey


def modes():
    import sys
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
    import gen_modes         # tools/modes.json: THE list (id, key, label, accent); a new mode = a new row there
    return gen_modes.load()


def _list_rows(w):
    ml = next(i for i in w["items"] if i["name"] == "menuList")
    return ml, [i for i in w["items"] if i.get("parent") == ml["guid"]]


def add_clan_row(w, after):
    """The CLAN button as a menu row: a copy of GEAR UP (a native button, source + text), no action tag (t2r-ext opens the page). after = the row it follows
    (None = first). The visible rows below it move down one step (hidden rows sit at y -5000 and stay)."""
    ml, rows = _list_rows(w)
    tpl = next(i for i in rows if i["name"] == "Loadouts")
    prev = next((i for i in rows if i["name"] == after), None)
    y = (prev["pivotAs.y"] + STEP) if prev else 0.0
    for r in rows:
        if r.get("visible", 1) and r["pivotAs.y"] > -1000 and r["pivotAs.y"] >= y - 0.5:
            r["pivotAs.y"] += STEP
    c = copy.deepcopy(tpl)
    c.update(guid=t2guid.guid(), name="Clan", text="CLAN", visible=1, focusable=1)
    c["pivotAs.y"] = y
    c.pop("tags", None)
    at = w["items"].index(prev) + 1 if prev else w["items"].index(rows[0])
    w["items"].insert(at, c)
    ml["rectSizeDelta.height"] = float(ml.get("rectSizeDelta.height", 480.0)) + STEP
    return c


QUICK_LABEL = "QUICK MATCH"
MAN_W, MAN_H, CNT_W = 22, 40, 92     # the count: icon 22 x 40 (the NR man is 36 x 66), the number box, together right-aligned in the row
RW, RH, RPITCH = 700, 92, 104      # a mode row inside the panel: card, 1 px edge, focus fill + frame (the clan page's row look: clan13_widgets.edge)
PAD = 28


def add_box(w, mlist):
    """The box: a closed panel (card + thin edge, the clan overview's look) with one row per mode: card / edge / hidden focus fill + frame, the label in
    the clan page's row face, the live count right-aligned in the small dim face. t2r-ext (modepick.c) fades mpFill<k> / mpFrame<k> with the selection."""
    import clan13_widgets as c13
    mlist = list(mlist) + [{"label": QUICK_LABEL}]       # QUICK MATCH: the last row, "any mode" - not in modes.json (modepick.c: row MODE_N)
    n = len(mlist)
    t, _, _ = _templates(w)
    b = Builder(t)
    by = {i["name"]: i for i in w["items"]}
    anim = by["anim-group"]["guid"]
    bw = RW + 2 * PAD
    bh = n * RH + (n - 1) * (RPITCH - RH) + 2 * PAD
    top = ROW_CY - bh / 2.0
    box = b.group(BOX, anim, b.tl(BX, top, bw, bh), visible=0, depth=4.6)
    bg = box["guid"]
    box.update({"focusable": 0, "engineClass": ""})
    b.image("modeBlur", bg, b.fill(), "general-textures/blur-background.png", 0xFFFFFFFF, 255)
    b.rect("modeBg", bg, b.fill(), 0xFF000000, 190)
    b.frame("modeEdge", bg, b.fill(), 0xFFFFFFFF, 90, 2.0)
    arrow = b.add("Polyline", "modeArrow", anim, **b.tl(BX - 70, ROW_CY - 24, 36, 48), **b.col(0xFFFFFFFF), closed=1, lineWidth=4.0,
                  pointsUv=[0.0, 0.0, 1.0, 0.5, 0.0, 1.0], visible=0, **{"color.a": 210})
    b.items.remove(arrow)
    for k, m in enumerate(mlist):
        g = b.group(f"modeRow{k}", bg, b.tl(PAD, PAD + k * RPITCH, RW, RH))["guid"]
        c13.edge(b, "mp", k, g, RW, RH)
        b.text(f"mpNm{k}", g, c13.tlm(36, (RH - 52) / 2.0, 420, 52), m["label"], 44, c13.TEXT, tracking=2)
        # the live count: No Return's HUD man (hud/rogue/enemies-man-icon.png, white, shipped as streaming/t2r/icons/nr-man.png) left of the number, white; one group
        # (mpCntG<k>) so t2r-ext dims both together (50 % at 0). Icon 22 x 40 and the number box share the row's centre line.
        cg = b.group(f"mpCntG{k}", g, b.tl(RW - 36 - CNT_W, 0, CNT_W, RH))["guid"]
        b.image(f"mpMan{k}", cg, b.tl(0, (RH - MAN_H) / 2.0, MAN_W, MAN_H), "streaming/t2r/icons/nr-man.png", 0xFFFFFFFF, 255, scaleMode="StretchAspect")
        b.text(f"mpCnt{k}", cg, b.tl(MAN_W + 14, (RH - 44) / 2.0, CNT_W - MAN_W - 14, 44), "...", 34, 0xFFFFFFFF, face="Default", align=0, tracking=2)
        b.rect(f"mpHit{k}", g, b.fill(), 0xFFFFFFFF, c13.HIT_A)
    w["items"] += [box] + b.items + [arrow]
    return len(b.items)


def add_modepick_ui(wdir):
    p = os.path.join(wdir, "to1", "main-menu.widget.json")
    main = json.load(open(p, encoding="utf-8"))
    n = 0
    for it in main.get("items", []):
        t = it.get("tags") or {}
        if it.get("name") == "FindMatch" and t.get("action") == "push to1/find-match-menu":
            del t["action"]
            if not t:
                it.pop("tags")
            n += 1
    assert n == 1, f"main-menu FindMatch row: {n} match(es)"
    add_clan_row(main, "FindMatch")
    nb = add_box(main, modes())
    json.dump(main, open(p, "w", encoding="utf-8"), indent=4)
    fp = os.path.join(wdir, "to1", "find-match-menu.widget.json")
    fm = json.load(open(fp, encoding="utf-8"))
    add_clan_row(fm, None)
    json.dump(fm, open(fp, "w", encoding="utf-8"), indent=4)
    return nb


def preview(wd, out, opened=True, focus=0, counts=(3, 0, 3)):
    """Offline preview (widget_preview has no button renderer: the native buttons are drawn as their label text, 41 pt, normal / focused colour)."""
    import widget_preview
    w = json.load(open(os.path.join(wd, "to1", "main-menu.widget.json"), encoding="utf-8"))
    by = {i["name"]: i for i in w["items"]}
    if opened:
        by[BOX]["visible"] = 1
        by["modeArrow"]["visible"] = 1
        for k, c in enumerate(counts):
            by[f"mpCnt{k}"]["text"] = str(c)
    foc = f"Mode{focus}" if opened else "FindMatch"
    for i in w["items"]:
        if i.get("class") == "Reference" and "button-default" in i.get("source", ""):
            on = i["name"] == foc
            i["class"] = "Text"
            i.update({"pointSize": 41, "alignH": 0, "alignV": 1, "faceId": "Default", "autoSize": 0, "effect": "SoftOutline",
                      "tint.start": 0xFFF2F2F2 if on else 0xFFA8A8A8, "tint.end": 0xFFF2F2F2 if on else 0xFFA8A8A8,
                      "rectSizeDelta.width": 700.0})
    tmp = os.path.join(os.environ.get("TEMP", "."), "mp3-prev.widget.json")
    json.dump(w, open(tmp, "w", encoding="utf-8"))
    return widget_preview.render(tmp, out, scale=0.5)


if __name__ == "__main__":
    import sys
    print(preview(sys.argv[1], sys.argv[2]))
