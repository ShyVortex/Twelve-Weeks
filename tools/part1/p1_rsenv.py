"""Part I render settings for a converted Part I map (re/part1/geometry-upgrade.md s11).

Why: TLOU2 picks its render settings (auto-exposure range + set point, sun direction / colour / intensity, sky, fog, bloom,
shadow cascades ...) per camera position from REGION_TREE regions tagged  render-settings = "*symbol*"  (the symbol is a
map in a DC render-settings module).  A converted Part I level sits at Part I's coordinates, outside every TLOU2 region
(the Downtown set's regions are at x -900..680, z -1460..-290; the Bookstore at x 58..139, z 254..366), so it rendered with
the engine's base settings: exposure for a sunny exterior (Part I's Bookstore asks for tonemap light range 4 .. 4.85, i.e.
~16x brighter than TLOU2's outdoor -1.5 .. 1.5) -> the baked lightmaps (intact, same encoding and magnitude as TLOU2's)
read as near black, only the sun patches show.

What this builds, all from the Part I install (Part I content is never committed; outputs go to the conv dir):
  * <rs-level>-ingame.pak  a TLOU2 -ingame pak holding one REGION_TREE: Part I's own render-settings regions (from
    <const>-ingame, e.g. hun-const-ingame) whose outline overlaps the map's levels, geometry / priority / blend copied
    exactly; the start-task / end-task gating tags (Part I story progress; MP never reaches those tasks) are dropped.
  * <rs-level>.t1x.bin     TLOU2's render-settings/t1x module (9 t1x-rs-* symbols that no TLOU2 level references) plus
    the Part I render-settings symbols those regions name, copied setting by setting from Part I's modules (same DC
    layout, same setting keys: FNV-1a-64 of 'group:name'); dropped: Part I's LUT texture reference (not in TLOU2) and any
    key TLOU2's own render-settings files never use.  build: staged as bin/dc1/render-settings/t1x.bin, modules.bin
    exports + size follow (sp_maps_build.stage_part1).
  * the registry block of <rs-level> (package <rs-level>-ingame + symbol / render-settings lines) in pak68-part1.txt.

  python p1_rsenv.py regions <pak> [x0 z0 x1 z1]       # REGION_TREE regions (TLOU2 or Part I pak), optional x/z filter
  python p1_rsenv.py rs <render-settings .bin> <symbol>...   # settings of render-settings symbols
  python p1_rsenv.py check <rs-level-ingame.pak> <t1x.bin>    # offline audit of a built pair (also run by convert)
  python p1_rsenv.py selftest <stock TLOU2 -ingame pak with a REGION_TREE>   # writer round trip (byte-identical span)
"""
import json
import os
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import t2pak  # noqa: E402


def fnv(s):
    h = 0xCBF29CE484222325
    for c in s.encode():
        h = ((h ^ c) * 0x100000001B3) & 0xFFFFFFFFFFFFFFFF
    return h


TAG_RS = fnv("render-settings")              # 0x3b0eb6ba2d8acb0d
TAG_OBSERVED_BY = 0x0D53D5C8C07EEC97         # value sid "camera" on render-settings regions (SceneEditor RegionTreeInfo)
SID_PLAYER = 0x4580FAB03B7EB9C0              # default observed-by (SceneEditor RegionTreeInfo.SidPlayer)
TAG_STATE_SCRIPT = 0xCE1173292ADCBD6E        # regions with a state script carry an extra aux block (not supported here)
# Part I story gating on render-settings regions: start-task / end-task (+ two companions that only ever appear with them)
GATING = {fnv("start-task"), fnv("end-task"), 0x9F836DFD45C1461C, 0xE90C05F74AE202F7}
TC_INT, TC_FLOAT, TC_SID = 0x40001, 0x40004, 0x4000D       # tag box type codes; strings: len << 16 | 5
RS_TYPE = 0xBDBE88DCF0440636                 # DC entry type of a render-settings symbol (a map: count, keys, records)
REC_TYPE = 0xDCEF8E18CF6E36AB                # tag before each setting record {key, value (f32 + i32 kind), sid}
ARRAY_TYPE = fnv("array")
BEH_SET = 0                                  # record +0x18 u32 m_behavior: 0 Set, 1 Max, 2 Min, 3 Multiply (by another setting), 4 curve
REC_SID = 0x3C0D17BAD169557B                 # third word of every stock record (the setting type sid; all 6741 stock symbols)
DROP_KEYS = {fnv("lut:lut-texture-params:lut-texture-file")}   # names a Part I LUT texture TLOU2 does not have
# Keys TLOU2's SHIPPED render-settings modules never set (so tlou2_keys() lacks them) but whose names are registered in the TLOU2 EXE
# (strings in tlou-ii.exe, same category:name as Part I's) = the engine reads them. The converter dropped them (6 / 6 / 6 / 2 / 1 / 1 / 1 of the 20 symbols):
#   fog:split-vol-fog-and-lights (6, =1: fire / runtime lights are NOT mixed into the volumetric fog),
#   lighting:hero-rim-light-aligned-with-camera-attenuation (6) and ...-buddy-aligned-with-camera-attenuation (6),
#   lighting:use-deferred-bounce-shading (2), lighting:ambient-projection-specular (1), misc:enable-depth-prepass-reflection (1), fog:vol-dir-fade-scale (1)
ENGINE_KEYS = {fnv(k) for k in (
    "fog:split-vol-fog-and-lights", "lighting:hero-rim-light-aligned-with-camera-attenuation",
    "lighting:hero-rim-light-buddy-aligned-with-camera-attenuation", "lighting:use-deferred-bounce-shading",
    "lighting:ambient-projection-specular", "misc:enable-depth-prepass-reflection", "fog:vol-dir-fade-scale")}
T1X_MODULE = "render-settings/t1x"
PAK_VERSION = 0xA79
FILL = 0x12345


