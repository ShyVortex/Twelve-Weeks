"""Release readiness: no calibration / TEST-mode content may ship.
Currently checked: the Train Station floor test (layout.py floortest: 8 labelled calibration boxes replace the real boxes,
"_boxes_before_floortest" in tools/maps/data/*.json).  Normally a WARNING (exit 0); with T2R_RELEASE=1 in the environment a
failure (exit 1), so a release build script can run this first."""
import glob
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
LAYOUTS = os.path.join(HERE, "..", "maps", "data", "*.json")
release = os.environ.get("T2R_RELEASE") == "1"
bad = []
for p in sorted(glob.glob(LAYOUTS)):
    try:
        raw = json.load(open(p, encoding="utf-8"))
    except (OSError, ValueError):
        continue
    if isinstance(raw, dict) and "_boxes_before_floortest" in raw:
        bad.append(os.path.basename(p))
for b in bad:
    print(("FAIL " if release else "WARN ") + b + ": still in floortest (TEST) mode - run `layout.py floortest <map> --off --pak` before a release")
if not bad:
    print("ok   no layout is in floortest mode")
print("\n%d problem(s)%s" % (len(bad), "" if release else " (warnings only; set T2R_RELEASE=1 to fail)"))
sys.exit(1 if bad and release else 0)
