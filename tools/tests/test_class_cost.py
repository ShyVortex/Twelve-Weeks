"""Class cost audit (re/class-cost-1019.md): every predefined class must cost the same LP on every path the ext prices it by.
Models lo_cost() of t2r-ext.c offline: guns from the launcher data (= the game tables, except the bow, see GAME_LP), skills from SK[] in
skills.c, the 4th skill from CLASSES[].s4.  The old bug: a class copy priced through the LOBBY's 4th skill (g_sk4_cur), so a class cost
12 at boot (lobby 4th empty) and 12 + (previous loadout's 4th skill) mid-match -> 'change failed lo_valid (cost 14)'.
Run: python tools/tests/test_class_cost.py"""
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.dirname(HERE)
ROOT = os.path.dirname(TOOLS)
sys.path.insert(0, TOOLS)
import classes_src  # noqa: E402

FAILS = []


def check(c, w):
    print(("ok   " if c else "FAIL ") + w)
    if not c:
        FAILS.append(w)


def rd(*p):
    return open(os.path.join(ROOT, *p), encoding="utf-8", errors="replace").read()


ext, sk_c = rd("tools", "ext", "t2r-ext.c"), rd("tools", "ext", "skills.c")
gd = rd("release", "launcher", "src", "gamedata.js")
G = json.loads(gd[gd.index("= ") + 2: gd.rindex(";")])
wb = {w["id"]: (s, w) for s, ws in G["weapons"].items() for w in ws}
# SK[] costs of the ext (what sk_lookup / lo_cost use) must be the launcher's / picker's
SK = {k: [int(x) for x in c.split(",")]
      for k, c in re.findall(r'\[(SK_[A-Z0-9]+)\] = \{"[^"]+", SK_ICON\("[^"]+"\), \d, \{([\d, ]+)\}', sk_c)}
check(len(SK) == len(G["skills"]), "skills.c SK[] has every launcher skill (%d)" % len(SK))
for s in G["skills"]:
    check(SK.get(s["key"]) == s["cost"], "skill %s costs %s in skills.c and the launcher" % (s["key"], s["cost"]))
# the game's bow row carries 2 LP until the PEND P1 price (re/stats-consistency-1019.md) lands: then this exception goes
bow_fixed = re.search(r'bow-ellie"\)\) \*\(uint32_t \*\)\(nl \+ i \* 0x38 \+ 0x18\) = 3', ext) is not None
GAME_LP = {} if bow_fixed else {"bow-ellie": 2}


def cost(c, s4_slot):
    """s4_slot: what sk4_slot() hands lo_cost for this loadout_t: 'own' = CLASSES[].s4, or an int = the lobby's 4th skill cost."""
    t = 0
    for wid in c["w"]:
        if wid:
            sup = wid.endswith("-supp")
            base = wid[:-5] if sup else wid
            t += GAME_LP.get(base, wb[base][1]["lp"]) + (wb[base][1]["supp"] if sup else 0)
    sk = c["skills"]
    t += sum(SK[k][lv - 1] for k, lv in sk[:3])
    s4 = sk[3:]
    t += sum(SK[k][lv - 1] for k, lv in s4) if s4_slot == "own" else s4_slot
    return t


classes = classes_src.parse()
for c in classes:
    own = cost(c, "own")
    check(own <= 13, "%s: %d LP through its own 4th skill (the lo_of path) is valid" % (c["name"], own))
    check(own >= 12, "%s: %d LP, budget nearly spent" % (c["name"], own))
# structural guards: the wiring that makes 'own' the only path
check("cls[k] = CLASSES[k].s4" in sk_c and "g_lo_res" in sk_c, "sk4_slot resolves a g_lo_res element to CLASSES[].s4")
i0 = ext.index("static const loadout_t *lo_of(int idx) {")
body = ext[i0:ext.index("static void lo_read_obj(loadout_t", i0)]
check("loadout_t *res = g_lo_res;" in body and "&res[c]" in body and "return l;" in body,
      "lo_of hands out the g_lo_res element itself (never a copy)")
for m in re.finditer(r"lo_write_obj(?:_forced)?\(([^;\n]*)\)", ext):
    a = m.group(1).strip()
    if a.startswith("const loadout_t"):
        continue
    check(a.startswith("lo_of(") or a in ("wsrc", "&want", "l"), "lo_write_obj* caller passes a table object (or the spawn's own copy): %r" % a)
# the one copy that is written back (&want) is written AFTER sk4_on_write set g_sk4_cur from the class, so its price is the class's
i1 = ext.index("static int lo_write_obj_forced(const loadout_t *l) {")
fwd = ext[i1:ext.index("// Mid-match change (skills were applied", i1)]
check(fwd.count("sk4_on_write(l);") == 1, "forced write sets g_sk4_cur from the class before any copy is priced")
check("pre-match write refused by lo_valid" in ext, "lo_write_obj logs a refusal (no silent class drop)")
# the old failure, reproduced by the model: pricing a class through a lobby 4th skill gives 12 + that skill
for c in classes:
    if len(c["skills"]) > 3:
        check(cost(c, 0) < 13 and cost(c, 2) == cost(c, 0) + 2,
              "%s: the OLD lobby-4th path priced %d at boot and %d with a 2 LP lobby skill" % (c["name"], cost(c, 0), cost(c, 2)))
print("\n%d failure(s)" % len(FAILS))
sys.exit(1 if FAILS else 0)
