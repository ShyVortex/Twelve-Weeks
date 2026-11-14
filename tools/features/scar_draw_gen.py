"""tools/ext/scar_draw.h: Abby's BACK draw for the Seraphite back holster (tools/models/scar_back_holster.py).

dc_data_patches.patch_holster_draw (build default, T2R_HOLSTER_DRAW) renames every abby-p-holster^X / abby-p-unholster^X answer of the overlay sets
to its abby-p-second-* twin, so every look draws its sidearm from the right hip / thigh holster. A Seraphite's FIRST sidearm now sits in the
back-of-belt holster, whose draw is Abby's first family (abby-p-unholster: the hand goes to the back of the belt). This lists the entries that
patch changed in their answer only ({from, patched to, original to}: all in anim-overlay-player-character-name-abby, one answer per name);
t2r-ext's overlay find hook answers such a hit with the original rename on a Seraphite body's overlay state (scar_draw_answer).

  python scar_draw_gen.py [player-overlays.bin]     (default: the game's re/gamebin/dc1 copy - the file stage_holster_draw patches)"""
import os
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(ROOT, "tools", "part1"))
from dcfile import DcFile, fnv  # noqa: E402

OUT = os.path.join(ROOT, "tools", "ext", "scar_draw.h")


def table(path):
    import p1_carrier
    clips = set(p1_carrier.anims(p1_carrier.load(p1_carrier.game_pak("anim-player-gun-abby"))))
    twin, name = {}, {}
    for n in clips:
        for fam in ("abby-p-holster", "abby-p-unholster"):
            if n.startswith(fam):
                s = "abby-p-second-" + n[len("abby-p-"):]
                if s in clips:
                    twin[fnv(n)] = fnv(s)
                    name[fnv(n)], name[fnv(s)] = n, s
                    for pre in ("p-", "ellie-p-"):           # the names the states ask (for the comments)
                        name[fnv(pre + n[len("abby-p-"):])] = pre + n[len("abby-p-"):]
    d = DcFile(open(path, "rb").read())
    t_set = fnv("anim-overlay-set")
    raw = d.data
    nsym = struct.unpack_from("<I", raw, 0x14)[0]
    base = struct.unpack_from("<Q", raw, 0x18)[0] or 0x28
    rows, seen = {}, set()
    for i in range(nsym):
        o = base + 24 * i
        if d.q(o + 8) != t_set:
            continue
        so = d.q(o + 16)
        if so in seen or not d.is_ptr(so):
            continue
        seen.add(so)
        arr, cnt = d.q(so), d.q(so + 8) & 0xffffffff
        for k in range(cnt):
            e = arr + 0x40 * k
            fr, to = d.q(e), d.q(e + 8)
            if to in twin and fr not in twin and twin[to] != fr:      # = patch_holster_draw's answer-only change
                assert rows.get(fr, to) == to, f"{name.get(fr, hex(fr))}: two answers"
                rows[fr] = to
    assert len(rows) >= 40, f"scar draw: {len(rows)} entries - layout not recognised"
    return [(fr, twin[to], to, name.get(fr, "?"), name[to]) for fr, to in sorted(rows.items(), key=lambda x: name.get(x[0], ""))]


def second_table(path):
    """WLF second sidearm (tools/models/second_holster.py): it sits in Abby's back holster on the back of the belt, so its draw /
    put-away is Abby's FIRST family. The overlay sets answer the slot-two names (p-second-(un)holster^X, ellie-p-second-...) with
    abby-p-second-* (her right hip / thigh holster; patch_holster_draw leaves these entries alone). -> [(from, answer abby-p-second-*, back twin
    abby-p-*, from name, back name)] of every such entry of the ORIGINAL file; t2r-ext answers a hit with the back twin on a WLF body
    (scar_draw_answer)."""
    import p1_carrier
    clips = set(p1_carrier.anims(p1_carrier.load(p1_carrier.game_pak("anim-player-gun-abby"))))
    first, name = {}, {}
    for n in clips:
        for fam in ("abby-p-second-holster", "abby-p-second-unholster"):
            if n.startswith(fam):
                f = "abby-p-" + n[len("abby-p-second-"):]
                if f in clips:
                    first[fnv(n)] = fnv(f)
                    name[fnv(n)], name[fnv(f)] = n, f
                    for pre in ("p-second-", "ellie-p-second-"):
                        name[fnv(pre + n[len("abby-p-second-"):])] = pre + n[len("abby-p-second-"):]
    d = DcFile(open(path, "rb").read())
    t_set = fnv("anim-overlay-set")
    raw = d.data
    nsym = struct.unpack_from("<I", raw, 0x14)[0]
    base = struct.unpack_from("<Q", raw, 0x18)[0] or 0x28
    rows, seen = {}, set()
    for i in range(nsym):
        o = base + 24 * i
        if d.q(o + 8) != t_set:
            continue
        so = d.q(o + 16)
        if so in seen or not d.is_ptr(so):
            continue
        seen.add(so)
        arr, cnt = d.q(so), d.q(so + 8) & 0xffffffff
        for k in range(cnt):
            e = arr + 0x40 * k
            fr, to = d.q(e), d.q(e + 8)
            if to in first and fr not in first and fr != first[to]:
                rows.setdefault((fr, to), first[to])
    assert len(rows) >= 20, f"second draw: {len(rows)} entries - layout not recognised"
    return [(fr, to, bk, name.get(fr, "?"), name[bk]) for (fr, to), bk in sorted(rows.items(), key=lambda x: (name.get(x[0][0], ""), x[0][1]))]


