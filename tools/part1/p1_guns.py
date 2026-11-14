"""Part I Shorty / El Diablo models transplanted into a TLOU2 host pak (deagle.py route).

The Part I paks cannot load in TLOU2 (re/part1/day-one-results.md), so the geometry is read with p1mesh.py and
written into a copy of a TLOU2 gun pak with tools/models/mesh_replace.py.  Both guns use the same host
(re/part1/weapons.md section 9): pistol-a-semi-auto.pak (actor pistol-beretta, TLOU2 pistol-base rig: magazine,
mag_bullet, slide, hammer, cylinder_arm / cylinder / shell + bullet joints - every joint the Part I reloads move has a
TLOU2 counterpart; the Shorty is a one-handed pistol-grip gun with a detachable shell magazine, NOT a break-action
double barrel, so the old over-under host and its break-open reload are gone):
  Shorty    <- Part I t1x-pistol-shotgun        renamed pistol-shorty1  (same length as pistol-beretta)
  El Diablo <- Part I t1x-pistol-uber-t1        renamed pistol-diablo1
Per LOD all kept Part I submeshes become ONE host submesh (the beretta body material: colour / normal / Pack_RO_AO_ME,
the same pack layout as Part I); EVERY other host submesh with vertices is emptied (one degenerate triangle).  Part I
uses several materials per gun, so the textures of the used materials (full-res, from the Part I texture dictionaries)
are packed into one power-of-two atlas per slot (tiles with an edge-extended gutter for the mip chain) and the UVs
remapped; injected through pak_editor_cli inject-texture (it re-encodes a full mip chain at the new size and rewrites
the descriptor).  The host material's extra layers (BaseColor02 / 04, their masks, detail normal) are overwritten with
the atlas colour / neutral maps, so no beretta wear layer can blend over the atlas (the striped / patchy look of the
first Diablo build came from the host material's own layer masks sampled at the atlas UVs).
Kept: the parts Part I shows in the chosen upgrade state (hidden joints from Part I's weapon-upgrades.bin
weapon-mods-joint-array lists: every vertex under a hidden joint is dropped) minus the scope glass materials.
Skinning: one rigid influence per vertex: the Part I joint, or its nearest ancestor, that drives a TLOU2 joint in
p1_anims.GUNS[gun]['rig'] (the table the reload / fire gun clips are baked with), else the host root.

Needs (read-only): the Part I install - env T2R_P1_GAME or <main repo>/re/part1/game-path.txt - and the pak editor
CLI (tlou2_pak_editor, main checkout).  Everything extracted goes to <main repo>/re/part1/ (not in the repo).
A build with T2R_P1_GUNS=1 and no Part I install stops (no silent fallback to the TLOU2-made models).
  python p1_guns.py shorty|diablo|colt [out.pak] [--preview]     (preview -> re/part1/preview/<gun>-*.png)
  python p1_guns.py shorty|diablo --parts                 (every part in red, kept / hidden -> <gun>-parts.png)
Wired into build_dll through tools/models/factions_guns.py when T2R_P1_GUNS=1."""
import collections
import io
import os
import struct
import subprocess
import sys
import tempfile
import sys as _t2s, os as _t2o; _t2s.path.append(_t2o.path.normpath(_t2o.path.join(_t2o.path.dirname(_t2o.path.abspath(__file__)), ".."))); import t2rtmp  # noqa: E402,F401  (temp hygiene: tools/t2rtmp.py)

import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
MODELS = os.path.join(os.path.dirname(HERE), "models")
sys.path.insert(0, HERE)
sys.path.insert(0, MODELS)
import mesh_replace  # noqa: E402
import ndpak  # noqa: E402
import p1_archive  # noqa: E402
import p1_render  # noqa: E402
import p1mesh  # noqa: E402
import rename_pak  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(HERE))
MAIN = os.environ.get("T2R_MAIN_ROOT", ROOT.split(os.sep + ".claude" + os.sep)[0])
P1DIR = os.path.join(MAIN, "re", "part1")
ACTORS = os.path.join(P1DIR, "x", "actors")
INDEX = os.path.join(P1DIR, "texdict-index.tsv")
PREVIEW = os.path.join(P1DIR, "preview")
ATLAS_MAX = int(os.environ.get("T2R_P1_ATLAS", "2048"))     # largest atlas side (power of two)
GUTTER = 1 / 32                                             # gutter per tile side (fraction of the tile): mips down to
                                                            # tile/32 px keep their tiles apart
DXGI_BPB = {71: 8, 72: 8, 80: 8, 83: 16, 98: 16}
GLASS = ("glass", None, None)                               # atlas key of the synthetic lens tile
GLASS_TILE = {"color": (16, 22, 30), "normal": (128, 128, 255), "pack": (28, 255, 0)}   # roughness low, AO 1, metal 0

HOST = dict(host="pistol-a-semi-auto.pak", host_base="pistol-base.pak", old_actor="pistol-beretta",
            targets=[1, 4, 7])           # low__ay LODShape0 / 1 / 2: physical-character, BaseColor01 / Normal01 / Pack_RO_AO_ME_01
# host material slots overwritten so its extra layers can't show (slot name part -> what goes in)
NEUTRAL_SLOTS = {"BaseColor02": "color", "BaseColor04": "color", "Generic03": "black", "Generic04": "black",
                 "LinearBlend04": "black", "Threshold04": "black", "BGDetailNormal04": "flat"}

# Hidden Part I joints (every vertex under one is dropped).  Part I's weapon-upgrades.bin (bin.psarc dc1) has
# weapon-mods-joint-array lists {joint, visible}; the Shorty's default list @0x5738 hides exactly SHORTY_HIDDEN (the
# upgrade parts: extended magazine mag_mod, leather grip wrap grip_mod, speed-reload body, compensator barrel_mod_b ...;
# mag_base = the stock 2-shell magazine stays).  For El Diablo that list (@0x80d8) would also hide the barrel shroud
# (barrel_mod) and the full cylinder (uber_cylinder_mod) and leave a thin striped barrel and a see-through cylinder, so
# its set was chosen from the per-part render (python p1_guns.py diablo --parts -> re/part1/preview/diablo-parts.png):
# taped wood grip (grip_base), shroud, full cylinder with its rounds, scope; the rubber grip / the alternative cylinder
# strips / the muzzle tip are hidden.  T2R_P1_DIABLO_STATE=list uses the weapon-mods list instead.
SHORTY_HIDDEN = {"grip_mod", "barrel_mod_b", "slide_mod", "slide_base", "mag_speed_reload_mod", "main_mod_b", "mag_mod",
                 "body_speed_reload_base", "shotgun_shorty_lever", "shotgun_shorty_lever_end"}
DIABLO_HIDDEN = {
    "chosen": {"grip_mod", "barrel_mod_b", "uber_cylinder_base", "uber_cylinder_mod_b", "main_base", "uber_reload_mod"},
    "list": {"barrel_mod", "uber_reload_mod", "uber_cylinder_mod", "grip_mod", "barrel_mod_b", "uber_cylinder_mod_b",
             "uber_bullet_2", "uber_bullet_3", "uber_bullet_4", "main_mod"},
}
SHORTY = dict(
    name="shorty", gun="shorty", p1="t1x-pistol-shotgun", archive="sp-common.psarc", actor="pistol-shorty1",
    hidden=SHORTY_HIDDEN, drop_materials=(), **HOST)
