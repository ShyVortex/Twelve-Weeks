"""The redesigned CHOOSE YOUR SIDE screen on to1/clan-side, inside the page's `side` group, driven by tools/ext/t2r-ext.c side_tick (choose_*).

Art: the same offline-render method as the clan end screens (re/choose-1115/src: build_choose.py -> Blender -> make_layers_choose.py), five RGBA parallax layers
chL4 (far) .. chL0 (near), 2560 x 1080 px over 5120 x 2160 units, the 3840 x 2160 frame centred (pivot in the middle, so the camera truck can move either
way). A WLF checkpoint on the left, a Seraphite treeline on the right, a ruined Seattle street at dusk between them. The ext moves / scales each layer by its
depth (idle drift + sway, a smoothed truck toward the focused camp), dims the unfocused half (chDimW / chDimS: a feathered black gradient, alpha set by the ext).
UI over it, centred like the clan end and map vote screens: title + short rule, the two camp tabs, the focused name + description + warning, the A / D hint and
SELECT. Mouse hover hit areas chHovW / chHovS (the left / right 39 %, the middle is the neutral zone). The old frames + figures (clan_widgets.build_side_page) stay in the page for the opt-out
t2r-no-choose-art.txt; the ext hides them while the art is on.
Widget space 3840 x 2160, y down."""

import os

TEX = "streaming/t2r/choose/"
W, H = 3840, 2160
CREAM = 0xFFE8E0CC
DIM = 0xFF8C887C
HINT = 0xFF9A9A9A
RED_TEXT = 0xFFE04848
SHADE_Y = 1000
HOV_W = 1500
# the camps' logos ship with the game (core.psarc gtex1/streaming/photo-mode/logos, nothing of ours): the white wolf head (wlf-wolf-logo, 414 x 504; the coloured
# wlf-logo triangle clashed with the white Seraphite mark) and the Seraphite scar mark (scar-logo, 258 x 504)
LOGO = {"W": "streaming/photo-mode/logos/wlf-wolf-logo.png", "S": "streaming/photo-mode/logos/scar-logo.png"}
LOGO_W = {"W": 414, "S": 258}
LOGO_H, LOGO_Y = 190, 1000
TW_W, TW_Y, TW_A = 1460, 1600, 215               # the title logo: 38 % of the width, centred in the band below the names (~y 700-900 of 1080), soft (alpha 215 of 255)
LOGO_CX = {"W": 1320, "S": 2520}                  # the two tabs' centres (the camp names sit under them; far enough apart that the names never touch, even with the zoomed title between)


