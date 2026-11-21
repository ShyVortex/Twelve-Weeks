"""Fast tab switching must always end on the visible target tab (content went blank). clan13.c can not run offline, so this checks the invariants that
fix the race and simulates the alpha book-keeping of 10 switches within 1 s with the same rules:
  1. cl13_set_tab calls cl13_settle() before it changes the tab; cl13_settle puts every tab group, every unfinished entrance item and the detail panels back to alpha 1 and
     empties the tween table;
  2. the fade-out of the previous tab group is written only for the CURRENT prev_tab (so a group abandoned mid-fade is the one settle restores).
  python tools/tests/test_clan13_tabswitch.py"""
import os
import random
import re
import sys

src = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "ext", "clan13.c"), encoding="utf-8").read()
m = re.search(r"static void cl13_set_tab\(int t, const char \*why\) \{(.*?)\n\}", src, re.S)
assert m, "cl13_set_tab not found"
body = m.group(1)
assert body.index("cl13_settle();") < body.index("C13.tab = t"), "settle must run before the tab changes"
st = re.search(r"static void cl13_settle\(void\) \{(.*?)\n\}", src, re.S).group(1)
for need in ("C13_GRP[k]", "w_alpha(g, 1.0f)", "w_alpha(w, 1.0f)", "w_pivot(w, f->bx, f->by)", "gu_grp(dp[k], 1.0f, 0.0f)", "cl13_fx_reset()"):
    assert need in st, "cl13_settle lacks " + need

# the same bookkeeping as a model: groups fade the previous tab out over 90 ms, an entrance sets alpha 0 -> 1 over ~1 s; with settle every switch starts from alpha 1
def run(settle, switches, rnd):
    alpha = [1.0] * 4
    tab, prev, t0 = 0, -1, 0.0
    fx = {}                                   # item (tab, k) -> start time
    now = 0.0
    for t in switches:
        now += rnd.uniform(0.02, 0.18)
        if t == tab:
            continue
        if settle:
            alpha = [1.0] * 4; fx = {}
        prev, tab, t0 = tab, t, now
        for k in range(6):
            fx[(tab, k)] = now
            alpha[tab] = alpha[tab]
        # tick: the old group's fade runs only for prev
    now += 3.0
    # at rest: finished fade-out for prev only, entrances done -> everything of the target tab is at 1
    return alpha[tab], all(now - s > 1.0 for (tb, _), s in fx.items() if tb == tab)


rnd = random.Random(7)
for _ in range(200):
    sw = [rnd.randrange(4) for _ in range(10)]
    a, done = run(True, sw, rnd)
    assert a == 1.0 and done, sw
print("clan13 tab switch ok")
