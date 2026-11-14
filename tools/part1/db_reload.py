"""Double Barrel reload, re-timed (the reload felt stiffly slow).

WHICH clips play (root cause, from the overlay debug log): the reload state asks the overlay for 1p-reload--part / 1p-reload /
weapon-anim-reload-clip; player-overlays.bin anim-overlay-player-weapon-base-shotgun renames them to shotgun-baserri-reload-stand-
<part / add / gun>, weapon-tweaks-aim (aiming) renames those to ...-stand-aim-*, prone-position-supine to ...-supine-*, and the lookup
ends there.  The DB module's second set, anim-overlay-player-weapon-upgrades-shotgun-baserri-over-under-stock (layer weapon-upgrades, the
SP workbench STOCK upgrade, HUD_WORKBENCH_SHOTGUN_ABBY_STOCK), would rename the result to shotgun-baserri-reload-STOCK-*, but MP never
applies that upgrade layer: every lookup of the final name answered "no entry" and the game played its own non-stock clip.  The 3cc939f
bake (stock clips, the stock set's 'to' slots pointed at the carriers) therefore never played.  Now: the PLAYED clips
shotgun-baserri-reload-<stance>-<layer> (anim-player-gun-abby, 66 frames @30 = 2.17 s, layers part / add / gun) are re-timed, carried on
the Abby workbench paks, and t2r-ext answers the final lookup (the one that finds no entry, so the aim / supine renames still run
first) with a rename to the carrier (tools/ext/db_reload_built.h, written by build_dll.stage_db_reload).

Speed: the engine's reload rate = the reload-speed upgrade stat x firearm def +0x2c (exe 0x1411863e0, called by the reload start
0x140be06f0; no MP upgrade, stat 1).  t2r-ext sets the DB's +0x2c ABSOLUTE to 0.80 = the 2013 2.71 s (t2r-db-reload-speed.txt overrides;
it used to multiply the MP def's own 0.5 -> x0.40, a 5.4 s reload); the map below is baked for PLAY_SPEED.
SP (normal = the same speed as SP): retail bin.psarc weapon-gameplay.bin has the DB's +0x2c at 1.0 and Abby's Bullet
Loops workbench upgrade (weapon-upgrades.bin reload-speed set: 1.5) makes it x1.5, so SP plays the 66-frame clip in 1.44 s (2.17 s without
Bullet Loops).  An SP gun with the Stock upgrade plays the -stock- clips (same 66 frames, shells from the stock: the hand never goes to the
bag; breech-open / insert / close at src 1 / 22 / 36 vs 4 / 25 / 42); MP keeps the non-stock bag reach (the 2013 move) at SP's rate.  The clip keeps its 66 frames / 30 fps and only its time axis is re-mapped: output frame
t shows the source pose at s(t) (open + reach, and load + close at real-time 1.0x, ONLY the frames the hand is inside
the bag slowed - measured per stance by FK, bag_window); every
event of every layer follows the inverse map, so each sound / haptic / weapon event stays on the motion it belongs to.

Layers part / add / gun share the stance's map (the strap layer stays as is).  Baked clips are carried by the SP-only Abby workbench paks
(p1_carrier.build, as the Frontier's lever clips are).

  python db_reload.py           bake all stances, print the maps, self-check (decode back: ends identical, monotone map)
  python db_reload.py save      bake and commit the clips (tools/features/data/db-reload)
"""
import os
import struct
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path[:0] = [HERE, os.path.dirname(HERE), os.path.join(os.path.dirname(HERE), "features")]
import p1_carrier  # noqa: E402
import p1_anims  # noqa: E402
import frontier_anims as fa  # noqa: E402
from dcfile import fnv  # noqa: E402

