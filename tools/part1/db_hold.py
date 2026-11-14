"""Double Barrel aim hold: the stock seated in the shoulder as in SP (the stock floated in front instead of sitting in the shoulder).

What MP plays while aiming the DB (test log, t2r-dbg-overlay.txt = all, hashes resolved with the sidbase):
  base     ellie-mm-rifle-aim-idle / -loop-* (anim-ellie-player-mm-aim, ellie-skel) - "no entry": MP's aim state asks for Ellie's motion-
           matching rifle set and the character-name-abby layer has no rename for it.  SP Abby aims on abby-mm-rifle-aim-* (anim-player-
           gun-abby), and the DB's grip clips are authored on top of THAT base.
  grip     shotgun-dbl-barrel-grip-stand-aim-add (additive, upper body) + shotgun-dbl-barrel-grip-stand-aim-hands (props + fingers): the
           DB module's *ellie-player-aim-rifle* weapon-anim-overlay-info after 5eec0ac (dc_data_patches.patch_db_grips).
  skeleton base-male-skel (every MP look): upper arm 0.293 / forearm 0.280 m vs Abby's 0.267 / 0.253.

Composite (this file, offline FK): local pose = target bind, base clip rotations, additive rotations post-multiplied (L = base * add),
the -hands / -part rows (props) replace; the gun hangs at r_hand_prop_attachment; the butt = the centre of the side-by-side model's rear
face (shotgun-dbl-barrel-abby, the rear 1.5 cm of its vertices).  Self-check of the convention: on Abby (SP) the left hand's
l_hand_prop_attachment lands on the gun root (0.0 cm), i.e. both hands hold the same gun.

Measured (stand): SP (Abby, abby base)          butt - r_shoulder (spined frame) = the reference;
                  MP (base-male, ellie base)    butt 5-6 cm off the reference, left hand 7 cm off the gun;
                  base-male on the abby base     ~3 cm off (longer arms), left hand 2.5 cm off.
Fix: (1) t2r-ext renames ellie-mm-rifle(-crouch)-aim-* to the abby-mm twins while the DB set is on the state (the SP base the grips were
made for); (2) this file re-bakes the DB's grip add with both arms re-solved by two-bone IK on base-male-skel so the butt sits where SP
puts it relative to r_shoulder (spined frame) and the left hand's prop meets the gun root; the add clip keeps every other row (spine,
head, fingers) and the gun orientation.  The baked clip rides a body slot of the Abby workbench carrier pak (db_reload.carriers) and
t2r-ext answers its name on the overlay miss like the reload clips (tools/ext/db_reload_built.h).

  python db_hold.py          measure SP / MP / fixed for stand + crouch, bake, self-check, save tools/features/data/db-hold
"""
import json
import os
import pickle
import struct
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.dirname(HERE)
ROOT = os.path.dirname(TOOLS)
MAIN = ROOT.split(os.sep + ".claude" + os.sep)[0]
sys.path[:0] = [HERE, os.path.join(TOOLS, "features"), os.path.join(TOOLS, "models"), TOOLS]
import p1_anims  # noqa: E402
import p1_carrier  # noqa: E402
import frontier_anims as fa  # noqa: E402
from p1_rig import qmul, qinv, qrot, qnorm, fk, from_to  # noqa: E402

