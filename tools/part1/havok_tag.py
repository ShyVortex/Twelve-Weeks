"""Havok 2017.1 binary tagfile ("TAG0") reader / writer, as used by TLOU2 COLLISION_DATA_HAVOK_BG / _FOREGROUND items.

Layout (decoded on real TLOU2 -phys paks, see re/part1/havok-collision.md):
  section = u32 BE (bits 0..29 size incl. this 8-byte header, bit 30 = leaf) + 4-char tag
  TAG0 { SDKV "20170100", DATA <object image>, TYPE { TPTR TSTR TNA1 FSTR TBDY THSH TPAD }, INDX { ITEM PTCH } }
  TSTR / FSTR: NUL-separated type / field names.  TNA1: packed count (types 1..count-1), per type: name, n template
  params, (param name, value) pairs.  TBDY: per type: id, parent, flags, [sub-type flags][pointee][version]
  [size, align][abstract][members: name, flags, offset, type][interfaces: type, value][attribute].
  THSH: count, (type, u32 hash).  ITEM: 12 bytes (u32 type | flags << 24, u32 DATA offset, u32 count); item 0 = null.
  PTCH: per type: u32 type, u32 count, u32 DATA offsets of pointer slots (each slot holds an ITEM index).
  Packed ints: 0xxxxxxx | 10xxxxxx +1 | 110xxxxx +2 | 11100xxx +3 | 11101xxx +4 | 11110xxx +7 (big-endian payload).

Library:  t = Tag.parse(bytes); t.types[i] (dict); t.items [(type, flags, offset, count)]; t.data (bytes)
          t.encode() -> bytes (re-serialises every section from the decoded tables)
          t.objects()  -> generic decode of every item into python values (records = dicts)
"""
import struct


def rd_packed(b, o):
    c = b[o]
    if c < 0x80:
        return c, o + 1
    if c < 0xC0:
        return ((c << 8) | b[o + 1]) & 0x3FFF, o + 2
    if c < 0xE0:
        return ((c << 16) | (b[o + 1] << 8) | b[o + 2]) & 0x1FFFFF, o + 3
    if c < 0xE8:
        return int.from_bytes(b[o:o + 4], "big") & 0x7FFFFFF, o + 4
    if c < 0xF0:
        return int.from_bytes(b[o:o + 5], "big") & 0x7FFFFFFFF, o + 5
    if c < 0xF8:
        return int.from_bytes(b[o:o + 8], "big") & 0x7FFFFFFFFFFFFFF, o + 8
    raise ValueError("packed int %02x at %x" % (c, o))


def wr_packed(v):
    if v < 0x80:
        return bytes([v])
    if v < 0x4000:
        return (v | 0x8000).to_bytes(2, "big")
    if v < 0x200000:
        return (v | 0xC00000).to_bytes(3, "big")
    if v < 0x8000000:
        return (v | 0xE0000000).to_bytes(4, "big")
    if v < 0x800000000:
        return (v | 0xE800000000).to_bytes(5, "big")
    return (v | 0xF000000000000000).to_bytes(8, "big")


def sections(b, o, end):
    out = []
    while o < end:
        h = struct.unpack_from(">I", b, o)[0]
        sz = h & 0x3FFFFFFF
        out.append((b[o + 4:o + 8].decode(), h >> 30, o + 8, o + sz))
        o += sz
    return out


def section(tag, payload, leaf=True):
    return struct.pack(">I", (len(payload) + 8) | (0x40000000 if leaf else 0)) + tag.encode() + payload


# sub-type flags (low nibble = kind), Havok 2016+ reflection
K_VOID, K_OPAQUE, K_BOOL, K_STRING, K_INT, K_FLOAT, K_POINTER, K_RECORD, K_ARRAY = range(9)
F_SUB, F_PTR, F_VER, F_SIZE, F_ABS, F_MEM, F_IFC, F_ATTR = 1, 2, 4, 8, 16, 32, 64, 128


