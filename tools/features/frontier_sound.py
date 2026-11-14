"""The Frontier Rifle's own gunshot.

The gun fires the lever-action bank's shot event (sfx-rifle-lever-action-npc, bank wpn-rifle-lever-action: nobody else in MP uses that
bank).  Its shot is layered; the layers that carry the character are replaced in place (tools/features/sndbank.py):
  * 4 raw 16-bit PCM "thump" layers (the Mini-14 thumps the SP lever rifle used) -> frontier-thump-1..4.wav (this module, written to
    re/sound/custom/): the hunting rifle's own tump (re/sound/wav/wpn-rifle-rembrandt-bolt, wpn-bolt-rifle-tump-v4-00..03) pitched DOWN
    to 0.78x (heavier, a bigger bore) + the pump shotgun's LFE punch pitched to 0.62x under it + a short synthetic sub drop (95 -> 48 Hz,
    0.30 s) + a slap-back of the tump 85 ms later at -9 dB (an open-country echo no other TLOU2 gun has).
  * 3 stereo ATRAC9 "bloom" layers (the MPX5's) -> the hunting rifle's bloom-st-v1-01..03 crack (replace_waves; the crack is the head of
    the wave, the slots are shorter than the source so its tail is cut - the far-tail layer stays the lever bank's own).
Everything else of the bank (lever down / up cycle, round inserts, mech clicks: the SP lever rifle's, TLOU2's own) stays: the PS3 build
has no Frontier-specific bank (re/factions2013/frontier-rifle.md).

  python frontier_sound.py [out dir]      -> writes the thump wavs (default re/sound/custom) and prints their levels
"""
import glob
import os
import struct
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
MAIN = ROOT.split(os.sep + ".claude" + os.sep)[0]
sys.path.insert(0, HERE)
import sndbank  # noqa: E402

SR = 48000
OUT_DIR = os.path.join(ROOT, "tools", "local", "frontier-sound")      # generated at build time (re/sound is not versioned)
BOLT_WAV = "wpn-rifle-rembrandt-bolt"
BOLT_TUMP = [f"wpn-bolt-rifle-tump-v4-0{k}.wav" for k in range(4)]
LFE_WAV = ("wpn-shotgun-dblbarrel-over-under", "wpn-pump-shotgun-lfe-1.wav")
LEVER_THUMPS = {f"wpn-rifle-mini-14-thump-v1-{k}.wav": f"frontier-thump-{k}.wav" for k in range(1, 5)}
# the 3 stereo blooms of the lever bank (the MPX5's) <- the hunting rifle's crack (source bank wpn-rifle-rembrandt-bolt)
LEVER_BLOOMS = {f"wpn-rifle-mpx5-bloom-st-v1-{k}.wav": f"wpn-bolt-rifle-bloom-st-v1-0{k}.wav" for k in (1, 2, 3)}
PITCH_TUMP, PITCH_LFE = 0.78, 0.62
SLAP_DELAY, SLAP_GAIN = 0.085, 0.35        # -9 dB


def _find(wav_root, name):
    for sub in (wav_root,):
        hits = glob.glob(os.path.join(sub, "*" + name))
        if hits:
            return hits[0]
    raise FileNotFoundError(name)


def read_wav(path):
    d = open(path, "rb").read()
    i = d.find(b"data")
    n = struct.unpack_from("<I", d, i + 4)[0]
    ch = struct.unpack_from("<H", d, 22)[0]
    v = np.frombuffer(d[i + 8:i + 8 + n], dtype="<i2").astype(np.float64)
    return v[::ch] if ch > 1 else v


def write_wav(path, x):
    pcm = np.clip(np.round(x), -32768, 32767).astype("<i2").tobytes()
    hdr = b"RIFF" + struct.pack("<I", 36 + len(pcm)) + b"WAVEfmt " + struct.pack("<IHHIIHH", 16, 1, 1, SR, SR * 2, 2, 16)
    open(path, "wb").write(hdr + b"data" + struct.pack("<I", len(pcm)) + pcm)


def pitch(x, ratio):
    """resample: ratio < 1 plays slower / lower (and longer)"""
    n = int(len(x) / ratio)
    return np.interp(np.arange(n) * ratio, np.arange(len(x)), x)


def mix_thump(tump, lfe, k):
    t = pitch(tump, PITCH_TUMP)
    body = t.copy()
    pk = np.abs(tump).max()
    # LFE punch pitched under the thump
    l = pitch(lfe, PITCH_LFE)
    body[:len(l)] += l * (0.9 * pk / max(1.0, np.abs(l).max()))
    # synthetic sub drop: sine sweeping 95 -> 48 Hz, exponential decay, 0.30 s; slightly different per variant
    n = int(0.30 * SR)
    tt = np.arange(n) / SR
    f = 95.0 - (95.0 - 48.0) * (tt / 0.30) ** 0.6 + 4.0 * (k - 1.5)
    ph = 2 * np.pi * np.cumsum(f) / SR
    sub = np.sin(ph) * np.exp(-tt * 11.0) * (0.32 * pk)
    sub *= np.minimum(1.0, tt / 0.004)             # 4 ms attack: no click
    body[:n] += sub[:len(body)] if len(body) < n else sub
    # slap-back echo of the whole body
    d = int(SLAP_DELAY * SR)
    out = np.concatenate([body, np.zeros(d)])
    out[d:d + len(body)] += body * SLAP_GAIN
    out *= min(1.15 * pk, 31500.0) / max(1.0, np.abs(out).max())   # up to 1.15 x the hunting tump's peak, never clipped
    return out


def build_wavs(out_dir=None, wav_root=None):
    out_dir = out_dir or OUT_DIR
    wav_root = wav_root or os.path.join(ROOT if os.path.isdir(os.path.join(ROOT, "re", "sound", "wav")) else MAIN, "re", "sound", "wav")
    os.makedirs(out_dir, exist_ok=True)
    lfe = read_wav(_find(os.path.join(wav_root, LFE_WAV[0]), LFE_WAV[1]))
    res = {}
    for k, name in enumerate(BOLT_TUMP):
        tump = read_wav(_find(os.path.join(wav_root, BOLT_WAV), name))
        out = mix_thump(tump, lfe, k)
        p = os.path.join(out_dir, f"frontier-thump-{k + 1}.wav")
        write_wav(p, out)
        res[p] = (len(out) / SR, float(np.abs(out).max()))
    return res


def build_bank(lever_bank, bolt_bank, wav_root=None, custom_dir=None):
    """lever bank bytes (re/sound/wpn-rifle-lever-action.bnk) with the Frontier shot layers; returns the new bank bytes"""
    wav_root = wav_root or os.path.join(ROOT if os.path.isdir(os.path.join(ROOT, "re", "sound", "wav")) else MAIN, "re", "sound", "wav")
    custom_dir = custom_dir or OUT_DIR
    data = sndbank.replace_waves(lever_bank, bolt_bank, LEVER_BLOOMS)
    data = sndbank.replace_pcm(data, os.path.join(wav_root, "wpn-rifle-lever-action"), LEVER_THUMPS, custom_dir)
    assert len(data) == len(lever_bank)
    return data


if __name__ == "__main__":
    for p, (sec, pk) in build_wavs(sys.argv[1] if len(sys.argv) > 1 else None).items():
        print(f"{os.path.basename(p)}: {sec:.3f} s, peak {pk:.0f}")
