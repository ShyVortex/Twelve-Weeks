"""Offline round trip of the loot group through the SceneEditor names:
editor_prepare.ops_for writes loot-spot-N[-shared] masters + random-spot-N-i-<item> markers; editor_import.classify / diff_item_spots must read
them back unchanged, take group / shared from the names (the editor's Loot group / Shared check boxes rename the master), keep room / fill /
respawn / dy, drop dy of a moved spot, and keep the loot scatter when the pak predates the loot group (no loot-spot names).
Run: python tools/tests/test_loot_editor_roundtrip.py"""
import copy
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
MAPS = os.path.join(os.path.dirname(HERE), "maps")
sys.path.insert(0, MAPS)
import editor_import as EI  # noqa: E402
import editor_prepare as EP  # noqa: E402
import itemspots as IS  # noqa: E402

KEY = "jackson-market"
FAILS = []


def check(cond, what):
    print(("ok   " if cond else "FAIL ") + what)
    if not cond:
        FAILS.append(what)


def run(spawners, js):
    df = EI.Diff()
    out = EI.diff_item_spots(df, EI.classify(spawners), KEY, js)
    return out, df


def main():
    js = json.load(open(os.path.join(EI.DATA, f"{KEY}-itemspots.json")))
    spots = [IS.norm_spot(s) for s in js["spots"]]
    loot = [i for i, s in enumerate(spots) if s.get("group") == "loot"]
    check(len(loot) > 0, f"{len(loot)} loot spots in data/{KEY}-itemspots.json")
    ops, _, _, _ = EP.ops_for(KEY)
    sp = [dict(r) for r in ops["add_random"] if not r["name"].startswith("random-satchel-")]
    masters = [r for r in sp if EI.RX_SPOT_M.match(r["name"])]
    check(sum(r["name"].startswith("loot-spot-") for r in masters) == len(loot), "prepare names every loot spot loot-spot-N[-shared]")
    check(sum(r["name"].endswith("-shared") for r in masters) == sum(bool(spots[i].get("shared")) for i in loot), "shared spots carry -shared")

    out, df = run(copy.deepcopy(sp), js)
    check(out is None, "unchanged pak -> no change" + ("" if out is None else f": {df.lines}"))

    # flip spot A to shared / unique, move spot B by 0.5 m, take spot C out of the loot group
    a, b, c = loot[0], loot[1], loot[2]
    sp2 = copy.deepcopy(sp)
    by = {r["name"]: r for r in sp2}
    def master(i):
        return next(r for r in sp2 if EI.RX_SPOT_M.match(r["name"]) and int(EI.RX_SPOT_M.match(r["name"]).group(1)) == i + 1)
    ma, mb, mc = master(a), master(b), master(c)
    was_shared = ma["name"].endswith("-shared")
    ma["name"] = f"loot-spot-{a + 1}" + ("" if was_shared else "-shared")
    for r in sp2:                                    # the spot and its item markers move together
        m = EI.RX_SPOT_I.match(r["name"])
        if r is mb or (m and int(m.group(1)) == b + 1):
            r["pos"] = [r["pos"][0] + 0.5, r["pos"][1], r["pos"][2]]
    mc["name"] = f"random-spot-{c + 1}"
    del by
    out, df = run(sp2, js)
    check(out is not None and len(out) == len(spots), "edited pak -> a full spot list")
    if out:
        check(bool(out[a].get("shared")) != was_shared and out[a].get("group") == "loot", "spot A: shared flipped by its name, still loot")
        check(out[a].get("room") == spots[a].get("room") and out[a].get("fill") == spots[a].get("fill"), "spot A keeps room / fill")
        check(out[b].get("group") == "loot" and "dy" not in out[b] and out[b].get("resp") == spots[b].get("resp"), "spot B moved: still loot, dy dropped, respawn kept")
        check(out[c].get("group") is None and out[c].get("shared") is None and out[c].get("fill") is None, "spot C: left the loot group (plain item spawner)")

    # a stale pak: the loot spots under plain names would have been read as plain spawners; with NO spawners at the loot places they must be kept
    keep = loot[0]                                   # one spawner left at a loot place, under the old plain name (a pak from before the loot group)
    sp3 = []
    for r in sp:
        mm, mi = EI.RX_SPOT_M.match(r["name"]), EI.RX_SPOT_I.match(r["name"])
        num = int((mm or mi).group(1)) - 1 if (mm or mi) else -1
        if num in loot and num != keep:
            continue
        sp3.append(dict(r, name=f"random-spot-{keep + 1}") if mm and num == keep else r)
    out, df = run(sp3, js)
    check(out is None or sum(s.get("group") == "loot" for s in out) == len(loot), "pak without loot names keeps every loot spot (and their attributes)")
    check(any("predates the loot group" in n for n in df.info), "stale pak noted")
    check(not any(t.startswith("- removed") for t in df.lines.get("itemspots", [])), "stale pak: nothing read as removed")
    print("PASS" if not FAILS else f"FAIL ({len(FAILS)})")
    return 1 if FAILS else 0


if __name__ == "__main__":
    sys.exit(main())
