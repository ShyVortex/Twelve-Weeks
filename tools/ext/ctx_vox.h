// Contextual takedowns: the clips' own voice events. Included by ctxdown.c.
// TLOU2's takedown clips carry `voice-effect` anim events (tools/ctxvox_gen.py -> ctx_vox_events.h): the attacker's efforts (fight-give-*) and the
// victim's pain / grab / fall / death vocals, each at its clip frame. They play through `say` on the half's body at that frame on the chain clock
// (the same clock as the native sound events), in the speaker's own voice (a female look: fem_effort_sid's take of the same kind). A pair that
// has such events no longer gets our generic grunt / pain / cry cues (cd_vox_has). t2r-cd-old-vox.txt next to the exe = the old generic cues.
#include "ctx_vox_events.h"
static const struct { const char *pair; int seg, role, ms; uint64_t sid; int kind; } CTX_VOX[] = { CTX_VOX_DATA {NULL, 0, 0, 0, 0, 0} };
static struct { uint32_t uid; size_t i, n; struct { uint16_t ms; uint8_t role, kind; uint64_t sid; } ev[24]; } g_cd_vox;
static int cd_vox_old(void) {
    static int old = -1; static uint64_t chk;
    if (old < 0 || GetTickCount64() - chk > 2000) { chk = GetTickCount64(); old = GetFileAttributesA("t2r-cd-old-vox.txt") != INVALID_FILE_ATTRIBUTES; }
    return old;
}
// 1 = this move's vox comes from the clips (the generic grunt / pain / cry cues stay off)
static int cd_vox_has(void) { return g_cd_vox.n > 0; }
static void cd_vox_arm(int pair, const float *st, int ns) {
    memset(&g_cd_vox, 0, sizeof g_cd_vox);
    g_cd_vox.uid = g_ps.uid;
    if (cd_vox_old()) return;
    for (size_t k = 0; CTX_VOX[k].pair && g_cd_vox.n < sizeof g_cd_vox.ev / sizeof g_cd_vox.ev[0]; k++) {
        if (strcmp(CTX_VOX[k].pair, CD_PAIRS[pair].name) || cd_tab_seg(pair, CTX_VOX[k].seg, CTX_VOX[k].role) >= ns) continue;
        int sg = cd_tab_seg(pair, CTX_VOX[k].seg, CTX_VOX[k].role);
        float lim = sg + 1 < ns ? cd_seg_len(pair, sg) * 1000.0f : CD_PAIRS[pair].end_s * 1000.0f + 300.0f;
        if ((float)CTX_VOX[k].ms > lim) continue;                          // past the cut / the hand-off: never plays in the chain
        float m = st[sg] * 1000.0f + (float)CTX_VOX[k].ms;
        size_t j = g_cd_vox.n++;
        g_cd_vox.ev[j].ms = (uint16_t)(m > 60000.0f ? 60000.0f : m); g_cd_vox.ev[j].role = (uint8_t)CTX_VOX[k].role;
        g_cd_vox.ev[j].kind = (uint8_t)CTX_VOX[k].kind; g_cd_vox.ev[j].sid = CTX_VOX[k].sid;
    }
    for (size_t a = 1; a < g_cd_vox.n; a++)
        for (size_t b = a; b > 0 && g_cd_vox.ev[b - 1].ms > g_cd_vox.ev[b].ms; b--) { __typeof__(g_cd_vox.ev[0]) x = g_cd_vox.ev[b]; g_cd_vox.ev[b] = g_cd_vox.ev[b - 1]; g_cd_vox.ev[b - 1] = x; }
    xlog("ctxdown: %s - %d voice event(s) of the clips armed%s", CD_PAIRS[pair].name, (int)g_cd_vox.n, g_cd_vox.n ? ", generic grunt / pain cues off" : "");
}
static void cd_vox_tick(double t_ms, int pair, uint64_t att, uint64_t vic) {
    static int nl;
    for (; g_cd_vox.i < g_cd_vox.n && (double)g_cd_vox.ev[g_cd_vox.i].ms <= t_ms; g_cd_vox.i++) {
        __typeof__(g_cd_vox.ev[0]) *e = &g_cd_vox.ev[g_cd_vox.i];
        if (t_ms - e->ms > 400.0) continue;                                // a late start: skip what has passed
        uint64_t ent = e->role ? vic : att;
        if (!ent) continue;
        int fk = e->kind == 2 && CD_PAIRS[pair].style == 3 ? VXE_DEATHKNIFE : e->kind;   // (VXE_GIVE 0 / VXE_PAIN 1 / VXE_DEATH 2 / VXE_DEATHKNIFE 3)
        uint64_t a[4] = {ent, e->sid, 2, 0};
        uint64_t fs = fem_effort_sid(ent, fk);                             // a female speaker: her own take of this kind
        if (fs) a[1] = fs;
        uint64_t r = dc_call(fnv64("say"), 4, a);
        if (!e->role) g_att_vox_ms = GetTickCount64();                     // (ex_grunt's one-voice-per-900-ms guard)
        if (r == ~0ULL) {                                                  // the speaker's bank has no such event: the generic cue of the kind
            if (e->kind == 0) gx_play(GXS_EFFORT, ent, 0); else gx_play(GXS_PAIN, ent, e->kind == 2);
        }
        if (nl++ < 80) xlog("ctxdown: clip voice %016llx kind %d on the %s (%u ms)%s -> %llx", (unsigned long long)e->sid, e->kind, e->role ? "victim" : "attacker",
                            e->ms, fs ? " [female take]" : "", (unsigned long long)r);
    }
}
