// nettest.c - offline test of the melee v3 netcode (tools/ext/mv3_net_core.h): two / three endpoints over a fake link (latency, jitter, loss, reorder),
// each with its own drifting clock and frame rate, driving a toy deterministic sim (the real one is mv3_sim.c). Checks: every confirmed-world
// hash both sides computed for the same frame agrees (outside an injected desync, which must be detected and healed), rollbacks stay short, sessions end
// the same way. Build: gcc -std=gnu2x -O2 -o nettest nettest.c   (from tools/mv3); against the real sim + moves:
//   gcc -std=gnu2x -O2 -DMV3N_REAL_SIM -I<dir holding mv3_sim.c and mv3_moves.h> -o nettest nettest.c
#include <stdio.h>
#include <stdlib.h>
#include <stdint.h>
#include <string.h>
#include <math.h>
#include "../ext/mv3.h"

#ifdef MV3N_REAL_SIM
// the real sim : gcc ... -DMV3N_REAL_SIM -I<dir with mv3_sim.c + mv3_moves.h>
#include "mv3_moves.h"
#include "mv3_sim.c"
#else
// ---------------------------------------------------------------- toy sim (pure, deterministic; uses the contract's types)
void mv3_sim_init(mv3_world *w, uint32_t seed) {
    memset(w, 0, sizeof *w);
    w->rng = seed ? seed : 1;
    for (int i = 0; i < MV3_MAX_F; i++) { w->f[i].slot = 0xff; w->f[i].move = -1; w->f[i].target = 0xff; w->f[i].dodged_by = 0xff; }
}
int mv3_sim_add(mv3_world *w, uint8_t slot, uint8_t team, const mv3_in *in) {
    for (int i = 0; i < MV3_MAX_F; i++) if (w->f[i].slot == 0xff) {
        mv3_fighter *f = &w->f[i];
        memset(f, 0, sizeof *f);
        f->slot = slot; f->team = team; f->move = -1; f->target = 0xff; f->dodged_by = 0xff; f->react = -1;
        f->px = in->px; f->pz = in->pz; f->py = in->py; f->yaw = in->yaw; f->wset = in->wset; f->hp = 1000;
        w->n++;
        return i;
    }
    return -1;
}
void mv3_sim_remove(mv3_world *w, int idx) { if (idx >= 0 && idx < MV3_MAX_F && w->f[idx].slot != 0xff) { w->f[idx].slot = 0xff; w->n--; } }
static uint32_t toy_rng(mv3_world *w) { uint32_t x = w->rng; x ^= x << 13; x ^= x >> 17; x ^= x << 5; return w->rng = x; }
static void toy_ev(mv3_evbuf *ev, uint32_t fr, int type, int a, int b, int move, int x) {
    if (ev->n >= MV3_EV_MAX) return;
    mv3_ev *e = &ev->e[ev->n++]; memset(e, 0, sizeof *e);
    e->frame = fr; e->type = (uint8_t)type; e->a = (uint8_t)a; e->b = (uint8_t)b; e->move = (int16_t)move; e->x = (int16_t)x;
}
void mv3_sim_step(mv3_world *w, const mv3_in in[MV3_MAX_F], mv3_evbuf *ev) {
    w->frame++;
    uint32_t fr = w->frame;
    for (int i = 0; i < MV3_MAX_F; i++) {
        mv3_fighter *f = &w->f[i];
        if (f->slot == 0xff) continue;
        uint8_t edge = in[i].btn & ~f->prev_btn;
        f->prev_btn = in[i].btn;
        switch (f->state) {
        case MV3_S_IDLE:
            f->px = in[i].px; f->pz = in[i].pz; f->py = in[i].py; f->yaw = in[i].yaw; f->wset = in[i].wset;
            if ((edge & MV3_B_ATK) && (in[i].flags & 1)) { f->state = MV3_S_SWING; f->mf = 0; f->move = 1; f->hit_done = 0; toy_ev(ev, fr, MV3_E_SWING, i, 0, 1, 0); }
            else if (edge & MV3_B_DODGE) { f->state = MV3_S_DODGE; f->mf = 0; f->move = 2; f->iframe_end = (uint16_t)(fr + 12); toy_ev(ev, fr, MV3_E_DODGE, i, 0, 2, 0); }
            break;
        case MV3_S_SWING:
            f->mf++;
            if (f->mf == 10 && !f->hit_done) {
                f->hit_done = 1;
                int best = -1; int64_t bd = 0;
                for (int j = 0; j < MV3_MAX_F; j++) {
                    if (j == i || w->f[j].slot == 0xff || w->f[j].team == f->team) continue;
                    int64_t dx = w->f[j].px - f->px, dz = w->f[j].pz - f->pz, d2 = dx * dx + dz * dz;
                    if (d2 < 1500LL * 1500 && (best < 0 || d2 < bd)) { best = j; bd = d2; }
                }
                if (best < 0) toy_ev(ev, fr, MV3_E_WHIFF, i, 0, 1, 0);
                else if (w->f[best].state == MV3_S_DODGE && (uint16_t)(w->f[best].iframe_end - (uint16_t)fr) < 0x8000) toy_ev(ev, fr, MV3_E_DODGED, best, i, 1, 0);
                else {
                    int dmg = 50 + (int)(toy_rng(w) % 100);
                    w->f[best].hp -= (int16_t)dmg; w->f[best].state = MV3_S_REACT; w->f[best].mf = 0; w->f[best].move = 3;
                    toy_ev(ev, fr, MV3_E_HIT, i, best, 1, dmg);
                }
            }
            if (f->mf >= 30) { f->state = MV3_S_IDLE; f->move = -1; }
            break;
        case MV3_S_DODGE:
            f->mf++;
            f->px += (in[i].sx > 0 ? 25 : -25);       // root motion owned by the sim
            if (f->mf >= 20) { f->state = MV3_S_IDLE; f->move = -1; }
            break;
        case MV3_S_REACT:
            f->mf++;
            f->pz -= 10;
            if (f->mf >= 25) { f->state = MV3_S_IDLE; f->move = -1; }
            break;
        default: break;
        }
    }
}
uint32_t mv3_sim_hash(const mv3_world *w) {
    const uint8_t *b = (const uint8_t *)w; uint32_t h = 2166136261u;
    for (size_t i = 0; i < sizeof *w; i++) h = (h ^ b[i]) * 16777619u;
    return h;
}

