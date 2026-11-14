"""Displayed stats must equal what the game does (stats audit, re/stats-consistency-1019.md P2 / P6).
 - rate-of-fire bar of every gun (GUN_STATS in tools/ext/t2r-ext.c, and the launcher's gamedata.js) = one formula of the gun's real
   sustained interval (ROF_IV), and ROF_IV equals the real tables (WEAPON_STATS iv[0], dc_data_patches);
 - the picker's "Starts with N rounds" = loaded magazine + SPAWN_AMMO reserve (spawn_start_rounds).
Run: python tools/tests/test_stat_display.py   (plain python, no game files)."""
import json
import math
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
FAILS = []


def check(c, what):
    print(("ok   " if c else "FAIL ") + what)
    if not c:
        FAILS.append(what)


def read(*p):
    return open(os.path.join(ROOT, *p), encoding="utf-8", errors="replace").read()


ext = read("tools", "ext", "t2r-ext.c")
dc = read("tools", "features", "dc_data_patches.py")
gd = read("release", "launcher", "src", "gamedata.js")
G = json.loads(gd[gd.index("= ") + 2: gd.rindex(";")])


def rof_bar(t):   # the documented formula (comment above GUN_STATS)
    return max(1, min(10, int(math.floor(10 - 2.5 * math.log2(t / 0.1) + 0.5))))


IDS = {"ASSAULT_ID": "rifle-assault-firefly-ellie-player", "EXPBOW_ID": "bow-explosive", "FLAME_ID": "flamethrower"}


def wid(tok):
    tok = tok.strip()
    return IDS[tok] if tok in IDS else tok.strip('"')


def block(start):
    i = ext.index(start)
    return ext[i: ext.index("};", i)]


WS_HEAD = "static const struct { const char *weapon; uint32_t def; int burst; int mag[3]; float iv[3]"
gs = {wid(m.group(1)): [int(x) for x in m.groups()[1:]]
      for m in re.finditer(r'\{([A-Za-z_"0-9-]+), (\d+), (\d+), (\d+), (\d+)\}',
                           block("static const struct { const char *weapon; int rof, reload, dmg, acc; } GUN_STATS[]"))}
iv = {wid(m.group(1)): float(m.group(2))
      for m in re.finditer(r'\{([A-Za-z_"0-9-]+), ([0-9.]+)f\}', block("static const struct { const char *weapon; float t; } ROF_IV[]"))}
check(len(gs) >= 20, "GUN_STATS parsed (%d guns)" % len(gs))
check(set(gs) == set(iv), "every GUN_STATS gun has a real interval in ROF_IV and vice versa: %s" % sorted(set(gs) ^ set(iv)))
for g in sorted(gs):
    check(gs[g][0] == rof_bar(iv[g]), "%s: ROF bar %d == formula(%.4f s) = %d" % (g, gs[g][0], iv[g], rof_bar(iv[g])))

# same interval -> same bar (the P2 complaint: Crossbow 2 vs Double Barrel 1 at the same .9 s)
check(gs["crossbow"][0] == gs["shotgun-baserri-over-under"][0], "crossbow and double barrel (both .9 s) show the same ROF bar")

# ROF_IV vs the real tables: WEAPON_STATS interval of level 0 (burst guns: the gap after the burst)
ws = {}
for m in re.finditer(r'^\s*\{"([a-z0-9-]+)", (?:0x[0-9a-f]+|0), (\d), \{[^}]*\}, \{([^}]*)\}', block(WS_HEAD), re.M):
    first = m.group(3).split(",")[0].strip().rstrip("f")
    ws[m.group(1)] = (int(m.group(2)), float(first))
GAP = {"pistol-glock": 0.48, "rifle-burst": float(re.search(r"BURST_ROUNDS, BURST_GAP = 3, ([0-9.]+)", dc).group(1))}
for g, (burst, t0) in ws.items():
    if g not in iv or not t0:
        continue
    t = (2 * t0 + GAP[g]) / 3 if g in GAP else t0
    check(abs(iv[g] - t) < 0.002, "%s: ROF_IV %.4f == WEAPON_STATS interval %.4f%s" % (g, iv[g], t, " (burst gap applied)" if g in GAP else ""))
