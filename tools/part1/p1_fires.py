"""Part I Bookstore fire barrels from the Forest (No Return) burning trash can.

Part I's two barrels are particle spawners only (fx-hun-fire-barrel-25 / -26 + embers / smoke / a light particle); the converted
levels keep the barrels and the baked orange, the fire and the realtime light are missing. The donor is the trash-can fire of
t2r-nor-scar-burial-parking-lot (world-rogue.psarc) at 17.20 4.64 37.43:

* fire: its particle spawners (t2r-nor-scar-burial-parking-lot-ingame.pak) cloned into the map's -ingame pak at each barrel, offsets
  from the can kept (tools/spawns/graft_spawners.ps1); their particle groups load with part-level-t2r-nor-scar-burial-parking-lot.
* light: the can's point light record (LIGHT_TABLE_1 point array, 0x54 bytes, measured below) appended to the point array
  of the converted base pak's LIGHT_TABLE_1 (Part I's Bookstore has none: +0x10 count 0, +0x28 null), moved to each barrel.

LIGHT_TABLE_1 payload (TLOU2 format 0xb, 0x68 bytes, read from the donor and the converted Part I pak):
  +0x00 u32 version 0xb      +0x08 ptr art name ("light-skel" + ...)   +0x10 u64 point lights   +0x18 u64 spot lights
  +0x20 u32 ortho lights, u32 1   +0x28 ptr point records   +0x38 ptr spot records   +0x48 ptr ortho records
  +0x50 ptr shadow / cascade settings   +0x58 ptr light-probe grid (bounds, counts, probe spheres, packed SH)
Point record (0x54): colour rgb, position, (1 1 1), position again, u32 0x0006000a-ish flags, radius, 0.02, 0, 0, intensity,
0, 0.1, 1.  The donor's ANIMATED_LIGHTS item maps each rt- light name to (array, index) for its ProcessDynLight flicker; that
item and the light-anims ANIM_GROUP are NOT ported (new items in the Part I pak): the barrel light is steady, the flicker is
the particles'.  T2R_P1_FIRES=0: off (no spawners, no part-level, no light records).
"""
import json
import os
import struct
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.dirname(HERE)
DONOR_LEVEL = "t2r-nor-scar-burial-parking-lot"
DONOR_PARTICLES = "part-level-t2r-nor-scar-burial-parking-lot"
DONOR_ANCHOR = (17.20383, 4.641314, 37.42868)          # fx-bonfire-tiny-41: the base of the can's fire
DONOR_SPAWNERS = ("fx-bonfire-tiny-41", "fx-bonfire-tiny-42", "fx-bonfire-tiny-44", "fx-bonfire-tiny-45", "fx-bonfire-tiny-46",
                  "fx-fire-looped-packed-window-med-3", "fx-fire-looped-packed-window-sm-11", "fx-fire-looped-packed-window-sm-12",
                  "fx-fireb-embers-1", "fx-fireB-smoke-1", "fx-heat-distort-7")
# rt-parking-lot-trash-can-Shape-1, the donor's LIGHT_TABLE_1 point record 1 (t2r-nor-scar-burial-parking-lot.pak +0x56e75c)
DONOR_LIGHT = bytes.fromhex("6fb7743f82bf923ed97e823ddcbc89418620a6405fb515420000803f0000803f0000803fdcbc89418620a6405fb51542"
                            "09000600000020410ad7a33c000000000000000085c4dd4000000000cdcccc3d0000803f")
DONOR_LIGHT_POS = (17.21721649169922, 5.191470146179199, 37.427120208740234)
POINT_SIZE = 0x54
LT_POINTS, LT_POINT_PTR = 0x10, 0x28
MAGIC = 0xDEADBEEFDEADBEEF


def on():
    return os.environ.get("T2R_P1_FIRES", "1") != "0"


def fires(m):
    """spec part1.fires: [{"name", "pos": [x, y, z] = the barrel's fire base, "light-level"}] (empty when off)"""
    return m.get("part1", {}).get("fires", []) if on() else []


