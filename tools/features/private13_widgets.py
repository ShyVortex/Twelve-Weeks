"""PRIVATE MATCH (re/private-lobby-1117.md): the 4th row of the FIND MATCH mode box opens a lobby page laid out like the MP main menu,
and its EDIT SETTINGS / CHOOSE MAP rows open a settings page with tabs, like TLOU2's own settings menu, in our clan-page style. Both pages are
driven by t2r-ext privlobby.c from daemon op 0xF8 / 0xF9 (tools/private_lobby.py).

to1/private13 (lobby page, a copy of to1/main-menu's own pieces):
  gameTitle "MULTIPLAYER" / menuTitle "PRIVATE MATCH" / titleUnderline / menuShade   the main menu's title block, as is
  menuList            the main menu's NATIVE Menu2::Container with five native buttons (button-default_autobright, the FIND MATCH widget): StartMatch,
                      ChooseMap, EditSettings, JoinCode, LeaveLobby. No action tags: privlobby.c catches select / click on them (as modepick.c does for FIND MATCH)
  lobbyPanel          the main menu's LOBBY box (blur, dark card, top / bottom lines, LOBBY n / 8) with OUR member rows plRow0..7 instead of the engine's
                      lobby list (team band blue / red / none, name, HOST tag, the team on the right)
  codeBox             LOBBY CODE + the code, top right (where ONLINE sits on the main menu)
  smBox               MATCH SETUP: the current mode, map and the rules that differ from the defaults (8 lines), between the menu and the lobby
  stTx                one status line under the menu ("WAITING FOR THE HOST", "STARTING - 2 OF 3 SEARCHING", errors)
  cdBox               JOIN WITH CODE: a modal box over the page (dim backdrop), five letter cells, the key hint for keyboard / pad
  buttonLegend / footerLine   the main menu footer (SELECT / BACK)

to1/private13s (EDIT SETTINGS, CHOOSE MAP):
  header              hdKick "PRIVATE MATCH - CODE K7MPX" / hdTitle EDIT SETTINGS or CHOOSE MAP
  tabs                tab0..3 GAME RULES / MATCH / MAP POOL / PLAYERS with the bumper glyphs left / right of the bar (TLOU2 settings), blue underline
  rw                  10 option rows (clan row look: card, edge, focus fill + frame): label left, < value > right, a blue dot when not the default
  inf                 the focused row's name, description and default on the right
  mg                  the all-maps grid (5 x 4, the vote grid's geometry): thumbnail, name, check = in the pool, dark + "NOT IN POOL" when out, lock text when
                      a member's game lacks the map; in CHOOSE MAP a cream frame marks the chosen map; the right column has VOTE FROM POOL / RANDOM FROM POOL
  footer              BACK / CHANGE / TABS / RESET (menu:action)
Widget space 3840 x 2160. python private13_widgets.py <extracted widget dir> <out dir> renders the previews."""
import copy
import json
import os
import t2guid

from clan_widgets import Builder, _templates, SUPPLY_BLUE, PM_TEXT, PM_DIM
from matchflow_widgets import TEXT, CREAM, MAPIMG
from nr_style import lm as tlm      # (was gearup13_widgets.tlm, same box; moved to the shared frame in ui-redesign-1117)

PAGE = "private13"
SPAGE = "private13s"
PANEL = "streaming/t2r/clan/gearup-panel.png"
TITLE = 0xFFD8D4CC
LABEL = 0xFFB4B4B4
DIM = 0xFF8D897B
HIT_A = 1
CARD_A, EDGE_A, FOCUS_A, HILITE_A = 150, 46, 190, 16
TEAM_COL = (0xFF48A8D8, 0xFFE04848)          # the vote roster's team bands (blue / red)
ROWS = ("StartMatch", "START MATCH"), ("ChooseMap", "CHOOSE MAP"), ("EditSettings", "EDIT SETTINGS"), ("JoinCode", "JOIN WITH CODE"), ("LeaveLobby", "LEAVE LOBBY")
NMEM = 8
SM_LINES = 8
CODE_LEN = 5
X0, X1 = 300, 3540
TAB_NAMES = ("GAME RULES", "MATCH", "MAP POOL", "PLAYERS")
TAB_X = (420, 900, 1240, 1690)
NROW = 10
RW_X, RW_Y0, RW_W, RW_H, RW_DY = 300, 440, 2150, 108, 124
VAL_W = 620
GRID_COLS, GRID_N = 5, 20
GX, GY, GGAP = 300, 440, 20
GW = (2262 - (GRID_COLS - 1) * GGAP) // GRID_COLS      # 436: the vote grid's cell (matchflow_widgets voteGrid)
GH = GW * 9 // 16
IX, IW = 2620, 920                                      # the right info column

