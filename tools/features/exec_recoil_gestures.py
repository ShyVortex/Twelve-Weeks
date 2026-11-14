"""Execution gun recoil: six gesture defs of gestures/ellie-gestures.bin re-pointed at TLOU2's OWN per-gun fire recoil clips.

The engine's aim recoil is a pair of clips per gun in the player gun paks (actor97/anim-player-gun-shared.pak, anim-player-gun-ellie.pak):
  <gun>-fire-start  flag 2 (ADDITIVE, header u16 @0x20), 5-12 frames @ 30, frame 0 = identity, peaks 28-37 deg on one arm joint, decays
  <gun>-fire-sub    flag 0, 1 frame, the same joint set (the gesture's "part" clip = the joint mask)
which the weapon-overlay state machine plays on a shot. The execution plays a full baked clip with that overlay switched off, so the shot has no
arm / gun reaction. A GESTURE is the engine's way to layer an additive clip over whatever plays (the ext already does it for hit reactions and the
cough): a gesture def of gestures/ellie-gestures.bin is { +0 -> { part clip sid, add clip sid, 0, 0, 0 }, +8 / +0x10 blend structs, ...,
+0x30 own name sid, +0x50 flags } (see re/uc4-own-movement.md: gesture_ takes gesture DEFS, not raw clip names). No pak carries a def for the fire
clips, so six defs the multiplayer never plays (the aim-pistol prone / supine and aim-bolt-rifle supine hit gestures, flags identical to the standing
ones) are re-pointed IN PLACE: same file size, no new pointers, nothing else in the file changes.

SLOTS is the single source: tools/ext/execrecoil.h is generated from it (python tools/features/exec_recoil_gestures.py --header) and
tools/tests/test_exec_recoil.py checks both.

  python tools/features/exec_recoil_gestures.py --check            verify the game's file has the six defs and patch them in memory
  python tools/features/exec_recoil_gestures.py --header           (re)write tools/ext/execrecoil.h
  python tools/features/exec_recoil_gestures.py --write OUT.bin    write the patched file
T2R_EXEC_RECOIL=0 (build_dll): no overlay, the game's file is used.
"""
import os
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)
import dcfile  # noqa: E402

GESTURE_TYPE = 0x525be520907a83fa        # type sid of a name table entry [name sid][type sid][ptr to the def]
DEF_FLAGS = 0x0000010001000100           # def +0x50 of the standing hit gestures: the slots carry the same
_P = "gesture-ellie-idle-ub-hr-front-%s-shldr-aim-%s"
# Amplitude of each class's recoil as a fraction of the stock <gun>-fire-start clip (SLIGHT). One constant per class, picked so the ARM-CHAIN
# peak (clavicle / shoulder = upper arm / elbow = forearm / wrist = hand, either side) lands in the target range; exec_recoil_clips.py prints the result
# and tools/tests/test_exec_recoil.py asserts it. Stock chain peaks: pistol 36.8 deg, revolver 33.2, shotgun 43.4, bolt rifle 28.3, mpx5 13.8.
K_PISTOL = 0.16      # -> 5.9 deg (target 4-8)
K_REVOLVER = 0.18    # -> 6.0 deg (target 4-8, heavier gun)
K_AUTO = 0.29        # -> 4.0 deg per shot (target 3-5; the Full-Auto Rifle's clip, ellie rig, for every automatic / burst / assault long gun)
K_BOLT = 0.21        # -> 5.9 deg
K_SHOTGUN = 0.18     # -> 7.8 deg (target 6-10)
TARGETS = {"pistol": (4.0, 8.0), "revolver": (4.0, 8.0), "auto": (3.0, 5.0), "bolt": (4.0, 8.0), "shotgun": (6.0, 10.0)}
CARRIER_PAK = "anim-ellie-horse.pak"   # the HORSE-RIDING animation pak: its additive horse clips carry the scaled copies (a modified copy ships; the level loads it). Horse riding does not exist in multiplayer
# (slot name, gesture def, part clip (joint mask, stock), source add clip (stock, ellie rig), source pak, carrier clip (name in the game), factor)
SLOTS = [
    ("pistol",   _P % ("r", "pistol-prone"),      "ellie-pistol-fire-sub",                 "ellie-pistol-fire-start",              "anim-player-gun-shared.pak", "ellie-horse-blizzard-block-snow-a--add", K_PISTOL),
    ("revolver", _P % ("l", "pistol-prone"),      "ellie-pistol-revolver-357-fire-sub",    "ellie-pistol-revolver-357-fire-start", "anim-player-gun-shared.pak", "ellie-horse-rhand-on-thigh--add",         K_REVOLVER),
    ("auto",     _P % ("r", "pistol-supine"),     "rifle-mpx5-fire-sub",                   "rifle-mpx5-fire-start",                "anim-player-gun-ellie.pak",  "ellie-horse-aim-lg-mid--add",             K_AUTO),
    ("bolt",     _P % ("r", "bolt-rifle-supine"), "rifle-remington-bolt-fire-sub",         "rifle-remington-bolt-fire-start",      "anim-player-gun-ellie.pak",  "ellie-horse-pet-r-hind--add",             K_BOLT),
    ("shotgun",  _P % ("l", "bolt-rifle-supine"), "shotgun-remington-pump-stand-fire-sub", "shotgun-remington-pump-stand-fire",    "anim-player-gun-ellie.pak",  "ellie-horse-l-hand-touch-face--add",      K_SHOTGUN),
]
GAME_BIN = os.path.join(ROOT, "re", "gamebin", "dc1", "gestures", "ellie-gestures.bin")
HEADER = os.path.join(ROOT, "tools", "ext", "execrecoil.h")


