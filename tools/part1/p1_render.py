"""Tiny orthographic software renderer (numpy + PIL only; the repo venv has no matplotlib) for gun previews.

    render(meshes, view, size) -> PIL image
    mesh = {"P": (n,3), "I": (m,3), and one of  "color": (n,3) 0..1 per vertex  |  "UV": (n,2) + "tex": (h,w,3) uint8,
            "alpha": 1.0}
    view: "side" (z right, y up), "top" (z right, x up), "front" (x right, y up); the model frame is ND's:
    z = muzzle direction, y = up, grip origin at 0.
"""
import numpy as np
from PIL import Image, ImageDraw

AXES = {"side": (2, 1, 0), "top": (2, 0, 1), "front": (0, 1, 2)}
LIGHT = np.array([0.3, 0.6, 0.75]) / np.linalg.norm([0.3, 0.6, 0.75])


def bounds(meshes, view):
    a, b, _ = AXES[view]
    pts = np.concatenate([m["P"][:, [a, b]] for m in meshes])
    return pts.min(0), pts.max(0)


def render(meshes, view="side", size=(1000, 500), bg=(30, 32, 36), extent=None, margin=24, sign=1):
    a, b, d = AXES[view]
    lo, hi = extent if extent is not None else bounds(meshes, view)
    W, H = size
    s = min((W - 2 * margin) / max(hi[0] - lo[0], 1e-6), (H - 2 * margin) / max(hi[1] - lo[1], 1e-6))
    img = np.zeros((H, W, 3), np.float32)
    img[:] = bg
    zb = np.full((H, W), -1e9, np.float32)
    for m in meshes:
        P, I = np.asarray(m["P"], float), np.asarray(m["I"])
        x = margin + (P[:, a] - lo[0]) * s
        y = H - margin - (P[:, b] - lo[1]) * s
        z = P[:, d] * sign
        tri = P[I]
        fn = np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0])
        fn /= np.maximum(np.linalg.norm(fn, axis=1, keepdims=True), 1e-12)
        shade = 0.45 + 0.55 * np.abs(fn @ LIGHT)
        tex = m.get("tex")
        for t in range(len(I)):
            i0, i1, i2 = I[t]
            if i0 == i1 or i1 == i2 or i0 == i2:
                continue
            xs, ys = x[[i0, i1, i2]], y[[i0, i1, i2]]
            x0, x1 = max(int(np.floor(xs.min())), 0), min(int(np.ceil(xs.max())), W - 1)
            y0, y1 = max(int(np.floor(ys.min())), 0), min(int(np.ceil(ys.max())), H - 1)
            if x1 < x0 or y1 < y0:
                continue
            den = (ys[1] - ys[2]) * (xs[0] - xs[2]) + (xs[2] - xs[1]) * (ys[0] - ys[2])
            if abs(den) < 1e-9:
                continue
            gx, gy = np.meshgrid(np.arange(x0, x1 + 1) + 0.5, np.arange(y0, y1 + 1) + 0.5)
            w0 = ((ys[1] - ys[2]) * (gx - xs[2]) + (xs[2] - xs[1]) * (gy - ys[2])) / den
            w1 = ((ys[2] - ys[0]) * (gx - xs[2]) + (xs[0] - xs[2]) * (gy - ys[2])) / den
            w2 = 1 - w0 - w1
            inside = (w0 >= -0.02) & (w1 >= -0.02) & (w2 >= -0.02)
            if not inside.any():
                continue
            zz = w0 * z[i0] + w1 * z[i1] + w2 * z[i2]
            win = inside & (zz > zb[y0:y1 + 1, x0:x1 + 1])
            if not win.any():
                continue
            if tex is not None:
                uv = np.asarray(m["UV"])
                u = w0 * uv[i0, 0] + w1 * uv[i1, 0] + w2 * uv[i2, 0]
                v = w0 * uv[i0, 1] + w1 * uv[i1, 1] + w2 * uv[i2, 1]
                th, tw = tex.shape[:2]
                px = np.clip((u % 1.0 * tw).astype(int), 0, tw - 1)
                py = np.clip((v % 1.0 * th).astype(int), 0, th - 1)
                col = tex[py, px].astype(np.float32) / 255.0
            else:
                c = np.asarray(m["color"])
                col = (w0[..., None] * c[i0] + w1[..., None] * c[i1] + w2[..., None] * c[i2])
            col = col * shade[t] * 255.0
            region = img[y0:y1 + 1, x0:x1 + 1]
            region[win] = col[win]
            zb[y0:y1 + 1, x0:x1 + 1][win] = zz[win]
    out = Image.fromarray(np.clip(img, 0, 255).astype(np.uint8))
    return out


def label(img, text, xy=(8, 6), fill=(220, 220, 220)):
    ImageDraw.Draw(img).text(xy, text, fill=fill)
    return img
