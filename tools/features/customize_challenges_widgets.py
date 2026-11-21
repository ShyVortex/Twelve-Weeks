"""CUSTOMIZE | CHALLENGES (to1/customize-challenges) and the first-visit CHALLENGES tip on the CUSTOMIZE page (re/customize-1117.md
"Challenges page"; style re/ui-refs-1117/STYLE.md = the No Return challenge screens with a change to something more like a list
thats both vertical and horizontal not just horizontal, but in the same spirit").

Page = the shared No Return frame (nr_style.frame, ui-redesign-1117: breadcrumb CUSTOMIZE | CHALLENGES, dimmed blurred scene, boxed
prompts) with the Q / E strip WLF / SERAPHITES, then:
  rows    one per category that has unlocks (HEADWEAR, TORSO, LOWER, BACKPACK, FACE, MELEE STYLE): a grey caps header with N | M and a
          hairline (nr_style.section), a line of square-ish tiles (the item's own picture: colour when unlocked, the dark greyscale
          copy + a padlock while locked) with a thin progress bar under each. ROWS rows x COLS tiles on screen; the rows scroll up /
          down, each row scrolls left / right, the arrows / stick / d-pad move in both axes and keep the column between rows.
  focus   ONE white 4 px outline (nr_style.focus_frame) on the focused tile; unfocused tiles dimmed.
  detail  the right column: the item's picture big (the 2x colour picture, greyscale while locked), the challenge title in caps, its
          line in sentence case, N | M + a thin bar, "Unlocks:" + the reward chip (grey = locked, accent = done), a state line.
Images on screen: ROWS x COLS tiles + the padlock + the detail picture + the frame's (blur, Q / E, prompt glyphs) <= 30 of gui2's 32.

Tip (group czTip on the CUSTOMIZE page, opened once on the first visit, the No Return explainer re/ui-refs-1117/nr-challenges-tip.png):
grey CHALLENGES title + rule, the line, one card per faction with its starting look's two portraits (czb-<faction>-<sex>.png, greyscale)
and the faction's N | M, the closing line, rule, [select] CONTINUE.

Widget space 3840 x 2160."""
import copy
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
try:
    import nr_style as nr
except ImportError:          # (until ui-redesign-1117 is merged: its own copy, for the offline previews)
    sys.path.append(os.environ.get("T2R_NR_STYLE", "../t2r-wt/uiredo/tools/features"))
    import nr_style as nr
import t2guid  # noqa: E402
from clan_widgets import Builder, _templates  # noqa: E402

PAGE = "customize-challenges"
ICONS = "streaming/t2r/icons/"
FACS = ("wlf", "scar")
FAC_TAB = ("WLF", "SERAPHITES")
ROW_CATS = ("hat", "torso", "lower", "backpack", "face", "melee", "mask")          # = customize_items.CATS without SEX (the ext's row order)
ROW_LABEL = {"hat": "HEADWEAR", "torso": "TORSO", "lower": "LOWER", "backpack": "BACKPACK", "face": "FACE", "melee": "MELEE STYLE", "mask": "MASK"}

# ------------------------------------------------------------------ geometry
X0 = nr.L0                          # rows: left margin ...
TW, TH, TGAP = 300, 275, 24         # tile = the CUSTOMIZE card (the 1x greyscale picture draws 1:1)
COLS, ROWS = 6, 3
X1 = X0 + COLS * TW + (COLS - 1) * TGAP          # ... 2068
ROW_Y0, ROW_P = 440, 440            # first row header centre line, row pitch
TILE_DY = 46                        # header line -> tile top
BAR_DY = TH + 16                    # tile top -> its progress bar
SB_X = X1 + 60                      # rows scroll bar
D_X0, D_X1 = 2300, nr.R1            # detail column
D_ART_W, D_ART_H = 780, 715         # the 600 x 550 picture x 1.3
D_ART_Y = 400
D_TITLE_Y = D_ART_Y + D_ART_H + 70
NEW_R = 10


