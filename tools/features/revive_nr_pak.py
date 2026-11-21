"""Revive pair clips on a NEW data page of a carrier pak ("page carriers").

The help-up revive (revive2013.c, kind PS_REVIVE) plays its halves by carrier names: existing ANIM resources of a small game anim pak that MP
loads (host = anim-npc-m-cover-share, base-female rig, SP cover idles nothing in MP asks for). The baked ClipData of the new halves are too big
for the carriers' own bodies (a 3 s full-body half is ~45 KB at 15 fps), so instead of overwriting in place:
  * every new ClipData goes on ONE new data page appended to the pak (tools/part1/t2pak.TPak.add_page: existing pages, item tables and
    fixups keep their (page, offset));
  * the carrier ANIM's +0x08 ClipData slot is repointed to it;
  * the carrier's align / apReference raw channels get the half's own rows (f32): the channel header's frame count and flags are rewritten
    and its data slot (+0x08) is repointed to a block on the same new page.
The carrier keeps its name; its old ClipData / channel bytes stay in the file, unused.

build(host_bytes, halves) -> patched bytes;  halves = [(carrier, clip bytes, align rows (F,7), apReference rows (F,7))]
verify(host_bytes, out_bytes, halves) -> True when every carrier decodes to exactly the given clip / rows and nothing else changed.
candidates(host_bytes, used) -> carrier names usable for new halves (ANIMs with both channels, not in `used`), in pak order."""
import os
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
for p in (os.path.join(ROOT, "tools", "models"), os.path.join(ROOT, "tools", "part1"), os.path.join(ROOT, "re", "factions2013", "t1anim")):
    if p not in sys.path:
        sys.path.append(p)
import ndpak  # noqa: E402
import t2pak  # noqa: E402

SID64_ALIGN = 0x509903bb65ac341e          # fnv64('align')
SID64_APREF = 0x05fed8d7a1d8cf89          # fnv64('apReference')
MAX_PAGE = 0xFFFE0                        # every game page is < 1 MB


def _pak(data):
    """ndpak.Pak from bytes (it reads a path)"""
    import tempfile
    fd, path = tempfile.mkstemp(suffix=".pak")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
        return ndpak.Pak(path)
    finally:
        os.remove(path)


def _r16(n):
    return (n + 15) & ~15


def _anim(p, name):
    it = [x for x in p.items if x[0] == name and x[1] == "ANIM"]
    if len(it) != 1:
        raise KeyError(f"ANIM {name}: {len(it)} items")
    return it[0][3] + 48


def channels(p, base):
    """[(sid64, channel header addr, frames, flags, data addr)] of the ANIM at payload `base`"""
    rc = p.ptr(base + 0x10)
    if not rc:
        return []
    n = p.u32(rc)
    sp, cp = p.ptr(rc + 8), p.ptr(rc + 0x10)
    out = []
    for j in range(n):
        c = p.ptr(cp + 8 * j)
        nf, fl = struct.unpack_from("<HH", p.d, c)
        out.append((p.q(sp + 8 * j), c, nf, fl, p.ptr(c + 8)))
    return out


def encode_rows(rows):
    """(F,7) pos + quat xyzw rows -> (flags, f32 bytes): frame 0 as quat, trans, scale (10 values), then frames 1.. with the animated components
    (the game's own channel layout, as t1raw.t2_encode)"""
    import t1raw
    return t1raw.t2_encode(rows)


def decode_rows(p, nf, fl, dp):
    import t1raw
    return t1raw.decode_channel(p.d, nf, fl, dp, False)[0]


def candidates(host, used=()):
    p = _pak(host)
    out = []
    for name, typ, pi, io in p.items:
        if typ != "ANIM" or name in used:
            continue
        sids = {s for s, *_ in channels(p, io + 48)}
        if SID64_ALIGN in sids and SID64_APREF in sids:
            out.append(name)
    return out


