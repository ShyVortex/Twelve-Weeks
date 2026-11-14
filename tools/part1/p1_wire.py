"""DC + pak wiring of the Part I Shorty / El Diablo animations (T2R_P1_GUNS=1, with T2R_FACTION_GUNS=1).
re/part1/weapons.md section 9.  Called from tools/features/build_dll.py; offline only.

1. carrier pak (p1_carrier.py): the baked clips (p1_anims.py bake -> <main>/re/part1/anims/*.clip) in
   actor97/anim-ellie-workbench-shared-pistol.pak, listed in the MP level (MP_ACTOR).
2. overlay modules: the player overlay of a gun = art def +0x180 (a key string; the module that exports
   *weapon-specific-overlay-<key>* maps 'player' to an anim-overlay-set).  TLOU2 ships two loaded but unused TLOU1
   modules with the keys 'pistol-uber' and 'pistol-shotgun'; they are rewritten (same symbols, new entries):
     El Diablo  = the revolver's set (anim-overlay-player-specific-weapon-pistol-revolver-taurus: grips, aim, fire)
     Shorty     = the Beretta's set  (anim-overlay-player-specific-weapon-pistol-beretta)
   + renames of TLOU2's one-shot pistol reload (ellie-pistol-[relaxed-]reload-<stance>-<tac|emerg|admin>-<part|add|gun>,
   the names the Beretta and the speed-loader revolver play) to our carriers per stance, and of the fire gun clip
   (stand-p-aim-fire-gun).  Prone / supine are not renamed to Part I clips (Part I has no prone): El Diablo gets the
   TLOU2 speed-loader revolver's own prone / supine reload (a cylinder swing-out on the same rig joints), the Shorty keeps
   the Beretta's (a magazine reload on the same 'magazine' joint) - TLOU2's arm layer on TLOU2's prone base.
3. weapon-art: +0x180 = the key; the Shorty takes the Beretta's hold / holster / anim-type fields (a one-handed
   pistol: art +0x28 class, +0x68 anim type, +0x140..+0x168, +0x190, +0x198 - the tomahawk patch's method), El Diablo
   the Beretta's anim type (+0x68 'pistol-beretta': TLOU2's revolver without the speed loader reloads round by round
   (start / mid / end clips), the Beretta type plays one reload clip - T2R_P1_DIABLO_ANIMTYPE=keep to leave it).
   Both get an own firearm-art def (+0x128) with the gun clips (+0x10 fire, +0x20 reload) = our carriers, +0x38 no
   magazine prop (nothing is dropped) and the muzzle point (+0x108) of the Part I model."""
import os
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.dirname(HERE)
sys.path[:0] = [HERE, os.path.join(TOOLS, "features")]
import p1_anims  # noqa: E402
import p1_carrier  # noqa: E402
import p1_overlay  # noqa: E402