def cstr(d, o):
    return bytes(d[o:d.index(b"\0", o)]).decode("latin1")


# ======================================================================== REGION_TREE read
class View:
    """pointer view of one pak page set: d = bytes, ptr(addr) -> target addr or None (both in one address space)"""
    def __init__(self, d, ptr):
        self.d, self.ptr = d, ptr

    def q(self, a):
        return struct.unpack_from("<Q", self.d, a)[0]


def parse_tree(v, base):
    """REGION_TREE payload at address base -> (regions, grid) ; region = dict(name, shape (1 volumes / 2 point), sflags (u16
    after it), prio (u16 after the corner count), vols [[112-byte faces]],
    point (40 bytes) | None, tags [(key, kind, value)], corners [16-byte xyzw])"""
    d, ptr, q = v.d, v.ptr, v.q
    grid = ptr(base)
    recs, k = [], 8
    while ptr(base + k) is not None:
        recs.append(ptr(base + k))
        k += 8
    regions = []
    for R in recs:
        name = cstr(d, ptr(R))
        assert q(R + 8) == fnv(name), name
        shape, sflags, nc, prio = struct.unpack_from("<HHHH", d, R + 0x68)
        body = ptr(R + 0x30)
        # (stock TLOU2 trees put the body right after the 128-byte record, Part I ones before it: follow the pointers)
        # supported = what build_tree writes (the stock render-settings layout): volume / point shape, no aux block (+0x40,
        # state scripts), no +0x48 block (shape flag 1); others are read for their tags only and never selected
        unsupported = None
        if ptr(R + 0x40) is not None or ptr(R + 0x48) is not None or sflags:
            unsupported = "aux block / shape flags %d" % sflags
        vols, point = [], None
        if unsupported:
            pass
        elif shape == 1:
            c = body
            while True:
                hdr = q(c + 16)
                assert hdr & 0xFFFF == 1 and q(c + 8) == 0 and q(c + 24) == 0, name
                n = (hdr >> 16) & 0xFFFF
                vols.append([bytes(d[c + 32 + 112 * j:c + 32 + 112 * (j + 1)]) for j in range(n)])
                nxt = ptr(c)
                if nxt is None:
                    break
                c = nxt
        elif shape == 2:
            point = bytes(d[body + 32:body + 72])
        else:
            unsupported = "shape %d" % shape
        dic = ptr(R + 0x50)
        ent = ptr(dic)
        tags = []
        for i in range(q(dic + 8)):
            key = q(ent + 16 * i)
            box = ptr(ent + 16 * i + 8)
            tc, val = q(box), ptr(box + 8)
            if tc == TC_SID:
                tags.append((key, "sid", q(val)))
            elif tc == TC_INT:
                tags.append((key, "int", struct.unpack_from("<i", d, val)[0]))
            elif tc == TC_FLOAT:
                tags.append((key, "float", struct.unpack_from("<I", d, val)[0]))
            elif tc & 0xFFFF == 5:
                s = cstr(d, ptr(val))
                assert len(s) == tc >> 16, (name, s, hex(tc))
                tags.append((key, "str", s))
            else:
                tags.append((key, "tc%x" % tc, None))
                unsupported = unsupported or "tag type code %#x" % tc
        cs = ptr(R + 0x58)
        regions.append({"name": name, "shape": shape, "sflags": sflags, "prio": prio, "vols": vols, "point": point, "tags": tags,
                        "unsupported": unsupported,
                        "corners": [bytes(d[cs + 16 * i:cs + 16 * i + 16]) for i in range(nc)]})
    g = struct.unpack_from("<4f4f3I", d, grid)
    return regions, {"origin": g[0:3], "size": g[4:7], "dims": g[8:11]}


def region_rs(r):
    return next((v for k, kind, v in r["tags"] if k == TAG_RS and kind == "str"), None)


def corner_box(r):
    """(x0, z0, x1, z1) of the region's outline corners"""
    xs = [struct.unpack_from("<f", c, 0)[0] for c in r["corners"]]
    zs = [struct.unpack_from("<f", c, 8)[0] for c in r["corners"]]
    return (min(xs), min(zs), max(xs), max(zs)) if xs else None


def world_aabb(r):
    """SceneEditor RegionTreeFormat.RegionWorldAabb (volumes) / the point's sqrt(2) r box -> (min xyz, max xyz) in float32"""
    import numpy as np
    if r["shape"] == 2:
        x, y, z = struct.unpack_from("<3f", r["point"], 0)
        rad = np.float32(struct.unpack_from("<f", r["point"], 32)[0]) * np.float32(np.sqrt(np.float32(2)))
        return [np.float32(x) - rad, np.float32(y) - rad, np.float32(z) - rad], [np.float32(x) + rad, np.float32(y) + rad, np.float32(z) + rad]
    lo = [np.float32(np.finfo(np.float32).max)] * 3
    hi = [np.float32(-np.finfo(np.float32).max)] * 3
    for vol in r["vols"]:
        for f in vol:
            rot = [struct.unpack_from("<f", f, 16 * j + 4 * k)[0] for j in range(3) for k in range(3)]
            tx, ty, tz = struct.unpack_from("<3f", f, 48)
            quad = struct.unpack_from("<8f", f, 80)
            for i in range(4):
                a = float(quad[2 * i]) - float(tx)
                b = float(quad[2 * i + 1]) - float(ty)
                c = 0.0 - float(tz)
                w = [np.float32(a * rot[0] + b * rot[1] + c * rot[2]), np.float32(a * rot[3] + b * rot[4] + c * rot[5]),
                     np.float32(a * rot[6] + b * rot[7] + c * rot[8])]
                lo = [min(lo[t], w[t]) for t in range(3)]
                hi = [max(hi[t], w[t]) for t in range(3)]
    return lo, hi


