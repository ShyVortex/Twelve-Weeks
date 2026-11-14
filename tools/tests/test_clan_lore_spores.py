"""Clan lore: the spores are canon (breathing them without a mask = infection = certain turning, no cure, no recovery), and the new story arcs
(spore, stranger, caravan, pendant, birthday) have real cards in EN and PL.   Run: python tools/tests/test_clan_lore_spores.py"""
import os
import random
import re
import sys

os.environ["T2R_CLAN_SAGA"] = "0"
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import clan                      # noqa: E402
import clan_story as CS          # noqa: E402
import clan_story_pl as PLN      # noqa: E402
import clan_chronicle as CH      # noqa: E402
import clan_arcs as AR           # noqa: E402
import clan_arcs_text as AT      # noqa: E402
import clan_story_spores as SP   # noqa: E402
import clan_kids as KD           # noqa: E402

FAILS = []


def check(cond, what):
    print(("ok   " if cond else "FAIL ") + what)
    if not cond:
        FAILS.append(what)


NEW_ARCS = ("spore", "stranger", "caravan", "pendant", "birthday")
SPORE_NODES = ("sp0", "hide", "confess", "signs", "turn", "mercy", "walk", "remembered", "after")
RECOVER = re.compile(r"\b(recover|recovered|recovers|cured|cure[sd]? (him|her|them)|on (his|her) feet|pulled through|will live|gets better|got better|survived the spores)\b", re.I)
RECOVER_PL = re.compile(r"(wyzdrowia|wyleczy|wraca do zdrowia|stoi znów na nogach|będzie żyć|poczuł się lepiej|poczuła się lepiej|przeżył[a]? zarodniki)", re.I)

# --- 1. every new arc node has EN + PL text, the spore arc has its cards and no way back
for k in NEW_ARCS:
    check(k in AR.ARCS and AR.FIRST[k] in AR.ARCS[k] and k in AR.START_W, "arc %s is registered (nodes, first node, start weight)" % k)
    for n in AR.ARCS[k]:
        t = AT.TEXT.get("%s.%s" % (k, n))
        check(bool(t) and all(x and x.strip() for x in t) and len(t) == 4, "arc text %s.%s has headline + vignette in EN and PL" % (k, n))
        if t:
            check(len(t[2]) > 120 and len(t[3]) > 120, "arc text %s.%s is a real vignette (EN %d / PL %d chars)" % (k, n, len(t[2]), len(t[3])))
check(set(SPORE_NODES) <= set(AR.ARCS["spore"]), "the spore arc has exposure, hide / confess, signs, three endings, a remembered branch and the aftermath")
for n in ("turn", "mercy", "walk"):
    check(AR.ARCS["spore"][n]["fx"] is not None and AR.ARCS["spore"][n]["nxt"], "spore ending %s removes the person (fx) and leads to the grief card" % n)
reach = {"sp0"}
for _ in range(10):
    for n in list(reach):
        reach |= {t for _c, t in AR.ARCS["spore"][n]["nxt"]}
check(not ({"recover", "alive", "pulled", "returns", "treat", "hold", "relent", "pardon"} & reach) and reach == set(SPORE_NODES), "no spore card leads to a recovery: every path ends in the end or the aftermath")
for n in AR.ARCS["spore"]:
    en, pl = AT.TEXT["spore." + n][2], AT.TEXT["spore." + n][3]
    check(not RECOVER.search(en) and not RECOVER_PL.search(pl), "spore.%s: no recovery wording" % n)
check(len(AR.ARCS["sick"]) and not any("spores" in str(AT.TEXT.get("sick." + n, "")) for n in AR.ARCS["sick"]), "the generic sick arc says nothing about spores")

# --- 2. the spore lines: parity, no recovery, no cure
for pool, rows in SP.POOLS.items():
    check(len(rows) >= 5, "spore pool %s has %d lines" % (pool, len(rows)))
    bad = [en for sc, en, pl in rows if RECOVER.search(en) or RECOVER_PL.search(pl) or re.search(r"\b(a|the) (filter|medicine|cure) (will|can|would) (save|heal|fix|help)", en)]
    check(not bad, "spore pool %s: no recovery / cure wording (%s)" % (pool, bad[:1]))
check(PLN.REG and all(("%s/%s" % (p, PLN.line_crc(en))) in PLN.REG for p, sc, en, pl in SP.ROWS), "every spore line is in the language registry (EN + PL)")
check(len(SP.ONSET_EN) == len(SP.ONSET_PL) and SP.ONSET_EN[0][1] in [t for _s, t in CS.LD.ONSET["spores"]], "the extra onset lines are in the spores onset pool, EN and PL index-parallel")
check(len(CS.LD.ONSET["spores"]) == len(CS.PLN.PD.ONSET["spores"]), "spores onset: EN and PL pools have the same length")
check("miracle" in CS.D.ILLNESS["spores"][2] and "filter" not in CS.D.ILLNESS["spores"][2], "the cure of the spores is a miracle: nothing in the shop")

