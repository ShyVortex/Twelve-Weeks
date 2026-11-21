"""Clan portraits: faction lock, faction tags, no face churn for members who already wore their faction's head, match stats faces,
pictures in sync (game source / pool lists / launcher copy), no warped head shipped.   Run: python tools/tests/test_clan_portraits.py"""
import hashlib
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.dirname(HERE)
ROOT = os.path.dirname(TOOLS)
sys.path.insert(0, TOOLS)
import clan_portrait_pool as PP      # noqa: E402
import clan_portraits as CP          # noqa: E402
import clan_chronicle as CH          # noqa: E402
import clan_ingame as CI             # noqa: E402

FAILS = []


def check(cond, what):
    print(("ok   " if cond else "FAIL ") + what)
    if not cond:
        FAILS.append(what)


FAC = {r[0]: r[2] for r in PP.POOL}
ROLES = ["kid", "elder", "medic", "cook", "guard", "scout", "scavenger", "mechanic", "gardener", "radio", ""]
NAMES = ["Noor", "Jose", "Ann", "Bram", "Selah", "Emrys", "Teodor", "Anika", "Rowan", "Una", "Matthias", "Kayla", "Ethan", "Damon"] + ["P%d" % k for k in range(60)]


# 1. every row's faction tag agrees with its outfit family: WLF = militia / stadium looks, Seraphite = scar looks, the rest (Jackson, festival,
#    Rattlers, Rattler prisoners, Firefly, Duster) = N, never in a clan
def outfit_faction(look):
    return "W" if look.startswith(("militia-", "stadium-")) else "S" if look.startswith("scar-") else "N"


bad = [(r[0], r[1], r[2]) for r in PP.POOL if r[2] != outfit_faction(r[1])]
check(not bad, "faction tag matches the outfit for all %d pool rows %s" % (len(PP.POOL), bad[:5]))

# 2. faction lock: a pick is always of the clan's faction (or no head at all), for every role / sex / name
leak = []
for fk in "WS":
    for sx in "mf":
        for role in ROLES:
            for n in NAMES:
                for used in ((), tuple(m for m in FAC if FAC[m] == fk)[:6]):
                    m = CP.pick(n, role, sx, fk, used)
                    if m is not None and FAC[m] != fk:
                        leak.append((fk, sx, role, n, m))
check(not leak, "no member of a W / S clan gets a head of another faction %s" % leak[:4])
check(FAC.get(CP.pick("Noor", "medic", "f", "S")) == "S", "the reported case: Noor, medic of a Seraphite clan, wears a Seraphite head (was the Jackson beanie, 165)")
check(all(CP.pick(n, r, "m", "W") is not None for n in NAMES[:20] for r in ROLES), "every WLF member gets a head")
check(all(CP.pick(n, r, sx, "S") is not None for n in NAMES[:20] for r in ROLES if r != "kid" for sx in "mf"), "every grown Seraphite member gets a head")
skid = {sx: {CP.pick(n, "kid", sx, "S") for n in NAMES} for sx in "mf"}
check(all(None not in v and len(v) >= 2 and all(m in PP.RENDERED and FAC[m] == "S" for m in v) for v in skid.values()),
      "Seraphite kids: boys and girls both get a rendered Seraphite head, more than one face each (%s)" % {k: sorted(v, key=str) for k, v in skid.items()})

# 3. no churn: a member whose old pick was already of the clan's faction keeps that exact head; only the neutral-head members move
kept = moved = 0
churn = []
for fk in "WS":
    for sx in "mf":
        for role in ROLES:
            for n in NAMES:
                old = CP._pick(n, role, sx, fk, (), CP._legacy)
                new = CP.pick(n, role, sx, fk)
                if old is not None and FAC[old] == fk:
                    kept += 1
                    if new != old:
                        churn.append((fk, sx, role, n, old, new))
                elif old is not None:
                    moved += 1
check(not churn and kept > 200 and moved > 20, "same-faction members keep their head (%d kept, %d moved off a neutral head) %s" % (kept, moved, churn[:3]))

# 4. a whole clan (dedup path): every face of the roster and of the dead is of the clan's faction, and no head repeats while the pool has free ones
for fk in "WS":
    ppl = [{"i": k, "n": NAMES[k], "g": "mf"[k % 2], "r": ROLES[k % 10] if ROLES[k % 10] != "kid" else "guard", "s": "h"} for k in range(14)]
    ids = [CH.portrait_id(p, fk, members=ppl).split("/") for p in ppl]
    check(all(FAC.get(int(a[2])) == fk and a[0] == fk for a in ids), "clan %s: all 14 faces are %s heads" % (fk, fk))
    check(len({a[2] for a in ids}) == len(ids), "clan %s: 14 members, 14 different heads" % fk)

# 5. MATCH STATS faces: team 0 WLF, team 1 Seraphite, never a neutral head; the pool has heads with every face the list shows
pool = CI.stats_head_pool()
check(sum(1 for _, _, f in pool if f == "W") >= 20 and sum(1 for _, _, f in pool if f == "S") >= 20, "match stats pool: %d WLF + %d Seraphite heads with %s" %
      (sum(1 for _, _, f in pool if f == "W"), sum(1 for _, _, f in pool if f == "S"), "/".join(CI.MATCH_EXPR)))
rows = [("tok%d" % k, k % 2) for k in range(24)]
hd = CI.stats_heads(rows)
check(len(hd) == 24 and all(FAC[hd[t]] == ("S" if team else "W") for t, team in rows), "match stats: 24 players, each wears a head of their own team's faction")
check(len(set(hd.values())) == 24, "match stats: no two players share a head")
check(CP.expr_for(min(PP.EXPR), "shock") in PP.EXPR[min(PP.EXPR)], "an expression a head lacks falls back to one it has")

# 6. pictures: pool lists, game source and launcher copy agree (sync_portraits.py --check), and the warped scar-male-01 renders are gone
r = subprocess.run([sys.executable, os.path.join(TOOLS, "models", "portrait_cast", "sync_portraits.py"), "--check"], capture_output=True, text=True)
check(r.returncode == 0, "pool lists + launcher copy in sync with re/clan-portraits/img (%s)" % r.stdout.strip().splitlines()[0] if r.stdout.strip() else r.stderr[-200:])
WARPED = {"0a8624815f1fcdfba713d80a68d396cb", "7caf138e4a82e0f9152e06ca6d11be2a"}       # scar-male-01 neutral / happy (joel-skel index bug)
img = os.path.join(ROOT, "re", "clan-portraits", "img")
md = {hashlib.md5(open(os.path.join(img, f), "rb").read()).hexdigest() for f in os.listdir(img) if f.startswith("scar-male-01_")}
check(not (md & WARPED) and len(md) >= 7, "scar-male-01: no warped render shipped, %d faces" % len(md))

print("\n%d failed" % len(FAILS) if FAILS else "\nall ok")
sys.exit(1 if FAILS else 0)
