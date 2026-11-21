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

import nr_style as nr
from clan_widgets import Builder, _templates

PAGE = "mission-choose"
ROWS = 8
SEC_Y = 440                                   # the CHOOSE MISSION / REWARDS section rows (centre line)
ROW_Y, ROW_DY, ROW_H = 500, 124, 108          # the mission list: tile tops, pitch, height
LX0, LX1 = nr.L0, 1500                        # list column
RX0, RX1 = 1700, nr.R1                        # detail column
TIER_Y, TIER_DY, TIER_H = 830, 130, 110
NAMES = ["Down Enemies", "Executions", "Revives", "Headshots", "Mark Enemies", "Hunting Rifle Executions", "Revolver Executions", "Shorty Executions"]


def build_page(main):
    """to1/mission-choose.widget.json content: the old CHOOSE MISSION page (used when the clan page's MISSIONS tab is off, t2r-no-clan13.txt) in the
    No Return frame: breadcrumb "<FACTION> CLAN | MISSIONS", week block, the list as tile rows (the focused one outlined), the mission name, its
    rewards as three tier tiles, boxed prompts SELECT / SWITCH / CHOOSE LATER. t2r-ext feature_missions fills it."""
    t, root0, anim0 = _templates(main)
    b = Builder(t)
    root = copy.deepcopy(root0); root.update(guid=t2guid.guid())
    anim = copy.deepcopy(anim0); anim.update(guid=t2guid.guid(), parent=root["guid"])
    b.items += [root, anim]
    a = anim["guid"]
    nr.frame(b, a, "WLF CLAN", "MISSIONS", tabs_labels=None, wk=(1, 1, 0), prompts=3)
    nr.section(b, a, "miSecL", LX0, LX1, SEC_Y, "CHOOSE MISSION", "")
    for k in range(ROWS):
        y = ROW_Y + k * ROW_DY
        g = b.group(f"miRow{k}", a, b.tl(0, 0, 3840, 2160))["guid"]
        b.rect(f"miBg{k}", g, b.tl(LX0, y, LX1 - LX0, ROW_H), nr.TILE, nr.TILE_A)
        s = b.group(f"miSel{k}", g, b.tl(LX0, y, LX1 - LX0, ROW_H), visible=0)["guid"]     # the focused row: brighter fill + a 2 px outline
        b.rect(f"miSel{k}Bg", s, b.fill(), nr.TILE, nr.TILE_FA)
        for nm, pl in (("T", b.tl(0, 0, LX1 - LX0, 4)), ("B", b.tl(0, ROW_H - 4, LX1 - LX0, 4)), ("L", b.tl(0, 0, 4, ROW_H)), ("R", b.tl(LX1 - LX0 - 4, 0, 4, ROW_H))):
            b.rect(f"miSel{k}{nm}", s, pl, nr.WHITE, 255)
        b.text(f"miName{k}", g, nr.lm(LX0 + 44, y, LX1 - LX0 - 88, ROW_H), NAMES[k], nr.pt(26), nr.GREY, tracking=2)     # (also the row's mouse hit box)
    b.text("miName", a, nr.lm(RX0, SEC_Y - 30, RX1 - RX0, 110), "Down Enemies", nr.pt(44), nr.WHITE, tracking=3)
    b.text("miSub", a, nr.lm(RX0, SEC_Y + 100, RX1 - RX0, 60), "You have 3 matches to complete your mission.", nr.pt(22), nr.GREY, tracking=2)
    nr.section(b, a, "miSecR", RX0, RX1, 690, "REWARDS", "")
    b.text("miRewSub", a, nr.lm(RX0, 760, RX1 - RX0, 60), "New clan members and one-use-boosters:", nr.pt(20), nr.GREY, tracking=2)
    for k in range(3):
        y = TIER_Y + k * TIER_DY
        b.rect(f"miTierBg{k}", a, b.tl(RX0, y, RX1 - RX0, TIER_H), nr.TILE, nr.TILE_A)
        b.text(f"miTier{k}", a, nr.lm(RX0 + 44, y, RX1 - RX0 - 88, TIER_H), "", nr.pt(24), nr.WHITE, tracking=2)
    b.text("miRep", a, nr.lm(RX0, 1260, RX1 - RX0, 70), "", nr.pt(20), nr.GREY, tracking=2)
    b.text("miStatus", a, nr.lm(RX0, 1340, RX1 - RX0, 80), "", nr.pt(28), nr.ACC, tracking=3)
    w = {k: copy.deepcopy(v) for k, v in main.items() if k != "items"}
    w["items"] = b.items
    return w


