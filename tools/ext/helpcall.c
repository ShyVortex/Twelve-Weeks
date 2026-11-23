// Calling a downed teammate for a revive
// . Included by t2r-ext.c after downed_vox.c.
// MSG_HELPCALL 0x9D, one message, two kinds:
//   HC_PING [kind 1][u8 downed slot]: a standing player pressed the MARK button (the one that marks enemies: winmm's latch 0x18013A7D0) with the reticle on
//       a downed TEAMMATE (and no enemy under it). It says a "Man down!" line (VX_ALLYDOWN, the generic pool only) and tells the other standing teammates.
//       Receivers: a marker over the downed body for 6 s; the notice "<name> needs a revive" when they stand nearer to the downed one than the pinger,
//       "... - you're closest" when nobody else standing (pinger and downed excluded) is nearer than they are.
//   HC_HELP [kind 2][u8 sender slot]: a DOWNED player pressed the call button (jump: Space / pad A / the engine's jump command - the game disables jumping
//       while downed). It shouts its own "downed" call again (VX_DOWNED: the cursing / groaning / Seraphite reinforcement whistle pool of the knocked-down
//       call), heard in 3D by the winmm voice path like every team line, and tells the standing teammates (notice + marker). 9 s cooldown, the prompt
//       "[SPACE] CALL FOR HELP" (the cooldown seconds while it recharges) is drawn at the bottom while downed.
// Team only: the message goes to teammates, never to enemies (the shout itself is heard by anyone within 35 m, like the downed call). Not while dead,
// dying, executed, in a paired move. Opt out: t2r-no-downed-ping.txt (the ping), t2r-no-help-call.txt (the call button + prompt). Log lines 'helpcall: ...'.
#define MSG_HELPCALL 0x9D            // peer msg (ours): [u8 kind 1 ping / 2 help][u8 downed slot] (see above)
#define HC_PING 1
#define HC_HELP 2
#define HC_MARK_MS 6000              // the marker over a pinged / calling downed teammate
#define HC_HELP_CD_MS 9000           // the call button's cooldown
#define HC_PING_CD_MS 2500           // one ping per target in this time
#define HC_FIRST_MS 1200             // no call in the first moments of the down (a jump key still held from before the down)
#define HC_RANGE 150.0f              // ping range (metres to the downed body; no blocks, the enemy mark's off-map cap, was 45)
static int hc_ping_off(void) { static uint64_t at; static int off; return feel_flag("t2r-no-downed-ping.txt", &at, &off, 120); }
static int hc_help_off(void) { static uint64_t at; static int off; return feel_flag("t2r-no-help-call.txt", &at, &off, 120); }
static struct { uint64_t until, start; uint8_t by, help; } g_hc_mark[T2R_MAX_PEERS];     // the markers (by = who called it, help = the downed one called itself)
static uint64_t g_hc_help_ready;                                                       // tick ms when our call button is ready again
static uint64_t g_hc_ping_ready[T2R_MAX_PEERS];                                        // per target: next ping allowed
static int g_hc_prompt;                                                                // our own call prompt is up (we are downed and may call)
static int g_hc_rush = -1;                                                             // the downed teammate we marked ourselves: no sprint limit while running towards them

