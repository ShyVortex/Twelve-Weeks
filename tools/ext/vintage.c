// ---- Vintage Rifle gunshot (re/weapons-1117.md 3.1; dc_data_patches.VINTAGE, tools/part1/p1_vintage_sound.py)
// The gunshot is the Part I hunting rifle's: the release build stages p1-vintage.pcm with
// the Part I pack (part1/pack, next to part1.dat), the launcher puts it at <exe dir>\t2r-maps\part1\. The bolt and reload foley is the
// Seraphite NPC bolt rifle's audio set (dc_data_patches.VINTAGE_AUDIO): it plays from the animation events through the engine, not here.
// The Vintage Rifle's art def names a shot event no bank has (dc_data_patches.VINTAGE_SFX: the engine's own shot is silent for it); on every
// Vintage shot this file plays:
//   - p1-vintage.pcm loaded: the Part I mix (shot-own 2D for our gun, shot-other positional on the shooter's puppet, 15 m full .. 150 m silent);
//   - no file (or t2r-no-vintage-p1.txt): the hunting rifle's own TLOU2 shot event through play-sound-at-joint (its bank is loaded: the
//     hunting rifle is a stock gun), so the gun is never silent.
// Gains: t2r-vintage-p1.txt "own other" (default 1.0 1.2, by ear - not measured yet).
#define VP_MAGIC "T2RVPCM1"
enum { VP_SHOT_OWN, VP_SHOT_OTHER, VP_N };
static int16_t *g_vp_pcm;                       // the samples of the file, NULL = not loaded
static uint32_t g_vp_rate, g_vp_off[VP_N], g_vp_len[VP_N];
static int g_vp_state;                          // 0 = not tried, 1 = loaded, -1 = absent / bad / switched off
static float g_vp_gain_own = 1.0f, g_vp_gain_other = 1.2f;
static void vp_load(void) {
    if (g_vp_state) return;
    g_vp_state = -1;
    FILE *f = exe_side_open("t2r-no-vintage-p1.txt", "r");
    if (f) { fclose(f); xlog("vintage: t2r-no-vintage-p1.txt - the hunting rifle's own shot"); return; }
    if ((f = exe_side_open("t2r-vintage-p1.txt", "r"))) { float a, b; if (fscanf(f, "%f %f", &a, &b) == 2 && a >= 0 && a <= 4 && b >= 0 && b <= 4) { g_vp_gain_own = a; g_vp_gain_other = b; } fclose(f); }
    char path[MAX_PATH];
    GetModuleFileNameA(NULL, path, MAX_PATH);
    char *sl = strrchr(path, 92);
    if (!sl || (size_t)(sl - path) + 40 >= sizeof path) return;
    strcpy(sl + 1, "t2r-maps\\part1\\p1-vintage.pcm");
    f = fopen(path, "rb");
    if (!f) { xlog("vintage: no %s (Part I pack not downloaded) - the hunting rifle's own shot", path); return; }
    fseek(f, 0, SEEK_END);
    long sz = ftell(f);
    fseek(f, 0, SEEK_SET);
    uint8_t *b = sz > 20 + 8 * VP_N && sz < (8 << 20) ? (uint8_t *)malloc((size_t)sz) : NULL;
    if (!b || fread(b, 1, (size_t)sz, f) != (size_t)sz) { fclose(f); free(b); xlog("vintage: %s unreadable (%ld bytes)", path, sz); return; }
    fclose(f);
    uint32_t ver = *(uint32_t *)(b + 8), rate = *(uint32_t *)(b + 12), n = *(uint32_t *)(b + 16);
    uint32_t data = 20 + 8 * n, total = data < (uint32_t)sz ? (uint32_t)((sz - data) / 2) : 0;
    int ok = !memcmp(b, VP_MAGIC, 8) && ver == 1 && rate >= 8000 && rate <= 96000 && n >= VP_N && n < 64 && data < (uint32_t)sz;
    for (int i = 0; ok && i < VP_N; i++) {
        g_vp_off[i] = *(uint32_t *)(b + 20 + 8 * i); g_vp_len[i] = *(uint32_t *)(b + 24 + 8 * i);
        ok = g_vp_len[i] > 0 && g_vp_off[i] <= total && g_vp_len[i] <= total - g_vp_off[i];
    }
    if (!ok) { free(b); xlog("vintage: %s is not a version 1 Vintage sound file - the hunting rifle's own shot", path); return; }
    g_vp_pcm = (int16_t *)(b + data); g_vp_rate = rate; g_vp_state = 1;
    xlog("vintage: Part I hunting rifle gunshot loaded from %s (%u waves, %u Hz, %.1f s; gains own %.2f other %.2f)", path, n, rate,
         (double)total / rate, g_vp_gain_own, g_vp_gain_other);
}
static int vp_play(int w, float gain, uint64_t ent, int positional) {
    if (g_vp_state != 1 || w < 0 || w >= VP_N) return 0;
    const int16_t *src = g_vp_pcm + g_vp_off[w];
    if (!positional) return pcm_play_lr(src, (int)g_vp_len[w], gain, gain, (int)g_vp_rate);
    g_mix_rnear = 15.0f; g_mix_rfar = 150.0f;                 // a rifle shot carries: full within 15 m, gone at 150 m
    int r = pcm_play_at(src, (int)g_vp_len[w], gain, (int)g_vp_rate, ent);
    g_mix_rnear = g_mix_rfar = 0.0f;
    return r;
}
// the hunting rifle's own TLOU2 shot event (fallback without the Part I file)
static int vp_stock_shot(uint64_t ent, int own) {
    uint64_t a[5] = {fnv64(own ? "sfx-rifle-remington-bolt-player" : "sfx-rifle-remington-bolt-npc"), ent, fnv64("root"), 0, 0};
    uint64_t r = dc_call(fnv64("play-sound-at-joint"), 5, a);
    return r != ~0ULL;
}
static void vintage_shot(uint64_t ent, int own, int slot) {
    static int nl;
    int ok;
    const char *how;
    if (g_vp_state == 1) { ok = vp_play(own ? VP_SHOT_OWN : VP_SHOT_OTHER, own ? g_vp_gain_own : g_vp_gain_other, ent, !own); how = "Part I"; }
    else { ok = vp_stock_shot(ent, own); how = "hunting rifle event"; }
    if (LOGCAP(nl, 40)) xlog("vintage: shot %s (slot %d) -> %s %s", own ? "ours" : "puppet", slot, how, ok ? "played" : "FAILED");
}
static void vintage_tick(void) {
    if (!T2R_VINTAGE_BUILT) return;
    if (match_substate() != 6) return;
    vp_load();
    static uint64_t vid;
    if (!vid) vid = fnv64(VINTAGE_ID);
    // our own shots: the clip drops while the Vintage Rifle is held
    static int last_clip = -1; static uint64_t last_w;
    uint64_t cw = current_weapon();
    if (cw == vid) {
        int c = ammo_clip();
        if (last_w == vid && last_clip >= 0 && c >= 0 && c < last_clip) vintage_shot(SID_PLAYER, 1, -1);
        last_clip = c;
    } else last_clip = -1;
    last_w = cw;
    // the other players' shots: a new press of their firing byte with the Vintage Rifle in hand
    typedef uint8_t *(*fn_peer)(uint32_t);
    static uint8_t was[T2R_MAX_PEERS];
    for (int s = 0; s < T2R_MAX_PEERS; s++) {
        uint8_t *pe = ((fn_peer)t2r_peer)((uint32_t)s);
        uint8_t firing = pe && pe[4] && !pe[5] && pe[0x89];
        if (firing && !was[s] && *(uint64_t *)(pe + 0x91) == vid && !g_puppet_dead_here[s]) {
            uint64_t h = *(uint64_t *)(pe + 0x60);
            if (h) vintage_shot(h, 0, s);
        }
        was[s] = firing;
    }
}
