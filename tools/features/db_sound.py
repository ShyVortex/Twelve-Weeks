"""Double Barrel shot sound (more unique and punchy).

The DB (weapon shotgun-baserri-over-under) fires the game's own event sfx-shotgun-baserri-over-under-player of the bank
wpn-shotgun-dblbarrel-over-under (the Shorty has its own Part I sound set now, so this bank is the DB's alone).  The event's body is the
four raw-PCM "thump" layers (wpn-shotgun-baserri-over-under-thump-v1-1..4, mono 48 kHz, ~1 s, 75-90 % under 150 Hz: a dull low boom with
no crack) under the 4-channel ATRAC9 bloom tail.  This module renders replacement thumps from the game's own waves, offline, and
build_dll puts them into the bank with sndbank.replace_pcm (same path as the Tactical Shotgun's Chigurh thumps), so the shot stays a
native game event: 3D positional on other players, the bloom tail / distant layers untouched.

Three candidates (CANDIDATES), default DEFAULT:
  magnum-boom   the DB thump + the .357 revolver's thump on top (the crack the DB lacks) + a 60 Hz sub (pump LFE) + the .45 spike transient
  rifle-slam    the DB thump + the hunting rifle's tump (v4) and its deep LFE (58 Hz, 0.36 s) + the R700 spike: a long, tight rifle-bore slam
  twin-cannon   two barrels: the DB thump pitched down 15 % (heavier) + a second, normal-pitch thump 24 ms later, .357 crack, pump LFE

Every mix is peak-limited (soft clip, 0.95) and its RMS is held within +2 dB of the original thump so the DB is not louder than the other
guns by more than a punchier shot should be.

  python db_sound.py render [outdir]    candidate WAVs (one-shot preview = thump variant 1 + the bloom tail at -12 dB) -> re/sound/custom/db-candidates
"""
import glob
import os
import struct
import sys
import wave

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
MAIN = ROOT.split(os.sep + ".claude" + os.sep)[0] if (os.sep + ".claude" + os.sep) in ROOT else ROOT
RATE = 48000
BANK = "wpn-shotgun-dblbarrel-over-under"
DB_THUMPS = [f"wpn-shotgun-baserri-over-under-thump-v1-{k}.wav" for k in range(1, 5)]
# source wave: (bank dir, file-name suffix); variant k picks entry k % len when several
SRC = {
    "thump": [(BANK, "baserri-over-under-thump-v1-%d.wav")],
    "magnum": [("wpn-pistol-revolver-bull", "revolver-taurus-thump-v10-1.wav"), ("wpn-pistol-revolver-bull", "revolver-taurus-thump-v10-3.wav"),
               ("wpn-pistol-revolver-bull", "revolver-taurus-thump-v10-4.wav"), ("wpn-pistol-revolver-bull", "revolver-taurus-thump-v10-5.wav")],
    "spike45": [("wpn-pistol-revolver-bull", "wpn-spike-45cal.wav")],
    "pumplfe": [(BANK, "wpn-pump-shotgun-lfe-1.wav")],
    "bolttump": [("wpn-rifle-rembrandt-bolt", "bolt-rifle-tump-v4-0%d.wav")],
    "boltlfe": [("wpn-rifle-rembrandt-bolt", "weapon-lfe-01.wav")],
    "r700": [("wpn-rifle-rembrandt-bolt", "wpn-spike-r700.wav")],
}
# candidate: [(source, gain, delay ms, speed)]  (speed < 1 = slower / lower; the thump of variant k is the layer 'thump')
CANDIDATES = {
    "magnum-boom": [("thump", 0.50, 0, 1.0), ("magnum", 0.70, 0, 1.0), ("pumplfe", 0.60, 0, 1.0), ("spike45", 1.00, 0, 1.0), ("r700", 0.60, 0, 1.0)],
    "rifle-slam": [("thump", 0.45, 0, 1.0), ("bolttump", 0.80, 2, 1.0), ("boltlfe", 0.50, 0, 1.0), ("r700", 1.00, 0, 1.0), ("spike45", 0.50, 0, 1.0)],
    "twin-cannon": [("thump", 0.60, 0, 0.85), ("thump", 0.55, 24, 1.0), ("magnum", 0.35, 0, 1.0), ("pumplfe", 0.60, 0, 1.0), ("spike45", 0.90, 0, 1.0)],
}
DEFAULT = "magnum-boom"
PEAK = 0.95
RMS_MAX_DB = 3.0
RMS_TARGET_DB = 2.0


def _find(bank, suffix):
    for base in (ROOT, MAIN):
        hit = glob.glob(os.path.join(base, "re", "sound", "wav", bank, "*" + suffix))
        if hit:
            return hit[0]
    raise FileNotFoundError(f"{bank}/*{suffix}")


def read_mono(path):
    w = wave.open(path)
    ch, sr, n = w.getnchannels(), w.getframerate(), w.getnframes()
    x = np.frombuffer(w.readframes(n), dtype="<i2").astype(np.float64).reshape(-1, ch)[:, 0] / 32768.0
    if sr != RATE:
        x = np.interp(np.arange(int(len(x) * RATE / sr)) * sr / RATE, np.arange(len(x)), x)
    return x


