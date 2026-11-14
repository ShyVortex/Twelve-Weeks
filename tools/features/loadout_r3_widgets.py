"""GEAR UP rework (approved mockups tools/features/gearup_mock.py, gearup-mockups/*-v3.png): the launcher's loadout layout on one strict grid.

Canvas 3840 x 2160 (the mockups are 1920 x 1080: every number here is the mockup's x 2).

    header rule y 300 and footer rule y 1980 run 220..3620 (the only full-width lines)
    column dividers x 1240 and 2340 run exactly header rule -> footer rule
    columns   A 220..1160 (slots / loadout list)   B 1320..2260 (options / gear)   D 2420..3620 (details)
    column heading box y 360..430, one column rule at y 456 spanning the column, first row at y 500, rows 88 tall on a 100 pitch
    type: title 66 pt, heading 33, row 26, body 23, small 20; colours TEXT / DIM / FAINT + ACCENT (the launcher palette)

Pages (to1/): loadout-root (chrome, referenced by every page), loadout-menu (edit), picker-primary / -secondary / -purchase (weapon pickers),
picker-skill (loadout list AND skill picker - t2r-ext moves the list between columns A and B).  Rows use OWN templates (to1/t3-row,
to1/t3-skill-row, to1/t3-slot) - picker-row is shared with the in-match backpack.  Row focus fades over 0.25 s (the launcher's transition).

Ground: blur-background + 78 % black + fine grain, twice - inside anim-group (fades with the page: entering / leaving gear up is the page's own fade)
and at the page root as t3Root (outside the fade, hidden in the template): t2r-ext shows it for 400 ms when one gear up page replaces another, so the
cross-fade never shows the world through (r2_grit_tick).  The page fade is our own animation file (to1/t3-page-anim: fade + a 24-unit rise).

t2r-ext detects this layout by the widget anim-group.t3Lines.  Opt-out: T2R_LOADOUT_R3=0 (then T2R_LOADOUT_R2 decides)."""
import copy
import json
import os

import t2guid
from clan_widgets import Builder, _templates
from pause_restyle_widgets import _col, _put

W, H = 3840, 2160
TEXT, DIM, FAINT, ACCENT = 0xFFE6DFCF, 0xFFA8A292, 0xFF6F6B60, 0xFF8EC3EA
LINE, LINE_A, RULE_A = 0xFFDCDCD6, 46, 30          # rules / dividers, row separators
M0, M1 = 220, 3620
HEAD_RULE, FOOT_RULE = 300, 1980
A0, A1, B0, B1, D0, D1 = 220, 1160, 1320, 2260, 2420, 3620
DIV = (1240, 2340)
HEAD_Y, HEAD_H, COL_RULE = 360, 70, 456
ROW0, PITCH, ROWH = 500, 100, 88
COL_W = A1 - A0                                      # 940: A and B are the same width, a list moves between them by its x only
PT_TITLE, PT_HEAD, PT_ROW, PT_BODY, PT_SMALL = 66, 33, 26, 23, 20
ICON_X, ICON_Y, ICON_W, ICON_H, NAME_X = 16, 10, 128, 68, 160
GRAIN = "streaming/t2r/clan/r2-grain.png"           # ship.py ui_r2_common.grain (alpha 11)
BLUR = "general-textures/blur-background.png"
DARK_A = 198                                         # the mockup's x 0.22 brightness over the blurred world
SLOT_Y = (0, 100, 220, 320, 420, 520, 640)           # the 7 slot rows: guns | 4 skills | purchasable, a 20 gap at each group edge
SLOT_GAPS = (204, 624)                               # y (from the first row) of the group rules, centred in those gaps
PICKERS = ("picker-primary", "picker-secondary", "picker-purchase")
PICK_TITLE = {"picker-primary": "LARGE FIREARM", "picker-secondary": "SMALL FIREARM", "picker-purchase": "PURCHASABLE"}
PICK_ROWS = {"picker-primary": 10, "picker-secondary": 6, "picker-purchase": 12}
PREV_ROWS = 14                                       # rows of the edit page's option preview (column B)
PILL_H, PILL_Y = 44, 22
GUN_PILL_W, SK_PILL_W, PILL_GAP, PILL_R = 150, 112, 12, 24     # pills right-aligned 24 in from the row's end
FADE_S = 0.25


