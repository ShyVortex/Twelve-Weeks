"""to1/launch-notice the unfinished-state notice shown once per game start. t2r-ext (notice.c) pushes it on the MP menu
while the TWELVE WEEKS entry page still covers the screen, so the notice is already there when that page fades out.

Look: built from the Clan Overview pieces: dimmed backdrop, black box with a
thin grey frame, the TWELVE WEEKS title texture, the text (t2r-ext fills it: English with <font color> emphasis, the loc tables translate
it piece by piece), an I ACKNOWLEDGE box locked for READ_S seconds (countdown in its label + a bar along the box's bottom edge), and two
buttons (CLOSE / CLOSE, DON'T SHOW AGAIN) greyed until the box is ticked; the focused control has the white frame.

Canvas 3840 x 2160 (every number is a 1920 x 1080 layout x 2). Text slots are sized for the longer language (PL)
with the engine's ~1.7 line height (48 pt ~ 82 units a line)."""
import copy
import json
import os

import t2guid
from clan_widgets import Builder, _templates, BRAND_TEX

PAGE = "launch-notice"
W, H = 3840, 2160
BOX_W, PAD = 2120, 112
WHITE = 0xFFECE9E2
BODY = 0xFFB2AEA6
DIM = 0xFF787670
FRAME = 0xFF4E4E4E
FOCUS = 0xFFE6E6E6
FILL = 0xFF090A0C
BTN_FILL = 0xFF060708
LINE = 76                  # units per text line at BODY_PT (engine ~1.7 x pt)
BODY_PT, HEAD_PT, ACK_PT, BTN_PT, HINT_PT = 44, 34, 46, 46, 34
BULLET_IN = 60
LOGO_W = 800
LOGO_H = LOGO_W * 760 // 3000

# (name, kind, lines): kind p = paragraph, h = heading, b = bullet; lines = the slot height in text lines (the longer language)
SLOTS = [("lnP0", "p", 2), ("lnHead", "h", 1), ("lnB0", "b", 2), ("lnB1", "b", 2), ("lnB2", "b", 2), ("lnB3", "b", 1), ("lnP1", "p", 3)]
GAP = {"p": 40, "h": 14, "b": 16}


def layout():
    """-> dict of y offsets (box-relative) + the box height"""
    y = 72
    L = {"logo": y}
    y += LOGO_H + 32
    L["rule"] = y
    y += 50
    for i, (nm, k, n) in enumerate(SLOTS):
        L[nm] = y
        y += (50 if k == "h" else n * LINE)
        if i + 1 < len(SLOTS):
            nk = SLOTS[i + 1][1]
            y += GAP["b"] if k == "b" and nk == "b" else GAP["h"] if k == "h" else GAP["p"]
    y += 56
    L["check"] = y
    y += 60 + 60
    L["btn"] = y
    y += 124 + 96
    L["h"] = y
    return L


