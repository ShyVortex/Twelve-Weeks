"""Make STREAMED SP melee clips resident in their own MP-loaded pak (v5-hatch).

Why: a clip longer than ~1 s in an anim pak is STREAMED (re/melee-finishers.md): its ANIM (flags 0xc) points at a 64-byte header ClipData (0 frames,
the total frame count at +0x22), the pak holds `<name>-chunk-0` (frames 0..30) and `<name>-chunk-last` (flags 0x18), an ANIM_STREAM item names the stream
and the remaining 30-frame chunks live in sp-common.psarc animstream97/<pak>.<name>.stm (one ClipData per chunk, each chunk's frame 0 = the previous chunk's
last frame). The engine's own melee move requests the stream; the ext plays its finishers through animate_, which never does, so a streamed clip plays as
the bind pose (both bodies stand still). SP's hatchet disarms (fist-1h-blade-disarm-iron-rhino / -punch-n-hack) and three 1h-blunt disarms are such clips.

What this does, per clip, in place in the game's own pak (anim-melee-abby-t2 is loaded by every MP match already, abby-player-fundamentals):
  * decodes chunk-0 + every .stm chunk with the game's own OrbisAnim handlers (re/uc4ps4/tools/uc4anim.ClipDecoder, emulated) into one frame list,
  * re-encodes ONE full ClipData (re/uc4ps4/tools/uc4enc layout): per group the chunk-0 group stream is kept as the base (its constant ops 0x16 / 0x18 /
    0x19 and their tables, i.e. the float-channel and constant joint values bit-exact), then a raw unpack (0x0b, code 0x80 = 16 bytes) + AoS lerp store
    (0x0f) writes every component that is not the chunk-0 constant in every frame (float32, no quantisation); the written-masks are chunk-0's (equal in
    every chunk, checked),
  * appends the ClipData bodies to the end of the pak's last data page (pages stay < 1 MB like every game page; the page header size + the page table are
    updated, the following page moves back in the file; no fixup is added - the ANIM +0x08 slot keeps its fixup, only its dst page / offset change),
  * clears the ANIM's streamed bit (flags 0xc -> 0x8, like every resident clip), so animate_ samples the full clip. The ANIM keeps its name, its raw
    channels (align / apReference, already the full length in the pak) and its effect table (the clip's own sounds); chunk-0 / chunk-last / ANIM_STREAM
    are left as they are.
verify(): every converted ANIM decodes back (emulated) to the source frames within 1e-6 and is a plain resident clip.
  python unstream_anims.py [<out.pak>]      builds from the game's files (read-only) and self-checks."""
import os
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.dirname(HERE)
ROOT = os.path.dirname(TOOLS)
MAIN = r"."
UC4T = os.path.join(ROOT, "re", "uc4ps4", "tools")
for p in (os.path.join(ROOT, "tools", "models"), os.path.join(MAIN, "tools", "models"), UC4T, os.path.join(MAIN, "re", "uc4ps4", "tools"), TOOLS):
    if p not in sys.path:
        sys.path.append(p)

