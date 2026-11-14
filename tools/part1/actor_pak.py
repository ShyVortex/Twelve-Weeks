"""Put a translated 2017.1 collision tag into a converted Part I actor pak (the TLOU2-layout output of p1_convert + p1_abi).

The COLLISION_DATA_FOREGROUND item carries its tagfile inline (item + 0x60), and the translated tag is bigger than the Part I one, so the item cannot
grow in place without moving everything behind it in the page.  Instead the item moves to a NEW page appended after the last one (the way
p1_fires.add_point_lights adds its page): header + item table with one record, the item header (name / type strings in a pool), the body (version
0x100d, body count, pointer to the pointer table, tag size), the tag, the pointer table and the runtime body images (+68: 0x12 -> 0x11, the value
every stock TLOU2 body image carries).  The old record is dropped from the old page's item table, its fixups (table slots) are dropped, the login
table entry (PAK_LOGIN_TABLE lists the item) points at the new page.  The old bytes stay behind as dead data.

  python actor_pak.py <converted pak> [out]       # dumps the FG item of a pak
"""
import os
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import p1_convert  # noqa: E402

MAGIC, PAD, MARK = p1_convert.MAGIC, p1_convert.PAD, 0x12345
Q, I = struct.Struct("<Q"), struct.Struct("<I")
VERSION_T2 = 0x100D
BODY_FLAGS_T2 = 0x11


def _cstr(d, a):
    return bytes(d[a:d.index(b"\0", a)]).decode("latin1")


class Pak:
    def __init__(self, data):
        self.d = bytes(data)
        d = self.d
        u = lambda o: I.unpack_from(d, o)[0]
        self.ver, self.first, self.lp, self.lo, self.n, self.pt, self.h6, self.ft = (u(4 * i) for i in range(8))
        self.tr_len, self.vp, self.vo = u(0x20), u(0x24), u(0x28)
        self.pages = [struct.unpack_from("<III", d, self.pt + 12 * i) for i in range(self.n)]
        fdo, fc = u(self.ft + 4), u(self.ft + 8)
        self.fix = [struct.unpack_from("<HHI", d, fdo + 8 * i) for i in range(fc)]
        self.end = max(s + z for s, z, _ in self.pages)

    def items(self):
        """[(page, record index, header offset in page, name, type)]"""
        out = []
        for pi, (st, sz, fl) in enumerate(self.pages):
            cnt = struct.unpack_from("<H", self.d, st + 18)[0]
            for k in range(cnt):
                h = I.unpack_from(self.d, st + 20 + 16 * k + 8)[0]
                out.append((pi, k, h, _cstr(self.d, st + Q.unpack_from(self.d, st + h)[0]), _cstr(self.d, st + Q.unpack_from(self.d, st + h + 8)[0])))
        return out

    def slot_target(self, pi, so):
        """page index + page offset a fixed-up pointer slot (page pi, offset so) points at"""
        for sp, dp, o in self.fix:
            if sp == pi and o == so:
                return dp, Q.unpack_from(self.d, self.pages[pi][0] + so)[0]
        return None


def fg_items(pak):
    return [it for it in Pak(pak).items() if it[4] == "COLLISION_DATA_FOREGROUND"]


def read_fg(p, item):
    """-> dict(version, count, tag_size, tag, bodies, extent (page-relative [lo, hi) the item and its table occupy), table slots)"""
    pi, k, h, name, typ = item
    st = p.pages[pi][0]
    b = h + 48
    d = p.d
    ver, cnt = struct.unpack_from("<II", d, st + b)
    tsz = I.unpack_from(d, st + b + 0x58)[0]
    tag = d[st + b + 0x60:st + b + 0x60 + tsz]
    tp = p.slot_target(pi, b + 8)
    assert tp is not None and tp[0] == pi, "pointer table slot has no fixup"
    bodies = []
    for j in range(cnt):
        t = p.slot_target(pi, tp[1] + 8 * j)
        assert t is not None and t[0] == pi
        bodies.append(d[st + t[1]:st + t[1] + 0xB0])
    return {"item": item, "version": ver, "count": cnt, "tag_size": tsz, "tag": tag, "bodies": bodies, "table": tp[1],
            "head": d[st + h:st + h + 48], "body": d[st + b:st + b + 0x60], "name": name}


