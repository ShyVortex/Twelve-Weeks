"""Part I (Havok 2020.1) actor collision -> TLOU2 (Havok 2017.1) tagfile, COLLISION_DATA_FOREGROUND items.

Same approach as havok_convert.py (level collision): the geometry and per-body data are decoded from the Part I image and written into a fresh 2017.1
tagfile that keeps the TYPE table, materials and motion properties of a stock TLOU2 actor with the same classes (the template).

Library:  Graph.from_tag(Tag)        item graph of a 2017.1 tagfile: items (type, flags, count, bytes), pointer slots {rel offset: (ptch type, target item)}
          Graph.layout()           -> (DATA bytes, ITEM list, PTCH list); the round trip of a stock tag is byte exact (test_roundtrip)
          translate(p1_tag_bytes, template Tag) -> TLOU2 tag bytes
Layout rules (measured on stock actors): objects (flags 16) at the type alignment, arrays (flags 32) at 16; DATA is padded to 16 at the end.
"""
import os
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "models"))
import havok_tag as H  # noqa: E402
import numpy as np  # noqa: E402

U32 = struct.Struct("<I")


def align(o, a):
    return (o + a - 1) & ~(a - 1)


class Item:
    def __init__(self, ti, fl, cnt, data, slots=None):
        self.ti, self.fl, self.cnt = ti, fl, cnt
        self.data = bytearray(data)
        self.slots = dict(slots or {})       # rel offset -> [ptch type index, target Item or None]
        self.name = None

    def clone(self):
        c = Item(self.ti, self.fl, self.cnt, self.data, {k: [v[0], v[1]] for k, v in self.slots.items()})
        c.name = self.name
        return c


class Graph:
    def __init__(self, tag):
        self.tag = tag
        self.items = []          # ITEM table order (item index = position + 1)
        self.layout_order = []   # offset order (Items)

    @classmethod
    def from_tag(cls, t):
        g = cls(t)
        for ti, fl, off, cnt in t.items[1:]:
            sz = t.resolved(ti, "size")
            it = Item(ti, fl, cnt, t.data[off:off + cnt * sz])
            it.off0 = off
            it.name = t.tname(ti)
            g.items.append(it)
        # pointer slots
        for pti, offs in t.ptch:
            for o in offs:
                for it in g.items:
                    if it.off0 <= o < it.off0 + len(it.data):
                        idx = U32.unpack_from(t.data, o)[0]
                        it.slots[o - it.off0] = [pti, g.items[idx - 1] if idx else None]
                        break
                else:
                    raise ValueError("ptch slot %d outside every item" % o)
        g.layout_order = sorted(g.items, key=lambda i: i.off0)
        return g

    def layout(self):
        pos = 0
        out = bytearray()
        for it in self.layout_order:
            a = 16 if it.fl & 32 else self.tag.resolved(it.ti, "align")
            pos = align(pos, a)
            out += bytes(pos - len(out))
            it.off = pos
            out += it.data
            pos += len(it.data)
        out += bytes(align(len(out), 16) - len(out))
        index = {id(it): k + 1 for k, it in enumerate(self.items)}
        ptch = {}
        for it in self.items:
            for rel, (pti, tgt) in it.slots.items():
                v = index[id(tgt)] if tgt is not None else 0
                U32.pack_into(out, it.off + rel, v)
                if v:
                    ptch.setdefault(pti, []).append(it.off + rel)
        order = [ti for ti, _ in self.tag.ptch if ti in ptch] + sorted(set(ptch) - {ti for ti, _ in self.tag.ptch})
        items = [(0, 0, 0, 0)] + [(it.ti, it.fl, it.off, it.cnt) for it in self.items]
        return bytes(out), items, [(ti, sorted(ptch[ti])) for ti in order]

    def encode(self):
        data, items, ptch = self.layout()
        return self.tag.encode(data, items, ptch)


def test_roundtrip(raw):
    t = H.Tag.parse(raw)
    g = Graph.from_tag(t)
    out = g.encode()
    return out == raw, len(out), len(raw)


class Unsupported(Exception):
    pass


def _vertex_block(verts):
    out = bytearray()
    for i, v in enumerate(verts):
        out += struct.pack("<3fI", v[0], v[1], v[2], 0x3F000000 + i)
    return bytes(out)


# ================================================================================================ generic pieces (constraints etc.)
_BASE_NAMES = ("sizeAndFlags", "refCount", "memSizeAndFlags", "propertyBag", "numNonDirectlySolvedAtoms")
_PTR_PREFIX = ("hkRefPtr", "hkViewPtr", "hkArray", "hkRelArray", "hkRelArrayView", "hkStringPtr", "hkRelPtr", "T*", "hkFreeList")