def tile_xy(r, c):
    return X0 + c * (TW + TGAP), ROW_Y0 + r * ROW_P + TILE_DY


def build_page(main):
    t, root0, anim0 = _templates(main)
    b = Builder(t)
    root = copy.deepcopy(root0); root.update(guid=t2guid.guid())
    anim = copy.deepcopy(anim0); anim.update(guid=t2guid.guid(), parent=root["guid"])
    b.items += [root, anim]
    a = anim["guid"]
    nr.frame(b, a, "CUSTOMIZE", "CHALLENGES", tabs_labels=list(FAC_TAB), active_tab=0, prompts=4)
    b.text("chTot", a, nr.lm(nr.R1 - 1400, nr.TAB_Y - 36, 1400, 72, right=1), "COMPLETED 0 | 0", nr.pt(24), nr.GREY, align=2, tracking=3)
    rows = b.group("rows", a, b.tl(0, 0, 3840, 2160))["guid"]
    for r in range(ROWS):
        y = ROW_Y0 + r * ROW_P
        nr.section(b, rows, f"rw{r}", X0, X1, y, "TORSO", "0 | 0")
        for c in range(COLS):
            x, ty = tile_xy(r, c)
            g = nr.plain_tile(b, rows, f"t{r}_{c}", x, ty, TW, TH)
            b.image(f"t{r}_{c}P", g, b.fill(), ICONS + "cz-torso.png", 0xFFFFFFFF, 255)
            b.image(f"t{r}_{c}I", g, b.ctr(TW / 2, TH / 2 - 10, 150, 150), ICONS + "cz-melee.png", 0xFFFFFFFF, 200,
                    scaleMode="StretchAspect", visible=0)            # an item without a picture (fists / knife): the icon
            b.image(f"t{r}_{c}L", g, b.ctr(TW / 2, TH / 2, 72, 72), ICONS + "cz-lock.png", 0xFFFFFFFF, 255, visible=0)
            nr.dot(b, g, f"t{r}_{c}N", TW - 26, 26, NEW_R, visible=0)
            nr.bar(b, rows, f"t{r}_{c}B", x, x + TW, ty + BAR_DY, h=4)
            b.rect(f"t{r}_{c}H", g, b.fill(), nr.WHITE, nr.HIT_A)
        nr.scroll_h(b, rows, f"rs{r}", X0, X1, ROW_Y0 + r * ROW_P + TILE_DY + BAR_DY + 30, visible=0)
        b.items[-1]["color.a"] = 110                                  # (the row's scroll thumb: quieter than the tiles' own bars)
        b.items[-1]["rectSizeDelta.height"] = 4.0
    nr.focus_frame(b, rows, "foc", th=4)
    nr.scroll_v(b, rows, "sbV", SB_X, ROW_Y0 - 20, ROW_Y0 + (ROWS - 1) * ROW_P + TILE_DY + BAR_DY + 8, visible=0)
    # ------------------------------------------------------------ detail column
    d = b.group("det", a, b.tl(0, 0, 3840, 2160))["guid"]
    b.rect("dBg", d, b.tl(D_X0 - 40, D_ART_Y - 40, D_X1 - D_X0 + 80, 1600 - D_ART_Y + 40 + 200), nr.TILE, 120)
    b.image("dArt", d, b.tl((D_X0 + D_X1 - D_ART_W) / 2, D_ART_Y, D_ART_W, D_ART_H), ICONS + "cz-torso.png", 0xFFFFFFFF, 255)
    b.image("dIc", d, b.ctr((D_X0 + D_X1) / 2, D_ART_Y + D_ART_H / 2, 300, 300), ICONS + "cz-melee.png", 0xFFFFFFFF, 220,
            scaleMode="StretchAspect", visible=0)
    b.image("dLock", d, b.ctr((D_X0 + D_X1) / 2, D_ART_Y + D_ART_H / 2, 120, 120), ICONS + "cz-lock.png", 0xFFFFFFFF, 255, visible=0)
    b.rect("dRule", d, b.tl(D_X0, D_TITLE_Y - 60, D_X1 - D_X0, 2), nr.WHITE, nr.HAIR_A)
    b.text("dTitle", d, nr.lm(D_X0, D_TITLE_Y - 45, D_X1 - D_X0, 90), "TITLE", nr.HEAD_PT, nr.WHITE, tracking=3)
    b.text("dDesc", d, b.tl(D_X0, D_TITLE_Y + 50, D_X1 - D_X0, 120), "", nr.pt(22), nr.WHITE, multiline=1, tracking=1)
    nr.bar(b, d, "dBar", D_X0, D_X1 - 260, D_TITLE_Y + 210, h=6)
    b.text("dCnt", d, nr.lm(D_X1 - 240, D_TITLE_Y + 213 - 34, 240, 68, right=1), "0 | 0", nr.pt(24), nr.WHITE, align=2, tracking=2)
    b.text("dUnl", d, nr.lm(D_X0, D_TITLE_Y + 300 - 30, 400, 60), "Unlocks:", nr.pt(22), nr.GREY, tracking=1)
    nr.chip(b, d, "dChip", D_X0 + 190, D_TITLE_Y + 300 - 28, "TORSO - COAT I", style="grey")      # locked
    nr.chip(b, d, "dChipA", D_X0 + 190, D_TITLE_Y + 300 - 28, "TORSO - COAT I", style="acc")      # unlocked (no tint setter: two chips)
    b.items[-2]["visible"] = b.items[-1]["visible"] = 0
    b.text("dState", d, nr.lm(D_X0, D_TITLE_Y + 390 - 30, D_X1 - D_X0, 60), "", nr.pt(20), nr.GREY, tracking=2)
    w = {k: copy.deepcopy(v) for k, v in main.items() if k != "items"}
    w["items"] = b.items
    return w


