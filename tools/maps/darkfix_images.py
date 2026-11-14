"""Before / after pictures of a lightmap_fix repair (offline, CPU): the baked lightColor of every charted texel near the gone geometry, splatted at
its world position (top-down for floors / snow, side-on for walls), plus the atlas crops.  Called by lightmap_fix.apply(png=DIR)."""
import os

import numpy as np
from PIL import Image, ImageDraw


def tone(v, ev=3.0):
    v = np.maximum(np.asarray(v, np.float64), 0) * ev
    v = v / (1 + v)
    return np.clip(255 * v ** (1 / 2.2), 0, 255).astype(np.uint8)


def splat(P, C, ax, box, px=0.03, depth=None, rad=None):
    rad = rad if rad is not None else (2 if px >= 0.03 else 4)
    """P world points, C (n,3) uint8, ax = (u axis, v axis, depth axis, depth sign) -> RGB image over box (u0, v0, u1, v1)"""
    u0, v0, u1, v1 = box
    w, h = int((u1 - u0) / px) + 1, int((v1 - v0) / px) + 1
    img = np.full((h, w, 3), 40, np.uint8)
    zb = np.full((h, w), -1e9)
    u = ((P[:, ax[0]] - u0) / px).astype(int)
    v = (h - 1 - (P[:, ax[1]] - v0) / px).astype(int)
    z = P[:, ax[2]] * ax[3]
    for du in range(-rad, rad + 1):
        for dv in range(-rad, rad + 1):
            uu, vv = u + du, v + dv
            ok = (uu >= 0) & (uu < w) & (vv >= 0) & (vv < h)
            o = np.argsort(z[ok])
            uu, vv, zz, cc = uu[ok][o], vv[ok][o], z[ok][o], C[ok][o]
            better = zz >= zb[vv, uu] - 1e-6
            img[vv[better], uu[better]] = cc[better]
            zb[vv[better], uu[better]] = np.maximum(zb[vv[better], uu[better]], zz[better])
    return img


def _label(im, text):
    d = ImageDraw.Draw(im)
    d.rectangle([0, 0, 8 * len(text) + 8, 16], fill=(0, 0, 0))
    d.text((4, 2), text, fill=(255, 255, 255))
    return im


def views(tx, w, box3, kind):
    """texel selection + axes for a view of box3 (x0 y0 z0 x1 y1 z1): kind 'top' or 'side-x' (wall facing x) / 'side-z'"""
    lo, hi = np.array(box3[:3]), np.array(box3[3:])
    m = (tx.P >= lo).all(1) & (tx.P <= hi).all(1)
    if kind == "top":
        m &= tx.N[:, 1] > 0.3
        return m, (0, 2, 1, 1), (lo[0], lo[2], hi[0], hi[2])
    if kind == "side-x":
        m &= np.abs(tx.N[:, 0]) > 0.7
        return m, (2, 1, 0, -np.sign(np.median(tx.N[m, 0])) if m.any() else 1), (lo[2], lo[1], hi[2], hi[1])
    m &= np.abs(tx.N[:, 2]) > 0.7
    return m, (0, 1, 2, -np.sign(np.median(tx.N[m, 2])) if m.any() else 1), (lo[0], lo[1], hi[0], hi[1])


def compare(diag, box3, kind, png, title, px=None):
    px = px or (0.03 if kind == "top" else 0.015)
    tx, w = diag["tx"], diag["w"]
    m, ax, box = views(tx, w, box3, kind)
    if m.sum() < 20:
        return False
    old = diag["imgs"]["basis1_lightColor"][tx.y[m], tx.x[m]]
    new = diag["new"]["basis1_lightColor"][tx.y[m], tx.x[m]]
    a = splat(tx.P[m], tone(old), ax, box, px)
    b = splat(tx.P[m], tone(new), ax, box, px)
    wm = np.stack([np.clip(w[m] * 255, 0, 255)] * 3, 1).astype(np.uint8)
    wm[:, 1] = (wm[:, 1] * 0.35).astype(np.uint8)
    wm[:, 2] = (wm[:, 2] * 0.2).astype(np.uint8)
    c = splat(tx.P[m], wm, ax, box, px)
    gT = diag.get("gT")
    if gT is not None and len(gT):                          # gone geometry (stock positions) as cyan dots over the weight panel
        lo3, hi3 = np.array(box3[:3]) - 0.5, np.array(box3[3:]) + 0.5
        G = gT.reshape(-1, 3)
        G = np.concatenate([G, gT.mean(1)])
        G = G[(G >= lo3).all(1) & (G <= hi3).all(1)]
        if len(G):
            h, wd = c.shape[:2]
            u = ((G[:, ax[0]] - box[0]) / px).astype(int)
            v = (h - 1 - (G[:, ax[1]] - box[1]) / px).astype(int)
            ok = (u >= 0) & (u < wd) & (v >= 0) & (v < h)
            c = c.copy()
            c[v[ok], u[ok]] = (0, 200, 255)
    ims = [_label(Image.fromarray(a), "before (shipped night52)"), _label(Image.fromarray(b), "after (lightmap_fix)"),
           _label(Image.fromarray(c), "repair weight (red) + gone geometry (cyan)")]
    W = sum(i.width for i in ims) + 20
    out = Image.new("RGB", (W, ims[0].height + 24), (20, 20, 20))
    x = 0
    for i in ims:
        out.paste(i, (x, 24)); x += i.width + 10
    ImageDraw.Draw(out).text((6, 5), title, fill=(230, 230, 230))
    out.save(png)
    return True


