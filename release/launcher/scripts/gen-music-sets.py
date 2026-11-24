"""Launcher music sets CALM and HOPEFUL (the faction sets are GRIM).

Source: the game's own common.psarc music1/*.xvag streams, decoded with vgmstream (4 ch = two stereo stems -> stereo as
front + 0.7 x rear, as the README describes for the first sets), chunks chained with 2.5 s cross-fades, faded in / out,
loudness-normalised to -23 LUFS, Opus 64 kbps stereo into assets/music/<name>.ogg.

  python scripts/gen-music-sets.py            # writes assets/music/calm-*.ogg + hope-*.ogg
  python scripts/gen-music-sets.py --wav DIR  # also keeps the 48 kHz wav of each track in DIR (auditions)

Needs: vgmstream-cli ($T2R_VGMSTREAM or the private toolchain's speech_dur.vgm()), ffmpeg on PATH, numpy,
a dsar_list.py archive lister ($T2R_TOOLS, required), the game's common.psarc ($T2R_COMMON_PSARC).
"""
import os, subprocess, sys, tempfile, wave, re, argparse
import numpy as np

TOOLS = os.environ.get("T2R_TOOLS", "")
sys.path.insert(0, TOOLS); sys.path.insert(0, os.path.join(TOOLS, "features"))
import dsar_list, speech_dur  # noqa: E402

PSARC = os.environ.get("T2R_COMMON_PSARC", "")
HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "..", "assets", "music")
XF, FADE_IN, FADE_OUT, LUFS, MAX_S = 2.5, 2.0, 4.0, -23.0, 125.0

M = "music1/%s.xvag"
SETS = {
    # CALM: beds with no pulse and no tension layer - the prologue ride's ambient loops, the farm, Ellie and Dina's lullaby.
    "calm-01-ride": ["698_g83_new_jackson_ride_b_ambient1_loop", "698_g83_new_jackson_ride_d_ambient2_loop",
                     "698_g83_new_jackson_ride_f_ambient3_loop", "698_g83_new_jackson_ride_h_ambient4_loop_taffied"],
    "calm-02-farm": ["425_far-explore-house-tractor_igc_pt1", "425_far-explore-house-tractor_igc_pt2", "425_far-explore-house-tractor_igc_pt3",
                     "425_far-explore-house-tractor_igc_pt4", "425_far-explore-house-tractor_igc_pt5", "425_far-explore-house-tractor_igc_pt6"],
    "calm-03-lullaby": ["602_elliedinalullaby_a_rideoneshot", "602_elliedinalullaby_b_ambientloop"],
    # HOPEFUL: the guitar - the ride into Jackson's guitar phrases and the walk through Jackson.
    # (tried and dropped: the museum's 579_joel_ellie_bguitar1 moods - sparse stingers with 5-10 s of silence between them; 576_g82_bguitar1_mood_k +
    # 593_bguitar1garden_firefly moods and 617_b_afd-jackson-reprise - too tense by ear)
    "hope-01-jackson": ["698_g83_new_jackson_ride_a_phrase1_intro_guitar_down", "698_g83_new_jackson_ride_c_phrase2_intro_guitar_down_trimmed",
                        "698_g83_new_jackson_ride_e_phrase3_intro_guitar_down_reupload", "698_g83_new_jackson_ride_g_phrase4_intro_guitar_down"],
    "hope-02-walk": ["640_snap_jackson_walk_loop"],
}


def decode(d, ent, bs, bsz, name, tmp, vgm):
    s = os.path.join(tmp, "a.xvag")
    open(s, "wb").write(dsar_list.extract(d, ent, bs, bsz, M % name))
    subprocess.run([vgm, "-o", s + ".wav", s], capture_output=True, check=True)
    w = wave.open(s + ".wav"); ch, sr, n = w.getnchannels(), w.getframerate(), w.getnframes()
    x = np.frombuffer(w.readframes(n), "<i2").reshape(-1, ch).astype(np.float64) / 32768; w.close()
    if ch >= 4:
        y = x[:, 0:2] + 0.7 * x[:, 2:4]
    elif ch == 2:
        y = x
    else:
        y = np.repeat(x[:, :1], 2, 1)
    if sr != 48000:
        raise SystemExit("unexpected rate %d for %s" % (sr, name))
    return trim(y, sr), sr


def trim(y, sr):
    """cut the near-silent head and tail of a chunk (moods ring out into 3-8 s of silence: a gap in a chained track)"""
    w = sr // 4
    m = y.mean(1)
    e = np.array([np.sqrt((m[i:i + w] ** 2).mean()) for i in range(0, len(m) - w + 1, w)]) + 1e-12
    on = np.nonzero(20 * np.log10(e / e.max()) > -36)[0]
    if not len(on):
        return y
    a, b = on[0] * w, min(len(y), (on[-1] + 2) * w)
    return y[a:b]


def chain(parts, sr):
    out = parts[0]
    x = int(XF * sr)
    for p in parts[1:]:
        k = min(x, len(out) // 2, len(p) // 2)
        r = np.linspace(0, 1, k)[:, None]
        out = np.concatenate([out[:-k], out[-k:] * np.sqrt(1 - r) + p[:k] * np.sqrt(r), p[k:]])
    return out


def lufs(path):
    r = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-i", path, "-af", "ebur128", "-f", "null", "-"], capture_output=True, text=True)
    m = re.findall(r"I:\s+(-?[\d.]+) LUFS", r.stderr)
    return float(m[-1])


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--wav"); ap.add_argument("--only")
    a = ap.parse_args()
    vgm = os.environ.get("T2R_VGMSTREAM") or speech_dur.vgm()
    d, ent, bs, bsz = dsar_list.open_files(PSARC)
    os.makedirs(OUT, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=os.environ.get("T2R_TMP")) as tmp:
        for name, srcs in SETS.items():
            if a.only and a.only not in name:
                continue
            parts, sr = [], 48000
            for s in srcs:
                y, sr = decode(d, ent, bs, bsz, s, tmp, vgm)
                parts.append(y)
                print("  %-60s %6.1f s" % (s, len(y) / sr))
            y = chain(parts, sr)
            if len(y) > MAX_S * sr:
                y = y[:int(MAX_S * sr)]
            fi, fo = int(FADE_IN * sr), int(FADE_OUT * sr)
            y[:fi] *= np.linspace(0, 1, fi)[:, None]; y[-fo:] *= np.linspace(1, 0, fo)[:, None]
            pk = np.abs(y).max()
            if pk > 0.99:
                y *= 0.99 / pk
            wavp = os.path.join(a.wav or tmp, name + ".wav")
            if a.wav:
                os.makedirs(a.wav, exist_ok=True)
            o = wave.open(wavp, "wb"); o.setnchannels(2); o.setsampwidth(2); o.setframerate(sr)
            o.writeframes((np.clip(y, -1, 1) * 32767).astype("<i2").tobytes()); o.close()
            g = LUFS - lufs(wavp)
            dst = os.path.join(OUT, name + ".ogg")
            subprocess.run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-i", wavp, "-af", "volume=%.2fdB,alimiter=limit=0.95:level=false" % g,
                            "-c:a", "libopus", "-b:a", "64k", "-ac", "2", dst], check=True)
            print("%s: %.1f s, gain %+.1f dB -> %.1f LUFS, %d KB" % (name, len(y) / sr, g, lufs(dst), os.path.getsize(dst) // 1024))


if __name__ == "__main__":
    main()