MP_ACTOR = p1_carrier.CARRIER_PAK
OVERLAY_DIR = "player-specific-weapon-overlays"
GUNS = {   # weapon id (dc_data_patches) -> setup
    "pistol-el-diablo": dict(gun="diablo", key="pistol-uber", module="pistol-uber",
                             host_module="ellie-guns/pistol-bull-revolver.bin",
                             host_set="anim-overlay-player-specific-weapon-pistol-revolver-taurus",
                             ref=("anim-player-gun-ellie", "ellie-revolver-taurus-speedloader-reload-{st}-part"),
                             prone="ellie-revolver-taurus-speedloader-reload-{st}-{k}",
                             muzzle=(0.0, 0.088, 0.272),
                             # scope camera (firearm-art +0x140): the Part I scope's eyepiece disk centre on the built model
                             # (scope-eyepiece: x -0.012..0.012, y 0.107..0.130, z 0.004..0.006; the hunting pistol's
                             # own eye point is 0 / 0.129 / 0, the bolt rifle's 0 / 0.129 / -0.01)
                             # z: back at the eyepiece since the model lives in the hunting pistol's pak with its real scope
                             # lens materials (p1_guns.HOST_XCAL; 3acb294 had it 0.29 m ahead of the opaque Beretta-pak
                             # lenses). The hunting pistol's eye is 1.6 cm behind its eyepiece (eye z 0, eyepiece z 0.015 -
                             # 0.017); ours keeps that distance to our eyepiece (z 0.004 - 0.006)
                             # (Beretta-pak El Diablo, opaque lenses: 0.29 ahead of the model, 3acb294)
                             # xcal: the hunting pistol's eye -> lens layout (p1_guns HOST_XCAL lens_place): eye z 0, on our axis y 0.119
                             # T2R_P1_DIABLO_SCOPE=xcal (default, 10.14): the hunting pistol's own scope moved by p1_guns.SCOPE_SHIFT -
                             # the eye is its eye vector plus the same shift (scope_eye_shift), nothing else
                             scope_eye=(0.0, 0.119, 0.0) if os.environ.get("T2R_P1_DIABLO_HOST", "xcal") == "xcal" else (0.0, 0.1185, 0.29),
                             scope_eye_shift=(0.0, -0.0102, 0.0) if (os.environ.get("T2R_P1_DIABLO_HOST", "xcal") == "xcal"
                                                                      and os.environ.get("T2R_P1_DIABLO_SCOPE", "xcal") == "xcal") else None,
                             # sound: the .357's set (module aud-sfx-wpn-pistol-revolver-357, bank wpn-pistol-revolver-357:
                             # player / npc / dryfire / cylinder-eject / cylinder-reload / revolver-open / -close; no MP gun
                             # uses it) with the Part I El Diablo waves (p1_sound.py)
                             sound=("pistol-revolver-taurus", "pistol-revolver-357",
                                    {"sfx-pistol-revolver-taurus-player": "sfx-pistol-revolver-357-player",
                                     "sfx-pistol-revolver-taurus-npc": "sfx-pistol-revolver-357-npc",
                                     "sfx-pistol-revolver-taurus-owen-player": "sfx-pistol-revolver-357-player",
                                     "sfx-pistol-revolver-taurus-npc-joel": "sfx-pistol-revolver-357-npc"})),
    "shotgun-shorty": dict(gun="shorty", key="pistol-shotgun", module="pistol-shotgun",
                           host_module="ellie-guns/pistol-a-semi-auto.bin",
                           host_set="anim-overlay-player-specific-weapon-pistol-beretta",
                           ref=("anim-player-gun-shared", "ellie-pistol-reload-{st}-tac-part"),
                           prone=None,
                           muzzle=(0.0, 0.092, 0.323),
                           # sound: the Ruger's set as it is (art pistol-militia: set pistol-ruger, bank wpn-pistol-storm:
                           # player / npc / dryfire / clip-eject / clip-insert / charge-back / -release = the Part I
                           # Shorty's reload suffixes; no MP gun uses it) with the Part I Shorty waves (p1_sound.py)
                           sound=("pistol-militia", None, None)),
}
# loaded with the MP level (pak68 starlight-mp-test): the audio set's actor / module / bank, both spellings of the bank
# (file name and its internal name, as the Galil / Enforcer lines)
MP_LEVEL_ADDS = ["actor pistol-ruger", "symbol pistol-ruger", "sound-bank wpn-pistol-storm", "sound-bank wpn-pistol-ruger",
                 "sound-bank wpn-pistol-revolver-357"]
# TLOU2 reload stance -> Part I stance (p1_anims.STANCES)
STANCE = {"stand-aim": "aim", "stand": "relax", "crouch-aim": "crouch-aim", "crouch": "crouch"}
VARIANTS = ("tac", "emerg", "admin")
SHORTY_ART_FROM_BERETTA = (0x28, 0x68, 0x148, 0x150, 0x158, 0x160, 0x168, 0x190, 0x198)   # (+0x140 = the sound set: own, below)
SHORTY_ART_ZERO = (0x50, 0x58)        # long-gun sling strap names (rifle-strap-leather-red / -nylon-black)
SCOPE_REF = "pistol-xcaliber"         # the hunting pistol: the scoped TLOU2 pistol El Diablo copies its scope view from


