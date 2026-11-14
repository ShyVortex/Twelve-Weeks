"""Strip single-player COLLECTIBLES from the SP level paks a ported map loads (MP has no Artifacts / Notes / Cards), plus the
spawners a map spec lists in "park_spawners" (e.g. the glass + wheels actor of a vehicle a level edit removed), plus the gameplay
spawners an LOD level (<base>-low / -mid) duplicates from its loaded base level (lod_twins: doubled breakable windows;
T2R_KEEP_LOD_SPAWNERS=1 = keep them).

The ported maps load stock SP art levels; each level's pak68/<level>-ingame.pak carries the level's gameplay spawners, among
them the collectibles (trading cards `col-tc-*`, artifacts `col-art-*`, coins, journal / note / log pages, `interact-loc-*`
location notes, the SP skill-pill pickups ...).  Picking one up adds it to the SP collection (backpack "Artifacts" tab).
Seen in a test log: Capitol Hill grocery, locker cab-short-locker-shelf-b-r (-43.0 -6.5 -284.5) held trading card col-tc-wat-4
(-42.9 -7.4 -284.2) and the player auto-collected it -> new Artifacts tab.

Offline, CPU only (SceneEditor reader / writer DLL, like tools/spawns/*.ps1; no game, no GPU tool):
  python collectibles.py list  <map key>...     # fetch the -ingame paks, list every collectible spawner (level, name, type, pos)
  python collectibles.py build <map key>...     # write <cache>/out/<key>/<level>-ingame.pak with them parked at y=-3000 (in-place byte patch)
  python collectibles.py names                  # every distinct spawner name / type per map (to refine COLLECT)
"Removal" is a byte patch of the spawner record position (the SceneEditor writer is lossy). The edited pak keeps the stock level name and ships in the staged pak68/ (shadows the original), exactly like level_edit.py edits.
"""
import json
import os
import re
import struct
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "part1"))
import level_edit  # noqa: E402

DUMP = os.path.join(HERE, "dump_spawners.ps1")
PARK = (0.0, -3000.0, 0.0)          # far below every level (the kill floor of a fall is ~ -200): the collectible is out of reach
WORK = os.path.join(level_edit.CACHE, "ingame")

# (regex on the spawner name, allowed process types or None = any, label).  Evidence:
#  col-tc-* / coll-*   ConversationPiece, trading card / note (coll-san-streets-slave-note = Train Station) (col-tc-wat-4 = the Capitol grocery locker card)
#  col-*               other `col-` collectibles (artifact / coin / safe / ... variants)
#  interact-loc-*      ConversationPiece, location note ("interact-loc-wat-wlf-rules")
#  player-upgrade-*    ItemPickup pills / supplement bottles = SP skill upgrade pickups (workbench-style SP progression)
COLLECT = [
    (r"^coll?-", None, "collectible (col-* / coll-*)"),
    (r"^(interact-loc|interact-note|note-|journal-|artifact|coin-|trading-card|trinket|safe-combo|safe-code)", None, "note / journal / artifact"),
    (r"^item-pickup-player-upgrade", None, "SP skill-upgrade pickup (pills)"),
    # throwable pickups (no bottles / bricks in the SP maps; art =bottle-collection= / =brick-collection=)
    (r"^item-pickup-(bottle|brick)", ("ItemPickup",), "throwable pickup (bottle / brick)"),
    # item-pickup-parts-* (crafting / weapon-upgrade PARTS) are deliberately NOT listed (crafting parts and normal pickups stay)
    (r"(^|-)(training-manual|manual-pickup|gun-part|gunpart|gun-upgrade-pickup|workbench-pickup)", None, "SP upgrade pickup"),
    # the SP workbench's interaction trigger (no crafting / weapon-upgrade bench in MP); the bench PROP is removed by tools/maps/workbench.py
    (r"workbench", ("ConversationPiece",), "SP workbench interaction (invisible-workbench)"),
]


def classify(s):
    n = s["name"].lower()
    for pat, types, label in COLLECT:
        if re.search(pat, n) and (types is None or s["type"] in types):
            return label
    return None


def levels(key):
    return level_edit.map_levels(key)