# ------------------------------------------------------------------ the tip (built into the CUSTOMIZE page: customize_widgets)
TIP_X0, TIP_X1 = 1050, 2870         # = the No Return tip x 2 (title / rules 525 .. 1435 at 1080p)
TIP_CX = (TIP_X0 + TIP_X1) / 2
TIP_CARD_Y, TIP_CARD_H = 724, 860
BUST_W, BUST_GAP, CARD_GAP = 500, 28, 48
TIP_LINE1 = 'Completing <font color="#ffffff">Challenges</font> will permanently unlock new outfits, headwear, faces and more.'
TIP_LINE2 = 'You can view your <font color="#ffffff">Challenges</font> any time from the <font color="#ffffff">CUSTOMIZE</font> page.'
TIP_TEXT = 0xFFD2D2D2


def tip_card_x(k):
    cw = 2 * BUST_W + BUST_GAP
    x0 = TIP_CX - (2 * cw + CARD_GAP) / 2
    return x0 + k * (cw + CARD_GAP), cw


def build_tip(b, a):
    """czTip: hidden; customize.c shows it (and hides the grid: image budget) on the first visit, select / back closes it."""
    g = b.group("czTip", a, b.tl(0, 0, 3840, 2160), visible=0)["guid"]
    b.image("tipBlur", g, b.bleed(), "general-textures/blur-background.png", 0xFFFFFFFF, 255)   # the live menu blur, as the pages
    b.rect("tipDim", g, b.bleed(), 0xFF000000, 200)                                            # ... dimmed: the scene stays readable
    b.text("tipTitle", g, nr.lm(TIP_X0, 432 - 45, 1400, 90), "CHALLENGES", nr.HEAD_PT, nr.GREY, tracking=3)
    b.rect("tipRule0", g, b.tl(TIP_X0, 494, TIP_X1 - TIP_X0, 2), nr.WHITE, nr.HAIR_A)
    b.text("tipLine1", g, b.tl(TIP_X0 - 60, 528, TIP_X1 - TIP_X0 + 120, 140), TIP_LINE1, nr.pt(24), TIP_TEXT, align=1, multiline=1, tracking=1)
    b.rect("tipRule1", g, b.tl(tip_card_x(0)[0], TIP_CARD_Y - 2, tip_card_x(1)[0] + tip_card_x(1)[1] - tip_card_x(0)[0], 2), nr.WHITE, nr.HAIR_A)
    for k, fac in enumerate(FACS):
        x, cw = tip_card_x(k)
        c = b.group(f"tipC{k}", g, b.tl(x, TIP_CARD_Y, cw, TIP_CARD_H))["guid"]
        b.rect(f"tipC{k}Bg", c, b.fill(), 0xFF101010, 255)
        for j, sex in enumerate(("m", "f")):
            b.image(f"tipC{k}P{j}", c, b.tl(j * (BUST_W + BUST_GAP), 0, BUST_W, TIP_CARD_H), ICONS + f"czb-{fac}-{sex}.png", 0xFFFFFFFF, 255)
        b.text(f"tipC{k}Nm", c, nr.lm(14, 52 - 45, 1000, 90), FAC_TAB[k], nr.pt(30), nr.WHITE, tracking=2)
        b.text(f"tipC{k}Ct", c, nr.lm(14, 118 - 34, 600, 68), "0 | 0", nr.pt(24), nr.WHITE, tracking=2)
    b.text("tipLine2", g, b.tl(TIP_X0 - 60, 1660, TIP_X1 - TIP_X0 + 120, 80), TIP_LINE2, nr.pt(24), TIP_TEXT, align=1, tracking=1)
    b.rect("tipRule2", g, b.tl(TIP_X0, 1758, TIP_X1 - TIP_X0, 2), nr.WHITE, nr.HAIR_A)
    lw = nr.est("CONTINUE", nr.pt(28)) * 1.06                    # (customize.c re-places the glyph from the measured label)
    b.image("tipKey", g, b.ctr(TIP_X1 - lw - 22 - 32, 1816, 64, 56), "menu:select", 0xFFFFFFFF, scaleMode="StretchAspect")
    b.text("tipCont", g, nr.lm(TIP_X1 - 600, 1816 - 40, 600, 80, right=1), "CONTINUE", nr.pt(28), nr.WHITE, align=2, tracking=2)
    b.rect("tipHit", g, b.tl(TIP_X1 - lw - 90, 1760, lw + 90, 110), nr.WHITE, nr.HIT_A)
    return g