# ======================================================================== REGION_TREE write (SceneEditor RegionTreeFormat.Build
# + string tags + the record's u16 priority; the layout is checked byte for byte against stock paks: selftest)
def _box_size(kind, val):
    return 16 + {"sid": 8, "int": 4, "float": 4}.get(kind, 0) + (8 + len(val) + 1 if kind == "str" else 0)


def build_tree(regions, grid, base):
    """-> (span bytes, [offsets of pointer slots inside the span]); pointers hold base + target (page offsets)"""
    assert regions, "REGION_TREE needs at least one region"

    def align(pos, n):
        return ((base + pos + n - 1) & ~(n - 1)) - base
    lays = []
    pos = align(8 + 8 * (len(regions) + 1), 16)
    for r in regions:
        tags = sorted(r["tags"])
        L = {"start": pos, "body": pos + 128}
        p = pos + 128 + (sum(32 + 112 * len(v) for v in r["vols"]) if r["shape"] == 1 else 72)
        L["dict"] = p
        L["entries"] = p + 16
        p = p + 16 + 16 * len(tags)
        L["boxes"] = []
        for k, kind, val in tags:
            p = align(p, 8)
            L["boxes"].append(p)
            p += _box_size(kind, val)
        L["strings"] = p
        p += 2 * (len(r["name"].encode()) + 1) + 1
        L["corners"] = align(p, 16)
        L["end"] = L["corners"] + 16 * len(r["corners"])
        lays.append(L)
        pos = L["end"]
    grid_pos = pos
    dims = grid["dims"]
    ncell = dims[0] * dims[1] * dims[2]
    cells = _derive_cells(regions, grid)
    cell_pos, p = [], grid_pos + 48 + 8 * (ncell + 1)
    for c in cells:
        cell_pos.append(p)
        p += 16 + 16 * len(c) + sum(16 + 8 * len(ix) for _, ix in c)
    total = p + 8
    out = bytearray(total)
    relocs = []

    def ptr(at, target):
        if target is None:
            return
        struct.pack_into("<Q", out, at, base + target)
        relocs.append(at)
    ptr(0, grid_pos)
    for i, L in enumerate(lays):
        ptr(8 + 8 * i, L["start"])
    for r, L in zip(regions, lays):
        s = L["start"]
        nb = r["name"].encode()
        sid = fnv(r["name"])
        ptr(s, L["strings"])
        struct.pack_into("<Q", out, s + 8, sid)
        ptr(s + 0x10, L["strings"] + len(nb) + 1)
        ptr(s + 0x20, L["strings"] + len(nb) + 2)
        struct.pack_into("<Q", out, s + 0x28, sid)
        ptr(s + 0x30, L["body"])
        ptr(s + 0x50, L["dict"])
        ptr(s + 0x58, L["corners"])
        struct.pack_into("<HHHH", out, s + 0x68, r["shape"], r["sflags"], len(r["corners"]), r["prio"])
        b = L["body"]
        if r["shape"] == 1:
            for i, vol in enumerate(r["vols"]):
                size = 32 + 112 * len(vol)
                ptr(b, b + size if i + 1 < len(r["vols"]) else None)
                struct.pack_into("<Q", out, b + 16, (len(vol) << 16) | 1)
                for j, f in enumerate(vol):
                    out[b + 32 + 112 * j:b + 32 + 112 * (j + 1)] = f
                b += size
        else:
            out[b + 32:b + 72] = r["point"]
        tags = sorted(r["tags"])
        ptr(L["dict"], L["entries"])
        struct.pack_into("<Q", out, L["dict"] + 8, len(tags))
        for i, ((k, kind, val), bx) in enumerate(zip(tags, L["boxes"])):
            struct.pack_into("<Q", out, L["entries"] + 16 * i, k)
            ptr(L["entries"] + 16 * i + 8, bx)
            if kind == "str":
                vb = val.encode("latin1")
                struct.pack_into("<Q", out, bx, (len(vb) << 16) | 5)
                ptr(bx + 8, bx + 16)
                ptr(bx + 16, bx + 24)
                out[bx + 24:bx + 24 + len(vb)] = vb
            else:
                struct.pack_into("<Q", out, bx, {"sid": TC_SID, "int": TC_INT, "float": TC_FLOAT}[kind])
                ptr(bx + 8, bx + 16)
                struct.pack_into({"sid": "<Q", "int": "<i", "float": "<I"}[kind], out, bx + 16, val)
        st = L["strings"]
        out[st:st + len(nb)] = nb
        out[st + len(nb) + 2:st + 2 * len(nb) + 2] = nb
        for i, c in enumerate(r["corners"]):
            out[L["corners"] + 16 * i:L["corners"] + 16 * (i + 1)] = c
    struct.pack_into("<4f4f3II", out, grid_pos, *grid["origin"], 1.0, *grid["size"], 1.0, *dims, 0)
    for i, c in enumerate(cells):
        ptr(grid_pos + 48 + 8 * i, cell_pos[i])
        cp = cell_pos[i]
        ptr(cp, cp + 16)
        struct.pack_into("<Q", out, cp + 8, len(c))
        lp = cp + 16 + 16 * len(c)
        lists = []
        for j, (cls, ix) in enumerate(c):
            struct.pack_into("<Q", out, cp + 16 + 16 * j, cls)
            ptr(cp + 16 + 16 * j + 8, lp)
            lists.append(lp)
            lp += 16 + 8 * len(ix)
        for (cls, ix), l in zip(c, lists):
            ptr(l, l + 16)
            struct.pack_into("<Q", out, l + 8, len(ix))
            for t, ri in enumerate(ix):
                ptr(l + 16 + 8 * t, lays[ri]["start"])
    return bytes(out), relocs


