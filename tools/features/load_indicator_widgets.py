"""TLOU2's own loading icon as a load indicator (the loading screen was only a banner with no load bar).

The icon is html/loadingicon-1.png (the 64 px arc), the widget the game itself uses for its loading / saving spinner:
menu/message-box-spinner.widget "iconLoading" and menu-collectibles/collect-loading.widget "icon" (rotation keyframes
0 -> 360 deg over 0.333 s at animation rate 0.5 = one turn per 0.667 s, label "loading", loop 1).
There is no native to start a gui2 animation label or to set a rotation at runtime, so the turn is stepped: N copies of the
same sprite at fixed layout rotations, one visible at a time (t2r-ext li_tick shows the copy for the current time).

Group "t2rSpin" (hidden) with children s00..s{N-1}, built into
  * loading.widget (the engine's level-load widget: every LoadingScreen::SetEnabled load - boot menu world, menu <-> match,
    map change), on top of the stock fader (depth 2.0), bottom right where the stock taskProgressBar sits;
  * to1/connecting (the FACTIONS II entry page, which can stay on screen over the menu world's load).
"""
STEPS = 48
PERIOD_MS = 667             # collect-loading label "loading": range 0..0.333 s at rate 0.5 (t2r-ext LI_PERIOD_MS)
ICON = "html/loadingicon-1.png"
SIZE = 80


def add_spinner(b, parent, cx, cy, size=SIZE):
    g = b.group("t2rSpin", parent, b.tl(0, 0, 3840, 2160), visible=0, depth=2.0)["guid"]
    for k in range(STEPS):
        b.image("s%02d" % k, g, b.ctr(cx, cy, size, size, 360.0 * k / STEPS), ICON, 0xFFFFFFFF, 255, visible=0)
    return STEPS + 1


def add_loading_widget_spinner(wdir):
    import json
    import os
    from clan_widgets import Builder, _templates
    path = os.path.join(wdir, "loading.widget.json")
    w = json.load(open(path, encoding="utf-8"))
    if any(i["name"] == "t2rSpin" for i in w["items"]):
        return 0
    main = json.load(open(os.path.join(wdir, "to1", "main-menu.widget.json"), encoding="utf-8"))
    t, _, _ = _templates(main)
    for c in t.values():
        for k in ("engineClass", "tags", "animationsPath"):
            c.pop(k, None)
    b = Builder(t)
    root = next(i for i in w["items"] if i["parent"] is None)
    n = add_spinner(b, root["guid"], 3580, 1930)
    w["items"] += b.items
    json.dump(w, open(path, "w", encoding="utf-8"), indent=4)
    return n

TW_BAR_H = 24                       # = t2r-ext LDS_BARH (the thin bottom bar of the TWELVE WEEKS entry page)


def add_loading_widget_tw(wdir):
    """loading.widget: the TWELVE WEEKS screen (the faction pick reloads the menu level "with the twelve weeks screen"; a menu page
    cannot stay up through a level load - the page stack is wiped - but the engine draws its loading widget all load long). Group "t2rTw"
    (hidden): black, the white title (loading_art TITLE_TEX, centred like to1/connecting) and the thin bottom bar (BAR_TEX; t2r-ext scales its
    width with the fill). Drawn over the stock fader and the 2013 LOADING group; t2r-ext shows it only for the pick's reload (loadseq.c)."""
    import json
    import os
    from clan_widgets import Builder, _templates
    import loading_art as la
    path = os.path.join(wdir, "loading.widget.json")
    w = json.load(open(path, encoding="utf-8"))
    if any(i["name"] == "t2rTw" for i in w["items"]):
        return 0
    main = json.load(open(os.path.join(wdir, "to1", "main-menu.widget.json"), encoding="utf-8"))
    t, _, _ = _templates(main)
    for c in t.values():
        for k in ("engineClass", "tags", "animationsPath"):
            c.pop(k, None)
    b = Builder(t)
    root = next(i for i in w["items"] if i["parent"] is None)
    g = b.group("t2rTw", root["guid"], b.tl(0, 0, 3840, 2160), visible=0, depth=1.5)["guid"]
    b.rect("t2rTwBlack", g, b.bleed(), 0xFF000000, 255)
    b.image("t2rTwTitle", g, b.tl((3840 - la.TITLE_W) // 2, (2160 - la.TITLE_H) // 2, la.TITLE_W, la.TITLE_H), la.TITLE_TEX, 0xFFFFFFFF, 255, depth=1.0)
    b.image("t2rTwBar", g, b.tl(0, 2160 - TW_BAR_H, 3840, TW_BAR_H), la.BAR_TEX, 0xFFFFFFFF, 255, depth=2.0)
    w["items"] += b.items
    json.dump(w, open(path, "w", encoding="utf-8"), indent=4)
    return len(b.items)
