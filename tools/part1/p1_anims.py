"""Part I Shorty / El Diablo player animations baked onto the TLOU2 player (Ellie rig) and the TLOU2 pistol-base gun rig
(T2R_P1_GUNS).  Notes: re/part1/weapons.md section 9.

Source (Part I, read-only): sp-common.psarc actor97/anim-t1x-joel-player-gun.pak (Joel's gameplay gun clips),
t1x-joel-skel.pak (Joel rig, ClipData sig 0xa8db40cf), pistol-base.pak (Part I gun rig, 86 joints, sig 0xf447b519).
Part I and TLOU2 share the ClipData format and the reload layout, so one Part I reload = the same four clips TLOU2 uses:
  <name>-part  arm layer: neck / head, clavicle..wrist, palms, hand props, fingers (local rows, played as a partial layer
               OVER whatever the legs / spine / cover / prone base plays: this is TLOU2's own arm-only reload layer)
  <name>-add   additive on root + spinea..spined (body sway of the reload, added on top of the locomotion)
  <name>-gun   the gun's own rig (magazine out / in, cylinder swing-out, rounds shown / hidden ...)
  <name>-base  Part I only: the 1-frame reference pose the additive was made against (used here to fill the spine for FK)

Retarget (Joel -> Ellie), per frame:
  arms / head / fingers: world-space delta (as re/uc4ps4/tools/retarget.py): D = W_joel * inv(Wbind_joel) per joint, Ellie
      world = D * Wbind_ellie, local = inv(world parent) * world, plus bone aiming (each arm bone's child direction = Joel's);
      the spine under the arms comes from the -base pose, so only the arm motion relative to the chest is taken.
  hand props (the gun): kept rigid to the WRIST as in Part I, corrected for the bind difference of the two wrists:
      G_ellie = W_ellie(wrist) * inv(Wbind_ellie(wrist)) * Wbind_joel(wrist) * inv(W_joel(wrist)) * G_joel
      (with no aiming this is exactly the Part I gun pose), translation likewise.
  additive: copied row for row (root, spinea..spined: bind rotations of the two rigs differ by <= 4 deg there).
  gun: every TLOU2 pistol-base joint that a Part I gun joint drives (GUNS[...]['rig'], the same table p1_guns.py skins the
      model with) gets that Part I joint's rigid motion T = W_p1(t) * inv(Wbind_p1) applied to its own bind
      (vertices skinned to it then move exactly as in Part I); its scale (rounds hidden / shown) is copied.
Encoding: re/uc4ps4/tools/uc4enc.build_clip (raw float4 rows, constant rows as op 0x16 / 0x18), checked by decoding every
clip back with the game's own handlers (emulator) - verify().

  python p1_anims.py bake [shorty|diablo|all]   -> <main>/re/part1/anims/*.clip + report
  python p1_anims.py events [shorty|diablo|all]  only re-read the Part I clips' anim events (-> *.events.json)
  python p1_anims.py preview [shorty|diablo|all] -> re/part1/preview/anim-<gun>-<stance>.png contact sheets
Env: T2R_P1_RELOAD=slow bakes Part I's slow (not upgraded) reloads; T2R_P1_ANIM_FPS (default 30) resamples 60 fps
sources down.
Needs: the Part I install (T2R_P1_GAME or re/part1/game-path.txt), re/uc4ps4/t2/ellie-skel.pak, re/models/pistol-base.pak,
the UC4 ELF for the emulator (UC4_ELF) - like the UC4 / 2013 bakes."""
import os
import struct
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.dirname(HERE)
ROOT = os.path.dirname(TOOLS)
MAIN = os.environ.get("T2R_MAIN_ROOT", ROOT.split(os.sep + ".claude" + os.sep)[0])
UC4 = os.path.join(ROOT, "re", "uc4ps4", "tools")
sys.path[:0] = [HERE, UC4]
import p1_anim  # noqa: E402
import p1_skel  # noqa: E402
from p1_rig import qmul, qinv, qnorm, qrot, from_to, fill, fk, resample  # noqa: E402

P1DIR = os.path.join(MAIN, "re", "part1")
X = os.path.join(P1DIR, "x", "anims", "actor97")
OUT = os.path.join(P1DIR, "anims")
PREVIEW = os.path.join(P1DIR, "preview")
P1_GUN_PAK = "anim-t1x-joel-player-gun"
ELLIE_SKEL = os.path.join(ROOT, "re", "uc4ps4", "t2", "ellie-skel.pak")
T2_PISTOL_BASE = os.path.join(ROOT, "re", "models", "pistol-base.pak")
ELLIE_SIG = 0x5abe1b4c
ELLIE_GROUPS = [(127, 0), (16, 108), (38, 0), (96, 0), (99, 0), (94, 0), (50, 0)]   # every ellie-skel clip's records
GUN_SIG = 0x29e20d42
GUN_GROUPS = [(62, 0)]
SPEED = os.environ.get("T2R_P1_RELOAD", "fast")      # 'fast' = Part I's upgraded reload, 'slow' = Part I's default
BODY_FPS = float(os.environ.get("T2R_P1_ANIM_FPS", "30"))
CONST_EPS = 0.2       # degrees: a row that never leaves frame 0 by more is written as a constant