def build_page(main):
    t, root0, anim0 = _templates(main)
    b = Builder(t)
    root = copy.deepcopy(root0); root.update(guid=t2guid.guid())
    anim = copy.deepcopy(anim0); anim.update(guid=t2guid.guid(), parent=root["guid"])
    b.items += [root]
    # the dim over the MP menu (its own group: faded with the box when the notice goes)
    dg = b.group("lnDimG", root["guid"], b.bleed())["guid"]
    b.rect("lnDim", dg, b.bleed(), 0xFF000000, 120)
    anim["depth"] = float(len(b.items)) * 0.01
    b.items.append(anim)
    a = anim["guid"]
    L = layout()
    bh = L["h"]
    bx, by = (W - BOX_W) // 2, (H - bh) // 2 - 30
    box = b.group("lnBox", a, b.tl(bx, by, BOX_W, bh))["guid"]
    b.rect("lnPanel", box, b.fill(), FILL, 246)
    b.frame("lnPanelFr", box, b.fill(), 0xFF464646, 255, 2.0)
    b.image("lnLogo", box, b.tl((BOX_W - LOGO_W) / 2, L["logo"], LOGO_W, LOGO_H), BRAND_TEX, WHITE, 255)
    b.line("lnRule", box, PAD, L["rule"], BOX_W - PAD, L["rule"], 0xFF3A3A3A, 255, 2.0)
    inner = BOX_W - 2 * PAD
    for nm, k, n in SLOTS:
        y = L[nm]
        if k == "h":
            b.text(nm, box, b.tl(PAD, y, inner, 50), "WHAT THAT MEANS", HEAD_PT, DIM, valign=0, tracking=5)
            continue
        x = PAD + (BULLET_IN if k == "b" else 0)
        if k == "b":
            b.rect(nm + "Dot", box, b.tl(PAD + 12, y + 28, 14, 14), BODY, 255)
        b.text(nm, box, b.tl(x, y, inner - (x - PAD), n * LINE), "", BODY_PT, BODY, multiline=1, valign=0, tracking=3)
    # I ACKNOWLEDGE: box (frame, tick) + label (the countdown is part of the label while it is locked)
    cy = L["check"]
    cg = b.group("lnCheck", box, b.tl(PAD, cy, inner, 60))["guid"]
    b.rect("lnCheckBg", cg, b.tl(0, 0, 60, 60), BTN_FILL, 255)
    b.frame("lnCheckFr", cg, b.tl(0, 0, 60, 60), FOCUS, 255, 4.0)
    tk = b.add("Polyline", "lnTick", cg, **b.tl(14, 16, 34, 30), **b.col(WHITE), closed=0, lineWidth=7.0,
               pointsUv=[0.0, 0.53, 0.35, 1.0, 1.0, 0.0], **{"color.a": 255})
    tk["visible"] = 0
    b.text("lnAck", cg, b.tl(96, 0, inner - 96, 60), "I ACKNOWLEDGE", ACK_PT, WHITE, tracking=4)
    # hidden twin (the timer flicker fix: a gui2 text whose string changes draws nothing for a frame - the ext writes the hidden copy and swaps, ui_text_db)
    b.text("lnAckB", cg, b.tl(96, 0, inner - 96, 60), "I ACKNOWLEDGE", ACK_PT, WHITE, tracking=4, visible=0)
    # the two buttons (t2r-ext: greyed until ticked; the focused one's lnBtn?Fo frame on)
    bw = (inner - 40) // 2
    for i, label in enumerate(("CLOSE", "CLOSE, DON'T SHOW AGAIN")):
        g = b.group(f"lnBtn{i}", box, b.tl(PAD + i * (bw + 40), L["btn"], bw, 124))["guid"]
        b.rect(f"lnBtn{i}Bg", g, b.fill(), BTN_FILL, 255)
        b.frame(f"lnBtn{i}Fr", g, b.fill(), FRAME, 255, 2.0)
        b.frame(f"lnBtn{i}Fo", g, b.fill(), FOCUS, 255, 4.0, visible=0)
        b.text(f"lnBtn{i}Tx", g, b.fill(), label, BTN_PT, WHITE, align=1, tracking=4)
    # the reading timer: a bar along the box's bottom edge, scaled from full to 0 by t2r-ext (pivot left)
    b.rect("lnTimer", box, b.tl(2, bh - 8, BOX_W - 4, 6), 0xFF96938C, 255)
    # the prompt under the box (the engine's select glyph: pad / keyboard)
    hg = b.group("lnHint", a, b.tl(bx, by + bh + 44, 1200, 60))["guid"]
    b.image("lnHintIcon", hg, b.tl(0, 2, 56, 56), "menu:select", 0xFFFFFFFF)
    b.text("lnHintTx", hg, b.tl(76, 0, 1100, 60), "READ THE NOTICE", HINT_PT, DIM, tracking=4)
    b.text("lnHintTxB", hg, b.tl(76, 0, 1100, 60), "READ THE NOTICE", HINT_PT, DIM, tracking=4, visible=0)   # twin (ui_text_db)
    w = {k: copy.deepcopy(v) for k, v in main.items() if k != "items"}
    w["items"] = b.items
    return w


def add_notice_page(wdir):
    main = json.load(open(os.path.join(wdir, "to1", "main-menu.widget.json"), encoding="utf-8"))
    json.dump(build_page(main), open(os.path.join(wdir, "to1", PAGE + ".widget.json"), "w", encoding="utf-8"), indent=4)
    return 1
