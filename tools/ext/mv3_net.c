// mv3_net.c - melee v3 net (spec re/melee-v3.md): the bubble session + rollback netcode for the ext. The engine-free core is mv3_net_core.h
// (shared with the offline test tools/mv3/nettest.c); this file is its engine side: MSG_MV3 through g_send_tramp, the QPC clock, our slot / teams /
// psync RTT, the mv3_glue_* callbacks, a lock (recv and tick may come from different threads), and the Net interface of re/melee-v3-brief.md.
// Included by t2r-ext.c after the melee modules (uses xlog, LOGCAP, VMA, g_send_tramp, g_ps_rtt (paired.c), team_of_slot, match_substate).
// Log lines: "mv3 net: ..." - session start (delay, t0, seed) / join / leave / END with the reason and totals, a 5 s summary (rollbacks: count, frames,
// longest; late inputs; stalls; desyncs; rtt; clock offset + trim), desyncs + resyncs, stalls.
#ifndef MSG_MV3
#define MSG_MV3 0x9E               // peer msg (ours): melee v3 bubble / inputs / hash (0x9D is MSG_HELPCALL)
#endif
#define MV3N_LOGCAP(c, n) LOGCAP(c, n)
#include "mv3_net_core.h"
static void mv3_glue_input(mv3_in *out);                 // mv3_glue.c
static void mv3_glue_events(const mv3_evbuf *ev, int resim);
static void mv3_glue_rolled_back(uint32_t to_frame);
static void mv3_glue_frame(const mv3_world *w);
static int16_t mv3_glue_hp10(uint32_t slot);

static mv3n_ctx g_mv3n;
static CRITICAL_SECTION g_mv3n_cs;
static volatile LONG g_mv3n_once;          // 0 none, 1 initialising, 2 ready
static uint32_t g_mv3n_me = 0xff;
static int64_t g_mv3n_gtc_off; static uint64_t g_mv3n_gtc_at;   // GetTickCount64 ms * 1000 - our QPC us (best = largest seen: GetTickCount lags up to 15.6 ms)

static uint64_t mv3n_qpc_us(void) {
    static LARGE_INTEGER f; LARGE_INTEGER q;
    if (!f.QuadPart) QueryPerformanceFrequency(&f);
    QueryPerformanceCounter(&q);
    return (uint64_t)(q.QuadPart / f.QuadPart) * 1000000ull + (uint64_t)(q.QuadPart % f.QuadPart) * 1000000ull / (uint64_t)f.QuadPart;
}
static void mv3n_e_send(void *u, uint32_t to, const uint8_t *b, int len) { (void)u; if (g_send_tramp && to < T2R_MAX_PEERS) g_send_tramp(MSG_MV3, (uint8_t *)b, (uint64_t)len, to); }
static void mv3n_e_input(void *u, mv3_in *out) { (void)u; mv3_glue_input(out); }
static void mv3n_e_events(void *u, const mv3_evbuf *ev, int resim) { (void)u; mv3_glue_events(ev, resim); }
static void mv3n_e_rolled(void *u, uint32_t f) { (void)u; mv3_glue_rolled_back(f); }
static void mv3n_e_frame(void *u, const mv3_world *w) { (void)u; mv3_glue_frame(w); }
static int16_t mv3n_e_hp(void *u) { (void)u; return mv3_glue_hp10(g_mv3n_me); }
static int mv3n_e_team(void *u, uint32_t s) { (void)u; return team_of_slot(s); }
static float mv3n_e_rtt(void *u, uint32_t s) { (void)u; return s < T2R_MAX_PEERS ? g_ps_rtt[s] : 0.0f; }
static void mv3n_e_log(void *u, const char *m) { (void)u; xlog("%s", m); }

static int mv3n_lock(void) {
    LONG st = InterlockedCompareExchange(&g_mv3n_once, 1, 0);
    if (st == 0) {
        InitializeCriticalSection(&g_mv3n_cs);
        mv3n_io io = { NULL, mv3n_e_send, mv3n_e_input, mv3n_e_events, mv3n_e_rolled, mv3n_e_frame, mv3n_e_hp, mv3n_e_team, mv3n_e_rtt, mv3n_e_log, NULL };
        mv3n_init(&g_mv3n, &io, 0xff);
        InterlockedExchange(&g_mv3n_once, 2);
    } else while (g_mv3n_once != 2) Sleep(0);
    EnterCriticalSection(&g_mv3n_cs);
    return 1;
}
static void mv3n_unlock(void) { LeaveCriticalSection(&g_mv3n_cs); }
static void mv3n_slot_check(uint64_t now) {     // our session slot: a change (rejoin, host migration) ends whatever we had
    uint32_t me = *(uint32_t *)VMA(0x180138090);
    if (me >= T2R_MAX_PEERS) me = 0xff;
    if (me == g_mv3n_me) return;
    if (g_mv3n.state != MV3N_IDLE) mv3n_hard_end(&g_mv3n, MV3N_END_ABORT, "our slot changed", now);
    xlog("mv3 net: our slot %u -> %u", g_mv3n_me, me);
    g_mv3n_me = me; g_mv3n.me = (uint8_t)me;
}