# the rows TLOU2's own pistol reload -part clip writes (anim-player-gun-shared ellie-pistol-reload-stand-tac-part)
PART_ROWS = ["neck", "heada", "headb", "l_clavicle", "r_clavicle", "l_shoulder", "r_shoulder", "l_elbow", "r_elbow",
             "l_wrist", "r_wrist", "l_hand_prop", "r_hand_prop", "l_hand_prop_attachment", "r_hand_prop_attachment",
             "l_palm", "r_palm"] + [f"{s}_{f}" for f in ("thumba", "thumbb", "thumbc", "index_meta", "indexa", "indexb",
                                                         "indexc", "middle_meta", "middlea", "middleb", "middlec",
                                                         "ring_meta", "ringa", "ringb", "ringc", "pinky_meta", "pinkya",
                                                         "pinkyb", "pinkyc") for s in ("l", "r")]
ADD_ROWS = ["root", "spinea", "spineb", "spinec", "spined"]
PROPS = ("l_hand_prop", "r_hand_prop")
AIM = {"l_clavicle": "l_shoulder", "r_clavicle": "r_shoulder", "l_shoulder": "l_elbow", "r_shoulder": "r_elbow",
       "l_elbow": "l_wrist", "r_elbow": "r_wrist", "neck": "heada"}

# Part I clip stems (the -part / -add / -gun / -base suffixes are added) per TLOU2 reload stance:
#   aim = TLOU2 *-stand-aim-*, relax = *-stand-* and relaxed-*, crouch-aim / crouch = *-crouch-aim-* / *-crouch-*
#   (Part I's own overlay t1x-guns/t1x-pistol-uber.bin maps joel-pistol-reload-aim -> reload, -reload -> reload-relax,
#   -crouch-aim -> crouch-reload, -crouch -> crouch-reload-relax).  Prone / supine keep TLOU2's own clips (weapons.md 9).
GUNS = {
    "diablo": dict(
        sep="--",
        reload={"aim": "joel-t1x-p-uber-reload{s}", "relax": "joel-t1x-p-uber-reload-relax{s}",
                "crouch-aim": "joel-t1x-p-uber-crouch-reload{s}", "crouch": "joel-t1x-p-uber-crouch-reload-relax{s}"},
        slow={"aim": "joel-t1x-p-uber-reload-slow", "relax": "joel-t1x-p-uber-reload-relax-slow",
              "crouch-aim": "joel-t1x-p-uber-crouch-reload-slow", "crouch": "joel-t1x-p-uber-crouch-reload-relax-slow"},
        fire_gun="joel-pistol-uber-fire-slow-gun",
        # TLOU2 pistol-base joint <- Part I pistol-base joint that drives it (p1_guns.DIABLO skins the model the same way)
        rig={"cylinder_arm": "cylinder_arm", "cylinder": "uber_cylinder", "bullet_01": "uber_bullet_1",
             "bullet_02": "uber_bullet_2", "bullet_03": "uber_bullet_3", "bullet_04": "uber_bullet_4",
             "hammer_revolver": "hammer_revolver", "trigger": "trigger"},
    ),
    "shorty": dict(
        sep="-",
        reload={"aim": "joel-pistol-shotgun-reload-aim", "relax": "joel-pistol-shotgun-reload-relax",
                "crouch-aim": "joel-pistol-shotgun-reload-crouch-aim", "crouch": "joel-pistol-shotgun-reload-crouch-relax"},
        slow={"aim": "joel-pistol-shotgun-reload-slow-aim", "relax": "joel-pistol-shotgun-reload-slow-relax",
              "crouch-aim": "joel-pistol-shotgun-reload-crouch-slow-aim", "crouch": "joel-pistol-shotgun-reload-crouch-slow-relax"},
        fire_gun="joel-pistol-shotgun-aim-fire-gun",
        rig={"magazine": "magazine", "mag_bullet": "pistol_shotgun_shell_b", "shell_whole_a": "pistol_shotgun_shell_a",
             "slide": "slide", "hammer": "hammer_shotgun", "trigger": "trigger"},
    ),
}
# Grip calibration of the right-hand prop (the gun): (Part I grip clip of the gun, TLOU2 pak, TLOU2 grip clip that holds
# it in game = the host overlay's: the Shorty overlay is the Beretta's set, El Diablo's the revolver's).  See grip_calibration.
# The TLOU2 grip is layered: the -grip-aim-part clip writes only the hand props, the -r-hand clip the right fingers, the
# -hands-part clip (Beretta) both hands; later clips win per row (t2_grip_pose).
GUNS["shorty"]["grip"] = ("joel-pistol-shotgun-grip-aim-part", "anim-player-gun-shared",
                          ("pistol-beretta-grip-aim-part", "pistol-beretta-grip-stand-aim-hands-part",
                           "pistol-beretta-grip-r-hand"))
