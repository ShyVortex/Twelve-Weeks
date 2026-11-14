"""GEAR UP, 2013 layout in the match-flow look (built with the in-game UI the same way as the map vote and loading
screen; not a fake UI). One new page, to1/gearup13, built like to1/matchflow (same backdrop, fonts, colours,
prompts) and driven entirely by t2r-ext gearup13.c on the real loadout data (lobby object, winmm's weapon tables, skills.c):

  "lst"  GEAR UP / CHOOSE LOADOUT - 00:11 / CHANGE LOADOUT: the 14 loadouts (6 custom + 8 classes) | the focused loadout's gear
         (small, large, purchasable, 4 skills) | what it is for and its points (2013factionsloadout4).
  "ed"   CUSTOM LOADOUT n: the 7 slots on the left (2013factionsloadout1: small, large | skills 1-4 | purchasable), the focused slot's
         options listed at once in the middle (no "enter the slot" page: hover / click equips), the hovered option's details on the right
         (icon, name, cost, description, 4 stat bars; a skill: its three levels).

Layout = the 2013 captures (1280 x 720) x 3, as tools/features/gearup2013_mock.py (x 1.5) drew the approved mockup. Widget space 3840 x 2160.
python gearup13_widgets.py <extracted widget dir> <out dir> renders previews."""
import copy
import json
import os
import t2guid

from clan_widgets import Builder, _templates, SUPPLY_BLUE, PM_TEXT, PM_DIM, HUD_PARTS_GREEN
from matchflow_widgets import TEXT, CREAM

PAGE = "gearup13"
HINT_W, HINT_W_REN = 1040.0, 1250.0  # the key hint's room (right aligned at x 3500): left of RENAME / the whole box while typing (gearup13.c GU_HINT_W*)
LIST_ROWS = 14                      # 6 custom rows (more customs scroll in them, gearup13.c G.coff) + 8 classes (t2r-ext N_CUSTOM + N_CLASSES)
SLOTS = 7                           # small, large, skill 1-4, purchasable
OPT_ROWS = 10                       # option window (scrolls)
LEVELS = 3
TITLE = 0xFFD8D4CC
HIT_A = 1                           # alpha of the invisible mouse hit rects (visible widgets, so their rect is laid out)
NONE_ICON = "streaming/t2r/icons/blocked.png"
EMPTY_ICON = "hud/weapon-cross/empty-slot.svg"
PU_Y0, PU_DY, PU_BOX = 980, 150, 124       # the purchasable price block
PARTS_ICON = "streaming/t2r/icons/hud-parts.png"   # the in-match parts counter's cog (make_icons.hud_counter_icon, tinted green like the HUD)
BOOM_ICON = "streaming/t2r/icons/boom-flat.png"   # the UNSUPPRESSED button: a flat jagged blast (make_icons.boom_icon_flat)
CAN_ICON = "streaming/t2r/icons/can-flat.png"   # the flat tilted suppressor can (make_icons.can_icon_flat, from 5b3c066a)
TG_Y, TG_H, TG_W, TG_GAP = 930, 156, 590, 29      # the UNSUPPRESSED / SUPPRESSED toggle under the description
PANEL = "streaming/t2r/clan/gearup-panel.png"   # the scratched dark backdrop (tools/features/ui_scratch.py, shipped by ship.py)
# Picker / loadout card rows (to1/picker-row, to1/loadout-slot): black card alpha 130, a 2 px white line under it alpha 40,
# a 2 px white focus frame alpha 180, a small grey Alternate label over the name, the cost right aligned (one button style for everything: separators between
# buttons, frames of buttons, names must not stick out when too long)
CARD_A, SEP_A, FOCUS_A, HILITE_A = 130, 40, 180, 14
LABEL = 0xFFB4B4B4
SLOT_LABELS = ("SMALL FIREARM", "LARGE FIREARM", "SKILL", "SKILL", "SKILL", "SKILL", "PURCHASABLE")

# 2013factionsloadout1 (capture units x 3)
SLOT_Y = [(123, 186), (191, 253), (262, 325), (330, 393), (398, 461), (466, 529), (540, 605)]
SX0, SX1 = 303, 1146                # slot column
OPT_Y0, OPT_DY, OPT_H = 480, 130.5, 112
OX0, OX1 = 1230, 2136               # option rows
DX0, DX1 = 2286, 3495               # details column
STAT_Y0, STAT_DY = 1150, 112
STAT_X0, STAT_X1 = 2406, 3399
STATS = ("RATE OF FIRE:", "RELOAD SPEED:", "DAMAGE:", "ACCURACY:")
# 2013factionsloadout4 (1920 capture x 2)
LIST_X, LIST_W, LIST_Y0, LIST_DY, LIST_GAP, LIST_H = 272, 900, 396, 86, 84, 80


def list_row_y(i):
    """lsRow i: the six custom rows, then (one row down: the CREATE LOADOUT button, NEW_Y) the gap and the eight classes."""
    return LIST_Y0 + LIST_DY * i + (LIST_DY + LIST_GAP if i >= 6 else 0)


NEW_Y = LIST_Y0 + LIST_DY * 6       # CREATE LOADOUT, under the custom rows
SB_X, SB_Y0, SB_H, SB_W = 1186, LIST_Y0, LIST_DY * 6 - 6, 6     # the custom rows' scroll bar (gearup13.c GU_SB_*: the thumb is moved + scaled)
NB_X, NB_Y, NB_W, NB_H = 1220, 760, 1400, 460                     # the CREATE LOADOUT name box


def opt_cy(k):
    return OPT_Y0 + OPT_DY * k


def tlm(x, y, w, h, right=0):
    """Box (x, y, w, h) with its pivot at the left (right=1: right) middle: gearup13.c scales a too-long name about it (w_scale), so
    a shrunk name keeps its left (right) edge and its vertical centre."""
    return {"anchorMinN.x": 0.0, "anchorMinN.y": 0.0, "anchorMaxN.x": 0.0, "anchorMaxN.y": 0.0,
            "pivotN.x": float(right), "pivotN.y": 0.5, "pivotAs.x": float(x + (w if right else 0)), "pivotAs.y": float(y + h / 2.0),
            "rectSizeDelta.width": float(w), "rectSizeDelta.height": float(h)}