# --- 3. a spore carrier never recovers in the roster: the game says "nobody is sick any more" for days; the spore-sick turn / leave, they never stand up
recovered_spores = turned = runs = 0
for seed in range(60):
    for fac in (clan.WLF, clan.SERAPHITES):
        rng = random.Random(seed)
        st = CS.new_state("sp%d" % seed, fac)
        CS._populate(rng, st, 12, 2, 2, 0)
        for p in st["people"]:
            if p["s"] == "s":
                p["il"] = "spores"
        carriers = {p["i"] for p in st["people"] if p["il"] == "spores"}
        for day in range(1, 8):
            size = len(st["people"])
            nu = sum(1 for p in st["people"] if p["s"] == "u")
            newc = {"day": day, "healthy": size - nu, "hungry": nu, "sick": 0, "status": clan.ALIVE}      # the game: nobody is sick any more
            r = {"day": day, "supplies": 12, "needed": 6, "died": 0, "gained": 0, "evk": 0, "evl": 0, "evt": 0, "evg": 0}
            msgs = CS.story_day(st, rng, newc, r)
            now = {p["i"]: p for p in st["people"]}
            for i in carriers:
                if i in now and now[i]["s"] != "s":
                    recovered_spores += 1
            gone = {i for i in carriers if i not in now}
            turned += len(gone)
            carriers -= gone
            check_msgs = [m for m in msgs if m["kind"] == "recovery" and m.get("names") and any(now.get(i, {}).get("n") in m["names"] and i in carriers for i in carriers)]
            if check_msgs:
                recovered_spores += 1
        runs += 1
check(recovered_spores == 0, "over %d seeded runs no spore carrier ever recovered (%d turned or left)" % (runs, turned))
check(turned > 0, "the spore carriers do leave the roster in the end")

# --- 4. the death / grief / worse lines through the real story: causes and kinds
kinds_seen = set()
for seed in range(120):
    rng = random.Random(1000 + seed)
    st = CS.new_state("sx%d" % seed, clan.WLF if seed % 2 else clan.SERAPHITES)
    CS._populate(rng, st, 12, 2, 2, 0)
    for p in st["people"]:
        if p["s"] == "s":
            p["il"] = "spores"
            p["id"] = 0
    for day in range(1, 14):
        size = len(st["people"])
        nu = sum(1 for p in st["people"] if p["s"] == "u")
        ns = sum(1 for p in st["people"] if p["s"] == "s")
        died = 1 if day in (3, 6, 9) else 0
        newc = {"day": day, "healthy": size - nu - ns - died, "hungry": nu, "sick": ns, "status": clan.ALIVE}
        r = {"day": day, "supplies": 3 if day % 2 else 12, "needed": 6, "died": died, "gained": 0, "evk": 0, "evl": 0, "evt": 0, "evg": 0}
        for m in CS.story_day(st, rng, newc, r):
            kinds_seen.add(m["kind"])
            if m["kind"] in ("death_turned", "grief_turned", "worse", "medicine"):
                if re.search(r"[{}|]", m["text"]):
                    check(False, "unfilled placeholder in %s: %s" % (m["kind"], m["text"]))
                pl = CS.render_msg(m["lid"], m["params"], "pl")
                if m["kind"] in ("death_turned", "grief_turned"):
                    check(bool(pl) and not re.search(r"[{}|]", pl or "") and pl != m["text"], "PL render of %s is filled and differs from EN" % m["kind"]) if seed < 2 else None
check("death_turned" in kinds_seen, "spore deaths come out as death_turned rows")
check("grief_turned" in kinds_seen, "the spore dead are grieved as grief_turned rows")
check("recovery" not in kinds_seen or True, "(recovery rows may exist for the other sicknesses)")

