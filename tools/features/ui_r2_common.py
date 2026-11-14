"""UI redesign round 2: shared look for the loadout picker + pause menu previews/widgets.

Feedback on round 1: too modern, fonts too thin; keep the 2013 UI style as inspiration, cleaner but still stylized.
So round 2 drops the wide-tracked thin small caps of the entry-loading look and goes back to what 2013 Factions did (2013factionsloadout1-4,
2013factionsclanfirstlaunch1-3):
  * heavy, condensed, upper-case type, tight tracking (0-2 px), real size steps (title 72 / row 34 / label 22 px at 1080p), never a light weight
  * near-black charcoal ground with worn "peeling paint" grit (GRIT_PNG below, generated, tiled/stretched under every page)
  * one cream-grey text colour (#D8D3C6) + dim (#8E8B82) + the Factions blue (#8EC3EA cost/FREE words, #3E92C4 team / accents), muted red #C24A4A
  * full-width hairline rules under titles, a vertical divider between list and details, a bright framed selection tile (hairline frame + grey fill)
  * stat bars = 10 chunky cream segments over dark empty segments, label directly above the bar (2013 DETAILS panel)
Widget space is 3840 x 2160; the PIL previews draw at 1920 x 1080 (multiply by 2).  Font: the game's own faces (Default = the DIN-like menu
face, Design = the heavy title face, see faceId in hud_overlay_widgets.py); PIL stand-in = Bahnschrift (wght 600 body / 700 + width 85 heavy)."""
import os
import random

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

# palette (RGB) -------------------------------------------------------------------------------------------------------------------------
CREAM = (0xD8, 0xD3, 0xC6)       # text / selected
DIM = (0x8E, 0x8B, 0x82)          # secondary text
FAINT = (0x5C, 0x5A, 0x54)        # disabled / empty
BLUE = (0x8E, 0xC3, 0xEA)         # cost words, FREE, 2013 "Loadout Points" blue
TEAM_BLUE = (0x3E, 0x92, 0xC4)
TEAM_RED = (0xC2, 0x4A, 0x4A)
GROUND = (0x10, 0x11, 0x12)
FONT_FILE = os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts", "bahnschrift.ttf")
_fc = {}


def font(px, heavy=False):
    """Bahnschrift stand-in for the game's menu face. heavy = title / header weight (condensed bold)."""
    k = (int(px), heavy)
    if k not in _fc:
        import widget_preview
        real = widget_preview.real_font()          # the game's DINPro Medium (one shared preview font path); Bahnschrift only if it cannot be read
        f = ImageFont.truetype(real or FONT_FILE, int(px))
        if not real:
            try:
                f.set_variation_by_axes([700, 86] if heavy else [600, 100])
            except Exception:
                pass
        _fc[k] = f
    return _fc[k]


# worn ground ---------------------------------------------------------------------------------------------------------------------------
def grit(w=1920, h=1080, seed=7, strength=1.0):
    """Peeling-paint grit like the 2013 menu ground: blotchy value noise, flake patches with a lit edge, a few scratches. RGB image."""
    rnd = np.random.default_rng(seed)

    def noise(scale, amp):
        small = rnd.random((h // scale + 2, w // scale + 2)).astype(np.float32)
        im = Image.fromarray((small * 255).astype(np.uint8)).resize((w, h), Image.BICUBIC)
        return (np.asarray(im, dtype=np.float32) / 255.0 - 0.5) * amp
    base = np.full((h, w), 18.0, np.float32) + noise(220, 11) + noise(70, 7) + noise(18, 4) + noise(4, 3)
    img = Image.fromarray(np.clip(base * strength + 18 * (1 - strength), 0, 255).astype(np.uint8)).convert("RGBA")
    ov = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(ov)
    r = random.Random(seed)
    for _ in range(int(70 * strength)):                       # paint flakes: lighter chip + dark crack edge
        cx, cy, rad = r.randrange(w), r.randrange(h), r.randrange(14, 70)
        pts = []
        nv = r.randrange(12, 18)
        for k in range(nv):
            a = k / nv * 6.2832
            rr = rad * r.uniform(0.7, 1.0)
            pts.append((cx + rr * np.cos(a) * 1.7, cy + rr * np.sin(a) * 0.8))
        d.polygon(pts, fill=(255, 250, 240, r.randrange(3, 8)), outline=(0, 0, 0, 55))
    for _ in range(int(26 * strength)):                       # scratches
        x, y = r.randrange(w), r.randrange(h)
        dx, dy = r.uniform(-1, 1) * 120, r.uniform(-1, 1) * 30
        d.line((x, y, x + dx, y + dy), fill=(255, 250, 240, r.randrange(8, 20)), width=1)
    img = Image.alpha_composite(img, ov.filter(ImageFilter.GaussianBlur(1.4)))
    # vignette
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    v = 1.0 - 0.55 * (((xx - w / 2) / (w * 0.75)) ** 2 + ((yy - h / 2) / (h * 0.75)) ** 2)
    arr = np.asarray(img.convert("RGB"), dtype=np.float32) * np.clip(v, 0.25, 1)[..., None]
    return Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8))