static const char *hc_name(uint32_t slot) {
    uint8_t *pe = sk_peer_ptr(slot);
    const char *n = pe ? (const char *)(pe + 6) : NULL;
    return n && n[0] && !IsBadReadPtr(n, 2) ? n : "Teammate";
}
// a standing (alive, up) teammate of ours in this slot, with a puppet
static int hc_standing(uint32_t slot) {
    uint8_t *pe = sk_peer_ptr(slot);
    return pe && pe[4] && !pe[5] && is_teammate(slot) && slot != sk_me() && !g_peer_downed[slot] && !g_puppet_dead_here[slot] && sk_peer_body(slot);
}
// a downed teammate: down, not (yet) dying / executed here
static int hc_downed_mate(uint32_t slot) {
    uint8_t *pe = sk_peer_ptr(slot);
    return pe && pe[4] && !pe[5] && is_teammate(slot) && slot != sk_me() && g_peer_downed[slot] == 1 && !g_puppet_dead_here[slot] && sk_peer_body(slot);
}
static float hc_dist(const float *a, const float *b) {
    float dx = a[0] - b[0], dy = a[1] - b[1], dz = a[2] - b[2];
    return __builtin_sqrtf(dx * dx + dy * dy + dz * dz);
}
static void hc_notice(const char *text) {
    if (!text) return;
    if (!ntf_push(NTF_REVIVE, text, 4.0f)) msg_tag(text, 4.0f, 0);
}
// to every standing teammate of ours (never an enemy)
static unsigned hc_send(uint8_t kind, uint8_t slot) {
    uint8_t b[2] = {kind, slot};
    unsigned sent = 0;
    for (uint32_t t = 0; t < T2R_MAX_PEERS && g_send_tramp; t++) {
        uint8_t *tp = sk_peer_ptr(t);
        if (t != sk_me() && tp && tp[4] && !tp[5] && is_teammate(t)) { g_send_tramp(MSG_HELPCALL, b, 2, t); sent++; }
    }
    return sent;
}
static void hc_mark_set(uint32_t downed, uint32_t by, int help) {
    if (downed >= T2R_MAX_PEERS) return;
    g_hc_mark[downed].start = GetTickCount64();
    g_hc_mark[downed].until = g_hc_mark[downed].start + HC_MARK_MS;
    g_hc_mark[downed].by = (uint8_t)by;
    g_hc_mark[downed].help = (uint8_t)help;
}
// skills.c sk_sprint_meter: marking a downed teammate and running towards them (only towards them) bypasses the stamina limit.
// vx / vz = our horizontal velocity; towards = within ~37 deg of the line to the body, until it is up / dead / reached.
static int hc_rush_towards(float vx, float vz) {
    if (g_hc_rush < 0) return 0;
    if (match_substate() != 6 || !hc_downed_mate((uint32_t)g_hc_rush)) { xlog("helpcall: rush over (%s no longer down)", hc_name((uint32_t)g_hc_rush)); g_hc_rush = -1; return 0; }
    float mb[16], db[16];
    const float *me = player_locator(mb), *dp = sk_peer_pos((uint32_t)g_hc_rush, db);
    if (!me || !dp) return 0;
    float dx = dp[0] - me[0], dz = dp[2] - me[2], d2 = dx * dx + dz * dz, v2 = vx * vx + vz * vz;
    if (d2 < 2.0f * 2.0f || v2 < 0.25f) return 0;
    float dot = vx * dx + vz * dz;
    return dot > 0.0f && dot * dot >= 0.64f * d2 * v2;                // cos >= 0.8
}
// are we the standing teammate nearest to the downed one (the pinger and the downed excluded)? 1 = yes, 0 = no, -1 = positions unknown
static int hc_closest(uint32_t downed, uint32_t pinger, int *nearer_than_pinger) {
    float mb[16], db[16], ob[16];
    const float *me = player_locator(mb), *dp = sk_peer_pos(downed, db);
    *nearer_than_pinger = 1;
    if (!me || !dp) return -1;
    float mine = hc_dist(me, dp);
    if (pinger < T2R_MAX_PEERS && pinger != downed) {
        const float *pp = sk_peer_pos(pinger, ob);
        if (pp && hc_dist(pp, dp) < mine) *nearer_than_pinger = 0;
    }
    for (uint32_t t = 0; t < T2R_MAX_PEERS; t++) {
        if (t == sk_me() || t == downed || t == pinger || !hc_standing(t)) continue;
        const float *tp = sk_peer_pos(t, ob);
        if (tp && hc_dist(tp, dp) < mine) return 0;
    }
    return 1;
}
static void hc_notify_mate(uint32_t downed, uint32_t by, int help) {
    char txt[96];
    int nearer, closest = hc_closest(downed, by, &nearer);
    if (!help && !nearer && closest != 1) return;                      // a ping: only the ones nearer than the pinger are asked to go
    // the card (NTF_REVIVE: the revive handshake badge) names the distance too
    float nb[16], nd[16];
    const float *np = player_locator(nb), *dp = sk_peer_pos(downed, nd);
    int dm = np && dp ? (int)(hc_dist(np, dp) + 0.5f) : -1;
    if (dm >= 0) {
        if (closest == 1) snprintf(txt, sizeof txt, help ? "%s is calling for help - %d m - you're closest" : "%s needs a revive - %d m - you're closest", hc_name(downed), dm);
        else snprintf(txt, sizeof txt, help ? "%s is calling for help - %d m" : "%s needs a revive - %d m", hc_name(downed), dm);
    } else if (closest == 1) snprintf(txt, sizeof txt, help ? "%s is calling for help - you're closest" : "%s needs a revive - you're closest", hc_name(downed));
    else snprintf(txt, sizeof txt, help ? "%s is calling for help" : "%s needs a revive", hc_name(downed));
    hc_notice(txt);
    xlog("helpcall: notice to us for slot %u (%s by slot %u, closest %d, nearer than the pinger %d): %s", downed, help ? "help call" : "ping", by, closest, nearer, txt);
}

