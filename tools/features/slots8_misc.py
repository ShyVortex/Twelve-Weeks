"""Everything outside the session layer and the net player records that was sized for 4 players:

  * PA_SLOT (per-slot anim replay state, 0x18013B2A0, 4 x 0x77E8) -> 8 entries (relocated, rip-relative references retargeted,
    unrolled chains extended, the offset loop FUN_180028C40 now ends at 8 * 0x77E8);
  * match state in the match context: stats[slot] (kills, deaths, parts; 12 bytes at ctx+0x2B98) grows in place from 4 to 8 rows
    (it takes over the 48 bytes of slotState behind it), slotState[slot] (dead, respawnGrace, grantCooldown; 12 bytes at ctx+0x2BC8)
    moves to .t2r8 (D_slotstate) and every access is re-based (disp32 rewritten; the match context is the base register);
  * small per-slot static arrays (anim stream bookkeeping, death animation state) -> 8 entries;
  * `cmp slot, 3` / `cmp slot, 4` guards and iterator end sentinels (the sentinel patches of NetPlayers' range-for loops are in
    slots8_players.ITER_END).
"""
import struct

CTX = 0x180135388
PA_OLD = 0x18013B2A0
PA_STRIDE = 0x77E8
SS_OLD = 0x2BC8
N = 8


