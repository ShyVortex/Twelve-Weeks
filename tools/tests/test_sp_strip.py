"""Offline checks of the SP-map strip step (tools/maps/collectibles.py sp_strip_collectibles_workbench: every SP map
ships without collectibles and workbenches; crafting parts and normal pickups stay).  No game files needed: the classifier, the
workbench name rules, the build hook and the committed snapshot tools/maps/data/sp-strip.json (made by
`python collectibles.py strip <map>...`, which needs the game install)."""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(TOOLS, "maps"))
import collectibles as c  # noqa: E402

# collectibles go ...
for nm, ty in (("col-tc-wat-4", "ConversationPiece"), ("coll-san-streets-slave-note-4", "ConversationPiece"),
               ("interact-loc-wat-wlf-rules-1", "ConversationPiece"), ("item-pickup-player-upgrade-generic-118", "ItemPickup"),
               ("artifact-flo-1", "ConversationPiece"), ("coin-wat-2", "ConversationPiece"), ("journal-page-3", "ConversationPiece"),
               ("training-manual-pickup-2", "ItemPickup"), ("item-pickup-bottle-499", "ItemPickup"),
               ("item-pickup-brick-497", "ItemPickup")):
    assert c.classify({"name": nm, "type": ty}), nm
# ... crafting parts and the normal pickups stay
for nm in ("item-pickup-parts-medium-173", "item-pickup-ammo-12", "item-pickup-binding-small-3", "item-pickup-blade-small-2",
           "item-pickup-health-kit-1", "item-pickup-rag-small-4", "item-pickup-alcohol-small-5", "item-pickup-canister-small-58",
           "item-pickup-explosive-small-2", "item-pickup-lead-pipe"):
    assert not c.classify({"name": nm, "type": "ItemPickup"}), nm

# workbench placements: prototypes named *workbench* (not the warehouse furniture table), building parts next to them stay
is_bench = lambda n: bool(c.BENCH.search(n)) and not c.BENCH_KEEP.search(n)  # noqa: E731
for nm in ("flo-cc-workbench-a.ma", "san-mansion-kitchen-workbench.ma", "pat-workbench-parts-bin.ma"):
    assert is_bench(nm), nm
assert not is_bench("res-retail-warehouse-workbench-a.ma")
for nm in ("san-mansion-window-c.ma", "fixtures-a-wall-plug-double.ma", "san-mansion-kitchen-floor-cabinet-a.ma",
           "san-mansion-kitchen-island.ma"):
    assert c.BENCH_FIXED.search(nm), nm
for nm in ("san-baking-set.ma", "san-mansion-mitts-set.ma", "pat-current-tester.ma", "fob-tool-screwdrivers-a.ma"):
    assert not c.BENCH_FIXED.search(nm), nm

# the build hook uses it for every selected map (not only maps with their own "edits")
src = open(os.path.join(TOOLS, "features", "sp_maps_build.py"), encoding="utf-8").read()
assert "sp_strip_collectibles_workbench" in src and "bench.get(m[\"key\"]" in src

# committed snapshot (per map counts, from the real levels)
snap = json.load(open(os.path.join(TOOLS, "maps", "data", "sp-strip.json"), encoding="utf-8"))
spec = json.load(open(os.path.join(TOOLS, "maps", "sp_maps.json"), encoding="utf-8"))["maps"]
for key in ("train-station", "wilds-houses", "capitol-shops", "into-the-city"):
    assert key in snap, key
    assert any(m["key"] == key and m.get("build") for m in spec), key
assert sum(snap["train-station"]["collectible_spawners"].values()) == 1
assert sum(snap["capitol-shops"]["collectible_spawners"].values()) == 12         # 1 location note, 1 card, 5 skill-pill pickups, 5 bottles (the parts pickup stays)
assert not snap["capitol-shops"]["workbench"] and not snap["train-station"]["workbench"]
assert [w["proto"] for w in snap["wilds-houses"]["workbench"] if w["kind"] == "bench"] == ["san-mansion-kitchen-workbench.ma"]
assert sorted(w["proto"] for w in snap["into-the-city"]["workbench"] if w["kind"] == "bench") == ["flo-cc-workbench-a.ma", "pat-workbench-parts-bin.ma"]
assert not any(c.BENCH_FIXED.search(w["proto"]) for k in snap for w in snap[k]["workbench"] if w["kind"] == "dressing")
print("sp strip OK: %s" % {k: (sum(v["collectible_spawners"].values()), len(v["workbench"])) for k, v in sorted(snap.items())})
