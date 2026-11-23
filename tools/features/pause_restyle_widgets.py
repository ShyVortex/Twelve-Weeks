"""to1/pause-menu: the in-match Esc page (MENU + CHANGE LOADOUT / OPTIONS / LEAVE GAME, the 2-team scoreboard, the match clock, the
mission block). PENDED restyle (the scoreboard / options menu redone in the style of the entry loading screen, variant A of
connecting_widgets.py). Off by default: widgets_patch applies it only with T2R_PAUSE_RESTYLE=1 (T2R_PAUSE_VARIANT = A / B / C).

Family of the loading screen: the game dark behind (no boxes), a title block at the left (MENU, thin rule), wide-tracked small caps in the
launcher's cream #E6DFCF / dim #A8A292 / faint #6F6B60, hairlines instead of panels, a thin cream progress line. Every widget the engine or
t2r-ext writes keeps its name and kind (winmm: scoreboard teamN_name / teamN_rowK_* / ping / input, menuList buttons, scoreBanner;
t2r-ext: pauseTimer.pzTime(B), pauseMission.pmMis1/2 + pmBarFill/Bg, pause_items() visibility list). Only places, sizes, colours change, plus:
  pzScore (group: pzAlly / pzColon / pzEnemy lives, pzScoreLabel)  - the banner's lives were drawn by the embedded to1/score-banner copy,
      whose layout is the HUD's (not placeable per page); that Reference is parked off screen and t2r-ext mirrors its allyLives / enemyLives
      writes into pzAlly / pzEnemy (pause_mission_tick)
  pzRules (hairlines), pzClockLabel, pzFoot (small labels)
Widget space 3840 x 2160, y down.   python pause_restyle_widgets.py <extracted widget dir> <out png> [A|B|C|before]   renders a preview."""
import copy
import json
import os
import sys

import t2guid  # noqa: F401  (Builder uses it)
from clan_widgets import Builder, _templates
import nr_style as nr

W, H = 3840, 2160
CREAM, DIM, FAINT = 0xFFE6DFCF, 0xFFA8A292, 0xFF6F6B60
BLUE, RED = 0xFF48A8D8, 0xFFE04848
TEAM_ACC = (0xFF4A7FA6, 0xFFA8484A)        # team accent hairlines (muted versions of the HUD blue / red)
PAGE = os.path.join("to1", "pause-menu.widget.json")
L, R = 240, 3600

# per variant: title (x, y, pt) + rule (x0, x1, y) | menu (x, y) | clock (x, y, w, h, pt, align, label_xy|None) |
# score (label_xy|None, y, pt, cx)  - the lives row: centre of the colon cx, number box centre y |
# mission (x, y, w) | tables [(x0, x1, yh)] with name_w, row pitch, header pt | rules [(x0, x1, y)] extra hairlines
VARIANTS = {
    # A: left rail (title, options, clock, lives, mission) - the scoreboard fills the right two thirds; nothing boxed
    "A": dict(title=(L, 250, 118), rule=(L + 6, L + 760, 450), menu=(L, 520),
              clock=(L, 1050, 760, 170, 130, 0, (L, 1004)), score=((L, 1296), 1400, 100, L + 150), mission=(L, 1640, 760),
              tables=[(1300, R, 380), (1300, R, 1004)], name_w=950, pitch=96, hdr_pt=26, rules=[]),
    # B: slim top bar (title left, clock + lives centred), the two teams side by side, options bottom left, mission bottom right
    "B": dict(title=(L, 90, 84), rule=(L + 6, R, 330), menu=(L, 1360),
              clock=(1920 - 400, 80, 800, 170, 118, 1, None), score=(None, 300, 64, 1920), mission=(2700, 1360, 900),
              tables=[(L, 1780, 560), (2060, R, 560)], name_w=560, pitch=100, hdr_pt=22, rules=[(L, R, 1250)]),
    # C: title + options at the left, the table big at the right, a status strip (clock | lives | mission) under it
    "C": dict(title=(L, 200, 118), rule=(L + 6, L + 760, 400), menu=(L, 470),
              clock=(L, 1650, 700, 170, 120, 0, (L, 1590)), score=((1180, 1590), 1730, 100, 1330), mission=(2300, 1590, 1300),
              tables=[(1300, R, 300), (1300, R, 880)], name_w=950, pitch=100, hdr_pt=26, rules=[(L, R, 1520)]),
}


def _put(it, x, y, w, h, centre=False):
    """Absolute rect in the parent (top-left anchored); centre=True: x, y are the centre."""
    it.update({"anchorMinN.x": 0.0, "anchorMinN.y": 0.0, "anchorMaxN.x": 0.0, "anchorMaxN.y": 0.0,
               "pivotN.x": 0.5 if centre else 0.0, "pivotN.y": 0.5 if centre else 0.0,
               "pivotAs.x": float(x), "pivotAs.y": float(y), "rectSizeDelta.width": float(w), "rectSizeDelta.height": float(h)})


def _col(it, argb, alpha=None):
    it["tint.start"] = it["tint.end"] = argb
    if alpha is not None:
        it["color.a"] = alpha


def _text(it, pt, argb, align=0, tracking=2.0):
    it.update({"pointSize": pt, "alignH": align, "alignV": 1, "effect": "Regular", "tracking.x": float(tracking)})
    _col(it, argb)


