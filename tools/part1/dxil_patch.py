"""Rewrite constant register indices inside compiled DXIL shaders (DXBC containers) in place, then re-sign the container.

Why: Part I level paks embed their material shaders compiled against Part I's engine-wide resource layout. TLOU2 binds
the same root signature but its per-frame constant buffers grew (cb0,space2: +3 registers from ~53; cb3,space2: +4 from ~132)
and its global SRVs moved (t100 -> t102, t108 -> t110). The Part I shaders run in TLOU2 but read the baked-lighting /
exposure constants from the wrong registers: textures and dynamic lights work, the baked light comes out ~0 (re/part1/geometry-upgrade.md s9).

What this does: walks the DXIL part's LLVM bitstream, finds the function-level integer constants (CONSTANTS_BLOCK INTEGER records),
and rewrites a constant's value when every use of that value in the function is a register operand we remap (decided by the caller
from the dxc disassembly). The new value must encode in the same number of bits (VBR chunk count), so nothing moves.
Then the container digest (the DXBC checksum, a modified MD5 the runtime verifies for DXIL) is recomputed.

  python dxil_patch.py checksum <file.dxbc>...      # verify our checksum against the stored digest
"""
import struct
import sys


# ---------------------------------------------------------------- DXBC container checksum (modified MD5, as in wine / vkd3d)
_S = [7, 12, 17, 22] * 4 + [5, 9, 14, 20] * 4 + [4, 11, 16, 23] * 4 + [6, 10, 15, 21] * 4
_K = [int(abs(__import__("math").sin(i + 1)) * 2 ** 32) & 0xffffffff for i in range(64)]


def _rol(x, c):
    return ((x << c) | (x >> (32 - c))) & 0xffffffff


def _transform(st, block):
    a, b, c, d = st
    w = struct.unpack("<16I", block)
    for i in range(64):
        if i < 16:
            f, g = (b & c) | (~b & d), i
        elif i < 32:
            f, g = (d & b) | (~d & c), (5 * i + 1) % 16
        elif i < 48:
            f, g = b ^ c ^ d, (3 * i + 5) % 16
        else:
            f, g = c ^ (b | (~d & 0xffffffff)), (7 * i) % 16
        f = (f + a + _K[i] + w[g]) & 0xffffffff
        a, d, c = d, c, b
        b = (b + _rol(f, _S[i])) & 0xffffffff
    return [(st[0] + a) & 0xffffffff, (st[1] + b) & 0xffffffff, (st[2] + c) & 0xffffffff, (st[3] + d) & 0xffffffff]


def dxbc_checksum(container):
    """digest over container[20:] (everything after magic + digest)"""
    data = container[20:]
    n = len(data)
    bits = (n * 8) & 0xffffffff
    st = [0x67452301, 0xefcdab89, 0x98badcfe, 0x10325476]
    full = n - n % 64
    for o in range(0, full, 64):
        st = _transform(st, data[o:o + 64])
    left = data[full:]
    if len(left) >= 56:
        blk = left + b"\x80" + b"\0" * (63 - len(left))
        st = _transform(st, blk)
        blk = struct.pack("<I", bits) + b"\0" * 56 + struct.pack("<I", (bits >> 2) | 1)
        st = _transform(st, blk)
    else:
        blk = struct.pack("<I", bits) + left + b"\x80"
        blk = blk + b"\0" * (60 - len(blk)) + struct.pack("<I", (bits >> 2) | 1)
        st = _transform(st, blk)
    return struct.pack("<4I", *st)


def resign(container):
    c = bytearray(container)
    c[4:20] = dxbc_checksum(bytes(c))
    return bytes(c)


# ---------------------------------------------------------------- container parts
def parts(container):
    n = struct.unpack_from("<I", container, 28)[0]
    out = {}
    for i in range(n):
        o = struct.unpack_from("<I", container, 32 + 4 * i)[0]
        out[container[o:o + 4]] = (o + 8, struct.unpack_from("<I", container, o + 4)[0])
    return out


