"""GEAR UP, restyled after the No Return screens (UI redesign: re/ui-redesign-1117/PROPOSAL.md, STYLE.md, the approved mockups
gearup-after.png / gearup-list-after.png, geometry = render.py x 2). One page, to1/gearup13, driven entirely by t2r-ext gearup13.c on the real
loadout data (lobby object, winmm's weapon tables, skills.c). The frame (backdrop, breadcrumb header, boxed key prompts) is nr_style.py's,
filled by nrui.c (nr_header / nr_prompts):

  "lst"  GEAR UP | CHOOSE LOADOUT: two rows of 2D tiles that scroll sideways (CUSTOM LOADOUTS + the CREATE LOADOUT tile, CLASSES), a detail band
         below for the focused loadout (name, text, LP bar, its 7 gear cells).
  "ed"   GEAR UP | CUSTOM LOADOUT n: the 7 slots as a ladder (rectangle thumbnails joined by a thin line) | the focused slot's options as the
         old vertical list (one row per option, cost right, EQUIPPED chip, scroll bar) | LP bar, big icon, name, cost, text, the suppressor
         toggle, 4 stat bars with N | M counts (a skill: its levels, a purchasable: the price block).
  "nb"   the NAME YOUR LOADOUT box (CREATE LOADOUT / RENAME).

Colour: white / grey text, the one accent (nr_style.ACC) on the EQUIPPED chips. A text that is grey when it is not focused is built grey
and written by gearup13.c as <font color="#F0F0F0">..</font> / plain; widths only by w_scale of left-pivot rects (bars, rules, chips).
python gearup13_widgets.py <extracted widget dir> <out dir> renders previews (the demo_* helpers of nr_style set the real widths)."""
import copy
import json
import os
import t2guid

import nr_style as N
from nr_style import WHITE, GREY, ACC, pt, lm
from clan_widgets import Builder, _templates

PAGE = "gearup13"
LIST_VISC = 7                        # custom rows on screen (gearup13.c GU_VISC): the customs + CREATE LOADOUT, scrolling up / down
N_CLS = 8
LIST_W = LIST_VISC + N_CLS           # lsRow widgets: 0..6 the custom window, 7..14 the classes
SLOTS = 7                            # small, large, skill 1-4, purchasable
OPT_ROWS = 9                         # option window (scrolls; the mockup's nine rows)
LEVELS = 3
HIT_A = 1                            # alpha of the invisible mouse hit rects (visible widgets, so their rect is laid out)
NONE_ICON = "streaming/t2r/icons/blocked.png"
EMPTY_ICON = "hud/weapon-cross/empty-slot.svg"
PARTS_ICON = "streaming/t2r/icons/hud-parts.png"   # the in-match parts counter's cog (make_icons.hud_counter_icon)
SLOT_LABELS = ("SMALL FIREARM", "LARGE FIREARM", "SKILL 1", "SKILL 2", "SKILL 3", "SKILL 4", "PURCHASABLE")
STATS = ("RATE OF FIRE", "RELOAD SPEED", "DAMAGE", "ACCURACY")
LP_TOTAL = 13

# ---- list (the old layout in the new style - the old three columns, list | gear | details, in the No Return frame)
LX0, LX1 = 148, 1180                 # the list column
ROW_H, ROW_P = 80, 92                # list rows
SEC_Y = (300, 1060)                  # CUSTOM LOADOUTS / CLASSES header centre lines
ROW_Y = (352, 1112)                  # first row top of each block
LSB_X = 1210                         # the custom rows' scroll bar
VDIV_X = (1270, 2610)                # the hairlines between the columns (the old page's dividers)
VDIV_Y0, VDIV_Y1 = 352, 1836
GX0, GX1 = 1360, 2520                # the gear column
GUN_Y, GUN_H = (352, 548, 772), 176  # small, large, purchasable (the purchasable apart, as on the old page)
SK_Y0, SK_P, SK_H = 996, 116, 100    # the four skill rows
GIC_W = 260                          # gear icon box
GTX = 300                            # gear text left (relative to the row)
DX0L = 2700                          # the details column (to R1)
LS_DESC_W = 1000
LS_DESC_Y, LS_DESC_H = 448, 560
LB_X0, LB_X1, LB_Y = DX0L, 3700, 1240   # the LP bar
PERK_Y = 1500
NB_X, NB_Y, NB_W, NB_H = 1220, 760, 1400, 500   # the NAME YOUR LOADOUT box

# ---- edit (mockup x 2)
SX0, SL_Y0, SL_P, THUMB_W, THUMB_H = 148, 300, 224, 256, 152      # ladder
SL_TX, SL_RX = 304, 972              # label / name left, cost right (relative to the slot group, x 148)
OX0, OX1, OPT_Y0, OPT_P, OPT_H = 1272, 2500, 392, 156, 144        # option rows
OPT_NAME_X, OPT_CO_R = 236, 1184     # name left, cost right edge (relative to the row)
SB_X, SB_Y0, SB_Y1 = 2528, 392, 1784  # the options' scroll bar
DX0, DX1 = 2660, 3700                # right column
LP_Y = 300
IC_Y, IC_H = 452, 208
NM_Y, CO_Y = 745, 832
DESC_Y = 892
TG_Y, TG_H, TG_W, TG_GAP = 1100, 160, 508, 24
STAT_Y0, STAT_DY = 1352, 128
LV_Y0, LV_DY = 900, 330
PU_Y0, PU_DY, PU_BOX = 1330, 150, 124
CHIP_PT = pt(20)
CHIP_H = CHIP_PT * 1.05 + 14


def card(b, g, name, w, h):
    """a tile / row card in group g (w x h): <name>Bg dim fill + <name>Fo focus outline (nr_style.tile) + <name>Fill hover fill (alpha 14)."""
    N.tile(b, g, name, w, h)
    b.rect(f"{name}Fill", g, b.fill(), WHITE, 14, visible=0)


