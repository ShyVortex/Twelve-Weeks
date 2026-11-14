"""Part I -> TLOU2 shader ABI retarget for converted Part I level paks (re/part1/geometry-upgrade.md s10).

Why: a Part I level pak embeds its own compiled material shaders (EFFECT items -> passes -> stages -> 'ndshader' blobs =
DXIL program container + root-signature container).  The material side of their ABI is the same as TLOU2's (space5 material
textures, space3 per-draw buffers, same per-material layouts by id), but the ENGINE-GLOBAL side changed between the games:

  role                   Part I id (pak table)          TLOU2 id      difference (by parameter name, GEOMETRY_1 +0x60 tables)
  per-frame cbuffer      0x3a89862b / 0x04a50665 0xb44  0x767c0614 0xb74  TLOU2 inserted 3 params: 182 of 250 moved (4..48 bytes)
  view cbuffer           0x96c693b9 0xaf0               0x6638bddc 0xb30  TLOU2 inserted g_gfxRegionConstsDummy: 28 moved (+0x40)
  global SRV/UAV table   0xabb5ec8d 293 descriptors     0xbc7e24a6 295    TLOU2 inserted 2 descriptors at 11: 161 moved (+2)

A stage asks for a global buffer by id (TechniqueShaderCommon::SetupCBuffers, exe+18a4410: kind < 2 -> registry lookup by the
32-bit id); the renderer fills the TLOU2 ids.  The Part I shaders read the Part I offsets: textures sample, the per-frame
terms (exposure / lightmap / probe constants, light lists, volumetric probe textures) come from the wrong places.

What this does (exact maps from the parameter names; nothing guessed):
  * DXIL: every cbufferLoadLegacy on the per-frame / view cbuffer gets the TLOU2 row, every extractvalue the TLOU2 component
    (word map by name); dynamic rows (arrays) get their base constant moved; the declared cbuffer size follows (type + metadata).
  * RTS0: the global descriptor table keeps Part I's registers but gets explicit TLOU2 table offsets per register (by name),
    so no SRV register / metadata / PSV0 changes are needed.
  * stage records: the global entries name the TLOU2 ids (id, size, param count, TLOU2 param array).
  * GEOMETRY_1 +0x60 tables: the Part I global descriptors are rewritten to the TLOU2 ones (so the pak registers them itself).
The containers are re-signed; a blob keeps its size (the program gives up its ILDN debug name / HASH part when the root
signature grows).

  python p1_abi.py ref <stock TLOU2 level pak>... --p1 <converted Part I pak>   # (re)build data/p1_abi_ref.json
  python p1_abi.py fix <in.pak> <out.pak> [--verify]                             # retarget one converted pak
  python p1_abi.py check <pak>... [--materials]                                  # audit (also p1_audit / tests)
"""
import collections
import hashlib
import json
import os
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import dxbc  # noqa: E402
import dxil_rw  # noqa: E402
import t2pak  # noqa: E402

REF_PATH = os.path.join(HERE, "data", "p1_abi_ref.json")
KIND_HASH = {0x7fb43557b54149ce: 0, 0xfe46f400c6b86658: 1, 0x026f7568983161e0: 2, 0x414a134c24ef8152: 3,
             0x5fb32d5f6b437923: 4, 0xb3c70b193d650662: 5, 0xe1b96e360b1bf792: 6, 0x614aaac8bd3d97bf: 7}
NDSHADER = b"ndshader"
PAGE_BODY = 0xFF000          # appended pages stay below the 1 MiB page size every TLOU2 pak keeps (p1_convert.PAGE_LIMIT)


class PatchError(Exception):
    pass


# ==================================================================== reference data (layouts by name)
def _geometry_tables(pk):
    """[(page, offset of the 0x28-byte descriptor, raw descriptor, [param records])] of every GEOMETRY_1 +0x60 table"""
    out = []
    for typ, pg, off in pk.items():
        if typ != "GEOMETRY_1":
            continue
        n = pk.u32(pg, off + 0x20)
        p = pk.ptr(pg, off + 0x60)
        if not p:
            continue
        for k in range(n):
            ep, eo = p[0], p[1] + 24 * k
            cnt = pk.u32(ep, eo + 8)
            a = pk.ptr(ep, eo + 0x10)
            for j in range(cnt if a else 0):
                dpg, doff = a[0], a[1] + 0x28 * j
                raw = bytes(pk.pages[dpg][doff:doff + 0x28])
                out.append((dpg, doff, raw, _params(pk, dpg, doff)))
    return out


