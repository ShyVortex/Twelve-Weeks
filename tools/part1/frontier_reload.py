"""Frontier Rifle reload: the NPC Marlin lever full reload (anim-npc-m-lg npc-m-marlin-lever-idle-reload-full--part / --add / --gun and
the npc-m-crouch-... set, 116 frames @30, five rounds inserted one by one) cut into the start / mid / end clips the hunting rifle's
per-round reload plays (re/factions2013/frontier-rifle.md) and baked onto the player rig, same method as frontier_anims.py (rechamber).

How the game plays a one-round-at-a-time reload (read from the bolt rifle's and the pump's clips): <start>, then <mid> - ONE clip that
holds as many round inserts as the magazine holds, each followed by a `weapon-event reload-one-bullet` that adds a round - cut as
soon as the magazine is full (partial reloads add only the missing rounds; firing / sprinting aborts through the abort-* events of
the clips), then <end>.  So:
  start  NPC frames 0 .. first insert - LEAD       (hand to the ammo pouch: gear-ammo-pull)
  mid    NPC frames first insert - LEAD .. last insert, then the last insert cycle repeated until MID_ROUNDS inserts (the NPC loads 5,
         the level II magazine holds 6); each insert: the NPC's insert-round weapon-effect (sound), a clip-drop haptic, and the
         reload-one-bullet event BULLET_DELAY frames later
  end    NPC frames last insert + BULLET_DELAY .. the end (pump forward / back / grab: the lever closes), abort events at its end
Every clip is a layer of the same global NPC timeline (deltas from NPC frame 0 on the player's stance anchor = the bolt reload's own
pose of that stance), so the three join; mid's last frames ease to end's first, end's last frames back to the anchor (the bolt end
clip ends there too).  Constants below are the tunables (2013 footage: reload timing).

  python frontier_reload.py bake     -> tools/features/data/frontier/reload-*.clip + reload-events.json (committed)
"""
import json
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path[:0] = [HERE]
import frontier_anims as fa  # noqa: E402
import p1_anims  # noqa: E402
import p1_carrier  # noqa: E402
from p1_rig import fill  # noqa: E402

# ---- tunables (frames of the NPC reload, 30 fps; the player clips keep the NPC's timing)
LEAD = 7                 # mid starts this many frames before its first insert
BULLET_DELAY = 5         # reload-one-bullet this many frames after the insert sound (the bolt's: 10)
MID_ROUNDS = 6           # inserts in the mid clip = the largest magazine (level II: 6)
EASE = 6                 # frames of every join / end blend
START_EASE_POW = 1.7     # start clip time ease-in (the NPC swings the gun up in its first 0.4 s: a pop on the player); 1 = the NPC's timing
STANCES = {"stand": "npc-m-marlin-lever-idle-reload-full", "aim": "npc-m-marlin-lever-idle-reload-full",
           "stand-relaxed": "npc-m-marlin-lever-idle-reload-full", "prone": "npc-m-marlin-lever-idle-reload-full",
           "supine": "npc-m-marlin-lever-idle-reload-full",
           "crouch": "npc-m-crouch-marlin-lever-idle-reload-full", "crouch-aim": "npc-m-crouch-marlin-lever-idle-reload-full"}
SEGS = ("start", "mid", "end")
GUN_SIG = 0xd39433bb
GUN_GROUPS = [(107, 0)]


def _clip(name):
    return fa.clip_of(fa.NPC_PAK, name)


def _inserts(prefix):
    """frames of the part clip, its events, the insert-round frames"""
    fnv = p1_carrier.fnv
    frames, ev = p1_carrier.ref_events(p1_carrier.game_pak(fa.NPC_PAK), prefix + "--part")
    ins = sorted(f for s, f, pr in ev if s == fnv("weapon-effect") and any(v == fnv("insert-round") for k, v in pr))
    return frames, ev, ins


