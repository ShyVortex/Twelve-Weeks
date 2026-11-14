"""LOD fix for the vehicle actors our spawner-pak props use (the cars we added only showed fully up close; from ~10 m their
body disappeared).  Offline only (CPU): reads the stock actor97 paks out of the game psarcs, writes patched copies.

What the stock actor pak holds (station-wagon-a, wat-traps-suv-small-a, military-truck-modern-a, measured):
  * one FOREGROUND_SECTION_2 per LOD ('geo.<art>', '.lod1', '.lod2').  u32 @ +64 = flags, f32 @ +72 = distance: the base section
    carries the cull distance (wagon 248 m, SUV 202, truck 500), '.lod1' / '.lod2' the distances where LOD1 / LOD2 start (wagon 15 /
    25 m, SUV 15 / 20, truck 16 / 40).  The same three floats sit in the pak's 'lod_distance' TAG_FLOAT items (f32 @ +48).
  * the SP levels never use these actors for the car body: their parked cars are baked into the level (`wat-capitol-hill-main-vehicles`
    etc., only the `*-glass-fg` twins are spawners), with the level's own LOD levels.  So the actor LODs are only ever exercised by
    OUR spawner props, and their LOD1 / LOD2 are the cheap stand-ins SP never shows on a drivable body.
Fix: LOD1 / LOD2 start far out (min(cull, 240 m), 1 m apart, ascending like stock; LOD0, the full body, is drawn at every distance a
map this size has); the tag floats follow.  First version (start = cull, tied) left the 500 m truck INVISIBLE in game (A/B; the wagons
were not reported), so values >= ~250 or ties are suspect; the capped values are untested.  Shipped as replacements of the stock actor97 paks (same names, like every other stock pak the mod replaces)."""
import glob
import os
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.dirname(HERE)
sys.path.insert(0, TOOLS)
sys.path.insert(0, os.path.join(TOOLS, "models"))
GAME = os.environ.get("T2R_TLOU2_DIR", r"C:\Games\The Last of Us Part II Remastered")
ARTS = ("station-wagon-a", "wat-traps-suv-small-a")   # military-truck-modern-a dropped (invisible with both LOD patches - ships stock)     # vehicle actors with LOD sections that props use
SEC_DIST = 72
MAX_START = 240.0                                # cap for the LOD1 / LOD2 start distances (the map is < 130 m across)
TAG_VAL = 48


def stock_pak(art, game=None):
    import dsar_list
    d_ = os.path.join(game or GAME, "build", "pc", "main")
    for arc in sorted(glob.glob(os.path.join(d_, "world-*.psarc"))) + [os.path.join(d_, "sp-common.psarc")]:
        if not os.path.exists(arc):
            continue
        d, ent, bs, bsz = dsar_list.open_files(arc)
        k = f"actor97/{art}.pak"
        if k in ent:
            return dsar_list.extract(d, ent, bs, bsz, k)
    raise SystemExit(f"actor97/{art}.pak not in any game archive")


def sections(p, art):
    """(base, [lod sections]) as (item offset, distance); lod sections in ascending LOD order"""
    base, lods = None, []
    for name, typ, _, off in p.items:
        if typ != "FOREGROUND_SECTION_2" or not name.startswith("geo." + art):
            continue
        dist = struct.unpack_from("<f", p.d, off + SEC_DIST)[0]
        rest = name[len("geo." + art):]
        if rest == "":
            base = (off, dist)
        elif rest.startswith(".lod"):
            lods.append((int(rest[4:]), off, dist))
    return base, [(o, d) for _, o, d in sorted(lods)]


def patch(raw, art):
    """-> (patched bytes, report); LOD1 / LOD2 distances (section floats + the matching lod_distance tag floats) = the cull distance"""
    import ndpak
    tmp = os.path.join(os.environ.get("TEMP", "."), f"prop_lod_{os.getpid()}_{art}.pak")
    open(tmp, "wb").write(raw)
    try:
        p = ndpak.Pak(tmp)
        base, lods = sections(p, art)
    finally:
        pass
    assert base and lods, f"{art}: no LOD sections"
    cull = base[1]
    far = min(cull, MAX_START)                       # the truck's 500 m cull distance as a LOD start = invisible body in game (A/B)
    new = [far - (len(lods) - 1 - i) for i in range(len(lods))]    # strictly ascending like stock (ties / start == cull were also suspect)
    out = bytearray(raw)
    old = [d for _, d in lods]
    for (off, _d), v in zip(lods, new):
        struct.pack_into("<f", out, off + SEC_DIST, v)
    olds = set(round(d, 3) for d in old)
    n = 0
    for name, typ, _, off in p.items:
        if typ == "TAG_FLOAT" and name == "lod_distance":
            v = struct.unpack_from("<f", raw, off + TAG_VAL)[0]
            if round(v, 3) in olds:
                struct.pack_into("<f", out, off + TAG_VAL, new[sorted(olds).index(round(v, 3))] if len(olds) == len(new) else far)
                n += 1
    try:
        os.remove(tmp)
    except OSError:
        pass
    return bytes(out), f"{art}: LOD starts {old} -> {new} (cull {cull}), {n} lod_distance tag floats"


def stage(stage_dir, arts=ARTS, game=None, log=print):
    """write the patched actor97 paks into <stage_dir>/actor97/; -> ['actor97/<art>.pak', ...] (manifest paths)"""
    os.makedirs(os.path.join(stage_dir, "actor97"), exist_ok=True)
    out = []
    for a in arts:
        data, rep = patch(stock_pak(a, game), a)
        open(os.path.join(stage_dir, "actor97", a + ".pak"), "wb").write(data)
        log("  prop LOD fix: " + rep)
        out.append(f"actor97/{a}.pak")
    return out


def main(argv):
    d = argv[1] if len(argv) > 1 else os.path.join(os.environ.get("TEMP", "."), "prop_lod")
    stage(d)


if __name__ == "__main__":
    main(sys.argv)
