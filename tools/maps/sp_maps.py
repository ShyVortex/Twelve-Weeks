"""PvP maps from single-player sections: data checks, spawn seeding, spawner pak builds, cover props.
Specs: tools/maps/sp_maps.json. Background: re/maps/technical.md, candidates: re/maps/candidates.md.

  python sp_maps.py check [key...]           # every level known to the game + the mod's pak68.txt
  python sp_maps.py extract <key> [--game D]  # READ-ONLY: copy the map's level paks (+ seed_levels) out of
                                              # the stock game psarcs into re/maps/paks/<key>/ and dump their
                                              # spawners to re/maps/seeds/<key>.json (SceneEditor reader)
  python sp_maps.py probe <name> <level>...   # extract + dump any levels (read only), bounds per level
  python sp_maps.py seed <key>                # seeds -> tools/maps/data/<key>-spawns.json (player, 4+4 intros,
                                              # 13 respawns, 6 boxes; placeholders until placed in game)
  python sp_maps.py pak <key>                 # tools/features/levels/<pak>-ingame.pak from the spawns + props
                                              # (no spawns file yet: a copy of the Hospital pak = placeholder)
  python sp_maps.py props <key> <HH:MM:SS from> <HH:MM:SS to> <prop> [<prop>...]
                                              # F8 marks in that window -> cover props (one prop name per mark,
                                              # the last name repeats), then rebuilds the pak
  python sp_maps.py props-clear <key>         # drop all props of a map
  python sp_maps.py player <key>              # pre-intro player / camera spawners -> T0-1 (after levels.py apply)
  python sp_maps.py list-props                # cover prop catalog (actor97 paks with collision)

Spawn placement in game afterwards = the existing flow (tools/spawns/levels.py apply|intro|set|add|nudge|view
<key> ...): levels.py works on tools/features/levels/to1-pvp-<key>-ingame.pak for any key.
"""
import json
import math
import os
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.dirname(HERE)
ROOT = os.path.dirname(TOOLS)
sys.path.insert(0, TOOLS)
sys.path.insert(0, os.path.join(TOOLS, "spawns"))
import sp_levels  # noqa: E402

SPEC = os.path.join(HERE, "sp_maps.json")
DATA = os.path.join(HERE, "data")
LEVELS = os.path.join(TOOLS, "features", "levels")
TEMPLATE = os.path.join(LEVELS, "to1-pvp-hospital-ingame.pak")   # 8 intros, 13 respawns, 6 boxes (hand-placed)
SCENE = os.path.join(TOOLS, "spawns")
MAKE_PAK = os.path.join(HERE, "make_map_pak.ps1")
DUMP = os.path.join(HERE, "dump_spawners.ps1")
MODFS = [os.path.join(ROOT, "re", "modfs"), r".\re\modfs"]

