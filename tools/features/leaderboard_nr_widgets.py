"""to1/leaderboard (MULTIPLAYER > LEADERBOARDS) in the No Return frame (re/ui-redesign-1117/PROPOSAL.md, nr_style.py).

The stock page is filled by winmm itself (daemon op 0x13 / 0x14: top 10 by Elo, 0x30 bytes a row): it writes the text widgets
anim-group.table.row<r>_onlineid / _wins / _losses / _ratio / _elo (r 0..9), the positions row<r>_position are static. So those 60
widgets keep their names and parent, and only their place, size, face and colour change here (winmm writes strings only). Everything else of
the stock chrome (shade picture, the big title, the panel, the header bar, the column separators, the alternating row bars, the button
legend) is hidden - the widgets stay in the file because the page's animation tracks reference them.

New: the frame (nr_style.frame: blurred scene dimmed + a little extra black at the left, breadcrumb TWELVE WEEKS | LEADERBOARDS, one boxed
BACK prompt bottom right) and, per row, a hairline `lbRl<r>` and a hidden group `lbMe<r>` (fill, accent bar, a YOU chip) that t2r-ext
(tools/ext/lbnr.c) shows over the row of the player at this screen. The clan feed group (clanFeed, bottom strip) is untouched.

Columns (widget px, 3840 x 2160): POSITION left at 196, ONLINE ID left at 450, WINS / LOSSES / W/L / ELO right aligned at 2380 / 2780 / 3180 /
3640. White: position, name, ELO; grey: the column labels, wins, losses, W/L. python leaderboard_nr_widgets.py <extracted widget dir> <out dir>
renders previews."""
import copy
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import nr_style as nr  # noqa: E402
from clan_widgets import Builder, _templates  # noqa: E402

PAGE = "leaderboard"
NROWS = 10
HIDE = ("menuShade", "gameTitle", "menuTitle", "titleUnderline", "footerLine", "versionText", "buttonLegend", "hintBackIcon", "hintBackText",
        "panelBlur", "panelBg", "panelLineTop", "panelLineBottom", "headerBar", "colsep0", "colsep1", "colsep2", "colsep3", "colsep4")
COLS = (("position", 196, 160, 0), ("onlineid", 450, 1450, 0), ("wins", 2000, 380, 1), ("losses", 2400, 380, 1), ("ratio", 2800, 380, 1),
        ("elo", 3260, 380, 1))                     # name, x of the box, width, right aligned
LABEL_Y, RULE_Y, ROW_Y0, ROW_P, ROW_H = 380, 416, 450, 120, 112
PT_ROW, PT_LABEL = nr.pt(26), nr.pt(17)


def _place(it, x, y, w, h, right, pt, argb, tracking):
    it.update(nr.lm(x, y, w, h, right))
    it.update({"alignH": 2 if right else 0, "alignV": 1, "pointSize": pt, "tint.start": argb, "tint.end": argb, "tracking.x": float(tracking),
               "effect": "Regular", "visible": 1})


def row_y(r):
    return ROW_Y0 + r * ROW_P


def add_leaderboard_nr(wdir):
    """Edit to1/leaderboard.widget.json in the extracted widget folder. Returns the number of widgets added."""
    path = os.path.join(wdir, "to1", PAGE + ".widget.json")
    if not os.path.exists(path):
        return 0
    page = json.load(open(path, encoding="utf-8"))
    items = page["items"]
    if any(i["name"] == "hdPar" for i in items):
        return 0
    main = json.load(open(os.path.join(wdir, "to1", "main-menu.widget.json"), encoding="utf-8"))
    t, _, _ = _templates(main)
    anim = next(i for i in items if i["name"] == "anim-group")
    table = next(i for i in items if i["name"] == "table")
    by = {i["name"]: i for i in items}
    for nm in HIDE:
        if nm in by:
            by[nm]["visible"] = 0
    for r in range(NROWS):
        if f"row{r}_bg" in by:
            by[f"row{r}_bg"]["visible"] = 0
    # the 6 column labels + 10 x 6 row texts, in place
    for key, x, w, right in COLS:
        _place(by[f"hdr_{key}"], x, LABEL_Y - 30, w, 60, right, PT_LABEL, nr.GREY, 3)
        by[f"hdr_{key}"]["depth"] = 3.0
        for r in range(NROWS):
            white = key in ("position", "onlineid", "elo")
            _place(by[f"row{r}_{key}"], x, row_y(r), w, ROW_H, right, PT_ROW, nr.WHITE if white else nr.GREY, 2)
    b = Builder(t)
    b.items = []
    a = anim["guid"]
    nr.frame(b, a, "TWELVE WEEKS", "LEADERBOARDS", prompts=1)
    # the frame parts are the lowest items of the page (the stock chrome is hidden; the table is depth 2)
    for it in b.items:
        it["depth"] = min(it.get("depth", 0.0), 0.9)
    page_items = list(b.items)
    tb = Builder(t)
    tb.items = []
    tb.rect("lbRule", table["guid"], tb.tl(nr.L0, RULE_Y, nr.R1 - nr.L0, nr.HAIR), nr.WHITE, nr.HAIR_A, depth=2.5)
    for r in range(NROWS):
        y = row_y(r)
        tb.rect(f"lbRl{r}", table["guid"], tb.tl(nr.L0, y + ROW_H + 4, nr.R1 - nr.L0, nr.HAIR), nr.WHITE, nr.HAIR_A, depth=2.5)
        g = tb.group(f"lbMe{r}", table["guid"], tb.tl(0, 0, 3840, 2160), visible=0, depth=2.6)["guid"]
        tb.rect(f"lbMe{r}Bg", g, tb.tl(nr.L0, y - 4, nr.R1 - nr.L0, ROW_H + 8), nr.TILE, nr.TILE_FA)
        tb.rect(f"lbMe{r}Bar", g, tb.tl(nr.L0, y - 4, 8, ROW_H + 8), nr.ACC, 255)
        nr.chip(tb, g, f"lbMe{r}Yo", 1700, y + ROW_H / 2.0 - 12, "YOU", pts=nr.pt(17), style="acc")
    page_items += tb.items
    for it in page_items:
        it.setdefault("animation", {"keyframes": {}})
    # gui2 draws a page in item-list order (depth does not reorder siblings): the backdrop (bgBlur / bgDim / bgVig*) goes in front of every
    # stock item, else it covers the table (A/B: an empty page with only the breadcrumb and BACK); the rest of the frame stays on top
    back = [i for i in page_items if i["name"].startswith("bg")]
    at = items.index(anim) + 1
    items[at:at] = back
    items.extend(i for i in page_items if not i["name"].startswith("bg"))
    json.dump(page, open(path, "w", encoding="utf-8"), indent=4)
    return len(page_items)


