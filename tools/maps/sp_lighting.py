"""SP lighting for ported SP maps make a map built from a story chapter's levels light and fog the way the chapter does.

Why: in SP the chapter's TASK STATE decides which render-settings regions are on.  A render-settings region (REGION_TREE of the
-ingame pak, tag "render-settings" = symbol) may carry story gating tags (task-node + task-subnode list, or start-task /
start-task-subnode / end-task / end-task-subnode); the engine only applies it while the patrol task is in that range.  MP never has
those tasks, so every gated region is off (interior tonemap range of the post office, fog volume resolution, cloud shadows ...).
The chapter's state scripts add nothing global (re/maps/jackson-market.md "SP lighting"): the lighting is the regions + a few
per-igc overrides.

Spec (tools/maps/sp_maps.json, key "sp_lighting" of a map):
  "task":      {"node": "patrol", "subnode": "pat-supermarket-entrance-done"}   the SP task state to reproduce
  "order":     optional [subnode, ...] chapter order, needed only to evaluate start-task .. end-task ranges of other subnodes
  "include":   region names to ungate although the state does not select them
  "exclude":   region names to leave gated although the state selects them
  "margin":    metres around "bounds" a region may lie (default 80)
  "match_level": a level of the map that is loaded only in this map (the ext detects the map by it)
  "interior":  boxes where the ext forces the interior exposure: {"region": name[, "y": [y0, y1]]} (the region's world box) or
               {"box": [x0, x1, y0, y1, z0, z1]}
  "ev_in", "ev_out": forced exposure value inside / outside the interior boxes (ext: imm_winter_exposure_tick)
  "drop_rs":   [{"region": name, "why": ...}]  plain regions whose render-settings tag the build cuts (the engine then has no symbol for them): SP
               optimisation / transition regions that change shadow cascades, ambient grid, bloom ... outdoors
  "layers":    [{"symbol": "*sym*", "prio": 50, "strength": 1.0}]  override-render-settings layers the ext applies every frame

Build (sp_maps_build.stage_edits): the gated regions the state selects get their gating tags cut out of the REGION_TREE tag
dictionary of the staged <level>-ingame.pak (in place: entries shift up, the count drops, page layout and fixups unchanged), so the
engine sees them as ordinary always-on regions.  Regions the state does not select stay gated (= off, as in SP at that point).

  python sp_lighting.py report <map key>    # gated render-settings regions near the map, which the state turns on
  python sp_lighting.py build  <map key>    # write the patched paks to <cache>/ingame/out/<key>/ and verify them
  python sp_lighting.py header [<map key>...]   # tools/ext/sp_lighting.h (maps with an "sp_lighting" spec)
  python sp_lighting.py selftest            # round trips on the cached stock paks
"""
import json
import math
import os
import struct
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(ROOT, "tools", "part1"))
import p1_rsenv as rs  # noqa: E402
import t2pak  # noqa: E402

SPEC = os.path.join(HERE, "sp_maps.json")
HEADER = os.path.join(ROOT, "tools", "ext", "sp_lighting.h")
CACHE = os.environ.get("T2R_INGAME_CACHE", os.path.join(ROOT, "re", "maps", "level-edit-cache", "ingame", "src"))
OUT = os.path.join(os.path.dirname(CACHE), "out")

K_NODE, K_SUB = rs.fnv("task-node"), rs.fnv("task-subnode")
K_START, K_START_SUB = rs.fnv("start-task"), rs.fnv("start-task-subnode")
K_END, K_END_SUB = rs.fnv("end-task"), rs.fnv("end-task-subnode")
GATE_KEYS = {K_NODE, K_SUB, K_START, K_START_SUB, K_END, K_END_SUB}
NAMES = {K_NODE: "task-node", K_SUB: "task-subnode", K_START: "start-task", K_START_SUB: "start-task-subnode",
         K_END: "end-task", K_END_SUB: "end-task-subnode"}
SID_NAMES = {}      # sid -> task name, filled from the spec / task lists (tags hold sids)


def sid_name(h):
    if h is None:
        return "-"
    if h not in SID_NAMES:
        try:
            sys.path.insert(0, os.path.join(ROOT, "tools", "re"))
            import sidname
            SID_NAMES[h] = sidname.look(h) or "%#x" % h
        except Exception:
            SID_NAMES[h] = "%#x" % h
    return SID_NAMES[h]


def spec_of(key):
    for m in json.load(open(SPEC, encoding="utf-8"))["maps"]:
        if m["key"] == key:
            return m
    raise SystemExit("no map %s in sp_maps.json" % key)


def load_names(extra=()):
    """sid -> name for the task names the gating tags hold: the patrol task list of the DC tasks module is not needed, the names
    are hashed from the candidates (spec task / order / include lists + every pat-* name the gate tags are compared with)"""
    for n in extra:
        SID_NAMES[rs.fnv(n)] = n


# ------------------------------------------------------------------------------------------------ pak access
def src_pak(level):
    p = os.path.join(CACHE, level + "-ingame.pak")
    return p if os.path.exists(p) else None


def record_slots(pk):
    """[(record address (page, off), name, dict address, entries address, count, [(key, raw ptr value, dst page)])] of the pak's REGION_TREEs"""
    out = []
    for typ, pg, off in pk.items():
        if typ != "REGION_TREE":
            continue
        k = 8
        while pk.ptr(pg, off + k) is not None:
            rpg, roff = pk.ptr(pg, off + k)
            k += 8
            npg, noff = pk.ptr(rpg, roff)
            name = bytes(pk.pages[npg][noff:pk.pages[npg].index(b"\0", noff)]).decode("latin1")
            dpg, doff = pk.ptr(rpg, roff + 0x50)
            epg, eoff = pk.ptr(dpg, doff)
            cnt = pk.q(dpg, doff + 8)
            ents = []
            for i in range(cnt):
                key = pk.q(epg, eoff + 16 * i)
                bp = pk.ptr(epg, eoff + 16 * i + 8)
                ents.append((key, bp))
            out.append({"name": name, "dict": (dpg, doff), "ents": (epg, eoff), "tags": ents})
    return out