def fetch_dump(key):
    """-> [(level, pak path, [spawner dicts])]"""
    src = os.path.join(WORK, "src")
    js = os.path.join(WORK, "json")
    os.makedirs(js, exist_ok=True)
    out = []
    import dsar_list
    import sp_levels
    where = sp_levels.where([lv + "-ingame" for lv in levels(key)])
    arcs = {}
    for lv, hits in where.items():
        arcs.setdefault(hits[0][0], []).append(lv)
    os.makedirs(src, exist_ok=True)
    for arc, lvs in sorted(arcs.items()):                       # READ-ONLY on the install
        need = [lv for lv in lvs if not os.path.exists(os.path.join(src, lv + ".pak"))]
        if need:
            d, ent, bs, bsz = dsar_list.open_files(os.path.join(level_edit.GAME, "build", "pc", "main", arc))
            for lv in need:
                open(os.path.join(src, lv + ".pak"), "wb").write(dsar_list.extract(d, ent, bs, bsz, "pak68/%s.pak" % lv))
    for lv in levels(key):
        if lv + "-ingame" not in where:
            continue                       # level without an -ingame pak
        p = os.path.join(src, lv + "-ingame.pak")
        j = os.path.join(js, lv + "-ingame.json")
        if not os.path.exists(j) or os.path.getmtime(j) < os.path.getmtime(p):
            r = subprocess.run(["pwsh", "-NoProfile", "-File", DUMP, "-Pak", p, "-Out", j])
            if r.returncode or not os.path.exists(j):
                print("  %s: SceneEditor could not read it" % lv)
                continue
        out.append((lv, p, json.load(open(j, encoding="utf-8-sig")) or []))
    return out


def parked(key):
    """the map's own "park_spawners" (sp_maps.json): [{"level", "name", "why"}] - spawners of stock levels that must not appear in
    the PvP map (e.g. the glass + wheels actor of a vehicle whose body a level edit removed) -> {(level, name): why}"""
    for m in json.load(open(level_edit.SPEC, encoding="utf-8"))["maps"]:
        if m["key"] == key:
            return {(p["level"], p["name"]): "parked by the map spec: " + p.get("why", "") for p in m.get("park_spawners", [])}
    return {}


LOD_SUFFIX = re.compile(r"-(low|mid)$")


def lod_twins(dumps):
    """Gameplay spawners an LOD level (<base>-low / <base>-mid) carries as an exact copy of its base level's: in SP the LOD level
    is swapped OUT when the base level loads, in a PvP map every level stays loaded, so both copies spawn.  Into the City:
    the 4 WPL store windows (flo-window-24007373 / -37822197 / -48402867, window-1o50x2o1-broken-*, BigBreakable, x 263.55
    z 562..567) are in flo-into-the-city-ingame AND flo-into-the-city-low-ingame -> two glass actors per opening: shooting breaks
    one, the other stays (seen from the other side) and its collision blocks the window vault; the same for the delivery truck's
    glass + wheels actor and the 28 windows of flo-convention-center-tunnel(-low).  Copy = same type, same art, position and
    rotation within 1 cm / 1e-3, and the base level is in the map's level list.  The LOD copy is parked (the base level's actor is
    the one SP plays with).  -> {(lod level, name): why}"""
    by_level = {lv: sp for lv, _, sp in dumps}
    out = {}
    for lv, sp in by_level.items():
        base = LOD_SUFFIX.sub("", lv)
        if base == lv or base not in by_level:
            continue
        ref = [b for b in by_level[base] if b.get("type")]
        for s in sp:
            if not s.get("type"):
                continue
            for b in ref:
                if (b["type"] == s["type"] and b.get("art") == s.get("art")
                        and max(abs(x - y) for x, y in zip(b["pos"], s["pos"])) < 0.01
                        and max(abs(x - y) for x, y in zip(b["quat"], s["quat"])) < 1e-3):
                    out[(lv, s["name"])] = "LOD copy of %s %s (both levels load in MP)" % (base, b["name"])
                    break
    return out


def found(key):
    res = []
    park = parked(key)
    dumps = fetch_dump(key)
    twins = lod_twins(dumps) if os.environ.get("T2R_KEEP_LOD_SPAWNERS", "") != "1" else {}
    import spedit                                   # Scene Editor removals of SP spawners: parked like the collectibles
    sp_rm = spedit.removed(key)
    seen = set()
    for lv, p, sp in dumps:
        hit = [(s, park.get((lv, s["name"])) or twins.get((lv, s["name"])) or classify(dict(s)) or sp_rm.get((lv, s["name"]))) for s in sp]
        hit = [(s, why) for s, why in hit if why]
        seen |= {(lv, s["name"]) for s, _ in hit}
        if hit:
            res.append((lv, p, sp, hit))
    missing = sorted(set(park) - seen)
    if missing:
        raise SystemExit("collectibles: %s: park_spawners not found in the levels' -ingame paks: %s" % (key, missing))
    return res


