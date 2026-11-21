"""The ESC / end-of-match scoreboard puts OUR team in the upper block, blue (in the ESC menu your team is always on the blue side above ... and the
enemy in the red team").  winmm fills the two fixed blocks team0_* (upper) and team1_* (lower) by the roster team index; t2r-ext (sbteam.c) swaps the two blocks'
places when our team is team 1.  So the colour has to belong to the PLACE, not to the block:

  * the two stock team bands (team0_band blue, team1_band red) are hidden; sbBlue sits at the upper band's place, sbRed at the lower one's (same size, same colours)
  * the row texts (names, numbers, ping), which were blue in the upper block and red in the lower one, wear one neutral light colour (the column heads' colour)
Both pages carry the same widgets (to1/pause-menu, to1/scoreboard).  Idempotent.
pause_restyle_widgets.add_pause_nr (runs later) replaces sbBlue / sbRed by thin team edge bars and restyles both pages in the No Return frame."""
import copy
import json
import os

import t2guid

PAGES = ("pause-menu", "scoreboard")
NEUTRAL = 0xFFE6E6E6
ROW_TEXT = ("name", "parts", "downs", "executions", "deaths", "revives", "ping")
NEW = ("sbBlue", "sbRed")


def add_sb_team(wdir):
    n = 0
    for page in PAGES:
        path = os.path.join(wdir, "to1", page + ".widget.json")
        if not os.path.exists(path):
            continue
        w = json.load(open(path, encoding="utf-8"))
        items = w["items"]
        items[:] = [i for i in items if i["name"] not in NEW]
        by = {i["name"]: i for i in items}
        if "team0_band" not in by or "team1_band" not in by:
            continue
        for k, (src, nm) in enumerate((("team0_band", "sbBlue"), ("team1_band", "sbRed"))):
            band = by[src]
            it = copy.deepcopy(band)
            it.update({"guid": t2guid.guid(), "name": nm, "tint.start": band["tint.start"], "tint.end": band["tint.start"]})
            items.insert(items.index(band) + 1, it)
            band["visible"] = 0
            band["color.a"] = 0
        for t in (0, 1):
            for r in range(4):
                for leaf in ROW_TEXT:
                    it = by.get(f"team{t}_row{r}_{leaf}")
                    if it:
                        it["tint.start"] = NEUTRAL
                        it["tint.end"] = NEUTRAL
        json.dump(w, open(path, "w", encoding="utf-8"), indent=4)
        n += 1
    return n