# ------------------------------------------------------------------ particles
def spawner_entries(fs, donor):
    """donor spawner list [{name, pos, quat}] -> graft_spawners.ps1 entries: every DONOR_SPAWNERS at every fire"""
    by = {s["name"]: s for s in donor}
    missing = [n for n in DONOR_SPAWNERS if n not in by]
    assert not missing, f"donor {DONOR_LEVEL}-ingame lacks {missing}"
    out = []
    for f in fs:
        for n in DONOR_SPAWNERS:
            if n in f.get("skip", ()):      # The upstairs barrel is a "whole ball of fire" - its big window-med sprite is left out
                continue
            s = by[n]
            out.append({"src": n, "name": f"t2r-{f['name']}-{n}",
                        "pos": [round(f["pos"][i] + s["pos"][i] - DONOR_ANCHOR[i], 4) for i in range(3)], "quat": s["quat"]})
    return out


def graft(pak, fs, cache):
    """our -ingame pak (edited in place) + the fires -> number of spawners added"""
    sys.path.insert(0, os.path.join(TOOLS, "maps"))
    import level_edit
    donor = level_edit.fetch(DONOR_LEVEL, cache, suffixes=("-ingame",))["-ingame"]
    dj = os.path.join(cache, DONOR_LEVEL + "-ingame.json")
    if not os.path.exists(dj) or os.path.getmtime(dj) < os.path.getmtime(donor):
        subprocess.run(["pwsh", "-NoProfile", "-File", os.path.join(TOOLS, "spawns", "dump_json.ps1"), "-Pak", os.path.abspath(donor), "-Out", dj],
                       check=True, stdout=subprocess.DEVNULL)
    ents = spawner_entries(fs, json.load(open(dj, encoding="utf-8-sig")))
    ej = os.path.join(cache, "fires-%d.json" % os.getpid())
    json.dump(ents, open(ej, "w"))
    try:
        subprocess.run(["pwsh", "-NoProfile", "-File", os.path.join(TOOLS, "spawns", "graft_spawners.ps1"), "-Pak", os.path.abspath(pak),
                        "-Donor", os.path.abspath(donor), "-Json", ej], check=True, stdout=subprocess.DEVNULL)
    finally:
        os.remove(ej)
    return len(ents)


# ------------------------------------------------------------------ Part I light actors
def light_actors_on():
    return os.environ.get("T2R_P1_LIGHT_ACTORS", "1") != "0"


def graft_actors(pak, donor_pak, names, cache):
    """Part I's own ProcessDynLight spawners (the Bookstore's rt-ortho-fake-son-Shape-1: type "projector", art light-skel, scale 10, its ~45 light
    properties) cloned as they are from the converted Part I -ingame pak into our -ingame pak. TLOU2 drives a light from its ACTOR (the table record is only
    the slot the actor rewrites every frame), and Part I's actor was never staged. Same schema in both games (the property sids are TLOU2's). -> count"""
    donor_pak = os.path.abspath(donor_pak)
    os.makedirs(cache, exist_ok=True)
    dj = os.path.join(cache, os.path.basename(donor_pak) + ".json")
    if not os.path.exists(dj) or os.path.getmtime(dj) < os.path.getmtime(donor_pak):
        subprocess.run(["pwsh", "-NoProfile", "-File", os.path.join(TOOLS, "spawns", "dump_json.ps1"), "-Pak", donor_pak, "-Out", dj],
                       check=True, stdout=subprocess.DEVNULL)
    by = {s["name"]: s for s in json.load(open(dj, encoding="utf-8-sig"))}
    ents = []
    for n in names:
        assert n in by, f"{donor_pak} has no spawner {n}"
        ents.append({"src": n, "name": n, "pos": by[n]["pos"], "quat": by[n]["quat"]})
    ej = os.path.join(cache, "actors-%d.json" % os.getpid())
    json.dump(ents, open(ej, "w"))
    try:
        subprocess.run(["pwsh", "-NoProfile", "-File", os.path.join(TOOLS, "spawns", "graft_spawners.ps1"), "-Pak", os.path.abspath(pak),
                        "-Donor", donor_pak, "-Json", ej], check=True, stdout=subprocess.DEVNULL)
    finally:
        os.remove(ej)
    return len(ents)


