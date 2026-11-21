// levelcull.c (re/perf-1116.md): per-map runtime level hides for frame rate. Included by t2r-ext.c, called every tick.
// Supermarket and Bookstore load the whole SP / Part I level set of their area; some loaded levels are never seen from inside the play
// box (measured on A/B with perftest.c: hidden one at a time at fixed camera views, screenshot diff + perfwin frame time). Those are hidden
// with the engine's own set-level-visible(level, #f) once the map's level is loaded, and re-asserted every 2 s.
// Only render visibility changes: the level stays loaded (memory is a level-set change, data build). Opt-out: t2r-no-level-cull.txt.
typedef struct { const char *map_level; const char *const *hide; } lc_map;
static const char *const LC_SUPERMARKET[] = { NULL };
static const char *const LC_BOOKSTORE[] = { NULL };
static const lc_map LC_MAPS[] = {
    {"to1-pvp-jackson-market", LC_SUPERMARKET},
    {"to1-pvp-p1-bookstore", LC_BOOKSTORE},
};
#define LC_NMAPS ((int)(sizeof LC_MAPS / sizeof *LC_MAPS))
static int g_lc_map = -1;

static void lc_apply(int m, int vis) {
    int n = 0;
    for (const char *const *l = LC_MAPS[m].hide; *l; l++, n++) {
        uint64_t a[2] = {fnv64(*l), (uint64_t)(vis ? 1 : 0)};
        dc_call(fnv64("set-level-visible"), 2, a);
    }
    static int nl; if (nl < 12 && n) { nl++; xlog("level cull: %s %d levels of %s", vis ? "showed" : "hid", n, LC_MAPS[m].map_level); }
}

static void levelcull_tick(int in_match) {
    static unsigned fr; static uint64_t last; static int off_v = -1; static uint64_t off_a;
    if (!in_match) { g_lc_map = -1; fr = 0; return; }
    if (feel_flag("t2r-no-level-cull.txt", &off_a, &off_v, 120)) { if (g_lc_map >= 0) lc_apply(g_lc_map, 1); g_lc_map = -1; return; }
    if (g_lc_map < 0 && (fr++ % 60) == 0) {
        for (int m = 0; m < LC_NMAPS; m++) {
            if (!LC_MAPS[m].hide[0]) continue;
            uint64_t sid = fnv64(LC_MAPS[m].map_level), l = dc_call(fnv64("is-level-loaded?"), 1, &sid);
            if (l && l != ~0ULL) { g_lc_map = m; last = 0; break; }
        }
    }
    if (g_lc_map < 0) return;
    uint64_t now = GetTickCount64();
    if (now - last >= 2000) { last = now; lc_apply(g_lc_map, 0); }
}