def _load(wdir, name):
    return json.load(open(os.path.join(wdir, "to1", name + ".widget.json"), encoding="utf-8"))


def _save(wdir, name, w):
    json.dump(w, open(os.path.join(wdir, "to1", name + ".widget.json"), "w", encoding="utf-8"), indent=4)


def _txt(it, pt, argb, align=0, tracking=1.0, valign=1):
    it.update({"pointSize": pt, "faceId": "Default", "alignH": align, "alignV": valign, "tracking.x": float(tracking)})
    _col(it, argb)


def _hide(by, *names):
    for n in names:
        if n in by:
            by[n]["visible"] = 0


# ------------------------------------------------------------------ focus animation (launcher: color / background / border .25 s)
def _focus_labels():
    return {"labels": [
        {"label": "normal", "loop": 0, "range": [0.0, 0.0], "rate": 1.0, "revCurve": 0},
        {"label": "focused", "loop": 0, "range": [FADE_S, FADE_S], "rate": 1.0, "revCurve": 0},
        {"label": "normal^focused", "loop": 0, "range": [0.0, FADE_S], "rate": 1.0, "revCurve": 0},
        {"label": "focused^normal", "loop": 0, "range": [FADE_S, 0.0], "rate": 1.0, "revCurve": 0}]}


def _kf_float(prop, off, on):
    return {"keyframes": {prop: {"type": "float", "keys": [0.0, FADE_S], "values": [float(off), float(on)],
                                 "curveTypes": ["EaseInOut2", "EaseInOut2"]}}}


def _kf_tint(off, on):
    return {"keyframes": {"tint": {"type": "QColor", "keys": [0.0, FADE_S], "values": [off, on], "curveTypes": ["EaseInOut2", "EaseInOut2"]}}}


def _row_look(by, name_key, cost_key=None):
    """Shared row look: hover fill 0 -> 5 % white, a 1-unit... (2 canvas) cream frame 0 -> 210, name DIM -> TEXT, all over FADE_S."""
    bg = by["cardBg"]
    bg.update({"path": "general-textures/square-32px.png", "scaleMode": "Stretch"})
    _col(bg, 0xFFFFFFFF, 0)
    bg["animation"] = _kf_float("fcolor.a", 0, 13 / 255)        # keyframe alpha is 0..1 (13 clamped to a pure white row)
    fr = by["focusFrame"]
    _col(fr, TEXT, 0)
    fr["lineWidth"] = 2.0
    fr["animation"] = _kf_float("fcolor.a", 0, 210 / 255)
    nm = by[name_key]
    nm["animation"] = _kf_tint(DIM, TEXT)
    if cost_key:
        _txt(by[cost_key], PT_SMALL, DIM, 2, 1.5)
    if "cardLine" in by:
        by["cardLine"]["visible"] = 0


def _pills(b, parent, prefix, n, w, row_w, y0=0):
    """n pills right-aligned in a row of width row_w, k = 0 leftmost: <prefix><k>Bg (fill, alpha 0), Fr (FAINT frame), FrOn (TEXT frame, alpha 0),
    Tx (TEXT colour; t2r-ext dims it by alpha). All hidden until t2r-ext shows them (r3_pill). The chosen pill = Bg (8 %) + FrOn instead of Fr
    (the launcher's .lv.on)."""
    for k in range(n):
        x = row_w - PILL_R - (n - k) * w - (n - 1 - k) * PILL_GAP
        b.rect(f"{prefix}{k}Bg", parent, b.tl(x, y0 + PILL_Y, w, PILL_H), 0xFFFFFFFF, 20, visible=0)
        b.frame(f"{prefix}{k}Fr", parent, b.tl(x, y0 + PILL_Y, w, PILL_H), FAINT, 140, 2.0, visible=0)
        b.frame(f"{prefix}{k}FrOn", parent, b.tl(x, y0 + PILL_Y, w, PILL_H), TEXT, 230, 2.0, visible=0)
        b.text(f"{prefix}{k}Tx", parent, b.tl(x, y0 + PILL_Y, w, PILL_H), "", PT_SMALL, TEXT, align=1, tracking=1.0, visible=0)