def build(host, halves):
    """every half's ClipData + its two channel blocks on new data pages (as many as needed, each < MAX_PAGE; a half never spans two pages)"""
    p = _pak(host)
    t = t2pak.TPak(host)
    pages, at = [bytearray()], []
    for carrier, clip, al, ap in halves:
        blob, ent = bytearray(), {}
        ent["clip"] = 0
        blob += clip
        for key, rows in (("align", al), ("apReference", ap)):
            fl, data = encode_rows(rows)
            blob += bytes(_r16(len(blob)) - len(blob))
            ent[key] = (len(blob), len(rows), fl)
            blob += data
        if 32 + _r16(len(blob)) > MAX_PAGE:
            raise ValueError(f"{carrier}: one half is {len(blob):#x} bytes > one page ({MAX_PAGE:#x})")
        body = pages[-1]
        if 32 + _r16(_r16(len(body)) + len(blob)) > MAX_PAGE:
            pages.append(bytearray())
            body = pages[-1]
        body += bytes(_r16(len(body)) - len(body))
        base = len(body)
        body += blob
        at.append((len(pages) - 1, base, ent))
    placed = [t.add_page(bytes(b)) for b in pages]
    for (carrier, clip, al, ap), (k, base, ent) in zip(halves, at):
        pg, shift = placed[k]
        a = _anim(p, carrier)
        sp, so = t.loc(a + 8)
        if (sp, so) not in t.fix:
            raise ValueError(f"{carrier}: ANIM +0x08 has no fixup")
        t.set_ptr(sp, so, pg, shift + base + ent["clip"])
        fpg, foff = t.loc(a + 4)
        struct.pack_into("<I", t.pages[fpg], foff, t.u32(fpg, foff) & ~0x5)          # not streamed (0x4), not looping (0x1): psync restarts loops itself
        chs = {s_: c for s_, c, *_ in channels(p, a)}
        for key, sid in (("align", SID64_ALIGN), ("apReference", SID64_APREF)):
            c = chs[sid]
            off, nf, fl = ent[key]
            hp, ho = t.loc(c)
            struct.pack_into("<HH", t.pages[hp], ho, nf, fl)
            dp_, do_ = t.loc(c + 8)
            if (dp_, do_) not in t.fix:
                raise ValueError(f"{carrier}: {key} channel data slot has no fixup")
            t.set_ptr(dp_, do_, pg, shift + base + off)
    return t.serialize()


def verify(host, out, halves):
    import numpy as np
    p, q = _pak(host), _pak(out)
    names = {h[0] for h in halves}
    if sorted((n, ty) for n, ty, _a, _b in p.items) != sorted((n, ty) for n, ty, _a, _b in q.items):
        return False
    for carrier, clip, al, ap in halves:
        b = _anim(q, carrier)
        ca = q.ptr(b + 8)
        if q.d[ca:ca + len(clip)] != clip or q.u32(b + 4) & 0x5:
            return False
        got = {s: (nf, fl, dp) for s, c, nf, fl, dp in channels(q, b)}
        for rows, sid in ((al, SID64_ALIGN), (ap, SID64_APREF)):
            nf, fl, dp = got[sid]
            if nf != len(rows) or np.abs(decode_rows(q, nf, fl, dp) - np.asarray(rows)).max() > 1e-5:
                return False
    for n, ty, _a, io in p.items:                 # every other ANIM: same ClipData bytes and channel rows
        if ty != "ANIM" or n in names:
            continue
        b, b2 = io + 48, _anim(q, n)
        ca, ca2 = p.ptr(b + 8), q.ptr(b2 + 8)
        if not ca:
            continue
        sz = p.u32(ca + 8)
        if p.d[ca:ca + sz] != q.d[ca2:ca2 + sz] or p.u32(b + 4) != q.u32(b2 + 4):
            return False
    return True


# ---------------------------------------------------------------- build stage (build_dll.stage_revive_nr)
HOST_PAK = "anim-npc-alert-caps"          # small anim pak every MP match loads (the first gun execution carrier set lives in it too)
SETS = ("kneel", "prone")                 # baked sets (re/revive-1118/bake/out/<set>/manifest.json): [0] kneel help-up, [1] prone dap-up
HEADER = os.path.join(ROOT, "tools", "ext", "revive_nr.h")
NPATH = 32


def src_dir():
    """baked halves: T2R_REVIVE_NR_DIR, else <T2R_MAIN_ROOT or this checkout>/re/revive-1118/bake/out"""
    d = os.environ.get("T2R_REVIVE_NR_DIR")
    if d:
        return d
    for r in (os.environ.get("T2R_MAIN_ROOT"), ROOT):
        if r and os.path.isdir(os.path.join(r, "re", "revive-1118", "bake", "out")):
            return os.path.join(r, "re", "revive-1118", "bake", "out")
    return None


