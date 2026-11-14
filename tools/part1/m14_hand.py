"""Semi-Auto Rifle (rifle-m14-semi / -supp) right hand: the hunting rifle's stock grip instead of the Vepr's pistol grip (the primary (right / trigger)
hand acted as if holding a pistol grip (Vepr), not a shotgun-style stock. Only the primary hand changes.
Tommy's M14 from SP should have the right hand pose; if not, use the Hunting Rifle's hand pose).

Reference.  The M14's overlay key rifle-tommy-abby-player is SP's Abby-rig Tommy rifle: every grip it plays is Abby's VEPR grip
(rifle-vepr-grip-*: pistol-grip hand).  SP Ellie's own Tommy rifle set (player-specific-weapon-overlays/rifle-tommy.bin) renames no grip, so
it holds on the base long-gun layer's names = the hunting rifle's rifle-remington-bolt-grip-* (plus rifle-tommy-grip-{stand,crouch}-aim-add
for the aim spine) - Tommy's M14 in SP IS held with the hunting rifle's hand.  Every Vepr grip clip has a hunting-rifle twin in
anim-player-gun-shared (same suffix under rifle-bolt-grip- / rifle-remington-bolt-grip-, twin_for); its r_hand_prop + fingers are sampled per
frame at the same normalized time (missing rows: the stance's plain hand pose, e.g. rifle-remington-bolt-grip-stand-aim-hands).
Models: rifle-m14-dark and the hunting rifle (rifle-rembrandt-bolt) share the layout around the root (stock wrist z -12..0 cm, y -4..6, butt at
z -30), the Vepr (rifle-boar) has its pistol grip there (y down to -7 at z -4..4): the hunting rifle's hand-to-gun relation fits the M14 as is.

What changes, per frame of every M14-played clip (only the right hand):
  r_hand_prop          = the hunting rifle's (the hand's place / angle on the gun: aim 30.9 deg off the Vepr's, carry 16-58, crouch 48-51,
                       prone 0 = the same prone hold, fingers only)
  r_wrist / r_elbow / r_shoulder   re-solved (two-bone IK on base-male-skel, bend plane kept) so the gun keeps its world pose: the hand turns
                       around the gun, the gun does not move, the left arm is untouched
  20 right finger rows = the hunting rifle's
Additive aim adds (rifle-vepr-grip-{stand,crouch}-aim-add) are baked by db_hold.py m14 (same rule inside its aim re-solve); this file does the
absolute (replace) clips: the aim -part (props) and the carry / move / transition -arms clips.  t2r-ext answers these names ONLY while the
M14's set is on (the Vepr / Galil / Burst play the same names): db_reload_built.h M14_GATED.

  python m14_hand.py          bake + self-check (decoded back: gun world pose kept < 0.05 cm / 0.05 deg, hand-to-gun = hunting rifle's)
"""
import json
import os
import struct
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.dirname(HERE)
sys.path[:0] = [HERE, os.path.join(TOOLS, "features"), TOOLS]
import db_hold as H  # noqa: E402
import p1_anims  # noqa: E402
import p1_carrier  # noqa: E402
import frontier_anims as fa  # noqa: E402
from p1_rig import qmul, qinv, qrot, qnorm, fk  # noqa: E402

SRC_PAK = "anim-player-gun-abby"
REF_PAK = "anim-player-gun-shared"
MP = "base-male-skel"
DATA = os.path.join(TOOLS, "features", "data", "m14-hand")
FINGERS = ["r_thumba", "r_thumbb", "r_thumbc"] + [f"r_{f}{s}" for f in ("index", "middle", "ring", "pinky") for s in ("_meta", "a", "b", "c")]
# Every absolute Vepr grip clip of anim-player-gun-abby (the M14's set plays them: overlay debug log "all", set rifle-tommy-abby-player on,
# every lookup "no entry" = a plain name the ext can answer) except: additive (the aim adds: db_hold.py m14; blocked / prone-aim adds stay the
# game's), the -ref poses, prop-only, cover (no player cover in MP), land-hard (13-17 KB each, a landing) and horse.
SKIP = ("cover", "land-hard", "horse", "-ref", "prop-only")
# its hunting-rifle twin (anim-player-gun-shared, Ellie): the same suffix under rifle-bolt-grip- / rifle-remington-bolt-grip- ('vepr' ->
# 'remington-bolt' in the carry <-> aim transitions); sampled at the same normalized time per frame
TWIN_EXTRA = {"carry-relaxed-jacket": "rifle-bolt-grip-carry-relaxed", "crouch-idle-arms": "rifle-remington-bolt-grip-crouch-arms",
              "prone-aim-arms-high": "rifle-remington-bolt-grip-prone-hands", "prone-aim-arms-low": "rifle-remington-bolt-grip-prone-hands",
              "r-hand": "rifle-remington-bolt-grip-r-hand"}


