"""Clan UI widgets (2013 Factions look), added to gui2-widgets.pak by widgets_patch.patch_widgets.

- to1/clan-side (new page, pushed by t2r-ext feature_clan): the 2013 first-launch flow.
  Group "intro": story card (dark framed panel, the two factions facing off, story text, NEXT).
  Group "side": CHOOSE YOUR SIDE (2013factionsclanfirstlaunch2png.png): title + divider, the two
  faction figures (focused one framed, glowing in its colour, the other dimmed), vertical divider,
  name / description / red warning on the right, SELECT bottom right, A/D TO SWITCH.
- to1/main-menu: "clanPanel" (2013factionsclanfirstlaunch3png.png): dark panel with side lines,
  N SURVIVORS, person icon, HEALTHY / HUNGRY / SICK, supply icon + NEEDED PER DAY, a soft grey
  circle with up to 60 survivor dots (one group per dot, three coloured ellipses inside: healthy /
  hungry / sick; t2r-ext moves the groups and picks the colour). Hidden until the ext shows it.
- to1/clan-postmatch (new page, pushed by t2r-ext pm_tick on the MP menu after a clan match): the
  2013 post-match day report (post-match-rewards/1..5.png) - parts per award, PARTS EARNED ->
  CONVERTED, then DAILY SUPPLIES | SURVIVORS GAINED with the dot circle. Offline previews:
  python clan_widgets.py <extracted widget dir> <out dir>.
- to1/clan-event (new page, pushed by t2r-ext ev_tick): the 2013 clan event screens (PAGE_CLAN_EVENT_1 announcement on the
  day of an event, PAGE_CLAN_EVENT_2 result after the match): event name, the picture (the camp circle with the raiders /
  friends around it), the 2013 description, the three tiers, the result lines. Preview: clan_widgets.py <dir> <out> event.

The faction figures are images rendered from the MP character models (FIG_IMG below); the
survivors icon is still built from widget primitives (PERSON).

Widget space is 3840 x 2160, y down. Items placed by their top-left (tl) or centre (ctr) with
zero anchors inside their parent. Colours are ARGB ints (tint.start / tint.end)."""
import copy
import json
import os
import t2guid
import ui_r2_widgets

W, H = 3840, 2160
WLF_COL = 0xFFDCEEF6          # WLF: white with a cold cyan cast (DESIGN: WLF = white)
WLF_GLOW = 0xFFB8E6FF
SER_COL = 0xFFD8402F          # Seraphites: red
SER_GLOW = 0xFFFF4A36
DARK = 0xFF0E1114             # silhouette detail colour
HEALTHY, HUNGRY, SICK = 0xFF5DC0DC, 0xFF9C9A9A, 0xFFFD6D51   # *clan-vars* colours (hungry lifted)
SUPPLY_BLUE = 0xFF3FA9F5
RED_TEXT = 0xFFE04848
MAX_DOTS = 60
DOT = 16
CIRCLE = 340

PAGE = "clan-side"
BRAND_TEX = "streaming/t2r/load/tw-title.png"     # the TWELVE WEEKS entry screen's title (loading_art.TITLE_TEX): white + alpha, 3000 x 760
BRAND_W = 900                                     # intro card: brand mark width above the card (ink = 90 % of it)
SIDE_BRAND_W = 640                                # CHOOSE YOUR SIDE: small mark at the right end of the header row
INTRO_BG = 0xFF0F1114                             # intro card: deep charcoal with a little blue, not pure black
INTRO_LIGHT_A = 34                                # its soft mid-card light (vignette)
INTRO_FIG_K = 0.95                                # figures 1102 of the card's 1310 units high (84 %)
INTRO_FIG_Y, INTRO_CX_W, INTRO_CX_S = 404, 1250, 2600
GLOW_R, GLOW_A = 1900, 100                   # hover bloom: radius 1250 units (58 % of the height), image alpha 30 / 255 at its centre (the corner)
SIDE_BG_A = 0.90                                  # backdrop alpha the ext fades to (t2r-ext SIDE_BG_A)
INTRO_TEXT = ("It's been 25 years since the Outbreak. In Seattle, the Washington Liberation Front and the "
              "Seraphites fight over territory, supplies, and lives to grow their size and influence. There is "
              "safety in numbers - each faction is trying to rebuild its population by finding supplies.")
# Lore texts: at most 6 lines in the 1200-wide box at 48 pt as the game draws it (its glyphs are
# ~1.33x wider than the offline preview's Bahnschrift; widget_preview.GAME_TEXT_SCALE). The red
# warning sits under the 7-line box with a gap, so neither faction's text can run into it.
WLF_DESC = ("Soldiers who drove FEDRA out of Seattle and took the city for themselves. Disciplined, well "
            "armed and dug in around the stadium. They trust training, numbers and firepower, and burn "
            "out anyone who threatens their walls.")
SER_DESC = ("Followers of the Prophet, living off the land on the islands around the city. They turned "
            "their backs on the old world and its machines. Patient, silent and deadly with a bow - they "
            "speak in whistles and strike from the trees.")
WARNING = "Your faction choice lasts until your clan dies or survives long enough to win."
DESC_Y, DESC_W, DESC_H = 450, 1200, 7 * 82      # in game a 48 pt line is ~82 units tall
WARN_Y = DESC_Y + DESC_H + 70

# ------------------------------------------------------------------ figures (images)
# Rendered from the MP character models in the 2013 style by tools/models/figures/make_figures.py
# (re/figures -> gtex1/streaming/t2r/clan, build_dll). fig-*: white figure, black detail shapes,
# transparent outside - the tint makes it the faction colour (focused) or grey (dimmed); glow-*:
# soft white silhouette drawn under the focused one in the glow colour.
FIG_W, FIG_H = 640, 1160
FIG_IMG = {"W": "streaming/t2r/clan/fig-wlf.png", "S": "streaming/t2r/clan/fig-ser.png"}
GLOW_IMG = {"W": "streaming/t2r/clan/glow-wlf.png", "S": "streaming/t2r/clan/glow-ser.png"}
DIM_TINT = 0xFF5C6064
PERSON = [   # the small survivors icon (2013 panel), box 80 x 170
    ("e", 40, 20, 34, 34), ("r", 40, 70, 46, 62, 0), ("e", 22, 46, 22, 22), ("e", 58, 46, 22, 22),
    ("r", 14, 78, 14, 58, 0), ("r", 66, 78, 14, 58, 0), ("r", 30, 128, 18, 76, 0), ("r", 50, 128, 18, 76, 0),
]


# ------------------------------------------------------------------ item factory
class Builder:
    def __init__(self, templates):
        self.t = templates
        self.items = []

    def add(self, cls, name, parent, **kw):
        c = copy.deepcopy(self.t[cls])
        c.update({"guid": t2guid.guid(), "parent": parent, "name": name, "visible": 1, "rotation": 0.0,
                  "depth": float(len(self.items)) * 0.01, "color.a": 255, "animation": {"keyframes": {}}})
        c.update(kw)
        self.items.append(c)
        return c

    @staticmethod
    def tl(x, y, w, h):
        return {"anchorMinN.x": 0.0, "anchorMinN.y": 0.0, "anchorMaxN.x": 0.0, "anchorMaxN.y": 0.0,
                "pivotN.x": 0.0, "pivotN.y": 0.0, "pivotAs.x": float(x), "pivotAs.y": float(y),
                "rectSizeDelta.width": float(w), "rectSizeDelta.height": float(h)}

    @staticmethod
    def ctr(cx, cy, w, h, rot=0.0):
        return {"anchorMinN.x": 0.0, "anchorMinN.y": 0.0, "anchorMaxN.x": 0.0, "anchorMaxN.y": 0.0,
                "pivotN.x": 0.5, "pivotN.y": 0.5, "pivotAs.x": float(cx), "pivotAs.y": float(cy),
                "rectSizeDelta.width": float(w), "rectSizeDelta.height": float(h), "rotation": float(rot)}

    @staticmethod
    def fill():
        return {"anchorMinN.x": 0.0, "anchorMinN.y": 0.0, "anchorMaxN.x": 1.0, "anchorMaxN.y": 1.0,
                "pivotN.x": 0.5, "pivotN.y": 0.5, "pivotAs.x": 0.0, "pivotAs.y": 0.0,
                "rectSizeDelta.width": 0.0, "rectSizeDelta.height": 0.0}

    @staticmethod
    def bleed():
        """Full-screen backdrop at ANY aspect: the page root is a fixed 3840x2160 box the engine fits (letterbox /
        pillarbox) into the real window, so a plain fill() stops at the 16:9 edge. Stretch anchors + a 1-canvas
        bleed on every side (centre pivot, delta grows symmetrically) cover up to ~3x the canvas either way."""
        return {"anchorMinN.x": 0.0, "anchorMinN.y": 0.0, "anchorMaxN.x": 1.0, "anchorMaxN.y": 1.0,
                "pivotN.x": 0.5, "pivotN.y": 0.5, "pivotAs.x": 0.0, "pivotAs.y": 0.0,
                "rectSizeDelta.width": 2.0 * W, "rectSizeDelta.height": 2.0 * H}

    @staticmethod
    def col(argb):
        return {"tint.start": argb, "tint.end": argb}

    def group(self, name, parent, place, **kw):
        return self.add("Group", name, parent, **place, **kw)

    def text(self, name, parent, place, text, pt, argb=0xFFE6E6E6, align=0, face="Default", multiline=0,
             valign=1, tracking=0.0, **kw):
        return self.add("Text", name, parent, **place, **self.col(argb), text=text, pointSize=pt, faceId=face,
                        alignH=align, alignV=valign, multiline=multiline, **{"tracking.x": float(tracking)}, **kw)

    def image(self, name, parent, place, path, argb=0xFFFFFFFF, alpha=255, **kw):
        if path.startswith("menu:"):    # stock button prompts (to1/find-match-menu footer): the engine's input glyph is
            # drawn StretchAspect, centred (alignH/alignV 1) - plain Stretch squished the wide SPACE key into the square box
            kw = {"scaleMode": "StretchAspect", "alignH": 1, "alignV": 1, "slices": [0.328125] * 4, **kw}
        else:
            kw = {"scaleMode": "Stretch", **kw}
        return self.add("Image", name, parent, **place, **self.col(argb), path=path,
                        **{"color.a": alpha}, **kw)

    def rect(self, name, parent, place, argb, alpha=255, **kw):
        return self.image(name, parent, place, "general-textures/square-32px.png", argb, alpha, **kw)

    def line(self, name, parent, x0, y0, x1, y1, argb=0xFFFFFFFF, alpha=120, width=2.0):
        x, y = min(x0, x1), min(y0, y1)
        w, h = max(abs(x1 - x0), 1.0), max(abs(y1 - y0), 1.0)
        uv = [(x0 - x) / w, (y0 - y) / h, (x1 - x) / w, (y1 - y) / h]
        return self.add("Polyline", name, parent, **self.tl(x, y, w, h), **self.col(argb), pointsUv=uv, closed=0,
                        lineWidth=float(width), **{"color.a": alpha})

    def frame(self, name, parent, place, argb=0xFFFFFFFF, alpha=200, width=3.0, **kw):
        return self.add("Polyline", name, parent, **place, **self.col(argb), closed=1, lineWidth=float(width),
                        pointsUv=[0.0, 0.0, 1.0, 0.0, 1.0, 1.0, 0.0, 1.0], **{"color.a": alpha}, **kw)

    def ellipse(self, name, parent, place, argb, alpha=255, filled=1, begin=0, end=360, width=0.0):
        return self.add("Ellipse", name, parent, **place, **self.col(argb), filled=filled, beginDegrees=begin,
                        endDegrees=end, lineWidth=width, **{"color.a": alpha})

    def shapes(self, prefix, parent, prims, argb_body, argb_detail=DARK, scale=1.0, ox=0.0, oy=0.0):
        """Pictogram primitives -> items, drawn in list order (later = on top)."""
        for k, (layer, p) in enumerate(prims):
            argb = argb_body if layer == "b" else argb_detail
            nm = f"{prefix}{layer}{k}"
            kind = p[0]
            if kind == "e":
                _, cx, cy, w, h = p
                self.ellipse(nm, parent, self.ctr(ox + cx * scale, oy + cy * scale, w * scale, h * scale), argb)
            elif kind == "r":
                _, cx, cy, w, h, rot = p
                self.rect(nm, parent, self.ctr(ox + cx * scale, oy + cy * scale, w * scale, h * scale, rot), argb)
            elif kind == "a":
                _, cx, cy, w, h, b, e, lw = p
                self.ellipse(nm, parent, self.ctr(ox + cx * scale, oy + cy * scale, w * scale, h * scale), argb,
                             filled=0, begin=b, end=e, width=lw * scale)
            elif kind == "l":
                _, x0, y0, x1, y1, lw = p
                self.line(nm, parent, ox + x0 * scale, oy + y0 * scale, ox + x1 * scale, oy + y1 * scale,
                          argb, 255, lw * scale)


def _templates(main):
    by = {i["name"]: i for i in main["items"]}
    t = {"Text": by["gameTitle"], "Image": by["lobbyBg"], "Polyline": by["titleUnderline"],
         "Ellipse": by["onlineDot"], "Group": by["lobbyPanel"]}
    return {k: copy.deepcopy(v) for k, v in t.items()}, by["root"], by["anim-group"]


def _figure(b, parent, key, x, y, body, glow):
    """Figure group at (x, y), box FIG_W x FIG_H: glow + bright image (focused) / grey image (dimmed).
    t2r-ext toggles fig?Glow / fig?Body / fig?Dim (side_focus) and re-sets the image paths."""
    g = b.group(f"fig{key}", parent, b.tl(x, y, FIG_W, FIG_H))
    b.image(f"fig{key}Glow", g["guid"], b.fill(), GLOW_IMG[key], glow, 230)
    b.image(f"fig{key}Body", g["guid"], b.fill(), FIG_IMG[key], body, 255)
    b.image(f"fig{key}Dim", g["guid"], b.fill(), FIG_IMG[key], DIM_TINT, 255, visible=0)
    return g


