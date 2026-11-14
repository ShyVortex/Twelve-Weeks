"""Death screen (victim POV) baked into the in-match HUD root (gui2-widgets.pak hud-root.widget, canvas.hudRoot), the same way
as hud_overlay_widgets (t2rBanner / t2rTitle): plain widgets, NO script, everything hidden; t2r-ext (feature_death_ui, log
'death ui:') drives visibility, alpha, texts and image paths.

  t2rDeath                 group (hidden, depth 30: above the banner / title card, hudMenuStack and the HUD)
    dBlack                 full-screen black (bleed), the fast fade to black at the kill frame
    dTip                   TLOU2 SP death tip, the native look: copies of hud-post-death-tip's icon0 (the 3840 x 1870
      dTipImg              illustration, streaming/large/death-tips/<name>.png) and label0 (45 pt ingame-read-text,
      dTipText             t2-tooltip, 2000 wide), same anchors / offsets as the SP widget
    dCard                  KILLED BY card bottom left, styled like to1/death-banner (killedByLabel / killerNameText /
      dKilledBy            killerWeaponIcon): red label, killer name, weapon icon (StretchAspect), weapon name
      dKiller
      dWIcon
      dWName
    dCount                 respawn countdown bottom right (stays up, small, while spectating)
      dCountShade          soft black gradient panel behind the countdown (menu-shade-sub.png)
      dCountLbl            "RESPAWNING IN" (t2-bright-grey)
      dCountNum / dCountNumB   the seconds, double-buffered (a gui2 text whose string changes draws nothing for a frame)
    dSpec                  the spectate prompt, bottom centre: input glyph image (gen:interact) + label
      dSpecIcon
      dSpecLbl             "SPECTATE TEAMMATE"
      dSpecLblB            "DEATH SCREEN" (shown while spectating)

    dSpecBar               spectating bar (only while spectating): dSpecShade panel, dSpecNameLbl "SPECTATING", dSpecNm / dSpecNmB the
                           teammate's name (double-buffered), dSwitch (dSwitchIcon glyph + dSwitchLbl "TO SWITCH TEAMMATES")

Widget space 3840 x 2160, y down. Opt-out on the ext side (t2r-no-death-ui.txt)."""
import copy
import json
import os
import t2guid

W, H = 3840, 2160
CARD_X, CARD_Y = 228, 1720           # KILLED BY card, top-left
COUNT_R, COUNT_Y = 3612, 1720        # countdown, right edge
COUNT_SHADE = "streaming/t2r/icons/death-count-shade.png"   # tools/models/make_icons.radial_shade (square, radial falloff)
SHADE_SUB = "streaming/t2r/clan/menu-shade-sub.png"         # tools/models/figures/ship.py (feathered rectangle)
SWITCH_GLYPH = "gen:attack"          # LMB / RT glyph, resolved by the engine (glyph id UNVERIFIED: check in game)
SPEC_Y = 1872                        # spectate prompt line (was 1990, under the engine's bottom black gradient; now inside the 90 % title-safe area, y < 1944)


def _items(wdir, rel):
    return json.load(open(os.path.join(wdir, *rel.split("/")), encoding="utf-8"))["items"]


def _tl(it, x, y, w, h):
    it.update({"anchorMinN.x": 0.0, "anchorMinN.y": 0.0, "anchorMaxN.x": 0.0, "anchorMaxN.y": 0.0,
               "pivotN.x": 0.0, "pivotN.y": 0.0, "pivotAs.x": float(x), "pivotAs.y": float(y),
               "rectSizeDelta.width": float(w), "rectSizeDelta.height": float(h)})
    return it


def _bc(it, dx, y, w, h):
    """Bottom-centre prompts: x anchored to the screen CENTRE (dx = offset from the centre in 3840-space), y from the top. The old
    top-left anchored x = 1920 - n sat left of centre on ultrawide (2560x1080 / 2560x1440, width-extended canvas)."""
    _tl(it, 0, y, w, h)
    it.update({"anchorMinN.x": 0.5, "anchorMaxN.x": 0.5, "pivotAs.x": float(dx)})
    return it


def _new(tmpl, parent, name, depth, **kw):
    c = copy.deepcopy(tmpl)
    c.pop("script", None)
    for k in ("engineClass", "animationsPath", "tags"):
        c.pop(k, None)
    c.update({"guid": t2guid.guid(), "parent": parent, "name": name, "depth": float(depth), "visible": 1,
              "focusable": 0, "color.a": 255, "animation": {"keyframes": {}}})
    if c.get("class") == "Text":
        c["cipherId"] = ""
    c.update(kw)
    return c