# guns whose interval is not in WEAPON_STATS: the def tables of dc_data_patches
DEFTAB = dc[dc.index('"rifle-vepr":                 ("variable-rifle"'):]
DEFTAB = DEFTAB[:DEFTAB.index("\n}")]
for m in re.finditer(r'^\s*"([a-z0-9-]+)":\s*\("[^"]+",\s*([0-9.]+),', DEFTAB, re.M):
    g, t = m.group(1), float(m.group(2))
    if g in iv and (g not in ws or not ws[g][1]):
        check(abs(iv[g] - t) < 0.002, "%s: ROF_IV %.4f == dc_data_patches interval %.2f" % (g, iv[g], t))
for name, g in (("GALIL_INTERVAL", "rifle-galil"), ("EXPBOW_INTERVAL", "bow-explosive")):
    m = re.search(r"^%s = ([0-9.]+)" % name, dc, re.M)
    check(bool(m) and abs(iv[g] - float(m.group(1))) < 0.002, "%s: ROF_IV == %s" % (g, name))
for name, g in (("DIABLO_STATS", "pistol-el-diablo"), ("ASSAULT_STATS", "rifle-assault-firefly-ellie-player")):
    m = re.search(r"^%s = \(([0-9.]+)," % name, dc, re.M)
    check(bool(m) and abs(iv[g] - float(m.group(1))) < 0.002, "%s: ROF_IV == %s[0]" % (g, name))
check(iv["rifle-frontier"] == 1.10 and "FR_CYC[3] = {1.10f, 0.95f, 0.80f}" in ext, "frontier: ROF_IV 1.10 = the lever cycle base (FR_CYC, rechamber rate since fix-frgate)")
check(iv["rifle-milsniper"] == iv["rifle-remington-bolt"] == 0.75 and 'T2R_MILSNIPER_SEMI", "0") == "1"' in dc,
      "military sniper: bolt cycle like the hunting rifle (.75 s) while T2R_MILSNIPER_SEMI is off")

# the launcher shows the same bars
for slot in G["weapons"].values():
    for w in slot:
        if w["id"] in gs:
            check(w["stats"] == gs[w["id"]], "launcher gamedata stats of %s == GUN_STATS %s (regenerate with gen-gamedata.py)" % (w["id"], gs[w["id"]]))

# ---- starting ammo: shown = loaded magazine + SPAWN_AMMO reserve
spawn = {}
for m in re.finditer(r'\{(?:0x[0-9a-f]+ULL), "(ammo-[a-z0-9-]+)", (\d+), (\d+)(?:, ([A-Za-z_"0-9-]+))?\},?[ \t]*(?://[ \t]*([a-z0-9-]+))?',
                     block("static const struct { uint64_t gun; const char *ammo; int reserve, per_level; const char *name; } SPAWN_AMMO[]")):
    name = m.group(4) or m.group(5)       # hashed rows carry their gun in the trailing comment
    if name:
        spawn[wid(name)] = int(m.group(2))
mags = {wid(m.group(1)): int(m.group(2)) for m in re.finditer(r'\{([A-Za-z_"0-9-]+), (\d+)\}', block("static const struct { const char *weapon; int mag; } SPAWN_MAG[]"))}
real_mag = {"rifle-assault-firefly-ellie-player": int(re.search(r"^ASSAULT_STATS = \([0-9.]+, (\d+)", dc, re.M).group(1)),
            "rifle-milsniper": int(re.search(r"^MILSNIPER_STATS = \([^,]+, (\d+)", dc, re.M).group(1))}
for g, mg in real_mag.items():
    check(mags.get(g) == mg, "%s: SPAWN_MAG %s == the def's magazine %d" % (g, mags.get(g), mg))
check("spawn_start_rounds(*(const char **)(row + 0x10), start)" in ext, "purchasable picker prints spawn_start_rounds(), not the raw row field")
# what the spawn grants (loaded mag + SPAWN_AMMO reserve): AR 20 loaded no reserve, Mil. Sniper 5, DB 2+2, Explosive Bow 1+2, Flamethrower 30
exp = {"rifle-assault-firefly-ellie-player": 20, "rifle-milsniper": 5, "shotgun-baserri-over-under": 4, "bow-explosive": 3, "flamethrower": 30}
for g, n in exp.items():
    check(g in mags and g in spawn and mags[g] + spawn[g] == n, "%s: shown start = mag %s + reserve %s = %d" % (g, mags.get(g), spawn.get(g), n))

print("\n%d failure(s)" % len(FAILS))
sys.exit(1 if FAILS else 0)