GUNS["diablo"]["grip"] = ("joel-pistol-uber-grip-aim-part", "anim-player-gun-shared",
                          ("pistol-revolver-taurus-grip-stand-aim-part", "pistol-revolver-taurus-grip-r-hand"))
GRIP_CAL = os.environ.get("T2R_P1_GRIP_CAL", "0") == "1"      # 1 = re-base the reload gun on the TLOU2 grip (grip_calibration; off since the hand aiming)
RPROP_ATT = "r_hand_prop_attachment"
STANCES = ("aim", "relax", "crouch-aim", "crouch")


def stems(gun):
    g = GUNS[gun]
    if SPEED == "slow":
        return dict(g["slow"])
    return {k: v.format(s="") for k, v in g["reload"].items()}


def clip_name(gun, stance, kind):
    g = GUNS[gun]
    return stems(gun)[stance] + g["sep"] + kind


# ---------------------------------------------------------------- sources

def ensure_sources():
    """extract the Part I paks this needs into <main>/re/part1/x/anims (read-only access to the install)"""
    need = [P1_GUN_PAK, "t1x-joel-skel", "pistol-base"]
    if all(os.path.exists(os.path.join(X, n + ".pak")) for n in need):
        return
    import p1_archive
    import p1_guns
    game = p1_guns.game_dir()
    a = p1_archive.Psarc(os.path.join(game, "build", "pc", "main", "sp-common.psarc"))
    os.makedirs(X, exist_ok=True)
    for n in need:
        open(os.path.join(X, n + ".pak"), "wb").write(a.get("actor97/" + n + ".pak"))


class Rig:
    """a skeleton with bind locals / bind world, rows in animated (clip) order"""

    def __init__(self, path):
        self.s = s = p1_skel.Skel(path)
        self.bm = s.animated()
        self.k = {b: i for i, b in enumerate(self.bm)}
        self.names = [s.names[b] for b in self.bm]
        self.idx = {n: i for i, n in enumerate(self.names)}
        self.parent = np.array([self.k.get(s.parent[b], -1) for b in self.bm])
        self.bind = s.bind[:len(self.bm)].astype(np.float64)
        self.wq, self.wp = fk(self.bind, self.parent)


_EMU = None


def decode(clip):
    """ClipData -> (F, rows, 12) float64 with NaN where the clip writes nothing"""
    global _EMU
    from uc4anim import ClipDecoder
    if _EMU is None:
        from emu import Emu
        _EMU = Emu()
    d = ClipDecoder(clip, _EMU)
    out = []
    for f in range(d.nframes):
        r = d.eval_frame(f)
        out.append(np.concatenate([r[g] for g in range(d.nrec)]))
    return np.array(out, dtype=np.float64), d.fps


class Source:
    def __init__(self):
        ensure_sources()
        self.anims = p1_anim.P1Anims(os.path.join(X, P1_GUN_PAK + ".pak"))
        self.joel = Rig(os.path.join(X, "t1x-joel-skel.pak"))
        self.p1gun = Rig(os.path.join(X, "pistol-base.pak"))
        self.ellie = Rig(ELLIE_SKEL)
        self.t2gun = Rig(T2_PISTOL_BASE)
        self._cache = {}

    def clip(self, name):
        if name not in self._cache:
            c = self.anims.clips[name]["clip"]
            self._cache[name] = decode(c)
        return self._cache[name]


# ---------------------------------------------------------------- retarget

def _world(local, parent):
    return fk(local, parent)


def body_frames(src, gun, stance):
    """Joel full local pose per frame (part rows over the -base pose over the bind)"""
    part, fps = src.clip(clip_name(gun, stance, "part"))
    base, _ = src.clip(clip_name(gun, stance, "base"))
    b = fill(base[0], src.joel.bind)
    return np.array([fill(p, b) for p in part]), fps


def _xmul(a, b):
    """compose rigid transforms (quat, pos): a then applied to b's frame"""
    return qnorm(qmul(a[0], b[0])), a[1] + qrot(a[0], b[1])


def _xinv(a):
    qi = qinv(a[0])
    return qi, -qrot(qi, a[1])


def t2_clip(pak, name):
    """a TLOU2 game clip decoded: (F, rows, 12), fps (rows in the rig's clip order)"""
    import p1_carrier
    p = p1_carrier.load(p1_carrier.game_pak(pak))
    base, ca, size, sig = p1_carrier.anims(p)[name]
    return decode(bytes(p.d[ca:ca + size + 0x10]))


def t2_grip_pose(pak, names):
    """frame 0 of the layered TLOU2 grip clips: (rows with NaN where none writes, rows filled later by the caller)"""
    rows = None
    for n in names:
        r, _ = t2_clip(pak, n)
        r = r[0]
        rows = r.copy() if rows is None else np.where(np.isnan(r), rows, r)
    return rows


