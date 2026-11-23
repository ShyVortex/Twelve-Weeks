// voxchar.c (included by t2r-ext.c after deathreact.c) - a player body whose head has no voice gets its faction's voice group.
//
// KELLIE voice ("kellie is a new face,
// so maybe she just doesnt have a voice assigned at all"). The 'vox req:' probe showed every KELLIE line refused with EXIT 6
// invalid_character_id: her body's VoxController +0x660 (the character id) is 0, while a stock-face body holds fnv64 "scar-female-a".."-d".
// Static decode (exe 1.6.10721):
//   - 0x336b20 VoxController::SetCharacter(ctl, group key, flag): 0x33b070 picks one entry at random among the vox2.bin character
//     records whose +0x18 is the group key (entries 0x68 bytes: +0 name, +8 sid "scar-female-a", +0x18 group "any-scar-female");
//     none -> +0x660 = 0 and +0x70 = 0. Called from the controller's init (0x32ca70, a vtable call; key = its 3rd argument).
//   - the group key comes from the body's HEAD part: vox2.bin holds a 542-entry list head part name -> group
//     ("scar-female-head-09" -> any-scar-female, "militia-female-head-13" -> any-militia-female). The stock looks carry no voice field.
//   - KELLIE's heads "t2r-kl-f-head-kellie01" / "t2r-kl-s-head-kellie01" are not in it, so her body never gets a character and the engine refuses all its lines,
//     on her own screen and on every other screen. When this was written both sides wore the same head (one data entry = one faction's
//     group); the ext sets the group from the body's side, which also covers every other head missing from the list (t2r-hh-* copies).
// Fix: a hook on 0x336b20 notes every controller left without a character; vch_tick (vx_tick, every frame) finds its owner (our own
// body = vdf_player(), a puppet = g_pa_chr[slot]) and calls the engine's own setter again with "any-<scar|militia>-<female|male>" of
// that body's faction and sex. The lines still play through `say` (native, subtitled); only the missing character is filled in.
// Controllers whose owner is not a player body (the CUSTOMIZE stage models) are dropped after 30 s.
//
// crash exe+336bbd (8 players, builds 195-198, re/reports-1122.md): `call [rax+0x178]` at the end of SetCharacter with the
// controller's vtable 0 or garbage = vch_tick called the setter on a pending controller that the engine had freed. The freed block still
// held +0x50/+0x58, and they resolved to a live process (a puppet re-instanced for a paired move / revive: KD85 crashed in the frame of
// visdiag's "process re-instanced"). The setter also writes +0x7c0 / +0x65c / +0x660 / +0x70 before that call, so a freed block that
// still had its old vtable was written to silently. Now an entry keeps the vtable it had in the hook (the object was live there) and
// the first owner it resolved to; the setter is called only while both are unchanged and the vtable lies in the exe image.
typedef uint64_t (*fn_vch_set)(void *, uint64_t, uint64_t);
static fn_vch_set g_vch_tramp;
static struct { void *ctl; uint64_t key, t; const void *vt; const uint8_t *own; } g_vch_pend[16];
static uint32_t g_vch_drops;
static int vch_vt_ok(const void *vt) {
    static const uint8_t *lo, *hi;
    if (!lo) {
        const uint8_t *b = (const uint8_t *)GetModuleHandleW(NULL);
        const IMAGE_NT_HEADERS *nt = (const IMAGE_NT_HEADERS *)(b + ((const IMAGE_DOS_HEADER *)b)->e_lfanew);
        hi = b + nt->OptionalHeader.SizeOfImage; lo = b + 0x1000;
    }
    return (const uint8_t *)vt >= lo && (const uint8_t *)vt + 0x180 <= hi;
}
// the controller is still the object the hook saw: readable, same vtable as then, vtable in the exe image
static int vch_alive(void *ctl, const void *vt) {
    if (!ctl || IsBadReadPtr(ctl, 8) || IsBadReadPtr((char *)ctl + 0x660, 8)) return 0;
    const void *now_vt = *(const void *const *)ctl;
    return vt && now_vt == vt && vch_vt_ok(now_vt);
}
static volatile LONG g_vch_lock;
static uint64_t vch_set_hook(void *ctl, uint64_t key, uint64_t flag) {
    uint64_t r = g_vch_tramp(ctl, key, flag);
    if (ctl && !IsBadReadPtr((char *)ctl + 0x660, 8) && !*(uint64_t *)((char *)ctl + 0x660)) {
        while (InterlockedExchange(&g_vch_lock, 1)) YieldProcessor();
        int free_i = -1;
        for (int i = 0; i < 16; i++) {
            if (g_vch_pend[i].ctl == ctl) { free_i = i; break; }
            if (!g_vch_pend[i].ctl && free_i < 0) free_i = i;
        }
        if (free_i >= 0) {
            const void *vt = *(const void *const *)ctl;
            if (vch_vt_ok(vt)) { g_vch_pend[free_i].ctl = NULL; g_vch_pend[free_i].key = key; g_vch_pend[free_i].t = GetTickCount64(); g_vch_pend[free_i].vt = vt; g_vch_pend[free_i].own = NULL; MemoryBarrier(); g_vch_pend[free_i].ctl = ctl; }
            else if (g_vch_pend[free_i].ctl == ctl) g_vch_pend[free_i].ctl = NULL;
        }
        InterlockedExchange(&g_vch_lock, 0);
    }
    return r;
}
static void vch_install(void) {
    static int tried;
    if (tried) return;
    tried = 1;
    // mov [rsp+10],rbx; mov [rsp+18],rsi; push rbp; push rdi; push r12; push r14; push r15 (18 bytes, position independent)
    static const uint8_t pro[18] = {0x48, 0x89, 0x5C, 0x24, 0x10, 0x48, 0x89, 0x74, 0x24, 0x18, 0x55, 0x57, 0x41, 0x54, 0x41, 0x56, 0x41, 0x57};
    uint8_t *fn = (uint8_t *)GetModuleHandleW(NULL) + 0x336b20;
    if (IsBadReadPtr(fn, sizeof pro) || memcmp(fn, pro, sizeof pro)) { hook_miss(fn, sizeof pro, "vox char: VoxController SetCharacter prologue differs, not hooked (a face without a voice stays silent)"); return; }
    uint8_t *t = VirtualAlloc(NULL, 64, MEM_COMMIT | MEM_RESERVE, PAGE_EXECUTE_READWRITE);
    if (!t) return;
    memcpy(t, fn, sizeof pro);
    t[18] = 0xFF; t[19] = 0x25; *(uint32_t *)(t + 20) = 0; *(uint64_t *)(t + 24) = (uint64_t)(fn + sizeof pro);
    g_vch_tramp = (fn_vch_set)t;
    DWORD old; VirtualProtect(fn, sizeof pro, PAGE_EXECUTE_READWRITE, &old);
    fn[0] = 0xFF; fn[1] = 0x25; *(uint32_t *)(fn + 2) = 0; *(uint64_t *)(fn + 6) = (uint64_t)vch_set_hook;
    for (int i = 14; i < (int)sizeof pro; i++) fn[i] = 0x90;
    VirtualProtect(fn, sizeof pro, old, &old);
    FlushInstructionCache(GetCurrentProcess(), fn, sizeof pro);
    xlog("vox char: SetCharacter hooked (a player body whose head has no voice gets its faction's group)");
}
// the controller's owner process (handle at +0x50 -> [+8], generation +0x58 = [process+0x94]: the check the engine's own gate makes)
static uint8_t *vch_owner(void *ctl) {
    if (IsBadReadPtr((char *)ctl + 0x50, 16)) return NULL;
    char *slot = *(char **)((char *)ctl + 0x50);
    uint32_t gen = *(uint32_t *)((char *)ctl + 0x58);
    if (!slot || IsBadReadPtr(slot, 16)) return NULL;
    uint8_t *o = *(uint8_t **)(slot + 8);
    if (!o || IsBadReadPtr(o + 0x94, 4) || *(uint32_t *)(o + 0x94) != gen) return NULL;
    return o;
}
static void vch_tick(void) {
    vch_install();
    if (!g_vch_tramp) return;
    uint64_t now = GetTickCount64();
    for (int i = 0; i < 16; i++) {
        void *ctl = g_vch_pend[i].ctl;
        if (!ctl) continue;
        int done = 0;
        uint8_t *o = vch_alive(ctl, g_vch_pend[i].vt) ? vch_owner(ctl) : NULL;
        if (o && !g_vch_pend[i].own) g_vch_pend[i].own = o;
        if (!vch_alive(ctl, g_vch_pend[i].vt) || (o && o != g_vch_pend[i].own)) {
            // freed / reused controller, or its handle now resolves to another process (re-instanced owner): never call the setter on it
            done = 1;
            if (g_vch_drops++ < 20) xlog("vox char: pending controller %p dropped (%s) - not set", ctl, !vch_alive(ctl, g_vch_pend[i].vt) ? "vtable changed: freed" : "owner changed: re-instanced");
        }
        else if (!o) done = now - g_vch_pend[i].t > 30000;
        else if (*(uint64_t *)((char *)ctl + 0x660)) done = 1;          // the engine set one meanwhile
        else {
            int fac = -1, fem = 0, slot = -1;
            const char *why = "";
            if (o == vdf_player()) { fac = vx_own_fac(); fem = own_female(); why = "our body"; }
            else for (int s = 0; s < T2R_MAX_PEERS; s++) if (g_pa_chr[s] == o) { slot = s; fac = vx_fac_of_slot((uint32_t)s, &why); fem = slot_female((uint32_t)s); break; }
            if (fac == 0 || fac == 1) {
                static const char *const G[2][2] = {{"any-scar-male", "any-scar-female"}, {"any-militia-male", "any-militia-female"}};
                const char *g = G[fac][fem ? 1 : 0];
                g_vch_tramp(ctl, fnv64_rt(g), 1);
                static int nl;
                char who[16]; if (slot < 0) snprintf(who, sizeof who, "our body"); else snprintf(who, sizeof who, "slot %d", slot);
                if (nl++ < 60) xlog("vox char: %s (%s) had no voice from its head (group key %llx) -> %s -> character %llx", who, why,
                                    (unsigned long long)g_vch_pend[i].key, g, (unsigned long long)*(uint64_t *)((char *)ctl + 0x660));
                done = 1;
            } else done = now - g_vch_pend[i].t > 30000;
        }
        if (done) {
            while (InterlockedExchange(&g_vch_lock, 1)) YieldProcessor();
            if (g_vch_pend[i].ctl == ctl) g_vch_pend[i].ctl = NULL;
            InterlockedExchange(&g_vch_lock, 0);
        }
    }
}