def flat_members(tag, ti, base=0, pre="", out=None, depth=0):
    """leaves of class ti: {path: (offset, size, is_pointer_like)}. Records with two or more members (and 8+ bytes) are descended into."""
    out = {} if out is None else out
    for n, fl, off, ty in tag.all_members(ti):
        if not pre and n in _BASE_NAMES:
            continue
        sub = (tag.resolved(ty, "sub") or 0)
        kind = sub & 0xF
        size = tag.resolved(ty, "size") or 0
        nm = tag.tname(ty)
        ptr = kind in (K_POINTER_, K_STRING_) or nm.startswith(_PTR_PREFIX) or (kind == 8 and (sub >> 8) == 0) or (nm.startswith("T[N]") and "T*" in nm)
        if kind == 7 and not ptr and size >= 8 and len(tag.all_members(ty)) >= 2 and depth < 8:
            flat_members(tag, ty, base + off, pre + n + ".", out, depth + 1)
        else:
            out[pre + n] = (base + off, size, ptr)
    return out


K_POINTER_, K_STRING_ = 6, 3


def copy_by_name(ptag, p_ti, psrc, ttag, t_ti, tdst, report=None):
    """copy every leaf member that both classes have under the same path and with the same size from the Part I bytes into the TLOU2 bytes
    (the rest of tdst keeps the template values).  Returns (copied paths, TLOU2-only paths, Part I-only paths); pointer-like leaves are never copied."""
    pl, tl = flat_members(ptag, p_ti), flat_members(ttag, t_ti)
    done, tonly = [], []
    for path, (toff, tsz, tptr) in tl.items():
        if tptr:
            continue
        if path in pl and pl[path][1] == tsz and not pl[path][2]:
            poff = pl[path][0]
            tdst[toff:toff + tsz] = psrc[poff:poff + tsz]
            done.append(path)
        else:
            tonly.append(path)
    ponly = [p for p in pl if p not in tl and not pl[p][2]]
    if report is not None:
        cls = ttag.tname(t_ti)
        r = report.setdefault("members", {}).setdefault(cls, {"tlou2 only": set(), "part1 only": set()})
        r["tlou2 only"].update(tonly)
        r["part1 only"].update(ponly)
    return done, tonly, ponly


def children(it):
    return [it.slots[r][1] for r in sorted(it.slots) if it.slots[r][1] is not None]


def index_order(root):
    """ITEM table order as Havok writes it (measured: reproduces all stock actor tags without compressed-mesh shapes): an object's children are
    numbered in slot offset order; then the arrays among them are expanded at once (their children numbered, recursively); the objects go to a
    first-in first-out queue, the object children of the arrays behind the direct object children"""
    seen = {id(root)}
    order = [root]
    q = [root]

    def proc(it):
        new = []
        for c in children(it):
            if id(c) not in seen:
                seen.add(id(c))
                order.append(c)
                new.append(c)
        q.extend(c for c in new if not c.fl & 32)
        for c in new:
            if c.fl & 32:
                proc(c)
    while q:
        proc(q.pop(0))
    return order


def layout_order(root):
    """DATA order: an object is followed by its array children (and theirs); object children are queued, direct ones first"""
    out, seen = [], set()
    queue = [root]
    queued = {id(root)}

    def expand(it):
        direct, arrays = [], []
        for c in children(it):
            if id(c) in seen:
                continue
            if c.fl & 32:
                seen.add(id(c))
                out.append(c)
                arrays.append(c)
            elif id(c) not in queued:
                queued.add(id(c))
                direct.append(c)
        deeper = []
        for a in arrays:                                 # the arrays of an object first, then what hangs off them
            deeper += expand(a)
        return direct + deeper
    while queue:
        it = queue.pop(0)
        seen.add(id(it))
        out.append(it)
        queue.extend(expand(it))
    return out


def graph_from_root(tag, root):
    g = Graph(tag)
    g.items = index_order(root)
    g.layout_order = layout_order(root)
    assert len(g.layout_order) == len(g.items), "unreachable items"
    return g


# ================================================================================================ the translator
SLOT_SCHEMA = {   # class -> {rel offset: ptch type name} for the pointer slots a translated object gets (measured on 3104 stock actors: one schema per class)
    "hknpPhysicsSystemData": {72: "hkArray<tT=hknpConstraintCinfo,tAllocator=hkContainerHeapAllocator>"},
    "hknpConstraintCinfo": {0: "hkRefPtr<tTYPE=hkpConstraintData>"},          # per element, stride 40
    "hkpRagdollConstraintData": {256: "T*<tT=hkpConstraintMotor>", 264: "T*<tT=hkpConstraintMotor>", 272: "T*<tT=hkpConstraintMotor>"},
    "hkpLimitedHingeConstraintData": {200: "T*<tT=hkpConstraintMotor>"},
    "hknpBreakableConstraintData": {32: "hkRefPtr<tTYPE=hkpConstraintData>"},
}
CONSTRAINT_CLASSES = ("hkpRagdollConstraintData", "hkpLimitedHingeConstraintData", "hkpHingeConstraintData", "hknpBreakableConstraintData",
                      "hkpSpringDamperConstraintMotor")
