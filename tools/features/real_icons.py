"""The REAL icon images for the offline UI previews (no silhouettes / placeholders): the stock game textures the widget paks reference
(read-only from re/models/gui2-textures-common.pak: RGBA8 icons, and the white R8 weapon icons = alpha only, rows padded to 64 px) and the
mod's own icons (streaming/t2r/icons/<name>.png as the build stages them; found in icons-for-manual/ours or re/icons/out of this or the main checkout).

  get("hud/weapons/guns/rifle-vepr/vepr.png")            -> RGBA PIL image or None
  get("streaming/t2r/icons/remington-bolt-supp.png")      -> the mod icon
Nothing is written anywhere; the pak is indexed once per process."""
import os
import re
import sys

import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "models"))
MAIN = os.environ.get("T2R_ROOT", ".")
ROOT = os.path.dirname(os.path.dirname(HERE))
PAK_CANDS = [os.path.join(r, "re", "models", "gui2-textures-common.pak") for r in (ROOT, MAIN)]
MOD_DIRS = [os.path.join(r, *p) for r in (ROOT, MAIN) for p in (("icons-for-manual", "ours"), ("re", "icons", "out"))]
_idx = None
_cache = {}


def _index():
    global _idx
    if _idx is None:
        _idx = {}
        import ndpak
        pak = next((c for c in PAK_CANDS if os.path.exists(c)), None)
        if pak:
            p = ndpak.Pak(pak)
            for t in ndpak.textures(p):
                m = re.search(r"textures/(.*)/[0-9A-F]+\.ndb", t["path"])
                n = m.group(1) if m else t["path"]
                if t["fmt"] in (28, 65) and n not in _idx:
                    _idx[n] = (p, t)
    return _idx


def stock(name):
    ent = _index().get(name)
    if not ent:
        return None
    p, t = ent
    w, h = t["w"], t["h"]
    pw = (w + 63) // 64 * 64
    if t["fmt"] == 28:
        a = np.frombuffer(p.d[t["data"]:t["data"] + pw * h * 4], np.uint8).reshape(h, pw, 4)[:, :w].copy()
        return Image.fromarray(a, "RGBA")
    a = np.frombuffer(p.d[t["data"]:t["data"] + pw * h], np.uint8).reshape(h, pw)[:, :w].copy()   # R8 = the alpha of a white icon
    rgba = np.empty((h, w, 4), np.uint8)
    rgba[..., :3] = 255
    rgba[..., 3] = a
    return Image.fromarray(rgba, "RGBA")


def mod(name):
    for d in MOD_DIRS:
        f = os.path.join(d, name)
        if os.path.exists(f):
            return Image.open(f).convert("RGBA")
    return None


def get(path):
    if path not in _cache:
        if path.startswith("streaming/t2r/icons/"):
            im = mod(path[len("streaming/t2r/icons/"):])
        else:
            im = stock(path)
        _cache[path] = im
    return _cache[path]


def paste(im, path, x, y, w, h, col=(216, 211, 198), a=255, fit=True):
    """Draw the icon fitted + centred into the box (x, y, w, h), tinted `col` (white icons take the tint, the mod's own coloured ones too, like
    the widget's colour multiply).  Returns False when the icon is missing."""
    src = get(path)
    if src is None:
        return False
    k = min(w / src.width, h / src.height) if fit else 1.0
    ic = src.resize((max(1, int(src.width * k)), max(1, int(src.height * k))), Image.LANCZOS)
    ch = [c.point(lambda v, t=t: v * t // 255) for c, t in zip(ic.split()[:3], col)]
    ch.append(ic.getchannel("A").point(lambda v: int(v * a / 255)))
    im.alpha_composite(Image.merge("RGBA", ch), (int(x + (w - ic.width) / 2), int(y + (h - ic.height) / 2)))
    return True