// ---------------------------------------------------------------- Net interface (re/melee-v3-brief.md)
static void mv3_net_tick(uint64_t now_ms) {
    (void)now_ms;                                // the glue's GetTickCount64: too coarse for the clock sync, QPC is used inside
    if (!g_winmm) return;
    mv3n_lock();
    uint64_t now = mv3n_qpc_us();
    {
        int64_t d = (int64_t)GetTickCount64() * 1000 - (int64_t)now;
        if (!g_mv3n_gtc_at || d > g_mv3n_gtc_off || now - g_mv3n_gtc_at > 10000000) { g_mv3n_gtc_off = d; g_mv3n_gtc_at = now; }
    }
    mv3n_slot_check(now);
    if (match_substate() != 6) { if (g_mv3n.state != MV3N_IDLE) mv3n_hard_end(&g_mv3n, MV3N_END_MATCH, NULL, now); }
    else if (g_mv3n_me < T2R_MAX_PEERS) mv3n_tick(&g_mv3n, now);
    mv3n_unlock();
}
static void mv3_recv(uint32_t from, const uint8_t *buf, uint64_t len) {
    if (!g_winmm || from >= T2R_MAX_PEERS || !buf || len < 3 || len > MV3N_PKT) return;
    mv3n_lock();
    if (g_mv3n_me < T2R_MAX_PEERS && match_substate() == 6) mv3n_recv(&g_mv3n, from, buf, len, mv3n_qpc_us());
    mv3n_unlock();
}
// 1 = a bubble with that slot runs, or the proposal / join request / invite is on its way (glue: check mv3_net_active() / idx_of_slot later); 0 = refused
// (teammate, busy with another proposal, leaving, not in a match)
static int mv3_net_propose(uint32_t slot) {
    if (!g_winmm || slot >= T2R_MAX_PEERS || match_substate() != 6) return 0;
    mv3n_lock();
    int r = g_mv3n_me < T2R_MAX_PEERS ? mv3n_propose(&g_mv3n, slot, mv3n_qpc_us()) : 0;
    mv3n_unlock();
    return r;
}
// our own leave: a bit in our input stream at the next frame we sample, so every machine drops our fighter at the same frame. A 1v1 bubble then ends on
// both machines at that frame ("bubble over"); in a 3+ bubble the others fight on.
static void mv3_net_end(const char *why) {
    mv3n_lock();
    mv3n_end(&g_mv3n, why, mv3n_qpc_us());
    mv3n_unlock();
}
static int mv3_net_active(void) { return g_mv3n.state == MV3N_ACTIVE; }
static const mv3_world *mv3_net_world(void) { return &g_mv3n.w; }
static int mv3_net_local_idx(void) { return g_mv3n.state == MV3N_ACTIVE ? mv3n_idx_of(&g_mv3n.w, g_mv3n.me) : -1; }
static uint32_t mv3_net_confirmed(void) { return g_mv3n.conf; }
static int mv3_net_idx_of_slot(uint32_t slot) { return g_mv3n.state == MV3N_ACTIVE ? mv3n_idx_of(&g_mv3n.w, slot) : -1; }
static int mv3_net_slot_of_idx(int idx) { return idx >= 0 && idx < MV3_MAX_F && g_mv3n.w.f[idx].slot != 0xff ? g_mv3n.w.f[idx].slot : -1; }
static uint32_t mv3_net_frame_ms(uint32_t frame) {        // GetTickCount64 time (low 32 bits) of a world frame on this machine
    if (g_mv3n.state != MV3N_ACTIVE) return (uint32_t)GetTickCount64();
    return (uint32_t)(((int64_t)mv3n_frame_local_us(&g_mv3n, frame) + g_mv3n_gtc_off) / 1000);
}
// the owner's engine hp x10 (glue, at bubble start and on change). Only our own fighter's: it rides in our input stream (hp_set at one frame, applied by
// every sim before that step); a report for another fighter is ignored - its owner reports it.
static void mv3_net_set_hp(int idx, int16_t hp10) {
    mv3n_lock();
    int li = mv3_net_local_idx();
    if (idx < 0 || idx == li) mv3n_set_hp(&g_mv3n, hp10);
    else { static int nl; if (LOGCAP(nl, 8)) xlog("mv3 net: hp report for fighter %d ignored (we are %d; each owner reports its own)", idx, li); }
    mv3n_unlock();
}
// drop a fighter (downed) from the bubble. Ours: our leave bit (agreed frame = the next one we sample; `frame` is not needed). Another slot's: its owner
// leaves through its own stream (a remote can not be removed at an agreed frame from here), so this only logs.
static void mv3_net_remove(uint32_t slot, uint32_t frame) {
    mv3n_lock();
    if (slot == g_mv3n_me) mv3n_end(&g_mv3n, "removed (down)", mv3n_qpc_us());
    else { static int nl; if (LOGCAP(nl, 8)) xlog("mv3 net: remove of slot %u at frame %u ignored - its owner leaves through its own input stream", slot, frame); }
    mv3n_unlock();
}

#ifdef MV3N_GLUE_STUBS
// inert callbacks so t2r-ext.c compiles without mv3_glue.c; the real ones live in mv3_glue.c.
static void mv3_glue_input(mv3_in *out) { if (out) memset(out, 0, sizeof *out); }
static void mv3_glue_events(const mv3_evbuf *ev, int resim) { (void)ev; (void)resim; }
static void mv3_glue_rolled_back(uint32_t to_frame) { (void)to_frame; }
static void mv3_glue_frame(const mv3_world *w) { (void)w; }
static int16_t mv3_glue_hp10(uint32_t slot) { (void)slot; return -1; }
#endif
