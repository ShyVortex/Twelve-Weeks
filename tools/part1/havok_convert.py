"""Part I (Havok 2020.1 memory image) -> TLOU2 (Havok 2017.1 tagfile) level collision translator.

Spec: re/part1/havok-collision.md.  Both games store level collision as COLLISION_DATA_HAVOK_BG items holding ONE
hknpCompressedMeshShape each.  Part I's is a raw 2020.1 object image (relative pointers, no type info); TLOU2's is a
2017.1 binary tagfile (havok_tag.py).  The geometry codecs (section codec, shared / packed vertex quantisation,
primitives, data runs, shape keys, both BVHs) are the same; only object layouts and the BVH node encoding differ.
TLOU2 keeps every item below 1 MiB (its pak pages are <= 1 MiB), so a Part I level mesh (one ~3 MB blob for the
Bookstore) is split into several shapes along section boundaries (the vertex data of a section is copied verbatim;
shared vertices are re-quantised to the piece's domain, error < 1e-5 m).

  python havok_convert.py roundtrip <tlou2 -phys.pak>...        # decode + re-encode every tagfile: byte-identical?
  python havok_convert.py convert <part1 -phys.pak> <out tlou2 -phys.pak> [--budget=0xE0000]
  python havok_convert.py check <part1 -phys.pak> <converted -phys.pak>   # triangles / bounds / trees / keys
  python havok_convert.py info <pak>                             # either game: items, sections, triangles, bounds
  python havok_convert.py preview <part1 -phys.pak>... --geo <part1 level.pak>... --out <png>
The Havok TYPE section (reflection data) is not ours: it is read at run time from a real TLOU2 -phys pak
(T2R_HK_TYPES=<pak>, default the first re/part1/x/t2ref/*-phys.pak, else extracted from the TLOU2 install).
"""
import glob
import os
import struct
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.dirname(HERE)
ROOT = os.path.dirname(TOOLS)
MAIN = os.environ.get("T2R_MAIN_ROOT", ROOT.split(os.sep + ".claude" + os.sep)[0])
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(TOOLS, "models"))
import havok_tag  # noqa: E402

FLT_MAX = np.float32(3.40282e38)
CODEC_DIV = 226.0               # hkcdStaticTree::Codec3Axis: child = parent.min + a^2 * ext / 226, parent.max - b^2 * ext / 226
BUDGET = 0xE0000                # max tagfile bytes per TLOU2 item (TLOU2 items + tag stay below 1 MiB pages)
U32, U64 = struct.Struct("<I"), struct.Struct("<Q")


def fnv(s):
    h = 0xcbf29ce484222325
    for c in s.encode():
        h = ((h ^ c) * 0x100000001b3) & (2 ** 64 - 1)
    return h


BG_ID = fnv("COLLISION_DATA_HAVOK_BG")


# ====================================================================================================== mesh model
class Section:
    __slots__ = ("nodes", "dom", "codec", "fp", "so", "nsh", "shlow", "po", "npr", "ro", "nru", "npv", "leaf", "tail")

    def __init__(self, **kw):
        for k in self.__slots__:
            setattr(self, k, kw.get(k))


class Mesh:
    """one hknpCompressedMeshShape, game independent.  Raw little-endian bytes are kept where the two games agree
    so that a TLOU2 round trip is byte exact."""

    def __init__(self):
        self.flags = 4
        self.keybits = 0
        self.dispatch = 3
        self.radius = b"\0" * 4
        self.user = 0
        self.codec_info = 1
        self.words = np.zeros(0, np.uint32)       # triangleIsInterior bit field
        self.nbits = 0
        self.dom = b"\0" * 32                     # meshTree.domain (min vec4, max vec4)
        self.npk = self.bpk = self.maxkey = 0
        self.flat = 255
        self.tree5 = b""                          # meshTree.nodes (Codec3Axis5, section BVH)
        self.sections = []
        self.prims = b""                          # 4 bytes each
        self.svi = np.zeros(0, np.uint16)
        self.packed = np.zeros(0, np.uint32)
        self.shared = np.zeros(0, np.uint64)
        self.runs = b""                           # 4 bytes each {u16 shape tag, u8 first prim, u8 count}
        self.simd = b""                           # hkcdSimdTree nodes, TLOU2 encoding (112 bytes)

    def domain(self):
        f = np.frombuffer(self.dom, np.float32).astype(np.float64)
        return f[0:3], f[4:7]


# -------------------------------------------------------------------------------------------- geometry decoding
def section_vertices(m, s, shared_xyz):
    out = []
    cp = np.frombuffer(s.codec, np.float32).astype(np.float64)
    if s.npv:
        q = m.packed[s.fp:s.fp + s.npv].astype(np.int64)
        out.append(cp[:3] + cp[3:] * np.stack([q & 0x7FF, (q >> 11) & 0x7FF, q >> 22], 1))
    if s.nsh:
        out.append(shared_xyz[m.svi[s.so:s.so + s.nsh].astype(np.int64)])
    return np.concatenate(out) if out else np.zeros((0, 3))


def shared_positions(m):
    dmin, dmax = m.domain()
    q = m.shared.astype(np.uint64)
    x = (q & np.uint64(0x1FFFFF)).astype(np.float64)
    y = ((q >> np.uint64(21)) & np.uint64(0x1FFFFF)).astype(np.float64)
    z = (q >> np.uint64(42)).astype(np.float64)
    return dmin + np.stack([x / 0x1FFFFF, y / 0x1FFFFF, z / 0x3FFFFF], 1) * (dmax - dmin)


def triangles(m):
    """(keys u32 array, (N,3,3) float64 vertices, tags) of every triangle; key = section<<8 | prim<<1 | second"""
    sv = shared_positions(m)
    prims = np.frombuffer(m.prims, np.uint8).reshape(-1, 4)
    runs = np.frombuffer(m.runs, np.uint8).reshape(-1, 4)
    keys, tris, tags = [], [], []
    for si, s in enumerate(m.sections):
        V = section_vertices(m, s, sv)
        tag = np.zeros(s.npr, np.int64)
        for r in runs[s.ro:s.ro + s.nru]:
            v = int(r[0]) | int(r[1]) << 8
            tag[r[2]:r[2] + r[3]] = v
        for p in range(s.npr):
            a, b, c, d = prims[s.po + p]
            if max(a, b, c, d) >= len(V):                  # ND filler primitive (a b a b, indices past the section's vertices;
                continue                                    # the-auditorium-nor-ext-phys item 0 section 106): no area, no triangle
            keys.append(si << 8 | p << 1)
            tris.append(V[[a, b, c]])
            tags.append(tag[p])
            if c != d:
                keys.append(si << 8 | p << 1 | 1)
                tris.append(V[[a, c, d]])
                tags.append(tag[p])
    return np.array(keys, np.int64), np.array(tris).reshape(-1, 3, 3), np.array(tags, np.int64)


def prim_boxes(m):
    """(N,2,3) AABB of every primitive (all 4 corners) in section order, and their keys"""
    sv = shared_positions(m)
    prims = np.frombuffer(m.prims, np.uint8).reshape(-1, 4)
    boxes, keys = [], []
    for si, s in enumerate(m.sections):
        V = section_vertices(m, s, sv)
        idx = prims[s.po:s.po + s.npr].astype(np.int64)
        # ND filler primitives (a b a b with indices past the section's vertices, see triangles()) have no triangle, no key (the source
        # npk leaves them out) and no SIMD leaf (hun-checkpoint-maze / hun-underpass-midground: IndexError before)
        real = idx.max(1) < len(V)
        P = V[idx[real]]
        boxes.append(np.stack([P.min(1), P.max(1)], 1).reshape(-1, 2, 3))
        keys.append((si << 8) | (np.arange(s.npr)[real] << 1))
    return np.concatenate(boxes), np.concatenate(keys)


