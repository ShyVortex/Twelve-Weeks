"""The in-game FRIENDS / PARTY panel (an in-game friends button, key P, next to the
lobby widget on the right; having it only in the launcher is not enough), built like the CLAN page (clan13_widgets.py) and driven by t2r-ext friends13.c from the
daemon's friends service (tools/social.py, op 0xD8 -> 0xD9).

  to1/main-menu + to1/find-match-menu: group "friendsBtn" directly under the LOBBY box on the right (lobby box = x 2500..3682, y 410..1530 in 3840 x 2160): a
        translucent black strip in the clan panel's style (blur + black + side lines), a key tile "P", FRIENDS, and a badge (new requests / invites).
  to1/friends13 (new page): header FRIENDS + who you are (name, friend id), two lists:
        left  PARTY   up to 4 member rows (leader mark, READY, presence) + the actions READY / LEAVE PARTY
        right FRIENDS row 0 = ADD FRIEND (typed in place), then party invites, friend requests, friends with presence (online first), requests you sent
        footer BACK / the focused row's action / the second action / SWITCH LIST, a key hint line and a status line.
Widget space 3840 x 2160. Every changing text / visibility / alpha is written by the ext; names are unique page-wide.
python friends13_widgets.py <extracted widget dir> <out dir> renders a quick CPU preview (PIL) of the page and the button."""
import copy
import json
import os
import t2guid
import rank_badge_widgets as rbw

from clan_widgets import Builder, _templates, PM_TEXT, PM_DIM
from matchflow_widgets import TEXT, CREAM
from gearup13_widgets import tlm

PAGE = "friends13"
PANEL = "streaming/t2r/clan/gearup-panel.png"
TITLE = 0xFFD8D4CC
LABEL = 0xFFB4B4B4
DIM = 0xFF8D897B
GOOD, WARN, BAD, INFO = 0xFF7CB494, 0xFFE0B04A, 0xFFFD6D51, 0xFF3FA9F5
TONE_COL = (CREAM, GOOD, WARN, BAD, INFO)           # band of a row: 0 neutral / offline, 1 in menu, 2 searching, 3 request, 4 in a match
HIT_A = 1
TAB_W, TAB_GREY, TAB_GREEN = 16, 0xFF4C4E52, 0xFF7FD07A     # the party readiness tab (same colours as teamtab_widgets)
CARD_A, EDGE_A, FOCUS_A, HILITE_A = 150, 46, 190, 16
X0, X1 = 300, 3540
LX, LW = 300, 1400
RX, RW = 1900, 1640
NL, NR = 6, 7                                       # left rows (4 members + 2 actions), right rows (ADD FRIEND + 6)
NPM = 4
LY = [540 + 170 * i for i in range(NPM)] + [1260, 1410]
LH = [150] * NPM + [130, 130]
RY0, RDY, RH = 540, 160, 140
MSG_Y, KEY_Y = 1690, 1770
BTN_X, BTN_Y, BTN_W, BTN_H = 2500, 1560, 1182, 120     # the button under the lobby box (lobby box 2500..3682 x 410..1530)


def edge(b, p, i, g, w, h):
    b.rect(f"{p}Card{i}", g, b.fill(), 0xFF000000, CARD_A)
    b.frame(f"{p}Edge{i}", g, b.fill(), 0xFFFFFFFF, EDGE_A, 2.0)
    b.rect(f"{p}Fill{i}", g, b.fill(), 0xFFFFFFFF, HILITE_A, visible=0)
    b.frame(f"{p}Frame{i}", g, b.fill(), 0xFFFFFFFF, FOCUS_A, 3.0, visible=0)
    for k, col in enumerate(TONE_COL):
        b.rect(f"{p}Bd{k}_{i}", g, b.tl(0, 0, 8, h), col, 230, visible=1 if k == 0 else 0)
    if p == "l" and i < NPM:         # party members: the readiness tab over the band - dark grey = not ready, green = ready (friends13.c fr_set_row)
        b.rect(f"lTabN{i}", g, b.tl(0, 0, TAB_W, h), TAB_GREY, 255, visible=0)
        b.rect(f"lTabG{i}", g, b.tl(0, 0, TAB_W, h), TAB_GREEN, 255, visible=0)


