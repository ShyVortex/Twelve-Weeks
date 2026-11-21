// bodyshield.c - the BODYSHIELD skill (design + reasons: re/bodyshield-1117.md; pure rules: bodyshield.h, tests/bodyshield_test.c).
// Included from t2r-ext.c after melee_pullout.c (uses psync, the world prompt, mpn_e_edge, the skill levels). Log prefix "bodyshield:".
//
// A player with the skill presses E behind / beside a standing enemy within BS_REACH_M: a psync pair of kind PS_BODYSHIELD starts, a 3-segment chain
//   [0] ENTER  SP's meatshield grab (back / left / right) - ellie-meatshield-enter-* + npc-meatshield-enter-* or Abby's *--abby + *--npc-f
//   [1] HOLD   the struggle loop of the pair (-aim variant once the shield is raised), restarted at its end
//   [2] END    picked when the grab ends: the NPC-escapes pair, the choke / neck-stab finisher, the finisher's abort, the shield death
// every client switches the segments on the same MSG_BS message (paired.c psync_bs_chain). Ownership, as the pin QTE: the VICTIM judges its escape
// (QTE / mash / Iron Grip II) on its own screen and owns its death; the ATTACKER owns its aim, its damage and the kill press.
// v1 slice: the hold is anchored (psync ap) - the shielder turns the camera and aims but does not walk the victim around yet; the
// locomotion hold (npc-meatshield-loop-* glued to the shielder) is slice 2 in the doc. t2r-no-bodyshield.txt next to the exe = off.
#include "bodyshield.h"

#define MSG_BS 0x5C                // ours (free in the recv chain, re/bodyshield-1117.md "Net protocol")
enum { BSO_ACC = 1, BSO_AIM = 2, BSO_END = 3, BSO_KILL = 4, BSO_TEST = 9 };   // (BSO_TEST: dev builds only, the test driver arms the victim)
typedef struct __attribute__((packed)) {
    uint8_t op, reason;            // BSO_*, BS_END_* (END) / 1 (AIM on)
    uint16_t kb_ms;                // ACC: the victim's own kill block (its Iron Grip can lengthen the attacker's)
    uint32_t uid;                  // the psync uid of the grab
} bs_wire;
_Static_assert(sizeof(bs_wire) == 8, "bs_wire layout");

// the move word of the START (psync_wire.move): tag | level << 8 | set << 4 | dir. Every client builds the same chain from it.
#define BS_MOVE_TAG 0xB500000000000000ULL
enum { BS_DIR_BACK, BS_DIR_LEFT, BS_DIR_RIGHT };
enum { BS_SET_ELLIE, BS_SET_ABBY };
static uint64_t bs_move_word(int lv, int set, int dir) { return BS_MOVE_TAG | ((uint64_t)(lv & 0xf) << 8) | ((uint64_t)(set & 0xf) << 4) | (uint64_t)(dir & 0xf); }
static int bs_move_ok(uint64_t m) { return (m & 0xff00000000000000ULL) == BS_MOVE_TAG && ((m >> 4) & 0xf) <= BS_SET_ABBY && (m & 0xf) <= BS_DIR_RIGHT; }
static int bs_move_lv(uint64_t m) { return bs_clamp_lv((int)((m >> 8) & 0xf)); }
static int bs_move_set(uint64_t m) { return (int)((m >> 4) & 0xf); }
static int bs_move_dir(uint64_t m) { return (int)(m & 0xf); }

// ---- clips (re/bodyshield-1117.md "Anims": all from the decoded SP melee DC player-meatshield-* sets; residency checked against the MP paks + the
// SP-common paks the parry branch already loads: dc_data_patches.PARRY_SP_COMMON_PAKS)
typedef struct {
    const char *enter[3][2];       // [dir][att, vic]
    const char *hold[2], *hold_aim[2];
    const char *escape[2];
    const char *kill[2]; float kill_s;   // the finisher + its damage-character moment (DC window, 30 fps frames)
    const char *kill_abort[2];
    const char *dies[2];
    uint64_t kill_w;               // the credit weapon of the finisher kill
    const char *kill_word;         // the attacker's prompt
} bs_set_t;
static const bs_set_t BS_SETS[2] = {
    [BS_SET_ELLIE] = {
        {{"ellie-meatshield-enter-bkwd", "npc-meatshield-enter-bkwd"}, {"ellie-meatshield-enter-lt", "npc-meatshield-enter-lt"}, {"ellie-meatshield-enter-rt", "npc-meatshield-enter-rt"}},
        {"ellie-meatshield-struggle", "npc-meatshield-struggle"}, {"ellie-meatshield-struggle-aim", "npc-meatshield-struggle-aim"},
        {"ellie-meatshield-pistol-npc-escapes--ellie", "ellie-meatshield-pistol-npc-escapes--npc-f"},
        {"ellie-meatshield-knife-kill-loud-neck-slit--ellie", "ellie-meatshield-knife-kill-loud-neck-slit--npc-f"}, 29.0f / 30.0f,   // meatshield-ellie-neck-slit-finisher: damage at frame 29
        {"ellie-meatshield-knife-stealth-kill-neck-jab-early-1--ellie", "ellie-meatshield-knife-stealth-kill-neck-jab-early-1--npc-f"},
        {"ellie-meatshield-pistol-npc-dies-aiming--ellie", "ellie-meatshield-pistol-npc-dies-aiming--npc-f"},
        0, "STAB"},
    [BS_SET_ABBY] = {
        {{"abby-meatshield-enter-bkwd--abby", "abby-meatshield-enter-bkwd--npc-f"}, {"abby-meatshield-enter-lt--abby", "abby-meatshield-enter-lt--npc-f"}, {"abby-meatshield-enter-rt--abby", "abby-meatshield-enter-rt--npc-f"}},
        {"abby-meatshield-struggle--abby", "abby-meatshield-struggle--npc-f"}, {"abby-meatshield-struggle-aim--abby", "abby-meatshield-struggle-aim--npc-f"},
        {"abby-meatshield-pistol-npc-escapes--abby", "abby-meatshield-pistol-npc-escapes--npc-f"},
        {"abby-meatshield-stealth-kill-gun-grab--abby", "abby-meatshield-stealth-kill-gun-grab--npc-f"}, 167.0f / 30.0f,   // meatshield-abby-strangle-stealth-human-kill: damage at frame 167 (5.57 s)
        {"abby-meatshield-stealth-kill-gun-grab-abort--abby", "abby-meatshield-stealth-kill-gun-grab-abort--npc-f"},
        {"ellie-meatshield-pistol-npc-dies-aiming--ellie", "ellie-meatshield-pistol-npc-dies-aiming--npc-f"},   // (SP has no Abby shield death: Ellie's, as the weapon pins share hers)
        0, "CHOKE"},
};
static uint64_t bs_kill_weapon(int set) { return set == BS_SET_ELLIE ? fnv64("switchblade") : fnv64("abby-unarmed"); }


