// loadheap.c (included by t2r-ext.c after voxchar.c) - the level heaps' figures in the log: pages in use, peaks.
//
// live 191 (reports-1121f cluster A): nearly every level load ended in int3 at exe+12d7fe4, "LoadingHeap::Alloc - Out of memory",
// and no log said how full the heap was. The level heap object (exe 1.6.10721) is exe+4896760:
//   +0x40 page size (2 MB)   +0x48 main pool pages in use   +0x124 main pool pages (1016 stock)   +0x114 the engine's own peak
// The PSO pre-loading heap (exe+48963b0, the same LoadingHeap class) gives the main heap some of its pages: winmm moves bytes from memory
// row 0x59 to row 0x55 before the engine starts (tools/features/level_heap.py, section .t2rlh, status at +8: 1 patched, 2 exe bytes
// differ, 3 VirtualProtect failed, 4 no exe module, 0 not run; no section = an older winmm). Its peak shows whether the move fits.
// lh_tick logs the start state once, then a line each time a heap's session high grows by 16 pages (32 MB); lh_note (crash_note) adds
// the state to every first-chance exception.
#define LH_HEAP 0x4896760
#define LH_PSO 0x48963b0
static const char *lh_winmm_state(void) {
    static char s[112];
    if (s[0]) return s;
    const uint8_t *m = (const uint8_t *)g_winmm;
    snprintf(s, sizeof s, "no .t2rlh in winmm (stock heap sizes)");
    if (!m || IsBadReadPtr(m, 0x400)) return s;
    const uint8_t *nt = m + *(const uint32_t *)(m + 0x3c);
    uint16_t nsec = *(const uint16_t *)(nt + 6), optsz = *(const uint16_t *)(nt + 20);
    const uint8_t *sh = nt + 24 + optsz;
    for (int i = 0; i < nsec; i++, sh += 40)
        if (!memcmp(sh, ".t2rlh", 7)) {
            const uint8_t *sec = m + *(const uint32_t *)(sh + 12);
            if (IsBadReadPtr(sec, 0x18) || *(const uint32_t *)sec != 0x484C3254) { snprintf(s, sizeof s, ".t2rlh without its header"); break; }
            static const char *const st[] = {"not run", "patched", "exe bytes differ, not patched", "VirtualProtect failed", "no exe module", "budget written, rows not"};
            uint32_t v = *(const uint32_t *)(sec + 8);
            uint32_t ver = *(const uint32_t *)(sec + 4);         // v3: +0x18 = render buffer bytes added
            if (ver >= 3 && !IsBadReadPtr(sec, 0x20))
                snprintf(s, sizeof s, "winmm level heap patch v%u: %s (+%llu MB, render buffer +%llu MB)", ver, v < 6 ? st[v] : "?",
                         (unsigned long long)(*(const uint64_t *)(sec + 0x10) >> 20), (unsigned long long)(*(const uint64_t *)(sec + 0x18) >> 20));
            else snprintf(s, sizeof s, "winmm level heap patch: %s (+%llu MB)", v < 6 ? st[v] : "?", (unsigned long long)(*(const uint64_t *)(sec + 0x10) >> 20));
            break;
        }
    return s;
}
static int lh_read(uint32_t at, int64_t *used, int *max, uint32_t *peak) {
    const uint8_t *h = (const uint8_t *)GetModuleHandleW(NULL) + at;
    if (IsBadReadPtr(h, 0x130) || *(const uint64_t *)(h + 0x40) != 0x200000) return 0;
    *used = *(const int64_t *)(h + 0x48);
    *max = *(const int32_t *)(h + 0x124);
    *peak = *(const uint32_t *)(h + 0x114);
    return 1;
}
static void rb_note(const char *why);
static void rb_tick(void);
static void lh_note(const char *why) {
    rb_note(why);
    int64_t u, pu; int mx, pmx; uint32_t pk, ppk;
    if (!lh_read(LH_HEAP, &u, &mx, &pk)) { xlog("loading heap (%s): not readable", why); return; }
    if (!lh_read(LH_PSO, &pu, &pmx, &ppk)) { pu = 0; pmx = 0; ppk = 0; }
    xlog("loading heap (%s): main %lld / %d pages (engine peak %u), PSO pre-loading %lld / %d (peak %u) (2 MB pages; %s)",
         why, (long long)u, mx, pk, (long long)pu, pmx, ppk, g_winmm ? lh_winmm_state() : "winmm not resolved yet");
}
static void lh_tick(void) {
    static int started, nl;
    static int64_t logged_main, logged_pso;
    rb_tick();
    if (!g_winmm) return;
    if (!started) { started = 1; lh_note("start"); }
    if (g_frame % 6) return;                     // (10 Hz: two IsBadReadPtr probes; a short peak still shows in the engine's own +0x114 peak)
    int64_t u, pu; int mx, pmx; uint32_t pk, ppk;
    if (!lh_read(LH_HEAP, &u, &mx, &pk)) return;
    if (!lh_read(LH_PSO, &pu, &pmx, &ppk)) pu = 0;
    if (u >= logged_main + 16) { logged_main = u; if (nl++ < 200) lh_note("new main high"); }
    else if (pu >= logged_pso + 16) { logged_pso = pu; if (nl++ < 200) lh_note("new PSO high"); }
}

