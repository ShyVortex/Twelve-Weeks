"""Frontier Rifle: the NPC Marlin lever-action rechamber (anim-npc-m-lg npc-m-marlin-lever-idle-rechamber--base / --add) baked onto
the TLOU2 player (Ellie rig) as the hunting rifle's rechamber layers (re/factions2013/frontier-rifle.md).

NPC clip layout (decoded with the game's handlers through the emulator, like the Part I bake in p1_anims.py):
  --base  1 frame, the NPC's full aim pose        --add  25 frames @30, ADDITIVE rows over it: arms, fingers, hand props, spine, head
  --gun   25 frames on the rifle-base rig (the lever, played as it is: the same ClipData signature as the player's gun clips)
Convention (measured, npc_add2 check): absolute = base_local * delta (the left palm stays within 3-8 cm of the gun while the
lever is worked; delta * base drifts it 20-30 cm off).

Player layers a lever cycle needs (the hunting rifle's rechamber triple):
  <variant>rechamber-arms   absolute partial layer over the aim pose: arms (stand variants), fingers, hand props
  rechamber-spine           ADDITIVE: root / spine / neck / head / pelvis sway
  rechamber-gun             = the NPC --gun clip (loaded straight from anim-npc-m-lg)
Retarget (per frame, arms layer): the NPC joint's WORLD rotation delta since frame 0 (spine held still: the sway is the additive
clip's) is applied on the hunting rifle's own rechamber pose at its frame 0 (the player's aim pose of that variant), so the layer
starts and ends in the pose the bolt clip does (no pop) and only the lever motion is the NPC's.  Hand props (the gun in the hand):
the NPC's wrist-relative motion since frame 0 on the player's wrist-relative hold.  Rows the NPC has no counterpart for stay at the
bolt clip's frame 0.

  python frontier_anims.py bake      -> tools/features/data/frontier/*.clip + events.json (committed: the build needs no emulator)
"""
import json
import os
import struct
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.dirname(HERE)
ROOT = os.path.dirname(TOOLS)
sys.path[:0] = [HERE, os.path.join(TOOLS, "features"), os.path.join(ROOT, "re", "uc4ps4", "tools")]
import p1_anims  # noqa: E402
import p1_carrier  # noqa: E402
from p1_rig import qmul, qinv, qnorm, qrot, fill, fk  # noqa: E402

DATA = os.path.join(TOOLS, "features", "data", "frontier")
NPC_PAK = "anim-npc-m-lg"
NPC_BASE = "npc-m-marlin-lever-idle-rechamber--base"
NPC_ADD = "npc-m-marlin-lever-idle-rechamber--add"
NPC_SKEL = os.path.join(ROOT, "re", "uc4ps4", "t2", "base-male-skel.pak")
PLAYER_PAK = "anim-player-gun-ellie"
VARIANTS = ("", "blocked-", "blocked-crouch-aim-", "crouch-", "crouch-aim-", "fast-", "prone-", "prone-aim-", "stand-", "stand-relaxed-", "supine-")   # rifle-remington-bolt-<variant>rechamber-arms: every variant the game has
SPINE_ROWS = ["root", "spinea", "spineb", "spinec", "spined", "neck", "heada", "headb", "pelvis"]
BLEND = 6
# 2013 timing (re/clips/f2013ref/measurements.md A, a 1080p reference clip): lever works from N+27 frames @60 = 0.45 s after the shot, gun down .. back
# on target = 40 frames = 0.67 s (tunables)
LEAD_SEC = 0.0
CYCLE_SEC = 1.1
CYCLE_EASE_POW = 1.4
SPINE_SCALE = 0.35          # fraction of the NPC's additive torso sway kept (1.0 = the NPC's: it pitched the player's rifle up)
FPS_OUT = 30.0
STILL = set(SPINE_ROWS)                                      # held at the base pose in the arms layer (the additive clip sways them)
PROPS = ("l_hand_prop", "r_hand_prop")
ATTACH = ("l_hand_prop_attachment", "r_hand_prop_attachment")


def clip_of(pakname, name):
    pk = p1_carrier.game_pak(pakname)
    p = p1_carrier.load(pk)
    base, ca, size, sig = p1_carrier.anims(p)[name]
    return bytes(p.d[ca:ca + size + 0x10])


def _xmul(a, b):
    return qnorm(qmul(a[0], b[0])), a[1] + qrot(a[0], b[1])


def _xinv(a):
    qi = qinv(a[0])
    return qi, -qrot(qi, a[1])


def npc_frames(npc):
    """absolute NPC local rows per frame (F, n, 12): base * delta on every row the additive clip writes (spine rows held)"""
    n = len(npc.names)
    base, _ = p1_anims.decode(clip_of(NPC_PAK, NPC_BASE))
    add, fps = p1_anims.decode(clip_of(NPC_PAK, NPC_ADD))
    b = fill(base[0][:n], npc.bind)
    out = np.repeat(b[None], len(add), axis=0)
    for f in range(len(add)):
        for i in range(n):
            if npc.names[i] in STILL or np.isnan(add[f, i, 4]):
                continue
            out[f, i, 4:8] = qnorm(qmul(b[i, 4:8], add[f, i, 4:8]))
            if not np.isnan(add[f, i, 8]):
                out[f, i, 8:11] = b[i, 8:11] + add[f, i, 8:11]
    # the NPC's last frame is not its first one (the left hand re-grips: fingers up to ~30 deg, wrists 3-4 deg): the player's layer
    # must end where it started (the hunting rifle's layer does), so the last BLEND frames ease back to frame 0
    from p1_rig import slerp
    F = len(out)
    for f in range(F - BLEND, F):
        w = (f - (F - BLEND - 1)) / BLEND
        w = w * w * (3 - 2 * w)                          # smoothstep 0 -> 1, exactly 1 on the last frame
        for i in range(n):
            if np.abs(out[-1, i] - out[0, i]).max() < 1e-6:
                continue
            out[f, i, 4:8] = slerp(out[f, i, 4:8], out[0, i, 4:8], w)
            out[f, i, 8:11] = out[f, i, 8:11] * (1 - w) + out[0, i, 8:11] * w
    return out, add, fps


def _blend_row(a, b, w):
    from p1_rig import slerp
    out = a.copy()
    out[4:8] = slerp(a[4:8], b[4:8], w)
    out[8:11] = a[8:11] * (1 - w) + b[8:11] * w
    return out