# ------------------------------------------------------------------ offline previews (filled the way customize.c fills the page)
def sentence(u, CI):
    """A challenge line in sentence case (STYLE: caps for names, sentence case for descriptions); map names keep their capitals."""
    s = CI.unlock_text(u)
    mp = CI.U_MAPS[u[2]][1] if u[0] == "mapwins" else None
    s = s.lower()
    s = s[0].upper() + s[1:]
    if mp:
        s = s.replace(mp.lower(), mp.title())
    return s + "."


def rows_of(CI, fac, sex):
    """[(cat, [item, ...])] the items with a challenge, per category, in list order."""
    T = CI.table()[(fac, sex)]
    out = []
    for c in ROW_CATS:
        its = [it for it in T[c] if it.get("unlock")]
        if its:
            out.append((c, its))
    return out


def demo(page, fac="wlf", sex="m", foc=(0, 0), row0=0, offs=None, prog=None, seen=()):
    import customize_items as CI
    import customize_widgets as CW
    prog = prog or {}
    offs = offs or {}
    w = copy.deepcopy(page)
    by = {i["name"]: i for i in w["items"]}
    nr.demo_header(by, "CUSTOMIZE", "CHALLENGES")
    nr.demo_tabs(by, list(FAC_TAB), FACS.index(fac))
    nr.demo_chips(by)
    R = rows_of(CI, fac, sex)
    tot = sum(len(its) for _, its in R)
    done = sum(1 for _, its in R for it in its if not CW.locked(it, prog))
    by["chTot"]["text"] = "COMPLETED %d | %d" % (done, tot)
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
        cat, its = R[ri]
        n_done = sum(1 for it in its if not CW.locked(it, prog))
        nr.demo_section(by, f"rw{r}", X0, X1, ROW_LABEL[cat], "%d | %d" % (n_done, len(its)))
        off = offs.get(ri, 0)
        for c in range(COLS):
            k = off + c
            on = k < len(its)
            by[f"t{r}_{c}"]["visible"] = int(on)
            by[f"t{r}_{c}BT"]["visible"] = int(on)
            if not on:
                by[f"t{r}_{c}BF"]["visible"] = 0
                continue
            it = its[k]
            lk = CW.locked(it, prog)
            f = (ri, k) == (fr, fc)
            pic = CI.card_pic(cat, it)
            P, I = by[f"t{r}_{c}P"], by[f"t{r}_{c}I"]
            P["visible"], I["visible"] = int(bool(pic)), int(not pic)
            if pic:
                P["path"] = ICONS + (("czg-" + pic[4:]) if lk else pic) + ".png"
                P["color.a"] = 255 if f else (200 if lk else 150)
            else:
                I["path"] = ICONS + (("cz-knife" if "KNIFE" in it["label"].upper() else "cz-fists") if cat == "melee" else "cz-" + cat) + ".png"
                I["color.a"] = 255 if f else (90 if lk else 150)
            by[f"t{r}_{c}L"]["visible"] = int(lk)
            by[f"t{r}_{c}L"]["color.a"] = 255 if f else 170
            by[f"t{r}_{c}Bg"]["color.a"] = nr.TILE_FA if f else nr.TILE_A
            by[f"t{r}_{c}N"]["visible"] = int(not lk and (cat, it["label"]) not in seen)
            u = it["unlock"]
            nr.demo_bar(by, f"t{r}_{c}B", 0, TW, min(1.0, CW.progress(u, prog) / float(u[1])))
            by[f"t{r}_{c}BF"]["pivotAs.x"] = float(tile_xy(r, c)[0])
            by[f"t{r}_{c}BF"]["color.a"] = 255 if f else 150
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
    # detail
    cat, its = R[fr]
    it = its[fc]
    u = it["unlock"]
    lk = CW.locked(it, prog)
    pic = CI.card_pic(cat, it)
    by["dArt"]["visible"], by["dIc"]["visible"] = int(bool(pic)), int(not pic)
    if pic:
        by["dArt"]["path"] = ICONS + pic + ".png"
        by["dArt"]["color.a"] = 150 if lk else 255
    by["dLock"]["visible"] = 0
    by["dTitle"]["text"] = CI.unlock_title(u)
    by["dDesc"]["text"] = sentence(u, CI)
    p = min(CW.progress(u, prog), u[1])
    nr.demo_bar(by, "dBar", D_X0, D_X1 - 260, p / float(u[1]))
    by["dCnt"]["text"] = "%d | %d" % (p, u[1])
    lab = it["label"]
    chip = lab if lab.split()[0] in ROW_LABEL[cat].split() else "%s - %s" % (ROW_LABEL[cat], lab)     # (TORSO 02, not TORSO - TORSO 02)
    for n, on in (("dChip", lk), ("dChipA", not lk)):
        by[n + "Tx"]["text"] = chip
        by[n + "Bg"]["rectSizeDelta.width"] = float(nr.est(chip, by[n + "Tx"]["pointSize"]) * 1.06 + 32)
        by[n + "Tx"]["visible"] = by[n + "Bg"]["visible"] = int(on)
    by["dState"]["text"] = "LOCKED" if lk else "UNLOCKED"
    eq = not lk
    nr.demo_prompts(by, [("Q E", "SWITCH FACTION", True, "menu:prev"), ("", "EQUIP", eq, "menu:select"),
                         ("", "BACK", True, "menu:back")])
    return w