def build_side_page(main):
    """to1/clan-side.widget.json content."""
    t, root0, anim0 = _templates(main)
    b = Builder(t)
    root = copy.deepcopy(root0); root.update(guid=t2guid.guid())
    anim = copy.deepcopy(anim0); anim.update(guid=t2guid.guid(), parent=root["guid"])
    b.items += [root, anim]
    a = anim["guid"]
    # redesign (re/clan-select-1105): the soft grey (blurred scene + grey card + grey floor + radial light) is gone. Pure black like the
    # 2013 first-launch screens; the scene shows through the black only dimly. Every top-level layer starts at alpha 0: t2r-ext side_tick
    # fades them in (SIDE_BG_A for the backdrop) so the page never pops (no frame at full alpha before the ext's first tick).
    b.rect("bgDark", a, b.bleed(), 0xFF000000, 0)

    # --- intro card (2013factionsclanfirstlaunch1): black card, white frame, the two sides facing off, brand mark above
    it = b.group("intro", a, b.tl(0, 0, W, H), **{"color.a": 0})
    i = it["guid"]
    b.image("introBrand", i, b.ctr(W / 2, 135, BRAND_W, BRAND_W * 760 / 3000), BRAND_TEX, 0xFFE6E6E6, 255)
    b.rect("introPanel", i, b.tl(600, 300, 2650, 1310), INTRO_BG, 255)
    b.image("introLight", i, b.ctr(1925, 955, 2900, 1500), "hud/player-menu/gradient/radial-gradient.png", 0xFFB4BEC8, INTRO_LIGHT_A)   # vignette: a cool soft light mid-card, the corners stay deep
    b.frame("introFrame", i, b.tl(600, 300, 2650, 1310), 0xFFE6E6E6, 170, 3.0)
    # the two sides facing off, black and white like the 2013 comic panel
    b.image("introW", i, b.tl(INTRO_CX_W - FIG_W * INTRO_FIG_K / 2, INTRO_FIG_Y, FIG_W * INTRO_FIG_K, FIG_H * INTRO_FIG_K), FIG_IMG["W"], 0xFFC8C8C8)
    b.image("introS", i, b.tl(INTRO_CX_S - FIG_W * INTRO_FIG_K / 2, INTRO_FIG_Y, FIG_W * INTRO_FIG_K, FIG_H * INTRO_FIG_K), FIG_IMG["S"], 0xFF9A9A9A)
    b.text("introVs", i, b.tl(1500, 860, 850, 200), "VS", 170, 0xFFE6E6E6, align=1, face="Alternate", tracking=20)
    b.text("introText", i, b.tl(600, 1650, 2650, 260), INTRO_TEXT, 52, 0xFFE6E6E6, align=1, multiline=1, valign=0)
    # end page (clan dead / won): title + stats, set by t2r-ext side_tick; empty on the first launch
    b.text("introTitle", i, b.tl(600, 330, 2650, 120), "", 90, 0xFFE6E6E6, align=1, face="Alternate", tracking=12)
    b.text("introStats", i, b.tl(600, 1330, 2650, 260), "", 56, 0xFFE6E6E6, align=1, multiline=1, valign=0, tracking=4)
    b.image("introNextIcon", i, b.tl(3330, 1898, 56, 56), "menu:select", 0xFFFFFFFF)
    b.text("introNextText", i, b.tl(3410, 1890, 300, 70), "NEXT", 46, 0xFFE6E6E6, tracking=4)

    # --- CHOOSE YOUR SIDE (2013factionsclanfirstlaunch2)
    sd = b.group("side", a, b.tl(0, 0, W, H), visible=0, **{"color.a": 0})
    s = sd["guid"]
    # mood lights of the focused faction (t2r-ext side_tick fades the group alpha, 300 ms, cross-fading): a soft radial bloom from the bottom-left corner in
    # white (WLF) / the bottom-right corner in red (Seraphites)
    for key, col, left in (("W", 0xFFEAF4FF, True), ("S", 0xFFE03A2C, False)):
        g = b.group("glow" + key, s, b.tl(0, 0, W, H), **{"color.a": 0})["guid"]
        # one soft radial from the bottom corner (the engine's own radial-gradient texture, smooth - no layers, no banding), tinted
        b.image("glow" + key + "R", g, b.ctr(0 if left else W, H, 2 * GLOW_R, 2 * GLOW_R), "hud/player-menu/gradient/radial-gradient.png", col, GLOW_A)
    b.text("sideTitle", s, b.tl(290, 150, 2000, 150), "CHOOSE YOUR SIDE", 96, 0xFFE6E6E6, face="Default", tracking=6)
    b.line("sideTitleLine", s, 264, 305, 3576, 305, 0xFFFFFFFF, 120, 2.0)
    b.image("sideBrand", s, b.tl(3576 - SIDE_BRAND_W, 230 - SIDE_BRAND_W * 760 / 3000 / 2 - 15, SIDE_BRAND_W, SIDE_BRAND_W * 760 / 3000), BRAND_TEX, 0xFFE6E6E6, 150)
    b.line("sideDivider", s, 2160, 350, 2160, 1910, 0xFFFFFFFF, 160, 2.0)
    for key, x, body, glow in (("W", 680, WLF_COL, WLF_GLOW), ("S", 1420, SER_COL, SER_GLOW)):
        fx = x - 80
        b.rect(f"frameBg{key}", s, b.tl(fx, 470, 680, 1290), INTRO_BG, 235)   # near-opaque: the corner light never washes over a card or its figure
        b.frame(f"frame{key}", s, b.tl(fx, 470, 680, 1290), 0xFFE6E6E6, 210, 3.0)
        _figure(b, s, key, fx + 20, 540, body, glow)
    b.text("sideName", s, b.tl(2230, 340, 1300, 100), "WLF", 66, 0xFFE6E6E6, face="Default", tracking=4)
    b.text("sideDesc", s, b.tl(2230, DESC_Y, DESC_W, DESC_H), WLF_DESC, 48, 0xFFE6E6E6, multiline=1, valign=0)
    b.text("sideWarn", s, b.tl(2230, WARN_Y, DESC_W, 200), WARNING, 48, RED_TEXT, multiline=1, valign=0)
    b.text("sideHint", s, b.tl(2230, 1890, 900, 70), "A / D  TO SWITCH", 38, 0xFF9A9A9A, tracking=4)
    # pad version of the hint (controller parity): the engine's own bumper glyphs (menu:prev / menu:next resolve to LB / RB, L1 / R1 on the pad in use) -
    # t2r-ext shows this group instead of sideHint while the last input was a pad
    ph = b.group("sideHintPad", s, b.tl(2230, 1890, 900, 70), visible=0)["guid"]
    b.image("sideHintPrev", ph, b.tl(0, 7, 56, 56), "menu:prev", 0xFFFFFFFF)
    b.image("sideHintNext", ph, b.tl(70, 7, 56, 56), "menu:next", 0xFFFFFFFF)
    b.text("sideHintPadTx", ph, b.tl(150, 0, 750, 70), "TO SWITCH", 38, 0xFF9A9A9A, tracking=4)
    b.image("sideSelectIcon", s, b.tl(3270, 1898, 56, 56), "menu:select", 0xFFFFFFFF)
    b.text("sideSelectText", s, b.tl(3350, 1890, 300, 70), "SELECT", 46, 0xFFE6E6E6, tracking=4)

    # --- the clan end screens (won / lost, t2r-ext clanend.c): key art + roll call, then the rank page
    import clanend_widgets
    clanend_widgets.add_end(b, a)

    _enter_cover(b, a)
    w = {k: copy.deepcopy(v) for k, v in main.items() if k != "items"}
    w["items"] = b.items
    return w


def _enter_cover(b, anim_guid):
    """t2rEnter: a full-screen black rect, topmost child of the page's anim-group, alpha 0 (entry hand-off). The UI sits above the 3D scene, so this is a real
    cover: t2r-ext (ms_fade_tick, ent_*) sets it to 1 while the page is pushed under the held black, releases the native black, then fades it to 0 over 0.7 s: the world
    and the page come up from black on ONE timeline. Hidden (alpha 0) the rest of the time."""
    it = b.rect("t2rEnter", anim_guid, b.bleed(), 0xFF000000, 0)
    it["depth"] = 99.0
    return it


def add_enter_cover(main):
    """to1/main-menu: the same cover (the first page of the entry when a clan side exists)."""
    if any(i["name"] == "t2rEnter" for i in main["items"]):
        return 0
    t, _, _ = _templates(main)
    anim = next(i for i in main["items"] if i["name"] == "anim-group")
    b = Builder(t)
    _enter_cover(b, anim["guid"])
    main["items"].extend(b.items)
    return 1


PANEL_SCALE = 0.78            # the clanPanel group is built at 1120 x 510 and scaled by this (t2r-ext CLAN_SCALE)
PANEL_H = 540                 # unscaled box height (was 510): more air under NEEDED PER DAY
CLAN_PERSON_ICON = "streaming/t2r/icons/fig-us.png"        # = the team figure under the in-match radar (make_icons.fig_icon("us"))
CLAN_SUPPLY_ICON = "streaming/t2r/icons/hud-supplies.png"  # = the in-match SUPPLIES counter glyph (make_icons.hud_counter_icon("supplies"))
PANEL_X, PANEL_Y = 176, 1369  # left-aligned with the buttons, directly below QUIT (one menu-item pitch under it; was 1520)
MENU_SHADE = "streaming/t2r/clan/menu-shade.png"       # tools/models/figures/ship.py (feathered black rectangle)
SHADE_RECT = (-300, -700, 2000, 3560)                  # x, y, w, h: the left column + the clan panel, feathered all round


def add_menu_shade(main, page=None):
    """Gradient backdrop behind the MP menu's left column: the lowest-depth child of anim-group.
    page = another menu page built on the main menu's layout (to1/find-match-menu): the same shade goes there."""
    t, _, _ = _templates(main)
    page = page or main
    anim = next(i for i in page["items"] if i["name"] == "anim-group")
    if any(i["name"] == "menuShade" for i in page["items"]):
        return 0
    b = Builder(t)
    it = b.image("menuShade", anim["guid"], b.tl(*SHADE_RECT), MENU_SHADE, 0xFFFFFFFF, 255, depth=-1.0)
    it["depth"] = -1.0
    at = next(k for k, i in enumerate(page["items"]) if i["name"] == "gameTitle")
    page["items"][at:at] = b.items
    return 1


def _feed_group(b, anim_guid):
    """clan feed: one 2013-style clan message at a time in the strip above the footer separator. t2r-ext feed_tick sets
    feedText, scales feedShade in x to the sentence width (pivot is the left edge) and fades the whole group (alpha). Hidden until the ext
    shows it. The same group sits on every page where that strip is free (FEED_PAGES; re/clan-feed-pages.md)."""
    fg = b.group("clanFeed", anim_guid, b.tl(FEED_X, FEED_Y, FEED_BOX_W, FEED_H), visible=0, depth=4.4)["guid"]
    b.image("feedShade", fg, b.tl(0, 0, FEED_SHADE_W0, FEED_H), FEED_SHADE, 0xFFFFFFFF, 255)
    b.text("feedText", fg, b.tl(FEED_PAD, (FEED_H - FEED_TXT_H) / 2, FEED_BOX_W - FEED_PAD, FEED_TXT_H), "", FEED_PT, 0xFFE6E6E6,
           tracking=FEED_TRACK)


# pages that get the feed group besides the main menu / find match (which add_main_panel handles). Every one has the strip y 1880..1977
# free (panel bottoms: GEAR UP pickers 1880, leaderboard 1860, map select 1880); keep in step with t2r-ext feed_page_ok.
FEED_PAGES = ("leaderboard", "map-select")      # none of the GEAR UP pages


def add_feed_pages(main, wdir):
    """Add anim-group.clanFeed to the FEED_PAGES widget files; returns how many pages got it."""
    t, _, _ = _templates(main)
    n = 0
    for name in FEED_PAGES:
        path = os.path.join(wdir, "to1", name + ".widget.json")
        if not os.path.exists(path):
            continue
        page = json.load(open(path, encoding="utf-8"))
        if any(i["name"] == "clanFeed" for i in page["items"]):
            continue
        anim = next(i for i in page["items"] if i["name"] == "anim-group")
        b = Builder(t)
        _feed_group(b, anim["guid"])
        page["items"].extend(b.items)
        json.dump(page, open(path, "w", encoding="utf-8"), indent=4)
        n += 1
    return n


def add_main_panel(main, page=None):
    """clanPanel group on to1/main-menu (hidden; t2r-ext shows and fills it), bottom left, scaled by PANEL_SCALE
    (every size / offset below is in the unscaled 1120 x 510 design; t2r-ext moves the dots with R and mid * CLAN_SCALE)."""
    t, _, _ = _templates(main)
    page = page or main                  # to1/find-match-menu gets the same panel (t2r-ext fills whichever page is on top)
    anim = next(i for i in page["items"] if i["name"] == "anim-group")
    if any(i["name"] == "clanPanel" for i in page["items"]):
        return 0
    S = PANEL_SCALE
    b = Builder(t)

    def tl(x, y, w, h):
        return b.tl(x * S, y * S, w * S, h * S)

    def ctr(cx, cy, w, h):
        return b.ctr(cx * S, cy * S, w * S, h * S)
    PW, PH = 1120, PANEL_H
    p = b.group("clanPanel", anim["guid"], b.tl(PANEL_X, PANEL_Y, PW * S, PH * S), visible=0, depth=4.5)["guid"]
    b.image("clanBlur", p, b.fill(), "general-textures/blur-background.png", 0xFFFFFFFF, 255)
    b.rect("clanBg", p, b.fill(), 0xFF000000, 150)
    b.line("clanLineL", p, 0, 0, 0, PH * S, 0xFFFFFFFF, 130, 2.0)
    b.line("clanLineR", p, PW * S, 0, PW * S, PH * S, 0xFFFFFFFF, 130, 2.0)
    b.text("clanCount", p, tl(44, 30, 640, 80), "5 SURVIVORS", 52 * S, 0xFFE6E6E6, tracking=4 * S)
    # the REAL icons: the survivor figure is the in-match team figure under the radar (currency-hud teamFigs "fig-us"),
    # the supply glyph is the in-match SUPPLIES counter canister (hud-supplies, the 2013 net.pak icon-supplies texture). t2r-ext
    # panel_tick sets both by path again (the static path alone is not trusted on this page, cf. side_images).
    b.image("clanPerson", p, tl(60, 140, 85, 170), CLAN_PERSON_ICON, 0xFFFFFFFF, 255, scaleMode="StretchAspect")
    b.text("clanHealthy", p, tl(176, 138, 520, 70), "HEALTHY: 5", 48 * S, HEALTHY, tracking=3 * S)
    b.text("clanHungry", p, tl(176, 222, 520, 70), "HUNGRY: 0", 48 * S, HUNGRY, tracking=3 * S)
    b.text("clanSick", p, tl(176, 306, 520, 70), "SICK: 0", 48 * S, SICK, tracking=3 * S)
    b.image("clanSupply", p, tl(214, 405, 72, 72), CLAN_SUPPLY_ICON, SUPPLY_BLUE, 255, scaleMode="StretchAspect")
    b.text("clanNeeded", p, tl(298, 405, 760, 72), "NEEDED PER DAY: 9", 44 * S, 0xFFE6E6E6, tracking=3 * S)
    # (the "OPEN THE CLAN" hint is gone - the CLAN row of the menu list opens the in-game CLAN page, modepick_widgets.add_clan_row)
    c = b.group("clanCircle", p, tl(720, 70, CIRCLE, CIRCLE))["guid"]
    b.image("clanCircleSoft", c, ctr(CIRCLE / 2, CIRCLE / 2, CIRCLE * 1.25, CIRCLE * 1.25),
            "hud/player-menu/gradient/radial-gradient.png", 0xFF9A9A9A, 90)
    b.ellipse("clanCircleBg", c, ctr(CIRCLE / 2, CIRCLE / 2, CIRCLE, CIRCLE), 0xFF6E6E6E, 60)
    for k in range(MAX_DOTS):
        d = b.group(f"clanDot{k}", c, ctr(CIRCLE / 2, CIRCLE / 2, DOT, DOT), visible=0)["guid"]
        for suf, argb in (("H", HEALTHY), ("U", HUNGRY), ("S", SICK)):
            b.ellipse(f"clanDot{k}{suf}", d, b.fill(), argb, 255)
    # mission strip: the loading screen's MISSION block (name, x/y count, day, tier progress) as a strip glued under the clan
    # box: same width, same blur / black / side-line style, a thin rule where it joins the box. Group "clanMission" sits in page units
    # (not scaled), hidden until t2r-ext mission_strip_tick fills it (it stays hidden while no mission runs).
    mg = b.group("clanMission", anim["guid"], b.tl(PANEL_X, MIS_Y, MIS_W, MIS_H), visible=0, depth=4.5)["guid"]
    b.image("misBlur", mg, b.fill(), "general-textures/blur-background.png", 0xFFFFFFFF, 255)
    b.rect("misBg", mg, b.fill(), 0xFF000000, 150)
    b.line("misLineL", mg, 0, 0, 0, MIS_H, 0xFFFFFFFF, 130, 2.0)
    b.line("misLineR", mg, MIS_W, 0, MIS_W, MIS_H, 0xFFFFFFFF, 130, 2.0)
    b.line("misRule", mg, MIS_PAD, 0, MIS_W - MIS_PAD, 0, 0xFFFFFFFF, 90, 2.0)
    b.text("misName", mg, b.tl(MIS_PAD, MIS_TXT_Y, 450, 48), "DOWN ENEMIES", MIS_PT, 0xFFE6E6E6, tracking=MIS_TRACK)
    b.text("misCount", mg, b.tl(MIS_W - MIS_PAD - 340, MIS_TXT_Y, 340, 48), "0/3  DAY 1/3", MIS_PT, 0xFFE6E6E6, align=2, tracking=MIS_TRACK)
    b.rect("misBarBg", mg, b.tl(MIS_PAD, MIS_BAR_Y, MIS_W - 2 * MIS_PAD, MIS_BAR_H), 0xFF6E6E6E, 90)
    b.rect("misBarFill", mg, b.tl(MIS_PAD, MIS_BAR_Y, MIS_W - 2 * MIS_PAD, MIS_BAR_H), SUPPLY_BLUE, 255)   # t2r-ext scales it in x (left pivot)
    _feed_group(b, anim["guid"])
    at = next(k for k, i in enumerate(page["items"]) if i["name"] == "versionText")
    page["items"][at:at] = b.items
    return 1