GUN_PAK = "anim-player-gun-abby"
ELLIE_AIM_PAK = "anim-ellie-player-mm-aim"
STANCES = {   # stance: (SP abby base, MP ellie base, add, props / hands clip)
    "stand": ("abby-mm-rifle-aim-idle", "ellie-mm-rifle-aim-idle", "shotgun-dbl-barrel-grip-stand-aim-add", "shotgun-dbl-barrel-grip-stand-aim-hands"),
    "crouch": ("abby-mm-rifle-crouch-aim-idle", "ellie-mm-rifle-crouch-aim-idle", "shotgun-dbl-barrel-grip-crouch-aim-add",
               "shotgun-dbl-barrel-grip-crouch-aim-part"),
}
DATA = os.path.join(TOOLS, "features", "data", "db-hold")
# 2013 Semi-Auto Rifle (rifle-m14-semi, the gun did not sit in the shoulder): its player overlay key is rifle-tommy-abby-player
# (build_dll: art def +0x180 / +0x188), whose aim entries name Abby's Vepr grips (rifle-vepr-grip-{stand,crouch}-aim-add + -part) on the M14
# model rifle-m14-dark; SP plays them on abby-mm-rifle-aim-*, MP on Ellie's base.  Same fix as the DB; the ext gates the baked adds on the
# M14's set (the Vepr plays the same add names and keeps the game's).
M14_STANCES = {
    "stand": ("abby-mm-rifle-aim-idle", "ellie-mm-rifle-aim-idle", "rifle-vepr-grip-stand-aim-add", "rifle-vepr-grip-stand-aim-part"),
    "crouch": ("abby-mm-rifle-crouch-aim-idle", "ellie-mm-rifle-crouch-aim-idle", "rifle-vepr-grip-crouch-aim-add",
               "rifle-vepr-grip-crouch-aim-part"),
}
# M14 only: the right hand takes the hunting rifle's stock grip (Ellie's hunting rifle right-hand clips, anim-player-gun-shared; m14_hand.py)
STOCK_PAK = "anim-player-gun-shared"
STOCK_HAND = {"m14": {"stand": "rifle-remington-bolt-grip-stand-aim-hands", "crouch": "rifle-remington-bolt-grip-stand-aim-hands"}}   # (= its crouch-aim-part prop)
FINGERS = ["r_thumba", "r_thumbb", "r_thumbc"] + [f"r_{f}{s}" for f in ("index", "middle", "ring", "pinky") for s in ("_meta", "a", "b", "c")]
GUNS = {   # gun: (model pak in re/models, stances, data dir, carrier key prefix)
    "db": ("shotgun-dbl-barrel-abby", STANCES, DATA, "hold"),
    "m14": ("rifle-m14-dark", M14_STANCES, os.path.join(TOOLS, "features", "data", "m14-hold"), "m14hold"),
    "vepr": ("rifle-boar", M14_STANCES, None, None),          # measured only (python db_hold.py vepr)
}


def _skel(name):
    for base in (ROOT, MAIN):
        p = os.path.join(base, "re", "uc4ps4", "t2", name + ".pak")
        if os.path.exists(p):
            return p
    raise SystemExit(f"{name}.pak not found in re/uc4ps4/t2")


def _model(name):
    for base in (ROOT, MAIN):
        p = os.path.join(base, "re", "models", name + ".pak")
        if os.path.exists(p):
            return p
    raise SystemExit(f"{name}.pak not found in re/models")


RIGS = {}


def rig(name):
    if name not in RIGS:
        RIGS[name] = p1_anims.Rig(_skel(name))
    return RIGS[name]


_RAW = {}


def clip_bytes(pak, name):
    if pak not in _RAW:
        p = p1_carrier.load(p1_carrier.game_pak(pak))
        _RAW[pak] = (p, p1_carrier.anims(p))
    p, a = _RAW[pak]
    base, ca, size, sig = a[name]
    return bytes(p.d[ca:ca + size + 0x10])


_DEC_CACHE = os.path.join(MAIN, "re", "db-hold-decoded.pkl")


def decoded(pak, name, rk):
    """frame 0 of a clip as {joint name: row} (rows of the clip's own rig, NaN = not written); cached (the decoder is slow)"""
    try:
        cache = pickle.load(open(_DEC_CACHE, "rb"))
    except Exception:
        cache = {}
    if name not in cache:
        r, fps = p1_anims.decode(clip_bytes(pak, name))
        R = rig(rk)
        cache[name] = {R.names[i]: r[0, i] for i in range(min(r.shape[1], len(R.names))) if not np.all(np.isnan(r[0, i]))}
        pickle.dump(cache, open(_DEC_CACHE, "wb"))
    return cache[name]


LOD0 = {"shotgun-dbl-barrel-abby": 3, "rifle-m14-dark": 3, "rifle-boar": 7}     # LOD0 submeshes