def _template(wdir, src, dst, rowfn):
    w = _load(wdir, src)
    # fresh guids (parents remapped) so the copy is its own widget
    remap = {i["guid"]: t2guid.guid() for i in w["items"]}
    for i in w["items"]:
        i["guid"] = remap[i["guid"]]
        if i.get("parent") in remap:
            i["parent"] = remap[i["parent"]]
    w["animation"] = _focus_labels()
    rowfn(w)
    _save(wdir, dst, w)


def _t3_row(T):
    """to1/t3-row (weapon pickers): name + focus look; icons / costs / pills live in the page's rowDeco (t2r-ext fills them)."""
    def fn(w):
        by = {i["name"]: i for i in w["items"]}
        by["root"].update({"rectSizeDelta.width": float(COL_W), "rectSizeDelta.height": float(ROWH)})
        _row_look(by, "label0")
        lb = by["label0"]
        lb.update({"pivotAs.x": float(NAME_X), "anchorMaxN.x": 0.62})
        _txt(lb, PT_ROW, DIM, 0, 1.5)
        lb["animation"] = _kf_tint(DIM, TEXT)
        _hide(by, "selectedMark")
    return fn


def _t3_skill_row(T):
    """to1/t3-skill-row (picker-skill: the loadout list and the skill picker): icon, name (skill mode), t3Lbl (list mode, no icon), end text,
    3 level pills, the rule under the row (t3Rule; t2r-ext hides it on the last row and in list mode)."""
    def fn(w):
        items = w["items"]
        by = {i["name"]: i for i in items}
        by["root"].update({"rectSizeDelta.width": float(COL_W), "rectSizeDelta.height": float(ROWH)})
        _row_look(by, "label0", "costText")
        ic = by["skillIcon"]
        ic.update({"pivotAs.x": float(ICON_X + (ICON_W - ICON_H) / 2), "pivotAs.y": float(ICON_Y), "rectSizeDelta.width": float(ICON_H),
                   "rectSizeDelta.height": float(ICON_H), "anchorMinN.y": 0.0, "anchorMaxN.y": 0.0, "pivotN.y": 0.0})
        lb = by["label0"]
        lb.update({"pivotAs.x": float(NAME_X), "anchorMaxN.x": 0.62})
        _txt(lb, PT_ROW, DIM, 0, 1.5)
        lb["animation"] = _kf_tint(DIM, TEXT)
        ct = by["costText"]
        ct.update({"pivotAs.x": -float(PILL_R), "rectSizeDelta.width": 300.0})
        b = Builder(T)
        root = by["root"]["guid"]
        t = b.text("t3Lbl", root, b.tl(28, 0, COL_W - 28 - 260, ROWH), "", PT_ROW, DIM, tracking=1.5)
        t["animation"] = _kf_tint(DIM, TEXT)
        _pills(b, root, "t3Pl", 3, SK_PILL_W, COL_W)
        b.line("t3Rule", root, 0, ROWH + 6, COL_W, ROWH + 6, LINE, RULE_A, 2.0)
        for i in b.items:
            i["depth"] = 10.0 + i["depth"]
        items += b.items
    return fn