def _params(pk, dpg, doff):
    n = pk.u32(dpg, doff + 0x18)
    a = pk.ptr(dpg, doff + 0x20)
    out = []
    for k in range(n if a else 0):
        pg, o = a[0], a[1] + 0x20 * k
        np_ = pk.ptr(pg, o)
        name = ""
        if np_:
            s = pk.pages[np_[0]]
            name = s[np_[1]:s.index(b"\0", np_[1])].decode("latin1")
        rec = bytes(pk.pages[pg][o:o + 0x20])
        sid, h32, off, size = struct.unpack_from("<QIHH", rec, 8)
        out.append({"name": name, "sid": sid, "h32": h32, "off": off, "size": size, "tail": rec[0x18:0x20].hex()})
    return out


def _desc_json(raw, params):
    kh, x, cid, size, n, f1c = struct.unpack_from("<QQIIII", raw, 0)
    return {"id": cid, "kind": KIND_HASH.get(kh, -1), "kind_hash": kh, "x": x, "size": size, "f1c": f1c, "params": params}


def build_ref(stock_paths, p1_path):
    """reference JSON: the TLOU2 global layouts (identical in every stock pak given - asserted) + the Part I ones + the map"""
    t2 = {}
    for path in stock_paths:
        pk = t2pak.TPak(open(path, "rb").read())
        for pg, off, raw, prm in _geometry_tables(pk):
            d = _desc_json(raw, prm)
            if d["kind"] not in (0, 1):
                continue
            if d["id"] in t2:
                a, b = t2[d["id"]], d
                assert (a["size"], [(p["name"], p["off"], p["size"]) for p in a["params"]]) == \
                       (b["size"], [(p["name"], p["off"], p["size"]) for p in b["params"]]), "id %#x differs between stock paks" % d["id"]
            t2[d["id"]] = d
    pk = t2pak.TPak(open(p1_path, "rb").read())
    p1 = {}
    for pg, off, raw, prm in _geometry_tables(pk):
        d = _desc_json(raw, prm)
        if d["kind"] in (0, 1) and d["id"] not in t2:
            p1[d["id"]] = d
    mp = {}
    for cid, d in p1.items():
        names = {p["name"] for p in d["params"]}
        best = max((len(names & {p["name"] for p in t["params"]}), tid) for tid, t in t2.items() if t["kind"] == d["kind"])
        tid = best[1]
        tn = {p["name"]: p for p in t2[tid]["params"]}
        missing = [p["name"] for p in d["params"] if p["name"] not in tn or tn[p["name"]]["size"] != p["size"]
                   or tn[p["name"]]["tail"] != p["tail"]]
        if missing:
            raise SystemExit("Part I %#x -> TLOU2 %#x: %d params without an identical TLOU2 param (%s ...)" % (cid, tid, len(missing), missing[:4]))
        mp[cid] = tid
    # role by the descriptor's class hash (+8): the cbuffers share one (0x9e275796a0d9a90b), the descriptor table has its own;
    # a table's param offsets are descriptor indices, a cbuffer's byte offsets
    cbx = collections.Counter(t["x"] for t in t2.values()).most_common(1)[0][0]
    roles = {tid: "srv_table" if t["x"] != cbx and any(p["name"].endswith("_vsharp") for p in t["params"]) else "cbuffer"
             for tid, t in t2.items()}
    ref = {"note": "generated by p1_abi.py ref; TLOU2 layouts from stock level paks, Part I ones from a converted Bookstore pak",
           "t2": {"%#010x" % k: v for k, v in sorted(t2.items())},
           "p1": {"%#010x" % k: v for k, v in sorted(p1.items())},
           "map": {"%#010x" % k: "%#010x" % v for k, v in sorted(mp.items())},
           "role": {"%#010x" % k: v for k, v in sorted(roles.items())},
           "t2_root_signatures": sorted(_rts_md5s(stock_paths))}
    return ref


def _rts_md5s(paths):
    out = set()
    for path in paths:
        d = open(path, "rb").read()
        for c in _containers(d):
            for tag, data in dxbc.parts(c):
                if tag == b"RTS0":
                    out.add(hashlib.md5(data).hexdigest()[:8])
    return out


