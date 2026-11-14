// Offline check of tools/ext/hookreg.h (the ext's hook registry): compiled and run by test_hook_overlap.py
#include <windows.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <stdarg.h>
static int g_xlog_nolimit;
static char g_out[64][700]; static int g_nout;
static void xlog(const char *fmt, ...) { va_list ap; va_start(ap, fmt); vsnprintf(g_out[g_nout < 63 ? g_nout : 63], 700, fmt, ap); va_end(ap); g_nout++; }
#include "../ext/hookreg.h"
static int fails;
#define CHECK(c, what) do { if (!(c)) { printf("FAIL %s\n", what); fails++; } else printf("ok   %s\n", what); } while (0)
static void a_installer(uint8_t *f) { hr_note(f, 16, __func__); }
static void b_installer(uint8_t *f) { hr_note(f + 8, 16, __func__); }
static void c_installer(uint8_t *f) { hr_note(f + 64, 8, __func__); hr_note(f + 64, 8, __func__); }
static void d_check(uint8_t *f) { hook_miss(f + 4, 4, "d hook: prologue mismatch, not installed"); }
static void e_check(uint8_t *f) { hook_miss(f + 200, 4, "e hook: prologue mismatch, not installed (%d)", 7); }
int main(void) {
    static uint8_t img[512];
    a_installer(img);
    CHECK(g_nout == 0, "first installer: no line");
    b_installer(img);
    CHECK(g_nout == 1 && !strncmp(g_out[0], "HOOK CONFLICT: b_installer patches", 34) && strstr(g_out[0], "a_installer already patched"), "overlapping second installer: HOOK CONFLICT naming both");
    c_installer(img);
    CHECK(g_nout == 1 && g_hr_n == 3, "same installer twice on one range, disjoint range: no conflict, one entry each");
    d_check(img);
    CHECK(g_nout == 2 && !strncmp(g_out[1], "HOOK CONFLICT: d_check: d hook: prologue mismatch", 49), "prologue check on already-patched bytes: HOOK CONFLICT");
    e_check(img);
    CHECK(g_nout == 3 && !strcmp(g_out[2], "HOOK FAIL: e hook: prologue mismatch, not installed (7)"), "prologue check on untouched bytes: HOOK FAIL <msg>");
    hook_fail("f hook: %s", "no stub memory");
    CHECK(g_nout == 4 && !strcmp(g_out[3], "HOOK FAIL: f hook: no stub memory"), "hook_fail: HOOK FAIL prefix");
    CHECK(g_hr_conf == 2 && g_hr_fail == 3, "counters");
    hr_summary();
    CHECK(strstr(g_out[4], "HOOK registry: 3 patched range(s) recorded, 2 conflict(s), 3 failed check(s)") != NULL, "summary line");
    return fails ? 1 : 0;
}
