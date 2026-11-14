"""In-memory editor for TLOU2-layout paks (version 0xA79, the converter's output): read / write bytes and pointers by file
offset, add pointer fixups, append whole pages, serialize.  Existing pages never move inside themselves, so item tables,
login entries (page, offset) and every existing fixup stay valid; only the file positions of the pages change.

Container (re/part1/pak-converter.md s1, p1_convert.py): header {ver, first-8, login page, login off, page count, page table
off 0x2c, h6, fixup table off; +0x20 trailer size, +0x24 / +0x28 VRAM table page / offset}, page table (start, size, flag),
fixup table {0, entries off, count} + 8-byte entries (src page u16, dst page u16, src offset u32), pages, trailer.
A pointer slot holds the target's offset inside its destination page."""
import struct

MAGIC = 0xDEADBEEFDEADBEEF


def fix_data_off(ft):
    return (ft + 0x64 + 15) // 16 * 16          # (same rule as p1_convert.fix_data_off)


class TPak:
    def __init__(self, data):
        u32 = lambda o: struct.unpack_from("<I", data, o)[0]
        self.ver, _first, self.lp, self.lo, n, self.pt, self.h6, ft = (u32(4 * i) for i in range(8))
        self.trailer_len, self.vram_pg, self.vram_off = u32(0x20), u32(0x24), u32(0x28)
        pages = [struct.unpack_from("<III", data, self.pt + 12 * i) for i in range(n)]
        self.flags = [f for _, _, f in pages]
        self.pages = [bytearray(data[s:s + z]) for s, z, _ in pages]
        fdo, fcnt = u32(ft + 4), u32(ft + 8)
        self.fix = {}                            # (src page, src off) -> dst page
        for i in range(fcnt):
            sp, dp, so = struct.unpack_from("<HHI", data, fdo + 8 * i)
            self.fix[(sp, so)] = dp
        end = max(s + z for s, z, _ in pages)
        self.trailer = data[end:]
        assert len(self.trailer) == self.trailer_len or not self.trailer_len, "trailer size mismatch"
        # file-offset view of the ORIGINAL layout, for callers that think in file offsets (ndpak addresses)
        self.starts = [s for s, _, _ in pages]

    # ------------------------------------------------------------ addressing: (page, offset) <-> original file offset
    def loc(self, a):
        for i, s in enumerate(self.starts):
            if s <= a < s + len(self.pages[i]):
                return i, a - s
        raise ValueError("address %#x is in no page" % a)

    def q(self, pg, off):
        return struct.unpack_from("<Q", self.pages[pg], off)[0]

    def u32(self, pg, off):
        return struct.unpack_from("<I", self.pages[pg], off)[0]

    def ptr(self, pg, off):
        """(dst page, dst offset) of the pointer slot, or None"""
        dp = self.fix.get((pg, off))
        return None if dp is None else (dp, self.q(pg, off))

    def set_ptr(self, pg, off, dpg, doff):
        struct.pack_into("<Q", self.pages[pg], off, doff)
        self.fix[(pg, off)] = dpg

    def items(self):
        """[(type name, page, payload offset)] from the page item tables"""
        out = []
        for pi, p in enumerate(self.pages):
            cnt = struct.unpack_from("<H", p, 18)[0]
            for k in range(cnt):
                ro = struct.unpack_from("<I", p, 20 + 16 * k + 8)[0]
                tn = struct.unpack_from("<Q", p, ro + 8)[0]
                e = p.index(b"\0", tn)
                out.append((p[tn:e].decode("latin1"), pi, ro + 48))
        return out

    # ------------------------------------------------------------ new data
    def add_page(self, body, fixups=(), flag=0):
        """append a page holding `body` (no items); fixups = [(offset in body, dst page, dst offset)] for pointer slots inside
        it (dst page None = this new page).  Returns (page index, offset of body[0] inside the page)."""
        shift = 32                               # 20-byte header padded to 16 (no item table)
        b = bytearray(body)
        while (shift + len(b)) % 16:
            b.append(0)
        pg = len(self.pages)
        hdr = struct.pack("<QIIHH", MAGIC, 0, shift + len(b), flag, 0)
        self.pages.append(bytearray(hdr) + bytearray(shift - len(hdr)) + b)
        self.flags.append(flag)
        self.starts.append(-1)
        for off, dpg, doff in fixups:
            self.set_ptr(pg, shift + off, pg if dpg is None else dpg, doff + (shift if dpg is None else 0))
        return pg, shift

    def item_entries(self, pg):
        """[(entry index, name offset, item offset)] of page pg's item table (header u16 +18 = count, 16-byte entries from +20:
        {u64 name offset, u32 item offset, u32 0x12345}); an item = 48-byte header {u64 name off, u64 type off, u32 payload size,
        7 x u32 0x12345} + payload, name / type offsets page-relative plain offsets (no fixups)"""
        p = self.pages[pg]
        return [(k,) + struct.unpack_from("<QI", p, 20 + 16 * k) for k in range(struct.unpack_from("<H", p, 18)[0])]

    def drop_item(self, pg, ro):
        """remove the item whose header sits at (pg, ro) from its page's item table (the bytes stay; nothing moves).  Used when an
        item is superseded by a larger copy in an appended page (e.g. VRAM_DESC_TABLE): tools that list items see one of each."""
        p = self.pages[pg]
        ents = self.item_entries(pg)
        keep = [bytes(p[20 + 16 * k:36 + 16 * k]) for k, _n, o in ents if o != ro]
        if len(keep) == len(ents):
            raise ValueError("no item at page %d +%#x" % (pg, ro))
        p[20:20 + 16 * len(ents)] = b"".join(keep) + bytes(16)
        struct.pack_into("<H", p, 18, len(keep))

    def append_trailer(self, data, align=0x200):
        """append texture data (VRAM_DESC payload +8 = offset into the trailer, +0x10 = size) -> its offset"""
        t = bytearray(self.trailer)
        while len(t) % align:
            t.append(0)
        off = len(t)
        t += data
        self.trailer = bytes(t)
        self.trailer_len = len(self.trailer)
        return off

    def commit(self, builders):
        """append the pages of PageBuilder objects (in order) -> [page index]; builders may point at each other ('B', builder, local)"""
        first = len(self.pages)
        for i, b in enumerate(builders):
            b.page = first + i
        for b in builders:
            b._emit(self)
        return [b.page for b in builders]

    # ------------------------------------------------------------ output
    def serialize(self):
        npg = len(self.pages)
        ft = self.pt + 12 * npg
        fdo = fix_data_off(ft)
        fix = sorted((sp, dp, so) for (sp, so), dp in self.fix.items())
        first = fdo + 8 * len(fix) + 8
        head = bytearray(first)
        struct.pack_into("<8I", head, 0, self.ver, first - 8, self.lp, self.lo, npg, self.pt, self.h6, ft)
        struct.pack_into("<III", head, 0x20, len(self.trailer), self.vram_pg, self.vram_off)
        pos = first
        for i, p in enumerate(self.pages):
            struct.pack_into("<I", p, 12, len(p))            # page header size field
            struct.pack_into("<III", head, self.pt + 12 * i, pos, len(p), self.flags[i])
            pos += len(p)
        struct.pack_into("<III", head, ft, 0, fdo, len(fix))
        for i, (sp, dp, so) in enumerate(fix):
            struct.pack_into("<HHI", head, fdo + 8 * i, sp, dp, so)
        return bytes(head) + b"".join(bytes(p) for p in self.pages) + self.trailer


