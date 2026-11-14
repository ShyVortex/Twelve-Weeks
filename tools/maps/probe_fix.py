"""Reflection-probe (cubemap) brightening for the winter Supermarket hall (the character went dark in the hallway).

Cause (offline, re/maps/darkfix/README.md "v42"): the level carries NO light-probe volume (no irradiance / volume-probe item in any jackson-market pak),
so a dynamic object's ambient comes from the SPECULAR_CUBEMAPSET probe volume it stands in (record: +0x00 position, +0x10.. influence matrix = box, +0xc0 colour,
+0xd0 blend distances, +0xf0 cubemap hash).  The lane / hall (x -509..-501, z 273.4..284) is covered by the SP bathroom-corridor probe `reflectionprobe41`
(box 7.2 x 7.4 x 10.5 m, smallest volume at the spot), captured in SP's sealed, unlit interior: mean radiance 0.003, i.e. a black probe in a lane that MP opened
to the storm.  Its neighbours are black too (-int probe 17 west of x -505: 0.0003), and the two porch probes 34 / 40 are dim (0.05 / 0.06) against the yard
probes 0.2-0.6.  The lightmap on the walls / floor is fine (lightmap_fix); only the dynamic objects see the black probe.

Repair: scale the HDR cubemap of the listed probes up to a target mean radiance (gain >= 1 only, capped): the probe keeps its own picture, only its level
changes, so reflections and the ambient SH follow smoothly.  The full 256x256x7 BC6H cube (6 faces, 4 KB-aligned face stride 90112) comes from the texture
dict (the pak holds a 64x64 stub), is decoded, scaled and re-encoded (bc6h mode 11), and is injected by lightmap_fix.apply through its own inject / undo
machinery (hash + 1, record + the same undo).  T2R_NO_PROBE_FIX=1 skips it.  `python probe_fix.py report <out dir>` prints the before / after numbers.
"""
import os
import re
import struct
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "models"))
import bc6h  # noqa: E402

VERSION = 2          # 2: the character was still dark in the BOOTS SALE side room: EVERY black probe of the supermarket / -int paks, not only the lane ones
FACE_STRIDE = 90112          # 7 mips of 256x256 BC6H (5461 blocks x 16 B = 87376) rounded up to 4096
W0, MIPS, FACES = 256, 7, 6
MAX_GAIN = 1000.0
LUMA = np.array([0.2126, 0.7152, 0.0722])
# level -> {probe number (the .dds name 'reflectionprobeN'): target mean radiance}.  Measured (mean over the 6 faces, mip 0):
#   supermarket 41 (lane / hall) 0.0035, 34 (lane mouth, porch) 0.050, 40 (front strip) 0.059; -int 17 (west of the lane, x -519.6..-505.1) 0.0003.
#   Open yard probes 18 / 20 / 43 / 50 / 60 are 0.2 - 0.6.  The lane is roofed shade between two buildings (lightmap 0.15-0.45 against 0.65 on the open
#   strip), so 0.12 = about 0.4 of the yard probes; the bakery side (17) stays darker, 0.06.
#   v2: the same sealed-SP-interior problem covers every side room: supermarket 0 / 1 / 2 / 5 / 32 / 33 / 52-58 (0.0006-0.024) and -int 25-28 / 4 / 8 / 16 / 17 / 24 / 39 ... (0.0002-0.02)
#   are black too (the first fix only reached the lane).  "*" = a floor for every probe of the level not listed (gain >= 1 only: bright probes stay as they are).
SPEC = {
    "pat-jackson-supermarket": {"*": 0.12},
    "pat-jackson-supermarket-int": {"*": 0.10},
}


def spec_sig():
    return [VERSION, sorted((lv, sorted(p.items(), key=str)) for lv, p in SPEC.items())]