def demo_tip(page, prog=None):
    """The CUSTOMIZE page with the tip open (the grid hidden, as customize.c does)."""
    import customize_items as CI
    import customize_widgets as CW
    prog = prog or {}
    w = copy.deepcopy(page)
    by = {i["name"]: i for i in w["items"]}
    by["czTip"]["visible"] = 1
    for n in ("grid", "tabs", "title", "titleDiv", "titleSub", "titleRule", "secName", "secRule", "mdlName", "pHint", "logoF", "logoB",
              "chkF", "chkB", "pBackIc", "pBackTx", "pSelIc", "pSelTx", "pSwIc", "pSwTx", "pChKb", "pChKt", "pChTx"):    # (customize.c: the page under the tip)
        by[n]["visible"] = 0
    for k, fac in enumerate(FACS):
        n = d = 0
        for sex in ("m", "f"):
            for _, its in rows_of(CI, fac, sex):
                n += len(its)
                d += sum(1 for it in its if not CW.locked(it, prog))
        by[f"tipC{k}Ct"]["text"] = "%d | %d" % (d, n)
    return w


def preview(wdir, out_dir):
    import tempfile
    import widget_preview
    sys.path.insert(0, os.path.join(HERE, "..", "models"))
    import real_icons
    import customize_icons
    import customize_widgets as CW
    main = json.load(open(os.path.join(wdir, "to1", "main-menu.widget.json"), encoding="utf-8"))
    page = build_page(main)
    os.makedirs(out_dir, exist_ok=True)
    icd = os.path.join(tempfile.gettempdir(), "cz-icons")
    os.makedirs(icd, exist_ok=True)
    for n, fn in customize_icons.ICONS.items():
        fn().save(os.path.join(icd, n + ".png"))
    real_icons.MOD_DIRS.append(customize_icons.CARDS)
    real_icons.MOD_DIRS.append(icd)
    bg = nr.preview_bg(os.path.join(tempfile.gettempdir(), "cz-ch-bg.png"))
    mid = {"weeks": 6, "rank": 1, "survivors": 23, "revives": 31, "safes": 2, ("mapwins", 1): 4, ("mapwins", 0): 7, "downs": 140,
           "executions": 38, "headshots": 12, "marks": 61, "streak": 5, "assists": 27, "downs-9mm": 22, "melee-downs": 9, "gifts": 4,
           "heals": 11, "long-range-downs": 9, "crafts": 14}
    import customize_items as CI
    seen = set()
    views = [("wlf", dict(fac="wlf", foc=(1, 1), prog=mid)),
             ("wlf-locked", dict(fac="wlf", foc=(0, 4), prog=mid)),
             ("wlf-scrolled", dict(fac="wlf", foc=(4, 2), row0=2, prog=mid)),
             ("scar-female", dict(fac="scar", sex="f", foc=(1, 7), offs={1: 3}, prog=mid))]
    out = []
    for name, kw in views:
        tmp = os.path.join(tempfile.gettempdir(), f"t2r-cz-ch-{name}.widget.json")
        json.dump(demo(page, seen=seen, **kw), open(tmp, "w", encoding="utf-8"))
        out.append(widget_preview.render(tmp, os.path.join(out_dir, f"challenges-{name}.png"), bg=bg))
    cpage = CW.build_page(main)
    tmp = os.path.join(tempfile.gettempdir(), "t2r-cz-tip.widget.json")
    json.dump(demo_tip(CW.demo(cpage, prog=mid), prog=mid), open(tmp, "w", encoding="utf-8"))
    # tipBlur = the engine's live menu blur (widget_preview skips it): the blurred scene stands in for it
    out.append(widget_preview.render(tmp, os.path.join(out_dir, "challenges-tip.png"), bg=bg))
    del CI
    return out


if __name__ == "__main__":
    for p in preview(sys.argv[1], sys.argv[2]):
        print(p)