def ease_pose(seq, target, frames, head=True):
    """blend the first (head) or last `frames` poses of seq (F, n, 12) toward the pose `target` (n, 12) (smoothstep, exactly the
    target on the last / first frame)"""
    F = len(seq)
    for k in range(frames):
        f = k if head else F - 1 - k
        w = (frames - k) / frames if head else (frames - k) / frames
        w = w * w * (3 - 2 * w)
        for i in range(seq.shape[1]):
            if np.abs(seq[f, i, 4:11] - target[i, 4:11]).max() > 1e-7:
                seq[f, i] = _blend_row(seq[f, i], target[i], w)
    return seq


def retarget_arms(ell, npc, seq, ref_pose, PA, PZ, ease, written, ik=True):
    """seq (F, n, 12): absolute NPC poses (spine still) of the frames to bake; ref_pose (n, 12): the NPC pose the deltas are taken
    from; PA / PZ: the player's anchor pose at the start / end of the layer, `ease` (F,) 0..1 between them.
    -> rows (F, nE, 12), NaN outside `written`.  ik: the left wrist is put where the NPC's is in the GUN frame (relative to its frame
    0) with a two-bone solve on the left arm - the world-delta retarget alone drifted it 11-15 cm off the forend (NPC source: 3-8 cm)."""
    from p1_rig import slerp, from_to
    nE = len(ell.names)
    F = len(seq)
    nq, npos = zip(*[fk(seq[f], npc.parent) for f in range(F)])
    rq, rp = fk(ref_pose, npc.parent)
    out = np.full((F, nE, 12), np.nan)
    common = {n for n in ell.names if n in npc.idx}
    att_e, att_n = ell.idx[ATTACH[1]], npc.idx[ATTACH[1]]
    wset = set(written)
    lsh, lel, lwr = ell.idx["l_shoulder"], ell.idx["l_elbow"], ell.idx["l_wrist"]
    nlw = npc.idx["l_wrist"]

    def chain(f, P0, q0, p0, override):
        Wq, Wp = {}, {}
        rows = np.full((nE, 12), np.nan)
        for e in range(nE):
            n, pe = ell.names[e], ell.parent[e]
            if n in PROPS and n in npc.idx and pe >= 0 and ell.names[pe] in npc.idx:
                # the gun in the hand, in WORLD terms like every other joint (the rifle spun 90 deg when the delta
                # was carried through the wrists' bind axes): rotation = the NPC prop's world delta since the reference pose on
                # the player's anchor; position = the player's wrist + its anchor offset + the NPC's world displacement of the
                # prop relative to ITS wrist
                jw, j = npc.idx[ell.names[pe]], npc.idx[n]
                if pe not in wset:
                    # the layer does not drive this wrist (the aimed variants: the arms follow the aim / IK layers, the gun is held on
                    # the aim line): the prop rows stay exactly the player's hold.  Any prop motion here (the NPC's
                    # in-hand slide, a turn) pitched the whole rifle up 30-45 deg and pulled the left hand off the forend.
                    rows[e, 4:8] = qnorm(qmul(qinv(q0[pe]), q0[e]))
                    rows[e, 8:11] = P0[e, 8:11]
                    Wq[e] = qnorm(qmul(Wq[pe], rows[e, 4:8]))
                    Wp[e] = Wp[pe] + qrot(Wq[pe], P0[e, 8:11])
                    continue
                # wrist driven: the gun in the hand in WORLD terms like every other joint: rotation = the NPC prop's world delta since
                # the reference pose on the player's anchor; position = the player's wrist + its anchor offset + the NPC's world
                # displacement of the prop relative to ITS wrist
                Wq[e] = qnorm(qmul(qmul(nq[f][j], qinv(rq[j])), q0[e]))
                d = (npos[f][j] - npos[f][jw]) - (rp[j] - rp[jw])
                Wp[e] = Wp[pe] + qrot(Wq[pe], qrot(qinv(q0[pe]), p0[e] - p0[pe])) + d
                rows[e, 8:11] = qrot(qinv(Wq[pe]), Wp[e] - Wp[pe])
                rows[e, 4:8] = qnorm(qmul(qinv(Wq[pe]), Wq[e]))
                continue
            if e in override:
                Wq[e] = override[e]
            elif n in common and n not in STILL and n not in ATTACH and n not in PROPS:
                j = npc.idx[n]
                Wq[e] = qnorm(qmul(qmul(nq[f][j], qinv(rq[j])), q0[e]))
            elif pe >= 0:
                Wq[e] = qnorm(qmul(Wq[pe], P0[e, 4:8]))
            else:
                Wq[e] = q0[e]
            if pe >= 0:
                Wp[e] = Wp[pe] + qrot(Wq[pe], P0[e, 8:11])
                rows[e, 4:8] = qnorm(qmul(qinv(Wq[pe]), Wq[e]))
                rows[e, 8:11] = P0[e, 8:11]
            else:
                Wp[e] = P0[e, 8:11]
                rows[e, 4:8] = Wq[e]
                rows[e, 8:11] = P0[e, 8:11]
        return Wq, Wp, rows

    for f in range(F):
        s = float(ease[f])
        s = s * s * (3 - 2 * s)
        P0 = PA.copy()
        for e in range(nE):
            P0[e, 4:8] = slerp(PA[e, 4:8], PZ[e, 4:8], s)
            P0[e, 8:11] = PA[e, 8:11] * (1 - s) + PZ[e, 8:11] * s
        q0, p0 = fk(P0, ell.parent)
        Wq, Wp, rows = chain(f, P0, q0, p0, {})
        if ik:
            # the left wrist in the gun frame: the player's anchor hold + the NPC's displacement since its reference pose
            lwn = qrot(qinv(nq[f][att_n]), npos[f][nlw] - npos[f][att_n])
            lwn0 = qrot(qinv(rq[att_n]), rp[nlw] - rp[att_n])
            lwA = qrot(qinv(q0[att_e]), p0[lwr] - p0[att_e])
            T = Wp[att_e] + qrot(Wq[att_e], lwA + (lwn - lwn0))
            S, E, W = Wp[lsh], Wp[lel], Wp[lwr]
            a, b = np.linalg.norm(E - S), np.linalg.norm(W - E)
            d = np.linalg.norm(T - S)
            d = min(max(d, abs(a - b) + 1e-3), a + b - 1e-3)
            dirv = (T - S) / max(np.linalg.norm(T - S), 1e-9)
            x = (a * a + d * d - b * b) / (2 * a * d)
            pole = (E - S) - dirv * np.dot(E - S, dirv)
            pole = pole / max(np.linalg.norm(pole), 1e-9)
            En = S + dirv * (a * x) + pole * (a * np.sqrt(max(0.0, 1 - x * x)))
            Tn = S + dirv * d
            ov = {}
            ov[lsh] = qnorm(qmul(from_to((E - S) / a, (En - S) / np.linalg.norm(En - S)), Wq[lsh]))
            ov[lel] = qnorm(qmul(from_to((W - E) / b, (Tn - En) / np.linalg.norm(Tn - En)), Wq[lel]))
            Wq, Wp, rows = chain(f, P0, q0, p0, ov)
            retarget_arms.dbg.append((float(np.linalg.norm(Wp[lwr] - T)), float(np.linalg.norm(T - S)), float(a + b)))
        out[f, :, 4:8] = rows[:, 4:8]
        out[f, :, 8:11] = rows[:, 8:11]
        out[f, :, 0:3] = 1.0
    mask = np.full(nE, False)
    mask[written] = True
    out[:, ~mask] = np.nan
    for e in written:                                   # quaternion sign continuity (and against the bind, like p1_anims)
        for f in range(F):
            ref_q = ell.bind[e, 4:8] if f == 0 else out[f - 1, e, 4:8]
            if np.dot(out[f, e, 4:8], ref_q) < 0:
                out[f, e, 4:8] *= -1
        out[:, e, 3] = 0
        out[:, e, 11] = 0
    return out


