"""EXPERIMENT (A/B only, never wired into a build): a copy of a car actor pak whose own collision items are relabelled COLLISION_DATA_EMPTY, so that the SP car's
collision written into -phys (level_edit action "cars") is the only collision.

  python vehicle_norcol.py <actor> <out dir>      # writes <out>/actor97/<actor>.pak (stock bytes, only the type strings of the collision items changed)

What is known (M, offline): a car actor pak has COLLISION_DATA_FOREGROUND (convex hull, tag 'collision.<actor>') and COLLISION_DATA_BACKGROUND items; item types are
ZERO-terminated strings in the page's string pool (the item record holds a page-relative pointer), shared by all items of that type.  A render-only actor exists in
the game: `void-blocker` (GEOMETRY + COLLISION_DATA_EMPTY, 'geo.void-blocker').  What is NOT known: whether the loader of COLLISION_DATA_EMPTY accepts the payload
of a FOREGROUND/BACKGROUND item (its payload version is 0x100d / other, the EMPTY one 0x1001), whether a BACKGROUND item may be relabelled, whether the stale
fixups of the old payload are harmless.  Nothing here was run in the game: if it crashes at load, the actor pak is the cause.  Shadowing the stock name also removes
the collision of every OTHER use of that actor (existing maps' props), so stage it only for a map that uses the actor through presets.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.dirname(HERE)
sys.path.insert(0, TOOLS)
sys.path.insert(0, os.path.join(TOOLS, "models"))
import ndpak  # noqa: E402

OLD = (b"COLLISION_DATA_FOREGROUND", b"COLLISION_DATA_BACKGROUND")
NEW = b"COLLISION_DATA_EMPTY"


def patch(raw):
    """-> (patched bytes, number of type strings changed)"""
    buf = bytearray(raw)
    n = 0
    for old in OLD:
        o = 0
        while True:
            o = buf.find(old + b"\0", o)
            if o < 0:
                break
            buf[o:o + len(old) + 1] = (NEW + b"\0").ljust(len(old) + 1, b"\0")
            n += 1
            o += len(old) + 1
    return bytes(buf), n


def stage(actor, out):
    import dsar_list
    rows = [l.rstrip("\n").split("\t") for l in open(os.path.join(os.path.dirname(TOOLS), "re", "game-files.tsv"), encoding="utf-8", errors="replace")]
    game = os.environ.get("T2_GAME", "C:/Games/The Last of Us Part II Remastered")
    for a, p, s, *_ in rows:
        if p == "actor97/%s.pak" % actor:
            d, ent, bs, bsz = dsar_list.open_files(os.path.join(game, "build", "pc", "main", a))
            raw = dsar_list.extract(d, ent, bs, bsz, p)
            new, n = patch(raw)
            dst = os.path.join(out, "actor97", actor + ".pak")
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            open(dst, "wb").write(new)
            pk = ndpak.Pak(dst)
            types = sorted({t for _, t, _, _ in pk.items if t.startswith("COLLISION")})
            print("%s: %d type string(s) relabelled -> collision item types now %s; %d bytes" % (actor, n, types, len(new)))
            return dst
    raise SystemExit("no actor97/%s.pak in the game archives" % actor)


if __name__ == "__main__":
    stage(sys.argv[1], sys.argv[2])
