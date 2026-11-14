"""Interrogation HUD (2013 interui.png, our modern style) baked into the in-match HUD root (gui2-widgets.pak hud-root.widget, canvas.hudRoot):
plain widgets, NO script, everything hidden; t2r-ext (interrogation_hud.c, log 'inthud:') drives visibility, pivots, alpha and texts.
Widget space 3840 x 2160, y down (1280 x 720 units x 3).

  t2rIntHud            block under the radar in the figures / lives row's place (centre FIG_CX, top FIG_TOP): soft shade panel, "INTERROGATIONS" label (40 pt white + underline, P1 CHUNKY) and two thin
                       segmented bars, ours (blue) over the enemy's (red). Each bar = 5 segments (one per interrogation: the intel needed),
                       a padlock at its right end and three small pips = the unlock stages that team got through (the lockbox's 3 stages).
      shade            streaming/t2r/clan/menu-shade-sub.png (the soft feathered black panel every modern menu panel uses)
      lbl              INTERROGATIONS
      t<r><i>          segment tracks (r 0 ours / 1 enemy, i 0-4), f<r><i> segment fills (visible per intel)
      pt<r><k> pf<r><k> unlock-stage pips (k 0-2): track / fill; the padlock itself is static shapes (lk<r>*)
  t2rIntMk0 / Mk1      world markers (group, 200 x 240, x anchored to the screen centre, y from the top; the ext sets pivotAs per frame):
                       Mk0 = ATTACK (the enemy lockbox: padlock in a circle), Mk1 = DEFEND (our lockbox: shield in a circle)
      disc, circ       dark disc + circle outline (team blue)
      rg0..rg23        24 arc segments (15 deg each) of the progress ring around the circle, visible 0..n = unlock progress
      aL aR aU aD      off-screen edge arrows (chevrons), one visible while the marker is pinned to the screen edge
      lbl              ATTACK / DEFEND under the circle
  t2rIntRn             bottom-centre round progress of an interrogation (a single press: no hold prompt): shade (radial), trk, rn0..rn23 (ring), qm ("?!")
  t2rIntPr             bottom-centre hold prompt (lockbox UNLOCKING only: it IS hold-to-cancel): shade, lbl ("UNLOCKING..." / "INTERROGATING..."), rel ("RELEASE"), icon (gen:interact glyph),
                       can ("TO CANCEL"), trk / fil (progress bar, the ext scales fil in x)
"""
import copy
import json
import os
import t2guid
import death_ui_widgets as D
from clan_widgets import Builder, FIG_CX, FIG_TOP

