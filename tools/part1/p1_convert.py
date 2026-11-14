"""Part I PC pak (version 0xA7D) -> TLOU2 PC pak (version 0xA79) converter.

What differs (measured, re/part1/day-one-results.md section 2 and re/part1/pak-converter.md):
  - TLOU2 pages start with a 20-byte header (DEADBEEF x2, 0, page size, u16 flag, u16 item count) + a 16-byte table entry
    per item; every pointer is an offset from the page start INCLUDING that header.  Part I pages are raw.
  - TLOU2 items have a 48-byte header {u64 name ptr, u64 type-name ptr, u32 size, 7 x 0x12345}; Part I headers carry a
    64-bit type id (FNV-1a-64 of the type name) instead of the strings.  Strings are appended to each page.
  - TLOU2 lists EVERY item in its page's table; Part I lists only the top-level ones in the login table.  The converter
    finds all items by their marker pattern.
  - GEOMETRY_1 keeps Part I's format version 0x37 and 176-byte submesh records: the engine upgrades the payload to 0x39 (192-byte
    records, re-linked pointers) itself when it loads the level (exe+18986b0); converting the records here as well made the engine
    convert them twice (crash exe+173c2d0, re/part1/geometry-upgrade.md).
  - header: +0x28 = offset of the VRAM_DESC_TABLE item, no 16-byte extension, page table at 0x2c.
Items whose type name is unknown (hash not in TYPE_NAMES) are not listed (their data stays in the page).

  python p1_convert.py <in.pak> <out.pak>
  python p1_convert.py --check <converted.pak> <original p1 pak>      # round trip with ndpak
  python p1_convert.py --repage <converted.pak> <out.pak>              # split pages > 1 MiB (convert does it; T2R_P1_REPAGE=0 = off)
"""
import collections
import os
import struct
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "models"))
import p1_pak  # noqa: E402

MARK = struct.pack("<I", 0x12345)
MAGIC = 0xDEADBEEFDEADBEEF
PAD = 48
ITEM_NAMES = {p1_pak.fnv(n): n for n in ("num_light_tables", "SpawnerGroup")}   # Part I name hash -> the TLOU2 item name string the loader hashes
LEVEL_NAME_FORMS = ("backgroundSection.%s",)
BLOB_MAX = 0x4000   # longest straddling non-item object the converter moves (seen: 0x3f0)
FIX_DATA_MIN = 0  # (was 0xE0: for >=29 pages ft+12.. runs into the 8 fixup group records the engine walks - crash exe+12e44c0)


def fix_data_off(ft):
    """TLOU2: the fixup table is 8 group records of 12 bytes (page, offset, count; only group 0 used) and the 8-byte entries start
    at round16(ft + 0x64) in every real pak (ft+0x68 / 0x6c / 0x64 seen); the loader (exe+12e4460) reads all 8 groups"""
    return (ft + 0x64 + 15) // 16 * 16


def parse(data):
    u32 = lambda o: struct.unpack_from("<I", data, o)[0]
    ver, _hs, login_page, login_off, n, pt, nfp, ft = (u32(4 * i) for i in range(8))
    assert ver in (0xA7D, 0x10A7D), f"not a Part I pak (version {ver:#x})"      # 0x10A7D = texture dictionary
    pages = [struct.unpack_from("<III", data, pt + 12 * i) for i in range(n)]
    fdo, fcnt = u32(ft + 4), u32(ft + 8)
    fix = []
    for i in range(fcnt):
        sp, dp, so = struct.unpack_from("<HHI", data, fdo + 8 * i)
        fix.append([sp, dp, so])
    end = max(s + z for s, z, _ in pages)
    return {"version": ver, "hdr6": nfp, "login": (login_page, login_off), "pages": pages, "fix": fix, "trailer": data[end:],
            "vram_table_hint": u32(0x28)}


def scan_items(data, pages):
    """[(page, header offset in page, type id)] - the 48-byte item headers are found by their 0x12345 markers"""
    out = []
    for pi, (st, sz, fl) in enumerate(pages):
        j = data.find(MARK, st, st + sz)
        while 0 <= j < st + sz:
            h = j - 8
            if (h >= st and data[h + 12:h + 16] == MARK and data[h + 20:h + 24] == MARK and data[h + 40:h + 44] == MARK
                    and data[h + 44:h + 48] == MARK and h + 48 <= st + sz):
                out.append((pi, h - st, struct.unpack_from("<Q", data, h + 32)[0]))
                j = h + 48
                continue
            j = data.find(MARK, j + 4, st + sz)
    return out


def u64(b, o):
    return struct.unpack_from("<Q", b, o)[0]


def merge_flag0_pages(data, P):
    """Part I's flag-0 pages (CPU data) are ONE contiguous memory cut into 2 MiB chunks: any object (a vis kd-tree, a material array, a
    list of small records) may run over a chunk end.  TLOU2 allocates every page separately, so a chunk end must never fall inside an
    object.  The pages are contiguous in the file, so they are merged into one page here (table entries, fixups, slot values, login
    entries are re-based) and `repage` later cuts the big page again at object starts only (item headers / pointer targets outside item
    extents and pointer slots).  Seen on the Bookstore: the rear level's vis kd-tree (344 x 24-byte nodes) cut 40 bytes before the end of
    a chunk -> VisProbe::Decode read the tail from unrelated memory (crash exe+18557d0, read of -1) in a 2-client match."""
    pages = P["pages"]
    groups = []
    for i, (s, z, f) in enumerate(pages):
        if groups and f == 0 and pages[i - 1][2] == 0 and groups[-1][-1] == i - 1 and pages[i - 1][0] + pages[i - 1][1] == s:
            groups[-1].append(i)
        else:
            groups.append([i])
    if all(len(g) == 1 for g in groups):
        return data, P, 0
    d = bytearray(data)
    newidx, base = {}, {}
    for gi, g in enumerate(groups):
        b = 0
        for i in g:
            newidx[i], base[i] = gi, b
            b += pages[i][1]
    newpages = [(pages[g[0]][0], sum(pages[i][1] for i in g), pages[g[0]][2]) for g in groups]
    lp, lo = P["login"]
    la = pages[lp][0] + lo                                   # login table item (file offset); entries are (page, offset) pairs, not pointers
    lcnt = struct.unpack_from("<I", d, la + PAD)[0]
    lrange = (la, la + PAD + 8 + 8 * lcnt)
    fix = []
    for sp, dp, so in P["fix"]:
        a = pages[sp][0] + so                                # (contiguous file: a slot past its page end lives in the next page)
        if lrange[0] <= a < lrange[1]:
            continue
        v = u64(d, a)
        if dp in base:
            struct.pack_into("<Q", d, a, v + base[dp])
        sp2, so2 = sp, so
        if sp in base:
            sp2, so2 = newidx[sp], so + base[sp]
        fix.append([sp2, newidx[dp], so2])
    for k in range(lcnt):
        o = la + PAD + 8 + 8 * k
        pg, off = struct.unpack_from("<II", d, o)
        struct.pack_into("<II", d, o, newidx[pg], off + base[pg])
    P = dict(P, pages=newpages, fix=fix, login=(newidx[lp], lo + base[lp]))
    return bytes(d), P, sum(len(g) - 1 for g in groups)


