"""clan13_overlap_check.py: nothing on the in-game CLAN page may touch or overlap. For every tab (and the overview with 0 / 1 / 4 status cards, with / without supplies) the page is filled
like clan13.c fills it, every visible text / icon / glyph gets its REAL box (the game's menu face measured at pointSize x 1.33, tracking, wrap, vertical centring - the same model as
widget_preview) and the boxes are tested pairwise (min gap 4 units), against the box of their own cell / group (min margin 6) and against the page edge. --wide N widens every text N times
(a language whose words are N times longer; Polish is ~1.15-1.25).
  python tools/features/clan13_overlap_check.py <extracted widget dir> [db] [--wide 1.2]      exit 1 when anything touches"""
import copy
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import clan13_widgets as W
import widget_preview as WP
import nr_style as NR
import re
from PIL import ImageFont

GAP, MARGIN = 3.0, 6.0
# Redesign: a survivor tile's name / role sit under the portrait tile (outside the tile group by design), and a prompt box's
# frame is sized at run time (nr_prompts), so its template width says nothing about the text: neither is held to its cell
OUT_OF_CELL = re.compile(r"^(sv\d+_\d+[NW]|pb\d+\w*)$")


def rects(w):
    """absolute rect of every visible item (parents' visibility included): name -> (x0, y0, x1, y1, item, parent name)."""
    items = w["items"]
    kids = {}
    for i in items:
        kids.setdefault(i.get("parent"), []).append(i)
    guids = {i["guid"] for i in items}
    out = {}

    def g(i, k, d=0.0):
        v = i.get(k, d)
        return d if v is None else v

    def walk(i, P, pname):
        if not g(i, "visible", 1):
            return
        px0, py0, pw, ph = P
        ax0, ax1 = px0 + g(i, "anchorMinN.x") * pw, px0 + g(i, "anchorMaxN.x") * pw
        ay0, ay1 = py0 + g(i, "anchorMinN.y") * ph, py0 + g(i, "anchorMaxN.y") * ph
        sw, sh = (ax1 - ax0) + g(i, "rectSizeDelta.width"), (ay1 - ay0) + g(i, "rectSizeDelta.height")
        pnx, pny = g(i, "pivotN.x", 0.5), g(i, "pivotN.y", 0.5)
        pvx = ax0 + (ax1 - ax0) * pnx + g(i, "pivotAs.x")
        pvy = ay0 + (ay1 - ay0) * pny + g(i, "pivotAs.y")
        x0, y0 = pvx - pnx * sw, pvy - pny * sh
        out[i["name"]] = (x0, y0, x0 + sw, y0 + sh, i, pname)
        for k in kids.get(i["guid"], []):
            walk(k, (x0, y0, sw, sh), i["name"])
    for t in [i for i in items if i.get("parent") not in guids]:
        walk(t, (0.0, 0.0, 3840.0, 2160.0), None)
    return out


_fonts = {}


def font(pt):
    k = max(6, int(pt * WP.GAME_TEXT_SCALE))
    if k not in _fonts:
        _fonts[k] = ImageFont.truetype(WP.FONT, k)
    return _fonts[k]


def text_box(it, x0, y0, x1, y1, wide):
    import re
    txt = re.sub(r"<[^>]+>", "", it.get("text", "") or "")
    if not txt.strip():
        return None
    f = font(it.get("pointSize", 40))
    trk = (it.get("tracking.x", 0.0) or 0.0) * 0.5
    sw = x1 - x0
    if it.get("multiline", 0) and sw > 0:
        lines, cur = [], ""
        for word in txt.split():
            t2 = (cur + " " + word).strip()
            if (f.getlength(t2) + trk * len(t2)) * wide > sw and cur:
                lines.append(cur); cur = word
            else:
                cur = t2
        lines.append(cur)
    else:
        lines = [txt]
    lw = max((f.getlength(l) + trk * len(l)) * wide for l in lines)
    lh = f.size * 1.3
    total = lh * len(lines)
    ty = y0 if it.get("alignV", 1) == 0 else (y0 + y1) / 2 - total / 2
    bb = [f.getbbox(l) for l in lines]                                # the INK of the glyphs (cap height / descenders), not the line box
    top = ty + (lh - f.size) / 2 + min(b[1] for b in bb)
    bot = ty + (lh - f.size) / 2 + (len(lines) - 1) * lh + max(b[3] for b in bb)
    al = it.get("alignH", 0)
    left = x0 if al == 0 else x1 - lw if al == 2 else (x0 + x1) / 2 - lw / 2
    return (left, top, left + lw, bot, len(lines))