def strip_tags(data, names, drop_keys):
    """pak bytes -> (pak bytes, [names changed]): the tags `drop_keys` cut out of the tag dictionary of every region in `names`.
    A pure byte patch of the original file (no re-serialisation): the kept entries shift up inside their array, the dictionary
    count drops; the freed tail slots keep their old (valid) pointers; the fixup table is untouched (every slot of a tag array
    points into the same page - asserted)."""
    pk = t2pak.TPak(data)
    out = bytearray(data)
    done = []
    for r in record_slots(pk):
        if r["name"] not in names:
            continue
        keep = [e for e in r["tags"] if e[0] not in drop_keys]
        if len(keep) == len(r["tags"]):
            continue
        epg, eoff = r["ents"]
        base = pk.starts[epg] + eoff
        for i, (key, bp) in enumerate(keep):
            assert bp[0] == pk.fix[(epg, eoff + 16 * i + 8)], "%s: tag box pages differ" % r["name"]
            struct.pack_into("<QQ", out, base + 16 * i, key, bp[1])
        dpg, doff = r["dict"]
        struct.pack_into("<Q", out, pk.starts[dpg] + doff + 8, len(keep))
        done.append(r["name"])
    return bytes(out), done


def strip_gating(data, names):
    """the gating tags of the regions in `names` cut out (they become ordinary always-on regions)"""
    return strip_tags(data, names, GATE_KEYS)


def _old(name):
    """Opt-in to the pre-exact behaviour per addition (env T2R_SPL_<NAME>=old): GATES = spec "exclude" list applied, DROP = "drop_rs" cuts applied"""
    return os.environ.get("T2R_SPL_" + name, "") == "old"


def dropped(m):
    """{region name: why} of the spec's "drop_rs": plain (never gated) render-settings regions whose render-settings tag the build cuts, so
    the engine has no symbol for them any more (SP optimisation / transition regions that change shadow cascades, ambient grid, bloom,
    ssao ... outdoors and would show as the sun / scenery lighting changing with the player's position)"""
    if not _old("DROP"):                                    # SP-exact: the optimisation regions stay native (SP has them on); T2R_SPL_DROP=old restores the cuts
        return {}
    return {d["region"]: d.get("why", "") for d in (m.get("sp_lighting") or {}).get("drop_rs", [])}


# ------------------------------------------------------------------------------------------------ region table
def _sids(r, key):
    """task names of a tag: stored as sids or as strings (both occur)"""
    out = []
    for k, kind, v in r["tags"]:
        if k == key and kind in ("sid", "str"):
            if kind == "str":
                SID_NAMES[rs.fnv(v)] = v
                v = rs.fnv(v)
            out.append(v)
    return out


def gate_of(r):
    """region dict (p1_rsenv.parse_tree) -> None | {"subs": [sid], "start": sid, "end": sid}"""
    subs, st, en = _sids(r, K_SUB), _sids(r, K_START_SUB), _sids(r, K_END_SUB)
    node = _sids(r, K_NODE) + _sids(r, K_START)
    if not (subs or st or en):
        return None
    return {"subs": subs, "start": st[0] if st else None, "end": en[0] if en else None, "node": node[0] if node else None}


def box_of(r):
    """(x0, x1, y0, y1, z0, z1); regions with flags / state scripts: outline box, any height"""
    if r["unsupported"]:
        cb = rs.corner_box(r)
        return (cb[0], cb[2], -1000.0, 1000.0, cb[1], cb[3]) if cb else None
    lo, hi = rs.world_aabb(r)
    v = [float(x) for x in list(lo) + list(hi)]
    if not all(map(math.isfinite, v)):
        return None
    if r["shape"] != 1:
        return (v[0], v[3], v[1], v[4], v[2], v[5])
    cb = rs.corner_box(r)
    return (v[0], v[3], v[1], v[4], v[2], v[5])


def region_volumes(data, names):
    """{region name: [volume = [(nx, ny, nz, d)]]} read from the REGION_TREE bodies of a TLOU2 -ingame pak, for ANY region shape code (1, 3, 5, 6, 7, 9 ... all
    carry the same convex-volume body): a point is inside a volume when n.p <= d for every face (n = outward face normal, d = n.face centre); regions are the
    union of their volumes.  SP trace check: with these exact volumes the replay matches SP's logged values at 100% of the settled samples."""
    pk = t2pak.TPak(data)
    starts, pos = [], 0
    for pg in pk.pages:
        starts.append(pos)
        pos += len(pg)
    blob = b"".join(bytes(pg) for pg in pk.pages)

    def ptr(a):
        for i, st in enumerate(starts):
            if st <= a < st + len(pk.pages[i]):
                dp = pk.fix.get((i, a - st))
                return None if dp is None else starts[dp] + pk.q(i, a - st)
        return None
    out = {}
    for typ, pg, off in pk.items():
        if typ != "REGION_TREE":
            continue
        base = starts[pg] + off
        k = 8
        while ptr(base + k) is not None:
            R = ptr(base + k)
            k += 8
            nm = bytes(blob[ptr(R):blob.index(b"\0", ptr(R))]).decode("latin1")
            if nm not in names:
                continue
            vols, c = [], ptr(R + 0x30)
            while True:
                hdr = struct.unpack_from("<Q", blob, c + 16)[0]
                assert hdr & 0xFFFF == 1, nm
                faces = []
                for j in range((hdr >> 16) & 0xFFFF):
                    f = blob[c + 32 + 112 * j:c + 32 + 112 * (j + 1)]
                    rot = [struct.unpack_from("<f", f, 16 * a + 4 * b)[0] for a in range(3) for b in range(3)]
                    tx, ty, tz = struct.unpack_from("<3f", f, 48)
                    quad = struct.unpack_from("<8f", f, 80)
                    n = (rot[2], rot[5], rot[8])
                    ctr = [0.0, 0.0, 0.0]
                    for i in range(4):
                        a, b, cc = quad[2 * i] - tx, quad[2 * i + 1] - ty, -tz
                        w = (a * rot[0] + b * rot[1] + cc * rot[2], a * rot[3] + b * rot[4] + cc * rot[5], a * rot[6] + b * rot[7] + cc * rot[8])
                        ctr = [ctr[t] + w[t] / 4 for t in range(3)]
                    faces.append((n[0], n[1], n[2], n[0] * ctr[0] + n[1] * ctr[1] + n[2] * ctr[2]))
                vols.append(faces)
                c = ptr(c)
                if c is None:
                    break
            out[nm] = vols
    return out