def _derive_cells(regions, grid):
    """SceneEditor RegionTreeFormat.DeriveCells: per grid cell (+ one for point regions) the regions whose world AABB
    touches it, grouped by observed-by class (sorted)"""
    import numpy as np
    nx, ny, nz = grid["dims"]
    cells = [[] for _ in range(nx * ny * nz + 1)]
    step = [float(np.float32(grid["size"][t])) / [nx, ny, nz][t] for t in range(3)]
    org = [float(np.float32(grid["origin"][t])) for t in range(3)]
    for j, r in enumerate(regions):
        lo, hi = world_aabb(r)
        if r["shape"] == 2:
            cells[-1].append(j)
        for a in range(nx):
            for b in range(ny):
                for c in range(nz):
                    c0 = [org[0] + a * step[0], org[1] + b * step[1], org[2] + c * step[2]]
                    if all(float(hi[t]) >= c0[t] and float(lo[t]) <= c0[t] + step[t] for t in range(3)):
                        cells[(a * ny + b) * nz + c].append(j)
    out = []
    for ix in cells:
        by = {}
        for j in ix:
            cls = next((v for k, kind, v in regions[j]["tags"] if k == TAG_OBSERVED_BY and kind == "sid"), SID_PLAYER)
            by.setdefault(cls, []).append(j)
        out.append(sorted(by.items()))
    return out


def fit_grid(regions, dims=(6, 6, 6)):
    """grid covering every region's world AABB (stock trees use 6 x 6 x 6)"""
    los, his = zip(*(world_aabb(r) for r in regions))
    lo = [min(float(x[t]) for x in los) for t in range(3)]
    hi = [max(float(x[t]) for x in his) for t in range(3)]
    return {"origin": tuple(lo), "size": tuple(max(1.0, hi[t] - lo[t]) for t in range(3)), "dims": tuple(dims)}


# ======================================================================== -ingame pak write (layout of the stock render-const
# -ingame paks, e.g. t2r-sea-hub-render-const-ingame: one page, REGION_TREE + login table + empty LEVEL_INFO_3 / VRAM table /
# SPLINE_TABLE / TAG_INT 'coverActionPackCount')
def make_ingame_pak(regions, grid, tree=None):
    items = [("", "REGION_TREE", None), ("", "PAK_LOGIN_TABLE", None), ("", "LEVEL_INFO_3", bytes(16)),
             ("", "VRAM_DESC_TABLE", bytes(8)), ("", "SPLINE_TABLE", bytes(4)), ("coverActionPackCount", "TAG_INT", bytes(4))]
    login_types = ("REGION_TREE", "LEVEL_INFO_3", "SPLINE_TABLE", "TAG_INT")
    n = len(items)
    hdr_end = (20 + 16 * n + 15) // 16 * 16
    rt_hdr = hdr_end
    span, relocs = tree(rt_hdr + 48) if tree else build_tree(regions, grid, rt_hdr + 48)       # tree: callable(base) -> (span, pointer slots), a prebuilt REGION_TREE (p1_firesfx)
    offs, pos = {}, rt_hdr
    sizes = {"REGION_TREE": len(span), "PAK_LOGIN_TABLE": 8 + 8 * len(login_types)}
    for nm, typ, pl in items:
        offs[typ] = pos
        size = sizes.get(typ, len(pl) if pl is not None else 0)
        sizes[typ] = size
        pos = (pos + 48 + size + 15) // 16 * 16
    names = sorted({nm for nm, _, _ in items} | {typ for _, typ, _ in items})
    str_at, strs = {}, bytearray()
    for s in names:
        str_at[s] = pos + len(strs)
        strs += s.encode() + b"\0"
    page = bytearray(pos + len(strs))
    while len(page) % 16:
        page.append(0)
    struct.pack_into("<QIIHH", page, 0, t2pak.MAGIC, 0, len(page), 0, n)
    for i, (nm, typ, pl) in enumerate(items):
        struct.pack_into("<QII", page, 20 + 16 * i, str_at[nm], offs[typ], FILL)
        h = offs[typ]
        struct.pack_into("<QQI7I", page, h, str_at[nm], str_at[typ], sizes[typ], *([FILL] * 7))
        if typ == "REGION_TREE":
            page[h + 48:h + 48 + len(span)] = span
        elif typ == "PAK_LOGIN_TABLE":
            struct.pack_into("<II", page, h + 48, len(login_types), FILL)
            for k, t in enumerate(login_types):
                struct.pack_into("<II", page, h + 56 + 8 * k, 0, offs[t])
        else:
            page[h + 48:h + 48 + len(pl)] = pl
    page[pos:pos + len(strs)] = strs
    fix = sorted((0, 0, rt_hdr + 48 + r) for r in relocs)
    pt, ft = 0x2C, 0x2C + 12
    fdo = t2pak.fix_data_off(ft)
    first = fdo + 8 * len(fix) + 8
    head = bytearray(first)
    struct.pack_into("<8I", head, 0, PAK_VERSION, first - 8, 0, offs["PAK_LOGIN_TABLE"], 1, pt, 8, ft)
    struct.pack_into("<III", head, 0x20, 0, 0, offs["VRAM_DESC_TABLE"])
    struct.pack_into("<III", head, pt, first, len(page), 0)
    struct.pack_into("<III", head, ft, 0, fdo, len(fix))
    for i, (sp, dp, so) in enumerate(fix):
        struct.pack_into("<HHI", head, fdo + 8 * i, sp, dp, so)
    return bytes(head) + bytes(page)


def read_pak_regions(data):
    """REGION_TREE regions + grid of a TLOU2-layout pak (bytes)"""
    pk = t2pak.TPak(data)
    starts, pos = [], 0
    for p in pk.pages:
        starts.append(pos)
        pos += len(p)
    blob = b"".join(bytes(p) for p in pk.pages)

    def ptr(a):
        for i, s in enumerate(starts):
            if s <= a < s + len(pk.pages[i]):
                dp = pk.fix.get((i, a - s))
                return None if dp is None else starts[dp] + pk.q(i, a - s)
        return None
    v = View(blob, ptr)
    out = []
    for typ, pg, off in pk.items():
        if typ == "REGION_TREE":
            out.append(parse_tree(v, starts[pg] + off))
    return out


