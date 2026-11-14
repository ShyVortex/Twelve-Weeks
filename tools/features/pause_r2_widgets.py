"""to1/pause-menu round 2: the in-match Esc page redrawn 2013-Factions-inspired (heavy condensed type, worn grit ground, framed panels,
solid team header bands) instead of round 1's thin wide-tracked entry-loading look.  Variants A2 / B2 / C2, selected with
T2R_PAUSE_RESTYLE=1 T2R_PAUSE_VARIANT=A2|B2|C2 (widgets_patch.py; default OFF = the current page; A / B / C = round 1).
Called from pause_restyle_widgets.restyle_pause() for any variant ending in "2".

Widget contract identical to round 1 (every name winmm / t2r-ext writes is kept: teamN_name, teamN_rowK_*, pauseTimer.pzTime(B),
pauseMission.pmMis1/2 + pmBarFill/Bg, menuList buttons, scoreBanner (parked), pzScore.pzAlly / pzEnemy mirrored by t2r-ext).  Added widgets reuse
the names t2r-ext already shows/hides with the page (pzLight = the grit ground image, pzRules = hairlines + panel frames, pzScore, pzFoot,
pzClockLabel), so NO ext change is needed over round 1.
Type: titles / team names use faceId "Design" (the heavy title face of to1/result banner), everything else the Default menu face with a bigger
point size and tracking 1-3 (round 1: 6-14).  In-game check: if "Design" lacks the Polish diacritics set T2R_UI_R2_FACE=Default.
Texture: streaming/t2r/clan/r2-grit.png (1920x1080, ui_r2_common.grit; tools/models/figures/ship.py generates it when T2R_UI_R2=1).
Preview:  python pause_r2_widgets.py <extracted widget dir> <out png> <A2|B2|C2>   (dir = gui2 extract with add_pause_widgets applied)"""
import json
import os
import sys

from clan_widgets import Builder, _templates
from pause_restyle_widgets import PAGE, _col, _put, _text, render

W, H = 3840, 2160
CREAM, DIM, FAINT = 0xFFD8D3C6, 0xFF8E8B82, 0xFF5C5A54
BLUE, RED = 0xFF8EC3EA, 0xFFE06A5E                       # lives numbers (lighter than team bands so they read on grit)
TEAM = (0xFF3E92C4, 0xFFC24A4A)                          # team bands (Seraphites blue / WLF red, muted)
DARK = 0xFF121314
GRIT = "streaming/t2r/clan/r2-grit.png"
FACE = os.environ.get("T2R_UI_R2_FACE", "Default")   # The post-match WEEK n: DAY d header = Default 86 pt tracking 6, colour D8D4CC (clan_widgets pmTitle)
HEAD_PT, HEAD_TRACK, HEAD_COL = 86, 6, 0xFFD8D4CC
ROW_PT = 46                                                 # scoreboard rows: sized around the stock menu buttons (not enlarged)
L, R = 140, 3700                                          # margins: the PL column heads (WSKRZESZENIA) need ~200 units per column, so the tables run nearly edge to edge