def clip_regions(data, clips):
    """pak bytes, {region name: [(nx, ny, nz, d)]} -> (pak bytes, {name: [(volume, face, old d, new d)]}): the NATIVE counterpart of an interior "clip":
    every volume face of the region whose outward normal matches a clip face (dot > 0.999) and lies outside it (old d > clip d + 1 cm) is moved onto the clip
    plane (byte patch of the face's local z translation: world point = R (a, b, -tz) + 0, n = R's third column, so n.p = -tz; quads keep their in-plane corners,
    the engine's inside test is the half-space set). A clip face no volume face can carry (no parallel face) raises: a face cannot be added in place."""
    pk = t2pak.TPak(data)
    lstarts, pos = [], 0
    for pg in pk.pages:
        lstarts.append(pos)
        pos += len(pg)
    blob = b"".join(bytes(pg) for pg in pk.pages)

    def ptr(a):
        for i, st in enumerate(lstarts):
            if st <= a < st + len(pk.pages[i]):
                dp = pk.fix.get((i, a - st))
                return None if dp is None else lstarts[dp] + pk.q(i, a - st)
        return None

    def fileoff(a):
        for i, st in enumerate(lstarts):
            if st <= a < st + len(pk.pages[i]):
                return pk.starts[i] + (a - st)
        raise ValueError(a)
    out, done = bytearray(data), {}
    for typ, pg, off in pk.items():
        if typ != "REGION_TREE":
            continue
        base = lstarts[pg] + off
        k = 8
        while ptr(base + k) is not None:
            R = ptr(base + k)
            k += 8
            nm = bytes(blob[ptr(R):blob.index(b"\0", ptr(R))]).decode("latin1")
            if nm not in clips or nm in done:
                continue
            ch, c, vi = [], ptr(R + 0x30), 0
            used = set()
            while True:
                hdr = struct.unpack_from("<Q", blob, c + 16)[0]
                for j in range((hdr >> 16) & 0xFFFF):
                    fo = c + 32 + 112 * j
                    rot = [struct.unpack_from("<f", blob, fo + 16 * a + 4 * b)[0] for a in range(3) for b in range(3)]
                    tx, ty, tz = struct.unpack_from("<3f", blob, fo + 48)
                    quad = struct.unpack_from("<8f", blob, fo + 80)
                    n = (rot[2], rot[5], rot[8])
                    assert abs(n[0] ** 2 + n[1] ** 2 + n[2] ** 2 - 1.0) < 1e-3, nm
                    ctr = [0.0, 0.0, 0.0]
                    for i in range(4):
                        a, b, cc = quad[2 * i] - tx, quad[2 * i + 1] - ty, -tz
                        w = (a * rot[0] + b * rot[1] + cc * rot[2], a * rot[3] + b * rot[4] + cc * rot[5], a * rot[6] + b * rot[7] + cc * rot[8])
                        ctr = [ctr[t] + w[t] / 4 for t in range(3)]
                    old_d = n[0] * ctr[0] + n[1] * ctr[1] + n[2] * ctr[2]
                    for ci, cf in enumerate(clips[nm]):
                        if n[0] * cf[0] + n[1] * cf[1] + n[2] * cf[2] > 0.999:
                            used.add(ci)
                            t = cf[3] - (cf[0] * ctr[0] + cf[1] * ctr[1] + cf[2] * ctr[2])     # face centre slid onto the clip plane (a face a hair off the
                            q = [ctr[i] + t * cf[i] for i in range(3)]                             # clip normal keeps its own tilt, passing through that point)
                            new_d = n[0] * q[0] + n[1] * q[1] + n[2] * q[2]
                            if new_d < old_d - 0.01:
                                struct.pack_into("<f", out, fileoff(fo + 56), tz - (new_d - old_d))
                                ch.append((vi, j, round(old_d, 3), round(new_d, 3)))
                c = ptr(c)
                vi += 1
                if c is None:
                    break
            missing = set(range(len(clips[nm]))) - used
            assert not missing, "clip_regions %s: no volume face parallel to clip face(s) %s" % (nm, sorted(missing))
            done[nm] = ch
    return bytes(out), done


def native_clips(m):
    """{region name: [clip faces]} of the spec's interior entries with "clip" (applied to the paks by build(), and to the ext's interior test by header())"""
    return {it["region"]: [tuple(f) for f in it["clip"]] for it in m["sp_lighting"].get("interior", []) if it.get("clip")}


def interior_volumes(m):
    """the interior regions' exact volumes (spec "interior" entries with a "region"): [[(nx, ny, nz, d) x faces] x volumes]; "y" limits are ignored (the volume has its own height)"""
    names = {it["region"] for it in m["sp_lighting"].get("interior", []) if "region" in it}
    vols = {}
    for lv in m["levels"]:
        p = src_pak(lv)
        if p:
            vols.update(region_volumes(open(p, "rb").read(), names - set(vols)))
    missing = names - set(vols)
    assert not missing, "interior regions not found: %s" % sorted(missing)
    # "clip": extra faces [nx, ny, nz, d] (inside = n.p <= d) added to every volume of that region: carves out open-air ground SP's volume holds
    return [list(v) + [tuple(f) for f in it.get("clip", [])] for it in m["sp_lighting"].get("interior", []) if "region" in it for v in vols[it["region"]]]


def regions(m, levels=None):
    """[(level, region dict)] of the render-settings regions of the map's levels (cached stock -ingame paks)"""
    out = []
    for lv in levels or m["levels"]:
        p = src_pak(lv)
        if not p:
            continue
        for regs, _g in rs.read_pak_regions(open(p, "rb").read()):
            out += [(lv, r) for r in regs if rs.region_rs(r)]
    return out