// (Supermarket never completes on live since ~191; int3 at exe+1383b09 = Memory::Allocator::PostAllocate "Allocation failed"
// with T = 0x4c000000): the full pool is the render buffer heap (memory row 0xcb ALLOCATION_RENDER_BUFFER, 1216 MB, 'render-buffer-heap').
// Its allocator object is exe+45280b0 (vtable exe+2de2a80): +0xc8 total bytes (vtable +0x88 returns it), +0xd0 / +0xd8 / +0xe0 the counters the
// vtable +0x90 / +0xa0 / +0xb0 getters return under the allocator lock (+0xd0 = the F of the assert). Read here without the lock (u64 reads, a
// log only). exe+45284e8 = the CPU base the handles' offsets are added to (exe 1292176); VirtualQuery on it tells system RAM from a mapped GPU heap.
#define RB_OBJ 0x45280b0
#define RB_BASE 0x45284e8
static int rb_read(uint64_t *tot, uint64_t *a, uint64_t *b, uint64_t *c) {
    const uint8_t *o = (const uint8_t *)GetModuleHandleW(NULL) + RB_OBJ;
    if (IsBadReadPtr(o, 0xe8)) return 0;
    *tot = *(volatile const uint64_t *)(o + 0xc8);
    *a = *(volatile const uint64_t *)(o + 0xd0); *b = *(volatile const uint64_t *)(o + 0xd8); *c = *(volatile const uint64_t *)(o + 0xe0);
    return *tot != 0;
}
static void rb_note(const char *why) {
    uint64_t t, a, b, c;
    if (!rb_read(&t, &a, &b, &c)) { xlog("render buffer (%s): not set up yet", why); return; }
    static int mem_said;
    char mem[160] = "";
    if (!mem_said) {
        mem_said = 1;
        void *base = *(void *const *)((const uint8_t *)GetModuleHandleW(NULL) + RB_BASE);
        MEMORY_BASIC_INFORMATION mi;
        if (base && VirtualQuery(base, &mi, sizeof mi))
            snprintf(mem, sizeof mem, " | base %p: region %llu MB from %p, state %lx protect %lx type %lx",
                     base, (unsigned long long)(mi.RegionSize >> 20), mi.AllocationBase, mi.State, mi.Protect, mi.Type);
        else snprintf(mem, sizeof mem, " | base %p (not queryable)", base);
    }
    xlog("render buffer (%s): total %llu MB, +d0 %llu MB, +d8 %llu MB, +e0 %llu MB%s", why, (unsigned long long)(t >> 20),
         (unsigned long long)(a >> 20), (unsigned long long)(b >> 20), (unsigned long long)(c >> 20), mem);
}
static void rb_tick(void) {
    static uint64_t hi[3]; static int nl;
    if (g_frame % 30) return;                   // 2 Hz
    uint64_t t, v[3];
    if (!rb_read(&t, &v[0], &v[1], &v[2])) return;
    static int first;
    if (!first) { first = 1; rb_note("set up"); memcpy(hi, v, sizeof hi); return; }
    for (int i = 0; i < 3; i++)
        if (v[i] >= hi[i] + (32ull << 20)) { memcpy(hi, v, sizeof hi); if (nl++ < 300) rb_note("+32 MB"); break; }
}