def second_queries(clips):
    """WLF second sidearm, the names the overlay chain does NOT bring to abby-p-second-* (it still used the hip holster draw and holster
    animations instead of the back ones; a dev log showed the El Diablo / revolver asks p-second-holster^X-taurus, which no set answers, so the bare
    Ellie hip clip of that name played, and a weapon set answered p-second-unholster^X with its own hip clip directly). Every slot-two draw /
    put-away name with Abby's back twin abby-p-(un)holster^X: p-second-, ellie-p-second- and their -taurus forms. t2r-ext answers such a query on
    a WLF body with the back twin when the engine has no entry or answers a clip outside this chain. -> [(from sid, back sid, from name, back name)]"""
    out = {}
    for n in sorted(clips):
        for fam in ("holster", "unholster"):
            pre = f"abby-p-{fam}^"
            if not n.startswith(pre):
                continue
            x = n[len(pre):]
            for q in (f"p-second-{fam}^{x}", f"ellie-p-second-{fam}^{x}", f"p-second-{fam}^{x}-taurus", f"ellie-p-second-{fam}^{x}-taurus"):
                out.setdefault(fnv(q), (fnv(n), q, n))
    assert len(out) >= 40, f"second queries: {len(out)} - clip names not recognised"
    return sorted(((k,) + v for k, v in out.items()), key=lambda r: r[0])


RELAXED = ("add", "part", "finish-add", "finish-part", "grab-add", "grab-part")


def misses(clips):
    """The relaxed stand put-away / draw names (p-holster^relaxed-idle-stand-X, p-unholster^relaxed-idle-stand-X): no layer of the MP player's
    stack renames them for the first sidearm (only weapon-tweaks-aim / -crafting / the holster-slot-secondary and the long-gun / bow / throwable
    draw sets list them), so such a lookup misses and the state plays the bare Ellie name. Abby has the back-of-belt twins
    abby-p-(un)holster^idle-stand-relaxed-X; t2r-ext answers a MISS of one of these names on a Seraphite body with that rename.
    -> [(from sid, to sid, from name, to name)]"""
    out = []
    for fam in ("holster", "unholster"):
        for sfx in RELAXED:
            fr, to = f"p-{fam}^relaxed-idle-stand-{sfx}", f"abby-p-{fam}^idle-stand-relaxed-{sfx}"
            if to in clips:
                out.append((fnv(fr), fnv(to), fr, to))
    assert len(out) >= 8, f"scar draw: {len(out)} relaxed twins - clip names not recognised"
    return out


