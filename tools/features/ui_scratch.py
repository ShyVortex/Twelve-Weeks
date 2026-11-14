"""Scratched dark panel (gradient rounds v6-v8): a soft dark gradient with the in-game notifications' grain and a few varied,
slightly blurred claw tears at one edge (45 % of a claw on the panel). rip_layer() is the generator (alpha cuts + 1 px lit lip + torn
fibres inside the cut), make_gearup_panel() the GEAR UP page backdrop shipped by tools/models/figures/ship.py as
gtex1/streaming/t2r/clan/gearup-panel*.png (replaces the page's flat dark fill)."""
import numpy as np
from PIL import Image, ImageDraw, ImageFilter


def smooth_noise(r, n, k):
    m = max(3, n // k + 2)
    v = r.normal(0, 1, m)
    return np.interp(np.linspace(0, m - 1, n), np.arange(m), v)


def blur_noise(r, h, w, sig, amp=50):
    g = r.normal(0, 1, (h, w))
    return np.array(Image.fromarray(np.clip(g * amp + 128, 0, 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(sig))) / 255.0 - 0.5


def blur(x, s):
    return np.array(Image.fromarray(np.clip(x * 255, 0, 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(s))) / 255.0


CLAW_BLUR = 1.8
VAR_L = [1.0, 0.72, 0.93, 0.55]   # claw lengths differ (a real swipe: middle fingers longest, the last one barely drags)
VAR_W = [1.0, 1.25, 0.8, 0.55]


def rip_layer(a, seed, size_ref, tears=4, inside=0.45, theta_deg=60, grit=1.0, core_boost=0.15, gamma=0.82,
              tint=(10, 8, 7), cy=None, wscale=1.0, lscale=1.0, sp_scale=0.2, edge_t=0.55, ymin=None,
              base_grit=0.25, edge_grit=1.0, clean_rects=()):
    """a: float alpha (H,W). Cuts are transparent (alpha 0). Only a 1px warm-grey rim on the cut edges, scaled by the local
    dark alpha so it vanishes where the dark does. Grit is neutral grain inside the dark only, denser near edges/claws,
    clean inside clean_rects (x0,y0,x1,y1 in full-image px)."""
    r = np.random.default_rng(seed)
    r2 = np.random.default_rng(seed + 7919)   # variety / fibres: own stream, so the v6 claw placement stays the same
    H, W = a.shape
    mx = a.max()
    a = np.clip(a ** gamma + core_boost * a / max(mx, 1e-6), 0, 1)
    ys, xs = np.nonzero(a > 0.02)
    y0, y1, x0, x1 = ys.min(), ys.max() + 1, xs.min(), xs.max() + 1
    X0, Y0, X1, Y1 = max(0, x0 - 4), max(0, y0 - 4), min(W, x1 + 4), min(H, y1 + 4)
    A = a[Y0:Y1, X0:X1]
    h, w = A.shape
    gate = np.ones((h, w)); ggate = np.ones((h, w))
    if ymin is not None:
        gate = np.clip((np.arange(h)[:, None] + Y0 - ymin) / 7.0, 0, 1) * np.ones((1, w))
        ggate = np.clip((np.arange(h)[:, None] + Y0 - ymin) / 40.0, 0, 1) ** 1.5 * np.ones((1, w))
    # ---- claws (geometry first, so grit can cluster around them)
    SS = 4
    cutI = Image.new('L', (w * SS, h * SS), 0)
    rimI = Image.new('L', (w * SS, h * SS), 0)
    dc, dr = ImageDraw.Draw(cutI), ImageDraw.Draw(rimI)
    th = np.radians(theta_deg)
    dx, dy = np.cos(th), np.sin(th)
    dx0, dy0 = dx, dy
    nx, ny = -dy, dx
    L0 = size_ref * lscale
    sp = size_ref * sp_scale
    ccy = (cy - Y0) if cy is not None else np.nonzero(A.max(1) > 0)[0].mean()
    row = A[int(np.clip(ccy, 0, h - 1))]
    cols = np.nonzero(row >= edge_t)[0]
    EX = cols[-1] if len(cols) else w * 0.8
    wmax0 = max(1.6, size_ref * 0.04) * wscale

    def prof(u):
        if u < 0.2:
            return (u / 0.2) ** 0.8
        return max(0.0, (1 - u) / 0.8) ** 1.1
    n = 70
    for k in range(tears):
        off = (k - (tears - 1) / 2) * sp + r.uniform(-0.06, 0.06) * sp + r2.uniform(-0.22, 0.22) * sp
        Lk = L0 * r.uniform(0.85, 1.0) * VAR_L[k % len(VAR_L)] * r2.uniform(0.92, 1.05)
        tk = th + np.radians(r2.uniform(-6, 6))
        dx, dy = np.cos(tk), np.sin(tk)
        st = r2.uniform(-0.12, 0.12) * Lk
        cxp = EX + nx * off + dx * st
        cyp = ccy + ny * off + dy * st
        curv = r.uniform(0.04, 0.08) + r2.uniform(-0.09, 0.04)
        pts = []
        for i in range(n + 1):
            u = i / n
            s = (u - inside) * Lk
            bend = curv * Lk * (u - 0.35) ** 2
            pts.append((u, cxp + dx * s + nx * bend, cyp + dy * s + ny * bend))
        nl, nr = smooth_noise(r, n + 1, 9), smooth_noise(r, n + 1, 4)
        nl2, nr2 = smooth_noise(r, n + 1, 9), smooth_noise(r, n + 1, 4)
        wmax = wmax0 * r.uniform(0.85, 1.15) * VAR_W[k % len(VAR_W)]
        Lp, Rp, ws = [], [], []
        for i, (u, bx, by) in enumerate(pts):
            wd = wmax * prof(u)
            jl = wd * 0.15 * nl[i] + 0.08 * wmax * nr[i] * (wd > 0.3)
            jr = wd * 0.15 * nl2[i] + 0.08 * wmax * nr2[i] * (wd > 0.3)
            wl, wr = max(0.0, wd + jl), max(0.0, wd + jr)
            Lp.append(((bx + nx * wl) * SS, (by + ny * wl) * SS))
            Rp.append(((bx - nx * wr) * SS, (by - ny * wr) * SS))
            ws.append((wl, wr))
        dc.polygon(Lp + Rp[::-1], fill=255)
        rw = 1.3   # 1px-ish edge ring
        for i in range(n):
            _, bx, by = pts[i]
            _, bx2, by2 = pts[i + 1]
            wl, wr = ws[i]
            wl2, wr2 = ws[i + 1]
            q = [((bx + nx * (wl + rw)) * SS, (by + ny * (wl + rw)) * SS), ((bx2 + nx * (wl2 + rw)) * SS, (by2 + ny * (wl2 + rw)) * SS),
                 ((bx2 - nx * (wr2 + rw)) * SS, (by2 - ny * (wr2 + rw)) * SS), ((bx - nx * (wr + rw)) * SS, (by - ny * (wr + rw)) * SS)]
            dr.polygon(q, fill=255)
    cb = CLAW_BLUR if size_ref >= 150 else 0.01   # notifications keep the crisp v6 claws (approved)
    cut = np.array(cutI.resize((w, h), Image.BOX).filter(ImageFilter.GaussianBlur(cb))) / 255.0 * gate
    rimr = np.array(rimI.resize((w, h), Image.BOX).filter(ImageFilter.GaussianBlur(cb * 1.3))) / 255.0 * gate
    rim = np.clip(rimr - cut, 0, 1)
    # ---- depth: streaks along the swipe (torn fibres left in the cut), a lit upper lip and a shadowed lower lip
    yy_, xx_ = np.mgrid[0:h, 0:w].astype(float)
    across = xx_ * nx + yy_ * ny                        # perpendicular coordinate: lines run along the swipe
    along = xx_ * dx0 + yy_ * dy0
    fib = np.interp(across, np.linspace(across.min(), across.max(), 4000), r2.normal(0, 1, 4000))
    fib = blur(np.clip(fib * 0.25 + 0.5, 0, 1), 0.7) - 0.5
    lowf = np.interp(along, np.linspace(along.min(), along.max(), 60), r2.normal(0, 1, 60))
    small = float(np.clip((size_ref - 60) / 200.0, 0, 1))   # notifications: thin claws, fewer fibres left in the cut
    keep = np.clip((0.22 + fib * 1.6 + lowf * 0.10) * (0.2 + 0.8 * small), 0, 0.75) * (cut > 0.05)
    sh = 2
    up = np.roll(np.roll(cut, -int(round(ny * sh)), 0), -int(round(nx * sh)), 1)
    dn = np.roll(np.roll(cut, int(round(ny * sh)), 0), int(round(nx * sh)), 1)
    lip_hi = blur(np.clip(cut - dn, 0, 1), 0.5)          # the edge facing the light
    lip_sh = blur(np.clip(dn - cut, 0, 1), 1.6)          # the dark under the other lip
    cut = np.clip(cut * (1 - keep), 0, 1)
    # ---- grit weight map: faint base, more near the dark's edge and the claws, clean behind text
    amax = max(A.max(), 1e-6)
    edgew = np.clip(1 - A / (0.9 * amax), 0, 1) ** 0.8 * (A > 0.03)
    clawn = blur(cut, 9) * 3.0
    wmap = np.clip(base_grit + edge_grit * edgew * 0.9 + clawn, 0, 1.6)
    for (rx0, ry0, rx1, ry1) in clean_rects:
        m = np.zeros((h, w))
        m[max(0, int(ry0 - Y0)):max(0, int(ry1 - Y0)), max(0, int(rx0 - X0)):max(0, int(rx1 - X0))] = 1
        m = blur(m, 14)
        wmap = wmap * (1 - 0.85 * m)
    g = blur_noise(r, h, w, 0.6)
    g2 = blur_noise(r, h, w, 1.5)
    gmod = (g * 1.4 + g2 * 1.0) * wmap * grit * ggate
    Ag = np.clip(A * (1 + gmod) , 0, 1)
    # a few short scratches, only where the weight is high
    sc = Image.new('L', (w, h), 0)
    d = ImageDraw.Draw(sc)
    cand = np.argwhere((wmap > 0.7) & (A > 0.25))
    if len(cand):
        for _ in range(int(len(cand) / 2500 * grit) + 2):
            yy, xx = cand[r.integers(len(cand))]
            L = r.uniform(0.03, 0.09) * size_ref * 3
            t = np.radians(theta_deg + r.uniform(-12, 12)) if r.random() < 0.7 else np.radians(r.uniform(0, 180))
            bnd = r2.uniform(-0.15, 0.15)
            pts_ = [(xx + L * q * np.cos(t + bnd * q), yy + L * q * np.sin(t + bnd * q)) for q in np.linspace(0, 1, 6)]
            d.line(pts_, fill=int(r.uniform(35, 80)), width=1)
    scr = np.array(sc) / 255.0
    Ag = np.clip(Ag - scr * 0.45 * A, 0, 1)
    Ac = Ag * (1 - cut)
    # colour: neutral near-black, grain modulates brightness a little (inside the dark only)
    col = np.zeros((h, w, 3)) + np.array(tint) + (g[..., None] * 16 * wmap[..., None] * grit)
    # rim: 1px warm grey, scaled by local dark alpha (vanishes where the dark does)
    localA = blur(np.where(cut > 0.02, 0, A), 2)
    ra = np.clip(rim * 1.0 * np.clip(localA * 1.8, 0, 1), 0, 1)
    rimcol = np.array([150, 140, 126])
    Ac = np.clip(Ac + lip_sh * 0.55 * localA.clip(0, 1) ** 0.5, 0, 1)
    if size_ref >= 150:
        ra = np.clip(ra * 0.5 + lip_hi * 1.0 * np.clip(localA * 2.2, 0, 1), 0, 1)
        rimcol = np.array([196, 186, 168])
    else:
        ra = np.clip(ra + lip_hi * 0.5 * np.clip(localA * 2.2, 0, 1), 0, 1)
    A2 = np.clip(Ac + ra * (1 - Ac), 0, 1)
    C = (col * Ac[..., None] + rimcol * (ra * (1 - Ac))[..., None]) / np.maximum(A2, 1e-4)[..., None]
    full = np.zeros((H, W, 4), np.uint8)
    full[Y0:Y1, X0:X1, :3] = np.clip(C, 0, 255)
    full[Y0:Y1, X0:X1, 3] = np.clip(A2 * 255, 0, 255)
    return Image.fromarray(full, 'RGBA')


def make_gearup_panel(W=1920, H=1080):
    """Full-screen RGBA: dark over the GEAR UP content box (widget units 270..3525 x 140..1960 of 3840 x 2160), fading to 0 at the
    screen edges; claws in the right edge band beside the content."""
    k = W / 1280.0
    # RADIAL - the middle most prominent (max alpha 0.66, never opaque), fading over a wide radius to the edges: a smooth cos^2 of the
    # normalised elliptical distance (slightly wider than tall for 16:9), flat in the very centre, no bands.
    y, x = np.mgrid[0:H, 0:W].astype(float)
    cx, cy = W * 0.5, H * 0.52
    r = np.sqrt(((x - cx) / (W * 0.86)) ** 2 + ((y - cy) / (H * 0.86)) ** 2)
    t = np.clip((r - 0.22) / 0.78, 0, 1)
    e = np.cos(t * np.pi / 2) ** 2
    a = 0.66 * e
    return rip_layer(a, 21, 185 * k, tears=4, cy=H * 0.40, grit=1.25, wscale=1.5, lscale=1.0, sp_scale=0.24, theta_deg=70,
                     edge_t=0.7, inside=0.3, base_grit=0.4, edge_grit=0.9, gamma=0.82, core_boost=0.15)
