"""(Restyled: the dark card with a red bar and a red circle-slash looked generic. The widget names below are kept, their
roles changed: panel / bar / slash = three stacked copies of the game's own soft blob texture (hud/status-effects/radial-gradient-arrow.png,
black-tinted) = a soft uneven dark smudge with no edge and no accent bar; ring = the thin warning badge icon (streaming/t2r/icons/
notify-warn.png, muted red); text = off-white. denynote.c sizes / places / fades them (DN_BLOBS), like notify.c's in-match box.)

'Blocked' notice: the loadout / weapon picker refusals ("Too many of TACTICAL SHOTGUN on team.", "Not enough Loadout
Points! ...") used to come as the plain white single-line HUD message. Now a dark panel with a red accent bar, a blocked icon (circle
with a slash) and the sentence WRAPPED over up to 4 lines, in the look of the launcher's error notices (release/launcher/src/neat.css
#notice .n.bad: dark panel, 2 px red left border).

  anim-group.denyNote  (to1/picker-skill, picker-primary, picker-secondary, picker-purchase)   and   t2rDenyNote (hud-root, the same group)
    panel   dark rectangle, NOTE_W x MAXH, scaled in y to the real height (pivot = top left)
    bar     red accent, BAR_W wide, scaled in y with the panel
    ring    circle polyline (the icon's ring), moved in y to the panel's centre
    slash   the diagonal of the blocked icon, moved with the ring
    text    4-line box, centred vertically, moved to the panel's centre; t2r-ext (denynote.c, log 'denynote:') writes the sentence with
            its own line breaks (measured wrap), so the panel height = lines * LINE_H + 2 * PAD_V

Geometry in 3840 x 2160 page units, y down. The group is top-left anchored at (NOTE_X, NOTE_TOP); t2r-ext moves it per page."""
import math
import os
import json
import death_ui_widgets as D

W = 3840
NOTE_W = 1100
NOTE_X = (W - NOTE_W) // 2          # 1370: centred
NOTE_TOP = 270                      # pickers: above the list panels (they start at y 510); 4 lines = 270 units
MAXH = 270
BAR_W = 8
ICON = 96
ICON_X = 56                         # icon left edge in the group
TEXT_X = 190
TEXT_W = 890
TEXT_H = 250
PT = 36
LINE_H = 60
PANEL = "general-textures/square-32px.png"
PANEL_ARGB, PANEL_A = 0xFF07090B, 226
RED = 0xFFD9604F                    # the launcher's --bad (#b9645a) lifted for a dark HUD
TEXT_ARGB = 0xFFEAE6DC
BLOB = "hud/status-effects/radial-gradient-arrow.png"
BLOB_W, BLOB_H = 1000, 400     # unscaled blob size (denynote.c scales it)
WARN_ICON = "streaming/t2r/icons/notify-warn.png"
PAGES = ("picker-skill", "picker-primary", "picker-secondary", "picker-purchase", "gearup13")      # (gearup13: the 2013 GEAR UP page, gearup13.c)
GROUP = "denyNote"
HUD_GROUP = "t2rDenyNote"


def _first(items, cls, skip=()):
    return next(i for i in items if i["class"] == cls and i["name"] not in skip)


def _circle(n=40, r=0.5):
    pts = []
    for k in range(n):
        a = 2 * math.pi * k / n
        pts += [0.5 + r * math.cos(a), 0.5 + r * math.sin(a)]
    return pts


def _build(items, parent_guid, name, tg, tt, ti, tp, depth):
    """tg / tt / ti / tp = group / text / image / polyline templates of the page. Returns the new items."""
    g = D._new(tg, parent_guid, name, depth, visible=0)
    D._tl(g, NOTE_X, NOTE_TOP, NOTE_W, MAXH)
    new = [g]
    gid = g["guid"]
    col = lambda a: {"tint.start": a, "tint.end": a}

    def rect(nm, x, y, w, h, argb, a, d):
        r = D._new(ti, gid, nm, d, path=PANEL, scaleMode="Stretch", alignH=0, alignV=0, **col(argb), **{"color.a": a})
        D._tl(r, x, y, w, h)
        new.append(r)
    def blob(nm, d):
        r = D._new(ti, gid, nm, d, path=BLOB, scaleMode="Stretch", alignH=0, alignV=0, **col(0xFF000000), **{"color.a": 255})
        D._tl(r, 0, 0, BLOB_W, BLOB_H)
        new.append(r)
    blob("panel", -3.0)
    blob("bar", -2.9)
    blob("slash", -2.8)
    ring = D._new(ti, gid, "ring", 0.2, path=WARN_ICON, scaleMode="StretchAspect", alignH=1, alignV=1, **col(0xFFFFFFFF), **{"color.a": 255})
    D._tl(ring, ICON_X, (MAXH - ICON) / 2, ICON, ICON)
    t = D._new(tt, gid, "text", 0.4, text="", pointSize=PT, alignH=0, alignV=1, multiline=1, visible=1, **col(TEXT_ARGB))
    t["cipherId"] = ""
    D._tl(t, TEXT_X, (MAXH - TEXT_H) / 2, TEXT_W, TEXT_H)
    new += [ring, t]
    return new


def add_deny_notes(wdir):
    """Add the notice to the picker pages and hud-root; returns the number of widgets added."""
    n = 0
    for page in PAGES:
        path = os.path.join(wdir, "to1", page + ".widget.json")
        if not os.path.exists(path):
            continue
        w = json.load(open(path, encoding="utf-8"))
        items = w["items"]
        if any(i["name"] == GROUP for i in items):
            continue
        anim = next(i for i in items if i["name"] == "anim-group")
        by = {i["name"]: i for i in items}
        new = _build(items, anim["guid"], GROUP, by.get("pickerPanel") or by["lst"], by.get("pickerTitle") or by.get("title") or by["edHdTx"], _first(items, "Image"),
                     _first(items, "Polyline"), 7.0)
        items.extend(new)
        json.dump(w, open(path, "w", encoding="utf-8"), indent=4)
        n += len(new)
    path = os.path.join(wdir, "hud-root.widget.json")
    w = json.load(open(path, encoding="utf-8"))
    items = w["items"]
    if not any(i["name"] == HUD_GROUP for i in items):
        root = next(i for i in items if i["name"] == "root")
        by = {i["name"]: i for i in items}
        new = _build(items, root["guid"], HUD_GROUP, by["rootFullscreen"], by["topCenterMessage"], _first(items, "Image"),
                     _first(items, "Polyline"), 7.0)
        items.extend(new)
        json.dump(w, open(path, "w", encoding="utf-8"), indent=4)
        n += len(new)
    return n
