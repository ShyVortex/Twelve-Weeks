"""Session layer (net::session compiled in winmm): the peer table g_peers[4] (0x180167CC0, stride 0x40A0, HM_ROLE follows at
0x180177F40) becomes an 8-entry table in .t2r8.

  * every rip-relative reference to the old table is retargeted (relocate_table); the new table is contiguous so the pointer loops
    (`add rdi, 0x40A0` ...) just need their end changed;
  * the pump FUN_18005B5B0, LeaveInternal FUN_18005A4D0, BroadcastRoster FUN_18005DB30, IsConnected FUN_18005DA70 and the ctor
    FUN_18005F350 unroll their loops over the 4 peers: the last (or a non-destructive) block is copied for peers 4..7
    (copy_chain) or the sequence is regenerated for 8 (asm);
  * the roster on the wire is N entries (2 + N * 67: 538 = 0x21A bytes for N = 8, 605 = 0x25D for N = 9, instead of 0x10E) and the protocol
    version is bumped (0x29 -> 0x2A for N = 8, 0x2A + (N - 8) in general: slots8.proto_version) so a build with another slot count never
    parses the roster.
"""
import struct

PEER_STRIDE = 0x40A0
OLD_PEERS = 0x180167CC0
HM_ROLE = 0x180177F40
MY_SLOT = 0x180138090
ROSTER_OLD = 0x10E