def convert(data, report=None, textures=None, drop=0, level=None):
    P = parse(data)
    data, P, merged = merge_flag0_pages(data, P)
    pages = P["pages"]
    cont = [bytearray(data[s:s + z]) for s, z, _ in pages]
    sizes = [z for _, z, _ in pages]
    # Part I treats consecutive pages as one memory (2 MiB chunks): a pointer slot recorded past its page end lives at
    # the start of the next page
    fix = P["fix"]
    for f in fix:
        while f[2] >= sizes[f[0]] and f[0] + 1 < len(pages):
            f[2] -= sizes[f[0]]
            f[0] += 1
    stats0 = len([1 for f in fix if f[2] >= sizes[f[0]]])
    flags = [f for _, _, f in pages]
    stats = collections.Counter()
    stats["flag-0 pages merged"] = merged
    items = scan_items(data, pages)
    names = dict(p1_pak.TYPES)
    if os.environ.get("T2R_P1_KEEP_UNKNOWN", "1") != "0":
        names.update(p1_pak.KEEPABLE)
    keep = [(pi, off, tid) for pi, off, tid in items if tid in names]
    stats["items found"] = len(items)
    stats["items listed"] = len(keep)
    stats["items skipped (unknown type)"] = len(items) - len(keep)
    unknown = collections.Counter(p1_pak.EXTRA_TYPES.get(t, "%016x" % t) for _, _, t in items if t not in names)

    # ---- items that run past their page end (the login table of a 2 MiB page): copy them to the end of the page
    remaps = []
    keep2, login_loc = [], list(P["login"])
    for pi, off, tid in keep:
        size = struct.unpack_from("<I", data, pages[pi][0] + off + 16)[0]
        if off + PAD + size > pages[pi][1]:
            region = bytearray(data[pages[pi][0] + off: pages[pi][0] + off + PAD + size])
            while len(cont[pi]) % 16:
                cont[pi].append(0)
            new = len(cont[pi])
            cont[pi] += region
            tail = off + PAD + size - pages[pi][1]       # bytes of the item that lie at the start of the next page
            for f in fix:
                if f[0] == pi and off <= f[2] < off + PAD + size:
                    f[2] += new - off
                elif f[0] == pi + 1 and 0 <= f[2] < tail:
                    # a slot in the item's tail: the continuation pass above re-homed it to the next page, but it belongs to the
                    # item (EFFECT straddling a 2 MiB page end lost its last 25 fixups: crash exe+18a44be)
                    f[0] = pi
                    f[2] = new + (pages[pi][1] - off) + f[2]
            remaps.append((pi, off, off + PAD + size, lambda v, a=off, n=new: v - a + n))
            if [pi, off] == login_loc:
                login_loc = [pi, new]
            keep2.append((pi, new, tid))
            stats["straddling items moved"] += 1
        else:
            keep2.append((pi, off, tid))
    keep = keep2
    P["login"] = tuple(login_loc)
    # ---- NON-item objects (material arrays, small records, ... anything a pointer targets) that run past a page end into the
    # next page of the same flag.  Part I's pages of one flag are one contiguous memory, so such an object is simply
    # continuous there; TLOU2 allocates every page separately, the loader reads the object's tail from whatever follows the
    # page in memory.  Seen on the Bookstore: a 0x3f0-byte material array (9 x 0x70 records) cut at the 2 MiB mark,
    # its records' submesh indices (+0x48) read garbage (see re/part1/page-straddle.md).  Same remedy as for items: the
    # object (from its start to the next object start) is copied to the end of its page and every pointer is remapped.
    item_offs = collections.defaultdict(set)
    for pi, off, tid in items:
        item_offs[pi].add(off)
    tstarts = collections.defaultdict(set)
    for sp, dp, so in fix:
        v, d_ = u64(cont[sp], so), dp
        if any(r[0] == d_ and r[1] <= v < r[2] for r in remaps):
            continue                                    # points into an item that was moved above
        while v >= sizes[d_] and d_ + 1 < len(pages) and flags[d_ + 1] == flags[d_]:
            v -= sizes[d_]
            d_ += 1
        if v < sizes[d_]:
            tstarts[d_].add(v)
    for pi in range(len(pages) - 1):
        if flags[pi] != flags[pi + 1]:
            continue
        sa, sb = tstarts[pi] | item_offs[pi], tstarts[pi + 1] | item_offs[pi + 1]
        if not sa or not sb:
            continue
        S, E, B = max(sa), min(sb), sizes[pi]
        if S in item_offs[pi] or E == 0 or S >= B:
            continue                                    # the last object is an item (handled above) or ends exactly at the page end
        if (B - S) + E > BLOB_MAX:
            stats["straddling blobs NOT moved (too long)"] += 1
            continue
        while len(cont[pi]) % 16:
            cont[pi].append(0)
        new = len(cont[pi])
        cont[pi] += bytes(cont[pi][S:B]) + bytes(cont[pi + 1][:E])
        for f in fix:
            if f[0] == pi and S <= f[2] < B:
                f[2] += new - S
            elif f[0] == pi + 1 and f[2] < E:
                f[0] = pi
                f[2] = new + (B - S) + f[2]
        remaps.append((pi, S, B + E, lambda v, a=S, n=new: v - a + n))
        stats["straddling blobs moved"] += 1
        stats["straddling blob bytes"] += (B - S) + E
    # ---- GEOMETRY_1: the submesh records stay in Part I's 176-byte layout.  The payload starts with a format version dword
    # (Part I 0x37, TLOU2 0x39) and BgGeometry's loader (tlou-ii.exe+18986b0) upgrades older payloads IN PLACE, version by
    # version (0x36 -> 0x37 -> 0x38 -> 0x39): 0x37 -> 0x38 rebuilds the group records (0x98 -> 0xb0 bytes), 0x38 -> 0x39 copies
    # the submesh array (176 -> 192 bytes, exe+1418991a0) and re-links every pointer into it by index.  An earlier version of this
    # converter relocated the records to 192 bytes itself and left the version at 0x37: the engine then converted the already
    # converted array again, read record 0 as {stream count = vertex count 1090, 2nd stream count = index count, 2nd stream
    # pointer = 0} and crashed at exe+173c2d0 (null stream, BgGeometry::ProcessLogin; re/part1/geometry-upgrade.md).
    arrays = []                     # (page, array start, count): the 176-byte records, for the name slot below
    for pi, off, tid in keep:
        if names[tid] != "GEOMETRY_1":
            continue
        b = off + PAD
        cnt = struct.unpack_from("<I", cont[pi], b + 8)[0]
        slot = next((f for f in fix if f[0] == pi and f[2] == b + 40), None)
        if cnt == 0 or slot is None:            # no submeshes (script / empty levels)
            continue
        assert struct.unpack_from("<I", cont[pi], b)[0] == 0x37, "GEOMETRY_1 payload is not format 0x37 (Part I)"
        arrays.append((slot[1], u64(cont[pi], b + 40), cnt))
        stats["submeshes (engine upgrades 176 -> 192)"] += cnt
    # ---- string pools (one per page that holds items): "" + every type name used
    per_page = collections.defaultdict(list)
    for pi, off, tid in keep:
        per_page[pi].append((off, tid))
    # the page holding the geometry arrays also needs an empty string for the submesh name slot
    sm_name_pages = {dp for dp, *_ in remaps} | {dp for dp, *_ in arrays}
    pools = {}
    # Part I items carry the 64-bit FNV hash of their name at +0x18 (not the string); TLOU2's loader dispatches TAG_INT by the hash
    # of the name string (exe+1b99ef0: 'num_light_tables' allocates the per-level light table arrays - without it the first
    # LIGHT_TABLE_1 writes through a null array, crash exe+1b99761)
    item_name = {}
    known = dict(ITEM_NAMES)
    if level:
        # level-dependent names (stock: 'backgroundSection.<level>' on BACKGROUND_SECTION); the pak name keeps its -phys / -ingame suffix
        for pref in LEVEL_NAME_FORMS:
            known[p1_pak.fnv(pref % level)] = pref % level
    if any(names[t] in ("NAV_MESH_1", "NAV_MESH_HEIGHT_MAP_TEX_1") for _, _, t in keep):
        for i in range(4000):                                   # stock: 'accessibility-nav-<n>' and '<same>-heightMapTex'
            for nm_ in ("accessibility-nav-%d" % i, "accessibility-nav-%d-heightMapTex" % i):
                known[p1_pak.fnv(nm_)] = nm_
    for pi, off, tid in keep:
        h = u64(cont[pi], off + 0x18)
        if h in known:
            item_name[(pi, off)] = known[h]
    for pi in sorted(set(per_page) | sm_name_pages):
        pool = bytearray()
        offs = {"": 0}
        pool += b"\0"
        for nm in sorted({n for (p_, _), n in item_name.items() if p_ == pi}):
            offs["\0" + nm] = len(pool)
            pool += nm.encode() + b"\0"
        for tid in sorted({t for _, t in per_page.get(pi, [])}):
            offs[names[tid]] = len(pool)
            pool += names[tid].encode() + b"\0"
        while len(pool) % 16:
            pool.append(0)
        base = len(cont[pi])
        cont[pi] += pool
        pools[pi] = (base, offs)
    # submesh name slot (+0x20): Part I has none -> the empty string of the page (the slot's fixup must target that same page)
    for dp, old, cnt in arrays:
        named = {f[2]: f for f in fix if f[0] == dp and old <= f[2] < old + 176 * cnt and (f[2] - old) % 176 == 0x20}
        for i in range(cnt):
            so = old + 176 * i + 0x20
            struct.pack_into("<Q", cont[dp], so, pools[dp][0])
            if so in named:
                named[so][1] = dp
            else:
                fix.append([dp, dp, so])
    # ---- per-page shift = header (20) + table (16 per item)
    n_items = {pi: len(per_page.get(pi, [])) for pi in range(len(pages))}
    # TLOU2 objects sit at offsets that are 0 / 8 mod 16 INCLUDING the header (measured: AMBSHADOWS, TEXTURE_TABLE, collision ...), as
    # Part I's do from the raw page start: the header + table region is padded to 16 so no alignment changes
    shift = [(20 + 16 * n_items[pi] + 15) // 16 * 16 for pi in range(len(pages))]
    # ---- pointer values: remap into relocated arrays, then + destination page shift; slots + source page shift
    def remap_target(dp, v):
        for rdp, a, b, fn in remaps:
            if rdp == dp and a <= v < b:
                return fn(v)
        return v
    # the login table entries are (page, offset) pairs, not pointers: Part I has fixups on some of them (they sit in the
    # table's page-1 continuation), TLOU2 has none -> drop those so the pairs are not shifted
    _lp, _lo = P["login"]
    _cnt = struct.unpack_from("<I", cont[_lp], _lo + PAD)[0]
    n0 = len(fix)
    fix[:] = [f for f in fix if not (f[0] == _lp and _lo <= f[2] < _lo + PAD + 8 + 8 * _cnt)]
    stats["login fixups dropped"] = n0 - len(fix)
    array_slots = {(dp, old + 176 * i + 0x20) for dp, old, cnt in arrays for i in range(cnt)}   # name slots: already final page offsets
    done = set()
    for f in fix:
        sp, dp, so = f
        if (sp, so) in done:
            continue
        done.add((sp, so))
        v = u64(cont[sp], so)
        if (sp, so) not in array_slots:         # (the submesh name slots already hold their final offset in their own page)
            while v >= sizes[dp] and dp + 1 < len(pages) and v < pages[dp][1] + 0x4000000 and not any(
                    r[0] == dp and r[1] <= v < r[2] for r in remaps):
                v -= sizes[dp]                  # a target past the page end lies in the next page
                dp += 1
                f[1] = dp
            v = remap_target(dp, v)
        struct.pack_into("<Q", cont[sp], so, v + shift[dp])
    # ---- item headers (in place) + tables
    new_hdr_off = {}
    for pi, lst in per_page.items():
        base, offs = pools[pi]
        for off, tid in lst:
            h = off
            size = struct.unpack_from("<I", cont[pi], h + 16)[0]
            nm_off = offs["\0" + item_name[(pi, off)]] if (pi, off) in item_name else 0
            hdr = struct.pack("<QQI", base + nm_off + shift[pi], base + offs[names[tid]] + shift[pi], size) + MARK * 7
            cont[pi][h:h + 48] = hdr
    # ---- login table payload: entries (page, offset) shifted; unknown types dropped
    lp, lo = P["login"]
    lb = lo + PAD
    cnt = struct.unpack_from("<I", cont[lp], lb)[0]
    ent = [struct.unpack_from("<II", cont[lp], lb + 8 + 8 * i) for i in range(cnt)]
    listed = {(pi, off) for pi, off, tid in keep}
    good = [(pg, o) for pg, o in ent if (pg, o) in listed]
    if os.environ.get('T2R_P1_DEBUG'):
        print('login entries read:', ent, 'login at', lp, lo)
        print('fixups on the login payload:', [f for f in fix if f[0] == lp and lo <= f[2] < lo + 48 + 8 + 8 * cnt])
        print('login dropped:', [(e, p1_pak.TYPES.get(next((t for p, o, t in items if (p, o) == e), None), '-')) for e in ent if e not in listed])
    stats["login entries"] = len(ent)
    stats["login entries kept"] = len(good)
    struct.pack_into("<I", cont[lp], lb, len(good))
    for i in range(cnt):
        if i < len(good):
            struct.pack_into("<II", cont[lp], lb + 8 + 8 * i, good[i][0], good[i][1] + shift[good[i][0]])
        else:
            struct.pack_into("<II", cont[lp], lb + 8 + 8 * i, 0, 0)
    # ---- optional: real textures instead of the 64x64 stubs, embedded in the trailer (the way the actor texture injection works)
    if textures is not None:
        # The engine's TextureMgrPub::ConsumeData (exe+12e7ee5, assert "offset + length <= m_startOffset + m_vramSize") streams the
        # trailer front to back and hands each chunk to the VRAM_DESC whose [offset, offset + size) holds it: the descriptors sorted
        # by offset must tile the trailer from byte 0 WITHOUT gaps and every size is a multiple of 512 (all 207 / 568 descriptors of
        # real TLOU2 paks).  So the trailer is rebuilt from scratch: replaced textures padded to 512 with the padding inside the size,
        # kept stubs copied from the old trailer.
        old = P["trailer"]
        trailer = bytearray()
        n_tex = n_missing = 0
        for pi, off, tid in keep:
            if names[tid] != "VRAM_DESC":
                continue
            b = off + 16                                  # descriptor base: payload offset +0x28, size +0x30, hash +0x38 ...
            t = textures.get(u64(cont[pi], b + 0x38), drop)
            if t is None:
                o_off, o_sz = struct.unpack_from("<II", cont[pi], b + 0x28)[0], struct.unpack_from("<I", cont[pi], b + 0x30)[0]
                data = old[o_off:o_off + o_sz]
                n_missing += 1
            else:
                data = t["data"]
                struct.pack_into("<I", cont[pi], b + 0x50, t["mips"])
                struct.pack_into("<II", cont[pi], b + 0x54, t["w"], t["h"])
                n_tex += 1
            data = bytes(data) + bytes(-len(data) % 512)
            struct.pack_into("<I", cont[pi], b + 0x28, len(trailer))
            struct.pack_into("<I", cont[pi], b + 0x30, len(data))
            trailer += data
        P["trailer"] = bytes(trailer)
        stats["textures embedded"] = n_tex
        stats["textures kept as stubs"] = n_missing
        stats["texture mips dropped"] = drop
    # ---- assemble pages: header + table + content
    out_pages = []
    for pi in range(len(pages)):
        lst = sorted(per_page.get(pi, []))
        body = bytearray(cont[pi])
        while (shift[pi] + len(body)) % 16:
            body.append(0)
        tbl = bytearray()
        for off, tid in lst:
            tbl += struct.pack("<IIII", pools[pi][0] + shift[pi], 0, off + shift[pi], 0x12345)
        size = shift[pi] + len(body)
        hdr = struct.pack("<QIIHH", MAGIC, 0, size, flags[pi], len(lst))
        out_pages.append(bytes(hdr) + bytes(tbl) + bytes(shift[pi] - 20 - len(tbl)) + bytes(body))
    # ---- file: header, page table, fixup table, pages, trailer
    npg = len(pages)
    pt = 0x2C
    ft = pt + 12 * npg
    fdo = fix_data_off(ft)
    new_fix = sorted((sp, dp, so + shift[sp]) for sp, dp, so in fix if True)
    seen, uniq = set(), []
    for sp, dp, so in new_fix:
        if (sp, so) not in seen:
            seen.add((sp, so))
            uniq.append((sp, dp, so))
    first = fdo + 8 * len(uniq) + 8
    starts, pos = [], first
    for pg in out_pages:
        starts.append(pos)
        pos += len(pg)
    vram = [(pi, off) for pi, off, tid in keep if names[tid] == "VRAM_DESC_TABLE"]
    vram_off = vram[0][1] + shift[vram[0][0]] if vram else 0
    vram_page = vram[0][0] if vram else 0     # header +0x24 (page) / +0x28 (offset): the sorted VRAM table of the loader (exe+1717d30; crash exe+1717d03)
    head = bytearray(first)
    struct.pack_into("<8I", head, 0, P["version"] - 4, first - 8, lp, lo + shift[lp], npg, pt, P["hdr6"], ft)
    struct.pack_into("<III", head, 0x20, len(P["trailer"]), vram_page, vram_off)
    for i, (st, pg) in enumerate(zip(starts, out_pages)):
        struct.pack_into("<III", head, pt + 12 * i, st, len(pg), flags[i])
    struct.pack_into("<III", head, ft, 0, fdo, len(uniq))
    for i, (sp, dp, so) in enumerate(uniq):
        struct.pack_into("<HHI", head, fdo + 8 * i, sp, dp, so)
    out = bytes(head) + b"".join(out_pages) + P["trailer"]
    if os.environ.get("T2R_P1_REPAGE", "1") != "0":
        rp = {}
        out = repage(out, report=rp)
        for k, v in rp.items():
            stats["repage " + k] = v
    if report is not None:
        report.update(stats)
        report["unknown types"] = dict(unknown)
        report["pages"] = npg
        report["fixups"] = len(uniq)
    return out


PAGE_LIMIT = 0xFFF00      # every page of every TLOU2 pak seen is below 1 MiB (max 0xfff10), data pages (flag 4 / 5 / 9) too
ALIGN = 256               # a cut keeps every object's offset mod 256 (GPU buffer pages)


def _protected(data):
    """{page: [(start, end)]} byte ranges that must not be cut: item extents and every GEOMETRY_1 vertex / index buffer"""
    import tempfile
    import ndpak
    fd, tmp = tempfile.mkstemp(suffix=".pak")
    os.write(fd, data)
    os.close(fd)
    try:
        p = ndpak.Pak(tmp)
    finally:
        os.remove(tmp)
    starts = [s for s, _, _ in p.pages]
    out = collections.defaultdict(list)

    def add(a, size):
        if not a or size <= 0:
            return
        pi = max(i for i, s in enumerate(starts) if s <= a)
        out[pi].append((a - starts[pi], a - starts[pi] + size))
    for name, typ, pi, io in p.items:
        add(io, PAD + p.u32(io + 16))
    for sm in p.submeshes:
        add(sm["index"], 2 * sm["icount"])
        for st in sm["streams"]:
            add(st["buf"], st["size"])
    for a, size in _payload_arrays(p):     # crash exe+173c2d0: hun-checkpoint-maze / -barricade had the GEOMETRY_1
        add(a, size)                       # submesh array cut by a page end (a group list points into it = a "legal" cut)
    return out


def _payload_arrays(p):
    """[(absolute offset, size)] of the arrays geometry_extent_check requires inside one page: GEOMETRY_1 submesh / material /
    texture binding / technique arrays + their sub-arrays, SPECULAR_CUBEMAPSET records, VIS_INFO_1 kd-trees"""
    out = []

    def arr(slot, size):
        if slot in p.fix and size > 0:
            out.append((p.ptr(slot), size))
            return p.ptr(slot)
        return None
    for name, typ, pi, io in p.items:
        b = io + 0x30
        if typ == "GEOMETRY_1":
            nsub, nmat, ntex, ntech = p.u32(b + 8), p.u32(b + 0x10), p.u32(b + 0x14), p.u32(b + 0x18)
            rs, c0 = (192, 0x88) if p.u32(b) >= 0x39 else (176, 0x80)
            sub = arr(b + 0x28, rs * nsub)
            mats = arr(b + 0x38, 8 * nmat)
            arr(b + 0x40, 0x28 * ntex)
            tech = arr(b + 0x48, 0x130 * ntech)
            for i in range(nsub if sub else 0):
                o = sub + rs * i
                arr(o + 0x30, 64 * p.u32(o + c0 + 8))
                arr(o + 0x38, 64 * p.u32(o + c0 + 12))
            for i in range(nmat if mats else 0):
                if (mats + 8 * i) not in p.fix:
                    continue
                m = p.ptr(mats + 8 * i)
                arr(m + 0x98, 0x70 * p.u32(m + 0xd4))
                arr(m + 0xa8, 0x20 * struct.unpack_from("<H", p.d, m + 0xee)[0])
            for i in range(ntech if tech else 0):
                e = tech + 0x130 * i
                arr(e + 0x20, 0x30 * p.u32(e + 0x114))
        elif typ == "SPECULAR_CUBEMAPSET":
            arr(b, 256 * p.u32(b + 8))
        elif typ == "VIS_INFO_1" and (b + 0x10) in p.fix:
            va = p.ptr(b + 0x10)
            nrec = p.u32(b + 4)
            out.append((va, 72 * nrec))
            for k in range(nrec):
                e = va + 72 * k
                if p.u32(e) and (e + 8) in p.fix:
                    out.append((p.ptr(e + 8), 16 * p.u32(e)))
                if (e + 0x10) not in p.fix:
                    continue
                t = p.ptr(e + 0x10)
                seen, stack, hi = set(), [0], 0
                while stack and len(seen) < 1 << 20:
                    i = stack.pop()
                    if i < 0 or i in seen or t + 24 * i + 24 > len(p.d):
                        continue
                    seen.add(i)
                    hi = max(hi, i)
                    nd = t + 24 * i
                    stack += [struct.unpack_from("<i", p.d, nd)[0] >> 2, struct.unpack_from("<i", p.d, nd + 4)[0]]
                out.append((t, 24 * (hi + 1)))
    return out


def repage(data, limit=PAGE_LIMIT, report=None):
    """split the pages of a TLOU2-layout pak (converter output) that are larger than `limit`.
    The TLOU2 loader (tlou-ii.exe 0x1417181e0) takes pages < 0x1f8000 from its page pool, larger ones from a fallback
    allocator, and only for version >= 0xa7c (Part I) knows 2 MiB pages; converted Part I pages keep Part I's 2 MiB and grow
    past it with the inserted headers.  Every pointer goes through the fixup table, so a page can be cut where no object
    spans: cuts are put at item headers or pointer targets that are not inside an item, a GEOMETRY_1 vertex / index buffer
    or a pointer slot; each new page gets its own header, item table and type-name pool, offsets keep their value mod 256."""
    u32 = lambda o: struct.unpack_from("<I", data, o)[0]
    ver, first, lp, lo, n, pt, h6, ft = (u32(4 * i) for i in range(8))
    trailer_len, vram_pg, vram_off = u32(0x20), u32(0x24), u32(0x28)
    pages = [struct.unpack_from("<III", data, pt + 12 * i) for i in range(n)]
    fdo, fcnt = u32(ft + 4), u32(ft + 8)
    fix = [struct.unpack_from("<HHI", data, fdo + 8 * i) for i in range(fcnt)]
    end = max(s + z for s, z, _ in pages)
    trailer = data[end:]
    if all(z <= limit for _, z, _ in pages):
        if report is not None:
            report["pages split"] = 0
        return data
    prot = _protected(data)
    targets = collections.defaultdict(set)
    slots = collections.defaultdict(list)
    for sp, dp, so in fix:
        targets[dp].add(struct.unpack_from("<Q", data, pages[sp][0] + so)[0])
        slots[sp].append((so, so + 8))
    plan, newp = [], []           # plan[old page] = [(new index, start, end)]; newp = (old page, start, end, items, flag)
    for pi, (st, sz, fl) in enumerate(pages):
        cnt = struct.unpack_from("<H", data, st + 18)[0]
        items = sorted((u32(st + 20 + 16 * k + 8), u32(st + u32(st + 20 + 16 * k + 8) + 16)) for k in range(cnt))
        shift = (20 + 16 * cnt + 15) // 16 * 16
        if sz <= limit:
            plan.append([(len(newp), 0, sz)])
            newp.append((pi, 0, sz, items, fl))
            continue
        iv = prot.get(pi, []) + slots.get(pi, [])
        # keep the two tables on one page when they are close (merged flag-0 pages: 2 MiB apart on the Bookstore main level, where the
        # old 2 MiB chunks had them on different pages already - the loader reads the login table by (page, offset) and the VRAM
        # table by header +0x24 / +0x28, independently)
        if pi == lp and vram_off and any(h == vram_off for h, _ in items) and abs(lo - vram_off) < 0x40000:
            iv.append((min(lo, vram_off), max(lo, vram_off) + PAD + 16))
        iv = sorted(iv)
        cand = sorted({h for h, _ in items} | {t for t in targets.get(pi, ()) if shift < t < sz})
        legal, j, reach = [], 0, 0                # a candidate is legal when no protected range strictly contains it
        for c in cand:
            while j < len(iv) and iv[j][0] < c:
                reach = max(reach, iv[j][1])
                j += 1
            if reach <= c:
                legal.append(c)
        cuts, cur = [shift], shift
        room = limit - 20 - 16 * (cnt + 1) - 0x200 - ALIGN
        k = 0
        while sz - cur > room:
            best = None
            while k < len(legal) and legal[k] - cur <= room:
                if legal[k] > cur:
                    best = legal[k]
                k += 1
            if best is None:                      # nothing legal in reach: the next legal cut (an oversized page)
                nxt = [c for c in legal if c > cur]
                if not nxt:
                    break
                best = nxt[0]
            cuts.append(best)
            cur = best
        cuts.append(sz)
        chunks = []
        for a, b in zip(cuts, cuts[1:]):
            chunks.append((len(newp), a, b))
            newp.append((pi, a, b, [(h, s) for h, s in items if a <= h < b], fl))
        plan.append(chunks)
    out_pages, delta = [], []
    for k, (pi, a, b, items, fl) in enumerate(newp):
        st = pages[pi][0]
        if a == 0:                                # unsplit page: copied as is
            out_pages.append(bytearray(data[st:st + b]))
            delta.append(0)
            continue
        shift = (20 + 16 * len(items) + 15) // 16 * 16
        pad = (a - shift) % ALIGN                 # new offset = old - a + shift + pad == old (mod ALIGN)
        d = shift + pad - a
        body = bytearray(pad) + bytearray(data[st + a:st + b])
        while len(body) % 16:
            body.append(0)
        pool, offs, names, inames = bytearray(b"\0"), {"": 0}, [], []
        for h, size in items:
            t = data[st + struct.unpack_from("<Q", data, st + h + 8)[0]:].split(b"\0", 1)[0].decode()
            n = data[st + struct.unpack_from("<Q", data, st + h)[0]:].split(b"\0", 1)[0].decode()   # the item's own name (num_light_tables ...)
            names.append(t)
            inames.append(n)
            for x in (t, n):
                if x not in offs:
                    offs[x] = len(pool)
                    pool += x.encode() + b"\0"
        pool_off = shift + len(body)
        body += pool
        while len(body) % 16:
            body.append(0)
        tbl = bytearray()
        for (h, size), t, n in zip(items, names, inames):
            nh = h + d
            struct.pack_into("<QQ", body, nh - shift, pool_off + offs[n], pool_off + offs[t])
            tbl += struct.pack("<IIII", pool_off, 0, nh, 0x12345)
        hdr = struct.pack("<QIIHH", MAGIC, 0, shift + len(body), fl, len(items))
        out_pages.append(bytearray(hdr + bytes(tbl) + bytes(shift - 20 - len(tbl)) + body))
        delta.append(d)

    def remap(pi, off):
        ch = plan[pi]
        if len(ch) == 1 and newp[ch[0][0]][1] == 0:
            return ch[0][0], off
        for k, a, b in ch:
            if a <= off < b or (off == b and k == ch[-1][0]):
                return k, off + delta[k]
        k = ch[0][0]                              # header / table area of a split page
        return k, off + delta[k]
    nf = set()
    for sp, dp, so in fix:
        v = struct.unpack_from("<Q", data, pages[sp][0] + so)[0]
        ns, nso = remap(sp, so)
        nd, nv = remap(dp, v)
        struct.pack_into("<Q", out_pages[ns], nso, nv)
        nf.add((ns, nd, nso))
    nlp, nlo = remap(lp, lo)
    lb = nlo + PAD
    cnt = struct.unpack_from("<I", out_pages[nlp], lb)[0]
    for i in range(cnt):
        epg, eo = struct.unpack_from("<II", out_pages[nlp], lb + 8 + 8 * i)
        struct.pack_into("<II", out_pages[nlp], lb + 8 + 8 * i, *remap(epg, eo))
    vp, vo = remap(vram_pg, vram_off) if vram_off else (0, 0)
    nf = sorted(nf)
    npg = len(out_pages)
    ft2 = pt + 12 * npg
    fdo2 = fix_data_off(ft2)
    first2 = fdo2 + 8 * len(nf) + 8
    head = bytearray(first2)
    struct.pack_into("<8I", head, 0, ver, first2 - 8, nlp, nlo, npg, pt, h6, ft2)
    struct.pack_into("<III", head, 0x20, trailer_len, vp, vo)
    pos = first2
    for i, pg in enumerate(out_pages):
        struct.pack_into("<III", head, pt + 12 * i, pos, len(pg), newp[i][4])
        pos += len(pg)
    struct.pack_into("<III", head, ft2, 0, fdo2, len(nf))
    for i, (s_, d_, o_) in enumerate(nf):
        struct.pack_into("<HHI", head, fdo2 + 8 * i, s_, d_, o_)
    if report is not None:
        report["pages split"] = sum(1 for c in plan if len(c) > 1)
        report["pages"] = npg
        report["max page"] = hex(max(len(p) for p in out_pages))
        report["pages over limit"] = sum(1 for p in out_pages if len(p) > limit)
    return bytes(head) + b"".join(bytes(p) for p in out_pages) + trailer


def check(conv_path, p1_path):
    """round trip: read the converted pak with ndpak and compare with the Part I reader"""
    import ndpak
    import p1mesh
    a = ndpak.Pak(conv_path)
    b = p1mesh.P1Mesh(p1_path)
    ok = True
    typ = collections.Counter(t for _, t, _, _ in a.items)
    nm = dict(p1_pak.TYPES)
    if os.environ.get("T2R_P1_KEEP_UNKNOWN", "1") != "0":
        nm.update(p1_pak.KEEPABLE)
    src = collections.Counter(nm.get(t, "?") for _, _, t in scan_items(b.d, b.pages))
    src.pop("?", None)
    print("items:", dict(typ))
    if typ != src:
        print("  MISMATCH vs source", dict(src))
        ok = False
    ta = [s for s in a.submeshes]
    tb = b.submesh_table()
    print("submeshes", len(ta), len(tb))
    ok &= len(ta) == len(tb)
    bad = 0
    for si, (sa, sb) in enumerate(zip(ta, tb)):
        if sa["vcount"] != sb["vcount"] or sa["icount"] != sb["icount"]:
            bad += 1
            print("  submesh", si, "counts", (sa["vcount"], sa["icount"]), (sb["vcount"], sb["icount"]))
            continue
        pa = a.positions(sa)
        pb = b.mesh(sb)["P"]
        if pa is None or not np.allclose(np.array(pa), pb, atol=1e-5):
            bad += 1
            print("  submesh", si, "positions differ", [s["type"] for s in sa["streams"]], [s["type"] for s in sb["streams"]])
        ia = np.array(a.indices(sa))
        ib = b.mesh(sb)["I"].reshape(-1)
        if not (ia == ib).all():
            bad += 1
    print("submesh content mismatches:", bad)
    ok &= bad == 0
    # every fixup lands inside its destination page
    off_bad = 0
    for addr, dp in a.fix.items():
        v = a.q(addr)
        if dp >= len(a.pages) or v >= a.pages[dp][1]:
            off_bad += 1
    print("fixups", len(a.fix), "out of page:", off_bad)
    ends = sorted(st + sz for st, sz, _ in a.pages)
    cross = 0
    for sm in a.submeshes:
        for lo_, size in [(sm["index"], 2 * sm["icount"])] + [(x["buf"], x["size"]) for x in sm["streams"]]:
            if lo_ and any(lo_ < e < lo_ + size for e in ends):
                cross += 1
    print("geometry buffers crossing a page end:", cross, " pages > 1 MiB:", sum(1 for _, sz, _ in a.pages if sz > PAGE_LIMIT))
    ok &= cross == 0
    ok &= off_bad == 0
    tx = ndpak.textures(a)
    print("textures", len(tx), "(source", len(b.tex_hashes), ")")
    print("ROUND TRIP", "OK" if ok else "FAILED")
    return ok


def main(argv):
    if len(argv) >= 4 and argv[1] == "--repage":
        rp = {}
        out = repage(open(argv[2], "rb").read(), report=rp)
        open(argv[3], "wb").write(out)
        print(argv[2], "->", argv[3], rp)
        return 0
    if len(argv) >= 4 and argv[1] == "--check":
        return 0 if check(argv[2], argv[3]) else 1
    if len(argv) < 3:
        print(__doc__)
        return 1
    rep = {}
    out = convert(open(argv[1], "rb").read(), rep)
    open(argv[2], "wb").write(out)
    print(argv[1], "->", argv[2], len(out), "bytes", dict(rep))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))


