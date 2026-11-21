"""The in-game ACHIEVEMENTS page (to1/clanach): the 6th tab of the CLAN strip (registered by tools/ext/achieve_ui.c through nrui.c
nr_clan_xtab_add), in the No Return style of re/ui-refs-1117/STYLE.md with the change to a list that is both vertical and
horizontal not just horizontal"):

  frame   nr_style.frame: blurred dimmed scene, breadcrumb WLF CLAN | ACHIEVEMENTS, the Q / E clan tab strip, the week block, boxed prompts
  rows    one per achievements.py group (MELEE MASTERY, WEAPON FEATS, SKILL, MILESTONES, CLAN, HIDDEN): grey caps header + N | M + hairline
          (nr_style.section), a line of square tiles (the icon: the art when unlocked, the dark grey copy + a padlock while locked, the dark
          "?" for a hidden one), a thin progress bar under counter ones, a yellow-green dot on one unlocked since the last visit.
          ROWS rows x COLS tiles on screen; the rows scroll up / down, a row scrolls left / right, the arrows / stick / d-pad move in both
          axes and keep the column between rows.
  focus   ONE white 4 px outline (nr_style.focus_frame) on the focused tile; the other tiles dimmed.
  detail  the right column: UNLOCKED N | M (p%) + the overall bar, the icon big, the title in caps, the description in sentence case,
          N | M + a thin bar (counter ones), "Status:" + a chip (UNLOCKED <date> accent / LOCKED grey / HIDDEN dark).

Icons: streaming/t2r/ach/<id>.png, <id>-l.png (locked), hidden.png, lock.png (the padlock). Images on screen: ROWS x COLS tiles + the
padlock + the detail icon (one of the tiles' textures) + the frame's (blur, Q / E glyphs, prompt glyphs) <= 28 of gui2's 32.
Widget space 3840 x 2160; every changing text / image / visibility / alpha / offset is written by the ext; names are unique page-wide."""
import copy
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import nr_style as nr  # noqa: E402
import t2guid  # noqa: E402
from clan_widgets import Builder, _templates  # noqa: E402

PAGE = "clanach"
ICONS = "streaming/t2r/ach/"
GROUPS = ("melee", "weapon", "skill", "stats", "clan", "secret")             # achievements.py groups, in row order
ROW_LABEL = ("MELEE MASTERY", "WEAPON FEATS", "SKILL", "MILESTONES", "CLAN", "HIDDEN")
CLAN_TABS = ["OVERVIEW", "SURVIVORS", "RAIDS", "JOURNAL", "MISSIONS", "ACHIEVEMENTS"]
X0 = nr.L0
TW = TH = 300
TGAP = 24
COLS, ROWS = 6, 3
X1 = X0 + COLS * TW + (COLS - 1) * TGAP          # 2068
ROW_Y0, ROW_P = 440, 440                          # first row header centre line, row pitch
TILE_DY = 46                                      # header line -> tile top
BAR_DY = TH + 16                                  # tile top -> its progress bar
SB_X = X1 + 60                                    # the rows' scroll bar
D_X0, D_X1 = 2300, nr.R1                          # the detail column
D_ART = 640
D_ART_Y = 560
D_TITLE_Y = D_ART_Y + D_ART + 90
LOCK = 84
NEW_R = 10
SEEN_T0 = 1794890000
def tile_alpha(foc, locked, hidden):              # = achieve_ui.c aui_alpha: focused full, unlocked a little dimmed, locked more, hidden dark (STYLE.md: hidden = dark + ?)
    return (140 if foc else 95) if hidden else 255 if foc else 205 if not locked else 165


def tile_xy(r, c):
    return X0 + c * (TW + TGAP), ROW_Y0 + r * ROW_P + TILE_DY


