"""Grow-able DC (.bin script/data) files.

Layout (TLOU2 PC): header "00CD" u32 version 1, u32 data_size, u32 ?, u32 1, u32 entry_count,
u64 entries offset (0x28); data [0, data_size); then the relocation table: u32 byte count +
a bitmap with one bit per data qword (bit set = that qword is a pointer, stored as a file
offset and rebased at load).

dconstruct -e can only replace values in place. DcFile.append() adds new data at the end of
the data block (before the bitmap), so lists can be EXPANDED: build a bigger copy of an array
at the end and repoint its owner to it. Pointer slots inside appended data are marked in the
bitmap by passing their offsets (relative to the appended block).
"""
import struct

import numpy as np


class DcFile:
    def __init__(self, data: bytes):
        d = bytearray(data)
        assert d[:4] == b"00CD", "not a DC file"
        self.size = struct.unpack_from("<I", d, 8)[0]
        self.strings = struct.unpack_from("<I", d, 12)[0]      # start of the string region
        nbytes = struct.unpack_from("<I", d, self.size)[0]
        self.data = d[:self.size]
        self.bits = bytearray(d[self.size + 4:self.size + 4 + nbytes])
        self.tail = bytes(d[self.size + 4 + nbytes:])   # anything after the bitmap (normally empty)

    # --- reading
    def q(self, off):
        return struct.unpack_from("<Q", self.data, off)[0]

    def is_ptr(self, off):
        i = off // 8
        return i // 8 < len(self.bits) and (self.bits[i // 8] >> (i % 8)) & 1

    def ptr_flags(self):
        """one bool per data qword: is it a pointer slot (the bitmap unpacked; vectorised is_ptr)"""
        nq = (len(self.data) + 7) // 8
        f = np.unpackbits(np.frombuffer(bytes(self.bits[:(nq + 7) // 8]), dtype=np.uint8), bitorder="little")
        if len(f) < nq:
            f = np.concatenate([f, np.zeros(nq - len(f), dtype=np.uint8)])
        return f[:nq].astype(bool)

    # --- writing
    def set_q(self, off, v):
        struct.pack_into("<Q", self.data, off, v)

    def set_ptr(self, off, target):
        """Point an existing slot at target (the slot must already be a pointer slot)."""
        assert self.is_ptr(off), f"{off:#x} is not a pointer slot"
        self.set_q(off, target)

    def _mark(self, off):
        i = off // 8
        while i // 8 >= len(self.bits):
            self.bits.append(0)
        self.bits[i // 8] |= 1 << (i % 8)

    def append(self, blob: bytes, ptr_slots=(), tag=None):
        """Add blob at the end of the objects, i.e. before the string region (header +0x0C:
        strings come last; tools read anything past that offset as text), which moves the
        strings: every pointer into them is shifted. Returns the blob's file offset.
        ptr_slots: offsets inside blob that hold file offsets (get relocated).
        tag: type name written in the qword before the object, as the compiler does
        ("array", "weapon-upgrade-ref-array", ...)."""
        ins = self.strings
        chunk = bytearray((-ins) % 8)          # the string region need not be 8-aligned
        if tag:
            chunk += struct.pack("<Q", fnv(tag))
        at_rel = len(chunk)
        chunk += blob
        while len(chunk) % 8:
            chunk.append(0)
        n = len(chunk)
        # shift pointers that target the moved region, then the bitmap and the data
        flags = self.ptr_flags()
        nq = len(self.data) // 8
        if len(self.data) % 8 == 0 or not flags[nq]:       # (vectorised; the loops below are the reference for the odd case)
            qa = np.frombuffer(self.data, dtype="<u8", count=nq)
            hit = flags[:nq] & (qa >= np.uint64(ins))
            qa[hit] += np.uint64(n)
            del qa                           # (a live view would block the resize below)
            idx = np.arange(ins, len(self.data), 8) // 8
            old = [ins + 8 * int(k) for k in np.nonzero(flags[idx])[0]]
        else:
            for i in range(0, len(self.data), 8):
                if self.is_ptr(i) and self.q(i) >= ins:
                    self.set_q(i, self.q(i) + n)
            old = [i for i in range(ins, len(self.data), 8) if self.is_ptr(i)]
        for i in old:
            self.bits[(i // 8) // 8] &= ~(1 << ((i // 8) % 8))
        self.data[ins:ins] = chunk
        for i in old:
            self._mark(i + n)
        for sl in ptr_slots:
            if self.q(ins + at_rel + sl) >= ins:
                self.set_q(ins + at_rel + sl, self.q(ins + at_rel + sl) + n)
            self._mark(ins + at_rel + sl)
        self.strings += n
        return ins + at_rel

    def copy_block(self, src, length):
        """Bytes + relative pointer slots of an existing block (for cloning structs/arrays)."""
        blob = bytes(self.data[src:src + length])
        slots = [o for o in range(0, length, 8) if self.is_ptr(src + o)]
        return blob, slots

    def save(self) -> bytes:
        self.size = len(self.data)
        need = (self.size // 8 + 7) // 8
        bits = bytes(self.bits[:need]) + bytes(max(0, need - len(self.bits)))
        out = bytearray(self.data)
        struct.pack_into("<I", out, 8, self.size)
        struct.pack_into("<I", out, 12, self.strings)
        return bytes(out) + struct.pack("<I", len(bits)) + bits + self.tail


def fnv(s: str) -> int:
    h = 0xcbf29ce484222325
    for c in s.encode():
        h = ((h ^ c) * 0x100000001b3) & (2 ** 64 - 1)
    return h
