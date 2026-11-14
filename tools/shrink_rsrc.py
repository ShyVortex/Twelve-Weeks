"""Shrink the RAW (file) size of .rsrc: the original RCDATA 1001 mod blob in there is dead (zeroed; the live blob is
in .t2rc). The virtual layout is untouched (VirtualSize keeps the zero-filled tail; the loader zero-fills
VirtualSize > SizeOfRawData), so no RVA, reloc, SizeOfImage, data directory or code constant changes. Only: the live
resource data (manifest) moves right behind the resource directory, .rsrc SizeOfRawData shrinks, and
PointerToRawData of the sections after .rsrc moves down. Idempotent."""
import struct, sys
import pefile


def shrink(data):
    pe = pefile.PE(data=bytes(data), fast_load=True)
    pe.parse_data_directories([pefile.DIRECTORY_ENTRY["IMAGE_DIRECTORY_ENTRY_RESOURCE"]])
    fa = pe.OPTIONAL_HEADER.FileAlignment
    rs = next(s for s in pe.sections if s.Name.rstrip(b"\0") == b".rsrc")
    base, vsz = rs.VirtualAddress, rs.Misc_VirtualSize
    ents = []

    def walk(d):
        for e in d.entries:
            if hasattr(e, "directory"):
                walk(e.directory)
            else:
                ents.append(e.data.struct)
    walk(pe.DIRECTORY_ENTRY_RESOURCE)
    dirend = max(s.get_file_offset() + 16 for s in ents) - rs.PointerToRawData      # data entries are the last part of the directory
    inside = [s for s in ents if base <= s.OffsetToData < base + vsz]
    if any(s.Size > 0x100000 for s in inside):
        raise SystemExit("a large resource blob is still inside .rsrc; pack first")
    out = bytearray(data)
    cur = dirend
    moves = []
    for s in sorted(inside, key=lambda s: s.OffsetToData):
        cur = (cur + 15) & ~15
        src = rs.PointerToRawData + (s.OffsetToData - base)
        moves.append((s, bytes(data[src:src + s.Size]), cur))
        cur += s.Size
    new_raw = (cur + fa - 1) // fa * fa
    old_raw = rs.SizeOfRawData
    if new_raw >= old_raw:
        return bytes(data)
    body = bytearray(new_raw)
    body[:dirend] = data[rs.PointerToRawData:rs.PointerToRawData + dirend]
    for s, blob, off in moves:
        body[off:off + len(blob)] = blob
    res = bytearray(data[:rs.PointerToRawData]) + body + data[rs.PointerToRawData + old_raw:]
    for s, blob, off in moves:           # re-point the resource data entries (file offset of the entry is before .rsrc raw move: unchanged)
        struct.pack_into("<I", res, s.get_file_offset(), base + off)
    delta = old_raw - new_raw
    sec0 = pe.DOS_HEADER.e_lfanew + 4 + 20 + pe.FILE_HEADER.SizeOfOptionalHeader
    for i, s in enumerate(pe.sections):
        o = sec0 + 40 * i
        if s is rs:
            struct.pack_into("<I", res, o + 16, new_raw)
        elif s.PointerToRawData > rs.PointerToRawData:
            struct.pack_into("<I", res, o + 20, s.PointerToRawData - delta)
    struct.pack_into("<I", res, pe.OPTIONAL_HEADER.get_file_offset() + 64, 0)       # CheckSum 0 (not enforced for DLLs)
    return bytes(res)


if __name__ == "__main__":
    d = open(sys.argv[1], "rb").read()
    o = shrink(d)
    open(sys.argv[2], "wb").write(o)
    print(len(d), "->", len(o))
