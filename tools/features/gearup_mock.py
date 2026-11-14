"""GEAR UP rework mockups: the launcher's loadout layout (release/launcher/src/loadout.js + gear.css)
drawn at game scale on one strict grid. Renders out/<state>.png at 1920x1080 (in-game widget units = x2).

Composition rules (every page, every state):
  * margins 110 px left / right; header rule at y 150 and footer rule at y 990 span the full width 110..1810 - the only full-width lines
  * column dividers run exactly header rule -> footer rule (T-joints on both, never past them, never short of them)
  * each column: 40 px gutter to a divider; its heading baseline at y 205, ONE column rule under it at y 228 spanning that column's text box exactly
  * first list row at y 250 in every column; rows on a 50 px rhythm (row box 44, gap 6); icons in a 64 x 34 box, text starts 80 px into the row
  * one type scale: title 44 / heading 22 / row 17 / body 15 / small 13 (bold caps for everything but body text), three greys + one accent
  * selection = 1 px cream frame; hover/focus = 5% white fill; equipped = accent word at the row end; never a filled grey card
  * level / variant choice = inline pills on the row (I 1 · II 3 · III 4 / LOUD 2 · QUIET 4) and, for skills, all levels' text in the details
    with only the chosen one bright (launcher) - no tiles
  * ground = the menu world, blurred and darkened, with fine grain - one layer under all GEAR UP pages, never re-faded between them
python gearup_mock.py <gamedata.json> <icons dir> <backdrop png> <out dir>"""
import json
import os
import sys

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

import ui_r2_common
import widget_preview

W, H = 1920, 1080
TEXT, DIM, FAINT = (0xE6, 0xDF, 0xCF), (0xA8, 0xA2, 0x92), (0x6F, 0x6B, 0x60)
ACCENT, BAD = (0x8E, 0xC3, 0xEA), (0xB9, 0x64, 0x5A)
LINE = (220, 220, 214, 46)       # --line2 ~ .3 alpha over the dark ground reads like the launcher's rules
M0, M1 = 110, 1810
HEAD_RULE, FOOT_RULE = 150, 990
HEAD_BASE, COL_RULE, ROW0, PITCH, ROWH = 205, 228, 250, 50, 44
GUT = 40
ROMAN = ["", "I", "II", "III"]
_F = {}


def F(px):
    if px not in _F:
        _F[px] = ImageFont.truetype(widget_preview.real_font(), px)
    return _F[px]