# preview only: the live server's 20 maps (daemon MAPS + the built SP-section maps), index = the daemon's map index
PREVIEW_MAPS = [("Forest", "forest"), ("Gas Station", "gas-station"), ("School", "school"), ("Shipyard", "shipyard"), ("Resort", "resort"),
                ("Seraphite Camp", "seraphite-camp"), ("Houses", "houses"), ("Hospital", "hospital"), ("Train Station", "train-station"),
                ("Downtown", "downtown"), ("Jackson Suburbs", "jackson-suburbs"), ("Suburbs", "outpost"), ("Bookstore (Part I)", "p1-bookstore"),
                ("Hillside", "wilds-houses"), ("Capitol Hill Shops", "capitol-shops"), ("Convention Center", "into-the-city"), ("Overpass", "overpass"),
                ("Chase", "chase"), ("Supermarket", "jackson-market"), ("Plaza (Part I)", "p1-plaza")]


def _keep_main_pieces(main):
    """The main menu's own title block, menu container, lobby box and footer (copies with new guids, parents remapped)."""
    keep = ("root", "anim-group", "menuShade", "gameTitle", "menuTitle", "titleUnderline", "menuList", "lobbyPanel", "lobbyBlur", "lobbyBg",
            "lobbyLineTop", "lobbyLineBottom", "lobbyHeader", "lobbyCount", "lobbyHeaderLine", "buttonLegend", "hintSelectIcon", "hintSelectText",
            "hintBackIcon", "hintBackText", "footerLine")
    by = {i["name"]: i for i in main["items"]}
    gmap = {}
    out = []
    for n in keep:
        if n not in by:
            continue
        c = copy.deepcopy(by[n])
        gmap[c["guid"]] = t2guid.guid()
        out.append(c)
    for c in out:
        c["guid"] = gmap[c["guid"]]
        if c.get("parent") is not None:
            c["parent"] = gmap.get(c["parent"], c["parent"])
    return {c["name"]: c for c in out}, out, by


