"""Sony BNK (TLOU2 soundbank4/*.bnk, ATRAC9 waves) - replace waves in place.

A shot sound is an event in the bank (e.g. sfx-rifle-mpx5-player-suppressed) whose layers pick
waves at random. Giving a gun another gun's sound by pointing at the other event breaks full-auto
fire (the other event's instance rules: only every other shot played), so instead the WAVES inside
the gun's own bank are replaced: each target wave's RIFF slot gets the source wave, truncated to
whole ATRAC9 blocks if longer (the tail end of a long bloom is lost) and zero-padded if shorter.
Channel counts must match (the bank table keeps its own stream info)."""
import re
import struct


def riff_slots(bank: bytes):
    """{wave file name: (offset, slot size)} for the RIFF-wrapped waves of a bank."""
    out = {}
    for m in re.finditer(b"RIFF", bank):
        i = m.start()
        names = re.findall(rb"[ -~]{4,}\.wav", bank[i - 0x100:i])
        if names:
            out[names[-1].decode()] = (i, struct.unpack_from("<I", bank, i + 4)[0] + 8)
    return out


def _chunks(blob):
    j, out = 12, {}
    while j + 8 <= len(blob):
        cid, cl = blob[j:j + 4], struct.unpack_from("<I", blob, j + 4)[0]
        out[cid] = (j, cl)
        if cid == b"data":
            break
        j += 8 + cl
    return out