// ---- state of this client
static struct {
    int role;                      // 0 none, 1 attacker (we grabbed), 2 victim (we are held), 3 bystander (a grab plays here between others)
    uint32_t uid, slot;            // the grab; slot = the OTHER body (attacker: the victim, victim: the attacker)
    uint64_t move;
    int64_t t0;                    // GetTickCount64 of the grab START on this client (victim: minus the START skip)
    bs_att_t a; bs_vic_t v;
    int hurt;                      // attacker: damage taken since the last tick
    int64_t kill_at;               // rel ms of the finisher's damage moment (0 = none pending): damage on the attacker before it = the abort pair
    int killed;                    // victim: the finisher's death applied
    int ended;                     // the grab logic is over here (an END segment is set)
    int final;                     // the END can no longer change (a death: shield shot / finisher past its kill moment)
    int iron_checked;              // victim: Iron Grip II asked at the open moment
    int was_shield;                // victim: we were a shield in this grab (the friendly-fire tail)
    int64_t ff_until;              // victim: friendly fire allowed until (GetTickCount64): the tail after the shield
    int64_t msg_until; const char *msg;   // victim: "Too early" / "Too late" grey prompt
    uint8_t ob_op, ob_reason; int ob_sent; int64_t ob_t0;   // outbox: the last AIM / KILL / END, sent BS_RESEND_N times (bodyshield.h)
    int by_shield_ms;              // bystander: rel when the AIM came (0 = none)
} g_bs;
static int64_t g_bs_cool_until[T2R_MAX_PEERS];      // attacker: no re-grab of that slot before (it broke free)

static int bsh_off(void) {
    if (!T2R_BODYSHIELD) return 1;   // out of the public release (skills.h)
    static int v = -1; static uint64_t at; uint64_t n = GetTickCount64();
    if (v < 0 || n - at > 3000) { at = n; int o = GetFileAttributesA("t2r-no-bodyshield.txt") != INVALID_FILE_ATTRIBUTES; if (o != v) xlog("bodyshield: %s", o ? "OFF (t2r-no-bodyshield.txt)" : "on"); v = o; }
    return v;
}
static int bs_sides_swapped(void) { static int v = -1; if (v < 0) v = GetFileAttributesA("t2r-bs-swap-sides.txt") != INVALID_FILE_ATTRIBUTES; return v; }
static int64_t bsh_now(void) { return (int64_t)GetTickCount64(); }
static int bs_rel(void) { return (int)(bsh_now() - g_bs.t0); }

static void bs_send(uint8_t op, uint8_t reason, uint16_t kb, uint8_t to) {
    bs_wire w = {op, reason, kb, g_bs.uid};
    if (g_send_tramp) g_send_tramp(MSG_BS, (uint8_t *)&w, sizeof w, to);
}
// AIM / KILL / END to everyone, repeated at BS_RESEND_AT (every receiver takes a copy it already has as a no-op). A newer op replaces an
// older one still in the outbox (an END after a KILL: the END is what counts).
static void bs_post(uint8_t op, uint8_t reason) {
    g_bs.ob_op = op; g_bs.ob_reason = reason; g_bs.ob_t0 = bsh_now(); g_bs.ob_sent = 1;
    bs_send(op, reason, 0, 0xff);
}
static void bs_flush(void) {
    if (!g_bs.ob_op || !bs_resend_due(g_bs.ob_sent, (int)(bsh_now() - g_bs.ob_t0))) return;
    g_bs.ob_sent++;
    bs_send(g_bs.ob_op, g_bs.ob_reason, 0, 0xff);
    static int nl; if (LOGCAP(nl, 30)) xlog("bodyshield: u%08x op %u (reason %u) re-sent, copy %d", g_bs.uid, g_bs.ob_op, g_bs.ob_reason, g_bs.ob_sent);
}

// ---- input. Aim: the engine's answer, or the raw aim button (the carrier clip on our body may hide the engine's aim state) - RMB / pad LT.
static int bs_aim_held(void) {
    uint64_t none = 0, r = dc_call(fnv64("player-is-aiming?"), 0, &none);
    if (r != ~0ULL && (r & 0xff)) return 1;
    if (game_focused() && (GetAsyncKeyState(VK_RBUTTON) & 0x8000)) return 1;
    WORD b; BYTE lt, rt; SHORT x, y;
    return pad_state(&b, &lt, &rt, &x, &y) && lt > 100;
}
// F (keyboard melee) or the pad's melee command: rising edge, once per frame
static int bs_f_edge(void) {
    static uint64_t cf; static int cr, prev;
    if (cf && cf == g_frame) return cr;
    cf = g_frame;
    int d = (game_focused() && (GetAsyncKeyState('F') & 0x8000)) || pad_melee_cmd();
    cr = d && !prev; prev = d;
    return cr;
}

// ---- dev test driver (bstest, end of file): scripted input for a grab, so A/B runs need no synthetic keyboard / mouse
#ifndef T2R_RELEASE
static struct {
    int on;                        // this grab is a driver grab (attacker: our job; victim: the attacker's BSO_TEST armed us)
    int att;                       // attacker action: BT_A_*
    int aim_ms;                    // BST_A_AIM: shield time before the scripted stop aim (0 = keep aiming)
    int vic, vic_par;              // victim action BT_V_*, its parameter (mash presses / s)
    int iron, lv;                  // forced levels (-1 = the real skill)
    int64_t next_f;                // victim mash: next F press (rel ms)
    int e_done, k_done;            // one scripted E (victim) / kill press (attacker) per grab
} g_bst = {.iron = -1, .lv = -1};
enum { BST_A_HOLD, BST_A_KILL, BST_A_AIM };
enum { BST_V_NONE, BST_V_PASS, BST_V_EARLY, BST_V_MASH };
#endif
static int bs_lv_now(void) {
#ifndef T2R_RELEASE
    if (g_bst.on && g_bst.lv > 0) return g_bst.lv;
#endif
#if T2R_BODYSHIELD
    return skl(SK_BODYSHIELD);
#else
    return 0;                      // not in this build (skills.h T2R_BODYSHIELD)
#endif
}
static int bs_grip_now(void) {
#ifndef T2R_RELEASE
    if (g_bst.on && g_bst.iron >= 0) return g_bst.iron;
#endif
    return skl(SK_GRIP);
}
static int bs_in_aim(int rel) {
#ifndef T2R_RELEASE
    if (g_bst.on && g_bs.role == 1) {
        if (g_bst.att != BST_A_AIM || rel < 300) return 0;               // the shield goes up 0.3 s into the grab (inside the kill block, as a quick player)
        return !(g_bst.aim_ms > 0 && g_bs.a.st == BS_ST_SHIELD && rel - g_bs.a.shield_ms >= g_bst.aim_ms);
    }
#endif
    (void)rel; return bs_aim_held();
}
static int bs_in_kill(int rel) {
#ifndef T2R_RELEASE
    if (g_bst.on && g_bs.role == 1) {
        if (g_bst.att != BST_A_KILL || g_bst.k_done >= 2) return 0;
        if (g_bst.k_done == 0 && rel >= 650) { g_bst.k_done = 1; xlog("bstest: kill press inside the kill block (%d ms, block %d) - must be ignored", rel, g_bs.a.kb_ms); return 1; }   // test plan 3.1
        if (g_bst.k_done == 1 && rel >= g_bs.a.kb_ms + 200) { g_bst.k_done = 2; return 1; }
        return 0;
    }
#endif
    (void)rel; return mpn_e_edge();
}
static int bs_in_e(int rel) {
#ifndef T2R_RELEASE
    if (g_bst.on && g_bs.role == 2) {
        if (g_bst.e_done) return 0;
        int at = g_bst.vic == BST_V_PASS ? g_bs.v.open_ms + g_bs.v.t.qte_zone_ms / 2 : g_bst.vic == BST_V_EARLY ? g_bs.v.open_ms - 150 : -1;
        if (at >= 0 && rel >= at) { g_bst.e_done = 1; return 1; }
        return 0;
    }
#endif
    (void)rel; return mpn_e_edge();
}
static int bs_in_f(int rel) {
#ifndef T2R_RELEASE
    if (g_bst.on && g_bs.role == 2) {
        if (g_bst.vic != BST_V_MASH || g_bs.v.st != BS_ST_SHIELD || g_bst.vic_par <= 0) return 0;
        if (!g_bst.next_f) g_bst.next_f = rel;
        if (rel < g_bst.next_f) return 0;
        g_bst.next_f += 1000 / g_bst.vic_par;
        return 1;
    }
#endif
    (void)rel; return bs_f_edge();
}

