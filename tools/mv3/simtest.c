// simtest.c - offline tests for the melee v3 sim (tools/ext/mv3_sim.c). Plain gcc, no engine:
//   gcc -O2 -Wall -o simtest simtest.c                 (stub move table, tools/mv3/moves_stub.h)
//   gcc -O2 -Wall -DMV3_REAL_MOVES -o simtest simtest.c (tools/ext/mv3_moves.h; every scenario reads its timings from the table,
//                                                        so both tables must pass; the SP-cadence checks run on the real table only)
//   simtest                 run every scenario, exit 1 on a failure
//   simtest run <script> [-v]   replay a text input script (format below) and print every event (+ per-frame state with -v)
//
// Script format (one command per line, '#' comments; frames are world frames, the first step is frame 1):
//   seed <n>
//   fighter <slot> <team> <x_mm> <z_mm> <yaw_cdeg> [wset] [hp]     adds a fighter (index = order of the lines)
//   follow <0|1>                    1 (default): IDLE input pose follows the sim body, like the owner's engine body does
//   hold <frame> <idx> <btnmask>    held buttons from that frame on (1 atk, 2 dodge)
//   tap <frame> <idx> atk|dodge     the button down for that one frame only
//   stick <frame> <idx> <sx> <sy>   stick from that frame on (body frame: sy+ forward, sx+ = the body's right = toward yaw-90)
//   pose <frame> <idx> <x> <z> <yaw>   owner pose from that frame on
//   flags <frame> <idx> <flags>     input flags from that frame on (bit0 can-melee, default 1)
//   run <frames>                    total frames to simulate
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "../ext/mv3.h"
#ifdef MV3_REAL_MOVES
#include "../ext/mv3_moves.h"
#else
#include "moves_stub.h"
#endif
#include "../ext/mv3_sim.c"

static int g_fail, g_pass, g_verbose;
#define CHECK(c, ...) do { if (c) g_pass++; else { g_fail++; printf("  FAIL %s:%d: %s :: ", __FILE__, __LINE__, #c); printf(__VA_ARGS__); printf("\n"); } } while (0)

static const char *ev_name[] = { "SWING", "HIT", "WHIFF", "DODGE", "DODGED", "REACT", "COUNTER", "DOWN" };
static const char *st_name[] = { "IDLE", "SWING", "DODGE", "REACT", "COUNTER", "COUNTERED", "MISS", "OUT" };

// ---- harness
typedef struct {
    mv3_world w;
    mv3_in in[MV3_MAX_F];
    uint8_t tap[MV3_MAX_F];
    int follow;
    mv3_ev log[8192]; int nlog;
} sc_t;

static void sc_init(sc_t *s, uint32_t seed) { memset(s, 0, sizeof *s); mv3_sim_init(&s->w, seed); s->follow = 1; }
static int sc_add(sc_t *s, int slot, int team, int x, int z, int yaw)
{
    mv3_in in = { 0 };
    in.px = x; in.pz = z; in.yaw = (int16_t)yaw; in.flags = 1; in.wset = MV3_WS_FIST;
    int i = mv3_sim_add(&s->w, (uint8_t)slot, (uint8_t)team, &in);
    s->in[i] = in;
    return i;
}
static void print_ev(const mv3_ev *e)
{
    const mv3_move *m = mv3b_mv(e->move);
    printf("    f=%u %-7s a=%d b=%d move=%d(%s) x=%d\n", e->frame, ev_name[e->type], e->a, e->b == 0xff ? -1 : e->b, e->move, m ? m->name : "-", e->x);
}
static void sc_step(sc_t *s)
{
    mv3_in in[MV3_MAX_F]; mv3_evbuf eb;
    memcpy(in, s->in, sizeof in);
    for (int i = 0; i < MV3_MAX_F; i++) in[i].btn |= s->tap[i];
    memset(s->tap, 0, sizeof s->tap);
    mv3_sim_step(&s->w, in, &eb);
    for (int k = 0; k < eb.n && s->nlog < 8192; k++) { s->log[s->nlog++] = eb.e[k]; if (g_verbose) print_ev(&eb.e[k]); }
    if (s->follow)
        for (int i = 0; i < s->w.n; i++) {          // the owner's engine body is posed at the sim body: its next input reports that pose
            s->in[i].px = s->w.f[i].px; s->in[i].pz = s->w.f[i].pz; s->in[i].py = s->w.f[i].py; s->in[i].yaw = s->w.f[i].yaw;
        }
}
static void sc_run(sc_t *s, int frames) { for (int k = 0; k < frames && k < 20000; k++) sc_step(s); }
// after: w.frame == frame. A target far ahead (an underflowed frame number from a missing event) is a test bug: fail, never spin
static void sc_run_to(sc_t *s, uint32_t frame)
{
    if (frame > s->w.frame + 20000u) { g_fail++; printf("  FAIL harness: run to frame %u from %u (bad frame number)\n", frame, s->w.frame); return; }
    while (s->w.frame < frame) sc_step(s);
}
// tap on world frame `frame` (steps up to frame-1 first); a frame already simulated is a test bug
static void sc_tap_at(sc_t *s, uint32_t frame, int i, int btn)
{
    if (frame <= s->w.frame) { g_fail++; printf("  FAIL harness: tap at frame %u but the world is at %u\n", frame, s->w.frame); return; }
    sc_run_to(s, frame - 1); s->tap[i] |= (uint8_t)btn; sc_step(s);
}
static int ev_find(const sc_t *s, int type, int a, uint32_t from)   // frame of the first event, -1 none
{
    for (int k = 0; k < s->nlog; k++) if (s->log[k].type == type && (a < 0 || s->log[k].a == a) && s->log[k].frame >= from) return (int)s->log[k].frame;
    return -1;
}
static const mv3_ev *ev_get(const sc_t *s, int type, int a, uint32_t from)
{
    for (int k = 0; k < s->nlog; k++) if (s->log[k].type == type && (a < 0 || s->log[k].a == a) && s->log[k].frame >= from) return &s->log[k];
    return 0;
}
static int ev_count(const sc_t *s, int type, int a)
{
    int n = 0;
    for (int k = 0; k < s->nlog; k++) if (s->log[k].type == type && (a < 0 || s->log[k].a == a)) n++;
    return n;
}
static const mv3_move *M(int kind) { int m = mv3b_find(kind, MV3_WS_FIST, -1); return m >= 0 ? &MV3_MOVES[m] : 0; }
static int has_row(int kind, int dir) { for (int i = 0; i < MV3_MOVES_N; i++) if (MV3_MOVES[i].kind == kind && MV3_MOVES[i].dir == dir) return 1; return 0; }
static int imax(int a, int b) { return a > b ? a : b; }
static int END(const mv3_move *m) { return mv3b_end(m); }
// move frame a committed chain press starts the next combo step (the sim's rule)
static int CS(const mv3_move *m) { int cs = imax(imax(m->chain0_f, mv3b_hit_last(m) + 1), MV3B_CADENCE); return cs > END(m) - 1 ? END(m) - 1 : cs; }
static int ms(int frames) { return frames * 1000 / MV3_HZ; }

