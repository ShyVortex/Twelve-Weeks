"""Kill feed rows baked into the in-match HUD root (gui2-widgets.pak hud-root.widget, canvas.hudRoot), like death_ui_widgets: plain
widgets, NO script, hidden; t2r-ext (killfeed.c, log 'killfeed:') sets strings / image paths, moves the row groups and fades them.

  t2rKf0..t2rKf4        row group, 3840 x ROW_H canvas units, top-left anchored (moved with gui2-rxfm-set-pivot-as, alpha fades the row)
    kb / kr             killer name, right aligned, ends at the icon (kb = friendly blue, kr = enemy red; one of them shown)
    shl / shm / shr     soft dark backdrop (left cap, stretched middle, right cap), lowest depth; t2r-ext sizes it to the row's names
    fi                  status icon (fist = downed, skull = killed), FI_W square, left of the weapon icon; killer names end 76 units further left when shown
    ic                  weapon icon (StretchAspect inside ICON_W x ICON_H, centred on the icon column; wide icons come out lower)
    vb / vr             victim name, left aligned, starts at the icon

The icon column is fixed (no text width needed), so rows are not right aligned as a block: killers grow left from it, victims right.
Widget space 3840 x 2160, y down. Names use the death banner's killerNameText look at KF_PT."""
import os
import death_ui_widgets as D

W = 3840
ROW_H = 78
ICON_W, ICON_H = 270, 66
RIGHT = 90                      # 30 px right margin of the old feed
VICTIM_W = 520                  # room for the victim name right of the icon
GAP = 20
FI_W = 66                       # status icon box (fist / skull), killfeed.c KF_FI_W / KF_FI_X / KF_FI_SPAN
ICX = W - RIGHT - VICTIM_W - GAP - ICON_W // 2     # icon column centre
KF_PT = 44
FI_X = ICX - ICON_W // 2 - 10 - FI_W      # 2864 = killfeed.c KF_FI_X
BLUE, RED = 0xFF8FB0CC, 0xFFCF7870                 # muted steel blue / brick red (old 3FA9F5 / E04848 were too saturated, 'fanmade'); was t2-blue / t2-red
SHADOW = 0x40000000                                # 25% black drop shadow copies (kbs/krs/vbs/vrs/ics) (50 % at 3 units was too intense), offset SH_OFF units
SH_OFF = 2
ROWS = 5
SH_Y, SH_H = -21, 120               # soft dark backdrop: row pitch 84, so neighbours' feathered edges just touch
SH_CAP = 240                      # feathered end width (fixed: left / right cap images)
SH_MID_W0 = 1000                  # unscaled middle width; t2r-ext (killfeed.c) scales it in x to the row's text and moves the three pieces
SH_PATH = "streaming/t2r/clan/kf-shade-%s.png"      # tools/models/figures/ship.py make_kf


def add_killfeed(wdir):
    path = os.path.join(wdir, "hud-root.widget.json")
    w = D.json.load(open(path, encoding="utf-8"))
    if any(i["name"] == "t2rKf0" for i in w["items"]):
        return 0
    root = next(i for i in w["items"] if i["name"] == "root")
    grp_t = next(i for i in w["items"] if i["name"] == "rootFullscreen")
    db = {i["name"]: i for i in D._items(wdir, "to1/death-banner.widget.json")}
    new = []
    for r in range(ROWS):
        g = D._new(grp_t, root["guid"], "t2rKf%d" % r, 6.0 + r * 0.1, visible=0)
        D._tl(g, 0, KF_TOP_PLACEHOLDER, W, ROW_H)
        new.append(g)
        gid = g["guid"]
        for nm, x, wd in (("shl", 0, SH_CAP), ("shm", SH_CAP, SH_MID_W0), ("shr", SH_CAP + SH_MID_W0, SH_CAP)):
            sh = D._new(db["killerWeaponIcon"], gid, nm, -1.0, path=SH_PATH % nm[2], scaleMode="Stretch", alignH=0, alignV=0,
                        **{"tint.start": 0xFFFFFFFF, "tint.end": 0xFFFFFFFF})
            D._tl(sh, x, SH_Y, wd, SH_H)
            new.append(sh)
        for nm, col, right in (("kb", BLUE, 1), ("kr", RED, 1), ("vb", BLUE, 0), ("vr", RED, 0)):
            t = D._new(db["killerNameText"], gid, nm, 1.0, text="", pointSize=KF_PT, alignH=2 if right else 0, alignV=1, visible=0,
                       **{"tint.start": col, "tint.end": col})
            if right:
                D._tl(t, ICX - ICON_W // 2 - GAP - 1100, 0, 1100, ROW_H)
            else:
                D._tl(t, ICX + ICON_W // 2 + GAP, 0, VICTIM_W, ROW_H)
            new.append(t)
        for nm, right in (("kbs", 1), ("krs", 1), ("vbs", 0), ("vrs", 0)):
            t = D._new(db["killerNameText"], gid, nm, 0.5, text="", pointSize=KF_PT, alignH=2 if right else 0, alignV=1, visible=0,
                       **{"tint.start": SHADOW, "tint.end": SHADOW})
            if right:
                D._tl(t, ICX - ICON_W // 2 - GAP - 1100 + SH_OFF, SH_OFF, 1100, ROW_H)
            else:
                D._tl(t, ICX + ICON_W // 2 + GAP + SH_OFF, SH_OFF, VICTIM_W, ROW_H)
            new.append(t)
        ics = D._new(db["killerWeaponIcon"], gid, "ics", -0.5, path="streaming/t2r/icons/killfeed-skull.png", scaleMode="StretchAspect",
                     alignH=1, alignV=1, visible=0, **{"tint.start": SHADOW, "tint.end": SHADOW})
        D._tl(ics, ICX - ICON_W // 2 + SH_OFF, (ROW_H - ICON_H) // 2 + SH_OFF, ICON_W, ICON_H)
        new.append(ics)
        ic = D._new(db["killerWeaponIcon"], gid, "ic", 0.0, path="streaming/t2r/icons/killfeed-skull.png", scaleMode="StretchAspect",
                    alignH=1, alignV=1, visible=0, **{"tint.start": 0xFFFFFFFF, "tint.end": 0xFFFFFFFF})
        D._tl(ic, ICX - ICON_W // 2, (ROW_H - ICON_H) // 2, ICON_W, ICON_H)
        new.append(ic)
        fi = D._new(db["killerWeaponIcon"], gid, "fi", 0.1, path="streaming/t2r/icons/fist.png", scaleMode="StretchAspect",
                    alignH=1, alignV=1, visible=0, **{"tint.start": 0xFFFFFFFF, "tint.end": 0xFFFFFFFF})    # status icon: fist (down) / skull (kill), left of the weapon icon
        D._tl(fi, FI_X, (ROW_H - FI_W) // 2, FI_W, FI_W)
        new.append(fi)
    w["items"].extend(new)
    D.json.dump(w, open(path, "w", encoding="utf-8"), indent=4)
    return len(new)


KF_TOP_PLACEHOLDER = 150
