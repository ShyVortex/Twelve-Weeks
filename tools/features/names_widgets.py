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

from clan_widgets import Builder, _templates, RED_TEXT
import nr_style as nr

PAGE = "name-entry"
# Redesign: the No Return frame (nr_style.frame: blur + dim + vignette, breadcrumb MULTIPLAYER | CHANGE NAME, boxed prompts) like CLAN /
# PLAYER STATS / FRIENDS. Field cards = flat tiles (TILE fill, white focus outline, faint hover wash), grey small-caps labels, white values.
X0, X1 = nr.L0, nr.R1
NY, NH = 560, 200                                    # the two field tiles
NX, NW = X0, 2380                                    # NAME
TX = NX + NW + 60                                    # CLAN TAG
TW = X1 - TX
SEC_Y = 470                                          # YOUR NAME section row
PSEC_Y = 960                                         # YOU WILL APPEAR AS section row
PY, PH = 1010, 200                                   # the "[TAG] name" preview tile
MSG_Y, KEY_Y = 1790, 1868                            # status + key hint lines (over the prompt row at nr.PROMPT_Y)
LBL_PT, VAL_PT, PREV_PT = nr.pt(18), nr.pt(36), nr.pt(46)
WASH_A, HIT_A = 12, 1


def card(b, p, g, x, y, w, h, focus=True):
    """A flat tile: <p>Card dim fill, <p>Fill hover / focus wash, <p>Frame the white focus outline (a group of 4 rects; t2r-ext shows it),
    <p>Hit the mouse rect (added by the caller)."""
    c = b.group(p + "Row", g, b.tl(x, y, w, h))["guid"]
    b.rect(p + "Card", c, b.fill(), nr.TILE, nr.TILE_A)
    b.rect(p + "Fill", c, b.fill(), nr.WHITE, WASH_A, visible=0)
    if focus:
        fo = b.group(p + "Frame", c, b.fill(), visible=0)["guid"]
        b.rect(p + "FoT", fo, b.tl(0, 0, w, 4), nr.WHITE, 255)
        b.rect(p + "FoB", fo, b.tl(0, h - 4, w, 4), nr.WHITE, 255)
        b.rect(p + "FoL", fo, b.tl(0, 0, 4, h), nr.WHITE, 255)
        b.rect(p + "FoR", fo, b.tl(w - 4, 0, 4, h), nr.WHITE, 255)
    return c


