"""Interrogation voice slots (see lines.md): which real TLOU2 enemy take plays in which beat of the interrogation, per faction,
and the three PCM tricks the engine's `say` cannot do (it plays a whole stream):
  tail      the second half of the Seraphite "Damn cowards, where are they?" = "Where are they?" alone (the clause after the comma pause)
  pre+tail  "Easy, friend." / "Hello, friend." followed by that tail = "Easy, friend, where are they?"
  trim      WLF "If you're gonna kill me... get it over with..." without the closing "if you've got the nerve..."
  align     a `say` take whose last word must land on the head smash ("You fuckin' bitch!"): the onset of the last word is stored (VXG_ALIGN, ms from the stream start)
The cut points are found in the decoded English streams (envelope of the voice: the deepest, most prominent silence in the window where the clause boundary must be);
the generator prints every voice's point (cut / tail start / last-word onset) for review. Used by vox_lines.py gen_beg (kinds 8..16 of the vox_beg tables).

Slots (kind): 8 fist demand 1 (starter), 9 victim first line, 10 fist demand 2 (after the slam), 11 victim second line, 12 victim plea cut by the finishing blow,
13 shiv demand, 14 victim shiv answer, 15 interrogator line before the kill swing, 16 interrogator line ON the kill blow."""
import os, re, subprocess, wave
import numpy as np