SRC_PAK = "anim-player-gun-abby"
STANCES = ["stand", "stand-aim", "stand-relaxed", "crouch", "crouch-aim", "prone", "supine"]
LAYERS = ("part", "add", "gun")
KIND = {"part": "part", "add": "add", "gun": "gun"}
BODY_SIG, GUN_SIG = 0xc1cca4f4, 0xd39433bb
# carrier paks (SP workbench paks no MP match plays): body clips (part / add) and gun clips (the gun clips need a pool of 7 x ~12.4 KB)
BODY_CARRIER, GUN_CARRIERS = "anim-abby-workbench", ["anim-abby-workbench-boar", "anim-abby-workbench-dblbarrel"]   # (the gun pools are fragmented: 6 clips fit the first)
# more SP-only Abby workbench paks for body clips once BODY_CARRIER's 39 body slots are taken (the M14 right-hand clips, m14_hand.py)
EXTRA_BODY_CARRIERS = ["anim-abby-workbench-crossbow", "anim-abby-workbench-military", "anim-abby-workbench-velazquez"]
# body clips authored on ellie-skel (the M14's prone Vepr grips): the Ellie-rig slots of an SP-only Ellie workbench pak no other feature uses
ELLIE_SIG, ELLIE_BODY_CARRIERS = 0x5abe1b4c, ["anim-ellie-workbench-a-semi-auto"]


def clip_name(stance, layer):
    """the clip MP plays (the non-stock reload; the -stock- variants need the SP stock upgrade's overlay layer, see the top)"""
    return f"shotgun-baserri-reload-{stance}-{layer}"


# Open and hand into backpack play NORMALLY (1.0x), then slow down a lot while the hand is in the bag
# (however long needed), and then the load and close play NORMALLY (1.0x). Normal = the same speed as SP,
# so the regular pieces run at SP_RATE (SP's real-time rate, x1.5 with Bullet Loops).  Three pieces, linear, no easing:
#   [0, E]      open + the reach to the bag: SP speed (source frames advance SP_RATE / PLAY_SPEED per output frame);
#   [E, L]      the hand IN the bag: one constant slow speed that takes every output frame the two SP-speed pieces leave;
#   [L, end]    out of the bag with the shells, insert, close, settle: SP speed.
# E / L are measured on each stance's own part clip (bag_window): the right hand's centre (r_wrist .. r_middleb midpoint) in the spined
# frame enters / leaves a 10 cm sphere around the bag point BAG_PT (the mean of the 7 stances' deepest reach behind the back, measured
# per stance: stand 15, stand-aim 20, relaxed 19, crouch 18, crouch-aim 19, prone 25, supine 20), sub-frame by linear crossing.  The clip keeps
# its 66 frames, so with PLAY_SPEED 0.80 the reload lasts the 2013 2.71 s and only the in-bag piece is longer than native.
PLAY_SPEED = 0.80
SP_RATE = 1.5 * 0.55   # open / reach / load / close at 55 % of SP-with-Bullet-Loops speed, in-bag shorter, total unchanged (2.71 s)
BAG_PT = np.array([-17.1, 9.9, -14.7])      # cm, spined frame (x = right -, y = back +, z = up +)
BAG_RAD = 10.0                               # cm
_RIG = None


def hand_track(rows):
    """(F, 3) right-hand centre in the spined frame (cm) of a decoded abby-skel part clip (rows over the bind)"""
    global _RIG
    import db_hold
    from p1_rig import fk, qrot, qinv
    if _RIG is None:
        _RIG = db_hold.rig("abby-skel")
    R = _RIG
    W, nj = R.idx, min(rows.shape[1], len(R.names))
    out = []
    for f in range(len(rows)):
        L = R.bind.copy()
        r = rows[f, :nj]
        m = ~np.isnan(r[:, 4])
        L[:nj][m, 4:8] = r[m, 4:8]
        mt = ~np.isnan(r[:, 8])
        L[:nj][mt, 8:11] = r[mt, 8:11]
        wq, wp = fk(L, R.parent)
        sq, sp = wq[W["spined"]], wp[W["spined"]]
        c = (wp[W["r_wrist"]] + wp[W["r_middleb"]]) / 2
        out.append(qrot(qinv(sq), c - sp) * 100)
    return np.array(out)


def bag_window(rows):
    """(E, L, closest frame, its distance cm): sub-frame source frames where the right hand enters / leaves the bag"""
    d = np.linalg.norm(hand_track(rows) - BAG_PT, axis=1)
    P = int(np.argmin(d[:50]))
    assert d[P] < BAG_RAD, ("the hand never reaches the bag", P, d[P])
    i = P
    while i > 0 and d[i - 1] < BAG_RAD:
        i -= 1
    j = P
    while j < len(d) - 1 and d[j + 1] < BAG_RAD:
        j += 1
    E = (i - 1) + (d[i - 1] - BAG_RAD) / (d[i - 1] - d[i])
    L = j + (BAG_RAD - d[j]) / (d[j + 1] - d[j])
    return float(E), float(L), P, float(d[P])


