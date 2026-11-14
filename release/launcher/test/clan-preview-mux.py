"""Frames + sound cues of test/clan-preview.js -> clan-open.mp4 (30 fps, the real cl-*.ogg cues mixed in at the times Snd.fx logged them) and clan-open.gif.

  python -I test/clan-preview-mux.py <clip dir (frames/, frames.json, cues.json)> <out basename without extension> [seconds]
CPU only (PIL + ffmpeg)."""
import json, os, shutil, subprocess, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
SOUNDS = os.path.join(HERE, "..", "assets", "sounds")
clip, base = sys.argv[1], sys.argv[2]
secs = float(sys.argv[3]) if len(sys.argv) > 3 else 8.0
FPS, START, VOL = 30, -0.15, 0.7          # the launcher's default sound volume is 70 %
fr = json.load(open(os.path.join(clip, "frames.json")))
cues = json.load(open(os.path.join(clip, "cues.json")))
frames = [(f["t"] - fr["t0"], os.path.join(clip, "frames", "%05d.jpg" % f["n"])) for f in fr["frames"]]
ff = shutil.which("ffmpeg") or "ffmpeg"
with tempfile.TemporaryDirectory() as t:
    n = int(secs * FPS)
    j = 0
    for k in range(n):
        tk = START + k / FPS
        while j + 1 < len(frames) and frames[j + 1][0] <= tk:
            j += 1
        shutil.copyfile(frames[j][1], os.path.join(t, "f%05d.jpg" % k))
    # audio: every cue delayed to its time, volume = launcher volume x cue gain
    ins, flt, labels = [], [], []
    for i, c in enumerate(c for c in cues if START <= c["at"] < secs):
        f = os.path.join(SOUNDS, c["n"] + ".ogg")
        if not os.path.exists(f):
            continue
        ins += ["-i", f]
        d = max(0, int((c["at"] - START) * 1000))
        flt.append("[%d:a]adelay=%d|%d,volume=%.3f[a%d]" % (len(labels) + 1, d, d, VOL * (c["g"] if c["g"] is not None else 0.5), len(labels)))
        labels.append("[a%d]" % (len(labels)))
    fc = ";".join(flt) + ";" + "".join(labels) + "amix=inputs=%d:normalize=0,alimiter=limit=0.95,apad,atrim=0:%.2f[out]" % (len(labels), secs - START - 0.0)
    mp4 = base + ".mp4"
    subprocess.run([ff, "-y", "-loglevel", "error", "-filter_complex_threads", "1", "-framerate", str(FPS), "-i", os.path.join(t, "f%05d.jpg"), *ins, "-filter_complex", fc, "-map", "0:v", "-map", "[out]",
                    "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "20", "-c:a", "aac", "-b:a", "160k", "-t", "%.2f" % (secs - START), mp4], check=True, stderr=subprocess.PIPE)
    # gif: 15 fps, 960 wide, one palette
    gif = base + ".gif"
    subprocess.run([ff, "-y", "-loglevel", "error", "-filter_complex_threads", "1", "-framerate", str(FPS), "-i", os.path.join(t, "f%05d.jpg"), "-vf", "fps=15,scale=960:-1:flags=lanczos,split[a][b];[a]palettegen=max_colors=128[p];[b][p]paletteuse=dither=bayer:bayer_scale=4",
                    gif], check=True)
print("wrote", mp4, os.path.getsize(mp4) // 1024, "KB;", gif, os.path.getsize(gif) // 1024, "KB;", len(labels), "cues mixed")