def loader_check(path):
    """mirror of the engine's fixup walker (tlou-ii.exe+12e4460, crash dump): [hdr+0x18] must be 8; the table at hdr[7] is
    8 groups of 12 bytes (page index, entry offset within that page's memory, count) read as overlapping dwords from ft; each
    entry is {u16 src page, u16 dst page, u32 src offset}.  Returns a list of problems (empty = the walk is clean)."""
    d = open(path, "rb").read()
    u32 = lambda o: struct.unpack_from("<I", d, o)[0]
    bad = []
    ver, hsz, lp, lo, npg, pt, groups, ft = (u32(4 * i) for i in range(8))
    if ver != 0xA79:
        bad.append(f"version {ver:#x}")
    if groups != 8:
        bad.append(f"[hdr+0x18] = {groups}, the loader wants 8")
    pages = [struct.unpack_from("<III", d, pt + 12 * i) for i in range(npg)]
    if pt + 12 * npg > ft:
        bad.append("page table runs into the fixup table")
    if ft + 4 + 12 * groups + 4 > len(d):
        return bad + ["fixup table past the end"]
    for g in range(min(groups, 8)):
        page, off, cnt = (u32(ft + 4 + 12 * g - 4 + 4 * k) for k in range(3))
        if cnt == 0:
            continue
        if g and page != 0:
            bad.append(f"group {g}: page {page} count {cnt}")
        if page >= npg and page != 0:
            bad.append(f"group {g}: page index {page} >= {npg}")
            continue
        base = 0 if page == 0 and g == 0 else pages[page][0]   # (page 0 of group 0 is the file base in the table walk)
        for i in range(cnt):
            o = base + off + 8 * i
            if o + 8 > len(d):
                bad.append(f"group {g}: entry {i} past the end")
                break
            sp, dp, so = struct.unpack_from("<HHI", d, o)
            if sp >= npg or dp >= npg:
                bad.append(f"group {g} entry {i}: pages {sp}/{dp} of {npg}")
                break
            if so + 8 > pages[sp][1]:
                bad.append(f"group {g} entry {i}: offset {so:#x} past page {sp} ({pages[sp][1]:#x})")
                break
    return bad