def jobs():
    """[(clip id, bytes, kind, events ref)] of every baked clip; clip id = '<weapon>|<stance>|<kind>'"""
    out = []
    for weapon, g in GUNS.items():
        baked = p1_anims.load_baked(g["gun"])
        need = [(st, k) for st in p1_anims.STANCES for k in ("part", "add", "gun")] + [("fire", "gun")]
        miss = [n for n in need if n not in baked]
        if miss:
            raise SystemExit(f"T2R_P1_GUNS: baked clips missing for {g['gun']} {miss} - run "
                             f"python tools/part1/p1_anims.py bake (needs the Part I install + the UC4 ELF emulator)")
        t2st = {v: k for k, v in STANCE.items()}
        p1ev = p1_anims.load_events(g["gun"])
        for st, kind in need:
            ev = None
            if kind == "part":
                ev = events(baked[(st, kind)], p1ev.get(st, []), g["ref"][0], g["ref"][1].format(st=t2st[st]))
            out.append((f"{weapon}|{st}|{kind}", baked[(st, kind)], kind, ev))
    return out


def events(clip, p1_events, ref_pak, ref_clip):
    """anim events of a -part carrier: the Part I clip's own (p1_anims.part_events: sounds / haptics / hide + show of the
    magazine joint / weapon-reload at Part I's frame) + the TLOU2 reload's state events Part I does not author
    (blend-in, abort-out, abort-idle-*), rescaled to our clip and never before our weapon-reload"""
    frames = struct.unpack_from("<H", clip, 0xe)[0]
    fr_ref, ref = p1_carrier.ref_events(p1_carrier.game_pak(ref_pak), ref_clip)
    k = (frames - 1) / max(fr_ref - 1, 1)
    reload_sid = p1_carrier.fnv("weapon-reload")
    have = {s for s, _, _ in p1_events}
    if reload_sid not in have:
        raise SystemExit(f"{ref_clip}: the Part I clip has no weapon-reload event")
    r = max(f for s, f, _ in p1_events if s == reload_sid)
    state = {p1_carrier.fnv(n) for n in ("blend-in", "abort-out", "abort-idle-tense", "abort-idle-uneasy",
                                         "abort-idle-search", "abort-idle-unaware")}
    out = list(p1_events)
    for s, f, pr in ref:
        if s in state and s not in have:
            f2 = round(f * k, 3)
            if s != p1_carrier.fnv("blend-in"):
                f2 = max(f2, r)
            out.append((s, f2, pr))
    return out


def carrier_pak(log=print):
    """(pak bytes, {clip id: carrier clip name})"""
    j = jobs()
    data, names = p1_carrier.build(j, log)
    p1_carrier.check(data, {names[cid]: clip for cid, clip, _, _ in j}, log)
    return data, names


def renames(weapon, names):
    g = GUNS[weapon]
    out = {}
    for t2, st in STANCE.items():
        for v in VARIANTS:
            for k in ("part", "add", "gun"):
                c = names[f"{weapon}|{st}|{k}"]
                out[f"ellie-pistol-reload-{t2}-{v}-{k}"] = c
                if t2 in ("stand-aim", "stand"):
                    out[f"ellie-pistol-relaxed-reload-{t2}-{v}-{k}"] = c
    if g["prone"]:
        for t2 in ("prone", "supine"):
            for v in VARIANTS:
                for k in ("part", "add", "gun"):
                    out[f"ellie-pistol-reload-{t2}-{v}-{k}"] = g["prone"].format(st=t2, k=k)
    out["stand-p-aim-fire-gun"] = names[f"{weapon}|fire|gun"]
    return out


def overlay_modules(gamebin_dc1, stage_dc1, names, log=print):
    """writes the two overlay modules into the stage; returns their dc1-relative paths"""
    rels = []
    for weapon, g in GUNS.items():
        rel = f"{OVERLAY_DIR}/{g['module']}.bin"
        dst = os.path.join(stage_dc1, *rel.split("/"))
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        n, ch, add = p1_overlay.rewrite(os.path.join(gamebin_dc1, *rel.split("/")),
                                        os.path.join(gamebin_dc1, OVERLAY_DIR, *g["host_module"].split("/")),
                                        g["host_set"], renames(weapon, names), dst)
        log(f"overlay {rel}: {g['host_set']} ({n} entries: {ch} retargeted, {add} added) for {weapon}; tree entries with "
            f"module pointers: {len(p1_overlay.rewrite.reused)} use the target's own lambdas, {len(p1_overlay.rewrite.dropped)} left out "
            f"(lambdas can't cross modules: {', '.join('%#x' % f for f in p1_overlay.rewrite.dropped)})")
        rels.append(rel)
    return rels


