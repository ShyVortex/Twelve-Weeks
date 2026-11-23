"""The in-game chat (proposal + mockups re/chat-proposal-1123), driven by t2r-ext chat.c:

  to1/currency-hud: group "chatHud" (full page) > row "chatBox" (hidden; chat.c shows it and drives its alpha) BETWEEN the lives counter and the parts
        counter, left: a faint box, the CHAT label, the tabs MATCH / TEAM / PARTY (the picked one in its colour and underlined), 5 lines, the typing line
        (its underline in the tab's colour, the tab name at its right) and the key hint under the box; idle: a fainter, smaller box behind the newest 3
        lines and the tab name. chat.c finds the leaves with hud_widget("chatHud", "chatBox", leaf) - they are direct children of chatBox.
  to1/pause-menu: group "pzChat" in CLAN NEWS's place (pause_restyle_widgets PNR_NEWS; hidden until chat.c shows it): the CHAT section row (its rule
        ends where the tabs start), the tabs, a box with 4 lines and the typing line. Group "pzPBadge": the red unread count chat.c puts at the
        P FRIENDS prompt's top right.
 to1/main-menu + to1/find-match-menu (MP menu layout mockup): group "mnChat" under the LOBBY box (x 2500..3682, y 1554..1956, 24 below
        the box, 24 above the footer rule): blur + black like the lobby box, CHAT + the PARTY tab, 4 lines, the typing line. onlineGroup moves up to y 104
        (the FRIENDS strip now sits at y 266, friends13_widgets BTN_Y). chat.c ch_menu_tick drives it.
Widget space 3840 x 2160. Every text is written by the ext (the templates carry English placeholders for the preview only).
python chat_widgets.py <extracted widget dir> adds both to an extracted widget tree (widgets_patch.py calls add_chat)."""
import copy
import json
import os
import re
import sys
import t2guid

from clan_widgets import Builder, _templates
import nr_style as nr

# ---- HUD box (4K px; mockup chat-hud-typing.png = the 1080p frame x 2)
HB_X, HB_Y, HB_W, HB_H = 44.0, 1160.0, 1076.0, 520.0       # the box; chat.c CHB_* mirror the tab slots / underline
HB_LX = 32.0
HB_LINE_Y0, HB_LINE_DY, HB_LINE_H = 88.0, 62.0, 56.0
HB_LINE_PT, HB_TAB_PT, HB_SMALL_PT = 40, 30, 28
HB_TABS_R = 1044.0                                          # = chat.c CHB_TABS_R (HB_W - HB_LX): the tabs are packed right to left from here
TAB_GAP_EM = 1.5                                            # = chat.c CH_TAB_GAP (in ems of the tab point size)
HB_TAB_W = 160.0
HB_TAB_Y, HB_TAB_H = 22.0, 44.0
HB_UL_Y = 70.0                                              # the picked tab's underline (centre line; chat.c scales it to the name)
HB_FLD_Y, HB_FLD_H = 416.0, 88.0
HB_HINT_Y = 532.0
HB_IDLE_Y, HB_IDLE_H = 196.0, 250.0
HB_IDLE_DY = 36.0                                           # = chat.c CHB_IDLE_DY: the preview's rows sit this much lower than the typing box's
TAB_COL = (0xFFD7D7D7, 0xFF48A8D8, 0xFFD9D86A)              # = chat.c CH_COL
DIM = 0xFF6E7074
LINES = (("Farse", TAB_COL[1], "two on the stairs, left side"), ("FinalxBoss", TAB_COL[1], "im down by the bus"),
         ("Yama", TAB_COL[1], "rez me im by the boxes"), ("Kellie", 0xFFD9D86A, "omw"), ("Farse", TAB_COL[1], "they have a bow, careful"))

# ---- ESC menu block (local to the group at PNR_NEWS = (2640, 400), width 1060)
PC_X, PC_Y, PC_W = 2640.0, 400.0, 1060.0
PC_SEC_Y = 30.0                                             # = pause_restyle_widgets PNR_SECROW_Y
PC_TABS_X0 = 600.0                                          # = chat.c PC_TABS_X0 (the section rule ends here)
PC_TAB_PT = 25.5                                            # = chat.c PC_TAB_PT (nr.pt(17)); packed from PC_W like the HUD tabs
PC_TAB_W = 140.0
PC_UL_Y = 58.0
PC_BOX_Y, PC_BOX_H = 72.0, 273.0
PC_LINE_Y0, PC_LINE_DY, PC_LINE_H = 84.0, 50.0, 48.0
PC_FLD_Y, PC_FLD_H = 287.0, 50.0
BADGE_W, BADGE_H = 52.0, 46.0                               # chat.c ch_pause_badge pivots the group at its top left
BADGE_COL = 0xFFFD6D51


