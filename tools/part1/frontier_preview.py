"""Contact sheets of the Frontier Rifle animations (re/frontier/preview/ in the main checkout):
  rechamber-ellie.png   the cycle as built: OUR baked arms layer (stand variant) decoded from the shipped clip over the player's
                        bolt-rifle pose, the Marlin posed by the NPC lever --gun clip (rifle-base rig), side + front
  rechamber-bolt.png    the same for the hunting rifle's own bolt cycle (what it replaces), for comparison
  rechamber-npc.png     the NPC source (anim-npc-m-lg base + add + gun) on the NPC rig
  reload-npc.png        the NPC full reload (--part + --add + --gun) on the NPC rig: the source of a future lever reload
  model-side.png        the Marlin model silhouette (the icon at 4x) and the shaded side view
  python frontier_preview.py [out dir]"""
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.dirname(HERE)
ROOT = os.path.dirname(TOOLS)
MAIN = ROOT.split(os.sep + ".claude" + os.sep)[0]
sys.path[:0] = [HERE, os.path.join(TOOLS, "models"), os.path.join(TOOLS, "features"), os.path.join(ROOT, "re", "uc4ps4", "tools")]
import p1_anims  # noqa: E402
import p1_carrier  # noqa: E402
import frontier_anims as fa  # noqa: E402
from p1_anim_preview import BONES, skin, place  # noqa: E402
from p1_rig import fill, fk, qmul, qinv, qnorm  # noqa: E402
import ndpak  # noqa: E402

PROP = "r_hand_prop_attachment"
RIFLE_BASE = os.path.join(ROOT, "re", "models", "rifle-base.pak")


def marlin():
    pk = p1_carrier.game_pak("rifle-marlin-lever")
    open(os.path.join(MAIN, "tools", "local", "_marlin.pak"), "wb").write(pk)
    p = ndpak.Pak(os.path.join(MAIN, "tools", "local", "_marlin.pak"))
    import struct
    P, J = [], []
    for sm in p.submeshes:
        if any(t in sm["name"] for t in ("LOD1", "LOD2")) or "pCylinder" in sm["name"] or "bullet_shell" in sm["name"]:
            continue
        pos = np.array(p.positions(sm))
        imap, wts = p.ptr(sm["skin"] + 16), p.ptr(sm["skin"] + 24)
        js = []
        for v in range(sm["vcount"]):
            c, at = struct.unpack_from("<II", p.d, imap + 8 * v)
            js.append(struct.unpack_from("<I", p.d, wts + at)[0] >> 22)
        P.append(pos)
        J.append(np.array(js))
    return np.concatenate(P), np.concatenate(J)


def draw(ax, rig, q, p, gun, a, b, ctr_name="spined", reach=(0.5, 0.5)):
    for x, y in BONES:
        if x in rig.idx and y in rig.idx:
            i0, i1 = rig.idx[x], rig.idx[y]
            col = "tab:red" if x.startswith("l_") else ("tab:blue" if x.startswith("r_") else "k")
            ax.plot([p[i0, a], p[i1, a]], [p[i0, b], p[i1, b]], "-", color=col, lw=1.2)
    ax.scatter(gun[:, a], gun[:, b], s=0.25, c="tab:orange")
    c = p[rig.idx[ctr_name]]
    ax.set_xlim(c[a] - (0.5 if a == 2 else 0.6), c[a] + (0.95 if a == 2 else 0.6))
    ax.set_ylim(c[b] - 0.7, c[b] + 0.45)
    ax.set_aspect("equal")
    ax.set_xticks([])
    ax.set_yticks([])


def sheet(path, title, frames, n=8):
    """frames: list of (label, [(rig, q, p, gunpts)]) per column; two rows (side, front)"""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, axs = plt.subplots(2, n, figsize=(2.3 * n, 5.6))
    for c, (lab, (rig, q, p, g)) in enumerate(frames):
        for r, (a, b) in enumerate(((2, 1), (0, 1))):
            draw(axs[r][c], rig, q, p, g, a, b)
        axs[0][c].set_title(lab, fontsize=8)
    axs[0][0].set_ylabel("side", fontsize=8)
    axs[1][0].set_ylabel("front", fontsize=8)
    fig.suptitle(title, fontsize=10)
    plt.tight_layout()
    plt.savefig(path, dpi=80)
    plt.close(fig)
    print("preview:", path)


