"""Pure-Python port of the SceneEditor's spawner-pak rewrite (PackageReader.ParsePackage + PackageWriter.BuildPackage, T2R variant), so that
nothing needs pwsh / TLOUSceneEditor.dll: p1_audio_spawners.ps1 = "read the converted pak, drop spawners by name prefix, write it back".

  python p1_spawner_pak.py <in.pak> <out.pak> [-Drop a,b] [-Json spawners.json]       # same arguments as the ps1

What the SceneEditor round trip does (kept exactly, because the output must be byte-identical to its pak):
  read   SPAWNER_GROUP spawners (position, source quaternion, scale, flags, art group, process type sid, property table; parent link), LEVEL_INFO_4 (if any);
         NAV_MESH_1 items would be carried too - refused here (the audio pak has none); REGION_TREE and FEATURE_DB_2 are NOT carried (the ps1 passes null)
  drop   spawners whose name starts with one of the prefixes
  write  one data page: spawners sorted by sid(name) (stable), each with its properties sorted by sid, SPAWNER_GROUP / LEVEL_INFO_3|4 / empty FEATURE_DB_2 /
         SPLINE_TABLE / TAG_INT coverActionPackCount / PAK_LOGIN_TABLE / VRAM_DESC_TABLE logins, relocation table (call order of WritePointer / UpdatePointer)
Reader losses that the writer then bakes in: properties with an empty value (empty string, sid 0, unsupported type, unknown array name) are dropped; a
process type that is not in T2RProcessTypes becomes 0; names are only re-hashed (an FNV of the resolved name is the original sid, "#HEX" ids parse back).
"""
import json
import os
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import t2pak  # noqa: E402

MAGIC = 0xDEADBEEFDEADBEEF
FILL = 74565                                    # 0x12345
FNV_OFF, FNV_PRIME, M64 = 14695981039346656037, 1099511628211, (1 << 64) - 1
ARRAY_NAMES = ("NavMeshBlocker", "PerchPointsData", "MoveModData")


def sid(s):
    """SidHash.Sid: "" -> 0, "#HEX" -> the number, else FNV-1a 64 over the bytes (chars cast to byte)"""
    if not s:
        return 0
    if s.startswith("#"):
        try:
            return int(s[1:], 16)
        except ValueError:
            pass
    h = FNV_OFF
    for c in s:
        h = ((h ^ (ord(c) & 0xFF)) * FNV_PRIME) & M64
    return h


def _process_sids():
    names = json.load(open(os.path.join(os.path.dirname(os.path.abspath(sys.modules[__name__].__file__)) if "__file__" in globals() else HERE, "data", "t2r_process_types.json")))
    return {sid(n) for n in names if n != "None"}


def _data_dir():
    base = getattr(sys, "_MEIPASS", HERE)
    return os.path.join(base, "data")


PROC = None


def proc_sids():
    global PROC
    if PROC is None:
        PROC = {sid(n) for n in json.load(open(os.path.join(_data_dir(), "t2r_process_types.json"))) if n != "None"}
    return PROC


# ------------------------------------------------------------------ read
class Spawner:
    __slots__ = ("name", "art", "pos", "quat", "scale", "ptype", "multi", "auto", "props", "parent")


def _cstr(pg_bytes, off):
    e = pg_bytes.index(b"\0", off)
    return pg_bytes[off:e].decode("utf-8")