// the stock downed-buddy icon over a called / pinged teammate (feature_downed: the "+" with the bleed-out ring) flashes while the mark is up:
// -1 = no mark on that slot, 0 / 1 = the phase (feature_downed swaps the ring's palette tint red / white every 250 ms)
static int hc_mark_pulse(uint32_t slot) {
    if (slot >= T2R_MAX_PEERS || !g_hc_mark[slot].until) return -1;
    uint64_t now = GetTickCount64();
    if (now >= g_hc_mark[slot].until) return -1;
    static uint64_t lg[T2R_MAX_PEERS];
    if (now - lg[slot] > 20000) { lg[slot] = now; xlog("helpcall: buddy icon of slot %u pulses (%s mark, %d ms left)", slot, g_hc_mark[slot].help ? "call" : "ping", (int)(g_hc_mark[slot].until - now)); }
    return (int)(((now - g_hc_mark[slot].start) / 250) & 1);
}

// ---- the ping: the mark button with the reticle on a downed teammate
static int hc_aimed_downed(void) {
    float pb[16];
    const float *pl = player_locator(pb);
    if (!pl) return -1;
    int best = -1; float best_d = 1e9f;
    for (uint32_t slot = 0; slot < T2R_MAX_PEERS; slot++) {
        if (!hc_downed_mate(slot)) continue;
        float b[16];
        const float *l = sk_peer_pos(slot, b);
        if (!l || hc_dist(l, pl) > HC_RANGE) continue;
        float c[4] = {l[0], l[1] + 0.3f, l[2], 1.0f}, u[4] = {l[0], l[1] + 1.3f, l[2], 1.0f};      // the lying body's middle, and a metre above it (the scale)
        float cx, cy, ux, uy;
        if (!tag_project(c, &cx, &cy, NULL) || !tag_project(u, &ux, &uy, NULL)) continue;
        float ppm = cy - uy; if (ppm < 0.0f) ppm = -ppm;
        float dx = cx - 640.0f, dy = cy - 360.0f, d = __builtin_sqrtf(dx * dx + dy * dy);
        if (d > 110.0f + ppm * 0.9f) continue;                  // the same generous cone as the enemy mark: 110 px + about a body length
        if (d < best_d) { best_d = d; best = (int)slot; }
    }
    return best;
}
static void hc_ping_tick(uint64_t enemy_cand) {
    static uint8_t prev;
    uint8_t latch = *(volatile uint8_t *)VMA(0x18013A7D0);
    int edge = latch && !prev;
    prev = latch;
    if (!edge || match_substate() != 6 || hc_ping_off() || !g_send_tramp) return;
    if (g_downed || g_down_dying || g_exec_until || g_getup_pre || g_special_exec_until > g_t60 || local_hp() <= 0.0f || !actor_can_act() || psync_own()) return;
    (void)enemy_cand;                                                          // no blocks - an enemy near the reticle no longer eats the ping (the press may mark both); walls never blocked it
    int slot = hc_aimed_downed();
    if (slot < 0) return;
    uint64_t now = GetTickCount64();
    if (now < g_hc_ping_ready[slot]) return;
    g_hc_ping_ready[slot] = now + HC_PING_CD_MS;
    unsigned sent = hc_send(HC_PING, (uint8_t)slot);
    hc_mark_set((uint32_t)slot, sk_me(), 0);
    if (g_hc_rush != slot) xlog("helpcall: rushing to %s - no sprint limit while running towards them", hc_name((uint32_t)slot));
    g_hc_rush = slot;
    g_vx_pingline = 1;
    vx_event_ex(VX_ALLYDOWN, "ping: downed teammate", 1);                    // "Man down!" / "Got a man down here!" / "Fallen!" / a Seraphite whistle; heard by the winmm voice path
    g_vx_pingline = 0;
    xlog("helpcall: we pinged downed slot %u (%s) - message to %u teammate(s)", (uint32_t)slot, hc_name((uint32_t)slot), sent);
}

