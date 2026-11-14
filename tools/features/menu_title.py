"""Title (boat) screen background: Ellie's Hillcrest overlook instead of the boat (re/menu-title-hillcrest.md).

The stock title / SP main menu world is the level set "menu-main" of bin/dc1/level-sets/level-sets-menu.bin:
    menu-main-common               menu, menu-beach-script (title script ss-main-menu-boat, camera cam-main-menu-boat-1, boat actors)  KEPT
    menu-main-pre-completion       menu-beach-a (+ -water, -audio)         \  one of the two by the player's save
    menu-main-post-completion      menu-beach-b, sky-mm-end (+ -water, -audio)  /   (+ the *-preload twins)
The pre / post level lists are replaced by the Hillcrest overlook set (Rescue Jesse, Seattle day 2: tower hill with Jesse's smoke plume
fx-res-car-smoke-plume-* of the level res-smoke-plume-fx). Everything else (the actors lists, the other arrays, the common set) stays byte for
byte. The title camera is the ext's (titlebg.c, over the same render-camera hook as the MP menu camera).

Audio: gbl-main-menu (the title's UI sounds) is declared by menu-beach-*-audio in pak68.txt; those levels go (their env-main-menu-beach ocean
bed and the boat creaks would play under the overlook), so patch_registry() gives menu-beach-script (kept) that bank. res-const-audio brings
lvl-res-amb (+ lvl-res-game, ir-pack dsp-rescue-jesse), res-neighborhood-audio lvl-res-neighborhood-game.

Gate: the file ships as a whole-file override inside the mod (re/dccgame/mods/t2r-data); the launcher's SP switch (release/launcher/lib/spmode.js)
parks the whole mod (winmm.dll, t2r-ext.dll, tlou-ii-mp\\, mods\\) so an SP-only launch runs the stock files and keeps the boat.
T2R_MENU_BOAT=1 at build time = no override (the stock boat).
"""
import os
import struct

from dcfile import DcFile, fnv

SETS = ("menu-main-pre-completion", "menu-main-post-completion",
        "menu-main-pre-completion-preload", "menu-main-post-completion-preload")
# The shot (SP freecam at 14.855 2.957 530.968): the levels active there, minus the gameplay parts, sp-all, world-*, accessibility, workbench and
# the *-script levels (NPCs, pickups, inactive fight-houses / ruins). NO smoke: res-smoke-plume-fx and its part level are not listed. Still loaded and
# smoke-related, in shared levels: the script icon ss-res-const-smoke-plume-1 (res-stores-neighborhood-const, 194 m away) and in res-neighborhood-audio the
# fire loop snd-pos-car-fire-base-layer-lp-1 / ss-snd-res-const-smoke-plume-fire-lp-1 (288 to 310 m away, out of earshot of a fire loop; in-game check).
# Cull by view: every level's geometry bounds extend 450 m or more ahead of the camera, so no whole level is behind it (nothing cut).
LEVELS = ["res-const-audio", "res-const-dispatcher-fx", "part-level-res-const-dispatcher-fx", "res-const-render", "res-const-texture-adjust",
          "res-neighborhood-audio", "res-neighborhood-fight-stores-end", "res-neighborhood-fight-stores-end-mesh-water",
          "res-neighborhood-fight-tower-hill", "part-level-res-neighborhood-fight-tower-hill", "res-neighborhood-fight-tower-hill-wide",
          "res-neighborhood-house-intro", "res-neighborhood-house-intro-detail", "res-neighborhood-house-intro-probes-off",
          "res-neighborhood-house-intro-water", "res-neighborhood-house-intro-wide",
          "res-stores-alley", "res-stores-audio", "res-stores-neighborhood-const", "sky-act2-day-2-rescue-jesse"]
TITLE_SCRIPT_LEVEL = "menu-beach-script"
TITLE_BANK = "gbl-main-menu"


def _entries(f):
    cnt = struct.unpack_from("<I", f.data, 0x14)[0]
    eo = struct.unpack_from("<Q", f.data, 0x18)[0]
    return {struct.unpack_from("<Q", f.data, eo + i * 24)[0]: struct.unpack_from("<Q", f.data, eo + i * 24 + 16)[0]
            for i in range(cnt)}