def dev_names(path, clips):
    """sid -> name of every sidearm draw / put-away name the MP overlay sets ask or answer (player-overlays.bin entries with a
    (ellie-|abby-)p-(second-)(un)holster name on either side), Abby's clips and the relaxed names: the dev build's 'scar draw dev:' log"""
    import re
    sys.path.insert(0, os.path.join(ROOT, "tools", "part1"))
    from p1_overlay import sid_names
    sn = sid_names()
    pat = re.compile(r"(^|-)p-(second-)?(un)?holster")
    out = {fnv(c): c for c in clips if pat.search(c)}
    d = DcFile(open(path, "rb").read())
    t_set = fnv("anim-overlay-set")
    raw = d.data
    nsym = struct.unpack_from("<I", raw, 0x14)[0]
    base = struct.unpack_from("<Q", raw, 0x18)[0] or 0x28
    seen = set()
    for i in range(nsym):
        o = base + 24 * i
        if d.q(o + 8) != t_set:
            continue
        so = d.q(o + 16)
        if so in seen or not d.is_ptr(so):
            continue
        seen.add(so)
        arr, cnt = d.q(so), d.q(so + 8) & 0xffffffff
        for k in range(cnt):
            for s in (d.q(arr + 0x40 * k), d.q(arr + 0x40 * k + 8)):
                n = sn.get(s)
                if n and pat.search(n):
                    out[s] = n
    for fam in ("holster", "unholster"):
        for sfx in RELAXED:
            out[fnv(f"p-{fam}^relaxed-idle-stand-{sfx}")] = f"p-{fam}^relaxed-idle-stand-{sfx}"
    return sorted(out.items())


def write(path):
    import p1_carrier
    clips = set(p1_carrier.anims(p1_carrier.load(p1_carrier.game_pak("anim-player-gun-abby"))))
    rows = table(path)
    miss = misses(clips)
    names = dev_names(path, clips)
    lines = ["// generated by tools/features/scar_draw_gen.py - do not edit. {from, patched answer (abby-p-second-*), original answer (abby-p-*)}",
             f"#define T2R_SCAR_DRAW_N {len(rows)}",
             "static const uint64_t SCAR_DRAW_MAP[][3] = {"]
    for fr, pt, ot, fn, on in rows:
        lines.append(f"    {{0x{fr:016x}ull, 0x{pt:016x}ull, 0x{ot:016x}ull}},   // {fn} -> {on}")
    lines.append("};")
    lines += ["// relaxed stand put-away / draw: a MISS of {from} on a Seraphite body is answered with a rename to {to} (Abby's back-of-belt twin)",
              f"#define T2R_SCAR_MISS_N {len(miss)}",
              "static const uint64_t SCAR_MISS_MAP[][2] = {"]
    for fr, to, fn, tn in miss:
        lines.append(f"    {{0x{fr:016x}ull, 0x{to:016x}ull}},   // {fn} -> {tn}")
    lines.append("};")
    sec = second_table(path)
    lines += ["// WLF second sidearm (Abby's back holster): a slot-two answer {from, abby-p-second-*} on a WLF body becomes {back twin abby-p-*}",
              f"#define T2R_SECOND_DRAW_N {len(sec)}",
              "static const uint64_t SECOND_DRAW_MAP[][3] = {"]
    for fr, to, bk, fn, bn in sec:
        lines.append(f"    {{0x{fr:016x}ull, 0x{to:016x}ull, 0x{bk:016x}ull}},   // {fn} -> {bn}")
    lines.append("};")
    sq = second_queries(clips)
    lines += ["// WLF second sidearm: slot-two draw / put-away names -> Abby's back twin (no entry / a clip outside the chain answered; sorted by from)",
              f"#define T2R_SECOND_Q_N {len(sq)}",
              "static const uint64_t SECOND_Q_MAP[][2] = {"]
    for fr, bk, fn, bn in sq:
        lines.append(f"    {{0x{fr:016x}ull, 0x{bk:016x}ull}},   // {fn} -> {bn}")
    lines.append("};")
    lines += ["#ifndef T2R_RELEASE",
              "// dev log 'scar draw dev:' - every sidearm draw / put-away name the overlay sets ask or answer (sorted by sid)",
              f"#define T2R_SCAR_NAMES_N {len(names)}",
              "static const struct { uint64_t sid; const char *name; } SCAR_DRAW_NAMES[] = {"]
    for s, n in names:
        lines.append(f"    {{0x{s:016x}ull, \"{n}\"}},")
    lines += ["};", "#endif"]
    open(OUT, "w", newline="\r\n").write("\n".join(lines) + "\n")
    return len(rows), len(miss), len(names), len(sec)


if __name__ == "__main__":
    src = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, "re", "gamebin", "dc1", "player-overlays.bin")
    if not os.path.exists(src):
        src = os.path.join(ROOT.split(os.sep + ".claude" + os.sep)[0], "re", "gamebin", "dc1", "player-overlays.bin")
    print("%s: %d draw / put-away entries, %d relaxed miss renames, %d dev log names, %d WLF second-sidearm back renames" % ((OUT,) + write(src)))