# (category hint, text, mode, flag). flag 1 = "Fuck you!": first OR second line of one interrogation, never both. mode: '' say, 'tail', 'pre+tail:<cat>|<text>', 'trim', 'align'
EASY = ("mtshld-grbbed-confident", "Easy, friend.")
HELLO = ("grb-plyr-start", "Hello, friend.")
TAIL = ("srch-check-in-frstrtd-mod-awr-plrl", "Damn cowards, where are they?")
SLOTS = {
    # An interrogation needs a QUESTION: the 0a4df980/8313e365 pools had lost "Where are they?!" (starter "Get up, fucker!" / "Hold still!", victim "Get off me, filth!").
    # Now: the interrogator QUESTIONS in every beat (8 starter, 10 after the slam), the victim answers in one short line (9), then a threat before the kill (15); shiv: a question (13) + a refusal (14).
    # Some interrogations open calm in one breath ("Easy, friend... Where are they?" = a prefix take + the question, mode pre+full), others just the question; random per interrogation
    8: {0: [("prst-trgt-gone-plrl-solo", "Where are they?!", "", 0), ("prst-trgt-gone-sp", "Where's the Wolf?!", "", 0), ("invstgt-ally-mssng-reactn-addtnl-solo", "Where are the others?", "", 0),
            EASY + ("pre+full", 0), HELLO + ("pre+full", 0)],
        1: [("prst-trgt-gone-plrl-solo", "Where are they?!", "", 0), ("srch-check-in-frstrtd-mod-awr-plrl", "Where are they hiding?", "", 0), ("srch-check-in-frstrtd-mod-awr-plrl", "Where are they...?", "", 0),
            ("enmy-rspns-confident-1x-sp", "Easy.", "pre+full", 0)]},
    # 2 interrogator + 2 victim lines per fist interrogation: Q1 (8) | the victim's first answer (9: defiant, "Fuck you!") | slam | "Where?!" (10) | the victim's
    # desperate answer (11: "Oh god, wait--!") | the interrogator's heavy grunt on the final smash (an effort event, intvox.c). No threat line (15 dropped).
    # The VICTIM pools are wide and varied (the plain answers were too uniform) - reply 1 (9) defiant curse /
    # insult ("Fuck you..", "Leggo, bitch!"), reply 2 after the slam (11) scared / breaking ("No, please--!", "Oh god, wait--!"); Seraphite equivalents (no "girl" lines: any body can be the
    # interrogator). The prayer lines ("She'll protect me...") are one row of 13 (rare), "Coward!" / "Savage!" two of 18. Full list per beat: re/interrogation-lines-1104.md.
    9: {0: [("mtshld-grbbed-spj", "Get off me, filth!", "", 0), ("mtshld-grbbed-spj", "Hands off, Wolf!", "", 0), ("mtshld-grbbed-spj", "Wretch, let go!", "", 0),
            ("mtshld-grbbed-spj", "Wolf! Let go!", "", 0), ("mtshld-grbbed-spj", "Damn it, let go!", "", 0), ("mtshld-grbbed-spj", "Rotten husk!", "", 0),
            ("mtshld-see-ally-klld", "You coward!", "", 0), ("mtshld-see-ally-klld", "Wretch!", "", 0), ("mtshld-see-ally-klld", "You afraid?", "", 0),
            ("mtshld-see-ally-klld", "You proud?", "", 0), ("mtshld-grbbed-confident", "Filthy Wolf.", "", 0), ("mtshld-grbbed-confident", "You'll die, Wolf.", "", 0),
            ("mtshld-grbbed-confident", "You'll die here.", "", 0), ("mtshld-grbbed-confident", "You're nothing.", "", 0), ("mtshld-grbbed-confident", "You won't escape.", "", 0),
            ("mtshld-grbbed-confident", "Release me.", "", 0), ("mtshld-see-ally-klld", "Coward!", "", 0), ("mtshld-see-ally-klld", "Savage!", "", 0)],
        1: [("mtshld-grbbed-spj", "Fuck you!", "", 1), ("mtshld-grbbed-spj", "Leggo, bitch!", "", 0), ("mtshld-grbbed-spj", "I'll fuck you up!", "", 0),
            ("mtshld-grbbed-spj", "I'll kill you!", "", 0), ("mtshld-grbbed-spj", "Get the fuck off!", "", 0), ("mtshld-grbbed-spj", "Fuckin' get off me!", "", 0),
            ("mtshld-grbbed-spj", "Get the hell off me!", "", 0), ("mtshld-grbbed-spj", "Shit, let go!", "", 0), ("mtshld-see-ally-klld", "Asshole!", "", 0),
            ("mtshld-see-ally-klld", "Motherfucker!", "", 0), ("mtshld-see-ally-klld", "Ahh! Bitch!", "", 0), ("mtshld-grbbed-confident", "Big mistake.", "", 0),
            ("mtshld-grbbed-confident", "Bad move.", "", 0), ("mtshld-grbbed-confident", "This your plan?", "", 0), ("mtshld-grbbed-confident", "Chill the fuck out!", "", 0)]},
    10: {0: [("spot-plyr-qstn", "Where?!", "", 0)],
         1: [("spot-plyr-qstn", "Where?!", "", 0)]},
    11: {0: [("mtshld-grbbed-scared-sp", "No... no...", "", 0), ("mtshld-grbbed-scared-sp", "Don't... just... wait...", "", 0),
             ("mtshld-grbbed-scared-sp", "Don't do this...", "", 0), ("mtshld-grbbed-scared-wh", "No! Not yet.", "", 0),
             ("mtshld-grbbed-scared-sp", "Not yet... not yet...", "", 0), ("take-cvr-solo", "Don't!", "", 0), ("take-cvr-solo", "No, no!", "", 0),
             ("mtshld-grbbed-scared-sp", "You'll regret this...", "", 0), ("mtshld-grbbed-scared-sp", "Damned Wolf...", "", 0),
             ("mtshld-grbbed-scared-wh", "Lend me courage...", "", 0), ("mtshld-grbbed-scared-sp", "Brace me... brace me...", "", 0),
             ("mtshld-grbbed-scared-sp", "Protect me... protect me...", "", 0), ("mtshld-grbbed-scared-wh", "She'll protect me...", "", 0)],
         1: [("last-words-plead", "Oh god, wait--!", "", 0), ("last-words-plead", "No, please--!", "", 0), ("last-words-plead", "Please, no--!", "", 0),
             ("last-words-plead", "Just let me go--!", "", 0), ("last-words-plead", "No, wait--!", "", 0), ("last-words-plead", "Wait, wait--!", "", 0),
             ("last-words-plead", "Wait a second, wait--!", "", 0), ("last-words-plead", "Don't, don't--!", "", 0), ("last-words-plead", "No, no, don't--!", "", 0),
             ("last-words-plead", "Don't do this--!", "", 0), ("mtshld-see-ally-klld", "Wait, just... wait!", "", 0), ("mtshld-see-ally-klld", "Please don't!", "", 0),
             ("mtshld-see-ally-klld", "Ahh, just let me go!", "", 0), ("mtshld-grbbed-scared-wh", "No! Don't!", "", 0),
             ("mtshld-grbbed-scared-wh", "All right, all right, relax!", "", 0), ("mtshld-grbbed-scared-sp", "Please... please...", "", 0)]},
    12: {0: [], 1: []},
    13: {0: [("prst-trgt-gone-solo", "Where's that Wolf?", "", 0), ("invstgt-ally-mssng-reactn-addtnl-solo", "Where are the others?", "", 0), ("srch-check-in-frstrtd-mod-awr-sp", "Where is she hiding...?", "", 0)],
         1: [("srch-reinforcement-unwr-qstn", "Talk to me.", "", 0), ("srch-check-in-frstrtd-mod-awr-sp", "Where is she hiding...?", "", 0)]},
    14: {0: [("mtshld-grbbed-spj", "Get off me, filth!", "", 0), ("mtshld-grbbed-spj", "Hands off, Wolf!", "", 0), ("mtshld-grbbed-spj", "Wretch, let go!", "", 0),
             ("mtshld-grbbed-confident", "You'll die, Wolf.", "", 0), ("mtshld-grbbed-confident", "Release me.", "", 0), ("mtshld-grbbed-scared-sp", "No... no...", "", 0),
             ("mtshld-grbbed-scared-sp", "Don't do this...", "", 0), ("take-cvr-solo", "No, no!", "", 0), ("mtshld-see-ally-klld", "Coward!", "", 0)],
         1: [("mtshld-grbbed-spj", "Fuck you!", "", 1), ("mtshld-grbbed-spj", "Leggo, bitch!", "", 0), ("mtshld-grbbed-spj", "Get the fuck off!", "", 0),
             ("last-words-plead", "No, please--!", "", 0), ("last-words-plead", "Please, no--!", "", 0), ("last-words-plead", "Oh god, wait--!", "", 0),
             ("last-words-plead", "Wait, wait--!", "", 0), ("mtshld-see-ally-klld", "Please don't!", "", 0), ("mtshld-grbbed-scared-wh", "Please don't...", "", 0)]},
    15: {0: [], 1: []},      # The threat before the kill is cut (the finishing blow gets a heavy grunt instead)
    16: {0: [], 1: []}      # Cut (an insult, not an attack); intvox.c ivx_pick skips kind 16
}
KINDS = sorted(SLOTS)


