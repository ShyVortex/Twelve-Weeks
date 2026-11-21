"""Offline preview of the CHOOSE YOUR SIDE intro cinematic + select payoff (tools/ext/choose.c chi_* / chp_*), through widget_preview on the page
choose_widgets / clan_widgets build: black + each line, the logo line, the text out, the camera drop, the UI fading in, the SKIP prompt and its dip, and the
confirm (logo lift / slam, texts out, red chalk mid / end). Timings and camera = choose.c + tools/ext/choose_intro_text.h + choose_deck.h.
The video carries the intro's real audio (choose_intro.pcm LORE / TAG with choose.c's gain envelopes, then the picker music's first track from the UI), and
`audio` writes that mix alone + a level plot of the tracks over the timeline (intro-audio.wav, intro-levels.png).
  python choose_intro_preview.py <extracted widget dir> <out dir> [frames|video|audio|beats|all]"""
import copy, json, math, os, re, subprocess, sys
import numpy as np
from PIL import Image, ImageDraw, ImageFont
import widget_preview as wp
import clan_widgets as cw
import choose_widgets as chw
import choose_preview as cp

ROOT = cp.ROOT
SRC = open(os.path.join(ROOT, "tools", "ext", "choose.c")).read()
HT = open(os.path.join(ROOT, "tools", "ext", "choose_intro_text.h"), encoding="utf-8").read()
HD = open(os.path.join(ROOT, "tools", "ext", "choose_deck.h")).read()


def cdef(name, txt=SRC):
    return float(re.search(r"#define %s \(?(-?[\d.]+)f?" % name, txt).group(1))


DECK_D, DECK_DY, DECK_HEM = cdef("CH_DECK_DEPTH", HD), cdef("CH_DECK_DY", HD), cdef("CH_DECK_HEM", HD)
FPX = 3200.0
Y0 = (2160.0 - DECK_HEM + 80.0) * DECK_D / FPX
LINES = [(int(m.group(2)),) for m in re.finditer(r"\{(NULL|\"[^\n]*?\"), [^\n]*?, (\d+)\},", HT)]
T_IN = [int(x) for x in re.findall(r", (\d+)\},\n", HT.split("CHI_LINE")[1].split("};")[0])]
TEXT_OUT, OUT_MS, FADE = cdef("CHI_TEXT_OUT_MS", HT), cdef("CHI_OUT_MS", HT), cdef("CHI_FADE_MS", HT)
T_DROP = TEXT_OUT + OUT_MS + cdef("CHI_PAUSE_MS")
DROP = cdef("CHI_DROP_MS")
T_UI = T_DROP + DROP - cdef("CHI_UI_LEAD_MS")
UI_IN = cdef("CHI_UI_IN_MS")
CHALK = json.load(open(chw.CHALK_JSON))
BEATS = [(m.group(1), int(m.group(2))) for m in re.finditer(r'\{"([^"]*)", (\d+)\}', HT.split("CHI_BEAT[CHI_BEAT_N] =")[1].split(";")[0])]
LOGO_IN, BEAT_FADE, LOGO_FADE = cdef("CHI_LOGO_IN_MS", HT), cdef("CHI_BEAT_FADE_MS", HT), cdef("CHI_LOGO_FADE_MS", HT)
LOGO_K = len(T_IN) - 1                                   # (the logo line is the last line)
T_TAG = LOGO_IN - cdef("CHI_TAG_LEAD_MS")
T_TAG_OUT = T_UI - cdef("CHI_TAG_END_GAP") - cdef("CHI_TAG_OUT_MS")


def ease(u):
    u = min(max(u, 0.0), 1.0)
    return u * u * (3 - 2 * u)


def cam_y(el):
    if el < T_DROP:
        return Y0
    u = (el - T_DROP) / DROP
    return 0.0 if u >= 1 else Y0 * (1 - u) ** 3


def kids(p, name):
    g = next(i for i in p["items"] if i["name"] == name)["guid"]
    return [i for i in p["items"] if i.get("parent") == g]