# clan feed geometry (page units, 3840 x 2160). Box (panel) bottom = PANEL_Y + PANEL_H * PANEL_SCALE = 1790.2, or 1914.2 with the mission strip;
# the footer separator (main-menu footerLine) is the line y = 1980 from x = 180. The feed text starts exactly at x = 180 (FEED_X + FEED_PAD)
# and its centre sits midway between the box bottom and the separator; t2r-ext feed_tick moves the group between the two cases.
SEP_X, SEP_Y = 180, 1980
FEED_H = 90
FEED_PAD = 20                     # shade lead: the shade starts this far left of the text (was 34, then 6 with a hard edge)
FEED_X = SEP_X - FEED_PAD         # the shade box (soft left fade) starts FEED_PAD left of the separator, the text at x 180
BOX_BOTTOM = PANEL_Y + PANEL_H * PANEL_SCALE          # no mission
FEED_Y = (BOX_BOTTOM + SEP_Y) / 2 - FEED_H / 2        # static default = no mission (t2r-ext moves it while the strip shows)
# mission strip geometry (page units): directly under the panel, same x / width (PW * PANEL_SCALE = 873.6)
MIS_Y, MIS_W, MIS_H = BOX_BOTTOM, 874, 124
MIS_PAD = 34
MIS_PT, MIS_TRACK = 34, 2.5       # = the panel's 44 * PANEL_SCALE text size
MIS_TXT_Y, MIS_BAR_Y, MIS_BAR_H = 20, 84, 10
FEED_BOX_W = 2600                 # widest line the group holds (t2r-ext truncates longer messages)
FEED_TXT_H = 56
FEED_PT, FEED_TRACK = 30, 1.5     # = t2r-ext FEED_PT / FEED_TRACK
FEED_SHADE_W0 = 1000              # unscaled shade width; t2r-ext FEED_SHADE_W0 scales it to the sentence
FEED_SHADE = "streaming/t2r/clan/feed-shade.png"       # tools/models/figures/ship.py make_feed


SUPPLY_ICON = "streaming/t2r/icons/supply.png"       # tools/models/make_icons.supply_icon (2013 cyan box)


FIG_ICON = "streaming/t2r/icons/"
HUD_SHIFT_U = 72.0                  # everything top-left moves down 10 % of the screen height (72 of 720 units, 216 of 2160 px)
FIG_CX, FIG_TOP = 106.0, 197.0 + HUD_SHIFT_U       # 1280x720 units: centre under the radar (player arrow), top of the figure rects
# 2013 inset (wtf.png): radar ~175 px, figure ~33 px tall (0.19 radar), pitch ~20.5 px (0.117), team centres
# ~36 px apart. Our radar is ~150 units across (225 px at 1080p): figure ~28 units, pitch 17.5, centres 31.
# The image widget fits the icon into the rect keeping its aspect, so the rect = the icon (52 x 104 at 4K).
# HEALTH-UI MAPPING (hud-ref/uiref.png = 2013, uiref2.png = TLOU2): the 2013 health ring is ~7.0 % of the screen width,
# TLOU2's ~4.8 %, so 2013 sizes (as a fraction of the screen) x K = 0.69 give ours; 2013 shot (1919 px wide): figure 47 px tall, pitch 29 px
# -> 21.6 / 13.3 units of 1280x720, gap between the teams 8.7. (The radar is the engine's own: it keeps TLOU2's margin, so the row sits
# right under it, top = radar bottom 182 + 6.)
HUD_K = 0.69
# In game (uiref3.png) the figures came out too small against the radar. Every element is now sized by the RATIOS of the
# 2013 shots (2013UI.png: radar D 240 px, figure 45 tall / pitch 29, team gap 48 -> 19 extra, timer cap 24 / width 75, lives 17 cap 28,
# 04 cap 17) times OUR radar (D = 150 units): figure 0.19 D, pitch 0.12 D, team gap 0.08 D.
RADAR_D_U = 150.0
TF_BIG = 1.15      # figures 15 % larger (row stays centred on FIG_CX, spacing scales with them)
TF_W, TF_H, TF_PITCH, TF_GAP = (v * RADAR_D_U * TF_BIG for v in (0.095, 0.19, 0.12, 0.08))


# ------------------------------------------------------------------ in-match pause menu (to1/pause-menu): match clock + mission tracker
# Page units 3840 x 2160 (the page root is fitted into the window: at 21:9 it is pillarboxed, so the layout is the same at every aspect).
# Existing rects (stock pause page): title MENU x 180..1080 y 135..255, menu list x 180..1180 y 300..620, score banner Reference centred on
# x 1920 (1500 wide, y 242..602), card / scoreboard x 180..3660 y 753..1771, button legend right edge 3680 (bottom).
PZ_TIMER_W, PZ_TIMER_H, PZ_TIMER_CY = 560, 150, 155          # top centre: x 1640..2200, y 80..230 (the banner rect starts at 242)
PZ_TIMER_PT = 80                                             # the HUD clock is 52 pt; the old pause clock sat inside the banner
PZ_MIS_W, PZ_MIS_H = 874, 250                                # = the main-menu strip width
PZ_MIS_R, PZ_MIS_Y = 3660, 135                               # right edge = the card's right edge, top = the MENU title's top
PZ_MIS_PAD = 34
PZ_MIS_BAR_Y, PZ_MIS_BAR_H = 218, 10


def pause_rects():
    """{name: (x, y, w, h)} in page units, for the offline placement check."""
    return {"pauseTimer": (1920 - PZ_TIMER_W / 2, PZ_TIMER_CY - PZ_TIMER_H / 2, PZ_TIMER_W, PZ_TIMER_H),
            "pauseMission": (PZ_MIS_R - PZ_MIS_W, PZ_MIS_Y, PZ_MIS_W, PZ_MIS_H)}


def add_pause_widgets(wdir):
    """to1/pause-menu: group pauseTimer (big match clock, top centre; text pzTime + hidden twin pzTimeB) and group pauseMission (the loading
    screen's MISSION block, top right). Both start hidden: t2r-ext pause_mission_tick fills and shows them (and hides the banner's own small
    clock, which winmm rewrites on every call)."""
    path = os.path.join(wdir, "to1", "pause-menu.widget.json")
    if not os.path.exists(path):
        return 0
    page = json.load(open(path, encoding="utf-8"))
    if any(i["name"] == "pauseMission" for i in page["items"]):
        return 0
    main = json.load(open(os.path.join(wdir, "to1", "main-menu.widget.json"), encoding="utf-8"))
    t, _, _ = _templates(main)
    anim = next(i for i in page["items"] if i["name"] == "anim-group")
    b = Builder(t)
    TEXT = 0xFFE6E6E6
    tx, ty, tw, th = pause_rects()["pauseTimer"]
    g = b.group("pauseTimer", anim["guid"], b.tl(tx, ty, tw, th), visible=0, depth=4.5)["guid"]
    b.image("pzBlur", g, b.fill(), "general-textures/blur-background.png", 0xFFFFFFFF, 255)
    b.rect("pzBg", g, b.fill(), 0xFF000000, 150)
    b.line("pzLineL", g, 0, 0, 0, th, 0xFFFFFFFF, 130, 2.0)
    b.line("pzLineR", g, tw, 0, tw, th, 0xFFFFFFFF, 130, 2.0)
    b.text("pzTime", g, b.tl(0, 6, tw, th - 12), "00:00", PZ_TIMER_PT, TEXT, align=1, tracking=4)
    b.text("pzTimeB", g, b.tl(0, 6, tw, th - 12), "00:00", PZ_TIMER_PT, TEXT, align=1, tracking=4, visible=0)   # twin (db_text_w)
    mx, my, mw, mh = pause_rects()["pauseMission"]
    m = b.group("pauseMission", anim["guid"], b.tl(mx, my, mw, mh), visible=0, depth=4.5)["guid"]
    b.image("pmBlur", m, b.fill(), "general-textures/blur-background.png", 0xFFFFFFFF, 255)
    b.rect("pmBg", m, b.fill(), 0xFF000000, 150)
    b.line("pmLineL", m, 0, 0, 0, mh, 0xFFFFFFFF, 130, 2.0)
    b.line("pmLineR", m, mw, 0, mw, mh, 0xFFFFFFFF, 130, 2.0)
    # the loading screen's block (matchflow_widgets.build_loading: MISSION: head 54 pt, rule, two 42 pt lines), x 0.8
    b.text("pmHead", m, b.tl(PZ_MIS_PAD, 14, 600, 70), "MISSION:", 43, TEXT, tracking=4)
    b.line("pmLine1", m, PZ_MIS_PAD - 4, 88, mw - PZ_MIS_PAD + 4, 88, 0xFFFFFFFF, 130, 2.0)
    b.text("pmMis1", m, b.tl(PZ_MIS_PAD, 100, mw - 2 * PZ_MIS_PAD, 54), "", 34, TEXT, tracking=2)   # no placeholder mission text
    b.text("pmMis2", m, b.tl(PZ_MIS_PAD, 154, mw - 2 * PZ_MIS_PAD, 54), "", 34, TEXT, tracking=2)
    b.rect("pmBarBg", m, b.tl(PZ_MIS_PAD, PZ_MIS_BAR_Y, mw - 2 * PZ_MIS_PAD, PZ_MIS_BAR_H), 0xFF6E6E6E, 90)
    b.rect("pmBarFill", m, b.tl(PZ_MIS_PAD, PZ_MIS_BAR_Y, mw - 2 * PZ_MIS_PAD, PZ_MIS_BAR_H), SUPPLY_BLUE, 255)   # t2r-ext scales it in x
    at = next(k for k, i in enumerate(page["items"]) if i["name"] == "versionText")
    page["items"][at:at] = b.items
    json.dump(page, open(path, "w", encoding="utf-8"), indent=4)
    return len(b.items)



def add_team_figs(wdir):
    """to1/currency-hud: group "teamFigs" with 8 rows figU0-3 (our team, blue, k=0 nearest the centre,
    growing left) / figE0-3 (enemy, red, growing right); each row has leaves <row>A alive (also downed)
    and <row>X dead (the dimmed figure with an x). t2r-ext (feature_team_figures) toggles the visibility."""
    path = os.path.join(wdir, "to1", "currency-hud.widget.json")
    w = json.load(open(path, encoding="utf-8"))
    items = w["items"]
    if any(i["name"] == "teamFigs" for i in items):
        return 0
    root = next(i for i in items if i["name"] == "root")
    grp = next(i for i in items if i["name"] == "partsRow")
    img = next(i for i in items if i["name"] == "partsRowIcon")
    U = 3.0                                       # page units per 1280x720 unit

    def group(name, parent, x, y, wd, ht):
        g = copy.deepcopy(grp)
        g.update(guid=t2guid.guid(), name=name, parent=parent, visible=1 if name == "teamFigs" else 0)
        g.update({"anchorMinN.x": 0.0, "anchorMinN.y": 0.0, "anchorMaxN.x": 0.0, "anchorMaxN.y": 0.0,
                  "pivotAs.x": x, "pivotAs.y": y, "rectSizeDelta.width": wd, "rectSizeDelta.height": ht})
        return g
    top = group("teamFigs", root["guid"], 0.0, 0.0, 3840.0, 2160.0)
    new = [top]
    for side, tag, sign in (("us", "U", -1), ("en", "E", 1)):
        for k in range(4):
            if sign < 0:
                x = FIG_CX - TF_GAP / 2 - TF_W - k * TF_PITCH
            else:
                x = FIG_CX + TF_GAP / 2 + k * TF_PITCH
            row = group(f"fig{tag}{k}", top["guid"], x * U, FIG_TOP * U, TF_W * U, TF_H * U)
            new.append(row)
            for suf, icon, vis in (("A", f"fig-{side}", 1), ("X", f"fig-x-{side}", 0)):
                c = copy.deepcopy(img)
                c.update(guid=t2guid.guid(), name=f"fig{tag}{k}{suf}", parent=row["guid"], visible=vis,
                         path=FIG_ICON + icon + ".png", depth=0.0)
                c.update({"anchorMinN.x": 0.0, "anchorMinN.y": 0.0, "anchorMaxN.x": 1.0, "anchorMaxN.y": 1.0,
                          "pivotN.x": 0.0, "pivotN.y": 0.0, "pivotAs.x": 0.0, "pivotAs.y": 0.0,
                          "rectSizeDelta.width": 0.0, "rectSizeDelta.height": 0.0})
                new.append(c)
    sep = group("figSep", top["guid"], (FIG_CX - TF_W / 4) * U, FIG_TOP * U, TF_W / 2 * U, TF_H * U)
    c = copy.deepcopy(img)
    c.update(guid=t2guid.guid(), name="figSepA", parent=sep["guid"], visible=1, path=FIG_ICON + "fig-colon.png", depth=0.0)
    c.update({"anchorMinN.x": 0.0, "anchorMinN.y": 0.0, "anchorMaxN.x": 1.0, "anchorMaxN.y": 1.0,
              "pivotN.x": 0.0, "pivotN.y": 0.0, "pivotAs.x": 0.0, "pivotAs.y": 0.0,
              "rectSizeDelta.width": 0.0, "rectSizeDelta.height": 0.0})
    new += [sep, c]
    items.extend(new)
    json.dump(w, open(path, "w", encoding="utf-8"), indent=4)
    return 1