def read_p1_regions(data):
    """REGION_TREE regions + grid of a raw Part I pak"""
    import p1_pak
    p = p1_pak.P1Pak("<mem>", data)

    def ptr(a):
        dp = p.fix.get(a)
        return None if dp is None else struct.unpack_from("<Q", data, a)[0] + p.pages[dp][0]
    v = View(data, ptr)
    return [parse_tree(v, p.pages[pg][0] + off + 48) for typ, pg, off in p.items if typ == "REGION_TREE"]


# ======================================================================== DC render-settings modules
class DcRs:
    """render-settings symbols of one DC module: {sid: [(key, value 8 bytes, sid 8 bytes)]}"""
    def __init__(self, data):
        sys.path.insert(0, os.path.join(os.path.dirname(HERE), "features"))
        from dcfile import DcFile
        self.f = f = DcFile(data)
        d = f.data
        n = struct.unpack_from("<I", d, 0x14)[0]
        eo = struct.unpack_from("<Q", d, 0x18)[0]
        self.rows = [struct.unpack_from("<QQQ", d, eo + 24 * i) for i in range(n)]
        self.syms = {}
        self.beh = {}                          # {sid: [(key, m_behavior, +0x20 pointer)]}
        self.tail = {}                         # {sid: [+0x28 word of each record (0 in every stock record), None past the data]}
        for s, t, p in self.rows:
            if t != RS_TYPE:
                continue
            cnt, ka, va = f.q(p), f.q(p + 8), f.q(p + 16)
            recs = []
            for k in range(cnt):
                r = f.q(va + 8 * k)
                assert f.q(r - 8) == REC_TYPE and f.q(ka + 8 * k) == f.q(r), "render-settings record layout"
                recs.append((f.q(r), bytes(d[r + 8:r + 16]), bytes(d[r + 16:r + 24])))
            self.syms[s] = recs
            # (Part I's 0x18-byte records can end the file: no m_behavior there, only meaningful for TLOU2 modules)
            self.beh[s] = [(f.q(r), struct.unpack_from("<I", d, r + 0x18)[0], f.q(r + 0x20)) if r + 0x28 <= len(d) else (f.q(r), None, 0)
                           for r in (f.q(va + 8 * k) for k in range(cnt))]
            self.tail[s] = [f.q(r + 0x28) if r + 0x30 <= len(d) else None for r in (f.q(va + 8 * k) for k in range(cnt))]


def tlou2_keys(rs_dir):
    """every setting key TLOU2's own render-settings modules use (the ones its engine reads)"""
    keys = set()
    for root, _, files in os.walk(rs_dir):
        for fn in files:
            if fn.endswith(".bin"):
                try:
                    for recs in DcRs(open(os.path.join(root, fn), "rb").read()).syms.values():
                        keys.update(k for k, _, _ in recs)
                except Exception:              # noqa: BLE001 - non-render-settings DC files in the tree
                    pass
    return keys


def shift_tonemap(t1x_data, d_range=0.0, d_set_point=0.0):
    """exposure bisect knob (stage time, no reconvert; sp_maps_build.stage_part1_rs, env T2R_P1_RS_EV / T2R_P1_RS_SP): adds
    d_range to every tonemap-light-range-min / -max float and d_set_point to every tonemap-set-point float of the module's
    render-settings symbols (the stock t1x ones nothing references are shifted too). Part I's values are 3.5..4.85 in the
    Bookstore (TLOU2's Seattle base -1.5..1.5); -> (module bytes, number of values changed)"""
    if not d_range and not d_set_point:
        return t1x_data, 0
    sys.path.insert(0, os.path.join(os.path.dirname(HERE), "features"))
    from dcfile import DcFile
    delta = {fnv("tonemap:tonemap-light-range-min"): d_range, fnv("tonemap:tonemap-light-range-max"): d_range,
             fnv("tonemap:tonemap-set-point"): d_set_point}
    f = DcFile(t1x_data)
    n = 0
    for s, t, p in (struct.unpack_from("<QQQ", f.data, f.q(0x18) + 24 * i) for i in range(struct.unpack_from("<I", f.data, 0x14)[0])):
        if t != RS_TYPE:
            continue
        cnt, va = f.q(p), f.q(p + 16)
        for k in range(cnt):
            r = f.q(va + 8 * k)
            d = delta.get(f.q(r))
            if d:
                val, kind = struct.unpack_from("<fi", f.data, r + 8)
                if kind == -1:
                    struct.pack_into("<f", f.data, r + 8, val + d)
                    n += 1
    return f.save(), n


