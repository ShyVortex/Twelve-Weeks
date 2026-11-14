// melee_exchange.c - the melee EXCHANGE: a scripted-ish sequence between two standing enemies on a shared clock (spec re/melee-exchange-1027.md; goal: melee that feels fair, like a proper sequence with rewarding QTEs).
// Included after melee_hitreact.c in t2r-ext.c. Log prefix "mex:". Opt-out: t2r-no-melee-exchange.txt next to the exe (re-read every 2 s) = today's free swings.
// Extra opt-outs / tuning: t2r-mex-hold.txt (the attacker's contact is held for the defender's verdict; off by default), t2r-mex-tune.txt "<fist tc ms> <weapon tc ms> <max vis ms>" (default 440 520 60).
//
// Built ON the existing pieces, nothing re-invented: the swing is the engine's own (melee_pace.c's padinj press), the dodge window / prompt / press / i-frames are melee_dodge.c's
// (this file only gives it a swing start and a window end on the shared clock), the DODGED branch is dcounter.c (dc_arm -> counter press -> psync pair -> escape), the HIT branch is
// the normal hit message + melee_hitreact.c reaction.
//  ENGAGE  A presses melee on a standing enemy D (<= 2.0 m, +-60 deg): the press is hidden from the engine (padinj_block), MSG_MEX START {uid, blow, T0 = now + lat_buf} goes to D.
//          lat_buf = clamp(one-way + 40, 120, 260) ms. D answers ACK (ok / refused). At T0 A's machine injects the press (the real swing starts), D's window starts at the same absolute
//          moment (T0 - one-way after the arrival). Refused / old build (no answer by T0 + 250 ms) = the press is delivered at once as a free swing.
//  ATTACK  owner D. Window = T0 .. T0 + tc + vis (tc = authored contact, vis = visual lag of A's streamed pose). A press = DODGED (i-frames, melee_dodge.c); none = HIT. D sends
//          MSG_MEX RES {verdict, R - now}; R = window close + lat_buf. A's engine contact is HELD (no send, no sound, no marker) until the verdict is due; HIT: the contact replays
//          through the normal hooks at R, DODGED: the miss (mdg_attacker_missed). No answer by the deadline = HIT (the safe default, D's i-frames still drop it if it dodged).
//  COMBO   after a HIT, A has 600 ms to press melee again (prompt "Combo", gen:attack): blow 2, 3 (v1: blow 3 is a normal ATTACK beat, not the finisher pair). None = END.
//  COUNTER after DODGED, dcounter.c owns it (D: dc_arm, the counter press, pair, escape). The exchange ends when it is over / its window lapsed.
//  END     controls back, 1.2 s pair cooldown (a press at that partner is a free swing). Partner's blows outside the beats are dropped; a third party's hit (or a gun shot of the
//          partner that HITS: punching limits the attacker but does not take away the attacked player's gun) breaks it for both. The defender keeps aim / fire (melee_stagger.c's
//          280 ms lock after a landed blow only); the ATTACKER's own firing is locked while it attacks (ENGAGE .. COMBO).
// MSG_MEX 0x9C: [u8 op][u16 uid] then op 1 START [u8 target slot][u8 blow 1..3][u8 weapon class][u16 T0 in ms][u16 tc ms]; op 2 ACK [u8 ok][u8 reason]; op 3 RES [u8 verdict 1 hit / 2 dodged]
// [u8 blow][u16 R in ms from the send]; op 4 END [u8 reason]. Every handler is idempotent (RES / START are sent twice).
#define MSG_MEX 0x9C
#define MX_COOL_MS 1200
#define MX_COMBO_MS 600
#define MX_MAX_BLOW 3
#define MX_ACK_GRACE_MS 600         // (was 250 with T0 = press + lat_buf; T0 is the press now, so a 300 ms RTT peer must still answer in time)
#define MX_REACH 2.0f
#define MX_CONE_COS 0.5f
enum { MXB_NONE, MXB_ENG, MXB_ATK, MXB_COMBO, MXB_CTR };
static struct {
    int role, beat, slot, blow, wcls, acked, swing_seen, contact, miss_done, verdict, burnt, hit_got, ctr_armed, ctr_seen, releasing, lastp, nlog, off, nohold, cfg_logged, res_pending, start_pending;
    uint16_t uid; unsigned ctr;
    uint64_t t_begin, t0, win_hi, rdue, fired, swing_ms, verd_ms, verd_dl, hard_dl, combo_until, ctr_until, hit_got_ms, contact_ms, block_until, bypass_until, cfg_at, res_at, start_at;
    int tc_ms, vis_ms, lat, tune[3]; uint64_t move_at_fire; int atk_at_fire;
    struct { int on, slot; uint64_t w, r8; float dmg; uint8_t lethal; } hold;
    uint64_t pair_cool[T2R_MAX_PEERS], nopeer[T2R_MAX_PEERS], rec_until[T2R_MAX_PEERS], rec_press; int rec_slot;
} g_mex = {.tune = {440, 520, 60}};
#define MXLOG(...) do { if (LOGCAP(g_mex.nlog, 400)) xlog(__VA_ARGS__); } while (0)
// melee_seq.c (included after this file): a landed blow plays TLOU2's synced hit pair; t2r-no-melee-seq.txt = off
static int msq_on(void);
static int msq_left_ms(void);
static void msq_break(const char *why, int normal_end);
static void msq_ended(int slot, uint16_t uid, uint64_t now);
static int msq_cooling(uint32_t slot, uint64_t now);
static void msq_note_contact(float dmg);
static int msq_try_start(uint64_t now, int final_);
static int msq_combo_press(int pedge, uint64_t now);
static void msq_tick(void);
static void mex_def_verdict(uint64_t now, int v, const char *why);
static float mxs_factor(float *lo);
// melee_qte.c (included after melee_seq.c): the turn-based QTE; t2r-no-melee-qte.txt = off
static int mq_active(void);
static int mq_tx_flags(void);
static int mq_tx_a(void);
static int mq_cap(void);
static void mq_begin(int role, uint64_t now, int peer_flags);
static void mq_peer_ack(int cap);
static void mq_end(const char *why);
static void mq_tick(uint64_t now);
static void mq_pair_end(uint64_t now);
static void mq_after_hit(uint64_t now);
static void mq_note_press(uint64_t now);
static int mq_atk_beat(uint64_t now, int slot, int *press);
static int mq_def_beat(uint64_t now, int slot);
static int mq_strike_eval(uint64_t now, int slot, int a_ms, int forced);
static void mq_yield(uint64_t now, int forced);
static int mq_start_ok(int slot, uint16_t uid, int blow, int flags);
static int mq_ignore_start(int slot, uint16_t uid, int flags, uint64_t now);
static void mq_beat_contact(uint64_t now);
static void mq_flip(uint64_t now, const char *why);
static int mq_lapse(uint64_t now, const char *why);
static int mex_press_edge(uint64_t now);
// an opt-out file next to the exe, re-read every 2 s (one cache slot per file)
static int mex_optout(const char *name, int *v, uint64_t *at) {
    uint64_t n = GetTickCount64();
    if (*v < 0 || n - *at > 2000) { *at = n ? n : 1; FILE *f = exe_side_open(name, "r"); *v = f != NULL; if (f) fclose(f); }
    return *v;
}
static uint32_t mex_self(void) { return *(uint32_t *)VMA(0x180138090); }
static void mex_cfg(uint64_t now) {
    if (g_mex.cfg_at && now - g_mex.cfg_at < 2000) return;
    g_mex.cfg_at = now ? now : 1;
    FILE *f = exe_side_open("t2r-no-melee-exchange.txt", "r"); int o = f != NULL || mv2_on() || mv3_on(); if (f) fclose(f);     // melee v2 / v3: no turn-based exchange (v3 even with t2r-melee-v1.txt: mex / mseq / mqte are not mv3_stand-gated)
    if (o != g_mex.off || !g_mex.cfg_logged) { g_mex.cfg_logged = 1; xlog("mex: %s", o ? "OFF (t2r-no-melee-exchange.txt) - free swings" : "on (a melee press at a standing enemy within 2 m starts an exchange: shared clock, the defender's dodge decides, combo / counter beats)"); }
    g_mex.off = o;
    // Melee felt unresponsive: the held contact landed up to 516 ms after the fist touched (verdict waits for the
    // defender's window + the trip back). The hit now lands at contact again; the defender's late-press grace (melee_dodge.c) still drops a dodged blow.
    // t2r-mex-hold.txt = hold for the verdict (the earlier behaviour).
    f = exe_side_open("t2r-mex-hold.txt", "r"); g_mex.nohold = f == NULL; if (f) fclose(f);
    f = exe_side_open("t2r-mex-tune.txt", "r");
    if (f) { int v[3]; if (fscanf(f, "%d %d %d", &v[0], &v[1], &v[2]) == 3 && v[0] > 150 && v[0] < 1200 && v[1] > 150 && v[1] < 1200 && v[2] >= 0 && v[2] < 400) memcpy(g_mex.tune, v, sizeof v); fclose(f); }
}
static int mex_lat(uint32_t slot) { int l = (int)(psync_oneway((int)slot) + 40.5f); return l < 120 ? 120 : l > 260 ? 260 : l; }
static int mex_vis(uint32_t slot) { int v = (int)(psync_oneway((int)slot) + 0.5f); if (v < 40) v = 40; if (v > g_mex.tune[2]) v = g_mex.tune[2]; return v; }
static int mex_tc_raw(int wcls) { return wcls == 0 ? g_mex.tune[0] : wcls == 1 ? g_mex.tune[0] - 40 : wcls == 2 ? g_mex.tune[1] : g_mex.tune[1] + 80; }
static int mex_tc_of(int wcls) { return mtell_tc(wcls, mex_tc_raw(wcls)); }      // melee_tell.c: contact planned at the tell (320 ms) unless the clip is faster
static void mex_send(int slot, const uint8_t *b, int len) { if (g_send_tramp && slot >= 0 && slot < T2R_MAX_PEERS) g_send_tramp(MSG_MEX, (uint8_t *)b, (uint64_t)len, (uint64_t)slot); }
static void mex_tx_start(uint64_t now) {
    uint64_t in = g_mex.t0 > now ? g_mex.t0 - now : 0; if (in > 600) in = 600;
    // melee_qte.c: [10] flags (bit 0 QTE, bit 1 forced), [11..12] the attacker's press offset (old builds read 10 bytes and ignore the rest)
    uint8_t b[13] = {1, (uint8_t)g_mex.uid, (uint8_t)(g_mex.uid >> 8), (uint8_t)g_mex.slot, (uint8_t)g_mex.blow, (uint8_t)g_mex.wcls, (uint8_t)in, (uint8_t)(in >> 8), (uint8_t)g_mex.tc_ms, (uint8_t)(g_mex.tc_ms >> 8), (uint8_t)mq_tx_flags(), (uint8_t)mq_tx_a(), (uint8_t)(mq_tx_a() >> 8)};
    mex_send(g_mex.slot, b, 13);
}
static void mex_tx_ack(int slot, uint16_t uid, int ok, int why) { uint8_t b[6] = {2, (uint8_t)uid, (uint8_t)(uid >> 8), (uint8_t)ok, (uint8_t)why, (uint8_t)(ok ? mq_cap() : 0)}; mex_send(slot, b, 6); }   // [5] bit 0 = we run the QTE
static void mex_tx_res(uint64_t now) {
    uint64_t in = g_mex.verdict == 1 && g_mex.rdue > now ? g_mex.rdue - now : 0; if (in > 1500) in = 1500;
    uint8_t b[7] = {3, (uint8_t)g_mex.uid, (uint8_t)(g_mex.uid >> 8), (uint8_t)g_mex.verdict, (uint8_t)g_mex.blow, (uint8_t)in, (uint8_t)(in >> 8)};
    mex_send(g_mex.slot, b, 7);
}
static int mex_peer_ok(uint32_t s) {
    if (s >= T2R_MAX_PEERS || s == mex_self()) return 0;
    uint8_t *pe = mdg_peer(s);
    return pe && pe[0x4c] && !pe[0x4d] && *(uint64_t *)(pe + 0x60) && !is_teammate(s) && !g_peer_downed[s] && !g_puppet_dead_here[s];
}
// our held contact goes out through the normal hook (the whole feedback + send path runs now, as if the contact were happening at this moment)
static void mex_release(const char *why) {
    if (!g_mex.hold.on) return;
    int slot = g_mex.hold.slot; g_mex.hold.on = 0;
    if (g_mex.verdict == 2) { MXLOG("mex: u%04x held contact on slot %d dropped (%s) - the defender dodged it", g_mex.uid, slot, why); return; }   // (live u2001: a DODGED blow was released by the reset and landed)
    if (slot < 0 || slot >= T2R_MAX_PEERS || !mex_peer_ok((uint32_t)slot) || match_substate() != 6 || g_downed || g_down_dying || local_hp() <= 0.0f) { MXLOG("mex: u%04x held contact on slot %d dropped (%s; target or we are gone / down)", g_mex.uid, slot, why); return; }
    uint8_t *peer = mdg_peer((uint32_t)slot);
    g_mex.releasing = 1;
    if (peer) directhit_hook(peer, g_mex.hold.w, g_mex.hold.r8, g_mex.hold.dmg, g_mex.hold.lethal);
    g_mex.releasing = 0;
    MXLOG("mex: u%04x held contact on slot %d released (%s), %llu ms after it", g_mex.uid, slot, why, (unsigned long long)(GetTickCount64() - g_mex.contact_ms));
}
static void mex_reset(const char *why, int notify, int cool) {
    if (!g_mex.role) return;
    uint64_t now = GetTickCount64();
    int slot = g_mex.slot;
    if (g_mex.hold.on) mex_release(why);
    msq_break(why, cool);                                              // melee_seq.c: a running synced pair is aborted for both (a normal end lets a pair in its last 0.4 s finish)
    mq_end(why);                                                       // melee_qte.c: the melee camera hands back (SP blend), the beat state is cleared
    MXLOG("mex: u%04x END (%s) role %s blow %d beat %d after %llu ms%s", g_mex.uid, why, g_mex.role == 1 ? "attacker" : "defender", g_mex.blow, g_mex.beat, (unsigned long long)(now - g_mex.t_begin), cool ? ", pair cooldown 1.2 s" : "");
    if (notify && slot >= 0) { uint8_t b[4] = {4, (uint8_t)g_mex.uid, (uint8_t)(g_mex.uid >> 8), 0}; mex_send(slot, b, 4); }
    if (cool && slot >= 0 && slot < T2R_MAX_PEERS) { g_mex.pair_cool[slot] = now + MX_COOL_MS; msq_ended(slot, g_mex.uid, now); }
    padinj_block("melee-attack", 0);
    g_mex.role = 0; g_mex.beat = MXB_NONE; g_mex.slot = -1; g_mex.fired = 0; g_mex.verdict = 0; g_mex.res_pending = g_mex.start_pending = 0;
    g_mex.hold.on = 0; g_mex.block_until = 0;
}
// the engine takes this as a real press edge; the pace lock is cleared so the exchange's own cadence rules
static void mex_press(uint64_t now) {
    padinj_block("melee-attack", 0);
    g_mp.on = 0; g_mp.until = 0; g_mp.vlock_until = 0; g_mp.buf = 0; g_mp.fire_at = 0; g_mp_fire_t = g_mp_mask_t = 0;
    if (!padinj_press("melee-attack", MP_FIRE_MS + MP_MASK_MS)) mpace_wrapper_press(now);
    g_mex.bypass_until = now + 250;
}
static void mex_fire(uint64_t now) {
    mex_press(now);
    g_mex.fired = now; g_mex.move_at_fire = g_ms_curmove; g_mex.atk_at_fire = g_ms_atk; g_mex.swing_seen = 0; g_mex.contact = 0; g_mex.miss_done = 0; g_mex.verdict = 0; g_mex.hold.on = 0;
    g_mex.beat = MXB_ATK;
    g_mex.verd_dl = g_mex.t0 + (uint64_t)(g_mex.tc_ms + g_mex.vis_ms + g_mex.lat + (int)psync_oneway(g_mex.slot) + 220);
    MXLOG("mex: u%04x blow %d FIRE at T0 (%llu ms after the press); contact planned +%d ms, verdict due by +%d ms", g_mex.uid, g_mex.blow, (unsigned long long)(now - g_mex.t_begin), g_mex.tc_ms, (int)(g_mex.verd_dl - g_mex.t0));
}
static int mex_wcls(void) {
    uint64_t w = dc_weapon();
    if (w == fnv64("abby-unarmed")) return 0;
    if (knife_weapon_id(w)) return 1;
    int two = 0; mhfx_class(w, &two, NULL);
    return two ? 3 : 2;
}
// the attacker's candidate: nearest standing enemy within 2 m and +-60 deg of our facing
static int mex_cand(uint64_t now, float *dist, float *deg) {
    float mb[16]; const float *ml = uc4_my_loc(mb);
    if (!ml || !__builtin_isfinite(ml[0])) return -1;
    float fx = 2.0f * (ml[4] * ml[6] + ml[7] * ml[5]), fz = 1.0f - 2.0f * (ml[4] * ml[4] + ml[5] * ml[5]), fl = __builtin_sqrtf(fx * fx + fz * fz);
    if (!(fl > 1e-3f)) return -1;
    int best = -1; float bd = 1e9f, bc = 1.0f;
    for (uint32_t s = 0; s < T2R_MAX_PEERS; s++) {
        if (now < g_mex.pair_cool[s] || now < g_mex.nopeer[s] || !mex_peer_ok(s) || psync_busy_slot(s) || gx_busy_slot(s) || mdg_slot_immune(s)) continue;
        uint8_t *pe = mdg_peer(s);
        float pb[16]; const float *pl = puppet_locator(*(uint64_t *)(pe + 0x60), pb);
        if (!pl || !__builtin_isfinite(pl[0])) continue;
        float dx = pl[0] - ml[0], dz = pl[2] - ml[2], d = __builtin_sqrtf(dx * dx + dz * dz);
        if (d > MX_REACH || d < 0.05f || __builtin_fabsf(pl[1] - ml[1]) > 1.0f) continue;
        float c = (fx * dx + fz * dz) / (fl * d);
        if (c < MX_CONE_COS) continue;
        if (d < bd) { bd = d; bc = c; best = (int)s; }
    }
    if (best >= 0) { if (dist) *dist = bd; if (deg) *deg = __builtin_acosf(bc > 1.0f ? 1.0f : bc) * 57.29578f; }
    return best;
}
static int mex_a_ok(uint64_t now, int ignore_pace) {
    if (mdg_busy() || g_mhs.on || g_ms_atk || g_mhr.on || g_mdg.cmb_on || g_md_fb.on || (g_mdg.atk_lock_until && now < g_mdg.atk_lock_until) || (g_mdg.gun_lock_until && now < g_mdg.gun_lock_until)) return 0;
    if (g_kd_early_slot >= 0 || g_dm_kick_frame || g_upgrade_armed > 0 || dc_armed_at(now) || g_dcm.pend || g_dcm.on_att || g_dcm.on_vic || g_mdh.on || g_mdg.miss_until > now) return 0;
    if (!ignore_pace && mpace_locked()) return 0;
    return !interact_down();
}
static int mex_ready(void) { return !g_mex.off && g_send_tramp && padinj_ready() && match_substate() == 6; }
// a pair (dcounter / sequence) with `slot` ended: neither side can be engaged on it for ms (the victim's recovery)
static void mex_note_pair_end(int slot, int ms) {
    if (slot < 0 || slot >= T2R_MAX_PEERS) return;
    uint64_t u = GetTickCount64() + (uint64_t)ms;
    if (g_mex.rec_until[slot] < u) g_mex.rec_until[slot] = u;
}
// a whole match with 9 free swings and 0 exchanges and no line saying why. At every engine swing that starts
// outside an exchange: which gate kept the press from becoming an ENGAGE (per-slot candidate reasons included).
static void mex_why_free(uint64_t now) {
    if (g_mex.role) return;
    char b[640]; int n = 0;
    const char *busy = mdg_busy();
    n += snprintf(b + n, sizeof b - n, "ready %d (off %d send %d padinj %d sub %d)", mex_ready(), g_mex.off, g_send_tramp != NULL, padinj_ready(), match_substate());
    n += snprintf(b + n, sizeof b - n, " | busy %s mhs %d ms_atk %d mhr %d cmb %d fb %d atk_lock %d gun_lock %d kd %d kick %d upg %d dc %d dcm %d/%d/%d mdh %d miss %d pace %d interact %d aim %d bypass %d",
                  busy ? busy : "-", g_mhs.on, g_ms_atk != 0, g_mhr.on, g_mdg.cmb_on, g_md_fb.on, g_mdg.atk_lock_until > now, g_mdg.gun_lock_until > now, g_kd_early_slot >= 0, g_dm_kick_frame != 0,
                  g_upgrade_armed > 0, dc_armed_at(now), g_dcm.pend, g_dcm.on_att, g_dcm.on_vic, g_mdh.on, g_mdg.miss_until > now, mpace_locked(), interact_down(), pad_cmd_on("aim"), now < g_mex.bypass_until);
    float mb[16]; const float *ml = uc4_my_loc(mb);
    for (uint32_t s = 0; s < T2R_MAX_PEERS && n < (int)sizeof b - 80; s++) {
        uint8_t *pe = mdg_peer(s);
        if (!pe || !pe[0x4c] || s == mex_self() || is_teammate(s)) continue;
        float pb[16]; const float *pl = *(uint64_t *)(pe + 0x60) ? puppet_locator(*(uint64_t *)(pe + 0x60), pb) : NULL;
        float d = -1, dy = 0, c = -2;
        if (pl && ml) {
            float fx = 2.0f * (ml[4] * ml[6] + ml[7] * ml[5]), fz = 1.0f - 2.0f * (ml[4] * ml[4] + ml[5] * ml[5]), fl = __builtin_sqrtf(fx * fx + fz * fz);
            float dx = pl[0] - ml[0], dz = pl[2] - ml[2]; d = __builtin_sqrtf(dx * dx + dz * dz); dy = pl[1] - ml[1];
            if (fl > 1e-3f && d > 0.05f) c = (fx * dx + fz * dz) / (fl * d);
        }
        n += snprintf(b + n, sizeof b - n, " | slot %u: %.2f m dy %.2f cos %.2f 4d %d down %d dead %d cool %d nopeer %d rec %d psync %d gx %d imm %d",
                      s, d, dy, c, pe[0x4d], g_peer_downed[s], g_puppet_dead_here[s], now < g_mex.pair_cool[s], now < g_mex.nopeer[s], now < g_mex.rec_until[s], psync_busy_slot(s), gx_busy_slot(s), mdg_slot_immune(s));
    }
    static int nl; if (LOGCAP(nl, 60)) MXLOG("mex: free swing, no exchange - %s", b);
}
static int mex_engage(uint64_t now, const char *how) {
    if (g_mex.role || !mex_ready() || !mex_a_ok(now, 1)) return 0;
    float d = 0, deg = 0; int slot = mex_cand(now, &d, &deg);
    if (slot < 0 || pad_cmd_on("aim")) return 0;
    // (log 59840: ENGAGE two frames after our dcounter ended, the victim still in its recovery; one dodge gave ~4 s of guaranteed hits from spamming F): the victim of a
    // pair cannot be engaged again for 500 ms (650 after a counter). The press is held (not a free swing); only one pressed in the last 250 ms of the recovery fires. t2r-no-mex-recover.txt = off.
    { static int nr = -1; static uint64_t nra;
      if (now < g_mex.rec_until[slot] && !mex_optout("t2r-no-mex-recover.txt", &nr, &nra)) {
          if (!g_mex.rec_press) MXLOG("mex: ENGAGE on slot %d held - it is still recovering from the last pair (%d ms left)", slot, (int)(g_mex.rec_until[slot] - now));
          g_mex.rec_press = now; g_mex.rec_slot = slot; return 2; } }
    uint16_t uid = (uint16_t)(((mex_self() & 7u) << 13) | (++g_mex.ctr & 0x1fffu)); if (!uid) uid = 1;
    memset(&g_mex.hold, 0, sizeof g_mex.hold);
    g_mex.role = 1; g_mex.beat = MXB_ENG; g_mex.slot = slot; g_mex.blow = 1; g_mex.uid = uid; g_mex.wcls = mex_wcls(); g_mex.tc_ms = mex_tc_of(g_mex.wcls);
    g_mex.lat = mex_lat((uint32_t)slot); g_mex.vis_ms = mex_vis((uint32_t)slot); g_mex.t_begin = now; g_mex.t0 = now; g_mex.hard_dl = now + 9000;   // (no input delay - the defender's window is anchored to the START's arrival = the moment it sees the swing begin, so a lead buys it nothing)
    g_mex.acked = 0; g_mex.fired = 0; g_mex.verdict = 0; g_mex.hit_got = 0; g_mex.lastp = 1; g_mex.start_pending = 1; g_mex.start_at = now + 70; g_mex.contact = 0; g_mex.miss_done = 0;
    mq_begin(1, now, -1);
    mex_tx_start(now);
    MXLOG("mex: u%04x ENGAGE slot %d (%s): %.2f m, %.0f deg off our facing, blow 1, class %d, T0 in %d ms (one-way %.0f ms), contact +%d ms", uid, slot, how, (double)d, (double)deg, g_mex.wcls, g_mex.lat, (double)psync_oneway(slot), g_mex.tc_ms);
    return 1;
}
// melee_pace.c: the lock is over and a buffered press is about to be replayed: it becomes an ENGAGE when a target is in front
static int mex_engage_buffered(void) { return mex_engage(GetTickCount64(), "buffered press"); }
// recv_hit_hook (all damage on us): 1 = drop
static int mex_note_hit(uint64_t w, float dmg) {
    if (!g_mex.role || g_mex.releasing || !(dmg > 0.0f) || dmg >= 100000.0f) return 0;
    uint32_t from = g_last_hit_slot; uint64_t now = GetTickCount64();
    int blow = mhs_is_blow(w) && !mdg_is_thrown(w);
    if (g_dcm.on_att || g_dcm.on_vic) return 0;                       // dcounter.c owns both bodies
    if ((int)from != g_mex.slot) { mex_reset("a third party's hit broke it", 1, 0); return 0; }
    if (!blow) { mex_reset("a gun shot of the partner hit us - broken for both", 1, 0); return 0; }
    if (g_mex.beat == MXB_CTR && g_mex.role == 1) return 0;           // the counter press's own (plain) hit on the countered attacker
    if (g_mex.role == 2 && g_mex.beat == MXB_ATK && g_mex.verdict != 2 && !g_mex.hit_got) {
        g_mex.hit_got = 1; g_mex.hit_got_ms = now;
        // (live log 59868: contact +282 ms, "no verdict by the deadline - safe default HIT" -> the hit and the synced pair came +922 ms, a ~640 ms freeze): the blow landing
        // here set verdict = 1 silently and moved to COMBO, where nothing ever sent the verdict (mex_def_verdict only ran in beat ATK on window close) - the attacker waited for its
        // deadline every time the blow arrived before the window closed. A landed blow IS the HIT verdict: answer at once (window closed now, R = now).
        if (!g_mex.verdict) { g_mex.win_hi = now; mex_def_verdict(now, 1, "the blow landed on us - answered at once"); }
        mq_after_hit(now);                                             // melee_qte.c: the next beat opens with the pair's hand-off (this one is spent)
        g_mex.beat = MXB_COMBO; g_mex.combo_until = now + MX_COMBO_MS + (uint64_t)g_mex.lat * 2 + 300;
        MXLOG("mex: u%04x blow %d HIT lands on us at +%llu ms", g_mex.uid, g_mex.blow, (unsigned long long)(now - g_mex.t0));
        return 0;
    }
    // (log 60043: "blow from slot 1 ... outside its beat dropped" - the victim's own swing was thrown away): the attacker no longer discards its partner's swing. Unless the
    // partner is inside a paired move (then its blow is a stray of the scripted body), it lands like a normal blow and the exchange ends as a trade (both free, 1.2 s cooldown).
    // t2r-mex-no-trade.txt = the old drop.
    { static int nt = -1; static uint64_t nta;
      if (mq_active()) {          // melee_qte.c: no trade - the partner's own swing is not a beat input (a STRIKE is a button press on the shared clock, resolved at the START)
          static int nq; if (LOGCAP(nq, 60)) xlog("mqte: u%04x a stray blow of slot %u (role %d, beat %d) dropped - inside the QTE only the beats deal damage", g_mex.uid, from, g_mex.role, g_mex.beat);
          return 1; }
      if (g_mex.role == 1 && !msq_on() && !g_dcm.on_att && !g_dcm.on_vic && !psync_busy_slot(from) && !mex_optout("t2r-mex-no-trade.txt", &nt, &nta)) {
          mex_reset("the partner's own swing hit us - a trade", 1, 1); return 0; } }
    static int nd; if (LOGCAP(nd, 60)) xlog("mex: u%04x blow from slot %u (weapon %llx, dmg %.0f) outside its beat dropped", g_mex.uid, from, (unsigned long long)w, (double)dmg);
    return 1;
}
// the attacker's verdict is HIT and the contact went through: COMBO window (or the end after blow 3)
static void mex_after_hit(uint64_t now) {
    mq_after_hit(now);
    if (g_mex.blow >= MX_MAX_BLOW) {
        if (msq_try_start(now, 1)) { g_mex.beat = MXB_COMBO; g_mex.combo_until = now + 3000; return; }          // melee_seq.c: blow 3's pair, the exchange ends with it
        mex_reset("blow 3 landed (v1: the finisher pair is not routed here)", 1, 1); return;
    }
    g_mex.beat = MXB_COMBO; g_mex.combo_until = now + MX_COMBO_MS;
    msq_try_start(now, 0);                                             // melee_seq.c: the landed blow plays its synced pair (the combo window moves to its hand-off)
    MXLOG("mex: u%04x blow %d HIT resolved at +%llu ms: combo window %d ms (melee press = blow %d)", g_mex.uid, g_mex.blow, (unsigned long long)(now - g_mex.t0), MX_COMBO_MS, g_mex.blow + 1);
}
static void mex_do_miss(const char *why) {
    if (g_mex.miss_done) return;
    g_mex.miss_done = 1;
    if (g_mex.hold.on) { g_mex.hold.on = 0; MXLOG("mex: u%04x held contact dropped - the defender dodged", g_mex.uid); }
    mdg_attacker_missed(why, g_mex.slot);
    g_mex.beat = MXB_CTR; g_mex.ctr_until = GetTickCount64() + 2400; g_mex.ctr_seen = 0;
}
// hitsend_hook / directhit_hook: OUR contact on `slot`. 1 = held / dropped (no send, no fx)
static int mex_contact(uint32_t slot, uint64_t w, float dmg, uint8_t lethal, int route, uint64_t r8) {
    if (mq_active() && g_mex.role == 2 && g_mex.beat != MXB_CTR && !g_mex.releasing && (int)slot == g_mex.slot && mhs_is_blow(w) && !mdg_is_thrown(w)) {   // melee_qte.c: the defender's own swing (a lost STRIKE / a cancelled blow) deals nothing
        static int nd; if (LOGCAP(nd, 60)) xlog("mqte: u%04x our own blow on slot %u dropped (we are the defender of this beat)", g_mex.uid, slot);
        return 1;
    }
    if (g_mex.role != 1 || g_mex.releasing || (int)slot != g_mex.slot || !mhs_is_blow(w) || mdg_is_thrown(w)) return 0;
    uint64_t now = GetTickCount64();
    if (g_mex.beat != MXB_ATK || g_mex.contact) {
        if (g_mex.beat == MXB_CTR && g_mex.verdict == 1) return 0;
        static int ns; if (LOGCAP(ns, 60)) xlog("mex: u%04x stray contact on slot %u (beat %d) dropped - free blows do not leak into an exchange", g_mex.uid, slot, g_mex.beat);
        return 1;
    }
    mtell_note_contact(g_mex.wcls, (int)(now - g_mex.t0));
    g_mex.contact = 1; g_mex.contact_ms = now; g_melee_contact_at = g_t60 ? g_t60 : 1; msq_note_contact(dmg);
    MXLOG("mex: u%04x blow %d CONTACT at +%llu ms (planned +%d) dmg %.0f%s, verdict %s", g_mex.uid, g_mex.blow, (unsigned long long)(now - g_mex.t0), g_mex.tc_ms, (double)dmg, lethal ? " lethal" : "", g_mex.verdict == 1 ? "HIT" : g_mex.verdict == 2 ? "DODGED" : "pending");
    if (g_mex.verdict == 2) { mex_do_miss("melee exchange: the defender dodged"); return 1; }
    if (g_mex.verdict == 1 && now >= g_mex.rdue) { mex_after_hit(now); return 0; }
    if (dmg > 25.0f || lethal || route != 1 || g_mex.nohold) { MXLOG("mex: u%04x contact not held (%s)", g_mex.uid, g_mex.nohold ? "no t2r-mex-hold.txt" : "downing / lethal / other route - the old path"); return 0; }
    g_mex.hold.on = 1; g_mex.hold.slot = (int)slot; g_mex.hold.w = w; g_mex.hold.r8 = r8; g_mex.hold.dmg = dmg; g_mex.hold.lethal = lethal;
    return 1;
}
// ---- the defender
static int mex_window_end(uint32_t s, uint64_t *end) {         // melee_dodge.c mdg_window: 0 = not ours, 1 = *end is the window end, 2 = closed
    if (!g_mex.role || (int)s != g_mex.slot) return 0;
    if (g_mex.role == 2 && g_mex.beat == MXB_ATK && !g_mex.verdict && !g_mex.burnt && GetTickCount64() <= g_mex.win_hi) { *end = g_mex.win_hi; return 1; }
    return 2;
}
static int mex_swing_msg(uint32_t slot, const uint8_t *buf, uint64_t len) {       // MSG_DODGE_SWING of our attacker: keeps the shared-clock swing time, takes only its class / hand
    if (g_mex.role != 2 || (int)slot != g_mex.slot || (g_mex.beat != MXB_ATK && g_mex.beat != MXB_ENG)) return 0;
    g_mdg.sw[slot].kind = len >= 1 && buf ? (buf[0] & 1) : 0; g_mdg.sw[slot].cls = len >= 2 && buf && buf[1] < 3 ? buf[1] : 0;
    g_mdg.sw[slot].hand = len >= 3 && buf ? (buf[2] & 1) : 0; g_mdg.sw[slot].hand_real = len >= 3 && buf ? (buf[2] >> 1) & 1 : 0;
    return 1;
}
static void mex_note_early_press(void) { if (g_mex.role == 2 && g_mex.beat == MXB_ENG && !g_mex.burnt) { g_mex.burnt = 1; MXLOG("mex: u%04x dodge pressed before the window opened - burnt for this beat", g_mex.uid); } }
static void mex_def_verdict(uint64_t now, int v, const char *why) {
    g_mex.verdict = v; g_mex.verd_ms = now;
    uint64_t close = g_mex.win_hi > now ? g_mex.win_hi : now;
    g_mex.rdue = v == 1 ? close : now;     // (no extra buffer - the attacker applies the HIT on arrival; its hold is ~ RTT + the window tail, not RTT + lat_buf)
    mex_tx_res(now); g_mex.res_pending = 1; g_mex.res_at = now + 60;
    MXLOG("mex: u%04x blow %d verdict %s (%s) at +%lld ms, R in %lld ms", g_mex.uid, g_mex.blow, v == 1 ? "HIT" : "DODGED", why, (long long)(now - g_mex.t0), (long long)(g_mex.rdue - now));
}
// melee_dodge.c mdg_start: our dodge press
static void mex_note_dodge(uint32_t slot, uint64_t now) {
    if (g_mex.role != 2 || (int)slot != g_mex.slot || g_mex.beat != MXB_ATK || g_mex.verdict) return;
    if (g_mdg.iframe_until) mex_def_verdict(now, 2, "dodge pressed in the window");
    else mex_def_verdict(now, 1, "dodged INTO the blow - no immunity");
}
// ---- messages
static void mex_recv(uint32_t slot, const uint8_t *buf, uint64_t len) {
    if (slot >= T2R_MAX_PEERS || slot == mex_self() || !buf || len < 4) return;
    uint64_t now = GetTickCount64();
    int op = buf[0]; uint16_t uid = (uint16_t)(buf[1] | (buf[2] << 8));
    if (op < 1 || op > 4 || (op == 1 && len < 10) || (op == 2 && len < 5) || (op == 3 && len < 7)) { pt_deny(PTK_wire, slot); return; }
    if (op == 1) {
        int dslot = buf[3], blow = buf[4], wcls = buf[5], t0in = buf[6] | (buf[7] << 8), tc = buf[8] | (buf[9] << 8);
        if (dslot != (int)mex_self() || blow < 1 || blow > MX_MAX_BLOW || wcls > 3 || t0in > 700 || tc < 150 || tc > 1500) { pt_deny(PTK_wire, slot); return; }
        const char *no = NULL;
        if (mq_ignore_start((int)slot, uid, len >= 11 ? buf[10] : 0, now)) return;
        int qflags = len >= 11 ? buf[10] : 0, qa = len >= 13 ? buf[11] | (buf[12] << 8) : 0, qk = mq_start_ok((int)slot, uid, blow, qflags);   // melee_qte.c: flags / the attacker's press offset / the QTE cases
        if (g_mex.off || !mex_ready()) no = "exchange off here";
        else if (qk) { /* melee_qte.c: a forced START on our attacker (it lost the beat), a yield, the next blow after a flip */ }
        else if (g_mex.role && g_mex.slot == (int)slot && g_mex.uid == uid && g_mex.blow == blow) { mex_tx_ack((int)slot, uid, 1, 0); return; }      // a repeat
        else if (g_mex.role == 1 && g_mex.beat == MXB_ENG && g_mex.slot == (int)slot && slot < mex_self()) { mex_reset("yielded: both pressed in the same moment, the lower slot attacks", 0, 0); }
        else if (g_mex.role == 2 && g_mex.slot == (int)slot && g_mex.uid == uid && blow == g_mex.blow + 1 && (g_mex.beat == MXB_COMBO || (g_mex.beat == MXB_ATK && g_mex.hit_got))) { /* the next blow of the combo */ }
        else if (g_mex.role) no = "busy (in another exchange / beat)";
        else if (msq_cooling(slot, now)) no = "less than 2.5 s since the last melee sequence with it (no chaining)";
        if (!no && (mdg_busy() || g_downed || g_dcm.on_att || g_dcm.on_vic || is_teammate(slot) || !mex_peer_ok(slot))) no = "busy / down / not an enemy in reach";
        if (!no && g_mex.role != 2) { float lb[16], pb[16]; const float *ml = uc4_my_loc(lb); uint64_t h = puppet_handle(slot); const float *pl = h ? puppet_locator(h, pb) : NULL;
            if (!ml || !pl || (pl[0] - ml[0]) * (pl[0] - ml[0]) + (pl[2] - ml[2]) * (pl[2] - ml[2]) > 3.6f * 3.6f) no = "the attacker is not in reach on our screen"; }
        if (no) { mex_tx_ack((int)slot, uid, 0, 1); MXLOG("mex: START u%04x from slot %u refused: %s", uid, slot, no); return; }
        float ow = psync_oneway((int)slot);
        if (qk == 2 && g_mex.role == 2 && mq_strike_eval(now, (int)slot, qa, (qflags & 2) != 0)) return;     // melee_qte.c: our STRIKE was first - we answered with a forced START of our own
        if (qk == 1) mq_yield(now, 1); else if (qk == 2 && g_mex.role == 1) mq_yield(now, 0);
        int cont = g_mex.role == 2 || qk != 0;
        if (!cont) memset(&g_mex.hold, 0, sizeof g_mex.hold);
        g_mex.role = 2; g_mex.slot = (int)slot; g_mex.uid = uid; g_mex.blow = blow; g_mex.wcls = wcls; g_mex.tc_ms = tc; g_mex.beat = MXB_ENG;
        g_mex.lat = mex_lat(slot); g_mex.vis_ms = mex_vis(slot);
        int dly = t0in - (int)ow; if (dly < 20) dly = 20;
        g_mex.t0 = now + (uint64_t)dly; g_mex.win_hi = g_mex.t0 + (uint64_t)(tc + g_mex.vis_ms);
        if (!cont) g_mex.t_begin = now;
        g_mex.hard_dl = now + 9000; g_mex.verdict = 0; g_mex.burnt = (qflags & 2) != 0; g_mex.hit_got = 0; g_mex.ctr_armed = 0; g_mex.ctr_seen = 0; g_mex.res_pending = 0; g_mex.acked = 1; g_mex.contact = 0; g_mex.miss_done = 0; g_mex.fired = 0;   // (a forced START = the blow we lost: no dodge window)
        if (!cont) mq_begin(2, now, qflags);
        mex_tx_ack((int)slot, uid, 1, 0);
        MXLOG("mex: u%04x blow %d START from slot %u accepted: T0 in %d ms (sent %d, one-way %.0f), contact +%d ms, dodge window to +%d ms, lat_buf %d", uid, blow, slot, dly, t0in, (double)ow, tc, tc + g_mex.vis_ms, g_mex.lat);
        return;
    }
    if (!g_mex.role || g_mex.slot != (int)slot || g_mex.uid != uid) return;
    if (op == 2) {
        if (g_mex.role != 1) return;
        if (buf[3]) { g_mex.acked = 1; g_mex.start_pending = 0; mq_peer_ack(len >= 6 ? (buf[5] & 1) : 0); MXLOG("mex: u%04x slot %u ACK ok (%llu ms after the press)", uid, slot, (unsigned long long)(now - g_mex.t_begin)); return; }
        MXLOG("mex: u%04x slot %u REFUSED (reason %d) - free swing", uid, slot, buf[4]);
        g_mex.pair_cool[slot] = now + 1500;
        int pre = g_mex.beat == MXB_ENG && !g_mex.fired;
        mex_reset("refused by the defender", 0, 0);
        g_mex.pair_cool[slot] = now + 1500;
        if (pre) mex_press(now);                                       // the plain press, now: this swing is free
        return;
    }
    if (op == 3) {
        if (g_mex.role != 1 || buf[4] != g_mex.blow || g_mex.verdict || (buf[3] != 1 && buf[3] != 2) || (g_mex.beat != MXB_ENG && g_mex.beat != MXB_ATK)) return;
        int rin = buf[5] | (buf[6] << 8); if (rin > 1500) { pt_deny(PTK_wire, slot); return; }
        float ow = psync_oneway((int)slot);
        g_mex.acked = 1; g_mex.verdict = buf[3]; g_mex.verd_ms = now;
        int dr = rin - (int)ow; if (dr < 0) dr = 0;
        g_mex.rdue = g_mex.verdict == 1 ? now + (uint64_t)dr : now;
        MXLOG("mex: u%04x blow %d verdict %s from slot %u at +%lld ms, R in %d ms%s", uid, g_mex.blow, g_mex.verdict == 1 ? "HIT" : "DODGED", slot, (long long)(now - g_mex.t0), dr, g_mex.hold.on ? " (contact held)" : "");
        return;
    }
    if (op == 4) mex_reset("the partner ended it", 0, 1);
}
// ---- per frame
static int mex_press_edge(uint64_t now) {
    int pr = padinj_blocked_raw() || (now < g_mex.block_until && game_focused() && (GetAsyncKeyState(0x46) & 0x8000));
    if (pr && interact_down()) pr = 0;
    int e = pr && !g_mex.lastp; g_mex.lastp = pr; return e;
}
static void mex_tick(void) {
    uint64_t now = GetTickCount64();
    mex_cfg(now);
    msq_tick();                                                        // melee_seq.c: the pair request / the pair's end / the exchange's clocks while it plays
    mq_tick(now);                                                      // melee_qte.c: melee camera, prompts + closing bar, distance end
    if (match_substate() != 6 || g_mex.off || !g_send_tramp) { if (g_mex.role) mex_reset(g_mex.off ? "switched off" : "left the match", g_mex.off, 0); return; }
    if (!padinj_ready()) padinj_install();
    if (!padinj_ready()) return;
    int want_block = 0;
    if (g_mex.role) {
        g_mp.buf = 0;                                                  // the pace lock's press buffer must not replay a free swing into the exchange
        int slot = g_mex.slot;
        const char *end = NULL;
        int dc_on = g_dcm.on_att || g_dcm.on_vic;
        if (g_downed || g_down_dying || g_uc4_dying_until || local_hp() <= 0.0f || g_down_at) end = "we are down / dead";
        else if (!dc_on && !msq_on() && mdg_busy()) end = "we are busy (stun / paired move / execution)";
        else if (slot < 0 || !mex_peer_ok((uint32_t)slot)) end = "the partner is gone / down / dead";
        else if (now > g_mex.hard_dl) end = "timeout";
        if (end) { mex_reset(end, 1, 1); return; }
        if (g_mex.start_pending && now >= g_mex.start_at) { g_mex.start_pending = 0; if (!g_mex.acked && g_mex.role == 1) mex_tx_start(now); }
        if (g_mex.res_pending && now >= g_mex.res_at) { g_mex.res_pending = 0; mex_tx_res(now); }
        if (g_mex.role == 1) {
            // the attacker's own firing is locked while it attacks (the defender keeps its gun); melee / camera / move / evade stay
            if (!g_mhs.on && g_mex.beat != MXB_CTR) { uint64_t ex[4] = {fnv64("camera"), fnv64("move"), fnv64("melee-attack"), fnv64("evade")}; dc_call(fnv64("joypad-disable-all-commands-except"), 4, ex); }
            want_block = 1;
            int pedge = mex_press_edge(now);                       // (kept fresh every frame: a button held since the first press is no combo press)
            if (g_mex.beat == MXB_ENG) {
                if (now >= g_mex.t0) { mex_fire(now); want_block = 0; }
            } else if (g_mex.beat == MXB_ATK) {
                if (!g_mex.swing_seen) {
                    if (g_mex.contact || (g_ms_atk && (!g_mex.atk_at_fire || g_ms_curmove != g_mex.move_at_fire))) {     // (a contact IS the swing: u2001 reset 'not taken' after its contact)
                     g_mex.swing_seen = 1; g_mex.swing_ms = now; MXLOG("mex: u%04x swing started %llu ms after T0", g_mex.uid, (unsigned long long)(now - g_mex.t0)); }
                    else if (now > g_mex.fired + 500) { mex_reset("the press was not taken by the engine", 1, 1); return; }
                }
                if (!g_mex.acked && now > g_mex.t0 + MX_ACK_GRACE_MS) { g_mex.nopeer[slot] = now + 20000; mex_reset("no answer from the partner (old build?) - free swings with it for 20 s", 0, 0); return; }
                // the deadline is only a fallback. A contact we already saw with no verdict one round trip + 300 ms later (the defender's HIT answer to a landed blow is sent at its
                // arrival now, the dodge answer at the press) resolves as HIT instead of waiting for the planned +900 ms.
                if (!g_mex.verdict && g_mex.contact && now > g_mex.contact_ms + (uint64_t)(2.0f * psync_oneway(slot)) + 300) { g_mex.verdict = 1; g_mex.rdue = now; MXLOG("mex: u%04x no verdict a round trip + 300 ms after the contact - fallback HIT", g_mex.uid); }
                if (!g_mex.verdict && now > g_mex.verd_dl) { g_mex.verdict = 1; g_mex.rdue = now; MXLOG("mex: u%04x no verdict by the deadline - safe default HIT", g_mex.uid); }
                mq_beat_contact(now);                              // melee_qte.c: the engine found no contact (psync holds the puppet's collider): the beat's own contact goes out
                if (g_mex.verdict == 1 && g_mex.hold.on && now >= g_mex.rdue) { mex_release("verdict HIT due"); mex_after_hit(now); if (!g_mex.role) return; }
                else if (g_mex.verdict == 1 && g_mex.contact && !g_mex.hold.on && now >= g_mex.rdue) { mex_after_hit(now); if (!g_mex.role) return; }
                else if (g_mex.verdict == 1 && !g_mex.contact && now > (g_mex.rdue > g_mex.t0 + g_mex.tc_ms ? g_mex.rdue : g_mex.t0 + g_mex.tc_ms) + 450) { mex_reset("HIT but the blow found no contact", 1, 1); return; }
                else if (g_mex.verdict == 2 && !g_mex.miss_done && (g_mex.contact || now >= g_mex.t0 + g_mex.tc_ms + 250)) mex_do_miss("melee exchange: the defender dodged (no contact)");
            } else if (g_mex.beat == MXB_COMBO) {
                int q = mq_active();                               // melee_qte.c owns the window, prompt and bar when on
                if (!q && now > g_mex.combo_until) { mex_reset("no combo press", 1, 1); return; }
                uint64_t h = puppet_handle((uint32_t)slot);
                if (!q && (!msq_on() || msq_left_ms() < 350)) { g_wpq_glyph = "gen:attack"; if (h) world_prompt(h, "Combo", -1.0f); g_wpq_glyph = NULL; }
                int cpress = msq_combo_press(pedge, now);
                if (q && mq_atk_beat(now, slot, &cpress)) return;
                if (cpress) {
                    float d = 0; int c = mex_cand(now, &d, NULL);
                    if (c != slot) { mex_reset("combo press but the partner is out of reach", 1, 1); return; }
                    g_mex.blow++; g_mex.lat = mex_lat((uint32_t)slot); g_mex.t0 = now; g_mex.vis_ms = mex_vis((uint32_t)slot); g_mex.beat = MXB_ENG; g_mex.fired = 0; g_mex.verdict = 0;
                    g_mex.contact = 0; g_mex.miss_done = 0; g_mex.swing_seen = 0; g_mex.acked = 1; g_mex.start_pending = 1; g_mex.start_at = now + 70;
                    if (q) mq_note_press(now);
                    mex_tx_start(now);
                    MXLOG("mex: u%04x COMBO press: blow %d, T0 in %d ms", g_mex.uid, g_mex.blow, g_mex.lat);
                }
            } else if (g_mex.beat == MXB_CTR) {
                if (dc_on) g_mex.ctr_seen = 1;
                if (g_mex.ctr_seen && !dc_on) { if (mq_active()) { mq_flip(now, "the counter is over - the dodger holds the initiative"); return; } mex_reset("counter over", 1, 1); return; }
                if (!g_mex.ctr_seen && now > g_mex.ctr_until) { if (mq_active()) { mq_lapse(now, "no counter came - the dodger holds the initiative"); return; } mex_reset("no counter came", 1, 1); return; }
            }
        } else {                                                       // the defender
            want_block = !(g_mex.beat == MXB_CTR && dc_armed_at(now) && now >= g_mdg.melee_ok_at);
            // melee_qte.c: the same gun lock as the attacker's while the melee camera runs (gun aim / reticle / ADS off); dodge + melee stay
            if (mq_active() && !g_mhs.on && g_mex.beat != MXB_CTR) { uint64_t ex[6] = {fnv64("camera"), fnv64("move"), fnv64("melee-attack"), fnv64("evade"), fnv64("dodge"), fnv64("evade-start")}; dc_call(fnv64("joypad-disable-all-commands-except"), 6, ex); }
            if (g_mex.beat == MXB_ENG && now >= g_mex.t0) {
                g_mex.beat = MXB_ATK;
                g_mdg.sw[slot].ms = g_mex.t0; g_mdg.sw[slot].open_ms = 0; g_mdg.sw[slot].seq = ++g_mdg.seq_n;
                if (!g_mhr.on) g_mhr.last_start_ms = 0;              // every blow of the exchange gets its SP reaction (not the 1.0 s grazing skip)
                g_mhs.immune_until = 0;
                mtell_cue((uint32_t)slot, puppet_handle((uint32_t)slot), g_mex.wcls >= 2, "exchange T0");
                int can = !mdg_off() && now >= g_mdg.cooldown_until && now >= g_mdg.miss_until && !mdg_busy() && !g_mex.burnt;
                MXLOG("mex: u%04x blow %d T0: swing starts on the shared clock, dodge window to +%d ms (%s)", g_mex.uid, g_mex.blow, g_mex.tc_ms + g_mex.vis_ms, can ? "open" : "NO window: cooldown / busy / burnt");
                if (!can) { g_mex.win_hi = now; mex_def_verdict(now, 1, "no dodge available"); }
            } else if (g_mex.beat == MXB_ATK) {
                if (!g_mex.verdict && now >= g_mex.win_hi) mex_def_verdict(now, 1, "window closed without a dodge");
                else if (g_mex.verdict == 2 && !g_mex.ctr_armed && now >= g_mex.win_hi) {
                    g_mex.ctr_armed = 1; dc_arm((uint32_t)slot);
                    g_mex.beat = MXB_CTR; g_mex.ctr_seen = 0;
                    g_mex.ctr_until = (g_mdg.melee_ok_at > now ? g_mdg.melee_ok_at : now) + (uint64_t)sk_counter_window_ms() + 500;
                    MXLOG("mex: u%04x DODGED -> the counter is dcounter.c's (window to +%llu ms)", g_mex.uid, (unsigned long long)(g_mex.ctr_until - now));
                } else if (g_mex.verdict == 1 && !g_mex.hit_got && !msq_on() && now > g_mex.rdue + (uint64_t)psync_oneway(slot) + 600) { mex_reset("HIT but the blow never arrived (the attacker's missed)", 1, 1); return; }
            } else if (g_mex.beat == MXB_COMBO) {
                if (mq_active()) { if (mq_def_beat(now, slot)) return; }
                else if (now > g_mex.combo_until) { mex_reset("no next blow", 1, 1); return; }
            } else if (g_mex.beat == MXB_CTR) {
                if (g_dcm.on_att && g_dcm.slot == slot) g_mex.ctr_seen = 1;
                if (g_mex.ctr_seen && !dc_on) { if (mq_active()) { mq_flip(now, "our counter is over - we hold the initiative"); return; } mex_reset("counter over", 1, 1); return; }
                if (!g_mex.ctr_seen && !dc_armed_at(now) && !g_dcm.pend && now > g_mex.ctr_until) { if (mq_active()) { mq_lapse(now, "no counter pressed - we hold the initiative"); return; } mex_reset("no counter pressed", 1, 1); return; }
            }
        }
    } else {                                                           // no exchange: hide a melee press from the engine while a target is in front, so it can become an ENGAGE
        if (g_mex.rec_press) {                                         // a press held during the victim's recovery: fires only if it is younger than 250 ms when the recovery ends
            int rs = g_mex.rec_slot;
            if (now - g_mex.rec_press > 250) { g_mex.rec_press = 0; MXLOG("mex: held ENGAGE press dropped (older than 250 ms)"); }
            else if (rs < 0 || now >= g_mex.rec_until[rs]) { g_mex.rec_press = 0; mex_engage(now, "press after the recovery"); }
        }
        if (mex_a_ok(now, 0) && now >= g_mex.bypass_until) {
            float d, deg;
            if (mex_cand(now, &d, &deg) >= 0 && !pad_cmd_on("aim")) {
                want_block = 1;
                if (mex_press_edge(now)) mex_engage(now, "press");
            } else g_mex.lastp = 0;
        } else g_mex.lastp = 0;
    }
    if (want_block && padinj_block("melee-attack", now + 150)) g_mex.block_until = now + 150;
}