PAK = "anim-melee-abby-t2"
# the clips made resident (both halves of each SP disarm; mduel_fin.h rows mf-fist-1h-blade-disarm-* / mf-fist-1h-blunt-disarm-*)
CLIPS = [
    "abby-disarm-kill-1hblade-iron-rhino--abby", "abby-disarm-kill-1hblade-iron-rhino--npc-f",
    "abby-disarm-kill-1hblade-punch-n-hack--abby", "abby-disarm-kill-1hblade-punch-n-hack--npc-f",
]
# Variants that add variety without changing functionality are welcome (SP run: fist-1h-blunt-disarm-arm-break-finisher x2, the third
# front disarm of a 1h-blunt holder next to left-back-hand / shoulder-check): its -sync halves are streamed stubs too and both CONVERT cleanly (122 frames
# from 5 chunks each, 142752 / 135296 bytes, decode-back max err 0) - but build() puts every converted clip into the pak's ONE last data page and with these two
# that page would be 0x7c190 + 0xc7760 bytes > MAX_PAGE (ValueError "too many clips for one page"). NOT in CLIPS until build() can use a second page: adding them
# there breaks the data build. When it can: move the two names into CLIPS - MARKER2 below is then written and ctxdown.c (CD_UNSTREAM_MARKER2) + gen_duel_fin.py
# (the row mf-fist-1h-blunt-disarm-arm-break-finisher appears by itself) are ready for it.
CLIPS_PS33_PENDING = ["abby-disarm-kill-1hblunt-arm-break--abby", "abby-disarm-kill-1hblunt-arm-break--npc-f"]
MAX_PAGE = 0xFFFE0            # every game page is < 1 MB; 0xfffe0 = the largest page of a shipped pak (anim-npc-m-p, anim-abby-player-mm-explore 0xfffd0)
EPS = 1e-6
MAGIC = 0x41430102
# The ext cannot tell a resident clip from a streamed stub (get-animation-duration reads the stub header's total frame count), so a client with the game's
# own pak would pick the rows and play the bind pose. MARKER = a now-unused ANIM of the converted set (the first clip's -chunk-0, 31 frames = 1.0 s, only
# ever read by the stream of the clip that is resident now) renamed in place (name string + ANIM +0x38 name sid, chunk bit cleared): ctxdown.c
# cd_unstream_ok() = get-animation-duration of MARKER > 0.2 s, i.e. this pak is loaded; else the rows count as not loaded.
MARKER = "t2r-unstreamed-disarms-1"
MARKER2 = "t2r-unstreamed-disarms-2"      # ps33: = the arm-break clips are resident (the -chunk-0 ANIM of MARKER2_CLIP renamed; ctxdown.c CD_UNSTREAM_MARKER2)
MARKER2_CLIP = "abby-disarm-kill-1hblunt-arm-break--abby"


def fnv(s):
    h = 0xCBF29CE484222325
    for c in s.encode():
        h = ((h ^ c) * 0x100000001B3) & (2 ** 64 - 1)
    return h


def _round16(n):
    return (n + 15) & ~15


def _load(data):
    import ndpak
    import tempfile
    fd, tmp = tempfile.mkstemp(suffix=".pak")
    os.close(fd)
    try:
        open(tmp, "wb").write(data)
        return ndpak.Pak(tmp)
    finally:
        os.remove(tmp)


def game_file(rel):
    """a file of sp-common.psarc (cached under re/gamebin/<rel> of this or the main checkout, else read from the install, read-only)"""
    for b in (ROOT, MAIN):
        p = os.path.join(b, "re", "gamebin", *rel.split("/"))
        if os.path.exists(p):
            return open(p, "rb").read()
    import dsar_list
    game = os.environ.get("T2_GAME", "C:/Games/The Last of Us Part II Remastered")
    d, ent, bs, bsz = dsar_list.open_files(os.path.join(game, "build", "pc", "main", "sp-common.psarc"))
    data = dsar_list.extract(d, ent, bs, bsz, rel)
    dst = os.path.join(ROOT, "re", "gamebin", *rel.split("/"))
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    open(dst, "wb").write(data)
    return data


def stm_chunks(stm):
    """the ClipData chunks of a .stm file, in order (each a complete ClipData: magic, skeleton, size at +8)"""
    out, pos = [], 0
    m = struct.pack("<I", MAGIC)
    while True:
        i = stm.find(m, pos)
        if i < 0:
            return out
        sz = struct.unpack_from("<I", stm, i + 8)[0]
        sig = struct.unpack_from("<I", stm, i + 4)[0]
        if 0x30 < sz <= len(stm) - i and (not out or sig == struct.unpack_from("<I", out[0], 4)[0]):
            out.append(stm[i:i + sz])
            pos = i + sz
        else:
            pos = i + 4


