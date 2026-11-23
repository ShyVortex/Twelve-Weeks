static int padinj_nofocus_on(void);   // padinject.c
static int mdg47_focus_off(void) { static int off = -1; static uint64_t at; uint64_t n = GetTickCount64(); if (off < 0 || n - at > 2000) { at = n; off = GetFileAttributesA("t2r-dodge-focus-ps47-old.txt") != INVALID_FILE_ATTRIBUTES; } return off; }
// melee_dodge.c - a melee dodge for the victim of a swing (the small stagger stays, BUT there is a dodge system - only when you are about to get meleed,
// so it is no movement tech; balanced so you cannot dodge every hit; it uses SP's dodge system; the attacker's hit anim is extended a little for a fair window;
// later: it balances upgraded one-shot melee, a dodged blow carries the attacker on and leaves him open, the dodger is limited too).
// Included after melee_feel.c in t2r-ext.c. Log prefix "dodge:". Opt-out: t2r-no-melee-dodge.txt next to the exe (re-read every 2 s).
//
// What the engine has (SP data and sandbox logs; none of it run in MP here): the dodge is the joypad command "evade" (player-set-gameplay-options
// gates it with joypad-disable-commands(evade) when allow-dodge is false); a press makes the melee system pick a player move of the set player-open-dodges
// (player-phantom-dodge, then player-dodge-<dir>-...-open-relax, animations ellie-1h-dodge-open^run-back--left-ft ...), macro melee-player-open-dodge, plus
// the dodge grunt / bag foley events. The streamed body shows it on every peer (dodge poses are already the owner's real ones).
//
// Design
//  * ATTACKER announces each free swing it starts (MSG_DODGE_SWING 0x97 [u8 kind: 1 = an upgraded one-shot is armed]). Its swing clip also plays at
//    MD_EXT_SPEED for its first MD_EXT_MS (the windup is ~100 ms longer: the fair timeframe); whiff recovery (x1.8) waits until that is restored.
//  * VICTIM gate: the "evade" command is disabled EVERY frame (the frame-scoped joypad-disable-commands) except while a window is open: an enemy announced a
//    swing < MD_WIN_MS ago (MD_WIN2_MS if the previous dodge was < MD_STREAK_MS ago), is within MD_REACH, faces us within ~40 deg, on our level, we are not
//    aiming / swinging / staggered / downed / in a paired move, no cooldown (MD_COOLDOWN_MS from the last dodge) and this announced swing was not dodged yet.
//    So the button does nothing otherwise (no movement tech). While a window is open the prompt "Dodge" (world_prompt over the attacker, the engine's own
//    interactable style, text fallback) shows.
//  * A press in the window starts the dodge: i-frames for MD_IFRAME_MS from the press. If the engine's own dodge move (MD_MOVES) is not seen within
//    MD_ENGINE_WAIT_MS, a fallback sidestep (0.9 m, rays for walls / ground, 0.2 s eased set_obj_loc, a dodge gesture if its clip is loaded) plays instead.
//  * HIT RULING (the victim decides, as for every hit): recv_hit_hook drops a melee blow that arrives inside the i-frames (mdg_hit_dodged) and a paired
//    one-shot / contextual down START inside them is refused with ABORT reason PS_AB_DODGED (mdg_pair_dodged, paired.c). A later blow of the combo lands.
//    The victim then sends MSG_DODGE_RES 0x98; the attacker (or the PS ABORT) plays the miss: momentum (a short collision-checked carry forward), a stumble
//    gesture on its body (streamed to everyone), its swing clip tail at MD_MISS_SPEED, and no fire / aim / melee for MD_ATK_RECOVER_MS (the stagger's lock).
//    The one-shot of a refused upgraded pair is given back; no plain-down fallback.
//  * DODGER limits: no aim / fire / throw for MD_GUN_LOCK_MS after the press, melee allowed again from MD_MELEE_OK_MS (melee is the reward), the same
//    joypad-disable-all-commands-except as the stagger (which wins when both want the body).
#include "melee_dodge_moves.h"
#include "melee_dodge_rm.h"   // authored root motion of the dodge clips (gen_dodge_rootmotion.py): the combat dodge step follows it
static void dc_arm(uint32_t slot);
static int mex_window_end(uint32_t s, uint64_t *end);                 // melee_exchange.c: 0 = no exchange, 1 = *end is the window end on the shared clock, 2 = closed
static int mex_wcls(void);                        // melee_exchange.c
static int mex_tc_raw(int wcls);                  // melee_exchange.c: the exchange's authored contact tune
static int mex_swing_msg(uint32_t slot, const uint8_t *buf, uint64_t len);   // melee_exchange.c: 1 = the swing time is the exchange's (only class / hand taken)
static void mex_note_dodge(uint32_t slot, uint64_t now);               // melee_exchange.c: our dodge press = the DODGED verdict
static void mex_note_early_press(void);                               // melee_exchange.c: a dodge press before the window burns it
// the whooshes natively used for melee weapon swinging are used for whiffs: a dodged swing plays the
// swung weapon's own SP swing whoosh on the swinger's wrist - on the swinger's screen (our body) and the dodger's (the swinger's puppet) - louder than
// the clip's cloth swish, so the miss reads. Fists: sfx-unarmed-finisher-whoosh. The weapon banks are SP_MELEE_BANKS (dc_data_patches.py: bat / hammer
// first, the others later - an older features build has only the bat, hammer, knife and fist ones; the rest fall back to the fist
// whoosh). t2r-no-whiff-whoosh.txt = off.
#ifndef T2R_MELEE_BANKS_1026
#define T2R_MELEE_BANKS_1026 1      // 1 once the features DLL carries the full SP_MELEE_BANKS (t2r-whiff-new-banks.txt forces it)
#endif
static int g_mdg_whoosh_kick;   // The cue being fired is a kick row (melee_duel.c MDUA_SWISH)
static int ex_t2m_label_wave(int label, float gain, uint64_t ent, const char *tag, const char *pair);   // t2r-ext.c
static int ex_t2m_label_wave_at(int label, float gain, const float *wpos, float rnear, float rfar, const char *tag);   // t2r-ext.c
static void mdg_whiff_whoosh(uint64_t ent, uint64_t w, int slot) {
    static uint64_t last[T2R_MAX_PEERS + 1]; static int nl;
    int k = slot >= 0 && slot < T2R_MAX_PEERS ? slot : T2R_MAX_PEERS;
    uint64_t now = GetTickCount64();
    if (!ent || ent == ~0ULL || GetFileAttributesA("t2r-no-whiff-whoosh.txt") != INVALID_FILE_ATTRIBUTES) return;
    if (now - last[k] < 400) { static int nd; if (LOGCAP(nd, 200)) xlog("dodge: whiff whoosh on %s dropped by the 400 ms limiter (%llu ms since the last)", slot < 0 ? "our swing" : "the swinger's puppet", (unsigned long long)(now - last[k])); return; }   // logged (clip audio: ~half the swings had no whoosh)
    last[k] = now;
    static const struct { const char *wpn, *ev; int base; } WH[] = {
        {"baseball-bat", "sfx-weapon-baseball-bat-whoosh", 1}, {"hammer-modern", "sfx-weapon-hammer-whoosh", 1}, {"hammer-scar", "sfx-weapon-hammer-whoosh", 1},
        {"two-by-four", "sfx-weapon-2x4-whoosh", 0}, {"crowbar", "sfx-weapon-crowbar-one-hand-whoosh", 0}, {"lead-pipe", "sfx-weapon-lead-pipe-whoosh", 0},
        {"short-pipe", "sfx-weapon-lead-pipe-whoosh", 0}, {"pipe-wrench", "sfx-weapon-pipe-wrench-whoosh", 0}, {"club-1h-police", "sfx-weapon-club-1h-police-whoosh", 0},
        {"club-1h-scar", "sfx-weapon-club-1h-whoosh", 0}, {"club-2h-scar", "sfx-weapon-club-2h-whoosh", 0}, {"tomahawk", "sfx-weapon-hatchet-whoosh", 0},
        {"hatchet-modern", "sfx-weapon-hatchet-whoosh", 0}, {"hatchet", "sfx-weapon-hatchet-whoosh", 0}, {"fireman-axe", "sfx-weapon-two-hand-axe-whoosh", 0}, {"machete", "sfx-weapon-machete-whoosh", 0},
        {"machete-scar", "sfx-weapon-machete-whoosh", 0}, {"sledgehammer", "sfx-weapon-club-2h-whoosh", 0}, {"pickaxe", "sfx-weapon-pickaxe-whoosh", 0}};
    const char *nm = NULL, *ev = "sfx-unarmed-finisher-whoosh";
    if (w && w != ~0ULL && knife_weapon_id(w)) ev = "sfx-weapon-switchblade-whoosh";
    else if (w && w != ~0ULL && (melee_class_of(base_weapon(w), &nm) >= 0 || melee_class_of(w, &nm) >= 0) && nm) {
        int newbanks = T2R_MELEE_BANKS_1026 || GetFileAttributesA("t2r-whiff-new-banks.txt") != INVALID_FILE_ATTRIBUTES;
        for (size_t i = 0; i < sizeof WH / sizeof *WH; i++) if (!strcmp(WH[i].wpn, nm)) { if (WH[i].base || newbanks) ev = WH[i].ev; break; }
    }
    // (clip audio: the engine's whoosh event returned a handle on every call but 34 of 72 calls were silent on both screens): fists / kick / knife
    // play TLOU2's own whoosh waves through the ext PCM mixer (t2melee.pcm EXS_T2_*: the route the punches / executions take), positional on the body.
    // Weapons with an SP whoosh bank (bat, hammer, ...) keep the engine event. t2r-whoosh-engine.txt = the engine events for everything.
    { static int eng = -1; static uint64_t echk; if (eng < 0 || now - echk > 3000) { echk = now; eng = GetFileAttributesA("t2r-whoosh-engine.txt") != INVALID_FILE_ATTRIBUTES; }
      int lab = !strcmp(ev, "sfx-weapon-switchblade-whoosh") ? EXS_T2_KNIFE_WHOOSH : !strcmp(ev, "sfx-unarmed-finisher-whoosh") ? (g_mdg_whoosh_kick ? EXS_T2_KICK_WHOOSH : EXS_T2_FIST_WHOOSH) : 0;
      if (!eng && lab) {
          // the body's position with a 3 m full-gain range (TUNING; dev23: the body-attached 3D path lost ~13 dB at 1-2 m); the fist mix is quieter than the blade's: x1.25
          float lb[16]; const float *l = ent == SID_PLAYER ? uc4_my_loc(lb) : puppet_locator(ent, lb); float wp[3] = {l ? l[0] : 0.0f, l ? l[1] + 1.2f : 0.0f, l ? l[2] : 0.0f};
          int ok = l && __builtin_isfinite(l[0]) ? ex_t2m_label_wave_at(lab, lab == EXS_T2_KNIFE_WHOOSH ? 1.0f : 1.25f, wp, 3.0f, 14.0f, "swing whoosh") : ex_t2m_label_wave(lab, 1.0f, ent, "swing whoosh", NULL); if (LOGCAP(nl, 400)) xlog("dodge: whiff whoosh PCM %s on %s -> %d", lab == EXS_T2_KNIFE_WHOOSH ? "switchblade" : lab == EXS_T2_KICK_WHOOSH ? "kick" : "fist (air + cotton)", slot < 0 ? "our swing" : "the swinger's puppet", ok); return; } }
    uint64_t a[5] = {fnv64(ev), ent, fnv64("r_wrist"), 0, 0};
    uint64_t r = dc_call(fnv64("play-sound-at-joint"), 5, a);
    if (LOGCAP(nl, 400)) xlog("dodge: whiff whoosh %s (%s) on %s -> %llx", ev, nm ? nm : "fists / knife", slot < 0 ? "our swing" : "the swinger's puppet", (unsigned long long)r);
}
// A clear SP-style cue when a dodge succeeds: the dodged swing's whoosh above plays at the swinger's wrist; this adds SP's dodge foley on the DODGER's body on both screens
// (re/sp-abby-fist-sounds-1026.md: SP's dodge = sfx-backpack-abby-bp-dodge-soft / -hard + the dodge grunt, ~150 ms after the clip start). The event is in fol-backpack-abby, a bank every MP level
// carries (dc_data_patches.py SP_BAG_FOLEY_BANKS); the log line shows what play-sound-at-joint returned (~0 = engine refused: silent). Once per 600 ms per body. t2r-no-dodge-cue.txt = off.
static void mdg_dodge_ok_cue(uint64_t ent, uint32_t who, const char *why) {
    static uint64_t last[T2R_MAX_PEERS + 1]; static int nl, off = -1; static uint64_t chk;
    uint64_t now = GetTickCount64(); uint32_t k = who < T2R_MAX_PEERS ? who : T2R_MAX_PEERS;
    if (who >= T2R_MAX_PEERS) ach_dodge();                     // achievements: one blow we dodged (achieve.c)
    if (off < 0 || now - chk > 2000) { chk = now; off = GetFileAttributesA("t2r-no-dodge-cue.txt") != INVALID_FILE_ATTRIBUTES; }
    if (off || !ent || ent == ~0ULL || now - last[k] < 600) return;
    last[k] = now;
    uint64_t a[5] = {fnv64("sfx-backpack-abby-bp-dodge-hard"), ent, 0, 0, 0};
    uint64_t r = dc_call(fnv64("play-sound-at-joint"), 5, a);
    if (LOGCAP(nl, 60)) xlog("DUEL: dodge cue sfx-backpack-abby-bp-dodge-hard on %s (%s) -> %llx", who >= T2R_MAX_PEERS ? "our body" : "the dodger's puppet", why, (unsigned long long)r);
}
static int mdu_vic_pair_on(void);   // melee_duel.c: we are the victim half of a running duel pair
static int mdu_partner_row_now(uint32_t slot);   // melee_duel_parry.c: the duel row of slot's swing in flight, -1 none
static const char *mdu_row_name(int row);   // melee_duel.c
static int dc_armed_at(uint64_t now);             // dcounter.c: the counter window is open now
static int dc_swing_start(void);                 // dcounter.c: a dodge that dropped a blow arms the counter window
static void dc_esc_early_press(void);           // dcounter.c: a dodge press before the escape window burns it
static int padinj_mel_held(void);   // padinject.c (v5-pinpress): the device's melee-attack bit, block or not
static int padinj_dodge_held(void);   // padinject.c: any evade / dodge input bit held on the device (pad or keyboard)
static int padinj_left_stick(float *x, float *y);   // padinject.c: the engine's own left stick of any pad
static int dc_esc_open(uint64_t now);              // dcounter.c: the countered attacker's (shorter) escape-dodge window
static void dc_escape(uint64_t now);
static int dc_esc_slot(void);
#define MD_REACH 3.6f
#define MD_COS 0.766f                  // ~40 deg
#define MD_WIN_MS 480
#define MD_WIN2_MS 260
#define MD_STREAK_MS 6000
#define MD_REACT_MS 380                // reaction time every defender gets from the moment the window could open (late geometry must not eat it)
#define MD_WIN_HARD_MS 1000            // the window never outlives the swing by more than this
#define MD_TURN_MS 450                 // after a swing note the attacker's puppet body is still turning towards us: facing is judged against the front half only
// Looser tuning (not 2013 data): the lockout after the last dodge charge 2.5 s -> 1.5 s, the PERFECT-dodge (counter) window
// 200 -> 350 ms before the contact, the parry's late edge up to the contact (melee_duel_parry.c). t2r-melee-strict.txt = the old values (2500 / 200 / mdp_lb).
static int mw_strict(void) { static int v = -1; static uint64_t at; uint64_t n = GetTickCount64(); if (v < 0 || n - at > 2000) { at = n ? n : 1; v = GetFileAttributesA("t2r-melee-strict.txt") != INVALID_FILE_ATTRIBUTES; } return v; }
#define MD_COOLDOWN_MS ((int)((mw_strict() ? 2500 : 1500) * sk_footwork_mul()))   // Boxer's Footwork (skills.c) x0.9 / 0.85 / 0.8
#define MD_FAIL_CD_MS 560          // [TUNING ps23] the cooldown of a dodge that dropped no blow, from its press (= where the dodge clip may be left by input, mdg_combat_tick)
#define MD_PERFECT_MS (mw_strict() ? 200 : 350)   // a dodge press at most this long before the contact = perfect (counter)
#define MD_MASH_MS 350            // Anti-spam: a dodge press with no window open locks the dodge for this long; a press in the
                                  // lock is ignored and renews it, so mashing never lands the dodge - one press timed to the window does. t2r-dodge-mash-ok.txt = no lock.
static uint64_t g_mdg_mash_until;
static int g_mdg_mash_n;                 // early presses in a row (a mash made dodging impossible); ONE early press (anticipating the swing) never locks, 2+ = a mash
static int mdg_mash_ok(void) { static int v = -1; if (v < 0) v = GetFileAttributesA("t2r-dodge-mash-ok.txt") != INVALID_FILE_ATTRIBUTES; return v; }
// a dodge should feel like a hard earned reward, not because the button was hit while 3 frames of the opponent swinging were visible: i-frames 380 -> 260 ms;
// with the duel's 420 / 360 ms windup floor a press in the first ~160 / ~100 ms of the windup runs out before the contact and the blow lands
#define MD_IFRAME_MS 260
#define MD_ENGINE_WAIT_MS 170
#define MD_GUN_LOCK_MS 380             // = the i-frames (the player was "locked in the dodge anim")
#define MD_CLIP_MAX_MS 680             // SP recording (19 dodge clips): SP leaves the dodge clip at 555-674 ms (median 660) and blends the next
                                       // clip in over ~175 ms - our 1200 ms hold felt sluggish. Was 1200, before that 600 with a 0.15 s blend (abrupt).
// (old)            // a combat-dodge clip is cut after this even without input (was 600: cut mid-recovery = a snap back to locomotion - abrupt)
#define MD_CLIP_FRAC 0.85f            // ... or at this fraction of the clip, whichever is first (the tail is idle settle)
#define MD_RELEASE_BLEND 0.18f        // SP: the clip after a dodge blends in over 175-193 ms. Was 0.30.
// (old)        // blend out of the dodge clip (was 0.15 s)
#define MD_MELEE_OK_MS 400
#define MD_ATK_RECOVER_MS 900
#define MD_MISS_MS 450                 // 0.5 x for 800 ms read as slow motion between moves (not fluid at all)
#define MD_MISS_SPEED 0.75f            // swing tail of a dodged blow (was 0.8: read as a connect when no miss clip is loaded)
#define MD_EXT_SPEED 0.65f
#define MD_EXT_MS 280
#define MSG_DODGE_SWING 0x97           // peer msg (ours): [u8 kind 1 = upgraded one-shot armed] the sender starts a free melee swing
#define MSG_DODGE_PRESS 0x99           // peer msg (ours): [u8 1 = immune][u8 dodge dir 0 fwd 1 left 2 right 3 back][u64 contextual dodge clip sid, 0 = none: played at once on the sender's puppet, phase-advanced by the one-way latency] the sender pressed dodge: our blow on him inside its i-frames shows nothing here (old peers ignore it)
#define MD_LAG_GRACE_MS 30.0f         // a press up to this long after the attacker's contact still dodges (ties go to the dodger)
#define MD_PRESS_MARGIN_MS 120         // ~1 RTT of slack on the attacker's copy of the dodger's i-frames
// ps45 (earlier: "not only do i not get the prompt, but its INSANELY hard to dodge, and even when you do, the other
// player (or bot) usually hits the one after anyways"). Measured on ps44 (rec44a A/B): the attacker ruled a press TOO LATE when it ARRIVED < 70 ms before its contact,
// while the victim's window (+ the prompt) ran to the contact SHOWN on its screen + 30 ms. The replica reaches its contact when the pair START arrives (one-way after the
// attacker's contact), so the dodger needed a lead of 70 + 2 x one-way on its own screen (local 90, 40 ms one-way 150, 80 ms one-way 230) and the last 100 + 2 x one-way ms
// of the advertised window were dead: such a press played the dodge, was ruled TOO LATE, the blow landed, and the ps36 rule then put a 1500 ms cooldown on it - the
// next blow (730-880 ms later in a chain) could not be dodged and showed no prompt. ps45: ONE rule on both screens = the press's lead on the DODGER's screen.
//  - the attacker accepts a press arriving >= md45_att_lead(one-way) before its contact = MD45_LEAD_MS on the dodger's screen minus the round trip (one-way capped at
//    MD45_OWL_CAP_MS; never under MD45_ATT_FLOOR_MS = the dodge shows a few frames on the attacker's screen before its contact). Local A/B (one-way ~10 ms): 70 ms, as ps44.
//  - the victim's window (and with it the press and the prompt) closes md45_vic_lead(one-way) before the contact shows on its screen: a later press does nothing (SP: presses
//    <= 67 ms before the contact gave no dodge), never a dodge that is then ruled late.
//  - a dodge pressed inside a window that dropped no blow keeps the 560 ms cooldown (MD_FAIL_CD_MS) instead of ps36's 1500 ms: the next swing is dodgeable again.
//  - the prompt is requested at least MD45_PROMPT_MIN_MS of the window (ps44: 63-125 ms).
// Opt-outs: t2r-dodge-window-ps45-old.txt (ruling + window), t2r-dodge-failcd-ps45-old.txt, t2r-dodge-prompt-ps45-old.txt (all re-read every 2 s).
#define MD45_LEAD_MS 90.0f             // [TUNING ps45] lead on the dodger's screen: between SP's latest failing press (67 ms) and latest avoided blow (133 ms, re/sp-melee-spec-1110.md 6); = ps44's local rule (70 + 2 x 10 ms)
#define MD45_ATT_FLOOR_MS 20           // [TUNING ps45] the press must still reach the attacker this long before its contact (the dodge starts on its screen before the blow)
#define MD45_OWL_CAP_MS 60.0f          // [TUNING ps45] one-way latency compensated at most (a laggier link pays the rest itself)
#define MD45_JITTER_MS 10              // [TUNING ps45] the two screens' one-way estimates differ: the victim's window closes this much earlier than the attacker's limit
#define MD45_PROMPT_MIN_MS 150         // [TUNING ps45] 9 frames of requests: the engine's icon is up and readable (its linger then runs 300-430 ms)
static int md45_flag(const char *nm, int *v, uint64_t *at) { uint64_t n = GetTickCount64(); if (*v < 0 || n - *at > 2000) { *at = n; *v = GetFileAttributesA(nm) != INVALID_FILE_ATTRIBUTES; } return *v; }
static int md45_win_old(void) { static int v = -1; static uint64_t at; return md45_flag("t2r-dodge-window-ps45-old.txt", &v, &at); }
static int md45_failcd_old(void) { static int v = -1; static uint64_t at; return md45_flag("t2r-dodge-failcd-ps45-old.txt", &v, &at); }
static int md45_prompt_old(void) { static int v = -1; static uint64_t at; return md45_flag("t2r-dodge-prompt-ps45-old.txt", &v, &at); }
// ps46: the lead 90 -> 54 ms, so the
// window (the 330 ms wind-up minus md45_vic_lead) is ~250 ms on a local link again (ps45 median ~219, live ~265; with ps46's 280 ms wind-up ~216). Same rule on both screens (the attacker's limit
// is still MDG46_LEAD_MS - round trip, >= MD45_ATT_FLOOR_MS). Note: SP's latest FAILING press was 67 ms before the contact - presses 54-67 ms before it now dodge.
// t2r-dodge-lead-ps46-old.txt = 90 (re-read every 2 s). Proof: 'dodge: ps46 press lead ...' on every change + the 'ps45 dodge window' DUEL line (lead45).
#define MDG46_LEAD_MS 54.0f            // [TUNING ps46] lead on the dodger's screen
static float mdg46_lead_ms(void) { static int v = -1, lg = -1; static uint64_t at; int o = md45_flag("t2r-dodge-lead-ps46-old.txt", &v, &at);
    if (lg != o) { lg = o; xlog("dodge: ps46 press lead %.0f ms on the dodger's screen (%s)", (double)(o ? MD45_LEAD_MS : MDG46_LEAD_MS), o ? "t2r-dodge-lead-ps46-old.txt: ps45's 90" : "[TUNING ps46], ps45 90"); }
    return o ? MD45_LEAD_MS : MDG46_LEAD_MS; }
static int md45_att_lead(float ow) { if (!(ow >= 0.0f)) ow = 0.0f; if (ow > MD45_OWL_CAP_MS) ow = MD45_OWL_CAP_MS; int r = (int)(mdg46_lead_ms() - 2.0f * ow + 0.5f); return r < MD45_ATT_FLOOR_MS ? MD45_ATT_FLOOR_MS : r; }
static int md45_vic_lead(float ow) { if (!(ow >= 0.0f)) ow = 0.0f; return md45_att_lead(ow) + (int)(2.0f * ow + 0.5f) + MD45_JITTER_MS; }
// ps54 (reports: a dodge played and the blow still landed). Measured in the 178 reports: light-swing windows 120-146 ms (median) at one-way 65 ms; at one-way 123 ms
// (one report) every window sat on the 120 ms floor while the attacker demanded a 276-285 ms lead = the dodge played and the blow landed. ps45 took the whole round
// trip out of the DODGER's window. ps54: the window is the same on every link = the wind-up minus MD54_VIC_LEAD_MS (what a zero-latency link got in ps46, ~216 ms
// for the 280 ms wind-up); the round trip is paid inside the attacker's hit-confirm wait (melee_duel.c verdict: the damage waits for the victim's ACK):
//  - a press that reaches the attacker before its contact = DODGED there (no TOO LATE limit: the dodger's window closes MD54_VIC_LEAD_MS before the contact showed);
//  - a later press: the attacker's pair START reaches the dodger inside its i-frames = refused there (mdg_pair_dodged: ABORT PS_AB_DODGED) -> the attacker's verdict
//    is NO HIT and it plays the miss (mdg_pair_refused_by_dodge).
// One rule for both screens: a dodge pressed inside the window, before the blow showed on the dodger's screen, dodges. On a slow link the attacker may see its blow
// start to connect for up to one round trip before the miss (the defender is favoured). t2r-dodge-window-ps54-old.txt = ps45 / ps46 (re-read every 2 s).
// A balance of tough but fair, not inhuman: 40 ms -> a light swing (contact 264-303 ms after it shows) leaves 224-263 ms to react = a
// focused player's visual reaction (200-250 ms) makes it, a late or distracted one does not; mashing stays locked (MD_MASH_MS) and the 2 charges / cooldown stay.
// (64 = ps46's LAN lead 54 + jitter 10: 200-239 ms. SP: presses <= 67 ms before the contact gave no dodge - SP's NPC swings are not reacted to on a network.)
#define MD54_VIC_LEAD_MS 40            // [TUNING ps54] the press must come this long before the blow shows on the dodger's screen
static int md54_off(void) { static int v = -1, lg = -1; static uint64_t at; int o = md45_flag("t2r-dodge-window-ps54-old.txt", &v, &at);
    if (lg != o) { lg = o; xlog("dodge: ps54 window %s (lead %d ms)", o ? "OFF (t2r-dodge-window-ps54-old.txt): ps45 - the round trip comes out of the dodger's window" : "ON - the window closes the lead before the contact shows, on every link; a press that reaches the attacker after its contact is ruled by the dodger at the pair START", MD54_VIC_LEAD_MS); }
    return o; }
// ps45: every light swing's wind-up lands its contact 330 ms after the press. Used by melee_npcwind.c NPCW_CONTACT_MS (the stretch,
// and with it the driven clip phase so the swing still reaches its -hit pose AT the contact, the SWING message's contact time = the victim's dodge window), the parry
// follow-up / initiative lock (melee_duel_parry.c) and the ps45 MISS lock formula (melee_duel.c). t2r-windup-330-ps45-old.txt = 380.
// ps46: 330 -> 280 ms. A swing whose SP clip reaches its contact later than that keeps SP's own time
// (melee_npcwind.c only stretches clips with tc < NPCW_CONTACT_MS - 15). t2r-windup-280-ps46-old.txt = 330; t2r-windup-330-ps45-old.txt = 380 (the newer file wins).
#define MW45_CONTACT_MS 330            // (was 380)
#define MW46_CONTACT_MS 280            // (was 330)
static int mw45_contact_ms(void) { static int v = -1, v46 = -1, lg = -1; static uint64_t at, at46; int o46 = md45_flag("t2r-windup-280-ps46-old.txt", &v46, &at46), o = md45_flag("t2r-windup-330-ps45-old.txt", &v, &at),
        r = o46 ? MW45_CONTACT_MS : o ? 380 : MW46_CONTACT_MS;
    if (lg != r) { lg = r; xlog("melee: ps46 light-swing wind-up target %d ms press -> contact (%s)", r, o46 ? "t2r-windup-280-ps46-old.txt: ps45's 330" : o ? "t2r-windup-330-ps45-old.txt: ps44's 380" : "ps45 330, ps44 380"); } return r; }
static int g_md45_inwin;               // the current dodge was pressed inside a swing's window (not the free / heavy dodge)
#define MSG_DODGE_RES 0x98             // peer msg (ours): [] the sender (victim) dodged a blow in time - the attacker plays the miss
typedef struct { int on, n, stage, chosen; uint64_t arm_f, t60_0, jw[2][2], jg[2]; float dir[2][2], total[2], from[3], sp, done, stop_xz[2]; int stop_on; const char *tag; uint64_t ms0; int pin; uint64_t hold_until; int dur60, face; float yaw0, yaw1; const MdgRm *rm; float rm_fx, rm_fz, rm_len;
                 int spm; float sp_th, sp_rmh, sp_u[2], sp_D, sp_lim0, sp_spc0, sp_auth; int lw_ok; float lw[2]; uint64_t lw_t60; float vt, rl; int vt_ok; uint64_t jl[2][2]; int heavy; } mdg_mv_t;   // spm: the SP in-melee dodge (melee_dodge.c "SP duel dodge"): travel at the hold = sp_D (attacker-aligned), sp_rmh = authored travel at sp_th s   // rm: follow the clip's authored root motion (frame: rm_f = forward), scaled to the collision-capped room   // dur60: travel frames (0 = 12 = 0.2 s); face: dodge curve + turn to yaw1