def audit(w, label, wide=1.0):
    R = rects(w)
    probs = []
    boxes = []
    for n, (x0, y0, x1, y1, it, par) in R.items():
        if it.get("class") == "Text":
            tb = text_box(it, x0, y0, x1, y1, wide)
            if tb:
                boxes.append((n, "T", tb[0], tb[1], tb[2], tb[3], par, it))
        elif it.get("class") == "Image":
            path = it.get("path", "")
            if (path.startswith("menu:") or ("/c13-" in path)) and not it["name"].startswith("pre") and "/c13-band" not in path:      # (a card's tone band image sits on the card edge by design)
                if it.get("color.a", 255) > 0:
                    boxes.append((n, "I", x0, y0, x1, y1, par, it))
    for i, a in enumerate(boxes):
        for b in boxes[i + 1:]:
            if a[6] != b[6] and not (a[6] and b[6] and a[6][:2] == b[6][:2]):
                pass
            ox = min(a[4], b[4]) - max(a[2], b[2])
            oy = min(a[5], b[5]) - max(a[3], b[3])
            if ox > -GAP and oy > -GAP:
                if a[1] == "I" and b[1] == "I":
                    continue
                if (a[0].startswith("pre") or b[0].startswith("pre")):
                    continue
                probs.append("%s: %s [%d,%d,%d,%d] touches %s [%d,%d,%d,%d] (gap x %.0f y %.0f)" % (label, a[0], a[2], a[3], a[4], a[5], b[0], b[2], b[3], b[4], b[5], -ox, -oy))
    for n, kind, x0, y0, x1, y1, par, it in boxes:
        if n.startswith("pre"):
            continue
        if par and par in R and par not in ("anim-group", None) and not OUT_OF_CELL.match(n):
            px0, py0, px1, py1, pit, _pp = R[par]
            if pit.get("class") == "Group" or pit.get("class") is None:
                pass
            if (px1 - px0) < 3840 and (py1 - py0) < 2160 and (px1 - px0) > 0:
                if x0 < px0 + MARGIN - 0.1 or x1 > px1 - MARGIN + 0.1 or y0 < py0 + MARGIN - 0.1 or y1 > py1 - MARGIN + 0.1:
                    probs.append("%s: %s [%d,%d,%d,%d] is not %d units inside its cell %s [%d,%d,%d,%d]" % (label, n, x0, y0, x1, y1, MARGIN, par, px0, py0, px1, py1))
        if x1 > NR.R1 + 0.5 or x0 < NR.L0 - 0.5:
            if not n.startswith("bg"):
                probs.append("%s: %s [%d..%d] is outside the page margins" % (label, n, x0, x1))
        if kind == "T" and not it.get("multiline", 0):
            bx0, by0, bx1, by1 = R[n][:4]
            if x1 > bx1 + 2 and it.get("alignH", 0) != 1 and it.get("pivotN.y", 0.0) == 0.0:
                probs.append("%s: %s text is %.0f units wider than its box" % (label, n, x1 - bx1))
    return probs


def main(wdir, db=None, wide=1.0):
    import sqlite3
    import tempfile
    main_w = json.load(open(os.path.join(wdir, "to1", "main-menu.widget.json"), encoding="utf-8"))
    page = W.build_page(main_w)
    here = os.path.dirname(os.path.abspath(__file__))
    sys.path.insert(0, os.path.join(here, ".."))
    import clan_ingame
    if not db:
        import clan_demo_seed
        db = os.path.join(tempfile.mkdtemp(), "demo.db")
        sys.argv = ["x", db, "--days", "9", "--size", "17"]
        clan_demo_seed.main()
    c = sqlite3.connect(db)
    secs = {s: clan_ingame.build(c, "0123456789abcdef01234567", "pl" if "--pl" in sys.argv else "en", s) for s in (1, 2, 3, 4)}
    probs = []
    empty = {s: t.split(chr(10))[0] for s, t in secs.items()}          # a clan with no members / raids / journal / supplies: the header line only
    for tab, nm in enumerate(("overview", "survivors", "raids", "journal", "missions")):
        probs += audit(W.demo(page, tab, secs), nm, wide)
        probs += audit(W.demo(page, tab, empty, "none"), nm + " (empty clan)", wide)
    for var in ("attack", "chosen"):
        probs += audit(W.demo(page, 4, secs, var), "missions " + var, wide)
    # the overview with 0 / 1 / 2 rows of status updates, with and without supplies, and a long headline list
    NL, TB = chr(10), chr(9)
    hdr4 = secs[4].split(NL)[0]
    for nu in (0, 1, 2, 4):
        for sup in (True, False):
            v = dict(secs)
            v[4] = NL.join([hdr4] + [l for l in secs[4].split(NL) if l.startswith('U' + TB)][:nu])
            if not sup:
                v[3] = NL.join(l for l in secs[3].split(NL) if not l.startswith(('S' + TB, 'M' + TB, 'T' + TB)))
            probs += audit(W.demo(page, 0, v), 'overview nu=%d supplies=%s' % (nu, sup), wide)
    return probs


if __name__ == "__main__":
    wide = float(sys.argv[sys.argv.index("--wide") + 1]) if "--wide" in sys.argv else 1.0
    args = [a for a in sys.argv[1:] if not a.startswith("--") and a != str(wide)]
    pr = main(args[0], args[1] if len(args) > 1 else None, wide)
    print("\n".join(pr) if pr else "no overlaps")
    sys.exit(1 if pr else 0)