def main(out):
    os.makedirs(out, exist_ok=True)
    gp, gj = marlin()
    rb = p1_anims.Rig(RIFLE_BASE)
    ell = p1_anims.Rig(p1_anims.ELLIE_SKEL)
    npc = p1_anims.Rig(fa.NPC_SKEL)
    nE = len(ell.names)
    gun_clip, gfps = p1_anims.decode(fa.clip_of(fa.NPC_PAK, fa.FRONTIER_GUN if hasattr(fa, "FRONTIER_GUN") else "npc-m-marlin-lever-idle-rechamber--gun"))
    gun_ours, _ = p1_anims.decode(open(os.path.join(fa.DATA, "gun.clip"), "rb").read())
    # 1. as built: our arms layer on the player's pose
    ours, ofps = p1_anims.decode(open(os.path.join(fa.DATA, "arms-stand.clip"), "rb").read())
    ref, _ = p1_anims.decode(fa.clip_of(fa.PLAYER_PAK, "rifle-remington-bolt-stand-rechamber-arms"))
    base_pose = fill(ref[0][:nE], ell.bind)
    n = 8

    def ellie_frame(rows, f, gunrows, fg):
        loc = np.where(np.isnan(rows[f][:nE]), base_pose, rows[f][:nE])
        q, p = fk(loc, ell.parent)
        g = place(skin(gp, gj, fill(gunrows[fg], rb.bind), rb), q, p, ell.idx[PROP])
        return ell, q, p, g

    cols = []
    for c in range(n):
        t = c / (n - 1)
        f = int(round(t * (len(ours) - 1)))
        fg = int(round(t * (len(gun_ours) - 1)))
        cols.append((f"{t * (len(ours) - 1) / ofps:.2f}s", ellie_frame(ours, f, gun_ours, fg)))
    sheet(os.path.join(out, "rechamber-ellie.png"), "Frontier Rifle rechamber as built: our baked arms layer (decoded from the shipped clip) + NPC lever gun clip, player rig", cols)
    # 2. the hunting rifle's bolt cycle (gun = the bolt rifle's own gun clip, model = the Marlin for scale)
    bolt_gun, bfps = p1_anims.decode(fa.clip_of(fa.PLAYER_PAK, "rifle-remington-bolt-stand-rechamber-gun"))
    cols = []
    for c in range(n):
        t = c / (n - 1)
        f = int(round(t * (len(ref) - 1)))
        fg = int(round(t * (len(bolt_gun) - 1)))
        cols.append((f"{t * (len(ref) - 1) / 30:.2f}s", ellie_frame(ref, f, bolt_gun, fg)))
    sheet(os.path.join(out, "rechamber-bolt.png"), "for comparison: the hunting rifle's bolt rechamber (what the Frontier replaces), same Marlin model", cols)
    # 3. NPC source
    nfr, add, nfps = fa.npc_frames(npc)
    nfr_full = nfr.copy()
    for f in range(len(add)):                      # spine too (the NPC's sway) for the source view
        for nm in fa.SPINE_ROWS:
            i = npc.idx[nm]
            if not np.isnan(add[f, i, 4]):
                nfr_full[f, i, 4:8] = qnorm(qmul(nfr[0, i, 4:8], add[f, i, 4:8]))
    cols = []
    for c in range(n):
        t = c / (n - 1)
        f = int(round(t * (len(nfr_full) - 1)))
        fg = int(round(t * (len(gun_clip) - 1)))
        q, p = fk(nfr_full[f], npc.parent)
        g = place(skin(gp, gj, fill(gun_clip[fg], rb.bind), rb), q, p, npc.idx[PROP])
        cols.append((f"{t * (len(nfr_full) - 1) / nfps:.2f}s", (npc, q, p, g)))
    sheet(os.path.join(out, "rechamber-npc.png"), "NPC source: npc-m-marlin-lever-idle-rechamber (--base + --add, --gun) on the NPC rig", cols)
    # 4. NPC reload
    base, _ = p1_anims.decode(fa.clip_of(fa.NPC_PAK, fa.NPC_BASE))
    part, rfps = p1_anims.decode(fa.clip_of(fa.NPC_PAK, "npc-m-marlin-lever-idle-reload-full--part"))
    radd, _ = p1_anims.decode(fa.clip_of(fa.NPC_PAK, "npc-m-marlin-lever-idle-reload-full--add"))
    rgun, _ = p1_anims.decode(fa.clip_of(fa.NPC_PAK, "npc-m-marlin-lever-idle-reload-full--gun"))
    n_npc = len(npc.names)
    b0 = fill(base[0][:n_npc], npc.bind)
    cols = []
    for c in range(n):
        t = c / (n - 1)
        f = int(round(t * (len(part) - 1)))
        loc = np.where(np.isnan(part[f][:n_npc]), b0, part[f][:n_npc])
        for nm in fa.SPINE_ROWS:
            i = npc.idx[nm]
            if not np.isnan(radd[f, i, 4]):
                loc[i, 4:8] = qnorm(qmul(b0[i, 4:8], radd[f, i, 4:8]))
        q, p = fk(loc, npc.parent)
        g = place(skin(gp, gj, fill(rgun[f], rb.bind), rb), q, p, npc.idx[PROP])
        cols.append((f"{f / rfps:.2f}s", (npc, q, p, g)))
    sheet(os.path.join(out, "reload-npc.png"), "NPC source: npc-m-marlin-lever-idle-reload-full (--part + --add + --gun), 116 frames: rounds inserted one by one", cols)
    # 4b. the reload as built (stand): start + mid (first 2.3 inserts) + end, decoded from the shipped clips, on the player rig
    import frontier_reload as fr
    for st in ("stand", "crouch"):
        grp = "crouch" if st.startswith("crouch") else "stand"
        bolt0, _ = p1_anims.decode(fa.clip_of(fa.PLAYER_PAK, f"ellie-sniper-bolt-reload-{st}-start-arms"))
        pose0 = fill(bolt0[0][:nE], ell.bind)
        seq = []
        for seg in fr.SEGS:
            arms, afps = p1_anims.decode(open(os.path.join(fa.DATA, f"reload-{st}-{seg}-arms.clip"), "rb").read())
            gunr, _ = p1_anims.decode(open(os.path.join(fa.DATA, f"reload-{grp}-{seg}-gun.clip"), "rb").read())
            take = len(arms) if seg != "mid" else min(len(arms), 44)       # the first ~3 inserts of the mid clip (the game cuts it when full)
            seq += [(arms[i], gunr[i]) for i in range(take)]
        cols = []
        for c in range(10):
            i = int(round(c / 9 * (len(seq) - 1)))
            a, gr = seq[i]
            loc = np.where(np.isnan(a[:nE]), pose0, a[:nE])
            q, p = fk(loc, ell.parent)
            g = place(skin(gp, gj, fill(gr, rb.bind), rb), q, p, ell.idx[PROP])
            cols.append((f"{i / 30:.2f}s", (ell, q, p, g)))
        sheet(os.path.join(out, f"reload-ellie-{st}.png"), f"Frontier Rifle one-round-at-a-time reload as built ({st}): start + mid (3 of 6 inserts) + end, decoded from the shipped clips", cols, n=10)
    # 4c. proof that the lever joint moves: the Marlin alone (gun space, side view, zoomed on the receiver / lever), red = the lever joints,
    # for the aimed rechamber (gun.clip, 1.1 s) and the reload start / mid / end gun layers; angle of the lever joint in every title
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    def lever_sheet(path, title, clips, n):
        fig, axs = plt.subplots(len(clips), n, figsize=(2.4 * n, 2.2 * len(clips)), squeeze=False)
        for r, (lab, rows) in enumerate(clips):
            for c in range(n):
                f = int(round(c / (n - 1) * (len(rows) - 1)))
                g = skin(gp, gj, fill(rows[f], rb.bind), rb)
                mv = np.isin(gj, [20, 21, 17])
                ax = axs[r][c]
                ax.scatter(g[~mv, 2], g[~mv, 1], s=0.25, c="0.45")
                ax.scatter(g[mv, 2], g[mv, 1], s=0.6, c="tab:red")
                ax.set_xlim(-0.12, 0.42)
                ax.set_ylim(-0.17, 0.17)
                ax.set_aspect("equal")
                ax.set_xticks([])
                ax.set_yticks([])
                a = np.degrees(2 * np.arccos(min(1.0, abs(float(np.dot(rows[f, 20, 4:8], rb.bind[20, 4:8]))))))
                ax.set_title(f"{lab} {f / 30:.2f}s lever {a:.0f} deg", fontsize=7)
        fig.suptitle(title, fontsize=9)
        plt.tight_layout()
        plt.savefig(path, dpi=80)
        plt.close(fig)
        print("preview:", path)
    lever_sheet(os.path.join(out, "lever-rechamber.png"), "Frontier aimed rechamber: gun layer (the lever joint, red) per frame", [("rechamber (NPC clip, native)", gun_clip)], 10)
    dg = {sg: p1_anims.decode(open(os.path.join(fa.DATA, f"rgun-{sg}.clip"), "rb").read())[0] for sg in ("start", "mid", "end")}
    lever_sheet(os.path.join(out, "lever-reload.png"), "Frontier reload gun layers: lever down (start), held open (mid), up (end)",
                [(sg, dg[sg]) for sg in ("start", "mid", "end")], 8)
    # 5. model
    from make_gun_icon import render
    from PIL import Image
    open(os.path.join(MAIN, "tools", "local", "_marlin.pak"), "rb").close()
    im = render(os.path.join(MAIN, "tools", "local", "_marlin.pak"), [0, 1], W=684, H=180, cuts=1, butt=True)
    bg = Image.new("RGBA", im.size, (70, 70, 70, 255))
    bg.alpha_composite(im)
    bg.save(os.path.join(out, "model-side.png"))
    print("preview:", os.path.join(out, "model-side.png"))


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else os.path.join(MAIN, "re", "frontier", "preview"))