def bitcode_span(container):
    """(byte offset, size) of the LLVM bitcode inside the DXIL part"""
    o, sz = parts(container)[b"DXIL"]
    # program header: u32 version, u32 size in dwords, 'DXIL', u32 dxil version, u32 bitcode offset (from 'DXIL'), u32 bitcode size
    assert container[o + 8:o + 12] == b"DXIL"
    bo, bs = struct.unpack_from("<II", container, o + 16)
    return o + 8 + bo, bs


# ---------------------------------------------------------------- minimal LLVM bitstream reader (enough for constants + types)
class Bits:
    def __init__(self, data, base_bits=0):
        self.d = data
        self.pos = base_bits

    def read(self, n):
        v = 0
        for i in range(n):
            byte = self.d[(self.pos + i) >> 3]
            v |= ((byte >> ((self.pos + i) & 7)) & 1) << i
        self.pos += n
        return v

    def vbr(self, n):
        v, shift = 0, 0
        hi = 1 << (n - 1)
        while True:
            x = self.read(n)
            v |= (x & (hi - 1)) << shift
            shift += n - 1
            if not x & hi:
                return v

    def align32(self):
        self.pos = (self.pos + 31) & ~31


class Field:
    """where one record operand sits: bit position, encoding ('fixed', w) / ('vbr', w), value"""
    __slots__ = ("pos", "enc", "w", "val")

    def __init__(self, pos, enc, w, val):
        self.pos, self.enc, self.w, self.val = pos, enc, w, val


def _read_abbrev_op(b, enc, w):
    p = b.pos
    if enc == "fixed":
        return Field(p, enc, w, b.read(w))
    if enc == "vbr":
        return Field(p, enc, w, b.vbr(w))
    if enc == "char6":
        return Field(p, enc, 6, b.read(6))
    raise ValueError(enc)


def walk(data):
    """yield (block id path, record code, [Field...]) for every record; data = bitcode bytes ('BC' 0xC0DE)"""
    b = Bits(data, 32)          # skip magic
    blockinfo = {}              # block id -> [abbrev defs]
    out = []

    def parse_block(abbrev_w, block_id, path, abbrevs):
        cur_info_bid = None
        while True:
            if block_id == -1 and b.pos + 32 > 8 * len(b.d):     # top level has no END_BLOCK
                return
            aid = b.read(abbrev_w)
            if aid == 0:            # END_BLOCK
                b.align32()
                return
            if aid == 1:            # ENTER_SUBBLOCK
                bid = b.vbr(8)
                nw = b.vbr(4)
                b.align32()
                b.read(32)          # block length in words
                parse_block(nw, bid, path + (bid,), list(blockinfo.get(bid, [])))
                continue
            if aid == 2:            # DEFINE_ABBREV
                nops = b.vbr(5)
                ops = []
                i = 0
                while i < nops:
                    if b.read(1):
                        ops.append(("lit", b.vbr(8)))
                    else:
                        e = b.read(3)
                        if e == 1:
                            ops.append(("fixed", b.vbr(5)))
                        elif e == 2:
                            ops.append(("vbr", b.vbr(5)))
                        elif e == 3:
                            ops.append(("array", None))
                        elif e == 4:
                            ops.append(("char6", None))
                        elif e == 5:
                            ops.append(("blob", None))
                    i += 1
                if block_id == 0:
                    blockinfo.setdefault(cur_info_bid, []).append(ops)
                else:
                    abbrevs.append(ops)
                continue
            if aid == 3:            # UNABBREV_RECORD
                code = b.vbr(6)
                n = b.vbr(6)
                fields = []
                for _ in range(n):
                    p = b.pos
                    fields.append(Field(p, "vbr", 6, b.vbr(6)))
                if block_id == 0 and code == 1:     # SETBID
                    cur_info_bid = fields[0].val
                out.append((path, code, fields))
                continue
            ops = abbrevs[aid - 4]
            vals = []
            j = 0
            while j < len(ops):
                kind, w = ops[j]
                if kind == "lit":
                    vals.append(Field(b.pos, "lit", 0, w))
                elif kind == "array":
                    n = b.vbr(6)
                    ek, ew = ops[j + 1]
                    for _ in range(n):
                        vals.append(_read_abbrev_op(b, ek, ew))
                    j += 1
                elif kind == "blob":
                    n = b.vbr(6)
                    b.align32()
                    b.pos += 8 * n
                    b.align32()
                else:
                    vals.append(_read_abbrev_op(b, kind, w))
                j += 1
            code = vals[0].val
            if block_id == 0 and code == 1:
                cur_info_bid = vals[1].val
            out.append((path, code, vals[1:]))

    parse_block(2, -1, (), [])
    return out


