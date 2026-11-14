"""Contact sheets of the baked Part I gun animations (p1_anims.py) for a check before going in game.

Per gun and reload stance, 8 key frames, re/part1/preview/anim-<gun>-<stance>.png:
  row 1  Part I: Joel (the -part arm layer over its -base pose) holding the Part I gun posed by the Part I -gun clip
  row 2  TLOU2: Ellie's rig with OUR -part clip DECODED FROM THE BAKED FILE (game handlers, emulator) on the arms /
         head / fingers (the rest at Ellie's bind, spine bent like Joel's -base for comparison) holding the gun mesh
         skinned to the TLOU2 pistol-base rig and posed by OUR -gun clip decoded from the baked file
  rows 3-4 the same from the front.
The gun is the Part I model's LOD2 (only the parts the build keeps), red = the parts on a moving joint (magazine /
cylinder / rounds / hammer).  Also anim-<gun>-gun.png: the gun alone, TLOU2 rig vs Part I rig over the reload (side).
  python p1_anims.py preview [shorty|diablo]"""
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import p1_anims  # noqa: E402
from p1_rig import qmul, qinv, qnorm, qrot, fill, fk  # noqa: E402

BONES = [("root", "spinea"), ("spinea", "spineb"), ("spineb", "spinec"), ("spinec", "spined"), ("spined", "neck"),
         ("neck", "heada"), ("heada", "headb")] + \
    [(f"{s}_{a}", f"{s}_{b}") for s in "lr" for a, b in (("clavicle", "shoulder"), ("shoulder", "elbow"),
                                                           ("elbow", "wrist"), ("upper_leg", "knee"), ("knee", "ankle"))] + \
    [("spined", "l_clavicle"), ("spined", "r_clavicle"), ("root", "l_upper_leg"), ("root", "r_upper_leg")] + \
    [(f"{s}_wrist", f"{s}_{f}a") for s in "lr" for f in ("index", "middle", "ring", "pinky", "thumb")] + \
    [(f"{s}_{f}a", f"{s}_{f}b") for s in "lr" for f in ("index", "middle", "ring", "pinky", "thumb")] + \
    [(f"{s}_{f}b", f"{s}_{f}c") for s in "lr" for f in ("index", "middle", "ring", "pinky", "thumb")]
PROP = "r_hand_prop_attachment"


def gun_points(gun):
    """Part I LOD2 vertices of the kept parts: (P (n,3), Part I joint per vertex, TLOU2 joint per vertex)"""
    import p1_guns
    import p1mesh
    cfg = p1_guns.SHORTY if gun == "shorty" else p1_guns.DIABLO
    game = p1_guns.game_dir()
    k = p1mesh.P1Mesh(p1_guns.ensure_actor(game, cfg["p1"], cfg["archive"]))
    pj = p1mesh.joints(p1mesh.P1Mesh(p1_guns.ensure_actor(game, "pistol-base", "sp-common.psarc")))
    names, parent = [j["name"] for j in pj], [j["parent"] for j in pj]
    host = p1_guns.joint_names(p1_guns.find_model(cfg["host_base"]), False)
    jmap = p1_guns.joint_map(cfg, names, parent, host)
    hidden = p1_guns.hidden_mask(cfg, names, parent)
    t = k.submesh_table()
    P, J1, J2 = [], [], []
    for i in k.lods(t)[-1]:
        if any(s in k.material_name(t[i]["material"]) for s in cfg["drop_materials"]):
            continue
        d = k.mesh(t[i])
        J = np.asarray(d["J"])
        keep = ~hidden[J]
        P.append(d["P"][keep])
        J1.append(J[keep])
        J2.append(np.array([jmap[int(j)] for j in J[keep]]))
    return np.concatenate(P), np.concatenate(J1).astype(int), np.concatenate(J2).astype(int), names, host


def skin(P, J, local, rig):
    """vertices at bind -> posed (gun model space) with the rig's pose `local` (rows in rig order)"""
    wq, wp = fk(local, rig.parent)
    out = np.zeros_like(P)
    for j in np.unique(J):
        sel = J == j
        k = int(j)                                   # gun rigs: every joint animated, clip row = joint index
        dq = qmul(wq[k], qinv(rig.wq[k]))
        out[sel] = np.array([wp[k] + qrot(dq, v - rig.wp[k]) for v in P[sel]])
    return out


def place(Pg, wq, wp, idx):
    q, p = wq[idx], wp[idx]
    return np.array([p + qrot(q, v) for v in Pg])


