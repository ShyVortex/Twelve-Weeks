"""UI round 2, match flow: the approved looks wired into the real widget builders.

  LOADING   A2   full-bleed map, big header + map name, mission block left, framed tip plate with a cream category tab
  VOTE      B2   loadout-style map list + one big focused map, 2-column roster, clan panel, HUGE "VOTE FOR A MAP - 00:15"
  NAME      C2   hero "you will appear as" plate on top, NAME / CLAN TAG side by side, cream SAVE
  POSTMATCH C2   itemised list left (one rule per row), framed hero PARTS EARNED total right

Every function here RESTYLES the widgets the builders already made (same names, same parent chain, so every path t2r-ext
fills - "anim-group.vote.voteTiles.tile0.tile0Name", "t2r.loading.ldTip" ... - keeps working) and adds a few decoration /
big-picture widgets.  Fonts: ONLY the face the game's own menus use (faceId "Default" = DINPro Medium, the heaviest TLOU2 Latin
face with digits and Polish diacritics; see re/ui-r2-matchflow-impl-1019.md).  No thin weights: sizes go up, dim greys go lighter.

Switches (default ON; "0" = the previous look, for rollback):
  T2R_UI_R2=0                    all four screens old
  T2R_UI_R2_LOAD / _VOTE / _NAME / _POST = 0 | 1      one screen
  T2R_UI_R2_TITLE_STYLE=<style>  optional: a stock text style (e.g. menu-header) on the page titles, for an in-game weight A/B
"""
import os

W, H = 3840, 2160
WARM = 0xFFD9D2BF            # cream: frames / hero text
BRIGHT = 0xFFEFEBDD          # heavy white-ish text
DIM2 = 0xFFB9B4A6            # lighter than the old PM_DIM (8E8A84): small text must not look thin
INK = 0xFF0C0D0E
TEAL = 0xFF5CB6D0
BAR = 0xFFFFFFFF
MARGIN_L, MARGIN_R = 240, 3600
RULE_Y = 282
TITLE_PT = 108

_SW = {"load": "T2R_UI_R2_LOAD", "vote": "T2R_UI_R2_VOTE", "name": "T2R_UI_R2_NAME", "post": "T2R_UI_R2_POST"}


def on(screen):
    """True = the round-2 look.  OFF by default (the previous map loading screen and vote were better - the
    2013-faithful match flow is the house style); T2R_UI_R2_<SCREEN>=1 turns one back on. The global T2R_UI_R2 only switches it OFF (it still
    defaults ON for the pause page)."""
    v = os.environ.get(_SW[screen])
    if v is not None and v.strip() != "":
        return v.strip().lower() not in ("0", "off", "no", "old", "false")
    return False


# ------------------------------------------------------------------ helpers
def by_name(b):
    return {i["name"]: i for i in b.items}


def put(i, x, y, w, h):
    """top-left rect (x, y, w, h) in the parent's space; keeps a centre-pivot item (b.ctr) centred on the same rect."""
    if i.get("anchorMaxN.x", 0.0) != i.get("anchorMinN.x", 0.0) or i.get("anchorMaxN.y", 0.0) != i.get("anchorMinN.y", 0.0):
        # a stretch-anchored item (b.fill()): becomes a plain top-left rect
        i.update({"anchorMinN.x": 0.0, "anchorMinN.y": 0.0, "anchorMaxN.x": 0.0, "anchorMaxN.y": 0.0, "pivotN.x": 0.0, "pivotN.y": 0.0})
    cx = i.get("pivotN.x", 0.0) == 0.5
    i["pivotAs.x"] = float(x + (w / 2 if cx else 0))
    i["pivotAs.y"] = float(y + (h / 2 if cx else 0))
    i["rectSizeDelta.width"] = float(w)
    i["rectSizeDelta.height"] = float(h)
    return i


def txt(i, pt=None, col=None, tr=None, align=None, valign=None):
    if pt is not None:
        i["pointSize"] = pt
    if col is not None:
        i["tint.start"] = i["tint.end"] = col
    if tr is not None:
        i["tracking.x"] = float(tr)
    if align is not None:
        i["alignH"] = align
    if valign is not None:
        i["alignV"] = valign
    return i