def restyle_pause(wdir, variant="A"):
    """Rewrite to1/pause-menu.widget.json (after clan_widgets.add_pause_widgets). Returns the number of widgets added (0: done before)."""
    if variant.endswith("2"):              # round 2: 2013-Factions-inspired, heavy type, grit ground: pause_r2_widgets.py
        import pause_r2_widgets
        return pause_r2_widgets.restyle_pause_r2(wdir, variant)
    v = VARIANTS[variant]
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

    def hide(*names):                       # alpha 0, not visible 0: t2r-ext pause_items() flips visibility
        for n in names:
            if n in by:
                by[n]["color.a"] = 0

    # --- backdrop: the stock scrim darkened (loading screen: near-black, one soft light)
    _col(by["scrim"], 0xFF0B0C0D, 228)
    light = b.image("pzLight", anim, b.ctr(960 if variant != "B" else 1920, 1000, 3000, 2000),
                    "hud/player-menu/gradient/radial-gradient.png", 0xFFFFFFFF, 22, depth=0.5)
    light["depth"] = 0.5
    hide("cardBlur", "cardBg", "cardLineTop", "cardLineBottom", *[f"colsep{k}" for k in range(5)])

    # --- title block + options
    tx, ty, tp = v["title"]
    _put(by["title"], tx, ty, 1400, tp * 1.45)
    _text(by["title"], tp, CREAM, 0, 4)
    by["menuList"].update({"pivotAs.x": float(v["menu"][0]), "pivotAs.y": float(v["menu"][1]), "flowSpacing": 38.0})
    rules = b.group("pzRules", anim, b.tl(0, 0, W, H), depth=4.4)["guid"]
    if v["rule"]:
        b.line("pzRuleTitle", rules, v["rule"][0], v["rule"][2], v["rule"][1], v["rule"][2], 0xFFFFFFFF, 110, 2.0)
    for k, (x0, x1, y) in enumerate(v["rules"]):
        b.line(f"pzRule{k}", rules, x0, y, x1, y, 0xFFFFFFFF, 70, 2.0)
    # bottom row: the page's own footer hairline + legend on the margins, a small brand line at the left
    ft = by["footerLine"]
    ft.update({"rectSizeDelta.width": -480.0, "pivotAs.x": 0.0, "pivotAs.y": -170.0})
    ft["color.a"] = 70
    by["buttonLegend"].update({"pivotAs.x": -240.0, "pivotAs.y": -75.0})
    b.text("pzFoot", anim, b.tl(L, 2020, 1200, 70), "TWELVE WEEKS", 40, FAINT, tracking=14, depth=4.4)

    # --- match clock (group pauseTimer, shown by t2r-ext), lives row (pzScore), mission block
    cx_, cy_, cw_, ch_, cpt, cal, clab = v["clock"]
    g = by["pauseTimer"]
    _put(g, cx_, cy_, cw_, ch_)
    hide("pzBlur", "pzBg", "pzLineL", "pzLineR")
    for n in ("pzTime", "pzTimeB"):
        _put(by[n], 0, 0, cw_, ch_)
        _text(by[n], cpt, CREAM, cal, 6)
    if clab:
        b.text("pzClockLabel", anim, b.tl(clab[0], clab[1], 900, 60), "MATCH TIME", 38, DIM, tracking=10, depth=4.4)
    lab, sy, spt, sx = v["score"]
    sg = b.group("pzScore", anim, b.tl(0, 0, W, H), depth=4.5)["guid"]
    if lab:
        b.text("pzScoreLabel", sg, b.tl(lab[0], lab[1], 900, 60), "LIVES", 38, DIM, tracking=10)
    bw = int(spt * 2.0)
    b.text("pzAlly", sg, b.ctr(sx - 20 - bw / 2, sy, bw, spt * 1.6), "20", spt, BLUE, align=2, tracking=2)
    b.text("pzColon", sg, b.ctr(sx, sy - spt * 0.06, 60, spt * 1.6), ":", spt, FAINT, align=1)
    b.text("pzEnemy", sg, b.ctr(sx + 20 + bw / 2, sy, bw, spt * 1.6), "20", spt, RED, align=0, tracking=2)
    # the banner copy: parked far off screen (its writes keep arriving, t2r-ext mirrors the lives into pzAlly / pzEnemy)
    by["scoreBanner"]["pivotAs.y"] = -4000.0
    mx, my, mw = v["mission"]
    mg = by["pauseMission"]
    _put(mg, mx, my, mw, 250)
    hide("pmBlur", "pmBg", "pmLineL", "pmLineR")
    _put(by["pmHead"], 0, 0, mw, 60)
    _text(by["pmHead"], 38, DIM, 0, 10)
    _put(by["pmLine1"], 0, 74, mw, 1)
    by["pmLine1"]["color.a"] = 110
    _put(by["pmMis1"], 0, 96, mw, 66)
    _text(by["pmMis1"], 46, CREAM, 0, 3)
    _put(by["pmMis2"], 0, 160, mw, 56)
    _text(by["pmMis2"], 38, DIM, 0, 3)
    _put(by["pmBarBg"], 0, 238, mw, 3)
    _col(by["pmBarBg"], 0xFF2A2C2E, 255)
    _put(by["pmBarFill"], 0, 238, mw, 3)
    _col(by["pmBarFill"], CREAM, 255)

    # --- scoreboard: two tables, hairline headers, hairline rows
    nw = v["name_w"]
    for team, (x0, x1, yh) in enumerate(v["tables"]):
        p = f"team{team}"
        cols = ("parts", "downs", "executions", "deaths", "revives")
        pitch_c = (x1 - x0 - nw) / 5.0
        _put(by[f"{p}_band"], (x0 + x1) / 2, yh + 52, x1 - x0, 3, centre=True)
        _col(by[f"{p}_band"], TEAM_ACC[team], 255)
        _put(by[f"{p}_name"], x0, yh, nw, 70, centre=False)
        by[f"{p}_name"]["pivotN.y"] = 0.5
        by[f"{p}_name"]["pivotAs.y"] = float(yh)
        _text(by[f"{p}_name"], 42, CREAM, 0, 8)
        for c, cn in enumerate(cols):
            ccx = x0 + nw + pitch_c * (c + 0.5)
            _put(by[f"{p}_col_{cn}"], ccx, yh, pitch_c, 58, centre=True)
            _text(by[f"{p}_col_{cn}"], v["hdr_pt"], DIM, 1, 3)
        for k in range(4):
            ry = yh + 66 + k * v["pitch"]
            rc = ry + v["pitch"] / 2
            _put(by[f"{p}_row{k}_bg"], (x0 + x1) / 2, ry + v["pitch"] - 1, x1 - x0, 2, centre=True)
            _col(by[f"{p}_row{k}_bg"], 0xFFFFFFFF, 26)
            _put(by[f"{p}_row{k}_name"], x0, rc, nw - 330, 66, centre=False)
            by[f"{p}_row{k}_name"]["pivotN.y"] = 0.5
            _text(by[f"{p}_row{k}_name"], 40, CREAM, 0, 4)
            for c, cn in enumerate(cols):
                ccx = x0 + nw + pitch_c * (c + 0.5)
                _put(by[f"{p}_row{k}_{cn}"], ccx, rc, pitch_c, 66, centre=True)
                _text(by[f"{p}_row{k}_{cn}"], 40, CREAM, 1, 2)
            png = by.get(f"{p}_row{k}_ping")
            if png:
                _put(png, x0 + nw - 100, rc, 200, 36, centre=False)
                png["pivotN.x"], png["pivotN.y"] = 1.0, 0.5
                _text(png, 26, FAINT, 2, 2)
            ico = by.get(f"{p}_row{k}_input")
            if ico:
                _put(ico, x0 + nw - 84, rc, 72, 36, centre=False)
                ico["pivotN.y"] = 0.5
                _col(ico, DIM)

    at = next(k for k, i in enumerate(items) if i["name"] == "versionText")
    items[at:at] = b.items
    json.dump(page, open(path, "w", encoding="utf-8"), indent=4)
    return len(b.items)


