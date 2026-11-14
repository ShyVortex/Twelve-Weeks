"""The clan end screens (re/win-screen-1112/PLAN.md) on to1/clan-side: group "end", driven by tools/ext/clanend.c.

Won (survived 12 weeks) and lost (the clan is gone) share one layout:
  key art: five parallax layers (ceL4 far .. ceL0 near, re/clan-end/tex/ce-<scene>-L<i>, 2560 x 1080 px over 5120 x 2160 units with
  the frame on the left; the ext picks the scene's images and moves / scales each layer by its depth), scratches, vignette, grain, a
  black fade; the title (DAY n + YOUR CLAN SURVIVED / IS GONE), the roll call (7 faces: c13p portraits, frames, names, a chalk strike
  per dead face), CONTINUE; then the dark rank page: win = the old rank (+ its rubbed-out ghost) and the new rank chalked in through 6
  stroke slots (line strokes: up to CE_KR reveal cells placed by the ext; dots: the whole stroke image fading in), the nib, 16 dust motes, a settle glow, RANK n + YOUR nTH
  CLAN TO SURVIVE; lost = the 12-week tally (12 stroke slots + guides + week numbers, the red break, a glow), WEEK n OF 12 + THE CLAN FELL
  n DAYS SHORT; then 4 stats and START A NEW CLAN / READ THE JOURNAL.
Chalk reveal: gui2 Image masks render nothing, so each straight stroke is cut into disjoint pieces in square cells
(re/win-screen-1112/src/make_segments.py, re/clan-end/seg.json); the ext fades piece j in as the stroke's progress passes j / K.
Widget space 3840 x 2160, y down."""

import json
import os

TEX = "streaming/t2r/clanend/"
SEG = json.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "re", "clan-end", "seg.json")))
W, H = 3840, 2160
CREAM = 0xFFE8E0CC
DIM = 0xFFA8A292
RED = 0xFFE04848
DARK = 0xFF0B0C0D
GW, GH = 878, 678            # tools/ext/clanend_data.h CE_GW / CE_GH (the rank glyph canvas)
GX, GY = 1920, 940           # rank glyph centre
NSLOT = 6                    # stroke slots (rank 9 / 10: 4 bars + 1-2 dots)
NDUST = 16
NROLL = 7
ROLL_X0, ROLL_STEP, ROLL_Y, PS = 1920 - 3 * 276, 276, 1440, 224
TALLY_X0, TALLY_STEP, TALLY_Y = 1120, 1600 / 11, 940
STATS_X0, STATS_X1, STATS_Y = 520, 3320, 1620


def tex(n):
    return TEX + n + ".png"