# 2013 in-match bottom-left counters (re/factions2013/hud-ref/gearandsupplies.png): PARTS = green cog + green number,
# SUPPLIES = blue canister + blue number, NO plate behind them. Icons = the 2013 net.pak textures (make_icons.hud_counter_icon);
# colours read off the reference (brightest cog / canister pixels, (124,180,148) / (84,136,156)).
HUD_PARTS_GREEN = 0xFF7CB494
HUD_SUPPLY_BLUE = 0xFF54889C
# the radar's inner-edge vignette (make_icons.radar_vignette): 450 px = the radar disc (r 75 units x 3) centred on it
RADAR_CX, RADAR_CY, RADAR_D = 104.0 * 3, (107.0 + HUD_SHIFT_U) * 3, 450.0   # (winmm's own radar glyphs are moved by the same HUD_SHIFT_U in t2r-ext radar_shift)
RADAR_GLOW = 600.0                 # make_icons.radar_glow size: the disc + 75 px soft halo per side


def add_hud_counters(wdir):
    path = os.path.join(wdir, "to1", "currency-hud.widget.json")
    w = json.load(open(path, encoding="utf-8"))
    items = w["items"]
    by = {i["name"]: i for i in items}
    if "radarVig" in by:
        return 0
    n = 0
    for pre, icon, argb in (("parts", "hud-parts", HUD_PARTS_GREEN), ("supply", "hud-supplies", HUD_SUPPLY_BLUE)):
        g = by.get(pre + "Gradient")
        if g:
            if pre == "parts":       # one soft dark rectangle behind BOTH rows (fades out toward every edge), replaces the old plates
                g.update(path=FIG_ICON + "hud-counter-panel.png", visible=1, **{"pivotAs.x": -174.0, "pivotAs.y": 41.0,
                         "rectSizeDelta.width": 528.0, "rectSizeDelta.height": 385.0, "tint.start": 0xFFFFFFFF, "tint.end": 0xFFFFFFFF,
                         "color.a": 255, "scaleMode": "Stretch"})
            else:
                g["visible"] = 0
            n += 1
        ic = by.get(pre + "RowIcon")
        if ic:
            ic["path"] = FIG_ICON + icon + ".png"
            ic["tint.start"] = ic["tint.end"] = argb
            ic["rectSizeDelta.width"] = ic["rectSizeDelta.height"] = 56.0      # 2013 ratio: icon ~0.11 x the radar diameter (was 88)
            # centre the glyph on its number's cap-height centre (digits sit ~14 px above the line centre); both glyphs are centred in
            # their 64 px textures, so the same x puts the cog and the canister on one vertical axis (the old +13 px
            # canister shift made the two icons look offset from each other)
            ic["pivotAs.y"] = -14.0
            ic["pivotAs.x"] = 0.0
            n += 1
        am = by.get(pre + "Amount")
        if am:
            am["tint.start"] = am["tint.end"] = argb
            am["pivotAs.x"] = 72.0
            am["pointSize"] = 54
            n += 1
    root = next(i for i in items if i["name"] == "root")
    grp = by["partsRow"]
    img = by["partsRowIcon"]
    v = copy.deepcopy(grp)
    v.update(guid=t2guid.guid(), name="radarVig", parent=root["guid"], visible=1)
    v.update({"anchorMinN.x": 0.0, "anchorMinN.y": 0.0, "anchorMaxN.x": 0.0, "anchorMaxN.y": 0.0,
              "pivotAs.x": RADAR_CX - RADAR_D / 2, "pivotAs.y": RADAR_CY - RADAR_D / 2,
              "rectSizeDelta.width": RADAR_D, "rectSizeDelta.height": RADAR_D})
    c = copy.deepcopy(img)
    c.update(guid=t2guid.guid(), name="radarVigImg", parent=v["guid"], visible=1, path=FIG_ICON + "radar-vignette.png", depth=0.0)
    c.update({"anchorMinN.x": 0.0, "anchorMinN.y": 0.0, "anchorMaxN.x": 1.0, "anchorMaxN.y": 1.0,
              "pivotN.x": 0.0, "pivotN.y": 0.0, "pivotAs.x": 0.0, "pivotAs.y": 0.0,
              "rectSizeDelta.width": 0.0, "rectSizeDelta.height": 0.0, "tint.start": 0xFFFFFFFF, "tint.end": 0xFFFFFFFF})
    # the soft halo just outside the disc (make_icons.radar_glow, 600 px: the 450 px disc + 75 px of falloff), drawn first = behind the vignette
    gl = copy.deepcopy(v)
    gl.update(guid=t2guid.guid(), name="radarGlow", parent=root["guid"], visible=1)
    gl.update({"pivotAs.x": RADAR_CX - RADAR_GLOW / 2, "pivotAs.y": RADAR_CY - RADAR_GLOW / 2,
               "rectSizeDelta.width": RADAR_GLOW, "rectSizeDelta.height": RADAR_GLOW})
    gc = copy.deepcopy(c)
    gc.update(guid=t2guid.guid(), name="radarGlowImg", parent=gl["guid"], path=FIG_ICON + "radar-glow.png")
    items.extend([gl, gc, v, c])
    n += add_hud_panels(items, root, grp, img)
    json.dump(w, open(path, "w", encoding="utf-8"), indent=4)
    return n + 2


# Soft dark panels behind the in-match HUD elements, the style of the PARTS / SUPPLIES panel (make_icons.soft_panel:
# ~46 % black in the middle, fading to 0 toward every edge, no border; the one texture is stretched to each size, so the fade zone
# is 34 % of each side). Each is sized to its element's measured box plus ~18 % padding per dimension. 4K page px:
#   figures row         from the TF_* constants (centre FIG_CX, top FIG_TOP)
#   health + weapon     ring (3360..3563 x 1850..2025) + weapon block (3207..3435 x 1852..1957), read off uiref2.png (TLOU2's own HUD)
#   armour icons        armorHudHelm / armorHudVest (ARMOR_HUD)
#   melee pips          the durability dashes (3450, 2102) and the free one-tap pips (MELEE_FREE_*)
# (the timer and the lives row are panels in to1/score-banner, matchflow_widgets.remake_score_banner; the radar keeps its vignette)
HUD_PANEL_PAD = 0.18
HUD_PANEL_ICON = FIG_ICON + "hud-counter-panel.png"


def hud_panel_rects():
    """[(name, cx, cy, w, h)] of content boxes (4K px) before padding. Only OUR widgets get a panel (not the game's own health /
    weapon HUD, nor the armour icons / melee pips sitting on it)."""
    U = 3.0
    left = FIG_CX - TF_GAP / 2 - TF_W - 3 * TF_PITCH
    right = FIG_CX + TF_GAP / 2 + 3 * TF_PITCH + TF_W
    return [("pnlFigures", (left + right) / 2 * U, (FIG_TOP + TF_H / 2) * U, (right - left) * U, TF_H * U)]


# per panel: (padding x, padding y) as a fraction of the content size per side, and how far the fade reaches INTO the content (fraction of
# the content size): the figures and the lives panels fade much softer (they fall off much softer; the lives one was too sharp)
HUD_PANEL_SOFT = {"pnlFigures": (0.22, 0.75, 0.30), "pnlLives": (0.45, 0.65, 0.30), "pnlTimer": (0.35, 1.10, 0.25)}


def hud_panel_geom(name, wd, ht):
    """-> (panel w, panel h, fade x, fade y) in 4K px for a content box wd x ht."""
    px, py, inner = HUD_PANEL_SOFT.get(name, (HUD_PANEL_PAD, HUD_PANEL_PAD, 0.0))
    pw, ph = wd * (1 + 2 * px), ht * (1 + 2 * py)
    return pw, ph, min(pw / 2, max(28.0, wd * (px + inner))), min(ph / 2, max(28.0, ht * (py + inner)))


def add_hud_panels(items, root, grp, img):
    """group "hudPanels" first under root (drawn behind the HUD widgets) with the panel images."""
    top = copy.deepcopy(grp)
    top.update(guid=t2guid.guid(), name="hudPanels", parent=root["guid"], visible=1)
    top.update({"anchorMinN.x": 0.0, "anchorMinN.y": 0.0, "anchorMaxN.x": 0.0, "anchorMaxN.y": 0.0,
                "pivotAs.x": 0.0, "pivotAs.y": 0.0, "rectSizeDelta.width": 3840.0, "rectSizeDelta.height": 2160.0})
    new = [top]
    for name, cx, cy, wd, ht in hud_panel_rects():
        pw, ph = hud_panel_geom(name, wd, ht)[:2]
        c = copy.deepcopy(img)
        c.update(guid=t2guid.guid(), name=name, parent=top["guid"], visible=1, path=FIG_ICON + "hud-panel-" + name + ".png", depth=0.0,
                 scaleMode="Stretch")
        c.update({"anchorMinN.x": 0.0, "anchorMinN.y": 0.0, "anchorMaxN.x": 0.0, "anchorMaxN.y": 0.0,
                  "pivotN.x": 0.5, "pivotN.y": 0.5, "pivotAs.x": cx, "pivotAs.y": cy,
                  "rectSizeDelta.width": pw, "rectSizeDelta.height": ph,
                  "tint.start": 0xFFFFFFFF, "tint.end": 0xFFFFFFFF, "color.a": 255})
        new.append(c)
    at = next(k for k, i in enumerate(items) if i["name"] == "root") + 1
    items[at:at] = new
    return len(new)


# 2013 armour hit marker (re/armor-feedback-2013.md): 4 dots on the reticle's line, the image
# (make_icons.armor_dots_icon, DOTS_W x DOTS_H 4K px) centred on the reticle = the screen centre.
ARMOR_DOTS_W, ARMOR_DOTS_H = 136.0 / 3, 16.0 / 3                  # 1280x720 units
ARMOR_HIT_X, ARMOR_HIT_Y = 640.0 - ARMOR_DOTS_W / 2, 360.0 - ARMOR_DOTS_H / 2


def add_armor_hit(wdir):
    """to1/currency-hud: group "armorHit" (full page) > row "armorHitRow" (hidden) > image
    "armorHitIcon" (streaming/t2r/icons/armor-dots.png, make_icons.armor_dots_icon) centred on the
    reticle. t2r-ext (armor_hit_feedback) shows the row 0.5 s when our hit was absorbed by the
    target's armour (2013: four dots beside the reticle, two each side; no helmet icon)."""
    path = os.path.join(wdir, "to1", "currency-hud.widget.json")
    w = json.load(open(path, encoding="utf-8"))
    items = w["items"]
    if any(i["name"] == "armorHit" for i in items):
        return 0
    root = next(i for i in items if i["name"] == "root")
    grp = next(i for i in items if i["name"] == "partsRow")
    img = next(i for i in items if i["name"] == "partsRowIcon")
    U = 3.0

    def group(name, parent, x, y, wd, ht, vis):
        g = copy.deepcopy(grp)
        g.update(guid=t2guid.guid(), name=name, parent=parent, visible=vis)
        g.update({"anchorMinN.x": 0.0, "anchorMinN.y": 0.0, "anchorMaxN.x": 0.0, "anchorMaxN.y": 0.0,
                  "pivotAs.x": x, "pivotAs.y": y, "rectSizeDelta.width": wd, "rectSizeDelta.height": ht})
        return g
    top = group("armorHit", root["guid"], 0.0, 0.0, 3840.0, 2160.0, 1)
    row = group("armorHitRow", top["guid"], ARMOR_HIT_X * U, ARMOR_HIT_Y * U, ARMOR_DOTS_W * U, ARMOR_DOTS_H * U, 0)
    c = copy.deepcopy(img)
    c.update(guid=t2guid.guid(), name="armorHitIcon", parent=row["guid"], visible=1,
             path=FIG_ICON + "armor-dots.png", depth=0.0)
    c.update({"anchorMinN.x": 0.0, "anchorMinN.y": 0.0, "anchorMaxN.x": 1.0, "anchorMaxN.y": 1.0,
              "pivotN.x": 0.0, "pivotN.y": 0.0, "pivotAs.x": 0.0, "pivotAs.y": 0.0,
              "rectSizeDelta.width": 0.0, "rectSizeDelta.height": 0.0})
    items.extend([top, row, c])
    json.dump(w, open(path, "w", encoding="utf-8"), indent=4)
    return 1


# Spawn-protection marker: a small shield at the reticle's bottom right for a shot that hit a spawn-protected enemy (replaces the armour dots there).
SHIELD_W, SHIELD_H = 64.0 / 3, 74.0 / 3                           # 1280x720 units (make_icons.SHIELD_W x SHIELD_H 4K px)
SHIELD_X, SHIELD_Y = 640.0 + 14.0, 360.0 + 12.0                   # top-left: right of and below the reticle centre


def add_spawn_shield(wdir):
    """to1/currency-hud: group "spawnShield" (full page) > row "spawnShieldRow" (hidden) > image "spawnShieldIcon"
    (streaming/t2r/icons/spawn-shield.png). t2r-ext shield_hit_draw shows the row 0.5 s (fading) per shot on a protected enemy."""
    path = os.path.join(wdir, "to1", "currency-hud.widget.json")
    w = json.load(open(path, encoding="utf-8"))
    items = w["items"]
    if any(i["name"] == "spawnShield" for i in items):
        return 0
    root = next(i for i in items if i["name"] == "root")
    grp = next(i for i in items if i["name"] == "partsRow")
    img = next(i for i in items if i["name"] == "partsRowIcon")
    U = 3.0

    def group(name, parent, x, y, wd, ht, vis):
        g = copy.deepcopy(grp)
        g.update(guid=t2guid.guid(), name=name, parent=parent, visible=vis)
        g.update({"anchorMinN.x": 0.0, "anchorMinN.y": 0.0, "anchorMaxN.x": 0.0, "anchorMaxN.y": 0.0,
                  "pivotAs.x": x, "pivotAs.y": y, "rectSizeDelta.width": wd, "rectSizeDelta.height": ht})
        return g
    top = group("spawnShield", root["guid"], 0.0, 0.0, 3840.0, 2160.0, 1)
    row = group("spawnShieldRow", top["guid"], SHIELD_X * U, SHIELD_Y * U, SHIELD_W * U, SHIELD_H * U, 0)
    c = copy.deepcopy(img)
    c.update(guid=t2guid.guid(), name="spawnShieldIcon", parent=row["guid"], visible=1,
             path=FIG_ICON + "spawn-shield.png", depth=0.0)
    c.update({"anchorMinN.x": 0.0, "anchorMinN.y": 0.0, "anchorMaxN.x": 1.0, "anchorMaxN.y": 1.0,
              "pivotN.x": 0.0, "pivotN.y": 0.0, "pivotAs.x": 0.0, "pivotAs.y": 0.0,
              "rectSizeDelta.width": 0.0, "rectSizeDelta.height": 0.0})
    items.extend([top, row, c])
    json.dump(w, open(path, "w", encoding="utf-8"), indent=4)
    return 1