# = nrui.c NR_CWF (DINPro Medium advance widths for ' ' .. '~'; x pt x 1.06 = widget units)
_CWF = (0.308, 0.427, 0.570, 0.863, 0.781, 1.082, 0.938, 0.330, 0.407, 0.407, 0.623, 0.685, 0.349, 0.547, 0.357, 0.488, 0.685, 0.685, 0.685, 0.685, 0.685,
        0.685, 0.685, 0.685, 0.685, 0.685, 0.389, 0.389, 0.685, 0.685, 0.685, 0.657, 0.946, 0.803, 0.852, 0.807, 0.856, 0.775, 0.752, 0.834, 0.888, 0.378,
        0.650, 0.845, 0.737, 1.045, 0.928, 0.830, 0.808, 0.830, 0.842, 0.758, 0.719, 0.867, 0.725, 1.119, 0.743, 0.699, 0.709, 0.446, 0.488, 0.446, 0.734,
        0.734, 0.642, 0.681, 0.710, 0.623, 0.710, 0.692, 0.421, 0.705, 0.727, 0.339, 0.339, 0.704, 0.400, 1.127, 0.730, 0.690, 0.710, 0.710, 0.564, 0.641,
        0.439, 0.730, 0.605, 0.955, 0.646, 0.601, 0.603, 0.523, 0.434, 0.523, 0.737)


def twf(t, pts):
    """= nrui.c nr_twf (colour tags skipped)."""
    t = re.sub(r"<[^>]*>", "", t)
    return sum(_CWF[ord(c) - 32] if 32 <= ord(c) < 127 else 0.66 for c in t) * pts * 1.06


def tabs_pack(names, r, pts):
    """= chat.c ch_tabs_pack: [(right end, width)] of each name, packed right to left from r with one gap."""
    out = [None] * len(names)
    for k in range(len(names) - 1, -1, -1):
        w = twf(names[k], pts)
        out[k] = (r, w)
        r -= w + TAB_GAP_EM * pts
    return out, r


def _hud_line(who, col, text):
    return '<font color="#%06X">%s:</font> %s' % (col & 0xFFFFFF, who, text)