def _cstr(f, o):
    return f.data[o:f.data.index(b"\0", o)].decode("latin1")


def patch_level_sets(raw, levels=LEVELS):
    """level-sets-menu.bin bytes with the four pre / post sets' level lists replaced (array 0 of their level-set-arrays block: pointer, count)."""
    f = DcFile(raw)
    ent = _entries(f)
    names = []
    for s in SETS:
        e = ent[fnv(s)]
        assert _cstr(f, f.q(e)) == s, s
        arr = f.q(e + 0x10)
        lp, cnt = struct.unpack_from("<QI", f.data, arr)
        assert cnt >= 3, (s, cnt)
        pre = s.endswith("-preload")
        lst = []
        for lv in levels:
            fl = (3, 7) if (not pre or lv.endswith("-audio")) else (7, 0)      # the stock preload twins mark their non-audio entries (7, 0)
            en = f.append(struct.pack("<QQII", 0, fnv(lv), *fl), ptr_slots=(0,), tag="level-entry")
            lst.append(en)
            names.append((en, lv))
        lo = f.append(struct.pack(f"<{len(lst)}Q", *lst), ptr_slots=tuple(range(0, 8 * len(lst), 8)))
        f.set_ptr(arr, lo)
        struct.pack_into("<I", f.data, arr + 8, len(lst))
    for en, lv in names:                         # strings last: nothing moves them now
        f.set_ptr(en, len(f.data))
        f.data += lv.encode() + b"\0"
    f.data += bytes((-len(f.data)) % 8)
    return f.save()


def check(data, levels=LEVELS):
    """read back: the four sets list exactly `levels`, the common set is untouched in shape."""
    f = DcFile(data)
    ent = _entries(f)
    for s in SETS:
        arr = f.q(ent[fnv(s)] + 0x10)
        lp, cnt = struct.unpack_from("<QI", f.data, arr)
        got = [_cstr(f, f.q(f.q(lp + 8 * i))) for i in range(cnt)]
        assert got == list(levels), (s, got)
        for i in range(cnt):
            assert struct.unpack_from("<Q", f.data, f.q(lp + 8 * i) + 8)[0] == fnv(got[i]), (s, got[i])
    arr = f.q(ent[fnv("menu-main-common")] + 0x10)
    lp, cnt = struct.unpack_from("<QI", f.data, arr)
    assert [_cstr(f, f.q(f.q(lp + 8 * i))) for i in range(cnt)] == ["menu", TITLE_SCRIPT_LEVEL]
    return True


def make_overlay(src, out_dir):
    """src = the game's level-sets-menu.bin; writes out_dir/level-sets-menu.bin (build_dll's overlay loop adds it to the manifest and sets
    the modules.bin size of level-sets/level-sets-menu)."""
    os.makedirs(out_dir, exist_ok=True)
    raw = open(src, "rb").read()
    data = patch_level_sets(raw)
    check(data)
    open(os.path.join(out_dir, "level-sets-menu.bin"), "wb").write(data)
    print(f"menu title: Hillcrest overlook in menu-main pre / post completion ({len(LEVELS)} levels, level-sets-menu.bin {len(raw)} -> {len(data)} bytes)")
    return len(data)


def patch_registry(path):
    """pak68.txt: the kept title script level also declares the title's UI sound bank (it hung on the removed menu-beach-*-audio levels)."""
    text = open(path, "rb").read().decode("latin1")
    nl = "\r\n" if "\r\n" in text else "\n"
    lines = text.split(nl)
    i = lines.index("level-name " + TITLE_SCRIPT_LEVEL)
    j = i + 1
    while j < len(lines) and not lines[j].startswith("level-name "):
        j += 1
    if "sound-bank " + TITLE_BANK in lines[i:j]:
        return False
    k = i + 1
    while k < j and not lines[k].startswith("package "):
        k += 1
    while k + 1 < j and lines[k + 1].startswith("package "):
        k += 1
    lines.insert(k + 1, "sound-bank " + TITLE_BANK)
    open(path, "wb").write(nl.join(lines).encode("latin1"))
    return True
