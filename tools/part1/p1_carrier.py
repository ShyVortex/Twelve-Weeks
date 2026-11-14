"""The carrier anim pak for the Part I Shorty / El Diablo clips (T2R_P1_GUNS): the game's SP-only workbench pak
actor97/anim-ellie-workbench-shared-pistol.pak (17 ellie-skel clips + 12 pistol-base clips, none played in MP) with our
baked clips in place of its clips, listed in the MP level like the UC4 downed carriers.  re/part1/weapons.md section 9.

Layout rules (all in place, the pages keep their size and order):
  * clip bodies: every ellie-skel / pistol-base ClipData body of the pak is freed into a pool (adjacent bodies merge;
    ClipData bodies are plain blobs only an ANIM +0x08 points at - checked here, as for the UC4 carriers); our clips are
    packed into it (largest first, 16-aligned) and each carrier ANIM +0x08 is repointed (its fixup's dst page too).
    Carriers we do not use point at one of our clips of the same rig (still a valid clip).  Carrier raw channels are
    frozen (frame count 1: the workbench root motion must not move the player) and the loop bit cleared; -add carriers
    get the additive flag (ANIM +4 bit 1, as TLOU2's own -add clips: 0xa).
  * anim events: TLOU2 reloads carry events the gameplay needs (weapon-reload = the ammo refill frame, abort-out /
    abort-idle-* = where the reload may be cut, blend-in, weapon-event hide / show-magazine, weapon-effect / gear-effect
    sounds, haptics).  Each -part carrier gets a new effect table with the events p1_wire.events() gives it (the Part I
    clip's own events + TLOU2's state events).  Table layout (as read from TLOU2's own reload clips): {u64 clip sid,
    ptr events, u64 count}, events of 24 bytes {u64 type sid, f32 frame, u32 value count, ptr values}, values of 16
    bytes {u64 key sid, u64 value}.  Tables go into the pool too; their pointers get NEW fixup entries (the fixup
    table grows by 8 bytes per entry, the pages move back as a whole, nothing inside a page moves).  Every other ANIM
    of the pak keeps its effect table with 0 events (the workbench foley must not fire).
Library only (p1_wire.carrier_pak builds and checks it)."""
import os
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.dirname(HERE)
ROOT = os.path.dirname(TOOLS)
MAIN = ROOT.split(os.sep + ".claude" + os.sep)[0]
sys.path[:0] = [HERE, os.path.join(TOOLS, "models"), TOOLS]
import ndpak  # noqa: E402

CARRIER_PAK = "anim-ellie-workbench-shared-pistol"
ELLIE_SIG, GUN_SIG = 0x5abe1b4c, 0x29e20d42
PAGE_HEADER = 20
FX = 0x28              # ANIM data + 0x28 (= item + 0x58, build_dll._strip_effects): effect table pointer


def fnv(s):
    h = 0xCBF29CE484222325
    for c in s.encode():
        h = ((h ^ c) * 0x100000001B3) & (2 ** 64 - 1)
    return h


def game_pak(name):
    """actor97/<name>.pak of TLOU2 (cached in re/gamebin/actor97 of this or the main checkout, else read from the
    install via dsar_list, read-only)"""
    for base in (ROOT, MAIN):
        p = os.path.join(base, "re", "gamebin", "actor97", name + ".pak")
        if os.path.exists(p):
            return open(p, "rb").read()
    import dsar_list
    game = os.environ.get("T2_GAME", "C:/Games/The Last of Us Part II Remastered")
    d, ent, bs, bsz = dsar_list.open_files(os.path.join(game, "build", "pc", "main", "sp-common.psarc"))
    data = dsar_list.extract(d, ent, bs, bsz, "actor97/" + name + ".pak")
    dst = os.path.join(MAIN, "re", "gamebin", "actor97", name + ".pak")
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    open(dst, "wb").write(data)
    return data


def load(data):
    import tempfile
    fd, path = tempfile.mkstemp(suffix=".pak")
    os.close(fd)
    try:
        open(path, "wb").write(data)
        return ndpak.Pak(path)
    finally:
        os.remove(path)