def add_chat_hud(wdir, main=None):
    """to1/currency-hud: chatHud > chatBox (see the module text). Idempotent; returns the number of widgets added."""
    path = os.path.join(wdir, "to1", "currency-hud.widget.json")
    if not os.path.exists(path):
        return 0
    w = json.load(open(path, encoding="utf-8"))
    items = w["items"]
    if any(i["name"] == "chatHud" for i in items):
        return 0
    if main is None:
        main = json.load(open(os.path.join(wdir, "to1", "main-menu.widget.json"), encoding="utf-8"))
    t, _, _ = _templates(main)
    b = Builder(t)
    b.items = []
    root = next(i for i in items if i["name"] == "root")
    top = b.group("chatHud", root["guid"], b.tl(0, 0, 3840, 2160))["guid"]
    g = b.group("chatBox", top, b.tl(HB_X, HB_Y, HB_W, HB_HINT_Y + 48), visible=0)["guid"]
    b.rect("chBg", g, b.tl(0, 0, HB_W, HB_H), nr.BLACK, 92)
    b.rect("chBgI", g, b.tl(0, HB_IDLE_Y, HB_W, HB_IDLE_H), nr.BLACK, 60, visible=0)
    b.text("chLbl", g, nr.lm(HB_LX, HB_TAB_Y, 300, HB_TAB_H), "CHAT", 32, nr.GREY, tracking=3)
    pk, _ = tabs_pack(("MATCH", "TEAM", "PARTY"), HB_TABS_R, HB_TAB_PT)
    for k, nm in enumerate(("MATCH", "TEAM", "PARTY")):
        r, uw = pk[k]
        b.text("chT%d" % k, g, nr.lm(r - HB_TAB_W, HB_TAB_Y, HB_TAB_W, HB_TAB_H, right=1), nm, HB_TAB_PT, TAB_COL[k] if k == 1 else DIM,
               align=2, tracking=3)
        b.rect("chU%d" % k, g, nr.lpiv(r - uw, HB_UL_Y - 1.5, nr.RULE_W0, 3), TAB_COL[k], 255, visible=int(k == 1), **{"scale.x": uw / nr.RULE_W0})
    for k in range(5):
        who, col, tx = LINES[k]
        for tw in ("", "B"):                               # "<leaf>B": the hidden twin chat.c writes first (double buffered, no blank frame on a change)
            b.text("chL%d%s" % (k, tw), g, nr.lm(HB_LX, HB_LINE_Y0 + k * HB_LINE_DY, HB_W - 2 * HB_LX, HB_LINE_H), "" if tw else _hud_line(who, col, tx),
                   HB_LINE_PT, 0xFFE8E8E8, tracking=1, **({"visible": 0} if tw else {}))
    b.rect("chFld", g, b.tl(16, HB_FLD_Y, HB_W - 32, HB_FLD_H), nr.BLACK, 120)
    for k in range(3):
        b.rect("chFu%d" % k, g, b.tl(16, HB_FLD_Y + HB_FLD_H - 3, HB_W - 32, 3), TAB_COL[k], 255, visible=int(k == 1))
    for tw in ("", "B"):
        b.text("chFtx" + tw, g, nr.lm(36, HB_FLD_Y, HB_W - 260, HB_FLD_H), "" if tw else "need ammo, who has a box|", HB_LINE_PT, 0xFFE8E8E8, tracking=1,
               **({"visible": 0} if tw else {}))
    b.text("chFch", g, nr.lm(HB_W - 216, HB_FLD_Y, 180, HB_FLD_H, right=1), '<font color="#48A8D8">TEAM</font>', HB_SMALL_PT, nr.GREY, align=2, tracking=3)
    k_ = '<font color="#E8E8E8">%s</font>'
    b.text("chHint", g, nr.lm(16, HB_HINT_Y, 1400, 40), (k_ % "ENTER") + " SEND      " + (k_ % "TAB") + " SWITCH TAB      " + (k_ % "ESC") + " CLOSE",
           HB_SMALL_PT, nr.GREY, tracking=2)
    # the preview's tab name at the box's top right
    b.text("chIdl", g, nr.lm(HB_W - HB_LX - 200, HB_IDLE_Y + 12, 200, 44, right=1), '<font color="#48A8D8">TEAM</font>', HB_SMALL_PT, nr.GREY,
           align=2, tracking=3, visible=0)
    items.extend(b.items)
    json.dump(w, open(path, "w", encoding="utf-8"), indent=4)
    return len(b.items)


