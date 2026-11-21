"""to1/connecting: the page shown after TWELVE WEEKS is picked in the boat (title) menu, while winmm checks the network
(net-connect: CHECKING NETWORK -> CONNECTING TO SERVER -> CHECKING GAME SERVER -> COMPLETE) and then starts the MP menu level.

The original (the base client's v1.08) page: a pure black screen, "CONNECTING" 120 pt centred, a grey status line under it and a
centred 1000 x 10 px bar. The mod's own look (simplistic, its own style, not associable with the base client):

  * the dark MP menu backdrop (blur + near-black + one soft light, the same layers as the clan / vote pages), no pure black
  * title block at the left, vertically centred, the launcher's title: "THE LAST OF US" (bold) over a thin rule over
    "TWELVE WEEKS" (small, wide-tracked, dimmer)
  * bottom row like the in-match LOADING screen (matchflow_widgets.build_loading): the status text at the left, "CONNECTING"
    right aligned in the small tracked caps, a 3 px progress line along the whole bottom edge

The engine / winmm contract is kept: widget names connectingText, statusText, progress (IProgressBar, child barFull) and
barTrack stay, winmm drives progress + statusText by path (anim-group.progress / anim-group.statusText) and t2r-ext translates
connectingText (loc_static_labels, page "connecting"). Only layout / colours / extra decoration change. Widget space is
3840 x 2160, y down.

Variant "L" (default since re/loading-1105/README.md): the TWELVE WEEKS entry sequence. Pure black, the title big and centred in the
user's "The Last Of Us Rough.ttf" rendered to a texture (loading_art.py; the game's font system cannot load a new TTF from our tooling), a 28 px
white bar with a torn right edge along the bottom edge (winmm keeps driving anim-group.progress). Nothing is visible in the JSON: t2r-ext ld_tick (tools/ext/loadseq.c) fades bg to black, holds, fades
the title (group t2rLoad) in slowly, fades the bar in and fades everything out; the stinger plays with the title fade.   python connecting_widgets.py <extracted widget dir> <out png>   renders the layout (preview)."""
import copy
import json
import os
import sys

import t2guid
from clan_widgets import Builder, _templates

W, H = 3840, 2160
CREAM = 0xFFE6DFCF          # launcher --text
DIM = 0xFFA8A292            # launcher --dim
FAINT = 0xFF6F6B60          # launcher --faint
LEFT = 240                  # the in-match LOADING screen's left margin
RIGHT = 3600

PAGE = os.path.join("to1", "connecting.widget.json")

# variant L (entry sequence)


def _col(it, argb):
    it["tint.start"] = argb
    it["tint.end"] = argb


def _place(it, p):
    it.update(p)


# layout per variant: title block (x, y of THE LAST OF US, rule length, align 0 left / 2 right), light centre, the bottom
# widgets (status box, label box, bar box, as x, y, w, h)
VARIANTS = {
    # A (default): title left, vertically centred; status left / CONNECTING right on the bottom row, 3 px line under
    "A": dict(tx=LEFT, ty=830, al=0, light=(900, 1000), st=(LEFT, 1880, 1900, 90, 0), ct=(2300, 1880, RIGHT - 2300, 90, 2),
              bar=(LEFT, 1985, RIGHT - LEFT, 3), spin=(3560, 1790)),
    # B: title block low on the left, CONNECTING small above it, status under it, the line along the very bottom edge
    "B": dict(tx=LEFT, ty=1330, al=0, light=(700, 1500), st=(LEFT, 1700, 2400, 90, 0), ct=(LEFT, 1250, 1400, 70, 0),
              bar=(0, 2154, W, 6), spin=(3560, 1800)),
    # C: everything right aligned in a column on the right, a short line under the status
    "C": dict(tx=RIGHT - 2400, ty=800, al=2, light=(2900, 1000), st=(RIGHT - 2400, 1260, 2400, 90, 2),
              ct=(RIGHT - 2400, 1170, 2400, 70, 2), bar=(RIGHT - 1100, 1370, 1100, 3), spin=(3560, 1560)),
}