def sheets(gun, src=None):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    src = src or p1_anims.Source()
    J, E, P1G, T2G = src.joel, src.ellie, src.p1gun, src.t2gun
    gp, gj1, gj2, p1names, host = gun_points(gun)
    moving1 = np.isin(gj1, [p1names.index(v) for v in p1_anims.GUNS[gun]["rig"].values()])
    os.makedirs(p1_anims.PREVIEW, exist_ok=True)
    for st in p1_anims.STANCES:
        jf, fps = p1_anims.body_frames(src, gun, st)
        part_clip = open(os.path.join(p1_anims.OUT, f"p1-{gun}-{st}-part.clip"), "rb").read()
        gun_clip = open(os.path.join(p1_anims.OUT, f"p1-{gun}-{st}-gun.clip"), "rb").read()
        ours, ofps = p1_anims.decode(part_clip)
        ogun, gfps = p1_anims.decode(gun_clip)
        p1gun, p1gfps = src.clip(p1_anims.clip_name(gun, st, "gun"))
        n = 8
        ts = np.linspace(0, 1, n)
        fig, axs = plt.subplots(4, n, figsize=(2.4 * n, 10.5))
        for c, tt in enumerate(ts):
            fj = int(round(tt * (len(jf) - 1)))
            fo = int(round(tt * (len(ours) - 1)))
            fg1 = int(round(tt * (len(p1gun) - 1)))
            fg2 = int(round(tt * (len(ogun) - 1)))
            # Joel
            jq, jp = fk(jf[fj], J.parent)
            g1 = skin(gp, gj1, fill(p1gun[fg1], P1G.bind), P1G)
            g1w = place(g1, jq, jp, J.idx[PROP])
            # Ellie: Joel's spine (world delta) under OUR decoded arm rows
            loc = E.bind.copy()
            for e, nm in enumerate(E.names):
                if nm in J.idx and nm in ("root", "spinea", "spineb", "spinec", "spined", "pelvis"):
                    j = J.idx[nm]
                    pe = E.parent[e]
                    D = qmul(jq[j], qinv(J.wq[j]))
                    W = qmul(D, E.wq[e])
                    pq = fk(loc, E.parent)[0][pe] if pe >= 0 else np.array([0, 0, 0, 1.0])
                    loc[e, 4:8] = qnorm(qmul(qinv(pq), W))
            loc = fill(ours[fo], loc)
            eq, ep = fk(loc, E.parent)
            g2 = skin(gp, gj2, fill(ogun[fg2], T2G.bind), T2G)
            g2w = place(g2, eq, ep, E.idx[PROP])
            for row, (q, p, rig, gw, lab) in enumerate(((jq, jp, J, g1w, "Part I Joel"), (eq, ep, E, g2w, "TLOU2 Ellie (baked)"))):
                for v, (a, b, vl) in enumerate(((2, 1, "side"), (0, 1, "front"))):
                    ax = axs[row + 2 * v][c]
                    for x, y in BONES:
                        if x in rig.idx and y in rig.idx:
                            i0, i1 = rig.idx[x], rig.idx[y]
                            col = "tab:red" if x.startswith("l_") else ("tab:blue" if x.startswith("r_") else "k")
                            ax.plot([p[i0, a], p[i1, a]], [p[i0, b], p[i1, b]], "-", color=col, lw=1.3)
                    ax.scatter(gw[~moving1, a], gw[~moving1, b], s=0.3, c="0.35")
                    ax.scatter(gw[moving1, a], gw[moving1, b], s=0.6, c="tab:orange")
                    ctr = p[rig.idx["spined"]]
                    ax.set_xlim(ctr[a] - (0.45 if a == 2 else 0.55), ctr[a] + (0.95 if a == 2 else 0.55))
                    ax.set_ylim(ctr[b] - 0.75, ctr[b] + 0.45)
                    ax.set_aspect("equal")
                    ax.set_xticks([])
                    ax.set_yticks([])
                    if c == 0:
                        ax.set_ylabel(f"{lab}\n{vl}", fontsize=8)
                    if row == 0 and v == 0:
                        ax.set_title(f"t={tt * (len(jf) - 1) / fps:.2f}s", fontsize=8)
        fig.suptitle(f"{gun} reload '{st}' ({p1_anims.clip_name(gun, st, 'part')}): Part I vs baked TLOU2 clip "
                     f"(decoded), orange = gun parts on moving joints", fontsize=10)
        plt.tight_layout()
        dst = os.path.join(p1_anims.PREVIEW, f"anim-{gun}-{st}.png")
        plt.savefig(dst, dpi=80)
        plt.close(fig)
        print("preview:", dst)