static struct {
    struct { uint64_t ms, open_ms, landed_ms; uint32_t seq; uint8_t kind, cls, hand, hand_real; } sw[T2R_MAX_PEERS];
    uint32_t seq_used, seq_n;
    uint64_t press_ms, iframe_until, cooldown_until, last_dodge_ms, melee_ok_at, gun_lock_until;
    int mode, last_slot;                                  // 0 idle, 1 waiting for the engine dodge move, 2 engine dodge, 3 fallback sidestep
    int prev_press, dodged_hits, window_open;
    uint64_t tr_until, tr_next; const char *tr_clip; float tr_from[2];
    uint64_t my_swing_ms, miss_until, atk_lock_until, ext_until, ext_clip, ext_move, slow_clip, slow_until, win_ms, prompt_n;
    int st_on, my_swing_sprint; float st_cap; uint64_t st_cap_ms; char st_clip[48]; uint64_t st_ms, st_f, st_jw[2], st_jg; float st_xz[2];     // the attacker's miss stumble (travel cap): clip, start, last probe rays
    int cmb_on, cmb_lastp; uint64_t cmb_ms, cmb_sid, cmb_hold_ms, cmb_land_ms;                 // the combat-dodge clip plays: start, clip sid (control returns early, see mdg_combat_tick)
    uint64_t imm_until[T2R_MAX_PEERS]; int8_t imm_dir[T2R_MAX_PEERS];
    struct { uint64_t ent, sid, end; } pd[T2R_MAX_PEERS];   // the dodge clip we forced on a puppet (blended out at its end)                    // attacker side: slot N dodged (pressed) and is immune until then (local time)
    int sfx_muted;
    uint64_t bar_t0, last_req_ms, last_req_f;             // cooldown bar start (the dodge press, 0 = none), last ms / frame the Dodge prompt was requested
    unsigned req_in_cd;                                   // prompt requests seen while the cooldown ran (must stay 0)
    int ext_on;
    uint64_t combat_clip, combat_move, combat_at; int combat_dir; char combat_name[72]; float press_xz[2]; int cap_done;   // successful-dodge clip chosen at the press (0 = none) + the press position (distance cap)
} g_mdg;
static mdg_mv_t g_md_fb, g_md_carry;
// v5-fb3: our own full-body dodge clip / its step runs on the local player (hfix_keep_melee, t2r-ext.c: the melee weapon stays in the hand through it)
static int mdg_own_clip_on(void) { return g_mdg.cmb_on || g_md_fb.on; }
static int g_mdg_glyph_logged;                 // the prompt glyph line is logged once per window
#ifndef T2R_RELEASE
static void mdgt_on_window_open(uint64_t now);
static int mdgt_press_now(uint64_t now);
static void mdgt_tick(uint64_t now);
static void mdgt_note_blow(uint64_t w, float dmg);
static void mdgt_note_dodged(void);
static void mdgt_note_miss(const char *anim);
#else
#define mdgt_on_window_open(n) ((void)0)
#define mdgt_press_now(n) 0
#define mdgt_tick(n) ((void)0)
#define mdgt_note_blow(w, d) ((void)0)
#define mdgt_note_dodged() ((void)0)
#define mdgt_note_miss(a) ((void)0)
#endif
static int mdg_off(void) {
    static int off = -1; static uint64_t at;
    uint64_t now = GetTickCount64();
    if (off < 0 || now - at >= 2000) {
        at = now ? now : 1;
        FILE *f = exe_side_open("t2r-no-melee-dodge.txt", "r"); int o = f != NULL; if (f) fclose(f);
        if (o != off) xlog("dodge: %s", o ? "OFF (t2r-no-melee-dodge.txt)" : "on (the dodge command works only while an enemy swing is about to land; 2.5 s cooldown, one dodge per swing)");
        off = o;
    }
    return off;
}
// a move the engine chains within MDG_DODGE_CHAIN_MS of a dodge move is still the dodge: against a puppet the engine follows player-dodge (3db24c6e)
// one frame later with an unnamed player-open-dodges.bin body move (6b29c4a5 / 1ea990e0, macro melee-player-swing-free) that we took for a swing -
// the lock-on glide + lunge then carried the dodger 2+ m toward / past the attacker (live test). The dodger can't swing before +400 ms.
#define MDG_DODGE_CHAIN_MS 380
static uint64_t mdg_dodge_seen_ms;
static int mdg_is_dodge_move(uint64_t m) {
    if (!m) return 0;
    size_t lo = 0, hi = sizeof MD_MOVES / sizeof MD_MOVES[0];
    while (lo < hi) { size_t mid = (lo + hi) / 2; if (MD_MOVES[mid] < m) lo = mid + 1; else hi = mid; }
    uint64_t now = GetTickCount64();
    if (lo < sizeof MD_MOVES / sizeof MD_MOVES[0] && MD_MOVES[lo] == m) { mdg_dodge_seen_ms = now; return 1; }
    return mdg_dodge_seen_ms && now - mdg_dodge_seen_ms < MDG_DODGE_CHAIN_MS;
}
static int mdg_no_whiff_boost(void) { return g_mdg.ext_on || g_mdg.miss_until > GetTickCount64(); }
// the states in which the dodge (and the miss lock) must not touch the body
static int mdu_att_hit_pair(void);   // melee_duel.c: our body is the attacker half of our own duel -hit pair (the follow-through of a landed blow)
static const char *mdg_busy(void) {
    if (match_substate() != 6) return "not in a match";
    if (g_downed || g_down_dying || g_uc4_dying_until || local_hp() <= 0.0f || g_down_at) return "downed / dying";
    // (a "Dodge" prompt showed over the puller while we lay prone under the truck - the dodge cannot start from prone / supine)
    { static uint64_t at; static int pr; uint64_t t = GetTickCount64(); if (t - at > 150) { at = t; uint64_t n = 0, p = dc_call(fnv64("player-is-prone?"), 0, &n), su = dc_call(fnv64("player-is-supine?"), 0, &n); pr = (p != ~0ULL && (p & 0xff)) || (su != ~0ULL && (su & 0xff)); }
      if (pr) return "prone / supine"; }
    // (log 131485/131491 -> layer lost 131525; 131147/131152 -> 131180): a dodge clip on our body while it plays the ATTACKER half of a pair (pin / hit pair)
    // crossfades the half out of the one ANIM_LAYER - our body stood in base locomotion, placed by the clock. Only the victim's -hit pair keeps the dodge.
    // ps36 (log [11844] / [14304] / [16394] / [18701] / [18837] 'button pressed ... (own attacker pair) - nothing happens; last enemy swing 250-468 ms ago
    // (in reach + facing, blow pending)', and no 'window OPEN' at all for the swings registered at [11816] / [14289] / [16368] / [16708]): after our own blow landed
    // our body is the attacker half of its -hit pair = our follow-through, and for that whole time an enemy swing had no window and no prompt. SP lets the player
    // dodge out of a follow-through: our own duel -hit pair (not a pin / parry / finisher / takedown) no longer blocks the dodge - melee_duel.c mdu_dodge_press
    // lets our half go the way the next combo press does. t2r-dodge-follow-ps35.txt = old.
    if (g_ps.role == 1 && g_ps.ent_att == SID_PLAYER && mdu_in_pair() && !mdu_att_hit_pair()) return "own attacker pair";
    if (g_stun_until || (g_exec_until && g_t60 < g_exec_until) || (psync_own() && !mdu_in_pair()) || gx_victim_active() || gx_running() || finisher_guard_on() || (g_xcam_on && !g_mq_cam) || g_unarm_exec) return "stun / execution / paired move";
    // (dodging past the 1st duel punch was near impossible - each -hit pair on us (0.9 s) made hrx_busy_own's psync_active() true until the next
    //  punch landed; inside a duel the -hit pair is cut by the dodge (mdu_dodge_press), so only the non-psync parts count there)
    if (g_intro_guard || (mdu_in_pair() ? (bp_own_phase_now() != 0 || g_rg[T2R_US].on || g_rev_by != 99 || g_xb.on) : hrx_busy_own())) return "intro / revive / backpack / bolt";
    return NULL;
}
static uint8_t *mdg_peer(uint32_t s) { typedef uint8_t *(*fn_peer)(uint32_t); return s < T2R_MAX_PEERS ? ((fn_peer)t2r_peer)(s) : NULL; }
// slot s is an enemy puppet that can swing at us now (geometry only): loose = a window already open (keeps it open while he steps)
// our own swing blocks the window only until its blow is out: in a live match (7 players) a trading player pressed dodge 14 times and never got a
// window - every enemy swing arrived while ours ran (g_ms_atk covers the whole clip, recovery included). SP lets the recovery be dodged.
#define MD_SELF_LOCK_MS 380                 // from our swing start: windup + contact (fists ~0.3 s, weapons a bit later)
static uint64_t mpace_swing_start(void);   // melee_pace.c
static uint64_t mdu_swing_t0(void);   // melee_duel.c: the start of our running duel swing (until its contact), 0 = none
static int mdg_own_swing_blocks(uint64_t now) {
    if (!g_ms_atk) return 0;
    static int old = -1; static uint64_t at;
    if (old < 0 || now - at >= 2000) { at = now ? now : 1; int o = GetFileAttributesA("t2r-dodge-no-recovery.txt") != INVALID_FILE_ATTRIBUTES; if (o != old) xlog("dodge: during our own swing %s", o ? "never (t2r-dodge-no-recovery.txt)" : "from 380 ms after its start (the recovery)"); old = o; }
    if (old) return 1;
    // ps36 (pre35 A [11922] / [14379] '(we swing (windup / contact))'): the gate was a fixed 380 ms from the pace's swing start. Inside a duel it is the swing
    // itself: closed until our contact (the wind-up stays committed), open from the contact on. t2r-dodge-swinggate-ps35.txt = the 380 ms.
    {   static int o36 = -1; static uint64_t at36; if (o36 < 0 || now - at36 >= 2000) { at36 = now ? now : 1; o36 = GetFileAttributesA("t2r-dodge-swinggate-ps35.txt") != INVALID_FILE_ATTRIBUTES; }
        if (!o36 && mdu_engaged()) return mdu_swing_t0() != 0; }
    uint64_t st = mpace_swing_start();
    return !st || now < st || now - st < MD_SELF_LOCK_MS || now - st > 2000;   // (no pace start known for this swing: block as before)
}
static int mdg_geom_ok(uint32_t s, int loose, float *dist) {
    uint8_t *pe = mdg_peer(s);
    if (!pe || !pe[0x4c] || pe[0x4d] || !*(uint64_t *)(pe + 0x60) || is_teammate(s) || g_peer_downed[s] || g_puppet_dead_here[s]) return 0;
    float pb[16], mb[16];
    const float *pl = puppet_locator(*(uint64_t *)(pe + 0x60), pb), *ml = uc4_my_loc(mb);
    if (!pl || !ml || !__builtin_isfinite(pl[0]) || !__builtin_isfinite(ml[0])) return 0;
    float dx = ml[0] - pl[0], dz = ml[2] - pl[2], d = __builtin_sqrtf(dx * dx + dz * dz);
    if (d > (loose ? MD_REACH + 0.8f : MD_REACH) || __builtin_fabsf(ml[1] - pl[1]) > 1.3f) return 0;
    if (dist) *dist = d;
    if (d < 0.05f) return 1;
    const float *q = pl + 4;
    float fx = 2.0f * (q[0] * q[2] + q[3] * q[1]), fz = 1.0f - 2.0f * (q[0] * q[0] + q[1] * q[1]), fl = __builtin_sqrtf(fx * fx + fz * fz);
    if (!(fl > 1e-3f)) return 0;
    float cosv = (fx * dx + fz * dz) / (fl * d);
    // the puppet body turns to its target some 250 ms after the swing note (windows opened 266-297 ms after the swing at 2.2-3 m): while the swing is young, anything in the front half counts
    if (s < T2R_MAX_PEERS && g_mdg.sw[s].ms && GetTickCount64() - g_mdg.sw[s].ms < MD_TURN_MS) return cosv >= 0.0f;
    return cosv >= (loose ? 0.5f : MD_COS);
}
// late-press grace (at 150-270 ms latency the swing is seen ~one-way + playout late, the presses came after the blow had arrived): a melee blow that arrives while that
// attacker's window is open and we have not pressed is HELD (applied by mdg_held_tick) for G = one-way + playout, clamp 60..180 ms; a press inside G drops it like a normal dodge.
// Opt-out t2r-no-dodge-grace.txt. Log: "dodge: blow from slot N held X ms (grace G) -> dodged / applied".
static struct { int on; uint32_t slot; uint64_t me, att, w, ammo, t0, until; float dmg; uint8_t flag; int grace; } g_mdh;
static int g_mdh_replay;
// the best open window: slot or -1
// each dodge gets a shorter and shorter window: every dodge of a streak (each < MD_STREAK_MS after the previous one) shrinks the next window: 480 -> 260 -> 180 -> 130 ms.
// A 6 s pause resets it. t2r-dodge-flat-streak.txt = old (480, then 260 for every later dodge of the streak).
static const uint16_t MD_STREAK_WIN[] = {MD_WIN_MS, MD_WIN2_MS, 180, 130};
static int g_mdg_streak_n;   // dodges in the current streak (set by mdg_start)
static int mdg_flat_streak(void) { static int v = -1; if (v < 0) v = GetFileAttributesA("t2r-dodge-flat-streak.txt") != INVALID_FILE_ATTRIBUTES; return v; }
static int mdg_cd36(void);   // (below) the ps36 cooldown rule
static int mdg_no_streak(void) { static int v = -1; static uint64_t at; uint64_t n = GetTickCount64(); if (v < 0 || n - at > 3000) { at = n ? n : 1; v = GetFileAttributesA("t2r-dodge-no-streak.txt") != INVALID_FILE_ATTRIBUTES; } return v; }
static uint64_t mdg_streak_win(uint64_t now) {
    // ps39 (log [9391] 'PRESS ... (window 260 ms, shortened: streak dodge)'): ps36 set the streak count to 1, and index 1 of the table IS the 260 ms
    // window - the shortening was still on. Under the ps36 rule a dodge never shortens the next window.
    // Restored rule: with no cooldown after a dodge that worked, the streak's shrinking window is
    // what stops a player from evading every swing. ps36 keeps it (the streak counts every press, mdg_start); a duel swing's window ends at its contact, so the
    // shrunk window opens late (mdg_window: the press must come in the last `win` ms). t2r-dodge-no-streak.txt = the ps39 rule (always 480 ms).
    if (mdg_cd36() && mdg_no_streak()) return MD_WIN_MS;
    if (!g_mdg.last_dodge_ms || now - g_mdg.last_dodge_ms >= MD_STREAK_MS) return MD_WIN_MS;
    int n = mdg_flat_streak() ? 1 : g_mdg_streak_n;
    if (n < 1) n = 1;
    if (n > 3) n = 3;
    return MD_STREAK_WIN[n];
}
// ps25 (the Dodge prompt stayed up from the first swing to the end of the fight; the log opens / closes the window per swing -
// 'dodge: window OPEN' [39576] [39624] [39668] ..., 'window closed' [39602] [39651] [39696] ...: 22 frames = ~370 ms between two windows). The prompt is the engine's
// interactable request, re-made every frame of the window; the engine's InteractableIcon keeps it up 300-430 ms after the LAST request and then fades (measured:
// melee_duel_pin.c:22) - longer than the gap, so it never went away. The requests now end MD_PROMPT_LINGER_MS before the window's end: the icon is gone when the
// window is (SP: the prompt shows only during the enemy's wind-up). The window itself and the press are untouched. t2r-dodge-prompt-ps24.txt = requested to the end.
#define MD_PROMPT_LINGER_MS 300   // the engine's linger after the last request (300-430 ms, melee_duel_pin.c:22)
#define MD_PROMPT_MIN_MS 50       // [TUNING ps25] a window shorter than the linger still requests the prompt this long (3 frames)
// ps46 (the prompt was misleading; ps45: window median ~219 ms, the
// "Dodge" icon up 450-650 ms = ps45's 150 ms request floor + the engine's 300-430 ms linger). The prompt is requested only while a press would start a dodge that
// avoids the blow: from the window's open (the window opens when the swing reaches us - nothing earlier is known, so no pre-open cue), never while our own dodge clip
// still travels (the press is dropped: ps39) or while the -hit pair on us would queue the press past the window's close (mdu_dodge_press), never through the
// anti-mash lock; the requests end MD_PROMPT_LINGER_MS before the close with a floor of MDG46_PROMPT_MIN_MS. The window's other gates (cooldown, prone,
// pinned, our own swing, busy, the miss lock) already close it = withdraw. LIMIT: the engine's InteractableIcon keeps the last label 300-430 ms after the last request
// and no call of ours ends it sooner (mdg_prompt_withdraw clears only our record + the text fallback), so a ~250 ms window still shows the icon ~100-230 ms past its
// close. Proof per window: 'dodge: ps46 prompt #N: requests +a..+b ms, window +0..+w ms ...'. t2r-dodge-prompt-ps46-old.txt = ps45's prompt (re-read every 2 s).
#define MDG46_PROMPT_MIN_MS 50    // [TUNING ps46] 3 frames of requests (ps25's floor): the icon comes up, its linger shows it on
static int mdg46_prompt_old(void) { static int v = -1; static uint64_t at; return md45_flag("t2r-dodge-prompt-ps46-old.txt", &v, &at); }
static struct { uint64_t req0, req1; int id, hid; } g_mdg46;   // this window's first / last prompt request; window id; the id whose suppression was logged
// ps46 icon hide (fixes the LIMIT above): at the window's close (and every other withdraw: press, cooldown, a press that would be dropped, pin / pullout) the
// engine icon our Dodge requests reached is hidden AT ONCE with the engine's own SetVisible(icon, 0) (t2r-ext.c wpi_hide: Hud2::InteractableIcon vtable
// 0x142d36770 +0x2e8 = 0x141e5ced0) instead of lingering 300-430 ms. Only when our Dodge request was its last refresh (else another prompt owns it now); the next
// request that reaches it shows it again. Proof: 'dodge: ps46 icon hidden at the close (+N ms after the last request)'. t2r-dodge-icon-hide-ps46-old.txt = the
// linger again (re-read every 2 s).
static int mdg46_icon_old(void) { static int v = -1; static uint64_t at; return md45_flag("t2r-dodge-icon-hide-ps46-old.txt", &v, &at); }
static struct { void *icon; uint64_t keep, ms; } g_mdg46i;     // the icon this window's latest Dodge request reached, its refresh frame (+0x4c0), when
static void mdg46_icon_hide(const char *why) {
    if (!g_mdg46i.icon) return;
    long long n = (long long)(GetTickCount64() - g_mdg46i.ms);
    static int nl;
    if (mdg46_icon_old()) { if (LOGCAP(nl, 150)) xlog("dodge: ps46 icon left to the engine's linger at the close (%s, +%lld ms after the last request; t2r-dodge-icon-hide-ps46-old.txt)", why, n); }
    else {
        const char *no = wpi_hide(g_mdg46i.icon, g_mdg46i.keep);
        if (LOGCAP(nl, 150)) {
            if (!no) xlog("dodge: ps46 icon hidden at the close (+%lld ms after the last request) - %s, window #%d, icon %p", n, why, g_mdg46.id, g_mdg46i.icon);
            else xlog("dodge: ps46 icon NOT hidden at the close (+%lld ms after the last request, %s): %s", n, why, no);
        }
    }
    g_mdg46i.icon = NULL;
}
static int mdu46w_queued_past(uint64_t now, uint64_t end);   // melee_duel.c: a press now is queued by the -hit pair on us until after the window's close
static uint64_t g_mdg_win_end, g_mdg_prompt_open_ms;   // the end of the window mdg_window just reported; when the current window opened
static int mdg_window(uint64_t now, uint64_t *win_ms) {
    uint64_t win = mdg_streak_win(now);
    const uint64_t streak_win = win;   // The streak's own window (the tell below may shorten `win` too; only the streak opens the window late)
    uint64_t react = win < MD_WIN_MS ? win : MD_REACT_MS;
    { uint64_t tw = mtell_win_ms(), tr = mtell_react_ms(); if (tw && win > tw) win = tw; if (tr && react > tr) react = tr; }   // melee_tell.c: the window follows the tell (a streak's 260 ms stays)
    *win_ms = win;
    int best = -1; uint64_t bms = 0, bend = 0;
    for (uint32_t s = 0; s < T2R_MAX_PEERS; s++) {
        uint64_t sw = g_mdg.sw[s].ms;
        int held = g_mdh.on && g_mdh.slot == s && now < g_mdh.until;                // a blow of this swing is held for the late-press grace: its window stays open
        if (!sw || (now - sw > MD_WIN_HARD_MS && !held) || g_mdg.sw[s].seq == g_mdg.seq_used) continue;
        if (g_mdg.sw[s].landed_ms >= sw) continue;                                    // the blow of this swing already came (landed / dodged): nothing left to react to
        if (!mdg_geom_ok(s, g_mdg.window_open, NULL)) continue;
        uint64_t xend = 0; int xr = mex_window_end(s, &xend);                       // melee exchange: its own window on the shared clock (2 = this partner's window is closed)
        if (xr == 2) continue;
        if (!g_mdg.sw[s].open_ms || g_mdg.sw[s].open_ms < sw) g_mdg.sw[s].open_ms = now;   // first moment this swing could be dodged
        // the window ends when the blow can land, not a fixed time after the swing began: at least `win` after the swing, and at least `react` after it could first open
        uint64_t end = sw + win; if (g_mdg.sw[s].open_ms + react > end) end = g_mdg.sw[s].open_ms + react;
        if (end > sw + MD_WIN_HARD_MS) end = sw + MD_WIN_HARD_MS;
        if (xr == 1) end = xend;
        { uint64_t dend = 0; int dr = xr ? 0 : mdu_window_end(s, &dend); if (dr == 1) end = dend; else if (dr == 2 && !held) continue; }   // melee_duel.c: a duel swing's window ends at ITS contact (fairness rule, DUEL: dodge ruling)
        if (now > end && !held) continue;
        if (!held && streak_win < MD_WIN_MS && now + streak_win < end) continue;   // A streak dodge's window is the last streak_win ms before the blow (480 -> 260 -> 180 -> 130)
        if (sw > bms) { bms = sw; best = (int)s; bend = end; }
    }
    g_mdg_win_end = best >= 0 ? bend : 0;
    return best;
}
// ---- short collision-checked moves of our own body (the glide's rays: walls at 0.5 / 1.0 m, ground at the end spot)
static void mdg_mv_begin(mdg_mv_t *m, const char *tag, int n, const float dirs[2][2], const float *tot) {
    float mb[16]; const float *l = uc4_my_loc(mb);
    if (!l || !__builtin_isfinite(l[0])) return;
    memset(m, 0, sizeof *m);
    m->n = n; m->tag = tag; m->arm_f = g_frame ? g_frame : 1; m->ms0 = GetTickCount64(); memcpy(m->from, l, 12);
    for (int i = 0; i < n; i++) {
        float ux = dirs[i][0], uz = dirs[i][1], total = tot[i], far_ = total + 0.4f;
        m->dir[i][0] = ux; m->dir[i][1] = uz; m->total[i] = total;
        float a1[3] = {l[0], l[1] + 0.5f, l[2]}, b1[3] = {l[0] + ux * far_, l[1] + 0.5f, l[2] + uz * far_};
        float a2[3] = {l[0], l[1] + 1.0f, l[2]}, b2[3] = {b1[0], l[1] + 1.0f, b1[2]};
        float c1[3] = {l[0] + ux * total, l[1] + 0.6f, l[2] + uz * total}, e1[3] = {c1[0], l[1] - 0.9f, c1[2]};
        // dodges should look like proper dodges: in tall grass the 0x207 rays stopped on the grass (~0.45 m up):
        // "left 0.00 right 0.00", "ground 0.11 / 0.25" -> "no room ... the clip plays in place (pinned, no travel)". 0x1b07 passes grass / foliage;
        // walls and other bodies still stop it (our own body stays ignored), same mask as the paired-move path gate and the placed mines.
        m->jw[i][0] = world_ray_kick_m(a1, b1, 0, 0x1b07); m->jw[i][1] = world_ray_kick_m(a2, b2, 0, 0x1b07); m->jg[i] = world_ray_kick_m(c1, e1, 0, 0x1b07);
        // ps35 (log [16260]-[16317]: 'room 2.17 m' for a back dodge although the attacker's takedown scan read 'WALL 0.91 m behind the victim ... 4 of 5 chest
        // rays hit (0.91 0.91 0.91 -1.00 0.96)' in the same frames - a surface with a gap: the two centre-line rays went through it, the body did not fit): two more
        // rays at chest height, one body radius (0.30 m, the path gates' radius) left and right of the path. t2r-dodge-rays-ps34.txt = the centre line only.
        for (int s = 0; s < 2; s++) { float o = s ? -0.30f : 0.30f, a3[3] = {l[0] + uz * o, l[1] + 1.0f, l[2] - ux * o}, b3[3] = {a3[0] + ux * far_, a3[1], a3[2] + uz * far_}; m->jl[i][s] = world_ray_kick_m(a3, b3, 0, 0x1b07); }
    }
    m->on = 1;
}
// ---- SP duel dodge. SP facts (re/sp-sandbox-runs/sea-1026-human-melee-
// dodge-parry-disarm.log, 11 player-contextual-dodge-back-* vs a 1h human; the same ellie-1h-dodge-back-combat-* clips we play): the player's travel is
// 0.37-0.60 m at 226-365 ms, 0.93-1.13 m at 700-820 ms, 1.15-1.21 m at ~1.1 s (the move ends at 1156-1170 ms) - about HALF the clips' authored 2.0-2.6 m
// root motion (the move plays under melee-state-custom-align on the attacker's locator). The attacker FOLLOWS: its combo swing steps 0.8-1.3 m in over the
// same time, so the spacing stays 1.25-1.45 m (start 0.97-1.68 m). In MP the attacker does not walk in after a dodge, so the travel here is SP's 1.05 m at
// the clip hold (MD_CLIP_MAX_MS), cut so the end spot is no further than MDS_SPC_END from where the attacker stands NOW (re-solved every frame: an attacker
// that steps in lets the dodge carry on, as SP's), never under MDS_MIN_M (a pinned 0.05-0.2 m dodge read as a stumble). Opt-out t2r-duel-dodge-v4.txt.
#define MDS_TRAVEL_M 1.05f    // SP travel at ~700 ms (0.93 / 1.04 / 1.05 / 1.06 / 1.13 m)
#define MDS_SP_END_M 1.17f    // SP travel at the move end (~1.16 s), for the log
// v5-geo2 (SP sandbox re/sp-sandbox-runs/*.log, player-contextual-dodge-<left|right>-* = ellie-1h-dodge-<left|right>-combat-* vs a fist / 1h NPC, travel at ~1.0-1.15 s:
// right-horiz-right-c 1.48-1.67, left-horiz-left-b 1.36-1.38, left-downward-left-c 1.47-1.52, left-downward-right-d 1.32-1.54 m; the back ones 1.20-1.36): a SIDE dodge
// travels further than a back one in SP. Both are still ~0.6-0.75 of the clips' authored ~2.0 m root (melee_dodge_rm.h) - SP does not play them at native travel either.
#define MDS_SP_END_SIDE_M 1.45f
// (dodges played in one place: every dodge was cut to MDS_MIN_M 0.65 m by the 1.50 m end spacing - "cut to 1.50 m of us: 0.31"):
// SP's 1.25-1.45 m end spacing exists only because its NPC attacker walks 0.8-1.3 m in during the dodge; ours does not, so the cut removed the travel itself.
// The end spacing is now the dodge's own SP travel from a normal start: 1.15 m start + 1.45 m side travel = 2.60 m, so a dodge covers SP's measured 1.17 m
// (back) / 1.45 m (side) unless the room stops it. t2r-dodge-spacing-old.txt = 1.50 m.
#define MDS_SPC_END_OLD 1.50f // SP spacing after the dodge 1.25-1.45 m (1.61 / 1.79 at the dodge counter's start)
static float mds_spc_end(void) { static int v = -1; static uint64_t at; uint64_t n = GetTickCount64(); if (v < 0 || n - at > 3000) { at = n; v = GetFileAttributesA("t2r-dodge-spacing-old.txt") != INVALID_FILE_ATTRIBUTES; } return v ? MDS_SPC_END_OLD : 2.60f; }
// Dodges looked as if the characters spasm (full travel, softer start chosen): the dodge travels the clip's own authored root motion to its flat
// part (~1.7 m back, not SP's 1.17 / 1.45 m = the x0.66 scale: the legs pushed hard while the body barely moved), the end spacing cap grows to fit it, and the
// puppet's dodge blends in over 0.25 s (melee_duel_tl.c). t2r-dodge-sp-travel.txt = SP's travel (the x0.66 scale) and the 0.20 s blend.
// ps35 (log [16260]-[16317] 'whole clip scaled x1.00, 2.17 m at its flat part ... travel 2.17 m in 953 ms (SP: 1.05 m at 700 ms, 1.17 m at the move end)':
// the ps17 full authored travel is twice SP's measured dodge - a 2 m slide backwards off a kick read as a knock-back, and it carried the dodger through a wall
// 0.9 m behind it). SP's measured travel again (back 1.17 m, side 1.45 m at the hold; same clip, timing, i-frames). t2r-dodge-full-travel-ps34.txt = the full travel.
static int mds_full(void) { static int v = -1; static uint64_t at; uint64_t n = GetTickCount64(); if (v < 0 || n - at > 3000) { at = n; v = GetFileAttributesA("t2r-dodge-full-travel-ps34.txt") != INVALID_FILE_ATTRIBUTES; } return v; }
#define MDS_SPC_END (mds_full() ? 3.40f : mds_spc_end())
#define MDS_MIN_M 0.65f
#define MDS_FLAT_V 0.35f      // authored root speed (m/s) under which the clip counts as flat (once >= 85 % of its travel): the release point
// where the clip's authored root motion has flattened (s): the dodge plays to there, scaled, and is released with ~no root motion left for the blend-out.
// Contextual dodge clips: 0.80-1.42 s, median ~1.06 (SP's move ends at 1156-1170 ms). Bounded [MD_CLIP_MAX_MS, 1.3 s] and by the clip's length.
static int mdg_sp_off(void);
static void mdu_swing_dodge_cancel(void);   // melee_duel.c: a dodge ends our duel swing record
static float mdg_sp_flat_s(const MdgRm *rm) {
    if (!rm || rm->n < 3) return (float)MD_CLIP_MAX_MS / 1000.0f;
    float dt = rm->dur / (float)(rm->n - 1), mx = 0.0f, t = 0.0f;
    for (int i = 0; i < rm->n; i++) { float d = __builtin_sqrtf((float)rm->x[i] * rm->x[i] + (float)rm->z[i] * rm->z[i]) / 100.0f; if (d > mx) mx = d; }
    for (int i = 1; i < rm->n; i++) {
        float d = __builtin_sqrtf((float)rm->x[i] * rm->x[i] + (float)rm->z[i] * rm->z[i]) / 100.0f;
        float vx = (float)(rm->x[i] - rm->x[i - 1]), vz = (float)(rm->z[i] - rm->z[i - 1]), v = __builtin_sqrtf(vx * vx + vz * vz) / 100.0f / dt;
        if (d >= 0.85f * mx && v < MDS_FLAT_V) { t = (float)i * dt; break; }
    }
    if (t <= 0.0f) t = 1.3f;
    if (t < (float)MD_CLIP_MAX_MS / 1000.0f) t = (float)MD_CLIP_MAX_MS / 1000.0f;
    if (t > 1.3f) t = 1.3f;
    if (t > rm->dur - 0.05f) t = rm->dur - 0.05f;
    return t;
}
// how long a dodge clip is held (ms): SP mode = to its flat part (both screens: the puppet's copy blends out where the dodger's does), else the v4 rule
// ps46 ("00:12-00:14 the character jitters,
// then glides backwards stationary"; A [104832] 'puppet slot 0 dodge PATH armed: ... 1.17 m at its flat part 987 ms' -> [104892] 'travel ... 0.80 m at 1000 ms',
// B [106765] 'HEAVY dodge ... the clip at x0.80' / [106843] '1.16 m in 1234 ms'; B [107316] PATH 1.17 m at 940 ms -> [107376] 0.81 m at 1000 ms, A [105382] HEAVY):
// a HEAVY dodge plays at x0.80 on the dodger's own body with its path on that slower clock (held th / 0.8), but MSG_DODGE_PRESS did not say so - the
// puppet on the other screen played the clip at x1.0 and its path on the x1.0 clock, ran ahead of the stream (the k shrink pulled it back = the jitter), let go
// at th + 60 ms and the spring then carried the body the remaining 0.3-0.4 m onto the stream with the clip already blended out = the stationary glide. The press
// now carries a heavy bit (buf[0] bit 1; old peers read bit 0 only): the puppet's clip runs at MDG_HEAVY_RATE, its path on the dodger's heavy clock and its hold
// th / MDG_HEAVY_RATE - the travel happens once, with the animation. t2r-dodge-glide-ps46-old.txt = old.
static uint64_t g_mdg_rx_heavy[T2R_MAX_PEERS], g_mdg_rx_heavy_sid[T2R_MAX_PEERS];   // press time / clip of a received heavy dodge
static int mdg_glide46_off(void) { static int off = -1; static uint64_t chk; return ov_off("t2r-dodge-glide-ps46-old.txt", &off, &chk); }
// ps46b (pre-mortem of 5911abc5): was keyed by the clip only (the first slot with a heavy dodge of this clip) and the hold took no slot - with 3+ players
// another slot's NORMAL dodge of the same clip within 2.5 s got the heavy hold / rate. Now per slot: 1 = slot's own received heavy dodge plays this clip.
static int mdg_rx_heavy(int slot, uint64_t sid) {
    if (!sid || slot < 0 || slot >= T2R_MAX_PEERS || mdg_glide46_off()) return 0;
    uint64_t now = GetTickCount64();
    return g_mdg_rx_heavy[slot] && g_mdg_rx_heavy_sid[slot] == sid && now - g_mdg_rx_heavy[slot] < 2500;
}
static uint64_t mdg_sp_hold_ms(int slot, uint64_t sid, uint64_t v4) {     // slot = the puppet's slot (its heavy hold), -1 = none
    if (mdg_sp_off() || mdu_dodge_cap() <= 0.0f) return v4;
    const MdgRm *rm = mdg_rm_find(sid);
    float hk = mdg_rx_heavy(slot, sid) ? 1.0f / 0.8f /* MDG_HEAVY_RATE */ : 1.0f;   // ps46 (ps46b: this slot's own heavy dodge only)
    return rm ? (uint64_t)(mdg_sp_flat_s(rm) * hk * 1000.0f) : (uint64_t)((float)v4 * hk);
}
static int mdg_sp_off(void) {
    static int off = -1; static uint64_t at; uint64_t now = GetTickCount64();
    if (off < 0 || now - at >= 2000) { at = now ? now : 1; FILE *f = exe_side_open("t2r-duel-dodge-v4.txt", "r"); int o = f != NULL; if (f) fclose(f); if (o != off) xlog("sdodge: SP duel dodge %s", o ? "OFF (t2r-duel-dodge-v4.txt: the v4 1.15 m cap along the clip)" : "on (SP travel 1.05 m at the hold, attacker-aligned end spacing <= 1.50 m, grunt at +150 ms)"); off = o; }
    return off;
}
static int mdg_att_xz(float *x, float *z) {      // the attacker of our dodge (the window's slot) as displayed here
    if (g_mdg.last_slot < 0) return 0;
    uint8_t *pe = mdg_peer((uint32_t)g_mdg.last_slot); float pb[16];
    const float *pl = pe && *(uint64_t *)(pe + 0x60) ? puppet_locator(*(uint64_t *)(pe + 0x60), pb) : NULL;
    if (!pl || !__builtin_isfinite(pl[0])) return 0;
    *x = pl[0]; *z = pl[2]; return 1;
}
// the travel at the hold: SP's, room-capped (m->total[c]), cut to the attacker spacing; grows only (an attacker stepping in), <= 3 m/s
static float mdg_sp_travel(mdg_mv_t *m, int c) {
    float D = m->total[c], ax, az;
    if (mdg_att_xz(&ax, &az)) {
        float fx = m->from[0] - ax, fz = m->from[2] - az, b = m->sp_u[0] * fx + m->sp_u[1] * fz, cc = fx * fx + fz * fz;
        float disc = b * b - cc + MDS_SPC_END * MDS_SPC_END, lim = disc >= 0.0f ? -b + __builtin_sqrtf(disc) : 0.0f;
        if (m->sp_lim0 < 0.0f) { m->sp_lim0 = lim; m->sp_spc0 = __builtin_sqrtf(cc); }
        if (lim < D) D = lim;
    }
    float dmin = MDS_MIN_M < m->total[c] ? MDS_MIN_M : m->total[c];
    if (D < dmin) D = dmin;
    if (m->sp_D <= 0.0f) m->sp_D = D;
    else if (D > m->sp_D) { float mx = m->sp_D + 0.05f; m->sp_D = D < mx ? D : mx; }
    return m->sp_D;
}
#define MDS_SETTLE_MS 500     // the post-release measure window (the old mid-motion release slid for 26 frames, ~430 ms)
static struct { int on; unsigned n; uint64_t until, t0; float x, z, fx, fz, undone; } g_mds_set;
static int mdg_stick_dir(float *sx, float *sy);
static void mdg_sp_report(mdg_mv_t *m, const char *why) {
    if (!m->spm) return;
    m->spm = 0;
    float mb[16], ax, az; const float *l = uc4_my_loc(mb);
    if (!l) return;
    float moved = __builtin_sqrtf((l[0] - m->from[0]) * (l[0] - m->from[0]) + (l[2] - m->from[2]) * (l[2] - m->from[2]));
    float e = -1.0f; if (mdg_att_xz(&ax, &az)) e = __builtin_sqrtf((l[0] - ax) * (l[0] - ax) + (l[2] - az) * (l[2] - az));
    uint64_t ms = GetTickCount64() - m->ms0;
    xlog("sdodge: %s travel %.2f m in %llu ms (SP: %.2f m at 700 ms, %.2f m at the move end ~1160 ms, flat; authored %.2f m, target %.2f m, spacing cut %.2f m, room %.2f m), spacing to attacker start %.2f end %.2f m (SP 1.25-1.45) - %s",
         g_mdg.combat_name, moved, (unsigned long long)ms, MDS_TRAVEL_M, MDS_SP_END_M, m->sp_auth, m->sp_D, m->sp_lim0, m->chosen >= 0 && m->chosen < 2 ? m->total[m->chosen] : 0.0f, m->sp_spc0, e, why);
    // after the release (released mid-motion at 680 ms, the dodger's OWN body slid on 0.3-0.6 m in ~26 frames - the clip's root motion
    // through its stop-animating blend-out - and the attacker's puppet mirrored it: 1.24-1.89 m at 1000 ms). The clip now plays to its flat part, so
    // this only MEASURES the slide after the release (no position writes): "sdodge: after release ...".
    if (strcmp(why, "counter press") != 0) {
        g_mds_set.on = 1; g_mds_set.until = GetTickCount64() + MDS_SETTLE_MS; g_mds_set.t0 = m->ms0; g_mds_set.x = l[0]; g_mds_set.z = l[2];
        g_mds_set.fx = m->from[0]; g_mds_set.fz = m->from[2]; g_mds_set.undone = 0.0f; g_mds_set.n = 0;
    }
}
// t2r-ext.c feature_stuck_guard: its rewind of the previous move (a duel hit pair that crossed geometry) lands while our dodge pin writes the body:
// the pin takes it as a shift of its origin (its path continues from the corrected spot) instead of the two writers fighting every frame. 1 = taken
static int mdg_pin_on(void) { return g_md_fb.on && g_md_fb.pin; }     // (t2r-ext.c own_snap_cross_tick: the dodge pin probes its own room)
// The controller follows the SAME scaled path: the engine's anim-delta step (t2r-ext.c adelta_hook) of our player gets the pin's step of THIS frame
// in place of the clip's unscaled root step (horizontal only; y and rotation untouched). Before, the controller followed the clip's 2.1 m root while the shown body followed the 1.2-1.45 m
// path: the net stream carried 2.2 m (log [219152] puppet travel 2.22 m), and the release teleported the controller onto the shown spot (log [217255], the camera cut).
// t2r-dodge-ctrl-old.txt = the old unscaled root. 1 = the delta was replaced.
static struct { uint64_t f; float dx, dz; uint32_t n_set, n_used; } g_mdpin;
static int mdg_ctrl_followed(void) { return g_mdpin.n_used >= 3; }     // the controller was stepped along the pinned path for this dodge: no release teleport needed
static int mdg_pin_adelta(float *r) {
    if (!g_md_fb.on || !g_md_fb.pin || !g_mdpin.f || g_frame > g_mdpin.f + 1 || g_frame < g_mdpin.f) return 0;
    static int old = -1; static uint64_t oc; uint64_t now = GetTickCount64(); if (old < 0 || now - oc > 3000) { oc = now; old = GetFileAttributesA("t2r-dodge-ctrl-old.txt") != INVALID_FILE_ATTRIBUTES; }
    if (old) return 0;
    float sx = g_mdpin.dx, sz = g_mdpin.dz;
    if (r[0] * r[0] + r[2] * r[2] > 0.8f * 0.8f) return 0;     // (a root step is centimetres: a big delta is a pending teleport / locator write - not ours to replace)
    if (sx * sx + sz * sz > 0.6f * 0.6f) return 0;      // (a path step is centimetres: a larger one is something else's delta - a pending teleport / locator write)
    static int nl; if (LOGCAP(nl, 12)) xlog("sdodge: the controller follows the pinned path - engine root step %.3f %.3f replaced by the path's %.3f %.3f (frame %llu)", (double)r[0], (double)r[2], (double)sx, (double)sz, (unsigned long long)g_frame);
    r[0] = sx; r[2] = sz; g_mdpin.n_used++;
    return 1;
}
static int mdg_pin_shift(float dx, float dz) {
    if (!g_md_fb.on || !g_md_fb.pin) return 0;
    g_md_fb.from[0] += dx; g_md_fb.from[2] += dz;
    static uint64_t last_ms0; static int nl;
    if (last_ms0 != g_md_fb.ms0 && LOGCAP(nl, 30)) { last_ms0 = g_md_fb.ms0; xlog("sdodge: the stuck guard's rewind arrives during the dodge - taken as a shift of the dodge's origin (one writer, no pin / guard fight)"); }
    return 1;
}
static void mdg_settle_end(const char *why) {
    if (!g_mds_set.on) return;
    g_mds_set.on = 0;
    float mb[16], ax, az; const float *l = uc4_my_loc(mb);
    float tot = l ? __builtin_sqrtf((l[0] - g_mds_set.fx) * (l[0] - g_mds_set.fx) + (l[2] - g_mds_set.fz) * (l[2] - g_mds_set.fz)) : -1.0f;
    float e = -1.0f; if (l && mdg_att_xz(&ax, &az)) e = __builtin_sqrtf((l[0] - ax) * (l[0] - ax) + (l[2] - az) * (l[2] - az));
    float sl = l ? __builtin_sqrtf((l[0] - g_mds_set.x) * (l[0] - g_mds_set.x) + (l[2] - g_mds_set.z) * (l[2] - g_mds_set.z)) : -1.0f;
    xlog("sdodge: after release (%s, %u frames): slid %.2f m past the release spot (target <= 0.10); travel from the press %.2f m at %llu ms (SP 1.15-1.21 m at ~1.1 s), spacing to attacker %.2f m",
         why, g_mds_set.n, sl, tot, (unsigned long long)(GetTickCount64() - g_mds_set.t0), e);
}
static void mdg_settle_tick(uint64_t now) {
    if (!g_mds_set.on) return;
    if (now >= g_mds_set.until) { mdg_settle_end("done"); return; }
    if (match_substate() != 6 || g_downed || local_hp() <= 0.0f || mdg_busy()) { mdg_settle_end("busy"); return; }
    if (!g_mds_set.n) { float ab[16]; const float *al = uc4_my_loc(ab); if (al && __builtin_isfinite(al[0])) { g_mds_set.x = al[0]; g_mds_set.z = al[2]; } }   // (the body as it stands, not the pin's last target)
    float sx, sy; mdg_stick_dir(&sx, &sy);
    if (sx * sx + sy * sy >= 0.3f * 0.3f) { mdg_settle_end("move input"); return; }
    if (pad_cmd_on("aim") || pad_melee_cmd() || (game_focused() && (GetAsyncKeyState(0x46) & 0x8000))) { mdg_settle_end("aim / melee input"); return; }
    g_mds_set.n++;
}
// (the dodger's puppet leaned / ducked where it stood and slid later):
// the puppet's dodge clip played over the STREAMED position, which the duel spring only follows without correcting while a clip runs. The puppet now travels the
// SAME path the dodger's own body is pinned to (mdg_mv_tick): the clip's baked root motion (melee_dodge_rm.h) in the frame facing the attacker, scaled by one k
// to SP's travel (back 1.17 m / side 1.45 m at the clip's flat part), cut to MDS_SPC_END from the attacker - from the frame its dodge clip starts here
// (dtl_play). The dodger's own room cap is not known here: when the stream shows it travelling under half of the path (a wall), k shrinks toward it. At the
// clip's hold the spring takes the body back onto the stream. t2r-puppet-dodge-path-old.txt = the old streamed position.
static struct { int on, dir; uint64_t t0, hold_ms; const MdgRm *rm; float k, fx, fz, p0[2], n0[2], th; int n0_ok, heavy; uint64_t ent, sid; } g_mdg_pp[T2R_MAX_PEERS];
static void dtl_speed_s(uint64_t ent, uint64_t sid, float v, int src);   // melee_duel_tl.c
// ps46: the dodger's own heavy clip clock (mdg_mv_tick): clip time at real time t, the velocity eased in over 0.15 s (MDG_HEAVY_RATE / MDG_HEAVY_RAMP_S)
static float mdg_heavy_tt(float t) { return 0.8f * (t < 0.15f ? t * t / (2.0f * 0.15f) : t - 0.5f * 0.15f); }
static int mdg_pp_off(void) { static int v = -1; static uint64_t at; uint64_t n = GetTickCount64(); if (v < 0 || n - at > 3000) { at = n; v = GetFileAttributesA("t2r-puppet-dodge-path-old.txt") != INVALID_FILE_ATTRIBUTES; } return v; }
static void mdg_pp_arm(uint32_t slot, uint64_t ent, uint64_t sid, float age_ms) {
    if (slot >= T2R_MAX_PEERS) return;
    g_mdg_pp[slot].on = 0;
    if (mdg_pp_off() || mdg_sp_off() || mdu_dodge_cap() <= 0.0f || !ent) return;
    const MdgRm *rm = mdg_rm_find(sid);
    float pb[16], mb[16]; const float *p = puppet_locator(ent, pb), *l = uc4_my_loc(mb);
    if (!rm || !p || !l || !__builtin_isfinite(p[0]) || !__builtin_isfinite(l[0])) return;
    float fx = l[0] - p[0], fz = l[2] - p[2], fl = __builtin_sqrtf(fx * fx + fz * fz);
    if (!(fl > 0.05f)) return;
    fx /= fl; fz /= fl;                                      // the clip frame faces the attacker (us)
    float th = mdg_sp_flat_s(rm), hx, hz, hy; mdg_rm_at(rm, th, &hx, &hz, &hy);
    float rmh = __builtin_sqrtf(hx * hx + hz * hz);
    if (!(rmh > 0.05f)) return;
    int dir = g_mdg.imm_dir[slot];
    float spe = dir == 1 || dir == 2 ? MDS_SP_END_SIDE_M : MDS_SP_END_M;
    float ux = (hx * -fz + hz * fx) / rmh, uz = (hx * fx + hz * fz) / rmh;   // the travel direction at the hold
    float ox = p[0] - l[0], oz = p[2] - l[2], b = ux * ox + uz * oz, cc = ox * ox + oz * oz, disc = b * b - cc + MDS_SPC_END * MDS_SPC_END;
    if (mds_full()) spe = rmh;   // The clip's own travel (see mds_full)
    float lim = disc >= 0.0f ? -b + __builtin_sqrtf(disc) : 0.0f, D = spe;
    if (lim < D) D = lim;
    if (D < MDS_MIN_M) D = MDS_MIN_M;
    typeof(&g_mdg_pp[0]) q = &g_mdg_pp[slot];
    q->on = 1; q->dir = dir; q->rm = rm; q->k = D / rmh; q->fx = fx; q->fz = fz; q->p0[0] = p[0]; q->p0[1] = p[2]; q->th = th; q->n0_ok = 0;
    q->t0 = GetTickCount64() - (uint64_t)(age_ms > 0.0f && age_ms < 400.0f ? age_ms : 0.0f); q->hold_ms = (uint64_t)(th * 1000.0f);
    q->heavy = mdg_rx_heavy((int)slot, sid); q->ent = ent; q->sid = sid;
    if (q->heavy) {     // ps46: the dodger's heavy clock - held th / rate, the clip at the rate (re-set every frame in mdg_pp_pos: dtl's catch-up resets it to x1.0)
        q->hold_ms = (uint64_t)(th / 0.8f * 1000.0f);
        dtl_speed_s(ent, sid, 0.8f, MO_SRC("dodge.pup_heavy"));
        static int nl46; if (LOGCAP(nl46, 60)) xlog("sdodge: ps46 puppet slot %u HEAVY dodge - its clip at x0.80 and its path on the dodger's heavy clock (eased-in 150 ms), held %llu ms (x1.0 clock: %.0f ms) - one travel, with the animation (t2r-dodge-glide-ps46-old.txt = old)",
                                                    slot, (unsigned long long)q->hold_ms, (double)(th * 1000.0f));
    }
    static int nl; if (LOGCAP(nl, 80)) xlog("sdodge: puppet slot %u dodge PATH armed: clip root x%.2f = %.2f m at its flat part %.0f ms (SP %.2f m, cut to %.2f m of us: %.2f), dir %d, %.0f ms late", slot, (double)q->k, (double)D, (double)(th * 1000.0f), (double)spe, (double)MDS_SPC_END, (double)lim, dir, (double)age_ms);
}
// melee_duel_tl.c dtl_locator: the path position of slot's dodging puppet now (1 = on); net = its streamed position this frame
static int mdg_pp_pos(int slot, uint64_t now, const float *net, float *px, float *pz, float *yaw_deg) {
    if (slot < 0 || slot >= T2R_MAX_PEERS) return 0;
    typeof(&g_mdg_pp[0]) q = &g_mdg_pp[slot];
    if (!q->on) return 0;
    if (now - q->t0 > q->hold_ms + 60 || g_peer_downed[slot] || psync_busy_slot((uint32_t)slot)) { q->on = 0; return 0; }
    float tr = (float)(now - q->t0) / 1000.0f, tt = q->heavy ? mdg_heavy_tt(tr) : tr; if (tt > q->th) tt = q->th;
    if (q->heavy && tr * 1000.0f < (float)q->hold_ms) dtl_speed_s(q->ent, q->sid, 0.8f, MO_SRC("dodge.pup_heavy"));   // ps46 (see mdg_pp_arm)
    float rx, rz, ry; mdg_rm_at(q->rm, tt, &rx, &rz, &ry);
    if (net) {
        if (!q->n0_ok) { q->n0[0] = net[0]; q->n0[1] = net[2]; q->n0_ok = 1; }
        else if (tt > 0.30f) {    // the stream (the dodger's controller on its own capped path) stays far behind the path = it is walled: shrink toward it
            float tl = q->heavy ? mdg_heavy_tt(tr - 0.15f) : tt - 0.15f; if (tl < 0.0f) tl = 0.0f; if (tl > q->th) tl = q->th;
            float lx, lz, ly; mdg_rm_at(q->rm, tl, &lx, &lz, &ly);
            float pd = q->k * __builtin_sqrtf(lx * lx + lz * lz), nd = __builtin_sqrtf((net[0] - q->n0[0]) * (net[0] - q->n0[0]) + (net[2] - q->n0[1]) * (net[2] - q->n0[1]));
            if (pd > 0.25f && nd < 0.5f * pd) q->k *= 0.94f;
        }
    }
    *px = q->p0[0] + q->k * (rx * -q->fz + rz * q->fx);
    *pz = q->p0[1] + q->k * (rx * q->fx + rz * q->fz);
    *yaw_deg = __builtin_atan2f(q->fx, q->fz) * 57.29578f;   // squared up with the attacker, as the dodger's own body
    return 1;
}
// the dodger's puppet on OUR screen (the attacker's view): its displayed travel + spacing to us, 700 / 1000 ms after its press arrived
static struct { uint64_t t0; int on, got7; float p0[2], spc0, tr7; } g_mds_pup[T2R_MAX_PEERS];
static void mdg_sp_pup_note(uint32_t slot) {
    if (slot >= T2R_MAX_PEERS || mdu_dodge_cap() <= 0.0f) return;
    uint64_t ent = puppet_handle(slot); float pb[16], mb[16]; const float *p = ent ? puppet_locator(ent, pb) : NULL, *l = uc4_my_loc(mb);
    if (!p || !l || !__builtin_isfinite(p[0])) return;
    g_mds_pup[slot].t0 = GetTickCount64(); g_mds_pup[slot].on = 1; g_mds_pup[slot].got7 = 0; g_mds_pup[slot].p0[0] = p[0]; g_mds_pup[slot].p0[1] = p[2];
    g_mds_pup[slot].spc0 = __builtin_sqrtf((p[0] - l[0]) * (p[0] - l[0]) + (p[2] - l[2]) * (p[2] - l[2]));
}
static void mdg_sp_pup_tick(uint64_t now) {
    for (uint32_t s = 0; s < T2R_MAX_PEERS; s++) {
        if (!g_mds_pup[s].on) continue;
        uint64_t el = now - g_mds_pup[s].t0, ent = puppet_handle(s); float pb[16], mb[16];
        const float *p = ent ? puppet_locator(ent, pb) : NULL, *l = uc4_my_loc(mb);
        if (!p || !l || !__builtin_isfinite(p[0]) || el > 3000) { g_mds_pup[s].on = 0; continue; }
        float tr = __builtin_sqrtf((p[0] - g_mds_pup[s].p0[0]) * (p[0] - g_mds_pup[s].p0[0]) + (p[2] - g_mds_pup[s].p0[1]) * (p[2] - g_mds_pup[s].p0[1]));
        if (!g_mds_pup[s].got7 && el >= 700) { g_mds_pup[s].got7 = 1; g_mds_pup[s].tr7 = tr; }
        if (el < 1000) continue;
        g_mds_pup[s].on = 0;
        static int nl; if (LOGCAP(nl, 60)) xlog("sdodge: puppet slot %u (attacker's view) travel %.2f m at 700 ms, %.2f m at 1000 ms after its press arrived (SP: %.2f / %.2f m; the dodger's own line is its sdodge), spacing to us start %.2f end %.2f m",
             s, g_mds_pup[s].tr7, tr, MDS_TRAVEL_M, MDS_SP_END_M, g_mds_pup[s].spc0, __builtin_sqrtf((p[0] - l[0]) * (p[0] - l[0]) + (p[2] - l[2]) * (p[2] - l[2])));
    }
}
// the dodge grunt at SP's time (vox-eff-gen-fight-dodge-* 96-200 ms into the move, median ~157; bp-dodge-hard 118-161 ms is the clip's own event)
static void mdg_dodge_say(uint32_t who, uint64_t ent);
static struct { uint64_t at, ent; uint32_t who; } g_mds_say[T2R_MAX_PEERS + 1];
static void mdg_dodge_say_at(uint32_t who, uint64_t ent, int delay_ms) {
    if (who > T2R_MAX_PEERS) return;
    if (delay_ms <= 0 || mdg_sp_off() || mdu_dodge_cap() <= 0.0f) { mdg_dodge_say(who, ent); return; }
    g_mds_say[who].at = GetTickCount64() + (uint64_t)delay_ms; g_mds_say[who].ent = ent; g_mds_say[who].who = who;
}
static void mdg_dodge_say_tick(uint64_t now) {
    for (int i = 0; i <= T2R_MAX_PEERS; i++) {
        if (!g_mds_say[i].at || now < g_mds_say[i].at) continue;
        g_mds_say[i].at = 0;
        if (i < T2R_MAX_PEERS && (g_peer_downed[i] || g_puppet_dead_here[i] || puppet_handle((uint32_t)i) != g_mds_say[i].ent)) continue;   // (gone / downed since)
        if (i == T2R_MAX_PEERS && (g_downed || local_hp() <= 0.0f)) continue;
        mdg_dodge_say(g_mds_say[i].who, g_mds_say[i].ent);
    }
}
static uint64_t mdu_swing_t0(void);   // melee_duel.c: the start of our running duel swing, 0 = none
static void mdg_mv_end(mdg_mv_t *m, const char *why) {
    if (!m->on) return;
    mdg_sp_report(m, why);
    float mb[16]; const float *l = uc4_my_loc(mb);
    float moved = l ? __builtin_sqrtf((l[0] - m->from[0]) * (l[0] - m->from[0]) + (l[2] - m->from[2]) * (l[2] - m->from[2])) : 0.0f;
    xlog("dodge: %s moved %.2f m of %.2f planned over %llu ms (%s)", m->tag, moved, m->chosen >= 0 && m->chosen < 2 ? m->total[m->chosen] : 0.0f, (unsigned long long)(GetTickCount64() - m->ms0), why);
    m->on = 0;
}
// Fall-through watch (a combat dodge moved 0.80 m "done", and 82 frames later the body died by a fall 5 m under the floor at the
// end spot; another report: "dodged into cover and glitched through it"). While a dodge move runs and for MD_FW_MS after it, a body that sinks more than
// MD_FW_DROP below the press height while still within MD_FW_XZ of where the move left it (straight down = through the floor, not off a ledge:
// the end spot's ground ray found ground there) goes back to the press spot.
#define MD_FW_MS 2500
#define MD_FW_DROP 1.2f
#define MD_FW_XZ 0.35f      // (0.6 m could catch a slow slide off a ledge)
static struct { uint64_t until; float from[4], end[2]; const char *tag; } g_mdfw;
static void mdg_fall_watch(void) {
    if (!g_mdfw.until) return;
    if (GetTickCount64() > g_mdfw.until || match_substate() != 6 || local_hp() <= 0.0f) { g_mdfw.until = 0; return; }
    float lb[16]; const float *l = uc4_my_loc(lb);
    if (!l || !__builtin_isfinite(l[0])) return;
    float dx = l[0] - g_mdfw.end[0], dz = l[2] - g_mdfw.end[1];
    if (dx * dx + dz * dz > MD_FW_XZ * MD_FW_XZ) { g_mdfw.until = 0; return; }   // walked / slid away: not ours any more
    if (l[1] > g_mdfw.from[1] - MD_FW_DROP) return;
    float l8[8] = {g_mdfw.from[0], g_mdfw.from[1] + 0.05f, g_mdfw.from[2], 1.0f, l[4], l[5], l[6], l[7]};
    static psync_bf bf;
    psync_bf_from_loc(&bf, l8);
    mo_write(SID_PLAYER, &bf, MO_SRC("dodge.fall_watch"), 0);
    xlog("dodge: %s fell through the floor at %.2f %.2f %.2f (%.2f m under the press height) - back to the press spot %.2f %.2f %.2f",
         g_mdfw.tag ? g_mdfw.tag : "move", l[0], l[1], l[2], g_mdfw.from[1] - l[1], g_mdfw.from[0], g_mdfw.from[1], g_mdfw.from[2]);
    g_mdfw.until = 0;
}
// ps36 (a failed dodge, outside of the window, has more momentum: slower and more forceful instead of
// an instant momentum in the animation, so it does not look too jarring in a fight if the enemy presses dodge too early): a press with NO swing about to land,
// the duel partner in reach, is the HEAVY dodge - the same SP dodge clip at MDG_HEAVY_RATE, its travel eased in over MDG_HEAVY_RAMP_S (no velocity on frame 1),
// no i-frames (as the whiff dodge), melee / guns locked 550 ms, the full cooldown. Presses during our own wind-up stay ignored. t2r-dodge-heavy-ps35.txt = a
// press outside a window does nothing.
#define MDG_HEAVY_RATE 0.8f       // [TUNING ps36] clip rate of the heavy dodge
#define MDG_HEAVY_RAMP_S 0.15f    // [TUNING ps36] the travel's velocity ramps from 0 over this
static uint64_t g_mdg_heavy_ms;   // the press time of the running heavy dodge (0 = a normal one)
static void dtl_speed_s(uint64_t ent, uint64_t sid, float v, int src);   // melee_duel_tl.c
static void mdg_mv_tick(mdg_mv_t *m) {
    if (m->on && m->stage >= 1) {
        float wb[16]; const float *w = uc4_my_loc(wb);
        if (w && __builtin_isfinite(w[0]) && w[1] > m->from[1] - MD_FW_DROP) {
            memcpy(g_mdfw.from, m->from, 12); g_mdfw.end[0] = w[0]; g_mdfw.end[1] = w[2]; g_mdfw.tag = m->tag; g_mdfw.until = GetTickCount64() + MD_FW_MS;
        }
    }
    if (!m->on) return;
    const char *busy = mdg_busy();
    // (ping 40, log [50808]-[50825]: a buffered combo press started fist-light-attack-2 while the dodge mover still pinned the body - duel.mdu_warp
    // and dodge.pin both wrote it for 14 frames, 0.15-0.36 m per frame back and forth): our own duel swing owns the body from its start, the dodge path ends.
    // ps39 B2 (log [16532]-[16554]: 'motion: own ...: 2 writers [paired.tc_frame 0.02 .. 0.72 m, dodge.pin ...]' on 22 frames, sixteen 'SNAP 0.17-0.81 m' -
    // the dodge was ruled too late, the pin push pair u011a6372 took its body as the victim half, and the dodge's path mover kept writing the same body every
    // frame; [16551] the same against 'pairwall.exit_ease'): one writer - a pair's victim half on us, the pair-exit ease and the wall hand-off own the body, the
    // dodge mover ends (mdg_combat_tick stops its clip). A dodge that leaves a pair ends that pair first, so it is not caught. t2r-dodge-pin-under-pair-ps38.txt = old.
    if (!busy && GetFileAttributesA("t2r-dodge-pin-under-pair-ps38.txt") == INVALID_FILE_ATTRIBUTES)
        busy = g_ps.role == 2 && g_ps.ent_vic == SID_PLAYER ? "a pair's victim half owns the body (ps39: one writer)" : g_pairwall_ez_on ? "the pair-exit ease owns the body (ps39: one writer)"
             : g_wallho.on && g_wallho.drive ? "the wall hand-off owns the body (ps39: one writer)" : NULL;
    if (!busy && m->stage >= 1 && mdu_swing_t0() > m->ms0 && GetFileAttributesA("t2r-dodge-pin-over-swing.txt") == INVALID_FILE_ATTRIBUTES) busy = "our duel swing started (it owns the body)";
    if (busy && m->stage >= 1) { mdg_mv_end(m, busy); return; }
    if (busy) { m->on = 0; return; }
    float lb[16]; const float *l = uc4_my_loc(lb);
    if (!l || !__builtin_isfinite(l[0])) { m->on = 0; return; }
    if (m->stage == 0) {
        if (g_frame <= m->arm_f) return;
        int best = -1; float bcap = 0.0f; char why[256]; int wn = 0; why[0] = 0;
        for (int i = 0; i < m->n; i++) {
            float cap = m->total[i];
            for (int k = 0; k < 2; k++) {
                uint64_t j = m->jw[i][k]; g_ray_err = 0; float r = ray_t(j); m->jw[i][k] = 0;
                wn += snprintf(why + wn, SNLEFT(why, wn), "%s%s%.2f", k ? "/" : i ? " | " : "", !j ? "unkicked:" : g_ray_err ? "err:" : "", r);
                if (!j || g_ray_err) cap = 0.0f;                       // a probe that never ran is not open space
                else if (r >= 0.0f && r < 0.99f) { float room = r * (m->total[i] + 0.4f) - 0.4f; if (room < cap) cap = room; }
            }
            int r35 = GetFileAttributesA("t2r-dodge-rays-ps34.txt") == INVALID_FILE_ATTRIBUTES; float wcap = cap;
            for (int s = 0; s < 2; s++) {                           // ps35: the body-width rays
                uint64_t j = m->jl[i][s]; g_ray_err = 0; float r = j ? ray_t(j) : -1.0f; m->jl[i][s] = 0;
                wn += snprintf(why + wn, SNLEFT(why, wn), " %s%.2f", s ? "R" : "L", r);
                if (r35 && j && !g_ray_err && r >= 0.0f && r < 0.99f) { float room = r * (m->total[i] + 0.4f) - 0.4f; if (room < cap) cap = room; }
            }
            if (cap < 0.0f) cap = 0.0f;
            float rg = ray_t(m->jg[i]); m->jg[i] = 0;
            wn += snprintf(why + wn, SNLEFT(why, wn), " ground %.2f", rg);
            // ps35 (uc5 B [16491] 'no room ... the clip plays in place (walls / ground t: 0.78/0.78 ground 0.03)': both wall rays hit 1.70 m out, 1.30 m of room, but the
            // ground ray at the 1.78 m END spot stood on that very obstacle and zeroed the dodge): an end spot beyond a wall hit is never reached - the wall room
            // decides, the ground test at that spot does not. (No wall hit = the end spot is where we land: the ground test as before.)
            int beyond = r35 && cap < m->total[i] - 0.01f && cap >= 0.12f;
            if (!beyond && (rg < 0.0f || rg > 0.99f || rg < 0.3f || rg > 0.62f)) cap = 0.0f;   // ground +0.15 .. -0.33 m (was +0.3: the body is placed at the press height, a step up put it inside the step)
            if (m->pin && (cap < wcap - 0.01f || beyond)) { static int nl35; if (LOGCAP(nl35, 60)) xlog("dodge: %s room %.2f m of %.2f (centre rays %.2f, body-width rays / end-spot rule: ps35; rays %s)", m->tag, (double)cap, (double)m->total[i], (double)wcap, why); }
            if (cap > bcap) { bcap = cap; best = i; }
        }
        if (best < 0 || bcap < 0.12f) {
            if (!m->pin) { xlog("dodge: %s cancelled - no room / step / drop on any side (walls / ground t: %s)", m->tag, why); m->on = 0; m->chosen = -1; return; }
            xlog("dodge: %s - no room / step / drop on any side: the clip plays in place (pinned, no travel; walls / ground t: %s)", m->tag, why);
            best = 0; bcap = 0.0f;
        }
        m->chosen = best; m->total[best] = bcap; m->stage = 1; m->t60_0 = g_t60; m->sp = 0; m->done = 0; if (!m->pin) memcpy(m->from, l, 12);   // (a pinned move keeps the press position: the clip's own root motion has already moved the body since)
    }
    int c = m->chosen;
    // (the character jumped sideways 1-2 m in one frame at a punch; log [101647]-[101649]: a 1178 ms frame stall, then the whole remaining 0.65 m of the dodge path was
    // written in ONE frame - the path is a function of the wall clock). Virtual path clock: at most 3 ticks per frame, and a stall is caught up at +2 ticks per frame (<= 3x
    // speed), never in one write.
    float real = (float)(g_t60 - m->t60_0);
    if (!m->vt_ok) { m->vt_ok = 1; m->vt = real; m->rl = real; }
    else { float dr = real - m->rl; if (dr < 0) dr = 0; m->rl = real; float base = dr > 3.0f ? 3.0f : dr, lagr = real - (m->vt + base); m->vt += base + (lagr > 0 ? (lagr > 2.0f ? 2.0f : lagr) : 0); if (m->vt > real) m->vt = real; }
    float ve = m->vt;
    float t = ve / (float)(m->dur60 > 0 ? m->dur60 : 12);   // 0.2 s unless the move sets its own travel time
    int last = t >= 1.0f; if (last) t = 1.0f;
    float s = t * t * (3.0f - 2.0f * t);
    if (m->face) {     // dodge curve (as immersive and fluid as possible, instead of abrupt quick movements): a quick push-off that settles - half smoothstep, half ease-out cubic
        float u = 1.0f - t; s = 0.5f * s + 0.5f * (1.0f - u * u * u);
    }
    float ds = (s - m->sp) * m->total[c];
    m->sp = s;
    if (m->stop_on) {                                              // do not walk into the body we carry past
        float dx = m->stop_xz[0] - l[0], dz = m->stop_xz[1] - l[2];
        if (dx * dx + dz * dz < 0.85f * 0.85f && dx * m->dir[c][0] + dz * m->dir[c][1] > 0.0f) { mdg_mv_end(m, "stopped at the other body"); return; }
    }
    if (m->pin) {      // the clip's root motion must not carry the body (it went out of bounds, 2.1 m): every frame the position is OUR path - press position + the collision-checked step - and nothing else
        float px = m->from[0] + m->dir[c][0] * m->total[c] * s, pz = m->from[2] + m->dir[c][1] * m->total[c] * s;
        if (m->rm && m->rm_len > 0.05f) {   // the clip's own root motion, in the frame facing the attacker, scaled down to the room the probes found
            float rx, rz, ry, tt = ve / 60.0f, k = m->total[c] / m->rm_len; if (k > 1.0f) k = 1.0f;
            if (m->heavy) tt = MDG_HEAVY_RATE * (tt < MDG_HEAVY_RAMP_S ? tt * tt / (2.0f * MDG_HEAVY_RAMP_S) : tt - 0.5f * MDG_HEAVY_RAMP_S);   // ps36: the clip's time at its rate, the velocity eased in
            if (m->spm && m->sp_rmh > 0.05f) { k = mdg_sp_travel(m, c) / m->sp_rmh; if (tt > m->sp_th) tt = m->sp_th; }   // SP duel dodge: the clip's curve, sp_D at the hold
            mdg_rm_at(m->rm, tt, &rx, &rz, &ry);
            float lx = -m->rm_fz, lz = m->rm_fx;           // left of forward
            px = m->from[0] + k * (rx * lx + rz * m->rm_fx); pz = m->from[2] + k * (rx * lz + rz * m->rm_fz);
            last = GetTickCount64() >= m->hold_until;
        }
        // This frame's step of the SCALED path (nominal = before the 'moved by someone else' shift below). adelta_hook gives it to the engine instead of the clip's
        // unscaled root step (mdg_pin_adelta), so the controller (and the net stream) follows the path the dodger SEES - no 2.2 m streamed travel, no release-sync teleport.
        {   static uint64_t ms0_; static float pnx, pnz; static int pok_;
            if (ms0_ != m->ms0 || !pok_) { ms0_ = m->ms0; pok_ = 1; g_mdpin.dx = g_mdpin.dz = 0.0f; g_mdpin.n_used = 0; }
            else { g_mdpin.dx = px - pnx; g_mdpin.dz = pz - pnz; }
            pnx = px; pnz = pz; g_mdpin.f = g_frame; g_mdpin.n_set++;
        }
        // Soak test (7x 'dtl: SNAP 0.2-0.5 m in 1 frame ... dodge mover'): the path is absolute from the press spot, so a displacement by anyone else
        // (the hit reaction's push-back, the engine's collision) since our last write was undone in ONE frame. It is kept instead: the path moves with it.
        // t2r-dodge-pin-snap.txt = old.
        {   static int old = -1; static uint64_t oc; if (old < 0 || GetTickCount64() - oc > 3000) { oc = GetTickCount64(); old = GetFileAttributesA("t2r-dodge-pin-snap.txt") != INVALID_FILE_ATTRIBUTES; }
            float ex = m->lw_ok ? l[0] - m->lw[0] : 0.0f, ez = m->lw_ok ? l[2] - m->lw[1] : 0.0f, e2 = ex * ex + ez * ez;
            float fdt = m->lw_ok && g_t60 > m->lw_t60 ? (float)(g_t60 - m->lw_t60) / 60.0f : 1.0f / 60.0f, thr = 0.08f + 5.0f * (fdt > 0.1f ? 0.1f : fdt);   // (above any clip root step: 5 m/s)
            if (!old && e2 > thr * thr && e2 < 1.5f * 1.5f) {
                m->from[0] += ex; m->from[2] += ez; px += ex; pz += ez;
                static int nl_; if (nl_ < 40) { nl_++; xlog("dodge: %s - the body was moved %.2f m by someone else since our last placement: kept (the path moves with it, no snap back)", m->tag, (double)__builtin_sqrtf(e2)); }
            }
            m->lw_ok = 1; m->lw[0] = px; m->lw[1] = pz; m->lw_t60 = g_t60;
        }
        float l8[8] = {px, l[1], pz, 1.0f, l[4], l[5], l[6], l[7]};
        if (m->face) {   // turn to square up with the attacker over the first 40 % of the travel (the SP contextual dodges are authored facing the attacker)
            float k = t / 0.4f; if (k > 1.0f) k = 1.0f; k = k * k * (3.0f - 2.0f * k);
            float dy = m->yaw1 - m->yaw0; while (dy > 3.14159265f) dy -= 6.2831853f; while (dy < -3.14159265f) dy += 6.2831853f;
            float y = m->yaw0 + dy * k;
            l8[4] = 0.0f; l8[5] = __builtin_sinf(0.5f * y); l8[6] = 0.0f; l8[7] = __builtin_cosf(0.5f * y);
        }
        static psync_bf bfp;
        psync_bf_from_loc(&bfp, l8);
        mo_write(SID_PLAYER, &bfp, MO_SRC("dodge.pin"), 0);
        m->done = m->total[c] * s;
        if (last && GetTickCount64() >= m->hold_until) mdg_mv_end(m, "done");
        return;
    }
    if (ds > 0.0005f) {
        float l8[8] = {l[0] + m->dir[c][0] * ds, l[1], l[2] + m->dir[c][1] * ds, 1.0f, l[4], l[5], l[6], l[7]};
        static psync_bf bf;
        psync_bf_from_loc(&bf, l8);
        mo_write(SID_PLAYER, &bf, MO_SRC("dodge.free_move"), 0);
        m->done += ds;
    }
    if (last) mdg_mv_end(m, "done");
}
// ---- room around us while a window is open (in a cramped house dodges went into walls / planks and the camera ended inside them):
// every 4 frames three probes along the attacker -> us axis (left / right / back, knee + chest height, MD_STEP_M + 0.4 m, and ground at the end spot), read one frame
// later. At the press a stick direction with < MD_ROOM_MIN of room is swapped for the freest other one (never toward the blow's side when the side is known).
#define MD_STEP_M 1.0f            // the dodge's travel (the dodger "went 3-4 m past" the attacker; the engine dodge sequence + counter lunge moved ~2.4 m)
#define MD_ROOM_MIN 0.55f
#define MD_DUCK_CAP 0.85f         // SP: dodge-clip travel median 0.86 m. Was 0.7.
// (old)          // a duck dodge (mdg_pick_combat) slides at most this far: the duck is the dodge, not the travel
#define MD_RM_CAP 1.8f            // the authored dodges travel ~2 m (1h back 2.1 m median, some sides 3.5 m): capped here, and by the room
static struct { uint64_t jw[4][2], jg[4], kick_f, ms; float room[4], ax, az; int slot, pend; } g_mdr;
static void mdg_room_dirs(float ax, float az, float d[4][2]) {   // index = dodge dir: 0 forward (at him), 1 left, 2 right, 3 back (away); ax/az = unit attacker -> us
    d[0][0] = -ax; d[0][1] = -az; d[1][0] = az; d[1][1] = -ax; d[2][0] = -az; d[2][1] = ax; d[3][0] = ax; d[3][1] = az;
}
static void mdg_room_probe(int slot) {
    if (g_mdr.pend && g_frame > g_mdr.kick_f) {
        for (int i = 1; i < 4; i++) {
            float total = MD_RM_CAP, cap = total;
            for (int k = 0; k < 2; k++) {
                uint64_t j = g_mdr.jw[i][k]; g_ray_err = 0; float r = ray_t(j); g_mdr.jw[i][k] = 0;
                if (!j || g_ray_err) cap = 0.0f;
                else if (r >= 0.0f && r < 0.99f) { float room = r * (total + 0.4f) - 0.4f; if (room < cap) cap = room; }
            }
            float rg = ray_t(g_mdr.jg[i]); g_mdr.jg[i] = 0;
            if (rg < 0.3f || rg > 0.62f) cap = 0.0f;
            g_mdr.room[i] = cap < 0.0f ? 0.0f : cap;
        }
        g_mdr.pend = 0; g_mdr.ms = GetTickCount64();
    }
    if (g_mdr.pend || slot < 0 || g_frame - g_mdr.kick_f < 4) return;
    float mb[16], pb[16]; const float *ml = uc4_my_loc(mb);
    uint8_t *pe = mdg_peer((uint32_t)slot);
    const float *pl = pe && *(uint64_t *)(pe + 0x60) ? puppet_locator(*(uint64_t *)(pe + 0x60), pb) : NULL;
    if (!ml || !pl || !__builtin_isfinite(ml[0]) || !__builtin_isfinite(pl[0])) return;
    float ax = ml[0] - pl[0], az = ml[2] - pl[2], al = __builtin_sqrtf(ax * ax + az * az);
    if (!(al > 0.05f)) return;
    ax /= al; az /= al;
    float d[4][2]; mdg_room_dirs(ax, az, d);
    for (int i = 1; i < 4; i++) {
        float ux = d[i][0], uz = d[i][1], far_ = MD_RM_CAP + 0.4f;
        float a1[3] = {ml[0], ml[1] + 0.5f, ml[2]}, b1[3] = {ml[0] + ux * far_, ml[1] + 0.5f, ml[2] + uz * far_};
        float a2[3] = {ml[0], ml[1] + 1.0f, ml[2]}, b2[3] = {b1[0], ml[1] + 1.0f, b1[2]};
        float c1[3] = {ml[0] + ux * MD_RM_CAP, ml[1] + 0.6f, ml[2] + uz * MD_RM_CAP}, e1[3] = {c1[0], ml[1] - 0.9f, c1[2]};
        g_mdr.jw[i][0] = world_ray_kick_m(a1, b1, 0, 0x1b07); g_mdr.jw[i][1] = world_ray_kick_m(a2, b2, 0, 0x1b07); g_mdr.jg[i] = world_ray_kick_m(c1, e1, 0, 0x1b07);   // (grass, see mdg_mv)
    }
    g_mdr.ax = ax; g_mdr.az = az; g_mdr.slot = slot; g_mdr.kick_f = g_frame; g_mdr.pend = 1;
}
// ---- the attacker: announce, longer windup
// The incoming blow's angle class (0 horizontal hook, 1 downward overhand, 2 upward) and striking hand (0 left, 1 right) from the swing's weapon: unarmed fists throw hooks,
// alternating hands (left jab / right cross ...), an upward one every third; a held melee weapon swings down (even) / across (odd). HEURISTIC: every swing logs its move + clip sid
// ("dodge: swing class") so the table can be made exact from the next A/B.
// move -> striking hand table (0 left, 1 right): FILL from the "dodge: swing class" log lines (move ids of fists / weapon swings). Until a move is in it the hand is a guess and is
// sent WITHOUT the "real" bit (hand byte bit 1), so receivers do not judge a sideways dodge as "into the blow" from it.
static const struct { uint64_t move; uint8_t hand; } MDG_HAND_TABLE[] = { {0, 0} };
static int mdg_move_hand(uint64_t move, uint8_t *hand) {
    for (size_t i = 0; i < sizeof MDG_HAND_TABLE / sizeof MDG_HAND_TABLE[0]; i++) if (MDG_HAND_TABLE[i].move && MDG_HAND_TABLE[i].move == move) { *hand = MDG_HAND_TABLE[i].hand; return 1; }
    return 0;
}
// Most dodges did not look like actual dodges (the right dodge is needed for the right occasion): the class / hand
// sent with MSG_DODGE_SWING was a COUNTER (n % 3 upward, n & 1 the hand) - the victim's contextual dodge (angle + side) never matched the swing. The class is
// now MEASURED per DUEL ROW (mduel_moves.h: fist-light-attack-1 / -2 / ... - the engine's melee move id is the same for every combo step, dev20 showed
// 43b365acc522c6db for attack-1, attack-2 and the dodge attack) from the hand joints of the swinging body in ITS OWN frame (hand - root, rotated by the body's
// yaw, so the lunge's root motion drops out): our own swings (SID_PLAYER, melee_duel.c mdu_swing_note) and the partner's replica swings on its puppet (the
// SWING message names the row). Striking hand = the larger forward speed in the row's windup (up to its contact + 60 ms, at most MDL_WIN_MS); angle = that hand's
// vertical speed over its forward speed at its fastest point (> MDL_ANG upward, < -MDL_ANG downward, else horizontal; TUNING: MDL_ANG). Learned once per row per
// session; the pick (mdg_pick_combat) takes the row's measured class over the announced guess. t2r-no-swing-learn.txt = the old counter.
#define MDL_N 48
#define MDL_WIN_MS 600
#define MDL_ANG 0.45f
static struct { int row; uint8_t cls, hand, ok; } g_mdl[MDL_N]; static int g_mdl_n;
static struct { int row, slot, tc; uint64_t ent, t0, last_ms; int n, done; float maxfw[2], vyat[2], fwat[2]; float last[2][3]; } g_mdl_cur[2];   // [0] our swing, [1] a puppet's
static int gx_joint_pos(uint64_t h, const char *joint, float *out);   // t2r-ext.c
static const char *mdu_row_name(int row);   // melee_duel.c
static int mdl_off(void) { static int v = -1; static uint64_t at; uint64_t n = GetTickCount64(); if (v < 0 || n - at > 3000) { at = n; v = GetFileAttributesA("t2r-no-swing-learn.txt") != INVALID_FILE_ATTRIBUTES; } return v; }
static int mdl_row_lookup(int row, uint8_t *cls, uint8_t *hand) {
    if (row < 0) return 0;
    for (int i = 0; i < g_mdl_n; i++) if (g_mdl[i].row == row && g_mdl[i].ok) { *cls = g_mdl[i].cls; *hand = g_mdl[i].hand; return 1; }
    return 0;
}
// melee_duel.c: a duel row's swing starts on `ent` (SID_PLAYER = ours, slot -1; a puppet = the partner's replica, its slot); tc = the row's contact ms
static void mdl_begin_row(int row, uint64_t ent, int slot, int tc) {
    if (mdl_off() || row < 0 || !ent || ent == ~0ULL) return;
    uint8_t c, h; if (mdl_row_lookup(row, &c, &h)) return;              // known already
    typeof(&g_mdl_cur[0]) m = &g_mdl_cur[ent == SID_PLAYER ? 0 : 1];
    memset(m, 0, sizeof *m);
    m->row = row; m->slot = slot; m->ent = ent; m->t0 = GetTickCount64(); m->tc = tc;
}
static void mdl_tick(uint64_t now) {
    static const char *const J[2] = {"l_hand_prop_attachment", "r_hand_prop_attachment"};
    for (int k = 0; k < 2; k++) {
        typeof(&g_mdl_cur[0]) m = &g_mdl_cur[k];
        if (!m->ent || m->done) continue;
        int win = m->tc > 0 && m->tc + 60 < MDL_WIN_MS ? m->tc + 60 : MDL_WIN_MS;
        if (now - m->t0 <= (uint64_t)win) {
            float lb[16]; const float *l = k == 0 ? uc4_my_loc(lb) : puppet_locator(m->ent, lb);
            if (!l || !__builtin_isfinite(l[0])) continue;
            float fx = 2.0f * (l[4] * l[6] + l[7] * l[5]), fz = 1.0f - 2.0f * (l[4] * l[4] + l[5] * l[5]), fl = __builtin_sqrtf(fx * fx + fz * fz);
            if (!(fl > 1e-3f)) continue;
            fx /= fl; fz /= fl;
            float p[2][3]; int ok = 1;
            for (int i = 0; i < 2 && ok; i++) {
                float w[3]; if (!gx_joint_pos(m->ent, J[i], w)) { ok = 0; break; }
                float dx = w[0] - l[0], dz = w[2] - l[2];
                p[i][0] = dx * fz - dz * fx;             // body right
                p[i][1] = w[1] - l[1];                   // up
                p[i][2] = dx * fx + dz * fz;             // body forward
            }
            if (!ok) continue;
            if (m->n == 0) { memcpy(m->last, p, sizeof p); m->last_ms = now; m->n = 1; continue; }
            float dt = (float)(now - m->last_ms) / 1000.0f;
            if (dt < 0.008f) continue;
            int bad = 0;
            for (int i = 0; i < 2; i++) {
                float vfw = (p[i][2] - m->last[i][2]) / dt, vy = (p[i][1] - m->last[i][1]) / dt;
                if (__builtin_fabsf(p[i][2] - m->last[i][2]) > 1.0f) { bad = 1; break; }   // a teleport / re-place, not a swing
                if (vfw > m->maxfw[i]) { m->maxfw[i] = vfw; m->vyat[i] = vy; m->fwat[i] = vfw; }
            }
            memcpy(m->last, p, sizeof p); m->last_ms = now; if (!bad) m->n++;
            continue;
        }
        m->done = 1;
        const char *rn = mdu_row_name(m->row);
        if (m->n < 6 || !(m->maxfw[0] > 1.5f || m->maxfw[1] > 1.5f)) { xlog("dodge: swing class of %s not learned on %s (%d samples, hand speeds L %.1f / R %.1f m/s in the body frame)", rn, k ? "the puppet" : "us", m->n, (double)m->maxfw[0], (double)m->maxfw[1]); m->ent = 0; continue; }
        int hand = m->maxfw[1] >= m->maxfw[0] ? 1 : 0;        // 0 left, 1 right
        float ratio = m->fwat[hand] > 0.1f ? m->vyat[hand] / m->fwat[hand] : 0.0f;
        uint8_t cls = ratio > MDL_ANG ? 2 : ratio < -MDL_ANG ? 1 : 0;   // 0 horizontal, 1 downward, 2 upward
        int i; for (i = 0; i < g_mdl_n; i++) if (g_mdl[i].row == m->row) break;
        if (i == g_mdl_n && g_mdl_n < MDL_N) g_mdl_n++;
        if (i < MDL_N) { g_mdl[i].row = m->row; g_mdl[i].cls = cls; g_mdl[i].hand = (uint8_t)hand; g_mdl[i].ok = 1; }
        xlog("dodge: swing class LEARNED for %s on %s: %s hand, %s (body-frame hand forward speeds L %.1f / R %.1f m/s, vertical / forward %.2f at the fastest point, %d samples)",
             rn, k ? "the puppet" : "us", hand ? "right" : "left", cls == 2 ? "upward" : cls == 1 ? "downward" : "horizontal", (double)m->maxfw[0], (double)m->maxfw[1], (double)ratio, m->n);
        m->ent = 0;
    }
}
static void mdg_swing_class(uint64_t move, uint8_t *cls, uint8_t *hand) {
    static unsigned n; n++;
    uint64_t none = 0, has = dc_call(SID_HAS_MELEE_WEAPON, 0, &none);
    int armed = has != ~0ULL && (has & 0xff);
    *hand = (uint8_t)(n & 1);
    int real = mdg_move_hand(move, hand);
    *cls = armed ? (uint8_t)(n % 2 == 0 ? 1 : 0) : (uint8_t)(n % 3 == 0 ? 2 : 0);
    if (real) *hand |= 2;
    static int nl; if (LOGCAP(nl, 60)) xlog("dodge: swing class %s hand %s%s (%s; move %llx clip %llx)", *cls == 1 ? "downward" : *cls == 2 ? "upward" : "horizontal", (*hand & 1) ? "right" : "left", real ? "" : " (guess)", armed ? "weapon" : "fists", (unsigned long long)move, (unsigned long long)mstag_clip_of(move));
}
static void mdg_swing_note(int started, uint64_t move) {
    if (!started || !move || mdg_off() || mdg_busy() || g_ms.active || !g_send_tramp) return;
    if (mv3_stand_me("dodge: our swing announce + windup tell")) return;     // melee v3: the sim's MV3_E_SWING is the announce (inputs on the wire)
    uint64_t me = SID_PLAYER, r = dc_call(SID_IN_MELEE_ATTACK, 1, &me);
    if (r == ~0ULL || !(r & 0xff)) return;
    uint8_t *rec = (uint8_t *)((fn_lookup)VMA(0x18000A190))(move);
    uint8_t *def = rec && !IsBadReadPtr(rec, 16) ? *(uint8_t **)(rec + 8) : NULL;
    uint64_t macro = def && !IsBadReadPtr(def, 0x20) ? *(uint64_t *)(def + 0x10) : 0;
    if (macro && macro != fnv64("melee-player-swing-free")) return;       // finishers / synced / paired / dodges themselves
    if (mdg_is_dodge_move(move)) return;
    uint64_t now = GetTickCount64();
    g_mdg.my_swing_ms = now; g_mdg.my_swing_sprint = bp_own_speed() >= OWN_SPRINT_MPS;
    uint8_t b[3] = {(uint8_t)(g_upgrade_armed > 0 ? 1 : 0), 0, 0};
    mdg_swing_class(move, &b[1], &b[2]);
    g_send_tramp(MSG_DODGE_SWING, b, 3, 0xff);
    mtell_cue(T2R_MAX_PEERS, SID_PLAYER, mex_wcls() >= 2, "our swing");       // melee_tell.c: swish + effort grunt at the swing start, same cue the peers play on our puppet
    // longer windup: only with a standing enemy in front within reach (nothing to be fair to otherwise)
    float mb[16]; const float *ml = uc4_my_loc(mb);
    if (!ml) return;
    float fx = 2.0f * (ml[4] * ml[6] + ml[7] * ml[5]), fz = 1.0f - 2.0f * (ml[4] * ml[4] + ml[5] * ml[5]);
    int near_ = 0;
    for (uint32_t s = 0; s < T2R_MAX_PEERS && !near_; s++) {
        uint8_t *pe = mdg_peer(s);
        if (!pe || !pe[0x4c] || pe[0x4d] || !*(uint64_t *)(pe + 0x60) || is_teammate(s) || g_peer_downed[s] || g_puppet_dead_here[s]) continue;
        float pb[16]; const float *pl = puppet_locator(*(uint64_t *)(pe + 0x60), pb);
        if (!pl || !__builtin_isfinite(pl[0])) continue;
        float dx = pl[0] - ml[0], dz = pl[2] - ml[2], d = __builtin_sqrtf(dx * dx + dz * dz);
        if (d < MD_REACH + 0.5f && d > 0.05f && (dx * fx + dz * fz) / d > 0.5f) near_ = 1;
    }
    uint64_t clip = near_ ? mstag_clip_of(move) : 0;
    if (!clip) return;
    int wc_ = mex_wcls();
    float tsp = mtell_speed(wc_, mex_tc_raw(wc_));      // melee_tell.c: tell on = the windup is SPED UP so contact lands at the tell (0 = tell off: the old x0.65)
    if (tsp > 0.0f) {
        if (tsp > 1.001f) { mstag_speed(clip, tsp); g_mdg.ext_on = 1; g_mdg.ext_clip = clip; g_mdg.ext_move = move; g_mdg.ext_until = now + (uint64_t)g_mtl.tell_ms; }
        static int nt; if (LOGCAP(nt, 60)) xlog("tell: swing windup x%.2f for %d ms (class %d, contact target %d ms after the start; the old x%.2f slow-down is off)", (double)tsp, g_mtl.tell_ms, wc_, g_mtl.tell_ms, (double)MD_EXT_SPEED);
        return;
    }
    if (mv2_on()) return;                                   // melee v2: SP windup speed
    mstag_speed(clip, MD_EXT_SPEED);
    g_mdg.ext_on = 1; g_mdg.ext_clip = clip; g_mdg.ext_move = move; g_mdg.ext_until = now + MD_EXT_MS;
    static int nl; if (LOGCAP(nl, 40)) xlog("dodge: swing announced (move %llx, %s), windup at x%.2f for %d ms (the dodge window is ~%d ms longer)", (unsigned long long)move, b[0] ? "one-shot armed" : "plain", MD_EXT_SPEED, MD_EXT_MS,
                                              (int)((1.0f / MD_EXT_SPEED - 1.0f) * MD_EXT_MS + 0.5f));
}
static int npcw_recv(uint32_t slot, const uint8_t *buf, uint64_t len);   // melee_npcwind.c
static void mdg_recv_swing(uint32_t slot, const uint8_t *buf, uint64_t len) {
    if (slot >= T2R_MAX_PEERS || slot == *(uint32_t *)VMA(0x180138090) || mdg_off()) return;
    if (mv3_stand("dodge: peer swing announce", slot)) return;                 // melee v3: a bubble member's swing is in our sim already
    if (npcw_recv(slot, buf, len)) return;           // melee_npcwind.c: an NPC windup tell (kind bit 7), not a swing yet
    if (mex_swing_msg(slot, buf, len)) return;       // a swing of a melee exchange: its time is the shared clock's, not this message's arrival
    { uint8_t *pe_ = mdg_peer(slot); if (pe_ && pe_[0x4c] && !is_teammate(slot)) mtell_cue(slot, puppet_handle(slot), 0, "peer free swing"); }   // melee_tell.c: the same cue on the swinger's puppet
    g_mdg.sw[slot].ms = GetTickCount64(); g_mdg.sw[slot].open_ms = 0; g_mdg.sw[slot].seq = ++g_mdg.seq_n; g_mdg.sw[slot].kind = len >= 1 && buf ? (buf[0] & 1) : 0; g_mdg.sw[slot].cls = len >= 2 && buf && buf[1] < 3 ? buf[1] : 0; g_mdg.sw[slot].hand = len >= 3 && buf ? (buf[2] & 1) : 0; g_mdg.sw[slot].hand_real = len >= 3 && buf ? (buf[2] >> 1) & 1 : 0;
}
// ---- the verdicts (victim side)
static int mdg_iframes(uint64_t now) { return g_mdg.iframe_until && now >= g_mdg.press_ms && now <= g_mdg.iframe_until; }
static int mdg_recent_swing(uint64_t now, uint32_t only, uint64_t within) {
    for (uint32_t s = 0; s < T2R_MAX_PEERS; s++) if ((only >= T2R_MAX_PEERS || s == only) && g_mdg.sw[s].ms && now - g_mdg.sw[s].ms <= within && !is_teammate(s)) return 1;
    return 0;
}
static void mdg_send_res(void) { if (g_send_tramp) g_send_tramp(MSG_DODGE_RES, (uint8_t[1]){0}, 1, 0xff); }
// [1][dodger slot]: the ATTACKER decided the dodge on its side (mdg_contact_dodged) - only that dodger arms its counter (old clients read byte 0 only and ignore it: 0 is the old meaning)
static void mdg_send_res_atk(uint32_t dodger) { if (g_send_tramp) g_send_tramp(MSG_DODGE_RES, (uint8_t[2]){1, (uint8_t)dodger}, 2, 0xff); }
// recv_hit_hook: 1 = the blow is dodged (dropped)
static int mdg_slot_of_obj(uint64_t obj) {
    for (uint32_t s = 0; s < T2R_MAX_PEERS; s++) {
        uint8_t *pe = mdg_peer(s);
        uint64_t ph = pe ? *(uint64_t *)(pe + 0x60) : 0;
        uint8_t *pp = ph ? ((uint8_t *(*)(uint64_t))VMA(0x18000A200))(ph) : NULL;
        if (pp && (uint64_t)(uintptr_t)pp == obj) return (int)s;
    }
    return -1;
}
static int mdg_is_thrown(uint64_t w) {
    static const char *const TH[] = {"brick", "bottle", "pipe-bomb", "molotov", "smoke-bomb", "stun-bomb", "nail-bomb", "thrown-brick", "thrown-bottle", "brick-throw", "bottle-throw"};
    for (size_t i = 0; i < sizeof TH / sizeof TH[0]; i++) if (fnv64_rt(TH[i]) == w) return 1;
    return 0;
}
static uint64_t recv_hit_hook(uint64_t me, uint64_t att, uint64_t w, uint64_t ammo, float dmg, uint8_t flag);
static int mdh_off(void) {
    static int off = -1; static uint64_t at; uint64_t now = GetTickCount64();
    if (off < 0 || now - at >= 2000) { at = now ? now : 1; int o = GetFileAttributesA("t2r-no-dodge-grace.txt") != INVALID_FILE_ATTRIBUTES; if (o != off) xlog("dodge: late-press grace %s", o ? "OFF (t2r-no-dodge-grace.txt)" : "on (a melee blow arriving in an open window waits 60-180 ms = one-way + playout for the dodge press)"); off = o; }
    return off;
}
// recv_hit_hook: 1 = the blow is held (its application is replayed by mdg_held_tick; the reliable-hit ack already went out)
static int mdg_partner_ruled(uint32_t from);   // (ps23, below)
static int mdg_hit_hold(uint64_t me, uint64_t att, uint64_t w, uint64_t ammo, float dmg, uint8_t flag) {
    if (g_mdh_replay || g_mdh.on || !(dmg > 0.0f) || dmg >= 200.0f || mdg_off() || mdh_off() || !mhs_is_blow(w) || mdg_is_thrown(w)) return 0;
    uint64_t now = GetTickCount64();
    if (mdg_iframes(now) || mdg_busy() || mdg_own_swing_blocks(now) || now < g_mdg.cooldown_until || now < g_mdg.miss_until || dc_esc_open(now)) return 0;
    int as = mdg_slot_of_obj(att);
    if (as < 0 || (uint32_t)as >= T2R_MAX_PEERS || is_teammate((uint32_t)as)) return 0;
    if (bq_hit_forced((uint32_t)as)) return 0;                                      // melee_beat.c: the duel owner ruled this blow a HIT - no late-press grace
    if (mdg_partner_ruled((uint32_t)as)) return 0;                                  // ps23: our duel partner's contact ruled it a HIT - no late-press grace either (one ruler)
    uint64_t wm; if (mdg_window(now, &wm) != as) return 0;                         // only a blow of the swing whose window is open right now
    float ow = psync_oneway(as); if (!(ow > 0.0f) || ow > 250.0f) ow = 40.0f;
    float po = g_ns[as].dcur > 0.0 ? (float)g_ns[as].dcur : 40.0f; if (po > 150.0f) po = 150.0f;
    // melee stays client-side (live log: "held 188 ms (grace 180) -> applied"): the swing had visibly connected on our screen and the
    // reaction / sound waited up to 180 ms more for a press that never came. Capped at 90 ms (40 min) - challenging, not so forgiving.
    int g = (int)(ow + po + 0.5f); if (g < 40) g = 40; if (g > 90) g = 90;
    g_mdh.on = 1; g_mdh.slot = (uint32_t)as; g_mdh.me = me; g_mdh.att = att; g_mdh.w = w; g_mdh.ammo = ammo; g_mdh.dmg = dmg; g_mdh.flag = flag; g_mdh.grace = g;
    g_mdh.t0 = now; g_mdh.until = now + (uint64_t)g;
    return 1;
}
static void mdg_held_tick(uint64_t now) {
    if (!g_mdh.on) return;
    int pressed = g_mdg.press_ms >= g_mdh.t0 && mdg_iframes(now);
    int gone = match_substate() != 6 || mdg_off();
    if (!pressed && !gone && now < g_mdh.until && !mdg_busy()) return;
    typeof(g_mdh) h = g_mdh; g_mdh.on = 0;
    if (gone) return;
    uint8_t *pe = mdg_peer(h.slot); uint64_t ph = pe ? *(uint64_t *)(pe + 0x60) : 0;
    uint8_t *pp = ph ? ((uint8_t *(*)(uint64_t))VMA(0x18000A200))(ph) : NULL;
    uint64_t att = pp ? (uint64_t)(uintptr_t)pp : h.att;                         // the puppet may have moved in the heap while the blow waited
    int before = g_mdg.dodged_hits;
    g_mdh_replay = 1; g_last_hit_slot = h.slot;
    recv_hit_hook(h.me, att, h.w, h.ammo, h.dmg, h.flag);
    g_mdh_replay = 0;
    xlog("dodge: blow from slot %u held %llu ms (grace %d) -> %s", h.slot, (unsigned long long)(now - h.t0), h.grace, g_mdg.dodged_hits != before ? "dodged" : pressed ? "applied (press did not cover it)" : "applied");
}
static uint64_t g_mdu_late_rx[T2R_MAX_PEERS];   // melee_duel.c MDUO_LATE: when the attacker in that slot ruled our press TOO LATE
static uint64_t g_mdg_late_ms;   // A blow / pair START accepted under the TOO LATE rule (no dodge clip after it)
static uint64_t g_mdg_ok_ms;     // ps23: when the current press dropped a blow / a pair START, or the attacker told us it did (mdg_recv_res)
// ps36 (our rule, not SP; log [12039] / [15866] '(cooldown) - nothing happens ... blow pending': a dodge that WORKED cost its last
// charge = 1500 ms, the missed attacker is free after 650 ms and its next contact came inside that cooldown - even a successful dodge was followed by a hit):
// a dodge that dropped a blow costs nothing - free again at its own lock (MD_GUN_LOCK_MS), no charge, no shorter streak window. Only a dodge that dropped nothing
// (ruled at press + MD_FAIL_CD_MS, mdg_tick) pays MD_COOLDOWN_MS. i-frames unchanged. t2r-dodge-cd-ps35.txt = the ps35 charges / cooldown.
static int mdg_cd36(void) { static int v = -1; static uint64_t at; uint64_t n = GetTickCount64(); if (v < 0 || n - at > 3000) { at = n; v = GetFileAttributesA("t2r-dodge-cd-ps35.txt") == INVALID_FILE_ATTRIBUTES; } return v; }
static void mdg_ok_note(uint64_t now) {
    g_mdg_ok_ms = now; if (!mdg_cd36() || !g_mdg.press_ms) return;
    uint64_t fr = g_mdg.press_ms + MD_GUN_LOCK_MS;
    if (g_mdg.cooldown_until > fr) { xlog("dodge: the dodge worked (a blow dropped %llu ms after the press) - no cooldown: free again %lld ms from now (ps36)", (unsigned long long)(now - g_mdg.press_ms), (long long)(fr > now ? fr - now : 0)); g_mdg.cooldown_until = fr; g_mdg.bar_t0 = 0; }
}
// ps23 (log [19140] / [14682]: the attacker ruled DODGED at 94 ms - its limit is 70 - and this client ruled the same press TOO LATE at
// '~101 ms' - its limit is 120 minus a round trip estimate): inside a duel the attacker's contact is the only ruler. A blow / pair START of our duel partner that
// reaches us was ruled a HIT there (a DODGED ruling sends neither), so it lands; our own estimate no longer decides it. t2r-dodge-vic-ruler-old.txt = old.
static int mdg_partner_ruled(uint32_t from) {
    static int old = -1; static uint64_t at; uint64_t n = GetTickCount64();
    if (old < 0 || n - at > 3000) { at = n; old = GetFileAttributesA("t2r-dodge-vic-ruler-old.txt") != INVALID_FILE_ATTRIBUTES; }
    return !old && mdu_engaged() && mdu_partner_slot() == (int)from;
}
// ps56 (a counter did not land even though the prompt appeared after a dodge: no damage or hit
// reaction; log [90108] counter armed, [90120] the counter swing, [90123] 'ps49 slot 3 pressed 352 ms before our contact - immune to it', [90134] MISS): the player
// whose blow was just dodged dodged the counter too. A dodge counter cannot be dodged: the countering side drops the dodged attacker's i-frames from the counter
// press (g_md56_ctr_ms, set in dcounter.c dc_swing_start), and the dodged attacker's own dodge never drops a blow / refuses a pair START from the player who just
// dodged it (g_md56_dodged_ms, set in mdg_attacker_missed). t2r-dc-dodgeable.txt = old (re-read every 2 s).
static uint64_t g_md56_ctr_ms[T2R_MAX_PEERS], g_md56_dodged_ms[T2R_MAX_PEERS];
#define MD56_CTR_MS 1800             // the counter press -> its blow / pair START (haymaker intro + contact 0.53 s, duel route contact <= 666 ms, + latency)
#define MD56_DODGED_MS 1600          // our dodged blow -> the counter's blow: press window +734 ms + its contact (<= 666 ms) + latency; a fresh swing after the window contacts later (dodgeable)
static int md56_off(void) { static int v = -1; static uint64_t at; uint64_t n = GetTickCount64(); if (v < 0 || n - at > 2000) { at = n; v = GetFileAttributesA("t2r-dc-dodgeable.txt") != INVALID_FILE_ATTRIBUTES; } return v; }
static int md56_window_from(uint32_t from, uint64_t now) { return from < T2R_MAX_PEERS && !md56_off() && g_md56_dodged_ms[from] && now - g_md56_dodged_ms[from] < MD56_DODGED_MS; }
// (a report: melee was still hitting even after dodging; in a clip the punch looked dodged, then the kick finisher downed them): player A [170479] 'PRESS 234 ms
// into slot 1's swing (window 480 ms)', [170487] 'ps56 pair START from slot 1 inside our i-frames accepted - its dodge counter (it dodged our blow 1219 ms ago)' cut the
// dodge clip after 62 ms; player B's log has no dcounter line - its press came ~0.8 s after its dodge (counter window 0.6 s): a plain fist-light-attack-1. ps56 ruled by
// time alone (any blow from the player who dodged us < MD56_DODGED_MS ago). Now only a real counter is undodgeable: its pair START is a counter pair (dc- / pe- rows,
// the duel route's <dodge-attack>-hit pair) or its duel SWING named a dodge-attack row (md56_note_swing, melee_duel.c). A known counter swing opens no dodge window
// and a dodge press while it is in flight is dropped - no dodge clip that the blow then cuts. t2r-md56-time-only.txt = the old time rule.
static uint64_t g_md56_ctrsw_ms[T2R_MAX_PEERS];   // that slot's last duel SWING was a dodge-attack row (its arrival; 0 = a plain swing)
#define MD56_CTRSW_MS 1200            // the counter's SWING -> its blow (contact <= 666 ms + one-way + the -hit pair's START)
static int md56_time_only(void) { static int v = -1; static uint64_t at; uint64_t n = GetTickCount64(); if (v < 0 || n - at > 2000) { at = n; v = GetFileAttributesA("t2r-md56-time-only.txt") != INVALID_FILE_ATTRIBUTES; } return v; }
static int md56_ctr_name(const char *n) { return n && (!strncmp(n, "dc-", 3) || !strncmp(n, "pe-", 3) || (strstr(n, "dodge-") && strstr(n, "attack"))); }
static int md56_ctr_swing(uint32_t s, uint64_t now) { return s < T2R_MAX_PEERS && g_md56_ctrsw_ms[s] && now - g_md56_ctrsw_ms[s] < MD56_CTRSW_MS; }
static void md56_note_swing(uint32_t s, const char *move, uint64_t now) {
    if (s >= T2R_MAX_PEERS) return;
    int c = md56_ctr_name(move);
    g_md56_ctrsw_ms[s] = c ? now : 0;
    if (c) { static int nl; if (LOGCAP(nl, 40)) xlog("dodge: ps56 slot %u's SWING %s is a dodge counter%s", s, move, md56_window_from(s, now) ? " (it dodged our blow) - undodgeable, no dodge window for it" : " (not after dodging our blow - dodgeable)"); }
}
static int md56_counter_from(uint32_t from, uint64_t now) { return md56_window_from(from, now) && (md56_time_only() || md56_ctr_swing(from, now)); }
static int md56_counter_pair(uint32_t from, uint64_t now, const char *pair) { return md56_window_from(from, now) && (md56_time_only() || md56_ctr_swing(from, now) || md56_ctr_name(pair)); }
static int md56_ctr_inflight(uint64_t now, int *slot) {   // a counter swing on us whose blow has not landed yet
    if (md56_time_only()) return 0;
    for (uint32_t s = 0; s < T2R_MAX_PEERS; s++)
        if (md56_ctr_swing(s, now) && md56_window_from(s, now) && g_mdg.sw[s].landed_ms < g_md56_ctrsw_ms[s]) { if (slot) *slot = (int)s; return 1; }
    return 0;
}