def load_set(d, name):
    """[(meta, clip bytes, align rows, apReference rows)] of one baked set, manifest order"""
    import json
    import numpy as np
    out = []
    for m in json.load(open(os.path.join(d, name, "manifest.json"))):
        r = m["role"]
        z = np.load(os.path.join(d, name, r + ".rows.npz"))
        out.append((m, open(os.path.join(d, name, r + ".clip"), "rb").read(), z["align"], z["apReference"]))
    return out


def used_carriers(game_host, staged_host):
    """ANIMs an earlier build stage already re-baked (ClipData bytes, flags or channel headers differ from the game's copy)"""
    p, q = _pak(game_host), _pak(staged_host)
    used = set()
    for n, ty, _a, io in p.items:
        if ty != "ANIM":
            continue
        b, b2 = io + 48, _anim(q, n)
        ca, ca2 = p.ptr(b + 8), q.ptr(b2 + 8)
        if not ca:
            continue
        sz = p.u32(ca + 8)
        same = p.d[ca:ca + sz] == q.d[ca2:ca2 + sz] and p.u32(b + 4) == q.u32(b2 + 4)
        same = same and [x[2:4] for x in channels(p, b)] == [x[2:4] for x in channels(q, b2)]
        if not same:
            used.add(n)
    return used


def assign(game_host, staged_host, roles):
    """role -> carrier, in pak order over the free carriers"""
    free = candidates(game_host, used_carriers(game_host, staged_host))
    if len(free) < len(roles):
        raise SystemExit(f"revive nr: {len(roles)} halves but only {len(free)} free carriers in {HOST_PAK}")
    return dict(zip(roles, free))


def _cs(x):
    return '"%s"' % x


def _set_tables(name, metas, car):
    """one set's rows: (enter entries, loop [L, R] x [reviver, revived], finish [L, R] x [...], loop seconds, finish seconds).
    Roles: enter_<side>_<start> (+ _vic, else enter_<side>_vic, else enter_vic), loop_<side> (+ _vic, else loop_vic),
    pull_<side> / fin_<side> (+ _vic)."""
    by = {m["role"]: m for m in metas}
    key = lambda r: f"{name}/{r}"
    has = lambda r: key(r) in car
    ents = []
    for m in metas:
        r = m["role"]
        parts = r.split("_")
        if len(parts) != 3 or parts[0] != "enter" or parts[1] not in ("L", "R") or parts[2] == "vic":
            continue
        vic = next((v for v in (r + "_vic", f"enter_{parts[1]}_vic", "enter_vic") if has(v)), None)
        if vic is None:
            raise SystemExit(f"revive nr: {name} {r} has no revived half")
        ents.append((m, car[key(r)], car[key(vic)]))
    loop, fin, secs = [], [], [0.0, 0.0, 0.0]
    for sd in "LR":
        lv = next((v for v in (f"loop_{sd}_vic", "loop_vic") if has(v)), None)
        loop.append((car.get(key(f"loop_{sd}"), ""), car.get(key(lv), "") if lv else ""))
        fr = next((f for f in (f"pull_{sd}", f"fin_{sd}") if has(f)), None)
        fin.append((car[key(fr)] if fr else "", car.get(key(fr + "_vic"), "") if fr else ""))
        if has(f"loop_{sd}"):
            secs[0] = max(secs[0], by[f"loop_{sd}"]["seconds"])
        if fr:
            secs[1] = max(secs[1], by[fr]["seconds"])
            sk = by[fr].get("skip_max", 0.0)
            secs[2] = sk if sd == "L" else min(secs[2], sk)            # (the smaller of both sides)
    return ents, loop, fin, secs