# ====================================================================================== workbenches (baked level geometry)
# SP crafting / weapon-upgrade benches are not spawners: the bench is a prop placement in the level's render pak
# (<level>.pak; the prompt + menu come from SP script levels no PvP map loads), authored as a ".ma" prototype whose name has
# "workbench" (flo-cc-workbench-a = Convention Center, san-mansion-kitchen-workbench, pat-workbench-parts-bin ...).
# res-*-warehouse-workbench-a is a plain furniture table (set dressing in house B, no crafting): kept (BENCH_KEEP).
BENCH = re.compile(r"workbench", re.I)
BENCH_KEEP = re.compile(r"warehouse-workbench", re.I)
BENCH_PAD = 0.3          # props lying on a bench (tools, parts bins, discs) are removed with it: placements whose centre is inside its box + this pad
BENCH_UP = 2.2           # ... and above it (shelf kits / tool racks / canisters stand up to 2.2 m over the bench's own box)
BENCH_FIXED = re.compile(r"window|door|plug|fixture|outlet|switch|vent|pipe|trim|wall|floor|ceiling|beam|pillar|column|cabinet|island|counter|oven|sink|fridge|locker", re.I)   # building parts near a bench stay
BENCH_MAX_DRESS = 2.0   # ... when they are smaller than this (m, longest world side): never a wall / floor piece


def bench_edits(key, log=print, work=None):
    """Offline scan of every art level of a map for baked workbench placements -> (edits, report).  edits = level_edit entries
    ({"action": "remove"}, render = those placements, collision = the triangles inside their oriented boxes),
    report = [{"level", "proto", "kind", "pos"}].  Works for any map key of sp_maps.json (reads only levels present in
    the world psarcs)."""
    import numpy as np
    import ndpak
    work = work or level_edit.CACHE
    edits, report = [], []
    for lv in levels(key):
        try:
            src = level_edit.fetch(lv, os.path.join(work, "src"), None, ("",))
        except SystemExit:
            continue                                  # not a world pak (our own spawner pak, audio-only sets ...)
        p = ndpak.Pak(src[""])
        if not any(BENCH.search(sm["name"]) for sm in p.submeshes):
            continue
        insts = level_edit.find_instances(p)

        def is_bench(it):
            nm = [it.proto] + [n for n, _ in it.names]
            return any(BENCH.search(n or "") and not BENCH_KEEP.search(n or "") for n in nm)
        benches = [it for it in insts if is_bench(it)]
        if not benches:
            continue
        take = {it.pak_off: (it, "bench") for it in benches}
        for b in benches:
            for it in insts:
                if it.pak_off in take or (it.whi - it.wlo).max() > BENCH_MAX_DRESS or BENCH_FIXED.search(it.proto or ""):
                    continue
                ctr = (it.wlo + it.whi) / 2
                if (ctr >= b.wlo - BENCH_PAD).all() and (ctr <= b.whi + [BENCH_PAD, BENCH_UP, BENCH_PAD]).all():   # centre on the bench
                    take[it.pak_off] = (it, "dressing")
        offs = sorted(take)
        lo = np.min([take[o][0].wlo for o in offs], 0)
        hi = np.max([take[o][0].whi for o in offs], 0)
        edits.append({
            "name": "workbench strip (%d placements: %d bench + %d on it)" % (
                len(offs), sum(1 for o in offs if take[o][1] == "bench"), sum(1 for o in offs if take[o][1] == "dressing")),
            "level": lv, "box": [round(float(v) - 0.1, 3) for v in (*lo, *hi)], "action": "remove",
            "render": {"offsets": ["%#x" % o for o in offs]},
            "collision": {"obb_of": ["%#x" % o for o in offs], "margin": 0.05}, "auto": "workbench"})
        for o in offs:
            it, kind = take[o]
            report.append({"level": lv, "proto": (it.proto or ",".join(n for n, _ in it.names)).split("/")[-1], "kind": kind,
                           "pos": [round(float(v), 2) for v in it.M[3, :3]]})
        log("workbench scan %s: %s - %d bench placement(s), %d on-bench prop(s)" % (
            key, lv, len(benches), len(offs) - len(benches)))
    return edits, report