// ---- chain (paired.c psync_bs_chain): the same table on every client
static int bs_chain_of(uint64_t move, uint64_t *att, uint64_t *vic, float *spd, float *cut, int max) {
    if (max < 3 || !bs_move_ok(move)) return 0;
    const bs_set_t *s = &BS_SETS[bs_move_set(move)];
    const char *c[3][2] = {{s->enter[bs_move_dir(move)][0], s->enter[bs_move_dir(move)][1]}, {s->hold[0], s->hold[1]}, {s->escape[0], s->escape[1]}};
    for (int i = 0; i < 3; i++) { att[i] = fnv64(c[i][0]); vic[i] = fnv64(c[i][1]); spd[i] = 1.0f; cut[i] = 0.0f; }
    return 3;
}
static int bs_mine(uint32_t uid) { return g_bs.role && g_bs.uid == uid && g_ps.role && g_ps.kind == PS_BODYSHIELD && g_ps.uid == uid; }
// the END pair into segment 2: switched at once (psync_bs_chain), or swapped in if the END already plays
static void bs_set_end(const char *a, const char *v, const char *why) {
    if (!g_ps.role || g_ps.kind != PS_BODYSHIELD || g_ps.nseg < 3 || g_bs.final) return;
    uint64_t na = fnv64(a), nv = fnv64(v);
    g_bs.ended = 1;
    if (g_ps.seg_att[2] == na && g_ps.seg_vic[2] == nv && (g_ps.rv_fin || g_ps.cur_seg == 2)) return;   // (the same END already set: both machines ended it at once)
    g_ps.seg_att[2] = na; g_ps.seg_vic[2] = nv;
    if (g_ps.cur_seg == 2) g_bs_end_swap = 1;
    else { g_ps.rv_fin = 1; g_ps.rv_fin_ms = psync_ms(); }
    xlog("bodyshield: u%08x END (%s): %s / %s (role %d, rel %d ms, %s)", g_ps.uid, why, a, v, g_bs.role, bs_rel(), g_ps.cur_seg == 2 ? "swapped in" : "switch now");
}
// fin_pending: a finisher was running and is broken (damage on the attacker before its kill moment) -> its abort pair
static void bs_end_for(int reason, int fin_pending) {
    const bs_set_t *s = &BS_SETS[bs_move_set(g_bs.move)];
    if (reason == BS_END_KILLED) bs_set_end(s->kill[0], s->kill[1], "finisher");
    else if (reason == BS_END_SHOTDEAD) { bs_set_end(s->dies[0], s->dies[1], "shield shot dead"); g_bs.final = 1; }
    else if (reason == BS_END_DAMAGE && fin_pending) bs_set_end(s->kill_abort[0], s->kill_abort[1], "finisher broken by damage");
    else bs_set_end(s->escape[0], s->escape[1], bs_end_name(reason));
}
static void bs_hold_aim(void) {
    if (!g_ps.role || g_ps.kind != PS_BODYSHIELD || g_ps.nseg < 3 || g_bs.ended) return;
    const bs_set_t *s = &BS_SETS[bs_move_set(g_bs.move)];
    if (g_ps.seg_att[1] == fnv64(s->hold_aim[0])) return;            // (a re-sent AIM: the aim loop already plays)
    g_ps.seg_att[1] = fnv64(s->hold_aim[0]); g_ps.seg_vic[1] = fnv64(s->hold_aim[1]);
    if (g_ps.cur_seg == 1) g_bs_hold_swap = 1;                    // (still in ENTER: the enter-over switch takes the aim loop)
    xlog("bodyshield: u%08x SHIELD up - hold loop -> %s / %s (role %d, rel %d ms)", g_ps.uid, s->hold_aim[0], s->hold_aim[1], g_bs.role, bs_rel());
}
static void bs_reset(const char *why) {
    if (g_bs.role) xlog("bodyshield: u%08x state cleared (%s), role %d", g_bs.uid, why, g_bs.role);
    int64_t ffu = g_bs.ff_until;
    memset(&g_bs, 0, sizeof g_bs);
    g_bs.ff_until = ffu;                                             // (the friendly-fire tail outlives the move by BS_FF_TAIL_MS)
}