def _anim(p, name):
    it = [x for x in p.items if x[0] == name and x[1] == "ANIM"]
    if not it:
        raise KeyError(name)
    base = it[0][3] + 48
    ca = p.pages[p.fix[base + 8]][0] + p.q(base + 8)
    return base, ca


def _clip(p, name):
    base, ca = _anim(p, name)
    return bytes(p.d[ca:ca + p.u32(ca + 8)])


class Frames:
    """every frame of a streamed clip, decoded: frames[f][g] = (n_g, 12) float32 (scale xyz,0 | quat xyzw | trans xyz,0, NaN = not written)"""

    def __init__(self, emu, chunks, total):
        from uc4anim import ClipDecoder
        self.frames = []
        self.seams = []
        for k, c in enumerate(chunks):
            dec = ClipDecoder(c, emu)
            fr = [dec.eval_frame(f) for f in range(dec.nframes)]
            if k:
                prev = self.frames[-1]
                self.seams.append(max(float(abs(prev[g] - fr[0][g])[~(prev[g] != prev[g])].max(initial=0.0)) for g in prev))
                fr = fr[1:]
            self.frames += fr
        if len(self.frames) != total:
            raise ValueError(f"chunks give {len(self.frames)} frames, the header says {total}")
        # each chunk picks its own quaternion hemisphere (the seams are q / -q, dot = -1): one continuous sign over the whole clip, or the
        # lerp between the seam frames passes through zero (same rotation at every key, garbage between the keys)
        self.flips = 0
        for g in self.frames[0]:
            for f in range(1, len(self.frames)):
                a, b = self.frames[f - 1][g], self.frames[f][g]
                dot = (a[:, 4:8] * b[:, 4:8]).sum(1)
                neg = dot < 0
                if neg.any():
                    b[neg, 4:8] = -b[neg, 4:8]
                    self.flips += int(neg.sum())


def _streams(clip):
    G = struct.unpack_from("<H", clip, 0xC)[0]
    recs = [struct.unpack_from("<IBBBBIHH", clip, 0x30 + 16 * g) for g in range(G)]
    data0 = min(r[5] for r in recs)
    offs = sorted(set(r[0] for r in recs)) + [data0]
    out = []
    for r in recs:
        nxt = min(o for o in offs if o > r[0])
        out.append(bytes(clip[r[0]:nxt]))
    return recs, out