retarget_arms.dbg = []


def bake_arms(ell, npc, nfr, variant, ik=True):
    """the rechamber arms layer of one stance variant -> (rows (F, nE, 12) with NaN outside the written set, written row indices)"""
    ref, _ = p1_anims.decode(clip_of(PLAYER_PAK, f"rifle-remington-bolt-{variant}rechamber-arms"))
    nE = len(ell.names)
    written = [i for i in range(nE) if not np.isnan(ref[0, i, 4])]
    PA = fill(ref[0][:nE], ell.bind)                     # the player's pose of this variant at the start of the bolt cycle
    PZ = np.where(np.isnan(ref[-1][:nE]), PA, ref[-1][:nE])   # ... and where the bolt cycle leaves it (the stand / crouch cycles
    # END with the gun lowered, not where they began: the engine blends out from there), so the anchor eases from one to the other
    F = len(nfr)
    ease = np.linspace(0.0, 1.0, F)
    return retarget_arms(ell, npc, nfr, nfr[0], PA, PZ, ease, written, ik), written



def sample_rows(arr, pos):
    """arr (F, n, 12) rows (NaN rows stay NaN) sampled at the fractional frames `pos` (len K): quaternions slerped, the rest lerped"""
    from p1_rig import slerp
    F = len(arr)
    out = np.empty((len(pos),) + arr.shape[1:])
    for k, p in enumerate(pos):
        i0 = int(np.clip(np.floor(p), 0, F - 1))
        i1 = min(i0 + 1, F - 1)
        w = float(np.clip(p - i0, 0.0, 1.0))
        a, b = arr[i0], arr[i1]
        out[k] = a * (1 - w) + b * w
        if w > 0 and i1 != i0:
            for j in range(arr.shape[1]):
                if not np.isnan(a[j, 4]) and not np.isnan(b[j, 4]):
                    out[k, j, 4:8] = slerp(a[j, 4:8], b[j, 4:8], w)
    return out


# One time map for the arms, spine and gun layers (the lever must visibly work, slowly, over the fire interval).  The NPC
# cycle is 25 frames, but its lever only moves in native frames 7-16 (down 65 deg at 11); (t seconds, native frame) knots: the hands
# start at the shot, the lever (native 6 -> 17) takes 0.4 .. 0.95 s - after the gun's own 0.47 s fire clip has started to let go - and
# the layers are back on the aim hold at CYCLE_SEC.
TIME_KNOTS = [(0.0, 0.0), (0.8333, 24.0), (1.10, 24.0)]       # the NPC's own speed: the gun layer is the NPC's clip (native timing), the hands match it


def _total_frames():
    return int(round((LEAD_SEC + CYCLE_SEC) * FPS_OUT))


def cycle_positions(n_native):
    """output frame k (30 fps) -> fractional frame of the NPC cycle (TIME_KNOTS); the arms layer always ends on the anchor"""
    t = np.arange(_total_frames()) / FPS_OUT
    kt, kf = zip(*TIME_KNOTS)
    return np.interp(t, kt, kf) * (n_native - 1) / 24.0, np.zeros(len(t))


def gun_positions(n_native):
    return cycle_positions(n_native)[0]


def retime(f):
    """a native NPC-cycle frame -> the output frame (events follow the same map)"""
    kt, kf = zip(*TIME_KNOTS)
    return round(float(np.interp(min(max(f, 0.0), 24.0), kf, kt)) * FPS_OUT, 3)


# ---- reload: the hunting rifle's own start / mid / end clips stay (stance, spine, hands, the single-round inserts); only the GUN layer
# changes: the bolt's "open" (start) and "close" (end) become the lever going down / coming back up.  The NPC
# rechamber gun clip is the lever motion: native frames 0 .. peak = down, peak .. 24 = back up.
RELOAD_SEG_FRAMES = {"start": 44, "mid": 68, "end": 54}      # the bolt reload clips' lengths (the layers must match them)
# stances whose hunting-rifle clips differ in length (measured on the game's anim-player-gun-ellie): stand-relaxed start 55, prone / supine end 51.
# Their gun layer used to be the 44 / 54-frame clip (shorter / longer than the arms layer); each now has its own length.
RELOAD_SEG_ODD = {"start55": ("start", 55), "end51": ("end", 51)}
RELOAD_ODD_STANCE = {("stand-relaxed", "start"): "start55", ("prone", "end"): "end51", ("supine", "end"): "end51"}
RELOAD_OPEN_FRAMES = 18        # start: the lever is down this many frames after the clip starts (the bolt opens at frame 7-14)
RELOAD_CLOSE_FROM = 4            # end: the lever starts back up this late ...
RELOAD_CLOSE_FRAMES = 12         # ... and is closed after this many frames (the bolt closes at frame 8-16)


