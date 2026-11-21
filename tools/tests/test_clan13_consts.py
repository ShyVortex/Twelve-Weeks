"""Offline: the journal day text layout constants of clan13_widgets.py (JT_*) and clan13.c (C13_JT_*) must be the same numbers.
clan13.c lays the paragraphs out itself (pivot + its own wrap); a drift puts the text in the wrong column (A/B: the C side kept the
old x 1700 / width 1840 after the page moved the column to x 2400 / width 1300, the paragraphs overlapped the week rows).
Run: python tools/tests/test_clan13_consts.py"""
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(TOOLS, "features"))
import clan13_widgets as W  # noqa: E402

c = open(os.path.join(TOOLS, "ext", "clan13.c"), encoding="utf-8").read()
fails = 0
for name in ("X", "W", "Y0", "Y1", "PT", "LINE", "CAP_H", "GAP"):
    m = re.search(r"#define C13_JT_%s ([0-9.]+)f" % name, c)
    py = float(getattr(W, "JT_" + name))
    ok = m is not None and abs(float(m.group(1)) - py) < 1e-3
    print(("ok   " if ok else "FAIL ") + "JT_%s: page %g, clan13.c %s" % (name, py, m.group(1) if m else "missing"))
    fails += not ok
print("all ok" if not fails else "FAILED: %d" % fails)
sys.exit(1 if fails else 0)