// A at the origin facing +z, B 1 m in front facing A
static void duel(sc_t *s, uint32_t seed) { sc_init(s, seed); sc_add(s, 1, 0, 0, 0, 0); sc_add(s, 2, 1, 0, 1000, 18000); }

// ---- scenarios
static void t_single_hit(void)
{
    printf("single swing hits an idle target\n");
    sc_t s; duel(&s, 1);
    const mv3_move *s1 = M(MV3_K_SWING1);
    sc_tap_at(&s, 1, 0, MV3_B_ATK);
    sc_run(&s, 300);
    CHECK(ev_find(&s, MV3_E_SWING, 0, 0) == 1, "swing at %d", ev_find(&s, MV3_E_SWING, 0, 0));
    const mv3_ev *h = ev_get(&s, MV3_E_HIT, 0, 0);
    CHECK(h && h->frame == 1u + s1->hit0_f && h->b == 1 && h->x == s1->dmg, "hit %d", h ? (int)h->frame : -1);
    const mv3_ev *r = ev_get(&s, MV3_E_REACT, 1, 0);
    CHECK(r && h && r->frame == h->frame && r->x == 0, "react front, frame %d", r ? (int)r->frame : -1);
    CHECK(s.w.f[1].hp == MV3B_HP0 - s1->dmg, "hp %d", s.w.f[1].hp);
    CHECK(ev_count(&s, MV3_E_HIT, -1) == 1 && ev_count(&s, MV3_E_WHIFF, -1) == 0, "one contact");
    CHECK(s.w.f[0].state == MV3_S_IDLE && s.w.f[1].state == MV3_S_IDLE, "both idle after");
    CHECK(s.w.f[0].pz > 0 && s.w.f[1].pz > 1000, "root motion: A %d forward, B %d pushed back", s.w.f[0].pz, s.w.f[1].pz);
}
static void t_combo(void)
{
    printf("3-hit combo chain timing\n");
    sc_t s; duel(&s, 2);
    const mv3_move *s1 = M(MV3_K_SWING1), *s2 = M(MV3_K_SWING2), *s3 = M(MV3_K_SWING3);
    sc_tap_at(&s, 1, 0, MV3_B_ATK);                           // swing 1 at f1
    sc_tap_at(&s, 1 + imax(2, s1->chain0_f - MV3B_CHAIN_EARLY), 0, MV3_B_ATK);   // the earliest press that commits at once
    uint32_t f2 = 1 + CS(s1);
    sc_run_to(&s, f2);
    const mv3_ev *e2 = ev_get(&s, MV3_E_SWING, 0, 2);
    CHECK(e2 && e2->frame == f2 && e2->x == 1, "step 2 at %d (want %u)", e2 ? (int)e2->frame : -1, f2);
    sc_tap_at(&s, f2 + imax(2, s2->chain0_f - MV3B_CHAIN_EARLY), 0, MV3_B_ATK);
    uint32_t f3 = f2 + CS(s2);
    sc_run(&s, 300);
    const mv3_ev *e3 = ev_get(&s, MV3_E_SWING, 0, f2 + 1);
    CHECK(e3 && e3->frame == f3 && e3->x == 2, "step 3 at %d (want %u)", e3 ? (int)e3->frame : -1, f3);
    CHECK(ev_count(&s, MV3_E_HIT, 0) == 3, "3 hits, got %d (dist end %d)", ev_count(&s, MV3_E_HIT, 0), s.w.f[1].pz - s.w.f[0].pz);
    const mv3_ev *h1 = ev_get(&s, MV3_E_HIT, 0, 0), *h2 = ev_get(&s, MV3_E_HIT, 0, f2), *h3 = ev_get(&s, MV3_E_HIT, 0, f3);
    CHECK(h1 && h1->frame == 1u + s1->hit0_f, "step 1 contact at %d", h1 ? (int)h1->frame : -1);
    CHECK(h2 && h2->frame == f2 + s2->hit0_f, "step 2 contact at %d", h2 ? (int)h2->frame : -1);
    CHECK(h3 && h3->frame == f3 + s3->hit0_f && h3->x == s3->dmg, "step 3 contact at %d", h3 ? (int)h3->frame : -1);
    const mv3_ev *r3 = h3 ? ev_get(&s, MV3_E_REACT, 1, h3->frame) : 0;
    CHECK(r3 && r3->frame == h3->frame && MV3_MOVES[r3->move].strength == s3->strength, "step 3 reaction of the finisher's strength");
    if (h1 && h2 && h3 && e2 && e3)
        printf("    contacts %d / %d / %d ms after each swing start, next step %d / %d ms after the contact\n", ms((int)h1->frame - 1), ms((int)(h2->frame - f2)),
               ms((int)(h3->frame - f3)), ms((int)(e2->frame - h1->frame)), ms((int)(e3->frame - h2->frame)));
#ifdef MV3_REAL_MOVES
    // SP cadence (re/sp-melee-1027, README-data.md): fist contacts ~300 / 267 / 333 ms, the next step at contact + 331 ms (+-1 frame)
    if (h1 && h2 && h3 && e2 && e3) {
        int c1 = ms((int)h1->frame - 1), c2 = ms((int)(h2->frame - f2)), c3 = ms((int)(h3->frame - f3));
        CHECK(c1 >= 284 && c1 <= 317 && c2 >= 250 && c2 <= 284 && c3 >= 317 && c3 <= 350, "SP contact times %d / %d / %d ms", c1, c2, c3);
        int g1 = ms((int)(e2->frame - h1->frame)), g2 = ms((int)(e3->frame - h2->frame));
        CHECK(g1 >= 314 && g1 <= 350 && g2 >= 314 && g2 <= 350, "chain at contact + %d / %d ms (SP 331)", g1, g2);
    }
#endif
    // a press after the chain window: the swing is over (cancel = chain1), a fresh step-0 swing at once
    sc_t t; duel(&t, 3);
    sc_tap_at(&t, 1, 0, MV3_B_ATK);
    uint32_t late = 1 + imax(END(s1), s1->chain1_f) + 1;
    sc_tap_at(&t, late, 0, MV3_B_ATK);
    const mv3_ev *ef = ev_get(&t, MV3_E_SWING, 0, 2);
    CHECK(ef && ef->frame == late && ef->x == 0, "fresh swing step 0 at %d (want %u)", ef ? (int)ef->frame : -1, late);
    // a press before the commit point that is still buffered when it opens: chains
    sc_t u; duel(&u, 4);
    sc_tap_at(&u, 1, 0, MV3_B_ATK);
    int early = imax(2, s1->chain0_f - MV3B_CHAIN_EARLY - MV3B_BUF_MAX / 2);   // (mf 1 = frame 2: right after the frame-1 tap it would read as held)
    sc_tap_at(&u, 1 + early, 0, MV3_B_ATK);
    sc_run(&u, 120);
    const mv3_ev *eb = ev_get(&u, MV3_E_SWING, 0, 2);
    CHECK(eb && eb->frame == 1u + CS(s1) && eb->x == 1, "early press (mf %d) buffered into the chain (%d)", early, eb ? (int)eb->frame : -1);
    // a press so early that its buffer runs out before the commit point: no chain, and no stray swing after the first one
    int too = s1->chain0_f - MV3B_CHAIN_EARLY - MV3B_BUF_MAX - 2;
    if (too >= 1) {
        sc_t v; duel(&v, 5);
        sc_tap_at(&v, 1, 0, MV3_B_ATK);
        sc_tap_at(&v, 1 + too, 0, MV3_B_ATK);
        sc_run(&v, 200);
        CHECK(ev_count(&v, MV3_E_SWING, 0) == 1, "press at mf %d expired: %d swings", too, ev_count(&v, MV3_E_SWING, 0));
    }
}
static void t_mash(void)
{
    printf("mashing respects the cadence floor\n");
    sc_t s; duel(&s, 5);
    s.w.f[1].hp = 30000;                                     // stays up through the whole mash
    for (int k = 0; k < 300; k++) { if (k % 2 == 0) s.tap[0] = MV3_B_ATK; sc_step(&s); }
    int n = 0, last = -1000, minsp = 1000;
    for (int k = 0; k < s.nlog; k++) if (s.log[k].type == MV3_E_SWING && s.log[k].a == 0) {
        if (n) minsp = (int)s.log[k].frame - last < minsp ? (int)s.log[k].frame - last : minsp;
        last = (int)s.log[k].frame; n++;
    }
    printf("    %d swings in 300 frames, min spacing %d frames (cadence %d)\n", n, minsp, MV3B_CADENCE);
    CHECK(minsp >= MV3B_CADENCE, "spacing %d", minsp);
    CHECK(n >= 4 && n <= 300 / MV3B_CADENCE + 1, "swing count %d", n);
}
static void t_dodge_nothing(void)
{
    printf("dodge with no incoming swing does nothing (and does not pre-arm)\n");
    sc_t s; duel(&s, 6);
    sc_tap_at(&s, 1, 1, MV3_B_DODGE);
    CHECK(s.w.f[1].state == MV3_S_IDLE && s.w.f[1].buf == 0, "B idle, nothing buffered");
    sc_tap_at(&s, 3, 0, MV3_B_ATK);
    sc_run(&s, 40);
    CHECK(ev_count(&s, MV3_E_DODGE, -1) == 0, "no dodge");
    CHECK(ev_count(&s, MV3_E_HIT, 0) == 1, "A's later swing lands");
}
static void dodge_setup(sc_t *s, uint32_t seed)
{
    duel(s, seed);
    sc_tap_at(s, 1, 0, MV3_B_ATK);                            // A swing, contact f11..f13
    sc_tap_at(s, 5, 1, MV3_B_DODGE);                          // B dodges in A's windup (neutral stick = back)
}
static void t_dodge(void)
{
    printf("dodge during windup avoids the hit, attacker plays MISS\n");
    sc_t s; dodge_setup(&s, 7);
    const mv3_ev *d = ev_get(&s, MV3_E_DODGE, 1, 0);
    CHECK(d && d->frame == 5 && d->b == 0 && d->x == 3, "dodge back at 5 vs A");
    sc_run_to(&s, 20);
    CHECK(ev_count(&s, MV3_E_HIT, -1) == 0, "no hit");
    const mv3_ev *dd = ev_get(&s, MV3_E_DODGED, 1, 0);
    CHECK(dd && dd->b == 0 && dd->frame == 1u + M(MV3_K_SWING1)->hit0_f, "dodged at A's hit0 (%d)", dd ? (int)dd->frame : -1);
    CHECK(s.w.f[0].state == MV3_S_MISS && s.w.f[1].dodged_by == 0, "A in MISS, B holds the counter window");
    // stick to the right with no right dodge row -> falls back to back; stick left -> left row
    // mirroring: B faces A (-z), so its left is -x. Stick left (sx-) -> a dir-1 clip whose root motion moves B toward -x; stick right -> dir 2
    // (or back when the table has no right row) and never toward -x
    sc_t t; duel(&t, 8);
    sc_tap_at(&t, 1, 0, MV3_B_ATK);
    t.in[1].sx = -127;
    sc_tap_at(&t, 5, 1, MV3_B_DODGE);
    const mv3_ev *dl = ev_get(&t, MV3_E_DODGE, 1, 0);
    CHECK(dl && dl->x == 1 && MV3_MOVES[dl->move].dir == 1, "stick left -> left dodge row");
    sc_run_to(&t, 5 + (dl ? END(&MV3_MOVES[dl->move]) : 1));
    CHECK(t.w.f[1].px < -300, "left dodge moved B to its left (-x): x %d", t.w.f[1].px);
    sc_t u; duel(&u, 9);
    sc_tap_at(&u, 1, 0, MV3_B_ATK);
    u.in[1].sx = 127;
    sc_tap_at(&u, 5, 1, MV3_B_DODGE);
    const mv3_ev *dr = ev_get(&u, MV3_E_DODGE, 1, 0);
    int want_row = has_row(MV3_K_DODGE, 2) ? 2 : 3;
    CHECK(dr && dr->x == 2 && MV3_MOVES[dr->move].dir == want_row, "stick right -> row dir %d (got %d)", want_row, dr ? MV3_MOVES[dr->move].dir : -1);
    sc_run_to(&u, 5 + (dr ? END(&MV3_MOVES[dr->move]) : 1));
    if (want_row == 2) CHECK(u.w.f[1].px > 300, "right dodge moved B to its right (+x): x %d", u.w.f[1].px);
    else CHECK(u.w.f[1].px > -300, "back fallback did not go left: x %d", u.w.f[1].px);
}
static void t_counter(void)
{
    printf("counter after a dodge\n");
    sc_t s; dodge_setup(&s, 11);
    uint32_t dodged = 1u + M(MV3_K_SWING1)->hit0_f;           // A's contact frame: B's i-frames make it DODGED
    uint32_t press = dodged + 3;
    sc_tap_at(&s, press, 1, MV3_B_ATK);
    const mv3_ev *c = ev_get(&s, MV3_E_COUNTER, 1, 0);
    CHECK(c && c->frame == press && c->b == 0, "counter at %u (%d), dist %d", press, c ? (int)c->frame : -1, s.w.f[0].pz - s.w.f[1].pz);
    CHECK(s.w.f[1].state == MV3_S_COUNTER && s.w.f[0].state == MV3_S_COUNTERED, "pair states %d %d", s.w.f[1].state, s.w.f[0].state);
    const mv3_move *cm = c ? &MV3_MOVES[c->move] : M(MV3_K_COUNTER), *cv = s.w.f[0].move >= 0 ? &MV3_MOVES[s.w.f[0].move] : M(MV3_K_COUNTERED);
    const mv3_ev *dg = ev_get(&s, MV3_E_DODGE, 1, 0);
    if (c && dg) CHECK(cm->dir == (MV3_MOVES[dg->move].dir == 0 ? 0 : 3) || !has_row(MV3_K_COUNTER, MV3_MOVES[dg->move].dir == 0 ? 0 : 3),
                       "counter row %s matches the dodge direction", cm->name);
    if (c && cm->pair) CHECK(cv->name && !strcmp(cv->name, cm->pair), "victim plays the row's pair (%s)", cv->name ? cv->name : "-");
    sc_run(&s, imax(END(cm), END(cv)) + 10);
    const mv3_ev *h = ev_get(&s, MV3_E_HIT, 1, 0);
    CHECK(h && h->frame == press + cm->hit0_f && h->b == 0 && h->x == cm->dmg, "counter contact at hit0 (%d)", h ? (int)h->frame : -1);
    CHECK(ev_count(&s, MV3_E_REACT, 0) == 0, "countered clip is the reaction");
    CHECK(s.w.f[0].hp == MV3B_HP0 - cm->dmg && s.w.f[1].hp == MV3B_HP0, "hp");
    CHECK(s.w.f[0].state == MV3_S_IDLE && s.w.f[1].state == MV3_S_IDLE, "both idle (B free at %d, A at %d)", (int)press + END(cm), (int)press + END(cv));
    // a counter press inside the i-frames, before the DODGED frame: buffered, fires on the frame after it
    sc_t e; dodge_setup(&e, 13);
    if (dodged - 2 > e.w.frame) {
        sc_tap_at(&e, dodged - 2, 1, MV3_B_ATK);
        sc_run_to(&e, dodged + 3);
        CHECK(ev_find(&e, MV3_E_COUNTER, 1, 0) == (int)dodged + 1, "early counter press fires at %u (%d)", dodged + 1, ev_find(&e, MV3_E_COUNTER, 1, 0));
    }
    // the window closes: a late press is a plain swing
    sc_t t; dodge_setup(&t, 12);
    const mv3_ev *td = ev_get(&t, MV3_E_DODGE, 1, 0);
    uint32_t win = dodged + MV3B_COUNTER_WIN;
    if (td && td->frame + MV3_MOVES[td->move].chain1_f > win) win = td->frame + MV3_MOVES[td->move].chain1_f;
    sc_tap_at(&t, win + 1, 1, MV3_B_ATK);
    sc_run(&t, 10);
    CHECK(ev_count(&t, MV3_E_COUNTER, -1) == 0 && ev_count(&t, MV3_E_SWING, 1) == 1, "late press = swing, no counter");
}
static void t_trade(void)
{
    printf("simultaneous swings: same-frame contacts trade, otherwise first contact wins\n");
    sc_t s; duel(&s, 13);
    s.tap[0] = s.tap[1] = MV3_B_ATK; sc_step(&s);
    sc_run(&s, 40);
    CHECK(ev_count(&s, MV3_E_HIT, 0) == 1 && ev_count(&s, MV3_E_HIT, 1) == 1, "both hit");
    CHECK(ev_find(&s, MV3_E_HIT, 0, 0) == ev_find(&s, MV3_E_HIT, 1, 0), "same frame");
    CHECK(ev_count(&s, MV3_E_REACT, 0) == 1 && ev_count(&s, MV3_E_REACT, 1) == 1, "both react");
    sc_t t; duel(&t, 14);
    sc_tap_at(&t, 1, 0, MV3_B_ATK);
    sc_tap_at(&t, 2, 1, MV3_B_ATK);                            // one frame later: B's contact would be one frame after A's
    sc_run(&t, 40);
    CHECK(ev_count(&t, MV3_E_HIT, 0) == 1 && ev_count(&t, MV3_E_HIT, 1) == 0, "only A lands");
    CHECK(ev_count(&t, MV3_E_REACT, 1) == 1 && ev_count(&t, MV3_E_REACT, 0) == 0, "only B reacts");
}
static void t_interrupt(void)
{
    printf("a hit interrupts the victim's windup\n");
    sc_t s; duel(&s, 15);
    sc_tap_at(&s, 1, 0, MV3_B_ATK);
    sc_tap_at(&s, 6, 1, MV3_B_ATK);                            // B mf 5 at A's contact (f11), B's hit0 = 10
    CHECK(s.w.f[1].state == MV3_S_SWING, "B winding up");
    sc_run(&s, 40);
    CHECK(ev_find(&s, MV3_E_REACT, 1, 0) == 1 + M(MV3_K_SWING1)->hit0_f, "B reacts at A's contact");
    CHECK(ev_count(&s, MV3_E_HIT, 1) == 0 && ev_count(&s, MV3_E_WHIFF, 1) == 0, "B's swing is gone");
}
static void t_buffer(void)
{
    printf("buffered press fires on the first legal frame, expires after 300 ms\n");
    for (int late = 0; late < 2; late++) {
        sc_t s; duel(&s, 16);
        sc_tap_at(&s, 1, 0, MV3_B_ATK);
        sc_run_to(&s, 1u + M(MV3_K_SWING1)->hit0_f);
        const mv3_ev *r = ev_get(&s, MV3_E_REACT, 1, 0);
        CHECK(r != 0, "B reacts at A's contact");
        if (!r) continue;
        uint32_t free_at = r->frame + (uint32_t)END(&MV3_MOVES[r->move]);  // first IDLE frame of B
        if (free_at < (uint32_t)MV3B_BUF_MAX + 2u + s.w.frame) { CHECK(0, "reaction %s too short for the buffer test", MV3_MOVES[r->move].name); continue; }
        uint32_t press = free_at - MV3B_BUF_MAX - (uint32_t)late;
        sc_tap_at(&s, press, 1, MV3_B_ATK);
        CHECK(s.w.f[1].state == MV3_S_REACT, "press during the reaction");
        sc_run(&s, 40);
        int sw = ev_find(&s, MV3_E_SWING, 1, 0);
        if (!late) CHECK(sw == (int)free_at, "age %d press fires at %d (got %d)", MV3B_BUF_MAX, (int)free_at, sw);
        else       CHECK(sw < 0, "age %d press expired (got swing at %d)", MV3B_BUF_MAX + 1, sw);
    }
    // can-melee off holds the press inside the window
    sc_t t; duel(&t, 17);
    t.in[0].flags = 0;
    sc_tap_at(&t, 1, 0, MV3_B_ATK);
    sc_run(&t, 5);
    t.in[0].flags = 1;
    sc_run(&t, 1);
    CHECK(ev_find(&t, MV3_E_SWING, 0, 0) == 7, "can-melee gate: swing at 7 (%d)", ev_find(&t, MV3_E_SWING, 0, 0));
}
static void t_react_side(void)
{
    printf("reaction side: a blow from the victim's left plays a left reaction and carries it to its right\n");
    sc_t s; sc_init(&s, 19);
    sc_add(&s, 1, 0, 0, 0, 0);                                 // A faces +z: its left is +x (engine handedness)
    sc_add(&s, 2, 1, 1000, 0, -9000);                          // B on A's left, facing A (-x)
    sc_tap_at(&s, 1, 1, MV3_B_ATK);
    sc_run(&s, 200);
    const mv3_ev *r = ev_get(&s, MV3_E_REACT, 0, 0);
    CHECK(r && r->x == 1 && MV3_MOVES[r->move].dir == 1, "left reaction (dir %d, row %d)", r ? r->x : -1, r ? MV3_MOVES[r->move].dir : -1);
    CHECK(s.w.f[0].px < -50, "carried to its right (-x): x %d", s.w.f[0].px);
    sc_t t; sc_init(&t, 20);
    sc_add(&t, 1, 0, 0, 0, 0);
    sc_add(&t, 2, 1, -1000, 0, 9000);                          // on A's right
    sc_tap_at(&t, 1, 1, MV3_B_ATK);
    sc_run(&t, 200);
    const mv3_ev *q = ev_get(&t, MV3_E_REACT, 0, 0);
    int want = has_row(MV3_K_REACT, 2) ? 2 : -1;
    CHECK(q && q->x == 2 && (want < 0 || MV3_MOVES[q->move].dir == 2), "right reaction (dir %d)", q ? q->x : -1);
    if (want == 2) CHECK(t.w.f[0].px > 50, "carried to its left (+x): x %d", t.w.f[0].px);
}
static void t_iframes(void)
{
    printf("dodge i-frames vs a fist swing: any dodge from the windup to the contact frame avoids it, after the contact it is too late\n");
    const mv3_move *s1 = M(MV3_K_SWING1);
    int contact = 1 + s1->hit0_f, ok = 0, tried = 0;
    for (int at = 2; at <= contact; at++) {
        sc_t s; duel(&s, 21u + (uint32_t)at);
        sc_tap_at(&s, 1, 0, MV3_B_ATK);
        sc_tap_at(&s, (uint32_t)at, 1, MV3_B_DODGE);
        sc_run(&s, 60);
        const mv3_ev *d = ev_get(&s, MV3_E_DODGE, 1, 0);
        int inv = d && (contact - at) >= MV3_MOVES[d->move].iframe0_f && (contact - at) < MV3_MOVES[d->move].iframe1_f;
        if (!inv) continue;                                    // a press whose i-frames do not cover the contact (stub iframe0 2): not this test
        tried++;
        if (ev_count(&s, MV3_E_HIT, 0) == 0 && ev_find(&s, MV3_E_DODGED, 1, 0) == contact) ok++;
        else printf("    dodge at %d: hits %d dodged %d\n", at, ev_count(&s, MV3_E_HIT, 0), ev_find(&s, MV3_E_DODGED, 1, 0));
    }
    CHECK(tried > 0 && ok == tried, "%d of %d dodges avoided the blow", ok, tried);
    sc_t l; duel(&l, 40);
    sc_tap_at(&l, 1, 0, MV3_B_ATK);
    sc_tap_at(&l, (uint32_t)contact + 1, 1, MV3_B_DODGE);
    sc_run(&l, 60);
    CHECK(ev_count(&l, MV3_E_HIT, 0) == 1 && ev_count(&l, MV3_E_DODGE, 1) == 0, "a dodge after the contact: hit, no dodge (B is reacting)");
}
static void t_down(void)
{
    printf("hp crossing zero -> DOWN, fighter OUT\n");
    sc_t s; duel(&s, 18);
    s.w.f[1].hp = 100;
    sc_tap_at(&s, 1, 0, MV3_B_ATK);
    sc_run(&s, 40);
    CHECK(ev_count(&s, MV3_E_DOWN, 1) == 1 && s.w.f[1].state == MV3_S_OUT && ev_count(&s, MV3_E_REACT, 1) == 0, "down, no reaction");
    sc_tap_at(&s, s.w.frame + 1, 0, MV3_B_ATK);
    sc_run(&s, 40);
    CHECK(ev_count(&s, MV3_E_HIT, 0) == 1, "no hits on an OUT fighter");
}