def intro(page, el, skippable=False, skip_dip=None, jumped=False):
    """the page at intro time el (ms); skip_dip = the black's alpha of a skip"""
    t = el / 1000.0
    p = cp.state(page, focus=-1, t=t)
    by = {i["name"]: i for i in p["items"]}
    Yc = 0.0 if jumped else cam_y(el)
    hem = DECK_HEM + FPX * Yc / DECK_D
    for i in range(5):
        it = by["chL%d" % i]
        off = FPX * Yc / cp.DEPTH[i]
        if off > hem:
            off = max(hem, 0.0)
        it["pivotAs.y"] += off
    d = by["chDeck"]
    if Yc > 0 or (not jumped and el < T_UI + UI_IN):
        X = 0.10 * math.sin(t * 0.23) + 0.04 * math.sin(t * 0.61); A = 0.10 * math.sin(t * 0.17); Y = 0.035 * math.sin(t * 0.19)
        dd = max(DECK_D - A, 0.3); sgd = DECK_D / dd
        dfig = max(cp.DEPTH[1] - A, 0.6); sgf = cp.DEPTH[1] / dfig
        S = sgd / sgf
        d["visible"] = 1
        d["rectSizeDelta.width"] = 5120.0 * S; d["rectSizeDelta.height"] = 2808.0 * S
        d["pivotAs.x"] = 1920.0 + (-FPX * X / dd + FPX * X / dfig) / sgf
        d["pivotAs.y"] = 1080.0 + (FPX * Y / dd - FPX * Y / dfig) / sgf + DECK_DY * S + FPX * Yc / DECK_D
    ua = ease((el - T_UI) / UI_IN) if el >= T_UI else 0.0
    by["chUi"]["color.a"] = int(255 * ua)
    by["chIntro"]["visible"] = 1
    out = 1.0 if el < TEXT_OUT else 1.0 - ease((el - TEXT_OUT) / OUT_MS)
    for k in range(chw.INTRO_MAX):
        sl = by["chIntroL%d" % k]
        if k >= len(T_IN) or jumped:
            sl["visible"] = 0
            continue
        if k != LOGO_K:
            sl["color.a"] = int(255 * ease((el - T_IN[k]) / FADE) * out)
            continue
        sl["color.a"] = int(255 * out) if el >= T_IN[k] else 0              # the logo line: each word, then the logo + tail, its own fade
        ch = {i["name"]: i for i in kids(p, "chIntroL%d" % k)}
        for j, (_, bt) in enumerate(BEATS):
            ch["b%d" % j]["color.a"] = int(255 * ease((el - bt) / BEAT_FADE))
        for n in ("lg", "tl"):
            ch[n]["color.a"] = int(255 * ease((el - LOGO_IN) / LOGO_FADE))
    sk = 0.0 if (not skippable or el >= T_DROP) else ease((el - 800) / 400.0) * (1 - ease((el - (T_DROP - 300)) / 300.0))
    by["chIntroSkip"]["color.a"] = int(255 * sk)
    if skip_dip is not None:
        by["chIntroFade"]["visible"] = 1; by["chIntroFade"]["color.a"] = int(255 * skip_dip)
    return p


def payoff(page, side, el):
    """the confirm at el ms after the select (choose.c chp_tick)"""
    p = cp.state(page, focus=side, zt=1.0, pan=1.0 if side else -1.0)
    by = {i["name"]: i for i in p["items"]}
    pa = 1.0 - ease(el / cdef("CHP_TEXT_MS"))
    LI, SL, SE = cdef("CHP_LIFT_MS"), cdef("CHP_SLAM_MS"), cdef("CHP_SETTLE_MS")
    LK, SQ, RI = cdef("CHP_LIFT_K"), cdef("CHP_SQUASH_K"), cdef("CHP_RISE")
    k_, r_ = 1.0, 0.0
    if el < LI:
        u = el / LI; e = 1 - (1 - u) ** 2; k_, r_ = 1 + LK * e, RI * e
    elif el < LI + SL:
        u = (el - LI) / SL; e = u * u; k_, r_ = 1 + LK - (LK + SQ) * e, RI * (1 - e) - 4 * e
    elif el < LI + SL + SE:
        e = ease((el - LI - SL) / SE); k_, r_ = 1 - SQ * (1 - e), -4 * (1 - e)
    nm = "chLogoS" if side else "chLogoW"
    it = by[nm]
    it["rectSizeDelta.width"] *= k_; it["rectSizeDelta.height"] *= k_
    it["pivotAs.y"] -= r_
    for n in ("chDesc", "chWarn"):
        by[n]["color.a"] = int(by[n]["color.a"] * pa)
    by["chNameS" if side else "chNameW"]["color.a"] = int(by["chNameS" if side else "chNameW"]["color.a"] * pa)
    for n in ("chHint", "chSelIcon", "chSelText", "chHintPad"):
        by[n]["color.a"] = int(255 * pa)
    g = by["chChalk"]
    g["visible"] = 1; g["pivotAs.x"] = cp.LOGO_CX[side ^ 1]
    for k, pc in enumerate(CHALK["groups"]):
        by["chg%d" % k]["color.a"] = int(255 * min(max((el - pc["t0"]) / (pc["t1"] - pc["t0"]), 0.0), 1.0))
    return p


