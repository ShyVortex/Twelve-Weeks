// mem_probe.c: "mem:" log line every 10 s in a match (+ at match start / end): working set, private bytes, commit, page faults per 10 s and
// the VRAM budget / usage from DXGI (IDXGIAdapter3::QueryVideoMemoryInfo, local = VRAM, non-local = shared system memory). Used > budget = the
// driver pages video memory = multi-second stalls. dxgi.dll is loaded dynamically and called through raw vtable slots (no header / import
// dependency); any failure is one log line and the VRAM part is dropped. Release and dev builds.
typedef struct { uint64_t budget, usage, avail, reserved; } mp_vmi;
static void *g_mp_adapter;                        // IDXGIAdapter3 of the biggest adapter (cached)
static int g_mp_vram_state;                       // 0 untried, 1 ok, -1 unavailable
static void mp_vram_init(void) {
    g_mp_vram_state = -1;
    HMODULE d = LoadLibraryA("dxgi.dll");
    typedef long (__stdcall *fn_cf)(const GUID *, void **);
    fn_cf cf = d ? (fn_cf)(void *)GetProcAddress(d, "CreateDXGIFactory1") : NULL;
    if (!cf) { xlog("mem: vram probe unavailable (no dxgi.dll / CreateDXGIFactory1)"); return; }
    static const GUID IID_F1 = {0x770aae78, 0xf26f, 0x4dba, {0xa8, 0x29, 0x25, 0x3c, 0x83, 0xd1, 0xb3, 0x87}};
    static const GUID IID_A3 = {0x645967a4, 0x1392, 0x4310, {0xa7, 0x98, 0x80, 0x53, 0xce, 0x3e, 0x93, 0xfd}};
    void **fac = NULL;
    if (cf(&IID_F1, (void **)&fac) < 0 || !fac) { xlog("mem: vram probe unavailable (factory)"); return; }
    typedef long (__stdcall *fn_enum)(void *, unsigned, void **);
    typedef long (__stdcall *fn_qi)(void *, const GUID *, void **);
    typedef long (__stdcall *fn_desc1)(void *, void *);
    typedef unsigned long (__stdcall *fn_rel)(void *);
    fn_enum en = (fn_enum)((void **)*fac)[12];       // IDXGIFactory1::EnumAdapters1
    void *best = NULL; unsigned long long bestmem = 0; char bestname[64] = "";
    for (unsigned i = 0; i < 16; i++) {
        void **ad = NULL;
        if (en(fac, i, (void **)&ad) < 0 || !ad) break;
        struct { WCHAR name[128]; UINT ven, dev, sub, rev; SIZE_T ded, sys, shared; LUID luid; UINT flags; } desc;   // DXGI_ADAPTER_DESC1
        memset(&desc, 0, sizeof desc);
        void **a3 = NULL;
        if (((fn_desc1)((void **)*ad)[10])(ad, &desc) >= 0 && !(desc.flags & 2) && desc.ded >= bestmem &&
            ((fn_qi)((void **)*ad)[0])(ad, &IID_A3, (void **)&a3) >= 0 && a3) {
            if (best) ((fn_rel)((void **)*(void **)best)[2])(best);
            best = a3; bestmem = desc.ded; WideCharToMultiByte(CP_ACP, 0, desc.name, -1, bestname, sizeof bestname, NULL, NULL);
        }
        ((fn_rel)((void **)*ad)[2])(ad);
    }
    ((fn_rel)((void **)*fac)[2])(fac);
    if (!best) { xlog("mem: vram probe unavailable (no IDXGIAdapter3)"); return; }
    g_mp_adapter = best; g_mp_vram_state = 1;
    xlog("mem: vram probe on '%s' (%llu MB dedicated)", bestname, bestmem >> 20);
}
static int mp_vram(int group, mp_vmi *o) {            // group 0 = local, 1 = non-local
    typedef long (__stdcall *fn_q)(void *, UINT, int, mp_vmi *);
    return ((fn_q)((void **)*(void **)g_mp_adapter)[14])(g_mp_adapter, 0, group, o) >= 0;   // IDXGIAdapter3::QueryVideoMemoryInfo(node 0, group)
}
// Own-resource summary (leak audit): one line at every match start / end with what the ext itself holds, so growth over a long session is visible in
// bug reports without a debugger: process handles / GDI / USER objects / threads (the engine's and ours together; a handle or thread count that climbs
// match after match is a leak, ours or not), our VirtualAlloc count + KB (all one-time installs: must be flat), the object ledger of dc_call (spawn-object
// vs kill-entity: objects left to the level unload are normal, the per-match delta is the number to watch), tracked tables (ammo drops, placed bombs,
// file-poll cache slots), the log counters. "d" values = since the previous [match start].
static struct { LONG64 spawn, kill, arrow, bf, part, lines, supp; } g_mp_base;
// (10-19b, re/tick-cost-1019b.md: the CreateToolhelp32Snapshot(TH32CS_SNAPTHREAD) below walks EVERY thread of the machine - 3450 of them = 20 ms here - and ran on the tick
// thread at each match start and end. The whole summary now runs on a short-lived worker thread: it only reads counters / tables, writes one log line, and the worker
// is one of the counted threads, so it takes itself off the figure.)
static void mem_own_summary_run(int at_start, int self_thread) {
    DWORD hc = 0; GetProcessHandleCount(GetCurrentProcess(), &hc);
    DWORD gdi = GetGuiResources(GetCurrentProcess(), GR_GDIOBJECTS), usr = GetGuiResources(GetCurrentProcess(), GR_USEROBJECTS);
    int thr = 0;
    HANDLE sn = CreateToolhelp32Snapshot(TH32CS_SNAPTHREAD, 0);
    if (sn != INVALID_HANDLE_VALUE) {
        THREADENTRY32 te; te.dwSize = sizeof te; DWORD pid = GetCurrentProcessId();
        for (BOOL ok = Thread32First(sn, &te); ok; ok = Thread32Next(sn, &te)) if (te.th32OwnerProcessID == pid) thr++;
        CloseHandle(sn);
    }
    if (thr >= self_thread) thr -= self_thread;
    int fa = 0; for (int i = 0; i < FA_N; i++) if (g_fap[i].path[0]) fa++;
    int pbu = 0; for (int i = 0; i < PB_MAX; i++) if (g_pb[i].used) pbu++;
    LONG64 so = g_own_spawn_obj, ke = g_own_kill_ent, sa = g_own_stuck_arrow, bf = g_own_bound_frame, pa = g_own_particles, ln = g_xl_lines_total, sp = g_xl_supp_total;
    xlog("mem: %s own: handles %lu, gdi %lu, user %lu, threads %d | own VirtualAlloc %lld blocks %lld KB | engine objects asked: spawn-object %lld (d %lld) kill-entity %lld (d %lld) "
         "outstanding %lld, stuck arrows %lld (d %lld), bound frames %lld (d %lld), particles %lld (d %lld) | tables: ammo drops %d, placed bombs %d, file-poll slots %d/%d, "
         "shiv prop %s, arrow prop %s | log: %lld lines, %lld rate-limited (d %lld / %lld), writer backlog %zu B, %u lost",
         at_start ? "[match start]" : "[match end]", (unsigned long)hc, (unsigned long)gdi, (unsigned long)usr, thr, (long long)g_own_va_n, (long long)g_own_va_kb,
         (long long)so, (long long)(so - g_mp_base.spawn), (long long)ke, (long long)(ke - g_mp_base.kill), (long long)(so - ke), (long long)sa, (long long)(sa - g_mp_base.arrow),
         (long long)bf, (long long)(bf - g_mp_base.bf), (long long)pa, (long long)(pa - g_mp_base.part), g_drops_n, pbu, fa, FA_N,
         g_shiv_prop.obj ? "ALIVE" : "none", g_arrow_prop.obj ? "ALIVE" : "none", (long long)ln, (long long)sp, (long long)(ln - g_mp_base.lines), (long long)(sp - g_mp_base.supp),
         g_xl_pn, (unsigned)g_xl_lost);
    if (at_start) { g_mp_base.spawn = so; g_mp_base.kill = ke; g_mp_base.arrow = sa; g_mp_base.bf = bf; g_mp_base.part = pa; g_mp_base.lines = ln; g_mp_base.supp = sp; }
}
static volatile LONG g_mos_busy;
static DWORD WINAPI mem_own_worker(LPVOID arg) {
    SetThreadPriority(GetCurrentThread(), THREAD_PRIORITY_BELOW_NORMAL);
    mem_own_summary_run((int)(intptr_t)arg, 1);
    InterlockedExchange(&g_mos_busy, 0);
    return 0;
}
static void mem_own_summary(int at_start) {
    if (InterlockedCompareExchange(&g_mos_busy, 1, 0)) return;          // the previous summary is still running (a match start right after an end): skip this one
    HANDLE t = CreateThread(NULL, 0, mem_own_worker, (LPVOID)(intptr_t)at_start, 0, NULL);
    if (t) CloseHandle(t); else { InterlockedExchange(&g_mos_busy, 0); mem_own_summary_run(at_start, 0); }
}
static void mem_probe_tick(void) {
    static uint64_t last_ms; static int was_in; static uint64_t pf_prev; static int over_logged;
    int in = match_substate() == 6;
    uint64_t now = GetTickCount64();
    int edge = in != was_in;
    was_in = in;
    // perf: the DXGI factory + adapter enumeration (a few ms of driver calls) used to run on the first match tick, in the middle of the
    // level-start streaming; do it in the menus instead (10 s after boot), the match edge only finds it done
    if (!g_mp_vram_state && !in && !edge && g_frame > 600) mp_vram_init();
    if (!in && !edge) return;
    if (!edge && now - last_ms < 10000) return;
    last_ms = now;
    if (!g_mp_vram_state) mp_vram_init();
    PROCESS_MEMORY_COUNTERS_EX pmc; memset(&pmc, 0, sizeof pmc); pmc.cb = sizeof pmc;
    if (!K32GetProcessMemoryInfo(GetCurrentProcess(), (PROCESS_MEMORY_COUNTERS *)&pmc, sizeof pmc)) return;
    uint64_t pf = pmc.PageFaultCount, dpf = pf_prev && pf >= pf_prev ? pf - pf_prev : 0;
    pf_prev = pf;
    char v[160] = "vram n/a";
    mp_vmi l = {0}, nl = {0};
    if (g_mp_vram_state == 1 && mp_vram(0, &l) && mp_vram(1, &nl)) {
        snprintf(v, sizeof v, "vram used %llu / budget %llu MB (local), non-local %llu / %llu MB", (unsigned long long)(l.usage >> 20), (unsigned long long)(l.budget >> 20),
                 (unsigned long long)(nl.usage >> 20), (unsigned long long)(nl.budget >> 20));
        if (l.budget && l.usage > l.budget && !over_logged) { over_logged = 1; g_perf_vram_over = 1; xlog("mem: budget exceeded - local vram used %llu MB > budget %llu MB (the driver pages video memory: stutters)", (unsigned long long)(l.usage >> 20), (unsigned long long)(l.budget >> 20)); }
    }
    xlog("mem: %s ws %llu MB, private %llu MB, commit %llu MB, pagefaults +%llu/10s, %s", edge ? (in ? "[match start]" : "[match end]") : "", (unsigned long long)(pmc.WorkingSetSize >> 20),
         (unsigned long long)(pmc.PrivateUsage >> 20), (unsigned long long)(pmc.PagefileUsage >> 20), (unsigned long long)dpf, v);
    if (edge) mem_own_summary(in);
}