def make_map(ev, last, E, L, play=PLAY_SPEED, sp=SP_RATE):
    """ev: [(sid, frame, ...)] of the stance's part clip, E / L its bag window; returns (fwd: output frame -> source frame, inv, source knots,
    rows)"""
    named = lambda nm: sorted(f for s, f, pr in ev if any(v == fnv(nm) for _, v in (pr or [])))
    op, ins = named("breech-open"), named("insert-round")
    assert op and ins, ("reload anchors missing", op, ins)
    assert op[0] < E < L < min(f for f in ins if f > E), ("bag window not between the open and the insert", op, E, L, ins)
    v = sp / play                                   # source frames per output frame = SP's real-time rate
    Ta, Tb = E / v, last - (last - L) / v           # output frames: bag entered / left
    D, dS = Tb - Ta, L - E
    k = dS / D * play                               # in-bag speed (x the clip's native 30 fps, real time)
    assert D > 0 and 0 < k < sp, ("the regular pieces leave no time for the bag", E, L, Ta, Tb)

    def fwd(t):
        t = np.clip(np.asarray(t, dtype=float), 0.0, last)
        out = np.where(t < Ta, t * v, np.where(t > Tb, L + (t - Tb) * v, E + (t - Ta) * (dS / D)))
        return np.minimum(out, last)

    def inv(s):
        s = float(s)
        if s <= E:
            return s / v
        if s >= L:
            return Tb + (s - L) / v
        return Ta + (s - E) * D / dS
    fps_out = 30.0 * play
    rows = [f"open+reach src 0-{E:.2f} = {Ta / fps_out:.3f} s (x{sp:.2f})", f"IN BAG src {E:.2f}-{L:.2f}: {dS / 30:.3f} s native -> {D / fps_out:.3f} s (x{k:.3f})",
            f"out+load+close src {L:.2f}-{last} = {(last - Tb) / fps_out:.3f} s (x{sp:.2f})"]
    return fwd, inv, [0.0, E, L, float(last)], rows


def _clip(pak_bytes, p, a, name):
    base, ca, size, sig = a[name]
    return bytes(p.d[ca:ca + size])


def bake(log=print):
    """-> (jobs {body: [...], gun: [...]} for p1_carrier.build, {(stance, layer): (carrier key, new clip name key)}, info rows)"""
    raw = p1_carrier.game_pak(SRC_PAK)
    p = p1_carrier.load(raw)
    a = p1_carrier.anims(p)
    jobs = {"body": [], "gun": []}
    info = []
    for st in STANCES:
        frames, ev = p1_carrier.ref_events(raw, clip_name(st, "part"))
        keys = sorted({round(f, 3) for _, f, _ in ev})
        c0 = _clip(raw, p, a, clip_name(st, "part"))
        E, L, P, dP = bag_window(p1_anims.decode(c0)[0])
        fwd, inv, k, kinds = make_map(ev, frames - 1, E, L)
        kinds = [f"hand closest to the bag at src {P} ({dP:.1f} cm)"] + kinds
        for layer in LAYERS:
            name = clip_name(st, layer)
            c = _clip(raw, p, a, name)
            rows, fps = p1_anims.decode(c)
            nf = len(rows)
            assert nf == frames, (name, nf, frames)
            pos = np.minimum(fwd(np.arange(nf)), nf - 1)
            out = fa.sample_rows(rows, pos)
            written = [i for i in range(rows.shape[1]) if not np.all(np.isnan(rows[:, i, 4]))]
            additive = struct.unpack_from("<H", c, 0x20)[0] == 2
            new = p1_anims.encode(out, fps, fa._groups(c), struct.unpack_from("<I", c, 4)[0], written, additive=additive)
            fr, evs = p1_carrier.ref_events(raw, name)
            evs = [(sid, round(inv(f), 3), pr) for sid, f, pr in evs]          # (identity at the keys; the gun's own events follow the inverse map)
            sig = struct.unpack_from("<I", c, 4)[0]
            jobs["gun" if sig == GUN_SIG else "body"].append((f"{st}|{layer}", new, KIND[layer], evs or None))
            info.append((st, layer, name, nf, fps, len(c), len(new), keys, k, kinds))
            # self-check: decoded back, the key frames equal the source's
            back, _ = p1_anims.decode(new)
            q = np.nan_to_num(rows[:, :, 4:8]) * np.sign(np.nan_to_num(rows[:, :, 7:8]) + 1e-12)
            qb = np.nan_to_num(back[:, :, 4:8]) * np.sign(np.nan_to_num(back[:, :, 7:8]) + 1e-12)
            for kf in (0, nf - 1):                                              # (the map retimes the inside; the ends stay)
                err = np.abs(q[kf] - qb[kf]).max()
                assert err < 5e-3, f"{name}: key frame {kf} differs by {err:.4f}"
    return jobs, info