def build_lobby_page(main):
    t, _, _ = _templates(main)
    pc, items, by = _keep_main_pieces(main)
    b = Builder(t)
    a = pc["anim-group"]["guid"]
    pc["gameTitle"]["text"] = "MULTIPLAYER"
    pc["menuTitle"]["text"] = "PRIVATE MATCH"
    # the five native buttons (a copy of FIND MATCH each; no action tag, privlobby.c acts on them)
    tpl = by["FindMatch"]
    ml = pc["menuList"]
    rows = []
    for k, (nm, txt) in enumerate(ROWS):
        r = copy.deepcopy(tpl)
        r.update(guid=t2guid.guid(), parent=ml["guid"], name=nm, text=txt, visible=1, focusable=1)
        r["pivotAs.y"] = k * 106.0
        r.pop("tags", None)
        rows.append(r)
    ml["rectSizeDelta.height"] = 56.0 + 106.0 * (len(ROWS) - 1)
    # status line under the menu
    b.text("stTx", a, b.tl(180, 1340, 2060, 60), "", 34, LABEL, face="Alternate", tracking=5)
    # LOBBY CODE (top right, the ONLINE spot)
    cb = b.group("codeBox", a, b.tl(2500, 150, 1180, 230))["guid"]
    b.text("cdLabel", cb, tlm(0, 20, 1180, 50, right=1), "LOBBY CODE", 34, LABEL, face="Alternate", align=2, tracking=8)
    b.text("cdCode", cb, tlm(0, 70, 1180, 130, right=1), "", 110, TITLE, align=2, tracking=24)
    # member rows in the LOBBY box (lobbyPanel is 1180 x 1120, its header line at y 120)
    lp = pc["lobbyPanel"]["guid"]
    pc["lobbyCount"]["text"] = "1 / 8"
    for k in range(NMEM):
        g = b.group(f"plRow{k}", lp, b.tl(50, 150 + k * 118, 1080, 100), visible=0)["guid"]
        b.rect(f"plBar{k}", g, b.fill(), 0xFFFFFFFF, 22)
        b.image(f"plTabB{k}", g, b.tl(0, 0, 700, 100), "streaming/t2r/icons/team-grad.png", TEAM_COL[0], 200, visible=0)
        b.image(f"plTabR{k}", g, b.tl(0, 0, 700, 100), "streaming/t2r/icons/team-grad.png", TEAM_COL[1], 200, visible=0)
        b.text(f"plNm{k}", g, tlm(36, 0, 620, 100), "", 46, TEXT, tracking=2)
        b.rect(f"plHostBg{k}", g, b.tl(680, 30, 120, 40), CREAM, 230, visible=0)
        b.text(f"plHost{k}", g, b.tl(680, 30, 120, 40), "HOST", 26, 0xFF101418, align=1, tracking=3, visible=0)
        b.text(f"plTm{k}", g, tlm(820, 0, 230, 100, right=1), "", 30, DIM, face="Alternate", align=2, tracking=6)
    b.text("plWait", lp, b.tl(50, 1000, 1080, 60), "", 30, DIM, face="Alternate", align=1, tracking=6)
    # MATCH SETUP between the menu and the lobby (the lobby box's look)
    sm = b.group("smBox", a, b.tl(1180, 524, 1060, 760))["guid"]
    b.image("smBlur", sm, b.fill(), "general-textures/blur-background.png", 0xFFFFFFFF, 255)
    b.rect("smBg", sm, b.fill(), 0xFF000000, 150)
    b.line("smLineT", sm, 0, 0, 1060, 0, 0xFFFFFFFF, 130, 2.0)
    b.line("smLineB", sm, 0, 760, 1060, 760, 0xFFFFFFFF, 130, 2.0)
    b.text("smHead", sm, b.tl(48, 26, 600, 70), "MATCH SETUP", 38, LABEL, face="Alternate", tracking=8)
    b.line("smHeadLine", sm, 40, 116, 1020, 116, 0xFFFFFFFF, 90, 2.0)
    for k in range(SM_LINES):
        b.text(f"smK{k}", sm, tlm(48, 140 + k * 74, 470, 64), "", 32, DIM, face="Alternate", tracking=6)
        b.text(f"smV{k}", sm, tlm(520, 140 + k * 74, 492, 64, right=1), "", 38, TEXT, align=2, tracking=2)
    # JOIN WITH CODE (modal)
    cd = b.group("cdBox", a, b.tl(0, 0, 3840, 2160), visible=0, depth=6.0)["guid"]
    b.rect("cdDim", cd, b.bleed(), 0xFF000000, 170)
    bx = b.group("cdPanel", cd, b.tl(1320, 700, 1200, 620))["guid"]
    b.image("cdBlur", bx, b.fill(), "general-textures/blur-background.png", 0xFFFFFFFF, 255)
    b.rect("cdBg", bx, b.fill(), 0xFF000000, 200)
    b.frame("cdEdge", bx, b.fill(), 0xFFFFFFFF, 70, 2.0)
    b.text("cdTitle", bx, b.tl(60, 40, 1080, 90), "JOIN WITH CODE", 54, TITLE, tracking=4)
    b.text("cdSub", bx, b.tl(60, 128, 1080, 50), "TYPE THE LOBBY CODE YOUR FRIEND SEES", 28, DIM, face="Alternate", tracking=6)
    cw, gap = 160, 32
    x0 = (1200 - (CODE_LEN * cw + (CODE_LEN - 1) * gap)) // 2
    for k in range(CODE_LEN):
        g = b.group(f"cdCell{k}", bx, b.tl(x0 + k * (cw + gap), 220, cw, 200))["guid"]
        b.rect(f"cdCellBg{k}", g, b.fill(), 0xFFFFFFFF, 14)
        b.rect(f"cdCellUl{k}", g, b.tl(0, 194, cw, 6), 0xFFFFFFFF, 120)
        b.rect(f"cdCellCur{k}", g, b.tl(0, 194, cw, 6), SUPPLY_BLUE, 255, visible=0)
        b.text(f"cdCh{k}", g, b.tl(0, 0, cw, 194), "", 120, TEXT, align=1, tracking=0)
    b.text("cdErr", bx, b.tl(60, 450, 1080, 50), "", 30, 0xFFF2625A, face="Alternate", align=1, tracking=5)
    b.text("cdKeys", bx, b.tl(60, 520, 1080, 50), "ENTER  JOIN     ESC  CANCEL", 28, DIM, face="Alternate", align=1, tracking=6)
    # order: the main pieces first (the page root first), then ours under anim-group, the rows inside menuList
    at = items.index(pc["menuList"]) + 1
    items[at:at] = rows
    w = {k: copy.deepcopy(v) for k, v in main.items() if k != "items"}
    w["items"] = items + b.items
    return w