def norm(s):
    s = re.sub(r"\{[^}]*\}", " ", s)      # (the index texts carry stage directions: "{struggling efforts} Please...")
    s = re.sub(r"\s+", " ", s.strip().lower())
    return {"where?": "where?!"}.get(s, s)


def _find(idx, texts, eng, pre, cat, text):
    """stream keys of one voice (prefix pre, e.g. 'scrma') whose category contains cat and whose text is `text`"""
    want = norm(text)
    return [k for k in sorted(idx) if k.startswith(pre + "-gen-") and cat in k and re.search(r"-\d+$", k) and idx[k][0] in eng and norm(texts.get(k, "")) == want]


def keys_for(kind, fi, pre, idx, texts, eng, missing):
    """[(key, mode, flag, prefix_key or None)] of one slot of one voice"""
    out = []
    for row in SLOTS[kind][fi]:
        cat, text, mode, flag = row[0], row[1], row[2], row[3]
        ks = _find(idx, texts, eng, pre, cat, text)
        if not ks:
            missing.append("%s %s kind %d: %s" % (("scr", "mlt")[fi], pre[3:], kind, text)); continue
        pk = None
        if mode == "pre+full":      # row = the PREFIX take (cat, text) + the question "Where are they?!" as a whole take
            pk = ks[0]
            qk = _find(idx, texts, eng, pre, "prst-trgt-gone-plrl-solo", "Where are they?!")
            if not qk:
                missing.append("%s question for %s" % (pre, text)); continue
            ks = qk
        if mode == "pre+tail":
            pk = ks[0]
            tk = _find(idx, texts, eng, pre, TAIL[0], TAIL[1])
            if not tk:
                missing.append("%s tail for %s" % (pre, text)); continue
            ks = tk
        for k in ks[:1]:
            out.append((k, mode.split(":")[0] or "full", flag, pk))
    return out


