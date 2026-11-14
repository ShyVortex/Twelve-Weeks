"""Read-only archive probe for TLOU Part I PC (and TLOU2 PC for comparison): day-one inventory, listing,
extraction and header comparison. Plan: re/part1/porting-plan.md section 7.

  python p1_archive.py inventory <game dir> [out.tsv]       # every build/pc/main/*.psarc: container (DSAR / PSAR),
                                                           # DSAR chunk tags, PSARC version / compression / block size
                                                           # / entry count -> re/part1/archives-<game>.tsv
  python p1_archive.py list <archive>... > files.tsv        # '<archive>\t<path>\t<size>' (as re/game-files.tsv)
  python p1_archive.py extract <archive> <out dir> [substring ...]
  python p1_archive.py hdr <file> [<file> ...]              # first 0x60 bytes as u32 / u64 + ascii, side by side
                                                           # (a Part I pak vs a TLOU2 pak, a Part I DC vs a TLOU2 DC)

Containers handled:
  DSAR  (TLOU2 PC: header 0x28, entries 0x20 {u64 off, u32 usize, u32 csize, u64 tag, u64 uend}) wrapping a PSARC.
        Chunk codec by tag: csize == usize stored, csize == 0 zeros, tag low byte 0x03 / 0x04 lz4 (TLOU2); any other
        tag is tried as lz4, then Oodle (T2R_OODLE), and reported if neither works - that IS the day-one finding.
  PSAR  plain Sony PSARC (big endian TOC, blocks zlib / lzma / oodl / stored) - psarc_extract.decompress.
Oodle needs the game's own oo2core_*_win64.dll: T2R_OODLE=<path>. Nothing is ever written next to the game.
"""
import bisect
import hashlib
import os
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.dirname(HERE)
ROOT = os.path.dirname(TOOLS)
sys.path.insert(0, TOOLS)
import psarc_extract  # noqa: E402


def find_oodle(path):
    """T2R_OODLE default: the oo2core_*_win64.dll that sits in the game dir (<game>/build/pc/main/x.psarc -> <game>).
    The dll is only loaded (read), never written; set T2R_OODLE yourself to use a copy instead."""
    if os.environ.get("T2R_OODLE"):
        return
    d = os.path.abspath(path)
    for _ in range(5):
        d = os.path.dirname(d)
        try:
            for fn in os.listdir(d):
                if fn.lower().startswith("oo2core") and fn.lower().endswith("_win64.dll"):
                    os.environ["T2R_OODLE"] = os.path.join(d, fn)
                    return
        except OSError:
            return


def _lz4(blk, usz):
    import lz4.block
    return lz4.block.decompress(blk, uncompressed_size=usz)


class Dsar:
    """Random access over the uncompressed bytes of a DSAR file."""
    def __init__(self, path):
        self.f = open(path, "rb")
        h = self.f.read(0x28)
        magic, self.ver, n, self.data_start, self.total = struct.unpack_from("<4sIIIQ", h, 0)
        assert magic == b"DSAR", magic
        d = self.f.read(n * 0x20)
        self.ent = [struct.unpack_from("<QIIQ", d, i * 0x20) for i in range(n)]
        self.ustart, u = [], 0
        for off, usz, csz, tag in self.ent:
            self.ustart.append(u)
            u += usz
        self.cache, self.codec = {}, {}

    def tags(self):
        out = {}
        for off, usz, csz, tag in self.ent:
            k = "stored" if csz == usz else "zero" if csz == 0 else "%016x" % tag
            out[k] = out.get(k, 0) + 1
        return out

    def chunk(self, i):
        if i in self.cache:
            return self.cache[i]
        off, usz, csz, tag = self.ent[i]
        self.f.seek(off)
        blk = self.f.read(csz)
        if csz == 0:
            out = b"\0" * usz
        elif csz == usz:
            out = blk
        else:
            out = None
            order = [self.codec[tag]] if tag in self.codec else ["lz4", "oodle"]
            for c in order:
                try:
                    out = _lz4(blk, usz) if c == "lz4" else psarc_extract.oodle_decompress(blk, usz)
                    if len(out) == usz:
                        self.codec[tag] = c
                        break
                    out = None
                except (Exception, SystemExit):
                    out = None
            if out is None:
                raise ValueError(f"DSAR chunk {i}: tag {tag:016x} is neither lz4 nor Oodle (set T2R_OODLE?)")
        if len(self.cache) > 64:
            self.cache.clear()
        self.cache[i] = out
        return out

    def read(self, pos, n):
        out = bytearray()
        i = bisect.bisect_right(self.ustart, pos) - 1
        while len(out) < n and i < len(self.ent):
            c = self.chunk(i)
            a = pos + len(out) - self.ustart[i]
            out += c[a:a + n - len(out)]
            i += 1
        return bytes(out)


