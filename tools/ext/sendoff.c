// ---------------------------------------------------------------- menu send-off
// re/menu-sendoff-impl-1115.md (research: re/menu-sendoff-1115.md). After the match-found war horn, over the faction menu
// scene (g_ms_cur 1 WLF stadium / 2 Seraphite island) a flock of birds flies away on screen with crow calls, then the
// faction's send-off runs into the black / loading screen: WLF vehicles driving off, Seraphites a pack of horses riding off.
// Timeline (ms from the horn sequence start, feature_match_horn's t; UI fade 0..MH_UI_MS 500, the horn at MH_HORN_MS 600).
// booster page gone -> every UI fades out -> war horn -> birds flock + crows -> transport -> fade to black
// -> loading screen fades in:
//   SO_CROWS_MS     crows + flock sound (SENDOFF_CROWS_PCM) and the birds take off (so_birds_go)
//   SO_FAC_MS       the faction clip (SENDOFF_WLF_PCM / SENDOFF_SER_PCM), ~1.4 s before the fade to black (MH_BLACK_MS 5200)
//   .. SO_FULL_MS   full (the clip's own fade-in is baked) into the fade to black
//   .. SO_FADE_MS   down to silent with the music fade, done by the level start release (MH_END_MS 7700; MH_MAX_MS 11 s cap)
// The clips are PCM through our mixer (tools/rip_sendoff.py -> sendoff_pcm.h): the game banks they come from are SP / level
// banks, silent in MP. The horn sequence dips the whole process session (MH_DIP_DB from t = 0) and fades it out from
// MH_BLACK_MS (session_volume, our mixer included): every voice's gain is driven every frame through mh_comp (wanted level /
// session volume, capped at MH_COMP_CAP): the crows stay full through the dip and go down with the black, the faction clip
// follows its own envelope (so_env).
// Birds (so_birds_go), per scene (SO_ROUTE, overridable for tests by t2r-sendoff-birds.txt):
//   SO_R_FLEE  the engine's own pigeon flocks: the Seraphite scene loads sle-scar-island-forest-trail-script (menu_scenes.py),
//              its FlockingBird spawners flee-sle-bird-lookout-* / -forest-* get send-event(force-flee, name) (the campaign's
//              scripts do the same), jittered 0..SO_FLEE_JIT ms; optional spawn-entity(name, 0, 0) first ("spawn 1")
//   SO_R_EXT   our own flock: SO_NB crow-t2 objects (spawn-object; the menu paks register the bird actors, menu_scenes.py
//              SENDOFF_ACTORS), takeoff then fly anims (animate_), moved every frame by set-object-locator: from below one side
//              third of the frame, SO_FAR_* m out, climbing away
//   SO_R_FX    the stadium's birds-flipbook particle group (part-level-fob-stadium-stands) spawned at points in front of the camera
// t2r-no-sendoff.txt = off (sound and birds). Log lines "sendoff:".
// TEST: t2r-sendoff-test.txt fires the whole sequence (horn, UI fade, birds, crows, send-off, fade to black, music fade) ~6 s
// after a faction scene is up on the menu, without any match (combine with t2r-menu-scene-test.txt 1 / 2 to force the scene).
// Its first word: "noblack" = no fade to black (screenshots of the birds), "repeat <s>" = again every <s> seconds.
#include "sendoff_pcm.h"
#define SO_CROWS_MS 2200     // horn (MH_HORN_MS 600) + 1.6 s: after its 1.2 s fade-in, at its loudest; the birds have 3.0 s on screen before the black (MH_BLACK_MS 5200)
#define SO_FAC_MS 3800       // transport (a little later): 1.4 s before the black (its 0.9 s fade-in baked: full at 4700)
#define SO_FULL_MS 5500      // full into the fade to black, then down with the music fade ..
#define SO_FADE_MS 7600      // .. silent by the music fade's end (MH_END_MS - 100; the level start at MH_END_MS 7700)
#define SO_FLEE_JIT 600
#define SO_NB 16
#define SO_FAR_WLF 24.0f     // the flock's distance from the menu camera (m): + 0..SO_FAR_SPREAD (38..52 m: lost in the fog / too small)
#define SO_FAR_SER 14.0f
#define SO_FAR_SPREAD 6.0f
enum { SO_R_NONE = 0, SO_R_FLEE = 1, SO_R_EXT = 2, SO_R_FX = 4 };
static const int SO_ROUTE[3] = {SO_R_NONE, SO_R_EXT, SO_R_EXT};    // both faction scenes: our own crow flock (engine FLEE pigeons = late + distant, test)
static int g_so_off = -1;
static struct {
    int on, scene, crows, fac, birds;
    uint64_t t_last;                     // last t seen (ms of the sequence)
    const int16_t *pcm; int n; float gain;
} g_so;
// bird state (both routes; the test harness reads t2r-sendoff-birds.txt at each go)
static struct {
    int route, n, spawn_first, live, scene;
    float far_m, spread_m;               // test overrides (far is a windef.h macro) (t2r-sendoff-birds.txt far / spread; 0 / -1 = SO_FAR_* / SO_FAR_SPREAD)
    char art[48], type[32], anim_takeoff[48], anim_fly[48];
    uint64_t go_ms;                      // GetTickCount64 at the go
    struct { uint64_t obj; float p[3], v[3], acc[3]; int delay, phase, anim_ms; uint64_t anim_at; } b[SO_NB];
    struct { uint64_t sid, at; char name[40]; } q[96]; int nq;       // pending force-flee events
} g_sob;
static int so_off(void) {
    if (g_so_off < 0) { FILE *f = exe_side_open("t2r-no-sendoff.txt", "r"); g_so_off = f != NULL; if (f) fclose(f); if (g_so_off) xlog("sendoff: off (t2r-no-sendoff.txt)"); }
    return g_so_off;
}
static uint32_t so_rng(void) { static uint32_t s = 0x9e3779b9u; s ^= s << 13; s ^= s >> 17; s ^= s << 5; return s; }
static float so_rf(void) { return (float)(so_rng() & 0xffffff) / (float)0x1000000; }
// the menu camera of the scene: position, forward / right / up unit vectors, vertical half-angle tangent
static void so_cam(int scene, float *c, float *f, float *r, float *u, float *th) {
    const float *d = MS_POSE[scene];
    float fx = d[3] - d[0], fy = d[4] - d[1], fz = d[5] - d[2], l = sqrtf(fx * fx + fy * fy + fz * fz);
    c[0] = d[0]; c[1] = d[1]; c[2] = d[2];
    f[0] = fx / l; f[1] = fy / l; f[2] = fz / l;
    // right = up(0,1,0) x forward ... with forward +Z, right = +X when looking down +Z: r = (f.z, 0, -f.x) normalised
    float rl = sqrtf(f[2] * f[2] + f[0] * f[0]);
    r[0] = -f[2] / rl; r[1] = 0; r[2] = f[0] / rl;        // (screen right; sign checked against the yaw convention below)
    u[0] = r[1] * f[2] - r[2] * f[1]; u[1] = r[2] * f[0] - r[0] * f[2]; u[2] = r[0] * f[1] - r[1] * f[0];
    if (u[1] < 0) { u[0] = -u[0]; u[1] = -u[1]; u[2] = -u[2]; r[0] = -r[0]; r[2] = -r[2]; }
    float fov = MS_FOV[scene] > 1.0f ? MS_FOV[scene] : 75.0f;
    *th = tanf(fov * 0.5f * 3.14159265f / 180.0f);
}
static uint64_t so_bf(const float *p, const float *q) {     // a bound frame (alloc-bound-frame copies the vectors)
    static __attribute__((aligned(16))) float tp[4], tq[4];
    memcpy(tp, p, 12); tp[3] = 1.0f; memcpy(tq, q, 16);
    uint64_t a[5] = {(uint64_t)tp, (uint64_t)tq, 0, 0, 0};
    uint64_t bf = dc_call(0x871ec52cc86b7427ULL /* alloc-bound-frame */, 5, a);
    return bf == ~0ULL ? 0 : bf;
}
static void so_quat_dir(const float *v, float *q) {          // forward (+Z) along v
    float h = sqrtf(v[0] * v[0] + v[2] * v[2]);
    float yaw = atan2f(v[0], v[2]) * 180.0f / 3.14159265f, pitch = -atan2f(v[1], h > 1e-4f ? h : 1e-4f) * 180.0f / 3.14159265f;
    mcam_quat(yaw, pitch, q);
}
static float so_anim_len(uint64_t ent, const char *anim) {
    uint64_t da[2] = {ent, fnv64(anim)};
    uint64_t r = dc_call(fnv64("get-animation-duration"), 2, da);
    float dur = 0; uint32_t lo = (uint32_t)r; memcpy(&dur, &lo, 4);
    return (r != ~0ULL && dur > 0.05f && dur < 30.0f) ? dur : 0.0f;
}
static void so_birds_kill(const char *why) {
    int k = 0;
    for (int i = 0; i < SO_NB; i++) if (g_sob.b[i].obj) { uint64_t o = g_sob.b[i].obj; if (live_proc(o)) dc_call(fnv64("kill-entity"), 1, &o); g_sob.b[i].obj = 0; k++; }
    if (k || g_sob.nq) xlog("sendoff: birds removed (%d objects, %d flee events dropped) - %s", k, g_sob.nq, why);
    g_sob.live = 0; g_sob.nq = 0;
}
// test overrides: t2r-sendoff-birds.txt, one "key value" per line: route flee|ext|fx|none (may repeat: flee+ext), n, art, type,
// takeoff, fly, spawn 0/1
static void so_birds_cfg(int scene) {
    g_sob.route = SO_ROUTE[scene]; g_sob.n = 14; g_sob.spawn_first = 0; g_sob.far_m = 0; g_sob.spread_m = -1;
    strcpy(g_sob.art, "crow-t2"); strcpy(g_sob.type, "SimpleObject");
    strcpy(g_sob.anim_takeoff, "takeoff-up-0-fast"); strcpy(g_sob.anim_fly, "fly-straight-panic");
    FILE *f = exe_side_open("t2r-sendoff-birds.txt", "r");
    if (!f) return;
    char k[32], v[48]; int routes = -1;
    while (fscanf(f, "%31s %47s", k, v) == 2) {
        if (!strcmp(k, "route")) {
            if (routes < 0) routes = 0;
            if (strstr(v, "flee")) routes |= SO_R_FLEE;
            if (strstr(v, "ext")) routes |= SO_R_EXT;
            if (strstr(v, "fx")) routes |= SO_R_FX;
        } else if (!strcmp(k, "n")) { int n = atoi(v); g_sob.n = n < 1 ? 1 : n > SO_NB ? SO_NB : n; }
        else if (!strcmp(k, "art")) snprintf(g_sob.art, sizeof g_sob.art, "%s", v);
        else if (!strcmp(k, "type")) snprintf(g_sob.type, sizeof g_sob.type, "%s", v);
        else if (!strcmp(k, "takeoff")) snprintf(g_sob.anim_takeoff, sizeof g_sob.anim_takeoff, "%s", v);
        else if (!strcmp(k, "fly")) snprintf(g_sob.anim_fly, sizeof g_sob.anim_fly, "%s", v);
        else if (!strcmp(k, "spawn")) g_sob.spawn_first = atoi(v);
        else if (!strcmp(k, "far")) g_sob.far_m = (float)atof(v);
        else if (!strcmp(k, "spread")) g_sob.spread_m = (float)atof(v);
    }
    fclose(f);
    if (routes >= 0) g_sob.route = routes;
    xlog("sendoff: birds config from t2r-sendoff-birds.txt: route %d, n %d, art %s, type %s, takeoff %s, fly %s, spawn %d", g_sob.route,
         g_sob.n, g_sob.art, g_sob.type, g_sob.anim_takeoff, g_sob.anim_fly, g_sob.spawn_first);
}
// the Seraphite trail flock (sle-scar-island-forest-trail-script): names of its FlockingBird spawners
static int so_flee_names(char out[][40], int cap) {
    int n = 0;
    for (int i = 1; i <= 63 && n < cap; i++) snprintf(out[n++], 40, "flee-sle-bird-lookout-%d", i);
    for (int i = 1; i <= 21 && n < cap; i++) snprintf(out[n++], 40, "flee-sle-bird-forest-%d", i);
    return n;
}
static float so_far(int scene) { return g_sob.far_m > 0.5f ? g_sob.far_m : scene == 1 ? SO_FAR_WLF : SO_FAR_SER; }
static float so_spread(void) { return g_sob.spread_m >= 0.0f ? g_sob.spread_m : SO_FAR_SPREAD; }
static void so_birds_go(int scene) {
    so_birds_kill("a new go");
    so_birds_cfg(scene);
    uint64_t now = GetTickCount64();
    g_sob.go_ms = now; g_sob.scene = scene;
    if (g_sob.route & SO_R_FLEE) {
        char nm[96][40];
        int n = so_flee_names(nm, 96), have = 0, alive = 0, spawned = 0;
        typedef uint8_t *(*fn_loc)(uint64_t);
        for (int i = 0; i < n; i++) {
            uint64_t sid = fnv64(nm[i]);
            uint8_t *l = ((fn_loc)VMA(0x18000ADB0))(sid);                 // the spawner exists (its level is loaded)
            if (!l || IsBadReadPtr(l, 8)) continue;
            have++;
            if (((uint8_t *(*)(uint64_t))VMA(0x18000A200))(sid)) alive++;
            if (g_sob.spawn_first) { uint64_t a[3] = {sid, 0, 0}; uint64_t r = dc_call(fnv64("spawn-entity"), 3, a); if (r && r != ~0ULL) spawned++; }
            if (g_sob.nq < 96) {
                g_sob.q[g_sob.nq].sid = sid; g_sob.q[g_sob.nq].at = now + (uint64_t)(so_rf() * SO_FLEE_JIT) + (g_sob.spawn_first ? 150 : 0);
                snprintf(g_sob.q[g_sob.nq].name, 40, "%s", nm[i]); g_sob.nq++;
            }
        }
        xlog("sendoff: birds FLEE: %d of %d trail flock spawners present, %d resolve as live objects, %d spawn-entity ok%s - force-flee queued (0..%d ms)",
             have, n, alive, spawned, g_sob.spawn_first ? "" : " (not asked)", SO_FLEE_JIT);
    }
    if (g_sob.route & SO_R_FX) {
        float c[3], f[3], r[3], u[3], th;
        so_cam(scene, c, f, r, u, &th);
        int ok = 0;
        for (int i = 0; i < 4; i++) {
            float d = 14.0f + 6.0f * (float)i, p[3], q[4] = {0, 0, 0, 1};
            for (int k = 0; k < 3; k++) p[k] = c[k] + f[k] * d + r[k] * ((float)i - 1.5f) * d * th * 0.4f - u[k] * d * th * 0.3f;
            uint64_t bf = so_bf(p, q);
            uint64_t a[3] = {fnv64("birds-flipbook"), bf, fnv64("none")};
            uint64_t rr = bf ? dc_call(fnv64("spawn-particles-at-bound-frame"), 3, a) : 0;
            if (rr && rr != ~0ULL) ok++;
            xlog("sendoff: birds FX: birds-flipbook at %.1f %.1f %.1f -> %llx", p[0], p[1], p[2], (unsigned long long)rr);
        }
        xlog("sendoff: birds FX: %d of 4 particle spawns returned a handle", ok);
    }
    if (g_sob.route & SO_R_EXT) {
        float c[3], f[3], r[3], u[3], th;
        so_cam(scene, c, f, r, u, &th);
        int ok = 0, anim_ok = 0;
        float lt = 0;
        // The first flock (a loose cluster rising from just below the bottom edge 4..7 m out, climbing away) was fine but
        // too close; wanted: somewhere from the side of the screen in the background (and behind the trees in the Seraphites menu case).
        // Same takeoff + climb-away motion, now SO_FAR_* m out and from one side third of the frame (Seraphites: the left, the big trunk - the
        // near trees cover the birds where they pass behind them; WLF: a random side), drifting towards the middle as they climb away.
        // The speeds scale with the distance (the screen motion of the old flock at ~5.5 m).
        int dir = scene == 2 ? 1 : (so_rf() < 0.5f ? 1 : -1);           // +1: from the left side (r = screen right)
        {   FILE *tf = exe_side_open("t2r-sendoff-birds.txt", "r");      // (test: "from left|right" in the same file)
            if (tf) { char k[32], v[48]; while (fscanf(tf, "%31s %47s", k, v) == 2) if (!strcmp(k, "from")) dir = strcmp(v, "right") ? 1 : -1; fclose(tf); } }
        for (int i = 0; i < g_sob.n; i++) {
            float d = so_far(scene) + so_spread() * so_rf(), ks = sqrtf(d / 5.5f);    // (screen speed falls off with the distance, not all the way)
            float hw = d * th * (16.0f / 9.0f);
            float lat = -(float)dir * (0.45f + 0.35f * so_rf()) * hw, hgt = -(1.04f + 0.10f * so_rf()) * d * th;
            float up = (3.2f + 1.0f * so_rf()) * ks, fw = (3.5f + 2.0f * so_rf()) * ks, sd = (float)dir * (1.2f + 1.2f * so_rf()) * ks;
            for (int k = 0; k < 3; k++) {
                g_sob.b[i].p[k] = c[k] + f[k] * d + r[k] * lat + u[k] * hgt;
                g_sob.b[i].v[k] = f[k] * fw + u[k] * up + r[k] * sd;
                g_sob.b[i].acc[k] = (f[k] * (2.5f + so_rf()) - u[k] * (1.2f + 0.4f * so_rf()) + r[k] * sd * 0.3f) * ks;
            }
            g_sob.b[i].delay = (int)(so_rf() * 450.0f);
            g_sob.b[i].phase = 0; g_sob.b[i].anim_at = 0; g_sob.b[i].anim_ms = 0;
            uint64_t a[9] = {fnv64(g_sob.art), fnv64(g_sob.type), 0, 0, 1, 0, 0, 0, 0};
            uint64_t o = dc_call(fnv64("spawn-object"), 9, a);
            if ((!o || o == ~0ULL) && i == 0 && strcmp(g_sob.type, "SimpleAttachable")) {     // (the type the ext's props use)
                xlog("sendoff: birds EXT: spawn-object %s as %s failed - SimpleAttachable instead", g_sob.art, g_sob.type);
                strcpy(g_sob.type, "SimpleAttachable");
                a[1] = fnv64(g_sob.type);
                o = dc_call(fnv64("spawn-object"), 9, a);
            }
            if (!o || o == ~0ULL) { g_sob.b[i].obj = 0; continue; }
            g_sob.b[i].obj = o; ok++;
            float q[4]; so_quat_dir(g_sob.b[i].v, q);
            uint64_t bf = so_bf(g_sob.b[i].p, q);
            if (bf) { uint64_t la[2] = {o, bf}; dc_call(fnv64("set-object-locator"), 2, la); }
            if (i == 0) lt = so_anim_len(o, g_sob.anim_takeoff);
            uint64_t ar = animate_now(o, g_sob.anim_takeoff);
            if (ar && ar != ~0ULL) anim_ok++;
        }
        g_sob.live = ok > 0;
        xlog("sendoff: birds EXT: %d of %d %s (%s) spawned on the %s side, %.0f..%.0f m out, takeoff '%s' %.2f s long, animate_ ok on %d - camera %.1f %.1f %.1f fwd %.2f %.2f %.2f",
             ok, g_sob.n, g_sob.art, g_sob.type, dir > 0 ? "left" : "right", so_far(scene), so_far(scene) + so_spread(),
             g_sob.anim_takeoff, lt, anim_ok, c[0], c[1], c[2], f[0], f[1], f[2]);
    }
}
// every frame: pending flee events, our own birds' flight
static void so_birds_tick(void) {
    uint64_t now = GetTickCount64();
    if (g_sob.nq) {
        int sent = 0, ok = 0;
        for (int i = 0; i < g_sob.nq;) {
            if (now < g_sob.q[i].at) { i++; continue; }
            uint64_t a[2] = {fnv64("force-flee"), g_sob.q[i].sid};
            uint64_t r = dc_call(fnv64("send-event"), 2, a);
            sent++; if (r && r != ~0ULL) ok++;
            static int nl; if (LOGCAP(nl, 12)) xlog("sendoff: force-flee %s -> %llx", g_sob.q[i].name, (unsigned long long)r);
            g_sob.q[i] = g_sob.q[--g_sob.nq];
        }
        (void)ok; (void)sent;
    }
    if (!g_sob.live) return;
    float el = (float)(now - g_sob.go_ms) / 1000.0f;
    static uint64_t last; float dt = last && now > last ? (float)(now - last) / 1000.0f : 1.0f / 60.0f; last = now;
    if (dt > 0.1f) dt = 0.1f;
    int alive = 0;
    for (int i = 0; i < g_sob.n; i++) {
        if (!g_sob.b[i].obj) continue;
        if (!live_proc(g_sob.b[i].obj)) { g_sob.b[i].obj = 0; continue; }
        alive++;
        float bt = el - g_sob.b[i].delay / 1000.0f;
        if (bt < 0) continue;                                       // still sitting (staggered takeoff)
        for (int k = 0; k < 3; k++) {
            float wob = (k == 1 ? 0.6f : 0.35f) * sinf(bt * (5.0f + (float)(i % 5)) + (float)i * 1.7f);
            g_sob.b[i].v[k] += (g_sob.b[i].acc[k] + wob) * dt;
        }
        {   // never dive: the climb (along the camera's up) levels off at >= 0.15 m/s
            float c0[3], f0[3], r0[3], u0[3], th0; so_cam(g_sob.scene, c0, f0, r0, u0, &th0);
            float vu = g_sob.b[i].v[0] * u0[0] + g_sob.b[i].v[1] * u0[1] + g_sob.b[i].v[2] * u0[2];
            if (vu < 0.15f) for (int k = 0; k < 3; k++) g_sob.b[i].v[k] += (0.15f - vu) * u0[k];
        }
        for (int k = 0; k < 3; k++) g_sob.b[i].p[k] += g_sob.b[i].v[k] * dt;
        float q[4]; so_quat_dir(g_sob.b[i].v, q);
        uint64_t bf = so_bf(g_sob.b[i].p, q);
        if (bf) { uint64_t la[2] = {g_sob.b[i].obj, bf}; dc_call(fnv64("set-object-locator"), 2, la); }
        uint64_t ms = (uint64_t)(bt * 1000.0f);
        if (g_sob.b[i].phase == 0 && ms > 700) {                     // takeoff done: the fly cycle (re-issued at its end)
            g_sob.b[i].phase = 1; g_sob.b[i].anim_at = now;
            float l = so_anim_len(g_sob.b[i].obj, g_sob.anim_fly); g_sob.b[i].anim_ms = l > 0.1f ? (int)(l * 1000.0f) : 600;
            animate_now(g_sob.b[i].obj, g_sob.anim_fly);
        } else if (g_sob.b[i].phase == 1 && now - g_sob.b[i].anim_at >= (uint64_t)g_sob.b[i].anim_ms) {
            g_sob.b[i].anim_at = now; animate_now(g_sob.b[i].obj, g_sob.anim_fly);
        }
    }
    static uint64_t lg;
    if (now - lg > 1000 && el < 7.0f) {
        lg = now;
        int i0 = -1; for (int i = 0; i < g_sob.n && i0 < 0; i++) if (g_sob.b[i].obj) i0 = i;
        if (i0 >= 0) {
            float c0[3], f0[3], r0[3], u0[3], th0; so_cam(g_sob.scene, c0, f0, r0, u0, &th0);
            float q[3] = {g_sob.b[i0].p[0] - c0[0], g_sob.b[i0].p[1] - c0[1], g_sob.b[i0].p[2] - c0[2]};
            float dz = q[0] * f0[0] + q[1] * f0[1] + q[2] * f0[2], dx = q[0] * r0[0] + q[1] * r0[1] + q[2] * r0[2], dy = q[0] * u0[0] + q[1] * u0[1] + q[2] * u0[2];
            xlog("sendoff: birds EXT t %.1f s: %d alive, bird %d at %.1f %.1f %.1f - %.1f m out, screen x %.2f y %.2f of the half frame (vertical fov, 16:9)", el, alive, i0,
                 g_sob.b[i0].p[0], g_sob.b[i0].p[1], g_sob.b[i0].p[2], dz, dz > 0.1f ? dx / (dz * th0 * (16.0f / 9.0f)) : 0.0f, dz > 0.1f ? dy / (dz * th0) : 0.0f);
        }
    }
    if (el > 8.0f || !alive) so_birds_kill(alive ? "flight over" : "all gone");
}
// --- the sound + bird timeline, driven by feature_match_horn (or the test) ---
static void so_start(int scene) {
    memset(&g_so, 0, sizeof g_so);
    if (so_off() || (scene != 1 && scene != 2)) return;
    g_so.on = 1; g_so.scene = scene;
    if (scene == 1) { g_so.pcm = SENDOFF_WLF_PCM; g_so.n = (int)(sizeof SENDOFF_WLF_PCM / sizeof SENDOFF_WLF_PCM[0]); g_so.gain = SENDOFF_GAIN_WLF; }
    else { g_so.pcm = SENDOFF_SER_PCM; g_so.n = (int)(sizeof SENDOFF_SER_PCM / sizeof SENDOFF_SER_PCM[0]); g_so.gain = SENDOFF_GAIN_SER; }
    xlog("sendoff: armed (%s): crows at %d ms, %s at %d ms, full %d..%d ms, silent by %d ms", MS_SCENE[scene].name, SO_CROWS_MS,
         scene == 1 ? "vehicles" : "horses", SO_FAC_MS, SO_FAC_MS + 900, SO_FULL_MS, SO_FADE_MS);
}
static float so_env(uint64_t t) {          // the effective level of the faction clip (after the session volume)
    if (t < SO_FULL_MS) return 1.0f;
    if (t >= SO_FADE_MS) return 0.0f;
    float x = (float)(SO_FADE_MS - t) / (float)(SO_FADE_MS - SO_FULL_MS);
    return x * x;
}
static void so_tick(uint64_t t) {
    if (!g_so.on) return;
    g_so.t_last = t;
    if (!g_so.crows && t >= SO_CROWS_MS) {
        g_so.crows = 1;
        int ok = pcm_play_rate(SENDOFF_CROWS_PCM, (int)(sizeof SENDOFF_CROWS_PCM / sizeof SENDOFF_CROWS_PCM[0]), SENDOFF_GAIN_CROWS * mh_comp(mh_blackfade(t)), SENDOFF_RATE);
        xlog("sendoff: crows %s at %llu ms (gain %.3f x%.2f through the music dip)", ok ? "playing" : "NOT played (mixer unavailable / all voices busy)", (unsigned long long)t,
             SENDOFF_GAIN_CROWS, (double)mh_comp(mh_blackfade(t)));
        so_birds_go(g_so.scene);
        g_so.birds = 1;
    } else if (g_so.crows == 1) pcm_voice_ctl(SENDOFF_CROWS_PCM, SENDOFF_GAIN_CROWS * mh_comp(mh_blackfade(t)), 0);   // full through the dip, down with the black
    float sess = g_sess_vol < 0 ? 1.0f : (float)g_sess_vol / 65535.0f;
    float comp = mh_comp(so_env(t));
    if (!g_so.fac && t >= SO_FAC_MS) {
        g_so.fac = 1;
        int ok = pcm_play_rate(g_so.pcm, g_so.n, g_so.gain * comp, SENDOFF_RATE);
        xlog("sendoff: %s %s at %llu ms (gain %.3f, session %.2f)", g_so.scene == 1 ? "vehicles" : "horses",
             ok ? "playing" : "NOT played (mixer unavailable / all voices busy)", (unsigned long long)t, g_so.gain, sess);
    } else if (g_so.fac == 1) {
        pcm_voice_ctl(g_so.pcm, g_so.gain * comp, 0);
        static uint64_t lg;
        if (t - lg >= 500 || t < lg) { lg = t; xlog("sendoff: %llu ms: session %.2f, envelope %.2f, voice gain x%.2f", (unsigned long long)t, sess, so_env(t), comp); }
        if (t >= SO_FADE_MS) { g_so.fac = 2; pcm_voice_ctl(g_so.pcm, 0.0f, 60); xlog("sendoff: send-off faded out at %llu ms", (unsigned long long)t); }
    }
}
static void so_stop(const char *why, int fade_ms, int kill_birds) {
    if (!g_so.on) return;
    int a = pcm_voice_ctl(SENDOFF_CROWS_PCM, -1.0f, fade_ms), b = g_so.pcm ? pcm_voice_ctl(g_so.pcm, -1.0f, fade_ms) : 0;
    g_so.crows = 2;
    if (kill_birds) so_birds_kill(why);
    xlog("sendoff: stopped at %llu ms - %s (%d voices faded over %d ms)", (unsigned long long)g_so.t_last, why, a + b, fade_ms);
    g_so.on = 0;
}
// every frame (after feature_match_horn): the birds, the TEST trigger
static void feature_sendoff(void) {
    so_birds_tick();
    static int test = -1, noblack, repeat_s;
    static int st, scene_seen = -1;
    static uint64_t scene_at, t0, next_at, black;
    uint64_t now = GetTickCount64();
    if (test < 0) {
        FILE *f = exe_side_open("t2r-sendoff-test.txt", "r");
        test = f != NULL;
        if (f) {
            char w[32]; int n;
            while (fscanf(f, "%31s", w) == 1) { if (!strcmp(w, "noblack")) noblack = 1; else if (!strcmp(w, "repeat") && fscanf(f, "%d", &n) == 1) repeat_s = n; }
            fclose(f);
            xlog("sendoff: TEST on (t2r-sendoff-test.txt%s%s): the whole sequence ~6 s after a faction scene is up", noblack ? ", no black" : "",
                 repeat_s ? ", repeating" : "");
        }
    }
    if (!test) return;
    int sc = (ms_on_menu() && !ms_switching()) ? g_ms_cur : -1;
    if (sc != scene_seen) {
        scene_seen = sc; scene_at = now; next_at = now + 6000;
        if (st) { so_stop("TEST: scene changed", 200, 1); session_volume(1.0f); if (black) fade_to_black(0.0f, 0.0f, 0.5f); w_alpha(ui_w("anim-group"), 1.0f); st = 0; }
        if (sc == 1 || sc == 2) xlog("sendoff: TEST: scene %s up - sequence in 6 s", MS_SCENE[sc].name);
    }
    if (sc != 1 && sc != 2) return;
    if (!st) {
        if (!next_at || now < next_at || g_mh_st) return;
        st = 1; t0 = now; black = 0; next_at = 0;
        xlog("sendoff: TEST: sequence start (%s)", MS_SCENE[sc].name);
        so_start(sc);
        return;
    }
    uint64_t t = now - t0;
    if (t < MH_UI_MS + 3000) w_alpha(ui_w("anim-group"), t >= MH_UI_MS ? 0.0f : 1.0f - (float)t / MH_UI_MS);
    if (t < MH_END_MS) session_volume(mh_duck(t) * mh_blackfade(t));     // the music dip + fade (feature_match_horn)
    if (st == 1 && t >= MH_HORN_MS) {
        st = 2;
        int ok = pcm_play_rate(MATCH_HORN_PCM, (int)(sizeof MATCH_HORN_PCM / sizeof MATCH_HORN_PCM[0]), 0.9f * mh_comp(mh_blackfade(t)), MATCH_HORN_RATE);
        xlog("sendoff: TEST: horn %s", ok ? "playing" : "NOT played");
    } else if (st == 2) pcm_voice_ctl(MATCH_HORN_PCM, 0.9f * mh_comp(mh_blackfade(t)), 0);
    so_tick(t);
    if (!noblack && !black && t >= MH_BLACK_MS) { black = now; fade_to_black(MH_BLACK_FADE, 2.0f, 0.0f); xlog("sendoff: TEST: fading to black"); }
    else if (black && t < MH_END_MS + 1500 && now > black + 1500) { fade_to_black(0.0f, 1.0f, 0.0f); black = now; }
    if (st == 2 && t >= MH_END_MS) {
        st = 3;
        so_stop("TEST: level start point (MH_END_MS)", 200, !noblack);
        session_volume(1.0f);
        xlog("sendoff: TEST: release point - session volume back to 1");
    }
    if (st == 3 && t >= MH_END_MS + 1500) {
        if (black) fade_to_black(0.0f, 0.0f, 0.5f);
        w_alpha(ui_w("anim-group"), 1.0f);
        xlog("sendoff: TEST: done%s", repeat_s ? "" : " (once per scene; re-enter the scene or set 'repeat <s>')");
        st = 0;
        if (repeat_s) next_at = now + (uint64_t)repeat_s * 1000;
    }
    (void)scene_at;
}