def _t3_slot(T):
    """to1/t3-slot (edit page slot rows): icon, name, LP; no slot label (the mockups have none), no shimmer."""
    def fn(w):
        by = {i["name"]: i for i in w["items"]}
        by["root"].update({"rectSizeDelta.width": float(COL_W), "rectSizeDelta.height": float(ROWH)})
        _row_look(by, "weaponName", "slotCost")
        ic = by["weaponIcon"]
        ic.update({"pivotAs.x": float(ICON_X), "pivotAs.y": float(ICON_Y), "rectSizeDelta.width": float(ICON_W), "rectSizeDelta.height": float(ICON_H),
                   "anchorMinN.y": 0.0, "anchorMaxN.y": 0.0, "pivotN.y": 0.0})
        nm = by["weaponName"]
        nm.update({"pivotAs.x": float(NAME_X), "pivotAs.y": 0.0, "rectSizeDelta.height": 0.0, "anchorMinN.y": 0.0, "anchorMaxN.y": 1.0,
                   "pivotN.y": 0.0, "anchorMaxN.x": 0.75, "multiline": 0})
        _txt(nm, PT_ROW, DIM, 0, 1.5)
        nm["animation"] = _kf_tint(DIM, TEXT)
        sc = by["slotCost"]
        sc.update({"pivotAs.x": -float(PILL_R), "anchorMinN.x": 0.7})
        _hide(by, "label0", "shimmerGrp")
    return fn


def _page_anim(wdir):
    """to1/t3-page-anim: container-fade-depth1-nofade's labels with the same alpha keys, plus a 24-unit rise into place (launcher 'fadeup')."""
    src = os.path.join(wdir, "menu", "animations", "container-fade-depth1-nofade.widget.json")
    w = json.load(open(src, encoding="utf-8"))
    for i in w["items"]:
        if i["name"] == "anim-group":
            kf = i["animation"]["keyframes"]
            keys = kf["fcolor.a"]["keys"]
            vals = kf["fcolor.a"]["values"]
            kf["pivotAs.y"] = {"type": "float", "keys": list(keys), "values": [0.0 if v >= 1.0 else 24.0 for v in vals],
                               "curveTypes": ["EaseInOut2"] * len(keys)}
    json.dump(w, open(os.path.join(wdir, "to1", "t3-page-anim.widget.json"), "w", encoding="utf-8"), indent=4)


# ------------------------------------------------------------------ shared page parts
def _ground(b, parent, prefix):
    b.image(prefix + "Blur", parent, b.bleed(), BLUR, 0xFFFFFFFF, 255)
    b.rect(prefix + "Dark", parent, b.bleed(), 0xFF000000, DARK_A)
    b.image(prefix + "Grain", parent, b.bleed(), GRAIN, 0xFFFFFFFF, 255)


def _lines(b, anim, heads):
    """Dividers (header rule -> footer rule) and one rule under each column heading; heads = [(x0, x1), ...]."""
    g = b.group("t3Lines", anim, b.tl(0, 0, W, H))["guid"]
    for k, x in enumerate(DIV):
        b.line(f"t3Div{k}", g, x, HEAD_RULE, x, FOOT_RULE, LINE, LINE_A, 2.0)
    for k, (x0, x1) in enumerate(heads):
        b.line(f"t3Col{k}", g, x0, COL_RULE, x1, COL_RULE, LINE, LINE_A, 2.0)
    return g


def _heading(it, x0, x1, text=None):
    _put(it, x0, HEAD_Y, x1 - x0, HEAD_H)
    _txt(it, PT_HEAD, TEXT, 0, 2.0)
    it["visible"] = 1
    if text is not None:
        it["text"] = text


def _lp_total(it):
    _put(it, D0, 174, D1 - D0, 70)
    _txt(it, PT_HEAD, ACCENT, 2, 2.0)
    it["depth"] = 8.0


