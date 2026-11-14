"""Backpack (TAB) menu: hide the SP journal tab (players sometimes still got the journal tab after loading into a match; it is now
forced hidden in the tab menu).

menu-player-tabs/page-player-menu-tabs-pc.widget (gui2-widgets-pc.pak, which wins on PC) has three tabs: craftingTab / upgradesTab (the mod's
buy menu) / collectiblesTab (source menu-collectibles/collect-root.widget = the SP collectibles / journal page), with the tab bar buttons
button1..3 (the third carries hud/player-menu/collectibles-tab). MP has no collectibles, so the third tab button and its page are hidden
(visible 0); the other two stay as they are. T2R_JOURNAL_TAB=1 keeps the stock tab. UNVERIFIED in game: if the tab bar script
(ss-hud2-proto-tab-bar) still lets the shoulder buttons land on the hidden page, the next step is dropping the tab from that script's list.
"""
import json
import os
import shutil
import subprocess
import tempfile

TOOLS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GUI2 = os.path.join(TOOLS, "local", "gui2", "gui2_cli", "gui2.exe")
SIDBASE = os.path.join(TOOLS, "win", "ext", "dcmain", "build", "sidbase.bin")
REL = os.path.join("pc", "menu-player-tabs", "page-player-menu-tabs-pc.widget.json")


def hide_journal_tab(pak_path):
    """Returns the number of widgets hidden (0 = pak untouched)."""
    if os.environ.get("T2R_JOURNAL_TAB") == "1":
        return 0
    tmp = tempfile.mkdtemp(prefix="t2r_tabs_")
    try:
        subprocess.run([GUI2, "extract", pak_path, tmp, "--sidbase", SIDBASE], check=True, capture_output=True)
        path = os.path.join(tmp, REL)
        w = json.load(open(path, encoding="utf-8"))
        byg = {i["guid"]: i for i in w["items"]}
        top = [i for i in w["items"] if i.get("name") in ("button3", "collectiblesTab")]
        assert any(i["name"] == "button3" for i in top) and any(i["name"] == "collectiblesTab" for i in top), "player-menu tab widgets changed"
        n = 0
        for i in w["items"]:
            p = i
            while p is not None and p not in top:
                p = byg.get(p.get("parent"))
            if p is not None and "visible" in i:
                i["visible"] = 0
                n += 1
            elif p is not None:
                i["visible"] = 0
                n += 1
        json.dump(w, open(path, "w", encoding="utf-8"), indent=4)
        out = pak_path + ".new"
        subprocess.run([GUI2, "build", tmp, out, "--t2r"], check=True, capture_output=True)
        os.replace(out, pak_path)
        return n
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
