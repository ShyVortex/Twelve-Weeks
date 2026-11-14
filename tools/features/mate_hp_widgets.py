"""Teammate health bars under the nametags baked into the in-match HUD root (gui2-widgets.pak hud-root.widget, canvas.hudRoot): plain images, no script, hidden.

For each of the T2R_MAX_PEERS (8) net slots, six image widgets (t2rMh<kind><slot>):
  T  track   pill, dark, soft rim (ship.make_mate_track), TRACK_W x TRACK_H canvas units
  G A R C    fill in green / amber / red / healing cyan (ship.make_mate_fill), FILL_W x FILL_H, inset FILL_X / FILL_Y in the track
  K  ticks   four thin dark dividers at 20 / 40 / 60 / 80 % (ship.make_mate_ticks), over the fill, same rect (2013 'five bars = 100 HP' readability)
All top-left pivoted (pivotN 0,0), x anchored to the screen centre like the dodge bar (_bc). t2r-ext (t2r-ext.c tag_mate_hp, log 'mate hp:') sets
per frame, for the teammate whose nametag is drawn: pivotAs (gui2-rxfm-set-pivot-as) = the tag's projected position in 3840 x 2160 units, x/y scale
(gui2-rxfm-set-scale-ps) = tag size (fill: x scale also x health fraction, the widget scales about its top-left corner), alpha = tag alpha, visibility
(only the fill of the current colour). A tag not drawn this frame hides all six.
No runtime tint exists (the mark triangle tried it), hence one fill widget per colour."""
import copy  # noqa: F401
import death_ui_widgets as D

SLOTS = 8
TRACK_W, TRACK_H = 240, 18          # 80 x 6 px of the 1280 x 720 box
FILL_X, FILL_Y = 6, 5               # fill zone inset in the track (the pill's round caps stay clear)
FILL_W, FILL_H = 228, 8
PATH = "streaming/t2r/clan/"
KINDS = (("T", "mate-track", TRACK_W, TRACK_H, 0, 0, 6.50),
         ("G", "mate-fill-g", FILL_W, FILL_H, FILL_X, FILL_Y, 6.52),
         ("A", "mate-fill-a", FILL_W, FILL_H, FILL_X, FILL_Y, 6.52),
         ("R", "mate-fill-r", FILL_W, FILL_H, FILL_X, FILL_Y, 6.52),
         ("C", "mate-fill-c", FILL_W, FILL_H, FILL_X, FILL_Y, 6.52),
         ("K", "mate-ticks", FILL_W, FILL_H, FILL_X, FILL_Y, 6.54))


def add_mate_hp(wdir):
    path = D.os.path.join(wdir, "hud-root.widget.json")
    w = D.json.load(open(path, encoding="utf-8"))
    if any(i["name"] == "t2rMhT0" for i in w["items"]):
        return 0
    root = next(i for i in w["items"] if i["name"] == "root")
    db = {i["name"]: i for i in D._items(wdir, "to1/death-banner.widget.json")}
    n = 0
    for s in range(SLOTS):
        for kind, img, bw, bh, ox, oy, depth in KINDS:
            b = D._new(db["killerWeaponIcon"], root["guid"], f"t2rMh{kind}{s}", depth, path=PATH + img + ".png", scaleMode="Stretch", alignH=0, alignV=0,
                       visible=0, **{"tint.start": 0xFFFFFFFF, "tint.end": 0xFFFFFFFF})
            D._bc(b, -TRACK_W // 2 + ox, 1500 + oy, bw, bh)
            w["items"].append(b)
            n += 1
    D.json.dump(w, open(path, "w", encoding="utf-8"), indent=4)
    return n
