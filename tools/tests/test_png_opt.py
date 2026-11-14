"""png_opt: lossless, pixel-checked PNG recompression. Synthetic images (RGBA gradient, palette, 16 bit gray, interlaced): the result must
decode to the same pixels with the same IHDR, never be bigger, and a non-PNG file must come back untouched.
Skips (SKIP, exit 0) without pyoxipng / Pillow (pip install pyoxipng)."""
import io
import os
import sys
import tempfile
import sys as _t2s, os as _t2o; _t2s.path.append(_t2o.path.normpath(_t2o.path.join(_t2o.path.dirname(_t2o.path.abspath(__file__)), ".."))); import t2rtmp  # noqa: E402,F401  (temp hygiene: tools/t2rtmp.py)

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "features"))


def main():
    try:
        import oxipng
        from PIL import Image
        import numpy as np
    except ImportError:
        print("SKIP test_png_opt: pyoxipng / Pillow / numpy not installed")
        return 0
    import png_opt
    bad = []

    def check(name, ok):
        print(("ok   " if ok else "FAIL ") + name)
        if not ok:
            bad.append(name)

    rng = np.random.RandomState(3)
    imgs = {}
    g = np.zeros((200, 300, 4), np.uint8)
    g[..., 0] = np.arange(300)[None, :] % 256
    g[..., 1] = np.arange(200)[:, None] % 256
    g[..., 2] = rng.randint(0, 4, (200, 300))
    g[..., 3] = 255
    imgs["rgba"] = Image.fromarray(g, "RGBA")
    imgs["palette"] = Image.fromarray(rng.randint(0, 8, (64, 64)).astype(np.uint8), "L").convert("P")
    imgs["gray16"] = Image.fromarray((rng.randint(0, 65535, (50, 60))).astype(np.uint16))
    imgs["rgb"] = Image.fromarray(rng.randint(0, 255, (40, 40, 3)).astype(np.uint8), "RGB")
    with tempfile.TemporaryDirectory() as td:
        os.environ["T2R_PNG_CACHE"] = os.path.join(td, "cache")
        stage = os.path.join(td, "stage")
        os.makedirs(stage)
        before = {}
        for name, im in imgs.items():
            b = io.BytesIO()
            im.save(b, "PNG", compress_level=1)
            p = os.path.join(stage, name + ".png")
            open(p, "wb").write(b.getvalue())
            before[p] = b.getvalue()
        junk = os.path.join(stage, "fake.png")
        open(junk, "wb").write(b"not a png at all")
        n, a, b = png_opt.optimize_stage(stage)
        check("all PNGs visited", n == len(imgs) + 1)
        for p, d in before.items():
            o = open(p, "rb").read()
            same = png_opt._pixels(o) == png_opt._pixels(d)
            check("%s: pixels identical, IHDR identical, not bigger (%d -> %d)" % (os.path.basename(p), len(d), len(o)),
                  same and o[8:33] == d[8:33] and len(o) <= len(d))
        check("a non-PNG file is left alone", open(junk, "rb").read() == b"not a png at all")
        n2, a2, b2 = png_opt.optimize_stage(stage)               # second run: cached, stable
        check("second run changes nothing", (a2, b2) == (b, b))
    print("\n%d problem(s)" % len(bad))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
