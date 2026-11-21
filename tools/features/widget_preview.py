"""Rough offline preview of a gui2 *.widget.json (layout check, not a faithful renderer).

  python widget_preview.py <page.widget.json> <out.png> [--show name,name] [--hide name,name]
                           [--scale 0.5] [--bg ref.png]

Rect model (matches the shipped layouts: lobbyPanel, versionText ...): parent rect P, anchors
amin/amax (0..1 of P), size = anchor span + rectSizeDelta, pivot point = lerp(amin, amax, pivotN) * P
+ pivotAs, item rect = pivot - pivotN * size; y down. Rotation about the pivot, clockwise in
degrees (GUESS: the sign is not verified in game). Text: Bahnschrift (DIN-like) at pointSize px,
wrapped when multiline. Images: square-32px = flat colour, radial-gradient = soft disc,
blur-background = skipped, menu:* = a button glyph circle, streaming/t2r/clan/* = the
image from re/figures (tinted), streaming/t2r/icons/{supply,gear,person} = drawn by make_icons
(tinted), <font color="#rrggbb"> runs coloured. Alpha multiplies down the tree."""
import argparse
import json
import math
import re
import os
import sys

from PIL import Image, ImageDraw, ImageFont

PALETTE = {"t2-white": 0xFFE6E6E6, "t2-bright-grey": 0xFFBDBDBD, "t2-grey-text": 0xFF8C8C8C,
           "t2-red": 0xFFE04848, "t2-blue": 0xFF3FA9F5}
FONT = os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts", "bahnschrift.ttf")
# T2R_PREVIEW_FONT = the game's own menu face (DINPro-Medium, build/pc/main/core.psarc fonts/seriffont-Medium.otf, extracted read-only):
# previews then show the real glyph widths / weights instead of the Bahnschrift stand-in


def real_font():
    """Path of the game's real menu face (DINPro Medium = core.psarc fonts/seriffont-Medium.otf) for every preview: T2R_PREVIEW_FONT, else a
    cache in the temp dir (read out of the game's core.psarc once, read-only; never committed), else None (Bahnschrift stand-in)."""
    e = os.environ.get("T2R_PREVIEW_FONT")
    if e and os.path.exists(e):
        return e
    c = os.path.join(os.environ.get("TEMP") or os.environ.get("TMP") or ".", "t2r-preview-font", "seriffont-Medium.otf")
    if not os.path.exists(c):
        try:
            sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            import dsar_list
            game = os.environ.get("T2_GAME", "C:/Games/The Last of Us Part II Remastered")
            d, ent, bs, bsz = dsar_list.open_files(os.path.join(game, "build", "pc", "main", "core.psarc"))
            os.makedirs(os.path.dirname(c), exist_ok=True)
            open(c, "wb").write(dsar_list.extract(d, ent, bs, bsz, "fonts/seriffont-Medium.otf"))
        except Exception:
            return None
    return c if os.path.exists(c) else None


if real_font():
    FONT = real_font()