# ---- the intro cinematic: on black (the tarp, ce-choose-deck), the lines fade in one by one, the last one carries the TWELVE WEEKS logo as a word; then
# all of it fades out, the camera drops to the overview and the UI fades in. ONE data list: swap the lines here, then `python choose_widgets.py header`
# (writes tools/ext/choose_intro_text.h: texts, measured widths per language, slot y, timing) and add their Polish lines to tools/loc/pl/03-clan.txt.
# A line = plain text (an explicit \n wraps it to two centred rows inside one fade; the loc layer translates each row) or {lead, logo: True, tail, beats}.
# The logo line's beats (Gather. Grow. Survive and TWELVE WEEKS show separately; the delay between each is shorter than the delay
# between the other sentences): each beat (its own Polish line in 03-clan.txt) fades in on its own, INTRO_BEAT_GAP_MS apart, at the place it has in the full row
# (nothing moves as they appear); then the logo + tail, INTRO_LOGO_BEAT_MS after the last word. Two beats ("Gather. Grow. Survive" | logo) = one line:
# INTRO_BEATS = ["Gather. Grow. Survive"].
INTRO_BEATS = ["Gather.", "Grow.", "Survive"]
INTRO_BEAT_MAX = 4                                  # beat text slots per line slot
# The gaps between the sentences doubled (700 -> 1400 ms), the last word and the logo on one beat (INTRO_LOGO_BEAT_MS 0; that word takes the logo's fade)
INTRO_BEAT_GAP_MS, INTRO_LOGO_BEAT_MS, INTRO_BEAT_FADE_MS = 1400, 0, 600
INTRO_LOGO_FADE_MS = 2000                           # the logo creeps in with the end tag's swell (full at ~its peak), much slower than the words
INTRO_LINES = [
    "The Outbreak took the world twenty-five years ago.",
    "Seattle flooded. The survivors stayed.",
    "Supplies are running out. Every street is claimed.",
    "The Washington Liberation Front and\nthe followers of the Prophet fight for what's left.",      # 2856 units on one row > INTRO_BOX: two rows
    {"lead": " ".join(INTRO_BEATS), "logo": True, "tail": ".", "beats": INTRO_BEATS},
]
INTRO_MAX = 6                                       # line slots in the page (3 .. 6 lines)
INTRO_PT, INTRO_COL = 56, 0xFFE2DCCE                # the picker's description style (chDesc), a size up
INTRO_BOX = 2700                                    # the widest row (game text width) before a line must be wrapped by hand
INTRO_ROW, INTRO_GAP, INTRO_CY = 96, 70, 1040       # a row's height (in game a 48 pt line is ~82 units: 56 pt ~96), the gap between lines, the block's centre y
INTRO_SLOT_H = 260
# the inline logo: tw-title.png 3000 x 760, ink x 150..2843 / y 95..664 (white + alpha); ink height = 1.45 x the text's cap height (Bahnschrift x GAME_TEXT_SCALE:
# 52.8 units at 56 pt), centred on the middle of the x-height band (10 units under the row's centre in the preview's text model)
LOGO_TEX, LOGO_SIZE, LOGO_INK = "streaming/t2r/load/tw-title.png", (3000, 760), (150, 95, 2843, 664)
INTRO_LOGO_INK_H = 1.45 * 52.8
INTRO_LOGO_K = INTRO_LOGO_INK_H / (LOGO_INK[3] - LOGO_INK[1])
INTRO_LOGO_W, INTRO_LOGO_H = LOGO_SIZE[0] * INTRO_LOGO_K, LOGO_SIZE[1] * INTRO_LOGO_K
INTRO_LOGO_INK_W = (LOGO_INK[2] - LOGO_INK[0]) * INTRO_LOGO_K
INTRO_LOGO_DX = ((LOGO_INK[0] + LOGO_INK[2]) / 2 - LOGO_SIZE[0] / 2) * INTRO_LOGO_K       # the ink's centre vs the image's centre
INTRO_LOGO_DY = -3.0                                # the logo sits on the line with the words (ink bottom on the baseline, was 17 under it)
INTRO_LOGO_GAP, INTRO_TAIL_GAP = 22.0, 4.0          # lead -> logo ink (a word space), logo ink -> the tail's '.'
# timing (ms): black, then each line's fade-in starts intro_hold(previous line) after the previous one; the logo holds INTRO_LOGO_HOLD_MS from its beat; then all out
INTRO_BLACK_MS, INTRO_FADE_MS, INTRO_LOGO_HOLD_MS, INTRO_OUT_MS = 1500, 1400, 4400, 1400   # hold 4400: the slow logo fade still gets ~2.4 s fully up


def intro_hold(line):
    n = len(line if isinstance(line, str) else line["lead"] + "twelve weeks" + line.get("tail", ""))
    return int(min(5300, max(3900, 2900 + 30 * n)))          # longer gaps between the sentences (+1.5 s each; the fade itself unchanged)


# the red chalk strike (re/choose-1115/src/make_chalk_choose.py -> chalk.json + tex/ch-chalk-NN.png): its box is centred at (the other camp's logo x, CHALK_CY)
CHALK_CY = 1140
_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
CHALK_JSON = os.path.join(_ROOT, "re", "choose-1115", "chalk.json")


def tex(n):
    return TEX + n + ".png"


def text_w(s, pt=INTRO_PT):
    """the game's text width (units) of one row: Bahnschrift at pt x widget_preview.GAME_TEXT_SCALE (the preview's in-game wrapping model)"""
    import widget_preview as wp
    from PIL import ImageFont
    f = ImageFont.truetype(wp.FONT, int(pt * wp.GAME_TEXT_SCALE * 8))
    return f.getlength(s) / 8.0