# ================================================================================================ Part I reader
def p1_collision_items(data):
    """[{kind, nbits, records, blob, data(DATA section bytes), sdk}] of a Part I -phys pak (raw 0xA7D container)"""
    import p1_convert
    P = p1_convert.parse(data)
    pages = P["pages"]
    base = [0]
    for s, z, f in pages:
        base.append(base[-1] + z)
    mem = b"".join(data[s:s + z] for s, z, f in pages)
    fx = {}
    for sp, dp, so in P["fix"]:
        fx[base[sp] + so] = dp
    out = []
    for pi, off, tid in p1_convert.scan_items(data, pages):
        if tid != BG_ID:
            continue
        b = base[pi] + off + 48

        def ptr(k):
            dp = fx.get(b + k)
            return None if dp is None else base[dp] + U64.unpack_from(mem, b + k)[0]
        ver, kind, tsz = struct.unpack_from("<III", mem, b)
        nbits, nrec = struct.unpack_from("<II", mem, b + 56)
        t = ptr(96)
        tag = mem[t:t + tsz]
        secs = {k: (s, e) for k, _, s, e in havok_tag.sections(tag, 8, len(tag))}
        out.append({"version": ver, "kind": kind, "nbits": nbits,
                    "records": mem[ptr(80):ptr(80) + 8 * nrec], "blob": mem[ptr(64):ptr(64) + (nbits + 7) // 8],
                    "sdk": tag[secs["SDKV"][0]:secs["SDKV"][1]].decode(), "data": tag[secs["DATA"][0]:secs["DATA"][1]]})
    return out


def p1_mesh(D):
    """hknpCompressedMeshShape (Havok 2020.1 memory image, pointers relative to their own field) -> Mesh"""
    u32 = lambda o: U32.unpack_from(D, o)[0]

    def arr(o):
        v = U64.unpack_from(D, o)[0]
        return (o + v if v else 0), u32(o + 8)
    m = Mesh()
    typ, m.dispatch, m.flags, m.keybits = struct.unpack_from("<BBHB", D, 0x18)
    assert typ == 8, "Part I shape type %d is not COMPRESSED_MESH (8)" % typ
    m.radius = D[0x20:0x24]
    m.user = U64.unpack_from(D, 0x28)[0]
    m.codec_info = u32(0x40)
    dobj = 0x48 + U64.unpack_from(D, 0x48)[0]
    wa, wn = arr(0x50)
    m.words = np.frombuffer(D, np.uint32, wn, wa).copy()
    m.nbits = u32(0x60)
    mt = dobj + 0x20
    m.dom = D[mt + 0x10:mt + 0x30]
    m.npk, m.bpk, m.maxkey, m.flat = struct.unpack_from("<IIIB", D, mt + 0x30)
    a, n = arr(mt)
    m.tree5 = D[a:a + 5 * n]
    pa, pn = arr(mt + 0x50)
    m.prims = D[pa:pa + 4 * pn]
    a, n = arr(mt + 0x60)
    m.svi = np.frombuffer(D, np.uint16, n, a).copy() if n else np.zeros(0, np.uint16)
    a, n = arr(mt + 0x70)
    m.packed = np.frombuffer(D, np.uint32, n, a).copy() if n else np.zeros(0, np.uint32)
    a, n = arr(mt + 0x80)
    m.shared = np.frombuffer(D, np.uint64, n, a).copy() if n else np.zeros(0, np.uint64)
    a, n = arr(mt + 0x90)
    m.runs = D[a:a + 4 * n]
    sa, sn = arr(mt + 0x40)
    for i in range(sn):
        o = sa + 96 * i
        na, nn = arr(o)
        fp, so, po, ro = struct.unpack_from("<4I", D, o + 0x48)
        npv, npr, nru, x5b, leaf = struct.unpack_from("<BBBBH", D, o + 0x58)
        m.sections.append(Section(nodes=D[na:na + 4 * nn], dom=D[o + 0x10:o + 0x30], codec=D[o + 0x30:o + 0x48], fp=fp,
                                  so=so, shlow=npv, po=po, npr=npr, ro=ro, nru=nru, npv=npv, leaf=leaf,
                                  tail=bytes(4)))
        # 2017.1 packs sharedVertices = (offset << 8 | numPackedVertices) (measured on every TLOU2 section);
        # +0x5b and +0x5e/f are 0 in every Part I section seen, TLOU2's page / flags / layerData bytes are always 0
    # 2020.1 has no per-section shared-index count: sections own consecutive slices of sharedVerticesIndex
    for i, s in enumerate(m.sections):
        s.nsh = (m.sections[i + 1].so if i + 1 < sn else len(m.svi)) - s.so
    # simd tree: 128-byte nodes {6 x vec4 AABBs, u32 data[4], u32 isLeaf, pad}; leaf data = primitive keys,
    # internal data = node indices.  TLOU2: 112-byte nodes, data = key << 1 | 1 (leaf) or node << 1, 0 = empty
    a, n = arr(dobj + 0xC0)
    out = bytearray()
    for i in range(n):
        o = a + 128 * i
        box = D[o:o + 96]
        f = np.frombuffer(box, np.float32).reshape(6, 4)
        data = struct.unpack_from("<4I", D, o + 96)
        leaf = u32(o + 112)
        enc = []
        for j in range(4):
            if f[0, j] > f[1, j]:
                enc.append(0)
            else:
                enc.append(data[j] << 1 | 1 if leaf else data[j] << 1)
        out += box + struct.pack("<4I", *enc)
    m.simd = bytes(out)
    # Part I's numPrimitiveKeys can exceed the triangle count by a few (2020.1 counts differently); TLOU2's equals
    # the triangle count in every file seen
    m.npk = len(triangles(m)[0])
    return m


# ================================================================================================= TLOU2 reader
def t2_mesh(T):
    """havok_tag.Tag (2017.1, root hknpCompressedMeshShape) -> Mesh"""
    D = T.data
    items = T.items

    def arr(o):
        k = U64.unpack_from(D, o)[0]
        if not k:
            return 0, 0
        return items[k][2], items[k][3]
    assert T.tname(items[1][0]) == "hknpCompressedMeshShape"
    m = Mesh()
    m.flags, typ, m.keybits, m.dispatch = struct.unpack_from("<HBBB", D, 0x20)
    assert typ == 9
    m.radius = D[0x28:0x2C]
    m.user = U64.unpack_from(D, 0x30)[0]
    m.codec_info = U32.unpack_from(D, 0x40)[0]
    dobj = items[U64.unpack_from(D, 0x50)[0]][2]
    a, n = arr(0x58)
    m.words = np.frombuffer(D, np.uint32, n, a).copy()
    m.nbits = U32.unpack_from(D, 0x68)[0]
    mt = dobj + 0x20
    m.dom = D[mt + 0x10:mt + 0x30]
    m.npk, m.bpk, m.maxkey, m.flat = struct.unpack_from("<IIIB", D, mt + 0x30)
    a, n = arr(mt)
    m.tree5 = D[a:a + 5 * n]
    a, n = arr(mt + 0x50)
    m.prims = D[a:a + 4 * n]
    a, n = arr(mt + 0x60)
    m.svi = np.frombuffer(D, np.uint16, n, a).copy() if n else np.zeros(0, np.uint16)
    a, n = arr(mt + 0x70)
    m.packed = np.frombuffer(D, np.uint32, n, a).copy() if n else np.zeros(0, np.uint32)
    a, n = arr(mt + 0x80)
    m.shared = np.frombuffer(D, np.uint64, n, a).copy() if n else np.zeros(0, np.uint64)
    a, n = arr(mt + 0x90)
    m.runs = D[a:a + 4 * n]
    a, n = arr(dobj + 0xC0)
    m.simd = D[a:a + 112 * n]
    sa, sn = arr(mt + 0x40)
    for i in range(sn):
        o = sa + 96 * i
        na, nn = arr(o)
        fp, sv, pr, ru = struct.unpack_from("<4I", D, o + 0x48)
        npv, nsh, leaf = struct.unpack_from("<BBH", D, o + 0x58)
        m.sections.append(Section(nodes=D[na:na + 4 * nn], dom=D[o + 0x10:o + 0x30], codec=D[o + 0x30:o + 0x48], fp=fp,
                                  so=sv >> 8, shlow=sv & 255, po=pr >> 8, npr=pr & 255, ro=ru >> 8, nru=ru & 255,
                                  npv=npv, nsh=nsh, leaf=leaf, tail=D[o + 0x5C:o + 0x60]))
    return m


# ================================================================================================= TLOU2 writer
class _Data:
    def __init__(self):
        self.b = bytearray()
        self.items = [(0, 0, 0, 0)]
        self.ptch = {}

    def align(self, a=16):
        while len(self.b) % a:
            self.b.append(0)

    def put(self, raw):
        o = len(self.b)
        self.b += raw
        return o

    def item(self, ty, flag, off, cnt):
        self.items.append((ty, flag, off, cnt))
        return len(self.items) - 1

    def patch(self, ty, off, value):
        U64.pack_into(self.b, off, value)
        self.ptch.setdefault(ty, []).append(off)


def encode_t2(m, ref):
    """Mesh -> TLOU2 tagfile bytes; ref = a real TLOU2 Tag (its TYPE section and type indices are reused)"""
    ty = ref.by_name
    t_shape, t_data = ty("hknpCompressedMeshShape"), ty("hknpCompressedMeshShapeData")
    t_u32, t_u16, t_u64 = ty("hkUint32"), ty("hkUint16"), ty("hkUint64")
    t_c5, t_c4 = ty("hkcdStaticTree::Codec3Axis5"), ty("hkcdStaticTree::Codec3Axis4")
    t_sec, t_prim = ty("hkcdStaticMeshTreeBase::Section"), ty("hkcdStaticMeshTreeBase::Primitive")
    t_run, t_simd = ty("hknpCompressedMeshShapeTreeDataRun"), ty("hkcdSimdTree::Node")
    arrt = lambda el: ty("hkArray<tT=%s,tAllocator=hkContainerHeapAllocator>" % el)
    p_ref = ty("hkRefPtr<tTYPE=hkReferencedObject>")
    w = _Data()
    # --- layout (same order as TLOU2's own files): shape, its bit-field words, data object, data arrays, section trees
    shape = w.put(bytes(0x90))
    w.align()
    words = w.put(m.words.astype("<u4").tobytes())
    w.align()
    dobj = w.put(bytes(0x100))
    arrays = []
    for name, raw, t_el in (("tree5", m.tree5, t_c5), ("sections", None, t_sec), ("prims", m.prims, t_prim),
                            ("svi", m.svi.astype("<u2").tobytes(), t_u16),
                            ("packed", m.packed.astype("<u4").tobytes(), t_u32),
                            ("shared", m.shared.astype("<u8").tobytes(), t_u64), ("runs", m.runs, t_run),
                            ("simd", m.simd, t_simd)):
        if name == "sections":
            raw = bytes(96 * len(m.sections))
        size = ref.resolved(t_el, "size")
        w.align()
        arrays.append((name, w.put(raw), len(raw) // size, t_el))
    sec_nodes = []
    for s in m.sections:
        w.align()
        sec_nodes.append((w.put(s.nodes), len(s.nodes) // 4))
    w.align()
    # --- items (discovery order) and pointers
    i_shape = w.item(t_shape, 0x10, shape, 1)
    i_data = w.item(t_data, 0x10, dobj, 1)
    i_words = w.item(t_u32, 0x20, words, len(m.words)) if len(m.words) else 0
    idx = {}
    for name, off, cnt, t_el in arrays:
        idx[name] = (w.item(t_el, 0x20, off, cnt) if cnt else 0, off, cnt)
    i_sec_nodes = [w.item(t_c4, 0x20, off, cnt) if cnt else 0 for off, cnt in sec_nodes]
    # --- shape (0x90)
    b = w.b
    struct.pack_into("<HBBB", b, shape + 0x20, m.flags, 9, m.keybits, m.dispatch)
    b[shape + 0x28:shape + 0x2C] = m.radius
    U64.pack_into(b, shape + 0x30, m.user)
    U32.pack_into(b, shape + 0x40, m.codec_info)
    w.patch(p_ref, shape + 0x50, i_data)
    if i_words:
        w.patch(arrt("hkUint32"), shape + 0x58, i_words)
    U32.pack_into(b, shape + 0x68, m.nbits)
    # --- data object (0x100): meshTree at +0x20, simdTree at +0xC0, connectivity (empty) at +0xD0
    mt = dobj + 0x20
    b[mt + 0x10:mt + 0x30] = m.dom
    struct.pack_into("<IIIB", b, mt + 0x30, m.npk, m.bpk, m.maxkey, m.flat)
    slots = {"tree5": (mt, "hkcdStaticTree::Codec3Axis5"), "sections": (mt + 0x40, "hkcdStaticMeshTreeBase::Section"),
             "prims": (mt + 0x50, "hkcdStaticMeshTreeBase::Primitive"), "svi": (mt + 0x60, "hkUint16"),
             "packed": (mt + 0x70, "hkUint32"), "shared": (mt + 0x80, "hkUint64"),
             "runs": (mt + 0x90, "hknpCompressedMeshShapeTreeDataRun"), "simd": (dobj + 0xC0, "hkcdSimdTree::Node")}
    for name, (slot, el) in slots.items():
        if idx[name][0]:
            w.patch(arrt(el), slot, idx[name][0])
    # --- sections (96 bytes)
    so = idx["sections"][1]
    for i, s in enumerate(m.sections):
        o = so + 96 * i
        if i_sec_nodes[i]:
            w.patch(arrt("hkcdStaticTree::Codec3Axis4"), o, i_sec_nodes[i])
        b[o + 0x10:o + 0x30] = s.dom
        b[o + 0x30:o + 0x48] = s.codec
        struct.pack_into("<4IBBH", b, o + 0x48, s.fp, s.so << 8 | s.shlow, s.po << 8 | s.npr, s.ro << 8 | s.nru,
                         s.npv, s.nsh, s.leaf)
        b[o + 0x5C:o + 0x60] = s.tail
    ptch = [(t, sorted(v)) for t, v in sorted(w.ptch.items())]
    return ref.encode(bytes(w.b), w.items, ptch)


# ====================================================================================== static tree (section BVH)
def _codec_encode(pmin, pmax, cmin, cmax, margin):
    """Codec3Axis byte per axis + the decoded child box (float64), decoded box contains [cmin-margin, cmax+margin]"""
    s = (pmax - pmin) / CODEC_DIV
    xyz, dmin, dmax = [], np.empty(3), np.empty(3)
    for k in range(3):
        a = 0
        for v in range(15, -1, -1):
            if pmin[k] + v * v * s[k] <= cmin[k] - margin:
                a = v
                break
        bb = 0
        for v in range(15, -1, -1):
            if pmax[k] - v * v * s[k] >= cmax[k] + margin:
                bb = v
                break
        xyz.append(a << 4 | bb)
        dmin[k] = pmin[k] + a * a * s[k]
        dmax[k] = pmax[k] - bb * bb * s[k]
    return xyz, dmin, dmax


def _codec_decode(pmin, pmax, xyz):
    s = (pmax - pmin) / CODEC_DIV
    x = np.array(xyz)
    return pmin + (x >> 4) ** 2 * s, pmax - (x & 15) ** 2 * s


def build_tree5(boxes, dmin, dmax, margin=1e-3):
    """hkcdStaticTree (Codec3Axis5) over section boxes (N,2,3): (bytes, leaf node index per section)"""
    nodes = []
    leaf_of = [0] * len(boxes)

    def rec(ids, pmin, pmax):
        bmin = boxes[ids, 0].min(0)
        bmax = boxes[ids, 1].max(0)
        i = len(nodes)
        nodes.append(None)
        if not nodes[:-1]:                     # root: the domain itself (TLOU2 roots are xyz = 0)
            xyz, nmin, nmax = [0, 0, 0], pmin, pmax
        else:
            xyz, nmin, nmax = _codec_encode(pmin, pmax, bmin, bmax, margin)
        if len(ids) == 1:
            nodes[i] = bytes(xyz) + struct.pack(">H", ids[0])
            leaf_of[ids[0]] = i
            return
        c = (boxes[ids, 0] + boxes[ids, 1]) / 2
        ax = int(np.argmax(c.max(0) - c.min(0)))
        order = ids[np.argsort(c[:, ax], kind="stable")]
        h = len(order) // 2
        rec(order[:h], nmin, nmax)
        right = len(nodes)
        rec(order[h:], nmin, nmax)
        k = (right - i) // 2
        assert right - i == 2 * k and k < 0x8000
        nodes[i] = bytes(xyz) + struct.pack(">H", 0x8000 | k)
    rec(np.arange(len(boxes)), dmin, dmax)
    return b"".join(n[:3] + bytes([n[3], n[4]]) for n in nodes), leaf_of


def walk_tree5(raw, dmin, dmax):
    """[(section index, node index, decoded min, decoded max)] of a Codec3Axis5 tree"""
    out = []

    def rec(i, pmin, pmax):
        x = raw[5 * i:5 * i + 5]
        nmin, nmax = _codec_decode(pmin, pmax, list(x[:3]))
        data = (x[3] & 0x7F) << 8 | x[4]
        if x[3] & 0x80:
            rec(i + 1, nmin, nmax)
            rec(i + 2 * data, nmin, nmax)
        else:
            out.append((data, i, nmin, nmax))
    rec(0, dmin, dmax)
    return out


# ============================================================================================ simd tree (4-wide)
def build_simd(boxes, keys, pad=1e-4):
    """hkcdSimdTree in the TLOU2 encoding over primitive boxes (N,2,3) / keys: node 0 empty, root 1"""
    EMPTY = (np.full(4, FLT_MAX, np.float32), np.full(4, -FLT_MAX, np.float32))
    nodes = [None, None]

    def split4(ids):
        c = (boxes[ids, 0] + boxes[ids, 1]) / 2
        if len(ids) <= 4:
            return [ids[i:i + 1] for i in range(len(ids))]
        groups = [ids]
        while len(groups) < 4:
            groups.sort(key=len)
            g = groups.pop()
            cg = (boxes[g, 0] + boxes[g, 1]) / 2
            ax = int(np.argmax(cg.max(0) - cg.min(0)))
            o = g[np.argsort(cg[:, ax], kind="stable")]
            h = len(o) // 2
            groups += [o[:h], o[h:]]
        return groups

    queue = [(1, np.arange(len(boxes)))]
    while queue:
        ni, ids = queue.pop(0)
        groups = split4(ids)
        f = np.zeros((6, 4), np.float32)
        f[0::2], f[1::2] = EMPTY[0], EMPTY[1]
        data = [0, 0, 0, 0]
        for j, g in enumerate(groups):
            lo = boxes[g, 0].min(0) - pad
            hi = boxes[g, 1].max(0) + pad
            f[0::2, j] = np.nextafter(lo.astype(np.float32), np.float32(-np.inf))
            f[1::2, j] = np.nextafter(hi.astype(np.float32), np.float32(np.inf))
            if len(g) == 1:
                data[j] = int(keys[g[0]]) << 1 | 1
            else:
                child = len(nodes)
                nodes.append(None)
                data[j] = child << 1
                queue.append((child, g))
        nodes[ni] = f.tobytes() + struct.pack("<4I", *data)
    e = np.zeros((6, 4), np.float32)
    e[0::2], e[1::2] = EMPTY[0], EMPTY[1]
    nodes[0] = e.tobytes() + bytes(16)
    return b"".join(nodes)


def walk_simd(raw):
    """[(key, lo, hi)] leaves of a TLOU2-encoded simd tree (also checks every node is reached once)"""
    n = len(raw) // 112
    seen = [0] * n
    out = []
    stack = [1] if n > 1 else []
    while stack:
        i = stack.pop()
        seen[i] += 1
        f = np.frombuffer(raw, np.float32, 24, 112 * i).reshape(6, 4)
        data = struct.unpack_from("<4I", raw, 112 * i + 96)
        for j in range(4):
            if f[0, j] > f[1, j]:
                continue
            if data[j] & 1:
                out.append((data[j] >> 1, f[0::2, j].astype(np.float64), f[1::2, j].astype(np.float64)))
            else:
                stack.append(data[j] >> 1)
    return out, seen


# ===================================================================================================== splitting
def sub_mesh(m, ids, requant=True):
    """a new Mesh made of sections `ids` of m (vertex data copied; trees, keys, bit fields rebuilt)"""
    n = Mesh()
    n.flags, n.dispatch, n.radius, n.user, n.codec_info, n.flat = m.flags, m.dispatch, m.radius, m.user, m.codec_info, m.flat
    prims = np.frombuffer(m.prims, np.uint8).reshape(-1, 4)
    runs = np.frombuffer(m.runs, np.uint8).reshape(-1, 4)
    sv_all = shared_positions(m)
    # shared vertices used by these sections, in first-use order
    used = []
    for i in ids:
        s = m.sections[i]
        used.extend(int(x) for x in m.svi[s.so:s.so + s.nsh])
    uniq = list(dict.fromkeys(used))
    remap = {g: k for k, g in enumerate(uniq)}
    pos = sv_all[uniq] if uniq else np.zeros((0, 3))
    # domain = bounds of everything in the piece (section boxes cover packed + shared vertices)
    sb = np.array([np.frombuffer(m.sections[i].dom, np.float32).reshape(2, 4)[:, :3] for i in ids]).astype(np.float64)
    dmin, dmax = sb[:, 0].min(0), sb[:, 1].max(0)
    if requant and len(pos):
        dmin = np.minimum(dmin, pos.min(0))
        dmax = np.maximum(dmax, pos.max(0))
    dom32 = np.zeros(8, np.float32)
    dom32[0:3], dom32[4:7] = dmin, dmax
    n.dom = dom32.tobytes()
    dmin, dmax = n.domain()
    if requant and len(pos):
        ext = np.where(dmax > dmin, dmax - dmin, 1.0)
        qq = np.rint((pos - dmin) / ext * np.array([0x1FFFFF, 0x1FFFFF, 0x3FFFFF])).astype(np.int64)
        qq = np.clip(qq, 0, [0x1FFFFF, 0x1FFFFF, 0x3FFFFF])
        n.shared = (qq[:, 0] | qq[:, 1] << 21 | qq[:, 2] << 42).astype(np.uint64)
    else:
        n.shared = m.shared[uniq].copy() if uniq else np.zeros(0, np.uint64)
    svi, packed, pr, rn = [], [], [], []
    for k, i in enumerate(ids):
        s = m.sections[i]
        t = Section(nodes=s.nodes, dom=s.dom, codec=s.codec, shlow=s.shlow, npr=s.npr, nru=s.nru, npv=s.npv,
                    nsh=s.nsh, tail=s.tail, leaf=0)
        t.fp, t.so, t.po, t.ro = len(packed), len(svi), len(pr), len(rn)
        packed.extend(m.packed[s.fp:s.fp + s.npv])
        svi.extend(remap[int(x)] for x in m.svi[s.so:s.so + s.nsh])
        pr.extend(prims[s.po:s.po + s.npr])
        rn.extend(runs[s.ro:s.ro + s.nru])
        n.sections.append(t)
    n.packed = np.array(packed, np.uint32)
    n.svi = np.array(svi, np.uint16)
    n.prims = np.array(pr, np.uint8).tobytes()
    n.runs = np.array(rn, np.uint8).tobytes()
    # keys, bit fields
    nsec = len(ids)
    n.bpk = 8 + max(1, (nsec - 1).bit_length())
    n.keybits = n.bpk
    keys_old, keys_new = [], []
    for k, i in enumerate(ids):
        s = m.sections[i]
        for p in range(s.npr):
            a, b, c, d = prims[s.po + p]
            if max(a, b, c, d) >= s.npv + s.nsh:              # ND filler primitive: no key (see triangles())
                continue
            for t in ((0, 1) if c != d else (0,)):
                keys_old.append(i << 8 | p << 1 | t)
                keys_new.append(k << 8 | p << 1 | t)
    keys_old, keys_new = np.array(keys_old, np.int64), np.array(keys_new, np.int64)
    n.npk = len(keys_new)
    n.maxkey = int(keys_new.max())
    n.nbits = n.maxkey + 1
    bits_old = np.unpackbits(m.words.astype("<u4").view(np.uint8), bitorder="little")
    bits = np.zeros((n.nbits + 31) // 32 * 32, np.uint8)
    ok = keys_old < len(bits_old)
    bits[keys_new[ok]] = bits_old[keys_old[ok]]
    n.words = np.packbits(bits, bitorder="little").view("<u4").astype(np.uint32)
    n._keymap = (keys_old, keys_new)
    # trees
    boxes = sb.copy()
    tree, leaf_of = build_tree5(boxes, dmin, dmax)
    n.tree5 = tree
    for k, t in enumerate(n.sections):
        t.leaf = leaf_of[k]
    pb, pk = prim_boxes(n)
    n.simd = build_simd(pb, pk)
    return n


def encoded_size(m, ref):
    return len(encode_t2(m, ref))


def split_mesh(m, ref, budget=BUDGET):
    """[Mesh] pieces of m, each encoding to <= budget bytes (spatial median splits over section centres)"""
    centres = np.array([np.frombuffer(s.dom, np.float32).reshape(2, 4)[:, :3].mean(0) for s in m.sections])

    def rec(ids):
        piece = sub_mesh(m, ids)
        size = encoded_size(piece, ref)
        if size <= budget or len(ids) == 1:
            if size > budget:
                raise ValueError("one section encodes to %d bytes > budget %d" % (size, budget))
            return [(ids, piece, size)]
        c = centres[ids]
        ax = int(np.argmax(c.max(0) - c.min(0)))
        o = ids[np.argsort(c[:, ax], kind="stable")]
        h = len(o) // 2
        return rec(o[:h]) + rec(o[h:])
    return rec(np.arange(len(m.sections)))


def rekey_blob(blob, nbits_old, keymap, nbits_new):
    """ND's 3-bit-per-shape-key field (payload +0x40, materialTable of the shape) for the new key numbering"""
    old = np.unpackbits(np.frombuffer(blob, np.uint8), bitorder="little")[:nbits_old]
    new = np.zeros((nbits_new + 7) // 8 * 8, np.uint8)
    ko, kn = keymap
    for b in range(3):
        ok = 3 * ko + b < len(old)
        new[3 * kn[ok] + b] = old[3 * ko[ok] + b]
    return np.packbits(new, bitorder="little").tobytes()


# ========================================================================================= TLOU2 type reference
def reference_tag():
    """a real TLOU2 COLLISION_DATA_HAVOK_BG tagfile (for its TYPE section), never shipped by us"""
    import ndpak
    cands = []
    if os.environ.get("T2R_HK_TYPES"):
        cands.append(os.environ["T2R_HK_TYPES"])
    cands += sorted(glob.glob(os.path.join(MAIN, "re", "part1", "x", "t2ref", "*-phys.pak")))
    cache = os.path.join(MAIN, "re", "part1", "x", "t2ref", "_havok_bg_ref.tag")
    if os.path.exists(cache):
        return havok_tag.Tag.parse(open(cache, "rb").read())
    for c in cands:
        try:
            p = ndpak.Pak(c)
        except Exception:
            continue
        for name, typ, pi, io in p.items:
            if typ == "COLLISION_DATA_HAVOK_BG":
                t = p.ptr(io + 48 + 16)
                return havok_tag.Tag.parse(p.d[t:t + p.u32(io + 48 + 12)])
    # last resort: pull one -phys pak out of the TLOU2 install (read only)
    import p1_archive
    game = os.environ.get("T2R_TLOU2_DIR", r"C:\Games\The Last of Us Part II Remastered")
    for arc in sorted(glob.glob(os.path.join(game, "build", "pc", "main", "world-*.psarc"))):
        a = p1_archive.Psarc(arc)
        for nm in a.ent:
            if nm.endswith("-phys.pak"):
                data = a.get(nm)
                if len(data) < 20000:
                    continue
                os.makedirs(os.path.dirname(cache), exist_ok=True)
                tmp = cache + ".pak"
                open(tmp, "wb").write(data)
                p = ndpak.Pak(tmp)
                for name, typ, pi, io in p.items:
                    if typ == "COLLISION_DATA_HAVOK_BG":
                        t = p.ptr(io + 48 + 16)
                        raw = p.d[t:t + p.u32(io + 48 + 12)]
                        open(cache, "wb").write(raw)
                        os.remove(tmp)
                        return havok_tag.Tag.parse(raw)
    raise SystemExit("no TLOU2 -phys pak found for the Havok type table (set T2R_HK_TYPES)")


# ============================================================================================== TLOU2 -phys pak
PAD = 48
MARK = struct.pack("<I", 0x12345)
RUNTIME_BITS = 16      # bytes per shape key of the per-item runtime block (+0x48): TLOU2 uses 8..13 per pak; 16 is a safe upper bound


def _item_header(name_off, type_off, size):
    return struct.pack("<QQI", name_off, type_off, size) + MARK * 7


def build_phys_pak(pieces):
    """TLOU2 0xA79 -phys pak from [(kind, tag bytes, records bytes, nbits, blob bytes, keybits)].
    Layout as ND's: per page {header, item table, tagfile(s) then their COLLISION_DATA_HAVOK_BG item(s), string pool},
    the last data page also holds PAK_LOGIN_TABLE and VRAM_DESC_TABLE; a final flag-1 (zero) page holds each item's
    runtime block (+0x48) and the 0x100-byte runtime item ND lists in the login table."""
    LIMIT = 0xF8000
    pages = []                    # each: {"items": [(type name, offset in body, size)], "body": bytearray, "flag": 0}
    fix = []                      # (src page, dst page, slot offset in body, value offset in body) - shifted later
    cur = None
    entries = []                  # (page, item body offset) for the login table

    def new_page(flag=0):
        p = {"items": [], "body": bytearray(), "flag": flag}
        pages.append(p)
        return p

    def align(buf, a=16):
        while len(buf) % a:
            buf.append(0)
    rt_sizes = []
    for kind, tag, recs, nbits, blob, keybits in pieces:
        nrec = len(recs) // 8
        payload_size = 0x60 + 8 * nrec
        payload_size = (payload_size + 15) // 16 * 16 + (len(blob) + 3) // 4 * 4
        need = len(tag) + PAD + payload_size + 64
        if cur is None or len(cur["body"]) + need > LIMIT:
            cur = new_page()
            cur["body"] += bytes(32)                              # room so the first object is not at the table end
        pi = len(pages) - 1
        b = cur["body"]
        align(b)
        tag_off = len(b)
        b += tag
        align(b)
        h = len(b)
        b += bytes(PAD + payload_size)
        cur["items"].append(("COLLISION_DATA_HAVOK_BG", h, payload_size))
        P = h + PAD
        struct.pack_into("<IIII", b, P, 0xE, kind, 0, len(tag))
        struct.pack_into("<II", b, P + 56, nbits, nrec)
        b[P + 0x60:P + 0x60 + len(recs)] = recs
        blob_off = P + (0x60 + 8 * nrec + 15) // 16 * 16
        b[blob_off:blob_off + len(blob)] = blob
        fix.append((pi, pi, P + 16, tag_off))
        fix.append((pi, pi, P + 64, blob_off))
        fix.append((pi, "rt", P + 72, len(rt_sizes)))
        fix.append((pi, pi, P + 80, P + 0x60))
        rt_sizes.append(0x10 + ((1 << keybits) * RUNTIME_BITS + 7) // 8)
        entries.append((pi, h))
    # login + vram tables in the last data page
    b = cur["body"]
    pi = len(pages) - 1
    align(b, 8)
    login_h = len(b)
    n_login = len(entries) + 1
    b += bytes(PAD + 8 + 8 * n_login)
    cur["items"].append(("PAK_LOGIN_TABLE", login_h, 8 + 8 * n_login))
    align(b, 8)
    vram_h = len(b)
    b += bytes(PAD + 8)
    cur["items"].append(("VRAM_DESC_TABLE", vram_h, 8))
    # runtime page(s) (flag 1): per-item blocks, then the runtime item (header + 0xd0 bytes, 4 pointer slots)
    rt_pages = []
    rpage = None
    rt_loc = []
    for size in rt_sizes:
        if rpage is None or len(rpage["body"]) + size > LIMIT:
            rpage = new_page(flag=1)
            rpage["body"] += bytes(16)
            rt_pages.append(len(pages) - 1)
        align(rpage["body"])
        rt_loc.append((len(pages) - 1, len(rpage["body"])))
        rpage["body"] += bytes(size)
    align(rpage["body"])
    tail_h = len(rpage["body"])
    rpage["body"] += bytes(0x100)
    tail_pi = len(pages) - 1
    for k in (0x38, 0x48, 0x50, 0x58):
        fix.append((tail_pi, tail_pi, tail_h + k, 0))
    entries.append((tail_pi, tail_h))
    # ---- strings, shifts, pointers
    shifts = []
    for p in pages:
        if p["flag"] == 0:
            pool = bytearray(b"\0")
            offs = {"": 0}
            for t, _, _ in p["items"]:
                if t not in offs:
                    offs[t] = len(pool)
                    pool += t.encode() + b"\0"
            align(p["body"])
            p["pool"] = len(p["body"])
            p["offs"] = offs
            p["body"] += pool
        shifts.append((20 + 16 * len(p["items"]) + 15) // 16 * 16)
    for (spi, dpi, slot, val) in fix:
        if dpi == "rt":
            dpi, val = rt_loc[val]
        U64.pack_into(pages[spi]["body"], slot, val + shifts[dpi])
    fix = [(spi, rt_loc[val][0] if dpi == "rt" else dpi, slot) for spi, dpi, slot, val in fix]
    for pi, p in enumerate(pages):
        for t, h, size in p["items"]:
            p["body"][h:h + PAD] = _item_header(p["pool"] + shifts[pi], p["pool"] + p["offs"][t] + shifts[pi], size)
    lp = len(pages) - 1 - len(rt_pages)
    lb = pages[lp]["body"]
    struct.pack_into("<II", lb, login_h + PAD, n_login, 0x12345)
    for i, (epi, eh) in enumerate(entries):
        struct.pack_into("<II", lb, login_h + PAD + 8 + 8 * i, epi, eh + shifts[epi])
    # ---- assemble
    out_pages = []
    for pi, p in enumerate(pages):
        body = p["body"]
        align(body)
        tbl = bytearray()
        for t, h, size in p["items"]:
            tbl += struct.pack("<IIII", p["pool"] + shifts[pi], 0, h + shifts[pi], 0x12345)
        size = shifts[pi] + len(body)
        hdr = struct.pack("<QIIHH", 0xDEADBEEFDEADBEEF, 0, size, p["flag"], len(p["items"]))
        out_pages.append(hdr + bytes(tbl) + bytes(shifts[pi] - 20 - len(tbl)) + bytes(body))
    npg = len(out_pages)
    pt, ft = 0x2C, 0x2C + 12 * npg
    from p1_convert import fix_data_off
    fdo = fix_data_off(ft)
    uniq = sorted(set((s, d, o + shifts[s]) for s, d, o in fix))
    first = fdo + 8 * len(uniq) + 8
    first = (first + 15) // 16 * 16
    head = bytearray(first)
    struct.pack_into("<8I", head, 0, 0xA79, first, lp, login_h + shifts[lp], npg, pt, 8, ft)
    struct.pack_into("<III", head, 0x20, 0, lp, vram_h + shifts[lp])   # (+0x24 = the VRAM table page: it sits on the login page here)
    pos = first
    for i, pg in enumerate(out_pages):
        struct.pack_into("<III", head, pt + 12 * i, pos, len(pg), pages[i]["flag"])
        pos += len(pg)
    struct.pack_into("<III", head, ft, 0, fdo, len(uniq))
    for i, (s, d, o) in enumerate(uniq):
        struct.pack_into("<HHI", head, fdo + 8 * i, s, d, o)
    return bytes(head) + b"".join(out_pages)


def t2_collision_items(path_or_bytes):
    """[{kind, nbits, records, blob, tag (Tag), raw}] of a TLOU2 -phys pak"""
    import ndpak
    if isinstance(path_or_bytes, (bytes, bytearray)):
        tmp = os.path.join(os.environ.get("TEMP", "/tmp"), "_t2r_hk_%d.pak" % os.getpid())
        open(tmp, "wb").write(path_or_bytes)
        p = ndpak.Pak(tmp)
        os.remove(tmp)
    else:
        p = ndpak.Pak(path_or_bytes)
    out = []
    for name, typ, pi, io in p.items:
        if typ != "COLLISION_DATA_HAVOK_BG":
            continue
        b = io + 48
        ver, kind, _, tsz = struct.unpack_from("<4I", p.d, b)
        nbits, nrec = struct.unpack_from("<II", p.d, b + 56)
        t = p.ptr(b + 16)
        raw = p.d[t:t + tsz]
        rp, bp = p.ptr(b + 80), p.ptr(b + 64)
        out.append({"version": ver, "kind": kind, "nbits": nbits, "records": p.d[rp:rp + 8 * nrec],
                    "blob": p.d[bp:bp + (nbits + 7) // 8], "raw": raw, "tag": havok_tag.Tag.parse(raw),
                    "runtime": p.ptr(b + 72), "tag_align": t % 16, "page": pi, "pak": p})
    return out


# ===================================================================================================== convert
def remap_proxy_records(records, kind):
    """The stair proxy ramps of Part I (collision items of kind 0x103 / 3: smooth 2-triangle ramps, the invisible planes) are hit by the
    0x207 ray chain only; the player chain (0x1b07) and 'all' pass through them, so the player's controller collides with a ramp it cannot stand on (blocked on the
    lowest ~5 steps).  Part I's material records have bytes 4..5 = 00 00 (mostly 01 02 in TLOU2) and the stair proxy record has byte 2 = 01 where the stock stair
    proxy (flo-mall item 1, 1188 triangles) is '0112002401024000'.  Only the proxy-layer items are touched (kind 259 / 3), per 8-byte record: the stair proxy
    '..12 01 24..' gets byte 2 = 00, every record gets byte 4 |= 01 and byte 5 = 02 when it is 00 (stock: 01 / 81 / 41 + 02 on all proxy-layer records).
    T2R_P1_MAT_REMAP=0 leaves the records as they are (default: on)."""
    if os.environ.get("T2R_P1_MAT_REMAP", "1") == "0" or kind not in (259, 3):
        return records
    out = bytearray(records)
    for o in range(0, len(out) - 7, 8):
        if out[o + 1] == 0x12 and out[o + 3] == 0x24 and out[o + 2] == 0x01:
            out[o + 2] = 0x00
        out[o + 4] |= 0x01
        if out[o + 5] == 0:
            out[o + 5] = 0x02
    return bytes(out)


def convert(p1_data, budget=BUDGET, ref=None, report=None):
    """Part I -phys pak bytes -> TLOU2 -phys pak bytes (None if the pak has no collision)"""
    ref = ref or reference_tag()
    pieces = []
    rep = report if report is not None else {}
    rep.setdefault("items", [])
    for it in p1_collision_items(p1_data):
        m = p1_mesh(it["data"])
        info = {"kind": hex(it["kind"]), "sections": len(m.sections), "keys": m.npk, "pieces": []}
        if encoded_size(m, ref) <= budget:
            parts = [(np.arange(len(m.sections)), m, None)]
        else:
            parts = split_mesh(m, ref, budget)
        for ids, piece, _ in parts:
            tag = encode_t2(piece, ref)
            nb = 3 << piece.keybits
            if piece is m:
                blob = bytes(it["blob"][:(min(it["nbits"], nb) + 7) // 8]) + bytes(max(0, (nb + 7) // 8 - len(it["blob"])))
                if it["nbits"] != nb:
                    keys = triangles(m)[0]
                    blob = rekey_blob(it["blob"], it["nbits"], (keys, keys), nb)
            else:
                blob = rekey_blob(it["blob"], it["nbits"], piece._keymap, nb)
            pieces.append((it["kind"], tag, remap_proxy_records(it["records"], it["kind"]), nb, blob, piece.keybits))
            info["pieces"].append({"sections": len(piece.sections), "keys": piece.npk, "tag bytes": len(tag)})
        rep["items"].append(info)
    if not pieces:
        return None
    return build_phys_pak(pieces)


# ===================================================================================================== checks
def check(p1_data, t2_path_or_bytes, tol=2e-4, verbose=True):
    """converted pak vs source: same triangles (as sets, positions within tol), same tags, trees valid, keys valid"""
    src = []
    for it in p1_collision_items(p1_data):
        m = p1_mesh(it["data"])
        k, t, g = triangles(m)
        src.append((it, m, k, t, g))
    dst = t2_collision_items(t2_path_or_bytes)
    ok = True
    S_t = np.concatenate([t for _, _, _, t, _ in src]) if src else np.zeros((0, 3, 3))
    S_g = np.concatenate([g for *_, g in src]) if src else np.zeros(0)
    D_t, D_g = [], []
    tree_bad = simd_bad = 0
    for d in dst:
        T = d["tag"]
        if T.encode() != d["raw"]:
            print("  re-encode of a converted tagfile differs")
            ok = False
        m = t2_mesh(T)
        k, t, g = triangles(m)
        D_t.append(t)
        D_g.append(g)
        bad = validate_mesh(m)
        if bad:
            print("  structure:", bad)
            tree_bad += sum(v for kk, v in bad.items() if "tree" in kk or "leaf" in kk)
            simd_bad += sum(v for kk, v in bad.items() if "simd" in kk)
            ok = False
        if m.npk != len(k) or m.maxkey != int(k.max()) or m.nbits != m.maxkey + 1 or m.bpk != m.keybits:
            print("  key header mismatch", m.npk, len(k), m.maxkey, int(k.max()), m.nbits)
            ok = False
        if d["nbits"] != 3 << m.keybits or (d["records"] and len(d["records"]) % 8):
            ok = False
        if m.codec_info == 1 and len(d["records"]) // 8 <= int(g.max() >> 6):
            print("  shape tag beyond the record table")
            ok = False
        if d["tag_align"]:
            print("  tagfile not 16-aligned")
            ok = False
        if len(d["raw"]) > BUDGET + 0x10000:
            print("  tagfile larger than budget")
            ok = False
    D_t = np.concatenate(D_t) if D_t else np.zeros((0, 3, 3))
    D_g = np.concatenate(D_g) if D_g else np.zeros(0)
    ok &= tree_bad == 0 and simd_bad == 0
    # match triangles as sets: sort by rounded centroid
    def canon(t):
        return np.round(t.mean(1) / tol).astype(np.int64)
    tag_eq = None
    if len(S_t) != len(D_t):
        print("  triangle count", len(S_t), "->", len(D_t))
        ok = False
        err = None
    else:
        a = np.lexsort(canon(S_t).T[::-1])
        b = np.lexsort(canon(D_t).T[::-1])
        err = np.abs(S_t[a] - D_t[b]).max() if len(S_t) else 0.0
        tag_eq = bool((S_g[a] == D_g[b]).all())
        if err > tol or not tag_eq:
            # centroid ties can misorder: fall back to nearest matching per triangle
            from scipy.spatial import cKDTree  # noqa
            tr = cKDTree(D_t.reshape(len(D_t), 9))
            dist, idx = tr.query(S_t.reshape(len(S_t), 9), k=min(4, len(D_t)))
            idx, dist = idx.reshape(len(S_t), -1), dist.reshape(len(S_t), -1)
            err = float(np.abs(S_t - D_t[idx[:, 0]]).max())
            # duplicate triangles with different tags (hun-checkpoint-maze) match either copy: any coincident neighbour with the same tag
            tag_eq = bool(((S_g[:, None] == D_g[idx]) & (dist <= tol * 3)).any(1).all())
        ok &= err <= tol and tag_eq
    lo_s, hi_s = S_t.reshape(-1, 3).min(0), S_t.reshape(-1, 3).max(0)
    lo_d, hi_d = D_t.reshape(-1, 3).min(0), D_t.reshape(-1, 3).max(0)
    if verbose:
        print("source: %d collision items, %d triangles, bounds %s .. %s" % (len(src), len(S_t), np.round(lo_s, 3), np.round(hi_s, 3)))
        print("TLOU2 : %d collision items, %d triangles, bounds %s .. %s" % (len(dst), len(D_t), np.round(lo_d, 3), np.round(hi_d, 3)))
        print("max vertex error %.2e m, shape tags equal %s, section-tree errors %d, simd-tree errors %d" % (
            err if err is not None else -1, tag_eq if err is not None else None, tree_bad, simd_bad))
        print("CHECK", "OK" if ok else "FAILED")
    return ok


def validate_mesh(m, tol=1e-4):
    """structural checks of a Mesh (either game): {name: number of violations}"""
    bad = {}
    prims = np.frombuffer(m.prims, np.uint8).reshape(-1, 4)
    runs = np.frombuffer(m.runs, np.uint8).reshape(-1, 4)
    sv = shared_positions(m)
    for s in m.sections:
        pp = prims[s.po:s.po + s.npr]
        past = pp.max(1) >= s.npv + s.nsh if len(pp) else np.zeros(0, bool)
        filler = (pp[:, 0] == pp[:, 2]) & (pp[:, 1] == pp[:, 3]) if len(pp) else past     # ND filler a b a b: allowed (see triangles())
        if (past & ~filler).any():
            bad["prim index past section vertices"] = bad.get("prim index past section vertices", 0) + 1
        cover = np.zeros(s.npr, int)
        for r in runs[s.ro:s.ro + s.nru]:
            cover[r[2]:r[2] + r[3]] += 1
        if (cover != 1).any():
            bad["data runs do not cover each prim once"] = bad.get("data runs do not cover each prim once", 0) + 1
        V = section_vertices(m, s, sv)
        b = np.frombuffer(s.dom, np.float32).reshape(2, 4)[:, :3].astype(np.float64)
        if len(V) and ((V < b[0] - tol).any() or (V > b[1] + tol).any()):
            bad["vertex outside section box"] = bad.get("vertex outside section box", 0) + 1
    dmin, dmax = m.domain()
    leaves = walk_tree5(m.tree5, dmin, dmax)
    if sorted(x[0] for x in leaves) != list(range(len(m.sections))):
        bad["section tree leaves != sections"] = 1
    for si, node, nmin, nmax in leaves:
        s = m.sections[si]
        b = np.frombuffer(s.dom, np.float32).reshape(2, 4)[:, :3].astype(np.float64)
        if node != s.leaf:
            bad["leafIndex"] = bad.get("leafIndex", 0) + 1
        if (b[0] < nmin - tol).any() or (b[1] > nmax + tol).any():
            bad["section box outside tree node"] = bad.get("section box outside tree node", 0) + 1
    sl, seen = walk_simd(m.simd)
    pb, pk = prim_boxes(m)
    box = {int(a): b for a, b in zip(pk, pb)}
    for key, lo, hi in sl:
        bb = box.get(key)
        if bb is None:
            bad["simd leaf key unknown"] = bad.get("simd leaf key unknown", 0) + 1
        elif (bb[0] < lo - tol).any() or (bb[1] > hi + tol).any():
            bad["prim outside simd box"] = bad.get("prim outside simd box", 0) + 1
    if sorted(k for k, _, _ in sl) != sorted(int(x) for x in pk):
        bad["simd leaves != prims"] = 1
    if any(x != 1 for x in seen[1:]):
        bad["simd nodes not reached exactly once"] = 1
    k = triangles(m)[0]
    if m.npk != len(k) or m.maxkey != int(k.max()) or m.nbits != m.maxkey + 1:
        bad["key header"] = 1
    return bad


def roundtrip(path, verbose=True):
    """decode every collision tagfile of a TLOU2 pak to the Mesh model and re-encode it: byte-identical?"""
    ok = True
    for d in t2_collision_items(path):
        T = d["tag"]
        same_tag = T.encode() == d["raw"]
        m = t2_mesh(T)
        again = encode_t2(m, T)
        same_mesh = again == d["raw"]
        ok &= same_tag and same_mesh
        if verbose:
            print("  item kind %#x: %d sections, %d triangles, %d bytes: tagfile re-encode %s, mesh re-encode %s" % (
                d["kind"], len(m.sections), m.npk, len(d["raw"]), "identical" if same_tag else "DIFFERS",
                "identical" if same_mesh else "DIFFERS"))
    return ok


def info(path):
    data = open(path, "rb").read()
    ver = U32.unpack_from(data, 0)[0]
    if ver in (0xA7D,):
        for it in p1_collision_items(data):
            m = p1_mesh(it["data"])
            k, t, g = triangles(m)
            v = t.reshape(-1, 3)
            print("Part I %s kind %#x: %d sections, %d prims, %d triangles, %d packed + %d shared verts, records %d, "
                  "keybits %d, bounds %s .. %s" % (it["sdk"], it["kind"], len(m.sections), len(m.prims) // 4, len(t),
                                                   len(m.packed), len(m.shared), len(it["records"]) // 8, m.keybits,
                                                   np.round(v.min(0), 2), np.round(v.max(0), 2)))
    else:
        for d in t2_collision_items(path):
            m = t2_mesh(d["tag"])
            k, t, g = triangles(m)
            v = t.reshape(-1, 3)
            print("TLOU2 kind %#x: %d sections, %d triangles, records %d, keybits %d, tag %d bytes, bounds %s .. %s" % (
                d["kind"], len(m.sections), len(t), len(d["records"]) // 8, m.keybits, len(d["raw"]),
                np.round(v.min(0), 2), np.round(v.max(0), 2)))


def main(argv):
    if len(argv) < 3:
        print(__doc__)
        return 1
    cmd = argv[1]
    opts = {a.split("=")[0]: a.split("=", 1)[1] if "=" in a else True for a in argv[2:] if a.startswith("--")}
    args = [a for a in argv[2:] if not a.startswith("--")]
    budget = int(opts.get("--budget", str(BUDGET)), 0)
    if cmd == "roundtrip":
        ok = True
        for p in args:
            print(p)
            ok &= roundtrip(p)
        print("ROUND TRIP", "OK" if ok else "FAILED")
        return 0 if ok else 1
    if cmd == "convert":
        rep = {}
        out = convert(open(args[0], "rb").read(), budget, report=rep)
        if out is None:
            print(args[0], ": no collision items")
            return 0
        open(args[1], "wb").write(out)
        print(args[0], "->", args[1], len(out), "bytes", rep)
        return 0
    if cmd == "check":
        return 0 if check(open(args[0], "rb").read(), args[1]) else 1
    if cmd == "info":
        for p in args:
            print(p)
            info(p)
        return 0
    if cmd == "preview":
        import havok_preview
        return havok_preview.main(argv)
    print(__doc__)
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
