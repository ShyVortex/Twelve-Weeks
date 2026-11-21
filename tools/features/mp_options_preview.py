"""OPTIONS > MULTIPLAYER preview (EN + PL): the to1/options-menu-multiplayer page after names_widgets.add_options_hint, rows in the
widget order with their real labels, the REGION PREFERENCE / INPUT PREFERENCE mockup rows greyed out with the lock.
Rough offline render with PIL, never launches the game:

  python mp_options_preview.py <out dir> [--pak <spec gui2-widgets.pak>]

Layout from the widget data (list / contents / row heights, the selector's label / value / lock / arrow slots); the menu tint colours
(t2-menu-normal / -focused / -disabled / -focused-disabled) are approximations, not read from the game. Texts: the built tables
re/modfs_feat/text2/{eng,pol}.common when present, else dc_data_patches.patch_text_ciphers' defaults + tools/loc/pl.
Outputs mp-options[-pl].png (focus on REGION PREFERENCE = focused_disabled) and mp-options-focus-bow[-pl].png (both mock rows plain
disabled), 1920 x 1080."""
import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile

from PIL import Image, ImageDraw, ImageFont, ImageFilter

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)
import names_widgets  # noqa: E402
import widget_preview  # noqa: E402
from widgets_patch import GUI2, SIDBASE  # noqa: E402

GUI2 = os.environ.get("T2R_GUI2", GUI2)              # gui2.exe / sidbase.bin live in the main checkout's untracked tools/
SIDBASE = os.environ.get("T2R_SIDBASE", SIDBASE)
MAIN = os.environ.get("T2R_MAIN_ROOT", ".")

# approximations of the game's menu palette entries
COL = {"normal": (189, 189, 189), "focused": (255, 255, 255), "disabled": (92, 92, 92), "focused_disabled": (140, 140, 140),
       "header_prev": (140, 140, 140), "line": (90, 90, 90)}
# shown values (the ext's / winmm's sources): the spec rows' defaults from t2r-settings.txt, our rows OFF, the mockups ANY
VALUES = {"to1-reticle-mode": "MENU_ON", "to1-menu-fps-cap": "MENU_ON", "to1-radar-mode": "MENU_ON", "to1-bow-arc": "MENU_ON",
          "to1-mp-ui-off": "MENU_OFF", "to1-mp-radar-off": "MENU_OFF", "to1-mp-lives-off": "MENU_OFF", "to1-mp-supplies-off": "MENU_OFF",
          "to1-region-pref": "TO1_PREF_ANY", "to1-input-pref": "TO1_PREF_ANY", "to1-p1-pref": "TO1_P1_DEFAULT"}
MOCK_SOURCES = {r[2] for r in names_widgets.MOCK_ROWS}
P1_SOURCES = {r[2] for r in names_widgets.P1_ROWS}      # PART I MAPS: a working row, greyed out only in the "locked" variant (no Part I maps installed)


def fnv64(s):
    h = 0xCBF29CE484222325
    for ch in s.encode():
        h = ((h ^ ch) * 0x100000001B3) & 0xFFFFFFFFFFFFFFFF
    return h


def texts(pl):
    """cipher name -> shown text"""
    import loc_tables
    import dc_data_patches
    import inspect
    defaults = dict(inspect.signature(dc_data_patches.patch_text_ciphers).parameters["add"].default)
    defaults.update({"MENU_ON": "ON", "MENU_OFF": "OFF", "MENU_OPTIONS": "OPTIONS", "T2RL_045A398B": "MULTIPLAYER", "TO1_RETICLE": "RETICLE",
                     "TO1_MENU_FPS_CAP": "LIMIT MENU TO 60 FPS", "TO1_MENU_RADAR": "RADAR STYLE"})
    tabs = []
    for base in (ROOT, MAIN):
        p = os.path.join(base, "re", "modfs_feat", "text2", ("pol" if pl else "eng") + ".common")
        if os.path.exists(p):
            tabs.append(loc_tables.load(p))
            break
    tr = loc_tables._translations("pl")[0] if pl else {}

    def get(name):
        for t in tabs:
            v = t.get(fnv64(name))
            if v:
                return v.decode("utf-8", "replace")
        en = defaults.get(name, name)
        return tr.get(en, en)
    return get