# ------------------------------------------------------------------ Part I prop spawners (actor art TLOU2 also has)
SPAWN_ARTS = os.path.join(TOOLS, "maps", "data", "p1-bookstore-spawn-arts.json")


def spawner_arts_on():
    return os.environ.get("T2R_P1_SPAWNERS", "1") != "0"


def converted_actors_on():
    """Crash (EXCEPTION 80000003 at exe+1c31515, frame 10021 after the Bookstore level start, r12 in the actor names hun-isle-sign-* /
    hun-bookstore-sign-new-arrivals-a / hun-tent-hanging-plug-a): every converted Part I actor pak still carries Part I's Havok 2020.1 collision tagfile
    (SDKV20200100) in COLLISION_DATA_FOREGROUND; TLOU2 reads 2017.1 (SDKV20170100). The hanging signs / plug (5 hkpConstraint each) assert first.
    Staging them is OFF until the actor collision is translated (havok_convert for actor shapes); T2R_P1_ACTORS_CONVERTED=1 forces it for a test."""
    return os.environ.get("T2R_P1_ACTORS_CONVERTED", "0") == "1"


def _arts_json(m):
    f = m.get("part1", {}).get("spawner-arts")
    if not f or not spawner_arts_on():
        return None
    return json.load(open(os.path.join(TOOLS, "..", f), encoding="utf-8"))


def spawner_arts(m, conv=None):
    """spec part1.spawner-arts (a json under tools/maps/data) -> [art]: the Part I prop spawners to graft: "same" = TLOU2 ships the same mesh (compared,
    bookstore_missing_objects_1105.md), plus "convert" = arts converted from the Part I actor paks by p1_actors.py that exist as
    <conv>/actors/<file>.pak (see actor_file); [] when off. Names are the Part I art names (what the spawners carry)"""
    d = _arts_json(m)
    if d is None:
        return []
    out = sorted(d["same"])
    if conv and converted_actors_on():
        ibg = set(d.get("interactive-bg-actors", []))
        out += [a for a in d.get("convert", []) if a not in ibg and os.path.exists(os.path.join(conv, "actors", actor_file(m, a) + ".pak")) and a not in out]
    return out


def actor_file(m, art):
    """the actor (pak) name a Part I art is staged / registered under: the 'p1-' renamed one for arts whose same-named TLOU2 actor has other art"""
    d = _arts_json(m)
    return (d or {}).get("rename", {}).get(art, art)


def actor_names(m, conv):
    """[actor name, ...] for the level blocks and the staging: the spawner arts (renamed ones under their new name) + the converted INTERACTIVE_BG_1 actors"""
    d = _arts_json(m)
    if d is None:
        return []
    out = [actor_file(m, a) for a in spawner_arts(m, conv)]
    if not converted_actors_on():
        return out
    out += [a for a in d.get("interactive-bg-actors", []) if os.path.exists(os.path.join(conv, "actors", a + ".pak"))]
    return out


def graft_level_spawners(pak, conv_dir, levels, arts, cache, rename=None, prefixes=()):
    """Every spawner of the converted Part I <level>-ingame paks whose art is in `arts`, cloned as it is (Part I name, position,
    rotation, properties) into our -ingame pak. The Part I levels hold them as dynamic props (books on the shelves, cups, car glass ...). -> count"""
    os.makedirs(cache, exist_ok=True)
    n = 0
    for lv in levels:
        donor = os.path.abspath(os.path.join(conv_dir, lv + "-ingame.pak"))
        if not os.path.exists(donor):
            continue
        dj = os.path.join(cache, os.path.basename(donor) + ".json")
        if not os.path.exists(dj) or os.path.getmtime(dj) < os.path.getmtime(donor):
            subprocess.run(["pwsh", "-NoProfile", "-File", os.path.join(TOOLS, "spawns", "dump_json.ps1"), "-Pak", donor, "-Out", dj],
                           check=True, stdout=subprocess.DEVNULL)
        if not os.path.exists(dj):          # a level without a SPAWNER_GROUP: the reader writes nothing
            continue
        d = json.load(open(dj, encoding="utf-8-sig"))
        if isinstance(d, dict):
            d = [d]
        ents = [{"src": s["name"], "name": s["name"], "pos": s["pos"], "quat": s["quat"], "art": (rename or {}).get(s["art"], s["art"])} for s in d if (s["art"] and s["art"] in arts) or (prefixes and s["name"].startswith(prefixes))]
        if not ents:
            continue
        ej = os.path.join(cache, "spawn-%d.json" % os.getpid())
        json.dump(ents, open(ej, "w"))
        try:
            subprocess.run(["pwsh", "-NoProfile", "-File", os.path.join(TOOLS, "spawns", "graft_spawners.ps1"), "-Pak", os.path.abspath(pak),
                            "-Donor", donor, "-Json", ej], check=True, stdout=subprocess.DEVNULL)
        finally:
            os.remove(ej)
        n += len(ents)
    return n