FILL = 0x12345
PAGE_MAX = 0xFF000                               # stock pages stay below 1 MiB (largest seen 0xfff50)


class PageBuilder:
    """one new page: typed items (in its item table, like the game's own) and plain objects.  Offsets handed out are LOCAL (relative
    to the body); pointer slots are recorded as (local src, target) with target (page, offset) of an existing page, ('L', local) inside
    this page or ('B', other builder, local).  TPak.commit([...]) lays the pages out:
      header 20 bytes {magic, 0, size, u16 flag, u16 item count} + 16-byte item entries, padded to 16 (flag-4 shader pages of the game
      start their data at +20; with no items we pad to 32 like TPak.add_page), body, then the item name / type strings."""

    def __init__(self, flag=0):
        self.flag, self.body, self.fix, self.items, self.page = flag, bytearray(), [], [], None
        self.strings = {}

    def size(self):
        return len(self.body)

    def blob(self, data, align=16):
        while len(self.body) % align:
            self.body.append(0)
        off = len(self.body)
        self.body += data
        return off

    def reserve(self, n, align=16):
        return self.blob(bytes(n), align)

    def ptr(self, local, target):
        """pointer slot at body offset `local` -> target ((page, off) | ('L', local) | ('B', builder, local))"""
        self.fix.append((local, target))

    def item(self, name, typ, payload, align=16):
        """a typed item: 48-byte header + payload; -> local offset of the PAYLOAD (item header = payload - 48)"""
        while (len(self.body) + 48) % align:
            self.body.append(0)
        h = len(self.body)
        self.body += bytes(48)
        self.body += payload
        self.items.append((h, name, typ, len(payload)))
        return h + 48

    def loc(self, local):
        """page offset of a local offset (valid after commit)"""
        return self._base + local

    def _emit(self, tp):
        names = []
        for _h, nm, ty, _n in self.items:
            names += [nm, ty]
        sb = bytearray()
        soff = {}
        for s in names:
            if s not in soff:
                soff[s] = len(sb)
                sb += s.encode("latin1") + b"\0"
        hdr = 20 + 16 * len(self.items)
        base = (hdr + 15) // 16 * 16 if self.items else 32
        self._base = base
        body = bytearray(self.body)
        while len(body) % 16:
            body.append(0)
        str_at = base + len(body)
        page = bytearray(base) + body + sb
        while len(page) % 16:
            page.append(0)
        if len(page) > PAGE_MAX:
            raise ValueError("PageBuilder: page of %#x bytes is over the %#x limit" % (len(page), PAGE_MAX))
        struct.pack_into("<QIIHH", page, 0, MAGIC, 0, len(page), self.flag, len(self.items))
        for k, (h, nm, ty, n) in enumerate(self.items):
            struct.pack_into("<QII", page, 20 + 16 * k, str_at + soff[nm], base + h, FILL)
            struct.pack_into("<QQI7I", page, base + h, str_at + soff[nm], str_at + soff[ty], n, *([FILL] * 7))
        pg = self.page
        tp.pages.append(page)
        tp.flags.append(self.flag)
        tp.starts.append(-1)
        for src, tg in self.fix:
            if tg[0] == "L":
                tp.set_ptr(pg, base + src, pg, base + tg[1])
            elif tg[0] == "B":
                tp.set_ptr(pg, base + src, tg[1].page, tg[1]._base_of() + tg[2])
            else:
                tp.set_ptr(pg, base + src, tg[0], tg[1])

    def _base_of(self):
        """body base of a builder that may not be emitted yet (same rule as _emit)"""
        hdr = 20 + 16 * len(self.items)
        return (hdr + 15) // 16 * 16 if self.items else 32