def build_page(main):
    t, root0, anim0 = _templates(main)
    b = Builder(t)
    root = copy.deepcopy(root0); root.update(guid=t2guid.guid())
    anim = copy.deepcopy(anim0); anim.update(guid=t2guid.guid(), parent=root["guid"])
    b.items += [root, anim]
    a = anim["guid"]
    nr.frame(b, a, "WLF CLAN", "ACHIEVEMENTS", tabs_labels=CLAN_TABS, active_tab=5, wk=(1, 1, 0), prompts=3)
    b.text("ldTx", a, b.tl(X0, 900, X1 - X0, 200), "", nr.pt(28), nr.GREY, align=1, tracking=3, visible=0)
    rows = b.group("rows", a, b.tl(0, 0, 3840, 2160))["guid"]
    for r in range(ROWS):
        y = ROW_Y0 + r * ROW_P
        nr.section(b, rows, f"rw{r}", X0, X1, y, ROW_LABEL[r], "0 | 0")
        for c in range(COLS):
            x, ty = tile_xy(r, c)
            g = nr.plain_tile(b, rows, f"t{r}_{c}", x, ty, TW, TH)
            b.image(f"t{r}_{c}P", g, b.fill(), ICONS + "hidden.png", 0xFFFFFFFF, 255, scaleMode="StretchAspect")
            b.image(f"t{r}_{c}L", g, b.ctr(TW / 2, TH / 2, LOCK, LOCK), ICONS + "lock.png", 0xFFFFFFFF, 255, visible=0)
            nr.dot(b, g, f"t{r}_{c}N", TW - 26, 26, NEW_R, visible=0)
            nr.bar(b, rows, f"t{r}_{c}B", x, x + TW, ty + BAR_DY, h=4)
        nr.scroll_h(b, rows, f"rs{r}", X0, X1, ROW_Y0 + r * ROW_P + TILE_DY + BAR_DY + 30, visible=0)
        b.items[-1]["color.a"] = 110                                  # (the row's scroll thumb: quieter than the tiles' own bars)
        b.items[-1]["rectSizeDelta.height"] = 4.0
    nr.focus_frame(b, rows, "foc", th=4)
    nr.scroll_v(b, rows, "sbV", SB_X, ROW_Y0 - 20, ROW_Y0 + (ROWS - 1) * ROW_P + TILE_DY + BAR_DY + 8, visible=0)
    # ------------------------------------------------------------ detail column
    d = b.group("det", a, b.tl(0, 0, 3840, 2160))["guid"]
    nr.section(b, d, "dTot", D_X0, D_X1, ROW_Y0, "UNLOCKED", "0 | 0")
    nr.bar(b, d, "dTotB", D_X0, D_X1, ROW_Y0 + 34, h=6)
    b.rect("dBg", d, b.tl(D_X0 - 40, D_ART_Y - 40, D_X1 - D_X0 + 80, 1880 - D_ART_Y), nr.TILE, 120)
    b.image("dArt", d, b.tl((D_X0 + D_X1 - D_ART) / 2, D_ART_Y, D_ART, D_ART), ICONS + "hidden.png", 0xFFFFFFFF, 255, scaleMode="StretchAspect")
    b.image("dLock", d, b.ctr((D_X0 + D_X1) / 2, D_ART_Y + D_ART / 2, 150, 150), ICONS + "lock.png", 0xFFFFFFFF, 255, visible=0)
    b.rect("dRule", d, b.tl(D_X0, D_TITLE_Y - 60, D_X1 - D_X0, 2), nr.WHITE, nr.HAIR_A)
    b.text("dGrp", d, nr.lm(D_X0, D_TITLE_Y - 110, D_X1 - D_X0, 56), "", nr.pt(20), nr.GREY, tracking=3)
    b.text("dTitle", d, nr.lm(D_X0, D_TITLE_Y - 5, D_X1 - D_X0, 90), "TITLE", nr.HEAD_PT, nr.WHITE, tracking=3)
    b.text("dDesc", d, b.tl(D_X0, D_TITLE_Y + 60, D_X1 - D_X0, 130), "", nr.pt(22), nr.WHITE, multiline=1, tracking=1)
    nr.bar(b, d, "dBar", D_X0, D_X1 - 300, D_TITLE_Y + 230, h=6)
    b.text("dCnt", d, nr.lm(D_X1 - 280, D_TITLE_Y + 233 - 34, 280, 68, right=1), "0 | 0", nr.pt(24), nr.WHITE, align=2, tracking=2)
    b.text("dSt", d, nr.lm(D_X0, D_TITLE_Y + 320 - 30, 400, 60), "Status:", nr.pt(22), nr.GREY, tracking=1)
    nr.chip(b, d, "dChip", D_X0 + 170, D_TITLE_Y + 320 - 28, "LOCKED", style="grey")         # status chip: grey = locked,
    nr.chip(b, d, "dChipA", D_X0 + 170, D_TITLE_Y + 320 - 28, "UNLOCKED", style="acc")      # accent = unlocked (done),
    nr.chip(b, d, "dChipD", D_X0 + 170, D_TITLE_Y + 320 - 28, "HIDDEN", style="dark")       # dark = hidden; achieve_ui.c shows one
    for n in ("dChipABg", "dChipATx", "dChipDBg", "dChipDTx"):
        next(i for i in b.items if i["name"] == n)["visible"] = 0
    # "UNLOCKS: <item>" (customize items an achievement unlocks, tools/ext/customize_ach.h): achieve_ui.c shows it when the table has a row
    b.text("dUnl", d, nr.lm(D_X0, D_TITLE_Y + 400 - 30, D_X1 - D_X0, 60), "UNLOCKS:", nr.pt(22), nr.ACC, tracking=1)
    b.items[-1]["visible"] = 0
    w = {k: copy.deepcopy(v) for k, v in main.items() if k != "items"}
    w["items"] = b.items
    return w