def fallback_for(name):
    """the stance's plain right-hand pose (props + fingers) when the twin lacks a row"""
    if "prone" in name or "supine" in name:
        return "rifle-remington-bolt-grip-prone-hands"
    if "crouch" in name:
        return "rifle-remington-bolt-grip-crouch-hands"
    if "aim" in name:
        return "rifle-remington-bolt-grip-stand-aim-hands"
    return "rifle-remington-bolt-grip-carry-hands"


_REF = {}


def _ref_anims():
    if "a" not in _REF:
        _REF["a"] = p1_carrier.anims(p1_carrier.load(p1_carrier.game_pak(REF_PAK)))
    return _REF["a"]


def twin_for(name):
    s = name[len("rifle-vepr-grip-"):]
    a = _ref_anims()
    for c in ([TWIN_EXTRA[s]] if s in TWIN_EXTRA else []) + [p + s.replace("vepr-", "remington-bolt-") for p in ("rifle-bolt-grip-", "rifle-remington-bolt-grip-")]:
        if c in a:
            return c
    return fallback_for(name)


# 13 of the Vepr grip clips are authored on ellie-skel (sig 0x5abe1b4c, not Abby's 0xc1cca4f4): the 6 prone idle / move ones and the 7 carry <-> aim
# blend transitions (rifle-vepr-grip-*^vepr-*).  Ellie-rig carrier slots of SP-only paks no other feature uses: anim-ellie-workbench-a-semi-auto,
# 6.  The prone stance gets them; the carry <-> aim blends (never asked in the test log while the M14 aimed, MP aims through the motion-
# matching set) keep the game's fingers.
ELLIE_SIG, ABBY_SIG = 0x5abe1b4c, 0xc1cca4f4
RIG_OF = {ELLIE_SIG: "ellie-skel", ABBY_SIG: "abby-skel"}
ELLIE_RIG_KEEP = ["rifle-vepr-grip-prone-flip", "rifle-vepr-grip-prone-move-bw-norm", "rifle-vepr-grip-prone-move-fw-norm",
                  "rifle-vepr-grip-prone-move-l-norm", "rifle-vepr-grip-prone-move-r-norm", "rifle-vepr-grip-prone-norm"]


def clips(log=print):
    a = p1_carrier.anims(p1_carrier.load(p1_carrier.game_pak(SRC_PAK)))
    p = p1_carrier.load(p1_carrier.game_pak(SRC_PAK))
    out = []
    for n in sorted(k for k in a if k.startswith("rifle-vepr-grip-")):
        if any(s in n for s in SKIP) or struct.unpack_from("<H", p.d, a[n][1] + 0x20)[0] == 2:
            continue
        sig = struct.unpack_from("<I", p.d, a[n][1] + 4)[0]
        if sig == ELLIE_SIG and n not in ELLIE_RIG_KEEP:
            log(f"  {n:52s} ellie-skel clip, not carried (the only free Ellie-rig carrier slots, anim-ellie-workbench-a-semi-auto: 6)")
            continue
        out.append(n)
    return out


def ref_track(ref, nf):
    """{joint: (nf, 12)} right-hand rows of the Ellie hunting-rifle clip `ref`, sampled at the normalized times of an nf-frame clip"""
    E = H.rig("ellie-skel")
    r, _ = p1_anims.decode(H.clip_bytes(REF_PAK, ref))
    pos = np.linspace(0.0, len(r) - 1, nf) if nf > 1 else np.zeros(1)
    s = fa.sample_rows(r, pos)
    out = {}
    for n in ["r_hand_prop"] + FINGERS:
        i = E.idx[n]
        if i < s.shape[1] and not np.all(np.isnan(s[:, i, 4])):
            out[n] = s[:, i]
    return out