def _restyle_sequence(wdir, w, path):
    """Variant L: black page, big centred title group t2rLoad (hidden, t2r-ext fades it in), thin bar. Returns the widgets added."""
    items = w["items"]
    by = {i["name"]: i for i in items}
    main = json.load(open(os.path.join(wdir, "to1", "main-menu.widget.json"), encoding="utf-8"))
    t, _, _ = _templates(main)
    for c in t.values():
        for k in ("engineClass", "tags", "animationsPath"):
            c.pop(k, None)
    anim = by["anim-group"]["guid"]
    b = Builder(t)
    _col(by["bg"], 0xFF000000)
    by["bg"]["color.a"] = 0                         # t2r-ext fades it to black (0.4 s); it sets it to 1 at once when the sequence is off
    for nm in ("connectingText", "statusText"):     # winmm still writes statusText by path; nothing of it shows
        by[nm]["visible"] = 0
    # The progress display is the TITLE FILL: the title as a dim texture (20 % white) and, on top, the same title in white clipped to the real
    # load progress. The clip is the engine's own pattern (hud-progress-bar/progress-vram osVramProgress): the IProgressBar `progress` resizes its child
    # `barFull`, a Group with isMaskOrClip = 1, and the bright title is a fixed-size child of that mask (not stretched to it). The progress rect is
    # the title's ink width + FEATHER, so the fill edge (feather strip at the mask's right end) is past the last letter at 100 %. The feather strip is a
    # black alpha-ramp image at the mask's right edge: black over white = the dim level, so the edge washes from white to dim over FEATHER units.
    import loading_art as la
    tex_l, tex_t = (W - la.TITLE_W) // 2, (H - la.TITLE_H) // 2
    ink_l = tex_l + (la.TITLE_W - la.INK_W) // 2
    rw = la.INK_W + la.FEATHER
    g = b.group("t2rLoad", anim, b.tl(0, 0, W, H), visible=0, depth=1.0)["guid"]
    b.image("t2rLoadTitle", g, b.tl(tex_l, tex_t, la.TITLE_W, la.TITLE_H), la.TITLE_TEX, 0xFFFFFFFF, la.DIM_A)
    b.image("t2rLoadTitleFull", g, b.tl(tex_l, tex_t, la.TITLE_W, la.TITLE_H), la.TITLE_TEX, 0xFFFFFFFF, 255, visible=0)   # t2r-load-bar.txt fallback
    pr = by["progress"]
    _place(pr, b.tl(ink_l, tex_t, rw, la.TITLE_H))
    pr["visible"] = 0
    pr["depth"] = 2.0
    for k in ("barFull", "gradient"):                      # the stock fill image and its glow: replaced by the mask group
        items[:] = [i for i in items if i["name"] != k]
    mask = b.group("barFull", pr["guid"], {"anchorMinN.x": 0.0, "anchorMinN.y": 0.0, "anchorMaxN.x": 1.0, "anchorMaxN.y": 1.0,
                                           "pivotN.x": 0.0, "pivotN.y": 0.5, "pivotAs.x": 0.0, "pivotAs.y": 0.0,
                                           "rectSizeDelta.width": 0.0, "rectSizeDelta.height": 0.0}, depth=0.0)
    mask["isMaskOrClip"] = 1
    mg = mask["guid"]
    b.image("t2rBright", mg, b.tl(tex_l - ink_l, 0, la.TITLE_W, la.TITLE_H), la.TITLE_TEX, 0xFFFFFFFF, 255, depth=0.0)
    b.image("t2rFeather", mg, {"anchorMinN.x": 1.0, "anchorMinN.y": 0.0, "anchorMaxN.x": 1.0, "anchorMaxN.y": 1.0,
                               "pivotN.x": 1.0, "pivotN.y": 0.5, "pivotAs.x": 0.0, "pivotAs.y": 0.0,
                               "rectSizeDelta.width": float(la.FEATHER), "rectSizeDelta.height": 0.0}, la.FEATHER_TEX, 0xFF000000, 255, depth=1.0)
    # fallback bar (t2r-load-bar.txt): the torn 12 px bar texture, fixed size inside the mask, hidden; t2r-ext scales / moves the progress group to the bottom edge
    b.image("t2rBarImg", mg, b.tl(0, 0, rw, la.TITLE_H), la.BAR_TEX, 0xFFFFFFFF, 255, visible=0, depth=2.0)
    tr = by["barTrack"]
    tr["visible"] = 0
    _col(tr, 0xFF000000)
    w["items"] = items + b.items
    json.dump(w, open(path, "w", encoding="utf-8"), indent=4)
    return len(b.items)


