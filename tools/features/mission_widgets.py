"""to1/mission-choose: the 2013 CHOOSE MISSION page (re/factions2013/screens/eachdaymissions.png), added to
gui2-widgets.pak by widgets_patch.patch_widgets.

Left: "CHOOSE MISSION:" and the list (one row per mission, the focused one bright with a marker); right: the
mission name, "You have 3 matches to complete your mission.", "Rewards:" and the three tiers
("3 Downs:  +1 SURVIVOR  +1 BOOSTER"). t2r-ext (feature_missions) fills every text, shows / hides the rows and
moves the marker; the data is tools/clan.py MISSIONS (names / goals mirrored in the ext's MIS table).
Widget space is 3840 x 2160, y down. python mission_widgets.py <extracted widget dir> <out dir> renders previews."""
import copy
import json
import os
import t2guid

from clan_widgets import Builder, _templates, PM_TEXT, PM_DIM, HEALTHY

PAGE = "mission-choose"
ROWS = 8
ROW_Y, ROW_H = 520, 110
LIST_X = 330
RX = 1500
NAMES = ["Down Enemies", "Executions", "Revives", "Headshots", "Mark Enemies", "Hunting Rifle Executions", "Revolver Executions", "Shorty Executions"]


def build_page(main):
    """to1/mission-choose.widget.json content."""
    t, root0, anim0 = _templates(main)
    b = Builder(t)
    root = copy.deepcopy(root0); root.update(guid=t2guid.guid())
    anim = copy.deepcopy(anim0); anim.update(guid=t2guid.guid(), parent=root["guid"])
    b.items += [root, anim]
    a = anim["guid"]
    b.image("bgBlur", a, b.bleed(), "general-textures/blur-background.png", 0xFFFFFFFF, 255)
    b.rect("bgDark", a, b.bleed(), 0xFF0B0C0D, 236)
    b.image("bgLight", a, b.ctr(1920, 980, 3600, 2200), "hud/player-menu/gradient/radial-gradient.png", 0xFFFFFFFF, 20)
    b.text("miTitle", a, b.tl(450, 150, 2400, 150), "WEEK 1: DAY 1", 86, PM_TEXT, tracking=6)
    b.line("miTitleLine", a, 264, 305, 3576, 305, 0xFFFFFFFF, 120, 2.0)
    b.text("miHead", a, b.tl(LIST_X, 380, 1000, 90), "CHOOSE MISSION:", 56, PM_TEXT, tracking=5)
    for k in range(ROWS):
        cy = ROW_Y + k * ROW_H + ROW_H / 2
        g = b.group(f"miRow{k}", a, b.tl(0, 0, 3840, 2160))["guid"]
        b.rect(f"miSel{k}", g, b.tl(LIST_X - 40, cy - 48, 1000, 96), 0xFFFFFFFF, 34, visible=0)
        b.text(f"miName{k}", g, b.tl(LIST_X, cy - 45, 900, 90), NAMES[k], 50, PM_DIM, tracking=3)
    b.line("miDivider", a, 1400, 400, 1400, 1700, 0xFFFFFFFF, 150, 2.0)
    b.text("miName", a, b.tl(RX, 400, 1900, 120), "Down Enemies:", 70, PM_TEXT, tracking=4)
    b.text("miSub", a, b.tl(RX, 520, 2000, 80), "You have 3 matches to complete your mission.", 44, PM_TEXT, tracking=2)
    b.line("miLine", a, RX, 660, 3200, 660, 0xFFFFFFFF, 220, 2.0)
    b.text("miRew", a, b.tl(RX, 700, 1500, 100), "Rewards:", 62, PM_TEXT, tracking=4)
    b.text("miRewSub", a, b.tl(RX, 820, 2200, 80), "New clan members and one-use-boosters:", 42, PM_TEXT, tracking=2)
    for k in range(3):
        b.text(f"miTier{k}", a, b.tl(RX + 120, 960 + k * 150, 2000, 100), "", 56, PM_TEXT, tracking=3)
    b.text("miRep", a, b.tl(RX, 1480, 2100, 80), "", 40, PM_DIM, tracking=3)
    b.text("miStatus", a, b.tl(RX, 1580, 2100, 80), "", 44, HEALTHY, tracking=3)
    b.image("miSelIcon", a, b.tl(270, 1898, 56, 56), "menu:select", 0xFFFFFFFF)
    b.text("miSelText", a, b.tl(350, 1890, 500, 70), "SELECT", 46, PM_TEXT, tracking=4)
    b.text("miHint", a, b.tl(900, 1890, 2600, 70), "W / S  TO SWITCH     ESC  CHOOSE LATER", 38, PM_DIM, tracking=4)
    w = {k: copy.deepcopy(v) for k, v in main.items() if k != "items"}
    w["items"] = b.items
    return w


def add_mission_page(wdir):
    main = json.load(open(os.path.join(wdir, "to1", "main-menu.widget.json"), encoding="utf-8"))
    json.dump(build_page(main), open(os.path.join(wdir, "to1", PAGE + ".widget.json"), "w", encoding="utf-8"), indent=4)
    return 1


def demo(page, focus=0):
    w = copy.deepcopy(page)
    by = {i["name"]: i for i in w["items"]}
    for k in range(ROWS):
        by[f"miSel{k}"]["visible"] = int(k == focus)
        by[f"miName{k}"]["tint.start"] = by[f"miName{k}"]["tint.end"] = PM_TEXT if k == focus else PM_DIM
    by["miName"]["text"] = NAMES[focus] + ":"
    for k, (g, s, bo) in enumerate(((3, 1, 1), (6, 1, 1), (9, 2, 2))):
        by[f"miTier{k}"]["text"] = "%d Downs:   +%d SURVIVOR%s   +%d BOOSTER%s" % (g, s, "S" if s > 1 else "", bo, "S" if bo > 1 else "")
    by["miRep"]["text"] = "Done 1 time before: the goals are higher."
    return w


def preview(wdir, out_dir):
    import tempfile
    import widget_preview
    main = json.load(open(os.path.join(wdir, "to1", "main-menu.widget.json"), encoding="utf-8"))
    page = build_page(main)
    os.makedirs(out_dir, exist_ok=True)
    tmp = os.path.join(tempfile.gettempdir(), "t2r-mission-choose.widget.json")
    json.dump(demo(page), open(tmp, "w", encoding="utf-8"))
    print(widget_preview.render(tmp, os.path.join(out_dir, "mission-choose.png")))


if __name__ == "__main__":
    import sys
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    preview(sys.argv[1], sys.argv[2])
