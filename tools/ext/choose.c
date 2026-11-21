// choose.c - the redesigned CHOOSE YOUR SIDE screen, included by t2r-ext.c after clanend.c; driven by side_tick (log: 'choose:').
// Offline key art (re/choose-1115/src, same method as the clan end screens): five RGBA parallax layers chL0 (near) .. chL4 (far) of one wide scene - the WLF
// checkpoint on the left, the ruined Seattle street at dusk, the Seraphite treeline on the right - moved by the key-art camera the way clanend.c ce_art does
// (layer depth CH_DEPTH, focal CE_FPX): a slow idle drift + sway, and a smoothed truck (0.8 s ease) toward the focused camp; the unfocused half dims.
// Widgets (tools/features/choose_widgets.py): anim-group.side.chArt / chUi / chHovW / chHovS. t2r-no-choose-art.txt = the old look (frames + figures).
#include "choose_data.h"
#include "vox_pick.h"                        // the faction voice takes (tools/features/vox_lines.py genpick)
#include "choose_vox.h"                      // ... as PCM clips per voice language (re/choose-1115/src/make_choose_vox_pcm.py)
__asm__(".section .rdata,\"dr\"\n.balign 4\n.globl cvx_blob\ncvx_blob:\n.incbin \"choose_vox.pcm\"\n.text\n");
extern const int16_t cvx_blob[];
#define CH_TRUCK_MS 800.0f

static const char *const CH_OLD[] = {"glowW", "glowS", "sideTitle", "sideTitleLine", "sideDivider", "frameBgW", "frameW", "figW", "frameBgS", "frameS", "figS",
                                    "sideName", "sideDesc", "sideWarn", "sideHint", "sideHintPad", "sideSelectIcon", "sideSelectText"};
static const char CH_WARN[] = "Your faction choice lasts until your clan dies or survives long enough to win.";
static struct { int on, focus, shown; float pos, from, twa; uint64_t t0, tmove, twt; } CH;      // twa: the TWELVE WEEKS title logo's show amount (0 .. 1)

static void ch_focus(int f);
static void ch_input(int left, int right, int hv, int allow_mouse);
static int ch_active(void) { return CH.on; }
static void ch_reset(void) { memset(&CH, 0, sizeof CH); }
static int ch_enabled(void) {                  // art on unless t2r-no-choose-art.txt sits beside the exe (re-read every 5 s)
    static int off = -1; static uint64_t chk;
    uint64_t n = GetTickCount64();
    if (off < 0 || n - chk > 5000) { chk = n; FILE *f = exe_side_open("t2r-no-choose-art.txt", "r"); off = f != NULL; if (f) fclose(f); }
    return !off;
}
static uint64_t ch_w(const char *name) { char p[96]; snprintf(p, sizeof p, "anim-group.side.%s", name); return ui_w(p); }
static void ch_a(const char *name, float a) { w_alpha(ch_w(name), a < 0.003f ? 0.003f : a > 1 ? 1 : a); }
static void ch_pad_hint(int *last) {
    if (*last == g_pad_mode) return;
    *last = g_pad_mode;
    ui_visible("anim-group.side.chHint", !g_pad_mode); ui_visible("anim-group.side.chHintPad", g_pad_mode);
}

