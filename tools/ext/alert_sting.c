// Alert sting: TLOU2's t2-hud-stealth-notification (tools/rip_alert_sting.py -> alert_sting.pcm), 2D through the PCM mixer at the
// music volume (exmus_user_volume):
//  (a) combat: when it is quiet and suddenly we get shot at (in our direction or hit), the sting plays - an enemy shot that
//      hits us (music_event "we took a hit") or passes close (immersion.c near miss) while the combat music is calm (tier 0) and no enemy-caused
//      music input came for ALS_QUIET_MS;
//  (b) shiv: a prominent shiv stinger, ONLY for shivs from behind and non stunned - the victim of shiv-stealth-back who is not
//      stunned (shivsting_start), louder, on top of the shock sting.
// Never twice within ALS_GAP_MS. t2r-no-alert-sting.txt next to the exe: off. Logs 'alert sting: ...'.
// Included from t2r-ext.c after shiv_sting.c (uses exmus_user_volume, pcm_play_voice, g_mixv).
#include "alert_sting.h"
__asm__(".section .rdata,\"dr\"\n.balign 4\n.globl als_blob\nals_blob:\n.incbin \"alert_sting.pcm\"\n.text\n");
extern const int16_t als_blob[];
#define ALS_QUIET_MS 15000
#define ALS_GAP_MS 6000
static uint64_t g_als_last;
static void alertsting_play(float level, const char *why) {
    static int off = -1;
    if (off < 0) { FILE *f = exe_side_open("t2r-no-alert-sting.txt", "r"); off = f != NULL; if (f) fclose(f); if (off) xlog("alert sting: off (t2r-no-alert-sting.txt)"); }
    if (off || match_substate() != 6) return;
    uint64_t now = GetTickCount64();
    if (g_als_last && now - g_als_last < ALS_GAP_MS) { xlog("alert sting: %s ignored - played %llu ms ago", why, (unsigned long long)(now - g_als_last)); return; }
    float g = level * exmus_user_volume();
    if (g <= 0.0f) return;
    if (!pcm_play_voice(als_blob, 2, 0.0f, 0.0f, AL_RATE, 0, 0, NULL, 1.0f) || g_mix_state != 1) { xlog("alert sting: %s - mixer off", why); return; }     // (starts the mixer if needed)
    EnterCriticalSection(&g_mix_cs);
    int a = -1, b = -1;
    for (int v = 0; v < MIX_VOICES && b < 0; v++) { if (g_mixv[v].on) continue; if (a < 0) a = v; else b = v; }
    if (b >= 0) {
        const int16_t *src[2] = {als_blob, als_blob + AL_N};
        int vv[2] = {a, b};
        for (int k = 0; k < 2; k++) {
            int v = vv[k];
            g_mixv[v].src = src[k]; g_mixv[v].n = AL_N; g_mixv[v].pos = 0.0; g_mixv[v].step = (double)AL_RATE / MIX_RATE; g_mixv[v].played = 0;
            g_mixv[v].fadeN = 0;
            g_mixv[v].gl = g_mixv[v].tgl = k ? 0.0f : g; g_mixv[v].gr = g_mixv[v].tgr = k ? g : 0.0f;
            g_mixv[v].dyn = 0; g_mixv[v].ent = 0; g_mixv[v].base = 1.0f; memset(g_mixv[v].wp, 0, 12);
            g_mixv[v].on = 1;
        }
    }
    LeaveCriticalSection(&g_mix_cs);
    if (b >= 0) g_als_last = now;
    xlog("alert sting: %s - %s (%.2f s, gain %.2f)", why, b >= 0 ? "playing" : "NOT played (voices busy)", AL_N / (double)AL_RATE, (double)g);
}
// (a) "quiet" = the music was calm (tier 0) until at most 1.5 s ago (the same burst's 'enemy shot heard' raises the tier a few frames before the hit /
// whizz lands) and no shot hit or passed us for ALS_QUIET_MS
static uint64_t g_als_calm_ms, g_als_threat_ms, g_als_due;
static const char *g_als_due_why;
#define ALS_DELAY_MS 100