def write_header(path, car, sets):
    """tools/ext/revive_nr.h: carrier names + the walk-in table (revive2013.c). sets = {set name: metas}; car = {"<set>/<role>": carrier}
    ({} = the empty table: no baked set, revive2013.c plays the 2013 pair)"""
    L = ["// generated by tools/features/revive_nr_pak.py (build_dll.stage_revive_nr) - do not edit",
         "// Two revive sets, each one psync chain ENTER -> LOOP -> FINISH on the revived's own locator (ap = her position + her own facing = the",
         "// clips' space): [0] kneel help-up (No Return ally revive edited for the all-fours downed pose; FINISH = the pull-up), [1] prone dap-up",
         "// (a prone reviver; FINISH = she rolls back onto her belly). ENTER = one walk-in / crawl-in per side (L / R of her body) and start; path =",
         "// the reviver's pelvis (x, z) every 0.1 s in that space (start skip by the nearest sample). Every ENTER / LOOP ends on the pose FINISH",
         "// starts with. A set with no rows is not in this build.",
         "#define RVNR_NPATH %d" % NPATH,
         "typedef struct { char set; char side; short bearing; float walk_s, dur_s; const char *att, *vic; int npath; float path[RVNR_NPATH][2]; } rvnr_enter_t;"]
    rows, loops, fins, secs = [], [], [], []
    for k, name in enumerate(SETS):
        if car and sets.get(name):
            e, lp, fn, sc = _set_tables(name, sets[name], car)
        else:
            e, lp, fn, sc = [], [("", ""), ("", "")], [("", ""), ("", "")], [0.0, 0.0, 0.0]
        rows += [(k, m, a, v) for m, a, v in e]
        loops.append(lp); fins.append(fn); secs.append(sc)
    L.append("#define RVNR_N_ENTER %d" % len(rows))
    L.append("static const rvnr_enter_t RVNR_ENTER[%d] = {" % max(1, len(rows)))
    for k, m, a, v in rows:
        pts = m.get("path", [])[:NPATH]
        L.append("    {%d, '%s', %d, %.3ff, %.3ff, %s, %s, %d, {%s}},   // %s/%s" % (k, m["side"], int(m.get("bearing", 0)), m.get("walk_s", 0.0), m["seconds"], _cs(a), _cs(v),
                                                                           len(pts), ", ".join("{%.3ff, %.3ff}" % (x, z) for x, z in pts) or "{0.0f, 0.0f}", SETS[k], m["role"]))
    if not rows:
        L.append('    {0, 0, 0, 0.0f, 0.0f, "", "", 0, {{0.0f, 0.0f}}},')
    L.append("};")
    tab = lambda t: "{" + ", ".join("{" + ", ".join("{%s, %s}" % (_cs(a), _cs(v)) for a, v in st) + "}" for st in t) + "}"
    L.append("static const char *const RVNR_LOOP[2][2][2] = %s;   // [set][side L / R][reviver / revived]" % tab(loops))
    L.append("static const char *const RVNR_FIN[2][2][2] = %s;   // kneel: the pull-up; prone: back onto her belly" % tab(fins))
    L.append("static const float RVNR_LOOP_S[2] = {%.3ff, %.3ff}, RVNR_FIN_S[2] = {%.3ff, %.3ff};" % (secs[0][0], secs[1][0], secs[0][1], secs[1][1]))
    L.append("static const float RVNR_FIN_SKIP_S[2] = {%.3ff, %.3ff};   // a short revive may start FINISH this far in (before she moves)" % (secs[0][2], secs[1][2]))
    txt = "\n".join(L) + "\n"
    if not os.path.exists(path) or open(path, "rb").read() != txt.encode():
        open(path, "w", newline="\n").write(txt)
    return txt


def stage(game_host, staged_host, header=HEADER):
    """-> (patched host bytes or None, {"<set>/<role>": carrier}); writes the header either way"""
    d = src_dir()
    halves, sets = [], {}
    for name in SETS:
        if d and os.path.exists(os.path.join(d, name, "manifest.json")):
            for m, clip, al, ap in load_set(d, name):
                sets.setdefault(name, []).append(m)
                halves.append((f"{name}/{m['role']}", clip, al, ap))
    if not halves:
        write_header(header, {}, {})
        return None, {}
    car = assign(game_host, staged_host, [h[0] for h in halves])
    hv = [(car[r], clip, al, ap) for r, clip, al, ap in halves]
    out = build(staged_host, hv)
    if not verify(staged_host, out, hv):
        raise SystemExit("revive nr: the patched pak does not decode back to the baked halves")
    write_header(header, car, sets)
    return out, car