def mip_blocks(k):
    return max(1, (W0 >> k) // 4)


def mip_offsets():
    """byte offset of each mip inside a face, and its block count per side"""
    out, o = [], 0
    for k in range(MIPS):
        nb = mip_blocks(k)
        out.append((o, nb))
        o += nb * nb * 16
    return out


def _decode(blk, nb):
    """(4 nb, 4 nb, 3) of an nb x nb block mip (imagecodecs refuses images under 4 x 4 blocks: pad to a 4 x 4 grid and crop)"""
    if nb >= 4:
        return bc6h.decode(blk, 4 * nb, 4 * nb)
    pad = bytearray(16 * 16)
    for y in range(nb):
        for x in range(nb):
            pad[(y * 4 + x) * 16:(y * 4 + x) * 16 + 16] = blk[(y * nb + x) * 16:(y * nb + x) * 16 + 16]
    return bc6h.decode(bytes(pad), 16, 16)[:4 * nb, :4 * nb]


def decode_cube(data):
    """list over faces of list over mips of (4*nb, 4*nb, 3) float32"""
    offs = mip_offsets()
    faces = []
    for f in range(FACES):
        mips = []
        for o, nb in offs:
            blk = data[f * FACE_STRIDE + o:f * FACE_STRIDE + o + nb * nb * 16]
            mips.append(_decode(blk, nb))
        faces.append(mips)
    return faces


def mean_radiance(data):
    """(mean luma, mean RGB) of mip 0 over the 6 faces = the cube's L0 (ambient) term up to a constant"""
    offs = mip_offsets()
    rgb = np.zeros(3)
    for f in range(FACES):
        img = _decode(data[f * FACE_STRIDE:f * FACE_STRIDE + offs[0][1] ** 2 * 16], offs[0][1])
        rgb += img.reshape(-1, 3).astype(np.float64).mean(0)
    rgb /= FACES
    return float(rgb @ LUMA), rgb


def scaled(data, gain):
    """the cube with every texel x gain, same layout (padding bytes kept)"""
    out = bytearray(data)
    offs = mip_offsets()
    dec = decode_cube(data)
    for f in range(FACES):
        for (o, nb), img in zip(offs, dec[f]):
            by, bx = np.divmod(np.arange(nb * nb), nb)
            enc = bc6h.encode(bc6h.blocks_of(img * np.float32(gain), bx, by))
            a = f * FACE_STRIDE + o
            out[a:a + nb * nb * 16] = enc
    return bytes(out)


def probe_number(path):
    m = re.search(r"reflectionprobe(\d*)\.dds", path)
    return int(m.group(1) or 0) if m else None


def full_cube(h, work, log=print):
    """(fmt, w, h, mips, data) of the 6-face cube of VRAM_DESC hash h from the mounted texture dicts (cached under <work>/probe-fix)"""
    import json
    import texdict
    cd = os.path.join(work, "probe-fix")
    os.makedirs(cd, exist_ok=True)
    f = os.path.join(cd, "%016x.bin" % h)
    if os.path.exists(f):
        return open(f, "rb").read()
    got = texdict.find([h])
    if h not in got:
        return None
    fmt, w, hh, data = got[h]
    if (fmt, w, hh, len(data)) != (95, W0, W0, FACES * FACE_STRIDE):
        log("    probe cube %016x: unexpected texture %s" % (h, (fmt, w, hh, len(data))))
        return None
    open(f, "wb").write(data)
    return bytes(data)


def layers(p, level, work, log=print):
    """{key: (desc, hash, fmt, w, h, data, mips)} for the probes of `level` (ndpak.Pak p) that SPEC raises; {} when none / switched off"""
    if not os.environ.get("T2R_PROBE_FIX") or level not in SPEC:      # OFF by default (brightened probes made the whole Supermarket shiny / metallic); T2R_PROBE_FIX=1 = on
        return {}
    import ndpak
    out = {}
    for t in ndpak.textures(p):
        n = probe_number(t["path"])
        tgt = SPEC[level].get(n, SPEC[level].get("*")) if n is not None else None
        if tgt is None:
            continue
        if t["w"] >= W0 and t["size"] >= FACES * FACE_STRIDE:         # the pak already carries a full cube (not ours to touch twice)
            continue
        data = full_cube(t["hash"], work, log)
        if data is None:
            log("    probe %d: cube %016x not in the texture dicts, skipped" % (n, t["hash"]))
            continue
        lum, rgb = mean_radiance(data)
        gain = float(np.clip(tgt / max(lum, 1e-6), 1.0, MAX_GAIN))
        if gain <= 1.0001:
            continue
        new = scaled(data, gain)
        lum2, _ = mean_radiance(new)
        log("    probe %d: mean radiance %.4f -> %.4f (gain %.2f)" % (n, lum, lum2, gain))
        out["probe%d" % n] = (int(t["desc"]), int(t["hash"]), 95, W0, W0, new, MIPS)
    return out


def main(argv):
    if len(argv) < 2 or argv[0] != "report":
        print(__doc__)
        return 2
    import ndpak
    d = argv[1]
    work = argv[2] if len(argv) > 2 else os.path.join(d, "probe-report")
    for lv in SPEC:
        f = os.path.join(d, lv + ".pak")
        p = ndpak.Pak(f)
        print(lv)
        for k, (desc, h, fmt, w, hh, data, mips) in sorted(layers(p, lv, work).items()):
            old = full_cube(h, work)
            l0, r0 = mean_radiance(old)
            l1, r1 = mean_radiance(data)
            print("  %s  luma %.4f -> %.4f   rgb %s -> %s" % (k, l0, l1, np.round(r0, 4), np.round(r1, 4)))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