def _mirror(b, anim, x0):
    """Slot column on the pickers / gear column on the list page: 7 static rows (icon, name, LP, hover fill, frame), filled by t2r-ext."""
    g = b.group("loMirror", anim, b.tl(x0, ROW0, COL_W, SLOT_Y[-1] + ROWH), depth=2.0)["guid"]
    for k, y in enumerate(SLOT_GAPS):
        b.line(f"loGap{k}", g, 0, y, COL_W, y, LINE, LINE_A, 2.0)
    for i, y in enumerate(SLOT_Y):
        b.rect(f"loSl{i}Bg", g, b.tl(0, y, COL_W, ROWH), 0xFFFFFFFF, 0)
        b.frame(f"loSl{i}Fr", g, b.tl(0, y, COL_W, ROWH), TEXT, 0, 2.0)
        b.image(f"loSl{i}Ic", g, b.tl(ICON_X, y + ICON_Y, ICON_W, ICON_H), "hud/weapon-cross/empty-slot.png", 0xFFFFFFFF, 255,
                scaleMode="StretchAspect", alignH=1, alignV=1)
        b.text(f"loSl{i}Nm", g, b.tl(NAME_X, y, COL_W - NAME_X - 200, ROWH), "", PT_ROW, TEXT, tracking=1.5)     # t2r-ext dims by alpha
        b.text(f"loSl{i}Co", g, b.tl(COL_W - PILL_R - 200, y, 200, ROWH), "", PT_SMALL, DIM, align=2, tracking=1.5)


def _detail(by, items, b, panel, kind):
    """The DETAILS panel moved to column D and restyled; kind gun | skill | purch | list. New: t3Lv<k>Ro / Tx / Co (level / variant lines) + t3LvMark."""
    dp = by[panel]
    _put(dp, D0, HEAD_Y, D1 - D0, FOOT_RULE - HEAD_Y)
    dp["rectSizeDelta.height"] = float(FOOT_RULE - HEAD_Y)
    sub = {i["name"]: i for i in items if i.get("parent") == dp["guid"]}
    _hide(sub, "detailShade", "detailBlur", "detailBg", "detailLineTop", "detailLineBottom", "detailDivider", "lvlLine", "lvlHint", "skLvlHint",
          "detailHeaderLine")
    for n, it in sub.items():
        if n.startswith(("lvlBg", "lvlFrame", "lvlIcon", "lvlCost", "skLvlBg", "skLvlFrame", "skLvlNum", "skLvlCost")):
            it["visible"] = 0
    if "detailHeader" in sub:
        _put(sub["detailHeader"], 0, 0, D1 - D0, HEAD_H)
        _txt(sub["detailHeader"], PT_HEAD, TEXT, 0, 2.0)
        sub["detailHeader"].update({"visible": 1, "text": "DETAILS"})
    W_D = D1 - D0
    _put(sub["perkName"], 0, 156, W_D - 360, 76)
    _txt(sub["perkName"], PT_HEAD, TEXT, 0, 2.0)
    _put(sub["perkCost"], W_D - 360, 156, 360, 76)
    _txt(sub["perkCost"], PT_HEAD, ACCENT, 2, 2.0)
    ic = sub["perkIcon"]
    _put(ic, 0, 252, 600, 180)                          # guns are wide, skills square: StretchAspect, left aligned
    ic.update({"scaleMode": "StretchAspect", "alignH": 0, "alignV": 1})
    _put(sub["perkDesc"], 0, 470, W_D, 200)
    _txt(sub["perkDesc"], PT_BODY, DIM, 0, 0.0, valign=0)
    sub["perkDesc"]["multiline"] = 1
    sub["perkDesc"]["color.a"] = 255
    for s in range(4):                                  # t2r-ext places the stat block under the variant lines (r3_stats_place)
        n = f"statLabel{s}"
        if n in sub:
            _put(sub[n], 0, 1100 + 92 * s, 600, 40)
            _txt(sub[n], PT_SMALL, DIM, 0, 1.5)
        for k in range(10):
            for pre in ("statE", "statF"):
                m = f"{pre}{s}_{k}"
                if m in sub:
                    _put(sub[m], 92 * k, 1146 + 92 * s, 84, 12)
                    if pre == "statE":
                        _col(sub[m], 0xFFFFFFFF, 30)
                    else:
                        _col(sub[m], TEXT, 225)
    g = dp["guid"]
    b.rect("t3LvMark", g, b.tl(-28, 700, 6, 48), ACCENT, 255, visible=0)
    for k in range(3):
        y = 700 + 130 * k
        b.text(f"t3Lv{k}Ro", g, b.tl(0, y, 120, 48), "", PT_BODY, TEXT, tracking=1.0, valign=0, visible=0)
        b.text(f"t3Lv{k}Tx", g, b.tl(140, y, W_D - 140 - 150, 120), "", PT_BODY, TEXT, multiline=1, valign=0, visible=0)
        b.text(f"t3Lv{k}Co", g, b.tl(W_D - 150, y, 150, 48), "", PT_BODY, TEXT, align=2, tracking=1.0, valign=0, visible=0)