# ------------------------------------------------------------------ preview (PIL): reads the JSON it renders
NAMES = (("SERAPHITES", ["Ellis", "Brandon", "Lena", "Marek"]), ("WLF", ["Tommy", "Kasia", "Dina", "Owen"]))
STATS = [("1325", "6", "2", "3", "1"), ("980", "4", "1", "4", "0"), ("640", "2", "0", "5", "2"), ("310", "1", "0", "6", "0")]


MOCK_OVERRIDE = {}           # preview only: texts the engine / t2r-ext write at run time (round 2 Polish previews)


def _scene(size):
    from PIL import Image, ImageDraw, ImageFilter
    img = Image.new("RGB", size, (40, 40, 38))
    d = ImageDraw.Draw(img)
    for y in range(size[1]):
        k = y / size[1]
        d.line([(0, y), (size[0], y)], fill=(int(70 - 40 * k), int(66 - 38 * k), int(58 - 34 * k)))
    for (x, y, r, c) in ((0.2, 0.45, 0.2, (150, 140, 110)), (0.62, 0.35, 0.12, (110, 130, 120)), (0.8, 0.7, 0.25, (60, 70, 60)),
                         (0.45, 0.8, 0.2, (140, 100, 70))):
        d.ellipse([(x - r) * size[0], (y - r) * size[1], (x + r) * size[0], (y + r) * size[1]], fill=c)
    d.rectangle([0, size[1] * 0.78, size[0], size[1]], fill=(40, 36, 30))
    return img


