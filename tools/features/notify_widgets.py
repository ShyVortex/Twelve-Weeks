"""The one styled HUD notification, baked into hud-root. TLOU / TLOU2 look (not the flat black card with a red bar
of a generic HUD): no panel, no accent bar - a soft uneven dark smudge made of three stacked copies of the game's own soft blob texture
(hud/status-effects/radial-gradient-arrow.png, black-tinted), the game's own notification badge icons, off-white text.

  t2rNtL / t2rNtM / t2rNtR   the three blobs (main wide one + two lumps, different size / offset / strength: notify.c NTF_BLOBS), hidden,
                             screen-centre anchored in x (pivotAs.x = offset from the centre, 3840-unit canvas), BLOB_W x BLOB_H unscaled
  t2rNtIc                    icon (StretchAspect, centred), hidden; its texture path is set per kind

The text is drawn by t2r-ext with the nametags' own text routine (notify.c, log 'notify:'). Preview: notify_preview.py."""
import os
import death_ui_widgets as D

BLOB_W, BLOB_H = 1000, 400
BLOB = "hud/status-effects/radial-gradient-arrow.png"
ICON = 84                              # canvas units (28 px of the 1280 x 720 text space; = notify.c NTF_ICON_PX * 3)
NAMES = ("t2rNtL", "t2rNtM", "t2rNtR", "t2rNtIc")


def add_notify(wdir):
    path = os.path.join(wdir, "hud-root.widget.json")
    w = D.json.load(open(path, encoding="utf-8"))
    if any(i["name"] == NAMES[0] for i in w["items"]):
        return 0
    root = next(i for i in w["items"] if i["name"] == "root")
    db = {i["name"]: i for i in D._items(wdir, "to1/death-banner.widget.json")}
    new = []
    for nm in NAMES[:3]:
        sh = D._new(db["killerWeaponIcon"], root["guid"], nm, 7.0, path=BLOB, scaleMode="Stretch", alignH=0, alignV=0, visible=0,
                    **{"tint.start": 0xFF000000, "tint.end": 0xFF000000})
        new.append(D._bc(sh, 0, 0, BLOB_W, BLOB_H))
    ic = D._new(db["killerWeaponIcon"], root["guid"], "t2rNtIc", 7.1, path="streaming/t2r/icons/notify-info.png", scaleMode="StretchAspect",
                alignH=1, alignV=1, visible=0, **{"tint.start": 0xFFFFFFFF, "tint.end": 0xFFFFFFFF})
    new.append(D._bc(ic, 0, 0, ICON, ICON))
    w["items"].extend(new)
    D.json.dump(w, open(path, "w", encoding="utf-8"), indent=4)
    return len(new)


# ---- the same notification on the menu pages (server notices must look like this in the lobby / menus too) ----
# The raw nametag text routine only draws in the match HUD, so every menu page gets its own copy of the five widgets under its anim-group
# (t2rNfL / t2rNfM / t2rNfR smudge, t2rNfIc icon, t2rNfTx text widget with SoftOutline). notify.c places them top-centre (the title blocks
# are top-left and the lists start at y ~510 of 2160) and fades them with the same timing. Pages with no anim-group are skipped.
MENU_NAMES = ("t2rNfL", "t2rNfM", "t2rNfR", "t2rNfIc", "t2rNfTx")
MENU_SKIP = ("row", "slot", "shimmer", "button", "list", "currency", "nametag", "scoreboard", "score-banner", "death-banner", "waiting")
MENU_PT = 36
MENU_TEXT_ARGB = 0xFFDCE6EA


def add_notify_menu(wdir):
    import glob
    n = 0
    mm = D.json.load(open(os.path.join(wdir, "to1", "main-menu.widget.json"), encoding="utf-8"))["items"]   # fallback templates for pages with no Image / Text of their own
    mm_img = next(i for i in mm if i["class"] == "Image")
    mm_txt = next(i for i in mm if i["class"] == "Text")
    for path in sorted(glob.glob(os.path.join(wdir, "to1", "*.widget.json"))):
        base = os.path.basename(path)[:-len(".widget.json")]
        if any(k in base for k in MENU_SKIP):
            continue
        w = D.json.load(open(path, encoding="utf-8"))
        items = w["items"]
        if any(i["name"] == MENU_NAMES[0] for i in items):
            continue
        anim = next((i for i in items if i["name"] == "anim-group"), None)
        img = next((i for i in items if i["class"] == "Image"), mm_img)
        txt = next((i for i in items if i["class"] == "Text"), mm_txt)
        if not anim:
            continue
        g = anim["guid"]
        new = []
        for nm in MENU_NAMES[:3]:
            sh = D._new(img, g, nm, 7.0, path=BLOB, scaleMode="Stretch", alignH=0, alignV=0, visible=0,
                        **{"tint.start": 0xFF000000, "tint.end": 0xFF000000})
            new.append(D._bc(sh, 0, 0, BLOB_W, BLOB_H))
        ic = D._new(img, g, MENU_NAMES[3], 7.1, path="streaming/t2r/icons/notify-info.png", scaleMode="StretchAspect",
                    alignH=1, alignV=1, visible=0, **{"tint.start": 0xFFFFFFFF, "tint.end": 0xFFFFFFFF})
        new.append(D._bc(ic, 0, 0, ICON, ICON))
        t = D._new(txt, g, MENU_NAMES[4], 7.2, text="", pointSize=MENU_PT, alignH=1, alignV=1, multiline=1, visible=0, effect="SoftOutline",
                   **{"tint.start": MENU_TEXT_ARGB, "tint.end": MENU_TEXT_ARGB})
        t["cipherId"] = ""
        new.append(D._bc(t, 0, 0, 1500, 250))
        items.extend(new)
        D.json.dump(w, open(path, "w", encoding="utf-8"), indent=4)
        n += len(new)
    return n