def read(data):
    """-> (spawners in the reader's order, level info or None); refuses nav meshes"""
    pk = t2pak.TPak(data)
    items = pk.items()
    if any(n == "NAV_MESH_1" for n, _, _ in items):
        raise SystemExit("NAV_MESH_1 items are not carried by this port")
    sg = [(p, o) for n, p, o in items if n == "SPAWNER_GROUP"]
    if not sg:
        raise SystemExit("no SPAWNER_GROUP in the pak")
    pg, off = sg[0]
    page = pk.pages[pg]

    def target(pgx, offx):
        r = pk.ptr(pgx, offx)
        return r                                # (dst page, dst offset) or None

    cnt = struct.unpack_from("<Q", page, off + 16)[0]
    out = []
    arr = target(pg, off + 8)
    if cnt and arr:
        apg, aoff = arr
        for i in range(cnt):
            t = target(apg, aoff + 8 * i)
            out.append(read_spawner(pk, *t))
    out.sort(key=lambda s: 0)                   # (the reader's name-order sort only reorders equal sids: stable file order is kept)
    # parent links by name (ReadSpawner reads the parent as its own object; ParseSpawnerGroup relinks it to a list member of that name)
    names = {}
    for s in out:
        names.setdefault(s.name, []).append(s)
    for s in out:
        if s.parent is None:
            continue
        cands = names.get(s.parent, [])
        other = next((c for c in cands if c is not s), None)
        s.parent = other.name if other is not None else None
    li = None
    for n, p, o in items:
        if n == "LEVEL_INFO_4":
            pgx = pk.pages[p]
            nsid = struct.unpack_from("<I", pgx, o + 4)[0]
            sp, nm = target(p, o + 8), target(p, o + 16)
            sids = []
            if nsid and sp:
                sids = [struct.unpack_from("<Q", pk.pages[sp[0]], sp[1] + 8 * k)[0] for k in range(nsid)]
            li = (_cstr(pk.pages[nm[0]], nm[1]) if nm else "", sids)
            break
    return out, li


def read_spawner(pk, pg, off):
    P = pk.pages[pg]
    s = Spawner()
    s.pos = bytes(P[off:off + 12])
    s.quat = bytes(P[off + 16:off + 32])
    s.scale = bytes(P[off + 32:off + 44])
    t = pk.ptr(pg, off + 80)
    s.name = _cstr(pk.pages[t[0]], t[1])
    s.ptype = struct.unpack_from("<Q", P, off + 112)[0]
    t = pk.ptr(pg, off + 120)
    if t is None:                                # SceneEditor: SeekPointer fails, the stream stays where ReadString(name) stopped -> the art group is
        npg, noff = pk.ptr(pg, off + 80)           # whatever string follows the name (a quirk the output bakes in)
        t = (npg, noff + len(s.name.encode("utf-8")) + 1)
    s.art = _cstr(pk.pages[t[0]], t[1])
    s.multi = P[off + 130] == 8
    s.auto = P[off + 131] == 0
    par = pk.ptr(pg, off + 144)
    s.parent = read_spawner(pk, *par).name if par else None
    # property table: ptr at +152 -> {ptr to entries, u64 count}; entry = {u64 sid, ptr to value block}
    pt = pk.ptr(pg, off + 152)
    tbl = pk.ptr(*pt)
    n = struct.unpack_from("<Q", pk.pages[pt[0]], pt[1] + 8)[0]
    s.props = []
    for k in range(n):
        epg, eoff = tbl
        psid = struct.unpack_from("<Q", pk.pages[epg], eoff + 16 * k)[0]
        vb = pk.ptr(epg, eoff + 16 * k + 8)
        vp = pk.pages[vb[0]]
        dtype = struct.unpack_from("<H", vp, vb[1])[0]
        v = prop_value(pk, vb[0], vb[1], dtype, psid)
        if v is not None:
            s.props.append((psid, dtype, v))
    return s


def prop_value(pk, pg, off, dtype, psid):
    """-> the raw payload to write back, or None when the reader's text would be empty (the property is dropped)"""
    P = pk.pages[pg]
    d = off + 16                                # {u16 type, u16 size, u32, ptr data} then the value
    if dtype == 1:
        return bytes(P[d:d + 4])
    if dtype == 4:
        return bytes(P[d:d + 4])
    if dtype == 5:
        t = pk.ptr(pg, d)
        s = _cstr(pk.pages[t[0]], t[1])
        return s.encode("utf-8") if s else None
    if dtype in (7, 8, 9):
        return bytes(P[d:d + 12])
    if dtype == 13:
        v = struct.unpack_from("<Q", P, d)[0]
        return struct.pack("<Q", v) if v else None
    if dtype == 6:
        # array: name must be one of the three the reader knows; the value string is re-parsed float by float, so the bytes are the raw ones
        name = {sid(n): n for n in ARRAY_NAMES}.get(psid)
        if name is None:
            return None
        if name == "NavMeshBlocker":
            n = struct.unpack_from("<Q", P, d + 8)[0]
            return bytes(P[d:d + 16 + 16 * n])
        if name == "PerchPointsData":
            n = struct.unpack_from("<I", P, d + 4)[0]
            return bytes(P[d:d + 16 + 32 * n])
        n = struct.unpack_from("<Q", P, d)[0]            # MoveModData
        return bytes(P[d:d + 16 + 64 * n])
    return None


