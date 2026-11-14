"""Model-space bounding boxes of prop actors (actor97/<name>.pak, read only from the game psarcs) so blocker
lines can be laid out with the right spacing and facing.
  python prop_bounds.py <actor>...   -> x / y / z extents (m) of all LOD0-ish submeshes
Results are cached in tools/maps/data/prop_bounds.json (used by sp_bounds.py)."""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.dirname(HERE)
ROOT = os.path.dirname(TOOLS)
sys.path.insert(0, TOOLS)
sys.path.insert(0, os.path.join(TOOLS, "models"))
GAME = os.environ.get("T2_GAME", "C:/Games/The Last of Us Part II Remastered")
CACHE = os.path.join(ROOT, "re", "maps", "paks", "_base", "actor97")
DB = os.path.join(HERE, "data", "prop_bounds.json")


def actor_pak(name):
    import dsar_list
    p = os.path.join(CACHE, name + ".pak")
    if os.path.exists(p):
        return p
    hits = [a for a, _ in [(l.split("\t")[0], 0) for l in open(os.path.join(ROOT, "re", "game-files.tsv"),
            encoding="utf-8", errors="replace") if l.split("\t")[1:2] == [f"actor97/{name}.pak"]]]
    assert hits, f"actor97/{name}.pak not in the game"
    os.makedirs(CACHE, exist_ok=True)
    d, ent, bs, bsz = dsar_list.open_files(os.path.join(GAME, "build", "pc", "main", hits[0]))
    open(p, "wb").write(dsar_list.extract(d, ent, bs, bsz, f"actor97/{name}.pak"))
    return p


def bounds(name):
    import ndpak
    pk = ndpak.Pak(actor_pak(name))
    lo, hi = [1e9] * 3, [-1e9] * 3
    for sm in getattr(pk, "submeshes", []) or []:
        try:
            for v in pk.positions(sm):
                for i in range(3):
                    lo[i], hi[i] = min(lo[i], v[i]), max(hi[i], v[i])
        except Exception:
            continue
    assert lo[0] < 1e9, f"{name}: no geometry read"
    return {"min": [round(float(v), 3) for v in lo], "max": [round(float(v), 3) for v in hi],
            "size": [round(float(hi[i] - lo[i]), 3) for i in range(3)]}


def load():
    return json.load(open(DB)) if os.path.exists(DB) else {}


if __name__ == "__main__":
    db = load()
    for n in sys.argv[1:]:
        db[n] = bounds(n)
        print(n, db[n])
    os.makedirs(os.path.dirname(DB), exist_ok=True)
    json.dump(db, open(DB, "w"), indent=1)