def card(b, p, i, g, w, h):
    """Row card in group g (w x h): background, separator line, hidden highlight fill + focus frame (<p>Fill<i> / <p>Frame<i>)."""
    b.rect(f"{p}Card{i}", g, b.fill(), 0xFF000000, CARD_A)
    b.line(f"{p}Sep{i}", g, 0, h - 1, w, h - 1, 0xFFFFFFFF, SEP_A, 2.0)
    b.rect(f"{p}Fill{i}", g, b.fill(), 0xFFFFFFFF, HILITE_A, visible=0)
    b.frame(f"{p}Frame{i}", g, b.fill(), 0xFFFFFFFF, FOCUS_A, 2.0, visible=0)


def build_page(main):
    t, root0, anim0 = _templates(main)
    b = Builder(t)
    root = copy.deepcopy(root0); root.update(guid=t2guid.guid())
    anim = copy.deepcopy(anim0); anim.update(guid=t2guid.guid(), parent=root["guid"])
    b.items += [root, anim]
    a = anim["guid"]
    # the match-flow backdrop, verbatim
    b.image("bgBlur", a, b.bleed(), "general-textures/blur-background.png", 0xFFFFFFFF, 255)
    b.rect("bgDark", a, b.bleed(), 0xFF0B0C0D, 90)        # (light: the panel below carries the dark; the screen edges stay the blurred menu)
    b.image("bgPanel", a, b.tl(0, 0, 3840, 2160), PANEL, 0xFFFFFFFF, 255)
    # title + its hidden double-buffer twin (the red countdown, as VOTE FOR A MAP)
    b.text("title", a, b.tl(300, 140, 3000, 150), "GEAR UP", 84, TITLE, tracking=4)
    b.text("titleB", a, b.tl(300, 140, 3000, 150), "GEAR UP", 84, TITLE, tracking=4, visible=0)

    # ------------------------------------------------------------ list
    lst = b.group("lst", a, b.tl(0, 0, 3840, 2160))["guid"]
    for i in range(LIST_ROWS):
        y = list_row_y(i)
        g = b.group(f"lsRow{i}", lst, b.tl(LIST_X, y, LIST_W, LIST_H))["guid"]
        card(b, "ls", i, g, LIST_W, LIST_H)
        b.text(f"lsName{i}", g, tlm(28, 0, 590, LIST_H), f"CUSTOM LOADOUT {i + 1}", 44, TEXT, tracking=4)
        b.text(f"lsTag{i}", g, b.tl(640, 0, LIST_W - 664, LIST_H), "", 30, SUPPLY_BLUE, align=2, tracking=2)
        b.rect(f"lsHit{i}", g, b.fill(), 0xFFFFFFFF, HIT_A)       # mouse hit area (gearup13.c hovers / clicks it; a hidden fill has no rect)
    # CREATE LOADOUT (a button like any other UI button): a list card under the custom rows; SELECT / a click opens the
    # name box (nb). The tag is the count (7/12); dimmed when the list is full or outside the menu's GEAR UP.
    g = b.group("lsNew", lst, b.tl(LIST_X, NEW_Y, LIST_W, LIST_H))["guid"]
    card(b, "lsNew", "", g, LIST_W, LIST_H)
    b.text("lsNewPlus", g, tlm(28, -2, 50, LIST_H), "+", 52, SUPPLY_BLUE)
    b.text("lsNewTx", g, tlm(84, 0, 560, LIST_H), "CREATE LOADOUT", 44, TEXT, tracking=4)
    b.text("lsNewTag", g, b.tl(640, 0, LIST_W - 664, LIST_H), "6/12", 30, PM_DIM, align=2, tracking=2)
    b.rect("lsNewHit", g, b.fill(), 0xFFFFFFFF, HIT_A)
    b.rect("lsSbTrack", lst, b.tl(SB_X, SB_Y0, SB_W, SB_H), 0xFFFFFFFF, 40, visible=0)
    b.rect("lsSbThumb", lst, b.tl(SB_X, SB_Y0, SB_W, SB_H), 0xFFFFFFFF, 170, visible=0)
    b.line("lsDivider", lst, 1212, 330, 1212, 1780, 0xFFFFFFFF, 160, 2.0)
    for k in range(3):                  # small, large | purchasable (2013 order)
        cy = (444, 644, 892)[k]
        g = b.group(f"lgRow{k}", lst, b.tl(1352, cy - 84, 1196, 168))["guid"]
        card(b, "lg", k, g, 1196, 168)
        b.text(f"lgLb{k}", g, b.tl(240, 22, 900, 40), ("SMALL FIREARM", "LARGE FIREARM", "PURCHASABLE")[k], 28, LABEL, face="Alternate", tracking=8)
        b.image(f"lgIc{k}", lst, b.ctr(1448, cy, 160, 104), EMPTY_ICON, CREAM, scaleMode="StretchAspect")
        b.text(f"lgNm{k}", lst, tlm(1592, cy - 26, 930, 92), "", 44, TEXT, tracking=3)
    for k in range(4):
        cy = 1092 + 116 * k
        g = b.group(f"lskRow{k}", lst, b.tl(1352, cy - 52, 1196, 104))["guid"]
        card(b, "lsk", k, g, 1196, 104)
        b.image(f"lskIc{k}", lst, b.ctr(1448, cy, 80, 80), EMPTY_ICON, 0xFFFFFFFF, scaleMode="StretchAspect")
        b.text(f"lskNm{k}", lst, tlm(1592, cy - 40, 930, 80), "", 40, TEXT, tracking=3)
    b.line("lsDivider2", lst, 2600, 330, 2600, 1780, 0xFFFFFFFF, 110, 2.0)
    b.text("lsName", lst, tlm(2670, 360, 880, 90), "", 56, TEXT, tracking=3)
    b.text("lsDesc", lst, b.tl(2670, 470, 880, 700), "", 42, PM_TEXT, multiline=1, valign=0)
    b.text("lsCur", lst, b.tl(2670, 1290, 900, 70), "", 38, PM_TEXT, tracking=2)
    b.text("lsLP", lst, b.tl(2670, 1200, 900, 80), "", 46, SUPPLY_BLUE, tracking=3)

    # ------------------------------------------------------------ edit
    ed = b.group("ed", a, b.tl(0, 0, 3840, 2160), visible=0)["guid"]
    for i in range(SLOTS):
        y0, y1 = SLOT_Y[i][0] * 3, SLOT_Y[i][1] * 3
        g = b.group(f"sl{i}", ed, b.tl(SX0, y0, SX1 - SX0, y1 - y0))["guid"]
        h = y1 - y0
        b.rect(f"slHit{i}", g, b.fill(), 0xFFFFFFFF, HIT_A)
        card(b, "sl", i, g, SX1 - SX0, h)
        b.add("Polyline", f"slArrow{i}", g, **b.tl(SX1 - SX0 + 5, h / 2 - 20, 20, 40), **b.col(CREAM), closed=1, lineWidth=3.0,
              pointsUv=[0.0, 0.0, 1.0, 0.5, 0.0, 1.0], visible=0, **{"color.a": 220})
        b.image(f"slIc{i}", g, b.ctr(108, h / 2, 186 if i < 2 or i == 6 else 120, 120), EMPTY_ICON, CREAM, scaleMode="StretchAspect")
        b.text(f"slLb{i}", g, b.tl(236, h * 0.16, 480, 40), SLOT_LABELS[i], 28, LABEL, face="Alternate", tracking=8)
        b.text(f"slNm{i}", g, tlm(236, h * 0.36, 480, h * 0.52), "", 40, TEXT, tracking=2)
        b.text(f"slCo{i}", g, b.tl(724, 0, 92, h), "", 44, SUPPLY_BLUE, align=2)
    b.line("slDivider", ed, 1176, SLOT_Y[0][0] * 3, 1176, SLOT_Y[-1][1] * 3, 0xFFFFFFFF, 160, 2.0)   # a margin from the slot boxes, the slot column's own height
    b.text("edHead", ed, b.tl(1224, 315, 1100, 80), "LARGE FIREARM", 50, TEXT, tracking=4)
    b.text("edLP", ed, b.tl(2300, 315, 1225, 80), "13/13 Loadout Points", 50, TEXT, align=2, tracking=2)
    b.line("edRule0", ed, 1224, 408, 3525, 408, 0xFFFFFFFF, 150, 2.0)
    b.line("edDivider", ed, 2193, 438, 2193, 1695, 0xFFFFFFFF, 150, 2.0)
    b.line("edRule1", ed, 1224, 1713, 3525, 1713, 0xFFFFFFFF, 150, 2.0)
    for k in range(OPT_ROWS):
        cy = opt_cy(k)
        g = b.group(f"op{k}", ed, b.tl(OX0, cy - OPT_H / 2, OX1 - OX0, OPT_H))["guid"]
        b.rect(f"opHit{k}", g, b.fill(), 0xFFFFFFFF, HIT_A)      # first child = bottom of the row's z-order (a hit rect over the name text hid names in game)
        card(b, "op", k, g, OX1 - OX0, OPT_H)
        b.rect(f"opEq{k}", g, b.tl(0, 0, 7, OPT_H), CREAM, 235, visible=0)      # the equipped marker: the card's full height, flush with its left edge
        b.image(f"opIc{k}", g, b.ctr(74, OPT_H / 2, 100, 76), EMPTY_ICON, CREAM, scaleMode="StretchAspect")
        b.text(f"opNm{k}", g, tlm(150, 0, 700, OPT_H), "", 38, TEXT, tracking=2)
        b.text(f"opCo{k}", g, tlm(632, 0, 250, OPT_H, right=1), "", 36, LABEL, align=2, tracking=1)   # right pivot: gearup13.c shrinks a long state word toward the row end
    for nm, y, uv in (("opUp", 436, [0.0, 1.0, 0.5, 0.0, 1.0, 1.0]), ("opDn", 1660, [0.0, 0.0, 0.5, 1.0, 1.0, 0.0])):
        b.add("Polyline", nm, ed, **b.tl(2148, y, 32, 20), **b.col(TEXT), closed=1, lineWidth=4.0, pointsUv=uv, visible=0,
              **{"color.a": 200})
    dt = b.group("dt", ed, b.tl(0, 0, 3840, 2160))["guid"]
    b.image("dtIc", dt, b.ctr(2436, 525, 210, 138), EMPTY_ICON, CREAM, scaleMode="StretchAspect")
    b.text("dtNm", dt, tlm(2592, 440, 920, 90), "", 52, TEXT, tracking=3)
    b.text("dtCo", dt, b.tl(2592, 540, 930, 90), "", 54, SUPPLY_BLUE, tracking=2)
    b.text("dtDesc", dt, b.tl(DX0, 640, DX1 - DX0, 285), "", 38, TEXT, multiline=1, valign=0)
    # the suppressor toggle UNDER the description (guns with a suppressed variant): two real buttons, A / D or a click switches (gearup13.c)
    tg = b.group("dtTg", dt, b.tl(0, 0, 3840, 2160), visible=0)["guid"]
    for k in range(2):
        g = b.group(f"tgB{k}", tg, b.tl(DX0 + k * (TG_W + TG_GAP), TG_Y, TG_W, TG_H))["guid"]
        card(b, "tg", k, g, TG_W, TG_H)
        b.rect(f"tgEq{k}", g, b.tl(0, 0, 7, TG_H), CREAM, 235, visible=0)
        b.image(f"tgIc{k}", g, b.ctr(124, TG_H / 2, 196, TG_H - 40), CAN_ICON if k else BOOM_ICON, CREAM, scaleMode="StretchAspect")   # UNSUPPRESSED: the gun's own icon (gearup13.c), SUPPRESSED: the can
        b.text(f"tgNm{k}", g, tlm(246, 24, 330, 60), ("UNSUPPRESSED", "SUPPRESSED")[k], 32, TEXT, tracking=2)
        b.text(f"tgCo{k}", g, tlm(246, 88, 330, 52), "", 30, LABEL, tracking=1)
        b.rect(f"tgHit{k}", g, b.fill(), 0xFFFFFFFF, HIT_A)
    st = b.group("dtSt", dt, b.tl(0, 0, 3840, 2160))["guid"]          # a gun: its rule + four stat bars (the group is hidden for anything else)
    b.line("dtRule", st, DX0, 1100, DX1, 1100, 0xFFFFFFFF, 130, 2.0)
    sw = (STAT_X1 - STAT_X0 - 9 * 18) / 10.0
    for s in range(4):
        y = STAT_Y0 + STAT_DY * s
        b.text(f"stLb{s}", st, b.tl(STAT_X0, y, 900, 56), STATS[s], 34, TEXT, tracking=2)
        for k in range(10):
            x = STAT_X0 + k * (sw + 18)
            b.rect(f"stE{s}_{k}", st, b.tl(x, y + 62, sw, 20), 0xFFFFFFFF, 40)
            b.rect(f"stF{s}_{k}", st, b.tl(x, y + 62, sw, 20), CREAM, 235, visible=0)
    b.text("dtVar", dt, b.tl(STAT_X0, 1610, 1100, 60), "", 32, PM_DIM, tracking=2)
    lv = b.group("dtLv", dt, b.tl(0, 0, 3840, 2160), visible=0)["guid"]     # a skill: its three levels (the equipped / shown one bright)
    for k in range(LEVELS):
        y = 650 + 330 * k
        b.text(f"lvHd{k}", lv, b.tl(DX0, y, 1209, 60), "", 36, SUPPLY_BLUE, tracking=3)
        b.text(f"lvTx{k}", lv, b.tl(DX0, y + 64, DX1 - DX0, 250), "", 36, TEXT, multiline=1, valign=0)
        b.rect(f"lvHit{k}", lv, b.tl(DX0, y - 10, DX1 - DX0, 320), 0xFFFFFFFF, HIT_A)      # a click on a level line equips that level

    # a purchasable: the in-match prices as a small block instead of description text. Row 0: [item icon in a square frame] -> price + the
    # in-game parts cog (same icon + green as the in-match parts counter, clan_widgets.HUD_PARTS_GREEN); row 1: [ammo icon in a frame] -> ammo pack price;
    # then "Starts with: [ammo icon] n". Row 1 / the starts line are hidden for items with no ammo (gearup13.c fills + shows them).
    pu = b.group("dtPu", dt, b.tl(0, 0, 3840, 2160), visible=0)["guid"]
    for r in range(2):
        y0 = PU_Y0 + PU_DY * r
        g = b.group(f"puRow{r}", pu, b.tl(DX0, y0, 1209, PU_BOX))["guid"]
        b.rect(f"puBg{r}", g, b.fill(), 0xFF000000, CARD_A)
        b.frame(f"puFrame{r}", g, b.tl(0, 0, PU_BOX, PU_BOX), 0xFFFFFFFF, 160, 2.0)
        b.image(f"puIc{r}", g, b.ctr(PU_BOX / 2, PU_BOX / 2, PU_BOX - 28, PU_BOX - 28), EMPTY_ICON, CREAM, scaleMode="StretchAspect")
        ax, ay = PU_BOX + 50, PU_BOX / 2
        b.line(f"puAr{r}", g, ax, ay, ax + 110, ay, 0xFFFFFFFF, 190, 3.0)
        b.line(f"puAh{r}", g, ax + 110, ay, ax + 86, ay - 18, 0xFFFFFFFF, 190, 3.0)
        b.line(f"puAh{r}b", g, ax + 110, ay, ax + 86, ay + 18, 0xFFFFFFFF, 190, 3.0)
        b.text(f"puN{r}", g, b.tl(ax + 150, 0, 300, PU_BOX), "", 64, HUD_PARTS_GREEN, align=2, tracking=2)
        b.image(f"puPart{r}", g, b.ctr(ax + 150 + 300 + 56, PU_BOX / 2, 80, 80), PARTS_ICON, HUD_PARTS_GREEN, scaleMode="StretchAspect")
    b.text("puStLb", pu, b.tl(DX0, PU_Y0 + PU_DY * 2 + 6, 340, 70), "Starts with:", 40, TEXT, tracking=2)
    b.image("puStIc", pu, b.ctr(DX0 + 400, PU_Y0 + PU_DY * 2 + 41, 84, 84), EMPTY_ICON, CREAM, scaleMode="StretchAspect")
    b.text("puStN", pu, b.tl(DX0 + 462, PU_Y0 + PU_DY * 2 + 6, 300, 70), "", 48, TEXT, tracking=2)

    # icon residency: 96 tiny always-visible images in the screen corner; gearup13.c puts every icon the page can show on them a few per frame after the
    # page opens, so the engine has streamed the textures in before the first selection (a texture shown for the first time appeared late)
    pre = b.group("pre", a, b.tl(3820, 2140, 20, 20))["guid"]
    for i in range(96):
        b.image(f"pre{i}", pre, b.tl(0, 0, 3, 3), EMPTY_ICON, 0xFFFFFFFF, 255)

    # ------------------------------------------------------------ the CREATE LOADOUT name box (gearup13.c gn_create_begin; under the footer prompts, which
    # read CREATE / CANCEL / DELETE while it is open). The field is the name being typed with its cursor (nbField), prefilled CUSTOM LOADOUT n.
    nb = b.group("nb", a, b.tl(0, 0, 3840, 2160), visible=0)["guid"]
    b.rect("nbDim", nb, b.bleed(), 0xFF000000, 150)
    b.rect("nbCard", nb, b.tl(NB_X, NB_Y, NB_W, NB_H), 0xFF0B0C0D, 235)
    b.frame("nbFrame", nb, b.tl(NB_X, NB_Y, NB_W, NB_H), 0xFFFFFFFF, 90, 2.0)
    b.text("nbHead", nb, b.tl(NB_X + 70, NB_Y + 50, NB_W - 140, 90), "NAME YOUR LOADOUT", 56, TITLE, tracking=4)
    b.line("nbSep", nb, NB_X + 70, NB_Y + 156, NB_X + NB_W - 70, NB_Y + 156, 0xFFFFFFFF, SEP_A * 2, 2.0)
    b.rect("nbBox", nb, b.tl(NB_X + 70, NB_Y + 196, NB_W - 140, 120), 0xFF000000, 150)
    b.frame("nbBoxFrame", nb, b.tl(NB_X + 70, NB_Y + 196, NB_W - 140, 120), 0xFFFFFFFF, FOCUS_A, 2.0)
    b.text("nbField", nb, tlm(NB_X + 110, NB_Y + 196, NB_W - 220, 120), "CUSTOM LOADOUT 7", 52, TEXT, tracking=4)
    b.text("nbSub", nb, b.tl(NB_X + 70, NB_Y + 348, NB_W - 140, 60), "UP TO 20 LETTERS", 32, PM_DIM, tracking=4)

    # ------------------------------------------------------------ prompts (the match-flow footer)
    b.image("pBackIc", a, b.tl(270, 1898, 56, 56), "menu:back", 0xFFFFFFFF)
    b.text("pBackTx", a, b.tl(350, 1890, 400, 70), "BACK", 46, PM_TEXT, tracking=4)
    b.image("pSelIc", a, b.tl(760, 1898, 56, 56), "menu:select", 0xFFFFFFFF)
    b.text("pSelTx", a, b.tl(840, 1890, 700, 70), "SELECT", 46, PM_TEXT, tracking=4)
    b.image("pRstIc", a, b.tl(1300, 1898, 56, 56), "menu:action", 0xFFFFFFFF, visible=0)
    b.text("pRstTx", a, b.tl(1380, 1890, 700, 70), "RESET LOADOUT", 46, PM_TEXT, tracking=4, visible=0)
    b.rect("pRstHit", a, b.tl(1280, 1800, 820, 200), 0xFFFFFFFF, HIT_A)
    # RENAME: the custom loadout's name, typed in the title (gearup13.c gn_*); the bumper glyph (menu-next), the E key, a click.
    # While typing it is hidden (SELECT / BACK / RESET read SAVE / CANCEL / DELETE) and the key hint gets the whole right side.
    b.image("pRenIc", a, b.tl(2100, 1898, 56, 56), "menu:next", 0xFFFFFFFF, visible=0)
    b.text("pRenTx", a, b.tl(2180, 1890, 500, 70), "RENAME", 46, PM_TEXT, tracking=4, visible=0)
    b.rect("pRenHit", a, b.tl(2080, 1800, 560, 200), 0xFFFFFFFF, HIT_A)
    # the key hint: right aligned at the panel edge, shrunk toward it when long (gu_fit, pivot right) so it never runs into RENAME
    b.text("pHint", a, tlm(2250, 1890, 1250, 70, right=1), "", 38, PM_DIM, align=2, tracking=4)
    b.rect("pBackHit", a, b.tl(250, 1800, 480, 200), 0xFFFFFFFF, HIT_A)
    b.rect("pSelHit", a, b.tl(740, 1800, 840, 200), 0xFFFFFFFF, HIT_A)
    w = {k: copy.deepcopy(v) for k, v in main.items() if k != "items"}
    w["items"] = b.items
    return w


