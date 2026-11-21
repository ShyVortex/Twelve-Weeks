"""Length of a TLOU2 speech stream (speech1/english.psarc, key = md5 of the stream id): active voice time in ms (first to last sound above 5 % of the peak).
Used by vox_lines.py genbeg to chain the dismemberment scream takes back to back. vgmstream-cli: $T2R_VGMSTREAM or tools/local/vgmstream (this or the main checkout)."""
import hashlib, os, struct, subprocess, tempfile, wave, zlib
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))


def vgm():
    for p in (os.environ.get("T2R_VGMSTREAM") or "", os.path.join(ROOT, "tools", "local", "vgmstream", "vgmstream-cli.exe"),
              r".\tools\local\vgmstream\vgmstream-cli.exe"):
        if p and os.path.exists(p):
            return p
    raise SystemExit("vgmstream-cli not found ($T2R_VGMSTREAM)")


class Psarc:
    """plain big-endian zlib PSARC read with seeks (english.psarc is 3.7 GB): entry by md5 of the path string"""
    def __init__(self, path):
        self.f = open(path, "rb")
        magic, vmaj, vmin, comp, toc_len, esz, n, bsize, flags = struct.unpack(">4sHH4sIIIII", self.f.read(32))
        assert magic == b"PSAR" and comp == b"zlib", (magic, comp)
        self.f.seek(0)
        toc = self.f.read(toc_len)
        bt = 32 + n * esz
        self.bs = struct.unpack_from(">%dH" % ((toc_len - bt) // 2), toc, bt)
        self.bsize = bsize
        self.ent = {toc[32 + i * esz:32 + i * esz + 16]: (int.from_bytes(toc[32 + i * esz + 16:32 + i * esz + 20], "big"),
                                                          int.from_bytes(toc[32 + i * esz + 20:32 + i * esz + 25], "big"),
                                                          int.from_bytes(toc[32 + i * esz + 25:32 + i * esz + 30], "big")) for i in range(n)}

    def get(self, name):
        e = self.ent.get(hashlib.md5(name.encode()).digest())
        if e is None:
            return None
        bi, usz, off = e
        out = bytearray()
        while len(out) < usz:
            cs = self.bs[bi] or self.bsize
            self.f.seek(off)
            blk = self.f.read(cs)
            want = min(self.bsize, usz - len(out))
            out += blk if cs == want else zlib.decompress(blk)
            off += cs
            bi += 1
        return bytes(out)


def active_ms(arc, sid, tmp):
    data = arc.get(sid)
    if data is None:
        return 0
    src = os.path.join(tmp, sid + ".xvag")
    open(src, "wb").write(data)
    subprocess.run([vgm(), "-o", src + ".wav", src], capture_output=True)
    if not os.path.exists(src + ".wav"):
        return 0
    w = wave.open(src + ".wav")
    ch, sr, n = w.getnchannels(), w.getframerate(), w.getnframes()
    x = np.frombuffer(w.readframes(n), "<i2").reshape(-1, ch).astype(np.float64)[:, 0]
    w.close()
    os.remove(src + ".wav"); os.remove(src)
    pk = np.abs(x).max()
    if pk < 300:
        return 0
    win = max(1, int(sr * 0.02))
    env = np.sqrt(np.convolve(x * x, np.ones(win) / win, "same"))
    act = np.nonzero(env > 0.05 * pk)[0]
    return int((act[-1] - act[0]) * 1000 / sr) if len(act) else 0