def build_page(main):
    t, root0, anim0 = _templates(main)
    b = Builder(t)
    root = copy.deepcopy(root0); root.update(guid=t2guid.guid())
    anim = copy.deepcopy(anim0); anim.update(guid=t2guid.guid(), parent=root["guid"])
    b.items += [root, anim]
    a = anim["guid"]
    N.frame(b, a, "GEAR UP", "CHOOSE LOADOUT", prompts=0)       # backdrop + breadcrumb; the prompt slots are added last (above the name box's dim)

    # ------------------------------------------------------------ list (the old layout: a vertical list, the gear rows, the details)
    lst = b.group("lst", a, b.tl(0, 0, 3840, 2160))["guid"]
    N.section(b, lst, "lsSecC", LX0, LX1, SEC_Y[0], "CUSTOM LOADOUTS", "")
    N.section(b, lst, "lsSecL", LX0, LX1, SEC_Y[1], "CLASSES", "")
    for w in range(LIST_W):
        blk, r = (0, w) if w < LIST_VISC else (1, w - LIST_VISC)
        g = b.group(f"lsRow{w}", lst, b.tl(LX0, ROW_Y[blk] + ROW_P * r, LX1 - LX0, ROW_H))["guid"]
        b.rect(f"lsHit{w}", g, b.fill(), WHITE, HIT_A)             # first child = bottom of the z-order
        card(b, g, f"ls{w}", LX1 - LX0, ROW_H)
        b.text(f"lsName{w}", g, lm(28, 0, 700, ROW_H), f"CUSTOM LOADOUT {w + 1}", pt(22), GREY, tracking=3)
        b.text(f"lsTag{w}", g, lm(LX1 - LX0 - 328, 0, 300, ROW_H, right=1), "", pt(17), GREY, align=2, tracking=2)
    N.scroll_v(b, lst, "lsSc", LSB_X, ROW_Y[0], ROW_Y[0] + ROW_P * (LIST_VISC - 1) + ROW_H, 0.0, 0.7, visible=0)
    for k, x in enumerate(VDIV_X):
        b.rect(f"lsVd{k}", lst, b.tl(x, VDIV_Y0, N.HAIR, VDIV_Y1 - VDIV_Y0), WHITE, N.HAIR_A)
    # the gear rows: small, large, purchasable (with its icon box), then the four skills; tile fills like the list rows
    for k, y in enumerate(GUN_Y):                     # (flat in lst: gearup13.c addresses anim-group.lst.lgIc<k> / lgNm<k>)
        b.rect(f"lgBg{k}", lst, b.tl(GX0, y, GX1 - GX0, GUN_H), N.TILE, N.TILE_A)
        b.image(f"lgIc{k}", lst, b.ctr(GX0 + GIC_W / 2 + 12, y + GUN_H / 2, GIC_W - 40, GUN_H - 44), EMPTY_ICON, WHITE, scaleMode="StretchAspect")
        b.text(f"lgLb{k}", lst, lm(GX0 + GTX, y + 26, 800, 52), ("SMALL FIREARM", "LARGE FIREARM", "PURCHASABLE")[k], pt(17), GREY, tracking=3)
        b.text(f"lgNm{k}", lst, lm(GX0 + GTX, y + 82, GX1 - GX0 - GTX - 40, 70), "", pt(28), WHITE)
    for k in range(4):
        y = SK_Y0 + SK_P * k
        b.rect(f"lskBg{k}", lst, b.tl(GX0, y, GX1 - GX0, SK_H), N.TILE, N.TILE_A)
        b.image(f"lskIc{k}", lst, b.ctr(GX0 + GIC_W / 2 + 12, y + SK_H / 2, 76, 76), EMPTY_ICON, WHITE, scaleMode="StretchAspect")
        b.text(f"lskNm{k}", lst, lm(GX0 + GTX, y, GX1 - GX0 - GTX - 40, SK_H), "", pt(26), WHITE)
    b.text("lsPerk", lst, lm(GX0, PERK_Y - 35, GX1 - GX0, 70), "", pt(20), GREY, tracking=2)
    # the details: name, description, loadout points
    b.text("lsName", lst, lm(DX0L, 352 - 6, N.R1 - DX0L, 90), "", pt(40), WHITE, tracking=3)
    b.text("lsDesc", lst, b.tl(DX0L, LS_DESC_Y, LS_DESC_W, LS_DESC_H), "", pt(24), WHITE, multiline=1, valign=0)
    b.text("lsLPt", lst, lm(DX0L, LB_Y - 80, 700, 60), "LOADOUT POINTS", pt(22), GREY, tracking=3)
    b.text("lsLP", lst, lm(LB_X1 - 600, LB_Y - 80, 600, 60, right=1), "13 | 13", pt(28), WHITE, align=2, tracking=2)
    N.bar(b, lst, "lsLB", LB_X0, LB_X1, LB_Y, h=6, ticks=LP_TOTAL)
    b.text("lsCur", lst, lm(DX0L, LB_Y + 70, 1000, 60), "", pt(20), GREY, tracking=3)

    # ------------------------------------------------------------ edit
    ed = b.group("ed", a, b.tl(0, 0, 3840, 2160), visible=0)["guid"]
    for i in range(SLOTS):
        g = b.group(f"sl{i}", ed, b.tl(SX0, SL_Y0 + SL_P * i, SL_RX, THUMB_H + 12))["guid"]
        b.rect(f"slHit{i}", g, b.tl(0, -10, SL_RX, THUMB_H + 30), WHITE, HIT_A)
        if i < SLOTS - 1:
            b.rect(f"slLn{i}", g, b.tl(THUMB_W / 2 - 2, THUMB_H, 4, SL_P - THUMB_H), WHITE, 90)      # the ladder's line down to the next thumbnail
        th = b.group(f"slTh{i}", g, b.tl(0, 0, THUMB_W, THUMB_H))["guid"]
        card(b, th, f"sl{i}", THUMB_W, THUMB_H)
        b.frame(f"slOu{i}", th, b.fill(), WHITE, 90, 2.0)
        gun = i < 2 or i == 6
        b.image(f"slIc{i}", th, b.ctr(THUMB_W / 2, THUMB_H / 2, 208 if gun else 136, 108), EMPTY_ICON, WHITE, scaleMode="StretchAspect")
        b.rect(f"slRuT{i}", g, b.tl(0, -14, THUMB_W, 4), WHITE, 255, visible=0)       # the active slot: white rules above and below its thumbnail
        b.rect(f"slRuB{i}", g, b.tl(0, THUMB_H + 10, THUMB_W, 4), WHITE, 255, visible=0)
        b.text(f"slLb{i}", g, lm(SL_TX, 2, 520, 60), SLOT_LABELS[i], pt(20), GREY, tracking=3)
        b.text(f"slNm{i}", g, lm(SL_TX, 62, 540, 60), "", pt(30), GREY)
        b.text(f"slCo{i}", g, lm(SL_RX - 200, 46, 200, 60, right=1), "", pt(26), GREY, align=2, tracking=2)
        N.bar(b, g, f"slB{i}", SL_TX, SL_RX, 158, h=4)
    N.section(b, ed, "edHd", OX0, OX1, LP_Y, "LARGE FIREARM", "", pts=pt(30), col=WHITE)
    for k in range(OPT_ROWS):
        g = b.group(f"op{k}", ed, b.tl(OX0, OPT_Y0 + OPT_P * k, OX1 - OX0, OPT_H))["guid"]
        b.rect(f"opHit{k}", g, b.fill(), WHITE, HIT_A)             # first child = bottom of the row's z-order (a hit rect over the name text hid names in game)
        card(b, g, f"op{k}", OX1 - OX0, OPT_H)
        N.chip(b, g, f"opEq{k}", OPT_CO_R - 236, (OPT_H - CHIP_H) / 2, "EQUIPPED", CHIP_PT, "acc", w=N.RULE_W0)      # gearup13.c sizes + moves it (gu_chip)
        for sfx in ("Bg", "Tx"):
            by = [i for i in b.items if i["name"] == f"opEq{k}{sfx}"][0]
            by["visible"] = 0
        b.image(f"opIc{k}", g, b.ctr(106, OPT_H / 2, 156, 80), EMPTY_ICON, WHITE, scaleMode="StretchAspect")
        b.text(f"opNm{k}", g, lm(OPT_NAME_X, 0, 900, OPT_H), "", pt(28), GREY)
        b.text(f"opCo{k}", g, lm(OPT_CO_R - 250, 0, 250, OPT_H, right=1), "", pt(24), GREY, align=2, tracking=1)   # right pivot: gearup13.c shrinks a long state word toward the row end
    N.scroll_v(b, ed, "opSb", SB_X, SB_Y0, SB_Y1, visible=0)       # gearup13.c scales + moves the thumb
    # the right column: loadout points
    b.text("lpTx", ed, lm(DX0, LP_Y - 30, 800, 60), "LOADOUT POINTS", pt(22), GREY, tracking=3)
    b.text("lpN", ed, lm(DX1 - 600, LP_Y - 30, 600, 60, right=1), "13 | 13", pt(28), WHITE, align=2, tracking=2)
    N.bar(b, ed, "lpB", DX0, DX1, 352, h=6, ticks=LP_TOTAL)
    dt = b.group("dt", ed, b.tl(0, 0, 3840, 2160))["guid"]
    b.image("dtIc", dt, b.tl(DX0, IC_Y, DX1 - DX0, IC_H), EMPTY_ICON, WHITE, scaleMode="StretchAspect")
    b.text("dtNm", dt, lm(DX0, NM_Y - 45, DX1 - DX0, 90), "", pt(42), WHITE, tracking=2)
    b.text("dtCo", dt, lm(DX0, CO_Y - 32, 700, 64), "", pt(28), GREY, tracking=3)
    N.chip(b, dt, "dtEq", DX0 + 160, CO_Y - CHIP_H / 2, "EQUIPPED", CHIP_PT, "acc", w=N.RULE_W0)
    for sfx in ("Bg", "Tx"):
        [i for i in b.items if i["name"] == f"dtEq{sfx}"][0]["visible"] = 0
    b.text("dtDesc", dt, b.tl(DX0, DESC_Y, DX1 - DX0, 190), "", pt(26), WHITE, multiline=1, valign=0)
    # the suppressor toggle under the description (guns with a suppressed variant): two boxes, A / D or a click switches (gearup13.c)
    tg = b.group("dtTg", dt, b.tl(0, 0, 3840, 2160), visible=0)["guid"]
    for k in range(2):
        g = b.group(f"tgB{k}", tg, b.tl(DX0 + k * (TG_W + TG_GAP), TG_Y, TG_W, TG_H))["guid"]
        b.rect(f"tgHit{k}", g, b.fill(), WHITE, HIT_A)
        card(b, g, f"tg{k}", TG_W, TG_H)
        b.text(f"tgNm{k}", g, lm(36, 20, 440, 60), ("UNSUPPRESSED", "SUPPRESSED")[k], pt(20), GREY, tracking=2)
        b.text(f"tgCo{k}", g, lm(36, 80, 440, 60), "", pt(20), GREY, tracking=2)
    st = b.group("dtSt", dt, b.tl(0, 0, 3840, 2160))["guid"]          # a gun: four stat bars (the group is hidden for anything else)
    for s in range(4):
        y = STAT_Y0 + STAT_DY * s
        b.text(f"stLb{s}", st, lm(DX0, y - 24, 700, 48), STATS[s], pt(21), GREY, tracking=3)
        b.text(f"stN{s}", st, lm(DX1 - 400, y - 24, 400, 48, right=1), "", pt(22), WHITE, align=2, tracking=2)
        N.bar(b, st, f"st{s}", DX0, DX1, y + 36, h=6, ticks=10)
    b.text("dtVar", dt, b.tl(DX0, 1880, DX1 - DX0, 60), "", pt(21), GREY, tracking=3)
    lv = b.group("dtLv", dt, b.tl(0, 0, 3840, 2160), visible=0)["guid"]     # a skill: its three levels (the equipped / shown one bright)
    for k in range(LEVELS):
        y = LV_Y0 + LV_DY * k
        b.text(f"lvHd{k}", lv, b.tl(DX0, y, DX1 - DX0, 60), "", pt(24), WHITE, tracking=3)
        b.text(f"lvTx{k}", lv, b.tl(DX0, y + 64, DX1 - DX0, 250), "", pt(24), WHITE, multiline=1, valign=0)
        b.rect(f"lvHit{k}", lv, b.tl(DX0, y - 10, DX1 - DX0, 320), WHITE, HIT_A)      # a click on a level line equips that level
    # a purchasable: the in-match prices as a small block. Row 0: [item icon in a square frame] -> price + the parts cog; row 1: [ammo icon] -> ammo pack price;
    # then "Starts with: [ammo icon] n". Row 1 / the starts line are hidden for items with no ammo (gearup13.c fills + shows them).
    pu = b.group("dtPu", dt, b.tl(0, 0, 3840, 2160), visible=0)["guid"]
    for r in range(2):
        y0 = PU_Y0 + PU_DY * r
        g = b.group(f"puRow{r}", pu, b.tl(DX0, y0, DX1 - DX0, PU_BOX))["guid"]
        b.rect(f"puBg{r}", g, b.fill(), N.TILE, N.TILE_A)
        b.frame(f"puFrame{r}", g, b.tl(0, 0, PU_BOX, PU_BOX), WHITE, 160, 2.0)
        b.image(f"puIc{r}", g, b.ctr(PU_BOX / 2, PU_BOX / 2, PU_BOX - 28, PU_BOX - 28), EMPTY_ICON, WHITE, scaleMode="StretchAspect")
        ax, ay = PU_BOX + 50, PU_BOX / 2
        b.line(f"puAr{r}", g, ax, ay, ax + 110, ay, WHITE, 190, 3.0)
        b.line(f"puAh{r}", g, ax + 110, ay, ax + 86, ay - 18, WHITE, 190, 3.0)
        b.line(f"puAh{r}b", g, ax + 110, ay, ax + 86, ay + 18, WHITE, 190, 3.0)
        b.text(f"puN{r}", g, b.tl(ax + 150, 0, 300, PU_BOX), "", 64, WHITE, align=2, tracking=2)
        b.image(f"puPart{r}", g, b.ctr(ax + 150 + 300 + 56, PU_BOX / 2, 80, 80), PARTS_ICON, WHITE, scaleMode="StretchAspect")
    b.text("puStLb", pu, b.tl(DX0, PU_Y0 + PU_DY * 2 + 6, 340, 70), "Starts with:", 40, GREY, tracking=2)
    b.image("puStIc", pu, b.ctr(DX0 + 400, PU_Y0 + PU_DY * 2 + 41, 84, 84), EMPTY_ICON, WHITE, scaleMode="StretchAspect")
    b.text("puStN", pu, b.tl(DX0 + 462, PU_Y0 + PU_DY * 2 + 6, 300, 70), "", 48, WHITE, tracking=2)

    # icon residency: 96 tiny always-visible images in the screen corner; gearup13.c puts every icon the page can show on them a few per frame after the
    # page opens (opt-in, t2r-gu-preload.txt), so the engine has streamed the textures in before the first selection
    pre = b.group("pre", a, b.tl(3820, 2140, 20, 20))["guid"]
    for i in range(96):
        b.image(f"pre{i}", pre, b.tl(0, 0, 3, 3), EMPTY_ICON, 0xFFFFFFFF, 255)

    # ------------------------------------------------------------ the NAME YOUR LOADOUT box (CREATE LOADOUT / RENAME; gearup13.c gn_*). Under the boxed prompts,
    # which read CREATE / SAVE, CANCEL, DELETE while it is open. The field is the name being typed with its cursor, prefilled CUSTOM LOADOUT n.
    nb = b.group("nb", a, b.tl(0, 0, 3840, 2160), visible=0)["guid"]
    b.rect("nbDim", nb, b.bleed(), 0xFF000000, 170)
    b.rect("nbCard", nb, b.tl(NB_X, NB_Y, NB_W, NB_H), N.TILE, 245)
    b.frame("nbFrame", nb, b.tl(NB_X, NB_Y, NB_W, NB_H), WHITE, 70, 2.0)
    b.text("nbHead", nb, lm(NB_X + 70, NB_Y + 50, NB_W - 140, 90), "NAME YOUR LOADOUT", pt(30), WHITE, tracking=3)
    b.rect("nbSep", nb, b.tl(NB_X + 70, NB_Y + 156, NB_W - 140, N.HAIR), WHITE, N.HAIR_A)
    b.rect("nbBox", nb, b.tl(NB_X + 70, NB_Y + 196, NB_W - 140, 120), N.TILE, 230)
    b.frame("nbBoxFrame", nb, b.tl(NB_X + 70, NB_Y + 196, NB_W - 140, 120), WHITE, 255, 3.0)
    b.text("nbField", nb, lm(NB_X + 110, NB_Y + 196, NB_W - 220, 120), "CUSTOM LOADOUT 7", pt(30), WHITE, tracking=3)
    b.text("nbSub", nb, lm(NB_X + 70, NB_Y + 350, NB_W - 140, 56), "UP TO 20 LETTERS", pt(20), GREY, tracking=3)
    b.text("nbHint", nb, lm(NB_X + 70, NB_Y + 418, NB_W - 140, 56), "", pt(20), GREY, tracking=3)

    N.prompt_slots(b, a)                                           # the boxed key prompts (nrui.c nr_prompts), last: above the name box's dim
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
           "9mm Pistol": G_ + "pistol-glock/glock.png",
           "Hunting Rifle": G_ + "rifle-vepr/vepr.png", "Military Sniper": G_ + "rifle-vepr/vepr.png", "Military Sniper Rifle": G_ + "rifle-vepr/vepr.png",
           "Variable Rifle": G_ + "rifle-vepr/vepr.png", "Suppressed Variable Rifle": G_ + "rifle-vepr/vepr.png", "Burst Rifle": G_ + "rifle-vepr/vepr.png",
           "Full-Auto Rifle": G_ + "rifle-vepr/vepr.png", "Pump Shotgun": G_ + "shotgun-remington-pump/remington-pump.png",
           "Double Barrel": G_ + "shotgun-baserri-over-under/baserri.png", "Crossbow": G_ + "crossbow/crossbow.png", "Bow": G_ + "bow-ellie/bow.png"}
