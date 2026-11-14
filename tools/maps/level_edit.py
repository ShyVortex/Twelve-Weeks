"""Edit baked TLOU2 level geometry + collision (remove / move / rotate things inside a world-space box).
Spec + findings: re/maps/level-edit.md.   Offline only (CPU): never starts the game or a GPU tool.

Formats (all measured on the real files, see the .md):
  <level>-phys.pak   COLLISION_DATA_HAVOK_BG items: Havok 2017.1 tagfile with one hknpCompressedMeshShape each
                     (tools/part1/havok_convert.py model).  Edited IN PLACE: the new tagfile (never larger than the old
                     one for 'remove') overwrites the old bytes, the item's tagfile size and its per-shape-key table are
                     updated; nothing else in the pak moves.
  <level>.pak        GEOMETRY_1 submeshes are in LOCAL space; the world placement of every prop is a 4x4 matrix
                     (row vectors, translation in row 3) followed by the prop's local AABB twice, inside INTERACTIVE_BG_1's
                     page.  Edited IN PLACE: 64 bytes of matrix (hide = translate far below the map, rotate = rotate
                     the basis rows / translation about a pivot, move = add a delta).

  python level_edit.py extract <level>... [--out DIR] [--game DIR]     # <level>.pak + <level>-phys.pak from the world psarc
  python level_edit.py find <level> x0 y0 z0 x1 y1 z1 [--dir DIR]      # collision items / tags / render instances in a box
  python level_edit.py vis <level> x0 y0 z0 x1 y1 z1 [outside box]     # VIS_INFO_1 kd cells / bitsets a "vis_open" edit would change
  python level_edit.py apply <map key> [--dir DIR] [--out DIR]          # the map's "edits" list in tools/maps/sp_maps.json
  python level_edit.py apply-spec <edit.json> [--dir DIR] [--out DIR]   # {"edits": [...]} straight from a file
  python level_edit.py verify <map key> [--dir DIR] [--out DIR]         # re-read the written paks, compare with the sources
  python level_edit.py preview <map key> <edit index> [--dir DIR] [--out DIR] [--png FILE]
  python level_edit.py group <level> <record offset>                 # the render records of one baked prop + a move spec template
  apply / verify / preview take --editor: also the Scene Editor's tools/maps/<map key>-editor-edits.json

Edit entry (sp_maps.json "edits" of a map, or an apply-spec file):
  {"name": "mansion gate", "level": "san-infected-wilds-mansion",
   "box": [x0, y0, z0, x1, y1, z1],                      # world box (m); y up
   "action": "remove" | "move" | "rotate" | "transform" | "scale_y" | "strip_parts" | "add" | "copy" | "vis_open",   # transform = rotate (angle, pivot) then move (delta)   # vis_open: see the visibility section (box = cells to open, "outside" = box whose cells' visible sets are added, "grid" m)
   "delta": [dx, dy, dz],                                 # move
   "angle": 90, "pivot": "hinge" | [x, y, z],             # rotate about +Y (x' = x c + z s, z' = -x s + z c), degrees
   "collision": {"tags": [1025], "mode": "inside"|"centroid"|"overlap"},   # optional; false = leave the collision alone
   "render": {"name": "wrought-iron-gate", "hide_dy": -1000.0}}   # optional; false = leave the render alone
  render world cut of only some submeshes of a merged mesh: {"world": true, "cut_name": "<asset>", "cut_sub": "<regex on the
  submesh name>", "cut_tris": [triangle indices of that submesh]}  (one piece of the ivy cards of a level-section mesh;
  tools/maps/ivy_float.py writes these)
  "cut_index": [submesh indices] restricts a world cut to those submeshes (converted Part I paks have no submesh names; box = world box)
  render may instead list explicit placements: {"offsets": ["0x553020", ...]}  (pak offsets of the instance matrices; `find` prints them)
  collision may select by the oriented boxes of render instances: {"obb_of": ["0x553020", ...], "margin": 0.1, "tags": [...]}
  move / rotate / transform collision is edited IN PLACE (move_in_place: vertices re-quantised, trees refitted, same size, same
  shape keys); obb selections first grow to whole primitives + the slivers sharing vertices inside a looser box ("close": false
  turns that off, "close_margin" 0.6 m) and to detached pieces wholly inside that box with a tag the selection has ("detached":
  false turns that off); a primitive sharing a vertex with an unselected one never moves in place (it goes remove + add, the
  unselected one stays put); verify fails on stretched (edge > old longest + 0.5 m), non-rigid or stray-moved triangles;
  "inplace": false forces the old remove + re-add path (grows the tagfile)
  (a prop that stands at an angle: the triangles completely inside any of the instances' local boxes; see re/maps/into-the-city.md)
"""
import copy
import glob
import hashlib
import json
import math
import os
import re
import struct
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.dirname(HERE)
ROOT = os.path.dirname(TOOLS)
MAIN = os.environ.get("T2R_MAIN_ROOT", ROOT.split(os.sep + ".claude" + os.sep)[0])
sys.path.insert(0, TOOLS)
sys.path.insert(0, os.path.join(TOOLS, "part1"))
sys.path.insert(0, os.path.join(TOOLS, "models"))
sys.path.insert(0, HERE)
import havok_convert as hc  # noqa: E402
import ndpak  # noqa: E402

SPEC = os.path.join(HERE, "sp_maps.json")
GAME = os.environ.get("T2R_TLOU2_DIR", r"C:\Games\The Last of Us Part II Remastered")
CACHE = os.environ.get("T2R_LEVEL_EDIT_DIR", os.path.join(MAIN, "re", "maps", "level-edit-cache"))
FLT = np.float32(3.40282e38)            # ND's value for empty simd lanes (not FLT_MAX)
U32 = struct.Struct("<I")


# ============================================================================================== source paks
def world_archives(game=None):
    d = os.path.join(game or GAME, "build", "pc", "main")
    sc = os.path.join(d, "sp-common.psarc")        # levels shared by several chapters (wat-explore-checkpoint, wat-capitol-hill-*-low / -wide, ...), searched last
    return sorted(glob.glob(os.path.join(d, "world-*.psarc"))) + ([sc] if os.path.exists(sc) else [])


def fetch_archives(game=None):
    """world-*.psarc first, then sp-common.psarc (the shared SP levels: afm-scar-island-* = Overpass)"""
    return world_archives(game) + [a for a in [os.path.join(game or GAME, "build", "pc", "main", "sp-common.psarc")] if os.path.exists(a)]


def fetch(level, out_dir, game=None, suffixes=("", "-phys")):
    """copy pak68/<level><suffix>.pak out of the game's world psarc (read only on the install); -> {suffix: path}"""
    import dsar_list
    os.makedirs(out_dir, exist_ok=True)
    got = {}
    import shutil
    import p1_src                       # Part I levels (p1-bookstore) are not in the game's archives: copy them from the converted folder
    if p1_src.is_part1_level(level):
        for s in suffixes:
            src = p1_src.source(level, s)
            if not src:
                raise SystemExit(f"Part I level {level}{s}.pak not found in {p1_src.conv_dir()} (run tools/part1/p1_levelset.py convert, or set T2R_P1_CONV)")
            dst = os.path.join(out_dir, level + s + ".pak")
            if not (os.path.exists(dst) and os.path.getsize(dst) == os.path.getsize(src) and os.path.getmtime(dst) >= os.path.getmtime(src)):
                tmp = "%s.%d.tmp" % (dst, os.getpid())
                shutil.copyfile(src, tmp)                      # a copy, never a link: the cache may be edited in place
                os.replace(tmp, dst)
            got[s] = dst
        return got
    need = [s for s in suffixes if not os.path.exists(os.path.join(out_dir, level + s + ".pak"))]
    for s in suffixes:
        if s not in need:
            got[s] = os.path.join(out_dir, level + s + ".pak")
    if not need:
        return got
    for arc in fetch_archives(game):
        d, ent, bs, bsz = dsar_list.open_files(arc)
        for s in list(need):
            nm = f"pak68/{level}{s}.pak"
            if nm in ent:
                dst = os.path.join(out_dir, level + s + ".pak")
                tmp = "%s.%d.tmp" % (dst, os.getpid())             # (atomic: parallel map builds may fetch the same level)
                open(tmp, "wb").write(dsar_list.extract(d, ent, bs, bsz, nm))
                os.replace(tmp, dst)
                got[s] = dst
                need.remove(s)
        if not need:
            break
    missing = [level + s for s in need]
    if missing:
        raise SystemExit(f"not in any world psarc: {missing}")
    return got


# ================================================================================================== Codec4 tree
def _enc(pmin, pmax, bmin, bmax, margin=1e-3):
    return hc._codec_encode(pmin, pmax, bmin, bmax, margin)


def build_tree4(boxes, dmin, dmax, margin=1e-3):
    """hkcdStaticTree Codec3Axis4 (xyz + 1 data byte; section primitive BVH) over primitive boxes (N,2,3):
    preorder, root xyz 0 (= the section box); data = prim << 1 (leaf) or (right child offset / 2) << 1 | 1."""
    nodes = []
    assert 1 <= len(boxes) <= 128

    def rec(ids, pmin, pmax):
        i = len(nodes)
        nodes.append(None)
        bmin, bmax = boxes[ids, 0].min(0), boxes[ids, 1].max(0)
        if i == 0:
            xyz, nmin, nmax = [0, 0, 0], pmin, pmax
        else:
            xyz, nmin, nmax = _enc(pmin, pmax, bmin, bmax, margin)
        if len(ids) == 1:
            nodes[i] = bytes(xyz) + bytes([int(ids[0]) << 1])
            return
        c = (boxes[ids, 0] + boxes[ids, 1]) / 2
        ax = int(np.argmax(c.max(0) - c.min(0)))
        order = ids[np.argsort(c[:, ax], kind="stable")]
        h = len(order) // 2
        rec(order[:h], nmin, nmax)
        right = len(nodes)
        rec(order[h:], nmin, nmax)
        k = (right - i) // 2
        assert right - i == 2 * k and k < 128
        nodes[i] = bytes(xyz) + bytes([k << 1 | 1])
    rec(np.arange(len(boxes)), dmin, dmax)
    return b"".join(nodes)


def walk_tree4(raw, dmin, dmax):
    """[(prim, node, decoded min, decoded max)] of a Codec3Axis4 section tree"""
    out = []

    def rec(i, pmin, pmax):
        x = raw[4 * i:4 * i + 4]
        nmin, nmax = hc._codec_decode(pmin, pmax, list(x[:3]))
        if x[3] & 1:
            rec(i + 1, nmin, nmax)
            rec(i + 2 * (x[3] >> 1), nmin, nmax)
        else:
            out.append((x[3] >> 1, i, nmin, nmax))
    if len(raw):
        rec(0, dmin, dmax)
    return out


def section_box(s):
    return np.frombuffer(s.dom, np.float32).reshape(2, 4)[:, :3].astype(np.float64)


def check_tree4(m, tol=1e-4):
    """every section's primitive tree: leaves = its prims once, every prim box inside its leaf box, node count 2n-1"""
    bad = {}
    sv = hc.shared_positions(m)
    prims = np.frombuffer(m.prims, np.uint8).reshape(-1, 4)
    dead = set(getattr(m, "_dead_sections", ()))
    for si, s in enumerate(m.sections):
        if si in dead or s.npr == 0:
            continue
        b = section_box(s)
        leaves = walk_tree4(s.nodes, b[0], b[1])
        if sorted(x[0] for x in leaves) != list(range(s.npr)) or len(s.nodes) != 4 * (2 * s.npr - 1):
            bad["section tree leaves != prims"] = bad.get("section tree leaves != prims", 0) + 1
            continue
        V = hc.section_vertices(m, s, sv)
        P = V[prims[s.po:s.po + s.npr].astype(np.int64)]
        pb = np.stack([P.min(1), P.max(1)], 1)
        for pi, node, nmin, nmax in leaves:
            if (pb[pi, 0] < nmin - tol).any() or (pb[pi, 1] > nmax + tol).any():
                bad["prim outside its leaf box"] = bad.get("prim outside its leaf box", 0) + 1
    return bad


# ============================================================================================ mesh editing
def _bits(arr_u32, n):
    b = np.unpackbits(np.asarray(arr_u32, "<u4").view(np.uint8), bitorder="little")
    return b[:n] if len(b) >= n else np.concatenate([b, np.zeros(n - len(b), np.uint8)])


def _tri_sel(m, box, tags=None, mode="inside", not_tags=None):
    """keys of the triangles of mesh m inside box (x0,y0,z0,x1,y1,z1), optionally with these shape tags (and without not_tags)"""
    keys, T, tg = hc.triangles(m)
    lo, hi = np.array(box[:3], float), np.array(box[3:], float)
    if len(T) == 0:
        return np.zeros(0, np.int64), T
    if mode == "centroid":
        c = T.mean(1)
        sel = ((c >= lo) & (c <= hi)).all(1)
    elif mode == "overlap":
        # every triangle that touches the box at all (a doorway clearance volume: whatever stands in it goes, big wall quads included)
        sel = ((T.max(1) >= lo) & (T.min(1) <= hi)).all(1)
        if sel.any():
            ov = tri_box_overlap(T[sel], lo, hi)
            idx = np.nonzero(sel)[0]
            sel = np.zeros(len(T), bool)
            sel[idx[ov]] = True
    else:
        sel = ((T.min(1) >= lo) & (T.max(1) <= hi)).all(1)
    if tags:
        sel &= np.isin(tg, np.array(tags))
    if not_tags:
        sel &= ~np.isin(tg, np.array(not_tags))
    return keys[sel], T[sel]


FLOOR_BAND = 0.4                                    # m: up-facing triangles this close to an instance box bottom are floor, not prop


def _tri_sel_obb(m, insts, margin=0.1, tags=None, keep_floor=True):
    """keys of the triangles of mesh m that lie completely inside the (rotated) local bounding box of a render instance
    (its matrix M: p_world = p_local @ M), grown by margin metres on every side.  For props that stand at an angle
    (a parked truck) where an axis aligned world box would also take the ground and the wall beside it."""
    keys, T, tg = hc.triangles(m)
    if len(T) == 0:
        return np.zeros(0, np.int64), T
    insts = insts if isinstance(insts, (list, tuple)) else [insts]
    sel = np.zeros(len(T), bool)
    for inst in insts:                                     # a triangle inside ANY of the boxes (body + trailer of one truck)
        Mi = np.linalg.inv(inst.M)
        L = (np.concatenate([T, np.ones(T.shape[:2] + (1,))], 2) @ Mi)[:, :, :3]
        lo, hi = inst.lo - margin, inst.hi + margin
        s = ((L.min(1) >= lo) & (L.max(1) <= hi)).all(1)
        if keep_floor and s.any():
            # the floor under a prop lies inside its box too (supermarket: removing 'pat-walls' took ~10 m2 of floor
            # with nothing left below): keep horizontal triangles in the bottom FLOOR_BAND of the box's world extent
            corners = np.array([[x, y, z, 1.0] for x in (lo[0], hi[0]) for y in (lo[1], hi[1]) for z in (lo[2], hi[2])]) @ inst.M
            ybot = corners[:, 1].min()
            nrm = np.cross(T[:, 1] - T[:, 0], T[:, 2] - T[:, 0])
            up = np.abs(nrm[:, 1]) > 0.6 * np.maximum(np.linalg.norm(nrm, axis=1), 1e-12)   # ground up to ~53 deg (rubble); Havok winding points floor normals down
            s &= ~(up & (T[:, :, 1].max(1) <= ybot + FLOOR_BAND))
        sel |= s
    if tags:
        sel &= np.isin(tg, np.array(tags))
    return keys[sel], T[sel]


ORPHAN_MAX_TRIS = 6                                 # a leftover piece this small ...
ORPHAN_MAX_EXT = 2.0                                # ... and this short (m) that touched a removed triangle is a remnant


def orphan_fragments(kall, Tall, removed, dropped):
    """keys of the small collision pieces a removal leaves floating (supermarket: slivers of shelves / boxes the
    removal box did not wholly contain): connected components (shared vertex, 1 mm) of the triangles that stay, with at
    most ORPHAN_MAX_TRIS triangles and ORPHAN_MAX_EXT metres extent, that share a vertex with a removed triangle.
    Pieces made only of horizontal triangles are floor and stay; the partner of a quad half goes with it."""
    if not len(kall) or not removed:
        return []
    V = np.round(np.asarray(Tall, float), 3)
    rem_v = set()
    stay = []
    for i, kk in enumerate(kall):
        if int(kk) in removed:
            rem_v.update(map(tuple, V[i]))
        elif int(kk) not in dropped:
            stay.append(i)
    if not rem_v:
        return []
    touch = [i for i in stay if any(tuple(v) in rem_v for v in V[i])]
    v2t = {}
    for i in stay:
        for v in map(tuple, V[i]):
            v2t.setdefault(v, []).append(i)
    present = {int(kk) for kk in kall}
    out, seen = set(), set()
    for i0 in touch:
        if i0 in seen:
            continue
        comp, j = [i0], 0
        seen.add(i0)
        while j < len(comp) and len(comp) <= ORPHAN_MAX_TRIS:
            for v in map(tuple, V[comp[j]]):
                for n_ in v2t.get(v, ()):
                    if n_ not in seen:
                        seen.add(n_)
                        comp.append(n_)
            j += 1
        if len(comp) > ORPHAN_MAX_TRIS:
            continue
        C = np.asarray(Tall, float)[comp]
        if np.ptp(C.reshape(-1, 3), axis=0).max() > ORPHAN_MAX_EXT:
            continue
        nn = np.cross(C[:, 1] - C[:, 0], C[:, 2] - C[:, 0])
        if (np.abs(nn[:, 1]) > 0.6 * np.maximum(np.linalg.norm(nn, axis=1), 1e-12)).all():
            continue                                        # floor / step pieces
        for i in comp:
            kk = int(kall[i])
            out.add(kk)
            if (kk ^ 1) in present and (kk ^ 1) not in dropped:
                out.add(kk ^ 1)
    return sorted(out)


def _simd_patch(raw, keymap, drop):
    """simd tree: leaf lanes of dropped keys become empty lanes, the leaf data of moved keys is renumbered"""
    raw = bytearray(raw)
    n = len(raw) // 112
    for i in range(n):
        o = 112 * i
        data = list(struct.unpack_from("<4I", raw, o + 96))
        for j in range(4):
            if data[j] & 1:
                k = data[j] >> 1
                if k in drop:
                    for r in range(6):
                        struct.pack_into("<f", raw, o + (r * 4 + j) * 4, float(FLT if r % 2 == 0 else -FLT))
                    data[j] = 0
                elif k in keymap and keymap[k] != k:
                    data[j] = keymap[k] << 1 | 1
        struct.pack_into("<4I", raw, o + 96, *data)
    return bytes(raw)


def remove_keys(m, drop):
    """Mesh without the triangles `drop` (old shape keys).  Returns (new Mesh, keymap {old key: new key} of every
    surviving triangle whose key changed, set of changed sections).  Vertex arrays, trees of untouched sections and the
    section tree (unless a section empties) stay as ND built them; touched sections get fresh primitive trees."""
    drop = {int(k) for k in drop}
    n = copy.deepcopy(m)
    prims = np.frombuffer(m.prims, np.uint8).reshape(-1, 4)
    runs = np.frombuffer(m.runs, np.uint8).reshape(-1, 4)
    sv = hc.shared_positions(m)
    by = {}
    for k in drop:
        by.setdefault(k >> 8, set()).add(k)
    # ND's run table is shared between sections (identical ranges are reused), so it is never rewritten in place:
    # a touched section gets fresh runs appended at the end, the old entries stay (still used or dead).
    runs_w = runs.copy()
    share = np.zeros(len(runs), np.int64)
    for s in m.sections:
        share[s.ro:s.ro + s.nru] += 1
    pr_out, ru_out, keymap, dead = [], [], {}, []
    po, ro = 0, len(runs)
    for si, s in enumerate(m.sections):
        t = n.sections[si]
        t.po = po
        sp = prims[s.po:s.po + s.npr]
        sr = runs[s.ro:s.ro + s.nru]
        if si not in by:
            pr_out.append(sp)
            po += len(sp)
            continue
        private = bool((share[s.ro:s.ro + s.nru] == 1).all())
        newp, pmap = [], {}
        for p, (a, b, c, d) in enumerate(sp):
            k0 = si << 8 | p << 1
            quad = c != d
            keep0 = k0 not in drop
            keep1 = quad and (k0 | 1) not in drop
            q = len(newp)
            if not quad:
                if keep0:
                    newp.append((a, b, c, d))
                    pmap[p] = q
                    keymap[k0] = si << 8 | q << 1
            elif keep0 and keep1:
                newp.append((a, b, c, d))
                pmap[p] = q
                keymap[k0] = si << 8 | q << 1
                keymap[k0 | 1] = si << 8 | q << 1 | 1
            elif keep0:
                newp.append((a, b, c, c))
                pmap[p] = q
                keymap[k0] = si << 8 | q << 1
            elif keep1:
                newp.append((a, c, d, d))
                pmap[p] = q
                keymap[k0 | 1] = si << 8 | q << 1
        newr = []
        for r in sr:
            first, cnt = int(r[2]), int(r[3])
            keep = [pmap[p] for p in range(first, first + cnt) if p in pmap]
            if keep:
                newr.append((r[0], r[1], keep[0], len(keep)))
        t.npr, t.nru = len(newp), len(newr)
        pa = np.array(newp, np.uint8).reshape(-1, 4)
        pr_out.append(pa)
        ra = np.array(newr, np.uint8).reshape(-1, 4)
        if private:                                  # rewrite the section's own run slots, the tail stays unused
            runs_w[s.ro:s.ro + len(ra)] = ra
            t.ro = s.ro
        else:
            ru_out.append(ra)
            t.ro = ro
            ro += len(ra)
        po += len(pa)
        if len(newp):
            V = hc.section_vertices(m, s, sv)
            P = V[pa.astype(np.int64)]
            b = section_box(s)
            t.nodes = build_tree4(np.stack([P.min(1), P.max(1)], 1), b[0], b[1])
        else:
            t.nodes = b""
            dead.append(si)
    n.prims = np.concatenate(pr_out).astype(np.uint8).tobytes() if pr_out else b""
    n.runs = np.concatenate([runs_w] + ru_out).astype(np.uint8).tobytes()
    changed = set(by)
    keys_new, _, _ = hc.triangles(n)
    n.npk = m.npk + len(keys_new) - len(hc.triangles(m)[0])      # ND's numPrimitiveKeys is not always the triangle count (+4 in one item here): keep its offset
    n.maxkey = int(keys_new.max()) if len(keys_new) else 0
    n.nbits = n.maxkey + 1
    # interior-triangle bit field
    nw = (n.nbits + 31) // 32
    old = _bits(m.words, 32 * len(m.words))
    new = np.zeros(nw * 32, np.uint8)
    keep_mask = np.ones(len(old), bool)
    for si in changed:                              # keys of touched sections are re-assigned below
        keep_mask[si << 8:min((si << 8) + 256, len(old))] = False
    kk = np.nonzero(keep_mask[:len(new)])[0]
    new[kk] = old[kk]
    for ok, nk in keymap.items():
        if ok < len(old):
            new[nk] = old[ok]
    n.words = np.packbits(new, bitorder="little").view("<u4").astype(np.uint32)
    n.simd = _simd_patch(m.simd, keymap, drop)
    n._keymap_changed = {si for si in changed}
    n._dead_sections = dead
    if dead:                                # a section lost every primitive: it leaves the section tree
        _tree5_without(n, dead)
    return n, keymap, changed