# 2013 armour HUD icons above the health ring (re/armor-feedback-2013.md): centres in 4K px, placed
# off our ring (right edge ~3560, top ~1852 at 4K) like 2013's (helmet 92.7 / vest 48.1 px left of the
# ring's right edge, 30 above its top, at 1080p) scaled 0.75 to our smaller ring; sizes =
# make_icons.HUD_HELMET_SIZE / HUD_VEST_SIZE.
ARMOR_HUD = (("armorHudHelm", "armor-hud-helmet.png", 3421.0, 1807.0, 52.0, 54.0),
             ("armorHudVest", "armor-hud-vest.png", 3488.0, 1807.0, 38.0, 57.0))


def add_armor_hud(wdir):
    """to1/currency-hud: group "armorHud" (full page) > rows "armorHudHelm" / "armorHudVest" (hidden)
    > images "<row>Icon". t2r-ext feature_armor_hud shows a row while that piece is worn and pulses
    its alpha after a hit (2013)."""
    path = os.path.join(wdir, "to1", "currency-hud.widget.json")
    w = json.load(open(path, encoding="utf-8"))
    items = w["items"]
    if any(i["name"] == "armorHud" for i in items):
        return 0
    root = next(i for i in items if i["name"] == "root")
    grp = next(i for i in items if i["name"] == "partsRow")
    img = next(i for i in items if i["name"] == "partsRowIcon")

    def group(name, parent, x, y, wd, ht, vis):
        g = copy.deepcopy(grp)
        g.update(guid=t2guid.guid(), name=name, parent=parent, visible=vis)
        g.update({"anchorMinN.x": 0.0, "anchorMinN.y": 0.0, "anchorMaxN.x": 0.0, "anchorMaxN.y": 0.0,
                  "pivotAs.x": x, "pivotAs.y": y, "rectSizeDelta.width": wd, "rectSizeDelta.height": ht})
        return g
    top = group("armorHud", root["guid"], 0.0, 0.0, 3840.0, 2160.0, 1)
    new = [top]
    for name, icon, cx, cy, wd, ht in ARMOR_HUD:
        row = group(name, top["guid"], cx - wd / 2, cy - ht / 2, wd, ht, 0)
        c = copy.deepcopy(img)
        c.update(guid=t2guid.guid(), name=name + "Icon", parent=row["guid"], visible=1, path=FIG_ICON + icon, depth=0.0)
        c.update({"anchorMinN.x": 0.0, "anchorMinN.y": 0.0, "anchorMaxN.x": 1.0, "anchorMaxN.y": 1.0,
                  "pivotN.x": 0.0, "pivotN.y": 0.0, "pivotAs.x": 0.0, "pivotAs.y": 0.0,
                  "rectSizeDelta.width": 0.0, "rectSizeDelta.height": 0.0})
        new += [row, c]
    items.extend(new)
    json.dump(w, open(path, "w", encoding="utf-8"), indent=4)
    return 1


# 2013 Lone Wolf HUD (lonewolf.png): a row of the granted skills' round icons above the armour icons / health ring and "Lone Wolf Active"
# under them. Centred over the health + weapon block (3207..3563 -> 3385 at 4K). Icons (skill-<x>-hud.png, skill_icons.py): Agility,
# Sharpshooter, Sharp Ears (II only: wolfHudIcon2 is shown by t2r-ext feature_wolf_hud).
WOLF_CX, WOLF_ICON_Y, WOLF_TEXT_Y = 3385.0, 1650.0, 1738.0
WOLF_ICON, WOLF_PITCH, WOLF_TEXT_PT = 96.0, 112.0, 46
WOLF_ICONS = ("skill-agility-hud.png", "skill-sharpshooter-hud.png", "skill-ears-hud.png")


def add_wolf_hud(wdir):
    """to1/currency-hud: group "wolfHud" (full page) > rows "wolfHudIcon<k>" (hidden, image "wolfHudIcon<k>Img") and "wolfHudText"
    (hidden, Text "wolfHudTextTx" = "Lone Wolf Active", cloned from partsAmount, centred). t2r-ext feature_wolf_hud shows them while
    Lone Wolf is active (alone) and fades them."""
    path = os.path.join(wdir, "to1", "currency-hud.widget.json")
    w = json.load(open(path, encoding="utf-8"))
    items = w["items"]
    if any(i["name"] == "wolfHud" for i in items):
        return 0
    root = next(i for i in items if i["name"] == "root")
    grp = next(i for i in items if i["name"] == "partsRow")
    img = next(i for i in items if i["name"] == "partsRowIcon")
    txt = next(i for i in items if i["name"] == "partsAmount")

    def group(name, parent, x, y, wd, ht, vis):
        g = copy.deepcopy(grp)
        g.update(guid=t2guid.guid(), name=name, parent=parent, visible=vis)
        g.update({"anchorMinN.x": 0.0, "anchorMinN.y": 0.0, "anchorMaxN.x": 0.0, "anchorMaxN.y": 0.0,
                  "pivotAs.x": x, "pivotAs.y": y, "rectSizeDelta.width": wd, "rectSizeDelta.height": ht})
        return g
    fill = {"anchorMinN.x": 0.0, "anchorMinN.y": 0.0, "anchorMaxN.x": 1.0, "anchorMaxN.y": 1.0,
            "pivotN.x": 0.0, "pivotN.y": 0.0, "pivotAs.x": 0.0, "pivotAs.y": 0.0,
            "rectSizeDelta.width": 0.0, "rectSizeDelta.height": 0.0}
    top = group("wolfHud", root["guid"], 0.0, 0.0, 3840.0, 2160.0, 1)
    new = [top]
    for k, icon in enumerate(WOLF_ICONS):
        cx = WOLF_CX + (k - 1) * WOLF_PITCH
        row = group("wolfHudIcon%d" % k, top["guid"], cx - WOLF_ICON / 2, WOLF_ICON_Y - WOLF_ICON / 2, WOLF_ICON, WOLF_ICON, 0)
        c = copy.deepcopy(img)
        c.update(guid=t2guid.guid(), name=row["name"] + "Img", parent=row["guid"], visible=1, path=FIG_ICON + icon, depth=0.0,
                 scaleMode="StretchAspect")
        c.update(fill)
        c.update({"tint.start": 0xFFFFFFFF, "tint.end": 0xFFFFFFFF, "color.a": 255})
        new += [row, c]
    tw, th = 900.0, 80.0
    row = group("wolfHudText", top["guid"], WOLF_CX - tw / 2, WOLF_TEXT_Y - th / 2, tw, th, 0)
    t = copy.deepcopy(txt)
    t.update(guid=t2guid.guid(), name="wolfHudTextTx", parent=row["guid"], visible=1, text="Lone Wolf Active", cipherId="",
             pointSize=WOLF_TEXT_PT, alignH=1, alignV=1, multiline=0, depth=0.0)
    t.update(fill)
    t.update({"tint.start": 0xFFE6E6E6, "tint.end": 0xFFE6E6E6, "color.a": 255})
    new += [row, t]
    items.extend(new)
    json.dump(w, open(path, "w", encoding="utf-8"), indent=4)
    return 1


# 2013 buy suggestion (buysuggestion.png), reworked: a TEMPORARY pop-up (t2r-ext feature_buy_hint: fade in, ~4 s, fade out) centred
# vertically BETWEEN the lives counter (panel pnlLives: centre 770 + HUD_SHIFT_PX + 6, 96 high) and the parts counter (currencyGroup is bottom-anchored:
# parts row y 1860..1960 at 4K, its panel starts ~1700). Line 1: price + parts cog + the item's icon; line 2: the game's own input glyph
# for the backpack command ("gen:inventory": TAB on keyboard, the touchpad / button on a pad, resolved by the engine like the death
# screen's "gen:interact") + "TO BUY". Backdrop = buy-hint-panel.png (make_icons.buy_hint_panel: long soft fade to the right, short top / bottom).
# All coordinates are page px (3840 x 2160, y down).
BUYH_X, BUYH_W, BUYH_H = 200.0, 760.0, 170.0
BUYH_Y = ((770.0 + HUD_SHIFT_U * 3 + 6.0 + 48.0) + 1700.0) / 2 - BUYH_H / 2       # centred between the lives panel's bottom edge and the parts panel's top


def add_buy_hint(wdir):
    """to1/currency-hud: group "buyHint" (full page) > row "buyHintRow" (hidden; alpha driven by t2r-ext) > "buyHintPanel" (backdrop),
    "buyHintPrice" (green number), "buyHintCoin" (parts cog), "buyHintItemA" (armour badge) / "buyHintItemW" (weapon icon, path set
    at runtime), "buyHintKeyIcon" (gen:inventory glyph), "buyHintKey" ("TO BUY")."""
    path = os.path.join(wdir, "to1", "currency-hud.widget.json")
    w = json.load(open(path, encoding="utf-8"))
    items = w["items"]
    if any(i["name"] == "buyHint" for i in items):
        return 0
    root = next(i for i in items if i["name"] == "root")
    grp = next(i for i in items if i["name"] == "partsRow")
    img = next(i for i in items if i["name"] == "partsRowIcon")
    txt = next(i for i in items if i["name"] == "partsAmount")

    def place(c, x, y, wd, ht):
        c.update({"anchorMinN.x": 0.0, "anchorMinN.y": 0.0, "anchorMaxN.x": 0.0, "anchorMaxN.y": 0.0,
                  "pivotN.x": 0.0, "pivotN.y": 0.0, "pivotAs.x": x, "pivotAs.y": y,
                  "rectSizeDelta.width": wd, "rectSizeDelta.height": ht})

    def group(name, parent, x, y, wd, ht, vis):
        g = copy.deepcopy(grp)
        g.update(guid=t2guid.guid(), name=name, parent=parent, visible=vis)
        place(g, x, y, wd, ht)
        return g

    def image(name, parent, icon, x, y, wd, ht, argb=0xFFFFFFFF, scale="StretchAspect", **extra):
        c = copy.deepcopy(img)
        c.update(guid=t2guid.guid(), name=name, parent=parent, visible=1, path=icon, depth=0.0, scaleMode=scale, **extra)
        place(c, x, y, wd, ht)
        c.update({"tint.start": argb, "tint.end": argb, "color.a": 255})
        return c

    def text(name, parent, s, x, y, wd, ht, pt, argb):
        t = copy.deepcopy(txt)
        t.update(guid=t2guid.guid(), name=name, parent=parent, visible=1, text=s, cipherId="", pointSize=pt, alignH=0, alignV=1,
                 multiline=0, depth=0.0)
        place(t, x, y, wd, ht)
        t.update({"tint.start": argb, "tint.end": argb, "color.a": 255})
        return t
    top = group("buyHint", root["guid"], 0.0, 0.0, 3840.0, 2160.0, 1)
    row = group("buyHintRow", top["guid"], BUYH_X, BUYH_Y, BUYH_W, BUYH_H, 0)
    g = row["guid"]
    new = [top, row,
           # backdrop from the screen's left edge (x -200 = page 0) to 700 px right of the content
           image("buyHintPanel", g, FIG_ICON + "buy-hint-panel.png", -BUYH_X, -34.0, BUYH_X + BUYH_W + 300.0, BUYH_H + 68.0, 0xFFFFFFFF, "Stretch"),
           text("buyHintPrice", g, "450", 0.0, 6.0, 150.0, 80.0, 54, HUD_PARTS_GREEN),
           image("buyHintCoin", g, FIG_ICON + "hud-parts.png", 150.0, 18.0, 56.0, 56.0, HUD_PARTS_GREEN),
           image("buyHintItemA", g, FIG_ICON + "armor-hit.png", 236.0, -4.0, 92.0, 92.0),
           image("buyHintItemW", g, FIG_ICON + "armor-hit.png", 236.0, -4.0, 150.0, 92.0),
           image("buyHintKeyIcon", g, "gen:inventory", 0.0, 100.0, 120.0, 68.0, 0xFFFFFFFF, "StretchAspect", alignH=1, alignV=1,
                 slices=[0.328125] * 4),
           text("buyHintKey", g, "TO BUY", 136.0, 98.0, BUYH_W - 136.0, 72.0, 44, 0xFFE6E6E6)]
    items.extend(new)
    json.dump(w, open(path, "w", encoding="utf-8"), indent=4)
    return 1


# free one-tap pips of an upgraded melee (meleeui.png): a row under the weapon's durability pips,
# under the melee durability dashes below the health ring (bat icon row; dashes centred ~3450,2102 at 4K,
# read off re/armor/ref/ours-health-ring-1080p.png; position unverified in game)
MELEE_FREE_N, MELEE_FREE_X, MELEE_FREE_Y, MELEE_FREE_PITCH = 2, 3450.0, 2130.0, 62.0
MELEE_PIP_SIZE = (56.0, 14.0)


def add_melee_free(wdir):
    """to1/currency-hud: group "meleeHud" (full page) > rows "meleeFree<k>" (hidden) > image
    "meleeFree<k>Icon" (melee-pip.png). t2r-ext feature_melee_free_hud shows one per free one-tap of
    an upgraded melee, greyed (alpha) once spent."""
    path = os.path.join(wdir, "to1", "currency-hud.widget.json")
    w = json.load(open(path, encoding="utf-8"))
    items = w["items"]
    if any(i["name"] == "meleeHud" for i in items):
        return 0
    root = next(i for i in items if i["name"] == "root")
    grp = next(i for i in items if i["name"] == "partsRow")
    img = next(i for i in items if i["name"] == "partsRowIcon")

    def group(name, parent, x, y, wd, ht, vis):
        g = copy.deepcopy(grp)
        g.update(guid=t2guid.guid(), name=name, parent=parent, visible=vis)
        g.update({"anchorMinN.x": 0.0, "anchorMinN.y": 0.0, "anchorMaxN.x": 0.0, "anchorMaxN.y": 0.0,
                  "pivotAs.x": x, "pivotAs.y": y, "rectSizeDelta.width": wd, "rectSizeDelta.height": ht})
        return g
    top = group("meleeHud", root["guid"], 0.0, 0.0, 3840.0, 2160.0, 1)
    new = [top]
    pw, ph = MELEE_PIP_SIZE
    for k in range(MELEE_FREE_N):
        cx = MELEE_FREE_X + (k - (MELEE_FREE_N - 1) / 2.0) * MELEE_FREE_PITCH
        row = group("meleeFree%d" % k, top["guid"], cx - pw / 2, MELEE_FREE_Y - ph / 2, pw, ph, 0)
        c = copy.deepcopy(img)
        c.update(guid=t2guid.guid(), name=row["name"] + "Icon", parent=row["guid"], visible=1,
                 path=FIG_ICON + "melee-pip.png", depth=0.0)
        c.update({"anchorMinN.x": 0.0, "anchorMinN.y": 0.0, "anchorMaxN.x": 1.0, "anchorMaxN.y": 1.0,
                  "pivotN.x": 0.0, "pivotN.y": 0.0, "pivotAs.x": 0.0, "pivotAs.y": 0.0,
                  "rectSizeDelta.width": 0.0, "rectSizeDelta.height": 0.0})
        new += [row, c]
    items.extend(new)
    json.dump(w, open(path, "w", encoding="utf-8"), indent=4)
    return 1


