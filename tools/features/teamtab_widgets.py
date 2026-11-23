"""Team / ready bands on the lobby rows (small blue/red tabs signal which team people are on (including yourself) instead of T1 and
T2; in the party system unready players are grey, green when ready; the tabs are one soft red/blue gradient behind the text itself, 100% on the
left and fading out smoothly to the right (one gradient band each); widget names unchanged).

The two row widgets of the LOBBY box (to1/lobby-row = the MP menu rows and find-match Player0, to1/find-match-row = the searching / MATCH FOUND rows) each carried
the game's team symbol (teamSymbol, a 44 px marker icon that winmm shows per found player). That icon is made zero-size here and four flat tabs take its
place: a full-row-height band behind the name text (depth 1.0, text is 2.0) starting at the left edge at full strength and easing out to
transparent over BAND_W (one white alpha-ramp texture streaming/t2r/icons/team-grad.png = make_icons.team_grad, tinted per state; widget alpha = strength);
hidden by default; t2r-ext (friends13.c fr_lobby_tabs) shows exactly one per row:
    tabGrey   party member, not ready          tabGreen  party member ready (the leader always)
    tabBlue   our team (the viewer, teammates) tabRed    the enemy team
The same colours (0xFF48A8D8 / 0xFFE04848) are the match HUD's ally / enemy colours (matchflow_widgets HUD_BLUE / HUD_RED)."""
import copy
import json
import os
import t2guid

GREY, GREEN, BLUE, RED = 0xFF4C4E52, 0xFF7FD07A, 0xFF48A8D8, 0xFFE04848
TABS = (("tabGrey", GREY), ("tabGreen", GREEN), ("tabBlue", BLUE), ("tabRed", RED))
ROWS = ("lobby-row", "find-match-row")
BAND_W, BAND_A = 700.0, 200                      # band width in row units (the row is 1080 x 100; the name starts at x 120), widget alpha (~59 %, the white name stays readable)
GRAD = "streaming/t2r/icons/team-grad.png"


def add_team_tabs(wdir):
    n = 0
    for page in ROWS:
        path = os.path.join(wdir, "to1", page + ".widget.json")
        w = json.load(open(path, encoding="utf-8"))
        items = w["items"]
        items[:] = [i for i in items if i["name"] not in {t[0] for t in TABS}]            # (rebuild: rects of the earlier tab style)
        root = next(i for i in items if i["name"] == "root")
        bg = next(i for i in items if i["name"] == "cardBg")
        sym = next(i for i in items if i["name"] == "teamSymbol")
        sym.update({"rectSizeDelta.width": 0.0, "rectSizeDelta.height": 0.0, "visible": 0, "color.a": 0})      # winmm still sets it; nothing shows
        for k, (name, argb) in enumerate(TABS):
            it = copy.deepcopy(bg)
            it.update({"guid": t2guid.guid(), "name": name, "parent": root["guid"], "depth": 1.0 + k * 0.01, "visible": 0, "color.a": BAND_A, "path": GRAD,
                       "anchorMinN.x": 0.0, "anchorMinN.y": 0.0, "anchorMaxN.x": 0.0, "anchorMaxN.y": 1.0, "pivotN.x": 0.0, "pivotN.y": 0.5,
                       "pivotAs.x": 0.0, "pivotAs.y": 0.0, "rectSizeDelta.width": BAND_W, "rectSizeDelta.height": 0.0,
                       "tint.start": argb, "tint.end": argb, "tint.blend": 0.0, "scaleMode": "Stretch"})
            items.append(it)
        json.dump(w, open(path, "w", encoding="utf-8"), indent=4)
        n += 1
    return n


# ---- party marks (a "(party - not searching)" suffix in the name was obnoxious): a party row gets a thin amber bar on the left edge (one shared party colour), a right-aligned
# two-line tag (PARTY LEAD / PARTY, then READY / NOT READY); t2r-ext (friends13.c fr_lobby_party_marks) strips the old suffix from the name and shows exactly these.
AMBER, OKG, DIMG = 0xFFE2B45A, 0xFF7FD07A, 0xFF9A9CA0
BAR_W = 8.0
TAG_W, TAG_RX = 210.0, -30.0                     # tag box width, right margin (the name label ends at 78 % = 842 of the 1080 row, the tag starts at 840)
PM_TEXTS = (("pmRole", AMBER, 14.0, 26), ("pmReady", OKG, 52.0, 30), ("pmNot", DIMG, 52.0, 30),     # name, colour, y of the text box top, point size
            ("lbSt", 0xFFFFFFFF, 33.0, 26))      # (lobby panel) the lobby status, one line centred: READY / IN SUMMARY / NEW (font colours from friends13.c)
PM_W = {"lbSt": 360.0}


def add_party_marks(wdir):
    n = 0
    for page in ROWS:
        path = os.path.join(wdir, "to1", page + ".widget.json")
        w = json.load(open(path, encoding="utf-8"))
        items = w["items"]
        names = {"partyBar"} | {t[0] for t in PM_TEXTS}
        items[:] = [i for i in items if i["name"] not in names]
        root = next(i for i in items if i["name"] == "root")
        bg = next(i for i in items if i["name"] == "cardBg")
        nm = next(i for i in items if i["name"] == "nameLabel")
        bar = copy.deepcopy(bg)
        bar.update({"guid": t2guid.guid(), "name": "partyBar", "parent": root["guid"], "depth": 1.2, "visible": 0, "color.a": 255, "path": "general-textures/square-32px.png",
                    "anchorMinN.x": 0.0, "anchorMinN.y": 0.0, "anchorMaxN.x": 0.0, "anchorMaxN.y": 1.0, "pivotN.x": 0.0, "pivotN.y": 0.5,
                    "pivotAs.x": 0.0, "pivotAs.y": 0.0, "rectSizeDelta.width": BAR_W, "rectSizeDelta.height": 0.0,
                    "tint.start": AMBER, "tint.end": AMBER, "tint.blend": 0.0, "scaleMode": "Stretch"})
        items.append(bar)
        for k, (name, argb, y, pt) in enumerate(PM_TEXTS):
            t = copy.deepcopy(nm)
            t.update({"guid": t2guid.guid(), "name": name, "parent": root["guid"], "depth": 2.1 + k * 0.01, "visible": 0, "text": "", "pointSize": pt, "alignH": 2, "alignV": 1,
                      "multiline": 0, "tracking.x": 3.0, "color.a": 255, "tint.start": argb, "tint.end": argb, "tint.blend": 0.0,
                      "anchorMinN.x": 1.0, "anchorMinN.y": 0.0, "anchorMaxN.x": 1.0, "anchorMaxN.y": 0.0, "pivotN.x": 1.0, "pivotN.y": 0.0,
                      "pivotAs.x": TAG_RX, "pivotAs.y": y, "rectSizeDelta.width": PM_W.get(name, TAG_W), "rectSizeDelta.height": 34.0})
            items.append(t)
        json.dump(w, open(path, "w", encoding="utf-8"), indent=4)
        n += 1
    return n