def add_gearup13_page(wdir):
    main = json.load(open(os.path.join(wdir, "to1", "main-menu.widget.json"), encoding="utf-8"))
    json.dump(build_page(main), open(os.path.join(wdir, "to1", PAGE + ".widget.json"), "w", encoding="utf-8"), indent=4)
    return 1


# ------------------------------------------------------------------ offline previews (filled like gearup13.c fills them)
G_ = "hud/weapons/guns/"
DEMO_IC = {"Revolver": G_ + "pistol-revolver-taurus/revolver-brl.png", "Suppressed Pistol": G_ + "pistol-glock/glock.png",
           "Hunting Rifle": G_ + "rifle-vepr/vepr.png", "Military Sniper": G_ + "rifle-vepr/vepr.png", "Military Sniper Rifle": G_ + "rifle-vepr/vepr.png",
           "Variable Rifle": G_ + "rifle-vepr/vepr.png", "Suppressed Variable Rifle": G_ + "rifle-vepr/vepr.png", "Burst Rifle": G_ + "rifle-vepr/vepr.png",
           "Full-Auto Rifle": G_ + "rifle-vepr/vepr.png", "Pump Shotgun": G_ + "shotgun-remington-pump/remington-pump.png",
           "Double Barrel": G_ + "shotgun-baserri-over-under/baserri.png", "Crossbow": G_ + "crossbow/crossbow.png", "Bow": G_ + "bow-ellie/bow.png"}


