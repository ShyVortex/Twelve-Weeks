"""List the files inside the game's DSAR-wrapped PSARC archives (build/pc/main/*.psarc) by
decompressing only the chunks holding the PSARC TOC and manifest.
  python dsar_list.py <archive.psarc>...      # prints '<archive>\t<path>\t<size>'
"""
import bisect, struct, sys, threading, zlib
import lz4.block


class Dsar:
    def __init__(self, path):
        self.f = open(path, "rb")
        h = self.f.read(0x28)
        magic, ver, n, data_start, total = struct.unpack_from("<4sIIIQ", h, 0)
        assert magic == b"DSAR", magic
        self.f.seek(0x28)
        d = self.f.read(n * 0x20)
        self.ent = [struct.unpack_from("<QII", d, i * 0x20) for i in range(n)]
        self.ustart, u = [], 0
        for off, usz, csz in self.ent:
            self.ustart.append(u); u += usz
        self.cache = {}
        self.lock = threading.Lock()

    def chunk(self, i):
        c = self.cache.get(i)
        if c is None:
            off, usz, csz = self.ent[i]
            with self.lock:                   # one shared file handle: seek+read must not interleave between threads (slim reads the game archive from a thread pool)
                self.f.seek(off); blk = self.f.read(csz)
            c = (b"\0" * usz if csz == 0 else blk if csz == usz
                 else lz4.block.decompress(blk, uncompressed_size=usz))
            self.cache[i] = c
        return c

    def read(self, pos, n):
        out = bytearray()
        i = bisect.bisect_right(self.ustart, pos) - 1
        while len(out) < n:
            c = self.chunk(i)
            a = pos + len(out) - self.ustart[i]
            out += c[a:a + n - len(out)]
            i += 1
        return bytes(out)


def listing(path):
    d = Dsar(path)
    magic, vmaj, vmin, comp, toc_len, esz, n, bsize, flags = struct.unpack(">4sHH4sIIIII", d.read(0, 32))
    assert magic == b"PSAR", magic
    toc_raw = d.read(0, toc_len)
    toc = [(int.from_bytes(toc_raw[32 + i * 30 + 16:32 + i * 30 + 20], "big"),
            int.from_bytes(toc_raw[32 + i * 30 + 20:32 + i * 30 + 25], "big"),
            int.from_bytes(toc_raw[32 + i * 30 + 25:32 + i * 30 + 30], "big")) for i in range(n)]
    bt = 32 + n * 30
    bsizes = struct.unpack_from(f">{(toc_len - bt) // 2}H", toc_raw, bt)
    bi, usz, off = toc[0]
    out = bytearray()
    while len(out) < usz:
        cs = bsizes[bi] or bsize
        blk = d.read(off, cs)
        want = min(bsize, usz - len(out))
        out += blk if cs == want else zlib.decompress(blk)
        off += cs; bi += 1
    paths = [p for p in out.decode(errors="replace").split("\0") if p]
    import hashlib
    sizes = {}
    by_md5 = {hashlib.md5(p.encode()).digest(): p for p in paths}
    for i in range(1, n):
        md5 = toc_raw[32 + i * 30:32 + i * 30 + 16]
        if md5 in by_md5: sizes[by_md5[md5]] = toc[i][1]
    return [(p, sizes.get(p, -1)) for p in paths]


if __name__ == "__main__":
    for a in sys.argv[1:]:
        try:
            for p, s in listing(a):
                print(f"{a.split('/')[-1]}\t{p}\t{s}")
        except Exception as e:
            print(f"{a}\tERROR {e}", file=sys.stderr)


def open_files(path):
    """(dsar, {path: (block idx, size, offset)}, bsizes, bsize) for extract()."""
    import hashlib
    d = Dsar(path)
    magic, vmaj, vmin, comp, toc_len, esz, n, bsize, flags = struct.unpack(">4sHH4sIIIII", d.read(0, 32))
    toc_raw = d.read(0, toc_len)
    bt = 32 + n * 30
    bsizes = struct.unpack_from(f">{(toc_len - bt) // 2}H", toc_raw, bt)
    paths = [p for p, _ in listing(path)]
    by_md5 = {hashlib.md5(p.encode()).digest(): p for p in paths}
    ent = {}
    for i in range(1, n):
        e = toc_raw[32 + i * 30:32 + (i + 1) * 30]
        if e[:16] in by_md5:
            ent[by_md5[e[:16]]] = (int.from_bytes(e[16:20], "big"), int.from_bytes(e[20:25], "big"), int.from_bytes(e[25:30], "big"))
    return d, ent, bsizes, bsize


def extract(d, ent, bsizes, bsize, p):
    bi, usz, off = ent[p]
    out = bytearray()
    while len(out) < usz:
        cs = bsizes[bi] or bsize
        blk = d.read(off, cs)
        want = min(bsize, usz - len(out))
        out += blk if cs == want else zlib.decompress(blk)
        off += cs; bi += 1
        if len(d.cache) > 64: d.cache.clear()
    return bytes(out)