// ---- 2D stereo one-shots with their voices kept (so they can be faded): g_mixv slots a / b + the source they were started with
typedef struct { int a, b; const int16_t *l, *r; } als_v2;
static int als_v2_live(const als_v2 *v) {
    if (v->a < 0 || g_mix_state != 1) return 0;
    EnterCriticalSection(&g_mix_cs);
    int on = g_mixv[v->a].on && g_mixv[v->a].src == v->l;
    LeaveCriticalSection(&g_mix_cs);
    return on;
}
static int als_v2_play(als_v2 *v, const int16_t *l, const int16_t *r, int n, int rate, float g) {
    v->a = v->b = -1; v->l = l; v->r = r;
    if (g <= 0.0f || !pcm_play_voice(l, 2, 0.0f, 0.0f, rate, 0, 0, NULL, 1.0f) || g_mix_state != 1) return 0;     // (starts the mixer if needed)
    EnterCriticalSection(&g_mix_cs);
    int a = -1, b = -1;
    for (int i = 0; i < MIX_VOICES && b < 0; i++) { if (g_mixv[i].on) continue; if (a < 0) a = i; else b = i; }
    if (b >= 0) {
        const int16_t *src[2] = {l, r};
        int vv[2] = {a, b};
        for (int k = 0; k < 2; k++) {
            int i = vv[k];
            g_mixv[i].src = src[k]; g_mixv[i].n = n; g_mixv[i].pos = 0.0; g_mixv[i].step = (double)rate / MIX_RATE; g_mixv[i].played = 0; g_mixv[i].fadeN = 0;
            g_mixv[i].gl = g_mixv[i].tgl = k ? 0.0f : g; g_mixv[i].gr = g_mixv[i].tgr = k ? g : 0.0f;
            g_mixv[i].dyn = 0; g_mixv[i].ent = 0; g_mixv[i].base = 1.0f; memset(g_mixv[i].wp, 0, 12);
            g_mixv[i].on = 1;
        }
        v->a = a; v->b = b;
    }
    LeaveCriticalSection(&g_mix_cs);
    return b >= 0;
}
static void als_v2_fade(als_v2 *v, int ms) {
    if (v->a < 0) return;
    if (g_mix_state == 1) {
        EnterCriticalSection(&g_mix_cs);
        int vv[2] = {v->a, v->b};
        for (int k = 0; k < 2; k++) {
            int i = vv[k];
            if (i < 0 || !g_mixv[i].on || g_mixv[i].src != (k ? v->r : v->l)) continue;     // slot already reused by another sound
            if (ms <= 0) g_mixv[i].on = 0; else g_mixv[i].fadeLeft = g_mixv[i].fadeN = ms * MIX_RATE / 1000;
        }
        LeaveCriticalSection(&g_mix_cs);
    }
    v->a = v->b = -1;
}