# ------------------------------------------------------------------ write
class PageWriter:
    def __init__(self):
        self.b = bytearray()
        self.relocs = []

    def pos(self):
        return len(self.b)

    def w(self, data):
        self.b += data

    def u32(self, v):
        p = len(self.b)
        self.b += struct.pack("<I", v & 0xFFFFFFFF)
        return p

    def u64(self, v):
        p = len(self.b)
        self.b += struct.pack("<Q", v & M64)
        return p

    def pad(self, n):
        while len(self.b) % n:
            self.b.append(0)

    def ptr(self, v, to_page=0):
        p = len(self.b)
        self.relocs.append((0, to_page, p))
        self.b += struct.pack("<Q", v & M64)
        return p

    def upd_ptr(self, off, v, to_page=0):
        self.relocs.append((0, to_page, off))
        struct.pack_into("<Q", self.b, off, v & M64)

    def upd32(self, off, v):
        struct.pack_into("<I", self.b, off, v & 0xFFFFFFFF)

    def upd64(self, off, v):
        struct.pack_into("<Q", self.b, off, v & M64)

    def string(self, s):
        p = len(self.b)
        if s:
            self.b += s.encode("utf-8") + b"\0"
        else:
            self.b += b"\0\0"
        return p


def write(spawners, levelinfo=None):
    """T2R package without nav meshes / region tree / feature db (bytes of the SceneEditor's PackageWriter.BuildPackage for that input)"""
    PROCS = proc_sids()
    sp = sorted(spawners, key=lambda s: sid(s.name))
    logins = []                                    # dicts: str, id_str, size_ptr, id_ptr, size_off, start

    pw = PageWriter()
    pw.u64(MAGIC)
    hdr = pw.pos()
    num3 = 3 + 0 + 0 + 4
    pw.u32(0)
    pw.u32(0)
    pw.w(struct.pack("<HH", 0, 0))
    for _ in range(num3):
        pw.u64(0)
        pw.u32(0)
        pw.u32(0)

    def login(text, idstr, value2):
        pw.pad(16)
        e = {"str": text, "id": idstr}
        e["size_ptr"] = pw.u64(0)
        e["id_ptr"] = pw.u64(0)
        e["size_off"] = pw.u32(value2)
        for _ in range(7):
            pw.u32(FILL)
        e["start"] = pw.pos()
        logins.append(e)
        return e

    sg = login("SpawnerGroup", "SPAWNER_GROUP", 0)
    pw.u64(0)
    off1 = pw.u64(0)
    pw.u64(len(sp))
    off2 = pw.u64(0)
    pw.u64(len(sp))
    pw.w(bytes(256))
    pw.u64(16777216)
    pw.u64(0)
    off3 = pw.u64(0)
    pw.u64(1)
    starts = []
    for s in sp:
        starts.append(pw.pos())
        pw.w(s.pos)
        pw.w(struct.pack("<f", 1.0))
        pw.w(s.quat)
        pw.w(s.scale)
        pw.w(struct.pack("<f", 0.0))
        o4 = pw.u64(0)
        pw.u64(sid(s.name))
        o5 = pw.u64(0)
        pw.u64(0)
        o6 = pw.u64(0)
        pw.u64(sid(s.name))
        pw.u64(0)
        pw.u64(0)
        pw.u64(s.ptype if s.ptype in PROCS else 0)
        o7 = pw.u64(0)
        pw.w(bytes([0, 0, 8 if s.multi else 0, 0 if s.auto else 64]))
        pw.u32(0)
        pw.ptr(sg["start"])
        pw.u64(0)
        o8 = pw.u64(0)
        pw.w(bytes(32))
        o9 = pw.u64(0)
        pw.w(bytes(80))
        pw.upd_ptr(o8, pw.pos())
        pw.ptr(pw.pos() + 16)
        props = sorted(s.props, key=lambda p: p[0])
        pw.u64(len(props))
        slots = []
        for psid, _t, _v in props:
            pw.u64(psid)
            slots.append(pw.pos())
            pw.u64(0)
        for slot, (psid, dtype, v) in zip(slots, props):
            pw.upd_ptr(slot, pw.pos())
            pw.w(struct.pack("<h", dtype))
            if dtype in (1, 4):
                pw.w(struct.pack("<h", 4))
                pw.u32(0)
                pw.ptr(pw.pos() + 8)
                pw.w(v)
                pw.u32(0)
            elif dtype == 5:
                pw.w(struct.pack("<h", len(v)))
                pw.u32(0)
                pw.ptr(pw.pos() + 8)
                pw.ptr(pw.pos() + 8)
                pw.string(v.decode("utf-8"))
            elif dtype == 6:
                pw.w(struct.pack("<h", 8))
                pw.u32(0)
                pw.ptr(pw.pos() + 8)
                pw.w(v)
            elif dtype in (7, 8, 9):
                pw.w(struct.pack("<h", 16))
                pw.u32(0)
                pw.ptr(pw.pos() + 8)
                pw.w(v)
            elif dtype == 13:
                pw.w(struct.pack("<h", 4))
                pw.u32(0)
                pw.ptr(pw.pos() + 8)
                pw.w(v)
            else:
                raise SystemExit("unsupported property type %d" % dtype)
        pw.u32(0)
        pw.upd_ptr(o5, pw.pos())
        pw.upd_ptr(o9, pw.pos() + 2)
        pw.u32(0)
        pw.upd_ptr(o4, pw.pos())
        pw.string(s.name)
        pw.upd_ptr(o6, pw.pos())
        pw.string(s.name)
        pw.upd_ptr(o7, pw.pos())
        pw.string(s.art)
        pw.u32(0)
    for i, s in enumerate(sp):                      # parent links: the first spawner of the parent's name
        if s.parent is None:
            continue
        for j, t in enumerate(sp):
            if t.name == s.parent:
                pw.upd_ptr(starts[i] + 144, starts[j])
                break
    pw.upd_ptr(off1, pw.pos())
    for st in starts:
        pw.ptr(st)
    pw.upd_ptr(off2, pw.pos())
    for s, st in zip(sp, starts):
        pw.u64(sid(s.name))
        pw.ptr(st)
    pw.upd_ptr(off3, pw.pos())
    pw.u64(0)
    pw.ptr(pw.pos() + 8)
    pw.ptr(pw.pos() + 16)
    pw.u64(len(sp))
    for s, st in zip(sp, starts):
        pw.u64(sid(s.name))
        pw.ptr(st)
    pw.upd32(sg["size_off"], pw.pos() - sg["start"])

    # level info
    if levelinfo and levelinfo[0]:
        nm = levelinfo[0].encode("utf-8")
        sids = levelinfo[1]
        e = login("", "LEVEL_INFO_4", 24 + 8 * len(sids) + len(nm) + 1)
        li_off = e["start"] - 48
        pw.u32(0)
        pw.u32(len(sids))
        if sids:
            pw.ptr(e["start"] + 24)
        else:
            pw.u64(0)
        pw.ptr(e["start"] + 24 + 8 * len(sids))
        for x in sids:
            pw.u64(x)
        pw.w(nm)
        pw.w(b"\0")
    else:
        e = login("", "LEVEL_INFO_3", 16)
        li_off = e["start"] - 48
        pw.u64(0)
        pw.u64(0)
    e = login("", "FEATURE_DB_2", 80)
    fdb_off = e["start"] - 48
    pw.w(bytes(80))
    e = login("", "SPLINE_TABLE", 4)
    spl_off = e["start"] - 48
    pw.u32(0)
    e = login("coverActionPackCount", "TAG_INT", 4)
    tag_off = e["start"] - 48
    pw.u32(0)
    n20 = 1 + 0 + 0 + 4
    plt = login("", "PAK_LOGIN_TABLE", n20 * 8 + 8)
    login_table_off = plt["start"] - 48
    pw.u32(n20)
    pw.u32(FILL)
    pw.u32(0)
    pw.u32(sg["start"] - 48)
    for o in (li_off, fdb_off, spl_off, tag_off):
        pw.u32(0)
        pw.u32(o)
    vr = login("", "VRAM_DESC_TABLE", 8)
    vram_off = vr["start"] - 48
    pw.u64(0)

    # login strings
    raw_done = False
    str_pos = []
    for e in logins:
        pw.upd64(e["id_ptr"], pw.pos())
        pw.string(e["id"])
        if not raw_done:
            pw.string("RAW_DATA")
            pw.string("_chunk0.0")
            raw_done = True
        p = pw.pos()
        pw.upd64(e["size_ptr"], p)
        pw.string(e["str"])
        str_pos.append(p)
    pw.pad(16)
    end = pw.pos()
    # the page header, now that the login count / length are known
    struct.pack_into("<IIHH", pw.b, hdr, 0, len(pw.b), 0, len(logins))
    q = hdr + 12
    for e, p in zip(logins, str_pos):
        struct.pack_into("<QII", pw.b, q, p, e["start"] - 48, FILL)
        q += 16
    page = bytes(pw.b)

    # container (PackageWriter.WritePackageFile): 44-byte header, one page-table entry, {0, reloc offset, reloc count}, 84 zero bytes, pad 16,
    # the relocation table inserted there, pad 16, the page
    rel = b"".join(struct.pack("<HHI", a, b, c) for a, b, c in pw.relocs)
    hb = bytearray(struct.pack("<11I", 2681, 0, 0, login_table_off, 1, 44, 8, 56, 0, 0, vram_off))
    hb += struct.pack("<III", 0, 500000, 0)
    hb += struct.pack("<III", 0, 0, len(pw.relocs))
    hb += bytes(84)
    while len(hb) % 16:
        hb.append(0)
    struct.pack_into("<I", hb, 60, len(hb))                        # reloc table offset (right after the header block)
    struct.pack_into("<I", hb, 4, len(hb) + len(rel))              # total header size
    out = bytearray(hb) + rel
    while len(out) % 16:
        out.append(0)
    start = len(out)
    out += page
    struct.pack_into("<II", out, 44, start, len(page))             # page table entry: start, size (flags stay 0)
    return bytes(out)