def seg(i, x0, y0, x1, y1, col=None, alpha=None, width=None):
    """re-aim a Polyline at (x0,y0)-(x1,y1)."""
    x, y = min(x0, x1), min(y0, y1)
    w, h = max(abs(x1 - x0), 1.0), max(abs(y1 - y0), 1.0)
    put(i, x, y, w, h)
    i["pointsUv"] = [(x0 - x) / w, (y0 - y) / h, (x1 - x) / w, (y1 - y) / h]
    if col is not None:
        i["tint.start"] = i["tint.end"] = col
    if alpha is not None:
        i["color.a"] = alpha
    if width is not None:
        i["lineWidth"] = float(width)
    return i


def under(item, ref):
    """draw order: just below `ref` (same parent)."""
    item["depth"] = ref["depth"] - 0.004
    return item


def title_style(i):
    st = os.environ.get("T2R_UI_R2_TITLE_STYLE", "").strip()
    if st:
        i["style"] = st
    return i


def glyph(b, parent, x, y, h=130, prefix="r2"):
    """the 2013 title mark (hand-cut tally / dagger) in front of a title; three short lines."""
    s = h
    cx, cy = x, y
    b.line(prefix + "G1", parent, cx, cy - s * .5, cx + s * .06, cy + s * .5, TEAL, 215, 9.0)
    b.line(prefix + "G2", parent, cx - s * .22, cy - s * .12, cx + s * .26, cy - s * .16, TEAL, 215, 8.0)
    b.line(prefix + "G3", parent, cx - s * .06, cy - s * .30, cx + s * .12, cy - s * .30, TEAL, 110, 4.0)


def header(b, parent, title, rule=None, prefix="r2h", gx=290, gy=170, tx=370, ty=100):
    """glyph + big title + the full-width rule (rule = the page's existing line, re-aimed; else a new one)."""
    glyph(b, parent, gx, gy, 130, prefix)
    txt(put(title, tx, ty, 2800, 150), TITLE_PT, WARM, 6, 0, 1)
    title_style(title)
    if rule is None:
        b.line(prefix + "Rule", parent, MARGIN_L, RULE_Y, MARGIN_R, RULE_Y, WARM, 130, 3.0)
    else:
        seg(rule, MARGIN_L, RULE_Y, MARGIN_R, RULE_Y, WARM, 130, 3.0)


def prompt(icon, label, hint, x, y):
    """footer prompt: the engine's WHITE button glyph (menu:select, tint white, as every page of the mod) + its label."""
    put(icon, x, y - 4, 64, 64)
    icon["tint.start"] = icon["tint.end"] = 0xFFFFFFFF
    txt(put(label, x + 90, y - 10, 700, 76), 52, BRIGHT, 5, 0, 1)
    if hint is not None:
        txt(hint, 44, DIM2, 4)