def row(b, p, i, parent, x, y, w, h):
    g = b.group(f"{p}Row{i}", parent, b.tl(x, y, w, h), visible=0)["guid"]
    edge(b, p, i, g, w, h)
    rbw.add_to_builder(b, g, f"{p}Rk{i}", f"{p}Rn{i}", 36, 40, 46, 80)                                   # the rank badge (rank_badge_widgets; friends13.c moves the name right by RKB_RES46 while it shows)
    b.text(f"{p}Nm{i}", g, tlm(36, 10, w - 700, 60), "", 46, TEXT, tracking=2)
    # St / Tg / Ac pivot at their left / right middle: friends13.c fits (w_scale) a too-long line about that edge instead of letting it run over its neighbour
    b.text(f"{p}St{i}", g, tlm(36, h - 56, w - 760, 40), "", 28, DIM, face="Alternate", tracking=6)
    b.text(f"{p}Tg{i}", g, tlm(w - 640, 16, 600, 40, right=1), "", 28, DIM, face="Alternate", align=2, tracking=6)
    b.text(f"{p}Ac{i}", g, tlm(w - 740, h - 56, 700, 40, right=1), "", 28, DIM, face="Alternate", align=2, tracking=6)
    b.rect(f"{p}Hit{i}", g, b.fill(), 0xFFFFFFFF, HIT_A)
    return g


# the ADD FRIEND text field (shown by friends13.c over the first right row while typing; hidden otherwise). Local coordinates, box RW x RH.
#   inpCard / inpEdge  the same card + thin edge as a row;  inpBd  the cream band on the left
#   inpGlow            faint band rising from the underline (alpha pulsed by the ext, scaled from the centre)
#   inpUl              the focus underline: grows from the centre to the full width when typing starts (w_scale x), the ext sets its alpha
#   inpLbl / inpCnt    what it is / "n / 31";  inpTx the value (caret = a "|" in the text, blinked by colour);  inpPh the placeholder (faded out by the ext)
#   inpKey             ENTER SENDS, inside the box on the right (the longer key line stays in the footer)
INP_TX_W = RW - 520


