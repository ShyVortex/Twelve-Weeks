"""The in-game CLAN page, built like GEAR UP (gearup13_widgets.py): one page to1/clan13 with the match-flow backdrop, fonts, colours and footer prompts,
driven entirely by t2r-ext clan13.c from daemon op 0xB6 / 0xB7 (tools/clan_ingame.py). The LOOK TARGET is the launcher CLAN tab:
WLF / WEEK n: DAY n big with the day-progress line top right; STATUS UPDATES "since you last looked" (cards: portrait
on a state-coloured tile, role, name, coloured state with icon, one line, READ IN THE JOURNAL, NEW); SUPPLIES (icon + number + days per need, THE STOCK LASTS n DAYS);
CAMP MORALE line with the state word; SURVIVORS grid, 4 columns; RAIDS (map rows, SUPPLIES BROUGHT HOME n / m NEEDED, the verdict box, bars with the need tick, loot cards).
The launcher scrolls one long page; a widget page cannot clip a scroll, so the same blocks are four tabs of one page:

  header   WLF / WEEK n: DAY d | day-progress line + "9 OF 84 DAYS SURVIVED - WEEK 2 OF 12" | tabs OVERVIEW SURVIVORS RAIDS JOURNAL | thin rule
  "ov"     STATUS UPDATES (4 cards) | SUPPLIES (5 tiles) | CAMP (morale line, clans won / lost)
  "sv"     SURVIVORS (4 x 5 cells, scrolls) | the focused member (tagline, CLOSE TO, LATELY)
  "rds"    RAIDS (4 rows) | the focused raid (brought home, verdict, 4 bars with the need tick, loot cards)
  "jrn"    JOURNAL: < WEEK n OF 12 > and its 7 day entries | the focused day: headline, the day's facts, its paragraphs
  "mst"    MATCH STATS, the flat list: over the RAIDS tab, F / the pad's menu-action on a raid lists every player of that match (t2r-clan-xs-old.txt keeps it)
  "mst2"   PLAYER STATS: the same opening, US and THE ENEMY sections of tall rows - face (the award's expression), role word, MOST <STAT>, name, the stat columns, PARTS
           (also opened by the RAIDS header button "rdBtn", SELECT / A on a raid, and the footer prompt)
  prompts  BACK / SELECT / NEXT TAB / PLAYER STATS (+ a hint line)

Portraits: just the head (soft edges baked into the PNG, tools/models/portrait_soft.py), no tile behind them. Widget space 3840 x 2160. Every changing text / image / visibility /
alpha / offset is written by the ext; names are unique page-wide. python clan13_widgets.py <extracted widget dir> <out dir> [db] renders previews (CPU, PIL)."""
import copy
import json
import os
import t2guid

from clan_widgets import Builder, _templates, SUPPLY_BLUE, PM_TEXT, PM_DIM
from matchflow_widgets import TEXT, CREAM
import rank_badge_widgets
from gearup13_widgets import tlm      # a box with its pivot at the left middle: clan13.c shrinks a too-long name about it (gu_fit)

PAGE = "clan13"
PANEL = "streaming/t2r/clan/gearup-panel.png"          # the scratched dark backdrop of GEAR UP (ship.py)
TITLE = 0xFFD8D4CC
LABEL = 0xFFB4B4B4
DIM = 0xFF8D897B
HIT_A = 1
CARD_A, EDGE_A, FOCUS_A, HILITE_A = 150, 46, 190, 16
GOOD, WARN, BAD, INFO = 0xFF7CB494, 0xFFE0B04A, 0xFFFD6D51, 0xFF3FA9F5
GREY = 0xFF9C9A9A
TONES = ("", "good", "warn", "bad", "info")             # band colours of a card: neutral cream, green, amber, red, blue
TONE_COL = (CREAM, GOOD, WARN, BAD, INFO)
BAND_IMG, DOT_IMG = "streaming/t2r/icons/c13-band%d.png", "streaming/t2r/icons/c13-dot%d.png"
# the launcher's status colours (clan-status.js COLOR; order = clan_status.NAMES: healthy hungry sad sick dead injured recovered new depressed shock)
ST_COL = (0xFF4FB04A, 0xFFE0A21A, 0xFF2F66D6, 0xFFC4202B, 0xFF353C47, 0xFFD9741F, 0xFF4FB04A, 0xFF2AA8D0, 0xFF5B6B7B, 0xFF8FA3B5)
NST, NSV, NJRN, NTHR, NRDS, NTILE, NLOOT, NBAR = 4, 20, 4, 4, 4, 5, 4, 4
NREC, REC_DY = 4, 68
# the JOURNAL tab: 7 day rows of the shown week (clan13.c C13_JD_ROWS) + the reading pane with up to 5 paragraphs (C13_JP)
NJD, JD_Y0, JD_DY, JD_W, JD_H = 7, 540, 176, 1280, 166
JD_TONE_COL = (CREAM, GOOD, WARN, BAD)                  # a day row's band: neutral, a good day, a hard day, a bad day
NJP, JT_X, JT_W, JT_Y0, JT_PT, JT_LINE, JT_CAP_H, JT_GAP, JT_Y1 = 5, 1700, 1840, 776, 36, 62, 44, 30, 1810      # (line pitch ~1.71 x the point size: widget_preview.GAME_TEXT_SCALE)
OVST = 2                                                # the overview shows the newest 2 status cards (one row); clan13.c C13_OVST
X0, X1 = 300, 3540
TAB_X = (300, 720, 1160, 1450, 1820)
TAB_W = (300, 335, 190, 260, 300)
TAB_NAMES = ("OVERVIEW", "SURVIVORS", "RAIDS", "JOURNAL", "MISSIONS")
NMS = 8                                                 # mission rows (clan13.c C13_MS_ROWS)
MS_X, MS_W, MS_Y0, MS_DY, MS_H = 300, 1280, 540, 112, 100
RUN_X, RUN_Y, RUN_W, RUN_H = 300, 559, 3240, 535        # the running mission's header card (layout A); the bar spans BAR_L.. +BAR_W2, 3 tier cards RT_W wide under it
BAR_L, BAR_W2, BAR_T = 384, 3072, 982
RT_Y, RT_W, RT_GAP, RT_H = 1171, 1050, 45, 365
DT_X, DT_W = 1900, 1640
ST_W, ST_H, ST_Y0, ST_DY = 1580, 270, 540, 300          # status cards: 2 columns, x = X0 + col * 1660
SV_W, SV_H, SV_X, SV_Y0, SV_DX, SV_DY = 780, 150, 300, 520, 820, 170     # survivors grid: 4 columns x 5 rows
JC_Y0, JC_DY, JC_W, JC_H = 440, 350, 1280, 344         # journal cards (a story: caption, title, 2 body lines, then up to 3 small timeline lines of the one-liners that follow it)
RR_Y0, RR_DY, RR_W, RR_H = 565, 110, 3240, 104         # raid rows
TL_W, TL_Y = 620, 1290                                  # supply tile width (5 x 620 + 4 x 35 = 3240), top
MO_X, MO_W, MO_Y = 760, 1500, 1700                       # the camp morale bar
MO_COL = (0xFFF2625A, 0xFFF0B429, 0xFF7FA8F5, 0xFF7FD07A)   # grim, strained, steady, hopeful (the launcher's --mc)
HB_X, HB_W, HB_Y = 2440, 1100, 205                      # the header's day-progress line
BAR_X, BAR_W = 760, 1900                                # raid detail bars
NXS, XS_Y0, XS_DY, XS_H = 12, 650, 88, 80               # MATCH STATS rows (clan13.c C13_NX)
XS_COLS = (("KILLS", 1760, 250), ("DOWNS", 2030, 250), ("DEATHS", 2300, 250), ("REVIVES", 2570, 250), ("EXECUTIONS", 2900, 330), ("HEADSHOTS", 3200, 300), ("PARTS", 3490, 220))     # label, right edge, width
BAR_Y0, BAR_DY = 1180, 88
# MATCH STATS v2 (concept.png): US / THE ENEMY sections, 4 tall rows each (portrait, role word, MOST <X> header, name; the stat columns; PARTS)
XP_Y, XP_H = 402, 1448                                  # the panel
# PLAYER STATS scoreboard geometry (units of the 3840 x 2160 widget space; rows are positioned by clan13.c cl13_fill_xp, the numbers below are its design values)
XP_NROW = 12                                            # the row pool = C13_NX
XP_RH, XP_PITCH = 104, 112                              # a row: height, pitch (up to 8 players; clan13.c squeezes to 76 / 80 above that)
XP_HD_Y = 528                                           # the column heads
XP_SEC_Y = 616                                          # the design position of a team's section row (US); the ENEMY's one is moved down by the client
XP_R0 = 720                                             # the design position of the first player row
XP_NAME_X, XP_AW_X = 171, 980                           # row-relative: the name (after the rank badge: rank_badge_widgets.reserved(40, 104)), the award word
XP_COL_R = (1780, 2048, 2316, 2584, 2852)               # right edges (row-relative) of DOWNS EXECUTIONS REVIVES HEADSHOTS DEATHS; PARTS follows at X1 - 110
XP_HEADS = ("DOWNS", "EXECUTIONS", "REVIVES", "HEADSHOTS", "DEATHS")
XP_COL_W = 260
# the stat colours (clan13.h stat: 0 downs, 1 executions, 2 revives, 3 headshots, 4 parts, 5 deaths)
XP_COL = (0xFFF08A33, 0xFFE0B04A, 0xFF7FA8F5, 0xFF55C6E8, 0xFF5FD068, 0xFFA9AFB8)
XP_RED = 0xFFE0443A


def ov_stack(nu, ns, nrec):
    """Offsets (y) of the overview blocks. Design tops: status 424, supplies 1170, camp 1560, recent 0. Heights: status = title + rows of cards (86 + 300 * rows ... 100 with none),
    supplies = 340 with tiles / 150 with the one muted line, camp 220; gap 60. -> (supplies offset, camp offset, recent top, recent rows shown)."""
    rows = (nu + 1) // 2
    st_h = 100 if rows == 0 else 116 + (rows - 1) * 300 + 270
    sup_top = 424 + st_h + 60
    sup_h = 340 if ns else 150
    camp_top = sup_top + sup_h + 60
    rec_top = camp_top + 230 + 40
    room = (1830 - rec_top - 100) // REC_DY
    return sup_top - 1170, camp_top - 1560, rec_top, max(0, min(nrec, NREC, room))


def edge(b, p, i, g, w, h):
    """card pieces: dark panel, a thin always-visible edge (the launcher's 1 px border), hidden focus fill + frame."""
    b.rect(f"{p}Card{i}", g, b.fill(), 0xFF000000, CARD_A)
    b.frame(f"{p}Edge{i}", g, b.fill(), 0xFFFFFFFF, EDGE_A, 2.0)
    b.rect(f"{p}Fill{i}", g, b.fill(), 0xFFFFFFFF, HILITE_A, visible=0)
    b.frame(f"{p}Frame{i}", g, b.fill(), 0xFFFFFFFF, FOCUS_A, 3.0, visible=0)