def _est(t, pt):
    """gearup13.c gu_est: capitals / digits 0.80 pt, lower case 0.62 pt, space 0.40 pt."""
    return pt * sum(0.40 if c == " " else 0.62 if c.islower() or ord(c) > 127 else 0.80 for c in t)


def _fit(item, box, floor=0.6):
    """Offline stand-in for gearup13.c gu_fit (w_scale about the left / right pivot, cut with '...' below the floor): shrinks pointSize."""
    t, pt = item.get("text", ""), item["pointSize"]
    e = _est(t, pt)
    sc = max(floor, box / e) if e > box else 1.0
    if e * sc > box * 1.02:
        while len(t) > 1 and _est(t + "...", pt) * sc > box:
            t = t[:-1].rstrip()
        item["text"] = t + "..."
    item["pointSize"] = pt * min(sc, 1.0)


SKI = "streaming/t2r/icons/"
SKILL_DEMO = {"Hawk-Eyed I": 7, "Sharp Ears I": 5, "Agility II": 20, "Covert Training III": 4, "Strategist I": 6, "Sharpshooter II": 10,
              "Lethal Efficiency II Extended": 25, "Wytrzymalosc fizyczna III": 11, "Quick Hands I": 22}      # name -> skill_icons.GLYPHS index
DEMO_IC.update({n: SKI + f"gu-sk{i}.png" for n, i in SKILL_DEMO.items()})