# per variant -----------------------------------------------------------------------------------------------------------------------------
# title (x, y, pt) | rule (x0, x1, y) | menu (x, y) | clock (x, y, w, h, pt, align, label_xy|None) | score (label_xy|None, y, pt, cx) | mission (x, y, w) |
# tables [(x0, x1, yh)] + name_w + pitch + band h + header pt | frames [(x0, y0, x1, y1)] hairline panels with corner ticks | rules [(x0, x1, y)]
V = {
    # A2: left rail (menu, clock, lives, mission) + one wide scoreboard; heavy team bands; no boxes except the bands
    "A2": dict(title=(L, 200, 210), rule=(L, R, 400), menu=(L, 500), clock=(L, 1040, 760, 230, 190, 0, (L, 986)),
               score=((L, 1330), 1440, 130, L + 150), mission=(L, 1590, 760),
               tables=[(1160, R, 440), (1160, R, 1090)], name_w=1000, pitch=112, band=92, hdr_pt=34, frames=[], rules=[(1060, 1060, 0)]),
    # B2: two framed panels (left: menu / clock / lives / mission, right: scoreboard) with corner ticks = the 2013 gear-up cards
    "B2": dict(title=(L, 190, 210), rule=(L, R, 366), menu=(L + 70, 470), clock=(L + 70, 1010, 700, 220, 180, 0, (L + 70, 950)),
               score=((L + 70, 1330), 1440, 120, L + 220), mission=(L + 70, 1590, 640),
               tables=[(1140, R - 60, 470), (1140, R - 60, 1130)], name_w=980, pitch=108, band=88, hdr_pt=32,
               frames=[(L, 400, 980, 1960), (1080, 400, R, 1960)], rules=[(L + 70, 920, 920), (L + 70, 920, 1290), (L + 70, 920, 1600)]),
    # C2: top bar (title | clock + lives | mission), the two teams side by side, options bottom left
    "C2": dict(title=(L + 10, 130, HEAD_PT), rule=(L + 10, 2300, 320), menu=(L + 10, 1400), clock=(1920 - 380, 100, 760, 150, HEAD_PT, 1, None),
               score=(None, 410, HEAD_PT, 1920), mission=(2640, 100, 960),
               tables=[(L, 1880, 520), (1960, R, 520)], name_w=700, pitch=130, band=120, hdr_pt=18, name_pt=64,
               frames=[], rules=[(L + 10, R - 10, 1300)]),
}


def _size(it, pt, align=0, tracking=1.0):
    """Size / alignment only: the widget keeps its colour (team coloured player names and numbers are written by the game / t2r-ext)."""
    it.update({"pointSize": pt, "alignH": align, "alignV": 1, "effect": "Regular", "tracking.x": float(tracking)})


