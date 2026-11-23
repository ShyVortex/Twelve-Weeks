"""Menu backdrops + list row text fit, added to gui2-widgets.pak by widgets_patch.patch_widgets (after the other
page builders).

- Dark feathered gradient (streaming/t2r/clan/menu-shade-sub.png, tools/models/figures/ship.py) as the lowest
  item behind every MP sub-menu: to1/loadout-root (the shared "chrome" Reference of loadout-menu, picker-*,
  weapon-picker, map-select, credits) and the pages with their own title block (leaderboard, find-match-menu,
  options-menu-multiplayer). The main menu has its own (clan_widgets.add_menu_shade); the clan / match flow /
  name / mission pages have an opaque dark background already.
- The same gradient behind every DETAILS panel (picker-skill / primary / secondary detailPanel, find-match-menu
 lobbyPanel until): the first child of the panel (so it follows the panel's visibility), a little larger than it.
- Row text fit: the row widgets' name labels get a wrapping box that ends before the LP column / selected tick, at
  a size that holds a long name on two lines ("SUPPRESSED HUNTING RIFLE" used to run into "2 LP")."""
import copy
import json
import os
import t2guid

SHADE = "streaming/t2r/clan/menu-shade-sub.png"
LEFT_RECT = (-250, -650, 2170, 3460)      # x, y, w, h: title block + the 1520 x 1370 list panel + feather
WIDE_RECT = (-250, -650, 4600, 3460)      # leaderboard: its table runs to x ~3650 (ldrboards.png: the left shade stopped mid-table) - the right feather lands off screen, so the whole backdrop is one even shade
DETAIL_PAD = 220                          # feather room round a details panel
NAME = "menuShade"


def _load(wdir, page):
    p = os.path.join(wdir, "to1", page + ".widget.json")
    return p, json.load(open(p, encoding="utf-8"))


def _save(p, w):
    json.dump(w, open(p, "w", encoding="utf-8"), indent=4)


def _image(w, template, name, parent, place, depth):
    it = copy.deepcopy(template)
    it.update({"guid": t2guid.guid(), "parent": parent, "name": name, "depth": float(depth), "visible": 1,
               "rotation": 0.0, "path": SHADE, "scaleMode": "Stretch", "color.a": 255, "animation": {"keyframes": {}},
               "tint.start": 0xFFFFFFFF, "tint.end": 0xFFFFFFFF, "pivotN.x": 0.0, "pivotN.y": 0.0})
    it.update(place)
    # list order is draw order: the shade goes in front of its first sibling so it draws first (behind them),
    # like the main menu's menuShade (appended last it drew OVER the details panel and GEAR UP)
    at = next((k for k, i in enumerate(w["items"]) if i.get("parent") == parent), len(w["items"]))
    w["items"].insert(at, it)
    return it


def _tl(x, y, ww, hh):
    return {"anchorMinN.x": 0.0, "anchorMinN.y": 0.0, "anchorMaxN.x": 0.0, "anchorMaxN.y": 0.0,
            "pivotAs.x": float(x), "pivotAs.y": float(y), "rectSizeDelta.width": float(ww),
            "rectSizeDelta.height": float(hh)}


def _around():
    """Fills its parent plus DETAIL_PAD on every side."""
    return {"anchorMinN.x": 0.0, "anchorMinN.y": 0.0, "anchorMaxN.x": 1.0, "anchorMaxN.y": 1.0,
            "pivotAs.x": float(-DETAIL_PAD), "pivotAs.y": float(-DETAIL_PAD),
            "rectSizeDelta.width": 2.0 * DETAIL_PAD, "rectSizeDelta.height": 2.0 * DETAIL_PAD}


TITLE_GRAD = "streaming/t2r/clan/title-grad.png"     # tools/models/figures/ship.py make_title_grad
# the title (boat) screen = menu/page-game-select: TWELVE WEEKS / QUIT TO DESKTOP top left over the Hillcrest world (re/title-grad-1105):
# black at 0.65 * (1 - smoothstep(r)), r = hypot((x - 0.12 W) / (0.35 W), (y - 0.38 H) / (0.65 H)) on the 3840 x 2160 page = a 2688 x 2808 image centred on (460.8, 820.8)
TG_CX, TG_CY, TG_RX, TG_RY = 0.12 * 3840, 0.38 * 2160, 0.35 * 3840, 0.65 * 2160