# El Diablo's host: the HUNTING PISTOL's pak (pistol-velazquez, actor pistol-xcaliber - TLOU2's
# scoped pistol, the same pistol-base rig): its scope lens submeshes carry TLOU2's own scope materials (physical-blend:
# eyepiece scope-eyepiece-c = refraction + parallax mask + reflection mask, frontpiece scope-frontpiece-c = refraction,
# interior = pistol-xcaliber-scope-eyepiece-zoomed, the scope view's vignette / parallax ring). Part I's lens meshes use
# the same material family (Refraction / ScopeParallaxMask / ScopeReflectionMask maps), so they go INTO those submeshes
# (LENS_JOBS) and keep the TLOU2 materials: real glass and the real scope ring, no material transplant needed. The opaque
# GLASS tile (Beretta host) is gone.
HOST_XCAL = dict(host="pistol-velazquez.pak", host_base="pistol-base.pak", old_actor="pistol-xcaliber",
                 targets=[1, 8, 14],   # trigger_LODShape0 / 1 / 2: pistol-excaliber-metal (physical-character)
                 neutral={"BaseColor02": "color", "BaseColor06": "color", "LinearBlend03": "black", "LinearBlend04": "black",
                          "LinearBlend05": "black", "LinearBlend06": "black", "Threshold04": "black", "Metallic02": "black",
                          "Heightmap05": "black", "Roughness02": "gray", "Roughness06": "gray"},
                 # Part I lens material -> the host lens submesh per LOD (eyepiece / interior / scope_barrel = frontpiece)
                 lens={"scope-eyepiece": [3, 10, 16], "pistol-scope-eyepiece-zoomed": [4, 11, 17], "scope-frontpiece": [5, 12, 18]},
                 # (centre z, radius) the hunting pistol's own: eyepiece 0.0162 / 0.0108, scope-view quad 0.0172 / 0.0109
                 # (its eye point: z 0, on the lens axis); the front lens keeps Part I's place in our longer tube
                 lens_place={"scope-eyepiece": (0.0162, 0.0108), "pistol-scope-eyepiece-zoomed": (0.0172, 0.0109)},
                 # the body submesh's per-vertex streams that are not geometry: mesh_replace copied the host's vertex 0 to every
                 # vertex - in this pak stream 4 (half RGBA vertex colour, the material's layer selector) is (1, 0, 0, 0) there, so
                 # the whole gun drew one blend layer (flat mauve, no textures). Colour 0 = the base layer (our atlas);
                 # stream 70 (layer index byte) 0, stream 20 0
                 body_records={4: bytes(8), 70: bytes(1), 20: bytes(8)})
# Which pak El Diablo is built into (T2R_P1_DIABLO_HOST): 'xcal' (default: the hunting pistol's pak, HOST_XCAL, real scope
# lens materials) or 'beretta' (the Beretta pak, opaque glass tile). The 'beretta' switch is the A/B for a report
# that the scopes were replaced by a simple zoom (natives too): offline every native gun's DC data is identical to
# the game's (p1_scope_compare.py natives); that build's likely cause was the winmm alloc_near window (5dac15f); the one
# El Diablo-side candidate is the second loaded copy of the hunting pistol's scope lens materials (weapons.md 10.10).
DIABLO_HOST = os.environ.get("T2R_P1_DIABLO_HOST", "xcal")
assert DIABLO_HOST in ("beretta", "xcal"), DIABLO_HOST
# T2R_P1_DIABLO_SCOPE: 'xcal' (default) = the hunting pistol's COMPLETE scope assembly (scope body + mounts, eyepiece, scope-view
# quad, front lens: its own submeshes, materials, textures, skinning) stays in the host pak, moved rigidly onto El Diablo's
# top (SCOPE_SHIFT), and Part I's own scope (its tube, rings, rail and lens meshes) is removed: the scope view data is the
# hunting pistol's 1:1 because it is its scope (weapons.md 10.14).  'p1' = Part I's scope meshes in the host's lens
# submeshes (HOST_XCAL lens / lens_place, 10.8 - 10.11).
DIABLO_SCOPE = os.environ.get("T2R_P1_DIABLO_SCOPE", "xcal")
assert DIABLO_SCOPE in ("xcal", "p1"), DIABLO_SCOPE
SCOPE_SHIFT = (0.0, -0.0102, 0.0)            # hunting pistol scope -> El Diablo: the scope axis (y 0.1292 there) on Part I's (0.119)
# host submeshes of the hunting pistol's scope assembly per LOD: scope body (tube, mounts, turrets), eyepiece, scope-view quad, front lens
SCOPE_SUBS = [2, 3, 4, 5, 9, 10, 11, 12, 15, 16, 17, 18]
# Part I's scope is skinned to its 'xcaliber_breach' joint like the frame; a welded component made ONLY of that joint's
# vertices is the scope (rail, rings, tube, screws), the frame component also has the main / cylinder joints
P1_SCOPE_JOINT = "xcaliber_breach"
# the graft's body targets: the host's foregrip submeshes (LOD0 0, LOD1 7, LOD2 19), a material whose textures nothing else of
# the kept scope uses (the scope body shares the hunting pistol's 'trigger' textures, which must stay the hunting pistol's)
GRAFT_NEUTRAL = {"BaseColor02": "color", "BaseColor05": "color", "Normal05": "flat", "Pack_RO_AO_05": "gray",
                 "Generic02": "black", "LinearBlend02": "black", "LinearBlend03": "black", "LinearBlend04": "black",
                 "Threshold04": "black"}
if DIABLO_HOST == "xcal" and DIABLO_SCOPE == "xcal":
    HOST_XCAL = dict(HOST_XCAL, targets=[0, 7, 19], neutral=GRAFT_NEUTRAL, scope_subs=SCOPE_SUBS, scope_shift=SCOPE_SHIFT,
                     p1_scope_joint=P1_SCOPE_JOINT, body_records={4: "zero", 20: "zero", 68: "zero", 70: "zero"})
    del HOST_XCAL["lens"], HOST_XCAL["lens_place"]
if DIABLO_HOST == "xcal":
    DIABLO = dict(
        name="diablo", gun="diablo", p1="t1x-pistol-uber-t1", archive="sp-common.psarc", actor="pistol-diablo-x",
        hidden=DIABLO_HIDDEN[os.environ.get("T2R_P1_DIABLO_STATE", "chosen")],
        # the lens meshes go to the host's lens submeshes (HOST_XCAL lens); the transparency-only scope-barrel stays out
        drop_materials=("scope-barrel",) if DIABLO_SCOPE == "p1" else
        ("scope-barrel", "scope-frontpiece", "scope-eyepiece", "pistol-scope-eyepiece"),
        # only the wood layer (vertex colour B -> layer 02): the R / G layer picks put a dark wedge on the shroud and a
        # copper cylinder (one hard tile choice per triangle where Part I blends with masks); see diablo-side.png
        layer_channels={2: 2}, **HOST_XCAL)
else:
    DIABLO = dict(
        name="diablo", gun="diablo", p1="t1x-pistol-uber-t1", archive="sp-common.psarc", actor="pistol-diablo1",
        hidden=DIABLO_HIDDEN[os.environ.get("T2R_P1_DIABLO_STATE", "chosen")],
        # Beretta pak (no scope materials): the lens disks as the opaque GLASS tile, the scope-view quad and scope-barrel out
        drop_materials=("pistol-scope-eyepiece", "scope-barrel"),
        glass_materials=("scope-frontpiece", "scope-eyepiece"),
        layer_channels={2: 2}, **HOST)
