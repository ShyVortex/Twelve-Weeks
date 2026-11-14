"""GEAR UP pages, UI round 2 (B2 "three columns" merged): slot column | picker list | details panel on a grit ground.

Pages (to1/): loadout-root (the shared chrome), loadout-menu (the edit page: 7 slot rows), picker-primary / picker-secondary / picker-purchase
(weapon pickers) and picker-skill (the loadout list AND the skill picker).  The B2 "list" and "picker" previews are one layout now:

    220 ..1140   slot column   - the real slot rows on the edit page; on the pickers a MIRROR (loMirror: 7 rows loSl<i>Bg/Fr/Ic/Lb/Nm/Co) that
                                 t2r-ext fills with the equipped loadout, the slot being picked framed (r2_mirror_fill in t2r-ext.c)
    1240..2400   picker list   - pickerList / rowDeco (weapons) or list.contents (picker-skill), same rows as before, only moved right
    2500..3680   details panel - unchanged widget (icon, name, LP, description, level boxes, 4 stat bars); t2r-ext keeps filling it

Header = the post-match header style (clan_widgets pmTitle: faceId Default, 86 pt, tracking 6, #D8D4CC).  Ground = streaming/t2r/clan/r2-grit
(ui_r2_common.grit, written by tools/models/figures/ship.py): widget `loGrit` is the first child of anim-group, so it fades in and out with the page
(quick page fade) while the pages under / over it keep it (no flicker between list and picker: every gear up page carries the same ground).
t2r-ext detects the new layout by the widget `anim-group.loMirror` (list x 1240 instead of 240) - no flag file, an old pak (T2R_LOADOUT_R2=0) works as before.

Opt-out (the old look): T2R_LOADOUT_R2=0 (or T2R_UI_R2=0) when running widgets_patch / the build.  T2R_LOADOUT_R2_GRIT=0 keeps the layout but drops the ground."""
import copy
import json
import os

import t2guid
from clan_widgets import Builder, _templates
from pause_restyle_widgets import _col, _put

W, H = 3840, 2160
PM_TEXT, BLUE, DIM = 0xFFD8D4CC, 0xFF8EC3EA, 0xFF8E8B82
GRIT = "streaming/t2r/clan/r2-grit.png"
HEAD_PT, HEAD_TRACK = 86, 6                    # the post-match WEEK n: DAY d header
COL_PT = 56                                    # column headers (pickerTitle / loadoutName / LP counter)
SLOT_X, SLOT_W = 220, 920
LIST_X, LIST_W = 1240, 1160
Y0, HEAD_Y = 660, 440
SLOT_PITCH, SLOT_H = 180, 160
MIRROR_ROWS = 7                                # PRIMARY, SECONDARY, SKILL 1-4, PURCHASABLE (the order of loadout-menu's slotList)
PICKERS = ("picker-primary", "picker-secondary", "picker-purchase")
COST_X = LIST_W - 270                          # rowDeco cost text (was 1130 of a 1400 wide list)
SCROLL_X = LIST_X + LIST_W + 30


def _load(wdir, name):
    return json.load(open(os.path.join(wdir, "to1", name + ".widget.json"), encoding="utf-8"))


def _save(wdir, name, w):
    json.dump(w, open(os.path.join(wdir, "to1", name + ".widget.json"), "w", encoding="utf-8"), indent=4)


def _hide(by, *names):
    for n in names:
        if n in by:
            by[n]["color.a"] = 0


def _txt(it, pt, argb=None, align=None, tracking=None, face="Default"):
    it["pointSize"] = pt
    it["faceId"] = face
    if argb is not None:
        _col(it, argb)
    if align is not None:
        it["alignH"] = align
    if tracking is not None:
        it["tracking.x"] = float(tracking)