def _strip_old(by):
    _hide(by, "panelBlur", "panelBg", "panelLineTop", "panelLineBottom")


def _insert(items, anim, b, before="lpTotal"):
    at = next(k for k, i in enumerate(items) if i["name"] == before)
    items[at:at] = [i for i in b.items if i.get("_root") is None]


def _root_ground(items, b_items, root_guid, anim):
    """t3Root (outside anim-group, alpha 0): inserted right after the page root so it draws first."""
    at = next(k for k, i in enumerate(items) if i is anim)
    items[at:at] = b_items


def _page_common(wdir, name, kind, T):
    w = _load(wdir, name)
    items = w["items"]
    by = {i["name"]: i for i in items}
    if "t3Lines" in by:
        return 0
    anim, root = by["anim-group"], by["root"]
    anim["animationsPath"] = "to1/t3-page-anim.widget"
    rb = Builder(T)                                            # root-level ground (t3Root)
    rg = rb.group("t3Root", root["guid"], rb.tl(0, 0, W, H), visible=0)     # shown by t2r-ext for 400 ms after a gear up page replaced another
    _ground(rb, rg["guid"], "t3R")
    _root_ground(items, rb.items, root["guid"], anim)
    b = Builder(T)
    _strip_old(by)
    _lp_total(by["lpTotal"])
    return w, items, by, anim, b


def _edit_page(wdir, T):
    r = _page_common(wdir, "loadout-menu", "edit", T)
    if not r:
        return 0
    w, items, by, anim, b = r
    sl = by["slotList"]
    _put(sl, A0, ROW0, COL_W, SLOT_Y[-1] + ROWH)
    order = ("PrimaryWeapon", "SecondaryWeapon", "SkillOne", "SkillTwo", "SkillThree", "SkillFour", "Purchasable1")
    for k, n in enumerate(order):
        it = by[n]
        it.update({"pivotAs.y": float(SLOT_Y[k]), "rectSizeDelta.height": float(ROWH), "source": "to1/t3-slot.widget"})
    _heading(by["loadoutName"], A0, A1, "EQUIPPED")
    g = _lines(b, anim["guid"], [(A0, A1), (B0, B1), (D0, D1)])
    for k, y in enumerate(SLOT_GAPS):
        b.line(f"t3SlotGap{k}", g, A0, ROW0 + y, A1, ROW0 + y, LINE, LINE_A, 2.0)
    # column B: the focused slot's options, dimmed (t2r-ext r3_preview_fill)
    pv = b.group("t3Prev", anim["guid"], b.tl(B0, 0, COL_W, H))["guid"]
    b.text("t3PrevHead", pv, b.tl(0, HEAD_Y, COL_W, HEAD_H), "", PT_HEAD, TEXT, tracking=2.0)
    for k in range(PREV_ROWS):
        y = ROW0 + PITCH * k
        if k:
            b.line(f"t3Pv{k}Rule", pv, 0, y - 6, COL_W, y - 6, LINE, RULE_A, 2.0)
        b.image(f"t3Pv{k}Ic", pv, b.tl(ICON_X, y + ICON_Y, ICON_W, ICON_H), "hud/weapon-cross/empty-slot.png", 0xFFFFFFFF, 255,
                scaleMode="StretchAspect", alignH=1, alignV=1, visible=0)
        b.text(f"t3Pv{k}Nm", pv, b.tl(NAME_X, y, COL_W - NAME_X - 340, ROWH), "", PT_ROW, TEXT, tracking=1.5)     # t2r-ext: equipped 1, others .45
        b.text(f"t3Pv{k}Co", pv, b.tl(COL_W - PILL_R - 300, y, 300, ROWH), "", PT_SMALL, DIM, align=2, tracking=1.5)
        _pills(b, pv, f"t3Pv{k}P", 3, SK_PILL_W, COL_W, y)
    _insert(items, anim, b)
    _save(wdir, "loadout-menu", w)
    return len(b.items)