// (brawl clips: 234660 own DODGE press, i-frames 365 ms, 234692 "dodger free again (391 ms ...)", 234721 "hit received ... dmg 25" from a plain swing while the dodge clip still
// ran (released 891 ms); the reaction was only the additive gesture): the dodged body is still travelling after its i-frames end - a plain blow that lands on it then must not hurt (SP: the
// dodge's body is out of reach until it stops). The plain-hit gate (mdg_hit_dodged) keeps its immunity until the combat-dodge clip has landed (cmb_land_ms), same rules otherwise.
// t2r-dodge-travel-immune-off.txt = the i-frames only.
static int mdg_travel_immune(uint64_t now) {
    static int off = -1; static uint64_t at;
    if (off < 0 || now - at > 2000) { at = now; off = GetFileAttributesA("t2r-dodge-travel-immune-off.txt") != INVALID_FILE_ATTRIBUTES; }
    return !off && g_mdg.iframe_until && g_mdg.press_ms && g_mdg.cmb_on && g_mdg.cmb_ms >= g_mdg.press_ms && now >= g_mdg.press_ms && now - g_mdg.cmb_ms < g_mdg.cmb_land_ms;
}
static int mdg_hit_dodged(uint64_t att, uint64_t w, float dmg) {
    mdgt_note_blow(w, dmg);
    if (dmg > 0.0f && dmg < 100000.0f && mhs_is_blow(w) && !mdg_is_thrown(w)) { int ls = mdg_slot_of_obj(att); if (ls >= 0 && (uint32_t)ls < T2R_MAX_PEERS) g_mdg.sw[ls].landed_ms = GetTickCount64(); }   // window of that swing is over (also a blow arriving inside the i-frames)
    if (!(dmg > 0.0f) || dmg >= 100000.0f || !g_mdg.iframe_until || mdg_off()) return 0;
    uint64_t now = GetTickCount64();
    int trv11 = !mdg_iframes(now) && mdg_travel_immune(now);
    if ((!mdg_iframes(now) && !trv11) || !mhs_is_blow(w) || mdg_is_thrown(w)) return 0;
    // only the blow of the attacker whose announced swing opened this dodge's window, from a body in melee reach (a bullet / thrown item / other player's hit is never dodged)
    int as = mdg_slot_of_obj(att);
    if (as < 0) as = g_mdg.last_slot;                                          // the attacker object did not resolve (heap move): the window's slot, if its swing is recent
    if (as < 0 || (uint32_t)as >= T2R_MAX_PEERS || !mdg_recent_swing(now, (uint32_t)as, 1600)) return 0;
    if (as != g_mdg.last_slot && mdg_slot_of_obj(att) >= 0) return 0;
    if (md56_counter_from((uint32_t)as, now)) { xlog("dodge: ps56 blow from slot %d inside our i-frames lands - its dodge counter (it dodged our blow %llu ms ago; a counter cannot be dodged)", as, (unsigned long long)(now - g_md56_dodged_ms[as])); return 0; }
    if (md56_window_from((uint32_t)as, now)) xlog("dodge: ps56 blow from slot %d %llu ms after it dodged our blow - NOT a counter (its swing named no dodge attack): dodgeable", as, (unsigned long long)(now - g_md56_dodged_ms[as]));
    if (bq_hit_forced((uint32_t)as)) { xlog("beat: blow from slot %d inside our i-frames NOT dropped - the duel owner ruled it a HIT", as); return 0; }
    if (mdg_partner_ruled((uint32_t)as)) { static int nlp; if (LOGCAP(nlp, 60)) xlog("dodge: blow from our duel partner slot %d inside our i-frames (%llu ms after the press) lands - its contact ruled it a HIT (one ruler; ps23)", as, (unsigned long long)(now - g_mdg.press_ms)); g_mdg_late_ms = now; return 0; }
    {   uint8_t *pe = mdg_peer((uint32_t)as); float pb[16], mb[16];
        const float *pl = pe && *(uint64_t *)(pe + 0x60) ? puppet_locator(*(uint64_t *)(pe + 0x60), pb) : NULL, *ml = uc4_my_loc(mb);
        if (pl && ml) { float dx = pl[0] - ml[0], dz = pl[2] - ml[2]; if (dx * dx + dz * dz > MHS_REACH * MHS_REACH) return 0; } }
    // lag fairness (a hit that visibly connected was followed by a counter on the attacker): the blow reaches us ~half an RTT after it
    // connected on the attacker's screen. A press made after that moment came after the hit the attacker already saw (kick, sound) - it is not a dodge.
    {   float lag = g_ps_rtt[as] > 0.0f ? g_ps_rtt[as] * 0.5f : 40.0f; if (lag > 250.0f) lag = 250.0f;
        uint64_t since = now - g_mdg.press_ms;
        if ((float)since + MD_LAG_GRACE_MS < lag && GetFileAttributesA("t2r-dodge-lag-check.txt") != INVALID_FILE_ATTRIBUTES) {   // at 165 ms one-way it refused nearly every dodge - now opt-in only
            static int nl2; if (LOGCAP(nl2, 40)) xlog("dodge: blow from slot %d NOT dropped - our press came %llu ms before the blow arrived, but the blow connected on its screen ~%.0f ms before it arrived (press after its contact)", as, (unsigned long long)since, lag);
            return 0; } }
    // (the attacker ruled 'TOO LATE, the blow lands' (press reached it < 70 ms before its contact), sent the damage, and this
    // gate dropped it '109 ms into the i-frames' - the attacker got MISS with its fist on our head). The same rule from our side: our press reached the attacker
    // ~one-way after we pressed, its contact was ~one-way before the blow got here; under the attacker's limit (+50 ms for the blow's send / hold delay) the blow lands.
    if (GetFileAttributesA("t2r-dodge-late-ok.txt") == INVALID_FILE_ATTRIBUTES) {
        float ow = g_ps_rtt[as] > 0.0f ? g_ps_rtt[as] * 0.5f : 10.0f; if (ow > 250.0f) ow = 250.0f;
        float lead = (float)(now - g_mdg.press_ms) - 2.0f * ow;
        if (g_mdu_late_rx[as] && now - g_mdu_late_rx[as] < 600) { xlog("dodge: slot %d ruled our press TOO LATE (MDUO_LATE) - its blow / START lands", (int)as); g_mdg_late_ms = now; return 0; }
        if (lead < 120.0f) { static int nl3; if (LOGCAP(nl3, 40)) xlog("dodge: blow from slot %d NOT dropped - our press reached its screen only ~%.0f ms before its contact (< 120 ms incl. send delay): TOO LATE, the blow lands", as, (double)lead); g_mdg_late_ms = now; return 0; }
    }
    if (trv11) { static int ntv; if (LOGCAP(ntv, 40)) xlog("dodge: blow from slot %d (dmg %.0f) %llu ms after the press - past the i-frames but our dodge clip is still travelling (lands at %llu ms): dropped (t2r-dodge-travel-immune-off.txt = old)", as, (double)dmg, (unsigned long long)(now - g_mdg.press_ms), (unsigned long long)g_mdg.cmb_land_ms); }
    g_mdg.dodged_hits++; mdg_ok_note(now);
    mdgt_note_dodged();
    xlog("dodge: blow from slot %d (weapon %llx, dmg %.0f) dropped %llu ms into the i-frames (%d ms) - dodged, attacker told", as, (unsigned long long)w, dmg, (unsigned long long)(now - g_mdg.press_ms), MD_IFRAME_MS);
    mdg_send_res();
    dc_arm((uint32_t)as);
    mdg_dodge_ok_cue(SID_PLAYER, T2R_MAX_PEERS, "our dodge dropped the blow");
    { uint8_t *wpl = t2r_peer((uint32_t)as); mdg_whiff_whoosh(puppet_handle((uint32_t)as), wpl && !IsBadReadPtr(wpl, 0x99) ? *(uint64_t *)(wpl + 0x91) : 0, (int)((uint32_t)as)); }   // the swinger's whiff on our screen
    return 1;
}
// paired.c: a one-shot / contextual down START from `from` arrives; 1 = refuse it (ABORT PS_AB_DODGED)
static int mdg_pair_dodged(uint32_t from, uint64_t move) {
    if (from < T2R_MAX_PEERS) g_mdg.sw[from].landed_ms = GetTickCount64();
    if (!g_mdg.iframe_until || mdg_off()) return 0;
    uint64_t now = GetTickCount64();
    if (!mdg_iframes(now) || !mdg_recent_swing(now, from, 2000)) return 0;
    {   int r56 = cd_pair_of_move(move); const char *pn56 = r56 >= 0 ? CD_PAIRS[r56].name : NULL;
        if (md56_counter_pair(from, now, pn56)) { xlog("dodge: ps56 pair START %s from slot %u inside our i-frames accepted - its dodge counter (it dodged our blow %llu ms ago; a counter cannot be dodged)", pn56 ? pn56 : "?", from, (unsigned long long)(now - g_md56_dodged_ms[from])); return 0; }
        if (md56_window_from(from, now)) xlog("dodge: ps56 pair START %s from slot %u %llu ms after it dodged our blow - NOT a counter: judged like any blow", pn56 ? pn56 : "?", from, (unsigned long long)(now - g_md56_dodged_ms[from])); }
    if (bq_hit_forced(from)) { xlog("beat: pair START from slot %u inside our i-frames accepted - the duel owner ruled a HIT", from); return 0; }
    // ps54 (md54_off above): our press was made inside the window of THIS attacker's swing, before its blow reached our screen (the START is the contact here). We
    // rule it: refused. The attacker's damage waits for our ACK (melee_duel.c verdict), so it is NO HIT there and it plays the miss. Only an explicit TOO LATE from
    // an attacker on the old rule still lands the blow.
    if (!md54_off() && !md45_win_old() && g_md45_inwin && g_mdg.last_slot == (int)from && !(g_mdu_late_rx[from] && now - g_mdu_late_rx[from] < 600))
        xlog("dodge: ps54 pair START from slot %u %llu ms after our in-window press (one-way %.0f) - the press came before its blow showed here: refused (ABORT DODGED)",
             from, (unsigned long long)(now - g_mdg.press_ms), (double)psync_oneway((int)from));
    else {
    if (mdg_partner_ruled(from)) { xlog("dodge: pair START from our duel partner slot %u inside our i-frames (%llu ms after the press) accepted - its contact ruled a HIT (one ruler; ps23)", from, (unsigned long long)(now - g_mdg.press_ms)); g_mdg_late_ms = now; return 0; }
    if (GetFileAttributesA("t2r-dodge-late-ok.txt") == INVALID_FILE_ATTRIBUTES) {   // The TOO LATE rule as in mdg_hit_dodged (a pair the attacker ruled TOO LATE was refused here)
        float ow = g_ps_rtt[from] > 0.0f ? g_ps_rtt[from] * 0.5f : 10.0f; if (ow > 250.0f) ow = 250.0f;
        float lead = (float)(now - g_mdg.press_ms) - 2.0f * ow;
        if (g_mdu_late_rx[from] && now - g_mdu_late_rx[from] < 600) { xlog("dodge: slot %d ruled our press TOO LATE (MDUO_LATE) - its blow / START lands", (int)from); g_mdg_late_ms = now; return 0; }
        if (lead < 120.0f) { xlog("dodge: pair START from slot %u accepted - our press reached its screen only ~%.0f ms before its contact: TOO LATE", from, (double)lead); g_mdg_late_ms = now; return 0; }
    }
    }   // (ps54 else)
    xlog("dodge: paired takedown / one-shot from slot %u refused %llu ms into the i-frames - dodged", from, (unsigned long long)(now - g_mdg.press_ms));
    mdg_ok_note(now);
    mdg_send_res();
    dc_arm(from);
    mdg_dodge_ok_cue(SID_PLAYER, T2R_MAX_PEERS, "our dodge refused the pair START");
    // ("refused - dodged" in log [217087] and the replica played its follow-through in silence): the START arrives when the replica reaches its contact frame -
    // the swinger's whiff whoosh on our screen now, as the "dropped the blow" path above. t2r-dodge-whoosh-old.txt = silent.
    if (GetFileAttributesA("t2r-dodge-whoosh-old.txt") == INVALID_FILE_ATTRIBUTES && from < T2R_MAX_PEERS) {
        uint8_t *wpl = t2r_peer(from); mdg_whiff_whoosh(puppet_handle(from), wpl && !IsBadReadPtr(wpl, 0x99) ? *(uint64_t *)(wpl + 0x91) : 0, (int)from);
        xlog("dodge: whoosh of slot %u's swing on our screen (its pair START was refused - dodged)", from);
    }
    return 1;
}
// ---- the attacker's side of a dodged blow
#define MD_STUMBLE_PHASE 0.40f     // where ellie-land-early-stumble^run starts (guess: the landing / run-in is the first ~40 %, the hand movement follows; tune with t2r-stumble-phase.txt)
#define MD_STUMBLE_M 1.2f
#define MD_STUMBLE_MS 900
#define MD_MISS_REG_M 0.4f          // a regular miss clip may drift this far
#define MD_MISS_REG_MS 800
static void mdg_attacker_missed(const char *why, int vslot) {
    if (vslot >= 0 && vslot < T2R_MAX_PEERS) g_md56_dodged_ms[vslot] = GetTickCount64();   // ps56: its counter cannot be dodged by us
    if (vslot >= 0 && mv3_stand("dodge: attacker miss (clip, carry, whoosh)", (uint32_t)vslot)) return;   // melee v3: the sim's MV3_E_DODGED / MISS (mv3_anim + mv3_fx)
    uint64_t now = GetTickCount64();
    if (g_mdg.miss_until > now + MD_MISS_MS - 300) return;                  // already handled (the hit drop and the pair refusal both tell us)
    g_mdg.miss_until = now + MD_MISS_MS; g_mdg.atk_lock_until = now + MD_ATK_RECOVER_MS;
    mpace_note_dodged();                                                    // melee_pace.c: the next swing start waits past the dodge recovery
    g_kd_early_slot = -1;                          // a pending swing-start knockdown ask (t2r-kd-swing-start.txt path) must not send its 0.4 s down hit after the dodge
    if (g_ms_atk && g_ms_curmove && !g_ms.active && !mdu_sp_miss(vslot)) {   // (not in a duel - SP's missed swing plays on at x1.00)
        uint64_t clip = mstag_clip_of(g_ms_curmove);
        if (clip) { mstag_speed(clip, MD_MISS_SPEED); g_mdg.slow_clip = clip; g_mdg.slow_until = now + MD_MISS_MS; }
    }
    if (mdu_miss_note(vslot, why)) { mdgt_note_miss(NULL); return; }   // melee_duel.c: inside a duel the miss is the swing's own slowed tail, in place (no stumble clip, no carry out of the sequence)
    // players can't really miss in SP, so the NPC anims are used - a REGULAR dodged swing plays an NPC's own miss clip of the weapon class (npc-* clips retargeted on the player the
    // way the other npc-* clips are played), in place (cap MD_MISS_REG_M); only a SPRINT swing (our ground speed >= OWN_SPRINT_MPS at the swing start) keeps the carried stumble
    // ellie-land-early-stumble^run (late phase, capped MD_STUMBLE_M). "dodge: miss clips" logs which candidates are loaded in MP (once).
    // (the attacker just did a normal empty attack: no npc-* miss clip is loaded in MP - logs "miss anim none loaded". Abby's own SP punch misses
    // of the brute fight come first: they may sit in the resident Abby melee pak the counters already use; the probe line says which load)
    static const char *const MISS_FIST[] = {"abby-fist-vs-brute-combo-punch-1-miss--abby", "abby-fist-vs-brute-combo-left-1-miss--abby", "fist-1-right-hook-miss",
                                            "npc-open-fw-idh-miss-punch-dodge", "npc-open-fw-idh-miss-backhand", "npc-open-fw-idh-miss-kick", "npc-open-fw-idh-miss-punch-enter",
                                            "fist-open-fw-hi-tr-haymaker-miss-hero", "fist-open-fw-hi-tl-l-cross-miss-hero", "hero-open-fw-idh-miss-backhand"};
    static const char *const MISS_KNIFE[] = {"npc-counter-knife-1-miss", "npc-counter-knife-2-miss", "npc-counter-knife-3-miss", "npc-counter-knife-4-miss"};
    static const char *const MISS_HEAVY[] = {"npc-sledge-attack-left-miss", "npc-sledge-attack-right-miss", "npc-sledge-attack-miss", "npc-sledge-attack-horizontal-sweep-overshoot"};   // 1h / 2h weapons: no named 1h blunt / blade whiff yet
    static const char *const MISS_SPRINT[] = {"ellie-land-early-stumble^run", "npc-m-1hblade-attack-sprint-slice-stumble", "npc-machete-sprint-slice-stumble", "npc-startle-stumble"};
    static const struct { const char *nm; const char *const *l; size_t n; } LISTS[4] = {
        {"fists", MISS_FIST, sizeof MISS_FIST / sizeof *MISS_FIST}, {"knife", MISS_KNIFE, sizeof MISS_KNIFE / sizeof *MISS_KNIFE},
        {"weapon", MISS_HEAVY, sizeof MISS_HEAVY / sizeof *MISS_HEAVY}, {"sprint", MISS_SPRINT, sizeof MISS_SPRINT / sizeof *MISS_SPRINT}};
    static int probed;
    if (!probed) {
        probed = 1; char b[1400]; int o = 0;
        for (int k = 0; k < 4; k++) { o += snprintf(b + o, SNLEFT(b, o), " [%s]", LISTS[k].nm); for (size_t i = 0; i < LISTS[k].n; i++) o += snprintf(b + o, SNLEFT(b, o), " %s=%.2f", LISTS[k].l[i], anim_len(SID_PLAYER, LISTS[k].l[i])); }
        xlog("dodge: miss clips (seconds, 0 = not loaded in MP):%s", b);
    }
    int sprint = g_mdg.my_swing_sprint;
    // SP's own miss: the attacker steps the way the dodger went (npc-reaction-step-<left|right|back>, set npc-human-shared; SP trace) - a regular swing only; the dodger's direction rides on MSG_DODGE_PRESS
    char stepn[40] = "";
    if (!sprint && vslot >= 0 && vslot < T2R_MAX_PEERS && g_mdg.imm_dir[vslot] > 0) {
        static const char *const SD[4] = {"forward", "left", "right", "back"};
        snprintf(stepn, sizeof stepn, "npc-reaction-step-%s", SD[g_mdg.imm_dir[vslot]]);
    }
    int cls = 3;
    if (!sprint) { uint64_t none = 0, hw = dc_call(SID_HAS_MELEE_WEAPON, 0, &none), w = current_weapon(); cls = !(hw != ~0ULL && (hw & 0xff)) ? 0 : knife_weapon_id(w) ? 1 : 2; }
    const char *used = NULL; uint64_t gr = ~0ULL;
    if (stepn[0] && anim_len(SID_PLAYER, stepn) > 0.1f) { gr = animate_now(SID_PLAYER, stepn); if (gr != ~0ULL) used = stepn; }
    { static unsigned rr[4];
      for (size_t k = 0; k < LISTS[cls].n && !used; k++) {
        const char *c = LISTS[cls].l[(rr[cls] + k) % LISTS[cls].n];
        if (anim_len(SID_PLAYER, c) <= 0.1f) continue;
        if (!strcmp(c, "ellie-land-early-stumble^run")) {      // the hand flail is in the later part of the clip: start past the run-in (t2r-stumble-phase.txt = a value 0..0.9)
            static float ph = -1.0f;
            if (ph < 0.0f) { ph = MD_STUMBLE_PHASE; FILE *f = exe_side_open("t2r-stumble-phase.txt", "r"); if (f) { float v = 0; if (fscanf(f, "%f", &v) == 1 && v >= 0.0f && v < 0.95f) ph = v; fclose(f); } xlog("dodge: miss stumble starts at phase %.2f of %s", ph, c); }
            gr = animate_from(SID_PLAYER, c, 0.2f, ph);
        } else gr = animate_now(SID_PLAYER, c);
        if (gr != ~0ULL) { used = c; rr[cls]++; }
      } }
    if (!used) { static int nl; if (LOGCAP(nl, 10)) xlog("dodge: no %s miss clip loaded in MP - slowed swing tail + lock only%s", LISTS[cls].nm, sprint ? " + the short carry" : ", no travel"); }
    float mb[16]; const float *ml = uc4_my_loc(mb);
    if (used && gr != ~0ULL && ml && __builtin_isfinite(ml[0])) {
        g_mdg.st_on = 1; g_mdg.st_ms = now; g_mdg.st_f = g_frame ? g_frame : 1; g_mdg.st_xz[0] = ml[0]; g_mdg.st_xz[1] = ml[2]; g_mdg.st_jw[0] = g_mdg.st_jw[1] = g_mdg.st_jg = 0;
        g_mdg.st_cap = sprint ? MD_STUMBLE_M : MD_MISS_REG_M; g_mdg.st_cap_ms = sprint ? MD_STUMBLE_MS : MD_MISS_REG_MS;
        snprintf(g_mdg.st_clip, sizeof g_mdg.st_clip, "%s", used);
        xlog("dodge: miss clip %s (%s swing, %s)", used, sprint ? "SPRINT" : "regular", LISTS[cls].nm);
    }
    if (ml && (sprint || !used)) {      // a sprint swing carries on; a regular miss with a clip stays put, without one the body follows the swing through 0.3 m (no connect look)
        float fx = 2.0f * (ml[4] * ml[6] + ml[7] * ml[5]), fz = 1.0f - 2.0f * (ml[4] * ml[4] + ml[5] * ml[5]), fl = __builtin_sqrtf(fx * fx + fz * fz);
        if (fl > 1e-3f) {
            float dirs[2][2] = {{fx / fl, fz / fl}, {0, 0}}, tot[2] = {sprint ? 0.6f : 0.3f, 0.0f};
            mdg_mv_begin(&g_md_carry, "carry through the dodged swing", 1, dirs, tot);
            uint8_t *vp = vslot >= 0 ? mdg_peer((uint32_t)vslot) : NULL;      // stop before the dodger's body
            float vb[16]; const float *vl = vp && *(uint64_t *)(vp + 0x60) ? puppet_locator(*(uint64_t *)(vp + 0x60), vb) : NULL;
            if (vl && g_md_carry.on) { g_md_carry.stop_on = 1; g_md_carry.stop_xz[0] = vl[0]; g_md_carry.stop_xz[1] = vl[2]; }
        }
    }
    mdgt_note_miss(used);
    mdg_whiff_whoosh(SID_PLAYER, current_weapon(), -1);       // our swing cut the air (the weapon's own swing whoosh)
    g_mdg.tr_until = now + 700; g_mdg.tr_clip = used; { float tb[16]; const float *tl = uc4_my_loc(tb); if (tl) { g_mdg.tr_from[0] = tl[0]; g_mdg.tr_from[1] = tl[2]; } }
    xlog("dodge: OUR blow was dodged (%s) - miss anim %s, swing tail x%.2f for %d ms, carried forward <= 0.6 m, no fire / aim / melee for %d ms (whiff x1.8 off)",
         why, used ? used : "none loaded (carry + lock only)", MD_MISS_SPEED, MD_MISS_MS, MD_ATK_RECOVER_MS);
}
// the dodger announced his press: until imm_until[slot] our contact with him is a miss, decided HERE at once (the attacker's own engine registers contact before MSG_DODGE_RES arrives)
static float mdg_clip_len(uint64_t sid);
// ps49 (dodging was almost impossible; the timing should be in the middle of the swing; log [147956] / [148078]: presses 63 / 93 ms into a swing
// ruled HEAVY with 1500 ms of cooldown; [149527]: a press 110 ms into a 386 ms swing had i-frames only to +370 ms): a dodge pressed in a swing's window covers that
// swing's contact - the i-frames reach its contact + MDG49_COVER_MS on the dodger's screen, and the attacker keeps the dodger immune to its own contact + the same.
// The ideal press is anywhere from the swing's start to its window's close (the middle of the swing is inside). t2r-dodge-cover-ps49-old.txt = i-frames 260 ms from the press.
#define MDG49_COVER_MS 60     // [TUNING ps49] ms past the contact the i-frames still hold
#define MDG49_BUF_MS 250      // [TUNING ps49] a heavy dodge pressed this long before a swing's window opens becomes that swing's dodge
static uint64_t g_mdg49_rx[T2R_MAX_PEERS], g_mdg49_cover[T2R_MAX_PEERS];
static uint64_t mdu49_vic_contact(uint32_t slot);   // melee_duel.c: the partner's swing contact on our clock (its SWING message)
static uint64_t mdu49_att_contact(uint32_t slot);   // melee_duel.c: our own swing's contact when it is on that slot
static int mdg49c_off(void) { static int v = -1; static uint64_t at; uint64_t n = GetTickCount64(); if (v < 0 || n - at > 2000) { at = n; int o = GetFileAttributesA("t2r-dodge-cover-ps49-old.txt") != INVALID_FILE_ATTRIBUTES; if (o != v) xlog("dodge: ps49 contact cover %s", o ? "OFF (t2r-dodge-cover-ps49-old.txt): i-frames 260 ms from the press" : "ON - a press in a window is immune to that swing's contact + 60 ms on both screens"); v = o; } return v; }
static int mdg49b_off(void) { static int v = -1; static uint64_t at; uint64_t n = GetTickCount64(); if (v < 0 || n - at > 2000) { at = n; int o = GetFileAttributesA("t2r-dodge-buffer-ps49-old.txt") != INVALID_FILE_ATTRIBUTES; if (o != v) xlog("dodge: ps49 press buffer %s", o ? "OFF (t2r-dodge-buffer-ps49-old.txt): a press before the window is a heavy dodge with 1500 ms cooldown" : "ON - a heavy dodge pressed up to 250 ms before a swing's window becomes that swing's dodge (no 1500 ms cooldown)"); v = o; } return v; }
static int mdg_slot_immune(uint32_t sl) {
    if (sl >= T2R_MAX_PEERS || !g_mdg.imm_until[sl] || bq_not_immune(sl)) return 0;   // (melee_beat.c: not while the owner HIT for our blow plays)
    uint64_t n = GetTickCount64();
    return n < g_mdg.imm_until[sl] || (g_mdg49_cover[sl] && n < g_mdg49_cover[sl]);
}
static int mdg49_pressed_in(int slot, uint64_t t0) { return slot >= 0 && slot < T2R_MAX_PEERS && g_mdg.imm_until[slot] && g_mdg49_rx[slot] && g_mdg49_rx[slot] >= t0 && !mdg49c_off(); }   // (melee_beat.c: not while the owner HIT for our blow plays)
// The dodger's puppet on OUR screen (attacker POV clip: the fist reached his face at 0.87 s, the streamed dodge only began ~0.95 s and read as a hit reaction): its dodge clip
// starts the moment the press message arrives, advanced by the one-way latency (half the measured RTT) so the lean is already under way, on the same layer the downed-melee flinches
// use. The streamed pose / position is not touched (the clip is played over it, then blended out at its end).
static uint64_t mdg_puppet_animate(uint64_t ent, uint64_t sid, float phase) {
    uint64_t aa[4] = {fnv64("single-frame"), 16, 2, 1};
    uint64_t arr = dc_call(fnv64("#%alloc-array"), 4, aa);
    if (!arr || arr == ~0ULL || IsBadReadPtr((void *)arr, 8)) return ~0ULL;
    uint64_t *tab = *(uint64_t **)arr;
    if (!tab || IsBadReadPtr(tab, 16) || !tab[0] || !tab[1] || alloc_entry_bad((void *)arr, (void *)tab[0], 16) || alloc_entry_bad((void *)arr, (void *)tab[1], 16)) return ~0ULL;   // (soak: the cold probe = 6-9 ms mdg_tick hitches)
    uint8_t *e0 = (uint8_t *)tab[0], *e1 = (uint8_t *)tab[1]; float blend = 0.20f;   // was 0.08 (fluid over fast)
    *(int32_t *)e0 = 28; memcpy(e0 + 8, &blend, 4);
    *(int32_t *)e1 = 58; memcpy(e1 + 8, &phase, 4);
    uint64_t a[3] = {ent, sid, arr};
    return dc_call(fnv64("animate_"), 3, a);
}
// the dodge grunt (SP's dodges carry Ellie's voice-effect vox-eff-gen-fight-dodge-hvy / -lrg-short; our duck clips are silent).
// `say` on the dodging body: ours at the combat dodge's start, a puppet's when its dodge clip starts here. t2r-no-dodge-vox.txt = off.
static void dm_say(uint64_t ent, const char *ev, int vxe);
static void mdg_dodge_say(uint32_t who, uint64_t ent) {      // who: slot, or T2R_MAX_PEERS = us
    static uint64_t last[T2R_MAX_PEERS + 1], chk; static int off = -1, nl, rr;
    uint64_t now = GetTickCount64();
    if (off < 0 || now - chk > 2000) { chk = now; off = GetFileAttributesA("t2r-no-dodge-vox.txt") != INVALID_FILE_ATTRIBUTES; }
    if (off || !ent || ent == ~0ULL || who > T2R_MAX_PEERS || now - last[who] < 600) return;
    last[who] = now;
    // (no Ellie / Abby voice at all - -hvy / -lrg-short have only their takes; every WLF / Seraphite voice has the plain dodge effort)
    const char *ev = "vox-eff-gen-fight-dodge"; (void)rr;
    dm_say(ent, ev, VXE_GIVE);
    if (LOGCAP(nl, 40)) xlog("dodge: grunt %s on %s", ev, who == T2R_MAX_PEERS ? "us" : "a puppet");
}
static int dtl_pup_route(uint32_t slot, int src, uint64_t sid, uint32_t cut, float age);   // melee_duel_tl.c: the duel partner's puppet clips (1 = handled there)
static void mdg_puppet_dodge(uint32_t slot, uint64_t sid) {
    static int off = -1; static uint64_t chk; uint64_t now = GetTickCount64();
    if (off < 0 || now - chk > 2000) { chk = now; FILE *f = exe_side_open("t2r-no-puppet-dodge.txt", "r"); off = f != NULL; if (f) fclose(f); }
    // duel timeline: the partner's dodge (its press = the prediction, the verdict confirms it) through the duel queue, phase 0 + catch-up (no trimmed start)
    if (!off && sid && slot < T2R_MAX_PEERS && dtl_pup_route(slot, 3 /* DTL_S_DODGE */, sid, 0, g_ps_rtt[slot] > 0.0f ? g_ps_rtt[slot] * 0.5f : 40.0f)) return;
    if (off || !sid || slot >= T2R_MAX_PEERS || g_peer_downed[slot] || g_puppet_dead_here[slot] || psync_busy_slot(slot)) return;
    uint64_t ent = puppet_handle(slot);
    if (!ent) return;
    float dur = mdg_clip_len(sid);
    if (!(dur > 0.2f)) { static int nl; if (LOGCAP(nl, 10)) xlog("dodge: puppet slot %u dodge clip %llx not loaded here - the streamed dodge only", slot, (unsigned long long)sid); return; }
    float age = g_ps_rtt[slot] > 0.0f ? g_ps_rtt[slot] * 0.5f : 40.0f;
    float ph = age / 1000.0f / dur; if (ph > 0.6f) ph = 0.6f;
    uint64_t r = mdg_puppet_animate(ent, sid, ph);
    if (r && r != ~0ULL && slot < T2R_MAX_PEERS) g_mdg_pup_anim_ms[slot] = now;
    if (r && r != ~0ULL && mdg_rx_heavy((int)slot, sid)) dtl_speed_s(ent, sid, 0.8f, MO_SRC("dodge.pup_heavy"));   // ps46: a heavy dodge's clip at its rate (held th / rate below)
    uint64_t cut = now + (uint64_t)(dur * MD_CLIP_FRAC * 1000.0f); if (cut > now + MD_CLIP_MAX_MS) cut = now + MD_CLIP_MAX_MS;
    cut = now + mdg_sp_hold_ms((int)slot, sid, cut - now);   // SP duel dodge: the dodger holds it to its flat part
    g_mdg.pd[slot].ent = ent; g_mdg.pd[slot].sid = sid; g_mdg.pd[slot].end = cut;
    if (r != ~0ULL) mdg_dodge_say_at(slot, ent, 150 - (int)age);
    xlog("dodge: puppet slot %u dodge clip %llx started at phase %.2f (age %.0f ms, clip %.2f s) -> %llx", slot, (unsigned long long)sid, ph, age, dur, (unsigned long long)r);
}
static void mdg_puppet_tick(uint64_t now) {
    for (uint32_t k = 0; k < T2R_MAX_PEERS; k++) {
        if (!g_mdg.pd[k].end || now < g_mdg.pd[k].end) continue;
        uint64_t a[5] = {g_mdg.pd[k].ent, ANIM_LAYER, 0, g_mdg.pd[k].sid, 0}; float sec = MD_RELEASE_BLEND; memcpy(&a[2], &sec, 4);
        dc_call(fnv64("stop-animating"), 5, a);
        g_mdg.pd[k].end = 0;
    }
}
static void mdg_recv_press(uint32_t slot, const uint8_t *buf, uint64_t len) {
    if (slot >= T2R_MAX_PEERS || slot == *(uint32_t *)VMA(0x180138090) || mdg_off() || is_teammate(slot)) return;
    int imm = len >= 1 && buf && (buf[0] & 1);
    g_mdg.imm_dir[slot] = len >= 2 && buf && buf[1] < 4 ? (int8_t)buf[1] : -1;
    if (imm && !md56_off() && g_md56_ctr_ms[slot] && GetTickCount64() - g_md56_ctr_ms[slot] < MD56_CTR_MS) {   // ps56: our dodge counter on it cannot be dodged
        static int nl56; if (LOGCAP(nl56, 40)) xlog("dodge: ps56 slot %u pressed dodge %llu ms into our dodge counter on it - NOT immune (a counter cannot be dodged)", slot, (unsigned long long)(GetTickCount64() - g_md56_ctr_ms[slot]));
        imm = 0; }
    g_mdg.imm_until[slot] = imm ? GetTickCount64() + MD_IFRAME_MS + MD_PRESS_MARGIN_MS : 0;
    {   uint64_t n49 = GetTickCount64(), c49 = imm ? mdu49_att_contact(slot) : 0;   // ps49: immune through our own swing's contact
        g_mdg49_rx[slot] = imm ? n49 : 0; g_mdg49_cover[slot] = 0;
        if (c49 && c49 > n49 && c49 - n49 < 1200 && !mdg49c_off()) {
            g_mdg49_cover[slot] = c49 + MDG49_COVER_MS;
            if (g_mdg49_cover[slot] > g_mdg.imm_until[slot]) { static int nl49; if (LOGCAP(nl49, 60)) xlog("dodge: ps49 slot %u pressed %llu ms before our contact - immune to it (+%d ms), not only %d ms from the press", slot, (unsigned long long)(c49 - n49), MDG49_COVER_MS, MD_IFRAME_MS + MD_PRESS_MARGIN_MS); }
        }
    }
    if (len >= 10 && buf) {
        uint64_t sid; memcpy(&sid, buf + 2, 8);
        if (sid) { g_mdg_rx_heavy[slot] = (buf[0] & 2) ? GetTickCount64() : 0; g_mdg_rx_heavy_sid[slot] = sid; }   // (ps49: an upgrade message has no clip - the running one keeps its rate)   // ps46: the dodger's heavy dodge (x0.80)
        mdg_puppet_dodge(slot, sid); if (sid) mdg_sp_pup_note(slot);
    }
    static int nl; if (LOGCAP(nl, 40)) xlog("dodge: slot %u pressed dodge - %s for %d ms", slot, imm ? "immune" : "NOT immune (into the blow)", imm ? MD_IFRAME_MS + MD_PRESS_MARGIN_MS : 0);
}
// hitsend_hook / directhit_hook: our blow on `slot`. 1 = it is dodged: the caller sends nothing and plays no hit feedback (sfx / blood / hitmarker / camera kick / damage number)
// ps23 (log [11237]-[11240], tl 9.13: the duel contact ruled HIT and started the pair, the victim's press reached us 2 frames later, and the blow's
// damage - delivered on the victim's ACK - was ruled again HERE: 'verdict HIT' and 'MISS (local contact on a dodger in i-frames)' on one blow, no damage sent, a
// 650 ms miss lock on a blow whose pair played on both screens; A [15705] took the pair and was told 'our dodge dropped its blow'). One ruler: a blow the duel's
// contact already ruled (melee_duel.c mdu_deliver sets g_mdg_ruled_blow round its hit) is not ruled a second time. t2r-dodge-reruling-old.txt = old.
static int g_mdg_ruled_blow;
static int mdg_rerule_old(void) { static int v = -1; static uint64_t at; uint64_t n = GetTickCount64(); if (v < 0 || n - at > 3000) { at = n; v = GetFileAttributesA("t2r-dodge-reruling-old.txt") != INVALID_FILE_ATTRIBUTES; } return v; }
static int mdg_contact_dodged(uint32_t slot, uint64_t w) {
    if (slot >= T2R_MAX_PEERS || !g_mdg.imm_until[slot] || mdg_off()) return 0;
    if (g_mdg_ruled_blow && !mdg_rerule_old()) {
        if (GetTickCount64() < g_mdg.imm_until[slot]) { static int nr; if (LOGCAP(nr, 40)) xlog("dodge: OUR blow on slot %u was ruled a HIT by the duel contact - not ruled again (its dodge press reached us after the contact; ps23)", slot); }
        return 0;
    }
    uint64_t now = GetTickCount64();
    if (now >= g_mdg.imm_until[slot] || !mhs_is_blow(w) || mdg_is_thrown(w) || bq_not_immune(slot)) return 0;
    static int nl; if (LOGCAP(nl, 40)) xlog("dodge: OUR contact on slot %u (weapon %llx) %llu ms before its i-frames end - dodged: no hit sent, no feedback", slot, (unsigned long long)w, (unsigned long long)(g_mdg.imm_until[slot] - now));
    mdg_attacker_missed("local contact on a dodger in i-frames", (int)slot);
    mdg_send_res_atk(slot);   // tell the dodger its dodge dropped our blow: its own recv_hit_hook never sees a blow we decided here, so it could not arm the dodge counter
    return 1;
}
// The miss stumble's travel cap. The pose of every puppet is streamed from the real body (re/melee-pose-gap.md: same as mstag_speed), so stopping the clip on our body stops it on every
// peer - no extra message. Ends when the body has moved MD_STUMBLE_M (XZ) or MD_STUMBLE_MS passed, or a probe ahead says wall < 0.4 m / no ground (the carry's rays).
static void mdg_stumble_end(const char *why, float moved) {
    uint64_t r = anim_end_blend(SID_PLAYER, g_mdg.st_clip, 0.25f);
    xlog("dodge: miss stumble capped at %.2f m (%s, %llu ms, %s -> %llx)", moved, why, (unsigned long long)(GetTickCount64() - g_mdg.st_ms), g_mdg.st_clip, (unsigned long long)r);
    g_mdg.st_on = 0; g_mdg.st_jw[0] = g_mdg.st_jw[1] = g_mdg.st_jg = 0;
}
static void mdg_stumble_tick(uint64_t now) {
    if (!g_mdg.st_on) return;
    float lb[16]; const float *l = uc4_my_loc(lb);
    if (!l || !__builtin_isfinite(l[0])) { g_mdg.st_on = 0; return; }
    float moved = __builtin_sqrtf((l[0] - g_mdg.st_xz[0]) * (l[0] - g_mdg.st_xz[0]) + (l[2] - g_mdg.st_xz[1]) * (l[2] - g_mdg.st_xz[1]));
    if (moved > g_mdg.st_cap) { mdg_stumble_end("distance", moved); return; }
    if (now - g_mdg.st_ms > g_mdg.st_cap_ms) { mdg_stumble_end("time", moved); return; }
    if (g_frame <= g_mdg.st_f) return;
    if (g_mdg.st_jw[0]) {                                        // last frame's probes: wall within 0.4 m (ray 0.8 m long) or no ground / a step 0.6 m ahead
        float rw = ray_t(g_mdg.st_jw[0]), rg = ray_t(g_mdg.st_jg);
        g_mdg.st_jw[0] = g_mdg.st_jg = 0;
        if (rw >= 0.0f && rw < 0.5f) { mdg_stumble_end("wall ahead", moved); return; }
        if (rg < 0.0f || rg > 0.99f || rg < 0.2f || rg > 0.62f) { mdg_stumble_end("edge / step ahead", moved); return; }
    }
    float fx = 2.0f * (l[4] * l[6] + l[7] * l[5]), fz = 1.0f - 2.0f * (l[4] * l[4] + l[5] * l[5]), fl = __builtin_sqrtf(fx * fx + fz * fz);
    if (!(fl > 1e-3f)) return;
    fx /= fl; fz /= fl;
    float a[3] = {l[0], l[1] + 0.5f, l[2]}, b[3] = {l[0] + fx * 0.8f, l[1] + 0.5f, l[2] + fz * 0.8f};
    float c[3] = {l[0] + fx * 0.6f, l[1] + 0.6f, l[2] + fz * 0.6f}, e[3] = {c[0], l[1] - 0.9f, c[2]};
    g_mdg.st_jw[0] = world_ray_kick_m(a, b, 0, 0x1b07); g_mdg.st_jg = world_ray_kick_m(c, e, 0, 0x1b07); g_mdg.st_f = g_frame;   // (grass)
}
static int dc_is_melee(uint64_t w);
static int g_mdg_press_late;   // the last dodge press came in the last 200 ms before the dodged swing's contact
static void mdg_recv_res(uint32_t slot, const uint8_t *buf, int len) {
    if (slot >= T2R_MAX_PEERS || mdg_off() || is_teammate(slot)) return;
    uint64_t now = GetTickCount64();
    if (buf && len >= 2 && buf[0] == 1) {   // the attacker-decided form: for its dodger only, never the old "you were dodged" meaning
        if (buf[1] != (uint8_t)*(uint32_t *)VMA(0x180138090) || !g_mdg.press_ms || now - g_mdg.press_ms >= 1500) return;   // we are the DODGER: the attacker decided our dodge on its side (mdg_contact_dodged) - arm the counter
        mdg_dodge_ok_cue(SID_PLAYER, T2R_MAX_PEERS, "the attacker decided our dodge");
        mdg_ok_note(now);
        // Counters were too dominant (dodge baiting gave a ~100% dodge rate): the counter is the reward for a PERFECT dodge (last 200 ms before the
        // contact) of a melee WEAPON swing; an early dodge or a dodged punch only saves you. t2r-counter-any-dodge.txt = the old rule.
        { uint8_t *wa = t2r_peer(slot); uint64_t aw = wa && !IsBadReadPtr(wa, 0x99) ? *(uint64_t *)(wa + 0x91) : 0;
          int any = GetFileAttributesA("t2r-counter-any-dodge.txt") != INVALID_FILE_ATTRIBUTES;
          int late_ok = sk_counter_late();          // Counter Fighter II: a late (not perfect) dodge of a melee weapon swing also arms the counter
          if (!any && late_ok && !g_mdg_press_late && dc_is_melee(aw)) xlog("skills: COUNTER FIGHTER 2: a late dodge (pressed earlier than %d ms before the contact) still earns the counter", MD_PERFECT_MS);
          if (!any && ((!g_mdg_press_late && !late_ok) || !dc_is_melee(aw))) {
              xlog("dodge: slot %u says our dodge dropped its blow (%llu ms after our press) - no counter (perfect window %d ms before the contact): %s", slot, (unsigned long long)(now - g_mdg.press_ms), MD_PERFECT_MS,
                   !dc_is_melee(aw) ? "the attacker's blow was unarmed (punches are dodged, never countered)" : "not a perfect dodge (pressed earlier than the perfect window before the contact)");
              mdg_whiff_whoosh(puppet_handle(slot), aw, (int)(slot));
              return;
          } }
        xlog("dodge: slot %u says our dodge dropped its blow (%llu ms after our press) - counter armed (perfect window %d ms before the contact, press was %s)", slot, (unsigned long long)(now - g_mdg.press_ms), MD_PERFECT_MS, g_mdg_press_late ? "perfect" : "late");
        dc_arm(slot);
        { uint8_t *wpl = t2r_peer(slot); mdg_whiff_whoosh(puppet_handle(slot), wpl && !IsBadReadPtr(wpl, 0x99) ? *(uint64_t *)(wpl + 0x91) : 0, (int)(slot)); }   // the swinger's whiff on our screen
        return;
    }
    if (!g_mdg.my_swing_ms || now - g_mdg.my_swing_ms > 1600 || mdg_busy()) return;
    mdg_attacker_missed("the victim told us", (int)slot);
}
// paired.c (ABORT with PS_AB_DODGED reaches the attacker): the pair never started; the swing is a miss and the one-shot is given back
static void mdg_pair_refused_by_dodge(uint32_t from) {
    if (g_upgrade_used > 0) { g_upgrade_armed++; g_upgrade_used--; }
    g_upgrade_spent_at = 0;
    mdg_attacker_missed("the victim dodged our takedown / one-shot", (int)from);
}
// ---- the dodge itself
// The Dodge prompt must not be visible at any moment while the cooldown runs. The engine icon is a per-frame request (world_prompt), so stopping the requests ends it; what can
// outlive the window is OUR side: the recorded request (g_wpr, read by the attach / self-draw routes for 2 more frames) and the "DODGE" text fallback, which goes through the
// styled-notification queue (shown 0.6 s + fade, or still WAITING in the queue behind another toast and coming up during the cooldown).
static void ntf_cancel(const char *text);                  // notify.c
static void mdg_prompt_withdraw(const char *why) {
    static int nl;
    if (g_wpr.h && !strcmp(g_wpr.label, loc_keep("Dodge"))) { g_wpr.h = 0; g_wpr.frame = 0; }
    ntf_cancel("DODGE");
    mdg46_icon_hide(why);
    if (LOGCAP(nl, 40)) xlog("dodge: prompt withdrawn (%s) - last request %llu frames / %llu ms ago", why, (unsigned long long)(g_mdg.last_req_f ? g_frame - g_mdg.last_req_f : 0), (unsigned long long)(g_mdg.last_req_ms ? GetTickCount64() - g_mdg.last_req_ms : 0));
}
static void mdg_fallback(int slot) {
    // The combat dodge was skipped (TOO LATE, the blow lands) but 100 ms later this fallback still sidestepped with a dodge clip
    if (g_mdg_late_ms && GetTickCount64() - g_mdg_late_ms < 600) { xlog("dodge: fallback sidestep skipped - the blow was TOO LATE for this press and lands"); return; }
    float mb[16], pb[16]; const float *ml = uc4_my_loc(mb);
    uint8_t *pe = mdg_peer((uint32_t)slot);
    const float *pl = pe && *(uint64_t *)(pe + 0x60) ? puppet_locator(*(uint64_t *)(pe + 0x60), pb) : NULL;
    if (!ml || !pl) return;
    float ax = ml[0] - pl[0], az = ml[2] - pl[2], al = __builtin_sqrtf(ax * ax + az * az);
    if (!(al > 0.05f)) { ax = 0; az = 1; al = 1; }
    ax /= al; az /= al;
    float px = -az, pz = ax;                                   // sideways of the line attacker -> us
    float dirs[2][2] = {{px * 0.96f + ax * 0.27f, pz * 0.96f + az * 0.27f}, {-px * 0.96f + ax * 0.27f, -pz * 0.96f + az * 0.27f}}, tot[2] = {0.9f, 0.9f};
    mdg_mv_begin(&g_md_fb, "fallback sidestep", 2, dirs, tot);
    float fx = 2.0f * (ml[4] * ml[6] + ml[7] * ml[5]), fz = 1.0f - 2.0f * (ml[4] * ml[4] + ml[5] * ml[5]);
    const char *cl = ((fz * px - fx * pz) > 0 ? "ellie-1hblade-dodge-right" : "ellie-1hblade-dodge-left");
    uint64_t gr = ~0ULL;
    if (anim_len(SID_PLAYER, cl) > 0.1f) gr = animate_now(SID_PLAYER, cl);     // full-body clip on the player layer (streams to peers like the stun clips), not the additive gesture layer
    g_mdg.tr_until = GetTickCount64() + 700; g_mdg.tr_clip = cl; g_mdg.tr_from[0] = ml[0]; g_mdg.tr_from[1] = ml[2];
    xlog("dodge: engine dodge move not seen in %d ms - fallback sidestep (0.9 m, best free side) + full-body clip %s (animate_ -> %llx)", MD_ENGINE_WAIT_MS, gr != ~0ULL ? cl : "none loaded", (unsigned long long)gr);
}
// ---- successful-dodge animations (successful dodges have different animations than just dodging). The engine's contextual dodges player-combat-dodge-<dir>-<angle>-<side>-<a..e>
// (re/uc4/sid4_strings.txt; all ids are in MD_MOVES: no lock-on glide / lunge toward anyone) are what SP picks vs an NPC's blow by its direction. Against a puppet the engine plays only the
// plain open dodge, so at the press the ext picks the move from the announced swing (angle class + hand from the attacker, MSG_DODGE_SWING) and plays its clip on the player layer
// (animate_, streamed to peers like the stun clips; the move's own clip sid = move def +0x68 -> info +0x20, as mstag_clip_of): the first candidate whose move and clip are loaded in MP.
// A blow from our left (his right hand) is slipped on that side or leaned away from (back). Our own sidestep (<= MD_STEP_M, collision checked) does the travel: the engine's root
// motion is cut by cancel-melee-action. Opt-out t2r-no-combat-dodge.txt. Log: "dodge: combat dodge ...".
#define MD_CAP_M 1.4f             // an engine dodge move that has carried the dodger further than this is cancelled
static int mdg_combat_off(void) {
    static int off = -1; static uint64_t at; uint64_t now = GetTickCount64();
    if (off < 0 || now - at >= 2000) { at = now ? now : 1; FILE *f = exe_side_open("t2r-no-combat-dodge.txt", "r"); int o = f != NULL; if (f) fclose(f); if (o != off) xlog("dodge: combat dodge clips %s", o ? "OFF (t2r-no-combat-dodge.txt)" : "on (player-combat-dodge-<dir>-<angle>-<side> clip at a successful dodge's press)"); off = o; }
    return off;
}
static float mdg_clip_len(uint64_t sid) {
    uint64_t d2[2] = {SID_PLAYER, sid}, rd = dc_call(fnv64("get-animation-duration"), 2, d2);
    float dur = 0; uint32_t dl = (uint32_t)rd; memcpy(&dur, &dl, 4);
    return rd != ~0ULL && dur > 0.2f && dur < 30.0f ? dur : 0.0f;
}
static uint64_t mdg_animate_sid(uint64_t sid) {          // animate_now with a clip sid (the move's own clip) instead of a name
    uint64_t aa[4] = {fnv64("single-frame"), 16, 1, 1};
    uint64_t arr = dc_call(fnv64("#%alloc-array"), 4, aa);
    if (!arr || arr == ~0ULL) return ~0ULL;
    if (!IsBadReadPtr((void *)arr, 8)) {
        uint64_t *tab = *(uint64_t **)arr;
        uint8_t *e = tab && !IsBadReadPtr(tab, 8) ? (uint8_t *)tab[0] : NULL;
        if (e && !alloc_entry_bad((void *)arr, e, 16)) { float b = ANIM_BLEND; *(int32_t *)e = 28; memcpy(e + 8, &b, 4); }
    }
    uint64_t a[3] = {SID_PLAYER, sid, arr};
    return dc_call(fnv64("animate_"), 3, a);
}
// The dodge direction is the player's own move stick at the press (dodge anims are direction based, to prevent dodging into the attack): keyboard WASD or the pad's
// left stick, relative to the body / camera (it faces the attacker within ~40 deg); no stick = back. 1 left, 2 right, 3 back, 0 forward.
static int mdg_stick_dir(float *sx, float *sy) {
    float x = 0.0f, y = 0.0f;
    if (game_focused()) {
        x = (float)(((GetAsyncKeyState('D') & 0x8000) ? 1 : 0) - ((GetAsyncKeyState('A') & 0x8000) ? 1 : 0));
        y = (float)(((GetAsyncKeyState('W') & 0x8000) ? 1 : 0) - ((GetAsyncKeyState('S') & 0x8000) ? 1 : 0));
    }
    WORD bt; BYTE l, r; SHORT lx, ly;
    // dodge was much more functional pressing alt on the keyboard: XInput alone misses a DualSense / Steam Input pad - the stick read 0 and every
    // pad dodge went back / default. The engine's own Joypad stick first (any pad), XInput as the fallback.
    float ex, ey;
    if (x == 0.0f && y == 0.0f && game_focused() && padinj_left_stick(&ex, &ey) && ex * ex + ey * ey >= 0.3f * 0.3f) { x = ex; y = ey; }
    if (x == 0.0f && y == 0.0f && pad_state(&bt, &l, &r, &lx, &ly)) { x = (float)lx / 32768.0f; y = (float)ly / 32768.0f; }
    *sx = x; *sy = y;
    if (x * x + y * y < 0.3f * 0.3f) return 3;
    if (__builtin_fabsf(x) > __builtin_fabsf(y)) return x > 0 ? 2 : 1;
    return y > 0 ? 0 : 3;
}
static int mdg48_off(void) { static int v = -1; static uint64_t at; uint64_t n = GetTickCount64(); if (v < 0 || n - at > 2000) { at = n; v = GetFileAttributesA("t2r-dodge-dir-ps48-old.txt") != INVALID_FILE_ATTRIBUTES; } return v; }
static int mdg48v_off(void) { static int v = -1; static uint64_t at; uint64_t n = GetTickCount64(); if (v < 0 || n - at > 2000) { at = n; v = GetFileAttributesA("t2r-dodge-variant-ps48-old.txt") != INVALID_FILE_ATTRIBUTES; } return v; }
// ps48: how far a clip's SP duel dodge squeezes its travel (SP end travel / the clip's own travel at its flat part); 0 = no root-motion row
static float mdg48_k(uint64_t clip, int dir) {
    const MdgRm *rm = mdg_rm_find(clip); if (!rm) return 0.0f;
    float th = mdg_sp_flat_s(rm), x, z, y; mdg_rm_at(rm, th, &x, &z, &y);
    float d = __builtin_sqrtf(x * x + z * z); if (d < 0.05f) return 0.0f;
    return (dir == 1 || dir == 2 ? MDS_SP_END_SIDE_M : MDS_SP_END_M) / d;
}
static int g_mdg_duck;            // the running combat dodge is one of the duck clips (travel capped at MD_DUCK_CAP)
static int g_mdg_conf;            // the running combat dodge is a CONFINED clip picked for a duel (authored travel 0.05-0.6 m, played unscaled)
static int mdg_pick_combat(uint32_t slot) {
    g_mdg.combat_clip = 0; g_mdg.combat_move = 0; g_mdg.combat_dir = 3;
    if (mdg_combat_off()) return 0;
    uint8_t cls = g_mdg.sw[slot].cls, hand = g_mdg.sw[slot].hand;
    {   // The measured class of the partner's running duel row (mdl_tick) replaces the announced guess
        int prow = mdu_partner_row_now(slot); uint8_t lc, lh;
        if (!mdl_off() && prow >= 0 && mdl_row_lookup(prow, &lc, &lh)) { cls = lc; hand = lh; g_mdg.sw[slot].cls = lc; g_mdg.sw[slot].hand = lh; g_mdg.sw[slot].hand_real = 1; xlog("dodge: pick uses the measured class of %s: %s, %s hand", mdu_row_name(prow),lc == 2 ? "upward" : lc == 1 ? "downward" : "horizontal", lh ? "right" : "left"); }
    }
    const char *side = hand ? "left" : "right";               // a right-handed blow comes from our left (we face each other)
    static const char *const ANG[3] = {"horiz", "downward", "upward"};
    static const char *const DIRN[4] = {"forward", "left", "right", "back"};
    float sx, sy; int dir = mdg_stick_dir(&sx, &sy);
    if (dir != 0 && g_mdr.slot == (int)slot && g_mdr.ms && GetTickCount64() - g_mdr.ms < 300 && g_mdr.room[dir] < MD_ROOM_MIN) {
        // the stick points into a wall / off a ledge: the freest of the other two (a sideways one toward the blow's known side would be "into the blow": skipped)
        int real0 = g_mdg.sw[slot].hand_real, bside = hand ? 1 : 2, alt = -1; float best = MD_ROOM_MIN;
        for (int i = 1; i < 4; i++) { if (i == dir || (real0 && i == bside)) continue; if (g_mdr.room[i] > best) { best = g_mdr.room[i]; alt = i; } }
        static const char *const DN[4] = {"forward", "left", "right", "back"};
        xlog("dodge: %s has %.2f m of room (left %.2f right %.2f back %.2f) - %s", DN[dir], g_mdr.room[dir], g_mdr.room[1], g_mdr.room[2], g_mdr.room[3], alt > 0 ? DN[alt] : "no better side: the clip plays where we stand");
        if (alt > 0) dir = alt;
    }
    // the dodge is prioritized to be the low duck sideways dodges rather than full blown backwards dodges - a clean MMA style dodge,
    // the dodger dodging under the swing. The deepest sideways ducks of TLOU2's player dodges (decoded poses, anim-melee-player-shared-t2: head drop
    // 0.65-0.91 m in the first 0.1-0.5 s, the root still within ~0.3 m when the head is down): a stick left / right keeps its side, anything else ducks
    // away from the blow's side (the freer side when that one is walled); the slide after the duck is capped at MD_DUCK_CAP. t2r-no-duck-dodge.txt = off.
    g_mdg_duck = 0; g_mdg_conf = 0;
    // Inside a melee DUEL (melee_duel.c): SP's in-melee dodge is the short, clean one (SP recorder: 0.38-1.12 m in 440-680 ms, held on the attacker's axis; the free open dodge is 1.7-2.3 m).
    // The only authored low-travel dodge clips are ellie-1h-dodge-<back|left|right>-combat-confined-<a..c> (root travel 0.05-0.59 m): played UNSCALED, so no
    // foot slide from squeezing a 2 m clip into the duel spacing. Stick left / right / back as pressed; forward or no stick ducks away from the blow. t2r-no-duel-confined.txt = off.
    // Live clips: the confined clips read as a stumble (0.05-0.21 m, pinned in place) - the directional dodges are used instead.
    // Off by default now; t2r-duel-confined.txt brings them back. In a duel the directional contextual pick below runs instead (no duck list).
    int duel = mdu_dodge_cap() > 0.0f;
    if (duel && GetFileAttributesA("t2r-duel-confined.txt") != INVALID_FILE_ATTRIBUTES) {
        int dc = dir == 1 || dir == 2 ? dir : dir == 0 ? (hand ? 2 : 1) : 3;
        static unsigned crot;
        for (int i = 0; i < 3; i++) {
            char cn[96]; int v = (int)((crot + (unsigned)i) % 3);
            snprintf(cn, sizeof cn, "ellie-1h-dodge-%s-combat-confined-%c", DIRN[dc], 'a' + v);
            uint64_t clip = fnv64_rt(cn);
            if (mdg_clip_len(clip) <= 0.0f) continue;
            crot += (unsigned)i + 1;
            g_mdg.combat_dir = dc; g_mdg.combat_clip = clip; g_mdg.combat_move = 0; g_mdg_conf = 1;
            snprintf(g_mdg.combat_name, sizeof g_mdg.combat_name, "%s", cn);
            xlog("DUEL: dodge - SP in-melee dodge: stick (%.2f, %.2f) -> CONFINED %s, %s (authored short travel, unscaled, facing the attacker)", sx, sy, DIRN[dc], cn);
            return 1;
        }
        static int ncf; if (LOGCAP(ncf, 6)) xlog("DUEL: dodge - no confined clip loaded for %s: duck / contextual pick (travel capped %.2f m)", DIRN[dc], (double)mdu_dodge_cap());
    }
    if (duel && dir == 0) {     // no stick / forward in a duel: sidestep away from the blow's side (a right-handed blow comes from our left -> right), the freer side when walled
        dir = hand ? 2 : 1;
        if (g_mdr.slot == (int)slot && g_mdr.ms && GetTickCount64() - g_mdr.ms < 300 && g_mdr.room[dir] < MD_ROOM_MIN && g_mdr.room[3 - dir] > g_mdr.room[dir]) dir = 3 - dir;
        xlog("DUEL: dodge - no stick: directional %s, away from the blow", DIRN[dir]);
    }
    // ps48 (the dodges did not feel like SP's dodges; measured: 6 of 6 duel dodges with no stick
    // = 'dodge back', clips back-* scaled x0.53-0.66 to SP's 1.17 m = the feet walk 2.1 m while the body moves 1.2 m): with NO stick in a duel the blow's class picks the dodge
    // the way a boxer reads it - a hook or an overhand is slipped to the side AWAY from the striking hand (side clips: authored ~1.9 m to SP's 1.45 m = x0.75, less slide),
    // an uppercut / kick is leaned back from; every 3rd hook still goes back (variety). A held stick is never overridden; a walled side keeps back. Away from the blow =
    // never "into the blow" (the immunity rule is unchanged). t2r-dodge-dir-ps48-old.txt = old (no stick = back). Proof line "ps48 dodge".
    if (duel && dir == 3 && sx * sx + sy * sy < 0.09f && cls != 2 && !mdg48_off()) {
        static unsigned hrot;
        int sd = hand ? 2 : 1, walled = g_mdr.slot == (int)slot && g_mdr.ms && GetTickCount64() - g_mdr.ms < 300 && g_mdr.room[sd] < MD_ROOM_MIN;
        int keep = cls == 0 && (hrot++ % 3) == 2;
        if (!walled && !keep) dir = sd;
        xlog("DUEL: ps48 dodge - no stick, %s blow from the %s: %s%s", ANG[cls], side, DIRN[dir], walled ? " (the slip side is walled: back)" : keep ? " (every 3rd hook: back, variety)" : " - slipped away from the striking hand");
    }
    if (!duel && GetFileAttributesA("t2r-no-duck-dodge.txt") == INVALID_FILE_ATTRIBUTES) {
        static const char *const DUCK_R[] = {"ellie-1h-dodge-right-combat-horiz-right-c", "ellie-1h-dodge-right-combat-upward-left-b", "ellie-1h-dodge-right-combat-upward-left-a",
                                             "ellie-1h-dodge-right-combat-horiz-right-a", "ellie-1h-dodge-right-combat-horiz-right-b", "ellie-2h-dodge-combat-right-horiz-right-a"};
        static const char *const DUCK_L[] = {"ellie-1h-dodge-left-combat-horiz-right-b", "ellie-1h-dodge-left-combat-upward-right-a", "ellie-1h-dodge-left-combat-horiz-left-a",
                                             "ellie-1h-dodge-left-combat-downward-right-e", "ellie-1h-dodge-left-combat-horiz-left-b", "ellie-1h-dodge-left-combat-horiz-right-a"};
        int dd = dir == 1 || dir == 2 ? dir : (hand ? 2 : 1);      // away from the blow: a right-handed blow comes from our left -> duck right
        if (dir != 1 && dir != 2 && g_mdr.slot == (int)slot && g_mdr.ms && GetTickCount64() - g_mdr.ms < 300 && g_mdr.room[dd] < MD_ROOM_MIN && g_mdr.room[3 - dd] > g_mdr.room[dd]) dd = 3 - dd;
        const char *const *L = dd == 2 ? DUCK_R : DUCK_L;
        static unsigned drot;
        for (int i = 0; i < 6; i++) {
            const char *nm = L[i < 3 ? (drot + (unsigned)i) % 3 : (unsigned)i];   // the 3 deepest rotate, the rest are fallbacks
            uint64_t clip = fnv64_rt(nm);
            if (mdg_clip_len(clip) <= 0.0f) continue;
            drot++;
            g_mdg.combat_dir = dd; g_mdg.combat_clip = clip; g_mdg.combat_move = 0; g_mdg_duck = 1;
            snprintf(g_mdg.combat_name, sizeof g_mdg.combat_name, "%s", nm);
            xlog("dodge: stick (%.2f, %.2f) -> DUCK %s under the blow from the %s: %s", sx, sy, DIRN[dd], side, nm);
            return 1;
        }
        static int nl; if (LOGCAP(nl, 10)) xlog("dodge: no duck clip loaded for %s - the contextual pick", DIRN[dd]);
    }
    g_mdg.combat_dir = dir;
    // into the blow: forward at the attacker, or sideways toward the side the blow comes from - no immunity (the dodge still plays, the blow lands as normal)
    // only a forward dodge (at the attacker) is judged "into the blow" while the hand is a guess; the sideways rule needs a real side from the attacker's move -> hand table
    int real = g_mdg.sw[slot].hand_real;
    int into = dir == 0 || (real && ((dir == 1 && !strcmp(side, "left")) || (dir == 2 && !strcmp(side, "right"))));
    xlog("dodge: stick (%.2f, %.2f) -> dodge %s; blow %s from the %s%s%s", sx, sy, DIRN[dir], ANG[cls], side, real ? "" : " (side guessed: sideways stays immune)", into ? " - INTO the blow - no immunity" : "");
    if (into) { g_mdg.iframe_until = 0; }
    // The real SP successful dodges (SP traces, t2r-sp.log): vs a HUMAN the set player-contextual-dodges, moves player-contextual-dodge-<back|left|right>-<downward|horiz|upward>-<left|right>-<a..c>
    // (clips ellie-1h-dodge-<dir>-combat-<angle>-<side>-<v> with a 1h weapon); vs infected player-2h-contextual-dodge-<dir>-<upward|downward>-<side>-<v> - macro melee-player-contextual-dodge, picked
    // by the engine only during an NPC's swing TELL. Side = the attacker's lead foot / hand (NPC "lt" -> -left), angle = the swing's, dir = the stick. No forward one (a forward dodge plays the plain
    // open dodge). Candidates: stick dir + angle + side, other side, other angles; the human set first, the 2h set as the fallback. The clip comes from the move def (mstag_clip_of) or, when the
    // move has none, by its clip name (ellie-1h-dodge-...) - whichever is loaded in MP.
    if (dir == 0) { static int nl0; if (LOGCAP(nl0, 10)) xlog("dodge: forward dodge - no contextual move, the plain open dodge plays"); return 0; }
    static const char *const A3[3] = {"horiz", "downward", "upward"};
    const char *hs = hand ? "right" : "left";                     // the attacker's striking hand = the move's side
    const char *sides[2] = {hs, hand ? "left" : "right"};
    int order[3] = {cls, cls == 0 ? 2 : 0, cls == 1 ? 2 : 1};     // own angle, then the nearest others
    char mv[24][80], cl[24][80]; int n = 0;
    for (int ai = 0; ai < 3; ai++) for (int k = 0; k < 2; k++) {
        snprintf(mv[n], sizeof mv[0], "player-contextual-dodge-%s-%s-%s", DIRN[dir], A3[order[ai]], sides[k]);
        snprintf(cl[n], sizeof cl[0], "ellie-1h-dodge-%s-combat-%s-%s", DIRN[dir], A3[order[ai]], sides[k]); n++;
    }
    for (int ai = 0; ai < 3; ai++) for (int k = 0; k < 2; k++) {
        if (order[ai] == 0) continue;
        snprintf(mv[n], sizeof mv[0], "player-2h-contextual-dodge-%s-%s-%s", DIRN[dir], A3[order[ai]], sides[k]); cl[n][0] = 0; n++;
    }
    static unsigned rot;
    // ps48: in an SP duel dodge every variant of the class-matched group is scaled to SP's travel - the variant whose own travel is nearest to it slides the
    // least. The loadable variants of the first group that has any are ranked by |1 - k| and the best two alternate (variety). t2r-dodge-variant-ps48-old.txt = old (rotation).
    if (duel && !mdg_sp_off() && !mdg48v_off()) {
        static unsigned r48;
        for (int i = 0; i < n; i++) {
            uint64_t bc[5] = {0}, bm[5] = {0}; float bk[5]; char bn[5][96]; int nb = 0;
            for (int v = 0; v < 5; v++) {
                char nm[96], cn[96]; snprintf(nm, sizeof nm, "%s-%c", mv[i], 'a' + v);
                if (!strcmp(nm, "player-contextual-dodge-back-upward-right-b") && GetFileAttributesA("t2r-dodge-keep-urb-ps45-old.txt") == INVALID_FILE_ATTRIBUTES) continue;
                uint64_t m = fnv64_rt(nm), clip = mstag_clip_of(m);
                if ((!clip || mdg_clip_len(clip) <= 0.0f) && cl[i][0]) { snprintf(cn, sizeof cn, "%s-%c", cl[i], 'a' + v); clip = fnv64_rt(cn); if (mdg_clip_len(clip) <= 0.0f) clip = 0; }
                if (!clip || mdg_clip_len(clip) <= 0.0f) continue;
                float k = mdg48_k(clip, dir); if (k <= 0.0f) continue;
                float e = k < 1.0f ? 1.0f / k - 1.0f : k - 1.0f; int j = nb++;
                while (j > 0 && bk[j - 1] > e) { bk[j] = bk[j - 1]; bc[j] = bc[j - 1]; bm[j] = bm[j - 1]; memcpy(bn[j], bn[j - 1], 96); j--; }
                bk[j] = e; bc[j] = clip; bm[j] = m; snprintf(bn[j], 96, "%s", nm);
            }
            if (!nb) continue;
            int pk = nb > 1 ? (int)(r48++ & 1) : 0;
            g_mdg.combat_clip = bc[pk]; g_mdg.combat_move = bm[pk];
            snprintf(g_mdg.combat_name, sizeof g_mdg.combat_name, "%s", bn[pk]);
            xlog("DUEL: ps48 dodge variant %s (travel x%.2f of its own; %d loaded in %s, best two alternate%s%s)", bn[pk], (double)mdg48_k(bc[pk], dir), nb, mv[i],
                 nb > 1 ? ", other " : "", nb > 1 ? bn[pk ^ 1] : "");
            return 1;
        }
    }
    for (int i = 0; i < n; i++) {
        for (int v = 0; v < 5; v++) {
            char nm[96], cn[96]; int vv = (int)((rot + (unsigned)v) % 5);
            snprintf(nm, sizeof nm, "%s-%c", mv[i], 'a' + vv);
            // ps45 item 4 (rec44a B: all three plays of player-contextual-dodge-back-upward-right-b, [9051] / [10261] / [19815], show 'BODY TURN 4f slot 1 (us) drawn hips
            // -44 / -42 / -47 deg, shoulders -38 / -45 / -41 deg within 4 frames (root -1 / -1 / +1 deg)' 13-14 frames in, the only writer dodge.pin (position): the turn
            // is in the clip's own pose (no other variant played in the session shows it) = the review's F at 25.167 / 187.83 B (own fighter to chest-to-camera in one
            // frame). The variant is dropped from the pick (melee variety rule: variants may be dropped; the other back-upward variants stay). The clip's joint track is
            // not decoded here (only its root: re/melee-dodge-rootmotion.md). t2r-dodge-keep-urb-ps45-old.txt = old (kept).
            if (!strcmp(nm, "player-contextual-dodge-back-upward-right-b")) {
                static int off45 = -1; static uint64_t at45; static int nl45;
                if (off45 < 0 || GetTickCount64() - at45 > 2000) { at45 = GetTickCount64(); int o = GetFileAttributesA("t2r-dodge-keep-urb-ps45-old.txt") != INVALID_FILE_ATTRIBUTES;
                    if (o != off45) xlog("dodge: ps45 variant drop player-contextual-dodge-back-upward-right-b %s", o ? "OFF (t2r-dodge-keep-urb-ps45-old.txt): picked as before" : "on (its own pose turns ~45 deg in 4 frames 0.22 s in)"); off45 = o; }
                if (!off45) { if (LOGCAP(nl45, 20)) xlog("dodge: %s skipped (ps45: the clip's pose turns ~45 deg in 4 frames 0.22 s in) - the next variant", nm); continue; }
            }
            uint64_t m = fnv64_rt(nm), clip = mstag_clip_of(m);
            if ((!clip || mdg_clip_len(clip) <= 0.0f) && cl[i][0]) { snprintf(cn, sizeof cn, "%s-%c", cl[i], 'a' + vv); clip = fnv64_rt(cn); if (mdg_clip_len(clip) <= 0.0f) clip = 0; }
            if (!clip || mdg_clip_len(clip) <= 0.0f) continue;
            rot++;
            g_mdg.combat_clip = clip; g_mdg.combat_move = m;
            snprintf(g_mdg.combat_name, sizeof g_mdg.combat_name, "%s", nm);
            return 1;
        }
    }
    static int nl; if (LOGCAP(nl, 20)) xlog("dodge: combat dodge - no contextual dodge move / clip loaded for %s dodges vs %s blows from the %s (attacker hand %s): plain engine dodge stays", DIRN[dir], ANG[cls], side, hand ? "right" : "left");
    return 0;
}
static void psync_layer_snap(const char *tag, uint64_t ent);   // paired.c
static int g_mdg_probe;   // ps41: frames left of the dodge-entry layer probe
// the combat-dodge clip + our capped sidestep (once, from the tick: when the engine's own dodge move showed or 60 ms passed)
static void mdg_combat_play(void) {
    if (g_mdg_late_ms && GetTickCount64() - g_mdg_late_ms < 400) { xlog("dodge: combat dodge skipped - the blow was TOO LATE for this press and already lands (Fable rec5 14.86 / 97.65: we ducked on our screen while the hit showed on theirs)"); g_mdg.combat_clip = 0; return; }
    float mb[16]; const float *ml = uc4_my_loc(mb);
    if (!ml || !__builtin_isfinite(ml[0])) { g_mdg.combat_clip = 0; return; }
    if (mdg_is_dodge_move(g_ms_curmove)) {
        uint64_t me = SID_PLAYER, c = dc_call(0x394888944e949d5fULL /* cancel-melee-action */, 1, &me);
        xlog("dodge: combat dodge - engine dodge move %llx cancelled (%llx) so its root motion cannot carry us", (unsigned long long)g_ms_curmove, (unsigned long long)c);
    }
    mdu_swing_dodge_cancel();   // melee core: our own duel swing record (its warp + contact) stops - the dodge is the one mover of our body
    // ps41 dodge-entry probe (the own body is in the dodge's folded pose within 1-3 video frames although animate_ gets a 0.30 s
    // blend; no own swing, no engine dodge move, no stance clip, no teleport on those frames): the body's anim layers (instances, weights, fades) right before
    // and after animate_ and on the next frames (mdg_combat_tick), first 12 dodges of a session. Measurement only - no behaviour change.
    static int nprobe; g_mdg_probe = nprobe < 12 ? (nprobe++, 5) : 0;
    if (g_mdg_probe) psync_layer_snap("dodge entry probe: before animate_ (ps41)", SID_PLAYER);
    uint64_t r = mdg_animate_sid(g_mdg.combat_clip);
    if (g_mdg_probe) psync_layer_snap("dodge entry probe: after animate_, blend 0.30 s asked (ps41)", SID_PLAYER);
    int spm = !g_mdg_conf && !g_mdg_duck && mdu_dodge_cap() > 0.0f && !mdg_sp_off();   // SP duel dodge (see MDS_TRAVEL_M)
    if (r != ~0ULL) mdg_dodge_say_at(T2R_MAX_PEERS, SID_PLAYER, spm ? 150 : 0);
    float clen = mdg_clip_len(g_mdg.combat_clip);
    uint64_t hold = clen > 0.2f ? (uint64_t)(clen * MD_CLIP_FRAC * 1000.0f) : 600; if (hold > MD_CLIP_MAX_MS) hold = MD_CLIP_MAX_MS; if (hold < 450) hold = 450;
    float trav = clen > 0.2f ? clen * 0.45f : 0.42f; if (trav < 0.32f) trav = 0.32f; if (trav > 0.55f) trav = 0.55f;   // the travel part of the clip (was a fixed 0.2 s: the abrupt jerk)
    g_mdg.cmb_hold_ms = hold; g_mdg.cmb_land_ms = (uint64_t)(trav * 1000.0f);
    float fx = 2.0f * (ml[4] * ml[6] + ml[7] * ml[5]), fz = 1.0f - 2.0f * (ml[4] * ml[4] + ml[5] * ml[5]), fl = __builtin_sqrtf(fx * fx + fz * fz);
    if (fl > 1e-3f) {
        fx /= fl; fz /= fl;
        // the dodge's axis is the line attacker -> us (some dodges "looked janky": left / right / back were taken from where our body happened to point)
        float ax = -fx, az = -fz, pb[16];
        uint8_t *pe = mdg_peer((uint32_t)g_mdg.last_slot);
        const float *pl = g_mdg.last_slot >= 0 && pe && *(uint64_t *)(pe + 0x60) ? puppet_locator(*(uint64_t *)(pe + 0x60), pb) : NULL;
        if (pl && __builtin_isfinite(pl[0])) { float vx = ml[0] - pl[0], vz = ml[2] - pl[2], vl = __builtin_sqrtf(vx * vx + vz * vz); if (vl > 0.05f) { ax = vx / vl; az = vz / vl; } }
        float dd[4][2]; mdg_room_dirs(ax, az, dd);
        int di = g_mdg.combat_dir >= 0 && g_mdg.combat_dir < 4 ? g_mdg.combat_dir : 3;
        float d[2][2] = {{dd[di][0], dd[di][1]}, {0, 0}}, tot[2] = {di == 3 ? 0.8f : di == 0 ? 0.4f : MD_STEP_M, 0.0f};
        const MdgRm *rm = mdg_rm_find(g_mdg.combat_clip);
        float rmx = 0, rmz = 0, rmy = 0, rml = 0, fwx = -ax, fwz = -az;
        if (rm) {
            mdg_rm_at(rm, rm->dur, &rmx, &rmz, &rmy); rml = __builtin_sqrtf(rmx * rmx + rmz * rmz);
            if (g_mdg_conf && rml <= 0.05f) { tot[0] = rml; rm = NULL; }     // a confined clip that barely moves: play it in place, no invented step
            else if (rml > 0.05f) {
                d[0][0] = (rmx * -fwz + rmz * fwx) / rml; d[0][1] = (rmx * fwx + rmz * fwz) / rml; tot[0] = rml < MD_RM_CAP ? rml : MD_RM_CAP;
                if (g_mdg_duck && tot[0] > MD_DUCK_CAP) tot[0] = MD_DUCK_CAP;
                for (int i = 1; i <= rm->n; i++) {     // landing = 90 % of the authored travel: input may take over from there
                    float t = rm->dur * (float)i / (float)rm->n, x, z, y; mdg_rm_at(rm, t, &x, &z, &y);
                    if (x * x + z * z >= 0.81f * rml * rml) { g_mdg.cmb_land_ms = (uint64_t)(t * 1000.0f); break; }
                }
            } else rm = NULL;
        }
        if (g_mdg_conf && !rm) tot[0] = 0.2f;     // (no table row for a confined clip: a token step)
        float sp_th = (float)hold / 1000.0f, sp_rmh = 0.0f, sp_u[2] = {0, 0};
        float spe = g_mdg.combat_dir == 1 || g_mdg.combat_dir == 2 ? MDS_SP_END_SIDE_M : MDS_SP_END_M;     // SP's travel: side 1.45 m, back 1.17 m
        if (spm && rm) {    // SP duel dodge: the WHOLE clip's root motion scaled by one k so it ends at SP's travel on its flat part; held (and released) there
            sp_th = mdg_sp_flat_s(rm);
            float hx, hz, hy; mdg_rm_at(rm, sp_th, &hx, &hz, &hy); sp_rmh = __builtin_sqrtf(hx * hx + hz * hz);
            if (sp_rmh > 0.05f) {
                hold = (uint64_t)(sp_th * 1000.0f); g_mdg.cmb_hold_ms = hold;
                sp_u[0] = (hx * -fwz + hz * fwx) / sp_rmh; sp_u[1] = (hx * fwx + hz * fwz) / sp_rmh;
                d[0][0] = sp_u[0]; d[0][1] = sp_u[1]; tot[0] = spe; if (mds_full()) { spe = sp_rmh; tot[0] = sp_rmh; }   // (the clip's own travel)
                for (int i = 1; i <= rm->n; i++) {     // landing = 95 % of the travel: the stick / aim may take over from there (<= ~0.1 m authored root motion left for the blend-out)
                    float t = sp_th * (float)i / (float)rm->n, x, z, y; mdg_rm_at(rm, t, &x, &z, &y);
                    if (x * x + z * z >= 0.9025f * sp_rmh * sp_rmh) { g_mdg.cmb_land_ms = (uint64_t)(t * 1000.0f); break; }
                }
            } else spm = 0;
        } else spm = 0;
        if (!spm) { float dcap = mdu_dodge_cap(); if (dcap > 0.0f && !g_mdg_conf && tot[0] > dcap) { xlog("dodge: duel - travel capped %.2f -> %.2f m (the dodger stays in the sequence at duel spacing, facing the attacker)", tot[0], dcap); tot[0] = dcap; } }
        mdg_mv_begin(&g_md_fb, "combat dodge step", 1, d, tot);
        g_md_fb.pin = 1; g_md_fb.hold_until = GetTickCount64() + hold;
        g_md_fb.dur60 = (int)(trav * 60.0f + 0.5f); g_md_fb.face = 1;
        g_md_fb.rm = rm; g_md_fb.rm_fx = fwx; g_md_fb.rm_fz = fwz; g_md_fb.rm_len = rml;
        if (spm && g_md_fb.on) {
            g_md_fb.spm = 1; g_md_fb.sp_th = sp_th; g_md_fb.sp_rmh = sp_rmh; g_md_fb.sp_u[0] = sp_u[0]; g_md_fb.sp_u[1] = sp_u[1];
            g_md_fb.sp_D = 0.0f; g_md_fb.sp_lim0 = -1.0f; g_md_fb.sp_spc0 = -1.0f; g_md_fb.sp_auth = rml;
            float x7, z7, y7; mdg_rm_at(rm, 0.7f, &x7, &z7, &y7);
            xlog("sdodge: %s - SP in-melee dodge: whole clip scaled x%.2f, %.2f m at its flat part %llu ms (authored %.2f m there, %.2f m in all), %.2f m at 700 ms (SP 0.93-1.13), stick / aim from %llu ms; end spacing to the attacker <= %.2f m, >= %.2f m travel",
                 g_mdg.combat_name, spe / sp_rmh, spe, (unsigned long long)hold, sp_rmh, rml, spe * __builtin_sqrtf(x7 * x7 + z7 * z7) / sp_rmh,
                 (unsigned long long)(g_mdg.cmb_land_ms > 560 ? g_mdg.cmb_land_ms : 560), MDS_SPC_END, MDS_MIN_M);
        }
        xlog("dodge: combat dodge travel %s (%.2f m authored, cap %.2f m, lands at %llu ms, clip held %llu ms)", rm ? "follows the clip's root motion" : "eased step (clip not in the root-motion table)", rml, tot[0], (unsigned long long)g_mdg.cmb_land_ms, (unsigned long long)hold);
        g_md_fb.yaw0 = __builtin_atan2f(fx, fz); g_md_fb.yaw1 = __builtin_atan2f(-ax, -az);
    }
    if (g_mdg_heavy_ms && g_mdg_heavy_ms == g_mdg.press_ms) {      // ps36 heavy dodge: the clip slower, every time of it longer by the same factor
        dtl_speed_s(SID_PLAYER, g_mdg.combat_clip, MDG_HEAVY_RATE, MO_SRC("dodge.heavy"));
        g_mdg.cmb_hold_ms = (uint64_t)((float)g_mdg.cmb_hold_ms / MDG_HEAVY_RATE); g_mdg.cmb_land_ms = (uint64_t)((float)g_mdg.cmb_land_ms / MDG_HEAVY_RATE);
        if (g_md_fb.on && g_md_fb.pin) { g_md_fb.heavy = 1; g_md_fb.hold_until = GetTickCount64() + g_mdg.cmb_hold_ms; g_md_fb.dur60 = (int)((float)g_md_fb.dur60 / MDG_HEAVY_RATE + 0.5f); }
        xlog("dodge: heavy dodge clip %llx at x%.2f, held %llu ms, lands at %llu ms (ps36)", (unsigned long long)g_mdg.combat_clip, (double)MDG_HEAVY_RATE, (unsigned long long)g_mdg.cmb_hold_ms, (unsigned long long)g_mdg.cmb_land_ms);
    }
    g_mdg.cmb_on = 1; g_mdg.cmb_lastp = 1; g_mdg.cmb_ms = GetTickCount64(); g_mdg.cmb_sid = g_mdg.combat_clip;
    g_mdg.tr_until = GetTickCount64() + 700; g_mdg.tr_clip = NULL; g_mdg.tr_from[0] = ml[0]; g_mdg.tr_from[1] = ml[2];
    xlog("dodge: combat dodge %s (move %llx, clip %llx, animate_ -> %llx), step %.1f m %s", g_mdg.combat_name, (unsigned long long)g_mdg.combat_move, (unsigned long long)g_mdg.combat_clip, (unsigned long long)r, MD_STEP_M,
         g_mdg.combat_dir == 1 ? "left" : g_mdg.combat_dir == 2 ? "right" : g_mdg.combat_dir == 3 ? "back" : "forward");
    g_mdg.combat_clip = 0; g_mdg.mode = 3;
}
// Control back early: after the i-frames, any move stick / aim / melee input blends the clip out (0.15 s) and locomotion returns; with no input the clip is cut at MD_CLIP_MAX_MS.
// (the pin of the step ends with it)
// v5-geo2 (B [18804]-[18810]: 'clip released' then the body went 0.42 + 0.30 + 0.16 m in 3 frames with no ext writer - 0.70 m = the clip's authored 1.89 m x (1 - 0.63),
// the part our scale took out): the pin moves the body with set-object-locator, but the engine's player state (character controller / locomotion, and the net
// position) keeps following the clip's UNSCALED root motion. Once the pin let go at the release, the engine put the body back on its own spot - the "slid
// 0.33 / 0.73 m past the release spot". Like psync's hand-off (paired.c), the player state is moved onto the pinned spot with teleport-player: after the
// release blend when the clip ran out (the body held on the spot meanwhile, so the blend-out keeps its pose), or at once on a move / aim / melee / counter input.
static struct { int on; uint64_t until; float l[8]; } g_mdg_sync;
static uint64_t g_mdg_late_rel_ms;   // ps41: when a dodge clip was released by the attacker's TOO LATE ruling
static int g_mdg_sync40;    // ps40 D5: this release's sync always ends on teleport-player (mdg_combat_release)
static void mdg_sync_tick(uint64_t now) {
    if (!g_mdg_sync.on) return;
    if (match_substate() != 6 || g_downed || local_hp() <= 0.0f || mdg_busy()) { g_mdg_sync.on = 0; return; }
    // ps43 L1 (rec41a B, clip 178.2-178.8 s: [20950] 'combat dodge clip released', [20952]-[20957] 'own frame: 2 writers [duel.mdu_warp ..., dodge.sync_hold ...]',
    // [20957] 'psync: u0125c68f START from slot 1 ... role 2' (the parry clinch took our body 7 frames into the release blend), [20958] 'victim root ... placed 0.02
    // 0.48 ... err 0.20 m', [20962] 'sdodge: release sync - ... teleport-player', [20963] 'BODY TURN slot 0 (us) drawn hips +62 deg ... writers: teleport-player from
    // ext+2bb771 (dodge.sync_release); psync u0125c68f kind 6 t=99 ms', [20967] 'victim half's layer lost at t=167 ms', then 'victim root ... err 0.28 / 0.19 / 0.59 /
    // 1.00 m ... LOST' and the summary 'victim max 1.14 m (mean 0.57)': the release sync of the dodge BEFORE the pair kept writing our body onto the dodge's end
    // spot under the pair's glide and then teleport-player ended the parrier half's layer - our body stood in its old pose 0.3-0.6 m off the clinch while the
    // partner's puppet walked its clip into it). A paired move that has our body owns it: the dodge's hold and teleport end there, the pair's glide / hand-off place
    // the body and the player state. t2r-dodge-sync-in-pair-old.txt = old.
    if (psync_active() && GetFileAttributesA("t2r-dodge-sync-in-pair-old.txt") == INVALID_FILE_ATTRIBUTES) {
        xlog("sdodge: release sync dropped - the paired move u%08x has our body (role %d, %s the release blend's end): no hold write and no teleport-player under its half (ps43)",
             g_ps.uid, psync_role(), now < g_mdg_sync.until ? "before" : "at");
        g_mdg_sync.on = 0; return;
    }
    // ps45 (log [10142] 'YAW SNAP slot 1 turned 101 deg in 1 frame ... writers: set-object-locator from ext+2cbc2f (dodge.sync_hold)',
    // then [10143]-[10152] 'own frame: 2 writers [duel.mdu_warp ... (yaw 95..130), dodge.sync_hold ...]', [10153] 'YAW SNAP -115 deg ... (dodge.sync_release);
    // (duel.mdu_warp)', [10154] '+137 deg (duel.mdu_warp)'; the same at [10328] -58 / [10340] +56 / [10341] -54 (B 26.07-26.29 s) and A [16191] -66 / [16202] +66): the
    // release hold wrote the dodge's END ROTATION every frame for 197 ms and teleport-player put it back on the player state, while the next swing (the opener at
    // [10142]) already turned the body to the victim with mdu_warp - two yaw owners on one body. The hold is about the POSITION (the clip's unscaled root slide):
    // it keeps the live rotation now, and a swing of ours that has started owns the body (no hold write, no teleport under it - its warp places the body, like
    // the ps43 pair rule above). t2r-dodge-sync-yaw-ps45-old.txt = old.
    {   static int off45 = -1; static uint64_t chk45;
        if (!ov_off("t2r-dodge-sync-yaw-ps45-old.txt", &off45, &chk45)) {
            if (mdu_swinging()) {
                static int nl45s; if (LOGCAP(nl45s, 40)) xlog("sdodge: ps45 release sync dropped - our swing owns the body (%s the release blend's end): no hold write, no teleport-player under it", now < g_mdg_sync.until ? "before" : "at");
                g_mdg_sync.on = 0; return;
            }
            float lb45[16]; const float *lv = player_locator(lb45);
            if (lv && ps_loc_ok(lv)) {
                float dy = (dm_yaw_of(lv) - dm_yaw_of(g_mdg_sync.l)) * 57.2957795f; while (dy > 180.0f) dy -= 360.0f; while (dy < -180.0f) dy += 360.0f;
                static int nl45y; if ((dy > 20.0f || dy < -20.0f) && LOGCAP(nl45y, 40)) xlog("sdodge: ps45 release %s keeps the live yaw (%.0f deg off the stored end rotation; position only)", now < g_mdg_sync.until ? "hold" : "teleport", (double)dy);
                memcpy(g_mdg_sync.l + 4, lv + 4, 4 * sizeof(float));
            }
        }
    }
    if (now < g_mdg_sync.until) { static psync_bf bf; psync_bf_from_loc(&bf, g_mdg_sync.l); mo_write(SID_PLAYER, &bf, MO_SRC("dodge.sync_hold"), 0); return; }
    if (mdg_ctrl_followed() && !g_mdg_sync40) { static int nl_; if (LOGCAP(nl_, 20)) xlog("sdodge: release sync not needed - the controller followed the pinned path (%u steps), no teleport-player", g_mdpin.n_used); g_mdg_sync.on = 0; return; }
    mo_teleport(g_mdg_sync.l, g_mdg_sync.l + 4, MO_SRC("dodge.sync_release"), 0);
    xlog("sdodge: release sync - the engine's player state put on the dodge's end spot %.2f %.2f %.2f (teleport-player after the %.0f ms blend; it had followed the clip's unscaled root)",
         g_mdg_sync.l[0], g_mdg_sync.l[1], g_mdg_sync.l[2], MD_RELEASE_BLEND * 1000.0f);
    g_mdg_sync.on = 0;
}
static void mdg_combat_release(const char *why, uint64_t now) {
    // ps40 D5 (rec39a B [18802] 'sdodge: ... travel 1.17 m in 1391 ms ... - done', 'combat dodge step moved 1.17 m of 1.17 planned', 'clip released after 1391 ms (clip
    // done)', [18832] 'after release (done, 30 frames): slid 0.47 m past the release spot'; 0.47 / 0.47 / 0.64 / 0.77 m in this run, and not one 'release sync' line
    // in either log): the mover's own report (mdg_sp_report, same frame, just before this) clears its spm flag, so the test below was false for every dodge whose
    // step ran to its end - no hold through the release blend, no player-state sync, and the clip's remaining root travel (authored 1.57 m against the 1.17 m we
    // allow) carried the body on. A step that reported 'done' for this clip counts as on, and its sync always ends on the engine's own teleport-player onto the
    // held spot (the 'controller followed' shortcut skipped it). t2r-dodge-release-sync-ps39.txt = old.
    int rs40 = !(g_md_fb.on && g_md_fb.spm) && g_mds_set.on && g_mds_set.t0 == g_md_fb.ms0 && GetFileAttributesA("t2r-dodge-release-sync-ps39.txt") == INVALID_FILE_ATTRIBUTES;
    g_mdg_sync40 = rs40;
    if (rs40) { static int nl40; if (LOGCAP(nl40, 40)) xlog("sdodge: release (%s) after the step's own end - the body is held on its spot through the %.0f ms release blend, then the player state is put on it (ps40: this release had no sync)", why, MD_RELEASE_BLEND * 1000.0f); }
    if ((g_md_fb.on && g_md_fb.spm) || rs40) {
        float lb[16]; const float *l = player_locator(lb);
        if (l && ps_loc_ok(l)) {
            memcpy(g_mdg_sync.l, l, sizeof g_mdg_sync.l);
            if (mdg_ctrl_followed() && strcmp(why, "clip done")) { g_mdg_sync.on = 0; }     // (input release: the controller is already on the path)
            // ps41 (rec40a B [18270] 'release sync at the TOO LATE ruled by the attacker (teleport-player ...)', [18300] 'slid 1.16 m past the release spot'; frames
            // 114.00-114.40: our body frozen, the puppet on the other screen moved 1.2 m with no leg motion): a dodge the attacker ruled too late gets NO
            // teleport-player - the blow lands, the hit pair takes the body from where it is (0.20 s entry blend, ps_take_other40). t2r-late-dodge-tp-ps40.txt = old.
            else if (!strncmp(why, "TOO LATE", 8) && GetFileAttributesA("t2r-late-dodge-tp-ps40.txt") == INVALID_FILE_ATTRIBUTES) { g_mdg_sync.on = 0; g_mdg_late_rel_ms = now; xlog("sdodge: release at the %s - no teleport-player, the body stays where it is for the hit pair (ps41)", why); }
            else if (strcmp(why, "clip done")) { mo_teleport(g_mdg_sync.l, g_mdg_sync.l + 4, MO_SRC("dodge.combat_release"), 0); xlog("sdodge: release sync at the %s (teleport-player onto the dodge's end spot at once: the input owns the body, no held blend)", why); g_mdg_sync.on = 0; }
            else { g_mdg_sync.on = 1; g_mdg_sync.until = now + (uint64_t)(MD_RELEASE_BLEND * 1000.0f) + 17; }
        }
    }
    uint64_t a[5] = {SID_PLAYER, ANIM_LAYER, 0, g_mdg.cmb_sid, 0}; float sec = MD_RELEASE_BLEND; memcpy(&a[2], &sec, 4);
    uint64_t r = dc_call(fnv64("stop-animating"), 5, a);
    xlog("dodge: combat dodge clip released after %llu ms (%s) - locomotion back (stop-animating -> %llx)", (unsigned long long)(now - g_mdg.cmb_ms), why, (unsigned long long)r);
    if (g_md_fb.on) mdg_sp_report(&g_md_fb, why);
    if (!strcmp(why, "counter press")) mdg_settle_end("counter press");
    g_mdg.cmb_on = 0; g_md_fb.on = 0; g_md_fb.pin = 0;
    g_mdg_rel_t60 = g_t60 ? g_t60 : 1;
    // v5-dgdraw (a dodge made the melee weapon holster, weirdly on top of that; log 16664-16729: the dodge clip's put-away actions were refused,
    // but the item controller kept its Holster request raised past the 0.6 s hold, then it passed and the holster debt stowed the bat): the held melee item is
    // drawn again at the release (instant draw of the held item = the controller wants it out, its Holster request drops) and the debt is cleared.
    // t2r-no-dodge-redraw.txt = off.
    if (hfix_hold_item_held() && GetFileAttributesA("t2r-no-dodge-redraw.txt") == INVALID_FILE_ATTRIBUTES) {
        uint64_t cw = current_weapon(), r = xr_draw(cw);
        if (g_hdebt_item) hdebt_clear("the dodge clip's put-away (held item re-drawn at the release)");
        xlog("dodge: held %llx re-drawn at the clip's release (its put-away / Holster request dropped) -> %llx", (unsigned long long)cw, (unsigned long long)r);
    }
}
static int padinj_press(const char *name, int ms);   // padinject.c (included after)
static uint64_t g_mdg_cbuf;   // C5: the last melee press made while the dodge clip commits (fires at the landing)
static void mdg_combat_tick(uint64_t now) {
    if (!g_mdg.cmb_on) return;
    int pv39 = g_ps.role == 2 && g_ps.ent_vic == SID_PLAYER && GetFileAttributesA("t2r-dodge-pin-under-pair-ps38.txt") == INVALID_FILE_ATTRIBUTES;   // ps39 B2: a pair's victim half took the body
    if (match_substate() != 6 || g_downed || mdg_busy() || pv39) {
        // (downed mid-dodge and could not crawl for the whole down; finishers lock the down into prone): this bail-out
        // dropped the state without stopping the held full-body dodge clip, which kept the body still (no 'clip released' line). The clip (only
        // its own sid) is stopped here too; no teleport sync, the down / paired move owns the body. t2r-no-dodge-bail-stop.txt = old behaviour.
        if (g_mdg.cmb_sid && GetFileAttributesA("t2r-no-dodge-bail-stop.txt") == INVALID_FILE_ATTRIBUTES) {
            uint64_t a[5] = {SID_PLAYER, ANIM_LAYER, 0, g_mdg.cmb_sid, 0}; float sec = MD_RELEASE_BLEND; memcpy(&a[2], &sec, 4);
            uint64_t r = dc_call(fnv64("stop-animating"), 5, a);
            xlog("dodge: combat dodge clip stopped after %llu ms (%s) - not left on the body (stop-animating -> %llx)", (unsigned long long)(now - g_mdg.cmb_ms),
                 g_downed ? "downed" : mdg_busy() ? "paired move" : pv39 ? "a pair's victim half took the body (ps39)" : "match state", (unsigned long long)r);
            g_mdg_rel_t60 = g_t60 ? g_t60 : 1;
        }
        g_mdg.cmb_on = 0; g_md_fb.on = 0; g_md_fb.pin = 0; return;
    }
    uint64_t el = now - g_mdg.cmb_ms;
    if (g_mdg_probe > 0) { g_mdg_probe--; char tg[96]; snprintf(tg, sizeof tg, "dodge entry probe: +%d ms into the clip, phase %.3f (ps41)", (int)el, (double)psync_phase(SID_PLAYER, g_mdg.cmb_sid)); psync_layer_snap(tg, SID_PLAYER); }
    if (g_mdg_heavy_ms && g_mdg_heavy_ms == g_mdg.press_ms && el < 120 && g_mdg.cmb_sid) dtl_speed_s(SID_PLAYER, g_mdg.cmb_sid, MDG_HEAVY_RATE, MO_SRC("dodge.heavy"));   // (ps36: a rate set on the creating frame may not stick)
    if (el >= (g_mdg.cmb_hold_ms ? g_mdg.cmb_hold_ms : MD_CLIP_MAX_MS)) { mdg_combat_release("clip done", now); return; }
    // the dodge counter's press: the counter window (+400..+1000 ms) sits inside the held dodge clip (lands ~935-1125 ms), where the engine cannot start the swing that
    // dc_swing_start waits for - so a fresh melee press in the window releases the clip and starts the counter here
    int mp = pad_melee_cmd() || padinj_mel_held() || (game_focused() && (GetAsyncKeyState(0x46) & 0x8000));   // (v5-pinpress: + the pad bit - a melee-attack block hides the engine command on a pad)
    int edge = mp && !g_mdg.cmb_lastp; g_mdg.cmb_lastp = mp;
    if (edge && now >= g_mdg.melee_ok_at && dc_armed_at(now)) { mdg_combat_release("counter press", now); dc_swing_start(); return; }
    // (a swing back cut the dodge animation): the melee button was free from +400 ms (MD_MELEE_OK_MS) while the clip travels to its
    // landing (cmb_land_ms, 830+ ms) - a swing started there stomped the dodge. The dodger commits to the clip until it lands; the only exception is the dodge counter's press
    // (handled above). The press is not buffered (no synthetic input). t2r-dodge-commit-old.txt = free from +400 ms.
    if (el < g_mdg.cmb_land_ms && !dc_armed_at(now) && GetFileAttributesA("t2r-dodge-commit-old.txt") == INVALID_FILE_ATTRIBUTES) {
        uint64_t mc[2] = {fnv64("melee-attack"), fnv64("melee-attack-shiv")};
        for (int i = 0; i < 2; i++) dc_call(fnv64("joypad-disable-commands"), 1, &mc[i]);
        if (edge) { g_mdg_cbuf = now; static int nc; if (LOGCAP(nc, 30)) xlog("dodge: melee press %llu ms into the dodge clip buffered (the last one only) - fires when it lands at %d ms", (unsigned long long)el, (int)g_mdg.cmb_land_ms); }
    } else if (g_mdg_cbuf) {   // the single buffered press fires at the landing frame (the game's own pad path, as the duel's buffered presses)
        uint64_t b = g_mdg_cbuf; g_mdg_cbuf = 0;
        if (el < g_mdg.cmb_land_ms + 400 && now - b < 900 && !mdg_busy() && padinj_press("melee-attack", 120)) xlog("dodge: the melee press buffered %llu ms ago fires at the landing", (unsigned long long)(now - b));
    }
    if (el < MD_IFRAME_MS || el < g_mdg.cmb_land_ms) return;     // input only takes over once the body has landed (no snap out mid-travel)
    if (el + 120 < g_mdg.cmb_hold_ms && el < 560) return;        // dodges were cut at 391 ms by the stick (a twitch, not a dodge) - the clip plays to ~560 ms first
    float sx, sy; mdg_stick_dir(&sx, &sy);
    int stick = sx * sx + sy * sy >= 0.3f * 0.3f;
    if (stick || pad_cmd_on("aim") || pad_melee_cmd()) mdg_combat_release(stick ? "move input" : "aim / melee input", now);
}
// client-side whiff: after our dodge press, the swinger's whoosh plays at ITS contact on our screen (swing start + window - 60 ms), not when its
// blow / RES arrives one-way later (mdg_whiff_whoosh dedups the late one, 400 ms per slot)
static struct { uint64_t at; uint32_t slot; } g_mdg_wpre;
static void mdg_whiff_pre_tick(uint64_t now) {
    if (!g_mdg_wpre.at || now < g_mdg_wpre.at) return;
    uint32_t sl = g_mdg_wpre.slot; g_mdg_wpre.at = 0;
    if (sl >= T2R_MAX_PEERS || !mdg_iframes(now)) return;
    uint8_t *wpl = t2r_peer(sl); mdg_whiff_whoosh(puppet_handle(sl), wpl && !IsBadReadPtr(wpl, 0x99) ? *(uint64_t *)(wpl + 0x91) : 0, (int)sl);
}
// more control for attack victims outside of pins - 2 consecutive attacks are dodgeable unless you get hit, then only one:
// dodge CHARGES. Two dodges in a row, the 2.5 s cooldown (and its bar) only after the last charge; a hit taken (our health dropped) cuts the charges to one.
// Both come back MD_COOLDOWN_MS after the last dodge AND the last hit.
#define MDG_CHARGES 2
static int g_mdg_ch = MDG_CHARGES; static uint64_t g_mdg_hit_ms; static float g_mdg_hp_last = -1.0f;
static void mdg_charges_refresh(uint64_t now) {
    if (g_mdg_ch < MDG_CHARGES && now >= g_mdg.last_dodge_ms + MD_COOLDOWN_MS && (!g_mdg_hit_ms || now >= g_mdg_hit_ms + MD_COOLDOWN_MS)) g_mdg_ch = MDG_CHARGES;
}
static void mdg_hit_watch(uint64_t now) {
    float hp = local_hp();
    if (g_mdg_hp_last > 0.0f && hp > 0.0f && hp < g_mdg_hp_last - 0.5f) {
        g_mdg_hit_ms = now;
        if (g_mdg_ch > 1) { g_mdg_ch = 1; xlog("dodge: hit taken (hp %.0f -> %.0f) - one dodge left until %d ms without a hit / dodge", (double)g_mdg_hp_last, (double)hp, MD_COOLDOWN_MS); }
    }
    g_mdg_hp_last = hp;
    mdg_charges_refresh(now);
}
static int g_mdg_whiff;   // the current mdg_start is a free duel dodge with no swing coming (no i-frames, longer lock)
static int g_mdg_heavy;   // ps36: the current mdg_start is the heavy dodge (see MDG_HEAVY_RATE)
static struct { uint32_t slot; uint64_t ms; } g_mdg_qpress;   // A dodge press refused by the running -hit pair (mdu_dodge_press 0), fired when the pair lets us go
static int mdu_dodge_press(uint32_t slot);   // melee_duel.c
static int mdu_vic_dodge_exit(uint64_t now);   // melee_duel.c: past the -hit reaction's exit point with a follow-up swing in flight
static void mdg_start(uint32_t slot, uint64_t now) {
    if (!mdu_dodge_press(slot)) { g_mdg_qpress.slot = slot; g_mdg_qpress.ms = now; return; }   // The -hit pair on us keeps the body (no follow-up swing to dodge); queued
    // (the press message goes out at the end of this function, once the into-the-blow ruling is known)
    uint64_t prev = g_mdg.last_dodge_ms;
    g_mdg_streak_n = prev && now - prev < MD_STREAK_MS ? g_mdg_streak_n + 1 : 1;
    mdg_charges_refresh(now);
    if (g_mdg_ch > 0) g_mdg_ch--;
    g_mdg_press_late = now + MD_PERFECT_MS >= g_mdg.sw[slot].ms + g_mdg.win_ms;   // (counter rules: a press in the last 200 ms before the contact; looser tuning: 350 ms, MD_PERFECT_MS)
    g_mdg.press_ms = now; g_mdg.iframe_until = now + MD_IFRAME_MS; g_mdg.cooldown_until = g_mdg_ch > 0 ? now + MD_IFRAME_MS : now + MD_COOLDOWN_MS; g_mdg.last_dodge_ms = now;
    g_mdg.seq_used = g_mdg.sw[slot].seq; g_mdg.mode = 1; g_mdg.last_slot = (int)slot; g_mdg.dodged_hits = 0;
    g_mdg.melee_ok_at = now + MD_MELEE_OK_MS; g_mdg.gun_lock_until = now + MD_GUN_LOCK_MS;
    if (g_mdg_whiff) { g_mdg.iframe_until = 0; g_mdg.melee_ok_at = g_mdg.gun_lock_until = now + 550; }   // a whiffed free dodge (see the free duel dodge)
    if (g_mdg.iframe_until && !g_mdg_whiff && !mdg49c_off()) {     // ps49: the i-frames cover this swing's contact
        uint64_t c = mdu49_vic_contact(slot);
        if (c > now && c - now < 1200 && c + MDG49_COVER_MS > g_mdg.iframe_until) { xlog("dodge: ps49 i-frames to the swing's contact + %d ms: %llu ms (were %d) - the press is %llu ms before the contact", MDG49_COVER_MS, (unsigned long long)(c + MDG49_COVER_MS - now), MD_IFRAME_MS, (unsigned long long)(c - now)); g_mdg.iframe_until = c + MDG49_COVER_MS; }
    }
    g_mdg.bar_t0 = g_mdg_ch > 0 ? 0 : now; g_mdg.cap_done = 0; g_mdg.combat_at = now + 60;   // (the bar = the real cooldown: only after the last charge)
    if (mdg_cd36()) {      // ps36: no charge / streak cost at the press; the cooldown is decided by the ruling (mdg_ok_note / mdg_tick), until then the press + MD_FAIL_CD_MS
        g_mdg_ch = MDG_CHARGES; if (mdg_no_streak()) g_mdg_streak_n = 1; g_mdg.cooldown_until = now + MD_FAIL_CD_MS; g_mdg.bar_t0 = 0;   // The streak counts (mdg_streak_win)
        if (g_mdg_whiff) { g_mdg.cooldown_until = now + MD_COOLDOWN_MS; g_mdg.bar_t0 = now; }      // (a press with no swing coming: the cooldown at once)
    }
    g_mdg_heavy_ms = g_mdg_heavy ? now : 0;
    g_md45_inwin = !g_mdg_whiff && !g_mdg_heavy;   // ps45: the failed-dodge cooldown of an in-window press (mdg_tick)
    { float pb[16]; const float *pl = uc4_my_loc(pb); if (pl && __builtin_isfinite(pl[0])) { g_mdg.press_xz[0] = pl[0]; g_mdg.press_xz[1] = pl[2]; } else g_mdg.press_xz[0] = g_mdg.press_xz[1] = 1e9f; }
    mdg_pick_combat(slot);
    { uint64_t c = g_mdg.sw[slot].ms + (g_mdg.win_ms > 120 ? g_mdg.win_ms - 60 : g_mdg.win_ms); g_mdg_wpre.slot = slot; g_mdg_wpre.at = c > now + 60 ? c : now + 60; }
    mdg_prompt_withdraw("press");
    if (g_send_tramp) g_send_tramp(MSG_DODGE_PRESS, (uint8_t[10]){(uint8_t)((g_mdg.iframe_until ? 1 : 0) | (g_mdg_heavy ? 2 : 0) /* ps46 */), (uint8_t)g_mdg.combat_dir, (uint8_t)g_mdg.combat_clip, (uint8_t)(g_mdg.combat_clip >> 8), (uint8_t)(g_mdg.combat_clip >> 16), (uint8_t)(g_mdg.combat_clip >> 24), (uint8_t)(g_mdg.combat_clip >> 32), (uint8_t)(g_mdg.combat_clip >> 40), (uint8_t)(g_mdg.combat_clip >> 48), (uint8_t)(g_mdg.combat_clip >> 56)}, 10, 0xff);
    if (mdg_cd36()) xlog("dodge: PRESS %llu ms into slot %u's swing (window %llu ms)%s - i-frames %d ms, gun lock %d ms (melee from %d ms); cooldown: %s (ps36 rule, no charges; streak %d shrinks the next window)",
         (unsigned long long)(now - g_mdg.sw[slot].ms), slot, (unsigned long long)g_mdg.win_ms, g_mdg_heavy ? " HEAVY (no swing about to land)" : g_mdg_whiff ? " WHIFF" : "", g_mdg.iframe_until ? MD_IFRAME_MS : 0, MD_GUN_LOCK_MS, MD_MELEE_OK_MS,
         g_mdg_whiff ? "1500 ms from now (no swing coming)" : "none if it drops a blow (free at +380 ms), else 1500 ms from the press (ruled at +560 ms)", g_mdg_streak_n);
    else
    xlog("dodge: PRESS %llu ms into slot %u's swing (window %llu ms%s) - i-frames %d ms, gun lock %d ms (melee from %d ms), cooldown %d ms (%d charge(s) left); the dodger frees at +%d ms, the attacker (if it connects as a miss) at +%d ms after the blow",
         (unsigned long long)(now - g_mdg.sw[slot].ms), slot, (unsigned long long)g_mdg.win_ms, prev && now - prev < MD_STREAK_MS ? ", shortened: streak dodge" : "", MD_IFRAME_MS, MD_GUN_LOCK_MS,
         MD_MELEE_OK_MS, g_mdg_ch > 0 ? MD_IFRAME_MS : MD_COOLDOWN_MS, g_mdg_ch, MD_GUN_LOCK_MS, MD_ATK_RECOVER_MS);
    mex_note_dodge(slot, now);                  // melee_exchange.c: inside an exchange this press is the defender's verdict
    bq_press_dodge(slot, now);                  // melee_beat.c: the stamped dodge intent for the duel owner
}
// ps49: a HEAVY dodge (no swing coming at the press) whose next swing window opens within MDG49_BUF_MS becomes that swing's dodge: i-frames to its contact,
// the in-window cooldown rule (no 1500 ms), the immune press sent (no clip: the running dodge clip goes on on every screen)
static void mdg49_upgrade(uint32_t slot, uint64_t now) {
    uint64_t pressed = g_mdg_heavy_ms, c = mdu49_vic_contact(slot);
    g_mdg_heavy_ms = 0;
    if (slot >= T2R_MAX_PEERS) return;
    uint64_t iu = now + MD_IFRAME_MS; if (c > now && c - now < 1200 && c + MDG49_COVER_MS > iu) iu = c + MDG49_COVER_MS;
    g_mdg.iframe_until = iu; g_mdg.seq_used = g_mdg.sw[slot].seq; g_mdg.last_slot = (int)slot; g_md45_inwin = 1; g_mdg.mode = 1;
    if (mdg_cd36()) { g_mdg.cooldown_until = now + MD_FAIL_CD_MS; g_mdg.bar_t0 = 0; }
    mdg_prompt_withdraw("ps49 buffered press");
    if (g_send_tramp) g_send_tramp(MSG_DODGE_PRESS, (uint8_t[10]){1, (uint8_t)g_mdg.combat_dir, 0, 0, 0, 0, 0, 0, 0, 0}, 10, 0xff);
    xlog("dodge: ps49 BUFFERED press - the heavy dodge pressed %llu ms ago became the dodge of slot %u's swing (window opened now): i-frames %llu ms (to its contact + %d), cooldown by the ruling, not 1500 ms",
         (unsigned long long)(now - pressed), slot, (unsigned long long)(iu - now), MDG49_COVER_MS);
    mex_note_dodge(slot, now);
    bq_press_dodge(slot, now);
}
// ---- the cooldown bar: a thin segmented line in the lower middle of the 16:9 HUD box (x 640, y 540 of 1280 x 720: under the crosshair, over the bottom HUD, clear of
// the award popups at y 452 and the low-ammo / loadout warning at y 640). Only after a dodge (g_mdg.bar_t0 = the press), full width at the press, shortening symmetrically to the
// centre as the 2500 ms run out, fading out over the last 180 ms (and in over the first 60). Drawn with the HUD text routine from the draw hook (no rectangle primitive exists):
// N overlapping "-" glyphs (each 3 pitches wide) = one solid white line with smoothstep-faded ends, a faint dark copy 1 px lower (shadow); was "=" segments ("battery level style") at the middle. The edge segment's alpha carries the fractional length,
// so the shortening is smooth, not stepped. Hidden: not in a match, dead / downed, match over, death fade, pause menu, bar off (t2r-no-dodge-bar.txt).
#define MDG_BAR_N 173             // segments (odd: one in the middle); 173 x 3 = ~518 px = ~40% of the screen width
#define MDG_BAR_PITCH 3.0f        // px per segment in the 1280 x 720 box; each '-' glyph is MDG_BAR_OVER pitches wide, so they overlap into one solid line
#define MDG_BAR_OVER 1.5f
#define MDG_BAR_ROWS 3            // '=' is two strokes: copies 1 px apart fill the gap between them
#define MDG_BAR_TAPER 6.0f        // segments over which each end of the line softens to nothing
#define MDG_BAR_Y 580.0f          // ~80% down the screen (above the bottom-left award lines, below the crosshair)
#define MDG_BAR_FADE_MS 180
#define MDG_BAR_IN_MS 60
static int mdg_bar_off(void) {
    static int off = -1; static uint64_t at;
    uint64_t now = GetTickCount64();
    if (off < 0 || now - at >= 2000) {
        at = now ? now : 1;
        FILE *f = exe_side_open("t2r-no-dodge-bar.txt", "r"); int o = f != NULL; if (f) fclose(f);
        if (o != off) xlog("dodge: cooldown bar %s", o ? "OFF (t2r-no-dodge-bar.txt)" : "on (after a dodge: thin line, y 540, shortens to the centre over the cooldown, fades at the end)");
        off = o;
    }
    return off;
}
// 0..1 how visible the bar is at now (0 = not drawn), plus the remaining fraction. Pure of the draw calls (preview tool mirrors it).
static float mdg_bar_state(uint64_t now, uint64_t t0, float *frac) {
    if (!t0 || now < t0 || now >= t0 + MD_COOLDOWN_MS) return 0.0f;
    uint64_t left = t0 + MD_COOLDOWN_MS - now;
    *frac = (float)left / (float)MD_COOLDOWN_MS;
    float a = 1.0f;
    if (left < MDG_BAR_FADE_MS) a = (float)left / (float)MDG_BAR_FADE_MS;
    if (now - t0 < MDG_BAR_IN_MS) { float i = (float)(now - t0) / (float)MDG_BAR_IN_MS; if (i < a) a = i; }
    return a;
}
// The bar as a real widget (a bar that is animated): hud-root's t2rDodgeBar (dodge_bar_widgets.py, one soft white line image,
// centred, pivotAs.x = -W/2 at full length). Per frame: pivotAs.x = -W/2 * frac and x scale = frac (the widget scales about its top-left pivot: both together shorten it
// symmetrically to the centre), alpha = ga (fade in 60 ms / out 180 ms); shown only while the bar runs. A page without the widget (old pak) falls back to the text bar.
#define MDG_BAR_WIDGET_W 1554.0f   // = dodge_bar_widgets.BAR_W (canvas units)
#define MDG_BAR_WIDGET_Y 1731.0f   // = BAR_CY - BAR_H / 2
static uint64_t g_mdg_bw; static int g_mdg_bw_vis, g_mdg_bw_miss; static uint64_t g_mdg_bw_page;
static int mdg_bar_widget(int show, float frac, float ga) {
    uint64_t page = *(uint64_t *)VMA(0x180189BA0);
    if (page != g_mdg_bw_page) { g_mdg_bw_page = page; g_mdg_bw = 0; g_mdg_bw_vis = 0; g_mdg_bw_miss = 0; }
    if (!show) { if (g_mdg_bw_vis && g_mdg_bw) w_visible(g_mdg_bw, 0); g_mdg_bw_vis = 0; return 1; }
    if (!g_mdg_bw && !g_mdg_bw_miss) {
        g_mdg_bw = hudw("t2rDodgeBar");
        if (!g_mdg_bw) { g_mdg_bw_miss = 1; xlog("dodge: widget t2rDodgeBar not in hud-root (old gui2-widgets.pak) - text bar fallback"); }
        else xlog("dodge: cooldown bar is the widget t2rDodgeBar (scaled + faded per frame)");
    }
    if (!g_mdg_bw) return 0;
    float s = frac < 0.004f ? 0.004f : frac > 1.0f ? 1.0f : frac;
    w_scale(g_mdg_bw, s, 1.0f);
    w_pivot(g_mdg_bw, -0.5f * MDG_BAR_WIDGET_W * s, MDG_BAR_WIDGET_Y);
    w_alpha(g_mdg_bw, ga);
    if (!g_mdg_bw_vis) { w_visible(g_mdg_bw, 1); g_mdg_bw_vis = 1; }
    return 1;
}
static int mqte_bar(float *frac, float *ga);     // melee_qte.c: the QTE window's closing bar (same widget as the cooldown bar)
static void mdg_bar_draw(void) {
    typedef void (*fn_text_va)(...);
    typedef uint64_t (*fn_measure)(const char *, float);
    static int logged;
    { float qf = 0, qa = 0;      // a running QTE window takes the bar (the cooldown bar resumes after it)
      if (mqte_bar(&qf, &qa) && match_substate() == 6 && !g_downed && !g_ff_ended && g_dui_black <= 0.05f && !hud_menu_up() && !mdg_bar_off() && mdg_bar_widget(1, qf, qa)) return; }
    if (!g_mdg.bar_t0) { if (g_mdg_bw_vis) mdg_bar_widget(0, 0, 0); return; }
    uint64_t now = GetTickCount64();
    float frac = 0.0f, ga = mdg_bar_state(now, g_mdg.bar_t0, &frac);
    if (ga <= 0.0f) { mdg_bar_widget(0, 0, 0); if (now >= g_mdg.bar_t0 + MD_COOLDOWN_MS) { if (logged) xlog("dodge: cooldown bar done (%llu ms)", (unsigned long long)(now - g_mdg.bar_t0)); g_mdg.bar_t0 = 0; logged = 0; } return; }
    if (match_substate() != 6 || mdg_off() || mdg_bar_off() || g_downed || local_hp() <= 0.0f || g_ff_ended || g_dui_black > 0.05f || hud_menu_up()) {
        mdg_bar_widget(0, 0, 0);
        if (logged) xlog("dodge: cooldown bar hidden (%s)", g_downed ? "downed" : local_hp() <= 0.0f ? "dead" : g_ff_ended ? "match over" : "state / menu / off");
        if (match_substate() != 6 || g_downed || local_hp() <= 0.0f || g_ff_ended) g_mdg.bar_t0 = 0;     // gone for good; a menu / pause only hides it for as long as it is up
        logged = 0;
        return;
    }
    if (mdg_bar_widget(1, frac, ga)) {
        if (!logged) { logged = 1; xlog("dodge: cooldown bar up (widget, %.0f%% left)", frac * 100.0f); }
        return;
    }
    static float gw1, gh1;
    if (!gw1) {
        uint64_t wh = ((fn_measure)VMA(0x1800051B0))("=", 1.0f);
        uint32_t lo = (uint32_t)wh, hi = (uint32_t)(wh >> 32);
        memcpy(&gw1, &lo, 4); memcpy(&gh1, &hi, 4);
        if (!(gw1 > 0.01f && gw1 < 50.0f && gh1 > 0.01f && gh1 < 50.0f)) { gw1 = 0; return; }
    }
    float sz = MDG_BAR_PITCH * MDG_BAR_OVER / gw1, th = gh1 * sz;
    float x0 = 640.0f - 0.5f * MDG_BAR_PITCH * MDG_BAR_N - 0.5f * MDG_BAR_PITCH * (MDG_BAR_OVER - 1.0f), ty = MDG_BAR_Y - th * 0.5f;
    float half = frac * (0.5f * MDG_BAR_N);                       // segments (and a fraction) kept each side of the centre
    int c = MDG_BAR_N / 2, drawn = 0;
    for (int pass = 0; pass < 2; pass++) {                         // 0 = soft dark shadow, 1 = the line
        for (int i = 0; i < MDG_BAR_N; i++) {
            float d = (float)(i > c ? i - c : c - i);            // segment distance from the middle one
            float cover = half + 0.5f - d;                        // 1 = whole segment inside, 0 = outside
            if (cover <= 0.0f) continue;
            if (cover > 1.0f) cover = 1.0f;
            float a = ga * cover, edge = (half + 0.5f - d) / MDG_BAR_TAPER;   // soft ends: the last MDG_BAR_TAPER segments fade out
            if (edge < 1.0f) a *= edge > 0.0f ? edge * edge * (3.0f - 2.0f * edge) : 0.0f;
            uint32_t col;
            float px = x0 + MDG_BAR_PITCH * (float)i;
            if (pass == 0) continue;                                                                               // (no shadow pass: 3 rows already)
            else {
                uint32_t al = (uint32_t)(a * 235.0f + 0.5f);                                                       // plain white (overlaps add up to solid)
                col = al << 24 | 0xF8F8F8u;                                                                         // ABGR
                for (int r = 0; r < MDG_BAR_ROWS; r++)
                    ((fn_text_va)VMA(0x1800039D0))(fbits(px), fbits(ty + (float)r), fbits(sz), (uint64_t)col, "%s", "=");
                drawn++;
            }
        }
    }
    if (!logged) { logged = 1; xlog("dodge: cooldown bar up (glyph %.2f x %.2f px at size 1, segment %.1f px, %d segments at start)", gw1, gh1, MDG_BAR_PITCH, drawn); }
}
// ---- winmm's per-frame dodge lock (the dodge is forced disabled by the winmm code once a match starts; 0x180032d4a-0x180032ddf, called first thing
// in the frame update 0x1800344e0 -> 0x180032ad0 -> every frame): joypad-disable-commands(argc 4, argv rsp+0x28 = {dodge, evade-start, flashlight-toggle, quick-turn}).
// Inside our dodge window the call is re-aimed at the LAST TWO entries ({flashlight-toggle, quick-turn}: lea r8,[rsp+0x28] -> [rsp+0x38], mov edx,4 -> 2), so
// `dodge` and `evade-start` stay enabled for the engine's own dodge; everywhere else winmm's list is untouched. Bytes verified (original or patched) before any write.
#define MDG_WG_ADDR 0x180032dd2ULL
static int mdg_winmm_gate(int open) {
    static const uint8_t orig[10] = {0x4C, 0x8D, 0x44, 0x24, 0x28, 0xBA, 0x04, 0x00, 0x00, 0x00};
    static const uint8_t pat[10]  = {0x4C, 0x8D, 0x44, 0x24, 0x38, 0xBA, 0x02, 0x00, 0x00, 0x00};
    static int bad, cur = -1;
    if (bad) return 0;
    uint8_t *f = (uint8_t *)VMA(MDG_WG_ADDR);
    if (cur == open) return 1;
    if (IsBadReadPtr(f, 10) || (memcmp(f, orig, 10) && memcmp(f, pat, 10))) { bad = 1; hook_miss(f, 10, "dodge: winmm 0x180032dd2 (the per-frame joypad-disable-commands(dodge, evade-start, flashlight-toggle, quick-turn)) bytes differ - winmm's dodge lock stays on"); return 0; }
    DWORD old;
    if (!VirtualProtect(f, 10, PAGE_EXECUTE_READWRITE, &old)) { bad = 1; hook_fail("dodge: winmm dodge lock not patchable"); return 0; }
    memcpy(f, open ? pat : orig, 10);
    VirtualProtect(f, 10, old, &old);
    FlushInstructionCache(GetCurrentProcess(), f, 10);
    cur = open;
    xlog("dodge: winmm's dodge lock %s (joypad-disable-commands argc %d from +0x%x)", open ? "OPENED for the window (dodge + evade-start enabled)" : "closed again", open ? 2 : 4, open ? 0x38 : 0x28);
    return 1;
}
static void mdg_tick(void) {
    mdg_whiff_pre_tick(GetTickCount64());
    uint64_t now = GetTickCount64();
    mdg_held_tick(now);
    // the attacker's windup extension restore + miss tail restore (always, also when the feature goes off)
    if (g_mdg.ext_on && (now >= g_mdg.ext_until || !g_ms_atk || g_ms_curmove != g_mdg.ext_move || mdg_off() || match_substate() != 6)) {
        if (!g_ms.active) mstag_speed(g_mdg.ext_clip, 1.0f);
        g_mdg.ext_on = 0;
    }
    if (g_mdg.slow_clip && (now >= g_mdg.slow_until || !g_ms_atk || match_substate() != 6)) { if (!g_ms.active) mstag_speed(g_mdg.slow_clip, 1.0f); g_mdg.slow_clip = 0; }
    {   // the attacker's local hit sound (winmm's PlayLocalHitFeedback list) is muted while any dodger's i-frames (his press message) cover our swing
        int mute = 0;
        if (match_substate() == 6 && !mdg_off()) for (uint32_t k = 0; k < T2R_MAX_PEERS; k++) if (g_mdg.imm_until[k] > now) mute = 1;
        if (mute != g_hit_sfx_mute) { g_hit_sfx_mute = mute; melee_hit_sfx_swap(-1); }
    }
    if (match_substate() != 6) { uint64_t cd_ = g_mdg.cooldown_until; memset(&g_mdg, 0, sizeof g_mdg); g_mdg.cooldown_until = cd_; /* the cooldown survives a state flicker */ g_md_fb.on = g_md_carry.on = 0; mdg_winmm_gate(0); return; }
    if (mdg_off()) { g_mdg.window_open = 0; mdg_winmm_gate(0); return; }
    mdg_hit_watch(now);
    if (g_mdg.tr_until && now < g_mdg.tr_until && now >= g_mdg.tr_next) {       // what the body does after a dodge / miss: clip playing?, move id, displacement
        g_mdg.tr_next = now + 120;
        uint64_t pa[3] = {SID_PLAYER, g_mdg.tr_clip ? fnv64_rt(g_mdg.tr_clip) : 0, 2}, pl_ = g_mdg.tr_clip ? dc_call(fnv64("get-animation-playing?"), 3, pa) : ~0ULL;
        float tb[16]; const float *tl = uc4_my_loc(tb);
        xlog("dodge: trace clip %s playing=%d move=%llx (dodge move %d) moved %.2f m", g_mdg.tr_clip ? g_mdg.tr_clip : "-", pl_ == ~0ULL ? -1 : (int)(pl_ & 0xff), (unsigned long long)g_ms_curmove, mdg_is_dodge_move(g_ms_curmove),
             tl ? __builtin_sqrtf((tl[0] - g_mdg.tr_from[0]) * (tl[0] - g_mdg.tr_from[0]) + (tl[2] - g_mdg.tr_from[1]) * (tl[2] - g_mdg.tr_from[1])) : 0.0f);
    }
    mdg_mv_tick(&g_md_fb);
    mdg_mv_tick(&g_md_carry);
    mdg_fall_watch();
    mdg_stumble_tick(now);
    mdg_combat_tick(now);
    mdg_puppet_tick(now);
    mdl_tick(now);
    mdg_dodge_say_tick(now);
    mdg_sync_tick(now);
    mdg_settle_tick(now);
    mdg_sp_pup_tick(now);
    if (mv3_stand_me("dodge: window / prompt / press / i-frames / winmm dodge gate")) {     // melee v3: the sim's dodge (MV3_B_DODGE) owns it inside a bubble; winmm's dodge lock stays closed
        if (g_mdg.window_open) mdg_prompt_withdraw("melee v3 bubble");
        g_mdg.window_open = 0; g_mdg.prev_press = 0;
        mdg_winmm_gate(0);
        return;
    }
    if (g_mdg_heavy_ms && now - g_mdg_heavy_ms <= MDG49_BUF_MS && !mdg49b_off() && !mpn_vic_pin() && mdg_streak_win(now) >= MD_WIN_MS) {   /* No early-press buffer inside a streak (its window is the timing test) */ uint64_t wm49 = 0; int s49 = mdg_window(now, &wm49); if (s49 >= 0) mdg49_upgrade((uint32_t)s49, now); }
    const char *busy = mdg_busy();
    int esc = dc_esc_open(now);                  // dcounter.c: we are the countered attacker, inside the escape window of the counter's last DC_ESC_WIN_MS
    int slot = -1;
    if (!busy && !mpn_vic_pin() && !mdg_own_swing_blocks(now) && now >= g_mdg.cooldown_until && now >= g_mdg.miss_until && !pad_cmd_on("aim")) slot = mdg_window(now, &g_mdg.win_ms);
    if (slot >= 0 && !md56_time_only() && md56_counter_from((uint32_t)slot, now)) {   // ps56: a dodge counter's swing opens no window / prompt (it cannot be dodged)
        static uint64_t lsw; if (lsw != g_md56_ctrsw_ms[slot]) { lsw = g_md56_ctrsw_ms[slot]; xlog("dodge: ps56 no window for slot %d's swing - its dodge counter (SWING %llu ms ago, it dodged our blow %llu ms ago)", slot, (unsigned long long)(now - g_md56_ctrsw_ms[slot]), (unsigned long long)(now - g_md56_dodged_ms[slot])); }
        slot = -1; }
    int open = slot >= 0;
    static int win_slot = -1; static uint64_t win_ms;              // the last window's attacker (an engine dodge that missed our press edge still dodges its blow)
    if (open) { win_slot = slot; win_ms = now; }
    if (now < g_mdg.cooldown_until && g_mdg.last_req_f && g_frame - g_mdg.last_req_f <= 3) mdg_prompt_withdraw("cooldown");
    if (open && !g_mdg.window_open) {
        g_mdg_glyph_logged = 0;
        { static int pr; if (!pr) { pr = 1; static const char *const D[] = {"left", "right", "back"}, *const A[] = {"horiz", "downward", "upward"}; char b[2200]; int o = 0, hmv = 0, hclip = 0, hname = 0, tot = 0;
            for (int set = 0; set < 2; set++) for (int d = 0; d < 3; d++) for (int a = set; a < 3; a++) for (int sd = 0; sd < 2; sd++) for (int v = 0; v < 5; v++) {
                char nm[96], cn[96]; snprintf(nm, sizeof nm, set ? "player-2h-contextual-dodge-%s-%s-%s-%c" : "player-contextual-dodge-%s-%s-%s-%c", D[d], A[a], sd ? "right" : "left", 'a' + v);
                tot++; uint8_t *rec = (uint8_t *)((fn_lookup)VMA(0x18000A190))(fnv64_rt(nm)); if (rec && !IsBadReadPtr(rec, 16) && *(void **)(rec + 8)) hmv++;
                uint64_t clip = mstag_clip_of(fnv64_rt(nm)); int ok = clip && mdg_clip_len(clip) > 0.0f; if (clip) hclip++;
                if (!ok && !set) { snprintf(cn, sizeof cn, "ellie-1h-dodge-%s-combat-%s-%s-%c", D[d], A[a], sd ? "right" : "left", 'a' + v); if (mdg_clip_len(fnv64_rt(cn)) > 0.0f) { ok = 1; hname++; } }
                if (ok && o < (int)sizeof b - 90) o += snprintf(b + o, SNLEFT(b, o), " %s", nm + (set ? 32 : 24)); }
            xlog("dodge: contextual dodges in MP (human set + 2h set, %d probed): %d move defs, %d clip sids, %d loaded by name (ellie-1h-dodge-*); loaded (dir-angle-side-variant):%s", tot, hmv, hclip, hname, o ? b : " none");
            static const char *const OP[] = {"player-dodge-back-lt-a-open-combat", "player-dodge-back-rt-a-open-combat", "player-dodge-back-lt-a-open-relax", "player-dodge-back-rt-a-open-relax", "player-phantom-dodge"};
            for (size_t i = 0; i < sizeof OP / sizeof OP[0]; i++) { uint64_t clip = mstag_clip_of(fnv64_rt(OP[i])); xlog("dodge: open dodge %s: clip sid %llx, clip %.2f s", OP[i], (unsigned long long)clip, clip ? mdg_clip_len(clip) : 0.0f); }
            xlog("dodge: npc-reaction-step clips (attacker's SP miss): left %.2f right %.2f back %.2f forward %.2f s", anim_len(SID_PLAYER, "npc-reaction-step-left"), anim_len(SID_PLAYER, "npc-reaction-step-right"), anim_len(SID_PLAYER, "npc-reaction-step-back"), anim_len(SID_PLAYER, "npc-reaction-step-forward")); } }
        mdgt_on_window_open(now);
        g_mdg_prompt_open_ms = now;
        g_mdg46.req0 = g_mdg46.req1 = 0; g_mdg46.id++; g_mdg46i.icon = NULL;
        float d = 0; mdg_geom_ok((uint32_t)slot, 0, &d);
        xlog("dodge: window OPEN - slot %d swung %llu ms ago at %.2f m (%llu ms window)%s", slot, (unsigned long long)(now - g_mdg.sw[slot].ms), d, (unsigned long long)g_mdg.win_ms, g_mdg.sw[slot].kind ? ", one-shot armed" : "");
    }
    if (!open && g_mdg.window_open) mdg_prompt_withdraw("window closed");
    if (!open && g_mdg.window_open) { static int nl; if (LOGCAP(nl, 60)) xlog("dodge: window closed (%s)", busy ? busy : mdg_own_swing_blocks(now) ? "we swing" : now < g_mdg.cooldown_until ? "cooldown" : "time up / out of reach / not facing"); }
    if (!open && g_mdg.window_open && !mdg46_prompt_old()) { static int n46; if (LOGCAP(n46, 150)) { uint64_t o = g_mdg_prompt_open_ms; long long w = (long long)(now - o);
        const char *why = busy ? busy : mpn_vic_pin() ? "pinned" : mdg_own_swing_blocks(now) ? "we swing" : now < g_mdg.cooldown_until ? "cooldown / pressed" : now < g_mdg.miss_until ? "miss lock" : "time up / out of reach / not facing";
        if (g_mdg46.req0) { long long a = (long long)(g_mdg46.req0 - o), b = (long long)(g_mdg46.req1 - o);
            xlog("dodge: ps46 prompt #%d: requests +%lld..+%lld ms, window +0..+%lld ms on this screen (closed: %s) - the engine's linger keeps the icon to ~+%lld..+%lld ms = %lld..%lld ms past the close",
                 g_mdg46.id, a, b, w, why, b + MD_PROMPT_LINGER_MS, b + 430, b + MD_PROMPT_LINGER_MS - w, b + 430 - w); }
        else xlog("dodge: ps46 prompt #%d: not requested in this +0..+%lld ms window (closed: %s)", g_mdg46.id, w, why); } }
    g_mdg.window_open = open;
    // ps47 (the gliding bug: when switching between two game windows with alt+tab while mashing melee, the non-controlled window
    // cut to a stationary hands-down pose and slid with no animation): Alt is TLOU2's dodge key. Alt+Tab leaves Alt DOWN in the window that
    // loses focus (its key-up goes to the other window) - its engine keeps "evade" held, and every dodge window the partner's swings open let winmm's evade through:
    // the engine's own evade ran with no dodge clip of ours (our edge never saw a new press). An unfocused game (no bot / unfocused-input test mode) now reads no
    // dodge press and keeps winmm's dodge lock shut. t2r-dodge-focus-ps47-old.txt = old.
    int foc47 = game_focused() || padinj_nofocus_on() || mdg47_focus_off();
    { static int was = 1; if (foc47 != was) { was = foc47; static int nl; if (LOGCAP(nl, 80)) xlog("dodge: ps47 game %s - dodge presses %s, winmm's dodge lock %s", foc47 ? "focused again" : "NOT focused (alt-tab)", foc47 ? "read again" : "ignored (a key held through alt-tab stays out)", foc47 ? "follows the windows" : "kept shut"); } }
    mdg_winmm_gate(foc47 && (open || esc || mpn_qte_open() || (g_mdg.press_ms && now < g_mdg.press_ms + 700)));    // winmm lets dodge / evade-start through for the window + the dodge start (takes effect from winmm's next frame call)
    mdgt_tick(now);
    mdg_room_probe(open ? slot : -1);     // (a closed window still collects its pending rays)
    int raw53 = padinj_dodge_held();
    int cmd53 = pad_cmd_on("evade") || pad_cmd_on("dodge") || pad_cmd_on("evade-start");
    int press = (cmd53 || raw53 || mdgt_press_now(now)) ? 1 : 0;
    { static int was; if (raw53 && !cmd53 && !was) { static int nl; if (LOGCAP(nl, 40)) xlog("dodge: ps53 press seen on the device bit only (the engine command read false) - taken"); } was = raw53 && !cmd53; }   // (presses seen by the engine, not by "evade" alone)
    if (!foc47 && !mdgt_press_now(now)) press = 0, g_mdg.prev_press = 1;   // ps47: a refocus with the key still down is no new press either
    int edge = press && !g_mdg.prev_press; g_mdg.prev_press = press;
    // ps39 (double dodges: the dodge was not limited to playing once; log [9174] / [9228] / [9262]: three dodge
    // clips 900 and 567 ms apart, each started while the one before was still travelling - they land at 780-990 ms; [9377] -> [9391]: a HEAVY press taken while
    // the -hit pair was on us was QUEUED by mdu_dodge_press and replayed 234 ms later as a second heavy dodge with no new press):
    //  1 one dodge clip at a time - from a press until its clip has landed (cmb_land_ms) a new press is dropped, never buffered;
    //  2 a queued press fires only into an OPEN window (the follow-up blow it was pressed against), else it is dropped;
    //  3 the heavy dodge never starts under a -hit pair on us (nothing to queue). t2r-dodge-once-ps38.txt = old.
    static int once39 = -1; static uint64_t once_at; if (once39 < 0 || now - once_at > 3000) { once_at = now; once39 = GetFileAttributesA("t2r-dodge-once-ps38.txt") == INVALID_FILE_ATTRIBUTES; }
    int dodging39 = once39 && ((g_mdg.mode == 1 && now - g_mdg.press_ms < 300) || (g_mdg.cmb_on && now - g_mdg.cmb_ms < g_mdg.cmb_land_ms));
    if (dodging39 && g_mdg_qpress.ms) g_mdg_qpress.ms = 0;
    if (edge && dodging39 && !esc && !mpn_qte_open()) {
        static int nl39; if (LOGCAP(nl39, 60)) xlog("dodge: press dropped - our dodge clip is still travelling (%llu of %llu ms to its landing): one dodge at a time (ps39)", (unsigned long long)(g_mdg.cmb_on ? now - g_mdg.cmb_ms : 0), (unsigned long long)g_mdg.cmb_land_ms);
        edge = 0;
    }
    if (!edge && g_mdg_qpress.ms && once39 && !mdu_vic_pair_on() && !open) {
        xlog("dodge: the press queued %llu ms ago by the -hit pair on us is dropped - the pair let us go and no window is open (ps39: never replayed as a free dodge)", (unsigned long long)(now - g_mdg_qpress.ms));
        g_mdg_qpress.ms = 0;
    }
    if (!edge && g_mdg_qpress.ms) {                                   // The press queued by the running -hit pair fires once it let us go (<= 700 ms)
        if (now - g_mdg_qpress.ms > 700) g_mdg_qpress.ms = 0;
        else if (!mdu_vic_pair_on()) { xlog("dodge: the press queued %llu ms ago by the -hit pair on us fires now (the pair let us go)", (unsigned long long)(now - g_mdg_qpress.ms)); edge = 1; g_mdg_qpress.ms = 0; }
        // ps23: ... or at the reaction's exit point when the attacker's follow-up swing is in flight and its window is open (SP: a dodge leaves a hit reaction at 650-680 ms)
        else if (open && !mpn_vic_held() && mdu_vic_dodge_exit(now)) { xlog("dodge: the press queued %llu ms ago by the -hit pair on us fires now (the reaction's exit point, a follow-up swing is in flight)", (unsigned long long)(now - g_mdg_qpress.ms)); edge = 1; g_mdg_qpress.ms = 0; }
    }
    { int s56 = -1; if (edge && !esc && !mpn_qte_open() && md56_ctr_inflight(now, &s56)) {   // ps56: no dodge clip under a counter's blow (it would only be cut by it)
        xlog("dodge: ps56 press dropped - slot %d's dodge counter is in flight on us (SWING %llu ms ago): it cannot be dodged, no dodge clip", s56, (unsigned long long)(now - g_md56_ctrsw_ms[s56]));
        edge = 0; } }
    if (!esc && edge && !mpn_qte_open()) dc_esc_early_press();     // (the pin QTE's early presses are its own E presses: melee_duel_pin.c mpn_e_edge)     // dcounter.c: a press before the escape window burns it (anti-mash)
    if (esc) {                                   // the escape window: the evade command stays enabled, a press ends the counter (dc_escape) and starts the normal dodge
        int es = dc_esc_slot();
        (void)es;                                // (no "E - Dodge" prompt during the counter's animation; the escape press still works)
        if (edge) dc_escape(now);
    } else if (mpn_qte_open()) {                 // melee_duel_pin.c: the pin QTE window - a press escapes the pin (no normal dodge)
        (void)0;                                 // E / triangle / Y escapes (melee_duel_pin.c mpn_e_edge); the dodge button does nothing here
    } else if (open && !mpn_vic_held()) {      // (pinned, the prompt flipped between "Dodge" and the QTE's "Escape" - pinned = Escape only)
        unsigned gf = g_wpq_glyph_fail;
        if (now < g_mdg.cooldown_until) { g_mdg.req_in_cd++; xlog("dodge: BUG prompt requested during the cooldown (%llu ms left)", (unsigned long long)(g_mdg.cooldown_until - now)); }
        // ps25: the last MD_PROMPT_LINGER_MS of the window are not requested (see mdg_window) - the engine's own linger shows the prompt to the window's end
        int p46 = !mdg46_prompt_old();
        int pmin45 = p46 ? MDG46_PROMPT_MIN_MS : md45_prompt_old() ? MD_PROMPT_MIN_MS : MD45_PROMPT_MIN_MS;   // ps45: at least 150 ms of requests (ps44: 50 ms floor, 63-125 ms seen); ps46: 50
        int ptail = (g_mdg_win_end <= now || g_mdg_win_end - now < MD_PROMPT_LINGER_MS) && now - g_mdg_prompt_open_ms >= (uint64_t)pmin45 && GetFileAttributesA("t2r-dodge-prompt-ps24.txt") == INVALID_FILE_ATTRIBUTES;
        if (ptail) { static uint64_t lw; static int nlp; if (lw != g_mdg_win_end) { lw = g_mdg_win_end; if (LOGCAP(nlp, 80)) xlog("dodge: prompt requests end %lld ms before the window closes (%llu ms after it opened, min %d ms%s) - the engine keeps the icon up ~300-430 ms after the last request", (long long)((int64_t)g_mdg_win_end - (int64_t)now), (unsigned long long)(now - g_mdg_prompt_open_ms), pmin45, p46 ? ", ps46" : pmin45 == MD45_PROMPT_MIN_MS ? ", ps45" : ""); } }
        g_wpq_glyph = "gen:evade";                               // the glyph of the evade command's real binding (device aware), never the interact key
        // (a real dodge press inside the window was eaten silently by the anti-mash lock while the prompt was shown): while the lock ignores presses
        // (below) the prompt is not offered - it never shows a dodge that cannot happen. t2r-dodge-lock-prompt-old.txt = shown through the lock.
        int plock = !mdg_mash_ok() && now < g_mdg_mash_until && g_mdg_mash_n >= 2 && GetFileAttributesA("t2r-dodge-lock-prompt-old.txt") == INVALID_FILE_ATTRIBUTES;
        if (plock) { static int nl; if (LOGCAP(nl, 30)) xlog("dodge: prompt withheld - the anti-mash lock ignores presses for %llu more ms", (unsigned long long)(g_mdg_mash_until - now)); }
        // ps46: no prompt while a press would not start a dodge that avoids this blow (see MDG46_PROMPT_MIN_MS)
        const char *h46 = !p46 ? NULL : dodging39 ? "our dodge clip still travels - a press is dropped" : mdu46w_queued_past(now, g_mdg_win_end) ? "the -hit pair on us would queue a press past the window's close" : NULL;
        if (h46) { if (g_mdg.last_req_f && g_frame - g_mdg.last_req_f <= 3) mdg_prompt_withdraw(h46);
                   if (g_mdg46.hid != g_mdg46.id) { g_mdg46.hid = g_mdg46.id; static int nh; if (LOGCAP(nh, 80)) xlog("dodge: ps46 prompt #%d withheld +%llu ms into the window: %s", g_mdg46.id, (unsigned long long)(now - g_mdg_prompt_open_ms), h46); } }
        if (!ptail && !(p46 && (plock || h46))) { g_mdg.last_req_f = g_frame; g_mdg.last_req_ms = now; if (!g_mdg46.req0) g_mdg46.req0 = now; g_mdg46.req1 = now; }
        g_wpq_ret = NULL;
        int shown = (plock || ptail || h46) ? 1 : world_prompt(puppet_handle((uint32_t)slot), "Dodge", -1.0f);
        if (g_wpq_ret) { g_mdg46i.icon = g_wpq_ret; g_mdg46i.keep = g_wpq_ret_keep; g_mdg46i.ms = now; }   // ps46 icon hide: the icon this request refreshed
        g_wpq_glyph = NULL;
        if (g_wpq_glyph_fail != gf) { if (!g_mdg_glyph_logged) { g_mdg_glyph_logged = 1; xlog("dodge: prompt glyph not swapped (request layout differs) - text-only prompt, no key shown"); } shown = 0; }
        else if (shown && g_wpq_glyph_ok && !g_mdg_glyph_logged) { g_mdg_glyph_logged = 1; xlog("dodge: prompt shown with the evade glyph (gen:evade)"); }
        if (!shown && g_t60 - g_mdg.prompt_n >= 120) { g_mdg.prompt_n = g_t60; T2R_PROMPT_MSG("DODGE", 0.6f, 0, 0); }
        if (edge && !mdg_mash_ok() && now < g_mdg_mash_until && g_mdg_mash_n >= 2) {     // (no renewal any more: a press in the window after the lock ends dodges)
            static int nm; if (LOGCAP(nm, 40)) xlog("dodge: press %llu ms into the mash lock (%d early presses) - ignored", (unsigned long long)(MD_MASH_MS - (g_mdg_mash_until - now)), g_mdg_mash_n);
        } else if (edge) { g_mdg_mash_n = 0; mdg_start((uint32_t)slot, now); }
    } else {
        // the gate: the command does nothing outside a window (frame-scoped native). Prone / supine keep it: there `evade` is the engine's prone roll
        // (evade-roll), a stance move and no dodge-roll; standing / crouched / cover evades (dive, slide, cover dodge, evade-climb) are the movement tech gated here.
        // Nothing else in the ext uses `evade` (grep); downed / revive / intro locks already disable every command.
        uint64_t nn = 0, pr = dc_call(fnv64("player-is-prone?"), 0, &nn), su = dc_call(fnv64("player-is-supine?"), 0, &nn);
        int low = (pr != ~0ULL && (pr & 0xff)) || (su != ~0ULL && (su & 0xff));
        uint64_t cmd = fnv64("evade");
        if (!low) dc_call(fnv64("joypad-disable-commands"), 1, &cmd);
        // dodges sometimes did not play: 18 / 24 presses in the two logs did nothing - the button only worked inside a swing's window. TLOU2 SP
        // dodges whenever the button is pressed in a fight: inside a duel, with the partner within 3 m, a press outside a window is a full dodge (same clip,
        // i-frames, charges and cooldown). t2r-dodge-window-only.txt = the old gate.
        // v5-pinesc (v5-int22, log 41001): pinned, a dodge press between two blows was a free duel dodge - it ABORTed the pin's -hit pair while the pin stayed on,
        // the pinner's next blow then started its wall swing with no pair holding its body and the engine's align carried it 178 m to the map origin (OOB death).
        // Pinned = Escape only: the press does nothing until the QTE. t2r-pin-free-dodge.txt = the old rule.
        if (edge && mpn_vic_held() && GetFileAttributesA("t2r-pin-free-dodge.txt") == INVALID_FILE_ATTRIBUTES) { static int npd; if (LOGCAP(npd, 30)) xlog("dodge: pinned (a pin is on us) - the dodge button does nothing outside the Escape QTE, the pin pair stays"); edge = 0; }
        // (a dodge activated outside of its window must not use those animations: standing in place it almost instantly
        // jumps to the side while staying pretty stationary): the free WHIFF dodge (no swing coming) played the dodge clip under the duel's travel cap - a
        // fast sidestep pose that barely moves. Off: outside a window the button does nothing again (every blow now has its windup tell, so real swings open a
        // window). t2r-dodge-whiff-anim.txt = the old whiff dodge.
        int heavy36 = GetFileAttributesA("t2r-dodge-heavy-ps35.txt") == INVALID_FILE_ATTRIBUTES && !mdg_own_swing_blocks(now) && !(once39 && mdu_vic_pair_on());   // ps36 (see MDG_HEAVY_RATE); ps39: not under a -hit pair on us
        if (edge && !low && !busy && now >= g_mdg.cooldown_until && mdu_engaged() && GetFileAttributesA("t2r-dodge-window-only.txt") == INVALID_FILE_ATTRIBUTES
            && (heavy36 || GetFileAttributesA("t2r-dodge-whiff-anim.txt") != INVALID_FILE_ATTRIBUTES)) {
            int ps = mdu_partner_slot(); float gd = 9.0f;
            if (ps >= 0 && (mdg_geom_ok((uint32_t)ps, 1, &gd) || gd < 3.0f) && gd < 3.0f) {
                // whiffing should cost both sides: a dodge with no swing coming is a WHIFF - the clip plays, but with no i-frames and
                // our melee / guns locked MDG_WHIFF_MS, so dodging on a guess is punishable like a dodged swing. t2r-dodge-free-iframes.txt = the old full dodge.
                int whiff = GetFileAttributesA("t2r-dodge-free-iframes.txt") == INVALID_FILE_ATTRIBUTES;
                xlog("dodge: free dodge in the duel (no swing window, partner slot %d at %.2f m)%s", ps, (double)gd, whiff ? " - WHIFF: no i-frames, melee / guns locked 550 ms" : "");
                if (heavy36 && whiff) xlog("dodge: HEAVY dodge (no swing about to land): the clip at x%.2f, travel eased in over %.0f ms, no i-frames, cooldown %d ms (ps36)", (double)MDG_HEAVY_RATE, (double)(MDG_HEAVY_RAMP_S * 1000.0f), MD_COOLDOWN_MS);
                g_mdg_whiff = whiff; g_mdg_heavy = heavy36 && whiff; mdg_start((uint32_t)ps, now); g_mdg_whiff = 0; g_mdg_heavy = 0; edge = 0;
            }
        }
        if (edge && !low) mex_note_early_press();
        if (edge && !low && now >= g_mdg.cooldown_until) { g_mdg_mash_n = now < g_mdg_mash_until ? g_mdg_mash_n + 1 : 1; g_mdg_mash_until = now + MD_MASH_MS; }     // (a press in the cooldown is not a mash: the bar shows it)
        if (edge && !low) { static int nl; if (LOGCAP(nl, 30)) { int ls = -1; uint64_t la = 0; for (uint32_t s = 0; s < T2R_MAX_PEERS; s++) if (g_mdg.sw[s].ms && (ls < 0 || g_mdg.sw[s].ms > la)) { ls = (int)s; la = g_mdg.sw[s].ms; }
              float gd = 0.0f; int gok = ls >= 0 ? mdg_geom_ok((uint32_t)ls, 1, &gd) : 0;
              xlog("dodge: button pressed with no swing about to land (%s) - nothing happens; last enemy swing: %s%d %llu ms ago (%s, %.2f m, blow %s), our swing %s", busy ? busy : now < g_mdg.cooldown_until ? "cooldown" : mdg_own_swing_blocks(now) ? "we swing (windup / contact)" : "no window",
                   ls < 0 ? "none" : "slot ", ls, ls < 0 ? 0ULL : (unsigned long long)(now - la), gok ? "in reach + facing" : "out of reach / not facing", gd, ls >= 0 && g_mdg.sw[ls].landed_ms >= la ? "already came" : "pending",
                   g_ms_atk ? "running" : "none"); } }
    }
    // an engine dodge move that did not come through our press edge (command read flickered) still starts the cooldown + bar
    // - and when a window was open in the last 200 ms it IS the dodge of that swing: the same i-frames as a press (dodged out of the
    // way, the blow still landed and the attacker played no miss)
    if (g_mdg.mode == 0 && now >= g_mdg.cooldown_until && mdg_is_dodge_move(g_ms_curmove)) {
        if (win_slot >= 0 && now - win_ms <= 200 && !busy) {
            xlog("dodge: engine dodge move %llx without our press edge, %llu ms after slot %d's window - counted as the press", (unsigned long long)g_ms_curmove, (unsigned long long)(now - win_ms), win_slot);
            mdg_start((uint32_t)win_slot, now);
            g_mdg.mode = 2;
        } else {
            g_mdg.cooldown_until = now + MD_COOLDOWN_MS; g_mdg.bar_t0 = now; mdg_prompt_withdraw("engine dodge");
            xlog("dodge: engine dodge move %llx without our press edge - cooldown %d ms started", (unsigned long long)g_ms_curmove, MD_COOLDOWN_MS);
        }
        win_slot = -1;
    }
    // the engine's own dodge move, or the fallback
    if (g_mdg.mode == 1 && g_mdg.combat_clip && !busy && (mdg_is_dodge_move(g_ms_curmove) || now >= g_mdg.combat_at)) mdg_combat_play();
    if (g_mdg.mode == 2 && g_mdg.press_xz[0] < 1e8f && !g_mdg.cap_done && mdg_is_dodge_move(g_ms_curmove)) {     // an engine dodge sequence that carries us too far is cut
        float cb[16]; const float *cl = uc4_my_loc(cb);
        if (cl && __builtin_isfinite(cl[0]) && (cl[0] - g_mdg.press_xz[0]) * (cl[0] - g_mdg.press_xz[0]) + (cl[2] - g_mdg.press_xz[1]) * (cl[2] - g_mdg.press_xz[1]) > MD_CAP_M * MD_CAP_M) {
            uint64_t me = SID_PLAYER, c = dc_call(0x394888944e949d5fULL /* cancel-melee-action */, 1, &me);
            g_mdg.cap_done = 1; xlog("dodge: engine dodge move %llx carried us > %.1f m - cancelled (%llx)", (unsigned long long)g_ms_curmove, MD_CAP_M, (unsigned long long)c);
        }
    }
    if (g_mdg.mode == 1) {
        if (mdg_is_dodge_move(g_ms_curmove)) { g_mdg.mode = 2; xlog("dodge: the engine's own dodge move %llx runs (%llu ms after the press)", (unsigned long long)g_ms_curmove, (unsigned long long)(now - g_mdg.press_ms)); }
        else if (now - g_mdg.press_ms >= MD_ENGINE_WAIT_MS) {
            g_mdg.mode = 3;
            if (busy) { g_mdg.iframe_until = 0; xlog("dodge: nothing played and the body is busy (%s) - i-frames revoked", busy); }
            else mdg_fallback(g_mdg.last_slot);
        }
    }
    // ps23 (tl 95.44-96.67: a dodge pressed 71 ms into a 451 ms wind-up dropped nothing - 'dodger free again (391 ms after the press, 0 blow(s) dodged)' -
    // and its 1500 ms cooldown then refused the presses at 96.30 / 96.53 against the NEXT swing, whose wall pair landed at 96.67): a dodge that dropped no blow
    // (none dropped here, no 'the attacker decided our dodge' notice) ends its long cooldown MD_FAIL_CD_MS after the press - every ruling of that press is in by
    // then (the attacker's copy of the i-frames lasts 380 ms + the way back). A dodge that worked keeps the full cooldown. t2r-dodge-fail-cd-old.txt = old.
    {   static uint64_t chk;
        if (g_mdg.press_ms && chk != g_mdg.press_ms && now >= g_mdg.press_ms + MD_FAIL_CD_MS) {
            chk = g_mdg.press_ms;
            if (mdg_cd36()) {      // ps36: the ruling is in - a dodge that dropped nothing pays the cooldown now (one that worked was freed by mdg_ok_note)
                if (!g_mdg.dodged_hits && g_mdg_ok_ms < g_mdg.press_ms && g_md45_inwin && !md45_failcd_old()) {
                    xlog("dodge: ps45 the dodge of %llu ms ago (pressed in the window) dropped no blow - FAILED, cooldown %d ms from its press (ps36: %d) - the next swing is dodgeable", (unsigned long long)(now - g_mdg.press_ms), MD_FAIL_CD_MS, MD_COOLDOWN_MS);
                } else
                if (!g_mdg.dodged_hits && g_mdg_ok_ms < g_mdg.press_ms && g_mdg.cooldown_until < g_mdg.press_ms + MD_COOLDOWN_MS) {
                    g_mdg.cooldown_until = g_mdg.press_ms + MD_COOLDOWN_MS; g_mdg.bar_t0 = g_mdg.press_ms;
                    xlog("dodge: the dodge of %llu ms ago dropped no blow - FAILED: cooldown %d ms from its press (ps36; a dodge that works has none)", (unsigned long long)(now - g_mdg.press_ms), MD_COOLDOWN_MS);
                }
            } else
            if (!g_mdg.dodged_hits && g_mdg_ok_ms < g_mdg.press_ms && g_mdg.cooldown_until > now && GetFileAttributesA("t2r-dodge-fail-cd-old.txt") == INVALID_FILE_ATTRIBUTES) {
                xlog("dodge: the dodge of %llu ms ago dropped no blow - its cooldown ends now (%llu ms were left; a dodge that works keeps %d ms; ps23)", (unsigned long long)(now - g_mdg.press_ms), (unsigned long long)(g_mdg.cooldown_until - now), MD_COOLDOWN_MS);
                g_mdg.cooldown_until = now; g_mdg.bar_t0 = 0;
            }
        }
    }
    // the dodger's own limits
    if (g_mdg.gun_lock_until && !busy) {
        if (now >= g_mdg.gun_lock_until) {
            xlog("dodge: dodger free again (%llu ms after the press, %d blow(s) dodged)", (unsigned long long)(now - g_mdg.press_ms), g_mdg.dodged_hits);
            g_mdg.gun_lock_until = 0;
        } else if (!g_mhs.on) {
            uint64_t ex[4] = {fnv64("camera"), fnv64("move"), 0, 0};
            int n = 2;
            if (now >= g_mdg.melee_ok_at) { ex[n++] = fnv64("melee-attack"); ex[n++] = fnv64("melee-attack-shiv"); }
            dc_call(fnv64("joypad-disable-all-commands-except"), n, ex);
        }
    } else if (g_mdg.gun_lock_until && busy) g_mdg.gun_lock_until = 0;
    // the attacker's recovery after a dodged blow
    if (g_mdg.atk_lock_until) {
        if (now >= g_mdg.atk_lock_until || busy) {
            xlog("dodge: attacker recovered (%s)", busy ? busy : "time up");
            g_mdg.atk_lock_until = 0;
        } else if (!g_mhs.on && !g_mdg.gun_lock_until) {
            uint64_t ex[2] = {fnv64("camera"), fnv64("move")};
            dc_call(fnv64("joypad-disable-all-commands-except"), 2, ex);
        }
    }
}