def restyle_connecting(wdir, variant="L"):
    """Rewrite to1/connecting.widget.json in the extracted widget folder. Returns the number of widgets added."""
    path = os.path.join(wdir, PAGE)
    w = json.load(open(path, encoding="utf-8"))
    items = w["items"]
    if any(i["name"] in ("t2rBackdrop", "t2rLoad") for i in items):
        return 0
    if variant == "L":
        return _restyle_sequence(wdir, w, path)
    v = VARIANTS[variant]
    by = {i["name"]: i for i in items}
    main = json.load(open(os.path.join(wdir, "to1", "main-menu.widget.json"), encoding="utf-8"))
    t, _, _ = _templates(main)
    for c in t.values():
        for k in ("engineClass", "tags", "animationsPath"):
            c.pop(k, None)
    anim = by["anim-group"]["guid"]
    b = Builder(t)

    # --- backdrop (under barTrack depth 1 / texts depth 2; the stock black `bg` is the floor)
    _col(by["bg"], 0xFF070808)
    g = b.group("t2rBackdrop", anim, b.tl(0, 0, W, H))["guid"]
    b.image("t2rBlur", g, b.bleed(), "general-textures/blur-background.png", 0xFFFFFFFF, 255)
    b.rect("t2rDark", g, b.bleed(), 0xFF0B0C0D, 238)
    b.image("t2rLight", g, b.ctr(v["light"][0], v["light"][1], 3000, 2000), "hud/player-menu/gradient/radial-gradient.png",
            0xFFFFFFFF, 26)

    # --- title block (launcher #title: h1 / rule / sub)
    tb = b.group("t2rTitle", anim, b.tl(0, 0, W, H))["guid"]
    x, y, al = v["tx"], v["ty"], v["al"]
    b.text("t2rMain", tb, b.tl(x, y, 2400, 170), "THE LAST OF US", 118, CREAM, align=al, tracking=4)
    rx0, rx1 = (x + 6, x + 1500) if al == 0 else (x + 2400 - 1500, x + 2400 - 6)
    b.line("t2rRule", tb, rx0, y + 200, rx1, y + 200, 0xFFFFFFFF, 110, 2.0)
    b.text("t2rSub", tb, b.tl(x, y + 230, 2400, 110), "TWELVE WEEKS", 62, DIM, align=al, tracking=30)

    # --- the stock widgets, restyled and moved
    ct = by["connectingText"]                       # "CONNECTING" (translated by loc_static_labels)
    _place(ct, b.tl(*v["ct"][:4]))
    ct.update({"pointSize": 46, "alignH": v["ct"][4], "alignV": 1, "tracking.x": 8.0})
    _col(ct, DIM)
    st = by["statusText"]                           # winmm: CHECKING NETWORK / CONNECTING TO SERVER / ...
    _place(st, b.tl(*v["st"][:4]))
    st.update({"pointSize": 46, "alignH": v["st"][4], "alignV": 1, "tracking.x": 6.0, "faceId": "Default"})
    _col(st, FAINT)
    tr = by["barTrack"]
    _place(tr, b.tl(*v["bar"]))
    _col(tr, 0xFF2A2C2E)
    _place(by["progress"], b.tl(*v["bar"]))
    _col(by["barFull"], CREAM)
    by["gradient"]["visible"] = 0                   # the stock glow at the bar head: too loud for a thin line
    import load_indicator_widgets   # TLOU2's loading icon, above the text row at the far right (driven by t2r-ext li_tick)
    sp = v["spin"]
    load_indicator_widgets.add_spinner(b, anim, sp[0], sp[1])
    # the backdrop right after the stock floor `bg`, ahead of the bar and texts: at rest the engine draws in list order (depth only sorts
    # while a page fades), so the appended backdrop (t2rDark, alpha 238) hid winmm's progress bar and status line
    back = [i for i in b.items if i["name"] in ("t2rBackdrop", "t2rBlur", "t2rDark", "t2rLight")]
    at = items.index(by["bg"]) + 1
    w["items"] = items[:at] + back + items[at:] + [i for i in b.items if i not in back]
    json.dump(w, open(path, "w", encoding="utf-8"), indent=4)
    return len(b.items)