def grip_calibration(src, gun, log=print):
    """M (quat, pos) in Ellie's right-wrist frame: maps the Part I hold of the gun (Joel's r_hand_prop_attachment relative to
    his wrist, through the wrist-bind correction K) onto the TLOU2 hold the game uses outside the reload (Ellie's
    r_hand_prop_attachment relative to her wrist in the host overlay's grip clip).  Measured (p1_hold.py): the wrist
    binds alone left the reloading gun 5.7 cm / 22 deg (Shorty), 4.1 cm / 35 deg (El Diablo) off the TLOU2 hold - the gun
    jumped out of the palm when a reload started and back when it ended.  With M the reload starts and ends exactly in
    the TLOU2 grip, and the Part I motion in between is kept (relative to that hold)."""
    J, E = src.joel, src.ellie
    p1name, pak, t2name = GUNS[gun]["grip"]
    wJ, wE = J.idx["r_wrist"], E.idx["r_wrist"]
    K = qmul(qinv(E.wq[wE]), J.wq[wJ])
    fr, _ = src.clip(p1name)
    jq, jp = fk(fill(fr[0], J.bind), J.parent)
    x_grip = _xmul((K, np.zeros(3)), _xmul(_xinv((jq[wJ], jp[wJ])), (jq[J.idx[RPROP_ATT]], jp[J.idx[RPROP_ATT]])))
    eq, ep = fk(fill(t2_grip_pose(pak, t2name), E.bind), E.parent)
    h_t2 = _xmul(_xinv((eq[wE], ep[wE])), (eq[E.idx[RPROP_ATT]], ep[E.idx[RPROP_ATT]]))
    M = _xmul(h_t2, _xinv(x_grip))
    log(f"  {gun}: grip calibration {p1name} -> {t2name[0]}: {100 * np.linalg.norm(M[1]):.1f} cm, "
        f"{np.degrees(2 * np.arccos(min(1.0, abs(M[0][3])))):.1f} deg")
    return M


FINGER_ROWS = [n for n in PART_ROWS if n[2:].rstrip("abc") in ("thumb", "index", "middle", "ring", "pinky")
               or n[2:].endswith("_meta") or n[2:] == "palm"]


def finger_calibration(src, gun, calib=None, log=print):
    """{Ellie row: quat}: per finger / palm joint of both hands, the local rotation that turns the retargeted Part I grip
    (Joel's grip clip through retarget_part) into the TLOU2 grip clip's.  The world-delta retarget of Joel's fingers onto
    Ellie's (other proportions and finger binds) left the index finger 4 cm off the trigger at the start of the reload
    (p1_hold.py); with this the reload's hands start and end in the TLOU2 grip's exact finger pose."""
    J, E = src.joel, src.ellie
    p1name, pak, t2name = GUNS[gun]["grip"]
    fr, _ = src.clip(p1name)
    ours, _ = retarget_part(src, np.array([fill(fr[0], J.bind)]), calib)
    raw = t2_grip_pose(pak, t2name)
    t2 = fill(raw, E.bind)
    out, worst = {}, 0.0
    for n in FINGER_ROWS:
        e = E.idx[n]
        if np.isnan(raw[e, 4]):
            continue                                # no TLOU2 grip clip poses this joint: left as retargeted
        off = qnorm(qmul(t2[e, 4:8], qinv(ours[0, e, 4:8])))
        out[e] = off
        worst = max(worst, np.degrees(2 * np.arccos(min(1.0, abs(off[3])))))
    log(f"  {gun}: finger calibration on {len(out)} joints (largest {worst:.1f} deg)")
    return out


FINGER_CHILD = {}
for _s in "lr":
    for _f in ("thumb", "index", "middle", "ring", "pinky"):
        FINGER_CHILD[f"{_s}_{_f}a"] = f"{_s}_{_f}b"
        FINGER_CHILD[f"{_s}_{_f}b"] = f"{_s}_{_f}c"
        if _f != "thumb":
            FINGER_CHILD[f"{_s}_{_f}_meta"] = f"{_s}_{_f}a"
# The gun-hand pose in the Shorty reload was wrong (p1_reload_hand.py): the hand is retargeted to wrap the gun
# as Part I's does - finger bones aimed in the wrist frame (HAND_AIM), the gun carried at Part I's hold relative to the
# wrist (no grip calibration by default: M re-based the gun 22 / 35 deg in the hand, so Part I's fingers no longer met it),
# and no TLOU2 grip hand pose (it fixed the fingers but the Part I gun moves inside the hand mid-reload).
HAND_AIM = os.environ.get("T2R_P1_HAND", "aim") == "aim"


def grip_hand_pose(src, gun, log=print):
    """{Ellie row: local quat} of the RIGHT palm / finger joints in the TLOU2 grip (the host overlay's layered grip pose:
    the -r-hand clip). The right hand holds the gun for the whole Part I reload (Shorty: the left hand works the shell
    magazine; El Diablo: the left hand swings / loads the cylinder), so the gun hand keeps TLOU2's own grip of this gun
    over the reload (p1_reload_hand.py): with the gun re-based on the TLOU2 hold (grip_calibration) but the
    fingers retargeted from Joel's (other hand size and finger binds), the fingertips sat ~3 cm off Part I's in the
    gun frame for the WHOLE reload and the index 4.0 / 4.5 cm off the trigger (the gun-hand pose in the reload was wrong).
    T2R_P1_HAND=retarget keeps Joel's retargeted fingers."""
    E = src.ellie
    p1name, pak, t2name = GUNS[gun]["grip"]
    raw = t2_grip_pose(pak, t2name)
    out = {}
    for n in FINGER_ROWS:
        e = E.idx[n]
        if n.startswith("r_") and not np.isnan(raw[e, 4]):
            out[e] = qnorm(raw[e, 4:8])
    log(f"  {gun}: gun hand = the TLOU2 grip's ({len(out)} right palm / finger joints from {t2name[-1]})")
    return out