def restyle_pause_r2(wdir, variant="A2"):
    v = V[variant]
    path = os.path.join(wdir, PAGE)
    if not os.path.exists(path):
        return 0
    page = json.load(open(path, encoding="utf-8"))
    items = page["items"]
    if any(i["name"] == "pzScore" for i in items):
        return 0
    by = {i["name"]: i for i in items}
    main = json.load(open(os.path.join(wdir, "to1", "main-menu.widget.json"), encoding="utf-8"))
    t, _, _ = _templates(main)
    for c in t.values():
        for k in ("engineClass", "tags", "animationsPath"):
            c.pop(k, None)
    anim = by["anim-group"]["guid"]
    b = Builder(t)

    def hide(*names):
        for n in names:
            if n in by:
                by[n]["color.a"] = 0

    def heavy(it):
        it["faceId"] = FACE

    # ground: the stock scrim stays (it dims the game behind), the grit image is the page ground, the other round-1 hidden bits as before
    _col(by["scrim"], 0xFF0B0C0D, 255)
    grit = b.image("pzLight", anim, b.tl(0, 0, W, H), GRIT, 0xFFFFFFFF, 255, depth=0.5)
    hide("cardBlur", "cardBg", "cardLineTop", "cardLineBottom", *[f"colsep{k}" for k in range(5)])

    # title + options
    tx, ty, tp = v["title"]
    _put(by["title"], tx, ty, 2000, tp * 1.3)
    _text(by["title"], tp, HEAD_COL, 0, HEAD_TRACK)
    heavy(by["title"])
    by["menuList"].update({"pivotAs.x": float(v["menu"][0]), "pivotAs.y": float(v["menu"][1]), "flowSpacing": 44.0})
    rules = b.group("pzRules", anim, b.tl(0, 0, W, H), depth=4.4)["guid"]
    x0, x1, y = v["rule"]
    b.line("pzRuleTitle", rules, x0, y, x1, y, CREAM, 150, 4.0)
    for k, (a, c, yy) in enumerate(v["rules"]):
        if yy:
            b.line(f"pzRule{k}", rules, a, yy, c, yy, CREAM, 70, 2.0)
    for k, (fx0, fy0, fx1, fy1) in enumerate(v["frames"]):          # panel: hairline frame + bold corner ticks
        b.frame(f"pzFrame{k}", rules, b.tl(fx0, fy0, fx1 - fx0, fy1 - fy0), CREAM, 60, 2.0)
        for j, (cx, cy, sx, sy) in enumerate(((fx0, fy0, 1, 1), (fx1, fy0, -1, 1), (fx0, fy1, 1, -1), (fx1, fy1, -1, -1))):
            b.line(f"pzTick{k}_{j}a", rules, cx, cy, cx + sx * 56, cy, CREAM, 230, 6.0)
            b.line(f"pzTick{k}_{j}b", rules, cx, cy, cx, cy + sy * 56, CREAM, 230, 6.0)
    ft = by["footerLine"]
    ft.update({"rectSizeDelta.width": -480.0, "pivotAs.x": 0.0, "pivotAs.y": -170.0})
    ft["color.a"] = 90
    by["buttonLegend"].update({"pivotAs.x": -240.0, "pivotAs.y": -75.0})
    ff = b.text("pzFoot", anim, b.tl(430, 2012, 1200, 80), "TWELVE WEEKS", 40, DIM, tracking=6, depth=4.4)
    ff["faceId"] = FACE

    # clock / lives / mission
    cx_, cy_, cw_, ch_, cpt, cal, clab = v["clock"]
    g = by["pauseTimer"]
    _put(g, cx_, cy_, cw_, ch_)
    hide("pzBlur", "pzBg", "pzLineL", "pzLineR")
    for n in ("pzTime", "pzTimeB"):
        _put(by[n], 0, 0, cw_, ch_)
        _text(by[n], cpt, HEAD_COL, cal, 3)
        heavy(by[n])
    if clab:
        lb = b.text("pzClockLabel", anim, b.tl(clab[0], clab[1], 900, 70), "MATCH TIME", 56, DIM, tracking=3, depth=4.4)
        lb["faceId"] = FACE
    lab, sy, spt, sx = v["score"]
    sg = b.group("pzScore", anim, b.tl(0, 0, W, H), depth=4.5)["guid"]
    if lab:
        lb = b.text("pzScoreLabel", sg, b.tl(lab[0], lab[1], 900, 70), "LIVES", 56, DIM, tracking=3)
        lb["faceId"] = FACE
    bw = int(spt * 2.0)
    for nm, cxx, col, al, txt in (("pzAlly", sx - 24 - bw / 2, TEAM[0] | 0, 2, "20"), ("pzEnemy", sx + 24 + bw / 2, TEAM[1], 0, "20")):
        it = b.text(nm, sg, b.ctr(cxx, sy, bw, spt * 1.6), txt, spt, BLUE if nm == "pzAlly" else RED, align=al, tracking=1)
        it["faceId"] = FACE
    cl = b.text("pzColon", sg, b.ctr(sx, sy - spt * 0.06, 60, spt * 1.6), ":", spt, DIM, align=1)
    cl["faceId"] = FACE
    by["scoreBanner"]["pivotAs.y"] = -4000.0
    mx, my, mw = v["mission"]
    mg = by["pauseMission"]
    _put(mg, mx, my, mw, 300)
    hide("pmBlur", "pmBg", "pmLineL", "pmLineR")
    _put(by["pmHead"], 0, 0, mw, 70)
    _text(by["pmHead"], 46, DIM, 0, 3)
    heavy(by["pmHead"])
    _put(by["pmLine1"], 0, 84, mw, 2)
    by["pmLine1"]["color.a"] = 140
    _put(by["pmMis1"], 0, 100, mw, 80)
    _text(by["pmMis1"], 50, CREAM, 0, 1)
    _put(by["pmMis2"], 0, 186, mw, 60)
    _text(by["pmMis2"], 38, DIM, 0, 1)
    _put(by["pmBarBg"], 0, 262, mw, 16)
    _col(by["pmBarBg"], 0xFF000000, 150)
    _put(by["pmBarFill"], 0, 262, mw, 16)
    _col(by["pmBarFill"], BLUE, 255)

    # scoreboard: solid team band with the heavy team name + column heads, tinted rows, 2013 cream numbers
    nw, pitch, bh = v["name_w"], v["pitch"], v["band"]
    for team, (x0, x1, yh) in enumerate(v["tables"]):
        p = f"team{team}"
        cols = ("parts", "downs", "executions", "deaths", "revives")
        pitch_c = (x1 - x0 - nw) / 5.0
        _put(by[f"{p}_band"], (x0 + x1) / 2, yh + bh / 2, x1 - x0, bh, centre=True)
        _col(by[f"{p}_band"], TEAM[team], 235)
        _put(by[f"{p}_name"], x0 + 34, yh + bh / 2, nw - 34, bh - 8, centre=False)
        by[f"{p}_name"]["pivotN.y"] = 0.5
        _text(by[f"{p}_name"], v.get("name_pt", 72), 0xFFF4F0E6, 0, 4)
        heavy(by[f"{p}_name"])
        for c, cn in enumerate(cols):
            ccx = x0 + nw + pitch_c * (c + 0.5)
            _put(by[f"{p}_col_{cn}"], ccx, yh + bh / 2, pitch_c, 64, centre=True)
            _text(by[f"{p}_col_{cn}"], v["hdr_pt"], 0xFFF4F0E6, 1, 2)
        for k in range(4):
            ry = yh + bh + 8 + k * pitch
            rc = ry + pitch / 2
            _put(by[f"{p}_row{k}_bg"], (x0 + x1) / 2, rc, x1 - x0, pitch - 6, centre=True)
            _col(by[f"{p}_row{k}_bg"], 0xFFFFFFFF if k % 2 == 0 else 0xFF000000, 26 if k % 2 == 0 else 70)
            _put(by[f"{p}_row{k}_name"], x0 + 34, rc, nw - 330, 80, centre=False)
            by[f"{p}_row{k}_name"]["pivotN.y"] = 0.5
            _size(by[f"{p}_row{k}_name"], ROW_PT, 0, 1)             # keeps the stock (team coloured) names
            for c, cn in enumerate(cols):
                ccx = x0 + nw + pitch_c * (c + 0.5)
                _put(by[f"{p}_row{k}_{cn}"], ccx, rc, pitch_c, 80, centre=True)
                _size(by[f"{p}_row{k}_{cn}"], ROW_PT, 1, 1)         # keeps the stock (team coloured) numbers
            png = by.get(f"{p}_row{k}_ping")
            if png:
                _put(png, x0 + nw - 100, rc, 200, 40, centre=False)
                png["pivotN.x"], png["pivotN.y"] = 1.0, 0.5
                _text(png, 34, DIM, 2, 1)
            ico = by.get(f"{p}_row{k}_input")
            if ico:
                _put(ico, x0 + nw - 90, rc, 76, 40, centre=False)
                ico["pivotN.y"] = 0.5
                _col(ico, DIM)

    b.items.remove(grit)
    at = next(k for k, i in enumerate(items) if i["name"] == "versionText")
    items[at:at] = b.items
    # the ground right after the scrim, ahead of the page content: at rest the engine draws in list order (depth only sorts while a page fades),
    # so a ground inserted before versionText covered the title, options and score banner once the fade ended (same as the gear up pages)
    items.insert(items.index(by["scrim"]) + 1, grit)
    json.dump(page, open(path, "w", encoding="utf-8"), indent=4)
    return len(b.items)


if __name__ == "__main__":
    os.environ["T2R_PREVIEW_R2"] = "1"
    restyle_pause_r2(sys.argv[1], sys.argv[3])
    render(sys.argv[1], sys.argv[2], scale=0.5)