TYPE_BLOCK = 17
CONSTANTS_BLOCK = 11
FUNCTION_BLOCK = 12
MODULE_BLOCK = 8


def int_constants(data):
    """[(Field of the value, int bit width, signed value, scope)] for every INTEGER constant; scope = 'module' or function ordinal"""
    recs = walk(data)
    types = []
    for path, code, f in recs:
        if path and path[-1] == TYPE_BLOCK and code != 1:       # NUMENTRY = 1
            types.append((code, f[0].val if f else None))
    out = []
    cur_type = None
    fn = -1
    last_path = None
    for path, code, f in recs:
        if path and path[-1] == FUNCTION_BLOCK and path != last_path:
            pass
        if path == (MODULE_BLOCK, FUNCTION_BLOCK) and last_path != path:
            fn += 1
        last_path = path
        if not path or path[-1] != CONSTANTS_BLOCK:
            continue
        if code == 1:                                   # SETTYPE
            cur_type = f[0].val
        elif code == 4:                                 # INTEGER (signed vbr: low bit = sign)
            t = types[cur_type] if cur_type is not None and cur_type < len(types) else (None, None)
            width = t[1] if t[0] == 7 else None         # TYPE_CODE_INTEGER = 7
            v = f[0].val
            sv = -(v >> 1) if v & 1 else v >> 1
            scope = "module" if len(path) == 2 else fn
            out.append((f[0], width, sv, scope))
    return out


def _encode_len(enc, w, v):
    if enc == "fixed":
        return w if v < (1 << w) else None
    n = 0
    while True:
        n += w
        v >>= (w - 1)
        if not v:
            return n


def set_field(data, fld, newval):
    """overwrite a Field in place; the encoding must keep the same bit length.  Returns False if it would not fit."""
    if fld.enc not in ("fixed", "vbr"):
        return False
    if _encode_len(fld.enc, fld.w, fld.val) != _encode_len(fld.enc, fld.w, newval):
        return False
    bits = []
    if fld.enc == "fixed":
        bits = [(newval >> i) & 1 for i in range(fld.w)]
    else:
        v = newval
        hi = fld.w - 1
        while True:
            chunk = v & ((1 << hi) - 1)
            v >>= hi
            cont = 1 if v else 0
            bits += [(chunk >> i) & 1 for i in range(hi)] + [cont]
            if not cont:
                break
    for i, bit in enumerate(bits):
        p = fld.pos + i
        if bit:
            data[p >> 3] |= 1 << (p & 7)
        else:
            data[p >> 3] &= ~(1 << (p & 7)) & 0xff
    fld.val = newval
    return True


def main(argv):
    if len(argv) >= 2 and argv[0] == "checksum":
        bad = 0
        for p in argv[1:]:
            c = open(p, "rb").read()
            ok = dxbc_checksum(c) == c[4:20]
            bad += not ok
            if not ok:
                print("MISMATCH", p)
        print("%d files, %d mismatches" % (len(argv) - 1, bad))
        return
    print(__doc__)


if __name__ == "__main__":
    main(sys.argv[1:])