def active(g, state, order):
    """is a gated region on in task state `state` (subnode name)?"""
    sid = rs.fnv(state)
    if g["subs"] and sid in g["subs"]:
        return True
    if g["start"] is not None and g["end"] is not None:
        if g["start"] == sid or g["end"] == sid:
            return True
        if g["start"] != g["end"] and order:
            idx = {rs.fnv(n): i for i, n in enumerate(order)}
            if sid in idx and g["start"] in idx and g["end"] in idx:
                return idx[g["start"]] <= idx[sid] <= idx[g["end"]]
    return False


def plan(m, quiet=True):
    """-> {level: [region names to ungate]}, rows [(level, region, prio, symbol, state on?, gate text, box)]"""
    sp = m["sp_lighting"]
    st = sp["task"]["subnode"]
    order = sp.get("order", [])
    b = m["bounds"]
    mg = sp.get("margin", 80)
    bx0, bx1, bz0, bz1 = b[0] - mg, b[1] + mg, b[2] - mg, b[3] + mg
    load_names([st] + list(order))
    sel, rows = {}, []
    for lv, r in regions(m):
        g = gate_of(r)
        if not g:
            continue
        bb = box_of(r)
        if not bb or bb[1] < bx0 or bb[0] > bx1 or bb[5] < bz0 or bb[4] > bz1:
            continue
        on = active(g, st, order)
        if r["name"] in sp.get("include", []):
            on = True
        if r["name"] in sp.get("exclude", []) and _old("GATES"):     # SP-exact: exact region volumes need no exclusions; T2R_SPL_GATES=old restores them
            on = False
        txt = "sub=" + ",".join(sid_name(x) for x in g["subs"]) if g["subs"] else "start=%s end=%s" % (sid_name(g["start"]), sid_name(g["end"]))
        rows.append((lv, r["name"], r["prio"], rs.region_rs(r), on, txt, bb))
        if on:
            sel.setdefault(lv, []).append(r["name"])
    return sel, rows


# ------------------------------------------------------------------------------------------------ build
def build(m, base_for=None, out_dir=None, log=print):
    """patched -ingame paks of the map's selected regions -> [path].  base_for(level) -> bytes of the pak to patch (the staged,
    collectible-stripped copy when the build has one), default: the cached stock pak."""
    sp = m.get("sp_lighting")
    if not sp:
        return []
    sel, _rows = plan(m)
    drop = dropped(m)
    dlv = {}                                                    # level -> region names whose render-settings tag is cut
    if drop:
        for lv, r in regions(m):
            if r["name"] in drop:
                dlv.setdefault(lv, set()).add(r["name"])
        miss = set(drop) - {n for v in dlv.values() for n in v}
        assert not miss, "sp_lighting %s: drop_rs regions not found: %s" % (m["key"], sorted(miss))
    clips = native_clips(m)                                     # interior "clip" faces, applied to SP's own region volumes too (the engine's region gather)
    clv = {}
    if clips:
        for lv, r in regions(m):
            if r["name"] in clips:
                clv.setdefault(lv, {})[r["name"]] = clips[r["name"]]
        miss = set(clips) - {n for v in clv.values() for n in v}
        assert not miss, "sp_lighting %s: clip regions not found: %s" % (m["key"], sorted(miss))
    out_dir = out_dir or os.path.join(OUT, m["key"] + "-lighting")
    os.makedirs(out_dir, exist_ok=True)
    files = []
    for lv in sorted(set(sel) | set(dlv) | set(clv)):
        names = sel.get(lv, [])
        data = base_for(lv) if base_for else None
        if data is None:
            data = open(src_pak(lv), "rb").read()
        new, done = strip_gating(data, set(names))
        bad = verify(data, new, set(done))
        assert not bad, "sp_lighting %s %s: %s" % (m["key"], lv, bad)
        assert set(done) == set(names), "sp_lighting %s %s: not changed: %s" % (m["key"], lv, sorted(set(names) - set(done)))
        if lv in dlv:
            new2, gone = strip_tags(new, dlv[lv], {rs.TAG_RS})
            bad = verify(new, new2, set(gone), {rs.TAG_RS})
            assert not bad, "sp_lighting %s %s drop_rs: %s" % (m["key"], lv, bad)
            assert set(gone) == dlv[lv], "sp_lighting %s %s: render-settings tag not cut: %s" % (m["key"], lv, sorted(dlv[lv] - set(gone)))
            log("sp lighting %s: %s - render-settings cut from %d region(s): %s" % (m["key"], lv, len(gone), ", ".join(sorted(gone))))
            new = new2
        if lv in clv:
            new3, cdone = clip_regions(new, clv[lv])
            assert set(cdone) == set(clv[lv]), "sp_lighting %s %s: clip regions not changed: %s" % (m["key"], lv, sorted(set(clv[lv]) - set(cdone)))
            for nm, ch in sorted(cdone.items()):
                log("sp lighting %s: %s - region %s clipped: %s" % (m["key"], lv, nm, "; ".join("volume %d face %d d %.3f -> %.3f" % c for c in ch) or "already inside the clip"))
            new = new3
        dst = os.path.join(out_dir, lv + "-ingame.pak")
        if not os.path.exists(dst) or open(dst, "rb").read() != new:
            open(dst, "wb").write(new)
        log("sp lighting %s: %s - %d gated render-settings region(s) ungated (task state %s): %s" %
            (m["key"], lv, len(done), sp["task"]["subnode"], ", ".join(sorted(done))))
        files.append(dst)
    return files