// ---- random streams (fixed arrays: the pose is a scripted wander, not fed back, so two runs see the exact same inputs)
#define RN 4
#define RF 1200
static mv3_in g_rs[RF + 1][MV3_MAX_F];
static uint32_t lcg(uint32_t *s) { *s = *s * 1664525u + 1013904223u; return *s >> 8; }
static void make_stream(uint32_t seed)
{
    uint32_t r = seed; int32_t x[RN], z[RN], y[RN];
    for (int i = 0; i < RN; i++) { x[i] = (int32_t)(lcg(&r) % 1500); z[i] = (int32_t)(lcg(&r) % 1500); y[i] = (int32_t)(lcg(&r) % 36000) - 18000; }
    memset(g_rs, 0, sizeof g_rs);
    for (int f = 0; f <= RF; f++)
        for (int i = 0; i < RN; i++) {
            mv3_in *in = &g_rs[f][i];
            x[i] += (int32_t)(lcg(&r) % 41) - 20; z[i] += (int32_t)(lcg(&r) % 41) - 20; y[i] = mv3b_wrap(y[i] + (int32_t)(lcg(&r) % 401) - 200);
            in->px = x[i]; in->pz = z[i]; in->yaw = (int16_t)y[i]; in->flags = (lcg(&r) % 50) ? 1 : 0; in->wset = (uint8_t)(i % MV3_WS_N);   // every weapon set's rows
            uint32_t b = lcg(&r) % 100;
            in->btn = b < 12 ? MV3_B_ATK : b < 18 ? MV3_B_DODGE : b < 20 ? (MV3_B_ATK | MV3_B_DODGE) : 0;
            in->sx = (int8_t)((int)(lcg(&r) % 255) - 127); in->sy = (int8_t)((int)(lcg(&r) % 255) - 127);
        }
}
static void rworld(mv3_world *w, uint32_t seed)
{
    mv3_sim_init(w, seed);
    for (int i = 0; i < RN; i++) mv3_sim_add(w, (uint8_t)(i + 1), (uint8_t)(i & 1), &g_rs[0][i]);
}
static void t_determinism(void)
{
    printf("determinism: same random input stream twice -> identical hash every frame\n");
    static uint32_t h1[RF + 1];
    int evs = 0, changes = 0;
    for (uint32_t seed = 1; seed <= 4; seed++) {
        make_stream(seed * 7919u);
        mv3_world a, b; mv3_evbuf ea, eb;
        rworld(&a, seed); rworld(&b, seed);
        int bad = -1;
        uint32_t prev = 0;
        for (int f = 1; f <= RF; f++) {
            mv3_sim_step(&a, g_rs[f], &ea); h1[f] = mv3_sim_hash(&a);
            mv3_sim_step(&b, g_rs[f], &eb);
            if (bad < 0 && (mv3_sim_hash(&b) != h1[f] || memcmp(&ea, &eb, sizeof(int) + (size_t)ea.n * sizeof(mv3_ev)))) bad = f;
            evs += ea.n; if (h1[f] != prev) changes++; prev = h1[f];
        }
        CHECK(bad < 0, "seed %u diverged at frame %d", seed, bad);
    }
    printf("    4 streams x %d frames, %d events, hash changed on %d frames\n", RF, evs, changes);
    CHECK(evs > 200 && changes > RF, "the stream exercises the sim (events %d)", evs);
}
static void t_rollback(void)
{
    printf("rollback: snapshot at N, input change at N+3, resimulate == straight run of the corrected stream\n");
    static mv3_world snap[RF + 1];
    static mv3_in fixed[RF + 1][MV3_MAX_F];
    static uint32_t hc[RF + 1];
    int cases = 0, diverged = 0, bad = 0;
    for (uint32_t seed = 1; seed <= 3; seed++) {
        make_stream(seed * 104729u);
        for (int N = 40; N < RF - 100; N += 37) {
            int who = (N / 37) % RN;
            memcpy(fixed, g_rs, sizeof fixed);
            fixed[N + 3][who].btn ^= MV3_B_ATK;                // the late input differs from what was predicted
            if (N % 3 == 0) fixed[N + 3][who].btn ^= MV3_B_DODGE;
            // straight run of the corrected stream
            mv3_world w; mv3_evbuf ev;
            rworld(&w, seed);
            for (int f = 1; f <= RF; f++) { mv3_sim_step(&w, fixed[f], &ev); hc[f] = mv3_sim_hash(&w); }
            // predicted run with snapshots, then roll back to N (after frame N) and re-step with the correction
            rworld(&w, seed); snap[0] = w;
            for (int f = 1; f <= N + 10; f++) { mv3_sim_step(&w, g_rs[f], &ev); snap[f] = w; }
            int div = 0;
            for (int f = N + 5; f <= N + 10; f++) if (mv3_sim_hash(&snap[f]) != hc[f]) div = 1;   // past the prev_btn echo
            w = snap[N];
            int first_bad = -1;
            for (int f = N + 1; f <= RF; f++) { mv3_sim_step(&w, fixed[f], &ev); if (first_bad < 0 && mv3_sim_hash(&w) != hc[f]) first_bad = f; }
            cases++; diverged += div;
            if (first_bad >= 0) { bad++; printf("    seed %u N %d: mismatch at %d\n", seed, N, first_bad); }
        }
    }
    printf("    %d rollback cases, %d where the corrected input changed the outcome\n", cases, diverged);
    CHECK(bad == 0, "%d mismatches", bad);
    CHECK(diverged > cases / 4, "the corrections matter (%d of %d)", diverged, cases);
}
static void t_trig(void)
{
    printf("integer trig sanity\n");
    CHECK(mv3b_atan2(0, 1000) == 0 && mv3b_atan2(1000, 0) == 9000 && mv3b_atan2(-1000, 0) == -9000, "axes");
    int a = mv3b_atan2(0, -1000); CHECK(a == 18000 || a == -18000, "back %d", a);
    CHECK(mv3b_atan2(1000, 1000) == 4500 && mv3b_atan2(-577, 1000) == -2998, "diagonals %d %d", mv3b_atan2(1000, 1000), mv3b_atan2(-577, 1000));
    int worst = 0;
    for (int d = -18000; d <= 18000; d += 7) {
        int64_t s = mv3b_sin(d), c = mv3b_cos(d);
        int back = mv3b_wrap(mv3b_atan2(s * 1000, c * 1000) - d);
        if (back < 0) back = -back;
        if (back > worst) worst = back;
    }
    CHECK(worst <= 3, "sin/cos/atan2 round trip worst %d cdeg", worst);
    CHECK(mv3b_isqrt(1000000) == 1000 && mv3b_isqrt(999999) == 999, "isqrt");
}

