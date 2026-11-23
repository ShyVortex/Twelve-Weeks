// Death screen drone
// . A pool of TLOU2 SP tonal beds,
// one picked at random per death (never the same twice in a row), plays 2D through the PCM mixer at the options menu's MUSIC volume (exmus_user_volume),
// stereo as two hard-panned voices. Each wave is 16 s with a 1 s equal-power fade-in and fade-out baked in.
//   start : death_ui.c arms it with the death sting (dth_arm) and it starts RIGHT THEN (an execution victim: under the victim cue, no wait).
//   duck  : the beds start right away and are muted by whatever is currently playing, synced with the death stinger
//           fading out and special execution stingers too - a sidechain: every frame the live level of every other 2D mixer voice longer than
//           0.5 s (death sting, execution victim cue, shiv sting, any later music cue) is read from its wave just ahead of its play position; the
//           drone sits at DTH_BED x (1 - that level / DTH_DUCK_FULL)^2, floored at DTH_FLOOR (near silent), fast down (60 ms), slow up (700 ms), so it
//           rises as the sting's tail fades and drops away whenever a cue hits.
//   loop  : a new copy starts every (wave length - fade) so the copies overlap by the baked fades = a seamless crossfade loop for as long as the
//           death screen lasts.
//   end   : dth_tick(phase, final) from feature_death_ui: respawn (phase 2) / countdown fade to black / match end / match left the playing
//           state / death screen off -> 600 ms fade-out once (edge-triggered); no further copies start.
// Other music is NOT touched. Client-side, only the dying player hears it. Kill switch t2r-no-death-drone.txt next to the exe (the old
// t2r-no-death-theme.txt still counts). Logs 'death drone: ...'.
// Included from t2r-ext.c after exec_music.c / shiv_sting.c, before death_ui.c.
#include "death_drone.h"
__asm__(".section .rdata,\"dr\"\n.balign 4\n.globl dr_blob\ndr_blob:\n.incbin \"death_drone.pcm\"\n.text\n");
extern const int16_t dr_blob[];
#define DTH_BED 0.30f                // the bed level with nothing else playing
#define DTH_FLOOR 0.02f              // ducked: near silent (-24 dB under the bed)
#define DTH_DUCK_FULL 0.25f          // a foreground cue this loud (peak x its gain) ducks the drone all the way to the floor
#define DTH_DOWN_S 0.06f             // duck attack
#define DTH_UP_S 0.70f               // duck release: follows a sting's tail fade
#define DTH_FADE_MS 600
#define DTH_MAX_INST 3
#define DTH_N DR_N
static struct { int a[DTH_MAX_INST], b[DTH_MAX_INST]; uint64_t t0[DTH_MAX_INST]; int armed, fading, count, cue; uint64_t arm_t0, first_t0, tick_t; float lvl, fg; const int16_t *src; } g_dth;
static int dth_off(void) {
    static uint64_t at, at2; static int off, off2;
    return feel_flag("t2r-no-death-drone.txt", &at, &off, 120) | feel_flag("t2r-no-death-theme.txt", &at2, &off2, 120);
}
static int dth_inst_live(int i) {
    if (g_dth.a[i] < 0 || !g_dth.src || g_mix_state != 1) return 0;
    int on = 0;
    EnterCriticalSection(&g_mix_cs);
    for (int k = 0; k < 2; k++) {
        int v = k ? g_dth.b[i] : g_dth.a[i];
        if (v >= 0 && g_mixv[v].on && g_mixv[v].src == g_dth.src + (k ? DTH_N : 0)) on = 1;
    }
    LeaveCriticalSection(&g_mix_cs);
    return on;
}
static int dth_live(void) {
    for (int i = 0; i < DTH_MAX_INST; i++) if (dth_inst_live(i)) return 1;
    return 0;
}
static void dth_reset(void) {
    for (int i = 0; i < DTH_MAX_INST; i++) { g_dth.a[i] = g_dth.b[i] = -1; g_dth.t0[i] = 0; }
    g_dth.fading = 0; g_dth.count = 0;
}
static void dth_cut(int fade_ms, const char *why) {
    g_dth.armed = 0;
    if (!dth_live()) { dth_reset(); return; }          // already silent (fade done / wave over)
    if (g_dth.fading && fade_ms > 0) return;           // edge-triggered: the fade-out runs once per death (callers re-ask every frame)
    g_dth.fading = fade_ms > 0;
    EnterCriticalSection(&g_mix_cs);
    for (int i = 0; i < DTH_MAX_INST; i++)
        for (int k = 0; k < 2; k++) {
            int v = k ? g_dth.b[i] : g_dth.a[i];
            if (v < 0 || !g_mixv[v].on || g_mixv[v].src != g_dth.src + (k ? DTH_N : 0)) continue;      // slot already reused by another sound
            if (fade_ms <= 0) g_mixv[v].on = 0;
            else if (!g_mixv[v].fadeN) { g_mixv[v].fadeLeft = g_mixv[v].fadeN = fade_ms * MIX_RATE / 1000; }
        }
    LeaveCriticalSection(&g_mix_cs);
    xlog("death drone: %s - fade-out %d ms (%llu ms into it)", why, fade_ms, (unsigned long long)(GetTickCount64() - g_dth.first_t0));
    if (fade_ms <= 0) dth_reset();
}
// death_ui.c, once per death (sting_ms / exec_cue: logged only - the sidechain duck follows whatever actually plays).
// Starts immediately; the first copy's 1 s fade-in sits under the sting's attack, ducked.
static void dth_arm(int sting_ms, int exec_cue) {
    if (dth_off()) return;
    if (dth_live()) dth_cut(0, "new death");
    dth_reset();
    static int prev = -1;      // the pool: random, never the same bed twice in a row
    int cue = DR_K > 1 ? (int)(t2r_rand() % (DR_K - (prev >= 0))) : 0;
    if (DR_K > 1 && prev >= 0 && cue >= prev) cue++;
    prev = cue;
    g_dth.cue = cue; g_dth.src = dr_blob + (size_t)2 * DTH_N * cue;
    g_dth.armed = 1; g_dth.arm_t0 = GetTickCount64(); g_dth.lvl = DTH_FLOOR; g_dth.fg = 1.0f; g_dth.tick_t = 0;
    xlog("death drone: armed - %s starts now %s (%d ms sting), ducked under whatever plays", DR_NAMES[cue], exec_cue ? "under the execution victim cue" : "under the death sting", sting_ms);
}
// the sidechain: the loudest other 2D mixer voice longer than 0.5 s (music cues / stings, not 3D sfx or short clicks): its wave's peak over the
// next 80 ms x its gain (x its fade-out)
static float dth_foreground(void) {
    float m = 0.0f;
    if (g_mix_state != 1) return 0.0f;
    EnterCriticalSection(&g_mix_cs);
    for (int v = 0; v < MIX_VOICES; v++) {
        if (!g_mixv[v].on || g_mixv[v].dyn || !g_mixv[v].src || g_mixv[v].step <= 0.0) continue;
        const int16_t *src = g_mixv[v].src;
        if (g_dth.src && (src == g_dth.src || src == g_dth.src + DTH_N)) continue;
        double rate = g_mixv[v].step * MIX_RATE;
        if (g_mixv[v].n < rate * 0.5) continue;
        float gn = g_mixv[v].gl > g_mixv[v].gr ? g_mixv[v].gl : g_mixv[v].gr;
        if (g_mixv[v].fadeN > 0) gn *= (float)g_mixv[v].fadeLeft / (float)g_mixv[v].fadeN;
        if (gn <= 0.0f) continue;
        int p0 = (int)g_mixv[v].pos, p1 = p0 + (int)(rate * 0.08);
        if (p0 < 0) p0 = 0;
        if (p1 > g_mixv[v].n) p1 = g_mixv[v].n;
        int pk = 0;
        for (int i = p0; i < p1; i += 4) { int x = src[i] < 0 ? -src[i] : src[i]; if (x > pk) pk = x; }
        float l = pk / 32768.0f * gn;
        if (l > m) m = l;
    }
    LeaveCriticalSection(&g_mix_cs);
    return m;
}
static int dth_spawn(uint64_t now) {
    int slot = -1;
    for (int i = 0; i < DTH_MAX_INST; i++) if (!dth_inst_live(i)) { slot = i; break; }
    if (slot < 0) return 0;
    float g = g_dth.lvl * exmus_user_volume();
    if (!pcm_play_voice(g_dth.src, 2, 0.0f, 0.0f, DR_RATE, 0, 0, NULL, 1.0f) || g_mix_state != 1) { xlog("death drone: mixer off"); return 0; }    // (starts the mixer if needed)
    EnterCriticalSection(&g_mix_cs);
    int a = -1, b = -1;
    for (int v = 0; v < MIX_VOICES && b < 0; v++) { if (g_mixv[v].on) continue; if (a < 0) a = v; else b = v; }
    if (b >= 0) {
        const int16_t *src[2] = {g_dth.src, g_dth.src + DTH_N};
        int vv[2] = {a, b};
        for (int k = 0; k < 2; k++) {
            int v = vv[k];
            g_mixv[v].src = src[k]; g_mixv[v].n = DTH_N; g_mixv[v].pos = 0.0; g_mixv[v].step = (double)DR_RATE / MIX_RATE; g_mixv[v].played = 0;
            g_mixv[v].fadeN = g_dth.fading ? 1 : 0; g_mixv[v].fadeLeft = 0;
            g_mixv[v].gl = g_mixv[v].tgl = k ? 0.0f : g; g_mixv[v].gr = g_mixv[v].tgr = k ? g : 0.0f;
            g_mixv[v].dyn = 0; g_mixv[v].ent = 0; g_mixv[v].base = 1.0f; memset(g_mixv[v].wp, 0, 12);
            g_mixv[v].on = 1;
        }
    }
    LeaveCriticalSection(&g_mix_cs);
    if (b < 0) { xlog("death drone: NOT played (voices busy)"); return 0; }
    g_dth.a[slot] = a; g_dth.b[slot] = b; g_dth.t0[slot] = now; g_dth.count++;
    if (g_dth.count == 1) g_dth.first_t0 = now;
    xlog("death drone: %s copy %d (%.0f s, gain %.3f, %llu ms after the death edge)", DR_NAMES[g_dth.cue], g_dth.count, (double)DTH_N / DR_RATE, (double)g,
         (unsigned long long)(now - g_dth.arm_t0));
    return 1;
}
// every frame (feature_death_ui): phase = g_du.phase (0 none, 1 dead, 2 respawned, 3 match end), final = the countdown's fade to black runs
static void dth_tick(int phase, int final) {
    if (!g_dth.armed && !dth_live()) { if (g_dth.count) dth_reset(); return; }
    uint64_t now = GetTickCount64();
    if (match_substate() != 6) { dth_cut(DTH_FADE_MS, "match left the playing state"); return; }
    if (phase == 0 || phase >= 2) { dth_cut(DTH_FADE_MS, phase == 2 ? "respawned" : phase == 3 ? "match ended" : "death screen off"); return; }
    if (final) {
        if (g_dth.armed && !g_dth.count) { g_dth.armed = 0; xlog("death drone: dropped (the respawn fade came first)"); return; }
        dth_cut(DTH_FADE_MS, "countdown fade to black"); return;
    }
    if (g_dth.fading) return;
    if (g_dth.armed) {
        if (!g_dth.count) { if (!dth_spawn(now)) { if (now - g_dth.arm_t0 > 3000) g_dth.armed = 0; return; } }
        else {
            int last = 0;
            for (int i = 0; i < DTH_MAX_INST; i++) if (g_dth.t0[i] > g_dth.t0[last]) last = i;
            if (now - g_dth.t0[last] >= (uint64_t)(DTH_N * 1000LL / DR_RATE - DR_XF_MS)) dth_spawn(now);      // overlap = the baked fades: a crossfade loop
        }
    }
    // level: the sidechain duck (set on the live voices; the mixer ramps within a buffer)
    float fg = dth_foreground(), dt = g_dth.tick_t ? (float)(now - g_dth.tick_t) / 1000.0f : 0.0f;
    g_dth.tick_t = now;
    float d = 1.0f - fg / DTH_DUCK_FULL; d = d < 0.0f ? 0.0f : d;
    float tgt = DTH_FLOOR + (DTH_BED - DTH_FLOOR) * d * d;
    float tc = tgt < g_dth.lvl ? DTH_DOWN_S : DTH_UP_S;
    g_dth.lvl += (tgt - g_dth.lvl) * (dt > 0.0f ? 1.0f - __builtin_expf(-dt / tc) : 0.0f);
    if ((fg > 0.02f) != (g_dth.fg > 0.02f))
        xlog("death drone: %s (foreground %.2f, level %.3f, %llu ms in)", fg > 0.02f ? "ducked under a cue" : "foreground clear - rising to the bed",
             (double)fg, (double)g_dth.lvl, (unsigned long long)(now - g_dth.arm_t0));
    g_dth.fg = fg;
    float g = g_dth.lvl * exmus_user_volume();
    EnterCriticalSection(&g_mix_cs);
    for (int i = 0; i < DTH_MAX_INST; i++)
        for (int k = 0; k < 2; k++) {
            int v = k ? g_dth.b[i] : g_dth.a[i];
            if (v < 0 || !g_mixv[v].on || g_mixv[v].src != g_dth.src + (k ? DTH_N : 0)) continue;
            g_mixv[v].tgl = k ? 0.0f : g; g_mixv[v].tgr = k ? g : 0.0f;
        }
    LeaveCriticalSection(&g_mix_cs);
}