def retarget_part(src, joel_frames, calib=None, fingers=None, hand_pose=None):
    """-> (F, ellie rows, 12) with every PART_ROWS row filled (scale 1, local q, local t).  calib = grip_calibration M:
    the right prop is placed so its attachment (the gun) = Ellie wrist * M * (Joel's attachment relative to his wrist,
    through K) - the Part I hold re-based on the TLOU2 hold.  fingers = finger_calibration (local pre-rotations)"""
    J, E = src.joel, src.ellie
    F = len(joel_frames)
    out = np.full((F, len(E.names), 12), np.nan)
    common = [n for n in E.names if n in J.idx]
    for f in range(F):
        jq, jp = _world(joel_frames[f], J.parent)
        Wq, Wp, Rws = {}, {}, {}
        for e, n in enumerate(E.names):                 # parents before children
            pe = E.parent[e]
            if n in J.idx and n not in PROPS and not n.endswith("_attachment"):
                j = J.idx[n]
                D = qmul(jq[j], qinv(J.wq[j]))
                Wq[e] = qnorm(qmul(D, E.wq[e]))
            elif pe >= 0:
                Wq[e] = qnorm(qmul(Wq[pe], E.bind[e, 4:8]))
            else:
                Wq[e] = E.bind[e, 4:8]
            Wp[e] = (Wp[pe] + qrot(Wq[pe], E.bind[e, 8:11])) if pe >= 0 else E.bind[e, 8:11]
            if n in AIM and AIM[n] in E.idx and AIM[n] in J.idx and E.parent[E.idx[AIM[n]]] == e:
                c, cj = E.idx[AIM[n]], J.idx[AIM[n]]
                want = jp[cj] - jp[J.idx[n]]
                have = qrot(Wq[e], E.bind[c, 8:11])
                if np.linalg.norm(want) > 1e-6 and np.linalg.norm(have) > 1e-6:
                    Wq[e] = qnorm(qmul(from_to(have / np.linalg.norm(have), want / np.linalg.norm(want)), Wq[e]))
            if n in ("l_wrist", "r_wrist"):
                Kw = qmul(qinv(E.wq[e]), J.wq[J.idx[n]])
                Rws[n[0]] = qmul(Wq[e], qmul(Kw, qinv(jq[J.idx[n]])))   # Joel world -> Ellie world about this wrist
            if HAND_AIM and n in FINGER_CHILD and FINGER_CHILD[n] in E.idx and FINGER_CHILD[n] in J.idx and n in J.idx:
                # finger bones aimed like Joel's in the WRIST frame (the frame the gun is carried in, Rw): the hand
                # wraps the gun as in Part I (the world-delta retarget alone left the tips ~3 cm off - p1_reload_hand.py)
                c, cj = E.idx[FINGER_CHILD[n]], J.idx[FINGER_CHILD[n]]
                want = qrot(Rws[n[0]], jp[cj] - jp[J.idx[n]])
                have = qrot(Wq[e], E.bind[c, 8:11])
                if np.linalg.norm(want) > 1e-6 and np.linalg.norm(have) > 1e-6:
                    Wq[e] = qnorm(qmul(from_to(have / np.linalg.norm(have), want / np.linalg.norm(want)), Wq[e]))
            if n in PROPS:
                side = n[0]
                w_e, w_j = E.idx[side + "_wrist"], J.idx[side + "_wrist"]
                j = J.idx[n]
                K = qmul(qinv(E.wq[w_e]), J.wq[w_j])            # Joel wrist axes -> Ellie wrist axes (bind)
                Rw = qmul(Wq[w_e], qmul(K, qinv(jq[w_j])))     # Joel world -> Ellie world about the wrist
                Wq[e] = qnorm(qmul(Rw, jq[j]))
                Wp[e] = Wp[w_e] + qrot(Rw, jp[j] - jp[w_j])
                if calib is not None and side == "r":
                    ja, ea = J.idx[RPROP_ATT], E.idx[RPROP_ATT]
                    x = _xmul((K, np.zeros(3)), _xmul(_xinv((jq[w_j], jp[w_j])), (jq[ja], jp[ja])))
                    att = _xmul((Wq[w_e], Wp[w_e]), _xmul(calib, x))           # where the gun goes
                    Wq[e], Wp[e] = _xmul(att, _xinv((E.bind[ea, 4:8], E.bind[ea, 8:11])))   # prop = att * inv(att local)
        for n in PART_ROWS:
            e = E.idx[n]
            pe = E.parent[e]
            q = qnorm(qmul(qinv(Wq[pe]), Wq[e]))
            if np.dot(q, E.bind[e, 4:8]) < 0:
                q = -q
            t = qrot(qinv(Wq[pe]), Wp[e] - Wp[pe]) if n in PROPS else E.bind[e, 8:11]
            out[f, e, 0:4] = (1.0, 1.0, 1.0, 0.0)
            out[f, e, 4:8] = q
            out[f, e, 8:12] = (*t, 0.0)
    for e, off in (fingers or {}).items():          # finger calibration (finger_calibration): local' = off * local
        for f in range(F):
            out[f, e, 4:8] = qnorm(qmul(off, out[f, e, 4:8]))
    for e, q in (hand_pose or {}).items():          # gun hand = the TLOU2 grip's hand pose (grip_hand_pose)
        out[:, e, 4:8] = q
    # sign continuity
    for n in PART_ROWS:
        e = E.idx[n]
        for f in range(1, F):
            if np.dot(out[f, e, 4:8], out[f - 1, e, 4:8]) < 0:
                out[f, e, 4:8] *= -1
    return out, common