// ---- psync callbacks
static void bs_ps_started(void) {
    if (g_ps.role == 3) { memset(&g_bs, 0, sizeof g_bs); g_bs.role = 3; g_bs.uid = g_ps.uid; g_bs.move = g_ps.move; g_bs.t0 = bsh_now(); }
    xlog("bodyshield: u%08x grab plays here (role %d, move %016llx)", g_ps.uid, g_ps.role, (unsigned long long)g_ps.move);
}
static int g_bs_last_end, g_bs_last_role, g_bs_last_rel;      // the grab that just ended (the dev driver's RESULT line)
static void bs_ps_ended(const char *why, int cancelled) {
    if (g_bs.role && g_bs.uid == g_ps.uid) { g_bs_last_role = g_bs.role; g_bs_last_rel = bs_rel(); g_bs_last_end = g_bs.role == 1 ? g_bs.a.end : g_bs.role == 2 ? g_bs.v.end : 0; }
#ifndef T2R_RELEASE
    if (g_bs.role == 2 && g_bst.on) { xlog("bstest: v grab over (end %s) - disarmed", bs_end_name(g_bs.v.end)); g_bst.on = 0; }   // (one BSO_TEST = one scripted grab)
#endif
    if (g_bs.role == 2 && g_bs.was_shield && !g_bs.ff_until) g_bs.ff_until = bsh_now() + BS_FF_TAIL_MS;
    xlog("bodyshield: u%08x move over (%s%s)", g_ps.uid, why, cancelled ? ", cut" : "");
    if (g_bs.role && g_bs.uid == g_ps.uid) bs_reset(why);
}
// we are the grabbed (psync START, role 2): the owner of our body decides
static int bs_victim_begin(uint32_t slot, uint32_t uid, uint64_t move, uint64_t skipf) {
    if (!bs_move_ok(move)) { xlog("bodyshield: START from slot %u with a bad move word %016llx - refused", slot, (unsigned long long)move); return 0; }
    if (g_downed || g_down_dying || g_exec_until || local_hp() <= 0.0f) { xlog("bodyshield: START from slot %u refused - we are downed / dying", slot); return 0; }
    memset(&g_bs, 0, sizeof g_bs);
    g_bs.role = 2; g_bs.uid = uid; g_bs.slot = slot; g_bs.move = move;
    g_bs.t0 = bsh_now() - (int64_t)(skipf * 1000ULL / 60ULL);         // our clock on the attacker's move time (the START skip = its one-way)
    bs_vic_begin(&g_bs.v, uid, bs_move_lv(move), bs_grip_now(), 0);
    bs_send(BSO_ACC, 0, (uint16_t)g_bs.v.t.kb_ms, (uint8_t)slot);
    xlog("bodyshield: u%08x GRABBED by slot %u (level %d, %s set, dir %d) - escape prompt at %d ms for %d ms (Iron Grip %d), kill block %d ms",
         uid, slot, bs_move_lv(move), bs_move_set(move) ? "Abby's" : "Ellie's", bs_move_dir(move), g_bs.v.open_ms, g_bs.v.t.qte_zone_ms, bs_grip_now(), g_bs.v.t.kb_ms);
    return 1;
}
static void bs_victim_cancel(const char *why) { if (g_bs.role == 2) bs_reset(why); }

// ---- the grab (attacker)
static int bs_slot_alive(uint32_t s) { return s < T2R_MAX_PEERS && !g_peer_downed[s] && !g_puppet_dead_here[s] && psync_puppet((int)s); }
// best target: a standing enemy within reach whose back / side faces us. dir out. -1 = none
static int bs_pick(int *dir_out) {
    float mb[16]; const float *ml = player_locator(mb);
    if (!ml || !ps_loc_ok(ml)) return -1;
    uint32_t self = psync_self();
    int best = -1; float bd = 1e9f;
    for (uint32_t s = 0; s < T2R_MAX_PEERS; s++) {
        if (s == self || is_teammate(s) || !bs_slot_alive(s) || psync_busy_slot(s) || bsh_now() < g_bs_cool_until[s]) continue;
        uint64_t h = psync_puppet((int)s); float pb[16];
        const float *pl = h ? puppet_locator(h, pb) : NULL;
        if (!pl || !ps_loc_ok(pl)) continue;
        float dx = ml[0] - pl[0], dz = ml[2] - pl[2], dy = ml[1] - pl[1], d2 = dx * dx + dz * dz;
        if (d2 > BS_REACH_M * BS_REACH_M || dy * dy > 0.6f * 0.6f) continue;
        const float *q = pl + 4;                                   // the victim's forward (as revive2013.c reads a locator)
        float fx = 2.0f * (q[0] * q[2] + q[3] * q[1]), fz = 1.0f - 2.0f * (q[0] * q[0] + q[1] * q[1]);
        float d = __builtin_sqrtf(d2); if (d < 0.05f) continue;
        float dot = (fx * dx + fz * dz) / d, cr = (fx * dz - fz * dx) / d;
        if (dot > 0.5f) continue;                                  // in front of them (inside +-60 deg): no grab (re/bodyshield-1117.md "Grab")
        int dir = dot < -0.5f ? BS_DIR_BACK : ((cr > 0.0f) != bs_sides_swapped() ? BS_DIR_LEFT : BS_DIR_RIGHT);
        if (d2 < bd) { bd = d2; best = (int)s; *dir_out = dir; }
    }
    return best;
}
static int bs_grab(uint32_t slot, int dir) {
    int lv = bs_lv_now(), set = own_female() ? BS_SET_ELLIE : BS_SET_ABBY;
    const bs_set_t *s = &BS_SETS[set];
    for (int k = 0; k < 2; k++) {                                  // every clip of the chain + its ends must be loaded here (else no grab: never a broken pair)
        const char *chk[] = {s->enter[dir][k], s->hold[k], s->hold_aim[k], s->escape[k], s->kill[k], s->kill_abort[k], s->dies[k]};
        for (unsigned i = 0; i < sizeof chk / sizeof chk[0]; i++)
            if (anim_len(SID_PLAYER, chk[i]) <= 0.0f) { static int nl; if (LOGCAP(nl, 6)) xlog("bodyshield: clip %s is not loaded in this build - no grab", chk[i]); return 0; }
    }
    uint64_t h = psync_puppet((int)slot); float pb[16], ap[7];
    const float *pl = h ? puppet_locator(h, pb) : NULL;
    if (!pl || !psync_solve_ap(h, fnv64(s->enter[dir][1]), pl, ap)) { xlog("bodyshield: slot %u - no ap (locator / clip align unreadable) - no grab", slot); return 0; }
    uint64_t mv = bs_move_word(lv, set, dir);
    if (!psync_start(PS_BODYSHIELD, slot, s->enter[dir][0], s->enter[dir][1], ap, -1.0f, PS_F_ANCHOR_VIC, 0xff, 0, mv)) { xlog("bodyshield: psync refused the grab on slot %u (see above)", slot); return 0; }
    memset(&g_bs, 0, sizeof g_bs);
    g_bs.role = 1; g_bs.uid = g_ps.uid; g_bs.slot = slot; g_bs.move = mv; g_bs.t0 = bsh_now();
    bs_att_begin(&g_bs.a, lv, sk_peer(slot, SK_GRIP));
    xlog("bodyshield: u%08x GRAB slot %u (level %d, %s set, dir %s, Iron Grip %d there) - kill block %d ms, hold max %d ms",
         g_bs.uid, slot, lv, set ? "Abby's" : "Ellie's", dir == BS_DIR_BACK ? "back" : dir == BS_DIR_LEFT ? "left" : "right", g_bs.a.iron, g_bs.a.kb_ms, g_bs.a.t.hold_max_ms);
    return 1;
}
static void bsh_att_frame(void) {
    if (!bs_mine(g_bs.uid)) return;
    if (match_substate() != 6) return;     // (at the match end our hp reads 0 - that is no damage; psync ends the pair itself)
    int rel = bs_rel();
    uint64_t hv = psync_puppet((int)g_bs.slot);
    int hurt = g_bs.hurt || g_downed || g_down_dying || local_hp() <= 0.0f; g_bs.hurt = 0;
    if (g_bs.kill_at) {                                               // the finisher runs: damage before its kill moment breaks it (its abort pair)
        if (rel >= g_bs.kill_at) { g_bs.kill_at = 0; g_bs.final = 1; xlog("bodyshield: u%08x finisher past its kill moment (%d ms)", g_bs.uid, rel); return; }
        if (!hurt) return;
        g_bs.a.st = BS_ST_END; g_bs.a.end = BS_END_DAMAGE;
        xlog("bodyshield: u%08x finisher BROKEN by damage at %d ms (kill moment was %lld)", g_bs.uid, rel, (long long)g_bs.kill_at);
        bs_post(BSO_END, BS_END_DAMAGE);
        bs_end_for(BS_END_DAMAGE, 1);
        g_bs.kill_at = 0;
        return;
    }
    if (g_bs.ended) return;
    int act = bs_att_step(&g_bs.a, rel, bs_in_aim(rel), bs_in_kill(rel), hurt);
    if (act == BS_A_SHIELD_ON) { bs_hold_aim(); bs_post(BSO_AIM, 1); }
    else if (act == BS_A_KILL) {
        const bs_set_t *s = &BS_SETS[bs_move_set(g_bs.move)];
        g_bs.kill_at = rel + (int64_t)(s->kill_s * 1000.0f);
        bs_post(BSO_KILL, BS_END_KILLED);
        bs_end_for(BS_END_KILLED, 0);
        xlog("bodyshield: u%08x %s at %d ms (kill moment %lld ms)", g_bs.uid, s->kill_word, rel, (long long)g_bs.kill_at);
        return;
    } else if (act == BS_A_RELEASE) {
        xlog("bodyshield: u%08x released at %d ms: %s", g_bs.uid, rel, bs_end_name(g_bs.a.end));
        bs_post(BSO_END, (uint8_t)g_bs.a.end);
        bs_end_for(g_bs.a.end, 0);
        g_bs_cool_until[g_bs.slot % T2R_MAX_PEERS] = bsh_now() + BS_REGRAB_COOL_MS;
        return;
    }
    // prompts on the victim's puppet: the kill block as a filling ring, then the finisher word; nothing while shielding
    if (hv && g_bs.a.st == BS_ST_HOLD) {
        if (rel < g_bs.a.kb_ms) world_prompt_grey_p(hv, "", 1, (float)rel / (float)g_bs.a.kb_ms);
        else world_prompt(hv, BS_SETS[bs_move_set(g_bs.move)].kill_word, -1.0f);
    }
}