# ------------------------------------------------------------------ offline preview
def demo(page, rows, me=-1, pad=False):
    """A copy of the page set up the way winmm + t2r-ext lbnr.c fill it. rows = [(name, wins, losses, ratio, elo)]."""
    w = copy.deepcopy(page)
    by = {i["name"]: i for i in w["items"]}
    nr.demo_chips(by)
    nr.demo_header(by, "TWELVE WEEKS", "LEADERBOARDS")
    nr.demo_prompts(by, [("ESC", "BACK", 1, "menu:back")])
    for r in range(NROWS):
        by[f"lbMe{r}"]["visible"] = int(r == me)
        if r < len(rows):
            n, wi, lo, ra, el = rows[r]
            by[f"row{r}_onlineid"]["text"] = n
            by[f"row{r}_wins"]["text"] = str(wi)
            by[f"row{r}_losses"]["text"] = str(lo)
            by[f"row{r}_ratio"]["text"] = "%.2f" % ra
            by[f"row{r}_elo"]["text"] = str(el)
        for k in ("position", "onlineid", "wins", "losses", "ratio", "elo"):
            by[f"row{r}_{k}"]["visible"] = int(r < len(rows))
        by[f"lbRl{r}"]["visible"] = int(r < len(rows))
    return w


def preview(wdir, out_dir):
    import tempfile
    sys.path.append(os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")))
    import t2rtmp  # noqa: F401
    import shutil
    import widget_preview
    os.makedirs(out_dir, exist_ok=True)
    tmp = tempfile.mkdtemp()
    os.makedirs(os.path.join(tmp, "to1"))
    for f in (PAGE, "main-menu"):
        shutil.copy(os.path.join(wdir, "to1", f + ".widget.json"), os.path.join(tmp, "to1"))
    print("widgets added:", add_leaderboard_nr(tmp))
    page = json.load(open(os.path.join(tmp, "to1", PAGE + ".widget.json"), encoding="utf-8"))
    print("items:", len(page["items"]))
    bg = nr.preview_bg(os.path.join(out_dir, "_bg.png"))
    rows = [("THEPIGGEHNINJA", 41, 12, 3.42, 1842), ("cdr1988", 38, 15, 2.53, 1797), ("Marlene", 33, 20, 1.65, 1730), ("KB-1993", 30, 21, 1.43, 1688),
            ("southprak", 27, 18, 1.50, 1650), ("ash_fall", 25, 25, 1.00, 1604), ("v0id", 19, 22, 0.86, 1561), ("TOBIAS", 17, 23, 0.74, 1520),
            ("Dina_77", 12, 20, 0.60, 1488), ("Jackal", 9, 18, 0.50, 1451)]
    for name, kw in (("lb-data", dict(rows=rows, me=4)), ("lb-few", dict(rows=rows[:4], me=-1))):
        f = os.path.join(tempfile.gettempdir(), "t2r-" + name + ".widget.json")
        json.dump(demo(page, **kw), open(f, "w", encoding="utf-8"))
        print(widget_preview.render(f, os.path.join(out_dir, name + ".png"), scale=0.5, bg=bg))
    shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    preview(sys.argv[1], sys.argv[2])
