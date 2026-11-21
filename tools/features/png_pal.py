"""8-bit palette PNGs for the mod's gui2 art (every PNG under the stage's gtex1): about half the RGBA bytes over the whole set
(a third for rendered pictures). int-1117a's winmm went over the loadable image size; this keeps the UI art in budget.

The game decodes gui2 PNGs with stb_image, which expands a palette PNG with a tRNS chunk to 4 channels, the same as an RGBA PNG.
Every file written here carries a tRNS chunk (index 0 = fully transparent), so it decodes to RGBA even when the picture is opaque.

Quantizer: k-means on premultiplied RGBA (so soft alpha edges keep their own entries), a lossless palette when the picture has 255
colours or fewer, and an 8x8 ordered dither sized to the palette spacing (no banding on skin and gradients). Fully transparent
pixels all map to index 0.

  python png_pal.py <in.png> <out.png>            one file
  python png_pal.py --stage <stage dir>           every PNG under <stage>/gtex1, in place (cached by content hash)
"""
import hashlib
import io
import os
import shutil
import sys
from concurrent.futures import ProcessPoolExecutor

import numpy as np
from PIL import Image

STAGE_ROOT = "gtex1"          # every .png under it, recursively (the stage holds only the mod's own gui2 art there)
VERSION = b"pngpal-2"
CACHE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "local", "build-cache", "pngpal")
SAMPLE = 40000
DITHER = float(os.environ.get("T2R_PNGPAL_DITHER", "1.0"))     # ordered-dither amplitude, x the palette spacing
GREY_TOL = 6                                                   # max channel spread of a "grey" picture (no dither)
# Full-screen key art with soft glow / mist layers: 255 entries dim the glows and the dither shows on the smooth areas at screen size
# (the clan event art, re/clan-events-1117.md "Size": the lamp's halo of the sick bay picture). Files under these stage paths are
# converted only when that is lossless (255 colours or fewer); their own ship step already made them small (clanev_ship.py, 6 bits of
# colour). T2R_PNGPAL_ALL=1 converts them like every other picture (the event art in a finished build: 11.2 MB -> 8.7 MB).
KEEP = ("streaming/t2r/clanev/",)
_BAYER8 = np.array([[0, 32, 8, 40, 2, 34, 10, 42], [48, 16, 56, 24, 50, 18, 58, 26], [12, 44, 4, 36, 14, 46, 6, 38],
                    [60, 28, 52, 20, 62, 30, 54, 22], [3, 35, 11, 43, 1, 33, 9, 41], [51, 19, 59, 27, 49, 17, 57, 25],
                    [15, 47, 7, 39, 13, 45, 5, 37], [63, 31, 55, 23, 61, 29, 53, 21]], np.float32) / 64.0 - 0.5


def _kmeans(x, k, iters=12, seed=1):
    """Plain k-means (k-means++ start) on the rows of x; returns the centres."""
    from scipy.spatial import cKDTree
    rng = np.random.default_rng(seed)
    c = [x[rng.integers(len(x))]]
    d2 = ((x - c[0]) ** 2).sum(1)
    for _ in range(1, k):
        p = d2 / d2.sum() if d2.sum() > 0 else None
        c.append(x[rng.choice(len(x), p=p)])
        d2 = np.minimum(d2, ((x - c[-1]) ** 2).sum(1))
    c = np.array(c, np.float32)
    for _ in range(iters):
        lab = cKDTree(c).query(x)[1]
        s = np.zeros_like(c)
        np.add.at(s, lab, x)
        n = np.bincount(lab, minlength=k).astype(np.float32)
        live = n > 0
        c[live] = s[live] / n[live, None]
    return c