def build(S):
    from slots8 import decode, rip_target, bump, proto_version
    N = S.N
    ROSTER_NEW = 2 + N * 67          # 0x21A for N = 8
    peers = S.data("peers", N * PEER_STRIDE)
    S.relocate_table("peers", OLD_PEERS, 4 * PEER_STRIDE, peers)
    P3 = OLD_PEERS + 3 * PEER_STRIDE
    P2 = OLD_PEERS + 2 * PEER_STRIDE

    def peer(j, off=0):
        return f"[rip + D_peers + {j * PEER_STRIDE + off}]"

    # ---- unrolled chains: copy the last block for peers 4..7 --------------------------------------------------------------
    def chain(name, lo, hi, **kw):
        S.copy_chain(name, hook=(lo, hi), tmpl=(lo, hi), win_lo=P3, stride=PEER_STRIDE, new_lo=peers, tmpl_entry=3,
                     first=3, **kw)

    # LeaveInternal: Goodbye to every active peer
    chain("leave_goodbye", 0x18005A5A9, 0x18005A5D3, fall="next", note="LeaveInternal: Goodbye to peers 3..7")
    # PeerForAddr chains (find the peer a datagram came from): "not this peer" edge -> next copy, found -> fall through
    chain("find_hello", 0x18005B7C4, 0x18005B7F3, next_targets=(0x18005C02D,), fall="end",
          note="pump Hello: PeerForAddr peers 3..7")
    chain("find_state", 0x18005B916, 0x18005B94C, next_targets=(0x18005B680,), fall="end",
          note="pump State/Anim (host): PeerForAddr peers 3..7")
    chain("find_bye", 0x18005BB66, 0x18005BB95, next_targets=(0x18005B680,), fall="end",
          note="pump Goodbye (host): PeerForAddr peers 3..7")
    chain("find_anim", 0x18005BC41, 0x18005BC76, next_targets=(0x18005B680,), fall="end",
          note="pump AnimCmd (host): PeerForAddr peers 3..7")
    # Update(): drop silent peers. The last original block reuses xmm9 destructively: copy the non-destructive block 2 instead.
    S.copy_chain("timeout", hook=(0x18005CF06, 0x18005CF39), tmpl=(0x18005CEDE, 0x18005CF06), win_lo=P2, stride=PEER_STRIDE,
                 new_lo=peers, tmpl_entry=2, first=3, next_targets=(0x18005CF06,), last_exit=0x18005CFCE, fall="next",
                 end=0x18005CFCE, slot_imm=(0x18005CEFC,), note="Update: peer timeout peers 3..7")

    # ---- regenerated sequences ----------------------------------------------------------------------------------------
    x = rip_target(decode(S.img, 0x18005BF95, 0x18005BF9C)[0])           # the received AnimCmd body (global buffer)
    for a in (0x18005BFCC, 0x18005C00B):
        assert rip_target(decode(S.img, a, a + 7)[0]) == x
    # Planned handover slot 0 -> 3 (match ba0d5577): a host whose own slot is not 0 has the OLD host as an ordinary client in
    # peer[0] (hm_migrate). Every host-role walk below therefore includes peer 0 (range(0, N) / index start -1 / one extra block). On a slot-0
    # host peer[0] is never active (the Hello allocator starts at 1, hm_migrate clears it), and every walk tests `active` before it touches
    # the peer, so nothing changes there. On a CLIENT peer[0] is the host link: all of these are role==1 paths (checked per site in the notes).
    anim = ["S8_anim_fwd:", "    mov r9d, r14d"]
    for j in range(0, N):
        anim += [f"    cmp dil, {j}", f"    je S8_af_{j + 1}", f"    cmp byte ptr {peer(j)}, 0", f"    je S8_af_{j + 1}",
                 "    mov qword ptr [rsp + 0x28], r15", f"    lea rax, [rip + V_{x:x}]", "    mov qword ptr [rsp + 0x20], rax",
                 f"    lea rcx, {peer(j)}", "    mov dl, 7", "    mov r8d, edi", "    mov r9d, r14d", "    call V_18005a9f0",
                 "    mov r9d, r14d", f"S8_af_{j + 1}:"]
    anim += ["    jmp V_18005b680"]
    S.hook(0x18005BF7E, 0x18005C02D - 0x18005BF7E, "S8_anim_fwd", "pump AnimCmd (host): forward to peers 0..7")

    alloc = ["S8_hello_alloc:", f"    cmp byte ptr {peer(3)}, 0", "    je V_18005c4dc"]
    for j in range(4, N):
        alloc += [f"    cmp byte ptr {peer(j)}, 0", f"    jne S8_ha_{j + 1}", f"    mov r12d, {j}", "    jmp V_18005c4e2", f"S8_ha_{j + 1}:"]
    alloc += ["    jmp V_18005c436"]
    S.hook(0x18005C429, 0x18005C436 - 0x18005C429, "S8_hello_alloc", "pump Hello: first free peer slot 1..7")

    others = ["S8_send_others:", f"    cmp byte ptr [rip + V_{HM_ROLE:x}], 1", "    jne V_18005d120"]
    for r in range(N):
        nx = f"S8_so_{r + 1}"
        others += [f"    mov eax, dword ptr [rip + V_{MY_SLOT:x}]", f"    cmp eax, {r}", f"    je {nx}", "    movzx ecx, byte ptr [rdi + 1]",
                   f"    cmp ecx, {r}", f"    je {nx}", f"    mov ecx, {r}", "    call V_180050fd0", "    cmp byte ptr [rax + 4], 0", f"    je {nx}",
                   "    cmp byte ptr [rax + 0x9c6], 0", f"    je {nx}", "    mov rcx, rax", "    add rcx, 0x68", "    mov word ptr [rax + 0x115], 0",
                   "    mov r9d, dword ptr [rax + 0x9c8]", "    mov qword ptr [rsp + 0x20], rcx", "    mov qword ptr [rsp + 0x28], 0xaf",
                   "    mov rcx, rdi", "    mov dl, 5", f"    mov r8d, {r}", "    call V_18005a9f0", f"{nx}:"]
    others += ["    jmp V_18005d120"]
    S.hook(0x18005D20C, 0x18005D3B3 - 0x18005D20C, "S8_send_others", "SendPhase (host): relay every other player's state to each peer")

    anyact = ["S8_anyact_cl:", f"    movzx ecx, byte ptr {peer(0)}"]
    anyact += [f"    or cl, byte ptr {peer(j)}" for j in range(1, N)] + ["    setne cl", "    jmp V_18005d08e"]
    S.hook(0x18005D078, 0x18005D08E - 0x18005D078, "S8_anyact_cl", "SendPhase (host): any peer 0..7 active")

    isconn = ["S8_isconn:", f"    movzx eax, byte ptr {peer(0)}"]
    isconn += [f"    or al, byte ptr {peer(j)}" for j in range(1, N)] + ["    setne al", "    and al, 1", "    ret"]
    S.hook(0x18005DA81, 0x18005DA9A - 0x18005DA81, "S8_isconn", "IsConnected (host): any peer 0..7 active")

    # frame: the roster buffer sits at rsp+0x40; 0x270 holds the 8-entry roster (0x40 + 0x21A), a longer one (N = 9: 0x25D) needs a bigger frame
    frame = max(0x270, (0x40 + ROSTER_NEW + 15) & ~15)
    bcast = ["S8_bcastroster:", "    push rsi", "    push rdi", "    push rbx", f"    sub rsp, {frame:#x}",
             f"    cmp byte ptr [rip + V_{HM_ROLE:x}], 1", "    jne S8_br_end"]
    for j in range(0, N):
        nx = f"S8_br_{j + 1}"
        bcast += [f"    cmp byte ptr {peer(j)}, 0", f"    je {nx}", f"    lea rsi, {peer(j)}", "    movzx edx, byte ptr [rsi + 1]",
                  "    lea rdi, [rsp + 0x40]", "    mov rcx, rdi", "    call V_18005e5f0", f"    movzx r8d, byte ptr [rip + V_{MY_SLOT:x}]",
                  "    mov qword ptr [rsp + 0x20], rdi", f"    mov qword ptr [rsp + 0x28], {ROSTER_NEW:#x}", "    mov rcx, rsi", "    mov dl, 4",
                  "    xor r9d, r9d", "    call V_18005a9f0", f"{nx}:"]
    bcast += ["S8_br_end:", f"    add rsp, {frame:#x}", "    pop rbx", "    pop rdi", "    pop rsi", "    ret"]
    S.hook_entry(0x18005DB30, "S8_bcastroster", "BroadcastRoster: peers 0..7, 8-entry roster", minbytes=9)

    build_roster = f"""
S8_buildroster:
    push rsi
    push rdi
    push rbx
    push r12
    push r13
    sub rsp, 0x20
    mov ebx, edx
    mov rsi, rcx
    add rcx, 2
    mov r8d, {N * 67:#x}
    xor edx, edx
    call V_18009e290
    mov byte ptr [rsi], bl
    mov byte ptr [rsi + 1], {N}
    xor edi, edi
1:
    mov ecx, edi
    call V_180050fd0
    mov r12, rax
    mov eax, edi
    imul eax, eax, 67
    lea r13, [rsi + rax + 2]
    mov byte ptr [r13], dil
    movzx eax, byte ptr [r12 + 4]
    mov byte ptr [r13 + 1], al
    mov ecx, edi
    call V_180058a00
    mov ecx, 0xffffffff
    test eax, eax
    cmovs eax, ecx
    mov byte ptr [r13 + 2], al
    lea r8, [r12 + 6]
    lea rcx, [r13 + 3]
    mov edx, 0x18
    mov r9, -1
    call V_18007f7b4
    lea r8, [r12 + 0x1e]
    lea rcx, [r13 + 0x1b]
    mov edx, 0x28
    mov r9, -1
    call V_18007f7b4
    inc edi
    cmp edi, {N}
    jb 1b
    add rsp, 0x20
    pop r13
    pop r12
    pop rbx
    pop rdi
    pop rsi
    ret
"""
    S.hook_entry(0x18005E5F0, "S8_buildroster", "BuildRoster: 8 entries (0x21A bytes)", minbytes=5)

    helpers = f"""
# NetPeer reset for the new entries (g_peers[s] = NetPeer{{}}; chan.Reset())
S8_peer_reset:
    push rbx
    sub rsp, 0x20
    mov rbx, rcx
    mov word ptr [rbx], 0xff00
    xorps xmm0, xmm0
    movups xmmword ptr [rbx + 4], xmm0
    mov qword ptr [rbx + 0x14], 0
    lea rcx, [rbx + 0x20]
    call V_18005ace0
    add rsp, 0x20
    pop rbx
    ret

# static constructor of g_peers for entries 4..7 (FUN_18005F350 does 0..3): slot = 0xFF, NetEventChannel's unordered_map built by
# FUN_18005DFB0, "ready" counter = 1
S8_init_hi_peers:
    push rbx
    push rsi
    sub rsp, 0x38
    lea rbx, [rip + D_peers + {4 * PEER_STRIDE}]
    mov esi, 4
1:
    mov byte ptr [rbx + 1], 0xff
    lea rcx, [rbx + 0x4058]
    mov dword ptr [rsp + 0x20], 0
    lea rdx, [rsp + 0x20]
    lea r8, [rsp + 0x27]
    call V_18005dfb0
    mov dword ptr [rbx + 0x4098], 1
    add rbx, {PEER_STRIDE}
    inc esi
    cmp esi, {N}
    jb 1b
    add rsp, 0x38
    pop rsi
    pop rbx
    ret

S8_ctor_tail:
    call S8_init_hi_peers
    lea rcx, [rip + V_18005a3b0]
    jmp V_18005f51b

# LeaveInternal: reset peers 4..7, then the displaced `mov byte [HM_ROLE], 0`
S8_leave_reset:
""" + "".join(f"    lea rcx, {peer(j)}\n    call S8_peer_reset\n" for j in range(4, N)) + f"""    mov byte ptr [rip + V_{HM_ROLE:x}], 0
    jmp V_18005a80d
"""
    # ---- peer 0 as an ordinary client of a host with slot != 0 -------------------------------------------------------
    # The two pointer loops index peer i by `[rbx + r8 + 0x40A0]` / `[rdi + r13 + 0x40A0]` with the index register starting at 0, i.e. they
    # begin at peer 1. Starting it at -0x40A0 makes the first pass peer 0 (the `active` test at the loop top skips it when idle) and the
    # `add reg, 0x40A0` then walks 1..7 as before; the end compare (patched to 7 * 0x40A0 below) is untouched. Only the entry code is
    # hooked: the original `movzx/mov` (event forward) / `add r14` (event route) before it is re-emitted verbatim.
    peer0 = f"""
# FUN_18005C0xx event forward (role==1 only: gate at 0x18005C25E): displaced 0x18005C27D..0x18005C28B, index start -0x40A0
S8_evf_entry:
    movzx eax, cl
    mov qword ptr [rbp + 0x4058], rax
    mov rbx, -0x40a0
    jmp V_18005c2c4

# event route (reached only with role == 1: 0x18005CC2B..0x18005CC38 sends role 0 / 2 elsewhere): displaced 0x18005CD43..0x18005CD4B
S8_evr_entry:
    add r14, 0x10
    mov rdi, -0x40a0
    jmp V_18005cd74

# Update(): host-role receive timeout, peer 0 first (the unrolled peer 1/2/3 blocks follow). Role gate: 0x18005CEAD..0x18005CEB0.
S8_to0:
    cmp byte ptr {peer(0)}, 0
    je 1f
    movaps xmm0, xmm9
    subss xmm0, dword ptr {peer(0, 0x14)}
    ucomiss xmm0, dword ptr [rip + V_1800a0d4c]
    jbe 1f
    xor ecx, ecx
    call V_18005d900
1:
    cmp byte ptr {peer(1)}, 0
    je V_18005cede
    jmp V_18005cebf
"""
    S.asm("\n".join(anim) + "\n" + "\n".join(alloc) + "\n" + "\n".join(others) + "\n" + "\n".join(anyact) + "\n" +
          "\n".join(isconn) + "\n" + "\n".join(bcast) + "\n" + build_roster + helpers + peer0, "peers")
    S.hook(0x18005C27D, 0x18005C28B - 0x18005C27D, "S8_evf_entry", "event forward loop: start at peer 0 (host with slot != 0)")
    S.hook(0x18005CD43, 0x18005CD4B - 0x18005CD43, "S8_evr_entry", "event route loop: start at peer 0 (host with slot != 0)")
    S.hook(0x18005CEB6, 0x18005CEBF - 0x18005CEB6, "S8_to0", "Update: receive timeout also for peer 0 (host with slot != 0)")
    S.hook(0x18005F514, 7, "S8_ctor_tail", "g_peers ctor: construct entries 4..7")
    S.hook(0x18005A806, 7, "S8_leave_reset", "LeaveInternal: reset peers 4..7")

    # ---- bounds ----------------------------------------------------------------------------------------------------------
    b3 = bump(N, 3)
    end = struct.pack("<I", (N - 1) * PEER_STRIDE)
    S.patch(0x18005C06D, "3c 03", bytes([0x3c, b3]), f"pump Hello (relay): slot bound 3 -> {b3}")
    S.patch(0x18005BCFB, "40 80 ff 03", bytes([0x40, 0x80, 0xff, b3]), f"pump State (client): sender slot bound 3 -> {b3}")
    S.patch(0x18005BEE5, "40 80 ff 03", bytes([0x40, 0x80, 0xff, b3]), f"pump AnimCmd: sender slot bound 3 -> {b3}")
    S.patch(0x18005C2B7, "48 81 fb e0 c1 00 00", bytes([0x48, 0x81, 0xfb]) + end, f"event forward loop: peers 1..3 -> 1..{b3} (end {N - 1}*0x40A0)")
    S.patch(0x18005CD67, "48 81 ff e0 c1 00 00", bytes([0x48, 0x81, 0xff]) + end, f"event route loop: peers 1..3 -> 1..{b3} (end {N - 1}*0x40A0)")
    S.patch(0x18005D0F9, "41 bc 04 00 00 00", bytes([0x41, 0xbc, N, 0, 0, 0]), f"SendPhase: 4 -> {N} peers")
    S.patch(0x18005D928, "8d 46 fc", bytes([0x8d, 0x46, (-N) & 0xff]), f"DropPeer: slot window 1..3 -> 1..{b3}")      # lea eax,[rsi - N]
    S.patch(0x18005D92B, "83 f8 fd", bytes([0x83, 0xf8, (-N) & 0xff]),                                                 # cmp eax, -N
            f"DropPeer: slot window 1..3 -> 0..{b3} (peer 0 = old host after a handover; only host-role callers)")
    # roster payload 0x10E -> 0x21A
    n = ROSTER_NEW.to_bytes(4, "little").hex(" ")
    o = ROSTER_OLD.to_bytes(4, "little").hex(" ")
    for va in (0x18005B82B, 0x18005C90D, 0x18005D1F6):
        S.patch(va, "48 c7 44 24 28 " + o, "48 c7 44 24 28 " + n, "roster send length 0x10E -> 0x21A")
    for va in (0x18005B9AB, 0x18005BA09):
        S.patch(va, "49 81 ff " + o, "49 81 ff " + n, "roster receive minimum length 0x10E -> 0x21A")
    for va in (0x18005B9C5, 0x18005BA23):
        S.patch(va, "41 b8 " + o, "41 b8 " + n, "roster receive copy length 0x10E -> 0x21A")
    # protocol version 0x29 -> 0x2A for N = 8, 0x2A + (N - 8) otherwise (a build with another slot count must not parse the roster)
    pv = proto_version(N)
    S.patch(0x18005AAE5, "66 c7 05 e6 bc 12 00 29 00", bytes.fromhex("66 c7 05 e6 bc 12 00") + bytes([pv, 0]), f"protocol version in SendRaw 41 -> {pv}")
    S.patch(0x18005C02D, "66 41 83 fe 29", bytes.fromhex("66 41 83 fe") + bytes([pv]), f"protocol version check in Hello 41 -> {pv}")