# ------------------------------------------------------------------ offline previews (filled the way achieve_ui.c fills the page)
def rows_of(table):
    """[(group index, [row, ...])] the non-empty groups in GROUPS order; row = dict(id, title, desc, goal, prog, t, hidden)"""
    out = []
    for k, g in enumerate(GROUPS):
        rs = [r for r in table if r["group"] == g]
        if rs:
            out.append((k, rs))
    return out


def demo(page, table, foc=(0, 0), row0=0, offs=None, seen_t=0, fac="WLF CLAN", wk=(3, 2, 16)):
    import time
    offs = offs or {}
    w = copy.deepcopy(page)
    by = {i["name"]: i for i in w["items"]}
    nr.demo_header(by, fac, "ACHIEVEMENTS")
    nr.demo_tabs(by, CLAN_TABS, 5)
    nr.demo_week(by, *wk)
    nr.demo_chips(by)
    R = rows_of(table)
    fr, fc = foc
    for r in range(ROWS):
        ri = row0 + r
        if ri >= len(R):
            for k in ("Tx", "Rt", "Rl"):
                by[f"rw{r}{k}"]["visible"] = 0
            for c in range(COLS):
                by[f"t{r}_{c}"]["visible"] = 0
                by[f"t{r}_{c}BT"]["visible"] = by[f"t{r}_{c}BF"]["visible"] = 0
            continue
        gi, its = R[ri]
        nr.demo_section(by, f"rw{r}", X0, X1, ROW_LABEL[gi], "%d | %d" % (sum(1 for it in its if it["t"]), len(its)))
        off = offs.get(ri, 0)
        for c in range(COLS):
            k = off + c
            on = k < len(its)
            by[f"t{r}_{c}"]["visible"] = int(on)
            if not on:
                by[f"t{r}_{c}BT"]["visible"] = by[f"t{r}_{c}BF"]["visible"] = 0
                continue
            it = its[k]
            lk, hid, f = not it["t"], it["hidden"] and not it["t"], (ri, k) == (fr, fc)
            P = by[f"t{r}_{c}P"]
            P["path"] = ICONS + ("hidden" if hid else it["id"] + ("-l" if lk else "")) + ".png"
            P["color.a"] = tile_alpha(f, lk, hid)
            by[f"t{r}_{c}L"]["visible"] = int(lk and not hid)
            by[f"t{r}_{c}L"]["color.a"] = 255 if f else 170
            by[f"t{r}_{c}Bg"]["color.a"] = nr.TILE_FA if f else nr.TILE_A
            by[f"t{r}_{c}N"]["visible"] = int(bool(it["t"]) and it["t"] > seen_t)
            bar = it["goal"] > 1 and not hid
            by[f"t{r}_{c}BT"]["visible"] = int(bar)
            if bar:
                nr.demo_bar(by, f"t{r}_{c}B", 0, TW, 1.0 if it["t"] else min(1.0, it["prog"] / float(it["goal"])))
                by[f"t{r}_{c}BF"]["pivotAs.x"] = float(tile_xy(r, c)[0])
                by[f"t{r}_{c}BF"]["color.a"] = 255 if f else 150
            else:
                by[f"t{r}_{c}BF"]["visible"] = 0
            if f:
                x, y = tile_xy(r, c)
                nr.demo_frame(by, "foc", x - 6, y - 6, TW + 12, TH + 12, th=4)
        if len(its) > COLS:
            by[f"rs{r}T"]["visible"] = by[f"rs{r}H"]["visible"] = 1
            nr.demo_scroll_h(by, f"rs{r}", X0, X1, off / len(its), (off + COLS) / len(its))
    if len(R) > ROWS:
        by["sbVT"]["visible"] = by["sbVH"]["visible"] = 1
        y0, y1 = ROW_Y0 - 20, ROW_Y0 + (ROWS - 1) * ROW_P + TILE_DY + BAR_DY + 8
        by["sbVH"]["pivotAs.y"] = float(y0 + (y1 - y0) * row0 / len(R))
        by["sbVH"]["rectSizeDelta.height"] = float((y1 - y0) * ROWS / len(R))
    un = sum(1 for it in table if it["t"])
    nr.demo_section(by, "dTot", D_X0, D_X1, "UNLOCKED", "%d | %d  (%d%%)" % (un, len(table), 100 * un // max(1, len(table))))
    nr.demo_bar(by, "dTotB", D_X0, D_X1, un / float(max(1, len(table))))
    gi, its = R[fr]
    it = its[fc]
    lk, hid = not it["t"], it["hidden"] and not it["t"]
    by["dArt"]["path"] = ICONS + ("hidden" if hid else it["id"] + ("-l" if lk else "")) + ".png"
    by["dLock"]["visible"] = int(lk and not hid)
    by["dArt"]["color.a"] = 140 if hid else 255
    by["dGrp"]["text"] = ROW_LABEL[gi]
    by["dTitle"]["text"] = "?" if hid else it["title"]
    by["dDesc"]["text"] = "Hidden achievement. Keep playing." if hid else it["desc"]
    bar = not hid                                        # every shown achievement: N | M + bar (a one-match goal: 0 | 1 / 1 | 1)
    for n in ("dBarT", "dBarF", "dCnt"):
        by[n]["visible"] = int(bar)
    if bar:
        gl = max(1, it["goal"])
        p = gl if it["t"] else min(it["prog"], gl)
        nr.demo_bar(by, "dBar", D_X0, D_X1 - 300, p / float(gl))
        by["dCnt"]["text"] = "%d | %d" % (p, gl)
    chip = ("UNLOCKED " + time.strftime("%d %b %Y", time.localtime(it["t"])).upper()) if it["t"] else "HIDDEN" if hid else "LOCKED"
    cn = "dChipA" if it["t"] else "dChipD" if hid else "dChip"
    for n in ("dChip", "dChipA", "dChipD"):
        by[n + "Bg"]["visible"] = by[n + "Tx"]["visible"] = int(n == cn)
    by[cn + "Tx"]["text"] = chip
    un = ", ".join(it.get("unlocks") or ())
    by["dUnl"]["visible"] = int(bool(un) and not hid)
    by["dUnl"]["text"] = "UNLOCKS: " + un
    by[cn + "Bg"]["rectSizeDelta.width"] = float(nr.est(chip, by[cn + "Tx"]["pointSize"]) * 1.06 + 32)
    nr.demo_prompts(by, [("", "CLAN TABS", True, "menu:prev"), ("W / S", "ROWS", True, None), ("", "BACK", True, "menu:back")])
    return w


def demo_table(seed=3, n_unlocked=16):
    """the real achievements.py table with a fake player's progress (previews only)"""
    import random
    sys.path.insert(0, os.path.join(HERE, ".."))
    import achievements as A
    rng = random.Random(seed)
    out = []
    ids = [a["id"] for a in A.ACH]
    got = set(rng.sample(ids, n_unlocked))
    for a in A.ACH:
        g = a["goal"]
        t = SEEN_T0 - rng.randint(0, 40) * 86400 if a["id"] in got else 0
        out.append(dict(id=a["id"], group=a["group"], title=a["title"], desc=a["desc"], goal=g, hidden=bool(a["hidden"]), t=t,
                        prog=g if t else (rng.randint(0, g - 1) if g > 1 else 0)))
    return out


def preview(wdir, out_dir, icons_dir):
    """PNG previews of the page (tools/features/widget_preview.py) with the real icons (icons_dir: the shipped <id>.png set + lock.png)"""
    import tempfile
    import widget_preview
    import real_icons
    get0 = real_icons.get

    def get(path):                                      # streaming/t2r/ach/<f> -> icons_dir/<f> (real_icons maps only streaming/t2r/icons/)
        if path.startswith(ICONS):
            f = os.path.join(icons_dir, path[len(ICONS):])
            if path not in real_icons._cache:
                real_icons._cache[path] = Image.open(f).convert("RGBA") if os.path.exists(f) else None
            return real_icons._cache[path]
        return get0(path)
    real_icons.get = get
    from PIL import Image
    main = json.load(open(os.path.join(wdir, "to1", "main-menu.widget.json"), encoding="utf-8"))
    page = build_page(main)
    os.makedirs(out_dir, exist_ok=True)
    bg = nr.preview_bg(os.path.join(tempfile.gettempdir(), "ach-bg.png"))
    tab = demo_table()
    R = rows_of(tab)
    seen = SEEN_T0 - 5 * 86400
    views = [("top", dict(foc=(0, 0))), ("locked", dict(foc=(1, 3))), ("scrolled", dict(foc=(4, 2), row0=2, offs={3: 4})),
             ("hidden", dict(foc=(5, 1), row0=3))]
    out = []
    for name, kw in views:
        fr, fc = kw["foc"]
        if fc >= len(R[fr][1]):
            kw["foc"] = (fr, len(R[fr][1]) - 1)
        tmp = os.path.join(tempfile.gettempdir(), f"t2r-ach-{name}.widget.json")
        json.dump(demo(page, tab, seen_t=seen, **kw), open(tmp, "w", encoding="utf-8"))
        out.append(widget_preview.render(tmp, os.path.join(out_dir, f"ach-{name}.png"), bg=bg))
    return out


# ---- the unlock card (the top-left notification style of the game, like "New Journal Entry added" ... "Unlocked Achievement: <name>")
# = TLOU2's own SP notification widget hud-notifications/new-item-root (its card hud-tutorial/tutorial-bg inlined in place of the Reference),
# copied item for item out of the same gui2-widgets.pak onto the menu pages, top left. Names get the prefix achNt (unique page-wide); the root
# animation timeline of the SP widget cannot be played on a page, so its keyframes are dropped and achieve_ui.c plays the card (slide + fade in,
# hold, fade out) and its chime (the MP rewards level-up wave, achc_chime). The sweep mask (maskAnimation) is kept hidden. Icon = the achievement art,
# fitted into the SP icon slot (156 wide).
CARD_PAGES = ("main-menu", "find-match-menu", "clan13x", "clan-postmatch", PAGE)
CARD_X, CARD_Y, CARD_S = 1440, 115, 0.8                  # left edge / centre line (canvas units from the top) / size of the card: the empty band at the
                                                         # top centre of every card page (SP spot: left edge, y 300 = over the main menu WEEK header);
                                                         # achieve_ui.c moves it per card so the icon + text sit at the screen centre, the box round them
CARD_MASK = "hud/texture-masks/gradient-center-inverted.png"
CARD_REN = {"root": "achNt", "fader": "achNtFd", "group": "achNtGr", "maskAnimation": "achNtMk", "itemIcon": "achNtIc", "textGroup": "achNtTg",
            "itemName": "achNtName", "actionText": "achNtAct", "masked": "achNtBgM", "blurGroup": "achNtBgBl", "bgGroup": "achNtBgG", "icon": "achNtBgIc",
            "blur": "achNtBgBlur", "blurMask": "achNtBgBlurMk", "gradient": "achNtBgGrad", "polyline1": "achNtBgL1", "polyline": "achNtBgL0", "bgMask": "achNtBgMk"}


def card_items(wdir, parent):
    nir = json.load(open(os.path.join(wdir, "hud-notifications", "new-item-root.widget.json"), encoding="utf-8"))
    tbg = json.load(open(os.path.join(wdir, "hud-tutorial", "tutorial-bg.widget.json"), encoding="utf-8"))
    gm = {}
    out = []

    def g(old):
        if old not in gm:
            gm[old] = t2guid.guid()
        return gm[old]
    for i in nir["items"]:
        if i["name"] == "bg":                            # the Reference -> tutorial-bg's own items, its root takes the Reference's rect
            ref = i
            for j in tbg["items"]:
                k = copy.deepcopy(j)
                k["animation"] = {"keyframes": {}}
                k["guid"] = g(k["guid"])
                if j.get("parent") is None:
                    for key in [x for x in ref if x.startswith(("anchor", "pivot", "rect", "scale", "layoutMode", "depth"))]:
                        k[key] = ref[key]
                    k["guid"] = g(ref["guid"]); gm[j["guid"]] = k["guid"]
                    k["parent"] = g(ref["parent"]); k["name"] = "achNtBg"
                else:
                    k["parent"] = g(j["parent"]); k["name"] = CARD_REN[j["name"]]
                if j["name"] in ("blurGroup", "bgGroup"):       # (the card at the top: rough at the beginning, ends softly): the SP
                    k.update({"pivotAs.x": 0.0, "rectSizeDelta.width": 0.0})   # card's 250-unit overhang under the left screen edge is gone, and
                if j["name"] in ("blurMask", "bgMask"):         # its right-end mask becomes the game's two-sided one (dark both ends, the shimmer
                    k.update({"path": CARD_MASK, "anchorMinN.x": 0.0, "anchorMaxN.x": 1.0, "anchorMinN.y": 0.0, "anchorMaxN.y": 1.0,   # mask) over
                              "pivotN.x": 0.5, "pivotN.y": 0.5, "pivotAs.x": 0.0, "pivotAs.y": 0.0,   # the whole box: soft at both ends. Masks
                              "rectSizeDelta.width": 0.0, "rectSizeDelta.height": 0.0})   # clamp at their edges, so the old 241x10 strip faded the full height
                out.append(k)
            continue
        k = copy.deepcopy(i)
        k["animation"] = {"keyframes": {}}
        k["guid"] = g(k["guid"]); k["name"] = CARD_REN[i["name"]]
        k["parent"] = g(i["parent"]) if i.get("parent") else parent
        if i["name"] == "root":                          # top centre of the page, hidden until achieve_ui.c shows it
            k.update({"anchorMinN.x": 0.0, "anchorMaxN.x": 0.0, "anchorMinN.y": 0.0, "anchorMaxN.y": 0.0, "pivotN.x": 0.0, "pivotN.y": 0.5,
                      "pivotAs.x": float(CARD_X), "pivotAs.y": float(CARD_Y), "scale.x": CARD_S, "scale.y": CARD_S,
                      "visible": 0})
        if i["name"] == "maskAnimation":
            k["visible"] = 0
        if i["name"] == "itemIcon":
            k.update({"path": "streaming/t2r/ach/hidden.png", "scaleMode": "StretchAspect", "autoSize": 0, "rectSizeDelta.width": 146.0})
        if i["name"] == "itemName":
            k["text"] = "Unlocked Achievement:"
        if i["name"] == "actionText":
            k["text"] = ""
        out.append(k)
    # (root items whose parent was the old root keep the mapped guid; the old root's own children point at the new root via gm)
    return out


def add_ach_card(wdir):
    """the unlock card on CARD_PAGES (the ones that exist). Returns how many pages got it."""
    n = 0
    for name in CARD_PAGES:
        path = os.path.join(wdir, "to1", name + ".widget.json")
        if not os.path.exists(path):
            continue
        page = json.load(open(path, encoding="utf-8"))
        if any(i["name"] == "achNt" for i in page["items"]):
            continue
        anim = next(i for i in page["items"] if i["name"] == "anim-group")
        items = card_items(wdir, anim["guid"])
        have = {i["name"] for i in page["items"]}
        assert not have & {i["name"] for i in items}, "card names clash on " + name
        page["items"] += items
        json.dump(page, open(path, "w", encoding="utf-8"), indent=4)
        n += 1
    return n


def add_ach_card_hud(wdir):
    """the same card in hud-root (achievements show as unlocked the moment they unlock, not at the end of the match):
    achieve.c's live unlocks show it during the match (achieve_ui.c, place = the match HUD). Same top-centre spot: above the top-centre message
    (y 406) and the styled notification (from y ~230). Returns the items added (0 = already there)."""
    path = os.path.join(wdir, "hud-root.widget.json")
    w = json.load(open(path, encoding="utf-8"))
    if any(i["name"] == "achNt" for i in w["items"]):
        return 0
    root = next(i for i in w["items"] if i["name"] == "root")
    items = card_items(wdir, root["guid"])
    for i in items:
        if i["name"] == "achNt":
            i["depth"] = 7.5                             # the HUD's message layer (topCenterMessage / the styled notification 7, banners 20+)
    assert not {i["name"] for i in w["items"]} & {i["name"] for i in items}, "card names clash in hud-root"
    w["items"] += items
    json.dump(w, open(path, "w", encoding="utf-8"), indent=4)
    return len(items)


def add_ach_page(wdir):
    main = json.load(open(os.path.join(wdir, "to1", "main-menu.widget.json"), encoding="utf-8"))
    pg = build_page(main)
    names = [i["name"] for i in pg["items"]]
    assert len(names) == len(set(names)), "duplicate widget names"
    json.dump(pg, open(os.path.join(wdir, "to1", PAGE + ".widget.json"), "w", encoding="utf-8"), indent=4)
    return len(names)


if __name__ == "__main__":
    if sys.argv[1] == "--preview":                       # python achieve_widgets.py --preview <gui2 widgets dir> <out dir> <icons dir>
        for p in preview(sys.argv[2], sys.argv[3], sys.argv[4]):
            print(p)
        sys.exit(0)
    src, out = sys.argv[1], sys.argv[2]
    os.makedirs(os.path.join(out, "to1"), exist_ok=True)
    main = json.load(open(os.path.join(src, "to1", "main-menu.widget.json"), encoding="utf-8"))
    pg = build_page(main)
    json.dump(pg, open(os.path.join(out, "to1", PAGE + ".widget.json"), "w", encoding="utf-8"), indent=1)
    print("page ok:", len(pg["items"]), "widgets")