def input_field(b, parent):
    h = RH
    g = b.group("inp", parent, b.tl(RX, RY0, RW, h), visible=0)["guid"]
    b.rect("inpCard", g, b.fill(), 0xFF000000, 175)
    b.frame("inpEdge", g, b.fill(), 0xFFFFFFFF, 70, 2.0)
    b.rect("inpBd", g, b.tl(0, 0, 8, h), CREAM, 230)
    b.rect("inpGlow", g, b.ctr(RW / 2.0, h - 22, RW, 40), 0xFFFFFFFF, 20)
    b.rect("inpUl", g, b.ctr(RW / 2.0, h - 3, RW, 5), 0xFFFFFFFF, 240)
    b.text("inpLbl", g, tlm(36, 12, 1100, 34), "", 28, DIM, face="Alternate", tracking=6)
    b.text("inpCnt", g, tlm(RW - 360, 12, 324, 34, right=1), "", 28, DIM, face="Alternate", align=2, tracking=6)
    b.text("inpTx", g, tlm(36, 46, INP_TX_W, 80), "", 54, TEXT, tracking=2)
    b.text("inpPh", g, tlm(36, 46, INP_TX_W, 80), "", 46, DIM, tracking=2)
    b.text("inpKey", g, tlm(RW - 460, h - 52, 424, 40, right=1), "", 28, DIM, face="Alternate", align=2, tracking=6)
    return g


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
    # header
    hd = b.group("hd", a, b.tl(0, 0, 3840, 2160))["guid"]
    b.text("hdKick", hd, b.tl(X0, 90, 1200, 44), "", 32, LABEL, face="Alternate", tracking=8)
    b.text("hdTitle", hd, b.tl(X0 - 4, 126, 1800, 150), "", 104, TITLE, tracking=4)
    b.text("hdMe", hd, tlm(2040, 150, 1500, 60, right=1), "", 46, TEXT, align=2, tracking=3)
    b.text("hdId", hd, tlm(2040, 214, 1500, 46, right=1), "", 30, LABEL, face="Alternate", align=2, tracking=4)
    b.line("hdRule", hd, X0, 392, X1, 392, 0xFFFFFFFF, 130, 2.0)
    b.text("ldTx", a, b.tl(X0, 900, X1 - X0, 200), "", 52, PM_DIM, align=1, tracking=4, multiline=1, visible=0)
    # left: PARTY
    lg = b.group("lf", a, b.tl(0, 0, 3840, 2160))["guid"]
    b.text("lTitle", lg, b.tl(LX, 424, 700, 80), "", 54, TEXT, tracking=3)
    b.text("lSub", lg, tlm(LX + 400, 450, LW - 400, 46, right=1), "", 30, DIM, face="Alternate", align=2, tracking=6)
    for i in range(NL):
        row(b, "l", i, lg, LX, LY[i], LW, LH[i])
    b.text("lNone", lg, b.tl(LX, 560, LW, 120), "", 38, PM_DIM, tracking=3, multiline=1, valign=0, visible=0)
    # right: FRIENDS
    rg = b.group("rt", a, b.tl(0, 0, 3840, 2160))["guid"]
    b.text("rTitle", rg, b.tl(RX, 424, 700, 80), "", 54, TEXT, tracking=3)
    b.text("rSub", rg, tlm(RX + 400, 450, RW - 400, 46, right=1), "", 30, DIM, face="Alternate", align=2, tracking=6)
    for i in range(NR):
        row(b, "r", i, rg, RX, RY0 + RDY * i, RW, RH)
    b.text("rMore", rg, tlm(RX, RY0 + RDY * NR - 10, RW, 40, right=1), "", 28, DIM, face="Alternate", align=2, tracking=6)
    input_field(b, rg)
    # status + key hint lines
    b.text("msgTx", a, tlm(X0, MSG_Y, X1 - X0, 60), "", 40, TEXT, tracking=3)
    b.text("keyTx", a, tlm(X0, KEY_Y, X1 - X0, 44), "", 28, DIM, face="Alternate", tracking=6)
    # prompts (the clan page's footer)
    b.image("pBackIc", a, b.tl(270, 1898, 56, 56), "menu:back", 0xFFFFFFFF)
    b.text("pBackTx", a, tlm(350, 1890, 400, 70), "BACK", 46, PM_TEXT, tracking=4)
    b.image("pSelIc", a, b.tl(760, 1898, 56, 56), "menu:select", 0xFFFFFFFF)
    b.text("pSelTx", a, tlm(840, 1890, 640, 70), "", 46, PM_TEXT, tracking=4)
    b.image("pActIc", a, b.tl(1520, 1898, 56, 56), "menu:action", 0xFFFFFFFF)
    b.text("pActTx", a, tlm(1600, 1890, 640, 70), "", 46, PM_TEXT, tracking=4)
    b.image("pPrevIc", a, b.tl(2300, 1898, 56, 56), "menu:prev", 0xFFFFFFFF)
    b.image("pNextIc", a, b.tl(2380, 1898, 56, 56), "menu:next", 0xFFFFFFFF)
    b.text("pTabTx", a, tlm(2460, 1890, 760, 70), "", 46, PM_TEXT, tracking=4)
    b.rect("pBackHit", a, b.tl(250, 1800, 480, 200), 0xFFFFFFFF, HIT_A)
    w = {k: copy.deepcopy(v) for k, v in main.items() if k != "items"}
    w["items"] = b.items
    return w