def _picker_page(wdir, name, T):
    r = _page_common(wdir, name, "gun", T)
    if not r:
        return 0
    w, items, by, anim, b = r
    _heading(by["pickerTitle"], B0, B1, PICK_TITLE[name])
    n = PICK_ROWS[name]
    for nm in ("pickerList", "rowDeco"):
        _put(by[nm], B0, ROW0, COL_W, PITCH * n)
    by["pickerList"]["flowSpacing"] = float(PITCH - ROWH)       # TopDown flow: the stock 28 put the rows at 116 while rowDeco's icons / pills sit at PITCH
    deco = by["rowDeco"]["guid"]
    for i in items:
        nm = i["name"]
        if nm.startswith("Item") and nm[4:].isdigit():
            k = int(nm[4:])
            i.update({"pivotAs.y": float(PITCH * k), "rectSizeDelta.height": float(ROWH), "source": "to1/t3-row.widget"})
        elif nm.startswith("icon") and nm[4:].isdigit() and i.get("parent") == deco:
            k = int(nm[4:])
            _put(i, ICON_X, PITCH * k + ICON_Y, ICON_W, ICON_H)
            i.update({"scaleMode": "StretchAspect", "alignH": 1, "alignV": 1})
        elif nm.startswith("cost") and nm[4:].isdigit() and i.get("parent") == deco:
            k = int(nm[4:])
            _put(i, COL_W - PILL_R - 300, PITCH * k, 300, ROWH)
            _txt(i, PT_SMALL, DIM, 2, 1.5)
    for k in range(n):
        if k < n - 1:
            b.line(f"t3Rule{k}", deco, 0, PITCH * k + ROWH + 6, COL_W, PITCH * k + ROWH + 6, LINE, RULE_A, 2.0)
        _pills(b, deco, f"t3P{k}_", 2, GUN_PILL_W, COL_W, PITCH * k)
    if "scrollBar" in by:
        _put(by["scrollBar"], B1 + 30, ROW0, 6, PITCH * 14 - 12)
    _lines(b, anim["guid"], [(A0, A1), (B0, B1), (D0, D1)])
    b.text("t3HeadA", anim["guid"], b.tl(A0, HEAD_Y, COL_W, HEAD_H), "EQUIPPED", PT_HEAD, TEXT, tracking=2.0)
    _mirror(b, anim["guid"], A0)
    _detail(by, items, b, "detailPanel", "purch" if name == "picker-purchase" else "gun")
    _insert(items, anim, b)
    _save(wdir, name, w)
    return len(b.items)