SKI = "streaming/t2r/icons/"
SKILL_DEMO = {"Hawk-Eyed I": 7, "Sharp Ears I": 5, "Agility II": 20, "Covert Training III": 4, "Strategist I": 6, "Sharpshooter II": 10,
              "Lethal Efficiency II Extended": 25, "Wytrzymalosc fizyczna III": 11, "Quick Hands I": 22}      # name -> skill_icons.GLYPHS index
DEMO_IC.update({n: SKI + f"gu-sk{i}.png" for n, i in SKILL_DEMO.items()})
KEYS = {"back": ("ESC", "BACK", "menu:back"), "select": ("SPACE", "SELECT", "menu:select"), "ren": ("E", "RENAME", "menu:next"),
        "rst": ("R", "RESET LOADOUT", None), "move": ("W / S", "MOVE", None)}


def _est(t, p):
    """= nr_style.est / gearup13.c gu_est: capitals / digits 0.80 pt, lower case 0.62 pt, space 0.40 pt."""
    return N.est(t, p)


def _fit(item, box, floor=0.6):
    """Offline stand-in for gearup13.c gu_fit (w_scale about the left / right pivot, cut with '...' below the floor): shrinks pointSize."""
    t, p = item.get("text", ""), item["pointSize"]
    e = _est(t, p)
    sc = max(floor, box / e) if e > box else 1.0
    if e * sc > box * 1.02:
        while len(t) > 1 and _est(t + "...", p) * sc > box:
            t = t[:-1].rstrip()
        item["text"] = t + "..."
    item["pointSize"] = p * min(sc, 1.0)


