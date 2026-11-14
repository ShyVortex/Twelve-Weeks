"""Measure a candidate Part I map: which paks, raw sizes, referenced textures, and (optionally) real compression.

  python p1_mapstudy.py index  <game dir> [out.tsv]          # texture-dict index: hash -> dict pak, payload range,
                                                            # format, size (ranged header reads, ~2 min for all dicts)
  python p1_mapstudy.py study  <game dir> <name> <level>...  # extract the levels' paks to re/part1/x/maps/<name>/,
                                                            # sum sizes, collect VRAM hashes, look them up in the index
  python p1_mapstudy.py actors <game dir> <actor name>...   # weapon / actor paks: size, tris, texture bytes (extracts to x/actors)
  python p1_mapstudy.py texbin <game dir> <name>            # write the referenced textures' payloads to
                                                            # re/part1/x/maps/<name>/tex.bin (+ tex.tsv)
Env: T2R_OODLE = path to a COPY of Part I's oo2core_9_win64.dll; T2R_REPO = main repo (default: this checkout, or the main one when run from a worktree).
Everything is read-only on <game dir>.  Output lives under re/part1 (git-ignored) - never commit it.
"""
import collections
import json
import os
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import p1_archive  # noqa: E402
import p1_pak  # noqa: E402

# the main checkout keeps the (untracked) game data; a git worktree finds it through the main checkout
_ROOT = os.path.dirname(os.path.dirname(HERE))
REPO = os.environ.get("T2R_REPO", _ROOT.split(os.sep + ".claude" + os.sep)[0])
P1DIR = os.path.join(REPO, "re", "part1")
INDEX = os.path.join(P1DIR, "texdict-index.tsv")
FILES = os.path.join(P1DIR, "game-files.tsv")
DXGI = {71: "BC1", 72: "BC1s", 74: "BC2", 77: "BC3", 80: "BC4", 83: "BC5", 98: "BC7", 99: "BC7s", 28: "RGBA8", 61: "R8"}

_arcs = {}


def arc(game, name):
    if name not in _arcs:
        _arcs[name] = p1_archive.Psarc(os.path.join(game, "build", "pc", "main", name))
    return _arcs[name]


def dict_header(a, path):
    """P1Pak over the descriptor region of a texture dictionary + payload base offset"""
    h = a.read_range(path, 0, 0x1000)
    n, pt = struct.unpack_from("<II", h, 16)
    end = 0
    for i in range(n):
        s, z, _ = struct.unpack_from("<III", h, pt + 12 * i)
        end = max(end, s + z)
    data = a.read_range(path, 0, end)
    return p1_pak.P1Pak(path, data), end


def build_index(game, out=INDEX):
    rows = []
    for line in open(FILES, encoding="utf-8"):
        p = line.rstrip("\n").split("\t")
        if len(p) == 3 and p[1].startswith("texturedict3/") and p[1].endswith(".pak"):
            a = arc(game, p[0])
            pk, base = dict_header(a, p[1])
            pg, off = pk.of_type("TEXTURE_DICTIONARY")[0]
            ad = pk.pages[pg][0] + off
            n, lst = pk.u32(ad + p1_pak.PAD), pk.ptr(ad + p1_pak.PAD + 24)
            cnt = 0
            for i in range(n):
                dp = pk.fix.get(lst + 8 * i)
                if dp is None:
                    continue
                v = pk.pages[dp][0] + pk.u64(lst + 8 * i) - 32
                u = lambda o: pk.u32(v + o)
                rows.append((pk.u64(v + 0x38), p[0], p[1], base + u(0x28), u(0x30), u(0x48), u(0x54), u(0x58), u(0x50)))
                cnt += 1
            print(f"{p[0]} {p[1]}: {cnt} textures, payload base {base:#x}, file {int(p[2])} bytes", flush=True)
    with open(out, "w", encoding="utf-8") as f:
        f.write("hash\tarchive\tdict\toffset\tsize\tdxgi\tw\th\tmips\n")
        for r in rows:
            f.write("%016x\t%s\t%s\t%d\t%d\t%d\t%d\t%d\t%d\n" % r)
    print(len(rows), "textures indexed ->", out)


def load_index():
    idx = {}
    for i, line in enumerate(open(INDEX, encoding="utf-8")):
        if i == 0:
            continue
        p = line.rstrip("\n").split("\t")
        idx.setdefault(int(p[0], 16), []).append((p[1], p[2], int(p[3]), int(p[4]), int(p[5]), int(p[6]), int(p[7]), int(p[8])))
    return idx


def where(levels):
    want = {}
    for lv in levels:
        for suf in ("", "-phys", "-ingame"):
            want[f"pak68/{lv}{suf}.pak"] = lv
    found = {}
    for line in open(FILES, encoding="utf-8"):
        p = line.rstrip("\n").split("\t")
        if len(p) == 3 and p[1] in want:
            found.setdefault(p[1], []).append((p[0], int(p[2])))
    return found