def bands(b, p, i, g, h):
    b.image(f"{p}Bd{i}", g, b.tl(0, 0, 8, h), BAND_IMG % 0, 0xFFFFFFFF, 230)         # ONE image per card, the ext swaps its texture to the tone's (c13-band0..4: the page is at gui2's 1024-widget limit)


def portrait(b, g, name, x, y, w, h=None):
    """A portrait slot: only the picture (soft edges baked in), path set at run time."""
    b.image(f"{name}Im", g, b.tl(x, y, w, h or w), "streaming/t2r/icons/c13p-100_neutral.png", 0xFFFFFFFF, 255, scaleMode="StretchAspect", visible=0)


def tag_new(b, g, name, x, y):
    b.rect(f"{name}Bg", g, b.tl(x, y, 96, 40), SUPPLY_BLUE, 255, visible=0)
    b.text(f"{name}Tx", g, b.tl(x, y, 96, 40), "NEW", 28, 0xFF101418, align=1, tracking=2, visible=0)


def build_page(main):
    t, root0, anim0 = _templates(main)
    b = Builder(t)
    root = copy.deepcopy(root0); root.update(guid=t2guid.guid())
    anim = copy.deepcopy(anim0); anim.update(guid=t2guid.guid(), parent=root["guid"])
    b.items += [root, anim]
    a = anim["guid"]
    b.image("bgBlur", a, b.bleed(), "general-textures/blur-background.png", 0xFFFFFFFF, 255)
    b.rect("bgDark", a, b.bleed(), 0xFF0B0C0D, 90)
    b.image("bgPanel", a, b.tl(0, 0, 3840, 2160), PANEL, 0xFFFFFFFF, 255)

    # ---------------------------------------------------------------- header (WLF / WEEK n: DAY n + the day-progress line)
    hd = b.group("hd", a, b.tl(0, 0, 3840, 2160))["guid"]
    b.text("hdFac", hd, b.tl(X0, 90, 900, 44), "", 32, LABEL, face="Alternate", tracking=8)
    b.text("hdWeek", hd, b.tl(X0 - 4, 126, 1800, 150), "", 104, TITLE, tracking=4)
    b.rect("hdBarBg", hd, b.tl(HB_X, HB_Y, HB_W, 8), 0xFFFFFFFF, 40)
    b.rect("hdBar", hd, {**b.tl(HB_X, HB_Y, HB_W, 8), "pivotN.x": 0.0, "pivotN.y": 0.5, "pivotAs.x": float(HB_X), "pivotAs.y": float(HB_Y + 4)}, 0xFF7FA8F5, 255)
    for k in range(1, 12):
        b.rect(f"hdTk{k}", hd, b.tl(HB_X + HB_W * k / 12.0 - 1, HB_Y - 4, 3, 16), 0xFFFFFFFF, 110)
    b.text("hdTxt", hd, b.tl(HB_X - 400, HB_Y + 24, HB_W + 400, 46), "", 32, LABEL, face="Alternate", align=2, tracking=4)
    tb = b.group("tabs", a, b.tl(0, 0, 3840, 2160))["guid"]
    for k in range(5):
        b.text(f"tab{k}", tb, b.tl(TAB_X[k], 292, 420, 80), TAB_NAMES[k], 46, TEXT, tracking=4)
        b.rect(f"tabU{k}", tb, b.tl(TAB_X[k], 352, 100, 5), SUPPLY_BLUE, 255, visible=0)
    b.line("tabRule", tb, X0, 392, X1, 392, 0xFFFFFFFF, 130, 2.0)
    b.text("ldTx", a, b.tl(X0, 900, X1 - X0, 200), "", 52, PM_DIM, align=1, tracking=4, multiline=1, visible=0)

    # ---------------------------------------------------------------- OVERVIEW: four blocks (status updates, supplies, camp, recently in camp) that clan13.c STACKS
    # (each block's top = the previous block's bottom + a gap, by writing the group's offset: ov_stack below), so no combination of 0 - 4 updates / with or without supplies overlaps
    ov = b.group("ov", a, b.tl(0, 0, 3840, 2160))["guid"]
    sg = b.group("ovSt", ov, b.tl(0, 0, 3840, 2160))["guid"]
    b.text("ovStTitle", sg, b.tl(X0, 424, 1500, 80), "", 54, TEXT, tracking=3)
    b.text("ovStSub", sg, b.tl(X0 + 780, 450, 2400, 46), "", 30, DIM, face="Alternate", tracking=7)
    for i in range(NST):
        x, y = X0 + (i % 2) * 1660, ST_Y0 + (i // 2) * ST_DY
        g = b.group(f"stRow{i}", sg, b.tl(x, y, ST_W, ST_H))["guid"]
        edge(b, "st", i, g, ST_W, ST_H)
        for q, col in enumerate(ST_COL):
            b.rect(f"stTn{q}_{i}", g, b.tl(0, 0, 270, ST_H), col, 215, visible=0)
        portrait(b, g, f"stPt{i}", 0, 0, 270, ST_H)
        b.rect(f"stEd{i}", g, b.tl(300, 30, 4, ST_H - 60), 0xFFFFFFFF, 60)
        b.text(f"stRole{i}", g, b.tl(326, 12, 700, 38), "", 28, DIM, face="Alternate", tracking=8)
        b.text(f"stName{i}", g, tlm(326, 50, 760, 76), "", 58, TEXT, tracking=2)
        b.image(f"stIc{i}", g, b.tl(326, 152, 38, 38), "streaming/t2r/icons/c13-pills.png", CREAM, 255, scaleMode="StretchAspect", visible=0)
        b.text(f"stWord{i}", g, b.tl(376, 148, 700, 46), "", 34, TEXT, tracking=5)
        b.text(f"stLine{i}", g, tlm(326, 208, ST_W - 360, 44), "", 34, PM_TEXT, tracking=1)
        b.text(f"stRead{i}", g, b.tl(ST_W - 800, 152, 770, 40), "", 26, SUPPLY_BLUE, face="Alternate", align=2, tracking=6)
        tag_new(b, g, f"stNew{i}", ST_W - 120, 16)
    lw = b.group("ovSup", ov, b.tl(0, 0, 3840, 2160))["guid"]
    b.text("ovSupTitle", lw, b.tl(X0, 1170, 1400, 80), "", 54, TEXT, tracking=3)
    b.text("ovSupNone", lw, b.tl(X0, 1262, 3240, 50), "", 32, DIM, face="Alternate", tracking=5)
    b.text("ovLastLb", lw, b.tl(1900, 1194, 1100, 46), "", 32, DIM, face="Alternate", align=2, tracking=6)
    b.text("ovLast", lw, b.tl(3000, 1150, 540, 120), "", 90, TEXT, align=2, tracking=2)
    for k in range(NTILE):
        g = b.group(f"tlRow{k}", lw, b.tl(X0 + k * (TL_W + 35), TL_Y, TL_W, 220))["guid"]
        edge(b, "tl", k, g, TL_W, 220)
        b.image(f"tlIc{k}", g, b.tl(24, 40, 100, 100), "streaming/t2r/icons/c13-food.png", CREAM, 255, scaleMode="StretchAspect")
        b.text(f"tlLb{k}", g, b.tl(150, 18, 440, 40), "", 28, DIM, face="Alternate", tracking=7)
        b.text(f"tlNum{k}", g, b.tl(150, 52, 440, 100), "", 80, TEXT, tracking=2)
        b.text(f"tlDays{k}", g, b.tl(24, 158, 560, 48), "", 32, PM_TEXT, tracking=5)
    cg = b.group("ovCamp", ov, b.tl(0, 0, 3840, 2160))["guid"]
    b.text("ovCampTitle", cg, b.tl(X0, 1560, 1000, 80), "", 54, TEXT, tracking=3)
    b.text("ovClans", cg, b.tl(1500, 1588, 2040, 46), "", 32, DIM, face="Alternate", align=2, tracking=5)
    mo = b.group("mo", cg, b.tl(0, 0, 3840, 2160))["guid"]
    b.text("moLb", mo, b.tl(X0, MO_Y - 28, 440, 50), "", 30, DIM, face="Alternate", tracking=7)
    b.rect("moBg", mo, b.tl(MO_X, MO_Y - 2, MO_W, 14), 0xFFB4B4B4, 95)
    for k, col in enumerate(MO_COL):
        b.rect(f"moFill{k}", mo, {**b.tl(MO_X, MO_Y, MO_W, 12), "pivotN.x": 0.0, "pivotN.y": 0.5, "pivotAs.x": float(MO_X), "pivotAs.y": float(MO_Y + 5)}, col, 255, visible=0)
    for k, v in enumerate((30, 50, 70)):
        b.rect(f"moTk{k}", mo, b.tl(MO_X + MO_W * v / 100.0 - 2, MO_Y - 10, 4, 32), 0xFFFFFFFF, 120)
    b.rect("moPin", mo, b.tl(MO_X - 5, MO_Y - 22, 10, 56), 0xFFFFFFFF, 255)
    b.text("moWord", mo, b.tl(MO_X + MO_W + 50, MO_Y - 30, 800, 64), "", 46, TEXT, tracking=6)
    rg = b.group("ovRec", ov, b.tl(0, 0, 3840, 2160))["guid"]       # OSTATNIO W OBOZIE: the newest journal headlines with their day (coordinates relative to the block's top)
    b.text("ovRecTitle", rg, b.tl(X0, 0, 2000, 80), "", 54, TEXT, tracking=3)
    for i in range(NREC):
        y = 100 + REC_DY * i
        b.text(f"ovRecDay{i}", rg, b.tl(X0, y, 280, 52), "", 30, DIM, face="Alternate", tracking=6)
        b.text(f"ovRecTx{i}", rg, tlm(X0 + 300, y, 2900, 52), "", 38, TEXT, tracking=2)
        b.line(f"ovRecLn{i}", rg, X0, y + 60, X1, y + 60, 0xFFFFFFFF, 40, 2.0)

    # ---------------------------------------------------------------- SURVIVORS
    sv = b.group("sv", a, b.tl(0, 0, 3840, 2160), visible=0)["guid"]
    b.text("svTitle", sv, b.tl(X0, 424, 1500, 80), "", 54, TEXT, tracking=3)
    for i in range(NSV):
        x, y = SV_X + (i % 4) * SV_DX, SV_Y0 + (i // 4) * SV_DY
        g = b.group(f"svRow{i}", sv, b.tl(x, y, SV_W, SV_H))["guid"]
        edge(b, "sv", i, g, SV_W, SV_H)
        portrait(b, g, f"svPt{i}", 14, 12, 124, 124)
        for k, col in enumerate((0xFF4FB04A, 0xFFE0A21A, 0xFFC4202B, 0xFF5B6B7B, 0xFF8FA3B5)):
            b.rect(f"svBar{k}_{i}", g, b.tl(18, 138, 116, 4), col, 255, visible=0)
        b.text(f"svRole{i}", g, b.tl(164, 8, 580, 34), "", 26, DIM, face="Alternate", tracking=7)
        b.text(f"svName{i}", g, tlm(164, 40, 580, 54), "", 42, TEXT, tracking=2)
        b.image(f"svIc{i}", g, b.tl(164, 104, 30, 30), "streaming/t2r/icons/c13-pills.png", CREAM, 255, scaleMode="StretchAspect", visible=0)
        b.text(f"svWord{i}", g, b.tl(202, 100, 560, 40), "", 28, TEXT, tracking=5)
        tag_new(b, g, f"svNew{i}", SV_W - 110, 10)
    dt = b.group("svDt", sv, b.tl(0, 0, 3840, 2160))["guid"]
    b.line("svDtRule", dt, X0, 1390, X1, 1390, 0xFFFFFFFF, 70, 2.0)
    portrait(b, dt, "svDt", X0, 1410, 330, 330)
    b.text("svDtName", dt, tlm(680, 1420, 1100, 100), "", 72, TEXT, tracking=3)
    b.text("svDtSub", dt, tlm(680, 1530, 1100, 56), "", 38, SUPPLY_BLUE, tracking=4)
    b.text("svDtTag", dt, b.tl(680, 1610, 1100, 180), "", 36, PM_TEXT, multiline=1, valign=0)
    b.text("svDtCloseLb", dt, b.tl(1950, 1426, 700, 42), "", 30, DIM, face="Alternate", tracking=7)
    portrait(b, dt, "svDtB", 1950, 1475, 110)
    b.text("svDtBond", dt, tlm(2090, 1480, 700, 56), "", 44, TEXT, tracking=2)
    b.text("svDtBondTy", dt, b.tl(2090, 1538, 700, 44), "", 30, SUPPLY_BLUE, tracking=5)
    b.text("svDtLatelyLb", dt, b.tl(1950, 1616, 700, 42), "", 30, DIM, face="Alternate", tracking=7)
    b.text("svDtLately", dt, b.tl(1950, 1665, 1590, 150), "", 34, PM_TEXT, multiline=1, valign=0)

    # ---------------------------------------------------------------- RAIDS
    rd = b.group("rds", a, b.tl(0, 0, 3840, 2160), visible=0)["guid"]
    b.text("rdTitle", rd, b.tl(X0, 410, 1500, 80), "", 54, TEXT, tracking=3)
    b.text("rdHint", rd, b.tl(X0, 500, 2900, 46), "", 30, DIM, face="Alternate", tracking=5)
    bt = b.group("rdBtn", rd, b.tl(0, 0, 3840, 2160), visible=0)["guid"]          # the way in to the match's player stats, in plain sight (the F prompt in the footer was not found)
    b.rect("rdBtnBg", bt, b.tl(2480, 404, 1060, 88), 0xFFFFFFFF, 22)
    b.frame("rdBtnFr", bt, b.tl(2480, 404, 1060, 88), 0xFFFFFFFF, 150, 3.0)
    b.image("rdBtnIc", bt, b.tl(2504, 420, 56, 56), "menu:action", 0xFFFFFFFF)
    b.text("rdBtnTx", bt, b.tl(2590, 410, 930, 76), "", 40, TEXT, tracking=4)
    b.rect("rdBtnHit", bt, b.tl(2480, 380, 1060, 168), 0xFFFFFFFF, HIT_A)
    for i in range(NRDS):
        g = b.group(f"rrRow{i}", rd, b.tl(X0, RR_Y0 + i * RR_DY, RR_W, RR_H))["guid"]
        edge(b, "rr", i, g, RR_W, RR_H)
        bands(b, "rr", i, g, RR_H)
        b.text(f"rrDay{i}", g, tlm(40, 26, 230, 52), "", 28, DIM, face="Alternate", tracking=7)      # inline before the map name (above it, it sat on the row's top border)
        b.text(f"rrMap{i}", g, tlm(290, 26, 800, 52), "", 42, TEXT, tracking=2)
        b.rect(f"rrBarBg{i}", g, b.tl(1500, 62, 900, 10), 0xFFFFFFFF, 40)
        b.rect(f"rrBar{i}", g, {**b.tl(1500, 62, 900, 10), "pivotN.x": 0.0, "pivotN.y": 0.5, "pivotAs.x": 1500.0, "pivotAs.y": 67.0}, GOOD, 255)
        b.text(f"rrWl{i}", g, b.tl(2400, 12, 540, 40), "", 28, GREY, face="Alternate", align=2, tracking=6)
        b.text(f"rrNum{i}", g, b.tl(2960, 22, 240, 60), "", 48, GOOD, align=2, tracking=2)
        tag_new(b, g, f"rrNew{i}", 1120, 30)
        b.rect(f"rrHit{i}", g, b.fill(), 0xFFFFFFFF, HIT_A)
    dd = b.group("rdDt", rd, b.tl(0, 0, 3840, 2160))["guid"]
    b.line("rdRule", dd, X0, 1010, X1, 1010, 0xFFFFFFFF, 70, 2.0)
    b.text("rdDtLb", dd, b.tl(X0 + 40, 1088, 700, 46), "", 30, DIM, face="Alternate", tracking=7)
    b.text("rdDtBig", dd, b.tl(1060, 1030, 340, 170), "", 140, TEXT, tracking=2)
    b.text("rdDtOf", dd, b.tl(1400, 1100, 700, 80), "", 44, PM_TEXT, tracking=3)
    b.frame("rdVerdFr", dd, b.tl(2780, 1050, 760, 110), GOOD, 255, 4.0)
    b.frame("rdVerdFrS", dd, b.tl(2780, 1050, 760, 110), WARN, 255, 4.0, visible=0)
    b.text("rdVerd", dd, b.tl(2780, 1050, 760, 110), "", 40, TEXT, align=1, tracking=3)
    for k in range(NBAR):
        y = BAR_Y0 + BAR_DY * k
        b.image(f"rdBIc{k}", dd, b.tl(X0 + 40, y + 12, 60, 60), "streaming/t2r/icons/c13-food.png", CREAM, 255, scaleMode="StretchAspect")
        b.text(f"rdBLb{k}", dd, b.tl(X0 + 130, y + 12, 340, 60), "", 30, DIM, face="Alternate", tracking=7)
        b.rect(f"rdBBg{k}", dd, b.tl(BAR_X, y + 36, BAR_W, 12), 0xFFFFFFFF, 40)
        b.rect(f"rdB{k}", dd, {**b.tl(BAR_X, y + 36, BAR_W, 12), "pivotN.x": 0.0, "pivotN.y": 0.5, "pivotAs.x": float(BAR_X), "pivotAs.y": float(y + 42)}, GOOD, 255)
        b.rect(f"rdBNeed{k}", dd, b.tl(BAR_X, y + 22, 4, 40), 0xFFFFFFFF, 255)
        b.text(f"rdBNum{k}", dd, b.tl(2740, y + 10, 260, 64), "", 44, TEXT, align=2, tracking=2)
        b.text(f"rdBDelta{k}", dd, b.tl(3040, y + 14, 200, 54), "", 32, DIM, tracking=3)
    b.text("rdLootLb", dd, b.tl(X0 + 40, 1544, 1000, 42), "", 30, DIM, face="Alternate", tracking=7)
    for k in range(NLOOT):
        g = b.group(f"ltRow{k}", dd, b.tl(X0 + k * 820, 1592, 780, 176))["guid"]
        edge(b, "lt", k, g, 780, 176)
        b.rect(f"ltEd{k}", g, b.tl(0, 0, 4, 176), CREAM, 150)
        b.image(f"ltIc{k}", g, b.tl(24, 43, 90, 90), "streaming/t2r/icons/c13-keepsake.png", CREAM, 255, scaleMode="StretchAspect")
        b.text(f"ltQty{k}", g, b.tl(140, 12, 400, 56), "", 40, TEXT, tracking=2)
        b.text(f"ltNm{k}", g, b.tl(140, 66, 620, 100), "", 28, PM_TEXT, multiline=1, valign=0)
        tag_new(b, g, f"ltNew{k}", 660, 10)

    # ---------------------------------------------------------------- JOURNAL: week pages. Left: the week (< WEEK n OF 12 >) and its day entries, one row a day;
    # right: the focused day - headline, the day's facts, then its paragraphs (THE RAID / SUPPLIES / THE CAMP / the event / NOTES), stacked by clan13.c (cl13_fill_jr_day).
    jr = b.group("jrn", a, b.tl(0, 0, 3840, 2160), visible=0)["guid"]
    b.text("jwPrev", jr, b.tl(X0, 424, 90, 80), "<", 60, TEXT, align=1)
    b.text("jwTitle", jr, b.tl(X0 + 100, 424, 620, 80), "", 54, TEXT, align=1, tracking=3)
    b.text("jwNext", jr, b.tl(X0 + 730, 424, 90, 80), ">", 60, TEXT, align=1)
    b.text("jwSub", jr, b.tl(X0 + 830, 446, JD_W - 830, 46), "", 28, DIM, face="Alternate", align=2, tracking=5)
    b.rect("jwPrevHit", jr, b.tl(X0 - 10, 414, 120, 100), 0xFFFFFFFF, HIT_A)
    b.rect("jwNextHit", jr, b.tl(X0 + 715, 414, 120, 100), 0xFFFFFFFF, HIT_A)
    for i in range(NJD):
        g = b.group(f"jdRow{i}", jr, b.tl(X0, JD_Y0 + JD_DY * i, JD_W, JD_H))["guid"]
        edge(b, "jd", i, g, JD_W, JD_H)
        b.image(f"jdBd{i}", g, b.tl(0, 0, 8, JD_H), BAND_IMG % 0, 0xFFFFFFFF, 230)       # ONE band image per day row, the ext swaps its texture (c13-band0..3 = JD_TONE_COL): the page is at gui2's 1024-widget limit
        b.text(f"jdDay{i}", g, b.tl(36, 18, 300, 42), "", 28, DIM, face="Alternate", tracking=6)
        b.text(f"jdRes{i}", g, b.tl(JD_W - 836, 18, 800, 42), "", 28, DIM, face="Alternate", align=2, tracking=5)
        b.text(f"jdTi{i}", g, tlm(36, 72, JD_W - 72, 72), "", 46, TEXT, tracking=2)
        tag_new(b, g, f"jdNew{i}", 250, 18)
    jt = b.group("jtPane", jr, b.tl(0, 0, 3840, 2160))["guid"]
    b.line("jtDiv", jt, 1650, 440, 1650, 1800, 0xFFFFFFFF, 70, 2.0)
    b.text("jtLb", jt, b.tl(JT_X, 428, JT_W, 50), "", 30, DIM, face="Alternate", tracking=6)
    b.text("jtTitle", jt, tlm(JT_X, 484, JT_W, 110), "", 72, TEXT, tracking=3)
    b.text("jtF0", jt, b.tl(JT_X, 606, JT_W, 52), "", 34, PM_TEXT, tracking=3)
    b.text("jtF1", jt, b.tl(JT_X, 662, JT_W, 52), "", 34, PM_TEXT, tracking=3)
    b.line("jtRule", jt, JT_X, 740, JT_X + JT_W, 740, 0xFFFFFFFF, 70, 2.0)
    for k in range(NJP):
        b.text(f"jtCap{k}", jt, b.tl(JT_X, JT_Y0 + 200 * k, JT_W, 40), "", 28, DIM, face="Alternate", tracking=7)
        b.text(f"jtBo{k}", jt, b.tl(JT_X, JT_Y0 + 200 * k + JT_CAP_H, JT_W, 1000), "", JT_PT, PM_TEXT, multiline=1, valign=0)

    # ---------------------------------------------------------------- MISSIONS: the 2013 CHOOSE MISSION pick (the old to1/mission-choose page) in the clan page's look; clan13.c fills it from meta (feature_missions' data)
    ms = b.group("ms", a, b.tl(0, 0, 3840, 2160), visible=0)["guid"]
    b.text("msTitle", ms, b.tl(X0, 424, 1500, 80), "", 54, TEXT, tracking=3)
    b.text("msSub", ms, b.tl(X0 + 840, 450, 2400, 46), "", 30, DIM, face="Alternate", tracking=7)
    for i in range(NMS):
        g = b.group(f"msRow{i}", ms, b.tl(MS_X, MS_Y0 + i * MS_DY, MS_W, MS_H))["guid"]
        edge(b, "ms", i, g, MS_W, MS_H)
        b.text(f"msNm{i}", g, tlm(36, 24, 860, 52), "", 44, TEXT, tracking=2)
        b.text(f"msRp{i}", g, b.tl(MS_W - 400, 30, 370, 40), "", 26, DIM, face="Alternate", align=2, tracking=6)
        b.rect(f"msHit{i}", g, b.fill(), 0xFFFFFFFF, HIT_A)
    # the RUNNING mission (layout A): ONE wide header card (icon, mission name, the event line, MATCH n OF 3 + 3 pips, the live count, ONE progress bar with the 3 tier ticks)
    # and 3 tier cards (state icon, goal, reward as icons + numbers) - clan13.c cl13_fill_ms_run fills it; the pick list's widgets are hidden meanwhile
    pg = b.group("msPrg", ms, b.tl(0, 0, 3840, 2160), visible=0)["guid"]
    b.rect("msPrgCard", pg, b.tl(RUN_X, RUN_Y, RUN_W, RUN_H), 0xFF000000, CARD_A)
    b.frame("msPrgEdge", pg, b.tl(RUN_X, RUN_Y, RUN_W, RUN_H), 0xFFFFFFFF, EDGE_A, 2.0)
    b.image("msRunIc", pg, b.tl(RUN_X + 40, RUN_Y + 61, 290, 200), "streaming/t2r/icons/skill-damage-marker.png", CREAM, 255, scaleMode="StretchAspect")
    b.text("msRunNm", pg, b.tl(RUN_X + 370, RUN_Y + 66, 2000, 110), "", 80, TEXT, tracking=4)
    b.text("msPrgDay", pg, b.tl(RUN_X + 370, RUN_Y + 196, 2400, 50), "", 30, DIM, face="Alternate", tracking=7)             # the event line (COMPLETE when all tiers are in)
    b.text("msRunMatch", pg, b.tl(RUN_X + RUN_W - 84 - 900, RUN_Y + 66, 900, 46), "", 30, LABEL, face="Alternate", align=2, tracking=8)
    for k in range(3):
        b.image(f"msRunPip{k}", pg, b.tl(RUN_X + RUN_W - 84 - 44 - 69 * (2 - k), RUN_Y + 166, 44, 44), "streaming/t2r/icons/c13-ms-pip%d.png" % (0 if k else 1), 0xFFFFFFFF, 255, scaleMode="StretchAspect")
    b.text("msPrgNum", pg, b.tl(BAR_L, RUN_Y + 266, 800, 140), "", 104, TEXT, tracking=3)
    b.text("msPrgLb", pg, b.tl(BAR_L + 80, RUN_Y + 321, 600, 46), "", 32, DIM, face="Alternate", tracking=8)
    b.rect("msBarBg", pg, b.tl(BAR_L, BAR_T, BAR_W2, 18), 0xFFFFFFFF, 40)
    b.rect("msBar", pg, {**b.tl(BAR_L, BAR_T, BAR_W2, 18), "pivotN.x": 0.0, "pivotN.y": 0.5, "pivotAs.x": float(BAR_L), "pivotAs.y": float(BAR_T + 9)}, CREAM, 255)
    for k in range(3):
        b.rect(f"msTk{k}", pg, b.tl(BAR_L + BAR_W2 * (0.45, 0.75, 1.0)[k] - 3, BAR_T - 28, 6, 74), 0xFFFFFFFF, 255)       # (the ext dims the ones not reached yet)
        b.text(f"msTkLb{k}", pg, b.tl(BAR_L + BAR_W2 * (0.45, 0.75, 1.0)[k] - 100, BAR_T + 54, 200, 44), "", 30, DIM, face="Alternate", align=1, tracking=4)
    for k in range(3):
        x = RUN_X + k * (RT_W + RT_GAP)
        b.rect(f"msRtCard{k}", pg, b.tl(x, RT_Y, RT_W, RT_H), 0xFF000000, CARD_A)
        b.frame(f"msRtEdge{k}", pg, b.tl(x, RT_Y, RT_W, RT_H), 0xFFFFFFFF, EDGE_A, 2.0)
        b.rect(f"msRtEd{k}", pg, b.tl(x, RT_Y, 8, RT_H), CREAM, 200, visible=0)
        b.image(f"msRtSt{k}", pg, b.tl(x + 58, RT_Y + 60, 80, 80), "streaming/t2r/icons/c13-ms-lock.png", 0xFFFFFFFF, 255, scaleMode="StretchAspect")
        b.text(f"msRtLb{k}", pg, b.tl(x + 182, RT_Y + 40, 400, 40), "", 28, DIM, face="Alternate", tracking=8)
        b.text(f"msRtTog{k}", pg, b.tl(x + RT_W - 30 - 460, RT_Y + 40, 460, 40), "", 28, LABEL, face="Alternate", align=2, tracking=8)
        b.text(f"msRtGoal{k}", pg, b.tl(x + 182, RT_Y + 98, RT_W - 182 - 30, 80), "", 58, TEXT, tracking=3)
        for q in range(2):
            b.image(f"msRtI{q}_{k}", pg, b.tl(x + 56 + 400 * q, RT_Y + 240, 72, 72), "streaming/t2r/icons/c13-person.png", CREAM, 255, scaleMode="StretchAspect")
            b.text(f"msRtT{q}_{k}", pg, b.tl(x + 146 + 400 * q, RT_Y + 240, 250, 72), "", 46, TEXT, tracking=2)
    b.text("msFoot", pg, b.tl(RUN_X, RT_Y + RT_H + 60, RUN_W, 50), "", 28, DIM, face="Alternate", tracking=8)
    dt = b.group("msDt", ms, b.tl(0, 0, 3840, 2160))["guid"]
    b.line("msDiv", dt, 1740, 540, 1740, 1840, 0xFFFFFFFF, 70, 2.0)
    b.text("msDtName", dt, tlm(DT_X, 540, DT_W, 80), "", 60, TEXT, tracking=3)
    b.text("msDtSub", dt, b.tl(DT_X, 636, DT_W, 46), "", 30, DIM, face="Alternate", tracking=7)
    b.line("msRule", dt, DT_X, 716, DT_X + DT_W, 716, 0xFFFFFFFF, 70, 2.0)
    b.text("msRewLb", dt, b.tl(DT_X, 740, 900, 70), "", 54, TEXT, tracking=3)
    b.text("msRewSub", dt, b.tl(DT_X, 820, DT_W, 46), "", 30, DIM, face="Alternate", tracking=5)
    for k in range(3):
        y = 900 + k * 140
        g = b.group(f"msTr{k}", dt, b.tl(DT_X, y, DT_W, 120))["guid"]
        b.rect(f"msTrCard{k}", g, b.fill(), 0xFF000000, CARD_A)
        b.frame(f"msTrEdge{k}", g, b.fill(), 0xFFFFFFFF, EDGE_A, 2.0)
        b.rect(f"msTrEd{k}", g, b.tl(0, 0, 8, 120), CREAM, 200)
        b.text(f"msTrLb{k}", g, b.tl(36, 8, 400, 36), "", 26, DIM, face="Alternate", tracking=8)
        b.text(f"msTrGoal{k}", g, tlm(36, 44, 700, 64), "", 46, TEXT, tracking=2)
        b.text(f"msTrRew{k}", g, b.tl(760, 40, DT_W - 790, 56), "", 38, PM_TEXT, align=2, tracking=3)
    b.text("msRep", dt, b.tl(DT_X, 1340, DT_W, 50), "", 32, PM_DIM, tracking=3)
    b.text("msRep2", dt, b.tl(DT_X, 1396, DT_W, 50), "", 32, PM_DIM, tracking=3)
    b.text("msStatus", dt, b.tl(DT_X, 1530, DT_W, 60), "", 44, 0xFF7FD07A, tracking=4)

    # ---------------------------------------------------------------- MATCH STATS: every player of the focused raid's match (clan13.c cl13_fill_xs; daemon section 5)
    # (the old flat MATCH STATS list "mst" is gone: clan13.widget hit gui2's single page limit with both lists)

    # (PLAYER STATS = its own page to1/clan13x, build_stats_page: clan13.widget is at gui2's single page limit)

    # ---------------------------------------------------------------- icon / portrait residency (the engine streams a texture in when a widget first shows it)
    pre = b.group("pre", a, b.tl(0, 0, 3, 3))["guid"]
    for i in range(32):
        b.image(f"pre{i}", pre, b.tl(0, 0, 3, 3), "streaming/t2r/icons/c13-food.png", 0xFFFFFFFF, 255)

    # ---------------------------------------------------------------- prompts (the match-flow footer)
    b.image("pBackIc", a, b.tl(270, 1898, 56, 56), "menu:back", 0xFFFFFFFF)
    b.text("pBackTx", a, b.tl(350, 1890, 400, 70), "BACK", 46, PM_TEXT, tracking=4)
    b.image("pSelIc", a, b.tl(760, 1898, 56, 56), "menu:select", 0xFFFFFFFF)
    b.text("pSelTx", a, b.tl(840, 1890, 700, 70), "OPEN", 46, PM_TEXT, tracking=4)
    b.image("pPrevIc", a, b.tl(1300, 1898, 56, 56), "menu:prev", 0xFFFFFFFF)         # the tab keys / bumpers (device-aware glyphs, like GEAR UP's prompts)
    b.image("pNextIc", a, b.tl(1380, 1898, 56, 56), "menu:next", 0xFFFFFFFF)
    b.text("pTabTx", a, b.tl(1460, 1890, 700, 70), "TABS", 46, PM_TEXT, tracking=4)
    b.image("pActIc", a, b.tl(2150, 1898, 56, 56), "menu:action", 0xFFFFFFFF, visible=0)       # F / the pad's menu-action: the match stats of the focused raid (RAIDS tab)
    b.text("pActTx", a, b.tl(2230, 1890, 900, 70), "PLAYER STATS", 46, PM_TEXT, tracking=4, visible=0)
    b.rect("pActHit", a, b.tl(2130, 1800, 700, 200), 0xFFFFFFFF, HIT_A)
    b.rect("pBackHit", a, b.tl(250, 1800, 480, 200), 0xFFFFFFFF, HIT_A)
    b.rect("pSelHit", a, b.tl(740, 1800, 540, 200), 0xFFFFFFFF, HIT_A)
    b.rect("pPrevHit", a, b.tl(1260, 1800, 120, 200), 0xFFFFFFFF, HIT_A)
    b.rect("pNextHit", a, b.tl(1380, 1800, 120, 200), 0xFFFFFFFF, HIT_A)
    w = {k: copy.deepcopy(v) for k, v in main.items() if k != "items"}
    w["items"] = b.items
    return w


STATS_PAGE = "clan13x"


def build_stats_page(main):
    """to1/clan13x: PLAYER STATS of one raid (concept.png), pushed over to1/clan13 by clan13.c cl13_xs_open; its own page because
    clan13.widget is at gui2's single page limit. Same backdrop, header and footer look as the clan page."""
    t, root0, anim0 = _templates(main)
    b = Builder(t)
    root = copy.deepcopy(root0); root.update(guid=t2guid.guid())
    anim = copy.deepcopy(anim0); anim.update(guid=t2guid.guid(), parent=root["guid"])
    b.items += [root, anim]
    a = anim["guid"]
    b.image("bgBlur", a, b.bleed(), "general-textures/blur-background.png", 0xFFFFFFFF, 255)
    b.rect("bgDark", a, b.bleed(), 0xFF0B0C0D, 90)
    b.image("bgPanel", a, b.tl(0, 0, 3840, 2160), PANEL, 0xFFFFFFFF, 255)
    hd = b.group("hd", a, b.tl(0, 0, 3840, 2160))["guid"]
    b.text("hdFac", hd, b.tl(X0, 90, 900, 44), "", 32, LABEL, face="Alternate", tracking=8)
    b.text("hdWeek", hd, b.tl(X0 - 4, 126, 1800, 150), "", 104, TITLE, tracking=4)
    b.rect("hdBarBg", hd, b.tl(HB_X, HB_Y, HB_W, 8), 0xFFFFFFFF, 40)
    b.rect("hdBar", hd, {**b.tl(HB_X, HB_Y, HB_W, 8), "pivotN.x": 0.0, "pivotN.y": 0.5, "pivotAs.x": float(HB_X), "pivotAs.y": float(HB_Y + 4)}, 0xFF7FA8F5, 255)
    for k in range(1, 12):
        b.rect(f"hdTk{k}", hd, b.tl(HB_X + HB_W * k / 12.0 - 1, HB_Y - 4, 3, 16), 0xFFFFFFFF, 110)
    b.text("hdTxt", hd, b.tl(HB_X - 400, HB_Y + 24, HB_W + 400, 46), "", 32, LABEL, face="Alternate", align=2, tracking=4)
    # ---------------------------------------------------------------- PLAYER STATS = the SCOREBOARD (proposal A, re/playerstats-1102/proposal.md): ONE table, shared right-aligned columns,
    # a section row per team (name, MATCH WON / LOST, the team totals in the same columns), then up to 12 player rows (a flat pool of XP_NROW row groups the ext places - clan13.c cl13_fill_xp).
    xp = b.group("mst2", a, b.tl(0, 0, 3840, 2160), visible=0)["guid"]
    b.rect("xpBg", xp, b.tl(X0 - 40, XP_Y, X1 - X0 + 80, XP_H), 0xFF0B0C0D, 244)
    b.frame("xpBgEdge", xp, b.tl(X0 - 40, XP_Y, X1 - X0 + 80, XP_H), 0xFFFFFFFF, EDGE_A, 2.0)
    b.text("xpTitle", xp, b.tl(X0 + 6, XP_Y + 12, 900, 56), "PLAYER STATS", 36, LABEL, face="Alternate", tracking=8)
    b.text("xpSub", xp, b.tl(X0 + 1500, XP_Y + 10, X1 - X0 - 1500, 46), "", 30, DIM, face="Alternate", align=2, tracking=5)
    hh = b.group("xpHead", xp, b.tl(0, 0, 3840, 2160))["guid"]                                # the column heads + the rule under them (one fade)
    b.text("xpChPl", hh, b.tl(X0 + XP_NAME_X, XP_HD_Y, 600, 44), "PLAYER", 24, DIM, face="Alternate", tracking=8)
    b.text("xpChAw", hh, b.tl(X0 + XP_AW_X, XP_HD_Y, 600, 44), "AWARD", 24, DIM, face="Alternate", tracking=8)
    for k, lb in enumerate(XP_HEADS):
        b.text("xpCh%d" % k, hh, b.tl(X0 + XP_COL_R[k] - XP_COL_W, XP_HD_Y, XP_COL_W, 44), lb, 22, DIM, face="Alternate", align=2, tracking=3)
    b.text("xpChP", hh, b.tl(X1 - XP_COL_W, XP_HD_Y, XP_COL_W, 44), "PARTS", 24, DIM, face="Alternate", align=2, tracking=8)
    b.line("xpHeadRule", hh, X0, XP_HD_Y + 64, X1, XP_HD_Y + 64, 0xFFB4B4B4, 70, 2.0)
    for sec, (tx, col) in enumerate((("US", TEXT), ("THE ENEMY", XP_RED))):
        hy = XP_SEC_Y
        sg = b.group("xpSec%d" % sec, xp, b.tl(0, 0, 3840, 2160), visible=0)["guid"]            # moved down as a whole by the client (y offset from the design)
        b.text("xpHd%d" % sec, sg, tlm(X0 + 4, hy + 2, 900, 84), tx, 66, col, tracking=4)
        b.text("xpTag%d" % sec, sg, b.tl(X0 + 4 + (176 if sec == 0 else 580), hy + 32, 520, 40), "", 24, DIM, face="Alternate", tracking=5)
        for k in range(5):
            b.text("xpT%d_%d" % (k, sec), sg, b.tl(X0 + XP_COL_R[k] - XP_COL_W, hy + 20, XP_COL_W, 46), "", 32, DIM, align=2, tracking=2)
        b.text("xpTP%d" % sec, sg, b.tl(X1 - 110 - XP_COL_W, hy + 20, XP_COL_W, 46), "", 32, DIM, align=2, tracking=2)
        b.image("xpTc%d" % sec, sg, b.tl(X1 - 92, hy + 16, 56, 56), "streaming/t2r/icons/c13-parts.png", 0xFF8D897B, 255, scaleMode="StretchAspect")
        b.line("xpRule%d" % sec, sg, X0, hy + 96, X1, hy + 96, 0xFFE0443A if sec else 0xFFB4B4B4, 110 if sec else 70, 2.0)
    for i in range(XP_NROW):
        g = b.group("xpRow%d" % i, xp, b.tl(X0, XP_R0 + i * XP_PITCH, X1 - X0, XP_RH), visible=0)["guid"]
        b.rect("xpMe%d" % i, g, b.tl(0, 0, X1 - X0, XP_RH), SUPPLY_BLUE, 46, visible=0)
        b.rect("xpBdW%d" % i, g, b.tl(0, 0, 12, XP_RH), 0xFFFFFFFF, 60)                       # the left bar: a white one, the enemy's red one, the own cream one (the ext shows one)
        b.rect("xpBdR%d" % i, g, b.tl(0, 0, 12, XP_RH), XP_RED, 150, visible=0)
        b.rect("xpBdM%d" % i, g, b.tl(0, 0, 12, XP_RH), CREAM, 255, visible=0)
        rank_badge_widgets.add_to_builder(b, g, "xpRk%d" % i, "xpRn%d" % i, 28, XP_RH // 2, 40, XP_RH)
        b.text("xpNm%d" % i, g, tlm(XP_NAME_X, 20, 740, 64), "", 40, TEXT, tracking=1)
        b.text("xpTg%d" % i, g, tlm(XP_NAME_X + 300, 32, 200, 40), "", 24, DIM, face="Alternate", tracking=8)
        b.text("xpAw%d" % i, g, b.tl(XP_AW_X, 32, 760, 40), "", 24, DIM, face="Alternate", tracking=8)
        for k in range(5):
            b.text("xpV%d_%d" % (k, i), g, b.tl(XP_COL_R[k] - XP_COL_W, 20, XP_COL_W, 64), "", 40, TEXT, align=2, tracking=2)
        b.text("xpP%d" % i, g, b.tl(X1 - X0 - 110 - XP_COL_W, 20, XP_COL_W, 64), "", 40, TEXT, align=2, tracking=2)
        b.text("xpPm%d" % i, g, b.tl(X1 - X0 - 110 - XP_COL_W, 10, XP_COL_W, 84), "", 56, TEXT, align=2, tracking=2, visible=0)       # the own row's PARTS: the page's one 56 pt number
        b.image("xpCg%d" % i, g, b.tl(X1 - X0 - 92, XP_RH // 2 - 28, 56, 56), "streaming/t2r/icons/c13-parts.png", XP_COL[4], 255, scaleMode="StretchAspect")
    b.text("xpEmpty", xp, b.tl(X0, 900, X1 - X0, 200), "", 46, PM_DIM, align=1, tracking=4, multiline=1, visible=0)
    b.image("pBackIc", a, b.tl(270, 1898, 56, 56), "menu:back", 0xFFFFFFFF)
    b.text("pBackTx", a, b.tl(350, 1890, 400, 70), "BACK", 46, PM_TEXT, tracking=4)
    b.rect("pBackHit", a, b.tl(250, 1800, 480, 200), 0xFFFFFFFF, HIT_A)
    # the POST-MATCH SCOREBOARD (clan13.c cl13_post_open) replaces the BACK prompt with CONTINUE (confirm): same place, hidden otherwise
    b.image("pCtIc", a, b.tl(270, 1898, 56, 56), "menu:select", 0xFFFFFFFF, visible=0)
    b.text("pCtTx", a, b.tl(350, 1890, 700, 70), "CONTINUE", 46, PM_TEXT, tracking=4, visible=0)
    b.rect("pCtHit", a, b.tl(250, 1800, 640, 200), 0xFFFFFFFF, HIT_A, visible=0)
    w = {k: copy.deepcopy(v) for k, v in main.items() if k != "items"}
    w["items"] = b.items
    return w


def add_clan13_page(wdir):
    main = json.load(open(os.path.join(wdir, "to1", "main-menu.widget.json"), encoding="utf-8"))
    json.dump(build_page(main), open(os.path.join(wdir, "to1", PAGE + ".widget.json"), "w", encoding="utf-8"), indent=4)
    json.dump(build_stats_page(main), open(os.path.join(wdir, "to1", STATS_PAGE + ".widget.json"), "w", encoding="utf-8"), indent=4)
    return 1


# ------------------------------------------------------------------ offline previews (filled like clan13.c fills them, from tools/clan_ingame.py output)
def _lines(text, kind):
    return [l.split("\t") for l in text.split("\n") if l.startswith(kind + "\t")]


def _est(t, pt):                       # gearup13.c gu_est
    return pt * sum(0.40 if c == " " else 0.62 if c.islower() or ord(c) > 127 else 0.80 for c in t)


def clip(src, boxw, pt, lines):
    """clan13.h cl13_clip: greedy word wrap with the estimated widths; at most `lines` lines, the cut ends in '...'."""
    boxw *= 0.88
    out, cur, n = [], "", 1
    for w in src.split():
        t = (cur + " " + w).strip()
        if cur and _est(t, pt) > boxw:
            if n >= lines:
                while cur and _est(cur + "...", pt) > boxw:
                    cur = cur.rsplit(" ", 1)[0] if " " in cur else ""
                out.append(cur.rstrip(" ,;") + "...")
                return " ".join(out)
            out.append(cur); n += 1; cur = w
        else:
            cur = t
    out.append(cur)
    return " ".join(out)


JD_TONE = {"": 0, "info": 0, "good": 1, "warn": 2, "bad": 3}
BR = chr(10)
BR2 = BR + BR


def wrap(src, boxw, pt, maxlines):
    """clan13.h cl13_wrap: greedy word wrap at 88 % of the box by the estimated widths; the lines are joined by a line break (the engine never wraps them again), a
    blank line in the source stays a blank line; at most `maxlines` lines, the cut ends in '...'. -> (text, lines used)."""
    boxw *= 0.88
    out = []
    for pi, para in enumerate(src.split(BR2)):
        if pi:
            out.append("")
        cur = ""
        for w in para.split():
            t = (cur + " " + w).strip()
            if cur and _est(t, pt) > boxw:
                out.append(cur); cur = w
            else:
                cur = t
        out.append(cur)
    if len(out) > maxlines:
        out = out[:maxlines]
        cur = out[-1]
        while cur and _est(cur + "...", pt) > boxw:
            cur = cur.rsplit(" ", 1)[0] if " " in cur else ""
        out[-1] = cur.rstrip(" ,;") + "..."
    return BR.join(out), len(out)


def jd_res(d):
    """A day row's right corner: MAP - WON / LOST - supplies / need (clan13.c cl13_jd_res)."""
    p = []
    if d[7]:
        p.append(d[7])
    if d[8] in ("0", "1"):
        p.append('<font color="#%s">%s</font>' % (("7CB494", "WON") if d[8] == "1" else ("FD6D51", "LOST")))
    if int(d[10]) > 0:
        p.append("%s / %s" % (d[9], d[10]))
    return "  -  ".join(p)


def jd_facts(d):
    """The two fact lines of the reading pane (clan13.c cl13_jd_facts)."""
    a = []
    if d[7]:
        a.append("RAID:  " + d[7] + ("" if d[8] not in ("0", "1") else '  <font color="#%s">%s</font>' % (("7CB494", "WON") if d[8] == "1" else ("FD6D51", "LOST"))))
    if int(d[10]) > 0:
        sup, need = int(d[9]), int(d[10])
        a.append('SUPPLIES:  <font color="#%s">%d / %d</font>' % ("7CB494" if sup >= need else "E0B04A" if (need - sup) * 3 < need else "FD6D51", sup, need))
    h, u, sk, dn = int(d[11]), int(d[12]), int(d[13]), int(d[14])
    b = ""
    if h >= 0:
        n = h + u + sk
        b = "%d SURVIVOR%s" % (n, "" if n == 1 else "S") + (" (%+d)" % dn if dn else "") + "      %d HEALTHY" % h
        b += '      <font color="#%s">%d HUNGRY</font>' % ("E0B04A" if u else "8D897B", u) + '      <font color="#%s">%d SICK</font>' % ("FD6D51" if sk else "8D897B", sk)
    return "      ".join(a), b


STCODE = {"healthy": 0, "hungry": 1, "sad": 2, "sick": 3, "dead": 4, "injured": 5, "recovered": 6, "new": 7, "depressed": 8, "shock": 9}
STTXT = {"healthy": "7FD07A", "hungry": "F0B429", "sad": "7FA8F5", "sick": "F2625A", "dead": "A9AFB8", "injured": "F29A4A", "recovered": "7FD07A", "new": "55C6E8",
         "shock": "DCE7F0", "depressed": "9DB0C4"}
STICON = {"hungry": "food", "sad": "person", "sick": "pills", "dead": "person", "injured": "bandage", "recovered": "medicine", "new": "person", "depressed": "person", "shock": "person"}
CODE2NAME = {"h": "healthy", "u": "hungry", "s": "sick", "d": "depressed", "k": "shock"}


# the picker's sample rows (clan13.c: the live missions of tools/clan.py MISSIONS + the weapon-execution offers; name, unit, completed times, the 3 goals)
MS_SAMPLE = [("Down Enemies", "Downs", 0, (3, 6, 9)), ("Executions", "Executions", 1, (4, 7, 12)), ("Revives", "Revives", 0, (2, 4, 6)), ("Headshots", "Headshots", 2, (6, 8, 10)),
             ("Mark Enemies", "Marks", 0, (7, 14, 21)), ("Variable Rifle Executions", "Executions", 0, (2, 3, 5)), ("Tactical Shotgun Executions", "Executions", 0, (2, 3, 5)),
             ("Semi-Auto Rifle Executions", "Executions", 3, (7, 9, 12))]


# the running view's sample missions: variant -> (name, unit, icon, goals, count, match, event kind 0 none / 1 survivors / 2 attack, completed before)
MS_RUN = {"running": ("Down Enemies", "Downs", "streaming/t2r/icons/skill-damage-marker.png", (9, 15, 20), 6, 2, 1, 0),
          "running-attack": ("Down Enemies", "Downs", "streaming/t2r/icons/skill-damage-marker.png", (9, 15, 20), 6, 2, 2, 0),
          "running-weapon": ("Variable Rifle Executions", "Executions", "hud/weapons/guns/rifle-vepr/vepr-scp.png", (5, 9, 12), 6, 2, 1, 1),
          "running-bow": ("Bow Executions", "Executions", "hud/weapons/guns/bow-ellie/bow.png", (3, 6, 9), 6, 2, 0, 0),
          "running-done": ("Headshots", "Headshots", "streaming/t2r/icons/skill-sharpshooter.png", (6, 8, 10), 11, 3, 1, 2)}
RUN_COL = ("E6E6E6", "8D897B", "7FD07A")                   # TEXT, DIM, green (the ext's <font color> runs)


def ms_run_demo(by, var):
    """clan13.c cl13_fill_ms_run, offline: the MISSIONS tab while a mission runs (layout A)."""
    name, unit, icon, goals, cnt, match, ek, rep = MS_RUN[var]
    u = unit.upper()

    def vis(n, on):
        by[n]["visible"] = 1 if on else 0

    def txt(n, t):
        by[n]["text"] = t

    def img(n, pth):
        by[n]["path"] = pth

    def fit(n, t):
        it = by[n]
        e = _est(t, it["pointSize"]); sc = min(1.0, 0.92 * it["rectSizeDelta.width"] / e) if e else 1.0
        it["text"] = t; it["pointSize"] = it["pointSize"] * max(sc, 0.6)

    def col(c, t):
        return f'<font color="#{c}">{t}</font>'
    top = goals[2]
    reached = sum(1 for g in goals if cnt >= g)
    vis("msTitle", True); txt("msTitle", "CURRENT MISSION"); txt("msSub", "")
    for i in range(NMS):
        vis(f"msRow{i}", False)
    vis("msDt", False); vis("msPrg", True)
    img("msRunIc", icon); fit("msRunNm", name.upper())
    if reached >= 3:
        txt("msPrgDay", col(RUN_COL[2], "COMPLETE"))
    else:
        txt("msPrgDay", {1: "NEW SURVIVORS - THE FURTHER YOU GET, THE MORE JOIN", 2: "ENEMY ATTACK - THE FURTHER YOU GET, THE FEWER YOU LOSE", 0: "THE FURTHER YOU GET, THE MORE BOOSTERS"}[ek])
    txt("msRunMatch", f"MATCH {match} OF 3")
    for k in range(3):
        img(f"msRunPip{k}", "streaming/t2r/icons/c13-ms-pip%d.png" % (1 if k + 1 < match else 2 if k + 1 == match else 0))
    txt("msPrgNum", str(cnt)); by["msPrgLb"]["pivotAs.x"] = BAR_L + _est(str(cnt), 104) + 36; txt("msPrgLb", u)
    by["msBar"]["rectSizeDelta.width"] = BAR_W2 * min(cnt, top) / top
    for k in range(3):
        x = BAR_L + BAR_W2 * goals[k] / top
        by[f"msTk{k}"]["pivotAs.x"] = x - 3; by[f"msTk{k}"]["color.a"] = 255 if cnt >= goals[k] else 120
        by[f"msTkLb{k}"]["pivotAs.x"] = x - 100; txt(f"msTkLb{k}", col(RUN_COL[0] if cnt >= goals[k] else RUN_COL[1], str(goals[k])))
    for k in range(3):
        st = 0 if k < reached else 1 if k == reached else 2
        dim = st == 2
        img(f"msRtSt{k}", "streaming/t2r/icons/c13-ms-" + ("check", "cur", "lock")[st] + ".png")
        vis(f"msRtEd{k}", st == 1)
        txt(f"msRtLb{k}", col(RUN_COL[1], f"TIER {k + 1}")); txt(f"msRtTog{k}", f"{goals[k] - cnt} TO GO" if st == 1 else "")
        fit(f"msRtGoal{k}", col(RUN_COL[1] if dim else RUN_COL[0], f"{goals[k]} {u}"))
        rew = []
        if ek == 2:
            rew.append(("streaming/t2r/icons/c13-ms-lose.png", f"{(40, 20, 10)[k]}%"))
        elif ek == 1:
            rew.append(("streaming/t2r/icons/c13-person.png", f"+{(1, 2, 2)[k]}"))
        rew.append(("streaming/t2r/icons/booster-ammo-start.png", f"x{(2, 2, 3)[k]}"))
        for q in range(2):
            vis(f"msRtI{q}_{k}", q < len(rew)); vis(f"msRtT{q}_{k}", q < len(rew))
            if q < len(rew):
                img(f"msRtI{q}_{k}", rew[q][0]); txt(f"msRtT{q}_{k}", col(RUN_COL[1] if dim else RUN_COL[0], rew[q][1]))
                by[f"msRtI{q}_{k}"]["color.a"] = 110 if dim else 255
    txt("msFoot", "NOTHING IS PAID BELOW TIER 1" + (f" - COMPLETED {rep} TIME{'S' if rep != 1 else ''} BEFORE: GOALS ARE HIGHER" if rep else ""))


def demo(page, tab, secs, ms=None, jfoc=None):
    """The page filled from the op 0xB7 texts (secs = {1..4: text}); tab 0 overview / 1 survivors / 2 raids / 3 journal; the end state of the entrance animations."""
    w = copy.deepcopy(page)
    by = {i["name"]: i for i in w["items"]}

    def vis(n, on):
        by[n]["visible"] = 1 if on else 0

    def txt(n, s):
        by[n]["text"] = s

    def img(n, p):
        by[n]["path"] = p

    def box(n, s, lines):
        it = by[n]
        it["text"] = clip(s, it["rectSizeDelta.width"], it["pointSize"], lines)

    def fit(n, s):
        it = by[n]
        e = _est(s, it["pointSize"]); sc = min(1.0, 0.92 * it["rectSizeDelta.width"] / e) if e else 1.0
        if sc < 0.6 and "<" not in s:                  # gu_fit: even at the floor too wide -> cut with "..."
            while len(s) > 3 and _est(s + "...", it["pointSize"] * 0.6) > 0.92 * it["rectSizeDelta.width"] * 1.02:
                s = s[:-1].rstrip()
            s += "..."
        it["text"] = s
        it["pointSize"] = it["pointSize"] * max(sc, 0.6)

    def pic(n, pid, show=True):
        a = (pid or "").split("/")
        if len(a) == 4:
            img(n + "Im", "streaming/t2r/icons/c13p-%s_%s.png" % (a[2], a[3]))
            vis(n + "Im", show)
    H = _lines(secs[1], "H")[0]
    week, dow, mv = int(H[1]), int(H[2]), int(H[4])
    done = int(H[8])
    txt("hdFac", "WLF" if H[3] == "W" else "SERAPHITES"); txt("hdWeek", f"WEEK {week}: DAY {dow}")
    by["hdBar"]["rectSizeDelta.width"] = max(8.0, HB_W * min(1.0, done / 84.0)); txt("hdTxt", f"{done} OF 84 DAYS SURVIVED - WEEK {week} OF 12")
    for k in range(5):
        vis(f"tabU{k}", k == tab)
        by[f"tab{k}"]["color.a"] = 255 if k == tab else 150
    for g, on in (("ov", tab == 0), ("sv", tab == 1), ("rds", tab == 2), ("jrn", tab == 3), ("ms", tab == 4)):
        vis(g, on)
    P, J, M, L = _lines(secs[1], "P"), _lines(secs[2], "J"), _lines(secs[3], "M"), _lines(secs[2], "L")
    U = _lines(secs[4], "U")
    S = _lines(secs[3], "S")
    if tab == 0:
        txt("ovStTitle", "STATUS UPDATES"); txt("ovStSub", "SINCE YOU LAST LOOKED")
        for i in range(NST):
            vis(f"stRow{i}", i < min(len(U), OVST))
            if i >= min(len(U), OVST):
                continue
            u = U[i]
            st = u[3]
            for q in range(10):
                vis(f"stTn{q}_{i}", q == STCODE.get(st, 1))
            pic(f"stPt{i}", u[5])
            txt(f"stRole{i}", u[2]); fit(f"stName{i}", u[1]); vis(f"stIc{i}", st in STICON); img(f"stIc{i}", "streaming/t2r/icons/c13-" + STICON.get(st, "pills") + ".png")
            txt(f"stWord{i}", f'<font color="#{STTXT.get(st, "FFFFFF")}">{u[4]}</font>'); fit(f"stLine{i}", u[6]); txt(f"stRead{i}", "READ IN THE JOURNAL ->")
            vis(f"stNew{i}Bg", i < 2); vis(f"stNew{i}Tx", i < 2)
        recs = [j for j in J if j[3]][:NREC]
        so, co, rt, nr = ov_stack(min(len(U), OVST), len(S), len(recs))
        txt("ovStSub", f"SINCE YOU LAST LOOKED  -  {len(U) - OVST} MORE IN THE JOURNAL" if len(U) > OVST else "SINCE YOU LAST LOOKED" if U else "NOTHING NEW SINCE YOU LAST LOOKED")
        by["ovSup"]["pivotAs.y"] = so; by["ovCamp"]["pivotAs.y"] = co; by["ovRec"]["pivotAs.y"] = rt
        txt("ovRecTitle", "RECENTLY IN CAMP" if nr else "")
        for i in range(NREC):
            vis(f"ovRecLn{i}", i < nr)
            txt(f"ovRecDay{i}", f"DAY {recs[i][8]}" if i < nr else ""); fit(f"ovRecTx{i}", recs[i][3].capitalize() if i < nr else "")
        txt("ovSupTitle", "SUPPLIES")
        txt("ovSupNone", "" if S else "NO SUPPLIES BOOKED YET - THEY ARE COUNTED AFTER EACH RAID")
        if S:
            txt("ovLastLb", "THE STOCK LASTS"); txt("ovLast", f"{H[7]} DAYS" if int(H[7]) >= 0 else "")
        for k in range(NTILE):
            vis(f"tlRow{k}", k < len(S))
            if k < len(S):
                s = S[k]
                img(f"tlIc{k}", "streaming/t2r/icons/c13-" + ("food", "water", "medicine", "ammo", "materials")[k] + ".png")
                txt(f"tlLb{k}", s[1]); txt(f"tlNum{k}", s[2] if int(s[2]) else "NONE"); txt(f"tlDays{k}", f"{s[3]} DAYS" if int(s[3]) >= 0 else "IN CAMP")
        txt("ovCampTitle", "CAMP"); txt("ovClans", f"CAMPAIGNS COMPLETED {H[9]} - CLANS LOST {H[10]} - LARGEST CLAN {H[11]}")
        band = 3 if mv >= 70 else 2 if mv >= 50 else 1 if mv >= 30 else 0
        txt("moLb", "CAMP MORALE")
        for k in range(4):
            vis(f"moFill{k}", k == band)
        by[f"moFill{band}"]["rectSizeDelta.width"] = MO_W * max(3, mv) / 100.0
        by["moPin"]["pivotAs.x"] = MO_X + MO_W * mv / 100.0 - 5
        txt("moWord", ("GRIM", "STRAINED", "STEADY", "HOPEFUL")[band])
    elif tab == 1:
        txt("svTitle", f"SURVIVORS  {H[6]}")
        foc = 1
        for i in range(NSV):
            vis(f"svRow{i}", i < len(P))
            if i >= len(P):
                continue
            p = P[i]
            nm = CODE2NAME.get(p[3], "healthy")
            pic(f"svPt{i}", p[6]); txt(f"svRole{i}", p[2]); fit(f"svName{i}", p[1])
            vis(f"svIc{i}", p[3] != "h"); img(f"svIc{i}", "streaming/t2r/icons/c13-" + STICON.get(nm, "pills") + ".png")
            txt(f"svWord{i}", f'<font color="#{STTXT[nm]}">{p[4]}</font>' if p[3] != "h" else "")
            for k, c in enumerate("husdk"):
                vis(f"svBar{k}_{i}", p[3] == c)
            vis(f"svFill{i}", i == foc); vis(f"svFrame{i}", i == foc)
            vis(f"svNew{i}Bg", i == 5); vis(f"svNew{i}Tx", i == 5)
        vis("svDt", bool(P))
        if not P:
            return w
        foc = min(foc, len(P) - 1)
        p = P[foc]
        pic("svDt", p[6]); fit("svDtName", p[1]); fit("svDtSub", f"{p[2]}  -  {p[4]}"); box("svDtTag", p[9], 3)
        txt("svDtCloseLb", "CLOSE TO"); pic("svDtB", next((q[6] for q in P if q[1] == p[7]), "")); fit("svDtBond", p[7]); txt("svDtBondTy", p[8])
        txt("svDtLatelyLb", "LATELY"); box("svDtLately", p[10], 3)
    elif tab == 2:
        txt("rdTitle", "RAIDS"); txt("rdHint", "CLICK A RAID TO SEE WHAT IT BROUGHT HOME.")
        for i in range(NRDS):
            vis(f"rrRow{i}", i < len(M))
            if i >= len(M):
                continue
            m = M[i]
            txt(f"rrDay{i}", f"DAY {(int(m[1]) - 1) % 7 + 1}"); fit(f"rrMap{i}", m[2]); txt(f"rrWl{i}", "MATCH WON" if m[3] == "1" else "MATCH LOST" if m[3] == "0" else "")
            txt(f"rrNum{i}", f"{m[4]} / {m[5]}"); by[f"rrBar{i}"]["rectSizeDelta.width"] = 900 * min(1.0, int(m[4]) / max(1, int(m[5])))
            vis(f"rrFill{i}", i == 0); vis(f"rrFrame{i}", i == 0); vis(f"rrNew{i}Bg", i == 0); vis(f"rrNew{i}Tx", i == 0)
        vis("rdDt", bool(M))
        if not M:
            txt("rdHint", "NO RAIDS YET - PLAY A MATCH TO SEND A PARTY OUT"); txt("pSelTx", ""); vis("pSelIc", False)
            return w
        m = M[0]
        got = [int(x) for x in m[7].split()]; need = [int(x) for x in m[8].split()]
        txt("rdDtLb", "SUPPLIES BROUGHT HOME"); txt("rdDtBig", m[4]); txt("rdDtOf", f"/ {m[5]} NEEDED")
        ok = int(m[4]) >= int(m[5])
        txt("rdVerd", f"ENOUGH, +{int(m[4]) - int(m[5])} OVER" if ok else f"SHORT BY {int(m[5]) - int(m[4])}"); vis("rdVerdFr", ok); vis("rdVerdFrS", not ok)
        for k, ci in enumerate((0, 1, 2, 4)):
            mx = max(got[ci], need[ci], 1)
            img(f"rdBIc{k}", "streaming/t2r/icons/c13-" + ("food", "water", "medicine", "ammo", "materials")[ci] + ".png")
            txt(f"rdBLb{k}", ("FOOD", "WATER", "MEDICINE", "AMMO", "MATERIALS")[ci]); txt(f"rdBNum{k}", f"{got[ci]} / {need[ci]}" if need[ci] else str(got[ci]))
            by[f"rdB{k}"]["rectSizeDelta.width"] = BAR_W * got[ci] / mx; by[f"rdBNeed{k}"]["pivotAs.x"] = BAR_X + BAR_W * need[ci] / mx - 2
            vis(f"rdBNeed{k}", need[ci] > 0); txt(f"rdBDelta{k}", f"+{got[ci] - need[ci]}" if need[ci] and got[ci] > need[ci] else "")
        txt("rdLootLb", "BROUGHT HOME")
        T = [t for t in _lines(secs[3], "T") if t[1] == m[1]][:NLOOT]
        for k in range(NLOOT):
            vis(f"ltRow{k}", k < len(T))
            if k < len(T):
                img(f"ltIc{k}", "streaming/t2r/icons/c13-" + T[k][4] + ".png"); txt(f"ltQty{k}", f"x{T[k][2]}"); box(f"ltNm{k}", T[k][3], 2)
                vis(f"ltNew{k}Bg", k == 0); vis(f"ltNew{k}Tx", k == 0)
    elif tab == 4 and ms and ms.startswith("running"):
        ms_run_demo(by, ms)
        txt("pSelTx", ""); vis("pSelIc", False)
        return w
    elif tab == 4:
        rows = MS_SAMPLE if ms is None or ms == "chosen" or ms == "attack" else []
        ek = 2 if ms == "attack" else 1
        txt("msTitle", "CHOOSE A MISSION")
        txt("msSub", "YOU HAVE 3 MATCHES TO COMPLETE YOUR MISSION" if rows else "")
        vis("msDt", bool(rows))
        for i in range(NMS):
            vis(f"msRow{i}", i < len(rows))
            if i >= len(rows):
                continue
            fit(f"msNm{i}", rows[i][0].upper()); txt(f"msRp{i}", f"DONE {rows[i][2]}X" if rows[i][2] else "")
            vis(f"msFill{i}", i == 1); vis(f"msFrame{i}", i == 1)
        if not rows:
            vis("ms", False); vis("ldTx", True); txt("ldTx", "NO MISSION TO CHOOSE RIGHT NOW - THE NEXT CLAN EVENT BRINGS ONE")
            txt("pSelTx", ""); vis("pSelIc", False)
            return w
        nm, unit, rep, goals = rows[1]
        fit("msDtName", nm.upper()); txt("msDtSub", "3 MATCHES - THE FURTHER YOU GET, THE MORE YOU WIN")
        txt("msRewLb", "REWARDS")
        txt("msRewSub", "FEWER CLAN MEMBERS LOST IN THE ATTACK AND ONE-USE BOOSTERS" if ek == 2 else "NEW CLAN MEMBERS AND ONE-USE BOOSTERS")
        for k in range(3):
            txt(f"msTrLb{k}", f"TIER {k + 1}"); fit(f"msTrGoal{k}", f"{goals[k]} {unit.upper()}")
            txt(f"msTrRew{k}", f"LOSE {(60, 40, 20)[k]}%   +{(1, 2, 2)[k]} BOOSTER{'S' if k else ''}" if ek == 2 else f"+{(1, 2, 2)[k]} SURVIVOR{'S' if k else ''}   +{(1, 1, 2)[k]} BOOSTER{'S' if k == 2 else ''}")
        txt("msRep", "WITH NO TIER REACHED 60% OF THE CLAN IS LOST." if ek == 2 else "NOTHING IS PAID BELOW THE FIRST TIER.")
        txt("msRep2", f"COMPLETED {rep} TIME{'S' if rep != 1 else ''} BEFORE: THE GOALS ARE HIGHER." if rep else "")
        txt("msStatus", "MISSION STARTED" if ms == "chosen" else "")
        txt("pSelTx", "SELECT"); vis("pSelIc", ms != "chosen")
        return w
    else:
        D, G, K = _lines(secs.get(6, ""), "D"), _lines(secs.get(6, ""), "G"), _lines(secs.get(6, ""), "K")
        wk, top = (int(K[0][1]), int(K[0][2])) if K else (1, 1)
        rows = [d for d in D if int(d[3]) == wk]
        off = max(0, len(rows) - NJD)
        foc = len(rows) - 1 if jfoc is None else max(0, min(jfoc, len(rows) - 1))
        txt("jwTitle", f"WEEK {wk} OF 12")
        won, lost = sum(1 for d in rows if d[8] == "1"), sum(1 for d in rows if d[8] == "0")
        txt("jwSub", f"{won} WON  -  {lost} LOST" if rows else "")
        by["jwPrev"]["color.a"] = 255 if wk > 1 else 60
        by["jwNext"]["color.a"] = 255 if wk < top else 60
        vis("jtPane", bool(rows))
        for i in range(NJD):
            vis(f"jdRow{i}", off + i < len(rows))
            if off + i >= len(rows):
                continue
            d = rows[off + i]
            txt(f"jdDay{i}", f"DAY {d[2]}" if int(d[1]) > 0 else "THE START"); fit(f"jdTi{i}", d[5]); txt(f"jdRes{i}", jd_res(d))
            by[f"jdBd{i}"]["path"] = BAND_IMG % JD_TONE.get(d[6], 0)
            vis(f"jdFill{i}", off + i == foc); vis(f"jdFrame{i}", off + i == foc)
            vis(f"jdNew{i}Bg", d[15] == "1"); vis(f"jdNew{i}Tx", d[15] == "1")
        if not rows:
            vis("ldTx", True); txt("ldTx", "NOTHING IS WRITTEN IN THE JOURNAL YET")
        else:
            d = rows[foc]
            txt("jtLb", f"WEEK {wk}  -  DAY {d[2]}" if int(d[1]) > 0 else "WEEK 1  -  THE START"); fit("jtTitle", d[5])
            f0, f1 = jd_facts(d)
            txt("jtF0", f0); txt("jtF1", f1)
            y, k = JT_Y0, 0
            paras = [g for g in G if g[1] == d[1]]
            for k in range(NJP):
                vis(f"jtCap{k}", k < len(paras)); vis(f"jtBo{k}", k < len(paras))
                if k >= len(paras):
                    continue
                cap, text = paras[k][2], paras[k][3]
                if k == NJP - 1:                                   # more paragraphs than slots: the rest follows in the last one
                    for g in paras[NJP:]:
                        text += BR2 + g[3]
                room = max(1, int((JT_Y1 - y - JT_CAP_H) // JT_LINE))
                body, n = wrap(text, JT_W, JT_PT, room)
                by[f"jtCap{k}"]["pivotAs.y"] = float(y); txt(f"jtCap{k}", cap)
                by[f"jtBo{k}"]["pivotAs.y"] = float(y + JT_CAP_H); txt(f"jtBo{k}", body)
                y += JT_CAP_H + n * JT_LINE + JT_GAP
        vis("pActIc", False); vis("pActTx", True); txt("pActTx", "LEFT / RIGHT:  WEEK")
    txt("pSelTx", {0: "JOURNAL", 1: "", 2: "", 3: ""}[tab]); vis("pSelIc", tab == 0); txt("pTabTx", "TABS")
    return w


def preview(wdir, out_dir, db=None):
    import sys
    import tempfile
    import widget_preview
    main = json.load(open(os.path.join(wdir, "to1", "main-menu.widget.json"), encoding="utf-8"))
    page = build_page(main)
    os.makedirs(out_dir, exist_ok=True)
    figs = os.path.join(tempfile.gettempdir(), "gu-fig")
    os.makedirs(figs, exist_ok=True)
    import ui_scratch
    ui_scratch.make_gearup_panel(1920, 1080).save(os.path.join(figs, "gearup-panel.png"))
    widget_preview.STREAMING["streaming/t2r/clan/"] = figs
    here = os.path.dirname(os.path.abspath(__file__))
    sys.path.insert(0, os.path.join(here, ".."))
    sys.path.insert(0, os.path.join(here, "..", "models"))
    import sqlite3
    import clan_ingame
    import make_icons, real_icons
    icd = os.path.join(tempfile.gettempdir(), "t2r-clan13-icons")
    os.makedirs(icd, exist_ok=True)
    make_icons.clan13_icons(icd)
    make_icons.clan13_portraits(icd)
    real_icons.MOD_DIRS.append(icd)
    tid = "0123456789abcdef01234567"
    if not db:
        import clan_demo_seed
        db = os.path.join(tempfile.mkdtemp(), "demo.db")
        sys.argv = ["x", db, "--days", "9", "--size", "17"]
        clan_demo_seed.main()
    c = sqlite3.connect(db)
    secs = {s: clan_ingame.build(c, tid, "en", s) for s in (1, 2, 3, 4, 6)}
    empty = {k: t.split(chr(10))[0] for k, t in secs.items()}                  # an empty clan: the header lines only
    for var, sx in (("", secs), ("-empty", empty)):
        for tab, nm in enumerate(("overview", "survivors", "raids", "journal", "missions")):
            tmp = os.path.join(tempfile.gettempdir(), f"t2r-clan13-{nm}.widget.json")
            json.dump(demo(page, tab, sx, "none" if var else None), open(tmp, "w", encoding="utf-8"))
            for px, sc in ((1920, 0.5), (1200, 0.3125)):                     # 1920x1080 and 1200x675
                print(widget_preview.render(tmp, os.path.join(out_dir, f"clan13-{nm}{var}-{px}.png"), scale=sc))
    for wk, foc in ((2, 3), (1, 0)):                                           # JOURNAL week pages: an older week with a day in the middle focused, and the first page
        sw = dict(secs)
        sw[6] = clan_ingame.build(c, tid, "en", 6, 0, wk)
        tmp = os.path.join(tempfile.gettempdir(), "t2r-clan13-jw.widget.json")
        json.dump(demo(page, 3, sw, None, foc), open(tmp, "w", encoding="utf-8"))
        for px, sc in ((1920, 0.5), (1200, 0.3125)):
            print(widget_preview.render(tmp, os.path.join(out_dir, f"clan13-journal-week{wk}-{px}.png"), scale=sc))
    for var in MS_RUN:                                                         # the RUNNING mission (layout A): survivors event / attack event / weapon icon / bow / all tiers done
        tmp = os.path.join(tempfile.gettempdir(), "t2r-clan13-ms.widget.json")
        json.dump(demo(page, 4, secs, var), open(tmp, "w", encoding="utf-8"))
        for px, sc in ((1920, 0.5), (1200, 0.3125)):
            print(widget_preview.render(tmp, os.path.join(out_dir, f"clan13-missions-{var}-{px}.png"), scale=sc))
    for var in ("attack", "chosen"):                                           # the mission view of an attack event (losses instead of survivors) / right after the pick
        tmp = os.path.join(tempfile.gettempdir(), "t2r-clan13-ms.widget.json")
        json.dump(demo(page, 4, secs, var), open(tmp, "w", encoding="utf-8"))
        for px, sc in ((1920, 0.5), (1200, 0.3125)):
            print(widget_preview.render(tmp, os.path.join(out_dir, f"clan13-missions-{var}-{px}.png"), scale=sc))


if __name__ == "__main__":
    import sys
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    preview(sys.argv[1], sys.argv[2], sys.argv[3] if len(sys.argv) > 3 else None)