SUPPORTED = {"hknpMaterial", "hknpPhysicsSystemData", "hknpPhysicsSystemData::bodyCinfoWithAttachment", "hknpShapeProperties::Property",
             "hknpMotionProperties", "hknpShapeMassProperties", "hkFloat3", "hknpConvexHull::Face", "hknpConvexShape", "hknpConvexHull::Edge",
             "hkVector4", "hkUint8", "hknpConstraintCinfo", "hknpSphereShape", "hknpCapsuleShape", "hknpCompoundShape", "hkcdSimdTree::Node",
             "hkFreeListArrayElement<tVALUE_TYPE=hknpShapeInstance>", "hknpCompressedMeshShape", "hknpCompressedMeshShapeData", "hkUint32",
             "hkcdCompressedAabbCodecs::Aabb4BytesCodec", "hkcdCompressedAabbCodecs::Aabb5BytesCodec", "hkcdDefaultStaticMeshTree::PrimitiveDataRun",
             "hkcdStaticMeshTree::Primitive", "hkcdStaticMeshTree::Section", "unsigned int", "hkUint16", "hkUint64", "unsigned long long",
             "unsigned short"} | set(CONSTRAINT_CLASSES)


def _fresh(it):
    """clone of a template item without its pointer slots (the stale item indices are zeroed)"""
    c = it.clone()
    for rel in list(c.slots):
        c.data[rel:rel + 4] = bytes(4)
    c.slots = {}
    return c


def _ptr_leaf_map(tag, ti):
    """{offset: (path, delta)} of the pointer-like leaves of a class (a T[N] of pointers has N slots: delta = 8 * i)"""
    out = {}
    for path, (off, size, ptr) in flat_members(tag, ti).items():
        if ptr:
            for d in range(0, max(size, 8), 8):
                out[off + d] = (path, d)
    return out


