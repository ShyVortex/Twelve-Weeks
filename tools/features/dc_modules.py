"""Patch a module's size in a DC modules.bin.

modules.bin (one 'module-info-array' entry) lists every script module with its byte size:
ModulesEntry = {char *name, u64 name_sid, u64 size, SymbolArray *imports, *exports}
where name_sid = FNV-1a-64 of the path under dc1 without extension
("ss-hud2/ss-menu2-player-upgrades"). Replacing a module with a different-size .bin
needs its size updated here, or the game loads it with the old size.

  python dc_modules.py <modules.bin> <dc1 dir with replaced .bin files> <rel/path.bin>...
"""
import os
import struct
import sys


def fnv(s):
    h = 0xCBF29CE484222325
    for c in s.encode():
        h = ((h ^ c) * 0x100000001B3) & 0xFFFFFFFFFFFFFFFF
    return h


def set_size(data, name, size):
    key = struct.pack("<Q", fnv(name))
    hits = []
    i = data.find(key)
    while i != -1:
        hits.append(i)
        i = data.find(key, i + 1)
    # entry layout: [name ptr][sid][size]; the sid we want is followed by a plausible size
    for i in hits:
        old = struct.unpack_from("<Q", data, i + 8)[0]
        if 0 < old < 64 << 20 and struct.unpack_from("<Q", data, i - 8)[0] < len(data):
            struct.pack_into("<Q", data, i + 8, size)
            return old
    raise SystemExit(f"{name}: module entry not found ({len(hits)} sid hits)")


def main():
    modules, dc1, *rels = sys.argv[1:]
    data = bytearray(open(modules, "rb").read())
    for rel in rels:
        name = os.path.splitext(rel.replace("\\", "/"))[0]
        size = os.path.getsize(os.path.join(dc1, rel))
        old = set_size(data, name, size)
        print(f"{name}: size {old} -> {size}")
    open(modules, "wb").write(data)


if __name__ == "__main__":
    main()
