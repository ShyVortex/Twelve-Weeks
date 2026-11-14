"""Melee dodge cooldown line baked into the in-match HUD root (gui2-widgets.pak hud-root.widget, canvas.hudRoot): ONE plain image, no script, hidden.

  t2rDodgeBar     image streaming/t2r/clan/dodge-bar.png (ship.make_dodge_bar: white line, feathered ends and long edges), BAR_W x BAR_H canvas units,
                  centred on the screen centre in x (anchor 0.5, pivotAs.x = -BAR_W / 2 at full length), top-left pivot. t2r-ext (melee_dodge.c, log 'dodge:')
                  shows it after a dodge, sets pivotAs.x = -BAR_W / 2 * s and the x scale s (gui2-rxfm-set-pivot-as / -set-scale-ps) every frame as the cooldown
                  runs out (s 1 -> 0: shortens symmetrically to the centre) and fades its alpha in / out.

Placement: x centre 640, y 580 of the 1280 x 720 HUD box (= 1920 / 1740 of the 3840 x 2160 canvas), ~518 px wide (1554 units)."""
import death_ui_widgets as D

BAR_W = 1554                    # 518 px of 1280 x 3
BAR_H = 18                      # 6 px of 720 incl. the feathered edges (the opaque core is ~3 px)
BAR_CY = 1740                   # y 580 x 3
BAR_PATH = "streaming/t2r/clan/dodge-bar.png"


def add_dodge_bar(wdir):
    path = D.os.path.join(wdir, "hud-root.widget.json")
    w = D.json.load(open(path, encoding="utf-8"))
    if any(i["name"] == "t2rDodgeBar" for i in w["items"]):
        return 0
    root = next(i for i in w["items"] if i["name"] == "root")
    db = {i["name"]: i for i in D._items(wdir, "to1/death-banner.widget.json")}
    b = D._new(db["killerWeaponIcon"], root["guid"], "t2rDodgeBar", 6.5, path=BAR_PATH, scaleMode="Stretch", alignH=0, alignV=0, visible=0,
               **{"tint.start": 0xFFFFFFFF, "tint.end": 0xFFFFFFFF})
    D._bc(b, -BAR_W // 2, BAR_CY - BAR_H // 2, BAR_W, BAR_H)
    w["items"].append(b)
    D.json.dump(w, open(path, "w", encoding="utf-8"), indent=4)
    return 1
