"""Kids are never fighters (tools/clan_kids.py).  Simulates many clan days for both factions (wins, losses, downs, executions, raids, attacks, sickness, hunger,
deaths, newcomers; story + A-Life + chronicle + saga + arcs + loot + perks + status + tickers) with seeded RNG, kids in every roster, English AND Polish, and asserts
  - no kid is named in a sentence that reads as combat, raid, patrol, danger-scavenging or weapon lore (clan_kids.combat_text),
  - no kid is named in a row of a combat kind (attack deaths, attack events, match / raid / haul / prep chronicle pools, match saga scenes),
  - no kid dies of anything but sickness, hunger or mercy (never "attack", "lost", "bite", "walkout", "suicide"),
  - no kid is a loot finder or a perk provider, has no "injured" status, no fighter's habit or keepsake, no combat tagline,
  - the detector works: with the rule switched off (a control run) the same simulation finds violations.
Run: python tools/tests/test_clan_kids.py"""
import os
import random
import re
import sqlite3
import sys
import tempfile

os.environ["T2R_CLAN_CHRONICLE"] = "1"
os.environ["T2R_CLAN_ALIFE"] = "1"
os.environ["T2R_CLAN_SAGA"] = "1"
os.environ["T2R_SAGA_STRICT"] = "1"
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import clan                      # noqa: E402
import clan_story as CS          # noqa: E402
import clan_kids as KD           # noqa: E402
import clan_chronicle as CH      # noqa: E402
import clan_alife as AL          # noqa: E402
import clan_saga as SG           # noqa: E402
import clan_perks as PK          # noqa: E402
import clan_status as ST         # noqa: E402
import clan_loot as LT           # noqa: E402

FAILS = []


def check(cond, what):
    print(("ok   " if cond else "FAIL ") + what)
    if not cond:
        FAILS.append(what)


MAPS = ["Train Station", "Hillside", "Overpass", "Hospital", "School", "Bookstore", "Forest", "Gas Station", "Shipyard", "Resort", "Houses", "Motel", "Downtown", "Lodge",
        "TV Station", "Hardware Store", "Jackson Suburbs", "Capitol Hill Shops", "Convention Center", "Seraphite Camp"]
WEAPONS = ["bow", "revolver", "shorty", "hunting", "semi", "burst", "pistol", "crossbow", "melee"]
COMBAT_SCENES = {"win", "loss", "down", "exec", "rev", "quiet", "haul", "prep"}              # the saga's match-day scenes (lid "sg/<scene>")
OK_KID_DEATHS = {"illness", "starved", "mercy"}


def sentences(text):
    return [s for s in re.split(r"(?<=[.!?])\s+", text.strip()) if s]


def named(text, name):
    return re.search(r"(?<!\w)" + re.escape(name) + r"(?!\w)", text) is not None


def pool_of(lid):
    """The combat tag of a stored row: (kind of the first template, True when its pool is a combat pool)."""
    if lid.startswith("ch/"):
        pools = [CH.REG[i][0] for i in lid[3:].split("+") if i in CH.REG]
        return any(p in KD.COMBAT_POOLS_CHRON for p in pools)
    if lid.startswith("al/"):
        pools = [AL.REG[i][0] for i in lid[3:].split("+") if i in AL.REG]
        return any(p in KD.COMBAT_POOLS_ALIFE for p in pools)
    if lid.startswith("sg/"):
        return lid[3:] in COMBAT_SCENES
    return False


def violations(row, kid_names, texts):
    """[(why, name, text)] of one stored row against the kids of the clan; texts = {"en": .., "pl": ..}."""
    out = []
    names = [n for n in kid_names if named(texts["en"], n)]
    for n in names:
        if row["kind"] in KD.COMBAT_KINDS or pool_of(row.get("lid") or ""):
            out.append(("combat row", n, texts["en"]))
    for lang, text in texts.items():
        if not text:
            continue
        for n in kid_names:
            if not named(text, n):
                continue
            for s in sentences(text):
                if named(s, n) and KD.combat_text(s, lang):
                    out.append(("combat sentence " + lang, n, s))
    return out