def add_mission_page(wdir):
    main = json.load(open(os.path.join(wdir, "to1", "main-menu.widget.json"), encoding="utf-8"))
    json.dump(build_page(main), open(os.path.join(wdir, "to1", PAGE + ".widget.json"), "w", encoding="utf-8"), indent=4)
    return 1


def demo(page, focus=0, fac=1, day=15):
    w = copy.deepcopy(page)
    by = {i["name"]: i for i in w["items"]}
    nr.demo_header(by, "WLF CLAN" if fac == 1 else "SERAPHITE CLAN", "MISSIONS")
    nr.demo_week(by, day // 7 + 1, day % 7 + 1, day)
    nr.demo_prompts(by, [("menu:select", "SELECT", True, "menu:select"), ("W / S", "SWITCH", True, None), ("menu:back", "CHOOSE LATER", True, "menu:back")])
    nr.demo_section(by, "miSecL", LX0, LX1, "CHOOSE MISSION")
    nr.demo_section(by, "miSecR", RX0, RX1, "REWARDS")
    for k in range(ROWS):
        by[f"miSel{k}"]["visible"] = int(k == focus)
        by[f"miName{k}"]["tint.start"] = by[f"miName{k}"]["tint.end"] = nr.WHITE if k == focus else nr.GREY
    by["miName"]["text"] = NAMES[focus]
    for k, (g, s, bo) in enumerate(((3, 1, 1), (6, 1, 1), (9, 2, 2))):
        by[f"miTier{k}"]["text"] = "%d %s:   +%d SURVIVOR%s   +%d BOOSTER%s" % (g, "DOWNS", s, "S" if s > 1 else "", bo, "S" if bo > 1 else "")
    by["miRep"]["text"] = "Done 1 time before: the goals are higher."
    return w


def preview(wdir, out_dir):
    import tempfile
    import widget_preview
    main = json.load(open(os.path.join(wdir, "to1", "main-menu.widget.json"), encoding="utf-8"))
    page = build_page(main)
    for it in page["items"]:
        if it["name"] == "bgBlur":
            it["visible"] = 0                     # (the engine's live blur: the preview draws the blurred launcher art under the page instead)
    bg = nr.preview_bg(os.path.join(tempfile.gettempdir(), "t2r-nr-bg.png"))
    os.makedirs(out_dir, exist_ok=True)
    for name, kw in (("mission-choose", {}), ("mission-choose-last", {"focus": 7, "fac": 2})):
        tmp = os.path.join(tempfile.gettempdir(), "t2r-" + name + ".widget.json")
        d = demo(page, **kw)
        if kw.get("focus") == 7:
            by = {i["name"]: i for i in d["items"]}
            by["miTier0"]["text"] = "3 SHORTY EXECUTIONS:   LOSE 60%   +1 BOOSTER"
            by["miStatus"]["text"] = "MISSION STARTED"
        json.dump(d, open(tmp, "w", encoding="utf-8"))
        print(widget_preview.render(tmp, os.path.join(out_dir, name + ".png"), scale=0.5, bg=bg))
    print(f"widgets: mission-choose {len(page['items'])} (gui2 limit 1024)")


if __name__ == "__main__":
    import sys
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    preview(sys.argv[1], sys.argv[2])
