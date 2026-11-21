"""Feature patches for the T2R client winmm.dll (code edits, applied on top of the
original mod DLL + server-address patch).

  python winmm_patches.py <in.dll> <out.dll> [patch ...]      # default: all patches
  python winmm_patches.py --list

Every patch states the exact original bytes; applying refuses to touch a DLL whose
bytes differ, so a patch can never land on the wrong code.
File offset = VMA - 0x180000000 - 0xC00 for .text.
"""
import sys

TEXT_DELTA = 0x180000000 + 0xC00

PATCHES = {
    # Matchmaking lobby list for 4v4 ("5 in queue" showed 4 / 4): the find-match page's lobby (FUN_180065760,
    # the base client's net-gui2.cpp fillLobby) has 8 rows (kLobbyRows) but fills / counts kLobbySlots = kMaxNetPlayers = 4. -> 8.
    "lobby8-found-loop": dict(vma=0x180065A9D, orig=bytes.fromhex("41 83 fe 04"), new=bytes.fromhex("41 83 fe 08"), desc="lobby: found-match roster rows < 8"),
    "lobby8-fill-test": dict(vma=0x180065AA7, orig=bytes.fromhex("41 83 fe 03"), new=bytes.fromhex("41 83 fe 07"), desc="lobby: placeholder rows while filled <= 7"),
    # (the unused-rows clear is a do-while ending on 'cmp ebp, 8; je': started at 8 it would never end. With all
    # 8 rows used there is nothing to clear: jump straight to the count text at 0x180065C59)
    "lobby8-clear-skip": dict(vma=0x180065AB6, orig=bytes.fromhex("bd 04 00 00 00"), new=bytes.fromhex("e9 9e 01 00 00"), desc="lobby: no unused rows to clear (jmp 0x180065C59)"),
    "lobby8-count": dict(vma=0x180065C6E, orig=bytes.fromhex("41 b9 04 00 00 00"), new=bytes.fromhex("41 b9 08 00 00 00"), desc="lobby: 'n / 8'"),
    "lobby8-search-loop": dict(vma=0x180065EAA, orig=bytes.fromhex("41 83 fe 04"), new=bytes.fromhex("41 83 fe 08"), desc="lobby: searching names rows < 8"),
    "lobby8-fill-loop": dict(vma=0x180065F04, orig=bytes.fromhex("83 fb 04"), new=bytes.fromhex("83 fb 08"), desc="lobby: placeholder rows up to 8"),
    # Supply boxes (FUN_18004ce10, refilled on a timer by FUN_18004ee40) draw items from
    # a pool of crafting ingredients (alcohol, binding, blade, canister, explosive, rag;
    # static init 0x180053ec0) but the spawn loop only spawns "*ammo*", "health-kit" and
    # "smoke-bomb": anything else hits `je 0x18004dc50` (skip). NOP it so every pool item
    # spawns as a pickup (count r14d = 1, set just before at 0x18004dad2).
    "box-ingredients": dict(
        # The fill loop skipped everything that wasn't ammo / health-kit / smoke-bomb.
        # 0x18004daf4 (12 bytes up to 0x18004db00, the spawn path; r14d = quantity = 1):
        #   jne 0x18004db00        smoke-bomb: keep quantity 1
        #   mov r14d, 3            anything else (ingredients): quantity 3
        #   nop4
        vma=0x18004DAF4,
        orig=bytes.fromhex("0f 84 56 01 00 00 66 0f 1f 44 00 00"),
        new=bytes.fromhex("75 0a 41 be 03 00 00 00 0f 1f 40 00"),
        desc="crafting ingredients drop from supply boxes again, 3 per pickup (wishlist #1)",
    ),
    # The box fill (FUN_18004ce10) inserts "smoke-bomb" into the item list when the player
    # holds < 3 (0x18004d7c5 cmp/ja). Repurpose that insert: always, and the name becomes
    # "crowbar" (SSO string: len 10 -> 7, "smoke-bo"+"mb" -> "crowbar" + NUL padding). Spawns through
    # the generic spawn-item-pickup path (needs box-ingredients). Smoke bombs are craftable.
    "box-crowbar": dict(
        vma=0x18004D7CD,
        orig=bytes.fromhex("0f 87 a5 00 00 00 48 c7 85 e8 26 00 00 00 00 00 00 48 c7 85 f0 26 00 00 0a 00 00 00"
                           " 48 c7 85 f8 26 00 00 0f 00 00 00 48 b8 73 6d 6f 6b 65 2d 62 6f 48 89 85 e0 26 00 00"
                           " 66 c7 85 e8 26 00 00 6d 62"),
        new=bytes.fromhex("66 0f 1f 44 00 00 48 c7 85 e8 26 00 00 00 00 00 00 48 c7 85 f0 26 00 00 07 00 00 00"
                          " 48 c7 85 f8 26 00 00 0f 00 00 00 48 b8 63 72 6f 77 62 61 72 00 48 89 85 e0 26 00 00"
                          " 66 c7 85 e8 26 00 00 00 00"),
        desc="TEST: every supply box refill includes a crowbar pickup (wishlist #2, replaces the smoke-bomb insert)",
    ),
    # Both mod inserts (health-kit, then smoke-bomb/crowbar) sit behind a rarely-true gate
    # (0x18004d63f cmp [rbp+0x29a7],1; jne 0x18004d878 = skip both). Retarget the jne to
    # 0x18004d767 (the second insert) so only the health-kit insert stays gated.
    "box-crowbar-ungated": dict(
        vma=0x18004D646,
        orig=bytes.fromhex("0f 85 2c 02 00 00"),
        new=bytes.fromhex("0f 85 1b 01 00 00"),
        desc="TEST: the crowbar insert no longer depends on the health-kit gate",
    ),
    # Marking enemies (flashlight-toggle while aiming at one: highlight + callout + msg 9 to
    # teammates, FUN_18001c370) only ran with the Hawk-eyed perk: the perk dispatcher
    # FUN_18001d6b0 tests perk bit 1 of ctx+0x2c70 (`test sil,1; jne`). In 2013 Factions
    # anyone could mark; Hawk-eyed only made marks last longer / glow. jne -> jmp.
    # MP main menu version label (bottom left), FUN_180063370 sets anim-group.versionText.
    # MP options added by the mod (engine option hook FUN_180069170 returns pointers to winmm
    # globals): reticle 0 moving / 1 marker widget / 2 grey / 3 none (DAT_180138228, default 2),
    # radar style 0 square / 1 circle (DAT_18013822c, default 1 already). Default the reticle to
    # the marker widget; a value saved in the player's profile still wins.
    # GEAR UP loadout point costs as in 2013 Factions (13 LP total). Cost = dword +0x18 of the
    # small firearm table (0x1800a0e90, stride 0x38) / purchasable table (0x1800a0f40, stride
    # 0x40), +0x20 of a skill record. Large firearms cost a hardcoded 2 (2013: 2, bow 3; the ext sets the bow row to 3 in install_weapon_tables).
    "lp-9mm-free": dict(vma=0x1800A0EA8, orig=bytes.fromhex("01 00 00 00"), new=bytes.fromhex("00 00 00 00"),
                        desc="LP: Beretta (9mm) is free"),
    "lp-revolver-free": dict(vma=0x1800A0EE0, orig=bytes.fromhex("02 00 00 00"), new=bytes.fromhex("00 00 00 00"),
                             desc="LP: revolver is free"),
    "lp-mpx5-3": dict(vma=0x1800A1018, orig=bytes.fromhex("06 00 00 00"), new=bytes.fromhex("03 00 00 00"),
                      desc="LP: MPX5 3 (2013 purchasables cost 3-4)"),
    "lp-crossbow-3": dict(vma=0x1800A1058, orig=bytes.fromhex("02 00 00 00"), new=bytes.fromhex("03 00 00 00"),
                          desc="LP: crossbow 3"),
    "lp-hawkeyed-2": dict(vma=0x1800A11C8, orig=bytes.fromhex("03 00 00 00"), new=bytes.fromhex("02 00 00 00"),
                          desc="LP: Hawk-Eyed 2 (2013 level 1: longer marks)"),
    "lp-marathon-1": dict(vma=0x1800A1328, orig=bytes.fromhex("02 00 00 00"), new=bytes.fromhex("01 00 00 00"),
                          desc="LP: Marathon Runner 1 (2013 level 1)"),
    "lp-steadyhands-4": dict(vma=0x1800A1278, orig=bytes.fromhex("05 00 00 00"), new=bytes.fromhex("04 00 00 00"),
                             desc="LP: Steady Hands 4"),
    "reticle-marker-default": dict(
        vma=0x180138228,
        orig=bytes.fromhex("02 00 00 00"),
        new=bytes.fromhex("01 00 00 00"),
        desc="MP reticle option defaults to MARKER WIDGET",
    ),
    "version-text": dict(
        vma=0x18012279F,
        orig=b"v1.08 BETA",
        new=b"v0.14 BETA",
        desc="main menu shows v0.14 BETA",
    ),
    "mark-without-perk": dict(
        vma=0x18001D6C9,
        orig=bytes.fromhex("40 f6 c6 01 75 28"),
        new=bytes.fromhex("40 f6 c6 01 eb 28"),
        desc="every player can mark enemies (was Hawk-eyed only)",
    ),
    # EXPERIMENT: the mod hooks the game's backpack/crafting-menu opener (tlou-ii.exe+0xF7B740,
    # FUN_18004e200 builds the supply box table (0x18013a4a8, 0x48 bytes per box) from the
    # level's to1-supplybox-1..4 spawners (+ their -itempos-1..16). 4 is hard-coded three
    # times: the "capacity > 3" shortcut (re-inits exactly 4 entries in place), the resize
    # count and the loop bound. The shortcut is dropped (always resize, from a cleared table)
    # and both counts become 12; a box number the level doesn't have stays an empty entry.
    "supplybox-12-cap": dict(
        vma=0x18004E27F,
        orig=bytes.fromhex("77 1a"),
        new=bytes.fromhex("90 90"),
        desc="supply box table: always resized (no in-place re-init of exactly 4 boxes)",
    ),
    "supplybox-12-resize": dict(
        vma=0x18004E28C,
        orig=bytes.fromhex("ba 04 00 00 00"),
        new=bytes.fromhex("ba 0c 00 00 00"),
        desc="supply box table: 12 entries",
    ),
    "supplybox-12-loop": dict(
        vma=0x18004E38F,
        orig=bytes.fromhex("83 fb 04"),
        new=bytes.fromhex("83 fb 0c"),
        desc="supply box table: look up to1-supplybox-1..12",
    ),
    # SafetyHook object @0x180161b58, trampoline ptr at +0x20 = 0x180161b78) with detour
    # 0x1800304d0, which pushes the mod store ("to1/backpack-menu") instead. Replace the
    # detour's first instruction with `jmp [rip+0x1316a2]` -> trampoline = original game
    # function, i.e. TAB opens the game's own backpack/crafting menu (store unreachable).
    "tab-native-backpack": dict(
        vma=0x1800304D0,
        orig=bytes.fromhex("48 83 ec 28 80 3d"),
        new=bytes.fromhex("ff 25 a2 16 13 00"),
        desc="EXPERIMENT: TAB opens the game's native backpack/crafting menu",
        default=False,
    ),
}


def apply(data, names):
    out = bytearray(data)
    for n in names:
        p = PATCHES[n]
        off = p["vma"] - TEXT_DELTA
        cur = bytes(out[off:off + len(p["orig"])])
        if cur == p["new"]:
            print(f"{n}: already applied")
            continue
        if cur != p["orig"]:
            raise SystemExit(f"{n}: unexpected bytes at {off:#x}: {cur.hex(' ')}")
        out[off:off + len(p["new"])] = p["new"]
        print(f"{n}: applied at {off:#x} ({p['desc']})")
    return bytes(out)


if __name__ == "__main__":
    if sys.argv[1:] == ["--list"]:
        for n, p in PATCHES.items():
            print(f"{n:20s} {p['desc']}")
        sys.exit(0)
    src, dst, *names = sys.argv[1:]
    default = [n for n, p in PATCHES.items() if p.get("default", True)]
    data = apply(open(src, "rb").read(), names or default)
    open(dst, "wb").write(data)