class Plain:
    def __init__(self, path):
        self.f = open(path, "rb")
        self.total = os.path.getsize(path)

    def read(self, pos, n):
        self.f.seek(pos)
        return self.f.read(n)


def open_any(path):
    with open(path, "rb") as f:
        m = f.read(4)
    return Dsar(path) if m == b"DSAR" else Plain(path)


class Psarc:
    def __init__(self, path):
        self.path = path
        find_oodle(path)
        self._pre = {}
        self.src = open_any(path)
        hd = self.src.read(0, 32)
        (self.magic, self.vmaj, self.vmin, self.comp, toc_len, self.esz, n, self.bsize,
         self.flags) = struct.unpack(">4sHH4sIIIII", hd)
        if self.magic != b"PSAR":
            raise ValueError(f"{path}: inner magic {self.magic!r}, not a PSARC")
        raw = self.src.read(0, toc_len)
        esz = self.esz
        self.toc = [(raw[32 + i * esz:32 + i * esz + 16], int.from_bytes(raw[32 + i * esz + 16:32 + i * esz + 20], "big"),
                     int.from_bytes(raw[32 + i * esz + 20:32 + i * esz + 25], "big"),
                     int.from_bytes(raw[32 + i * esz + 25:32 + i * esz + 30], "big")) for i in range(n)]
        bt = 32 + n * esz
        w = 2 if self.bsize <= 0x10000 else (3 if self.bsize <= 0x1000000 else 4)
        self.bs = [int.from_bytes(raw[bt + i * w:bt + (i + 1) * w], "big") for i in range((toc_len - bt) // w)]
        man = self.file(*self.toc[0][1:]).decode("latin1")
        self.names = [x for x in man.replace("\0", "\n").split("\n") if x]
        look = {}
        for nm in self.names:
            for v in {nm, nm.lower(), nm.upper(), "/" + nm, nm.lstrip("/")}:
                look[hashlib.md5(v.encode("latin1")).digest()] = nm
        self.ent = {}
        for md5, bi, usz, off in self.toc[1:]:
            self.ent[look.get(md5, "_unnamed/" + md5.hex())] = (bi, usz, off)

    def file(self, bi, usz, off):
        out = bytearray()
        while len(out) < usz:
            cs = self.bs[bi] or self.bsize
            want = min(self.bsize, usz - len(out))
            out += psarc_extract.decompress(self.comp, self.src.read(off, cs), want)
            off += cs
            bi += 1
        return bytes(out)

    def get(self, name):
        return self.file(*self.ent[name])

    def read_range(self, name, pos, n):
        """bytes [pos, pos+n) of one entry without decompressing the rest (block table prefix sums, cached)"""
        bi, usz, off = self.ent[name]
        n = max(0, min(n, usz - pos))
        pre = self._pre.get(name)
        if pre is None:
            nblk = (usz + self.bsize - 1) // self.bsize
            pre, o = [], off
            for j in range(nblk):
                pre.append(o)
                o += self.bs[bi + j] or self.bsize
            self._pre[name] = pre
        out = bytearray()
        k = pos // self.bsize
        a = pos - k * self.bsize
        while len(out) < n + a and k < len(pre):
            cs = self.bs[bi + k] or self.bsize
            want = min(self.bsize, usz - k * self.bsize)
            out += psarc_extract.decompress(self.comp, self.src.read(pre[k], cs), want)
            k += 1
        return bytes(out[a:a + n])


def inventory(game, out=None):
    main = os.path.join(game, "build", "pc", "main")
    find_oodle(main)
    rows = ["archive\tbytes\tcontainer\tdsar_tags\tpsarc_ver\tcomp\tblock\tentries\tfirst_dirs"]
    for fn in sorted(os.listdir(main)):
        if not fn.endswith(".psarc"):
            continue
        p = os.path.join(main, fn)
        try:
            src = open_any(p)
            tags = ",".join(f"{k}:{v}" for k, v in sorted(src.tags().items())) if isinstance(src, Dsar) else "-"
            a = Psarc(p)
            dirs = sorted({n.lstrip("/").split("/")[0] for n in a.names})
            rows.append(f"{fn}\t{os.path.getsize(p)}\t{'DSAR' if isinstance(src, Dsar) else 'PSAR'}\t{tags}\t"
                        f"{a.vmaj}.{a.vmin}\t{a.comp.decode('latin1')}\t{a.bsize}\t{len(a.names)}\t{' '.join(dirs[:8])}")
        except Exception as e:
            rows.append(f"{fn}\t{os.path.getsize(p)}\tERROR {e}")
        print(rows[-1], flush=True)
    if out:
        os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
        open(out, "w", encoding="utf-8").write("\n".join(rows) + "\n")


def hdr(paths):
    blobs = []
    for p in paths:
        if "::" in p:                          # archive::inner/path
            a, inner = p.split("::", 1)
            blobs.append(Psarc(a).get(inner)[:0x60])
        else:
            blobs.append(open(p, "rb").read(0x60))
    print("off  " + "  ".join(os.path.basename(p)[-34:].rjust(34) for p in paths))
    for o in range(0, 0x60, 8):
        cells = []
        for b in blobs:
            q = b[o:o + 8].ljust(8, b"\0")
            lo, hi = struct.unpack("<II", q)
            asc = "".join(chr(c) if 32 <= c < 127 else "." for c in q)
            cells.append(f"{lo:08x} {hi:08x} {asc}".rjust(34))
        print(f"{o:03x}  " + "  ".join(cells))


def main(argv):
    if len(argv) < 2:
        print(__doc__)
        return 1
    cmd = argv[1]
    if cmd == "inventory":
        game = argv[2]
        out = argv[3] if len(argv) > 3 else os.path.join(ROOT, "re", "part1",
                                                       "archives-%s.tsv" % os.path.basename(game.rstrip("/\\")).replace(" ", "_"))
        inventory(game, out)
    elif cmd == "list":
        for p in argv[2:]:
            a = Psarc(p)
            for nm, (bi, usz, off) in sorted(a.ent.items()):
                print(f"{os.path.basename(p)}\t{nm.lstrip('/')}\t{usz}")
    elif cmd == "extract":
        a = Psarc(argv[2])
        subs = [s.lower() for s in argv[4:]]
        got = 0
        for nm in a.ent:
            if subs and not any(s in nm.lower() for s in subs):
                continue
            dst = os.path.join(argv[3], nm.lstrip("/"))
            os.makedirs(os.path.dirname(dst) or argv[3], exist_ok=True)
            open(dst, "wb").write(a.get(nm))
            got += 1
        print(f"{argv[2]}: {got} files -> {argv[3]}")
    elif cmd == "hdr":
        hdr(argv[2:])
    else:
        print(__doc__)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