# --- 5. the arcs through the chronicle: the spore story is told in order, ends with the person gone, EN + PL render, a mask halves the risk
import clan_chronicle_dump as DUMP  # noqa: E402
spore_runs = full = gone_ok = 0
other = {k: 0 for k in NEW_ARCS}
for seed in range(1, 41):
    fk = "W" if seed % 2 else "S"
    rng = random.Random(seed)
    st = CS.new_state("arc%d" % seed, clan.WLF if fk == "W" else clan.SERAPHITES)
    CS._populate(rng, st, 13, 2, 1, 0)
    for p in st["people"]:
        if p["s"] == "s":
            p["il"] = "spores"
            p["id"] = 0
    seen = {}
    for day in range(1, 16):
        size = len(st["people"])
        nu = sum(1 for p in st["people"] if p["s"] == "u")
        ns = sum(1 for p in st["people"] if p["s"] == "s")
        newc = {"day": day, "healthy": size - nu - ns, "hungry": nu, "sick": ns, "status": clan.ALIVE}
        r = {"day": day, "supplies": 9, "needed": 7, "died": 0, "gained": 0, "evk": 0, "evl": 0, "evt": 0, "evg": 0, "parts": 300}
        CS.story_day(st, rng, newc, r)
        match = {"map": "Hospital", "kills": 5, "deaths": 2, "downs": 1, "win": True, "execs": 0, "revives": 1}
        st["day"] = day
        rows = CH.day_rows(st, newc, r, match, rng=random.Random(seed * 100 + day))
        for row in rows:
            if row["lid"].startswith("arc/"):
                k, n = row["lid"][4:].split(".")
                seen.setdefault(row["params"]["a"], []).append((k, n, row))
                en, pl = row["text"], CH.CS.render_msg(row["lid"], row["params"], "pl")
                if re.search(r"[{}|]", en) or not pl or re.search(r"[{}|]", pl) or "None" in en + pl:
                    check(False, "arc row %s renders clean in EN and PL: %r / %r" % (row["lid"], en[:80], (pl or "")[:80]))
    for aid, steps in seen.items():
        k = steps[0][0]
        other[k] = other.get(k, 0) + 1
        if k != "spore":
            continue
        spore_runs += 1
        nodes = [n for _k, n, _r in steps]
        if nodes[0] == "sp0" and nodes[-1] == "after" and any(n in ("turn", "mercy", "walk", "remembered") for n in nodes):
            full += 1
        name = steps[0][2]["params"]["p"]["A"][0]
        gone_ok += int(all(p["n"] != name for p in st["people"]) and any(d["n"] == name and d["c"] == "turned" for d in st["dead"]))
check(spore_runs > 0, "the spore arc starts for a member sick with the spores (%d of 40 runs)" % spore_runs)
check(full == gone_ok and gone_ok > 0, "every finished spore story ends with the person off the roster and a 'turned' record (%d of %d)" % (gone_ok, full))
print("INFO  arcs seen over 40 runs:", {k: v for k, v in other.items() if v})

# --- 6. a gas mask on the shelf makes the spores rarer; kids are never sent where the spores are
st0 = CS.new_state("mask", clan.WLF)
st1 = CS.new_state("mask", clan.WLF)
st1["ch"] = {"log": [{"d": 1, "finds": [{"k": "gasmask", "n": 1}]}]}
rng = random.Random(5)
n0 = sum(1 for _ in range(4000) if CS._pick_illness(rng, st0, True) == "spores")
n1 = sum(1 for _ in range(4000) if CS._pick_illness(rng, st1, True) == "spores")
check(CS.has_mask(st1) and not CS.has_mask(st0) and n1 < n0 * 0.5, "a found gas mask makes the spores rarer (%d -> %d of 4000)" % (n0, n1))
kid = CS.new_person(random.Random(1), st0, role="kid")
check(not any(CS._pick_illness(rng, st0, True, kid) == "spores" for _ in range(2000)), "a kid is never drawn the spores")
check(all("spores" not in str(v) for k, v in AT.TEXT.items() if k.startswith("sick.")), "the generic fever arc never mentions the spores")

# --- 7. the journal keeps its structure: the spore story and the spore death are cards, the grief / worsening lines are one-liners between them
import clan_story as CSX  # noqa: E402
rows = []
i = 0
for day, (kind, style, txt) in enumerate([
        ("chron", "arc_spore", "DAY 1: CARLOS BREATHED THE SPORES IN THE CELLAR. " + AT.TEXT["spore.sp0"][2].replace("{A}", "Carlos").replace("{B}", "Hannah").replace("{A_his}", "his")),
        ("worse", "", "Carlos is worse. Grey dust on the pillow, red eyes, a cough that doesn't stop. We all know there is no coming back from this."),
        ("death_turned", "", "Carlos told Hannah plainly, at the fire, that it was the spores, and asked for one more night. Hannah gave it. Nobody slept, and nobody called it weakness."),
        ("grief_turned", "", "Hannah keeps glancing at the door Carlos went through. Hannah knows what happened. Knowing doesn't help."),
        ("chron", "arc_spore", "DAY 5: HANNAH DID NOT SPEAK AT SUPPER. " + AT.TEXT["spore.after"][2].replace("{A}", "Carlos").replace("{B}", "Hannah"))], 1):
    i += 1
    rows.append({"id": i, "day": day, "week": 1, "kind": kind, "style": style, "text": txt, "names": ["Carlos", "Hannah"], "mood": "grieving"})
sr = {m["id"]: m for m in CSX.story_rows(list(reversed(rows)))}
check(sr[1]["card"] and sr[3]["card"] and sr[5]["card"], "the spore cards and the spore death are story cards")
check(not sr[2]["card"] and not sr[4]["card"], "the worsening and the grief lines of the spores are one-liners between the cards")
jr = CSX.journal(list(reversed(list(sr.values()))))
check(len(jr) == 3 and all(e["card"]["card"] for e in jr) and any(e["lines"] for e in jr), "the journal model is cards with lines between them (%d cards)" % len(jr))

print("FAILS:", len(FAILS))
sys.exit(1 if FAILS else 0)