def add_supply_row(wdir):
    """to1/currency-hud (the mod's in-match parts counter): clone partsRow (gradient, icon, number) as
    "supplyRow" one row lower, icon = the 2013 supplies glyph; t2r-ext (feature_supply_counter) sets the
    number and shows it in clan matches only."""
    path = os.path.join(wdir, "to1", "currency-hud.widget.json")
    w = json.load(open(path, encoding="utf-8"))
    items = w["items"]
    if any(i["name"] == "supplyRow" for i in items):
        return 0
    row = next(i for i in items if i["name"] == "partsRow")
    sub = [i for i in items if i is row or i.get("parent") == row["guid"]]
    remap = {i["guid"]: t2guid.guid() for i in sub}
    new = []
    for i in sub:
        c = copy.deepcopy(i)
        c["guid"] = remap[i["guid"]]
        if c.get("parent") in remap:
            c["parent"] = remap[c["parent"]]
        c["name"] = c["name"].replace("parts", "supply").replace("Parts", "Supply")
        if c["name"] == "supplyRow":
            c["pivotAs.y"] = row["pivotAs.y"] + row["rectSizeDelta.height"] + 10.0     # right under the parts row
        elif c["name"] == "supplyRowIcon":
            c["path"] = SUPPLY_ICON
        elif c["name"] == "supplyAmount":
            c["text"] = "0"
        new.append(c)
    items[items.index(row) + len(sub):items.index(row) + len(sub)] = new
    json.dump(w, open(path, "w", encoding="utf-8"), indent=4)
    return 1


# ------------------------------------------------------------------ post-match (2013 day report)
# to1/clan-postmatch: pushed by t2r-ext (feature_clan, pm_tick) on the MP menu after a clan match,
# the 2013 sequence of post-match-rewards/1..5.png on one page, three stages (groups):
#   "earned"  the match's parts per award (up to PM_ROWS rows, filled from the bottom row up so
#             the list always ends on the divider) and the PARTS EARNED total under it;
#   "convert" CONVERTED: parts tick down while the supplies tick up (50 parts = 1), as 2013;
#   "result"  two columns: DAILY SUPPLIES (+surplus / -deficit, gathered vs needed, what the day
#             did to the clan) | SURVIVORS GAINED, N SURVIVORS, HEALTHY / HUNGRY / SICK, dot circle.
# Header (WEEK n: DAY d of the day played, faction emblem, faction name where 2013 had the version
# number), the 2013 scroll line on the right, NEXT / CONTINUE bottom right.
PM_PAGE = "clan-postmatch"
PM_ROWS = 5
PM_TEXT = 0xFFD8D4CC                 # the 2013 post-match labels: warm light grey
PM_DIM = 0xFF8E8A84
PM_CIRCLE, PM_DOT = 430, 18
GEAR_ICON = "streaming/t2r/icons/gear.png"            # tools/models/make_icons.gear_icon (2013 parts cog)
PERSON_ICON = "streaming/t2r/icons/person.png"        # make_icons.person_icon (2013 survivor pictogram)
PM_ROW_Y, PM_ROW_H = 420, 80         # breakdown rows (top of row 0), row pitch
PM_PARTS_Y, PM_CONV_Y = 916, 1012    # centre lines of PARTS EARNED / CONVERTED
PM_LX, PM_RX = 1234, 2862            # label left edge / number right edge (2013 layout x 3)
PM_OUT_ROWS = 5


def build_postmatch_page(main):
    """to1/clan-postmatch.widget.json content."""
    t, root0, anim0 = _templates(main)
    b = Builder(t)
    root = copy.deepcopy(root0); root.update(guid=t2guid.guid())
    anim = copy.deepcopy(anim0); anim.update(guid=t2guid.guid(), parent=root["guid"])
    b.items += [root]
    a = anim["guid"]
    # the backdrop is its own group under the root (drawn first), NOT under anim-group: anim-group is the
    # content that fades in, the dark background is opaque from the very first frame (t2r-ext pm_tick
    # fades "pmBg" only when the page goes out, 0.3 s)
    bg = b.group("pmBg", root["guid"], b.bleed())["guid"]
    b.image("bgBlur", bg, b.bleed(), "general-textures/blur-background.png", 0xFFFFFFFF, 255)
    b.rect("bgDark", bg, b.bleed(), 0xFF0B0C0D, 255)
    b.image("bgLight", bg, b.ctr(1920, 980, 3600, 2200), "hud/player-menu/gradient/radial-gradient.png", 0xFFFFFFFF, 26)
    anim["depth"] = float(len(b.items)) * 0.01     # above the backdrop
    b.items.append(anim)

    # --- header (post-match-rewards/1.png)
    for key, col in (("W", WLF_COL), ("S", SER_COL)):
        b.image(f"pmEmblem{key}", a, b.tl(318, 158, 66, 137), FIG_IMG[key], col, 210, visible=int(key == "W"))
    b.text("pmTitle", a, b.tl(450, 150, 2200, 150), "WEEK 1: DAY 1", 86, PM_TEXT, tracking=6)
    b.text("pmFaction", a, b.tl(2600, 118, 976, 60), "WASHINGTON LIBERATION FRONT", 34, PM_DIM, align=2, tracking=4)
    b.line("pmTitleLine", a, 264, 305, 3576, 305, 0xFFFFFFFF, 120, 2.0)
    b.line("pmScroll", a, 3768, 420, 3768, 1925, 0xFFFFFFFF, 140, 2.0)

    def amount(prefix, parent, cy, pt, num, argb, icon, icon_argb, icon_w, icon_h):
        """number right-aligned on PM_RX + its icon right of it (the 2013 '2065 [cog]')."""
        b.text(prefix + "Num", parent, b.tl(PM_RX - 700, cy - pt, 700, pt * 2), num, pt, argb, align=2, tracking=2)
        # hidden twin (the counting numbers flicker - the ext writes the hidden copy and swaps, db_text_w)
        b.text(prefix + "NumB", parent, b.tl(PM_RX - 700, cy - pt, 700, pt * 2), num, pt, argb, align=2, tracking=2, visible=0)
        b.image(prefix + "Icon", parent, b.ctr(PM_RX + 86, cy, icon_w, icon_h), icon, icon_argb)

    # --- stage 0: parts per award + total (post-match-rewards/2.png, with our breakdown above)
    e = b.group("earned", a, b.tl(0, 0, W, H))["guid"]
    rows = b.group("rows", e, b.tl(0, 0, W, H))["guid"]
    demo = [("DOWNED ENEMY", 6, 600), ("EXECUTION", 4, 200), ("REVIVE", 2, 200), ("HEADSHOT", 5, 250),
            ("KILL ASSIST", 3, 75)]
    for k in range(PM_ROWS):
        cy = PM_ROW_Y + k * PM_ROW_H + PM_ROW_H / 2
        r = b.group(f"pmRow{k}", rows, b.tl(0, 0, W, H))["guid"]
        lab, cnt, pts = demo[k]
        b.text(f"pmRow{k}Label", r, b.tl(PM_LX, cy - 40, 1000, 80), lab, 46, PM_TEXT, tracking=4)
        b.text(f"pmRow{k}Count", r, b.tl(2080, cy - 40, 260, 80), f"x{cnt}", 40, PM_DIM, align=1, tracking=2)
        b.text(f"pmRow{k}Num", r, b.tl(PM_RX - 500, cy - 40, 500, 80), str(pts), 46, PM_TEXT, align=2, tracking=2)
        b.image(f"pmRow{k}Icon", r, b.ctr(PM_RX + 86, cy, 58, 58), GEAR_ICON, PM_DIM)
    b.line("pmEarnLine", e, PM_LX - 90, PM_ROW_Y + PM_ROWS * PM_ROW_H + 30, PM_RX + 130,
           PM_ROW_Y + PM_ROWS * PM_ROW_H + 30, 0xFFFFFFFF, 70, 2.0)
    b.image("pmPartsGear", e, b.ctr(PM_LX - 84, PM_PARTS_Y, 80, 80), GEAR_ICON, PM_TEXT, visible=0)      # (hidden - a second cog left of the label stuck out of the column and doubled the right-hand one; round 2 shows it as the hero plate watermark)
    b.text("pmPartsLabel", e, b.tl(PM_LX, PM_PARTS_Y - 76, 1100, 152), "PARTS EARNED", 66, PM_TEXT, tracking=6)
    amount("pmParts", e, PM_PARTS_Y, 66, "1325", PM_TEXT, GEAR_ICON, PM_TEXT, 80, 80)

    # --- stage 1: CONVERTED (post-match-rewards/3.png, 4.png)
    cv = b.group("convert", a, b.tl(0, 0, W, H), visible=0)["guid"]
    b.image("pmConvGear", cv, b.ctr(PM_LX - 84, PM_CONV_Y, 80, 80), GEAR_ICON, PM_TEXT, visible=0)      # (hidden - the supply icon sits on the right)
    b.text("pmConvLabel", cv, b.tl(PM_LX, PM_CONV_Y - 76, 1100, 152), "CONVERTED:", 66, PM_TEXT, tracking=6)
    amount("pmConv", cv, PM_CONV_Y, 66, "26", SUPPLY_BLUE, SUPPLY_ICON, 0xFFFFFFFF, 100, 100)
    b.text("pmConvRate", cv, b.tl(PM_LX, PM_CONV_Y + 80, PM_RX - PM_LX, 70), "50 PARTS = 1 SUPPLY", 40, PM_DIM,
           tracking=4)
    b.text("pmWait", cv, b.tl(PM_LX, PM_CONV_Y + 190, PM_RX - PM_LX + 130, 80), "WAITING FOR THE CAMP...", 48,
           PM_DIM, align=1, tracking=4, visible=0)
    b.text("pmLeft", cv, b.tl(PM_LX, PM_CONV_Y + 190, PM_RX - PM_LX + 130, 80),
           "YOU LEFT EARLY - THE DAY'S PARTS ARE LOST", 48, RED_TEXT, align=1, tracking=4, visible=0)

    # --- stage 2: the day for the clan (post-match-rewards/5.png)
    rs = b.group("result", a, b.tl(0, 0, W, H), visible=0)["guid"]
    LX, RX, TY = 570, 2100, 485                         # column left edges, first row centre line
    b.text("pmDailyLabel", rs, b.tl(LX, TY - 66, 1000, 132), "DAILY SUPPLIES:", 56, PM_TEXT, tracking=5)
    b.text("pmDailyNum", rs, b.tl(1340, TY - 96, 360, 192), "+4", 84, SUPPLY_BLUE, align=2, tracking=2)
    b.text("pmDailyNumB", rs, b.tl(1340, TY - 96, 360, 192), "+4", 84, SUPPLY_BLUE, align=2, tracking=2, visible=0)
    b.image("pmDailyIcon", rs, b.ctr(1790, TY, 120, 120), SUPPLY_ICON, 0xFFFFFFFF)
    b.text("pmGathered", rs, b.tl(LX, 620, 1250, 80), 'SUPPLIES GATHERED: <font color="#3fa9f5">26</font>', 42,
           PM_DIM, tracking=4)
    b.text("pmNeeded", rs, b.tl(LX, 710, 1250, 80), 'NEEDED PER DAY: <font color="#3fa9f5">22</font>', 42,
           PM_DIM, tracking=4)
    b.line("pmOutLine", rs, LX, 830, 1800, 830, 0xFFFFFFFF, 60, 2.0)
    for k in range(PM_OUT_ROWS):
        b.text(f"pmOut{k}", rs, b.tl(LX, 880 + k * 92, 1300, 80), ["THE CLAN IS FED", "2 RECOVERED", "", "", ""][k],
               46, HEALTHY, tracking=4)
    b.line("pmMisLine", rs, LX, 1370, 1800, 1370, 0xFFFFFFFF, 60, 2.0)       # the daily mission (t2r-ext pm_mission)
    b.text("pmMis0", rs, b.tl(LX, 1400, 1300, 80), "", 46, PM_TEXT, tracking=4)
    b.text("pmMis1", rs, b.tl(LX, 1490, 1300, 80), "", 42, PM_DIM, tracking=3)
    b.text("pmMis2", rs, b.tl(LX, 1580, 1300, 80), "", 42, HEALTHY, tracking=3)
    b.line("pmDivider", rs, 1910, 400, 1910, 1870, 0xFFFFFFFF, 150, 2.0)
    b.text("pmGainLabel", rs, b.tl(RX, TY - 66, 1000, 132), "SURVIVORS GAINED:", 56, PM_TEXT, tracking=5)
    b.text("pmGainNum", rs, b.tl(2760, TY - 72, 300, 144), "0", 64, HEALTHY, align=2, tracking=2)
    b.text("pmGainNumB", rs, b.tl(2760, TY - 72, 300, 144), "0", 64, HEALTHY, align=2, tracking=2, visible=0)
    b.image("pmGainIcon", rs, b.ctr(3150, TY, 60, 130), PERSON_ICON, HEALTHY)
    b.text("pmCount", rs, b.tl(RX, 630, 1000, 90), "21 SURVIVORS", 50, HUNGRY, tracking=4)
    for k, (nm, txt, col) in enumerate((("pmHealthy", "HEALTHY: 19", HEALTHY), ("pmHungry", "HUNGRY: 2", HUNGRY),
                                        ("pmSick", "SICK: 0", SICK))):
        b.text(nm, rs, b.tl(RX, 815 + k * 120, 720, 80), txt, 52, col, tracking=3)
    cx, cy = 2870, 990
    c = b.group("pmCircle", rs, b.tl(cx - PM_CIRCLE / 2, cy - PM_CIRCLE / 2, PM_CIRCLE, PM_CIRCLE))["guid"]
    b.image("pmCircleSoft", c, b.ctr(PM_CIRCLE / 2, PM_CIRCLE / 2, PM_CIRCLE * 1.25, PM_CIRCLE * 1.25),
            "hud/player-menu/gradient/radial-gradient.png", 0xFF9A9A9A, 90)
    b.ellipse("pmCircleBg", c, b.ctr(PM_CIRCLE / 2, PM_CIRCLE / 2, PM_CIRCLE, PM_CIRCLE), 0xFF6E6E6E, 60)
    for k in range(MAX_DOTS):
        d = b.group(f"pmDot{k}", c, b.ctr(PM_CIRCLE / 2, PM_CIRCLE / 2, PM_DOT, PM_DOT), visible=0)["guid"]
        for suf, argb in (("H", HEALTHY), ("U", HUNGRY), ("S", SICK)):
            b.ellipse(f"pmDot{k}{suf}", d, b.fill(), argb, 255)

    # --- prompt (NEXT while counting through, CONTINUE on the last stage)
    b.image("pmNextIcon", a, b.tl(3330, 1898, 56, 56), "menu:select", 0xFFFFFFFF)
    b.text("pmNextText", a, b.tl(3410, 1890, 300, 70), "NEXT", 46, PM_TEXT, tracking=4)
    b.image("pmContIcon", a, b.tl(3200, 1898, 56, 56), "menu:select", 0xFFFFFFFF, visible=0)
    b.text("pmContText", a, b.tl(3280, 1890, 400, 70), "CONTINUE", 46, PM_TEXT, tracking=4, visible=0)
    if ui_r2_widgets.on("post"):        # UI round 2 (C2): itemised list + framed hero total
        ui_r2_widgets.postmatch(b)

    w = {k: copy.deepcopy(v) for k, v in main.items() if k != "items"}
    w["items"] = b.items
    return w