def edge(b, p, i, g):
    b.rect(f"{p}Card{i}", g, b.fill(), 0xFF000000, CARD_A)
    b.frame(f"{p}Edge{i}", g, b.fill(), 0xFFFFFFFF, EDGE_A, 2.0)
    b.rect(f"{p}Fill{i}", g, b.fill(), 0xFFFFFFFF, HILITE_A, visible=0)
    b.frame(f"{p}Frame{i}", g, b.fill(), 0xFFFFFFFF, FOCUS_A, 3.0, visible=0)


def arrow(b, name, parent, x, y, left):
    pts = [1.0, 0.0, 0.0, 0.5, 1.0, 1.0] if left else [0.0, 0.0, 1.0, 0.5, 0.0, 1.0]
    return b.add("Polyline", name, parent, **b.tl(x, y, 22, 40), **b.col(0xFFE6E6E6), closed=0, lineWidth=4.0, pointsUv=pts, **{"color.a": 230})


def build_settings_page(main):
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
    b.text("hdKick", hd, b.tl(X0, 90, 1800, 44), "PRIVATE MATCH", 32, LABEL, face="Alternate", tracking=8)
    b.text("hdTitle", hd, b.tl(X0 - 4, 126, 1800, 150), "EDIT SETTINGS", 104, TITLE, tracking=4)
    b.text("hdNote", hd, tlm(2040, 170, 1500, 60, right=1), "", 34, DIM, face="Alternate", align=2, tracking=6)
    tb = b.group("tabs", a, b.tl(0, 0, 3840, 2160))["guid"]
    b.image("tabPrevIc", tb, b.tl(X0, 300, 64, 64), "menu:prev", 0xFFFFFFFF)
    for k in range(4):
        b.text(f"tab{k}", tb, b.tl(TAB_X[k], 292, 460, 80), TAB_NAMES[k], 46, TEXT, tracking=4)
        b.rect(f"tabU{k}", tb, b.tl(TAB_X[k], 352, 100, 5), SUPPLY_BLUE, 255, visible=0)
        b.rect(f"tabHit{k}", tb, b.tl(TAB_X[k] - 20, 280, 420 if k != 1 else 300, 100), 0xFFFFFFFF, HIT_A)
    b.image("tabNextIc", tb, b.tl(2120, 300, 64, 64), "menu:next", 0xFFFFFFFF)
    b.line("tabRule", tb, X0, 392, X1, 392, 0xFFFFFFFF, 130, 2.0)
    # ---- option rows
    rw = b.group("rw", a, b.tl(0, 0, 3840, 2160))["guid"]
    for k in range(NROW):
        g = b.group(f"row{k}", rw, b.tl(RW_X, RW_Y0 + k * RW_DY, RW_W, RW_H), visible=0)["guid"]
        edge(b, "r", k, g)
        b.text(f"rLb{k}", g, tlm(48, 0, 1200, RW_H), "", 44, TEXT, tracking=2)
        b.rect(f"rDot{k}", g, b.ctr(RW_W - VAL_W - 70, RW_H / 2.0, 14, 14), SUPPLY_BLUE, 255, visible=0)
        arrow(b, f"rL{k}", g, RW_W - VAL_W - 20, (RW_H - 40) / 2.0, 1)
        b.text(f"rVal{k}", g, b.tl(RW_W - VAL_W + 20, 0, VAL_W - 80, RW_H), "", 44, TEXT, align=1, tracking=2)
        arrow(b, f"rR{k}", g, RW_W - 60, (RW_H - 40) / 2.0, 0)
        b.rect(f"rHitL{k}", g, b.tl(RW_W - VAL_W - 40, 0, 120, RW_H), 0xFFFFFFFF, HIT_A)
        b.rect(f"rHitR{k}", g, b.tl(RW_W - 120, 0, 120, RW_H), 0xFFFFFFFF, HIT_A)
        b.rect(f"rHit{k}", g, b.fill(), 0xFFFFFFFF, HIT_A)
    inf = b.group("inf", a, b.tl(0, 0, 3840, 2160))["guid"]
    b.text("infName", inf, b.tl(IX, 440, IW, 80), "", 54, TEXT, tracking=3)
    b.line("infRule", inf, IX, 540, IX + IW, 540, 0xFFFFFFFF, 90, 2.0)
    b.text("infDesc", inf, b.tl(IX, 570, IW, 500), "", 34, LABEL, multiline=1, valign=0, tracking=2)
    b.text("infDef", inf, b.tl(IX, 1090, IW, 50), "", 28, DIM, face="Alternate", tracking=6)
    # ---- the all-maps grid (MAP POOL tab, CHOOSE MAP)
    mg = b.group("mg", a, b.tl(0, 0, 3840, 2160), visible=0)["guid"]
    for k in range(GRID_N):
        x, y = GX + (k % GRID_COLS) * (GW + GGAP), GY + (k // GRID_COLS) * (GH + GGAP)
        g = b.group(f"m{k}", mg, b.tl(x, y, GW, GH), visible=0)["guid"]
        b.rect(f"m{k}Back", g, b.fill(), 0xFF050606, 255)
        b.image(f"m{k}Img", g, b.fill(), MAPIMG.format("forest"), 0xFFFFFFFF, 255)
        b.rect(f"m{k}Shade", g, b.fill(), 0xFF000000, 90)
        b.rect(f"m{k}Off", g, b.fill(), 0xFF0B0C0D, 215, visible=0)
        b.text(f"m{k}Name", g, b.tl(16, 8, GW - 32, 70), "Forest", 36, TEXT, tracking=1)
        b.text(f"m{k}St", g, b.tl(16, GH - 56, GW - 96, 44), "", 26, DIM, face="Alternate", tracking=5)
        b.add("Polyline", f"m{k}Ck", g, **b.tl(GW - 66, GH - 54, 40, 36), **b.col(0xFFFFFFFF), closed=0, lineWidth=6.0,
              pointsUv=[0.05, 0.55, 0.38, 0.95, 0.97, 0.05], visible=0, **{"color.a": 255})
        b.frame(f"m{k}Sel", g, b.fill(), CREAM, 255, 6.0, visible=0)
        b.frame(f"m{k}Frame", g, b.fill(), 0xFFFFFFFF, 230, 4.0, visible=0)
        b.rect(f"m{k}Hit", g, b.fill(), 0xFFFFFFFF, HIT_A)
    b.text("mgCount", mg, b.tl(IX, 440, IW, 70), "", 46, TEXT, tracking=3)
    b.text("mgFoc", mg, b.tl(IX, 520, IW, 60), "", 34, LABEL, tracking=2)
    b.line("mgRule", mg, IX, 610, IX + IW, 610, 0xFFFFFFFF, 90, 2.0)
    for k, txt in enumerate(("VOTE FROM POOL", "RANDOM FROM POOL")):
        g = b.group(f"mo{k}", mg, b.tl(IX, 650 + k * 140, IW, 120), visible=0)["guid"]
        edge(b, "mo", k, g)
        b.text(f"moTx{k}", g, tlm(40, 0, IW - 140, 120), txt, 42, TEXT, tracking=2)
        b.add("Polyline", f"moCk{k}", g, **b.tl(IW - 80, 40, 44, 40), **b.col(CREAM), closed=0, lineWidth=6.0,
              pointsUv=[0.05, 0.55, 0.38, 0.95, 0.97, 0.05], visible=0, **{"color.a": 255})
        b.rect(f"moHit{k}", g, b.fill(), 0xFFFFFFFF, HIT_A)
    b.text("mgHelp", mg, b.tl(IX, 950, IW, 400), "", 32, LABEL, multiline=1, valign=0, tracking=2)
    # ---- status + footer
    b.text("msgTx", a, tlm(X0, 1760, X1 - X0, 60), "", 36, LABEL, face="Alternate", tracking=5)
    b.image("pBackIc", a, b.tl(270, 1898, 56, 56), "menu:back", 0xFFFFFFFF)
    b.text("pBackTx", a, b.tl(350, 1890, 400, 70), "BACK", 46, PM_TEXT, tracking=4)
    b.image("pSelIc", a, b.tl(760, 1898, 56, 56), "menu:select", 0xFFFFFFFF)
    b.text("pSelTx", a, b.tl(840, 1890, 500, 70), "CHANGE", 46, PM_TEXT, tracking=4)
    b.image("pPrevIc", a, b.tl(1340, 1898, 56, 56), "menu:prev", 0xFFFFFFFF)
    b.image("pNextIc", a, b.tl(1420, 1898, 56, 56), "menu:next", 0xFFFFFFFF)
    b.text("pTabTx", a, b.tl(1500, 1890, 500, 70), "TABS", 46, PM_TEXT, tracking=4)
    b.image("pActIc", a, b.tl(2000, 1898, 56, 56), "menu:action", 0xFFFFFFFF)
    b.text("pActTx", a, b.tl(2080, 1890, 900, 70), "RESET TO DEFAULT", 46, PM_TEXT, tracking=4)
    b.rect("pBackHit", a, b.tl(250, 1800, 480, 200), 0xFFFFFFFF, HIT_A)
    b.rect("pActHit", a, b.tl(1980, 1800, 900, 200), 0xFFFFFFFF, HIT_A)
    w = {k: copy.deepcopy(v) for k, v in main.items() if k != "items"}
    w["items"] = b.items
    return w


def add_private_pages(wdir):
    """to1/private13 + to1/private13s next to to1/main-menu. Returns the number of pages written."""
    main = json.load(open(os.path.join(wdir, "to1", "main-menu.widget.json"), encoding="utf-8"))
    n = 0
    for name, fn in ((PAGE, build_lobby_page), (SPAGE, build_settings_page)):
        pg = fn(main)
        names = [i["name"] for i in pg["items"]]
        assert len(names) == len(set(names)), "duplicate widget names on " + name
        json.dump(pg, open(os.path.join(wdir, "to1", name + ".widget.json"), "w", encoding="utf-8"), indent=4)
        n += 1
    return n


# ---------------------------------------------------------------- previews (the ext's fill, offline)
def _set(by, name, **kw):
    by[name].update(kw)


def demo_lobby(page, owner=True, code_box=False, starting=False):
    pg = copy.deepcopy(page)
    by = {i["name"]: i for i in pg["items"]}
    mem = [("PlayerA", 0, 1), ("PlayerB", 1, 0), ("PlayerC", 0, 0), ("PlayerD", 1, 0), ("PlayerE", 255, 0)]
    by["cdCode"]["text"] = "K7MPX"
    by["lobbyCount"]["text"] = "%d / 8" % len(mem)
    for k, (nm, tm, host) in enumerate(mem):
        by[f"plRow{k}"]["visible"] = 1
        by[f"plNm{k}"]["text"] = nm
        by[f"plTabB{k}"]["visible"] = int(tm == 0)
        by[f"plTabR{k}"]["visible"] = int(tm == 1)
        by[f"plTm{k}"]["text"] = "TEAM 1" if tm == 0 else "TEAM 2" if tm == 1 else "AUTO"
        by[f"plHostBg{k}"]["visible"] = by[f"plHost{k}"]["visible"] = host
    by["plWait"]["text"] = "UP TO 8 PLAYERS - SHARE THE CODE"
    lines = [("MODE", "SUPPLY RAID"), ("MAP", "VOTE - 12 MAPS"), ("TEAMS", "HOST ASSIGNS"), ("TEAM LIVES", "40"), ("MATCH TIME", "20 MIN"),
             ("DAMAGE MODEL", "TLOU2"), ("PARTS EARNED", "200%"), ("FREE CRAFTING", "ON")]
    for k, (kk, vv) in enumerate(lines):
        by[f"smK{k}"]["text"] = kk
        by[f"smV{k}"]["text"] = vv
    if starting:
        by["stTx"]["text"] = "STARTING - 3 OF 5 PLAYERS SEARCHING"
        by["StartMatch"]["text"] = "CANCEL START"
    elif owner:
        by["stTx"]["text"] = "YOU ARE THE HOST - START WHEN EVERYONE IS IN"
    else:
        by["stTx"]["text"] = "WAITING FOR THE HOST TO START"
        by["StartMatch"]["text"] = "START MATCH"
    _buttons_as_text(by, pg, "StartMatch" if not code_box else "JoinCode", dim=() if owner else ("StartMatch",))
    if code_box:
        by["cdBox"]["visible"] = 1
        for k, ch in enumerate("Q4N"):
            by[f"cdCh{k}"]["text"] = ch
        by["cdCellCur3"]["visible"] = 1
        by["cdKeys"]["text"] = "ENTER  JOIN     BACKSPACE  DELETE     ESC  CANCEL"
    return pg


def _buttons_as_text(by, pg, focus, dim=()):
    """widget_preview has no button renderer: the native buttons are drawn as their label (41 pt, normal / focused colour), as modepick_widgets.preview."""
    for i in pg["items"]:
        if i.get("class") == "Reference" and "button-default" in i.get("source", ""):
            on = i["name"] == focus
            col = 0xFFF2F2F2 if on else 0xFFA8A8A8
            i["class"] = "Text"
            i.update({"pointSize": 41, "alignH": 0, "alignV": 1, "faceId": "Default", "autoSize": 0, "effect": "SoftOutline",
                      "tint.start": col, "tint.end": col, "rectSizeDelta.width": 700.0, "tracking.x": 2.0})
            if i["name"] in dim:
                i["color.a"] = 102


RULE_DEMO = {
    0: [("PARTS EARNED", "200%", 1), ("TEAM LIVES", "40", 1), ("INVINCIBILITY", "OFF", 0), ("DAMAGE MODEL", "TLOU2", 1), ("DOWNED SYSTEM", "OFF", 1),
        ("RESPAWN TIMER", "WAVES", 0),
        ("FREE CRAFTING", "ON", 1), ("FRIENDLY FIRE", "OFF", 0), ("RADAR", "ON", 0), ("GUN LIMITS", "ON", 0)],
    1: [("MODE", "SUPPLY RAID", 0), ("MATCH TIME", "20 MIN", 1), ("TEAMS", "HOST ASSIGNS", 1), ("LATE JOIN", "ON", 0), ("MAX PLAYERS", "8", 0),
        ("AFK REMOVAL", "OFF", 0), ("PING LIMIT", "OFF", 0)],
    3: [("PlayerA", "TEAM 1", 1), ("PlayerB", "TEAM 2", 1), ("PlayerC", "TEAM 1", 1), ("PlayerD", "TEAM 2", 1), ("PlayerE", "AUTO", 0)],
}
INFO_DEMO = {
    0: ("DAMAGE MODEL", "FACTIONS: the 2013 damage table (body / head per gun, armour).\nTLOU2: the game's own gun damage, and every headshot is a "
        "would-kill hit: a down, or a kill with DOWNED SYSTEM off.", "DEFAULT: FACTIONS"),
    1: ("MATCH TIME", "How long a Supply Raid match runs. DEFAULT keeps the mode's own clock. Interrogation ends on the lockbox, not on a clock.",
        "DEFAULT: DEFAULT"),
    3: ("TEAMS", "TEAMS is HOST ASSIGNS: pick each player's team. AUTO players fill the smaller team when the match starts.", "KICK: RESET TO DEFAULT KEY"),
}


def demo_settings(page, tab, focus=0, pick=False, owner=True):
    pg = copy.deepcopy(page)
    by = {i["name"]: i for i in pg["items"]}
    for k in range(4):
        by[f"tabU{k}"]["visible"] = int(k == tab)
        by[f"tab{k}"]["color.a"] = 255 if k == tab else 150
    by["hdKick"]["text"] = "PRIVATE MATCH - CODE K7MPX"
    if not owner:
        by["hdNote"]["text"] = "ONLY THE HOST CAN CHANGE THE SETTINGS"
        by["pActTx"]["visible"] = by["pActIc"]["visible"] = 0
        by["pSelTx"]["visible"] = by["pSelIc"]["visible"] = 0
    if pick or tab == 2:
        by["rw"]["visible"] = 0
        by["inf"]["visible"] = 0
        by["mg"]["visible"] = 1
        pool = {0, 2, 4, 5, 6, 7, 8, 9, 10, 13, 14, 15, 16, 17, 18}
        missing = {12, 19} if not pick else set()
        for k, (nm, key) in enumerate(PREVIEW_MAPS):
            by[f"m{k}"]["visible"] = 1
            by[f"m{k}Name"]["text"] = nm
            by[f"m{k}Img"]["path"] = MAPIMG.format(key)
            inp = k in pool and k not in missing
            by[f"m{k}Off"]["visible"] = int(not inp)
            by[f"m{k}Ck"]["visible"] = int(inp and not pick)
            by[f"m{k}St"]["text"] = "MISSING FOR 1 PLAYER" if k in missing else ("" if inp else "NOT IN POOL")
            by[f"m{k}Frame"]["visible"] = int(k == focus)
        by["mgCount"]["text"] = "%d OF %d MAPS IN THE POOL" % (len(pool - missing), len(PREVIEW_MAPS))
        by["mgFoc"]["text"] = PREVIEW_MAPS[focus][0].upper()
        if pick:
            by["hdTitle"]["text"] = "CHOOSE MAP"
            by["tabs"]["visible"] = 0
            by["mo0"]["visible"] = by["mo1"]["visible"] = 1
            by["moCk0"]["visible"] = 1
            by["moFrame0"]["visible"] = by["moFill0"]["visible"] = 0
            by["pSelTx"]["text"] = "CHOOSE"
            by["pActTx"]["visible"] = by["pActIc"]["visible"] = 0
            by["pTabTx"]["visible"] = by["pPrevIc"]["visible"] = by["pNextIc"]["visible"] = 0
            by["mgHelp"]["text"] = "Pick the map of the next match, or let the players vote over the map pool / take a random pool map. Greyed maps are not in the pool (EDIT SETTINGS > MAP POOL)."
        else:
            by["pSelTx"]["text"] = "TOGGLE"
            by["pActTx"]["text"] = "ALL MAPS"
            by["mgHelp"]["text"] = "Toggle the maps a vote or a random pick may land on. A map a player's game does not have is never picked."
        return pg
    rows = RULE_DEMO[tab]
    for k in range(NROW):
        on = k < len(rows)
        by[f"row{k}"]["visible"] = int(on)
        if not on:
            continue
        lb, val, chg = rows[k]
        by[f"rLb{k}"]["text"] = lb
        by[f"rVal{k}"]["text"] = val
        by[f"rDot{k}"]["visible"] = chg
        by[f"rFill{k}"]["visible"] = by[f"rFrame{k}"]["visible"] = int(k == focus)
        if not owner:
            by[f"rL{k}"]["visible"] = by[f"rR{k}"]["visible"] = 0
    nm, desc, df = INFO_DEMO[tab]
    by["infName"]["text"] = nm
    by["infDesc"]["text"] = desc
    by["infDef"]["text"] = df
    if tab == 3:
        by["pActTx"]["text"] = "KICK"
    return pg


def preview(wdir, out_dir):
    import tempfile
    import widget_preview
    main = json.load(open(os.path.join(wdir, "to1", "main-menu.widget.json"), encoding="utf-8"))
    lob, st = build_lobby_page(main), build_settings_page(main)
    os.makedirs(out_dir, exist_ok=True)
    figs = os.path.join(tempfile.gettempdir(), "gu-fig")
    os.makedirs(figs, exist_ok=True)
    import ui_scratch
    ui_scratch.make_gearup_panel(1920, 1080).save(os.path.join(figs, "gearup-panel.png"))
    widget_preview.STREAMING["streaming/t2r/clan/"] = figs
    shots = [("lobby-host", demo_lobby(lob)), ("lobby-member", demo_lobby(lob, owner=False)), ("lobby-starting", demo_lobby(lob, starting=True)),
             ("lobby-join-code", demo_lobby(lob, code_box=True)),
             ("settings-game-rules", demo_settings(st, 0, 3)), ("settings-match", demo_settings(st, 1, 1)), ("settings-map-pool", demo_settings(st, 2, 7)),
             ("settings-players", demo_settings(st, 3, 1)), ("settings-member-view", demo_settings(st, 0, 3, owner=False)),
             ("choose-map", demo_settings(st, 2, 8, pick=True))]
    out = []
    for nm, pg in shots:
        tmp = os.path.join(tempfile.gettempdir(), f"t2r-priv-{nm}.widget.json")
        json.dump(pg, open(tmp, "w", encoding="utf-8"))
        out.append(widget_preview.render(tmp, os.path.join(out_dir, f"private-{nm}.png"), scale=0.5))
    return out


if __name__ == "__main__":
    import sys
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    for p in preview(sys.argv[1], sys.argv[2]):
        print(p)