// ---- the call button while downed
static int g_hc_prev_on;                                                               // the call keys were down at the last poll (while not downed: treated as down)
static int g_hc_src;                                                                   // what saw the press: 1 key, 2 XInput A, 3 raw joypad mask, 4 engine command
// Controller support: the XInput read only sees an XInput pad, and the engine disables its jump command while
// downed, so a native DualSense / Steam Input pad saw nothing. The engine's own Joypad object (padinject.c: the reader hook learns the input bit the
// jump command uses on the active scheme) is read RAW instead: its held mask (Joypad+0x138) is filled by every device and not touched by the command
// disable. The bit is learned while the jump command is read (we probe it every 2 s in a match, so it is known before the down).
static uint64_t hc_raw_jump(void) {
    if (!padinj_ready()) padinj_install();
    if (!padinj_ready()) return 0;
    struct padinj_w *w = padinj_watch("jump");
    if (!w) return 0;
    if (!w->mask || !w->jp) { padinj_probe_read("jump"); if (!w->mask || !w->jp) return 0; }
    static uint64_t lm; if (lm != w->mask) { lm = w->mask; xlog("helpcall: jump command input bit %016llx on joypad %p - raw held mask read (any pad / DualSense / Steam Input)", (unsigned long long)w->mask, w->jp); }
    const uint8_t *jp = (const uint8_t *)w->jp;
    if (IsBadReadPtr(jp + 0x138, 8)) return 0;
    return *(const volatile uint64_t *)(jp + 0x138) & w->mask;
}
static int hc_call_pressed(void) {
    int on = 0, src = 0;
    if (game_focused() && (GetAsyncKeyState(VK_SPACE) & 0x8000)) { on = 1; src = 1; }
    if (!on) { WORD pb = 0; BYTE l, r; SHORT x, y; if (pad_state(&pb, &l, &r, &x, &y) && (pb & 0x1000)) { on = 1; src = 2; } }      // pad A (Cross through Steam Input)
    if (!on && game_focused() && hc_raw_jump()) { on = 1; src = 3; }
    if (!on && game_focused() && pad_cmd_on("jump")) { on = 1; src = 4; }  // the engine's own command (while it is enabled)
    int edge = on && !g_hc_prev_on;
    g_hc_prev_on = on;
    if (edge) g_hc_src = src;
    return edge;
}
static int hc_can_call(void) {
    return match_substate() == 6 && g_downed && !g_down_dying && !psync_active() && !g_uc4_me.dying && !eb_covers() && !(g_gx.until && g_t60 < g_gx.until) &&
           !g_exec_until && !g_getup_pre && local_hp() > 0.0f;
}
static int g_hc_wp_shown;                                                              // the engine's own prompt (glyph + words) is up over our body
static uint64_t g_hc_say_due;                                                          // our call line waits for the groan to be cut (see hc_tick)
static void hc_tick(void) {
    static uint64_t down_since, last_poll, probe_at;
    uint64_t now = GetTickCount64();
    // the prompt is a per-frame request of the engine's own interactable (the Dodge / Counter prompts' route), so it is asked for every frame
    if (g_hc_prompt && !g_hc_say_due && now >= g_hc_help_ready && match_substate() == 6 && g_downed && hc_can_call()) {
        unsigned gf = g_wpq_glyph_fail;
        g_wpq_glyph = "gen:jump";                                                  // TLOU2's own glyph of the jump command (key icon / pad button icon, device aware), not the word SPACE
        int shown = world_prompt(SID_PLAYER, "Call for help", -1.0f);
        g_wpq_glyph = NULL;
        if (g_wpq_glyph_fail != gf) shown = 0;
        static int lg; if (shown != g_hc_wp_shown && LOGCAP(lg, 10)) xlog("helpcall: call prompt %s", shown ? "shown with the engine's glyph (gen:jump) + \"Call for help\" over our body" : "not available (request layout / world prompt off) - drawn text instead");
        g_hc_wp_shown = shown;
    } else g_hc_wp_shown = 0;
    if (g_hc_say_due && now >= g_hc_say_due) {                                     // the groan is cut: say the call
        g_hc_say_due = 0;
        if (hc_can_call()) {
            vx_event_ex(VX_DOWNED, "downed: call for help", 1);                    // our own downed pool again (curse / groan / whistle), heard in 3D by everybody near
            uint64_t sa[1] = {SID_PLAYER}, sp = dc_call(fnv64("is-speaking?"), 1, sa);
            xlog("helpcall: call line sent - is-speaking? on our body right after: %llx", (unsigned long long)sp);
        }
    }
    if (match_substate() == 6 && !g_downed && now >= probe_at) { probe_at = now + 2000; if (!hc_help_off()) hc_raw_jump(); }   // learn the jump bit while the command is still enabled
    if (now - last_poll < 33) return;                                        // ~30 Hz is plenty for a button edge
    last_poll = now;
    for (uint32_t s = 0; s < T2R_MAX_PEERS; s++)                             // markers end with the down (revived / dead / left)
        if (g_hc_mark[s].until && (now >= g_hc_mark[s].until || match_substate() != 6 || !hc_downed_mate(s))) g_hc_mark[s].until = 0;
    int can = !hc_help_off() && hc_can_call();
    if (!can) { down_since = 0; g_hc_prompt = 0; g_hc_prev_on = 1; g_hc_say_due = 0; return; }      // (a key still held from before the down is no press)
    if (!down_since) down_since = now;
    g_hc_prompt = 1;
    int press = hc_call_pressed();
    if (!press || now - down_since < HC_FIRST_MS || now < g_hc_help_ready) return;
    g_hc_help_ready = now + HC_HELP_CD_MS;
    unsigned sent = hc_send(HC_HELP, (uint8_t)sk_me());
    // (calling for help played no voice line; log frame 34077: 'vox: rule say kind 5 (downed: call for help)' was logged but nothing was
    // heard): the downed groan loop (downed_vox.c) says its take on the same body (SID_PLAYER, 3 s long, one 0.5 s before the call in that log) and the
    // engine keeps the line already playing on a character, so the later `say` was dropped. The groan is cut first (stop-vox) and the call follows
    // 140 ms later; the groan loop stays quiet for DV_FIRST_MS after (dv_cut resets it).
    uint64_t sa[1] = {SID_PLAYER}, sp = dc_call(fnv64("is-speaking?"), 1, sa);
    uint64_t st = vox_stop(SID_PLAYER);
    dv_cut(T2R_MAX_PEERS, "call for help");
    g_hc_say_due = now + 140;
    xlog("helpcall: we called for help while downed (seen by %s) - message to %u teammate(s), next call in %d s; our body was speaking: %llx, stop-vox -> %llx",
         g_hc_src == 1 ? "the key" : g_hc_src == 2 ? "XInput A" : g_hc_src == 3 ? "the raw joypad mask" : "the engine command", sent, HC_HELP_CD_MS / 1000, (unsigned long long)sp, (unsigned long long)st);
}

