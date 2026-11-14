"""No Return style HUD overlays baked into the in-match HUD root (gui2-widgets.pak: hud-root.widget, the widget the game spawns as
canvas.hudRoot - its children are rootFullscreen, hudMenuStack, topCenterMessage, healthAndAmmoV2 ...). Both are plain widgets with NO
script (the NR widgets run ss-rogue-title-card etc.; here t2r-ext drives text and alpha, re/no-return-analysis.md 3.1 / 3.2 / 6.1 / 6.3):

  t2rBanner          group (hidden), alpha driven by the ext: band: one smooth gradient image, full width, centred;, card (slid by the ext) with
    sub              Text, 44 pt team line (WLF WIN / SERAPHITES WIN)
    win              Text "VICTORY" t2-yellow, style complete-header, SoftOutline (= t2r-hud-encounter-over's text)
    lose             Text "DEFEAT"  t2-red, same
    draw             Text "DRAW"    t2-white, same (the match ended level)
    lineL / lineR    the two thin Polylines flanking the text (encounter-over's left-line / right-line)
  t2rTitle           Text, map / mode line (t2r-hud-title-card: 149 pt Design face, t2-white, top left 228 / 245 of 3840x2160)
  t2rTitleSub        Text, second line 1.5 s later (56 pt size-number-extra-large, t2-tooltip, y 475)

Everything starts hidden (visible 0, alpha 1); the ext shows them with gui2-set-widget-visible / -alpha. Opt-out is on the ext side
(t2r-no-end-banner.txt, t2r-no-title-card.txt) - the baked widgets are invisible and harmless without it."""
import copy
import json
import os
import t2guid


BAND_IMG = "streaming/t2r/clan/result-band.png"
BAND_H = 700.0       # units (3840 x 2160 canvas); gradient peak plateau is the middle ~28 %
TXT_DX = 0.0         # measured: the in-game glyphs were already horizontally centred (screenshot Victory.png)


def _text(tmpl, parent, name, text, depth, **kw):
    t = copy.deepcopy(tmpl)
    t.pop("script", None)
    t.update({"guid": t2guid.guid(), "parent": parent, "name": name, "text": text, "depth": depth, "visible": 0,
              "cipherId": "", "focusable": 0, "color.a": 255})
    t.update(kw)
    return t