#endif
#include "../ext/mv3_net_core.h"

// ---------------------------------------------------------------- harness
#define NE 3
#define LINKQ 20000
typedef struct {
    int id; uint8_t slot; uint8_t team;
    mv3n_ctx c;
    double drift; int64_t clk_off;            // local_us = global * (1 + drift) + clk_off
    double fps; uint64_t next_tick;
    uint32_t rng;
    int16_t hp;
    // input script
    int32_t px, pz; int hold, hold_btn; int frames;
    int sleeping;                              // not in a match / gone
    // checks
    struct { uint32_t f, h; } hs[4096]; int nh;
    uint32_t ev_first, ev_resim, rb_calls;
    int quiet;
} ep_t;
static ep_t g_e[NE];
static uint64_t g_now;                          // global us
static struct { uint64_t at; int from, to, len; uint8_t b[MV3N_PKT]; } g_q[LINKQ];
static int g_qn;
static double g_loss = 0.05; static int g_rtt_lo = 100, g_rtt_hi = 250, g_jit = 30;
static uint32_t g_lrng = 12345;
static uint32_t lr(void) { uint32_t x = g_lrng; x ^= x << 13; x ^= x >> 17; x ^= x << 5; return g_lrng = x; }
static double lrf(void) { return (lr() & 0xffffff) / (double)0x1000000; }
static uint32_t g_sent, g_lost, g_maxlen, g_bytes;
static int ep_of_slot(uint32_t s) { for (int i = 0; i < NE; i++) if (g_e[i].slot == s) return i; return -1; }
static uint64_t loc_us(ep_t *e) { return (uint64_t)((double)g_now * (1.0 + e->drift)) + (uint64_t)e->clk_off; }
static int g_verbose = 0;