class PakEdit:
    """TLOU2 pak (0xA79) with editable pointer fixups: {u16 src page, u16 dst page, u32 src offset} entries; a pointer's
    value = offset from its dst page's start (incl. the 20-byte page header).  save() rewrites the fixup table (grown
    for new entries) and moves the pages back by the growth; page contents are edited in place."""

    def __init__(self, data):
        self.d = bytearray(data)
        u32 = lambda o: struct.unpack_from("<I", self.d, o)[0]   # noqa: E731
        self.hdr_size, self.npages, self.page_table, self.fix_table = u32(4), u32(16), u32(20), u32(28)
        self.pages = [list(struct.unpack_from("<III", self.d, self.page_table + 12 * i)) for i in range(self.npages)]
        fd, fc = u32(self.fix_table + 4), u32(self.fix_table + 8)
        assert fd + 8 * fc == self.hdr_size and 0 <= self.pages[0][0] - self.hdr_size < 16, "fixups must end where the first page starts (up to 16-alignment padding)"
        self.fix = [list(struct.unpack_from("<HHI", self.d, fd + 8 * i)) for i in range(fc)]
        self.by_addr = {self.pages[sp][0] + so: i for i, (sp, dp, so) in enumerate(self.fix)}
        self.n0 = fc

    def page_of(self, a):
        for i, (s, z, _) in enumerate(self.pages):
            if s <= a < s + z:
                return i
        raise ValueError(hex(a))

    def ptr(self, a):
        i = self.by_addr.get(a)
        if i is None:
            return None
        return self.pages[self.fix[i][1]][0] + struct.unpack_from("<Q", self.d, a)[0]

    def set_ptr(self, a, target):
        """pointer slot a -> absolute file offset target (adds a fixup when the slot had none)"""
        tp = self.page_of(target)
        struct.pack_into("<Q", self.d, a, target - self.pages[tp][0])
        i = self.by_addr.get(a)
        if i is None:
            sp = self.page_of(a)
            self.fix.append([sp, tp, a - self.pages[sp][0]])
            self.by_addr[a] = len(self.fix) - 1
        else:
            self.fix[i][1] = tp

    def save(self):
        n = len(self.fix)
        grow = 8 * (n - self.n0)
        grow += (-grow) % 16                      # pages stay 16-aligned in the file (padding after the entries)
        d = self.d
        fd = struct.unpack_from("<I", d, self.fix_table + 4)[0]
        head = bytearray(d[:fd])
        struct.pack_into("<I", head, 4, self.hdr_size + grow)
        struct.pack_into("<I", head, self.fix_table + 8, n)
        for i, (s, z, t) in enumerate(self.pages):
            struct.pack_into("<I", head, self.page_table + 12 * i, s + grow)
        ent = b"".join(struct.pack("<HHI", *e) for e in self.fix)
        body = bytes(head) + ent
        body += bytes(self.hdr_size + grow - len(body))
        return body + bytes(d[self.hdr_size:])


def anims(p):
    """{name: (ANIM data address, ClipData address, ClipData size, sig)} of an ndpak.Pak"""
    out = {}
    for name, typ, pi, io in p.items:
        if typ != "ANIM":
            continue
        base = io + 48
        if base + 8 not in p.fix:
            continue
        ca = p.pages[p.fix[base + 8]][0] + p.q(base + 8)
        out[name] = (base, ca, p.u32(ca + 8), p.u32(ca + 4))
    return out


def ref_events(pak_bytes, clip):
    """the effect table of a TLOU2 clip: (frames of the clip, [(type sid, frame, [(key sid, value)])])"""
    p = load(pak_bytes)
    a = anims(p)[clip]
    base = a[0]
    t = p.ptr(base + FX) if (base + FX) in p.fix else None
    frames = struct.unpack_from("<H", p.d, a[1] + 0xe)[0]
    if not t:
        return frames, []
    cnt = p.u32(t + 0x10)
    ev = p.ptr(t + 8)
    out = []
    for i in range(cnt):
        e = ev + 24 * i
        sid, fr, npairs = struct.unpack_from("<QfI", p.d, e)
        pl = p.ptr(e + 16) if (e + 16) in p.fix else 0
        pairs = []
        for k in range(npairs):
            assert (pl + 16 * k + 8) not in p.fix, f"{clip}: event {i} value {k} is a pointer (not supported)"
            pairs.append(struct.unpack_from("<QQ", p.d, pl + 16 * k))
        out.append((sid, fr, pairs))
    return frames, out