# ------------------------------------------------------------------ light records
def light_record(pos, light=None):
    """the donor's point record moved to `pos` (the fire base; the light sits as high above it as the can's).
    light = spec part1.fires[].light {"radius", "intensity", "vol"}: the upstairs barrel (orange fog filling the hall, the light
    reaching the ground floor through the slab - the record has no shadow, so its radius is the only limit) gets radius 4.5 (the light sits
    5.8 m over the ground floor), intensity 3.2 and volumetric intensity (+0x4c, the can's 0.1) 0.02; no `light` = the can's own values"""
    r = bytearray(DONOR_LIGHT)
    light = light or {}
    if "radius" in light:
        struct.pack_into("<f", r, 0x34, light["radius"])
    if "intensity" in light:
        struct.pack_into("<f", r, 0x44, light["intensity"])
    if "vol" in light:
        struct.pack_into("<f", r, 0x4c, light["vol"])
    p = [pos[i] + DONOR_LIGHT_POS[i] - DONOR_ANCHOR[i] for i in range(3)]
    struct.pack_into("<3f", r, 12, *p)
    struct.pack_into("<3f", r, 36, *p)
    return bytes(r)


def _hdr(d):
    u = lambda o: struct.unpack_from("<I", d, o)[0]
    return [u(4 * i) for i in range(11)]


def _items(d, pages):
    for pi, (st, sz, fl) in enumerate(pages):
        cnt = struct.unpack_from("<H", d, st + 18)[0]
        for k in range(cnt):
            io = st + struct.unpack_from("<I", d, st + 20 + 16 * k + 8)[0]
            a = st + struct.unpack_from("<Q", d, io + 8)[0]
            typ = bytes(d[a:d.index(b"\0", a)]).decode("latin1")
            yield pi, io, typ


def light_table(d):
    """-> (page index, payload offset in the file) of the pak's single LIGHT_TABLE_1"""
    h = _hdr(d)
    pages = [struct.unpack_from("<III", d, h[5] + 12 * i) for i in range(h[4])]
    lts = [(pi, io + 48) for pi, io, t in _items(d, pages) if t == "LIGHT_TABLE_1"]
    assert len(lts) == 1, f"{len(lts)} LIGHT_TABLE_1 items"
    return lts[0]


def point_lights(d):
    """the point records of the pak's LIGHT_TABLE_1 (read back through the fixup table) -> [bytes]"""
    h = _hdr(d)
    pages = [struct.unpack_from("<III", d, h[5] + 12 * i) for i in range(h[4])]
    fdo, fc = struct.unpack_from("<II", d, h[7] + 4)
    pi, pl = light_table(d)
    slot = pl + LT_POINT_PTR - pages[pi][0]
    n = struct.unpack_from("<Q", d, pl + LT_POINTS)[0]
    if not n:
        return []
    dp = next(e[1] for e in (struct.unpack_from("<HHI", d, fdo + 8 * i) for i in range(fc)) if e[0] == pi and e[2] == slot)
    a = pages[dp][0] + struct.unpack_from("<Q", d, pl + LT_POINT_PTR)[0]
    return [bytes(d[a + POINT_SIZE * i:a + POINT_SIZE * (i + 1)]) for i in range(n)]