// op 0xCA [64B token][u8 ver=1][u8 stalls>=250ms][u8 stalls>=1000ms][u16 worst ms][u16 avg frame ms*10][u8 flags bit0 = VRAM over budget]:
// every 30 s, stalls of the last 5 minutes in a match. Reply 0xCB. A server that never answers is left alone after 2 tries.
static void perf_report_tick(void) {
    static uint64_t next_at;
    uint64_t now = GetTickCount64();
    int early = g_ow_alarm != 0;                                       // one-way spell seen (netsmooth.c ow_tick): report now, not at the next 30 s mark
    if (g_perf_dead >= 2 || (now < next_at && !early) || g_clan_busy) return;
    if (!next_at && !early) { next_at = now + 20000; return; }
    unsigned c250 = 0, c1000 = 0, worst = 0;
    int n = g_perf_n < PERF_RING ? g_perf_n : PERF_RING;
    for (int i = 0; i < n; i++) {
        if (now - g_perf_t[i] > PERF_WINDOW_MS) continue;
        c250++; if (g_perf_ms[i] >= 1000) c1000++;
        if (g_perf_ms[i] > worst) worst = g_perf_ms[i];
    }
    uint64_t avg10 = g_perf_frames ? g_perf_sum_ms * 10 / g_perf_frames : 0;
    uint8_t b[24 + 3 + 9 * T2R_MAX_PEERS];
    b[0] = 1; b[1] = c250 > 255 ? 255 : (uint8_t)c250; b[2] = c1000 > 255 ? 255 : (uint8_t)c1000;
    if (worst > 65535) worst = 65535;
    if (avg10 > 65535) avg10 = 65535;
    b[3] = (uint8_t)worst; b[4] = (uint8_t)(worst >> 8); b[5] = (uint8_t)avg10; b[6] = (uint8_t)(avg10 >> 8);
    b[7] = (g_perf_vram_over ? 1 : 0) | (early ? 2 : 0);              // bit1 = one-way alarm (trailer 2 below)
    // optional trailer (netsmooth.c g_cap_*; old servers ignore it): [u8 1][u16 avg tx KB/s][u16 peak tx KB/s][u8 worst msg-7 loss x10 %][u8 samples]
    uint32_t cn = g_cap_n, cavg = cn ? g_cap_tx_sum_kb / cn : 0, cpk = g_cap_tx_peak_kb, cl = g_cap_loss10;
    b[8] = 1; b[9] = (uint8_t)(cavg > 65535 ? 255 : cavg); b[10] = (uint8_t)((cavg > 65535 ? 65535 : cavg) >> 8);
    if (cpk > 65535) cpk = 65535;
    b[11] = (uint8_t)cpk; b[12] = (uint8_t)(cpk >> 8); b[13] = (uint8_t)cl; b[14] = (uint8_t)(cn > 255 ? 255 : cn);
    // trailer 2 (only with the alarm; old servers ignore it): [u8 1][u8 quiet s][u16 rx datagrams this match][u16 tx KB since the last rx][u8 s into the match]
    int blen = 15;
    if (early) {
        uint32_t rp = g_ow_rx_pkts > 65535 ? 65535 : g_ow_rx_pkts, tk = g_ow_tx_kb > 65535 ? 65535 : g_ow_tx_kb;
        b[15] = 1; b[16] = (uint8_t)(g_ow_streak_s > 255 ? 255 : g_ow_streak_s); b[17] = (uint8_t)rp; b[18] = (uint8_t)(rp >> 8);
        b[19] = (uint8_t)tk; b[20] = (uint8_t)(tk >> 8); b[21] = (uint8_t)(g_ow_in_s > 255 ? 255 : g_ow_in_s); blen = 22;
    }
    // trailer 3 (flags bit2; old servers ignore it): [u8 1][u8 flags: bit0 our msg 7 sends to far peers are paced (t2r-m7-lod.txt), bit1 our host
    // upload budget is on (t2r-host-bw.txt) - both make seq gaps that are not loss][u8 n] n x ([u8 slot][u32 FNV-1a of the roster name, up to 24 B][u16 msg 7 received][u16 lost])
    // = what we received from each other player since the last report. The daemon removes a player whose median loss over 2+ observers stays high.
    if (match_substate() != 6) { memset(g_lr_rx, 0, sizeof g_lr_rx); memset(g_lr_lost, 0, sizeof g_lr_lost); }
    else {
        int at = blen, n = 0;
        b[at] = 1; b[at + 1] = (uint8_t)((g_ns_m7_lod_off ? 0 : 1) | (g_hbw.on ? 2 : 0));
        for (uint32_t sl = 0; sl < T2R_MAX_PEERS; sl++) {
            uint32_t rx = g_lr_rx[sl], lo = g_lr_lost[sl];
            if (!rx && !lo) continue;
            if (rx > 65535 || lo > 65535) { double k = 65535.0 / (rx > lo ? rx : lo); rx = (uint32_t)(rx * k); lo = (uint32_t)(lo * k); }
            uint8_t *e = b + at + 3 + n * 9; uint32_t h = 2166136261u;
            for (int i = 0; i < 24 && g_lr_nm[sl][i]; i++) h = (h ^ (uint8_t)g_lr_nm[sl][i]) * 16777619u;
            e[0] = (uint8_t)sl; e[1] = (uint8_t)h; e[2] = (uint8_t)(h >> 8); e[3] = (uint8_t)(h >> 16); e[4] = (uint8_t)(h >> 24);
            e[5] = (uint8_t)rx; e[6] = (uint8_t)(rx >> 8); e[7] = (uint8_t)lo; e[8] = (uint8_t)(lo >> 8);
            n++;
        }
        if (n) { b[at + 2] = (uint8_t)n; blen = at + 3 + n * 9; b[7] |= 4; }
    }
    if (clan_send(0xCA, b, blen)) {
        if (b[7] & 4) { memset(g_lr_rx, 0, sizeof g_lr_rx); memset(g_lr_lost, 0, sizeof g_lr_lost); }
        if (early) { g_ow_alarm = 0; if (!next_at) next_at = now + 20000; return; }   // the stats windows keep running for the regular report
        g_cap_tx_sum_kb = g_cap_tx_peak_kb = g_cap_n = g_cap_loss10 = 0;
        next_at = now + 30000;
        g_perf_sum_ms = 0; g_perf_frames = 0;
        static int logged; if (logged++ < 3 || c1000) xlog("perf: report %u stalls >= 250 ms, %u >= 1 s, worst %u ms, avg frame %.1f ms%s", c250, c1000, worst, avg10 / 10.0, g_perf_vram_over ? ", vram over budget" : "");
    }
}