static void io_send(void *u, uint32_t to, const uint8_t *b, int len) {
    ep_t *e = (ep_t *)u;
    int t = ep_of_slot(to);
    g_sent++; g_bytes += (uint32_t)len; if ((uint32_t)len > g_maxlen) g_maxlen = (uint32_t)len;
    if (len > MV3N_PKT) { printf("FAIL: packet op %u of %d bytes > %d\n", b[0], len, MV3N_PKT); exit(1); }
    if (t < 0 || g_e[t].sleeping) return;
    if (lrf() < g_loss) { g_lost++; return; }
    if (g_qn >= LINKQ) return;
    // one-way = half of a slowly varying RTT in [lo, hi] + jitter (reorders)
    double ph = (double)g_now / 7e6;
    double rtt = g_rtt_lo + (g_rtt_hi - g_rtt_lo) * (0.5 + 0.5 * sin(ph * 6.283));
    uint64_t ow = (uint64_t)(rtt * 500.0) + (uint64_t)(lrf() * g_jit * 1000.0);
    g_q[g_qn].at = g_now + ow; g_q[g_qn].from = e->id; g_q[g_qn].to = t; g_q[g_qn].len = len; memcpy(g_q[g_qn].b, b, (size_t)len); g_qn++;
}
static void io_input(void *u, mv3_in *o) {
    ep_t *e = (ep_t *)u;
    memset(o, 0, sizeof *o);
    uint32_t x = e->rng; x ^= x << 13; x ^= x >> 17; x ^= x << 5; e->rng = x;
    if (e->hold > 0) { e->hold--; o->btn = (uint8_t)e->hold_btn; }
    else if (x % 37 == 0) { e->hold = 1 + (int)(x >> 8) % 4; e->hold_btn = (x >> 12) & 1 ? MV3_B_ATK : MV3_B_DODGE; o->btn = (uint8_t)e->hold_btn; }
    e->px += (int)((x >> 16) % 61) - 30; e->pz += (int)((x >> 20) % 41) - 20;
    if (e->px > 1200) e->px -= 40;
    if (e->px < -1200) e->px += 40;
    if (e->pz > 800) e->pz -= 30;
    if (e->pz < -800) e->pz += 30;
    o->px = e->px; o->pz = e->pz; o->py = 0; o->yaw = (int16_t)((x >> 4) % 36000 - 18000);
    o->sx = (int8_t)((x >> 3) & 0x7f); o->sy = 0; o->wset = MV3_WS_FIST; o->flags = 1;
}
static void io_events(void *u, const mv3_evbuf *ev, int resim) { ep_t *e = (ep_t *)u; if (resim) e->ev_resim += (uint32_t)ev->n; else e->ev_first += (uint32_t)ev->n; }
static void io_rb(void *u, uint32_t f) { (void)f; ((ep_t *)u)->rb_calls++; }
static void io_frame(void *u, const mv3_world *w) { (void)u; (void)w; }
static int16_t io_hp(void *u) { return ((ep_t *)u)->hp; }
static int io_team(void *u, uint32_t s) { (void)u; int i = ep_of_slot(s); return i >= 0 ? g_e[i].team : (int)(s & 1); }
static float io_rtt(void *u, uint32_t s) { (void)u; (void)s; return (float)(g_rtt_lo + g_rtt_hi) * 0.5f; }
static void io_log(void *u, const char *m) { ep_t *e = (ep_t *)u; if (!e->quiet || g_verbose) printf("  [%7.3f s] ep%d: %s\n", (double)g_now / 1e6, e->id, m); }
static void io_hash(void *u, uint32_t f, uint32_t h) { ep_t *e = (ep_t *)u; if (e->nh < 4096) { e->hs[e->nh].f = f; e->hs[e->nh].h = h; e->nh++; } }

