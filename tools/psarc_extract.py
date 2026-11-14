"""Extract a plain Sony PSARC (e.g. TLOU1 PS3 build/main/*.psarc) for reference.

  python psarc_extract.py <file.psarc> <out_dir> [substring ...]   # only paths containing any substring

Handles NUL- or newline-separated manifests and MD5 over the path as stored, upper- or
lower-cased, with or without a leading '/'; zlib, lzma or Oodle ('oodl', e.g. TLOU Part I / Uncharted PC
archives - needs the game's own oo2core_*_win64.dll: set T2R_OODLE=<path to the dll>) or raw blocks.
DSAR-wrapped archives (TLOU2 PC) go through tools/part1/p1_archive.py instead.
"""
import hashlib
import lzma
import os
import struct
import sys
import zlib

_OODLE = []


def oodle_decompress(blk, usz):
    """One Oodle block (Kraken / Mermaid / ... - the dll picks) via the game's oo2core dll (T2R_OODLE)."""
    if not _OODLE:
        import ctypes
        dll = os.environ.get("T2R_OODLE")
        if not dll or not os.path.exists(dll):
            raise SystemExit("Oodle-compressed archive: set T2R_OODLE to the game's oo2core_*_win64.dll (read only)")
        lib = ctypes.WinDLL(dll)
        f = lib.OodleLZ_Decompress
        f.restype = ctypes.c_ssize_t
        f.argtypes = [ctypes.c_char_p, ctypes.c_ssize_t, ctypes.c_char_p, ctypes.c_ssize_t] + [ctypes.c_int] * 3 +                      [ctypes.c_void_p, ctypes.c_ssize_t, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_ssize_t, ctypes.c_int]
        _OODLE.append((ctypes, f))
    ctypes, f = _OODLE[0]
    out = ctypes.create_string_buffer(usz)
    n = f(blk, len(blk), out, usz, 1, 0, 0, None, 0, None, None, None, 0, 3)
    if n != usz:
        raise ValueError(f"OodleLZ_Decompress returned {n}, wanted {usz}")
    return out.raw


def decompress(comp, blk, want):
    """One PSARC block of `want` bytes (blocks of exactly `want` bytes are stored)."""
    if len(blk) == want:
        return blk
    if comp == b"zlib":
        return zlib.decompress(blk)
    if comp == b"lzma":
        return lzma.decompress(blk)
    if comp == b"oodl":
        return oodle_decompress(blk, want)
    raise ValueError(f"unknown PSARC compression {comp!r}")


def extract(path, out, subs=()):
    p = open(path, "rb").read()
    magic, vmaj, vmin, comp, toc_len, esz, n, bsize, flags = struct.unpack_from(">4sHH4sIIIII", p, 0)
    assert magic == b"PSAR", magic
    toc = []
    for i in range(n):
        e = p[32 + i * esz: 32 + (i + 1) * esz]
        toc.append((e[:16], int.from_bytes(e[16:20], "big"),
                    int.from_bytes(e[20:25], "big"), int.from_bytes(e[25:30], "big")))
    bt = 32 + n * esz
    width = 2 if bsize <= 0x10000 else (3 if bsize <= 0x1000000 else 4)
    nblk = (toc_len - bt) // width
    bs = [int.from_bytes(p[bt + i * width: bt + (i + 1) * width], "big") for i in range(nblk)]

    def data(bi, usz, off):
        outb = bytearray()
        while len(outb) < usz:
            cs = bs[bi] or bsize
            blk = p[off:off + cs]
            want = min(bsize, usz - len(outb))
            outb += decompress(comp, blk, want)
            off += cs
            bi += 1
        return bytes(outb)

    manifest = data(*toc[0][1:]).decode("latin1")
    names = [x for x in manifest.replace("\0", "\n").split("\n") if x]
    lookup = {}
    for nm in names:
        for v in {nm, nm.upper(), nm.lower(), "/" + nm, nm.lstrip("/"), nm.lstrip("/").upper()}:
            lookup[hashlib.md5(v.encode("latin1")).digest()] = nm
    got = 0
    for md5, bi, usz, off in toc[1:]:
        nm = lookup.get(md5, f"_unnamed/{md5.hex()}")
        if subs and not any(s in nm.lower() for s in subs):
            continue
        dst = os.path.join(out, nm.lstrip("/"))
        os.makedirs(os.path.dirname(dst) or out, exist_ok=True)
        open(dst, "wb").write(data(bi, usz, off))
        got += 1
    print(f"{path}: {n - 1} entries, {got} extracted -> {out}")
    return names


if __name__ == "__main__":
    extract(sys.argv[1], sys.argv[2], [s.lower() for s in sys.argv[3:]])