# Cover props: actor97 paks of the stock game built to block / be climbed on (No Return arena blockers and SP
# cover pieces). size = rough footprint (m) for the placement list; all carry collision in the game.
COVER_PROPS = {
    "drag-dumpster-blue-blocker": ("world-rogue", "dumpster, chest high, NoR arena blocker (used by School's gates)"),
    "drag-dumpster-brown-blocker": ("world-rogue", "dumpster, brown"),
    "drag-dumpster-yellow-blocker": ("world-rogue", "dumpster, yellow"),
    "drag-dumpster-noclimb": ("world-rogue", "dumpster that can't be climbed (lane blocker)"),
    "crate-shrinkwrap-1o5x1o5-a-blocker": ("world-rogue", "1.5 x 1.5 m shrink-wrapped pallet crate, chest high"),
    "san-wood-crate-1x1-blocker-a": ("world-rogue", "1 m wooden crate, waist high"),
    "san-wood-crate-1x1-blocker-stacked-a": ("world-rogue", "stacked 1 m crates, head high (full cover)"),
    "pallet-forklift-a-blocker": ("world-rogue", "forklift pallet stack"),
    "compressor-tank-set-a-tank-b-blocker": ("world-rogue", "compressor tank, waist high"),
    "gas-garage-welding-machine-blocker": ("world-rogue", "welding cart, waist high"),
    "cardboard-box-b-pile-b-blocker": ("world-rogue", "cardboard box pile (soft look, solid)"),
    "blocker-bookstore-shelf-a": ("world-rogue", "shelf unit, head high (indoor lane splitter)"),
    "blocker-bookstore-shelf-b": ("world-rogue", "shelf unit b"),
    "blocker-wood-planks-a": ("world-rogue", "boarded planks (door / window blocker)"),
    "blocker-wood-planks-b": ("world-rogue", "boarded planks b"),
    "res-neighborhood-window-boards": ("sp-common", "SP window boards 2.39 x 1.64 x 0.11 m (origin at the left end, front = +z; Capitol Hill grocery window uses it scaled)"),
    "rooftop-column-broken-blocker-ao": ("world-rogue", "broken concrete column"),
    "rl-cache-crate-military": ("world-rogue", "military cache crate, knee-waist high"),
    "station-wagon-a": ("world-rogue", "station wagon car (vehicle cover)"),
    "barbed-wire": ("world-rogue", "barbed wire coil (blocks movement, not bullets)"),
    "flo-fence-boat-blocker": ("world-flooded-city", "boat fence panel (School's gate blocker)"),
    "jersey-barrier-concrete-broken-a-mossy": ("sp-common", "concrete jersey barrier, waist high"),
    "ind-wood-crate-2x1-a": ("sp-common", "2 x 1 m wooden crate"),
    "sle-logging-crate-1m": ("sp-common", "1 m logging crate"),
    "drag-dumpster": ("sp-common", "dumpster (SP version, draggable in SP - may move)"),
    "layout-cover-200x400x100": ("sp-common", "grey blockout cover box 2x4x1 m (dev look, last resort)"),
    # invisible collision (no mesh; collision_walls.py lays them as walls, re/maps/collision-editing.md)
    "invisible-block-050x300x200": ("sp-common", "INVISIBLE wall block 0.5 x 3 tall x 2 m, origin = bottom corner"),
    "invisible-block-050x150x100": ("sp-common", "INVISIBLE block 0.5 x 1.5 tall x 1 m, origin = bottom corner"),
    "invis-collision": ("sp-common", "INVISIBLE panel 3 x 3 x 0.1 m, centred on its origin"),
}


def spec_all():
    return json.load(open(SPEC, encoding="utf-8"))["maps"]


def spec(key):
    for m in spec_all():
        if m["key"] == key:
            return m
    sys.exit(f"no map '{key}' in {SPEC}")


def save_spec_props(key, props):
    d = json.load(open(SPEC, encoding="utf-8"))
    for m in d["maps"]:
        if m["key"] == key:
            m["props"] = props
    with open(SPEC, "w", encoding="utf-8", newline="\n") as f:
        json.dump(d, f, indent=1)
        f.write("\n")


def modfs_file(rel):
    for r in MODFS:
        p = os.path.join(r, rel)
        if os.path.exists(p):
            return p
    return None


# ------------------------------------------------------------------ check
def check(keys):
    maps = [m for m in spec_all() if not keys or m["key"] in keys]
    reg = modfs_file("pak68.txt")
    known = set()
    if reg:
        for line in open(reg, encoding="latin1"):
            if line.startswith("level-name "):
                known.add(line.split(None, 1)[1].strip())
    bad = 0
    for m in maps:
        miss_files, miss_reg = [], []
        lv = [x for x in m["levels"] if x != m["pak"]]
        found = sp_levels.where(lv)
        for x in lv:
            if x not in found:
                miss_files.append(x)
            if known and x not in known:
                miss_reg.append(x)
        tags = {x: sp_levels.tag(x) for x in lv}
        risky = [x for x, t in tags.items() if t in ("SCRIPT", "NPC", "CINE")]
        full = sp_levels.where([x + s for x in lv for s in ("", "-phys", "-ingame")])
        size = sum(h[0][1] for h in full.values()) // (1 << 20)          # base + phys + ingame paks
        auto = sum(1 for p in m.get("props", []) if p.get("auto"))
        state = "OK" if not (miss_files or miss_reg or risky) else "CHECK"
        print(f"{m['key']:18s} {state:5s} {len(lv):2d} levels {size:4d} MB (base+phys+ingame)  props {len(m.get('props', []))} "
              f"({auto} boundary)  build={m['build']}")
        for x in miss_files:
            print(f"    no pak68/{x}.pak in re/game-files.tsv")
        for x in miss_reg:
            print(f"    {x} not registered in the mod's pak68.txt")
        for x in risky:
            print(f"    {x}: tagged {tags[x]} (script/NPC/cine level in an art set?)")
        if not (miss_files or miss_reg or risky):
            continue
        bad += 1
    if not reg:
        print("(no re/modfs/pak68.txt: registry not checked)")
    return bad