def bake_reload_gun():
    gun, _ = p1_anims.decode(clip_of(NPC_PAK, "npc-m-marlin-lever-idle-rechamber--gun"))
    lever = 20
    ang = [np.degrees(2 * np.arccos(min(1.0, abs(float(np.dot(gun[f, lever, 4:8], gun[0, lever, 4:8])))))) for f in range(len(gun))]
    peak = int(np.argmax(ang))
    out = {}
    for key, n in list(RELOAD_SEG_FRAMES.items()) + [(k_, v_[1]) for k_, v_ in RELOAD_SEG_ODD.items()]:
        seg = RELOAD_SEG_ODD[key][0] if key in RELOAD_SEG_ODD else key
        k = np.arange(n, dtype=float)
        if seg == "start":
            u = np.clip(k / RELOAD_OPEN_FRAMES, 0, 1)
            pos = peak * (u * u * (3 - 2 * u))
        elif seg == "mid":
            pos = np.full(n, float(peak))
        else:
            u = np.clip((k - RELOAD_CLOSE_FROM) / RELOAD_CLOSE_FRAMES, 0, 1)
            pos = peak + (len(gun) - 1 - peak) * (u * u * (3 - 2 * u))
        rows = sample_rows(gun, pos)
        set_hammer(rows, np.ones(n))        # a lever works with the hammer cocked: the open / close never drops it (the mesh rests cocked)
        clip = p1_anims.encode(rows, FPS_OUT, [(107, 0)], 0xd39433bb, list(range(rows.shape[1])))
        out[key] = (clip, rows, FPS_OUT, False)
    print(f"  reload gun clips: lever peak {max(ang):.1f} deg at native frame {peak}")
    return out


def bake():
    ell = p1_anims.Rig(p1_anims.ELLIE_SKEL)
    npc = p1_anims.Rig(NPC_SKEL)
    nfr, add, fps = npc_frames(npc)
    pos, ease = cycle_positions(len(nfr))
    nfr_w = sample_rows(nfr, pos)
    nE = len(ell.names)
    os.makedirs(DATA, exist_ok=True)
    res = {}
    for v in VARIANTS:
        ref, _ = p1_anims.decode(clip_of(PLAYER_PAK, f"rifle-remington-bolt-{v}rechamber-arms"))
        written = [i for i in range(nE) if not np.isnan(ref[0, i, 4])]
        PA = fill(ref[0][:nE], ell.bind)
        PZ = np.where(np.isnan(ref[-1][:nE]), PA, ref[-1][:nE])
        rows = retarget_arms(ell, npc, nfr_w, nfr[0], PA, PZ, ease, written)
        # the support hand stays on the forend: the NPC's left-hand re-grip (fingers open / close ~30 deg) is not wanted
        for e in written:
            nme = ell.names[e]
            if nme.startswith("l_") and (nme == "l_palm" or any(f in nme for f in ("thumb", "index", "middle", "ring", "pinky"))):
                rows[:, e, 4:11] = PA[e, 4:11]
        clip = p1_anims.encode(rows, FPS_OUT, p1_anims.ELLIE_GROUPS, p1_anims.ELLIE_SIG, written)
        name = f"arms-{(v or 'aim-').rstrip('-')}"
        res[name] = (clip, rows, FPS_OUT, False)
        print(f"  {name}: {len(written)} rows, {len(rows)} frames @{FPS_OUT:g}, {len(clip)} bytes")
    add_w = sample_rows(np.nan_to_num(add, nan=0.0) if False else add, pos)
    rows = np.full((len(pos), nE, 12), np.nan)
    idx = [ell.idx[n] for n in SPINE_ROWS]
    from p1_rig import slerp
    for n in SPINE_ROWS:
        rows[:, ell.idx[n]] = add_w[:, npc.idx[n]]
        for k in range(len(rows)):                      # the NPC's torso sway scaled down: the player keeps the rifle on the aim line
            r = rows[k, ell.idx[n]]
            r[4:8] = slerp(np.array([0.0, 0.0, 0.0, 1.0]), r[4:8], SPINE_SCALE)
            r[8:11] = r[8:11] * SPINE_SCALE
    clip = p1_anims.encode(rows, FPS_OUT, p1_anims.ELLIE_GROUPS, p1_anims.ELLIE_SIG, idx, additive=True)
    res["spine"] = (clip, rows, FPS_OUT, True)
    print(f"  spine: {len(idx)} rows, {len(rows)} frames, {len(clip)} bytes")
    # the lever itself: the NPC gun clip on the same time map (rifle-base rig)
    gun, _ = p1_anims.decode(clip_of(NPC_PAK, "npc-m-marlin-lever-idle-rechamber--gun"))
    gw = sample_rows(gun, gun_positions(len(gun)))
    gclip = p1_anims.encode(gw, FPS_OUT, [(107, 0)], 0xd39433bb, list(range(gw.shape[1])))
    res["gun"] = (gclip, gw, FPS_OUT, False)
    for seg, v in bake_reload_gun().items():
        res[f"rgun-{seg}"] = v
    print(f"  gun: {len(gw)} frames, {len(gclip)} bytes")
    p1_anims.verify(res)
    for name, (clip, *_r) in res.items():
        open(os.path.join(DATA, f"{name}.clip"), "wb").write(clip)
    # anim events: the NPC rechamber's lever sounds (pump-forward 7, pump-back 12, grab 15 of 25 frames) + the engine events of the
    # hunting rifle's rechamber, re-timed to the lever cycle (chambered when the lever is back, abort window at the end)
    frames, npc_ev = p1_carrier.ref_events(p1_carrier.game_pak(NPC_PAK), NPC_ADD)
    ev = [[s, retime(f), [list(x) for x in pr]] for s, f, pr in npc_ev]
    fr_b, bolt_ev = p1_carrier.ref_events(p1_carrier.game_pak(PLAYER_PAK), "rifle-remington-bolt-stand-rechamber-arms")
    fnv = p1_carrier.fnv
    haptic = next(pr for s, f, pr in bolt_ev if s == fnv("haptic-effect"))
    ev.append([fnv("haptic-effect"), retime(12.0), [list(x) for x in haptic]])
    ev.append([fnv("weapon-rechamber"), retime(14.0), []])
    ev.append([fnv("abort-out"), retime(21.0), []])
    json.dump(ev, open(os.path.join(DATA, "events.json"), "w"))
    print(f"events: {len(ev)} ({len(pos)} frames: lead {LEAD_SEC} s + cycle {CYCLE_SEC} s)")


