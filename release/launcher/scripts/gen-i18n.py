"""Builds src/i18n/game-pl.json: the Polish text of the game data the launcher shows (skill / weapon / class / mission / booster names and descriptions),
taken from the mod's own Polish table tools/loc/pl/*.txt ("EN => PL" lines, {1} {2} placeholders) - the same strings the in-game GEAR UP shows.
Prints the strings of src/gamedata.js that have no Polish line yet (those must be added to src/i18n/pl.json by hand).  Run from release/launcher."""
import glob, json, os, re
HERE = os.path.dirname(os.path.abspath(__file__))
LOC = os.path.join(HERE, "..", "..", "..", "tools", "loc", "pl")
loc = {}
for f in sorted(glob.glob(os.path.join(LOC, "*.txt"))):
    for line in open(f, encoding="utf-8"):
        line = line.rstrip("\n")
        if not line or line.startswith("##") or " => " not in line:
            continue
        en, pl = line.split(" => ", 1)
        loc.setdefault(en, pl)
def norm(s):
    return s.replace("|gen:flashlight|", "the mark button").replace("|gen:jump|", "jump").replace("  ", " ").strip()
nloc = {norm(k): v for k, v in loc.items()}
g = open(os.path.join(HERE, "..", "src", "gamedata.js"), encoding="utf-8").read()
G = json.loads(g[g.index("= ") + 2: g.rindex(";")])
need = []
for s in G["skills"]:
    need += [s["name"]] + s["desc"]
for slot in G["weapons"].values():
    for w in slot:
        need += [w["name"], w["desc"]]
for c in G["classes"]:
    need += [c["name"], c["desc"]]
need += [m["name"] for m in G["missions"].values()] + list(G["boosters"].values())
out, missing = {}, []
for s in need:
    k = norm(s)
    if k in nloc:
        out[s] = re.sub(r"\{(\d)\}", r"{\1}", nloc[k])
    elif s.upper() in nloc:
        out[s] = nloc[s.upper()]
    else:
        missing.append(s)
# a few terms of the clan screens / GEAR UP the launcher reuses verbatim
for k in ("GEAR UP", "NOTHING", "Nothing", "No Small Firearm", "No Large Firearm", "No Purchasable", "RATE OF FIRE:", "RELOAD SPEED:", "DAMAGE:", "ACCURACY:", "EQUIPPED", "SELECT", "BACK", "CONFIRM",
          "WLF", "SERAPHITES", "HEALTHY: %d", "HUNGRY: %d", "SICK: %d", "NEEDED PER DAY:", "%d SURVIVORS", "WEEK %d: DAY %d", "RESET LOADOUT", "CUSTOM LOADOUT %d", "NOT ENOUGH POINTS",
          "Spend your loadout points elsewhere.", "QUIT", "OPTIONS", "LOADING"):
    if k in loc:
        out[k] = re.sub(r"\{(\d)\}", r"{\1}", loc[k])
ROMAN = ["", "I", "II", "III"]
for s in G["skills"]:                                   # "JACK OF ALL TRADES II" rows
    if s["name"] in out:
        for k in range(1, s["levels"] + 1):
            out["%s %s" % (s["name"], ROMAN[k])] = "%s %s" % (out[s["name"]], ROMAN[k])
for slot in G["weapons"].values():                      # "SUPPRESSED HUNTING RIFLE": the game's own line when it has one
    for w in slot:
        if w["supIcon"]:
            k = "SUPPRESSED " + w["name"]
            if k in loc: out[k] = loc[k]
os.makedirs(os.path.join(HERE, "..", "src", "i18n"), exist_ok=True)
json.dump(out, open(os.path.join(HERE, "..", "src", "i18n", "game-pl.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print(len(out), "game strings with Polish;", len(missing), "missing:")
for m in missing:
    print("  -", m)