class Page:
    def __init__(self, backdrop, g):
        bg = Image.open(backdrop).convert("RGB").resize((W, H)).filter(ImageFilter.GaussianBlur(28))
        arr = np.asarray(bg, dtype=np.float32) * 0.22 + 6
        self.im = Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8)).convert("RGBA")
        self.im = Image.alpha_composite(self.im, g)
        self.ov = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        self.d = ImageDraw.Draw(self.ov)
        self.icons = None

    def text(self, x, y, s, px, col=TEXT, al="l", track=0.5, a=255):
        """y = baseline."""
        f = F(px)
        w = sum(f.getlength(ch) for ch in s) + track * max(0, len(s) - 1)
        if al == "r":
            x -= w
        elif al == "c":
            x -= w / 2
        asc = f.getmetrics()[0]
        cx = x
        for ch in s:
            self.d.text((cx, y - asc), ch, font=f, fill=col + (a,))
            cx += f.getlength(ch) + track
        return w

    def wrap(self, x, y, s, px, col, maxw, lh):
        f = F(px)
        line = ""
        for word in s.split():
            t = (line + " " + word).strip()
            if f.getlength(t) > maxw and line:
                self.text(x, y, line, px, col, track=0)
                y += lh
                line = word
            else:
                line = t
        if line:
            self.text(x, y, line, px, col, track=0)
            y += lh
        return y

    def hline(self, x0, x1, y, a=None):
        self.d.line((x0, y, x1, y), fill=LINE if a is None else LINE[:3] + (a,), width=1)

    def vline(self, x, y0, y1):
        self.d.line((x, y0, x, y1), fill=LINE, width=1)

    def frame(self, x0, y0, x1, y1, a=210):
        self.d.rectangle((x0, y0, x1, y1), outline=TEXT + (a,), width=1)

    def fill(self, x0, y0, x1, y1, a=13):
        self.d.rectangle((x0, y0, x1, y1), fill=(255, 255, 255, a))

    def icon(self, name, x, y, w, h, a=255):
        p = os.path.join(self.icons, (name or "none") + ".png")
        if not os.path.isfile(p):
            p = os.path.join(self.icons, "none.png")
        ic = Image.open(p).convert("RGBA")
        ic.thumbnail((w, h), Image.LANCZOS)
        if a < 255:
            ic.putalpha(ic.getchannel("A").point(lambda v: v * a // 255))
        self.ov.alpha_composite(ic, (int(x + (w - ic.width) / 2), int(y + (h - ic.height) / 2)))

    def chrome(self, title, right=None, right_col=TEXT, hints=("SELECT", "BACK")):
        self.text(M0, 112, title, 44, TEXT, track=2)
        if right:
            self.text(M1, 112, right, 22, right_col, al="r", track=1)
        self.hline(M0, M1, HEAD_RULE)
        self.hline(M0, M1, FOOT_RULE)
        x = M1
        for h in reversed(hints):
            w = F(15).getlength(h) + 6 * len(h) * 0
            x -= self.text(x, 1030, h, 15, DIM, al="r", track=1.5) + 0
            self.d.rounded_rectangle((x - 46, 1013, x - 12, 1035), 3, outline=DIM + (200,), width=1)
            x -= 74

    def cols(self, xs):
        for x in xs:
            self.vline(x, HEAD_RULE, FOOT_RULE)

    def heading(self, x0, x1, s, right=None, right_col=TEXT):
        self.text(x0, HEAD_BASE, s, 22, TEXT, track=1)
        if right:
            self.text(x1, HEAD_BASE, right, 22, right_col, al="r", track=1)
        self.hline(x0, x1, COL_RULE)

    def row(self, x0, x1, k, name, icon=None, end=None, end_col=DIM, sel=False, hov=False, dim=False, pills=None, y=None):
        y0 = y if y is not None else ROW0 + k * PITCH
        if hov:
            self.fill(x0, y0, x1, y0 + ROWH)
        if sel:
            self.frame(x0, y0, x1, y0 + ROWH)
        a = 120 if dim else 255
        if icon is not False:
            self.icon(icon, x0 + 8, y0 + 5, 64, 34, a)
        tx = x0 + (80 if icon is not False else 14)
        col = TEXT if (sel or hov) else DIM
        self.text(tx, y0 + 29, name, 17, col if not dim else FAINT, track=1)
        ex = x1 - 12
        if pills:
            for lbl, cost, on, ok in reversed(pills):
                s = f"{lbl} {cost}"
                pw = F(13).getlength(lbl) + F(13).getlength(" " + str(cost)) + 18
                bx0 = ex - pw
                self.d.rectangle((bx0, y0 + 11, ex, y0 + 33), outline=(TEXT if on else FAINT) + ((230 if on else 140),), width=1,
                                 fill=(255, 255, 255, 20) if on else None)
                lw = self.text(bx0 + 9, y0 + 27, lbl, 13, TEXT if on else (DIM if ok else FAINT), track=0.5)
                self.text(bx0 + 9 + lw + 5, y0 + 27, str(cost), 13, ACCENT if on else FAINT, track=0)
                ex = bx0 - 6
        elif end:
            self.text(ex, y0 + 28, end, 13, end_col, al="r", track=1.5)

    def stats(self, x, y, vals, w):
        for k, n in enumerate(("RATE OF FIRE", "RELOAD SPEED", "DAMAGE", "ACCURACY")):
            self.text(x, y, n, 13, DIM, track=1.5)
            sw = (w - 9 * 4) / 10
            for s in range(10):
                sx = x + s * (sw + 4)
                self.d.rectangle((sx, y + 10, sx + sw, y + 16), fill=(TEXT + (225,)) if s < vals[k] else (255, 255, 255, 30))
            y += 46
        return y

    def save(self, p):
        Image.alpha_composite(self.im, self.ov).convert("RGB").save(p)


def lo_rows(G, lo):
    """(icon, name, cost, empty) for the 7 slot rows, launcher order: SMALL, LARGE | skills 1-4 | PURCHASABLE."""
    def w(slot, sel, none):
        if not sel:
            return (None, none, "", True)
        wp = next(x for x in G["weapons"][slot] if x["id"] == sel["id"])
        q = sel.get("supp") and wp.get("supIcon")
        return (wp["supIcon"] if q else wp["icon"], ("SUPPRESSED " if q else "") + wp["name"], str(wp["lp"] + (wp["supp"] if q else 0)) if wp["lp"] or q else "FREE", False)
    out = [w("small", lo["small"], "NO SMALL FIREARM"), w("large", lo["large"], "NO LARGE FIREARM")]
    for s in lo["skills"]:
        if s:
            sk = G["skills"][s["id"]]
            out.append(("skill-" + sk["icon"], f'{sk["name"]} {ROMAN[s["lv"]]}', str(sk["cost"][s["lv"] - 1]), False))
        else:
            out.append((None, "NOTHING", "", True))
    out.append(w("purch", lo["purch"], "NO PURCHASABLE"))
    return out


def slot_column(p, G, lo, x0, x1, sel=None, focus=None, dimmed=False):
    """The 7 slot rows; a column line (not a divider: inside the column's box only) after the two guns and before the purchasable."""
    rows = lo_rows(G, lo)
    y = ROW0
    for i, (ic, nm, co, empty) in enumerate(rows):
        if i in (2, 6):
            p.hline(x0, x1, y + 2)
            y += 10
        p.row(x0, x1, 0, nm, ic, end=(co + " LP" if co not in ("", "FREE") else co), sel=i == sel, hov=i == focus,
              dim=(dimmed and i != sel) or empty, y=y)
        y += PITCH


def main(gd, icons, backdrop, out):
    G = json.load(open(gd, encoding="utf-8"))
    os.makedirs(out, exist_ok=True)
    g = ui_r2_common.grain(W, H)
    lo = {"small": {"id": "pistol-revolver", "supp": 0}, "large": {"id": "bow", "supp": 0}, "purch": {"id": "crossbow", "supp": 0},
          "skills": [None, {"id": 6, "lv": 1}, {"id": 2, "lv": 1}, None]}
    for k in ("small", "large", "purch"):     # ids from the data (names differ per build)
        ids = [x["id"] for x in G["weapons"][k]]
        want = {"small": "revolver", "large": "bow", "purch": "crossbow"}[k]
        lo[k]["id"] = next((i for i in ids if want in i), ids[0])

    # ---------------------------------------------------------------- 1 list page: loadouts | its gear | its description (same 3-column grid)
    p = Page(backdrop, g); p.icons = icons
    p.chrome("GEAR UP", "THE LAST OF US  TWELVE WEEKS", DIM)
    a0, a1, b0, b1, d0, d1 = M0, 560, 640, 1180, 1260, M1
    p.cols([a1 + GUT, b1 + GUT])
    p.heading(a0, a1, "LOADOUTS")
    names = [f"CUSTOM LOADOUT {i + 1}" for i in range(6)] + [c["name"] for c in G["classes"]]
    y = ROW0
    for i, n in enumerate(names):
        if i == 6:
            p.hline(a0, a1, y + 2)
            y += 10
        p.row(a0, a1, 0, n, False, end="EQUIPPED" if i == 7 else "", end_col=ACCENT, sel=i == 7, hov=i == 7, y=y)
        y += 44 if i >= 6 else PITCH
    cl = G["classes"][1]
    clo = {"small": cl["slots"]["small"], "large": cl["slots"]["large"], "purch": cl["slots"]["purch"],
           "skills": [cl["skills"][i] if i < len(cl["skills"]) else None for i in range(4)]}
    p.heading(b0, b1, "GEAR", f'{cl["lp"]}/13 LP', ACCENT)
    slot_column(p, G, clo, b0, b1)
    p.heading(d0, d1, cl["name"])
    p.wrap(d0, ROW0 + 28, cl["desc"], 15, DIM, d1 - d0, 24)
    p.save(os.path.join(out, "1-list.png"))

    # ---------------------------------------------------------------- 2 edit page: slots | options of the focused slot (dim) | details
    def three(title, sel_slot, mid_focus, mid_active, det, mid_rows, mid_head, lp="7/13 LOADOUT POINTS"):
        p = Page(backdrop, g); p.icons = icons
        p.chrome(title, lp, ACCENT, hints=("SELECT", "RESET LOADOUT", "BACK"))
        a0, a1 = M0, 560
        b0, b1 = a1 + 2 * GUT, 1180
        d0, d1 = b1 + 2 * GUT, M1
        p.cols([a1 + GUT, b1 + GUT])
        p.heading(a0, a1, "EQUIPPED")
        slot_column(p, G, lo, a0, a1, sel=sel_slot, focus=None if mid_active else sel_slot, dimmed=mid_active)
        p.heading(b0, b1, mid_head)
        for k in range(1, len(mid_rows)):        # a rule between every two option rows, centred in the 6 px row gap, the column's width
            p.hline(b0, b1, ROW0 + k * PITCH - 3, 30)
        for k, r in enumerate(mid_rows):
            p.row(b0, b1, k, r["name"], r["icon"], end=r.get("end"), end_col=r.get("end_col", DIM), pills=r.get("pills"),
                  sel=mid_active and k == mid_focus, hov=mid_active and k == mid_focus, dim=not mid_active and not r.get("cur"))
        det(p, d0, d1)
        return p

    def gun_rows(slot, cur_id, cur_q=0, none=None):
        rows = [{"name": none, "icon": None, "end": "FREE"}] if none else []
        for wp in G["weapons"][slot]:
            cur = wp["id"] == cur_id
            if wp.get("supIcon"):
                pills = [("LOUD", wp["lp"] or "FREE", cur and not cur_q, True), ("QUIET", wp["lp"] + wp["supp"], cur and cur_q, True)]
                rows.append({"name": wp["name"], "icon": wp["supIcon"] if cur and cur_q else wp["icon"], "pills": pills, "cur": cur})
            else:
                rows.append({"name": wp["name"], "icon": wp["icon"], "end": "EQUIPPED" if cur else (f'{wp["lp"]} LP' if wp["lp"] else "FREE"),
                             "end_col": ACCENT if cur else DIM, "cur": cur})
        return rows

    def gun_det(wp, q, cost_word):
        def f(p, x0, x1):
            p.heading(x0, x1, "DETAILS")
            p.text(x0, ROW0 + 30, ("SUPPRESSED " if q else "") + wp["name"], 22, TEXT, track=1)
            p.text(x1, ROW0 + 30, cost_word, 22, ACCENT, al="r", track=1)
            p.icon(wp["supIcon"] if q else wp["icon"], x0, ROW0 + 52, 300, 90)
            y = p.wrap(x0, ROW0 + 178, wp["desc"], 15, DIM, x1 - x0, 24)
            if wp.get("supIcon"):
                y += 6
                p.text(x0, y, "LOUD", 15, DIM if q else TEXT, track=1)
                y = p.wrap(x0 + 70, y, f"Standard. {wp['lp']} LP.", 15, DIM if q else TEXT, x1 - x0 - 70, 24)
                p.text(x0, y, "QUIET", 15, TEXT if q else DIM, track=1)
                y = p.wrap(x0 + 70, y, f"Suppressed: shots don't show you on the enemy radar. {wp['lp'] + wp['supp']} LP.", 15,
                           TEXT if q else DIM, x1 - x0 - 70, 24)
            p.stats(x0, y + 22, wp["stats"], min(460, x1 - x0))
        return f

    def skill_det(s, lv, chosen=None):
        def f(p, x0, x1):
            p.heading(x0, x1, "DETAILS")
            p.text(x0, ROW0 + 30, s["name"], 22, TEXT, track=1)
            p.text(x1, ROW0 + 30, f'{ROMAN[lv]}  ·  {s["cost"][lv - 1]} LP', 22, ACCENT, al="r", track=1)
            p.icon("skill-" + s["icon"], x0, ROW0 + 52, 90, 90)
            y = ROW0 + 182
            for k, dsc in enumerate(s["desc"]):
                on = k + 1 == lv
                col = TEXT if on else FAINT
                if on:
                    p.d.rectangle((x0 - 14, y - 22, x0 - 11, y - 22 + 24 * max(1, (len(dsc) // 52) + 1)), fill=ACCENT + (255,))
                p.text(x0, y, ROMAN[k + 1], 15, col, track=1)
                p.text(x1, y, f'{s["cost"][k]} LP', 15, ACCENT if on else FAINT, al="r", track=1)
                y = p.wrap(x0 + 44, y, dsc, 15, col, x1 - x0 - 44 - 60, 24) + 12
        return f

    large = G["weapons"]["large"]
    bow = next(w for w in large if w["id"] == lo["large"]["id"])
    p = three("CUSTOM LOADOUT 1", 1, 0, False, gun_det(bow, 0, f'{bow["lp"]} LP' if bow["lp"] else "FREE"), gun_rows("large", bow["id"], none="NO LARGE FIREARM"), "LARGE FIREARM")
    p.save(os.path.join(out, "2-edit.png"))

    vr = large[0]
    p = three("CUSTOM LOADOUT 1", 1, 1, True, gun_det(vr, 1, f'{vr["lp"] + vr["supp"]} LP'), gun_rows("large", bow["id"], none="NO LARGE FIREARM"),
              "LARGE FIREARM")
    p.save(os.path.join(out, "3-pick-gun.png"))

    rv = G["skills"][2]
    used = {6}
    srows = []
    for i, s in enumerate(G["skills"]):
        if i in used:
            continue
        pills = [(ROMAN[k + 1], s["cost"][k], i == 2 and k == 1, True) for k in range(s["levels"])]
        srows.append({"name": s["name"], "icon": "skill-" + s["icon"], "pills": pills, "cur": i == 2})
    p = three("CUSTOM LOADOUT 1", 3, 2, True, skill_det(rv, 2), srows[:14], "SURVIVAL SKILL 2")
    p.save(os.path.join(out, "4-pick-skill.png"))
    return out


if __name__ == "__main__":
    print(main(*sys.argv[1:5]))