def fit(blob: bytes, size: int) -> bytes:
    """RIFF/ATRAC9 wave cut to at most `size` bytes (whole blocks), sample count fixed up."""
    c = _chunks(blob)
    fo, _ = c[b"fmt "]
    channels = struct.unpack_from("<H", blob, fo + 8 + 2)[0]
    align = struct.unpack_from("<H", blob, fo + 8 + 12)[0]
    spb = struct.unpack_from("<H", blob, fo + 8 + 18)[0]          # samples per block
    do, dl = c[b"data"]
    head = do + 8
    blocks = min(dl // align, max(0, (size - head) // align))
    data = blob[head:head + blocks * align]
    out = bytearray(blob[:head]) + data
    struct.pack_into("<I", out, do + 4, len(data))
    struct.pack_into("<I", out, 4, len(out) - 8)
    if b"fact" in c:
        xo, _ = c[b"fact"]
        total, delay = struct.unpack_from("<II", blob, xo + 8)
        struct.pack_into("<I", out, xo + 8, min(total, max(0, blocks * spb - delay)))
    # shorter than the slot: the RIFF / data sizes still span the whole slot (the bank table and
    # readers expect that), zero-padded; the fact sample count ends playback at the real end
    pad = size - len(out)
    if pad > 0:
        out += bytes(pad)
        struct.pack_into("<I", out, do + 4, len(data) + pad)
        struct.pack_into("<I", out, 4, len(out) - 8)
    return bytes(out), channels


def channels(blob):
    fo, _ = _chunks(blob)[b"fmt "]
    return struct.unpack_from("<H", blob, fo + 8 + 2)[0]


def replace_waves(target: bytes, source: bytes, mapping: dict) -> bytes:
    """mapping: target wave name -> source wave name."""
    t, s = riff_slots(target), riff_slots(source)
    out = bytearray(target)
    for tn, sn in mapping.items():
        to, tl = t[tn]
        so, sl = s[sn]
        src = source[so:so + sl]
        assert channels(src) == channels(target[to:to + tl]), f"{sn} -> {tn}: channel count differs"
        new, _ = fit(src, tl)
        out[to:to + tl] = new
    return bytes(out)


def _layer(f):
    """'<bank>_<wave>.wav' (vgmstream export) -> '<wave>.wav'; plain '<wave>.wav' as is."""
    import os
    n = os.path.basename(f)
    return n.split("_", 1)[1] if "_" in n else n


def wav_pcm(path):
    d = open(path, "rb").read()
    i = d.find(b"data")
    return d[i + 8:i + 8 + struct.unpack_from("<I", d, i + 4)[0]]


def replace_pcm(target: bytes, wav_dir: str, mapping: dict, src_dir: str = None) -> bytes:
    """Some layers (thumps, LFE) are raw 16-bit PCM in the bank, without a RIFF header. They are
    located by their decoded audio (wav_dir = vgmstream export of the target bank, file names
    '<bank>_<wave>.wav'); each target's PCM gets the source's, cut to the target length with a
    3 ms fade-out (or zero-padded)."""
    import glob, os
    files = {_layer(f): f for f in glob.glob(os.path.join(wav_dir, "*.wav"))}
    srcs = {_layer(f): f for f in glob.glob(os.path.join(src_dir or wav_dir, "*.wav"))}
    out = bytearray(target)
    for tn, sn in mapping.items():
        tp, sp = wav_pcm(files[tn]), wav_pcm(srcs[sn])
        at = target.find(tp[200:264])
        assert at >= 200 and target[at - 200:at - 200 + len(tp)] == tp, f"{tn}: PCM not found in the bank"
        at -= 200
        new = bytearray(sp[:len(tp)]) + bytes(max(0, len(tp) - len(sp)))
        fade = min(144, len(new) // 2)                       # 3 ms at 48 kHz, mono 16-bit
        for k in range(fade):
            o = len(new) - 2 * fade + 2 * k
            v = struct.unpack_from("<h", new, o)[0]
            struct.pack_into("<h", new, o, int(v * (fade - k) / fade))
        out[at:at + len(tp)] = new
    return bytes(out)


def mix_pcm(target: bytes, wav_dir: str, mapping: dict, src_dir: str, gain: float = 1.0) -> bytes:
    """Raw 16-bit PCM layers: target layer = target + source * gain (source mono is spread to
    the target's channel count), clipped, length kept, 3 ms fade-out at the end."""
    import glob, os
    files = {_layer(f): f for f in glob.glob(os.path.join(wav_dir, "*.wav"))}
    srcs = {_layer(f): f for f in glob.glob(os.path.join(src_dir, "*.wav"))}
    out = bytearray(target)
    for tn, sn in mapping.items():
        tw = open(files[tn], "rb").read()
        sw = open(srcs[sn], "rb").read()
        tch = struct.unpack_from("<H", tw, 22)[0]
        sch = struct.unpack_from("<H", sw, 22)[0]
        tp, sp = wav_pcm(files[tn]), wav_pcm(srcs[sn])
        at = target.find(tp[200:264])
        assert at >= 200 and target[at - 200:at - 200 + len(tp)] == tp, f"{tn}: PCM not found in the bank"
        at -= 200
        n = len(tp) // 2
        t = list(struct.unpack(f"<{n}h", tp))
        s = struct.unpack(f"<{len(sp) // 2}h", sp)
        frames = n // tch
        for f in range(frames):
            for c in range(tch):
                si = f * sch + (c % sch)
                v = t[f * tch + c] + (s[si] * gain if si < len(s) else 0)
                t[f * tch + c] = max(-32768, min(32767, int(v)))
        fade = min(144, frames // 2)
        for k in range(fade):
            f = frames - fade + k
            for c in range(tch):
                t[f * tch + c] = int(t[f * tch + c] * (fade - k) / fade)
        out[at:at + len(tp)] = struct.pack(f"<{n}h", *t)
    return bytes(out)


# ATRAC9 frames that decode to digital silence (vgmstream/libatrac9: all-zero PCM), by block
# align = the most common 128-byte (stereo) / 64-byte (mono) block in the game's weapon banks
# (the silent ends of their waves) - real encoder output, not hand-made bitstreams.
SILENT_ATRAC9 = {
    128: bytes.fromhex("0028f001440000006739ce739cf7bde8" * 2) + b"\x01" * 96,
    64: bytes.fromhex("2c2ef37fe400000000000006739ce739cf7bdef7bde936d26da4db4f1e3c78f1d4751d4750") + b"\x01" * 27,
}


def silence_waves(target: bytes, names) -> bytes:
    """Replace RIFF/ATRAC9 waves with silence in place: every block of the data chunk becomes a
    silent ATRAC9 frame (SILENT_ATRAC9); header, fact (length) and slot size stay, so the bank
    table and the event's timing are untouched - the layer plays, but plays nothing."""
    t = riff_slots(target)
    out = bytearray(target)
    for n in names:
        o, l = t[n]
        blob = target[o:o + l]
        c = _chunks(blob)
        fo, _ = c[b"fmt "]
        align = struct.unpack_from("<H", blob, fo + 8 + 12)[0]
        silent = SILENT_ATRAC9[align]
        do, dl = c[b"data"]
        dl = min(dl, l - do - 8)
        k = dl // align
        out[o + do + 8:o + do + 8 + k * align] = silent * k
    return bytes(out)


def mute_waves(target: bytes, names) -> bytes:
    """Silence RIFF/ATRAC9 waves in place: their fact chunk's sample count -> 0 (playback ends at
    once); the data stays, so sizes and the bank table are untouched."""
    t = riff_slots(target)
    out = bytearray(target)
    for n in names:
        o, l = t[n]
        c = _chunks(target[o:o + l])
        if b"fact" in c:
            xo, _ = c[b"fact"]
            struct.pack_into("<I", out, o + xo + 8, 0)
    return bytes(out)


def mix_wav_mono(a_path: str, a_gain: float, b_path: str, b_gain: float, out_path: str):
    """16-bit wav files -> one mono 48 kHz wav: a * a_gain + b * b_gain (first channel of each,
    same sample rate expected), length of the longer one, clipped."""
    def read(p):
        d = open(p, "rb").read()
        ch, sr = struct.unpack_from("<HI", d, 22)
        s = wav_pcm(p)
        v = struct.unpack(f"<{len(s) // 2}h", s)
        return v[::ch], sr
    a, sra = read(a_path)
    b, srb = read(b_path)
    assert sra == srb == 48000, (sra, srb)
    n = max(len(a), len(b))
    mix = [max(-32768, min(32767, int((a[i] * a_gain if i < len(a) else 0) + (b[i] * b_gain if i < len(b) else 0)))) for i in range(n)]
    pcm = struct.pack(f"<{n}h", *mix)
    hdr = b"RIFF" + struct.pack("<I", 36 + len(pcm)) + b"WAVEfmt " + struct.pack("<IHHIIHH", 16, 1, 1, 48000, 96000, 2, 16)
    open(out_path, "wb").write(hdr + b"data" + struct.pack("<I", len(pcm)) + pcm)


# ---- the bank's cue table (root cause of the silent carrier bank) -------------------------------------------------------------------
# The cues (event name hash -> node) sit in a COALESCED HASH TABLE of N 16-byte slots {u64 fnv64(name), u16 bucket, u16 next slot (0xffff = end), u32 cue
# index c}.  A lookup starts at slot hash % N and follows `next` until the hash matches.  Every slot's `bucket` is its hash % N (checked on all 49 weapon
# banks of the game).  Layout as the game's tool writes it: the entry of each bucket with the lowest c sits in slot = bucket, the other entries
# ("overflow") fill the slots no bucket head uses, ascending slots <- ascending c, and a bucket's chain runs head -> next-lowest c -> ...  So rewriting
# a cue's hash in place (what retarget_cue used to do) leaves the entry in the chain of the OLD hash: the lookup of the new name starts in another slot
# and never finds it - the carrier bank's event was silent in game.  rebuild_cue_table() re-lays the table for the new hash.
CUE_REC = "<QHHI"


def cue_table(bank: bytes, h: int):
    """(start offset, N) of the cue table that holds the cue hash h; the table's invariants are checked (bucket == hash % N, every entry reachable from
    its home slot, cue indices unique and < N)"""
    pat = struct.pack("<Q", h)
    i = bank.find(pat)
    if i < 0:
        raise ValueError("cue hash not in the bank")
    bucket = struct.unpack_from("<H", bank, i + 8)[0]
    for n in range(2, 160):
        if h % n != bucket:                      # (the cue's own record names the bucket it was laid out for)
            continue
        for k in range(n):
            st = i - 16 * k
            if st < 0 or st + 16 * n > len(bank):
                continue
            es = [struct.unpack_from(CUE_REC, bank, st + 16 * j) for j in range(n)]
            if any(e[0] % n != e[1] for e in es) or sorted(e[3] for e in es) != list(range(n)):
                continue
            if all(e[2] == 0xffff or e[2] < n for e in es) and _reachable(es, n):
                return st, n
    raise ValueError("cue table layout not recognised")


def _reachable(es, n):
    for e in es:
        s, seen = e[0] % n, 0
        while es[s][0] != e[0]:
            s = es[s][2]
            seen += 1
            if s == 0xffff or seen > n:
                return False
    return True


def layout_cues(entries, n):
    """slots for [(hash, cue index)]: heads at their bucket (lowest cue index of the bucket), overflow into the free slots by ascending cue index"""
    byb = {}
    for h, c in sorted(entries, key=lambda e: e[1]):
        byb.setdefault(h % n, []).append((h, c))
    slot = [None] * n
    nxt = [0xffff] * n
    for b, lst in byb.items():
        slot[b] = lst[0]
    free = [s for s in range(n) if slot[s] is None]
    over = sorted((e for lst in byb.values() for e in lst[1:]), key=lambda e: e[1])
    place = {}
    for e, s in zip(over, free):
        slot[s] = e
        place[e] = s
    for b, lst in byb.items():
        prev = b
        for e in lst[1:]:
            nxt[prev] = place[e]
            prev = place[e]
    return [(slot[s][0], s_bucket(slot[s][0], n), nxt[s], slot[s][1]) for s in range(n) if slot[s] is not None]


def s_bucket(h, n):
    return h % n


def rebuild_cue_table(bank: bytes, old_h: int, new_h: int) -> bytes:
    """`bank` with the cue hash old_h replaced by new_h and the cue table laid out again, so the lookup of new_h works (same length)"""
    st, n = cue_table(bank, old_h)
    es = [struct.unpack_from(CUE_REC, bank, st + 16 * j) for j in range(n)]
    ent = [((new_h if e[0] == old_h else e[0]), e[3]) for e in es]
    out = bytearray(bank)
    for j, e in enumerate(layout_cues(ent, n)):
        struct.pack_into(CUE_REC, out, st + 16 * j, *e)
    return bytes(out)


def cue_lookup(bank: bytes, h: int):
    """the cue index the engine's lookup finds for hash h (None = silent): start slot hash % N, follow `next`"""
    st, n = cue_table(bank, h) if bank.find(struct.pack("<Q", h)) >= 0 else (None, None)
    if st is None:
        return None
    return cue_lookup_in(bank, st, n, h)


def cue_lookup_in(bank: bytes, st: int, n: int, h: int):
    s, seen = h % n, 0
    while s != 0xffff and seen <= n:
        e = struct.unpack_from(CUE_REC, bank, st + 16 * s)
        if e[0] == h:
            return e[3]
        s, seen = e[2], seen + 1
    return None


def retarget_cue(bank: bytes, old_name: str, new_name: str, donor: bytes) -> bytes:
    """A copy of `bank` that serves cue `new_name` instead of `old_name`: the cue table's fnv64 hash (found exactly once) is replaced AND the table is
    laid out again for it (rebuild_cue_table: the hash decides the slot the lookup starts in), the name string in the node records, when it fits,
    follows, and the header guid + bank name (0x30..0x60) are the donor bank's, so the copy can ship as the donor's own bank file (a set that is
    loaded in the level but whose cues nothing uses).  Same length."""
    def fnv(s):
        h = 0xcbf29ce484222325
        for c in s.encode():
            h = ((h ^ c) * 0x100000001b3) & (2 ** 64 - 1)
        return h
    a, b = struct.pack("<Q", fnv(old_name)), struct.pack("<Q", fnv(new_name))
    assert bank.count(a) == 1 and b not in bank, f"cue {old_name}: hash occurrences {bank.count(a)}"
    out = bytearray(rebuild_cue_table(bank, fnv(old_name), fnv(new_name)))
    for m in re.finditer(re.escape(old_name.encode()) + b"\0", bytes(out)):
        i = m.start()
        room = 0
        while i + len(old_name) + room < len(out) and out[i + len(old_name) + room] == 0 and room < 0x40:
            room += 1
        if len(new_name) <= len(old_name) + room - 1:
            out[i:i + len(new_name) + 1] = new_name.encode() + b"\0"
            out[i + len(new_name) + 1:i + len(old_name) + room] = bytes(len(old_name) + room - len(new_name) - 1)
    out[0x30:0x60] = donor[0x30:0x60]
    assert cue_lookup(bytes(out), fnv(new_name)) is not None, f"cue {new_name} not found by the hash lookup after the retarget"
    return bytes(out)