def retarget_add(src, gun, stance):
    add, fps = src.clip(clip_name(gun, stance, "add"))
    J, E = src.joel, src.ellie
    out = np.full((len(add), len(E.names), 12), np.nan)
    for n in ADD_ROWS:
        out[:, E.idx[n]] = add[:, J.idx[n]]
    return out, fps


def gun_rows(src, gun, name):
    """Part I gun clip -> (F, 62, 12) TLOU2 pistol-base rows, every row written"""
    P, T = src.p1gun, src.t2gun
    g, fps = src.clip(name)
    rig = GUNS[gun]["rig"]
    F = len(g)
    out = np.zeros((F, len(T.names), 12))
    for f in range(F):
        loc = fill(g[f], P.bind)
        pq, pp = _world(loc, P.parent)
        Wq, Wp = {}, {}
        for e, n in enumerate(T.names):
            pe = T.parent[e]
            if n in rig:
                j = P.idx[rig[n]]
                Dq = qmul(pq[j], qinv(P.wq[j]))
                Wq[e] = qnorm(qmul(Dq, T.wq[e]))
                Wp[e] = pp[j] + qrot(Dq, T.wp[e] - P.wp[j])
            elif pe >= 0:
                Wq[e] = qnorm(qmul(Wq[pe], T.bind[e, 4:8]))
                Wp[e] = Wp[pe] + qrot(Wq[pe], T.bind[e, 8:11])
            else:
                Wq[e], Wp[e] = T.bind[e, 4:8], T.bind[e, 8:11]
            if pe >= 0:
                q = qnorm(qmul(qinv(Wq[pe]), Wq[e]))
                t = qrot(qinv(Wq[pe]), Wp[e] - Wp[pe])
            else:
                q, t = Wq[e], Wp[e]
            if np.dot(q, T.bind[e, 4:8]) < 0:
                q = -q
            s = loc[P.idx[rig[n]], 0:3] if n in rig else np.ones(3)
            out[f, e, 0:3] = s
            out[f, e, 4:8] = q
            out[f, e, 8:11] = t
    for e in range(len(T.names)):
        for f in range(1, F):
            if np.dot(out[f, e, 4:8], out[f - 1, e, 4:8]) < 0:
                out[f, e, 4:8] *= -1
    return out, fps


# ---------------------------------------------------------------- encode

def _slot(groups, k):
    for g, (n, _) in enumerate(groups):
        if k < n:
            return g, k
        k -= n
    raise ValueError(k)


def encode(rows, fps, groups, sig, written, kinds=("s", "q", "t"), additive=False):
    """rows (F, N, 12); `written`: row indices to write (all others stay untouched by the clip).  A component that never
    changes is a constant op; scale constants of exactly 1 are written too (an unwritten scale is 0 = collapsed row)."""
    import uc4enc
    F = len(rows)
    content, const = {}, {}
    for r in written:
        g, sl = _slot(groups, r)
        c = const.setdefault(g, dict(prefix=None, tr=[], quat=[]))
        cont = content.setdefault(g, {"comps": [], "frames": []})
        for kind in kinds:
            if kind == "q":
                v = rows[:, r, 4:8]
                ang = np.degrees(2 * np.arccos(np.clip(np.abs((v * v[0]).sum(1)), 0, 1))).max()
                if ang < CONST_EPS:
                    c["quat"].append((sl * 0x30 + 0x10, tuple(float(x) for x in qnorm(v[0]))))
                    continue
            else:
                v = rows[:, r, 0:3] if kind == "s" else rows[:, r, 8:11]
                if np.isnan(v).any():
                    continue
                if np.abs(v - v[0]).max() < (1e-4 if kind == "t" else 1e-3):
                    c["tr"].append((sl * 0x30 + (0 if kind == "s" else 0x20), tuple(float(x) for x in v[0])))
                    continue
            fr = np.zeros((F, 4), np.float32)
            fr[:, :v.shape[1]] = v
            cont["comps"].append((sl, kind))
            cont["frames"].append(fr)
    gc = {g: (c["comps"], np.stack(c["frames"], axis=1)) for g, c in content.items() if c["comps"]}
    const = {g: c for g, c in const.items() if c["tr"] or c["quat"]}
    clip = bytearray(uc4enc.build_clip(sig, fps, F, groups, gc, const=const))
    if additive:
        struct.pack_into("<H", clip, 0x20, 2)            # ClipData +0x20 flags: 2 = additive (as TLOU2's -add clips)
    return bytes(clip)


