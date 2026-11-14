"""8 net players (NetPlayers records): ctx+0x1C0 + slot*0xA70 (4 records, the match state follows at ctx+0x2B80) -> 8 records in
.t2r8 (D_players, contiguous, same stride and layout).

Everything that touches a record goes through FUN_180050FD0 (BySlot) except ~11 small functions in 0x18004BF80-0x180051CBB that
address the records relative to the match context (call 0x18004BF70 returns the context; [rax+0x1C4] = record 0 active ...).
Those are handled three ways:
  * loops (Reset / SetupLocal / ApplyRoster / OnPeerDropped / Advance): the `call 0x18004BF70` that only feeds the record
    accesses is retargeted to S8_plbase, which returns D_players - 0x1C0 (a "context" whose +0x1C0 is the new table), and the
    4-entry bounds become 8;
  * unrolled functions (Local / FromEnginePtr / ActiveCount / CountActivePerTeam), the BySlot accessor and TeamOf:
    rewritten in the cave as loops over 8 records;
  * the context's own fields (EnsureInit flag at +0x2CC0, match state at +0x2B80 ...) keep using the real context.
The old records (ctx+0x1C0..0x2B80) are left unused. netSlot of record j (dword at +0) is baked into the section (EnsureInit's
own init of the 4 old records is harmless).
"""
import struct

PL_STRIDE = 0xA70
N = 8
CTX = 0x180135388