// ---- stun tone (SP's low ear-split concussion cue, synced to the explosion): started at the frame the enemy stun
// bomb's copy bursts on our screen when we are inside its stun radius (stuntone_burst, ~0.1 s before the stun is judged at the thrower's burst point);
// stun_local confirms it (or starts it, when no burst was seen: a thrower-side burst message only); not confirmed within 0.7 s = not stunned:
// faded out over 0.15 s. Played at the sfx volume.
#include "stun_tone.h"
__asm__(".section .rdata,\"dr\"\n.balign 4\n.globl st_blob\nst_blob:\n.incbin \"stun_tone.pcm\"\n.text\n");
extern const int16_t st_blob[];
#include "stun_ring.h"
__asm__(".section .rdata,\"dr\"\n.balign 4\n.globl sr_blob\nsr_blob:\n.incbin \"stun_ring.pcm\"\n.text\n");
extern const int16_t sr_blob[];
static struct { als_v2 v; uint64_t t0; int confirmed; } g_stt = {{-1, -1, NULL, NULL}, 0, 0};
// The SP ear-split wave is no tone, it is a sub-bass thump - 99 % of its energy after the first
// second is below 300 Hz (89 % below 150 Hz, rms 0.07 from 1 s on), inaudible on most speakers / headphones. The stun bed is therefore built here
// once: the ear-split impact (first ~1 s: the crack + thump) under the SP tinnitus tone's steady body (sh_blob, ~410 Hz, 86 % of its energy in
// 300-1000 Hz: a dull ring, not a high whine), looped with 0.25 s crossfades and a slow +-12 % swell, coming in over 0.12 s and fading out with a
// raised cosine over the last 1.5 s so it ends ~0.1 s before the stun lock does (the lock is 3.5 s, the voice starts ~0.1 s before it is judged).
#define STT_LEN_S 3.45f
#define STT_N ((int)(STT_LEN_S * ST_RATE))
static int16_t g_stt_l[STT_N], g_stt_r[STT_N];
static int g_stt_built;
// The ring is the SP tinnitus wave itself (stun_ring.pcm,
// audition/downed-shock 02, ~410 Hz), played as is from STT_RING_AT into the ear-split's crack, faded in over STT_RING_IN; the bed's tail fade still ends it.
#define STT_RING_AT 0.30f
#define STT_RING_IN 0.40f
static void stuntone_build(void) {
    if (g_stt_built) return;
    const int16_t *ring[2] = {sr_blob, sr_blob + SR_N}, *hit[2] = {st_blob, st_blob + ST_N};
    const int R0 = (int)(STT_RING_AT * ST_RATE);
    int16_t *out[2] = {g_stt_l, g_stt_r};
    const float fo = 1.5f, T = (float)STT_N / ST_RATE;
    for (int c = 0; c < 2; c++) {
        for (int i = 0; i < STT_N; i++) {
            float t = (float)i / ST_RATE, env = t < 0.12f ? t / 0.12f : 1.0f;
            if (t > T - fo) { float u = (t - (T - fo)) / fo; env *= 0.5f * (1.0f + __builtin_cosf(3.14159265f * u)); }
            int ri = i - R0;
            float rin = ri <= 0 ? 0.0f : ri >= (int)(STT_RING_IN * ST_RATE) ? 1.0f : (float)ri / (STT_RING_IN * ST_RATE);
            float rs = ri >= 0 && ri < SR_N ? ring[c][ri] * rin * rin * (3.0f - 2.0f * rin) : 0.0f;
            float hf = t < T - 0.4f ? 1.0f : (T - t) / 0.4f;                       // (the impact wave's own tail is cut with a short fade)
            float x = rs * env + hit[c][i] * hf;
            x = x > 32000.0f ? 32000.0f : x < -32000.0f ? -32000.0f : x;
            out[c][i] = (int16_t)x;
        }
    }
    g_stt_built = 1;
}
static void stuntone_burst(uint32_t slot, const float *at, float radius) {
    if (match_substate() != 6 || g_downed || g_down_dying || g_uc4_dying_until || local_hp() <= 0.0f || !at) return;
    float lb[16];
    const float *pl = uc4_my_loc(lb);
    if (!pl) return;
    float dx = at[0] - pl[0], dy = at[1] + 0.0f - (pl[1] + 1.0f), dz = at[2] - pl[2], d = __builtin_sqrtf(dx * dx + dy * dy + dz * dz);
    if (!(d <= radius + 0.5f)) return;
    if (g_stt.v.a >= 0 && als_v2_live(&g_stt.v) && GetTickCount64() - g_stt.t0 < 1500) return;
    int ok = (stuntone_build(), als_v2_play(&g_stt.v, g_stt_l, g_stt_r, STT_N, ST_RATE, 0.8f * sfx_user_volume()));
    g_stt.t0 = GetTickCount64(); g_stt.confirmed = 0;
    xlog("stun: concussion tone at slot %u's bomb burst on our screen (%.2f m, radius %.1f) -> %d (stun not judged yet)", slot, d, radius, ok);
}
static void stuntone_stunned(void) {
    uint64_t now = GetTickCount64();
    if (g_stt.v.a >= 0 && now - g_stt.t0 < 1500 && als_v2_live(&g_stt.v)) { g_stt.confirmed = 1; xlog("stun: concussion tone confirmed (%llu ms after the burst)", (unsigned long long)(now - g_stt.t0)); return; }
    int ok = (stuntone_build(), als_v2_play(&g_stt.v, g_stt_l, g_stt_r, STT_N, ST_RATE, 0.8f * sfx_user_volume()));
    g_stt.t0 = now; g_stt.confirmed = 1;
    xlog("stun: concussion tone (no burst seen on our screen) -> %d", ok);
}
static void stuntone_tick(void) {
    if (g_stt.v.a < 0) return;
    uint64_t now = GetTickCount64();
    if (!g_stt.confirmed && now - g_stt.t0 > 700) { als_v2_fade(&g_stt.v, 150); xlog("stun: concussion tone faded - the burst did not stun us"); return; }
    if (match_substate() != 6) { als_v2_fade(&g_stt.v, 100); return; }
    // the stun ended early (downed / killed / shiv cut it): the bed does not ring on over the down
    if (g_stt.confirmed && now - g_stt.t0 > 900 && !stun_fx_live()) { als_v2_fade(&g_stt.v, 250); xlog("stun: concussion tone faded - the stun (lock or Launcher stun fx) is over"); return; }
    if (!als_v2_live(&g_stt.v)) g_stt.v.a = g_stt.v.b = -1;
}

