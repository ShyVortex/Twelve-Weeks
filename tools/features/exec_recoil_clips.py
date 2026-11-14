"""Scaled copies of TLOU2's additive gun-fire (recoil) clips for the execution recoil (tools/features/exec_recoil_gestures.py).

The stock <gun>-fire-start clips are additive (header flag 2 at +0x20, frame 0 = identity): every written joint row holds a rotation / translation
DELTA. A copy scaled by k is the same motion at k times the amplitude: each rotation is slerped from identity by k (angle * k about the same axis),
each translation is multiplied by k, the scale rows stay. Written with the UC4 clip writer (re/uc4ps4/tools/uc4enc.build_clip) on the same rig
(ellie-skel 0x5abe1b4c, group layout copied from the source clip, float-channel groups copied raw), then into unused additive ellie-rig carrier clips
of actor97/anim-ellie-horse.pak (additive horse-riding clips: no horse in multiplayer; NOT the throw / holster / hit clips, which prone, supine and cover paths of the MP throwables reach - see --refs) with carrier_patch.patch_pool. The ANIM resource keeps the
carrier's name (the clip names in the game are the carrier names) and its additive flag (+4 = 0xa, same as fire-start).

  python tools/features/exec_recoil_clips.py            print per-class peaks (source / scaled) and the carrier sizes
  python tools/features/exec_recoil_clips.py --build OUT.pak   (the game's pak with the carriers patched, decoded back and compared)
"""
import os
import struct
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
UC4 = os.path.join(ROOT, "re", "uc4ps4", "tools")
for p in (HERE, UC4, os.path.join(ROOT, "tools", "models"), os.path.join(ROOT, "tools")):
    if p not in sys.path:
        sys.path.insert(0, p)

GAME = os.environ.get("T2_GAME", "C:/Games/The Last of Us Part II Remastered")
SKEL = os.path.join(UC4, "..", "t2", "ellie-skel.pak")
ADD_FLAG_OFF = 0x20          # clip header u16: 2 = additive


def _slerp_id(q, k):
    """quaternions (..., 4) xyzw scaled toward identity by k (shortest arc)"""
    q = np.where(q[..., 3:4] < 0, -q, q).astype(np.float64)
    w = np.clip(q[..., 3], -1.0, 1.0)
    half = np.arccos(w)
    s = np.sin(half)
    axis = np.where(s[..., None] > 1e-9, q[..., :3] / np.maximum(s[..., None], 1e-9), 0.0)
    h2 = half * k
    out = np.concatenate([axis * np.sin(h2)[..., None], np.cos(h2)[..., None]], axis=-1)
    return out / np.linalg.norm(out, axis=-1, keepdims=True)


def decode_rows(clip):
    """{(group, slot): (scale (F,3), quat (F,4), trans (F,3))} of every written row, frame count"""
    from uc4anim import ClipDecoder
    d = ClipDecoder(clip)
    F = d.nframes
    fr = [d.eval_frame(f) for f in range(F)]
    rows = {}
    for g, a0 in fr[0].items():
        for sl in range(a0.shape[0]):
            if np.isnan(a0[sl, 4]):
                continue
            sc = np.array([fr[f][g][sl, 0:3] for f in range(F)])
            q = np.array([fr[f][g][sl, 4:8] for f in range(F)])
            t = np.array([fr[f][g][sl, 8:11] for f in range(F)])
            assert not (np.isnan(sc).any() or np.isnan(q).any() or np.isnan(t).any()), (g, sl)
            rows[(g, sl)] = (sc, q, t)
    return rows, F


def peaks(clip, names=None):
    """{joint name: max rotation angle from identity (deg)} over the clip (decoded with the engine's own sampler)"""
    from retarget import Target
    tgt = Target(SKEL)
    s = tgt.s
    rows, F = decode_rows(clip)
    out = {}
    for (g, sl), (sc, q, t) in rows.items():
        j = tgt.bm[sum(n for n, _ in tgt.groups[:g]) + sl]
        out[s.names[j]] = float(np.degrees(2 * np.arccos(np.clip(np.abs(q[:, 3]), 0, 1))).max())
    return out