def build_page(main):
    """to1/name-entry.widget.json content."""
    t, root0, anim0 = _templates(main)
    b = Builder(t)
    root = copy.deepcopy(root0); root.update(guid=t2guid.guid())
    anim = copy.deepcopy(anim0); anim.update(guid=t2guid.guid(), parent=root["guid"])
    b.items += [root, anim]
    a = anim["guid"]
    nr.frame(b, a, "MULTIPLAYER", "CHANGE NAME", prompts=2)
    b.text("hdInfo", a, nr.lm(X0, 290 - 28, 2600, 56), "SHOWN IN THE LOBBY, ON THE SCOREBOARD AND IN THE KILL FEED", nr.pt(20), nr.GREY, tracking=3)
    e = b.group("entry", a, b.tl(0, 0, 3840, 2160))["guid"]
    nr.section(b, e, "secNm", X0, X1, SEC_Y, "YOUR NAME")
    # the two fields
    for p, lbl, x, w, cnt in (("name", "NAME", NX, NW, "0/15"), ("tag", "CLAN TAG", TX, TW, "0/5")):
        c = card(b, p, e, x, NY, w, NH)
        b.text(p + "Lbl", c, nr.lm(36, 22, w - 400, 44), lbl, LBL_PT, nr.GREY, tracking=3)
        b.text(p + "Count", c, nr.lm(w - 300, 22, 264, 44, right=1), cnt, LBL_PT, nr.GREY, align=2, tracking=3)
        b.text(p + "Val", c, nr.lm(36, 78, w - 72, 100), "", VAL_PT, nr.WHITE, tracking=3)
        b.rect(p + "Hit", c, b.fill(), nr.WHITE, HIT_A)
    b.text("nameHelp", e, nr.lm(NX, NY + NH + 16, NW, 44), "1 TO 15 CHARACTERS", LBL_PT, nr.GREY, tracking=3)
    b.text("tagHelp", e, nr.lm(TX, NY + NH + 16, TW, 44), "UP TO 5 LETTERS OR DIGITS", LBL_PT, nr.GREY, tracking=3)
    # live preview: "[TAG] name"
    nr.section(b, e, "secPv", X0, X1, PSEC_Y, "YOU WILL APPEAR AS")
    c = card(b, "prev", e, X0, PY, X1 - X0, PH, focus=False)
    b.text("prevVal", c, nr.lm(36, 0, X1 - X0 - 72, PH), "", PREV_PT, nr.WHITE, tracking=3)
    # status + key hint lines
    b.text("status", a, nr.lm(X0, MSG_Y - 30, X1 - X0, 60), "", nr.pt(22), nr.WHITE, tracking=3)
    b.text("statusErr", a, nr.lm(X0, MSG_Y - 30, X1 - X0, 60), "", nr.pt(22), RED_TEXT, tracking=3)     # errors (t2r-ext fills one of the two)
    b.text("keyTx", a, nr.lm(X0, KEY_Y - 24, 2700, 48), "TYPE TO EDIT     TAB / UP / DOWN / D-PAD  SWITCH FIELD     BACKSPACE  DELETE     CLICK A FIELD",
           nr.pt(17), nr.GREY, tracking=3)
    w = {k: copy.deepcopy(v) for k, v in main.items() if k != "items"}
    w["items"] = b.items
    return w


BOW_ROW = "selectorBowAimArc"
UI_ROW = "selectorDisableMpUi"
NAME_ROW = "buttonChangeName"
# DISABLE MP UI in the stock OPTIONS > HUD / SUBTITLES design: the parent row stays a selector-default, its child rows are
# menu/components/selector-dependent.widget (the indented row page-options-subtitles uses under SUBTITLES) - t2r-ext mpui_sync / mpui_child_tick
UI_SUBROWS = (("selectorMpRadarOff", "TO1_MP_RADAR_OFF", "to1-mp-radar-off"), ("selectorMpLivesOff", "TO1_MP_LIVES_OFF", "to1-mp-lives-off"),
              ("selectorMpSuppliesOff", "TO1_MP_SUPPLIES_OFF", "to1-mp-supplies-off"),
              ("selectorMpChatOff", "TO1_MP_CHAT_OFF", "to1-mp-chat-off"))     # chat: DISABLE CHAT (t2r-ext g_mp_hide[3]; the parent row does not set it)
UI_SUBNAMES = tuple(r[0] for r in UI_SUBROWS)
# two MOCKUP rows for the dedicated-server matchmaking, shown greyed out and locked at ANY (t2r-ext bds_state_hook answers
# state 2 = disabled for their data sources). menu/components/selector-default-show-disabled.widget = the stock row of Permadeath /
# Difficulty on the in-game gameplay options page: its animation set (menu-item-animations-show) keeps the value text visible and greyed
# while disabled and shows the lock (the plain selector-default fades the value out when disabled)
MOCK_ROWS = (("selectorRegionPref", "TO1_REGION_PREF", "to1-region-pref"), ("selectorInputPref", "TO1_INPUT_PREF", "to1-input-pref"))
MOCK_NAMES = tuple(r[0] for r in MOCK_ROWS)
# PART I MAPS (DEFAULT / ALWAYS): a WORKING row after the mockups, same widget (selector-default-show-disabled): enabled it is a plain selector,
# t2r-ext greys it out (state 2) and holds it at DEFAULT while this client has no Part I maps installed. ALWAYS = the Part I maps are always in
# this player's vote and the matchmaker only groups ALWAYS players together (daemon: 0xC8 flags byte).
P1_ROWS = (("selectorPartIMaps", "TO1_P1_MAPS", "to1-p1-pref"),)
P1_NAMES = tuple(r[0] for r in P1_ROWS)
OLD_ROWS =("changeNameBack", "changeNameHov", "changeNameHint", "bowArcBack", "bowArcHov", "bowArcText")