def resample_rows(rows, fps):
    if BODY_FPS >= fps:
        return rows, fps
    out, nf = resample(rows, fps, BODY_FPS)
    q = out[..., 4:8]
    n = np.linalg.norm(q, axis=-1, keepdims=True)
    out[..., 4:8] = np.where(n > 0, q / np.where(n > 0, n, 1), q)
    return out, nf


# ---------------------------------------------------------------- bake

def bake(gun, src=None, log=print):
    """-> {(stance, kind): (clip bytes, rows, fps, additive)} for every reload stance + the fire gun clip"""
    src = src or Source()
    E, T = src.ellie, src.t2gun
    out = {}
    part_idx = [E.idx[n] for n in PART_ROWS]
    add_idx = [E.idx[n] for n in ADD_ROWS]
    gun_idx = list(range(len(T.names)))
    calib = grip_calibration(src, gun, log) if GRIP_CAL else None
    # finger calibration: off (measurement: Part I's reload already starts with the index 2.6 cm off the trigger,
    # unlike its grip clip (0.4 cm); offsets taken against the grip made the start worse, 4.0 -> 4.5 cm, with up to 78 deg on
    # single joints). T2R_P1_FINGER_CAL=1 to try it.
    fingers = finger_calibration(src, gun, calib, log) if GRIP_CAL and os.environ.get("T2R_P1_FINGER_CAL") == "1" else None
    hand_pose = grip_hand_pose(src, gun, log) if os.environ.get("T2R_P1_HAND") == "grip" else None
    for st in STANCES:
        jf, fps = body_frames(src, gun, st)
        part, _ = retarget_part(src, jf, calib, fingers, hand_pose)
        part, pf = resample_rows(part, fps)
        out[(st, "part")] = (encode(part, pf, ELLIE_GROUPS, ELLIE_SIG, part_idx), part, pf, False)
        add, afps = retarget_add(src, gun, st)
        add, af = resample_rows(add, afps)
        out[(st, "add")] = (encode(add, af, ELLIE_GROUPS, ELLIE_SIG, add_idx, additive=True), add, af, True)
        gr, gfps = gun_rows(src, gun, clip_name(gun, st, "gun"))
        gr, gf = resample_rows(gr, gfps)
        out[(st, "gun")] = (encode(gr, gf, GUN_GROUPS, GUN_SIG, gun_idx), gr, gf, False)
        log(f"  {gun} {st}: part {len(out[(st, 'part')][0])} B ({len(part)} f @{pf:g}), add {len(out[(st, 'add')][0])} B, "
            f"gun {len(out[(st, 'gun')][0])} B ({len(gr)} f @{gf:g})")
    fg = GUNS[gun]["fire_gun"]
    gr, gfps = gun_rows(src, gun, fg)
    out[("fire", "gun")] = (encode(gr, gfps, GUN_GROUPS, GUN_SIG, gun_idx), gr, gfps, False)
    return out


def verify(baked, log=print):
    """decode every baked clip with the game's handlers; compare written rows with what was meant"""
    worst = 0.0
    for key, (clip, rows, fps, additive) in baked.items():
        got, gfps = decode(clip)
        assert got.shape[0] == rows.shape[0] and abs(gfps - fps) < 1e-3, (key, got.shape, rows.shape)
        m = ~np.isnan(rows)
        m[..., 3] = m[..., 11] = False              # padding lanes
        # quaternion sign is free
        a, b = got.copy(), rows.copy()
        s = np.sign((a[..., 4:8] * b[..., 4:8]).sum(-1, keepdims=True))
        s[s == 0] = 1
        a[..., 4:8] *= np.nan_to_num(s, nan=1.0)
        err = np.nanmax(np.abs(a - b)[m & ~np.isnan(a)]) if m.any() else 0.0
        miss = int((m & np.isnan(got)).sum())
        worst = max(worst, err)
        log(f"  verify {key}: max row error {err:.2e}, rows meant but not written {miss}")
        assert miss == 0 and err < 2e-3, key
    return worst


EVENT_KEEP = ("haptic-effect", "weapon-effect", "gear-effect-upper", "weapon-event", "weapon-reload", "sound-effect")
# Part I sound-effect events naming Part I-only sounds, played as weapon-effects of the host sound set instead
# (p1_sound.py; El Diablo's reload lacked sounds - the open / close at frames 1 / 45 were dropped)
SFX_TO_SUFFIX = {"sfx-weapon-pistol-uber-open": "revolver-open", "sfx-weapon-pistol-uber-close": "revolver-close"}
EVENT_NAMES_DROP = ("eject-magazine",)     # spawns the firearm-art +0x38 magazine prop (none on our guns)


