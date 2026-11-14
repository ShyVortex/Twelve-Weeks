"""The Part I Bookstore file set: exactly what sp_maps_build stages for the map, as in-game relative paths.

  python p1_fileset.py list [key]                      # paths the build stages (T2R_P1_CONV = the conv dir; honours T2R_P1_PHYS / _INGAME / _RS / _AUDIO)
  python p1_fileset.py hash <dir> [--key=p1-bookstore] # {path: sha256} of those files under <dir> (a staged tree) as JSON on stdout
  python p1_fileset.py compare <a.json|dir> <b.json|dir> [--key=..]   # exit 0 only when every file of the set matches byte for byte

Used by tools/update_server/publish_part1.py (server pack from a build's staged tree) and by p1conv (the launcher-side converter writes the same
set, so `compare` of its output against the server pack proves the player's conversion is byte-identical). Paths mirror the in-game paths; the
launcher keeps them under <game dir>/t2r-maps/part1/.
"""
import hashlib
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(TOOLS, "features"))
sys.path.insert(0, os.path.join(TOOLS, "models"))


def bookstore_files(key="p1-bookstore"):
    import sp_maps_build as B
    m = next(x for x in B.specs() if x["key"] == key) if hasattr(B, "specs") else None
    out = []
    for lv in B.p1_levels(m):
        for suf in ("",) + (("-phys",) if B.p1_phys(lv) else ()) + (("-ingame",) if B.p1_ingame() else ()):
            out.append(f"pak68/{lv}{suf}.pak")
    rs = B.p1_rs(m)
    if rs:
        out += [f"pak68/{rs}-ingame.pak", "bin/dc1/" + B.RS_MODULE + ".bin"]
    out += B.p1_audio_files(m) + B.p1_actor_files(m)
    return sorted(set(out))


def sha256_file(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 22), b""):
            h.update(b)
    return h.hexdigest()


def hash_tree(root, paths):
    return {p: sha256_file(os.path.join(root, *p.split("/"))) for p in paths if os.path.isfile(os.path.join(root, *p.split("/")))}


def load_side(arg, paths):
    if os.path.isdir(arg):
        return hash_tree(arg, paths)
    d = json.load(open(arg, encoding="utf-8"))
    if "files" in d:
        d = {f["path"]: f["sha256"] for f in d["files"]}
    return d


def compare(a, b):
    """-> (same, only_a, only_b, different)"""
    same = sorted(p for p in a if p in b and a[p] == b[p])
    return same, sorted(set(a) - set(b)), sorted(set(b) - set(a)), sorted(p for p in a if p in b and a[p] != b[p])


def main(argv):
    key = next((a.split("=", 1)[1] for a in argv if a.startswith("--key=")), "p1-bookstore")
    args = [a for a in argv[1:] if not a.startswith("--key=")]
    if args[:1] == ["list"]:
        print("\n".join(bookstore_files(args[1] if len(args) > 1 else key)))
    elif args[:1] == ["hash"]:
        print(json.dumps(hash_tree(args[1], bookstore_files(key)), indent=1, sort_keys=True))
    elif args[:1] == ["compare"]:
        paths = None
        try:
            paths = bookstore_files(key)
        except Exception:        # no build tree / conv: compare what both sides hold
            pass
        a, b = load_side(args[1], paths or []), load_side(args[2], paths or [])
        same, oa, ob, diff = compare(a, b)
        print(f"same {len(same)}, only in A {len(oa)}, only in B {len(ob)}, different {len(diff)}")
        for p in oa:
            print("  only A:", p)
        for p in ob:
            print("  only B:", p)
        for p in diff:
            print("  DIFFERENT:", p)
        return 0 if not (oa or ob or diff) and same else 1
    else:
        print(__doc__)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