def build_page(rd, tag, flag):
    """-> (page bytes, header offset 48, fixups [(slot offset, target offset)])"""
    n = rd["count"]
    tag = bytes(tag)
    assert len(tag) % 4 == 0, len(tag)
    shift = 48
    hdr = 48
    body = hdr + 48
    tag_o = body + 0x60
    tab_o = (tag_o + len(tag) + 15) // 16 * 16
    bod_o = (tab_o + 8 * n + 15) // 16 * 16
    pool = (bod_o + 0xB0 * n + 15) // 16 * 16
    names = [rd["name"], "COLLISION_DATA_FOREGROUND"]
    po, pool_b = {}, bytearray()
    for s in names:
        if s not in po:
            po[s] = len(pool_b)
            pool_b += s.encode("latin1") + b"\0"
    size = (pool + len(pool_b) + 15) // 16 * 16
    pg = bytearray(size)
    struct.pack_into("<QIIHH", pg, 0, MAGIC, 0, size, flag, 1)
    struct.pack_into("<IIII", pg, 20, pool, 0, hdr, MARK)
    old = rd["head"]
    pg[hdr:hdr + 48] = old
    Q.pack_into(pg, hdr, pool + po[rd["name"]])
    Q.pack_into(pg, hdr + 8, pool + po["COLLISION_DATA_FOREGROUND"])
    I.pack_into(pg, hdr + 16, 0x60 + len(tag) + 48)
    ob = bytearray(rd["body"])
    struct.pack_into("<II", ob, 0, VERSION_T2, n)
    Q.pack_into(ob, 8, tab_o)
    ob[0x28:0x30] = bytes(8)                           # source name pointers: none in Part I data
    ob[0x38:0x40] = bytes(8)
    I.pack_into(ob, 0x58, len(tag))
    pg[body:body + 0x60] = ob
    pg[tag_o:tag_o + len(tag)] = tag
    fixes = [(body + 8, tab_o)]
    for j, bd in enumerate(rd["bodies"]):
        b = bytearray(bd)
        I.pack_into(b, 68, BODY_FLAGS_T2)
        pg[bod_o + 0xB0 * j:bod_o + 0xB0 * (j + 1)] = b
        Q.pack_into(pg, tab_o + 8 * j, bod_o + 0xB0 * j)
        fixes.append((tab_o + 8 * j, bod_o + 0xB0 * j))
    pg[pool:pool + len(pool_b)] = pool_b
    return bytes(pg), hdr, fixes


def replace_fg(pak, tags):
    """pak with its COLLISION_DATA_FOREGROUND items (in item order) carrying `tags` (translated 2017.1 tags)"""
    p = Pak(pak)
    d = bytearray(p.d)
    fgs = fg_items(p.d)
    assert len(fgs) == len(tags), (len(fgs), len(tags))
    pages = [bytearray(d[s:s + z]) for s, z, _ in p.pages]
    flags = [f for _, _, f in p.pages]
    fix = set(p.fix)
    login_fix = {}
    new_pages = []
    for item, tag in zip(fgs, tags):
        rd = read_fg(p, item)
        pi, k, h, _, _ = item
        newpi = len(pages) + len(new_pages)
        pg, nh, fx = build_page(rd, tag, flags[pi])
        new_pages.append(pg)
        # drop the old record (compact the table), its fixups
        pgb = pages[pi]
        cnt = struct.unpack_from("<H", pgb, 18)[0]
        recs = [bytes(pgb[20 + 16 * j:36 + 16 * j]) for j in range(cnt)]
        del recs[k]
        pgb[20:20 + 16 * cnt] = b"".join(recs) + bytes(16)
        struct.pack_into("<H", pgb, 18, cnt - 1)
        lo_, hi_ = rd["item"][2], rd["table"] + 8 * rd["count"]
        pgb[lo_:rd["table"] + 8 * rd["count"]] = bytes(rd["table"] + 8 * rd["count"] - lo_)     # the old item (header, body, Part I tag, table) is dead: zeroed
        for j in range(rd["count"]):
            bo = Q.unpack_from(p.d, p.pages[pi][0] + rd["table"] + 8 * j)[0]
            pgb[bo:bo + 0xB0] = bytes(0xB0)
        # item k+1.. keep their header offsets; only the record order moved
        fix = {e for e in fix if not (e[0] == pi and lo_ <= e[2] < hi_)}
        fix |= {(newpi, newpi, so) for so, _ in fx}
        # fixups of the new page point inside it: (slot page, target page, slot offset)
        login_fix[(pi, h)] = (newpi, nh)
    # login table entries
    lp, lo = p.lp, p.lo
    lb = lo + PAD
    cnt = I.unpack_from(pages[lp], lb)[0]
    for i in range(cnt):
        e = struct.unpack_from("<II", pages[lp], lb + 8 + 8 * i)
        if e in login_fix:
            struct.pack_into("<II", pages[lp], lb + 8 + 8 * i, *login_fix[e])
    out_pages = pages + [bytearray(x) for x in new_pages]
    out_flags = flags + [flags[item[0]] for item in fgs]
    nf = sorted(fix)
    npg = len(out_pages)
    ft2 = p.pt + 12 * npg
    fdo2 = p1_convert.fix_data_off(ft2)
    first2 = fdo2 + 8 * len(nf) + 8
    head = bytearray(first2)
    head[:p.pt] = p.d[:p.pt]
    struct.pack_into("<8I", head, 0, p.ver, first2 - 8, p.lp, p.lo, npg, p.pt, p.h6, ft2)
    struct.pack_into("<III", head, 0x20, p.tr_len, p.vp, p.vo)
    pos = first2
    for i, pg in enumerate(out_pages):
        struct.pack_into("<III", head, p.pt + 12 * i, pos, len(pg), out_flags[i])
        pos += len(pg)
    struct.pack_into("<III", head, ft2, 0, fdo2, len(nf))
    for i, (s_, d_, o_) in enumerate(nf):
        struct.pack_into("<HHI", head, fdo2 + 8 * i, s_, d_, o_)
    return bytes(head) + b"".join(bytes(x) for x in out_pages) + p.d[p.end:]


if __name__ == "__main__":
    pk = open(sys.argv[1], "rb").read()
    for it in fg_items(pk):
        rd = read_fg(Pak(pk), it)
        print(it, "version %#x bodies %d tag %d" % (rd["version"], rd["count"], rd["tag_size"]))