# 9mm: the Colt Defender (Part I pak pistol-b-semi-auto-defender, material colt-defender-outsource; Part I's unused-in-SP
# NPC pistol) REPLACES the Beretta in the Beretta's own pak (actor stays pistol-beretta, so the pistol-beretta weapon,
# its -supp clone, the holster slot and every TLOU2 Beretta clip keep working).  The Colt skins to the same four pistol-base
# joints the Beretta uses - slide (fire/reload slide lock), magazine (reload), hammer, trigger - one rigid influence per
# vertex; its single round (pistol-round on mag_bullet) is dropped.  T2R_P1_COLT=0 keeps the Beretta (default on with
# T2R_P1_GUNS).
COLT = dict(name="colt", gun="colt", p1="pistol-b-semi-auto-defender", archive="sp-common.psarc", actor="pistol-beretta",
            hidden=set(), drop_materials=("pistol-round",), close_ports=True,
            # Part I's Colt has its ejection port on the left and the slide release / safety on the right; the
            # mesh is mirrored (x -> -x) so the port is on the right like any 1911 (bore, slide, pivots are symmetric)
            mirror=True,
            # The slide rides slide_mod (3), a child of slide that no gun skins to (joint 2 slide_base is the Enforcer's)
            # and the Beretta's default joint list leaves visible; the pistol gun clips drive it with the Colt's own extra
            # slide travel (tools/models/deagle_slide.py COLT_K).  The hammer stays on joint 29 (verified: the fire / reload
            # clips rotate it 0 -> -65 deg about X at the same pivot the Beretta's hammer_base child has)
            rig={"slide_mod": "slide", "magazine": "magazine", "hammer": "hammer", "trigger": "trigger"}, **HOST)
assert len(SHORTY["actor"]) == len(SHORTY["old_actor"]) and len(DIABLO["actor"]) == len(DIABLO["old_actor"])


def rig_of(cfg):
    """{TLOU2 pistol-base joint: Part I pistol-base joint that drives it} (p1_anims.GUNS - one table for model + anims;
    a cfg with its own 'rig' (the Colt: no Part I clips are ported, it keeps TLOU2's Beretta anims) uses that)"""
    if cfg.get("rig"):
        return dict(cfg["rig"])
    import p1_anims
    return dict(p1_anims.GUNS[cfg["gun"]]["rig"])


def joint_map(cfg, p1_names, p1_parent, host_names):
    """{Part I joint index: host joint index} for every Part I joint: itself or its nearest ancestor that drives a host
    joint, else the host root (index 0, checked to be 'root')"""
    assert p1_names[0] == "root" and host_names[0] == "root", "joint 0 must be the root in both rigs"
    inv = {}
    for t2, p1 in rig_of(cfg).items():
        assert t2 in host_names, f"{cfg['name']}: host rig has no joint {t2}"
        assert p1 in p1_names, f"{cfg['name']}: Part I rig has no joint {p1}"
        inv[p1] = host_names.index(t2)
    out = {}
    for j in range(len(p1_names)):
        k = j
        while k >= 0 and p1_names[k] not in inv:
            k = p1_parent[k]
        out[j] = inv[p1_names[k]] if k >= 0 else 0
    return out


def hidden_mask(cfg, p1_names, p1_parent):
    """bool per Part I joint: it or an ancestor is hidden in the chosen upgrade state"""
    hid = cfg["hidden"]
    out = []
    for j in range(len(p1_names)):
        k, h = j, False
        while k >= 0:
            h |= p1_names[k] in hid
            k = p1_parent[k]
        out.append(h)
    return np.array(out)


def game_dir():
    g = os.environ.get("T2R_P1_GAME")
    if not g:
        f = os.path.join(P1DIR, "game-path.txt")
        if os.path.exists(f):
            g = open(f).read().strip()
    if not g or not os.path.isdir(g):
        raise SystemExit("T2R_P1_GUNS=1: the Part I install was not found - set T2R_P1_GAME (or write re/part1/game-path.txt in the main checkout); the build stops here, it does not fall back to the TLOU2 models")
    return g


def find_model(name):
    for base in (ROOT, MAIN):
        p = os.path.join(base, "re", "models", name)
        if os.path.exists(p):
            return p
    # not cached yet: the game's actor97 pak (read-only from the TLOU2 install), cached in <main>/re/models
    import p1_carrier
    data = p1_carrier.game_pak(name[:-4] if name.endswith(".pak") else name)
    p = os.path.join(MAIN, "re", "models", name)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    open(p, "wb").write(data)
    return p


def ensure_actor(game, name, archive):
    p = os.path.join(ACTORS, name + ".pak")
    if not os.path.exists(p):
        os.makedirs(ACTORS, exist_ok=True)
        a = p1_archive.Psarc(os.path.join(game, "build", "pc", "main", archive))
        open(p, "wb").write(a.get("actor97/" + name + ".pak"))
    return p