static void ep_setup(int i, uint8_t slot, uint8_t team, double drift, int64_t off, double fps) {
    ep_t *e = &g_e[i]; memset(e, 0, sizeof *e);
    e->id = i; e->slot = slot; e->team = team; e->drift = drift; e->clk_off = off; e->fps = fps; e->rng = 0x1234567u * (uint32_t)(i + 1); e->hp = 1000;
    e->px = i == 0 ? -600 : 600; e->pz = i == 2 ? 500 : 0;
    mv3n_io io = { e, io_send, io_input, io_events, io_rb, io_frame, io_hp, io_team, io_rtt, io_log, io_hash };
    mv3n_init(&e->c, &io, slot);
}
static void run_until(uint64_t until, void (*hook)(void)) {
    while (g_now < until) {
        g_now += 500;    // 0.5 ms steps
        // deliver
        for (int k = 0; k < g_qn; ) {
            if (g_q[k].at <= g_now) {
                ep_t *t = &g_e[g_q[k].to];
                if (!t->sleeping) mv3n_recv(&t->c, g_e[g_q[k].from].slot, g_q[k].b, (uint64_t)g_q[k].len, loc_us(t));
                g_q[k] = g_q[--g_qn];
            } else k++;
        }
        for (int i = 0; i < NE; i++) {
            ep_t *e = &g_e[i];
            if (e->sleeping || g_now < e->next_tick) continue;
            if (e->c.state == MV3N_ACTIVE && (lr() % 400) == 0) { e->hp = (int16_t)(200 + lr() % 800); mv3n_set_hp(&e->c, e->hp); }   // the owner's engine hp changes now and then
            mv3n_tick(&e->c, loc_us(e));
            double dt = 1e6 / e->fps;
            if ((lr() % 600) == 0) dt += 60000;          // a hitch now and then
            e->next_tick = g_now + (uint64_t)dt;
        }
        if (hook) hook();
    }
}
// compare every hash two endpoints computed for the same frame
static int cmp_hashes(int a, int b, uint32_t from_f, uint32_t *n_same, uint32_t *n_diff) {
    *n_same = *n_diff = 0;
    for (int i = 0; i < g_e[a].nh; i++) {
        if (g_e[a].hs[i].f < from_f) continue;
        // the latest hash b computed for this frame (a resync recomputes after an adopt)
        int k = -1; for (int j = 0; j < g_e[b].nh; j++) if (g_e[b].hs[j].f == g_e[a].hs[i].f) k = j;
        if (k < 0) continue;
        int ka = i; for (int j = i + 1; j < g_e[a].nh; j++) if (g_e[a].hs[j].f == g_e[a].hs[i].f) ka = j;
        if (ka != i) continue;
        if (g_e[a].hs[ka].h == g_e[b].hs[k].h) (*n_same)++; else (*n_diff)++;
    }
    return (int)*n_diff;
}
static int g_fail;
#define CHECK(x, ...) do { if (!(x)) { printf("FAIL: " __VA_ARGS__); printf("\n"); g_fail++; } else { printf("ok: " __VA_ARGS__); printf("\n"); } } while (0)

// ---------------------------------------------------------------- scenarios
static uint32_t g_rbn[NE], g_rbf[NE], g_rbmax[NE], g_steps[NE], g_desync[NE], g_resync[NE], g_stall[NE];
static void grab_stats(void) {   // session totals survive until the ctx clears: sample them every step
    for (int i = 0; i < NE; i++) {
        mv3n_ctx *c = &g_e[i].c;
        if (c->state != MV3N_ACTIVE) continue;
        g_rbn[i] = c->s_rb; g_rbf[i] = c->s_rbf; g_rbmax[i] = c->s_rbmax; g_steps[i] = c->s_steps; g_desync[i] = c->s_desync; g_resync[i] = c->s_resync; g_stall[i] = c->s_stall;
    }
}
static void print_stats(int i) {
    printf("  ep%d: steps %u, rollbacks %u (%.2f per s), resimulated frames %u (avg %.1f, max %u), stalls %u, desyncs %u, resyncs %u, events first %u / resim %u\n",
           i, g_steps[i], g_rbn[i], g_steps[i] ? g_rbn[i] * 60.0 / g_steps[i] : 0.0, g_rbf[i], g_rbn[i] ? (double)g_rbf[i] / g_rbn[i] : 0.0, g_rbmax[i], g_stall[i], g_desync[i], g_resync[i], g_e[i].ev_first, g_e[i].ev_resim);
}
static void reset_world(void) { g_now = 0; g_qn = 0; g_sent = g_lost = g_maxlen = g_bytes = 0; memset(g_rbn, 0, sizeof g_rbn); memset(g_rbf, 0, sizeof g_rbf); memset(g_rbmax, 0, sizeof g_rbmax); memset(g_steps, 0, sizeof g_steps); memset(g_desync, 0, sizeof g_desync); memset(g_resync, 0, sizeof g_resync); memset(g_stall, 0, sizeof g_stall); }