// ---- the other side of the message
static int hc_recv(uint32_t slot, const uint8_t *buf, uint64_t len) {
    static uint64_t last_ms[T2R_MAX_PEERS];
    if (slot >= T2R_MAX_PEERS || !buf || len < 2 || match_substate() != 6) return 0;
    if (slot == sk_me() || !is_teammate(slot)) { xlog("helpcall: message from slot %u refused (not a teammate)", slot); return 0; }
    uint8_t kind = buf[0], tgt = buf[1];
    if ((kind != HC_PING && kind != HC_HELP) || tgt >= T2R_MAX_PEERS) return 0;
    if (kind == HC_HELP) tgt = (uint8_t)slot;                                // a call is always from the downed one itself
    if (tgt == sk_me() || !is_teammate(tgt)) return 0;
    uint64_t now = GetTickCount64();
    if (now - last_ms[tgt] < 1500) return 0;                                 // spam / the repeat of a ping by two teammates
    if (!hc_downed_mate(tgt)) { static unsigned n; if (LOGCAP(n, 10)) xlog("helpcall: slot %u is not downed here - %s from slot %u ignored", (uint32_t)tgt, kind == HC_HELP ? "call" : "ping", slot); return 0; }
    last_ms[tgt] = now;
    hc_mark_set(tgt, slot, kind == HC_HELP);
    if (kind == HC_HELP) dv_cut((int)tgt, "its call for help");              // the puppet's groan must not hold the call's line back on this screen either
    if (!g_downed && local_hp() > 0.0f) hc_notify_mate(tgt, slot, kind == HC_HELP);       // (a downed or dead player is not asked to go)
    return 1;
}