// ---- held (victim)
static void bs_vic_die(void) {
    if (g_bs.killed) return;
    g_bs.killed = 1;
    uint64_t w = bs_kill_weapon(bs_move_set(g_bs.move));
    xlog("bodyshield: u%08x the finisher kills us (hp %.1f, credit slot %u, weapon %llx)", g_bs.uid, local_hp(), g_bs.slot, (unsigned long long)w);
    psync_keep_victim("bodyshield finisher");
    uint64_t a0[2] = {SID_PLAYER, 0}, z0 = 0;
    dc_call(fnv64("character-set-invincibility-cannot-die-threshold"), 2, a0);
    if (g_recv_tramp) { uint8_t hit[0x16] = {0}; *(uint64_t *)hit = w; *(float *)(hit + 0x10) = 250.0f; g_own_kill_hit = 1; g_recv_tramp(g_bs.slot, 3, hit, sizeof hit); g_own_kill_hit = 0; }
    trade_credit(g_bs.slot, w, "bodyshield finisher kill");
    if (local_hp() > 0) { uint64_t zero = 0; dc_call(fnv64("set-player-health"), 1, &zero); dc_call(fnv64("kill-player"), 0, &z0); }
}
static void bs_vic_escape(int reason) {
    xlog("bodyshield: u%08x ESCAPED at %d ms (%s)", g_bs.uid, bs_rel(), bs_end_name(reason));
    bs_post(BSO_END, (uint8_t)reason);
    bs_end_for(reason, 0);
    if (g_bs.was_shield) g_bs.ff_until = bsh_now() + BS_FF_TAIL_MS;
    if (reason == BS_END_QTE || reason == BS_END_IRON) msg_tag("ESCAPED!", 1.2f, 0);
    else if (reason == BS_END_TIMEOUT) xlog("bodyshield: u%08x no word from the attacker for %d ms past its hold - broke out ourselves (a lost END / AIM)", g_bs.uid, BS_LOST_MS);
}
static void bsh_vic_frame(void) {
    if (!bs_mine(g_bs.uid)) return;
    if (match_substate() != 6) return;     // (the match end is no shield death: hp reads 0 there)
    int rel = bs_rel();
    uint64_t ha = puppet_handle(g_bs.slot);
    if (g_bs.kill_at) { if (rel >= g_bs.kill_at) { g_bs.final = 1; bs_vic_die(); g_bs.kill_at = 0; } return; }
    if (g_bs.ended) return;
    if (g_bs.v.st == BS_ST_SHIELD && (local_hp() <= 0.0f || g_downed || g_down_dying)) {   // our own team's fire took us
        xlog("bodyshield: u%08x shot %s as a shield (hp %.1f)", g_bs.uid, g_downed ? "down" : "dead", local_hp());
        bs_post(BSO_END, BS_END_SHOTDEAD);
        bs_end_for(BS_END_SHOTDEAD, 0);
        psync_keep_victim("bodyshield shield death");
        g_bs.ff_until = bsh_now() + BS_FF_TAIL_MS;
        return;
    }
    if (g_bs.v.st == BS_ST_HOLD && !g_bs.iron_checked && rel >= g_bs.v.open_ms) {   // Iron Grip II: asked once, at the open moment (sk_iron_free spends this life's use)
        g_bs.iron_checked = 1;
#ifndef T2R_RELEASE
        if (g_bst.on && g_bst.iron >= 2) {   // (driver: forced Iron Grip II - sk_iron_free reads the real skill; the same once-per-life flag here)
            if (!g_sk_iron_used) { g_sk_iron_used = 1; g_bs.v.iron_free = 1; xlog("bstest: v forced Iron Grip II used for this life"); }
        } else
#endif
        if (bs_grip_now() >= 2 && sk_iron_free("body shield grab")) g_bs.v.iron_free = 1;
    }
    int r = BS_V_NONE;
    if (bs_in_e(rel)) r = bs_vic_press_e(&g_bs.v, rel);
    if (bs_in_f(rel)) bs_vic_press_f(&g_bs.v, rel);
    if (r == BS_V_NONE) r = bs_vic_tick(&g_bs.v, rel);
    if (r == BS_V_ESCAPE) { bs_vic_escape(g_bs.v.end); return; }
    if (r == BS_V_QTE_FAIL) {
        g_bs.msg = g_bs.v.qte == BS_Q_BURN ? "Too early" : "Too late"; g_bs.msg_until = bsh_now() + 600;
        xlog("bodyshield: u%08x escape prompt %s at %d ms (open %d, zone %d)", g_bs.uid, g_bs.v.qte == BS_Q_BURN ? "BURNED (pressed early)" : "missed", rel, g_bs.v.open_ms, g_bs.v.t.qte_zone_ms);
    }
    if (!ha) return;
    if (g_bs.v.st == BS_ST_SHIELD) world_prompt(ha, "BREAK FREE (F)", g_bs.v.m.fill > 0.99f ? 0.99f : g_bs.v.m.fill);
    else if (bs_vic_qte_open(&g_bs.v, rel)) world_prompt(ha, "ESCAPE!", -1.0f);
    else if (g_bs.msg && bsh_now() < g_bs.msg_until) world_prompt_grey(ha, g_bs.msg, 0);
}

