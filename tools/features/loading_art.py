"""Art of the TWELVE WEEKS entry screen (connecting_widgets variant L): the title as an alpha-mask texture drawn with "The Last Of Us Rough.ttf"
(project root; the file itself is copied to features/data/ so a clean worktree builds) and the progress bar fill with a torn right edge.

  python loading_art.py   # writes data/tw-title.png (3000 x 760, white + alpha) and data/tw-bar.png (3840 x 2*BAR_PX)
The widgets are 3840 x 2160 units; the previews (loading_seq_preview.py) show these very images."""
import os
import numpy as np
from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data")
FONT = os.path.join(DATA, "TheLastOfUs-Rough.ttf")
TITLE_PNG = os.path.join(DATA, "tw-title.png")
BAR_PNG = os.path.join(DATA, "tw-bar.png")
TITLE_TEX = "streaming/t2r/load/tw-title.png"
BAR_TEX = "streaming/t2r/load/tw-bar.png"
TITLE_W, TITLE_H = 3000, 760        # texture size = widget size in 3840 x 2160 units
INK_W = 2700                        # ink width of the title in the texture / on screen (units)
FEATHER = 100                       # soft fill edge, units (50 px at 1080p)
DIM_A = 51                          # the empty title: 20 % white (alpha 51 / 255); the feather darkens white to exactly this
FEATHER_PNG = os.path.join(DATA, "tw-feather.png")
FEATHER_TEX = "streaming/t2r/load/tw-feather.png"
BAR_PX = 12                         # bar thickness at 1080p (thin; 8 / 12 / 16 compared in re/loading-1105/bar_thickness.png, 12 chosen)
BAR_W, BAR_H = 3840, BAR_PX * 2


def make_title(text="TWELVE WEEKS"):
    f = ImageFont.truetype(FONT, 1000)
    l, t, r, b = f.getbbox(text)
    k = 2700.0 / (r - l)            # ink width 2700 units (70 % of 3840), no tracking
    f = ImageFont.truetype(FONT, int(1000 * k))
    l, t, r, b = f.getbbox(text)
    im = Image.new("L", (TITLE_W, TITLE_H), 0)
    d = ImageDraw.Draw(im)
    d.text(((TITLE_W - (r - l)) / 2 - l, (TITLE_H - (b - t)) / 2 - t), text, font=f, fill=255)
    out = Image.new("RGBA", im.size, (255, 255, 255, 0))
    out.putalpha(im)
    return out, (b - t)


def make_bar(px=BAR_PX):
    BAR_H = px * 2          # units (3840 x 2160 space)
    k = px / 28.0           # the torn end scales with the bar
    rng = np.random.default_rng(12)
    a = np.zeros((BAR_H, BAR_W), np.float32)
    # torn right edge: the solid body ends at x = BAR_W - 70 + a ragged profile (sum of octaves per row, plus bites and flecks)
    edge = np.zeros(BAR_H)
    for oct_, amp in ((7, 26), (3, 14), (1, 6)):
        oct_ = max(1, oct_ * k)
        p = rng.standard_normal(int(BAR_H / oct_) + 3)
        edge += np.interp(np.arange(BAR_H) / oct_, np.arange(len(p)), p) * amp * k
    xs = np.arange(BAR_W)[None, :]
    a[:] = (xs < (BAR_W - 60 * k + edge)[:, None]).astype(np.float32)
    for _ in range(60):          # flecks of torn paper just beyond the edge, and bites inside it
        y = rng.integers(0, BAR_H); x = int(BAR_W - 60 * k + edge[y] + rng.integers(-40, 50)); w = rng.integers(3, 14); h = rng.integers(2, 7)
        a[y:y + h, max(0, x):x + w] = float(rng.random() < 0.5)
    a[:, :6] = 1.0
    out = np.zeros((BAR_H, BAR_W, 4), np.uint8)
    out[..., :3] = 255
    out[..., 3] = (a * 255).astype(np.uint8)
    return Image.fromarray(out, "RGBA")


def make_feather():
    """black, alpha ramps 0 -> 1 - DIM_A/255 left to right (smoothstep): laid over the bright title at the fill's right edge it darkens white to the empty-title level"""
    n = 256
    u = np.linspace(0, 1, n)
    a = (u * u * (3 - 2 * u)) * (1 - DIM_A / 255.0)
    out = np.zeros((8, n, 4), np.uint8)
    out[..., 3] = (a * 255 + 0.5).astype(np.uint8)[None, :]
    return Image.fromarray(out, "RGBA")


if __name__ == "__main__":
    make_feather().save(FEATHER_PNG, optimize=True)
    t, cap = make_title()
    t.save(TITLE_PNG, optimize=True)
    make_bar().save(BAR_PNG, optimize=True)
    print("title cap-ish height (units)", cap, "->", cap / 2, "px at 1080p")