# ---------------------------------------------------------------- audio
def decode(arc, sid, tmp, vgm):
    d = arc.get(sid)
    src = os.path.join(tmp, sid + ".xvag")
    open(src, "wb").write(d)
    subprocess.run([vgm, "-o", src + ".wav", src], capture_output=True)
    w = wave.open(src + ".wav")
    ch, sr, n = w.getnchannels(), w.getframerate(), w.getnframes()
    x = np.frombuffer(w.readframes(n), "<i2").reshape(-1, ch)[:, 0].astype(np.float64)
    w.close(); os.remove(src + ".wav"); os.remove(src)
    return x, sr


def env_db(x, sr, ms=10):
    win = max(1, int(sr * ms / 1000.0))
    e = np.sqrt(np.convolve(x * x, np.ones(win) / win, "same"))
    return 20 * np.log10(e / (e.max() + 1e-9) + 1e-4)


def active(x, sr):
    e = np.sqrt(np.convolve(x * x, np.ones(int(sr * 0.02)) / int(sr * 0.02), "same"))
    a = np.nonzero(e > 0.05 * e.max())[0]
    return int(a[0]), int(a[-1])


def deepest_dip(x, sr, lo_ms, hi_ms):
    """the most prominent silence between lo_ms and hi_ms: (centre ms, end ms (the voice is back), depth dB, prominence dB)"""
    db = env_db(x, sr)
    hop = int(sr * 0.005)
    d = db[::hop]
    t = np.arange(len(d)) * 5.0
    best = None
    for i in range(2, len(d) - 2):
        if not (lo_ms <= t[i] <= hi_ms) or not (d[i] <= d[i - 1] and d[i] <= d[i + 1]):
            continue
        # prominence: how far the voice rises on both sides within 250 ms
        L = d[max(0, i - 50):i].max() if i > 0 else d[i]
        R = d[i + 1:i + 51].max()
        prom = min(L, R) - d[i]
        if best is None or prom > best[3] + 1e-9:
            j = i
            while j < len(d) - 1 and d[j] < d[i] + 10:
                j += 1
            best = (t[i], t[j], d[i], prom)
    return best


def last_word_onset(x, sr, a_ms, b_ms):
    """onset (ms from the stream start) of the last word of "You fuckin' bitch!": the end of the last silence (>= 40 ms below -26 dB) that leaves at least 280 ms of voice
    (the last word is ~0.3-0.45 s; the later silences inside it are the closures of its t / ch)"""
    db = env_db(x, sr, 8)
    hop = int(sr * 0.005); d = db[::hop]
    lo, hi = int(a_ms / 5.0), int((b_ms - 280.0) / 5.0)
    best = None
    i = lo
    while i < hi:
        if d[i] < -26:
            j = i
            while j < len(d) - 1 and d[j] < -26: j += 1
            if (j - i) * 5 >= 40 and j * 5.0 <= b_ms - 280.0:
                best = j * 5.0
            i = j
        i += 1
    return best


