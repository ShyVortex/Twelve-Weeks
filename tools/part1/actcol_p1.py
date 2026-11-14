"""Part I (Havok 2020.1) actor collision tagfile reader: sections, type names, ITEM table, PTCH, the DATA image.
(The 2020.1 TBDY body encoding is not decoded: the layouts of the few classes that matter are in actor_collision.py.)"""
import os
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "models"))
import havok_convert as hc  # noqa: E402
import havok_tag as H  # noqa: E402
import p1_convert  # noqa: E402

FG_ID = hc.fnv("COLLISION_DATA_FOREGROUND")


def p1_fg_tags(data):
    """[tag bytes] of every COLLISION_DATA_FOREGROUND item of a Part I actor pak (raw container bytes)"""
    P = p1_convert.parse(data)
    pages = P["pages"]
    base = [0]
    for s, z, f in pages:
        base.append(base[-1] + z)
    mem = b"".join(data[s:s + z] for s, z, f in pages)
    out = []
    for pi, off, tid in p1_convert.scan_items(data, pages):
        if tid == FG_ID:
            b = base[pi] + off + 48
            sz = struct.unpack_from("<I", mem, b + 0x58)[0]
            out.append(bytes(mem[b + 0x60:b + 0x60 + sz]))
    return out


class P1Tag:
    def __init__(self, raw):
        self.raw = raw
        top = H.sections(raw, 0, len(raw))[0]
        secs = {x[0]: x for x in H.sections(raw, top[2], top[3])}
        self.sdk = raw[secs["SDKV"][2]:secs["SDKV"][3]].decode()
        self.data = bytes(raw[secs["DATA"][2]:secs["DATA"][3]])
        ty = secs["TYPE"]
        sub = {x[0]: x for x in H.sections(raw, ty[2], ty[3])}
        tst = raw[sub["TST1"][2]:sub["TST1"][3]].split(b"\0")
        p = raw[sub["TNA1"][2]:sub["TNA1"][3]]
        n, o = H.rd_packed(p, 0)
        self.names = [None]
        for _ in range(1, n):
            nm, o = H.rd_packed(p, o)
            k, o = H.rd_packed(p, o)
            tp = []
            for _ in range(k):
                a, o = H.rd_packed(p, o)
                v, o = H.rd_packed(p, o)
                tp.append((tst[a].decode(), v))
            self.names.append(tst[nm].decode() + ("<%s>" % ",".join("%s=%s" % t for t in tp) if tp else ""))
        ix = {x[0]: x for x in H.sections(raw, secs["INDX"][2], secs["INDX"][3])}
        it = raw[ix["ITEM"][2]:ix["ITEM"][3]]
        self.items = [(self.names[w & 0xFFFFFF] if w & 0xFFFFFF else None, w >> 24, off, cnt)
                      for w, off, cnt in (struct.unpack_from("<III", it, o) for o in range(0, len(it), 12))]
        pt = raw[ix["PTCH"][2]:ix["PTCH"][3]]
        self.ptch = []
        o = 0
        while o < len(pt):
            ti, c = struct.unpack_from("<II", pt, o)
            self.ptch.append((self.names[ti], list(struct.unpack_from("<%dI" % c, pt, o + 8))))
            o += 8 + 4 * c

    def classes(self):
        return [it[0] for it in self.items[1:]]