// ---- crossbow bolt in us: SP's arrow HUD sounds of
// gbl-hud.bnk (xbow_hud.pcm): hud-arrow-impact-1 when a bolt goes in (each new hit), hud-tonal-arrow-impaled-pulse-01 repeated back to back while it
// stays in, hud-arrow-impact-complete-02 when it is pulled out (g_xb_out_pull: xb_clear by a pull). Sfx volume, 2D.
#include "xbow_hud.h"
__asm__(".section .rdata,\"dr\"\n.balign 4\n.globl xbh_blob\nxbh_blob:\n.incbin \"xbow_hud.pcm\"\n.text\n");
extern const int16_t xbh_blob[];
static als_v2 g_xbh_pulse = {-1, -1, NULL, NULL}, g_xbh_one = {-1, -1, NULL, NULL};
static void xbhud_tick(void) {
    static int was; static uint64_t hit_seen, next_pulse;
    uint64_t now = GetTickCount64();
    float vol = sfx_user_volume();
    int on = g_xb.on && match_substate() == 6;
    if (on && (!was || g_xb.hit_ms != hit_seen)) {
        hit_seen = g_xb.hit_ms;
        int ok = als_v2_play(&g_xbh_one, xbh_blob + XBI_OFF, xbh_blob + XBI_OFF + XBI_N, XBI_N, XBI_RATE, 0.8f * vol);
        next_pulse = now + 900;      // the pulse comes in under the impact's tail
        xlog("crossbow hud: impact sound -> %d", ok);
    }
    if (on && now >= next_pulse) {
        als_v2_play(&g_xbh_pulse, xbh_blob + XBP_OFF, xbh_blob + XBP_OFF + XBP_N, XBP_N, XBP_RATE, 0.55f * vol);
        next_pulse = now + (uint64_t)XBP_N * 1000 / XBP_RATE;
    }
    if (!on && was) {
        als_v2_fade(&g_xbh_pulse, 200);
        if (g_xb_out_pull && match_substate() == 6) {
            int ok = als_v2_play(&g_xbh_one, xbh_blob + XBC_OFF, xbh_blob + XBC_OFF + XBC_N, XBC_N, XBC_RATE, 0.8f * vol);
            xlog("crossbow hud: pulled-out sound -> %d", ok);
        }
        g_xb_out_pull = 0;
    }
    was = on;
}
// ---- stun cough
// TLOU2's own vox-eff-gen-cough-light speech takes (tools/rip_stun_cough.py -> stun_cough.pcm, 6 male
// + 6 female voices) through the PCM mixer instead of the engine's say (local only, quiet, first one late). The first cough the frame the stun starts,
// then one every SC_EVERY_MS for the stun lock, by the body's gender, random without repeats:
//  * a stunned enemy / teammate puppet: 3-D on its body, full within 12 m, silent past 50 m (louder than the world's own vox);
//  * our own stun: 2-D through a one-pole low-pass copy (~900 Hz), under the stun muffle.
#include "stun_cough.h"
__asm__(".section .rdata,\"dr\"\n.balign 4\n.globl sc_blob\nsc_blob:\n.incbin \"stun_cough.pcm\"\n.text\n");
extern const int16_t sc_blob[];
#define SC_EVERY_MS 1150
static int16_t *g_sc_muf;
static int sc_pick(int female) {
    static int prev[2] = {-1, -1};
    int ids[SC_N], n = 0;
    for (int i = 0; i < SC_N; i++) if ((SC_WAVE[i].female != 0) == (female != 0) && i != prev[female != 0]) ids[n++] = i;
    if (!n) return -1;
    int w = ids[t2r_rand() % n];
    prev[female != 0] = w;
    return w;
}
static const int16_t *sc_muffled(void) {
    if (g_sc_muf) return g_sc_muf;
    unsigned tot = SC_WAVE[SC_N - 1].off + SC_WAVE[SC_N - 1].n;
    int16_t *m = (int16_t *)malloc(tot * sizeof(int16_t));
    if (!m) return NULL;
    const float a = 0.889f;      // exp(-2 pi 900 / 48000)
    for (int k = 0; k < SC_N; k++) {     // per wave (no smear across the boundaries), two poles for a softer top
        float y1 = 0.0f, y2 = 0.0f;
        for (unsigned i = SC_WAVE[k].off; i < SC_WAVE[k].off + SC_WAVE[k].n; i++) {
            y1 = a * y1 + (1.0f - a) * (float)sc_blob[i];
            y2 = a * y2 + (1.0f - a) * y1;
            float v = y2 * 1.6f;     // the low-pass loses level: brought back up
            m[i] = (int16_t)(v > 32767.0f ? 32767.0f : v < -32768.0f ? -32768.0f : v);
        }
    }
    g_sc_muf = m;
    return m;
}
static void stuncough_tick(void) {
    static uint64_t own_next, pup_next[T2R_MAX_PEERS], pup_at[T2R_MAX_PEERS];
    static int own_was;
    uint64_t now = GetTickCount64();
    int live = match_substate() == 6;
    int own = live && g_stun_until && g_t60 < g_stun_until && !g_downed && !g_down_dying && !g_uc4_dying_until && !psync_active() && local_hp() > 0.0f;
    if (own && (!own_was || now >= own_next)) {
        const int16_t *m = sc_muffled();
        int w = sc_pick(own_female());
        int ok = m && w >= 0 ? pcm_play_lr(m + SC_WAVE[w].off, (int)SC_WAVE[w].n, 0.9f, 0.9f, SC_RATE) : 0;
        if (!own_was) xlog("stun cough: ours (muffled) starts - %s -> %d", w >= 0 ? SC_NAME[w] : "-", ok);
        own_next = now + SC_EVERY_MS;
    }
    own_was = own;
    for (int s = 0; s < T2R_MAX_PEERS; s++) {
        if (!live || !g_stun_pup_at[s] || g_peer_downed[s] || g_puppet_dead_here[s]) { pup_at[s] = 0; continue; }
        int fresh = pup_at[s] != g_stun_pup_at[s];
        if (!fresh && now < pup_next[s]) continue;
        pup_at[s] = g_stun_pup_at[s];
        pup_next[s] = now + SC_EVERY_MS;
        if (g_t60 - g_stun_pup_at[s] >= S60(STUN_SECONDS - 0.3f)) continue;
        typedef uint8_t *(*fn_peer)(uint32_t);
        uint8_t *pe = ((fn_peer)t2r_peer)((uint32_t)s);
        uint64_t h = pe && pe[4] && !pe[5] ? *(uint64_t *)(pe + 0x60) : 0;
        int w = sc_pick(slot_female((uint8_t)s));
        if (!h || w < 0) continue;
        g_mix_rnear = 2.5f; g_mix_rfar = 45.0f;     // a real distance cue (was a flat 12 m plateau: heard as 2D); gain 1.4 keeps it audible feedback
        int ok = pcm_play_at(sc_blob + SC_WAVE[w].off, (int)SC_WAVE[w].n, 1.4f, SC_RATE, h);
        g_mix_rnear = g_mix_rfar = 0.0f;
        if (fresh) xlog("stun cough: slot %d's puppet starts coughing - %s -> %d", s, SC_NAME[w], ok);
    }
}
static void alertsting_tick(void) {
    if (g_ms_tier == 0) g_als_calm_ms = GetTickCount64();
    if (g_als_due && GetTickCount64() >= g_als_due) {
        g_als_due = 0;
        if (!g_ms_dead && !g_downed) alertsting_play(0.8f, g_als_due_why ? g_als_due_why : "shot at");
    }
    stuntone_tick();
    xbhud_tick();
    stuncough_tick();
}
static void alertsting_combat(const char *why) {
    uint64_t now = GetTickCount64(), prev = g_als_threat_ms;
    g_als_threat_ms = now;
    if (g_ms_dead || g_downed || match_substate() != 6) return;
    if (!g_als_calm_ms || now - g_als_calm_ms > 1500) return;
    if (prev && now - prev < ALS_QUIET_MS) return;
    g_als_due = now + ALS_DELAY_MS; g_als_due_why = why;      // delayed ~0.1 s: it played too soon, right after getting hit (alertsting_tick)
}