class Demo:
    """a page + the setters gearup13.c uses (text / image / visible / colour / alpha); the nr_style demo_* helpers stand in for nrui.c."""

    def __init__(self, page):
        self.w = copy.deepcopy(page)
        self.by = {i["name"]: i for i in self.w["items"]}

    def vis(self, n, on):
        self.by[n]["visible"] = int(bool(on))

    def txt(self, n, s):
        self.by[n]["text"] = s

    def img(self, n, p):
        self.by[n]["path"] = p

    def col(self, n, c):
        self.by[n]["tint.start"] = self.by[n]["tint.end"] = c

    def alpha(self, n, a):
        self.by[n]["color.a"] = int(255 * a)

    def fit(self, n, box):
        _fit(self.by[n], box)

    def bar(self, name, x0, x1, frac):
        N.demo_bar(self.by, name, x0, x1, frac)

    def chip(self, base, text, right=None, left=None, ymid=0.0, tw=None):
        """gu_chip: the chip's box sized to its text, right aligned at `right` or left aligned at `left`."""
        w = _est(text, CHIP_PT) * 1.06 + 32
        x = right - w if right is not None else left
        self.txt(f"{base}Tx", text)
        bg, tx = self.by[f"{base}Bg"], self.by[f"{base}Tx"]
        bg["pivotAs.x"] = float(x); bg["rectSizeDelta.width"] = float(w)
        tx["pivotAs.x"] = float(x + 16)
        self.vis(f"{base}Bg", 1); self.vis(f"{base}Tx", 1)
        return w