// ---- net
#ifndef T2R_RELEASE
static void bst_vic_arm(uint32_t from, const bs_wire *w);
#endif
static int bs_recv(uint32_t slot, const uint8_t *buf, uint64_t len) {
    if (len < sizeof(bs_wire) || slot >= T2R_MAX_PEERS) return 1;
    bs_wire w; memcpy(&w, buf, sizeof w);
#ifndef T2R_RELEASE
    if (w.op == BSO_TEST) { bst_vic_arm(slot, &w); return 1; }
#else
    if (w.op == BSO_TEST) return 1;
#endif
    if (!g_ps.role || g_ps.kind != PS_BODYSHIELD || g_ps.uid != w.uid || ((int)slot != g_ps.att && (int)slot != g_ps.vic)) {
        static int nl; if (LOGCAP(nl, 20)) xlog("bodyshield: op %u from slot %u for u%08x - no such grab here (ours u%08x kind %d) - dropped", w.op, slot, w.uid, g_ps.uid, g_ps.kind);
        return 1;
    }
    if (g_bs.role == 0 || g_bs.uid != w.uid) { memset(&g_bs, 0, sizeof g_bs); g_bs.role = 3; g_bs.uid = w.uid; g_bs.move = g_ps.move; g_bs.t0 = bsh_now(); }   // (a bystander that missed the start callback)
    int from_att = (int)slot == g_ps.att, pend = g_bs.kill_at != 0;
    switch (w.op) {
    case BSO_ACC:
        if (g_bs.role == 1 && !from_att) { bs_att_acc(&g_bs.a, w.kb_ms); xlog("bodyshield: u%08x ACC from the victim: its kill block %u ms -> ours %d ms", w.uid, w.kb_ms, g_bs.a.kb_ms); }
        break;
    case BSO_AIM:
        if (!from_att || g_bs.ended) break;
        if (g_bs.role == 3 && !g_bs.by_shield_ms) g_bs.by_shield_ms = bs_rel() ? bs_rel() : 1;
        if (g_bs.role == 2 && g_bs.v.st == BS_ST_HOLD) { bs_vic_shield(&g_bs.v, bs_rel()); g_bs.was_shield = 1; xlog("bodyshield: u%08x we are a SHIELD now - our team can hit us, mash F (free in %d ms at the cap, %d ms without a press)", w.uid, g_bs.v.t.mash_fast_ms, g_bs.v.t.mash_idle_ms); }
        bs_hold_aim();
        break;
    case BSO_KILL:
        if (!from_att || g_bs.final || pend || g_bs.killed) break;     // (pend: a re-sent KILL - the finisher already runs here)
        if (g_bs.role == 2) {
            if (g_bs.ended || !bs_vic_kill_ok(&g_bs.v, bs_rel())) {        // our escape stands: tell everyone again
                xlog("bodyshield: u%08x KILL refused at %d ms (state %d, QTE %d, our kill block %d) - escape stands", w.uid, bs_rel(), g_bs.v.st, g_bs.v.qte, g_bs.v.t.kb_ms);
                if (g_bs.v.end && !(g_bs.ob_op == BSO_END && g_bs.ob_sent < BS_RESEND_N)) bs_post(BSO_END, (uint8_t)g_bs.v.end);   // (not while our END copies still go out)
                break;
            }
            g_bs.v.st = BS_ST_KILL;
        }
        g_bs.kill_at = bs_rel() + (int64_t)(BS_SETS[bs_move_set(g_bs.move)].kill_s * 1000.0f);
        bs_end_for(BS_END_KILLED, 0);
        break;
    case BSO_END:
        if (w.reason > BS_END_GONE || g_bs.final) break;
        if (g_bs.role == 1) {                                         // the victim broke free (its call) / was shot dead as a shield
            if (from_att) break;
            xlog("bodyshield: u%08x the victim ended it: %s", w.uid, bs_end_name(w.reason));
            g_bs.a.st = BS_ST_END; g_bs.a.end = w.reason; g_bs.kill_at = 0;
            if (bs_end_escapes(w.reason)) g_bs_cool_until[slot] = bsh_now() + BS_REGRAB_COOL_MS;
        } else if (g_bs.role == 2) {                                  // the attacker let go (stop aim / damage / timeout / a broken finisher)
            if (!from_att || g_bs.killed || (g_bs.ended && !pend)) break;    // (our own escape / death already stands)
            g_bs.v.st = BS_ST_END; g_bs.v.end = w.reason; g_bs.kill_at = 0;
            if (g_bs.was_shield) g_bs.ff_until = bsh_now() + BS_FF_TAIL_MS;
            if (w.reason == BS_END_STOPAIM) msg_tag("BROKE FREE!", 1.2f, 0);
        } else g_bs.kill_at = 0;
        bs_end_for(w.reason, pend && w.reason == BS_END_DAMAGE);
        break;
    }
    return 1;
}

// ---- hooks the rest of the ext calls
// the friendly-fire drop (t2r-ext.c recv_hook_body): a teammate's hit on us passes while we are a shield (+ BS_FF_TAIL_MS)
static int bs_ff_allow(uint32_t slot) {
    if (slot >= T2R_MAX_PEERS || (g_bs.role == 2 && slot == g_bs.slot)) return 0;
    int live = g_bs.role == 2 && g_bs.v.st == BS_ST_SHIELD && bs_mine(g_bs.uid);
    int tail = g_bs.ff_until && bsh_now() < g_bs.ff_until;
    if (live || tail) { static int nl; if (LOGCAP(nl, 40)) xlog("bodyshield: friendly fire from slot %u passes - we are %s", slot, live ? "a shield" : "a shield that just ended (tail)"); }
    return live || tail;
}
// a damage message on us (after the friendly-fire drop): the shielder lets go (bsh_att_frame books it)
static void bs_on_hit(uint32_t slot, float dmg) {
    if (g_bs.role != 1 || !(dmg > 0.0f) || slot == g_bs.slot) return;
    g_bs.hurt = 1;
    xlog("bodyshield: u%08x shielder hit by slot %u (%.1f) - lets go", g_bs.uid, slot, dmg);
}
// bystander: follows the two players' messages. If every copy of the END was lost, the pair would loop the hold here forever: past the
// longest either side can last (hold max, or the shield's wiggle time) + 2 x BS_LOST_MS (each side's own lost-message cap) it plays the escape.
static void bsh_by_frame(void) {
    int rel = bs_rel();
    if (g_bs.kill_at) { if (rel >= g_bs.kill_at) { g_bs.kill_at = 0; g_bs.final = 1; } return; }
    if (g_bs.ended || !bs_mine(g_bs.uid)) return;
    bs_tier_t t = bs_tier(bs_move_lv(g_bs.move), 0);
    int cap = (g_bs.by_shield_ms ? g_bs.by_shield_ms + t.mash_idle_ms : t.hold_max_ms) + 2 * BS_LOST_MS;
    if (rel < cap) return;
    xlog("bodyshield: u%08x no END heard in %d ms (%s) - the escape plays here", g_bs.uid, rel, g_bs.by_shield_ms ? "shield" : "hold");
    bs_end_for(BS_END_TIMEOUT, 0);
}
#ifndef T2R_RELEASE
static void bst_tick(void);
#endif
static void bs_tick(void) {
#ifndef T2R_RELEASE
    bst_tick();
#endif
    if (g_bs.ff_until && bsh_now() >= g_bs.ff_until) g_bs.ff_until = 0;
    if (g_bs.role == 1 || g_bs.role == 2) bs_flush();
    if (g_bs.role == 1) { bsh_att_frame(); return; }
    if (g_bs.role == 2) { bsh_vic_frame(); return; }
    if (g_bs.role == 3) { bsh_by_frame(); return; }
    if (bsh_off() || !bs_lv_now() || match_substate() != 6) return;
    if (psync_active() || g_downed || g_down_dying || g_exec_until || local_hp() <= 0.0f || !actor_can_act()) return;
    float mb[16]; const float *ml = player_locator(mb);
    if (!ml || box_claims_press(ml)) return;
    int dir = BS_DIR_BACK, s = bs_pick(&dir);
    if (s < 0) return;
    uint64_t h = psync_puppet(s);
    if (h) world_prompt(h, "GRAB", -1.0f);
    if (mpn_e_edge()) bs_grab((uint32_t)s, dir);
}

