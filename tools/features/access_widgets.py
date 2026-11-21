"""to1/options-menu-ingame (OPTIONS from the MULTIPLAYER main menu and the in-match pause menu): the ACCESSIBILITY entry is back.

The mod's options page was built without the stock page's buttonAccessibility (menu/page-options-v3 has it; same container, same
button-default reference, action "push menu/page-options-v3-accessibility-v2" -> the six native accessibility sub pages). It is copied
over as the last row of the vertical flow (the flow lays the rows out, pivotAs.y only keeps the order). Which accessibility options may
actually change in Twelve Weeks is decided in t2r-ext (feature_access: unfair ones are held at the game's default, every option is
reset to default on each entry). Returns 1 if changed."""
import copy
import json
import os
import t2guid

ROW = "buttonAccessibility"


def add_accessibility_button(wdir):
    path = os.path.join(wdir, "to1", "options-menu-ingame.widget.json")
    src = os.path.join(wdir, "menu", "page-options-v3.widget.json")
    if not (os.path.exists(path) and os.path.exists(src)):
        return 0
    w = json.load(open(path, encoding="utf-8"))
    items = w["items"]
    if any(i["name"] == ROW for i in items):
        return 0
    stock = next((i for i in json.load(open(src, encoding="utf-8"))["items"] if i["name"] == ROW), None)
    cont = next((i for i in items if i["name"] == "container1"), None)
    last = next((k for k, i in enumerate(items) if i["name"] == "buttonSystem"), None)
    if stock is None or cont is None or last is None:
        return 0
    btn = copy.deepcopy(stock)
    btn.update(guid=t2guid.guid(), parent=cont["guid"], visible=1)
    btn["pivotAs.y"] = items[last]["pivotAs.y"] + 126.0
    btn["depth"] = items[last].get("depth", 12.0) + 1.0
    items.insert(last + 1, btn)
    json.dump(w, open(path, "w", encoding="utf-8"), indent=4)
    return 1