BLUE, RED = 0xFF48A8D8, 0xFFE04848            # = matchflow_widgets.HUD_BLUE / HUD_RED (2013 figure blue / enemy red)
WHITE, GREY = 0xFFF2F2F2, 0xFFB4B4B4            # GREY = clan13_widgets.LABEL
SHADE_SUB = "streaming/t2r/clan/menu-shade-sub.png"
# Placement: exactly where the figures row + lives counters were, under the radar: centred on the radar column (clan_widgets.FIG_CX),
# top = the figures' top (clan_widgets.FIG_TOP, which carries HUD_SHIFT_U). 4K page px (U = 3).
SEG_W, SEG_GAP, SEG_H = 46, 6, 14
SEGS, PIPS = 5, 3
PIP_W, PIP_GAP = 16, 5
LOCK_GAP, LOCK_W, PIP_LGAP = 14, 24, 12                # gap bar -> padlock, padlock width (0.9 x 26), gap padlock -> pips
CONT_W = SEGS * SEG_W + (SEGS - 1) * SEG_GAP + LOCK_GAP + LOCK_W + PIP_LGAP + PIPS * PIP_W + (PIPS - 1) * PIP_GAP      # content width (label, bars, padlock, pips)
BX = round(FIG_CX * 3.0 - CONT_W / 2.0)                # content left
INT_DROP = 45                                          # a little too close to the radar, moved downwards a little (4K page px, ~22 px at 1080p)
BY = round(FIG_TOP * 3.0) + INT_DROP                   # content top (the label's top)
LBL_PT, LBL_TRACK, LBL_CY = 40, 6, 22                  # CHUNKY variant: 40 pt white label, tracking 6, centre 22 px below the content top
LBL_W = 420                                            # label box width (the 40 pt label is ~408 px wide, a touch wider than the bars; centred on the same axis)
UL_W, UL_H, UL_Y, UL_A = 120, 6, 56, 200               # P1 underline: 120 x 6 white (alpha 200) under the label, centred
ROW_Y = (BY + 80, BY + 80 + 40)                        # P1 spacing under the label + underline (bars unchanged: 14 px, 40 px pitch)
CONT_H = (ROW_Y[1] + 21) - BY                          # label top .. the lower padlock's bottom
LOCK_X = BX + SEGS * SEG_W + (SEGS - 1) * SEG_GAP + LOCK_GAP
PIP_X = LOCK_X + LOCK_W + PIP_LGAP
PAD_X, PAD_Y = 0.22, 0.35                              # shade padding per side (x of CONT_W, y of CONT_H), like pnlLives / pnlFigures (clan_widgets.HUD_PANEL_SOFT); 0.25/0.60 clipped into the radar
SHADE_A = 130                                          # menu-shade-sub peaks at 178 / 255 = 70 %; x 0.66 = the ~46 % of the other HUD panels
RING_SEGS = 24
MK_W, MK_H = 240, 240                            # marker box (icons made bigger for readability: 1.5x the 72ff0267 size): label, ring (outer diameter MK_D = 138 units = 69 px at 1080p), distance under it
MK_C = (120, 105)                                # circle centre inside the marker box (= interrogation_hud.c IH_MK_CX / CY)
MK_D = 138                                      # ring outer diameter
RING_W = 13                                     # ring stroke (6.5 px at 1080p)
RING_PIECES = 24                                # fill pieces per arc (72 in all, = interrogation_hud.c IH_RING / 3): with the leading piece's alpha the fill is continuous
RING_GAP = 16.0                                 # degrees between the 3 arcs
TRACK_ARC_A = 110
MK_COL = (0xFFFF3C3C, 0xFF40B0FF)               # ATTACK red / DEFEND blue (the lockbox markers of interrogation.c)
PR_Y = 1500                                     # prompt block top
TRACK_A, FILL_A = 70, 255


class HB(Builder):
    """Builder that cleans the template copies the way death_ui_widgets._new does (no script / engine class / animation path)."""
    def add(self, cls, name, parent, **kw):
        c = super().add(cls, name, parent, **kw)
        for k in ("script", "engineClass", "animationsPath", "tags"):
            c.pop(k, None)
        if c.get("class") == "Text":
            c["cipherId"] = ""
        c["focusable"] = 0
        return c


def _bc(place, dx):
    """x anchored to the screen centre (dx = offset from the centre in 3840-space), like death_ui_widgets._bc."""
    place = dict(place)
    place.update({"anchorMinN.x": 0.5, "anchorMaxN.x": 0.5, "pivotAs.x": float(dx)})
    return place


def _templates(wdir, root_items):
    db = {i["name"]: i for i in D._items(wdir, "to1/death-banner.widget.json")}
    img = next(i for i in D._items(wdir, "to1/picker-skill.widget.json") if i["name"] == "perkIcon")
    eo = json.load(open(os.path.join(wdir, "t2r-hud-rogue", "t2r-hud-encounter-over.widget.json"), encoding="utf-8"))
    line = next(i for i in eo["items"] if i["name"] == "left-line")
    dot = next(i for i in D._items(wdir, "to1/main-menu.widget.json") if i["name"] == "onlineDot")
    grp = next(i for i in root_items if i["name"] == "rootFullscreen")
    return {"Text": db["killedByLabel"], "Image": img, "Polyline": line, "Ellipse": dot, "Group": grp}


def _padlock(b, parent, pre, x, y, col, alpha=255, s=1.0):
    """A small padlock: body + a shackle built from three bars (deterministic, no arc angles). Box ~ 26 x 34 at s = 1."""
    b.rect(pre + "b", parent, b.tl(x, y + 14 * s, 26 * s, 20 * s), col, alpha)
    b.rect(pre + "l", parent, b.tl(x + 4 * s, y + 3 * s, 4 * s, 13 * s), col, alpha)
    b.rect(pre + "r", parent, b.tl(x + 18 * s, y + 3 * s, 4 * s, 13 * s), col, alpha)
    b.rect(pre + "t", parent, b.tl(x + 4 * s, y, 18 * s, 4 * s), col, alpha)