def _chrome(wdir):
    """to1/loadout-root (shared by the five pages): post-match style header, full-width rule, no side shade."""
    w = _load(wdir, "loadout-root")
    by = {i["name"]: i for i in w["items"]}
    if by["menuTitle"].get("pointSize") == HEAD_PT:
        return 0
    _hide(by, "menuShade")
    _put(by["menuTitle"], SLOT_X - 4, 120, 2300, 150)
    _txt(by["menuTitle"], HEAD_PT, PM_TEXT, 0, HEAD_TRACK)
    _put(by["gameTitle"], 2640, 150, 1040, 60)
    _txt(by["gameTitle"], 40, DIM, 2, 6)
    _put(by["titleUnderline"], SLOT_X, 330, W - 2 * SLOT_X + 60, 10)
    by["titleUnderline"]["color.a"] = 150
    for n in ("hintSelectText", "hintBackText"):
        by[n]["faceId"] = "Default"
    _save(wdir, "loadout-root", w)
    return 1


def _slot_row(wdir):
    """to1/loadout-slot: the slot row of the edit page, B2: icon left, small label over the name, LP at the right edge."""
    w = _load(wdir, "loadout-slot")
    by = {i["name"]: i for i in w["items"]}
    if by["label0"].get("faceId") == "Default":
        return 0
    by["weaponIcon"].update({"pivotAs.x": 24.0, "rectSizeDelta.width": 220.0, "rectSizeDelta.height": 96.0})
    for n, y, h, pt, rw in (("label0", 24.0, 44.0, 28, 200.0), ("weaponName", 56.0, 100.0, 30, 30.0)):
        it = by[n]
        it.update({"pivotAs.x": 270.0, "pivotAs.y": y, "anchorMaxN.x": 1.0, "rectSizeDelta.width": -(270.0 + rw), "rectSizeDelta.height": h})
        _txt(it, pt, None, 0, 3 if n == "label0" else 1)
    _col(by["label0"], DIM)
    by["slotCost"].update({"pointSize": 40, "pivotAs.x": -30.0, "pivotAs.y": -46.0})      # cost at the right end of the label line
    by["cardBg"]["color.a"] = 110
    _save(wdir, "loadout-slot", w)
    return 1


TILE, TILE_GAP, TILE_X = 240, 30, 130          # level / variant tiles in the details panel (x of the stat bars)
TILE_Y = 1135                                  # under the 4 stat bars (the last bar row ends ~1115); t2r-ext moves them with the stat block (detail_stats_shift)
PANEL_H = 1520                                 # details panel height (was 1370): room for the tiles + the A / D hint under them


def _tiles(by, skill):
    """Level / variant selector: two (guns: loud / quiet) or three (skills: level 1 / 2 / 3) large square tiles under the stat bars,
    left-aligned with them, small gap, selected = framed (the frame widgets t2r-ext already shows), the hint under them.
    Guns reuse the page's lvl* widgets (lvlBg / lvlFrame / lvlIcon / lvlCost / lvlCostR, lvlHint), skills the skLvl* ones."""
    pre = "skLvl" if skill else "lvl"
    n = 3 if skill else 2
    if f"{pre}Bg0" not in by:                  # the page has no level boxes (picker-purchase)
        return
    for k in range(n):
        x = TILE_X + k * (TILE + TILE_GAP)
        _put(by[f"{pre}Bg{k}"], x, TILE_Y, TILE, TILE)
        by[f"{pre}Bg{k}"]["color.a"] = 60
        _put(by[f"{pre}Frame{k}"], x, TILE_Y, TILE, TILE)
        by[f"{pre}Frame{k}"]["lineWidth"] = 6.0
        if skill:
            _put(by[f"skLvlNum{k}"], x, TILE_Y + 10, TILE, TILE - 60)
            by[f"skLvlNum{k}"]["text"] = str(k + 1)
            _txt(by[f"skLvlNum{k}"], 130, PM_TEXT, 1, 0)
        else:
            _put(by[f"lvlIcon{k}"], x + 20, TILE_Y + 24, TILE - 40, TILE - 100)
        for suf in ("", "R"):
            it = by[f"{pre}Cost{suf}{k}"]
            _put(it, x + TILE - 190, TILE_Y + TILE - 66, 170, 52)     # "N LP" (t2r-ext lo_cost_str; FREE at 0): the cost of THAT variant, never a bare number
            _txt(it, 40, None, 2, 0)
    hint = by["skLvlHint" if skill else "lvlHint"]
    _put(hint, TILE_X, TILE_Y + TILE + 10, 1000, 50)
    _txt(hint, 36, PM_TEXT, 0, 3)