def translate(p1raw, template_raw, report=None):
    """Part I COLLISION_DATA_FOREGROUND tag bytes (2020.1) -> TLOU2 tag bytes (2017.1), built on the template: a stock TLOU2 tag whose class
    set contains every class of the result (so its TYPE table and the per-class default bytes fit)."""
    rep = report if report is not None else {}
    pt = H.Tag.parse(p1raw)
    pg = Graph.from_tag(pt)
    D = pt.data
    extra = {it.name for it in pg.items} - SUPPORTED
    if extra:
        raise Unsupported("classes " + ", ".join(sorted(extra)))
    t = H.Tag.parse(template_raw)
    g0 = Graph.from_tag(t)
    have = {it.name for it in g0.items}
    pcls = {it.name for it in pg.items}
    need = {n for n in pcls if n in CONSTRAINT_CLASSES}
    if "hknpConvexShape" in pcls:
        need.add("hknpConvexPolytopeShape")
    if "hknpShapeProperties::Property" in pcls:
        need |= {"hkRefCountedProperties", "hknpShapeMassProperties"}
    if "hknpConstraintCinfo" in {it.name for it in pg.items}:
        need.add("hknpConstraintCinfo")
    if "hknpSphereShape" in {it.name for it in pg.items}:
        need.add("hknpSphereShape")
    if "hknpCompressedMeshShape" in {it.name for it in pg.items}:
        need |= {"hknpCompressedMeshShape", "hknpCompressedMeshShapeData", "hkcdStaticTree::Codec3Axis4", "hkcdStaticTree::Codec3Axis5", "hkcdStaticMeshTreeBase::Section",
                 "hkcdStaticMeshTreeBase::Primitive", "hknpCompressedMeshShapeTreeDataRun", "hkcdSimdTree::Node", "hkUint32"}
    if "hknpCompoundShape" in {it.name for it in pg.items}:
        need |= {"hknpCompoundShape", "hknpCompoundShapeData", "hkcdSimdTree::Node", "hkFreeListArrayElement<tVALUE_TYPE=hknpShapeInstance>"}
    if need - have:
        raise Unsupported("template lacks " + ", ".join(sorted(need - have)))
    first = {}
    for it in g0.items:
        first.setdefault(it.name, it)
    root0, mat0, mot0 = g0.items[0], first["hknpMaterial"], first["hknpMotionProperties"]
    bod0 = first["hknpPhysicsSystemData::bodyCinfoWithAttachment"]
    roles = None
    for shp0 in g0.items:
        if shp0.name == "hknpConvexPolytopeShape" and 56 in shp0.slots:      # a body shape with properties (compound children have none)
            roles = {"shape": shp0, "rcp": shp0.slots[56][1], "verts": shp0.slots[66][1], "planes": shp0.slots[80][1], "faces": shp0.slots[84][1],
                     "idx": shp0.slots[88][1], "conn": shp0.slots[96][1]}
            roles["entry"] = roles["rcp"].slots[24][1]
            roles["mass"] = roles["entry"].slots[0][1]
            roles["vedges"] = roles["conn"].slots[24][1]
            roles["flinks"] = roles["conn"].slots[40][1]
            break
    roles_nop = None
    for shp0 in g0.items:
        if shp0.name == "hknpConvexPolytopeShape" and 56 not in shp0.slots and 96 in shp0.slots:
            roles_nop = {"shape": shp0, "verts": shp0.slots[66][1], "planes": shp0.slots[80][1], "faces": shp0.slots[84][1], "idx": shp0.slots[88][1],
                         "conn": shp0.slots[96][1]}
            roles_nop["vedges"] = roles_nop["conn"].slots[24][1]
            roles_nop["flinks"] = roles_nop["conn"].slots[40][1]
            break

    def ptype(cls, rel):
        return t.by_name(SLOT_SCHEMA[cls][rel])

    def ti_of(name):
        return t.find(name)[0]

    proot = pg.items[0]
    if proot.name != "hknpPhysicsSystemData":
        raise Unsupported("root " + proot.name)
    m_it, mo_it, b_it = proot.slots[24][1], proot.slots[40][1], proot.slots[56][1]
    c_it = proot.slots[72][1] if 72 in proot.slots else None
    root_n = _fresh(root0)
    root_n.slots = {r: [v[0], None] for r, v in root0.slots.items() if r in (24, 40, 56)}
    # ---- materials / motion properties
    mats = _fresh(mat0)
    mats.cnt, mats.data = m_it.cnt, bytearray()
    for k in range(m_it.cnt):
        b = bytearray(mat0.data[:112])
        src = m_it.data[80 * k:80 * (k + 1)]
        b[50:56] = src[26:32]                          # dynamicFriction / staticFriction / restitution (hkHalf16)
        b[56:58] = src[32:34]                          # combine policies
        b[60:72] = src[36:48]                          # weldingTolerance, maxContactImpulse, fractionOfClippedImpulseToApply
        mats.data += b
    mots = _fresh(mot0)
    mots.cnt, mots.data = mo_it.cnt, bytearray(mo_it.data)   # identical layout in both games
    # ---- bodies
    bodies = _fresh(bod0)
    bodies.cnt, bodies.data = b_it.cnt, bytearray()
    shape_items, order_of = [], {}
    for k in range(b_it.cnt):
        s = b_it.data[192 * k:192 * (k + 1)]
        sh = b_it.slots[192 * k][1]
        if id(sh) not in order_of:
            order_of[id(sh)] = len(shape_items)
            shape_items.append(sh)
        b = bytearray(176)
        b[8:128] = s[8:128]
        b[128:140] = s[136:148]                        # P1 has 8 more bytes before motionPropertiesId and 8 more before attachedBody
        b[160:176] = s[176:192]
        bodies.data += b
        bodies.slots[176 * k] = [bod0.slots[0][0], None]
    # ---- shapes: convex hulls (hknpConvexShape -> hknpConvexPolytopeShape), spheres, compounds (recursively)
    sph0 = first.get("hknpSphereShape")
    sroles = None
    if sph0 is not None:
        sroles = {"shape": sph0, "rcp": sph0.slots[56][1], "verts": sph0.slots[66][1]}
        sroles["entry"] = sroles["rcp"].slots[24][1]
        sroles["mass"] = sroles["entry"].slots[0][1]
    cap0 = first.get("hknpCapsuleShape")
    croles = None
    if cap0 is not None:
        croles = {"shape": cap0, "rcp": cap0.slots[56][1], "verts": cap0.slots[66][1], "planes": cap0.slots[80][1], "faces": cap0.slots[84][1],
                  "idx": cap0.slots[88][1]}
        croles["entry"] = croles["rcp"].slots[24][1]
        croles["mass"] = croles["entry"].slots[0][1]
    by_off = {it.off0: it for it in pg.items}
    memo = {}

    def build_shape(sh):
        if id(sh) in memo:
            return memo[id(sh)]
        if sh.name == "hknpCompoundShape":
            grp = build_compound(sh)
        elif sh.name == "hknpCompressedMeshShape":
            grp = build_mesh(sh)
        elif sh.name in ("hknpConvexShape", "hknpSphereShape", "hknpCapsuleShape"):
            grp = build_simple(sh)
        else:
            raise Unsupported("shape class " + sh.name)
        memo[id(sh)] = grp
        return grp

    def build_simple(sh):
        s = P1ShapeView(pt, D, sh).decode()
        rl = {"hknpConvexShape": roles, "hknpSphereShape": sroles, "hknpCapsuleShape": croles}[sh.name]
        if sh.name == "hknpConvexShape" and s["mass"] is None and roles_nop is not None:
            rl = roles_nop
        if rl is None:
            raise Unsupported("template has no " + sh.name)
        if s["mass"] is None:                            # compound children carry no properties
            rl = {r: it for r, it in rl.items() if r not in ("rcp", "entry", "mass")}
        grp = {r: it.clone() for r, it in rl.items()}
        link = {id(rl[r]): grp[r] for r in rl}
        for it in grp.values():
            for rel in list(it.slots):
                tgt = it.slots[rel][1]
                if tgt is not None and id(tgt) not in link:
                    del it.slots[rel]
                    it.data[rel:rel + 4] = bytes(4)
                else:
                    it.slots[rel][1] = link[id(tgt)] if tgt is not None else None
        S = grp["shape"].data
        S[40:44], S[48:52], S[64:66] = s["radius"], s["user"], s["maxpen"]
        grp["verts"].cnt, grp["verts"].data = len(s["verts"]), bytearray(_vertex_block(s["verts"]))
        if sh.name == "hknpCapsuleShape":
            hv, hp = capsule_hull(s["verts"][0], s["verts"][1], struct.unpack("<f", s["radius"])[0])
            grp["verts"].cnt, grp["verts"].data = 8, bytearray(_vertex_block(hv))
            grp["planes"].cnt, grp["planes"].data = 6, bytearray(struct.pack("<24f", *[x for pl in hp for x in pl]))
            S[40:44] = struct.pack("<f", struct.unpack("<f", s["radius"])[0] * 0.99)     # Part I's radius = TLOU2's a.w = radius / 0.99
            S[112:128] = struct.pack("<4f", *s["verts"][0], struct.unpack("<f", s["radius"])[0])
            S[128:144] = struct.pack("<3f", *s["verts"][1]) + cap0.data[140:144]
        if sh.name == "hknpConvexShape":
            grp["planes"].cnt, grp["planes"].data = len(s["planes"]) // 16, bytearray(s["planes"])
            grp["faces"].cnt, grp["faces"].data = len(s["faces"]) // 4, bytearray(s["faces"])
            grp["idx"].cnt, grp["idx"].data = len(s["indices"]), bytearray(s["indices"])
            grp["vedges"].cnt, grp["vedges"].data = len(s["vertexEdges"]) // 4, bytearray(s["vertexEdges"])
            grp["flinks"].cnt, grp["flinks"].data = len(s["faceLinks"]) // 4, bytearray(s["faceLinks"])
        if s["mass"] is not None:
            grp["entry"].data[8:12] = s["pkey"]
            grp["mass"].data = bytearray(s["mass"])
        return grp

    def build_mesh(sh):
        """hknpCompressedMeshShape: the level path (havok_convert: decode the Part I mesh, encode the TLOU2 tagfile with section trees, SIMD tree and key
        tables) gives the shape and its data objects; they are grafted into this graph with the type indices of the template"""
        import havok_convert as hc
        if "hknpCompressedMeshShape" not in first:
            raise Unsupported("template has no mesh shape")
        m = hc.p1_mesh(bytes(D[sh.off0:]))
        ref = hc.reference_tag()
        gb = Graph.from_tag(H.Tag.parse(hc.encode_t2(m, ref)))
        for it in gb.items:
            it.ti = t.by_name(gb.tag.tname(it.ti))
            for rel in it.slots:
                it.slots[rel][0] = t.by_name(gb.tag.tname(it.slots[rel][0]))
        shape = gb.items[0]
        m0 = first["hknpCompressedMeshShape"]
        shape.data[0x34:0x38] = m0.data[0x34:0x38]           # userData high dword: the template's (Part I has 0)
        pr = P1ShapeView(pt, D, sh).props()
        if pr["mass"] is not None and 56 in m0.slots:       # stock static meshes (glass, ...) carry no mass properties: dropped with a template without
            rcp0 = m0.slots[56][1]
            entry0 = rcp0.slots[24][1]
            mass0 = entry0.slots[0][1]
            rcp, entry, mass = rcp0.clone(), entry0.clone(), mass0.clone()
            rcp.slots = {24: [rcp0.slots[24][0], entry]}
            entry.slots = {0: [entry0.slots[0][0], mass]}
            entry.data[8:12] = pr["pkey"]
            mass.data = bytearray(pr["mass"])
            shape.slots[56] = [m0.slots[56][0], rcp]
        return {"shape": shape}

    def build_compound(sh):
        if "hknpCompoundShape" not in first:
            raise Unsupported("template has no compound")
        c0 = first["hknpCompoundShape"]
        fl0, cd0 = c0.slots[80][1], c0.slots[184][1]
        rcp0 = c0.slots[56][1]
        entry0 = rcp0.slots[24][1]
        mass0 = entry0.slots[0][1]
        nodes0, pts0 = cd0.slots[64][1], cd0.slots[80][1]
        off = sh.off0
        comp, rcp, entry, mass = c0.clone(), rcp0.clone(), entry0.clone(), mass0.clone()
        fl, cd, nodes, pts = _fresh(fl0), cd0.clone(), nodes0.clone(), pts0.clone()
        comp.slots = {56: [c0.slots[56][0], rcp], 80: [c0.slots[80][0], fl], 184: [c0.slots[184][0], cd]}
        rcp.slots = {24: [rcp0.slots[24][0], entry]}
        entry.slots = {0: [entry0.slots[0][0], mass]}
        cd.slots = {64: [cd0.slots[64][0], nodes], 80: [cd0.slots[80][0], pts]}
        keep = bytes(c0.data)
        copy_by_name(pt, sh.ti, bytes(sh.data), t, ti_of("hknpCompoundShape"), comp.data, rep)
        comp.data[32:34] = keep[32:34]                   # flags / type / dispatchType: version specific enums, template values
        comp.data[34:35] = keep[34:35]
        comp.data[36:37] = keep[36:37]
        comp.data[48:52] = sh.data[40:44]                # userData low dword; the high dword is the template's
        comp.data[52:56] = keep[52:56]
        # the embedded bounding volume (hknpCompoundShapeData at +176) -> hknpCompoundShapeData
        cdd = bytearray(cd0.data)
        copy_by_name(pt, pt.find("hknpCompoundShapeData")[0], bytes(sh.data[176:272]), t, ti_of("hknpCompoundShapeData"), cdd, rep)
        cdd[96:97] = cd0.data[96:97]                     # bounding volume type enum: template value
        cd.data = cdd
        pr = P1ShapeView(pt, D, sh).props()
        entry.data[8:12] = pr["pkey"]
        mass.data = bytearray(pr["mass"])
        eo = off + 72 + struct.unpack_from("<q", D, off + 72)[0]
        n = U32.unpack_from(D, off + 80)[0]
        no = off + 240 + struct.unpack_from("<q", D, off + 240)[0]
        nn = U32.unpack_from(D, off + 248)[0]
        P = []
        for k in range(nn):
            b = D[no + 128 * k:no + 128 * (k + 1)]
            P.append({"box": np.frombuffer(b[:96], "<f4").reshape(6, 4), "raw": b[:112], "ints": struct.unpack_from("<4i", b, 96), "leaf": b[112]})
        t_nodes, leaf_order = convert_tree(P)
        leaf_of = {inst: k for k, (inst, _) in enumerate(leaf_order)}
        fl.cnt, fl.data = n, bytearray()
        fl.slots = {}
        for k in range(n):
            ib = D[eo + 64 * k:eo + 64 * (k + 1)]
            x, y, z, w = struct.unpack_from("<4f", ib, 0)
            tr = struct.unpack_from("<3f", ib, 16)
            sc = struct.unpack_from("<3f", ib, 32)
            cols = [(1 - 2 * (y * y + z * z), 2 * (x * y + z * w), 2 * (x * z - y * w)),
                    (2 * (x * y - z * w), 1 - 2 * (x * x + z * z), 2 * (y * z + x * w)),
                    (2 * (x * z + y * w), 2 * (y * z - x * w), 1 - 2 * (x * x + y * y))]
            e = bytearray(fl0.data[:112])
            for j, cv in enumerate(cols):
                struct.pack_into("<3f", e, 16 * j, *cv)
                e[16 * j + 12:16 * j + 16] = bytes(4)
            U32.pack_into(e, 12, 0x3F000000 | ib[30])
            struct.pack_into("<3f", e, 48, *tr)
            U32.pack_into(e, 60, 0x3F000000 + leaf_of.get(k, 0))
            struct.pack_into("<3f", e, 64, *sc)
            e[88:92] = ib[44:48]                          # shapeTag, destructionTag
            fl.data += e
            child = by_off[(eo + 64 * k + 48) + struct.unpack_from("<q", ib, 48)[0]]
            fl.slots[112 * k + 80] = [fl0.slots[80][0], build_shape(child)["shape"]]
        nodes.cnt, nodes.data = len(t_nodes), bytearray(b"".join(t_nodes))
        pts.data = bytearray()
        for inst, box in leaf_order:
            pts.data += struct.pack("<3f", box[0] + box[1], box[2] + box[3], box[4] + box[5]) + U32.pack(0x3F000000)
        pts.cnt = len(leaf_order)
        return {"shape": comp}

    shapes = [build_shape(sh) for sh in shape_items]
    for k in range(b_it.cnt):
        bodies.slots[176 * k][1] = shapes[order_of[id(b_it.slots[192 * k][1])]]["shape"]
    root_n.slots[24][1], root_n.slots[40][1], root_n.slots[56][1] = mats, mots, bodies
    # ---- constraints
    done = {}                                           # id(P1 item) -> T2 Item

    def convert_constraint(pit):
        if id(pit) in done:
            return done[id(pit)]
        cls = pit.name
        tmpl = first[cls]
        n = _fresh(tmpl)
        done[id(pit)] = n
        p_ti, t_ti = pit.ti, ti_of(cls)
        copy_by_name(pt, p_ti, bytes(pit.data), t, t_ti, n.data, rep)
        pmap, tmap = _ptr_leaf_map(pt, p_ti), _ptr_leaf_map(t, t_ti)
        inv = {v: k for k, v in tmap.items()}
        for rel, (pti, tgt) in sorted(pit.slots.items()):
            if tgt is None:
                continue
            path = pmap[rel]
            trel = inv[path]
            n.slots[trel] = [ptype(cls, trel), convert_constraint(tgt)]
        return n
    if c_it is not None:
        cin = _fresh(first["hknpConstraintCinfo"])
        cin.cnt, cin.data = c_it.cnt, bytearray(40 * c_it.cnt)
        p_ti, t_ti = c_it.ti, ti_of("hknpConstraintCinfo")
        for k in range(c_it.cnt):
            buf = bytearray(first["hknpConstraintCinfo"].data[:40])
            copy_by_name(pt, p_ti, bytes(c_it.data[40 * k:40 * (k + 1)]), t, t_ti, buf, rep)
            cin.data[40 * k:40 * (k + 1)] = buf
            tgt = c_it.slots.get(40 * k, [None, None])[1]
            cin.slots[40 * k] = [ptype("hknpConstraintCinfo", 0), convert_constraint(tgt) if tgt is not None else None]
        root_n.slots[72] = [ptype("hknpPhysicsSystemData", 72), cin]
    g = Graph(t)
    g.items = index_order(root_n)
    g.layout_order = layout_order(root_n)
    assert len(g.items) == len(g.layout_order)
    rep.update(shapes=len(shapes), bodies=b_it.cnt, materials=m_it.cnt, motions=mo_it.cnt, constraints=(c_it.cnt if c_it else 0))
    return g.encode()