# ------------------------------------------------------------------ clan event page (to1/clan-event)
# The 2013 event screens (re/factions2013/clan-events-ui.md): net-menu.bin PAGE_CLAN_EVENT_1 (the announcement:
# EVENT_TITLE, EVENT_IMAGE = the clan/event-* picture, NET_BLURB = the description, one button) and
# PAGE_CLAN_EVENT_2 (the result: the "THE MARAUDERS ATTACKED" title, the picture, the tier text, "[A] CLAN MEMBERS DIED
# IN THE ...", "[A] NEW MEMBERS JOINED THE CLAN"). One page of ours serves both; t2r-ext ev_tick fills it.
EV_PAGE = "clan-event"
EV_DOTS, EV_ACTORS = 60, 24
EV_FRAME = (1070, 590, 1700, 660)        # the picture frame (x, y, w, h)
EV_CIRCLE = 420                          # the camp circle in the picture
EV_DOT, EV_ACT = 22, 28
EV_ENEMY = 0xFFD8402F                    # the raiders (enemy red)
EV_FRIEND = 0xFFDCEEF6                   # allies / hostages / friendly survivors (white with a cold cast)
EV_CREAM = 0xFFE9E4CE                    # the 2013 picture-card border (loading tip card)
EV_CHIP_X = (1020, 1920, 2820)           # tier chip centres


def build_event_page(main):
    """to1/clan-event.widget.json content."""
    t, root0, anim0 = _templates(main)
    b = Builder(t)
    root = copy.deepcopy(root0); root.update(guid=t2guid.guid())
    anim = copy.deepcopy(anim0); anim.update(guid=t2guid.guid(), parent=root["guid"])
    b.items += [root]
    a = anim["guid"]
    # the backdrop is its own group (opaque from frame 1, faded only when the page goes out), the content fades in
    bg = b.group("evBg", root["guid"], b.bleed())["guid"]
    b.image("evBlur", bg, b.bleed(), "general-textures/blur-background.png", 0xFFFFFFFF, 255)
    b.rect("evDark", bg, b.bleed(), 0xFF0B0C0D, 255)
    b.image("evLight", bg, b.ctr(1920, 980, 3600, 2200), "hud/player-menu/gradient/radial-gradient.png", 0xFFFFFFFF, 26)
    anim["depth"] = float(len(b.items)) * 0.01
    b.items.append(anim)

    # --- header (the same as the post-match page: emblem, WEEK n: DAY d, faction, line)
    for key, col in (("W", WLF_COL), ("S", SER_COL)):
        b.image(f"evEmblem{key}", a, b.tl(318, 158, 66, 137), FIG_IMG[key], col, 210, visible=int(key == "W"))
    b.text("evTitle", a, b.tl(450, 150, 2200, 150), "WEEK 1: DAY 1", 86, PM_TEXT, tracking=6)
    b.text("evFaction", a, b.tl(2600, 118, 976, 60), "WASHINGTON LIBERATION FRONT", 34, PM_DIM, align=2, tracking=4)
    b.line("evTitleLine", a, 264, 305, 3576, 305, 0xFFFFFFFF, 120, 2.0)

    # --- EVENT_TITLE (+ what kind of screen: incoming / result) and the risk / buff on the right
    b.text("evKind", a, b.tl(300, 335, 1600, 60), "INCOMING EVENT", 36, PM_DIM, tracking=6)
    b.text("evName", a, b.tl(290, 380, 2500, 190), "SERAPHITE ATTACK", 112, PM_TEXT, tracking=8)
    b.text("evRisk", a, b.tl(2300, 420, 1276, 110), "", 54, PM_TEXT, align=2, tracking=3)

    # --- EVENT_IMAGE: the picture. 2013 had one painted still per event; ours is the camp circle of survivor dots
    # (the clan panel's own language) with the event happening around it: raiders closing in, friends / hostages / allies
    # walking in. Card border in the 2013 tip-card cream.
    fx, fy, fw, fh = EV_FRAME
    sc = b.group("evScene", a, b.tl(fx, fy, fw, fh))["guid"]
    b.rect("evPic", sc, b.fill(), 0xFF0F1113, 255)
    b.image("evPicLight", sc, b.ctr(fw / 2, fh / 2, fw * 1.1, fh * 1.5), "hud/player-menu/gradient/radial-gradient.png",
            0xFFFFFFFF, 40)
    b.image("evGlowEnemy", sc, b.ctr(fw / 2, fh / 2, fw * 1.05, fh * 1.45), "hud/player-menu/gradient/radial-gradient.png",
            EV_ENEMY, 255)           # (t2r-ext sets the widget alpha: the glow's strength)
    b.image("evGlowFriend", sc, b.ctr(fw / 2, fh / 2, fw * 1.05, fh * 1.45), "hud/player-menu/gradient/radial-gradient.png",
            HEALTHY, 255)
    cg = b.group("evCircle", sc, b.ctr(fw / 2, fh / 2, EV_CIRCLE, EV_CIRCLE))["guid"]
    b.image("evCircleSoft", cg, b.ctr(EV_CIRCLE / 2, EV_CIRCLE / 2, EV_CIRCLE * 1.3, EV_CIRCLE * 1.3),
            "hud/player-menu/gradient/radial-gradient.png", 0xFF9A9A9A, 100)
    b.ellipse("evCircleBg", cg, b.ctr(EV_CIRCLE / 2, EV_CIRCLE / 2, EV_CIRCLE, EV_CIRCLE), 0xFF6E6E6E, 64)
    for k in range(EV_DOTS):
        d = b.group(f"evDot{k}", cg, b.ctr(EV_CIRCLE / 2, EV_CIRCLE / 2, EV_DOT, EV_DOT), visible=0)["guid"]
        for suf, argb in (("H", HEALTHY), ("U", HUNGRY), ("S", SICK)):
            b.ellipse(f"evDot{k}{suf}", d, b.fill(), argb, 255)
    for k in range(EV_ACTORS):
        d = b.group(f"evAct{k}", sc, b.ctr(fw / 2, fh / 2, EV_ACT, EV_ACT), visible=0)["guid"]
        for suf, argb in (("R", EV_ENEMY), ("W", EV_FRIEND), ("G", HUNGRY)):
            b.ellipse(f"evAct{k}{suf}", d, b.fill(), argb, 255)
    b.frame("evFrame", a, b.tl(fx, fy, fw, fh), EV_CREAM, 255, 6.0)

    # --- NET_BLURB: the 2013 description / the tier text of the result
    b.text("evBlurb", a, b.tl(520, 1290, 2800, 220), "", 52, PM_TEXT, align=1, multiline=1, valign=0, tracking=2)

    # --- the three tiers (the mission block of the 2013 loading screen: goal, % ), the reached one lit on the result
    for k in range(3):
        cx = EV_CHIP_X[k]
        c = b.group(f"evChip{k}", a, b.tl(cx - 400, 1530, 800, 270))["guid"]
        b.frame(f"evChip{k}Frame", c, b.fill(), EV_CREAM, 255, 4.0, visible=0)    # lit on the result page (the tier reached)
        b.text(f"evChip{k}Tier", c, b.tl(0, 18, 800, 50), f"TIER {k + 1}", 32, PM_DIM, align=1, tracking=6)
        b.text(f"evChip{k}Big", c, b.tl(0, 66, 800, 110), "3 DOWNS", 80, PM_TEXT, align=1, tracking=4)
        b.text(f"evChip{k}Pct", c, b.tl(0, 186, 800, 70), "LOSE 40%", 46, HEALTHY, align=1, tracking=4)
    b.line("evChipLine0", a, 1470, 1560, 1470, 1770, 0xFFFFFFFF, 90, 2.0)
    b.line("evChipLine1", a, 2370, 1560, 2370, 1770, 0xFFFFFFFF, 90, 2.0)

    # --- result lines under the tiers (outcome page): "[A] CLAN MEMBERS DIED IN THE ... ATTACK"
    b.text("evLine0", a, b.tl(300, 1830, 2900, 80), "", 54, SICK, align=1, tracking=4)
    b.text("evLine1", a, b.tl(300, 1915, 2900, 70), "", 42, PM_DIM, align=1, tracking=3)

    # --- prompt (CONTINUE)
    b.image("evContIcon", a, b.tl(3200, 1898, 56, 56), "menu:select", 0xFFFFFFFF)
    b.text("evContText", a, b.tl(3280, 1890, 400, 70), "CONTINUE", 46, PM_TEXT, tracking=4)

    w = {k: copy.deepcopy(v) for k, v in main.items() if k != "items"}
    w["items"] = b.items
    return w