def gun_points(model="shotgun-dbl-barrel-abby"):
    import ndpak
    pk = ndpak.Pak(_model(model))
    P = np.concatenate([pk.positions(sm) for sm in pk.submeshes[:LOD0[model]]])
    rear = P[P[:, 2] < P[:, 2].min() + 0.015]
    return rear.mean(0)


BUTT = None


def compose(rk, base, add, part, base_t):
    """-> (L local rows, wq, wp) on rig rk; base / add / part = {joint: row}"""
    R = rig(rk)
    L = R.bind.copy()
    for n, row in base.items():
        if n in R.idx:
            j = R.idx[n]
            L[j, 4:8] = row[4:8]
            if base_t and not np.isnan(row[8]):
                L[j, 8:11] = row[8:11]
    for n, row in add.items():
        if n in R.idx:
            j = R.idx[n]
            L[j, 4:8] = qnorm(qmul(L[j, 4:8], row[4:8]))
            if not np.isnan(row[8]):
                L[j, 8:11] += row[8:11]
    for n, row in part.items():
        if n in R.idx:
            L[R.idx[n], 4:11] = row[4:11]
    wq, wp = fk(L, R.parent)
    return L, wq, wp


def measure(rk, L, wq, wp):
    R = rig(rk)
    j = R.idx["r_hand_prop_attachment"]
    butt = wp[j] + qrot(wq[j], BUTT)
    sq = wq[R.idx["spined"]]
    rel = qrot(qinv(sq), butt - wp[R.idx["r_shoulder"]])
    lgap = wp[R.idx["l_hand_prop_attachment"]] - wp[j]
    lang = np.degrees(2 * np.arccos(min(1.0, abs(float(np.dot(wq[R.idx["l_hand_prop_attachment"]], wq[j]))))))
    return rel, np.linalg.norm(lgap), lang, butt


def two_bone(wp, a, b, c, target):
    """new world positions of the elbow for shoulder a, elbow b, wrist c reaching `target` (bend plane kept)"""
    l1, l2 = np.linalg.norm(wp[b] - wp[a]), np.linalg.norm(wp[c] - wp[b])
    d = target - wp[a]
    dist = np.clip(np.linalg.norm(d), abs(l1 - l2) + 1e-4, l1 + l2 - 1e-4)
    dn = d / np.linalg.norm(d)
    pole = (wp[b] - wp[a]) - dn * np.dot(wp[b] - wp[a], dn)
    pole /= np.linalg.norm(pole)
    x = (l1 * l1 - l2 * l2 + dist * dist) / (2 * dist)
    h = np.sqrt(max(l1 * l1 - x * x, 0.0))
    return wp[a] + dn * x + pole * h, wp[a] + dn * dist


def solve_arm(rk, L, wq, wp, side, prop_target_p, prop_target_q):
    """re-solve one arm (shoulder / elbow / wrist local rotations) so <side>_hand_prop_attachment reaches the target transform"""
    R = rig(rk)
    s, e, w, pr = (R.idx[f"{side}_{n}"] for n in ("shoulder", "elbow", "wrist", "hand_prop_attachment"))
    # wrist -> prop rigid offset (current pose)
    off_q = qmul(qinv(wq[w]), wq[pr])
    off_p = qrot(qinv(wq[w]), wp[pr] - wp[w])
    w_q = qnorm(qmul(prop_target_q, qinv(off_q)))
    w_p = prop_target_p - qrot(w_q, off_p)
    elbow, wrist = two_bone(wp, s, e, w, w_p)
    L = L.copy()
    # shoulder: rotate the upper arm onto the new elbow
    ps = R.parent[s]
    ns_q = qnorm(qmul(from_to((wp[e] - wp[s]) / np.linalg.norm(wp[e] - wp[s]), (elbow - wp[s]) / np.linalg.norm(elbow - wp[s])), wq[s]))
    L[s, 4:8] = qnorm(qmul(qinv(wq[ps]), ns_q))
    wq2, wp2 = fk(L, R.parent)
    ne_q = qnorm(qmul(from_to((wp2[w] - wp2[e]) / np.linalg.norm(wp2[w] - wp2[e]), (wrist - wp2[e]) / np.linalg.norm(wrist - wp2[e])), wq2[e]))
    L[e, 4:8] = qnorm(qmul(qinv(wq2[R.parent[e]]), ne_q))
    wq3, wp3 = fk(L, R.parent)
    L[w, 4:8] = qnorm(qmul(qinv(wq3[R.parent[w]]), w_q))
    return L