class P1ShapeView:
    """one hknpConvexShape item of a Part I image (128-byte object + inline relative arrays)"""

    def __init__(self, pt, D, item):
        self.D, self.off = D, item.off0

    def rel(self, field):
        r, c = struct.unpack_from("<iI", self.D, self.off + field)
        return self.off + field + r, c

    def props(self):
        D, off = self.D, self.off
        pro = off + 48 + struct.unpack_from("<q", D, off + 48)[0]
        nprop = U32.unpack_from(D, off + 56)[0]
        if nprop > 1:
            raise Unsupported("shape with %d properties" % nprop)
        if not nprop:
            return {"pkey": None, "mass": None}
        mo = pro + struct.unpack_from("<q", D, pro)[0]
        return {"pkey": D[pro + 8:pro + 12], "mass": D[mo:mo + 56]}

    def decode(self):
        D, off = self.D, self.off
        vo, vc = self.rel(64)
        po, pc = self.rel(72)
        fo, fc = self.rel(80)
        io, ic = self.rel(88)
        eo, ec = self.rel(96)
        veo, vec = self.rel(104)
        pro = off + 48 + struct.unpack_from("<q", D, off + 48)[0]      # property array: rel ptr at +48, count at +56; entry {rel ptr to mass props, key, flags}
        nprop = U32.unpack_from(D, off + 56)[0]
        if nprop > 1:
            raise Unsupported("shape with %d properties" % nprop)
        mo = pro + struct.unpack_from("<q", D, pro)[0] if nprop else 0
        return {"radius": D[off + 32:off + 36], "user": D[off + 40:off + 44], "maxpen": D[off + 112:off + 114],
                "verts": [struct.unpack_from("<3f", D, vo + 12 * i) for i in range(vc)], "planes": D[po:po + 16 * pc],
                "faces": D[fo:fo + 4 * fc], "indices": D[io:io + ic], "faceLinks": D[eo:eo + 4 * ec], "vertexEdges": D[veo:veo + 4 * vec],
                "pkey": D[pro + 8:pro + 12] if nprop else None, "mass": D[mo:mo + 56] if nprop else None}