def _layer(name, k):
    opts = SRC[name]
    bank, suf = opts[(k - 1) % len(opts)]
    if "%d" in suf:
        suf = suf % ((k - 1) % 4 if name == "bolttump" else k)
    return read_mono(_find(bank, suf))


def render_variant(spec, k, n=None):
    """one thump variant (k = 1..4) of a candidate, mono float, length of the original thump"""
    ref = _layer("thump", k)
    n = n or len(ref)
    out = np.zeros(n + RATE // 2)
    for name, gain, delay_ms, speed in spec:
        x = _layer(name, k)
        if speed != 1.0:
            x = np.interp(np.arange(int(len(x) / speed)) * speed, np.arange(len(x)), x)
        d = int(RATE * delay_ms / 1000)
        m = min(len(x), len(out) - d)
        out[d:d + m] += x[:m] * gain
    out = out[:n]
    rms_ref = np.sqrt((ref ** 2).mean())
    # RMS cap: at most +RMS_MAX_DB over the original thump (a punchier shot, not a louder gun)
    # target: ~+1 dB over the original (RMS_TARGET_DB) - candidates that came out quieter are raised, louder ones are held at the cap
    r = np.sqrt((out ** 2).mean())
    out *= min(rms_ref * 10 ** (RMS_TARGET_DB / 20) / r, rms_ref * 10 ** (RMS_MAX_DB / 20) / r) if r > 0 else 1.0
    # soft clip to PEAK (tanh knee), then a hard guard
    out = np.tanh(out / PEAK) * PEAK
    fade = min(144, n // 2)                      # 3 ms fade-out like sndbank.replace_pcm
    out[-fade:] *= np.linspace(1, 0, fade)
    return np.clip(out, -PEAK, PEAK)


def write_wav(path, x, rate=RATE, ch=1):
    pcm = (np.clip(x, -1, 1) * 32767).astype("<i2").tobytes()
    with wave.open(path, "wb") as w:
        w.setnchannels(ch)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(pcm)


def build_wavs(out_dir, name=None):
    """the four thump variants of candidate `name` as '<thump wave name>' files in out_dir (replace_pcm's src_dir)"""
    os.makedirs(out_dir, exist_ok=True)
    spec = CANDIDATES[name or DEFAULT]
    for k, wn in enumerate(DB_THUMPS, 1):
        write_wav(os.path.join(out_dir, wn), render_variant(spec, k))
    return {wn: wn for wn in DB_THUMPS}


def stats(x):
    sp = np.abs(np.fft.rfft(x)) ** 2
    fr = np.fft.rfftfreq(len(x), 1 / RATE)
    t = sp.sum() + 1e-12
    a = x[:int(RATE * 0.03)]
    return dict(attack=float(np.sqrt((a ** 2).mean()) / (np.sqrt((x ** 2).mean()) + 1e-12)), peak=float(np.abs(x).max()), rms=float(np.sqrt((x ** 2).mean())), low150=float(sp[fr < 150].sum() / t),
                presence=float(sp[(fr >= 2000) & (fr < 8000)].sum() / t), centroid=float((fr * sp).sum() / t))


def render(outdir=None):
    outdir = outdir or os.path.join(MAIN, "re", "sound", "custom", "db-candidates")
    os.makedirs(outdir, exist_ok=True)
    tail = None
    for base in (ROOT, MAIN):
        hit = glob.glob(os.path.join(base, "re", "sound", "wav", BANK, "*bloom-quad-v1-1.wav"))
        if hit:
            w = wave.open(hit[0])
            t = np.frombuffer(w.readframes(w.getnframes()), dtype="<i2").astype(np.float64).reshape(-1, w.getnchannels()) / 32768
            tail = t[:, :2]
            break
    ref = _layer("thump", 1)
    base = ref.copy()
    print("%-12s attack %.2f peak %.2f rms %.3f low<150 %.2f presence(2-8k) %.2f centroid %5.0f Hz" % ((("old",)) + tuple(stats(base).values())))
    for name, spec in CANDIDATES.items():
        x = render_variant(spec, 1)
        s = stats(x)
        print("%-12s attack %.2f peak %.2f rms %.3f low<150 %.2f presence(2-8k) %.2f centroid %5.0f Hz" % ((name,) + tuple(s.values())))
        mix = np.zeros((len(tail), 2))
        mix += tail * 0.25                                      # the real shot also has the bloom tail (about this much in the event)
        mix[:len(x), :] += x[:, None]
        write_wav(os.path.join(outdir, name + ".wav"), np.clip(mix, -1, 1).reshape(-1), RATE, 2)
    mix = np.zeros((len(tail), 2))
    mix += tail * 0.25
    mix[:len(base), :] += base[:, None]
    write_wav(os.path.join(outdir, "old-db.wav"), np.clip(mix, -1, 1).reshape(-1), RATE, 2)
    print("rendered ->", outdir)


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "render":
        render(sys.argv[2] if len(sys.argv) > 2 else None)
    else:
        print(__doc__)