def tg_state(vis, txt, v):
    """The suppressor toggle under the description: v = 0 UNSUPPRESSED / 1 SUPPRESSED equipped (-1: neither)."""
    vis("dtTg", 1)
    for k, c in enumerate(("2 LP", "4 LP")):
        txt(f"tgCo{k}", c)
        vis(f"tgFrame{k}", v == k); vis(f"tgFill{k}", v == k); vis(f"tgEq{k}", v == k)


PU_DEMO = {"crossbow": ("Crossbow", G_ + "crossbow/crossbow.png", "hud/weapons/ammo/ammo-arrow_small.png", 350, 380, 4,
                        "Silent. Two body shots to down, a headshot kills. A bolt sticks in the enemy, forcing them to pull it out."),
           "launcher": ("Explosive Bow", G_ + "bow-ellie/bow.png", "hud/weapons/ammo/ammo-arrow-explosive_small.png", 450, 300, 3,
                        "Fires explosive arrows. Slow to reload, devastating on a group."),
           "machete": ("Machete", NONE_ICON, None, 150, 0, 0, "A heavy blade. Quiet and fast up close.")}


def pu_state(vis, txt, img, key):
    nm, ic, am, cost, acost, start, ds = PU_DEMO[key]
    vis("dtPu", 1); vis("dtSt", 0); vis("dtTg", 0)
    txt("dtNm", nm); txt("dtCo", "3 LP"); img("dtIc", ic)
    txt("dtDesc", ds + "\n\nOnce bought it is yours again at every spawn.")
    img("puIc0", ic); txt("puN0", str(cost))
    vis("puRow1", acost > 0); vis("puStLb", start > 0); vis("puStIc", start > 0); vis("puStN", start > 0)
    if acost > 0:
        img("puIc1", am); txt("puN1", str(acost))
    if start > 0:
        img("puStIc", am); txt("puStN", str(start))