# ------------------------------------------------------------------ extract / seed
def game_dir(argv):
    if "--game" in argv:
        return argv[argv.index("--game") + 1]
    return os.environ.get("T2_GAME", "C:/Games/The Last of Us Part II Remastered")


def extract(key, argv, want=None):
    """READ-ONLY on the game install: copies pak68/<level>-ingame.pak (spawners live there) of the map's art
    levels and seed levels out of the psarcs that hold them. want = explicit level list (probe)."""
    import dsar_list
    if want is None:
        m = spec(key)
        want = [x for x in m["levels"] if x != m["pak"]] + list(m.get("seed_levels", []))
    found = sp_levels.where([x + "-ingame" for x in want])
    out = os.path.join(ROOT, "re", "maps", "paks", key)
    os.makedirs(out, exist_ok=True)
    main = os.path.join(game_dir(argv), "build", "pc", "main")
    by_arc = {}
    for lv, hits in found.items():
        by_arc.setdefault(hits[0][0], []).append(lv)
    for arc, lvs in sorted(by_arc.items()):
        d, ent, bs, bsz = dsar_list.open_files(os.path.join(main, arc))
        for lv in lvs:
            dst = os.path.join(out, lv + ".pak")
            if not os.path.exists(dst):
                open(dst, "wb").write(dsar_list.extract(d, ent, bs, bsz, f"pak68/{lv}.pak"))
            print(f"{arc}: {lv} ({os.path.getsize(dst) // 1024} KB)")
    seeds = []
    for fn in sorted(os.listdir(out)):
        if not fn.endswith(".pak"):
            continue
        js = os.path.join(out, fn[:-4] + ".json")
        r = subprocess.run(["pwsh", "-NoProfile", "-File", DUMP, "-Pak", os.path.join(out, fn), "-Out", js])
        if r.returncode or not os.path.exists(js):
            print(f"  {fn}: SceneEditor could not read it")
            continue
        for s in json.load(open(js, encoding="utf-8-sig")) or []:
            s["level"] = fn[:-4]
            seeds.append(s)
    sd = os.path.join(ROOT, "re", "maps", "seeds")
    os.makedirs(sd, exist_ok=True)
    json.dump(seeds, open(os.path.join(sd, f"{key}.json"), "w"), indent=0)
    print(f"{key}: {len(seeds)} spawners from {len(found)} paks -> re/maps/seeds/{key}.json")


def probe_report(key):
    """spawner bounds per level of re/maps/seeds/<key>.json (x / z / y ranges, count)"""
    pts = json.load(open(os.path.join(ROOT, "re", "maps", "seeds", f"{key}.json")))
    by = {}
    for p in pts:
        by.setdefault(p["level"], []).append(p)
    for lv, L in sorted(by.items()):
        xs, ys, zs = ([p["pos"][i] for p in L] for i in range(3))
        print(f"{lv:52s} n={len(L):4d} x {min(xs):7.1f}..{max(xs):7.1f} z {min(zs):7.1f}..{max(zs):7.1f} "
              f"y {min(ys):6.1f}..{max(ys):6.1f}")


def _yaw_quat(yaw):
    return [0.0, math.sin(yaw / 2), 0.0, math.cos(yaw / 2)]


def _d(a, b):
    return math.dist(a["pos"], b["pos"])


def _fps(points, n, start, min_d=0.0):
    """farthest point sampling: n points, spread out, beginning next to `start`"""
    out, pool = [], list(points)
    if not pool:
        return out
    first = min(pool, key=lambda p: math.dist(p["pos"], start))
    out.append(first)
    pool.remove(first)
    while pool and len(out) < n:
        best = max(pool, key=lambda p: min(_d(p, q) for q in out))
        if min(_d(best, q) for q in out) < min_d:
            break
        out.append(best)
        pool.remove(best)
    return out


STAND = ("npc", "spawn", "start", "player", "wave", "enemy", "checkpoint", "infected", "human", "militia", "scar",
         "wlf", "buddy", "goto", "cover", "patrol", "post")