def stock_hand(name, nf):
    """per-frame target rows {joint: (nf, 12)}: the twin's, any missing row from the stance's plain hand pose; -> (rows, source names)"""
    tw = twin_for(name)
    t = ref_track(tw, nf)
    used = [tw]
    # missing rows: the stance's plain hand pose, then its right-hand-only clip (prone-hands has no prop: prone-idle-r-hand), then the stand one
    chain = [fallback_for(name)] + (["rifle-remington-bolt-grip-prone-idle-r-hand"] if "prone" in name or "supine" in name else []) + \
        ["rifle-remington-bolt-grip-r-hand"]
    for fb in chain:
        if len(t) >= 1 + len(FINGERS):
            break
        if fb == tw:
            continue
        f = ref_track(fb, 1)
        miss = [k for k in f if k not in t]
        for k in miss:
            t[k] = np.repeat(f[k], nf, axis=0)
        if miss:
            used.append(f"{fb} ({len(miss)} rows)")
    return t, used


def _ang(a, b):
    return float(np.degrees(2 * np.arccos(min(1.0, abs(float(np.dot(qnorm(a), qnorm(b))))))))


def frame_local(R, A, row):
    """base-male local pose from one frame of an abby-skel clip (rotations by name; props keep their translations)"""
    L = R.bind.copy()
    for i in range(min(row.shape[0], len(A.names))):
        if np.isnan(row[i, 4]):
            continue
        n = A.names[i]
        if n in R.idx:
            j = R.idx[n]
            L[j, 4:8] = row[i, 4:8]
            if n.endswith("hand_prop") or n.endswith("prop_attachment"):
                if not np.isnan(row[i, 8]):
                    L[j, 8:11] = row[i, 8:11]
    return L