def verify(old, new, changed, keys=GATE_KEYS):
    """problems: the patched pak re-reads, the changed regions lost exactly their gating tags, everything else is identical"""
    bad = []
    a = [r for regs, _ in rs.read_pak_regions(old) for r in regs]
    b = [r for regs, _ in rs.read_pak_regions(new) for r in regs]
    if [r["name"] for r in a] != [r["name"] for r in b]:
        return ["region list differs"]
    for x, y in zip(a, b):
        if x["name"] in changed:
            want = [t for t in x["tags"] if t[0] not in keys]
            if want != y["tags"]:
                bad.append("%s: tags %s != %s" % (x["name"], y["tags"], want))
            if any(t[0] in keys for t in y["tags"]):
                bad.append("%s: cut tag left" % x["name"])
        elif x["tags"] != y["tags"]:
            bad.append("%s: tags changed but not selected" % x["name"])
        for k in ("shape", "sflags", "prio", "vols", "point", "corners", "unsupported"):
            if x[k] != y[k]:
                bad.append("%s: %s changed" % (x["name"], k))
    # byte level: same length, only tag-array slots / counts of the changed regions differ
    if len(old) != len(new):
        bad.append("pak length changed")
    pk = t2pak.TPak(old)
    ok = []
    for r in record_slots(pk):
        if r["name"] in changed:
            epg, eoff = r["ents"]
            dpg, doff = r["dict"]
            ok += [(pk.starts[epg] + eoff, pk.starts[epg] + eoff + 16 * len(r["tags"])), (pk.starts[dpg] + doff + 8, pk.starts[dpg] + doff + 16)]
    stray = [i for i in range(len(old)) if old[i] != new[i] and not any(x <= i < y for x, y in ok)]
    if stray:
        bad.append("%d byte(s) changed outside the tag arrays (first %#x)" % (len(stray), stray[0]))
    return bad


# ------------------------------------------------------------------------------------------------ ext header
def interior_boxes(m):
    sp = m["sp_lighting"]
    byname = None
    out = []
    for it in sp.get("interior", []):
        if "box" in it:
            out.append(tuple(float(x) for x in it["box"]))
            continue
        if byname is None:
            byname = {r["name"]: r for _lv, r in regions(m)}
        r = byname[it["region"]]
        bb = box_of(r)
        y0, y1 = it.get("y", [bb[2], bb[3]])
        out.append((bb[0], bb[1], float(y0), float(y1), bb[4], bb[5]))
    return out


GB = os.environ.get("T2R_GAMEBIN", "./re/gamebin")
TONEMAP_KEYS = {rs.fnv("tonemap:" + n) for n in (
    "tonemap-light-range-min", "tonemap-light-range-max", "tonemap-set-point", "tonemap-adaption-time", "tonemap-exposure-method",
    "final-exposure-bias", "tonemap-histogram-sample-position", "tonemap-histogram-edge-size", "fade-to-black-multiplier")}


def _symbol_table():
    mods = {}
    d = os.path.join(GB, "dc1", "render-settings")
    for fn in os.listdir(d):
        if fn.endswith(".bin"):
            try:
                mods[fn] = rs.DcRs(open(os.path.join(d, fn), "rb").read())
            except Exception:
                pass
    return mods


def tonemap_regions(m):
    """the map's render-settings regions that set a tonemap / exposure value and are always on in MP (never gated, or ungated by the
    plan) -> [(name, symbol, prio, blend-in s, blend-out s, holds-the-whole-map, box (x0 x1 y0 y1 z0 z1))], highest priority first.  The ext replays them
    (immersion.c imm_spl_regions_tick) so the engine's auto exposure sees SP's per-region values with SP's priorities and blend times."""
    sp = m["sp_lighting"]
    if sp.get("exposure", "regions") != "regions":
        return []
    mods = _symbol_table()
    on = {n for names in plan(m)[0].values() for n in names}
    rb = sp.get("replay_boxes", {})
    b = m["bounds"]
    mg = sp.get("margin", 80)
    out = []
    drop = dropped(m)
    for lv, r in regions(m):
        if (r["name"] in drop and r["name"] not in rb) or (gate_of(r) and r["name"] not in on and r["name"] not in rb):
            continue
        sym = rs.region_rs(r)
        h = rs.fnv(sym)
        if r["name"] not in sp.get("replay_also", []) and not any(h in md.syms and any(k in TONEMAP_KEYS for k, _v, _ in md.syms[h]) for md in mods.values()):
            continue
        bb = tuple(rb[r["name"]]) if r["name"] in rb else box_of(r)      # replay_boxes: the real interior instead of the region's coarse outline
        if not bb or bb[1] < b[0] - mg or bb[0] > b[1] + mg or bb[5] < b[2] - mg or bb[4] > b[3] + mg:
            continue
        def tagf(name, default):
            v = [struct.unpack("<f", struct.pack("<I", x))[0] for k, kind, x in r["tags"] if kind == "float" and k == rs.fnv(name)]
            return v[0] if v else default
        bl = tagf("render-settings-blend-time", 1.0)
        # a region that holds the whole map (+ margin) is the area's base look (SP: *pat-rs-pat-cloudy*): applied at full strength from the
        # first frame, not blended in over its 2 s (the blend would swing the sun / sky from the level default to the real look at match start)
        always = int(r["name"] not in rb and bb[0] <= b[0] - mg and bb[1] >= b[1] + mg and bb[4] <= b[2] - mg and bb[5] >= b[3] + mg and bb[2] <= 0 <= bb[3] + 400)
        out.append((r["name"], sym, r["prio"], bl, tagf("render-settings-blend-out-time", bl), always, bb))
    return sorted(out, key=lambda x: -x[2])


# ---------------------------------------------------------------------------------------------------- door sun
# Deliberate deviation from SP: we opened doors / garage doors that SP keeps shut, so from INSIDE the building the yard seen through the openings must
# look as from outside.  SP's interior zones switch sun / fog / cloud shadows camera-globally; in the volumes that see out the ext (flag t2r-spl-door-sun.txt = SP's
# original) rewrites those keys of the interior zone symbols to the OUTDOOR value (*pat-rs-pat-cloudy* over *pat-rs-pat*), keeps the sun shadow cascades at the outdoor setup
# (interior zones and the alley / suburb optimisation regions overlapping them shorten them: 10 / 20 and 12 m, so a sun that stays on would leak into rooms beyond the
# short cascades) and caps the eye-adaptation boost.  Interior surfaces keep SP's interior look (hood light, ambient, bounce, flash light keys are untouched).
DOOR_OUT = ("lighting:sun-light:", "sky:", "skydome:", "fog:", "new-volumetrics:sun-light:", "new-volumetrics:fog-start-distance", "rain:")
DOOR_CASC = ("shadow:cascade", "shadow:sun-shadow-")
DOOR_EV_MIN_CAP = 0.5      # tonemap-light-range-min cap, see door_sun_overrides
# During the random blizzard (weather.c WX_LAYERS) the outdoors is NOT *pat-rs-pat-cloudy*: the storm layers set the sun to 0, fog sun brightness
# 13, one 15 m shadow cascade ... but the door rooms kept the clear-weather outdoor values, and the region symbols win over the storm's override layer for the sun
# (test log: sun-light rgbi-i 2.8 inside the door rooms, 0 in the yard, storm at full strength) - the yard / courtyard seen from inside was sunlit, outside overcast.
# Each door entry therefore also carries the storm's value of its key (the layers below in priority order, later wins), which the ext blends in by the storm
# strength; door-room symbols below the storm's priority that set a storm key of the DOOR_OUT / DOOR_CASC families to another value get an entry too (clear weather =
# their own value, no change).  Keep in sync with weather.c WX_LAYERS (the cloth-wind layer has wind keys only).
STORM_LAYERS = (("*pat-rs-pat-forest-blizzard*", 300), ("*pat-rs-pat-forest-blizzard-height*", 350))