SHORTY_CLASS = 1        # weapon-gameplay-def +0x0: 1 small firearm (pistols), 2 long gun, 3 melee, 4 throwable, 5 consumable
SHORTY_SUBTYPE = int(os.environ.get("T2R_SHORTY_SUBTYPE", "4"))   # +0x4: 0 pistol, 1 rifle, 2 auto, 4 shotgun, 5 bow


def patch_gameplay(wg_path, log=print):
    """weapon-gameplay.bin: the Shorty as a SIDEARM.  The clone of the over-under kept the long-gun class (def +0x0 = 2):
    the engine took the class from there, not from the art def - in testing the Shorty hung on 'leftHand' (the
    long-gun attach, the log 'exec end: ... weapon f27b5469addf5949 ... attach joint f170dca7466d11c1 (leftHand)') with the
    pistol grips posing the RIGHT hand, sat in the long-gun slot of the d-pad and was slung like a long gun.  +0x0 = 1 (every
    TLOU2 pistol's) gives the right-hand attach, the sidearm slot and the hip holster; +0x4 stays 4 (shotgun: the pellet /
    spread logic of its firearm def is untouched - T2R_SHORTY_SUBTYPE=0 makes it a plain pistol type if the game balks);
    +0x68 = the Beretta's (*zoom-camera-dof-settings-sp*: the pistol aim camera's depth of field)."""
    from dcfile import DcFile, fnv
    from weapon_clone import find_symbol, map_get
    d = DcFile(open(wg_path, "rb").read())
    mo = find_symbol(d, "*weapon-gameplay-defs*")
    s, b = map_get(d, mo, fnv("shotgun-shorty")), map_get(d, mo, fnv("pistol-beretta"))
    assert s and b, "weapon-gameplay: shotgun-shorty / pistol-beretta missing (clone first)"
    old = struct.unpack_from("<ii", d.data, s)
    assert old[0] in (1, 2), f"weapon-gameplay shotgun-shorty: unexpected class {old}"
    struct.pack_into("<ii", d.data, s, SHORTY_CLASS, SHORTY_SUBTYPE)
    assert not d.is_ptr(s + 0x68) and not d.is_ptr(b + 0x68)
    d.set_q(s + 0x68, d.q(b + 0x68))
    open(wg_path, "wb").write(d.save())
    log(f"weapon-gameplay shotgun-shorty: class/type {old} -> ({SHORTY_CLASS}, {SHORTY_SUBTYPE}) (sidearm: right hand, "
        f"holster slot), aim camera dof = the Beretta's")