VID_FPS = 24
VID_END = T_UI + UI_IN + 3000                            # through the UI fade-in and the picker music's start
SR = 48000
T_LINE_CY = [float(m.group(1)) for m in re.finditer(r", (\d+\.\d)f, \d+\},", HT.split("CHI_LINE")[1].split("};")[0])]


def smooth(x):
    x = np.clip(x, 0.0, 1.0)
    return x * x * (3 - 2 * x)


def audio_mix(out):
    """the intro's audio as the ext plays it (choose.c chi_audio + ch_music_hold's first track), 48 kHz, with each track's level for the plot"""
    from scipy import signal as sg
    H = open(os.path.join(ROOT, "tools", "ext", "choose_intro.h")).read()
    clips = [tuple(int(v) for v in m) for m in re.findall(r"\{(\d+), (\d+), (\d+)\}", H.split("CHI_CLIP[3] =")[1].split(";")[0])]
    pcm = np.fromfile(os.path.join(ROOT, "tools", "ext", "choose_intro.pcm"), "<i2")
    M = open(os.path.join(ROOT, "tools", "ext", "choose_music.h")).read()
    mrate = int(re.search(r"CHM_RATE (\d+)", M).group(1))
    moff, mn = [int(v) for v in re.search(r"CHM_TRACK\[2\] = \{\{(\d+), (\d+)\}", M).groups()]
    mpcm = np.fromfile(os.path.join(ROOT, "tools", "ext", "choose_music.pcm"), "<i2")

    def st(L, R, rate):
        x = np.stack([L, R], 1).astype(np.float64) / 32768
        return np.stack([sg.resample_poly(x[:, c], SR, rate) for c in (0, 1)], 1) if rate != SR else x

    def clip(i):
        off, n, rate = clips[i]
        return st(pcm[off:off + n], pcm[off + n:off + 2 * n], rate)

    N = int(VID_END / 1000 * SR)
    t = np.arange(N) / SR * 1000.0                       # ms
    lore, tag = clip(0), clip(1)
    pick = st(mpcm[moff:moff + mn], mpcm[moff + mn:moff + 2 * mn], mrate)
    tracks = {}
    g = cdef("CHI_LORE_GAIN") * smooth(t / cdef("CHI_LORE_IN_MS")) * smooth(1 - (t - T_TAG) / cdef("CHI_XFADE_MS"))
    a = np.zeros((N, 2)); k = min(N, len(lore)); a[:k] = lore[:k]; tracks["LORE explore D"] = a * g[:, None]
    g = cdef("CHI_TAG_GAIN") * smooth(1 - (t - T_TAG_OUT) / cdef("CHI_TAG_OUT_MS"))
    a = np.zeros((N, 2)); s0 = int(T_TAG / 1000 * SR); k = min(N - s0, len(tag)); a[s0:s0 + k] = tag[:k]; tracks["TAG unaware endtag 1"] = a * g[:, None]
    g = cdef("CHM_GAIN") * smooth((t - T_UI) / cdef("CHM_FADE_MS"))
    a = np.zeros((N, 2)); s0 = int(T_UI / 1000 * SR); k = min(N - s0, len(pick)); a[s0:s0 + k] = pick[:k]; tracks["picker music (track B)"] = a * g[:, None]
    mix = sum(tracks.values())
    pk = np.abs(mix).max()
    if pk > 0.98:
        mix *= 0.98 / pk
    import wave
    w = wave.open(os.path.join(out, "intro-audio.wav"), "wb"); w.setnchannels(2); w.setsampwidth(2); w.setframerate(SR)
    w.writeframes(np.clip(mix * 32767, -32768, 32767).astype("<i2").tobytes()); w.close()
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    hop = SR // 20
    fig, ax = plt.subplots(figsize=(15, 5.2))
    for (nm, x), col in zip(tracks.items(), ("#5b8def", "#e8833a", "#55b36b")):
        r = np.sqrt(np.convolve((x ** 2).mean(1), np.ones(hop) / hop, "same"))[::hop // 4]
        ax.plot(np.arange(len(r)) * (hop // 4) / SR, 20 * np.log10(r + 1e-6), lw=1.3, color=col, label=nm)
    r = np.sqrt(np.convolve((mix ** 2).mean(1), np.ones(hop) / hop, "same"))[::hop // 4]
    ax.plot(np.arange(len(r)) * (hop // 4) / SR, 20 * np.log10(r + 1e-6), lw=0.7, color="#888", ls="--", label="mix")
    ev = [(ti / 1000, "line %d" % (i + 1)) for i, ti in enumerate(T_IN[:-1])] + [(bt / 1000, w) for w, bt in BEATS] + [(LOGO_IN / 1000, "LOGO")]
    ev += [(TEXT_OUT / 1000, "text out"), (T_DROP / 1000, "drop"), (T_TAG_OUT / 1000, "tag fade")]
    for x, lab in ev:
        ax.axvline(x, color="#bbb", lw=0.6)
        ax.text(x + 0.05, -8, lab, rotation=90, fontsize=7, va="top", color="#555")
    ax.axvspan(T_UI / 1000, (T_UI + UI_IN) / 1000, color="#55b36b", alpha=0.15)
    ax.text(T_UI / 1000 + 0.05, -52, "UI fade-in", fontsize=8, color="#2c7a3e")
    ax.set_xlim(0, VID_END / 1000); ax.set_ylim(-60, -5); ax.set_xlabel("s from the page showing"); ax.set_ylabel("level, dBFS (50 ms RMS, after gain)")
    ax.legend(loc="lower left", fontsize=8); ax.grid(alpha=0.25)
    plt.tight_layout(); plt.savefig(os.path.join(out, "intro-levels.png"), dpi=90)
    print(os.path.join(out, "intro-audio.wav"), os.path.join(out, "intro-levels.png"))


def label(fn, txt):
    im = Image.open(fn).convert("RGB")
    d = ImageDraw.Draw(im)
    f = ImageFont.truetype(wp.FONT, 18)
    d.rectangle([0, im.height - 26, im.width, im.height], fill=(0, 0, 0))
    d.text((8, im.height - 23), txt, font=f, fill=(230, 230, 230))
    im.save(fn)


def main():
    wdir, out = sys.argv[1], sys.argv[2]
    what = sys.argv[3] if len(sys.argv) > 3 else "frames"
    os.makedirs(out, exist_ok=True)
    main_ = json.load(open(os.path.join(wdir, "to1", "main-menu.widget.json"), encoding="utf-8"))
    page = cw.build_side_page(main_)
    shots = []
    if what in ("frames", "all"):
        shots.append(("intro-00-black", intro(page, 700), "0.7 s: black - the tarp, camera %.2f m up" % Y0))
        for k, t in enumerate(T_IN[:-1]):
            shots.append(("intro-%02d-line%d" % (k + 1, k + 1), intro(page, t + FADE + 200), "%.1f s: line %d faded in" % ((t + FADE + 200) / 1000, k + 1)))
        for j, (w, bt) in enumerate(BEATS):
            shots.append(("intro-05-beat%d" % (j + 1), intro(page, bt + BEAT_FADE), "%.2f s: \"%s\" in" % ((bt + BEAT_FADE) / 1000, w)))
        shots.append(("intro-06-logo-beat", intro(page, LOGO_IN + LOGO_FADE), "%.2f s: TWELVE WEEKS. in (end tag from %.2f s, its peak %.2f s)" % ((LOGO_IN + LOGO_FADE) / 1000, T_TAG / 1000, (T_TAG + 1930) / 1000)))
        shots.append(("intro-07-textout", intro(page, TEXT_OUT + OUT_MS * 0.5), "%.1f s: all text fading out" % ((TEXT_OUT + OUT_MS * 0.5) / 1000)))
        for nm, u in (("a", 0.05), ("b", 0.15), ("c", 0.3), ("d", 0.5)):
            el = T_DROP + DROP * u
            shots.append(("intro-08-midpan-%s" % nm, intro(page, el), "%.2f s: the drop, %.0f %% of its time (camera %.2f m up)" % (el / 1000, u * 100, cam_y(el))))
        shots.append(("intro-09-ui-fading-in", intro(page, T_UI + UI_IN * 0.4), "%.1f s: camera settling, the UI fading in" % ((T_UI + UI_IN * 0.4) / 1000)))
        shots.append(("intro-10-overview", intro(page, T_UI + UI_IN + 400), "%.1f s: the overview, UI in" % ((T_UI + UI_IN + 400) / 1000)))
        shots.append(("intro-11-skip-button", intro(page, 3200, skippable=True), "later visits: the SKIP prompt (bottom right) over line 1"))
        shots.append(("intro-12-skip-dip", intro(page, 3500, skippable=True, skip_dip=0.6), "SKIP pressed: the dip to black (300 ms)"))
        shots.append(("intro-13-skip-up", intro(page, T_UI + 250, skippable=True, skip_dip=0.5, jumped=True), "after the dip: back up at the overview, the UI fading in"))
        for nm, el, lab in (("intro-20-pick-lift", 180, "confirm +180 ms: WLF logo at the top of the lift, texts fading out"),
                            ("intro-21-pick-slam", 250, "confirm +250 ms: the slam (squash), NR select hit, chalk starts"),
                            ("intro-22-chalk-mid", 520, "confirm +520 ms: red chalk mid-strike over SERAPHITES, texts out"),
                            ("intro-23-chalk-end", 1000, "confirm +1.0 s: the strike done (the page fades out at +1.48 s)")):
            shots.append((nm, payoff(page, 0, el), lab))
        shots.append(("intro-24-chalk-end-ser", payoff(page, 1, 1000), "Seraphites chosen: the chalk over WLF"))
        for nm, p, lab in shots:
            f = os.path.join(out, nm + ".png")
            wp.render(p, f, scale=0.25)
            label(f, lab)
            print(f, flush=True)
        ims = [Image.open(os.path.join(out, nm + ".png")) for nm, _, _ in shots]
        w, h = ims[0].size
        cols = 4
        sheet = Image.new("RGB", (cols * w, -(-len(ims) // cols) * h), (0, 0, 0))
        for i, im in enumerate(ims):
            sheet.paste(im, ((i % cols) * w, (i // cols) * h))
        sheet.save(os.path.join(out, "intro-contact-sheet.png"))
        print(os.path.join(out, "intro-contact-sheet.png"))
    if what in ("beats", "all"):
        strip = []
        for j, (w, bt) in enumerate(BEATS + [("TWELVE WEEKS.", LOGO_IN)]):
            fd = LOGO_FADE if w == "TWELVE WEEKS." else BEAT_FADE
            for nm, el in (("mid", bt + fd * 0.5), ("in", bt + fd)):
                f = os.path.join(out, "_beat.png")
                wp.render(intro(page, el), f, scale=0.5)
                im = Image.open(f).convert("RGB")
                cy = int(T_LINE_CY[LOGO_K] * 0.5)
                im = im.crop((400, cy - 55, 1520, cy + 55))
                d = ImageDraw.Draw(im)
                d.text((8, 4), "%.2f s  %s %s" % (el / 1000, w, "half" if nm == "mid" else "in"), font=ImageFont.truetype(wp.FONT, 16), fill=(150, 150, 150))
                strip.append(im)
        os.remove(os.path.join(out, "_beat.png"))
        sh = Image.new("RGB", (strip[0].width, sum(i.height for i in strip)), (0, 0, 0))
        y = 0
        for im in strip:
            sh.paste(im, (0, y)); y += im.height
        sh.save(os.path.join(out, "intro-beats-strip.png"))
        print(os.path.join(out, "intro-beats-strip.png"))
    if what in ("audio", "video", "all"):
        audio_mix(out)
    if what in ("video", "all"):
        fdir = os.path.join(out, "intro-video-frames")
        os.makedirs(fdir, exist_ok=True)
        for f in os.listdir(fdir):
            os.remove(os.path.join(fdir, f))
        fps, n = VID_FPS, int(VID_END / 1000 * VID_FPS)
        procs = [subprocess.Popen([sys.executable, os.path.abspath(__file__), wdir, out, "vpart", str(i), "2"]) for i in range(2)]   # two renderers (moderate CPU)
        for pr in procs:
            pr.wait()
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-framerate", str(fps), "-i", os.path.join(fdir, "f%04d.png"), "-i", os.path.join(out, "intro-audio.wav"),
                        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "22", "-c:a", "aac", "-b:a", "192k", "-shortest", os.path.join(out, "intro-preview.mp4")], check=True)
        print(os.path.join(out, "intro-preview.mp4"), "(%d frames at %d fps)" % (n, fps))
    if what == "vpart":
        part, parts = int(sys.argv[4]), int(sys.argv[5])
        fdir = os.path.join(out, "intro-video-frames")
        n = int(VID_END / 1000 * VID_FPS)
        for i in range(part, n, parts):
            wp.render(intro(page, i * 1000.0 / VID_FPS), os.path.join(fdir, "f%04d.png" % i), scale=0.25)
            if i % 48 == part:
                print("video frame", i, "/", n, flush=True)


if __name__ == "__main__":
    main()