# ------------------------------------------------------------------ LOADING  (A2)
def loading(b, g):
    """b = the loading Builder (build_loading), g = group "t2r"."""
    n = by_name(b)
    ld = n["loading"]["guid"]
    # full-bleed map, readable but present (was ~18 % visible); dark plates carry the text
    n["ldDark"]["color.a"] = 60
    n["mapBg"]["color.a"] = 255
    n["mapShade"]["color.a"] = 105
    for k in ("ldPic", "ldPicOld", "ldPicShade", "ldPicBack", "ldPicFrame"):          # the framed picture goes (the map is the picture now)
        n[k]["visible"] = 0
    top = b.rect("r2LdTop", ld, b.tl(0, 0, W, 330), INK, 150)
    under(top, n["ldTitle"])
    pan = under(b.rect("r2LdPanel", ld, b.tl(MARGIN_L - 30, 980, 1150, 880), INK, 150), n["ldMissionHead"])
    header(b, ld, n["ldTitle"], n["ldLine"], "r2l")
    txt(put(n["ldMap"], 370, 335, 2600, 150), 116, BRIGHT, 6, 0, 1)
    title_style(n["ldMap"])
    txt(put(n["ldMode"], 372, 490, 2000, 80), 58, WARM, 7, 0, 1)
    # mission block (left)
    txt(put(n["ldMissionHead"], MARGIN_L + 20, 1010, 1000, 100), 64, BRIGHT, 6, 0, 1)
    seg(n["ldMisLine1"], MARGIN_L + 20, 1120, 1250, 1120, WARM, 140, 2.0)
    txt(put(n["ldMis1"], MARGIN_L + 20, 1140, 1050, 90), 56, BRIGHT, 3)
    txt(put(n["ldMis2"], MARGIN_L + 20, 1230, 1050, 80), 42, DIM2, 2)
    seg(n["ldMisLine2"], MARGIN_L + 20, 1335, 1250, 1335, WARM, 140, 2.0)
    for k in range(3):
        y = 1380 + k * 92
        txt(put(n[f"ldTier{k}"], MARGIN_L + 20, y, 640, 84), 48, BRIGHT, 3)
        put(n[f"ldTier{k}Icon"], 900, y + 8, 30, 66)
        txt(put(n[f"ldTier{k}Pct"], 1000, y, 250, 84), 48, BRIGHT, 3, 2)
    seg(n["ldDivider"], 1330, 640, 1330, 1850, WARM, 120, 2.0)
    # tip plate (right) with the cream category tab sitting on its top edge
    PX, PY, PW, PH = 1700, 1400, 1900, 250
    plate = under(b.rect("r2LdPlate", ld, b.tl(PX, PY, PW, PH), INK, 205), n["ldTip"])
    under(b.rect("r2LdPlateBar", ld, b.tl(PX, PY, 10, PH), WARM, 240), n["ldTip"])
    under(b.frame("r2LdPlateFrame", ld, b.tl(PX, PY, PW, PH), WARM, 90, 2.0), n["ldTip"])
    tab = under(b.rect("r2LdTab", ld, b.tl(PX + 50, PY - 76, 340, 76), WARM, 250), n["ldTipCat"])
    for nm in ("ldTipCat", "ldTipCatB"):
        txt(put(n[nm], PX + 50, PY - 76, 340, 76), 46, INK, 6, 1, 1)
    for nm in ("ldTip", "ldTipB"):
        txt(put(n[nm], PX + 60, PY + 20, PW - 120, PH - 40), 58, BRIGHT, 2, 0, 1)
        n[nm]["multiline"] = 1
    for nm in ("ldSpin", "ldSpinB"):
        txt(put(n[nm], 2200, 1888, 1400, 80), 54, WARM, 7, 2, 1)
    b.line("r2LdBottom", ld, MARGIN_L, 1985, MARGIN_R, 1985, WARM, 70, 2.0)


# ------------------------------------------------------------------ VOTE  (B2)
ROW_X, ROW_Y0, ROW_W, ROW_H, ROW_P = 240, 520, 1100, 170, 190
BIG = (1420, 520, 1260, 709)
ROS_Y0, ROS_P, ROS_W = 1380, 100, 1170
PANEL_X = 2890