DATA_TYPES = {1: "Int32", 4: "Float", 5: "String", 6: "Array", 7: "Vector3_7", 8: "Vector3_8", 9: "Vector3_9", 13: "StringId64"}


def fstr(raw):
    """.NET Core float.ToString(InvariantCulture): shortest round-trip digits, exponent form below 1e-5 / from 1e15"""
    import numpy as np
    f = np.frombuffer(raw, dtype="<f4")[0]
    if f != f:
        return "NaN"
    if f in (np.inf, -np.inf):
        return "Infinity" if f > 0 else "-Infinity"
    if f == 0:
        return "-0" if raw[3] & 0x80 else "0"
    sci = np.format_float_scientific(f, unique=True, trim="-")        # e.g. -4.8e+01
    mant, exp = sci.split("e")
    exp = int(exp)
    neg = mant.startswith("-")
    digits = mant.lstrip("-").replace(".", "")
    if exp < -5 or exp >= 15:
        m = digits[0] + ("." + digits[1:] if len(digits) > 1 else "")
        return ("-" if neg else "") + m + "E" + ("+" if exp >= 0 else "-") + "%02d" % abs(exp)
    if exp >= 0:
        txt = digits + "0" * (exp + 1 - len(digits)) if len(digits) <= exp + 1 else digits[:exp + 1] + "." + digits[exp + 1:]
    else:
        txt = "0." + "0" * (-exp - 1) + digits
    return ("-" if neg else "") + txt


