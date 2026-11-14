"""SP's burning human death (the thug-death-reactions rows npc-m-death-molotov-{fw-a,bw,lt-a,rt-a}) as a small carrier pak for MP.

The clips live in anim-npc-m.pak (15 MB, 727 clips, never an MP level add: the Seraphite own-spawn crash exe+c065cc went away without it). The
UC4 downed pipeline already proved the safe route: bake clips into the ClipData of the carriers of a small game pak (re/uc4ps4/tools/carrier_patch.py,
plain blobs with no fixups, rig 0x2696d0b4 = base-female = every MP look) and let the level list that pak. Host = anim-npc-m-cover-share.pak (1.7 MB,
SP cover idles, same rig, nothing in MP asks for its clips): its four biggest carriers on page 1 (>= 32 KB, the molotov ClipData are 19-24 KB) get the four
molotov ClipData bytes unchanged; the pak keeps its name, ANIM flags loop bit cleared (the -bw / non -a clips ship with it set), raw channels (mover)
frozen like every carrier (the body stays where the net puts it). build_dll._stage_anim_pak then strips the effect tables (the ext does the fire +
scream) and the pack step writes it like any other actor97 pak.

  python molo_death_pak.py <anim-npc-m.pak> <anim-npc-m-cover-share.pak> <out.pak>   (self-check included)
t2r-ext deathreact.c DR_CLIPS[0][2] uses the CARRIER names below (clip names in the game are the carrier names)."""
import os
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
UC4T = os.path.join(ROOT, "re", "uc4ps4", "tools")
HOST_PAK = "anim-npc-m-cover-share"
SRC_PAK = "anim-npc-m"
# direction (t2r-ext dir 0 fw 1 bw 2 lt 3 rt) -> (SP clip, carrier name in the host pak)
MOLO = [
    ("npc-m-death-molotov-fw-a", "npc-bow-cover-low-l-hunker-idle"),
    ("npc-m-death-molotov-bw", "npc-bow-cover-stand-r-hunker-idle"),
    ("npc-m-death-molotov-lt-a", "npc-bow-cover-low-r-hunker-idle"),
    ("npc-m-death-molotov-rt-a", "npc-bow-cover-stand-l-hunker-idle"),
]


def _clipdata(pak, name):
    """ClipData bytes of ANIM `name` in an ndpak.Pak (raises if it is not plain: a fixup inside it)"""
    d = pak.d
    it = [x for x in pak.items if x[0] == name and x[1] == "ANIM"]
    if not it:
        raise KeyError(name)
    base = it[0][3] + 48
    ca = pak.pages[pak.fix[base + 8]][0] + struct.unpack_from("<Q", d, base + 8)[0]
    sz = struct.unpack_from("<I", d, ca + 8)[0]
    if any(ca <= a < ca + sz for a in pak.fix):
        raise ValueError(f"{name}: ClipData holds pointer fixups - not a plain blob")
    return bytes(d[ca:ca + sz]), base


def _load(data):
    sys.path.insert(0, os.path.join(ROOT, "tools", "models"))
    import ndpak
    import tempfile
    fd, tmp = tempfile.mkstemp(suffix=".pak")
    os.close(fd)
    try:
        open(tmp, "wb").write(data)
        return ndpak.Pak(tmp)
    finally:
        os.remove(tmp)


def build(src, host):
    """src = anim-npc-m.pak bytes, host = anim-npc-m-cover-share.pak bytes -> patched host bytes"""
    sys.path.insert(0, UC4T)
    import carrier_patch
    sp = _load(src)
    cwd = os.getcwd()
    import tempfile
    os.chdir(tempfile.gettempdir())            # carrier_patch parses through a temp file in the cwd
    try:
        for clip, carrier in MOLO:
            cd, _ = _clipdata(sp, clip)
            host, cap, nfrz = carrier_patch.patch(host, carrier, cd, True, loop=False)
            print("  %-26s <- %-26s %6d / %6d bytes, %d raw channels frozen" % (carrier, clip, len(cd), cap, nfrz))
    finally:
        os.chdir(cwd)
    return host


def verify(src, host, out):
    """every carrier = the SP ClipData byte for byte (zero padded to the slot), loop bit clear, same pak size / page table, other clips untouched"""
    sp, h0, h1 = _load(src), _load(host), _load(out)
    assert len(out) == len(host) and h1.pages == h0.pages, "pak layout changed"
    for clip, carrier in MOLO:
        cd, _ = _clipdata(sp, clip)
        got, base = _clipdata(h1, carrier)
        assert got[:len(cd)] == cd and not any(got[len(cd):]), f"{carrier}: ClipData differs from {clip}"
        assert not struct.unpack_from("<I", h1.d, base + 4)[0] & 1, f"{carrier}: loop bit still set"
        nfr = struct.unpack_from("<I", cd, 0x10)[0] if len(cd) > 0x14 else 0
        print("  ok %-26s = %s (%d bytes)" % (carrier, clip, len(cd)))
    names = {c for _, c in MOLO}
    for nm, typ, pi, io in h0.items:
        if typ == "ANIM" and nm not in names:
            a, _ = _clipdata(h0, nm)
            b, _ = _clipdata(h1, nm)
            assert a == b, f"{nm} (other clip) changed"
    return True


if __name__ == "__main__":
    a = sys.argv[1:]
    src, host = open(a[0], "rb").read(), open(a[1], "rb").read()
    out = build(src, host)
    verify(src, host, out)
    open(a[2], "wb").write(out)
    print("wrote", a[2], len(out), "bytes")