def _top_group(b, name, parent, depth, place=None, vis=0):
    g = b.group(name, parent, place or {"anchorMinN.x": 0.0, "anchorMinN.y": 0.0, "anchorMaxN.x": 1.0, "anchorMaxN.y": 1.0,
                                       "pivotN.x": 0.5, "pivotN.y": 0.5, "pivotAs.x": 0.0, "pivotAs.y": 0.0,
                                       "rectSizeDelta.width": 0.0, "rectSizeDelta.height": 0.0}, visible=vis)
    g["depth"] = float(depth)
    return g


def build_hud(b, parent):
    g = _top_group(b, "t2rIntHud", parent, 31.0)
    gid = g["guid"]
    pw = max(CONT_W, LBL_W)                             # the wider of label / bars drives the panel width
    px, py = pw * PAD_X, CONT_H * PAD_Y
    b.image("shade", gid, b.tl(BX + CONT_W / 2.0 - pw / 2.0 - px, BY - py, pw + 2 * px, CONT_H + 2 * py), SHADE_SUB, 0xFFFFFFFF, SHADE_A)      # centred on the content box
    cxm = BX + CONT_W / 2.0                            # content centre
    b.text("lbl", gid, b.tl(cxm - LBL_W / 2.0, BY + LBL_CY - 30, LBL_W, 60), "INTERROGATIONS", LBL_PT, WHITE, face="Alternate", align=1, tracking=LBL_TRACK, valign=1)      # P1 CHUNKY label
    b.rect("ul", gid, b.tl(cxm - UL_W / 2.0, BY + UL_Y, UL_W, UL_H), WHITE, UL_A)      # P1 underline
    for r in range(2):
        col = BLUE if r == 0 else RED
        y = ROW_Y[r]
        for i in range(SEGS):
            x = BX + i * (SEG_W + SEG_GAP)
            b.rect(f"t{r}{i}", gid, b.tl(x, y, SEG_W, SEG_H), 0xFFFFFFFF, TRACK_A)
            b.rect(f"f{r}{i}", gid, b.tl(x, y, SEG_W, SEG_H), col, FILL_A, visible=0)
        _padlock(b, gid, f"lk{r}", LOCK_X, y - 10, col, 235, 0.9)
        for k in range(PIPS):
            x = PIP_X + k * (PIP_W + PIP_GAP)
            b.rect(f"pt{r}{k}", gid, b.tl(x, y, PIP_W, SEG_H), 0xFFFFFFFF, TRACK_A)
            b.rect(f"pf{r}{k}", gid, b.tl(x, y, PIP_W, SEG_H), col, FILL_A, visible=0)
    return g


def ring_pieces(N=RING_PIECES):
    """The marker ring: 3 arcs of ARC_DEG with RING_GAP degrees between them, the first starting just right of 12 o'clock and running clockwise (PIL / screen
    convention: 0 deg = 3 o'clock, angles grow clockwise, so 12 o'clock = 270). Each arc is N equal pieces; the ext shows the first n of an arc as it fills.
    A piece never crosses 360 (the widget does not wrap), so the one arc that passes 0 deg is cut there."""
    out = []
    for a in range(3):
        a0 = 270.0 + a * 120.0 + RING_GAP / 2.0
        a1 = 270.0 + (a + 1) * 120.0 - RING_GAP / 2.0
        if a0 < 360.0 < a1:        # the arc that passes 0 deg: split at 360 (6 + 2 pieces), so no piece crosses it
            n1 = max(1, min(N - 1, round(N * (360.0 - a0) / (a1 - a0))))
            edges = [a0 + (360.0 - a0) * k / n1 for k in range(n1 + 1)] + [360.0 + (a1 - 360.0) * k / (N - n1) for k in range(1, N - n1 + 1)]
        else:
            edges = [a0 + (a1 - a0) * k / float(N) for k in range(N + 1)]
        out.append([(edges[k], edges[k + 1]) for k in range(N)])
    return out


def _wrap_pieces(pieces):
    """Angles >= 360 -> -360 (the widget does not wrap past 360); ring_pieces() already splits the arc at 360."""
    return [(round(b - 360.0, 2), round(e - 360.0, 2)) if b >= 360.0 else (round(b, 2), round(e, 2)) for b, e in pieces]


