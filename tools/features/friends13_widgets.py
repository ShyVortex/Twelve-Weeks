"""The in-game FRIENDS / PARTY panel (the ingame ui has a friends button (P maybe for party), and it should be somewhere next to the
lobby widget on the right, having it just in the launcher is useless"), built like the CLAN page (clan13_widgets.py) and driven by t2r-ext friends13.c from the
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

from clan_widgets import Builder, _templates
from matchflow_widgets import TEXT, CREAM
import nr_style as nr
from nr_style import lm as tlm      # (was gearup13_widgets.tlm, same box; moved to the shared frame)

PAGE = "friends13"
TITLE = 0xFFD8D4CC
LABEL = 0xFFB4B4B4
DIM = 0xFF8D897B
GOOD, WARN, BAD, INFO = 0xFF7CB494, 0xFFE0B04A, 0xFFFD6D51, 0xFF3FA9F5
HIT_A = 1
HILITE_A = 16
# Redesign: the page sits on the shared No Return frame (nr_style.frame): breadcrumb MULTIPLAYER | FRIENDS, two columns PARTY / FRIENDS
# headed by nr.section rows, flat tile rows (one movable focus outline, nrui.c nr_frame_at "frFo"), boxed prompts (nrui.c nr_prompts).
LX, LW = 148, 1676                                  # left column (PARTY), margin L0 148
RX, RW = 2004, 1676                                 # right column (FRIENDS), ends at 3680; the scroll track stands at x 3694 (R1 3700)
SCX = 3694
NL, NR = 6, 7                                       # left rows (4 members + 2 actions), right rows (ADD FRIEND + 6)
NPM = 4
SEC_Y = 470                                         # the section rows' centre line
LY = [524 + 152 * i for i in range(NPM)] + [1176, 1328]
LH = [136] * NL
RY0, RDY, RH = 524, 152, 136
MSG_Y, KEY_Y = 1730, 1830
NAME_CY, ST_CY, CHIP_Y = 46, 100, 26               # row-local: name line, status / action line, chip top
NAME_PT, SM_PT = nr.pt(26), nr.pt(16)               # 39 / 24 (the player stats rows: name pt(26), small caps pt(16))
RK_PT, RK_H = 40, 68                                # rank badge metrics (= clan13x xpRk): reserved width 104
# MP menu layout: the strip sits ABOVE the lobby box (24 apart); chat_widgets.add_menu_chat puts the
# CHAT panel under the box and moves the online counter up to y 104. friends13.c fr_btn_hover mirrors BTN_Y.
BTN_X, BTN_Y, BTN_W, BTN_H = 2500, 266, 1182, 120      # the strip above the lobby box (lobby box 2500..3682 x 410..1530)
CHIPS = (("Cg", "grey"), ("Ca", "acc"), ("Cw", "white"))     # per row: grey (LEADER / NOT READY / IN YOUR PARTY), accent (READY), white (INVITE / REQUEST); friends13.c places them right to left


def row(b, p, i, parent, x, y, w, h):
    g = b.group(f"{p}Row{i}", parent, b.tl(x, y, w, h), visible=0)["guid"]
    b.rect(f"{p}Bg{i}", g, b.fill(), nr.TILE, nr.TILE_A)
    b.rect(f"{p}Fill{i}", g, b.fill(), 0xFFFFFFFF, HILITE_A, visible=0)               # hover / focus lift (gu_fade)
    b.rect(f"{p}Ed{i}", g, b.tl(0, 0, 6, h), nr.ACC, 255, visible=0)                  # the accent edge: your own row / a ready member
    rbw.add_to_builder(b, g, f"{p}Rk{i}", f"{p}Rn{i}", 36, NAME_CY, RK_PT, RK_H)       # the rank badge (friends13.c moves the name right by RKB_RES while it shows)
    b.text(f"{p}Nm{i}", g, nr.lm(36, NAME_CY - 32, w - 400, 64), "", NAME_PT, nr.WHITE, tracking=1)
    b.text(f"{p}Yu{i}", g, nr.lm(36, NAME_CY - 20, 200, 40), "", SM_PT, nr.ACC, tracking=3)
    b.text(f"{p}St{i}", g, nr.lm(36, ST_CY - 20, 1000, 40), "", SM_PT, nr.GREY, tracking=3)
    b.text(f"{p}Ac{i}", g, nr.lm(w - 24 - 600, ST_CY - 20, 600, 40, right=1), "", SM_PT, nr.GREY, align=2, tracking=3)
    for k, style in CHIPS:
        nr.chip(b, g, f"{p}{k}{i}", w - 200, CHIP_Y, "", pts=SM_PT, style=style, w=100)
    b.rect(f"{p}Hit{i}", g, b.fill(), 0xFFFFFFFF, HIT_A)
    return g


# the ADD FRIEND text field (shown by friends13.c over the first right row while typing; hidden otherwise). Local coordinates, box RW x RH.
#   inpBg              the tile (focused alpha);  inpGlow faint band rising from the underline (alpha pulsed by the ext, scaled from the centre)
#   inpUl              the white underline: grows from the centre to the full width when typing starts (w_scale x), the ext sets its alpha
#   inpLbl / inpCnt    what it is / "n / 31" (grey);  inpTx the value (caret = a "|" in the text, blinked by colour);  inpPh the placeholder (faded out by the ext)
#   inpKey             ENTER SENDS, inside the box on the right (the longer key line stays in the footer)
INP_TX_W = RW - 520


def input_field(b, parent):
    h = RH
    g = b.group("inp", parent, b.tl(RX, RY0, RW, h), visible=0)["guid"]
    b.rect("inpBg", g, b.fill(), nr.TILE, nr.TILE_FA)
    b.rect("inpGlow", g, b.ctr(RW / 2.0, h - 22, RW, 40), 0xFFFFFFFF, 20)
    b.rect("inpUl", g, b.ctr(RW / 2.0, h - 2, RW, 4), 0xFFFFFFFF, 240)
    b.text("inpLbl", g, nr.lm(36, 12, 1100, 36), "", SM_PT, nr.GREY, tracking=3)
    b.text("inpCnt", g, nr.lm(RW - 360, 12, 324, 36, right=1), "", SM_PT, nr.GREY, align=2, tracking=3)
    b.text("inpTx", g, nr.lm(36, 52, INP_TX_W, 64), "", nr.pt(30), nr.WHITE, tracking=1)
    b.text("inpPh", g, nr.lm(36, 52, INP_TX_W, 64), "", NAME_PT, nr.GREY, tracking=1)
    b.text("inpKey", g, nr.lm(RW - 460, h - 50, 424, 36, right=1), "", SM_PT, nr.GREY, align=2, tracking=3)
    return g


# MESSAGES (chat, "a P prompt button that opens up the friends UI from the menu and that should have a chat box in the left of the screen where the
# empty space is where you can select latest chats"): group "msg" (hidden; friends13.c fm_fill shows it and moves it: section line at y 760 without a party,
# at the PARTY section's 470 with one while MESSAGES is the picked list). Group-local coordinates (x 0 = the left margin 148), = friends13.c FM_*:
#   msSec              section row MESSAGES ... FRIENDS ONLY
#   mR0..4             conversation tiles (0, 54 + 146 i, 560 x 130): mRBg / mRFill (hover lift) / mREd (accent edge = the open chat) / mRNm name / mRLt last line /
#                      mRUb + mRUt the unread badge
#   mMore              "+ n MORE" under the tiles
#   mTh                the thread panel (600, 54, 1076 x 646): mThBg, mThE (empty / loading line), mThN0..4 (who + when) / mThT0..4 (the text, two lines)
#   mQL, mQ0..3(F)     QUICK REPLY label + four chips (dark; the "F" twin in white = focused / hovered), laid out by fm_fill (nrui.c nr_chip)
#   mF                 the typing line (600, 826, 1076 x 96): mFBg, mFUl (accent underline while typing), mFTx, mFCnt (n / 200), mFKey (ENTER SENDS)
MS_X, MS_Y, MS_W = 148, 760, 1676
MS_TY, MS_TDY, MS_TW, MS_TH, MS_NV = 54, 146, 560, 130, 5
MS_PX, MS_PW, MS_PH = 600, 1076, 646
MS_NTL, MS_LDY = 5, 124
MS_QLY, MS_QY, MS_QPT = 724, 752, 30
MS_FY, MS_FH = 826, 96
MS_BADGE = 0xFFFD6D51
MS_QUICK = ("GG", "ONE MORE?", "INVITE ME", "REVIVE ME")      # = friends13.c fm_quick (REVIVE ME, was AFTER THIS MATCH)
MS_QGAP = 16


def messages(b, a):
    g = b.group("msg", a, b.tl(MS_X, MS_Y, MS_W, MS_FY + MS_FH), visible=0)["guid"]
    nr.section(b, g, "msSec", 0, MS_W, 0, "MESSAGES", "FRIENDS ONLY")
    for i in range(MS_NV):
        r = b.group(f"mR{i}", g, b.tl(0, MS_TY + MS_TDY * i, MS_TW, MS_TH), visible=0)["guid"]
        b.rect(f"mRBg{i}", r, b.fill(), nr.TILE, nr.TILE_A)
        b.rect(f"mRFill{i}", r, b.fill(), 0xFFFFFFFF, HILITE_A, visible=0)
        b.rect(f"mREd{i}", r, b.tl(0, 0, 6, MS_TH), nr.ACC, 255, visible=0)
        b.text(f"mRNm{i}", r, nr.lm(28, 40 - 28, MS_TW - 120, 56), "", 36, nr.WHITE, tracking=1)
        b.text(f"mRLt{i}", r, nr.lm(28, 94 - 20, MS_TW - 56, 40), "", SM_PT, nr.GREY, tracking=1)
        b.rect(f"mRUb{i}", r, b.tl(MS_TW - 64, 20, 44, 40), MS_BADGE, 255, visible=0)
        b.text(f"mRUt{i}", r, b.tl(MS_TW - 64, 20, 44, 40), "", SM_PT, nr.INK, align=1, visible=0)
    b.text("mMore", g, nr.lm(0, MS_TY + MS_TDY * MS_NV, MS_TW, 40, right=1), "", SM_PT, nr.GREY, align=2, tracking=3)
    th = b.group("mTh", g, b.tl(MS_PX, MS_TY, MS_PW, MS_PH))["guid"]
    b.rect("mThBg", th, b.fill(), nr.TILE, 150)
    b.text("mThE", th, nr.lm(40, MS_PH / 2 - 30, MS_PW - 80, 60), "", nr.pt(22), nr.GREY, align=1, tracking=3)
    for k in range(MS_NTL):
        y = 24 + MS_LDY * k
        for tw in ("", "B"):                                # "B" twins: friends13.c fm_tw (no blank frame when a message comes in or goes out)
            hid = {"visible": 0} if tw else {}
            b.text(f"mThN{k}{tw}", th, nr.lm(32, y, MS_PW - 64, 30), "", SM_PT, nr.GREY, tracking=2, **hid)
            b.text(f"mThT{k}{tw}", th, b.tl(32, y + 30, MS_PW - 64, 84), "", nr.pt(19), nr.WHITE, multiline=1, valign=0, tracking=1, **hid)
    b.text("mQL", g, nr.lm(MS_PX, MS_QLY - 20, MS_PW, 40), "", SM_PT, nr.GREY, tracking=3)
    # the chips fill the panel's width, each text centred (= friends13.c fm_fill / fm_chip)
    nat = [nr.est(q, MS_QPT) * 1.06 + 32 for q in MS_QUICK]
    extra = (MS_PW - MS_QGAP * (len(MS_QUICK) - 1) - sum(nat)) / len(MS_QUICK)
    x = MS_PX
    for k, q in enumerate(MS_QUICK):
        w = MS_PX + MS_PW - x if k == len(MS_QUICK) - 1 else nat[k] + extra
        for tw, style in (("", "dark"), ("F", "white")):
            nr.chip(b, g, f"mQ{k}{tw}", x, MS_QY, q, pts=MS_QPT, style=style, w=w)
            bg, tx = b.items[-2:]
            bg["visible"] = tx["visible"] = 0
            tx.update({"alignH": 1, "pivotN.x": 0.5, "pivotAs.x": float(x + w / 2.0), "rectSizeDelta.width": float(w)})
        x += w + MS_QGAP
    f = b.group("mF", g, b.tl(MS_PX, MS_FY, MS_PW, MS_FH), visible=0)["guid"]
    b.rect("mFBg", f, b.fill(), nr.BLACK, 120)
    b.rect("mFUl", f, b.tl(0, MS_FH - 4, MS_PW, 4), nr.ACC, 255, visible=0)
    # "<leaf>B": the twins friends13.c fm_tw writes (chat.c chtw: the new text shows while the old stays, no blank frame on a key -)
    for tw in ("", "B"):
        b.text("mFTx" + tw, f, nr.lm(28, 0, MS_PW - 340, MS_FH), "", nr.pt(26), nr.WHITE, tracking=1, **({"visible": 0} if tw else {}))
        b.text("mFCnt" + tw, f, nr.lm(MS_PW - 320, 8, 296, 36, right=1), "", SM_PT, nr.GREY, align=2, tracking=2, **({"visible": 0} if tw else {}))
    b.text("mFKey", f, nr.lm(MS_PW - 320, MS_FH - 46, 296, 36, right=1), "", SM_PT, nr.GREY, align=2, tracking=3)
    return g


def build_page(main):
    t, root0, anim0 = _templates(main)
    b = Builder(t)
    root = copy.deepcopy(root0); root.update(guid=t2guid.guid())
    anim = copy.deepcopy(anim0); anim.update(guid=t2guid.guid(), parent=root["guid"])
    b.items += [root, anim]
    a = anim["guid"]
    nr.frame(b, a, "MULTIPLAYER", "FRIENDS", None, 0, None, 4)             # BACK / the row's action / the second action / SWITCH LIST
    # who you are, top right where the clan pages carry the week block
    hd = b.group("hd", a, b.tl(0, 0, 3840, 2160))["guid"]
    b.text("hdMe", hd, nr.lm(nr.R1 - 1500, 256 - 34, 1500, 68, right=1), "", nr.pt(28), nr.WHITE, align=2, tracking=3)
    b.text("hdId", hd, nr.lm(nr.R1 - 1500, 320 - 26, 1500, 52, right=1), "", nr.pt(20), nr.GREY, align=2, tracking=3)
    b.text("ldTx", a, nr.lm(nr.L0, 900, nr.R1 - nr.L0, 200), "", nr.pt(24), nr.GREY, align=1, tracking=3, multiline=1, visible=0)
    # left: PARTY
    lg = b.group("lf", a, b.tl(0, 0, 3840, 2160))["guid"]
    nr.section(b, lg, "lSec", LX, LX + LW, SEC_Y, "PARTY", "")
    for i in range(NL):
        row(b, "l", i, lg, LX, LY[i], LW, LH[i])
    b.text("lNone", lg, nr.lm(LX, 524, LW - 80, 200), "", nr.pt(20), nr.GREY, tracking=3, multiline=1, valign=0, visible=0)
    # right: FRIENDS
    rg = b.group("rt", a, b.tl(0, 0, 3840, 2160))["guid"]
    nr.section(b, rg, "rSec", RX, RX + RW, SEC_Y, "FRIENDS", "")
    for i in range(NR):
        row(b, "r", i, rg, RX, RY0 + RDY * i, RW, RH)
    b.text("rMore", rg, nr.lm(RX, RY0 + RDY * NR + 24, RW, 40, right=1), "", SM_PT, nr.GREY, align=2, tracking=3)
    nr.scroll_v(b, rg, "rSc", SCX, RY0, RY0 + RDY * NR, 0.0, 1.0, visible=0)
    input_field(b, rg)
    messages(b, a)                                                          # MESSAGES (chat), in the left column's empty space
    nr.focus_frame(b, a, "frFo")                                            # ONE focus outline for both lists (nrui.c nr_frame_at)
    # status + key hint lines (grey small caps above the prompts)
    b.text("msgTx", a, nr.lm(nr.L0, MSG_Y, nr.R1 - nr.L0, 60), "", nr.pt(22), nr.GREY, tracking=3)
    b.text("keyTx", a, nr.lm(nr.L0, KEY_Y, nr.R1 - nr.L0, 44), "", SM_PT, nr.GREY, tracking=3)
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


# ---- the friend / party toast (notifications in the bottom right corner (lifted) for friend invites and party invites): ONE card on the MP menu and FIND MATCH,
# bottom right, above the footer and below the FRIENDS strip, slid / faded in and out by friends13.c (w_pivot x + w_alpha), with a progress line and the key chips Y / N.
TOAST_X, TOAST_Y, TOAST_W, TOAST_H = 2480, 1760, 1240, 180
TOAST_HUD_Y = 1500        # the HUD copy (to1/currency-hud frHud > frToast): above the weapon ring (= friends13.c FT_HY)
TOAST_TONES = (0xFF3FA9F5, 0xFFF0B429, 0xFF7CB494, 0xFFF2625A, 0xFFB4B4B4)     # friend request, party invite, done, refused, info
CHIP_X, CHIP_Y0, CHIP_Y1, CHIP_W, CHIP_H = 868, 26, 98, 340, 62


def add_toast(b, parent, y=TOAST_Y):
    W, H = TOAST_W, TOAST_H
    g = b.group("frToast", parent, b.tl(TOAST_X, y, W, H), visible=0, depth=4.6)["guid"]
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
    # the same card in a match: the HUD page gets a copy,
    # frHud (full page) > frToast, which friends13.c finds through hud_widget("frHud", "frToast", leaf) and drives like the menu one.
    path = os.path.join(wdir, "to1", "currency-hud.widget.json")
    if os.path.exists(path):
        page = json.load(open(path, encoding="utf-8"))
        if not any(i["name"] == "frHud" for i in page["items"]):
            root = next(i for i in page["items"] if i["name"] == "root")
            b = Builder(t)
            top = b.group("frHud", root["guid"], b.tl(0, 0, 3840, 2160))["guid"]
            add_toast(b, top, TOAST_HUD_Y)
            page["items"].extend(b.items)
            json.dump(page, open(path, "w", encoding="utf-8"), indent=4)
            n += 1
    return n


# ---------------------------------------------------------------------------------------------------------------- previews
# An offline stand-in for friends13.c fr_fill (the widgets are filled by the ext in the game): demo(page, state, lang) writes a state into a copy of the page.
RES = 104.0                                          # = friends13.c RKB_RES46 = rank_badge_widgets.reserved(RK_PT, RK_H)
ONLINE_TXT = {1: ("IN THE LAUNCHER", "W LAUNCHERZE"), 2: ("IN THE MENU", "W MENU"), 3: ("SEARCHING FOR A MATCH", "SZUKA MECZU"), 4: ("IN A MATCH", "W MECZU"), 0: ("OFFLINE", "OFFLINE")}


def _fit(by, n, s, box):
    """gu_fit: the text shrinks (about its pivot) to the box, never below 0.6; a plain text that still does not fit is cut with ..."""
    import re
    it = by[n]
    pt0 = it.setdefault("_pt0", it["pointSize"])
    e = nr.est(re.sub("<[^>]*>", "", s), pt0) * 1.06
    sc = min(1.0, box / e) if e else 1.0
    if sc < 0.6 and "<" not in s:
        while len(s) > 3 and nr.est(s + "...", pt0 * 0.6) * 1.06 > box:
            s = s[:-1].rstrip()
        s += "..."
    it["text"] = s
    it["pointSize"] = pt0 * max(sc, 0.6)


def _prompts(by, items):
    """nr.demo_prompts with the prev + next pair (two glyphs): items = [(key, label, on, glyph or 'a+b')], left to right."""
    x = nr.R1
    for k in range(nr.NPROMPT):
        if f"pb{k}" in by:
            by[f"pb{k}"]["visible"] = 0
    for k, (key, label, on, glyph) in enumerate(reversed(items)):
        pair = "+" in glyph
        lw = nr.est(label, nr.PROMPT_PT) * 1.06
        kw = 136 if pair else 64
        tot = 18 + kw + 22 + lw + 34
        g = by[f"pb{k}"]
        g["visible"] = 1
        g["pivotAs.x"] = float(x - tot)
        g["pivotAs.y"] = float(nr.PROMPT_Y - nr.PROMPT_H / 2)
        for s_ in ("T", "B"):
            by[f"pb{k}{s_}"]["rectSizeDelta.width"] = float(tot)
        by[f"pb{k}R"]["pivotAs.x"] = float(tot - 2)
        for s_ in "TBLR":
            by[f"pb{k}{s_}"]["color.a"] = 70 if on else 30
        g1, _, g2 = glyph.partition("+")
        by[f"pb{k}Kg"]["visible"] = 1
        by[f"pb{k}Kg"]["path"] = g1
        by[f"pb{k}Kg"]["color.a"] = 255 if on else 100
        by[f"pb{k}Kg2"]["visible"] = int(pair)
        if pair:
            by[f"pb{k}Kg2"]["path"] = g2
            by[f"pb{k}Kg2"]["color.a"] = 255 if on else 100
        by[f"pb{k}Kb"]["visible"] = 0
        by[f"pb{k}Kt"]["visible"] = 0
        tx = by[f"pb{k}Tx"]
        tx["text"] = label
        tx["pivotAs.x"] = float(18 + kw + 22)
        tx["tint.start"] = tx["tint.end"] = nr.WHITE if on else nr.DIMG
        x -= tot + 28


def _set_row(by, p, i, d, foc, hov=0):
    g = by[f"{p}Row{i}"]
    if d is None:
        g["visible"] = 0
        return
    g["visible"] = 1
    by[f"{p}Ed{i}"]["visible"] = int(bool(d.get("edge")))
    rk = d.get("rk")
    has = rk is not None
    by[f"{p}Rk{i}"]["visible"] = int(has)
    by[f"{p}Rn{i}"]["visible"] = int(has)
    if has:
        by[f"{p}Rk{i}"]["path"] = f"streaming/t2r/icons/rank-{rk}.png"
        by[f"{p}Rn{i}"]["text"] = str(d.get("wk", 0))
    nx = 36.0 + (RES if has else 0.0)
    nbox = 1100.0 - (RES if has else 0.0) - (160.0 if d.get("me") else 0.0)
    nm = by[f"{p}Nm{i}"]
    nm["pivotAs.x"] = nx
    _fit(by, f"{p}Nm{i}", d["name"], nbox)
    yu = by[f"{p}Yu{i}"]
    if d.get("me"):
        w = max(nr.est(d["name"], NAME_PT) * 1.06, 24.0 * len(d["name"].encode("utf-8")))
        w = min(w, nbox)
        yu["text"] = '<font color="#D9D86A">%s</font>' % ("TY" if d.get("pl") else "YOU")
        yu["pivotAs.x"] = nx + w + 36.0
    else:
        yu["text"] = ""
    _fit(by, f"{p}St{i}", d.get("st", ""), 1560.0 if d.get("wide") else 1000.0)
    _fit(by, f"{p}Ac{i}", d.get("ac", "") if (foc or hov) else "", 560.0)
    right = float(by[f"{p}Row{i}"]["rectSizeDelta.width"]) - 24.0
    for k, key in (("Cw", "cw"), ("Ca", "ca"), ("Cg", "cg")):
        t = d.get(key, "")
        bg, tx = by[f"{p}{k}{i}Bg"], by[f"{p}{k}{i}Tx"]
        bg["visible"] = tx["visible"] = int(bool(t))
        if t:
            w = nr.est(t, SM_PT) * 1.06 + 32
            bg["rectSizeDelta.width"] = float(w)
            bg["pivotAs.x"] = right - w
            tx["pivotAs.x"] = right - w + 16
            tx["text"] = t
            right -= w + 10
    by[f"{p}Fill{i}"]["visible"] = int(bool(foc or hov))


def demo(page, S, pl=0):
    """S: me (name, id), party = [dict(name, rk, wk, me, leader, ready, pres)] or None, searching, pmax, friends = [dict(name, rk, wk, pres, party)], invites / requests / out = [dict(name, rk, wk)],
    foc = (col, row), off, typing = text or None, hover = (col, row) or None, msg."""
    import copy as _c
    T = (lambda en, pl_: pl_ if pl else en)
    w = _c.deepcopy(page)
    by = {i["name"]: i for i in w["items"]}
    nr.demo_header(by, T("MULTIPLAYER", "TRYB WIELOOSOBOWY"), T("FRIENDS", "ZNAJOMI"))
    _fit(by, "hdMe", S["me"][0], 1300.0)
    _fit(by, "hdId", T("YOUR FRIEND ID  %s", "TWOJE ID  %s") % S["me"][1], 1400.0)

    def stat(p):
        txt = ONLINE_TXT[p][pl]
        return '<font color="#F0F0F0">%s</font>' % txt if p else txt
    party = S.get("party")
    typing = S.get("typing") is not None
    # left
    ln = len(party) + 2 if party else 0
    by["lNone"]["visible"] = int(not ln)
    by["lNone"]["text"] = T("NO PARTY YET. INVITE A FRIEND FROM THE LIST ON THE RIGHT - A PARTY QUEUES TOGETHER AND PLAYS ON ONE TEAM.",
                          "JESZCZE NIE MASZ GRUPY. ZAPROŚ ZNAJOMEGO Z LISTY PO PRAWEJ - GRUPA SZUKA MECZU RAZEM I GRA W JEDNEJ DRUŻYNIE.")
    right = ""
    if party:
        right = "%d / %d%s" % (len(party), S.get("pmax", 4), T("  |  SEARCHING", "  |  SZUKA MECZU") if S.get("searching") else "")
    nr.demo_section(by, "lSec", LX, LX + LW, T("PARTY", "GRUPA"), right)
    fcol, frow = S["foc"]
    me_leader = bool(party and any(m.get("me") and m.get("leader") for m in party))
    me_ready = bool(party and any(m.get("me") and m.get("ready") for m in party))
    for i in range(NL):
        foc = fcol == 0 and frow == i
        hov = S.get("hover") == (0, i)
        if i >= ln:
            _set_row(by, "l", i, None, 0)
            continue
        nm = len(party)
        if i < nm:
            m = party[i]
            d = dict(name=m["name"], rk=m.get("rk", 0), wk=m.get("wk", 0), st=stat(m["pres"]), me=m.get("me"), pl=pl, edge=m.get("ready") or m.get("leader") or m.get("me"),
                     ac=T("MAKE LEADER", "ZOSTAŃ LIDEREM") if me_leader and not m.get("me") else "",
                     cg=T("LEADER", "LIDER") if m.get("leader") else "" if m.get("ready") else T("NOT READY", "NIEGOTOWY"),
                     ca=T("READY", "GOTOWY") if m.get("ready") and not m.get("leader") else "")
        elif i == nm:
            if me_leader:
                d = dict(name=T("YOU START THE SEARCH", "TY ZACZYNASZ SZUKANIE"), wide=1, st=T("FIND MATCH ON THE MP MENU - THE PARTY GOES IN ONCE EVERYONE IS READY", "ZNAJDŹ MECZ W MENU MP - GRUPA IDZIE RAZEM, GDY WSZYSCY SĄ GOTOWI"))
                foc = hov = 0
            else:
                d = dict(name=T("UNREADY", "NIEGOTOWY") if me_ready else T("READY UP", "GOTOWY"), wide=1, edge=me_ready,
                         st=T("THE LEADER STARTS THE SEARCH AND THE READY PARTY GOES IN TOGETHER", "LIDER ZACZYNA SZUKANIE, A GOTOWA GRUPA IDZIE RAZEM"))
        else:
            d = dict(name=T("DISBAND PARTY", "ROZWIĄŻ GRUPĘ") if me_leader else T("LEAVE PARTY", "OPUŚĆ GRUPĘ"), wide=1,
                     st=T("THE PARTY ENDS FOR EVERYONE", "GRUPA KOŃCZY SIĘ DLA WSZYSTKICH") if me_leader else T("YOU STAY A FRIEND OF EVERYONE IN IT", "ZOSTAJESZ ZNAJOMYM WSZYSTKICH Z GRUPY"))
        _set_row(by, "l", i, d, foc, hov)
    # right: row 0 ADD FRIEND, party invites, requests, friends (online first), requests sent
    rows = [("add", None)] + [("pinv", x) for x in S.get("invites", [])] + [("req", x) for x in S.get("requests", [])] + \
           [("fr", x) for x in S.get("friends", [])] + [("out", x) for x in S.get("out", [])]
    off = S.get("off", 0)
    on = sum(1 for x in S.get("friends", []) if x["pres"] > 0)
    nr.demo_section(by, "rSec", RX, RX + RW, T("FRIENDS", "ZNAJOMI"), T("%d ONLINE  |  %d FRIENDS", "%d ONLINE  |  %d ZNAJOMYCH") % (on, len(S.get("friends", []))))
    for i in range(NR):
        idx = off + i
        foc = fcol == 1 and frow == idx
        hov = S.get("hover") == (1, i)
        if idx >= len(rows):
            _set_row(by, "r", i, None, 0)
            continue
        kind, x = rows[idx]
        if kind == "add":
            d = None if typing else dict(name=T("ADD A FRIEND", "DODAJ ZNAJOMEGO"), st=T("BY PLAYER NAME OR STEAM ID", "PO NAZWIE GRACZA LUB ID STEAM"), ac=T("TYPE A NAME", "WPISZ NAZWĘ"))
        elif kind == "pinv":
            d = dict(name=x["name"], rk=x.get("rk", 0), wk=x.get("wk", 0), st=T("INVITED YOU TO A PARTY", "ZAPRASZA CIĘ DO GRUPY"), cw=T("INVITE", "ZAPROSZENIE"), ac=T("JOIN PARTY", "DOŁĄCZ DO GRUPY"))
        elif kind == "req":
            d = dict(name=x["name"], rk=x.get("rk", 0), wk=x.get("wk", 0), st=T("WANTS TO BE YOUR FRIEND", "CHCE ZOSTAĆ TWOIM ZNAJOMYM"), cw=T("REQUEST", "PROŚBA"), ac=T("ACCEPT", "PRZYJMIJ"))
        elif kind == "fr":
            d = dict(name=x["name"], rk=x.get("rk", 0), wk=x.get("wk", 0), st=stat(x["pres"]), cg=T("IN YOUR PARTY", "W TWOJEJ GRUPIE") if x.get("party") else "",
                     ac=T("INVITE TO PARTY", "ZAPROŚ DO GRUPY") if x["pres"] > 0 and not x.get("party") else "")
        else:
            d = dict(name=x["name"], rk=x.get("rk", 0), wk=x.get("wk", 0), st=T("REQUEST SENT - WAITING FOR AN ANSWER", "ZAPROSZENIE WYSŁANE - CZEKA NA ODPOWIEDŹ"))
        _set_row(by, "r", i, d, foc, hov)
    more = len(rows) - (off + NR)
    by["rMore"]["text"] = (T("+ %d MORE", "+ JESZCZE %d") % more) if more > 0 else ""
    sc = len(rows) > NR
    by["rScT"]["visible"] = by["rScH"]["visible"] = int(sc)
    if sc:
        y0, y1 = RY0, RY0 + RDY * NR
        by["rScH"]["pivotAs.y"] = float(y0 + (y1 - y0) * off / len(rows))
        by["rScH"]["rectSizeDelta.height"] = float(max(8.0, (y1 - y0) * NR / len(rows)))
    # the field
    if typing:
        t = S["typing"]
        by["inp"]["visible"] = 1
        by["inpLbl"]["text"] = T("ADD A FRIEND  -  PLAYER NAME OR STEAM ID", "DODAJ ZNAJOMEGO  -  NAZWA GRACZA LUB ID STEAM")
        by["inpCnt"]["text"] = "%d / 31" % len(t)
        by["inpKey"]["text"] = T("ENTER SENDS", "ENTER WYSYŁA")
        by["inpTx"]["text"] = t + '<font color="#F0F0F0">|</font>'
        by["inpPh"]["text"] = T("TYPE A NAME OR A STEAM ID", "WPISZ NAZWĘ LUB ID STEAM") if not t else ""
    # the focus outline
    if not typing:
        if fcol == 1:
            nr.demo_frame(by, "frFo", RX, RY0 + RDY * (frow - off), RW, RH)
        else:
            nr.demo_frame(by, "frFo", LX, LY[frow], LW, RH)
    # prompts
    pri = sec = ""
    if fcol == 1 and frow < len(rows):
        k_, x_ = rows[frow]
        pri = {"add": T("ADD A FRIEND", "DODAJ ZNAJOMEGO"), "pinv": T("JOIN PARTY", "DOŁĄCZ DO GRUPY"), "req": T("ACCEPT", "PRZYJMIJ"),
               "fr": T("INVITE TO PARTY", "ZAPROŚ DO GRUPY") if k_ == "fr" and x_["pres"] > 0 and not x_.get("party") else "", "out": ""}[k_]
        sec = {"add": "", "pinv": T("DECLINE", "ODRZUĆ"), "req": T("DECLINE", "ODRZUĆ"), "fr": T("REMOVE FRIEND", "USUŃ ZNAJOMEGO"), "out": T("CANCEL REQUEST", "ANULUJ ZAPROSZENIE")}[k_]
    elif fcol == 0 and party:
        if frow < len(party) and me_leader and not party[frow].get("me"):
            pri, sec = T("MAKE LEADER", "ZOSTAŃ LIDEREM"), T("KICK", "WYRZUĆ")
        elif frow == len(party):
            pri = "" if me_leader else (T("UNREADY", "NIEGOTOWY") if me_ready else T("READY UP", "GOTOWY"))
        elif frow == len(party) + 1:
            pri = T("DISBAND PARTY", "ROZWIĄŻ GRUPĘ") if me_leader else T("LEAVE PARTY", "OPUŚĆ GRUPĘ")
    if typing:
        pri = sec = ""
    _prompts(by, [("menu:select", T("SEND", "WYŚLIJ") if typing else (pri or T("SELECT", "WYBIERZ")), typing or bool(pri), "menu:select"),
                  ("menu:action", sec or T("ACTION", "AKCJA"), bool(sec), "menu:action"),
                  ("menu:prev+menu:next", T("SWITCH LIST", "ZMIEŃ LISTĘ"), bool(ln) and not typing, "menu:prev+menu:next"),
                  ("menu:back", T("BACK", "WSTECZ"), True, "menu:back")])
    by["msgTx"]["text"] = S.get("msg", "")
    key = (T("ENTER SEND     ESC CANCEL     CTRL+V PASTE     LEFT / RIGHT / HOME / END MOVE     BACKSPACE / DELETE ERASE",
             "ENTER WYŚLIJ     ESC ANULUJ     CTRL+V WKLEJ     STRZAŁKI / HOME / END PRZESUWAJĄ     BACKSPACE / DELETE KASUJE") if typing else
           T("CLICK OR W / S SELECT     ENTER OR THE PROMPT BELOW DOES IT     X SECOND ACTION     R READY     L LEAVE PARTY     TAB SWITCH LIST     P OR ESC CLOSE",
             "KLIKNIJ LUB W / S ZAZNACZ     ENTER LUB PRZYCISK NA DOLE WYKONUJE     X DRUGA AKCJA     R GOTOWY     L OPUŚĆ GRUPĘ     TAB ZMIEŃ LISTĘ     P LUB ESC ZAMKNIJ"))
    _fit(by, "keyTx", key, 3500.0)
    _fit(by, "msgTx", S.get("msg", ""), 3500.0)
    return w


def states():
    friends = [dict(name="Bo", rk=1, wk=4, pres=2, party=1), dict(name="Ilsa", rk=2, wk=9, pres=3), dict(name="Mara", rk=0, wk=1, pres=4),
               dict(name="Kit", rk=3, wk=12, pres=1), dict(name="Rook", rk=0, wk=0, pres=0), dict(name="Tal", rk=4, wk=21, pres=0)]
    party3 = [dict(name="Vex", rk=2, wk=7, me=1, leader=1, ready=1, pres=2), dict(name="Bo", rk=1, wk=4, ready=1, pres=2), dict(name="June", rk=0, wk=2, ready=0, pres=2)]
    base = dict(me=("Vex", "7656119800000000"), friends=friends, invites=[dict(name="Wren", rk=1, wk=3)], requests=[dict(name="Dax", rk=0, wk=0)], out=[dict(name="Pia", rk=0, wk=0)])
    st = {}
    st["party"] = dict(base, party=party3, foc=(0, 1), msg="PARTY INVITE SENT")
    member = [dict(name="Bo", rk=1, wk=4, leader=1, ready=1, pres=2), dict(name="Vex", rk=2, wk=7, me=1, ready=1, pres=2), dict(name="June", rk=0, wk=2, ready=0, pres=3)]
    st["party-member-friends"] = dict(base, party=member, foc=(1, 3), searching=1)
    st["typing"] = dict(base, party=party3, foc=(1, 0), typing="Rook_Ma")
    st["empty"] = dict(base, party=None, foc=(1, 2))
    st["scroll"] = dict(base, party=party3, foc=(1, 8), off=2, friends=friends + [dict(name="Nora", rk=1, wk=5, pres=0), dict(name="Sol", rk=0, wk=1, pres=0)])
    st["long-pl"] = dict(me=("Aleksandra-Wiktoria_Kowalczyk-Nowak", "7656119800000000"), foc=(1, 3), msg="NIE ZNALEZIONO GRACZA O TEJ NAZWIE LUB ID STEAM",
                         party=[dict(name="Aleksandra-Wiktoria_Kowalczyk-Nowak", rk=2, wk=7, me=1, leader=1, ready=1, pres=3), dict(name="Zażółć_Gęślą_Jaźń_Wojciechowski", rk=1, wk=4, ready=1, pres=2),
                                dict(name="Przemysław Krzysztofowicz", rk=0, wk=2, ready=0, pres=4)],
                         invites=[dict(name="Bartłomiej Świątkowski-Wiśniewski", rk=1, wk=3)], requests=[dict(name="Małgorzata Żurawska", rk=0, wk=0)],
                         friends=[dict(name="Wojciech Szczęśniak-Kowalewski", rk=2, wk=40, pres=3, party=1), dict(name="Ćma", rk=0, wk=1, pres=0)], out=[dict(name="Józef Ślusarczyk", rk=0, wk=0)])
    return st


def preview(wdir, out_dir):
    import sys
    import tempfile
    import widget_preview
    main = json.load(open(os.path.join(wdir, "to1", "main-menu.widget.json"), encoding="utf-8"))
    page = build_page(main)
    for it in page["items"]:
        if it["name"] == "bgBlur":
            it["visible"] = 0                         # (the engine's live blur: the preview draws the blurred launcher art under the page instead)
    here = os.path.dirname(os.path.abspath(__file__))
    sys.path.insert(0, os.path.join(here, ".."))
    sys.path.insert(0, os.path.join(here, "..", "models"))
    import make_icons
    import real_icons
    import rank_icons
    icd = os.path.join(tempfile.gettempdir(), "t2r-friends13-icons")
    os.makedirs(icd, exist_ok=True)
    rank_icons.main(icd, make_icons.save_variants)
    real_icons.MOD_DIRS.append(icd)
    os.makedirs(out_dir, exist_ok=True)
    bg = nr.preview_bg(os.path.join(tempfile.gettempdir(), "t2r-nr-bg.png"))
    for name, S in states().items():
        tmp = os.path.join(tempfile.gettempdir(), "t2r-friends13-prev.widget.json")
        json.dump(demo(page, S, 1 if name == "long-pl" else 0), open(tmp, "w", encoding="utf-8"))
        print(widget_preview.render(tmp, os.path.join(out_dir, "friends13-" + name + ".png"), scale=0.5, bg=bg))
    print("friends13: %d widgets (gui2 limit 1024)" % len(page["items"]))


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
    preview(src, out)