def _grit_item(b, anim_guid):
    if os.environ.get("T2R_LOADOUT_R2_GRIT", "1") == "0":
        return None
    return b.image("loGrit", anim_guid, b.bleed(), GRIT, 0xFFFFFFFF, 255, depth=-20.0)


def _lines(b, anim_guid, head_rules, dividers):
    g = b.group("loLines", anim_guid, b.tl(0, 0, W, H), depth=1.0)["guid"]
    for k, (x0, x1) in enumerate(head_rules):
        b.line(f"loHeadRule{k}", g, x0, HEAD_Y + 100, x1, HEAD_Y + 100, 0xFFD8D3C6, 150, 4.0)
    for k, x in enumerate(dividers):
        b.line(f"loDiv{k}", g, x, HEAD_Y - 20, x, 1960, 0xFFD8D3C6, 70, 3.0)


def _mirror(b, anim_guid):
    """Slot column of the picker pages: static widgets, filled by t2r-ext (r2_mirror_fill)."""
    g = b.group("loMirror", anim_guid, b.tl(SLOT_X, Y0, SLOT_W, MIRROR_ROWS * SLOT_PITCH), depth=2.0)["guid"]
    for i in range(MIRROR_ROWS):
        y = i * SLOT_PITCH
        b.rect(f"loSl{i}Bg", g, b.tl(0, y, SLOT_W, SLOT_H), 0xFF000000, 110)
        b.image(f"loSl{i}Ic", g, b.tl(24, y + 32, 220, 96), "hud/weapon-cross/empty-slot.png", 0xFFFFFFFF, 255,
                scaleMode="StretchAspect", alignH=1, alignV=1)
        b.text(f"loSl{i}Lb", g, b.tl(270, y + 24, SLOT_W - 270 - 200, 44), "", 28, DIM, tracking=3)
        b.text(f"loSl{i}Nm", g, b.tl(270, y + 56, SLOT_W - 270 - 30, 100), "", 30, PM_TEXT, tracking=1, multiline=1)
        b.text(f"loSl{i}Co", g, b.tl(SLOT_W - 230, y + 14, 200, 60), "", 40, BLUE, align=2)
        b.frame(f"loSl{i}Fr", g, b.tl(0, y, SLOT_W, SLOT_H), 0xFFD8D3C6, 0, 4.0)       # alpha 255 on the slot being picked


def _page(wdir, name, kind, T):
    """kind: edit | picker | skill.  Returns the number of widgets added."""
    w = _load(wdir, name)
    items = w["items"]
    by = {i["name"]: i for i in items}
    if "loLines" in by:
        return 0
    anim = by["anim-group"]
    b = Builder(T)
    _hide(by, "panelBlur", "panelBg", "panelLineTop", "panelLineBottom", "detailShade", "detailBlur", "detailBg", "detailLineTop", "detailLineBottom")
    _put(by["lpTotal"], W - 220 - 760, HEAD_Y, 760, 100)
    _txt(by["lpTotal"], COL_PT, BLUE, 2, 2)
    by["lpTotal"]["alignV"] = 1
    if kind == "edit":
        by["slotList"].update({"pivotAs.x": float(SLOT_X), "rectSizeDelta.width": float(SLOT_W)})
        _put(by["loadoutName"], SLOT_X, HEAD_Y, SLOT_W, 100)
        _txt(by["loadoutName"], COL_PT, PM_TEXT, 0, 3)
        by["loadoutName"]["alignV"] = 1
        _lines(b, anim["guid"], [(SLOT_X, SLOT_X + SLOT_W)], [SLOT_X + SLOT_W + 50])
    else:
        _put(by["pickerTitle"], LIST_X, HEAD_Y, 1100, 100)
        _txt(by["pickerTitle"], COL_PT, PM_TEXT, 0, 3)
        by["pickerTitle"]["alignV"] = 1
        if kind == "skill":
            by["list"].update({"pivotAs.x": float(LIST_X), "rectSizeDelta.width": float(LIST_W)})
        else:
            for n in ("pickerList", "rowDeco"):
                by[n].update({"pivotAs.x": float(LIST_X), "rectSizeDelta.width": float(LIST_W)})
            for i in items:
                if i["name"].startswith("cost") and i["name"][4:].isdigit():
                    i["pivotAs.x"] = float(COST_X)
        if "scrollBar" in by:
            by["scrollBar"]["pivotAs.x"] = float(SCROLL_X)
        dp = by["detailPanel"]
        dp["rectSizeDelta.height"] = float(PANEL_H)
        panel_items = {i["name"]: i for i in items if i.get("parent") == dp["guid"]}
        _tiles(panel_items, kind == "skill")
        _lines(b, anim["guid"], [(SLOT_X, SLOT_X + SLOT_W), (LIST_X, W - 220)], [SLOT_X + SLOT_W + 50, 2450])
        _mirror(b, anim["guid"])
        by["lpTotal"]["depth"] = 8.0
    grit = _grit_item(b, anim["guid"])
    if grit is not None:
        b.items.remove(grit)
    at = next(k for k, i in enumerate(items) if i["name"] == "lpTotal")
    items[at:at] = b.items
    # the ground goes right after anim-group, ahead of every child: the engine sorts by depth only while a page fades; at rest it draws
    # in list order, so a ground inserted before lpTotal covered the header, lists and footer the moment the fade ended
    if grit is not None:
        items.insert(next(k for k, i in enumerate(items) if i is anim) + 1, grit)
    _save(wdir, name, w)
    return len(b.items)