def vote(b):
    n = by_name(b)
    v = n["vote"]["guid"]
    tiles = n["voteTiles"]["guid"]
    rows = n["voteRoster"]["guid"]
    header(b, v, n["voteTitle"], None, "r2v")
    txt(put(n["voteSub"], MARGIN_L, 300, 1100, 140), 64, BRIGHT, 6, 0, 1)
    # the countdown: HUGE (was 46 pt), right aligned on the content edge, heavy face, red digits come from the ext's markup
    for nm in ("voteTimer", "voteTimerB"):
        txt(put(n[nm], 1000, 296, 2600, 170), 104, WARM, 4, 2, 1)
    txt(put(n["voteWait"], MARGIN_L, 700, 3000, 140), 70, BRIGHT, 4, 0, 1)
    # map list (loadout-style rows): thumbnail | name | one check per vote
    for k in range(3):
        g = n[f"tile{k}"]
        put(g, ROW_X, ROW_Y0 + k * ROW_P, ROW_W, ROW_H)
        n[f"tile{k}Back"]["tint.start"] = n[f"tile{k}Back"]["tint.end"] = 0xFF1B1C1D
        n[f"tile{k}Back"]["color.a"] = 255
        put(n[f"tile{k}Img"], 0, 0, 302, ROW_H)
        n[f"tile{k}Shade"]["color.a"] = 120
        n[f"tile{k}Frame"]["tint.start"] = n[f"tile{k}Frame"]["tint.end"] = WARM
        n[f"tile{k}Frame"]["lineWidth"] = 7.0
        txt(put(n[f"tile{k}Name"], 340, 0, 640, ROW_H), 62, BRIGHT, 5, 0, 1)
        for j in range(8):
            c = n[f"tile{k}Ck{j}"]
            put(c, ROW_W - 40 - (j + 1) * 50, 66, 38, 40)
            c["lineWidth"] = 7.0
            c["tint.start"] = c["tint.end"] = WARM
    # the big picture of the focused map (t2r-ext mf_vote_fill sets voteBigImg's path; nothing breaks if it never does)
    bx, by_, bw, bh = BIG
    b.rect("voteBigBack", tiles, b.tl(bx, by_, bw, bh), 0xFF050606, 255)
    b.image("voteBigImg", tiles, b.tl(bx + 6, by_ + 6, bw - 12, bh - 12), "streaming/menus/to1/map-pvp-school.png", 0xFFFFFFFF, 255)
    b.frame("voteBigFrame", tiles, b.tl(bx, by_, bw, bh), WARM, 255, 7.0)
    # roster: two columns, teal accent on every row
    b.line("r2vRosRule", v, MARGIN_L, ROS_Y0 - 50, BIG[0] + BIG[2], ROS_Y0 - 50, WARM, 90, 2.0)
    for r in range(8):
        g = n[f"ros{r}"]
        put(g, MARGIN_L + (r % 2) * (ROS_W + 80), ROS_Y0 + (r // 2) * ROS_P, ROS_W, 90)
        n[f"ros{r}Bar"]["color.a"] = 34
        acc = b.rect(f"ros{r}Acc", g["guid"], b.tl(0, 0, 9, 90), TEAL, 255)
        txt(put(n[f"ros{r}Name"], 44, 0, 900, 90), 52, BRIGHT, 4, 0, 1)
        c = n[f"ros{r}Ck"]
        put(c, ROS_W - 90, 24, 44, 42)
        c["lineWidth"] = 7.0
        c["tint.start"] = c["tint.end"] = WARM
    # clan panel
    seg(n["voteDivider"], 2860, 450, 2860, 1560, WARM, 120, 2.0)
    txt(put(n["voteWeek"], PANEL_X, 460, 940, 130), 62, BRIGHT, 4, 0, 1)
    seg(n["voteWeekLine"], PANEL_X, 610, MARGIN_R, 610, WARM, 130, 2.0)
    put(n["voteSurvIcon"], PANEL_X + 10, 690, 46, 98)
    txt(put(n["voteSurv"], PANEL_X + 90, 688, 700, 100), 54, BRIGHT, 4, 0, 1)
    for k, nm in enumerate(("voteHealthy", "voteHungry", "voteSick")):
        txt(put(n[nm], PANEL_X, 840 + k * 100, 700, 90), 56, None, 4, 0, 1)
    put(n["voteSupplyIcon"], PANEL_X + 8, 1166, 62, 62)
    txt(put(n["voteNeeded"], PANEL_X + 90, 1152, 760, 90), 44, BRIGHT, 3, 0, 1)
    seg(n["voteNeedLine"], PANEL_X, 1290, MARGIN_R, 1290, WARM, 130, 2.0)
    prompt(n["voteSelIcon"], n["voteSelText"], n["voteHint"], MARGIN_L, 1888)
    put(n["voteHint"], 760, 1884, 1400, 76)


# ------------------------------------------------------------------ NAME  (C2)
def name(b):
    n = by_name(b)
    e = n["entry"]["guid"]
    header(b, e, n["title"], n["titleLine"], "r2n")
    txt(put(n["intro"], 240, 305, 3360, 110), 52, DIM2, 3, 1, 1)
    n["intro"]["text"] = "Shown to everyone in the lobby and on the kill feed."
    # hero plate: "YOU WILL APPEAR AS" + the live preview, big
    txt(put(n["prevLabel"], 780, 470, 2280, 80), 50, WARM, 8, 1, 1)
    plate = b.rect("r2nPlate", e, b.tl(780, 580, 2280, 340), INK, 215)
    under(plate, n["prevVal"])
    under(b.rect("r2nPlateBar", e, b.tl(780, 580, 2280, 12), WARM, 250), n["prevVal"])
    under(b.frame("r2nPlateFrame", e, b.tl(780, 580, 2280, 340), WARM, 100, 2.0), n["prevVal"])
    txt(put(n["prevLine"], 780, 1000, 2280, 2), None)
    n["prevLine"]["visible"] = 0
    txt(put(n["prevVal"], 800, 600, 2240, 300), 150, BRIGHT, 6, 1, 1)
    # fields side by side
    txt(put(n["nameLabel"], 780, 1090, 1000, 80), 50, WARM, 8, 0, 1)
    put(n["nameBack"], 780, 1180, 1380, 140)
    put(n["nameFocus"], 780, 1180, 1380, 140)
    n["nameFocus"]["tint.start"] = n["nameFocus"]["tint.end"] = WARM
    n["nameBack"]["color.a"] = 40
    txt(put(n["nameVal"], 820, 1180, 1100, 140), 70, BRIGHT, 3, 0, 1)
    txt(put(n["nameCount"], 1940, 1180, 190, 140), 44, DIM2, 2, 2, 1)
    n["tagLabel"]["text"] = "CLAN TAG"
    txt(put(n["tagLabel"], 2280, 1090, 780, 80), 50, WARM, 8, 0, 1)
    put(n["tagBack"], 2280, 1180, 780, 140)
    put(n["tagFocus"], 2280, 1180, 780, 140)
    n["tagFocus"]["tint.start"] = n["tagFocus"]["tint.end"] = WARM
    n["tagBack"]["color.a"] = 40
    txt(put(n["tagVal"], 2320, 1180, 560, 140), 70, BRIGHT, 3, 0, 1)
    txt(put(n["tagCount"], 2880, 1180, 160, 140), 44, DIM2, 2, 2, 1)
    hint = b.text("tagHint", e, b.tl(2280, 1330, 780, 60), "(UP TO 5 LETTERS OR DIGITS)", 36, DIM2, tracking=3)
    txt(put(n["status"], 780, 1390, 2280, 90), 48, None, 2, 0, 1)
    # buttons: cream SAVE, ghost CANCEL (the *Back rects are the mouse hit areas)
    put(n["saveBack"], 780, 1520, 1116, 132)
    n["saveBack"]["tint.start"] = n["saveBack"]["tint.end"] = WARM
    n["saveBack"]["color.a"] = 255
    put(n["saveHov"], 780, 1520, 1116, 132)
    n["saveHov"]["tint.start"] = n["saveHov"]["tint.end"] = 0xFFFFFFFF
    put(n["cancelBack"], 1944, 1520, 1116, 132)
    n["cancelBack"]["color.a"] = 30
    put(n["cancelHov"], 1944, 1520, 1116, 132)
    n["cancelHov"]["tint.start"] = n["cancelHov"]["tint.end"] = WARM
    txt(put(n["saveBtn"], 780, 1520, 1116, 132), 62, INK, 10, 1, 1)
    txt(put(n["cancelBtn"], 1944, 1520, 1116, 132), 62, BRIGHT, 10, 1, 1)
    prompt(n["selIcon"], n["selText"], n["hint"], MARGIN_L, 1888)
    txt(put(n["hint"], 760, 1884, 2800, 76), 40, DIM2, 4, 0, 1)


# ------------------------------------------------------------------ POST-MATCH  (C2)
ROW_LX, ROW_RX = 360, 2090              # label left edge / number right edge
ROW_Y, ROW_PITCH = 540, 130             # top of row 0, pitch
HERO = (2640, 540, 940, 900)            # x, y, w, h
CONV_Y = 1400                           # CONVERTED block centre line (left, under the 5 rows)


def postmatch(b):
    n = by_name(b)
    a = n["anim-group"]["guid"]
    earned = n["earned"]["guid"]
    convert = n["convert"]["guid"]
    # header: the title is big, the faction rides on the right (the hero plate is only on stage 0)
    txt(put(n["pmTitle"], 420, 110, 2400, 160), TITLE_PT, WARM, 6, 0, 1)
    title_style(n["pmTitle"])
    put(n["pmEmblemW"], 270, 130, 74, 154)
    put(n["pmEmblemS"], 270, 130, 74, 154)
    txt(put(n["pmFaction"], 2400, 140, 1200, 90), 40, DIM2, 5, 2, 1)
    seg(n["pmTitleLine"], 264, RULE_Y, 3576, RULE_Y, WARM, 130, 3.0)
    # itemised list: label | xN | parts | cog, a rule under every row
    for k in range(5):
        cy = ROW_Y + k * ROW_PITCH + ROW_PITCH / 2
        g = n[f"pmRow{k}"]["guid"]
        txt(put(n[f"pmRow{k}Label"], ROW_LX, cy - 45, 1100, 90), 58, BRIGHT, 6, 0, 1)
        txt(put(n[f"pmRow{k}Count"], 1380, cy - 40, 260, 80), 46, DIM2, 2, 1, 1)
        txt(put(n[f"pmRow{k}Num"], ROW_RX - 500, cy - 45, 500, 90), 58, BRIGHT, 2, 2, 1)
        put(n[f"pmRow{k}Icon"], ROW_RX + 70, cy - 32, 64, 64)
        n[f"pmRow{k}Icon"]["tint.start"] = n[f"pmRow{k}Icon"]["tint.end"] = DIM2
        b.line(f"pmRow{k}Rule", g, ROW_LX - 20, cy + ROW_PITCH / 2, ROW_RX + 160, cy + ROW_PITCH / 2, WARM, 70, 2.0)
    # hero total (everything of it fades in with the total: ext TOT[] lists the names)
    hx, hy, hw, hh = HERO
    ref = n["pmEarnLine"]
    for item in (b.rect("pmHeroBack", earned, b.tl(hx, hy, hw, hh), INK, 215),
                 b.rect("pmHeroBar", earned, b.tl(hx, hy, hw, 14), WARM, 250),
                 b.frame("pmHeroFrame", earned, b.tl(hx, hy, hw, hh), WARM, 100, 2.0)):
        under(item, ref)
    txt(put(n["pmPartsLabel"], hx, hy + 70, hw, 110), 64, WARM, 8, 1, 1)
    put(n["pmPartsGear"], hx + hw / 2 - 150, hy + 330, 300, 300)
    n["pmPartsGear"]["tint.start"] = n["pmPartsGear"]["tint.end"] = 0xFF4A4A46; n["pmPartsGear"]["visible"] = 1
    for nm in ("pmPartsNum", "pmPartsNumB"):
        txt(put(n[nm], hx + 20, hy + 290, hw - 40, 380), 190, BRIGHT, 4, 1, 1)
    n["pmPartsIcon"]["visible"] = 0                      # (the cog sits behind the number now)
    seg(ref, hx + 80, hy + 760, hx + hw - 80, hy + 760, WARM, 110, 2.0)
    # CONVERTED block under the list (the old centre column is the hero's place now)
    put(n["pmConvGear"], ROW_LX - 10, CONV_Y - 40, 80, 80); n["pmConvGear"]["visible"] = 1
    txt(put(n["pmConvLabel"], ROW_LX + 90, CONV_Y - 70, 1100, 140), 70, BRIGHT, 6, 0, 1)
    for nm in ("pmConvNum", "pmConvNumB"):
        txt(put(n[nm], ROW_RX - 700, CONV_Y - 70, 700, 140), 76, None, 2, 2, 1)
    put(n["pmConvIcon"], ROW_RX + 36, CONV_Y - 50, 100, 100)
    txt(put(n["pmConvRate"], ROW_LX + 90, CONV_Y + 80, 1700, 76), 44, DIM2, 4, 0, 1)
    for nm in ("pmWait", "pmLeft"):
        txt(put(n[nm], ROW_LX, CONV_Y + 190, ROW_RX - ROW_LX + 160, 90), 50, None, 4, 0, 1)
    # result stage keeps its structure, sized up
    for nm, pt in (("pmDailyLabel", 62), ("pmGainLabel", 62), ("pmCount", 56), ("pmHealthy", 56), ("pmHungry", 56), ("pmSick", 56),
                   ("pmGathered", 46), ("pmNeeded", 46), ("pmOut0", 50), ("pmOut1", 50), ("pmOut2", 50), ("pmOut3", 50), ("pmOut4", 50),
                   ("pmMis0", 50), ("pmMis1", 46), ("pmMis2", 46)):
        n[nm]["pointSize"] = pt
        if n[nm]["tint.start"] == 0xFF8E8A84:
            n[nm]["tint.start"] = n[nm]["tint.end"] = DIM2
    for nm in ("pmDailyNum", "pmDailyNumB"):
        n[nm]["pointSize"] = 96
    # prompts (the WHITE engine glyph, as before)
    for ic, tx in (("pmNextIcon", "pmNextText"), ("pmContIcon", "pmContText")):
        i, t = n[ic], n[tx]
        i["tint.start"] = i["tint.end"] = 0xFFFFFFFF
        t["pointSize"] = 52
        t["tint.start"] = t["tint.end"] = BRIGHT
