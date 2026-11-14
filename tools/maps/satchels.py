"""Supply satchel spots (re/satchel-1102.md): python satchels.py  ->  data/<key>-satchels.json + tools/ext/itemspots.h

Fixed spots, 3 per shipped map, in the item-spot data format (itemspots.c: a spot whose only candidate is `parts` is a dedicated satchel spot, always filled,
60 s respawn).  Placed by tools/maps/box_place.py (satchels): navmesh FLOOR points flush against a wall / cover (footprint 0.45 x 0.30 m, 1.6 m open floor in front),
y = floor + 0.02, quat = yaw facing out of the wall; in non-hallway rooms with some traffic, >= 14 m (path) from every supply box, >= 20 m (path) from each other,
>= 8 m from the intro spawns.  (The medkit-surface picker put bags in the air / in foliage: the ext's ground probe never hit.)
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
DATA = os.path.join(HERE, "data")
MAPS = {"train-station": 3, "hospital": 3, "wilds-houses": 3, "capitol-shops": 3, "into-the-city": 3, "overpass": 3, "chase": 3, "jackson-market": 3}


NAV_KEY = {"hospital": "hospital-ellie"}      # the item-spot / map-list key -> the layout / navmesh key of the shipped map
MAPS_INDEX = {"chase": 22, "jackson-market": 23}   # not in medkits.INDEX


def main():
    import box_place
    import itemspots
    import layoutlib
    for key, want in MAPS.items():
        nk = NAV_KEY.get(key, key)
        sats, ctx, ras, lay = box_place.satchels(nk, want)
        spots = [{"pos": s["pos"], "quat": s["quat"], "family": "satchel", "arts": ["satchel"]} for s in sats]
        idx = MAPS_INDEX.get(key)
        if idx is None:
            idx = itemspots.index_of(key)
        d = {"key": key, "map_index": idx, "rule": __doc__.split(chr(10))[2].strip(), "boxes_checked": len(lay["boxes"]),
             "from": [{"traffic": s["traffic"], "yaw_deg": s["yaw_deg"], "quality": s["q"]} for s in sats], "spots": spots}
        json.dump(d, open(os.path.join(DATA, f"{key}-satchels.json"), "w", newline=chr(10)), indent=1)
        box_place.draw_satchels(nk, sats, ctx, ras, lay)
        print(key, len(spots), "spots", [s["pos"] for s in spots])
    itemspots.write_header()


if __name__ == "__main__":
    main()