// ================================================================ DEV TEST DRIVER (#ifndef T2R_RELEASE) - re/bodyshield-1117.md "Test driver"
// No synthetic keyboard / mouse: the driver feeds its script into the grab's own input reads (bs_in_*), everything else is the real path
// (bs_pick / bs_grab / psync START / MSG_BS / the victim's own judge and death).
//   ATTACKER (A): t2r-bs-test.txt next to the exe, read once then deleted. One job per line ('#' = comment):
//        <back|left|right> <hold|kill|aim[=<ms>]> [vic=<pass|early|none|mash=<hz>>] [iron=<0..2>] [lv=<1..3>] [wait=<s>]
//      aim=<ms>: the shield stays up that long, then the scripted stop aim (no =: aim until the grab ends). lv: our BODYSHIELD level (default 1).
//      Per job: wait for a live standing enemy, arm it (BSO_TEST: its script + iron), teleport 1.0 m to its back / left / right facing it,
//      check that bs_pick picks the same side, grab, wait for the end, log RESULT, wait (default 6 s), next job.
//   VICTIM (B): t2r-bs-test-vic.txt next to the exe (polled every 2 s). Without it B ignores BSO_TEST and plays every grab with its real input.
//   Log lines: "bstest: #k ..." on A, "bstest: v ..." on B; the grab's own "bodyshield:" lines carry the uid.
#ifndef T2R_RELEASE
#define BST_MAXJOB 32
typedef struct { int dir, att, aim_ms, vic, vic_par, iron, lv, wait_s; char text[96]; } bst_job;
static struct { int n, cur, st, slot, tries; int64_t at; uint32_t uid; bst_job job[BST_MAXJOB]; } g_bstr;
enum { BSTS_IDLE, BSTS_PICK, BSTS_TP, BSTS_GRAB, BSTS_RUN, BSTS_TAIL };
static int g_bst_vic_ok;            // B: consent file present
static int64_t g_bst_vic_poll;