def vram_check(path):
    """mirror of the engine's VRAM table step (tlou-ii.exe+1717d30): header +0x24 / +0x28 = page / offset of the VRAM_DESC_TABLE item;
    the loader reads count = u32 at item+0x30 and qsorts the 8-byte entries behind it.  Problems list (empty = ok)."""
    d = open(path, "rb").read()
    u32 = lambda o: struct.unpack_from("<I", d, o)[0]
    n, pt = u32(16), u32(20)
    vp, vo = u32(0x24), u32(0x28)
    pages = [struct.unpack_from("<III", d, pt + 12 * i) for i in range(n)]
    if vo == 0:
        return []
    if vp >= n:
        return [f"vram page {vp} >= {n}"]
    st, sz, _ = pages[vp]
    if vo + 0x38 > sz:
        return [f"vram offset {vo:#x} past page {vp} ({sz:#x})"]
    io = st + vo
    tp = struct.unpack_from("<Q", d, io + 8)[0]
    if tp >= sz:
        return [f"vram item type pointer {tp:#x} outside its page"]
    name = d[st + tp:st + tp + 24].split(b"\0")[0]
    if name != b"VRAM_DESC_TABLE":
        return [f"item at page {vp} +{vo:#x} is {name!r}, not VRAM_DESC_TABLE"]
    cnt = u32(io + 0x30)
    size = u32(io + 16)
    if cnt * 8 + 8 > size and cnt * 8 > size:
        return [f"vram count {cnt} does not fit the item size {size:#x}"]
    return []