def add_pause_chat(wdir, main=None):
    """to1/pause-menu: pzChat (CHAT block in CLAN NEWS's place) + pzPBadge. Idempotent; returns the number of widgets added."""
    path = os.path.join(wdir, "to1", "pause-menu.widget.json")
    if not os.path.exists(path):
        return 0
    w = json.load(open(path, encoding="utf-8"))
    items = w["items"]
    if any(i["name"] == "pzChat" for i in items):
        return 0
    if main is None:
        main = json.load(open(os.path.join(wdir, "to1", "main-menu.widget.json"), encoding="utf-8"))
    t, _, _ = _templates(main)
    b = Builder(t)
    b.items = []
    anim = next(i for i in items if i["name"] == "anim-group")
    a = anim["guid"]
    g = b.group("pzChat", a, b.tl(PC_X, PC_Y, PC_W, PC_FLD_Y + PC_FLD_H + 10), visible=0)["guid"]
    pk, x0 = tabs_pack(("MATCH", "TEAM", "PARTY"), PC_W, PC_TAB_PT)
    xa, xb = nr.section(b, g, "pcSec", 0, x0, PC_SEC_Y, "CHAT", "")              # (the rule ends one tab gap before the leftmost tab, = chat.c)
    tp = nr.pt(17)
    for k, nm in enumerate(("MATCH", "TEAM", "PARTY")):
        r, uw = pk[k]
        b.text("pcT%d" % k, g, nr.lm(r - PC_TAB_W, PC_SEC_Y - 22, PC_TAB_W, 44, right=1), nm, tp, TAB_COL[k] if k == 1 else DIM, align=2, tracking=2)
        b.rect("pcU%d" % k, g, nr.lpiv(r - uw, PC_UL_Y - 1.5, nr.RULE_W0, 3), TAB_COL[k], 255, visible=int(k == 1), **{"scale.x": uw / nr.RULE_W0})
    b.rect("pcBg", g, b.tl(0, PC_BOX_Y, PC_W, PC_BOX_H), nr.BLACK, 70)
    for k in range(4):
        who, col, tx = LINES[k + 1]
        for tw in ("", "B"):
            b.text("pcL%d%s" % (k, tw), g, nr.lm(28, PC_LINE_Y0 + k * PC_LINE_DY, PC_W - 56, PC_LINE_H), "" if tw else _hud_line(who, col, tx), nr.pt(21),
                   0xFFE8E8E8, tracking=1, **({"visible": 0} if tw else {}))
    b.rect("pcFld", g, b.tl(16, PC_FLD_Y, PC_W - 32, PC_FLD_H), nr.BLACK, 110)
    for k in range(3):
        b.rect("pcFu%d" % k, g, b.tl(16, PC_FLD_Y + PC_FLD_H - 3, PC_W - 32, 3), TAB_COL[k], 255, visible=int(k == 1))
    for tw in ("", "B"):
        b.text("pcFtx" + tw, g, nr.lm(34, PC_FLD_Y, PC_W - 230, PC_FLD_H), "" if tw else '<font color="#6E7074">ENTER to type,  TAB switch</font>', nr.pt(18),
               0xFFE8E8E8, tracking=1, **({"visible": 0} if tw else {}))
    b.text("pcFch", g, nr.lm(PC_W - 196, PC_FLD_Y, 170, PC_FLD_H, right=1), '<font color="#48A8D8">TEAM</font>', nr.pt(16), nr.GREY, align=2, tracking=3)
    bg = b.group("pzPBadge", a, b.tl(0, 0, BADGE_W, BADGE_H), visible=0)["guid"]
    b.rect("pzPBadgeBg", bg, b.fill(), BADGE_COL, 255)
    b.text("pzPBadgeTx", bg, b.fill(), "2", nr.pt(17), nr.INK, align=1, tracking=0)
    # gui2 draws in list order: the chat block goes BEFORE LEAVE GAME's ARE YOU SURE box (pause_restyle_widgets lqBox, last in the list), so the box and
    # its dim cover it (appended after the box, the chat lines drew over the dim)
    at = next((k for k, i in enumerate(items) if i["name"] == "lqBox"), len(items))
    items[at:at] = b.items
    for it in b.items:                                     # the section rule's real length (nrui.c nr_section sets it again at run time)
        if it["name"] == "pcSecRl":
            it["pivotAs.x"] = float(xa)
            it["scale.x"] = float(max(2.0, xb - xa) / nr.RULE_W0)
    json.dump(w, open(path, "w", encoding="utf-8"), indent=4)
    return len(b.items)


# ---- MP menu / FIND MATCH panel (preview scratch pvmenu/mk.py): local to the group at (MC_X, MC_Y); chat.c MC_* mirror these
MC_X, MC_W = 2500.0, 1182.0
MC_Y = 410.0 + 1120.0 + 24.0                                # the lobby box's bottom + one gap = 1554
MC_H = 1980.0 - 24.0 - MC_Y                                 # to one gap above the footer rule = 402
MC_HDR = 88.0                                               # header row (CHAT + the tab), the rule under it
MC_LX = 56.0
MC_LINE_Y0, MC_LINE_DY, MC_LINE_H, MC_LINE_PT = 100.0, 50.0, 50.0, 30
MC_FLD_H = 64.0
MC_FLD_Y = MC_H - 22.0 - MC_FLD_H                           # 316
MC_TAB_PT = 30
MC_UL_Y = MC_HDR / 2.0 + 24.0                               # = chat.c MC_UL_Y
ONLINE_Y = 104.0                                            # onlineGroup (it was 150 on main-menu, 285 on find-match-menu: under the strip now)