def add_title_grad(wdir):
    """Image 'titleGrad' as the first child of anim-group on menu/page-game-select (drawn before every label); skipped for T2R_MENU_BOAT=1 (the stock
    boat has no Hillcrest background to read against). It is part of the page, so the engine's fade-up (titlebg.c boot hold) covers it with the page."""
    if os.environ.get("T2R_MENU_BOAT", "0") == "1":
        return 0
    path = os.path.join(wdir, "menu", "page-game-select.widget.json")
    w = json.load(open(path, encoding="utf-8"))
    if any(i["name"] == "titleGrad" for i in w["items"]):
        return 0
    _, main = _load(wdir, "main-menu")
    t = next(i for i in main["items"] if i["name"] == "lobbyBg" and i["class"] == "Image")
    anim = next(i for i in w["items"] if i["name"] == "anim-group")
    it = copy.deepcopy(t)
    it.update({"guid": t2guid.guid(), "parent": anim["guid"], "name": "titleGrad", "depth": -1.0, "visible": 1,
               "rotation": 0.0, "path": TITLE_GRAD, "scaleMode": "Stretch", "color.a": 255, "animation": {"keyframes": {}},
               "tint.start": 0xFFFFFFFF, "tint.end": 0xFFFFFFFF, "pivotN.x": 0.0, "pivotN.y": 0.0})
    it.update(_tl(TG_CX - TG_RX, TG_CY - TG_RY, 2 * TG_RX, 2 * TG_RY))
    at = next(k for k, i in enumerate(w["items"]) if i.get("parent") == anim["guid"])
    w["items"].insert(at, it)
    json.dump(w, open(path, "w", encoding="utf-8"), indent=4)
    return 1


def add_shades(wdir):
    _, main = _load(wdir, "main-menu")
    t = next(i for i in main["items"] if i["name"] == "lobbyBg" and i["class"] == "Image")
    n = 0
    # 1. page backdrops
    p, w = _load(wdir, "loadout-root")
    if not any(i["name"] == NAME for i in w["items"]):
        root = next(i for i in w["items"] if i["name"] == "root")
        _image(w, t, NAME, root["guid"], _tl(*LEFT_RECT), -1.0)
        _save(p, w)
        n += 1
    for page in ("leaderboard", "options-menu-multiplayer"):   # (find-match-menu has the main menu's shade: clan_widgets)
        p, w = _load(wdir, page)
        if any(i["name"] == NAME for i in w["items"]):
            continue
        anim = next(i for i in w["items"] if i["name"] == "anim-group")
        _image(w, t, NAME, anim["guid"], _tl(*(WIDE_RECT if page == "leaderboard" else LEFT_RECT)), -1.0)
        _save(p, w)
        n += 1
    # the ONLINE counter sits inside the lobby panel's shade on FINDING MATCH (it was above it)
    p, w = _load(wdir, "find-match-menu")
    og = next((i for i in w["items"] if i["name"] == "onlineGroup"), None)
    if og and og.get("pivotAs.y") == 150.0:
        og["pivotAs.y"] = 285.0
        _save(p, w)
    # ONLINE label + green dot on the player count's row, left of the number, on the MP menu and
    # FINDING MATCH; the label box is wide + right-aligned so "STEAM NOT DETECTED" grows left inside the shade
    for page in ("main-menu", "find-match-menu"):
        p, w = _load(wdir, page)
        by = {i["name"]: i for i in w["items"]}
        if "onlineLabel" in by and by["onlineLabel"].get("pivotAs.y") == 82.0:
            by["onlineLabel"].update({"pivotAs.x": -125.0, "pivotAs.y": 40.0, "rectSizeDelta.width": 700.0})
            by["onlineDot"].update({"pivotAs.x": -95.0, "pivotAs.y": 52.0})
            _save(p, w)
    # 2. DETAILS panels
    for page, panel_name in (("picker-skill", "detailPanel"), ("picker-primary", "detailPanel"),
                             ("picker-secondary", "detailPanel"), ("picker-purchase", "detailPanel")):
        # (- find-match-menu lobbyPanel has no detailShade any more:
        # the box has its own blur + black, and the shade ran past it on the left / top after the FRIENDS strip + CHAT panel layout)
        p, w = _load(wdir, page)
        if any(i["name"] == "detailShade" for i in w["items"]):
            continue
        panel = next(i for i in w["items"] if i["name"] == panel_name)
        _image(w, t, "detailShade", panel["guid"], _around(), -1.0)
        _save(p, w)
        n += 1
    return n


# ------------------------------------------------------------------ row text fit
# row widget -> (label item, box right end as a fraction of the row width, point size, (y, height) or None).
# The game's menu font draws ~1.33x wider than the sizes suggest, so 24 characters need 2 lines at these sizes.
ROW_FITS = {
    # loadout-slot (1100 x 160): icon 40..320, small category label, name from x 370; "N LP" right-aligned to x 1050
    "loadout-slot": ("weaponName", 0.80, 38, (62.0, 92.0)),         # box x 370..880, y 62..154
    # picker rows (1400): name box ends before the selected tick (x 1036); purchase rows before the LP text (1130)
    "picker-row": ("label0", 0.72, 38, None),
    "purchase-row": ("label0", 0.55, 38, None),
    "skill-row": ("label0", 0.76, 40, None),                         # cost box starts at 1100
}


def fit_row_text(wdir):
    n = 0
    for page, (item, right, pt, ybox) in ROW_FITS.items():
        p, w = _load(wdir, page)
        it = next(i for i in w["items"] if i["name"] == item)
        it.update({"anchorMaxN.x": right, "multiline": 1, "pointSize": pt, "alignV": 1})
        if ybox:
            it["pivotAs.y"], it["rectSizeDelta.height"] = ybox
        _save(p, w)
        n += 1
    return n