def add_point_lights(d, recs):
    """converted pak bytes + point records -> pak bytes with them as the LIGHT_TABLE_1 point array (the table must have none):
    one new page (0x20 header, no items) after the last page, one new fixup (table +0x28 -> it); the header, page table and
    fixup table are laid out as p1_convert.repage does, the pages and the texture trailer are unchanged."""
    sys.path.insert(0, HERE)
    import p1_convert
    d = bytes(d)
    h = _hdr(d)
    ver, _hs, lp, lo, n, pt, h6, ft, tr_len, vp, vo = h
    pages = [struct.unpack_from("<III", d, pt + 12 * i) for i in range(n)]
    fdo, fc = struct.unpack_from("<II", d, ft + 4)
    fix = [struct.unpack_from("<HHI", d, fdo + 8 * i) for i in range(fc)]
    end = max(s + z for s, z, _ in pages)
    pi, pl = light_table(d)
    assert struct.unpack_from("<Q", d, pl + LT_POINTS)[0] == 0 and struct.unpack_from("<Q", d, pl + LT_POINT_PTR)[0] == 0, \
        "LIGHT_TABLE_1 already has point lights"
    body = b"".join(recs)
    size = (0x20 + len(body) + 15) // 16 * 16
    page = bytearray(size)
    struct.pack_into("<QIIHH", page, 0, MAGIC, 0, size, 0, 0)
    page[0x20:0x20 + len(body)] = body
    out_pages = [bytearray(d[s:s + z]) for s, z, _ in pages] + [page]
    flags = [f for _, _, f in pages] + [0]
    lt = out_pages[pi]
    o = pl - pages[pi][0]
    struct.pack_into("<Q", lt, o + LT_POINTS, len(recs))
    struct.pack_into("<Q", lt, o + LT_POINT_PTR, 0x20)
    nf = sorted(set(fix) | {(pi, n, o + LT_POINT_PTR)})
    npg = n + 1
    ft2 = pt + 12 * npg
    fdo2 = p1_convert.fix_data_off(ft2)
    first2 = fdo2 + 8 * len(nf) + 8
    head = bytearray(first2)
    head[:pt] = d[:pt]
    struct.pack_into("<8I", head, 0, ver, first2 - 8, lp, lo, npg, pt, h6, ft2)
    struct.pack_into("<III", head, 0x20, tr_len, vp, vo)
    pos = first2
    for i, pg in enumerate(out_pages):
        struct.pack_into("<III", head, pt + 12 * i, pos, len(pg), flags[i])
        pos += len(pg)
    struct.pack_into("<III", head, ft2, 0, fdo2, len(nf))
    for i, (s_, d_, o_) in enumerate(nf):
        struct.pack_into("<HHI", head, fdo2 + 8 * i, s_, d_, o_)
    return bytes(head) + b"".join(bytes(p) for p in out_pages) + d[end:]


def check(before, after, recs):
    """problems list: the light records read back, every old page / fixup / the trailer unchanged, the loader mirrors clean"""
    bad = []
    if point_lights(after) != list(recs):
        bad.append("point records do not read back")
    hb, ha = _hdr(before), _hdr(after)
    pb = [struct.unpack_from("<III", before, hb[5] + 12 * i) for i in range(hb[4])]
    pa = [struct.unpack_from("<III", after, ha[5] + 12 * i) for i in range(ha[4])]
    pi, pl = light_table(before)
    for i, ((s0, z0, f0), (s1, z1, f1)) in enumerate(zip(pb, pa)):
        a, b = before[s0:s0 + z0], after[s1:s1 + z1]
        if z0 != z1 or f0 != f1 or (a != b and i != pi):
            bad.append(f"page {i} changed")
    if before[max(s + z for s, z, _ in pb):] != after[max(s + z for s, z, _ in pa):]:
        bad.append("texture trailer changed")
    if ha[2:4] != hb[2:4] or ha[8:11] != hb[8:11]:
        bad.append("login / trailer / vram header fields changed")
    return bad
