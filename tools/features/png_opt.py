"""Lossless PNG recompression of the mod stage (size audit: the 326 staged PNGs are 48.8 MB, incompressible by lz4 / xz).

The IDAT stream is recoded (oxipng level 4, libdeflater 12); NOTHING else may change: no colour type / bit depth / palette
reduction, no chunk stripping, same interlacing, same IHDR. Every result is checked against the original (IHDR bytes identical, decoded
pixels identical through PIL) and discarded when it differs or is not smaller. Results are cached by content hash
(tools/local/build-cache/png), so a rebuild only pays for new images.

Needs `pip install pyoxipng` (+ Pillow, numpy: already in tools/win/.venv); without it optimize_stage() does nothing and says so.
  python png_opt.py <stage_dir>        # in place
Measured on one stage: 48.8 MB -> 46.1 MB (map-pvp-blockmesh-1.png 4.3 -> 2.8 MB), all 326 pixel-identical.
"""
import concurrent.futures
import hashlib
import io
import os
import sys

TOOLS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _cache_dir():
    d = os.environ.get("T2R_PNG_CACHE") or os.path.join(TOOLS, "local", "build-cache", "png")
    os.makedirs(d, exist_ok=True)
    return d


def _pixels(data):
    from PIL import Image
    import numpy as np
    im = Image.open(io.BytesIO(data))
    im.load()
    return im.mode, im.size, np.asarray(im).tobytes(), repr(im.info.get("transparency"))


def optimize_bytes(data, oxipng):
    """the recoded PNG, or `data` itself when nothing smaller and pixel-identical came out"""
    if data[:8] != b"\x89PNG\r\n\x1a\n":
        return data
    out = oxipng.optimize_from_memory(
        data, level=4, deflate=oxipng.Deflaters.libdeflater(12), idat_recoding=True, optimize_alpha=False, fix_errors=False,
        bit_depth_reduction=False, color_type_reduction=False, palette_reduction=False, grayscale_reduction=False,
        strip=oxipng.StripChunks.none())
    if len(out) >= len(data) or out[8:33] != data[8:33]:          # (signature excluded) IHDR chunk incl. CRC: same size / depth / type / interlace
        return data
    if _pixels(out) != _pixels(data):
        return data
    return out


def optimize_stage(stage, log=print):
    """recode every *.png under `stage` in place; returns (files, bytes before, bytes after)"""
    try:
        import oxipng
        import PIL  # noqa: F401
    except ImportError:
        log("png_opt: pyoxipng / Pillow not installed (pip install pyoxipng): PNGs staged as they are")
        return 0, 0, 0
    cache = _cache_dir()
    files = []
    for dp, _, fn in os.walk(stage):
        for f in fn:
            if f.lower().endswith(".png"):
                files.append(os.path.join(dp, f))

    import threading
    guard, locks = threading.Lock(), {}

    def one(p):
        d = open(p, "rb").read()
        key = hashlib.blake2b(d, digest_size=20).hexdigest()
        cp = os.path.join(cache, key + ".png")
        with guard:                      # one worker per cache key: files with the same bytes (e.g. one image staged as several variants)
            lk = locks.setdefault(key, threading.Lock())   # raced on the same cache file (Windows: replace onto a file open in another thread = WinError 5)
        with lk:
            if os.path.exists(cp):
                o = open(cp, "rb").read()
            else:
                o = optimize_bytes(d, oxipng)
                tmp = cp + f".{os.getpid()}.{id(d)}.tmp"
                with open(tmp, "wb") as f:
                    f.write(o)
                os.replace(tmp, cp)
        if o != d:
            with open(p, "wb") as f:
                f.write(o)
        return len(d), len(o)

    with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, (os.cpu_count() or 4) - 1)) as ex:
        res = list(ex.map(one, files))
    a, b = sum(r[0] for r in res), sum(r[1] for r in res)
    log(f"png_opt: {len(files)} PNGs {a / 1e6:.1f} MB -> {b / 1e6:.1f} MB (lossless, pixel-checked)")
    return len(files), a, b


if __name__ == "__main__":
    optimize_stage(sys.argv[1])