def add_symbols(t1x_data, symbols, keep_key):
    """TLOU2 t1x module bytes + {name: [(key, value, sid)]} -> (new module bytes, {name: (kept, dropped keys)})
    Each symbol: tag + map {count, keys array, records array} + 'array'-tagged arrays + REC_TYPE-tagged records, appended
    at the end of the data block; the entry table gets the rows (sorted by sid; everything after it moves)."""
    sys.path.insert(0, os.path.join(os.path.dirname(HERE), "features"))
    from dcfile import DcFile
    f = DcFile(t1x_data)
    n_ent = struct.unpack_from("<I", f.data, 0x14)[0]
    ent = f.q(0x18)
    rows = [struct.unpack_from("<QQQ", f.data, ent + 24 * i) for i in range(n_ent)]
    have = {r[0] for r in rows}
    report, new = {}, []
    for name, recs in symbols.items():
        sid = fnv(name)
        assert sid not in have, "%s already in the module" % name
        kept = [r for r in recs if keep_key(r[0])]
        report[name] = (len(kept), [r[0] for r in recs if not keep_key(r[0])])
        rec_off = []
        for k, val, s2 in kept:
            # the engine reads a 0x30-byte entry per record (every stock TLOU2 record: tag + 0x30 body, byte compare vs
            # *pat-rs-pat-cloudy* / *zgame-mp-player-health-02-low*): key, value, type sid, +0x18 u32 m_behavior (0 = Set; TLOU2's
            # GetRenderSettingTargetValueFloat asserts on anything but 0..4), +0x20 pointer (curve, behavior 4 only), +0x28 zero.
            # Part I's records are 0x18 bytes: pad them, or the next record's tag lands in the engine's fields.
            rec_off.append(f.append(struct.pack("<QQ", REC_TYPE, k) + val + (s2 if s2 != bytes(8) else struct.pack("<Q", REC_SID))
                                    + struct.pack("<IIQQ", BEH_SET, 0, 0, 0)) + 8)
        ka = f.append(struct.pack("<Q", ARRAY_TYPE) + b"".join(struct.pack("<Q", k) for k, _, _ in kept)) + 8
        va = f.append(struct.pack("<Q", ARRAY_TYPE) + b"".join(struct.pack("<Q", o) for o in rec_off),
                      [8 + 8 * i for i in range(len(rec_off))]) + 8
        mp = f.append(struct.pack("<QQQQ", RS_TYPE, len(kept), ka, va), [16, 24]) + 8
        new.append((sid, mp))
    # entry table rows (as sp_maps_build._insert_entries)
    add = len(new) * 24
    tab_end = ent + 24 * n_ent
    rows += [(sid, RS_TYPE, mp) for sid, mp in new]
    rows.sort()
    for i in range(0, len(f.data), 8):
        if f.is_ptr(i) and f.q(i) >= tab_end:
            f.set_q(i, f.q(i) + add)
    old_ptrs = [i for i in range(tab_end, len(f.data), 8) if f.is_ptr(i)]
    for i in range(tab_end, len(f.bits) * 64, 8):
        if f.is_ptr(i):
            f.bits[(i // 8) // 8] &= ~(1 << ((i // 8) % 8))
    f.data[ent:tab_end] = b"".join(struct.pack("<QQQ", s, t, p + add if p >= tab_end else p) for s, t, p in rows)
    for i in old_ptrs:
        f._mark(i + add)
    for k in range(len(rows)):
        f._mark(ent + 24 * k + 16)
    f.strings += add
    struct.pack_into("<I", f.data, 0x14, len(rows))
    return f.save(), report


# synthetic "ambient fill" symbol: the converted Part I levels carry no data a TLOU2 level normally gets ambient from for
# dynamic objects (the player stood black in a doorway); these settings light characters and scale baked ambient without any probe.
# Render-setting value cell (8 bytes, measured over all 6741 stock TLOU2 symbols): float = f32 + i32 -1; int / enum = u32 0 + i32 value
# (tonemap-exposure-method: 1 = auto exposure (477 stock records), 0 = manual at tonemap-manual-exposure-value (287); exe+13f92fa tests
# the field at settings+0x1820: 1 -> auto (forced EV honoured), 0 -> manual EV from +0x1830).  A symbol that leaves the key unset gets the
# engine default 0 = MANUAL EV 0: near black, deaf to force-exposure-value.  Part I's own symbols never set it (its engine is always auto).
EXPOSURE_AUTO = 1
KEY_EXPOSURE_METHOD = "tonemap:tonemap-exposure-method"


def pack_value(v):
    """setting value -> the 8-byte record cell: python int -> int cell, float -> float cell"""
    if isinstance(v, bool) or isinstance(v, int):
        return struct.pack("<Ii", 0, int(v))
    return struct.pack("<fi", v, -1)


def with_auto_exposure(recs):
    """records of one Part I symbol -> the same plus tonemap-exposure-method = auto when the symbol does not set it"""
    k = fnv(KEY_EXPOSURE_METHOD)
    if any(r[0] == k for r in recs):
        return recs
    return sorted(list(recs) + [(k, pack_value(EXPOSURE_AUTO), struct.pack("<Q", 0))])   # keys stay sorted (check())


FILL_SETTINGS = (("lighting:character-fake-ambient-r", 0.6), ("lighting:character-fake-ambient-g", 0.6),
                 ("lighting:character-fake-ambient-b", 0.65), ("lighting:character-fake-ambient-i", 1.0),
                 ("lighting:ambient-background-scale", 4.0), ("lighting:ambient-foreground-scale", 4.0),
                 ("lighting:ambient-character-scale", 2.0), ("tonemap:tonemap-exposure-method", EXPOSURE_AUTO))


def add_fill_symbol(t1x_data, name, settings=FILL_SETTINGS):
    """t1x module bytes -> (bytes with one more render-settings symbol `name` holding `settings`, number of settings);
    layer it with  t2r-p1-rs-override.txt  `<name> <priority> <strength>` (strength = blend 0..1 toward these values)."""
    recs = [(fnv(k), pack_value(v), struct.pack("<Q", 0)) for k, v in sorted(settings, key=lambda kv: fnv(kv[0]))]
    data, _ = add_symbols(t1x_data, {name: recs}, lambda k: True)
    return data, len(recs)


# ======================================================================== the map's environment
def select_regions(regions, box, rs_known):
    """render-settings regions whose outline overlaps box (x0, z0, x1, z1) and whose symbol exists; gating tags dropped"""
    out, skipped = [], []
    for r in regions:
        rs = region_rs(r)
        cb = corner_box(r)
        if rs is None or cb is None or cb[2] < box[0] or cb[0] > box[2] or cb[3] < box[1] or cb[1] > box[3]:
            continue
        if rs not in rs_known:
            skipped.append((r["name"], rs))
            continue
        if r["unsupported"] or any(k == TAG_STATE_SCRIPT for k, _, _ in r["tags"]):
            skipped.append((r["name"], r["unsupported"] or "state script"))
            continue
        out.append(dict(r, tags=[t for t in r["tags"] if t[0] not in GATING]))
    return out, skipped


CONST_BASE = "*t1-rs-hun-const-base*"
DEFAULTS_JSON = os.path.join(HERE, "data", "p1_rs_defaults.json")


def engine_defaults(tlou2_rs_dir, part1_recs):
    """{key sid: 8-byte value cell} = Part I's ENGINE DEFAULT for every setting TLOU2's exe registers (the Part I live render settings at the
    Bookstore (re/p1_trace/20261105-002750 poses) = these defaults + the region symbols; the converted level only carried the region symbols, so every
    key a region leaves alone fell back to TLOU2's own default - volumetrics / sun shadow / ambient rows differ). data/p1_rs_defaults.json = the first
    snapshot of the Part I tracer (all 1244 keys, tools/part1 data), exe-registered, plain floats / small ints. The cell kind (float {f32,-1} vs int {0,i32})
    follows TLOU2's own module records for the key, else Part I's; a key with no known kind is skipped (a float cell read as a bool is -1 = true)."""
    kinds = {}
    for recs in part1_recs:
        for k, v, _ in recs:
            kinds.setdefault(k, struct.unpack("<i", v[4:8])[0] == -1)
    for root, _, files in os.walk(tlou2_rs_dir):
        for fn in files:
            if fn.endswith(".bin"):
                try:
                    for recs in DcRs(open(os.path.join(root, fn), "rb").read()).syms.values():
                        for k, v, _ in recs:
                            kinds[k] = struct.unpack("<i", v[4:8])[0] == -1
                except Exception:              # noqa: BLE001
                    pass
    out = {}
    for name, (t, val) in json.load(open(DEFAULTS_JSON)).items():
        k = fnv(name)
        if k not in kinds or k in DROP_KEYS:
            continue
        if kinds[k]:
            out[k] = pack_value(float(val))
        elif (t == "i" or float(val) == int(float(val))) and abs(float(val)) < 2 ** 31:
            out[k] = pack_value(int(val))
    return out


def build_env(const_ingame, rs_modules, t1x_data, tlou2_rs_dir, box, report=None):
    """const_ingame: raw Part I <const>-ingame pak; rs_modules: {file name: bytes} of Part I render-settings modules;
    t1x_data: TLOU2's render-settings/t1x.bin; box: (x0, z0, x1, z1) of the map.  -> (ingame pak bytes, t1x bytes,
    [render-settings symbol names])"""
    trees = read_p1_regions(const_ingame)
    assert len(trees) == 1, "expected one REGION_TREE in the const level"
    regions, _grid = trees[0]
    mods = {}
    for fn, data in rs_modules.items():
        for sid, recs in DcRs(data).syms.items():
            mods.setdefault(sid, (fn, recs))
    names = {region_rs(r) for r in regions if region_rs(r)}
    known = {nm for nm in names if fnv(nm) in mods}
    sel, skipped = select_regions(regions, box, known)
    syms = sorted({region_rs(r) for r in sel})
    t2keys = tlou2_keys(tlou2_rs_dir)
    dflt = engine_defaults(tlou2_rs_dir, [recs for _, recs in mods.values()])
    keep = lambda k: (k in t2keys or k in ENGINE_KEYS or k in dflt) and k not in DROP_KEYS      # noqa: E731
    symrecs = {nm: with_auto_exposure(mods[fnv(nm)][1]) for nm in syms}
    if CONST_BASE in symrecs:        # Part I's engine defaults under its const base (lowest layer, always on)
        have = {r[0] for r in symrecs[CONST_BASE]}
        symrecs[CONST_BASE] = sorted(list(symrecs[CONST_BASE]) + [(k, v, struct.pack("<Q", 0)) for k, v in dflt.items() if k not in have])
        # The sky turned while walking in / out: a sky-space key that every region symbol setting it agrees on takes THAT value in the base,
        # so a region blend (ramp in / out, ~1 s) never moves between the region value and the engine default (sky:rotation 60 vs 0 = a visible turn)
        skyk = {fnv(nm): nm for nm in json.load(open(DEFAULTS_JSON)) if nm.startswith("sky:")}
        agree = {}
        for nm, recs in symrecs.items():
            if nm == CONST_BASE:
                continue
            for k, v, _ in recs:
                if k in skyk:
                    agree.setdefault(k, set()).add(v)
        pin = {k: next(iter(vs)) for k, vs in agree.items() if len(vs) == 1}
        symrecs[CONST_BASE] = sorted([(k, pin.get(k, v), s2) for k, v, s2 in symrecs[CONST_BASE]])
    t1x_new, rep = add_symbols(t1x_data, symrecs, keep)
    pak = make_ingame_pak(sel, fit_grid(sel))
    if report is not None:
        report.update({"regions": [r["name"] for r in sel], "skipped": skipped, "symbols": {nm: (mods[fnv(nm)][0],) + rep[nm]
                       for nm in syms}})
    return pak, t1x_new, syms


def registry_block(level, syms):
    out = ["level-name " + level, "level-id " + level, "package %s-ingame" % level]
    for s in syms:
        out += ["symbol " + s, "render-settings " + s]
    return out


# ======================================================================== audit
def check(pak_data, t1x_data, t1x_stock=None, src_regions=None):
    """problems list: the pak re-reads (one REGION_TREE, every region with a render-settings symbol, no gating tags, cells
    hold every region its AABB touches), every symbol it names is a render-settings map of the t1x module, the module's
    stock symbols are unchanged, (src_regions given) geometry / tags equal the Part I source minus the gating tags"""
    bad = []
    trees = read_pak_regions(pak_data)
    if len(trees) != 1:
        return ["%d REGION_TREE items" % len(trees)]
    regions, grid = trees[0]
    rs = DcRs(t1x_data)
    for r in regions:
        s = region_rs(r)
        if s is None:
            bad.append("%s: no render-settings tag" % r["name"])
        elif fnv(s) not in rs.syms:
            bad.append("%s: %s is not in the t1x module" % (r["name"], s))
        if any(k in GATING for k, _, _ in r["tags"]):
            bad.append("%s: gating tag left" % r["name"])
    stock_syms = DcRs(t1x_stock).syms if t1x_stock is not None else {}
    for sid, bl in rs.beh.items():
        for k, b, ptr in bl:
            if b is None or b > 4 or (b != 4 and ptr):
                bad.append("symbol %#x key %#x: m_behavior %#x / +0x20 %#x (not a TLOU2 behavior 0..4)" % (sid, k, b, ptr))
            elif sid not in stock_syms and b != BEH_SET:
                bad.append("symbol %#x key %#x: m_behavior %d on a copied Part I record (TLOU2 reads it as a Set target)" % (sid, k, b))
    ek = fnv(KEY_EXPOSURE_METHOD)
    for sid, recs in rs.syms.items():
        if sid not in stock_syms and (any(t != 0 for t in rs.tail[sid]) or any(x == bytes(8) for _, _, x in recs)):
            bad.append("symbol %#x: record layout differs from stock (0x30-byte body, +0x28 = 0, a type sid, e.g. %#x; night61 override did nothing)" % (sid, REC_SID))
        if sid not in stock_syms and dict((k, v) for k, v, _ in recs).get(ek) != pack_value(EXPOSURE_AUTO):
            bad.append("symbol %#x: tonemap-exposure-method is not auto (engine default = manual EV 0, near black)" % sid)
        if [k for k, _, _ in recs] != sorted(k for k, _, _ in recs):
            bad.append("symbol %#x: keys not sorted (every stock map is)" % sid)
    span, _ = build_tree(regions, grid, 0)
    again = build_tree(*read_pak_regions(make_ingame_pak(regions, grid))[0], 0)[0]
    if span != again:
        bad.append("REGION_TREE does not round-trip")
    if t1x_stock is not None:
        old = DcRs(t1x_stock)
        for sid, recs in old.syms.items():
            if rs.syms.get(sid) != recs:
                bad.append("stock t1x symbol %#x changed" % sid)
    if src_regions is not None:
        by = {r["name"]: r for r in src_regions}
        for r in regions:
            s = by.get(r["name"])
            want = dict(s, tags=[t for t in s["tags"] if t[0] not in GATING]) if s else None
            if want is None or any(want[k] != r[k] for k in ("shape", "sflags", "prio", "vols", "point", "corners")) or \
                    sorted(want["tags"]) != sorted(r["tags"]):
                bad.append("%s: differs from the Part I region" % r["name"])
    return bad


def selftest(path):
    """parse a stock TLOU2 REGION_TREE and write it again at the same page offset: the span must be byte-identical"""
    data = open(path, "rb").read()
    pk = t2pak.TPak(data)
    trees = read_pak_regions(data)
    bad = []
    if any(r["unsupported"] for t in trees for r in t[0]):
        return ["%s: regions the writer does not support (%s)" % (os.path.basename(path), sorted({r["unsupported"] for t in trees
                for r in t[0] if r["unsupported"]}))], sum(len(r) for r, _ in trees)
    for (regions, grid), (typ, pg, off) in zip(trees, [i for i in pk.items() if i[0] == "REGION_TREE"]):
        span, relocs = build_tree(regions, grid, off)
        orig = bytes(pk.pages[pg][off:off + len(span)])
        if span != orig:
            i = next(k for k in range(len(span)) if span[k] != orig[k])
            bad.append("%s: span differs at +%#x (of %#x)" % (os.path.basename(path), i, len(span)))
        fx = sorted(o - off for (p_, o) in pk.fix if p_ == pg and off <= o < off + len(span))
        if fx != sorted(relocs):
            bad.append("%s: pointer slots differ (%d vs %d)" % (os.path.basename(path), len(relocs), len(fx)))
    return bad, sum(len(r) for r, _ in trees)


def main(argv):
    if not argv:
        print(__doc__)
        return 2
    cmd = argv[0]
    if cmd == "regions":
        data = open(argv[1], "rb").read()
        trees = read_p1_regions(data) if struct.unpack_from("<I", data, 0)[0] in (2685, 68221) else read_pak_regions(data)
        box = [float(x) for x in argv[2:6]] if len(argv) >= 6 else None
        for regions, grid in trees:
            print(len(regions), "regions, grid", grid)
            for r in regions:
                cb = corner_box(r)
                if box and (not cb or cb[2] < box[0] or cb[0] > box[2] or cb[3] < box[1] or cb[1] > box[3]):
                    continue
                print("  %-50s prio %5d  %-52s x %s z %s" % (r["name"], r["prio"], region_rs(r) or "-",
                      cb and "%.0f..%.0f" % (cb[0], cb[2]), cb and "%.0f..%.0f" % (cb[1], cb[3])))
        return 0
    if cmd == "rs":
        m = DcRs(open(argv[1], "rb").read())
        for nm in argv[2:]:
            recs = m.syms.get(fnv(nm))
            print("==", nm, "missing" if recs is None else len(recs))
            for k, v, s in recs or []:
                fv, kind = struct.unpack("<fi", v)
                print("   %016x  %s" % (k, ("%g" % fv) if kind == -1 else "int %d (%d)" % (struct.unpack("<I", v[:4])[0], kind)))
        return 0
    if cmd == "check":
        bad = check(open(argv[1], "rb").read(), open(argv[2], "rb").read())
        print("OK" if not bad else "PROBLEMS", *bad, sep="\n  ")
        return bool(bad)
    if cmd == "selftest":
        rc = 0
        for p in argv[1:]:
            bad, n = selftest(p)
            print(p, n, "regions", "OK (byte-identical)" if not bad else bad)
            rc |= bool(bad)
        return rc
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