def page_rows(pak):
    wd = tempfile.mkdtemp(prefix="mpopt_")
    try:
        subprocess.run([GUI2, "extract", pak, wd, "--sidbase", SIDBASE], check=True, capture_output=True)
        names_widgets.add_options_hint(wd, None)
        w = json.load(open(os.path.join(wd, "to1", "options-menu-multiplayer.widget.json"), encoding="utf-8"))
    finally:
        shutil.rmtree(wd, ignore_errors=True)
    by = {i["name"]: i for i in w["items"]}
    c = by["contents"]
    rows = [i for i in w["items"] if i.get("parent") == c["guid"]]
    return by["list"], c, rows


def lock_icon(d, cx, cy, s, col):
    """the padlock (the row's lockcon slot), drawn: shackle arc + body"""
    bw, bh = 18 * s, 14 * s
    d.arc([cx - 6 * s, cy - 13 * s, cx + 6 * s, cy - 1 * s], 180, 360, fill=col, width=max(2, int(3 * s)))
    d.line([cx - 6 * s, cy - 7 * s, cx - 6 * s, cy - 1 * s], fill=col, width=max(2, int(3 * s)))
    d.line([cx + 6 * s, cy - 7 * s, cx + 6 * s, cy - 1 * s], fill=col, width=max(2, int(3 * s)))
    d.rounded_rectangle([cx - bw / 2, cy - 2 * s, cx + bw / 2, cy - 2 * s + bh], radius=2 * s, fill=col)


def arrow(d, cx, cy, s, col, left):
    w, h = 9 * s, 15 * s
    pts = [(cx + w / 2, cy - h / 2), (cx - w / 2, cy), (cx + w / 2, cy + h / 2)] if left else [(cx - w / 2, cy - h / 2), (cx + w / 2, cy), (cx - w / 2, cy + h / 2)]
    d.line(pts, fill=col, width=max(2, int(3 * s)), joint="curve")