def add_friends13_page(wdir):
    main = json.load(open(os.path.join(wdir, "to1", "main-menu.widget.json"), encoding="utf-8"))
    json.dump(build_page(main), open(os.path.join(wdir, "to1", PAGE + ".widget.json"), "w", encoding="utf-8"), indent=4)
    return 1


def add_friends_button(wdir):
    """group friendsBtn on to1/main-menu and to1/find-match-menu (hidden; t2r-ext shows it in the menus). Returns how many pages got it."""
    n = 0
    main = json.load(open(os.path.join(wdir, "to1", "main-menu.widget.json"), encoding="utf-8"))
    t, _, _ = _templates(main)
    for name in ("main-menu", "find-match-menu"):
        path = os.path.join(wdir, "to1", name + ".widget.json")
        if not os.path.exists(path):
            continue
        page = json.load(open(path, encoding="utf-8"))
        if any(i["name"] == "friendsBtn" for i in page["items"]):
            continue
        anim = next(i for i in page["items"] if i["name"] == "anim-group")
        b = Builder(t)
        g = b.group("friendsBtn", anim["guid"], b.tl(BTN_X, BTN_Y, BTN_W, BTN_H), visible=0, depth=4.5)["guid"]
        b.image("frBlur", g, b.fill(), "general-textures/blur-background.png", 0xFFFFFFFF, 255)
        b.rect("frBg", g, b.fill(), 0xFF000000, 150)
        b.line("frLineL", g, 0, 0, 0, BTN_H, 0xFFFFFFFF, 130, 2.0)
        b.line("frLineR", g, BTN_W, 0, BTN_W, BTN_H, 0xFFFFFFFF, 130, 2.0)
        b.rect("frFill", g, b.fill(), 0xFFFFFFFF, HILITE_A, visible=0)
        b.frame("frKeyEdge", g, b.tl(34, 26, 68, 68), 0xFFE6E6E6, 200, 3.0)
        b.text("frKey", g, b.tl(34, 26, 68, 68), "P", 44, 0xFFE6E6E6, align=1, tracking=0)
        b.text("frLabel", g, tlm(130, 20, 620, 80), "FRIENDS", 50, 0xFFE6E6E6, tracking=4)
        b.text("frSub", g, b.tl(BTN_W - 470, 38, 420, 44), "", 30, 0xFF9C9A9A, face="Alternate", align=2, tracking=5)
        b.ellipse("frBadgeBg", g, b.ctr(BTN_W - 590, 60, 52, 52), 0xFFE04848, 255)["visible"] = 0
        b.text("frBadge", g, b.ctr(BTN_W - 590, 60, 52, 52), "", 30, 0xFFFFFFFF, align=1, tracking=0, visible=0)
        b.rect("frHit", g, b.fill(), 0xFFFFFFFF, HIT_A)
        at = next(k for k, i in enumerate(page["items"]) if i["name"] == "versionText") if any(i["name"] == "versionText" for i in page["items"]) else len(page["items"])
        page["items"][at:at] = b.items
        json.dump(page, open(path, "w", encoding="utf-8"), indent=4)
        n += 1
    return n


# ---- the friend / party toast (notifications in the bottom right corner, lifted, for friend invites and party invites): ONE card on the MP menu and FIND MATCH,
# bottom right, above the footer and below the FRIENDS strip, slid / faded in and out by friends13.c (w_pivot x + w_alpha), with a progress line and the key chips Y / N.
TOAST_X, TOAST_Y, TOAST_W, TOAST_H = 2480, 1760, 1240, 180
TOAST_TONES = (0xFF3FA9F5, 0xFFF0B429, 0xFF7CB494, 0xFFF2625A, 0xFFB4B4B4)     # friend request, party invite, done, refused, info
CHIP_X, CHIP_Y0, CHIP_Y1, CHIP_W, CHIP_H = 868, 26, 98, 340, 62