def add_end(b, parent):
    """Builder b (clan_widgets.Builder) adds group "end" under parent (the page's anim group). Returns the group item."""
    e = b.group("end", parent, b.tl(0, 0, W, H), visible=0)
    g = e["guid"]
    b.rect("ceBlack", g, b.bleed(), 0xFF000000, 255)
    art = b.group("ceArt", g, b.tl(0, 0, W, H))["guid"]
    for i in (4, 3, 2, 1, 0):                         # far first (drawn under)
        b.image("ceL%d" % i, art, {"anchorMinN.x": 0.0, "anchorMinN.y": 0.0, "anchorMaxN.x": 0.0, "anchorMaxN.y": 0.0,
                                    "pivotN.x": 0.375, "pivotN.y": 0.5, "pivotAs.x": 1920.0, "pivotAs.y": 1080.0,
                                    "rectSizeDelta.width": 5120.0, "rectSizeDelta.height": 2160.0}, tex("ce-wlf-L%d" % i))
    b.image("ceScratch", g, b.tl(0, 0, W, H), tex("ce-scratch"))
    b.image("ceVig", g, b.tl(0, 0, W, H), tex("ce-vig"))
    b.image("ceGrain", g, b.tl(-512, -512, W + 1024, H + 1024), tex("ce-grain"), 0xFFFFFFFF, 150, scaleMode="Tile")
    b.rect("ceFade", g, b.bleed(), 0xFF000000, 255)

    ui = b.group("ceUI", g, b.tl(0, 0, W, H))["guid"]
    b.text("ceDay", ui, b.tl(1320, 150, 1200, 80), "DAY 84", 36, CREAM, align=1, tracking=10)
    b.line("ceDayLine", ui, 1620, 238, 2220, 238, CREAM, 90, 2.0)
    b.text("ceTitle", ui, b.tl(320, 290, 3200, 230), "YOUR CLAN SURVIVED", 150, CREAM, align=1, face="Alternate", tracking=6)
    b.text("ceRollHdr", ui, b.tl(1120, 1330, 1600, 70), "THEY MADE IT", 32, CREAM, align=1, tracking=8)
    for i in range(NROLL):
        x = ROLL_X0 + i * ROLL_STEP - PS / 2
        pg = b.group("ceP%d" % i, ui, b.tl(x, ROLL_Y, PS, PS + 110))["guid"]
        b.rect("ceP%dBg" % i, pg, b.tl(0, 0, PS, PS), 0xFF16181A, 200)
        b.image("ceP%dImg" % i, pg, b.tl(0, 0, PS, PS), "streaming/t2r/icons/c13p-0_neutral.png")
        b.frame("ceP%dFrame" % i, pg, b.tl(0, 0, PS, PS), CREAM, 140, 3.0)
        b.text("ceP%dName" % i, pg, b.tl(-40, PS + 22, PS + 80, 56), "", 24, CREAM, align=1, tracking=2)
        sg = b.group("ceP%dStr" % i, pg, b.tl(0, 0, PS, PS))["guid"]
        b.image("ceP%dStrImg" % i, sg, b.tl(0, 0, PS, PS), tex("ce-strike%d" % (i + 1)), visible=0)
        for j, (cx, cy) in enumerate(SEG["strike"][i]):
            b.image("ceP%dStrC%d" % (i, j), sg, b.ctr(PS / 2 + cx, PS / 2 + cy, SEG["cp"], SEG["cp"]), tex("ce-strike%d-c%d" % (i + 1, j)), 0xFFFFFFFF, 0)
    b.text("ceRollSub", ui, b.tl(720, 1830, 2400, 60), "", 26, DIM, align=1, tracking=4)
    cg = b.group("ceCont", ui, b.tl(0, 0, W, H))["guid"]
    b.image("ceContIcon", cg, b.tl(3200, 1898, 56, 56), "menu:select", 0xFFFFFFFF)
    b.text("ceContText", cg, b.tl(3280, 1890, 420, 70), "CONTINUE", 46, 0xFFE6E6E6, tracking=4)

    pg = b.group("cePage", g, b.tl(0, 0, W, H))["guid"]
    b.rect("ceDark", pg, b.bleed(), DARK, 244)
    rk = b.group("ceRank", pg, b.tl(0, 0, W, H))["guid"]
    b.image("ceGlow", rk, b.ctr(GX, GY, 1400, 1400), tex("ce-glow"), CREAM, 0)
    b.image("ceOldG", rk, b.ctr(GX, GY, GW, GH), tex("ce-r1-g"))
    b.image("ceOld", rk, b.ctr(GX, GY, GW, GH), tex("ce-r1"))
    b.text("ceOldT", rk, b.tl(1320, GY + 330, 1200, 70), "", 32, CREAM, align=1, tracking=6)
    for k in range(NSLOT):
        sg = b.group("ceS%d" % k, rk, b.tl(0, 0, W, H))["guid"]
        b.image("ceS%dImg" % k, sg, b.ctr(GX, GY, GW, GH), tex("ce-r1-s1"), 0xFFFFFFFF, 0)
        for j in range(SEG["kr"]):
            b.image("ceS%dC%d" % (k, j), sg, b.ctr(GX, GY, SEG["cr"], SEG["cr"]), tex("ce-r1-s1-c0"), 0xFFFFFFFF, 0)
    for j in range(NDUST):
        b.image("ceDust%d" % j, rk, b.ctr(GX, GY, 6, 6), tex("ce-dust"), CREAM, 0)
    b.image("ceNib", rk, b.ctr(GX, GY, 44, 44), tex("ce-nib"), 0xFFFFFFFF, 0)
    b.text("ceRankT", rk, b.tl(1120, GY + 330, 1600, 150), "", 100, CREAM, align=1, face="Alternate", tracking=8)
    b.text("ceRankS", rk, b.tl(920, GY + 475, 2000, 70), "", 30, 0xFFE2DCCE, align=1, tracking=5)

    ty = b.group("ceTally", pg, b.tl(0, 0, W, H), visible=0)["guid"]
    b.image("ceTGlow", ty, b.ctr(GX, GY, 700, 700), tex("ce-glow"), 0xFFE07848, 0)
    for i in range(12):
        x = TALLY_X0 + i * TALLY_STEP
        b.image("ceTg%d" % i, ty, b.ctr(x, TALLY_Y, 48, 300), tex("ce-tally%d" % (i + 1)), DIM, 55)
        b.text("ceTn%d" % i, ty, b.tl(x - 60, TALLY_Y + 190, 120, 50), str(i + 1), 24, DIM, align=1, tracking=1)
        sg = b.group("ceT%d" % i, ty, b.tl(0, 0, W, H))["guid"]
        b.image("ceT%dImg" % i, sg, b.ctr(x, TALLY_Y, 48, 300), tex("ce-tally%d" % (i + 1)), visible=0)
        for j, (cx, cy) in enumerate(SEG["tally"][i]):
            b.image("ceT%dC%d" % (i, j), sg, b.ctr(x + cx, TALLY_Y + cy, SEG["ct"], SEG["ct"]), tex("ce-tally%d-c%d" % (i + 1, j)), 0xFFFFFFFF, 0)
    sl = b.group("ceSl", ty, b.tl(0, 0, W, H))["guid"]
    b.image("ceSlImg", sl, b.ctr(GX, GY, 280, 160), tex("ce-slash"), visible=0)
    for j, (cx, cy) in enumerate(SEG["slash"]):
        b.image("ceSlC%d" % j, sl, b.ctr(GX + cx, GY + cy, SEG["csl"], SEG["csl"]), tex("ce-slash-c%d" % j), 0xFFFFFFFF, 0)
    b.text("ceWk", ty, b.tl(1120, TALLY_Y - 420, 1600, 150), "", 100, CREAM, align=1, face="Alternate", tracking=8)
    b.text("ceWkS", ty, b.tl(920, TALLY_Y + 290, 2000, 70), "", 30, 0xFFE2DCCE, align=1, tracking=5)

    st = b.group("ceStats", pg, b.tl(0, 0, W, H))["guid"]
    step = (STATS_X1 - STATS_X0) / 4
    for i in range(4):
        cx = STATS_X0 + step * (i + 0.5)
        b.text("ceSV%d" % i, st, b.tl(cx - 330, STATS_Y, 660, 130), "", 76, CREAM, align=1, face="Alternate", tracking=2)
        b.text("ceSL%d" % i, st, b.tl(cx - 330, STATS_Y + 140, 660, 60), "", 26, 0xFFD2CCBE, align=1, tracking=3)
        if i:
            b.line("ceSD%d" % i, st, STATS_X0 + step * i, STATS_Y + 10, STATS_X0 + step * i, STATS_Y + 190, CREAM, 70, 2.0)
    bt = b.group("ceBtns", pg, b.tl(0, 0, W, H))["guid"]
    b.image("ceBtnAIcon", bt, b.tl(2930, 1898, 56, 56), "menu:select", 0xFFFFFFFF)
    b.text("ceBtnAText", bt, b.tl(3010, 1890, 700, 70), "START A NEW CLAN", 46, 0xFFE6E6E6, tracking=4)
    b.image("ceBtnBIcon", bt, b.tl(240, 1898, 56, 56), "menu:action", 0xFFFFFFFF)
    b.text("ceBtnBText", bt, b.tl(320, 1890, 700, 70), "READ THE JOURNAL", 46, 0xFFE6E6E6, tracking=4)
    return e