def intro_layout(lines=None, tr=None):
    """per line: its slot centre y, rows, and for a logo line the x layout {lead_right, logo_cx, tail_left} (tr: a translation lookup, None = English)"""
    lines = INTRO_LINES if lines is None else lines
    tr = tr or (lambda s: s)
    rows = [1 if not isinstance(ln, str) else ln.count("\n") + 1 for ln in lines]
    tot = sum(r * INTRO_ROW for r in rows) + INTRO_GAP * (len(lines) - 1)
    y, out = INTRO_CY - tot / 2.0, []
    for ln, r in zip(lines, rows):
        h = r * INTRO_ROW
        d = {"cy": y + h / 2.0, "rows": r}
        if not isinstance(ln, str):
            bw = [text_w(tr(x)) for x in ln.get("beats") or [ln["lead"]]]
            sp = text_w(" ")
            wl = sum(bw) + sp * (len(bw) - 1)                       # (the beats' widths + spaces: the same sum the ext makes)
            wt = text_w(tr(ln["tail"])) if ln.get("tail") else 0.0
            total = wl + INTRO_LOGO_GAP + INTRO_LOGO_INK_W + (INTRO_TAIL_GAP + wt if wt else 0.0)
            x0 = W / 2.0 - total / 2.0
            ink_l = x0 + wl + INTRO_LOGO_GAP
            bx = [x0 + sum(bw[:i]) + sp * i for i in range(len(bw))]
            d.update(lead_right=x0 + wl, logo_cx=ink_l + INTRO_LOGO_INK_W / 2.0 - INTRO_LOGO_DX, tail_left=ink_l + INTRO_LOGO_INK_W + INTRO_TAIL_GAP, lead_w=wl, tail_w=wt,
                     beat_left=bx)
        out.append(d)
        y += h + INTRO_GAP
    return out


# The intro camera starts high so the pan down starts well above the characters:
# the layers carry LAYER_EXT units of scene ABOVE the overview frame (render_choose.sh / make_layers_choose.py T2R_EXT_TOP = 1200 px at SC 2), so the intro
# camera can start high; the pivot stays the overview frame's centre (= choose.c CH_LAYER_EXT).
LAYER_EXT = 1200.0


def add_art(b, s):
    """Group chArt (first child of `side`: under everything): black, the five layers, the dims, the shade, vignette, grain. Returns the group item."""
    a = b.group("chArt", s, b.tl(0, 0, W, H), visible=0)
    g = a["guid"]
    b.rect("chBlack", g, b.bleed(), 0xFF000000, 255)
    art = b.group("chLayers", g, b.tl(0, 0, W, H))["guid"]
    for i in (4, 3, 2, 1, 0):                         # far first (drawn under)
        b.image("chL%d" % i, art, {"anchorMinN.x": 0.0, "anchorMinN.y": 0.0, "anchorMaxN.x": 0.0, "anchorMaxN.y": 0.0,
                                    "pivotN.x": 0.5, "pivotN.y": (1080.0 + LAYER_EXT) / (2160.0 + LAYER_EXT), "pivotAs.x": 1920.0, "pivotAs.y": 1080.0,
                                    "rectSizeDelta.width": 5120.0, "rectSizeDelta.height": 2160.0 + LAYER_EXT}, tex("ce-choose-L%d" % i))
    b.image("chDeck", art, {"anchorMinN.x": 0.0, "anchorMinN.y": 0.0, "anchorMaxN.x": 0.0, "anchorMaxN.y": 0.0,     # the intro's tarp (nearest: over L0, 5120 x 2808,
                            "pivotN.x": 0.5, "pivotN.y": 0.5, "pivotAs.x": 1920.0, "pivotAs.y": 1080.0 - 2354.4,                    # its centre 2354 units over a layer's at rest):
                            "rectSizeDelta.width": 5120.0, "rectSizeDelta.height": 2808.0}, tex("ce-choose-deck"), visible=0)    # the ext drops it with the camera, then hides it
    b.image("chDimW", g, b.tl(0, 0, W, H), tex("ch-dim-l"), 0xFFFFFFFF, 0)       # the unfocused half darkens (ext alpha)
    b.image("chDimS", g, b.tl(0, 0, W, H), tex("ch-dim-r"), 0xFFFFFFFF, 0)
    b.image("chShade", g, b.tl(0, SHADE_Y, W, H - SHADE_Y), tex("ch-shade"), 0xFFFFFFFF, 255)   # under the text block
    b.image("chVig", g, b.tl(0, 0, W, H), "streaming/t2r/clanend/ce-vig.png")
    b.image("chGrain", g, b.tl(-512, -512, W + 1024, H + 1024), "streaming/t2r/clanend/ce-grain.png", 0xFFFFFFFF, 150, scaleMode="Tile")
    return a