CHAIN = ("clavicle", "shoulder", "elbow", "wrist")


def chain_peak(pk):
    """largest rotation of the arm chain (clavicle, shoulder = upper arm, elbow = forearm, wrist = hand), both sides, fingers excluded"""
    return max([v for k, v in pk.items() if k[:2] in ("l_", "r_") and k[2:] in CHAIN] or [0.0])


def scale_clip(clip, k, const_eps=0.4):
    """the additive clip `clip` at amplitude k (see the module doc); same rig / groups / frame count / fps, flag 2 kept"""
    from uc4enc import build_clip
    from bake_player import ref_layout
    from retarget import Target
    tgt = Target(SKEL)
    assert struct.unpack_from("<I", clip, 4)[0] == tgt.sig, "not an ellie-skel clip"
    assert struct.unpack_from("<H", clip, ADD_FLAG_OFF)[0] == 2, "not an additive clip"
    rows, F = decode_rows(clip)
    _, raw = ref_layout(clip, tgt)
    fps = struct.unpack_from("<f", clip, 0x1c)[0]
    content, const = {}, {}
    for (g, sl), (sc, q, t) in sorted(rows.items()):
        if g in raw:
            continue
        c = const.setdefault(g, dict(prefix=None, tr=[], quat=[]))
        c["tr"].append((sl * 0x30, tuple(float(x) for x in sc[0])))
        qs = _slerp_id(q, k).astype(np.float32)
        ts = (t * k).astype(np.float32)
        # a row that does not move stays a constant op (the 16-bit constant quaternion is exact to ~3e-5)
        if float(np.degrees(2 * np.arcsin(min(1.0, float(np.abs(qs - qs[0]).max())))) ) < const_eps:   # (below const_eps degrees of motion after scaling: held at frame 0)
            c["quat"].append((sl * 0x30 + 0x10, tuple(float(x) for x in qs[0])))
        else:
            content.setdefault(g, {"comps": [], "frames": []})
            content[g]["comps"].append((sl, "q"))
            content[g]["frames"].append(qs)
        if float(np.abs(ts - ts[0]).max()) < 2e-5:
            c["tr"].append((sl * 0x30 + 0x20, tuple(float(x) for x in ts[0])))
        else:
            t4 = np.zeros((F, 4), np.float32)
            t4[:, :3] = ts
            content.setdefault(g, {"comps": [], "frames": []})
            content[g]["comps"].append((sl, "t"))
            content[g]["frames"].append(t4)
    gc = {g: (c["comps"], np.stack(c["frames"], axis=1)) for g, c in content.items()}
    out = bytearray(build_clip(tgt.sig, fps, F, tgt.groups, gc, const=const, raw=raw))
    struct.pack_into("<H", out, ADD_FLAG_OFF, 2)
    return bytes(out)


def game_pak(name):
    """bytes of actor97/<name> from the game's sp-common.psarc"""
    import dsar_list
    d, ent, bs, bsz = dsar_list.open_files(os.path.join(GAME, "build", "pc", "main", "sp-common.psarc"))
    return dsar_list.extract(d, ent, bs, bsz, "actor97/" + name)


def pak_clips(name):
    """{clip name: {...}} of a game anim pak (t2clip.t2_clips needs a file: a temp copy)"""
    import tempfile
    import t2clip
    fd, tmp = tempfile.mkstemp(suffix=".pak")
    os.close(fd)
    try:
        open(tmp, "wb").write(game_pak(name))
        return t2clip.t2_clips(tmp)[1]
    finally:
        os.remove(tmp)


