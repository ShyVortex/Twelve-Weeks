"""Top-down preview of level collision (decoded from converted TLOU2 -phys paks, or Part I -phys paks) against the level
render geometry (the world-space GEOMETRY_1 submeshes of the Part I level paks).

  python havok_preview.py --phys <-phys.pak>... --geo <part I level.pak>... --out <png> [--mpp=0.08]
Panels: render geometry (height shaded) | collision (height shaded, steep faces darker) | collision edges over geometry.
Output belongs in <main>/re/part1/preview/ (git-ignored: it pictures Part I content).
"""
import os
import struct
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "models"))


def collision_tris(paths):
    import havok_convert as hc
    out = []
    for p in paths:
        data = open(p, "rb").read()
        if struct.unpack_from("<I", data, 0)[0] == 0xA7D:
            for it in hc.p1_collision_items(data):
                out.append(hc.triangles(hc.p1_mesh(it["data"]))[1])
        else:
            for d in hc.t2_collision_items(p):
                out.append(hc.triangles(hc.t2_mesh(d["tag"]))[1])
    return np.concatenate(out) if out else np.zeros((0, 3, 3))


def geometry_tris(paths, lo, hi):
    """triangles of the submeshes that are already in world space (their box overlaps the collision box)"""
    import p1mesh
    out = []
    for p in paths:
        m = p1mesh.P1Mesh(p)
        for s in m.submesh_table():
            try:
                g = m.mesh(s)
            except Exception:              # noqa: BLE001 - unsupported stream layouts are skipped
                continue
            P, I = g["P"], g["I"].reshape(-1, 3)
            a, b = P.min(0), P.max(0)
            inter = np.clip(np.minimum(b, hi) - np.maximum(a, lo), 0, None)
            if (inter[[0, 2]] <= 0).any() or np.prod(inter[[0, 2]]) < 0.5 * np.prod(np.maximum(b - a, 1e-3)[[0, 2]]):
                continue
            out.append(P[I])
    return np.concatenate(out) if out else np.zeros((0, 3, 3))


def shade(tris, lo, hi, mpp, size, steep_dark=True, base=None):
    from PIL import Image, ImageDraw
    img = base.copy() if base is not None else Image.new("RGB", size, (24, 26, 30))
    dr = ImageDraw.Draw(img)
    order = np.argsort(tris[:, :, 1].max(1))
    n = np.cross(tris[:, 1] - tris[:, 0], tris[:, 2] - tris[:, 0])
    ny = np.abs(n[:, 1]) / np.maximum(np.linalg.norm(n, axis=1), 1e-12)
    h = np.clip((tris[:, :, 1].mean(1) - lo[1]) / max(hi[1] - lo[1], 1e-6), 0, 1)
    for i in order:
        t = tris[i]
        pts = [((x - lo[0]) / mpp, (z - lo[2]) / mpp) for x, _, z in t]
        c = np.array([60 + 150 * h[i], 90 + 120 * (1 - abs(h[i] - 0.5) * 2), 200 - 150 * h[i]])
        if steep_dark:
            c = c * (0.35 + 0.65 * ny[i])
        dr.polygon(pts, fill=tuple(int(v) for v in c))
    return img


def edges(img, tris, lo, mpp, color=(255, 60, 60)):
    from PIL import ImageDraw
    dr = ImageDraw.Draw(img)
    for t in tris:
        pts = [((x - lo[0]) / mpp, (z - lo[2]) / mpp) for x, _, z in t]
        dr.line(pts + pts[:1], fill=color, width=1)
    return img


def main(argv):
    from PIL import Image, ImageDraw
    args, cur = {"--phys": [], "--geo": []}, None
    opts = {}
    for a in argv[1:]:
        if a in ("--phys", "--geo"):
            cur = a
        elif a.startswith("--"):
            k, _, v = a.partition("=")
            opts[k] = v
            cur = None if "=" in a else k
        elif cur in args:
            args[cur].append(a)
        elif cur == "--out":
            opts["--out"] = a
            cur = None
    mpp = float(opts.get("--mpp", 0.08))
    out = opts.get("--out") or os.path.join(os.environ.get("T2R_MAIN_ROOT", os.path.dirname(os.path.dirname(HERE)).split(
        os.sep + ".claude" + os.sep)[0]), "re", "part1", "preview", "collision.png")
    col = collision_tris(args["--phys"])
    v = col.reshape(-1, 3)
    lo, hi = v.min(0) - 1, v.max(0) + 1
    size = (int((hi[0] - lo[0]) / mpp) + 1, int((hi[2] - lo[2]) / mpp) + 1)
    geo = geometry_tris(args["--geo"], lo, hi) if args["--geo"] else np.zeros((0, 3, 3))
    p_geo = shade(geo, lo, hi, mpp, size, steep_dark=True)
    p_col = shade(col, lo, hi, mpp, size)
    grey = p_geo.convert("L").convert("RGB")
    p_ov = edges(grey, col, lo, mpp)
    W = Image.new("RGB", (3 * size[0] + 40, size[1] + 40), (12, 12, 14))
    for k, p in enumerate((p_geo, p_col, p_ov)):
        W.paste(p, (10 + k * (size[0] + 10), 30))
    d = ImageDraw.Draw(W)
    d.text((10, 8), "render geometry (%d tris, world-space submeshes)" % len(geo), fill=(220, 220, 220))
    d.text((20 + size[0], 8), "collision (%d tris), x %.1f..%.1f z %.1f..%.1f, y %.1f..%.1f" % (
        len(col), lo[0] + 1, hi[0] - 1, lo[2] + 1, hi[2] - 1, lo[1] + 1, hi[1] - 1), fill=(220, 220, 220))
    d.text((30 + 2 * size[0], 8), "collision edges over geometry (top-down, +x right, +z down)", fill=(220, 220, 220))
    os.makedirs(os.path.dirname(out), exist_ok=True)
    W.save(out)
    print(out, W.size, "collision tris", len(col), "geometry tris", len(geo))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