def demo_prompts(d, items):
    N.demo_prompts(d.by, items)


def fill_slots(d, rows, active, col0=True):
    """rows: [(name, icon-key, lp)] x7."""
    for i, (n, ic, lp) in enumerate(rows):
        on = i == active
        d.txt(f"slNm{i}", n); d.fit(f"slNm{i}", 480)
        d.col(f"slNm{i}", WHITE if on else GREY)
        d.txt(f"slCo{i}", f"{lp} LP" if n and lp is not None else "0 LP"); d.col(f"slCo{i}", WHITE if on else GREY)
        d.img(f"slIc{i}", DEMO_IC.get(ic, NONE_ICON)); d.alpha(f"slIc{i}", 1.0 if on else 0.6)
        d.vis(f"sl{i}Fo", on); d.vis(f"slRuT{i}", on); d.vis(f"slRuB{i}", on)
        d.vis(f"sl{i}Fill", False)
        N.demo_bar(d.by, f"slB{i}", SL_TX, SL_RX, (lp or 0) / float(LP_TOTAL))


def fill_opts(d, head, rows, foc, eq):
    """rows: [(name, cost-word, dim)]; foc = focused row (None = none), eq = equipped row."""
    d.txt("edHdTx", head)
    N.demo_section(d.by, "edHd", OX0, OX1, head, "")
    for k in range(OPT_ROWS):
        d.vis(f"op{k}", k < len(rows))
        if k >= len(rows):
            continue
        n, co, dim = rows[k]
        d.txt(f"opNm{k}", n)
        d.col(f"opNm{k}", WHITE if k == foc else GREY)
        d.img(f"opIc{k}", DEMO_IC.get(n, NONE_ICON)); d.alpha(f"opIc{k}", 1.0 if k == foc else 0.55)
        is_eq = k == eq
        d.txt(f"opCo{k}", "" if is_eq else co)
        d.vis(f"op{k}Fo", k == foc)
        d.vis(f"opEq{k}Bg", is_eq); d.vis(f"opEq{k}Tx", is_eq)
        if is_eq:
            d.chip(f"opEq{k}", "EQUIPPED", right=OPT_CO_R, ymid=OPT_H / 2)
        cw = min(250.0, max(70.0, _est(co, pt(24)))) if not is_eq else 250.0
        d.fit(f"opNm{k}", OPT_CO_R - OPT_NAME_X - cw - 30)
        d.by[f"op{k}"]["color.a"] = 115 if dim else 255