def build(S):
    from slots8 import decode  # noqa: F401
    # ================================================================================== PA_SLOT
    pa = S.data("pa_slot", N * PA_STRIDE)
    S.relocate_table("pa_slot", PA_OLD, 4 * PA_STRIDE, pa)
    PA3 = PA_OLD + 3 * PA_STRIDE
    PA2 = PA_OLD + 2 * PA_STRIDE
    # chains: "which slot owns this anim controller" (found -> falls through to the shared tail)
    S.copy_chain("pa_find_a", hook=(0x180026E51, 0x180026E73), tmpl=(0x180026E51, 0x180026E73), win_lo=PA3, stride=PA_STRIDE,
                 new_lo=pa, tmpl_entry=3, first=3, next_targets=(0x180026F8C,), fall="end", slot_imm=(0x180026E65,),
                 note="anim locator hook: owner slot search 3..7")
    S.copy_chain("pa_find_b", hook=(0x18002705F, 0x180027075), tmpl=(0x18002705F, 0x180027075), win_lo=PA3, stride=PA_STRIDE,
                 new_lo=pa, tmpl_entry=3, first=3, next_targets=(0x1800273E1,), fall="end", slot_imm=(0x180027066,),
                 note="anim set-puppet: owner slot search 3..7")
    # session residual clear (4 identical blocks; the last one uses esi=0 as the zero, so copy block 2)
    S.copy_chain("pa_clear_all", hook=(0x180029230, 0x1800292AA), tmpl=(0x1800291B4, 0x180029230), win_lo=PA2, stride=PA_STRIDE,
                 new_lo=pa, tmpl_entry=2, first=3, fall="next", end=0x1800292AA, note="NetAnim residuals clear: slots 3..7")
    S.asm(f"""
# FUN_180029A30 NetAnimClear(bool full in cl): per slot npcAC/proc/streamAlive/seq = 0, and with `full` also the dictionary epoch + flag
S8_netanimclear:
    xor eax, eax
    lea rdx, [rip + D_pa_slot]
    mov r8d, {N}
1:
    mov qword ptr [rdx], 0
    mov qword ptr [rdx + 8], 0
    mov byte ptr [rdx + 0x2894], 0
    xor r9d, r9d
    xchg dword ptr [rdx + 0x4cb0], r9d
    test cl, cl
    je 2f
    xor r9d, r9d
    xchg dword ptr [rdx + 0x2840], r9d
    lock or dword ptr [rdx + 0x77e4], 2
2:
    add rdx, {PA_STRIDE}
    dec r8d
    jnz 1b
    ret
""", "netanimclear")
    S.hook_entry(0x180029A30, "S8_netanimclear", "NetAnimClear: 8 slots")
    S.patch(0x180028CE7, "49 81 fe a0 df 01 00", "49 81 fe 40 bf 03 00", "anim offset loop: 4 -> 8 slots (end 8*0x77E8)")
    for va, old in ((0x18002668F, 3), (0x180026A92, 3), (0x180027810, 3), (0x1800292E7, 3), (0x1800293B5, 3), (0x1800297B7, 3),
                    (0x180029960, 3), (0x1800299A0, 3), (0x1800299D0, 3), (0x180027D07, 3), (0x180027D14, 3)):
        S.patch_imm(va, old, 7, "anim slot bound 3 -> 7", mnem="cmp")

    # ================================================================================== small per-slot arrays (4 -> 8)
    arrays = (("sa_last", 0x18013B120, 16, 4), ("sa_alive", 0x18013B1E0, 16, 4),
              ("d_pending", 0x1801628DC, 4, 1), ("d_age", 0x1801628E0, 16, 4), ("d_anim", 0x1801628F0, 4, 1))
    for name, old, size, elem in arrays:
        new = S.data(name, N * elem)
        S.relocate_table(name, old, size, new)
    S.asm("""
# FUN_1800380A0 (replication ResetRuntime): clear the three death-state arrays (bool[8], dword[8], bool[8])
S8_death_clear:
    mov qword ptr [rip + D_d_pending], 0
    mov qword ptr [rip + D_d_anim], 0
    xorps xmm0, xmm0
    movaps xmmword ptr [rip + D_d_age], xmm0
    movaps xmmword ptr [rip + D_d_age + 16], xmm0
    jmp V_1800380c3
""", "death_clear")
    S.hook(0x1800380A5, 0x1800380C3 - 0x1800380A5, "S8_death_clear", "ResetRuntime: clear death arrays for 8 slots")

    # ================================================================================== slotState (moves) / stats (grows in place)
    ss = S.data("slotstate", N * 12)
    delta = ss - CTX - SS_OLD                       # new disp32 = old disp32 + delta
    for va, old, note in (
            (0x18001CF49, 0x2BC8, "slotState.dead"), (0x18001D23A, 0x2BC8, "slotState.dead"), (0x18002CD82, 0x2BC8, "slotState.dead"),
            (0x18003350B, 0x2BD0, "slotState.grantCooldown"), (0x180033525, 0x2BC8, "slotState.dead"),
            (0x180033664, 0x2BD0, "slotState.grantCooldown"), (0x1800336A7, 0x2BD0, "slotState.grantCooldown"),
            (0x18003596D, 0x2BC8, "slotState.dead"), (0x180037573, 0x2BC8, "slotState.dead"), (0x180037583, 0x2BC8, "slotState.dead"),
            (0x18003770C, 0x2BCC, "slotState.respawnGrace"), (0x18003778A, 0x2BCC, "slotState.respawnGrace"),
            (0x180037DDE, 0x2BC8, "slotState.dead"), (0x18003892C, 0x2BCC, "slotState.respawnGrace"),
            (0x1800389B9, 0x2BCC, "slotState.respawnGrace"),
            # TickMatchAuthority: respawnGrace -= dt for slots 0..2 (slot 3 is the chain below)
            (0x180034091, 0x2BCC, "grace tick s0"), (0x1800340A9, 0x2BCC, "grace tick s0"), (0x1800340B1, 0x2BD8, "grace tick s1"),
            (0x1800340C6, 0x2BD8, "grace tick s1"), (0x1800340CE, 0x2BE4, "grace tick s2"), (0x1800340E3, 0x2BE4, "grace tick s2"),
            # grantCooldown -= dt for slots 0..2
            (0x180034D18, 0x2BD0, "cooldown tick s0"), (0x180034D2C, 0x2BD0, "cooldown tick s0"), (0x180034D34, 0x2BDC, "cooldown tick s1"),
            (0x180034D45, 0x2BDC, "cooldown tick s1"), (0x180034D4D, 0x2BE8, "cooldown tick s2"), (0x180034D5E, 0x2BE8, "cooldown tick s2"),
            # ResetRuntime: slots 0..3 (explicit stores)
            (0x180038187, 0x2BCC, "reset grace s0"), (0x180038191, 0x2BD8, "reset grace s1"), (0x18003819B, 0x2BE4, "reset grace s2"),
            (0x1800381A5, 0x2BF0, "reset grace s3"), (0x1800381C5, 0x2BD0, "reset cooldown s0"), (0x1800381CF, 0x2BDC, "reset cooldown s1"),
            (0x1800381D9, 0x2BE8, "reset cooldown s2"), (0x1800381E3, 0x2BF4, "reset cooldown s3"),
            (0x1800381F2, 0x2BC8, "reset dead s0"), (0x1800381F9, 0x2BD4, "reset dead s1"), (0x180038200, 0x2BE0, "reset dead s2"),
            (0x180038207, 0x2BEC, "reset dead s3")):
        S.patch_disp(va, old, old + delta, f"slotState moved to .t2r8 ({note})")
    S.patch(0x18001C706, "bf c8 2b 00 00", b"\xbf" + struct.pack("<I", ss - CTX), "slotState base offset (dead flags) -> .t2r8")
    # grace / cooldown tick for slots 3..7 (copy of the slot-3 block; disp32 re-based and advanced by 12 per slot)
    S.copy_chain("grace_tick", hook=(0x1800340EB, 0x180034108), tmpl=(0x1800340EB, 0x180034108), win_lo=0, stride=12, new_lo=0,
                 tmpl_entry=3, first=3, rec_disp=(0x2BEC, 0x2BF8), rec_delta=delta, fall="next", end=0x180034108,
                 note="TickMatchAuthority: respawnGrace tick slots 3..7")
    S.copy_chain("cooldown_tick", hook=(0x180034D66, 0x180034D7F), tmpl=(0x180034D66, 0x180034D7F), win_lo=0, stride=12, new_lo=0,
                 tmpl_entry=3, first=3, rec_disp=(0x2BEC, 0x2BF8), rec_delta=delta, fall="next", end=0x180034D7F,
                 note="Update: grantCooldown tick slots 3..7")
    S.asm("""
# ResetRuntime: slotState of slots 4..7 (0..3 were re-based above); then the displaced `mov dword [rsi+0x2c18], -1`
S8_ss_reset:
    mov qword ptr [rip + D_slotstate + 48], 0
    mov qword ptr [rip + D_slotstate + 56], 0
    mov qword ptr [rip + D_slotstate + 64], 0
    mov qword ptr [rip + D_slotstate + 72], 0
    mov qword ptr [rip + D_slotstate + 80], 0
    mov qword ptr [rip + D_slotstate + 88], 0
    mov dword ptr [rsi + 0x2c18], 0xffffffff
    jmp V_180038218

# FUN_180061EA0: new match -> stats of all 8 rows (ctx+0x2B98 .. +0x2BF8) cleared
S8_stats_reset:
    movups xmmword ptr [rax + 0x2b98], xmm0
    movups xmmword ptr [rax + 0x2ba8], xmm0
    movups xmmword ptr [rax + 0x2bb8], xmm0
    movups xmmword ptr [rax + 0x2bc8], xmm0
    movups xmmword ptr [rax + 0x2bd8], xmm0
    movups xmmword ptr [rax + 0x2be8], xmm0
    jmp V_180061f1b
""", "ss_reset")
    S.hook(0x18003820E, 10, "S8_ss_reset", "ResetRuntime: clear slotState 4..7")
    S.hook(0x180061F06, 0x180061F1B - 0x180061F06, "S8_stats_reset", "new match: clear stats rows 0..7")

    # ================================================================================== unrolled per-slot resets through BySlot
    # (xor ecx,ecx / mov ecx,k ; call BySlot ; store) x 4: the slot-3 block is copied for 4..7
    for nm, lo, hi, imms, note in (
            ("reset_a", 0x18001D0ED, 0x18001D112, (0x18001D0ED, 0x18001D0FE), "melee grace flags reset: slots 3..7"),
            ("reset_b", 0x18001D1AD, 0x18001D1D2, (0x18001D1AD, 0x18001D1BE), "melee grace flags reset (variant): slots 3..7"),
            ("reset_c", 0x1800618B9, 0x1800618CD, (0x1800618B9,), "radar blip alpha reset: slots 3..7")):
        S.copy_chain(nm, hook=(lo, hi), tmpl=(lo, hi), win_lo=0, stride=1, new_lo=0, tmpl_entry=3, first=3, fall="next",
                     slot_imm=imms, note=note)

    # ================================================================================== slot guards (3 -> 7, 4 -> 8)
    for va, old, new, note in GUARDS:
        S.patch_imm(va, old, new, note)


