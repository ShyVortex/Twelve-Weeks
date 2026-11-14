"""Builds src/gamedata.js (the Loadout and Clan tabs' data) from the mod's own sources:

  skills            tools/ext/skills.c  SK[]   (name, LP cost per level, 2013 descriptions)
  classes           tools/ext/t2r-ext.c CLASSES[]  (the 8 pre-made loadouts: guns + 4 skill rows), via tools/classes_src.py
  clan rules/tables tools/clan.py (MISSIONS, events, needed per day ...) - the server computes; the launcher only needs names
  weapons + LP      the mod builds its GEAR UP tables at run time (t2r-ext.c weapon tables, winmm lp-* patches). The rows below are
                    copied from re/factions2013/DESIGN.md "LP balance" + the cost comments next to CLASSES[] in t2r-ext.c
                    (silencer: +1 small firearm, +2 large firearm; 13 LP in total, 3 weapon slots + 4 skill rows).
Run: python scripts/gen-gamedata.py   (from release/launcher)
"""
import json, os, re, sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
SKILLS_C = os.path.join(ROOT, "tools", "ext", "skills.c")
EXT_C = os.path.join(ROOT, "tools", "ext", "t2r-ext.c")

src = open(SKILLS_C, encoding="utf-8", errors="replace").read()
start = src.index("static const sk_def_t SK[SK_COUNT] = {")
end = src.index("};", start)
block = src[start:end]
skills = []
for m in re.finditer(r"\[(SK_[A-Z]+)\] = \{\"([^\"]+)\", SK_ICON\(\"([^\"]+)\"\), (\d), \{([\d, ]+)\}, (\d),\s*\{(.*?)\},\s*(?:\"|NULL)", block, re.S):
    key, name, icon, nlv, costs, avail, descs = m.groups()
    ds = re.findall(r'"((?:[^"\\]|\\.)*)"', descs)
    skills.append({"key": key, "name": name, "icon": icon, "levels": int(nlv), "cost": [int(x) for x in costs.split(",")][: int(nlv)],
                   "desc": [d.replace('\\"', '"').replace("|gen:flashlight|", "the mark button").replace("|gen:jump|", "jump") for d in ds][: int(nlv)]})
keys = [s["key"] for s in skills]
assert len(skills) == 31, len(skills)

# ---- weapons: exactly the rows / names / LP / icons of the mod's GEAR UP tables (tools/ext/t2r-ext.c install_weapon_tables + the original
# winmm.dll rows read from the dll: large 0x1800A0DB0, small 0x1800A0E90, purchasable 0x1800A0F40; LP patches in features/winmm_patches.py).
# Order = the picker's order. icon = the game's HUD icon of the row (loud), supIcon = the mod's suppressed icon (quiet); supp = LP added by the
# suppressor (+2 large, +1 small; none for the bow, revolver, shorty, purchasables).
def W(id, name, lp, icon, supIcon=None, supp=0):
    return {"id": id, "name": name, "lp": lp, "icon": icon, "supIcon": supIcon, "supp": supp}