def door_volumes(m):
    """exact volumes of the rooms that see out through the three opened doors (spec sp_lighting.door_sun.regions)"""
    names = set(m["sp_lighting"]["door_sun"]["regions"])
    vols = {}
    for lv in m["levels"]:
        p = src_pak(lv)
        if p:
            vols.update(region_volumes(open(p, "rb").read(), names - set(vols)))
    assert set(vols) == names, sorted(names - set(vols))
    return [v for n in m["sp_lighting"]["door_sun"]["regions"] for v in vols[n]]


def _inside_any(P, vols):
    """bool mask over the points P (n,3): inside any convex volume (list of faces (nx, ny, nz, d): n.p <= d for every face).  Elementwise float64 like the scalar
    expression it replaces (no BLAS / FMA: the same sums in the same order)"""
    res = np.zeros(len(P), bool)
    for v in vols:
        ok = np.ones(len(P), bool)
        for f in v:
            ok &= f[0] * P[:, 0] + f[1] * P[:, 1] + f[2] * P[:, 2] <= f[3]
        res |= ok
    return res


def door_sun_overrides(m):
    """-> [(symbol, key name, value, kind)] kind: sun / cascade / exposure.  Symbols = every region (on in MP) whose volume overlaps an interior volume of the map."""
    sys.path.insert(0, os.path.join(ROOT, "tools", "win"))
    import rs_bisect
    names = rs_bisect.exe_names()
    mods = _symbol_table()

    def allrows(sym):
        h = rs.fnv(sym)
        for md in mods.values():
            if h in md.syms:
                o = {}
                for k, v, _ in md.syms[h]:
                    f, kind = struct.unpack("<fi", v)
                    o[k] = f if kind == -1 else struct.unpack("<ii", v)[1]
                    if kind != -1:
                        ints.add(k)
                return o
        return {}
    ints = set()
    prio = {}
    out_v = dict(allrows("*pat-rs-pat*"))
    out_v.update(allrows("*pat-rs-pat-cloudy*"))
    ivol = door_volumes(m)
    on = {n for names_ in plan(m)[0].values() for n in names_}
    syms = {}
    import numpy as np
    pts = np.stack(np.meshgrid(-560 + 1.0 * np.arange(71), 12 + 1.0 * np.arange(17), 210 + 1.0 * np.arange(111), indexing="ij"), -1).reshape(-1, 3)      # (same grid, same order)
    pts = pts[_inside_any(pts, ivol)]
    for lv in m["levels"]:
        pth = src_pak(lv)
        if not pth:
            continue
        data = open(pth, "rb").read()
        try:
            regs = [r for rr, _g in rs.read_pak_regions(data) for r in rr if rs.region_rs(r)]
        except Exception:
            continue
        vols = region_volumes(data, {r["name"] for r in regs})
        for r in regs:
            if (gate_of(r) and r["name"] not in on) or r["name"] not in vols:
                continue
            if len(pts) and _inside_any(pts, vols[r["name"]]).any():
                syms.setdefault(rs.region_rs(r), r["name"])
                prio[rs.region_rs(r)] = max(prio.get(rs.region_rs(r), -1), r["prio"])
    storm = {}
    for ssym, _sp in sorted(STORM_LAYERS, key=lambda x: x[1]):
        storm.update(allrows(ssym))
    res = []
    for sym in sorted(syms):
        for k, v in sorted(allrows(sym).items()):
            nm = names.get(k)
            if not nm:
                continue
            st = storm.get(k)
            if nm.startswith(DOOR_OUT) and k in out_v and abs(out_v[k] - v) > 1e-6:
                res.append((sym, nm, out_v[k], "sun", k in ints, v, st))
            elif nm.startswith(DOOR_CASC) and k in out_v and abs(out_v[k] - v) > 1e-6:
                res.append((sym, nm, out_v[k], "cascade", k in ints, v, st))
            elif nm == "tonemap:tonemap-light-range-min" and v > DOOR_EV_MIN_CAP:
                res.append((sym, nm, DOOR_EV_MIN_CAP, "exposure", False, v, None))
            elif nm.startswith(DOOR_OUT + DOOR_CASC) and st is not None and abs(st - v) > 1e-6 and prio[sym] < min(p for _s, p in STORM_LAYERS)                     and sym not in ("*pat-rs-pat*", "*pat-rs-pat-cloudy*"):     # (the outdoor base itself: the storm layer is above it everywhere)
                res.append((sym, nm, v, "storm", k in ints, v, st))
    return res


def hold_symbols(m):
    """symbols of the regions that are on in MP near the map and set a wind time-scale key (joint-wind-speed / -flutter-speed): the ext keeps those two constant
    (the shake fix: they are time scales, every change jumps the wind phase)"""
    mods = _symbol_table()
    keys = {rs.fnv("wind:joint-wind-speed"), rs.fnv("wind:joint-wind-flutter-speed")}
    sp = m["sp_lighting"]
    b, mg = m["bounds"], sp.get("margin", 80)
    on = {n for names in plan(m)[0].values() for n in names}
    out, seen = [], set()
    for lv, r in regions(m):
        if gate_of(r) and r["name"] not in on:
            continue
        sym = rs.region_rs(r)
        h = rs.fnv(sym)
        bb = box_of(r)
        if sym in seen or not bb or bb[1] < b[0] - mg or bb[0] > b[1] + mg or bb[5] < b[2] - mg or bb[4] > b[3] + mg:
            continue
        if any(h in md.syms and any(k in keys for k, _v, _ in md.syms[h]) for md in mods.values()):
            seen.add(sym)
            out.append(sym)
    return out


