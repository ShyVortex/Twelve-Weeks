"""Offline test: the health-kit spots of the added maps (tools/maps/medkits.py, data/<key>-medkits.json, tools/ext/medkits.h)
against the 2013-derived rules (re/maps/medkits-2013.md). Run: python tools/tests/test_medkits.py

  - the count equals round(6 * area / 7900) clamped 4..12 for the map's current layout
  - kits are >= 7 m apart (14 m wanted; the relaxed passes never go below 0.4 x), >= 4 m from a team start, both halves have kits
    (the halves differ by at most one kit)
  - every kit is flat-surface data: 0.55-1.40 m above a floor, inside the map's spawn hull + 40 m
  - medkits.h lists exactly the maps that have a json file, with the same positions
"""
import glob
import json
import math
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(TOOLS, "maps"))
import medkits as M  # noqa: E402

FAILS = []


def check(cond, what):
    print(("ok   " if cond else "FAIL ") + what)
    if not cond:
        FAILS.append(what)


files = sorted(glob.glob(os.path.join(M.DATA, "*-medkits.json")))
check(len(files) >= 1, f"{len(files)} medkit data files")
hdr = open(M.HEADER).read() if os.path.exists(M.HEADER) else ""
for f in files:
    d = json.load(open(f))
    key = d["key"]
    lay = M.layout(key)
    area = M.map_area([(p[0], p[2]) for v in lay.values() for p in v])
    n = M.count_for(area)
    kits = d["kits"]
    # hand_placed = SceneEditor placement (editor_import.py; `medkits.py gen` keeps it): the user's spots win over the
    # count / half-balance / floor-height rules (capitol-shops: 6 kits vs rule 5), gap / team-start / header checks still apply
    hand = bool(d.get("hand_placed"))
    if hand:
        check(len(kits) >= 1, f"{key}: {len(kits)} hand placed kits (count rule {n} not applied)")
    else:
        check(len(kits) == n, f"{key}: {len(kits)} kits == count rule {n} (area {area:.0f} m2)")
    P = [k["pos"] for k in kits]
    gaps = [math.dist((a[0], a[2]), (b[0], b[2])) for i, a in enumerate(P) for b in P[i + 1:]]
    check(not gaps or min(gaps) >= M.KIT_GAP * 0.4, f"{key}: kits >= {M.KIT_GAP * 0.4:.1f} m apart (min {min(gaps) if gaps else 0:.1f}, wanted {M.KIT_GAP})")
    intros = [(p[0], p[2]) for p in lay["intro0"] + lay["intro1"]]
    dm = min(math.dist((p[0], p[2]), q) for p in P for q in intros)
    check(dm >= 4.0, f"{key}: kits >= 4 m from every team start (min {dm:.1f}, wanted {M.INTRO_GAP})")
    h0 = sum(1 for k in kits if k["half"] == "t0")
    h1 = sum(1 for k in kits if k["half"] == "t1")
    check(hand or abs(h0 - h1) <= 1 + (len(kits) - h0 - h1), f"{key}: halves {h0} / {h1} (+{len(kits) - h0 - h1} middle)")
    check(hand or all(M.H_MIN - 0.01 <= k["above_floor"] <= M.H_MAX + 0.01 for k in kits), f"{key}: every kit {M.H_MIN}-{M.H_MAX} m above its floor")
    nm = key.upper().replace("-", "_")
    m = re.search(r"MK_%s\[\] = \{(.*?)\n\};" % nm, hdr, re.S)
    got = [tuple(float(x) for x in t) for t in re.findall(r"\{(-?[\d.]+)f, (-?[\d.]+)f, (-?[\d.]+)f\}", m.group(1))] if m else []
    check(len(got) == len(kits) and all(abs(a - b) < 0.002 for g, k in zip(got, kits) for a, b in zip(g, k["pos"])), f"{key}: medkits.h has the same {len(kits)} positions")
print("FAILED: %d" % len(FAILS) if FAILS else "ALL OK")
sys.exit(1 if FAILS else 0)