def sb_state(d, n_total, off):
    on = n_total > OPT_ROWS
    d.vis("opSbT", on); d.vis("opSbH", on)
    if on:
        h = SB_Y1 - SB_Y0
        d.by["opSbH"]["rectSizeDelta.height"] = h * OPT_ROWS / n_total
        d.by["opSbH"]["pivotAs.y"] = SB_Y0 + h * off / n_total


def fill_details(d, name, cost, eq, desc, stats=None, tg=None, show_lv=None, pu=None, icon=None):
    d.txt("dtNm", name); d.fit("dtNm", DX1 - DX0)
    d.txt("dtCo", cost)
    d.img("dtIc", icon or DEMO_IC.get(name, NONE_ICON))
    cw = _est(cost, pt(28)) * 1.06
    d.vis("dtEqBg", eq); d.vis("dtEqTx", eq)
    if eq:
        d.chip("dtEq", "EQUIPPED", left=DX0 + cw + 28, ymid=CO_Y)
    d.txt("dtDesc", desc)
    d.vis("dtSt", stats is not None)
    if stats is not None:
        for s, v in enumerate(stats):
            d.txt(f"stN{s}", f"{v} | 10")
            N.demo_bar(d.by, f"st{s}", DX0, DX1, v / 10.0)
    d.vis("dtTg", tg is not None)
    if tg is not None:                       # tg = (selected 0/1, ("2 LP", "4 LP"))
        for k in range(2):
            on = tg[0] == k
            d.txt(f"tgCo{k}", tg[1][k]); d.vis(f"tg{k}Fo", on)
            d.col(f"tgNm{k}", WHITE if on else GREY)
    d.vis("dtLv", show_lv is not None)
    if show_lv:
        for k, (h, t, on) in enumerate(show_lv):
            d.txt(f"lvHd{k}", h); d.txt(f"lvTx{k}", t)
            d.alpha(f"lvHd{k}", 1.0 if on else 0.45); d.alpha(f"lvTx{k}", 1.0 if on else 0.45)
    d.vis("dtPu", pu is not None)
    if pu:
        nm, ic, am, cost, acost, start = pu
        d.img("puIc0", ic); d.txt("puN0", str(cost))
        d.vis("puRow1", acost > 0); d.vis("puStLb", start > 0); d.vis("puStIc", start > 0); d.vis("puStN", start > 0)
        if acost > 0:
            d.img("puIc1", am); d.txt("puN1", str(acost))
        if start > 0:
            d.img("puStIc", am); d.txt("puStN", str(start))


def fill_lp(d, left):
    d.txt("lpN", f"{left} | {LP_TOTAL}")
    N.demo_bar(d.by, "lpB", DX0, DX1, left / float(LP_TOTAL))


PU_DEMO = {"crossbow": ("Crossbow", G_ + "crossbow/crossbow.png", "hud/weapons/ammo/ammo-arrow_small.png", 350, 380, 4,
                        "Silent. Two body shots to down, a headshot kills. A bolt sticks in the enemy, forcing them to pull it out."),
           "machete": ("Machete", NONE_ICON, None, 150, 0, 0, "A heavy blade. Quiet and fast up close.")}