# ------------------------------------------------------------------ preview (PIL), reads the JSON it renders
def render(wdir, out, progress=0.45, status="CONNECTING TO SERVER", scale=0.5):
    from PIL import Image, ImageDraw, ImageFont
    w = json.load(open(os.path.join(wdir, PAGE), encoding="utf-8"))
    items = w["items"]
    by = {i["guid"]: i for i in items}
    img = Image.new("RGB", (int(W * scale), int(H * scale)), (0, 0, 0))

    def argb(i):
        v = i.get("tint.start")
        if isinstance(v, str):      # stock named tints
            return {"t2-grey-text": (150, 150, 150), "t2-menu-disabled": (70, 70, 70)}.get(v, (255, 255, 255))
        return (v >> 16 & 255, v >> 8 & 255, v & 255)

    def rect_of(i):
        p = by.get(i.get("parent"))
        px, py, pw, ph = rect_of(p) if p else (0, 0, W, H)
        if i["anchorMinN.x"] == 0 and i["anchorMaxN.x"] == 1 and i["anchorMinN.y"] == 0 and i["anchorMaxN.y"] == 1:
            return (px - i["rectSizeDelta.width"] / 2, py - i["rectSizeDelta.height"] / 2,
                    pw + i["rectSizeDelta.width"], ph + i["rectSizeDelta.height"])
        ax = px + i["anchorMinN.x"] * pw
        ay = py + i["anchorMinN.y"] * ph
        ww, hh = i["rectSizeDelta.width"], i["rectSizeDelta.height"]
        x = ax + i["pivotAs.x"] - i["pivotN.x"] * ww
        y = ay + i["pivotAs.y"] - i["pivotN.y"] * hh
        return (x, y, ww, hh)

    font_cache = {}

    def font(pt):
        if pt not in font_cache:
            font_cache[pt] = ImageFont.truetype("C:/Windows/Fonts/bahnschrift.ttf", max(8, int(pt * 0.78 * scale)))
        return font_cache[pt]

    def dkey(i):                    # siblings draw by depth, children inside their parent
        k = []
        while i:
            k.append(i.get("depth", 0.0))
            i = by.get(i.get("parent"))
        return k[::-1]

    for i in sorted(items, key=dkey):
        if not i.get("visible", 1):
            continue
        p = i
        vis = True
        while p:
            if not p.get("visible", 1):
                vis = False
            p = by.get(p.get("parent"))
        if not vis or i["class"] in ("Group", "Reference"):
            continue
        x, y, ww, hh = [v * scale for v in rect_of(i)]
        a = i.get("color.a", 255) / 255.0
        if i["class"] == "Image":
            pth = i.get("path", "")
            if i["name"] == "barFull":
                px, py, pw, ph = [v * scale for v in rect_of(by[i["parent"]])]
                x, y, ww, hh = px, py, pw * progress, ph
            if "radial-gradient" in pth:
                from PIL import ImageOps
                gimg = ImageOps.invert(Image.radial_gradient("L")).point(lambda q: max(0, q - 74) * 255 // 181)
                gimg = gimg.resize((max(1, int(ww)), max(1, int(hh))))
                gimg = gimg.point(lambda v: int(v * a))
                img.paste(Image.new("RGB", gimg.size, (255, 255, 255)), (int(x), int(y)), gimg)
            elif "blur-background" in pth:
                continue            # (stock blur texture: roughly mid-grey cloud; the dark layer on top hides it)
            else:
                ov = Image.new("RGB", (max(1, int(ww)), max(1, int(hh))), argb(i))
                m = Image.new("L", ov.size, int(255 * a))
                img.paste(ov, (int(x), int(y)), m)
        elif i["class"] == "Polyline":
            d = ImageDraw.Draw(img)
            uv = i["pointsUv"]
            pts = [(x + uv[k] * ww, y + uv[k + 1] * hh) for k in range(0, len(uv), 2)]
            c = tuple(int(v * a) for v in argb(i))
            d.line(pts, fill=c, width=max(1, int(i.get("lineWidth", 2) * scale)))
        elif i["class"] == "Text":
            txt = i.get("text", "")
            if i["name"] == "statusText":
                txt = status
            f = font(i["pointSize"])
            tr = i.get("tracking.x", 0.0) * scale
            tw = sum(f.getlength(ch) + tr for ch in txt) - tr
            tx = x if i.get("alignH", 0) == 0 else (x + ww - tw if i["alignH"] == 2 else x + (ww - tw) / 2)
            ty = y + (hh - f.size) / 2 - f.size * 0.08
            d = ImageDraw.Draw(img)
            for ch in txt:
                d.text((tx, ty), ch, font=f, fill=argb(i))
                tx += f.getlength(ch) + tr
    img.save(out)


if __name__ == "__main__":
    restyle_connecting(sys.argv[1], sys.argv[3] if len(sys.argv) > 3 else "A")
    render(sys.argv[1], sys.argv[2], scale=1.0)
