"""Offline check of the Bookstore upper-floor ring wall removal: tools/maps/data/p1-bookstore-colledits-auto.json holds exactly the 12 triangles of Part I's
layer-0x23 planes (x 100.7..115.6, y 4.45..8.09, z 278.3..300.3), all vertical and tall; when the converted paks are around (T2R_P1_CONV) the file equals what
p1_ring_wall.py derives from them.  Run: python tools/tests/test_p1_ring_wall.py"""
import json
import os
import sys
HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(TOOLS, "part1"))
FAILS = []


def check(c, what):
    print(("ok   " if c else "FAIL ") + what)
    if not c:
        FAILS.append(what)


d = json.load(open(os.path.join(TOOLS, "maps", "data", "p1-bookstore-colledits-auto.json"), encoding="utf-8"))
e = d["edits"][0]
T = e["tris"]
check(len(d["edits"]) == 1 and e["kind"] == "delete" and e["level"] == "hun-checkpoint-bookstore" and e.get("active"), "one active delete edit on hun-checkpoint-bookstore")
check(len(T) == 12, "12 triangles (6 quads)")
xs = [t[i] for t in T for i in (0, 3, 6)]
ys = [t[i] for t in T for i in (1, 4, 7)]
zs = [t[i] for t in T for i in (2, 5, 8)]
check(abs(min(xs) - 100.7) < 0.05 and abs(max(xs) - 115.6) < 0.05 and abs(min(zs) - 278.3) < 0.05 and abs(max(zs) - 300.3) < 0.05 and min(ys) > 4.4 and max(ys) < 8.15, "bbox = the hall ring (x 100.7-115.6, z 278.3-300.3, y 4.45-8.09)")
check(all(max(t[1], t[4], t[7]) - min(t[1], t[4], t[7]) > 2.0 for t in T), "every triangle is 2+ m tall (vertical plane, not a railing box 1 m)")
conv = os.environ.get("T2R_P1_CONV")
if conv and os.path.exists(os.path.join(conv, "hun-checkpoint-bookstore-phys.pak")):
    import p1_ring_wall as R
    got = R.ring_triangles(conv)
    key = lambda t: tuple(round(float(v), 4) for v in t)
    check(sorted(key(t.reshape(-1)) for t in got) == sorted(tuple(t) for t in T), "file == triangles derived from the converted pak")
else:
    print("skip  (T2R_P1_CONV not set: not compared with the converted pak)")
print("ALL OK" if not FAILS else "FAILED: %d" % len(FAILS))
sys.exit(1 if FAILS else 0)