# ---- the lever path: fire-start -> the NPC --add, fire-gun -> the NPC --gun (both play for the whole fire interval).  The NPC clips
# are 25 frames @30 (0.83 s, lever moving only in native frames 7-16); 2013's rechamber takes the whole 1.1 s fire interval with a slow start,
# the lever down ~0.40-0.95 s.  The retimed copies keep the NPC clips' own frame count (25, so the carriers' raw channels stay valid) and
# stretch the time axis instead: fps = 24 / 1.10, output frame k samples the native clip at WEDGE_KNOTS (t = k / fps).
# The time map is built from phases (fast throw down, short hold, fast return, ease-in / ease-out like a real lever cycle), not
# pchip knots.  2013's rechamber (re/clips/f2013ref/measurements.md A): the lever starts 0.45 s after the shot and gun-down .. back-on-target takes
# 0.667 s -> 0.45 + 0.667 = the 1.1 s fire interval.  Native NPC frames: hands reach 0-6, lever throw 7 -> 11 (65 deg at 11), return 11 -> 16, hands settle 16-24.
#   phase      seconds        native frames   easing
#   lead       0    .. 0.45   0    -> 7       smoothstep (the hands come to the lever while the recoil settles)
#   throw      0.45 .. 0.583  7    -> 11      NATIVE speed (fast throw to fully open)
#   hold       0.583 .. 0.833 11   -> 11.4    SLOW drift while fully open: the only stretched part, fills the 2013 cycle exactly
#   return     0.833 .. 0.987 11.4 -> 16     NATIVE speed (fast close)
#   settle     0.987 .. 1.10  16   -> 24      ease-out (hands back on the hold)
# The arms (--add), the lever (--gun) and the sound events all use this one map.
# The levering animation has to be smooth and fast, with little interval between lever down and lever up: the open hold
# was 0.25 s of the cycle; it is now 0.067 s and the time it gave back goes to the recoil settle before the hands reach (the lever-shut moment,
# 0.987 s = shot ready, and the 1.10 s cycle are unchanged; the throw / return keep the NPC's native speed, the upgrades speed all of it up).
# A delay between firing and starting to pull the lever down looked janky: measured on a clip (60 fps), shot flash
# frame 72, the kick settled by 76 (0.07 s) and the lever did not move until ~98-104: a 0.4 s dead gap = the 0.35 s recoil-settle hold below + the slow
# first part of the reach + the arms layer's 5-frame ease in.  The reach now starts at once (the engine's own recoil still plays on the fire clips
# for the first WEDGE_SPLIT 0.183 s, the arms ease in over it) and is one long slow-in / fast-out stroke into the throw (the hand reaches the
# lever, then the lever is thrown at native speed, like the SP bolt / lever cycles that begin out of the recoil); throw / return keep native speed,
# the open hold is 0.10 s; lever shut at 0.987 s (= shot ready) and the 1.10 s cycle are unchanged.
# A pause remained, jagged and unsmooth compared with the hunting rifle: measured on the baked clips played the way the engine does
# (linear between keys, 60 fps): the lever (rifle-base joint 20) sat still for 0.57 s after the shot (native frame 7 = throw start) = the pause, then threw
# 64 deg in 0.133 s = 12.8 deg per 60 fps frame in 3 key steps (the hunting rifle's bolt peaks at 10-13 deg/frame but over 5-6 keys at 30 fps, and its
# clips are 30 fps, ours 21.8).  Now: the throw starts at 0.38 s (hands reach 0.12-0.38), the throw / return are a little slower than the NPC's native
# speed (0.17 s / 0.22 s: 3.7 / 5 keys at the rech clip's 26 fps), the open hold is 0.11 s, the lever is shut by 0.88 s (the shot-ready event stays at
# 0.987 s = 2013's 1.10 s cycle); the rechamber clips are baked straight from the native NPC keys with a cubic (Catmull-Rom) resample at 26.2 fps
# (bake_rech) instead of slicing the 21.8 fps full clips.
WEDGE_PHASES = [(0.0, 0.12, 0.0, 0.5, 1.0),           # first reach: hands leave the hold as the kick settles (slow in)
                (0.12, 0.38, 0.5, 7.0, 1.0),           # reach: hands to the lever, accelerating into the throw
                (0.38, 0.55, 7.0, 11.0, 0.0),          # throw: 4 native frames in 0.17 s
                (0.55, 0.66, 11.0, 11.3, 0.0),         # open hold: short (0.11 s)
                (0.66, 0.88, 11.3, 16.0, 0.0),         # return: 62 -> 0 deg in 0.22 s
                (0.88, 1.10, 16.0, 20.0, 1.0)]         # settle: hands back toward the hold (arms only, lever shut)
WEDGE_SEC = 1.10
WEDGE_FPS = 24.0 / WEDGE_SEC
HAMMER_DROP_SEC = 0.09      # the hammer falls as the lever work begins (cocked at rest -> down), then the lever cocks it again


def _ease(u, k):
    s = u * u * (3 - 2 * u)
    return u * (1 - k) + s * k


def _wedge_spline():
    """C1 monotone Hermite through the WEDGE_PHASES boundary knots (the frontier rifle animations were snappy): the old
    piecewise map was C0 only - every phase boundary was a velocity step (0 -> the full native throw speed of 30 native frames/s, 30 -> 1.6 into the
    hold, 1.6 -> 30 into the return, 70 -> 0 on the settle), which the 21.8 fps clips replay as jerks and the x1.2 / x1.49 upgrade rates sharpen.
    Slopes = the harmonic mean of the neighbouring chord slopes (Fritsch-Carlson, monotone), 0 at both ends; knot times / frames are unchanged."""
    from scipy.interpolate import CubicHermiteSpline
    ts = [WEDGE_PHASES[0][0]] + [p[1] for p in WEDGE_PHASES]
    ns = [WEDGE_PHASES[0][2]] + [p[3] for p in WEDGE_PHASES]
    ch = [(ns[i + 1] - ns[i]) / (ts[i + 1] - ts[i]) for i in range(len(ts) - 1)]
    d = [0.0] + [2 * ch[i] * ch[i + 1] / (ch[i] + ch[i + 1]) for i in range(len(ch) - 1)] + [0.0]
    return CubicHermiteSpline(ts, ns, d)


_WEDGE_SPL = []


def wedge_native_t(t):
    """native NPC-cycle frame (0..24) at time t (seconds after the shot) of the retimed clips (WEDGE_PHASES knots, C1 spline)"""
    if not _WEDGE_SPL:
        _WEDGE_SPL.append(_wedge_spline())
    t = np.clip(np.asarray(t, dtype=float), 0.0, WEDGE_PHASES[-1][1])
    return np.clip(_WEDGE_SPL[0](t), 0.0, 24.0)


def wedge_native(k):
    """native NPC-cycle frame played at output frame k of the retimed clips (t = k / WEDGE_FPS)"""
    return wedge_native_t(np.asarray(k, dtype=float) / WEDGE_FPS)