def demo(page, view):
    w = copy.deepcopy(page)
    by = {i["name"]: i for i in w["items"]}

    def vis(n, on):
        by[n]["visible"] = int(bool(on))

    def txt(n, s):
        by[n]["text"] = s

    def img(n, p):
        by[n]["path"] = p
    named = view == "list-named"
    sub = view if view in ("list-create", "list-more", "create-box", "create-typed") else ""
    if named or sub:
        view = "list"
    vis("lst", view == "list"); vis("ed", view != "list")
    if view != "list":
        vis("pRstIc", 1); vis("pRstTx", 1); vis("pRenIc", 1); vis("pRenTx", 1)
    if view == "list":
        names = [("RUSH KIT" if named and i == 0 else "ŁOWCA" if named and i == 2 else f"CUSTOM LOADOUT {i + 1}") for i in range(6)] + ["COMMANDO", "MARKSMAN", "SHADOW", "SUPPORT", "RECON", "BARRAGE",
                                                                  "SALVO", "SUPPRESSION"]
        for i, n in enumerate(names):
            txt(f"lsName{i}", n)
            vis(f"lsFill{i}", i == 7); vis(f"lsFrame{i}", i == 7)
        txt("lsTag0", "EQUIPPED")
        txt("lgNm0", "Revolver"); txt("lgNm1", "Hunting Rifle"); txt("lgNm2", "Military Sniper")
        for k, n in enumerate(("Revolver", "Hunting Rifle", "Military Sniper")):
            img(f"lgIc{k}", DEMO_IC[n])
        for k in range(4):
            img(f"lskIc{k}", NONE_ICON)
        for k, s in enumerate(("Sharpshooter II", "Hawk-Eyed I", "Strategist I", "Sharp Ears I")):
            txt(f"lskNm{k}", s)
        txt("lsName", "MARKSMAN")
        txt("lsDesc", "Picks targets from afar. A hunting rifle, a Military Sniper in the back pocket, a steady aim, sharp ears and an eye for marking.")
        txt("lsLP", "13/13 Loadout Points")
        txt("lsCur", "This is your current loadout")
        txt("pSelTx", "EQUIP")
        if sub:                     # CREATE LOADOUT (gearup13.c gu_fill_list: the button focused / more customs scrolled / the name box)
            more = sub == "list-more"
            n_cust = 9 if more else 6
            off = n_cust - 6 if more else 0
            for i in range(6):
                k = off + i
                txt(f"lsName{i}", ("RUSH KIT", "CUSTOM LOADOUT 2", "ŁOWCA", "CUSTOM LOADOUT 4", "CUSTOM LOADOUT 5", "CUSTOM LOADOUT 6",
                                   "SNIPER NEST", "CUSTOM LOADOUT 8", "BOMBER")[k])
                txt(f"lsTag{i}", "EQUIPPED" if k == 0 else "")
            for i in range(14):
                vis(f"lsFill{i}", 0); vis(f"lsFrame{i}", 0)
            txt("lsNewTag", f"{n_cust}/12")
            vis("lsNewFill", 1); vis("lsNewFrame", 1)
            if more:
                vis("lsSbTrack", 1); vis("lsSbThumb", 1)
                th = by["lsSbThumb"]
                th["rectSizeDelta.height"] = SB_H * 6.0 / n_cust
                th["pivotAs.y"] = SB_Y0 + SB_H * off / n_cust
            for k in range(3):
                txt(f"lgNm{k}", ("9mm Pistol", "No Large Firearm", "No Purchasable")[k]); img(f"lgIc{k}", G_ + "pistol-glock/glock.png" if k == 0 else NONE_ICON)
            for k in range(4):
                txt(f"lskNm{k}", ""); img(f"lskIc{k}", EMPTY_ICON)
            txt("lsName", "CREATE LOADOUT")
            txt("lsDesc", "Make a new custom loadout. SELECT to name it, then choose its gear.")
            txt("lsLP", "13/13 Loadout Points"); txt("lsCur", "")
            txt("pSelTx", "CREATE")
            if sub.startswith("create-"):
                vis("nb", 1)
                txt("nbField", '<font color="#3fa9f5">CUSTOM LOADOUT 7</font>_' if sub == "create-box" else 'SNIPER NES<font color="#3fa9f5">_</font>')
                txt("pSelTx", "CREATE"); txt("pBackTx", "CANCEL"); txt("pRstTx", "DELETE"); vis("pRstIc", 1); vis("pRstTx", 1)
                txt("pHint", "TYPE A NAME     ENTER  CREATE     ESC  CANCEL")
    else:
        for i, (n, c) in enumerate((("Suppressed Pistol", "2"), ("Variable Rifle", "2"), ("Hawk-Eyed I", "2"), ("Nothing", ""), ("Nothing", ""),
                                    ("Nothing", ""), ("No Purchasable", ""))):
            txt(f"slNm{i}", n); txt(f"slCo{i}", c or "0")
            img(f"slIc{i}", DEMO_IC.get(n, NONE_ICON))
        vis("slFill1", 1); vis("slFrame1", 1); vis("slArrow1", 1)
        opts = [("No Large Firearm", "FREE"), ("Hunting Rifle", "2 LP"), ("Variable Rifle", "EQUIPPED"), ("Bow", "3 LP"),
                ("Burst Rifle", "2 LP"), ("Full-Auto Rifle", "2 LP"), ("Pump Shotgun", "4 LP"),
                ("Double Barrel", "1 LP"), ("Crossbow", "3 LP")]
        for k, (n, c) in enumerate(opts):
            txt(f"opNm{k}", n); txt(f"opCo{k}", c)
            img(f"opIc{k}", DEMO_IC.get(n, NONE_ICON))
        vis("opFill2", 1); vis("opFrame2", 1); vis("opEq2", 1); vis("opDn", 1)
        txt("dtNm", "Variable Rifle"); txt("dtCo", "2 LP"); img("dtIc", DEMO_IC["Variable Rifle"])
        txt("dtDesc", "A bolt-action rifle with a big magazine. Good at mid range.")
        for s, v in enumerate((6, 5, 5, 7)):
            for k in range(10):
                vis(f"stF{s}_{k}", k < v)
        txt("dtVar", "")
        tg_state(vis, txt, 0)
        txt("edLP", "7/13 Loadout Points"); txt("title", "CUSTOM LOADOUT 1")
        txt("pHint", "W / S  TO MOVE     D  OPTIONS")
        if view in ("toggle-off", "toggle-on"):
            on = view == "toggle-on"
            tg_state(vis, txt, 1 if on else 0)
            txt("opCo2", "EQUIPPED"); txt("opCo3", "2 LP"); vis("opEq2", 1); vis("opEq3", 0)
            if on:
                txt("slNm1", "Suppressed Variable Rifle"); txt("slCo1", "4"); txt("edLP", "5/13 Loadout Points")
            txt("dtNm", "Suppressed Variable Rifle" if on else "Variable Rifle"); txt("dtCo", "4 LP" if on else "2 LP")
            txt("dtDesc", "A bolt-action rifle with a big magazine. Good at mid range." + ("\nHides shots from appearing on enemy radar." if on else ""))
            txt("pHint", "W / S  TO MOVE     A / D  SUPPRESSOR")
            vis("op9", 0)
        if view.startswith("rename"):          # RENAME: the NAME YOUR LOADOUT box as CREATE LOADOUT's (gn_title -> nbField), the prompts are the name's
            if view == "rename-saved":
                txt("title", "RUSH KIT")
            else:
                vis("nb", 1)
                txt("nbField", {"rename": '<font color="#3fa9f5">CUSTOM LOADOUT 1</font>_',
                                "rename-pad": 'RUSH K<font color="#3fa9f5">I</font>T'}[view])
                txt("pSelTx", "SAVE"); txt("pBackTx", "CANCEL"); txt("pRstTx", "DELETE"); vis("pRenIc", 0); vis("pRenTx", 0)
                txt("pHint", "UP / DOWN  LETTER     LEFT / RIGHT  MOVE" if view == "rename-pad" else "TYPE A NAME     ENTER  SAVE     ESC  CANCEL")
        if view.startswith("pu-"):
            pu_state(vis, txt, img, view[3:]); txt("edHead", "PURCHASABLE"); txt("title", "CUSTOM LOADOUT 1")
        if view in ("reset", "locked"):
            vis("dtTg", 0)
        if view == "reset":          # right after RESET LOADOUT: everything back to the empty default, the first slot focused
            for i in range(SLOTS):
                txt(f"slNm{i}", ("9MM PISTOL", "No Large Firearm", "Nothing", "Nothing", "Nothing", "Nothing", "No Purchasable")[i])
                txt(f"slCo{i}", "0" if i else "0"); img(f"slIc{i}", NONE_ICON)
                vis(f"slFill{i}", i == 0); vis(f"slFrame{i}", i == 0); vis(f"slArrow{i}", i == 0)
            img("slIc0", G_ + "pistol-glock/glock.png")
            for k, (n, c) in enumerate((("No Small Firearm", ""), ("9mm Pistol", "EQUIPPED"), ("Revolver", "1 LP"), ("Shorty", "1 LP"),
                                        ("Enforcer", "1 LP"), ("Burst Pistol", "1 LP"))):
                vis(f"op{k}", 1); txt(f"opNm{k}", n); txt(f"opCo{k}", c or "FREE"); img(f"opIc{k}", DEMO_IC.get(n, G_ + "pistol-glock/glock.png"))
                vis(f"opFill{k}", 0); vis(f"opFrame{k}", 0); vis(f"opEq{k}", k == 1)
            for k in range(6, OPT_ROWS):
                vis(f"op{k}", 0)
            vis("opDn", 0); txt("edHead", "SMALL FIREARM"); txt("edLP", "13/13 Loadout Points")
            vis("opFill1", 1); vis("opFrame1", 1)
            txt("dtNm", "9mm Pistol"); txt("dtCo", "FREE"); img("dtIc", G_ + "pistol-glock/glock.png")
            txt("dtDesc", "Reliable and quiet to carry. Weak against anything with armour.")
            txt("dtVar", ""); txt("pHint", "W / S  TO MOVE     A  SLOTS")
        if view == "locked":         # a skill slot: locked / taken / over-points rows (dimmed), an empty slot, a long Polish name
            vis("slFill1", 0); vis("slFrame1", 0); vis("slArrow1", 0)
            vis("slFill3", 1); vis("slFrame3", 1); vis("slArrow3", 1)
            txt("edHead", "SURVIVAL SKILL 2"); txt("edLP", "<font color=\"#d23c32\">0/13 Loadout Points</font>")
            rows = [("Nothing", "FREE", 1, 0), ("Hawk-Eyed I", "IN SKILL 1", 0, 1), ("Sharp Ears I", "EQUIPPED", 0, 0), ("Agility II", "ZABLOKOWANE", 0, 1),
                    ("Covert Training III", "5 LP", 0, 1), ("Strategist I", "2 LP", 0, 0), ("Sharpshooter II", "3 LP", 0, 1),
                    ("Lethal Efficiency II Extended", "4 LP", 0, 1), ("Wytrzymalosc fizyczna III", "W UZYCIU", 0, 0), ("Quick Hands I", "2 LP", 0, 0)]
            for k, (n, c, foc, dim) in enumerate(rows):
                txt(f"opNm{k}", n); txt(f"opCo{k}", c); img(f"opIc{k}", NONE_ICON if n == "Nothing" else DEMO_IC.get(n, NONE_ICON))
                vis(f"opFill{k}", k == 3); vis(f"opFrame{k}", k == 3); vis(f"opEq{k}", k == 2)
                by[f"op{k}"]["color.a"] = 255
                if dim:
                    for sub in (f"opNm{k}", f"opCo{k}", f"opIc{k}"):
                        by[sub]["color.a"] = 115
            txt("dtNm", "Agility II"); txt("dtCo", "II  LOCKED"); txt("dtVar", ""); img("dtIc", DEMO_IC["Agility II"])
            vis("dtSt", 0); txt("dtDesc", "")
            vis("dtLv", 1)
            for k, (h, t) in enumerate((("I  -  1 LP", "Move faster while crouched."), ("II  -  LOCKED", "Move faster while crouched and sprint longer."),
                                        ("III  -  LOCKED", "Not available yet."))):
                txt(f"lvHd{k}", h); txt(f"lvTx{k}", t)
            txt("pHint", "W / S  TO MOVE     A / D  LEVEL")
            txt("title", "CUSTOM LOADOUT 2")
    _fit(by["pHint"], HINT_W_REN if view in ("rename", "rename-pad") or sub.startswith("create-") else HINT_W)                        # (gu_fit on the key hint, gearup13.c GU_HINT_W)
    for k in range(OPT_ROWS):                      # what gu_fit does in game
        if by[f"opCo{k}"].get("text"):
            _fit(by[f"opCo{k}"], 250.0)
            cw = min(250.0, max(70.0, _est(by[f"opCo{k}"]["text"], 36.0)))
            _fit(by[f"opNm{k}"], 882.0 - 150.0 - cw - 30.0)
    for i in range(SLOTS):
        if by[f"slNm{i}"].get("text"):
            _fit(by[f"slNm{i}"], 470.0)
    return w