def vram_sort_check(path):
    """resolve the VRAM table entries like the loader (fixup-relocated pointers) and read the sort key at target+0x38
    (the qsort comparator exe+1717d00).  Problems list."""
    import ndpak
    p = ndpak.Pak(path)
    d = p.d
    u32 = lambda o: struct.unpack_from("<I", d, o)[0]
    vp, vo = u32(0x24), u32(0x28)
    if not vo:
        return []
    io = p.pages[vp][0] + vo
    cnt = u32(io + 0x30)
    bad = []
    for i in range(cnt):
        slot = io + 0x38 + 8 * i
        dp = p.fix.get(slot)
        if dp is None:
            bad.append(f"entry {i}: no fixup")
            break
        tgt = p.q(slot) + p.pages[dp][0]
        if not (p.pages[dp][0] <= tgt and tgt + 0x40 <= p.pages[dp][0] + p.pages[dp][1]):
            bad.append(f"entry {i}: target {tgt:#x} outside page {dp}")
            break
    return bad


def trailer_check(path):
    """mirror of TextureMgrPub::ConsumeData's expectation (exe+12e7ee5): the VRAM_DESCs sorted by offset tile the trailer from
    0 to its end with no gap / overlap and every size is a multiple of 512.  Problems list."""
    import ndpak
    p = ndpak.Pak(path)
    d = p.d
    end = max(s + z for s, z, _ in p.pages)
    tr = len(d) - end
    rows = []
    for n, t, pi, io in p.items:
        if t == "VRAM_DESC":
            b = io + 16
            rows.append((struct.unpack_from("<I", d, b + 0x28)[0], struct.unpack_from("<I", d, b + 0x30)[0]))
    rows.sort()
    bad = []
    pos = 0
    for off, sz in rows:
        if sz == 0:
            continue
        if off != pos:
            bad.append(f"descriptor at {off:#x} (size {sz:#x}) but the previous one ends at {pos:#x}")
            break
        if sz % 512:
            bad.append(f"size {sz:#x} at {off:#x} is not a multiple of 512")
            break
        pos = off + sz
    else:
        if rows and pos != tr:
            bad.append(f"descriptors end at {pos:#x}, the trailer is {tr:#x} long")
    return bad