def seg_indices(ins, nframes):
    m0 = int(ins[0]) - LEAD
    e0 = int(ins[-1]) + BULLET_DELAY
    cyc = list(range(int(ins[-2]) + 1, int(ins[-1]) + 1))            # one insert cycle (~13 frames)
    mid = list(range(m0, int(ins[-1]) + 1))
    n_extra = max(MID_ROUNDS - len(ins), 0)
    mid += cyc * n_extra
    insert_rel = [int(i) - m0 for i in ins] + [int(ins[-1]) - m0 + len(cyc) * (k + 1) for k in range(n_extra)]
    return {"start": list(range(0, m0)), "mid": mid, "end": list(range(e0, nframes))}, insert_rel, m0, e0


def npc_poses(npc, prefix, b0):
    """absolute NPC local rows (F, n, 12): the part layer's rows over the base pose, spine held; + the additive rows + gun rows"""
    n = len(npc.names)
    part, fps = p1_anims.decode(_clip(prefix + "--part"))
    add, _ = p1_anims.decode(_clip(prefix + "--add"))
    gun, _ = p1_anims.decode(_clip(prefix + "--gun"))
    F = len(part)
    seq = np.repeat(b0[None], F, axis=0)
    for f in range(F):
        for i in range(n):
            if npc.names[i] in fa.STILL or np.isnan(part[f, i, 4]):
                continue
            seq[f, i, 4:8] = part[f, i, 4:8]
            if not np.isnan(part[f, i, 8]):
                seq[f, i, 8:11] = part[f, i, 8:11]
    return seq, add[:, :n], gun, fps


def start_positions(n):
    """NPC frame of every output frame of the start clip: the NPC's 0 .. n-1 with an ease-in"""
    u = np.arange(n) / max(n - 1, 1)
    return (n - 1) * u ** START_EASE_POW


def _ease_add(arr, target, rows, frames):
    """ease the last `frames` additive rows (names `rows`) toward `target` (a per-NPC-row array)"""
    for k in range(frames):
        f = len(arr) - 1 - k
        w = (frames - k) / frames
        w = w * w * (3 - 2 * w)
        for j in rows:
            arr[f, j] = fa._blend_row(np.nan_to_num(arr[f, j]), np.nan_to_num(target[j]), w)