class Textures:
    """Full-res textures of the Part I dicts by VRAM hash (needs re/part1/texdict-index.tsv)."""

    def __init__(self, game):
        self.game = game
        if not os.path.exists(INDEX):
            import p1_mapstudy
            p1_mapstudy.build_index(game, INDEX)
        self.idx = {}
        for i, line in enumerate(open(INDEX, encoding="utf-8")):
            if i:
                p = line.rstrip("\n").split("\t")
                self.idx.setdefault(int(p[0], 16), (p[1], p[2], int(p[3]), int(p[4]), int(p[5]), int(p[6]), int(p[7])))
        self._arc = {}

    def rgba(self, h):
        arc, dpath, off, size, fmt, w, hh = self.idx[h]
        if fmt not in DXGI_BPB:
            raise ValueError(f"texture {h:016x}: DXGI {fmt} not supported")
        if arc not in self._arc:
            self._arc[arc] = p1_archive.Psarc(os.path.join(self.game, "build", "pc", "main", arc))
        rb = (w // 4) * DXGI_BPB[fmt]
        pitch = (rb + 255) // 256 * 256
        data = self._arc[arc].read_range(dpath, off, pitch * (hh // 4))
        blocks = b"".join(data[r * pitch:r * pitch + rb] for r in range(hh // 4))
        hdr = (b"DDS " + struct.pack("<7I", 124, 0x1007, hh, w, 0, 0, 1) + bytes(44) + struct.pack("<2I", 32, 4)
               + b"DX10" + bytes(20) + struct.pack("<5I", 0x1000, 0, 0, 0, 0) + struct.pack("<5I", fmt, 3, 0, 1, 0))
        return np.array(Image.open(io.BytesIO(hdr + blocks)).convert("RGBA"))


def slot(tex, key):
    """hash of the first slot whose name contains `key` (e.g. 'BaseColor01')"""
    for n, h in tex.items():
        if key in n:
            return h
    return None


def joint_names(path, p1):
    pk = p1mesh.P1Mesh(path) if p1 else ndpak.Pak(path)
    return [j["name"] for j in p1mesh.joints(pk)]


LAYER_OF_CHANNEL = {0: 5, 1: 3, 2: 2}      # vertex colour R / G / B > 0.5 selects material layer 05 / 03 / 02 (checked on the
                                            # Diablo: B = the wood grip, G = brass bits; R = side plate, uncertain)


def layer_keys(t, layer):
    """(colour, normal, pack) hashes of a material layer (None where the layer has no such map)"""
    def f(prefix):
        for n, h in t.items():
            if n.endswith(prefix + "%02dMap" % layer) or (prefix == "Pack_RO" and "Pack_RO" in n and n.endswith("%02dMap" % layer)):
                return h
        return None
    return f("BaseColor"), f("Normal"), f("Pack_RO") if layer else None


def scope_vertex_masks(cfg, k, table, lod, p1_names):
    """{Part I submesh index: bool per vertex} of Part I's scope (cfg['p1_scope_joint']) in one LOD: the welded
    triangle components made only of that joint's vertices.  The frame is a component with other joints too."""
    joint = cfg.get("p1_scope_joint")
    if not joint:
        return {}
    meshes = {i: k.mesh(table[i]) for i in lod if "pistol-uber" in k.material_name(table[i]["material"])}
    P = np.concatenate([m["P"] for m in meshes.values()])
    J = np.concatenate([np.asarray(m["J"]) for m in meshes.values()])
    base, I = 0, []
    for m in meshes.values():
        I.append(m["I"] + base)
        base += len(m["P"])
    I = np.concatenate(I)
    ids = {}
    wid = np.array([ids.setdefault(tuple(np.round(p, 4)), len(ids)) for p in P])
    parent = list(range(len(ids)))

    def find(a):
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a

    for t in I:
        for x, y in ((wid[t[0]], wid[t[1]]), (wid[t[1]], wid[t[2]])):
            rx, ry = find(x), find(y)
            if rx != ry:
                parent[rx] = ry
    comp = np.array([find(w) for w in wid])
    sj = p1_names.index(joint)
    drop = np.zeros(len(P), bool)
    for c in np.unique(comp):
        m = comp == c
        if (J[m] == sj).all():
            drop |= m
    out, base = {}, 0
    for i, m in meshes.items():
        out[i] = drop[base:base + len(m["P"])]
        base += len(m["P"])
    print(f"model: {cfg['name']}: Part I scope removed: {int(drop.sum())} of {len(drop)} vertices of {len(meshes)} submeshes "
          f"(y {P[drop].min(0)[1]:.3f} .. {P[drop].max(0)[1]:.3f}, z {P[drop].min(0)[2]:.3f} .. {P[drop].max(0)[2]:.3f})")
    return out


# The Colt's slide has two vertical "lightening" slots per side (z 0.118 .. 0.137, the front serration area); the slots are not
# wanted.  The slide is a closed shell, so the slots are closed by cover strips laid over each opening and
# its rim fillet: two columns of vertices (z0 / z1, on the plain slide either side of the slot) on the slide's own outer
# cross-section (x as a function of y, measured on the plain slide between the ejection port and the slots - the section
# is constant along z there), normals from that profile, UVs fitted on the neighbouring slide vertices, tangent frame
# copied from the nearest one, 0.15 mm proud so the strip wins the depth test against the slot rim.  Nothing is deleted.
COLT_PORT_ZONES = ((0.1158, 0.1272), (0.1282, 0.1385))         # z extents of the two slots (rim fillet included)
COLT_PORT_Y = (0.0690, 0.0880)                                  # y extent that covers the opening and its rim
COLT_PORT_REF_Z = 0.1105
COLT_PORT_LIFT = 2e-5           # flush: 0.02 mm proud, just enough to cover the rim fillet edges that end exactly on the skin plane
PORT_PATCHES = []               # (uv min, uv max, uv shift to a plain patch) per strip: the slide texture paints the slots
                                # (colour edge / AO, normal, roughness); atlas() overwrites those texels with plain slide


def _slide_surface_x(P, I, z, ys, sign):
    """outermost sign * x of the triangles I at (z, y) for each y in ys; NaN where no triangle covers that point"""
    tri = P[I]
    zs = tri[:, :, 2]
    near = (zs.min(1) <= z + 1e-6) & (zs.max(1) >= z - 1e-6)
    tri = tri[near]
    zs, yv, xv = tri[:, :, 2], tri[:, :, 1], tri[:, :, 0]
    z0, z1, z2 = zs[:, 0], zs[:, 1], zs[:, 2]
    out = np.full(len(ys), np.nan)
    den = (yv[:, 1] - yv[:, 2]) * (z0 - z2) + (z2 - z1) * (yv[:, 0] - yv[:, 2])
    ok = np.abs(den) > 1e-12
    for i, y in enumerate(ys):
        with np.errstate(divide="ignore", invalid="ignore"):
            w0 = ((yv[:, 1] - yv[:, 2]) * (z - z2) + (z2 - z1) * (y - yv[:, 2])) / den
            w1 = ((yv[:, 2] - yv[:, 0]) * (z - z2) + (z0 - z2) * (y - yv[:, 2])) / den
        w2 = 1 - w0 - w1
        hit = ok & (w0 >= -1e-9) & (w1 >= -1e-9) & (w2 >= -1e-9)
        if hit.any():
            out[i] = (sign * (w0[hit] * xv[hit, 0] + w1[hit] * xv[hit, 1] + w2[hit] * xv[hit, 2])).max()
    return out


def close_slide_ports(d, joint, zones=COLT_PORT_ZONES, y_range=COLT_PORT_Y, ref_z=COLT_PORT_REF_Z):
    """a copy of the p1mesh mesh dict d with cover strips over the slide's slots (see the comment above)"""
    P, I, J = np.asarray(d["P"]), np.asarray(d["I"]), np.asarray(d["J"])
    Is = I[(J[I] == joint).all(1)]
    ys_all = np.arange(y_range[0], y_range[1] + 1e-9, 0.0005)
    add = {k: [] for k in ("P", "N", "T", "H", "C", "UV0", "UV1", "UV2")}
    tris, base = [], len(P)
    zlo, zhi = zones[0][0], zones[-1][1]
    for sign in (1, -1):
        prof = _slide_surface_x(P, Is, ref_z, ys_all, sign)
        idx = np.flatnonzero(~np.isnan(prof))
        assert len(idx) > 10, "slide profile not found"
        # the contiguous run from the bottom of the range: the profile stops where the top edge rounds off the surface
        brk = np.flatnonzero(np.diff(idx) > 1)
        idx = idx[:brk[0] + 1] if len(brk) else idx
        ys, xs = ys_all[idx], prof[idx]
        slope = np.gradient(xs, ys)
        near_slide = np.zeros(len(P), bool)
        near_slide[np.unique(Is)] = True
        ref = (near_slide & (np.sign(P[:, 0]) == sign) & (sign * P[:, 0] > xs.min() - 0.0008) & (P[:, 2] > 0.095)
               & (P[:, 2] < 0.15) & (P[:, 1] > ys.min() - 0.01) & (P[:, 1] < ys.max()))
        ref &= ~((P[:, 2] > zlo) & (P[:, 2] < zhi))
        assert ref.sum() >= 12, f"too few reference vertices ({int(ref.sum())})"
        refi = np.flatnonzero(ref)
        m = len(ys)
        # UV of a strip vertex: the slide's side island is linear in (z, y), but the mesh carries several UV copies of the same
        # skin (flat skin / pocket walls / fillets in other islands), so the fit uses only the vertices of the big flat triangles of
        # the dominant island (largest total area of side-facing faces), outside the slots
        tri3 = P[Is]
        ar = np.linalg.norm(np.cross(tri3[:, 1] - tri3[:, 0], tri3[:, 2] - tri3[:, 0]), axis=1) / 2
        side = (sign * np.asarray(d["N"])[Is][:, :, 0].mean(1) > 0.9) & (sign * tri3[:, :, 0].mean(1) > xs.min() - 0.0009)             & (tri3[:, :, 2].mean(1) > 0.09) & (tri3[:, :, 2].mean(1) < 0.15) & (tri3[:, :, 1].mean(1) > 0.06)
        fits = []
        for k in range(3):
            if d["UV"][k] is None:
                fits.append(None)
                continue
            uvk = np.asarray(d["UV"][k])
            wcell = collections.defaultdict(float)
            for ti in np.flatnonzero(side):
                wcell[tuple(np.round(uvk[Is[ti]].mean(0) / 0.15).astype(int))] += ar[ti]
            cen = np.array(max(wcell, key=wcell.get)) * 0.15
            vsel = np.unique(Is[side])
            vsel = vsel[(np.abs(uvk[vsel] - cen) < 0.2).all(1) & (sign * P[vsel, 0] > xs.min() - 0.0009)
                        & ~((P[vsel, 2] > zlo - 0.001) & (P[vsel, 2] < zhi + 0.001))]
            assert len(vsel) >= 4, f"UV{k}: {len(vsel)} skin vertices"
            A = np.c_[P[vsel, 2], P[vsel, 1], np.ones(len(vsel))]
            coef = np.linalg.lstsq(A, uvk[vsel], rcond=None)[0]
            res = np.abs(A @ coef - uvk[vsel]).max()
            assert res < 0.01, f"UV{k} side {sign}: skin UV fit residual {res:.4f} over {len(vsel)} vertices"
            fits.append(coef)
        for z0, z1 in zones:
            c0 = base
            for zz in (z0, z1):
                for yy, xx, sl in zip(ys, xs, slope):
                    n = np.array([sign * 1.0, -sl, 0.0])
                    n /= np.linalg.norm(n)
                    near = refi[np.argmin(3 * np.abs(P[refi, 1] - yy) + np.abs(P[refi, 2] - zz))]
                    add["P"].append((sign * (xx + COLT_PORT_LIFT), yy, zz))
                    add["N"].append(d["N"][near])           # the exact frame of the nearest real slide vertex
                    add["T"].append(d["T"][near])
                    add["H"].append(d["H"][near])
                    if "C" in d:
                        add["C"].append(d["C"][near])
                    for k in range(3):
                        add["UV%d" % k].append((0.0, 0.0) if fits[k] is None else np.array([zz, yy, 1.0]) @ fits[k])
            uvs = np.array(add["UV0"][c0 - len(P):])
            fl = np.floor(uvs.mean(0))
            PORT_PATCHES.append((uvs.min(0) - fl, uvs.max(0) - fl, None))
            for i in range(m - 1):
                a, b, c, e = c0 + i, c0 + i + 1, c0 + m + i, c0 + m + i + 1
                tris += [(a, b, c), (b, e, c)] if sign > 0 else [(a, c, b), (b, c, e)]
            base += 2 * m
    n_new = len(add["P"])
    out = dict(d)
    out["P"] = np.vstack([P, add["P"]])
    out["N"] = np.vstack([d["N"], add["N"]])
    out["T"] = np.vstack([d["T"], add["T"]])
    out["H"] = np.concatenate([d["H"], add["H"]])
    out["J"] = np.concatenate([J, np.full(n_new, joint, np.int64)])
    out["W"] = np.concatenate([np.asarray(d["W"]), np.ones(n_new)])
    out["UV"] = [None if d["UV"][k] is None else np.vstack([d["UV"][k], add["UV%d" % k]]) for k in range(3)]
    if "C" in d:
        out["C"] = np.vstack([d["C"], add["C"]])
    out["I"] = np.vstack([I, np.array(tris, np.int64)])
    return out


def mirror_x(d):
    """the mesh dict mirrored across the gun's vertical plane (x -> -x): positions, normals, tangents; the winding is
    reversed (the handedness record is re-derived from the UV bitangent when the frames are written, so it flips with it)"""
    out = dict(d)
    for k in ("P", "N", "T"):
        out[k] = np.asarray(d[k]) * np.array([-1.0, 1.0, 1.0])
    out["H"] = -np.asarray(d["H"])
    out["I"] = np.asarray(d["I"])[:, ::-1].copy()
    return out


def patch_ports(arr):
    """a texture (h, w, 3) with every PORT_PATCHES rectangle (plus a margin) repainted as plain slide: the rectangle is
    interpolated from the 4-texel ring just outside it (left / right columns across, top / bottom rows down, averaged) with
    the ring's grain added, so colour, normal and roughness / AO lose the painted slot outline"""
    h, w = arr.shape[:2]
    out = arr.astype(np.float32).copy()
    from scipy.ndimage import gaussian_filter
    rng = np.random.RandomState(7)
    boxes = []                         # texel boxes; overlapping ones (the two slots of a side) are merged into one
    for lo, hi, _shift in PORT_PATCHES:
        boxes.append([int((lo[0] - 0.012) * w), int(np.ceil((hi[0] + 0.012) * w)), int((lo[1] - 0.012) * h), int(np.ceil((hi[1] + 0.012) * h))])
    merged = True
    while merged:
        merged = False
        for i in range(len(boxes)):
            for j in range(i + 1, len(boxes)):
                a_, b_ = boxes[i], boxes[j]
                if a_[0] < b_[1] + 6 and b_[0] < a_[1] + 6 and a_[2] < b_[3] + 6 and b_[2] < a_[3] + 6:
                    boxes[i] = [min(a_[0], b_[0]), max(a_[1], b_[1]), min(a_[2], b_[2]), max(a_[3], b_[3])]
                    del boxes[j]
                    merged = True
                    break
            if merged:
                break
    for x0, x1, y0, y1 in sorted(boxes):
        src = arr.astype(np.float32)
        r = 4
        left, right = src[y0:y1, x0 - r:x0].mean(1), src[y0:y1, x1:x1 + r].mean(1)
        top, bot = src[y0 - r:y0, x0:x1].mean(0), src[y1:y1 + r, x0:x1].mean(0)
        tx = np.linspace(0, 1, x1 - x0)[None, :, None]
        ty = np.linspace(0, 1, y1 - y0)[:, None, None]
        fill = 0.5 * (left[:, None, :] * (1 - tx) + right[:, None, :] * tx) + 0.5 * (top[None, :, :] * (1 - ty) + bot[None, :, :] * ty)
        ring = np.concatenate([src[y0 - r:y0, x0:x1].reshape(-1, src.shape[2]), src[y1:y1 + r, x0:x1].reshape(-1, src.shape[2])])
        grain = gaussian_filter(rng.normal(0, 1, fill.shape[:2]), 1.2)          # smooth luminance grain, one value for all channels
        mad = 1.4826 * np.median(np.abs(ring - np.median(ring, 0)), 0)              # robust spread of the ring (not its edge highlights)
        fill += (grain / max(grain.std(), 1e-6))[:, :, None] * mad * 0.5
        out[y0:y1, x0:x1] = fill
    return np.clip(out, 0, 255).astype(arr.dtype)


def build_mesh(cfg, k, table, lods, p1_joints, host_names, tex_by_mat):
    """per LOD: merged mesh dict (positions, frames, atlas UVs, host joints); + atlas keys, grid, report"""
    PORT_PATCHES.clear()
    keys = []                                       # one atlas tile per distinct (colour, normal, pack) triple
    p1_names = [j["name"] for j in p1_joints]
    p1_parent = [j["parent"] for j in p1_joints]
    jmap = joint_map(cfg, p1_names, p1_parent, host_names)
    hidden = hidden_mask(cfg, p1_names, p1_parent)
    used = collections.Counter()

    def tile(mat, layer):
        if any(g in k.material_name(mat) for g in cfg.get("glass_materials", ())):
            if GLASS not in keys:
                keys.append(GLASS)
            return keys.index(GLASS)
        t = tex_by_mat[mat]
        key = layer_keys(t, layer)
        if key[0] is None:
            key = layer_keys(t, 1)
        if key not in keys:
            keys.append(key)
        return keys.index(key)

    plan = []                                       # per LOD: [(mesh dict, tri array, tile per tri)]
    for lod in lods:
        items = []
        sdrop = scope_vertex_masks(cfg, k, table, lod, p1_names)
        for i in lod:
            m = table[i]["material"]
            if any(s in k.material_name(m) for s in tuple(cfg["drop_materials"]) + tuple(cfg.get("lens", {}))):
                continue
            d = k.mesh(table[i])
            if cfg.get("close_ports") and (np.asarray(d["J"]) == p1_names.index("slide")).any():
                d = close_slide_ports(d, p1_names.index("slide"))
            if cfg.get("mirror"):
                d = mirror_x(d)
            J = np.asarray(d["J"])
            ok = ~hidden[np.clip(J, 0, len(hidden) - 1)] & (J < len(hidden))
            if i in sdrop:
                ok &= ~sdrop[i]
            tri = d["I"][ok[d["I"]].all(1)]
            if not len(tri):
                continue
            for j in np.unique(J[np.unique(tri)]):
                used[(p1_names[j], host_names[jmap[int(j)]])] += 1
            tl = np.full(len(tri), tile(m, 1))
            if "C" in d and cfg.get("layers", True) and keys[tl[0]] != GLASS:
                w = np.clip(d["C"][:, :3], 0, 1)[tri].mean(1)
                best, on = w.argmax(1), w.max(1) > 0.5
                for ch, layer in cfg.get("layer_channels", LAYER_OF_CHANNEL).items():
                    sel = on & (best == ch)
                    if sel.any() and layer_keys(tex_by_mat[m], layer)[0] is not None:
                        tl[sel] = tile(m, layer)
            items.append((d, tri, tl))
        plan.append(items)
    grid, tsize = atlas_grid(len(keys))
    cols, rows = grid
    g = GUTTER
    out = []
    for items in plan:
        P, N, T, UV, Jo, I = [], [], [], [], [], []
        base = 0
        for d, tri, tl in items:
            # one duplicate of a vertex per (integer UV offset, tile) of the triangles that use it (tiling UVs -> [0,1])
            uv = d["UV"][0]
            off = np.floor(uv[tri].mean(1)).astype(int)
            vmap, nv, ntri = {}, [], np.zeros_like(tri)
            for t, (tr, o, ti) in enumerate(zip(tri, off, tl)):
                for c, v in enumerate(tr):
                    key = (int(v), int(o[0]), int(o[1]), int(ti))
                    if key not in vmap:
                        vmap[key] = len(nv)
                        nv.append(key)
                    ntri[t, c] = vmap[key]
            src = np.array([v for v, _, _, _ in nv])
            u = uv[src] - np.array([[a, b] for _, a, b, _ in nv], float)
            u = np.clip(u, 0.0, 1.0)
            u = g + u * (1 - 2 * g)                 # inside the tile's gutter
            ti = np.array([c for _, _, _, c in nv])
            u = np.stack([(ti % cols + u[:, 0]) / cols, (ti // cols + u[:, 1]) / rows], 1)
            P.append(d["P"][src])
            N.append(d["N"][src])
            T.append(d["T"][src])
            UV.append(u)
            Jo.append(np.array([jmap[int(j)] for j in np.asarray(d["J"])[src]]))
            I.append(ntri + base)
            base += len(src)
        out.append({"P": np.concatenate(P), "N": np.concatenate(N), "T": np.concatenate(T), "UV": [np.concatenate(UV)],
                    "J": np.concatenate(Jo), "I": np.concatenate(I)})
    return out, keys, (grid, tsize), used


def lens_of(cfg, matname):
    """the cfg['lens'] key a Part I material belongs to (longest match: 'pistol-scope-eyepiece-zoomed' before
    'scope-eyepiece')"""
    hits = [key for key in cfg.get("lens", {}) if key in matname]
    return max(hits, key=len) if hits else None


def lens_meshes(cfg, k, table, lods, p1_joints, host_names):
    """{host submesh: mesh dict} - per LOD, the Part I lens submeshes of each cfg['lens'] material merged, with their own
    UVs (the host's scope materials sample their refraction / parallax / reflection masks at them, as Part I's do)"""
    if not cfg.get("lens"):
        return {}
    p1_names = [j["name"] for j in p1_joints]
    jmap = joint_map(cfg, p1_names, [j["parent"] for j in p1_joints], host_names)
    out = {}
    for lod, idx in enumerate(lods):
        parts = {}
        for i in idx:
            key = lens_of(cfg, k.material_name(table[i]["material"]))
            if key:
                parts.setdefault(key, []).append(k.mesh(table[i]))
        for key, ms in parts.items():
            smi = cfg["lens"][key][lod]
            P, N, T, UV, J, I, base = [], [], [], [], [], [], 0
            for d in ms:
                P.append(d["P"]); N.append(d["N"]); T.append(d["T"]); UV.append(d["UV"][0])
                J.append(np.array([jmap[int(j)] for j in np.asarray(d["J"])])); I.append(np.asarray(d["I"]) + base)
                base += len(d["P"])
            P = np.concatenate(P)
            if key in cfg.get("lens_place", {}):
                # the hunting pistol's own optical layout (eye -> eyepiece -> scope-view quad distances and radii) on our
                # scope's axis: the scope-view material's parallax is made for it (with Part I's spacing - eyepiece
                # 1.2 cm in front of the quad, a 20 % larger quad - the view through the scope came out almost black)
                zc, r = cfg["lens_place"][key]
                c = P.mean(0)
                cur = float(np.abs(P[:, :2] - c[:2]).max())
                P = np.c_[c[0] + (P[:, 0] - c[0]) * r / cur, c[1] + (P[:, 1] - c[1]) * r / cur, P[:, 2] - c[2] + zc]
            out[smi] = {"P": P, "N": np.concatenate(N), "T": np.concatenate(T), "UV": [np.concatenate(UV)],
                        "J": np.concatenate(J), "I": np.concatenate(I)}
    missing = [(key, s) for key, sl in cfg["lens"].items() for s in sl if s not in out]
    assert not missing, f"{cfg['name']}: no Part I lens mesh for host lens submeshes {missing}"
    return out


def atlas_grid(n):
    """(cols, rows) both powers of two holding n tiles, and the tile size so the atlas side stays <= ATLAS_MAX"""
    cols = rows = 1
    while cols * rows < n:
        if cols <= rows:
            cols *= 2
        else:
            rows *= 2
    tile = ATLAS_MAX // max(cols, rows)
    return (cols, rows), tile


def atlas(tx, keys, layout, cfg_ports=False):
    """three arrays (colour RGB, normal RGB, pack RGB) of cols*tile x rows*tile (powers of two): each texture set
    scaled into its tile minus a GUTTER border, the border filled by edge extension (mips do not mix tiles)"""
    (cols, rows), T = layout
    G = int(round(T * GUTTER))
    inner = T - 2 * G
    out = {"color": np.full((rows * T, cols * T, 3), 127, np.uint8),
           "normal": np.full((rows * T, cols * T, 3), (128, 128, 255), np.uint8),
           "pack": np.full((rows * T, cols * T, 3), (200, 255, 0), np.uint8)}      # rough, AO 1, metal 0
    for n, (c, nm, pk) in enumerate(keys):
        x0, y0 = (n % cols) * T, (n // cols) * T
        if (c, nm, pk) == GLASS:
            for name in out:
                out[name][y0:y0 + T, x0:x0 + T] = GLASS_TILE[name]
            continue
        for name, h in (("color", c), ("normal", nm), ("pack", pk)):
            if not h:
                continue
            src = tx.rgba(h)[:, :, :3]
            if PORT_PATCHES and cfg_ports:
                src = patch_ports(src)
            a = Image.fromarray(src).resize((inner, inner), Image.LANCZOS)
            arr = np.pad(np.array(a), ((G, G), (G, G), (0, 0)), mode="edge")
            if name == "normal":
                arr[:, :, 2] = 255
            out[name][y0:y0 + T, x0:x0 + T] = arr
    return out


def stub():
    z = np.zeros((3, 3))
    return {"P": z, "N": np.tile([0.0, 1.0, 0.0], (3, 1)), "T": np.tile([1.0, 0.0, 0.0], (3, 1)), "UV": [np.zeros((3, 2))],
            "J": np.zeros(3, np.int64), "I": np.zeros((1, 3), np.int64)}


def pak_cli():
    cli = os.path.join(MAIN, "tlou2_pak_editor", "build", "gcc", "pak_editor_cli.exe")
    env = dict(os.environ, PATH=os.path.join(MAIN, "tools", "win", "ext", "msys64", "ucrt64", "bin") + os.pathsep
               + os.environ["PATH"])
    return cli, env


def host_slots(hp, smi):
    """{slot name: VRAM hash} of a host submesh's material"""
    mat = hp.submeshes[smi]["material"]
    texl, tc = hp.ptr(mat + 32), hp.u32(mat + 64 + 208 + 4)
    out = {}
    for j in range(tc):
        e = texl + 48 * j
        out[hp.cstr(hp.ptr(e))] = hp.q(hp.ptr(e + 24) + 8)
    return out


def check_host(cfg, hp):
    """the target submeshes are the host's LODShape0 / 1 / 2 of ONE material with colour, normal and pack slots"""
    mats = set()
    for lod, smi in enumerate(cfg["targets"]):
        nm = hp.submeshes[smi]["name"]
        assert f"LODShape{lod}" in nm, f"{cfg['host']} submesh {smi} is not LOD{lod}: {nm}"
        mats.add(hp.submeshes[smi]["material"])
        sl = host_slots(hp, smi)
        for key in ("BaseColor01", "Normal01", "Pack_RO_AO_ME"):
            assert slot(sl, key), f"{cfg['host']} submesh {smi}: material has no {key} slot ({sorted(sl)})"
    return host_slots(hp, cfg["targets"][0])


def build(cfg, out, preview=True):
    try:
        game = game_dir()
    except SystemExit as e:
        print(f"model: {cfg['name']}: T2R_P1_GUNS=1 needs the Part I install - stopping the build ({e})")
        raise
    p1 = p1mesh.P1Mesh(ensure_actor(game, cfg["p1"], cfg["archive"]))
    base = ensure_actor(game, "pistol-base", "sp-common.psarc")
    p1_joints = p1mesh.joints(p1mesh.P1Mesh(base))
    host_path = find_model(cfg["host"])
    host_names = joint_names(find_model(cfg["host_base"]), False)
    table = p1.submesh_table()
    lods = p1.lods(table)
    assert len(lods) == 3, f"{cfg['p1']}: expected 3 LODs, found {len(lods)}"
    hp = ndpak.Pak(host_path)
    host_tex = check_host(cfg, hp)
    tx = Textures(game)
    tex_by_mat = {t["material"]: p1.material_textures(t["material"]) for t in table}
    meshes, keys, layout, used = build_mesh(cfg, p1, table, lods, p1_joints, host_names, tex_by_mat)
    host = open(host_path, "rb").read()
    jobs, stubbed = [], 0
    lens = lens_meshes(cfg, p1, table, lods, p1_joints, host_names)
    for smi in range(len(hp.submeshes)):
        if smi in cfg["targets"]:
            jobs.append((smi, dict(meshes[cfg["targets"].index(smi)], records=cfg.get("body_records", {}))))
        elif smi in lens:                            # Part I lens geometry in the host's own scope-lens submesh
            jobs.append((smi, lens[smi]))
        elif smi in cfg.get("scope_subs", ()):       # the hunting pistol's own scope assembly, moved onto our top
            jobs.append((smi, {"shift": cfg["scope_shift"]}))
        elif hp.submeshes[smi]["vcount"]:            # every other host part (sights, magazine, rounds ...) is emptied
            jobs.append((smi, stub()))
            stubbed += 1
    data = mesh_replace.replace(host, jobs)
    n = 0
    if cfg["actor"] != cfg["old_actor"]:
        data, n = rename_pak.rename(data, cfg["old_actor"], cfg["actor"])
    open(out, "wb").write(data)
    atl = atlas(tx, keys, layout, bool(cfg.get("close_ports")))
    side = atl["color"].shape
    neutral = {"black": np.zeros((64, 64, 3), np.uint8), "flat": np.full((64, 64, 3), (128, 128, 255), np.uint8),
               "gray": np.full((64, 64, 3), 200, np.uint8)}
    cli, env = pak_cli()
    injected, skipped = [], []
    with tempfile.TemporaryDirectory() as work:
        jobs_t = [(kind, slot(host_tex, key), True) for kind, key in
                  (("color", "BaseColor01"), ("normal", "Normal01"), ("pack", "Pack_RO_AO_ME"))]
        done = {h for _, h, _ in jobs_t}
        for key, what in cfg.get("neutral", NEUTRAL_SLOTS).items():
            h = slot(host_tex, key)
            if h and h not in done:
                jobs_t.append((what, h, False))
                done.add(h)
        for kind, target, must in jobs_t:
            png = os.path.join(work, f"{kind}-{target:016x}.png")
            Image.fromarray(atl[kind] if kind in atl else neutral[kind]).save(png)
            tmp = out + ".tex"
            r = subprocess.run([cli, "inject-texture", out, png, tmp, "--texture", "%016x" % target, "--no-flip"],
                               env=env, capture_output=True, text=True)
            if r.returncode:
                msg = (r.stderr.strip() or r.stdout.strip()).splitlines()[-1:]
                if must:
                    raise SystemExit(f"{cfg['name']} texture {kind}: {msg}")
                skipped.append((f"{target:016x}", kind, msg))
                continue
            os.replace(tmp, out)
            # inject-texture bumps the VRAM hash to hash + 1. Both guns come from the SAME host pak, so both would carry
            # the same bumped hashes with different pixels (the texture manager keeps one per hash: one gun would show
            # the other's atlas). Give every injected texture a hash of its own (actor + slot).
            data = bytearray(open(out, "rb").read())
            old = struct.pack("<Q", (target + 1) & (2 ** 64 - 1))
            new_h = rename_pak.fnv(f"{cfg['actor']}:{target:016x}") | 1
            hits = data.count(old)
            if not hits:                  # a small slot rewritten in place keeps its hash: the stock texture dict entry
                old = struct.pack("<Q", target)        # would still win, so it gets an own hash as well
                hits = data.count(old)
            assert hits, f"{cfg['name']}: hash of {target:016x} not found after inject-texture"
            data = data.replace(old, struct.pack("<Q", new_h))
            open(out, "wb").write(bytes(data))
            injected.append(kind)
    print(f"model: {cfg['name']} = Part I {cfg['p1']} -> {cfg['host']}: LOD verts "
          f"{[len(m['P']) for m in meshes]}, {stubbed} other host submeshes emptied, {len(keys)} texture sets in a "
          f"{side[1]}x{side[0]} atlas (tile {layout[1]}, gutter {int(round(layout[1] * GUTTER))} px), "
          f"{len(injected)} slots injected{f', skipped {skipped}' if skipped else ''}, {n} names -> {cfg['actor']}")
    print(f"model: {cfg['name']} skinning (Part I joint -> host joint): "
          + ", ".join(f"{a}->{b}" for (a, b), _ in sorted(used.items())))
    if preview:
        render_preview(cfg, out, atl["color"], host_path)
    return out


def read_lod0(pak_path, smi):
    p = ndpak.Pak(pak_path)
    sm = p.submeshes[smi]
    P = np.array(p.decode_quantized([s for s in sm["streams"] if s["type"] == 64][0], sm["vcount"], 3))
    UV = np.array(p.decode_quantized([s for s in sm["streams"] if s["type"] == 65][0], sm["vcount"], 2))
    I = np.array(p.indices(sm)).reshape(-1, 3)
    return P, UV, I


def render_preview(cfg, pak, color, host_path):
    """Views of the BUILT pak's LOD0 (read back from the file: checks the written geometry, UVs, quantisation) with
    the atlas colour map, next to the TLOU2 host model it replaces."""
    os.makedirs(PREVIEW, exist_ok=True)
    P, UV, I = read_lod0(pak, cfg["targets"][0])
    mesh = {"P": P, "I": I, "UV": UV, "tex": color}
    extra = []                                       # the hunting pistol's scope assembly kept in the pak (LOD0), moved onto our top
    for smi in cfg.get("scope_subs", ())[:4]:
        Ps, _, Is = read_lod0(pak, smi)
        extra.append({"P": Ps, "I": Is, "color": np.tile([0.85, 0.45, 0.2] if smi in (3, 4, 5) else [0.3, 0.55, 0.9], (len(Ps), 1))})
    host_meshes = []
    hp = ndpak.Pak(host_path)
    for smi in range(len(hp.submeshes)):
        if hp.submeshes[smi]["vcount"] and "LODShape0" in hp.submeshes[smi]["name"]:
            Ph = np.array(hp.positions(hp.submeshes[smi]))
            Ih = np.array(hp.indices(hp.submeshes[smi])).reshape(-1, 3)
            host_meshes.append({"P": Ph, "I": Ih, "color": np.tile([0.6, 0.62, 0.66], (len(Ph), 1))})
    for view in ("side", "top", "front"):
        both = [mesh] + extra + host_meshes
        ext = p1_render.bounds(both, view)
        a = p1_render.label(p1_render.render([mesh] + extra, view, (1000, 480), extent=ext), f"{cfg['name']} (Part I model in the built pak{' + the hunting pistol scope (blue body, orange lenses)' if extra else ''}), {view}")
        b = p1_render.label(p1_render.render(host_meshes, view, (1000, 480), extent=ext), f"TLOU2 host model it replaces: {cfg['host']}")
        img = Image.new("RGB", (1000, 960))
        img.paste(a, (0, 0))
        img.paste(b, (0, 480))
        dst = os.path.join(PREVIEW, f"{cfg['name']}-{view}.png")
        img.save(dst)
        print("preview:", dst)
    Image.fromarray(color).resize((512, 512 * color.shape[0] // color.shape[1])).save(os.path.join(PREVIEW, cfg["name"] + "-atlas-color.png"))


def parts_sheet(cfg):
    """re/part1/preview/<gun>-parts.png: the Part I model's LOD0, one panel per (driving joint, material), that part in
    red - the reference for the hidden-joint choice above; panel titles say whether the build keeps the part"""
    game = game_dir()
    k = p1mesh.P1Mesh(ensure_actor(game, cfg["p1"], cfg["archive"]))
    pj = p1mesh.joints(p1mesh.P1Mesh(ensure_actor(game, "pistol-base", "sp-common.psarc")))
    names, parent = [j["name"] for j in pj], [j["parent"] for j in pj]
    hidden = hidden_mask(cfg, names, parent)
    t = k.submesh_table()
    groups = {}
    for i in k.lods(t)[0]:
        d = k.mesh(t[i])
        mat = k.material_name(t[i]["material"]).split(":")[0].split("/")[-1]
        J = np.asarray(d["J"])
        for j in np.unique(J):
            tri = d["I"][(J[d["I"]] == j).all(1)]
            if len(tri):
                groups.setdefault((names[j], mat, bool(hidden[j]) or any(s in mat for s in cfg["drop_materials"])),
                                  []).append((d["P"], tri))
    keys = sorted(groups)
    W, H, cols = 400, 220, 4
    rows = (len(keys) + cols - 1) // cols
    sheet = Image.new("RGB", (W * cols, H * rows))
    for n, key in enumerate(keys):
        meshes = []
        for kk in keys:
            col = (0.9, 0.3, 0.2) if kk == key else (0.35, 0.37, 0.4)
            meshes += [{"P": P, "I": tri, "color": np.tile(col, (len(P), 1))} for P, tri in groups[kk]]
        im = p1_render.label(p1_render.render(meshes, "side", (W, H)), f"{key[0]} [{key[1]}] {'HIDDEN' if key[2] else 'kept'}")
        sheet.paste(im, ((n % cols) * W, (n // cols) * H))
    os.makedirs(PREVIEW, exist_ok=True)
    dst = os.path.join(PREVIEW, cfg["name"] + "-parts.png")
    sheet.save(dst)
    print("parts:", dst)


def build_shorty(out):
    return build(SHORTY, out, preview=bool(os.environ.get("T2R_P1_PREVIEW")))


def colt_enabled():
    return os.environ.get("T2R_P1_COLT", "1") != "0"


def build_colt(out):
    return build(COLT, out, preview=bool(os.environ.get("T2R_P1_PREVIEW")))


def build_diablo(out):
    return build(DIABLO, out, preview=bool(os.environ.get("T2R_P1_PREVIEW")))


if __name__ == "__main__":
    which = sys.argv[1] if len(sys.argv) > 1 else ""
    cfg = {"shorty": SHORTY, "diablo": DIABLO, "colt": COLT}.get(which)
    if not cfg:
        print(__doc__)
        sys.exit(1)
    if "--parts" in sys.argv:
        parts_sheet(cfg)
        sys.exit(0)
    outp = next((a for a in sys.argv[2:] if not a.startswith("--")), os.path.join(tempfile.gettempdir(), f"t2r-p1-{which}.pak"))
    build(cfg, outp, preview="--preview" in sys.argv)
    print("wrote", outp)