def lights_check(path):
    """mirror of the loader's light-table setup (exe+1b99f6d / +1b99761): every LIGHT_TABLE_1 is stored into arrays that are only
    allocated by the TAG_INT item named 'num_light_tables' (count byte at payload +0).  Problems list."""
    import ndpak
    p = ndpak.Pak(path)
    n_lt = sum(1 for _, t, _, _ in p.items if t == "LIGHT_TABLE_1")
    if not n_lt:
        return []
    tags = [(n, struct.unpack_from("<B", p.d, io + 0x30)[0]) for n, t, _, io in p.items if t == "TAG_INT" and n == "num_light_tables"]
    if not tags:
        return [f"{n_lt} LIGHT_TABLE_1 but no TAG_INT 'num_light_tables'"]
    if tags[0][1] < n_lt:
        return [f"num_light_tables = {tags[0][1]} < {n_lt} LIGHT_TABLE_1"]
    return []


def pointer_pattern_check(path, types=("EFFECT", "LIGHT_TABLE_1", "MATERIAL_TABLE_1", "VRAM_DESC", "TEXTURE_TABLE", "POPULATOR_1", "KD_TREE_2")):
    """items of one type and size carry the same pointer slots; one that has fewer fixups than the majority pattern has lost slots
    (e.g. an item that straddled a 2 MiB Part I page end: the loader dereferences the unrelocated page offset, crash exe+18a44be).
    Problems list."""
    import ndpak
    import bisect
    p = ndpak.Pak(path)
    d = p.d
    fixa = sorted(p.fix)
    groups = collections.defaultdict(list)
    for n, t, pi, io in p.items:
        if t in types:
            sz = struct.unpack_from("<I", d, io + 16)[0]
            lo = io + 0x30
            s = frozenset(a - lo for a in fixa[bisect.bisect_left(fixa, lo):bisect.bisect_left(fixa, lo + sz)])
            groups[(t, sz)].append((pi, io - p.pages[pi][0], s))
    bad = []
    for (t, sz), lst in groups.items():
        if len(lst) < 3:
            continue
        common = collections.Counter(s for _, _, s in lst).most_common(1)[0][0]
        for pi, off, s in lst:
            lost = [o for o in common - s if struct.unpack_from("<Q", d, p.pages[pi][0] + off + 0x30 + o)[0] != 0]   # (a slot that is simply 0 is a real null)
            if lost:
                bad.append(f"{t} (size {sz}) at page {pi} +{off:#x}: {len(lost)} pointer slots with a value but no fixup (+{lost[0]:#x} ...)")
    return bad[:5]