def wedge_frame(native):
    """a native NPC-cycle frame -> the retimed clips' (fractional) frame (inverse of wedge_native; events follow the same map)"""
    ts = np.arange(0, int(WEDGE_SEC * 4000) + 1) / 4000.0
    nat = wedge_native_t(ts) + ts * 1e-9                 # (strictly increasing for the interpolation: the hold phase is nearly flat)
    return round(float(np.interp(native, nat, ts)) * WEDGE_FPS, 3)


def hammer_state_gun(rows_native, k_out):
    """cocked fraction s (0 = down, 1 = cocked) of the hammer at output frames k_out (the retimed lever clip): the NPC's own cocking by the lever
    (native frames 8-10) plus the fall as the rechamber part begins (the fire clips are the hunting rifle's own again - its recoil, and the dry
    fire the engine derives from them - so the Marlin stays cocked through the shot / a dry click; down within HAMMER_DROP_SEC of WEDGE_SPLIT)"""
    ang = np.array([np.degrees(2 * np.arccos(min(1.0, abs(float(np.dot(rows_native[f, HAMMER, 4:8], rows_native[0, HAMMER, 4:8]))))))
                    for f in range(len(rows_native))])
    s_nat = np.clip(ang / max(ang.max(), 1e-9), 0.0, 1.0)
    pos = wedge_native(k_out)
    s = np.interp(pos, np.arange(len(rows_native)), s_nat)
    u = np.clip((np.asarray(k_out, dtype=float) - WEDGE_SPLIT) / WEDGE_FPS / HAMMER_DROP_SEC, 0.0, 1.0)
    return np.maximum(s, 1.0 - u * u * (3 - 2 * u))


TRIGGER = 17     # rifle-base joint trigger: the NPC's finger holds it pulled (46 deg) for the whole cycle, the player's rests
HAMMER = 21     # rifle-base joint lever_hammer (tools/models/frontier_hammer.py: the mesh rests cocked, the clip rows are re-expressed for it)


def set_hammer(rows, s):
    """rows (K, 107, 12) gun clip: joint 21 = the hammer at cocked fraction s (K,), expressed for the pre-cocked mesh"""
    sys.path.insert(0, os.path.join(TOOLS, "models"))
    import frontier_hammer as fh
    from p1_rig import slerp
    for k in range(len(rows)):
        q = slerp(fh.BIND_Q, fh.COCKED_Q, float(s[k]))
        rows[k, HAMMER, 4:8] = fh.clip_quat(q)
    return rows


def _groups(c):
    nrec = struct.unpack_from("<H", c, 0xc)[0]
    g = [(c[0x30 + 16 * i + 6], c[0x30 + 16 * i + 7]) for i in range(nrec)]
    return g   # (float channels are not re-encoded: the groups keep their float counts, like ELLIE_GROUPS, nothing is written to them)


def retime_clip(name, native_of=None):
    """the NPC clip `name` of anim-npc-m-lg re-encoded on the same rig / groups; output frame k = native frame native_of(k) (None = unchanged)"""
    c = clip_of(NPC_PAK, name)
    rows, fps = p1_anims.decode(c)
    nf = len(rows)
    pos = np.arange(nf, dtype=float) if native_of is None else np.minimum(native_of(np.arange(nf)), nf - 1)
    out = sample_rows(rows, pos)
    if native_of is not None and rows.shape[1] == 107:         # the lever (rifle-base) clip: the hammer rests cocked (frontier_hammer.py)
        set_hammer(out, hammer_state_gun(rows, np.arange(nf)))
        out[:, TRIGGER, 4:8] = out[0, TRIGGER, 4:8]
    written = [i for i in range(rows.shape[1]) if not np.all(np.isnan(rows[:, i, 4]))]
    additive = struct.unpack_from("<H", c, 0x20)[0] == 2
    new = p1_anims.encode(out, fps if native_of is None else WEDGE_FPS, _groups(c), struct.unpack_from("<I", c, 4)[0], written, additive=additive)
    return new, rows, out


def bake_wedge():
    for key, name in (("add", NPC_ADD), ("gun", "npc-m-marlin-lever-idle-rechamber--gun")):
        ident, rows, _ = retime_clip(name)                         # self-test: native timing round-trips through the encoder
        back, _ = p1_anims.decode(ident)
        q = np.nan_to_num(rows[:, :, 4:8]) * np.sign(np.nan_to_num(rows[:, :, 7:8]) + 1e-12)
        qb = np.nan_to_num(back[:, :, 4:8]) * np.sign(np.nan_to_num(back[:, :, 7:8]) + 1e-12)
        err = np.abs(q - qb).max()
        clip, _, out = retime_clip(name, wedge_native)
        open(os.path.join(DATA, f"wedge-{key}.clip"), "wb").write(clip)
        print(f"  wedge-{key}: {len(out)} frames @{WEDGE_FPS:.4f} ({len(out) / WEDGE_FPS:.3f} s), native round-trip max quat error {err:.2e}, {len(clip)} bytes")
    frames, npc_ev = p1_carrier.ref_events(p1_carrier.game_pak(NPC_PAK), NPC_ADD)
    ev = [[s, wedge_frame(f), [list(x) for x in pr]] for s, f, pr in npc_ev]
    json.dump(ev, open(os.path.join(DATA, "wedge-events.json"), "w"))
    print("  events (native frame -> retimed frame / s): " + ", ".join(f"{f:g} -> {wedge_frame(f)} / {wedge_frame(f) / WEDGE_FPS:.3f}" for _, f, _ in npc_ev))
    rech, rev = bake_rech()
    for key in ("add", "gun"):
        open(os.path.join(DATA, f"wedge-{key}-rech.clip"), "wb").write(rech[f"{key}-rech"])
    json.dump(rev, open(os.path.join(DATA, "wedge-events-rech.json"), "w"))
    print(f"  rech clips: {RECH_KEYS} keys @{RECH_FPS:.3f} fps = {(RECH_KEYS - 1) / RECH_FPS:.3f} s; events (frame): " + ", ".join(f"{e_[1]:g}" for e_ in rev))


GATE_SEC = 0.05    # The RechamberWeapon state starts only when the fire clips END (the retimed lever is
                   # on them, WEDGE_SEC 1.10 s), so a gate of the lever-shut time (0.987 s) came ON TOP of it: next shot ready ~2.08 s after the last.
                   # The lever is already shut when the rechamber state begins: the gate only has to hand the state its weapon-rechamber event at once.