def rehand(name, log=print):
    """-> (new clip bytes, report) for one absolute Vepr grip clip.  Modes: 'arm' (the clip writes the right arm: prop + fingers swapped, the
    arm re-solved so the gun keeps its world pose), 'part' (the aim -part: props only, its arm comes from the aim add db_hold.py m14 re-solves
    for this prop), 'fingers' (no right arm, not an aim part: only the fingers, the gun is left where the clip puts it)"""
    c = H.clip_bytes(SRC_PAK, name)
    assert struct.unpack_from("<H", c, 0x20)[0] != 2, f"{name} is additive"
    rows, fps = p1_anims.decode(c)
    A, R = H.rig(RIG_OF[struct.unpack_from("<I", c, 4)[0]]), H.rig(MP)
    written = [i for i in range(rows.shape[1]) if not np.all(np.isnan(rows[:, i, 4]))]
    wn = {A.names[i] for i in written}
    tgt, used = stock_hand(name, len(rows))
    fingn = [n for n in FINGERS if n in wn and n in tgt]
    if "r_hand_prop" in wn and all(f"r_{n}" in wn for n in ("shoulder", "elbow", "wrist")):
        mode = "arm"
    elif "r_hand_prop" in wn:
        mode = "part"
    elif fingn:
        mode = "fingers"
    else:
        log(f"  {name:52s} no right-hand rows: left as the game's")
        return None, None
    g, pr = R.idx["r_hand_prop_attachment"], R.idx["r_hand_prop"]
    out = rows.copy()
    for f in range(len(rows)):
        L = frame_local(R, A, rows[f])
        wq, wp = fk(L, R.parent)
        Gq, Gp = wq[g].copy(), wp[g].copy()
        L2 = L.copy()
        if mode in ("arm", "part"):
            L2[pr, 4:11] = tgt["r_hand_prop"][f, 4:11]
        for n in fingn:
            L2[R.idx[n], 4:8] = qnorm(tgt[n][f, 4:8])
        if mode == "arm":
            wq2, wp2 = fk(L2, R.parent)
            L2 = H.solve_arm(MP, L2, wq2, wp2, "r", Gp, Gq)
        names = list(fingn) + (["r_hand_prop"] if mode in ("arm", "part") else []) + (["r_shoulder", "r_elbow", "r_wrist"] if mode == "arm" else [])
        for n in names:
            i = A.idx[n]
            q = L2[R.idx[n], 4:8].copy()
            if np.dot(q, out[f, i, 4:8]) < 0:
                q = -q
            out[f, i, 4:8] = q
            if n == "r_hand_prop" and not np.isnan(out[f, i, 8]):
                out[f, i, 8:11] = L2[pr, 8:11]
    for i in written:                    # each quaternion channel continuous over the frames
        for f in range(1, len(out)):
            if np.dot(out[f, i, 4:8], out[f - 1, i, 4:8]) < 0:
                out[f, i, 4:8] *= -1
    new = p1_anims.encode(out, fps, fa._groups(c), struct.unpack_from("<I", c, 4)[0], written)
    # self-check on the decoded bake: the gun's world pose ('arm'), the prop = the hunting rifle's, the fingers, the left hand untouched
    back, _ = p1_anims.decode(new)
    err = dict(gun_cm=0.0, gun_deg=0.0, prop_deg=0.0, finger_deg=0.0, left_cm=0.0)
    for f in range(len(back)):
        L0 = frame_local(R, A, rows[f]); wq0, wp0 = fk(L0, R.parent)
        L1 = frame_local(R, A, back[f]); wq1, wp1 = fk(L1, R.parent)
        if mode == "arm":
            err["gun_cm"] = max(err["gun_cm"], np.linalg.norm(wp1[g] - wp0[g]) * 100)
            err["gun_deg"] = max(err["gun_deg"], _ang(wq1[g], wq0[g]))
        if mode != "fingers":
            err["prop_deg"] = max(err["prop_deg"], _ang(L1[pr, 4:8], tgt["r_hand_prop"][f, 4:8]))
        for n in fingn:
            err["finger_deg"] = max(err["finger_deg"], _ang(L1[R.idx[n], 4:8], tgt[n][f, 4:8]))
        for n in ("l_wrist", "l_hand_prop_attachment"):
            err["left_cm"] = max(err["left_cm"], np.linalg.norm(wp1[R.idx[n]] - wp0[R.idx[n]]) * 100)
    vp = rows[0, A.idx["r_hand_prop"], 4:8] if "r_hand_prop" in wn else None
    rep = dict(frames=len(rows), mode=mode, ref=used, hand_turn_on_gun_deg=round(_ang(vp, tgt["r_hand_prop"][0, 4:8]), 1) if vp is not None else None,
               **{k: round(float(v), 3) for k, v in err.items()}, bytes=[len(c), len(new)])
    assert err["gun_cm"] < 0.1 and err["gun_deg"] < 0.1 and err["prop_deg"] < 0.2 and err["finger_deg"] < 0.5 and err["left_cm"] < 0.05, \
        f"{name}: bake check failed {rep}"
    log(f"  {name:52s} {rep}")
    return new, rep


def bake(log=print):
    out, report = {}, {}
    for n in clips():
        c, r = rehand(n, log)
        if c:
            out[n], report[n] = c, r
    return out, report


def save(out, report):
    os.makedirs(DATA, exist_ok=True)
    meta = {}
    raw = p1_carrier.game_pak(SRC_PAK)
    for k, (n, clip) in enumerate(sorted(out.items())):
        fn = n.replace("rifle-vepr-grip-", "") + ".clip"
        open(os.path.join(DATA, fn), "wb").write(clip)
        _, evs = p1_carrier.ref_events(raw, n)        # (the clip's own anim events ride along, unchanged: same frame count)
        meta[n] = {"file": fn, "report": report[n], "events": [[sid, fr, [list(x) for x in pr]] for sid, fr, pr in (evs or [])]}
    json.dump(meta, open(os.path.join(DATA, "meta.json"), "w"), indent=1)


def load():
    """[(key, clip bytes, 'part', None)] carrier jobs + {key: played name}"""
    meta = json.load(open(os.path.join(DATA, "meta.json")))
    jobs, names = [], {}
    for n, m in sorted(meta.items()):
        key = f"m14hand|{n}"
        evs = [(sid, fr, [tuple(x) for x in pr]) for sid, fr, pr in m.get("events", [])] or None
        jobs.append((key, open(os.path.join(DATA, m["file"]), "rb").read(), "part", evs))
        names[key] = n
    return jobs, names


if __name__ == "__main__":
    o, r = bake()
    save(o, r)
    print("saved", DATA, len(o), "clips", sum(len(c) for c in o.values()), "bytes")