def prop_name(psid):
    names = {sid(n): n for n in ARRAY_NAMES}
    names.update({sid(n): n for n in _proc_names() if n != "None"})
    return names.get(psid, "#%016X" % psid)


def _proc_names():
    return json.load(open(os.path.join(_data_dir(), "t2r_process_types.json")))


def prop_text(psid, dtype, v):
    if dtype == 1:
        return str(struct.unpack("<i", v)[0])
    if dtype == 4:
        return fstr(v)
    if dtype == 5:
        return v.decode("utf-8")
    if dtype in (7, 8, 9):
        return ", ".join(fstr(v[i:i + 4]) for i in (0, 4, 8))
    if dtype == 13:
        return "#%016X" % struct.unpack("<Q", v)[0]
    name = prop_name(psid)
    if name == "NavMeshBlocker":
        n = struct.unpack_from("<Q", v, 8)[0]
        return ", ".join(["#%016X" % struct.unpack_from("<Q", v, 0)[0] if struct.unpack_from("<Q", v, 0)[0] else "", str(n)] + [fstr(v[16 + 4 * i:20 + 4 * i]) for i in range(4 * n)])
    if name == "PerchPointsData":
        a, n, c = struct.unpack_from("<IIQ", v, 0)
        return ", ".join([str(a), str(n), str(c)] + [fstr(v[16 + 4 * i:20 + 4 * i]) for i in range(8 * n)])
    a, n = struct.unpack_from("<QQ", v, 0)
    return ", ".join([str(a), str(n)] + [fstr(v[16 + 4 * i:20 + 4 * i]) for i in range(16 * n)])