def event_table(clip_sid, events):
    """blob of a new effect table (events = [(type sid, frame, [(key sid, value)])], frames of OUR clip) + its internal
    pointer slots [(slot offset, target offset)] (offsets in the blob)"""
    keep = sorted(events, key=lambda e: e[1])
    k = 1.0
    n = len(keep)
    head = 0x18
    pay = head + 24 * n
    blob = bytearray(pay + 16 * sum(len(pr) for _, _, pr in keep) + 16)
    slots = [(8, head)]
    struct.pack_into("<QQQ", blob, 0, clip_sid, 0, n)
    at = pay
    for i, (sid, fr, pairs) in enumerate(keep):
        e = head + 24 * i
        struct.pack_into("<QfI", blob, e, sid, round(fr * k, 3), len(pairs))
        slots.append((e + 16, at))                 # (an event without values points at the next free spot, as stock)
        for key, val in pairs:
            struct.pack_into("<QQ", blob, at, key, val)
            at += 16
    return bytes(blob), slots, len(keep)


def build(jobs, log=print, pak=None, use_gun=True, gun_sig=None, body_sig=None, keep_raw=False, src_bytes=None, exclude=()):
    """jobs: [(carrier key, clip bytes, kind 'part' / 'add' / 'gun', anim events for the clip or None)] with carrier
    key = our clip id; returns (pak bytes, {our clip id: carrier name})"""
    CARRIER = pak or CARRIER_PAK
    GSIG = gun_sig or GUN_SIG
    BSIG = body_sig or ELLIE_SIG     # (body_sig: another body rig's carriers, e.g. the NPC pak anim-npc-m-lg; keep_raw: leave their raw channels as they are)
    src = src_bytes or game_pak(CARRIER)       # (src_bytes: the pak as an earlier step left it, e.g. the 2013 execution clips in anim-npc-m-lg; exclude = carrier names that step owns)
    p = load(src)
    pe = PakEdit(src)
    a = anims(p)
    ellie = sorted((n for n, v in a.items() if v[3] == BSIG and n not in exclude), key=lambda n: -a[n][2])
    gun = sorted((n for n, v in a.items() if v[3] == GSIG and n not in exclude), key=lambda n: -a[n][2]) if use_gun else []
    # unique clips (identical bakes share one carrier)
    uniq, of = [], {}
    for key, clip, kind, ref in jobs:
        for u, (c2, k2, r2, keys) in enumerate(uniq):
            if c2 == clip and k2 == kind and repr(r2) == repr(ref):
                keys.append(key)
                of[key] = u
                break
        else:
            of[key] = len(uniq)
            uniq.append((clip, kind, ref, [key]))
    need_e = [u for u, (c, k, r, _) in enumerate(uniq) if struct.unpack_from("<I", c, 4)[0] == BSIG]
    need_g = [u for u, (c, k, r, _) in enumerate(uniq) if struct.unpack_from("<I", c, 4)[0] == GSIG]
    assert len(need_e) + len(need_g) == len(uniq), "a baked clip of another rig"
    if len(need_e) > len(ellie) or len(need_g) > len(gun):
        raise SystemExit(f"carrier pak {CARRIER}: {len(need_e)} body / {len(need_g)} gun clips, "
                         f"only {len(ellie)} / {len(gun)} carriers")
    carrier = {}
    for lst, need in ((ellie, need_e), (gun, need_g)):
        for u, name in zip(need, lst):
            carrier[u] = name
    # pool: every ellie / gun body; nothing else may point into one (checked)
    bodies = sorted((a[n][1], a[n][1] + a[n][2]) for n in ellie + gun)
    targets = {}
    for addr, i in pe.by_addr.items():
        t = pe.ptr(addr)
        targets.setdefault(t, []).append(addr)
    clip_slots = {a[n][0] + 8 for n in ellie + gun}
    for lo, hi in bodies:
        for t, srcs in targets.items():
            if lo <= t < hi:
                assert t == lo and all(s in clip_slots for s in srcs), f"pointer into a ClipData body at {t:#x}"
    free = []
    for lo, hi in bodies:
        if free and free[-1][1] == lo and pe.page_of(lo) == pe.page_of(free[-1][0]):
            free[-1][1] = hi
        else:
            free.append([lo, hi])
    pool_total = sum(h - l for l, h in free)
    for lo, hi in free:
        pe.d[lo:hi] = bytes(hi - lo)

    def alloc(size):
        size16 = (size + 15) & ~15
        best = None
        for iv in free:
            s = iv[0] + ((-(iv[0] - pe.pages[pe.page_of(iv[0])][0])) % 16)
            if s + size16 <= iv[1] and (best is None or iv[1] - iv[0] < best[1] - best[0]):
                best = iv
        if best is None:
            raise SystemExit(f"carrier pool full ({size} bytes needed; free {[h - l for l, h in free]})")
        s = best[0] + ((-(best[0] - pe.pages[pe.page_of(best[0])][0])) % 16)
        best[0] = s + size16
        return s

    placed = {}
    for u in sorted(range(len(uniq)), key=lambda u: -len(uniq[u][0])):
        clip = uniq[u][0]
        at = alloc(len(clip))
        pe.d[at:at + len(clip)] = clip
        placed[u] = at
    # carrier ANIMs: clip pointer, flags, raw channels; unused carriers -> one of our clips of the same rig
    used_e = [placed[u] for u in need_e] or [None]
    used_g = [placed[u] for u in need_g] or [None]
    ev_total = 0
    for name in ellie + gun:
        base = a[name][0]
        u = next((u for u, n in carrier.items() if n == name), None)
        if u is None:
            at = used_e[0] if name in ellie else used_g[0]
            if at is None:
                continue
            pe.set_ptr(base + 8, at)
            continue
        clip, kind, ref, keys = uniq[u]
        gun_clip = struct.unpack_from("<I", clip, 4)[0] == GSIG
        pe.set_ptr(base + 8, placed[u])
        f = struct.unpack_from("<I", pe.d, base + 4)[0] & ~1           # one-shot
        f = (f | 2) if kind == "add" else (f & ~2)
        struct.pack_into("<I", pe.d, base + 4, f)
        if (base + 0x10) in pe.by_addr and not keep_raw:               # freeze the raw channels (root motion)
            rc = pe.ptr(base + 0x10)
            n = struct.unpack_from("<I", pe.d, rc)[0]
            cp = pe.ptr(rc + 0x10)
            # body carriers: one frame (the workbench root motion must not move the player).  GUN carriers: the real clip's own
            # layout (NPC / player gun clips: one raw channel with as many frames as the clip) - frozen to 1 frame the clip may play
            # as a single frame (the Frontier's baked lever gun clip never moved the lever joint)
            frames = struct.unpack_from("<H", pe.d, placed[u] + 0xe)[0] if gun_clip else 1
            for j in range(n):
                struct.pack_into("<H", pe.d, pe.ptr(cp + 8 * j), frames)
        if ref:
            blob, slots, nk = event_table(fnv(name), ref)
            at = alloc(len(blob))
            pe.d[at:at + len(blob)] = blob
            for so, to in slots:
                pe.set_ptr(at + so, at + to)
            pe.set_ptr(base + FX, at)
            ev_total += nk
    # every other effect table of the pak: 0 events
    for name, (base, ca, size, sig) in a.items():
        if name in carrier.values() and any(uniq[u][2] for u, n in carrier.items() if n == name):
            continue
        if (base + FX) in pe.by_addr:
            t = pe.ptr(base + FX)
            if t:
                struct.pack_into("<I", pe.d, t + 0x10, 0)
    out = pe.save()
    used = sum(len(c) for c, _, _, _ in uniq)
    log(f"anim: carrier pak {CARRIER}: {len(uniq)} clips ({len(need_e)} body, {len(need_g)} gun) in a "
        f"{pool_total} byte pool ({used} used), {ev_total} anim events on the -part carriers, "
        f"{len(pe.fix) - pe.n0} new fixups, {len(out)} bytes")
    names = {key: carrier[of[key]] for key, _, _, _ in jobs}
    return out, names


def check(data, expect=None, log=print):
    """every ANIM of the pak resolves; the carriers of `expect` {carrier name: clip bytes} hold exactly those bytes"""
    p = load(data)
    a = anims(p)
    for name, (base, ca, size, sig) in a.items():
        assert struct.unpack_from("<I", p.d, ca)[0] == 0x41430102, f"{name}: no ClipData"
    for name, clip in (expect or {}).items():
        base, ca, size, sig = a[name]
        assert bytes(p.d[ca:ca + len(clip)]) == clip, f"{name}: carrier does not hold its clip"
    log(f"anim: carrier pak check: {len(a)} clips resolve, {len(expect or {})} carriers hold our clips")
    return True


if __name__ == "__main__":
    print(__doc__)
