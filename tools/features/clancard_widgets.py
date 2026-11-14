"""Clan card widgets. Two things, both baked into the HUD / pause pages:

1. PERK POP (mockup clan-perk-pop-v5-zoom.png): NO frame / circle. A grainy smoky dark band (popBand, clan-pop-band.png) with the member's portrait (its own soft
   alpha edges) straight on it, "<NAME> PROVIDED YOU WITH <ITEM>!" + the dim "ROLE - FROM YOUR CLAN" subline to its right and a faint grey item icon at the far end. Group perkPop >
   row perkPopRow (hidden; t2r-ext clancard.c slides it in from the left and drives its alpha) with leaves: popBand popPt popTx popSb popBig. Placed on the left, mid-height.
2. the ESC (pause) menu list of status updates (bottom of this file)."""
import copy
import os
import t2guid
import death_ui_widgets as D

POP_W, POP_H = 2400.0, 520.0                       # card box (canvas units = 4K px); resting x / y: clancard.c CC_POP_X / CC_POP_Y (left, mid-height)
POP_BAND = "streaming/t2r/icons/clan-pop-band.png"  # tools/models/make_icons.clan_pop_band
POP_HEAD = "streaming/t2r/icons/c13p-100_neutral.png"   # replaced per member at run time (c13p-<model>_<expr>.png)
POP_ICON = "streaming/t2r/icons/notify-info.png"   # replaced per perk at run time
POP_PT = 380.0                                      # portrait box (square)
POP_PT_X = 120.0
POP_TX_X = POP_PT_X + POP_PT - 30.0
POP_TX_W = 1500.0
POP_ICON_X, POP_ICON_U = 2020.0, 225.0
POP_LEAVES = ("popBand", "popBig", "popPt", "popTx", "popSb")


def add_perk_pop(wdir):
    path = os.path.join(wdir, "to1", "currency-hud.widget.json")
    w = D.json.load(open(path, encoding="utf-8"))
    items = w["items"]
    if any(i["name"] == "perkPop" for i in items):
        return 0
    import clan_widgets as CWG
    root = next(i for i in items if i["name"] == "root")
    grp = next(i for i in items if i["name"] == "partsRow")
    img = next(i for i in items if i["name"] == "partsRowIcon")
    txt = next(i for i in items if i["name"] == "partsAmount")

    def place(c, x, y, wd, ht):
        c.update({"anchorMinN.x": 0.0, "anchorMinN.y": 0.0, "anchorMaxN.x": 0.0, "anchorMaxN.y": 0.0, "pivotN.x": 0.0, "pivotN.y": 0.0,
                  "pivotAs.x": float(x), "pivotAs.y": float(y), "rectSizeDelta.width": float(wd), "rectSizeDelta.height": float(ht)})

    def group(name, parent, x, y, wd, ht, vis):
        g = copy.deepcopy(grp)
        g.update(guid=t2guid.guid(), name=name, parent=parent, visible=vis)
        place(g, x, y, wd, ht)
        return g

    def image(name, parent, icon, x, y, wd, ht, argb, scale, vis=1):
        c = copy.deepcopy(img)
        c.update(guid=t2guid.guid(), name=name, parent=parent, visible=vis, path=icon, depth=0.0, scaleMode=scale)
        place(c, x, y, wd, ht)
        c.update({"tint.start": argb, "tint.end": argb, "color.a": 255})
        return c

    def text(name, parent, s, x, y, wd, ht, pt, argb):
        t = copy.deepcopy(txt)
        t.update(guid=t2guid.guid(), name=name, parent=parent, visible=1, text=s, cipherId="", pointSize=pt, alignH=0, alignV=1, multiline=1, depth=0.0)
        place(t, x, y, wd, ht)
        t.update({"tint.start": argb, "tint.end": argb, "color.a": 255})
        return t
    top = group("perkPop", root["guid"], 0.0, 0.0, 3840.0, 2160.0, 1)
    row = group("perkPopRow", top["guid"], -POP_W - 150.0, 1304.0, POP_W, POP_H, 0)   # left, centred between the team score and the parts counter (clancard.c CC_POP_Y; scaled 0.55 at runtime)
    g = row["guid"]
    new = [top, row]
    new.append(image("popBand", g, POP_BAND, 0.0, 0.0, POP_W, POP_H, 0xFFFFFFFF, "Stretch"))   # opaque white tint: the PNG is black with its own alpha, ext drives widget alpha
    new.append(image("popBig", g, POP_ICON, POP_ICON_X, POP_H / 2 - POP_ICON_U / 2 - 20.0, POP_ICON_U, POP_ICON_U, 0xFFB4B4B4, "StretchAspect"))   # faint grey item icon, alpha by the ext
    new.append(image("popPt", g, POP_HEAD, POP_PT_X, (POP_H - POP_PT) / 2, POP_PT, POP_PT, 0xFFFFFFFF, "StretchAspect", 0))
    t = text("popTx", g, "", POP_TX_X, POP_H / 2 - 80.0 - 50.0, POP_TX_W, 100.0, 50, 0xFFEFEBE3)
    t["tracking.x"] = 4.0
    t["multiline"] = 0
    new.append(t)
    sb = text("popSb", g, "", POP_TX_X, POP_H / 2 - 15.0 - 22.0, POP_TX_W, 44.0, 27, 0xFF8A8985)   # the dim subline: ROLE - FROM YOUR CLAN
    sb["multiline"] = 0
    sb["tracking.x"] = 7.0
    new.append(sb)
    items.extend(new)
    D.json.dump(w, open(path, "w", encoding="utf-8"), indent=4)
    return len(new)


