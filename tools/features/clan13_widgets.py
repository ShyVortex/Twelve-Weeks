"""The in-game CLAN page, built like GEAR UP (gearup13_widgets.py): one page to1/clan13 with the match-flow backdrop, fonts, colours and footer prompts,
driven entirely by t2r-ext clan13.c from daemon op 0xB6 / 0xB7 (tools/clan_ingame.py). The LOOK TARGET is the launcher CLAN tab capture
E:/t2tmp_lead/tmp/clan-ui-preview/clan-cast-proof4.mp4: WLF / WEEK n: DAY n big with the day-progress line top right; STATUS UPDATES "since you last looked" (cards: portrait
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
import nr_style as nr
tlm = nr.lm      # a box with its pivot at the left middle: clan13.c shrinks a too-long name about it (gu_fit)

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


# ---------------------------------------------------------------- redesign (re/ui-redesign-1117): the No Return frame (nr_style) + 2D tile rows, one fixed detail column per tab.
# Geometry = render.py x 2 (widget space 3840 x 2160). Every tile set has ONE movable focus outline (<tab>Fo, nrui.c nr_frame_at) instead of an outline per tile (widget budget);
# a tile's fill is brighter when focused / hovered (clan13.c writes its alpha). clan13.c places every row / tile group of the 2D views (row window + per-row column window).
TABS = ["OVERVIEW", "SURVIVORS", "RAIDS", "JOURNAL", "MISSIONS"]
TILE_DIM, TILE_FOC = nr.TILE_A, nr.TILE_FA
# OVERVIEW
OV_L1, OV_R0 = 2380, 2520
OV_ST_Y, OV_ST_T, OV_ST_W, OV_ST_H, OV_ST_DX = 452, 508, 340, 356, 372
OV_SU_Y, OV_SU_T, OV_SU_W, OV_SU_H = 952, 1008, 340, 300
OV_CA_Y, MO_X0, MO_X1, MO_Y = 1412, 528, 1668, 1494
OV_REC_Y, OV_REC_T, OV_REC_DY = 1380, 1472, 104
# SURVIVORS: 3 visible role rows x 7 tiles
SV_ROWS, SV_COLS = 3, 7
SV_L1, SV_R0 = 2420, 2580
SV_RY0, SV_RDY, SV_TW, SV_TH, SV_TDX, SV_TOP = 564, 428, 280, 248, 308, 44
SV_SB_X, SV_SB_Y0, SV_SB_Y1 = 2448, 540, 1860
# RAIDS: 2 visible week rows x 3 tiles
RD_ROWS, RD_COLS = 2, 3
RD_L1, RD_R0 = 2020, 2180
RD_RY0, RD_RDY, RD_TW, RD_TH, RD_TDX, RD_TOP = 564, 540, 600, 432, 632, 48
RD_SB_X = 2048
RD_BAR_X0, RD_BAR_X1, RD_BAR_Y0, RD_BAR_DY = 2620, 3420, 800, 124
# JOURNAL: 3 visible week rows x 7 day tiles
JR_ROWS, JR_COLS = 3, 7
JR_L1, JR_R0 = 2260, 2400
JR_RY0, JR_RDY, JR_TW, JR_TH, JR_TDX, JR_TOP = 464, 476, 280, 352, 304, 52
JR_SB_X = 2288
NJP, JT_X, JT_W, JT_Y0, JT_PT, JT_LINE, JT_CAP_H, JT_GAP, JT_Y1 = 5, 2400, 1300, 900, 33, 57, 44, 30, 1880
# MISSIONS: the ladder (3 tiers) + the mission column; the pick list (CHOOSE A MISSION)
NMS = 8
MS_LX, MS_LY0, MS_LDY, MS_PW, MS_PH = 148, 580, 300, 256, 164
MS_TX, MS_TX1 = 452, 1800
MS_R0 = 2020
MS_BAR_X0, MS_BAR_X1, MS_BAR_Y = 2020, 3700, 1360
MS_PICK_Y0, MS_PICK_DY, MS_PICK_W, MS_PICK_H = 560, 128, 1660, 112
MS_LAD_PICK_DX, MS_LAD_PICK_DY = 1872, 380          # the ladder's offset while the pick list is up (it is the focused mission's tiers in the right column then)


def _sec(b, g, name, x0, x1, y, title, right=""):
    return nr.section(b, g, name, x0, x1, y, title, right)


def build_page(main):
    t, root0, anim0 = _templates(main)
    b = Builder(t)
    root = copy.deepcopy(root0); root.update(guid=t2guid.guid())
    anim = copy.deepcopy(anim0); anim.update(guid=t2guid.guid(), parent=root["guid"])
    b.items += [root, anim]
    a = anim["guid"]
    nr.frame(b, a, "WLF CLAN", "OVERVIEW", tabs_labels=TABS, active_tab=0, wk=(1, 1, 0), prompts=4)
    b.text("ldTx", a, b.tl(nr.L0, 900, nr.R1 - nr.L0, 200), "", nr.pt(26), nr.GREY, align=1, tracking=3, multiline=1, visible=0)

    # ---------------------------------------------------------------- OVERVIEW
    ov = b.group("ov", a, b.tl(0, 0, 3840, 2160))["guid"]
    _sec(b, ov, "ovSt", nr.L0, OV_L1, OV_ST_Y, "STATUS UPDATES", "SINCE YOU LAST LOOKED")
    for i in range(NST):
        g = nr.plain_tile(b, ov, f"stRow{i}", nr.L0 + i * OV_ST_DX, OV_ST_T, OV_ST_W, OV_ST_H)
        portrait(b, g, f"stPt{i}", 28, 16, 284, 240)
        b.text(f"stName{i}", g, nr.lm(24, 276, OV_ST_W - 40, 56), "", nr.pt(20), nr.GREY, tracking=2)
        nr.dot(b, g, f"stNew{i}", OV_ST_W - 32, 36, visible=0)
    nr.focus_frame(b, ov, "ovFo")
    _sec(b, ov, "ovSu", nr.L0, OV_L1, OV_SU_Y, "SUPPLIES")
    b.text("ovLastLb", ov, nr.lm(OV_L1 - 1400, OV_SU_Y - 28, 1100, 56, right=1), "", nr.pt(20), nr.GREY, align=2, tracking=3)
    b.text("ovLast", ov, nr.lm(OV_L1 - 400, OV_SU_Y - 40, 400, 80, right=1), "", nr.pt(34), nr.WHITE, align=2, tracking=2)
    b.text("ovSupNone", ov, nr.lm(nr.L0, OV_SU_T + 40, 2200, 60), "", nr.pt(20), nr.GREY, tracking=3)
    for k in range(NTILE):
        g = nr.plain_tile(b, ov, f"tlRow{k}", nr.L0 + k * OV_ST_DX, OV_SU_T, OV_SU_W, OV_SU_H)
        b.image(f"tlIc{k}", g, b.tl(28, 28, 88, 96), "streaming/t2r/icons/c13-food.png", nr.WHITE, 220, scaleMode="StretchAspect")
        b.text(f"tlLb{k}", g, nr.lm(140, 28, OV_SU_W - 150, 44), "", nr.pt(16), nr.GREY, tracking=3)
        b.text(f"tlNum{k}", g, nr.lm(140, 76, OV_SU_W - 150, 76), "", nr.pt(34), nr.WHITE, tracking=1)
        nr.bar(b, g, f"tlBar{k}", 28, OV_SU_W - 28, 210, h=6)
        b.text(f"tlDays{k}", g, nr.lm(28, 232, OV_SU_W - 40, 48), "", nr.pt(17), nr.GREY, tracking=2)
    _sec(b, ov, "ovCa", nr.L0, OV_L1, OV_CA_Y, "CAMP")
    b.text("moLb", ov, nr.lm(nr.L0, MO_Y - 28, 380, 56), "CAMP MORALE", nr.pt(20), nr.GREY, tracking=3)
    nr.bar(b, ov, "mo", MO_X0, MO_X1, MO_Y - 4, h=8, ticks=5)
    b.rect("moPin", ov, b.tl(MO_X1 - 3, MO_Y - 22, 6, 44), nr.WHITE, 255)
    b.text("moWord", ov, nr.lm(MO_X1 + 60, MO_Y - 36, 700, 72), "", nr.pt(24), nr.WHITE, tracking=3)
    for k, lab in enumerate(("CAMPAIGNS COMPLETED", "CLANS LOST", "LARGEST CLAN", "YOUR RANK")):      # (YOUR RANK: the 2013 rank = weeks survived in total, was the header's line)
        x = nr.L0 + k * 558
        b.text(f"ovCs{k}Lb", ov, nr.lm(x, 1612 - 26, 540, 52), lab, nr.pt(18), nr.GREY, tracking=3)
        b.text(f"ovCs{k}", ov, nr.lm(x, 1680 - 36, 540, 72), "", nr.pt(30), nr.WHITE, tracking=1)
    od = b.group("ovDt", ov, b.tl(0, 0, 3840, 2160))["guid"]
    _sec(b, od, "ovDs", OV_R0, nr.R1, OV_ST_Y, "")
    portrait(b, od, "ovDt", OV_R0, 512, 500, 448)
    b.text("ovDtRole", od, nr.lm(OV_R0 + 560, 580 - 26, 620, 52), "", nr.pt(20), nr.GREY, tracking=3)
    b.text("ovDtName", od, nr.lm(OV_R0 + 560, 660 - 44, 620, 88), "", nr.pt(42), nr.WHITE, tracking=2)
    b.image("ovDtIc", od, b.tl(OV_R0 + 560, 740, 40, 64), "streaming/t2r/icons/c13-person.png", nr.WHITE, 230, scaleMode="StretchAspect", visible=0)
    b.text("ovDtWord", od, nr.lm(OV_R0 + 624, 772 - 34, 560, 68), "", nr.pt(22), nr.WHITE, tracking=3)
    nr.dot(b, od, "ovDtNew", OV_R0 + 576, 876, visible=0)
    b.text("ovDtNewTx", od, nr.lm(OV_R0 + 608, 876 - 28, 300, 56), "NEW", nr.pt(20), nr.ACC, tracking=3, visible=0)
    b.text("ovDtLine", od, b.tl(OV_R0, 1004, nr.R1 - OV_R0, 140), "", nr.pt(24), nr.WHITE, multiline=1, valign=0, tracking=1)
    nr.chip(b, od, "ovDtRd", OV_R0, 1210, "READ IN THE JOURNAL")
    _sec(b, ov, "ovRc", OV_R0, nr.R1, OV_REC_Y, "RECENTLY IN CAMP")
    for i in range(NREC):
        y = OV_REC_T + OV_REC_DY * i
        b.text(f"ovRecDay{i}", ov, nr.lm(OV_R0, y - 26, 190, 52), "", nr.pt(20), nr.GREY, tracking=3)
        b.text(f"ovRecTx{i}", ov, nr.lm(OV_R0 + 200, y - 30, nr.R1 - OV_R0 - 200, 60), "", nr.pt(26), nr.WHITE, tracking=1)
        b.rect(f"ovRecLn{i}", ov, b.tl(OV_R0, y + 50, nr.R1 - OV_R0, nr.HAIR), nr.WHITE, 30)

    # ---------------------------------------------------------------- SURVIVORS: a row per role, 7 tiles visible per row, 3 rows visible
    sv = b.group("sv", a, b.tl(0, 0, 3840, 2160), visible=0)["guid"]
    b.text("svTitle", sv, nr.lm(nr.L0, OV_ST_Y - 30, 1200, 60), "SURVIVORS", nr.pt(26), nr.WHITE, tracking=3)
    b.text("svCount", sv, nr.lm(nr.L0 + 380, OV_ST_Y - 30, 400, 60), "", nr.pt(26), nr.GREY, tracking=3)
    for r in range(SV_ROWS):
        rg = b.group(f"svR{r}", sv, b.tl(0, SV_RY0 + r * SV_RDY, 3840, SV_RDY))["guid"]       # (clan13.c shows / hides a row; the rows never move)
        _sec(b, rg, f"svS{r}", nr.L0, SV_L1, 0, "GUARDS", "5")
        for c in range(SV_COLS):
            g = nr.plain_tile(b, rg, f"sv{r}_{c}", nr.L0 + c * SV_TDX, SV_TOP, SV_TW, SV_TH)
            portrait(b, g, f"sv{r}_{c}P", 16, 8, SV_TW - 32, SV_TH - 20)
            b.rect(f"sv{r}_{c}Sb", g, b.tl(0, SV_TH - 8, SV_TW, 8), nr.WHITE, 230, visible=0)
            b.text(f"sv{r}_{c}N", g, nr.lm(4, SV_TH + 18, SV_TW + 20, 52), "", nr.pt(19), nr.GREY, tracking=2)
            b.text(f"sv{r}_{c}W", g, nr.lm(4, SV_TH + 66, SV_TW + 20, 40), "", nr.pt(15), nr.GREY, tracking=2)
            nr.dot(b, g, f"sv{r}_{c}D", SV_TW - 28, 28, visible=0)
    nr.focus_frame(b, sv, "svFo")
    nr.scroll_v(b, sv, "svSb", SV_SB_X, SV_SB_Y0, SV_SB_Y1, 0.0, 0.5)
    b.text("svFoot", sv, nr.lm(nr.L0, 1880 - 24, 1200, 48), "", nr.pt(17), nr.GREY, tracking=3)
    sd = b.group("svDt", sv, b.tl(0, 0, 3840, 2160))["guid"]
    _sec(b, sd, "svDs", SV_R0, nr.R1, OV_ST_Y, "")
    portrait(b, sd, "svDt", SV_R0, 512, 460, 428)
    b.text("svDtRole", sd, nr.lm(SV_R0 + 512, 592 - 26, 600, 52), "", nr.pt(20), nr.GREY, tracking=3)
    b.text("svDtName", sd, nr.lm(SV_R0 + 512, 680 - 44, 600, 88), "", nr.pt(42), nr.WHITE, tracking=2)
    b.text("svDtSub", sd, nr.lm(SV_R0 + 512, 776 - 30, 600, 60), "", nr.pt(22), nr.WHITE, tracking=3)
    b.text("svDtTag", sd, b.tl(SV_R0, 1004, nr.R1 - SV_R0, 180), "", nr.pt(24), nr.WHITE, multiline=1, valign=0, tracking=1)
    _sec(b, sd, "svDc", SV_R0, nr.R1, 1232, "CLOSE TO")
    portrait(b, sd, "svDtB", SV_R0, 1278, 164, 164)
    b.text("svDtBond", sd, nr.lm(SV_R0 + 200, 1324 - 30, 900, 60), "", nr.pt(28), nr.WHITE, tracking=2)
    nr.chip(b, sd, "svDtBt", SV_R0 + 200, 1400, "FAMILY", style="grey", pts=nr.pt(18))
    _sec(b, sd, "svDl", SV_R0, nr.R1, 1560, "LATELY")
    b.text("svDtLately", sd, b.tl(SV_R0, 1604, nr.R1 - SV_R0, 240), "", nr.pt(24), nr.WHITE, multiline=1, valign=0, tracking=1)

    # ---------------------------------------------------------------- RAIDS: a row per week (newest first), 3 tiles visible per row, 2 rows visible
    rd = b.group("rds", a, b.tl(0, 0, 3840, 2160), visible=0)["guid"]
    b.text("rdTitle", rd, nr.lm(nr.L0, OV_ST_Y - 30, 400, 60), "RAIDS", nr.pt(26), nr.WHITE, tracking=3)
    b.text("rdHint", rd, nr.lm(nr.L0 + 240, OV_ST_Y - 26, RD_L1 - nr.L0 - 240, 52), "", nr.pt(18), nr.GREY, tracking=3)
    for r in range(RD_ROWS):
        rg = b.group(f"rdR{r}", rd, b.tl(0, RD_RY0 + r * RD_RDY, 3840, RD_RDY))["guid"]
        _sec(b, rg, f"rdS{r}", nr.L0, RD_L1, 0, "WEEK 2", "2")
        for c in range(RD_COLS):
            g = nr.plain_tile(b, rg, f"rd{r}_{c}", nr.L0 + c * RD_TDX, RD_TOP, RD_TW, RD_TH)
            b.text(f"rd{r}_{c}Dy", g, nr.lm(32, 56 - 26, 400, 52), "", nr.pt(18), nr.GREY, tracking=3)
            nr.dot(b, g, f"rd{r}_{c}D", RD_TW - 40, 56, visible=0)
            b.text(f"rd{r}_{c}M", g, nr.lm(32, 136 - 36, RD_TW - 64, 72), "", nr.pt(26), nr.GREY, tracking=2)
            b.text(f"rd{r}_{c}W", g, nr.lm(32, 236 - 24, RD_TW - 64, 48), "", nr.pt(17), nr.GREY, tracking=3)
            b.text(f"rd{r}_{c}SL", g, nr.lm(32, 320 - 22, 300, 44), "SUPPLIES", nr.pt(15), nr.GREY, tracking=3)
            b.text(f"rd{r}_{c}N", g, nr.lm(RD_TW - 332, 320 - 38, 300, 76, right=1), "", nr.pt(34), nr.GREY, align=2, tracking=2)
            nr.bar(b, g, f"rd{r}_{c}B", 32, RD_TW - 32, 390, h=6)
    nr.focus_frame(b, rd, "rdFo")
    nr.scroll_v(b, rd, "rdSb", RD_SB_X, 540, 1600, 0.0, 0.5)
    dd = b.group("rdDt", rd, b.tl(0, 0, 3840, 2160))["guid"]
    _sec(b, dd, "rdDs", RD_R0, nr.R1, OV_ST_Y, "")
    b.text("rdDtBig", dd, nr.lm(RD_R0, 616 - 76, 400, 152), "", nr.pt(76), nr.WHITE, tracking=1)
    b.text("rdDtOf", dd, nr.lm(RD_R0 + 112, 632 - 30, 1000, 60), "", nr.pt(26), nr.GREY, tracking=3)
    nr.chip(b, dd, "rdVd", nr.R1 - 300, 620, "SHORT BY 3", style="grey", pts=nr.pt(24))
    for k in range(NBAR):
        y = RD_BAR_Y0 + RD_BAR_DY * k
        b.image(f"rdBIc{k}", dd, b.tl(RD_R0, y - 40, 72, 80), "streaming/t2r/icons/c13-food.png", nr.WHITE, 220, scaleMode="StretchAspect")
        b.text(f"rdBLb{k}", dd, nr.lm(RD_R0 + 108, y - 26, 400, 52), "", nr.pt(19), nr.GREY, tracking=3)
        nr.bar(b, dd, f"rdB{k}", RD_BAR_X0, RD_BAR_X1, y - 3, h=6)
        b.rect(f"rdBNeed{k}", dd, b.tl(RD_BAR_X1 - 2, y - 18, 3, 40), nr.WHITE, 255)
        b.text(f"rdBDelta{k}", dd, nr.lm(3440, y - 22, 120, 44, right=1), "", nr.pt(16), nr.GREY, align=2, tracking=1)
        b.text(f"rdBNum{k}", dd, nr.lm(nr.R1 - 300, y - 30, 300, 60, right=1), "", nr.pt(26), nr.WHITE, align=2, tracking=2)
    _sec(b, dd, "rdLs", RD_R0, nr.R1, 1360, "BROUGHT HOME")
    for k in range(NLOOT):
        g = nr.plain_tile(b, dd, f"ltRow{k}", RD_R0 + (k % 2) * 768, 1412 + (k // 2) * 204, 744, 188)
        b.image(f"ltIc{k}", g, b.tl(28, 32, 96, 124), "streaming/t2r/icons/c13-keepsake.png", nr.WHITE, 220, scaleMode="StretchAspect")
        b.text(f"ltQty{k}", g, nr.lm(160, 64 - 30, 400, 60), "", nr.pt(26), nr.WHITE, tracking=1)
        b.text(f"ltNm{k}", g, nr.lm(160, 128 - 24, 560, 48), "", nr.pt(19), nr.GREY, tracking=1)
        nr.dot(b, g, f"ltNew{k}", 704, 40, visible=0)

    # ---------------------------------------------------------------- JOURNAL: a row per week (newest first), its day tiles; 3 rows visible
    jr = b.group("jrn", a, b.tl(0, 0, 3840, 2160), visible=0)["guid"]
    for r in range(JR_ROWS):
        rg = b.group(f"jrR{r}", jr, b.tl(0, JR_RY0 + r * JR_RDY, 3840, JR_RDY))["guid"]
        _sec(b, rg, f"jrS{r}", nr.L0, JR_L1, 0, "WEEK 2", "4 | 3  WON | LOST")
        for c in range(JR_COLS):
            g = nr.plain_tile(b, rg, f"jd{r}_{c}", nr.L0 + c * JR_TDX, JR_TOP, JR_TW, JR_TH)
            b.text(f"jd{r}_{c}Dy", g, nr.lm(24, 52 - 24, JR_TW - 40, 48), "", nr.pt(17), nr.GREY, tracking=3)
            nr.dot(b, g, f"jd{r}_{c}D", JR_TW - 30, 52, visible=0)
            b.text(f"jd{r}_{c}M", g, nr.lm(24, 164 - 26, JR_TW - 40, 52), "", nr.pt(15), nr.GREY, tracking=2)
            b.text(f"jd{r}_{c}W", g, nr.lm(24, 236 - 30, JR_TW - 40, 60), "", nr.pt(20), nr.GREY, tracking=3)
            b.rect(f"jd{r}_{c}B", g, b.tl(24, 300, JR_TW - 48, 6), nr.WHITE, 230)
    nr.focus_frame(b, jr, "jrFo")
    nr.scroll_v(b, jr, "jrSb", JR_SB_X, JR_RY0, 1860, 0.0, 0.5)
    jt = b.group("jtPane", jr, b.tl(0, 0, 3840, 2160))["guid"]
    _sec(b, jt, "jtS", JR_R0, nr.R1, JR_RY0, "")
    b.text("jtTitle", jt, nr.lm(JR_R0, 584 - 50, nr.R1 - JR_R0, 100), "", nr.pt(38), nr.WHITE, tracking=2)
    b.text("jtF0", jt, nr.lm(JR_R0, 692 - 30, nr.R1 - JR_R0, 60), "", nr.pt(22), nr.WHITE, tracking=2)
    b.text("jtF1", jt, nr.lm(JR_R0, 784 - 34, nr.R1 - JR_R0, 68), "", nr.pt(22), nr.WHITE, tracking=2)
    b.rect("jtRule", jt, b.tl(JR_R0, 856, nr.R1 - JR_R0, nr.HAIR), nr.WHITE, 40)
    for k in range(NJP):
        b.text(f"jtCap{k}", jt, b.tl(JT_X, JT_Y0 + 200 * k, JT_W, 40), "", nr.pt(17), nr.GREY, tracking=3)
        b.text(f"jtBo{k}", jt, b.tl(JT_X, JT_Y0 + 200 * k + JT_CAP_H, JT_W, 1000), "", JT_PT, nr.WHITE, multiline=1, valign=0, tracking=1)

    # ---------------------------------------------------------------- MISSIONS
    ms = b.group("ms", a, b.tl(0, 0, 3840, 2160), visible=0)["guid"]
    b.text("msTitle", ms, nr.lm(nr.L0, 464 - 30, 1400, 60), "", nr.pt(26), nr.GREY, tracking=3)
    b.text("msSub", ms, nr.lm(nr.L0 + 700, 464 - 26, 1700, 52), "", nr.pt(18), nr.GREY, tracking=3)
    for i in range(NMS):
        g = nr.plain_tile(b, ms, f"msRow{i}", nr.L0, MS_PICK_Y0 + i * MS_PICK_DY, MS_PICK_W, MS_PICK_H)
        b.text(f"msNm{i}", g, nr.lm(36, MS_PICK_H / 2 - 30, 1200, 60), "", nr.pt(26), nr.GREY, tracking=2)
        b.text(f"msRp{i}", g, nr.lm(MS_PICK_W - 436, MS_PICK_H / 2 - 22, 400, 44, right=1), "", nr.pt(17), nr.GREY, align=2, tracking=3)
    for k, y in enumerate((1660, 1724, 1800)):
        b.text(("msRep", "msRep2", "msStatus")[k], ms, nr.lm(nr.L0, y - 26, MS_PICK_W, 52), "", nr.pt(18), nr.GREY if k < 2 else nr.WHITE, tracking=3)
    ld = b.group("msLad", ms, b.tl(0, 0, 3840, 2160))["guid"]            # the 3 tiers (clan13.c moves the group to the right column for the pick list)
    for k in range(3):
        y = MS_LY0 + k * MS_LDY
        if k < 2:
            b.rect(f"msLk{k}", ld, b.tl(MS_LX + MS_PW / 2 - nr.HAIR / 2, y + MS_PH, nr.HAIR, MS_LDY - MS_PH), nr.WHITE, 90)
        b.rect(f"msPl{k}", ld, b.tl(MS_LX, y, MS_PW, MS_PH), nr.TILE, TILE_DIM)
        b.image(f"msPi{k}", ld, b.ctr(MS_LX + MS_PW / 2, y + MS_PH / 2, 112, 112), "streaming/t2r/icons/c13-ms-lock.png", nr.WHITE, 230, scaleMode="StretchAspect")
        b.text(f"msTl{k}", ld, nr.lm(MS_TX, y + 28 - 22, 600, 44), f"TIER {k + 1}", nr.pt(18), nr.GREY, tracking=3)
        b.text(f"msTg{k}", ld, nr.lm(MS_TX1 - 600, y + 28 - 22, 600, 44, right=1), "", nr.pt(18), nr.GREY, align=2, tracking=3)
        b.text(f"msGo{k}", ld, nr.lm(MS_TX, y + 92 - 36, 900, 72), "", nr.pt(30), nr.GREY, tracking=2)
        b.text(f"msCn{k}", ld, nr.lm(MS_TX1 - 500, y + 92 - 34, 500, 68, right=1), "", nr.pt(28), nr.GREY, align=2, tracking=2)
        b.text(f"msUl{k}", ld, nr.lm(MS_TX, y + 184 - 28, 260, 56), "Unlocks:", nr.pt(22), nr.GREY)
        for q in range(2):
            nr.chip(b, ld, f"msC{q}_{k}", MS_TX + 200 + q * 300, y + 184 - 27, "+1 SURVIVOR", style="grey")
        nr.bar(b, ld, f"msB{k}", MS_TX, MS_TX1, y + 250, h=6)
    nr.focus_frame(b, ld, "msFo")
    pg = b.group("msPrg", ms, b.tl(0, 0, 3840, 2160), visible=0)["guid"]  # the running mission's column (the pick list's detail reuses icon / name / line)
    b.image("msRunIc", ms, b.tl(MS_R0, 500, 420, 420), "streaming/t2r/icons/skill-damage-marker.png", nr.WHITE, 230, scaleMode="StretchAspect")
    b.text("msRunNm", ms, nr.lm(MS_R0 + 500, 600 - 50, 1180, 100), "", nr.pt(46), nr.WHITE, tracking=3)
    b.text("msPrgDay", ms, b.tl(MS_R0 + 500, 680, 1180, 140), "", nr.pt(20), nr.GREY, multiline=1, valign=0, tracking=3)
    b.text("msRunMatchLb", pg, nr.lm(MS_R0, 1020 - 24, 200, 48), "MATCH", nr.pt(18), nr.GREY, tracking=3)
    b.text("msRunMatch", pg, nr.lm(MS_R0 + 180, 1020 - 30, 240, 60), "", nr.pt(26), nr.WHITE, tracking=2)
    for k in range(3):
        b.image(f"msRunPip{k}", pg, b.tl(MS_R0 + 440 + 80 * k, 996, 48, 48), "streaming/t2r/icons/c13-ms-pip0.png", nr.WHITE, 255, scaleMode="StretchAspect")
    b.text("msPrgNum", pg, nr.lm(MS_R0, 1200 - 90, 500, 180), "", nr.pt(90), nr.WHITE, tracking=1)
    b.text("msPrgLb", pg, nr.lm(MS_R0 + 140, 1224 - 30, 900, 60), "", nr.pt(22), nr.GREY, tracking=3)
    nr.bar(b, pg, "msBar", MS_BAR_X0, MS_BAR_X1, MS_BAR_Y - 4, h=8)
    for k in range(3):
        b.rect(f"msTk{k}", pg, b.tl(MS_BAR_X1 - 2, MS_BAR_Y - 16, 4, 48), nr.WHITE, 255)
        b.text(f"msTkLb{k}", pg, b.tl(MS_BAR_X1 - 100, MS_BAR_Y + 48, 200, 48), "", nr.pt(18), nr.GREY, align=1, tracking=2)
    b.text("msFoot", pg, nr.lm(MS_R0, 1600 - 24, 1680, 48), "", nr.pt(18), nr.GREY, tracking=3)

    # ---------------------------------------------------------------- icon / portrait residency (the engine streams a texture in when a widget first shows it)
    pre = b.group("pre", a, b.tl(0, 0, 3, 3))["guid"]
    for i in range(32):
        b.image(f"pre{i}", pre, b.tl(0, 0, 3, 3), "streaming/t2r/icons/c13-food.png", 0xFFFFFFFF, 255)
    w = {k: copy.deepcopy(v) for k, v in main.items() if k != "items"}
    w["items"] = b.items
    return w


STATS_PAGE = "clan13x"
XP_NROW = 12                                            # the row pool = C13_NX
XP_X0, XP_X1 = nr.L0, nr.R1
XP_RH, XP_PITCH = 104, 112                              # a row: height, pitch (up to 8 players; clan13.c squeezes to 76 / 80 above that)
XP_HD_Y = 480                                           # the column heads
XP_SEC_Y = 560                                          # the design position of a team's section row (US); THE ENEMY's is moved down by the client
XP_R0 = 660                                             # the design position of the first player row
XP_NAME_X, XP_AW_X = 171, 1000                          # row-relative: the name (after the rank badge: rank_badge_widgets.reserved(40, 104)), the award word
XP_COL_R = (1980, 2260, 2540, 2820, 3100)               # right edges (row-relative) of DOWNS EXECUTIONS REVIVES HEADSHOTS DEATHS; PARTS follows at the row end
XP_HEADS = ("DOWNS", "EXECUTIONS", "REVIVES", "HEADSHOTS", "DEATHS")
XP_COL_W = 260


def build_stats_page(main):
    """to1/clan13x: PLAYER STATS of one raid / the post-match scoreboard, pushed over to1/clan13 by clan13.c; the clan frame (breadcrumb, week block, boxed prompts), the
    US / THE ENEMY sections as row headers (title, rule, MATCH WON / LOST + the team totals), the players as tile rows."""
    t, root0, anim0 = _templates(main)
    b = Builder(t)
    root = copy.deepcopy(root0); root.update(guid=t2guid.guid())
    anim = copy.deepcopy(anim0); anim.update(guid=t2guid.guid(), parent=root["guid"])
    b.items += [root, anim]
    a = anim["guid"]
    nr.frame(b, a, "WLF CLAN", "PLAYER STATS", tabs_labels=None, wk=(1, 1, 0), prompts=2)
    xp = b.group("mst2", a, b.tl(0, 0, 3840, 2160), visible=0)["guid"]
    b.text("xpSub", xp, nr.lm(nr.L0, 290 - 28, 2400, 56), "", nr.pt(20), nr.GREY, tracking=3)
    hh = b.group("xpHead", xp, b.tl(0, 0, 3840, 2160))["guid"]
    b.text("xpChPl", hh, nr.lm(XP_X0 + XP_NAME_X, XP_HD_Y - 22, 600, 44), "PLAYER", nr.pt(15), nr.GREY, tracking=3)
    b.text("xpChAw", hh, nr.lm(XP_X0 + XP_AW_X, XP_HD_Y - 22, 600, 44), "AWARD", nr.pt(15), nr.GREY, tracking=3)
    for k, lb in enumerate(XP_HEADS):
        b.text("xpCh%d" % k, hh, nr.lm(XP_X0 + XP_COL_R[k] - XP_COL_W, XP_HD_Y - 22, XP_COL_W, 44, right=1), lb, nr.pt(15), nr.GREY, align=2, tracking=2)
    b.text("xpChP", hh, nr.lm(XP_X1 - XP_COL_W - 24, XP_HD_Y - 22, XP_COL_W, 44, right=1), "PARTS", nr.pt(15), nr.GREY, align=2, tracking=3)
    for sec, tx in enumerate(("US", "THE ENEMY")):
        hy = XP_SEC_Y
        sg = b.group("xpSec%d" % sec, xp, b.tl(0, 0, 3840, 2160), visible=0)["guid"]            # moved down as a whole by the client (y offset from the design)
        b.text("xpHd%d" % sec, sg, nr.lm(XP_X0, hy - 34, 900, 68), tx, nr.pt(26), nr.WHITE, tracking=3)
        b.text("xpTag%d" % sec, sg, nr.lm(XP_X0 + 300, hy - 24, 600, 48), "", nr.pt(18), nr.GREY, tracking=3)
        b.rect("xpRule%d" % sec, sg, nr.lpiv(XP_X0 + 900, hy - nr.HAIR / 2, nr.RULE_W0, nr.HAIR), nr.WHITE, 40)
        for k in range(5):
            b.text("xpT%d_%d" % (k, sec), sg, nr.lm(XP_X0 + XP_COL_R[k] - XP_COL_W, hy - 26, XP_COL_W, 52, right=1), "", nr.pt(22), nr.GREY, align=2, tracking=2)
        b.text("xpTP%d" % sec, sg, nr.lm(XP_X1 - XP_COL_W - 24, hy - 26, XP_COL_W, 52, right=1), "", nr.pt(22), nr.GREY, align=2, tracking=2)
    for i in range(XP_NROW):
        g = b.group("xpRow%d" % i, xp, b.tl(XP_X0, XP_R0 + i * XP_PITCH, XP_X1 - XP_X0, XP_RH), visible=0)["guid"]
        b.rect("xpBg%d" % i, g, b.tl(0, 0, XP_X1 - XP_X0, XP_RH), nr.TILE, TILE_DIM)
        b.rect("xpMe%d" % i, g, b.tl(0, 0, 6, XP_RH), nr.ACC, 255, visible=0)          # the own row: the accent edge (+ YOU in the accent)
        rank_badge_widgets.add_to_builder(b, g, "xpRk%d" % i, "xpRn%d" % i, 28, XP_RH // 2, 40, XP_RH)
        b.text("xpNm%d" % i, g, nr.lm(XP_NAME_X, XP_RH / 2 - 32, 740, 64), "", nr.pt(26), nr.WHITE, tracking=1)
        b.text("xpTg%d" % i, g, nr.lm(XP_NAME_X + 300, XP_RH / 2 - 20, 200, 40), "", nr.pt(16), nr.GREY, tracking=3)
        b.text("xpAw%d" % i, g, nr.lm(XP_AW_X, XP_RH / 2 - 20, 760, 40), "", nr.pt(16), nr.GREY, tracking=3)
        for k in range(5):
            b.text("xpV%d_%d" % (k, i), g, nr.lm(XP_COL_R[k] - XP_COL_W, XP_RH / 2 - 32, XP_COL_W, 64, right=1), "", nr.pt(26), nr.WHITE, align=2, tracking=2)
        b.text("xpP%d" % i, g, nr.lm(XP_X1 - XP_X0 - XP_COL_W - 24, XP_RH / 2 - 32, XP_COL_W, 64, right=1), "", nr.pt(26), nr.WHITE, align=2, tracking=2)
        b.text("xpPm%d" % i, g, nr.lm(XP_X1 - XP_X0 - XP_COL_W - 24, XP_RH / 2 - 42, XP_COL_W, 84, right=1), "", nr.pt(36), nr.WHITE, align=2, tracking=2, visible=0)
    b.text("xpEmpty", xp, b.tl(nr.L0, 900, nr.R1 - nr.L0, 200), "", nr.pt(26), nr.GREY, align=1, tracking=3, multiline=1, visible=0)
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


def _vis(by, n, on):
    by[n]["visible"] = 1 if on else 0


def _fit(by, n, s, box=None):
    it = by[n]
    box = box or it["rectSizeDelta.width"]
    import re
    e = _est(re.sub("<[^>]*>", "", s), it["pointSize"]); sc = min(1.0, 0.92 * box / e) if e else 1.0
    if sc < 0.6 and "<" not in s:
        while len(s) > 3 and _est(s + "...", it["pointSize"] * 0.6) > 0.92 * box:
            s = s[:-1].rstrip()
        s += "..."
    it["text"] = s
    it["pointSize"] = it["pointSize"] * max(sc, 0.6)


def _grey(s):
    return '<font color="#8C8C8C">%s</font>' % s


def _tile(by, name, foc):
    by[name + "Bg"]["color.a"] = TILE_FOC if foc else TILE_DIM


def _pos(by, name):
    """absolute top-left of a tile group (its parents are full-screen groups at 0 or row groups at (0, y))."""
    it = by[name]
    x, y = it["pivotAs.x"], it["pivotAs.y"]
    par = next((p for p in by.values() if p.get("guid") == it.get("parent")), None)
    if par is not None and par.get("type") == "Group" and par["name"] not in ("anim-group",):
        y += par["pivotAs.y"] if par.get("pivotN.y", 0) == 0 else 0
    return x, y


def _chip(by, name, text, x=None, right=None):
    w = _est(text, by[name + "Tx"]["pointSize"]) * 1.06 + 32
    by[name + "Bg"]["rectSizeDelta.width"] = float(w)
    by[name + "Tx"]["text"] = text
    if right is not None:
        x = right - w
    if x is not None:
        by[name + "Bg"]["pivotAs.x"] = float(x)
        by[name + "Tx"]["pivotAs.x"] = float(x + 16)
    return w


def _sect(by, name, x0, x1, title, right=""):
    nr.demo_section(by, name, x0, x1, title, right)


def _rows_by_role(P):
    order, groups = [], {}
    for i, p in enumerate(P):
        if p[2] not in groups:
            order.append(p[2]); groups[p[2]] = []
        groups[p[2]].append(i)
    return [(r, groups[r]) for r in order]


def demo(page, tab, secs, ms=None, jfoc=None):
    """The page filled from the op 0xB7 texts (secs = {1..6: text}) the way clan13.c fills it; tab 0 overview .. 4 missions; the resting state (no tweens)."""
    w = copy.deepcopy(page)
    by = {i["name"]: i for i in w["items"]}
    nr.demo_chips(by)
    vis = lambda n, on: _vis(by, n, on)
    txt = lambda n, s: by[n].__setitem__("text", s)
    img = lambda n, p: by[n].__setitem__("path", p)
    fit = lambda n, s, box=None: _fit(by, n, s, box)

    def pic(n, pid, show=True):
        a = (pid or "").split("/")
        if len(a) == 4:
            img(n + "Im", "streaming/t2r/icons/c13p-%s_%s.png" % (a[2], a[3]))
            vis(n + "Im", show)
        else:
            vis(n + "Im", False)

    def box(n, s, lines):
        it = by[n]
        it["text"] = clip(s, it["rectSizeDelta.width"], it["pointSize"], lines)
    H = _lines(secs[1], "H")[0]
    week, dow, mv, done = int(H[1]), int(H[2]), int(H[4]), int(H[8])
    nr.demo_header(by, "WLF CLAN" if H[3] == "W" else "SERAPHITE CLAN", TABS[tab])
    nr.demo_tabs(by, TABS, tab)
    nr.demo_week(by, week, dow, done)
    for g, on in (("ov", tab == 0), ("sv", tab == 1), ("rds", tab == 2), ("jrn", tab == 3), ("ms", tab == 4)):
        vis(g, on)
    P, J, M = _lines(secs[1], "P"), _lines(secs[2], "J"), _lines(secs[3], "M")
    U, S = _lines(secs[4], "U"), _lines(secs[3], "S")
    prompts = [("menu:prev+menu:next", "TABS", True, "menu:prev"), ("menu:back", "BACK", True, "menu:back")]
    if tab == 0:
        foc = 0
        _sect(by, "ovSt", nr.L0, OV_L1, "STATUS UPDATES", "SINCE YOU LAST LOOKED" if U else "NOTHING NEW SINCE YOU LAST LOOKED")
        for i in range(NST):
            vis(f"stRow{i}", i < len(U))
            if i < len(U):
                u = U[i]
                _tile(by, f"stRow{i}", i == foc)
                pic(f"stPt{i}", u[5]); by[f"stPt{i}Im"]["color.a"] = 255 if i == foc else 150
                fit(f"stName{i}", u[1].upper() if i == foc else _grey(u[1].upper()))
                vis(f"stNew{i}", i < 2)
        if U:
            nr.demo_frame(by, "ovFo", nr.L0 + foc * OV_ST_DX, OV_ST_T, OV_ST_W, OV_ST_H)
            u = U[foc]
            _sect(by, "ovDs", OV_R0, nr.R1, f"{u[2]}  |  {u[1].upper()}")
            pic("ovDt", u[5]); txt("ovDtRole", u[2]); fit("ovDtName", u[1].upper())
            vis("ovDtIc", u[3] in STICON); img("ovDtIc", "streaming/t2r/icons/c13-" + STICON.get(u[3], "pills") + ".png"); txt("ovDtWord", u[4])
            vis("ovDtNew", foc < 2); vis("ovDtNewTx", foc < 2)
            box("ovDtLine", u[6], 3)
            _chip(by, "ovDtRd", "READ IN THE JOURNAL", x=OV_R0)
        vis("ovDt", bool(U))
        _sect(by, "ovSu", nr.L0, OV_L1 - 700 if S else OV_L1, "SUPPLIES")
        txt("ovSupNone", "" if S else "NO SUPPLIES BOOKED YET - THEY ARE COUNTED AFTER EACH RAID")
        txt("ovLastLb", "THE STOCK LASTS" if S else ""); txt("ovLast", f"{H[7]} DAYS" if S and int(H[7]) >= 0 else "")
        for k in range(NTILE):
            vis(f"tlRow{k}", k < len(S))
            if k < len(S):
                s = S[k]
                img(f"tlIc{k}", "streaming/t2r/icons/c13-" + ("food", "water", "medicine", "ammo", "materials")[k] + ".png")
                txt(f"tlLb{k}", s[1]); txt(f"tlNum{k}", s[2] if int(s[2]) else _grey("NONE")); txt(f"tlDays{k}", f"{s[3]} DAYS" if int(s[3]) >= 0 else "IN CAMP")
                x = nr.L0 + k * OV_ST_DX
                nr.demo_bar(by, f"tlBar{k}", 28, OV_SU_W - 28, min(1.0, int(s[2]) / 12.0))
        _sect(by, "ovCa", nr.L0, OV_L1, "CAMP")
        nr.demo_bar(by, "mo", MO_X0, MO_X1, max(3, mv) / 100.0)
        by["moPin"]["pivotAs.x"] = MO_X0 + (MO_X1 - MO_X0) * mv / 100.0 - 3
        band = 3 if mv >= 70 else 2 if mv >= 50 else 1 if mv >= 30 else 0
        txt("moWord", ("GRIM", "STRAINED", "STEADY", "HOPEFUL")[band])
        for k, v in enumerate((H[9], H[10], H[11], "%d WEEKS" % (week + 2))):
            txt(f"ovCs{k}", v)
        recs = [j for j in J if j[3]][:NREC]
        _sect(by, "ovRc", OV_R0, nr.R1, "RECENTLY IN CAMP" if recs else "")
        for i in range(NREC):
            on = i < len(recs)
            vis(f"ovRecLn{i}", on); txt(f"ovRecDay{i}", f"DAY {recs[i][8]}" if on else ""); fit(f"ovRecTx{i}", recs[i][3].capitalize() if on else "")
        if U:
            prompts = [("menu:select", "JOURNAL", True, "menu:select")] + prompts
    elif tab == 1:
        txt("svCount", str(len(P)))
        rows = _rows_by_role(P)
        fr, fc = min(1, len(rows) - 1), 0
        for r in range(SV_ROWS):
            vis(f"svR{r}", r < len(rows))
            if r >= len(rows):
                continue
            role, mem = rows[r]
            _sect(by, f"svS{r}", nr.L0, SV_L1, role + "S", str(len(mem)))
            for c in range(SV_COLS):
                on = c < len(mem)
                vis(f"sv{r}_{c}", on)
                if not on:
                    continue
                p = P[mem[c]]
                f = r == fr and c == fc
                _tile(by, f"sv{r}_{c}", f)
                pic(f"sv{r}_{c}P", p[6]); by[f"sv{r}_{c}PIm"]["color.a"] = 255 if f else 150 if p[3] == "h" else 190
                vis(f"sv{r}_{c}Sb", p[3] != "h"); by[f"sv{r}_{c}Sb"]["color.a"] = 230 if p[3] in "us" else 120
                fit(f"sv{r}_{c}N", p[1].upper() if f else _grey(p[1].upper()), SV_TW)
                txt(f"sv{r}_{c}W", p[4] if p[3] != "h" else "")
        nr.demo_frame(by, "svFo", nr.L0 + fc * SV_TDX, SV_RY0 + fr * SV_RDY + SV_TOP, SV_TW, SV_TH)
        sh = min(SV_ROWS, len(rows))
        txt("svFoot", f"{sh} | {len(rows)} GROUPS")
        if len(rows) > SV_ROWS:
            by["svSbH"]["rectSizeDelta.height"] = (SV_SB_Y1 - SV_SB_Y0) * SV_ROWS / len(rows)
        else:
            vis("svSbT", False); vis("svSbH", False)
        if rows:
            p = P[rows[fr][1][fc]]
            nm = CODE2NAME.get(p[3], "healthy")
            _sect(by, "svDs", SV_R0, nr.R1, f"{p[2]}  |  {p[4]}" if p[3] != "h" else p[2])
            pic("svDt", p[6]); txt("svDtRole", p[2]); fit("svDtName", p[1].upper()); txt("svDtSub", p[4] if p[3] != "h" else "")
            box("svDtTag", p[9], 3)
            _sect(by, "svDc", SV_R0, nr.R1, "CLOSE TO" if p[7] else "")
            pic("svDtB", next((q[6] for q in P if q[1] == p[7]), "")); fit("svDtBond", p[7].upper())
            vis("svDtBtBg", bool(p[8])); vis("svDtBtTx", bool(p[8]))
            if p[8]:
                _chip(by, "svDtBt", p[8].upper(), x=SV_R0 + 200)
            _sect(by, "svDl", SV_R0, nr.R1, "LATELY" if p[10] else "")
            box("svDtLately", p[10], 4)
    elif tab == 2:
        txt("rdHint", "SELECT A RAID TO SEE WHAT IT BROUGHT HOME" if M else "NO RAIDS YET - PLAY A MATCH TO SEND A PARTY OUT")
        weeks = []
        for i, m in enumerate(M):
            wk = (int(m[1]) - 1) // 7 + 1
            if not weeks or weeks[-1][0] != wk:
                weeks.append((wk, []))
            weeks[-1][1].append(i)
        for r in range(RD_ROWS):
            vis(f"rdR{r}", r < len(weeks))
            if r >= len(weeks):
                continue
            wk, ids = weeks[r]
            _sect(by, f"rdS{r}", nr.L0, RD_L1, f"WEEK {wk}", str(len(ids)))
            for c in range(RD_COLS):
                vis(f"rd{r}_{c}", c < len(ids))
                if c >= len(ids):
                    continue
                m = M[ids[c]]
                f = r == 0 and c == 0
                _tile(by, f"rd{r}_{c}", f)
                txt(f"rd{r}_{c}Dy", f"DAY {(int(m[1]) - 1) % 7 + 1}"); vis(f"rd{r}_{c}D", f)
                fit(f"rd{r}_{c}M", m[2].upper() if f else _grey(m[2].upper()))
                txt(f"rd{r}_{c}W", "MATCH WON" if m[3] == "1" else "MATCH LOST" if m[3] == "0" else "")
                txt(f"rd{r}_{c}N", f"{m[4]} | {m[5]}" if f else _grey(f"{m[4]} | {m[5]}"))
                nr.demo_bar(by, f"rd{r}_{c}B", 32, RD_TW - 32, min(1.0, int(m[4]) / max(1, int(m[5]))))
        vis("rdDt", bool(M))
        vis("rdSbT", len(weeks) > RD_ROWS); vis("rdSbH", len(weeks) > RD_ROWS)
        if M:
            nr.demo_frame(by, "rdFo", nr.L0, RD_RY0 + RD_TOP, RD_TW, RD_TH)
            m = M[0]
            got = [int(x) for x in m[7].split()]; need = [int(x) for x in m[8].split()]
            _sect(by, "rdDs", RD_R0, nr.R1, f"{m[2].upper()}  |  SUPPLIES BROUGHT HOME")
            txt("rdDtBig", m[4]); by["rdDtOf"]["pivotAs.x"] = RD_R0 + _est(m[4], by["rdDtBig"]["pointSize"]) * 1.06 + 28
            txt("rdDtOf", f"| {m[5]} NEEDED")
            ok = int(m[4]) >= int(m[5])
            _chip(by, "rdVd", f"ENOUGH, +{int(m[4]) - int(m[5])} OVER" if ok and int(m[4]) > int(m[5]) else "ENOUGH" if ok else f"SHORT BY {int(m[5]) - int(m[4])}", right=nr.R1)
            for k, ci in enumerate((0, 1, 2, 4)):
                mx = max(got[ci], need[ci], 1)
                img(f"rdBIc{k}", "streaming/t2r/icons/c13-" + ("food", "water", "medicine", "ammo", "materials")[ci] + ".png")
                txt(f"rdBLb{k}", ("FOOD", "WATER", "MEDICINE", "AMMO", "MATERIALS")[ci]); txt(f"rdBNum{k}", f"{got[ci]} | {need[ci]}" if need[ci] else str(got[ci]))
                nr.demo_bar(by, f"rdB{k}", RD_BAR_X0, RD_BAR_X1, got[ci] / mx)
                by[f"rdBNeed{k}"]["pivotAs.x"] = RD_BAR_X0 + (RD_BAR_X1 - RD_BAR_X0) * need[ci] / mx - 1
                vis(f"rdBNeed{k}", need[ci] > 0); txt(f"rdBDelta{k}", f"+{got[ci] - need[ci]}" if need[ci] and got[ci] > need[ci] else "")
            T = [t for t in _lines(secs[3], "T") if t[1] == m[1]][:NLOOT]
            _sect(by, "rdLs", RD_R0, nr.R1, "BROUGHT HOME" if T else "")
            for k in range(NLOOT):
                vis(f"ltRow{k}", k < len(T))
                if k < len(T):
                    img(f"ltIc{k}", "streaming/t2r/icons/c13-" + T[k][4] + ".png"); txt(f"ltQty{k}", f"x{T[k][2]}"); fit(f"ltNm{k}", T[k][3])
                    vis(f"ltNew{k}", k == 0)
            prompts = [("menu:action", "PLAYER STATS", True, "menu:action")] + prompts
    elif tab == 4:
        _demo_ms(by, ms, vis, txt, img, fit)
        if not (ms or "").startswith("running") and ms != "none":
            prompts = [("menu:select", "SELECT", ms != "chosen", "menu:select")] + prompts
    else:
        D, G, K = _lines(secs.get(6, ""), "D"), _lines(secs.get(6, ""), "G"), _lines(secs.get(6, ""), "K")
        top = int(K[0][2]) if K else 1
        wks = list(range(top, 0, -1))
        fwk = int(K[0][1]) if K else top
        fr = wks.index(fwk) if fwk in wks else 0
        r0 = max(0, min(fr - 1, len(wks) - JR_ROWS))
        rows_f = [d for d in D if int(d[3]) == fwk]
        fc = len(rows_f) - 1 if jfoc is None else max(0, min(jfoc, len(rows_f) - 1))
        for r in range(JR_ROWS):
            on = r0 + r < len(wks)
            vis(f"jrR{r}", on)
            if not on:
                continue
            wk = wks[r0 + r]
            rows = [d for d in D if int(d[3]) == wk]
            won, lost = sum(1 for d in rows if d[8] == "1"), sum(1 for d in rows if d[8] == "0")
            act = wk == fwk
            _sect(by, f"jrS{r}", nr.L0, JR_L1, (f"WEEK {wk}" if act else _grey(f"WEEK {wk}")) + "  " + _grey("OF 12"), f"{won} | {lost}  WON | LOST")
            c0 = max(0, len(rows) - JR_COLS) if not act else max(0, min(fc - JR_COLS + 1, len(rows) - JR_COLS))
            for c in range(JR_COLS):
                vis(f"jd{r}_{c}", c0 + c < len(rows))
                if c0 + c >= len(rows):
                    continue
                d = rows[c0 + c]
                f = act and c0 + c == fc
                _tile(by, f"jd{r}_{c}", f)
                txt(f"jd{r}_{c}Dy", f"DAY {d[2]}" if int(d[1]) > 0 else "THE START")
                fit(f"jd{r}_{c}M", (d[7].upper() or d[5]) if f else _grey(d[7].upper() or d[5]), JR_TW - 40)
                wl = "WON" if d[8] == "1" else "LOST" if d[8] == "0" else ""
                txt(f"jd{r}_{c}W", wl if (act and d[8] == "1") or f else _grey(wl))
                vis(f"jd{r}_{c}B", d[8] in ("0", "1")); by[f"jd{r}_{c}B"]["color.a"] = (230 if act else 110) if d[8] == "1" else 40
                vis(f"jd{r}_{c}D", d[15] == "1")
                if f:
                    nr.demo_frame(by, "jrFo", nr.L0 + c * JR_TDX, JR_RY0 + r * JR_RDY + JR_TOP, JR_TW, JR_TH)
        vis("jrSbT", len(wks) > JR_ROWS); vis("jrSbH", len(wks) > JR_ROWS)
        vis("jtPane", bool(rows_f))
        if not rows_f:
            vis("ldTx", True); txt("ldTx", "NOTHING IS WRITTEN IN THE JOURNAL YET")
        else:
            d = rows_f[fc]
            _sect(by, "jtS", JR_R0, nr.R1, f"WEEK {fwk}  |  DAY {d[2]}" if int(d[1]) > 0 else "WEEK 1  |  THE START")
            fit("jtTitle", d[5])
            f0 = []
            if d[7]:
                f0.append(_grey("RAID") + "   " + d[7] + ("   " + _grey("WON" if d[8] == "1" else "LOST") if d[8] in ("0", "1") else ""))
            if int(d[10]) > 0:
                f0.append(_grey("SUPPLIES") + f"   {d[9]} | {d[10]}")
            txt("jtF0", "      ".join(f0))
            h, u, sk, dn = int(d[11]), int(d[12]), int(d[13]), int(d[14])
            txt("jtF1", "" if h < 0 else f"{h + u + sk} " + _grey("SURVIVORS") + (f" ({dn:+d})" if dn else "") + f"      {h} " + _grey("HEALTHY") + f"      {u} " + _grey("HUNGRY") + f"      {sk} " + _grey("SICK"))
            y = JT_Y0
            paras = [g for g in G if g[1] == d[1]]
            for k in range(NJP):
                vis(f"jtCap{k}", k < len(paras)); vis(f"jtBo{k}", k < len(paras))
                if k >= len(paras):
                    continue
                cap, text = paras[k][2], paras[k][3]
                if k == NJP - 1:
                    for g in paras[NJP:]:
                        text += BR2 + g[3]
                room = max(1, int((JT_Y1 - y - JT_CAP_H) // JT_LINE))
                body, n = wrap(text, JT_W, JT_PT, room)
                by[f"jtCap{k}"]["pivotAs.y"] = float(y); txt(f"jtCap{k}", cap)
                by[f"jtBo{k}"]["pivotAs.y"] = float(y + JT_CAP_H); txt(f"jtBo{k}", body)
                y += JT_CAP_H + n * JT_LINE + JT_GAP
        prompts = [("A / D", "DAY", True, None), ("W / S", "WEEK", True, None)] + prompts
    nr.demo_prompts(by, [(k, l, on, gl) for k, l, on, gl in prompts])
    return w


def _demo_ms(by, ms, vis, txt, img, fit):
    """clan13.c cl13_fill_ms / cl13_fill_ms_run, offline."""
    run = ms and ms.startswith("running")
    vis("msPrg", bool(run))
    if run:
        name, unit, icon, goals, cnt, match, ek, rep = MS_RUN[ms]
        u = unit.upper()
        txt("msTitle", "CURRENT MISSION"); txt("msSub", "")
        for i in range(NMS):
            vis(f"msRow{i}", False)
        for n in ("msRep", "msRep2", "msStatus"):
            txt(n, "")
        img("msRunIc", icon); fit("msRunNm", name.upper())
        reached = sum(1 for g in goals if cnt >= g)
        txt("msPrgDay", "COMPLETE" if reached >= 3 else {1: "NEW SURVIVORS - THE FURTHER YOU GET, THE MORE JOIN", 2: "ENEMY ATTACK - THE FURTHER YOU GET, THE FEWER YOU LOSE", 0: "THE FURTHER YOU GET, THE MORE BOOSTERS"}[ek])
        txt("msRunMatch", f"{match} | 3")
        for k in range(3):
            img(f"msRunPip{k}", "streaming/t2r/icons/c13-ms-pip%d.png" % (1 if k + 1 < match else 2 if k + 1 == match else 0))
        txt("msPrgNum", str(cnt)); by["msPrgLb"]["pivotAs.x"] = MS_R0 + _est(str(cnt), by["msPrgNum"]["pointSize"]) * 1.06 + 40; txt("msPrgLb", u)
        top = goals[2]
        nr.demo_bar(by, "msBar", MS_BAR_X0, MS_BAR_X1, min(cnt, top) / top)
        for k in range(3):
            x = MS_BAR_X0 + (MS_BAR_X1 - MS_BAR_X0) * goals[k] / top
            by[f"msTk{k}"]["pivotAs.x"] = x - 2; by[f"msTk{k}"]["color.a"] = 255 if cnt >= goals[k] else 120
            by[f"msTkLb{k}"]["pivotAs.x"] = x - 100; txt(f"msTkLb{k}", str(goals[k]))
        txt("msFoot", "NOTHING IS PAID BELOW TIER 1" + (f" - COMPLETED {rep} TIME{'S' if rep != 1 else ''} BEFORE: GOALS ARE HIGHER" if rep else ""))
        tiers = []
        for k in range(3):
            rew = (["LOSE %d%%" % (40, 20, 10)[k]] if ek == 2 else ["+%d SURVIVOR%s" % ((1, 2, 2)[k], "" if k == 0 else "S")] if ek == 1 else []) + ["x%d BOOSTERS" % (2, 2, 3)[k]]
            tiers.append((goals[k], rew))
        _demo_ladder(by, vis, txt, img, fit, tiers, cnt, u, reached, 0, 0)
        return
    rows = MS_SAMPLE if ms is None or ms in ("chosen", "attack") else []
    ek = 2 if ms == "attack" else 1
    txt("msTitle", "CHOOSE A MISSION"); txt("msSub", "YOU HAVE 3 MATCHES TO COMPLETE YOUR MISSION" if rows else "")
    foc = 1
    for i in range(NMS):
        vis(f"msRow{i}", i < len(rows))
        if i < len(rows):
            _tile(by, f"msRow{i}", i == foc)
            fit(f"msNm{i}", rows[i][0].upper() if i == foc else _grey(rows[i][0].upper())); txt(f"msRp{i}", f"DONE {rows[i][2]}X" if rows[i][2] else "")
    vis("msLad", bool(rows)); vis("msRunIc", bool(rows)); vis("msRunNm", bool(rows)); vis("msPrgDay", bool(rows))
    if not rows:
        vis("ms", False); vis("ldTx", True); txt("ldTx", "NO MISSION TO CHOOSE RIGHT NOW - THE NEXT CLAN EVENT BRINGS ONE")
        return
    nr.demo_frame(by, "msFo", nr.L0 - MS_LAD_PICK_DX, MS_PICK_Y0 + foc * MS_PICK_DY - MS_LAD_PICK_DY, MS_PICK_W, MS_PICK_H)      # (the outline lives in the moved ladder group)
    nm, unit, rep, goals = rows[foc]
    fit("msRunNm", nm.upper()); txt("msPrgDay", "3 MATCHES - THE FURTHER YOU GET, THE MORE YOU WIN")
    tiers = []
    for k in range(3):
        rew = (["LOSE %d%%" % (60, 40, 20)[k]] if ek == 2 else ["+%d SURVIVOR%s" % ((1, 2, 2)[k], "" if k == 0 else "S")]) + ["+%d BOOSTER%s" % ((1, 1, 2)[k], "S" if (1, 1, 2)[k] > 1 else "")]
        tiers.append((goals[k], rew))
    _demo_ladder(by, vis, txt, img, fit, tiers, -1, unit.upper(), -1, MS_LAD_PICK_DX, MS_LAD_PICK_DY)
    txt("msRep", "WITH NO TIER REACHED 60% OF THE CLAN IS LOST." if ek == 2 else "NOTHING IS PAID BELOW THE FIRST TIER.")
    txt("msRep2", f"COMPLETED {rep} TIME{'S' if rep != 1 else ''} BEFORE: THE GOALS ARE HIGHER." if rep else "")
    txt("msStatus", "MISSION STARTED" if ms == "chosen" else "")


def _demo_ladder(by, vis, txt, img, fit, tiers, cnt, unit, reached, dx, dy):
    by["msLad"]["pivotAs.x"] = float(dx); by["msLad"]["pivotAs.y"] = float(dy)
    for k, (goal, rew) in enumerate(tiers):
        y = MS_LY0 + k * MS_LDY
        cur = cnt >= 0 and k == min(reached, 2)
        done = cnt >= 0 and k < reached
        lock = cnt >= 0 and k > reached
        img(f"msPi{k}", "streaming/t2r/icons/c13-ms-" + ("check" if done else "lock" if lock else "cur") + ".png")
        if cnt < 0:
            img(f"msPi{k}", "streaming/t2r/icons/c13-ms-lock.png" if k else "streaming/t2r/icons/c13-ms-cur.png")
        txt(f"msTg{k}", f"{goal - cnt} TO GO" if cur and cnt < goal else "")
        txt(f"msGo{k}", f"{goal} {unit}" if cur or cnt < 0 else _grey(f"{goal} {unit}"))
        txt(f"msCn{k}", "" if cnt < 0 else (f"{min(cnt, goal)} | {goal}" if not lock else _grey(f"0 | {goal}")))
        x = MS_TX + _est("Unlocks:", by[f"msUl{k}"]["pointSize"]) * 1.06 + 24
        for q in range(2):
            on = q < len(rew)
            vis(f"msC{q}_{k}Bg", on); vis(f"msC{q}_{k}Tx", on)
            if on:
                x += _chip(by, f"msC{q}_{k}", rew[q], x=x) + 24
        nr.demo_bar(by, f"msB{k}", MS_TX, MS_TX1, 0 if cnt < 0 or lock else min(1.0, cnt / goal))
        vis(f"msB{k}F", cnt >= 0 and not lock and cnt > 0)
        if cur:
            nr.demo_frame(by, "msFo", MS_LX + dx, y + dy, MS_PW, MS_PH)


def stats_demo(page, secs_x=None, post=False):
    """PLAYER STATS (to1/clan13x) filled with a sample match (US 4 / THE ENEMY 4)."""
    w = copy.deepcopy(page)
    by = {i["name"]: i for i in w["items"]}
    nr.demo_header(by, "WLF CLAN", "PLAYER STATS")
    nr.demo_week(by, 2, 3, 9)
    by["mst2"]["visible"] = 1
    by["xpSub"]["text"] = "DAY 2   |   LODGE"
    players = [("Vex", 0, 1, (5, 1, 2, 3, 1), 140), ("Tal", 0, 0, (3, 0, 1, 1, 2), 90), ("Rook", 0, 0, (2, 2, 0, 0, 1), 60), ("June", 0, 0, (1, 0, 3, 0, 3), 40),
               ("Mara", 1, 0, (6, 1, 0, 2, 1), 120), ("Ilsa", 1, 0, (2, 0, 1, 0, 2), 70), ("Bo", 1, 0, (1, 0, 0, 1, 3), 30), ("Kit", 1, 0, (0, 0, 0, 0, 4), 10)]
    y = XP_SEC_Y
    k = 0
    for sec in range(2):
        mem = [p for p in players if p[1] == sec]
        by["xpSec%d" % sec]["visible"] = 1
        by["xpSec%d" % sec]["pivotAs.y"] = float(y - XP_SEC_Y)
        by["xpTag%d" % sec]["text"] = "MATCH LOST" if sec == 0 else "MATCH WON"
        hw = _est(by["xpHd%d" % sec]["text"], by["xpHd%d" % sec]["pointSize"]) * 1.06
        by["xpTag%d" % sec]["pivotAs.x"] = float(XP_X0 + hw + 40)
        xa = XP_X0 + hw + 40 + _est(by["xpTag%d" % sec]["text"], by["xpTag%d" % sec]["pointSize"]) * 1.06 + 40
        by["xpRule%d" % sec]["pivotAs.x"] = float(xa); by["xpRule%d" % sec]["rectSizeDelta.width"] = float(XP_X0 + XP_COL_R[0] - XP_COL_W - 40 - xa)
        for c in range(5):
            by["xpT%d_%d" % (c, sec)]["text"] = str(sum(p[3][c] for p in mem))
        by["xpTP%d" % sec]["text"] = str(sum(p[4] for p in mem))
        r0 = y + 64
        for r, p in enumerate(mem):
            g = by["xpRow%d" % k]
            g["visible"] = 1; g["pivotAs.y"] = float(r0 + r * XP_PITCH)
            by["xpNm%d" % k]["text"] = p[0]
            by["xpMe%d" % k]["visible"] = p[2]
            by["xpTg%d" % k]["text"] = '<font color="#D9D86A">YOU</font>' if p[2] else ""
            by["xpTg%d" % k]["pivotAs.x"] = float(XP_NAME_X + _est(p[0], by["xpNm%d" % k]["pointSize"]) * 1.06 + 40)
            by["xpAw%d" % k]["text"] = "MOST DOWNS" if r == 0 and sec == 0 else ""
            for c in range(5):
                v = p[3][c]
                by["xpV%d_%d" % (c, k)]["text"] = str(v) if v else _grey("0")
            by["xpPm%d" % k]["visible"] = p[2]; by["xpP%d" % k]["visible"] = 1 - p[2]
            by[("xpPm%d" if p[2] else "xpP%d") % k]["text"] = str(p[4])
            k += 1
        y = r0 + len(mem) * XP_PITCH + 48
    nr.demo_prompts(by, [("menu:select", "CONTINUE", True, "menu:select")] if post else [("menu:back", "BACK", True, "menu:back")])
    return w


def preview(wdir, out_dir, db=None):
    import sys
    import tempfile
    import widget_preview
    main = json.load(open(os.path.join(wdir, "to1", "main-menu.widget.json"), encoding="utf-8"))
    page, spage = build_page(main), build_stats_page(main)
    for pg in (page, spage):
        for it in pg["items"]:
            if it["name"] == "bgBlur":
                it["visible"] = 0                     # (the engine's live blur: the preview draws the blurred launcher art under the page instead)
    os.makedirs(out_dir, exist_ok=True)
    bg = nr.preview_bg(os.path.join(tempfile.gettempdir(), "t2r-nr-bg.png"))
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
        sys.argv = ["x", db, "--days", "16", "--size", "17"]
        clan_demo_seed.main()
    c = sqlite3.connect(db)
    secs = {s: clan_ingame.build(c, tid, "en", s) for s in (1, 2, 3, 4, 6)}
    empty = {k: t.split(chr(10))[0] for k, t in secs.items()}                  # an empty clan: the header lines only

    def out(w, name):
        tmp = os.path.join(tempfile.gettempdir(), "t2r-clan13-prev.widget.json")
        json.dump(w, open(tmp, "w", encoding="utf-8"))
        print(widget_preview.render(tmp, os.path.join(out_dir, name + ".png"), scale=0.5, bg=bg))
    for var, sx in (("", secs), ("-empty", empty)):
        for tab, nm in enumerate(("overview", "survivors", "raids", "journal", "missions")):
            out(demo(page, tab, sx, "none" if var else None), f"clan13-{nm}{var}")
    sw = dict(secs)
    sw[6] = clan_ingame.build(c, tid, "en", 6, 0, 1)
    out(demo(page, 3, sw, None, 0), "clan13-journal-week1")
    for var in list(MS_RUN) + ["attack", "chosen"]:
        out(demo(page, 4, secs, var), f"clan13-missions-{var}")
    out(stats_demo(spage), "clan13x-stats")
    out(stats_demo(spage, post=True), "clan13x-post")
    n1, n2 = len(page["items"]), len(spage["items"])
    print(f"widgets: clan13 {n1}, clan13x {n2} (gui2 limit 1024)")


if __name__ == "__main__":
    import sys
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    preview(sys.argv[1], sys.argv[2], sys.argv[3] if len(sys.argv) > 3 else None)
