"""png_pal: gui2 art to 8-bit palette PNGs (tools/features/png_pal.py)."""
import io
import os
import sys
import unittest

import numpy as np
from PIL import Image

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "features"))
import png_pal  # noqa: E402


def png(im):
    b = io.BytesIO()
    im.save(b, "PNG")
    return b.getvalue()


def back(data):
    im = Image.open(io.BytesIO(data))
    return im, np.asarray(im.convert("RGBA")).astype(int)


class PngPal(unittest.TestCase):
    def test_few_colours_lossless(self):
        a = np.zeros((40, 50, 4), np.uint8)
        a[5:20, 5:30] = (200, 10, 10, 255)
        a[25:35, 10:45] = (10, 200, 90, 128)
        out, b = back(png_pal.encode(png(Image.fromarray(a, "RGBA"))))
        self.assertEqual(out.mode, "P")
        self.assertTrue((b == a).all())

    def test_opaque_picture_keeps_trns(self):
        # stb_image decodes a palette PNG to 4 channels only with a tRNS chunk: every output carries one
        rng = np.random.default_rng(3)
        a = np.concatenate([rng.integers(0, 256, (64, 64, 3)), np.full((64, 64, 1), 255)], 2).astype(np.uint8)
        out, b = back(png_pal.encode(png(Image.fromarray(a, "RGBA"))))
        self.assertEqual(out.mode, "P")
        self.assertIn("transparency", out.info)
        self.assertTrue((b[..., 3] == 255).all())

    def test_soft_alpha_edge_and_gradient(self):
        h, w = 120, 200
        x = np.linspace(0, 1, w)[None, :].repeat(h, 0)
        y = np.linspace(0, 1, h)[:, None].repeat(w, 1)
        a = np.stack([x * 255, y * 255, (1 - x) * 200 + 30, np.clip((1 - y) * 400, 0, 255)], 2).astype(np.uint8)
        _, b = back(png_pal.encode(png(Image.fromarray(a, "RGBA"))))
        src = a.astype(int)
        self.assertLessEqual(np.abs(b[..., 3] - src[..., 3]).max(), 24)            # the fade keeps its steps small
        vis = src[..., 3] > 64
        self.assertLess(np.abs(b[..., :3] - src[..., :3])[vis].mean(), 8)
        self.assertTrue((b[src[..., 3] == 0][:, 3] == 0).all())                      # transparent stays transparent

    def test_grey_art_no_colour_cast(self):
        g = (np.add.outer(np.arange(300), np.arange(300)) % 256).astype(np.uint8)
        a = np.stack([g, g, g, np.full_like(g, 255)], 2)
        _, b = back(png_pal.encode(png(Image.fromarray(a, "RGBA"))))
        self.assertLessEqual(np.abs(b[..., 0] - b[..., 1]).max(), 2)
        self.assertLessEqual(np.abs(b[..., 1] - b[..., 2]).max(), 2)

    def test_keep_paths(self):
        # full-screen key art (KEEP): a picture with more than 255 colours is left alone, one with few colours is still converted
        import tempfile
        rng = np.random.default_rng(5)
        many = np.concatenate([rng.integers(0, 256, (64, 64, 3)), np.full((64, 64, 1), 255)], 2).astype(np.uint8)
        tab = np.concatenate([rng.integers(0, 256, (200, 3)), np.full((200, 1), 255)], 1).astype(np.uint8)
        few = tab[rng.integers(0, 200, (128, 128))]                      # 200 colours: the palette file is the smaller one
        with tempfile.TemporaryDirectory(prefix="t2r-tmp-pngpal-") as d:
            kd = os.path.join(d, "gtex1", "streaming", "t2r", "clanev"); od = os.path.join(d, "gtex1", "streaming", "t2r", "other")
            os.makedirs(kd); os.makedirs(od)
            for dd in (kd, od):
                Image.fromarray(many, "RGBA").save(os.path.join(dd, "many.png")); Image.fromarray(few, "RGBA").save(os.path.join(dd, "few.png"))
            cache, png_pal.CACHE = png_pal.CACHE, os.path.join(d, "cache")
            try:
                for f in png_pal.stage_files(d):
                    png_pal._one(f)
            finally:
                png_pal.CACHE = cache
            self.assertEqual(Image.open(os.path.join(kd, "many.png")).mode, "RGBA")
            self.assertTrue((np.asarray(Image.open(os.path.join(kd, "many.png"))) == many).all())
            self.assertEqual(Image.open(os.path.join(od, "many.png")).mode, "P")
            self.assertEqual(Image.open(os.path.join(kd, "few.png")).mode, "P")


if __name__ == "__main__":
    unittest.main()