// ---- script replay
typedef struct { uint32_t frame; int idx, kind; int v[4]; } cmd_t;
enum { C_HOLD, C_TAP, C_STICK, C_POSE, C_FLAGS };
static int run_script(const char *path)
{
    FILE *fp = fopen(path, "r");
    if (!fp) { printf("cannot open %s\n", path); return 2; }
    static sc_t s; static cmd_t cmd[65536]; int nc = 0, frames = 0; uint32_t seed = 1;
    char line[512], w0[32], w1[32];
    struct { int slot, team, x, z, yaw, wset, hp; } fi[MV3_MAX_F]; int nf = 0;
    s.follow = 1;                                       // the documented default (a static sc_t starts at 0)
    while (fgets(line, sizeof line, fp)) {
        char *h = strchr(line, '#'); if (h) *h = 0;
        if (sscanf(line, "%31s", w0) != 1) continue;
        cmd_t c = { 0 }; int n;
        if (!strcmp(w0, "seed")) sscanf(line, "%*s %u", &seed);
        else if (!strcmp(w0, "run")) sscanf(line, "%*s %d", &frames);
        else if (!strcmp(w0, "follow")) { sscanf(line, "%*s %d", &n); s.follow = n; }
        else if (!strcmp(w0, "fighter") && nf < MV3_MAX_F) {
            fi[nf].wset = MV3_WS_FIST; fi[nf].hp = MV3B_HP0;
            if (sscanf(line, "%*s %d %d %d %d %d %d %d", &fi[nf].slot, &fi[nf].team, &fi[nf].x, &fi[nf].z, &fi[nf].yaw, &fi[nf].wset, &fi[nf].hp) >= 5) nf++;
        }
        else if (!strcmp(w0, "hold") && sscanf(line, "%*s %u %d %d", &c.frame, &c.idx, &c.v[0]) == 3) { c.kind = C_HOLD; cmd[nc++] = c; }
        else if (!strcmp(w0, "tap") && sscanf(line, "%*s %u %d %31s", &c.frame, &c.idx, w1) == 3) {
            c.kind = C_TAP; c.v[0] = !strcmp(w1, "dodge") ? MV3_B_DODGE : MV3_B_ATK; cmd[nc++] = c;
        }
        else if (!strcmp(w0, "stick") && sscanf(line, "%*s %u %d %d %d", &c.frame, &c.idx, &c.v[0], &c.v[1]) == 4) { c.kind = C_STICK; cmd[nc++] = c; }
        else if (!strcmp(w0, "pose") && sscanf(line, "%*s %u %d %d %d %d", &c.frame, &c.idx, &c.v[0], &c.v[1], &c.v[2]) == 5) { c.kind = C_POSE; cmd[nc++] = c; }
        else if (!strcmp(w0, "flags") && sscanf(line, "%*s %u %d %d", &c.frame, &c.idx, &c.v[0]) == 3) { c.kind = C_FLAGS; cmd[nc++] = c; }
        else printf("? %s", line);
        if (nc >= 65536) break;
    }
    fclose(fp);
    int follow = s.follow;
    sc_init(&s, seed); s.follow = follow;
    for (int i = 0; i < nf; i++) {
        int k = sc_add(&s, fi[i].slot, fi[i].team, fi[i].x, fi[i].z, fi[i].yaw);
        s.in[k].wset = (uint8_t)fi[i].wset; s.w.f[k].wset = (uint8_t)fi[i].wset; s.w.f[k].hp = (int16_t)fi[i].hp;
    }
    if (!g_verbose) g_verbose = 1;
    for (int f = 1; f <= frames; f++) {
        for (int k = 0; k < nc; k++) {
            if (cmd[k].frame != (uint32_t)f || cmd[k].idx < 0 || cmd[k].idx >= MV3_MAX_F) continue;
            mv3_in *in = &s.in[cmd[k].idx];
            switch (cmd[k].kind) {
            case C_HOLD: in->btn = (uint8_t)cmd[k].v[0]; break;
            case C_TAP: s.tap[cmd[k].idx] |= (uint8_t)cmd[k].v[0]; break;
            case C_STICK: in->sx = (int8_t)cmd[k].v[0]; in->sy = (int8_t)cmd[k].v[1]; break;
            case C_POSE: in->px = cmd[k].v[0]; in->pz = cmd[k].v[1]; in->yaw = (int16_t)cmd[k].v[2]; break;
            case C_FLAGS: in->flags = (uint16_t)cmd[k].v[0]; break;
            }
        }
        sc_step(&s);
        if (g_verbose > 1)
            for (int i = 0; i < s.w.n; i++) {
                const mv3_fighter *q = &s.w.f[i];
                printf("  f=%d #%d %-9s mv=%d mf=%u pos=%d,%d yaw=%d hp=%d buf=%02x/%u tgt=%d\n", f, i, st_name[q->state], q->move, q->mf,
                       q->px, q->pz, q->yaw, q->hp, q->buf, q->buf_age, q->target == 0xff ? -1 : q->target);
            }
    }
    printf("%d frames, %d events, final hash %08x\n", frames, s.nlog, mv3_sim_hash(&s.w));
    return 0;
}

int main(int argc, char **argv)
{
    if (argc >= 3 && !strcmp(argv[1], "run")) {
        if (argc >= 4 && !strcmp(argv[3], "-v")) g_verbose = 2;
        return run_script(argv[2]);
    }
    printf("mv3 simtest: %d moves (%s)\n", MV3_MOVES_N,
#ifdef MV3_REAL_MOVES
           "mv3_moves.h"
#else
           "moves_stub.h"
#endif
    );
    t_trig(); t_single_hit(); t_combo(); t_mash(); t_dodge_nothing(); t_dodge(); t_iframes(); t_counter(); t_trade(); t_interrupt(); t_buffer();
    t_react_side(); t_down();
    t_determinism(); t_rollback();
    printf("%d checks passed, %d failed\n", g_pass, g_fail);
    return g_fail ? 1 : 0;
}