def sp_strip_collectibles_workbench(key, log=print):
    """THE reusable SP-map step (every SP map ships without collectibles and workbenches; crafting parts and normal
    pickups stay).  For one map key of sp_maps.json:
      collectibles  every collectible spawner (notes, artifacts, coins, cards, journal pages, skill-pill pickups, ...; COLLECT)
                    parked at y=-3000 in an edited <level>-ingame.pak copy (build_key)
      workbenches   baked workbench placements + the props lying on them removed from the level's render pak, their collision
                    triangles from the -phys pak (bench_edits -> level_edit entries, built by level_edit.build_edits)
    -> {"spawner_paks": [paths], "collectibles": {level: n}, "edits": [level_edit entries], "workbench": [report rows]}
    sp_maps_build.stage_edits calls it for every selected map; the map's own "edits" are merged per level."""
    files = build_key(key, log)
    cnt, other = {}, {}
    for lv, p, sp, hit in found(key):           # collectibles proper vs the LOD twins / spec-parked spawners that share the park edit
        for s, why in hit:
            d = other if why.startswith(("LOD copy", "parked by")) else cnt
            d[lv] = d.get(lv, 0) + 1
    edits, rep = bench_edits(key, log)
    return {"spawner_paks": files, "collectibles": cnt, "other_parked": other, "edits": edits, "workbench": rep}


def cmd_list(keys):
    for key in keys:
        tot = 0
        print("== %s" % key)
        for lv, p, sp, hit in found(key):
            for s, why in hit:
                tot += 1
                print("  %-44s %-24s %-14s (%8.1f %7.1f %8.1f)  %s" % (lv, s["name"], s["type"], *s["pos"], why))
        print("== %s: %d collectible spawner(s)" % (key, tot))


def cmd_names(keys):
    for key in keys:
        seen = {}
        for lv, p, sp in fetch_dump(key):
            for s in sp:
                k = (s["type"], re.sub(r"[-_]?\d+$", "", s["name"]))
                seen[k] = seen.get(k, 0) + 1
        print("== %s" % key)
        for (t, n), c in sorted(seen.items()):
            print("  %-22s %-60s %d" % (t, n, c))


def patch_pak(raw, hits):
    """In-place: every collectible spawner's position (3 x float32 in its record) -> PARK.  The SceneEditor writer rewrites a
    pak lossily (wat-accessibility 165 -> 52 KB with NO change), so the bytes are patched like tools/spawns/levels.py does
    (find the record by its exact position + rotation; unique hit required).  -> (bytes, [(name, offset)])"""
    b = bytearray(raw)
    done = []
    for s, _ in hits:
        key = struct.pack("<3f", *s["pos"])
        q = struct.pack("<4f", *s["quat"])
        offs, i = [], b.find(key)
        while i >= 0:
            offs.append(i)
            i = b.find(key, i + 1)
        both = [o for o in offs if bytes(b[o + 16:o + 32]) == q]
        use = both if len(both) == 1 else offs if len(offs) == 1 else None
        if use is None:
            raise SystemExit("collectibles: %s: %d position hits / %d with the rotation - not unique" % (s["name"], len(offs), len(both)))
        o = use[0] if isinstance(use, list) else use
        struct.pack_into("<3f", b, o, *PARK)
        done.append((s["name"], o))
    return bytes(b), done


def lod_feature_levels(key):
    """-ingame paks of the map's LOD levels (<base>-low / <base>-mid with <base> in the map's level list) that carry a FEATURE_DB_2:
    -> {level: pak path}.  T2R_KEEP_LOD_FEATURES=1: none."""
    if os.environ.get("T2R_KEEP_LOD_FEATURES", "") == "1":
        return {}
    # batch port: measured on Into the City only; the other pool maps keep their LOD FEATURE_DB until checked (T2R_LOD_FEATURES_ALL=1 = every map)
    if key != "into-the-city" and os.environ.get("T2R_LOD_FEATURES_ALL", "") != "1":
        return {}
    import ndpak
    lvs = set(levels(key))
    out = {}
    for lv, p, _ in fetch_dump(key):
        base = LOD_SUFFIX.sub("", lv)
        if base != lv and base in lvs and any(t == "FEATURE_DB_2" for _, t, _, _ in ndpak.Pak(p).items):
            out[lv] = p
    return out