def add_toast(b, parent):
    W, H = TOAST_W, TOAST_H
    g = b.group("frToast", parent, b.tl(TOAST_X, TOAST_Y, W, H), visible=0, depth=4.6)["guid"]
    b.image("tBlur", g, b.fill(), "general-textures/blur-background.png", 0xFFFFFFFF, 255)
    b.rect("tBg", g, b.fill(), 0xFF000000, 170)
    b.frame("tEdge", g, b.fill(), 0xFFFFFFFF, 50, 2.0)
    for k, col in enumerate(TOAST_TONES):
        b.rect(f"tAc{k}", g, b.tl(0, 0, 10, H), col, 240, visible=1 if k == 0 else 0)
    b.image("tIc", g, b.tl(44, 46, 88, 88), "streaming/t2r/icons/notify-info.png", 0xFFFFFFFF)
    b.text("tKick", g, tlm(160, 16, 700, 36), "", 26, DIM, face="Alternate", tracking=8)
    b.text("tName", g, tlm(160, 52, 680, 66), "", 52, TEXT, tracking=2)
    b.text("tSub", g, tlm(160, 118, 680, 40), "", 28, LABEL, face="Alternate", tracking=5)
    b.text("tInfo", g, b.tl(160, 52, W - 220, 100), "", 34, TEXT, tracking=2, multiline=1, valign=0, visible=0)
    b.text("tMore", g, tlm(W - 160, 12, 130, 32, right=1), "", 26, DIM, face="Alternate", align=2, tracking=5)
    for k, (cy, key) in enumerate(((CHIP_Y0, "Y"), (CHIP_Y1, "N"))):
        n = "YN"[k]
        b.rect(f"tFill{n}", g, b.tl(CHIP_X - 16, cy, CHIP_W, CHIP_H), 0xFFFFFFFF, 16, visible=0)
        b.frame(f"tKe{n}", g, b.tl(CHIP_X, cy + 5, 52, 52), 0xFFE6E6E6, 210, 3.0)
        b.text(f"tKt{n}", g, b.tl(CHIP_X, cy + 5, 52, 52), key, 32, 0xFFE6E6E6, align=1, tracking=0)
        b.text(f"tLb{n}", g, tlm(CHIP_X + 72, cy, CHIP_W - 100, CHIP_H), "", 32, TEXT, tracking=4)
    b.rect("tBarBg", g, b.tl(0, H - 5, W, 5), 0xFFFFFFFF, 22)
    b.rect("tBar", g, b.tl(0, H - 5, W, 5), 0xFFFFFFFF, 150)
    return g


def add_friends_toast(wdir):
    """group frToast on to1/main-menu and to1/find-match-menu (hidden). Returns how many pages got it."""
    n = 0
    main = json.load(open(os.path.join(wdir, "to1", "main-menu.widget.json"), encoding="utf-8"))
    t, _, _ = _templates(main)
    for name in ("main-menu", "find-match-menu"):
        path = os.path.join(wdir, "to1", name + ".widget.json")
        if not os.path.exists(path):
            continue
        page = json.load(open(path, encoding="utf-8"))
        if any(i["name"] == "frToast" for i in page["items"]):
            continue
        anim = next(i for i in page["items"] if i["name"] == "anim-group")
        b = Builder(t)
        add_toast(b, anim["guid"])
        at = next(k for k, i in enumerate(page["items"]) if i["name"] == "versionText") if any(i["name"] == "versionText" for i in page["items"]) else len(page["items"])
        page["items"][at:at] = b.items
        json.dump(page, open(path, "w", encoding="utf-8"), indent=4)
        n += 1
    return n


if __name__ == "__main__":
    import sys
    src, out = sys.argv[1], sys.argv[2]
    os.makedirs(out, exist_ok=True)
    main = json.load(open(os.path.join(src, "to1", "main-menu.widget.json"), encoding="utf-8"))
    pg = build_page(main)
    names = [i["name"] for i in pg["items"]]
    assert len(names) == len(set(names)), "duplicate widget names"
    json.dump(pg, open(os.path.join(out, PAGE + ".widget.json"), "w", encoding="utf-8"), indent=1)
    print("page ok:", len(names), "widgets")