DATA = os.path.join(os.path.dirname(HERE), "features", "data", "db-reload")


def save(jobs):
    """bake once, commit the clips: the build loads them (no emulator, no minutes of decoding per build)"""
    import json
    os.makedirs(DATA, exist_ok=True)
    meta = {}
    for grp, lst in jobs.items():
        for key, clip, kind, evs in lst:
            fn = key.replace("|", "-") + ".clip"
            open(os.path.join(DATA, fn), "wb").write(clip)
            meta[key] = dict(file=fn, kind=kind, group=grp, events=[[sid, fr, [list(x) for x in pr]] for sid, fr, pr in (evs or [])])
    json.dump(meta, open(os.path.join(DATA, "meta.json"), "w"), indent=1)


def load():
    """jobs {'body': [...], 'gun': [...]} of `save` (committed data)"""
    import json
    meta = json.load(open(os.path.join(DATA, "meta.json")))
    jobs = {"body": [], "gun": []}
    for key, m in sorted(meta.items()):
        evs = [(sid, fr, [tuple(x) for x in pr]) for sid, fr, pr in m["events"]] or None
        jobs[m["group"]].append((key, open(os.path.join(DATA, m["file"]), "rb").read(), m["kind"], evs))
    return jobs


def _body_slots(pak):
    return sum(1 for v in p1_carrier.anims(p1_carrier.load(p1_carrier.game_pak(pak))).values() if v[3] == BODY_SIG)


def carriers(jobs):
    """[(carrier pak, body sig, use gun slots, jobs)] for p1_carrier.build: the body clips in BODY_CARRIER (in job order; what outgrows its body
    slots spills to EXTRA_BODY_CARRIERS), the gun clips over GUN_CARRIERS and then BODY_CARRIER's own rifle-base slots (the played non-stock gun
    clips, 7 x ~12 KB, outgrow the two gun pools; a clip that does not fit a pool moves on to the next pak).  Body sig 1 = no body slot of that
    pak is touched (sig 1 matches no rig)."""
    left = list(jobs["gun"])
    sig = lambda j: struct.unpack_from("<I", j[1], 4)[0]
    body_left = [j for j in jobs["body"] if sig(j) != ELLIE_SIG]
    ellie = [j for j in jobs["body"] if sig(j) == ELLIE_SIG]
    out = []
    for pak in GUN_CARRIERS + [BODY_CARRIER] + EXTRA_BODY_CARRIERS:
        body = body_left[:_body_slots(pak)] if pak == BODY_CARRIER or pak in EXTRA_BODY_CARRIERS else []
        mine = list(left)
        while mine or body:
            try:
                p1_carrier.build(body + mine, lambda *a: None, pak=pak, body_sig=BODY_SIG if body else 1, gun_sig=GUN_SIG, use_gun=True)
                break
            except SystemExit as e:
                if "pool full" not in str(e) and "carriers" not in str(e):
                    raise
                if mine:
                    mine.pop()
                else:
                    body.pop()
        left = left[len(mine):]
        body_left = body_left[len(body):]
        if mine or body:
            out.append((pak, BODY_SIG if body else 1, bool(mine), body + mine))
    for pak in ELLIE_BODY_CARRIERS:
        if not ellie:
            break
        mine = ellie[:sum(1 for v in p1_carrier.anims(p1_carrier.load(p1_carrier.game_pak(pak))).values() if v[3] == ELLIE_SIG)]
        while mine:
            try:
                p1_carrier.build(mine, lambda *a: None, pak=pak, body_sig=ELLIE_SIG, gun_sig=GUN_SIG, use_gun=False)
                break
            except SystemExit as e:
                if "pool full" not in str(e) and "carriers" not in str(e):
                    raise
                mine.pop()
        ellie = ellie[len(mine):]
        if mine:
            out.append((pak, ELLIE_SIG, False, mine))
    assert not ellie, f"{len(ellie)} ellie-skel body clips left without a carrier slot"
    assert not left, "gun clips left without a carrier pool"
    assert not body_left, f"{len(body_left)} body clips left without a carrier slot"
    return out