// ---- the faction voice: focusing a camp plays ONE real TLOU2 enemy take of that faction (log 'choose vox:'), no subtitle, in the ACTIVE voice language.
// Takes = VXP_TAKE (vox_pick.h; REQUIRED: the Seraphite "No matter what... you're going to hell." and the WLF "Doesn't matter how far you run... we'll find you...",
// played first for a camp), records = one vox-info record per voice set (militia / scar x male / female x a..d) in the mod's vox module, played through the same
// `say` on the menu world's player as the old hover voice (side_vox). A record without a stream in the voice language is skipped (the engine would play English):
// a take with no usable record is not played, the next one is; a language the table does not know stays silent. Never the previous take again; a take that is
// still playing is not restarted and nothing stacks; a switch to the other camp cuts the old take (vox_stop) and plays that camp's. t2r-no-choose-vox.txt = off
// (the old hover voice comes back).
static uint64_t vox_stop(uint64_t ent);
static int ms_player_exists(void);
static struct { int pend, playing, last[2], seen[2]; uint64_t until, wait_at; uint8_t take_done[2][VXP_NTAKE], rec_done[VXP_NREC]; const int16_t *src; } CHV = {0, -1, {-1, -1}, {0, 0}, 0, 0};
// Voice lines did not play: `say` on the menu world's player is said on the OWN body, and the own body's dialogue is never heard on the own
// screen (deathreact.c: say answers 0, is-speaking? 1, nothing audible). The takes now play as clips of the same streams in the active voice language
// (choose_vox.pcm: every voice language the take tables know) through the ext mixer at the Dialogue volume, panned to the camp's side (WLF left, Seraphites
// right). t2r-choose-vox-say.txt = the old `say` route.
static int ch_vox_say(void) {
    static int on = -1; static uint64_t chk;
    uint64_t n = GetTickCount64();
    if (on < 0 || n - chk > 5000) { chk = n; FILE *f = exe_side_open("t2r-choose-vox-say.txt", "r"); on = f != NULL; if (f) fclose(f); }
    return on;
}
static float ch_dlg_gain(void) {                                     // Dialogue option over the Effects option (pcm_play_voice multiplies the Effects level in)
    float s = 1.0f, m = 0.0f, d = 1.0f;
    if (!sfx_option_raw(&s, &m, &d)) return 1.0f;
    s = s > 1.5f ? s / 100.0f : s; d = d > 1.5f ? d / 100.0f : d;
    s = s > 1.0f ? 1.0f : s; d = d > 1.0f ? 1.0f : d;
    float k = (d * d) / (s * s > 1e-3f ? s * s : 1e-3f);
    return k > 4.0f ? 4.0f : k;
}
static void ch_vox_cut(void) { if (CHV.src) { pcm_voice_ctl(CHV.src, -1.0f, 60); CHV.src = NULL; } vox_stop(SID_PLAYER); }
static int ch_vox_enabled(void) {
    static int off = -1; static uint64_t chk;
    uint64_t n = GetTickCount64();
    if (off < 0 || n - chk > 5000) { chk = n; FILE *f = exe_side_open("t2r-no-choose-vox.txt", "r"); off = f != NULL; if (f) fclose(f); }
    return !off;
}
static int ch_vox_on(void) { return CH.on && ch_vox_enabled(); }
static void ch_vox_req(int focus) {                                 // focus 0 = WLF, 1 = Seraphites (ch_focus)
    if (!ch_vox_on()) return;
    int fac = focus == 0 ? 1 : 0;                                   // vox_pick.h faction index: 0 Seraphite, 1 WLF
    uint64_t now = GetTickCount64();
    if (CHV.playing >= 0 && now < CHV.until) {
        if (CHV.playing == fac) return;                             // the take of this camp is still playing: no restart, no stack
        ch_vox_cut(); CHV.until = 0; CHV.playing = -1;
        xlog("choose vox: switched to %s - the old take is cut", fac ? "WLF" : "Seraphites");
    }
    CHV.pend = fac + 1; CHV.wait_at = 0;
}
static void ch_vox_tick(uint64_t now) {
    if (!CHV.pend) return;
    int fac = CHV.pend - 1;
    if (ch_vox_say() && !ms_player_exists()) {
        if (!CHV.wait_at) CHV.wait_at = now;
        if (now - CHV.wait_at > 8000) { CHV.pend = 0; xlog("choose vox: no player object in the menu world after 8 s - %s take dropped", fac ? "WLF" : "Seraphites"); }
        return;
    }
    CHV.pend = 0;
    vx_lang_tab(0);                                                 // latches the voice language (g_vx_lang_nm)
    int li = -1;
    if (g_vx_lang_nm) for (int k = 0; k < (int)(sizeof VXP_LANGS / sizeof *VXP_LANGS); k++) if (!_stricmp(g_vx_lang_nm, VXP_LANGS[k].name)) li = k;
    if (li < 0) { xlog("choose vox: voice language '%s' has no availability table - silent (never English in another language)", g_vx_lang_nm ? g_vx_lang_nm : "?"); return; }
    const uint8_t *av = VXP_LANGS[li].tab;
    int nrec = (int)(sizeof VXP_REC / sizeof *VXP_REC), nt = VXP_NTAKES[fac], avail[VXP_NTAKE], na = 0;
    for (int t = 0; t < nt; t++) {
        int have = 0;
        for (int i = 0; i < nrec && !have; i++) have = VXP_REC[i].fac == fac && VXP_REC[i].take == t && av[i];
        if (have) avail[na++] = t;
    }
    if (!na) { xlog("choose vox: %s - no take has a stream in %s, silent", fac ? "WLF" : "Seraphites", VXP_LANGS[li].name); return; }
    // a shuffle bag of LINES: no line repeats until every line of the camp (with a stream in this language) has played; inside a line a bag of VOICES: no voice repeats until
    // every kept voice of that line has played. The Seraphites open with their REQUIRED line on the first hover (the user deleted the WLF required line).
    int take = -1, left = 0;
    for (int k = 0; k < na; k++) if (!CHV.take_done[fac][avail[k]]) left++;
    if (!left) { for (int k = 0; k < na; k++) CHV.take_done[fac][avail[k]] = 0; left = na; }     // every line played: a new round (never the line that just played first, below)
    if (!CHV.seen[fac]) for (int k = 0; k < na; k++) if (VXP_TAKE[fac][avail[k]].req) take = avail[k];
    if (take < 0) {
        int pool[VXP_NTAKE], np = 0;
        for (int k = 0; k < na; k++) if (!CHV.take_done[fac][avail[k]] && !(left > 1 && avail[k] == CHV.last[fac])) pool[np++] = avail[k];
        take = pool[t2r_rand() % (uint32_t)np];
    }
    CHV.seen[fac] = 1; CHV.last[fac] = take; CHV.take_done[fac][take] = 1;
    int cand[8], nc = 0, nleft = 0;
    for (int i = 0; i < nrec && nc < 8; i++) if (VXP_REC[i].fac == fac && VXP_REC[i].take == take && av[i]) { cand[nc++] = i; if (!CHV.rec_done[i]) nleft++; }
    if (!nleft) { for (int k = 0; k < nc; k++) CHV.rec_done[cand[k]] = 0; nleft = nc; }          // every kept voice of the line played: a new round
    int pick = (int)(t2r_rand() % (uint32_t)nleft), i = cand[0];
    for (int k = 0; k < nc; k++) if (!CHV.rec_done[cand[k]] && pick-- == 0) { i = cand[k]; break; }
    CHV.rec_done[i] = 1;
    ch_vox_cut();
    if (!ch_vox_say()) {                                            // the clip route (default)
        int cl = li < CVX_NLANG && !_stricmp(CVX_LANG[li], VXP_LANGS[li].name) ? li : -1;
        int n = cl >= 0 ? CVX_CLIP[cl][i].n : 0;
        if (!n) { xlog("choose vox: %s take %d - no clip in %s, silent", fac ? "WLF" : "Seraphites", take + 1, VXP_LANGS[li].name); return; }
        const int16_t *src = cvx_blob + CVX_CLIP[cl][i].off;
        float g = 0.85f * ch_dlg_gain(), pan = fac ? -0.35f : 0.35f;   // (fac 1 = WLF: the left camp)
        int ok = pcm_play_lr(src, n, g * (pan > 0 ? 1.0f - pan : 1.0f), g * (pan < 0 ? 1.0f + pan : 1.0f), CVX_RATE);
        CHV.src = ok ? src : NULL;
        int ms = n * 1000 / CVX_RATE;
        CHV.playing = fac; CHV.until = now + ms + 150;
        xlog("choose vox: %s take %d of %d%s \"%s\" - %s %s voice %c, language %s, %d ms clip, gain %.2f pan %+.2f -> %s", fac ? "WLF" : "Seraphites", take + 1, nt,
             VXP_TAKE[fac][take].req ? " (REQUIRED)" : "", VXP_TAKE[fac][take].text, fac ? "mlt" : "scr", VXP_REC[i].g ? "female" : "male", 'a' + VXP_REC[i].v,
             VXP_LANGS[li].name, ms, (double)g, (double)pan, ok ? "playing" : "NOT played (mixer off)");
        return;
    }
    // the engine's own dialogue path in the ACTIVE voice language (`say` on the menu world's player body: a world-positioned voice, same treatment in every language).
    // (A baked-reverb PCM variant was tried and dropped: too much reverb, and it baked one language only. No engine native places dialogue at a
    // world point or sets a reverb / environment preset: say takes a speaker body, play-sound-at-position / -at-joint are for sfx events, set-per-frame-mixer-override
    // snapshots are gain tables only.)
    uint64_t a4[4] = {SID_PLAYER, VXP_REC[i].id, 2, 0};
    uint64_t r = dc_call(fnv64("say"), 4, a4);
    int ms = VXP_TAKE[fac][take].ms;
    CHV.playing = fac; CHV.until = now + ms + 250;
    xlog("choose vox: %s take %d of %d%s \"%s\" - %s %s voice %c, language %s, ~%d ms, say -> %llx", fac ? "WLF" : "Seraphites", take + 1, nt, VXP_TAKE[fac][take].req ? " (REQUIRED)" : "",
         VXP_TAKE[fac][take].text, fac ? "mlt" : "scr", VXP_REC[i].g ? "female" : "male", 'a' + VXP_REC[i].v, VXP_LANGS[li].name, ms, (unsigned long long)r);
}
// ---- the screen's states: NOTHING focused = all 8 figures framed like the key art's own composition, the title and the two logos with the two camp names as small
// tab labels under them, no description / warning. Focusing a camp (a click on its side, pad / keys left / right; hovering only highlights it) zooms the camera so THAT half fills the whole screen
// (CH_ZOOM x about a fixed point per side), its name animates from under its logo into the big title position + size (CH_NAME_MS) and then the description fades in
// (+ the red warning); switching camps pans the zoomed camera to the other half (CH_PAN_MS, no zoom-out between), the old name returns under its logo while the new one
// comes up, the description fades out (CH_FADE_OUT_MS) and in again once the name has arrived. Unfocusing (Esc / B / a right click: ch_back) reverses all of it.
#define CH_ZOOM 2.0f                          // the focused half is 1920 x 2160 of the 3840 x 2160 frame: x2 fills the screen's width
#define CH_ZOOM_MS 900.0f
#define CH_PAN_MS 800.0f
#define CH_NAME_MS 350.0f
#define CH_GRAIN_MS 125                       // film grain step (8 a second; was every other frame = 30 a second)
#define CH_FADE_OUT_MS 130.0f
#define CH_FADE_IN_MS 250.0f
#define CH_TAB_Y 1250.0f                      // the small name under its logo (centre y); scale CH_TAB_K of the big name
#define CH_TAB_K 0.40f
#define CH_BIG_X 1920.0f
#define CH_BIG_Y 1365.0f                      // the big name position (centre) = the description title
#define CH_LOGO_UP 1.35f                      // the focused camp's logo scales up, the other one down (same ease as the name move); both 1.0 with nothing focused
#define CH_LOGO_DOWN 0.72f
#define CH_DOLLY 3.0f                         // metres the camera dollies in while zoomed (parallax: nearer layers grow faster)
#define CH_TRUCK 2.5f                         // metres it trucks toward the focused side (parallax: nearer layers slide faster)
#define CH_FIG 1                              // the figures' layer (the framing is held on it)
#define CH_GY 560.0f                          // zoom invariant point y: the figures' centre lands at screen y 900, above the text block
#define CH_LOGO_Y 1095.0f                     // the logos' centre y (= choose_widgets LOGO_Y + LOGO_H / 2)
static const float CH_LOGO_CX[2] = {1320.0f, 2520.0f};   // = choose_widgets.py the two tabs' x
typedef struct { float from, to; uint64_t t0; float ms; } ch_tw_t;
static float ch_tw_val(const ch_tw_t *t, uint64_t now) { return t->from + (t->to - t->from) * ce_ease((float)(now - t->t0) / t->ms); }
static void ch_tw_to(ch_tw_t *t, float to, uint64_t now, float ms) { if (t->to == to) return; t->from = ch_tw_val(t, now); t->to = to; t->t0 = now; t->ms = ms; }
static struct { ch_tw_t zoom, pan, nw[2], lg[2], hl[2]; int desc_for, hov, sel_hov, dtgt; uint64_t fo_t, dead_at, dt_t; int swapped; } CHA;   // hl: the overview hover highlight per camp
static void ch_anim_reset(void) {
    uint64_t now = GetTickCount64();
    memset(&CHA, 0, sizeof CHA);
    CHA.zoom.ms = CHA.pan.ms = CHA.nw[0].ms = CHA.nw[1].ms = CHA.lg[0].ms = CHA.lg[1].ms = CHA.hl[0].ms = CHA.hl[1].ms = 1.0f;
    CHA.zoom.t0 = CHA.pan.t0 = CHA.nw[0].t0 = CHA.nw[1].t0 = CHA.lg[0].t0 = CHA.lg[1].t0 = CHA.hl[0].t0 = CHA.hl[1].t0 = now - 5000;
    CHA.hov = -1;
    CHA.lg[0].from = CHA.lg[0].to = CHA.lg[1].from = CHA.lg[1].to = 1.0f;
    CHA.pan.from = CHA.pan.to = -1.0f;
    CHA.desc_for = -1; CHA.dtgt = -1; CHA.dt_t = now;
}
// ---- the picker's music (B and C from the auditions, one after the other, with B fading in and out): the game's own streams 623
// tracking-horde ambient loop (B) and 662 minimal-tension 5 explore h (C) from common.psarc music1, embedded as 32 kHz PCM (make_choose_music.py) and played by the ext
// mixer: B, C, B, C ... while the picker is up. Every track fades in and out over CHM_FADE_MS (soft transitions, no cuts), the music fades out over CHM_LEAVE_MS when the
// picker closes or a side is confirmed, and it ducks CHM_DUCK (-6 dB) under a faction voice line. The lobby playlist is cut meanwhile (clanend.c ce_lobby_tick:
// ce_menu_music_hold + ce_music_live). t2r-no-choose-music.txt beside the exe = no picker music. (Engine playlists cannot be gain-faded or ducked, and cue C only plays inside
// the 10-cue explore playlist: hence the PCM.) Log: 'choose music:'.
#include "choose_music.h"
__asm__(".section .rdata,\"dr\"\n.balign 4\n.globl chm_blob\nchm_blob:\n.incbin \"choose_music.pcm\"\n.globl chm_blob_end\nchm_blob_end:\n.text\n");
extern const int16_t chm_blob[], chm_blob_end[];
#define CHM_FADE_MS 1500.0f
#define CHM_LEAVE_MS 800.0f
#define CHM_DUCK 0.5f
#define CHM_GAIN 0.55f                                              // (the end music's level, measured in the A/B capture)
// Faction-specific music that switches with the selected faction (only in the clan selection screen):
// three beds - the overview (B, C, B ...), WLF (W 655 watchtower unaware) and Seraphites (S 656 prophet mural), from the auditions in
// re/choose-vox-audition/faction-music (W2 / S1). The focused camp's bed plays (looped, each pass with its own in / out envelope); a focus change
// crossfades the beds over CHM_XF_MS.
#define CHM_NTRK 4
#define CHM_XF_MS 1200.0f
static const char *const CHM_NAME[CHM_NTRK] = {"B 623 tracking-horde ambient", "C 662 minimal-tension-5 explore", "W 655 watchtower unaware (WLF)", "S 656 prophet mural (Seraphites)"};
static struct { int on, leaving, dead, seq, want, began; uint64_t last, leave_t, duck_t, step_t; float duck; struct { uint64_t t0; int trk; float lv; } g[3]; } CHM;
static int ch_music_live(void) { return CHM.on; }
static int ch_music_enabled(void) {
    static int off = -1; static uint64_t chk;
    uint64_t n = GetTickCount64();
    if (off < 0 || n - chk > 5000) { chk = n; FILE *f = exe_side_open("t2r-no-choose-music.txt", "r"); off = f != NULL; if (f) fclose(f); }
    return !off;
}
static const int16_t *chm_ch(int trk, int right) { return chm_blob + CHM_TRACK[trk].off + (right ? CHM_TRACK[trk].n : 0); }
static void chm_gain(int trk, float g, int stop) {                  // set the two channel voices' gains (g already has the envelope); stop: cut them (their gain is 0)
    if (g_mix_state != 1) return;
    const int16_t *l = chm_ch(trk, 0), *r = chm_ch(trk, 1);
    float vol = sfx_user_volume();
    EnterCriticalSection(&g_mix_cs);
    for (int v = 0; v < MIX_VOICES; v++) {
        if (!g_mixv[v].on) continue;
        const int16_t *s = g_mixv[v].src;
        if (s != l && s != r) continue;
        if (stop) { if (!g_mixv[v].fadeN) g_mixv[v].fadeN = g_mixv[v].fadeLeft = 20 * 48; continue; }
        float gg = g * vol;
        if (s == l) { g_mixv[v].tgl = gg; g_mixv[v].tgr = 0; } else { g_mixv[v].tgl = 0; g_mixv[v].tgr = gg; }
    }
    LeaveCriticalSection(&g_mix_cs);
}
static int chm_voices_live(void) {
    if (g_mix_state != 1) return 0;
    int live = 0;
    EnterCriticalSection(&g_mix_cs);
    for (int v = 0; v < MIX_VOICES && !live; v++) {
        const int16_t *s = g_mixv[v].src;
        if (g_mixv[v].on && s >= chm_blob && s < chm_blob_end) live = 1;
    }
    LeaveCriticalSection(&g_mix_cs);
    return live;
}
static float chm_smooth(float x) { x = x < 0 ? 0 : x > 1 ? 1 : x; return x * x * (3.0f - 2.0f * x); }
static int chm_play(int gi, uint64_t now) {
    int trk = CHM.g[gi].trk;
    if (pcm_play_stereo(chm_ch(trk, 0), chm_ch(trk, 1), CHM_TRACK[trk].n, 0.0f, CHM_RATE)) {
        CHM.g[gi].t0 = now; CHM.began = 1;
        xlog("choose music: %s (%.1f s, fade %.1f s in / out)", CHM_NAME[trk], CHM_TRACK[trk].n / (float)CHM_RATE, CHM_FADE_MS / 1000.0f);
        return 1;
    }
    CHM.g[gi].t0 = 0; static int nf; if (nf++ < 5) xlog("choose music: no mixer voice free");
    return 0;
}
// the bed: 0 overview (B / C), 1 WLF, 2 Seraphites. The faction's bed already plays while its camp is only hovered in the overview
// (before pressing it); a hover change counts after CHM_HOVER_MS (a cursor sweeping across the page does
// not flip the beds), a focus at once.
#define CHM_HOVER_MS 300
static int ch_confirmed(void);
static int chm_want(void) {
    int w = CH.focus >= 0 ? CH.focus + 1 : !ch_confirmed() && CHA.hov >= 0 ? CHA.hov + 1 : 0;
    static int last = -1, cur; static uint64_t at;
    uint64_t now = GetTickCount64();
    if (w != last) { if (last < 0) cur = w; last = w; at = now; }
    if (CH.focus >= 0 || now - at >= CHM_HOVER_MS) cur = w;
    return cur;
}
static void ch_music_step(uint64_t now) {
    if (!CHM.on) return;
    if (!CHM.leaving && now - CHM.last > 300) { CHM.leaving = 1; CHM.leave_t = now; xlog("choose music: picker gone - fading out %.1f s", CHM_LEAVE_MS / 1000.0f); }
    float lv = 1.0f;
    if (CHM.leaving) {
        lv = 1.0f - (now - CHM.leave_t) / CHM_LEAVE_MS;
        if (lv <= 0.0f) {
            for (int k = 0; k < CHM_NTRK; k++) chm_gain(k, 0.0f, 1);
            for (int gi = 0; gi < 3; gi++) CHM.g[gi].t0 = 0;
            CHM.on = 0; CHM.leaving = 0; xlog("choose music: stopped");
            return;
        }
    } else ce_menu_music_hold(now);                                 // (the lobby playlist stays cut while we play)
    int want = CHM.leaving ? CHM.want : chm_want();
    if (want != CHM.want) { CHM.want = want; xlog("choose music: the %s bed (crossfade %.1f s)", want == 1 ? "WLF" : want == 2 ? "Seraphite" : "overview", CHM_XF_MS / 1000.0f); }
    float fdt = CHM.step_t && now > CHM.step_t ? (float)(now - CHM.step_t) : 16.0f; if (fdt > 100.0f) fdt = 100.0f;
    CHM.step_t = now;
    float wd = CHV.playing >= 0 && now < CHV.until ? CHM_DUCK : 1.0f;     // (a faction voice line: the music ducks, eased 0.25 s)
    float dt = fdt / 250.0f;
    CHM.duck += wd > CHM.duck ? (wd - CHM.duck > dt ? dt : wd - CHM.duck) : -(CHM.duck - wd > dt ? dt : CHM.duck - wd);
    for (int gi = 0; gi < 3; gi++) {
        float tgt = gi == want ? 1.0f : 0.0f, d = fdt / CHM_XF_MS, *l = &CHM.g[gi].lv;
        *l += tgt > *l ? (tgt - *l < d ? tgt - *l : d) : -(*l - tgt < d ? *l - tgt : d);
        int trk = CHM.g[gi].trk;
        float len = CHM_TRACK[trk].n * 1000.0f / CHM_RATE;
        if (CHM.g[gi].t0 && now - CHM.g[gi].t0 >= (uint64_t)len - 20) {    // a pass is over: the overview bed goes B -> C -> B ..., a camp's bed loops
            chm_gain(trk, 0.0f, 1); CHM.g[gi].t0 = 0;
            if (gi == 0) { CHM.seq++; CHM.g[0].trk = trk = CHM.seq & 1; len = CHM_TRACK[trk].n * 1000.0f / CHM_RATE; }
        }
        if (*l <= 0.0f && tgt == 0.0f) { if (CHM.g[gi].t0) { chm_gain(trk, 0.0f, 1); CHM.g[gi].t0 = 0; } continue; }
        if (!CHM.g[gi].t0) {
            if (CHM.leaving || (!CHM.began && chm_voices_live()) || !chm_play(gi, now)) continue;   // (a pass left over from the last picker: wait for it)
        }
        float tt = (float)(now - CHM.g[gi].t0);
        float env = chm_smooth(tt / CHM_FADE_MS) * chm_smooth((len - tt) / CHM_FADE_MS);
        chm_gain(trk, CHM_GAIN * env * chm_smooth(*l) * CHM.duck * chm_smooth(lv), 0);
    }
}
static void ch_music_hold(uint64_t now) {                           // each picker frame
    if (CHM.dead || !ch_music_enabled()) { ch_music_step(now); return; }
    CHM.last = now;
    if (!CHM.on) {
        CHM.on = 1; CHM.leaving = 0; CHM.seq = 0; CHM.duck = 1.0f; CHM.duck_t = CHM.step_t = 0; CHM.began = 0;
        CHM.g[0].trk = 0; CHM.g[1].trk = 2; CHM.g[2].trk = 3;
        CHM.want = chm_want();
        for (int gi = 0; gi < 3; gi++) { CHM.g[gi].t0 = 0; CHM.g[gi].lv = gi == CHM.want ? 1.0f : 0.0f; }
        ce_menu_music_hold(now);
        xlog("choose music: start");
    }
    ch_music_step(now);
}
static void ch_music_leave(void) {                                  // a side was confirmed: fade out now, no restart in the exit fade
    CHM.dead = 1;
    if (CHM.on && !CHM.leaving) { CHM.leaving = 1; CHM.leave_t = GetTickCount64(); xlog("choose music: side confirmed - fading out %.1f s", CHM_LEAVE_MS / 1000.0f); }
}
// ---- the intro cinematic: "after the twelve weeks screen disappears, its still black, and then text fades in sentence by sentence slowly ... while a drone
// plays, and then the whole text fades out, camera starts suddenly going downwards vertically, showing that the black background behind the text was actually a 3d
// object and the camera moves into the same placement of the clan choice overview, and then the ui ... fades in". The black = the tarp (re/choose-1115/src
// build_deck_choose.py: a dark WLF sniper screen 2.5 m in front of the key-art camera, its hem just above the overview's top edge; texture ce-choose-deck = chDeck).
// The camera starts CHI_Y0 m higher (the tarp fills the frame), the lines (choose_intro_text.h, from choose_widgets.INTRO_LINES) fade in one by one, the logo line
// word by word ("Gather." "Grow." "Survive" then the TWELVE WEEKS logo inline as a word: CHI_BEAT, CHI_LOGO_IN_MS), all fade out, then the camera drops (ease-out
// cubic: the fastest at the start) and every layer moves by its own depth (CE_FPX * Y / depth: the tarp fastest, the sky barely) and the UI fades in.
// Music: minimal-tension 5 explore D (CHI_LORE) from the black, under the lore; the unaware end tag 1 (CHI_TAG) on the logo beat (LORE crossfades out
// under it), carried through the text out and the drop, faded out slowly so it is gone just before the UI; the picker music starts with the UI.
// First-launch path (no side yet, incl. the server's re-choice rc=1): unskippable. From the end screens (START A NEW CLAN): a SKIP prompt bottom right (select:
// Enter / A / Cross, or a click) = a quick dip to black and back up at the overview with the UI fading in. t2r-no-choose-intro.txt = no intro. Log: 'choose intro:'.
#include "choose_deck.h"
#include "choose_intro_text.h"
#include "choose_intro.h"
__asm__(".section .rdata,\"dr\"\n.balign 4\n.globl chi_blob\nchi_blob:\n.incbin \"choose_intro.pcm\"\n.globl chi_blob_end\nchi_blob_end:\n.text\n");
extern const int16_t chi_blob[], chi_blob_end[];
#define CHI_PAUSE_MS 350                      // black after the text is gone, before the drop
#define CHI_DROP_MS 6000.0f                   // (was 2300 for a 1.79 m drop, too short a pan: 5.75 m now, eased in and out)
#define CHI_UI_LEAD_MS 450                    // the UI starts fading in this long before the camera settles
#define CHI_UI_IN_MS 1100.0f
#define CHI_T_DROP (CHI_TEXT_OUT_MS + CHI_OUT_MS + CHI_PAUSE_MS)
#define CHI_T_UI (CHI_T_DROP + (int)CHI_DROP_MS - CHI_UI_LEAD_MS)
#define CHI_INPUT_MS 500                      // input is the picker's again this long after the UI started
#define CHI_SKIP_DOWN_MS 300.0f               // skip: to black ...
#define CHI_SKIP_UP_MS 550.0f                 // ... and back up at the overview
#define CHI_LORE_GAIN 0.55f                   // (= CHM_GAIN: all three are RMS 0.12 over what plays)
#define CHI_LORE_IN_MS 600.0f                 // (explore D starts near silence: only a de-click)
#define CHI_LORE_OUT_END 200                  // LORE: out from the first logo word ("Gather.") to this long after the bass hit, squared smooth curve (the music otherwise started again
                                              // on "survive twelve weeks": explore D swells +16 dB from 20 to 22 s, right under the words)
