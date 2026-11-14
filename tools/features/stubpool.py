"""Reserved, zero-filled executable stub pool section `.t2rstub` in winmm (re/stub-pool-1103.md).

The ext's hooks need stubs/caves within rel32 reach of winmm code. With a ~1.75 GB image the address space within +-2 GB
of the module is fully taken, so VirtualAlloc-near found nothing (night36, 18 HOOK FAILs). A section inside the image is
always in reach. Virtual-only (raw size 0, zero-filled by the loader), RWX; the ext finds it by section name."""
import struct, sys

NAME = b".t2rstub"
POOL_SIZE = 0x400000        # 4 MB; the ext reports 'stub pool: used X of Y' at boot (measured use well under 0x40000)


def add(data, size=POOL_SIZE):
    d = bytearray(data)
    pe = struct.unpack_from("<I", d, 0x3C)[0]
    assert d[pe:pe + 4] == b"PE\0\0"
    nsec = struct.unpack_from("<H", d, pe + 6)[0]
    optsz = struct.unpack_from("<H", d, pe + 20)[0]
    opt = pe + 24
    soi = struct.unpack_from("<I", d, opt + 56)[0]
    soh = struct.unpack_from("<I", d, opt + 60)[0]
    sa = struct.unpack_from("<I", d, opt + 32)[0]
    tab = opt + optsz
    for i in range(nsec):
        if bytes(d[tab + 40 * i:tab + 40 * i + 8]).rstrip(b"\0") == NAME:
            raise SystemExit("stub pool already present")
    so = tab + 40 * nsec
    if so + 40 > soh:
        raise SystemExit("stubpool: no room for another section header")
    rva = (soi + sa - 1) // sa * sa
    vsize = (size + sa - 1) // sa * sa
    # raw size/pointer 0: uninitialised data, but executable + readable + writable (0x80 | 0x20000000 | 0x40000000 | 0x80000000)
    d[so:so + 40] = struct.pack("<8sIIIIIIHHI", NAME, vsize, rva, 0, 0, 0, 0, 0, 0, 0xE0000080)
    struct.pack_into("<H", d, pe + 6, nsec + 1)
    struct.pack_into("<I", d, opt + 56, rva + vsize)
    return bytes(d), rva, vsize


def check(data):
    """Build check: the section exists with the right size and lies inside SizeOfImage."""
    pe = struct.unpack_from("<I", data, 0x3C)[0]
    nsec = struct.unpack_from("<H", data, pe + 6)[0]
    optsz = struct.unpack_from("<H", data, pe + 20)[0]
    soi = struct.unpack_from("<I", data, pe + 24 + 56)[0]
    tab = pe + 24 + optsz
    for i in range(nsec):
        n, vs, va = struct.unpack_from("<8sII", data, tab + 40 * i)
        if n.rstrip(b"\0") == NAME:
            ch = struct.unpack_from("<I", data, tab + 40 * i + 36)[0]
            if vs < 0x100000 or va + vs > soi or (ch & 0xE0000000) != 0xE0000000:
                raise SystemExit(f"stubpool: bad section {va:#x} {vs:#x} {ch:#x} soi {soi:#x}")
            return va, vs
    raise SystemExit("stubpool: .t2rstub section missing from winmm - the ext cannot place its stubs")


if __name__ == "__main__":
    out, rva, vs = add(open(sys.argv[1], "rb").read())
    open(sys.argv[2], "wb").write(out)
    print(f"{sys.argv[2]}: .t2rstub rva {rva:#x} size {vs:#x}")