def bake_stance(ell, npc, st, b0, log=print):
    """-> {(seg, kind): (clip bytes, rows, fps, additive)}, {seg: events} for one stance"""
    prefix = STANCES[st]
    nE = len(ell.names)
    seq, add, gun, fps = npc_poses(npc, prefix, b0)
    nf, ev_part, ins = _inserts(prefix)
    idx, insert_rel, m0, e0 = seg_indices(ins, len(seq))
    ref_pose = seq[0]
    # the player's anchor: the bolt reload's own start pose of this stance (its arms clip frame 0), written rows per segment
    bolt = {s: p1_anims.decode(fa.clip_of(fa.PLAYER_PAK, f"ellie-sniper-bolt-reload-{st}-{s}-arms"))[0] for s in SEGS}
    PA = fill(bolt["start"][0][:nE], ell.bind)
    for s in ("mid", "end"):
        PA = np.where(np.isnan(bolt["start"][0][:nE]), np.where(np.isnan(bolt[s][0][:nE]), PA, bolt[s][0][:nE]), PA)
    spine_j = [npc.idx[nm] for nm in fa.SPINE_ROWS]
    out, evs = {}, {}
    for s in SEGS:
        written = [i for i in range(nE) if not np.isnan(bolt[s][0, i, 4])]
        pos = start_positions(len(idx[s])) if s == "start" else None
        sq = fa.sample_rows(seq, pos) if s == "start" else np.array([seq[i] for i in idx[s]])
        if s == "mid":
            fa.ease_pose(sq, seq[e0], EASE, head=False)          # ends on the end clip's first pose
        elif s == "end":
            fa.ease_pose(sq, ref_pose, EASE, head=False)         # back to the aim hold
        rows = fa.retarget_arms(ell, npc, sq, ref_pose, PA, PA, np.zeros(len(sq)), written)
        out[(s, "arms")] = (p1_anims.encode(rows, fps, p1_anims.ELLIE_GROUPS, p1_anims.ELLIE_SIG, written), rows, fps, False)
        # spine: the NPC's additive sway of the same frames
        arr = fa.sample_rows(add, pos) if s == "start" else np.array([add[i] for i in idx[s]])
        if s == "mid":
            _ease_add(arr, add[e0], spine_j, EASE)
        elif s == "end":
            _ease_add(arr, add[0], spine_j, EASE)
        sp = np.full((len(arr), nE, 12), np.nan)
        for nm in fa.SPINE_ROWS:
            sp[:, ell.idx[nm]] = arr[:, npc.idx[nm]]
        sidx = [ell.idx[nm] for nm in fa.SPINE_ROWS]
        out[(s, "spine")] = (p1_anims.encode(sp, fps, p1_anims.ELLIE_GROUPS, p1_anims.ELLIE_SIG, sidx, additive=True), sp, fps, True)
        # gun (rifle-base rig): the NPC gun rows of the same frames, same seams
        g = fa.sample_rows(gun, pos) if s == "start" else np.array([gun[i] for i in idx[s]])
        gt = {"mid": gun[e0], "end": gun[0]}.get(s)
        if gt is not None:
            fa.ease_pose(g, gt, EASE, head=False)
        out[(s, "gun")] = (p1_anims.encode(g, fps, GUN_GROUPS, GUN_SIG, list(range(g.shape[1]))), g, fps, False)
        log(f"  {st} {s}: {len(idx[s])} frames (NPC {idx[s][0]}..{idx[s][-1]}), arms {len(written)} rows")
    # events (frames relative to each clip)
    fnv = p1_carrier.fnv
    pk = p1_carrier.game_pak(fa.PLAYER_PAK)

    def bolt_ev(seg):
        return p1_carrier.ref_events(pk, f"ellie-sniper-bolt-reload-{st}-{seg}-arms")[1]
    npc_fx = [(s_, f, [tuple(x) for x in pr]) for s_, f, pr in ev_part]
    insert_pairs = next(pr for s_, f, pr in npc_fx if s_ == fnv("weapon-effect") and any(v == fnv("insert-round") for k, v in pr))
    haptic_pairs = next(pr for s_, f, pr in bolt_ev("mid") if s_ == fnv("haptic-effect"))
    one_pairs = next(pr for s_, f, pr in bolt_ev("mid") if s_ == fnv("weapon-event"))
    n0 = len(idx["start"])
    evs["start"] = [(s_, round((n0 - 1) * (f / (n0 - 1)) ** (1.0 / START_EASE_POW), 3), pr) for s_, f, pr in npc_fx if f < n0]
    mid = []
    for r in insert_rel:
        mid += [(fnv("weapon-effect"), float(r), list(insert_pairs)), (fnv("haptic-effect"), float(r), list(haptic_pairs)),
                (fnv("weapon-event"), float(r + BULLET_DELAY), list(one_pairs))]
    evs["mid"] = mid
    end = [(s_, f - e0, pr) for s_, f, pr in npc_fx if f >= e0]
    pump_back = next((f - e0 for s_, f, pr in npc_fx if f >= e0 and any(v == fnv("pump-back") for k, v in pr)), 10)
    grab = max(f - e0 for s_, f, pr in npc_fx if f >= e0)
    hap_end = next(pr for s_, f, pr in bolt_ev("end") if s_ == fnv("haptic-effect"))
    end.append((fnv("haptic-effect"), float(pump_back), list(hap_end)))
    idle = {fnv("abort-idle-tense"), fnv("abort-idle-uneasy"), fnv("abort-idle-search"), fnv("abort-idle-unaware")}
    for s_, f, pr in bolt_ev("end"):                       # the bolt end clip's abort windows, re-timed to the lever's
        if s_ == fnv("abort-out"):
            end.append((s_, float(grab), list(pr)))
        elif s_ in idle:
            end.append((s_, float(pump_back), list(pr)))
    evs["end"] = end
    return out, evs


