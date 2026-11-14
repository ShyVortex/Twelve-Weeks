// memmap.c (dev tool, release + dev builds): once-per-match virtual-memory summary of THIS process, gated by t2r-memmap.txt next to the exe (absent = nothing runs,
// zero cost). Question it answers: what is the ~20 GB "private" of the "mem:" line made of, and how much of it is resident (working set).
// Why: live reports show private commit 19-24 GB on EVERY map (Hospital / Resort / Convention Center too, not only Bookstore); a read-only VirtualQueryEx walk of two
// running A/B clients split 19.3 GB private into: engine arena (one 514 GB reservation at 0x9000000000, 10.0 GB commit, RW) + 6.8 GB RW|WRITECOMBINE (64 MB blocks =
// GPU driver / D3D12 system-memory heaps) + 2.4 GB plain RW heaps; our own VirtualAlloc is 5 MB. winmm.dll (.t2rc blob, R--) and part1.dat are file-backed (mapped/image),
// not private. This file prints the same split from inside the process at known moments, so a run on any PC / map / menu can be compared.
// Output (xlog lines "memmap:"):
//   memmap: <label> totals: image C/R, mapped C/R, private C/R (MB), private by protection (RW / RW|WC / other), working set sampled per class
//   memmap: <label> top N allocation bases by commit: base, commit MB, reserve MB, type, resident MB (sampled, 1 page per 256 KB), owner (module / mapped file / "-")
// Labels: "menu" (once, ~60 s after boot, outside a match), "match+45s" (45 s into each match), "match end".
// The walk runs on a short-lived below-normal worker thread (a few thousand VirtualQuery calls, ~ms); it never touches the engine.
//
// Hook-up (tools/ext/t2r-ext.c, NOT edited by this commit):
//   1. next to  #include "mem_probe.c"  (line ~65378), after it:      #include "memmap.c"
//   2. in the per-frame tick list next to  PF(mem_probe_tick());  (line ~67067):   PF(memmap_tick());
// Needs from the includer (all exist in t2r-ext.c): xlog, exe_side_open, match_substate, g_frame, and <psapi.h> (K32GetProcessMemoryInfo is already used by mem_probe.c).
#define MM_TOP 20
#define MM_MAXBASES 4096
typedef struct { uint64_t base; uint64_t commit, reserve, res; DWORD type; DWORD prot_or; int wc; char owner[96]; } mm_ab;
static mm_ab g_mm_ab[MM_MAXBASES];
static volatile LONG g_mm_busy;
typedef struct { LONG label; } mm_arg;
static const char *const mm_labels[] = { "menu", "match+45s", "match end" };