static int g_corrupt_done;
static void hook_corrupt(void) {
    grab_stats();
    if (!g_corrupt_done && g_now > 20000000 && g_e[1].c.state == MV3N_ACTIVE) {   // flip B's world (rng + a fighter's hp) and its whole history: a real desync
        mv3n_ctx *c = &g_e[1].c;
        c->w.rng ^= 0x5a5a; c->w.f[0].hp -= 7;
        for (int i = 0; i < MV3_HIST; i++) { c->snap[i].rng ^= 0x5a5a; c->snap[i].f[0].hp -= 7; }
        g_corrupt_done = 1;
        printf("  [%7.3f s] test: corrupted ep1's world at frame %u\n", (double)g_now / 1e6, c->cur);
    }
}
static int g_join_done, g_leave_done;
static void hook_join(void) {
    grab_stats();
    if (!g_join_done && g_now > 8000000 && g_e[0].c.state == MV3N_ACTIVE) {
        g_e[2].sleeping = 0; g_e[2].next_tick = g_now;
        int r = mv3n_propose(&g_e[2].c, g_e[0].slot, loc_us(&g_e[2]));     // C walks up to its enemy A (not the master): REDIRECT -> JOIN_REQ -> JOIN -> SNAP
        printf("  [%7.3f s] test: ep2 proposes to ep0 -> %d\n", (double)g_now / 1e6, r);
        g_join_done = 1;
    }
    if (!g_leave_done && g_now > 30000000 && g_e[1].c.state == MV3N_ACTIVE) {
        mv3n_end(&g_e[1].c, "test leave", loc_us(&g_e[1]));
        printf("  [%7.3f s] test: ep1 leaves\n", (double)g_now / 1e6);
        g_leave_done = 1;
    }
}