def grain(w=1920, h=1080, seed=11, alpha=11):
    """Film grain over the blurred menu (blurred out / noisy, no blobs): per-pixel luminance noise, a touch of
    1 px blur so it is grain and not sparkle, no large-scale shapes. RGBA: grey value = noise, alpha = its strength (the page puts it over
    blur-background + a near-black scrim, so the menu world shows through as a soft blur)."""
    rnd = np.random.default_rng(seed)
    n = rnd.normal(0.0, 1.0, (h, w)).astype(np.float32)
    im = Image.fromarray(np.clip(n * 40 + 128, 0, 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(0.6))
    v = np.asarray(im, dtype=np.float32)
    a = np.clip(np.abs(v - 128.0) / 64.0, 0, 1) * alpha
    rgb = np.where(v >= 128, 235, 0).astype(np.uint8)
    out = np.dstack([rgb, rgb, rgb, a.astype(np.uint8)])
    return Image.fromarray(out, "RGBA")


# drawing canvas ------------------------------------------------------------------------------------------------------------------------
class Cv:
    """1920x1080 RGBA canvas over the grit ground. y of text = vertical middle of the line."""

    def __init__(self, W=1920, H=1080, seed=7, tint=None, dark=1.0):
        self.W, self.H = W, H
        g = grit(W, H, seed)
        if dark != 1.0:
            g = g.point(lambda v: int(v * dark))
        if tint:
            ov = Image.new("RGB", (W, H), tint)
            g = Image.blend(g, ov, 0.07)
        self.im = g.convert("RGBA")
        self._ov()

    def _ov(self):
        self.ov = Image.new("RGBA", (self.W, self.H), (0, 0, 0, 0))
        self.d = ImageDraw.Draw(self.ov)

    def flush(self):
        self.im = Image.alpha_composite(self.im, self.ov)
        self._ov()

    def rect(self, x0, y0, x1, y1, col, a=255, outline=None, oa=255, w=1):
        self.d.rectangle((x0, y0, x1, y1), fill=(col + (a,)) if col is not None else None,
                         outline=(outline + (oa,)) if outline else None, width=w)

    def frame(self, x0, y0, x1, y1, col=CREAM, a=230, w=2):
        self.d.rectangle((x0, y0, x1, y1), outline=col + (a,), width=w)

    def line(self, x0, y0, x1, y1, col=CREAM, a=255, w=1):
        self.d.line((x0, y0, x1, y1), fill=col + (a,), width=w)

    def vgrad(self, x0, y0, x1, y1, col, a0, a1):
        n = int(y1 - y0)
        for i in range(n):
            self.d.line((x0, y0 + i, x1, y0 + i), fill=col + (int(a0 + (a1 - a0) * i / max(1, n - 1)),))

    def measure(self, s, px, track=0, heavy=False):
        f = font(px, heavy)
        return sum(f.getlength(c) + track for c in s) - track

    def text(self, x, y, s, px, col=CREAM, track=1, al="l", heavy=False, a=255, maxw=None):
        """Shrinks the tracking, then the size, to fit maxw (the game's fixed boxes cannot grow). Returns the drawn width."""
        tw = self.measure(s, px, track, heavy)
        if maxw and tw > maxw:
            track = 0
            tw = self.measure(s, px, track, heavy)
            while tw > maxw and px > 12:
                px -= 1
                tw = self.measure(s, px, track, heavy)
        f = font(px, heavy)
        x0 = x if al == "l" else (x - tw if al == "r" else x - tw / 2)
        for ch in s:
            self.d.text((x0, y), ch, font=f, fill=col + (a,), anchor="lm")
            x0 += f.getlength(ch) + track
        return tw

    def wrap(self, x, y, s, px, col, maxw, lh, track=0.3):
        words, line, ly = s.split(), "", y
        for w_ in words + [None]:
            t = (line + " " + w_).strip() if w_ else line
            if w_ is None or self.measure(t, px, track) > maxw:
                self.text(x, ly, line, px, col, track=track)
                ly += lh
                line = w_ or ""
            else:
                line = t
        return ly

    def save(self, p):
        self.flush()
        self.im.convert("RGB").save(p)


def bars(c, x, y, w, h, n, filled, col=CREAM, gap=4):
    """2013 stat bar: chunky segments, filled = cream, empty = dark with a hairline."""
    sw = (w - gap * (n - 1)) / n
    for i in range(n):
        xx = x + i * (sw + gap)
        if i < filled:
            c.rect(xx, y, xx + sw, y + h, col, 235)
        else:
            c.rect(xx, y, xx + sw, y + h, (0, 0, 0), 120, outline=FAINT, oa=90)


def glyph(c, x, y, g, r=15, col=DIM):
    """Controller prompt circle (the real build uses the input glyph textures)."""
    c.d.ellipse((x, y - r, x + 2 * r, y + r), outline=col + (220,), width=2)
    c.text(x + r, y, g, int(r * 1.15), col, al="m", heavy=True, track=0)


def icon(c, kind, x, y, w, h, col, a=255):
    """Silhouettes inside the box (x, y, w, h): stand-ins for the real weapon / skill icon textures."""
    d = c.d

    def S(px, py):
        return (x + px * w / 100.0, y + py * h / 40.0)
    fill = col + (a,)
    lw = max(2, int(h / 12))
    if kind == "rifle":
        for pts in ([(0, 16), (16, 12), (38, 12), (40, 18), (4, 24)], [(38, 13), (96, 13), (96, 17), (38, 17)],
                    [(30, 10), (62, 10), (62, 13), (30, 13)], [(40, 17), (44, 30), (50, 30), (48, 17)]):
            d.polygon([S(*p) for p in pts], fill=fill)
        d.rectangle((*S(60, 6), *S(76, 9)), fill=fill)
    elif kind == "pistol":
        d.polygon([S(*p) for p in [(10, 8), (88, 8), (88, 17), (36, 17), (30, 36), (16, 36), (22, 17), (10, 17)]], fill=fill)
    elif kind == "shotgun":
        for pts in ([(0, 18), (14, 14), (40, 14), (40, 19), (6, 26)], [(40, 14), (98, 14), (98, 19), (40, 19)],
                    [(48, 19), (82, 19), (82, 24), (48, 24)]):
            d.polygon([S(*p) for p in pts], fill=fill)
    elif kind == "bow":
        d.arc((*S(30, -6), *S(70, 46)), 270, 90, fill=fill, width=lw)
        d.line((*S(50, -4), *S(50, 44)), fill=fill, width=max(1, int(h / 28)))
        d.line((*S(10, 20), *S(80, 20)), fill=fill, width=max(1, int(h / 28)))
    elif kind == "xbow":
        d.rectangle((*S(10, 17), *S(90, 22)), fill=fill)
        d.arc((*S(46, -2), *S(96, 42)), 270, 90, fill=fill, width=lw)
    elif kind == "skill":
        cx, cy, r = x + w / 2, y + h / 2, min(w, h) * 0.42
        d.ellipse((cx - r, cy - r, cx + r, cy + r), outline=fill, width=lw)
        d.polygon([(cx - r * .3, cy - r * .5), (cx + r * .55, cy), (cx - r * .3, cy + r * .5)], fill=fill)
    else:                       # none = the 2013 "no" sign
        cx, cy, r = x + w / 2, y + h / 2, min(w, h) * 0.42
        d.ellipse((cx - r, cy - r, cx + r, cy + r), outline=fill, width=lw + 1)
        d.line((cx - r * .7, cy - r * .7, cx + r * .7, cy + r * .7), fill=fill, width=lw + 1)