def event_demo(page, mode, kind, fac=1, day=14, tier=0, lost=0, join=0, survivors=25, phase=1.0):
    """The event page set up the way t2r-ext ev_tick fills it, for widget_preview.
    mode 'announce' / 'result'; kind 'attack' / 'growth'; phase 0..1 = how far the picture's action is."""
    import math
    import random
    w = copy.deepcopy(page)
    by = {i["name"]: i for i in w["items"]}
    vis = lambda n, on: by[n].update(visible=int(bool(on)))
    txt = lambda n, s, col=None: (by[n].update(text=s), col is not None and by[n].update({"tint.start": col, "tint.end": col}))
    wk, dw = day // 7 + 1, day % 7 + 1
    txt("evTitle", f"WEEK {wk}: DAY {dw}")
    foe = "SERAPHITE" if fac == 1 else "WLF"
    foes = "Seraphites" if fac == 1 else "WLF"
    vis("evEmblemW", fac == 1); vis("evEmblemS", fac == 2)
    txt("evFaction", "WASHINGTON LIBERATION FRONT" if fac == 1 else "SERAPHITES")
    loss = (60, 40, 20, 10) if day in (15, 30) else (100, 60, 40, 20)
    cx = EV_CIRCLE / 2
    rng = random.Random(7)
    n = survivors
    dn = min(n, EV_DOTS)
    lost_d = min(dn - 1, max(1 if lost else 0, round(lost * dn / max(1, n)))) if lost else 0
    join_d = min(EV_DOTS - dn, max(1 if join else 0, round(join * dn / max(1, n)))) if join else 0
    if kind == "attack":
        txt("evName", f"{foe} ATTACK" if mode == "announce" else f"THE {foes.upper()} ATTACKED")
        txt("evKind", "INCOMING EVENT" if mode == "announce" else "EVENT RESULT")
        if mode == "announce":
            txt("evRisk", f'RISK: <font color="#e04848">{loss[0]}%</font> OF POPULATION')
            txt("evBlurb", f"Scouts have picked up a large group of {foes} massing nearby for an attack. Improve the "
                           "training of the group to help us survive the attack.")
        else:
            txt("evRisk", "")
            txt("evBlurb", ["You were not able to improve the training of your clan before the %s attacked. Massive "
                            "casualties were sustained." % foes,
                            "You were able to partially improve the training of your clan. You sustained heavy "
                            "casualties from the %s." % foes,
                            "You were able to partially improve the training of your clan. You sustained heavy "
                            "casualties from the %s." % foes,
                            "You were able to dramatically improve the training of your clan before the %s attacked. As "
                            "a result, a minimum of clan members died in the attack." % foes][tier])
        goals = ("3 DOWNS", "6 DOWNS", "9 DOWNS")
        for k in range(3):
            txt(f"evChip{k}Big", goals[k])
            txt(f"evChip{k}Pct", f"LOSE {loss[k + 1]}%", SICK)
        by["evGlowEnemy"]["color.a"] = 90
        by["evGlowFriend"]["color.a"] = 0     # (preview: the ext drives these by widget alpha)
        act_kind = "R"
    else:
        names = ("FRIENDLY SURVIVORS", "HOSTAGES TAKEN", "RESCUE ALLIES")
        blurbs = ("Some friendly survivors have been located nearby. If we can protect them from the %s they'll join our "
                  "clan." % foes,
                  "Some of our people have been taken hostage by the %s. Improve the training of the group to mount a "
                  "rescue mission." % foes,
                  "A group of allies trying to reach our camp were captured by the %s. Improve the training of the "
                  "group so we can mount a rescue mission." % foes)
        res_names = ("FRIENDLY SURVIVORS", "HOSTAGE RESCUE", "RESCUE ALLIES ATTEMPTED")
        gi = (day // 5) % 3
        txt("evName", names[gi] if mode == "announce" else res_names[gi])
        txt("evKind", "INCOMING EVENT" if mode == "announce" else "EVENT RESULT")
        txt("evRisk", 'EVENT BUFF: <font color="#5dc0dc">NEW SURVIVORS</font>' if mode == "announce" else "")
        if mode == "announce":
            txt("evBlurb", blurbs[gi])
        else:
            txt("evBlurb", ["You were not able to protect any friendly survivors. No one joined your clan.",
                            "You were able to partially improve the training of your clan and protect some friendlies. "
                            "Some new members joined your clan.",
                            "You were able to partially improve the training of your clan and protect some friendlies. "
                            "Some new members joined your clan.",
                            "You were able to dramatically improve the training of your clan and protect the friendly "
                            "survivors. All the friendlies joined your clan."][tier])
        for k, (big, pct) in enumerate((("FED", "+5%"), ("25% SPARE", "+7.5%"), ("50% SPARE", "+10%"))):
            txt(f"evChip{k}Big", big)
            txt(f"evChip{k}Pct", f"{pct} JOIN", HEALTHY)
        by["evGlowEnemy"]["color.a"] = 0
        by["evGlowFriend"]["color.a"] = 70
        act_kind = "W"
    for k in range(3):                                       # the reached tier lit on the result page
        vis(f"evChip{k}Frame", mode == "result" and tier == k + 1)
        dim = mode == "result" and tier != k + 1
        for s in ("Tier", "Big", "Pct"):
            by[f"evChip{k}{s}"]["color.a"] = 90 if dim else 255
    if mode == "result":
        if kind == "attack":
            txt("evLine0", f"{lost} CLAN MEMBERS DIED IN THE {foe} ATTACK" if lost else "NO ONE WAS LOST", SICK if lost else HEALTHY)
            txt("evLine1", f"{n - lost} SURVIVORS LEFT" if survivors - lost > 0 else "YOUR CLAN WAS WIPED OUT")
        else:
            txt("evLine0", f"{join} NEW MEMBERS JOINED THE CLAN" if join else "NO ONE JOINED THE CLAN", HEALTHY if join else PM_DIM)
            txt("evLine1", f"{n + join} SURVIVORS")
    else:
        txt("evLine0", "")
        txt("evLine1", "DOWN ENEMIES IN YOUR NEXT MATCH - THE MORE YOU DOWN, THE FEWER SURVIVORS FALL" if kind == "attack" else
            "FEED THE CLAN IN YOUR NEXT MATCH - THE MORE SPARE SUPPLIES, THE MORE SURVIVORS JOIN")
    # picture: camp dots (+ lost ones red on the result), actors around / converging
    shown = dn + (join_d if mode == "result" and phase >= 0.7 else 0)
    for k in range(EV_DOTS):
        on = k < shown
        a, r = rng.uniform(0, 6.2832), 165 * rng.random() ** 0.5
        by[f"evDot{k}"].update(visible=int(on), **{"pivotAs.x": cx + r * math.cos(a), "pivotAs.y": cx + r * math.sin(a)})
        st = "S" if (mode == "result" and kind == "attack" and k >= dn - lost_d and k < dn and phase < 0.9) else "H"
        for suf in "HUS":
            vis(f"evDot{k}{suf}", suf == st)
        if mode == "result" and kind == "attack" and k >= dn - lost_d and k < dn and phase >= 0.9:
            vis(f"evDot{k}", 0)
    na = 12 if kind == "attack" else 7
    if mode == "result" and kind == "growth":
        na = max(1, join_d) if join else 0
    fw, fh = EV_FRAME[2], EV_FRAME[3]
    for k in range(EV_ACTORS):
        on = k < na
        ang = 6.2832 * k / max(1, na) + 0.4
        ring0 = 270.0 + 90 * (k % 3) / 2
        edge = EV_CIRCLE / 2 * 0.95
        rr = ring0 if mode == "announce" else ring0 + (edge - ring0) * min(1.0, phase * 1.4)
        if mode == "announce":
            rr -= 14 * math.sin(k)
        ax, ay = math.cos(ang) * rr * 1.7, math.sin(ang) * rr * 0.78      # (t2r-ext EV_RX / EV_RY)
        by[f"evAct{k}"].update(visible=int(on and not (mode == "result" and phase > 0.9)),
                               **{"pivotAs.x": fw / 2 + ax, "pivotAs.y": fh / 2 + ay})
        for suf in "RWG":
            vis(f"evAct{k}{suf}", suf == act_kind)
    return w


def preview_event(wdir, out_dir):
    import widget_preview
    import tempfile
    main = json.load(open(os.path.join(wdir, "to1", "main-menu.widget.json"), encoding="utf-8"))
    page = build_event_page(main)
    shots = (("event-1-attack-announce", dict(mode="announce", kind="attack", day=15, survivors=25)),
             ("event-2-attack-result-t0", dict(mode="result", kind="attack", day=15, survivors=25, tier=0, lost=15, phase=0.5)),
             ("event-3-attack-result-t3", dict(mode="result", kind="attack", day=15, survivors=25, tier=3, lost=3, phase=0.5, fac=2)),
             ("event-4-growth-announce", dict(mode="announce", kind="growth", day=10, survivors=19)),
             ("event-5-growth-result", dict(mode="result", kind="growth", day=10, survivors=19, tier=2, join=2, phase=0.6)))
    os.makedirs(out_dir, exist_ok=True)
    for name, kw in shots:
        tmp = os.path.join(tempfile.gettempdir(), "t2r-" + name + ".widget.json")
        json.dump(event_demo(page, **kw), open(tmp, "w", encoding="utf-8"))
        print(widget_preview.render(tmp, os.path.join(out_dir, name + ".png")))


def add_clan_ui(wdir):
    """Edit the extracted widget folder: returns (main menu panels added, pages written)."""
    mp = os.path.join(wdir, "to1", "main-menu.widget.json")
    main = json.load(open(mp, encoding="utf-8"))
    side = build_side_page(main)
    json.dump(side, open(os.path.join(wdir, "to1", PAGE + ".widget.json"), "w", encoding="utf-8"), indent=4)
    pm = build_postmatch_page(main)
    json.dump(pm, open(os.path.join(wdir, "to1", PM_PAGE + ".widget.json"), "w", encoding="utf-8"), indent=4)
    ev = build_event_page(main)
    json.dump(ev, open(os.path.join(wdir, "to1", EV_PAGE + ".widget.json"), "w", encoding="utf-8"), indent=4)
    n = add_main_panel(main) + add_menu_shade(main)
    add_enter_cover(main)
    json.dump(main, open(mp, "w", encoding="utf-8"), indent=4)
    # the FINDING MATCH page is the main menu with FIND MATCH hidden: same gradient + clan panel
    fp = os.path.join(wdir, "to1", "find-match-menu.widget.json")
    fm = json.load(open(fp, encoding="utf-8"))
    add_main_panel(main, fm)
    add_menu_shade(main, fm)
    json.dump(fm, open(fp, "w", encoding="utf-8"), indent=4)
    add_feed_pages(main, wdir)
    add_pause_widgets(wdir)
    add_supply_row(wdir)
    add_team_figs(wdir)
    add_armor_hit(wdir)
    add_spawn_shield(wdir)
    add_armor_hud(wdir)
    add_melee_free(wdir)
    add_wolf_hud(wdir)
    add_buy_hint(wdir)
    add_hud_counters(wdir)      # last: the other adders clone partsRowIcon (untinted)
    return n, 3


# ------------------------------------------------------------------ offline previews
def postmatch_demo(page, stage, day=None):
    """A copy of the post-match page set up the way t2r-ext fills it (pm_tick), for widget_preview.
    stage 0 / 1 / 2; day = dict of the 0xE1 l* fields + clan counts (a fed day of 21 if None)."""
    import random
    d = dict(day or {})
    w = copy.deepcopy(page)
    by = {i["name"]: i for i in w["items"]}
    vis = lambda n, on: by[n].update(visible=int(bool(on)))
    rows = d.get("rows", [("DOWNED ENEMY", 6, 600), ("EXECUTION", 4, 200), ("REVIVE", 2, 200), ("HEADSHOT", 5, 250)])
    first = PM_ROWS - len(rows)
    for k in range(PM_ROWS):
        vis(f"pmRow{k}", k >= first)
        if k >= first:
            lab, cnt, pts = rows[k - first]
            by[f"pmRow{k}Label"]["text"], by[f"pmRow{k}Count"]["text"], by[f"pmRow{k}Num"]["text"] = lab, f"x{cnt}", str(pts)
    parts = sum(r[2] for r in rows)
    sup = 0 if d.get("lleft") else parts // 50
    by["pmPartsNum"]["text"] = str(parts if stage == 0 else 0)
    by["pmConvNum"]["text"] = str(sup)
    vis("earned", stage < 2); vis("convert", stage == 1); vis("result", stage == 2)
    by["rows"]["color.a"] = 255 if stage == 0 else 80
    vis("pmLeft", stage == 1 and d.get("lleft"))
    vis("pmNextIcon", stage < 2); vis("pmNextText", stage < 2)
    vis("pmContIcon", stage == 2); vis("pmContText", stage == 2)
    if d.get("fac") == 2:
        vis("pmEmblemW", 0); vis("pmEmblemS", 1); by["pmFaction"]["text"] = "SERAPHITES"
    h, hu, s, need = d.get("h", 19), d.get("hu", 2), d.get("s", 0), d.get("lneed", 22)
    diff = sup - need
    by["pmDailyNum"]["text"] = f"+{diff}" if diff >= 0 else str(diff)
    by["pmDailyNum"]["tint.start"] = by["pmDailyNum"]["tint.end"] = SUPPLY_BLUE if diff >= 0 else RED_TEXT
    by["pmGathered"]["text"] = f'SUPPLIES GATHERED: <font color="#3fa9f5">{sup}</font>'
    by["pmNeeded"]["text"] = f'NEEDED PER DAY: <font color="#3fa9f5">{need}</font>'
    for k, (txt, col) in enumerate((d.get("out") or [("THE CLAN IS FED", HEALTHY), ("2 RECOVERED", HEALTHY)])
                                   + [("", PM_TEXT)] * PM_OUT_ROWS):
        if k < PM_OUT_ROWS:
            by[f"pmOut{k}"].update({"text": txt, "tint.start": col, "tint.end": col})
    by["pmGainNum"]["text"] = str(d.get("lgain", 0))
    by["pmCount"]["text"] = f"{h + hu + s} SURVIVORS"
    by["pmHealthy"]["text"], by["pmHungry"]["text"], by["pmSick"]["text"] = f"HEALTHY: {h}", f"HUNGRY: {hu}", f"SICK: {s}"
    rng = random.Random(2013)
    n = h + hu + s
    for k in range(min(n, MAX_DOTS)):
        st = "H" if k < h else "U" if k < h + hu else "S"
        a, r = rng.uniform(0, 6.2832), 190 * rng.random() ** 0.5
        import math
        by[f"pmDot{k}"].update(visible=1, **{"pivotAs.x": PM_CIRCLE / 2 + r * math.cos(a),
                                             "pivotAs.y": PM_CIRCLE / 2 + r * math.sin(a)})
        for suf in "HUS":
            vis(f"pmDot{k}{suf}", suf == st)
    return w


def preview_postmatch(wdir, out_dir):
    """python clan_widgets.py <extracted widget dir> <out dir>: re/factions2013/preview/postmatch-*.png"""
    import widget_preview
    import tempfile
    main = json.load(open(os.path.join(wdir, "to1", "main-menu.widget.json"), encoding="utf-8"))
    page = build_postmatch_page(main)
    hungry_day = {"rows": [("DOWNED ENEMY", 2, 200), ("HEADSHOT", 1, 50), ("KILL ASSIST", 1, 25)],
                  "fac": 2, "h": 14, "hu": 5, "s": 2, "lneed": 22, "lgain": 0,
                  "out": [("SHORT BY 17 SUPPLIES", RED_TEXT), ("5 WENT HUNGRY", HUNGRY), ("2 FELL SICK", SICK),
                          ("1 DIED", SICK)]}
    shots = (("postmatch-1-parts", 0, None), ("postmatch-2-convert", 1, None), ("postmatch-3-day", 2, None),
             ("postmatch-4-hungry-day", 2, hungry_day))
    os.makedirs(out_dir, exist_ok=True)
    for name, stage, day in shots:
        tmp = os.path.join(tempfile.gettempdir(), "t2r-" + name + ".widget.json")
        json.dump(postmatch_demo(page, stage, day), open(tmp, "w", encoding="utf-8"))
        print(widget_preview.render(tmp, os.path.join(out_dir, name + ".png")))


def postmatch_anim_frame(page, ms, rows):
    """The parts -> supplies timeline of t2r-ext pm_tick stage 0 at ms after the page opened (keep in sync):
    page fade 0-1200, PARTS EARNED fades in 1400-2000, count from 2200 for min(1800, max(700, parts*15)),
    CONVERTED fades in 300 ms before the count. Returns a widget dict for widget_preview."""
    parts = sum(r[2] for r in rows)
    cdur = min(1800, max(700, parts * 15))
    clamp = lambda x: max(0.0, min(1.0, x))
    f = clamp((ms - 2200) / cdur)
    w = postmatch_demo(page, 1, {"rows": rows})
    by = {i["name"]: i for i in w["items"]}
    by["pmPartsNum"]["text"] = str(parts - int(parts * f + 0.5))
    by["pmConvNum"]["text"] = str(int(parts // 50 * f + 0.5))
    by["rows"]["color.a"] = 255
    by["anim-group"]["color.a"] = int(255 * clamp(ms / 1200))
    for n in ("pmEarnLine", "pmPartsGear", "pmPartsLabel", "pmPartsNum", "pmPartsIcon"):
        by[n]["color.a"] = int(by[n].get("color.a", 255) * clamp((ms - 1400) / 600))
    by["convert"]["color.a"] = int(255 * clamp((ms - 1900) / 300))
    return w


def preview_postmatch_bg(wdir, out_dir):
    """The backdrop is opaque from the first frame, only the content fades in; going out both fade in 0.3 s."""
    import widget_preview
    import tempfile
    main = json.load(open(os.path.join(wdir, "to1", "main-menu.widget.json"), encoding="utf-8"))
    page = build_postmatch_page(main)
    rows = [("DOWNED ENEMY", 3, 75), ("HEADSHOT", 2, 25), ("EXECUTION", 4, 20)]
    for name, ms, out in (("postmatch-bg-0-first-frame", 0, None), ("postmatch-bg-1-text-fading-in", 800, None),
                          ("postmatch-bg-2-full", 4300, None), ("postmatch-bg-3-out-150ms", 4300, 0.5),
                          ("postmatch-bg-4-out-300ms", 4300, 0.0)):
        w = postmatch_anim_frame(page, ms, rows)
        by = {i["name"]: i for i in w["items"]}
        if out is not None:
            by["pmBg"]["color.a"] = int(255 * out)
            by["anim-group"]["color.a"] = int(255 * out)
        tmp = os.path.join(tempfile.gettempdir(), "t2r-" + name + ".widget.json")
        json.dump(w, open(tmp, "w", encoding="utf-8"))
        print(widget_preview.render(tmp, os.path.join(out_dir, name + ".png")))


def preview_postmatch_anim(wdir, out_dir):
    import widget_preview
    import tempfile
    main = json.load(open(os.path.join(wdir, "to1", "main-menu.widget.json"), encoding="utf-8"))
    page = build_postmatch_page(main)
    rows = [("DOWNED ENEMY", 3, 75), ("HEADSHOT", 2, 25), ("EXECUTION", 4, 20)]    # 120 parts -> 2 supplies
    for ms in (500, 1000, 1700, 2100, 2800, 3300, 4000, 4300):
        name = f"postmatch-anim-{ms:04d}ms"
        tmp = os.path.join(tempfile.gettempdir(), "t2r-" + name + ".widget.json")
        json.dump(postmatch_anim_frame(page, ms, rows), open(tmp, "w", encoding="utf-8"))
        print(widget_preview.render(tmp, os.path.join(out_dir, name + ".png")))


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 3 and sys.argv[3] == "event":
        preview_event(sys.argv[1], sys.argv[2])
        sys.exit(0)
    preview_postmatch(sys.argv[1], sys.argv[2])
    preview_postmatch_anim(sys.argv[1], sys.argv[2])
    preview_postmatch_bg(sys.argv[1], sys.argv[2])