def preview(wdir, out_dir):
    import sys
    import tempfile
    import widget_preview
    main = json.load(open(os.path.join(wdir, "to1", "main-menu.widget.json"), encoding="utf-8"))
    page = build_page(main)
    os.makedirs(out_dir, exist_ok=True)
    figs = os.path.join(tempfile.gettempdir(), "gu-fig")      # the scratched backdrop (ship.py stages it as streaming/t2r/clan/gearup-panel*.png)
    os.makedirs(figs, exist_ok=True)
    import ui_scratch
    ui_scratch.make_gearup_panel(1920, 1080).save(os.path.join(figs, "gearup-panel.png"))
    widget_preview.STREAMING["streaming/t2r/clan/"] = figs
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "models"))
    import make_icons, real_icons
    icd = os.path.join(tempfile.gettempdir(), "gu-icons")
    os.makedirs(icd, exist_ok=True)
    make_icons.can_icon_flat().save(os.path.join(icd, "can-flat.png"))
    make_icons.boom_icon_flat().save(os.path.join(icd, "boom-flat.png"))
    import skill_icons
    for n, i in SKILL_DEMO.items():
        skill_icons.skill_icon(i).save(os.path.join(icd, f"gu-sk{i}.png"))
    real_icons.MOD_DIRS.append(icd)
    make_icons.hud_counter_icon("parts").save(os.path.join(icd, "hud-parts.png"))
    for view in ("list", "list-named", "list-create", "list-more", "create-box", "create-typed", "edit", "rename", "rename-pad", "rename-saved", "toggle-off", "toggle-on", "reset", "locked", "pu-crossbow", "pu-launcher", "pu-machete"):
        tmp = os.path.join(tempfile.gettempdir(), f"t2r-gearup13-{view}.widget.json")
        json.dump(demo(page, view), open(tmp, "w", encoding="utf-8"))
        print(widget_preview.render(tmp, os.path.join(out_dir, f"gearup13-{view}.png")))


if __name__ == "__main__":
    import sys
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    preview(sys.argv[1], sys.argv[2])