// ---- a sequence slows players down instead of locking them (they can move, much slower): while we are in an active
// exchange / sequence (ENGAGE .. COMBO beats, a running pair; not the dodge or the counter) our own movement runs at MXS pct % (default 40) of normal, no sprint advantage, turning free;
// it ramps in / out over 300 ms and ends with the exchange (third-party hit, down, END). Mechanism: the same motion-match speed multipliers skills.c sk_movement already drives
// every frame for Agility / the 10 % slowdown (sprint / crouch / run); this factor multiplies them there (mxs_factor). Only OUR body is touched, each client slows itself; teammates and
// bystanders have no exchange and run at full speed. Tuning: t2r-mex-slow.txt "<percent 15..100>"; opt-out t2r-no-mex-slow.txt.
#define MXS_RAMP_MS 300
static struct { float cur, lo; uint64_t last, cfg_at; int pct, off, on_logged; } g_mxs = {.cur = 1.0f, .lo = 0.4f, .pct = 40};
static int mxs_active(void) {
    if (!g_mex.role || match_substate() != 6 || g_downed || g_down_dying || g_down_at || local_hp() <= 0.0f) return 0;
    if (g_mex.beat == MXB_CTR || g_mex.beat == MXB_NONE) return 0;
    if (g_mex.beat == MXB_ATK && g_mex.verdict == 2) return 0;       // dodged: the dodge / counter own the body
    return 1;
}
static float mxs_factor(float *lo) {
    uint64_t now = GetTickCount64();
    if (!g_mxs.cfg_at || now - g_mxs.cfg_at > 2000) {
        g_mxs.cfg_at = now ? now : 1;
        FILE *f = exe_side_open("t2r-no-mex-slow.txt", "r"); g_mxs.off = f != NULL; if (f) fclose(f);
        f = exe_side_open("t2r-mex-slow.txt", "r");
        if (f) { int p; if (fscanf(f, "%d", &p) == 1 && p >= 15 && p <= 100) g_mxs.pct = p; fclose(f); }
    }
    float tgt = !g_mxs.off && mxs_active() ? g_mxs.pct / 100.0f : 1.0f;
    float dt = g_mxs.last && now > g_mxs.last ? (float)(now - g_mxs.last) / 1000.0f : 0.0f;
    g_mxs.last = now; if (dt > 0.1f) dt = 0.1f;
    float step = dt / (MXS_RAMP_MS / 1000.0f) * (1.0f - g_mxs.pct / 100.0f);
    if (g_mxs.cur < tgt) { g_mxs.cur += step; if (g_mxs.cur > tgt) g_mxs.cur = tgt; }
    else if (g_mxs.cur > tgt) { g_mxs.cur -= step; if (g_mxs.cur < tgt) g_mxs.cur = tgt; }
    g_mxs.lo = g_mxs.pct / 100.0f;
    if (tgt < 1.0f && !g_mxs.on_logged) { g_mxs.on_logged = 1; xlog("mex: movement slowed to %d %% for the exchange (ramp %d ms; no sprint gain, turning free)", g_mxs.pct, MXS_RAMP_MS); }
    if (tgt >= 1.0f && g_mxs.on_logged && g_mxs.cur >= 1.0f) { g_mxs.on_logged = 0; xlog("mex: movement back to normal"); }
    if (lo) *lo = g_mxs.lo;
    return g_mxs.cur;
}
static int spm_in_exchange(void) { return g_mex.role != 0 || mdu_engaged(); }   // (melee_duel.c: the duel keeps the framing too)