def park_features(raw, src_path):
    """In-place: every edge (64 B records), post (56 B) and outline (40 B) of the pak's FEATURE_DB_2 (climb / vault / ledge edges,
    low-cover posts, cover outlines) moved to y - 3000 (P0 / P1; normals and the Prev / Next links stay).  The spatial trees stay
    as they are: they only prune, the edge geometry decides.  Into the City: the LOD level flo-into-the-city-low carries 460
    edges of its coarse proxy geometry (362 in the play area, 341 of them > 0.3 m from any real ledge, median 2.5 m): in SP the
    LOD level is swapped out when the base level loads, in a PvP map every level stays loaded, so those edges are phantom ledges
    over the real ones.  -> (bytes, (edges, posts, outlines))"""
    import ndpak
    pak = ndpak.Pak(src_path)                      # same layout as raw (the spawner patch is in place)
    b = bytearray(raw)
    cnt = [0, 0, 0]
    for _, typ, _, io in pak.items:
        if typ != "FEATURE_DB_2":
            continue
        base = io + 48
        for j, (off, stride) in enumerate(((0, 64), (16, 56), (32, 40))):
            n = struct.unpack_from("<Q", b, base + off + 8)[0]
            if not n:
                continue
            arr = pak.ptr(base + off)
            if not arr:
                raise SystemExit("collectibles: FEATURE_DB_2 array %d has a count but no pointer" % j)
            for i in range(n):
                for o in (4, 16):                      # P0.y, P1.y
                    y = struct.unpack_from("<f", b, arr + i * stride + o)[0]
                    struct.pack_into("<f", b, arr + i * stride + o, y + PARK[1])
            cnt[j] = int(n)
    return bytes(b), tuple(cnt)


def build_key(key, log=print):
    """-> ["<path of an edited <level>-ingame.pak>", ...]"""
    out_dir = os.path.join(WORK, "out", key)
    os.makedirs(out_dir, exist_ok=True)
    import spedit
    mv = spedit.moves(key)
    files = []
    feats = lod_feature_levels(key)        # 503f7e9a (Into the City): the loaded LOD levels' FEATURE_DB (phantom climb / vault edges) is parked too
    todo = [(lv, p, hit) for lv, p, sp, hit in found(key)]
    have = {lv for lv, _, _ in todo}
    if any(m["level"] not in have for m in mv):
        pk = {lv: p for lv, p, _sp in fetch_dump(key)}
        todo += [(lv, pk[lv], []) for lv in sorted({m["level"] for m in mv} - have) if lv in pk]
        have = {lv for lv, _, _ in todo}
    todo += [(lv, p, []) for lv, p in sorted(feats.items()) if lv not in have]
    for lv, p, hit in todo:
        raw = open(p, "rb").read()
        data, done = patch_pak(raw, hit) if hit else (raw, [])
        data, moved = spedit.patch_moves(data, [m for m in mv if m["level"] == lv])
        if lv in feats:
            data, fc = park_features(data, p)
            log("collectibles %s: %s - FEATURE_DB of the LOD level parked at y=%d (%d edges, %d posts, %d outlines)" % (key, lv, PARK[1], *fc))
        dst = os.path.join(out_dir, lv + "-ingame.pak")
        if not os.path.exists(dst) or open(dst, "rb").read() != data:
            open(dst, "wb").write(data)
        log("collectibles %s: %s - parked %d spawner(s) at y=%d: %s; moved %d (spedits)" % (key, lv, len(done), PARK[1], ", ".join(n for n, _ in done), len(moved)))
        files.append(dst)
    return files


def build(keys):
    for key in keys:
        fs = build_key(key)
        print("%s: %d edited -ingame pak(s)" % (key, len(fs)))


SNAPSHOT = os.path.join(HERE, "data", "sp-strip.json")


def cmd_strip(keys):
    """python collectibles.py strip <map key>...   run sp_strip_collectibles_workbench for each map (writes the edited
    -ingame paks to the cache, builds nothing else) and merge the counts into data/sp-strip.json (checked by tests/test_sp_strip.py)"""
    snap = json.load(open(SNAPSHOT, encoding="utf-8")) if os.path.exists(SNAPSHOT) else {}
    for key in keys:
        r = sp_strip_collectibles_workbench(key)
        snap[key] = {"collectible_spawners": r["collectibles"], "other_parked_spawners": r["other_parked"],
                     "workbench": sorted(r["workbench"], key=lambda x: (x["level"], x["kind"], x["proto"], x["pos"]))}
        print("%s: %d collectible spawner(s) %s, %d workbench placement(s) (%d bench, %d on it); other parked spawners %d" % (
            key, sum(r["collectibles"].values()), r["collectibles"], len(r["workbench"]),
            sum(1 for w in r["workbench"] if w["kind"] == "bench"), sum(1 for w in r["workbench"] if w["kind"] == "dressing"),
            sum(r["other_parked"].values())))
    json.dump(snap, open(SNAPSHOT, "w", encoding="utf-8", newline="\n"), indent=1, sort_keys=True)


if __name__ == "__main__":
    if len(sys.argv) < 2 or sys.argv[1] not in ("list", "build", "names", "strip"):
        raise SystemExit(__doc__)
    {"list": cmd_list, "build": build, "names": cmd_names, "strip": cmd_strip}[sys.argv[1]](sys.argv[2:])