class Tag:
    @classmethod
    def parse(cls, b):
        t = cls()
        (tag, leaf, s, e), = [x for x in sections(b, 0, len(b))][:1]
        assert tag == "TAG0", tag
        t.raw = b
        t.order = []
        for tag, leaf, s, e in sections(b, s, e):
            t.order.append(tag)
            if tag == "SDKV":
                t.sdk = b[s:e].decode()
            elif tag == "DATA":
                t.data = bytes(b[s:e])
            elif tag == "TYPE":
                t._type(b, s, e)
            elif tag == "INDX":
                t._indx(b, s, e)
            else:
                raise ValueError("section " + tag)
        return t

    def _type(self, b, s, e):
        self.type_order = []
        for tag, leaf, s1, e1 in sections(b, s, e):
            self.type_order.append(tag)
            p = b[s1:e1]
            tag = {"TST1": "TSTR", "FST1": "FSTR"}.get(tag, tag)     # Havok 2020.1 spelling
            if tag == "TPTR":
                self.tptr = bytes(p)
            elif tag == "TSTR":
                self.tstr = p.split(b"\0")[:-1]
                self.tstr_raw = bytes(p)
            elif tag == "FSTR":
                self.fstr = p.split(b"\0")[:-1]
                self.fstr_raw = bytes(p)
            elif tag == "TNA1":
                self.tna1_raw = bytes(p)
                n, o = rd_packed(p, 0)
                self.types = [None] + [{} for _ in range(n - 1)]
                for i in range(1, n):
                    nm, o = rd_packed(p, o)
                    k, o = rd_packed(p, o)
                    tp = []
                    for _ in range(k):
                        a, o = rd_packed(p, o)
                        v, o = rd_packed(p, o)
                        tp.append((self.tstr[a].decode(), v))
                    self.types[i].update(name=self.tstr[nm].decode(), params=tp, parent=0, flags=0)
                self.tna1_pad = bytes(p[o:])
            elif tag == "TBDY":
                self.tbdy_raw = bytes(p)
                o = 0
                self.tbdy_order = []
                while o < len(p):
                    ti, o = rd_packed(p, o)
                    if ti == 0:
                        self.tbdy_tail = bytes(p[o - 1:])
                        break
                    self.tbdy_order.append(ti)
                    T = self.types[ti]
                    T["parent"], o = rd_packed(p, o)
                    T["flags"], o = rd_packed(p, o)
                    f = T["flags"]
                    if f & F_SUB:
                        T["sub"], o = rd_packed(p, o)
                    if f & F_PTR:
                        T["pointee"], o = rd_packed(p, o)
                    if f & F_VER:
                        T["version"], o = rd_packed(p, o)
                    if f & F_SIZE:
                        T["size"], o = rd_packed(p, o)
                        T["align"], o = rd_packed(p, o)
                    if f & F_ABS:
                        T["abstract"], o = rd_packed(p, o)
                    if f & F_MEM:
                        n, o = rd_packed(p, o)
                        T["nmem_raw"] = n             # low 16 bits = count; high bits seen set (0x30001) on one type
                        mem = []
                        T["mem_extra"] = {}
                        for mi in range(n & 0xFFFF):
                            a, o = rd_packed(p, o)
                            fl, o = rd_packed(p, o)
                            if fl & 0x80:                 # 2020.1: one more packed value before the offset
                                T["mem_extra"][mi], o = rd_packed(p, o)
                            off, o = rd_packed(p, o)
                            ty, o = rd_packed(p, o)
                            mem.append((self.fstr[a].decode(), fl, off, ty))
                        T["members"] = mem
                    if f & F_IFC:
                        n, o = rd_packed(p, o)
                        T["ifc"] = []
                        for _ in range(n):
                            a, o = rd_packed(p, o)
                            v, o = rd_packed(p, o)
                            T["ifc"].append((a, v))
                    if f & F_ATTR:
                        T["attr"], o = rd_packed(p, o)
                else:
                    self.tbdy_tail = b""
            elif tag == "THSH":
                self.thsh_raw = bytes(p)
                n, o = rd_packed(p, 0)
                self.thsh = []
                for _ in range(n):
                    ti, o = rd_packed(p, o)
                    self.thsh.append((ti, struct.unpack_from("<I", p, o)[0]))
                    o += 4
                self.thsh_pad = bytes(p[o:])
            elif tag == "TPAD":
                self.tpad = bytes(p)
            else:
                raise ValueError("TYPE sub-section " + tag)

    def _indx(self, b, s, e):
        for tag, leaf, s1, e1 in sections(b, s, e):
            p = b[s1:e1]
            if tag == "ITEM":
                self.items = []
                for o in range(0, len(p), 12):
                    w, off, cnt = struct.unpack_from("<III", p, o)
                    self.items.append((w & 0xFFFFFF, w >> 24, off, cnt))
            elif tag == "PTCH":
                self.ptch = []
                o = 0
                while o < len(p):
                    ti, n = struct.unpack_from("<II", p, o)
                    self.ptch.append((ti, list(struct.unpack_from("<%dI" % n, p, o + 8))))
                    o += 8 + 4 * n
            else:
                raise ValueError("INDX sub-section " + tag)

    # ---------------------------------------------------------------- type helpers
    def tname(self, i):
        if not i:
            return "-"
        T = self.types[i]
        s = T["name"]
        if T["params"]:
            s += "<" + ",".join(("%s=%s" % (a, self.tname(v)) if a.startswith("t") else "%s=%d" % (a, v)) for a, v in T["params"]) + ">"
        return s

    def resolved(self, i, key):
        """walk the parent chain for a body field (sub, size, align, pointee)"""
        while i:
            T = self.types[i]
            if key in T:
                return T[key]
            i = T["parent"]
        return None

    def all_members(self, i):
        out = []
        chain = []
        while i:
            chain.append(i)
            i = self.types[i]["parent"]
        for c in reversed(chain):
            out += [(n, fl, off, ty) for n, fl, off, ty in self.types[c].get("members", [])]
        return out

    def find(self, name):
        return [i for i in range(1, len(self.types)) if self.types[i]["name"] == name]

    def by_name(self, name):
        """type index of a (templated) type name as tname() prints it"""
        for i in range(1, len(self.types)):
            if self.tname(i) == name:
                return i
        raise KeyError(name)

    # ---------------------------------------------------------------- generic object decode (debug / validation)
    def value(self, ti, o, depth=0):
        """python value of type ti at DATA offset o: records -> dict, hkArray -> ('item', index), pointers -> ('ptr', index)"""
        sub = self.resolved(ti, "sub") or 0
        kind = sub & 0xF
        d = self.data
        if kind == K_RECORD:
            return {n: self.value(ty, o + off, depth + 1) for n, fl, off, ty in self.all_members(ti)}
        if kind == K_INT:
            size = {0x2000: 1, 0x4000: 2, 0x8000: 4, 0x10000: 8}[sub & 0x1E000]
            return int.from_bytes(d[o:o + size], "little", signed=bool(sub & 0x200))
        if kind == K_FLOAT:
            return struct.unpack_from("<f", d, o)[0]
        if kind == K_BOOL:
            return d[o]
        if kind in (K_POINTER, K_STRING):
            return ("ptr", struct.unpack_from("<Q", d, o)[0])
        if kind == K_ARRAY:
            n = sub >> 8
            el = self.resolved(ti, "pointee")
            if n:
                es = self.resolved(el, "size")
                return [self.value(el, o + es * i, depth + 1) for i in range(n)]
            return ("item", struct.unpack_from("<Q", d, o)[0])
        if kind == K_OPAQUE or kind == K_VOID:
            return None
        raise ValueError("kind %x of %s" % (sub, self.tname(ti)))

    def item_values(self, k):
        ti, fl, off, cnt = self.items[k]
        es = self.resolved(ti, "size")
        return [self.value(ti, off + es * i) for i in range(cnt)]

    # ---------------------------------------------------------------- encoder
    def encode_type(self):
        tna = bytearray(wr_packed(len(self.types)))
        sidx = {s.decode(): i for i, s in enumerate(self.tstr)}
        fidx = {s.decode(): i for i, s in enumerate(self.fstr)}
        for T in self.types[1:]:
            tna += wr_packed(sidx[T["name"]]) + wr_packed(len(T["params"]))
            for a, v in T["params"]:
                tna += wr_packed(sidx[a]) + wr_packed(v)
        tna += self.tna1_pad
        bd = bytearray()
        for ti in self.tbdy_order:
            T = self.types[ti]
            f = T["flags"]
            bd += wr_packed(ti) + wr_packed(T["parent"]) + wr_packed(f)
            if f & F_SUB:
                bd += wr_packed(T["sub"])
            if f & F_PTR:
                bd += wr_packed(T["pointee"])
            if f & F_VER:
                bd += wr_packed(T["version"])
            if f & F_SIZE:
                bd += wr_packed(T["size"]) + wr_packed(T["align"])
            if f & F_ABS:
                bd += wr_packed(T["abstract"])
            if f & F_MEM:
                bd += wr_packed(T.get("nmem_raw", len(T["members"])) & ~0xFFFF | len(T["members"]))
                for mi, (n, fl, off, ty) in enumerate(T["members"]):
                    bd += wr_packed(fidx[n]) + wr_packed(fl) + (wr_packed(T["mem_extra"][mi]) if fl & 0x80 else b"") + wr_packed(off) + wr_packed(ty)
            if f & F_IFC:
                bd += wr_packed(len(T["ifc"]))
                for a, v in T["ifc"]:
                    bd += wr_packed(a) + wr_packed(v)
            if f & F_ATTR:
                bd += wr_packed(T["attr"])
        bd += self.tbdy_tail
        th = bytearray(wr_packed(len(self.thsh)))
        for ti, h in self.thsh:
            th += wr_packed(ti) + struct.pack("<I", h)
        th += self.thsh_pad
        sub = {"TPTR": self.tptr, "TSTR": self.tstr_raw, "TNA1": bytes(tna), "FSTR": self.fstr_raw, "TBDY": bytes(bd),
               "THSH": bytes(th), "TPAD": self.tpad}
        alias = {"TST1": "TSTR", "FST1": "FSTR"}
        return section("TYPE", b"".join(section(k, sub[alias.get(k, k)]) for k in self.type_order), leaf=False)

    def encode_indx(self, items=None, ptch=None):
        items = self.items if items is None else items
        ptch = self.ptch if ptch is None else ptch
        it = b"".join(struct.pack("<III", ty | (fl << 24), off, cnt) for ty, fl, off, cnt in items)
        pt = b"".join(struct.pack("<II", ti, len(lst)) + struct.pack("<%dI" % len(lst), *lst) for ti, lst in ptch)
        return section("INDX", section("ITEM", it) + section("PTCH", pt), leaf=False)

    def encode(self, data=None, items=None, ptch=None):
        data = self.data if data is None else data
        body = section("SDKV", self.sdk.encode()) + section("DATA", data) + self.encode_type() + self.encode_indx(items, ptch)
        return section("TAG0", body, leaf=False)