def add_options_hint(wdir, main):
    """to1/options-menu-multiplayer (MULTIPLAYER > OPTIONS): spec built its rows as Reference widgets in the `contents`
    Menu2::Container (vertical flow, focusWrap), e.g. selectorRadarMode = menu/components/selector-default.widget with
    cipherId (label) and tags.dataSource "to1-radar-mode" (the data source is created / answered in winmm). Two rows are
    added the same way, right after the last selector, so they sit in the same list (arrow keys / d-pad, Enter / A, left /
    right on the selector, mouse hover + click: all native):
      - selectorBowAimArc: a selector copy, label TO1_BOW_ARC, dataSource "to1-bow-arc" (t2r-ext install_bow_options)
      - selectorDisableMpUi: a selector copy, label TO1_MP_UI_OFF, dataSource "to1-mp-ui-off" (t2r-ext: hides every MP HUD element)
      - under it three selector-dependent rows DISABLE RADAR / DISABLE LIVES COUNTER / DISABLE SUPPLIES / PARTS (UI_SUBROWS): the parent
        sets all three, each hides only its element
      - buttonChangeName: a button-default Reference (as page-options-v3's buttonDifficulty), label TO1_CHANGE_NAME,
        tags.action "push-fullscreen to1/name-entry" (the engine pushes our change-name page, as the main menu's buttons push theirs)
      - last (MOCKUP until dedicated servers): REGION PREFERENCE (ANY / NORTH AMERICA / EUROPE) and INPUT PREFERENCE
        (ANY / CONTROLLER / KEYBOARD AND MOUSE), MOCK_ROWS, greyed out and locked at ANY by t2r-ext
      - then PART I MAPS (DEFAULT / ALWAYS), P1_ROWS: a working row (greyed out only when no Part I maps are installed)
    `contents` gets the summed row height and `list` the stock long-page height (page-options-v3-gameplay: 1650) once the rows no
    longer fit the subtitles-page size spec copied (766 / 1043), so the scroll container sees every row.
    The old mouse-only changeName* / bowArc* widgets are removed. Texts: dc_data_patches.patch_text_ciphers. Returns 1 if changed."""
    path = os.path.join(wdir, "to1", "options-menu-multiplayer.widget.json")
    if not os.path.exists(path):
        return 0
    w = json.load(open(path, encoding="utf-8"))
    items = w["items"]
    names = {i["name"] for i in items}
    if (BOW_ROW in names and UI_ROW in names and NAME_ROW in names and names.issuperset(UI_SUBNAMES + MOCK_NAMES + P1_NAMES)
            and not names.intersection(OLD_ROWS)):
        return 0
    items[:] = [i for i in items if i["name"] not in OLD_ROWS + (BOW_ROW, UI_ROW, NAME_ROW) + UI_SUBNAMES + MOCK_NAMES + P1_NAMES]
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
    subs = []
    for nm, ci, ds in UI_SUBROWS:
        r = copy.deepcopy(sel)
        r.update(guid=t2guid.guid(), name=nm, cipherId=ci, source="menu/components/selector-dependent.widget")
        r["tags"] = {"dataSource": ds}
        subs.append(r)
    mocks = []
    for nm, ci, ds in MOCK_ROWS:
        r = copy.deepcopy(sel)
        r.update(guid=t2guid.guid(), name=nm, cipherId=ci, source="menu/components/selector-default-show-disabled.widget")
        r["rectSizeDelta.height"] = 57.0           # (that widget's own height)
        r["tags"] = {"dataSource": ds}
        mocks.append(r)
    for nm, ci, ds in P1_ROWS:
        r = copy.deepcopy(sel)
        r.update(guid=t2guid.guid(), name=nm, cipherId=ci, source="menu/components/selector-default-show-disabled.widget")
        r["rectSizeDelta.height"] = 57.0
        r["tags"] = {"dataSource": ds}
        mocks.append(r)
    items[last + 1:last + 1] = [bow, ui] + subs + [btn] + mocks
    fit_list(items)
    json.dump(w, open(path, "w", encoding="utf-8"), indent=4)
    return 1