def bake_gate():
    """(clip bytes, events [(sid, frame, [])]) of the Frontier's shot-ready gate (there was a 0.5 s gap between the end of the lever action and the
    gunshot).  The engine's RechamberWeapon state ends on the hunting rifle's rechamber-arms events (weapon-rechamber frame 55 of 65 aimed / 30
    stand / 39 prone, abort-out 60) and paces itself by those clips; build_dll nulls every rechamber layer for the Frontier (the fire-clip path puts the lever
    on the fire clips), so the gate lost its lever clock.  This is a motion-free additive (one root-side joint at identity, 25 frames) of GATE_SEC =
    the moment the lever is shut, carrying weapon-rechamber / abort-out at its end, the same for every stance; the rechamber state plays it at
    def +0x2c (FR_LEVER), so the next shot is ready when the lever closes at every upgrade level.  Deterministic, no emulator."""
    ell = p1_anims.Rig(p1_anims.ELLIE_SKEL)
    nE = len(ell.names)
    rows = np.full((25, nE, 12), np.nan)
    r = ell.idx["spinea"]
    rows[:, r, 4:8] = (0.0, 0.0, 0.0, 1.0)
    rows[:, r, 8:11] = 0.0
    fps = 24.0 / GATE_SEC
    clip = p1_anims.encode(rows, fps, p1_anims.ELLIE_GROUPS, p1_anims.ELLIE_SIG, [r], additive=True)
    fnv = p1_carrier.fnv
    return clip, [(fnv("weapon-rechamber"), 23.0, []), (fnv("abort-out"), 23.5, [])]


WEDGE_SPLIT = 4          # output frame (0.183 s) where the contributed clips are cut: before = the shot's recoil on the FIRE clips, after = the lever on the RECHAMBER clips
EASE_FR = 6              # frames (0.18 s) of the additive arms layer's ease back to the aim pose at the end of the rechamber part
EASE_IN = 6              # frames (0.23 s) of its ease in from the aim pose (3 frames put the NPC's 52 deg offset on in 0.14 s, a pop at the hand-off)
LEVER_SHUT = 0.987   # s after the shot: the next shot is ready (2013's 1.10 s cycle; the lever itself is closed at WEDGE_PHASES[4][1] = 0.88 s)


RECH_KEYS = 25                          # keys of a baked rechamber clip (the carriers' own frame count)
T_SPLIT = WEDGE_SPLIT / WEDGE_FPS       # s after the shot where the rechamber layers take over (0.183 s)
RECH_SEC = WEDGE_SEC - T_SPLIT          # 0.917 s: the rechamber part (the ext paces it at def +0x2c: FR_CYC)
RECH_FPS = (RECH_KEYS - 1) / RECH_SEC   # 26.2 fps (the old slice of the 25-key full clip: 20 keys over the same time = 21.8)


def sample_rows_cubic(arr, pos):
    """arr (F, n, 12) sampled at fractional frames `pos` with a Catmull-Rom spline per component (quaternions sign-aligned, renormalised):
    C1 through the NPC's own 30 fps keys, so the 26 fps output has no velocity steps where it crosses the native keys"""
    F = len(arr)
    out = np.empty((len(pos),) + arr.shape[1:])
    for k, p in enumerate(pos):
        i1 = int(np.clip(np.floor(p), 0, F - 1))
        u = float(np.clip(p - i1, 0.0, 1.0))
        idx = [max(i1 - 1, 0), i1, min(i1 + 1, F - 1), min(i1 + 2, F - 1)]
        P = [arr[i].copy() for i in idx]
        for q in (P[0], P[2], P[3]):                                # hemisphere of the segment's start key
            d = np.sum(q[:, 4:8] * P[1][:, 4:8], axis=1)
            q[:, 4:8] *= np.where(d < 0, -1.0, 1.0)[:, None]
        u2, u3 = u * u, u * u * u
        v = 0.5 * ((2 * P[1]) + (-P[0] + P[2]) * u + (2 * P[0] - 5 * P[1] + 4 * P[2] - P[3]) * u2 + (-P[0] + 3 * P[1] - 3 * P[2] + P[3]) * u3)
        n = np.linalg.norm(v[:, 4:8], axis=1, keepdims=True)
        ok = np.isfinite(n) & (n > 1e-9)
        v[:, 4:8] = np.where(ok, v[:, 4:8] / np.where(ok, n, 1.0), v[:, 4:8])
        out[k] = v
    return out


def _smoother(e):
    return e * e * e * (e * (e * 6 - 15) + 10)       # zero velocity AND acceleration at both ends


def bake_rech():
    """-> {'add-rech', 'gun-rech'}: clip bytes, events [(sid, frame, pairs)] of the rechamber part, baked straight from the NPC clips on the
    WEDGE_PHASES time map (t = T_SPLIT + k / RECH_FPS), cubic-resampled; the additive arms layer eases in from identity over EASE_IN keys and
    back over EASE_FR keys (smootherstep)"""
    out = {}
    t = T_SPLIT + np.arange(RECH_KEYS) / RECH_FPS
    pos = wedge_native_t(t)
    for key, name in (("add", NPC_ADD), ("gun", "npc-m-marlin-lever-idle-rechamber--gun")):
        c = clip_of(NPC_PAK, name)
        rows, fps = p1_anims.decode(c)
        r = sample_rows_cubic(rows, pos)
        additive = struct.unpack_from("<H", c, 0x20)[0] == 2
        written = [i for i in range(rows.shape[1]) if not np.all(np.isnan(rows[:, i, 4]))]
        if rows.shape[1] == 107:
            ang = np.array([np.degrees(2 * np.arccos(min(1.0, abs(float(np.dot(rows[f, HAMMER, 4:8], rows[0, HAMMER, 4:8])))))) for f in range(len(rows))])
            s_nat = np.clip(ang / max(ang.max(), 1e-9), 0.0, 1.0)
            sh = np.interp(pos, np.arange(len(rows)), s_nat)
            u = np.clip((t - T_SPLIT) / HAMMER_DROP_SEC, 0.0, 1.0)
            set_hammer(r, np.maximum(sh, 1.0 - u * u * (3 - 2 * u)))
            r[:, TRIGGER, 4:8] = r[0, TRIGGER, 4:8]
        if additive:
            from p1_rig import slerp
            w = np.ones(RECH_KEYS)
            e = np.arange(EASE_IN + 1) / EASE_IN
            w[:EASE_IN + 1] = _smoother(e)
            e = np.arange(EASE_FR + 1) / EASE_FR
            w[RECH_KEYS - 1 - EASE_FR:] = np.minimum(w[RECH_KEYS - 1 - EASE_FR:], _smoother(e)[::-1])
            ident = np.array([0.0, 0.0, 0.0, 1.0])
            for k in range(RECH_KEYS):
                if w[k] >= 1.0:
                    continue
                for j in written:
                    r[k, j, 4:8] = slerp(ident, r[k, j, 4:8], float(w[k]))
                    r[k, j, 8:11] *= w[k]
        out[f"{key}-rech"] = p1_anims.encode(r, RECH_FPS, _groups(c), struct.unpack_from("<I", c, 4)[0], written, additive=additive)
    frames, npc_ev = p1_carrier.ref_events(p1_carrier.game_pak(NPC_PAK), NPC_ADD)
    ev = [[s_, round(float(wedge_frame(f)) / WEDGE_FPS * RECH_FPS - T_SPLIT * RECH_FPS, 3), [list(x) for x in pr]] for s_, f, pr in npc_ev]
    ev = [e_ for e_ in ev if e_[1] >= 0]
    fnv = p1_carrier.fnv
    ev += [[fnv("weapon-rechamber"), round((LEVER_SHUT - T_SPLIT) * RECH_FPS, 3), []], [fnv("abort-out"), round(RECH_KEYS - 1 - 0.5, 3), []]]
    return out, ev


