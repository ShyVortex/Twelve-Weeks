"""Looping fire sound for the Bookstore fire barrels.

The donor can fire of t2r-nor-scar-burial-parking-lot has no sound in its own paks.  Its loop is a REGION_TREE sound emitter of the NR Forest audio
level t2r-assault-forest-layout-0-audio (-ingame pak, world-rogue.psarc): region emt-nor-parking-garage-fire-2-lp-cc-1 at 17.17 5.04 37.57 (0.4 m
above the can), a 20 m sphere with an SfxProcess aux block, sound sfx-amb-emt-nor-parking-garage-fire-1-lp-cc (0xddd5015fa757cece), cue in the
bank soundbank4/lvl-nor-forest-amb.bnk (sp-common.psarc).  Nothing of it is Part I data: the region bytes are copied from the TLOU2 donor.

What this builds (one small level, <key>-fire-sfx, only the Bookstore loads it and its bank):
  pak68/t2r-<key>-fire-sfx-ingame.pak   a REGION_TREE (+ the stock ingame items, p1_rsenv.make_ingame_pak) with one copy of the donor region per fire:
                                        the record + body + aux + tag dictionary bytes verbatim (416 bytes, 12 pointer slots, all internal), only the
                                        body position (xyz at body+0x20) moved by [fire pos + (donor region - donor can anchor)] and the last name
                                        character changed (-1, -2 ...: one region name per fire, sid +8 / +0x28 recomputed)
  registry block                        level-name / level-id / package <lv>-ingame / sound-bank lvl-nor-forest-amb
The tree's grid is one cell covering every emitter sphere; each region is in that cell and in the point cell (as in the donor, which lists the
sphere regions in their cells and in the last "point" cell).  T2R_P1_FIRE_SFX=0: off.
"""
import os
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.dirname(HERE)
sys.path[:0] = [HERE, os.path.join(TOOLS, "maps"), os.path.join(TOOLS, "models")]
import p1_rsenv  # noqa: E402
import t2pak  # noqa: E402

DONOR_LEVEL = "t2r-assault-forest-layout-0-audio"
DONOR_REGION = "emt-nor-parking-garage-fire-2-lp-cc-1"
DONOR_ANCHOR = (17.20383, 4.641314, 37.42868)       # p1_fires.DONOR_ANCHOR (the can's fire base)
BANK = "lvl-nor-forest-amb"
SOUND = 0xDDD5015FA757CECE                          # sfx-amb-emt-nor-parking-garage-fire-1-lp-cc
AUX_TYPE = 0x01386CE5B3A92451                       # SfxProcess
BODY_POS = 0x20                                     # xyz floats inside the region body (record +0x30 points at it)


def on():
    return os.environ.get("T2R_P1_FIRE_SFX", "1") != "0"


def level_name(m):
    return "t2r-" + m["key"] + "-fire-sfx"


def sfx_fires(m):
    """spec part1.fires of the map (empty when the sound or the fires are off)"""
    import p1_fires
    return p1_fires.fires(m) if on() else []


def registry(m):
    lv = level_name(m)
    return [f"level-name {lv}", f"level-id {lv}", f"package {lv}-ingame", f"sound-bank {BANK}"]


def files(m):
    """mod-relative archive paths of the map's fire sound level"""
    return [f"pak68/{level_name(m)}-ingame.pak"] if sfx_fires(m) else []


# ------------------------------------------------------------------ donor
class Donor:
    def __init__(self, data, region=DONOR_REGION):
        self.pk = t2pak.TPak(data)
        (self.pg, off), = [(p, o) for n, p, o in self.pk.items() if n == "REGION_TREE"]
        page = self.pk.pages[self.pg]
        recs = []
        k = off + 8
        while (self.pg, k) in self.pk.fix:
            recs.append(struct.unpack_from("<Q", page, k)[0])
            k += 8
        recs.sort()
        want = region.encode() + b"\0"
        self.start = next(r for r in recs if bytes(page[struct.unpack_from("<Q", page, r)[0]:][:len(want)]) == want)
        nxt = [r for r in recs if r > self.start]
        self.end = nxt[0] if nxt else None
        assert self.end, f"{region} is the last record of the donor tree"
        self.blob = bytes(page[self.start:self.end])
        self.slots = sorted(so - self.start for (p, so), dp in self.pk.fix.items() if p == self.pg and self.start <= so < self.end)
        for so in self.slots:                       # self-contained: every pointer of the blob stays inside it (and on the same page)
            assert self.pk.fix[(self.pg, self.start + so)] == self.pg
            t = struct.unpack_from("<Q", self.blob, so)[0]
            assert self.start <= t <= self.end, f"{region}: pointer at +{so:#x} leaves the blob ({t:#x})"
        body = struct.unpack_from("<Q", self.blob, 0x30)[0] - self.start
        self.body = body
        self.pos = struct.unpack_from("<3f", self.blob, body + BODY_POS)
        aux = struct.unpack_from("<Q", self.blob, 0x40)[0] - self.start
        assert struct.unpack_from("<QQ", self.blob, aux) == (AUX_TYPE, SOUND), "donor aux is not SfxProcess fire-1-lp-cc"
        regions, self.grid = p1_rsenv.read_pak_regions(data)[0]
        reg = next(r for r in regions if r["name"] == region)
        self.cls = next((v for k, kind, v in reg["tags"] if k == p1_rsenv.TAG_OBSERVED_BY and kind == "sid"), p1_rsenv.SID_PLAYER)
        self.radius = struct.unpack_from("<f", self.blob, body + BODY_POS + 0x20)[0]


