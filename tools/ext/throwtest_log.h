// ---------------------------------------------------------------- throwable test harness: structured log lines (DEV builds only)
// Included at the top of explosives2013.c. Every line starts with "throwtest:" and carries tms = GetTickCount64() (the two A/B instances
// share the machine clock, so tools/win/throwtest_report.py joins A's "sent" lines to B's lines by time). Release builds: all macros empty.
#ifndef T2R_RELEASE
static uint64_t g_tt_last_ms;                                     // last throwtest line of the target side (the target heal waits for quiet)
static struct { int reached, best; float ratio, dmg; } g_tt_res;
static void tt_res_reset(void) { memset(&g_tt_res, 0, sizeof g_tt_res); g_tt_res.best = -1; }
static const char *tt_kn(int kind) { return kind == 2 ? "molotov" : kind == 4 ? "placed" : kind == 5 ? "xbowarrow" : "nail"; }
static void tt_log_burst(int kind, int slot, const float *pos, const float *pl, float d, float reach, float scale) {
    g_tt_last_ms = GetTickCount64();
    xlog("throwtest: burst kind=%s slot=%d at=%.3f,%.3f,%.3f feet=%.3f,%.3f,%.3f dist=%.2f reach=%.2f scale=%.2f downed=%d tms=%llu", tt_kn(kind), slot,
         pos[0], pos[1], pos[2], pl[0], pl[1], pl[2], d, reach, scale, g_downed, (unsigned long long)g_tt_last_ms);
}
static void tt_log_result(int kind, int slot, const float *pos, const float *feet, float hp0, float hp1, float v0, float v1) {
    g_tt_last_ms = GetTickCount64();
    float dx = pos[0] - feet[0], dy = pos[1] - (feet[1] + 0.9f), dz = pos[2] - feet[2];
    xlog("throwtest: result kind=%s slot=%d dist=%.2f probes=%d/6 best=%d ratio=%.2f dmg_calc=%.0f hp_before=%.1f hp_after=%.1f vest_before=%.0f vest_after=%.0f downed=%d killed=%d tms=%llu",
         tt_kn(kind), slot, __builtin_sqrtf(dx * dx + dy * dy + dz * dz), g_tt_res.reached, g_tt_res.best, g_tt_res.ratio, g_tt_res.dmg, hp0, hp1, v0, v1, g_downed,
         hp1 <= 0.0f, (unsigned long long)g_tt_last_ms);
}
#define TT_LOG_BURST(kind, slot, pos, pl, d, reach, s) tt_log_burst((kind), (slot), (pos), (pl), (d), (reach), (s))
#define TT_LOG_FRIENDLY(kind, slot) xlog("throwtest: friendly kind=%s slot=%d tms=%llu", tt_kn(kind), (slot), (unsigned long long)GetTickCount64())
#define TT_NOTE_PROBES(r, b, ra) (g_tt_res.reached = (r), g_tt_res.best = (b), g_tt_res.ratio = (ra))
#define TT_NOTE_DMG(d) (g_tt_res.dmg = (d))
#define TT_LOG_FIRE(ticks, total, secs) do { g_tt_last_ms = GetTickCount64(); xlog("throwtest: fire ticks=%d dmg=%.1f secs=%.2f hp=%.1f tms=%llu", (ticks), (total), (secs), local_hp(), (unsigned long long)g_tt_last_ms); } while (0)
#else
#define TT_LOG_BURST(kind, slot, pos, pl, d, reach, s) ((void)0)
#define TT_LOG_FRIENDLY(kind, slot) ((void)0)
#define TT_NOTE_PROBES(r, b, ra) ((void)0)
#define TT_NOTE_DMG(d) ((void)0)
#define TT_LOG_FIRE(ticks, total, secs) ((void)0)
#endif