#define CHI_TAG_GAIN 1.0f                     // the payoff (the end tag was not audible when twelve weeks showed: at 0.60 the A capture had it only ~8 dB over the
                                              // lore bed's quiet part, under the menu level's ambience; now +4.4 dB, the ambience ducked; t2r-choose-tag-gain.txt = another gain)
#define CHI_TAG_LEAD_MS CHI_TAG_HIT_MS        // the TAG (the whole 480 unaware end tag A, fades in and plays earlier than SURVIVE TWELVE WEEKS shows, but
                                              // with the bass landing when that sentence starts showing) starts its hit's offset early: the bass lands on the logo beat
#define CHI_TAG_IN_MS ((float)CHI_TAG_HIT_MS) // ... fading in over that lead
#define CHI_TAG_OUT_MS 1800.0f                // the TAG fades out slowly ...
#define CHI_TAG_END_GAP 100                   // ... and is gone this long before the UI starts fading in
#define CHI_SKIP_AUDIO_MS 800.0f              // skip: both out with the dip
#define CHI_T_TAG (CHI_LOGO_IN_MS - CHI_TAG_LEAD_MS)
#define CHI_T_TAG_OUT (CHI_T_UI - CHI_TAG_END_GAP - (int)CHI_TAG_OUT_MS)
// The camera started too low for the pan down, so the tarp is higher: when the camera starts panning down it is well above the
// characters and then goes into the right position. The tarp hangs CH_DECK_LIFT units higher than the deck render placed it (its hem 5120 units over the
// overview frame), so the start is 5.75 m up; the frame clears the tarp at 4.0 m, the camera still well above the figures, and the layers carry CH_LAYER_EXT
// units of scene over the frame (choose_widgets.LAYER_EXT) for that part of the drop.
#define CH_DECK_LIFT 5063.0f                  // the hem leaves the frame top at 4.0 m up
#define CH_LAYER_EXT 1200.0f
#define CHI_PARALLAX_P 0.2f
#define CH_HEM (CH_DECK_HEM - CH_DECK_LIFT)
#define CHI_Y0 ((2160.0f - CH_HEM + 80.0f) * CH_DECK_DEPTH / CE_FPX)   // the start height (m): the tarp's hem 80 units under the frame
static struct { int on, skippable, skipping, jumped, tag, lore_on, tag_on, lines_off, logo_k, ui_on, art_on; uint64_t t0, skip_t, skip_a; float lore_g, tag_g; } CHI;
// the crossfade from the clan end page into the intro passed the engine's 32-image table (t2r-ext.c gui2_slot_full: drawn images evicted =
// flicker): the end page's images + the tarp + the 5 layers + the shade + chUi's logos (alpha 0.003) all asked in the same frames. Under the tarp the
// layers / shade / logos are not seen until the drop, so they come on CHI_ART_MS into the intro (the end page is gone by then), or at once on a skip.
#define CHI_ART_MS 2500
static void chi_art(int on) {
    char p[64];
    for (int i = 0; i < 5; i++) { snprintf(p, sizeof p, "anim-group.side.chArt.chLayers.chL%d", i); ui_visible(p, on); }
    ui_visible("anim-group.side.chArt.chShade", on); ui_visible("anim-group.side.chUi", on);
    CHI.art_on = on;
}
static int chi_enabled(void) {
    static int off = -1; static uint64_t chk;
    uint64_t n = GetTickCount64();
    if (off < 0 || n - chk > 5000) { chk = n; FILE *f = exe_side_open("t2r-no-choose-intro.txt", "r"); off = f != NULL; if (f) fclose(f); }
    return !off;
}
static const int16_t *chi_ch(int clip, int right) { return chi_blob + CHI_CLIP[clip].off + (right ? CHI_CLIP[clip].n : 0); }
static void chi_gain(int clip, float g, int stop) {                 // the clip's two channel voices (cf. chm_gain)
    if (g_mix_state != 1) return;
    const int16_t *l = chi_ch(clip, 0), *r = chi_ch(clip, 1);
    float vol = sfx_user_volume();
    EnterCriticalSection(&g_mix_cs);
    for (int v = 0; v < MIX_VOICES; v++) {
        if (!g_mixv[v].on) continue;
        const int16_t *s = g_mixv[v].src;
        if (s != l && s != r) continue;
        if (stop) { if (!g_mixv[v].fadeN) g_mixv[v].fadeN = g_mixv[v].fadeLeft = 20 * 48; continue; }
        if (s == l) { g_mixv[v].tgl = g * vol; g_mixv[v].tgr = 0; } else { g_mixv[v].tgl = 0; g_mixv[v].tgr = g * vol; }
    }
    LeaveCriticalSection(&g_mix_cs);
}
static float chi_tag_gain(void) {
    static float g = -1.0f; static uint64_t chk;
    uint64_t n = GetTickCount64();
    if (g < 0.0f || n - chk > 3000) { chk = n; g = CHI_TAG_GAIN; FILE *f = exe_side_open("t2r-choose-tag-gain.txt", "r"); if (f) { float v; if (fscanf(f, "%f", &v) == 1 && v > 0.0f && v <= 2.0f) g = v; fclose(f); } }
    return g;
}
static int chi_play(int clip, float g) { return pcm_play_stereo(chi_ch(clip, 0), chi_ch(clip, 1), CHI_CLIP[clip].n, g, CHI_CLIP[clip].rate); }
static int chi_busy(void) { return CHI.on; }
static int64_t chi_el(uint64_t now) { return (int64_t)(now - CHI.t0); }
static int chi_input_ok(uint64_t now) { return !CHI.on || chi_el(now) >= CHI_T_UI + CHI_INPUT_MS; }
static float chi_w(const char *s) {                                 // the game width of one displayed row (choose_intro_text.h CHI_W; else ~34.7 units a character at 56 pt)
    for (size_t i = 0; i < sizeof CHI_W / sizeof *CHI_W; i++) if (!strcmp(CHI_W[i].s, s)) return CHI_W[i].w;
    int n = 0;
    for (const unsigned char *p = (const unsigned char *)s; *p; p++) if ((*p & 0xC0) != 0x80) n++;
    return n * 34.7f;
}
static void chi_lines(void) {                                       // texts + slot places (the loc layer translates each row; the logo line is laid out for the active language)
    char p[96], c[128];
    CHI.logo_k = -1;
    for (int k = 0; k < CHI_MAX; k++) {
        snprintf(p, sizeof p, "anim-group.side.chIntro.chIntroL%d", k);
        ui_visible(p, k < CHI_N);
        w_alpha(ui_w(p), 0.003f);
        if (k >= CHI_N) continue;
        const chi_line_t *L = &CHI_LINE[k];
        w_pivot(ui_w(p), 1920.0f, L->cy);
        snprintf(c, sizeof c, "%s.tx", p); ui_visible(c, !L->logo); if (!L->logo) ui_text(c, L->text);
        for (int j = 0; j < CHI_BEAT_MAX; j++) { snprintf(c, sizeof c, "%s.b%d", p, j); ui_visible(c, L->logo && j < CHI_BEAT_N); }
        snprintf(c, sizeof c, "%s.lg", p); ui_visible(c, L->logo);
        snprintf(c, sizeof c, "%s.tl", p); ui_visible(c, L->logo && L->tail && L->tail[0]);
        if (!L->logo) continue;
        CHI.logo_k = k;                                             // the words, each where it sits in the full row (the same sum as choose_widgets.intro_layout)
        float wb[CHI_BEAT_MAX], sp = chi_w(" "), wl = 0.0f;
        for (int j = 0; j < CHI_BEAT_N; j++) { const char *bt = loc_tr(CHI_BEAT[j].s); wb[j] = chi_w(bt ? bt : CHI_BEAT[j].s); wl += wb[j] + (j ? sp : 0.0f); }
        const char *tl = L->tail && L->tail[0] ? loc_tr(L->tail) : "";
        float wt = tl && tl[0] ? chi_w(tl) : 0.0f;
        float total = wl + CHI_LOGO_GAP + CHI_LOGO_INK_W + (wt > 0.0f ? CHI_TAIL_GAP + wt : 0.0f);
        float x0 = 1920.0f - 0.5f * total, ink_l = x0 + wl + CHI_LOGO_GAP, mid = 0.5f * CHI_SLOT_H, bx = x0;
        for (int j = 0; j < CHI_BEAT_N; j++) {
            snprintf(c, sizeof c, "%s.b%d", p, j); ui_text(c, CHI_BEAT[j].s); w_pivot(ui_w(c), bx + 700.0f, mid); w_alpha(ui_w(c), 0.003f);
            bx += wb[j] + sp;
        }
        snprintf(c, sizeof c, "%s.lg", p); ce_img(c, "streaming/t2r/load/tw-title.png"); w_pivot(ui_w(c), ink_l + 0.5f * CHI_LOGO_INK_W - CHI_LOGO_DX, mid + CHI_LOGO_DY); w_alpha(ui_w(c), 0.003f);
        snprintf(c, sizeof c, "%s.tl", p); if (wt > 0.0f) { ui_text(c, L->tail); w_pivot(ui_w(c), ink_l + CHI_LOGO_INK_W + CHI_TAIL_GAP + 150.0f, mid); w_alpha(ui_w(c), 0.003f); }
        xlog("choose intro: logo line, %d words + logo + \"%s\" (words %.0f units, total %.0f, centred)", CHI_BEAT_N, tl ? tl : "", wl, total);
    }
}
// The black page behind the UI = the six 5120 px wide textures (layers + tarp) never draw - the game shows nothing for a texture over 4096 px (every
// other one is <= 4096 and shows; the _1080p variants of the same art showed on B). choose_ship.py now caps them at 4096. For a build made before that:
// t2r-choose-art-test.txt "1080" = load the layers + tarp by their _1080p variant name (2560 px), "ce" = the clan end screen's layers (a visibility test).
static const char *ch_art_test(void) {
    static char tm[16]; static uint64_t chk;
    uint64_t n = GetTickCount64();
    if (!chk || n - chk > 3000) { chk = n; tm[0] = 0; FILE *f = exe_side_open("t2r-choose-art-test.txt", "r"); if (f) { if (fscanf(f, "%15s", tm) != 1) tm[0] = 0; fclose(f); } }
    return tm;
}
// The first view of the intro lore is unskippable (this includes players that will see the intro again with the big update that already have
// had clan progress). The SKIP prompt (the end screens' START A NEW CLAN) shows only once this install has played the intro through to the UI once:
// t2r-intro-seen.txt next to the exe, written when the UI comes in after an unskipped run. (The first-launch path - no side, the re-choice - stays
// unskippable either way.)
#define CHI_SEEN_FILE "t2r-intro-seen.txt"
static int chi_seen(void) { FILE *f = exe_side_open(CHI_SEEN_FILE, "r"); if (f) fclose(f); return f != NULL; }
static void chi_start(int skippable) {                              // after ch_show: the page is black (the tarp), the UI hidden
    memset(&CHI, 0, sizeof CHI);
    if (skippable && !chi_seen()) { skippable = 0; xlog("choose intro: SKIP held back - the intro has not been watched through on this install (%s)", CHI_SEEN_FILE); }
    if (!CH.on || !chi_enabled()) { xlog("choose intro: off (%s)", CH.on ? "t2r-no-choose-intro.txt" : "old look"); return; }
    CHI.on = 1; CHI.skippable = skippable; CHI.t0 = GetTickCount64();
    ce_img("anim-group.side.chArt.chLayers.chDeck", !strcmp(ch_art_test(), "1080") ? "streaming/t2r/choose/ce-choose-deck_1080p.png" : "streaming/t2r/choose/ce-choose-deck.png");
    ui_visible("anim-group.side.chArt.chLayers.chDeck", 1);
    ui_visible("anim-group.side.chIntro", 1);
    w_alpha(ch_w("chUi"), 0.003f);
    w_alpha(ch_w("chIntro.chIntroSkip"), 0.003f);
    ui_visible("anim-group.side.chIntro.chIntroSkip", skippable);
    ui_text("anim-group.side.chIntro.chIntroSkip.chSkipText", "SKIP");
    ui_visible("anim-group.side.chIntroFade", 0);
    chi_art(0);
    chi_lines();
    CHI.lore_on = chi_play(CHI_LORE, 0.0f);
    xlog("choose intro: start (%s, %d lines, logo at %.2f s, drop at %.2f s, UI at %.2f s, camera %.2f m up, lore %s, tag at %.2f s out %.2f..%.2f s, audio picks %s)",
         skippable ? "SKIP shown" : "unskippable", CHI_N, CHI_LOGO_IN_MS / 1000.0f, CHI_T_DROP / 1000.0f, CHI_T_UI / 1000.0f, CHI_Y0,
         CHI.lore_on ? "on" : "no mixer voice", CHI_T_TAG / 1000.0f, CHI_T_TAG_OUT / 1000.0f, (CHI_T_TAG_OUT + CHI_TAG_OUT_MS) / 1000.0f, CHI_PICK);
}
static void chi_skip(void) {
    if (!CHI.on || !CHI.skippable || CHI.skipping || CHI.jumped) return;
    uint64_t now = GetTickCount64();
    if (chi_el(now) >= CHI_T_DROP) return;                          // (the drop has begun: it is nearly over anyway)
    CHI.skipping = 1; CHI.skip_t = CHI.skip_a = now;
    ui_visible("anim-group.side.chIntroFade", 1);
    w_alpha(ch_w("chIntroFade"), 0.003f);
    xlog("choose intro: SKIP at %.1f s", chi_el(now) / 1000.0f);
}
// the camera's height over the overview (m); the skip jumps to the overview
static float chi_cam_y(uint64_t now) {
    if (!CHI.on || CHI.jumped) return 0.0f;
    float el = (float)chi_el(now);
    if (el < CHI_T_DROP) return CHI_Y0;
    float u = (el - CHI_T_DROP) / CHI_DROP_MS;
    if (u >= 1.0f) return 0.0f;
    float v = __builtin_powf(u, 0.8f), e = v * v * v * (v * (v * 6.0f - 15.0f) + 10.0f);   // smootherstep of u^0.8: starts from rest, the fastest a bit before half-way,
    return CHI_Y0 * (1.0f - e);                                     // settles softly (the ease-out cubic jumped off the tarp at 3x the mean speed)
}
static void chi_audio(uint64_t now, int64_t el) {                   // LORE from the start; the TAG on the logo beat with LORE crossfading out; the TAG out before the UI
    if (CHI.skip_a) {                                               // skip: the gains held at the press fade with the dip
        float o = 1.0f - (now - CHI.skip_a) / CHI_SKIP_AUDIO_MS;
        if (o <= 0.0f) {
            if (CHI.lore_on) chi_gain(CHI_LORE, 0.0f, 1);
            if (CHI.tag_on) chi_gain(CHI_TAG, 0.0f, 1);
            if (CHI.lore_on || CHI.tag_on) xlog("choose intro: music out (skip)");
            CHI.lore_on = CHI.tag_on = 0;
            return;
        }
        if (CHI.lore_on) chi_gain(CHI_LORE, CHI.lore_g * chm_smooth(o), 0);
        if (CHI.tag_on) chi_gain(CHI_TAG, CHI.tag_g * chm_smooth(o), 0);
        return;
    }
    if (CHI.lore_on) {
        float g = CHI_LORE_GAIN * chm_smooth(el / CHI_LORE_IN_MS);
        const int64_t o0 = CHI_BEAT[0].t_in, o1 = CHI_LOGO_IN_MS + CHI_LORE_OUT_END;
        if (el >= o0) {
            float o = 1.0f - (float)(el - o0) / (float)(o1 - o0), q = chm_smooth(o);
            if (o <= 0.0f) { chi_gain(CHI_LORE, 0.0f, 1); CHI.lore_on = 0; xlog("choose intro: lore out (%.2f s)", el / 1000.0f); }
            g *= q * q;
        }
        if (CHI.lore_on) { chi_gain(CHI_LORE, g, 0); CHI.lore_g = g; }
    }
    if (!CHI.tag && el >= CHI_T_TAG && el < CHI_T_TAG_OUT) {
        CHI.tag = 1; CHI.tag_on = chi_play(CHI_TAG, 0.0f); CHI.tag_g = 0.0f;
        xlog("choose intro: logo beat - end tag %s (%.2f s)", CHI.tag_on ? "on" : "(no mixer voice)", el / 1000.0f);
    }
    if (CHI.tag_on) {
        float g = chi_tag_gain() * (CHI_TAG_IN_MS > 0.0f ? chm_smooth((el - CHI_T_TAG) / CHI_TAG_IN_MS) : 1.0f);
        if (el >= CHI_T_TAG_OUT) {
            float o = 1.0f - (el - CHI_T_TAG_OUT) / CHI_TAG_OUT_MS;
            if (o <= 0.0f) { chi_gain(CHI_TAG, 0.0f, 1); CHI.tag_on = 0; xlog("choose intro: end tag out (%.2f s)", el / 1000.0f); return; }
            g *= chm_smooth(o);
        }
        chi_gain(CHI_TAG, g, 0); CHI.tag_g = g;
    }
}
static void chi_tick(uint64_t now) {                                // ch_tick, before the camera: the lines, the skip, the UI fade, the sounds
    if (!CHI.on) return;
    int64_t el = chi_el(now);
    if (!CHI.art_on && (el >= CHI_ART_MS || CHI.skipping || CHI.jumped)) { chi_art(1); xlog("choose intro: key art layers + logos on (%lld ms in%s)", (long long)el, CHI.skipping ? ", skip" : ""); }
    if (CHI.skipping && !CHI.jumped) {
        float d = (now - CHI.skip_t) / CHI_SKIP_DOWN_MS;
        w_alpha(ch_w("chIntroFade"), d >= 1.0f ? 1.0f : d < 0.003f ? 0.003f : ce_ease(d));
        if (d >= 1.0f) {                                            // black: jump to the overview, the UI comes up with the black lifting
            CHI.jumped = 1; CHI.t0 = now - CHI_T_UI; el = CHI_T_UI;
            CHI.skip_t = now;
            ui_visible("anim-group.side.chIntro", 0);
            ui_visible("anim-group.side.chArt.chLayers.chDeck", 0);
        }
    } else if (CHI.jumped) {
        float d = (now - CHI.skip_t) / CHI_SKIP_UP_MS, a = 1.0f - ce_ease(d);
        w_alpha(ch_w("chIntroFade"), a < 0.003f ? 0.003f : a);
        if (d >= 1.0f) ui_visible("anim-group.side.chIntroFade", 0);
    }
    if (!CHI.jumped) {
        float out = el < CHI_TEXT_OUT_MS ? 1.0f : 1.0f - ce_ease((float)(el - CHI_TEXT_OUT_MS) / CHI_OUT_MS);
        char p[64];
        for (int k = 0; k < CHI_N && !CHI.lines_off; k++) {
            snprintf(p, sizeof p, "chIntro.chIntroL%d", k);
            if (k != CHI.logo_k) { ch_a(p, ce_ease((float)(el - CHI_LINE[k].t_in) / CHI_FADE_MS) * out); continue; }
            ch_a(p, el >= CHI_LINE[k].t_in ? out : 0.0f);               // the logo line: the slot = the text out; each word, then the logo + tail, its own fade
            char c[64];
            for (int j = 0; j < CHI_BEAT_N; j++) {                 // (a word on the logo's beat - "Survive", shown together with the logo - takes the logo's fade)
                float fd = CHI_BEAT[j].t_in >= CHI_LOGO_IN_MS ? (float)CHI_LOGO_FADE_MS : (float)CHI_BEAT_FADE_MS;
                snprintf(c, sizeof c, "%s.b%d", p, j); ch_a(c, ce_ease((float)(el - CHI_BEAT[j].t_in) / fd));
            }
            float la = ce_ease((float)(el - CHI_LOGO_IN_MS) / CHI_LOGO_FADE_MS);   // slow: creeps in with the end tag
            snprintf(c, sizeof c, "%s.lg", p); ch_a(c, la);
            snprintf(c, sizeof c, "%s.tl", p); ch_a(c, la);
        }
        if (el >= CHI_TEXT_OUT_MS + CHI_OUT_MS && !CHI.lines_off) {
            CHI.lines_off = 1;
            for (int k = 0; k < CHI_N; k++) { snprintf(p, sizeof p, "anim-group.side.chIntro.chIntroL%d", k); ui_visible(p, 0); }
        }
        float sk = !CHI.skippable || el >= CHI_T_DROP ? 0.0f : ce_ease((float)(el - 800) / 400.0f) * (1.0f - ce_ease((float)(el - (CHI_T_DROP - 300)) / 300.0f));
        ch_a("chIntro.chIntroSkip", sk);
    }
    if (el < CHI_T_UI) ce_menu_music_hold(now);                     // (the lobby playlist stays cut: the intro music plays)
    int ui_t = el >= CHI_T_UI;
    if (ui_t && !CHI.ui_on) {
        CHI.ui_on = 1; xlog("choose intro: UI in (%s)", CHI.jumped ? "after the skip" : "camera settling");
        if (!CHI.jumped && !chi_seen()) {                           // watched through: later runs may offer SKIP
            FILE *f = exe_side_open(CHI_SEEN_FILE, "w");
            if (f) { fputs("1", f); fclose(f); }
            xlog("choose intro: watched through - %s %s", CHI_SEEN_FILE, f ? "written (SKIP from now on)" : "NOT written");
        }
    }
    float ua = ui_t ? ce_ease((float)(el - CHI_T_UI) / CHI_UI_IN_MS) : 0.0f;
    w_alpha(ch_w("chUi"), ua < 0.003f ? 0.003f : ua);
    chi_audio(now, el);
    if (el >= CHI_T_UI + (int64_t)CHI_UI_IN_MS + 100 && chi_cam_y(now) <= 0.0f && !CHI.lore_on && !CHI.tag_on && (!CHI.jumped || now - CHI.skip_t >= CHI_SKIP_UP_MS)) {
        CHI.on = 0;
        ui_visible("anim-group.side.chIntro", 0); ui_visible("anim-group.side.chArt.chLayers.chDeck", 0); ui_visible("anim-group.side.chIntroFade", 0);
        w_alpha(ch_w("chUi"), 1.0f);
        xlog("choose intro: done");
    }
}
// ---- the select payoff: "when you select the faction fully, it should play the no return encounter selection stinger/sfx, and maybe like etch out the
// other faction choice in a red chalk" + "a small animation for the logo, maybe like a lift and small slam? and upon selecting the description and clan text should fade
// out". On confirm: the description, the warning (chWarn), the chosen camp's name and the hints fade out (CHP_TEXT_MS); the chosen logo lifts (CHP_LIFT_MS, ease-out) and
// slams down (fast ease-in, a squash, settles); the NR encounter-select sound (CHI_SELECT: sfx-rl-hub-interact-map-select's wave in gbl-hud-rl, a bank the menu does not
// load: PCM) starts so its hit lands on the slam; the red chalk strike crosses out the OTHER camp's logo + name piece by piece from the slam (re/choose-1115/chalk.json).
// Then the page's own exit (side_tick stage 3). Log: 'choose pick:'.
#define CHP_TEXT_MS 250.0f
#define CHP_LIFT_MS 180.0f
#define CHP_SLAM_MS 70.0f
#define CHP_SETTLE_MS 110.0f
#define CHP_LIFT_K 0.12f                      // +12 % at the top of the lift
#define CHP_SQUASH_K 0.08f                    // -8 % at the slam
#define CHP_RISE 26.0f                        // units up at the top of the lift (and 4 under rest at the slam)
#define CHP_SELECT_LEAD_MS 50                 // the select wave's hit is 50 ms in (measured)
#define CHP_SELECT_GAIN 0.8f
#define CHP_HOLD_MS 650                       // after the last chalk piece, before the page fades out
static struct { int on, side, snd; uint64_t t0; } CHP;
static int ch_confirmed(void) { return CHP.on; }                    // a side was confirmed: the payoff / exit runs - nothing may bring the texts back (side_rc_note: gate on this)
static int chp_done(void) { return !CHP.on || GetTickCount64() - CHP.t0 >= (uint64_t)(CHI_CHALK_END_MS + CHP_HOLD_MS); }
static void chp_start(int side) {
    memset(&CHP, 0, sizeof CHP);
    if (!CH.on) return;
    CHP.on = 1; CHP.side = side; CHP.t0 = GetTickCount64();
    int o = side ^ 1;
    char p[64], img[64];
    ui_visible("anim-group.side.chUi.chChalk", 1);
    w_pivot(ch_w("chUi.chChalk"), CH_LOGO_CX[o], CHI_CHALK_CY);
    for (int k = 0; k < CHI_CHALK_N; k++) {
        snprintf(p, sizeof p, "anim-group.side.chUi.chChalk.chg%d", k); w_alpha(ui_w(p), 0.003f);   // (8 group images: 24 pieces + the page passed the 32-image table, A/B)
        snprintf(img, sizeof img, "streaming/t2r/choose/ch-chalkg-%02d.png", k); ce_img(p, img);
    }
    xlog("choose pick: %s confirmed - logo lift + slam, NR select sound, red chalk over %s", side ? "SERAPHITES" : "WLF", o ? "SERAPHITES" : "WLF");
}
static float chp_text_a(uint64_t now) { return CHP.on ? 1.0f - ce_ease((now - CHP.t0) / CHP_TEXT_MS) : 1.0f; }
static void chp_tick(uint64_t now, float *logo_k, float *logo_rise) {   // the chosen logo's extra scale / rise; the chalk; the sound
    *logo_k = 1.0f; *logo_rise = 0.0f;
    if (!CHP.on) return;
    float el = (float)(now - CHP.t0);
    if (el < CHP_LIFT_MS) { float u = el / CHP_LIFT_MS, e = 1.0f - (1.0f - u) * (1.0f - u); *logo_k = 1.0f + CHP_LIFT_K * e; *logo_rise = CHP_RISE * e; }
    else if (el < CHP_LIFT_MS + CHP_SLAM_MS) { float u = (el - CHP_LIFT_MS) / CHP_SLAM_MS, e = u * u; *logo_k = 1.0f + CHP_LIFT_K - (CHP_LIFT_K + CHP_SQUASH_K) * e; *logo_rise = CHP_RISE * (1.0f - e) - 4.0f * e; }
    else if (el < CHP_LIFT_MS + CHP_SLAM_MS + CHP_SETTLE_MS) { float e = ce_ease((el - CHP_LIFT_MS - CHP_SLAM_MS) / CHP_SETTLE_MS); *logo_k = 1.0f - CHP_SQUASH_K * (1.0f - e); *logo_rise = -4.0f * (1.0f - e); }
    if (!CHP.snd && el >= CHP_LIFT_MS + CHP_SLAM_MS - CHP_SELECT_LEAD_MS) {
        CHP.snd = 1;
        int ok = chi_play(CHI_SELECT, CHP_SELECT_GAIN);
        xlog("choose pick: NR select sound %s (its hit on the slam)", ok ? "on" : "(no mixer voice)");
    }
    char p[48];
    for (int k = 0; k < CHI_CHALK_N; k++) {
        float a = (el - CHI_CHALK_T0[k]) / (CHI_CHALK_T1[k] - CHI_CHALK_T0[k]);   // a group fades in over its pieces' show times
        snprintf(p, sizeof p, "chUi.chChalk.chg%d", k);
        ch_a(p, a <= 0.0f ? 0.0f : a);
    }
}
// The side group is about to show (intro -> pick, or the crossfade from the end screens): switch the art on (or leave the old frames when opted out). Nothing is focused.
static void ch_show(int focus) {
    (void)focus;
    CH.on = ch_enabled();
    CHM.dead = 0;
    CH.shown = 1; CH.focus = -1; CH.pos = 0.0f; CH.from = 0.0f; CH.t0 = CH.tmove = GetTickCount64();
    ch_anim_reset();
    CHI.on = 0; CHP.on = 0;                                         // (chi_start runs the intro; a fresh page has no confirmed side)
    ui_visible("anim-group.side.chIntro", 0); ui_visible("anim-group.side.chIntroFade", 0);
    ui_visible("anim-group.side.chArt.chLayers.chDeck", 0); ui_visible("anim-group.side.chUi.chChalk", 0);
    ui_visible("anim-group.side.chArt", CH.on); ui_visible("anim-group.side.chUi", CH.on);
    chi_art(CH.on);                                                 // (chi_start hides the layers / logos again for its first CHI_ART_MS)
    for (size_t i = 0; i < sizeof CH_OLD / sizeof *CH_OLD; i++) {
        char p[96]; snprintf(p, sizeof p, "anim-group.side.%s", CH_OLD[i]);
        if (CH.on) ui_visible(p, 0);                                // (off: side_focus shows the old frames / figures as before)
        else if (strncmp(CH_OLD[i], "glow", 4) && strncmp(CH_OLD[i], "fig", 3) && strncmp(CH_OLD[i], "frame", 5) && strcmp(CH_OLD[i], "sideHintPad")) ui_visible(p, 1);
    }
    xlog("choose: %s (nothing focused)", CH.on ? "key art on" : "old look (t2r-no-choose-art.txt)");
    if (!CH.on) return;
    g_ce_nimg = 0;                                                  // (the end screens' image list is spent)
    char p[64], img[96];
    const char *tm = ch_art_test();
    for (int i = 0; i < 5; i++) {                                   // "1080" = our layers by their _1080p variant name (2560 x 1080), else the base names (5120 x 2160)
        snprintf(p, sizeof p, "anim-group.side.chArt.chLayers.chL%d", i);
        if (!strcmp(tm, "ce")) snprintf(img, sizeof img, "streaming/t2r/clanend/ce-lost-ser-L%d.png", i);
        else if (!strcmp(tm, "1080")) snprintf(img, sizeof img, "streaming/t2r/choose/ce-choose-L%d_1080p.png", i);
        else snprintf(img, sizeof img, "streaming/t2r/choose/ce-choose-L%d.png", i);
        ce_img(p, img);
    }
    if (tm[0]) xlog("choose: art test '%s' - layer 0 image %s", tm, img[0] ? "set" : "?");
    ce_img("anim-group.side.chArt.chShade", "streaming/t2r/choose/ch-shade.png");
    {   // (A: black page behind the logos, no key art): which art widgets the page data has
        static const char *const CW[] = {"chArt", "chArt.chLayers", "chArt.chLayers.chL0", "chArt.chLayers.chL1", "chArt.chLayers.chL2", "chArt.chLayers.chL3", "chArt.chLayers.chL4", "chArt.chShade", "chUi", "chUi.chLogoW"};
        char d[512]; int n = 0;
        for (size_t i = 0; i < sizeof CW / sizeof *CW && n < (int)sizeof d - 40; i++) n += snprintf(d + n, sizeof d - n, " %s=%llx", CW[i], (unsigned long long)ch_w(CW[i]));
        xlog("choose: art widgets%s", d);
    }
    ce_img("anim-group.side.chUi.chLogoW", "streaming/photo-mode/logos/wlf-wolf-logo.png");   // (the game's own faction logos)
    ce_img("anim-group.side.chUi.chLogoS", "streaming/photo-mode/logos/scar-logo.png");
    ui_text("anim-group.side.chUi.chWarn", CH_WARN);
    ce_img("anim-group.side.chUi.chTitleLogo", "streaming/t2r/load/tw-title.png");   // (the TWELVE WEEKS title in the empty band under the camp names)
    CH.twa = 1.0f; CH.twt = 0;
    ui_text("anim-group.side.chNameW", "<font color=\"#9CC4E8\">WLF</font>");
    ui_text("anim-group.side.chNameS", "<font color=\"#E8905A\">SERAPHITES</font>");
}
static void ch_focus(int f) {                                       // a camp is focused (f 0 WLF, 1 Seraphites) or -1: nothing
    if (!CH.on) return;
    uint64_t now = GetTickCount64();
    if (f == CH.focus) return;
    CH.focus = f; CHA.fo_t = now; CHA.swapped = 0;
    ch_tw_to(&CHA.zoom, f >= 0 ? 1.0f : 0.0f, now, CH_ZOOM_MS);
    if (f >= 0) ch_tw_to(&CHA.pan, f ? 1.0f : -1.0f, now, CH_PAN_MS);
    for (int k = 0; k < 2; k++) { ch_tw_to(&CHA.nw[k], k == f ? 1.0f : 0.0f, now, CH_NAME_MS); ch_tw_to(&CHA.lg[k], f < 0 ? 1.0f : k == f ? CH_LOGO_UP : CH_LOGO_DOWN, now, CH_NAME_MS); }
    if (f >= 0) ch_vox_req(f);                                      // the camp voice (a no-op with t2r-no-choose-vox.txt)
    xlog("choose: focus %s", f < 0 ? "none (all 8 framed)" : f ? "SERAPHITES" : "WLF");
}
// input (side_tick, art on; the clickability of that screen was still made for the old ui). Two states:
//  OVERVIEW (nothing focused): the mouse over a camp (its 39 % half chHovW / chHovS, or its logo / name) HIGHLIGHTS it - the logo lifts a little, the other half dims - with no
//    camera move; a click there, or left / right, FOCUSES it (the zoom). SELECT does nothing yet (it is shown dimmed).
//  FOCUSED (zoomed onto one camp): the halves no longer react (the old rule switched camps on the way to SELECT, which sits in the right half); a click on the OTHER camp's
//    logo / name, or left / right, switches; SELECT (the prompt, click / Space / Enter / A) picks the focused camp; Esc / B / a right click goes back to the overview.
// tab: the camp whose logo / name is under the cursor, zone: whose half (-1 none, -2 no live cursor). Returns 1 = pick the focused camp (a click on SELECT).
#define CH_HL_MS 180.0f
#define CH_HOVER_LOG 1
#define CH_HL_LOGO 0.12f                      // the hovered logo's lift (+12 %)
#define CH_HL_DIM 0.55f                       // the other half's dim at full highlight
static void ch_input(int left, int right, int hv, int allow_mouse) {   // keys / pad (hv, allow_mouse: the hover state, see ch_mouse)
    (void)hv; (void)allow_mouse;
    if (left || right) {
        if (CH.focus < 0) ch_focus(left ? 0 : 1);
        else ch_focus(CH.focus ^ 1);
    }
}
// The overview hover (hovering over the wlf/seraphites text itself shifted it): the hovered camp's name now moves up to the big title above the
// description, so the hover must not follow the name widgets - the SERAPHITES tab straddles the edge of chHovS, the name left the cursor, the hover dropped, the
// name came back. The overview hover = the camp's half (zone) or its fixed tab column (logo + small name, from the cursor itself); the moved big name only KEEPS
// the hover it already has.
#define CH_COL_HW 480.0f                      // the tab column's half width about CH_LOGO_CX
#define CH_COL_Y0 940.0f
#define CH_COL_Y1 1330.0f
static int ch_mouse(int tab, int zone, int on_sel, int click, float mx, float my) {
    uint64_t now = GetTickCount64();
    int hov;
    if (zone == -2) hov = -1;
    else if (CH.focus < 0) {
        int col = my >= CH_COL_Y0 && my <= CH_COL_Y1 ? (__builtin_fabsf(mx - CH_LOGO_CX[0]) < CH_COL_HW ? 0 : __builtin_fabsf(mx - CH_LOGO_CX[1]) < CH_COL_HW ? 1 : -1) : -1;
        hov = zone >= 0 ? zone : col >= 0 ? col : tab >= 0 && tab == CHA.hov ? tab : -1;
    } else hov = tab >= 0 && tab != CH.focus ? tab : -1;
    if (hov != CHA.hov) {
        CHA.hov = hov;
        for (int k = 0; k < 2; k++) ch_tw_to(&CHA.hl[k], k == hov ? 1.0f : 0.0f, now, CH_HL_MS);
        if (CH.focus < 0 && CH_HOVER_LOG) xlog("choose: hover %s (overview)", hov < 0 ? "none" : hov ? "SERAPHITES" : "WLF");
    }
    if (CH.focus < 0 && !CHP.on) for (int k = 0; k < 2; k++) ch_tw_to(&CHA.nw[k], k == hov ? 1.0f : 0.0f, now, CH_NAME_MS);   // the hovered name enlarges + moves above the description (no camera move)
    CHA.sel_hov = CH.focus >= 0 && on_sel;
    if (!click || zone == -2) return 0;
    if (CH.focus >= 0 && on_sel) { xlog("choose: SELECT clicked (%s)", CH.focus ? "SERAPHITES" : "WLF"); return 1; }
    if (CH.focus >= 0 && (zone == CH.focus || tab == CH.focus) && now - CHA.fo_t > CH_NAME_MS) {   // a click on the focused camp picks it
        xlog("choose: click on the focused %s - select", CH.focus ? "SERAPHITES" : "WLF"); return 1;
    }
    if (CH.focus < 0 && hov >= 0) { xlog("choose: click on %s (overview) - focus", hov ? "SERAPHITES" : "WLF"); ch_focus(hov); return 0; }
    if (CH.focus >= 0 && tab >= 0 && tab != CH.focus) { xlog("choose: click on the %s tab - switch", tab ? "SERAPHITES" : "WLF"); ch_focus(tab); return 0; }
    return 0;
}
static int ch_back(void) {                                          // Esc / B / right click: a focused camp goes back to the overview (1 = used; else the page's own back)
    if (!CH.on || CH.focus < 0 || CHP.on) return 0;
    xlog("choose: back to the overview");
    ch_focus(-1);
    return 1;
}
static int ch_hover_desc(void) {                                    // the overview hover shows the description (t2r-choose-hover-nodesc.txt = off)
    static int off = -1; static uint64_t chk;
    uint64_t n = GetTickCount64();
    if (off < 0 || n - chk > 5000) { chk = n; FILE *f = exe_side_open("t2r-choose-hover-nodesc.txt", "r"); off = f != NULL; if (f) fclose(f); }
    return !off;
}
static int ch_grain_ms(void) {                                      // film grain tile step (ms); t2r-choose-grain-ms.txt = another value (16 = the old every-other-frame)
    static int ms = -1; static uint64_t chk;
    uint64_t n = GetTickCount64();
    if (ms < 0 || n - chk > 3000) { chk = n; ms = CH_GRAIN_MS; FILE *f = exe_side_open("t2r-choose-grain-ms.txt", "r"); if (f) { int v; if (fscanf(f, "%d", &v) == 1 && v >= 16 && v <= 2000) ms = v; fclose(f); } }
    return ms;
}
static int ch_amb_duck(void) {                                      // the menu level's ambience ducked while the page is up (t2r-no-choose-amb-duck.txt = off)
    static int off = -1; static uint64_t chk;
    uint64_t n = GetTickCount64();
    if (off < 0 || n - chk > 5000) { chk = n; FILE *f = exe_side_open("t2r-no-choose-amb-duck.txt", "r"); off = f != NULL; if (f) fclose(f); }
    return !off;
}
// The menu level's ambience under the intro + the pick (the ambient sounds of the already loaded level were still audible instead of being
// muted for the duration of the clan intro + pick; the per-frame under-black duck alone left it audible on A). t2r-choose-amb.txt picks the way (letters):
// b = per-frame mix-main-menu-boot-sequence (the five ambience categories -inf), f = per-frame under-black duck (instead of b), a = per-frame
// mix-menu-attenuate-ambis (instead of b / f), s = set-mixer-override(under-black duck) while the page is up, released by ch_amb_release_tick once ch_tick
// stops (it ducks every vox category too: the camp voice lines were silent under it), e = the game's Effects option held at 0 (sfx_hold_tick:
// the Effects slider mutes the waterfall the snapshots left on). Default "be". t2r-no-choose-amb-duck.txt = none.
static uint64_t g_ch_amb_t; static int g_ch_amb_stay;
static void ch_amb_tick(uint64_t now) {
    static char md[8] = "be"; static uint64_t chk; static uint64_t lg;
    if (!chk || now - chk > 3000) { chk = now; strcpy(md, "be"); FILE *f = exe_side_open("t2r-choose-amb.txt", "r"); if (f) { if (fscanf(f, "%7s", md) != 1) strcpy(md, "be"); fclose(f); } }
    if (strchr(md, 'e')) sfx_hold_tick();                           // the game's Effects option at 0 (t2r-ext.c sfx_hold_*): the waterfall too; dialogue + our PCM stay
    if (!ch_amb_duck()) return;
    g_ch_amb_t = now;
    if (strchr(md, 'b')) {                                          // the main menu's own boot mute (ss-main-menu-splash-screen): all five ambience categories -inf,
        static int lb;                                              // attack 0, release 10 s - incl. ambience-waterfall, which the under-black mix leaves on (
        uint64_t a[1] = {fnv64("mix-main-menu-boot-sequence")};     // the menu scene ambience was still heard under 'fs')
        uint64_t r = dc_call(fnv64("set-per-frame-mixer-override"), 1, a);
        if (!lb) { lb = 1; xlog("choose: ambience - per-frame mix-main-menu-boot-sequence -> %llx", (unsigned long long)r); }
    } else if (strchr(md, 'a')) { uint64_t a[1] = {fnv64("mix-menu-attenuate-ambis")}; dc_call(fnv64("set-per-frame-mixer-override"), 1, a); }
    else if (strchr(md, 'f')) mix_under_black();
    if (strchr(md, 's') && !g_ch_amb_stay) {
        uint64_t m = fnv64("mix-rl-under-black-duck-all-except-music"), r = dc_call(fnv64("set-mixer-override"), 1, &m);
        g_ch_amb_stay = 1; xlog("choose: ambience - set-mixer-override(under-black duck) -> %llx (mode '%s')", (unsigned long long)r, md);
    }
    if (now - lg > 30000) { lg = now; xlog("choose: menu level ambience muted (mode '%s')", md); }
}
static void ch_amb_release_tick(void) {
    if (g_ch_amb_stay && GetTickCount64() - g_ch_amb_t > 400) { uint64_t z = 0; dc_call(fnv64("set-mixer-override"), 1, &z); g_ch_amb_stay = 0; xlog("choose: ambience - mixer override released"); }
}
#define CH_BRAND_OUT_MS 900.0f                // the corner TWELVE WEEKS (sideBrand) fades out as the camera starts down: the pick has its own title logo
static void ch_tick(int *hint_dev) {
    if (!CH.on || !CH.shown) return;
    uint64_t now = GetTickCount64();
    float t = (now - CH.t0) / 1000.0f;
    // the menu level behind the page (the faction scene picked before: its wind / birds / camp sounds) is not this screen's place: the game's own under-black mixer
    // state ducks everything but the music every frame the page is up (the picker / intro music is the ext's own mixer); it fades back when the page is gone
    ch_amb_tick(now);
    chi_tick(now);                                                  // the intro (a no-op once it is done)
    if (!CHI.on || CHI.ui_on) ch_music_hold(now);                   // the picker music comes in with the UI (the intro's end tag is out by then)
    float Yc = chi_cam_y(now);                                      // the intro camera's height over the overview (m)
    {   // (the top right twelve weeks logo disappears after the camera starts panning down, since there is an extra TWELVE WEEKS already)
        float ba = 0.0f;
        if (CHI.on && !CHI.jumped) { float el = (float)chi_el(now); ba = el < CHI_T_DROP ? 1.0f : 1.0f - (el - CHI_T_DROP) / CH_BRAND_OUT_MS; }
        ch_a("sideBrand", ba);
    }
    if (!strcmp(ch_art_test(), "st")) {   // texture size test (choose_ship.py SIZE_TEST, a build with T2R_TEX_SIZETEST=1): the far layer shows ce-sizetest-<k>, 2.5 s each
        static const char *const ST[] = {"2560x1080", "2560x1404", "2048x2048", "2560x1680", "3412x1872", "4096x2048", "4096x2248", "4096x2688", "4096x4096", "5120x1080"};
        static int last = -1; int k = (int)(now / 2500 % 10);
        if (k != last) {
            last = k; char img[64]; snprintf(img, sizeof img, "streaming/t2r/choose/ce-sizetest-%d.png", k);
            ce_img("anim-group.side.chArt.chLayers.chL4", img);
            for (int i = 0; i < 4; i++) { char q[48]; snprintf(q, sizeof q, "chArt.chLayers.chL%d", i); ch_a(q, 0.0f); }
            xlog("choose: size test %d = %s", k, ST[k]);
        }
    }
    float zt = ch_tw_val(&CHA.zoom, now), pan = ch_tw_val(&CHA.pan, now);
    // the camera (the clan end screens' ce_art model: X right, A toward the scene, Y up, metres; layer depth CH_DEPTH, focal CE_FPX): the idle drift never stops; while zoomed the
    // camera also DOLLIES in (CH_DOLLY) and TRUCKS toward the focused side (CH_TRUCK * pan), so every depth layer moves and grows at its OWN rate - the foreground fastest, the
    // sky slowest, the figures (layer CH_FIG) sliding against the background when it pans between the camps. The figure layer is held at the framing below (the screen zoom
    // Z about G puts the focused half over the screen), the other layers move relative to it: scale sigma_i / sigma_fig, offset (tau_i - tau_fig) / sigma_fig.
    float X = CH_TRUCK * pan * zt + 0.10f * sinf(t * 0.23f) + 0.04f * sinf(t * 0.61f);
    float A = CH_DOLLY * zt + 0.10f * sinf(t * 0.17f);
    float Y = 0.035f * sinf(t * 0.19f);
    float Z = 1.0f + zt * (CH_ZOOM - 1.0f);
    float Gx = 1920.0f + 1920.0f * pan, Gy = CH_GY;
    float sg[5], tx[5], ty[5];
    for (int i = 0; i < 5; i++) {
        float dd = CH_DEPTH[i] - A;
        if (dd < 0.6f) dd = 0.6f;
        sg[i] = CH_DEPTH[i] / dd; tx[i] = -CE_FPX * X / dd; ty[i] = CE_FPX * Y / dd;
    }
    for (int i = 0; i < 5; i++) {
        float S = Z * sg[i] / sg[CH_FIG];
        float px = 1920.0f + (tx[i] - tx[CH_FIG]) / sg[CH_FIG], py = 1080.0f + (ty[i] - ty[CH_FIG]) / sg[CH_FIG];
        px = Gx + Z * (px - Gx); py = Gy + Z * (py - Gy);
        float lo = 3840.0f - 2560.0f * S, hi = 2560.0f * S;          // keep the 3840 x 2160 frame covered by the 5120 x 2160 layer (pivot = its centre)
        if (lo > hi) lo = hi = 0.5f * (lo + hi);
        if (px < lo) px = lo;
        if (px > hi) px = hi;
        float vlo = 2160.0f - 1080.0f * S, vhi = 1080.0f * S;
        if (vlo > vhi) vlo = vhi = 0.5f * (vlo + vhi);
        if (py < vlo) py = vlo;
        if (py > vhi) py = vhi;
        if (Yc > 0.0f) {                                            // the intro drop: the camera Yc m higher moves the layer down by its depth (parallax); never so far that its
            // The bottom half of the scenery was cut and moved into place during the last moments of the pan: true parallax from 4 m up
            // moved the near street (3.8 m) 3x the figures' layer, out of the frame until the last metre. The drop now compresses the depth differences:
            // every layer moves the figures' layer shift x (D1 / D) ^ CHI_PARALLAX_P (0.2: the street 1.25x, the sky 0.6x), so the scene stays whole.
            float off = CE_FPX * Yc / CH_DEPTH[1] * __builtin_powf(CH_DEPTH[1] / CH_DEPTH[i], CHI_PARALLAX_P), hf = CH_HEM + CE_FPX * Yc / CH_DECK_DEPTH;   // (hf: the tarp's hem in the frame; the layer's art top
            float lim = (hf > 0.0f ? hf : 0.0f) + CH_LAYER_EXT * S;                                  // must stay over the frame's top or under the hem)
            if (off > lim) off = lim;
            py += off;
        }
        char p[48]; snprintf(p, sizeof p, "chArt.chLayers.chL%d", i);
        uint64_t w = ch_w(p);
        w_scale(w, S, S);
        w_pivot(w, px, py);
    }
    if (CHI.on && !CHI.jumped) {                                    // the tarp (nearest of all): the same camera model, its centre CH_DECK_DY over a layer's, + the drop
        float dd = CH_DECK_DEPTH - A;
        if (dd < 0.3f) dd = 0.3f;
        float sgd = CH_DECK_DEPTH / dd, S = Z * sgd / sg[CH_FIG];
        float px = 1920.0f + (-CE_FPX * X / dd - tx[CH_FIG]) / sg[CH_FIG], py = 1080.0f + (CE_FPX * Y / dd - ty[CH_FIG]) / sg[CH_FIG];
        px = Gx + Z * (px - Gx); py = Gy + Z * (py - Gy);
        uint64_t w = ch_w("chArt.chLayers.chDeck");
        w_scale(w, S, S);
        w_pivot(w, px, py + (CH_DECK_DY - CH_DECK_LIFT) * S + CE_FPX * Yc / CH_DECK_DEPTH);
    }
    static uint32_t gr = 91; static uint64_t gr_t;                  // film grain: the tile jumps every CH_GRAIN_MS (every other frame was too fast)
    if (now - gr_t >= (uint64_t)ch_grain_ms()) { gr_t = now; gr = gr * 1664525u + 1013904223u; w_pivot(ch_w("chArt.chGrain"), -512.0f + (float)(gr >> 8 & 511), -512.0f + (float)(gr >> 20 & 511)); }
    float pa = chp_text_a(now), lk, lrise;                         // the select payoff (a no-op until a side is confirmed)
    chp_tick(now, &lk, &lrise);
    // the camp names: small under their logo -> the big title (position + scale)
    for (int k = 0; k < 2; k++) {
        float p = ch_tw_val(&CHA.nw[k], now);
        float x = CH_LOGO_CX[k] + (CH_BIG_X - CH_LOGO_CX[k]) * p, y = CH_TAB_Y + (CH_BIG_Y - CH_TAB_Y) * p, sc = CH_TAB_K + (1.0f - CH_TAB_K) * p;
        uint64_t w = ch_w(k ? "chUi.chNameS" : "chUi.chNameW");
        w_pivot(w, x, y); w_scale(w, sc, sc);
        // a switch moves both names through the middle at once: each dips to invisible half-way (and is whole again at its destination), so they never touch
        float p0 = ch_tw_val(&CHA.nw[0], now), p1 = ch_tw_val(&CHA.nw[1], now);
        int both = p0 > 0.02f && p0 < 0.98f && p1 > 0.02f && p1 < 0.98f;
        float dip = both ? fabsf(2.0f * p - 1.0f) : 1.0f;
        ch_a(k ? "chUi.chNameS" : "chUi.chNameW", dip * (CHP.on && k == CHP.side ? pa : 1.0f));
    }
    // the description + the warning: out fast, swap the text, in once the name has arrived. The camp under the cursor in the overview shows its description
    // too (no zoom; its name moves up to the title like a focus, ch_mouse); t2r-choose-hover-nodesc.txt = only a focused camp shows it.
    float da = 0.0f;
    int tg = CH.focus >= 0 ? CH.focus : !CHP.on && ch_hover_desc() ? CHA.hov : -1;
    if (tg != CHA.dtgt) { CHA.dtgt = tg; CHA.dt_t = now; }
    float u = (float)(now - CHA.dt_t), wait = CH_NAME_MS;   // (the hovered name moves up too, so the overview text also waits for it)
    if (tg >= 0) {
        if (CHA.desc_for != tg) {
            if (CHA.desc_for >= 0 && u < CH_FADE_OUT_MS) da = 1.0f - u / CH_FADE_OUT_MS;
            else { ui_text("anim-group.side.chUi.chDesc", SIDE_DESC[tg + 1]); CHA.desc_for = tg; }
        }
        if (CHA.desc_for == tg) {
            static int was_tg = -2, was_focus = -2;                 // (a hovered camp's text already up stays up when that camp is clicked)
            if (was_tg == tg && was_focus < 0 && CH.focus == tg) CHA.dt_t = now - (uint64_t)(CH_NAME_MS + CH_FADE_IN_MS), u = CH_NAME_MS + CH_FADE_IN_MS;
            was_tg = tg; was_focus = CH.focus;
            da = u < wait ? 0.0f : ce_ease((u - wait) / CH_FADE_IN_MS);
        }
    } else if (CHA.desc_for >= 0) {
        da = u < CH_FADE_OUT_MS ? 1.0f - u / CH_FADE_OUT_MS : 0.0f;
        if (da <= 0.0f) CHA.desc_for = -1;
    }
    ch_a("chUi.chDesc", da * pa); ch_a("chUi.chWarn", da * pa);     // (pa: they fade out on the confirm and stay out)
    if (CHP.on) { ch_a("chUi.chHint", pa); ch_a("chUi.chHintPad", pa); ch_a("chUi.chSelIcon", pa); ch_a("chUi.chSelText", pa); }
    {   // the TWELVE WEEKS title logo fills the band under the camp names only while nothing else is shown there: out with the description's fade-out time as soon
        // as a camp is focused, back in (the description's ease + fade-in time) once the description is fully gone
        float dt = CH.twt ? (float)(now - CH.twt) : 0.0f; CH.twt = now;
        int free_ = CH.focus < 0 && CHA.desc_for < 0 && CHV.pend == 0;
        if (free_) { CH.twa += dt / CH_FADE_IN_MS; if (CH.twa > 1.0f) CH.twa = 1.0f; }
        else { CH.twa -= dt / CH_FADE_OUT_MS; if (CH.twa < 0.0f) CH.twa = 0.0f; }
        ch_a("chUi.chTitleLogo", CH.twa <= 0.0f ? 0.0f : ce_ease(CH.twa));
    }
    for (int k = 0; k < 2; k++) {                                   // the hover highlight: the OTHER half dims (overview only; ch_mouse)
        float h = ch_tw_val(&CHA.hl[k ^ 1], now) * (CH.focus < 0 && !CHP.on ? 1.0f : 0.0f);
        ch_a(k ? "chArt.chDimS" : "chArt.chDimW", h * CH_HL_DIM);
    }
    if (!CHP.on) {                                                  // SELECT: dim until a camp is focused (nothing to pick), bright under the cursor
        float sa = CH.focus < 0 ? 0.35f : CHA.sel_hov ? 1.0f : 0.85f;
        ch_a("chUi.chSelIcon", sa); ch_a("chUi.chSelText", sa);
        static int hint_for = -2;
        if (hint_for != (CH.focus >= 0)) { hint_for = CH.focus >= 0; ui_text("anim-group.side.chUi.chHint", hint_for ? "A / D  SWITCH     ESC  BACK" : "A / D  OR CLICK A SIDE"); }
    }
    for (int k = 0; k < 2; k++) {                                   // the logos: scale up / down about their centre (no separator line); the unfocused one a little dimmer
        float l = ch_tw_val(&CHA.lg[k], now) * (1.0f + CH_HL_LOGO * ch_tw_val(&CHA.hl[k], now));
        if (CHP.on && k == CHP.side) { l *= lk; w_pivot(ch_w(k ? "chUi.chLogoS" : "chUi.chLogoW"), CH_LOGO_CX[k], CH_LOGO_Y - lrise); }
        w_scale(ch_w(k ? "chUi.chLogoS" : "chUi.chLogoW"), l, l);
        ch_a(k ? "chUi.chLogoS" : "chUi.chLogoW", CH.focus >= 0 && CH.focus != k ? 0.6f + 0.35f * ch_tw_val(&CHA.hl[k], now) : 1.0f);   // (the other camp's tab brightens under the cursor: a click switches)
    }
    ch_pad_hint(hint_dev);
    ch_vox_tick(now);
    ce_img_tick(now);
}
