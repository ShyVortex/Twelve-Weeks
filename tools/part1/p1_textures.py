"""Full-resolution Part I textures by VRAM hash, with the top mips optionally dropped (read-only on the Part I install).

Part I keeps full-res textures in per-world `texturedict3/*-dict.pak` files; a level pak only carries a 64x64 stub per texture in
its trailer.  `re/part1/texdict-index.tsv` (p1_mapstudy.py index) maps hash -> dict pak, payload range, format, size.
Payload layout (identical in dicts and in pak trailers): mips top to bottom, each row padded to 256 bytes, each mip start aligned
to 512 bytes; BC formats store 4x4 blocks.

    T = P1Textures(game_dir); t = T.get(hash, drop=1) -> dict(fmt, w, h, mips, data) or None
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import p1_archive  # noqa: E402

MAIN = os.environ.get("T2R_MAIN_ROOT", os.path.dirname(os.path.dirname(HERE)).split(os.sep + ".claude" + os.sep)[0])
INDEX = os.path.join(MAIN, "re", "part1", "texdict-index.tsv")
BLOCK_BYTES = {71: 8, 72: 8, 80: 8, 81: 8, 74: 16, 75: 16, 77: 16, 78: 16, 83: 16, 84: 16, 95: 16, 96: 16, 98: 16, 99: 16}
RAW_BYTES = {28: 4, 29: 4, 61: 1, 49: 2}


def align(v, a):
    return (v + a - 1) // a * a


def mip_layout(fmt, w, h, mips):
    """-> [(offset, size)] per mip of a payload"""
    out, off = [], 0
    for l in range(mips):
        lw, lh = max(1, w >> l), max(1, h >> l)
        if fmt in BLOCK_BYTES:
            rb = max(1, (lw + 3) // 4) * BLOCK_BYTES[fmt]
            rows = max(1, (lh + 3) // 4)
        else:
            rb, rows = lw * RAW_BYTES[fmt], lh
        size = rows * align(rb, 256)
        out.append((off, size))
        off = align(off + size, 512)
    return out


class P1Textures:
    def __init__(self, game):
        self.game = game
        if not os.path.exists(INDEX):
            raise SystemExit(f"{INDEX} missing: python tools/part1/p1_mapstudy.py index <Part I dir>")
        self.idx = {}
        for i, line in enumerate(open(INDEX, encoding="utf-8")):
            if i:
                p = line.rstrip("\n").split("\t")
                self.idx.setdefault(int(p[0], 16), (p[1], p[2], int(p[3]), int(p[4]), int(p[5]), int(p[6]), int(p[7]), int(p[8])))
        self._arc = {}

    def has(self, h):
        return h in self.idx

    def get(self, h, drop=0):
        e = self.idx.get(h)
        if e is None or (e[4] not in BLOCK_BYTES and e[4] not in RAW_BYTES):
            return None
        arc, dpath, off, size, fmt, w, hh, mips = e
        lay = mip_layout(fmt, w, hh, mips)
        plain = align(lay[-1][0] + lay[-1][1], 512) == size or lay[-1][0] + lay[-1][1] == size
        drop = max(0, min(drop, mips - 1)) if plain else 0      # cubemaps / arrays / volumes keep every mip
        if not plain:
            lay = [(0, size)]
        if arc not in self._arc:
            self._arc[arc] = p1_archive.Psarc(os.path.join(self.game, "build", "pc", "main", arc))
        start = lay[drop][0]
        end = lay[-1][0] + lay[-1][1]
        data = self._arc[arc].read_range(dpath, off + start, end - start)
        return {"fmt": fmt, "w": max(1, w >> drop), "h": max(1, hh >> drop), "mips": mips - drop, "data": data}


def pack_size(index_rows, drop):
    """bytes of the payloads of the given hashes after dropping `drop` mips (for the size tables)"""
    tot = 0
    for fmt, w, h, mips, size in index_rows:
        lay = mip_layout(fmt, w, h, mips)
        end = lay[-1][0] + lay[-1][1]
        plain = align(end, 512) == size or end == size
        tot += end - lay[max(0, min(drop, mips - 1))][0] if plain else size
    return tot