def simulate(seed, faction, policy, days=70, kids=4):
    """One whole clan run through the real rules (apply_match + on_day, all modules on).  Returns a dict of everything the checks need."""
    d = tempfile.mkdtemp()
    c = sqlite3.connect(os.path.join(d, "t.db"))
    rng = random.Random(seed * 7919 + faction)
    clan.rng = random.Random(seed)
    tid = "%024x" % (seed * 1000 + faction + 12345)
    clan.choose_side(c, tid, faction)
    CS.on_new_run(c, tid, faction)
    st = CS._load(c, tid)
    for p in st["people"][-2:]:                                  # kids from day 0 (more come with the newcomers)
        p["r"] = "kid"
    CS._save(c, tid, st)
    res = {"viol": [], "rows": 0, "kid_rows": 0, "kid_names": set(), "deaths": [], "kid_dead": 0, "days": 0, "finds_kid": 0, "status_kid_injured": 0, "tick_kid": 0, "texts": []}
    for i in range(1, days + 1):
        c0 = clan.load(c, tid)
        if c0["status"] != clan.ALIVE:
            break
        parts = policy(i, c0)
        counts = {1: rng.randrange(0, 14), 3: rng.randrange(0, 3)}
        new, r = clan.apply_match(c, tid, "m%d" % i, parts, counts=counts)
        if not r:
            continue
        win = rng.random() < 0.5
        r["match"] = {"map": rng.choice(MAPS), "kills": counts[1], "deaths": rng.randrange(0, 6) + (0 if win else 2), "downs": rng.choice([0, 0, 1, 2, 3, 4]), "win": win,
                      "execs": rng.choice([0, 0, 1, 2, 3]), "revives": rng.choice([0, 0, 1, 2]), "headshots": rng.randrange(0, 5), "weapon": rng.choice(WEAPONS),
                      "streak": rng.randrange(0, 6)}
        before = CS._load(c, tid)
        if i % 6 == 1 and before:                                # a kid arrives now and then (the roll of the newcomers is random, this keeps kids in every clan)
            before["people"].append(CS.new_person(random.Random(seed * 31 + i), before, role="kid", state="h", join_day=i))
            CS._save(c, tid, before)
            new = dict(new, healthy=new["healthy"] + 1)
            clan.save(c, tid, new)
        msgs = CS.on_day(c, tid, new, r)
        st = CS._load(c, tid)
        res["days"] += 1
        res["kid_names"] = {x["n"] for x in st["people"] if x["r"] == "kid"} | {x["n"] for x in st["dead"] if x["r"] == "kid"}     # (own check, independent of clan_kids)
        for m in msgs:
            res["rows"] += 1
            en = m["text"]
            pl = CS.render_msg(m.get("lid"), m.get("params"), "pl") or ""
            res["texts"].append(en)
            kn = res["kid_names"]
            if any(named(en, n) for n in kn):
                res["kid_rows"] += 1
            for v in violations(m, kn, {"en": en, "pl": pl}):
                res["viol"].append((seed, faction, i, m.get("lid"), m["kind"]) + v)
        # the supply perks: credit the day's goods, draw the uses; the credited member is never a kid
        try:
            PK.on_day(c, tid, new, r, {})
        except Exception as ex:                                  # noqa: BLE001
            res["viol"].append((seed, faction, i, "perks", "", "exception", repr(ex), ""))
        cs = (st.get("ch") or {})
        for cat in ("med", "ammo", "mat", "food", "water"):
            who = PK.credit_of(st, cat)
            if who and who["r"] == "kid":
                res["viol"].append((seed, faction, i, "perks", "", "kid provides " + cat, who["n"], ""))
        for e in (cs.get("log") or [])[-1:]:
            for f in e.get("finds") or []:
                if f.get("w") in res["kid_names"]:
                    res["finds_kid"] += 1
                    res["viol"].append((seed, faction, i, "loot", "", "kid finds loot on a raid", f["w"], ""))
        for ev in ((cs.get("stat") or {}).get("ev") or []):
            if ev["c"] == ST.INJURED and ev.get("r") == "kid":
                res["status_kid_injured"] += 1
                res["viol"].append((seed, faction, i, "status", "", "kid injured / light duty", ev["n"], ""))
        # the tickers (live lines, A-Life facts) in both languages
        for lang in ("en", "pl"):
            for slot in range(i * 3, i * 3 + 2):
                try:
                    for _id, t in CS.live_lines(c, tid, 8, lang, now=slot * CS.SLOT_S, save=False):
                        for n in res["kid_names"]:
                            if named(t, n) and any(KD.combat_text(s_, lang) for s_ in sentences(t) if named(s_, n)):
                                res["viol"].append((seed, faction, i, "ticker", "", "combat ticker " + lang, n, t))
                except Exception as ex:                          # noqa: BLE001
                    res["viol"].append((seed, faction, i, "ticker", "", "exception", repr(ex), ""))
        for p in st["people"]:
            if p["r"] == "kid":
                for lang in ("en", "pl"):
                    tg = CH.tagline(p, st["people"], "S" if faction == clan.SERAPHITES else "W", lang, st)
                    if KD.combat_text(tg, lang):
                        res["viol"].append((seed, faction, i, "tagline", "", "combat tagline " + lang, p["n"], tg))
                if SG.KD.combat_text(((cs.get("mem") or {}).get(str(p["i"])) or {}).get("poss") or "", "en"):
                    res["viol"].append((seed, faction, i, "saga", "", "combat keepsake", p["n"], ""))
        for dd in st["dead"]:
            if dd["r"] == "kid" and dd["i"] not in {x[0] for x in res["deaths"]}:
                res["deaths"].append((dd["i"], dd["c"]))
                res["kid_dead"] += 1
                if dd["c"] not in OK_KID_DEATHS:
                    res["viol"].append((seed, faction, i, "death", "", "kid death by " + str(dd["c"]), dd["n"], ""))
    return res