def add_ui(b, s):
    """Group chUi (last child of `side`: over the old items, which the ext hides while the art is on) + the hover areas."""
    b.group("chHovW", s, b.tl(0, 0, HOV_W, H))                                    # mouse zones: the left 39 % = WLF, the right 39 % = Seraphites, the middle 22 % neutral
    b.group("chHovS", s, b.tl(W - HOV_W, 0, HOV_W, H))
    u = b.group("chUi", s, b.tl(0, 0, W, H), visible=0)["guid"]
    b.text("chTitle", u, b.tl(320, 120, 3200, 150), "CHOOSE YOUR SIDE", 96, CREAM, align=1, face="Alternate", tracking=8)
    b.line("chTitleLine", u, 1620, 292, 2220, 292, CREAM, 90, 2.0)
    b.image("chScrim", u, b.ctr(1920, 1140, 3300, 560), "hud/player-menu/gradient/radial-gradient.png", 0xFF000000, 200)       # a soft dark scrim under the logos / names (they sit over the figures)
    b.image("chTitleLogo", u, b.ctr(W / 2, TW_Y, TW_W, TW_W * 760 / 3000), "streaming/t2r/load/tw-title.png", CREAM, TW_A)   # the TWELVE WEEKS title in the empty dark band below the camp names; only while nothing else is in the lower area (the ext fades it)
    for k, cx in (("W", LOGO_CX["W"]), ("S", LOGO_CX["S"])):                                      # the two camp tabs = the game's own faction logos (white, 504 px high); the ext lights the focused one
        lw = LOGO_H * LOGO_W[k] / 504.0                                           # (centred: the ext scales the focused logo up and the other down about its centre)
        b.image("chLogo%s" % k, u, b.ctr(cx, LOGO_Y + LOGO_H / 2, lw, LOGO_H), LOGO[k], 0xFFFFFFFF, 255)
    for k, cx in (("W", LOGO_CX["W"]), ("S", LOGO_CX["S"])):                                      # the camp names: 100 pt, centred (so the ext scales / moves them about the centre): small under the logo
        # (scale CH_TAB_K at CH_TAB_Y) until the camp is focused, then the big title (scale 1 at CH_BIG_X, CH_BIG_Y) - t2r-ext choose.c
        b.text("chName%s" % k, u, b.ctr(cx, 1250, 1100, 150), "WLF" if k == "W" else "SERAPHITES", 100, CREAM, align=1, face="Alternate", tracking=8)
    b.text("chDesc", u, b.tl(700, 1445, 2440, 290), "", 48, 0xFFE2DCCE, align=1, multiline=1, valign=0, **{"color.a": 0})
    b.text("chWarn", u, b.tl(420, 1760, 3000, 90), "", 42, RED_TEXT, align=1, multiline=1, valign=0, **{"color.a": 0})
    b.text("chHint", u, b.tl(240, 1890, 900, 70), "A / D  TO SWITCH", 38, HINT, tracking=4)
    ph = b.group("chHintPad", u, b.tl(240, 1890, 900, 70), visible=0)["guid"]          # the pad version (controller parity): the bumper glyphs
    b.image("chHintPrev", ph, b.tl(0, 7, 56, 56), "menu:prev", 0xFFFFFFFF)
    b.image("chHintNext", ph, b.tl(70, 7, 56, 56), "menu:next", 0xFFFFFFFF)
    b.text("chHintPadTx", ph, b.tl(150, 0, 750, 70), "TO SWITCH", 38, HINT, tracking=4)
    b.image("chSelIcon", u, b.tl(3270, 1898, 56, 56), "menu:select", 0xFFFFFFFF)
    b.text("chSelText", u, b.tl(3350, 1890, 300, 70), "SELECT", 46, 0xFFE6E6E6, tracking=4)
    add_chalk(b, u)
    add_intro(b, s)
    return u


def add_chalk(b, u):
    """chChalk (in chUi, over the logos): the red chalk strike's 8 group images (make_chalk_groups.py; was 24 piece images, which passed the engine's
    32-image table on the payoff, A/B), all alpha 0; the ext moves the group to the unchosen camp's logo and fades them in in turn"""
    import json
    cj = json.load(open(CHALK_JSON))
    bw, bh = cj["box"]
    g = b.group("chChalk", u, b.ctr(LOGO_CX["S"], CHALK_CY, bw, bh), visible=0)["guid"]
    for k, p in enumerate(cj["groups"]):
        b.image("chg%d" % k, g, b.tl(p["x"], p["y"], p["w"], p["h"]), tex(p["name"]), 0xFFFFFFFF, 0)


