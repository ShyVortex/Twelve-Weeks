"""Offline test of the pre-made classes (GEAR UP presets, re/preset-classes-v3.md).
The one source is CLASSES[] in tools/ext/t2r-ext.c (read by tools/classes_src.py); this checks that every copy matches it and that the
table obeys the design rules.   Run: python tools/tests/test_classes.py   (plain python, no game files)."""
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
def check(cond, what):
    print(("ok   " if cond else "FAIL ") + what)
    if not cond:
        FAILS.append(what)

def read(*p):
    return open(os.path.join(ROOT, *p), encoding="utf-8", errors="replace").read()

ext = read("tools", "ext", "t2r-ext.c")
skills_c = read("tools", "ext", "skills.c")
gd = read("release", "launcher", "src", "gamedata.js")
G = json.loads(gd[gd.index("= ") + 2: gd.rindex(";")])
classes = classes_src.parse()

# ---- the tables the launcher data was built from (gen-gamedata.py): weapon rows with LP, skills with level costs
wbyid = {w["id"]: (slot, w) for slot, ws in G["weapons"].items() for w in ws}
skkey = [s["key"] for s in G["skills"]]
SLOTS = ("large", "small", "purch")

# suppressible guns = the lists install_weapon_tables builds "-supp" rows for
large_supp = set(re.findall(r'"([a-z0-9-]+)"', re.search(r"LARGE_SUPP\[\] = \{(.*?)\};", ext, re.S).group(1)))
small_supp = set(re.findall(r'"([a-z0-9-]+)"', re.search(r"SMALL_SUPP\[\] = \{(.*?)\};", ext, re.S).group(1)))
supp_ok = {"large": large_supp, "small": small_supp, "purch": set()}

check(len(classes) == 8, "8 preset classes (the picker page scrolls 6 custom + 8)")
check(len({c["name"] for c in classes}) == 8, "class names unique")

def lp_of(c):
    total = 0
    for slot, wid in zip(SLOTS, c["w"]):
        if not wid:
            continue
        sup = wid.endswith("-supp")
        base = wid[:-5] if sup else wid
        ok = base in wbyid and wbyid[base][0] == slot
        check(ok, f"{c['name']}: {slot} gun {wid} exists in the {slot} table")
        if not ok:
            continue
        if sup:
            check(base in supp_ok[slot], f"{c['name']}: {base} has a suppressed row")
        total += wbyid[base][1]["lp"] + (wbyid[base][1]["supp"] if sup else 0)
    seen = set()
    check(len(c["skills"]) <= 4, f"{c['name']}: at most 4 skill rows")
    for k, lv in c["skills"]:
        check(k in skkey, f"{c['name']}: skill {k} exists")
        if k not in skkey:
            continue
        s = G["skills"][skkey.index(k)]
        check(1 <= lv <= s["levels"], f"{c['name']}: {k} level {lv} is valid")
        check(k not in seen, f"{c['name']}: {k} not picked twice")
        seen.add(k)
        total += s["cost"][lv - 1]
    return total

for c in classes:
    lp = lp_of(c)
    check(lp <= 13, f"{c['name']}: {lp} LP <= 13")
    check(lp >= 12, f"{c['name']}: {lp} LP nearly / fully spent")
    check(c["w"][0] is not None, f"{c['name']}: has a large firearm")
    check(c["w"][1] is not None, f"{c['name']}: has a small firearm")

# ---- design rules
used = {w[:-5] if w and w.endswith("-supp") else w for c in classes for w in c["w"]}
check(not any((w or "").startswith("shotgun-tactical") for c in classes for w in c["w"]),
      "no preset uses the Tactical Shotgun (limited to 1 per team: a dimmed preset is a bad first experience)")
for g in ("rifle-vepr", "rifle-remington-bolt", "bow-ellie", "rifle-mpx5", "rifle-m14-semi", "rifle-frontier", "rifle-burst",
          "pistol-beretta", "pistol-revolver-taurus", "pistol-glock", "pistol-cz75-enforcer", "shotgun-shorty", "shotgun-remington-pump",
          "rifle-galil", "crossbow", "pistol-el-diablo", "rifle-milsniper", "shotgun-baserri-over-under", "rifle-assault-firefly-ellie-player"):
    check(g in used, f"gun {g} appears in at least one preset")
check(any(w and w.endswith("-supp") for c in classes for w in c["w"]), "a preset with suppressed (QUIET) guns")
check(len({tuple(c["w"]) for c in classes}) == len(classes), "no two presets with the same guns")

# ---- sources agree
by_name = {c["name"]: c for c in classes}
gc = G["classes"]
check([c["name"] for c in gc] == [c["name"] for c in classes], "launcher gamedata.js: same classes in the same order")
for g in gc:
    c = by_name.get(g["name"])
    if not c:
        continue
    mine = []
    for slot in SLOTS:
        s = g["slots"][slot]
        mine.append(None if not s else s["id"] + ("-supp" if s["supp"] else ""))
    check(mine == c["w"], f"launcher gamedata.js: {g['name']} guns match the ext")
    check([(skkey[k["id"]], k["lv"]) for k in g["skills"]] == c["skills"], f"launcher gamedata.js: {g['name']} skills match the ext")
    check(g["desc"] == c["desc"], f"launcher gamedata.js: {g['name']} description matches the ext")
    check(g["lp"] == lp_of(c), f"launcher gamedata.js: {g['name']} LP matches")

# ---- Polish in every place the strings live
pl_txt = {}
for line in read("tools", "loc", "pl", "02-gearup.txt").splitlines():
    if " => " in line and not line.startswith("##"):
        a, b = line.split(" => ", 1)
        pl_txt.setdefault(a, b)
loc_h = read("tools", "ext", "loc_pl.h")
game_pl = json.loads(read("release", "launcher", "src", "i18n", "game-pl.json"))
def cesc(s):
    return s.replace("\\", "\\\\").replace('"', '\\"')
for c in classes:
    for en in (c["name"], c["desc"]):
        pl = pl_txt.get(en)
        check(bool(pl) and pl != en, f"PL source (tools/loc/pl/02-gearup.txt): {en[:40]}")
        if not pl:
            continue
        check('{"%s", "%s"}' % (cesc(en), cesc(pl)) in loc_h, f"tools/ext/loc_pl.h matches: {en[:40]}")
        check(game_pl.get(en) == pl, f"launcher i18n/game-pl.json matches: {en[:40]}")
# no stale class text left behind in the PL source
stale = [k for k in pl_txt if k not in {x for c in classes for x in (c["name"], c["desc"])} and
         re.match(r"(Front line fighter|Picks targets from afar|Moves unheard|Keeps the group alive|Scouts ahead|Wins with|Volleys of fire|Silenced firepower)", k)]
check(not stale, "no stale class descriptions in the PL source: %s" % stale)

# ---- ext wiring: the 4th skill row belongs to the class (resolved copies are identified by g_lo_res, not the lobby's)
check("SK4_CLASS" not in skills_c and "CLASSES[k].s4" in skills_c and "g_lo_res" in skills_c, "skills.c: the class's own 4th skill (CLASSES[].s4)")
check("lo_write_obj_forced(wsrc)" in ext, "spawn kit: the pending loadout is written from the table's object (4th skill kept)")
check("T2R_FRONTIER_PICK ?" not in ext[ext.index("CLASSES[] = {"):ext.index("#define N_CLASSES")], "class table has no build-switch expression (parseable)")

print("\n%d failure(s)" % len(FAILS))
sys.exit(1 if FAILS else 0)