def bake():
    ell = p1_anims.Rig(p1_anims.ELLIE_SKEL)
    npc = p1_anims.Rig(fa.NPC_SKEL)
    base, _ = p1_anims.decode(_clip(fa.NPC_BASE))
    b0 = fill(base[0][:len(npc.names)], npc.bind)
    res, events = {}, {}
    for st in STANCES:
        out, evs = bake_stance(ell, npc, st, b0)
        for (s, kind), v in out.items():
            key = f"{st}-{s}-arms" if kind == "arms" else f"{'crouch' if st.startswith('crouch') else 'stand'}-{s}-{kind}"
            res[key] = v
        for s, e in evs.items():
            events[f"{st}-{s}"] = [[a, b, [list(x) for x in c]] for a, b, c in e]
    p1_anims.verify(res)
    os.makedirs(fa.DATA, exist_ok=True)
    for key, (clip, *_r) in res.items():
        open(os.path.join(fa.DATA, f"reload-{key}.clip"), "wb").write(clip)
    json.dump(events, open(os.path.join(fa.DATA, "reload-events.json"), "w"))
    print(f"reload: {len(res)} clips, events {sum(len(v) for v in events.values())}")


def load():
    """({key: clip bytes}, {'<stance>-<seg>': events}); keys '<stance>-<seg>-arms', '<stand|crouch>-<seg>-spine' / '-gun'"""
    clips = {}
    for f in sorted(os.listdir(fa.DATA)):
        if f.startswith("reload-") and f.endswith(".clip"):
            clips[f[7:-5]] = open(os.path.join(fa.DATA, f), "rb").read()
    ev = {k: [(a, b, [tuple(x) for x in c]) for a, b, c in v]
          for k, v in json.load(open(os.path.join(fa.DATA, "reload-events.json"))).items()}
    return clips, ev


# ---- the reload as shipped: the HUNTING rifle's start / mid / end arms + spine clips with only the RIGHT arm replaced - the right hand
# holds the lever: down (start), down through the inserts (mid), back up (end) - and the lever gun layer (frontier_anims.bake_reload_gun).
# Left arm (ammo pouch, gate), spine, head, events, stance: the bolt reload's own.
RELOAD_STANCES = ("aim", "stand", "stand-relaxed", "crouch", "crouch-aim", "prone", "supine")


def _smooth(x):
    x = min(max(x, 0.0), 1.0)
    return x * x * (3 - 2 * x)


def lever_pos(seg, k, n, peak, last):
    """the NPC lever-cycle frame (0 .. last) the gun layer (frontier_anims.bake_reload_gun) shows at frame k of the segment"""
    if seg == "start":
        return peak * _smooth(k / fa.RELOAD_OPEN_FRAMES)
    if seg == "mid":
        return float(peak)
    return peak + (last - peak) * _smooth((k - fa.RELOAD_CLOSE_FROM) / fa.RELOAD_CLOSE_FRAMES)


START_HOLD = 22          # frames the right hand stays on the lever in the start clip (44 frames)


def right_weight(seg, k, n):
    """0 = the hunting rifle's own right arm (grip / pouch / loading), 1 = the right hand on the lever, for frame k of an n-frame segment"""
    # The right hand stayed stuck to the gun: the bake REPLACED the hunting rifle's right arm by the frozen anchor pose
    # (the gun grip) in every frame - mid and end included, so the hand never left the gun to load the rounds.  Now the bolt reload's own
    # right arm (it leaves the grip, goes to the pouch, loads each round, comes back) is the base in every frame and only this weight puts
    # the hand on the lever: it reaches it while the lever opens (start), lets go for the round inserts (mid), takes it again to close it (end).
    # The hunting rifle's own start / end right hand is the BOLT-handle reach (top right of the receiver), so in start and end the lever
    # pose REPLACES it completely (weight 1 from the first frame: the lever pose at lever position 0 is the grip anchor = the hunting clip's frame 0,
    # no pop); the hunting arm only comes back after the lever is shut (end, once the hunting hand is back on the grip) and for the round loading (mid).
    # On the lever for about half the start clip (the lever is open at frame 18), then a smooth hand-off to the mid clip's FIRST pose (the
    # hunting loading arm; right_base), not to the hunting start arm (that is the bolt reach); end: lever shut at frame 16, off it by frame 30.
    if seg == "start":
        return 1.0 - _smooth((k - START_HOLD) / 14.0)
    if seg == "mid":
        return _smooth((k - (n - 9)) / 8.0)                    # start hands off to this clip's first pose: only the return to the lever at its end
    return 1.0 - _smooth((k - 18) / 12.0)