int main(int argc, char **argv) {
    if (argc > 1 && !strcmp(argv[1], "-v")) g_verbose = 1;
    printf("sizeof(mv3_world) %zu, sizeof(mv3n_ctx) %zu\n", sizeof(mv3_world), sizeof(mv3n_ctx));

    // ---- 1. two players, 100-250 ms RTT, 5 % loss, 30 ms jitter, clocks 7 s apart + 300 ppm drift, 144 vs 60 fps with hitches, 60 s
    printf("\n== 1: 1v1, RTT 100-250 ms, 5%% loss, jitter 30 ms, 60 s\n");
    reset_world();
    ep_setup(0, 0, 0, 0.0, 1000000, 144.0); ep_setup(1, 3, 1, 0.0003, 7000000, 60.0); g_e[2].sleeping = 1; g_e[2].slot = 0xff;
    run_until(200000, NULL);
    CHECK(mv3n_propose(&g_e[0].c, 3, loc_us(&g_e[0])) == 1, "propose returns 1");
    run_until(60000000, grab_stats);
    CHECK(g_e[0].c.state == MV3N_ACTIVE && g_e[1].c.state == MV3N_ACTIVE, "both still in the bubble after 60 s (states %d %d)", g_e[0].c.state, g_e[1].c.state);
    { uint32_t s, d; cmp_hashes(0, 1, 0, &s, &d); CHECK(s > 100 && d == 0, "confirmed hashes agree: %u equal, %u different", s, d); }
    CHECK(g_desync[0] == 0 && g_desync[1] == 0, "no desync detected");
    CHECK(g_rbmax[0] <= 20 && g_rbmax[1] <= 20, "rollbacks bounded (max %u / %u frames)", g_rbmax[0], g_rbmax[1]);
    CHECK(g_stall[0] == 0 && g_stall[1] == 0, "no stalls");
    {
        int64_t fa = mv3n_target(&g_e[0].c, loc_us(&g_e[0])), fb = mv3n_target(&g_e[1].c, loc_us(&g_e[1]));
        CHECK(llabs(fa - fb) <= 2, "shared clocks agree: frame %lld vs %lld (A off %+.1f trim %+.1f, B off %+.1f trim %+.1f ms)", (long long)fa, (long long)fb,
              g_e[0].c.off / 1000.0, g_e[0].c.trim / 1000.0, g_e[1].c.off / 1000.0, g_e[1].c.trim / 1000.0);
    }
    printf("  link: %u packets, %u lost, max %u bytes, avg %.1f bytes, %.1f packets/s per side\n", g_sent, g_lost, g_maxlen, g_sent ? (double)g_bytes / g_sent : 0.0, g_sent / 60.0 / 2);
    print_stats(0); print_stats(1);
    // leave: A walks away (glue ends) -> both end at the same frame
    mv3n_end(&g_e[0].c, "test end", loc_us(&g_e[0]));
    run_until(63000000, grab_stats);
    CHECK(g_e[0].c.state == MV3N_IDLE && g_e[1].c.state == MV3N_IDLE, "both idle after A's leave (states %d %d)", g_e[0].c.state, g_e[1].c.state);

    // ---- 2. injected desync: detected and healed by the lower slot's snapshot
    printf("\n== 2: desync injection (RTT 120-180, 5%% loss)\n");
    reset_world(); g_rtt_lo = 120; g_rtt_hi = 180;
    ep_setup(0, 1, 0, 0.0, 0, 90.0); ep_setup(1, 4, 1, -0.0002, 123456789, 75.0); g_e[2].sleeping = 1; g_e[2].slot = 0xff;
    g_corrupt_done = 0;
    run_until(100000, NULL);
    mv3n_propose(&g_e[1].c, 1, loc_us(&g_e[1]));          // the higher slot proposes this time
    run_until(40000000, hook_corrupt);
    CHECK(g_desync[0] + g_desync[1] >= 1, "desync detected (%u / %u)", g_desync[0], g_desync[1]);
    CHECK(g_resync[1] >= 1 && g_resync[0] == 0, "ep1 (higher slot) adopted ep0's world (resyncs %u / %u)", g_resync[0], g_resync[1]);
    { uint32_t s, d; cmp_hashes(0, 1, g_e[1].c.cur > 600 ? g_e[1].c.cur - 600 : 0, &s, &d); CHECK(s > 10 && d == 0, "hashes agree again over the last 10 s: %u equal, %u different", s, d); }
    print_stats(0); print_stats(1);

    // ---- 3. a third player joins (via a non-master member), then a founder leaves; the other two fight on
    printf("\n== 3: join + leave (RTT 100-250, 5%% loss)\n");
    reset_world(); g_rtt_lo = 100; g_rtt_hi = 250;
    ep_setup(0, 5, 0, 0.0, 5000, 120.0); ep_setup(1, 2, 1, 0.0001, 99000000, 60.0); ep_setup(2, 6, 1, -0.0001, 42000000, 100.0);   // ep1 (slot 2) = master; ep2 sides with ep1
    g_e[2].sleeping = 1; g_join_done = g_leave_done = 0;
    run_until(100000, NULL);
    mv3n_propose(&g_e[0].c, 2, loc_us(&g_e[0]));
    run_until(45000000, hook_join);
    CHECK(g_e[2].c.state == MV3N_ACTIVE, "ep2 is in the bubble (state %d)", g_e[2].c.state);
    CHECK(g_e[1].c.state == MV3N_IDLE, "ep1 left (state %d)", g_e[1].c.state);
    CHECK(g_e[0].c.state == MV3N_ACTIVE, "ep0 fights on with ep2 (state %d)", g_e[0].c.state);
    { uint32_t s, d; cmp_hashes(0, 1, 0, &s, &d); CHECK(s > 50 && d == 0, "ep0/ep1 hashes: %u equal, %u different", s, d); }
    { uint32_t s, d; cmp_hashes(0, 2, 0, &s, &d); CHECK(s > 20 && d == 0, "ep0/ep2 hashes (after the join): %u equal, %u different", s, d); }
    { uint32_t s, d; cmp_hashes(1, 2, 0, &s, &d); CHECK(s > 20 && d == 0, "ep1/ep2 hashes: %u equal, %u different", s, d); }
    print_stats(0); print_stats(1); print_stats(2);

    printf("\n%s (%d failure%s)\n", g_fail ? "FAILED" : "ALL OK", g_fail, g_fail == 1 ? "" : "s");
    return g_fail ? 1 : 0;
}