def spawner_json(spawners):
    """the ps1's -Json: [{n, t (T2RProcessTypes value), a, p [x, y, z], pr [{k, t, v}]}] (properties by name, ordinal)"""
    names = _proc_names()
    by_sid = {sid(n): i for i, n in enumerate(names) if n != "None"}
    out = []
    for s in spawners:
        pr = [{"k": prop_name(psid), "t": DATA_TYPES.get(dt, ""), "v": prop_text(psid, dt, v)} for psid, dt, v in s.props]
        pr.sort(key=lambda q: q["k"].encode("utf-8"))
        out.append({"n": s.name, "t": by_sid.get(s.ptype, 0), "a": s.art, "p": ["__F:" + fstr(s.pos[i:i + 4]) + "__" for i in (0, 4, 8)], "pr": pr})
    return out


def json_text(spawners):
    import re
    t = json.dumps(spawner_json(spawners), separators=(",", ":"), ensure_ascii=False)
    return re.sub(r'"__F:([^"]+)__"', lambda m: m.group(1), t)


def rewrite(in_bytes, drop=()):
    sp, li = read(in_bytes)
    keep = [s for s in sp if not any(s.name.startswith(d) for d in drop)]
    return write(keep, li), len(keep), len(sp) - len(keep)


def main(argv):
    a = {}
    i = 1
    while i < len(argv):
        if argv[i] in ("-Pak", "-Out", "-Drop", "-Json") and i + 1 < len(argv):
            a[argv[i][1:]] = argv[i + 1]
            i += 2
        else:
            raise SystemExit("usage: p1_spawner_pak.py -Pak in.pak -Out out.pak [-Drop a,b]")
    drop = [d for d in a.get("Drop", "").split(",") if d]
    out, kept, dropped = rewrite(open(a["Pak"], "rb").read(), drop)
    if a.get("Json"):
        sp, _li = read(open(a["Pak"], "rb").read())
        open(a["Json"], "w", encoding="utf-8").write(json_text([x for x in sp if not any(x.name.startswith(d) for d in drop)]))
    tmp = a["Out"] + ".tmp"
    open(tmp, "wb").write(out)
    os.replace(tmp, a["Out"])
    print(f"{a['Out']} : {kept} spawners ({dropped} dropped)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