def fit_list(items):
    """`contents` height = its rows + the flow spacing (as every stock options page sizes it); `list` (the scroll container) at the stock
    long-page height 1650 when the rows outgrow the 1043 one (page-options-v3-gameplay / -audio-all: list 1650, same position)."""
    by = {i["name"]: i for i in items}
    c, lst = by.get("contents"), by.get("list")
    if not c or not lst:
        return
    rows = [i for i in items if i.get("parent") == c["guid"]]
    h = sum(float(i.get("rectSizeDelta.height", 0.0)) for i in rows) + float(c.get("flowSpacing", 0.0)) * max(len(rows) - 1, 0)
    c["rectSizeDelta.height"] = max(float(c.get("rectSizeDelta.height", 0.0)), h)
    top = float(c.get("pivotAs.y", 0.0))
    if top + c["rectSizeDelta.height"] > float(lst.get("rectSizeDelta.height", 0.0)):
        lst["rectSizeDelta.height"] = max(float(lst["rectSizeDelta.height"]), 1650.0)


def add_names_page(wdir):
    main = json.load(open(os.path.join(wdir, "to1", "main-menu.widget.json"), encoding="utf-8"))
    json.dump(build_page(main), open(os.path.join(wdir, "to1", PAGE + ".widget.json"), "w", encoding="utf-8"), indent=4)
    return 1 + add_options_hint(wdir, main)


def demo(page, name="Big Joel", tag="WLF", focus=0, status="", hover=None, err=0, prompts=None):
    w = copy.deepcopy(page)
    by = {i["name"]: i for i in w["items"]}
    nr.demo_header(by, "MULTIPLAYER", "CHANGE NAME")
    nr.demo_section(by, "secNm", X0, X1, "YOUR NAME")
    nr.demo_section(by, "secPv", X0, X1, "YOU WILL APPEAR AS")
    nr.demo_prompts(by, prompts or [("", "BACK", 1, "menu:back"), ("", "CONFIRM", 1, "menu:select")])
    by["nameVal"]["text"] = name + ("_" if focus == 0 else "")
    by["tagVal"]["text"] = tag + ("_" if focus == 1 else "")
    by["nameCount"]["text"] = "%d/15" % len(name)
    by["tagCount"]["text"] = "%d/5" % len(tag)
    for p, k in (("name", 0), ("tag", 1)):
        by[p + "Frame"]["visible"] = int(focus == k)
        by[p + "Fill"]["visible"] = int(hover == p and focus != k)
    by["prevVal"]["text"] = ("[%s] %s" % (tag, name)) if tag else name
    by["statusErr" if err else "status"]["text"] = status.upper()
    return w


def preview(wdir, out_dir):
    import tempfile
    import widget_preview
    main = json.load(open(os.path.join(wdir, "to1", "main-menu.widget.json"), encoding="utf-8"))
    page = build_page(main)
    os.makedirs(out_dir, exist_ok=True)
    bg = nr.preview_bg(os.path.join(out_dir, "_bg.png"))
    for nm, kw in (("name-entry-0", dict()), ("name-entry-1", dict(focus=1, hover="name", status="Tag: letters and digits only", err=1)),
                   ("name-entry-2", dict(name="Wolfsschanze", tag="SERA", status="Saved. Everyone sees it now."))):
        tmp = os.path.join(tempfile.gettempdir(), "t2r-" + nm + ".widget.json")
        json.dump(demo(page, **kw), open(tmp, "w", encoding="utf-8"))
        print(widget_preview.render(tmp, os.path.join(out_dir, nm + ".png"), scale=0.5, bg=bg))


if __name__ == "__main__":
    import sys
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    preview(sys.argv[1], sys.argv[2])
