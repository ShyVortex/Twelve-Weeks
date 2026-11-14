"""DXBC container helpers for the Part I shader ABI retarget (p1_abi.py): part table, rebuild with new parts, PSV0 resource
bindings, RTS0 root signature decode / encode (D3D12 serialized root signature 1.0 / 1.1).

RTS0 layout: header {version 1 / 2, param count, params offset, static sampler count, samplers offset, flags}, 12-byte param
headers {type, visibility, payload offset}; table payload {range count, ranges offset} + ranges (1.1: type, count, base register,
space, flags, table offset = 24 bytes; 1.0: no flags, 20 bytes); 32-bit constants {register, space, count}; root CBV/SRV/UAV
{register, space(, flags 1.1)}; static samplers 13 dwords.  encode() writes header, param headers, each payload in param order,
then the static samplers - the layout the D3D12 serializer produces (checked: every root signature of the Bookstore paks and of
three stock TLOU2 levels re-encodes byte-identically)."""
import struct

import dxil_patch as dp

APPEND = 0xFFFFFFFF


def parts(c):
    """[(tag, payload bytes)] in container order"""
    n = struct.unpack_from("<I", c, 28)[0]
    out = []
    for i in range(n):
        o = struct.unpack_from("<I", c, 32 + 4 * i)[0]
        sz = struct.unpack_from("<I", c, o + 4)[0]
        out.append((bytes(c[o:o + 4]), bytes(c[o + 8:o + 8 + sz])))
    return out


def build(c0, plist):
    """new signed container: header fields (version) of c0, parts plist [(tag, payload)]"""
    out = bytearray(c0[:32]) + bytes(4 * len(plist))
    struct.pack_into("<I", out, 28, len(plist))
    for i, (tag, data) in enumerate(plist):
        struct.pack_into("<I", out, 32 + 4 * i, len(out))
        out += tag + struct.pack("<I", len(data)) + data
    struct.pack_into("<I", out, 24, len(out))
    return dp.resign(bytes(out))


def with_bitcode(dxil_part, bitcode):
    """DXIL part payload with a new LLVM bitcode (program header sizes updated)"""
    d = bytearray(dxil_part)
    bo = struct.unpack_from("<I", d, 16)[0]           # payload: version, size in dwords, 'DXIL', dxil version, bitcode
    d = d[:8 + bo] + bitcode                           # offset (from the 'DXIL' tag at +8), bitcode size
    struct.pack_into("<I", d, 20, len(bitcode))
    struct.pack_into("<I", d, 4, len(d) // 4)          # program size in dwords
    return bytes(d)


def bitcode(dxil_part):
    assert dxil_part[8:12] == b"DXIL"
    bo, bs = struct.unpack_from("<II", dxil_part, 16)
    return dxil_part[8 + bo:8 + bo + bs]


def shader_kind(dxil_part):
    """0 pixel, 1 vertex, 2 geometry, 3 hull, 4 domain, 5 compute"""
    return struct.unpack_from("<I", dxil_part, 0)[0] >> 16


# ---------------------------------------------------------------- PSV0
CBV, SAMPLER = 2, 1
SRV_TYPES = (3, 4, 5)
UAV_TYPES = (6, 7, 8, 9)


def psv_resources(psv):
    """[(res type, space, lower, upper)] in container order (CBVs, samplers, SRVs, UAVs - each in range-id order)"""
    rsz = struct.unpack_from("<I", psv, 0)[0]
    o = 4 + rsz
    n = struct.unpack_from("<I", psv, o)[0]
    o += 4
    if not n:
        return []
    esz = struct.unpack_from("<I", psv, o)[0]
    o += 4
    return [struct.unpack_from("<4I", psv, o + esz * i) for i in range(n)]


def ranges_by_class(psv):
    """{'cbv'|'sampler'|'srv'|'uav': [(space, lower, upper)]} indexed by DXIL range id"""
    out = {"cbv": [], "sampler": [], "srv": [], "uav": []}
    for t, sp, lo, hi in psv_resources(psv):
        k = "cbv" if t == CBV else "sampler" if t == SAMPLER else "srv" if t in SRV_TYPES else "uav" if t in UAV_TYPES else None
        if k:
            out[k].append((sp, lo, hi))
    return out


# ---------------------------------------------------------------- RTS0
class RootSig:
    def __init__(self, raw):
        self.version, n, po, ns, so, self.flags = struct.unpack_from("<6I", raw, 0)
        self.params = []
        for i in range(n):
            t, vis, off = struct.unpack_from("<3I", raw, po + 12 * i)
            if t == 0:
                nr, ro = struct.unpack_from("<2I", raw, off)
                if self.version >= 2:
                    rs = [list(struct.unpack_from("<6I", raw, ro + 24 * k)) for k in range(nr)]
                else:
                    rs = [list(struct.unpack_from("<5I", raw, ro + 20 * k)) for k in range(nr)]
                self.params.append([t, vis, rs])
            elif t == 1:
                self.params.append([t, vis, list(struct.unpack_from("<3I", raw, off))])
            else:
                self.params.append([t, vis, list(struct.unpack_from("<3I" if self.version >= 2 else "<2I", raw, off))])
        self.samplers = [raw[so + 52 * k:so + 52 * (k + 1)] for k in range(ns)]

    def encode(self):
        n = len(self.params)
        po = 24
        pos = po + 12 * n
        heads, body = [], bytearray()
        for t, vis, data in self.params:
            off = pos + len(body)
            heads.append(struct.pack("<3I", t, vis, off))
            if t == 0:
                body += struct.pack("<2I", len(data), off + 8)
                for r in data:
                    body += struct.pack("<%dI" % len(r), *r)
            else:
                body += struct.pack("<%dI" % len(data), *data)
        so = pos + len(body)
        out = struct.pack("<6I", self.version, n, po, len(self.samplers), so, self.flags)     # (no samplers: end offset)
        return out + b"".join(heads) + bytes(body) + b"".join(self.samplers)

    def describe(self):
        T = {0: "SRV", 1: "UAV", 2: "CBV", 3: "SMP"}
        out = []
        for i, (t, vis, data) in enumerate(self.params):
            if t == 0:
                out.append("p%d table [%s]" % (i, " ".join(
                    "%s%s@%d,s%d->%s" % (T[r[0]], "unb" if r[1] == APPEND else r[1], r[2], r[3],
                                          "app" if r[-1] == APPEND else r[-1]) for r in data)))
            else:
                out.append("p%d type%d %s" % (i, t, data))
        return out