def add_hud_overlays(wdir):
    path = os.path.join(wdir, "hud-root.widget.json")
    w = json.load(open(path, encoding="utf-8"))
    names = {i["name"] for i in w["items"]}
    if "t2rBanner" in names:
        return 0
    root = next(i for i in w["items"] if i["name"] == "root")
    tmpl = next(i for i in w["items"] if i["name"] == "topCenterMessage")
    grp_t = next(i for i in w["items"] if i["name"] == "rootFullscreen")
    eo = json.load(open(os.path.join(wdir, "t2r-hud-rogue", "t2r-hud-encounter-over.widget.json"), encoding="utf-8"))
    line_t = next(i for i in eo["items"] if i["name"] == "left-line")
    new = []

    def center(it, x, y, wd, ht):      # anchor = screen centre, pivotAs = offset from it (y down)
        it.update({"anchorMinN.x": 0.5, "anchorMinN.y": 0.5, "anchorMaxN.x": 0.5, "anchorMaxN.y": 0.5,
                   "pivotN.x": 0.5, "pivotN.y": 0.5, "pivotAs.x": float(x), "pivotAs.y": float(y),
                   "rectSizeDelta.width": float(wd), "rectSizeDelta.height": float(ht)})
        return it
    img_t = next(i for i in json.load(open(os.path.join(wdir, "to1", "picker-skill.widget.json"), encoding="utf-8"))["items"]
                 if i["name"] == "perkIcon")
    g = copy.deepcopy(grp_t)
    g.update({"guid": t2guid.guid(), "parent": root["guid"], "name": "t2rBanner", "depth": 20.0, "visible": 0})
    new.append(g)
    # darkened background: ONE image, a smooth vertical gradient PNG (streaming/t2r/clan/result-band.png, tools/models/figures/ship.py
    # make_band), full width, BAND_H units tall, centred on the screen's vertical centre = the card's centre
    b = copy.deepcopy(img_t)
    b.update({"guid": t2guid.guid(), "parent": g["guid"], "name": "band", "depth": 0.0, "visible": 1,
              "path": BAND_IMG, "scaleMode": "Stretch", "color.a": 255, "rotation": 0.0,
              "tint.start": 0xFFFFFFFF, "tint.end": 0xFFFFFFFF,
              "anchorMinN.x": 0.0, "anchorMaxN.x": 1.0, "anchorMinN.y": 0.5, "anchorMaxN.y": 0.5,
              "pivotN.x": 0.5, "pivotN.y": 0.5, "pivotAs.x": 0.0, "pivotAs.y": 0.0,
              "rectSizeDelta.width": 0.0, "rectSizeDelta.height": float(BAND_H)})
    new.append(b)
    card = copy.deepcopy(grp_t)
    card.update({"guid": t2guid.guid(), "parent": g["guid"], "name": "card", "depth": 5.0, "visible": 1})
    card.update({"anchorMinN.x": 0.5, "anchorMaxN.x": 0.5, "anchorMinN.y": 0.5, "anchorMaxN.y": 0.5, "pivotN.x": 0.5,
                 "pivotN.y": 0.5, "pivotAs.x": 0.0, "pivotAs.y": 0.0, "rectSizeDelta.width": 3200.0, "rectSizeDelta.height": 200.0})
    new.append(card)
    for nm, txt, tint in (("win", "VICTORY", "t2-yellow"), ("lose", "DEFEAT", "t2-red"), ("draw", "DRAW", "t2-white")):   # draw (equal reinforcements)
        t = _text(tmpl, card["guid"], nm, txt, 1.0, alignH=1, alignV=1, pointSize=96, effect="SoftOutline",
                  style="complete-header", **{"tint.start": tint, "tint.end": tint, "tracking.x": 16.0})
        center(t, TXT_DX, 0, 1600, 150)
        new.append(t)
    sub = _text(tmpl, card["guid"], "sub", "WLF WIN", 1.1, alignH=1, alignV=1, pointSize=44, effect="SoftOutline",
                style="size-number-extra-large", **{"tint.start": "t2-tooltip", "tint.end": "t2-tooltip", "tracking.x": 10.0})
    center(sub, TXT_DX, 90, 1600, 80)
    new.append(sub)
    for nm, x, pv in (("lineL", -470, 1.0), ("lineR", 470, 0.0)):
        ln = copy.deepcopy(line_t)
        ln.update({"guid": t2guid.guid(), "parent": card["guid"], "name": nm, "depth": 2.0, "visible": 1})
        center(ln, x, 0, 600, 0)
        ln["pivotN.x"] = pv
        new.append(ln)
    for nm, txt, size, y, tint, extra in (
            ("t2rTitle", "TITLE", 149, 245.0, "t2-white", {"faceId": "Design"}),
            ("t2rTitleSub", "SUBTITLE", 56, 475.0, "t2-tooltip", {"style": "size-number-extra-large"})):
        t = _text(tmpl, root["guid"], nm, txt, 21.0 if nm == "t2rTitle" else 22.0, alignH=0, alignV=1, pointSize=size,
                  effect="SoftOutline", **{"tint.start": tint, "tint.end": tint}, **extra)
        t.update({"anchorMinN.x": 0.0, "anchorMinN.y": 0.0, "anchorMaxN.x": 0.0, "anchorMaxN.y": 0.0,
                  "pivotN.x": 0.0, "pivotN.y": 0.5, "pivotAs.x": 228.0, "pivotAs.y": y,
                  "rectSizeDelta.width": 3000.0, "rectSizeDelta.height": 230.0})
        new.append(t)
    w["items"].extend(new)
    json.dump(w, open(path, "w", encoding="utf-8"), indent=4)
    return len(new)
