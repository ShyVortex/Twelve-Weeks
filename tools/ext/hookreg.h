// hookreg.h - one registry of every code / data patch the ext writes into an image (tests/test_hook_overlap.py).
// Why: install_sendevent_hook patched the winmm function install_send_hook also patches; the second installer's prologue check
// failed ('send hook: prologue mismatch, not installed') and a build shipped with every ext peer message silently disabled.
// How: t2r_vprot() (a VirtualProtect wrapper, #defined over VirtualProtect right after this header) calls hr_note() for every call that
// makes an IMAGE range writable (exe / winmm / any dll: the stubs and heap objects are private memory and not tracked). hr_note logs
// "HOOK CONFLICT" (once per installer pair) when another installer already patched an overlapping range. The prologue-check failures use
// hook_miss(): "HOOK CONFLICT" when the bytes are already patched by an earlier installer, else "HOOK FAIL" (other exe build / unknown). Both
// prefixes are greppable and make tools/tests/ab_asserts.py FAIL. A re-patch of a range by the SAME function (toggles) is not a conflict.
// Needs before inclusion: <windows.h>, <stdint.h>, <stdio.h>, <stdarg.h>, <string.h>, xlog(), g_xlog_nolimit.
#ifndef T2R_HOOKREG_H
#define T2R_HOOKREG_H
#define HR_MAX 1024
typedef struct { uintptr_t lo, hi; const char *who; } hr_ent;
static hr_ent g_hr[HR_MAX];
static int g_hr_n, g_hr_conf, g_hr_fail, g_hr_over;
static volatile LONG g_hr_lk;
#define HR_LOG_MAX 200
static int g_hr_logged;
// intentional chains: {installer A, installer B} patching overlapping bytes ON PURPOSE (B wraps / re-patches A). None today: tests/test_hook_overlap.py
// has the static allow-list for the pairs that exist in the source, keep both in step.
static const char *const HR_ALLOW[][2] = { {"", ""} };
static int hr_allowed(const char *a, const char *b) {
    for (int i = 0; HR_ALLOW[i][0][0]; i++)
        if ((!strcmp(HR_ALLOW[i][0], a) && !strcmp(HR_ALLOW[i][1], b)) || (!strcmp(HR_ALLOW[i][0], b) && !strcmp(HR_ALLOW[i][1], a))) return 1;
    return 0;
}
static void hr_lock(void) { for (int i = 0; InterlockedCompareExchange(&g_hr_lk, 1, 0) != 0; i++) { if (i > 100000) return; YieldProcessor(); } }
static void hr_unlock(void) { InterlockedExchange(&g_hr_lk, 0); }
static void hr_say(const char *fmt, ...) {
    if (g_hr_logged >= HR_LOG_MAX) return;
    g_hr_logged++;
    char b[700];
    va_list ap; va_start(ap, fmt); vsnprintf(b, sizeof b, fmt, ap); va_end(ap);
    int was = g_xlog_nolimit; g_xlog_nolimit = 1;     // (the release rate limiter keys on the format pointer: these lines are few and must all be written)
    xlog("%s", b);
    g_xlog_nolimit = was;
}
// first registered range overlapping [lo, hi) from another installer (any installer when who == NULL); skips allow-listed pairs
static int hr_find(uintptr_t lo, uintptr_t hi, const char *who, hr_ent *out) {
    int hit = 0;
    for (int i = 0; i < g_hr_n && !hit; i++)
        if (g_hr[i].lo < hi && lo < g_hr[i].hi && (!who || !hr_allowed(g_hr[i].who, who))) { *out = g_hr[i]; hit = 1; }
    return hit;
}
// has this installer already recorded exactly this range? (a repeated patch of the same bytes: the caller skips the image query)
static int hr_have(const void *p, size_t n, const char *who) {
    uintptr_t lo = (uintptr_t)p, hi = lo + n; int r = 0;
    hr_lock();
    for (int i = 0; i < g_hr_n && !r; i++) if (g_hr[i].lo == lo && g_hr[i].hi == hi && !strcmp(g_hr[i].who, who)) r = 1;
    hr_unlock();
    return r;
}
// an installer is about to write [p, p+n): record it, report an overlap with another installer's range (once per pair)
static void hr_note(const void *p, size_t n, const char *who) {
    uintptr_t lo = (uintptr_t)p, hi = lo + n;
    if (!n || hi < lo) return;
    hr_ent o = {0, 0, NULL};
    int hit = 0, dup = 0;
    hr_lock();
    for (int i = 0; i < g_hr_n; i++) {
        if (g_hr[i].lo < hi && lo < g_hr[i].hi) {
            if (!strcmp(g_hr[i].who, who)) { dup = 1; continue; }        // the same function again (toggle / second site): fine
            if (!hr_allowed(g_hr[i].who, who) && !hit) { o = g_hr[i]; hit = 1; }
        }
    }
    int exact = 0;
    for (int i = 0; i < g_hr_n; i++) if (g_hr[i].lo == lo && g_hr[i].hi == hi && !strcmp(g_hr[i].who, who)) exact = 1;
    if (!exact) { if (g_hr_n < HR_MAX) g_hr[g_hr_n++] = (hr_ent){lo, hi, who}; else g_hr_over++; }
    if (hit) g_hr_conf++;
    hr_unlock();
    (void)dup;
    if (hit) hr_say("HOOK CONFLICT: %s patches %p+%u but %s already patched %p+%u (two installers on the same bytes: the second one's prologue check fails or it corrupts the first)",
                    who, (void *)lo, (unsigned)n, o.who, (void *)o.lo, (unsigned)(o.hi - o.lo));
}
// a prologue / signature check failed at [p, p+n): HOOK CONFLICT when an earlier installer already patched those bytes, else HOOK FAIL
static void hook_miss_(const void *p, size_t n, const char *who, const char *fmt, ...) {
    char msg[500];
    va_list ap; va_start(ap, fmt); vsnprintf(msg, sizeof msg, fmt, ap); va_end(ap);
    hr_ent o = {0, 0, NULL};
    int hit = 0;
    if (p && n) { hr_lock(); hit = hr_find((uintptr_t)p, (uintptr_t)p + n, who, &o); g_hr_fail++; if (hit) g_hr_conf++; hr_unlock(); }
    else { hr_lock(); g_hr_fail++; hr_unlock(); }
    if (hit) hr_say("HOOK CONFLICT: %s: %s [bytes %p+%u were already patched by %s (%p+%u) - installer order / overlap]", who, msg, p, (unsigned)n, o.who, (void *)o.lo, (unsigned)(o.hi - o.lo));
    else hr_say("HOOK FAIL: %s", msg);
    if (strstr(msg, "stub memory") || strstr(msg, "cave memory") || strstr(msg, "within reach") || strstr(msg, "rel32"))
        hr_say("!!!!!! STUB POOL: a hook could not get memory within rel32 reach (%s) - the winmm .t2rstub section is missing/full or the exe pool failed; see 'stub pool:' lines", who);
}
static void hr_summary(void) { hr_say("HOOK registry: %d patched range(s) recorded, %d conflict(s), %d failed check(s)%s", g_hr_n, g_hr_conf, g_hr_fail, g_hr_over ? " (table full)" : ""); }
#define hook_miss(p, n, ...) hook_miss_((p), (size_t)(n), __func__, __VA_ARGS__)
#define hook_fail(...) hook_miss_(NULL, 0, __func__, __VA_ARGS__)
#endif