def header(keys=None):
    maps = [m for m in json.load(open(SPEC, encoding="utf-8"))["maps"] if m.get("sp_lighting") and (not keys or m["key"] in keys)]
    o = ["// generated by tools/maps/sp_lighting.py header - do not edit (sp_maps.json \"sp_lighting\")",
         "// per SP map: the pack level that identifies it, the interior boxes (x0 x1 y0 y1 z0 z1; LEGACY, flag t2r-spl-aabb.txt) and the interior regions' exact convex volumes",
         "// (face = nx ny nz d, inside = n.p <= d for all faces), forced EVs (inert: spec has none), override layers",
         "typedef struct { int nface; float f[8][4]; } spl_vol;",
         "typedef struct { const char *level; int forced; float ev_in, ev_out; int nbox; float box[8][6]; int nvol; spl_vol vol[16]; int ndvol; spl_vol dvol[16]; int nlayer; struct { const char *sym; int prio; float str; } layer[4]; } spl_map;",
         "// tonemap regions of the LEGACY ext replay (flag t2r-spl-replay.txt): map index, name, symbol, priority, blend-in s, blend-out s, whole-map base (no blend), world box x0 x1 y0 y1 z0 z1",
         "typedef struct { int map; const char *name, *sym; int prio; float blend, blend_out; int always; float box[6]; } spl_reg;",
         "// symbols whose wind time-scale keys the ext holds constant",
         "typedef struct { int map; const char *sym; } spl_hold;",
         "// door sun (flag t2r-spl-door-sun.txt = SP's original): symbol key value kind(0 sun / fog / sky, 1 cascade, 2 exposure cap, 3 storm only), the storm layers' value of the key (hs = 1)",
         "typedef struct { int map; const char *sym, *key; float v, orig; int kind, isint, hs; float storm; } spl_door;",
         "// doorways to the outdoors (sp_lighting.openings: weather.c storm fog seen through doors), box x0 x1 y0 y1 z0 z1",
         "typedef struct { int map; float box[6]; } spl_open;",
         "#define SPL_N %d" % len(maps),
         "#define SPL_LEVEL_ITEMS " + "".join(', "%s"' % m["sp_lighting"]["match_level"] for m in maps),
         "static const spl_map g_spl[] = {"]
    for m in maps:
        sp = m["sp_lighting"]
        bx = interior_boxes(m)
        vols = interior_volumes(m)
        assert len(bx) <= 8 and len(vols) <= 16 and len(sp.get("layers", [])) <= 4, m["key"]
        assert all(len(v) <= 8 for v in vols)
        boxes = ", ".join("{%s}" % ", ".join("%.2ff" % v for v in b) for b in bx)
        vs = ", ".join("{%d, {%s}}" % (len(v), ", ".join("{%s}" % ", ".join("%.6ff" % x for x in f) for f in v)) for v in vols)
        dv = door_volumes(m)
        assert len(dv) <= 16
        dvs = ", ".join("{%d, {%s}}" % (len(v), ", ".join("{%s}" % ", ".join("%.6ff" % x for x in f) for f in v)) for v in dv)
        lay = ", ".join('{"%s", %d, %.3ff}' % (L["symbol"], L["prio"], L.get("strength", 1.0)) for L in sp.get("layers", []))
        forced = int("ev_in" in sp or "ev_out" in sp)
        o.append('  {"%s", %d, %.2ff, %.2ff, %d, {%s}, %d, {%s}, %d, {%s}, %d, {%s}},  // %s' % (sp["match_level"], forced, sp.get("ev_in", 0.0), sp.get("ev_out", 0.0), len(bx),
                                                                                    boxes, len(vols), vs, len(dv), dvs, len(sp.get("layers", [])), lay, m["key"]))
    if not maps:
        o.append("  {0},")
    o.append("};")
    regs = []
    for k, m in enumerate(maps):
        for n, sym, pr, bl, bo, al, bb in tonemap_regions(m):
            regs.append('  {%d, "%s", "%s", %d, %.2ff, %.2ff, %d, {%s}},' % (k, n, sym, pr, bl, bo, al, ", ".join("%.2ff" % v for v in bb)))
    o.append("#define SPL_NREG %d" % len(regs))
    o.append("#define SPL_NREG_MAX 64")
    o.append("static const spl_reg g_spl_reg[] = {")
    o += regs or ["  {0},"]
    o.append("};")
    assert len(regs) <= 64, len(regs)
    hs = [(k, sym) for k, m in enumerate(maps) for sym in hold_symbols(m)]
    ds = [(k, ) + d for k, m in enumerate(maps) for d in door_sun_overrides(m)]
    o.append("#define SPL_NDOOR %d" % len(ds))
    o.append("static const spl_door g_spl_door[] = {")
    o += ['  {%d, "%s", "%s", %.6ff, %.6ff, %d, %d, %d, %.6ff},' % (k, sy, nm, v, og, {"sun": 0, "cascade": 1, "exposure": 2, "storm": 3}[kd], int(ii), st is not None, st or 0.0)
          for k, sy, nm, v, kd, ii, og, st in ds] or ["  {0},"]
    o.append("};")
    op = [(k, b["box"]) for k, m in enumerate(maps) for b in m["sp_lighting"].get("openings", [])]
    assert all(len(b) == 6 and b[0] <= b[1] and b[2] <= b[3] and b[4] <= b[5] for _, b in op)
    o.append("#define SPL_NOPEN %d" % len(op))
    o.append("static const spl_open g_spl_open[] = {")
    o += ['  {%d, {%s}},' % (k, ", ".join("%.2ff" % v for v in b)) for k, b in op] or ["  {0},"]
    o.append("};")
    o.append("#define SPL_NHOLD %d" % len(hs))
    o.append("static const spl_hold g_spl_hold[] = {")
    o += ['  {%d, "%s"},' % h for h in hs] or ["  {0},"]
    o.append("};")
    new = "\n".join(o) + "\n"
    if not os.path.exists(HEADER) or open(HEADER, encoding="utf-8").read() != new:
        open(HEADER, "w", encoding="utf-8", newline="\n").write(new)
    return len(maps)