static int mm_cmp(const void *a, const void *b) {
    uint64_t x = ((const mm_ab *)a)->commit + ((const mm_ab *)a)->reserve, y = ((const mm_ab *)b)->commit + ((const mm_ab *)b)->reserve;
    uint64_t cx = ((const mm_ab *)a)->commit, cy = ((const mm_ab *)b)->commit;
    return cx != cy ? (cx < cy) - (cx > cy) : (x < y) - (x > y);
}
static uint64_t mm_resident_sample(uint64_t base, uint64_t size, uint64_t *sampled_bytes) {   // 1 page per 256 KB: valid bit of QueryWorkingSetEx, scaled
    typedef struct { PVOID va; ULONG_PTR attr; } mm_wsx;
    typedef BOOL (WINAPI *fn_qws)(HANDLE, PVOID, DWORD);
    static fn_qws q; static int tried;
    if (!tried) { tried = 1; HMODULE k = GetModuleHandleA("kernel32.dll"); q = k ? (fn_qws)(void *)GetProcAddress(k, "K32QueryWorkingSetEx") : NULL; }
    if (!q || size < 0x40000) return 0;
    uint64_t n = size >> 18, hit = 0, done = 0;
    mm_wsx buf[256];
    for (uint64_t i = 0; i < n; ) {
        uint64_t c = n - i > 256 ? 256 : n - i;
        for (uint64_t j = 0; j < c; j++) { buf[j].va = (PVOID)(uintptr_t)(base + ((i + j) << 18)); buf[j].attr = 0; }
        if (!q(GetCurrentProcess(), buf, (DWORD)(c * sizeof buf[0]))) break;
        for (uint64_t j = 0; j < c; j++) if (buf[j].attr & 1) hit++;
        done += c; i += c;
    }
    *sampled_bytes += done << 18;
    return hit << 18;
}
static void mm_run(int label) {
    static const char *const T[] = { "image", "mapped", "private" };
    uint64_t c[3] = {0, 0, 0}, r[3] = {0, 0, 0}, pc_rw = 0, pc_wc = 0, pc_oth = 0, res[3] = {0, 0, 0}, smp[3] = {0, 0, 0};
    int nb = 0; uint64_t t0 = GetTickCount64();
    MEMORY_BASIC_INFORMATION m; uint8_t *a = NULL;
    memset(g_mm_ab, 0, sizeof g_mm_ab);
    while (VirtualQuery(a, &m, sizeof m) == sizeof m) {
        uint8_t *next = (uint8_t *)m.BaseAddress + m.RegionSize;
        if (m.State != MEM_FREE) {
            int ti = m.Type == MEM_IMAGE ? 0 : m.Type == MEM_MAPPED ? 1 : 2;
            int cm = m.State == MEM_COMMIT;
            if (cm) c[ti] += m.RegionSize; else r[ti] += m.RegionSize;
            uint64_t rs = cm ? mm_resident_sample((uint64_t)(uintptr_t)m.BaseAddress, m.RegionSize, &smp[ti]) : 0;
            res[ti] += rs;
            if (cm && ti == 2) { if (m.Protect & PAGE_WRITECOMBINE) pc_wc += m.RegionSize; else if ((m.Protect & 0xFF) == PAGE_READWRITE) pc_rw += m.RegionSize; else pc_oth += m.RegionSize; }
            uint64_t ab = (uint64_t)(uintptr_t)(m.AllocationBase ? m.AllocationBase : m.BaseAddress);
            int k = -1;
            for (int i = nb - 1; i >= 0 && i >= nb - 8; i--) if (g_mm_ab[i].base == ab) { k = i; break; }     // regions of one allocation are adjacent: look at the last few only
            if (k < 0) for (int i = 0; i < nb; i++) if (g_mm_ab[i].base == ab) { k = i; break; }
            if (k < 0 && nb < MM_MAXBASES) {
                k = nb++; g_mm_ab[k].base = ab; g_mm_ab[k].type = m.Type;
                if (m.Type != MEM_PRIVATE) {
                    char nm[MAX_PATH] = ""; DWORD n = GetMappedFileNameA(GetCurrentProcess(), m.BaseAddress, nm, sizeof nm);
                    if (n) { const char *s = strrchr(nm, '\\'); snprintf(g_mm_ab[k].owner, sizeof g_mm_ab[k].owner, "%s", s ? s + 1 : nm); }
                }
            }
            if (k >= 0) {
                if (cm) { g_mm_ab[k].commit += m.RegionSize; g_mm_ab[k].res += rs; if (m.Protect & PAGE_WRITECOMBINE) g_mm_ab[k].wc = 1; }
                else g_mm_ab[k].reserve += m.RegionSize;
                g_mm_ab[k].prot_or |= cm ? (m.Protect & 0xFF) : 0;
            }
        }
        if (next <= a) break;
        a = next;
        if ((uintptr_t)a >= 0x7FFFFFFF0000ull) break;
    }
    qsort(g_mm_ab, (size_t)nb, sizeof g_mm_ab[0], mm_cmp);
    const double MB = 1048576.0;
    char line[900]; int o = snprintf(line, sizeof line, "memmap: %s totals (MB commit/reserve, resident = sampled estimate):", mm_labels[label]);
    for (int i = 0; i < 3; i++) o += snprintf(line + o, sizeof line - (size_t)o, " %s %.0f/%.0f res~%.0f;", T[i], c[i] / MB, r[i] / MB, smp[i] ? res[i] / MB * ((double)c[i] / (double)smp[i]) : 0.0);
    o += snprintf(line + o, sizeof line - (size_t)o, " private commit by protection: RW %.0f, RW|WRITECOMBINE %.0f, other %.0f | %d allocation bases, walk %llu ms", pc_rw / MB, pc_wc / MB, pc_oth / MB, nb,
                  (unsigned long long)(GetTickCount64() - t0));
    xlog("%s", line);
    for (int i = 0; i < nb && i < MM_TOP; i++) {
        const mm_ab *b = &g_mm_ab[i];
        if (!b->commit && !b->reserve) break;
        xlog("memmap: %s #%d base %016llx commit %.0f MB reserve %.0f MB %s%s prot %02x resident~%.0f MB %s", mm_labels[label], i + 1, (unsigned long long)b->base, b->commit / MB, b->reserve / MB,
             b->type == MEM_IMAGE ? "image" : b->type == MEM_MAPPED ? "mapped" : "private", b->wc ? " write-combine" : "", (unsigned)b->prot_or, b->res / MB, b->owner[0] ? b->owner : "-");
    }
}
static DWORD WINAPI mm_worker(LPVOID arg) {
    SetThreadPriority(GetCurrentThread(), THREAD_PRIORITY_BELOW_NORMAL);
    mm_run((int)(intptr_t)arg);
    InterlockedExchange(&g_mm_busy, 0);
    return 0;
}
static void mm_launch(int label) {
    if (InterlockedCompareExchange(&g_mm_busy, 1, 0)) return;
    HANDLE t = CreateThread(NULL, 0, mm_worker, (LPVOID)(intptr_t)label, 0, NULL);
    if (t) CloseHandle(t); else InterlockedExchange(&g_mm_busy, 0);
}
static void memmap_tick(void) {
    static int on = -1, menu_done, was_in; static uint64_t in_at; static int plus_done;
    if (on < 0) {
        if (g_frame < 300) return;
        FILE *f = exe_side_open("t2r-memmap.txt", "r");
        on = f != NULL; if (f) { fclose(f); xlog("memmap: t2r-memmap.txt present - memory map summaries on (menu ~60 s after boot, match+45s, match end)"); }
    }
    if (!on) return;
    int in = match_substate() == 6;
    uint64_t now = GetTickCount64();
    if (in && !was_in) { in_at = now; plus_done = 0; }
    if (!in && was_in) mm_launch(2);
    was_in = in;
    if (in && !plus_done && now - in_at >= 45000) { plus_done = 1; mm_launch(1); }
    if (!in && !menu_done && g_frame > 3600) { menu_done = 1; mm_launch(0); }          // ~60 s at 60 fps, first time out of a match
}