def _tree5_without(n, dead):
    live = [i for i in range(len(n.sections)) if i not in set(dead)]
    boxes = np.array([section_box(n.sections[i]) for i in live])
    dmin, dmax = n.domain()
    tree, leaf_of = hc.build_tree5(boxes, dmin, dmax)
    # build_tree5 numbers leaves by position in `boxes`: remap to section indices
    out = bytearray(tree)
    for k in range(len(out) // 5):
        x = out[5 * k:5 * k + 5]
        if not x[3] & 0x80:
            data = (x[3] & 0x7F) << 8 | x[4]
            out[5 * k + 3], out[5 * k + 4] = live[data] >> 8, live[data] & 255
    n.tree5 = bytes(out)
    for pos, si in enumerate(live):
        n.sections[si].leaf = leaf_of[pos]
    for si in dead:
        n.sections[si].leaf = 0


def remap_key_table(blob, nbits_old, keymap, drop, changed, stride=3):
    """ND's per-shape-key table (3 bits per key, materialTable) for the new numbering"""
    old = np.unpackbits(np.frombuffer(blob, np.uint8), bitorder="little")
    new = old.copy()
    vals = {}
    for ok, nk in keymap.items():
        vals[nk] = old[stride * ok:stride * ok + stride].copy()
    for si in changed:
        lo_k, hi_k = si << 8, min((si << 8) + 256, len(old) // stride)
        new[stride * lo_k:stride * hi_k] = 0
    for nk, v in vals.items():
        new[stride * nk:stride * nk + stride] = v
    return np.packbits(new, bitorder="little").tobytes()[:len(blob)]


def tri_attrs(m, keys):
    """(tag, interior bit) of the given shape keys"""
    k, T, tg = hc.triangles(m)
    pos = {int(a): i for i, a in enumerate(k)}
    words = _bits(m.words, 32 * len(m.words))
    return [(int(tg[pos[int(x)]]), int(words[int(x)]) if int(x) < len(words) else 0) for x in keys]


def add_triangles(m, tris, attrs, blob_vals, blob):
    """Append `tris` (N,3,3 world) as new sections (shared vertices quantised over the mesh domain, 1 prim per triangle,
    <=100 prims / <=250 vertices per section).  attrs = [(tag, interior bit)], blob_vals = [3 bit value per triangle].
    The section tree gets one new root per added section, the simd tree one new subtree; keys of existing triangles
    do not change.  Returns (new Mesh, new blob bytes, [new keys])."""
    n = copy.deepcopy(m)
    dmin, dmax = n.domain()
    tris = np.asarray(tris, float)
    if len(tris) == 0:
        return n, blob, []
    if (tris.reshape(-1, 3).min(0) < dmin - 1e-3).any() or (tris.reshape(-1, 3).max(0) > dmax + 1e-3).any():
        raise ValueError("moved triangles leave the mesh domain %s .. %s" % (np.round(dmin, 2), np.round(dmax, 2)))
    nokey = len(n.sections)
    order = np.lexsort((tris.mean(1)[:, 2], tris.mean(1)[:, 0]))
    chunks, cur = [], []
    for i in order:
        if len(cur) >= 100:
            chunks.append(cur)
            cur = []
        cur.append(int(i))
    chunks.append(cur)
    new_keys = []
    ext = np.where(dmax > dmin, dmax - dmin, 1.0)
    maxq = np.array([0x1FFFFF, 0x1FFFFF, 0x3FFFFF], float)
    nocodec = next((s.codec for s in n.sections if s.npv == 0), None)
    assert nocodec is not None, "no section without packed vertices to copy the codec block from"
    words = _bits(n.words, 32 * len(n.words))
    blob_bits = np.unpackbits(np.frombuffer(blob, np.uint8), bitorder="little")
    sec_boxes = []
    all_prims = [np.frombuffer(n.prims, np.uint8).reshape(-1, 4)]
    all_runs = [np.frombuffer(n.runs, np.uint8).reshape(-1, 4)]
    po = len(all_prims[0])
    ro = len(all_runs[0])
    shared = [n.shared]
    svi = [n.svi]
    nsh_total = len(n.shared)
    nsvi = len(n.svi)
    simd_subs = []
    for ch in chunks:
        S = len(n.sections)
        if S >= 1 << (n.keybits - 8):
            raise ValueError("no free section slot for new keys (%d bits)" % n.keybits)
        P = tris[ch]
        q = np.clip(np.rint((P.reshape(-1, 3) - dmin) / ext * maxq), 0, maxq).astype(np.int64)
        uq, inv = np.unique(q, axis=0, return_inverse=True)
        inv = inv.reshape(-1)
        if len(uq) > 250:
            raise ValueError("section vertex budget exceeded")
        qq = uq.astype(np.uint64)
        sh = (qq[:, 0] | qq[:, 1] << np.uint64(21) | qq[:, 2] << np.uint64(42)).astype(np.uint64)
        dq = dmin + uq / maxq * ext                     # decoded (what Havok sees)
        pr = np.zeros((len(ch), 4), np.uint8)
        idx = inv.reshape(-1, 3)
        pr[:, 0], pr[:, 1], pr[:, 2], pr[:, 3] = idx[:, 0], idx[:, 1], idx[:, 2], idx[:, 2]
        boxes = np.stack([dq[idx].min(1), dq[idx].max(1)], 1)
        sb = np.stack([dq.min(0) - 1e-4, dq.max(0) + 1e-4])
        sb = np.minimum(np.maximum(sb, dmin), dmax)
        dom = np.zeros(8, np.float32)
        dom[0:3], dom[4:7] = sb[0], sb[1]
        # runs: consecutive equal tags
        rn = []
        for j, ti in enumerate(ch):
            tg = attrs[ti][0]
            if rn and rn[-1][0] == tg:
                rn[-1][2] += 1
            else:
                rn.append([tg, j, 1])
        ra = np.array([[tg & 255, tg >> 8, first, cnt] for tg, first, cnt in rn], np.uint8).reshape(-1, 4)
        sec = hc.Section(nodes=build_tree4(boxes, sb[0].astype(np.float32).astype(float), sb[1].astype(np.float32).astype(float)),
                         dom=dom.tobytes(), codec=nocodec, fp=0, so=nsvi, nsh=len(uq), shlow=0, po=po, npr=len(ch),
                         ro=ro, nru=len(ra), npv=0, leaf=0, tail=bytes(4))
        n.sections.append(sec)
        shared.append(sh)
        svi.append(np.arange(nsh_total, nsh_total + len(uq), dtype=np.uint16))
        nsh_total += len(uq)
        nsvi += len(uq)
        all_prims.append(pr)
        all_runs.append(ra)
        po += len(pr)
        ro += len(ra)
        keys = [S << 8 | j << 1 for j in range(len(ch))]
        for j, ti in enumerate(ch):
            new_keys.append(keys[j])
            if keys[j] >= len(words):
                words = np.concatenate([words, np.zeros(((keys[j] // 32 + 1) * 32) - len(words), np.uint8)])
            words[keys[j]] = attrs[ti][1]
            if 3 * keys[j] + 3 > len(blob_bits):           # new keys past the old per-key table (a moved prop re-added in new sections)
                blob_bits = np.concatenate([blob_bits, np.zeros(((3 * keys[j] + 3 + 7) // 8) * 8 - len(blob_bits), np.uint8)])
            blob_bits[3 * keys[j]:3 * keys[j] + 3] = [(blob_vals[ti] >> b) & 1 for b in range(3)]
        simd_subs.append((boxes, keys))
        sec_boxes.append(sb)
    n.shared = np.concatenate(shared).astype(np.uint64)
    n.svi = np.concatenate(svi).astype(np.uint16)
    n.prims = np.concatenate(all_prims).astype(np.uint8).tobytes()
    n.runs = np.concatenate(all_runs).astype(np.uint8).tobytes()
    # section tree: a new root per added section (old tree becomes the left child, nodes shift by one)
    t5 = n.tree5
    for k, sb in enumerate(sec_boxes):
        si = nokey + k
        nn = len(t5) // 5
        assert nn % 2 == 1, "section tree has an even node count"
        xyz, _, _ = hc._codec_encode(dmin, dmax, sb[0], sb[1], 1e-3)
        leaf = bytes(xyz) + struct.pack(">H", si)
        root = bytes([0, 0, 0]) + struct.pack(">H", 0x8000 | (nn + 1) // 2)
        t5 = root + t5 + leaf
        for s in n.sections[:si]:
            s.leaf += 1
        n.sections[si].leaf = nn + 1
    n.tree5 = t5
    # simd tree: append a subtree per new section and hang it on the root
    simd = bytearray(n.simd)
    for boxes, keys in simd_subs:
        sub = hc.build_simd(boxes, np.array(keys, np.int64))
        base = len(simd) // 112
        cnt = len(sub) // 112
        sub = bytearray(sub)
        for i in range(1, cnt):                         # node 0 of the sub tree is its empty node: dropped
            o = 112 * i
            data = list(struct.unpack_from("<4I", sub, o + 96))
            for j in range(4):
                if data[j] and not data[j] & 1:
                    data[j] = (base + data[j] // 2 - 1) << 1
            struct.pack_into("<4I", sub, o + 96, *data)
        simd += sub[112:]
        sroot = base
        lo = boxes.reshape(-1, 3).min(0) - 1e-4
        hi = boxes.reshape(-1, 3).max(0) + 1e-4
        simd = _simd_attach(simd, sroot, lo, hi)
    n.simd = bytes(simd)
    n.words = np.packbits(np.concatenate([words, np.zeros((-len(words)) % 32, np.uint8)]), bitorder="little").view("<u4").astype(np.uint32)
    k_all = hc.triangles(n)[0]
    n.npk = m.npk + len(new_keys)
    n.maxkey = int(k_all.max())
    n.nbits = n.maxkey + 1
    need = (n.nbits + 31) // 32
    w = np.zeros(need * 32, np.uint8)
    w[:min(len(words), len(w))] = words[:len(w)]
    n.words = np.packbits(w, bitorder="little").view("<u4").astype(np.uint32)
    return n, np.packbits(blob_bits, bitorder="little").tobytes()[:max(len(blob), (3 * (n.maxkey + 1) + 7) // 8)], new_keys


# ===================================================================== move collision triangles IN PLACE (same size)
def _refit_codec_tree(raw, stride, root_min, root_max, leaf_box, old_root=None, margin=1e-3):
    """Refit a Codec3Axis4 (stride 4) / Codec3Axis5 (stride 5) static tree to new leaf boxes, keeping ND's topology and node
    count.  leaf_box(leaf data) -> (min, max, changed).  Nodes whose subtree did not change and whose parent box is unchanged
    keep their bytes.  root_min / root_max: the new root box (section box / mesh domain); old_root: the old one."""
    raw = bytearray(raw)
    n = len(raw) // stride
    if n == 0:
        return bytes(raw)

    def node(i):
        x = raw[stride * i:stride * i + stride]
        if stride == 4:
            return list(x[:3]), bool(x[3] & 1), x[3] >> 1
        d = (x[3] & 0x7F) << 8 | x[4]
        return list(x[:3]), bool(x[3] & 0x80), d
    box, chg = {}, {}

    def up(i):                                          # pass 1: union boxes + changed flags, bottom-up
        _, inner, d = node(i)
        if inner:
            a, b = up(i + 1), up(i + 2 * d)
            box[i] = (np.minimum(a[0], b[0]), np.maximum(a[1], b[1]))
            chg[i] = chg[i + 1] or chg[i + 2 * d]
        else:
            lo, hi, c = leaf_box(d)
            box[i] = (np.asarray(lo, float), np.asarray(hi, float))
            chg[i] = bool(c)
        return box[i]
    up(0)
    old_root = (root_min, root_max) if old_root is None else old_root

    def down(i, pmin, pmax, opmin, opmax, parent_same):  # pass 2: re-encode top-down where the box or the parent changed
        xyz, inner, d = node(i)
        omin, omax = hc._codec_decode(opmin, opmax, xyz) if i else (opmin, opmax)
        if i == 0:
            nmin, nmax, same = pmin, pmax, parent_same
        elif parent_same and not chg[i]:
            nmin, nmax, same = omin, omax, True
        else:
            xyz2, nmin, nmax = hc._codec_encode(pmin, pmax, box[i][0], box[i][1], margin)
            raw[stride * i:stride * i + 3] = bytes(xyz2)
            same = False
        if inner:
            down(i + 1, nmin, nmax, omin, omax, same)
            down(i + 2 * d, nmin, nmax, omin, omax, same)
    rmin, rmax = np.asarray(root_min, float), np.asarray(root_max, float)
    omin, omax = np.asarray(old_root[0], float), np.asarray(old_root[1], float)
    down(0, rmin, rmax, omin, omax, bool(np.allclose(rmin, omin, rtol=0, atol=1e-9) and np.allclose(rmax, omax, rtol=0, atol=1e-9)))
    return bytes(raw)


def close_selection(m, keys, inside, max_rounds=8):
    """Grow a collision selection to whole primitives and to the primitives that share vertices with it, as long as the
    added triangles pass inside(T (N,3,3)) -> bool mask (a looser box around the prop).  A prop's collision is one
    connected piece; the tight oriented box of its render parts misses slivers (a mirror, a bumper corner) whose vertices
    the selected triangles share, and those would otherwise force the remove + add path.  -> sorted keys"""
    sel = {int(k) for k in keys}
    prims = np.frombuffer(m.prims, np.uint8).reshape(-1, 4)
    sv = hc.shared_positions(m)
    users, refs, tri = {}, {}, {}
    for si, s in enumerate(m.sections):
        nv = s.npv + s.nsh
        V = None
        for p in range(s.npr):
            a, b, c, d = (int(v) for v in prims[s.po + p])
            if max(a, b, c, d) >= nv:
                continue
            if V is None:
                V = hc.section_vertices(m, s, sv)
            k0 = si << 8 | p << 1
            ks = [k0] + ([k0 | 1] if c != d else [])
            gl = set()
            for v in {a, b, c, d}:
                gid = ("p", si, v) if v < s.npv else ("s", int(m.svi[s.so + v - s.npv]))
                gl.add(gid)
                users.setdefault(gid, set()).add((si, p))
            refs[(si, p)] = (gl, ks)
            tri[k0] = V[[a, b, c]]
            if c != d:
                tri[k0 | 1] = V[[a, c, d]]
    for _ in range(max_rounds):
        cand = set()
        for (si, p), (gl, ks) in refs.items():
            if any(k in sel for k in ks):
                cand.update(k for k in ks if k not in sel)          # the rest of a half-selected quad
                for gid in gl:
                    for sp in users[gid]:
                        cand.update(k for k in refs[sp][1] if k not in sel)
        if not cand:
            break
        cl = sorted(cand)
        ok = inside(np.array([tri[k] for k in cl]))
        add = {k for k, o in zip(cl, ok) if o}
        if not add:
            break
        sel |= add
    return sorted(sel)


def shrink_kept_triangle(m, si, size=0.02, reach=1.5):
    """Section si of mesh m holds exactly one primitive (a triangle kept so that the section does not leave the section tree), e.g. a
    shelf sliver left where a removed prop stood: players got stuck on it.  Park it where it blocks nothing new: the triangle is
    moved IN PLACE (move_in_place: boxes, primitive / section / simd trees refitted, tags and bits untouched) to a tiny triangle
    (legs ~size m) lying in the plane of an EXISTING wall / ceiling / floor triangle of another section, at the point of that
    triangle nearest to the old one (within `reach` m).  The surface already blocks there, so the kept triangle adds no obstacle in
    open space.  -> (new mesh, old area, new area, centre) or None (already a speck, its vertices are shared with other
    primitives, or no surface within reach: left as is)"""
    s = m.sections[si]
    if s.npr != 1:
        return None
    prims = np.frombuffer(m.prims, np.uint8).reshape(-1, 4)
    a, b, c, d = (int(v) for v in prims[s.po])
    if len({a, b, c}) != 3 or c != d or max(a, b, c) >= s.npv + s.nsh or min(a, b, c) < s.npv:
        return None
    sv = hc.shared_positions(m)
    V = hc.section_vertices(m, s, sv)
    T0 = V[[a, b, c]]
    area0 = 0.5 * float(np.linalg.norm(np.cross(T0[1] - T0[0], T0[2] - T0[0])))
    if area0 <= 3e-4:                                    # already a stock-sized speck
        return None
    cen = T0.mean(0)
    keys, TT, _tg = hc.triangles(m)
    other = (np.asarray(keys) >> 8) != si
    cross = np.cross(TT[:, 1] - TT[:, 0], TT[:, 2] - TT[:, 0])
    area = 0.5 * np.linalg.norm(cross, axis=1)
    near = other & (area > 0.02) & (TT.max(1) >= cen - reach).all(1) & (TT.min(1) <= cen + reach).all(1)
    best = None
    for ti in np.nonzero(near)[0]:
        Tn = TT[ti]
        nrm = cross[ti] / (2 * area[ti])
        e1, e2 = Tn[1] - Tn[0], Tn[2] - Tn[0]
        l1, l2 = np.linalg.norm(e1), np.linalg.norm(e2)
        if min(l1, l2) < 0.1:
            continue
        M2 = np.array([e1, e2]).T
        uv = np.linalg.lstsq(M2, cen - Tn[0] - nrm * float((cen - Tn[0]) @ nrm), rcond=None)[0]
        uv = np.clip(uv, 0.03, 0.9)                        # nearest point kept inside the triangle, off its edges
        if uv[0] + uv[1] > 0.93:
            uv = uv * 0.93 / (uv[0] + uv[1])
        p = Tn[0] + uv[0] * e1 + uv[1] * e2
        q1, q2 = p + e1 / l1 * size, p + e2 / l2 * size
        ok = True
        for X in (q1, q2):
            w = np.linalg.lstsq(M2, X - Tn[0], rcond=None)[0]
            if w[0] < 0.005 or w[1] < 0.005 or w[0] + w[1] > 0.995:
                ok = False
        dist = float(np.linalg.norm(p - cen))
        if ok and dist <= reach and (best is None or dist < best[0]):
            best = (dist, np.array([p, q1, q2]))
    if best is None:
        return None
    key = si << 8
    gs = sorted({int(m.svi[s.so + v - s.npv]) for v in (a, b, c)})
    if len(gs) != 3:
        return None
    n2, moved, rest = move_in_place(m, [key], lambda P: best[1][:len(P)])
    if not moved:
        return None
    sv2 = hc.shared_positions(n2)
    P2 = sv2[gs]
    area1 = 0.5 * float(np.linalg.norm(np.cross(P2[1] - P2[0], P2[2] - P2[0])))
    return n2, area0, area1, P2.mean(0)


def move_in_place(m, keys, fn):
    """Transform the collision triangles `keys` of mesh m with fn ((N,3) -> (N,3)) WITHOUT re-adding them: their shared
    vertices are re-quantised where they are, the touched sections' boxes / primitive trees, the section tree and the
    simd tree are refitted (ND's topology kept), so the tagfile keeps its size and every shape key, tag, interior bit
    and material bit stays as it was.  Possible for a primitive when all its triangles are selected, it uses only shared
    vertices and none of those vertices is used by an unselected primitive.
    -> (new mesh, [keys moved in place], [selected keys that need the remove + add path])"""
    sel = {int(k) for k in keys}
    n = copy.deepcopy(m)
    prims = np.frombuffer(m.prims, np.uint8).reshape(-1, 4)
    users = {}                                          # shared vertex -> set of (section, prim)
    prim_refs = {}                                      # (section, prim) -> (shared vertex ids, uses packed, quad)
    for si, s in enumerate(m.sections):
        nv = s.npv + s.nsh
        for p in range(s.npr):
            a, b, c, d = (int(v) for v in prims[s.po + p])
            if max(a, b, c, d) >= nv:
                continue
            g, packed = set(), False
            for v in {a, b, c, d}:
                if v < s.npv:
                    packed = True
                else:
                    gi = int(m.svi[s.so + v - s.npv])
                    g.add(gi)
                    users.setdefault(gi, set()).add((si, p))
            prim_refs[(si, p)] = (g, packed, c != d)
    full = set()
    for (si, p), (g, packed, quad) in prim_refs.items():
        k0 = si << 8 | p << 1
        if k0 in sel and (not quad or (k0 | 1) in sel):
            full.add((si, p))
    ok = set()
    for sp in full:
        g, packed, _ = prim_refs[sp]
        if not packed and all(users[gi] <= full for gi in g):
            ok.add(sp)
    moved_keys = sorted(k for k in sel if ((k >> 8), (k & 0xFF) >> 1) in ok)
    rest = sorted(sel - set(moved_keys))
    if not ok:
        return n, [], rest
    gs = sorted({gi for sp in ok for gi in prim_refs[sp][0]})
    sv = hc.shared_positions(m)
    P = fn(sv[gs])
    dmin, dmax = m.domain()
    if (P < dmin - 1e-4).any() or (P > dmax + 1e-4).any():
        raise ValueError("moved collision leaves the mesh domain %s .. %s" % (np.round(dmin, 2), np.round(dmax, 2)))
    ext = np.where(dmax > dmin, dmax - dmin, 1.0)
    maxq = np.array([0x1FFFFF, 0x1FFFFF, 0x3FFFFF], float)
    q = np.clip(np.rint((P - dmin) / ext * maxq), 0, maxq).astype(np.uint64)
    sh = n.shared.astype(np.uint64).copy()
    sh[gs] = q[:, 0] | q[:, 1] << np.uint64(21) | q[:, 2] << np.uint64(42)
    n.shared = sh
    gset = set(gs)
    sv2 = hc.shared_positions(n)
    sec_changed = set()
    for si, s in enumerate(n.sections):
        if s.nsh and gset.intersection(int(x) for x in n.svi[s.so:s.so + s.nsh]):
            sec_changed.add(si)
    for si in sorted(sec_changed):
        s = n.sections[si]
        V = hc.section_vertices(n, s, sv2)
        old = np.frombuffer(s.dom, np.float32).reshape(2, 4).copy()
        old_box = old[:, :3].astype(np.float64)
        lo = np.nextafter((V.min(0) - 1e-4).astype(np.float32), np.float32(-np.inf))
        hi = np.nextafter((V.max(0) + 1e-4).astype(np.float32), np.float32(np.inf))
        lo = np.maximum(lo, dmin.astype(np.float32))
        hi = np.minimum(hi, dmax.astype(np.float32))
        dom = old.copy()
        dom[0, :3], dom[1, :3] = lo, hi
        s.dom = dom.astype(np.float32).tobytes()
        nb = dom[:, :3].astype(np.float64)
        nv = s.npv + s.nsh
        pr = prims[s.po:s.po + s.npr].astype(np.int64)
        okp = (pr < nv).all(1)
        pb = np.zeros((s.npr, 2, 3))
        if okp.any():
            pb[okp, 0] = V[pr[okp]].min(1)
            pb[okp, 1] = V[pr[okp]].max(1)
        pb[~okp] = old_box                              # ND filler primitive (never hit): keep it inside the old box
        moved_p = {p for (sj, p) in ok if sj == si}
        s.nodes = _refit_codec_tree(s.nodes, 4, nb[0], nb[1],
                                    lambda d, pb=pb, mp=moved_p: (pb[d, 0], pb[d, 1], d in mp), old_root=(old_box[0], old_box[1]))

    def sec_leaf(d):
        b = np.frombuffer(n.sections[d].dom, np.float32).reshape(2, 4)[:, :3].astype(np.float64)
        return b[0], b[1], d in sec_changed
    n.tree5 = _refit_codec_tree(n.tree5, 5, dmin, dmax, sec_leaf)
    # simd tree: lanes on the path to a moved primitive get the new boxes, every other lane keeps ND's floats
    pbox = {}
    for si in sec_changed:
        s = n.sections[si]
        V = hc.section_vertices(n, s, sv2)
        nv = s.npv + s.nsh
        for p in range(s.npr):
            r = prims[s.po + p].astype(np.int64)
            if (r < nv).all():
                pbox[si << 8 | p << 1] = (V[r].min(0), V[r].max(0))
    movedp = {si << 8 | p << 1 for si, p in ok}
    simd = bytearray(n.simd)

    def refit(i):
        f = np.frombuffer(bytes(simd[112 * i:112 * i + 96]), np.float32).reshape(6, 4).copy()
        data = struct.unpack_from("<4I", simd, 112 * i + 96)
        lo_all, hi_all, any_c = np.full(3, np.inf), np.full(3, -np.inf), False
        for j in range(4):
            if f[0, j] > f[1, j]:
                continue
            if data[j] & 1:
                k = data[j] >> 1
                c = k in movedp
                if c:
                    lo, hi = pbox[k]
            else:
                lo, hi, c = refit(data[j] >> 1)
            if c:
                f[0::2, j] = np.nextafter((np.asarray(lo) - 1e-4).astype(np.float32), np.float32(-np.inf))
                f[1::2, j] = np.nextafter((np.asarray(hi) + 1e-4).astype(np.float32), np.float32(np.inf))
                any_c = True
            lo_all = np.minimum(lo_all, f[0::2, j].astype(np.float64))
            hi_all = np.maximum(hi_all, f[1::2, j].astype(np.float64))
        if any_c:
            simd[112 * i:112 * i + 96] = f.astype(np.float32).tobytes()
        return lo_all, hi_all, any_c
    if len(simd) // 112 > 1:
        refit(1)
    n.simd = bytes(simd)
    return n, moved_keys, rest


def _lane_box(raw, o, j):
    f = np.frombuffer(raw, np.float32, 24, o).reshape(6, 4)
    return f[0::2, j].astype(np.float64), f[1::2, j].astype(np.float64)


def _simd_attach(simd, child, lo, hi):
    """hang node `child` on the simd root (node 1): in a free lane, else the old root moves to a new node"""
    simd = bytearray(simd)
    o = 112
    data = list(struct.unpack_from("<4I", simd, o + 96))
    free = [j for j in range(4) if data[j] == 0 and _lane_box(simd, o, j)[0][0] > _lane_box(simd, o, j)[1][0]]

    def setlane(buf, off, j, mn, mx, d):
        for r in range(3):
            struct.pack_into("<f", buf, off + ((2 * r) * 4 + j) * 4, float(np.nextafter(np.float32(mn[r]), np.float32(-np.inf))))
            struct.pack_into("<f", buf, off + ((2 * r + 1) * 4 + j) * 4, float(np.nextafter(np.float32(mx[r]), np.float32(np.inf))))
        dd = list(struct.unpack_from("<4I", buf, off + 96))
        dd[j] = d
        struct.pack_into("<4I", buf, off + 96, *dd)
    if free:
        setlane(simd, o, free[0], lo, hi, child << 1)
        return simd
    # push the root down: copy it to a new node X, root = {X, child}
    x = len(simd) // 112
    simd += simd[o:o + 112]
    boxes = [_lane_box(simd, o, j) for j in range(4) if data[j]]
    ulo = np.min([b[0] for b in boxes], 0)
    uhi = np.max([b[1] for b in boxes], 0)
    empty = bytearray(112)
    for r in range(6):
        for j in range(4):
            struct.pack_into("<f", empty, (r * 4 + j) * 4, float(FLT if r % 2 == 0 else -FLT))
    simd[o:o + 112] = empty
    setlane(simd, o, 0, ulo, uhi, x << 1)
    setlane(simd, o, 1, lo, hi, child << 1)
    return simd


# ======================================================================================== phys pak (in place)
class PhysItem:
    def __init__(self, pak, name, io):
        self.pak, self.name, self.io = pak, name, io
        b = io + 48
        self.ver, self.kind, _, self.tsz = struct.unpack_from("<4I", pak.d, b)
        self.nbits, self.nrec = struct.unpack_from("<II", pak.d, b + 56)
        self.tag_off = pak.ptr(b + 16)
        self.blob_off = pak.ptr(b + 64)
        self.raw = bytes(pak.d[self.tag_off:self.tag_off + self.tsz])
        self.blob = bytes(pak.d[self.blob_off:self.blob_off + (self.nbits + 7) // 8])
        self.tag = hc.havok_tag.Tag.parse(self.raw)
        self.mesh = hc.t2_mesh(self.tag)


def phys_items(path):
    p = ndpak.Pak(path)
    return p, [PhysItem(p, n, io) for n, t, pi, io in p.items if t == "COLLISION_DATA_HAVOK_BG"]


RELOCATE = os.environ.get("T2R_NO_RELOCATE", "") != "1"


class PakBuf(bytearray):
    """a pak under edit.  Tagfiles that outgrow a shared page are queued in `queue` as pages of their own (relocate_tag); bytes(buf) lays them out:
    the page table grows by 12 bytes per page (everything after it shifts, header +4 / +28 and the fixup table's data pointer follow, exactly like
    mesh_replace.replace does for appended pages) and the pages are appended behind the last one."""
    queue = None

    def __init__(self, *a):
        super().__init__(*a)
        self.queue = []

    def __bytes__(self):
        if not self.queue:
            return bytes(memoryview(self))
        return _layout(self)


def _layout(buf):
    d = bytearray(bytes(memoryview(buf)))
    n, pt, ft = struct.unpack_from("<III", d, 16)[0], struct.unpack_from("<I", d, 20)[0], struct.unpack_from("<I", d, 28)[0]
    assert struct.unpack_from("<I", d, 32)[0] == 0, "pak with a trailer: relocation not supported"
    k = len(buf.queue)
    growth = 12 * k
    end = len(d)
    pages_new = []
    cur = end
    for pg in buf.queue:
        pages_new.append((cur + growth, len(pg)))
        cur += len(pg)
    struct.pack_into("<I", d, 4, struct.unpack_from("<I", d, 4)[0] + growth)
    struct.pack_into("<I", d, 16, n + k)
    struct.pack_into("<I", d, 28, ft + growth)
    fdo = struct.unpack_from("<I", d, ft + 4)[0]
    struct.pack_into("<I", d, ft + 4, fdo + growth)
    for i in range(n):
        e = pt + 12 * i
        struct.pack_into("<I", d, e, struct.unpack_from("<I", d, e)[0] + growth)
    out = bytearray(d[:ft])
    for st, sz in pages_new:
        out += struct.pack("<III", st, sz, 0)
    out += d[ft:end]
    assert len(out) == end + growth
    for pg in buf.queue:
        out += pg
    return bytes(out)


def relocate_tag(buf, it, tag):
    """the tagfile `tag` of item `it` into a page of its own (queued in buf.queue): 0x20 header like the 0x100-kind pages of -phys paks, the tagfile
    at +0x20, the 0x20 name pool behind it; the item's tag pointer + its fixup entry (source page, destination page) are repointed in place, the
    old tagfile bytes stay where they are (dead).  Nothing in the file moves until bytes(buf)."""
    d = buf
    n = struct.unpack_from("<I", d, 16)[0]
    pt, ft = struct.unpack_from("<I", d, 20)[0], struct.unpack_from("<I", d, 28)[0]
    pages = [struct.unpack_from("<III", d, pt + 12 * i) for i in range(n)]
    a = it.io + 48 + 16                                   # the tag pointer slot of the item record
    sp = next(i for i, (s0, z, f) in enumerate(pages) if s0 <= a < s0 + z)
    so = a - pages[sp][0]
    fd, fc = struct.unpack_from("<I", d, ft + 4)[0], struct.unpack_from("<I", d, ft + 8)[0]
    ent = None
    for i in range(fc):
        s_, dp_, o_ = struct.unpack_from("<HHI", d, fd + 8 * i)
        if s_ == sp and o_ == so:
            ent = fd + 8 * i
            break
    assert ent is not None, "relocate_tag: no fixup entry for the tag pointer"
    idx = n + len(buf.queue)
    size = (0x20 + len(tag) + 15) // 16 * 16 + 0x20
    if size > 0x100000:
        raise ValueError("relocated tagfile page of %d bytes exceeds the 1 MB page size every stock pak keeps (item %s)" % (size, it.name))
    page = bytearray(size)
    page[0:8] = struct.pack("<Q", 0xDEADBEEFDEADBEEF)
    struct.pack_into("<I", page, 12, size)
    page[0x20:0x20 + len(tag)] = tag
    pool = b"\x00RAW_DATA\x00_chunk%d.%d\x00" % (idx, idx)
    page[size - 0x20:size - 0x20 + len(pool)] = pool
    buf.queue.append(bytes(page))
    struct.pack_into("<Q", d, a, 0x20)
    struct.pack_into("<H", d, ent + 2, idx)


def _grow_tag_page(buf, pak, it, new_len):
    """Make the page that holds item `it`'s tagfile bigger.  Only possible when that page holds nothing but the tagfile
    (ND puts the 0x100-kind tagfiles of a -phys pak on pages of their own: page size = 0x20 header bytes + tagfile size,
    no item, no pointer slot inside): the page is rewritten bigger, later pages move up in the file, the page table and
    the page's size field are updated.  Pointers into the page (the tagfile at +0x20) and every other page stay valid."""
    pg = next(i for i, (s, z, f) in enumerate(pak.pages) if s <= it.tag_off < s + z)
    st, sz, fl = pak.pages[pg]
    cnt = struct.unpack_from("<H", pak.d, st + 18)[0]
    inside = [k for k in list(pak.fix) if st <= k < st + sz]
    tail = sz - (it.tag_off - st) - it.tsz              # ND: the page's name pool ("\0RAW_DATA\0_chunk2.2\0", padded), 0x20 bytes
    if (cnt or inside or tail < 0 or tail > 0x40) and buf is None and RELOCATE:
        return pg, st, sz, sz, 0                         # a probe: a tagfile that cannot grow in its page moves to a page of its own (relocate_tag), always possible
    if cnt or inside or tail < 0 or tail > 0x40:
        raise ValueError("the edited tagfile (%d bytes, slot %d) does not fit and its page also holds other data "
                         "(items %d, pointer slots %d, %d bytes after the tagfile): cannot be grown in place" % (
                             new_len, it.tsz, cnt, len(inside), tail))
    new_sz = ((it.tag_off - st) + new_len + 15) // 16 * 16 + tail
    return pg, st, sz, new_sz, new_sz - sz


def write_item(buf, it, new_mesh, new_blob):
    """overwrite item `it` inside bytearray `buf` (the pak of `it`, items processed from the highest file offset down)
    with the edited mesh.  -> (buf, new tag size)"""
    tag = hc.encode_t2(new_mesh, it.tag)
    nb = len(it.blob)
    assert len(new_blob) >= nb or all(v == 0 for v in new_blob[nb:]), "key table grew"
    buf[it.blob_off:it.blob_off + nb] = new_blob[:nb].ljust(nb, b"\0")
    struct.pack_into("<I", buf, it.io + 48 + 12, len(tag))
    t = it.tag_off
    if len(tag) <= it.tsz:
        buf[t:t + it.tsz] = tag + bytes(it.tsz - len(tag))
        return buf, len(tag)
    try:
        pg, st, sz, new_sz, delta = _grow_tag_page(buf, it.pak, it, len(tag))
    except ValueError:
        if not RELOCATE or not isinstance(buf, PakBuf):
            raise
        relocate_tag(buf, it, tag)
        return buf, len(tag)
    n_pages = struct.unpack_from("<I", buf, 16)[0]
    pt = struct.unpack_from("<I", buf, 20)[0]
    tail = bytes(buf[t + it.tsz:st + sz])
    out = PakBuf(bytes(buf[:t]) + tag + bytes(new_sz - (t - st) - len(tag) - len(tail)) + tail + bytes(buf[st + sz:])) if isinstance(buf, PakBuf) else         bytearray(buf[:t]) + tag + bytes(new_sz - (t - st) - len(tag) - len(tail)) + tail + bytes(buf[st + sz:])
    if isinstance(buf, PakBuf):
        out.queue = buf.queue
    struct.pack_into("<I", out, st + 12, new_sz)                  # the page's own size field
    struct.pack_into("<I", out, pt + 12 * pg + 4, new_sz)         # page table: size
    for j in range(pg + 1, n_pages):
        s0 = struct.unpack_from("<I", out, pt + 12 * j)[0]
        struct.pack_into("<I", out, pt + 12 * j, s0 + delta)      # later pages start later in the file
    return out, len(tag)


# ============================================================================================== render pak
class Instance:
    __slots__ = ("pak_off", "M", "lo", "hi", "wlo", "whi", "names", "page", "proto", "subs", "loc", "parent", "idx", "count")
    # draw entries only (loc = the entry's own placement-relative matrix, pak_off = the entry's offset, parent = the placement,
    # idx / count = index in / size of its entry list); placements get loc = None in find_instances


def _proto_of(p, o):
    """asset path of the placement whose matrix is at o: the record's header follows its two boxes (o + 0x80); header +0 points
    at the prototype, prototype +0x30 at its name 'pmCollection0.<asset path>.ma' (the gate: san-mansion-wrought-iron-gate-a.ma,
    measured on the mansion pak; the header BEFORE a matrix belongs to the previous placement)"""
    h = o + 0x80
    try:
        pr = p.ptr(h)
        s = p.ptr(pr + 0x30) if pr else 0
        nm = p.cstr(s) if s else ""
    except Exception:
        return ""
    if not nm or not nm.endswith(".ma") or not all(32 <= ord(c) < 127 for c in nm):
        return ""
    return nm.split(".", 1)[1] if nm.startswith("pmCollection") else nm


def find_instances(p, variant=False):
    """Every prop instance of a level pak: 4x4 world matrix (rows = basis x/y/z + translation, w = 0 0 0 1) directly
    followed by the prop's local AABB twice (4 rows, w = 1; min, max, min, max).  Names = the submeshes whose AABBs
    union to that local box (matched by asset path).
    variant=True also returns the second record layout (Overpass barbed wire / razor wire / chain-link fence pieces of the
    taco level): matrix, then a symmetric +-box (min = -max, w = 1), then the local AABB ONCE (min, max); `it.lo / hi` = that AABB."""
    d = p.d
    res = []
    for pi, (st, sz, fl) in enumerate(p.pages):
        n = sz // 4
        if n < 32:
            continue
        a32 = np.frombuffer(d, "<f4", count=n, offset=st)
        m = n - 32
        # every layout needs w(15) == 1: only those positions (a tiny fraction of the page) get the other 20+ comparisons, on the same float64 values
        # (nan / inf -> +-7e30 as before) as the full-page evaluation, so the same positions come out in the same (ascending) order
        cand = np.nonzero(a32[15:15 + m] == 1)[0]
        if not len(cand):
            continue

        def w(k, cand=cand, a32=a32):
            return np.nan_to_num(a32[cand + k].astype(np.float64), nan=7e30, posinf=7e30, neginf=-7e30)
        ok = (w(3) == 0) & (w(7) == 0) & (w(11) == 0) & (w(19) == 1) & (w(23) == 1) & (w(27) == 1) & (w(31) == 1)
        ok &= (w(16) == w(24)) & (w(17) == w(25)) & (w(18) == w(26)) & (w(20) == w(28)) & (w(21) == w(29)) & (w(22) == w(30))
        ok &= (w(20) >= w(16)) & (w(21) >= w(17)) & (w(22) >= w(18))
        for k in cand[ok]:
            res.append((pi, st + 4 * int(k), 0))
        if variant:
            ok2 = (w(3) == 0) & (w(7) == 0) & (w(11) == 0) & (w(19) == 1) & (w(23) == 1) & (w(27) == 1) & (w(31) == 1)
            ok2 &= (np.abs(w(16) + w(20)) < 2e-3) & (np.abs(w(17) + w(21)) < 2e-3) & (np.abs(w(18) + w(22)) < 2e-3) & (w(20) >= 0) & (w(21) >= 0) & (w(22) >= 0)
            ok2 &= (w(28) >= w(24)) & (w(29) >= w(25)) & (w(30) >= w(26)) & ~ok
            ok2 &= (np.abs(w(0)) < 1e4) & (np.abs(w(12)) < 1e4) & (np.abs(w(14)) < 1e4) & (np.abs(w(20)) + np.abs(w(22)) > 0)
            for k in cand[ok2]:
                res.append((pi, st + 4 * int(k), 1))
    sub = np.array([struct.unpack_from("<3f", d, s["offset"]) + struct.unpack_from("<3f", d, s["offset"] + 16)
                    for s in p.submeshes]) if p.submeshes else np.zeros((0, 6))
    asset = [s["name"].split("|")[0] for s in p.submeshes]
    by_asset = {}
    for i, a in enumerate(asset):
        by_asset.setdefault(a, []).append(i)
    out = []
    for pi, o, v in res:
        it = Instance()
        it.pak_off, it.page = o, pi
        it.loc = it.parent = it.idx = it.count = None
        it.M = np.frombuffer(d, "<f4", 16, o).reshape(4, 4).astype(np.float64)
        it.lo = np.frombuffer(d, "<f4", 3, o + 64 + 32 * v).astype(np.float64)
        it.hi = np.frombuffer(d, "<f4", 3, o + 80 + 32 * v).astype(np.float64)
        cor = np.array([[x, y, z, 1] for x in (it.lo[0], it.hi[0]) for y in (it.lo[1], it.hi[1]) for z in (it.lo[2], it.hi[2])]) @ it.M
        it.wlo, it.whi = cor[:, :3].min(0), cor[:, :3].max(0)
        tol = 2e-3
        inside = np.nonzero((sub[:, :3] >= it.lo - tol).all(1) & (sub[:, 3:] <= it.hi + tol).all(1))[0].tolist() if len(sub) else []
        groups = {}
        for i in inside:
            groups.setdefault(asset[i], []).append(i)
        it.names = []
        for g, ids in groups.items():
            if (abs(sub[ids, :3].min(0) - it.lo) < tol).all() and (abs(sub[ids, 3:].max(0) - it.hi) < tol).all():
                it.names.append((g.split("/")[-1], ids))
        it.proto = _proto_of(p, o)                  # what the record itself says it draws (also for the AABB-unmatched ones)
        it.subs = by_asset.get(it.proto, [])
        out.append(it)
    return out


def instances_in(insts, box, name=None, pad=0.05):
    lo, hi = np.array(box[:3]) - pad, np.array(box[3:]) + pad
    out = []
    for it in insts:
        if (it.wlo >= lo).all() and (it.whi <= hi).all() and (not name or any(name in n for n, _ in it.names)):
            out.append(it)
    return out


def _family(names):
    """'military-truck-modern-cab.ma' -> 'military-truck' (first two dash words of the asset): the parts of one prop"""
    nm = (names[0][0] if names else "").split("/")[-1]
    nm = re.sub(r"\.ma$", "", nm)
    return "-".join(nm.split("-")[:2]) if nm.count("-") >= 1 else nm


def prop_group(insts, anchor, grow=0.3, max_size=15.0):
    """the render instances that make up one baked prop with `anchor` (a car = body + interior + undercarriage + wheels):
    same asset family (first two dash words) and overlapping the group's box, plus wheels / tyres inside it.  Merged level
    meshes (> max_size m) and foliage never join (their oriented boxes would take the ground with them)."""
    fam = _family(anchor.names)
    g = [anchor]
    lo, hi = anchor.wlo.copy(), anchor.whi.copy()
    changed = True
    while changed:
        changed = False
        for it in insts:
            if it in g or ((it.whi - it.wlo) > max_size).any():
                continue
            nm = ", ".join(n for n, _ in it.names)
            if re.search(r"ivy|weed|grass|foliage|leaves|vine|moss|decal|tfrag|merge", nm):
                continue
            same = _family(it.names) == fam and fam
            wheel = re.search(r"wheel|tire|tyre", nm) and (it.wlo >= lo - grow).all() and (it.whi <= hi + grow).all()
            touch = (it.whi >= lo - grow).all() and (it.wlo <= hi + grow).all()
            if (same and touch) or wheel:
                g.append(it)
                lo, hi = np.minimum(lo, it.wlo), np.maximum(hi, it.whi)
                changed = True
    return g


def prop_dressing(insts, group, grow=0.15, max_size=15.0):
    """render instances lying completely inside the prop group's box that are not part of it: ivy hanging on a truck, a
    case on its bed, the level's own baked bits of the prop.  They move with the prop (render), but their oriented boxes
    are NOT used to select collision (foliage boxes reach the ground)."""
    lo = np.min([i.wlo for i in group], 0) - grow
    hi = np.max([i.whi for i in group], 0) + grow
    return [it for it in insts if it not in group and not ((it.whi - it.wlo) > max_size).any()
            and (it.wlo >= lo).all() and (it.whi <= hi).all()]


def _rot_y(deg):
    c, s = math.cos(math.radians(deg)), math.sin(math.radians(deg))
    return np.array([[c, 0, s], [0, 1, 0], [-s, 0, c]])      # column convention: x' = x c + z s, z' = -x s + z c


def transform_point(P, action, pivot=None, delta=None, angle=0.0):
    P = np.asarray(P, float)
    if action == "move":
        return P + np.array(delta, float)
    if action == "rotate":
        pv = np.array(pivot, float)
        return (P - pv) @ _rot_y(angle).T + pv
    if action == "transform":                          # rotate about the pivot (if an angle is given), then move
        if angle:
            pv = np.array(pivot, float)
            P = (P - pv) @ _rot_y(angle).T + pv
        return P + np.array(delta if delta is not None else (0.0, 0.0, 0.0), float)
    raise ValueError(action)


def edit_matrix(M, action, pivot=None, delta=None, angle=0.0, hide_dy=-1000.0):
    """new 4x4 (row-vector convention: p_world = p_local @ M) for remove (= hide) / move / rotate"""
    M = M.copy()
    if action == "remove":
        M[3, 1] += hide_dy
    elif action == "move":
        M[3, :3] += np.array(delta, float)
    elif action == "rotate":
        R = _rot_y(angle)
        M[:3, :3] = M[:3, :3] @ R.T
        M[3, :3] = (M[3, :3] - np.array(pivot, float)) @ R.T + np.array(pivot, float)
    elif action == "transform":
        if angle:
            R = _rot_y(angle)
            M[:3, :3] = M[:3, :3] @ R.T
            M[3, :3] = (M[3, :3] - np.array(pivot, float)) @ R.T + np.array(pivot, float)
        if delta is not None:
            M[3, :3] += np.array(delta, float)
    else:
        raise ValueError(action)
    return M


def submesh_tris(p, i):
    """local-space triangles (n,3,3) of submesh i of a level pak"""
    sm = p.submeshes[i]
    P = _qpos(p, sm)
    if P is None:
        return np.zeros((0, 3, 3))
    I = np.array(p.indices(sm), np.int64).reshape(-1, 3)
    return P[I]


def _qpos(p, sm):
    st = p.pos_stream(sm)
    if st is None:
        return None
    n = sm["vcount"]
    if st["type"] == 0:
        return np.frombuffer(bytes(p.d[st["buf"]:st["buf"] + 12 * n]), "<f4").reshape(n, 3).astype(float)
    bits, stride = st["bits"], sum(st["bits"])
    buf = np.frombuffer(p.d, np.uint8)
    bo = st["buf"] * 8 + np.arange(n, dtype=np.int64) * stride
    out = np.zeros((n, 3))
    for c in range(3):
        byte = bo >> 3
        wv = np.zeros(n, np.uint64)
        for k in range(8):
            wv |= buf[np.minimum(byte + k, len(buf) - 1)].astype(np.uint64) << np.uint64(8 * k)
        wv >>= (bo & 7).astype(np.uint64)
        raw = (wv & np.uint64((1 << bits[c]) - 1)).astype(np.float64)
        out[:, c] = raw * st["scale"][c] + st["off"][c]
        bo = bo + bits[c]
    return out


def world_submeshes(p, box, insts=None):
    """world-space render triangles in/near box: world-space (merged) submeshes whose AABB meets the box + every
    instance's submeshes through its matrix"""
    lo, hi = np.array(box[:3]), np.array(box[3:])
    insts = insts if insts is not None else find_instances(p)
    out = []
    inst_sub = {i for it in insts for _, ids in it.names for i in ids}
    for i, sm in enumerate(p.submeshes):
        if i in inst_sub:
            continue
        o = sm["offset"]
        a, b = np.array(struct.unpack_from("<3f", p.d, o)), np.array(struct.unpack_from("<3f", p.d, o + 16))
        if (b < lo).any() or (a > hi).any():
            continue
        if (b - a).max() > 400:             # sky / whole-level meshes
            continue
        T = submesh_tris(p, i)
        if len(T):
            out.append(T)
    for it in insts:
        if (it.whi < lo).any() or (it.wlo > hi).any():
            continue
        for _, ids in it.names:
            for i in ids:
                T = submesh_tris(p, i)
                if len(T):
                    T4 = np.concatenate([T, np.ones(T.shape[:2] + (1,))], 2) @ it.M
                    out.append(T4[:, :, :3])
    return np.concatenate(out) if out else np.zeros((0, 3, 3))


# ============================================================================================ edit pipeline
def _spec_box(e):
    return [float(v) for v in e["box"]]


def world_cut(p, box, mode="inside", insts=None, name=None, sub=None, tris=None, hide=None, skip_shared=False, index=None):
    """{submesh index: triangle indices} of the render triangles inside box that can be cut: the triangles of submeshes that
    only ONE placement uses (merged / baked world-space meshes sit in an instance record with an identity matrix; a prop
    prototype used by several records cannot be cut for one of them - that raises).  Cutting = the three indices of the
    triangle become its first one (a degenerate triangle: nothing is drawn), no buffer changes size.
    hide (a list, optional): a SHARED prototype (several placements draw the submesh) whose every live triangle is selected for
    one placement is not cut; that placement is appended to `hide` instead (hiding it = the same visible result for it alone).
    index (a list, optional): only these submeshes (by index) are cut.  The converted Part I paks carry no submesh names (Part I has none:
    p1_convert writes the empty string), so `name` / `sub` cannot select anything there, and a name-less cut over a box reaches every
    prototype used by several placements (raises).  The submesh index is stable (converted order = Part I order = the order of the
    'pmCollection0.' strings of the pak).  `box` stays the WORLD box (find_instances still owns the submesh and puts it through its matrix)."""
    lo, hi = np.array(box[:3], float), np.array(box[3:], float)
    insts = insts if insts is not None else find_instances(p)
    owners = {}
    for it in insts:
        for _, ids in it.names:
            for i in ids:
                owners.setdefault(i, []).append(it)
    out = {}
    todo = []
    for it in insts:                                       # placements whose world box meets the box
        if not ((it.whi >= lo).all() and (it.wlo <= hi).all()):
            continue
        if name and not any(name in n for n, _ in it.names) and not (it.names == [] and name in (it.proto or "")):
            continue
        todo += [(i, it.M, it) for _, ids in it.names for i in ids] or ([(i, it.M, it) for i in it.subs] if name else [])
    ident = np.eye(4)
    if not name:
        todo += [(i, ident, None) for i in range(len(p.submeshes)) if i not in owners]
    for i, M, own in todo:
        sm = p.submeshes[i]
        T = submesh_tris(p, i)
        if not len(T) or (sub and not re.search(sub, sm["name"])) or (index is not None and i not in index):
            continue
        W = (np.concatenate([T, np.ones(T.shape[:2] + (1,))], 2) @ M)[:, :, :3]
        if (W.reshape(-1, 3).max(0) < lo).any() or (W.reshape(-1, 3).min(0) > hi).any():
            continue
        if mode == "centroid":
            c = W.mean(1)
            sel = ((c >= lo) & (c <= hi)).all(1)
        else:
            sel = ((W.min(1) >= lo) & (W.max(1) <= hi)).all(1)
        I = np.array(p.indices(sm), np.int64).reshape(-1, 3)
        sel &= I[:, 0] != I[:, 1]                       # already degenerate: not counted
        if tris is not None:                            # explicit triangle list (one connected ivy piece, tools/maps/ivy_float.py)
            sel &= np.isin(np.arange(len(sel)), np.asarray(tris, np.int64))
        if not sel.any():
            continue
        if len(owners.get(i, [])) > 1:
            if hide is not None and not skip_shared and own is not None and sel.sum() == (I[:, 0] != I[:, 1]).sum():
                if own not in hide:
                    hide.append(own)                  # every live triangle of this placement's copy: hide the placement instead
                continue
            if skip_shared:                                # shadow-proxy companion cut (geoedit.shadow_edit): a shared prototype's proxy stays
                continue
            raise SystemExit("submesh #%d (%s) is used by %d placements: cutting it would remove the triangles from every one of them"
                             % (i, sm["name"][-60:], len(owners[i])))
        out[i] = np.nonzero(sel)[0]
    return out


def cut_triangles(buf, p, i, tris):
    sm = p.submeshes[i]
    base = sm["index"]
    for t in tris:
        o = base + 6 * int(t)
        first = bytes(buf[o:o + 2])
        buf[o + 2:o + 4] = first
        buf[o + 4:o + 6] = first


ROOM = {}


def box_tris(center, size, yaw_deg=0.0, open_bottom=False):
    """12 triangles (outward winding) of an oriented box: centre, size (x, y, z of the box's own frame), yaw about +Y (the render
    rotate convention x' = x c + z s, z' = -x s + z c)"""
    c, s = math.cos(math.radians(yaw_deg)), math.sin(math.radians(yaw_deg))
    hx, hy, hz = (float(v) / 2 for v in size)
    P = np.array([[sx * hx, sy * hy, sz * hz] for sx in (-1, 1) for sy in (-1, 1) for sz in (-1, 1)])   # index = 4 a + 2 b + c (a, b, c = 0 / 1)
    W = np.stack([P[:, 0] * c + P[:, 2] * s, P[:, 1], -P[:, 0] * s + P[:, 2] * c], 1) + np.array(center, float)
    quads = [(0, 1, 3, 2), (4, 6, 7, 5), (0, 4, 5, 1), (2, 3, 7, 6), (0, 2, 6, 4), (1, 5, 7, 3)]
    out = []
    for a, b, cc, d in quads:
        out += [[W[a], W[b], W[cc]], [W[a], W[cc], W[d]]]
    T = np.array(out)
    ctr = W.mean(0)
    for i, t in enumerate(T):                               # make every face point away from the box centre
        if np.dot(np.cross(t[1] - t[0], t[2] - t[0]), t.mean(0) - ctr) < 0:
            T[i] = t[[0, 2, 1]]
    if open_bottom:                                          # no floor face (a prop on the ground: 10 instead of 12 triangles, each new triangle costs ~90 bytes of tagfile)
        nrm = np.cross(T[:, 1] - T[:, 0], T[:, 2] - T[:, 0])
        T = T[~(nrm[:, 1] < -0.9 * np.linalg.norm(nrm, axis=1))]
    return T


def add_box_plan(e, phys):
    """edit {"action": "add", "level", "boxes": [{"center": [x, y, z], "size": [w, h, t], "yaw": deg, "name": ..., "like": [x, y, z]}], "like": [x, y, z]}
    ("like": the vertical wall triangle nearest this point gives tag / interior bit / material bits; default the box centre).  A box with "mrec": "<8-byte material record hex>" copies from the nearest triangle (any orientation) that has exactly that record.
    -> {phys item index: (reference keys (one per new triangle), new triangles)}.  The item is the one holding the nearest wall triangle:
    the new triangles join that static collision body, so they answer to the same layers (player capsule AND bullets / grenades) as the walls around them."""
    per = {}
    for b in e["boxes"]:
        c = np.array(b["center"], float)
        like = np.array(b.get("like") or e.get("like") or c, float)
        best = None
        if b.get("tris"):                                    # explicit single-layer triangles ([[x y z] x3, ...], up-facing winding): a ground surface that follows the render snow
            TB = np.array(b["tris"], float).reshape(-1, 3, 3)
        elif b.get("points"):                                # a sloped slab over 4 points (coll_edit.thick_quad), "thickness" m thick
            import coll_edit
            TB = coll_edit.thick_quad(b["points"], float(b.get("thickness", 0.1)))
        else:
            TB = box_tris(c, b["size"], b.get("yaw", 0.0), bool(b.get("open_bottom")))
        for k, it in enumerate(phys):
            m_ = it.mesh
            dmin_, dmax_ = m_.domain()
            if (TB.reshape(-1, 3).min(0) < dmin_).any() or (TB.reshape(-1, 3).max(0) > dmax_).any():
                continue                                    # the box has to lie inside the item's mesh domain (quantised vertex range)
            if len(m_.sections) + 1 >= 1 << (m_.keybits - 8) or len(it.blob) * 8 < 3 * (1 << m_.keybits):
                continue                                    # no free section slot / the per-key table has no room for new keys (small items)
            if not b.get("room") and not e.get("room"):
                try:
                    _grow_tag_page(None, it.pak, it, it.tsz + 100000)
                except ValueError:
                    continue                                # the tagfile shares its page with other data: it cannot grow (give "room" to pay for the new triangles)
            keys, T, tg = hc.triangles(it.mesh)
            if not len(T):
                continue
            n = np.cross(T[:, 1] - T[:, 0], T[:, 2] - T[:, 0])
            nl = np.linalg.norm(n, axis=1)
            wall = (np.abs(n[:, 1]) < 0.3 * nl + 1e-12) & (0.5 * nl > 0.25)
            b_ = it.io + 48                                 # material records (8 bytes each): only a plain solid one (surface 1, no flag bytes) is copied
            ro_, nr_ = it.pak.ptr(b_ + 80), struct.unpack_from("<I", it.pak.d, b_ + 60)[0]
            plain = {i for i in range(nr_) if it.pak.d[ro_ + 8 * i] == 1 and it.pak.d[ro_ + 8 * i + 2] == 0 and it.pak.d[ro_ + 8 * i + 3] == 0}
            mrec = b.get("mrec") or e.get("mrec")           # exact 8-byte material record (hex) instead of the plain wall one: a window sill / frame with its flag bytes (SP sill 0100040001010000)
            if mrec:
                ridx = _recs(it).get(mrec.lower())
                if ridx is None:
                    continue
                wall = np.isin(tg >> 6, np.array([ridx], np.int64))
            else:
                wall &= np.isin(tg >> 6, np.array(sorted(plain), np.int64))
            if not wall.any():
                continue
            d = np.linalg.norm(T[wall].mean(1) - like, axis=1)
            j = int(np.argmin(d))
            if best is None or d[j] < best[0]:
                best = (float(d[j]), k, int(keys[wall][j]), int(tg[wall][j]))
        if best is None or best[0] > float(e.get("like_max", 12.0)):
            raise SystemExit("edit %r: no wall triangle within %s m of %s (in an item with room for new keys) to copy the collision material from" % (
                e.get("name"), e.get("like_max", 12.0), like.tolist()))
        ks, Tn = per.get(best[1], ([], []))
        ks += [best[2]] * len(TB)
        Tn += [t for t in TB]
        per[best[1]] = (ks, Tn)
        room = b.get("room") or e.get("room")
        if room:                                            # an item that cannot grow: drop collision triangles far outside the play space instead (same item)
            for rb in (room if isinstance(room[0], (list, tuple)) else [room]):          # one box or a list of boxes
                rk, _rT = _tri_sel(phys[best[1]].mesh, rb, None, "inside")
                ROOM.setdefault(id(e), {}).setdefault(best[1], set()).update(int(x) for x in rk)
        print("  add box %-24s centre %s size %s yaw %s -> phys item %d, material of key %#x (tag %d, %.2f m away)" % (
            b.get("name", ""), np.round(c, 2).tolist(), b["size"], b.get("yaw", 0), best[1], best[2], best[3], best[0]))
    return {k: (np.array(ks, np.int64), np.array(Tn)) for k, (ks, Tn) in per.items()}


PREFAB_DIR = os.path.join(HERE, "data", "prefabs")


def load_car_collision(prefab, pdir=None):
    """(T [n,3,3] car-frame triangles, inter [n], bv [n], mrec [n] hex of the 8-byte material record, tag [n] source tags) of a vehicle prefab (vehicle_prefabs.py extract)"""
    import zlib
    pdir = pdir or PREFAB_DIR
    meta = json.load(open(os.path.join(pdir, prefab + ".json")))
    b = zlib.decompress(open(os.path.join(pdir, meta["collision_file"]), "rb").read())
    nv, nt = np.frombuffer(b, "<u4", 2, 4)
    v = np.frombuffer(b, "<f4", int(nv) * 3, 12).reshape(-1, 3).astype(float)
    T = v[np.frombuffer(b, "<u4", int(nt) * 3, 12 + int(nv) * 12).reshape(-1, 3)]
    tg = np.frombuffer(b, "<u2", int(nt), 12 + int(nv) * 12 + int(nt) * 12).astype(int)
    a = json.loads(zlib.decompress(open(os.path.join(pdir, meta["collision_attr_file"]), "rb").read()))
    return T, np.array(a["inter"]), np.array(a["bv"]), [a["materials"][i] for i in a["mat_index"]], tg


def car_world(T, pos, yaw_deg):
    c, s_ = math.cos(math.radians(yaw_deg)), math.sin(math.radians(yaw_deg))
    R = np.array([[c, 0, -s_], [0, 1, 0], [s_, 0, c]])
    return T @ R + np.asarray(pos, float)


def _recs(it):
    """{8-byte material record hex: index} of a phys item"""
    b_ = it.io + 48
    ro_, nr_ = it.pak.ptr(b_ + 80), struct.unpack_from("<I", it.pak.d, b_ + 60)[0]
    return {bytes(it.pak.d[ro_ + 8 * i:ro_ + 8 * i + 8]).hex(): i for i in range(nr_)}


def car_collision_plan(e, phys):
    """edit {"action": "cars", "level", "cars": [{"prefab", "pos": [x, y, z] (world position of the car-frame origin), "yaw": deg, "name"}]}
    The SP car's EXACT collision triangles (tools/maps/data/prefabs/<prefab>.col + .colattr: vertices, interior bit, 3-bit material value, material record) moved
    to the pose and appended to the phys items of this level: every triangle goes to an item whose quantisation domain holds it and that has room (free section
    slots, per-key table, growable tagfile page); a car that straddles items is split.  The tag of a triangle is re-pointed at the destination item's identical
    8-byte material record (items have their own material tables); no identical record = SystemExit (never a silent other material).
    -> {item index: ({"direct": (attrs [(tag, interior)], blob values)}, new triangles)}"""
    out = {}
    free, nogrow = {}, {}
    for k, it in enumerate(phys):
        m_ = it.mesh
        ok = len(it.blob) * 8 >= 3 * (1 << m_.keybits)
        grow = True
        if ok:
            try:
                _grow_tag_page(None, it.pak, it, it.tsz + 100000)
            except ValueError:
                grow = False                                    # the tagfile shares its page: it cannot grow, only pay with triangles of its own ("room")
        ok = ok and (grow or bool(e.get("room")))
        free[k] = (1 << (m_.keybits - 8)) - len(m_.sections) - 1 if ok else 0
        nogrow[k] = not grow
        if ok and not grow:                                     # pays one dropped triangle (room box) per new triangle, with 30 % slack for the tree nodes
            rk = set()
            for rb in e["room"]:
                rk |= set(int(x) for x in _tri_sel(m_, rb, None, "inside")[0])
            free[k] = min(free[k], int(len(rk) / 1.3) // 100)
    for c in e["cars"]:
        T, inter, bv, mrec, tg0 = load_car_collision(c["prefab"], e.get("prefab_dir"))
        W = car_world(T, c["pos"], c.get("yaw", 0.0))
        todo = set(range(len(W)))
        while todo:
            idx = np.array(sorted(todo))
            best = None
            for k, it in enumerate(phys):
                lo, hi = it.mesh.domain()
                inside = idx[((W[idx].reshape(len(idx), -1, 3).min(1) >= lo) & (W[idx].reshape(len(idx), -1, 3).max(1) <= hi)).all(1)]
                if len(inside) and free[k] > 0:
                    cap = (free[k] - 1) * 100                      # new sections hold <= 100 triangles each; a car that does not fit is split over items
                    if len(inside) > cap:
                        inside = inside[np.argsort(W[inside].mean(1)[:, 0])][:max(cap, 0)]
                    if not len(inside):
                        continue
                    sc = (not nogrow[k], sum(1 for i in inside if mrec[i] in _recs(it)), len(inside))        # a growable tagfile first (a fixed one only pays with room triangles)        # most triangles keeping their exact material record, then the most triangles
                    if best is None or sc > best[2]:
                        best = (k, inside, sc)
            if best is None:
                lo_, hi_ = W[idx].reshape(-1, 3).min(0), W[idx].reshape(-1, 3).max(0)
                raise SystemExit("edit %r car %r: %d triangles at %s .. %s fit no phys item of %s (domain + free section slots + growable tagfile page); "
                                 "move the car inside an item's domain, name another level, or give 'room'" % (
                                     e.get("name"), c.get("name") or c["prefab"], len(idx), np.round(lo_, 2).tolist(), np.round(hi_, 2).tolist(), e["level"]))
            k, ins, _sc = best
            it = phys[k]
            recs = _recs(it)
            nr_ = len(recs)
            attrs, bvs, subst = [], [], {}
            for i in ins:
                r = mrec[i]
                if r not in recs:
                    # The material table (8-byte records) of an item cannot grow (the key table follows it in the page), and no item holds every record of a
                    # car.  Nearest record of THIS item: same surface byte 0 and class byte 1, fewest differing bits in the rest; none = SystemExit.
                    if r not in subst:
                        cand = []
                        for pre in (4, 2, 0):            # same surface + class bytes, else the same surface byte, else any record: fewest differing bits
                            cand = [(bin(int(r, 16) ^ int(x, 16)).count("1"), x) for x in recs if x[:pre] == r[:pre]]
                            if cand:
                                break
                        subst[r] = min(cand)[1]
                    r = subst[r]
                attrs.append((recs[r] << 6 | (int(tg0[i]) & 63), int(inter[i])))
                bvs.append(int(bv[i]))
            ent = out.setdefault(k, [[], [], []])
            ent[0] += attrs
            ent[1] += bvs
            ent[2] += [W[i] for i in ins]
            free[k] -= (len(ins) + 99) // 100 + 1
            if nogrow[k] and e.get("room"):
                for rb in e["room"]:
                    rk, _rT = _tri_sel(it.mesh, rb, None, "inside")
                    ROOM.setdefault(id(e), {}).setdefault(k, set()).update(int(x) for x in rk)
            todo -= set(int(i) for i in ins)
            print("  car %-28s %d triangles -> phys item %d (%d records, free sections left %d)%s" % (
                c.get("name") or c["prefab"], len(ins), k, nr_, free[k],
                "; material records substituted (exact one missing in the item): " + ", ".join("%s->%s (%d tris)" % (a, b, sum(1 for i in ins if mrec[i] == a)) for a, b in subst.items()) if subst else ""))
    return {k: ({"direct": (v[0], v[1])}, np.array(v[2])) for k, v in out.items()}


def assign_car_levels(levels, cars, room=None, game=None, work=None, log=print):
    """dry-run car_collision_plan: the first level (in the given order) whose -phys items take each car (domain, free sections, growable page / room).
    -> [(level, [cars])]  (SystemExit when a car fits none: the 'no item with room' case)"""
    work = work or CACHE
    cache, per = {}, {}
    for c in cars:
        done = False
        for lv in levels:
            if lv not in cache:
                try:
                    cache[lv] = phys_items(fetch(lv, os.path.join(work, "src"), game, ("-phys",))["-phys"])[1]
                except SystemExit:
                    cache[lv] = None
            if cache[lv] is None:
                continue
            try:
                import io as _io, contextlib, tempfile
                ed = {"action": "cars", "name": "dry run", "level": lv, "cars": per.get(lv, []) + [c], "room": room}
                src_ = fetch(lv, os.path.join(work, "src"), game, ("-phys",))["-phys"]
                with contextlib.redirect_stdout(_io.StringIO()):       # the real write too: a tagfile that cannot grow only fails when it is encoded
                    pls = plan_edits([ed], None, src_)
                    apply_plans(pls, None, src_, None, os.path.join(tempfile.gettempdir(), "t2r-cars-dry-%d.pak" % os.getpid()), lambda *a: None, None)
            except (SystemExit, ValueError) as ex:
                log("  car %s: not in %s: %s" % (c.get("name") or c["prefab"], lv, str(ex)[:150]))
                continue
            per.setdefault(lv, []).append(c)
            done = True
            break
        if not done:
            raise SystemExit("car %r fits no phys item of %s (domain + free sections + growable tagfile page, or room): move it or load another level" % (c.get("name") or c["prefab"], levels))
    return [(lv, cs) for lv, cs in per.items()]


def _variant_only(p):
    base = {it.pak_off for it in find_instances(p)}
    return [it for it in find_instances(p, True) if it.pak_off not in base]


def _variants(p):
    """{offset: variant-layout Instance} of a pak, cached on the pak object (an id()-keyed cache served a freed pak's data to a new one)"""
    v = getattr(p, "_t2r_variants", None)
    if v is None:
        v = p._t2r_variants = {x.pak_off: x for x in _variant_only(p)}
    return v


ENTRY_STRIDE = 0x80                                 # one draw entry of a placement: local matrix + local box (+ flags)


def entry_instance(p, c, k, n):
    """draw entry k of n of placement c as an Instance: M = entry matrix x placement matrix (the entry's own world matrix),
    lo / hi = the entry's local box (floats 16..18 / 20..22 of the entry), loc = the entry's matrix as stored (placement-relative)"""
    o = p.ptr(c.pak_off + 0x90) + k * ENTRY_STRIDE
    it = Instance()
    it.pak_off, it.page, it.parent, it.idx, it.count = o, c.page, c, k, n
    it.loc = np.frombuffer(p.d, "<f4", 16, o).reshape(4, 4).astype(np.float64)
    it.M = it.loc @ c.M
    it.lo = np.frombuffer(p.d, "<f4", 3, o + 64).astype(np.float64)
    it.hi = np.frombuffer(p.d, "<f4", 3, o + 80).astype(np.float64)
    cor = np.array([[x, y, z, 1] for x in (it.lo[0], it.hi[0]) for y in (it.lo[1], it.hi[1]) for z in (it.lo[2], it.hi[2])]) @ it.M
    it.wlo, it.whi = cor[:, :3].min(0), cor[:, :3].max(0)
    it.names, it.proto, it.subs = c.names, c.proto, c.subs
    return it


def entry_of(p, cands, o):
    """(placement Instance, entry index, entry count) when o is a draw entry of one of cands, else None"""
    for c in cands:
        try:
            a, n = p.ptr(c.pak_off + 0x90), p.u32(c.pak_off + 0xC8)
        except Exception:
            continue
        if a and 0 < n < 4096 and a <= o < a + n * ENTRY_STRIDE and (o - a) % ENTRY_STRIDE == 0:
            return c, (o - a) // ENTRY_STRIDE, n
    return None


def resolve_records(p, insts, want, name=None, log=print, union=None, entries=False):
    """pak offsets -> Instances.  An offset is either a placement record (matrix + two boxes: find_instances) or,
    from the Scene Editor (MapItem.RecordOffset), one DRAW ENTRY of a placement: the 0x80-byte entries of the list at
    record + 0x90 (count u32 at record + 0xC8), whose matrix is relative to the placement.  The entries are separate copies of
    the prop, so an entry offset resolves to an entry Instance (its own world matrix and box; Instance.loc set) - EXCEPT when
    every entry of the placement is selected (in `want` plus `union`, {placement offset: {entry offsets}} across the edits of a
    level), where the placement itself is returned (the proven whole-placement hide).  entries=True: always entry Instances
    (collision boxes).  -> deduplicated Instance list"""
    insts = list(insts)
    by = {it.pak_off: it for it in insts}
    var = None
    out, seen = [], set()
    ent = {}                                            # (hit placement) -> entry hits of this call
    for o in sorted(want):
        it = by.get(o)
        if it is None:
            var = _variants(p)
            it = var.get(o)
        if it is not None:
            if it.pak_off not in seen:
                seen.add(it.pak_off)
                out.append(it)
            continue
        var = _variants(p)
        h = entry_of(p, insts + list(var.values()), o)
        if h is None:
            raise SystemExit("edit %r: offset %#x is neither a placement record nor a draw entry of one" % (name, o))
        ent.setdefault(h[0].pak_off, [h[0], h[2], set()])[2].add(h[1])
        out.append(("entry", h[0], h[1], h[2], o))
    res = []
    for x in out:
        if not isinstance(x, tuple):
            res.append(x)
            continue
        _, c, k, n, o = x
        sel = set(ent[c.pak_off][2])
        for eo in (union or {}).get(c.pak_off, ()):
            sel.add((eo - p.ptr(c.pak_off + 0x90)) // ENTRY_STRIDE)
        if n == 1 or (len(sel) >= n and not entries):
            it = c
        else:
            it = entry_instance(p, c, k, n)
        key = ("e", o) if it is not c else c.pak_off
        if key in seen:
            continue
        seen.add(key)
        res.append(it)
    return res


REC = 0x110                                         # size of one placement record (matrix at +0, boxes +0x40, header +0x80)
REC_SLOTS = (0x80, 0x90, 0x98, 0xA8, 0xB0, 0xB8, 0xC0)      # pointer slots of a record header (each has a fixup entry or none)


def level_basis(yaw_deg, n=(0.0, 1.0, 0.0)):
    """rows x / y / z of a prop standing on a ground plane with normal n, heading yaw (the 'rotate' convention: local z -> (sin, 0, cos))"""
    c, s = math.cos(math.radians(yaw_deg)), math.sin(math.radians(yaw_deg))
    ny = np.array(n, float)
    ny /= np.linalg.norm(ny)
    f = np.array([s, 0.0, c])
    z = f - ny * float(f @ ny)
    z /= np.linalg.norm(z)
    return np.array([np.cross(ny, z), ny, z])


def _slot_pattern(p, o):
    return tuple(p.fix.get(o + k) for k in REC_SLOTS)


def copy_plan(e, p, insts):
    """edit {"action": "copy", "level", "source": ["0x4145f0", ...] (the placement records of ONE prop, e.g. an RV's body + interiors),
    "copies": [{"name", "pos": [x, y, z] (where the FIRST source record's origin goes), "yaw": deg, "normal": [nx, ny, nz],
    "donors": ["0x..", ...] (one per source record)}]}.
    A copy = the source record byte for byte (same prototype pointer, draw entries and light data -> the same LOD chain and look)
    with a new matrix, written over a DONOR record of the same pointer-slot pattern (the donor prop disappears).  No file grows: the pak
    has no free record slots.  The donor keeps its own id (u32 at +0xE8).  -> [(donor offset, 0x110 bytes, source it, donor it, name)]"""
    by = {it.pak_off: it for it in insts}
    src = [int(o, 16) if isinstance(o, str) else int(o) for o in e["source"]]
    for o in src:
        if o not in by:
            raise SystemExit("edit %r: source record %#x is not a placement" % (e.get("name"), o))
    B0 = by[src[0]].M[:3, :3]
    t0 = by[src[0]].M[3, :3]
    used = set(src)
    out = []
    for c in e["copies"]:
        don = [int(o, 16) if isinstance(o, str) else int(o) for o in c["donors"]]
        if len(don) != len(src):
            raise SystemExit("edit %r copy %r: %d donors for %d source records" % (e.get("name"), c.get("name"), len(don), len(src)))
        Bn = level_basis(c["yaw"], c.get("normal", (0, 1, 0)))
        for so, do in zip(src, don):
            if do not in by or do in used:
                raise SystemExit("edit %r copy %r: donor %#x is not a free placement" % (e.get("name"), c.get("name"), do))
            if _slot_pattern(p, do) != _slot_pattern(p, so) or any((do + k) in p.fix for k in range(REC) if k not in REC_SLOTS):
                raise SystemExit("edit %r copy %r: donor %#x has another pointer-slot pattern than source %#x" % (e.get("name"), c.get("name"), do, so))
            used.add(do)
            M = by[so].M.copy()
            d_local = (M[3, :3] - t0) @ np.linalg.inv(B0)
            M[:3, :3] = by[so].M[:3, :3] @ np.linalg.inv(B0) @ Bn
            M[3, :3] = np.array(c["pos"], float) + d_local @ Bn
            rec = bytearray(p.d[so:so + REC])
            rec[0:64] = M.astype("<f4").tobytes()
            rec[0xE8:0xEC] = p.d[do + 0xE8:do + 0xEC]
            out.append((do, bytes(rec), by[so], by[do], c.get("name")))
    return out


# ============================================================================================ visibility (VIS_INFO_1)
# Precomputed visibility ("PVS"), seen in the Capitol Hill garage: the outside buildings are culled from inside the garage:
#   VIS_INFO_1 payload (item +0x30): u32 version 0xa, u32 record count (+4), records at +0x10 (72 bytes each), u32 +0x18 = n, bitset
#   size = 4 n bytes, u32 +0x1c = 0x100, Huffman table at +0x20 (0x100 nodes of {u16 bit0, u16 bit1}: value < 0x100 = byte,
#   0x100 = end of stream, else node (value - 0x101); the root is the LAST node).  Record: +4 priority, +0x10 kd-tree (24-byte
#   nodes: i32 axis | child << 2 (child for coordinate > split), i32 child for <= split, f32 split, a leaf is a node whose qword
#   +0x10 is non-zero), +0x18 AABB (min xyz, max xyz).  A leaf's qword is the offset of its Huffman stream in the page that its
#   FIXUP names: the pak's fixup table has 8 groups; group 0 (all ndpak reads) and group 1 (stored right behind it, 8-byte
#   {u16 src page, u16 dst page, u32 src offset} entries) - the leaf pointers are in group 1.  VisProbe::Decode (exe+17bc530 /
#   +17bf620 / +18557a0): at a camera position the engine takes the records whose box holds it and which have the HIGHEST
#   priority, walks each kd-tree to its leaf and ORs the decoded bitsets (bit = "object group visible from here").  Baked with the
#   garage door closed, the cells inside the garage see ~2200 bits of the ~3200 the street sees: the buildings outside are culled.
#   Edit "vis_open": every leaf cell that overlaps `box` gets its own bitset OR the union of what the cells of `outside` see.
class VisInfo:
    def __init__(self, p):
        self.p, self.d = p, p.d
        it = next((x for x in p.items if x[1] == "VIS_INFO_1"), None)
        if it is None:
            raise SystemExit("no VIS_INFO_1 item in this pak")
        self.io, self.pi = it[3], it[2]
        b = self.b = self.io + 0x30
        if p.u32(b) != 0xA:
            raise SystemExit("VIS_INFO_1 version %#x (expected 0xa)" % p.u32(b))
        self._dec = {}
        self.codes = None
        self.vfix = {}                                      # pointer slot (file offset) -> (dst page, fixup entry file offset), ALL fixup groups
        u32 = lambda o: struct.unpack_from("<I", self.d, o)[0]
        ft, n = u32(28), len(p.pages)
        start = u32(ft + 4)
        for g in range(8):
            cnt = u32(ft + 12 * g + 8)
            if cnt:
                ents = np.frombuffer(self.d, np.dtype([("sp", "<u2"), ("dp", "<u2"), ("so", "<u4")]), cnt, start)
                for i in np.nonzero((ents["sp"] < n) & (ents["dp"] < n))[0]:
                    sp, dp, so = int(ents["sp"][i]), int(ents["dp"][i]), int(ents["so"][i])
                    self.vfix[p.pages[sp][0] + so] = (dp, start + 8 * int(i))
            start += 8 * cnt
        # the header's own pointers (records, huffman table) sit in fixup group 1 in the big level paks (supermarket / alley), not group 0
        self.cnt, self.arr = p.u32(b + 4), self.ptr(b + 0x10)
        self.nbytes = p.u32(b + 0x18) * 4
        self.tab, self.ncode = self.ptr(b + 0x20), p.u32(b + 0x1c)
        self.root = self.tab + (self.ncode - 1) * 4

    def ptr(self, a):
        """file offset a pointer slot points at (any fixup group), 0 when the slot has no fixup"""
        x = self.vfix.get(a)
        return 0 if x is None else self.p.q(a) + self.p.pages[x[0]][0]

    def base_of(self, nd):
        """file offset of the page a leaf's stream offset is relative to (None: no fixup)"""
        x = self.vfix.get(nd + 0x10)
        return self.p.pages[x[0]][0] if x else None

    def rec(self, k):
        e = self.arr + 72 * k
        return e, struct.unpack_from("<i", self.d, e + 4)[0], struct.unpack_from("<6f", self.d, e + 0x18)

    def planes(self, k):
        """the record's convex volume: [(nx, ny, nz, d)], inside = n . p + d <= 0 for every plane.  The ENGINE decides "record holds the point" with these
        planes (exe+17bf8b0: count u32 at record +0, plane array pointer at +8, 16 bytes each), NOT with the AABB at +0x18 (widening the
        AABB alone changed nothing in game, the supermarket interior stayed culled from the courtyard)"""
        e = self.arr + 72 * k
        n, pp = self.p.u32(e), self.ptr(e + 8)
        return [struct.unpack_from("<4f", self.d, pp + 16 * i) for i in range(n)] if pp else []

    def inside(self, k, pt):
        e, pr, bx = self.rec(k)
        if any(bx[i + 3] - bx[i] == 0 for i in range(3)):
            return False
        return all(a * pt[0] + b * pt[1] + c * pt[2] + d <= 0 for a, b, c, d in self.planes(k))

    def leaves(self):
        """-> [(record, node file offset, stream offset, cell lo, cell hi, base)] over every record"""
        p, d, out = self.p, self.d, []
        for k in range(self.cnt):
            e, pr, bx = self.rec(k)
            if (e + 0x10) not in self.vfix:
                continue
            t = self.ptr(e + 0x10)
            seen, st = set(), [(0, np.array(bx[:3]), np.array(bx[3:]))]
            while st:
                i, lo, hi = st.pop()
                if i < 0 or i in seen or len(seen) > 100000:
                    continue
                seen.add(i)
                nd = t + 24 * i
                v = p.q(nd + 0x10)
                if v:
                    out.append((k, nd, v, lo, hi, self.base_of(nd)))
                    continue
                a, b2 = struct.unpack_from("<ii", d, nd)
                ax, sp = a & 3, struct.unpack_from("<f", d, nd + 8)[0]
                if ax > 2:
                    continue
                l2 = lo.copy()
                l2[ax] = sp
                st.append((a >> 2, l2, hi))                 # coordinate > split
                h3 = hi.copy()
                h3[ax] = sp
                st.append((b2, lo, h3))                     # coordinate <= split
        return out

    def decode(self, off, base):
        """-> (bytes, nbits) or None (not a stream of at most nbytes bytes)"""
        if base is None:
            return None
        key = (base, off)
        if key in self._dec:
            return self._dec[key]
        d, out, tab, root = self.d, bytearray(), self.tab, self.root
        cur = struct.unpack_from("<HH", d, root)
        pos, bit, res = base + off, 0, None
        try:
            while True:
                v = cur[(d[pos + (bit >> 3)] >> (7 - (bit & 7))) & 1]
                bit += 1
                if v < 0x100:
                    out.append(v)
                    if len(out) > self.nbytes:
                        break
                    cur = struct.unpack_from("<HH", d, root)
                elif v == 0x100:
                    res = (bytes(out), bit)
                    break
                else:
                    cur = struct.unpack_from("<HH", d, tab + (v - 0x101) * 4)
        except (IndexError, struct.error):
            res = None
        self._dec[key] = res
        return res

    def codetable(self):
        if self.codes is None:
            res = {}

            def rec(node, pref):
                for bit in (0, 1):
                    val = struct.unpack_from("<HH", self.d, node)[bit]
                    c = pref + str(bit)
                    if val < 0x100:
                        res[val] = c
                    elif val == 0x100:
                        res["eof"] = c
                    else:
                        rec(self.tab + (val - 0x101) * 4, c)
            rec(self.root, "")
            self.codes = res
        return self.codes

    def encode(self, data):
        """bitset bytes -> stream (trailing zero bytes dropped: the engine zeroes the buffer first); same bytes as the baked ones"""
        c = self.codetable()
        data = bytes(data).rstrip(b"\0")
        # the level's fixed Huffman tree only codes the byte values its baked sets used; a union can produce a byte with no code ->
        # widen it to the smallest coded superset (more cells visible, never fewer: safe for culling)
        sup = {}
        for x in set(data):
            if x not in c:
                cand = [y for y in c if isinstance(y, int) and y & x == x]
                if not cand:
                    raise ValueError("vis encode: byte %#x has no coded superset" % x)
                sup[x] = min(cand, key=lambda y: (bin(y).count("1"), y))
        s = "".join(c[sup.get(x, x)] for x in data) + c["eof"]
        s += "0" * ((-len(s)) % 8)
        return int(s, 2).to_bytes(len(s) // 8, "big")

    def bitset_at(self, pt):
        """what the engine decodes at a position: OR of the leaves of the highest-priority records holding it (int, little-endian bytes)"""
        p, d = self.p, self.d
        best, hits = None, []
        for k in range(self.cnt):
            e, pr, bx = self.rec(k)
            if not self.inside(k, pt) or (e + 0x10) not in self.vfix:
                continue
            t, i, nd = self.ptr(e + 0x10), 0, None
            for _ in range(100000):
                n_ = t + 24 * i
                if p.q(n_ + 0x10):
                    nd = n_
                    break
                a, b2 = struct.unpack_from("<ii", d, n_)
                i = (a >> 2) if pt[a & 3] > struct.unpack_from("<f", d, n_ + 8)[0] else b2
                if i < 0:
                    break
            if nd is None:
                continue
            if best is None or pr > best:
                best, hits = pr, []
            if pr == best:
                hits.append((p.q(nd + 0x10), self.base_of(nd)))
        acc = 0
        for off, base in hits:
            r = self.decode(off, base)
            if r is None:
                raise SystemExit("vis: the stream at %#x (page base %s) does not decode" % (off, base))
            acc |= int.from_bytes(r[0], "little")
        return acc


def _grow_box(rule, g, k, prio, bx, recs):
    """AABB of record k after "grow" (edit key "grow_rule"; default = today's behaviour for every map).
    default   : widen x / z by g
    below_max : only records whose priority is below the level's maximum
    lowest    : only the lowest-priority record(s)
    clip_hi   : widen, but never into the original box of a record of strictly higher priority
    gap       : widen, but never into the original box of a record of a different priority (only gaps and same-priority space are
                taken, so no viewer that had a record before gets a different set of records: bits can only be added)
    tiered    : records below the level's max priority: default; top-priority records: gap
    -> 6-tuple or None (record not grown)"""
    gb = [bx[0] - g, bx[1], bx[2] - g, bx[3] + g, bx[4], bx[5] + g]
    if rule == "default":
        return tuple(gb)
    prios = [r[1] for r in recs]
    if rule == "below_max":
        return tuple(gb) if prio < max(prios) else None
    if rule == "lowest":
        return tuple(gb) if prio == min(prios) else None
    if rule == "tiered":                                                          # top-priority records: gap only; the others: default
        rule = "default" if prio < max(prios) else "gap"
        if rule == "default":
            return tuple(gb)
    if rule in ("clip_hi", "gap"):
        oth = [r[2] for r in recs if r[0] != k and ((r[1] > prio) if rule == "clip_hi" else (r[1] != prio))]
        box = list(bx)
        for ax, lo_side in ((0, True), (0, False), (2, True), (2, False)):     # x- x+ then z- z+ (z slabs use the already widened x range)
            o = 2 - ax
            ext = (box[ax] - g, box[ax]) if lo_side else (box[ax + 3], box[ax + 3] + g)
            lim = ext[0] if lo_side else ext[1]
            for h in oth:
                if not (h[o] < box[o + 3] and h[o + 3] > box[o] and h[1] < box[4] and h[4] > box[1]):
                    continue                                                    # not beside this face
                if lo_side and h[ax + 3] > ext[0] and h[ax] < ext[1]:
                    lim = max(lim, min(h[ax + 3], ext[1]))
                elif not lo_side and h[ax] < ext[1] and h[ax + 3] > ext[0]:
                    lim = min(lim, max(h[ax], ext[0]))
            box[ax if lo_side else ax + 3] = lim
        return tuple(box)
    raise SystemExit("vis_open: unknown grow_rule %r" % rule)


def vis_plan(e, src_pak, log=print):
    """edit "vis_open": {"action": "vis_open", "level": L, "box": [x0,y0,z0,x1,y1,z1] (cells that overlap it are opened),
    "outside": [box whose cells' visible sets are added], "grid": 3.0 (m, sample step in `outside`)}.
    -> {"writes": [(file offset, bytes)], "targets": [...], "union_bits", "nodes"}"""
    try:
        v = VisInfo(src_pak)
    except SystemExit:
        if e.get("tolerant"):                               # auto_vis_edits: a level without VIS_INFO_1 has nothing to open
            return {"writes": [], "targets": [], "union_bits": 0, "union": 0, "unions": {}, "nodes": [], "skipped": 0}
        raise
    L = v.leaves()
    step = float(e.get("grid", 3.0))
    pairs = e.get("pairs") or [{"box": e["box"], "outside": e["outside"]}]    # several (cells to open, region whose view is added) pairs in one edit
    leafU, U, npts, tg = {}, 0, 0, []
    for pr in pairs:
        lo, hi = np.array(pr["box"][:3], float), np.array(pr["box"][3:], float)
        pt = [x for x in L if (x[3] < hi - 1e-3).all() and (x[4] > lo + 1e-3).all()]
        if not pt:
            continue
        olo, ohi = np.array(pr["outside"][:3], float), np.array(pr["outside"][3:], float)
        Up = 0
        for x in np.arange(olo[0], ohi[0] + 1e-6, step):
            for y in np.arange(olo[1], ohi[1] + 1e-6, step):
                for z in np.arange(olo[2], ohi[2] + 1e-6, step):
                    Up |= v.bitset_at((float(x), float(y), float(z)))
                    npts += 1
        for x in L:                                         # every kd cell overlapping `outside`: the point samples above (6 m) skip cells narrower than the step
            if (x[3] < ohi - 1e-3).all() and (x[4] > olo + 1e-3).all():
                r_ = v.decode(x[2], x[5])
                if r_ is not None:
                    Up |= int.from_bytes(r_[0], "little")
        for x in pt:
            if x[1] not in leafU:
                tg.append(x)
            leafU[x[1]] = leafU.get(x[1], 0) | Up
        U |= Up
    if not tg:
        if e.get("tolerant"):
            return {"writes": [], "targets": [], "union_bits": 0, "union": 0, "unions": {}, "nodes": [], "skipped": 0}
        raise SystemExit("vis_open %r: no kd leaf cell overlaps the box %s" % (e.get("name"), e["box"]))
    ub = bin(U).count("1")
    refs = {}
    for k, nd, off, clo, chi, base in L:
        refs.setdefault((base, off), []).append(nd)
    tnodes = {x[1] for x in tg}
    by_slot = {}
    for k, nd, off, clo, chi, base in tg:
        by_slot.setdefault((base, off), []).append(nd)
    writes, rep, unfit, skipped = [], [], [], 0
    ones = v.encode(b"\xff" * v.nbytes)
    for (base, off), nds in sorted(by_slot.items(), key=lambda kv: (kv[0][0] or 0, kv[0][1])):
        r = v.decode(off, base)
        if r is None:
            skipped += 1
            log("  vis: leaf stream %#x (page base %s) does not decode: left alone" % (off, base))
            continue
        own = int.from_bytes(r[0], "little")
        new = own
        for nd_ in nds:
            new |= leafU[nd_]
        enc = v.encode(new.to_bytes(max((new.bit_length() + 7) // 8, 1), "little"))
        slot = (r[1] + 7) // 8
        if v.d[base + off:base + off + slot] != v.encode(r[0]):
            raise SystemExit("vis_open: the stream at %#x does not re-encode to its own bytes (wrong decoder?)" % off)
        excl = all(n in tnodes for n in refs[(base, off)])
        if excl and len(enc) <= slot:
            writes.append((base + off, enc))
            rep.append({"off": off, "mode": "union", "bits": (bin(own).count("1"), bin(new).count("1")), "bytes": (slot, len(enc))})
        else:
            unfit.append((base, off, nds, slot, excl, own))
    if unfit:
        # the union does not fit its old slot: those leaves point at one all-visible stream stored in a big enough exclusive slot
        shared_set = 0
        for base, off, nds, sl, ex, own in unfit:
            for nd_ in nds:
                shared_set |= leafU[nd_]
            shared_set |= own                               # one stream for all of them: the union plus every old bitset
        shared = v.encode(shared_set.to_bytes(max((shared_set.bit_length() + 7) // 8, 1), "little"))
        mode = "shared-union"
        pool = [(sl, base, off) for base, off, nds, sl, ex, own in unfit if ex and sl >= len(shared)]
        if not pool:                                        # the all-visible stream is the last resort (needs the biggest slot)
            shared, shared_set, mode = ones, (1 << (8 * v.nbytes)) - 1, "all-visible"
            pool = [(sl, base, off) for base, off, nds, sl, ex, own in unfit if ex and sl >= len(shared)]
        if not pool:
            raise SystemExit("vis_open %r: %d leaves need more room than their slots hold and no exclusive slot fits the %d-byte stream" % (
                e.get("name"), len(unfit), len(shared)))
        pool.sort(reverse=True)
        _, hbase, hoff = pool[0]
        hdp = next(dp for dp, pg in enumerate(v.p.pages) if pg[0] == hbase)
        writes.append((hbase + hoff, shared))
        for base, off, nds, sl, ex, own in unfit:
            if (base, off) != (hbase, hoff):
                for nd in nds:
                    writes.append((nd + 0x10, struct.pack("<Q", hoff)))
                    writes.append((v.vfix[nd + 0x10][1] + 2, struct.pack("<H", hdp)))
            rep.append({"off": off, "mode": mode, "bits": (bin(own).count("1"), bin(shared_set).count("1")), "bytes": (sl, len(shared))})
    grown = 0
    g = float(e.get("grow", 0.0) or 0.0)
    if g > 0:
        # kd records hold only their own AABB: a viewer outside every record of a level (a gap between two records, or past the edge of the
        # outermost one) gets NO bit of that level = the whole level pops away (the supermarket interior vanished a few metres
        # outside the door).  Records that touch an opened box are widened in x / z by `grow` m: outside the old AABB the kd walk ends in
        # the edge leaf, which is one of the opened cells.
        recs = [(kk,) + tuple(v.rec(kk)[1:]) for kk in range(v.cnt)]                  # (record, priority, original AABB) before any growth
        bl = np.min([np.array(pr["box"][:3], float) for pr in pairs], 0)
        bh = np.max([np.array(pr["box"][3:], float) for pr in pairs], 0)
        for k in range(v.cnt):
            r_, prio, bx = v.rec(k)
            if (r_ + 0x10) not in v.vfix:
                continue
            blo, bhi = np.array(bx[:3]), np.array(bx[3:])
            if (blo < bh).all() and (bhi > bl).all():
                gb = _grow_box(e.get("grow_rule", "default"), g, k, prio, bx, recs)
                if gb is None:
                    continue
                writes.append((r_ + 0x18, struct.pack("<6f", *gb)))
                pp, npl = v.ptr(r_ + 8), v.p.u32(r_)
                if pp and npl == 6 and (r_ + 8) in v.vfix:     # the engine tests the record's 6 PLANES (exe+17bf8b0), not the AABB: replace the (rotated) hull by the grown box
                    pl = [(-1, 0, 0, gb[0]), (1, 0, 0, -gb[3]), (0, -1, 0, gb[1]), (0, 1, 0, -gb[4]), (0, 0, -1, gb[2]), (0, 0, 1, -gb[5])]
                    writes.append((pp, b"".join(struct.pack("<4f", *x) for x in pl)))
                else:
                    log("  vis: record %d has no 6-plane hull (%d planes): AABB only" % (k, npl))
                grown += 1
    log("  vis %s: %d kd cells overlap the box, union of %d street samples = %d bits; %d streams rewritten in place (old | union), %d leaves on one shared stream (union | their old bitsets), %d skipped" % (
        e.get("level"), len(tg), npts, ub, sum(1 for x in rep if x["mode"] == "union"), sum(1 for x in rep if x["mode"] != "union"), skipped))
    return {"writes": writes, "targets": rep, "union_bits": ub, "union": U, "unions": leafU, "nodes": sorted(tnodes), "skipped": skipped}


def verify_vis(src_path, out_path, vedits, log=print, check_stray=True):
    """re-read both paks: only the planned stream slots / leaf slots differ, every non-target leaf still decodes to the same bitset,
    every target decodes to a superset of its old bitset and to exactly old | union"""
    pa, pb = ndpak.Pak(src_path), ndpak.Pak(out_path)
    a, b = open(src_path, "rb").read(), open(out_path, "rb").read()
    ok = len(a) == len(b)
    cover = np.zeros(len(a), bool)
    tn, exp = set(), {}
    for e in vedits:
        pl = vis_plan(e, pa, lambda *x: None)
        for o, data in pl["writes"]:
            cover[o:o + len(data)] = True
        tn |= set(pl["nodes"])
        for nd in pl["nodes"]:
            exp[nd] = pl["unions"].get(nd, pl["union"])
    A, B = np.frombuffer(a, np.uint8), np.frombuffer(b, np.uint8)
    stray = int(((A != B) & ~cover).sum())
    log("  vis: %d bytes differ, %d of them outside the planned vis writes%s" % (
        int((A != B).sum()), stray, "" if check_stray else " (instance matrices of the level's other edits; verify_render checks those)"))
    ok &= stray == 0 or not check_stray
    va, vb = VisInfo(pa), VisInfo(pb)
    La, Lb = va.leaves(), vb.leaves()
    ok &= len(La) == len(Lb)
    bad_same = bad_sup = bad_exp = n_same = n_sup = 0
    for xa, xb in zip(La, Lb):
        ra, rb = va.decode(xa[2], xa[5]), vb.decode(xb[2], xb[5])
        if xa[1] in tn:
            if ra is None or rb is None:
                bad_sup += 1
                continue
            sa, sb = int.from_bytes(ra[0], "little"), int.from_bytes(rb[0], "little")
            n_sup += 1
            if sa & ~sb:
                bad_sup += 1
            if (sa | exp[xa[1]]) & ~sb:
                bad_exp += 1
        else:
            n_same += 1
            if (ra is None) != (rb is None) or (ra is not None and ra[0] != rb[0]):
                bad_same += 1
    log("  vis: %d non-target leaves keep their bitset (%d changed); %d target leaves hold old | union (%d do not), %d lose a bit" % (
        n_same, bad_same, n_sup, bad_exp, bad_sup))
    ok &= bad_same == 0 and bad_sup == 0 and bad_exp == 0
    return bool(ok)


def strip_parts_plan(e, src_render, insts):
    """edit "strip_parts": {"action": "strip_parts", "level": L, "render": {"offsets": ["0x39bb40"]}, "parts": ["game5"], "collision": false}.
    Every triangle of the instance's prototype submeshes (all LODs) whose name contains one of the `parts` strings is made degenerate
    in the shared index buffer (same pak size).  Refuses when another placement draws the same prototype (it would lose the part too).
    -> {submesh index: all its triangle numbers}"""
    offs = (e.get("render") or {}).get("offsets") if isinstance(e.get("render"), dict) else None
    if not offs or not e.get("parts"):
        raise SystemExit("edit %r: strip_parts needs render.offsets and parts" % e.get("name"))
    want = {int(o, 16) if isinstance(o, str) else int(o) for o in offs}
    sel = [it for it in insts if it.pak_off in want]
    if len(sel) != len(want):
        raise SystemExit("edit %r: strip_parts offsets not found as instances" % e.get("name"))
    cut = {}
    for it in sel:
        ids = sorted(set(it.subs) | {i for _, ids_ in it.names for i in ids_})
        for other in insts:
            if other.pak_off not in want and (set(other.subs) | {i for _, i_ in other.names for i in i_}) & set(ids):
                raise SystemExit("edit %r: prototype of %#x is also drawn by instance %#x; strip_parts would remove the part there too" % (
                    e.get("name"), it.pak_off, other.pak_off))
        for i in ids:
            nm = src_render.submeshes[i]["name"].split("|", 1)[-1]
            if any(pt in nm for pt in e["parts"]):
                cut[i] = list(range(src_render.submeshes[i]["icount"] // 3))
    if not cut:
        raise SystemExit("edit %r: no submesh name contains any of %s" % (e.get("name"), e["parts"]))
    return cut


def entry_union(level_edits, p, insts):
    """{placement offset: {draw entry offsets}} selected by the 'remove' edits of one level (render offsets), so that a placement
    whose entries are ALL removed (by one edit or several) is hidden as a whole"""
    u = {}
    if p is None:
        return u
    var = None
    for e in level_edits:
        rc = e.get("render", {})
        if e.get("action") != "remove" or not isinstance(rc, dict) or not rc.get("offsets"):
            continue
        by = {it.pak_off for it in insts}
        for o in rc["offsets"]:
            o = int(o, 16) if isinstance(o, str) else int(o)
            if o in by:
                continue
            var = _variants(p)
            if o in var:
                continue
            h = entry_of(p, list(insts) + list(var.values()), o)
            if h:
                u.setdefault(h[0].pak_off, set()).add(o)
    return u


def plan_edits(level_edits, src_render, src_phys):
    """resolve every edit against the source paks.  -> list of dicts with the selected collision keys per item index
    and the selected render instances (nothing is written)"""
    plans = []
    insts = find_instances(src_render) if src_render is not None else []
    phys = phys_items(src_phys)[1] if src_phys else []
    union = entry_union(level_edits, src_render, insts)
    for e in level_edits:
        if e["action"] == "add":                           # new solid collision (thin boxes over window / door openings)
            col = add_box_plan(e, phys)
            plans.append({"edit": e, "render": [], "collision": col, "pivot": None, "cut": {}, "room": {k: sorted(v) for k, v in ROOM.get(id(e), {}).items()}})
            continue
        if e["action"] == "cars":                          # exact SP vehicle collision at new poses (vehicle presets)
            col = car_collision_plan(e, phys)
            plans.append({"edit": e, "render": [], "collision": col, "pivot": None, "cut": {}, "room": {k: sorted(v) for k, v in ROOM.get(id(e), {}).items()}})
            continue
        if e["action"] == "vis_open":                      # visibility cells opened (garage door removed): VIS_INFO_1 bitsets
            plans.append({"edit": e, "render": [], "collision": {}, "pivot": None, "cut": {}, "vis": vis_plan(e, src_render)})
            continue
        if e["action"] == "strip_parts":                   # named parts of one prop dropped from what renders (door guide rails)
            plans.append({"edit": e, "render": [], "collision": {}, "pivot": None, "cut": strip_parts_plan(e, src_render, insts)})
            continue
        if e["action"] == "copy":                          # placement records copied over donor records (an RV for the Overpass cover)
            plans.append({"edit": e, "render": [], "collision": {}, "pivot": None, "cut": {}, "copy": copy_plan(e, src_render, insts)})
            continue
        box = _spec_box(e)
        pl = {"edit": e, "render": [], "collision": {}, "pivot": None, "cut": {}}
        rc = e.get("render", {})
        if rc is not False:
            name = (rc or {}).get("name") if isinstance(rc, dict) else None
            offs = (rc or {}).get("offsets") if isinstance(rc, dict) else None
            if offs:                                           # explicit placements (pak offsets of their matrices)
                want = {int(o, 16) if isinstance(o, str) else int(o) for o in offs}
                pl["render"] = resolve_records(src_render, insts, want, e.get("name"), union=union if e["action"] == "remove" else None)
                if e["action"] != "remove" and any(h.loc is not None for h in pl["render"]):
                    raise SystemExit("edit %r: a draw entry of a placement can only be removed, not %s" % (e.get("name"), e["action"]))
            elif isinstance(rc, dict) and rc.get("instances") is False:
                pl["render"] = []                              # a sub-mesh cut (Scene Editor geoedits): the placements in the box stay
            else:
                pl["render"] = instances_in(insts, box, name)
            if isinstance(rc, dict) and rc.get("world"):       # triangles of world-space (merged) submeshes: remove only
                if e["action"] != "remove":
                    raise SystemExit("edit %r: world-space render meshes can only be cut ('remove')" % e.get("name"))
                hid = []
                pl["cut"] = world_cut(src_render, box, rc.get("mode", "inside"), insts, rc.get("cut_name"), rc.get("cut_sub"),
                                      rc.get("cut_tris"), hide=hid, skip_shared=bool(rc.get("skip_shared")),
                                      index=rc.get("cut_index"))
                pl["render"] = list(pl["render"]) + hid
        cc = e.get("collision", {})
        if cc is not False:
            cc = cc if isinstance(cc, dict) else {}
            obb = None
            if cc.get("obb_of") is not None:
                ws = cc["obb_of"] if isinstance(cc["obb_of"], list) else [cc["obb_of"]]
                obb = []
                for w in ws:
                    want = int(w, 16) if isinstance(w, str) else int(w)
                    for hit in resolve_records(src_render, insts, {want}, e.get("name"), entries=True):
                        if hit not in obb:
                            obb.append(hit)
            for k, it in enumerate(phys):
                if cc.get("items") is not None and k not in cc["items"]:      # restrict to these phys items (wire boxes vs a prop hull in the same box)
                    continue
                if cc.get("keys") is not None:                  # explicit shape keys per phys item: {"1": [2099, 2143], ...} (tools/maps/doorway.py)
                    kl = cc["keys"].get(str(k)) or []
                    if not kl:
                        continue
                    ka_, Ta_, _ga = hc.triangles(it.mesh)
                    pos_ = {int(x): i for i, x in enumerate(ka_)}
                    miss = [x for x in kl if int(x) not in pos_]
                    if miss:
                        raise SystemExit("edit %r: collision keys %s not in phys item %d" % (e.get("name"), miss[:5], k))
                    keys = np.array([int(x) for x in kl], np.int64)
                    T = Ta_[[pos_[int(x)] for x in kl]]
                elif obb is not None:
                    keys, T = _tri_sel_obb(it.mesh, obb, float(cc.get("margin", 0.1)), cc.get("tags"))
                    if len(keys) and e["action"] in ("move", "rotate", "transform") and cc.get("close", True):
                        # whole primitives + the slivers that share vertices with the prop (inside a looser box): they move
                        # with it, and the move can then stay in place (no shared vertex with an unselected primitive)
                        lm = float(cc.get("close_margin", 0.6))

                        def loose(TT, obb=obb, lm=lm):
                            ok_ = np.zeros(len(TT), bool)
                            for inst in obb:
                                L = (np.concatenate([TT, np.ones(TT.shape[:2] + (1,))], 2) @ np.linalg.inv(inst.M))[:, :, :3]
                                ok_ |= ((L.min(1) >= inst.lo - lm) & (L.max(1) <= inst.hi + lm)).all(1)
                            return ok_
                        ka_, Ta_, ga_ = hc.triangles(it.mesh)
                        k1 = [int(x) for x in keys]
                        if cc.get("detached", True):
                            # detached pieces of the prop (a flat underside plate sharing no vertex with the body): wholly
                            # inside the loose box and carrying a shape tag the selection already has
                            sk = set(k1)
                            tg = set(int(g) for x, g in zip(ka_, ga_) if int(x) in sk)
                            cand = np.array([int(x) not in sk and int(g) in tg for x, g in zip(ka_, ga_)], bool)
                            if cand.any():
                                ci = np.nonzero(cand)[0]
                                k1 += [int(ka_[i]) for i, o in zip(ci, loose(Ta_[ci])) if o]
                        k2 = close_selection(it.mesh, k1, loose)
                        if len(k2) != len(keys):
                            pos_ = {int(x): i for i, x in enumerate(ka_)}
                            keys = np.array(k2, np.int64)
                            T = Ta_[[pos_[x] for x in k2]]
                else:
                    keys, T = _tri_sel(it.mesh, box, cc.get("tags"), cc.get("mode", "inside"), cc.get("not_tags"))
                if len(keys):
                    # whole primitives only: a quad that loses ONE of its two triangles (key ^ 1 = the other half) leaves the simd tree with a leaf
                    # that no longer matches its primitive (validate_mesh "simd leaves != prims", measured on the Jackson supermarket)
                    ka_, Ta_, _ga = hc.triangles(it.mesh)
                    have = {int(x) for x in keys}
                    pos_ = {int(x): i for i, x in enumerate(ka_)}
                    extra = [int(x) ^ 1 for x in keys if (int(x) ^ 1) not in have and (int(x) ^ 1) in pos_]
                    if extra:
                        keys = np.concatenate([keys, np.array(sorted(set(extra)), np.int64)])
                        T = np.concatenate([T, Ta_[[pos_[x] for x in sorted(set(extra))]]])
                if len(keys):
                    pl["collision"][k] = (keys, T)
        piv = e.get("pivot")
        if e["action"] == "rotate" or (e["action"] == "transform" and e.get("angle")):
            if piv == "hinge" or piv is None:
                if len(pl["render"]) != 1:
                    raise SystemExit("edit %r: pivot 'hinge' needs exactly one render instance in the box (found %d)"
                                     % (e.get("name"), len(pl["render"])))
                pl["pivot"] = pl["render"][0].M[3, :3].copy()
            else:
                pl["pivot"] = np.array(piv, float)
        plans.append(pl)
    return plans


def _harmless_key(t, ref):
    """sort key of a collision triangle that has to stay behind (its section would be emptied): (class, height).  class 0 = it lies
    within 8 cm of the reference collision's surface samples (10 cm grid: a coincident duplicate, no effect), 1 = completely above `ref`.hi_y (over the play
    space: out of reach), 2 = anything else (lowest first: the one most likely under the floor).  ref = (cKDTree of reference
    surface samples, hi_y)"""
    tree, hi_y = ref
    P = np.vstack([t.mean(0)[None], t, (t + np.roll(t, 1, 0)) / 2])
    d = float(tree.query(P)[0].max())
    if d <= 0.08:
        return (0, 0.0)
    if float(t[:, 1].min()) > hi_y:
        return (1, 0.0)
    return (2, float(t[:, 1].max()))


def ref_surface(levels, work_dir, game=None, step=0.1, box=None):
    """cKDTree of surface samples of the stock collision (-phys) of `levels` (triangle vertices + centroid + a grid of `step` m on the
    big triangles), for _harmless_key"""
    from scipy.spatial import cKDTree
    pts = []
    for lv in levels:
        pth = fetch(lv, os.path.join(work_dir, "src"), game, ("-phys",))["-phys"]
        for it in phys_items(pth)[1]:
            keys, T, tg = hc.triangles(it.mesh)
            if len(T) == 0:
                continue
            T = T.astype(np.float64)
            if box is not None:
                m = ((T.max(1)[:, [0, 2]] >= [box[0], box[2]]) & (T.min(1)[:, [0, 2]] <= [box[1], box[3]])).all(1)
                T = T[m]
            tg = tg[m] if box is not None else tg
            T = T[tg != 65535]
            pts.append(T.mean(1))
            pts.append(T.reshape(-1, 3))
            a, b, c = T[:, 0], T[:, 1], T[:, 2]
            area = np.linalg.norm(np.cross(b - a, c - a), axis=1) / 2
            for i in np.nonzero(area > step * step * 2)[0]:
                n = int(np.sqrt(area[i]) / step) + 1
                for u in range(n + 1):
                    for v in range(n + 1 - u):
                        pts.append((a[i] + (b[i] - a[i]) * u / n + (c[i] - a[i]) * v / n)[None])
    return cKDTree(np.concatenate(pts))


def apply_plans(plans, render_bytes, phys_path, out_render, out_phys, log=print, src_pak=None, sliver_ref=None):
    """write the edited paks.  render_bytes: source <level>.pak bytes or None; phys_path: source <level>-phys.pak or None"""
    rb = bytearray(render_bytes) if render_bytes is not None else None
    pp = ndpak.Pak(phys_path) if phys_path else None
    pbuf = PakBuf(pp.d) if pp else None
    items = [PhysItem(pp, n, io) for n, t, pi, io in pp.items if t == "COLLISION_DATA_HAVOK_BG"] if pp else []
    # collect per item: (drop keys, add tris + attrs)
    per = {}
    for pl in plans:
        e = pl["edit"]
        act = e["action"]
        for do, rec, sit, dit, nm in pl.get("copy", []):
            rb[do:do + REC] = rec
            log("  render copy %-12s %s (record %#x) over donor %#x (%s) at %s" % (nm, sit.proto.split("/")[-1], sit.pak_off, do,
                                                                                dit.proto.split("/")[-1], np.round(np.frombuffer(rec, "<f4", 3, 48), 3).tolist()))
        for o_, data_ in (pl.get("vis") or {}).get("writes", []):
            rb[o_:o_ + len(data_)] = data_
        for it in pl["render"]:
            if it.loc is not None:        # one draw entry of a placement: its own matrix (placement-relative) hidden like a placement
                M = edit_matrix(it.loc, "remove", None, None, 0.0, (e.get("render") or {}).get("hide_dy", -1000.0) if isinstance(e.get("render"), dict) else -1000.0)
                rb[it.pak_off:it.pak_off + 64] = M.astype("<f4").tobytes()
                log("  render %-34s remove draw entry %d of %d (placement %#x) @%#x  world %s -> local y %+.1f" % (
                    ", ".join(n for n, _ in it.names) or "(unnamed)", it.idx, it.count, it.parent.pak_off, it.pak_off,
                    np.round(it.M[3, :3], 3).tolist(), M[3, 1] - it.loc[3, 1]))
                continue
            if act == "scale_y":          # partly-open door: y basis scaled by e["sy"], top edge (world) kept
                M = it.M.copy()
                top = float(it.whi[1])
                M[1, :3] *= float(e["sy"])
                M[3, 1] = top - float(e["sy"]) * (top - it.M[3, 1])
            else:
                M = edit_matrix(it.M, act, pl["pivot"], e.get("delta"), e.get("angle", 0.0),
                                (e.get("render") or {}).get("hide_dy", -1000.0) if isinstance(e.get("render"), dict) else -1000.0)
            rb[it.pak_off:it.pak_off + 64] = M.astype("<f4").tobytes()
            log("  render %-34s %s  instance @%#x  %s -> %s" % (", ".join(n for n, _ in it.names) or "(unnamed)", act, it.pak_off,
                                                              np.round(it.M[3, :3], 3).tolist(), np.round(M[3, :3], 3).tolist()))
        for si, tris in pl["cut"].items():
            cut_triangles(rb, src_pak, si, tris)
            log("  render world-space submesh #%d %s: %d triangles cut (degenerate)" % (si, src_pak.submeshes[si]["name"][-60:], len(tris)))
        for k, (keys, T) in pl["collision"].items():
            d = per.setdefault(k, {"drop": [], "add": []})
            if act in ("add", "cars"):
                d["add"].append((keys, T))
                d["drop"].extend(pl.get("room", {}).get(k, []))
                log("  collision item %d: add %d triangles" % (k, len(T)))
                continue
            ccfg = e.get("collision") if isinstance(e.get("collision"), dict) else {}
            if act in ("move", "rotate", "transform") and ccfg.get("inplace", True):
                # same triangles, same shape keys: vertices re-quantised in place, trees refitted (no growth); primitives that
                # share vertices with unselected ones (or use packed vertices) fall back to remove + add in apply below
                def fnc(P, e=e, pv=pl["pivot"], act=act):
                    return np.asarray(transform_point(np.asarray(P, float), act, pv, e.get("delta"), e.get("angle", 0.0)), float)
                d.setdefault("inplace", []).append((np.asarray(keys, np.int64), np.asarray(T, float), fnc))
                log("  collision item %d: %s %d triangles (%s), in place" % (k, act, len(keys), "sections " + ",".join(str(s) for s in sorted({int(x) >> 8 for x in keys}))))
                continue
            d["drop"].extend(int(x) for x in keys)
            if act == "remove" and ccfg.get("orphans"):    # Scene Editor removals: their floating remnants go too (orphan_fragments)
                d.setdefault("removed", []).extend(int(x) for x in keys)
            if act != "remove":
                new = np.array([transform_point(t, act, pl["pivot"], e.get("delta"), e.get("angle", 0.0)) for t in T])
                d["add"].append((keys, new))
            log("  collision item %d: %s %d triangles (%s)" % (k, act, len(keys), "sections " + ",".join(str(s) for s in sorted({int(x) >> 8 for x in keys}))))
    report = {"items": {}}
    for k, d in sorted(per.items(), key=lambda kv: -items[kv[0]].tag_off):     # high file offsets first: growing a page moves only later pages
        it = items[k]
        m = it.mesh
        for keys_i, T_i, fnc in d.get("inplace", []):
            m, done, rest = move_in_place(m, keys_i, fnc)
            log("  item %d: %d triangles moved in place, %d by remove + add (shared vertices / packed section)" % (k, len(done), len(rest)))
            if rest:
                rs = set(rest)
                idx = [i for i, x in enumerate(keys_i) if int(x) in rs]
                d["drop"].extend(rest)
                d["add"].append((keys_i[idx], fnc(T_i[idx].reshape(-1, 3)).reshape(-1, 3, 3)))
        kall, Tall, _ = hc.triangles(m)
        if d.get("removed"):
            orph, rem_ = [], set(d["removed"])
            for _round in range(4):                         # dropping a remnant can leave the piece beside it floating
                o_ = orphan_fragments(kall, Tall, rem_, set(d["drop"]) | set(orph))
                if not o_:
                    break
                orph += o_
                rem_ |= set(o_)
            if orph:
                d["drop"].extend(orph)
                log("  item %d: %d orphan collision triangles left floating by removals dropped too (small pieces that touched a removed one, floor kept)" % (k, len(orph)))
        keys_all = sorted(set(d["drop"]))
        # A section that loses EVERY primitive would have to leave the section tree (_tree5_without: never seen in the game,
        # and validate_mesh counts one tree leaf per section).  Keep the smallest triangle of such a section instead: it ends
        # up as a stray sliver where the removed prop stood.
        left = {}
        for kk in kall:
            left.setdefault(int(kk) >> 8, set()).add(int(kk))
        dropped = set(keys_all)
        kept_secs = []
        for si_, ks_ in sorted(left.items()):
            if ks_ <= dropped:
                cand = {int(kk): (0.5 * float(np.linalg.norm(np.cross(t[1] - t[0], t[2] - t[0]))), float(t[:, 1].max()))
                        for kk, t in zip(kall, Tall) if int(kk) >> 8 == si_}
                pool = ([c for c in cand if cand[c][0] >= 0.01 and not c & 1] or [c for c in cand if not c & 1] or list(cand))   # fallback: a section of only tiny / odd-keyed triangles (a small prop's own section, workbench strip)
                keep_k = min(pool, key=cand.get)   # the smallest proper triangle: no sliver, and the first of its prim (the simd leaf is keyed by it)
                if sliver_ref is not None:         # "keep_harmless_vs": the kept triangle should not be an obstacle (see _harmless_key)
                    tmap = {int(kk): t for kk, t in zip(kall, Tall) if int(kk) >> 8 == si_}
                    keep_k = min(pool, key=lambda c: _harmless_key(tmap[c], sliver_ref) + (cand[c][0],))
                keys_all.remove(keep_k)
                dropped.discard(keep_k)
                kept_secs.append((si_, keep_k, cand[keep_k][0]))
                log("  item %d: section %d would be emptied; kept its smallest triangle (key %#x, area %.4f m2, top y %.2f)" % (
                    k, si_, keep_k, cand[keep_k][0], cand[keep_k][1]))
        adds = []
        for keys, new in d["add"]:
            if isinstance(keys, dict):                      # "cars": attributes given per triangle (exact SP shapes)
                adds.append((new, keys["direct"][0], keys["direct"][1]))
                continue
            attr = tri_attrs(m, keys)
            bl = np.unpackbits(np.frombuffer(it.blob, np.uint8), bitorder="little")
            bv = [int(bl[3 * int(x)]) | int(bl[3 * int(x) + 1]) << 1 | int(bl[3 * int(x) + 2]) << 2 for x in keys]
            adds.append((new, attr, bv))
        m2, keymap, changed = remove_keys(m, keys_all)
        nshr = 0
        for si_, kk_, a_ in kept_secs:                      # the kept triangles become ~2 cm specks (no floating collision where the props stood)
            r_ = shrink_kept_triangle(m2, si_)
            if r_ is None:
                log("  item %d: section %d kept triangle %#x left as is (already a speck, vertices shared with other primitives, or no surface within 1.5 m)" % (k, si_, kk_))
                continue
            m2 = r_[0]
            nshr += 1
            log("  item %d: section %d kept triangle %#x shrunk %.4f -> %.5f m2 at %s" % (k, si_, kk_, r_[1], r_[2], np.round(r_[3], 2).tolist()))
        if kept_secs:
            log("  item %d: %d of %d kept triangles shrunk" % (k, nshr, len(kept_secs)))
        blob = remap_key_table(it.blob, it.nbits, keymap, set(keys_all), changed)
        nkeys = []
        for new, attr, bv in adds:
            m2, blob, nk = add_triangles(m2, new, attr, bv, blob)
            nkeys += nk
        pbuf, n_new = write_item(pbuf, it, m2, blob)
        report["items"][k] = {"dropped": len(keys_all), "added": len(nkeys), "tag bytes": (it.tsz, n_new)}
        log("  item %d tagfile %d -> %d bytes" % (k, it.tsz, n_new))
    if rb is not None and out_render:
        os.makedirs(os.path.dirname(out_render), exist_ok=True)
        open(out_render, "wb").write(bytes(rb))
    if pbuf is not None and out_phys:
        os.makedirs(os.path.dirname(out_phys), exist_ok=True)
        open(out_phys, "wb").write(bytes(pbuf))
    return report


VIS_SKIP = ("-const", "sky-", "audio", "texture-adjust", "-fx", "part-", "to1-pvp-", "t2r-", "-render", "cubemaps", "-vis", "accessibility", "-script", "-pickups")


def auto_vis_edits(edits, levels, reach=None, near=None, grid=6.0, merge=12.0, grow_rule=None):
    """Removed geometry (the garage door, shelves, walls ...) still occludes: every level pak carries a precomputed visibility set (VIS_INFO_1,
    section 10 of re/maps/level-edit.md) that was baked with the geometry in place, so a viewer behind a removed wall is culled from everything
    the wall used to hide.  One tolerant "vis_open" edit per art level of the map, with one pair per cluster of removals: every kd cell within
    `reach` m of the removal gets (its own bitset | what the cells within `near` m of the removal see (30 m: a removed entrance barricade must show the whole store interior behind it)).  Cost: some extra objects stay in the
    draw list near the removals (the frustum still culls); nothing is hidden that was visible.  T2R_AUTO_VIS=0 turns it off,
    T2R_VIS_REACH / T2R_VIS_NEAR override the distances; `grow_rule` (sp_maps.json "auto_vis_grow_rule", env T2R_VIS_GROW_RULE) = which kd records the 24 m "grow" widens (see _grow_box).  On for EVERY map with removals (sp_maps.json "auto_vis": false opts a map out)."""
    if os.environ.get("T2R_AUTO_VIS", "1") == "0":
        return []
    reach = float(os.environ.get("T2R_VIS_REACH", reach if reach is not None else 45.0))
    near = float(os.environ.get("T2R_VIS_NEAR", near if near is not None else 30.0))
    boxes = []
    for e in edits:
        if e.get("action") == "remove" and e.get("box") and e.get("level") and (e.get("render") is not False or e.get("collision") is not False):
            boxes.append(np.array(e["box"], float))
    if not boxes:
        return []
    cl = []                                                  # greedy clusters: touching boxes (within 2 m) merge while the cluster stays under `merge` m
    for b in boxes:
        for c in cl:
            m = np.r_[np.minimum(c[:3], b[:3]), np.maximum(c[3:], b[3:])]
            if (b[:3] < c[3:] + 2.0).all() and (b[3:] > c[:3] - 2.0).all() and (m[3:] - m[:3]).max() <= merge:
                c[:] = m
                break
        else:
            cl.append(b.copy())
    pairs = [{"box": (c + np.r_[[-reach] * 3, [reach] * 3]).round(2).tolist(), "outside": (c + np.r_[[-near] * 3, [near] * 3]).round(2).tolist()} for c in cl]
    allb = np.r_[np.min([c[:3] for c in cl], 0), np.max([c[3:] for c in cl], 0)]
    out = []
    for lv in levels:
        if any(t in lv for t in VIS_SKIP) or lv.endswith(("-rs", "-audio", "-audio-rgn")):      # (-rs = the Part I render-settings level, -audio* = the Part I ambience levels: no geometry)
            continue
        out.append({"name": "auto vis (removed geometry)", "level": lv, "action": "vis_open", "tolerant": True, "grid": grid, "pairs": pairs, "grow": float(os.environ.get("T2R_VIS_GROW", 24.0)), "grow_rule": os.environ.get("T2R_VIS_GROW_RULE") or grow_rule or "default",
                    "box": allb.round(2).tolist(), "outside": allb.round(2).tolist(), "render": False, "collision": False})
    return out


def spec_edits(key):
    """a map key of sp_maps.json, or the path of a {"edits": [...]} file"""
    if os.path.isfile(key):
        return json.load(open(key, encoding="utf-8"))["edits"]
    maps = json.load(open(SPEC, encoding="utf-8"))["maps"]
    m = next(x for x in maps if x["key"] == key)
    edits = m.get("edits", [])
    rp = os.path.join(HERE, "data", "%s-sealremove.json" % key)      # Scene Editor "Remove this seal": names of added collision boxes to drop (the spec itself stays as it is)
    if os.path.exists(rp):
        rm = set(json.load(open(rp, encoding="utf-8")).get("remove", []))
        out = []
        for e in edits:
            if e.get("action") == "add" and e.get("boxes") and (e.get("name") in rm or any(b.get("name") in rm for b in e["boxes"])):
                keep = [b for b in e["boxes"] if b.get("name") not in rm and e.get("name") not in rm]
                if not keep:
                    continue
                e = dict(e, boxes=keep)
            out.append(e)
        edits = out
    import openings                                                  # holes cut into seals + extra edits of data/fixes/openings-<key>.json (not the Scene Editor's files)
    edits = openings.apply(key, edits)
    return edits + prefab_car_edits(m)


def prefab_car_edits(m):
    """the exact-collision "cars" edits of a map's placed vehicle presets (sp_maps.json "prefabs", tools/maps/vehicle_presets.py)"""
    if not m.get("prefabs"):
        return []
    import vehicle_presets
    return vehicle_presets.expand_map(m)["car_edits"]


def editor_edits_path(key):
    """tools/maps/<map>-editor-edits.json: baked-object edits written by the Scene Editor (move / yaw / remove)"""
    return os.path.join(HERE, "%s-editor-edits.json" % key)


def edits_for(key, opts):
    """a map's edits; with --editor also the Scene Editor's pending edits of that map (appended, applied after the map's own)"""
    edits = spec_edits(key)
    if not os.path.isfile(key):                               # geometry removals made in the Scene Editor (tools/maps/geoedit.py), always applied
        import geoedit
        ge = geoedit.edits_for(key)
        if ge:
            print("  + %d Scene Editor geometry removal(s) from data/%s-geoedits.json" % (len(ge), key))
            edits = edits + ge
    if opts.get("--editor") and not os.path.isfile(key):
        pe = editor_edits_path(key)
        if os.path.exists(pe):
            extra = json.load(open(pe, encoding="utf-8"))["edits"]
            print("  + %d Scene Editor edits from %s" % (len(extra), os.path.basename(pe)))
            edits = edits + extra
        else:
            print("  (no %s)" % os.path.basename(pe))
    if not os.path.isfile(key) and not opts.get("--no-vis") and next(x for x in json.load(open(SPEC, encoding="utf-8"))["maps"] if x["key"] == key).get("auto_vis", True):
        mm_ = next(x for x in json.load(open(SPEC, encoding="utf-8"))["maps"] if x["key"] == key)
        av = auto_vis_edits(edits, map_levels(key), grow_rule=mm_.get("auto_vis_grow_rule"))
        if av:
            print("  + %d auto vis edit(s): %d cluster(s) of removed geometry" % (len(av), len(av[0]["pairs"])))
            edits = edits + av
    return edits


def map_levels(key):
    """the art levels a map loads (sp_maps.json "levels"; our own spawner pak left out), or a spec file's "levels" list"""
    if os.path.isfile(key):
        return json.load(open(key, encoding="utf-8")).get("levels", [])
    m = next(x for x in json.load(open(SPEC, encoding="utf-8"))["maps"] if x["key"] == key)
    return [x for x in m["levels"] if x != m["pak"]]


def levels_of(edits):
    out = []
    for e in edits:
        if e["level"] not in out:
            out.append(e["level"])
    return out


_CODE_DEPS = ("level_edit.py", "geoedit.py", "level_morph.py", "coll_edit.py", "havok_convert.py", "snow_fill.py", "snow_stitch.py", "openings.py")


def _digest_parts(edits, src_paths):
    """{input: sha1[:10]} of everything a level's edited pak depends on: the edit list, the source archives, each code module"""
    parts = {"edits": hashlib.sha1(json.dumps(edits, sort_keys=True).encode()).hexdigest()[:10]}
    parts["src"] = hashlib.sha1("|".join(str(os.path.getsize(p)) for p in src_paths).encode()).hexdigest()[:10]
    for n in _CODE_DEPS:
        for d in (HERE, os.path.join(HERE, "..", "models")):
            f = os.path.join(d, n)
            if os.path.exists(f):
                parts["code:" + n] = hashlib.sha1(open(f, "rb").read()).hexdigest()[:10]
                break
    return parts


def _digest(edits, src_paths):
    return hashlib.sha1(json.dumps(_digest_parts(edits, src_paths), sort_keys=True).encode()).hexdigest()[:12]


def _edit_level(lv, le, work_dir, out_dir, game, sig, parts, log=print):
    """the ordinary edits of ONE level (build_edits' loop body for a stale level) -> [paths written]"""
    need_r = any(e.get("render", {}) is not False or (e.get("collision") or {}).get("obb_of") is not None or e["action"] == "vis_open" for e in le)
    need_c = any(e.get("collision", {}) is not False for e in le)
    suf = tuple(s for s, f in (("", need_r), ("-phys", need_c)) if f)
    stamp = os.path.join(out_dir, lv + ".stamp")
    src = fetch(lv, os.path.join(work_dir, "src"), game, suf)
    sr = ndpak.Pak(src[""]) if "" in src else None
    plans = plan_edits(le, sr, src.get("-phys"))
    for pl in plans:
        if not pl["render"] and not pl["collision"] and not pl["cut"] and not pl.get("copy") and not (pl.get("vis") or {}).get("writes") and not pl["edit"].get("tolerant"):
            raise SystemExit("level edit %r: nothing inside the box %s (no render instance, no collision triangle)" % (
                pl["edit"].get("name"), pl["edit"]["box"]))
    out_r = os.path.join(out_dir, lv + ".pak") if sr else None
    out_p = os.path.join(out_dir, lv + "-phys.pak") if "-phys" in src else None
    log("level %s" % lv)
    sref = None
    hv = [e.get("collision", {}).get("keep_harmless_vs") for e in le if isinstance(e.get("collision"), dict)]
    hv = [x for x in hv if x]
    if hv:      # a section emptied by the edit keeps one triangle: pick one that is no obstacle (coincident with these levels' collision; 503f7e9a, Into the City)
        lvs = sorted({x for h in hv for x in h})
        log("  reference collision for the kept triangles: %s" % ", ".join(lvs))
        hi = max(float(e.get("collision", {}).get("keep_harmless_above", 31.5)) for e in le if isinstance(e.get("collision"), dict))
        sref = (ref_surface(lvs, work_dir, game, box=(150, 420, 380, 700)), hi)
    rep = apply_plans(plans, open(src[""], "rb").read() if sr else None, src.get("-phys"), out_r, out_p, log, sr, sref)
    files = []
    for pth, flag in ((out_r, sr is not None and any(p["render"] or p["cut"] or p.get("copy") or (p.get("vis") or {}).get("writes") for p in plans)), (out_p, bool(rep["items"]))):
        if pth and flag:
            files.append(pth)
        elif pth and os.path.exists(pth):
            os.remove(pth)
    json.dump({"sig": sig, "parts": parts, "files": files}, open(stamp, "w"))
    return files


def build_edits(edits, work_dir=None, out_dir=None, game=None, log=print):
    """Run every edit of a map: fetch the source paks of each level, write <out_dir>/<level>[-phys].pak.
    -> [paths written]  (sp_maps_build.stage_edits copies them into the staged mod tree's pak68/)"""
    work_dir = work_dir or CACHE
    out_dir = out_dir or os.path.join(work_dir, "out")
    written = []
    all_edits = list(edits)
    morph = [e for e in edits if e.get("action") in ("morph", "detach")]       # level_morph.py (Scene Editor Morph / Detach): run after the ordinary edits of their level
    colled = [e for e in edits if e.get("action") == "colledit"]                 # coll_edit.py (Scene Editor Collision edit): last stage
    edits = [e for e in edits if e not in morph and e not in colled]
    todo = []                                       # [(level, level edits, sig, parts)] of the levels whose edited paks are stale
    slot = {}                                       # level -> position in `written` order
    order = []
    for lv in levels_of(edits):
        le = [e for e in edits if e["level"] == lv]
        parts = _digest_parts(le, world_archives(game))
        sig = _digest(le, world_archives(game))
        stamp = os.path.join(out_dir, lv + ".stamp")
        if os.path.exists(stamp):
            try:
                st = json.load(open(stamp))
            except ValueError:
                st = {}
            if st.get("sig") == sig and all(os.path.exists(f) for f in st.get("files", [])):
                log("level %s: edited paks up to date (%s): %s" % (lv, sig, ", ".join(os.path.basename(f) for f in st["files"])))
                order.append((lv, st["files"]))
                continue
            if st.get("parts"):
                log("level %s: edited paks stale, changed inputs: %s" % (lv, ", ".join(k for k in sorted(set(parts) | set(st["parts"])) if parts.get(k) != st["parts"].get(k)) or "(files missing)"))
            else:
                log("level %s: edited paks stale (stamp has no input list)" % lv)
        order.append((lv, None))
        todo.append((lv, le, sig, parts))
    # the stale levels are independent (own source paks, own output files, no shared state): one child interpreter each (parjobs.py, T2R_PAR_JOBS=1 = serial)
    if todo:
        import parjobs
        built = parjobs.run([("level_edit", "_edit_level", (lv, le, work_dir, out_dir, game, sig, parts), {}) for lv, le, sig, parts in todo], log=log)
        done = {t[0]: b for t, b in zip(todo, built)}
    for lv, files in order:
        written += files if files is not None else done[lv]
    if morph:
        import level_morph
        written = level_morph.apply_all(morph, written, work_dir, out_dir, game, log)
    if colled:
        import coll_edit
        written = coll_edit.apply_all(colled, written, work_dir, out_dir, game, log)
    # ghost shadow proxies (dark patches = shadows of removed things): cut orphan proxy triangles in every removal / morph box, fail if any is left
    import ghost_shadow_audit
    written = ghost_shadow_audit.sweep_to(written, all_edits, out_dir, log)      # (cut copies in <out_dir>/swept: the cached stage outputs are never edited in place)
    # roof shadow caps (sun through the Supermarket ceiling with door sun on): casters under the roofs SP never shadow-capped
    import shadow_caps
    shadow_caps.apply_all(written, log)
    # baked lightmap atlas (dark patches): rebake the texels that were buried under / inside now-gone geometry (lightmap_fix.py)
    import lightmap_fix
    lightmap_fix.apply(written, all_edits, work_dir, game, log)
    return written


# ================================================================================================== verification
def verify_phys(src_path, out_path, edits_level, log=print):
    """re-read the written phys pak with the repo readers and compare with the source.  Returns True when everything holds."""
    ok = True
    a_items = phys_items(src_path)[1]
    b_items = phys_items(out_path)[1]
    if len(a_items) != len(b_items):
        log("  item count differs")
        return False
    pa, pb = ndpak.Pak(src_path), ndpak.Pak(out_path)

    def page_of(p, off):
        return next(i for i, (s, z, f) in enumerate(p.pages) if s <= off < s + z)

    def fixrel(p):
        return {(page_of(p, k), k - p.pages[page_of(p, k)][0]): v for k, v in p.fix.items()}
    if len(pa.pages) != len(pb.pages) or [f for _, _, f in pa.pages] != [f for _, _, f in pb.pages]:
        log("  page list changed")
        ok = False
    if fixrel(pa) != fixrel(pb):
        log("  fixup table changed")
        ok = False
    if [(n, t) for n, t, _, _ in pa.items] != [(n, t) for n, t, _, _ in pb.items]:
        log("  item list changed")
        ok = False
    changed = [i for i in range(len(a_items)) if a_items[i].raw != b_items[i].raw or a_items[i].blob != b_items[i].blob]
    # per page: bytes that differ outside the edited items' tagfile (whole page tail when it grew), key table and size field
    allowed = {}
    for i in changed:
        it = a_items[i]
        pg = page_of(pa, it.tag_off)
        s0 = pa.pages[pg][0]
        grown = pb.pages[pg][1] != pa.pages[pg][1]
        allowed.setdefault(pg, []).append((it.tag_off - s0, (pb.pages[pg][1] if grown else it.tsz + it.tag_off - s0) - (it.tag_off - s0)))
        pg2 = page_of(pa, it.blob_off)
        allowed.setdefault(pg2, []).append((it.blob_off - pa.pages[pg2][0], len(it.blob)))
        pg3 = page_of(pa, it.io)
        allowed.setdefault(pg3, []).append((it.io + 48 + 12 - pa.pages[pg3][0], 4))
    diff = stray = 0
    for pg, ((sa, za, _), (sb, zb, _)) in enumerate(zip(pa.pages, pb.pages)):
        A = np.frombuffer(pa.d, np.uint8, za, sa)
        B = np.frombuffer(pb.d, np.uint8, zb, sb)
        m = min(za, zb)
        ne = np.zeros(max(za, zb), bool)
        ne[:m] = A[:m] != B[:m]
        ne[m:] = True
        diff += int(ne.sum())
        for off, ln in allowed.get(pg, []):
            ne[off:off + ln] = False
        if pa.d[sa:sa + 12] != pb.d[sb:sb + 12] or pa.d[sa + 16:sa + 20] != pb.d[sb + 16:sb + 20]:
            log("  page %d header changed" % pg)
            ok = False
        ne[12:16] = False if zb != za else ne[12:16]          # page size field of a grown page
        stray += int(ne.sum())
    # file range right after the last page and the header block before the first page
    if pa.d[:pa.pages[0][0]] != pb.d[:pb.pages[0][0]]:
        hd = [k for k in range(0, pa.pages[0][0], 4) if pa.d[k:k + 4] != pb.d[k:k + 4]]
        # page table entries (start / size) legitimately move with a grown page
        pt = struct.unpack_from("<I", pa.d, 20)[0]
        extra = [k for k in hd if not (pt <= k < pt + 12 * len(pa.pages) and (k - pt) % 12 in (0, 4))]
        if extra:
            log("  file header changed at %s" % [hex(k) for k in extra])
            ok = False
    log("  page bytes changed: %d, outside the edited items' tagfile / key table / size field: %d%s" % (
        diff, stray, "  (a page grew: pak %d -> %d bytes)" % (len(pa.d), len(pb.d)) if len(pa.d) != len(pb.d) else ""))
    ok &= stray == 0
    for i, (a, b) in enumerate(zip(a_items, b_items)):
        if a.raw == b.raw and a.blob == b.blob:
            continue
        mb = b.mesh
        if hc.havok_tag.Tag.parse(b.raw).encode() != b.raw:
            log("  item %d: tagfile re-encode differs" % i)
            ok = False
        if hc.encode_t2(mb, b.tag) != b.raw:
            log("  item %d: mesh model re-encode differs" % i)
            ok = False
        ka, Ta, ga = hc.triangles(a.mesh)
        kb, Tb, gb = hc.triangles(mb)
        bad = hc.validate_mesh(mb)
        if bad.get("key header") and mb.maxkey == int(kb.max()) and mb.nbits == mb.maxkey + 1 \
                and mb.npk - len(kb) == a.mesh.npk - len(ka):
            del bad["key header"]               # ND's numPrimitiveKeys sits a fixed offset above the triangle count in some items
        bad.update(check_tree4(mb))
        ba = hc.validate_mesh(a.mesh)
        ba.update(check_tree4(a.mesh))
        for kx in list(bad):                    # ND's own trees have a few boxes a hair too tight: only NEW violations count
            if bad[kx] <= ba.get(kx, 0):
                del bad[kx]
        if bad:
            log("  item %d: structure %s" % (i, bad))
            ok = False
        log("  item %d: %d -> %d triangles, %d -> %d sections, tagfile %d -> %d bytes, maxkey %d -> %d" % (
            i, len(Ta), len(Tb), len(a.mesh.sections), len(mb.sections), a.tsz, b.tsz, a.mesh.maxkey, mb.maxkey))
        if b.nbits != a.nbits or len(b.blob) != len(a.blob):
            log("  item %d: key table size changed" % i)
            ok = False
        # key table / interior bits / tags must follow their triangles: compare as multisets keyed by geometry
        def sig(T, g, k, m, blob):
            bl = np.unpackbits(np.frombuffer(blob, np.uint8), bitorder="little")
            wd = _bits(m.words, 32 * len(m.words))
            out = {}
            for t, tg, kk in zip(T, g, k):
                key = tuple(np.round(t.reshape(-1), 3))
                out.setdefault(key, []).append((int(tg), int(wd[kk]) if kk < len(wd) else 0,
                                                int(bl[3 * kk]) | int(bl[3 * kk + 1]) << 1 | int(bl[3 * kk + 2]) << 2))
            return out
        sa, sb_ = sig(Ta, ga, ka, a.mesh, a.blob), sig(Tb, gb, kb, mb, b.blob)
        gone = 0
        for key, v in sa.items():
            w = sb_.get(key, [])
            if len(w) < len(v):
                gone += len(v) - len(w)
        new = sum(max(0, len(v) - len(sa.get(key, []))) for key, v in sb_.items())
        mism = 0
        for key, v in sb_.items():
            if key in sa and sorted(v)[:len(sa[key])] != sorted(sa[key])[:len(v)] and len(v) == len(sa[key]):
                mism += 1
        log("  item %d: triangles gone %d, new/moved %d, surviving triangles whose tag / interior bit / material bits changed: %d" % (i, gone, new, mism))
        ok &= mism == 0
        # moves must be rigid: a triangle that keeps its key and changed position kept its edge lengths (a vertex shared with
        # an unselected triangle would have dragged that one out: a stretched sliver = an invisible wall), and, where the
        # edit's transform is known, sits exactly where the edit puts it; no triangle got an edge > its old longest + 0.5 m
        def edges(T):
            return np.stack([np.linalg.norm(T[:, j] - T[:, (j + 1) % 3], axis=1) for j in range(3)], 1)
        pos_a = {int(x): t for x, t in zip(ka, Ta)}
        mv_edits = [e for e in edits_level if e["action"] in ("move", "rotate", "transform")]
        # shape keys only identify triangles when nothing was dropped / re-added in this item (in-place moves keep every key);
        # otherwise compare geometry: every new triangle must be a rigid copy of a gone one (unless the level has edits that
        # legitimately make new shapes: add / scale_y / copy)
        keyed = len(ka) == len(kb) and set(int(x) for x in ka) == set(int(x) for x in kb)
        same = [(pos_a[int(x)], t) for x, t in zip(kb, Tb) if int(x) in pos_a] if keyed else []
        stretched = nonrigid = stray_mv = 0
        if not keyed and not any(e["action"] in ("add", "cars", "scale_y", "copy") for e in edits_level):
            ga_ = [np.array(k_, float).reshape(3, 3) for k_, v in sa.items() for _ in range(len(v) - len(sb_.get(k_, [])))]
            nb_ = [np.array(k_, float).reshape(3, 3) for k_, v in sb_.items() for _ in range(len(v) - len(sa.get(k_, [])))]
            if nb_:
                en = np.sort(edges(np.array(nb_)), 1)
                eg = np.sort(edges(np.array(ga_)), 1) if ga_ else np.zeros((0, 3))
                for r in en:
                    if not len(eg) or np.abs(eg - r).max(1).min() > 0.01:
                        nonrigid += 1
                stretched += int((en.max(1) > (eg.max() if len(eg) else 0.0) + 0.5).sum())
        if same:
            A_, B_ = np.array([u for u, _ in same]), np.array([v for _, v in same])
            chg = np.abs(A_ - B_).max((1, 2)) > 1e-4
            ea, eb = edges(A_), edges(B_)
            stretched += int((eb.max(1) > ea.max(1) + 0.5).sum())
            nonrigid = int((chg & (np.abs(ea - eb).max(1) > 0.01)).sum())
            for t0, t1 in zip(A_[chg], B_[chg]):
                hit = False
                for e in mv_edits:
                    piv = e.get("pivot")
                    if e["action"] != "move" and not (isinstance(piv, (list, tuple)) and len(piv) == 3):
                        hit = True                      # pivot resolved at plan time ('hinge'): rigidity is checked above
                        break
                    w = transform_point(t0, e["action"], np.asarray(piv, float) if piv is not None else None, e.get("delta"), e.get("angle", 0.0))
                    if np.abs(w - t1).max() < 5e-3:
                        hit = True
                        break
                stray_mv += not hit
        newk = [t for x, t in zip(kb, Tb) if int(x) not in pos_a]
        if newk and len(Ta) and not any(e["action"] in ("add", "cars", "scale_y", "copy") for e in edits_level):
            stretched += int((edges(np.array(newk)).max(1) > edges(Ta).max() + 0.5).sum())
        if stretched or nonrigid or stray_mv or same and np.abs(A_ - B_).max() > 1e-4:
            log("  item %d: moved-triangle check: stretched %d, non-rigid %d, changed but not where an edit puts it %d" % (i, stretched, nonrigid, stray_mv))
        ok &= stretched == 0 and nonrigid == 0 and stray_mv == 0
    return ok


def copy_records(level_edits, src_path):
    """for verify: [{"donors": [pak offsets], "src": [offsets]}] of the 'copy' edits, checking the donor pattern again on the written pak"""
    out = []
    for e in level_edits:
        if e["action"] == "copy":
            out.append({"donors": [int(d, 16) for c in e["copies"] for d in c["donors"]], "src": [int(o, 16) for o in e["source"]]})
    return out


def entry_records(level_edits, src_path):
    """for verify: {draw entry offset: hide_dy} of the entries the 'remove' edits hide on their own (not whole placements)"""
    p = ndpak.Pak(src_path)
    insts = find_instances(p)
    union = entry_union(level_edits, p, insts)
    out = {}
    for e in level_edits:
        rc = e.get("render", {})
        if e.get("action") != "remove" or not isinstance(rc, dict) or not rc.get("offsets"):
            continue
        want = {int(o, 16) if isinstance(o, str) else int(o) for o in rc["offsets"]}
        for h in resolve_records(p, insts, want, e.get("name"), lambda *a: None, union=union):
            if h.loc is not None:
                out[h.pak_off] = float(rc.get("hide_dy", -1000.0))
    return out


def verify_render(src_path, out_path, log=print, copies=(), vis=(), entries=None):
    a, b = open(src_path, "rb").read(), open(out_path, "rb").read()
    if len(a) != len(b):
        log("  render pak size changed")
        return False
    A, B = np.frombuffer(a, np.uint8), np.frombuffer(b, np.uint8)
    idx = np.nonzero(A != B)[0]
    log("  render pak: %d bytes differ" % len(idx))
    pa, pb = ndpak.Pak(src_path), ndpak.Pak(out_path)
    ia, ib = find_instances(pa, True), find_instances(pb, True)
    ok = len(ia) == len(ib)
    moved = [(x, y) for x, y in zip(ia, ib) if not np.array_equal(x.M, y.M)]
    for x, y in moved:
        log("  instance %s @%#x: translation %s -> %s, basis %s" % (
            ",".join(n for n, _ in x.names), x.pak_off, np.round(x.M[3, :3], 3).tolist(), np.round(y.M[3, :3], 3).tolist(),
            "same" if np.allclose(x.M[:3], y.M[:3]) else "rotated"))
    cover = np.zeros(len(a), bool)
    if vis:                                                    # 'vis_open' edits: stream slots / leaf offsets (checked by verify_vis)
        for e_ in vis:
            for o_, data_ in vis_plan(e_, pa, lambda *x: None)["writes"]:
                cover[o_:o_ + len(data_)] = True
        ok &= verify_vis(src_path, out_path, list(vis), log, check_stray=False)
    for ce in copies:                                          # 'copy' edits: the donor records (0x110 bytes) were rewritten
        for do in ce["donors"]:
            cover[do:do + REC] = True
    for x, y in moved:
        cover[x.pak_off:x.pak_off + 64] = True
    for eo, dy in sorted((entries or {}).items()):             # hidden draw entries: ONLY the translation y of the entry's own matrix, by hide_dy
        fa = np.frombuffer(a, "<f4", 16, eo).copy()
        fb = np.frombuffer(b, "<f4", 16, eo)
        want = fa.copy()
        want[13] = np.float32(fa[13] + np.float32(dy))
        if not np.array_equal(want.view(np.uint32), fb.view(np.uint32)):
            log("  draw entry %#x: matrix is not the source with translation y %+g" % (eo, dy))
            ok = False
        cover[eo:eo + 64] = True
    if entries:
        log("  %d draw entries hidden individually (matrix translation y only)" % len(entries))
    cut_total = 0
    for i, sm in enumerate(pa.submeshes):                      # world-space cuts: index buffers
        o = sm["index"]
        n = sm["icount"]
        if (A[o:o + 2 * n] != B[o:o + 2 * n]).any():
            ia_ = np.frombuffer(a, "<u2", n, o).reshape(-1, 3).astype(np.int64)
            ib_ = np.frombuffer(b, "<u2", n, o).reshape(-1, 3).astype(np.int64)
            ch = (ia_ != ib_).any(1)
            degen = (ib_[ch][:, 0] == ib_[ch][:, 1]) & (ib_[ch][:, 0] == ib_[ch][:, 2])
            if not degen.all():
                log("  submesh #%d: an index changed that is not a cut" % i)
                ok = False
            cut_total += int(ch.sum())
            cover[o:o + 2 * n] = True
            log("  submesh #%d %s: %d triangles cut" % (i, sm["name"][-60:], int(ch.sum())))
    for ce in copies:
        n = len(ce["src"])
        for k, do in enumerate(ce["donors"]):
            so = ce["src"][k % n]
            ra, rb_ = b[so + 64:so + REC], b[do + 64:do + REC]
            diff = [i for i in range(len(ra)) if ra[i] != rb_[i] and not (0xE8 - 64 <= i < 0xEC - 64)]
            if diff:
                log("  copy record %#x differs from its source %#x at +%s" % (do, so, [hex(64 + i) for i in diff[:8]]))
                ok = False
            elif k == 0:
                log("  copy records equal their sources except matrix + id (checked all %d)" % len(ce["donors"]))
    ok &= not (A != B)[~cover].any()
    log("  all %d instances found again, %d triangles cut in world-space submeshes, every differing byte lies inside a moved "
        "instance's matrix, a hidden draw entry's matrix or a cut index buffer: %s" % (len(ib), cut_total, ok))
    return ok


# ==================================================================================================== previews
def _shade_img(tris, lo, hi, S, view, color, base=None, wire=False):
    from PIL import Image, ImageDraw
    ax = {"top": (0, 2), "front": (0, 1), "side": (2, 1)}[view]
    w = int((hi[ax[0]] - lo[ax[0]]) * S) + 1
    h = int((hi[ax[1]] - lo[ax[1]]) * S) + 1
    img = base.copy() if base is not None else Image.new("RGB", (w, h), (18, 20, 24))
    dr = ImageDraw.Draw(img)
    if len(tris) == 0:
        return img
    depth_ax = {"top": 1, "front": 2, "side": 0}[view]
    order = np.argsort(tris[:, :, depth_ax].mean(1))
    n = np.cross(tris[:, 1] - tris[:, 0], tris[:, 2] - tris[:, 0])
    nl = np.maximum(np.linalg.norm(n, axis=1), 1e-12)
    face = np.abs(n[:, depth_ax]) / nl
    for i in order:
        t = tris[i]
        if view == "top":
            pts = [((x - lo[0]) * S, (z - lo[2]) * S) for x, y, z in t]
        elif view == "front":
            pts = [((x - lo[0]) * S, (hi[1] - y) * S) for x, y, z in t]
        else:
            pts = [((z - lo[2]) * S, (hi[1] - y) * S) for x, y, z in t]
        k = 0.35 + 0.65 * face[i]
        if wire:
            dr.polygon(pts, outline=color)
        else:
            dr.polygon(pts, fill=tuple(int(c * k) for c in color), outline=tuple(int(c * 0.6) for c in color))
    return img


def preview(src_render, out_render, src_phys, out_phys, box, png, pad=(4.0, 3.0, 4.0), S=40, label=""):
    """before / after panels (CPU, PIL): collision + render, top-down and front view of the edit box"""
    from PIL import Image, ImageDraw
    b = np.array(box, float)
    lo, hi = b[:3] - np.array(pad), b[3:] + np.array(pad)
    panels = []

    def coll(path):
        out = []
        for it in phys_items(path)[1]:
            T = hc.triangles(it.mesh)[1]
            if len(T):
                sel = ((T.max(1) >= lo) & (T.min(1) <= hi)).all(1)
                out.append(T[sel])
        return np.concatenate(out) if out else np.zeros((0, 3, 3))

    def rend(path):
        p = ndpak.Pak(path)
        return world_submeshes(p, list(lo) + list(hi))
    sets = []
    for tag, rp, pp in (("before", src_render, src_phys), ("after", out_render, out_phys)):
        sets.append((tag, rend(rp) if rp else np.zeros((0, 3, 3)), coll(pp) if pp else np.zeros((0, 3, 3))))
    rows = []
    for view, what in (("top", "render fill + collision wire"), ("front", "render only"), ("front", "collision only")):
        row = []
        for tag, R, C in sets:
            if what.startswith("render fill"):
                img = _shade_img(C, lo, hi, S, view, (90, 150, 255), base=_shade_img(R, lo, hi, S, view, (150, 170, 150)), wire=True)
            elif what == "render only":
                img = _shade_img(R, lo, hi, S, view, (150, 170, 150))
            else:
                img = _shade_img(C, lo, hi, S, view, (90, 150, 255))
            d = ImageDraw.Draw(img)
            d.text((6, 4), "%s %s: %s  %s" % (view, tag, what, label), fill=(255, 255, 255))
            ax = {"top": (0, 2), "front": (0, 1)}[view]
            for gx in range(int(math.ceil(lo[ax[0]])), int(hi[ax[0]]), 2):
                d.line([((gx - lo[ax[0]]) * S, 16), ((gx - lo[ax[0]]) * S, 24)], fill=(255, 255, 255))
                d.text(((gx - lo[ax[0]]) * S + 2, 24), str(gx), fill=(255, 255, 255))
            row.append(img)
        rows.append(row)
    W = sum(i.size[0] for i in rows[0]) + 30
    H = sum(max(i.size[1] for i in r) for r in rows) + 30
    canvas = Image.new("RGB", (W, H), (8, 8, 10))
    y = 10
    for r in rows:
        x = 10
        for i in r:
            canvas.paste(i, (x, y))
            x += i.size[0] + 10
        y += max(i.size[1] for i in r) + 10
    os.makedirs(os.path.dirname(png) or ".", exist_ok=True)
    canvas.save(png)
    return png, [(t, len(R), len(C)) for t, R, C in sets]


# ========================================================================================================= CLI
def _opts(argv):
    o, a = {}, []
    it = iter(argv)
    for x in it:
        if x.startswith("--"):
            k, _, v = x.partition("=")
            if not v and k in ("--dir", "--out", "--game", "--png"):
                v = next(it)
            o[k] = v or True
        else:
            a.append(x)
    return o, a


def tri_box_overlap(T, lo, hi):
    """exact triangle / AABB overlap (separating axis test) for (N,3,3) triangles -> bool (N,)"""
    lo, hi = np.asarray(lo, float), np.asarray(hi, float)
    c, h = (lo + hi) / 2, (hi - lo) / 2
    v = np.asarray(T, float) - c
    ok = np.ones(len(v), bool)
    for ax in range(3):
        ok &= ~((v[:, :, ax].min(1) > h[ax]) | (v[:, :, ax].max(1) < -h[ax]))
    e = [v[:, 1] - v[:, 0], v[:, 2] - v[:, 1], v[:, 0] - v[:, 2]]
    n = np.cross(e[0], e[1])
    ok &= ~(np.abs((n * v[:, 0]).sum(1)) > np.abs(n) @ h)
    for ei in e:
        for ax in range(3):
            a = np.zeros(3)
            a[ax] = 1
            axis = np.cross(ei, a)
            p = np.stack([(axis * v[:, k]).sum(1) for k in range(3)])
            r = np.abs(axis) @ h
            ok &= ~((p.min(0) > r) | (p.max(0) < -r))
    return ok


def clearance(edit, map_levels, work, out_dir, game=None, after=True, log=print):
    """collision triangles of EVERY level of the map (the edited level taken from out_dir when after=True) that overlap
    the edit's "clear" box (the walkable passage that must be free).  -> list of (level, item, key, tag, bbox)"""
    box = edit["clear"]
    hits = []
    for lv in map_levels:
        path = os.path.join(out_dir, lv + "-phys.pak") if after and os.path.exists(os.path.join(out_dir, lv + "-phys.pak")) else None
        if path is None:
            try:
                path = fetch(lv, os.path.join(work, "src"), game, ("-phys",))["-phys"]
            except SystemExit:
                continue                        # level has no collision pak (art / audio / script levels)
        for k, it in enumerate(phys_items(path)[1]):
            keys, T, tg = hc.triangles(it.mesh)
            cand = ((T.max(1) >= box[:3]) & (T.min(1) <= box[3:])).all(1)
            if not cand.any():
                continue
            ov = tri_box_overlap(T[cand], box[:3], box[3:])
            for kk, tt, g in zip(keys[cand][ov], T[cand][ov], tg[cand][ov]):
                hits.append((lv, k, int(kk), int(g), (np.round(tt.min(0), 2).tolist(), np.round(tt.max(0), 2).tolist())))
    return hits


def cmd_find(level, box, work, game):
    src = fetch(level, os.path.join(work, "src"), game)
    box = [float(v) for v in box]
    p = ndpak.Pak(src[""])
    insts = find_instances(p)
    hit = [it for it in insts if (it.whi >= box[:3]).all() and (it.wlo <= box[3:]).all()]
    print("%s: %d render instances touching the box" % (level, len(hit)))
    for it in hit:
        inside = (it.wlo >= box[:3]).all() and (it.whi <= box[3:]).all()
        print("  %s @%#x world %s .. %s scale~%.3f %s" % ("INSIDE" if inside else "touch ", it.pak_off, np.round(it.wlo, 2).tolist(),
                                                       np.round(it.whi, 2).tolist(), np.linalg.norm(it.M[0, :3]),
                                                       ", ".join(n for n, _ in it.names) or "(no submesh match)"))
    for mode in ("inside", "centroid"):
        try:
            wc = world_cut(p, box, mode, insts)
        except SystemExit as e:
            print("  render triangles (%s): %s" % (mode, e))
            continue
        print("  render triangles of single-use submeshes that a 'render': {'world': true%s} edit would cut: %d in %d submeshes %s" % (
            ", 'mode': 'centroid'" if mode == "centroid" else "", sum(len(v) for v in wc.values()), len(wc),
            [(i, p.submeshes[i]["name"].split("|")[-1][-40:]) for i in list(wc)[:4]]))
    ps, items = phys_items(src["-phys"])
    for k, it in enumerate(items):
        keys, T, tg = hc.triangles(it.mesh)
        sel = ((T.max(1) >= box[:3]) & (T.min(1) <= box[3:])).all(1)
        if not sel.any():
            continue
        ins = ((T.min(1) >= box[:3]) & (T.max(1) <= box[3:])).all(1)
        tags = {}
        for t_ in tg[ins]:
            tags[int(t_)] = tags.get(int(t_), 0) + 1
        print("  collision item %d (kind %#x, %d sections): %d triangles touch the box, %d inside; tags inside %s; sections %s" % (
            k, it.kind, len(it.mesh.sections), int(sel.sum()), int(ins.sum()), tags, sorted({int(x) >> 8 for x in keys[ins]})[:12]))


def main(argv):
    o, a = _opts(argv[1:])
    if not a:
        print(__doc__)
        return 1
    cmd, args = a[0], a[1:]
    work = o.get("--dir") or CACHE
    game = o.get("--game")
    out = o.get("--out") or os.path.join(work, "out")
    if cmd == "extract":
        for lv in args:
            print(fetch(lv, o.get("--out") or os.path.join(work, "src"), game))
        return 0
    if cmd == "find":
        cmd_find(args[0], args[1:7], work, game)
        return 0
    if cmd == "group":                                  # group <level> <record offset>: one baked prop's records
        src = fetch(args[0], os.path.join(work, "src"), game, ("",))[""]
        insts = find_instances(ndpak.Pak(src))
        want = int(args[1], 16)
        a = next((it for it in insts if it.pak_off == want), None)
        if a is None:
            print("no render record at %#x" % want)
            return 1
        g = prop_group(insts, a)
        dr = prop_dressing(insts, g)
        for it in g:
            print("  part     @%#x %s" % (it.pak_off, ", ".join(n for n, _ in it.names)))
        for it in dr:
            print("  attached @%#x %s" % (it.pak_off, ", ".join(n for n, _ in it.names)))
        lo = np.min([i.wlo for i in g + dr], 0)
        hi = np.max([i.whi for i in g + dr], 0)
        offs = ["0x%x" % i.pak_off for i in g]
        print(json.dumps({"edits": [{"name": "move " + _family(a.names), "level": args[0], "box": np.r_[lo - 3, hi + 3].round(2).tolist(),
                                     "action": "transform", "angle": 0.0, "pivot": a.M[3, :3].round(3).tolist(), "delta": [0.0, 0.0, 0.0],
                                     "render": {"offsets": offs + ["0x%x" % i.pak_off for i in dr]},
                                     "collision": {"obb_of": offs, "margin": 0.1}},
                                    {"name": "shadow proxy", "level": args[0], "box": np.r_[lo - 0.05, hi + 0.05].round(3).tolist(),
                                     "action": "remove", "render": {"world": True, "cut_name": "tfrag-merge-shadows"}, "collision": False}]}, indent=1))
        return 0
    if cmd == "vis":                                   # vis <level> x0 y0 z0 x1 y1 z1 [ox0 oy0 oz0 ox1 oy1 oz1]: kd cells + bitsets in the box
        src = fetch(args[0], os.path.join(work, "src"), game, ("",))[""]
        e = {"level": args[0], "box": [float(x) for x in args[1:7]],
             "outside": [float(x) for x in (args[7:13] if len(args) >= 13 else args[1:7])]}
        pl = vis_plan(e, ndpak.Pak(src))
        for t in pl["targets"]:
            print("  stream %#x: %s, bits %d -> %d, bytes slot %d new %d" % (t["off"], t["mode"], t["bits"][0], t["bits"][1], *t["bytes"]))
        return 0
    if cmd in ("apply", "apply-spec"):
        edits = edits_for(args[0], o) if cmd == "apply" else json.load(open(args[0]))["edits"]
        w = build_edits(edits, work, out, game)
        print("written:", *w, sep="\n  ")
        return 0
    if cmd == "verify":
        edits = [e for e in edits_for(args[0], o) if e.get("action") not in ("morph", "detach", "colledit")]       # those: level_morph.py verify
        ok = True
        for lv in levels_of(edits):
            print("level", lv)
            src = os.path.join(work, "src")
            if os.path.exists(os.path.join(out, lv + "-phys.pak")):
                ok &= verify_phys(os.path.join(src, lv + "-phys.pak"), os.path.join(out, lv + "-phys.pak"), [e for e in edits if e["level"] == lv])
            if os.path.exists(os.path.join(out, lv + ".pak")):
                ok &= verify_render(os.path.join(src, lv + ".pak"), os.path.join(out, lv + ".pak"), copies=copy_records([e for e in edits if e["level"] == lv], os.path.join(src, lv + ".pak")),
                                     entries=entry_records([e for e in edits if e["level"] == lv], os.path.join(src, lv + ".pak")),
                                     vis=[e for e in edits if e["level"] == lv and e["action"] == "vis_open"])
        for e in edits:
            if "clear" not in e:
                continue
            lvs = map_levels(args[0])
            b = clearance(e, lvs, work, out, game, after=False)
            a = clearance(e, lvs, work, out, game, after=True)
            print("passage %s (%s): collision triangles of the map's levels in the clear box: before %d, after %d" % (
                e.get("name"), e["clear"], len(b), len(a)))
            for h in a[:8]:
                print("   still there:", h)
            ok &= not a and (e["action"] != "remove" or len(b) > 0)
        print("VERIFY", "OK" if ok else "FAILED")
        return 0 if ok else 1
    if cmd == "preview":
        edits = [e for e in edits_for(args[0], o) if e.get("action") not in ("morph", "detach", "colledit")]
        e = edits[int(args[1]) if len(args) > 1 else 0]
        lv = e["level"]
        src = os.path.join(work, "src")
        png = o.get("--png") or os.path.join(MAIN, "re", "maps", "preview", "level-edit-%s.png" % args[0])
        r = preview(os.path.join(src, lv + ".pak"), os.path.join(out, lv + ".pak") if os.path.exists(os.path.join(out, lv + ".pak")) else None,
                    os.path.join(src, lv + "-phys.pak"), os.path.join(out, lv + "-phys.pak") if os.path.exists(os.path.join(out, lv + "-phys.pak")) else None,
                    e["box"], png, label=e.get("name", ""))
        print(r)
        return 0
    print(__doc__)
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