# ------------------------------------------------------------------------------------------------ cli
def cmd_report(key):
    m = spec_of(key)
    sel, rows = plan(m)
    print("map %s, task state %s: %d gated render-settings regions near the map, %d on" %
          (key, m["sp_lighting"]["task"]["subnode"], len(rows), sum(1 for r in rows if r[4])))
    for lv, n, pr, sym, on, txt, bb in sorted(rows, key=lambda r: (not r[4], -r[2])):
        print("  %-3s %5d %-44s %-52s %s | x %.0f..%.0f z %.0f..%.0f | %s" % ("ON" if on else "off", pr, n, sym, lv, bb[0], bb[1], bb[4], bb[5], txt))


GRID_KEYS = ["lighting:sun-light:dir-x", "lighting:sun-light:dir-y", "lighting:sun-light:dir-z", "lighting:sun-light:rgbi-r",
             "lighting:sun-light:rgbi-g", "lighting:sun-light:rgbi-b", "lighting:sun-light:rgbi-i", "sky:rotation", "sky:intensity",
             "tonemap:tonemap-light-range-min", "tonemap:tonemap-light-range-max", "tonemap:tonemap-set-point", "tonemap:tonemap-adaption-time",
             "skydome:enable-cloud-shadow"]


def sym_values(mods, sym, keys):
    h = rs.fnv(sym)
    want = {rs.fnv(k): k for k in keys}
    for md in mods.values():
        if h in md.syms:
            out = {}
            for k, v, _ in md.syms[h]:
                if k in want:
                    f, kind = struct.unpack("<fi", v)
                    out[want[k]] = f if kind == -1 else struct.unpack("<ii", v)[1]
            return out
    return {}


def cmd_grid(key, step=6.0, y=19.7, base="*pat-rs-pat*", at=None):
    """effective sun direction / colour / intensity / sky / tonemap at a grid of camera positions over the map, resolving the level
    default symbol and every always-on region (ungated or ungated by the plan) by priority, per key, at full strength - what the
    engine's region manager and the ext replay converge to.  Prints the distinct looks and where they occur."""
    m = spec_of(key)
    mods = _symbol_table()
    on = {n for names in plan(m)[0].values() for n in names}
    regs = []
    rb = m["sp_lighting"].get("replay_boxes", {})
    drop = dropped(m)
    for lv, r in regions(m):
        if (r["name"] in drop and r["name"] not in rb) or (gate_of(r) and r["name"] not in on and r["name"] not in rb):
            continue
        bb = tuple(rb[r["name"]]) if r["name"] in rb else box_of(r)
        if bb:
            regs.append((r["prio"], r["name"], rs.region_rs(r), bb, sym_values(mods, rs.region_rs(r), GRID_KEYS)))
    regs.sort(key=lambda x: x[0])
    bx = m["bounds"] if not at else [at[0], at[0], at[1], at[1]]
    looks = {}
    x = bx[0]
    while x <= bx[1]:
        z = bx[2]
        while z <= bx[3]:
            cur = dict(sym_values(mods, base, GRID_KEYS))
            src = {k: base for k in cur}
            for pr, n, sym, bb, vals in regs:
                if bb[0] <= x <= bb[1] and bb[2] <= y <= bb[3] and bb[4] <= z <= bb[5]:
                    for k, v in vals.items():
                        cur[k], src[k] = v, n
            sig = tuple(round(cur.get(k, float("nan")), 3) for k in GRID_KEYS)
            looks.setdefault(sig, []).append((x, z, src))
            z += step
        x += step
    allp = [p for v in looks.values() for p in v]
    print("%s: grid %.0f m, camera y %.1f, %d positions" % (key, step, y, len(allp)))
    for title, ks in (("SUN + SKY (dir, colour, intensity, sky rotation / intensity, cloud shadow)", GRID_KEYS[:9] + GRID_KEYS[13:]),
                      ("TONEMAP (range min / max, set point, adaption time)", GRID_KEYS[9:13])):
        groups = {}
        for sig, pts in looks.items():
            sel = tuple((-999.0 if sig[GRID_KEYS.index(k)] != sig[GRID_KEYS.index(k)] else sig[GRID_KEYS.index(k)] + 0.0) for k in ks)
            groups.setdefault(sel, []).extend(pts)
        print(title + ": %d distinct" % len(groups))
        for sel, pts in sorted(groups.items(), key=lambda kv: -len(kv[1])):
            xs, zs = [p[0] for p in pts], [p[1] for p in pts]
            print("  %4d pts x %.0f..%.0f z %.0f..%.0f  %s" % (len(pts), min(xs), max(xs), min(zs), max(zs), " ".join("%s=%g" % (k.split(":")[-1], v) for k, v in zip(ks, sel))))


def cmd_selftest():
    n = 0
    for fn in sorted(os.listdir(CACHE)):
        if not fn.endswith("-ingame.pak"):
            continue
        d = open(os.path.join(CACHE, fn), "rb").read()
        try:
            if not rs.read_pak_regions(d):
                continue
        except Exception:
            continue
        names = {r["name"] for regs, _ in rs.read_pak_regions(d) for r in regs if gate_of(r)}
        new, done = strip_gating(d, names)
        bad = verify(d, new, set(done))
        assert not bad, (fn, bad)
        n += 1
    print("selftest ok: %d paks" % n)


if __name__ == "__main__":
    a = sys.argv[1:]
    if not a:
        print(__doc__)
    elif a[0] == "report":
        cmd_report(a[1])
    elif a[0] == "build":
        build(spec_of(a[1]))
    elif a[0] == "header":
        print("sp_lighting.h: %d map(s)" % header(a[1:]))
    elif a[0] == "grid":
        cmd_grid(a[1], at=(float(a[2]), float(a[3])) if len(a) >= 4 else None, y=float(a[4]) if len(a) >= 5 else 19.7)
    elif a[0] == "selftest":
        cmd_selftest()