def render(pak, out, pl=False, focus="selectorRegionPref", scale=0.5, p1="default"):
    """p1 = the PART I MAPS row: "default" (DEFAULT, enabled), "always" (ALWAYS, enabled), "locked" (DEFAULT, greyed out: no Part I maps installed)"""
    get = texts(pl)
    lst, c, rows = page_rows(pak)
    W, H = int(3840 * scale), int(2160 * scale)
    img = Image.new("RGB", (W, H), (34, 36, 38))
    # backdrop: a dim blurred scene stand-in + the page's left menu shade
    bg = Image.new("RGB", (W, H), (0, 0, 0))
    bd = ImageDraw.Draw(bg)
    for k in range(12):
        bd.ellipse([W * (0.45 + 0.04 * k), H * (0.1 + 0.05 * (k % 5)), W * (0.75 + 0.03 * k), H * (0.6 + 0.04 * (k % 4))],
                   fill=(52 + 4 * (k % 3), 58 + 3 * (k % 4), 54 + 2 * k))
    img = Image.blend(img, bg.filter(ImageFilter.GaussianBlur(60 * scale)), 0.6)
    shade = Image.new("L", (W, H), 0)
    sd = ImageDraw.Draw(shade)
    for x in range(int(2170 * scale)):
        sd.line([(x, 0), (x, H)], fill=int(200 * max(0.0, 1.0 - x / (2170 * scale)) ** 0.8))
    img = Image.composite(Image.new("RGB", (W, H), (0, 0, 0)), img, shade)
    d = ImageDraw.Draw(img)

    def font(pt):
        return ImageFont.truetype(widget_preview.FONT, max(6, int(pt * scale * widget_preview.GAME_TEXT_SCALE)))
    # title group (y 162): OPTIONS | MULTIPLAYER, the two lines; bottom line (y 2160 - 233)
    ty = 162 * scale
    x0 = 143 * scale
    d.text((x0, ty), get("MENU_OPTIONS"), font=font(50), fill=COL["header_prev"], anchor="lm")
    d.line([(x0 + 336 * scale, ty - 25 * scale), (x0 + 336 * scale, ty + 25 * scale)], fill=COL["line"], width=max(1, int(2 * scale)))
    title = get("T2RL_045A398B")
    d.text((x0 + 402 * scale, ty), title, font=font(50), fill=(230, 230, 230), anchor="lm")
    tx1 = x0 + 402 * scale + d.textlength(title, font=font(50)) + 40 * scale
    d.line([(max(x0 + 806 * scale, tx1), ty), (W - 143 * scale, ty)], fill=COL["line"], width=max(1, int(2 * scale)))
    d.line([(140 * scale, H - 233 * scale), (W - 140 * scale, H - 233 * scale)], fill=COL["line"], width=max(1, int(2 * scale)))
    # the list: x = centre - 1777, y = centre - 830; contents at +111, rows flow down with the contents' spacing
    lx, ly = (1920 - 1777) * scale, (1080 - 830) * scale
    cw = (float(lst["rectSizeDelta.width"]) + float(c["rectSizeDelta.width"])) * scale
    y = ly + float(c["pivotAs.y"]) * scale
    sp = float(c["flowSpacing"]) * scale
    s = scale * 2
    for r in rows:
        h = float(r["rectSizeDelta.height"]) * scale
        ds = (r.get("tags") or {}).get("dataSource")
        disabled = ds in MOCK_SOURCES or (ds in P1_SOURCES and p1 == "locked")
        focused = r["name"] == focus
        state = ("focused_disabled" if focused else "disabled") if disabled else ("focused" if focused else "normal")
        col = COL[state]
        cy = y + h / 2
        if focused:     # hover-bg: a soft bar behind the row
            bar = Image.new("RGBA", (W, H), (0, 0, 0, 0))
            ImageDraw.Draw(bar).rectangle([lx + 10 * scale, y - 3 * scale, lx + cw, y + h + 3 * scale], fill=(255, 255, 255, 28))
            img.paste(Image.alpha_composite(img.convert("RGBA"), bar).convert("RGB"))
            d = ImageDraw.Draw(img)
        indent = 60 * scale if "dependent" in r.get("source", "") else 0
        d.text((lx + 50 * scale + indent, cy), get(r["cipherId"]), font=font(41), fill=col, anchor="lm")
        if ds:
            right = lx + cw
            # value group (arrows) at the right, the lock left of it, the value text right-aligned left of the lock (show-disabled order)
            arrow(d, right - 85 * scale, cy, s, col, True)
            arrow(d, right - 25 * scale, cy, s, col, False)
            tx = right - 140 * scale
            if disabled:
                lock_icon(d, right - 152 * scale, cy, s * 0.9, col)
                tx = right - 201 * scale
            val = "TO1_P1_ALWAYS" if ds in P1_SOURCES and p1 == "always" else VALUES.get(ds, "MENU_OFF")
            d.text((tx, cy), get(val), font=font(35), fill=col, anchor="rm")
        y += h + sp
    img.save(out)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("out")
    ap.add_argument("--pak", default=None)
    a = ap.parse_args()
    pak = a.pak
    if not pak:
        for base in (ROOT, MAIN):
            p = os.path.join(base, "re", "modfs", "actor97", "gui2-widgets.pak")
            if os.path.exists(p):
                pak = p
                break
    os.makedirs(a.out, exist_ok=True)
    for pl in (False, True):
        sfx = "-pl" if pl else ""
        print(render(pak, os.path.join(a.out, f"mp-options{sfx}.png"), pl, "selectorRegionPref"))
        print(render(pak, os.path.join(a.out, f"mp-options-focus-bow{sfx}.png"), pl, "selectorBowAimArc"))
        print(render(pak, os.path.join(a.out, f"mp-options-p1-always{sfx}.png"), pl, "selectorPartIMaps", p1="always"))
        print(render(pak, os.path.join(a.out, f"mp-options-p1-locked{sfx}.png"), pl, "selectorPartIMaps", p1="locked"))


if __name__ == "__main__":
    main()
