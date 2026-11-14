"""Builds the Steam library art of the ADD TO STEAM button into assets/steam/ (run from release/launcher).
Source: logos/backgroundnotext.png (scene, no text) and logos/text.png (white TWELVE WEEKS on transparent).
cover.jpg 1200x1800 (portrait, house kept in frame), wide.jpg 1840x860, hero.jpg 3840x1240, logo.png = text trimmed to its alpha box."""
import os, sys
from PIL import Image
SRC = sys.argv[1] if len(sys.argv) > 1 else "./logos"
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "assets", "steam")
os.makedirs(OUT, exist_ok=True)
bg = Image.open(os.path.join(SRC, "backgroundnotext.png")).convert("RGB")
W, H = bg.size
def crop(w, h, cx=0.5, cy=0.5):
    """largest w:h box of the scene centred on (cx, cy) (fractions), resized to w x h"""
    r = w / h
    cw, ch = (W, int(W / r)) if W / H < r else (int(H * r), H)
    x = min(max(int(cx * W - cw / 2), 0), W - cw)
    y = min(max(int(cy * H - ch / 2), 0), H - ch)
    return bg.crop((x, y, x + cw, y + ch)).resize((w, h), Image.LANCZOS)
def save(im, name):
    im.save(os.path.join(OUT, name), optimize=True)
CX = float(os.environ.get("CX", 0.5))
for n, (w, h) in {"cover": (1200, 1800), "wide": (1840, 860), "hero": (3840, 1240)}.items():
    crop(w, h, 0.64 if n == "cover" else CX).save(os.path.join(OUT, n + ".jpg"), quality=88, optimize=True, progressive=True)
t = Image.open(os.path.join(SRC, "text.png")).convert("RGBA")
t = t.crop(t.getchannel("A").getbbox())
save(t, "logo.png")
for f in sorted(os.listdir(OUT)):
    print(f, Image.open(os.path.join(OUT, f)).size, os.path.getsize(os.path.join(OUT, f)) // 1024, "KB")