def patch_art(art_path, names, log=print):
    from dcfile import DcFile, fnv
    from weapon_clone import find_symbol, hash_get, copy_obj
    d = DcFile(open(art_path, "rb").read())
    ho = find_symbol(d, "*weapon-art-defs-hash*")
    beretta = hash_get(d, ho, fnv("pistol-beretta"))

    def copy_slot(dst, src):
        d.set_q(dst, d.q(src))
        i = dst // 8
        if d.is_ptr(src):
            d._mark(dst)
        elif i // 8 < len(d.bits):
            d.bits[i // 8] &= ~(1 << (i % 8)) & 0xff

    def sound_def(d, ho, spec):
        """-> address of a pointer slot holding the weapon-sound-def to use (copy_slot source)"""
        src_art, aset, repl = spec
        sa = hash_get(d, ho, fnv(src_art))
        assert sa, f"{src_art} not in weapon-art.bin"
        if not aset:
            return sa + 0x140                                 # the other gun's own def, shared as is
        from weapon_clone import replace_sids_deep
        sd = d.q(sa + 0x140)
        nd = replace_sids_deep(d, sd, {fnv(k): fnv(v) for k, v in repl.items()})
        if nd == sd:
            nd = copy_obj(d, sd)
        d.set_ptr(nd + 0x18, d.append(aset.encode() + b"\0"))   # +0x18: the audio set (module aud-sfx-wpn-<set>, bank)
        holder = d.append(struct.pack("<Q", nd), ptr_slots=[0])
        return holder

    for weapon, g in GUNS.items():
        a = hash_get(d, ho, fnv(weapon))
        assert a, f"{weapon} not in weapon-art.bin (clone first)"
        if g["gun"] == "shorty":
            for off in SHORTY_ART_FROM_BERETTA:
                copy_slot(a + off, beretta + off)
            for off in SHORTY_ART_ZERO:                          # the over-under's sling straps: none on a sidearm
                assert not d.is_ptr(a + off)
                d.set_q(a + off, 0)
        elif os.environ.get("T2R_P1_DIABLO_ANIMTYPE", "beretta") != "keep":
            copy_slot(a + 0x68, beretta + 0x68)
        # sound set (art +0x140 weapon-sound-def): the host set whose bank build_dll rebuilds with the Part I waves
        # (p1_sound.py); the Shorty took the Beretta's set originally (wrong sounds, and the 9mm's bank is shared)
        snd = sound_def(d, ho, g["sound"])
        copy_slot(a + 0x140, snd)
        key = d.append(g["key"].encode() + b"\0")
        d.set_ptr(a + 0x180, key)
        fa = copy_obj(d, d.q(a + 0x128), min_size=0x140)       # fields up to +0x138 (mod-laser)
        d.set_ptr(a + 0x128, fa)
        d.set_q(fa + 0x10, fnv(names[f"{weapon}|fire|gun"]))
        d.set_q(fa + 0x20, fnv(names[f"{weapon}|aim|gun"]))
        d.set_q(fa + 0x38, 0)
        # +0x58 = the joint weapon-event hide- / show-magazine hides: Part I's El Diablo hides its uber_cylinder (Part I
        # weapon-art) while the reload clip moves it out of the gun; on our rig that is 'cylinder'
        d.set_q(fa + 0x58, fnv("cylinder" if g["gun"] == "diablo" else "magazine"))
        vec = copy_obj(d, d.q(fa + 0x108), min_size=0x10)
        d.set_ptr(fa + 0x108, vec)
        struct.pack_into("<3f", d.data, vec, *g["muzzle"])
        if g.get("scope_eye"):
            # El Diablo's scope view = the hunting pistol's (p1_scope_compare.py, weapons.md 10.6): the scope camera sits at
            # firearm-art +0x140 (a vector, gun space: the eyepiece; the revolver's is null - with the scope on, the camera
            # went to the gun's root: the "first-person-ish zoom with the gun in front of the camera, no overlay"),
            # +0x148 / +0x150 its scope parameters (the revolver's: -1 = none), art +0x1c0 = 8 the scope reticle / overlay
            xc = hash_get(d, ho, fnv(SCOPE_REF))
            xfa = d.q(xc + 0x128)
            assert d.is_ptr(xfa + 0x140) and d.q(xfa + 0x140), f"{SCOPE_REF} firearm-art has no scope eye vector"
            eye = copy_obj(d, d.q(xfa + 0x140), min_size=0x10)
            if g.get("scope_eye_shift"):
                import p1_guns
                assert tuple(g["scope_eye_shift"]) == tuple(p1_guns.SCOPE_SHIFT), "scope eye shift != the model's scope shift"
                struct.pack_into("<3f", d.data, eye, *(a + b for a, b in zip(struct.unpack_from("<3f", d.data, eye),
                                                                           g["scope_eye_shift"])))
            else:
                struct.pack_into("<3f", d.data, eye, *g["scope_eye"])
            if not d.is_ptr(fa + 0x140):
                d._mark(fa + 0x140)
            d.set_q(fa + 0x140, eye)
            for off in (0x148, 0x150):
                d.set_q(fa + off, d.q(xfa + off))
            d.set_q(a + 0x1c0, d.q(xc + 0x1c0))
        log(f"weapon-art {weapon}: overlay key {g['key']}, own firearm-art (fire gun {names[f'{weapon}|fire|gun']}, "
            f"reload gun {names[f'{weapon}|aim|gun']}, muzzle {g['muzzle']})"
            + (", Beretta hold / holster / anim type" if g["gun"] == "shorty" else ", Beretta anim type (one-clip reload)"))
    open(art_path, "wb").write(d.save())