def lever_target_setup():
    """(marlin loop verts, joints, rifle-base rig, mask of the loop's lowest verts = where the palm holds it) for lever_hand_ik"""
    import frontier_preview as fp
    rb = p1_anims.Rig(fa.os.path.join(fa.ROOT, "re", "models", "rifle-base.pak"))
    gp, gj = fp.marlin()
    loop = gj == 20
    P = gp[loop]
    low = P[:, 1] <= np.percentile(P[:, 1], 30)
    return P, np.full(len(P), 20), rb, low


def lever_hand_ik(ell, rig, setup, lev, PA, gunrows, passes=2):
    """The NPC retarget leaves the right palm ~0.27 m off the Marlin's lever loop (rig / gun mismatch).  Per frame: the right palm is put on
    the loop (its lowest part) as the lever swings, with a two-bone solve on the right arm, and the gun prop rows are re-expressed so the gun's world pose
    is exactly what the retarget gave (only the hand moves).  lev (F, nE, 12) is changed in place (r_shoulder, r_elbow, r_hand_prop rows)."""
    from p1_anim_preview import skin, place
    from p1_rig import fk, qmul, qinv, qrot, qnorm, from_to
    P, J, rb, low = setup
    I = ell.idx
    sh, el, wr, pm, pr = I["r_shoulder"], I["r_elbow"], I["r_wrist"], I["r_palm"], I["r_hand_prop"]
    par = ell.parent

    def turn(loc, j, dq):
        Wq, _ = fk(loc, par)
        pq = Wq[par[j]] if par[j] >= 0 else np.array([0.0, 0.0, 0.0, 1.0])
        loc[j, 4:8] = qnorm(qmul(qinv(pq), qmul(dq, Wq[j])))

    for f in range(len(lev)):
        loc = np.where(np.isnan(lev[f]), PA, lev[f])
        Wq, Wp = fk(loc, par)
        Gq, Gp = Wq[pr].copy(), Wp[pr].copy()                  # the gun's world pose from the retarget: kept
        g = skin(P, J, fill(gunrows[f], rb.bind), rb)
        T = Gp + qrot(Gq, g[low].mean(0))
        for _ in range(passes):
            Wq, Wp = fk(loc, par)
            Wt = Wp[wr] + (T - Wp[pm])
            S, E, W = Wp[sh], Wp[el], Wp[wr]
            a, b = np.linalg.norm(E - S), np.linalg.norm(W - E)
            d = min(max(np.linalg.norm(Wt - S), abs(a - b) + 1e-3), a + b - 1e-3)
            dirv = (Wt - S) / max(np.linalg.norm(Wt - S), 1e-9)
            x = (a * a + d * d - b * b) / (2 * a * d)
            pole = (E - S) - dirv * np.dot(E - S, dirv)
            pole = pole / max(np.linalg.norm(pole), 1e-9)
            En = S + dirv * (a * x) + pole * (a * np.sqrt(max(0.0, 1 - x * x)))
            turn(loc, sh, from_to((E - S) / a, (En - S) / np.linalg.norm(En - S)))
            Wq, Wp = fk(loc, par)
            turn(loc, el, from_to((Wp[wr] - Wp[el]) / np.linalg.norm(Wp[wr] - Wp[el]), (Wt - Wp[el]) / np.linalg.norm(Wt - Wp[el])))
        Wq, Wp = fk(loc, par)
        loc[pr, 4:8] = qnorm(qmul(qinv(Wq[par[pr]]), Gq))
        loc[pr, 8:11] = qrot(qinv(Wq[par[pr]]), Gp - Wp[par[pr]])
        for j in (sh, el, pr):
            lev[f, j, 4:11] = loc[j, 4:11]