# The game's menu font draws ~1.33x wider than Bahnschrift at the same pointSize (measured on the
# CHOOSE YOUR SIDE page, lookclaude.png: a 48 pt line is ~1000 units wide / 82 tall in game), so
# text is previewed at pointSize * GAME_TEXT_SCALE to show the in-game wrapping.
GAME_TEXT_SCALE = 1.33
FONT_AXES = None          # e.g. [600, 100]: Bahnschrift weight / width (the game's menu face is a medium-heavy DIN, not the regular cut); None = font default
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
STREAMING = {"streaming/t2r/clan/": os.path.join(ROOT, "re", "figures"),
             "streaming/t2r/load/": os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")}   # mod images we can draw
# the map thumbnails (match flow): the mod's gtex1 staging copy, here or in the main checkout (a worktree has none)
for _d in (os.path.join(ROOT, "re", "modfs", "gtex1", "streaming", "menus", "to1"),
           os.path.join(ROOT, "..", "..", "..", "re", "modfs", "gtex1", "streaming", "menus", "to1")):
    if os.path.isdir(_d):
        STREAMING["streaming/menus/to1/"] = os.path.normpath(_d)
        break
MOD_ICONS = {"supply": "supply_icon", "gear": "gear_icon", "person": "person_icon",
             "hud-parts": lambda: __import__("make_icons").hud_counter_icon("parts"),
             "hud-supplies": lambda: __import__("make_icons").hud_counter_icon("supplies"),
             "fig-us": lambda: __import__("make_icons").fig_icon("us"), "fig-en": lambda: __import__("make_icons").fig_icon("en"),
             "fig-x-us": lambda: __import__("make_icons").fig_icon("us", True), "fig-x-en": lambda: __import__("make_icons").fig_icon("en", True),
             "fig-colon": lambda: __import__("make_icons").fig_colon(),
             "hud-counter-panel": lambda: __import__("make_icons").soft_panel(),
             "buy-hint-panel": lambda: __import__("make_icons").buy_hint_panel(),
             "radar-vignette": lambda: __import__("make_icons").radar_vignette(),
             "radar-glow": lambda: __import__("make_icons").radar_glow(),
             "team-grad": lambda: __import__("make_icons").team_grad()}   # tools/models/make_icons.py


def argb(v):
    if isinstance(v, str):
        v = PALETTE.get(v, 0xFFFFFFFF)
    return (v >> 16) & 255, (v >> 8) & 255, v & 255


def _runs(txt, rgba):
    """'a <font color="#rrggbb">b</font> c' (the markup t2r-ext sets) -> [(text, rgba), ...]."""
    out, pos = [], 0
    for m in re.finditer(r'<font color="#([0-9a-fA-F]{6})">(.*?)</font>', txt):
        if m.start() > pos:
            out.append((txt[pos:m.start()], rgba))
        v = int(m.group(1), 16)
        out.append((m.group(2), ((v >> 16) & 255, (v >> 8) & 255, v & 255, rgba[3])))
        pos = m.end()
    if pos < len(txt) or not out:
        out.append((txt[pos:], rgba))
    return out


def _real_icon(layer, path, x, y, w, h, col, a, item):
    """The REAL texture of an Image widget (stock game icon from the textures pak, or the mod's own streaming/t2r/icons file), tinted by the
    widget colour, fitted like StretchAspect (real_icons.py).  False = no such texture (then the caller draws the outline box)."""
    try:
        import real_icons
        if w < 1 or h < 1 or real_icons.get(path) is None:
            return False
        ts = item.get("tint.start")
        if isinstance(ts, int) and item.get("tint.end") == ts:           # an Image tint (e.g. the dark parts gear watermark)
            col = tuple(((ts >> sh) & 255) * c // 255 for sh, c in ((16, col[0]), (8, col[1]), (0, col[2])))
        stretch = item.get("scaleMode") not in (None, "StretchAspect") and item.get("scaleMode") == "Stretch"
        tmp = Image.new("RGBA", layer.size, (0, 0, 0, 0))
        if stretch:
            src = real_icons.get(path).resize((max(1, int(w)), max(1, int(h))), Image.LANCZOS)
            ch = [c.point(lambda v, t=t: v * t // 255) for c, t in zip(src.split()[:3], col)]
            ch.append(src.getchannel("A").point(lambda v: int(v * a)))
            tmp.alpha_composite(Image.merge("RGBA", ch), (int(x), int(y)))
        else:
            real_icons.paste(tmp, path, x, y, w, h, col, int(255 * a))
        layer.alpha_composite(tmp)
        return True
    except Exception:
        return False


def render(page, out, show=(), hide=(), scale=0.5, bg=None):
    w = page if isinstance(page, dict) else json.load(open(page, encoding="utf-8"))
    cw, ch = w.get("size", [3840.0, 2160.0])
    items = w["items"]
    kids = {}
    for i in items:
        kids.setdefault(i.get("parent"), []).append(i)
    guids = {i["guid"] for i in items}
    tops = [i for i in items if i.get("parent") not in guids]
    img = Image.new("RGBA", (int(cw * scale), int(ch * scale)), (24, 24, 26, 255))
    if bg:
        img = Image.open(bg).convert("RGBA").resize(img.size)
    fonts = {}

    def font(pt):
        k = max(6, int(pt * scale * GAME_TEXT_SCALE))
        if k not in fonts:
            fonts[k] = ImageFont.truetype(FONT, k)
            if FONT_AXES:
                try:
                    fonts[k].set_variation_by_axes(FONT_AXES)
                except Exception:
                    pass
        return fonts[k]

    def g(i, k, d=0.0):
        v = i.get(k, d)
        return d if v is None else v

    def draw(i, P, alpha):
        vis = g(i, "visible", 1) or i["name"] in show
        if not vis or i["name"] in hide:
            return
        px0, py0, pw, ph = P
        ax0, ax1 = px0 + g(i, "anchorMinN.x") * pw, px0 + g(i, "anchorMaxN.x") * pw
        ay0, ay1 = py0 + g(i, "anchorMinN.y") * ph, py0 + g(i, "anchorMaxN.y") * ph
        sw, sh = (ax1 - ax0) + g(i, "rectSizeDelta.width"), (ay1 - ay0) + g(i, "rectSizeDelta.height")
        pnx, pny = g(i, "pivotN.x", 0.5), g(i, "pivotN.y", 0.5)
        pvx = ax0 + (ax1 - ax0) * pnx + g(i, "pivotAs.x")
        pvy = ay0 + (ay1 - ay0) * pny + g(i, "pivotAs.y")
        x0, y0 = pvx - pnx * sw, pvy - pny * sh
        a = alpha * (g(i, "color.a", 255) / 255.0 if g(i, "inheritAlpha", 1) else 1.0)
        col = argb(i.get("tint.start", 0xFFFFFFFF))
        rot = math.radians(g(i, "rotation"))
        S = scale

        def pt(x, y):                                     # rotate about the pivot, to pixels
            dx, dy = x - pvx, y - pvy
            return ((pvx + dx * math.cos(rot) - dy * math.sin(rot)) * S, (pvy + dx * math.sin(rot) + dy * math.cos(rot)) * S)
        layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
        d = ImageDraw.Draw(layer)
        rgba = col + (int(255 * a),)
        cls = i.get("class")
        if cls == "Image":
            path = i.get("path", "")
            if "square" in path:
                d.polygon([pt(x0, y0), pt(x0 + sw, y0), pt(x0 + sw, y0 + sh), pt(x0, y0 + sh)], fill=rgba)
            elif "radial" in path:
                cx, cy = (x0 + sw / 2) * S, (y0 + sh / 2) * S
                for k in range(24, 0, -1):
                    f = k / 24.0
                    d.ellipse([cx - sw * S / 2 * f, cy - sh * S / 2 * f, cx + sw * S / 2 * f, cy + sh * S / 2 * f],
                              fill=col + (int(255 * a * (1 - f) * 0.25),))
            elif any(path.startswith(k) for k in STREAMING):
                k = next(k for k in STREAMING if path.startswith(k))
                src = os.path.join(STREAMING[k], path[len(k):])
                if os.path.exists(src) and sw * S >= 1 and sh * S >= 1:
                    im = Image.open(src).convert("RGBA").resize((int(sw * S), int(sh * S)), Image.LANCZOS)
                    ch = [c.point(lambda v, t=t: v * t // 255) for c, t in zip(im.split()[:3], col)]
                    ch.append(im.split()[3].point(lambda v: int(v * a)))
                    sub, ox, oy = Image.merge("RGBA", ch), int(x0 * S), int(y0 * S)
                    cx0, cy0 = max(0, -ox), max(0, -oy)           # (off-screen parts, e.g. the menu shade, are clipped)
                    sub = sub.crop((cx0, cy0, min(sub.width, layer.width - ox), min(sub.height, layer.height - oy)))
                    if sub.width > 0 and sub.height > 0:
                        layer.alpha_composite(sub, (ox + cx0, oy + cy0))
            elif path.startswith("menu:"):
                d.ellipse([x0 * S, y0 * S, (x0 + sw) * S, (y0 + sh) * S], outline=rgba, width=2)
                glyph = {"menu:select": "A", "menu:back": "B", "menu:prev": "Q", "menu:next": "E"}.get(path, "")     # the real prompt is the engine's WHITE input glyph (A / B on a pad, the key on a keyboard)
                if glyph:
                    d.text(((x0 + sw / 2) * S, (y0 + sh / 2) * S), glyph, font=font(30), fill=rgba, anchor="mm")
                else:
                    d.line([(x0 + sw * .3) * S, (y0 + sh * .3) * S, (x0 + sw * .7) * S, (y0 + sh * .7) * S], fill=rgba, width=2)
                    d.line([(x0 + sw * .7) * S, (y0 + sh * .3) * S, (x0 + sw * .3) * S, (y0 + sh * .7) * S], fill=rgba, width=2)
            elif path.startswith("streaming/t2r/icons/") and (path[20:-4] in MOD_ICONS or path[20:].startswith("booster-") or path[20:].startswith("hud-panel-")):
                sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "models"))
                if path[20:].startswith("booster-"):        # the real 2013 one-use booster icons (booster_icons.py)
                    src = Image.open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "models",
                                                  "booster_icons_2013", path[28:-4] + ".png")).convert("RGBA")
                elif path[20:].startswith("hud-panel-"):    # per-element soft panel (make_icons.main sizes: content + 18 % padding)
                    import clan_widgets as _cw, matchflow_widgets as _mf, make_icons
                    nm = path[30:-4]
                    _r = {r[0]: r for r in _cw.hud_panel_rects() + _mf.banner_panel_rects()}[nm]
                    _pw, _ph, _fx, _fy = _cw.hud_panel_geom(nm, _r[3], _r[4])
                    src = make_icons.soft_panel(max(8, round(_pw)), max(8, round(_ph)), _fx, _fy)
                else:                                       # drawn like the build does
                    import make_icons
                    m_ = MOD_ICONS[path[20:-4]]
                    src = m_() if callable(m_) else getattr(make_icons, m_)()
                f = min(sw / src.width, sh / src.height)            # StretchAspect-like fit, centred
                if path.endswith("team-grad.png"):                  # the team band is Stretch: fills its rect
                    iw, ih = max(1, int(sw * S)), max(1, int(sh * S))
                    ic = src.resize((iw, ih), Image.BILINEAR)
                    ch = [c.point(lambda v, t=t: v * t // 255) for c, t in zip(ic.split()[:3], col)]
                    ch.append(ic.getchannel("A").point(lambda v: int(v * a)))
                    layer.alpha_composite(Image.merge("RGBA", ch), (int(x0 * S), int(y0 * S)))
                    img.alpha_composite(layer)
                    for c in sorted(kids.get(i["guid"], []), key=lambda c: g(c, "depth")):
                        draw(c, (x0, y0, sw, sh), a)
                    return
                iw, ih = max(1, int(src.width * f * S)), max(1, int(src.height * f * S))
                ic = src.resize((iw, ih), Image.LANCZOS)
                ch = [c.point(lambda v, t=t: v * t // 255) for c, t in zip(ic.split()[:3], col)]
                ch.append(ic.getchannel("A").point(lambda v: int(v * a)))
                layer.alpha_composite(Image.merge("RGBA", ch), (int((x0 + sw / 2) * S - iw / 2), int((y0 + sh / 2) * S - ih / 2)))
            elif "blur" not in path and _real_icon(layer, path, x0 * S, y0 * S, sw * S, sh * S, col, a, i):
                pass
            elif "blur" not in path:
                d.rectangle([x0 * S, y0 * S, (x0 + sw) * S, (y0 + sh) * S], outline=rgba, width=1)
        elif cls == "Ellipse":
            box = [x0 * S, y0 * S, (x0 + sw) * S, (y0 + sh) * S]
            if g(i, "filled", 1):
                d.ellipse(box, fill=rgba)
            else:
                b0, b1 = g(i, "beginDegrees", 0), g(i, "endDegrees", 360)
                d.arc(box, b0, b1, fill=rgba, width=max(1, int(g(i, "lineWidth", 2) * S)))
        elif cls == "Polyline":
            uv = i.get("pointsUv", [])
            pts = [pt(x0 + uv[k] * sw, y0 + uv[k + 1] * sh) for k in range(0, len(uv) - 1, 2)]
            if g(i, "closed", 0) and pts:
                pts.append(pts[0])
            if len(pts) > 1:
                d.line(pts, fill=rgba, width=max(1, int(g(i, "lineWidth", 2) * S)))
        elif cls == "Text":
            txt = i.get("text", "")
            f = font(g(i, "pointSize", 40))
            runs = _runs(txt, rgba)
            txt = "".join(t for t, _ in runs)
            lines = [txt]
            if g(i, "multiline", 0) and sw > 0:
                lines = []
                for para in txt.split(chr(10)):                       # an explicit line break stays one (clan13 journal: the ext wraps the text itself)
                    cur = ""
                    for word in para.split():
                        t2 = (cur + " " + word).strip()
                        if f.getlength(t2) > sw * S and cur:
                            lines.append(cur); cur = word
                        else:
                            cur = t2
                    lines.append(cur)
            lh = f.size * 1.3
            total = lh * len(lines)
            ty = y0 * S if g(i, "alignV", 1) == 0 else (y0 + sh) * S - total if g(i, "alignV", 1) == 2 else (y0 + sh / 2) * S - total / 2
            trk = g(i, "tracking.x", 0.0) * S * 0.5           # (approximate: the engine's unit is not measured)

            def tlen(t):
                return f.getlength(t) + trk * len(t)

            def tdraw(x, y, t, c):
                if not trk:
                    d.text((x, y), t, font=f, fill=c)
                    return
                for ch in t:
                    d.text((x, y), ch, font=f, fill=c)
                    x += f.getlength(ch) + trk
            for ln in lines:
                lw = tlen(ln)
                al = g(i, "alignH", 0)
                tx = x0 * S if al == 0 else ((x0 + sw / 2) * S - lw / 2 if al == 1 else (x0 + sw) * S - lw)
                if (len(runs) > 1 or runs[0][1] != rgba) and len(lines) == 1:              # <font color> runs (single line; a text that is ONE coloured run too)
                    for t, c in runs:
                        tdraw(tx, ty, t, c)
                        tx += tlen(t)
                else:
                    tdraw(tx, ty, ln, rgba)
                ty += lh
        img.alpha_composite(layer)
        for c in sorted(kids.get(i["guid"], []), key=lambda c: g(c, "depth")):
            draw(c, (x0, y0, sw, sh), a)

    for t in tops:
        draw(t, (0.0, 0.0, cw, ch), 1.0)
    img.convert("RGB").save(out)
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("page"); ap.add_argument("out")
    ap.add_argument("--show", default=""); ap.add_argument("--hide", default="")
    ap.add_argument("--scale", type=float, default=0.5); ap.add_argument("--bg")
    a = ap.parse_args()
    print(render(a.page, a.out, [s for s in a.show.split(",") if s], [s for s in a.hide.split(",") if s], a.scale, a.bg))