def add_intro(b, s):
    """chIntro (over everything of `side`): INTRO_MAX line slots (a group per line, alpha = its fade; children: the centred text `tx`, or the beats `b0`..`b3`
    (left-aligned words, each its own fade) / logo `lg` / tail `tl`), the SKIP prompt (bottom right, where SELECT sits; glyph = menu:select), and chIntroFade (black: the skip's dip to black). All hidden / alpha 0:
    the ext (choose.c chi_*) runs it and re-places the slots and the logo line from tools/ext/choose_intro_text.h."""
    g = b.group("chIntro", s, b.tl(0, 0, W, H), visible=0)["guid"]
    lay = intro_layout()
    for k in range(INTRO_MAX):
        ln = INTRO_LINES[k] if k < len(INTRO_LINES) else ""
        d = lay[k] if k < len(lay) else {"cy": INTRO_CY, "rows": 1}
        sl = b.group("chIntroL%d" % k, g, b.ctr(W / 2, d["cy"], W, INTRO_SLOT_H), **{"color.a": 0})["guid"]
        mid = INTRO_SLOT_H / 2.0
        lg = not isinstance(ln, str)
        b.text("tx", sl, b.ctr(W / 2, mid, 3400, INTRO_SLOT_H), "" if lg else ln, INTRO_PT, INTRO_COL, align=1, multiline=1)
        lr, lc, tl_ = d.get("lead_right", W / 2), d.get("logo_cx", W / 2), d.get("tail_left", W / 2)
        bts = (ln.get("beats") or [ln["lead"]]) if lg else []
        for j in range(INTRO_BEAT_MAX):
            bl = d["beat_left"][j] if j < len(bts) else W / 2
            b.text("b%d" % j, sl, b.ctr(bl + 700, mid, 1400, INTRO_SLOT_H), bts[j] if j < len(bts) else "", INTRO_PT, INTRO_COL, align=0, visible=1 if j < len(bts) else 0,
                   **{"color.a": 0})
        b.image("lg", sl, b.ctr(lc, mid + INTRO_LOGO_DY, INTRO_LOGO_W, INTRO_LOGO_H), LOGO_TEX, INTRO_COL, 255, visible=1 if lg else 0)
        b.text("tl", sl, b.ctr(tl_ + 150, mid, 300, INTRO_SLOT_H), ln.get("tail", "") if lg else "", INTRO_PT, INTRO_COL, align=0, visible=1 if lg else 0)
    sk = b.group("chIntroSkip", g, b.tl(0, 0, W, H), **{"color.a": 0})["guid"]
    b.image("chSkipIcon", sk, b.tl(3270, 1898, 56, 56), "menu:select", 0xFFFFFFFF)
    b.text("chSkipText", sk, b.tl(3350, 1890, 300, 70), "SKIP", 46, 0xFFE6E6E6, tracking=4)
    b.rect("chIntroFade", s, b.bleed(), 0xFF000000, 0, visible=0)


def _cstr(t):
    return '"' + t.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n") + '"'


