"""ui_r2_widgets: default OFF, the per-screen opt-in switches, and put()/seg() geometry (no game, no pak)."""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "features"))
import ui_r2_widgets as u  # noqa: E402

KEYS = ("T2R_UI_R2", "T2R_UI_R2_LOAD", "T2R_UI_R2_VOTE", "T2R_UI_R2_NAME", "T2R_UI_R2_POST")


def clear():
    for k in KEYS:
        os.environ.pop(k, None)


clear()
assert not any(u.on(s) for s in ("load", "vote", "name", "post")), "default must be OFF (the 2013-faithful match flow)"
os.environ["T2R_UI_R2"] = "1"
assert not any(u.on(s) for s in ("load", "vote", "name", "post")), "the global switch does not turn the match flow on"
os.environ["T2R_UI_R2_VOTE"] = "1"
assert u.on("vote") and not u.on("load"), "per-screen opt-in"
clear()
os.environ["T2R_UI_R2_NAME"] = "off"
assert not u.on("name") and not u.on("post")
clear()

# put(): a stretch-anchored (fill) item becomes a top-left rect; a centre-pivot item stays centred on the rect
fill = {"anchorMinN.x": 0.0, "anchorMinN.y": 0.0, "anchorMaxN.x": 1.0, "anchorMaxN.y": 1.0, "pivotN.x": 0.5, "pivotN.y": 0.5,
        "pivotAs.x": 0.0, "pivotAs.y": 0.0, "rectSizeDelta.width": 0.0, "rectSizeDelta.height": 0.0}
u.put(fill, 10, 20, 300, 170)
assert (fill["anchorMaxN.x"], fill["pivotN.x"], fill["pivotAs.x"], fill["rectSizeDelta.width"]) == (0.0, 0.0, 10.0, 300.0)
ctr = {"anchorMinN.x": 0.0, "anchorMinN.y": 0.0, "anchorMaxN.x": 0.0, "anchorMaxN.y": 0.0, "pivotN.x": 0.5, "pivotN.y": 0.5,
       "pivotAs.x": 0.0, "pivotAs.y": 0.0, "rectSizeDelta.width": 0.0, "rectSizeDelta.height": 0.0}
u.put(ctr, 100, 200, 60, 40)
assert (ctr["pivotAs.x"], ctr["pivotAs.y"]) == (130.0, 220.0)
ln = dict(ctr, **{"pointsUv": [0, 0, 1, 1]})
u.seg(ln, 50, 80, 450, 80)
assert ln["pointsUv"][1] == 0.0 and ln["rectSizeDelta.width"] == 400.0
print("ui_r2_widgets: ok")
