"""to1/name-entry: CHANGE NAME page (wishlist 8), added to gui2-widgets.pak by widgets_patch.patch_widgets.

A text-entry page pushed by t2r-ext feature_names (CHANGE NAME button on MULTIPLAYER > OPTIONS), in the CLAN / FRIENDS / GEAR UP
family: blur + dark + panel backdrop, small label line + big title + rule, two field cards (NAME 1..15, CLAN TAG 0..5;
the focused one framed + washed like a clan row, blinking cursor), a "[TAG] name" preview card, a status line, footer prompts BACK / CONFIRM
(device-aware glyphs, mouse rects). There is no native text-entry dialog in the game's DC scripts / widgets
(the PC build takes names from Steam), so t2r-ext reads the keyboard itself (GetAsyncKeyState).
Widget space is 3840 x 2160, y down. python names_widgets.py <extracted widget dir> <out dir> renders
a preview."""
import copy
import json
import os
import t2guid

from clan_widgets import Builder, _templates, PM_TEXT, PM_DIM, RED_TEXT
from matchflow_widgets import TEXT, CREAM

PAGE = "name-entry"
PANEL = "streaming/t2r/clan/gearup-panel.png"       # the scratched dark backdrop of GEAR UP / CLAN / FRIENDS (ship.py)
TITLE = 0xFFD8D4CC
LABEL = 0xFFB4B4B4
DIM = 0xFF8D897B
X0, X1 = 300, 3540
CARD_A, EDGE_A, FOCUS_A, HILITE_A, HIT_A = 150, 46, 190, 16, 1
NY, NH = 560, 190                                    # the two field cards
NX, NW = 300, 2060                                   # NAME
TX, TW = 2480, 1060                                  # CLAN TAG
PY, PH = 840, 230                                    # the "[TAG] name" preview card
MSG_Y, KEY_Y = 1690, 1770


def tlm(x, y, w, h, right=0):
    """Box with its pivot at the left (right=1: right) middle (the family's helper, as gearup13_widgets.tlm)."""
    return {"anchorMinN.x": 0.0, "anchorMinN.y": 0.0, "anchorMaxN.x": 0.0, "anchorMaxN.y": 0.0,
            "pivotN.x": float(right), "pivotN.y": 0.5, "pivotAs.x": float(x + (w if right else 0)), "pivotAs.y": float(y + h / 2.0),
            "rectSizeDelta.width": float(w), "rectSizeDelta.height": float(h)}


def card(b, p, g, x, y, w, h, focus=True):
    """A clan-row card: dark translucent body, thin edge, cream band on the left; Fill = hover / focus wash, Frame = focus frame
    (both hidden, t2r-ext shows them); Hit = the mouse rect (t2r-ext hit-tests it)."""
    c = b.group(p + "Row", g, b.tl(x, y, w, h))["guid"]
    b.rect(p + "Card", c, b.fill(), 0xFF000000, CARD_A)
    b.frame(p + "Edge", c, b.fill(), 0xFFFFFFFF, EDGE_A, 2.0)
    b.rect(p + "Fill", c, b.fill(), 0xFFFFFFFF, HILITE_A, visible=0)
    if focus:
        b.frame(p + "Frame", c, b.fill(), 0xFFFFFFFF, FOCUS_A, 3.0, visible=0)
    b.rect(p + "Bd", c, b.tl(0, 0, 8, h), CREAM, 230)
    return c