def _const_ops(stream):
    import uc4enc
    ops = uc4enc.group_ops(stream)
    keep, p = [], 0
    for op, a in ops:
        if op not in (0x16, 0x18, 0x19):
            break
        keep.append(stream[p:p + 2 + 2 * len(a)])
        p += 2 + 2 * len(a)
    tabs = [struct.unpack_from("<%dH" % (len(k) // 2 - 1), k, 2)[2] & ~3 for k in keep]
    # where the const tables end: the first table of a non-const op after them (the compressed key tables, dead once our raw ops replace those
    # ops), else the stream end. Real clips put the const tables first (0x60 / 0x40 ..), the decompression tables after them.
    rest = [a[2] & ~3 for op, a in ops[len(keep):] if len(a) >= 3]
    cut = min([t for t in rest if t > max(tabs, default=0)], default=len(stream))
    return b"".join(keep), (min(tabs) if tabs else len(stream)), cut


def encode(chunk0, frames, anim_comps):
    """one full ClipData: chunk-0's header / groups / const ops / masks + raw per-frame data for anim_comps {g: [(row, kind)]}"""
    import uc4enc
    G = struct.unpack_from("<H", chunk0, 0xC)[0]
    F = len(frames)
    fps = struct.unpack_from("<f", chunk0, 0x1C)[0]
    recs, streams = _streams(chunk0)
    nmask = recs[0][0] - 0x30 - 16 * G            # the written-mask table between the records and the first stream (+ its padding)
    masks = chunk0[0x30 + 16 * G:recs[0][0]]
    KO = {"s": 0, "q": 4, "t": 8}
    new_streams, datas, strides = [], [], []
    for g in range(G):
        st = streams[g]
        comps = anim_comps.get(g, [])
        if not comps:
            if recs[g][6] == 0:                           # constant-only (or empty) group: chunk-0's stream as is
                new_streams.append(st); datas.append(b""); strides.append(0)
                continue
            # (an animated group whose values are all chunk-0's constants: const ops only)
        cops, first_tab, cut = _const_ops(st)
        n = len(comps)
        npad = (n + 3) & ~3
        nj = recs[g][3]
        blob = bytearray(st[:cut])
        blob += bytes(_round16(len(blob)) - len(blob))
        ops = bytearray(cops)
        stride = 0
        data = b""
        if n:
            sink = nj * 0x30
            code_off = len(blob)
            blob += bytes([0x80]) * n + bytes(npad - n)
            blob += bytes(_round16(len(blob)) - len(blob))
            out_off = len(blob)
            offs = [r * 0x30 + {"s": 0x00, "q": 0x10, "t": 0x20}[k] for r, k in comps] + [sink] * (npad - n)
            blob += struct.pack("<%dH" % npad, *offs)
            blob += bytes(_round16(len(blob)) - len(blob))
            ops += struct.pack("<H6H", 0x0B | (6 << 8), n | 0x8000, 3, code_off, 0, 0, 16 * n)
            ops += struct.pack("<H4H", 0x0F | (4 << 8), npad, 3, out_off, 0)
            stride = 16 * n
            dd = bytearray()
            for f in range(F):
                a = frames[f][g]
                for r, k in comps:
                    v = a[r, KO[k]:KO[k] + 4].astype("<f4").copy()
                    if k != "q":
                        v[3] = 0.0
                    dd += v.tobytes()[::-1]                 # the unpack op reads a float4 as one big-endian field
            data = bytes(dd)
        ops += struct.pack("<H", 0)
        if len(ops) > first_tab:
            raise ValueError(f"group {g}: op list {len(ops)} bytes runs into the first const table at {first_tab}")
        # clear the old op list (its non-const ops) and write ours
        old = 0
        for op, a in uc4enc.group_ops(st):
            old += 2 + 2 * len(a)
        blob[0:min(old + 2, first_tab)] = bytes(min(old + 2, first_tab))
        blob[0:len(ops)] = ops
        new_streams.append(bytes(blob)); datas.append(data); strides.append(stride)
    base = 0x30 + 16 * G + nmask
    body = bytearray()
    soff, pos = [], base
    for s in new_streams:
        soff.append(pos)
        s = s + bytes(_round16(len(s)) - len(s))
        body += s
        pos += len(s)
    doffs, last_end = [], 0
    for g in range(G):
        doffs.append(pos)
        if datas[g]:
            body += datas[g]
            last_end = pos + len(datas[g])
            pos += _round16(len(datas[g]))
            body += bytes(pos - last_end)
    recb = bytearray()
    for g in range(G):
        r = recs[g]
        recb += struct.pack("<IBBBBIHH", soff[g], r[1], r[2], r[3], r[4], doffs[g], strides[g], uc4enc.fetch_size(strides[g]))
    head = bytearray(chunk0[:0x30])
    struct.pack_into("<I", head, 0x08, pos)
    struct.pack_into("<HH", head, 0x0C, G, F)
    struct.pack_into("<I", head, 0x18, last_end or pos)
    struct.pack_into("<f", head, 0x1C, fps)
    struct.pack_into("<HH", head, 0x20, 0, F)
    struct.pack_into("<f", head, 0x24, 1.0 / max(F - 1, 1))
    struct.pack_into("<f", head, 0x28, float(F - 1))
    struct.pack_into("<f", head, 0x2C, 1.0 / fps)
    out = bytes(head) + bytes(recb) + bytes(masks) + bytes(body)
    assert len(out) == pos, (len(out), pos)
    # the masks the runtime copies must cover what the new streams write (uc4enc.pool_masks: an unlisted row is skipped)
    gi = [(recs[g][3], recs[g][4]) for g in range(G)]
    want = uc4enc.pool_masks(gi, dict(enumerate(new_streams)))
    if want != bytes(masks[:len(want)]):
        raise ValueError("written masks of the re-encoded clip differ from chunk-0's")
    return out


def _cmp(emu, clip, frames):
    from uc4anim import ClipDecoder
    dec = ClipDecoder(clip, emu)
    bad = {}
    worst = 0.0
    for f in range(len(frames)):
        r = dec.eval_frame(f)
        for g, a in frames[f].items():
            b = r[g]
            na, nb = a != a, b != b
            if (na != nb).any():
                for row in sorted(set(int(x) for x in ((na != nb).nonzero()[0]))):
                    bad[(g, row)] = 9e9
                continue
            dif = abs(a - b)
            dif[na] = 0.0
            worst = max(worst, float(dif.max(initial=0.0)))
            for row, col in zip(*(dif > EPS).nonzero()):
                k = (g, int(row), "s" if col < 4 else "q" if col < 8 else "t")
                bad[k] = max(bad.get(k, 0.0), float(dif[row, col]))
    return bad, worst


def convert(emu, p, stm, name):
    """(full ClipData, info) of streamed ANIM `name` of pak p"""
    base, ca = _anim(p, name)
    flags = p.u32(base + 4)
    if not flags & 4:
        raise ValueError(f"{name}: not a streamed clip (flags {flags:#x})")
    total = struct.unpack_from("<H", p.d, ca + 0x22)[0]
    c0 = _clip(p, name + "-chunk-0")
    chunks = [c0] + stm_chunks(stm)
    fr = Frames(emu, chunks, total)
    G = struct.unpack_from("<H", c0, 0xC)[0]
    # start: every written component that changes over the clip; then add whatever the decode-back still misses (a chunk-0 constant that later moves)
    comps = {}
    for g in range(G):
        a0 = fr.frames[0][g]
        rows = set()
        for f in fr.frames:
            a = f[g]
            m = abs(a - a0) > 0.0
            m &= ~((a != a) | (a0 != a0))
            for row, col in zip(*m.nonzero()):
                rows.add((int(row), "s" if col < 4 else "q" if col < 8 else "t"))
        if rows:
            comps[g] = sorted(rows)
    for it in range(6):
        clip = encode(c0, fr.frames, comps)
        bad, worst = _cmp(emu, clip, fr.frames)
        if not bad:
            return clip, dict(frames=total, chunks=len(chunks), seam=max(fr.seams or [0.0]), flips=fr.flips, comps=sum(len(v) for v in comps.values()),
                              size=len(clip), worst=worst)
        for k in bad:
            if len(k) == 3:
                comps.setdefault(k[0], [])
                if (k[1], k[2]) not in comps[k[0]]:
                    comps[k[0]].append((k[1], k[2]))
                    comps[k[0]].sort()
            else:
                raise ValueError(f"{name}: group {k[0]} row {k[1]} written / unwritten differs after re-encode")
    raise ValueError(f"{name}: re-encode does not converge ({len(bad)} components off)")


def convert_clip(src, n):
    """(ClipData, info) of one clip with its own emulator (job of build)"""
    from emu import Emu
    return convert(Emu(), _load(src), game_file(f"animstream97/{PAK}.{n}.stm"), n)


def verify_clip(src, data, n):
    """the per-clip part of verify (job)"""
    from emu import Emu
    emu = Emu()
    p, q = _load(src), _load(data)
    base, ca = _anim(q, n)
    if q.u32(base + 4) & 4:
        return False
    stm = game_file(f"animstream97/{PAK}.{n}.stm")
    b0, c0 = _anim(p, n)
    total = struct.unpack_from("<H", p.d, c0 + 0x22)[0]
    clip = bytes(q.d[ca:ca + q.u32(ca + 8)])
    if struct.unpack_from("<H", clip, 0xE)[0] != total:
        return False
    fr = Frames(emu, [_clip(p, n + "-chunk-0")] + stm_chunks(stm), total)
    bad, worst = _cmp(emu, clip, fr.frames)
    return not bad


def build(src, clips=CLIPS, log=print):
    """src = the game's anim-melee-abby-t2.pak bytes -> (patched bytes, {name: info})"""
    p = _load(src)
    d = bytearray(src)
    u32 = lambda o: struct.unpack_from("<I", d, o)[0]                     # noqa: E731
    npg, pt, ft = u32(16), u32(20), u32(28)
    pages = [list(struct.unpack_from("<III", d, pt + 12 * i)) for i in range(npg)]
    host = max(i for i, (s, z, f) in enumerate(pages) if f == 0)         # the last data page (the one after it is the flag-1 page)
    hs, hz, _ = pages[host]
    built, info = [], {}
    import parjobs      # the clips are independent (own emulator each, ~1 min per clip): child interpreters (parjobs.py; T2R_PAR_JOBS=1 = serial)
    for n, (clip, inf) in zip(clips, parjobs.run([("unstream_anims", "convert_clip", (src, n), {}) for n in clips], log=lambda *_a: None)):
        built.append((n, clip))
        info[n] = inf
        log(f"unstream: {n}: {inf['frames']} frames from {inf['chunks']} chunks ({inf['flips']} seam quaternion signs aligned), {inf['comps']} raw components, "
            f"{inf['size']} bytes, decode-back max err {inf['worst']:.2g}")
    blob = bytearray()
    at = {}
    cur = _round16(hz)
    pad0 = cur - hz
    for n, c in built:
        at[n] = cur + len(blob)
        blob += c + bytes(_round16(len(c)) - len(c))
    grow = pad0 + len(blob)
    if hz + grow > MAX_PAGE:
        raise ValueError(f"page {host}: {hz:#x} + {grow:#x} bytes > {MAX_PAGE:#x} (too many clips for one page)")
    ins = hs + hz
    d[ins:ins] = bytes(pad0) + bytes(blob)
    pages[host][1] = hz + grow
    struct.pack_into("<I", d, hs + 0xC, hz + grow)                      # page header +0x0c = page size
    for i in range(host + 1, npg):
        pages[i][0] += grow
    for i, (s, z, f) in enumerate(pages):
        struct.pack_into("<III", d, pt + 12 * i, s, z, f)
    # repoint each ANIM +0x08 (page-relative offset; the fixup entry's dst page -> host) and clear the streamed bit
    fd, fc = u32(ft + 4), u32(ft + 8)
    fix = {}
    for i in range(fc):
        sp, dp, so = struct.unpack_from("<HHI", d, fd + 8 * i)
        fix[(sp, so)] = i
    for n, c in built:
        base, ca = _anim(p, n)
        sp = next(i for i, (s, z, f) in enumerate(p.pages) if s <= base + 8 < s + z)
        so = base + 8 - p.pages[sp][0]
        abs_slot = pages[sp][0] + so
        i = fix[(sp, so)]
        struct.pack_into("<HHI", d, fd + 8 * i, sp, host, so)
        struct.pack_into("<Q", d, abs_slot, at[n])
        fl = struct.unpack_from("<I", d, abs_slot - 8 + 4)[0]
        struct.pack_into("<I", d, abs_slot - 8 + 4, fl & ~4)
    # the marker (see MARKER): the first clip's -chunk-0 ANIM renamed in place (the name string is longer: NUL padded), its +0x38 sid and flags
    mk = clips[0] + "-chunk-0"
    it = [x for x in p.items if x[0] == mk and x[1] == "ANIM"][0]
    pg = it[2]
    na = p.pages[pg][0] + p.q(it[3])
    assert p.cstr(na) == mk and len(MARKER) <= len(mk)
    shift = sum(grow for i in [0] if pg > host)                       # (pages after the host moved back by grow)
    na2 = na + shift
    d[na2:na2 + len(mk)] = MARKER.encode() + bytes(len(mk) - len(MARKER))
    b2 = it[3] + 48 + shift
    struct.pack_into("<Q", d, b2 + 0x38, fnv(MARKER))
    struct.pack_into("<I", d, b2 + 4, struct.unpack_from("<I", d, b2 + 4)[0] & ~0x10)
    if MARKER2_CLIP in clips:               # ps33: the second marker, the same way
        mk2 = MARKER2_CLIP + "-chunk-0"
        it = [x for x in p.items if x[0] == mk2 and x[1] == "ANIM"][0]
        pg = it[2]
        na = p.pages[pg][0] + p.q(it[3])
        assert p.cstr(na) == mk2 and len(MARKER2) <= len(mk2)
        shift = grow if pg > host else 0
        d[na + shift:na + shift + len(mk2)] = MARKER2.encode() + bytes(len(mk2) - len(MARKER2))
        b2 = it[3] + 48 + shift
        struct.pack_into("<Q", d, b2 + 0x38, fnv(MARKER2))
        struct.pack_into("<I", d, b2 + 4, struct.unpack_from("<I", d, b2 + 4)[0] & ~0x10)
    log(f"unstream: {len(built)} clips resident in {PAK} page {host} ({hz:#x} -> {hz + grow:#x} bytes, pak +{grow} bytes); marker ANIM {MARKER} (was {mk}){', ' + MARKER2 if MARKER2_CLIP in clips else ''}")
    return bytes(d), info


def verify(data, src, clips=CLIPS):
    """the converted ANIMs are resident (flags without the streamed bit, ClipData = the full frame count) and decode back to the source frames;
    every other ANIM's ClipData bytes, flags and raw channel pointer are unchanged"""
    p, q = _load(src), _load(data)
    import parjobs
    if not all(parjobs.run([("unstream_anims", "verify_clip", (src, data, n), {}) for n in clips])):
        return False
    mk = [x for x in q.items if x[0] == MARKER and x[1] == "ANIM"]
    if len(mk) != 1 or q.q(mk[0][3] + 48 + 0x38) != fnv(MARKER) or q.u32(mk[0][3] + 48 + 4) & 0x14:
        return False
    if MARKER2_CLIP in clips:
        mk2 = [x for x in q.items if x[0] == MARKER2 and x[1] == "ANIM"]
        if len(mk2) != 1 or q.q(mk2[0][3] + 48 + 0x38) != fnv(MARKER2) or q.u32(mk2[0][3] + 48 + 4) & 0x14:
            return False
    names = set(clips) | {clips[0] + "-chunk-0"} | ({MARKER2_CLIP + "-chunk-0"} if MARKER2_CLIP in clips else set())
    for (n, t, pi, io) in p.items:
        if t != "ANIM" or n in names:
            continue
        b, ca = _anim(p, n)
        b2, ca2 = _anim(q, n)
        if p.u32(b + 4) != q.u32(b2 + 4) or _clip(p, n) != _clip(q, n) or bool(p.ptr(b + 0x10)) != bool(q.ptr(b2 + 0x10)):
            return False
        if p.ptr(b + 0x28) and p.d[p.ptr(b + 0x28):p.ptr(b + 0x28) + 0x18] != q.d[q.ptr(b2 + 0x28):q.ptr(b2 + 0x28) + 0x18]:
            return False
    return True


if __name__ == "__main__":
    sys.path.insert(0, os.path.join(ROOT, "tools", "features"))
    src = game_file(f"actor97/{PAK}.pak")
    out, info = build(src)
    ok = verify(out, src)
    print("verify:", "ok" if ok else "FAILED")
    if len(sys.argv) > 1:
        open(sys.argv[1], "wb").write(out)
        print("wrote", sys.argv[1], len(out))
    sys.exit(0 if ok else 1)