# ---- the ESC (pause) menu list (in game, status updates appear ONLY here) ----
# to1/pause-menu: group pauseStatus under the mission block (top right): head CLAN NEWS, rule, up to 4 rows pst0-3 (text, <font color> markup per state), all hidden until
# t2r-ext (clancard.c cc_pause_tick) fills and shows them when the page is up and an update is pending.
PS_ROWS = 4
PS_H0, PS_ROW_H = 96, 56


def add_pause_status(wdir):
    import clan_widgets as CWG
    path = os.path.join(wdir, "to1", "pause-menu.widget.json")
    if not os.path.exists(path):
        return 0
    page = D.json.load(open(path, encoding="utf-8"))
    if any(i["name"] == "pauseStatus" for i in page["items"]):
        return 0
    main = D.json.load(open(os.path.join(wdir, "to1", "main-menu.widget.json"), encoding="utf-8"))
    t, _, _ = CWG._templates(main)
    anim = next(i for i in page["items"] if i["name"] == "anim-group")
    b = CWG.Builder(t)
    mx, my, mw, mh = CWG.pause_rects()["pauseMission"]
    h = PS_H0 + PS_ROWS * PS_ROW_H + 24
    pad = CWG.PZ_MIS_PAD
    g = b.group("pauseStatus", anim["guid"], b.tl(mx, my + mh + 30, mw, h), visible=0, depth=4.5)["guid"]
    b.image("psBlur", g, b.fill(), "general-textures/blur-background.png", 0xFFFFFFFF, 255)
    b.rect("psBg", g, b.fill(), 0xFF000000, 150)
    b.line("psLineL", g, 0, 0, 0, h, 0xFFFFFFFF, 130, 2.0)
    b.line("psLineR", g, mw, 0, mw, h, 0xFFFFFFFF, 130, 2.0)
    b.text("psHead", g, b.tl(pad, 14, 700, 70), "CLAN NEWS:", 43, 0xFFE6E6E6, tracking=4)
    b.line("psRule", g, pad - 4, 88, mw - pad + 4, 88, 0xFFFFFFFF, 130, 2.0)
    for k in range(PS_ROWS):
        b.text("pst%d" % k, g, b.tl(pad, PS_H0 + k * PS_ROW_H, mw - 2 * pad, PS_ROW_H), "", 34, 0xFFE6E6E6, tracking=2)
    at = next(k for k, i in enumerate(page["items"]) if i["name"] == "versionText")
    page["items"][at:at] = b.items
    D.json.dump(page, open(path, "w", encoding="utf-8"), indent=4)
    return len(b.items)