def exec_game_dir():
    return os.environ.get('T2_GAME', 'C:/Games/The Last of Us Part II Remastered')


def fnv(s):
    h = 0xcbf29ce484222325
    for c in s.encode():
        h = ((h ^ c) * 0x100000001b3) & 0xffffffffffffffff
    return h


def _entries(f):
    """{name sid: (entry offset, def offset)} of the gesture name table"""
    out = {}
    for o in range(0, f.size - 0x18, 8):
        if f.q(o + 8) == GESTURE_TYPE and f.is_ptr(o + 0x10):
            out.setdefault(f.q(o), []).append((o, f.q(o + 0x10)))
    return out


def patch(raw):
    """the patched file bytes (same length); asserts the layout it relies on"""
    f = dcfile.DcFile(raw)
    ent = _entries(f)
    structs = {}
    for lst in ent.values():
        for _, d in lst:
            if f.is_ptr(d):
                structs[f.q(d)] = structs.get(f.q(d), 0) + 1
    for name, gdef, part, src, srcpak, add, k in SLOTS:
        hits = ent.get(fnv(gdef), [])
        assert len(hits) == 1, "%s: %d name table entries for %s" % (name, len(hits), gdef)
        d = hits[0][1]
        assert f.is_ptr(d) and f.q(d + 0x30) == fnv(gdef), "%s: def layout differs" % name
        assert f.q(d + 0x50) == DEF_FLAGS, "%s: def flags %#x" % (name, f.q(d + 0x50))
        s = f.q(d)
        assert structs[s] == 1, "%s: the clip struct is shared by %d defs" % (name, structs[s])
        assert f.q(s + 16) == 0 and f.q(s + 24) == 0 and f.q(s + 32) == 0, "%s: clip struct layout differs" % name
        f.set_q(s, fnv(part))
        f.set_q(s + 8, fnv(add))
    out = bytes(f.data) + struct.pack("<I", len(f.bits)) + bytes(f.bits) + f.tail
    assert len(out) == len(raw), "size changed %d -> %d" % (len(raw), len(out))
    return out


def verify(raw):
    f = dcfile.DcFile(raw)
    ent = _entries(f)
    for name, gdef, part, src, srcpak, add, k in SLOTS:
        d = ent[fnv(gdef)][0][1]
        s = f.q(d)
        assert f.q(s) == fnv(part) and f.q(s + 8) == fnv(add), "%s: not patched" % name


def make_overlay(gamebin_dc1, overlay_dc1):
    """gestures/ellie-gestures.bin with the six defs re-pointed -> overlay_dc1/gestures/ellie-gestures.bin (same size as the game file)"""
    raw = open(os.path.join(gamebin_dc1, "gestures", "ellie-gestures.bin"), "rb").read()
    out = patch(raw)
    verify(out)
    dst = os.path.join(overlay_dc1, "gestures", "ellie-gestures.bin")
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    open(dst, "wb").write(out)
    print("exec recoil: %d gesture defs of gestures/ellie-gestures.bin re-pointed at the fire recoil clips (%s)" % (len(SLOTS), ", ".join(s[0] for s in SLOTS)))
    return dst


def header_text():
    L = ["// generated by tools/features/exec_recoil_gestures.py --header - do not edit",
         "// execution gun recoil: gesture def (re-pointed in gestures/ellie-gestures.bin, same file size) -> the carrier clip it plays (the stock fire-start clip scaled by the class factor, exec_recoil_clips.py)",
         "enum { ER_PISTOL, ER_REVOLVER, ER_AUTO, ER_BOLT, ER_SHOTGUN, ER_N };",
         "static const struct { const char *gesture, *add; } EXEC_RECOIL[ER_N] = {"]
    for name, gdef, part, src, srcpak, add, k in SLOTS:
        L.append('    {"%s", "%s"},   // %s x%.2f of %s (mask clip %s)' % (gdef, add, name, k, src, part))
    L.append("};")
    return "\n".join(L) + "\n"


def main():
    if "--header" in sys.argv:
        with open(HEADER, "w", newline="") as fh:
            fh.write(header_text())
        print("wrote", HEADER)
    raw = open(GAME_BIN, "rb").read()
    out = patch(raw)
    verify(out)
    print("ok: %d defs patchable in %s (%d bytes, unchanged size)" % (len(SLOTS), GAME_BIN, len(out)))
    if "--write" in sys.argv:
        p = sys.argv[sys.argv.index("--write") + 1]
        open(p, "wb").write(out)
        print("wrote", p)


if __name__ == "__main__":
    main()