def _edit_details(wdir):
    """The edit page had no DETAILS panel (B2 "list" preview): a copy of the weapon picker's panel (already restyled), hidden until t2r-ext
    (skills.c r2_edit_detail) fills it for the focused slot row; it sits right beside the slot column, where the picker pages have their list."""
    name = "loadout-menu"
    w = _load(wdir, name)
    items = w["items"]
    if any(i["name"] == "detailPanel" for i in items):
        return 0
    pp = _load(wdir, "picker-primary")
    byg = {i["guid"]: i for i in pp["items"]}
    top = next(i for i in pp["items"] if i["name"] == "detailPanel")

    def under(i):
        while i is not None and i is not top:
            i = byg.get(i.get("parent"))
        return i is top
    sub = [i for i in pp["items"] if under(i)]
    anim = next(i for i in items if i["name"] == "anim-group")
    remap = {i["guid"]: t2guid.guid() for i in sub}
    new = []
    for i in sub:
        c = copy.deepcopy(i)
        c["guid"] = remap[i["guid"]]
        c["parent"] = anim["guid"] if i is top else remap.get(i.get("parent"), i.get("parent"))
        if c["name"].startswith(("lvl", "skLvl")):
            c["visible"] = 0
        if c["name"] == "detailPanel":
            c["visible"] = 0
            c["pivotAs.x"] = -float(W - (LIST_X + 1180))
        new.append(c)
    at = next(k for k, i in enumerate(items) if i["name"] == "lpTotal")
    items[at:at] = new
    _save(wdir, name, w)
    return len(new)


def _picker_row(wdir):
    """Picker list rows (picker-row template, a fixed 1400 wide root): the name box ends 20 before the cost column (COST_X; shade_widgets had it at
    0.72 = 1008, which reaches into the cost text of the longest Polish names), so those wrap to two lines instead (final2 preview)."""
    w = _load(wdir, "picker-row")
    for i in w["items"]:
        if i["name"] == "label0":
            r = round((COST_X - 20) / 1400.0, 3)
            if i.get("anchorMaxN.x") != r:
                i["anchorMaxN.x"] = r
                i["pointSize"] = 36
                _save(wdir, "picker-row", w)
                return 1
    return 0


def apply(wdir):
    """Restyle the gear up pages in the extracted widget dir (after the details panel / skill UI / scroll tracks / shades are in). Returns widgets added + pages edited."""
    main = _load(wdir, "main-menu")
    T, _, _ = _templates(main)
    for c in T.values():
        for k in ("engineClass", "tags", "animationsPath"):
            c.pop(k, None)
    n = _chrome(wdir) + _slot_row(wdir) + _picker_row(wdir)
    n += _page(wdir, "loadout-menu", "edit", T)
    for p in PICKERS:
        n += _page(wdir, p, "picker", T)
    n += _page(wdir, "picker-skill", "skill", T)
    n += _edit_details(wdir)
    return n