#ifndef T2R_RELEASE
// ---------------------------------------------------------------------------------------------------------------------------------------------
// DEV test support for pairtest.c ("dodge" job): no synthetic keyboard / mouse. The presses are injected INTO the game's own joypad-command-active? reads (the
// script VM's record: generic handler +8 and typed pointer +0x10, the same record the world-prompt VM hook wraps): "evade" / "evade-start" / "evade-press" read
// true on B for ~120 ms starting `late` ms after its dodge window opens, "melee-attack" reads true on A for ~110 ms. Our own pad_cmd_on reads go through the
// same record, and mdg_tick also ORs the press directly, so the ext-side dodge path runs even if the engine's reads are not those names ("engine_hook_hits" in
// the RESULT line says how many engine reads saw the injected press).
static struct {
    int armed, k, none, late_ms, opened, pressed, blows, dodged, miss_n, installed;
    uint64_t armed_ms, open_ms, press_at, evade_until, melee_until;
    unsigned evade_hits, melee_hits;
    char miss_anim[64];
} g_mdgt;
static fn_dccall g_mdgi_gen;
static uint64_t (*g_mdgi_typed)(uint64_t, uint64_t, uint64_t, uint64_t, uint64_t, uint64_t, uint64_t, uint64_t, uint64_t);
static int mdgi_want(uint64_t sid) {
    uint64_t now = GetTickCount64();
    if (g_mdgt.evade_until > now && (sid == fnv64("evade") || sid == fnv64("evade-start") || sid == fnv64("evade-press"))) { g_mdgt.evade_hits++; return 1; }
    if (g_mdgt.melee_until > now && sid == fnv64("melee-attack")) { g_mdgt.melee_hits++; return 1; }
    return 0;
}
// The generic handler's real signature returns the pointer to its ret block (holster_trace.c fn_dccall_r; the VM reads the answer through the returned
// pointer: a void thunk left garbage in rax and the VM dereferenced 0x1 - crash at exe+161359c). So: call the ORIGINAL first (same args, same
// ret block, same return pointer), then only flip the answer's low byte to true for the injected command.
typedef uint64_t *(*mdgi_gen_t)(uint64_t *ret, int argc, uint64_t *argv, uint64_t sec);
static uint64_t *mdgi_thunk_gen(uint64_t *ret, int argc, uint64_t *argv, uint64_t sec) {
    uint64_t *r = ((mdgi_gen_t)g_mdgi_gen)(ret, argc, argv, sec);
    if (ret && argc >= 1 && argv && !IsBadReadPtr(argv, 8) && mdgi_want(argv[0])) {
        ret[0] = (ret[0] & ~0xffULL) | 1;
        if (!r) r = ret;
    }
    return r;
}
static uint64_t mdgi_thunk_typed(uint64_t a, uint64_t b, uint64_t c, uint64_t d, uint64_t e, uint64_t f, uint64_t g, uint64_t h, uint64_t j) {
    uint64_t r = g_mdgi_typed(a, b, c, d, e, f, g, h, j);
    return mdgi_want(a) ? (r & ~0xffULL) | 1 : r;
}
static void mdgt_install(void) {
    if (g_mdgt.installed) return;
    g_mdgt.installed = 1;
    uint8_t *rec = (uint8_t *)((fn_lookup)VMA(0x18000A190))(fnv64("joypad-command-active?"));
    if (!rec) { xlog("pairtest: dodge test: no joypad-command-active? record - presses go through the ext's own reads only"); return; }
    fn_dccall gen = *(fn_dccall *)(rec + 8);
    void *typed = *(void **)(rec + 0x10);
    DWORD old; int n = 0;
    if (gen && is_code((void *)gen) && !IsBadWritePtr(rec + 8, 8)) { g_mdgi_gen = gen; *(mdgi_gen_t volatile *)(rec + 8) = mdgi_thunk_gen; n |= 1; }
    if (typed && is_code(typed) && VirtualProtect(rec + 0x10, 8, PAGE_READWRITE, &old)) {
        g_mdgi_typed = (uint64_t (*)(uint64_t, uint64_t, uint64_t, uint64_t, uint64_t, uint64_t, uint64_t, uint64_t, uint64_t))typed;
        *(void *volatile *)(rec + 0x10) = (void *)mdgi_thunk_typed; n |= 2;
    }
    xlog("pairtest: dodge test: injection hook on joypad-command-active? (generic %s, typed %s)", n & 1 ? "yes" : "no", n & 2 ? "yes" : "no");
}
// A: forget the last test swing's miss, then press melee for ms
static void mdgt_a_press_melee(int ms) {
    mdgt_install();
    g_mdgt.miss_n = 0; g_mdgt.miss_anim[0] = 0; g_mdgt.melee_hits = 0;
    g_mdgt.melee_until = GetTickCount64() + (uint64_t)ms;
}
// B: armed by the attacker's PT_DODGE message
static void mdgt_b_arm(int k, int none, int late_ms) {
    mdgt_install();
    uint64_t now = GetTickCount64();
    g_mdgt.armed = 1; g_mdgt.k = k; g_mdgt.none = none; g_mdgt.late_ms = late_ms < 0 ? 0 : late_ms > 2000 ? 2000 : late_ms; g_mdgt.armed_ms = now;
    g_mdgt.opened = g_mdgt.pressed = g_mdgt.blows = 0;
    g_mdgt.open_ms = g_mdgt.press_at = g_mdgt.evade_until = 0; g_mdgt.evade_hits = 0;
    g_mdgt.dodged = 0;
    xlog("pairtest: v #%d dodge armed: %s, late %d ms after the window opens tms %llu", k, none ? "NO press (control: the blow must land)" : "press", g_mdgt.late_ms, (unsigned long long)now);
}
static void mdgt_on_window_open(uint64_t now) {
    if (!g_mdgt.armed || g_mdgt.opened) return;
    g_mdgt.opened = 1; g_mdgt.open_ms = now;
    if (!g_mdgt.none) g_mdgt.press_at = now + (uint64_t)g_mdgt.late_ms;
    xlog("pairtest: v #%d dodge window opened (%s) tms %llu", g_mdgt.k, g_mdgt.none ? "no press will follow" : "evade press injected after the delay", (unsigned long long)now);
}
static int bot_evade_now(void);   // bot.c
static int mdgt_press_now(uint64_t now) { return (g_mdgt.armed && g_mdgt.evade_until > now) || bot_evade_now(); }
static void mdgt_note_blow(uint64_t w, float dmg) { if (g_mdgt.armed && dmg > 0.0f && dmg < 100000.0f && mhs_is_blow(w)) g_mdgt.blows++; }
static void mdgt_note_dodged(void) { if (g_mdgt.armed) g_mdgt.dodged++; }
static void mdgt_note_miss(const char *anim) { g_mdgt.miss_n++; snprintf(g_mdgt.miss_anim, sizeof g_mdgt.miss_anim, "%s", anim ? anim : "none"); }
static void mdgt_tick(uint64_t now) {
    if (!g_mdgt.armed) return;
    if (g_mdgt.press_at && !g_mdgt.pressed && now >= g_mdgt.press_at) {
        g_mdgt.pressed = 1; g_mdgt.evade_until = now + 120;
        xlog("pairtest: v #%d dodge: evade press injected %llu ms after the window opened tms %llu", g_mdgt.k, (unsigned long long)(now - g_mdgt.open_ms), (unsigned long long)now);
    }
    if ((g_mdgt.opened && now > g_mdgt.open_ms + 3000) || (!g_mdgt.opened && now > g_mdgt.armed_ms + 15000)) {
        int dodged = g_mdgt.dodged;
        xlog("pairtest: v #%d dodge RESULT window=%d pressed=%d late=%d blows_seen=%d dodged=%d landed=%d iframes_ms=%d engine_move=%d fallback=%d engine_hook_hits=%u gun_lock_ms=%d melee_ok_ms=%d cooldown_ms=%d tms %llu",
             g_mdgt.k, g_mdgt.opened, g_mdgt.pressed, g_mdgt.late_ms, g_mdgt.blows, dodged, g_mdgt.blows - dodged, g_mdgt.pressed ? MD_IFRAME_MS : 0, g_mdg.mode == 2, g_mdg.mode == 3,
             g_mdgt.evade_hits, MD_GUN_LOCK_MS, MD_MELEE_OK_MS, MD_COOLDOWN_MS, (unsigned long long)now);
        g_mdgt.armed = 0;
    }
}
#endif