LOOT = ("pickup", "loot", "ammo", "item", "supply", "chest", "cache", "lockbox", "workbench")
# SceneEditor process types (T2RProcessTypes) of standing characters / loot
STAND_TYPES = {"Infected", "Dog", "SimpleNpc", "Dina", "Jesse", "Joel", "Lev", "Manny", "Mel", "Owen", "Tommy", "Yara",
               "Jerry", "Nora", "Alice", "Pirate", "position"}
NOT_STAND = ("camera", "cam-", "perch", "look", "vox", "lens", "sky")   # spots in the air / on roofs
NOT_GROUND = {"ParticleSpawner", "ParticleMultiSpawner", "ParticleSpawnerWater", "ProcessDynLight", "NdLightObject", "SimpleVoxActor",
              "FlockingBird", "FlockingFish", "SimpleBird", "AnimalPerchProcess", "BackgroundLadder"}
LOOT_TYPES = {"ItemPickup", "UpgradeManualPickup", "JournalTreasure", "MeleeWeapon", "ProcessWeapon"}


def seed(key):
    """Placeholder spawns from the dumped SP / No Return spawners: standing spots (player starts, NPC / wave
    spawners) for spawns, loot spots for boxes. Team bases = the player start and the stand spot farthest
    from it. All of it is meant to be replaced by in-game placement (re/maps/candidates.md checklists)."""
    sd = os.path.join(ROOT, "re", "maps", "seeds", f"{key}.json")
    pts = json.load(open(sd))
    m = spec(key)
    if m.get("bounds"):                      # [xmin, xmax, zmin, zmax]: the play space (e.g. the NoR arena)
        x0, x1, z0, z1 = m["bounds"]
        pts = [p for p in pts if x0 <= p["pos"][0] <= x1 and z0 <= p["pos"][2] <= z1]
    walls = [p["pos"] for p in m.get("props", []) if p.get("auto")]
    if walls:                                # boundary blockers (sp_bounds.py): keep spawns / boxes 3 m away
        pts = [p for p in pts if all(math.dist(p["pos"], w) > 3.0 for w in walls)]
    stand = [p for p in pts if (p.get("type") in STAND_TYPES or p.get("type") in (None, "None") and
                                any(w in (p["name"] + " " + (p.get("art") or "")).lower() for w in STAND))
             and not any(w in p["name"].lower() for w in LOOT + NOT_STAND)]
    loot = [p for p in pts if p.get("type") in LOOT_TYPES or
            any(w in (p["name"] + " " + (p.get("art") or "")).lower() for w in LOOT)]
    if len({tuple(round(v) for v in p["pos"]) for p in stand}) < 40:   # few NPC / player spots (e.g. the lodge): add gameplay spawners near the floor
        rest = [p for p in pts if p.get("type") not in NOT_GROUND and not any(w in p["name"].lower() for w in NOT_STAND)]
        if rest:
            ys = sorted(p["pos"][1] for p in rest)
            floor = ys[len(ys) // 2]
            rest = [p for p in rest if p["pos"][1] <= floor + 1.5]
        print(f"{key}: only {len(stand)} standing-spot seeds - adding {len(rest)} other spawners at floor height (CHECK IN GAME)")
        stand = stand + [p for p in rest if p not in stand]
    if len(stand) < 8:
        sys.exit(f"{key}: only {len(stand)} usable seeds - place spawns in game instead")
    starts = [p for p in stand if "player" in p["name"].lower() or "start" in p["name"].lower()]
    base0 = starts[0] if starts else stand[0]
    base1 = max(stand, key=lambda p: _d(p, base0))
    if m.get("intro_hints"):                 # [[x, z], [x, z]]: team areas picked from the level layout
        near = lambda h: min(stand, key=lambda p: math.hypot(p["pos"][0] - h[0], p["pos"][2] - h[1]))
        base0, base1 = near(m["intro_hints"][0]), near(m["intro_hints"][1])
    centre = [sum(p["pos"][i] for p in stand) / len(stand) for i in range(3)]

    def facing(p):
        return _yaw_quat(math.atan2(centre[0] - p["pos"][0], centre[2] - p["pos"][2]))

    def team(base):
        near = [p for p in sorted(stand, key=lambda p: _d(p, base)) if _d(p, base) <= 15.0 and abs(p["pos"][1] - base["pos"][1]) < 1.5]
        pick = []
        for p in near:                       # the team starts together: within 10 m of the base, same floor
            if all(_d(p, q) >= 1.0 for q in pick):
                pick.append(p)
            if len(pick) == 4:
                break
        while len(pick) < 4:                       # fewer seeds than 4 near the base: side steps of 0.9 m
            k = len(pick)
            pick.append({"pos": [base["pos"][0] + 0.9 * k, base["pos"][1], base["pos"][2]]})
        return [{"pos": p["pos"], "quat": facing(p)} for p in pick]

    t0, t1 = team(base0), team(base1)
    intro_pts = t0 + t1                     # respawns / boxes keep >= 12 / 10 m from every intro spawn
    far = lambda p, r: all(math.dist(p["pos"], q["pos"]) > r for q in intro_pts)
    resp = _fps([p for p in stand if far(p, 12.0)], 13, centre, 5.0)
    resp = [{"pos": p["pos"], "quat": facing(p)} for p in resp]
    while len(resp) < 13:                          # the pak has 13 respawn slots: repeat the spread ones
        resp.append(dict(resp[len(resp) % max(1, len(resp))]))
    loot = [p for p in loot if far(p, 10.0) and all(math.dist(p["pos"], q["pos"]) > 10.0 for q in resp)]
    boxes = _fps(loot, 6, centre, 8.0) if len(loot) >= 6 else []
    if len(boxes) < 6:                       # top up from standing spots away from intros, respawns and boxes
        extra = [p for p in stand if far(p, 8.0) and all(math.dist(p["pos"], q["pos"]) > 5.0 for q in resp + boxes)]
        boxes += _fps(extra, 6 - len(boxes), centre, 5.0)
    boxes = [{"pos": p["pos"], "quat": [0.0, 0.0, 0.0, 1.0]} for p in boxes]
    out = {"_note": "PLACEHOLDER spawns seeded from SP/NoR spawners (sp_maps.py seed) - replace in game",
           "player": t0[0], "intro0": t0, "intro1": t1, "respawns": resp, "boxes": boxes}
    os.makedirs(DATA, exist_ok=True)
    json.dump(out, open(os.path.join(DATA, f"{key}-spawns.json"), "w"), indent=1)
    print(f"{key}: base0 {base0['name']} ({base0.get('level')}) base1 {base1['name']} {_d(base0, base1):.0f} m apart; "
          f"{len(resp)} respawns, {len(boxes)} boxes -> tools/maps/data/{key}-spawns.json")


# ------------------------------------------------------------------ pak / props
def pak(key, out=None):
    """out: write there instead of tools/features/levels (scratch builds: editor_import round trip tests)"""
    m = spec(key)
    dst = out or os.path.join(LEVELS, m["pak"] + "-ingame.pak")
    sp = os.path.join(DATA, f"{key}-spawns.json")
    if not os.path.exists(sp) and not m.get("props") and not m.get("prefabs"):
        if os.path.exists(dst):
            print(f"{key}: {os.path.basename(dst)} kept (no spawns file / props)")
            return
        shutil.copyfile(TEMPLATE, dst)
        print(f"{key}: {os.path.basename(dst)} = copy of the Hospital pak (PLACEHOLDER positions)")
        return
    js = os.path.join(DATA, f"{key}-pak.json") if not out else out + ".json"
    body = json.load(open(sp)) if os.path.exists(sp) else {}
    body["props"] = m.get("props", [])
    gp = os.path.join(DATA, f"{key}-respawns-gen.json")          # generated respawns (respawn_fill.py): after the hand-placed ones, to1-spawn-point-<n_user+1..>
    if body.get("respawns") is not None and os.path.exists(gp):
        gen = [{"pos": g["pos"], "quat": g["quat"]} for g in json.load(open(gp)).get("respawns", [])]
        print(f"{key}: {len(body['respawns'])} user respawns + {len(gen)} generated ({os.path.basename(gp)})")
        body["respawns"] = body["respawns"] + gen
    if m.get("prefabs"):                       # placed vehicle presets: actor spawners + their vault / cover records (vehicle_presets.py, re/maps/vehicle-prefabs.md)
        import vehicle_presets as VP
        ex = VP.expand_map(m)
        body["props"] = body["props"] + ex["props"]
        body["featuredb"] = ex["featuredb"]
    import scaled_props                        # a prop with Scale != 1: its baked copy (the game ignores spawner Scale)
    import openings                            # data/fixes/openings-<key>.json: extra FEATURE_DB edges (a window vault)
    body["props"] = scaled_props.map_props(body["props"])[0] if m.get("bake_scaled") else body["props"]
    fx = openings.featuredb(key)
    if fx:
        base = body.setdefault("featuredb", {"edges": [], "posts": [], "outlines": []})
        n0 = len(base["edges"])
        for e in fx["edges"]:
            e = dict(e)
            e["prev"] = e["prev"] if e["prev"] == 65535 else e["prev"] + n0
            e["next"] = e["next"] if e["next"] == 65535 else e["next"] + n0
            base["edges"].append(e)
        base["posts"] += fx["posts"]
        base["outlines"] += fx["outlines"]
    json.dump(body, open(js, "w"), indent=1)
    src = dst if os.path.exists(dst) and not os.path.exists(sp) else TEMPLATE
    subprocess.run(["pwsh", "-NoProfile", "-File", MAKE_PAK, "-Template", os.path.abspath(src),
                    "-Spec", os.path.abspath(js), "-Out", os.path.abspath(dst)], check=True)


def props(key, t0, t1, names):
    import levels as lv
    marks = [k for k in lv.read_marks(t0, t1) if not k["box"]]
    if not marks:
        sys.exit("no F8 marks in that window")
    m = spec(key)
    cur = list(m.get("props", []))
    for i, k in enumerate(marks):
        art = names[min(i, len(names) - 1)]
        if art not in COVER_PROPS:
            print(f"  note: {art} is not in the cover catalog (list-props) - make sure actor97/{art}.pak exists")
        cur.append({"art": art, "pos": list(k["pos"]), "quat": list(k["quat"])})
        print(f"  prop {len(cur)}: {art} at {k['pos'][0]:.2f} {k['pos'][1]:.2f} {k['pos'][2]:.2f}")
    save_spec_props(key, cur)
    pak(key)


def player(key):
    """The pre-intro 'player' / 'camera' spawners onto team 0's intro 1 (levels.py apply doesn't move them)."""
    import levels as lv
    m = spec(key)
    short = m["pak"][len("to1-pvp-"):]
    import struct
    by = {s["name"]: s for s in lv.spawners(short)}
    t = by["to1-t0-intro-spawn-point-1"]
    path = lv.pak_path(short)
    b = bytearray(open(path, "rb").read())
    n = 0
    for name in ("player", "camera"):        # they usually share one transform: patch every record with it
        old_p, old_q = struct.pack("<3f", *by[name]["pos"]), struct.pack("<4f", *by[name]["quat"])
        i = b.find(old_p)
        while i >= 0:
            if b[i + 16:i + 32] == old_q:
                struct.pack_into("<3f", b, i, *t["pos"])
                struct.pack_into("<4f", b, i + 16, *t["quat"])
                n += 1
            i = b.find(old_p, i + 1)
    open(path, "wb").write(b)
    after = {s["name"]: s for s in lv.spawners(short)}
    for name in ("player", "camera"):
        assert max(abs(a - c) for a, c in zip(after[name]["pos"], t["pos"])) < 1e-3, f"{name} not moved"
    print(f"{key}: player + camera -> T0-1 {t['pos']} ({n} transforms)")


def main():
    a = sys.argv[1:]
    if not a:
        print(__doc__)
        return
    if a[0] == "check":
        sys.exit(1 if check(a[1:]) else 0)
    elif a[0] == "extract":
        extract(a[1], a)
    elif a[0] == "probe":              # probe <name> <level>...: extract + dump any levels, then bounds per level
        extract(a[1], [], [x for x in a[2:] if not x.startswith("--")])
        probe_report(a[1])
    elif a[0] == "seed":
        seed(a[1])
    elif a[0] == "pak":
        for k in (a[1:] or [m["key"] for m in spec_all() if m["build"]]):
            pak(k)
    elif a[0] == "props":
        props(a[1], a[2], a[3], a[4:] or ["crate-shrinkwrap-1o5x1o5-a-blocker"])
    elif a[0] == "player":
        player(a[1])
    elif a[0] == "props-clear":
        save_spec_props(a[1], [])
        pak(a[1])
    elif a[0] == "list-props":
        for n, (arc, d) in COVER_PROPS.items():
            print(f"{n:40s} {arc:20s} {d}")
    else:
        print(__doc__)


if __name__ == "__main__":
    main()
