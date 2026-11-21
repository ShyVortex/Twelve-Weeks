"""Offline layout preview of the redesigned CHOOSE YOUR SIDE page (choose_widgets.py on to1/clan-side) through widget_preview: nothing focused (all 8 framed),
each camp zoomed to fill the screen, and a frame in the middle of the name move; the camera / names / alphas of tools/ext/choose.c ch_tick evaluated.
  python choose_preview.py <extracted widget dir> <out dir> [t seconds]"""
import copy, json, math, os, re, sys
import widget_preview as wp
import clan_widgets as cw
import choose_widgets as chw

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
wp.STREAMING["streaming/t2r/choose/"] = os.path.join(ROOT, "re", "choose-1115", "tex")
wp.STREAMING["streaming/photo-mode/logos/"] = os.environ.get("T2R_LOGOS", "../t2r-wt/choose-out/logos")   # extracted read-only from core.psarc for previews, never committed
wp.STREAMING["streaming/t2r/load/"] = os.path.join(ROOT, "tools", "features", "data")
wp.STREAMING["streaming/t2r/clanend/"] = os.path.join(ROOT, "re", "clan-end", "tex")
HDR = open(os.path.join(ROOT, "tools", "ext", "choose_data.h")).read()
DEPTH = [float(x) for x in re.search(r"CH_DEPTH\[5\] = \{([^}]*)\}", HDR).group(1).replace("f", "").split(",")]
SRC = open(os.path.join(ROOT, "tools", "ext", "choose.c")).read()
def const(name):
    return float(re.search(r"#define %s ([\d.]+)f?" % name, SRC).group(1))


ZOOM, GY = const("CH_ZOOM"), const("CH_GY")
TAB_Y, TAB_K, BIG_X, BIG_Y = const("CH_TAB_Y"), const("CH_TAB_K"), const("CH_BIG_X"), const("CH_BIG_Y")
LOGO_CX = [1320.0, 2520.0]
LOGO_UP, LOGO_DOWN = const("CH_LOGO_UP"), const("CH_LOGO_DOWN")
FPX = 3200.0
DESC = {0: cw.WLF_DESC, 1: cw.SER_DESC}