def rich(i, c0):
    return 4000


def poor(i, c0):
    return 400


def mixed(i, c0):
    return 400 if (i // 5) % 2 else 2500


def hard(i, c0):
    return 150 if (i // 3) % 2 else 1800


def sweep(seeds=3, days=60):
    tot = {"viol": [], "rows": 0, "kid_rows": 0, "kid_dead": 0, "days": 0}
    for fac in (clan.WLF, clan.SERAPHITES):
        for pol in (rich, poor, mixed, hard):
            for seed in range(seeds):
                r = simulate(seed, fac, pol, days)
                for k in tot:
                    tot[k] = tot[k] + r[k] if k != "viol" else tot[k] + r[k]
    return tot


# ------------------------------------------------------------------ unit rules
people = [{"i": 1, "n": "Mo", "g": "m", "r": "kid", "s": "h"}, {"i": 2, "n": "Al", "g": "m", "r": "guard", "s": "h"}, {"i": 3, "n": "Kit", "g": "n", "r": "elder", "s": "h"}]
check(not KD.can_fight(people[0]) and KD.can_fight(people[1]) and KD.can_fight(people[2]), "can_fight: kids no, grown people and elders yes (the adult rule of each module)")
check(KD.combat_text("{A} cleaned the rifle after {map}.") and KD.combat_text("{A} stand a night patrol") and KD.combat_text("{A} stoi na warcie.", "pl") and not KD.combat_text("{A} plays chess with {B}."),
      "combat_text reads combat in English and Polish and lets home life through")
check(not KD.kid_safe("{A} cleaned the rifle.", {"A": people[0]}) and KD.kid_safe("{A} cleaned the rifle.", {"A": people[1]}) and KD.kid_safe("{A} plays chess.", {"A": people[0]}),
      "kid_safe: a combat template is out only when it names a kid")
st0 = CS.new_state("u", clan.WLF)
st0["people"] = [dict(p, il="", **{"is": 0, "id": 0, "k": 0, "jd": 0, "gr": 0, "gl": 0, "l": "X"}) for p in people]
st0["morale"] = 50
bad = 0
for k in range(300):
    pk = CS._kill_pick(random.Random(k), st0, fight=True)
    bad += 1 if pk["r"] == "kid" else 0
check(bad == 0, "the death of the attack never picks a kid while grown people live")
check(all(CS._pick_illness(random.Random(k), st0, True, people[0]) != "infected_wound" for k in range(200)), "a kid never gets an infected (fight) wound")
check(PK._pick_bringer({"people": [dict(p, r=p["r"]) for p in people], "n": 1}, "ammo", 3)["r"] != "kid", "a kid is never the supply-perk provider")
check(LT.pick_member(random.Random(1), {"people": people}, LT.ITEMS[next(iter(LT.ITEMS))], {}, 1)[0] != "Mo", "a kid is never the finder of a raid")
check(CS.ticker_for(random.Random(5), dict(st0, people=st0["people"], dead=[]), st0["people"][0], set())[0] is not None, "ticker_for works for a kid")

# roster portrait follows the status card: a depressed member shows the depressed face
st1 = CS.new_state("u", clan.WLF)
st1["people"] = [dict(p, il="", **{"is": 0, "id": 0, "k": 0, "jd": 0, "gr": 0, "gl": 0, "l": "X"}) for p in people]
st1["day"] = 9
st1.setdefault("ch", {})["dep"] = {str(people[1]["i"]): {"n": ST.DEP_AT, "d": 9, "up": -1, "rec": False}}
_pid = CH._roster_portrait(st1, st1["people"][1], "W")
check(_pid.endswith("/depressed") or CH.fit_expr(int(_pid.split("/")[2]), "depressed") == _pid.split("/")[3], "roster portrait of a depressed member is /depressed, or the expression its head has instead (%s)" % _pid)
check(CH._roster_portrait(st1, st1["people"][2], "W").rsplit("/", 1)[1] in ("neutral", "happy", "scared"), "a healthy member keeps the morale rule")

# ------------------------------------------------------------------ the sweep
res = sweep()
print("rows %d, rows naming a kid %d, kid deaths %d, days %d" % (res["rows"], res["kid_rows"], res["kid_dead"], res["days"]))
for v in res["viol"][:25]:
    print("  VIOLATION", v)
check(res["rows"] > 2000 and res["kid_rows"] > 150, "the sweep is big enough and kids are in many rows (%d rows, %d naming a kid)" % (res["rows"], res["kid_rows"]))
check(res["kid_dead"] >= 3, "kids die in the sweep too (%d), of sickness, hunger or mercy only" % res["kid_dead"])
check(not res["viol"], "no kid in any combat sentence / row / death / loot / perk / status / ticker (%d violations)" % len(res["viol"]))

# ------------------------------------------------------------------ the control: the detector fires with the rule switched off
_orig = (KD.is_kid, KD.kid_safe)
KD.is_kid = lambda p: False
KD.kid_safe = lambda *a, **k: True
try:
    ctl = [simulate(s, f, mixed, 40) for f in (clan.WLF, clan.SERAPHITES) for s in range(2)]
finally:
    KD.is_kid, KD.kid_safe = _orig
nctl = sum(len(x["viol"]) for x in ctl)
check(nctl > 0, "control: with the kid rule off the same detector finds violations (%d)" % nctl)

print("\n%d failed" % len(FAILS) if FAILS else "\nall ok")
sys.exit(1 if FAILS else 0)