def _containers(d):
    i = d.find(b"DXBC")
    while i >= 0:
        sz = struct.unpack_from("<I", d, i + 24)[0]
        if 32 < sz < 8_000_000:
            try:
                dxbc.parts(d[i:i + sz])
                yield d[i:i + sz]
                i = d.find(b"DXBC", i + sz)
                continue
            except Exception:
                pass
        i = d.find(b"DXBC", i + 4)


class Ref:
    def __init__(self, path=REF_PATH):
        j = json.load(open(path))
        h = lambda s: int(s, 16)
        self.t2 = {h(k): v for k, v in j["t2"].items()}
        self.p1 = {h(k): v for k, v in j["p1"].items()}
        self.map = {h(k): h(v) for k, v in j["map"].items()}
        self.role = {h(k): v for k, v in j["role"].items()}
        self.t2_rts = set(j["t2_root_signatures"])
        self.wmap, self.wparam, self.imap = {}, {}, {}
        for p1id, tid in self.map.items():
            tn = {p["name"]: p for p in self.t2[tid]["params"]}
            if self.role[tid] == "cbuffer":
                wm, wp = {}, {}
                for p in self.p1[p1id]["params"]:
                    q = tn[p["name"]]
                    for w in range(0, max(p["size"], 4), 4):
                        wm[(p["off"] + w) // 4] = (q["off"] + w) // 4
                        wp[(p["off"] + w) // 4] = p["name"]
                self.wmap[p1id], self.wparam[p1id] = wm, wp
            else:
                im = {}
                for p in self.p1[p1id]["params"]:
                    q = tn[p["name"]]
                    for j_ in range(max(p["size"], 1)):
                        im[p["off"] + j_] = q["off"] + j_
                self.imap[p1id] = im

    def target(self, p1id):
        return self.map.get(p1id)


# ==================================================================== DXIL program patch
def patch_program(c, roles, ref):
    """c = program DXBC container; roles = {(space, register): Part I cbuffer id}.  -> (new container, stats) ; raises
    PatchError when a load cannot be mapped exactly (the program is then left alone by the caller)."""
    P = dxbc.parts(c)
    pd = dict(P)
    if b"DXIL" not in pd or b"PSV0" not in pd:
        raise PatchError("no DXIL / PSV0 part")
    psv = dxbc.ranges_by_class(pd[b"PSV0"])
    prog = dxil_rw.Program(dxbc.bitcode(pd[b"DXIL"]))
    handles = {}
    for it in prog.calls(57):                            # createHandle(57, class, range id, index, nonuniform)
        k = it.call[2]
        if k[1] != 2:
            continue
        if k[2] is None:
            raise PatchError("CBV handle with a dynamic range id")
        sp, lo, hi = psv["cbv"][k[2]]
        if (sp, lo) in roles:
            handles[it.vid] = roles[(sp, lo)]
    st = collections.Counter()
    const_edits, lit_edits, inserts, ref_edits = [], [], [], []
    dyn_done = set()
    used = set()
    for it in prog.calls(59):                            # cbufferLoadLegacy(59, handle, row)
        cid = handles.get(it.call[1][1])
        if cid is None:
            continue
        used.add(cid)
        wm = ref.wmap[cid]
        users = prog.users(it.vid)
        if any(u.code != 26 or u.ref_ids[0] != it.vid or len(u.ops) != 2 for u in users):
            raise PatchError("cbuffer load result used other than by extractvalue")
        comps = [(u, u.ops[1]) for u in users]
        row = it.call[2][2]
        if row is not None:
            new = {}
            for u, cc in comps:
                w = wm.get(row * 4 + cc)
                if w is None:
                    raise PatchError("%#x row %d comp %d: no Part I parameter there" % (cid, row, cc))
                new[cc] = w
            rows = collections.Counter(w // 4 for w in new.values())
            if not rows:
                st["loads without users"] += 1
                continue
            nr = rows.most_common(1)[0][0]                 # the load keeps the row most of its components move to;
            if nr != row:                                  # components landing elsewhere read a second, inserted load
                const_edits.append((it, it.call[3] + 2, nr))
                st["rows moved"] += 1
            else:
                st["rows kept"] += 1
            extra = {}
            for r2 in rows:
                if r2 != nr:
                    extra[r2] = len(inserts)
                    inserts.append((it, it, {2: ("c", r2)}))
                    st["loads split"] += 1
            for u, cc in comps:
                w = new[cc]
                if w // 4 != nr:
                    ref_edits.append((u, 0, extra[w // 4]))
                if w % 4 != cc:
                    lit_edits.append((u, 1, w % 4))
                    st["components moved"] += 1
        else:
            # dynamic row (an array element): row = (... + const) + ...  through 'add' instructions; exactly one constant
            consts, chain, stack = [], set(), [it.call[1][2]]
            while stack:
                v = stack.pop()
                d = prog.by_vid.get(v)
                if d is None or d.code != 2 or d.ops[2] != 0:
                    continue
                chain.add(d.vid)
                for oi, rv in enumerate(d.ref_ids[:2]):
                    cv = prog.const_of(rv)
                    if cv is not None:
                        consts.append((d, oi, cv))
                    else:
                        stack.append(rv)
            if len(consts) != 1:
                raise PatchError("%#x: dynamic row with %d constant terms" % (cid, len(consts)))
            d, oi, base = consts[0]
            name = ref.wparam[cid].get(base * 4)
            if name is None:
                raise PatchError("%#x: dynamic row base %d outside the parameters" % (cid, base))
            ws = [w for w, n in ref.wparam[cid].items() if n == name]
            deltas = {wm[w] - w for w in ws}
            if len(deltas) != 1 or next(iter(deltas)) % 4:
                raise PatchError("%#x: array %s does not move by whole rows" % (cid, name))
            drow = next(iter(deltas)) // 4
            for v in chain:
                for u in prog.users(v):
                    if not (u.vid in chain or (u.code == 34 and u.call[2] and u.call[2][0] == 59
                                               and handles.get(u.call[1][1]) == cid)):
                        raise PatchError("%#x: dynamic row term also used elsewhere" % cid)
            if drow:
                if (d, oi) not in dyn_done:
                    const_edits.append((d, oi, base + drow))
                    dyn_done.add((d, oi))
                st["dynamic bases moved"] += 1
            else:
                st["dynamic bases kept"] += 1
    if not used:
        return None, st
    # declared sizes: [N x i8] type + the metadata's i32 N (only when no instruction uses that module constant)
    sizes = {}
    for cid in used:
        s1, s2 = ref.p1[cid]["size"], ref.t2[ref.map[cid]]["size"]
        if s1 != s2:
            sizes[s1] = s2
    for s1, s2 in sizes.items():
        mvid = [prog.m.n_global + i for i, (t, v) in enumerate(prog.mvals) if v == s1]
        if any(v in it.ref_ids for it in prog.insts for v in mvid):
            st["size kept (constant used by code)"] += 1
            continue
        prog.set_array_len(s1, s2)                          # (a [N x i8] body type, when the layout has one)
        st["declared sizes updated"] += prog.set_module_int(s1, s2)   # the dx.resources cbuffer size
    bc = prog.emit(const_edits, lit_edits, inserts, ref_edits)
    newp = [(t, dxbc.with_bitcode(d, bc) if t == b"DXIL" else d) for t, d in P]
    return dxbc.build(c, newp), st


# ==================================================================== RTS0 patch
def patch_rootsig(c, imap):
    """c = root-signature container (part RTS0); imap = Part I global table index -> TLOU2 index.  The global table (the one
    with the space-4 SRV ranges) gets explicit TLOU2 offsets per register run.  -> new container or None"""
    pd = dict(dxbc.parts(c))
    rs = dxbc.RootSig(pd[b"RTS0"])
    named = sorted(imap)

    def t2_index(pi):
        if pi in imap:
            return imap[pi]
        lo = [k for k in named if k <= pi]                # unnamed index (no shader uses it): its named neighbour's shift
        k = lo[-1] if lo else named[0]
        return imap[k] + (pi - k)
    hit = 0
    for prm in rs.params:
        t, vis, data = prm
        if t != 0 or not any(r[0] == 0 and r[3] == 4 for r in data):
            continue
        hit += 1
        out = []
        for r in data:
            typ, cnt, base, space = r[:4]
            if cnt == dxbc.APPEND:
                raise PatchError("unbounded range in the global table")
            if typ not in (0, 1):
                raise PatchError("range type %d in the global table" % typ)
            # Part I index from the REGISTER (= the parameter's name), not from the range's descriptor offset: a root signature
            # that leaves a range out (Part I's sky: no s201 SRVs, the UAVs appended right after t147..) has its later ranges
            # at lower offsets, but TLOU2 binds one fixed table, so every register goes to the TLOU2 offset of its name.
            # (Material root signatures list every range: there both readings are the same.)
            run = None
            for j in range(cnt):
                ti = t2_index(_p1_index(typ, space, base + j))
                if run is not None and ti == run[-1] + run[1]:
                    run[1] += 1
                else:
                    run = list(r)                          # (type, count, base, space, [flags,] offset)
                    run[1], run[2], run[-1] = 1, base + j, ti
                    out.append(run)
        prm[2] = out
    if hit != 1:
        raise PatchError("root signature: %d global tables" % hit)
    raw = rs.encode()
    return dxbc.build(c, [(t, raw if t == b"RTS0" else d) for t, d in dxbc.parts(c)])


# ==================================================================== blob (ndshader) handling
def _shrink(c, room):
    """program container reduced by up to `room` bytes: drops HASH, then ILDN (both debug-only parts)"""
    P = dxbc.parts(c)
    for drop in ((b"HASH",), (b"HASH", b"ILDN")):
        q = [(t, d) for t, d in P if t not in drop]
        nc = dxbc.build(c, q)
        if len(c) - len(nc) >= room:
            return nc
    return None


def patch_blob(blob, roles, ref, imap):
    """ndshader blob = 0x28 header {'ndshader', u32 3, ..., +0x20 program size, +0x24 root-signature size} + program DXBC +
    root-signature DXBC.  Returns (new blob, stats): the same size when it fits (debug parts dropped if needed), else larger
    (the caller relocates it)."""
    if blob[:8] != NDSHADER:
        raise PatchError("not an ndshader blob")
    ps, rsz = struct.unpack_from("<II", blob, 0x20)
    prog, rsc = blob[0x28:0x28 + ps], blob[0x28 + ps:0x28 + ps + rsz]
    if prog[:4] != b"DXBC" or (rsz and rsc[:4] != b"DXBC"):
        raise PatchError("unexpected ndshader layout")
    np_, st = patch_program(prog, roles, ref) if roles else (None, collections.Counter())
    np_ = np_ or prog
    nr = patch_rootsig(rsc, imap) if rsz else rsc
    room = (len(np_) + len(nr)) - (ps + rsz)
    if room > 0:
        sm = _shrink(np_, room)
        if sm is not None:
            np_ = sm
            st["debug parts dropped"] += 1
    out = bytearray(blob[:0x28])
    struct.pack_into("<II", out, 0x20, len(np_), len(nr))
    body = bytes(out) + np_ + nr
    if len(body) < len(blob):
        body += bytes(len(blob) - len(body))
    else:
        st["blobs relocated (grew %s)" % ("<=64" if len(body) - len(blob) <= 64 else ">64")] += 1
    return body, st


# ==================================================================== pak level
def _effects(pk):
    """[(stage page, stage offset)] of every stage record of every EFFECT item (2 per pass, pass stride 0xb8)"""
    out = []
    for typ, pg, off in pk.items():
        if typ != "EFFECT":
            continue
        p = pk.ptr(pg, off)
        n = pk.u32(pg, off + 8)
        for i in range(n if p else 0):
            for so in (8, 0x48):
                out.append((p[0], p[1] + 0xb8 * i + so))
    return out


def _entries(pk, spg, soff):
    n = pk.u32(spg, soff + 8)
    a = pk.ptr(spg, soff + 0x30)
    return [] if not a else [(a[0], a[1] + 0x28 * k) for k in range(n)]


def fix_pak(data, ref=None, report=None):
    """retarget every EFFECT stage of a converted Part I pak; returns the new pak bytes"""
    ref = ref or Ref()
    pk = t2pak.TPak(data)
    st = collections.Counter()
    stages = _effects(pk)
    if not any(pk.u32(e, o + 0x1c) in ref.map for s_ in stages for e, o in _entries(pk, *s_)):
        return data                                       # no Part I global ids (no EFFECTs, or already retargeted)
    blobs = collections.defaultdict(list)                 # (page, off, size) -> [stage]
    has_blob = set()
    for spg, so in stages:
        b = pk.ptr(spg, so + 0x10)
        size = pk.u32(spg, so + 0xc)
        if b and pk.pages[b[0]][b[1]:b[1] + 8] == NDSHADER:
            blobs[(b[0], b[1], size)].append((spg, so))
            has_blob.add((spg, so))
        elif b or size:
            st["stages without a blob (stripped debug passes)"] += 1
    p1_ids = set(ref.map)
    imap_by_t2 = {}
    for p1id, tid in ref.map.items():
        if ref.role[tid] == "srv_table":
            imap_by_t2[p1id] = ref.imap[p1id]
    srv_p1 = [k for k in imap_by_t2]
    if len(srv_p1) != 1:
        raise PatchError("expected one Part I global SRV table in the reference")
    imap = imap_by_t2[srv_p1[0]]
    patched = set()
    grown, body_sizes = [], {}
    for (bpg, boff, size), sts in blobs.items():
        roles = {}
        for spg, so in sts:
            for epg, eo in _entries(pk, spg, so):
                cid = pk.u32(epg, eo + 0x1c)
                if cid in p1_ids and ref.role[ref.map[cid]] == "cbuffer":
                    reg, kind = pk.pages[epg][eo + 0x20], pk.pages[epg][eo + 0x23]
                    key = (2, reg)                        # kinds 0 / 1 / 2 live in space 2, register = byte +0x20 (kind 3: space 3)
                    if kind not in (0, 1):
                        raise PatchError("Part I global id %#x with kind %d" % (cid, kind))
                    if roles.get(key, cid) != cid and ref.map[roles[key]] != ref.map[cid]:
                        raise PatchError("stages disagree about cbuffer register %s" % (key,))
                    roles[key] = cid
        blob = bytes(pk.pages[bpg][boff:boff + size])
        try:
            nb, s = patch_blob(blob, roles, ref, imap)
        except PatchError as e:
            raise PatchError("blob at page %d +%#x: %s" % (bpg, boff, e))
        st.update(s)
        if len(nb) == size:
            pk.pages[bpg][boff:boff + size] = nb
        else:
            grown.append((nb, sts, pk.flags[bpg]))
        st["blobs patched"] += 1
        patched.update(sts)
    # ---- blobs that grew: appended shader pages (same flag), stage pointers + sizes moved there
    pages_new = collections.defaultdict(list)
    for nb, sts, flag in grown:
        pages_new[flag].append((nb, sts))
    for flag, lst in pages_new.items():
        chunk, body = [], bytearray()
        for nb, sts in lst + [(None, None)]:
            if nb is None or len(body) + len(nb) + 16 > PAGE_BODY:
                pg, base = pk.add_page(body, (), flag=flag)
                st["pages added for grown blobs"] += 1
                for off, sts_ in chunk:
                    for spg, so in sts_:
                        pk.set_ptr(spg, so + 0x10, pg, base + off)
                        struct.pack_into("<I", pk.pages[spg], so + 0xc, len(body_sizes[off]))
                chunk, body = [], bytearray()
                body_sizes.clear()
                if nb is None:
                    break
            while len(body) % 16:
                body.append(0)
            chunk.append((len(body), sts))
            body_sizes[len(body)] = nb
            body += nb
    # ---- new TLOU2 param arrays (one per TLOU2 id) in an appended page
    body, fixups, arr_off, strs = bytearray(), [], {}, {}
    for tid in sorted({ref.map[k] for k in ref.map}):
        while len(body) % 16:
            body.append(0)
        arr_off[tid] = len(body)
        for p in ref.t2[tid]["params"]:
            rec = bytearray(0x20)
            struct.pack_into("<QIHH", rec, 8, p["sid"], p["h32"], p["off"], p["size"])
            rec[0x18:0x20] = bytes.fromhex(p["tail"])
            fixups.append((len(body), p["name"]))
            body += rec
    for _, name in fixups:
        if name not in strs:
            strs[name] = None
    for name in strs:
        strs[name] = len(body)
        body += name.encode("latin1") + b"\0"
    npg, base = pk.add_page(body, [(o, None, strs[n]) for o, n in fixups], flag=0)
    st["param arrays added"] = len(arr_off)
    # ---- stage entries -> TLOU2 ids
    seen = set()
    for spg, so in stages:
        for epg, eo in _entries(pk, spg, so):
            if (epg, eo) in seen:
                continue
            seen.add((epg, eo))
            cid = pk.u32(epg, eo + 0x1c)
            if cid not in p1_ids:
                continue
            if (spg, so) not in patched and (spg, so) in has_blob:
                raise PatchError("stage at page %d +%#x names %#x but its blob was not patched" % (spg, so, cid))
            t = ref.t2[ref.map[cid]]
            struct.pack_into("<I", pk.pages[epg], eo + 0x10, len(t["params"]))
            struct.pack_into("<II", pk.pages[epg], eo + 0x18, t["size"], t["id"])
            pk.set_ptr(epg, eo, npg, base + arr_off[t["id"]])
            st["stage entries retargeted"] += 1
    # ---- GEOMETRY_1 tables: Part I global descriptors -> TLOU2 descriptors
    for typ, pg, off in pk.items():
        if typ != "GEOMETRY_1":
            continue
        n = pk.u32(pg, off + 0x20)
        p = pk.ptr(pg, off + 0x60)
        for k in range(n if p else 0):
            ep, eo = p[0], p[1] + 24 * k
            a = pk.ptr(ep, eo + 0x10)
            for j in range(pk.u32(ep, eo + 8) if a else 0):
                dpg, doff = a[0], a[1] + 0x28 * j
                cid = pk.u32(dpg, doff + 0x10)
                if cid not in p1_ids:
                    continue
                t = ref.t2[ref.map[cid]]
                struct.pack_into("<QIIII", pk.pages[dpg], doff + 8, t["x"], t["id"], t["size"], len(t["params"]), t["f1c"])
                pk.set_ptr(dpg, doff + 0x20, npg, base + arr_off[t["id"]])
                st["geometry descriptors retargeted"] += 1
    if report is not None:
        report.update(st)
    return pk.serialize()


# ==================================================================== audit
def _rts_ok(rs, imap):
    """None if the root signature's global table puts every named Part I register on the TLOU2 offset of the same name"""
    tables = [d for t, v, d in rs.params if t == 0 and any(r[0] == 0 and r[3] == 4 for r in d)]
    if len(tables) != 1:
        return "%d global tables" % len(tables)
    for r in tables[0]:
        if r[-1] == dxbc.APPEND:
            return "Part I layout (appended ranges)"
        p1base = _p1_index(r[0], r[3], r[2])
        for j in range(r[1]):
            if p1base + j in imap and imap[p1base + j] != r[-1] + j:
                return "register %s%d space %d on offset %d, TLOU2 has that name at %d" % (
                    "tu"[r[0]], r[2] + j, r[3], r[-1] + j, imap[p1base + j])
    return None


def check(path, ref=None, materials=False):
    """audit of a (retargeted) converted pak -> (problems, stats[, per-material rows]):
      * no stage entry and no GEOMETRY_1 descriptor names a Part I engine-global id (kinds 0 / 1) any more;
      * every root signature is a stock TLOU2 one or keeps Part I's registers on the TLOU2 table offsets of the same names;
      * materials=True: per material (GEOMETRY_1 technique record) its EFFECT (EFFECT_TABLE by hash), its stages, their
        global ids / root signatures, and its texture slots (each bound to a texture binding entry whose VRAM_DESC is in the pak).
    The DXIL side (every per-frame / view cbuffer read lands on the TLOU2 offset of the same parameter) needs dxc:
    p1_abi_verify.py."""
    ref = ref or Ref()
    pk = t2pak.TPak(open(path, "rb").read())
    bad, st = [], collections.Counter()
    imap = next(ref.imap[k] for k in ref.imap)
    stage_bad = {}
    rts_cache = {}

    def stage_state(spg, so):
        key = (spg, so)
        if key in stage_bad:
            return stage_bad[key]
        err = []
        for epg, eo in _entries(pk, spg, so):
            cid = pk.u32(epg, eo + 0x1c)
            if pk.pages[epg][eo + 0x23] in (0, 1) and cid in ref.map:
                err.append("Part I global id %#x" % cid)
        b = pk.ptr(spg, so + 0x10)
        if b and bytes(pk.pages[b[0]][b[1]:b[1] + 8]) == NDSHADER:
            if b not in rts_cache:
                blob = pk.pages[b[0]]
                ps, rsz = struct.unpack_from("<II", blob, b[1] + 0x20)
                rc = bytes(blob[b[1] + 0x28 + ps:b[1] + 0x28 + ps + rsz])
                raw = dict(dxbc.parts(rc))[b"RTS0"] if rsz else None
                if raw is None:
                    rts_cache[b] = None
                elif hashlib.md5(raw).hexdigest()[:8] in ref.t2_rts:
                    rts_cache[b] = None
                    st["root signatures byte-identical to stock TLOU2"] += 1
                else:
                    rts_cache[b] = _rts_ok(dxbc.RootSig(raw), imap)
                    st["root signatures on TLOU2 offsets" if rts_cache[b] is None else "root signatures NOT on TLOU2 offsets"] += 1
            if rts_cache[b]:
                err.append("root signature: " + rts_cache[b])
        stage_bad[key] = err
        return err
    for spg, so in _effects(pk):
        st["stages"] += 1
        e = stage_state(spg, so)
        if e:
            bad.append("stage page %d +%#x: %s" % (spg, so, "; ".join(e)))
    for pg, off, raw, prm in _geometry_tables(pk):
        cid = struct.unpack_from("<I", raw, 0x10)[0]
        if cid in ref.map:
            bad.append("GEOMETRY_1 table still registers Part I global id %#x" % cid)
        elif cid in ref.t2:
            st["GEOMETRY_1 global descriptors on TLOU2 ids"] += 1
    rows = []
    if materials:
        vh = set()
        for typ, pg, off in pk.items():
            if typ == "VRAM_DESC":
                vh.add(pk.q(pg, off - 48 + 16 + 0x38))
        eff_by_hash = collections.defaultdict(list)
        for typ, pg, off in pk.items():
            if typ == "EFFECT_TABLE":
                n = pk.u32(pg, off)
                a = pk.ptr(pg, off + 8)
                for k in range(n if a else 0):
                    e = pk.ptr(a[0], a[1] + 24 * k)
                    eff_by_hash[pk.q(a[0], a[1] + 24 * k + 16)].append(e)
            if typ != "GEOMETRY_1":
                continue
            nt = pk.u32(pg, off + 0x18)
            ta = pk.ptr(pg, off + 0x48)
            for i in range(nt if ta else 0):
                tpg, to = ta[0], ta[1] + 0x130 * i
                np_ = pk.ptr(tpg, to)
                name = pk.pages[np_[0]][np_[1]:pk.pages[np_[0]].index(b"\0", np_[1])].decode("latin1") if np_ else "?"
                h = pk.q(tpg, to + 0x10)
                ntex = pk.u32(tpg, to + 0x114)
                tl = pk.ptr(tpg, to + 0x20)
                bound = 0
                for j in range(ntex if tl else 0):
                    bp = pk.ptr(tl[0], tl[1] + 0x30 * j + 0x18)
                    if bp and pk.q(bp[0], bp[1] + 8) in vh:
                        bound += 1
                effs = eff_by_hash.get(h, [])
                nst, errs = 0, []
                for e in effs:
                    n = pk.u32(e[0], e[1] + 8)
                    pa = pk.ptr(e[0], e[1])
                    for pi in range(n if pa else 0):
                        for so in (8, 0x48):
                            nst += 1
                            errs += stage_state(pa[0], pa[1] + 0xb8 * pi + so)
                ok = bool(effs) and not errs and bound == ntex
                rows.append((i, name, len(effs), nst, ntex, bound, "ok" if ok else ("; ".join(sorted(set(errs)))[:120] or
                                                                                    ("no EFFECT" if not effs else "unbound textures"))))
                st["materials ok" if ok else "materials with problems"] += 1
    return bad[:12], st, rows


def _p1_index(typ, space, reg):
    """Part I global table index of a register (Part I table: SRV t0..t144 s4, t0..t1 s201, t147..t277 s4, UAV u0..u14 s4)"""
    if typ == 0 and space == 201:
        return 145 + reg
    if typ == 0:
        return reg
    return 278 + reg


def main(argv):
    if not argv or argv[0] not in ("ref", "fix", "check"):
        print(__doc__)
        return 2
    if argv[0] == "ref":
        p1 = argv[argv.index("--p1") + 1]
        stock = [a for a in argv[1:] if a not in ("--p1", p1)]
        ref = build_ref(stock, p1)
        os.makedirs(os.path.dirname(REF_PATH), exist_ok=True)
        json.dump(ref, open(REF_PATH, "w"), indent=1)
        print(REF_PATH, "map", ref["map"], "roles", ref["role"])
        return 0
    if argv[0] == "fix":
        rep = {}
        out = fix_pak(open(argv[1], "rb").read(), report=rep)
        open(argv[2], "wb").write(out)
        print(argv[2], dict(rep))
        return 0
    rc = 0
    mats = "--materials" in argv
    for p in [a for a in argv[1:] if not a.startswith("--")]:
        bad, st, rows = check(p, materials=mats)
        print(p, "OK" if not bad else "PROBLEMS", dict(st))
        for b in bad:
            print("  ", b)
        for r in rows:
            print("   mat %4d effects %d stages %3d textures %2d/%2d  %-4s %s" % (r[0], r[2], r[3], r[5], r[4], r[6], r[1][:110]))
        rc |= bool(bad)
    return rc


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