GUARDS = [
    # stats readers / writers (rows 0..7 now live at ctx+0x2B98 + slot*12)
    (0x180018E9D, 3, 7, "score: own stats slot"), (0x180018EE4, 3, 7, "score: own stats slot"),
    (0x180018F8A, 3, 7, "score: own stats slot"), (0x180019253, 3, 7, "score: own stats slot"),
    (0x180033B9E, 3, 7, "AddParts: slot"), (0x180061DD9, 3, 7, "kills++ slot"), (0x180061E7B, 3, 7, "deaths++ slot"),
    (0x180067A69, 3, 7, "scoreboard sort: stats row"), (0x180067AA3, 3, 7, "scoreboard sort: stats row"),
    (0x180067B8C, 3, 7, "scoreboard row: stats row"),
    # accessor / slotState users
    (0x180019A68, 3, 7, "mark/outline owner slot"), (0x180019B7A, 3, 7, "mark/outline owner slot"),
    (0x18001D034, 3, 7, "player grace flag slot"), (0x18001CF05, 4, 8, "revive/heal slot"), (0x18001C74E, 4, 8, "grace loop end"),
    (0x18002CD33, 3, 7, "heal slot"), (0x1800334EF, 3, 7, "HostGrantRespawn slot"), (0x180034EFC, 3, 7, "spectate target slot"),
    (0x180036807, 3, 7, "HandleNetEvent sender slot"), (0x180037556, 3, 7, "kill handler: victim slot"),
    (0x1800376D8, 3, 7, "kill handler: own slot"), (0x180037759, 3, 7, "kill handler: victim slot"),
    (0x1800379D3, 3, 7, "kill handler: victim slot"), (0x1800379EE, 4, 8, "kill handler: killer slot"),
    (0x180038357, 4, 8, "nearest enemy: slot"), (0x18003890E, 4, 8, "netslot < N"), (0x180038978, 4, 8, "netslot < N"),
    (0x180038990, 4, 8, "netslot < N"), (0x180038FD6, 3, 7, "slot bound"), (0x1800390E4, 3, 7, "slot bound"),
    (0x18004B81D, 3, 7, "play sound at slot"), (0x18004B93C, 3, 7, "play sound at slot"),
    (0x18004BA95, 3, 7, "vox: slot"), (0x18004BDA8, 3, 7, "vox: slot"), (0x18004BCAE, 2, 6, "vox: scan slots 0..7 (4 candidates max)"),
    (0x18006158E, 4, 8, "radar: players loop"), (0x18001A098, 3, 7, "finisher: target slot"),
]