FR_CYC = (1.10, 0.95, 0.80)             # 2013-style lever cycle (s) per upgrade level (the ext's FR_CYC; ROF_IV / the stat bars)


def level_rate(lv):
    """lever rate of level lv: the rechamber part (RECH_SEC) shortens so the whole cycle (T_SPLIT fire part + rechamber) is FR_CYC[lv]"""
    return RECH_SEC / (FR_CYC[lv] - T_SPLIT)


def level_clip(clip, lv):
    """clip bytes played at level_rate(lv): ClipData fps (+0x1c) and frame period (+0x2c) scaled, frames / events untouched (events are in frames, so the
    lever sounds and the weapon-rechamber gate follow)"""
    b = bytearray(clip)
    fps = struct.unpack_from("<f", b, 0x1c)[0] * level_rate(lv)
    struct.pack_into("<f", b, 0x1c, fps)
    struct.pack_into("<f", b, 0x2c, 1.0 / fps)
    return bytes(b)


def split_wedge():
    """Frontier upgrades must apply: the lever is on the RECHAMBER layers, the engine's RechamberWeapon state plays them at def +0x2c
    (the ext's per-level lever rate: FR_CYC) and ends on weapon-rechamber at the shot-ready frame.  The fire clips stay the hunting rifle's own
    (the engine derives the dry fire from their names).  The rechamber clips are bake_rech's committed output (wedge-add-rech.clip /
    wedge-gun-rech.clip / wedge-events-rech.json, no emulator needed).
    Returns {'add-rech','gun-rech': clip bytes}, [] (no fire events), events of add-rech (frames of the rechamber part)."""
    clips = {k: open(os.path.join(DATA, f"wedge-{k}-rech.clip"), "rb").read() for k in ("add", "gun")}
    ev = [(s_, f, [tuple(x) for x in pr]) for s_, f, pr in json.load(open(os.path.join(DATA, "wedge-events-rech.json")))]
    out = {"add-rech": clips["add"], "gun-rech": clips["gun"]}
    for lv in (1, 2):                       # the level clips: the same keys / events, played faster (fps) - the ext answers our own body's lookups with them
        for k in ("add", "gun"):
            out[f"{k}-rech{lv}"] = level_clip(clips[k], lv)
    return out, [], ev


def load_wedge():
    """({'add': clip, 'gun': clip}, events [(sid, frame, [(key, value)])]) of `bake_wedge` (committed data, no emulator)"""
    clips = {k: open(os.path.join(DATA, f"wedge-{k}.clip"), "rb").read() for k in ("add", "gun")}
    ev = [(s, f, [tuple(x) for x in pr]) for s, f, pr in json.load(open(os.path.join(DATA, "wedge-events.json")))]
    return clips, ev


def load():
    """{name: clip bytes}, events [(sid, frame, [(key, value)])] baked by `bake` (committed data, no emulator)"""
    clips = {}
    for v in VARIANTS:
        n = f"arms-{(v or 'aim-').rstrip('-')}"
        clips[n] = open(os.path.join(DATA, n + ".clip"), "rb").read()
    clips["spine"] = open(os.path.join(DATA, "spine.clip"), "rb").read()
    clips["gun"] = open(os.path.join(DATA, "gun.clip"), "rb").read()
    for seg in ("start", "mid", "end", *RELOAD_SEG_ODD):
        clips[f"rgun-{seg}"] = open(os.path.join(DATA, f"rgun-{seg}.clip"), "rb").read()
    ev = [(s, f, [tuple(x) for x in pr]) for s, f, pr in json.load(open(os.path.join(DATA, "events.json")))]
    return clips, ev


EXT_HEADER = os.path.join(TOOLS, "ext", "frontier_lever_built.h")


def write_ext_header(wn):
    """tools/ext/frontier_lever_built.h (generated, not committed): the carrier clip sids per level, [arms / gun][level 0..2]"""
    nl = chr(10)
    fnv = p1_carrier.fnv
    rows = "".join("    {" + ", ".join(f"0x{fnv(wn['wedge|' + k + '-rech' + ('' if lv == 0 else str(lv))]):016x}ULL" for lv in range(3)) + "}," + nl for k in ("add", "gun"))
    names = "".join(f"// {k} level {lv}: {wn['wedge|' + k + '-rech' + ('' if lv == 0 else str(lv))]}" + nl for k in ("add", "gun") for lv in range(3))
    text = ("// generated by tools/part1/frontier_anims.py (build_dll.stage_frontier) - do not edit, do not commit" + nl + names +
            "#define T2R_FRL_N 1" + nl + "static const uint64_t FRL_CAR[2][3] = {" + nl + rows + "};" + nl)
    old = open(EXT_HEADER, encoding="utf-8").read() if os.path.exists(EXT_HEADER) else None
    if old != text:
        open(EXT_HEADER, "w", encoding="utf-8", newline=nl).write(text)
    return text


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "bake":
        bake()
    elif len(sys.argv) > 1 and sys.argv[1] == "wedge":
        bake_wedge()
    elif len(sys.argv) > 1 and sys.argv[1] == "reloadgun":      # only the lever's reload gun layers (rgun-*.clip)
        for seg, (clip, *_r) in bake_reload_gun().items():
            open(os.path.join(DATA, f"rgun-{seg}.clip"), "wb").write(clip)
    else:
        print(__doc__)