def played_name(key):
    st, layer = key.split("|")
    return clip_name(st, layer)


EXT_HEADER = os.path.join(os.path.dirname(HERE), "ext", "db_reload_built.h")


def write_ext_header(names, played=None, gated=()):
    """tools/ext/db_reload_built.h (generated, not committed): {played clip sid, carrier clip sid} pairs; t2r-ext's overlay find-entry hook
    answers a lookup of a played name that found no entry with a rename to its carrier (names = {key: carrier}, {} = none; played =
    {key: played clip name} for keys that are not stance|layer, e.g. db_hold's aim adds)"""
    nl = chr(10)
    pn = lambda k: (played or {}).get(k) or played_name(k)
    rows = "".join(f"    {{0x{fnv(pn(k)):016x}ULL, 0x{fnv(c):016x}ULL}},   // {pn(k)} -> {c}" + nl
                   for k, c in sorted(names.items()))
    # gated = keys whose played name the ext answers ONLY while the Semi-Auto Rifle's overlay set is on (the M14 hold / hand clips: the Vepr,
    # Galil and Burst Rifle play the same rifle-vepr-grip-* names)
    gnames = sorted({pn(k) for k in gated if k in names})
    grows = "".join(f"    0x{fnv(n):016x}ULL,   // {n}" + nl for n in gnames)
    text = ("// generated by tools/part1/db_reload.py (build_dll.stage_db_reload) - do not edit, do not commit" + nl +
            f"#define T2R_DB_RELOAD_N {len(names)}" + nl +
            "static const uint64_t DB_RELOAD_MAP[][2] = {" + nl + (rows or "    {0, 0}," + nl) + "};" + nl +
            f"#define T2R_M14_GATED_N {len(gnames)}" + nl +
            "static const uint64_t M14_GATED[] = {" + nl + (grows or "    0," + nl) + "};" + nl)
    old = open(EXT_HEADER, encoding="utf-8").read() if os.path.exists(EXT_HEADER) else None
    if old != text:
        open(EXT_HEADER, "w", encoding="utf-8", newline=nl).write(text)
    return text


def main():
    jobs, info = bake()
    if len(sys.argv) > 1 and sys.argv[1] == "save":
        save(jobs)
        print("saved", DATA)
        jobs = load()
    for st, layer, name, nf, fps, osz, nsz, keys, k, kinds in info:
        if layer == "part":
            print(f"{st:14s} {nf} frames @{fps:g} x{PLAY_SPEED:.2f} = {(nf - 1) / fps / PLAY_SPEED:.3f} s  knots (0, bag in, bag out, end) "
                  f"{[round(x, 2) for x in k]}: {'; '.join(kinds)}")
    n_body, n_gun = len(jobs["body"]), len(jobs["gun"])
    print(f"baked {n_body} body clips ({sum(len(j[1]) for j in jobs['body'])} bytes), {n_gun} gun clips ({sum(len(j[1]) for j in jobs['gun'])} bytes)")
    allnames = {}
    for pak, bsig, use_gun, js in carriers(jobs):
        data, names = p1_carrier.build(js, print, pak=pak, body_sig=bsig, gun_sig=GUN_SIG, use_gun=use_gun)
        p1_carrier.check(data, {names[j[0]]: j[1] for j in js})
        allnames.update(names)
    for k, c in sorted(allnames.items()):
        print(f"  {played_name(k)} -> {c}")


if __name__ == "__main__":
    main()