def demo(page, view):
    d = Demo(page)
    by = d.by
    named = view.startswith("list")
    d.vis("lst", named); d.vis("ed", not named)
    d.vis("nb", view in ("list-box", "edit-name"))
    if named:
        N.demo_header(by, "GEAR UP", "CHOOSE LOADOUT")
        names = [f"CUSTOM {i}" for i in range(1, 7)] + ["COMMANDO", "MARKSMAN", "SHADOW", "SUPPORT", "RECON", "BARRAGE", "SALVO", "SUPPRESSION"]
        guns = ["Variable Rifle", "Hunting Rifle", "Pump Shotgun", "Bow", "Burst Rifle", "Crossbow"] + \
               ["Full-Auto Rifle", "Hunting Rifle", "Bow", "Pump Shotgun", "Burst Rifle", "Double Barrel", "Crossbow", "Full-Auto Rifle"]
        ncust = 9 if view == "list-more" else 6
        cust_names = names[:6] if ncust == 6 else [f"CUSTOM {i}" for i in range(1, 10)]
        cust_guns = guns[:6] + ["Bow", "Revolver", "Crossbow"]
        coff = ncust + 1 - LIST_VISC if view == "list-more" else 0
        focus = {"list-custom": 0, "list": ncust + 1 + 1, "list-create": ncust, "list-more": ncust, "list-box": ncust}.get(view, ncust + 2)
        for w in range(LIST_W):
            if w < LIST_VISC:
                pos = coff + w
                ok = pos <= ncust
                is_new = pos == ncust
                nm = "+ CREATE LOADOUT" if is_new else (cust_names[pos] if ok else "")
            else:
                pos = ncust + 1 + (w - LIST_VISC)
                ok, is_new, nm = True, False, names[6 + w - LIST_VISC]
            foc = ok and pos == focus
            d.vis(f"lsRow{w}", ok)
            d.txt(f"lsName{w}", nm); d.fit(f"lsName{w}", 640)
            d.col(f"lsName{w}", WHITE if foc else GREY)
            d.vis(f"ls{w}Fo", foc); d.vis(f"ls{w}Fill", False)
            if is_new:
                tag = f"{ncust} | 12"
            elif w == 0 and coff == 0:
                tag = "EQUIPPED"
            else:
                tag = ""
            d.txt(f"lsTag{w}", tag)
            d.col(f"lsTag{w}", ACC if tag == "EQUIPPED" else WHITE if foc else GREY)
        N.demo_section(by, "lsSecC", LX0, LX1, "CUSTOM LOADOUTS", "")
        N.demo_section(by, "lsSecL", LX0, LX1, "CLASSES", "")
        n_all = ncust + 1
        sc = n_all > LIST_VISC
        d.vis("lsScT", sc); d.vis("lsScH", sc)
        if sc:
            y0, y1 = ROW_Y[0], ROW_Y[0] + ROW_P * (LIST_VISC - 1) + ROW_H
            h = by["lsScH"]
            h["pivotAs.y"] = float(y0 + (y1 - y0) * coff / n_all); h["rectSizeDelta.height"] = float((y1 - y0) * LIST_VISC / n_all)
        if view in ("list-create", "list-box"):
            d.txt("lsName", "CREATE LOADOUT")
            d.txt("lsDesc", "Make a new custom loadout. SELECT to name it, then choose its gear.")
            d.txt("lsLP", f"{LP_TOTAL - 0} | {LP_TOTAL}"); d.bar("lsLB", LB_X0, LB_X1, 1.0)
            d.txt("lsCur", ""); d.txt("lsPerk", "")
            cell = [("9mm Pistol", "9mm Pistol"), ("No Large Firearm", None), ("No Purchasable", None)] + [("", None)] * 4
        else:
            d.txt("lsName", "MARKSMAN" if view in ("list", "list-more") else "CUSTOM LOADOUT 1")
            d.txt("lsDesc", "Picks targets from afar. A hunting rifle, a Military Sniper in the back pocket, a steady aim, sharp ears and an eye for marking."
                  if view in ("list", "list-more") else "Your own loadout. SELECT to change its gear.")
            d.txt("lsLP", f"13 | {LP_TOTAL}" if view in ("list", "list-more") else f"7 | {LP_TOTAL}")
            d.bar("lsLB", LB_X0, LB_X1, 1.0 if view in ("list", "list-more") else 7 / 13.0)
            d.txt("lsCur", "THIS IS YOUR CURRENT LOADOUT" if view == "list-custom" else "")
            d.txt("lsPerk", "YOUR CLAN SENT: medkit x2 (Tyler), 4 arrows (Marlene)" if view == "list-custom" else "")
            cell = [("Revolver", "Revolver"), ("Hunting Rifle", "Hunting Rifle"), ("Military Sniper", "Military Sniper"),
                    ("Sharpshooter II", "Sharpshooter II"), ("Hawk-Eyed I", "Hawk-Eyed I"), ("Strategist I", "Strategist I"), ("Sharp Ears I", "Sharp Ears I")]
        pre = ("lg", "lg", "lg", "lsk", "lsk", "lsk", "lsk")
        for n, (nm, ic) in enumerate(cell):
            k = n if n < 3 else n - 3
            d.txt(f"{pre[n]}Nm{k}", nm); d.fit(f"{pre[n]}Nm{k}", GX1 - GX0 - GTX - 40)
            d.img(f"{pre[n]}Ic{k}", DEMO_IC.get(ic, NONE_ICON) if ic else (NONE_ICON if nm else EMPTY_ICON))
        d.fit("lsName", N.R1 - DX0L)
        if view == "list-custom":
            demo_prompts(d, [("WASD", "MOVE", 1, None), ("A", "EDIT", 1, "menu:select"), ("E", "RENAME", 1, "menu:next"), ("ESC", "BACK", 1, "menu:back")])
        elif view in ("list-create", "list-more"):
            demo_prompts(d, [("WASD", "MOVE", 1, None), ("A", "CREATE", 1, "menu:select"), ("E", "RENAME", 0, "menu:next"), ("ESC", "BACK", 1, "menu:back")])
        elif view == "list-box":
            demo_prompts(d, [("BKSP", "DELETE", 1, None), ("ENTER", "CREATE", 1, None), ("ESC", "CANCEL", 1, "menu:back")])
            d.txt("nbField", '<font color="#8C8C8C">CUSTOM LOADOUT 7</font>_'); d.txt("nbHint", "TYPE A NAME")
        else:
            demo_prompts(d, [("WASD", "MOVE", 1, None), ("A", "EQUIP", 1, "menu:select"), ("E", "RENAME", 0, "menu:next"), ("ESC", "BACK", 1, "menu:back")])
        return d.w

    # ---- edit
    N.demo_header(by, "GEAR UP", "CUSTOM LOADOUT 1")
    slots = [("Suppressed Pistol", "Suppressed Pistol", 2), ("Variable Rifle", "Variable Rifle", 2), ("Hawk-Eyed I", "Hawk-Eyed I", 2),
             ("NOTHING", None, 0), ("NOTHING", None, 0), ("NOTHING", None, 0), ("No Purchasable", None, 0)]
    keys = [("A / D", "SUPPRESSOR", 1, None), ("W / S", "MOVE", 1, None), ("E", "RENAME", 1, "menu:next"), ("R", "RESET LOADOUT", 1, None),
            ("SPACE", "SELECT", 1, "menu:select"), ("ESC", "BACK", 1, "menu:back")]
    desc = "A bolt-action rifle with a big magazine. Good at mid range."
    if view in ("edit", "edit-name", "edit-toggle-on"):
        on = view == "edit-toggle-on"
        if on:
            slots[1] = ("Suppressed Variable Rifle", "Variable Rifle", 4)
        fill_slots(d, slots, 1)
        fill_lp(d, 5 if on else 7)
        fill_opts(d, "LARGE FIREARM", [("No Large Firearm", "FREE", 0), ("Hunting Rifle", "2 LP", 0), ("Variable Rifle", "2 LP", 0), ("Bow", "3 LP", 0),
                                       ("Burst Rifle", "2 LP", 0), ("Full-Auto Rifle", "2 LP", 0), ("Pump Shotgun", "4 LP", 0), ("Double Barrel", "1 LP", 0),
                                       ("Crossbow", "3 LP", 0)], 2, 2)
        sb_state(d, 12, 0)
        fill_details(d, "Variable Rifle" if not on else "Suppressed Variable Rifle", "4 LP" if on else "2 LP", True,
                     desc + ("\nHides shots from appearing on enemy radar." if on else ""), (6, 5, 5, 7), tg=(1 if on else 0, ("2 LP", "4 LP")),
                     icon=DEMO_IC["Variable Rifle"])
        demo_prompts(d, keys)
        if view == "edit-name":
            d.txt("nbField", '<font color="#8C8C8C">CUSTOM LOADOUT 1</font>_'); d.txt("nbHint", "TYPE A NAME")
            demo_prompts(d, [("BKSP", "DELETE", 1, None), ("ENTER", "SAVE", 1, None), ("ESC", "CANCEL", 1, "menu:back")])
    elif view == "edit-locked":
        slots[1] = ("Variable Rifle", "Variable Rifle", 2)
        fill_slots(d, slots, 3)
        fill_lp(d, 0)
        fill_opts(d, "SURVIVAL SKILL 2", [("NOTHING", "FREE", 0), ("Hawk-Eyed I", "IN SKILL 1", 1), ("Sharp Ears I", "EQUIPPED", 0), ("Agility II", "ZABLOKOWANE", 1),
                                          ("Covert Training III", "5 LP", 1), ("Strategist I", "2 LP", 0), ("Sharpshooter II", "3 LP", 1),
                                          ("Lethal Efficiency II Extended", "4 LP", 1), ("Wytrzymalosc fizyczna III", "W UZYCIU", 0)], 3, 2)
        sb_state(d, 25, 0)
        fill_details(d, "Agility II", "II  LOCKED", False, "", show_lv=[("I  -  1 LP", "Move faster while crouched.", False),
                                                                        ("II  -  LOCKED", "Move faster while crouched and sprint longer.", True),
                                                                        ("III  -  LOCKED", "Not available yet.", False)], icon=DEMO_IC["Agility II"])
        demo_prompts(d, [("A / D", "LEVEL", 1, None), ("W / S", "MOVE", 1, None), ("E", "RENAME", 1, "menu:next"), ("R", "RESET LOADOUT", 1, None),
                         ("SPACE", "EQUIP", 1, "menu:select"), ("ESC", "BACK", 1, "menu:back")])
    elif view == "edit-pu":
        nm, ic, am, cost, acost, start, ds = PU_DEMO["crossbow"]
        slots[6] = ("Crossbow", "Crossbow", 3)
        fill_slots(d, slots, 6)
        fill_lp(d, 4)
        fill_opts(d, "PURCHASABLE", [("No Purchasable", "FREE", 0), ("Crossbow", "3 LP", 0), ("Explosive Bow", "3 LP", 0), ("Machete", "1 LP", 0)], 1, 1)
        sb_state(d, 4, 0)
        fill_details(d, nm, "3 LP", True, ds + "\n\nOnce bought it is yours again at every spawn.", pu=(nm, ic, am, cost, acost, start), icon=ic)
        demo_prompts(d, [("W / S", "MOVE", 1, None), ("E", "RENAME", 1, "menu:next"), ("R", "RESET LOADOUT", 1, None),
                         ("SPACE", "EQUIP", 1, "menu:select"), ("ESC", "BACK", 1, "menu:back")])
    return d.w


