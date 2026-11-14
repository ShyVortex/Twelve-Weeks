"""Minimal BC6H_UF16 (DXGI 95) block codec for lightmap repairs.  Decode: imagecodecs.bcn_decode (bcdec, every mode, float16 out).
Encode: mode 11 only (one region, 10-bit unsigned endpoints, 4-bit indices; D3D11 spec "m[4:0]=00011, rw gw bw rx gx bx [9:0]"),
endpoints on the block's principal axis in the codec's interpolation domain, then a least-squares refit.  Deterministic, numpy only.
Only the blocks a repair touches are re-encoded; every other block of the texture keeps its bytes."""
import numpy as np

W4 = np.array([0, 4, 9, 13, 17, 21, 26, 30, 34, 38, 43, 47, 51, 55, 60, 64], np.int64)


def decode(data, w, h):
    """(h, w, 3) float32 of a whole BC6H_UF16 mip"""
    import imagecodecs
    return imagecodecs.bcn_decode(bytes(data), 6, shape=(h, w, 3)).astype(np.float32)


def _unq(x):
    """10-bit endpoint -> 16-bit interpolation value (unsigned)"""
    x = np.asarray(x, np.int64)
    return np.where(x == 0, 0, np.where(x == 1023, 0xFFFF, ((x << 16) + 0x8000) >> 10))


def _to_c(f):
    """float -> the codec's interpolation domain (half bits * 64 / 31): finish = (c * 31) >> 6 gives the half bits back"""
    hb = np.clip(np.asarray(f, np.float32), 0, 65504).astype(np.float16).view(np.uint16).astype(np.float64)
    return np.minimum(hb * 64.0 / 31.0, 65535.0)


def _quant(c):
    """interpolation-domain value -> nearest 10-bit endpoint"""
    c = np.asarray(c, np.float64)
    x0 = np.clip(np.floor(c * 1024 / 65536), 0, 1023).astype(np.int64)
    best = x0.copy()
    be = np.abs(_unq(x0) - c)
    for dx in (-1, 1, 2):
        x = np.clip(x0 + dx, 0, 1023)
        e = np.abs(_unq(x) - c)
        m = e < be
        best, be = np.where(m, x, best), np.where(m, e, be)
    return best


def _palette(q0, q1):
    e0, e1 = _unq(q0), _unq(q1)                                          # (n, 3)
    c = ((64 - W4)[None, :, None] * e0[:, None, :] + W4[None, :, None] * e1[:, None, :] + 32) >> 6
    return c.astype(np.float64)                                          # (n, 16, 3)


def encode(px):
    """px (n, 16, 3) float texels (row-major 4x4 per block) -> n * 16 bytes, mode 11"""
    px = np.asarray(px, np.float64)
    n = len(px)
    C = _to_c(px)
    m = C.mean(1)
    d = C - m[:, None]
    cov = np.einsum("nki,nkj->nij", d, d)
    ax = np.ones((n, 3)) / np.sqrt(3)
    for _ in range(10):
        ax = np.einsum("nij,nj->ni", cov, ax)
        ax /= np.maximum(np.linalg.norm(ax, axis=1, keepdims=True), 1e-12)
        ax = np.where(np.isfinite(ax), ax, 1 / np.sqrt(3))
    t = np.einsum("nki,ni->nk", d, ax)
    e0 = np.clip(m + t.min(1)[:, None] * ax, 0, 65535)
    e1 = np.clip(m + t.max(1)[:, None] * ax, 0, 65535)
    for it in range(3):
        q0, q1 = _quant(e0), _quant(e1)
        pal = _palette(q0, q1)
        idx = ((C[:, :, None, :] - pal[:, None, :, :]) ** 2).sum(3).argmin(2)       # (n, 16)
        if it == 2:
            break
        a = (64 - W4[idx]) / 64.0                                        # least-squares refit of the endpoints for these indices
        b = W4[idx] / 64.0
        aa, ab, bb = (a * a).sum(1), (a * b).sum(1), (b * b).sum(1)
        det = aa * bb - ab * ab
        ok = np.abs(det) > 1e-9
        ax_ = np.einsum("nk,nkc->nc", a, C)
        bx_ = np.einsum("nk,nkc->nc", b, C)
        ne0 = (bb[:, None] * ax_ - ab[:, None] * bx_) / np.where(ok, det, 1)[:, None]
        ne1 = (aa[:, None] * bx_ - ab[:, None] * ax_) / np.where(ok, det, 1)[:, None]
        e0 = np.where(ok[:, None], np.clip(ne0, 0, 65535), e0)
        e1 = np.where(ok[:, None], np.clip(ne1, 0, 65535), e1)
    sw = idx[:, 0] >= 8                                                  # anchor (texel 0) index MSB is implicit 0
    q0, q1 = np.where(sw[:, None], q1, q0), np.where(sw[:, None], q0, q1)
    idx = np.where(sw[:, None], 15 - idx, idx)
    fields = [(np.full(n, 0b00011), 5)]
    for q in (q0, q1):
        for c in range(3):
            fields.append((q[:, c], 10))
    fields.append((idx[:, 0], 3))
    fields += [(idx[:, k], 4) for k in range(1, 16)]
    bits = np.concatenate([((v[:, None].astype(np.int64) >> np.arange(nb)) & 1) for v, nb in fields], 1).astype(np.uint8)
    assert bits.shape[1] == 128
    return np.packbits(bits, 1, bitorder="little").tobytes()


def blocks_of(img, bx, by):
    """(n, 16, c) texels of the 4x4 blocks (bx, by) of an (h, w, c) image"""
    bx, by = np.asarray(bx), np.asarray(by)
    ys = by[:, None] * 4 + np.repeat(np.arange(4), 4)[None, :]
    xs = bx[:, None] * 4 + np.tile(np.arange(4), 4)[None, :]
    return img[ys, xs]


def patch(data, w, h, img, bx, by):
    """re-encode blocks (bx, by) of BC6H texture bytes `data` from image img (h, w, 3 float) -> new bytes"""
    out = bytearray(data)
    if not len(bx):
        return bytes(out)
    enc = encode(blocks_of(img, bx, by))
    nbx = w // 4
    for k, (x, y) in enumerate(zip(bx, by)):
        o = (int(y) * nbx + int(x)) * 16
        out[o:o + 16] = enc[16 * k:16 * k + 16]
    return bytes(out)


def _selftest():
    rng = np.random.default_rng(1)
    base = rng.uniform(0, 2, (500, 1, 3)) * np.linspace(0.2, 1, 16)[None, :, None] + rng.uniform(0, 0.05, (500, 16, 3))
    enc = encode(base)
    # decode as a 4 x (4*500) strip: block k at bx = k
    import imagecodecs
    dec = imagecodecs.bcn_decode(enc, 6, shape=(4, 4 * 500, 3)).astype(np.float64)
    got = dec.reshape(4, 500, 4, 3).transpose(1, 0, 2, 3).reshape(500, 16, 3)
    rel = np.abs(got - base) / np.maximum(base, 0.05)
    return float(rel.mean()), float(rel.max())


if __name__ == "__main__":
    print("BC6H mode 11 self test (mean / max relative error):", _selftest())