def build(pak_bytes):
    """(new pak bytes, {slot: scaled clip}) : actor97/anim-ellie-horse.pak with the five scaled clips pooled into their (horse-riding) carriers"""
    import exec_recoil_gestures as E
    import carrier_patch
    src = {}
    assign, clips = [], {}
    for name, gdef, part, add, pk, carrier, k in E.SLOTS:
        if pk not in src:
            src[pk] = pak_clips(pk)
        new = scale_clip(src[pk][add]["clip"], k)
        clips[name] = new
        assign.append((carrier, new, None))
    # patch_pool works inside one page of the pak: one call per page (pistol + revolver, bolt + shotgun, auto; see CARRIER_PAGES in the test)
    import ndpak
    import tempfile
    fd, tmp = tempfile.mkstemp(suffix=".pak")
    os.close(fd)
    try:
        open(tmp, "wb").write(pak_bytes)
        pk = ndpak.Pak(tmp)
        page = {x[0]: pk.fix[x[3] + 48 + 8] for x in pk.items if x[1] == "ANIM"}
    finally:
        os.remove(tmp)
    out, total = pak_bytes, 0
    for pg in sorted({page[a[0]] for a in assign}):
        group = [a for a in assign if page[a[0]] == pg]
        out, placed, pool, used = carrier_patch.patch_pool(out, group, freeze_raw=True)
        total += used
        print("exec recoil clips: page %d: %s into %d pool bytes (%d used)" % (pg, ", ".join(a[0] for a in group), pool, used))
    return out, clips


def check(pak_bytes_new, pak_bytes_old, clips):
    """decode every carrier back with the engine's sampler: equals the scaled source; every other ANIM resource's ClipData is untouched. returns max error"""
    import tempfile
    import t2clip
    import exec_recoil_gestures as E

    def load(b):
        fd, tmp = tempfile.mkstemp(suffix=".pak")
        os.close(fd)
        try:
            open(tmp, "wb").write(b)
            return t2clip.t2_clips(tmp)[1]
        finally:
            os.remove(tmp)
    new, old = load(pak_bytes_new), load(pak_bytes_old)
    names = {s[5] for s in E.SLOTS}
    for n, c in old.items():
        if n not in names:
            sz = struct.unpack_from("<I", c["clip"], 8)[0]      # (t2_clips slices 0x10 bytes past the clip: the pool zeroing may touch those)
            assert new[n]["clip"][:sz] == c["clip"][:sz], "carrier patch changed another clip: " + n
    err = 0.0
    for name, gdef, part, add, pk, carrier, k in E.SLOTS:
        got = new[carrier]["clip"]
        assert struct.unpack_from("<H", got, ADD_FLAG_OFF)[0] == 2, carrier
        a, _ = decode_rows(got)
        b, _ = decode_rows(clips[name])
        assert a.keys() == b.keys(), carrier
        for key in a:
            for x, y in zip(a[key], b[key]):
                err = max(err, float(np.abs(x - y).max()))
    return err


def main():
    import exec_recoil_gestures as E
    src = {}
    for cls in E.SLOTS:
        pk = cls[4]
        if pk not in src:
            src[pk] = pak_clips(pk)
    for name, gdef, part, add, pk, carrier, k in E.SLOTS:
        clip = src[pk][add]["clip"]
        new = scale_clip(clip, k)
        p0, p1 = peaks(clip), peaks(new)
        print("%-9s %-40s k=%.2f  arm-chain peak %5.1f -> %4.1f deg, all-joint peak %5.1f -> %4.1f, %d -> %d bytes (carrier %s)" % (
            name, add, k, chain_peak(p0), chain_peak(p1), max(p0.values()), max(p1.values()), len(clip), len(new), carrier))


if __name__ == "__main__":
    if "--build" in sys.argv:
        old = game_pak("anim-ellie-horse.pak")
        new, clips = build(old)
        err = check(new, old, clips)
        open(sys.argv[sys.argv.index("--build") + 1], "wb").write(new)
        print("wrote %d bytes; carriers decode back to the scaled clips, max error %.2e" % (len(new), err))
    else:
        main()
