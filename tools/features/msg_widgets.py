"""Our HUD message line baked into the in-match HUD root (gui2-widgets.pak hud-root.widget, canvas.hudRoot), the same way as
hud_overlay_widgets / death_ui_widgets: plain Text widgets, NO script, hidden; t2r-ext (msg_hook, log 'msg:') sets the string
with gui2's own set-text and drives visibility / alpha.

  t2rMsg / t2rMsgB   two copies of the HUD's own topCenterMessage (same font, size, colour, anchors, place), double-buffered
                     (a gui2 text whose string changes draws nothing for a frame: the ext writes the hidden one, then swaps)

  t2rMsgIcon         Image (hidden): the Covert Training III badge (streaming/t2r/icons/skill-covert.png), same anchor as t2rMsg; t2r-ext
                     (feature_msg_tag_draw) moves it left of the nametag-style message text and fades it with the text (an <img>
                     tag inside the Text drew nothing)

Why: every message went through winmm's HUD message call, which shows a TEXT ID; all our messages shared one id
whose table text is "Placeholder text. " x100 and the HUD caches the rendered text per id - "Healing teammate..." came up as a wall
of placeholder text or as the previous message ("Food: +40 health"). A widget whose string we set needs no text id at all."""
import copy
import json
import os
import t2guid

NAMES = ("t2rMsg", "t2rMsgB")
ICON = "t2rMsgIcon"
ICON_PATH = "streaming/t2r/icons/skill-covert-hud.png"   # thick-ring HUD variant (skill_icons.py)   # tools/models/skill_icons.py, staged by build_dll with the t2r icons
ICON_SIZE = 78.0      # canvas units (3840 x 2160) = 26 px of the 1280 x 720 text space (t2r-ext MT_ICON_PX)


def add_msg_line(wdir):
    path = os.path.join(wdir, "hud-root.widget.json")
    w = json.load(open(path, encoding="utf-8"))
    items = w["items"]
    tmpl = next(i for i in items if i["name"] == "topCenterMessage")
    n = 0
    if not any(i["name"] in NAMES for i in items):
        for nm in NAMES:
            c = copy.deepcopy(tmpl)
            c.pop("script", None)
            for k in ("engineClass", "animationsPath", "tags"):
                c.pop(k, None)
            c.update({"guid": t2guid.guid(), "name": nm, "text": "", "cipherId": "", "visible": 0, "focusable": 0,
                      "color.a": 255, "animation": {"keyframes": {}}})
            items.append(c)
            n += 1
    if not any(i["name"] == ICON for i in items):
        img_t = next(i for i in json.load(open(os.path.join(wdir, "to1", "picker-skill.widget.json"), encoding="utf-8"))["items"]
                     if i["name"] == "perkIcon")
        c = copy.deepcopy(img_t)
        c.pop("script", None)
        c.update({"guid": t2guid.guid(), "parent": tmpl["parent"], "name": ICON, "depth": float(tmpl["depth"]) + 0.1, "visible": 0,
                  "focusable": 0, "path": ICON_PATH, "scaleMode": "StretchAspect", "color.a": 255, "rotation": 0.0,
                  "tint.start": "t2-white", "tint.end": "t2-white", "animation": {"keyframes": {}},
                  "anchorMinN.x": tmpl["anchorMinN.x"], "anchorMinN.y": tmpl["anchorMinN.y"],
                  "anchorMaxN.x": tmpl["anchorMaxN.x"], "anchorMaxN.y": tmpl["anchorMaxN.y"],
                  "pivotN.x": 0.5, "pivotN.y": 0.5, "pivotAs.x": 0.0, "pivotAs.y": tmpl["pivotAs.y"],
                  "rectSizeDelta.width": ICON_SIZE, "rectSizeDelta.height": ICON_SIZE})
        items.append(c)
        n += 1
    if n:
        json.dump(w, open(path, "w", encoding="utf-8"), indent=1)
    return n