def state(page, focus=-1, zt=0.0, pan=-1.0, nw=None, desc_a=None, t=3.0, logo=None):
    """the page as tools/ext/choose.c ch_tick sets it: zt = zoom progress 0..1, pan = -1 (WLF half) .. 1 (Seraphite half), nw = the two names' progress to the big title,
    desc_a = the description / warning alpha (default: 1 when a camp is focused and the name has arrived)"""
    p = copy.deepcopy(page)
    by = {i["name"]: i for i in p["items"]}
    for n in ("intro", "end", "bgDark"):
        by[n]["visible"] = 0
    by["side"]["visible"] = 1; by["side"]["color.a"] = 255
    for n in ("glowW", "glowS", "sideTitle", "sideTitleLine", "sideDivider", "frameBgW", "frameW", "figW", "frameBgS", "frameS", "figS", "sideName",
              "sideDesc", "sideWarn", "sideHint", "sideHintPad", "sideSelectIcon", "sideSelectText", "sideBrand"):
        by[n]["visible"] = 0
    for n in ("chArt", "chUi"):
        by[n]["visible"] = 1
    nw = nw if nw is not None else [1.0 if focus == 0 else 0.0, 1.0 if focus == 1 else 0.0]
    DOLLY, TRUCK = const("CH_DOLLY"), const("CH_TRUCK")
    X = TRUCK * pan * zt + 0.10 * math.sin(t * 0.23) + 0.04 * math.sin(t * 0.61)
    A = DOLLY * zt + 0.10 * math.sin(t * 0.17)
    Y = 0.035 * math.sin(t * 0.19)
    Z = 1.0 + zt * (ZOOM - 1.0)
    Gx, Gy = 1920.0 + 1920.0 * pan, GY
    sg, tx, ty = [], [], []
    for i in range(5):
        dd = max(DEPTH[i] - A, 0.6)
        sg.append(DEPTH[i] / dd); tx.append(-FPX * X / dd); ty.append(FPX * Y / dd)
    for i in range(5):
        S = Z * sg[i] / sg[1]
        px, py = 1920.0 + (tx[i] - tx[1]) / sg[1], 1080.0 + (ty[i] - ty[1]) / sg[1]
        px, py = Gx + Z * (px - Gx), Gy + Z * (py - Gy)
        lo, hi = 3840.0 - 2560.0 * S, 2560.0 * S
        if lo > hi: lo = hi = 0.5 * (lo + hi)
        px = min(max(px, lo), hi)
        vlo, vhi = 2160.0 - 1080.0 * S, 1080.0 * S
        if vlo > vhi: vlo = vhi = 0.5 * (vlo + vhi)
        py = min(max(py, vlo), vhi)
        it = by["chL%d" % i]
        it["rectSizeDelta.width"] = 5120.0 * S; it["rectSizeDelta.height"] = 2160.0 * S
        it["pivotAs.x"] = px; it["pivotAs.y"] = py
    by["chDimW"]["color.a"] = 0; by["chDimS"]["color.a"] = 0
    for k, nm in enumerate(("chNameW", "chNameS")):
        q = nw[k]
        it = by[nm]
        sc = TAB_K + (1.0 - TAB_K) * q
        it["pivotAs.x"] = LOGO_CX[k] + (BIG_X - LOGO_CX[k]) * q; it["pivotAs.y"] = TAB_Y + (BIG_Y - TAB_Y) * q
        it["pointSize"] = 100 * sc; it["rectSizeDelta.width"] = 1800 * sc; it["rectSizeDelta.height"] = 150 * sc
        it["tint.start"] = it["tint.end"] = 0xFF9CC4E8 if k == 0 else 0xFFE8905A
        both = 0.02 < nw[0] < 0.98 and 0.02 < nw[1] < 0.98
        it["color.a"] = int(255 * (abs(2 * q - 1) if both else 1.0))
    by["chNameW"]["text"] = "WLF"; by["chNameS"]["text"] = "SERAPHITES"
    da = (1.0 if focus >= 0 else 0.0) if desc_a is None else desc_a
    by["chDesc"]["text"] = DESC[focus if focus >= 0 else 0]; by["chWarn"]["text"] = cw.WARNING
    by["chDesc"]["color.a"] = int(255 * da); by["chWarn"]["color.a"] = int(255 * da)
    by["chTitleLogo"]["color.a"] = int(chw.TW_A * (1.0 - da) * (1.0 if focus < 0 else 0.0))
    lg = logo if logo is not None else [1.0 if focus < 0 else (LOGO_UP if focus == 0 else LOGO_DOWN), 1.0 if focus < 0 else (LOGO_UP if focus == 1 else LOGO_DOWN)]
    for k, nm in enumerate(("chLogoW", "chLogoS")):
        it = by[nm]
        it["rectSizeDelta.width"] *= lg[k]; it["rectSizeDelta.height"] *= lg[k]
        it["color.a"] = 153 if (focus >= 0 and focus != k) else 255
    by["chVig"]["color.a"] = 255
    by["chGrain"]["visible"] = 0
    return p


if __name__ == "__main__":
    wdir, out = sys.argv[1], sys.argv[2]
    t = float(sys.argv[3]) if len(sys.argv) > 3 else 3.0
    os.makedirs(out, exist_ok=True)
    main = json.load(open(os.path.join(wdir, "to1", "main-menu.widget.json"), encoding="utf-8"))
    page = cw.build_side_page(main)
    for name, kw in (("none", dict(focus=-1)), ("wlf", dict(focus=0, zt=1.0, pan=-1.0)), ("ser", dict(focus=1, zt=1.0, pan=1.0)),
                     ("textmove", dict(focus=0, zt=1.0, pan=-1.0, nw=[0.5, 0.0], desc_a=0.0, logo=[1.17, 0.86])), ("midpan", dict(focus=1, zt=1.0, pan=0.0, nw=[0.5, 0.5], desc_a=0.0, logo=[1.0, 1.0]))):
        f = os.path.join(out, "choose-%s.png" % name)
        wp.render(state(page, t=t, **kw), f, scale=0.5)
        print(f)