def convert_tree(P):
    """Part I hkcdSimdTree nodes (128 bytes: 6 x vec4 boxes, 4 ints, isLeaf, isActive; node 0 unused, root 1) -> (TLOU2 nodes of 112 bytes, leaf order
    [(instance, box lx hx ly hy lz hz)]).  TLOU2 encodes a child as (node << 1) or (instance << 1) | 1 and has no separate leaf node for a single
    instance (the entry sits in the parent slot); a leaf node with several instances stays a node whose slots are leaf entries."""
    def resolve(n):
        """an interior node whose only entry is another node is skipped (TLOU2 trees have no single-child chains)"""
        while not P[n]["leaf"]:
            v = [x for x in P[n]["ints"] if x != 0]
            if len(v) == 1 and not (P[v[0]]["leaf"] and len([x for x in P[v[0]]["ints"] if x != -1]) == 1):
                n = v[0]
            else:
                break
        return n

    def entries(n):
        nd = P[n]
        out = []
        for v in nd["ints"]:
            if nd["leaf"]:
                out.append(None if v == -1 else ("leaf", v))
            elif v == 0:
                out.append(None)
            else:
                c = P[v]
                valid = [x for x in c["ints"] if x != -1] if c["leaf"] else None
                if c["leaf"] and len(valid) == 1:
                    out.append(("leaf", valid[0]))
                else:
                    out.append(("node", resolve(v)))
        return out
    root = resolve(1)
    new = {root: 1}
    order = [root]
    for n in order:
        for e in entries(n):
            if e and e[0] == "node" and e[1] not in new:
                new[e[1]] = len(new) + 1
                order.append(e[1])
    out = [bytes(P[0]["raw"])]
    for n in order:
        raw = bytearray(P[n]["raw"])
        for i, e in enumerate(entries(n)):
            v = 0 if e is None else ((e[1] << 1) | 1 if e[0] == "leaf" else new[e[1]] << 1)
            struct.pack_into("<i", raw, 96 + 4 * i, v)
        out.append(bytes(raw))
    leaves = []

    def walk(n):
        for i, e in enumerate(entries(n)):
            if e is None:
                continue
            if e[0] == "leaf":
                b = P[n]["box"]
                leaves.append((e[1], [float(b[0][i]), float(b[1][i]), float(b[2][i]), float(b[3][i]), float(b[4][i]), float(b[5][i])]))
            else:
                walk(e[1])
    walk(root)
    return out, leaves