// perf30 (release + dev): ONE log line every 30 s in a match with the numbers that say where a player's frame time goes:
//   perf30: N frames, frame avg X ms (Y fps) worst Z ms, > 25 ms a / > 40 ms b / > 100 ms c | our tick avg A ms max B ms (P % of the frame) |
//   draw hook avg C ms max D | sound requests n (avg ns, T ms total), breakable events m (avg ns) | top: feature avg ms/frame (peak ms) x3 | slowest call: name ms
// "our tick" = everything t2r_tick does (all PF features + the code between them); the draw hook (HUD overlays from winmm's marker draw) and the
// two engine-event hooks run outside it. Frame avg far above tick + hooks = the engine / GPU / driver (not the mod). The window is reset by each
// line, a line is skipped (window kept) outside a match or under 120 frames.
static void perf_line_tick(void) {
    static uint64_t next_at;
    uint64_t now = GetTickCount64();
    if (now < next_at) return;
    if (!next_at) { next_at = now + 30000; return; }
    next_at = now + 30000;
    if (match_substate() != 6 || g_pl_fr_n < 120 || !g_stall_qf) return;
    double k = 1000.0 / (double)g_stall_qf, n = (double)g_pl_fr_n;
    double fa = g_pl_fr_sum / n, ta = (double)g_pl_tk_sum * k / n, tm = (double)g_pl_tk_max * k;
    char line[2400]; int o = snprintf(line, sizeof line, "perf30: %llu frames, frame avg %.2f ms (%.0f fps) worst %.1f ms, >25 ms %llu / >40 ms %llu / >100 ms %llu | our tick avg %.3f ms max %.2f ms (%.1f%% of the frame)",
                                     (unsigned long long)g_pl_fr_n, fa, fa > 0.0 ? 1000.0 / fa : 0.0, g_pl_fr_max, (unsigned long long)g_pl_fr_25, (unsigned long long)g_pl_fr_40,
                                     (unsigned long long)g_pl_fr_100, ta, tm, fa > 0.0 ? 100.0 * ta / fa : 0.0);
    o += snprintf(line + o, SNLEFT(line, o), " | our tick cpu %.2f Mcycles/frame", (double)g_pl_cyc_sum / n / 1e6);
    o += snprintf(line + o, SNLEFT(line, o), " | >25 ms frames: ours (prev tick > 4 ms) %llu (%.0f ms), engine only %llu (%.0f ms); ticks > 4 ms %llu",
                  (unsigned long long)g_pl_h_ours, g_pl_h_ours_ms, (unsigned long long)g_pl_h_eng, g_pl_h_eng_ms, (unsigned long long)g_pl_t4);
    if (g_pl_dr_n) o += snprintf(line + o, SNLEFT(line, o), " | draw hook avg %.3f ms max %.2f ms", (double)g_pl_dr_sum * k / (double)g_pl_dr_n, (double)g_pl_dr_max * k);
    LONG64 sn = g_pl_snd_n, sq = g_pl_snd_q, gn = g_pl_gl_n, gq = g_pl_gl_q;
    o += snprintf(line + o, SNLEFT(line, o), " | hooks: sound requests %lld (avg %.0f ns, %.2f ms total)", (long long)sn, sn ? (double)sq * k * 1e6 / (double)sn : 0.0, (double)sq * k);
    o += snprintf(line + o, SNLEFT(line, o), ", breakable events %lld (avg %.0f ns, %.2f ms total)", (long long)gn, gn ? (double)gq * k * 1e6 / (double)gn : 0.0, (double)gq * k);
    static char used[T2R_PF_MAX];
    memset(used, 0, sizeof used);
    int64_t worst_q = 0; int worst_i = -1;
    for (int i = 0; i < g_pf_n; i++) if (g_pl_max[i] > worst_q) { worst_q = g_pl_max[i]; worst_i = i; }
    o += snprintf(line + o, SNLEFT(line, o), " | top:");
    { int64_t pfsum = 0; for (int i = 0; i < g_pf_n; i++) pfsum += g_pl_acc[i];
      o += snprintf(line + o, SNLEFT(line, o), " | PF features sum %.3f ms/frame (rest of the tick: %.3f)", (double)pfsum * k / n, ta - (double)pfsum * k / n); }
    for (int r = 0; r < 6; r++) {
        int best = -1;
        for (int i = 0; i < g_pf_n; i++) if (!used[i] && g_pl_acc[i] > 0 && (best < 0 || g_pl_acc[i] > g_pl_acc[best])) best = i;
        if (best < 0) break;
        used[best] = 1;
        o += snprintf(line + o, SNLEFT(line, o), " %.36s %.3f ms (peak %.2f);", g_pf_name[best], (double)g_pl_acc[best] * k / n, (double)g_pl_max[best] * k);
    }
    if (worst_i >= 0) o += snprintf(line + o, SNLEFT(line, o), " slowest single call %.36s %.2f ms", g_pf_name[worst_i], (double)worst_q * k);
    {   // sub-steps (SUBP / SUBT in the big features): the 4 with the worst single call
        int ub[T2R_SUB_MAX] = {0}; o += snprintf(line + o, SNLEFT(line, o), " | subs:");
        for (int r = 0; r < 6; r++) {
            int best = -1;
            for (int i = 0; i < g_sub_n; i++) if (!ub[i] && g_sub_max[i] > 0 && (best < 0 || g_sub_max[i] > g_sub_max[best])) best = i;
            if (best < 0) break;
            ub[best] = 1;
            o += snprintf(line + o, SNLEFT(line, o), " %.44s avg %.3f ms (peak %.2f);", g_sub_name[best], (double)g_sub_acc[best] * k / n, (double)g_sub_max[best] * k);
        }
    }
    {   // pacing (frame-time histogram, 0.25 ms bins): what perf30's average hides at high fps
        uint64_t tot = 0; for (int b = 0; b <= 200; b++) tot += g_pl_hist[b];
        if (tot) {
            double pc[3] = {0, 0, 0}; const double qs[3] = {0.5, 0.95, 0.99}; uint64_t cum = 0; int qi = 0;
            for (int b = 0; b <= 200 && qi < 3; b++) { cum += g_pl_hist[b]; while (qi < 3 && (double)cum >= qs[qi] * (double)tot) pc[qi++] = (b + 1) * 0.25; }
            uint64_t o15 = 0, o20 = 0;
            for (int b = 0; b <= 200; b++) { double lo = b * 0.25; if (lo >= 1.5 * pc[0]) o15 += g_pl_hist[b]; if (lo >= 2.0 * pc[0]) o20 += g_pl_hist[b]; }
            o += snprintf(line + o, SNLEFT(line, o), " | pacing: p50 %.2f p95 %.2f p99 %.2f ms, mean |frame delta| %.2f ms, >1.5x median %llu, >2x median %llu, uneven (jump > 30%% and > 2 ms) %llu frames, longest uneven run %llu",
                          pc[0], pc[1], pc[2], g_pl_abs_n ? g_pl_abs_d / (double)g_pl_abs_n : 0.0, (unsigned long long)o15, (unsigned long long)o20,
                          (unsigned long long)g_pl_jit, (unsigned long long)g_pl_runmax);
        }
    }
    // the match clock vs the wall clock (wave respawn: players did not spawn with their teammates): each client ends its countdown at its OWN
    // reading of the replicated timer; clocks of two players' logs are compared through this (system tms = same machine on A/B)
    { float rem; uint8_t *lo = lobby_obj();
      if (music_match_rem(&rem) && lo) o += snprintf(line + o, SNLEFT(line, o), " | match clock %.2f s elapsed tms %llu", *(float *)(lo + 0x2b8c) - rem, (unsigned long long)now); }
    xlog("%s", line);
    g_pl_fr_sum = g_pl_fr_max = 0.0; g_pl_fr_n = g_pl_fr_25 = g_pl_fr_40 = g_pl_fr_100 = 0;
    memset(g_pl_hist, 0, sizeof g_pl_hist); g_pl_abs_d = 0.0; g_pl_abs_n = g_pl_run = g_pl_runmax = g_pl_jit = 0;
    memset(g_sub_acc, 0, sizeof g_sub_acc); memset(g_sub_max, 0, sizeof g_sub_max);
    g_pl_cyc_sum = 0; g_pl_h_ours = g_pl_h_eng = g_pl_t4 = 0; g_pl_h_ours_ms = g_pl_h_eng_ms = 0.0;
    g_pl_tk_sum = g_pl_tk_max = 0; g_pl_dr_sum = g_pl_dr_max = 0; g_pl_dr_n = 0;
    InterlockedExchange64(&g_pl_snd_n, 0); InterlockedExchange64(&g_pl_snd_q, 0); InterlockedExchange64(&g_pl_gl_n, 0); InterlockedExchange64(&g_pl_gl_q, 0);
    memset(g_pl_acc, 0, sizeof g_pl_acc); memset(g_pl_max, 0, sizeof g_pl_max); memset(g_pl_calls, 0, sizeof g_pl_calls);
}
