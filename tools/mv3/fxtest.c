// fxtest.c - offline check of mv3_fx.c's rollback dedupe / cancel / grace logic (no engine: every helper is a recording stub).
// Build + run (from tools/mv3):  gcc -std=gnu2x -O1 -Wall -I../ext fxtest.c -o fxtest.exe && ./fxtest.exe
#include <stdio.h>
#include <stdint.h>
#include <string.h>
#include <stdarg.h>
#define T2R_MAX_PEERS 8
#define SID_PLAYER 0x4580fab03b7eb9c0ULL
#define INVALID_FILE_ATTRIBUTES 0xffffffffu
#define VXE_GIVE 1
#define VXE_PAIN 2
#define EXS_PIPE_WHOOSH 7
static int g_debug_mode = 1;
#define LOGCAP(c, n) ((c)++ < (n) || g_debug_mode)
static uint64_t g_now = 100000;
#define GetTickCount64() g_now
static unsigned GetFileAttributesA(const char *f) { (void)f; return INVALID_FILE_ATTRIBUTES; }
static int IsBadReadPtr(const void *p, size_t n) { (void)p; (void)n; return 1; }
static void xlog(const char *f, ...) { va_list a; va_start(a, f); printf("  [%6llu] ", (unsigned long long)g_now); vprintf(f, a); printf("\n"); va_end(a); }
static FILE *exe_side_open(const char *n, const char *m) { (void)n; (void)m; return NULL; }
static int feel_flag(const char *file, uint64_t *at, int *val, int every) { (void)file; (void)at; (void)every; return *val; }
static uint64_t fnv64(const char *s) { uint64_t h = 0xcbf29ce484222325ULL; while (*s) { h ^= (uint8_t)*s++; h *= 0x100000001b3ULL; } return h; }
static uint64_t g_att_vox_ms;
static int n_say, n_wave, n_punch, n_pain, n_kick, n_vic, n_whoosh, n_dodge, n_whiff, n_spm;
static uint64_t puppet_handle(uint32_t sl) { return 0x1000 + sl; }
static uint8_t *t2r_peer(uint32_t sl) { (void)sl; return NULL; }
static uint64_t current_weapon(void) { return 0; }
static int knife_weapon_id(uint64_t w) { (void)w; return 0; }
static int melee_class_of(uint64_t w, const char **n) { (void)w; (void)n; return -1; }
static uint64_t base_weapon(uint64_t w) { return w; }
static int dm_wave(int l, uint64_t e, float g) { (void)l; (void)e; (void)g; n_wave++; return 1; }
static void dm_say(uint64_t e, const char *ev, int v) { (void)e; (void)ev; (void)v; n_say++; }
static void knife_hit_native(uint64_t e, int l) { (void)e; (void)l; }
static void melee_hit_fx(uint64_t e, uint64_t w) { (void)e; (void)w; }
static float local_hp(void) { return 100.0f; }
static void esfx_stop(uint64_t h) { (void)h; }
#include "mv3.h"
const mv3_move MV3_MOVES[] = {{.name = "fist-swing-1", .kind = MV3_K_SWING1, .wset = MV3_WS_FIST, .hit0_f = 25, .strength = 1}};
const int MV3_MOVES_N = 1;
#include "mv3_fx.c"
// ---- the stubbed net + helpers
static mv3_world g_w; static uint32_t g_conf;
static int mv3_net_active(void) { return 1; }
static const mv3_world *mv3_net_world(void) { return &g_w; }
static int mv3_net_local_idx(void) { return 0; }
static uint32_t mv3_net_confirmed(void) { return g_conf; }
static int mv3_net_slot_of_idx(int i) { return i; }
static uint32_t mv3_net_frame_ms(uint32_t f) { return (uint32_t)(100000 + f * 1000 / 60); }
static int mtell_body_ok(uint32_t who) { (void)who; return 1; }
static void mdg_whiff_whoosh(uint64_t e, uint64_t w, int s) { (void)e; (void)w; (void)s; n_whoosh++; }
static void mdg_dodge_say(uint32_t who, uint64_t e) { (void)who; (void)e; n_dodge++; }
static void mhr_pain_say(uint32_t who, uint64_t e, int s, int sh) { (void)who; (void)e; (void)s; (void)sh; n_pain++; }
static uint64_t mhr_punch_at(uint64_t e, int s, const char *w) { (void)e; (void)s; (void)w; n_punch++; return 1; }
static int mfk_flag(int w) { (void)w; return 0; }
static const char *mfk_busy(void) { return NULL; }
static void mfk_add(float a, float r, float p, float y) { (void)a; (void)r; (void)p; (void)y; n_kick++; }
static void mfk_whiff(void) { n_whiff++; }
static void mfk_victim_hit(uint32_t s, uint64_t w, float d, float b, float a) { (void)s; (void)w; (void)d; (void)b; (void)a; n_vic++; }
static void mhfx_counter(uint32_t s, uint64_t w) { (void)s; (void)w; }
static void spm_event(void) { n_spm++; }
static void run_to(uint32_t f) { while (g_w.frame < f) { g_w.frame++; g_now = mv3_net_frame_ms(g_w.frame); mv3_fx_tick(g_now); } }
static mv3_evbuf one(uint32_t f, int type, int a, int b) { mv3_evbuf e = {0}; e.n = 1; e.e[0].frame = f; e.e[0].type = (uint8_t)type; e.e[0].a = (uint8_t)a; e.e[0].b = (uint8_t)b; e.e[0].move = 0; e.e[0].x = 200; return e; }
static int fails;
#define CHECK(c, ...) do { if (!(c)) { fails++; printf("FAIL %s: ", #c); printf(__VA_ARGS__); printf("\n"); } else printf("ok   %s\n", #c); } while (0)
int main(void) {
    g_w.n = 2; g_w.f[0].state = MV3_S_SWING; g_w.f[1].state = MV3_S_IDLE;
    printf("1. swing + resim re-emit: every cue once\n");
    run_to(10); g_conf = 10;
    mv3_evbuf e = one(10, MV3_E_SWING, 0, 0xff); mv3_fx_events(&e, 0);
    run_to(14); mv3_fx_rolled_back(9); mv3_fx_events(&e, 1); run_to(40);
    CHECK(n_wave == 1 && n_say == 1 && n_whoosh == 1, "wave %d say %d whoosh %d", n_wave, n_say, n_whoosh);
    printf("2. predicted HIT removed by a rollback inside the grace: nothing heard\n");
    g_conf = 40; e = one(41, MV3_E_HIT, 1, 0); g_w.frame = 41; g_now = mv3_net_frame_ms(41); mv3_fx_events(&e, 0);
    g_now += 5; mv3_fx_rolled_back(41); mv3_fx_tick(g_now); run_to(60);
    CHECK(n_punch == 0 && n_pain == 0 && n_vic == 0, "punch %d pain %d jolt %d", n_punch, n_pain, n_vic);
    printf("3. HIT played after the grace, then moved one frame by a resim: re-keyed, no repeat\n");
    g_conf = 60; e = one(61, MV3_E_HIT, 1, 0); run_to(61); mv3_fx_events(&e, 0); run_to(63);
    CHECK(n_punch == 1 && n_vic == 1, "punch %d jolt %d", n_punch, n_vic);
    mv3_fx_rolled_back(60); e = one(62, MV3_E_HIT, 1, 0); mv3_fx_events(&e, 1); run_to(80);
    CHECK(n_punch == 1 && n_pain == 1 && n_vic == 1, "punch %d pain %d jolt %d", n_punch, n_pain, n_vic);
    printf("4. HIT heard, gone in a resim, back in a later one: not replayed\n");
    g_conf = 80; e = one(81, MV3_E_HIT, 1, 0); run_to(81); mv3_fx_events(&e, 0); run_to(85);
    int p0 = n_punch, q0 = n_pain;
    mv3_fx_rolled_back(80); run_to(86);
    mv3_fx_rolled_back(80); mv3_fx_events(&e, 1); run_to(100);
    CHECK(n_punch == p0 && n_pain == q0, "punch %d->%d pain %d->%d", p0, n_punch, q0, n_pain);
    printf("5. downing HIT: no pain grunt\n");
    g_conf = 100; mv3_evbuf d = {0}; d.n = 2; d.e[0] = one(101, MV3_E_HIT, 1, 0).e[0]; d.e[1] = one(101, MV3_E_DOWN, 0, 0xff).e[0];
    q0 = n_pain; run_to(101); mv3_fx_events(&d, 0); run_to(120);
    CHECK(n_pain == q0, "pain %d->%d", q0, n_pain);
    printf("6. dodge grunt once; WHIFF + DODGED of one swing: one follow-through; SP framing held\n");
    g_conf = 120; e = one(121, MV3_E_DODGE, 1, 0xff); run_to(121); mv3_fx_events(&e, 0);
    mv3_evbuf w2 = {0}; w2.n = 2; w2.e[0] = one(122, MV3_E_DODGED, 1, 0).e[0]; w2.e[1] = one(122, MV3_E_WHIFF, 0, 0xff).e[0];
    run_to(122); mv3_fx_events(&w2, 0); run_to(150);
    CHECK(n_dodge == 1 && n_whiff == 1, "dodge %d whiff %d", n_dodge, n_whiff);
    CHECK(n_spm > 100, "spm %d", n_spm);
    printf("7. a swing found 400 ms late (resim): its swish / grunt are stale, not played late\n");
    int s0 = n_say; g_conf = 150; e = one(126, MV3_E_SWING, 1, 0xff); mv3_fx_events(&e, 1); run_to(170);
    CHECK(n_say == s0, "say %d->%d", s0, n_say);
    g_now += 6000; mv3_fx_tick(g_now);
    printf(fails ? "%d FAILED\n" : "all passed\n", fails);
    return fails != 0;
}