weapons = {
    "large": [W("rifle-vepr", "VARIABLE RIFLE", 2, "vepr-scp", "vepr-supp", 2), W("rifle-remington-bolt", "HUNTING RIFLE", 2, "remington-bolt-scp", "remington-bolt-supp", 2),
              W("bow-ellie", "BOW", 3, "bow"), W("rifle-mpx5", "FULL-AUTO RIFLE", 2, "mpx5-nocan", "mpx5", 2), W("rifle-m14-semi", "SEMI-AUTO RIFLE", 2, "m14", "m14-supp", 2),
              W("shotgun-tactical", "TACTICAL SHOTGUN", 3, "tac-shotgun", "tac-shotgun-supp", 2), W("rifle-frontier", "FRONTIER RIFLE", 2, "frontier", "frontier-supp", 2),
              W("rifle-burst", "BURST RIFLE", 2, "burst-rifle", "burst-rifle-supp", 2)],
    "small": [W("pistol-beretta", "9MM PISTOL", 0, "colt", "colt-supp", 1), W("pistol-revolver-taurus", "REVOLVER", 0, "revolver-brl"),
              W("pistol-glock", "BURST PISTOL", 1, "glock", "glock-supp", 1), W("pistol-cz75-enforcer", "ENFORCER", 1, "cz75", "cz75-supp", 1), W("shotgun-shorty", "SHORTY", 1, "shorty")],
    "purch": [W("shotgun-remington-pump", "PUMP SHOTGUN", 4, "pump-shotgun"), W("pistol-xcaliber", "HUNTING PISTOL", 3, "hunting-pistol"), W("rifle-galil", "SPECTER", 3, "specter"),
              W("crossbow", "CROSSBOW", 3, "crossbow"), W("pistol-el-diablo", "EL DIABLO", 3, "el-diablo"), W("machete", "MACHETE", 2, "machete"),
              W("rifle-milsniper", "MILITARY SNIPER", 3, "milsniper"), W("shotgun-baserri-over-under", "DOUBLE BARREL", 1, "double-barrel"),
              W("rifle-assault-firefly-ellie-player", "ASSAULT RIFLE", 3, "assault-rifle")],
}
# descriptions: the in-game strings (t2r-ext.c rows for the mod's guns; the unpatched winmm.dll rows for the game's own: hunting rifle, bow, 9mm, revolver, burst pistol)
DESC = {
    "rifle-vepr": "A rifle with a variable zoom scope. Press jump while aiming to change the zoom level. Four body shots to down.",
    "rifle-remington-bolt": "Bolt-action. Two body shots to down, a headshot kills.", "bow-ellie": "Silent and lethal. Arrows can be recovered.",
    "rifle-mpx5": "Full-auto. Steady damage at mid range.", "rifle-m14-semi": "A reliable mid-range killer. Three body shots to down.",
    "shotgun-tactical": "Tight spread, long reach. Two shots to down.", "rifle-frontier": "A lever-action rifle. Heavy hits, slow cycling. Two body shots to down.",
    "rifle-burst": "A short range monster. Three shots per burst.", "pistol-beretta": "Reliable sidearm with a fast draw.", "pistol-revolver-taurus": "Heavy hitting, slow to reload.",
    "pistol-glock": "Larger magazine, lighter per shot.", "pistol-cz75-enforcer": "A versatile pistol with great range and accuracy.", "shotgun-shorty": "A widespread shotgun. Downs in two shots up close.",
    "shotgun-remington-pump": "Pump-action shotgun with a tighter spread than the double barrel. Pumps a shell between shots; deadly up close.",
    "pistol-xcaliber": "Precision sidearm with huge stopping power. Slow between shots, so make the first one count.",
    "rifle-galil": "A silenced fully automatic rifle that kills from the shadows. Steady damage at mid range, a deep magazine.",
    "crossbow": "Silent. Two body shots to down, a headshot kills. Bolts that hit scenery can be picked up again.", "pistol-el-diablo": "Handgun that comes with a scope. Two body shots to down.",
    "machete": "Fast and deadly. Three hits to down a foe. Never breaks.", "rifle-milsniper": "A long range rifle with a powerful scope. Two body shots to down, a headshot kills.",
    "shotgun-baserri-over-under": "A bargain priced shotgun that downs enemies with two shots at close range.",
    "rifle-assault-firefly-ellie-player": "Military grade rifle with a high rate of fire. Five body shots to down.",
}
# stat bars (10 segments): RATE OF FIRE, RELOAD SPEED, DAMAGE, ACCURACY = GUN_STATS[] of t2r-ext.c (the 2013 stats the in-game details tab draws)
_ext = open(EXT_C, encoding="utf-8", errors="replace").read()
_blk = _ext[_ext.index("static const struct { const char *weapon; int rof, reload, dmg, acc; } GUN_STATS[]"):]
_blk = _blk[:_blk.index("};")]
STATS = {m.group(1): [int(x) for x in m.groups()[1:]] for m in re.finditer(r'\{"([a-z0-9-]+)", (\d+), (\d+), (\d+), (\d+)\}', _blk)}
STATS["rifle-assault-firefly-ellie-player"] = [int(x) for x in re.search(r'\{ASSAULT_ID, (\d+), (\d+), (\d+), (\d+)\}', _blk).groups()]   # same row of GUN_STATS
for _slot in weapons.values():
    for _w in _slot:
        _w["desc"] = DESC[_w["id"]]
        _w["stats"] = STATS.get(_w["id"])
        if _w["id"] not in ("machete", "pistol-xcaliber"): assert _w["stats"], _w["id"]   # melee has no bars; the hunting pistol is not in GUN_STATS (no bars drawn)
byid = {w["id"]: (slot, w) for slot, ws in weapons.items() for w in ws}
# ---- classes: the one source is CLASSES[] in t2r-ext.c, read by tools/classes_src.py ("<id>-supp" = the suppressed variant of <id>)
sys.path.insert(0, os.path.join(ROOT, "tools"))
import classes_src
classes = []
for c in classes_src.parse(EXT_C):
    slots = []
    for n in c["w"]:
        if not n: slots.append(None); continue
        sup = 0
        if n.endswith("-supp"): n, sup = n[:-5], 1
        slots.append({"id": n, "supp": sup})
    classes.append({"name": c["name"], "desc": c["desc"], "slots": dict(zip(("large", "small", "purch"), slots)),
                    "skills": [{"id": keys.index(k), "lv": lv} for k, lv in c["skills"]]})
assert len(classes) == 8, [c["name"] for c in classes]

def lp(slot, sel):
    if not sel: return 0
    w = byid[sel["id"]][1]
    return w["lp"] + (w["supp"] if sel["supp"] else 0)
for c in classes:
    c["lp"] = sum(lp(s, c["slots"][s]) for s in c["slots"]) + sum(skills[k["id"]]["cost"][k["lv"] - 1] for k in c["skills"])
    assert c["lp"] <= 13, (c["name"], c["lp"])
    for sel in c["slots"].values(): assert not sel or not sel["supp"] or byid[sel["id"]][1]["supp"], (c["name"], sel)
    print(c["name"], c["lp"], c["slots"], [(skills[k["id"]]["name"], k["lv"]) for k in c["skills"]])

# ---- clan names (tools/clan.py)
clan_src = open(os.path.join(ROOT, "tools", "clan.py"), encoding="utf-8").read()
missions = {int(i): {"name": n, "goals": [int(x) for x in g.split(",")], "pickable": p == "True"}
            for i, n, g, p in re.findall(r'^\s*(?:MISSIONS = \{)?(\d+): \("([^"]+)", "[^"]*", \(([\d, ]+)\), (True|False)\)', clan_src, re.M)}
boosters = {int(i): n for i, n in re.findall(r'(\d): "([A-Za-z ]+)"', re.search(r"BOOSTERS = \{(.*?)\}", clan_src, re.S).group(1))}
data = {"skills": skills, "weapons": weapons, "classes": classes, "missions": missions, "boosters": boosters, "lpMax": 13, "customSlots": 6, "skillRows": 4}
out = os.path.join(HERE, "..", "src", "gamedata.js")
open(out, "w", encoding="utf-8").write("// generated by scripts/gen-gamedata.py from the mod's sources - do not edit\nconst GAMEDATA = " + json.dumps(data, indent=1) + ";\n")
print("missions", len(missions), "boosters", len(boosters), "-> src/gamedata.js")