def atlas_crop(diag, png, title, pad=24, maxw=900):
    """before / after crop of the atlas around the changed texels (lightColor)"""
    tx, dst, ok = diag["tx"], diag["dst"], diag["ok"]
    if not len(dst) or not ok.any():
        return False
    xs, ys = tx.x[dst[ok]], tx.y[dst[ok]]
    # the densest 512 x 512 window of changed texels
    H, W = diag["H"], diag["W"]
    hist, xe, ye = np.histogram2d(xs, ys, bins=[max(1, W // 256), max(1, H // 256)], range=[[0, W], [0, H]])
    i, j = np.unravel_index(hist.argmax(), hist.shape)
    sel = (xs >= xe[i] - 128) & (xs < xe[i + 1] + 128) & (ys >= ye[j] - 128) & (ys < ye[j + 1] + 128)
    x0, x1 = max(0, xs[sel].min() - pad), min(W, xs[sel].max() + pad)
    y0, y1 = max(0, ys[sel].min() - pad), min(H, ys[sel].max() + pad)
    a = tone(diag["imgs"]["basis1_lightColor"][y0:y1, x0:x1])
    b = tone(diag["new"]["basis1_lightColor"][y0:y1, x0:x1])
    s = max(1, int(maxw // (2 * (x1 - x0) + 10)))
    A = _label(Image.fromarray(a).resize(((x1 - x0) * s, (y1 - y0) * s), Image.NEAREST), "atlas before")
    B = _label(Image.fromarray(b).resize(((x1 - x0) * s, (y1 - y0) * s), Image.NEAREST), "atlas after")
    out = Image.new("RGB", (A.width * 2 + 10, A.height + 24), (20, 20, 20))
    out.paste(A, (0, 24)); out.paste(B, (A.width + 10, 24))
    ImageDraw.Draw(out).text((6, 5), title + "  texels x %d..%d y %d..%d" % (x0, x1, y0, y1), fill=(230, 230, 230))
    out.save(png)
    return True


VIEWS = {   # reported places (jackson-market), world boxes
    "pat-jackson-supermarket": [("post-office-wall-courtyard", [-506.5, 17.8, 280.0, -505.8, 21.0, 300.0], "side-x")],
    "pat-jackson-alley": [("courtyard-snow-top", [-534.0, 16.0, 281.0, -505.0, 21.0, 299.0], "top")],
}


def vertex_images(lv, vd, d):
    """per-vertex lit props: before / after baked vertex light (Basis3Luminance sum) of the repaired draw items, side or top view"""
    done = []
    if vd is None:
        return done
    os.makedirs(d, exist_ok=True)
    P, w = vd["P"], vd["w"]
    rep = np.unique(vd["own"][w > 0])
    cnt = [(int(((vd["own"] == k) & (w > 0)).sum()), k) for k in rep]
    for n, k in sorted(cnt, reverse=True)[:6]:
        m = vd["own"] == k
        lo, hi = P[m].min(0) - 0.6, P[m].max(0) + 0.6
        near = (P >= lo).all(1) & (P <= hi).all(1)
        ext = hi - lo
        if ext[1] < 0.5 * max(ext[0], ext[2]):
            ax, box = (0, 2, 1, 1), (lo[0], lo[2], hi[0], hi[2])
        elif ext[0] < ext[2]:
            ax, box = (2, 1, 0, -1), (lo[2], lo[1], hi[2], hi[1])
        else:
            ax, box = (0, 1, 2, -1), (lo[0], lo[1], hi[0], hi[1])
        px = max(ext) / 500
        T = vd["tris"]
        T = T[near[T].any(1)]                                   # gouraud: sample every triangle densely, interpolate the vertex values
        A = 0.5 * np.linalg.norm(np.cross(P[T[:, 1]] - P[T[:, 0]], P[T[:, 2]] - P[T[:, 0]]), axis=1)
        cnt = np.clip((A / px ** 2 * 1.5).astype(int), 3, 4000)
        ti = np.repeat(np.arange(len(T)), cnt)
        rng = np.random.default_rng(0)
        u, v = rng.random(len(ti)), rng.random(len(ti))
        fl = u + v > 1
        u[fl], v[fl] = 1 - u[fl], 1 - v[fl]
        bc = np.c_[1 - u - v, u, v]
        Q = (P[T[ti]] * bc[:, :, None]).sum(1)
        val = lambda a: (a[T[ti]] * bc).sum(1)
        mk = lambda a: splat(Q, tone(np.stack([val(a)] * 3, 1) / 3, 3.0), ax, box, px, rad=1)
        wq = val(w)
        wm = np.stack([np.clip(wq * 255, 0, 255)] * 3, 1).astype(np.uint8)
        wm[:, 1] //= 3; wm[:, 2] //= 5
        ims = [_label(Image.fromarray(mk(vd["before"])), "vertex light before"), _label(Image.fromarray(mk(vd["after"])), "after"),
               _label(Image.fromarray(splat(Q, wm, ax, box, px, rad=1)), "repair weight")]
        out = Image.new("RGB", (sum(i.width for i in ims) + 20, ims[0].height + 24), (20, 20, 20))
        x = 0
        for i in ims:
            out.paste(i, (x, 24)); x += i.width + 10
        rec, sub, name = vd["items"][k]
        ImageDraw.Draw(out).text((6, 5), "%s  vertex-lit %s (rec 0x%x s%d, %d vertices repaired)" % (lv, name.split("|")[0].split("/")[-1], rec, sub, n), fill=(230, 230, 230))
        f = os.path.join(d, "%s-vertex-%x-s%d.png" % (lv.replace("pat-jackson-", ""), rec, sub))
        out.save(f)
        done.append(f)
    return done


def level_images(lv, diag, d):
    os.makedirs(d, exist_ok=True)
    done = vertex_images(lv, diag.get("vtx"), d)
    if "tx" not in diag:
        for f in done:
            print("    image", f)
        return done
    for nm, box, kind in VIEWS.get(lv, []):
        f = os.path.join(d, "%s-%s.png" % (lv.replace("pat-jackson-", ""), nm))
        if compare(diag, box, kind, f, "%s  %s  baked lightColor (tonemapped)" % (lv, nm)):
            done.append(f)
    # the biggest clusters of changed texels (2 m cells)
    tx, w = diag["tx"], diag["w"]
    ch = w > 0
    if ch.any():
        c = np.floor(tx.P[ch] / 3.0).astype(int)
        keys, cnt = np.unique(c, axis=0, return_counts=True)
        for k in np.argsort(-cnt)[:4]:
            cc = keys[k] * 3.0
            sel = ch.copy()
            sel[ch] = (c == keys[k]).all(1)
            P, N = tx.P[sel], tx.N[sel]
            kind = "top" if np.median(N[:, 1]) > 0.5 else ("side-x" if np.median(np.abs(N[:, 0])) > np.median(np.abs(N[:, 2])) else "side-z")
            box = [cc[0] - 2, cc[1] - 1.5, cc[2] - 2, cc[0] + 5, cc[1] + 4.5, cc[2] + 5]
            f = os.path.join(d, "%s-cluster-%d_%d_%d-%s.png" % (lv.replace("pat-jackson-", ""), *[int(v) for v in cc], kind))
            if compare(diag, box, kind, f, "%s  cluster at %s (%d rebaked texels)  baked lightColor" % (lv, cc.astype(int).tolist(), int(cnt[k]))):
                done.append(f)
    f = os.path.join(d, "%s-atlas.png" % lv.replace("pat-jackson-", ""))
    if atlas_crop(diag, f, lv + " lightColor atlas"):
        done.append(f)
    for f in done:
        print("    image", f)
    return done
