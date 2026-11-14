// stall_diag.c - whole-game stall detector. Included from t2r-ext.c right before t2r_tick.
//
// Why: 0.5-1.1 s freezes of the whole picture in matches. The per-feature profiler (PF) only sees our own tick, and it showed ~6 ms peaks, so the
// stall is outside our ticks. This answers WHERE the main thread sits while it does not tick:
//  - stall_tick_begin() (every tick, ~0.1 us): real time since the previous tick; > 200 ms logs ONE line "stall: N ms between ticks" with the
//    last thing we did (PF name of the feature tick, or "between ticks" = the engine/render/GPU wait, or the last dc_call native), the main
//    thread's CPU time over the stall (cpu ~ 0 = blocked waiting, cpu ~ N = busy), the page faults, and what the watchdog saw.
//  - a watchdog thread (wakes every 40 ms): when no tick began for 250 ms it suspends the main thread for a few microseconds, reads RIP and a
//    stack scan (no locks / allocation while suspended), resumes it and logs "stall: main thread at module+off, stack: ...". Up to 3 samples
//    per stall (250 ms apart), so a wait in d3d12 / the driver / the file system / a mutex shows by module name.
//  - dc_call() times every native: > 30 ms logs "stall: dc_call 0x.. took N ms" (a native that loads / streams something).
// Always on (release too), one line per stall, rate limited. Opt out: t2r-no-stall-diag.txt next to the exe.
#include <psapi.h>
static volatile LONG g_stall_on;                    // 1 = running (watchdog thread started)
static volatile int64_t g_stall_begin_q;            // QPC of the current tick's begin (0 = no tick yet)
static volatile LONG g_stall_in_tick;
static volatile DWORD g_stall_main_tid;
static int64_t g_stall_qf;
static uint64_t g_stall_cpu_end;                    // CPU (100 ns) of the thread that ran the last tick, at its end
static DWORD g_stall_end_tid;                       // that thread (the engine runs t2r_tick on whichever worker thread: cpu is per thread)
static int64_t g_stall_tick_q;                      // the last tick's own duration (QPC), its slowest PF call and that call's name
static int64_t g_stall_last_slow_q;
static const char *g_stall_last_slow_nm;
static volatile uint64_t g_stall_wd_pf;             // page faults when the watchdog first saw this stall
static char g_stall_wd_txt[3][420];                 // watchdog samples of the current stall
static volatile LONG g_stall_wd_n;
static volatile int64_t g_stall_wd_for;             // the g_stall_begin_q the samples belong to
static uint32_t g_stall_logged;