def bake(log=print, gun="db"):
    global BUTT
    model, stances = GUNS[gun][:2]
    BUTT = gun_points(model)
    log(f"{gun}: {model} butt (rear 1.5 cm centre, gun root frame) {np.round(BUTT * 100, 1).tolist()} cm")
    out, report = {}, {}
    MP = "base-male-skel"
    for st, (sp_base, mp_base, add_n, part_n) in stances.items():
        add = decoded(GUN_PAK, add_n, "abby-skel")
        part = decoded(GUN_PAK, part_n, "abby-skel")
        sp_b = decoded(GUN_PAK, sp_base, "abby-skel")
        el_b = decoded(ELLIE_AIM_PAK, mp_base, "ellie-skel")
        Ls, wqs, wps = compose("abby-skel", sp_b, add, part, True)
        ref, lg0, la0, _ = measure("abby-skel", Ls, wqs, wps)
        rows = {"SP abby": (ref, lg0, la0)}
        L1, wq1, wp1 = compose(MP, el_b, add, part, False)
        rows["MP before (ellie base)"] = measure(MP, L1, wq1, wp1)[:3]
        L2, wq2, wp2 = compose(MP, sp_b, add, part, False)          # after the ext's ellie -> abby base rename
        rel2 = measure(MP, L2, wq2, wp2)
        rows["MP abby base, stock add"] = rel2[:3]
        # targets: the gun moved so the butt has SP's offset from r_shoulder in the spined frame; orientation kept; both props on it
        R = rig(MP)
        j = R.idx["r_hand_prop_attachment"]
        dW = qrot(wq2[R.idx["spined"]], ref - rel2[0])
        tp, tq = wp2[j] + dW, wq2[j]
        # M14 right hand (m14_hand.py): the hunting rifle's stock grip instead of the Vepr's pistol grip - its r_hand_prop (the
        # hand's place / angle on the gun) and right fingers; the right arm below is solved for THAT prop, so the gun pose is the same
        hand, part_new, fingers = STOCK_HAND.get(gun, {}).get(st), part, {}
        L2h = L2
        if hand:
            hd = decoded(STOCK_PAK, hand, "ellie-skel")
            part_new = {**part, "r_hand_prop": hd["r_hand_prop"]}
            fingers = {n: hd[n] for n in FINGERS if n in hd}
            L2h = L2.copy()
            L2h[R.idx["r_hand_prop"], 4:11] = hd["r_hand_prop"][4:11]
            for n, row in fingers.items():
                L2h[R.idx[n], 4:8] = row[4:8]
        wq2h, wp2h = fk(L2h, R.parent)
        L3 = solve_arm(MP, L2h, wq2h, wp2h, "r", tp, tq)
        wq3, wp3 = fk(L3, R.parent)
        L3 = solve_arm(MP, L3, wq3, wp3, "l", tp, tq)
        wq3, wp3 = fk(L3, R.parent)
        rows["MP fixed"] = measure(MP, L3, wq3, wp3)[:3]
        # the new additive rows: add = inv(base local) * solved local (post convention), for the six arm joints
        base_L, _, _ = compose(MP, sp_b, {}, {}, False)
        new_add = {}
        for side in "lr":
            for n in ("shoulder", "elbow", "wrist"):
                jn = f"{side}_{n}"
                new_add[jn] = qnorm(qmul(qinv(base_L[R.idx[jn], 4:8]), L3[R.idx[jn], 4:8]))
        for jn in fingers:
            new_add[jn] = qnorm(qmul(qinv(base_L[R.idx[jn], 4:8]), L3[R.idx[jn], 4:8]))
        # re-encode the add clip on the abby rig with the six rows replaced (everything else as the game's clip)
        c = clip_bytes(GUN_PAK, add_n)
        r, fps = p1_anims.decode(c)
        A = rig("abby-skel")
        written = [i for i in range(r.shape[1]) if not np.all(np.isnan(r[0, i]))]
        for jn, q in new_add.items():
            i = A.idx[jn]
            if i not in written and jn in fingers:
                log(f"  {st:6s} {add_n} does not write {jn}: left as the base's")
                continue
            assert i in written, f"{add_n} does not write {jn}"
            if np.dot(q, r[0, i, 4:8]) < 0:
                q = -q
            r[:, i, 4:8] = q
        new = p1_anims.encode(r, fps, fa._groups(c), struct.unpack_from("<I", c, 4)[0], written, additive=True)
        back, _ = p1_anims.decode(new)
        d = {A.names[i]: back[0, i] for i in written}
        L4, wq4, wp4 = compose(MP, sp_b, d, part_new, False)
        rows["MP fixed (decoded bake)"] = measure(MP, L4, wq4, wp4)[:3]
        if hand:      # the right hand on the gun = the hunting rifle's (prop local) and its fingers, after the decoded add on the abby base
            ang = lambda a, b: np.degrees(2 * np.arccos(min(1.0, abs(float(np.dot(qnorm(a), qnorm(b)))))))
            ph = ang(L4[R.idx["r_hand_prop"], 4:8], hd["r_hand_prop"][4:8])
            fh = max(ang(L4[R.idx[n], 4:8], r_[4:8]) for n, r_ in fingers.items() if A.idx[n] in written)
            turn = ang(part["r_hand_prop"][4:8], hd["r_hand_prop"][4:8])
            log(f"  {st:6s} right hand: {hand} (hand turned {turn:.1f} deg on the gun vs the Vepr grip), decoded: prop {ph:.3f} deg, "
                f"{len(fingers)} fingers max {fh:.3f} deg off it")
            assert ph < 0.1 and fh < 0.5, f"{st}: right hand check failed {ph} {fh}"
        for k, (rel, lg, la) in rows.items():
            err = np.linalg.norm(np.asarray(rel) - ref) * 100
            log(f"  {st:6s} {k:26s} butt-r_shoulder (spined) {np.round(np.asarray(rel) * 100, 1).tolist()} cm, off SP {err:4.1f} cm; "
                f"left hand prop vs gun {lg * 100:4.1f} cm / {la:4.1f} deg")
        fin = rows["MP fixed (decoded bake)"]
        assert np.linalg.norm(np.asarray(fin[0]) - ref) < 0.01 and fin[1] < 0.01, f"{st}: bake check failed {fin}"
        out[st] = (add_n, new)
        report[st] = {k: [np.round(np.asarray(v[0]) * 100, 2).tolist(), round(v[1] * 100, 2), round(v[2], 2)] for k, v in rows.items()}
    return out, report


def save(out, report, gun="db"):
    DATA = GUNS[gun][2]
    os.makedirs(DATA, exist_ok=True)
    meta = {}
    for st, (name, clip) in out.items():
        fn = f"{st}-aim-add.clip"
        open(os.path.join(DATA, fn), "wb").write(clip)
        meta[st] = {"file": fn, "name": name, "report_cm": report[st]}
    json.dump(meta, open(os.path.join(DATA, "meta.json"), "w"), indent=1)


def load(gun="db"):
    """[(key, clip bytes, 'add', None)] carrier jobs + {key: played name}"""
    _, _, DATA, pre = GUNS[gun]
    meta = json.load(open(os.path.join(DATA, "meta.json")))
    jobs, names = [], {}
    for st, m in sorted(meta.items()):
        key = f"{pre}|{st}"
        jobs.append((key, open(os.path.join(DATA, m["file"]), "rb").read(), "add", None))
        names[key] = m["name"]
    return jobs, names


if __name__ == "__main__":
    g = sys.argv[1] if len(sys.argv) > 1 else "db"
    o, rep = bake(gun=g)
    if GUNS[g][2]:
        save(o, rep, g)
        print("saved", GUNS[g][2])