def build_page(main):
    """to1/name-entry.widget.json content."""
    t, root0, anim0 = _templates(main)
    b = Builder(t)
    root = copy.deepcopy(root0); root.update(guid=t2guid.guid())
    anim = copy.deepcopy(anim0); anim.update(guid=t2guid.guid(), parent=root["guid"])
    b.items += [root, anim]
    a = anim["guid"]
    b.image("bgBlur", a, b.bleed(), "general-textures/blur-background.png", 0xFFFFFFFF, 255)
    b.rect("bgDark", a, b.bleed(), 0xFF0B0C0D, 90)
    b.image("bgPanel", a, b.tl(0, 0, 3840, 2160), PANEL, 0xFFFFFFFF, 255)
    # header: small label line + big title + the rule (as CLAN / FRIENDS)
    hd = b.group("hd", a, b.tl(0, 0, 3840, 2160))["guid"]
    b.text("hdKick", hd, b.tl(X0, 90, 1600, 44), "MULTIPLAYER OPTIONS", 32, LABEL, face="Alternate", tracking=8)
    b.text("hdTitle", hd, b.tl(X0 - 4, 126, 1800, 150), "CHANGE NAME", 104, TITLE, tracking=4)
    b.text("hdInfo", hd, tlm(1740, 190, 1800, 46, right=1), "SHOWN IN THE LOBBY, ON THE SCOREBOARD AND IN THE KILL FEED", 28, DIM, face="Alternate", align=2, tracking=6)
    b.line("hdRule", hd, X0, 392, X1, 392, 0xFFFFFFFF, 130, 2.0)
    e = b.group("entry", a, b.tl(0, 0, 3840, 2160))["guid"]
    # the two fields
    for p, lbl, x, w, cnt in (("name", "NAME", NX, NW, "0/15"), ("tag", "CLAN TAG", TX, TW, "0/5")):
        c = card(b, p, e, x, NY, w, NH)
        b.text(p + "Lbl", c, tlm(36, 16, w - 400, 36), lbl, 28, DIM, face="Alternate", tracking=6)
        b.text(p + "Count", c, tlm(w - 260, 16, 224, 36, right=1), cnt, 28, DIM, face="Alternate", align=2, tracking=6)
        b.text(p + "Val", c, tlm(36, 64, w - 72, 110), "", 72, TEXT, tracking=3)
        b.rect(p + "Hit", c, b.fill(), 0xFFFFFFFF, HIT_A)
    b.text("tagHelp", e, tlm(TX, NY + NH + 14, TW, 40), "UP TO 5 LETTERS OR DIGITS", 28, DIM, face="Alternate", tracking=6)
    b.text("nameHelp", e, tlm(NX, NY + NH + 14, NW, 40), "1 TO 15 CHARACTERS", 28, DIM, face="Alternate", tracking=6)
    # live preview in the plate style: "[TAG] name"
    c = card(b, "prev", e, X0, PY, X1 - X0, PH, focus=False)
    b.text("prevLbl", c, tlm(36, 16, 1400, 36), "YOU WILL APPEAR AS", 28, DIM, face="Alternate", tracking=6)
    b.text("prevVal", c, tlm(36, 62, X1 - X0 - 72, 150), "", 96, TEXT, tracking=4)
    # status + key hint lines
    b.text("status", a, tlm(X0, MSG_Y, X1 - X0, 60), "", 34, TEXT, face="Alternate", tracking=6)
    b.text("statusErr", a, tlm(X0, MSG_Y, X1 - X0, 60), "", 34, RED_TEXT, face="Alternate", tracking=6)     # errors (t2r-ext fills one of the two)
    b.text("keyTx", a, tlm(X0, KEY_Y, X1 - X0, 44), "TYPE TO EDIT     TAB / UP / DOWN / D-PAD  SWITCH FIELD     BACKSPACE  DELETE     CLICK A FIELD", 28, DIM, face="Alternate", tracking=6)
    # prompts (the match-flow footer): BACK, CONFIRM (device-aware glyphs, mouse rects)
    b.image("pBackIc", a, b.tl(270, 1898, 56, 56), "menu:back", 0xFFFFFFFF)
    b.text("pBackTx", a, tlm(350, 1890, 400, 70), "BACK", 46, PM_TEXT, tracking=4)
    b.image("pSelIc", a, b.tl(760, 1898, 56, 56), "menu:select", 0xFFFFFFFF)
    b.text("pSelTx", a, tlm(840, 1890, 640, 70), "CONFIRM", 46, PM_TEXT, tracking=4)
    b.rect("pBackHit", a, b.tl(250, 1800, 480, 200), 0xFFFFFFFF, HIT_A)
    b.rect("pSelHit", a, b.tl(740, 1800, 640, 200), 0xFFFFFFFF, HIT_A)
    w = {k: copy.deepcopy(v) for k, v in main.items() if k != "items"}
    w["items"] = b.items
    return w


BOW_ROW = "selectorBowAimArc"
UI_ROW = "selectorDisableMpUi"
NAME_ROW = "buttonChangeName"
OLD_ROWS = ("changeNameBack", "changeNameHov", "changeNameHint", "bowArcBack", "bowArcHov", "bowArcText")