static uint64_t stall_cpu_now(void) {
    FILETIME c, e, k, u;
    if (!GetThreadTimes(GetCurrentThread(), &c, &e, &k, &u)) return 0;
    return (((uint64_t)k.dwHighDateTime << 32) | k.dwLowDateTime) + (((uint64_t)u.dwHighDateTime << 32) | u.dwLowDateTime);
}
static uint64_t stall_pf_now(void) {
    PROCESS_MEMORY_COUNTERS pmc;
    if (!K32GetProcessMemoryInfo(GetCurrentProcess(), &pmc, sizeof pmc)) return 0;
    return pmc.PageFaultCount;
}
static int stall_sym(char *out, int cap, uint64_t a) {      // "module+0xoff"
    HMODULE m = NULL;
    if (!GetModuleHandleExA(GET_MODULE_HANDLE_EX_FLAG_FROM_ADDRESS | GET_MODULE_HANDLE_EX_FLAG_UNCHANGED_REFCOUNT, (LPCSTR)(uintptr_t)a, &m) || !m)
        return snprintf(out, (size_t)cap, "%llx", (unsigned long long)a);
    char p[MAX_PATH];
    DWORD n = GetModuleFileNameA(m, p, sizeof p);
    const char *b = p;
    for (DWORD i = 0; i < n; i++) if (p[i] == '\\' || p[i] == '/') b = p + i + 1;
    return snprintf(out, (size_t)cap, "%s+%llx", b, (unsigned long long)(a - (uint64_t)(uintptr_t)m));
}
static int stall_is_code(uint64_t a) {
    MEMORY_BASIC_INFORMATION mi;
    if (a < 0x10000 || !VirtualQuery((void *)(uintptr_t)a, &mi, sizeof mi)) return 0;
    return mi.State == MEM_COMMIT && mi.Type == MEM_IMAGE && (mi.Protect & (PAGE_EXECUTE | PAGE_EXECUTE_READ | PAGE_EXECUTE_READWRITE | PAGE_EXECUTE_WRITECOPY));
}
static DWORD WINAPI stall_watchdog(LPVOID unused) {
    (void)unused;
    DWORD th_tid = g_stall_main_tid;
    HANDLE th = OpenThread(THREAD_SUSPEND_RESUME | THREAD_GET_CONTEXT | THREAD_QUERY_INFORMATION, FALSE, th_tid);
    if (!th) return 0;
    int64_t last_sample_q = 0;
    uint32_t samples_total = 0;
    for (;;) {
        Sleep(40);
        if (g_stall_main_tid != th_tid) {      // the tick moved to another thread: sample the one that ran the last tick
            HANDLE nt = OpenThread(THREAD_SUSPEND_RESUME | THREAD_GET_CONTEXT | THREAD_QUERY_INFORMATION, FALSE, g_stall_main_tid);
            if (nt) { CloseHandle(th); th = nt; th_tid = g_stall_main_tid; }
        }
        int64_t b = g_stall_begin_q;
        LARGE_INTEGER c; QueryPerformanceCounter(&c);
        int64_t ms = (c.QuadPart - b) * 1000 / g_stall_qf;
        if (!b || ms < 250 || ms > 600000 || samples_total > 150) continue;
        if (g_stall_wd_for != b) { g_stall_wd_for = b; g_stall_wd_n = 0; g_stall_wd_pf = stall_pf_now(); last_sample_q = 0; }
        if (g_stall_wd_n >= 3 || (last_sample_q && (c.QuadPart - last_sample_q) * 1000 / g_stall_qf < 220)) continue;
        // sample the main thread: suspend, copy RIP / RSP / 160 stack words, resume - nothing else while it is stopped (no heap, no loader lock)
        CONTEXT ctx; memset(&ctx, 0, sizeof ctx); ctx.ContextFlags = CONTEXT_CONTROL | CONTEXT_INTEGER;
        uint64_t stk[160]; SIZE_T got = 0; int ok = 0;
        if (SuspendThread(th) != (DWORD)-1) {
            if (GetThreadContext(th, &ctx)) ok = ReadProcessMemory(GetCurrentProcess(), (void *)(uintptr_t)ctx.Rsp, stk, sizeof stk, &got) || got > 0;
            ResumeThread(th);
        }
        last_sample_q = c.QuadPart; samples_total++;
        if (!ok) continue;
        char t[420]; int n = snprintf(t, sizeof t, "@%lld ms rip ", (long long)ms);
        n += stall_sym(t + n, (int)sizeof t - n, ctx.Rip);
        n += snprintf(t + n, SNLEFT(t, n), " stack");
        int shown = 0;
        for (SIZE_T i = 0; i < got / 8 && shown < 9 && n < (int)sizeof t - 60; i++) {
            if (!stall_is_code(stk[i])) continue;
            n += snprintf(t + n, SNLEFT(t, n), " ");
            n += stall_sym(t + n, (int)sizeof t - n, stk[i]);
            shown++;
        }
        LONG k = g_stall_wd_n;
        if (k < 3) { snprintf(g_stall_wd_txt[k], sizeof g_stall_wd_txt[k], "%s", t); g_stall_wd_n = k + 1; }
    }
    return 0;
}
// ---- performance report for the server's host pick: stalls >= 250 ms seen while IN A MATCH (loads / menus excluded), last 5 minutes.
// perf_note_gap() runs every tick; perf_report_tick() (mem_probe.c) sends op 0xCA every 30 s: see tools/daemon.py "PERFORMANCE REPORT".
#define PERF_RING 64
#define PERF_WINDOW_MS 300000ULL
static uint64_t g_perf_t[PERF_RING];           // GetTickCount64 of each stall >= 250 ms
static uint32_t g_perf_ms[PERF_RING];
static int g_perf_n;                            // ring write index
static int64_t g_perf_prev_q;
static uint64_t g_perf_sum_ms, g_perf_frames;   // in-match frame time sum over the window start (reset each send)
static int g_perf_vram_over;                    // mem_probe.c: local VRAM used > budget (the driver pages video memory)
static void perf_note_gap(int64_t q) {
    // Boot crash: this runs at the top of t2r_tick, BEFORE the first tick resolves g_winmm - match_substate() reads through
    // winmm's base (VMA) and crashed every client on its first frame, before the log was even opened. Nothing until winmm is known.
    if (!g_winmm) return;
    int64_t prev = g_perf_prev_q; g_perf_prev_q = q;
    double pdl = g_pl_counting ? g_pl_prev_d : 0.0;      // previous counted frame time (0 = none: the first frame of a run is not compared)
    g_pl_counting = 0;
    static uint64_t in_since;
    uint64_t now = GetTickCount64();
    if (match_substate() != 6) { in_since = 0; return; }
    if (!in_since) { in_since = now; return; }
    if (!prev || !g_stall_qf || now - in_since < 15000) return;      // the first seconds of a match are still streaming in
    int64_t ms = (q - prev) * 1000 / g_stall_qf;
    if (ms < 0 || ms >= 120000) return;
    g_perf_sum_ms += (uint64_t)ms; g_perf_frames++;
    {   // perf30 (t2r-ext.c g_pl_*): exact frame time in ms, counted while in a match (the first 15 s excluded: level streaming)
        double dms = (double)(q - prev) * 1000.0 / (double)g_stall_qf;
        g_pl_fr_sum += dms; g_pl_fr_n++; g_pl_counting = 1;
        if (dms > g_pl_fr_max) g_pl_fr_max = dms;
        { int bi = (int)(dms * 4.0); if (bi > 200) bi = 200; g_pl_hist[bi]++;
          if (pdl > 0.0) {
              double dd = dms > pdl ? dms - pdl : pdl - dms;
              g_pl_abs_d += dd; g_pl_abs_n++;
              if (dd > 2.0 && dd > 0.3 * pdl) { g_pl_jit++; if (++g_pl_run > g_pl_runmax) g_pl_runmax = g_pl_run; } else g_pl_run = 0;
          } else g_pl_run = 0;
          g_pl_prev_d = dms; }
        if (dms > 25.0) {
            g_pl_fr_25++;
            // the gap runs tick-start to tick-start, so the previous tick's own time (g_stall_tick_q, still that tick's) is part of it
            double tk = g_stall_qf ? (double)g_stall_tick_q * 1000.0 / (double)g_stall_qf : 0.0;
            if (tk > 4.0) { g_pl_h_ours++; g_pl_h_ours_ms += dms; } else { g_pl_h_eng++; g_pl_h_eng_ms += dms; }
            {   // one line per > 25 ms frame (40 per session) naming what the engine / we were doing around it, so engine-only hitches can be
                // matched to a body spawn, a heap compaction pass or a downed / paired move instead of only being counted in perf30
                static int nh;
                if (nh < 40) {
                    nh++;
                    uint64_t born = 0;
                    for (int i = 0; i < T2R_MAX_PEERS; i++) if (g_pup_born[i] > born) born = g_pup_born[i];
                    double sl = g_stall_qf ? (double)g_stall_last_slow_q * 1000.0 / (double)g_stall_qf : 0.0;
                    xlog("hitch: frame %llu took %.1f ms (previous tick %.1f ms, its slowest %s %.1f ms) | heap compaction last pass %.2f ms, a move of our Player %lld frames ago | "
                         "own spawn %lld frames ago, newest puppet spawn %lld frames ago | downed %d, psync %d",
                         (unsigned long long)g_frame, dms, tk, g_stall_last_slow_nm ? g_stall_last_slow_nm : "-", sl,
                         g_stall_qf ? (double)g_cm_q_last * 1000.0 / (double)g_stall_qf : 0.0, g_cm_move_frame ? (long long)(g_frame - g_cm_move_frame) : -1LL,
                         g_spawned_frame ? (long long)(g_frame - g_spawned_frame) : -1LL, born ? (long long)(g_frame - born) : -1LL, g_downed, psync_active());
                }
            }
        }
        if (dms > 40.0) g_pl_fr_40++;
        if (dms > 100.0) g_pl_fr_100++;
    }
    if (ms >= 250) { g_perf_t[g_perf_n % PERF_RING] = now; g_perf_ms[g_perf_n % PERF_RING] = (uint32_t)ms; g_perf_n++; }
}
static void stall_tick_begin(void) {
    static int off = -1;
    LARGE_INTEGER c; QueryPerformanceCounter(&c);
    if (off < 0) {
        FILE *f = exe_side_open("t2r-no-stall-diag.txt", "r");
        off = f != NULL; if (f) fclose(f);
        LARGE_INTEGER q; QueryPerformanceFrequency(&q); g_stall_qf = q.QuadPart ? q.QuadPart : 1;
        if (off) xlog("stall diag: OFF (t2r-no-stall-diag.txt)");
    }
    perf_note_gap(c.QuadPart);     // host-pick performance report (perf_report below): independent of the diag opt-out
    if (off) return;
    int64_t prev = g_stall_begin_q;
    if (prev) {
        int64_t ms = (c.QuadPart - prev) * 1000 / g_stall_qf;
        if (ms >= 200 && ms < 600000 && (g_stall_logged < 80 || ms >= 1500)) {
            g_stall_logged++;
            // ms of CPU the tick thread used between the last tick's end and now - only when this tick runs on that same thread (it moves
            // between engine workers: the old line subtracted two threads' times = the 1844674407... values)
            int same = g_stall_end_tid == GetCurrentThreadId();
            double cpu = g_stall_cpu_end && same ? (double)(stall_cpu_now() - g_stall_cpu_end) / 10000.0 : -1.0;
            uint64_t pf = g_stall_wd_for == prev && g_stall_wd_pf ? stall_pf_now() - g_stall_wd_pf : 0;
            char ring[200]; int rn = 0; ring[0] = 0;
            LONG ri = g_stall_ring_i;
            for (int k = 0; k < 4 && ri - k > 0 && rn < 170; k++) rn += snprintf(ring + rn, SNLEFT(ring, rn), " %llx", (unsigned long long)g_stall_ring[(ri - k) & 7]);
            // our share of the gap: the previous tick's own time and its slowest feature (the rest is the engine / render / the OS)
            double tick_ms = (double)g_stall_tick_q * 1000.0 / (double)g_stall_qf, slow_ms = (double)g_stall_last_slow_q * 1000.0 / (double)g_stall_qf;
            xlog("stall: %lld ms between ticks (frame %llu): our last tick %.1f ms (slowest %s %.1f ms), then %s%s | tick thread cpu %s%.0f ms after it, page faults after 250 ms %llu | last dc_call sids%s | watchdog: %s | %s | %s",
                 (long long)ms, (unsigned long long)g_frame, tick_ms, g_stall_last_slow_nm ? g_stall_last_slow_nm : "-", slow_ms,
                 g_stall_in_tick ? "INSIDE " : "after ", g_stall_what ? g_stall_what : "?",
                 same ? "" : "n/a (next tick on another thread) ", same ? cpu : 0.0, (unsigned long long)pf, ring[0] ? ring : " -",
                 g_stall_wd_for == prev && g_stall_wd_n > 0 ? g_stall_wd_txt[0] : "-", g_stall_wd_for == prev && g_stall_wd_n > 1 ? g_stall_wd_txt[1] : "-",
                 g_stall_wd_for == prev && g_stall_wd_n > 2 ? g_stall_wd_txt[2] : "-");
        }
    }
    g_stall_begin_q = c.QuadPart;
    QueryThreadCycleTime(GetCurrentThread(), &g_pl_cyc0);   // perf30: CPU cycles the main thread really spent in our tick (vs wall time)
    g_stall_in_tick = 1;
    g_stall_slow_q = 0; g_stall_slow_nm = NULL;
    g_spk_dc_q = g_spk_dc_tot = 0; g_spk_dc_sid = 0; g_spk_dc_n = 0;        // spike line: this tick's natives
    g_spk_vq_n0 = g_bw_n_vq; g_spk_vq_q0 = g_bw_vq_q;                       // ... and the synchronous VirtualQuery rounds of the bad-write cache
    g_stall_main_tid = GetCurrentThreadId();
    if (!g_stall_on && InterlockedCompareExchange(&g_stall_on, 1, 0) == 0) {
        HANDLE t = CreateThread(NULL, 0, stall_watchdog, NULL, 0, NULL);
        if (t) { SetThreadPriority(t, THREAD_PRIORITY_ABOVE_NORMAL); CloseHandle(t); }
        xlog("stall diag: on (watchdog samples the main thread after 250 ms without a tick; stall lines at >= 200 ms)");
    }
}
// "spike:": one line per tick whose slowest feature took >= 6 ms in a match (60 per session, 12 per feature): the feature, the tick,
// the main thread's CPU time in it (QueryThreadCycleTime delta, converted with this window's cycles per wall ms: a wall time far above it = the thread was descheduled / blocked,
// not working), this tick's natives (count, total, worst sid - tools/reports/dc_sid_names.py names it) and the named sub-steps (SUBP / SUBLAP) of that feature >= 0.5 ms.
static void spike_emit(int64_t tick_q) {
    static uint32_t total; static const char *nm_seen[12]; static uint8_t nm_cnt[12];
    const char *nm = g_stall_slow_nm ? g_stall_slow_nm : "?";
    if (total >= 60 || !g_stall_qf) return;
    int k = -1;
    for (int i = 0; i < 12; i++) { if (nm_seen[i] == nm) { k = i; break; } if (!nm_seen[i] && k < 0) k = i; }
    if (k >= 0) { if (!nm_seen[k]) nm_seen[k] = nm; if (nm_cnt[k] >= 12) return; nm_cnt[k]++; }
    total++;
    double qk = 1000.0 / (double)g_stall_qf;
    ULONG64 c1 = 0; QueryThreadCycleTime(GetCurrentThread(), &c1);
    int same = g_stall_main_tid == GetCurrentThreadId() && g_pl_cyc0 && c1 > g_pl_cyc0;
    double mcyc = same ? (double)(c1 - g_pl_cyc0) / 1e6 : -1.0;
    double cyc_ms = g_pl_cyc_sum && g_pl_tk_sum ? (double)g_pl_cyc_sum / ((double)g_pl_tk_sum * qk) : 0.0;     // cycles per wall ms while our tick ran
    char subs[700]; int o = 0; subs[0] = 0;
    for (int i = 0; i < g_sub_n && o < (int)sizeof subs - 90; i++)
        if (g_sub_seq[i] == g_spk_slow_seq && (double)g_sub_last[i] * qk >= 0.5) o += snprintf(subs + o, SNLEFT(subs, o), " %.44s %.2f ms;", g_sub_name[i], (double)g_sub_last[i] * qk);
    xlog("spike: frame %llu %.60s %.1f ms (tick %.1f ms; main-thread cpu %s%.1f Mcycles%s%.1f ms) | natives this tick: %u, %.1f ms total, worst %016llx %.2f ms | sync VirtualQuery (bad-write cache) this tick: %lld, %.1f ms | sub-steps of it:%s | downed %d, psync %d",
         (unsigned long long)g_frame, nm, (double)g_stall_slow_q * qk, (double)tick_q * qk, same ? "" : "n/a ", mcyc < 0 ? 0.0 : mcyc,
         mcyc >= 0 && cyc_ms > 0 ? " = ~" : " (", mcyc >= 0 && cyc_ms > 0 ? mcyc * 1e6 / cyc_ms : 0.0,
         (unsigned)g_spk_dc_n, (double)g_spk_dc_tot * qk, (unsigned long long)g_spk_dc_sid, (double)g_spk_dc_q * qk,
         (long long)(g_bw_n_vq - g_spk_vq_n0), (double)(g_bw_vq_q - g_spk_vq_q0) * qk, o ? subs : " none >= 0.5 ms", g_downed, psync_active());
}
static void stall_tick_end(void) {
    LARGE_INTEGER c; QueryPerformanceCounter(&c);
    g_stall_tick_q = g_stall_begin_q ? c.QuadPart - g_stall_begin_q : 0;
    g_stall_last_slow_q = g_stall_slow_q; g_stall_last_slow_nm = g_stall_slow_nm;
    if (g_stall_slow_q * 1000 >= 6 * g_stall_qf && match_substate() == 6) spike_emit(g_stall_tick_q);
    if (g_pl_counting && g_stall_tick_q * 1000 > 4 * g_stall_qf) g_pl_t4++;
    if (g_pl_counting) { g_pl_tk_sum += g_stall_tick_q; if (g_stall_tick_q > g_pl_tk_max) g_pl_tk_max = g_stall_tick_q; }
    if (g_pl_counting && g_pl_cyc0) { ULONG64 c1 = 0; QueryThreadCycleTime(GetCurrentThread(), &c1); if (c1 > g_pl_cyc0) g_pl_cyc_sum += c1 - g_pl_cyc0; }
    g_stall_in_tick = 0;
    g_stall_what = "(engine / render, between ticks)";
    g_stall_cpu_end = stall_cpu_now();
    g_stall_end_tid = GetCurrentThreadId();
}