def add_menu_chat(wdir, main=None):
    """to1/main-menu + to1/find-match-menu: mnChat (hidden until chat.c shows it) + onlineGroup moved up. Idempotent; returns the widgets added."""
    n = 0
    if main is None:
        main = json.load(open(os.path.join(wdir, "to1", "main-menu.widget.json"), encoding="utf-8"))
    t, _, _ = _templates(main)
    for name in ("main-menu", "find-match-menu"):
        path = os.path.join(wdir, "to1", name + ".widget.json")
        if not os.path.exists(path):
            continue
        w = json.load(open(path, encoding="utf-8"))
        items = w["items"]
        if any(i["name"] == "mnChat" for i in items):
            continue
        for i in items:
            if i["name"] == "onlineGroup":
                i["pivotAs.y"] = ONLINE_Y
        anim = next(i for i in items if i["name"] == "anim-group")
        b = Builder(t)
        b.items = []
        g = b.group("mnChat", anim["guid"], b.tl(MC_X, MC_Y, MC_W, MC_H), visible=0, depth=4.5)["guid"]
        b.image("mcBlur", g, b.fill(), "general-textures/blur-background.png", 0xFFFFFFFF, 255)
        b.rect("mcBg", g, b.fill(), nr.BLACK, 150)
        b.line("mcLnT", g, 0, 0, MC_W, 0, 0xFFFFFFFF, 120)
        b.line("mcLnB", g, 0, MC_H, MC_W, MC_H, 0xFFFFFFFF, 120)
        b.text("mcHdr", g, nr.lm(MC_LX, 0, 500, MC_HDR), "CHAT", 38, 0xFFE6E6E6, face="Alternate", tracking=10)
        pk, _ = tabs_pack(("PARTY",), MC_W - MC_LX, MC_TAB_PT)
        r, uw = pk[0]
        b.text("mcT0", g, nr.lm(r - 300, 0, 300, MC_HDR, right=1), "PARTY", MC_TAB_PT, TAB_COL[2], align=2, tracking=3)
        b.rect("mcU0", g, b.tl(r - uw, MC_UL_Y, uw, 3), TAB_COL[2], 255)
        # (lobby panel) LOBBY: right of PARTY while the search is a lobby's (chat.c ch_menu_tabs moves PARTY left of it and shows these)
        lw = twf("LOBBY", MC_TAB_PT)
        b.text("mcT1", g, nr.lm(r - 300, 0, 300, MC_HDR, right=1), "LOBBY", MC_TAB_PT, 0xFF8FB0C8, align=2, tracking=3, visible=0)
        b.rect("mcU1", g, b.tl(r - lw, MC_UL_Y, lw, 3), 0xFF8FB0C8, 255, visible=0)
        b.line("mcHl", g, 40, MC_HDR, MC_W - 40, MC_HDR, 0xFFFFFFFF, 60)
        for k in range(4):
            who, col, tx = LINES[k + 1]
            for tw in ("", "B"):
                b.text("mcL%d%s" % (k, tw), g, nr.lm(MC_LX, MC_LINE_Y0 + k * MC_LINE_DY, MC_W - 2 * MC_LX, MC_LINE_H),
                       "" if tw else _hud_line(who, TAB_COL[2], tx), MC_LINE_PT, 0xFFE8E8E8, tracking=1, **({"visible": 0} if tw else {}))
        b.rect("mcFld", g, b.tl(40, MC_FLD_Y, MC_W - 80, MC_FLD_H), nr.BLACK, 110)
        b.rect("mcFu", g, b.tl(40, MC_FLD_Y + MC_FLD_H - 3, MC_W - 80, 3), TAB_COL[2], 255, visible=0)
        for tw in ("", "B"):
            b.text("mcFtx" + tw, g, nr.lm(64, MC_FLD_Y, MC_W - 300, MC_FLD_H), "" if tw else '<font color="#6E7074">ENTER to chat</font>', MC_LINE_PT,
                   0xFFE8E8E8, tracking=1, **({"visible": 0} if tw else {}))
        b.text("mcFch", g, nr.lm(MC_W - 260, MC_FLD_Y, 200, MC_FLD_H, right=1), "", 26, nr.GREY, align=2, tracking=3)
        at = next((k for k, i in enumerate(items) if i["name"] == "versionText"), len(items))
        items[at:at] = b.items
        json.dump(w, open(path, "w", encoding="utf-8"), indent=4)
        n += len(b.items)
    return n


def add_chat(wdir):
    main = json.load(open(os.path.join(wdir, "to1", "main-menu.widget.json"), encoding="utf-8"))
    return add_chat_hud(wdir, main) + add_pause_chat(wdir, main) + add_menu_chat(wdir, main)


if __name__ == "__main__":
    print(add_chat(sys.argv[1]))