def _skill_page(wdir, T):
    r = _page_common(wdir, "picker-skill", "skill", T)
    if not r:
        return 0
    w, items, by, anim, b = r
    # template = list mode (GEAR UP's first page): LOADOUTS (the list) in column A | GEAR (loMirror) in column B. The skill picker moves the
    # list to B and the mirror to A (t2r-ext r3_skill_cols: x only - the columns are the same width) and renames the headings.
    _heading(by["pickerTitle"], B0, B1, "GEAR")
    lst = by["list"]
    top = by["contents"]["pivotAs.y"]                      # the scroll container's own top band: the first row lands at ROW0
    _put(lst, A0, ROW0 - top, COL_W, PITCH * 14 + top)
    by["contents"]["flowSpacing"] = float(PITCH - ROWH)
    for i in items:
        if i["name"].startswith("Skill") and i["name"][5:].isdigit():
            k = int(i["name"][5:])
            i.update({"pivotAs.y": float(PITCH * k), "rectSizeDelta.height": float(ROWH), "source": "to1/t3-skill-row.widget"})
    if "scrollBar" in by:
        _put(by["scrollBar"], B1 + 30, ROW0, 6, PITCH * 14 - 12)
    _lines(b, anim["guid"], [(A0, A1), (B0, B1), (D0, D1)])
    b.text("t3HeadA", anim["guid"], b.tl(A0, HEAD_Y, COL_W, HEAD_H), "LOADOUTS", PT_HEAD, TEXT, tracking=2.0)
    _mirror(b, anim["guid"], B0)
    _detail(by, items, b, "detailPanel", "skill")
    _insert(items, anim, b)
    _save(wdir, "picker-skill", w)
    return len(b.items)


def _chrome(wdir, T):
    w = _load(wdir, "loadout-root")
    items = w["items"]
    by = {i["name"]: i for i in items}
    if "t3Ground" in by:
        return 0
    _hide(by, "menuShade")
    _put(by["menuTitle"], M0 - 4, 138, 2300, 110)
    _txt(by["menuTitle"], PT_TITLE, TEXT, 0, 4.0)
    by["gameTitle"]["visible"] = 0                        # the header's right side is lpTotal (each page's own)
    for n, y in (("titleUnderline", HEAD_RULE), ("footerLine", FOOT_RULE)):
        it = by[n]
        _put(it, M0, y, M1 - M0, 2)
        it.update({"pointsUv": [0.0, 0.0, 1.0, 0.0], "closed": 0, "lineWidth": 2.0})
        _col(it, LINE, LINE_A)
    bl = by["buttonLegend"]
    _put(bl, M1 - 640, 2010, 640, 70)
    for n in ("hintSelectText", "hintBackText"):
        by[n]["faceId"] = "Default"
        _col(by[n], DIM)
    b = Builder(T)
    g = b.group("t3Ground", by["root"]["guid"], b.tl(0, 0, W, H))
    _ground(b, g["guid"], "t3G")
    at = next(k for k, i in enumerate(items) if i is by["root"]) + 1
    items[at:at] = b.items
    _save(wdir, "loadout-root", w)
    return len(b.items)


def apply(wdir):
    main = _load(wdir, "main-menu")
    T, _, _ = _templates(main)
    for c in T.values():
        for k in ("engineClass", "tags", "animationsPath"):
            c.pop(k, None)
    _page_anim(wdir)
    _template(wdir, "picker-row", "t3-row", _t3_row(T))
    _template(wdir, "skill-row", "t3-skill-row", _t3_skill_row(T))
    _template(wdir, "loadout-slot", "t3-slot", _t3_slot(T))
    n = _chrome(wdir, T) + _edit_page(wdir, T) + _skill_page(wdir, T)
    for p in PICKERS:
        n += _picker_page(wdir, p, T)
    n += _edit_details(wdir)
    return n


def _edit_details(wdir):
    """The edit page's DETAILS panel: a copy of picker-primary's (already moved to column D) - t2r-ext fills it for the focused slot row."""
    w = _load(wdir, "loadout-menu")
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
        new.append(c)
    at = next(k for k, i in enumerate(items) if i["name"] == "lpTotal")
    items[at:at] = new
    _save(wdir, "loadout-menu", w)
    return len(new)