def quantize(im):
    """RGBA image -> P image (256 entries max, index 0 transparent) + the transparency bytes for PIL's save."""
    from scipy.spatial import cKDTree
    a = np.asarray(im.convert("RGBA"))
    h, w = a.shape[:2]
    flat = a.reshape(-1, 4)
    vis = flat[:, 3] > 0
    idx = np.zeros(h * w, np.uint8)
    pal = np.zeros((256, 4), np.uint8)          # entry 0: transparent black
    if vis.any():
        u, inv = np.unique(flat[vis], axis=0, return_inverse=True)
        if len(u) <= 255:                        # lossless
            pal[1:1 + len(u)] = u
            idx[vis] = (inv.reshape(-1) + 1).astype(np.uint8)
        else:
            f = flat[vis].astype(np.float32)
            pm = np.concatenate([f[:, :3] * (f[:, 3:4] / 255.0), f[:, 3:4]], 1)     # premultiplied RGBA
            rng = np.random.default_rng(7)
            smp = pm[rng.choice(len(pm), min(SAMPLE, len(pm)), replace=False)]
            c = _kmeans(smp, 255)
            # dither amplitude: the median distance from a palette entry to its nearest neighbour
            dd = cKDTree(c).query(c, k=2)[0][:, 1]
            amp = float(np.median(dd)) * DITHER
            if np.abs(f[:, 0] - f[:, 1]).max() <= GREY_TOL and np.abs(f[:, 1] - f[:, 2]).max() <= GREY_TOL:
                amp = 0.0                        # grey art: 255 greys are ~all the levels it has; dither noise only costs bytes
            yy, xx = np.nonzero(vis.reshape(h, w))
            noise = _BAYER8[yy % 8, xx % 8][:, None] * amp
            q = pm.copy()
            q[:, :3] += noise                    # colour only: alpha stays undithered (clean edges)
            lab = cKDTree(c).query(q)[1]
            # un-premultiply the centres
            ca = np.clip(c[:, 3:4], 1e-3, 255)
            rgb = np.clip(c[:, :3] * 255.0 / ca, 0, 255)
            pal[1:256, :3] = np.round(rgb).astype(np.uint8)
            pal[1:256, 3] = np.round(np.clip(c[:, 3], 1, 255)).astype(np.uint8)
            idx[vis] = (lab + 1).astype(np.uint8)
    out = Image.frombytes("P", (w, h), idx.tobytes())
    out.putpalette(pal[:, :3].reshape(-1).tolist())
    return out, bytes(pal[:, 3].tolist())


def encode(data):
    """PNG bytes in -> palette PNG bytes out."""
    p, trns = quantize(Image.open(io.BytesIO(data)))
    buf = io.BytesIO()
    p.save(buf, "PNG", optimize=True, transparency=trns)
    return buf.getvalue()


def _kept(path, data):
    """1 = a KEEP picture with more than 255 colours: left as it is."""
    if os.environ.get("T2R_PNGPAL_ALL") == "1" or not any(k in path.replace("\\", "/") for k in KEEP):
        return False
    im = Image.open(io.BytesIO(data))
    if im.mode == "P":
        return True
    a = np.asarray(im.convert("RGBA")).reshape(-1, 4)
    a = a[a[:, 3] > 0]
    return len(np.unique(a.view(np.uint32))) > 255


def _one(path):
    data = open(path, "rb").read()
    if _kept(path, data):
        return len(data), len(data)
    key = hashlib.sha1(VERSION + str(DITHER).encode() + data).hexdigest()
    cp = os.path.join(CACHE, key[:2], key + ".png")
    if os.path.exists(cp):
        out = open(cp, "rb").read()
    else:
        if Image.open(io.BytesIO(data)).mode == "P":
            return len(data), len(data)
        out = encode(data)
        os.makedirs(os.path.dirname(cp), exist_ok=True)
        open(cp + ".tmp", "wb").write(out)
        os.replace(cp + ".tmp", cp)
    if len(out) < len(data):
        open(path, "wb").write(out)
        return len(data), len(out)
    return len(data), len(data)


def stage_files(stage):
    for dp, dn, fn in os.walk(os.path.join(stage, STAGE_ROOT)):
        dn.sort()
        for f in sorted(fn):
            if f.endswith(".png"):
                yield os.path.join(dp, f)


def optimize_stage(stage):
    files = list(stage_files(stage))
    with ProcessPoolExecutor(max(1, min(8, (os.cpu_count() or 2) - 2))) as ex:
        res = list(ex.map(_one, files, chunksize=8))
    before, after = sum(r[0] for r in res), sum(r[1] for r in res)
    print("png_pal: %d gui2 PNGs -> 8-bit palette, %.1f MB -> %.1f MB" % (len(files), before / 1e6, after / 1e6))
    return before, after


if __name__ == "__main__":
    if sys.argv[1] == "--stage":
        optimize_stage(sys.argv[2])
    else:
        shutil.copyfile(sys.argv[1], sys.argv[2]) if sys.argv[1] != sys.argv[2] else None
        open(sys.argv[2], "wb").write(encode(open(sys.argv[1], "rb").read()))