def geometry_extent_check(path):
    """mirror of what BgGeometry::ProcessLogin walks (tlou-ii.exe+167cc80 / +17bcfb0): every array reachable from the
    GEOMETRY_1 payload must lie inside ONE page (TLOU2 allocates pages separately; Part I's pages are one contiguous memory, an
    object cut at a page end reads its tail from unrelated memory), and the per-material records (+0x98, 0x70 bytes each) must
    carry a submesh index +0x48 in [0, submesh count) - the loader sets bit `index` of a bitset sized for the submesh count.
    Also: the payload format version must match the record size (0x37: 176-byte records the engine upgrades itself, 0x39: 192), each submesh's stream arrays and the technique sub-arrays.  Problems list."""
    import ndpak
    p = ndpak.Pak(path)
    d = p.d
    bad = []

    def inside(what, slot, size):
        """the pointer in `slot` (needs a fixup) -> target..target+size must be inside its page"""
        if slot not in p.fix:
            return None
        t = p.ptr(slot)
        pi = p.fix[slot]
        z = p.pages[pi][1]
        off = t - p.pages[pi][0]
        if off + size > z:
            bad.append(f"{what}: {size:#x} bytes at page {pi} +{off:#x} run {off + size - z:#x} past the page end ({z:#x})")
            return None
        return t
    for name, typ, pi, io in p.items:
        if typ != "GEOMETRY_1":
            continue
        b = io + 0x30
        nsub, nmat, ntex, ntech = p.u32(b + 8), p.u32(b + 0x10), p.u32(b + 0x14), p.u32(b + 0x18)
        ver = p.u32(b)
        # the layout the ENGINE reads the records in: 192 bytes only when the payload says format 0x39, else 176 (it upgrades
        # older payloads in place: exe+18986b0 / +1418991a0).  A 192-byte array under version 0x37 (the first Bookstore
        # conversion) is read with the wrong stride: record 0 got stream count = vertex count and a 2nd stream list = index count
        # with a null pointer -> crash exe+173c2d0.
        rs, c0 = (192, 0x88) if ver >= 0x39 else (176, 0x80)
        if ver not in (0x37, 0x39):
            bad.append(f"GEOMETRY_1 payload format {ver:#x} (expected 0x37 Part I or 0x39 TLOU2)")
        sub = inside("submesh array", b + 0x28, rs * nsub)
        mats = inside("material pointer list", b + 0x38, 8 * nmat)
        inside("texture binding array", b + 0x40, 0x28 * ntex)
        tech = inside("technique array", b + 0x48, 0x130 * ntech)
        for i in range(nsub if sub else 0):
            o = sub + rs * i
            n1, n2 = p.u32(o + c0 + 8), p.u32(o + c0 + 12)
            if not 1 <= n1 <= 16 or n2:
                bad.append(f"submesh {i} (format {ver:#x}, {rs}-byte records): stream counts {n1} / {n2} - records are not laid out as the engine will read them")
                break
            for sl, n, esz, nm in ((0x30, n1, 64, "stream array"), (0x38, n2, 64, "stream array 2")):
                if n and (o + sl) not in p.fix:
                    bad.append(f"submesh {i}: {nm} count {n} but no pointer at +{sl:#x}")
                elif n:
                    inside(f"submesh {i} {nm}", o + sl, esz * n)
            if len(bad) > 8:
                break
        for i in range(nmat if mats else 0):
            if (mats + 8 * i) not in p.fix:
                bad.append(f"material {i}: pointer without fixup")
                continue
            m = p.ptr(mats + 8 * i)
            n1, n2 = struct.unpack_from("<H", d, m + 0xee)[0], p.u32(m + 0xd4)
            a2 = inside(f"material {i} records", m + 0x98, 0x70 * n2) if n2 else 0
            inside(f"material {i} +0xa8 array", m + 0xa8, 0x20 * n1) if n1 else None
            if n2 and not a2 and (m + 0x98) not in p.fix:
                bad.append(f"material {i}: {n2} records but no pointer at +0x98")
            for k in range(n2 if a2 else 0):
                idx = struct.unpack_from("<i", d, a2 + 0x70 * k + 0x48)[0]
                if not 0 <= idx < nsub:
                    bad.append(f"material {i} record {k}: submesh index {idx} (submesh count {nsub})")
                    break
            if len(bad) > 8:
                break
        for i in range(ntech if tech else 0):
            e = tech + 0x130 * i
            n = p.u32(e + 0x114)
            if n and (e + 0x20) in p.fix:
                inside(f"technique {i} sub-array", e + 0x20, 0x30 * n)
            if len(bad) > 8:
                break
    # SPECULAR_CUBEMAPSET (loader case 61 -> exe+141749310): {ptr to count x 256-byte probe records, count, format byte +0xd = 3}; every
    # record's texture key (+0xf0) must be the hash of a VRAM_DESC of this pak (the cubemap), its name pointer (+0xe0) relocated.
    vh = {struct.unpack_from("<Q", d, io + 16 + 0x38)[0] for n_, t_, p_, io in p.items if t_ == "VRAM_DESC"}
    for name, typ, pi, io in p.items:
        if typ != "SPECULAR_CUBEMAPSET":
            continue
        b = io + 0x30
        cnt = p.u32(b + 8)
        if d[b + 0xd] != 3:
            bad.append(f"probe set format byte {d[b + 0xd]} (the engine converts only 2 -> 3)")
        arr = inside("probe records", b, 256 * cnt)
        for k in range(cnt if arr else 0):
            r = arr + 256 * k
            if (r + 0xe0) not in p.fix:
                bad.append(f"probe {k}: name pointer without fixup")
                break
            if struct.unpack_from("<Q", d, r + 0xf0)[0] not in vh:
                bad.append(f"probe {k}: texture key {struct.unpack_from('<Q', d, r + 0xf0)[0]:#x} is no VRAM_DESC of this pak")
                break
    # VIS_INFO_1 (VisProbe::Decode, exe+17bc140 / +17bf620 / +18557a0): per record (72 bytes at payload+0x10, count payload+4) a
    # kd-tree of 24-byte nodes at record+0x10 ({axis|child<<2, child, split, -, -, leaf data ptr at +0x10}); a leaf is a node whose
    # +0x10 is non-zero and must be a fixup'd pointer to the compressed vis bits.  A tree cut by a page end reads its tail from other
    # memory (the crash exe+18557d0: leaf pointer = garbage / -1).
    for name, typ, pi, io in p.items:
        if typ != "VIS_INFO_1":
            continue
        b = io + 0x30
        arr = inside("vis records", b + 0x10, 72 * p.u32(b + 4)) if (b + 0x10) in p.fix else None
        for k in range(p.u32(b + 4) if arr else 0):
            e = arr + 72 * k
            # crash exe+17bf925 (convex-volume point test, 16-byte planes at +8, count +0): hun-underpass-midground's
            # records 36.. were garbage (count 74565, no fixup) - the record array was cut by a page end
            npl = p.u32(e)
            if npl and (e + 8) not in p.fix:
                bad.append(f"vis record {k}: {npl} planes but no pointer at +8")
                break
            if npl:
                inside(f"vis record {k} planes", e + 8, 16 * npl)
            if (e + 0x10) not in p.fix:
                continue
            t, dpg = p.ptr(e + 0x10), p.fix[e + 0x10]
            ps, pz = p.pages[dpg][0], p.pages[dpg][1]
            seen, stack = set(), [0]
            while stack and len(bad) < 8:
                i = stack.pop()
                if i < 0 or i in seen:
                    continue
                seen.add(i)
                nd = t + 24 * i
                if nd + 24 > ps + pz:
                    bad.append(f"vis record {k}: kd-tree node {i} runs past its page (page {dpg} +{nd - ps:#x}, page size {pz:#x})")
                    break
                if p.q(nd + 0x10) and (nd + 0x10) not in p.fix:
                    bad.append(f"vis record {k}: leaf node {i} data pointer {p.q(nd + 0x10):#x} has no fixup")
                    break
                stack += [struct.unpack_from("<i", d, nd)[0] >> 2, struct.unpack_from("<i", d, nd + 4)[0]]
    return bad[:8]


def full_audit(conv_paths, ref_paths, out=print):
    """see p1_audit.full_audit (per item type: ours against stock TLOU2 paks, loader switch coverage, header / table checks)"""
    import p1_audit
    return p1_audit.full_audit(conv_paths, ref_paths, out)