def study(game, name, levels):
    out = os.path.join(P1DIR, "x", "maps", name)
    os.makedirs(out, exist_ok=True)
    found = where(levels)
    hashes, tot = {}, collections.Counter()
    verts = tris = 0
    for path, hits in sorted(found.items()):
        a_name, size = hits[0]
        kind = "phys" if path.endswith("-phys.pak") else "ingame" if path.endswith("-ingame.pak") else "geo"
        tot[kind] += size
        dst = os.path.join(out, path)
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        data = arc(game, a_name).get(path)
        open(dst, "wb").write(data)
        try:
            pk = p1_pak.P1Pak(dst, data)
            for h, src in pk.tex_hashes.items():
                hashes[h] = src
            if kind == "geo":
                sm = pk.submeshes
                verts += sum(s["vcount"] for s in sm)
                tris += sum(s["icount"] for s in sm) // 3
        except Exception as e:
            print("  parse failed", path, repr(e))
    print(f"{name}: {len(found)} paks; raw MB geo {tot['geo'] / 1e6:.1f} phys {tot['phys'] / 1e6:.1f} "
          f"ingame {tot['ingame'] / 1e6:.1f}; verts {verts}, tris {tris}; texture refs {len(hashes)}")
    res = {"name": name, "levels": levels, "geo": tot["geo"], "phys": tot["phys"], "ingame": tot["ingame"],
           "verts": verts, "tris": tris, "refs": len(hashes)}
    if os.path.exists(INDEX):
        idx = load_index()
        miss = [h for h in hashes if h not in idx]
        fmts, total, by_arc = collections.Counter(), 0, collections.Counter()
        dims = collections.Counter()
        picked = {}
        for h in hashes:
            if h in idx:
                picked[h] = idx[h][0]
        for h, (a_name, dpath, off, sz, fmt, w, hh, mips) in picked.items():
            total += sz
            fmts[DXGI.get(fmt, str(fmt))] += sz
            by_arc[a_name] += sz
            dims[max(w, hh)] += 1
        print(f"  textures found {len(picked)}/{len(hashes)} (missing {len(miss)}); payload MB all mips {total / 1e6:.1f}")
        print("  by format MB:", {k: round(v / 1e6, 1) for k, v in fmts.items()})
        print("  by dict archive MB:", {k: round(v / 1e6, 1) for k, v in by_arc.items()})
        print("  max-dimension histogram:", dict(sorted(dims.items())))
        # size if the top mip is dropped: top mip is ~ 3/4 of a chain
        res.update(tex_found=len(picked), tex_missing=len(miss), tex_bytes=total,
                   tex_fmt={k: v for k, v in fmts.items()}, tex_arc=dict(by_arc))
        with open(os.path.join(out, "textures.tsv"), "w") as f:
            for h, (a_name, dpath, off, sz, fmt, w, hh, mips) in sorted(picked.items()):
                f.write("%016x\t%s\t%s\t%d\t%d\t%d\t%d\t%d\t%d\t%s\n" % (h, a_name, dpath, off, sz, fmt, w, hh, mips, hashes[h]))
    json.dump(res, open(os.path.join(out, "study.json"), "w"), indent=1)


def texbin(game, name):
    out = os.path.join(P1DIR, "x", "maps", name)
    n = 0
    with open(os.path.join(out, "tex.bin"), "wb") as f:
        for line in open(os.path.join(out, "textures.tsv")):
            p = line.rstrip("\n").split("\t")
            f.write(arc(game, p[1]).read_range(p[2], int(p[3]), int(p[4])))
            n += 1
    print(n, "textures ->", os.path.join(out, "tex.bin"), os.path.getsize(os.path.join(out, "tex.bin")))


def actors(game, names):
    """actor paks (weapons etc.): pak size, submeshes, tris, referenced texture payload bytes (needs the dict index)"""
    idx = load_index() if os.path.exists(INDEX) else {}
    out = os.path.join(P1DIR, "x", "actors")
    os.makedirs(out, exist_ok=True)
    hits = {}
    for line in open(FILES, encoding="utf-8"):
        p = line.rstrip("\n").split("\t")
        if len(p) == 3 and p[1].startswith("actor97/"):
            hits.setdefault(p[1][8:-4], []).append(p[0])
    for nm in names:
        for a_name in hits.get(nm, []):
            data = arc(game, a_name).get(f"actor97/{nm}.pak")
            open(os.path.join(out, nm + ".pak"), "wb").write(data)
            pk = p1_pak.P1Pak(nm, data)
            sm = pk.submeshes
            th = pk.tex_hashes
            tb = sum(idx[h][0][3] for h in th if h in idx)
            print(f"{nm:44s} {a_name:18s} pak {len(data) / 1e6:6.2f} MB  submeshes {len(sm):3d}  tris {sum(s['icount'] for s in sm) // 3:6d}"
                  f"  textures {len(th):3d} ({sum(1 for h in th if h in idx)} indexed, {tb / 1e6:6.1f} MB all mips)")
        if nm not in hits:
            print(f"{nm}: not found")


def main(argv):
    if len(argv) < 3:
        print(__doc__)
        return 1
    cmd, game = argv[1], argv[2]
    if cmd == "index":
        build_index(game, argv[3] if len(argv) > 3 else INDEX)
    elif cmd == "study":
        study(game, argv[3], argv[4:])
    elif cmd == "actors":
        actors(game, argv[3:])
    elif cmd == "texbin":
        texbin(game, argv[3])
    else:
        print(__doc__)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
