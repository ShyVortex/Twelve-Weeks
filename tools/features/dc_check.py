"""Offline check of a patched DC module the way the game's loader treats it (decompiled from tlou-ii.exe):

  FUN_141863af0  (relocation)   header "00CD", version 1, data size at +8, relocation bitmap after the data: u32 byte count +
                                one bit per data qword; every set bit = a pointer slot: value must be 0 or inside [0, size), the
                                loader adds the load base. Qwords with the bit CLEAR are plain integers (a pointer that was not marked
                                stays a raw file offset = garbage at run time).
  FUN_1417b4ca0  (module setup) compares the file size with the modules.bin entry (+0x10) before it registers anything; then entry
                                count = header +0x14, entry table = header +0x18 (24-byte rows {sid, type tag, ptr}).
  FUN_1417b5280  (symbol find)  BINARY SEARCH of that table by sid (unsigned): the rows must be sorted and unique.
  FUN_1417b5640                 copies the entry sids into the module's symbol list.
  modules.bin                   the module's export list = the sids it holds (sorted).

  python dc_check.py <mod root> [<mod root>...]     checks level-sets-test.bin + test-tasks.bin of a staged / built mod tree
Used by sp_maps_build.verify() (a failed check stops the build)."""
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from dcfile import DcFile, fnv  # noqa: E402

MODULES = (("level-sets/level-sets-test", os.path.join("bin", "dc1", "level-sets", "level-sets-test.bin")),
           ("test-tasks", os.path.join("bin", "dc1", "test-tasks.bin")))


def check_relocation(raw, label):
    assert raw[:4] == b"00CD" and struct.unpack_from("<I", raw, 4)[0] == 1, f"{label}: header"
    size = struct.unpack_from("<I", raw, 8)[0]
    nb = struct.unpack_from("<I", raw, size)[0]
    assert nb == (size // 8 + 7) // 8, f"{label}: bitmap bytes {nb} for data size {size}"
    assert len(raw) == size + 4 + nb, f"{label}: file size {len(raw)} != data {size} + 4 + bitmap {nb}"
    bits = raw[size + 4:size + 4 + nb]
    n = 0
    for idx in range(nb * 8):
        if (bits[idx // 8] >> (idx % 8)) & 1:
            assert idx * 8 + 8 <= size, f"{label}: relocation bit {idx} beyond the data"
            v = struct.unpack_from("<Q", raw, idx * 8)[0]
            assert v == 0 or v < size, f"{label}: pointer slot {idx * 8:#x} -> {v:#x} outside the data ({size:#x})"
            n += 1
    return size, n


def module_sids(m, name):
    """modules.bin: the export sids of module `name`"""
    e = m.data.find(struct.pack("<Q", fnv(name))) - 8
    assert e > 0 and m.is_ptr(e) and m.is_ptr(e + 32), f"modules.bin entry of {name}"
    sa = m.q(e + 32)
    n, d = m.q(sa), m.q(sa + 8)
    return [m.q(d + 8 * k) for k in range(n)], m.q(e + 0x10)


def check_module(root, name, rel, modules):
    raw = open(os.path.join(root, rel), "rb").read()
    size, nptr = check_relocation(raw, name)
    f = DcFile(raw)
    n = struct.unpack_from("<I", f.data, 0x14)[0]
    eo = struct.unpack_from("<Q", f.data, 0x18)[0]
    rows = [struct.unpack_from("<QQQ", f.data, eo + 24 * i) for i in range(n)]
    sids = [r[0] for r in rows]
    assert sids == sorted(set(sids)), f"{name}: entry table not sorted / unique (binary search by sid)"
    assert all(f.is_ptr(eo + 24 * i + 16) and rows[i][2] < size for i in range(n)), f"{name}: an entry's object pointer is not a relocated slot"
    assert not any(f.is_ptr(eo + 24 * i) or f.is_ptr(eo + 24 * i + 8) for i in range(n)), f"{name}: sid / tag columns marked as pointers"
    exp, msize = module_sids(modules, name)
    assert msize == len(raw), f"{name}: modules.bin size {msize} != file {len(raw)} (the loader skips the module)"
    assert exp == sorted(exp), f"{name}: exports not sorted"
    missing = set(sids) - set(exp)
    assert not missing or name == "test-tasks", f"{name}: {len(missing)} entries not in the modules.bin export list"
    if name.startswith("level-sets"):
        for sid, tag, ptr in rows:       # a level set's own name hashes to its entry sid (stock invariant), its arrays are relocated slots
            nm_ptr = f.q(ptr)
            nm = f.data[nm_ptr:f.data.index(b"\0", nm_ptr)].decode("latin1")
            assert fnv(nm) == sid or ptr == 0, f"{name}: entry {nm}: sid {sid:#x} != fnv(name)"
            assert f.is_ptr(ptr) and f.is_ptr(ptr + 0x10), f"{name}: set {nm}: name / arrays slot not relocated"
            # the whole 0x30-byte struct as in all 2232 game sets (fresh sets had +0x28 = the next appended bytes)
            assert (f.q(ptr - 8) == fnv("level-set") and f.is_ptr(ptr + 0x18) and f.q(ptr + 0x18) == ptr + 0x30
                    and f.q(ptr + 0x20) >> 32 == 0xFFFFFFFF and f.q(ptr + 0x28) == 0xFFFFFFFF), \
                f"{name}: set {nm}: struct differs from the stock level-set layout (+0x18 / +0x20 / +0x28)"
    return n, nptr, len(exp)


def check_mod_tree(root):
    modules = DcFile(open(os.path.join(root, "bin", "dc1", "modules.bin"), "rb").read())
    check_relocation(open(os.path.join(root, "bin", "dc1", "modules.bin"), "rb").read(), "modules.bin")
    out = {}
    for name, rel in MODULES:
        out[name] = check_module(root, name, rel, modules)
    return out


if __name__ == "__main__":
    for r in sys.argv[1:]:
        for k, v in check_mod_tree(r).items():
            print(f"{r}: {k}: {v[0]} entries, {v[1]} relocated pointers, {v[2]} exports - OK")
