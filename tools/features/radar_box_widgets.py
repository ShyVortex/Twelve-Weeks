"""Supply box icons for the radar, baked into the in-match HUD root (gui2-widgets.pak hud-root.widget, canvas.hudRoot): 12 plain image widgets t2rRbx0..11,
hidden, NO script. The image is TLOU2's own No Return crate marker (hud-buddy-status/rogue-attachable icon0): the stock texture
hud/interactions/marker-lootbox.png (white chest glyph, 162 x 132, extracted to re/radar/marker-lootbox-1080.png), tinted pure white (the grey 0xDCDCDC tint read grey on the radar).
t2r-ext (radar_box.c, log 'radar box:') records where winmm's radar draws each box blip and moves one widget onto each (gui2-rxfm-set-pivot-as, like the
teammate health bars), alpha = the radar's fade. Top-left pivoted, x anchored to the screen centre (_bc). W x H canvas units = radar_box.c RBX_W / RBX_H."""
import death_ui_widgets as D

N = 12
W = 72
H = 59
PATH = "hud/interactions/marker-lootbox.png"
TINT = 0xFFFFFFFF


def add_radar_box(wdir):
    """Into the currency-hud PAGE (to1/currency-hud, which also holds the radar disc radarVig and is drawn over hud-root), after the disc; top-left anchored."""
    path = D.os.path.join(wdir, "to1", "currency-hud.widget.json")
    w = D.json.load(open(path, encoding="utf-8"))
    if any(i["name"] == "t2rRbx0" for i in w["items"]):
        return 0
    root = next(i for i in w["items"] if i["name"] == "root")
    tmpl = next(i for i in w["items"] if i["name"] == "partsRowIcon")
    for s in range(N):
        b = D._new(tmpl, root["guid"], "t2rRbx%d" % s, 6.60 + s * 0.001, path=PATH, scaleMode="Stretch", visible=0, **{"tint.start": TINT, "tint.end": TINT})
        b.update({"anchorMinN.x": 0.0, "anchorMinN.y": 0.0, "anchorMaxN.x": 0.0, "anchorMaxN.y": 0.0, "pivotN.x": 0.0, "pivotN.y": 0.0,
                  "pivotAs.x": 0.0, "pivotAs.y": 0.0, "rectSizeDelta.width": float(W), "rectSizeDelta.height": float(H)})
        w["items"].append(b)
    D.json.dump(w, open(path, "w", encoding="utf-8"), indent=4)
    return N