def part_events(src, gun, stance, frames_new, known=None, log=print):
    """the Part I -part clip's own anim events (same vocabulary as TLOU2: weapon-reload = the ammo refill frame,
    weapon-event hide / show-magazine = the firearm-art +0x58 joint hidden while the clip teleports it, weapon-effect
    suffixes = the gun's sound set, haptics, gear foley), frames rescaled to the baked clip.  Dropped: eject-magazine
    (prop spawn) and sound-effects whose sound name TLOU2 does not know (Part I banks are not loaded).
    -> [(type sid, frame, [(key sid, value)])]"""
    a = src.anims
    it = a.clips[clip_name(gun, stance, "part")]["item"]
    k = a.k
    base = it + 0x30
    t = k.ptr(base + 0x28)
    if not t:
        return []
    import p1_carrier
    keep = {p1_carrier.fnv(n) for n in EVENT_KEEP}
    drop_names = {p1_carrier.fnv(n) for n in EVENT_NAMES_DROP}
    name_key = p1_carrier.fnv("name")
    sfx = p1_carrier.fnv("sound-effect")
    frames_src = struct.unpack_from("<H", a.clips[clip_name(gun, stance, "part")]["clip"], 0xe)[0]
    scale = (frames_new - 1) / max(frames_src - 1, 1)
    out, dropped = [], []
    for i in range(k.u32(t + 0x10)):
        e = k.ptr(t + 8) + 24 * i
        sid, fr, n = struct.unpack_from("<QfI", k.d, e)
        pl = k.ptr(e + 16)
        pairs = [struct.unpack_from("<QQ", k.d, pl + 16 * j) for j in range(n)] if pl else []
        names = [v for kk, v in pairs if kk == name_key]
        sfxmap = {p1_carrier.fnv(k2): v2 for k2, v2 in SFX_TO_SUFFIX.items()}
        remap = [sfxmap[v] for v in names if v in sfxmap]
        if sid == sfx and remap:
            # a Part I-only sound name played through the gun's sound set instead (weapon-effect suffix)
            sid = p1_carrier.fnv("weapon-effect")
            pairs = [(p1_carrier.fnv("suffix"), p1_carrier.fnv(remap[0]))] + [(kk, v) for kk, v in pairs if kk != name_key]
            names = []
        if sid not in keep or any(v in drop_names for v in names) or \
                (sid == sfx and known is not None and any(v not in known for v in names)):
            dropped.append(sid)
            continue
        out.append((sid, round(fr * scale, 3), pairs))
    return out


def save(gun, baked, events=None):
    import json
    os.makedirs(OUT, exist_ok=True)
    for (st, kind), (clip, rows, fps, add) in baked.items():
        open(os.path.join(OUT, f"p1-{gun}-{st}-{kind}.clip"), "wb").write(clip)
    for st, ev in (events or {}).items():
        json.dump([[s, f, [[a, b] for a, b in pr]] for s, f, pr in ev],
                  open(os.path.join(OUT, f"p1-{gun}-{st}-part.events.json"), "w"))


def load_baked(gun):
    """the baked clips of a previous `bake` run (build_dll reads these; no emulator needed at build time)"""
    out = {}
    for st in STANCES + ("fire",):
        for kind in ("part", "add", "gun"):
            p = os.path.join(OUT, f"p1-{gun}-{st}-{kind}.clip")
            if os.path.exists(p):
                out[(st, kind)] = open(p, "rb").read()
    return out


def load_events(gun):
    import json
    out = {}
    for st in STANCES:
        p = os.path.join(OUT, f"p1-{gun}-{st}-part.events.json")
        if os.path.exists(p):
            out[st] = [(s, f, [tuple(x) for x in pr]) for s, f, pr in json.load(open(p))]
    return out


def main(argv):
    if len(argv) < 2:
        print(__doc__)
        return 1
    guns = ["shorty", "diablo"] if len(argv) < 3 or argv[2] == "all" else [argv[2]]
    src = Source()
    for gun in guns:
        if argv[1] == "bake":
            b = bake(gun, src)
            verify(b)
            import p1_overlay
            known = set(p1_overlay.sid_names())
            ev = {st: part_events(src, gun, st, len(b[(st, "part")][1]), known) for st in STANCES}
            save(gun, b, ev)
            print(f"{gun}: {len(b)} clips, {sum(map(len, ev.values()))} anim events -> {OUT}")
        elif argv[1] == "events":           # only re-read the Part I events (no re-bake)
            import p1_overlay
            known = set(p1_overlay.sid_names())
            b = load_baked(gun)
            ev = {st: part_events(src, gun, st, struct.unpack_from("<H", b[(st, "part")], 0xe)[0], known)
                  for st in STANCES}
            save(gun, {}, ev)
            for st, e in ev.items():
                print(f"{gun} {st}: {len(e)} events")
        elif argv[1] == "preview":
            import p1_anim_preview
            p1_anim_preview.sheets(gun, src)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