def build(S):
    pl = S.data("players", N * PL_STRIDE, init=b"".join(struct.pack("<I", j).ljust(PL_STRIDE, b"\0") for j in range(N)))
    S.relocs_note = getattr(S, "relocs_note", [])
    init_slots = "\n".join(f"    mov dword ptr [rip + D_players + {j * PL_STRIDE}], {j}" for j in range(N))

    S.asm(f"""
S8_plbase:
    lea rax, [rip + D_players - 0x1c0]
    ret

# FUN_18004C030: TeamOf(ctx rcx, slot edx) -> team (the player record's +0x48, else the matchmaker roster team)
S8_teamof:
    cmp edx, 7
    ja 2f
    cmp byte ptr [rcx + 0x2cc0], 0
    jne 1f
{init_slots}
    mov byte ptr [rcx + 0x2cc0], 1
1:
    mov eax, edx
    imul rax, rax, {PL_STRIDE}
    lea rcx, [rip + D_players]
    mov eax, dword ptr [rcx + rax + 0x48]
    test eax, eax
    js 2f
    ret
2:
    mov ecx, edx
    jmp V_180058a00

# FUN_180050FD0: BySlot(slot) -> record (slot clamped to 0..7)
S8_byslot:
    push rsi
    sub rsp, 0x20
    mov esi, ecx
    call V_18004bf70
    mov rcx, rax
    call V_18004bf80
    xor eax, eax
    test esi, esi
    cmovg eax, esi
    mov esi, 7
    cmp eax, 7
    cmovb esi, eax
    imul rcx, rsi, {PL_STRIDE}
    lea rax, [rip + D_players]
    add rax, rcx
    add rsp, 0x20
    pop rsi
    ret

# FUN_180051060: Local() -> first record with active && isLocal, else 0
S8_local:
    push rsi
    sub rsp, 0x20
    call V_18004bf70
    mov rcx, rax
    call V_18004bf80
    lea rsi, [rip + D_players]
    xor ecx, ecx
1:
    cmp byte ptr [rsi + 4], 0
    je 2f
    cmp byte ptr [rsi + 5], 0
    jne 3f
2:
    add rsi, {PL_STRIDE}
    inc ecx
    cmp ecx, {N}
    jb 1b
    xor eax, eax
    jmp 4f
3:
    mov rax, rsi
4:
    add rsp, 0x20
    pop rsi
    ret

# FUN_180051120: FromEnginePtr(ptr rcx) -> record whose engine object is ptr, else 0
S8_fromptr:
    push rsi
    push rdi
    push rbx
    push r12
    sub rsp, 0x28
    test rcx, rcx
    je 8f
    mov rdi, rcx
    movabs rbx, 0x4580fab03b7eb9c0
    call V_18004bf70
    mov rcx, rax
    call V_18004bf80
    lea rsi, [rip + D_players]
    xor r12d, r12d
1:
    cmp byte ptr [rsi + 4], 0
    je 5f
    mov rcx, rbx
    cmp byte ptr [rsi + 5], 0
    jne 3f
    xor eax, eax
    cmp byte ptr [rsi + 0x4c], 0
    je 4f
    mov rcx, qword ptr [rsi + 0x60]
    test rcx, rcx
    je 4f
3:
    call V_18000a200
4:
    cmp rax, rdi
    je 7f
5:
    add rsi, {PL_STRIDE}
    inc r12d
    cmp r12d, {N}
    jb 1b
8:
    xor eax, eax
    jmp 9f
7:
    mov rax, rsi
9:
    add rsp, 0x28
    pop r12
    pop rbx
    pop rdi
    pop rsi
    ret

# FUN_1800512A0: ActiveCount()
S8_activecount:
    push rsi
    sub rsp, 0x30
    call V_18004bf70
    mov rcx, rax
    call V_18004bf80
    lea rcx, [rip + D_players + 4]
    xor eax, eax
    mov edx, {N}
1:
    movzx esi, byte ptr [rcx]
    add eax, esi
    add rcx, {PL_STRIDE}
    dec edx
    jnz 1b
    add rsp, 0x30
    pop rsi
    ret

# FUN_1800512F0: CountActivePerTeam(int* team0 rcx, int* team1 rdx)
S8_countteam:
    push rsi
    push rdi
    push rbx
    push r12
    sub rsp, 0x28
    mov rsi, rcx
    mov rdi, rdx
    call V_18004bf70
    mov rcx, rax
    call V_18004bf80
    mov dword ptr [rsi], 0
    mov dword ptr [rdi], 0
    lea rbx, [rip + D_players]
    xor r12d, r12d
1:
    cmp byte ptr [rbx + 4], 0
    je 4f
    call V_18004bf70
    mov rcx, rax
    mov edx, dword ptr [rbx]
    call V_18004c030
    test eax, eax
    je 2f
    cmp eax, 1
    jne 4f
    inc dword ptr [rdi]
    jmp 4f
2:
    inc dword ptr [rsi]
4:
    add rbx, {PL_STRIDE}
    inc r12d
    cmp r12d, {N}
    jb 1b
    add rsp, 0x28
    pop r12
    pop rbx
    pop rdi
    pop rsi
    ret
""", "players")

    # --- rewritten functions: jump into the cave at their entry -------------------------------------------------------
    for va, lbl, note in ((0x18004C030, "S8_teamof", "TeamOf(ctx, slot)"),
                          (0x180050FD0, "S8_byslot", "BySlot accessor (clamp 7, 8 records)"),
                          (0x180051060, "S8_local", "NetPlayers::Local"),
                          (0x180051120, "S8_fromptr", "NetPlayers::FromEnginePtr"),
                          (0x1800512A0, "S8_activecount", "NetPlayers::ActiveCount"),
                          (0x1800512F0, "S8_countteam", "NetPlayers::CountActivePerTeam")):
        S.hook_entry(va, lbl, note)

    # --- loops: record accesses relative to the pseudo context ---------------------------------------------------------
    S.retarget_calls([0x1800515BF], 0x18004BF70, "S8_plbase", "NetPlayers::Reset loop context")
    S.retarget_calls([0x18005166F], 0x18004BF70, "S8_plbase", "NetPlayers::SetupLocal context")
    S.retarget_calls([0x18005179B], 0x18004BF70, "S8_plbase", "NetPlayers::ApplyRoster context")
    S.retarget_calls([0x180051BA6], 0x18004BF70, "S8_plbase", "NetPlayers::OnPeerDropped context")
    S.retarget_calls([0x18005144E], 0x18004BF70, "S8_plbase", "NetPlayers iterator Advance context")
    # --- bounds ---------------------------------------------------------------------------------------------------------
    S.patch(0x1800515B6, "48 81 ff aa 35 00 00", "48 81 ff 6a 5f 00 00", "Reset: loop end 4 -> 8 records (0xBEA + 8*0xA70)")
    S.patch(0x180051662, "83 f8 03", "83 f8 07", "SetupLocal: slot clamp 3 -> 7")
    S.patch(0x180051665, "41 be 03 00 00 00", "41 be 07 00 00 00", "SetupLocal: clamp value 3 -> 7")
    S.patch(0x180051784, "48 83 fe 03", "48 83 fe 07", "ApplyRoster: entry slot bound 3 -> 7")
    S.patch(0x180051890, "49 83 fd 02", "49 83 fd 06", "ApplyRoster: entry count 4 -> 8")
    S.patch(0x180051B9B, "83 f8 03", "83 f8 07", "OnPeerDropped: slot clamp 3 -> 7")
    S.patch(0x180051B9E, "bf 03 00 00 00", "bf 07 00 00 00", "OnPeerDropped: clamp value 3 -> 7")
    S.patch(0x180051419, "83 fb 03", "83 fb 07", "iterator Advance: already-at-end test 3 -> 7")
    S.patch(0x180051437, "83 f8 03", "83 f8 07", "iterator Advance: last entry 3 -> 7")
    S.patch(0x180051026, "83 f9 03", "83 f9 07", "SlotIsFriendly: slot bound 3 -> 7")
    # range-for sentinel (Remotes()/active loops): `call 0x180051410 ; mov ecx,[it] ; cmp ecx, 4` -> 8
    for va in ITER_END:
        S.patch(va, "83 f9 04", "83 f9 08", "iterator end sentinel 4 -> 8")


# `cmp ecx, 4` after NetPlayers' iterator Advance (FUN_180051410): the end() value
ITER_END = [0x18001AF12, 0x18001B000, 0x18001B4BE, 0x18001B5AD, 0x18001C5C6, 0x18001C5EB, 0x18001C688, 0x18001C6B4,
            0x18001C6F1, 0x18001C83E, 0x18002E00B, 0x18002E040, 0x18002EF04, 0x18002EF29, 0x18003018B, 0x18003022E,
            0x18003441C, 0x180034473, 0x180034FBB, 0x180034FE4, 0x180035315, 0x180035349, 0x18003542B, 0x18003567C,
            0x180036104, 0x18003622E, 0x18003765B, 0x180037880, 0x1800383B8, 0x1800383EE, 0x18004B894, 0x18004B8C0,
            0x1800679A2, 0x1800679D6]