def fire_pos(f, donor):
    return tuple(f["pos"][i] + donor.pos[i] - DONOR_ANCHOR[i] for i in range(3))


def region_copy(donor, name, pos):
    """donor blob with the name, its sids and the body position replaced -> bytearray"""
    b = bytearray(donor.blob)
    old = DONOR_REGION.encode()
    nb = name.encode()
    assert len(nb) == len(old)
    sid = p1_rsenv.fnv(name)
    for slot in (0x00, 0x20):                           # the two name strings (+0x10 points at an empty one)
        so = struct.unpack_from("<Q", b, slot)[0] - donor.start
        assert bytes(b[so:so + len(old) + 1]) == old + b"\0", (slot, so)
        b[so:so + len(nb)] = nb
    struct.pack_into("<Q", b, 8, sid)
    struct.pack_into("<Q", b, 0x28, sid)
    struct.pack_into("<3f", b, donor.body + BODY_POS, *pos)
    return b


def region_names(n):
    return [DONOR_REGION[:-1] + str(i + 1) for i in range(n)]


# ------------------------------------------------------------------ tree
def build_tree(donor, poss, base):
    """REGION_TREE span for copies of the donor region at `poss` -> (span bytes, pointer slot offsets inside the span); pointers hold base + offset"""
    n = len(poss)
    L = len(donor.blob)
    start0 = (8 + 8 * (n + 1) + 15) // 16 * 16
    assert base % 16 == 0
    starts = [start0 + i * ((L + 15) // 16 * 16) for i in range(n)]
    grid_pos = starts[-1] + (L + 15) // 16 * 16
    rad = donor.radius
    lo = [min(p[t] for p in poss) - rad - 1.0 for t in range(3)]
    hi = [max(p[t] for p in poss) + rad + 1.0 for t in range(3)]
    ncell = 1
    cell0 = grid_pos + 48 + 8 * (ncell + 1)
    cell_pos = [cell0, cell0 + 16 + 16 + 16 + 8 * n]          # cell = header 16 + one class entry 16 + list header 16 + n pointers
    total = cell_pos[1] + 16 + 16 + 16 + 8 * n + 8
    out = bytearray(total)
    relocs = []

    def ptr(at, target):
        struct.pack_into("<Q", out, at, base + target)
        relocs.append(at)
    ptr(0, grid_pos)
    for i, s in enumerate(starts):
        ptr(8 + 8 * i, s)
    struct.pack_into("<4f4f3II", out, grid_pos, lo[0], lo[1], lo[2], 1.0, hi[0] - lo[0], hi[1] - lo[1], hi[2] - lo[2], 1.0, 1, 1, 1, 0)
    for i, cp in enumerate(cell_pos):
        ptr(grid_pos + 48 + 8 * i, cp)
        ptr(cp, cp + 16)
        struct.pack_into("<Q", out, cp + 8, 1)
        struct.pack_into("<Q", out, cp + 16, donor.cls)
        lp = cp + 32
        ptr(cp + 24, lp)
        ptr(lp, lp + 16)
        struct.pack_into("<Q", out, lp + 8, n)
        for t, s in enumerate(starts):
            ptr(lp + 16 + 8 * t, s)
    return out, relocs, starts


def make_pak(donor_data, fires):
    """donor Forest audio -ingame pak bytes + [{"name", "pos"}] -> the fire sound level's -ingame pak bytes"""
    donor = Donor(donor_data)
    poss = [fire_pos(f, donor) for f in fires]
    names = region_names(len(fires))

    def tree(base):
        out, relocs, starts = build_tree(donor, poss, base)
        for s, nm, p in zip(starts, names, poss):
            blob = region_copy(donor, nm, p)
            for so in donor.slots:           # rebase the blob's pointers: donor page offset -> base + s + (target - donor.start)
                t = struct.unpack_from("<Q", blob, so)[0]
                struct.pack_into("<Q", blob, so, base + s + (t - donor.start))
                relocs.append(s + so)
            out[s:s + len(blob)] = blob
        return bytes(out), relocs
    return p1_rsenv.make_ingame_pak(None, None, tree=tree), donor


def build(stage_pak, fires, cache):
    """fetch the donor, write the level pak at `stage_pak` -> number of emitters"""
    import level_edit
    donor = level_edit.fetch(DONOR_LEVEL, cache, suffixes=("-ingame",))["-ingame"]
    data, _ = make_pak(open(donor, "rb").read(), fires)
    os.makedirs(os.path.dirname(stage_pak), exist_ok=True)
    open(stage_pak, "wb").write(data)
    return len(fires)
