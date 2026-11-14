// Offline harness for tools/ext/crashdiag.h.
//   gcc -std=gnu2x -O2 -o crashdiag_harness.exe crashdiag_harness.c        (MSYS2 UCRT64; no game, no windows.h)
//   crashdiag_harness.exe [image.bin]     checks the rings (wrap, order, fields), prints the per-event cost, and writes the raw block to image.bin
// tools/tests/test_crashdiag.py compiles + runs it, then parses image.bin with tools/reports/dumps.py (--ring-image) and compares.
#include <stdio.h>
#include <stdarg.h>
#include <stdlib.h>
#include <time.h>
#include "../ext/crashdiag.h"

static char g_out[1 << 16];
static size_t g_on;
static void lg(const char *fmt, ...) {
    va_list ap; va_start(ap, fmt);
    g_on += (size_t)vsnprintf(g_out + g_on, sizeof g_out - g_on, fmt, ap);
    va_end(ap);
    if (g_on < sizeof g_out - 1) g_out[g_on++] = '\n';
}
static const char *nm(uint64_t sid) { return sid == 0x1111 ? "kill-entity" : sid == 0x2222 ? "spawn-object" : "?"; }
static int fails;
#define CHECK(c) do { if (!(c)) { printf("FAIL %s:%d: %s\n", __FILE__, __LINE__, #c); fails++; } } while (0)
static double now_ns(void) { struct timespec t; timespec_get(&t, TIME_UTC); return t.tv_sec * 1e9 + t.tv_nsec; }

int main(int argc, char **argv) {
    g_cdiag.self = (uint64_t)&g_cdiag; g_cdiag.exe_base = 0x140000000ULL; g_cdiag.ext_base = 0x7ff800000000ULL;
    cd_be_add(0x1111); cd_be_add(0x2222); cd_be_add(0x1111);
    CHECK(cd_be_is(0x1111) && cd_be_is(0x2222) && !cd_be_is(0x3333) && !cd_be_is(0));
    // body events: wrap past CD_BE_N, newest first, the 'since' marker
    for (uint32_t i = 1; i <= CD_BE_N + 20; i++) cd_be_note(1000 + i, 5000 + i, 7, i & 1 ? 0x1111 : 0x2222, 0xA000 + i, i);
    CHECK(g_cdiag.be_i == CD_BE_N + 20);
    CHECK(g_cdiag.be[(CD_BE_N + 20) & (CD_BE_N - 1)].a0 == 0xA000 + CD_BE_N + 20);
    // compactions: one running while the report is made
    for (int i = 0; i < 70; i++) {
        uint64_t t0 = cd_cm_begin(2000 + i, 6000 + i, 3, 100 + i);
        cd_cm_end(t0, i % 10 == 0, 0x1000 + i, 0x1000 + i + (i % 10 == 0), 0x2000, 0x2000);
    }
    CHECK(g_cdiag.cm_calls == 70 && g_cdiag.cm_moves == 7 && !g_cdiag.cm_active && g_cdiag.cm_i == 70);
    cd_pup_note(3000, 7000, 3, CD_PUP_NEW, 1, 0, 0xCAFE0000, 0x77);
    cd_pup_note(3001, 7001, 3, CD_PUP_REG, 1, 0xCAFE0000, 0xBEEF0000, 9);
    uint64_t w[CD_HK_W];
    for (int s = 0; s < 40; s++) { for (int j = 0; j < CD_HK_W; j++) w[j] = 0x100 + j; w[5] = 1000 + s; cd_hk_put(4000 + 30 * s, 8000 + 500 * s, w); }
    CHECK(g_cdiag.hk_i == 40 && g_cdiag.hk[40 & (CD_HK_N - 1)].w[5] == 1039);
    uint64_t t0 = cd_cm_begin(9999, 9000, 3, 700);       // left running: "a compaction is running"
    (void)t0;
    cd_report(lg, nm, 9100);
    printf("%s", g_out);
    CHECK(strstr(g_out, "COMPACTION IS RUNNING"));
    CHECK(strstr(g_out, "world+028") && strstr(g_out, "CHANGED"));
    CHECK(strstr(g_out, "kill-entity") && strstr(g_out, "spawn-object"));
    CHECK(strstr(g_out, "attach table registered"));
    if (argc > 1) {         // the state the report above saw (the cost loops below overwrite the rings) + that report's text, for test_crashdiag.py
        FILE *f = fopen(argv[1], "wb");
        if (f) { fwrite(&g_cdiag, 1, sizeof g_cdiag, f); fclose(f); }
        char tp[1024]; snprintf(tp, sizeof tp, "%s.txt", argv[1]);
        f = fopen(tp, "wb");
        if (f) { fwrite(g_out, 1, g_on, f); fclose(f); }
    }
    // cost: the per-event writers
    enum { N = 20000000 };
    double a = now_ns();
    for (uint32_t i = 0; i < N; i++) cd_be_note(i, i, 1, 0x1111, i, i);
    double be_ns = (now_ns() - a) / N;
    a = now_ns();
    volatile int sink = 0;
    for (uint32_t i = 0; i < N; i++) sink += cd_be_is(0xDEADBEEF00ULL + i * 977);
    double is_ns = (now_ns() - a) / N;
    a = now_ns();
    for (uint32_t i = 0; i < 2000000; i++) { uint64_t t = cd_cm_begin(i, i, 1, i); cd_cm_end(t, 0, 1, 1, 2, 2); }
    double cm_ns = (now_ns() - a) / 2000000;
    a = now_ns();
    for (uint32_t i = 0; i < 2000000; i++) cd_hk_put(i, i, w);
    double hk_ns = (now_ns() - a) / 2000000;
    printf("COST ns/event: body event %.1f, set test (miss) %.1f, compaction begin+end %.1f, world sample (512 B) %.1f; block %u bytes\n", be_ns, is_ns, cm_ns, hk_ns, (unsigned)sizeof g_cdiag);
    CHECK(be_ns < 100 && is_ns < 50 && cm_ns < 200 && hk_ns < 500);
    printf("LAYOUT magic@0 self@%zu cm@%zu be@%zu hk@%zu pup@%zu cm_i@%zu be_i@%zu hk_i@%zu pup_i@%zu cm_active@%zu cm_frame@%zu size %zu\n", offsetof(t2r_cdiag_t, self),
           offsetof(t2r_cdiag_t, cm), offsetof(t2r_cdiag_t, be), offsetof(t2r_cdiag_t, hk), offsetof(t2r_cdiag_t, pup), offsetof(t2r_cdiag_t, cm_i), offsetof(t2r_cdiag_t, be_i),
           offsetof(t2r_cdiag_t, hk_i), offsetof(t2r_cdiag_t, pup_i), offsetof(t2r_cdiag_t, cm_active), offsetof(t2r_cdiag_t, cm_frame), sizeof g_cdiag);
    printf(fails ? "HARNESS FAILED (%d)\n" : "HARNESS OK\n", fails);
    return fails ? 1 : 0;
}