def add_radar_box_hudroot(wdir):
    path = D.os.path.join(wdir, "hud-root.widget.json")
    w = D.json.load(open(path, encoding="utf-8"))
    if any(i["name"] == "t2rRbx0" for i in w["items"]):
        return 0
    root = next(i for i in w["items"] if i["name"] == "root")
    db = {i["name"]: i for i in D._items(wdir, "to1/death-banner.widget.json")}
    for s in range(N):
        b = D._new(db["killerWeaponIcon"], root["guid"], "t2rRbx%d" % s, 6.60 + s * 0.001, path=PATH, scaleMode="Stretch", alignH=0, alignV=0,
                   visible=0, **{"tint.start": TINT, "tint.end": TINT})
        D._bc(b, -W // 2, 1500, W, H)
        w["items"].append(b)
    D.json.dump(w, open(path, "w", encoding="utf-8"), indent=4)
    return N


PATH_UP = "streaming/t2r/icons/radar-box-up.png"        # make_icons.radar_box_floor: the grey crate + a small white arrow, same 162 x 132 canvas as the stock icon
PATH_DOWN = "streaming/t2r/icons/radar-box-down.png"


def add_radar_box_floor(wdir):
    """The radar icon of a supply box on another floor (t2r-ext radar_box.c, nrbox.c nrbox_floor_update, log 'box floor:'): t2rRbxU0..11 (grey crate + arrow up) and t2rRbxD0..11
    (arrow down), same page / size / pivot setup as t2rRbx0..11, hidden; radar_box.c shows the one for the box's state on its blip."""
    path = D.os.path.join(wdir, "to1", "currency-hud.widget.json")
    w = D.json.load(open(path, encoding="utf-8"))
    if any(i["name"] == "t2rRbxU0" for i in w["items"]):
        return 0
    root = next(i for i in w["items"] if i["name"] == "root")
    tmpl = next(i for i in w["items"] if i["name"] == "partsRowIcon")
    n = 0
    for tag, tex, dz in (("U", PATH_UP, 0.0), ("D", PATH_DOWN, 0.0005)):
        for s in range(N):
            b = D._new(tmpl, root["guid"], "t2rRbx%s%d" % (tag, s), 6.60 + s * 0.001 + dz, path=tex, scaleMode="Stretch", visible=0, **{"tint.start": TINT, "tint.end": TINT})
            b.update({"anchorMinN.x": 0.0, "anchorMinN.y": 0.0, "anchorMaxN.x": 0.0, "anchorMaxN.y": 0.0, "pivotN.x": 0.0, "pivotN.y": 0.0,
                      "pivotAs.x": 0.0, "pivotAs.y": 0.0, "rectSizeDelta.width": float(W), "rectSizeDelta.height": float(H)})
            w["items"].append(b)
            n += 1
    D.json.dump(w, open(path, "w", encoding="utf-8"), indent=4)
    return n


PATH_ARC = "streaming/t2r/icons/radar-box-arc.png"      # make_icons.radar_box_arc: a soft arc on the inside of the radar rim, centred at 12 o'clock, 450 px = the radar disc
ARC_STEPS = 60                                          # = radar_box.c RBX_ARC_N: copies turned 6 degrees apart (no native sets a rotation at runtime, cf. load_indicator_widgets)
ARC_GREY = 0xFF8C8C8C                                   # same grey as the other-floor crate (make_icons.radar_box_floor)


def add_radar_box_arcs(wdir):
    """Boxes outside the radar's range show as an arc on the rim at their direction: t2rRbxA0..59 (white = same floor) and t2rRbxG0..59 (grey = another floor), the arc
    texture at layout rotation 6 * k degrees about the radar centre, hidden; t2r-ext radar_box.c shows the ones at the bearings of the out-of-range boxes. In the currency-hud page
    right after the radar disc (depth 6.59, under the crate icons); centred on the disc like radarVig (clan_widgets.RADAR_CX / CY / D)."""
    import clan_widgets as C
    path = D.os.path.join(wdir, "to1", "currency-hud.widget.json")
    w = D.json.load(open(path, encoding="utf-8"))
    if any(i["name"] == "t2rRbxA0" for i in w["items"]):
        return 0
    root = next(i for i in w["items"] if i["name"] == "root")
    tmpl = next(i for i in w["items"] if i["name"] == "partsRowIcon")
    n = 0
    for tag, tint, dz in (("G", ARC_GREY, 0.0), ("A", 0xFFFFFFFF, 0.0005)):       # grey first (under), white over it where both sit on one step
        for s in range(ARC_STEPS):
            b = D._new(tmpl, root["guid"], "t2rRbx%s%d" % (tag, s), 6.59 + s * 0.00001 + dz, path=PATH_ARC, scaleMode="Stretch", visible=0, **{"tint.start": tint, "tint.end": tint})
            b.update({"anchorMinN.x": 0.0, "anchorMinN.y": 0.0, "anchorMaxN.x": 0.0, "anchorMaxN.y": 0.0, "pivotN.x": 0.5, "pivotN.y": 0.5,
                      "pivotAs.x": C.RADAR_CX, "pivotAs.y": C.RADAR_CY, "rectSizeDelta.width": C.RADAR_D, "rectSizeDelta.height": C.RADAR_D,
                      "rotation": 360.0 * s / ARC_STEPS})
            w["items"].append(b)
            n += 1
    D.json.dump(w, open(path, "w", encoding="utf-8"), indent=4)
    return n