static void bst_remove(const char *name) { char pa[MAX_PATH]; GetModuleFileNameA(NULL, pa, MAX_PATH); char *sa = strrchr(pa, 92); if (sa) { strcpy(sa + 1, name); remove(pa); } }
static void bst_load(void) {
    static int64_t poll; if (bsh_now() - poll < 2000) return; poll = bsh_now();
    FILE *f = exe_side_open("t2r-bs-test.txt", "r");
    if (!f) return;
    char line[160]; int n = 0;
    while (n < BST_MAXJOB && fgets(line, sizeof line, f)) {
        char *h = strchr(line, '#'); if (h) *h = 0;
        char *e = line + strlen(line); while (e > line && (e[-1] == '\n' || e[-1] == '\r' || e[-1] == ' ')) *--e = 0;
        if (!line[0]) continue;
        bst_job j = {.dir = -1, .att = BST_A_HOLD, .vic = BST_V_NONE, .iron = -1, .lv = 1, .wait_s = 6};
        snprintf(j.text, sizeof j.text, "%s", line);
        for (char *t = strtok(line, " \t"); t; t = strtok(NULL, " \t")) {
            if (!strcmp(t, "back")) j.dir = BS_DIR_BACK; else if (!strcmp(t, "left")) j.dir = BS_DIR_LEFT; else if (!strcmp(t, "right")) j.dir = BS_DIR_RIGHT;
            else if (!strcmp(t, "hold")) j.att = BST_A_HOLD; else if (!strcmp(t, "kill")) j.att = BST_A_KILL;
            else if (!strncmp(t, "aim", 3)) { j.att = BST_A_AIM; j.aim_ms = t[3] == '=' ? atoi(t + 4) : 0; }
            else if (!strcmp(t, "vic=pass")) j.vic = BST_V_PASS; else if (!strcmp(t, "vic=early")) j.vic = BST_V_EARLY; else if (!strcmp(t, "vic=none")) j.vic = BST_V_NONE;
            else if (!strncmp(t, "vic=mash=", 9)) { j.vic = BST_V_MASH; j.vic_par = atoi(t + 9); }
            else if (!strncmp(t, "iron=", 5)) j.iron = atoi(t + 5);
            else if (!strncmp(t, "lv=", 3)) j.lv = bs_clamp_lv(atoi(t + 3));
            else if (!strncmp(t, "wait=", 5)) j.wait_s = atoi(t + 5);
            else xlog("bstest: unknown token '%s' in '%s' - ignored", t, j.text);
        }
        if (j.dir < 0) { xlog("bstest: job '%s' has no side (back / left / right) - skipped", j.text); continue; }
        g_bstr.job[n++] = j;
    }
    fclose(f); bst_remove("t2r-bs-test.txt");
    g_bstr.n = n; g_bstr.cur = 0; g_bstr.st = n ? BSTS_PICK : BSTS_IDLE; g_bstr.at = bsh_now();
    xlog("bstest: %d job(s) loaded from t2r-bs-test.txt (file deleted)", n);
}
// B: consent + the attacker's arm message
static void bst_vic_poll(void) {
    if (bsh_now() - g_bst_vic_poll < 2000) return;
    g_bst_vic_poll = bsh_now();
    int was = g_bst_vic_ok; g_bst_vic_ok = GetFileAttributesA("t2r-bs-test-vic.txt") != INVALID_FILE_ATTRIBUTES;
    if (was != g_bst_vic_ok) xlog("bstest: v victim mode %s", g_bst_vic_ok ? "ON (t2r-bs-test-vic.txt: the attacker's BSO_TEST scripts our next grab)" : "off");
}
static void bst_vic_arm(uint32_t from, const bs_wire *w) {
    if (!g_bst_vic_ok) { static int nl; if (LOGCAP(nl, 10)) xlog("bstest: v BSO_TEST from slot %u ignored - no t2r-bs-test-vic.txt here", from); return; }
    memset(&g_bst, 0, sizeof g_bst);
    g_bst.on = 1; g_bst.vic = w->reason; g_bst.vic_par = w->kb_ms & 0xff; g_bst.iron = (w->kb_ms >> 8) & 0xf; g_bst.lv = -1;
    if (g_bst.iron > 2) g_bst.iron = -1;
    xlog("bstest: v armed by slot %u: victim %s (par %d), Iron Grip %d", from, g_bst.vic == BST_V_PASS ? "pass" : g_bst.vic == BST_V_EARLY ? "early" : g_bst.vic == BST_V_MASH ? "mash" : "none", g_bst.vic_par, g_bst.iron);
}
static int bst_enemy(void) {
    uint32_t self = psync_self();
    for (uint32_t s = 0; s < T2R_MAX_PEERS; s++) if (s != self && !is_teammate(s) && bs_slot_alive(s) && !psync_busy_slot(s)) return (int)s;
    return -1;
}
static void bst_tick(void) {
    bst_vic_poll();
    bst_load();
    if (!g_bstr.n) return;
    bst_job *j = &g_bstr.job[g_bstr.cur];
    int64_t now = bsh_now();
    switch (g_bstr.st) {
    case BSTS_PICK: {
        if (now - g_bstr.at < 1000) return;
        if (match_substate() != 6 || g_downed || local_hp() <= 0.0f || psync_active()) { g_bstr.at = now; return; }
        int s = bst_enemy();
        if (s < 0) { if (++g_bstr.tries % 30 == 1) xlog("bstest: #%d waiting for a live standing enemy", g_bstr.cur + 1); g_bstr.at = now; return; }
        g_bstr.slot = s; g_bstr.tries = 0;
        g_bs_cool_until[s] = 0;                                               // (the driver's jobs run back to back: no re-grab cooldown)
        bs_wire w = {BSO_TEST, (uint8_t)j->vic, (uint16_t)((j->vic_par & 0xff) | ((j->iron < 0 ? 0xf : j->iron) << 8)), 0};
        if (g_send_tramp) g_send_tramp(MSG_BS, (uint8_t *)&w, sizeof w, (uint8_t)s);
        xlog("bstest: #%d begin '%s' on slot %u", g_bstr.cur + 1, j->text, (unsigned)s);
        g_bstr.st = BSTS_TP; g_bstr.at = now;
        return; }
    case BSTS_TP: {
        if (now - g_bstr.at < 500) return;                                     // (the arm message reaches B first)
        uint64_t h = psync_puppet(g_bstr.slot); float pb[16];
        const float *pl = h ? puppet_locator(h, pb) : NULL;
        if (!pl || !ps_loc_ok(pl)) { xlog("bstest: #%d no locator for slot %d - job skipped", g_bstr.cur + 1, g_bstr.slot); g_bstr.st = BSTS_TAIL; g_bstr.at = now; return; }
        const float *q = pl + 4;
        float fx = 2.0f * (q[0] * q[2] + q[3] * q[1]), fz = 1.0f - 2.0f * (q[0] * q[0] + q[1] * q[1]);   // victim forward (bs_pick's read)
        float rx = fz, rz = -fx;                                                                           // a side vector; which one is "left" is what bs_pick decides
        float ox = j->dir == BS_DIR_BACK ? -fx : j->dir == BS_DIR_LEFT ? -rx : rx, oz = j->dir == BS_DIR_BACK ? -fz : j->dir == BS_DIR_LEFT ? -rz : rz;
        float pos[3] = {pl[0] + ox * 1.0f, pl[1], pl[2] + oz * 1.0f};
        float yaw = __builtin_atan2f(-ox, -oz);                                // face the victim
        float rot[4] = {0.0f, __builtin_sinf(yaw * 0.5f), 0.0f, __builtin_cosf(yaw * 0.5f)};
        teleport_player_to(pos, rot);
        xlog("bstest: #%d teleported to the %s of slot %d (1.0 m)", g_bstr.cur + 1, j->dir == BS_DIR_BACK ? "back" : j->dir == BS_DIR_LEFT ? "left" : "right", g_bstr.slot);
        g_bstr.st = BSTS_GRAB; g_bstr.at = now;
        return; }
    case BSTS_GRAB: {
        if (now - g_bstr.at < 700) return;                                     // (the teleport lands, the puppet's locator settles)
        int pdir = -1, ps = bs_pick(&pdir), dir = j->dir;
        if (ps != g_bstr.slot || pdir != j->dir) {
            xlog("bstest: #%d bs_pick says slot %d side %d (wanted slot %d side %d)%s", g_bstr.cur + 1, ps, pdir, g_bstr.slot, j->dir,
                 ps == g_bstr.slot && (pdir == BS_DIR_LEFT || pdir == BS_DIR_RIGHT) && (j->dir == BS_DIR_LEFT || j->dir == BS_DIR_RIGHT) ? " - left / right flipped vs the teleport side: grabbing with bs_pick's side" : "");
            if (ps == g_bstr.slot && pdir >= 0) dir = pdir;
        } else xlog("bstest: #%d bs_pick agrees: slot %d, side %d (GRAB prompt would show)", g_bstr.cur + 1, ps, pdir);
        memset(&g_bst, 0, sizeof g_bst);
        g_bst.on = 1; g_bst.att = j->att; g_bst.aim_ms = j->aim_ms; g_bst.lv = j->lv; g_bst.iron = -1;
        if (!bs_grab((uint32_t)g_bstr.slot, dir)) { xlog("bstest: #%d RESULT NOT STARTED (bs_grab refused, see above)", g_bstr.cur + 1); g_bst.on = 0; g_bstr.st = BSTS_TAIL; g_bstr.at = now; return; }
        g_bstr.uid = g_bs.uid;
        xlog("bstest: #%d STARTED u%08x", g_bstr.cur + 1, g_bstr.uid);
        g_bstr.st = BSTS_RUN; g_bstr.at = now;
        return; }
    case BSTS_RUN:
        if (g_bs.role == 1 && g_bs.uid == g_bstr.uid) { if (now - g_bstr.at > 40000) { xlog("bstest: #%d still running after 40 s - aborted", g_bstr.cur + 1); psync_abort("bstest timeout", 1); } return; }
        xlog("bstest: #%d RESULT u%08x end %s at %d ms ('%s')", g_bstr.cur + 1, g_bstr.uid, bs_end_name(g_bs_last_end), g_bs_last_rel, j->text);
        g_bst.on = 0; g_bstr.st = BSTS_TAIL; g_bstr.at = now;
        return;
    case BSTS_TAIL:
        if (now - g_bstr.at < (int64_t)j->wait_s * 1000) return;
        if (++g_bstr.cur >= g_bstr.n) { xlog("bstest: all %d job(s) done", g_bstr.n); g_bstr.n = 0; g_bstr.st = BSTS_IDLE; return; }
        g_bstr.st = BSTS_PICK; g_bstr.at = now;
        return;
    }
}
#endif