def build_marker(b, parent, k):
    """k 0 = ATTACK (enemy safe, the real No Return safe icon, red), 1 = DEFEND (our safe, shield, blue). Native 2013 layout: label above, ring + icon, distance below.
    The ring is THREE arcs with gaps (grey track + a team-coloured fill piece per 1/8 of an arc, visible as the unlock progresses; the gaps = the 2 checkpoints and the
    start / end at 12 o'clock). Icon textures: streaming/t2r/icons/safe-marker.png (stock hud/interactions/safe.png) / safe-shield.png (tools/models/icons_static)."""
    cx, cy = MK_C
    col = MK_COL[k]
    place = {"anchorMinN.x": 0.5, "anchorMinN.y": 0.0, "anchorMaxN.x": 0.5, "anchorMaxN.y": 0.0, "pivotN.x": 0.0, "pivotN.y": 0.0,
             "pivotAs.x": 0.0, "pivotAs.y": 0.0, "rectSizeDelta.width": float(MK_W), "rectSizeDelta.height": float(MK_H)}
    g = _top_group(b, f"t2rIntMk{k}", parent, 30.0 + k * 0.1, place)
    gid = g["guid"]
    b.text("lbl", gid, b.tl(0, 0, MK_W, 33), "ATTACK" if k == 0 else "DEFEND", 30, col, face="Alternate", align=1, tracking=3, valign=1)
    b.ellipse("disc", gid, b.ctr(cx, cy, MK_D - 2 * RING_W, MK_D - 2 * RING_W), 0xFF0A0C0E, 150)
    d = MK_D - RING_W                     # stroke centre line (the arc is drawn centred on the ellipse box)
    arcs = [_wrap_pieces(p) for p in ring_pieces()]
    for a in range(3):
        # track = the whole arc in grey, one piece (two where it passes 360 -> 0, the widget does not wrap)
        pcs = arcs[a]
        cut = next((n for n in range(1, len(pcs)) if pcs[n][0] < pcs[n - 1][0]), len(pcs))
        for t, grp in enumerate((pcs[:cut], pcs[cut:])):
            if grp:
                b.ellipse(f"tr{a}{t}", gid, b.ctr(cx, cy, d, d), 0xFF969696, TRACK_ARC_A, filled=0, begin=grp[0][0], end=min(360.0, grp[-1][1] + 0.4), width=float(RING_W))
    for a in range(3):
        for n, (pb, pe) in enumerate(arcs[a]):
            b.ellipse(f"rg{a * RING_PIECES + n}", gid, b.ctr(cx, cy, d, d), col, 255, filled=0, begin=pb, end=min(360.0, pe + 0.4), width=float(RING_W))["visible"] = 0
    if k == 0:
        b.image("ic", gid, b.ctr(cx, cy, 100, 82), "streaming/t2r/icons/safe-marker.png", col, 255, scaleMode="StretchAspect", alignH=1, alignV=1)
    else:
        b.image("ic", gid, b.ctr(cx, cy, 80, 80), "streaming/t2r/icons/safe-shield.png", col, 255, scaleMode="StretchAspect", alignH=1, alignV=1)
    b.text("dist", gid, b.tl(0, cy + MK_D // 2 + 3, MK_W, 39), "", 30, 0xFFEBEBEB, face="Alternate", align=1, tracking=2, valign=0)
    for nm, pts, pl in (("aL", [1.0, 0.0, 0.0, 0.5, 1.0, 1.0], b.tl(0, cy - 16, 16, 33)),
                        ("aR", [0.0, 0.0, 1.0, 0.5, 0.0, 1.0], b.tl(MK_W - 16, cy - 16, 16, 33)),
                        ("aU", [0.0, 1.0, 0.5, 0.0, 1.0, 1.0], b.tl(cx - 16, 0, 33, 16)),
                        ("aD", [0.0, 0.0, 0.5, 1.0, 1.0, 0.0], b.tl(cx - 16, MK_H - 16, 33, 16))):
        b.add("Polyline", nm, gid, **pl, **b.col(col), closed=0, lineWidth=4.5, pointsUv=pts, visible=0, **{"color.a": 255})
    return g


ATT_FILE = ("hud-buddy-status/t2r-int-mk0", "hud-buddy-status/t2r-int-mk1")      # = interrogation_hud.c IH_ATT_NAME


def add_marker_attachables(wdir, templates):
    """The safe marker was laggy (the hud-root marker is a widget the ext moves with w_pivot, drawn one frame after it is set): the same
    marker as an ATTACHABLE widget file, which the engine places on the lockbox object itself in the frame it draws (the buddy + / the mark triangle / the
    nametags' path: no lag). Root = a copy of the stock buddy-health-attachable root (Gui2::AttachableWidget, arrowEnabled, clampType default = pinned to the
    screen border off screen with the stock offscreen arrow pointing at it, the buddy icon's own behaviour), MK_W x MK_H with the circle centre at the root's
    centre (= the attach point). Children = build_marker's disc, track, ring pieces, icon and distance (no ATTACK / DEFEND label, no own chevrons: the
    engine's arrow). interrogation_hud.c drives the ring / distance / alpha through gui2-build-widget-path on the shown instance."""
    src = json.load(open(os.path.join(wdir, "hud-buddy-status", "buddy-health-attachable.widget.json"), encoding="utf-8"))
    n = 0
    for k in range(2):
        w = copy.deepcopy(src)
        items = w["items"]
        root = next(i for i in items if i["name"] == "root")
        arrow = next(i for i in items if i["name"] == "arrow" and i.get("parent") == root["guid"])
        arrow_ic = [i for i in items if i.get("parent") == arrow["guid"]]
        remap = {i["guid"]: t2guid.guid() for i in [root, arrow] + arrow_ic}
        for i in [root, arrow] + arrow_ic:
            i["guid"] = remap[i["guid"]]
            if i.get("parent"):
                i["parent"] = remap[i["parent"]]
        root["tags"] = dict(root.get("tags") or {}, arrowEnabled="true", clampType="default")
        root["scale.x"] = root["scale.y"] = 1.0
        root.update({"rectSizeDelta.width": float(MK_W), "rectSizeDelta.height": float(MK_H), "pivotN.x": 0.5, "pivotN.y": 0.5, "pivotAs.x": 0.0, "pivotAs.y": 0.0})
        root.pop("a11yScale", None)
        arrow["pivotAs.y"] = float(MK_D // 2 + 12)          # (stock: 51 for the 80-unit buddy circle = just outside it)
        arrow["depth"] = 9.0
        w["size"] = [float(MK_W), float(MK_H)]
        b = HB(templates)
        gid = root["guid"]
        cx, cy = MK_W // 2, MK_H // 2
        col = MK_COL[k]
        b.ellipse("disc", gid, b.ctr(cx, cy, MK_D - 2 * RING_W, MK_D - 2 * RING_W), 0xFF0A0C0E, 150)
        d = MK_D - RING_W
        arcs = [_wrap_pieces(pc) for pc in ring_pieces()]
        for a in range(3):
            pcs = arcs[a]
            cut = next((m for m in range(1, len(pcs)) if pcs[m][0] < pcs[m - 1][0]), len(pcs))
            for t, grp in enumerate((pcs[:cut], pcs[cut:])):
                if grp:
                    b.ellipse(f"tr{a}{t}", gid, b.ctr(cx, cy, d, d), 0xFF969696, TRACK_ARC_A, filled=0, begin=grp[0][0], end=min(360.0, grp[-1][1] + 0.4), width=float(RING_W))
        for a in range(3):
            for m, (pb, pe) in enumerate(arcs[a]):
                b.ellipse(f"rg{a * RING_PIECES + m}", gid, b.ctr(cx, cy, d, d), col, 255, filled=0, begin=pb, end=min(360.0, pe + 0.4), width=float(RING_W))["visible"] = 0
        if k == 0:
            b.image("ic", gid, b.ctr(cx, cy, 100, 82), "streaming/t2r/icons/safe-marker.png", col, 255, scaleMode="StretchAspect", alignH=1, alignV=1)
        else:
            b.image("ic", gid, b.ctr(cx, cy, 80, 80), "streaming/t2r/icons/safe-shield.png", col, 255, scaleMode="StretchAspect", alignH=1, alignV=1)
        b.text("dist", gid, b.tl(0, cy + MK_D // 2 + 3, MK_W, 39), "", 30, 0xFFEBEBEB, face="Alternate", align=1, tracking=2, valign=0)
        w["items"] = [root] + b.items + [arrow] + arrow_ic
        json.dump(w, open(os.path.join(wdir, *ATT_FILE[k].split("/")) + ".widget.json", "w", encoding="utf-8"), indent=4)
        n += len(w["items"])
    return n


def build_prompt(b, parent):
    g = _top_group(b, "t2rIntPr", parent, 32.0)
    gid = g["guid"]
    y = PR_Y
    b.image("shade", gid, b.tl(0, y - 40, 1400, 300), SHADE_SUB, 0xFFFFFFFF, 255)
    gi = b.items[-1]
    gi.update(_bc(b.tl(0, y - 40, 1400, 300), -700))
    t = b.text("lbl", gid, _bc(b.tl(0, y, 1400, 90), -700), "UNLOCKING...", 48, WHITE, align=1, tracking=6)
    b.text("rel", gid, _bc(b.tl(0, y + 100, 560, 70), -640), "RELEASE", 38, GREY, align=2, tracking=4)
    ic = b.image("icon", gid, _bc(b.tl(0, y + 96, 80, 80), -40), "gen:interact", 0xFFFFFFFF, 255, scaleMode="StretchAspect", alignH=1, alignV=1)
    b.text("can", gid, _bc(b.tl(0, y + 100, 560, 70), 80), "TO CANCEL", 38, GREY, align=0, tracking=4)
    b.rect("trk", gid, _bc(b.tl(0, y + 196, 900, 12), -450), 0xFFFFFFFF, TRACK_A)
    b.rect("fil", gid, _bc(b.tl(0, y + 196, 900, 12), -450), BLUE, 255, visible=0)
    return g


RN_CY, RN_D = 1640, 200                       # interrogation progress circle (bottom centre): centre y, ring diameter (3840 x 2160 space)
RN_SHADE = "streaming/t2r/icons/death-count-shade.png"      # make_icons.radial_shade: soft radial black (the respawn countdown's backdrop)


def build_round(b, parent):
    """t2rIntRn: the interrogation is ONE press (the pair plays out, no cancel), so no hold prompt: a round progress widget instead -
    soft radial dark circle, a ring that fills with the interrogation's progress (rn0..rn23, 15 deg arcs like the markers' rings) and a white ?! ."""
    g = _top_group(b, "t2rIntRn", parent, 32.5)
    gid = g["guid"]
    sd = int(RN_D * 2.1)
    b.image("shade", gid, _bc(b.tl(0, RN_CY - sd / 2, sd, sd), -sd / 2), RN_SHADE, 0xFFFFFFFF, 255)
    b.ellipse("trk", gid, _bc(b.ctr(0, RN_CY, RN_D, RN_D), 0.0), 0xFFFFFFFF, 70, filled=0, width=10.0)
    for n in range(RING_SEGS):
        b0 = n * 15
        b.ellipse(f"rn{n}", gid, _bc(b.ctr(0, RN_CY, RN_D, RN_D), 0.0), 0xFFFFFFFF, 255, filled=0, begin=b0, end=min(360, b0 + 16), width=10.0)["visible"] = 0
    b.text("qm", gid, _bc(b.tl(0, RN_CY - 70, RN_D, 140), -RN_D / 2), "?!", 96, WHITE, align=1, valign=1, tracking=2)
    return g


def add_interrogation_hud(wdir):
    path = os.path.join(wdir, "hud-root.widget.json")
    w = json.load(open(path, encoding="utf-8"))
    if any(i["name"] == "t2rIntHud" for i in w["items"]):
        return 0
    root = next(i for i in w["items"] if i["name"] == "root")
    tpl = _templates(wdir, w["items"])
    add_marker_attachables(wdir, tpl)
    b = HB(tpl)
    build_hud(b, root["guid"])
    build_marker(b, root["guid"], 0)
    build_marker(b, root["guid"], 1)
    build_prompt(b, root["guid"])
    build_round(b, root["guid"])
    w["items"].extend(b.items)
    json.dump(w, open(path, "w", encoding="utf-8"), indent=4)
    return len(b.items)