def to_rate(x, sr, rate=24000):
    try:
        from scipy.signal import resample_poly
        from math import gcd
        g = gcd(int(sr), rate)
        y = resample_poly(x, rate // g, int(sr) // g)
    except Exception:
        k = int(sr) // rate
        y = np.convolve(x, np.ones(k) / k, "same")[::k]
    return y


def fade(y, ms, rate):
    n = min(len(y), int(rate * ms / 1000.0))
    y = y.copy()
    if n > 0:
        y[-n:] *= np.linspace(1, 0, n)
    return y


def pcm_for(mode, arc, idx, key, pkey, tmp, vgm, log):
    """int16 24 kHz clip for a tail / pre+tail / trim record, plus the cut evidence string"""
    x, sr = decode(arc, idx[key][0], tmp, vgm)
    a, b = active(x, sr)
    am, bm = a * 1000.0 / sr, b * 1000.0 / sr
    if mode in ("tail", "pre+tail"):
        dip = deepest_dip(x, sr, am + 0.35 * (bm - am), am + 0.75 * (bm - am))
        start = max(int((dip[1] - 25) * sr / 1000.0), 0)
        tail = x[start:min(len(x), b + int(0.03 * sr))]
        ev = "tail from %.0f ms (silence centre %.0f ms, %.0f dB, prominence %.0f dB) of %.0f ms" % (dip[1] - 25, dip[0], dip[2], dip[3], bm)
        if mode == "pre+tail":
            px, psr = decode(arc, idx[pkey][0], tmp, vgm)
            pa, pb = active(px, psr)
            pre = px[max(0, pa - int(0.02 * psr)):pb + int(0.03 * psr)]
            clip = np.concatenate([to_rate(pre, psr), np.zeros(int(24000 * 0.12)), to_rate(tail, sr)])
            ev = "prefix %.0f ms + 120 ms + " % ((pb - pa) * 1000.0 / psr) + ev
        else:
            clip = to_rate(tail, sr)
    elif mode == "pre+full":      # a calm opener, 160 ms, the question (one breath)
        px, psr = decode(arc, idx[pkey][0], tmp, vgm)
        pa, pb = active(px, psr)
        pre = px[max(0, pa - int(0.02 * psr)):pb + int(0.03 * psr)]
        a0 = max(0, a - int(0.02 * sr))
        q = x[a0:min(len(x), b + int(0.03 * sr))]
        clip = fade(np.concatenate([to_rate(pre, psr, FULL_RATE), np.zeros(int(FULL_RATE * 0.16)), to_rate(q, sr, FULL_RATE)]), 25, FULL_RATE)
        ev = "opener %.0f ms + 160 ms + question %.0f ms" % ((pb - pa) * 1000.0 / psr, bm - am)
    elif mode in ("full", "align"):      # Every line is a PCM clip of the decoded English stream (the dialogue system refuses / does not stream most of these categories on a paired body)
        a0 = max(0, a - int(0.02 * sr))
        clip = fade(to_rate(x[a0:min(len(x), b + int(0.03 * sr))], sr, FULL_RATE), 25, FULL_RATE)
        ev = "full take %.0f ms (from %.0f ms)" % (bm - am, a0 * 1000.0 / sr)
    else:      # trim: the last pause before the final clause ("if you've got the nerve" is the last 0.8-1.7 s)
        dip = deepest_dip(x, sr, max(am + 1000.0, bm - 1800.0), bm - 750.0)
        end = int(dip[0] * sr / 1000.0)
        clip = to_rate(x[max(0, a - int(0.02 * sr)):end], sr)
        clip = fade(clip, 40, 24000)
        ev = "cut at %.0f ms (silence centre; %.0f dB, prominence %.0f dB) of %.0f ms" % (dip[0], dip[2], dip[3], bm)
    pk = np.abs(clip).max() + 1e-9
    clip = clip / pk * 0.85 * 32767.0
    return np.clip(clip, -32768, 32767).astype("<i2"), ev


FULL_RATE = 24000


def align_full(arc, idx, key, tmp, vgm):
    """onset of the last word in ms from the START OF THE FULL PCM CLIP (pcm_for 'align': the stream from 20 ms before its first voiced sample)"""
    x, sr = decode(arc, idx[key][0], tmp, vgm)
    a, b = active(x, sr)
    on = last_word_onset(x, sr, a * 1000.0 / sr, b * 1000.0 / sr)
    return (on - max(0, a - int(0.02 * sr)) * 1000.0 / sr) if on else 0


def align_for(arc, idx, key, tmp, vgm):
    x, sr = decode(arc, idx[key][0], tmp, vgm)
    a, b = active(x, sr)
    on = last_word_onset(x, sr, a * 1000.0 / sr, b * 1000.0 / sr)
    return on, b * 1000.0 / sr