// ---- drawing: the marker over the downed body, the call prompt at the bottom
static float hc_text_w(const char *s, float size) {
    uint64_t wh = ((fn_measure)VMA(0x1800051B0))(s, size);
    uint32_t lo = (uint32_t)wh; float w; memcpy(&w, &lo, 4);
    return w > 0.0f && w < 1280.0f ? w : 0.0f;
}
static void hc_text_c(float cx, float y, float size, uint32_t argb, const char *s) {       // centred at cx, top y (1280 x 720 text space)
    float w = hc_text_w(s, size);
    if (w <= 0.0f) return;
    ((fn_text_va)VMA(0x1800039D0))(fbits(cx - w * 0.5f), fbits(y), fbits(size), (uint64_t)argb, "%s", s);
}
static void hc_draw(void) {
    if (match_substate() != 6) return;
    uint64_t now = GetTickCount64();
    float pb[16];
    const float *pl = player_locator(pb);
    for (uint32_t s = 0; s < T2R_MAX_PEERS; s++) {
        if (!g_hc_mark[s].until || now >= g_hc_mark[s].until || !hc_downed_mate(s)) continue;
        float b[16];
        const float *l = sk_peer_pos(s, b);
        if (!l) continue;
        float p[4] = {l[0], l[1] + 1.75f, l[2], 1.0f}, x, y;                  // above the teammate's name tag (it sits ~0.75 + 0.44 m over a lying body)
        if (!tag_project(p, &x, &y, NULL) || x < 40.0f || x > 1240.0f || y < 30.0f || y > 690.0f) continue;
        float a = 1.0f, age = (float)(now - g_hc_mark[s].start) / 1000.0f, left = (float)(g_hc_mark[s].until - now);
        if (age < 0.15f) a = age / 0.15f;
        if (left < 500.0f) a = left / 500.0f;
        float pulse = 0.78f + 0.22f * __builtin_sinf(age * 7.0f);
        uint32_t al = (uint32_t)(255.0f * a * pulse);
        char txt[64];
        const char *what = loc_tr_draw(g_hc_mark[s].help ? "CALLING FOR HELP" : "REVIVE NEEDED");      // the words say what happened; the stock buddy icon below flashes with them
        if (pl) snprintf(txt, sizeof txt, "%s  %.0f m", what, hc_dist(l, pl));
        else snprintf(txt, sizeof txt, "%s", what);
        hc_text_c(x, y, 0.95f, (al << 24) | 0x0030c8ffu, txt);                 // amber (ABGR)
    }
    if (g_hc_prompt && !hc_help_off() && hc_can_call()) {
        WORD pb2 = 0; BYTE l, r; SHORT lx, ly;
        // the ready prompt is the engine's own interactable over our body (glyph of the jump command + "Call for help", hc_tick); text is drawn
        // only for the cooldown count and when that request is not available (then with the key names, as before)
        const char *key = pad_state(&pb2, &l, &r, &lx, &ly) ? "SPACE / A" : "SPACE";
        char txt[96];
        uint64_t ready = g_hc_help_ready;
        if (now < ready) snprintf(txt, sizeof txt, "%s (%d)", loc_tr_draw("CALL FOR HELP"), (int)((ready - now + 999) / 1000));
        else if (!g_hc_wp_shown) snprintf(txt, sizeof txt, "[%s] %s", key, loc_tr_draw("CALL FOR HELP"));
        else txt[0] = 0;
        if (txt[0]) hc_text_c(640.0f, 600.0f, 1.0f, now < ready ? 0xa0c0c0c0u : 0xf0ffffffu, txt);
    }
}
