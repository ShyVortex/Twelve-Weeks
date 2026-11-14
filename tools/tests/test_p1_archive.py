"""Offline test of tools/part1/p1_archive.py on synthetic archives: a DSAR-wrapped PSARC (as TLOU2 PC / the mod blob,
built with t2r_pack) and plain PSARCs with zlib and lzma blocks (as TLOU1 PS3 / possibly Part I PC).
Run with tools/win/.venv (lz4, numpy, pefile): python tools/tests/test_p1_archive.py"""
import hashlib, lzma, os, struct, sys, tempfile, zlib
import sys as _t2s, os as _t2o; _t2s.path.append(_t2o.path.normpath(_t2o.path.join(_t2o.path.dirname(_t2o.path.abspath(__file__)), ".."))); import t2rtmp  # noqa: E402,F401  (temp hygiene: tools/t2rtmp.py)

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.dirname(HERE)
sys.path.insert(0, TOOLS)
sys.path.insert(0, os.path.join(TOOLS, "part1"))
import t2r_pack  # noqa: E402
import p1_archive  # noqa: E402

FAILS = []
def check(cond, what):
    print(("ok   " if cond else "FAIL ") + what)
    if not cond:
        FAILS.append(what)

files = {"pak68/a-level.pak": os.urandom(5000) + b"x" * 200000, "dc1/test.bin": b"00CD" + bytes(100),
         "texturedict3/d.pak": bytes(range(256)) * 1000}
tmp = tempfile.mkdtemp()

# DSAR(lz4) around a PSARC with raw blocks (t2r_pack, = the stock TLOU2 layout)
meta = {"flags": 0, "paths": sorted(files), "data_order": sorted(files), "trail": False}
ps, cuts = t2r_pack.psarc_write(meta, files)
dsar = t2r_pack.dsar_write(ps, cuts)
dsar = dsar[0] if isinstance(dsar, tuple) else dsar
p = os.path.join(tmp, "t2.psarc"); open(p, "wb").write(dsar)
a = p1_archive.Psarc(p)
check(isinstance(a.src, p1_archive.Dsar), "DSAR detected")
check(all(a.get(k) == v for k, v in files.items()), "DSAR+PSARC: every file reads back")
check(set(a.src.tags()) <= {"5555555555555503", "stored", "zero"}, "DSAR tags reported: %s" % a.src.tags())

def plain_psarc(comp, enc):
    """A plain PSARC with compressed 64 KiB blocks (manifest first, NUL separated)."""
    names = sorted(files)
    man = "\0".join(names).encode()
    order = [man] + [files[n] for n in names]
    blocks, bsz, ents = [], [], []
    bi = 0
    for data in order:
        nb = 0
        for i in range(0, max(len(data), 1), 0x10000):
            c = enc(data[i:i + 0x10000])
            raw = data[i:i + 0x10000]
            blk = c if len(c) < len(raw) else raw
            blocks.append(blk); bsz.append(len(blk) if len(blk) < 0x10000 else 0); nb += 1
        ents.append((bi, len(data))); bi += nb
    n = len(order)
    toc_len = 32 + n * 30 + 2 * len(bsz)
    offs, off, k = [], toc_len, 0
    for (b0, usz) in ents:
        offs.append(off)
        cnt = (max(usz, 1) + 0xffff) // 0x10000
        off += sum(len(x) for x in blocks[k:k + cnt]); k += cnt
    md5s = [b"\0" * 16] + [hashlib.md5(nm.encode()).digest() for nm in names]
    toc = b"".join(m + e[0].to_bytes(4, "big") + e[1].to_bytes(5, "big") + o.to_bytes(5, "big") for m, e, o in zip(md5s, ents, offs))
    head = struct.pack(">4sHH4sIIIII", b"PSAR", 1, 4, comp, toc_len, 30, n, 0x10000, 0)
    return head + toc + struct.pack(">%dH" % len(bsz), *bsz) + b"".join(blocks)

for comp, enc in ((b"zlib", zlib.compress), (b"lzma", lambda d: lzma.compress(d, format=lzma.FORMAT_ALONE))):
    p = os.path.join(tmp, "plain-%s.psarc" % comp.decode()); open(p, "wb").write(plain_psarc(comp, enc))
    a = p1_archive.Psarc(p)
    check(isinstance(a.src, p1_archive.Plain) and a.comp == comp, "plain PSARC (%s) detected" % comp.decode())
    check(all(a.get(k) == v for k, v in files.items()), "plain PSARC (%s): every file reads back" % comp.decode())

os.makedirs(os.path.join(tmp, "g", "build", "pc", "main"))
for fn in ("t2.psarc", "plain-zlib.psarc"):
    os.replace(os.path.join(tmp, fn), os.path.join(tmp, "g", "build", "pc", "main", fn))
out = os.path.join(tmp, "inv.tsv")
p1_archive.inventory(os.path.join(tmp, "g"), out)
rows = open(out).read().splitlines()
check(len(rows) == 3 and "DSAR" in rows[2] and "PSAR\t-\t1.4\tzlib" in rows[1], "inventory rows")

print("\n%d FAILED" % len(FAILS) if FAILS else "\nall passed")
sys.exit(1 if FAILS else 0)