def add_death_ui(wdir):
    path = os.path.join(wdir, "hud-root.widget.json")
    w = json.load(open(path, encoding="utf-8"))
    if any(i["name"] == "t2rDeath" for i in w["items"]):
        return 0
    root = next(i for i in w["items"] if i["name"] == "root")
    grp_t = next(i for i in w["items"] if i["name"] == "rootFullscreen")
    tip = {i["name"]: i for i in _items(wdir, "hud-post-death-tip.widget.json")}
    db = {i["name"]: i for i in _items(wdir, "to1/death-banner.widget.json")}
    img_t = next(i for i in _items(wdir, "to1/picker-skill.widget.json") if i["name"] == "perkIcon")
    new = []

    def group(name, parent, depth, vis=1):
        g = _new(grp_t, parent, name, depth, visible=vis)
        g.update({"anchorMinN.x": 0.0, "anchorMinN.y": 0.0, "anchorMaxN.x": 1.0, "anchorMaxN.y": 1.0,
                  "pivotN.x": 0.5, "pivotN.y": 0.5, "pivotAs.x": 0.0, "pivotAs.y": 0.0,
                  "rectSizeDelta.width": 0.0, "rectSizeDelta.height": 0.0})
        new.append(g)
        return g["guid"]

    top = group("t2rDeath", root["guid"], 30.0, vis=0)
    # full-screen black: stretch anchors + a 1-canvas bleed on every side (any window aspect, clan_widgets.Builder.bleed)
    blk = _new(img_t, top, "dBlack", 0.0, path="general-textures/square-32px.png", scaleMode="Stretch",
               **{"tint.start": 0xFF000000, "tint.end": 0xFF000000})
    blk.update({"anchorMinN.x": 0.0, "anchorMinN.y": 0.0, "anchorMaxN.x": 1.0, "anchorMaxN.y": 1.0,
                "pivotN.x": 0.5, "pivotN.y": 0.5, "pivotAs.x": 0.0, "pivotAs.y": 0.0,
                "rectSizeDelta.width": 2.0 * W, "rectSizeDelta.height": 2.0 * H})
    new.append(blk)

    # ---- the SP death tip, native: icon0 / label0 as they are (anchored bottom centre)
    g = group("dTip", top, 1.0)
    new.append(_new(tip["icon0"], g, "dTipImg", 0.0, path="streaming/large/death-tips/cover-from-gunfire.png"))
    new.append(_new(tip["label0"], g, "dTipText", 1.0, text="Stay crouched behind cover to protect from gunfire.",
                    **{"rectSizeDelta.height": 200.0}))

    # ---- KILLED BY card (to1/death-banner styling)
    g = group("dCard", top, 2.0)
    new.append(_tl(_new(db["killedByLabel"], g, "dKilledBy", 0.0, text="KILLED BY"), CARD_X, CARD_Y, 1400, 50))
    new.append(_tl(_new(db["killerNameText"], g, "dKiller", 1.0, text="PLAYER", pointSize=64), CARD_X, CARD_Y + 58, 1400, 96))
    wi = _new(db["killerWeaponIcon"], g, "dWIcon", 2.0, path="hud/weapons/guns/rifle-vepr/vepr.png")
    wi.update({"pivotN.x": 0.0, "pivotN.y": 0.0, "alignH": 0})
    new.append(_tl(wi, CARD_X, CARD_Y + 170, 400, 150))
    wn = _new(db["killerNameText"], g, "dWName", 3.0, text="VARIABLE RIFLE", pointSize=40, faceId="Alternate",
              **{"tint.start": "t2-bright-grey", "tint.end": "t2-bright-grey", "tracking.x": 6.0})
    new.append(_tl(wn, CARD_X + 430, CARD_Y + 210, 1100, 70))

    # ---- respawn countdown (to1/death-banner respawnLabel / respawnNumber), right aligned
    g = group("dCount", top, 3.0)
    # soft black gradient panel behind the countdown (readable over the spectate view): the feathered rectangle the MP menus
    # use behind their details panels (shade_widgets: streaming/t2r/clan/menu-shade-sub.png, black, alpha 0.66 at the core, fading to 0 at
    # every edge), first in the group = drawn first = behind the texts. Stretched over the countdown block plus feather room.
    sh = _new(img_t, g, "dCountShade", -1.0, path=COUNT_SHADE, scaleMode="Stretch",
              **{"tint.start": 0xFFFFFFFF, "tint.end": 0xFFFFFFFF})
    # Was a huge feathered rectangle; now a small SQUARE (radial falloff: soft edges and corners) around the countdown block
    new.append(_tl(sh, COUNT_R - 520, COUNT_Y - 190, 600, 600))
    new.append(_tl(_new(db["respawnLabel"], g, "dCountLbl", 0.0, text="RESPAWNING IN", alignH=2),
                   COUNT_R - 1400, COUNT_Y, 1400, 50))
    for nm, vis in (("dCountNum", 1), ("dCountNumB", 0)):
        new.append(_tl(_new(db["respawnNumber"], g, nm, 1.0, text="10", pointSize=110, alignH=2, visible=vis),
                       COUNT_R - 600, COUNT_Y + 58, 600, 150))

    # E and F share one hierarchy, with the dark gradient behind both: the bar group is emitted BEFORE the E prompt group,
    # items later in the list draw on top, so the band's shade no longer dims the E row (it was emitted after it and covered it)
    # ---- spectating bar, bottom centre above the E prompt: "SPECTATING" (red death-banner label style) + the teammate's name
    # (killer-name style, double-buffered like the countdown) on a dark soft panel, and the switch prompt: the engine's input glyph
    # (SWITCH_GLYPH: LMB on keyboard / RT on a pad) + "TO SWITCH TEAMMATES". Alpha driven by t2r-ext (DT_BAR / DT_SWITCH).
    g = group("dSpecBar", top, 3.5)
    shd = _new(img_t, g, "dSpecShade", -1.0, path=SHADE_SUB, scaleMode="Stretch", **{"tint.start": 0xFFFFFFFF, "tint.end": 0xFFFFFFFF})
    new.append(_bc(shd, -1000, 1540, 2000, 500))   # (uifix.png: the E row sat on the feathered bottom edge): band 1540..2040, the feather leaves ~the same visible margin under the E row as above SPECTATING
    new.append(_bc(_new(db["killedByLabel"], g, "dSpecNameLbl", 0.0, text="SPECTATING", alignH=1), -700, 1618, 1400, 50))
    for nm, vis in (("dSpecNm", 1), ("dSpecNmB", 0)):
        new.append(_bc(_new(db["killerNameText"], g, nm, 1.0, text="PLAYER", pointSize=64, alignH=1, visible=vis), -700, 1676, 1400, 96))
    sg = group("dSwitch", g, 2.0)
    ic = _new(img_t, sg, "dSwitchIcon", 0.0, path=SWITCH_GLYPH, scaleMode="StretchAspect", alignH=1, alignV=1,
              slices=[0.328125] * 4, **{"tint.start": "t2-white", "tint.end": "t2-white"})
    new.append(_bc(ic, -380, 1790, 72, 72))
    new.append(_bc(_new(db["respawnLabel"], sg, "dSwitchLbl", 1.0, text="TO SWITCH TEAMMATES", pointSize=40,
                        **{"tint.start": "t2-white", "tint.end": "t2-white"}), -288, 1794, 900, 64))
    # ---- spectate prompt: the input glyph (the way the menus draw "menu:select") + a label
    g = group("dSpec", top, 4.0)
    ic = _new(img_t, g, "dSpecIcon", 0.0, path="gen:interact", scaleMode="StretchAspect", alignH=1, alignV=1,
              slices=[0.328125] * 4, **{"tint.start": "t2-white", "tint.end": "t2-white"})
    new.append(_bc(ic, -380, SPEC_Y - 4, 72, 72))   # E row on the same column as the F row (icon -380, label -288)
    for nm, txt, vis in (("dSpecLbl", "SPECTATE TEAMMATE", 1), ("dSpecLblB", "DEATH SCREEN", 0)):
        new.append(_bc(_new(db["respawnLabel"], g, nm, 1.0, text=txt, pointSize=40, visible=vis,
                            **{"tint.start": "t2-white", "tint.end": "t2-white"}), -288, SPEC_Y, 900, 64))
    w["items"].extend(new)
    json.dump(w, open(path, "w", encoding="utf-8"), indent=4)
    return len(new)


if __name__ == "__main__":                 # python death_ui_widgets.py <extracted widget dir>: dry run on a copy
    import shutil
    import sys
    import tempfile
    src = sys.argv[1]
    t = tempfile.mkdtemp()
    for rel in ("hud-root.widget.json", "hud-post-death-tip.widget.json", "to1/death-banner.widget.json", "to1/picker-skill.widget.json"):
        os.makedirs(os.path.dirname(os.path.join(t, rel)), exist_ok=True)
        shutil.copy(os.path.join(src, rel), os.path.join(t, rel))
    print(add_death_ui(t), "widgets")
    for i in json.load(open(os.path.join(t, "hud-root.widget.json"), encoding="utf-8"))["items"][-24:]:
        print(i["name"], i.get("class"), i.get("pivotAs.x"), i.get("pivotAs.y"), i.get("path", ""), i.get("text", ""))
    shutil.rmtree(t)
