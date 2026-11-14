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
import json
import os
import sys

import t2guid  # noqa: F401  (Builder uses it)
from clan_widgets import Builder, _templates

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
NAMES = (("SERAPHITES", ["Ellis", "Jordan", "Lena", "Marek"]), ("WLF", ["Tommy", "Kasia", "Dina", "Owen"]))
STATS = [("1325", "6", "2", "3", "1"), ("980", "4", "1", "4", "0"), ("640", "2", "0", "5", "2"), ("310", "1", "0", "6", "0")]


MOCK_OVERRIDE = {}           # preview only: texts the engine / t2r-ext write at run time (round 2 Polish previews)


def _scene(size):
    from PIL import Image, ImageDraw
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


if __name__ == "__main__":
    var = sys.argv[3] if len(sys.argv) > 3 else "A"
    if var != "before":
        restyle_pause(sys.argv[1], var)
    render(sys.argv[1], sys.argv[2], scale=0.5, before=var == "before")