def add_options_hint(wdir, main):
    """to1/options-menu-multiplayer (MULTIPLAYER > OPTIONS): the stock menu builds its rows as Reference widgets in the `contents`
    Menu2::Container (vertical flow, focusWrap), e.g. selectorRadarMode = menu/components/selector-default.widget with
    cipherId (label) and tags.dataSource "to1-radar-mode" (the data source is created / answered in winmm). Two rows are
    added the same way, right after the last selector, so they sit in the same list (arrow keys / d-pad, Enter / A, left /
    right on the selector, mouse hover + click: all native):
      - selectorBowAimArc: a selector copy, label TO1_BOW_ARC, dataSource "to1-bow-arc" (t2r-ext install_bow_options)
      - selectorDisableMpUi: a selector copy, label TO1_MP_UI_OFF, dataSource "to1-mp-ui-off" (t2r-ext: hides every MP HUD element)
      - buttonChangeName: a button-default Reference (as page-options-v3's buttonDifficulty), label TO1_CHANGE_NAME,
        tags.action "push-fullscreen to1/name-entry" (the engine pushes our change-name page, as the main menu's buttons push theirs)
    The old mouse-only changeName* / bowArc* widgets are removed. Texts: dc_data_patches.patch_text_ciphers. Returns 1 if changed."""
    path = os.path.join(wdir, "to1", "options-menu-multiplayer.widget.json")
    if not os.path.exists(path):
        return 0
    w = json.load(open(path, encoding="utf-8"))
    items = w["items"]
    names = {i["name"] for i in items}
    if BOW_ROW in names and UI_ROW in names and NAME_ROW in names and not names.intersection(OLD_ROWS):
        return 0
    items[:] = [i for i in items if i["name"] not in OLD_ROWS + (BOW_ROW, UI_ROW, NAME_ROW)]
    last = next(k for k, i in enumerate(items) if i["name"] == "selectorRadarMode")
    sel = items[last]
    bow = copy.deepcopy(sel)
    bow.update(guid=t2guid.guid(), name=BOW_ROW, cipherId="TO1_BOW_ARC")
    bow["tags"] = {"dataSource": "to1-bow-arc"}
    ui = copy.deepcopy(sel)
    ui.update(guid=t2guid.guid(), name=UI_ROW, cipherId="TO1_MP_UI_OFF")
    ui["tags"] = {"dataSource": "to1-mp-ui-off"}
    btn = copy.deepcopy(sel)
    btn.update(guid=t2guid.guid(), name=NAME_ROW, cipherId="TO1_CHANGE_NAME", source="menu/components/button-default.widget")
    btn["rectSizeDelta.height"] = 56.0
    btn["tags"] = {"action": "push-fullscreen to1/name-entry", "allowTtsOnInvisibleHack": "true"}
    items[last + 1:last + 1] = [bow, ui, btn]
    json.dump(w, open(path, "w", encoding="utf-8"), indent=4)
    return 1


def add_names_page(wdir):
    main = json.load(open(os.path.join(wdir, "to1", "main-menu.widget.json"), encoding="utf-8"))
    json.dump(build_page(main), open(os.path.join(wdir, "to1", PAGE + ".widget.json"), "w", encoding="utf-8"), indent=4)
    return 1 + add_options_hint(wdir, main)


def demo(page, name="Big Joel", tag="WLF", focus=0, status="", hover=None, err=0):
    w = copy.deepcopy(page)
    by = {i["name"]: i for i in w["items"]}
    by["nameVal"]["text"] = name + ("_" if focus == 0 else "")
    by["tagVal"]["text"] = tag + ("_" if focus == 1 else "")
    by["nameCount"]["text"] = "%d/15" % len(name)
    by["tagCount"]["text"] = "%d/5" % len(tag)
    for p, k in (("name", 0), ("tag", 1)):
        by[p + "Frame"]["visible"] = int(focus == k)
        by[p + "Fill"]["visible"] = int(focus == k or hover == p)
    by["prevVal"]["text"] = ("[%s] %s" % (tag, name)) if tag else name
    by["statusErr" if err else "status"]["text"] = status.upper()
    return w


def preview(wdir, out_dir):
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
    for nm, kw in (("after-0", dict()), ("after-1", dict(focus=1, hover="name", status="Tag: letters and digits only", err=1)), ("after-2", dict(status="Saved. Everyone sees it now."))):
        tmp = os.path.join(tempfile.gettempdir(), "t2r-" + nm + ".widget.json")
        json.dump(demo(page, **kw), open(tmp, "w", encoding="utf-8"))
        print(widget_preview.render(tmp, os.path.join(out_dir, nm + ".png")))


if __name__ == "__main__":
    import sys
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    preview(sys.argv[1], sys.argv[2])
