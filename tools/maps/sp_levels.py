"""Look up TLOU2 single-player level sets (stock level-sets-*.json dumps in re/gamebin/dc1/level-sets)
to build PvP maps out of SP sections (re/maps/technical.md).

  python sp_levels.py find <substring>...        # set names containing all substrings (+ file)
  python sp_levels.py show <set>                 # one set: its levels / actors / nested sets
  python sp_levels.py leaves <set>...            # all levels the sets load (nested sets resolved),
                                                 # each tagged GEO / SCRIPT / NPC / CINE / AUDIO / FX / PART
  python sp_levels.py where <level>...           # which world-*.psarc holds pak68/<level>.pak (re/game-files.tsv)

Data root: re/gamebin next to this repo, or env T2R_GAMEBIN (a checkout that keeps re/gamebin
untracked: point T2R_GAMEBIN at that folder).
"""
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))


def _first(*cands):
    for c in cands:
        if c and os.path.exists(c):
            return c
    return cands[-1]


GAMEBIN = _first(os.environ.get("T2R_GAMEBIN"), os.path.join(ROOT, "re", "gamebin"),
                 r".\re\gamebin")
FILES_TSV = _first(os.environ.get("T2R_GAME_FILES"), os.path.join(ROOT, "re", "game-files.tsv"),
                   r".\re\game-files.tsv")

# level name patterns that must NOT go into a PvP set (SP logic / AI / cinematics). Order matters.
# (wat-explore-checkpoint / -b: the street geometry behind the Capitol shops, 55 / 13 ingame spawners = decor, particles, 4 trip-wire mines (parked by
#  the capitol-shops spec "park_spawners"): geometry, not a script level)
TAGS = [
    ("SCRIPT", r"(-script|scriptset|scripted|-tasks?$|-logic|(?<!wat-explore)-checkpoint(?!-low)|mission-|-encounter|-wave-manager)"),
    ("NPC", r"(^npc-|-npcs?\b|-enemies|-enemy|spawners|-infected-(?!wilds|house)|-buddy|-ambush|-combat-(?!cover))"),
    ("CINE", r"(^cin-|-cine|-igc|-ig-|cinematic|-cam-|-vox)"),
    ("AUDIO", r"(-audio|-amb$|-ambi\b|-music)"),
    ("FX", r"(-fx\b|-const-fx|texture-adjust|-render|-ibl|cubemaps|probes|shadow-blocker|^sky-)"),
    ("PART", r"(^part-|^sp-all$|interaction)"),
]


def tag(level):
    for t, rx in TAGS:
        if re.search(rx, level):
            return t
    return "GEO"


def load():
    sets = {}
    d = os.path.join(GAMEBIN, "dc1", "level-sets")
    for fn in sorted(os.listdir(d)):
        if not fn.endswith(".json") or not fn.startswith("level-sets"):
            continue
        for line in open(os.path.join(d, fn), encoding="utf-8"):
            line = line.strip()
            if not line:
                continue
            try:
                arr = json.loads(line)
            except ValueError:
                continue
            for e in arr:
                s = sets.setdefault(e["name"], {"file": fn, "levels": [], "actors": [], "sets": []})
                for k, dst in (("levels", "levels"), ("levels-pc", "levels"), ("actors", "actors"),
                               ("actors-pc", "actors"), ("level-sets", "sets"), ("level-sets-pc", "sets")):
                    for v in e.get(k, []):
                        if v not in s[dst]:
                            s[dst].append(v)
    return sets


def leaves(sets, names, seen=None, out=None, actors=None):
    seen = set() if seen is None else seen
    out = [] if out is None else out
    actors = [] if actors is None else actors
    for n in names:
        if n in seen:
            continue
        seen.add(n)
        s = sets.get(n)
        if not s:
            if n not in out:
                out.append(n)       # not a set: a level name (or a set we have no dump of)
            continue
        for lv in s["levels"]:
            if lv not in out:
                out.append(lv)
        for a in s["actors"]:
            if a not in actors:
                actors.append(a)
        leaves(sets, s["sets"], seen, out, actors)
    return out, actors


def where(levels):
    want = {f"pak68/{lv}.pak": lv for lv in levels}
    found = {}
    if os.path.exists(FILES_TSV):
        for line in open(FILES_TSV, encoding="utf-8", errors="replace"):
            p = line.rstrip("\n").split("\t")
            if len(p) >= 3 and p[1] in want:
                found.setdefault(want[p[1]], []).append((p[0], int(p[2])))
    return found


def main():
    if len(sys.argv) < 3:
        print(__doc__)
        return
    cmd, args = sys.argv[1], sys.argv[2:]
    sets = load()
    if cmd == "find":
        for n, s in sets.items():
            if all(a in n for a in args):
                print(f"{n}\t{s['file']}\t{len(s['levels'])} levels, {len(s['sets'])} sets")
    elif cmd == "show":
        for n in args:
            s = sets.get(n)
            print(n, json.dumps(s, indent=1) if s else "(no such set)")
    elif cmd == "leaves":
        lv, ac = leaves(sets, args)
        loc = where(lv)
        for x in lv:
            arc = ",".join(f"{a}:{sz // 1024}K" for a, sz in loc.get(x, [])) or "-"
            print(f"{tag(x):6} {x}\t{arc}")
        if ac:
            print("actors:", " ".join(ac))
    elif cmd == "where":
        for lv, hits in where(args).items():
            print(lv, hits)
    else:
        print(__doc__)


if __name__ == "__main__":
    main()