def write_header(path=None):
    """tools/ext/choose_intro_text.h from INTRO_LINES (+ the loc lines of every language for the logo line's widths) and chalk.json"""
    import json, glob
    path = path or os.path.join(_ROOT, "tools", "ext", "choose_intro_text.h")
    tr = {}
    for f in glob.glob(os.path.join(_ROOT, "tools", "loc", "*", "*.txt")):
        for row in open(f, encoding="utf-8"):
            if " => " in row and not row.startswith("#"):
                a, c = row.rstrip("\n").split(" => ", 1)
                tr.setdefault(a, set()).add(c)
    lay = intro_layout()
    o = ["// tools/ext/choose_intro_text.h - generated by tools/features/choose_widgets.py header (do not edit): the CHOOSE YOUR SIDE intro lines (INTRO_LINES),",
         "// their slot centres (y, units), fade-in start (ms after the page shows), the logo line's text widths (every displayed form: English and each",
         "// translation in tools/loc/<code>; game width = Bahnschrift x GAME_TEXT_SCALE), and the red chalk strike's groups (fade-in start / end ms after the confirm).",
         "#define CHI_N %d" % len(INTRO_LINES), "#define CHI_MAX %d" % INTRO_MAX,
         "#define CHI_BLACK_MS %d" % INTRO_BLACK_MS, "#define CHI_FADE_MS %d" % INTRO_FADE_MS, "#define CHI_OUT_MS %d" % INTRO_OUT_MS,
         "#define CHI_LOGO_GAP %.1ff" % INTRO_LOGO_GAP, "#define CHI_TAIL_GAP %.1ff" % INTRO_TAIL_GAP, "#define CHI_LOGO_INK_W %.1ff" % INTRO_LOGO_INK_W,
         "#define CHI_LOGO_DX %.2ff" % INTRO_LOGO_DX, "#define CHI_LOGO_DY %.1ff" % INTRO_LOGO_DY, "#define CHI_SLOT_H %.1ff" % INTRO_SLOT_H,
         "#define CHI_PT %d" % INTRO_PT, "#define CHI_BEAT_MAX %d" % INTRO_BEAT_MAX, "#define CHI_BEAT_FADE_MS %d" % INTRO_BEAT_FADE_MS, "#define CHI_LOGO_FADE_MS %d" % INTRO_LOGO_FADE_MS,
         "typedef struct { const char *text, *lead, *tail; int logo; float cy; int t_in; } chi_line_t;",
         "typedef struct { const char *s; int t_in; } chi_beat_t;",
         "typedef struct { const char *s; float w; } chi_w_t;"]
    t, rows, ws, beats, logo_t = INTRO_BLACK_MS, [], {'    {" ", %.1ff},' % text_w(" ")}, [], None
    for k, (ln, d) in enumerate(zip(INTRO_LINES, lay)):
        if isinstance(ln, str):
            rows.append("    {%s, NULL, NULL, 0, %.1ff, %d}," % (_cstr(ln), d["cy"], t))
        else:
            rows.append("    {NULL, %s, %s, 1, %.1ff, %d}," % (_cstr(ln["lead"]), _cstr(ln.get("tail", "")), d["cy"], t))
            bts = ln.get("beats") or [ln["lead"]]
            assert " ".join(bts) == ln["lead"] and len(bts) <= INTRO_BEAT_MAX, "the beats must spell the lead"
            beats = [(x, t + j * INTRO_BEAT_GAP_MS) for j, x in enumerate(bts)]
            logo_t = beats[-1][1] + INTRO_LOGO_BEAT_MS
            for s_ in bts + [ln.get("tail", "")]:
                if s_:
                    for v in {s_} | tr.get(s_, set()):
                        ws.add("    {%s, %.1ff}," % (_cstr(v), text_w(v)))
        if k < len(INTRO_LINES) - 1:
            t += intro_hold(ln)
    o.append("static const chi_line_t CHI_LINE[CHI_N] = {")
    o += rows
    o.append("};")
    last = INTRO_LINES[-1]
    assert not isinstance(last, str), "the logo line is the last line"
    o.append("#define CHI_LAST_IN_MS %d" % t)
    o.append("#define CHI_BEAT_N %d" % len(beats))
    o.append("static const chi_beat_t CHI_BEAT[CHI_BEAT_N] = {%s};             // the logo line's words: text, fade-in start (ms)" % ", ".join("{%s, %d}" % (_cstr(x), bt) for x, bt in beats))
    o.append("#define CHI_LOGO_IN_MS %d                   // the TWELVE WEEKS logo (+ tail) beat" % logo_t)
    o.append("#define CHI_TEXT_OUT_MS %d                  // everything fades out from here (the logo holds INTRO_LOGO_HOLD_MS)" % (logo_t + INTRO_LOGO_HOLD_MS))
    o.append("static const chi_w_t CHI_W[] = {")
    o += sorted(ws) or ['    {"", 0.0f},']
    o.append("};")
    cj = json.load(open(CHALK_JSON))
    o.append("#define CHI_CHALK_N %d" % len(cj["groups"]))
    o.append("#define CHI_CHALK_END_MS %.0f" % max(cj["end_ms"], max(p["t1"] for p in cj["groups"])))
    o.append("#define CHI_CHALK_CY %.1ff" % CHALK_CY)
    o.append("static const float CHI_CHALK_T0[CHI_CHALK_N] = {%s};" % ", ".join("%.1ff" % p["t0"] for p in cj["groups"]))
    o.append("static const float CHI_CHALK_T1[CHI_CHALK_N] = {%s};" % ", ".join("%.1ff" % p["t1"] for p in cj["groups"]))
    for k, ln in enumerate(INTRO_LINES):
        rws = [ln] if not isinstance(ln, str) else ln.split("\n")
        for r in rws:
            w_ = text_w(r) if isinstance(r, str) else 0
            if w_ > INTRO_BOX:
                raise SystemExit("intro line %d row is %.0f units > INTRO_BOX %d: wrap it with \\n" % (k + 1, w_, INTRO_BOX))
    open(path, "w", encoding="utf-8", newline="\n").write("\n".join(o) + "\n")
    return path


if __name__ == "__main__":
    import sys
    if sys.argv[1:] == ["header"]:
        print(write_header())