def render(wdir, out, scale=0.5, before=False):
    from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageOps
    items = json.load(open(os.path.join(wdir, PAGE), encoding="utf-8"))["items"]
    by = {i["guid"]: i for i in items}
    byn = {i["name"]: i for i in items}
    img = _scene((int(W * scale), int(H * scale)))
    blur = img.filter(ImageFilter.GaussianBlur(14))

    def argb(i):
        v = i.get("tint.start")
        if isinstance(v, str):
            return {"t2-bright-grey": (200, 200, 200), "t2-grey-text": (150, 150, 150)}.get(v, (255, 255, 255))
        return (v >> 16 & 255, v >> 8 & 255, v & 255)

    def rect_of(i):
        p = by.get(i.get("parent"))
        px, py, pw, ph = rect_of(p) if p else (0, 0, W, H)
        ax0, ay0 = px + i["anchorMinN.x"] * pw, py + i["anchorMinN.y"] * ph
        aw, ah = (i["anchorMaxN.x"] - i["anchorMinN.x"]) * pw, (i["anchorMaxN.y"] - i["anchorMinN.y"]) * ph
        ww, hh = aw + i["rectSizeDelta.width"], ah + i["rectSizeDelta.height"]
        return (ax0 + i["pivotN.x"] * aw + i["pivotAs.x"] - i["pivotN.x"] * ww,
                ay0 + i["pivotN.y"] * ah + i["pivotAs.y"] - i["pivotN.y"] * hh, ww, hh)

    fonts = {}

    def font(pt, face="Default"):
        if (pt, face) not in fonts:
            if face == "Design" or face == "Alternate":       # round 2: the heavy condensed title face (stand-in: Bahnschrift 700 / width 86)
                f = ImageFont.truetype("C:/Windows/Fonts/bahnschrift.ttf", max(8, int(pt * (1.33 if os.environ.get("T2R_PREVIEW_R2") else 0.78) * scale)))
                f.set_variation_by_axes([700, 86])
            elif os.environ.get("T2R_PREVIEW_R2"):             # round 2 body weight (the game's menu face is medium, not light); 1.33 px em per pt = widget_preview's measured in-game size
                f = ImageFont.truetype("C:/Windows/Fonts/bahnschrift.ttf", max(8, int(pt * 1.33 * scale)))
                f.set_variation_by_axes([600, 100])
            else:
                f = ImageFont.truetype("C:/Windows/Fonts/bahnschrift.ttf", max(8, int(pt * 0.78 * scale)))
            fonts[(pt, face)] = f
        return fonts[(pt, face)]

    def dkey(i):
        k = []
        while i:
            k.append(i.get("depth", 0.0))
            i = by.get(i.get("parent"))
        return k[::-1]

    mock = {"pzTime": "12:34", "pzAlly": "20", "pzEnemy": "14", "pmMis1": "4/10 Down enemies", "pmMis2": "Day 2/3", "pzColon": ":"}
    mock.update(MOCK_OVERRIDE)
    for t, (tn, pl) in enumerate(NAMES):
        mock.setdefault(f"team{t}_name", tn)
        for k in range(4):
            mock[f"team{t}_row{k}_name"] = pl[k]
            for c, cn in enumerate(("parts", "downs", "executions", "deaths", "revives")):
                mock[f"team{t}_row{k}_{cn}"] = STATS[k][c]
            mock[f"team{t}_row{k}_ping"] = f"{34 + 9 * k} ms"
    for i in sorted(items, key=dkey):
        p, vis = i, True
        while p:
            vis = vis and (p.get("visible", 1) or p["name"] in ("pauseTimer", "pauseMission"))    # (t2r-ext shows both)
            p = by.get(p.get("parent"))
        if not vis or i["class"] in ("Group",):
            continue
        if i["name"] in ("pzTimeB",):
            continue
        x, y, ww, hh = [q * scale for q in rect_of(i)]
        a = i.get("color.a", 255) / 255.0
        if a <= 0:
            continue
        if i["class"] == "Reference":
            if i["name"] in ("changeLoadout", "options", "leaveGame"):
                f = font(46)
                k = ("changeLoadout", "options", "leaveGame").index(i["name"])
                y += k * (56 + byn["menuList"]["flowSpacing"]) * scale
                sel = k == 0
                d = ImageDraw.Draw(img)
                d.text((x, y + (hh - f.size) / 2 - 3), _spaced(i["text"], 4), font=f, fill=(235, 235, 235) if sel else (150, 150, 150))
            continue
        if i["class"] == "Image":
            pth = i.get("path", "")
            if "radial-gradient" in pth:
                g = ImageOps.invert(Image.radial_gradient("L")).point(lambda q: max(0, q - 74) * 255 // 181)
                g = g.resize((max(1, int(ww)), max(1, int(hh)))).point(lambda q: int(q * a))
                img.paste(Image.new("RGB", g.size, (255, 255, 255)), (int(x), int(y)), g)
            elif "blur-background" in pth:
                box = (int(x), int(y), int(x + ww), int(y + hh))
                img.paste(blur.crop(box), box[:2], Image.new("L", (box[2] - box[0], box[3] - box[1]), int(255 * a)))
            elif "r2-grit" in pth:
                import ui_r2_common
                g = ui_r2_common.grit(int(W * scale), int(H * scale))
                img.paste(g.crop((0, 0, int(ww), int(hh))).resize((int(ww), int(hh))), (int(x), int(y)))
            elif pth.endswith(".svg"):
                ImageDraw.Draw(img).rectangle([x, y + hh * 0.2, x + ww, y + hh * 0.8], outline=argb(i), width=1)
            elif pth.startswith("menu:"):
                dd = ImageDraw.Draw(img)           # the engine's input prompt is WHITE (A / B on a pad): white circle + letter
                r = min(ww, hh) * 0.36
                cx, cy = x + ww / 2, y + hh / 2
                dd.ellipse([cx - r, cy - r, cx + r, cy + r], outline=(255, 255, 255), width=2)
                dd.text((cx, cy), "B" if "Back" in i["name"] else "A", font=font(int(r * 1.1 / 0.39), "Default"), fill=(255, 255, 255), anchor="mm")
            else:
                if i["name"] == "pmBarFill":
                    ww *= 0.4
                ov = Image.new("RGB", (max(1, int(ww)), max(1, int(hh))), argb(i))
                img.paste(ov, (int(x), int(y)), Image.new("L", ov.size, int(255 * a)))
        elif i["class"] == "Polyline":
            uv = i["pointsUv"]
            pts = [(x + uv[k] * ww, y + uv[k + 1] * hh) for k in range(0, len(uv), 2)]
            if i.get("closed"):
                pts.append(pts[0])
            c = tuple(int(q * a + bg * (1 - a)) for q, bg in zip(argb(i), (40, 40, 40)))
            ImageDraw.Draw(img).line(pts, fill=c, width=max(1, int(i.get("lineWidth", 2) * scale)))
        elif i["class"] == "Text":
            txt = mock.get(i["name"], i.get("text", ""))
            if "<font" in txt:
                txt = txt.split(">")[1].split("<")[0]
            if not txt:
                continue
            f = font(i["pointSize"], i.get("faceId", "Default"))
            tr = i.get("tracking.x", 0.0) * scale
            tw = sum(f.getlength(ch) + tr for ch in txt) - tr
            al = i.get("alignH", 0)
            tx = x if al == 0 else (x + ww - tw if al == 2 else x + (ww - tw) / 2)
            ty = y + (hh - f.size) / 2 - f.size * 0.08
            d = ImageDraw.Draw(img)
            col = tuple(int(q * a + 60 * (1 - a)) for q in argb(i))
            for ch in txt:
                d.text((tx, ty), ch, font=f, fill=col)
                tx += f.getlength(ch) + tr
    img.save(out)


def _spaced(s, n):
    return s


# ================================================================== UI redesign: the in-match pages in the No Return frame
# to1/pause-menu (the Esc page: MENU, match clock, mission, CLAN NEWS, the two team blocks) and to1/scoreboard (the scoreboard page) wear the frame of
# PLAYER STATS (clan13_widgets.build_stats_page): backdrop, breadcrumb <MODE> | MENU / SCOREBOARD, one grey column head line, US / THE ENEMY section rows with
# team totals, flat tile rows, the own row = accent edge bar + YOU tag, rank badges (rank_badge_widgets.add_scoreboards), numbers right aligned.
# Everything winmm / t2r-ext writes keeps its name and kind (teamN_name, teamN_row<r>_name / parts / downs / executions / deaths / revives / ping / input / bg, the
# column heads teamN_col_*, menuList, scoreBanner, pauseTimer.pzTime, pauseMission.pmMis1 / pmMis2 / pmBarBg / pmBarFill, pauseStatus.pst0-3): only place, size,
# colour change. New (named for t2r-ext sbteam.c / clancard.c): per block teamN_tag (US / THE ENEMY), teamN_rl (rule), teamN_tot_<col> (team totals); per row
# teamN_row<r>_me (accent edge bar) + _tag (YOU); sbLvA / sbLvE (+ labels) the lives; sbBlue / sbRed thin team edge bars (by PLACE: our team is the upper
# block); the page frame (bgDim / bgVig / bgBlur, hdPar / hdDiv / hdPage / hdRule, pbar boxed prompts on the pause page); pmSec* / psSec* section rows.
PNR_X0, PNR_X1 = nr.L0, nr.R1
PNR_RH, PNR_P, PNR_SEC = 96, 104, 56            # a row: height, pitch; the first row starts PNR_SEC under the section row's centre
PNR_D = 520                                     # block 1 = block 0 + PNR_D (sbteam.c swaps the blocks by the distance of the two team name widgets)
PNR_PT = nr.pt(26)                              # names / numbers
PNR_NAME_BOX = 900                              # the name's room (sbteam.c fits a longer one by scaling about its left end)
PNR_BADGE_X = PNR_X0 + 36
PNR_COLW = 330
PNR_COL_R = {"downs": PNR_X1 - 24 - 4 * 360, "executions": PNR_X1 - 24 - 3 * 360, "revives": PNR_X1 - 24 - 2 * 360, "deaths": PNR_X1 - 24 - 360,
             "parts": PNR_X1 - 24}
PNR_COL_ORDER = ("downs", "executions", "revives", "deaths", "parts")
PNR_PING_R, PNR_INPUT_X = 1860, 1560
PNR_RULE_X0, PNR_RULE_END = PNR_X0 + 700, 1400  # a section rule: the static start (sbteam.c places it after the team name + tag), its end (the lives sit after it)
PNR_LV_NUM_R, PNR_LV_LAB_R = 1800, 1730          # lives: number right edge, label right edge
PNR_BLUE, PNR_RED = 0xFF4A8FC2, 0xFFC24A4A
PNR_PAGES = {"pause-menu": dict(hd=780, s0=868), "scoreboard": dict(hd=528, s0=616)}
PNR_HIDE = ("scrim", "title", "footerLine", "buttonLegend", "cardBlur", "cardBg", "cardLineTop", "cardLineBottom", "versionText",
            "colsep0", "colsep1", "colsep2", "colsep3", "colsep4", "team0_band", "team1_band")
PNR_MENU = (PNR_X0, 300)                        # the native button list (pause page)
PNR_MIS = (1480, 400, 1060)                     # pauseMission: x, y, width (local coordinates inside it: section row at y 30)
PNR_NEWS = (2640, 400, 1060)                    # pauseStatus
PNR_CLK = (PNR_X0, 590, 900, 100)               # pauseTimer: under LEAVE GAME, left aligned
PNR_CLK_CAP_X = 250                             # MATCH TIME right of the clock (local x)
PNR_SECROW_Y = 30                               # the section row of pauseMission / pauseStatus (local y)


def pnr_name_x():
    """x of a player's name after the rank badge (rank_badge_widgets.add_scoreboards shifts the name right by reserved(): t2r-ext sbteam.c SBT_NAME_X = this)."""
    import rank_badge_widgets as rb
    return PNR_BADGE_X + rb.reserved(PNR_PT, 64)


def _pnr_place(it, x, y, w, h, right=0, pt=None, argb=None, tracking=None):
    it.update(nr.lm(x, y, w, h, right))
    it.update({"alignH": 2 if right else 0, "alignV": 1, "effect": "Regular", "visible": 1})
    if pt is not None:
        it["pointSize"] = pt
    if argb is not None:
        it["tint.start"] = it["tint.end"] = argb
        it["color.a"] = 255
    if tracking is not None:
        it["tracking.x"] = float(tracking)


def _pnr_text(it, text):
    """A static label whose English text is (re)set: the loc pass (loc_widgets.apply) moves it to a cipher again."""
    it["text"] = text
    if str(it.get("cipherId", "")).startswith("T2RL_"):
        it["cipherId"] = ""


def _pnr_rule_scale(it, x0, x1):
    """A rule built at RULE_W0 whose real length t2r-ext sets at run time: start with the right one (no flash of a 1000 long rule)."""
    it["pivotAs.x"] = float(x0)
    it["scale.x"] = float(max(2.0, x1 - x0) / nr.RULE_W0)


# the LEAVE GAME confirm box: the launch / kick
# notice look (notice_widgets.py) - dim, black box with the thin grey frame, a centred title, a rule, the message, two framed buttons (the focused
# one has the white frame), the prompts under the box. t2r-ext lq_tick shows it, moves the focus and fills lqMsg.
LQ_W = 1640                              # = notice_widgets.KN_W
LQ_BTN_W, LQ_BTN_H, LQ_BTN_GAP = 688, 124, 40


def lq_layout():
    """-> box-relative y of the title, rule, message, buttons + the box height (= notice_widgets.kick_layout, a 2-line message)"""
    y = 84
    L = {"title": y}
    y += 110 + 30
    L["rule"] = y
    y += 56
    L["msg"] = y
    y += 2 * 76 + 64
    L["btn"] = y
    y += LQ_BTN_H + 80
    L["h"] = y
    return L


def add_leave_box(b, a):
    """lqBox: lqDim, lqPanel(+Fr), lqTitle, lqRule, lqMsg, lqBtn0 (LEAVE MATCH) / lqBtn1 (STAY) with Bg / Fr / Fo / Tx, lqHint (select + back)"""
    import notice_widgets as nw
    L = lq_layout()
    bw, bh = LQ_W, L["h"]
    bx, by_ = (W - bw) / 2, (H - bh) / 2 - 40
    lq = b.group("lqBox", a, b.tl(0, 0, W, H), visible=0)["guid"]
    b.rect("lqDim", lq, b.bleed(), 0xFF000000, 215)     # (darker than the notice's 120: the busy scoreboard page is under it)
    box = b.group("lqPanelG", lq, b.tl(bx, by_, bw, bh))["guid"]
    b.rect("lqPanel", box, b.fill(), nw.FILL, 246)
    b.frame("lqPanelFr", box, b.fill(), 0xFF464646, 255, 2.0)
    inner = bw - 2 * nw.PAD
    b.text("lqTitle", box, b.tl(nw.PAD, L["title"], inner, 110), "ARE YOU SURE?", nw.KN_TITLE_PT, nw.WHITE, align=1, tracking=6)
    b.line("lqRule", box, nw.PAD, L["rule"], bw - nw.PAD, L["rule"], 0xFF3A3A3A, 255, 2.0)
    b.text("lqMsg", box, b.tl(nw.PAD, L["msg"], inner, 2 * nw.LINE), LQ_MSG_CLAN, nw.KN_MSG_PT, nw.BODY, align=1, multiline=1, valign=0, tracking=3)
    x0 = (bw - 2 * LQ_BTN_W - LQ_BTN_GAP) / 2
    for i, label in enumerate(("LEAVE MATCH", "STAY")):
        g = b.group("lqBtn%d" % i, box, b.tl(x0 + i * (LQ_BTN_W + LQ_BTN_GAP), L["btn"], LQ_BTN_W, LQ_BTN_H))["guid"]
        b.rect("lqBtn%dBg" % i, g, b.fill(), nw.BTN_FILL, 255)
        b.frame("lqBtn%dFr" % i, g, b.fill(), nw.FRAME, 255, 2.0)
        b.frame("lqBtn%dFo" % i, g, b.fill(), nw.FOCUS, 255, 4.0, visible=int(i == 1))     # STAY has the focus when the box comes up
        b.text("lqBtn%dTx" % i, g, b.fill(), label, nw.BTN_PT, nw.WHITE, align=1, tracking=4)
    hg = b.group("lqHint", lq, b.tl(bx, by_ + bh + 44, bw, 60))["guid"]
    b.image("lqHintIc0", hg, b.tl(0, 2, 56, 56), "menu:select", 0xFFFFFFFF)
    b.text("lqHintTx0", hg, b.tl(76, 0, 500, 60), "SELECT", nw.HINT_PT, nw.DIM, tracking=4)
    b.image("lqHintIc1", hg, b.tl(420, 2, 56, 56), "menu:back", 0xFFFFFFFF)
    b.text("lqHintTx1", hg, b.tl(496, 0, 600, 60), "STAY", nw.HINT_PT, nw.DIM, tracking=4)


LQ_MSG_CLAN = 'YOU ARE ABOUT TO LEAVE THE MATCH.\nYOUR CLAN <font color="#fd6d51">WILL SUFFER.</font>'     # = t2r-ext lq_fill


def add_pause_nr(wdir):
    """Restyle to1/pause-menu and to1/scoreboard. Idempotent. Returns the number of widgets added (both pages)."""
    import rank_badge_widgets as rb
    total = 0
    main = json.load(open(os.path.join(wdir, "to1", "main-menu.widget.json"), encoding="utf-8"))
    t, _, _ = _templates(main)
    for page, cfg in PNR_PAGES.items():
        path = os.path.join(wdir, "to1", page + ".widget.json")
        if not os.path.exists(path):
            continue
        w = json.load(open(path, encoding="utf-8"))
        items = w["items"]
        if any(i["name"] == "hdPar" for i in items):
            continue
        by = {i["name"]: i for i in items}
        if "team0_row0_name" not in by:
            continue
        pause = page == "pause-menu"
        anim = by["anim-group"]
        sbg = by["scoreboard"]["guid"]
        hd, s0 = cfg["hd"], cfg["s0"]
        for nm in PNR_HIDE:
            if nm in by:
                by[nm]["visible"] = 0
        if "scoreBanner" in by:
            by["scoreBanner"]["pivotAs.y"] = -4000.0          # parked: winmm / t2r-ext keep writing its texts, sbteam.c shows the lives in the section rows
        items[:] = [i for i in items if i["name"] not in ("sbBlue", "sbRed")]       # (sbteam_widgets' bands by colour: replaced by the thin edge bars below)
        if "resultText" in by:                                # VICTORY / DEFEAT (winmm writes it): the big white line at the right, like the week block
            _pnr_place(by["resultText"], nr.R1 - 1400, 270 - 40, 1400, 80, 1, nr.pt(30), nr.WHITE, 3)
        # ---- the two blocks, in place
        name_x = pnr_name_x()
        reserved = rb.reserved(PNR_PT, 64)
        for tm in (0, 1):
            sy = s0 + tm * PNR_D
            _pnr_place(by["team%d_name" % tm], PNR_X0, sy - 34, 1100, 68, 0, PNR_PT, nr.WHITE, 3)
            for r in range(4):
                top = sy + PNR_SEC + r * PNR_P
                bg = by["team%d_row%d_bg" % (tm, r)]
                bg.update(Builder.tl(PNR_X0, top, PNR_X1 - PNR_X0, PNR_RH))
                bg["tint.start"] = bg["tint.end"] = nr.TILE
                bg["color.a"] = nr.TILE_A
                _pnr_place(by["team%d_row%d_name" % (tm, r)], PNR_BADGE_X, top + (PNR_RH - 64) / 2.0, PNR_NAME_BOX + reserved, 64, 0, PNR_PT, nr.WHITE, 1)
                for col in PNR_COL_ORDER:
                    _pnr_place(by["team%d_row%d_%s" % (tm, r, col)], PNR_COL_R[col] - PNR_COLW, top + (PNR_RH - 64) / 2.0, PNR_COLW, 64, 1, PNR_PT, nr.WHITE, 2)
                _pnr_place(by["team%d_row%d_ping" % (tm, r)], PNR_PING_R - 220, top + (PNR_RH - 40) / 2.0, 220, 40, 1, nr.pt(17), nr.GREY, 2)
                ic = by["team%d_row%d_input" % (tm, r)]
                ic.update(Builder.tl(PNR_INPUT_X, top + (PNR_RH - 36) / 2.0, 72, 36))
                ic["color.a"] = 150
            for col in PNR_COL_ORDER:                          # ONE column head line (team 0's labels); team 1's are hidden
                c = by["team%d_col_%s" % (tm, col)]
                if tm == 0:
                    _pnr_place(c, PNR_COL_R[col] - PNR_COLW, hd - 22, PNR_COLW, 44, 1, nr.pt(15), nr.GREY, 2)
                    _pnr_text(c, col.upper())
                else:
                    c["visible"] = 0
        # ---- the stock chrome of the pause page
        if pause:
            by["menuList"].update(Builder.tl(PNR_MENU[0], PNR_MENU[1], 1000, 320))
            items[:] = [i for i in items if i["name"] not in ("pzBlur", "pzBg", "pzLineL", "pzLineR", "pmBlur", "pmBg", "pmLineL", "pmLineR", "pmHead", "pmLine1",
                                                              "psBlur", "psBg", "psLineL", "psLineR", "psHead", "psRule")]
            by = {i["name"]: i for i in items}
            cx, cy, cw, ch = PNR_CLK
            by["pauseTimer"].update(Builder.tl(cx, cy, cw, ch))
            for nm in ("pzTime", "pzTimeB"):
                _pnr_place(by[nm], 0, 0, PNR_CLK_CAP_X - 20, 100, 0, nr.pt(40), nr.WHITE, 3)
            by["pzTimeB"]["visible"] = 0                      # (the twin t2r-ext swaps in when the second changes)
            mx, my, mw = PNR_MIS
            by["pauseMission"].update(Builder.tl(mx, my, mw, 250))
            _pnr_place(by["pmMis1"], 0, 84, mw, 56, 0, nr.pt(24), nr.WHITE, 2)
            _pnr_place(by["pmMis2"], 0, 142, mw, 48, 0, nr.pt(20), nr.GREY, 2)
            for nm, al in (("pmBarBg", 40), ("pmBarFill", 255)):
                by[nm].update(Builder.tl(0, 214, mw, 6))
                by[nm]["tint.start"] = by[nm]["tint.end"] = nr.WHITE
                by[nm]["color.a"] = al
            nx, ny, nw = PNR_NEWS
            by["pauseStatus"].update(Builder.tl(nx, ny, nw, 330))
            for k in range(4):
                _pnr_place(by["pst%d" % k], 0, 84 + k * 56, nw, 56, 0, nr.pt(22), nr.WHITE, 2)
        # ---- new items
        b = Builder(t)
        b.items = []
        a = anim["guid"]
        if pause:
            nr.backdrop(b, a)
        else:                                                  # the scoreboard: no scene blur, a dim + the left vignette
            b.rect("bgDim", a, b.bleed(), nr.BLACK, 150)
            b.image("bgVig", a, b.tl(nr.VIG_X0, -2160, nr.VIG_W, 2160 * 3), nr.VIG_IMG, 0xFFFFFFFF, 200)
        back = list(b.items)
        b.items = []
        nr.header(b, a, "TWELVE WEEKS", "MENU" if pause else "SCOREBOARD")
        if pause:
            nr.prompt_slots(b, a, 3)                           # P FRIENDS / SELECT / BACK (chat.c ch_pause_prompts)
        for k, (nm, col) in enumerate((("sbBlue", PNR_BLUE), ("sbRed", PNR_RED))):         # thin team edge bars by PLACE: our team is the upper block
            top = s0 + k * PNR_D + PNR_SEC
            b.rect(nm, sbg, b.tl(PNR_X0, top, 6, 3 * PNR_P + PNR_RH), col, 230)
        b.text("pnrChPl", sbg, nr.lm(name_x, hd - 22, 600, 44), "PLAYER", nr.pt(15), nr.GREY, tracking=3)
        for tm in (0, 1):
            sy = s0 + tm * PNR_D
            b.text("team%d_tag" % tm, sbg, nr.lm(PNR_X0 + 300, sy - 24, 600, 48), "US" if tm == 0 else "THE ENEMY", nr.pt(18), nr.GREY, tracking=3)
            b.rect("team%d_rl" % tm, sbg, nr.lpiv(PNR_RULE_X0, sy - nr.HAIR / 2, nr.RULE_W0, nr.HAIR), nr.WHITE, 40)
            for col in PNR_COL_ORDER:
                b.text("team%d_tot_%s" % (tm, col), sbg, nr.lm(PNR_COL_R[col] - PNR_COLW, sy - 26, PNR_COLW, 52, right=1), "", nr.pt(22), nr.GREY, align=2,
                       tracking=2)
            for r in range(4):
                top = sy + PNR_SEC + r * PNR_P
                b.rect("team%d_row%d_me" % (tm, r), sbg, b.tl(PNR_X0, top, 6, PNR_RH), nr.ACC, 255, visible=0)
                b.text("team%d_row%d_tag" % (tm, r), sbg, nr.lm(name_x + 300, top + PNR_RH / 2.0 - 20, 200, 40), "", nr.pt(16), nr.GREY, tracking=3, visible=0)
        for k, (lv, lab) in enumerate((("sbLvA", "sbLvAl"), ("sbLvE", "sbLvEl"))):       # lives (sbteam.c): ally = the upper block
            sy = s0 + k * PNR_D
            b.text(lab, sbg, nr.lm(PNR_LV_LAB_R - 300, sy - 20, 300, 40, right=1), "LIVES", nr.pt(16), nr.GREY, align=2, tracking=3, visible=0)
            b.text(lv, sbg, nr.lm(PNR_LV_NUM_R - 100, sy - 26, 100, 52, right=1), "", nr.pt(22), nr.GREY, align=2, tracking=2, visible=0)
        if pause:
            by = {i["name"]: i for i in items}
            mx, my, mw = PNR_MIS
            nx, ny, nw = PNR_NEWS
            xa, xb = nr.section(b, by["pauseMission"]["guid"], "pmSec", 0, mw, PNR_SECROW_Y, "MISSION", "")
            xa2, xb2 = nr.section(b, by["pauseStatus"]["guid"], "psSec", 0, nw, PNR_SECROW_Y, "CLAN NEWS", "")
            b.text("pzCap", by["pauseTimer"]["guid"], nr.lm(PNR_CLK_CAP_X, 28, PNR_CLK[2] - PNR_CLK_CAP_X, 44), "MATCH TIME", nr.pt(20), nr.GREY, tracking=3)
            # LEAVE GAME's ARE YOU SURE box (restyled like the launch notice; t2r-ext lq_tick shows it while the leave is held)
            add_leave_box(b, a)
            for it in b.items:
                if it["name"] == "pmSecRl":
                    _pnr_rule_scale(it, xa, xb)
                elif it["name"] == "psSecRl":
                    _pnr_rule_scale(it, xa2, xb2)
        for it in b.items:
            if it["name"] in ("team0_rl", "team1_rl"):
                _pnr_rule_scale(it, PNR_RULE_X0, PNR_RULE_END)
            elif it["name"] == "hdRule":
                _pnr_rule_scale(it, it["pivotAs.x"], nr.R1)
        for k, it in enumerate(back):
            it["depth"] = k * 0.01                              # (gui2 draws in list order; the previews sort by depth: backdrop lowest, the new frame / marks above every stock item)
        for k, it in enumerate(b.items):
            it["depth"] = 9.0 + k * 0.001
        # the LEAVE GAME box and EVERY widget under it (A/B: only its direct children were moved, so the panel's title / message / buttons stayed
        # before the dim in the draw order and the box showed as a dark screen only)
        lq_ids = {i["guid"] for i in b.items if i["name"] == "lqBox"}
        while True:
            more = {i["guid"] for i in b.items if i.get("parent") in lq_ids} - lq_ids
            if not more:
                break
            lq_ids |= more
        for k, it in enumerate(i for i in b.items if i["guid"] in lq_ids):
            it["depth"] = 30.0 + k * 0.001                     # (the LEAVE GAME box over everything; it is also last in the list)
        for it in back + b.items:
            it.setdefault("animation", {"keyframes": {}})
        at = items.index(anim) + 1                              # gui2 draws in item-list order: the backdrop in front of every stock item, the frame on top
        items[at:at] = back
        b.items = [i for i in b.items if i["guid"] not in lq_ids] + [i for i in b.items if i["guid"] in lq_ids]
        items.extend(b.items)
        json.dump(w, open(path, "w", encoding="utf-8"), indent=4)
        total += len(back) + len(b.items)
    return total


# ------------------------------------------------------------------ offline previews of the two pages (filled the way sbteam.c / clancard.c / pause_mission_tick fill them)
PNR_SAMPLE = (("WLF", [("Vex", (5, 1, 2, 1, 140), 1, 31, 4), ("Tal", (3, 0, 1, 2, 90), 0, 48, 2), ("Rook", (2, 2, 0, 1, 60), 0, 95, 0), ("June", (1, 0, 3, 3, 40), 0, 142, 1)]),
              ("SERAPHITES", [("Mara", (6, 1, 0, 1, 120), 0, 28, 3), ("Ilsa", (2, 0, 1, 2, 70), 0, 61, 1), ("Zażółć Gęślą Jaźń Wojciech", (1, 0, 0, 3, 30), 0, 77, 0),
                              ("Kit", (0, 0, 0, 4, 10), 0, 233, 5)]))


def pnr_demo(page, which, sample=PNR_SAMPLE, lives=("12", "9"), clock="07:42"):
    """A copy of the page (pause-menu / scoreboard json) set up as t2r-ext + winmm fill it. sample = ((team name, [(name, (downs, execs, revives, deaths, parts), me, ping, rank)] ) x 2)."""
    w = copy.deepcopy(page)
    by = {i["name"]: i for i in w["items"]}
    pause = which == "pause-menu"
    for it in w["items"]:
        if it["name"] == "bgBlur":
            it["visible"] = 0                              # (the engine's live blur: the preview draws the blurred art under the page)
    for k in list(by):
        if k.startswith("pb") and k[2:3].isdigit():
            pass
    nr.demo_header(by, "SUPPLY RAID", "MENU" if pause else "SCOREBOARD")
    if "resultText" in by:
        by["resultText"]["text"] = "VICTORY"
    if pause:
        nr.demo_prompts(by, [("menu:select", "SELECT", True, "menu:select"), ("menu:back", "BACK", True, "menu:back")])
    by["team0_col_downs"]["visible"] = 1
    nr.demo_rule(by, "hdRule", by["hdRule"]["pivotAs.x"], nr.R1)
    by["hdRule"]["scale.x"] = 1.0
    heads = {"downs": "DOWNS", "executions": "EXECUTIONS", "revives": "REVIVES", "deaths": "DEATHS", "parts": "PARTS"}
    for col, tx in heads.items():
        by["team0_col_" + col]["text"] = tx
    sums = []
    for tm, (tname, rows) in enumerate(sample):
        by["team%d_name" % tm]["text"] = tname
        tag = "US" if tm == 0 else "THE ENEMY"
        by["team%d_tag" % tm]["text"] = tag
        xt = PNR_X0 + nr.est(tname, PNR_PT) * 1.06 + 36
        by["team%d_tag" % tm]["pivotAs.x"] = float(xt)
        xr = xt + nr.est(tag, nr.pt(18)) * 1.06 + 40
        by["team%d_rl" % tm]["scale.x"] = 1.0
        nr.demo_rule(by, "team%d_rl" % tm, xr, PNR_RULE_END)
        tot = [0] * 5
        for r, (nm, st, me, ping, rk) in enumerate(rows):
            n = by["team%d_row%d_name" % (tm, r)]
            n["text"] = nm
            est = nr.est(nm, PNR_PT) * 1.06
            box = PNR_NAME_BOX
            sc = min(1.0, box / est) if est else 1.0
            sc = max(sc, 0.6)
            if sc < 1.0:
                n["pointSize"] = max(8, int(round(PNR_PT * sc)))
            ex = pnr_name_x() + est * sc
            for ci, col in enumerate(PNR_COL_ORDER):
                v = st[ci] if col != "parts" else st[4]
                v = (st[0], st[1], st[2], st[3], st[4])[ci]
                by["team%d_row%d_%s" % (tm, r, col)]["text"] = str(v)
                tot[ci] += v
            by["team%d_row%d_ping" % (tm, r)]["text"] = "%d ms" % ping
            by["team%d_row%d_me" % (tm, r)]["visible"] = me
            by["team%d_row%d_tag" % (tm, r)]["visible"] = me
            by["team%d_row%d_tag" % (tm, r)]["text"] = '<font color="#D9D86A">YOU</font>' if me else ""
            by["team%d_row%d_tag" % (tm, r)]["pivotAs.x"] = float(ex + 28)
            by["team%d_row%d_bg" % (tm, r)]["color.a"] = nr.TILE_FA if me else nr.TILE_A
            for k, v in (("rkIcon", 1), ("rkNum", 1)):
                it = by.get("team%d_row%d_%s" % (tm, r, k))
                if it:
                    it["visible"] = v
                    if k == "rkNum":
                        it["text"] = str(rk + 3)
        for ci, col in enumerate(PNR_COL_ORDER):
            by["team%d_tot_%s" % (tm, col)]["text"] = str(tot[ci])
        sums.append(tot)
    by["sbLvA"]["text"], by["sbLvE"]["text"] = lives
    for k in ("sbLvA", "sbLvE", "sbLvAl", "sbLvEl"):
        by[k]["visible"] = 1
    if pause:
        by["pauseTimer"]["visible"] = 1
        by["pzTime"]["text"] = clock
        by["pauseMission"]["visible"] = 1
        by["pmMis1"]["text"] = "4/10 Down enemies"
        by["pmMis2"]["text"] = "Day 2/3"
        by["pmBarFill"]["rectSizeDelta.width"] = float(by["pmBarBg"]["rectSizeDelta.width"] * 0.4)
        nr.demo_section(by, "pmSec", 0, PNR_MIS[2], "MISSION", "")
        by["pmSecRl"]["scale.x"] = 1.0
        by["pauseStatus"]["visible"] = 1
        news = (("#9CA6B5", "CLAN SUPPLY", "Mara"), ("#F0B429", "HUNGRY", "Tal"), ("#6C9BF2", "GRIEVING", "Bo"))
        for k, (c, wd, nm) in enumerate(news):
            by["pst%d" % k]["text"] = '<font color="#8C8C8C">%s</font>  %s' % (wd, nm)
        nr.demo_section(by, "psSec", 0, PNR_NEWS[2], "CLAN NEWS", "")
        by["psSecRl"]["scale.x"] = 1.0
    return w


def nr_preview(wdir, out_dir):
    import shutil
    import tempfile
    import widget_preview
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
    import t2rtmp  # noqa: F401
    import rank_badge_widgets
    os.makedirs(out_dir, exist_ok=True)
    tmp = tempfile.mkdtemp()
    os.makedirs(os.path.join(tmp, "to1"))
    for f in ("main-menu", "pause-menu", "scoreboard"):
        shutil.copy(os.path.join(wdir, "to1", f + ".widget.json"), os.path.join(tmp, "to1"))
    print("widgets added:", add_pause_nr(tmp), "| rank badges:", rank_badge_widgets.add_scoreboards(tmp))
    bg = nr.preview_bg(os.path.join(out_dir, "_bg.png"))
    out = {}
    for which in ("pause-menu", "scoreboard"):
        page = json.load(open(os.path.join(tmp, "to1", which + ".widget.json"), encoding="utf-8"))
        vis = [i for i in page["items"] if i.get("visible", 1)]
        print(which, "items:", len(page["items"]), "| visible images:", sum(1 for i in vis if i.get("class") == "Image"), "| texts:", sum(1 for i in vis if i.get("class") == "Text"))
        out[which] = page
    longn = (PNR_SAMPLE[0], ("SERAPHITES", [("Zażółć Gęślą Jaźń Wojciech-Kowalski", (6, 1, 0, 1, 120), 0, 28, 3), ("Ilsa", (2, 0, 1, 2, 70), 0, 61, 1), ("Bo", (1, 0, 0, 3, 30), 0, 77, 0),
                                              ("Kit", (0, 0, 0, 4, 10), 0, 233, 5)]))
    cases = [("pause-menu", "pause-4v4", {}), ("scoreboard", "scoreboard-4v4", {}), ("scoreboard", "scoreboard-long-name", dict(sample=longn, lives=("3", "0"))),
             ("pause-menu", "pause-clock-low", dict(clock="00:28")), ("pause-menu", "pause-leave-confirm", {})]
    for which, name, kw in cases:
        f = os.path.join(tempfile.gettempdir(), "t2r-pnr-" + name + ".widget.json")
        d = pnr_demo(out[which], which, **kw)
        if name == "pause-leave-confirm":                      # the LEAVE GAME box up (t2r-ext lq_tick)
            for it in d["items"]:
                if it["name"] == "lqBox":
                    it["visible"] = 1
        json.dump(d, open(f, "w", encoding="utf-8"))
        print(widget_preview.render(f, os.path.join(out_dir, name + ".png"), scale=0.5, bg=bg))
    shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    if sys.argv[1] == "nr":
        nr_preview(sys.argv[2], sys.argv[3])
        sys.exit(0)
    var = sys.argv[3] if len(sys.argv) > 3 else "A"
    if var != "before":
        restyle_pause(sys.argv[1], var)
    render(sys.argv[1], sys.argv[2], scale=0.5, before=var == "before")