def bake_right(stances=None):
    ell = p1_anims.Rig(p1_anims.ELLIE_SKEL)
    npc = p1_anims.Rig(fa.NPC_SKEL)
    nfr, add, fps = fa.npc_frames(npc)
    gun, _ = p1_anims.decode(fa.clip_of(fa.NPC_PAK, "npc-m-marlin-lever-idle-rechamber--gun"))
    ang = [np.degrees(2 * np.arccos(min(1.0, abs(float(np.dot(gun[f, 20, 4:8], gun[0, 20, 4:8])))))) for f in range(len(gun))]
    peak = int(np.argmax(ang))
    last = len(nfr) - 1
    nE = len(ell.names)
    res = {}
    setup = lever_target_setup()
    rg = {k: v[1] for k, v in fa.bake_reload_gun().items()}
    for st in (stances or RELOAD_STANCES):
        bolt = {sg: p1_anims.decode(fa.clip_of(fa.PLAYER_PAK, f"ellie-sniper-bolt-reload-{st}-{sg}-arms"))[0] for sg in SEGS}
        PA = fill(bolt["start"][0][:nE], ell.bind)
        for sg in ("mid", "end"):
            PA = np.where(np.isnan(bolt["start"][0][:nE]), np.where(np.isnan(bolt[sg][0][:nE]), PA, bolt[sg][0][:nE]), PA)
        for sg in SEGS:
            written = [i for i in range(nE) if not np.isnan(bolt[sg][0, i, 4])]
            n = len(bolt[sg])
            # the hand / gun-prop rows on the lever at every lever position the segment passes through (the lever cycle's own frames)
            seq = fa.sample_rows(nfr, np.array([lever_pos(sg, k, n, peak, last) for k in range(n)]))
            lev = fa.retarget_arms(ell, npc, seq, nfr[0], PA, PA, np.zeros(n), written)
            lever_hand_ik(ell, ell, setup, lev, PA, rg[fa.RELOAD_ODD_STANCE.get((st, sg), sg)], passes=2)
            rows = bolt[sg].copy()
            right = [e for e in written if ell.names[e].startswith("r_") and not np.isnan(lev[0, e, 4])]
            for f in range(n):
                w = right_weight(sg, f, n)
                if w <= 0.0 and not (sg == "start" and f >= START_HOLD):
                    continue                                       # exactly the hunting rifle's frame
                for e in right:
                    base = bolt[sg][f, e]
                    if sg == "start" and f >= START_HOLD and not np.isnan(bolt["mid"][0, e, 4]):
                        base = bolt["mid"][0, e]             # past the hold the hand heads for the loading pose, not the bolt reach
                    rows[f, e] = fa._blend_row(base, lev[f, e], w)
                    rows[f, e, 0:3] = 1.0
                    rows[f, e, 3] = rows[f, e, 11] = 0.0
            # quaternion sign continuity along the clip
            for e in right:
                for f in range(1, len(rows)):
                    if np.dot(rows[f, e, 4:8], rows[f - 1, e, 4:8]) < 0:
                        rows[f, e, 4:8] *= -1
            clip = p1_anims.encode(rows, fps, p1_anims.ELLIE_GROUPS, p1_anims.ELLIE_SIG, written)
            res[f"{st}-{sg}"] = (clip, rows, fps, False)
        print(f"  right-arm reload {st}: {sum(len(v[1]) for k, v in res.items() if k.startswith(st + '-'))} frames, {len(right)} right rows")
    p1_anims.verify(res)
    for key, (clip, *_r) in res.items():
        open(os.path.join(fa.DATA, f"rarm-{key}.clip"), "wb").write(clip)
    print(f"reload right arm: {len(res)} clips (lever peak native frame {peak})")


def load_right():
    return {f[5:-5]: open(os.path.join(fa.DATA, f), "rb").read() for f in sorted(os.listdir(fa.DATA)) if f.startswith("rarm-") and f.endswith(".clip")}


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "bake":
        bake()
    elif len(sys.argv) > 1 and sys.argv[1] == "bakeright":
        bake_right(sys.argv[2:] or None)           # optional stance names (one foreground run per stance: each takes a few minutes)
    else:
        print(__doc__)