def preview(wdir, out_dir):
    import sys
    import tempfile
    import widget_preview
    main = json.load(open(os.path.join(wdir, "to1", "main-menu.widget.json"), encoding="utf-8"))
    page = build_page(main)
    os.makedirs(out_dir, exist_ok=True)
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "models"))
    import make_icons, real_icons
    icd = os.path.join(tempfile.gettempdir(), "gu-icons")
    os.makedirs(icd, exist_ok=True)
    import skill_icons
    for n, i in SKILL_DEMO.items():
        skill_icons.skill_icon(i).save(os.path.join(icd, f"gu-sk{i}.png"))
    real_icons.MOD_DIRS.append(icd)
    make_icons.hud_counter_icon("parts").save(os.path.join(icd, "hud-parts.png"))
    bg = N.preview_bg(os.path.join(icd, "gu-bg.png"))
    for view in ("edit", "edit-locked", "edit-pu", "edit-name", "edit-toggle-on", "list", "list-custom", "list-create", "list-more", "list-box"):
        tmp = os.path.join(tempfile.gettempdir(), f"t2r-gearup13-{view}.widget.json")
        json.dump(demo(page, view), open(tmp, "w", encoding="utf-8"))
        print(widget_preview.render(tmp, os.path.join(out_dir, f"gearup13-{view}.png"), bg=bg))
    n = len(page["items"])
    print("widgets on the page:", n)


if __name__ == "__main__":
    import sys
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    preview(sys.argv[1], sys.argv[2])