def capsule_hull(a, b, radius):
    """TLOU2 capsule shapes carry a box hull around the segment a-b (measured on the 2545 stock capsules): 8 vertices / 6 planes, faces and indices
    constant; radius is Part I's convex radius (= a.w); half width delta = radius / 100 on both perpendicular axes, extended by delta past both ends.
    d = (b - a) / |b - a|; p = normalize(d x y) for a z dominant axis, normalize(z x d) otherwise, q = d x p (the roll of p, q around d is the one thing
    Part I does not carry: stock capsules use p along either helper axis, 86% satisfy q = d x p; the box is 1% of the radius thick, so the roll
    moves the hull by less than that).
    vertex k: end b for even k, end a for odd k; (+p, +q), (-p, +q), (+p, -q), (-p, -q) for k >> 1 = 0..3; planes +d, -d, +p, -p, +q, -q"""
    a, b = np.array(a, float), np.array(b, float)
    d = b - a
    L = float(np.linalg.norm(d))
    d /= L
    if int(np.argmax(abs(d))) == 2:
        p = np.cross(d, [0.0, 1.0, 0.0])
    else:
        p = np.cross([0.0, 0.0, 1.0], d)
    p /= np.linalg.norm(p)
    q = np.cross(d, p)
    dl = radius / 100.0
    c = (a + b) / 2
    half = L / 2 + dl
    verts = []
    for k in range(8):
        sd = 1 if k % 2 == 0 else -1
        sp = 1 if (k >> 1) % 2 == 0 else -1
        sq = 1 if (k >> 1) < 2 else -1
        verts.append(tuple(c + sd * half * d + sp * dl * p + sq * dl * q))
    planes = []
    for n, h in ((d, half), (-d, half), (p, dl), (-p, dl), (q, dl), (-q, dl)):
        planes.append((float(n[0]), float(n[1]), float(n[2]), float(-(np.dot(n, c)) - h)))
    return verts, planes
