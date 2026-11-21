// paired.c - psync: paired moves in sync on every client (paired.h, re/paired-sync.md). Included near the end of
// t2r-ext.c (uses its helpers: dc_call, xlog, player_locator, anim tables, the gun-execution timeline g_gx).
//
// Lifecycle of one move (uid = initiator slot << 24 | counter):
//   initiator  psync_start: solve / take the ap, suspend the partner puppet's network channels, animate_ both halves
//              around the ap (own body + puppet), broadcast START (resent at +100 / +300 ms with its move time).
//   receivers  psync_recv START: victim (role 2) - the kind's owner logic accepts it (gx_victim_begin for the E
//              executions; refused -> ABORT back), then both halves (own body + the attacker's puppet); third party
//              (role 3) - both halves on both puppets. Start phase advanced by the initiator's move time at the send
//              plus the one-way latency (PING / PONG RTT / 2), as ND's NetEventStartMelee (+0x388 frames).
//   everyone   psync_tick: per-frame log of both bodies in apReference space (the same numbers on every screen at the
//              same move time = in sync), channel bypass counters, collision, partner checks, resends; at the end of
//              the longer half the puppets are released (net channels back, interpolation reset).
//   abort      psync_abort(notify): both halves blended out, puppets released, ABORT broadcast; receivers do the same.
//              Death is never applied here: the victim's own client kills the victim (the execution tail) - the
//              owner authorises its body's death, as ND's ProcessMeleeAction does with the net game on.

// START is reliable (desync log: the START of a stunned victim's shiv never played there - its dedupe ring still held the
// same uid from an earlier match with this attacker's previous session, and nothing told the attacker): the victim ACKs a START it plays, the
// attacker resends (PS_RESEND_MS copies) until the ACK / an ABORT, and aborts its half cleanly (shiv refunded) PS_ACK_WAIT_MS + rtt after the START.
static const double PS_RESEND_MS[4] = {100.0, 220.0, 340.0, 460.0};
#define PS_ACK_WAIT_MS 400.0
#define PS_SEEN_MS 20000.0         // a START uid is a duplicate only this long (attacker restarts / new matches reuse uids)
enum { PS_AB_BUSY = 1, PS_AB_FAR, PS_AB_REFUSED, PS_AB_NOPLAY, PS_AB_NOACK, PS_AB_GENERIC };   // ABORT's reason (the wire's resend byte)
static const char *psync_ab_name(unsigned r) {   // names in every ABORT log line (0 = the sender cut its own move, no refusal)
    switch (r) { case 0: return "SENDER-CUT"; case PS_AB_BUSY: return "BUSY"; case PS_AB_FAR: return "FAR"; case PS_AB_REFUSED: return "REFUSED"; case PS_AB_NOPLAY: return "NOPLAY"; case PS_AB_NOACK: return "NOACK"; case PS_AB_GENERIC: return "GENERIC"; case 7: return "DODGED"; case 8: return "ESCAPED"; default: return "?"; }
}
#define PS_PING_MS 2000.0
#define PS_DEFAULT_ONEWAY 60.0f    // ms, until a PONG measured the peer
#define PS_BLEND 0.3f              // minimum blend-in of every half (same on every client); g_ps_blend grows with the start distance
// TLOU2 SP's own pull onto a paired move (SP sandbox, re/contextual-downs.md "SP sandbox 10-12"): the attacker's align reaches the move's
// apReference path in 0.20 s whatever the offset (Abby wall takedown: 0.83 m / 42 deg in 0.20 s; Ellie disarm kill: 0.19 m in ~0.2 s), the
// remaining offset falling as (1 - x)^2 (quadratic ease-out); the victim is put onto the authored relation to the attacker within 1-3 frames
// (yaw 173 -> 180 in 0.05 s) while its body pose blends. ctxdown's takedowns start with it; t2r-cd-old-blend.txt = the distance-based blend.
#define PS_SP_PULL_S 0.20f
// melee smoothing opt-outs (default ON, files next to the exe, re-read every 2 s, state change logged "smooth:"): 0 noskip, 1 glide, 2 align (melee_beat.c), 3 windup (melee_beat.c)
static int smooth_off(int which) {
    static const char *const fn[4] = {"t2r-smooth-noskip-off.txt", "t2r-smooth-glide-off.txt", "t2r-smooth-align-off.txt", "t2r-smooth-windup-off.txt"};
    static const char *const nm[4] = {"no skip-ahead (a late START plays from frame 0 with a catch-up rate)", "glide to align (smoothstep position, capped turn)", "agreed align point in the beat RESULT", "windup stretch while the contact waits"};
    static int v[4] = {-1, -1, -1, -1}; static uint64_t at[4];
    uint64_t n = GetTickCount64();
    if (which < 0 || which > 3) return 0;
    if (v[which] < 0 || n - at[which] >= 2000) {
        at[which] = n; int o = GetFileAttributesA(fn[which]) != INVALID_FILE_ATTRIBUTES;
        if (o != v[which]) xlog("smooth: %s %s", nm[which], o ? "OFF (opt-out file present)" : "on");
        v[which] = o;
    }
    return v[which];
}
static int bq_align_vic(int att_slot);     // melee_beat.c (smooth:align)
#define PS_CATCH_RATE 0.15f        // smooth:noskip - max catch-up rate (x1.15) of a late duel START that plays from frame 0
#define PS_CATCH_MAXLAG_MS 90.0f   // ... what x1.15 absorbs in ~600 ms; a lateness beyond it is still skipped (the remainder only)
// cluster A ('janky watching others'): a BYSTANDER (psync role 3) sees the pair one-way later (170-350 ms of a 3-player match; its
// START skipped 130-260 ms of the clip and pulled both bodies 0.6-2.9 m in 0.2 s). It has nothing to answer, so it plays from frame 0 and absorbs up to
// PS_CATCH_BYST_MAXLAG_MS at up to x1.20 (the move clock keeps the shared time, so hand-off / kill / blend-out stay on time); the start pull of both bodies lasts
// >= 0.25 s and at most 3.5 m/s / 360 deg/s (<= 0.8 s), one duration for both (moved as one). TUNING (labelled: no 2013 data for bystander views). t2r-byst-smooth-old.txt = old.
#define PS_CATCH_BYST_MAXLAG_MS 330.0f
#define PS_CATCH_BYST_RATE 0.20f
static int byst_old(void) { static int off = -1; if (off < 0) { FILE *f = exe_side_open("t2r-byst-smooth-old.txt", "r"); off = f != NULL; if (f) fclose(f); } return off; }
static uint32_t g_ps_fin_step_uid;  // v5-geo2: a duel finisher started closer than its intro's start spot (ctxdown cd_upg_go): psync_fin_step holds our distance through the intro
static int g_ps_fin_pull;          // set by ctxdown's cd_upg_go around a duel finisher's psync_start: the attacker closes a far gap at a run-in rate (PS_FIN_PULL_MS)
#define PS_FIN_PULL_MS 2.6f          // m/s: from 2.4 m (the 4th punch's knockback) the finisher starts on the press frame and the attacker steps in over ~0.5 s
static float g_ps_start_skip_ms;     // ctxdown sets it right before psync_start: the move starts this far into its first segment (consumed by the call)
#define PS_MAXSEG 5
static float g_ps_blend = PS_BLEND;
// the 2013 revive pair (revive2013.c): a 3-segment chain ENTER -> LOOP (restarted until the revive completes) -> FINISH, kind PS_REVIVE
#define RV_BLEND 0.6f                // the blend onto the first segment: the downed body gets onto its knees, the reviver walks onto its spot
static int rv_chain_of(uint64_t *att, uint64_t *vic, float *spd, float *cut, int max);       // revive2013.c: the segments (0 = the clips are not in this build)
static int rvnr_chain(double now);                                                            // revive2013.c: the kneel help-up chain's switches (1 = it is that chain)
static void rv_ps_ended(const char *why, int cancelled);                                      // revive2013.c: the move is over here (called with g_ps still valid)
static int rv_victim_begin(uint32_t slot, uint64_t skipf);                                    // revive2013.c: we are the revived (0 = refuse)
static void rv_victim_cancel(const char *why);
static void rv_aborted(int role, uint32_t from);                                              // revive2013.c: the other player aborted it
static void rv_ps_started(void);                                                              // revive2013.c: a revive move plays here (any role)
static int rv_loop_tail(void);                                                                // revive2013.c: the loop ran out a moment before the revive completes (a screen that only watches)
// the BODYSHIELD grab (bodyshield.c, re/bodyshield-1117.md): a 3-segment chain ENTER -> HOLD (restarted, swapped plain / aim) -> END (escape / finisher / shield death, set by bodyshield.c)
static int bs_chain_of(uint64_t move, uint64_t *att, uint64_t *vic, float *spd, float *cut, int max);  // bodyshield.c: the segments from the START's move word (0 = not in this build)
static int bs_victim_begin(uint32_t slot, uint32_t uid, uint64_t move, uint64_t skipf);         // bodyshield.c: we are the grabbed (0 = refuse)
static void bs_victim_cancel(const char *why);
static void bs_ps_ended(const char *why, int cancelled);                                       // bodyshield.c: the move is over here (g_ps still valid)
static void bs_ps_started(void);                                                              // bodyshield.c: the grab plays here (any role)
#define PS_END_PAD_MS 120.0        // after the longer half: release the puppets
// ---- smoothing (executions were stiff at their end and too dependent on ping).
// t2r-psync-no-smooth.txt next to the exe = the old behaviour (every item below off):
//  - the attacker half fades out over its LAST PS_OUT s (own body back to locomotion, the puppet handed back to the network under
//    the fading clip) instead of holding its last pose until the longer half + PS_END_PAD_MS and stopping then;
//  - a released puppet's locator goes from where the clip left it to the net locator over PS_HB_* (offset decay, no pop);
//  - a discontinuity in a driven puppet's clip placement (layer dropped / re-applied, kick-fix hold, a missed frame) is absorbed
//    and decays over ~PS_JUMP_TAU instead of a hard snap; a vanished layer's phase follows the move time instead of jumping to 1;
//  - phase drift of a half vs the shared move time is corrected with a small playback-rate change (<= PS_RATE_MAX), never a jump.
#define PS_OUT_DRIVE_MAX_M 0.30f   // [TUNING ps41] m: beyond this our body was not following the attacker half when its fade starts (psync_att_out)
static uint64_t g_ps_att_gone43_f; static uint32_t g_ps_att_gone43_uid;   // ps43 P1: the frame / pair in which the attacker half's layer read gone (psync tick's kick fix / lost layer -> psync_drive)
#define PS_OUT 0.25f               // attacker half blend-out (s), started PS_OUT before its clip end - same move time on every client
// (melee needs blending; live 165: 347 hand-backs, p90 0.66 m offset, 10 over 1 m): longer glides back to the net locator
#define PS_HB_MIN 0.40f            // hand-back to the net locator: window (s) = PS_HB_MIN + PS_HB_PER_M * start offset, <= PS_HB_MAX
#define PS_HB_PER_M 0.35f
#define PS_HB_MAX 0.9f
#define PS_HB_SNAP_M 4.0f          // a larger offset (respawn / teleport) is taken as is
#define PS_JUMP_TAU 0.14f          // placement discontinuity decay time constant (s): 95 % gone in 0.24 s
#define PS_RATE_MAX 0.10f          // max playback-rate change for the drift correction (+-10 %)
static int g_ps_smooth = 1;
static int g_ps_att_out_drive = 1;   // t2r-no-att-out-drive.txt next to the exe = off (our attacker body is left to the engine at its blend-out)

static struct {
    int role;                      // 0 idle, 1 initiator (attacker, our body plays att), 2 victim (our body plays vic), 3 third party
    int kind, flags, pair;
    uint32_t uid;
    int att, vic;                  // slots
    uint64_t att_sid, vic_sid, weapon, move;
    float ap[7];                   // shared apReference (world)
    psync_bf bf_att, bf_vic;       // per-half BoundFrames (ap, or ap o inv(C) for carrier clips)
    float c_att[8], c_vic[8];      // each half's align at phase 0 for an identity ap (C), valid flags below
    int c_att_ok, c_vic_ok;
    float kill_s, dur_s, att_dur, vic_dur;
    uint64_t f_audit;              // g_frame at the start (blend audit)
    int vdefer, vic_early;          // chain victim half deferred to just before the contact (vic_early: started already, the switch keeps it)
    double vic_early_t;             // v5-feel2: the move time (ms, segment 0) the deferred victim half really started - its own clock's zero
    float ahold; int ahold_on;     // duel hit-stop: our attacker half frozen on its contact frame for ahold s while the victim half waits (see psync_start)
    float hs_rate;                 // melee_duel_contact.c: > 0 = the duel hit-confirm hold plays BOTH halves at this rate from frame 0 (no frozen frame), 0 = the frozen hold
    float catch_ms; int catch_n;       // smooth:noskip - ms of lateness the halves absorb with a rate up to 1 + PS_CATCH_RATE (0 = none)
    float irate, ilate; int irate_n;   // v5 duel finisher intro on a late screen: the attacker half's intro runs at irate (from frame 0) to absorb ilate ms
    float vrate; int vrate_n;          // a duel -hit pair's VICTIM half runs at this rate on every screen (MDU_REACT_RATE, melee_duel.c mdu_react_rate), 0 = the clip's own of lateness
    float vlag, clk_shift; int vlag_hold, vlag_pins, vhold_seg;     // victim half starts vlag s after the attacker's (dodge counter: SP plays the "-hit" half at CONTACT, trace +0.47 s); held frozen on its first frame until then
    // a CHAIN of clip pairs (ctxdown's takedowns: push into the surface -> one quick hit -> the finisher): segment i plays seg_att[i] / seg_vic[i] at seg_spd[i]; when the
    // shorter half of the current segment ends, every client switches both halves to the next one on the SAME move clock (t0 moves forward by the boundary, so t is the time
    // inside the current segment, chain_shift the sum of the boundaries). nseg <= 1: an ordinary single-pair move.
    int nseg, cur_seg;
    uint64_t seg_att[PS_MAXSEG], seg_vic[PS_MAXSEG];
    float seg_spd[PS_MAXSEG], seg_cut[PS_MAXSEG];      // seg_cut: clip seconds played before the switch (0 = to the shorter half's end)
    double chain_shift;
    float speed;                   // playback speed of both halves (1 = the clips' own; ctxdown plays its long takedowns sped up). att_dur / vic_dur / dur_s are REAL-time lengths (clip / speed)
    double t0;                     // QPC ms of move time 0 (receivers: their start minus the skip)
    float skip_ms;
    uint64_t ent_att, ent_vic;     // SID_PLAYER or the puppet handle playing that half here
    uint64_t r_att, r_vic;         // animate_ results
    uint64_t start_frame;
    int resend;                    // copies sent (initiator)
    int acked; double start_ms;    // initiator: the victim's ACK arrived / the START's send time
    int ack_cap;                   // the victim's build ACKs (a PONG said so): no ACK within PS_ACK_WAIT_MS + rtt = abort
    int ended, released;
    int last_sync_bucket;          // 100 ms buckets of the "psync sync" lines
    float max_err[2], sum_err[2]; int n_err[2];   // |our body - the clip's placement for the half's phase| (m), after the blend-in
    float max_err_bl[2];           // the same during the blend-in (the body slides from where it stood)
    uint32_t log_n;
    // the clip's placement of each half this frame (world, ap o inv(apReference(phase)), psync_place), its half-yaw unwrap
    float place[2][8]; int place_ok[2];
    float half_yaw[2]; int half_yaw_ok[2];
    float start_loc[2][8]; int start_ok[2];    // each body before the start (the puppet drive blends from it)
    double play_ms;                // QPC ms when the halves were started here
    uint8_t vic_throat;            // shivdeath_tick put an SP throat-cut death clip on the victim body: the half is not re-applied over it
    uint8_t pr_on, pr_tried; int pr_n;   // power ragdoll (psync_pr_tick): the engine's keyframed-till-first-collision ragdoll is on for the victim
    uint8_t vic_keep; int keep_n;  // the victim is dead (engine Death state) but its half plays to its end: re-assert the layer if the state dropped it
    // smoothing (g_ps_smooth)
    double prev_tick; float tick_dt;           // QPC ms of the previous psync_tick, its frame time (ms)
    float drv_raw[2][8]; int drv_ok[2];        // the previous frame's raw drive target (clip placement / start blend) per half
    float off_p[2][3], off_q[2][4];            // the absorbed placement discontinuity (decays to 0 / identity)
    int jumps[2];
    float wS[PWS_NK][2], wtend, wD[2]; uint8_t wsh_ok, wsh_dyn;   // pair shift (pairshift.c): the shift profile over the move (keys, seconds), its current D(t), verified / sliding flags
    float rate[2]; int rate_n[2];              // current playback rate set on the half (0 = never set = 1.0), changes logged
    int out_done[2];                           // the half's blend-out started (attacker: PS_OUT before its end)
    // victim root (our victim body did not travel the way the 2013 victim does, psync_vic_root_* below)
    uint8_t vic_own_lethal;                    // our own body plays the victim half of a lethal move (death-anim side withheld from the start)
    int lost[2], lost_n[2];                    // the half's layer is gone (phase read 0 / -1 while the move time is well into it)
    float mt[2];                               // the half's phase by the shared move time (t / its clip length), this frame
    int own_drv; uint32_t own_drv_n;           // our own victim body placed on the clip by psync (the engine stopped moving it)
    float att_last[8]; int att_last_ok;        // the last locator psync placed our attacker body at (handed to the engine's player when the blend-out drive ends)
    double att_drive_until;                    // our own ATTACKER body is placed on its clip by psync until this QPC ms (its blend-out: the engine drops the clip's root motion in one frame)
    double keep_last;                          // QPC ms of the last re-apply of a dropped victim half
    uint64_t wall_job; int wall_hold, wall_hits; float wall_pos[3], last_put[3]; int last_put_ok; float put[2][3]; int put_ok[2]; int place_bucket;   // wall guard of the driven victim body
    uint64_t gr_job[2], gr_job2[2], gr_job3[2]; float gr_dy[2], gr_a[2][3]; int gr_ok[2], gr_n, gr_rej;   // slope grounding of the puppet halves (psync_drive): pending floor ray, smoothed floor delta vs the ap's floor
    int root_bucket;                           // 250 ms buckets of the "victim root:" lines
    float max_err_dead[2];                     // |body - clip placement| after the kill (the kept victim half), m
    // the puppet drive's blend from where a body stood onto its half (psync_drive): its length (s) and curve (0 smoothstep, 1 SP's quadratic
    // ease-out); seg_drive_bl = the distance-based length the chain's segment switches keep using (they are not SP's start pull)
    float drive_bl, seg_drive_bl; int drive_easeout;
    // the revive chain (PS_REVIVE): rv_fin = the revive completed (MSG_REVIVE: switch to the finish segment), rv_loops = segment switches so far
    int rv_fin; double rv_fin_ms; int rv_loops;
} g_ps;
// we run a paired move of our OWN (role 1 attacker / 2 victim); role 3 = our copy of a third player's move (bystander), which
// must not block our melee (duel blows, parry, pin, auto-draw)
#define PS_OURS (g_ps.role && g_ps.role != 3)
// melee_duel_tl.c (the duel timeline, included much later): the duel bodies' presentation arbiter
static int dtl_on(void); static void dtl_note_pair(uint32_t slot); static void dtl_note_abort(const char *why); static int dtl_trade_yield(const psync_wire *w, uint32_t from);
static int dtl_hb_take(int s, uint64_t h, const char *why); static float dtl_pull_s(int k, uint64_t ent, float dbl);   // v5-body: the duel partner's hand-back / start pull (melee_duel_tl.c)
static void dtl_loc_reset(int s); static void dtl_cut(const char *what, uint32_t slot, uint64_t sid, const char *why); static void dtl_trim(const char *what, int ms, const char *why);
// melee_duel_contact.c (included after melee_duel_tl.c): every duel blow visibly connects - contact-frame timing on both screens (re/melee-duel-contact.md)
static void dtail_abort(const char *why);   // melee_duel_sptl.c: the swing clip's own tail on a dodged attacker
static float sptl_vic_drive_s(float dbl); static float sptl_own_att_blend(void); static float sptl_pup_att_blend(float xfade); static float sptl_seg_att_blend(float intro_phase); static void sptl_note_pair(void);   // melee_duel_sptl.c
static int mct_on(void); static void mct_hitstop_arm(void); static float mct_vic_blend(float bl); static void mct_note_pair(uint32_t slot); static int mct_pin_from0(uint64_t move, float skip_ms); static float mct_pup_blend(float bl); static float mct_own_att_blend(float bl);
static float g_ps_off_d[2] = {-1.0f, -1.0f}, g_ps_off_y[2];   // psync_play: each half's offset from its spot at the start (m / deg), for mct_vic_blend
static int g_ps_ground = 1;         // t2r-no-psync-ground.txt next to the exe = off (puppet halves are not re-grounded on slopes)
// A/B Bookstore (on B's screen A was constantly shifting downwards into the patio and above it during the pin; B [21996] 'psync ground: u01726563
// attacker half slot 1 floor -1.80 under 72.12 432.48 vs the ap's -1.13: y -0.68 (applied -0.68)', the next blows 'floor -1.87 ... REJECTED ... kept +0.00'; A's own
// screen read 'floor -1.91' under its victim puppet too, and both travel clamps logged 'ledge (no floor within 0.8 m below)' on the patio): the converted Part I
// collision of the patio is not in the 0x207 / 0x1b07 cast filters (the fallprobe.c finding), so every down ray there passes the floor the bodies stand on and
// reads the courtyard 0.7 m below. Calibration: once per pair a down ray at the ap itself - where a body provably stands on the floor. When it reads no floor,
// or one more than 0.25 m below the ap, the rays are blind on this ground: no ground delta and no ledge planes for the pair (both halves stay on the ap's
// height, like the bodies on their own screens). t2r-ps-blind-old.txt = old (trust every reading).
static int ps_loc_ok(const float *l);
static struct { uint32_t uid; uint64_t job; int state; } g_psb;      // state: 0 unknown, 1 rays see the floor, 2 blind
static int ps_rays_blind(void) {
    static int old = -1; static uint64_t at; uint64_t n = GetTickCount64();
    if (old < 0 || n - at > 3000) { at = n; old = GetFileAttributesA("t2r-ps-blind-old.txt") != INVALID_FILE_ATTRIBUTES; }
    if (old || !g_ps.uid) return 0;
    if (g_psb.uid != g_ps.uid) {
        if (g_psb.job) ray_t(g_psb.job);
        g_psb.uid = g_ps.uid; g_psb.state = 0;
        float a[3] = {g_ps.ap[0], g_ps.ap[1] + 0.6f, g_ps.ap[2]}, b[3] = {g_ps.ap[0], g_ps.ap[1] - 1.4f, g_ps.ap[2]};
        g_psb.job = ps_loc_ok(a) ? world_ray_kick_m(a, b, g_ps.ent_vic ? g_ps.ent_vic : SID_PLAYER, 0x1b07) : 0;
        return 0;
    }
    if (g_psb.job && !g_psb.state) {
        g_ray_err = 0; float t = ray_t(g_psb.job); g_psb.job = 0;
        if (g_ray_err) return 0;
        float fl = t >= 0.0f && t <= 1.0f ? g_ps.ap[1] + 0.6f - t * 2.0f : -1e9f;
        g_psb.state = fl < g_ps.ap[1] - 0.25f ? 2 : 1;
        if (g_psb.state == 2) xlog("psync ground: u%08x the down ray at the ap %.2f %.2f %.2f reads %s - blind on this floor (Part I collision?): no ground delta / ledge planes for this pair",
                                   g_ps.uid, (double)g_ps.ap[0], (double)g_ps.ap[1], (double)g_ps.ap[2], t < 0.0f || t > 1.0f ? "no floor" : "a floor below it");
    }
    return g_psb.state == 2;
}
static int g_ps_gx_nowall = 1;      // t2r-no-gx-nowall.txt next to the exe = off (the wall guard also holds a gun execution's victim puppet)
static int g_ps_t744;              // ps44 T7: this frame's own victim body drive is the start glide of a non-duel victim half (psync_drive)
static int g_ps_vic_drive = 1;     // t2r-no-vic-root-drive.txt next to the exe = off (our dead victim body left where the engine leaves it)
static int g_ps_no_corpse;         // t2r-no-corpse-hold.txt next to the exe = a dead victim puppet is handed back to the network at the move's end (old)
static struct {
    volatile uint64_t h;
    uint8_t *volatile proc, *volatile ac;
    volatile int on;
    volatile LONG rep, root, gate, loc;      // bypass counters (replay, root write, pose/locator gate, net locator)
    LONG drv;                                // frames its locator was placed on the clip by psync_drive
    int early;                               // handed back to the network before the move ended (attacker half blend-out)
    int coll_off, hr_off;
    double since;
    // corpse hold (hunting rifle: the executed body stood up for ~0.2 s at the end of the move, then dropped):
    // a dead victim puppet keeps its net channels suspended after the move, its half frozen on the final pose, until it respawns
    int corpse; double corpse_ms; uint64_t corpse_sid;
} g_ps_pup[T2R_MAX_PEERS];
static float g_ps_rtt[T2R_MAX_PEERS];          // ms, EWMA; 0 = not measured
static struct { uint32_t uid; uint8_t from, st; double ms; } g_ps_seen[16]; static int g_ps_seen_i;   // st 0 = accepted, 1 = refused / aborted
static uint32_t g_ps_counter;
static uint8_t g_ps_ack_cap[T2R_MAX_PEERS];    // peers whose build ACKs a START
static int g_ps_log_every = 1, g_ps_no_suspend, g_ps_kickfix = 1;

static double psync_ms(void) {
    static double inv;
    LARGE_INTEGER q;
    if (!inv) { LARGE_INTEGER f; QueryPerformanceFrequency(&f); inv = 1000.0 / (double)f.QuadPart; }
    QueryPerformanceCounter(&q);
    return (double)q.QuadPart * inv;
}
static uint32_t psync_self(void) { return *(volatile uint32_t *)VMA(0x180138090); }
static uint64_t psync_puppet(int slot) {
    typedef uint8_t *(*fn_peer)(uint32_t);
    uint8_t *peer = slot >= 0 && slot < T2R_MAX_PEERS ? ((fn_peer)t2r_peer)((uint32_t)slot) : NULL;
    return peer && peer[4] ? *(uint64_t *)(peer + 0x60) : 0;
}
static const char *psync_name(uint64_t sid) {
    static char hx[4][20]; static int k;
    for (size_t i = 0; i < GX_N; i++)
        for (int j = 0; j < 2; j++)
            if (*GUNEXEC_CARRIER[i][j] && fnv64(GUNEXEC_CARRIER[i][j]) == sid) return GUNEXEC_CARRIER[i][j];
    for (size_t i = 0; i < GX_N; i++)
        for (int j = 0; j < 7; j++)
            if (*GUNEXEC_ATK_ALT[i][j] && fnv64(GUNEXEC_ATK_ALT[i][j]) == sid) return GUNEXEC_ATK_ALT[i][j];
    for (size_t i = 0; i < MX_N; i++)
        for (int j = 0; j < 2; j++)
            if (*MELEEEXEC_CARRIER[i][j] && fnv64(MELEEEXEC_CARRIER[i][j]) == sid) return MELEEEXEC_CARRIER[i][j];
    for (size_t i = 0; i < sizeof MELEEEXEC_VARIANT / sizeof MELEEEXEC_VARIANT[0]; i++)
        if (*MELEEEXEC_VARIANT[i].carrier && fnv64(MELEEEXEC_VARIANT[i].carrier) == sid) return MELEEEXEC_VARIANT[i].carrier;
    for (size_t i = 0; i < sizeof FIN_ANIMS / sizeof FIN_ANIMS[0]; i++) {
        if (fnv64(FIN_ANIMS[i].att) == sid) return FIN_ANIMS[i].att;
        if (fnv64(FIN_ANIMS[i].vic) == sid) return FIN_ANIMS[i].vic;
    }
    k = (k + 1) & 3;
    snprintf(hx[k], sizeof hx[k], "%016llx", (unsigned long long)sid);
    return hx[k];
}
// ---- locator math (pos xyz(w), quat xyzw at [4..7])
static void ps_qmul(const float *a, const float *b, float *o) {      // o = a * b
    float x = a[3] * b[0] + a[0] * b[3] + a[1] * b[2] - a[2] * b[1];
    float y = a[3] * b[1] - a[0] * b[2] + a[1] * b[3] + a[2] * b[0];
    float z = a[3] * b[2] + a[0] * b[1] - a[1] * b[0] + a[2] * b[3];
    float w = a[3] * b[3] - a[0] * b[0] - a[1] * b[1] - a[2] * b[2];
    o[0] = x; o[1] = y; o[2] = z; o[3] = w;
}
static void ps_qrot(const float *q, const float *v, float *o) {      // o = q v q*
    float t[3] = {2.0f * (q[1] * v[2] - q[2] * v[1]), 2.0f * (q[2] * v[0] - q[0] * v[2]), 2.0f * (q[0] * v[1] - q[1] * v[0])};
    o[0] = v[0] + q[3] * t[0] + (q[1] * t[2] - q[2] * t[1]);
    o[1] = v[1] + q[3] * t[1] + (q[2] * t[0] - q[0] * t[2]);
    o[2] = v[2] + q[3] * t[2] + (q[0] * t[1] - q[1] * t[0]);
}
static void ps_compose(const float *a, const float *b, float *o) {   // locators: o = a o b (b in a's space)
    float p[3], q[4];
    ps_qrot(a + 4, b, p);
    ps_qmul(a + 4, b + 4, q);
    o[0] = a[0] + p[0]; o[1] = a[1] + p[1]; o[2] = a[2] + p[2]; o[3] = 1.0f;
    memcpy(o + 4, q, 16);
}
static void ps_inverse(const float *a, float *o) {
    float qi[4] = {-a[4], -a[5], -a[6], a[7]}, p[3] = {-a[0], -a[1], -a[2]}, r[3];
    ps_qrot(qi, p, r);
    o[0] = r[0]; o[1] = r[1]; o[2] = r[2]; o[3] = 1.0f;
    memcpy(o + 4, qi, 16);
}
static void ps_ap8(const float *ap7, float *o) { o[0] = ap7[0]; o[1] = ap7[1]; o[2] = ap7[2]; o[3] = 1.0f; memcpy(o + 4, ap7 + 3, 16); }
static void ps_ap7(const float *l8, float *o) { o[0] = l8[0]; o[1] = l8[1]; o[2] = l8[2]; memcpy(o + 3, l8 + 4, 16); }
static int ps_loc_ok(const float *l) {
    for (int i = 0; i < 8; i++) if (i != 3 && !__builtin_isfinite(l[i])) return 0;
    float n = l[4] * l[4] + l[5] * l[5] + l[6] * l[6] + l[7] * l[7];
    return n > 0.25f && n < 4.0f && __builtin_fabsf(l[0]) < 1e5f && __builtin_fabsf(l[1]) < 1e5f && __builtin_fabsf(l[2]) < 1e5f;
}
// world locator of a body (our player or a puppet)
static const float *psync_loc(uint64_t ent, float *buf) {
    typedef void *(*fn_proc)(uint64_t);
    typedef const float *(*fn_loc)(void *, float *);
    if (ent == SID_PLAYER) return player_locator(buf);
    uint8_t *pr = ent ? ((fn_proc)VMA(0x18000A200))(ent) : NULL;
    return pr ? ((fn_loc)((uint8_t *)GetModuleHandleW(NULL) + 0x133db30))(pr + 0x100, buf) : NULL;
}
// a world locator in the shared apReference's space: x (ap left), z (ap forward), y up, yaw (deg, rel ap)
static void psync_in_ap(const float *l, float *o) {
    float a8[8], ia[8], r[8];
    ps_ap8(g_ps.ap, a8);
    ps_inverse(a8, ia);
    ps_compose(ia, l, r);
    o[0] = r[0]; o[1] = r[2]; o[2] = r[1]; o[3] = uc4_yaw(r);
}
// where the engine puts a half's align at `phase` for the BoundFrame `bf` (get-channel-locator-from-ap-ref
// impl 0x140d42130: align channel o inv(apReference channel), returned as a new BoundFrame) -> world locator
static int cd_local_move(uint64_t move);   // ctxdown.c
static int cd_counter_move(uint64_t move); // ctxdown.c
static int mdu_move(uint64_t move);
static int mpn_byst_replica(int slot);           // melee_duel_pin.c (brawl): an MDPO_BYST windup replica of this attacker slot is running on its puppet
static int mpn_byst_pair(uint64_t move);        // melee_duel_pin.c: a wall / low-cover pin blow pair (t2r-no-pin-byst-windup.txt aware)
#define PS_PIN_BYST_BLEND 0.30f                 // [TUNING] = melee_duel_pin.c PS45_PIN_SW_BLEND: the pin swing replica's crossfade off a held pair half
static int cd_wall_move(uint64_t move);
static int cd_cover_move(uint64_t move);   // ctxdown.c: a low-cover takedown / pin row
static int pul_drag_move(uint64_t move);   // ctxdown.c: a prone pull-out pair (kind 8)
static int pul_fail_move(uint64_t move);   // ctxdown.c: the pull-out fail pair (the death punch)
static float pul_ps_xfade(uint64_t move);  // melee_pullout.c (ps45 prone): SP's crossfade into a pull-out pair (s), 0 = not one / switched off
#define PUL_RISE_MS 650
static uint64_t g_pul_rise_until; static uint32_t g_pul_rise_uid;   // melee_pullout.c pul_rise_tick: the attacker held crouched after a pull-out fail blow until this
static int g_ps_pul_vdrv;                  // our live victim body was placed by psync in a pull-out (melee_pullout.c hands it to the engine at the end)    // ctxdown.c: a wall pin / wall takedown pair (its ap is the wall surface, the victim stands in front of it)
static int cd_mf_intro_move(uint64_t move); // ctxdown.c: a duel finisher (mf- row) whose segment 0 is SP's attacker-only intro (the windup)
static float cd_seg0_ms(uint64_t move);    // ctxdown.c: real ms of a chain's first segment
static float cd_stature_dy(int k, double now);   // ctxdown.c (ps46): metres added to a PUPPET half's placement y (the MP body's stature vs the clip's skeleton)
static void cd_stature_apply(int k, double now, float *t);   // ctxdown.c (ps46): the above for CD_STATURE rows + the kind 0 finishers (dy and the along-the-line dz)
static int psync_expected(uint64_t ent, uint64_t sid, const psync_bf *bf, float phase, float *out) {
    typedef const float *(*fn_loc)(void *, float *);
    uint64_t a[6] = {ent, sid, (uint64_t)bf, 0, 0x509903bb65ac341eULL /* align */, 0x05fed8d7a1d8cf89ULL /* apReference */};
    memcpy(&a[3], &phase, 4);
    uint64_t r = dc_call(fnv64("get-channel-locator-from-ap-ref"), 6, a);
    if (!r || r == ~0ULL || IsBadReadPtr((void *)r, 0x50)) return 0;
    float b[16];
    const float *l = ((fn_loc)((uint8_t *)GetModuleHandleW(NULL) + 0x133db30))((void *)r, b);
    if (!l || !ps_loc_ok(l)) return 0;
    memcpy(out, l, 32);
    return 1;
}
static float psync_phase(uint64_t ent, uint64_t sid) {
    uint64_t a[3] = {ent, ANIM_LAYER, sid};
    uint64_t r = dc_call(fnv64("get-animation-phase"), 3, a);
    float f = -1.0f; uint32_t lo = (uint32_t)r;
    if (r != ~0ULL) memcpy(&f, &lo, 4);
    return __builtin_isfinite(f) && f >= 0.0f && f <= 1.01f ? f : -1.0f;
}
// Rubberbanding back to downed after a special execution: 9 of 18 lethal victim halves were frozen at layer phase
// 0.000 instead of ~0.97 (u0022bcbc npc-bow-cover-low-r-hunker-enter-idle-r, the cap-npc-m-lg-search-look-below-enter-lt / -check-prone-space
// carriers): those carriers loop, the half had already wrapped to its first frame - the victim's start (downed) pose - when the hold froze it,
// so the corpse snapped back to where it lay before the move. A frozen half that reads back near its start is put on its end pose.
// (there should be no instant animations; dev24 round: the own -hit attacker half "blend 0 (cut)" x12, puppet attacker halves "starts with a cut"
// x3, finisher main clips "at full weight on the switch" x2, puppet -hit halves 0.04 s x14, crossfades 0.05 s x16): every melee clip start on a body blends in
// over at least MEL_MIN_BLEND (TUNING: 0.10 s = 6 frames at 60 fps), through the two animate helpers (psync_animate, mhr_animate). t2r-melee-cuts-old.txt = old.
#define MEL_MIN_BLEND 0.10f
#define PS_HIT_OWN_DRIVE_MS 320.0   // [TUNING ps24] psync places our attacker body through a duel -hit pair's blend-in (0.30 s) + one frame
// ps22 (SP log: the swing is cut to its -hit clip at phase 0, weight 1.0 on the contact frame, 119 / 119; our 0.10 s floor gave the -hit 35 % weight at its
// +35 ms impact frame = the fist 0.70 m from the chest with the roots right): the next animate's floor, set by the duel -hit attacker half only (2 frames).
static float g_mel_floor_once = -1.0f;
// ps40 D3 (rec39a one-frame pose pops when a pair takes a body that is in another move: B [22018] 'victim half ... on US blends in over 0.08 s' + [22019] 'combat
// dodge clip stopped after 906 ms (a pair's victim half took the body)' = 192.633; A [20118] parry pair 'victim half on US blends in over 0.08 s' = 195.167; A [16870]
// 'ABORT (slot 0 aborted it)' + START on the same frame, 'victim half on US blends in over 0.08 s' = 141.034; B [18702] 'engine -hit move ... at +384 ms (SP switch
// +303 ms)', 'att blend 0.034 s applied (asked 0: the floor)' = 137.133; A [20218] 'victim half on the puppet blends in over 0.12 s (off its spot 0.00 m / 45 deg)').
// The 2-frame (MEL_HIT_BLEND) and 0.04-0.08 s starts of a duel half are SP's for a body that stands on the authored switch pose (its swing's contact frame, the
// neutral stance). One rule for every other case: a half that takes a body out of ANOTHER move - our dodge clip, the previous pair's victim half still on it, a
// victim more than 30 deg off its facing, an attacker whose swing ran more than 50 ms past its SP switch frame - starts over PS_TAKE_BL from the pose the body
// has, never shorter. t2r-pair-take-blend-ps39.txt = old.
#define PS_TAKE_BL 0.10f    // [TUNING ps40] s (= MEL_MIN_BLEND, the floor every other scripted clip start already has; 3 frames of a 30 fps recording)
static double g_ps_end40_ms; static uint64_t g_ps_end40_vic;
// ps41 (bis40 r1 B [18580] 'swing switchblade-light-attack-1 cancelled at +203 ms: the partner's pair takes our body' + 'victim half ... on US blends in over
// 0.08 s' - the authored recoil pose of ellie-knife-combo-slash-1-hit--npc-m stands 60-100 deg of shoulder yaw off a wind-up pose, hipyaw.py table): a half that takes
// a body out of its OWN SWING (our body: the duel swing cut on this frame; a puppet: its swing replica still running) starts over PS_TAKE_SWING_BL.
#define PS_TAKE_SWING_BL 0.20f   // [TUNING ps41] s
static uint64_t g_mdu_sw_cut_ms;         // melee_duel.c mdu_swing_stop: when our running duel swing was last cut
static float g_ps_take_bl40;             // set by ps_take_other40: the entry blend its reason asks for
// ps42 J3: entry blend by MEASURED pose distance. melee_pose0.h = each melee clip's first-frame hip / shoulder line (offline decode, scratchpad ps42body/gen.py),
// in the frame the take-pose measurement below reads in game. Calibration from rec41a's chained takes (the body was in a known clip at a known time when the next
// half measured it): in-game line yaw = offline forward yaw - 90 deg, same sign, residuals -1 / +6, 0 / 0, +3 / -2, +3 / +1, +1 / 0 deg (hips / shoulders) over
// ellie-knife-combo-slash-1-hit--npc-m (male rig), abby-fist-combo-punch-1-left-hit--npc-f, abby-fist-combo-punch-1-hit--npc-f x2,
// abby-fist-hwall-enter-npc-close-hit--npc-f. A half that starts on its first frame (skip <= 50 ms) on a body whose drawn hips or shoulders stand more than
// PS_POSE_FAR_DEG off that frame starts over PS_TAKE_SWING_BL - whatever the reason. t2r-pair-pose-blend-off.txt = off (the measurement line stays).
#include "melee_pose0.h"
#define PS_POSE_FAR_DEG 60.0f   // tuning value (ps42)
static int ps_pose42_off(void) { static int v = -1; static uint64_t at; uint64_t n = GetTickCount64(); if (v < 0 || n - at > 2000) { at = n; v = GetFileAttributesA("t2r-pair-pose-blend-off.txt") != INVALID_FILE_ATTRIBUTES; } return v; }
static int ps_pose0(uint64_t sid, float *hip, float *sh) {
    int lo = 0, hi = (int)MEL_POSE0_N - 1;
    while (lo <= hi) { int mid = (lo + hi) / 2; if (MEL_POSE0[mid].sid == sid) { *hip = (float)MEL_POSE0[mid].hip; *sh = (float)MEL_POSE0[mid].sh; return 1; } if (MEL_POSE0[mid].sid < sid) lo = mid + 1; else hi = mid - 1; }
    return 0;
}
static const char *ps_take_other40(int k, int own);      // melee_duel_sptl.c: the other move that body is in right now (NULL = none)
static float ps_take_blend40(int k, int own, float bl) {
    static int off = -1; static uint64_t chk; uint64_t n = GetTickCount64();
    if (off < 0 || n - chk > 2000) { chk = n; off = GetFileAttributesA("t2r-pair-take-blend-ps39.txt") != INVALID_FILE_ATTRIBUTES; }
    if (off || g_ps.kind != PS_CTXDOWN) return bl;
    float d42 = -1.0f, th42 = 0.0f, ts42 = 0.0f, mh42 = 0.0f, ms42 = 0.0f;
    {   // ps41 (e), measurement only: the body's DRAWN hip / shoulder line against its root at every half start, with the clip - the numbers the offline table
        // (scratchpad ps40\hipyaw.py: hips / shoulders yaw of each half's first frame) has to be calibrated against (its zero and sign are not known in game yet)
        uint64_t e41 = k ? g_ps.ent_vic : g_ps.ent_att; float jl[3], jr[3], sl[3], sr[3], rb[16]; const float *rl = e41 ? psync_loc(e41, rb) : NULL;
        if (rl && ps_loc_ok(rl) && gx_joint_pos(e41, "l_upper_leg", jl) && gx_joint_pos(e41, "r_upper_leg", jr) && gx_joint_pos(e41, "l_shoulder", sl) && gx_joint_pos(e41, "r_shoulder", sr)) {
            float ry = uc4_yaw(rl), hy = uc4_wrap(__builtin_atan2f(jr[0] - jl[0], jr[2] - jl[2]) * 57.29578f - ry), sy = uc4_wrap(__builtin_atan2f(sr[0] - sl[0], sr[2] - sl[2]) * 57.29578f - ry);
            static int nl41; if (LOGCAP(nl41, 400)) xlog("psync: u%08x take pose - %s half %s (%016llx) on %s: the body's hip line %+.0f deg, shoulder line %+.0f deg from its root at the start (asked entry blend %.3f s; ps41 measurement)",
                                                       g_ps.uid, k ? "victim" : "attacker", psync_name(k ? g_ps.vic_sid : g_ps.att_sid), (unsigned long long)(k ? g_ps.vic_sid : g_ps.att_sid), own ? "US" : "the puppet", (double)hy, (double)sy, (double)bl);
            if (g_ps.skip_ms <= 50.0 && ps_pose0(k ? g_ps.vic_sid : g_ps.att_sid, &th42, &ts42)) {
                float dh = __builtin_fabsf(uc4_wrap(hy - th42)), ds = __builtin_fabsf(uc4_wrap(sy - ts42));
                d42 = dh > ds ? dh : ds; mh42 = hy; ms42 = sy;
            }
        }
    }
    g_ps_take_bl40 = PS_TAKE_BL;
    const char *why = ps_take_other40(k, own);
    if (d42 > PS_POSE_FAR_DEG && !ps_pose42_off()) {      // ps42 J3: the measured pose is far from the half's first frame
        float cur = bl < 0.0f ? g_ps_blend : bl, oth = why ? g_ps_take_bl40 : 0.0f;
        if (k == 0 && own) {      // our own attacker half: SP's contact-frame switch (ps22: a long blend leaves the fist short of the body at the impact frame) - measured only
            static int nm42; if (LOGCAP(nm42, 200)) xlog("psync: u%08x attacker half on US: the drawn body stands %.0f deg off the half's first frame (hips %+.0f vs %+.0f, shoulders %+.0f vs %+.0f) - entry blend left at %.3f s (own attacker halves are not lengthened; ps42 measurement)",
                                                         g_ps.uid, (double)d42, (double)mh42, (double)th42, (double)ms42, (double)ts42, (double)(cur > oth ? cur : oth));
        } else if (k == 0 && !own && g_ps.role == 3 && mpn_byst_pair(g_ps.move) && cur < PS_PIN_BYST_BLEND && oth < PS_PIN_BYST_BLEND) {
            // (frames 165410-165830: 'attacker half on the puppet starts over 0.20 s, not 0.180 s - the drawn body stands 87 deg off' on every pin blow a
            // bystander watched): the pin pair's attacker half on a puppet we only watch crossfades over the pin swing replica's 0.30 s (ps45) from a pose > 60 deg off.
            // t2r-no-pin-byst-windup.txt = the 0.20 s.
            static int nlp; if (LOGCAP(nlp, 200)) xlog("psync: u%08x pin attacker half on the puppet we watch (role 3) starts over %.2f s, not %.3f s - the drawn body stands %.0f deg off the half's first frame (hips %+.0f vs %+.0f, shoulders %+.0f vs %+.0f deg from the root) (t2r-no-pin-byst-windup.txt = %.2f s)",
                                                       g_ps.uid, (double)PS_PIN_BYST_BLEND, (double)(cur > oth ? cur : oth), (double)d42, (double)mh42, (double)th42, (double)ms42, (double)ts42, (double)PS_TAKE_SWING_BL);
            g_ps_take_bl40 = PS_PIN_BYST_BLEND;
            return PS_PIN_BYST_BLEND;
        } else if (cur < PS_TAKE_SWING_BL && oth < PS_TAKE_SWING_BL) {
            static int nl42; if (LOGCAP(nl42, 300)) xlog("psync: u%08x %s half on %s starts over %.2f s, not %.3f s - the drawn body stands %.0f deg off the half's first frame (hips %+.0f vs %+.0f, shoulders %+.0f vs %+.0f deg from the root; melee_pose0.h) (ps42; t2r-pair-pose-blend-off.txt = off)",
                                                         g_ps.uid, k ? "victim" : "attacker", own ? "US" : "the puppet", (double)PS_TAKE_SWING_BL, (double)(cur > oth ? cur : oth), (double)d42, (double)mh42, (double)th42, (double)ms42, (double)ts42);
            g_ps_take_bl40 = PS_TAKE_SWING_BL;
            return PS_TAKE_SWING_BL;
        }
    }
    if (!why) return bl;
    if (bl < 0.0f) { if (g_ps_take_bl40 <= g_ps_blend) return bl; }                         // (< 0 = the move's pull, g_ps_blend: kept when it is the longer one)
    else if (bl >= g_ps_take_bl40) return bl;
    static int nl; if (LOGCAP(nl, 200)) xlog("psync: u%08x %s half on %s starts over %.2f s, not %.3f s - the body is in another move (%s): no cut from a pose that is not the switch pose (ps40 / ps41)",
                                             g_ps.uid, k ? "victim" : "attacker", own ? "US" : "the puppet", (double)g_ps_take_bl40, (double)(bl < 0.0f ? g_ps_blend : bl), why);
    return g_ps_take_bl40;
}
// ps23 (rec13: every duel -hit line printed 'att blend 0 (cut)' = the REQUESTED blend, while the half really blended in over the floor, B [10908] / [11133]):
// the blend psync_animate really passed to animate_ on its last call, and the one our own / the puppet's attacker half of the running pair got (sptl_emit prints it).
static float g_ps_anim_bl = -1.0f, g_ps_att_bl_applied = -1.0f; static uint32_t g_ps_att_bl_uid;
#define MEL_HIT_BLEND 0.034f
static float mel_min_blend(float bl) {
    static int old = -1; static uint64_t at; uint64_t n = GetTickCount64();
    if (old < 0 || n - at > 3000) { at = n; old = GetFileAttributesA("t2r-melee-cuts-old.txt") != INVALID_FILE_ATTRIBUTES; }
    float fl = g_mel_floor_once >= 0.0f ? g_mel_floor_once : MEL_MIN_BLEND; g_mel_floor_once = -1.0f;
    return !old && bl < fl ? fl : bl;
}
static uint64_t psync_animate(uint64_t ent, uint64_t sid, const psync_bf *bf, float phase, float blend);
static void psync_hold_end_pose(uint64_t ent, uint64_t sid, float dur_s, const char *tag) {
    float ph = psync_phase(ent, sid);
    if (ph < 0.0f || ph >= 0.5f || dur_s <= 0.2f) return;
    float want = 1.0f - 0.1f / dur_s; if (want < 0.9f) want = 0.9f;
    uint64_t b[4] = {ent, 0, ANIM_LAYER, sid};
    memcpy(&b[1], &want, 4);
    uint64_t r = dc_call(fnv64("set-animation-phase"), 4, b);
    float rb = psync_phase(ent, sid);
    xlog("psync: %s - the frozen victim half read phase %.3f (a looping carrier wrapped to its start pose): set-animation-phase %.3f -> %llx, reads %.3f now",
         tag, ph, want, (unsigned long long)r, rb);
    // A:87615 etc: the write never stuck (reads 0.000 again). 0.000 is also what the engine answers when the half's LAYER IS GONE (the clip ran
    // out / the death removed it - "kick fix: clip ended" in the same frames), so there was no instance to write to and the body showed the base
    // (downed) pose. Make a fresh instance of the half on its end phase, freeze it, and read it back.
    if (rb >= 0.5f || ent != g_ps.ent_vic || ent == SID_PLAYER) return;
    psync_animate(ent, sid, &g_ps.bf_vic, want, 0.0f);
    float zero = 0.0f; uint64_t z[4] = {ent, 0, ANIM_LAYER, sid};
    memcpy(&z[1], &zero, 4);
    mo_rate_dc(z, MO_SRC("paired.hold_end_pose"));
    float rb2 = psync_phase(ent, sid);
    xlog("psync: %s - layer was gone: half re-applied on its end phase %.3f and frozen, reads %.3f now%s", tag, want, rb2,
         rb2 >= 0.5f ? "" : " (STILL not held)");
}
static float psync_dur(uint64_t ent, uint64_t sid) {
    uint64_t d2[2] = {ent, sid};
    uint64_t rd = dc_call(fnv64("get-animation-duration"), 2, d2);
    float dur = 0; uint32_t dl = (uint32_t)rd; memcpy(&dur, &dl, 4);
    return rd != ~0ULL && dur > 0.2f && dur < 30.0f ? dur : 0.0f;
}
// animate_(ent, clip, [blend-in 28, ap-ref 10 (a real BoundFrame), start-phase 58])
// blend < 0: the move's g_ps_blend; >= 0: that blend-in (psync_play passes 0 for a puppet's attacker half, see PS_PUP_CUT)
// the attacker puppet's base layer (L1, 81b46a69304ee2c9) holds the half's instance in every good start and is empty
// (n 0, fade 0) in a collapsed one. This logs the used layers of a puppet the same frame, before and right after animate_, so a
// collapsed start shows whether the instance was never made or was made and dropped later in the frame.
static void psync_layer_snap(const char *tag, uint64_t ent);
static void p30_start(void);        // melee_hitreact.c (ps30): an armed victim's duel -hit half - proof log of its layers + the arm hold's release, before the half's animate_
static uint64_t psync_animate(uint64_t ent, uint64_t sid, const psync_bf *bf, float phase, float blend) {
    int n = phase > 0.0005f ? 3 : 2;
    uint64_t aa[4] = {fnv64("single-frame"), 16, (uint64_t)n, 1};
    uint64_t arr = dc_call(fnv64("#%alloc-array"), 4, aa);
    if (!arr || arr == ~0ULL || IsBadReadPtr((void *)arr, 8)) return ~0ULL;
    uint64_t *tab = *(uint64_t **)arr;
    if (!tab || IsBadReadPtr(tab, 8 * (size_t)n)) return ~0ULL;
    for (int i = 0; i < n; i++) if (!tab[i] || alloc_entry_bad((void *)arr, (void *)tab[i], 16)) return ~0ULL;
    float bl = mel_min_blend(blend >= 0.0f ? blend : g_ps_blend);
    g_ps_anim_bl = bl;
    *(int32_t *)tab[0] = 28; *(uint64_t *)((uint8_t *)tab[0] + 8) = 0; memcpy((uint8_t *)tab[0] + 8, &bl, 4);
    *(int32_t *)tab[1] = 10; *(uint64_t *)((uint8_t *)tab[1] + 8) = (uint64_t)bf;
    if (n == 3) { *(int32_t *)tab[2] = 58; *(uint64_t *)((uint8_t *)tab[2] + 8) = 0; memcpy((uint8_t *)tab[2] + 8, &phase, 4); }
    uint64_t a[3] = {ent, sid, arr};
    uint64_t rp_ = dc_call(fnv64("animate_"), 3, a);
    fa_note(ent, NULL, sid, rp_, 2);
    return rp_;
}
static uint64_t psync_stop(uint64_t ent, uint64_t sid, float blend) {
    if (!ent || !sid) return 0;
    uint64_t a[5] = {ent, ANIM_LAYER, 0, sid, 0};
    blend = mel_min_blend(blend);                    // no instant clip ends either
    memcpy(&a[2], &blend, 4);
    uint64_t rs_ = dc_call(fnv64("stop-animating"), 5, a);
    fa_note(ent, NULL, sid, rs_, 3);
    return rs_;
}
static int psync_dead(uint64_t ent) {
    uint64_t h = ent;
    if (ent == SID_PLAYER) return 0;
    uint64_t d = dc_call(0xe93f704f02a9ecd5ULL /* character-is-dead? */, 1, &h);
    return d != ~0ULL && (d & 0xff);
}
// ---- quaternion bits for the smoothing (xyzw, as the locators)
static void ps_qnorm(float *q) {
    float n = __builtin_sqrtf(q[0] * q[0] + q[1] * q[1] + q[2] * q[2] + q[3] * q[3]);
    if (n < 1e-6f) { q[0] = q[1] = q[2] = 0.0f; q[3] = 1.0f; return; }
    for (int i = 0; i < 4; i++) q[i] /= n;
}
static void ps_qconj(const float *q, float *o) { o[0] = -q[0]; o[1] = -q[1]; o[2] = -q[2]; o[3] = q[3]; }
static void ps_qtoward_id(float *q, float f) {          // q = nlerp(identity, q, f), shortest way
    if (q[3] < 0.0f) for (int i = 0; i < 4; i++) q[i] = -q[i];
    for (int i = 0; i < 3; i++) q[i] *= f;
    q[3] = 1.0f - f + f * q[3];
    ps_qnorm(q);
}
static float ps_qangle(const float *q) {                // rotation angle (deg) of a unit quaternion
    float w = __builtin_fabsf(q[3]); if (w > 1.0f) w = 1.0f;
    return 2.0f * __builtin_acosf(w) * 57.29578f;
}
// ---- hand-back of a released puppet to winmm's net locator (the end of an execution snapped, more with ping).
// When a puppet left psync its net locator came back in one frame (and winmm's interpolation was reset with it, +0x77e4): the body
// jumped from where the clip left it to the latency-delayed net position. Now locator_hook asks psync_locator_handback for the first
// PS_HB_* s: the net locator plus the start offset (body - net at the first net frame), the offset faded to 0 with a smoothstep, so
// the body follows the net motion from the first frame (no lag) and lands exactly on it at the end of the window (no residual snap).
static struct {
    volatile uint64_t h;
    float from[8];                 // the body's locator at the release
    float off_p[3], off_q[4];      // body - net at the first net frame
    float win, d0, y0;             // window (s), start offset (m / deg)
    double armed, first;           // QPC ms
    int n;
    int hold;                      // (a recording): a pull-out victim's hand-back holds the clip's end placement until the net yaw matches (<= 0.5 s)
    char why[40];
} g_ps_hb[T2R_MAX_PEERS];
static const char *pul_pair_name(uint64_t move);     // ctxdown.c
static void psync_hb_arm(int s, uint64_t h, const char *why) {
    if (s < 0 || s > T2R_MAX_PEERS - 1 || !h) return;
    g_ps_hb[s].h = 0;
    if (!g_ps_smooth) return;
    if (dtl_hb_take(s, h, why)) return;    // v5-body: the duel partner's puppet glides onto the net position through the duel timeline's bounded spring instead (net jumps right after the release passed through this glide)
    float b[16];
    const float *l = psync_loc(h, b);
    if (!l || !ps_loc_ok(l)) { xlog("psync: slot %d hand-back not armed (%s): no locator", s, why); return; }
    memcpy(g_ps_hb[s].from, l, 32);
    g_ps_hb[s].n = 0; g_ps_hb[s].armed = psync_ms(); g_ps_hb[s].first = 0;
    g_ps_hb[s].d0 = g_ps_hb[s].y0 = g_ps_hb[s].win = 0.0f;
    // (a recording: log line 252439 "hand-back to the net locator done (contextual down hand-off): start offset 0.05 m / 90 deg" - after pu-fail the victim turned 90 deg on the
    // floor, sat up, got kicked and popped up): the victim half of a pull-out pair ends on its clip's facing, the net locator still carries the older yaw and the glide turned the
    // lying body over the whole window. Hold the clip's end placement until the net yaw is within 20 deg (cap 0.5 s), then glide as before. t2r-pullout-end-fix-off.txt = old.
    g_ps_hb[s].hold = g_ps.role && g_ps.kind == PS_CTXDOWN && g_ps.vic == s && pul_pair_name(g_ps.move) && GetFileAttributesA("t2r-pullout-end-fix-off.txt") == INVALID_FILE_ATTRIBUTES;
    snprintf(g_ps_hb[s].why, sizeof g_ps_hb[s].why, "%s", why);
    g_ps_hb[s].h = h;
}
static void psync_hb_end(int s, const char *how) {
    if (!g_ps_hb[s].h) return;
    xlog("psync: slot %d hand-back to the net locator %s (%s): start offset %.2f m / %.0f deg, window %.2f s, %d frames, %.0f ms after the release",
         s, how, g_ps_hb[s].why, g_ps_hb[s].d0, g_ps_hb[s].y0, g_ps_hb[s].win, g_ps_hb[s].n, psync_ms() - g_ps_hb[s].armed);
    g_ps_hb[s].h = 0;
}
// locator_hook (winmm's net locator for puppet h): 1 = we set the blended locator ourselves
static int psync_locator_handback(uint64_t h, void *loc) {
    if (!h) return 0;
    int s = -1;
    for (int i = 0; i < T2R_MAX_PEERS; i++) if (g_ps_hb[i].h == h) { s = i; break; }
    if (s < 0) return 0;
    if (!g_ps_smooth) { psync_hb_end(s, "off (t2r-psync-no-smooth.txt)"); return 0; }
    const psync_bf *nb = (const psync_bf *)loc;
    if (!nb || IsBadReadPtr(nb, sizeof *nb) || nb->magic[0] != 0x7fccccccu || nb->binding) { psync_hb_end(s, "skipped - net locator not an unbound BoundFrame"); return 0; }
    float net[8];
    memcpy(net, nb->local, 32); net[3] = 1.0f;
    if (!ps_loc_ok(net)) { psync_hb_end(s, "skipped - bad net locator"); return 0; }
    if (psync_dead(h)) { psync_hb_end(s, "ended - the body is dead (death / ragdoll own it)"); return 0; }
    double now = psync_ms();
    float *f = g_ps_hb[s].from;
    if (g_ps_hb[s].hold && !g_ps_hb[s].n) {
        float nc2[4], dq[4], ang = 0.0f;
        ps_qconj(net + 4, nc2); ps_qmul(f + 4, nc2, dq); ps_qnorm(dq); ang = ps_qangle(dq);
        if (now - g_ps_hb[s].armed < 500.0 && ang > 20.0f) {
            float hl[8]; memcpy(hl, f, 32); hl[3] = 1.0f;
            static psync_bf hbf; psync_bf_from_loc(&hbf, hl);
            mo_write(h, &hbf, MO_SRC("paired.handback_hold"), 0);
            static int nlh; if (LOGCAP(nlh, 60) && now - g_ps_hb[s].armed < 40.0) xlog("psync: slot %d pull-out victim hand-back: the net yaw is %.0f deg off the clip's end facing - the body holds the clip's placement (<= 500 ms; t2r-pullout-end-fix-off.txt = old glide)", s, ang);
            return 1;
        }
        static int nld; if (LOGCAP(nld, 60)) xlog("psync: slot %d pull-out victim hand-back: hold over after %.0f ms (net yaw %.0f deg off) - the glide starts", s, now - g_ps_hb[s].armed, ang);
        g_ps_hb[s].hold = 0;
    }
    if (!g_ps_hb[s].n) {
        float dx = f[0] - net[0], dy = f[1] - net[1], dz = f[2] - net[2], d = __builtin_sqrtf(dx * dx + dy * dy + dz * dz);
        float nc[4];
        ps_qconj(net + 4, nc);
        ps_qmul(f + 4, nc, g_ps_hb[s].off_q);   // from.q = off_q * net.q
        ps_qnorm(g_ps_hb[s].off_q);
        g_ps_hb[s].off_p[0] = dx; g_ps_hb[s].off_p[1] = dy; g_ps_hb[s].off_p[2] = dz;
        g_ps_hb[s].d0 = d; g_ps_hb[s].y0 = ps_qangle(g_ps_hb[s].off_q);
        g_ps_hb[s].first = now;
        float w = PS_HB_MIN + PS_HB_PER_M * d;
        g_ps_hb[s].win = w > PS_HB_MAX ? PS_HB_MAX : w;
        if (d > PS_HB_SNAP_M) { g_ps_hb[s].n = 1; psync_hb_end(s, "skipped - offset too large (respawn / teleport), net taken as is"); return 0; }
        if (d < 0.01f && g_ps_hb[s].y0 < 0.5f) { g_ps_hb[s].n = 1; psync_hb_end(s, "not needed - already on the net locator"); return 0; }
    }
    g_ps_hb[s].n++;
    float u = (float)((now - g_ps_hb[s].first) / (g_ps_hb[s].win * 1000.0));
    if (u >= 1.0f) { psync_hb_end(s, "done"); return 0; }
    if (u < 0.0f) u = 0.0f;
    float k = 1.0f - u * u * (3.0f - 2.0f * u);          // offset weight: 1 -> 0, smoothstep
    float o[8], q[4];
    for (int i = 0; i < 3; i++) o[i] = net[i] + g_ps_hb[s].off_p[i] * k;
    o[3] = 1.0f;
    memcpy(q, g_ps_hb[s].off_q, 16);
    ps_qtoward_id(q, k);
    ps_qmul(q, net + 4, o + 4);
    ps_qnorm(o + 4);
    if (!ps_loc_ok(o)) { psync_hb_end(s, "aborted - non-finite blend"); return 0; }
    static psync_bf bf;
    psync_bf_from_loc(&bf, o);
    mo_write(h, &bf, MO_SRC("paired.handback"), 0);
    return 1;
}

// ---- puppet channel suspension (winmm: 0x180035bac gate -> net locator 0x180035ddf + pose writer 0x1800297b0;
// AnimCmdList replay 0x180026ff0; root-transform write 0x180026d60)
static void psync_pup_cache(int s) {
    typedef uint8_t *(*fn_proc)(uint64_t);
    uint64_t h = g_ps_pup[s].h;
    uint8_t *proc = h ? ((fn_proc)VMA(0x18000A200))(h) : NULL;
    g_ps_pup[s].proc = proc;
    g_ps_pup[s].ac = proc && !IsBadReadPtr(proc + 0x1b8, 8) ? *(uint8_t **)(proc + 0x1b8) : NULL;
}
// 2013: a reviver can be hit (and the hit interrupts the revive). The reviver's puppet keeps its character collider on for the revive move - the
// engine's melee contact test only finds a body through that capsule (the collider-off puppet let every swing through). Shots use the per-joint
// hit bodies and never needed it. The revived (lying) half stays as for every paired move.
static int psync_reviver_pup(int s) { return s >= 0 && s < T2R_MAX_PEERS && g_ps.role && g_ps.kind == PS_REVIVE && g_ps.att == s; }
// The executioner can be meleed (2013: the executioner is a normal, hittable standing body - only the downed victim is
// untouchable): the EXECUTIONER half of a gun / melee special execution keeps its character collider on exactly like a reviver's (the engine's melee
// contact test finds a body only through that capsule) and is not excluded from the melee target pick (mcam_body_filter). The victim stays untouchable.
// (a report: a teammate could not be saved from a stealth kill by punching the attacker): 2013 has no invulnerable attacker - hitting the attacker of ANY
// paired takedown frees the victim. The attacker half of a contextual down / finisher / tackle / pull-out (not a duel -hit pair or a dodge counter: the duel has its own
// third-party rule, mdu_note_hit) is now as hittable as an executioner's; the victim keeps every protection. t2r-no-pair-hit-break.txt next to the exe = old (executions only).
static int dc_is_counter(uint64_t move);       // dcounter.c
static int ps_hitatt_kind(void) {
    static int off = -1;
    if (g_ps.kind == PS_GUN_EXEC || g_ps.kind == PS_MELEE_EXEC) return 1;
    if (off < 0) { FILE *f = exe_side_open("t2r-no-pair-hit-break.txt", "r"); off = f != NULL; if (f) fclose(f); }
    if (off) return 0;
    if (g_ps.kind == PS_FINISHER || g_ps.kind == PS_TACKLE) return 1;
    return g_ps.kind == PS_CTXDOWN && !mdu_move(g_ps.move) && !dc_is_counter(g_ps.move);
}
static int psync_exec_att_pup(int s) { return s >= 0 && s < T2R_MAX_PEERS && g_ps.role && !g_ps.ended && ps_hitatt_kind() && g_ps.att == s; }
static int psync_exec_att_slot(uint32_t sl) { return psync_exec_att_pup((int)sl) && psync_busy_slot(sl); }
// The executioner takes damage during a special execution: OUR body is the executioner half of a running gun / melee execution - a standing, fully hittable body
// (own_inv_clear / recv_hit_hook swallow check / gunexec_tick abort use it; the VICTIM half - role 2 - keeps every protection)
static int psync_exec_att_own(void) { return g_ps.role == 1 && !g_ps.ended && ps_hitatt_kind(); }
static void psync_pup_take(int s, uint64_t h, const char *why) {
    if (s < 0 || s > T2R_MAX_PEERS - 1 || !h) return;
    if (g_ps_pup[s].corpse) xlog("psync: slot %d corpse hold ended (%s takes the puppet)", s, why);
    g_ps_pup[s].corpse = 0;
    if (g_ps_pup[s].on && g_ps_pup[s].h == h) return;
    g_ps_pup[s].h = h; g_ps_pup[s].rep = g_ps_pup[s].root = g_ps_pup[s].gate = g_ps_pup[s].loc = g_ps_pup[s].drv = 0; g_ps_pup[s].early = 0;
    g_ps_hb[s].h = 0;                                            // a hand-back still running from the previous move: the half owns it now
    dtl_loc_reset(s);                                            // (duel timeline: its displayed-locator filter restarts from the body when the puppet is handed back)
    g_ps_pup[s].since = psync_ms();
    psync_pup_cache(s);
    if (g_uc4_pup[s].cur) uc4_stop(&g_uc4_pup[s]);                 // no downed / crawl loop over the half
    anim_end_blend(h, g_down_loop, 0.2f);
    int hittable = psync_reviver_pup(s) || psync_exec_att_pup(s);
    uint64_t a = h, r1 = dc_call(fnv64(hittable ? "npc-enable-character-collider" : "npc-disable-character-collider"), 1, &a);
    uint64_t a2[2] = {h, 0}, r2 = dc_call(fnv64("npc-enable-hit-reactions"), 2, a2);
    g_ps_pup[s].coll_off = !hittable; g_ps_pup[s].hr_off = 1;
    if (hittable) xlog("psync: slot %d is the %s - its character collider stays ON (a hit on it lands%s)", s, psync_exec_att_pup(s) ? "executioner" : "reviver",
                       psync_exec_att_pup(s) ? "; a down breaks the execution (gx_abort 'we were downed' on its side)" : " and cancels the revive");
    g_ps_pup[s].on = !g_ps_no_suspend;
    xlog("psync: slot %d puppet %llx taken (%s): net channels %s, collider off -> %llx, hit reactions off -> %llx, proc %p ac %p",
         s, (unsigned long long)h, why, g_ps_no_suspend ? "LEFT ON (t2r-psync-no-suspend.txt)" : "suspended", (unsigned long long)r1,
         (unsigned long long)r2, (void *)g_ps_pup[s].proc, (void *)g_ps_pup[s].ac);
}
static void psync_pup_release(int s, const char *why, int blend_out);
static float ps_out_blend(void);
static int dc_is_counter(uint64_t move);       // dcounter.c: a dodge counter pair
static int g_ps_corpse_keep40;     // (ps40 D1, see its second declaration below)
static int g_ps_corpse_force;      // psync_release_victim_pup: the held lethal hp is applied right after - a corpse even if it still reads alive
static void psync_release_victim_pup(const char *why) {
    g_ps_corpse_force = 1;
    if (g_ps.role == 1 && g_ps.vic >= 0 && g_ps.vic < T2R_MAX_PEERS && g_ps_pup[g_ps.vic].h) psync_pup_release(g_ps.vic, why, 0);
    g_ps_corpse_force = 0;
}
static void psync_pup_release(int s, const char *why, int blend_out) {
    if (s < 0 || s > T2R_MAX_PEERS - 1 || !g_ps_pup[s].h) return;
    uint64_t h = g_ps_pup[s].h;
    int same = psync_puppet(s) == h, dead = same && psync_dead(h);
    // the dead victim of a lethal move: no hand-back to the network. Handing its replay / pose writer back (replay reset +0x77e4) put
    // the remote's base pose on the corpse for the frames before the ragdoll / death pose took it - the body stood up and dropped
    // (hunting rifle). Its half stays frozen on the final pose (psync_vic_end_hold) and the channels stay suspended until
    // the puppet respawns / lives again (psync_corpse_tick). t2r-no-corpse-hold.txt = the old hand-back.
    if (g_ps_pup[s].corpse && same && !blend_out) return;        // already held (exhold released it before the move's end): stays held
    if (g_ps_pup[s].corpse && same && g_ps_corpse_keep40 && s == g_ps.vic) return;   // ps40 D1: a killing finisher row's dead victim stays in its corpse hold through the hand-off's abort
    int killed = dead || g_ps_corpse_force || (g_ps.kill_s > 0 && psync_ms() - g_ps.t0 >= g_ps.kill_s * 1000.0);   // its owner killed it at the kill time
    if (same && killed && !blend_out && !g_ps_no_corpse && !g_ps_pup[s].corpse && g_ps.role && g_ps.ent_vic == h && (g_ps.flags & PS_F_LETHAL)) {
        float zero = 0.0f;
        uint64_t b[4] = {h, 0, ANIM_LAYER, g_ps.vic_sid};
        memcpy(&b[1], &zero, 4);
        uint64_t r = mo_rate_dc(b, MO_SRC("paired.pup_release"));
        g_ps_pup[s].corpse = 1; g_ps_pup[s].corpse_ms = psync_ms(); g_ps_pup[s].corpse_sid = g_ps.vic_sid;
        psync_hold_end_pose(h, g_ps.vic_sid, g_ps.vic_dur, "corpse hold");
        g_ps_pup[s].on = 1;
        xlog("psync: slot %d dead victim puppet - corpse hold (%s): net channels stay suspended, half %s frozen at phase %.3f (-> %llx), "
             "until it respawns; placed on the clip %ld frames", s, why, psync_name(g_ps.vic_sid), psync_phase(h, g_ps.vic_sid),
             (unsigned long long)r, (long)g_ps_pup[s].drv);
        return;
    }
    g_ps_pup[s].corpse = 0;
    if (same && !dead) {
        // the attacker's half always ends with the move: a clip that holds its last pose keeps the layer on, and the baked clips'
        // hand-prop joints sit at bind pose, so the gun floated off the hand once the aim pose came back. The victim
        // half is left lying (it ended by itself / the death takes over) unless the move was aborted.
        // (smoothing: an attacker half handed back early already fades out - stopping it again would restart the fade)
        if (g_ps.ent_att == h && !g_ps_pup[s].early) psync_stop(h, g_ps.att_sid, ps_out_blend());
        if ((blend_out || g_ps.out_done[1]) && g_ps.ent_vic == h) psync_stop(h, g_ps.vic_sid, ps_out_blend());   // (out_done[1]: frozen by psync_vic_end_hold - it lives)
    }
    int early = g_ps_pup[s].early;
    g_ps_pup[s].on = 0;
    // winmm's replay restarts cleanly: no interpolation from the pose before the move (flags +0x77e4, 0x1800277c0). Not twice: a
    // puppet handed back early is already on the net replay, a second reset now would pop its pose again.
    if (!early && s < T2R_ENGINE_PEERS) InterlockedOr((volatile LONG *)(PA_SLOT(s) + 0x77e4), 3);
    if (!early && same && !dead) psync_hb_arm(s, h, why);        // its locator glides onto the net position (psync_locator_handback)
    uint64_t z = 0, r1 = ~0ULL, r2;
    if (same && !dead && !g_peer_downed[s]) { uint64_t a = h; r1 = dc_call(fnv64("npc-enable-character-collider"), 1, &a); }
    if (same && !dead && !g_peer_downed[s]) { uint64_t a2[2] = {h, 1}; dc_call(fnv64("npc-enable-hit-reactions"), 2, a2); }
    r2 = dc_call(fnv64("player-ignore-object-collision"), 1, &z);
    xlog("psync: slot %d puppet released (%s, %s%s%s) after %.0f ms: replay bypassed %ld, root write bypassed %ld, pose/locator gate %ld, "
         "net locator skipped %ld, placed on the clip %ld; collider -> %llx, player ignore cleared -> %llx", s, why, same ? (dead ? "dead" : "alive") : "puppet gone",
         g_peer_downed[s] ? ", downed (collider left to the downed hitbox)" : "", early ? ", on the net since its half's blend-out" : "", psync_ms() - g_ps_pup[s].since,
         (long)g_ps_pup[s].rep, (long)g_ps_pup[s].root, (long)g_ps_pup[s].gate, (long)g_ps_pup[s].loc, (long)g_ps_pup[s].drv,
         (unsigned long long)r1, (unsigned long long)r2);
    g_ps_pup[s].h = 0; g_ps_pup[s].proc = NULL; g_ps_pup[s].ac = NULL;
}
static int psync_busy_slot(uint32_t slot) { return slot < T2R_MAX_PEERS && g_ps.role && g_ps_pup[slot].h != 0; }
static int psync_active(void) { return g_ps.role != 0; }
// ps51: the victim half of a pair we only watch (role 3) - its standing capsule stays off (downed hitbox code must not turn it back on), so a
// bystander's shots at the executioner are not stopped by the downed victim's body. t2r-bystander-victim-ps51-old.txt = the old rule.
static int psync51_bystander_victim(uint32_t slot) {
    static int off = -1; static uint64_t at;
    uint64_t now = GetTickCount64();
    if (off < 0 || now - at > 2000) { at = now; FILE *f = exe_side_open("t2r-bystander-victim-ps51-old.txt", "r"); int v = f != NULL; if (f) fclose(f);
        if (v != off) xlog("psync: ps51 bystander victim capsule %s", v ? "OLD (t2r-bystander-victim-ps51-old.txt): back on during the move" : "stays OFF during someone else's execution");
        off = v; }
    if (off || g_ps.role != 3 || (int)slot != g_ps.vic) return 0;
    static double logged; if (logged != (double)g_ps.t0) { logged = (double)g_ps.t0; xlog("psync: ps51 slot %u is the victim of a pair we watch - its capsule stays off, shots at the executioner pass it", slot); }
    return 1;
}
// our own body is a half of the running paired move (attacker 1 / victim 2). psync_active() is also true for a bystander (role 3: two OTHER players'
// pair) - seen live (7 players): every dodge press during someone else's execution was refused as "paired move".
static int psync_own(void) { return g_ps.role == 1 || g_ps.role == 2; }
static int psync_kind_now(void) { return g_ps.role ? g_ps.kind : 0; }
static int psync_role(void) { return g_ps.role; }
// ms left of the victim half on our body (we are the victim of a running paired move), -1 = none
static int psync_vic_left_ms(void) { if (g_ps.role != 2 || g_ps.vic_dur <= 0.0f) return -1; double l = (g_ps.vic_dur + g_ps.vlag) * 1000.0 - (psync_ms() - g_ps.t0); return l > 0.0 ? (int)l : 0; }
static int g_ps_vic_slot(void) { return g_ps.role ? g_ps.vic : -1; }
static int g_ps_kind(void) { return g_ps.kind; }
static int psync_exec_attacker(void) { return psync_exec_att_own(); }      // (every hittable attacker half, see ps_hitatt_kind)
static int psync_ctx_window(int *att, int *vic) {      // ctx shield: a contextual takedown pair runs (role 1 / 2 / 3), its two slots
    if (!g_ps.role || g_ps.kind != PS_CTXDOWN || g_ps.ended) return 0;
    if (att) *att = g_ps.att;
    if (vic) *vic = g_ps.vic;
    return g_ps.role;
}
// our body plays one half of a 2013 paired move (executions, shiv kills, finishers, tackles, revives - every kind but ctxdown, whose
// takedowns are TLOU2 SP ellie-knife clips that keep the knife in the hand): fem_exec_body() turns the female knife IsEllie off for it
static int psync_body_2013(void) { return (g_ps.role == 1 || g_ps.role == 2) && g_ps.kind != PS_CTXDOWN; }
// Hit marker gate (shooting an enemy who executes a teammate showed no marker - the old gate dropped every tick while ANY paired move ran).
// Dropped only when the tick belongs to the move's own gore shots: we are in it (role 1 / 2), or we only watch it (role 3) and the tick's target
// is the move's victim. A tick on anyone else - the executor above all - is a real shot of ours and shows (also the down / kill tick).
static int psync_hit_tick_ok(uint64_t i0, uint64_t i1) {
    if (!g_ps.role) return 1;
    if (g_ps.kind == PS_BODYSHIELD) return 1;   // (a body shield has no gore shots: the shielder's own shots, and the victim's team hitting the shield, are real hits)
    if (g_ps.role != 3) return 0;
    if (g_ps.ent_vic && g_ps.ent_vic != SID_PLAYER && (i0 == g_ps.ent_vic || i1 == g_ps.ent_vic)) return 0;
    return 1;
}
static void psync_vic_throat_set(int on) { g_ps.vic_throat = (uint8_t)on; }
static int psync_ap(float *ap7) { if (!g_ps.role) return 0; memcpy(ap7, g_ps.ap, 7 * sizeof(float)); return 1; }   // the exec camera's track space
static double psync_ms(void);
static int msq_move(uint64_t move);       // melee_seq.c: a melee sequence pair (ctxdown.c kind 6 row)
// (the lock-on stayed on the body 3-4 s after the execution - the victim half (longer) still ran. Only while OUR half
// plays: the executed body's death is held (peer_dead_hook / set_hp_hook) until then)
static int psync_attacked_slot(void) {
    if (g_ps.role != 1) return -1;
    if (g_ps.att_dur > 0 && psync_ms() - g_ps.t0 > g_ps.att_dur * 1000.0) return -1;
    return g_ps.vic;
}
// the executed body's lethal hp is held until BOTH halves are over (set_hp_hook / exhold_tick): the kick pairs' victim half runs up to
// 1.3 s longer than ours, and a death applied at the end of OUR half ragdolled the body mid-clip, so it stopped on its path (victim root)
static int psync_exec_hold_slot(void) {
    if (g_ps.role != 1) return -1;
    float d = g_ps.att_dur > g_ps.vic_dur ? g_ps.att_dur : g_ps.vic_dur;
    if (d > 0 && psync_ms() - g_ps.t0 > d * 1000.0) return -1;
    return g_ps.vic;
}
// shiv kills (t2r-ext.c g_exk): the victim slot whose puppet kill is held on this screen - we attack (1) or watch (3) a 2013 shiv kill
// and its halves still play. -1 = none / over (exkill_tick kills the puppet then, no death anim, from the half's final pose).
static int mx_is_kill_defer_move(uint64_t move);
static int psync_kill_defer_slot(void) {
    if ((g_ps.role != 1 && g_ps.role != 3) || !(g_ps.flags & PS_F_LETHAL) || g_ps.kind != PS_MELEE_EXEC) return -1;
    if (g_ps.vic < 0 || g_ps.vic > T2R_MAX_PEERS - 1 || !g_ps.ent_vic || g_ps.ent_vic == SID_PLAYER || !mx_is_kill_defer_move(g_ps.move)) return -1;
    float d = g_ps.att_dur > g_ps.vic_dur ? g_ps.att_dur : g_ps.vic_dur;
    if (d <= 0.0f || psync_ms() - g_ps.t0 >= d * 1000.0) return -1;
    return g_ps.vic;
}
// the health component (character +0x610) of the body psync_exec_hold_slot() names: the only one set_hp_hook may hold. Any other body
// whose hp goes 0 meanwhile (a dead peer's puppet torn down at its respawn: crash 2, slot 0 respawned 90 frames into our
// execution of slot 2) is none of the execution's business - holding it kept a pointer to freed memory for the later apply.
static int psync_is_exec_victim_comp(const uint8_t *comp) {
    int s = psync_exec_hold_slot();
    if (s < 0 || s > T2R_MAX_PEERS - 1 || !comp || !g_ps_pup[s].h) return 0;
    uint8_t *proc = ((uint8_t *(*)(uint64_t))VMA(0x18000A200))(g_ps_pup[s].h);
    return proc && !IsBadReadPtr(proc + 0x610, 8) && *(uint8_t **)(proc + 0x610) == comp;
}
static int psync_skip_frames(void) { return g_ps.role >= 2 ? (int)(g_ps.skip_ms * 0.06f + 0.5f) : 0; }
static int psync_gate_slot(int32_t slot) {
    if (slot < 0 || slot > T2R_MAX_PEERS - 1 || !g_ps_pup[slot].on) return 0;
    InterlockedIncrement(&g_ps_pup[slot].gate);
    return 1;
}
static int psync_locator_skip(uint64_t h) {
    for (int s = 0; s < T2R_MAX_PEERS; s++)
        if (g_ps_pup[s].on && g_ps_pup[s].h == h) { InterlockedIncrement(&g_ps_pup[s].loc); return 1; }
    return 0;
}
typedef uint64_t (*fn_ps_replay)(uint64_t, uint64_t, uint64_t);
typedef uint64_t (*fn_ps_root)(uint64_t);
typedef int (*fn_ps_mtx)(void *);
// winmm calls the saved originals under its own recursive mutex (MSVC _Mtx_lock 0x180072de8 / _Mtx_unlock 0x180072e10;
// replay hook: mutex 0x18013b180, original 0x18013b150 (+8 nonzero = hooked); root hook: 0x18013b240 / 0x18013b210):
// the bypass does exactly the same, so the original runs as it does for every non-puppet character
static uint64_t psync_call_orig(uint64_t mtx_va, uint64_t fn_va, int nargs, uint64_t a1, uint64_t a2, uint64_t a3, int *done) {
    uint64_t fn = *(volatile uint64_t *)VMA(fn_va);
    if (!fn || !*(volatile uint64_t *)VMA(fn_va + 8)) return 0;
    void *mtx = (void *)VMA(mtx_va);
    if (((fn_ps_mtx)VMA(0x180072DE8))(mtx) != 0) return 0;
    uint64_t r = nargs == 3 ? ((fn_ps_replay)fn)(a1, a2, a3) : ((fn_ps_root)fn)(a1);
    ((fn_ps_mtx)VMA(0x180072E10))(mtx);
    *done = 1;
    return r;
}
static uint64_t psync_replay_bypass(uint64_t ac, uint64_t a2, uint64_t a3, int *done) {
    *done = 0;
    if (!ac) return 0;
    int hit = -1;
    for (int s = 0; s < T2R_MAX_PEERS && hit < 0; s++) if (g_ps_pup[s].on && (uint64_t)g_ps_pup[s].ac == ac) hit = s;
    if (hit < 0) {                  // the engine moved the puppet (heap compaction): resolve again
        typedef uint8_t *(*fn_proc)(uint64_t);
        for (int s = 0; s < T2R_MAX_PEERS && hit < 0; s++) {
            if (!g_ps_pup[s].on || !g_ps_pup[s].h) continue;
            uint8_t *proc = ((fn_proc)VMA(0x18000A200))(g_ps_pup[s].h);
            if (pa_ptr_ok((uint64_t)proc, 0xfe48) && *(uint64_t *)(proc + 0x1b8) == ac) { g_ps_pup[s].proc = proc; g_ps_pup[s].ac = (uint8_t *)ac; hit = s; }
        }
    }
    if (hit < 0) return 0;
    // the puppet's own graph (our animate_ half), not winmm's replay of the network AnimCmdList
    uint64_t r = psync_call_orig(0x18013B180, 0x18013B150, 3, ac, a2, a3, done);
    if (*done) InterlockedIncrement(&g_ps_pup[hit].rep);
    return r;
}
static uint64_t psync_root_bypass(uint64_t proc, uint64_t a2, uint64_t a3, uint64_t a4, int *done) {
    (void)a2; (void)a3; (void)a4;
    *done = 0;
    int hit = -1;
    for (int s = 0; s < T2R_MAX_PEERS && hit < 0; s++) if (g_ps_pup[s].on && (uint64_t)g_ps_pup[s].proc == proc) hit = s;
    if (hit < 0) {                  // the engine moved the puppet (heap compaction) - the stale proc missed here, winmm wrote the
        // victim's NETWORK root for that frame and the executed body rotated into the ground for a frame. Resolve again by handle (as the replay bypass does).
        typedef uint8_t *(*fn_proc)(uint64_t);
        for (int s = 0; s < T2R_MAX_PEERS && hit < 0; s++) {
            if (!g_ps_pup[s].on || !g_ps_pup[s].h) continue;
            uint8_t *pr = ((fn_proc)VMA(0x18000A200))(g_ps_pup[s].h);
            if ((uint64_t)pr == proc && pa_ptr_ok(proc, 0xfe48)) { g_ps_pup[s].proc = pr; g_ps_pup[s].ac = *(uint8_t **)(pr + 0x1b8); hit = s; }
        }
    }
    if (hit < 0) return 0;
    uint64_t r = psync_call_orig(0x18013B240, 0x18013B210, 1, proc, 0, 0, done);   // without winmm's msg 5 root write after it
    if (*done) InterlockedIncrement(&g_ps_pup[hit].root);
    return r;
}

// ---- ap
// each half's align at phase 0 for an identity ap = C (the clip's authored offset from its apReference)
static int psync_offset(uint64_t ent, uint64_t sid, float *c) {
    static const float id7[7] = {0, 0, 0, 0, 0, 0, 1};
    psync_bf bf;
    psync_bf_make(&bf, id7);
    return psync_expected(ent, sid, &bf, 0.0f, c);
}
// solve the ap so the half `sid` (played on `ent`) starts with its align ON `anchor` (8-float world locator):
// ap = anchor o inv(C), yaw only (upright), C from the clip itself. 0 = the clip has no readable align / ap channels.
static int psync_solve_ap(uint64_t ent, uint64_t sid, const float *anchor, float *ap7) {
    float c[8], ic[8], r[8];
    if (!ps_loc_ok(anchor) || !psync_offset(ent, sid, c)) return 0;
    float yc = uc4_yaw(c) * 0.0174533f, ya = uc4_yaw(anchor) * 0.0174533f;
    float cu[8] = {c[0], c[1], c[2], 1.0f, 0, __builtin_sinf(yc * 0.5f), 0, __builtin_cosf(yc * 0.5f)};
    float au[8] = {anchor[0], anchor[1], anchor[2], 1.0f, 0, __builtin_sinf(ya * 0.5f), 0, __builtin_cosf(ya * 0.5f)};
    ps_inverse(cu, ic);
    ps_compose(au, ic, r);
    ps_ap7(r, ap7);
    xlog("psync: ap solved on the anchor %.2f %.2f %.2f yaw %.0f for %s (its align at phase 0: %.2f %.2f %.2f yaw %.0f) -> ap %.2f %.2f %.2f yaw %.0f",
         anchor[0], anchor[1], anchor[2], uc4_yaw(anchor), psync_name(sid), c[0], c[1], c[2], uc4_yaw(c), ap7[0], ap7[1], ap7[2], uc4_yaw(r));
    return 1;
}
// a locator within 5 cm / 3 deg of identity
static int ps_near_identity(const float *c) {
    float yw = uc4_yaw(c);
    return c[0] * c[0] + c[1] * c[1] + c[2] * c[2] < 0.05f * 0.05f && yw > -3.0f && yw < 3.0f;
}
// the per-half BoundFrames: the shared ap, or (frozen carrier channels) ap o inv(C) so the half's align is ON the ap
static void psync_bfs(void) {
    float a8[8];
    ps_ap8(g_ps.ap, a8);
    g_ps.c_att_ok = psync_offset(g_ps.ent_att, g_ps.att_sid, g_ps.c_att);
    g_ps.c_vic_ok = psync_offset(g_ps.ent_vic, g_ps.vic_sid, g_ps.c_vic);
    // The gun / 2013 melee pairs are TLOU1 clips baked onto carrier clips. Current paks rewrite the carrier's align /
    // apReference channels with the pair's 2013 tracks, re-based so the VICTIM's align at phase 0 is exactly the ap: then C
    // is the authored offset (attacker ~1 m off, the root motion follows) and is kept, as for TLOU2's own pairs. Paks built
    // before that (re/paired-sync.md 9) left the carrier's frozen frame-0 channels in both halves (C = the search clip's
    // offset, the same in both): cancel C there so align == ap, as before. Told apart by the victim's C.
    int frozen = g_ps.kind == PS_GUN_EXEC && !(g_ps.c_vic_ok && ps_near_identity(g_ps.c_vic));
    for (int k = 0; k < 2; k++) {
        float *c = k ? g_ps.c_vic : g_ps.c_att;
        int ok = k ? g_ps.c_vic_ok : g_ps.c_att_ok;
        psync_bf *bf = k ? &g_ps.bf_vic : &g_ps.bf_att;
        float o[8], ap7[7];
        if (frozen && ok) {
            float ic[8];
            ps_inverse(c, ic);
            ps_compose(a8, ic, o);
            ps_ap7(o, ap7);
            psync_bf_make(bf, ap7);
        } else psync_bf_make(bf, g_ps.ap);
        if (ok) xlog("psync: %s half %s: authored align at phase 0 = %.2f %.2f %.2f yaw %.0f from its apReference%s",
                     k ? "victim" : "attacker", psync_name(k ? g_ps.vic_sid : g_ps.att_sid), c[0], c[1], c[2], uc4_yaw(c),
                     frozen ? " (frozen carrier channels: cancelled, align = ap)" : " (kept: the pair's authored offset)");
        else xlog("psync: %s half %s: no align / apReference channel readable - the engine aligns its align to the ap as is",
                  k ? "victim" : "attacker", psync_name(k ? g_ps.vic_sid : g_ps.att_sid));
    }
}

static int psync_own_vic_needs_drive(void);
static int psync_own_dead_now(void);
static void psync_wall_guard(float *t, int armed);
static uint64_t world_ray_kick(const float *a, const float *b);
static float ray_t(uint64_t job);
// ---- where the clip puts each body (re/paired-sync.md 10)
// The engine places a body playing a half with an ap-ref at  bf o inv(apReference(phase))  - a test: the
// player's locator matched inv(apReference(t)) of the baked track to 0.01 m / 1 deg the whole move. The engine's own
// get-channel-locator-from-ap-ref(.., align, apReference) is bf o inv(apReference(t)) o align(t): it adds the align (root
// motion) a SECOND time, so it is only the placement at phase 0 (align(0) = identity). With the clips' convention
// align(t) o apReference(t) = apReference(0) (our bake by construction, most TLOU2 pairs):
//   inv(apReference(t)) = C0 o align(t)   and   E(t) = C0 o align(t) o align(t),   C0 = E(0)
// so the placement is C0 o sqrt(inv(C0) o E(t)). The square root is taken upright (yaw + translation, the tracks are
// upright): yaw/2 or yaw/2 + 180, whichever continues the previous frame's (unwrapped from phase 0 on the first call, so a
// receiver that starts mid-clip picks the same branch), then (I + R) p = t solved in x/z, y halved.
// pulfix (from the grabber's POV the grabbed stayed under the truck for a second too long between 2 anims; B [12477]-[12537] 'vic ... exp n/a',
// drive frozen at 118 for 1.1 s, then the success pair pulled the puppet 1.19 m): the pull-out drag's victim half ROLLS OVER - its root turns 180 deg (yaw
// -180 -> 0 at phase 0.6). A o A then turns 360 deg and (I + R) is singular: the translation of the half is lost (det -> 0, 'a half turn per step'), the
// placement failed for the rest of the clip and both the puppet (B) and our own driven victim body (A) stood still at -0.35 m in ap space while the clip
// carried it to +0.86 m. Near that singularity the root is read from the BAKED own-align track of the same clip (pullout_cam_tracks.h 'own', ap space,
// t = clip seconds), offset so it continues the last good placement; the yaw keeps the half-yaw branch (it is exact there). t2r-ps-baked-root-off.txt = old.
static const char *pul_pair_name(uint64_t move);     // ctxdown.c: the CD_PAIRS name of a pull-out pair (kind 8), NULL otherwise
// 'who' (T2R_US = our own body, else a slot) is the victim of the pull-out pair running here now (t2r-ext.c pul_end_recent: the down that arrives INSIDE the pair).
static int psync_pul_vic_now(int who) {
    if (!g_ps.role || g_ps.kind != PS_CTXDOWN || !pul_pair_name(g_ps.move)) return 0;
    return who == T2R_US ? g_ps.role == 2 : g_ps.role != 2 && g_ps.vic == who;
}
static struct { uint32_t uid; int seg, ok, sing, n; float off[3]; } g_ps_bk;
static int psync_baked_root(int k, float ph, float *p3) {
#ifdef XCAM_HAVE_PUL
    static int v = -1; static uint64_t at; uint64_t now = GetTickCount64();
    if (v < 0 || now - at > 2000) { at = now; v = GetFileAttributesA("t2r-ps-baked-root-off.txt") == INVALID_FILE_ATTRIBUTES; }
    if (!v || k != 1 || g_ps.kind != PS_CTXDOWN) return 0;
    const char *pn = pul_pair_name(g_ps.move); if (!pn) return 0;
    char nm[48]; snprintf(nm, sizeof nm, "ctxdown:%s", pn);
    const xcam_track *tr = NULL;
    for (size_t i = 0; i < sizeof PUL_XCAM_TRACKS / sizeof PUL_XCAM_TRACKS[0] && !tr; i++) if (!strcmp(PUL_XCAM_TRACKS[i].move, nm)) tr = &PUL_XCAM_TRACKS[i];
    if (!tr || tr->n < 2) return 0;
    float t = ph * g_ps.vic_dur * (g_ps.speed > 1.001f ? g_ps.speed : 1.0f);
    const xcam_key *kk = tr->k; int n = tr->n;
    if (t <= kk[0].t) { memcpy(p3, kk[0].own, 12); return 1; }
    if (t >= kk[n - 1].t) { memcpy(p3, kk[n - 1].own, 12); return 1; }
    int i = 0; while (i + 1 < n && kk[i + 1].t < t) i++;
    float f = (t - kk[i].t) / (kk[i + 1].t - kk[i].t + 1e-6f);
    for (int j = 0; j < 3; j++) p3[j] = kk[i].own[j] + (kk[i + 1].own[j] - kk[i].own[j]) * f;
    return 1;
#else
    (void)k; (void)ph; (void)p3; return 0;
#endif
}
static int psync_place(int k, float ph, float *out) {
    uint64_t ent = k ? g_ps.ent_vic : g_ps.ent_att, sid = k ? g_ps.vic_sid : g_ps.att_sid;
    const float *c0 = k ? g_ps.c_vic : g_ps.c_att;
    const psync_bf *bf = k ? &g_ps.bf_vic : &g_ps.bf_att;
    if (!(k ? g_ps.c_vic_ok : g_ps.c_att_ok) || ph < 0.0f) return 0;
    static const float id7[7] = {0, 0, 0, 0, 0, 0, 1};
    psync_bf id;
    psync_bf_make(&id, id7);
    float ic0[8];
    ps_inverse(c0, ic0);
    float ph_end = ph > 1.0f ? 1.0f : ph;
    // first call: walk the phase from 0 so the branch of the half yaw is the clip's own (<= 0.02 phase per step)
    float ph0 = g_ps.half_yaw_ok[k] ? ph_end : 0.0f;
    if (!g_ps.half_yaw_ok[k]) g_ps.half_yaw[k] = 0.0f;
    int steps = g_ps.half_yaw_ok[k] ? 1 : 1 + (int)(ph_end / 0.02f);
    float s8[8] = {0}, bk[3]; int sing = 0;
    int bk_ok = psync_baked_root(k, ph_end, bk);
    if (bk_ok && (g_ps_bk.uid != g_ps.uid || g_ps_bk.seg != g_ps.cur_seg)) { memset(&g_ps_bk, 0, sizeof g_ps_bk); g_ps_bk.uid = g_ps.uid; g_ps_bk.seg = g_ps.cur_seg; }
    for (int i = 1; i <= steps; i++) {
        float p = steps == 1 ? ph_end : ph0 + (ph_end - ph0) * (float)i / (float)steps;
        float e[8], m[8];
        if (!psync_expected(ent, sid, &id, p, e)) return 0;
        ps_compose(ic0, e, m);                               // align(t) o align(t)
        float th = uc4_yaw(m), prev = g_ps.half_yaw[k];
        float a = uc4_wrap(th * 0.5f), b = uc4_wrap(th * 0.5f + 180.0f);
        float y = __builtin_fabsf(uc4_wrap(a - prev)) <= __builtin_fabsf(uc4_wrap(b - prev)) ? a : b;
        g_ps.half_yaw[k] = y;
        float r = y * 0.0174533f, cs = __builtin_cosf(r), sn = __builtin_sinf(r);
        // R(yaw) on (x, z): x' = x cos + z sin, z' = -x sin + z cos; (I + R) p = t
        float a11 = 1.0f + cs, a12 = sn, a21 = -sn, a22 = 1.0f + cs, det = a11 * a22 - a12 * a21;
        // (det = 2 + 2 cos: under 0.03 the half has turned within ~10 deg of 180 - the translation is noise / lost; the baked track takes it)
        sing = bk_ok && __builtin_fabsf(det) < 0.03f;
        if (!sing && __builtin_fabsf(det) < 1e-4f) return 0;          // a half turn per step: no unique root
        if (!sing) {
            s8[0] = (m[0] * a22 - a12 * m[2]) / det;
            s8[2] = (a11 * m[2] - a21 * m[0]) / det;
            s8[1] = m[1] * 0.5f;
        }
        s8[3] = 1.0f;
        s8[4] = 0.0f; s8[5] = __builtin_sinf(r * 0.5f); s8[6] = 0.0f; s8[7] = __builtin_cosf(r * 0.5f);
    }
    g_ps.half_yaw_ok[k] = 1;
    float pid[8], b8[8];
    ps_compose(c0, s8, pid);                                 // inv(apReference(t)) in ap space
    if (bk_ok) {
        if (!sing) { for (int j = 0; j < 3; j++) g_ps_bk.off[j] = pid[j] - bk[j]; g_ps_bk.ok = 1; }      // the baked track's offset to the exact solve, kept for the singular frames
        else {
            for (int j = 0; j < 3; j++) pid[j] = bk[j] + (g_ps_bk.ok ? g_ps_bk.off[j] : 0.0f);
            if (!g_ps_bk.sing && g_ps_bk.n++ < 4)
                xlog("psync: u%08x victim half rolled ~180 deg (phase %.3f): the root translation is unsolvable from align o align - placed on the baked own-align track "
                     "(%.2f %.2f %.2f ap space, offset %.2f %.2f m from the last exact solve)", g_ps.uid, ph_end, pid[0], pid[1], pid[2], (double)g_ps_bk.off[0], (double)g_ps_bk.off[2]);
        }
        g_ps_bk.sing = sing;
    }
    memcpy(b8, bf->local, sizeof b8);                        // unbound BoundFrame: local = world
    ps_compose(b8, pid, out);
    return ps_loc_ok(out);
}
// Where a pair's two halves END (clip phase 1) for an ap, BEFORE the move exists (no g_ps): the same math as psync_place on local state
// (no non-frozen carrier half is touched: melee pairs only), clips read through our own body. ph_out[k] = the world placement at phase `ph`;
// bit k of the result = half k (0 attacker, 1 victim) is readable. Used by the upgraded one-shot's path gate (a victim was forced to fall
// through the map): the 2013 side swing carries both bodies ~2.3 m with no collider, over whatever is there.
static int psync_pair_end(const float *ap7, uint64_t att_sid, uint64_t vic_sid, float ph, int gun, float out[2][8]) {
    static const float id7[7] = {0, 0, 0, 0, 0, 0, 1};
    psync_bf id;
    psync_bf_make(&id, id7);
    float a8[8];
    ps_ap8(ap7, a8);
    int got = 0;
    for (int k = 0; k < 2; k++) {
        uint64_t sid = k ? vic_sid : att_sid;
        float c0[8], ic0[8];
        if (!psync_offset(SID_PLAYER, sid, c0)) continue;
        ps_inverse(c0, ic0);
        float hy = 0.0f, s8[8] = {0};
        int steps = 1 + (int)(ph / 0.02f), ok = 1;
        for (int i = 1; i <= steps && ok; i++) {
            float p = ph * (float)i / (float)steps, e[8], m[8];
            if (!psync_expected(SID_PLAYER, sid, &id, p, e)) { ok = 0; break; }
            ps_compose(ic0, e, m);
            float th = uc4_yaw(m);
            float a = uc4_wrap(th * 0.5f), b = uc4_wrap(th * 0.5f + 180.0f);
            float y = __builtin_fabsf(uc4_wrap(a - hy)) <= __builtin_fabsf(uc4_wrap(b - hy)) ? a : b;
            hy = y;
            float r = y * 0.0174533f, cs = __builtin_cosf(r), sn = __builtin_sinf(r);
            float a11 = 1.0f + cs, a12 = sn, a21 = -sn, a22 = 1.0f + cs, det = a11 * a22 - a12 * a21;
            if (__builtin_fabsf(det) < 1e-4f) { ok = 0; break; }
            s8[0] = (m[0] * a22 - a12 * m[2]) / det;
            s8[2] = (a11 * m[2] - a21 * m[0]) / det;
            s8[1] = m[1] * 0.5f; s8[3] = 1.0f;
            s8[4] = 0.0f; s8[5] = __builtin_sinf(r * 0.5f); s8[6] = 0.0f; s8[7] = __builtin_cosf(r * 0.5f);
        }
        if (!ok) continue;
        float pid[8];
        ps_compose(c0, s8, pid);
        ps_compose(a8, pid, out[k]);
        if (ps_loc_ok(out[k])) got |= 1 << k;
    }
    return got;
}
// A puppet's locator does not follow its half (the downed victim puppet stayed on its start spot for 3.3 s,
// then jumped onto the clip in the frame its character collider came back on and it died). The NPC applies the animated
// align only while its character collider is on (npc-disable-character-collider clears Character+0x2aef bit 0, read by
// the per-frame update 0x140480a28 that switches the collider body's motion mode), and psync / the downed hitbox keep it
// off so the overlapping bodies don't push each other. So psync places the puppet itself every frame - what winmm's net
// locator did, now with the clip's placement - blended from where it stood over the half's blend-in (PS_BLEND).
// v5-geo (a shiv execution collided with a car on the backstep and slingshot the player across the room): the hand-off
// below teleport-players our attacker body onto the clip's end spot (att_last). The engine's own body - its character controller, which never
// enters geometry - stood 0.42 m off it: the clip's backstep had carried the placement into the car, and teleport-player put the capsule INSIDE
// the car, which the physics then shoved out. The hand-off now probes the line from the engine's body to the end spot (plus the 0.35 m capsule
// radius) at knee and chest height first (one frame, the body held on the end spot meanwhile) and hands over at the last clear spot before a hit.
static struct { int on; uint32_t uid; uint64_t f, j[2]; float from[3], dir[2], len, ey; int n; float pos[T2R_MAX_PEERS][3]; uint64_t hs[T2R_MAX_PEERS]; } g_ps_ho;
static int psync_ho_kick(const float *l0) {
    float dx = g_ps.att_last[0] - l0[0], dz = g_ps.att_last[2] - l0[2], d = __builtin_sqrtf(dx * dx + dz * dz);
    if (d < 0.10f) return 0;
    g_ps_ho.dir[0] = dx / d; g_ps_ho.dir[1] = dz / d; g_ps_ho.len = d; g_ps_ho.ey = g_ps.att_last[1];
    memcpy(g_ps_ho.from, l0, 12);
    g_ps_ho.n = sg_bodies(g_ps_ho.pos, g_ps_ho.hs);
    for (int k = 0; k < 2; k++) {
        float h = k ? 1.1f : 0.45f;
        float a[3] = {l0[0], l0[1] + h, l0[2]}, b[3] = {g_ps.att_last[0] + g_ps_ho.dir[0] * 0.35f, g_ps.att_last[1] + h, g_ps.att_last[2] + g_ps_ho.dir[1] * 0.35f};
        g_ps_ho.j[k] = world_ray_kick_m(a, b, 0, 0x1b07);
    }
    if (!g_ps_ho.j[0] && !g_ps_ho.j[1]) return 0;
    g_ps_ho.on = 1; g_ps_ho.uid = g_ps.uid; g_ps_ho.f = g_frame;
    return 1;
}
static void psync_ho_read(float *tgt) {
    float tot = g_ps_ho.len + 0.35f, th = -1.0f;
    for (int k = 0; k < 2; k++) {
        float t = g_ps_ho.j[k] ? ray_t(g_ps_ho.j[k]) : -1.0f;
        g_ps_ho.j[k] = 0;
        if (t < 0.0f || t >= 1.0f) continue;
        float s = t * tot, p[3] = {g_ps_ho.from[0] + g_ps_ho.dir[0] * s, g_ps_ho.from[1] + (k ? 1.1f : 0.45f) + (g_ps_ho.ey - g_ps_ho.from[1]) * (s < g_ps_ho.len ? s / g_ps_ho.len : 1.0f),
                                    g_ps_ho.from[2] + g_ps_ho.dir[1] * s};
        if (sg_body_at(p, g_ps_ho.pos, g_ps_ho.n, 0.60f) >= 0) continue;     // the victim's / anyone's body: not geometry
        if (th < 0.0f || t < th) th = t;
    }
    g_ps_ho.on = 0;
    if (th < 0.0f) { xlog("psync: u%08x hand-off probe: clear from the engine's body to the clip's end spot (%.2f m)", g_ps.uid, g_ps_ho.len); return; }
    float back = th * tot - 0.35f;
    back = back < 0.0f ? 0.0f : back > g_ps_ho.len ? g_ps_ho.len : back;
    tgt[0] = g_ps_ho.from[0] + g_ps_ho.dir[0] * back;
    tgt[1] = g_ps_ho.from[1] + (g_ps_ho.ey - g_ps_ho.from[1]) * (back / g_ps_ho.len);
    tgt[2] = g_ps_ho.from[2] + g_ps_ho.dir[1] * back;
    xlog("psync: u%08x hand-off probe: geometry %.2f m from the engine's body toward the clip's end spot (%.2f m away) - handed over at the last clear spot, %.2f m along (not inside it)",
         g_ps.uid, th * tot, g_ps_ho.len, back);
}
static void psync_drive(int k, double now) {
    uint64_t ent = k ? g_ps.ent_vic : g_ps.ent_att;
    int slot = k ? g_ps.vic : g_ps.att;
    int own = ent == SID_PLAYER;
    if (!ent || !g_ps.place_ok[k]) return;
    if (own) {
        // Our own body: the engine places it on its half (bf o inv(apReference)) while the layer plays and we live (1007h: err 0.00).
        // Once we are dead (the kill frame, or a stray hit before it) the Death state dropped the layer (phase reads 0.000) and nothing
        // moved the body any more: the executed victim stopped where it was at the kill (machete-decapitate 2013 moves 1.04 m, ~0.6 m
        // of it after the kill at 2.03 s; back-shiv 1.78 m, ~0.7 m after 1.30 s). From then psync places it on the clip itself.
        int need = k == 1 && g_ps_vic_drive && psync_own_vic_needs_drive();
        // Our ATTACKER body at its blend-out (A/B, two gun / cover-shotgun executions u0103084d, u0103084f: the body stepped 0.29 / 0.38 m toward the
        // victim in ONE frame, 2 frames after the stop-animating, 'err 0.00 -> 0.31' - the engine drops the clip's root motion at once while the
        // layer fades; the smooth ones (melee / shiv) glide). psync places it on the clip from the frame of the stop for the blend-out + 0.12 s,
        // continuing the placement the engine had (no offset at take-over), so nothing snaps; afterwards locomotion starts from where it stands.
        if (k == 0 && g_ps_att_out_drive && g_ps.out_done[0] && g_ps.att_drive_until > now) need = 1;
        // v5-geo2 (A i10 [12966]-[12978]: our body dragged from 1.21 to 1.61 m off the victim, then run in again): a duel finisher started closer than its SP
        // intro's start spot. Through the intro psync places our body itself: on the clip's spot, but never further from the victim than we started - we stand
        // (the intro's windup plays in place) until the intro's own run-in comes within our distance, then follow it. The full intro plays.
        if (k == 0 && g_ps_fin_step_uid && g_ps_fin_step_uid == g_ps.uid && g_ps.start_ok[0]) {
            float im = cd_seg0_ms(g_ps.move) / (g_ps.irate > 1.0f ? g_ps.irate : 1.0f);
            if (now - g_ps.play_ms < im + 50.0f) need = 1; else g_ps_fin_step_uid = 0;
        }
        // ps24 (rec15 B [25705]-[25706]: PLAY 'start 0.07 m / 0 deg from the attacker's authored spot', one frame later 'YAW SNAP -58 deg ... psync t=15 ms own drive 0'
        // - through the swing the duel warp wrote our facing over the engine's own ('the engine's own yaw step was up to 52.9 deg a frame (replaced)'); the frame the
        // pair took the body nobody wrote it, the engine's heading showed, and its align eased back over 156 ms = the flip when the punch lands, 8 of 12 pairs):
        // through a duel -hit pair's blend-in psync places our attacker body on the clip itself. t2r-hit-own-drive-old.txt = the engine from frame 0.
        if (k == 0 && g_ps.kind == PS_CTXDOWN && g_ps.nseg <= 1 && mdu_move(g_ps.move) && g_ps.start_ok[0] && now - g_ps.play_ms < PS_HIT_OWN_DRIVE_MS
            && GetFileAttributesA("t2r-hit-own-drive-old.txt") == INVALID_FILE_ATTRIBUTES) need = 1;
        // ps39 B4 (rec38a B [21426] 'victim 0.09 m / 110 deg off their spots', 'smooth: glide ... turn <= 420 deg/s', 'victim root ... our body by the engine'; frames
        // B 187.43-187.53: the body hit from behind flips ~150 deg within 0.1 s): the glide's turn limit only reaches bodies psync places - our own victim body
        // is put on its half by the engine's align, which takes the authored facing at once. Through the start glide of a duel -hit pair whose victim half starts
        // more than 15 deg off its facing, psync places our own victim body (the glide's smoothstep position and capped turn), like the attacker body since ps24.
        // t2r-vic-own-turn-ps38.txt = the engine from frame 0.
        if (k == 1 && g_ps.kind == PS_CTXDOWN && g_ps.nseg <= 1 && mdu_move(g_ps.move) && g_ps.start_ok[1] && g_ps_off_y[1] > 15.0f && !psync_own_dead_now()
            && now - g_ps.play_ms < (double)(g_ps.drive_bl > 0.0f ? g_ps.drive_bl : g_ps_blend) * 1000.0 + 34.0 && GetFileAttributesA("t2r-vic-own-turn-ps38.txt") == INVALID_FILE_ATTRIBUTES) need = 1;
        // ps44 T7 (rec43a B 9.00->9.03 / 50.23->50.27: our own victim body flips back-to-lens -> side in one frame at a pair start, no YAW SNAP line and no 'held to
        // 15 deg' line in either log): the ps39 B4 rule above (and the ps43 15 deg cap below, which only runs where psync places our body) covers duel -hit pairs of
        // ONE segment only - a takedown / execution / finisher / chained victim half on us is placed by the engine's align from its first frame, which takes the
        // authored facing at once. Every victim half that starts on our living body more than 15 deg off its facing gets the same start glide by psync (smoothstep
        // position, capped turn, 15 deg a frame at most). Which of these was the 9.03 / 50.27 flip is NOT proven (the line below names each start it takes).
        // t2r-vic-own-turn-all-old.txt = only the duel -hit rule above.
        int t744 = 0;
        if (k == 1 && !need && g_ps.start_ok[1] && g_ps_off_y[1] > 15.0f && !psync_own_dead_now() && g_ps_vic_drive
            && now - g_ps.play_ms < (double)(g_ps.drive_bl > 0.0f ? g_ps.drive_bl : g_ps_blend) * 1000.0 + 34.0) {
            static int old44 = -1; static uint64_t chk44; uint64_t n44 = GetTickCount64();
            if (old44 < 0 || n44 - chk44 > 2000) { chk44 = n44; old44 = GetFileAttributesA("t2r-vic-own-turn-all-old.txt") != INVALID_FILE_ATTRIBUTES; }
            static uint32_t lu44;
            if (lu44 != g_ps.uid) { lu44 = g_ps.uid; xlog("psync: u%08x our victim half (kind %d, %d segment(s), duel move %d) starts %.0f deg off its facing - %s (ps44 T7; t2r-vic-own-turn-all-old.txt = old)",
                g_ps.uid, g_ps.kind, g_ps.nseg, mdu_move(g_ps.move) ? 1 : 0, (double)g_ps_off_y[1], old44 ? "old: the engine's align from frame 0" : "psync places our body through the start glide, turn capped 15 deg a frame"); }
            if (!old44) { need = 1; t744 = 1; }
        }
        g_ps_t744 = t744;
        if (!need) {
            // (the executioner rubber-banded back to the downed player; A log 87581: ap 0.45 0.04 -> 0.10 0.10 in ONE frame, 0.35 m, the frame
            // after this drive ended, then drifting on to 0.42 m; 3 of 8 gun / cover executions, 0.29-0.35 m): set-object-locator moves the player
            // object but the engine's player state (character controller / locomotion) never took the clip's root motion, so when psync let go the
            // engine put the body back to its own spot - on our screen, and (the net position is read from that state) on every other screen's puppet.
            // The player state is moved to where the drive left the body with the engine's own teleport-player, once, as the drive ends.
            if (k == 0 && own && g_ps.own_drv && g_ps.att_last_ok && g_ps.out_done[0] && g_ps_att_out_drive && !psync_own_dead_now()) {
                float b0[16]; const float *l0 = psync_loc(SID_PLAYER, b0);
                float dd = l0 ? __builtin_sqrtf((l0[0] - g_ps.att_last[0]) * (l0[0] - g_ps.att_last[0]) + (l0[2] - g_ps.att_last[2]) * (l0[2] - g_ps.att_last[2])) : -1.0f;
                if (g_ps_ho.on && (g_ps_ho.uid != g_ps.uid || g_frame - g_ps_ho.f > 4)) { ray_t(g_ps_ho.j[0]); ray_t(g_ps_ho.j[1]); g_ps_ho.j[0] = g_ps_ho.j[1] = 0; g_ps_ho.on = 0; }
                if (!g_ps_ho.on && l0 && dd > 0.10f && psync_ho_kick(l0)) {
                    static psync_bf bfh;                         // v5-geo: held on the end spot for the probe's frame (no 1-frame snap toward the engine's body)
                    psync_bf_from_loc(&bfh, g_ps.att_last);
                    mo_write(SID_PLAYER, &bfh, MO_SRC("paired.att_end_hold"), 0);
                    return;                                      // own_drv stays: the hand-off runs next frame with the probe's answer
                }
                float tgt[8]; memcpy(tgt, g_ps.att_last, sizeof tgt);
                if (g_ps_ho.on && g_ps_ho.uid == g_ps.uid) psync_ho_read(tgt);
                mo_teleport(tgt, tgt + 4, MO_SRC("paired.att_end_handoff"), 0);
                xlog("psync: u%08x our attacker body handed to the engine at its placed end spot %.2f %.2f %.2f (teleport-player; the engine's body read %.2f m off it just before) - the end-of-move snap back",
                     g_ps.uid, tgt[0], tgt[1], tgt[2], dd);
                g_ps.att_last_ok = 0;
            }
            g_ps.own_drv = 0; return;
        }
    } else {
        if (slot < 0 || slot > T2R_MAX_PEERS - 1) return;
        if (!g_ps_pup[slot].on || g_ps_pup[slot].h != ent || (psync_dead(ent) && !(k && g_ps.vic_keep))) return;    // released / death owns the body (unless the victim half is kept)
    }
    float dbl = g_ps.drive_bl > 0.0f ? g_ps.drive_bl : g_ps_blend;
    if (k == 1) dbl = sptl_vic_drive_s(dbl);   // (a duel -hit victim half snaps onto its facing in one frame, as SP: melee_duel_sptl.c)
    if (!own) dbl = dtl_pull_s(k, ent, dbl);   // v5-body: a duel half's start pull on the PUPPET is never faster than a lunge (peak <= 6 m/s, 540 deg/s; melee_duel_tl.c)
    float w = (float)((now - g_ps.play_ms) / (dbl * 1000.0));
    w = w < 0.0f ? 0.0f : w > 1.0f ? 1.0f : w;
    w = g_ps.drive_easeout ? 1.0f - (1.0f - w) * (1.0f - w) : w * w * (3.0f - 2.0f * w);   // SP's quadratic ease-out / smoothstep
    float t[8];
    memcpy(t, g_ps.place[k], sizeof t);
    if (w < 1.0f && g_ps.start_ok[k]) {
        const float *s = g_ps.start_loc[k];
        for (int i = 0; i < 3; i++) t[i] = s[i] + (g_ps.place[k][i] - s[i]) * w;
        float d = s[4] * t[4] + s[5] * t[5] + s[6] * t[6] + s[7] * t[7], sg = d < 0.0f ? -1.0f : 1.0f, n = 0.0f;
        for (int i = 4; i < 8; i++) { t[i] = s[i] * (1.0f - w) + sg * g_ps.place[k][i] * w; n += t[i] * t[i]; }
        n = __builtin_sqrtf(n);
        if (n < 1e-3f) return;
        for (int i = 4; i < 8; i++) t[i] /= n;
    }
    if (own && k == 0 && g_ps_fin_step_uid == g_ps.uid && g_ps.start_ok[0]) {      // the finisher's natural step (see the need above): never back away from the victim
        const float *s = g_ps.start_loc[0];
        float vx = g_ps.ap[0], vz = g_ps.ap[2];
        float d0 = __builtin_sqrtf((s[0] - vx) * (s[0] - vx) + (s[2] - vz) * (s[2] - vz)), dt = __builtin_sqrtf((t[0] - vx) * (t[0] - vx) + (t[2] - vz) * (t[2] - vz));
        if (dt > d0 && dt > 0.05f) { t[0] = vx + (t[0] - vx) * d0 / dt; t[2] = vz + (t[2] - vz) * d0 / dt; }
    }
    t[3] = 1.0f;
    if (g_ps_smooth && ps_loc_ok(t)) {
        // A discontinuity of the target (the layer dropped by the death and re-applied, a kick-fix hold, a frame without a placement)
        // was a one-frame snap of the puppet. It is absorbed into an offset that decays (PS_JUMP_TAU); normal root motion passes
        // unchanged (the threshold is a 5 m/s step + 6 cm, 360 deg/s + 10 deg), so the paired alignment is not lagged.
        float dt = g_ps.tick_dt > 0.0f ? g_ps.tick_dt / 1000.0f : 1.0f / 60.0f;
        if (dt > 0.1f) dt = 0.1f;
        // ps39 B8 (rec38a B [14521], clash pair u001a5451: 'drive slot 0 attacker half - placement jumped 1.16 m / 0 deg in one frame (t=1016) - absorbed, decays over
        // ~0.42 s' on the first frame of our blend-out drive; frames B 72.10-72.17: the clinch snaps to the shoved-apart pose): our own body is driven for the
        // pair's blend-in (ps24), then placed by the engine, then driven again at the blend-out - the 'previous target' was still the one from the blend-in, a second
        // ago, so the whole travel of the move since then read as a one-frame jump and was put back on the body as an offset (it stepped back to where the move
        // began and slid in again). A target older than one frame is no previous target. t2r-drive-stale-prev-ps38.txt = old.
        static uint64_t drv_f39[2]; static uint32_t drv_uid39;
        int fresh39 = (drv_uid39 == g_ps.uid && g_frame - drv_f39[k] <= 1) || GetFileAttributesA("t2r-drive-stale-prev-ps38.txt") != INVALID_FILE_ATTRIBUTES;
        if (g_ps.drv_ok[k] && !fresh39) { static int nls; if (LOGCAP(nls, 60)) xlog("psync: u%08x drive %s half (%s): the last drive target is %llu frames old - not a jump, nothing absorbed (ps39)", g_ps.uid, k ? "victim" : "attacker", own ? "our body" : "puppet", (unsigned long long)(drv_uid39 == g_ps.uid ? g_frame - drv_f39[k] : 0)); }
        if (drv_uid39 != g_ps.uid) { drv_uid39 = g_ps.uid; drv_f39[0] = drv_f39[1] = 0; }
        drv_f39[k] = g_frame;
        if (g_ps.drv_ok[k] && fresh39) {
            const float *p = g_ps.drv_raw[k];
            float dx = t[0] - p[0], dy = t[1] - p[1], dz = t[2] - p[2], d = __builtin_sqrtf(dx * dx + dy * dy + dz * dz);
            float pc[4], dq[4];
            ps_qconj(t + 4, pc);
            ps_qmul(p + 4, pc, dq);                          // prev.q = dq * t.q
            ps_qnorm(dq);
            float ang = ps_qangle(dq);
            if (d > 0.06f + 5.0f * dt || ang > 10.0f + 360.0f * dt) {
                for (int i = 0; i < 3; i++) g_ps.off_p[k][i] += p[i] - t[i];
                float nq[4];
                ps_qmul(g_ps.off_q[k], dq, nq);              // out stays: off' * t.q = off * prev.q
                ps_qnorm(nq);
                memcpy(g_ps.off_q[k], nq, 16);
                if (g_ps.jumps[k]++ < 12)
                    xlog("psync: u%08x drive slot %d %s half - placement jumped %.2f m / %.0f deg in one frame (t=%.0f) - absorbed, decays over ~%.2f s",
                         g_ps.uid, slot, k ? "victim" : "attacker", d, ang, now - g_ps.t0, PS_JUMP_TAU * 3.0f);
            }
            float f = __builtin_expf(-dt / PS_JUMP_TAU);
            for (int i = 0; i < 3; i++) g_ps.off_p[k][i] *= f;
            ps_qtoward_id(g_ps.off_q[k], f);
        } else {
            g_ps.off_p[k][0] = g_ps.off_p[k][1] = g_ps.off_p[k][2] = 0.0f;
            g_ps.off_q[k][0] = g_ps.off_q[k][1] = g_ps.off_q[k][2] = 0.0f; g_ps.off_q[k][3] = 1.0f;
        }
        memcpy(g_ps.drv_raw[k], t, sizeof t);
        g_ps.drv_ok[k] = 1;
        if (own && !g_ps.own_drv) {         // take-over: from where the engine left the body, the offset to the clip decays (no pop)
            float b[16];
            const float *l = psync_loc(SID_PLAYER, b);
            if (l && ps_loc_ok(l)) {
                for (int i = 0; i < 3; i++) g_ps.off_p[k][i] = l[i] - t[i];
                float pc[4], dq[4];
                ps_qconj(t + 4, pc);
                ps_qmul(l + 4, pc, dq);
                ps_qnorm(dq);
                memcpy(g_ps.off_q[k], dq, 16);
            }
        }
        for (int i = 0; i < 3; i++) t[i] += g_ps.off_p[k][i];
        float rq[4];
        ps_qmul(g_ps.off_q[k], t + 4, rq);
        ps_qnorm(rq);
        memcpy(t + 4, rq, 16);
    }
    // Slopes ('enemy execution on a slope sinks the victim into the ground', third-party view): the clips are authored on flat
    // ground, so the placement is ap.y + the clip's own y - at the half's x / z the floor can be higher or lower than under the ap (the victim
    // crawls / is dragged several metres up or down a slope). Each puppet half gets the floor delta under its CURRENT x / z (static-world ray
    // 0.6 m above to 1.4 m below the placement, kicked now / read next frame, mask 0x207) added to its y, smoothed (~80 ms) and clamped to
    // 0.8 m; the clip's own vertical motion and the pair's relative alignment are untouched. No hit = the last delta is kept.
    if (!own && g_ps_ground && ps_loc_ok(t) && !ps_rays_blind()) {
        float dtg = g_ps.tick_dt > 0.0f ? g_ps.tick_dt / 1000.0f : 1.0f / 60.0f;
        if (dtg > 0.1f) dtg = 0.1f;
        if (g_ps.gr_job[k]) {
            float rt = ray_t(g_ps.gr_job[k]), rt2 = g_ps.gr_job2[k] ? ray_t(g_ps.gr_job2[k]) : -1.0f, rt3 = g_ps.gr_job3[k] ? ray_t(g_ps.gr_job3[k]) : -1.0f;
            g_ps.gr_job[k] = g_ps.gr_job2[k] = g_ps.gr_job3[k] = 0;
            // (B, shivved, saw herself half a meter lower than the character on A's screen; B log 148773: 'floor -1.26 ... vs the ap's
            // -1.86: y +0.60' with all three rays agreeing, and 31 of the logged lifts are exactly +0.60 = the ray's start height): a hit at t = 0 is a
            // ray that STARTED inside a collider (the other body's capsule, a prop, the cover the clip leans over), not a floor 0.6 m up - ignored
            if (rt >= 0.0f && rt < 0.01f) rt = -1.0f;
            if (rt2 >= 0.0f && rt2 < 0.01f) rt2 = -1.0f;
            if (rt3 >= 0.0f && rt3 < 0.01f) rt3 = -1.0f;
            if (rt2 >= 0.0f && rt2 <= 1.0f && (rt < 0.0f || rt > 1.0f || rt2 > rt)) rt = rt2;   // the lowest floor of the three: a body / grass only ever raises a reading
            if (rt3 >= 0.0f && rt3 <= 1.0f && (rt < 0.0f || rt > 1.0f || rt3 > rt)) rt = rt3;
            // (v5-int22, A = attacker of a half-wall pin against a car: the victim was lifted up during all the hits and the finisher,
            // fine on the victim's POV; A 29361-29525: 'psync place ... clip -84.65 3.66 ... we put -84.65 4.08', 'psync ground: ... floor 4.12 under
            // -84.65 166.95 vs the ap's 3.66: y +0.45'): the pinned victim's root sits 0.26 m from the ap, under the car's body overhang, and the
            // down ray landed on the car's bumper / sill 0.46 m up. A floor that no walkable slope connects to the ap's floor (grade > 0.6 plus a
            // 0.15 m step) is not the ground the half stands on - it is the cover / prop the clip leans over: rejected, the last delta is kept
            // (0 when nothing valid was read yet), so the puppet stays on the ap's ground like the victim's own body on its own screen.
            if (rt >= 0.0f && rt <= 1.0f) {
                float dxa = g_ps.gr_a[k][0] - g_ps.ap[0], dza = g_ps.gr_a[k][2] - g_ps.ap[2], dh = __builtin_sqrtf(dxa * dxa + dza * dza);
                float rise = g_ps.gr_a[k][1] - rt * 2.0f - g_ps.ap[1], lim = 0.6f * dh + 0.15f;
                // (special executions bugged out on stairs, u01095ef8 [138109]-[138168]: the attacker puppet followed a stair at floor delta -0.49 (applied), then
                // the half's x / z came within 0.45 m of the ap (walkable limit 0.6 * dist + 0.15 = 0.38 < the 0.46 m rise) -> 'REJECTED ... kept -0.25' every frame: the half popped 0.24 m up
                // mid-clip). A floor that continues the one the half already follows (accepted delta within 0.30 m of this reading) is the same stair, not a prop the clip leans over:
                // the continuity test comes first. t2r-no-ground-cont.txt = old rule.
                static int gcont = -1; if (gcont < 0) gcont = GetFileAttributesA("t2r-no-ground-cont.txt") == INVALID_FILE_ATTRIBUTES;
                float wantc = g_ps.gr_a[k][1] - rt * 2.0f - g_ps.ap[1];
                int cont = gcont && g_ps.gr_ok[k] && __builtin_fabsf(wantc - g_ps.gr_dy[k]) <= 0.30f;
                if (!cont && __builtin_fabsf(rise) > lim) {
                    if (g_ps.gr_rej++ < 12)
                        xlog("psync ground: u%08x %s half slot %d floor %.2f under %.2f %.2f vs the ap's %.2f: y %+.2f REJECTED (%.2f m from the ap, walkable <= %.2f: "
                             "a prop / cover, not ground) - kept %+.2f", g_ps.uid, k ? "victim" : "attacker", slot, g_ps.gr_a[k][1] - rt * 2.0f, g_ps.gr_a[k][0],
                             g_ps.gr_a[k][2], g_ps.ap[1], rise, dh, lim, g_ps.gr_dy[k]);
                    rt = -1.0f;
                }
            }
            if (rt >= 0.0f && rt <= 1.0f) {
                float want = g_ps.gr_a[k][1] - rt * 2.0f - g_ps.ap[1];
                want = want < -0.8f ? -0.8f : want > 0.8f ? 0.8f : want;
                if (!g_ps.gr_ok[k]) g_ps.gr_dy[k] = want;     // first reading: no ramp-in
                g_ps.gr_dy[k] += (want - g_ps.gr_dy[k]) * (1.0f - __builtin_expf(-dtg / 0.08f));
                g_ps.gr_ok[k] = 1;
                if (__builtin_fabsf(want) > 0.08f && g_ps.gr_n++ < 24)
                    xlog("psync ground: u%08x %s half slot %d floor %.2f under %.2f %.2f vs the ap's %.2f: y %+.2f (applied %+.2f)", g_ps.uid, k ? "victim" : "attacker", slot,
                         g_ps.gr_a[k][1] - rt * 2.0f, g_ps.gr_a[k][0], g_ps.gr_a[k][2], g_ps.ap[1], want, g_ps.gr_dy[k]);
            }
        }
        float ga[3] = {t[0], t[1] + 0.6f, t[2]}, gb[3] = {t[0], t[1] - 1.4f, t[2]};
        // (B constantly jumped up and down in a special execution): mask 0x207 reports body colliders too, and the ray down through
        // the pair read a body ('floor 4.92 under -98.14 198.48 vs the ap's 4.33', flickering 4.61 / 4.92 frame to frame) - the half was lifted
        // ~0.5 m and dropped. kick-raycast ignores one object, so two rays: one ignores this half's puppet, the other the other half's body (our
        // player, or its puppet); the lower floor wins.
        uint64_t other = k ? g_ps.ent_att : g_ps.ent_vic;
        g_ps.gr_job[k] = world_ray_kick_ign(ga, gb, ent);
        g_ps.gr_job2[k] = other && other != ent ? world_ray_kick_ign(ga, gb, other) : 0;
        g_ps.gr_job3[k] = world_ray_kick_m(ga, gb, ent, 0x1b07);   // 0x207 stops on tall grass ~0.5 m up (the path gate's grass field); 0x1b07 passes it
        memcpy(g_ps.gr_a[k], ga, sizeof ga);
        t[1] += g_ps.gr_dy[k];
    }
    if (!own && g_ps.kind == PS_CTXDOWN) cd_stature_apply(k, now, t);   // ps46 (machete throat slash in the face; ice-pick knife behind the head): ctxdown.c CD_STATURE + CD_FIN_STATURE
    if (!ps_loc_ok(t)) {                                     // never hand the engine a NaN / huge locator (HavokRayCastJob assert)
        static int nl;
        if (LOGCAP(nl, 20)) xlog("psync: drive slot %d - non-finite / huge placement (%g %g %g q %g %g %g %g) refused, body left as is",
                            slot, t[0], t[1], t[2], t[4], t[5], t[6], t[7]);
        return;
    }
    // (not for a takedown: its ap IS the wall frame the engine's probe found, the authored victim path stays in front of that surface - the guard's
    //  ray runs 0.35 m past the body and hit the very wall the victim is pressed against: "victim root ... WALL ... body held" up to 0.37 m off the clip, A/B)
    // gun executions: the victim PUPPET (attacker's screen) follows the clip's whole placement like the victim's own body does on its screen.
    // The guard's probe (0.35 m past each step, 0.35 m up) hit nearby clutter 0.1 s into the hunting-rifle move (A 'wall 0.93 along the
    // way at t=501'), froze the puppet's x/z at 0.16 -0.10 while the clip crawled it to 1.07 0.01 (err up to 0.92 m, 'WALL'), and it snapped at the end.
    // The victim's own screen has no such guard while alive, so both screens disagreed. t2r-no-gx-nowall.txt = the guard as before.
    // (shiv anims sometimes made the victim stay in place and teleport at the end): the same hold on the shiv / melee-execution /
    // finisher puppets (A stand shiv 'npc-bow-cover-stand-r-aim^hunker': 'WALL' from t=500, placed 0.07 0.01 while authored went to 0.10 1.78, err 1.76 m,
    // snap at the end). Every non-own victim puppet follows its clip; ctxdown's guard was already off; only our OWN dead body keeps the guard.
    int gx_free = k == 1 && !own && g_ps_gx_nowall && !(g_ps.kind == PS_CTXDOWN && mdu_move(g_ps.move));   // (a melee duel reaction keeps the guard: B's hit reaction clipped into collision)
    if (gx_free) {
        static int nl; if (g_ps.wall_hold || g_ps.wall_job) { if (LOGCAP(nl, 6)) xlog("gx place: u%08x victim puppet follows its clip, wall guard off for puppets (hold dropped)", g_ps.uid); }
        psync_wall_guard(t, 0);
    } else
    if (k == 1) psync_wall_guard(t, (g_ps.kind != PS_CTXDOWN || mdu_move(g_ps.move)) && now - g_ps.play_ms >= g_ps_blend * 1000.0);
    // ps43 N3 (rec42a B [20735] 'smooth: glide ... victim 0.03 / 162 deg -> smoothstep over 385 ms, turn <= 420 deg/s', [20742] 'YAW SNAP slot 0 turned -72 deg in 1
    // frame (... psync role 2, victim half) - writers: psync u0104dc37 kind 6 t=115 ms own drive 1', then -12 / -13 deg a frame for 8 frames; B [19387] / [19388] -73 /
    // -78 deg at t=16 / 32 ms of an attacker half, [11392] / [11393] -55 / +62): the drive's turn limit is a time for the whole glide, not a step - one frame of this
    // drive turned our own root 55-78 deg (no 'placement jumped' line: the raw target did not step, the written yaw did - the cause inside the drive is NOT found;
    // this line is the measurement). The rule (ps43): our own root never turns more than PS_OWN_YAW_STEP in one frame under a duel pair's drive; the rest
    // comes on the following frames (the target is still ahead, the step repeats). t2r-own-drive-yaw-step-old.txt = no limit (the line stays).
#define PS_OWN_YAW_STEP 15.0f   // [TUNING ps43] deg a frame
    if (own && ((g_ps.kind == PS_CTXDOWN && mdu_move(g_ps.move)) || (k == 1 && g_ps_t744))) {   // (ps44 T7: every victim-half start glide on our body)
        static struct { uint32_t uid; uint64_t f; float yaw; int k; } y43; static int off43 = -1; static uint64_t chk43; uint64_t n43 = GetTickCount64();
        if (off43 < 0 || n43 - chk43 > 2000) { chk43 = n43; off43 = GetFileAttributesA("t2r-own-drive-yaw-step-old.txt") != INVALID_FILE_ATTRIBUTES; }
        float ty43 = uc4_yaw(t), by43 = ty43, b43[16]; int have43 = 0, last43 = y43.uid == g_ps.uid && y43.k == k && g_frame - y43.f <= 1;
        const float *l43 = psync_loc(SID_PLAYER, b43);
        if (last43) { by43 = y43.yaw; have43 = 1; }
        else if (l43 && ps_loc_ok(l43)) { by43 = uc4_yaw(l43); have43 = 1; }
        float d43 = uc4_wrap(ty43 - by43);
        if (have43 && __builtin_fabsf(d43) > PS_OWN_YAW_STEP) {
            float ny43 = uc4_wrap(by43 + (d43 > 0.0f ? PS_OWN_YAW_STEP : -PS_OWN_YAW_STEP));
            static int nl43; if (LOGCAP(nl43, 300)) xlog("psync: u%08x own %s body: this frame's drive turns the root %+.0f deg (from %s %+.0f to %+.0f deg; the body reads %+.0f; t=%.0f ms, blend weight %.2f, start %.0f deg off) - %s (ps43; t2r-own-drive-yaw-step-old.txt = old)",
                                                       g_ps.uid, k ? "victim" : "attacker", (double)d43, last43 ? "our last write" : "the body's yaw", (double)by43, (double)ty43, l43 ? (double)uc4_yaw(l43) : 0.0, now - g_ps.t0, (double)w, (double)g_ps_off_y[k],
                                                       off43 ? "written as is (old)" : "held to 15 deg, the rest follows on the next frames");
            if (!off43) { float h43 = ny43 * 0.5f / 57.29578f; t[4] = 0.0f; t[5] = __builtin_sinf(h43); t[6] = 0.0f; t[7] = __builtin_cosf(h43); ty43 = ny43; }
        }
        y43.uid = g_ps.uid; y43.k = k; y43.f = g_frame; y43.yaw = ty43;
    }
    static psync_bf bf;                                      // a BoundFrame, not a Locator (re/tackle-crash-10-06.md)
    psync_bf_from_loc(&bf, t);
    // (after a low cover pin escape the victim teleported behind the attacker): the struggle-success clip's root runs ~2.7 m
    // in the 0.35 s after its release (B 39769-39790: 404.17 -> 406.12, then a 3.4 m pos-jump at the hand-off). The blend-out drive follows the clip only
    // while it moves like a body (<= 0.08 m a frame); a faster step ends the drive where the body stands (the engine keeps it there).
    // ps43 P1 (rec42a B clash pair u0004f9fc, swinger half released at t=916: [20887]-[20892] 'dtl: SNAP slot 0 0.15 / 0.21 / 0.25 / 0.30 / 0.27 / 0.21 m in 1 frame
    // (clip root motion explains 0.01-0.04 m ...) - writers: psync ... own drive 1 out 10' = 1.35 m in 6 frames, [20889] 'kick fix: attacker half's clip ended (phase
    // 0.000)', [20893] 'SNAP 1.46 m', [20895] 0.42 m, then 'paired.att_free TP 0.00 m (eng 0.64)' + 'travel clamp: our body handed to the engine at its last clipped
    // spot (it read 0.64 m off it)' = [20896] SNAP 0.64 m; frames B 176.27-176.47: our body runs 1.3 m forward through the opponent and is back). The placement
    // itself moved 0.01-0.04 m a frame and this drive's step guard below (0.08 m of the TARGET) never fired: the body left our writes, the writes did not step. No
    // other ext writer is named on those frames, so the mover is the engine (its own state under the fading / gone layer; a bot melee press was dropped by the duel
    // 9 frames before - an engine lunge is the suspect, NOT proven). The same shape, one frame, 4 frames after 'kick fix: clip ended' on three more clash pairs
    // ([14854] 0.27 m, [15476] 0.24 m, [15615] 0.21 m). The rule (lead): while the attacker half blends OUT the drive follows the clip only -
    //  1 the body reads PS_OUT_RUN_M further off our last write than the frame before: the engine is moving it -> the drive stops, NOTHING is written or teleported
    //    (the body stays with the engine);
    //  2 the half's layer is gone (phase reads 0: kick fix / lost layer) -> the drive stops as the step guard below does (held on the last placed spot, handed over);
    //  3 the target steps more than the clip's own root motion that frame + PS_OUT_PULL_M -> the same stop.
    // The line is also the measurement for the blend-IN steps (B [21128] 'SNAP 0.18 m ... t=32 ms own drive 1 out 00': the pull's own share of that frame is <= 0.05 m
    // (quadratic ease-out over 0.17 s of 0.30 m) - the rest came from outside this drive, the engine's align of the new layer is the suspect; no rule there yet).
    // t2r-att-out-chase-old.txt = old (the line stays).
#define PS_OUT_PULL_M 0.03f    // m a frame the blend-out target may step beyond the clip's own root motion (= TC_D_STEP)
#define PS_OUT_RUN_M 0.10f     // [TUNING ps43] m: the body's distance from our last write grew by this in ONE frame = the engine carries it (6 m/s: no clip fade does that)
    if (own && k == 0) {
        static struct { uint32_t uid; uint64_t f; float pl[3], e; } o43; static int old43 = -1, nl43; static uint64_t chk43b; uint64_t n43b = GetTickCount64();
        if (old43 < 0 || n43b - chk43b > 2000) { chk43b = n43b; old43 = GetFileAttributesA("t2r-att-out-chase-old.txt") != INVALID_FILE_ATTRIBUTES; }
        int cont43 = o43.uid == g_ps.uid && g_frame - o43.f <= 1 && g_ps.own_drv && g_ps.att_last_ok;
        float bb43[16]; const float *lb43 = psync_loc(SID_PLAYER, bb43);
        float e43 = -1.0f, c43 = -1.0f, s43 = -1.0f, pe43 = cont43 ? o43.e : 0.0f;
        if (cont43) {
            c43 = __builtin_sqrtf((g_ps.place[0][0] - o43.pl[0]) * (g_ps.place[0][0] - o43.pl[0]) + (g_ps.place[0][2] - o43.pl[2]) * (g_ps.place[0][2] - o43.pl[2]));
            s43 = __builtin_sqrtf((t[0] - g_ps.att_last[0]) * (t[0] - g_ps.att_last[0]) + (t[2] - g_ps.att_last[2]) * (t[2] - g_ps.att_last[2]));
            if (lb43 && ps_loc_ok(lb43)) e43 = __builtin_sqrtf((lb43[0] - g_ps.att_last[0]) * (lb43[0] - g_ps.att_last[0]) + (lb43[2] - g_ps.att_last[2]) * (lb43[2] - g_ps.att_last[2]));
        }
        o43.uid = g_ps.uid; o43.f = g_frame; memcpy(o43.pl, g_ps.place[0], 12); o43.e = e43 >= 0.0f ? e43 : 0.0f;
        int gone43 = g_ps_att_gone43_uid == g_ps.uid && g_ps_att_gone43_f == g_frame, eng43 = 0;
        const char *why43 = NULL;
        if (cont43 && g_ps.out_done[0]) {
            if (e43 > PS_OUT_RUN_M && e43 - pe43 > PS_OUT_RUN_M) { why43 = "the engine carries the body away from our writes"; eng43 = 1; }
            else if (gone43) why43 = "the half's layer is gone";
            else if (s43 > c43 + PS_OUT_PULL_M) why43 = "the target steps more than the clip's root motion + 0.03 m";
        }
        if ((e43 > 0.05f || why43) && LOGCAP(nl43, 400))
            xlog("psync: u%08x own attacker drive t=%.0f ms (%s): the body reads %.2f m off our last write (%.2f m the frame before), this frame's target steps %.2f m, the clip's root %.2f m, layer %s - %s%s (ps43 P1; t2r-att-out-chase-old.txt = old)",
                 g_ps.uid, now - g_ps.t0, g_ps.out_done[0] ? "blend-OUT" : "blend-in / intro", (double)e43, (double)pe43, (double)s43, (double)c43, gone43 ? "GONE" : "on",
                 why43 ? why43 : "measurement: the engine moved the body since our write, the drive goes on",
                 !why43 ? "" : old43 ? ": old, the drive goes on" : eng43 ? ": the drive stops, no hold and no hand-off teleport - the body stays with the engine" : ": the drive stops, the body is held on its last placed spot and handed to the engine there");
        if (why43 && !old43) {
            g_ps.att_drive_until = 0.0;
            if (eng43) { g_ps.att_last_ok = 0; g_ps.own_drv = 0; return; }
            static psync_bf bfs43;
            psync_bf_from_loc(&bfs43, g_ps.att_last);
            mo_write(SID_PLAYER, &bfs43, MO_SRC("paired.att_end_hold"), 0);
            return;
        }
    }
    if (own && k == 0 && g_ps.own_drv && g_ps.out_done[0] && g_ps.att_last_ok) {
        float st = __builtin_sqrtf((t[0] - g_ps.att_last[0]) * (t[0] - g_ps.att_last[0]) + (t[2] - g_ps.att_last[2]) * (t[2] - g_ps.att_last[2]));
        if (st > 0.08f) {
            g_ps.att_drive_until = 0.0;
            xlog("psync: u%08x our attacker blend-out drive stopped at t=%.0f ms: the clip's root steps %.2f m in one frame - the body stays at %.2f %.2f %.2f", g_ps.uid, now - g_ps.t0, st,
                 g_ps.att_last[0], g_ps.att_last[1], g_ps.att_last[2]);
            // ps23 (rec13 B [16908]-[16911]: this frame placed nothing, so the engine put the body back on ITS spot 2.23 m away, the next frame's end hold
            // pulled it back - 'SNAP 2.21 m ... paired.att_end_hold' - and the hand-off moved it 0.25 m again): the frame the drive stops holds the body where it
            // says it stays, with the end hold's own write; the hand-off (probe, then teleport-player there) follows as before. t2r-att-stop-hold-old.txt = no write.
            if (GetFileAttributesA("t2r-att-stop-hold-old.txt") == INVALID_FILE_ATTRIBUTES) {
                static psync_bf bfs;
                psync_bf_from_loc(&bfs, g_ps.att_last);
                mo_write(SID_PLAYER, &bfs, MO_SRC("paired.att_end_hold"), 0);
            }
            return;
        }
    }
    if (own) {
        uint64_t a[2] = {SID_PLAYER, (uint64_t)&bf};
        uint64_t r = mo_write_dc(a, MO_SRC("paired.drive_own"), 0);   // set-object-locator
        if (k == 0) { memcpy(g_ps.att_last, t, 32); g_ps.att_last_ok = 1; }
        if (!g_ps.own_drv)
            xlog("psync: u%08x our %s body taken over at t=%.0f ms (%s%s%s): placed on its half by psync from here (set-object-locator -> %llx), "
                 "start offset %.2f m", g_ps.uid, k ? "victim" : "attacker", now - g_ps.t0, k == 0 ? (g_ps.out_done[0] ? "blend-out, the clip's root motion continues" : "the half's blend-in / intro: psync places it, the half is NOT released (ps37: this line said blend-out for every duel -hit pair since ps24)") : g_ps.vic_keep ? "dead, half kept" : psync_own_dead_now() ? "Death state before the kill" : "the pair's start turn: psync turns our victim body at the glide's rate (ps39)",
                 g_ps.lost[1] ? ", layer lost" : "", "", (unsigned long long)r,
                 __builtin_sqrtf(g_ps.off_p[k][0] * g_ps.off_p[k][0] + g_ps.off_p[k][2] * g_ps.off_p[k][2]));
        g_ps.own_drv = 1; g_ps.own_drv_n++;
    } else {
        mo_write(ent, &bf, MO_SRC("paired.drive_puppet"), 0);   // set-object-locator (winmm's wrapper)
        g_ps_pup[slot].drv++;
        memcpy(g_ps.put[k], t, 12); g_ps.put_ok[k] = 1;      // what we put (psync_place_log: moved by someone else since?)
    }
    if (k == 1) { memcpy(g_ps.last_put, t, 12); g_ps.last_put_ok = 1; }
}

// ---- travel clamp (v5-fb2: getting punched could travel a player into collision in the animation, so a check keeps them on the edge of the collision; and an out-of-bounds report: dlog3 116318-116672 / 90013-90205, Hospital ~255 13.7 -98: a duel
// finisher carried the victim into a wall and the attacker toward a 1 m drop, the attacker fell out of the map after the hand-off). Every paired half
// (duel hit pairs, pins, escapes, finishers, takedowns, executions, revives - attacker AND victim, our own body AND the puppets on our screen) moves on
// its clip's root motion with no character collision. Each frame, before the step is shown, the step is clipped against the collision edges found so
// far: static-world rays (mask 0x1b07: walls / props stop it, tall grass does not) from where the body is allowed to be, along the clip's wanted step,
// at 0.5 m and 1.1 m above the root, looking 0.4 m + 6 steps ahead (kicked this frame, read the next - the look-ahead covers the frame of latency), and
// a floor ray just ahead (no floor within 0.8 m below = a ledge). A hit becomes a stop plane at TC_R (TC_R_LOW for a knee-only hit: low cover the
// clips lean over) short of the surface; a body that already stands closer is never pushed out (the plane sits where it stands: it only cannot go
// further in). The part of the step into a plane is removed, the part along it stays (it slides). Hits on the other body (0.4 m round its root) are not
// collision. Our own body: set-object-locator on the clipped spot every frame the clip asks for more (the engine re-places it from the clip each frame),
// and the engine's player state is handed the last clipped spot (teleport-player) when the move ends. Every clamp is logged (clip, wanted vs allowed).
// t2r-no-travel-clamp.txt next to the exe = off.
#define TC_R 0.28f
#define TC_R_LOW 0.12f
#define TC_NPL 6
static struct {
    uint32_t uid;
    float a[2][3]; int a_ok[2];                       // where each half is allowed to be (last frame's output)
    float pn[2][TC_NPL][2], pd[2][TC_NPL]; int np[2], pi[2];   // stop planes: normal (into the obstacle, x/z), max dot(pos, n)
    uint64_t j[2][3]; float jo[2][3], jd[2][2], jlen[2]; int jon[2];   // pending rays: knee, chest, floor; origin, dir, length
    int corr[2], nlog; float cut_max[2], cut_sum[2]; float own_last[8]; int own_last_ok; int own_corr;
    // pair as one: each half's clip spot W (before the clamp) and the shift R the clamp wants for it; ONE shift D (the larger) moves BOTH halves, so the
    // authored relative placement of the two bodies is never changed by the clamp (A/B 178-dev1 stairs fist stomp, A 227986-228456: attacker puppet held 1.20 m,
    // our victim body 0.48 m, each on its own planes = the pair came apart on the victim's screen). t2r-no-pair-clamp.txt = the old per-body clamp.
    float W[2][2], R[2][2], t8[2][8], Dap[2][2]; int rv[2], tv[2], dap_ok[2]; uint64_t ents[2]; int owns[2];
    float Ds[2], Dd[2], osc; int n_in[2];              // ps34: the eased pair shift really applied, its last change, the summed reversals of it; frames a half stood in the pair's wall
} g_tc;
// ps34 (wall33 A [15892]-[16073], wall-throat-punch u001f579c: 'victim half (puppet) - wall 0.00 m ahead along -0.99 0.12: stop plane 0.00 m from the body',
// then 179 frames 'wanted step .. allowed 0.000 m, held 0.36-0.55 m off the clip's spot', the attacker shifted with it, 'sum 78.59 m'): slot 1's puppet stood
// 0.2 m BEHIND the wall face the pair is anchored on (its dodge replica had carried it through; on B its own body was 0.67 m in front, 'err 0.01 m'). The clip
// pulled it back out to the room side, the probe along that way hit the wall it stood in, and a plane 'at the body' kept it in there for the whole move.
//  1 a hit nearer than TC_R_LOW along a step that leads OUT of a wall pair's surface (toward its room side, the ap's forward) is the wall the body stands in:
//    never a stop plane (the clip brings the body out). t2r-tc-inside-old.txt = old.
//  2 the pair's shift D jumped whenever the two halves' wanted shifts crossed or a plane was added (D = the larger of the two, re-chosen every frame; A [15904]-
//    [15908] 'SNAP 0.18-0.22 m in 1 frame ... attacker half' on five frames running): the shift that is applied follows a GROWING hold at once (the body just does
//    not advance) and changes direction / lets go at no more than TC_D_STEP a frame. t2r-tc-ease-old.txt = old.
#define TC_D_STEP 0.03f   // [TUNING ps34] m a frame the applied pair shift may turn / shrink (1.8 m/s: a step, not a snap)
static int tc_inside_old(void) { static int v = -1; static uint64_t at; uint64_t n = GetTickCount64(); if (v < 0 || n - at > 3000) { at = n; v = GetFileAttributesA("t2r-tc-inside-old.txt") != INVALID_FILE_ATTRIBUTES; } return v; }
static int tc_ease_old(void) { static int v = -1; static uint64_t at; uint64_t n = GetTickCount64(); if (v < 0 || n - at > 3000) { at = n; v = GetFileAttributesA("t2r-tc-ease-old.txt") != INVALID_FILE_ATTRIBUTES; } return v; }
static int tc_pair_off(void) {
    static int off = -1; static uint64_t at; uint64_t n = GetTickCount64();
    if (off < 0 || n - at > 2000) { at = n; off = GetFileAttributesA("t2r-no-pair-clamp.txt") != INVALID_FILE_ATTRIBUTES; }
    return off;
}
static void tc_aps_write(int k, float tx, float tz);
static struct { uint32_t uid; uint8_t *inst; float base[3], S[2], lun[2][2]; int act[2], bad, n; } g_aps;   // ap shift (see tc_aps_begin)
static void tc_put(int k, const float *t8) {           // put half k's body on t8 (set-object-locator, same bookkeeping as the single-body clamp)
    if (g_tc.owns[k] && g_aps.act[k]) { tc_aps_write(k, t8[0], t8[2]); return; }   // our engine-placed body moves through its ap
    static psync_bf bfc;
    psync_bf_from_loc(&bfc, t8);
    mo_write(g_tc.ents[k], &bfc, MO_SRC("paired.tc_frame"), 0);
    if (g_tc.owns[k]) { memcpy(g_tc.own_last, t8, 32); g_tc.own_last_ok = 1; g_tc.own_corr = 1; if (k == 0 && g_ps.att_last_ok) memcpy(g_ps.att_last, t8, 32); }
    else { memcpy(g_ps.put[k], t8, 12); if (k == 1) memcpy(g_ps.last_put, t8, 12); }
}
static int tc_off(void) {
    static int off = -1; static uint64_t at; uint64_t n = GetTickCount64();
    if (off < 0 || n - at > 2000) { at = n; off = GetFileAttributesA("t2r-no-travel-clamp.txt") != INVALID_FILE_ATTRIBUTES; }
    return off;
}
static void tc_drain(int k) { for (int i = 0; i < 3; i++) if (g_tc.j[k][i]) { ray_t(g_tc.j[k][i]); g_tc.j[k][i] = 0; } g_tc.jon[k] = 0; }
static void tc_add_plane(int k, float nx, float nz, float d, const float *at, const char *what) {
    float cur = at[0] * nx + at[2] * nz;
    if (d < cur) d = cur;                                // never pushed out: it only cannot go further in
    for (int i = 0; i < g_tc.np[k]; i++)
        if (g_tc.pn[k][i][0] * nx + g_tc.pn[k][i][1] * nz > 0.94f) {
            float ci = at[0] * g_tc.pn[k][i][0] + at[2] * g_tc.pn[k][i][1], dd = ci + (d - cur);   // (close normals: one plane, the nearer surface)
            if (dd < g_tc.pd[k][i]) g_tc.pd[k][i] = dd < ci ? ci : dd;
            return;
        }
    int s = g_tc.np[k] < TC_NPL ? g_tc.np[k]++ : (g_tc.pi[k]++ % TC_NPL);
    g_tc.pn[k][s][0] = nx; g_tc.pn[k][s][1] = nz; g_tc.pd[k][s] = d;
    if (g_tc.nlog < 24 && (g_tc.nlog++, 1))
        xlog("travel clamp: u%08x %s half (%s) - %s %.2f m ahead along %.2f %.2f: stop plane %.2f m from the body", g_ps.uid, k ? "victim" : "attacker",
             (k ? g_ps.ent_vic : g_ps.ent_att) == SID_PLAYER ? "our body" : "puppet", what, (double)(d - cur), (double)nx, (double)nz, (double)(d - cur));
}
// ps34 (wall33 B [15788]-[15816], the same wall-throat-punch on the victim's own screen: stop planes 'wall 0.45 m ahead along 1.00 0.07', '0.21 m ahead along
// 0.85 0.52', '0.28 m ahead along 0.59 0.81', '0.22 m ahead along 0.81 -0.59' - four planes for ONE wall, each with the body's momentary step direction as its
// normal, so a step ALONG the wall was cut like a step into it: 40 clamped frames, 0.20 m off the clip): a hit on the wall pair's own surface (within 0.35 m of
// the ap's face, the step heading into it) becomes a plane with the WALL's normal (the ap's forward) - one plane, the body slides along it. 1 = added.
// t2r-tc-wallnormal-old.txt = the step direction as before.
static int tc_wall_plane(int k, float h, float R, const float *a, const char *what) {
    static int old = -1; static uint64_t at; uint64_t n = GetTickCount64();
    if (old < 0 || n - at > 3000) { at = n; old = GetFileAttributesA("t2r-tc-wallnormal-old.txt") != INVALID_FILE_ATTRIBUTES; }
    if (old || h < 0.0f || g_ps.kind != PS_CTXDOWN || !cd_wall_move(g_ps.move)) return 0;
    const float *q = g_ps.ap + 3;
    float fx = 2.0f * (q[0] * q[2] + q[3] * q[1]), fz = 1.0f - 2.0f * (q[0] * q[0] + q[1] * q[1]), fn = __builtin_sqrtf(fx * fx + fz * fz);
    if (fn < 0.5f) return 0;
    fx /= fn; fz /= fn;
    if (g_tc.jd[k][0] * fx + g_tc.jd[k][1] * fz > -0.3f) return 0;                    // not heading into the pair's wall
    float px = g_tc.jo[k][0] + g_tc.jd[k][0] * h, pz = g_tc.jo[k][2] + g_tc.jd[k][1] * h;
    if (__builtin_fabsf((px - g_ps.ap[0]) * fx + (pz - g_ps.ap[2]) * fz) > 0.35f) return 0;   // another surface (a corner, a prop): the old plane
    tc_add_plane(k, -fx, -fz, -(px * fx + pz * fz) - R, a, what);
    return 1;
}
// ps44 T1 (rec43a B wall-throat-punch u0104aabe, frames B 193.3-195.5: our victim body is DRAWN at the wall behind a crate - the authored spot - while the attacker's
// puppet throws its punches ~1 m out in the room; B.log 'victim root ... placed -0.17 0.98 (1.00 m) | err 0.80 m | our body by the engine', 'travel clamp ... attacker
// half (puppet) - 85 clamped frame(s), max 0.81 m off its clip', 'psync sync t=1000 att -0.55 1.31 vic -0.15 0.99 rel 0.32 -0.40' = by the LOCATORS the two halves
// were shifted together 0.75 m; [22161] 'pair snap check: our body moved 0.14 m since its last verified spot (.. 292.56 -> .. 292.70' = the next tick reads our body
// back on the clip spot the engine had given it the frame before (292.70 = that frame's wanted spot), not on our write (292.58)). While the half's layer plays the
// engine's align places our own body every frame and that is what is drawn; the clamp's set-object-locator on it does not show (inferred from the frames + that
// line, NOT measured in the engine). So the clamp held nothing on our body and its pair shift moved only the puppet = the pair came apart by exactly the clamp's hold.
// While our own body is placed by the engine (psync does not drive it, we live) the pair takes no stop planes and no clamp shift: both halves stay on the pair's
// placement. (A pair of two puppets / our psync-driven body is clamped as before.) t2r-tc-engbody-old.txt = old.
// ap shift (keep the animation of the walk but stop the travel at collision; dev10 cover-lift-n-slam A frames: the attacker clip's walk carried
// our legs into the tarp crate while 'travel clamp ... knee hit' planes were found but not applied - ps44 T1: while the pair's half plays, the engine's align places our
// own body from the clip every frame and a set-object-locator on it does not show). The align is the clip root on the half's apReference, which the engine keeps in the
// layer's anim instance (exe 0x1603070: layer +0x640 count, **(layer +0x638) -> 0x1614ae0 -> instance; the ap = BoundFrame at instance +0x10: +0x08 binding, +0x10 parent
// locator, +0x30 local pos, +0x40 local quat - 0x133db30 / 0x133da80). Shifting the LOCAL pos of that ap moves the drawn body with the clip still playing - the same
// thing the clamp's set-object-locator meant to do. The clamp's planes + pair shift D now apply to our engine-placed body through the ap (absolute: base + S, rebased
// when the engine writes the ap itself). Checked at the first frame against psync's ap (> 0.5 m apart = not our pair's instance: off for the pair).
// t2r-tc-apshift-off.txt = ps44 T1 (no cuts on our engine-placed body).
static int tc_aps_flag_off(void) { static int off = -1; static uint64_t at; uint64_t n = GetTickCount64(); if (off < 0 || n - at > 2000) { at = n; off = GetFileAttributesA("t2r-tc-apshift-off.txt") != INVALID_FILE_ATTRIBUTES; } return off; }
static uint8_t *tc_own_inst(void) {
    typedef uint8_t *(*fn_me)(void); typedef void *(*fn_layer)(void *); typedef uint8_t *(*fn_i)(void *);
    uint8_t *exe = (uint8_t *)GetModuleHandleW(NULL);
    uint8_t *proc = ((fn_me)VMA(0x180050390))();
    if (!proc || IsBadReadPtr(proc + 0x1b8, 8)) return NULL;
    uint8_t *ac = *(uint8_t **)(proc + 0x1b8);
    if (!ac || IsBadReadPtr(ac, 0x30)) return NULL;
    uint8_t *layer = ((fn_layer)(exe + 0x14440d0))(ac);
    if (!layer || IsBadReadPtr(layer + 0x638, 0x10) || !*(int *)(layer + 0x640)) return NULL;
    uint8_t *arr = *(uint8_t **)(layer + 0x638);
    if (!arr || IsBadReadPtr(arr, 8)) return NULL;
    uint8_t *a2 = *(uint8_t **)arr;
    if (!a2 || IsBadReadPtr(a2, 0x14)) return NULL;
    uint8_t *inst = ((fn_i)(exe + 0x1614ae0))(a2);
    if (!inst || IsBadWritePtr(inst + 0x10, 0x50)) return NULL;
    return inst;
}
static void tc_aps_vec_local(const uint8_t *inst, float dx, float dz, float *o) {   // world delta -> the ap's local frame (conj of the parent quat)
    const float *q = (const float *)(inst + 0x30);
    float qx = -q[0], qy = -q[1], qz = -q[2], qw = q[3];
    float n = qx * qx + qy * qy + qz * qz + qw * qw;
    if (!(n > 0.5f && n < 2.0f)) { o[0] = dx; o[1] = 0.0f; o[2] = dz; return; }
    float vx = dx, vy = 0.0f, vz = dz;
    float tx = 2.0f * (qy * vz - qz * vy), ty = 2.0f * (qz * vx - qx * vz), tz = 2.0f * (qx * vy - qy * vx);
    o[0] = vx + qw * tx + (qy * tz - qz * ty); o[1] = vy + qw * ty + (qz * tx - qx * tz); o[2] = vz + qw * tz + (qx * ty - qy * tx);
}
// is our own body (half k) moved through the ap this frame; sets g_aps.act[k]
static int tc_aps_begin(int k) {
    g_aps.act[k] = 0;
    if (tc_aps_flag_off() || g_ps.own_drv || psync_own_dead_now()) return 0;
    uint8_t *inst = tc_own_inst();
    if (!inst) return 0;
    float *lp = (float *)(inst + 0x40);
    if (g_aps.uid != g_ps.uid || g_aps.inst != inst) {
        int newpair = g_aps.uid != g_ps.uid;
        g_aps.uid = g_ps.uid; g_aps.inst = inst; memcpy(g_aps.base, lp, 12); g_aps.S[0] = g_aps.S[1] = 0.0f;
        if (newpair) {
            typedef const float *(*fn_loc)(void *, float *);
            static __attribute__((aligned(32))) uint8_t bf[0x60]; float b[16];
            memcpy(bf, inst + 0x10, 0x50);
            const float *w = ((fn_loc)((uint8_t *)GetModuleHandleW(NULL) + 0x133db30))(bf, b);
            float d = w ? __builtin_sqrtf((w[0] - g_ps.ap[0]) * (w[0] - g_ps.ap[0]) + (w[2] - g_ps.ap[2]) * (w[2] - g_ps.ap[2])) : 99.0f;
            g_aps.bad = !(d < 0.5f); g_aps.n = 0;
            xlog("travel clamp: u%08x our %s body - its anim instance's ap %.2f m from the pair's ap (%s)%s", g_ps.uid, k ? "victim" : "attacker", (double)d,
                 w ? "read" : "unreadable", g_aps.bad ? " - NOT our pair's instance: no ap shift for this pair (ps44 T1 rule)" : " - the clamp moves our body by shifting this ap (the clip keeps playing)");
        }
    } else {
        // the engine wrote the ap itself (its local pos is not base + our shift any more): rebase on its value
        float d0[3]; tc_aps_vec_local(inst, g_aps.S[0], g_aps.S[1], d0);
        float ex = lp[0] - (g_aps.base[0] + d0[0]), ey = lp[1] - (g_aps.base[1] + d0[1]), ez = lp[2] - (g_aps.base[2] + d0[2]);
        if (ex * ex + ey * ey + ez * ez > 0.0001f) { g_aps.base[0] = lp[0] - d0[0]; g_aps.base[1] = lp[1] - d0[1]; g_aps.base[2] = lp[2] - d0[2]; }
    }
    if (g_aps.bad) return 0;
    g_aps.act[k] = 1;
    return 1;
}
static void tc_aps_write(int k, float tx, float tz) {    // our body (half k) on tx / tz: S = target - the unshifted clip spot
    if (!g_aps.act[k] || !g_aps.inst || g_aps.inst != tc_own_inst()) return;
    float sx = tx - g_aps.lun[k][0], sz = tz - g_aps.lun[k][1];
    float ds = __builtin_sqrtf((sx - g_aps.S[0]) * (sx - g_aps.S[0]) + (sz - g_aps.S[1]) * (sz - g_aps.S[1]));
    if (ds < 0.0005f) return;
    float d[3]; tc_aps_vec_local(g_aps.inst, sx, sz, d);
    float *lp = (float *)(g_aps.inst + 0x40);
    lp[0] = g_aps.base[0] + d[0]; lp[1] = g_aps.base[1] + d[1]; lp[2] = g_aps.base[2] + d[2];
    if (g_aps.n++ < 12 || (g_aps.n % 30) == 0) xlog("travel clamp: u%08x our %s body - ap shift %.2f %.2f (%.2f m) t=%.0f ms: the clip plays on, the travel stops at the plane", g_ps.uid, k ? "victim" : "attacker", (double)sx, (double)sz, (double)__builtin_sqrtf(sx * sx + sz * sz), psync_ms() - g_ps.t0);
    g_aps.S[0] = sx; g_aps.S[1] = sz;
}
static int tc_eng44(void) {
    static int old = -1; static uint64_t at; uint64_t n = GetTickCount64();
    if (old < 0 || n - at > 2000) { at = n; old = GetFileAttributesA("t2r-tc-engbody-old.txt") != INVALID_FILE_ATTRIBUTES; }
    if (old || g_ps.own_drv || !(g_ps.ent_att == SID_PLAYER || g_ps.ent_vic == SID_PLAYER) || psync_own_dead_now()) return 0;
    static uint32_t lu;
    if (lu != g_ps.uid) { lu = g_ps.uid; xlog("travel clamp: u%08x our %s body is placed by the engine's align (psync does not drive it) - no stop planes / clamp shift for this pair, both halves stay on the pair's placement (ps44 T1; t2r-tc-engbody-old.txt = old)", g_ps.uid, g_ps.ent_vic == SID_PLAYER ? "victim" : "attacker"); }
    return 1;
}
static void tc_frame(int k) {
    if (k == 0) {                                        // once per frame (k 0 runs first): a new move = a fresh state
        if (g_tc.uid != g_ps.uid) { tc_drain(0); tc_drain(1); memset(&g_tc, 0, sizeof g_tc); g_tc.uid = g_ps.uid; }
    }
    uint64_t ent = k ? g_ps.ent_vic : g_ps.ent_att;
    int own = ent == SID_PLAYER, slot = k ? g_ps.vic : g_ps.att;
    g_tc.rv[k] = 0; g_tc.tv[k] = 0;
    if (!ent || tc_off() || g_ps.ended) { tc_drain(k); g_tc.a_ok[k] = 0; return; }
    // rec6 276.19 (A, 2h wall head-bonk): our attacker body released (ctxdown release, blend-out drive stopped) and back in locomotion / a new
    // swing - the engine no longer re-places it from the clip, so the pair's shift D written on it every frame ACCUMULATED (0.15 -> 0.26 m a frame, 38
    // frames, flung 8.6 m onto the crates). A released own attacker half is not clamped / shifted any more. t2r-tc-released-old.txt = the old clamp.
    if (own && k == 0 && g_ps.out_done[0] && !(g_ps.att_drive_until > psync_ms())) {
        static int ro = -1; static uint64_t rchk; if (ro < 0 || GetTickCount64() - rchk > 3000) { rchk = GetTickCount64(); ro = GetFileAttributesA("t2r-tc-released-old.txt") != INVALID_FILE_ATTRIBUTES; }
        if (!ro) {
            if (g_tc.a_ok[0]) { static int nlr; if (LOGCAP(nlr, 20)) xlog("travel clamp: u%08x our released attacker half - no clamp / pair shift on it any more (the engine moves it)", g_ps.uid); }
            // ps23 (rec13 B [16908] 'our released attacker half - no clamp / pair shift on it any more', then 69 frames later at the victim half's hand-off
            // [16977] 'our body handed to the engine at its last clipped spot 103.05 -0.96 308.94 (teleport-player; it read 1.82 m off it)' = SNAP 1.82 m [16978]):
            // tc_finish still held the released body's last CLAMPED spot and teleported the free, walking body back onto it. The release ends that record - the
            // blend-out's own hand-off (att_end_handoff) already gave the body to the engine. t2r-tc-finish-released-old.txt = old.
            if (g_tc.own_last_ok || g_tc.own_corr) {
                static int fo = -1; static uint64_t fchk; if (fo < 0 || GetTickCount64() - fchk > 3000) { fchk = GetTickCount64(); fo = GetFileAttributesA("t2r-tc-finish-released-old.txt") != INVALID_FILE_ATTRIBUTES; }
                if (!fo) { g_tc.own_last_ok = 0; g_tc.own_corr = 0; }
            }
            tc_drain(k); g_tc.a_ok[k] = 0; g_tc.rv[k] = 0; g_tc.tv[k] = 0; g_tc.R[k][0] = g_tc.R[k][1] = 0.0f; return;
        }
    }
    // (int100 under-truck pull-out was a buggy mess): the drag's whole point is the way OUT from under the vehicle - the clamp read the truck as a
    // chest-height wall and held all three bodies (A: our attacker 0.86 m, the victim puppet 1.46 m; B: our victim 1.36 m off the clip, 97 frames). No clamp on
    // pull-out pairs.
    if (g_ps.kind == PS_CTXDOWN && pul_drag_move(g_ps.move)) { tc_drain(k); g_tc.a_ok[k] = 0; return; }
    if (!own && (slot < 0 || slot >= T2R_MAX_PEERS || !g_ps_pup[slot].on || g_ps_pup[slot].h != ent)) { tc_drain(k); g_tc.a_ok[k] = 0; return; }   // the net owns the puppet
    if (psync_dead(ent) && !(k && g_ps.vic_keep) && !(own && g_ps.own_drv)) { tc_drain(k); g_tc.a_ok[k] = 0; return; }   // death / ragdoll owns the body
    float lb[16]; const float *l = psync_loc(ent, lb);
    if (!l || !ps_loc_ok(l)) return;
    float lun16[16]; int aps = own && tc_aps_begin(k);
    if (aps) { memcpy(lun16, l, sizeof lun16); lun16[0] -= g_aps.S[0]; lun16[2] -= g_aps.S[1]; l = lun16; g_aps.lun[k][0] = l[0]; g_aps.lun[k][1] = l[2]; }   // (the clip's own spot: the drawn one minus our ap shift)
    if (!g_tc.a_ok[k]) { memcpy(g_tc.a[k], l, 12); g_tc.a_ok[k] = 1; tc_drain(k); }
    float *a = g_tc.a[k];
    if (__builtin_fabsf(l[1] - a[1]) > 1.0f || (l[0] - a[0]) * (l[0] - a[0]) + (l[2] - a[2]) * (l[2] - a[2]) > 1.5f * 1.5f) {   // a teleport / snap (not root motion): start over there
        memcpy(a, l, 12); g_tc.np[k] = 0; tc_drain(k);
    }
    // last frame's rays -> stop planes
    if (g_tc.jon[k]) {
        float ob[16]; const float *ol = psync_loc(k ? g_ps.ent_att : g_ps.ent_vic, ob);
        float hk = -1.0f, hc = -1.0f;
        for (int i = 0; i < 2; i++) {
            g_ray_err = 0; float t = g_tc.j[k][i] ? ray_t(g_tc.j[k][i]) : -2.0f; g_tc.j[k][i] = 0;
            if (g_ray_err || !(t >= 0.01f && t < 0.995f)) continue;
            float hx = g_tc.jo[k][0] + g_tc.jd[k][0] * g_tc.jlen[k] * t, hz = g_tc.jo[k][2] + g_tc.jd[k][1] * g_tc.jlen[k] * t;
            if (ol && ps_loc_ok(ol) && (hx - ol[0]) * (hx - ol[0]) + (hz - ol[2]) * (hz - ol[2]) < 0.40f * 0.40f) continue;   // the other body, not collision
            if (i == 0) hk = t * g_tc.jlen[k]; else hc = t * g_tc.jlen[k];
        }
        float o_d = g_tc.jo[k][0] * g_tc.jd[k][0] + g_tc.jo[k][2] * g_tc.jd[k][1];
        float R = g_ps.kind == PS_CTXDOWN && cd_wall_move(g_ps.move) ? 0.10f : TC_R;   // (a wall pair's ap IS the wall: its victim spot is authored ~0.2 m off it)
        int inwall = 0;
        if ((hc >= 0.0f || hk >= 0.0f) && g_ps.kind == PS_CTXDOWN && cd_wall_move(g_ps.move) && !tc_inside_old()) {
            const float *q = g_ps.ap + 3;      // ap forward = q * (0,0,1): out of the wall (wallho_arm)
            float fx = 2.0f * (q[0] * q[2] + q[3] * q[1]), fz = 1.0f - 2.0f * (q[0] * q[0] + q[1] * q[1]), fn = __builtin_sqrtf(fx * fx + fz * fz);
            float hm = hc >= 0.0f && (hk < 0.0f || hc < hk) ? hc : hk;
            if (fn > 0.5f && hm < TC_R_LOW && (g_tc.jd[k][0] * fx + g_tc.jd[k][1] * fz) / fn > 0.3f) {
                inwall = 1;
                if (g_tc.n_in[k]++ < 3 || (g_tc.n_in[k] % 30) == 0) xlog("travel clamp: u%08x %s half (%s) stands in the pair's wall (hit %.2f m along its way out, %.2f %.2f) - no stop plane, its clip brings it out to the room side (frame %d of it; ps34)",
                    g_ps.uid, k ? "victim" : "attacker", own ? "our body" : "puppet", (double)hm, (double)g_tc.jd[k][0], (double)g_tc.jd[k][1], g_tc.n_in[k]);
            }
        }
        if (inwall) { }
        else if (hc >= 0.0f) { if (!tc_wall_plane(k, hc, R, a, "the pair's own wall (its normal)")) tc_add_plane(k, g_tc.jd[k][0], g_tc.jd[k][1], o_d + hc - R, a, hk >= 0.0f ? "wall" : "wall (chest height)"); }
        else if (hk >= 0.0f) {
            // cluster D (animations broke near walls and bushes, different surfaces: 'low obstacle (knee height only) 0.00 m ahead ... stop plane 0.00 m from the body' on BOTH
            // halves of u0106b0d8, 10+ pairs per match in Bookstore / Capitol Hill): a knee-only hit that close is clutter the body already stands in (a bush, a plant, a box edge) - a plane there
            // freezes the whole pair in place while its clip plays. Not a stop plane. Real low cover is still stopped by the chest-height rays, by the engine's controller (our body) and
            // by every farther knee hit. t2r-tc-touch-old.txt = the old plane.
            static int told = -1; static uint64_t tchk; if (told < 0 || GetTickCount64() - tchk > 3000) { tchk = GetTickCount64(); told = GetFileAttributesA("t2r-tc-touch-old.txt") != INVALID_FILE_ATTRIBUTES; }
            if (!told && hk < TC_R_LOW + 0.13f) { static int nlt; if (LOGCAP(nlt, 30)) xlog("travel clamp: u%08x %s half - a knee-height hit %.2f m ahead is clutter the body already touches: no stop plane (the pair keeps moving)", g_ps.uid, k ? "victim" : "attacker", (double)hk); }
            else tc_add_plane(k, g_tc.jd[k][0], g_tc.jd[k][1], o_d + hk - TC_R_LOW, a, "low obstacle (knee height only)");
        }
        if (g_tc.j[k][2]) {
            g_ray_err = 0; float t = ray_t(g_tc.j[k][2]); g_tc.j[k][2] = 0;
            if (!g_ray_err && (t < 0.0f || t > 0.995f) && hc < 0.0f && hk < 0.0f && !ps_rays_blind())
                tc_add_plane(k, g_tc.jd[k][0], g_tc.jd[k][1], o_d + TC_R * 0.5f, a, "ledge (no floor within 0.8 m below)");
        }
        g_tc.jon[k] = 0;
    }
    // the clip's wanted spot, clipped against the planes (slides along them)
    // pair shift: our engine-driven body (psync does not place it) gets the pair's sliding shift D(t) on top of the clip's spot, every frame, by the same
    // set-object-locator the clamp uses (the engine re-places the body from the clip each frame, so it never accumulates); puppets / psync-placed bodies have D in their placement
    float wsh[2] = {0.0f, 0.0f};
    if (own && !g_ps.own_drv) { wsh[0] = g_ps.wD[0]; wsh[1] = g_ps.wD[1]; }
    float wx = l[0] + wsh[0], wz = l[2] + wsh[1], sx = wx - a[0], sz = wz - a[2], step = __builtin_sqrtf(sx * sx + sz * sz);
    float cx = wx, cz = wz;
    int eng44 = (g_aps.act[0] || g_aps.act[1]) ? 0 : tc_eng44();   // ps44 T1: our engine-placed body in the pair - no plane cuts on either half (unless its ap carries the cut)
    for (int pass = 0; pass < 2 && !eng44; pass++)
        for (int i = 0; i < g_tc.np[k]; i++) {
            float pen = cx * g_tc.pn[k][i][0] + cz * g_tc.pn[k][i][1] - g_tc.pd[k][i];
            if (pen > 0.0f) { cx -= g_tc.pn[k][i][0] * pen; cz -= g_tc.pn[k][i][1] * pen; }
        }
    float cut = __builtin_sqrtf((cx - wx) * (cx - wx) + (cz - wz) * (cz - wz));
    if (!tc_pair_off()) {
        // pair as one: this half's wanted shift R_k; the pair moves by the larger of the two (the other half's is last frame's while k = 0, fresh at k = 1;
        // at k = 1 the attacker body is re-placed when the final shift differs from the one it got)
        g_tc.W[k][0] = wx; g_tc.W[k][1] = wz; g_tc.R[k][0] = cx - wx; g_tc.R[k][1] = cz - wz; g_tc.rv[k] = 1;
        memcpy(g_tc.t8[k], l, 32); g_tc.t8[k][3] = 1.0f; g_tc.ents[k] = ent; g_tc.owns[k] = own; g_tc.tv[k] = 1;
        const float *Rb = g_tc.R[k];
        const float *Ro = g_tc.R[1 - k];
        float mb = Rb[0] * Rb[0] + Rb[1] * Rb[1], mo = Ro[0] * Ro[0] + Ro[1] * Ro[1];
        float D[2] = {Rb[0], Rb[1]};
        if (g_tc.rv[1 - k] && mo > mb) { D[0] = Ro[0]; D[1] = Ro[1]; }
        if (!tc_ease_old()) {                              // ps34: the applied shift (see TC_D_STEP)
            float tl = __builtin_sqrtf(D[0] * D[0] + D[1] * D[1]), sl = __builtin_sqrtf(g_tc.Ds[0] * g_tc.Ds[0] + g_tc.Ds[1] * g_tc.Ds[1]);
            float n0 = g_tc.Ds[0], n1 = g_tc.Ds[1];
            if (tl >= sl && (sl < 0.004f || D[0] * g_tc.Ds[0] + D[1] * g_tc.Ds[1] >= 0.94f * tl * sl)) { n0 = D[0]; n1 = D[1]; }   // a growing hold, same way: at once
            else { float ex = D[0] - g_tc.Ds[0], ez = D[1] - g_tc.Ds[1], el = __builtin_sqrtf(ex * ex + ez * ez), mxs = TC_D_STEP * 0.5f;   // (two halves a frame)
                   if (el > mxs) { ex *= mxs / el; ez *= mxs / el; } n0 += ex; n1 += ez; }
            float cx_ = n0 - g_tc.Ds[0], cz_ = n1 - g_tc.Ds[1];
            if (cx_ * g_tc.Dd[0] + cz_ * g_tc.Dd[1] < 0.0f) g_tc.osc += __builtin_sqrtf(cx_ * cx_ + cz_ * cz_);          // the shift's change reversed: the measure of a shake
            if (cx_ * cx_ + cz_ * cz_ > 1e-8f) { g_tc.Dd[0] = cx_; g_tc.Dd[1] = cz_; }
            g_tc.Ds[0] = n0; g_tc.Ds[1] = n1; D[0] = n0; D[1] = n1;
        }
        cx = wx + D[0]; cz = wz + D[1];
        cut = __builtin_sqrtf(D[0] * D[0] + D[1] * D[1]);
        g_tc.Dap[k][0] = D[0]; g_tc.Dap[k][1] = D[1]; g_tc.dap_ok[k] = 1;
        if (k == 1 && g_tc.tv[0]) {                       // the attacker half already placed this frame with its D: bring it onto the final one
            float dd = __builtin_sqrtf((g_tc.Dap[0][0] - D[0]) * (g_tc.Dap[0][0] - D[0]) + (g_tc.Dap[0][1] - D[1]) * (g_tc.Dap[0][1] - D[1]));
            if (dd > 0.004f) {
                float t0[8]; memcpy(t0, g_tc.t8[0], 32); t0[0] = g_tc.W[0][0] + D[0]; t0[2] = g_tc.W[0][1] + D[1];
                tc_put(0, t0); g_tc.Dap[0][0] = D[0]; g_tc.Dap[0][1] = D[1];
                if (g_tc.a_ok[0]) { g_tc.a[0][0] = t0[0]; g_tc.a[0][2] = t0[2]; }
            }
        }
    }
    float mvd = __builtin_sqrtf((cx - l[0]) * (cx - l[0]) + (cz - l[2]) * (cz - l[2]));     // how far from where the engine put the body (clamp + shift)
    if (cut > 0.004f || mvd > 0.004f) {
        float t8[8]; memcpy(t8, l, 32); t8[0] = cx; t8[2] = cz; t8[3] = 1.0f;
        g_tc.ents[k] = ent; g_tc.owns[k] = own;
        tc_put(k, t8);
        float as = __builtin_sqrtf((cx - a[0]) * (cx - a[0]) + (cz - a[2]) * (cz - a[2]));
        if (cut > 0.004f && (g_tc.corr[k]++ < 10 || cut > g_tc.cut_max[k] + 0.05f))
            xlog("travel clamp: u%08x %s half %s (%s) t=%.0f ms - wanted step %.3f m, allowed %.3f m, held %.2f m off the clip's spot (%.2f %.2f %.2f -> %.2f %.2f)%s",
                 g_ps.uid, k ? "victim" : "attacker", psync_name(k ? g_ps.vic_sid : g_ps.att_sid), own ? "our body" : "puppet", psync_ms() - g_ps.t0,
                 (double)step, (double)as, (double)cut, (double)wx, (double)l[1], (double)wz, (double)cx, (double)cz, tc_pair_off() ? "" : " [pair shift: both halves]");
        if (cut > g_tc.cut_max[k]) g_tc.cut_max[k] = cut;
        g_tc.cut_sum[k] += cut;
    } else if (own) { memcpy(g_tc.own_last, l, 32); g_tc.own_last_ok = 1; }
    // this frame's rays along the wanted step (read next frame)
    if (step > 0.003f && !g_tc.jon[k]) {
        float dx = sx / step, dz = sz / step, len = 0.40f + 6.0f * (step < 0.15f ? step : 0.15f);
        float o[3] = {cx, l[1], cz};
        float k0[3] = {o[0], o[1] + 0.5f, o[2]}, k1[3] = {o[0] + dx * len, o[1] + 0.5f, o[2] + dz * len};
        float c0[3] = {o[0], o[1] + 1.1f, o[2]}, c1[3] = {k1[0], o[1] + 1.1f, k1[2]};
        float fa[3] = {o[0] + dx * (TC_R + 0.10f), o[1] + 0.6f, o[2] + dz * (TC_R + 0.10f)}, fb[3] = {fa[0], o[1] - 0.8f, fa[2]};
        g_tc.j[k][0] = world_ray_kick_m(k0, k1, ent, 0x1b07);
        g_tc.j[k][1] = world_ray_kick_m(c0, c1, ent, 0x1b07);
        g_tc.j[k][2] = world_ray_kick_m(fa, fb, ent, 0x1b07);
        memcpy(g_tc.jo[k], o, 12); g_tc.jd[k][0] = dx; g_tc.jd[k][1] = dz; g_tc.jlen[k] = len; g_tc.jon[k] = 1;
    }
    if (aps) tc_aps_write(k, cx, cz);                    // (every frame: also back to 0 when the clamp lets go)
    a[0] = cx; a[1] = l[1]; a[2] = cz;
}
static void tc_finish(const char *why) {                // psync_finish: our own clipped body handed to the engine's player state; the summary
    if (g_tc.uid != g_ps.uid || !g_ps.uid) return;
    for (int k = 0; k < 2; k++) {
        if (g_tc.corr[k]) xlog("travel clamp: u%08x %s half (%s) - %d clamped frame(s), max %.2f m off its clip, sum %.2f m (%s)", g_ps.uid, k ? "victim" : "attacker",
                               (k ? g_ps.ent_vic : g_ps.ent_att) == SID_PLAYER ? "our body" : "puppet", g_tc.corr[k], (double)g_tc.cut_max[k], (double)g_tc.cut_sum[k], why);
        tc_drain(k);
    }
    // ps34 self-test: one line per wall / cover pair (and per pair the clamp touched) - the next recording proves the fit
    if ((g_ps.kind == PS_CTXDOWN && cd_wall_move(g_ps.move)) || g_tc.corr[0] || g_tc.corr[1] || g_tc.n_in[0] || g_tc.n_in[1]) {
        int bad = g_tc.corr[0] > 5 || g_tc.corr[1] > 5 || g_tc.cut_max[0] > 0.10f || g_tc.cut_max[1] > 0.10f;
        xlog("wall fit: u%08x role %d move %llx - max off-clip %.2f m (attacker) / %.2f m (victim), clamped frames %d / %d, oscillation %.2f m, frames in the wall %d / %d (%s)",
             g_ps.uid, g_ps.role, (unsigned long long)g_ps.move, (double)g_tc.cut_max[0], (double)g_tc.cut_max[1], g_tc.corr[0], g_tc.corr[1], (double)g_tc.osc, g_tc.n_in[0], g_tc.n_in[1], why);
        if (bad) xlog("wall fit: WARNING u%08x - the pair did not fit in front of its surface (clamped frames > 5 or off-clip > 0.10 m): its anchor / start check let it start too close", g_ps.uid);
    }
    if (g_tc.own_corr && g_tc.own_last_ok && !psync_dead(SID_PLAYER)) {
        float b[16]; const float *l = psync_loc(SID_PLAYER, b);
        float d = l ? __builtin_sqrtf((l[0] - g_tc.own_last[0]) * (l[0] - g_tc.own_last[0]) + (l[2] - g_tc.own_last[2]) * (l[2] - g_tc.own_last[2])) : -1.0f;
        // ps43 P1 (rec42a B [20895] 'travel clamp: ... our body handed to the engine at its last clipped spot (teleport-player; it read 0.64 m off it)', [20896] 'SNAP slot 0
        // 0.64 m ... (paired.tc_finish)'): the move ended inside our released attacker half's blend-out drive, so the 'released' reset in tc_frame had not run and the
        // record was the drive's last spot. A RELEASED attacker body is the engine's: this hand-over may not move it more than PS_TCF_MAX_M - further, it is skipped.
        // (An unreleased / victim body keeps the hand-over: its clipped spot is the wall edge the clamp held it on.) t2r-tc-finish-far-old.txt = old.
#define PS_TCF_MAX_M 0.05f    // m (the lead's limit)
        int rel43 = g_ps.role == 1 && g_ps.ent_att == SID_PLAYER && g_ps.out_done[0] && d > PS_TCF_MAX_M && GetFileAttributesA("t2r-tc-finish-far-old.txt") == INVALID_FILE_ATTRIBUTES;
        if (l && d > 0.08f && d < 3.0f && rel43)
            xlog("travel clamp: u%08x our released attacker body reads %.2f m off its last clipped spot at the move's end - NOT teleported (> %.2f m; it stays where the engine has it; ps43 P1)", g_ps.uid, (double)d, (double)PS_TCF_MAX_M);
        if (l && d > 0.08f && d < 3.0f && !rel43) {
            float p[3] = {g_tc.own_last[0], l[1], g_tc.own_last[2]};
            mo_teleport(p, l + 4, MO_SRC("paired.tc_finish"), 0);
            xlog("travel clamp: u%08x our body handed to the engine at its last clipped spot %.2f %.2f %.2f (teleport-player; it read %.2f m off it)", g_ps.uid, p[0], p[1], p[2], d);
        }
    }
    memset(&g_tc, 0, sizeof g_tc);
}

// ---- wire
// ---- pair shift on the wire / per frame (pairshift.c has the planner). Trailer after the 84-byte START: 'W' 'S', flags (bit0 dynamic), nk, tend in 10 ms (u16),
// then PWS_NK x (dx, dz) int16 mm = S_k ABSOLUTE (the wire ap is already moved by S_0 = the start shift). 6 + 24 bytes.
#define PWS_TRL (6 + PWS_NK * 4)
static size_t pws_trailer(uint8_t *o) {
    o[0] = 'W'; o[1] = 'S'; o[2] = (uint8_t)(g_ps.wsh_dyn ? 1 : 0); o[3] = PWS_NK;
    uint16_t te = (uint16_t)(g_ps.wtend * 100.0f > 65000.0f ? 65000.0f : g_ps.wtend * 100.0f); memcpy(o + 4, &te, 2);
    for (int k = 0; k < PWS_NK; k++) for (int c = 0; c < 2; c++) { float v = g_ps.wS[k][c] * 1000.0f; int16_t m = (int16_t)(v > 32000.0f ? 32000.0f : v < -32000.0f ? -32000.0f : v); memcpy(o + 6 + (k * 2 + c) * 2, &m, 2); }
    return PWS_TRL;
}
static struct { uint32_t uid; int ok, dyn; float S[PWS_NK][2], tend; } g_pws_rx;     // the trailer of the START being handled
static void pws_trailer_read(uint32_t uid, const uint8_t *b, uint64_t len) {
    g_pws_rx.ok = 0;
    if (len < sizeof(psync_wire) + PWS_TRL || b[sizeof(psync_wire)] != 'W' || b[sizeof(psync_wire) + 1] != 'S' || b[sizeof(psync_wire) + 3] != PWS_NK) return;
    const uint8_t *o = b + sizeof(psync_wire);
    uint16_t te; memcpy(&te, o + 4, 2);
    for (int k = 0; k < PWS_NK; k++) for (int c = 0; c < 2; c++) { int16_t m; memcpy(&m, o + 6 + (k * 2 + c) * 2, 2); g_pws_rx.S[k][c] = (float)m / 1000.0f; }
    g_pws_rx.uid = uid; g_pws_rx.dyn = o[2] & 1; g_pws_rx.tend = (float)te / 100.0f; g_pws_rx.ok = 1;
}
// D(t) = S(t) - S_0: Catmull-Rom through the keys over the move time / tend (clamped at the ends). Both screens use only the keys and the shared move clock.
static void pws_D(float *d) {
    d[0] = d[1] = 0.0f;
    if (!g_ps.wsh_ok || !g_ps.wsh_dyn || g_ps.wtend < 0.05f || g_ps.nseg > 1) return;
    float u = (float)((psync_ms() - g_ps.t0) / 1000.0) / g_ps.wtend;
    u = u < 0.0f ? 0.0f : u > 1.0f ? 1.0f : u;
    float x = u * (float)(PWS_NK - 1); int i = (int)x; if (i > PWS_NK - 2) i = PWS_NK - 2;
    float f = x - (float)i, f2 = f * f, f3 = f2 * f;
    for (int c = 0; c < 2; c++) {
        float p0 = g_ps.wS[i > 0 ? i - 1 : 0][c], p1 = g_ps.wS[i][c], p2 = g_ps.wS[i + 1][c], p3 = g_ps.wS[i + 2 < PWS_NK ? i + 2 : PWS_NK - 1][c];
        float v = 0.5f * ((2.0f * p1) + (-p0 + p2) * f + (2.0f * p0 - 5.0f * p1 + 4.0f * p2 - p3) * f2 + (-p0 + 3.0f * p1 - 3.0f * p2 + p3) * f3);
        d[c] = v - g_ps.wS[0][c];
    }
}
static void psync_fill(psync_wire *wp, int op, int resend) {
    psync_wire w;
    memset(&w, 0, sizeof w);
    w.op = (uint8_t)op; w.ver = 1; w.kind = (uint8_t)g_ps.kind; w.flags = (uint8_t)g_ps.flags;
    w.att = (uint8_t)g_ps.att; w.vic = (uint8_t)g_ps.vic; w.pair = (uint8_t)g_ps.pair; w.resend = (uint8_t)resend;
    w.uid = g_ps.uid; w.att_clip = g_ps.att_sid; w.vic_clip = g_ps.vic_sid;
    memcpy(w.ap, g_ps.ap, sizeof w.ap);
    w.kill_s = g_ps.kill_s; w.dur_s = g_ps.dur_s;
    double t = psync_ms() - g_ps.t0;
    w.sent_ms = t > 0 ? (uint32_t)t : 0;
    w.weapon = g_ps.weapon; w.move = g_ps.move;
    *wp = w;
}
static void psync_send(int op, int resend, uint8_t to) {
    if (!g_send_tramp) return;
    psync_wire w;
    psync_fill(&w, op, resend);
    uint8_t buf[sizeof w + PWS_TRL];
    memcpy(buf, &w, sizeof w);
    size_t n = sizeof w;
    if (op == PS_OP_START && g_ps.wsh_ok && g_ps.uid == w.uid) n += pws_trailer(buf + sizeof w);     // the shift profile after the 84 bytes (older builds ignore the extra bytes)
    g_send_tramp(MSG_PSYNC, buf, n, to);
}
// the NOACK ABORT went out ONCE; on a lossy link (measured 12-22 %) a lost ABORT left the victim playing a move the attacker had
// cut. It now goes out 3 times (0 / 60 / 150 ms, like the hit copies): the first at once, two more from this queue after the g_ps state is gone.
static struct { psync_wire w; double at[2]; int n; } g_ps_abq;
static void psync_abq_tick(double now) {
    for (int i = 0; i < g_ps_abq.n; i++) {
        if (!g_ps_abq.at[i] || now < g_ps_abq.at[i]) continue;
        g_ps_abq.at[i] = 0;
        if (g_send_tramp) g_send_tramp(MSG_PSYNC, (uint8_t *)&g_ps_abq.w, sizeof g_ps_abq.w, 0xff);
    }
}
static float psync_oneway(int slot) {
    return slot >= 0 && slot < T2R_MAX_PEERS && g_ps_rtt[slot] > 0.0f ? g_ps_rtt[slot] * 0.5f : PS_DEFAULT_ONEWAY;
}

static int cd_chain_of(uint64_t move, uint64_t *att, uint64_t *vic, float *spd, float *cut, int max);   // ctxdown.c: the segments of a takedown (0 = not a chain)
// (revive animations swapped with execution ones): one client answered 4.00 / 3.93 / 3.73 / 3.87 s for the revive carriers (baked 1.47 /
// 3.60 / 1.00 s; every other client of the same build answered the baked lengths) - its carrier clips were another set's (execution clips), so as a bystander it
// saw the reviver stand and the revived roll, then a grapple, while the move's chain on the other clients was a kneel / give / stand-up. Every ext-side table
// (carrier names, the move's timing, the psync chain) is the build's own, so a client whose carriers answer another length than the baked clip plays a wrong
// animation under the right name. carrier_dur.h (generated with the carrier headers) has the baked length of every carrier clip: such a move is not played on
// that client (the bodies keep their net pose, the same path as "clip not loaded"), logged once per carrier with both lengths.
#include "carrier_dur.h"
static int ps_carrier_len_bad(uint64_t ent, uint64_t sid, const char *what) {
    static uint64_t hs[sizeof CARRIER_DUR / sizeof *CARRIER_DUR];
    static int init;
    const int n = (int)(sizeof CARRIER_DUR / sizeof *CARRIER_DUR);
    if (!init) { for (int i = 0; i < n; i++) hs[i] = fnv64_rt(CARRIER_DUR[i].name); init = 1; }
    for (int i = 0; i < n; i++) {
        if (hs[i] != sid) continue;
        float got = psync_dur(ent, sid), want = CARRIER_DUR[i].dur, tol = want * 0.03f > 0.06f ? want * 0.03f : 0.06f;
        if (got <= 0.0f || (got > want - tol && got < want + tol)) return 0;      // (0 = not loaded: the caller's own check)
        static int nl; if (LOGCAP(nl, 12)) xlog("psync: carrier %s (%s) answers %.2f s here, the build baked %.2f s - this install's carrier pak is not the build's (stale / foreign clip under that name): the move is not played on this client", CARRIER_DUR[i].name, what, got, want);
        return 1;
    }
    return 0;                                                                        // not a baked carrier (the game's own clip)
}
// The attacker half on a PUPPET starts with a cut (animate_ blend-in 0), not the move's 0.3-1.3 s blend-in. A/B logs (A 25487, Houses 56927,
// 57242, "backpack on the floor"): the puppet's skeleton is at its locator (head / chest / pelvis 0.00 m over it, "pose pop (collapse)"
// 0.91 -> 0.00) in the first frame after the half starts in 14 of 22 puppet attacker starts, it grows back over 0.15-0.5 s in 10 of them, and in
// 4 of them it never does until the puppet is released (phase, replay / root counters, locator placement and every layer of the anim control
// read exactly as in the starts that play fine). A puppet is posed by winmm's replay, not by its NPC graph (re/puppet-jitter.md), so when the half
// takes it over the graph starts from a state it has not evaluated for minutes: animate_'s blend-in is a state transition away from that stale
// state, and a transition fades the new pose in from the old state's pose = nothing (the own body, whose graph always runs, and lying victims,
// whose graph already plays a script clip, never do it). Blend-in 0 is the instant transition: the half is at full weight in its first frame.
// The position / yaw glide onto the authored spot is the locator drive's (g_ps.drive_bl), not animate_'s. t2r-no-pup-cut-start.txt = the old blend-in.
static int ps_dc(void);
#define DTL_PUP_XFADE 0.18f        // s: a duel pair's attacker half crossfades in on the puppet (its graph is live: our predicted swing replica plays there)
static float ps_pup_att_blend(void) {
    FILE *f = exe_side_open("t2r-no-pup-cut-start.txt", "r");
    if (f) { fclose(f); return -1.0f; }
    // (B went from dodge to counter attack smoothly, but on A's POV the counter cut into the haymaker): a dodge counter's attacker
    // puppet was just playing OUR duck clip (mdg_puppet_dodge) - its graph is live, not the stale replay state the cut guards against - so it blends
    // from the duck into the counter like the attacker's own body does
    if (ps_dc() && g_ps.att >= 0 && g_ps.att < T2R_MAX_PEERS && g_mdg_pup_anim_ms[g_ps.att] && GetTickCount64() - g_mdg_pup_anim_ms[g_ps.att] < 2500 &&
        GetFileAttributesA("t2r-dc-pup-cut.txt") == INVALID_FILE_ATTRIBUTES) {
        xlog("psync: u%08x attacker half %s on slot %d's puppet blends in over %.2f s from its dodge clip (live graph)", g_ps.uid, psync_name(g_ps.att_sid), g_ps.att, 0.35);
        return 0.35f;                                                                // (= PS_DC_IN)
    }
    // duel timeline (160 ms RTT clips: the opponent's body popped when its -hit pair started): a duel pair's attacker half crossfades in. The
    // puppet's graph is live here - melee_duel_tl.c dtl_pred_swing started the swing clip on it from the SWING message - not the stale replay state the
    // cut guards against (the same reasoning as the dodge counter's 0.35 s above). GUESS until A/B shows no 'pose pop (collapse)' on these starts.
    // ps45 prone (a recording: the grapple "pops" in; SP recorder ep 5 / ep 8, re/review/pullout-1031/sp-pullout-ep5-ep8.log: the struggle layer ramps in 0 -> 1 over
    // 0.50 s smoothstep on top of the drag's last frame, both roots still): a pull-out pair's attacker half on the puppet (the victim's screen) crossfades in over SP's
    // time instead of the cut. Its graph is live (the intro / the previous pull-out pair plays on it), the reasoning of the dodge counter / duel pair above.
    // t2r-pullout-spblend-off.txt = the old cut (pul_ps_xfade answers 0).
    if (g_ps.kind == PS_CTXDOWN) {
        float px = pul_ps_xfade(g_ps.move);
        if (px > 0.0f) { xlog("psync: u%08x pull-out pair attacker half %s on slot %d's puppet crossfades in over %.2f s (SP's transition; ps45 prone, t2r-pullout-spblend-off.txt = the cut)", g_ps.uid, psync_name(g_ps.att_sid), g_ps.att, px); return px; }
    }
    // (a recording): a pin blow's attacker half on the puppet of a pair we only watch, with the MDPO_BYST windup replica standing on the contact frame: the same
    // short crossfade as the victim's screen (mct_pup_blend 0.05 s), not fix1116c's 0.30 s / dtl's 0.18 s. t2r-no-pin-byst-windup.txt = off.
    if (g_ps.role == 3 && g_ps.kind == PS_CTXDOWN && mpn_byst_pair(g_ps.move) && mpn_byst_replica(g_ps.att)) {
        static int nlr; if (LOGCAP(nlr, 100)) xlog("psync: u%08x pin attacker half %s on slot %d's puppet (role 3): its windup replica stands on the contact frame - crossfade 0.05 s (not %.2f s)", g_ps.uid, psync_name(g_ps.att_sid), g_ps.att, (double)DTL_PUP_XFADE);
        return 0.05f;
    }
    if (g_ps.kind == PS_CTXDOWN && mdu_move(g_ps.move) && dtl_on()) {
        if (GetFileAttributesA("t2r-dtl-pup-cut.txt") == INVALID_FILE_ATTRIBUTES) {
            float xb = mct_pup_blend(DTL_PUP_XFADE);   // melee_duel_contact.c (round 2): 0.05 s when the replica stands on its contact frame - the -hit's fist lands at the impact
            float xs = sptl_pup_att_blend(DTL_PUP_XFADE);   // (sptl: short when the replica sat on its contact frame)
            if (xs < xb) xb = xs;
            if (xb == DTL_PUP_XFADE) xlog("dtl: u%08x duel pair attacker half %s on slot %d's puppet crossfades in over %.2f s (no cut; t2r-dtl-pup-cut.txt = the old cut)", g_ps.uid, psync_name(g_ps.att_sid), g_ps.att, DTL_PUP_XFADE);
            return xb;
        }
        dtl_cut("duel pair attacker half", (uint32_t)g_ps.att, g_ps.att_sid, "t2r-dtl-pup-cut.txt: the old cut start");
    }
    xlog("psync: u%08x attacker half %s on slot %d's puppet starts with a cut (animate_ blend-in 0, the move's %.2f s glide stays with the locator drive)",
         g_ps.uid, psync_name(g_ps.att_sid), g_ps.att, g_ps_blend);
    return 0.0f;
}
// The VICTIM half of an execution on our own DOWNED body starts with a cut too (the whole torso piece disappeared during
// special executions). A log f62272 + a 60 fps clip: the victim half went in with the attacker's distance blend (1.17 s,
// "start 2.01 m ... -> blend-in 1.17 s"), on the same frame the UC4 lying overlay went off ("uc4 overlay: off (tackle on us) - 8 renamed
// lookups"), so the state the transition fades OUT of is the lying state whose renamed lookups are gone. For exactly that blend the torso piece
// (militia-male-13-torso: shirt, sleeves, hands - the only piece skinned to the arm / shoulder twist + helper joints) was gone with every draw
// input reading visible (drawn 4/4, masks ff, camhide 0), only torn edges of the lower shirt left (triangles with a vertex on a degenerate joint),
// and it GREW back over the last ~8 frames (14.73-14.87 s, cut at 13.77 s = 1.1 s) - the shape of a blend weight running out, not of a draw flag.
// The same stale-state transition is documented above for puppets (skeleton at its locator, grows back over 0.15-0.5 s). Our victim screen cuts
// to the execution camera on that frame (xcam victim "blends: in 0 ms (2013 cut)" for gun and melee executions), so the pose cut is never seen.
// The puppet halves on the other screens keep their blend (they are not touched here). t2r-no-vic-cut-start.txt next to the exe = the old blend.
static float ps_own_vic_blend(void) {
    static int off = -1;
    if (off < 0) { FILE *f = exe_side_open("t2r-no-vic-cut-start.txt", "r"); off = f != NULL; if (f) fclose(f); }
    if (off || !g_downed || (g_ps.kind != PS_GUN_EXEC && g_ps.kind != PS_MELEE_EXEC)) return -1.0f;
    xlog("psync: u%08x victim half %s on our DOWNED body starts with a cut (animate_ blend-in 0 instead of %.2f s: no transition out of the lying "
         "state whose overlay goes off now - torso fix; t2r-no-vic-cut-start.txt = old blend)", g_ps.uid, psync_name(g_ps.vic_sid), g_ps_blend);
    return 0.0f;
}
// The VICTIM half of an execution / upgraded one-shot on a STANDING PUPPET starts with a cut too (the torso piece disappeared; the
// same stale-graph transition as the attacker half above). Reports + A/B: 180 'pose pop (collapse)' lines on 'paired-victim' puppets,
// 73 of them 1 frame after the victim half started (slot 3 pelvis 0.88 -> 0.01 m, 1 f after half-start of the pipe-mod-side-swing-fin
// victim clip; its 'victim root' t=0 line read the hands 0.00 m apart = skeleton on the locator). The torso piece is the only mesh skinned to the arm /
// shoulder twist + helper joints, so a collapsed skeleton shows as the torso gone. A downed puppet is excluded: its graph already plays a script clip.
// t2r-no-pup-vic-cut-start.txt next to the exe = the old blend.
// Dodge counter (the cuts between and of the clips were too abrupt; more fluid): longer blends than the takedowns' 0.3 s.
// In: both halves at least PS_DC_IN; a victim held on its first frame (contact lag / the haymaker's intro) eases into that pose over most of the
// hold instead of snapping into it and standing frozen. Out: PS_DC_OUT at the hand-off (the stagger flows back into locomotion).
#define PS_DC_IN 0.35f
#define PS_DC_OUT 0.6f
#define PS_VIC_EARLY_MS 120.0
static int ps_dc(void) { return g_ps.kind == PS_CTXDOWN && dc_is_counter(g_ps.move); }
static float ps_out_blend(void) { return ps_dc() ? PS_DC_OUT : PS_BLEND; }
static float ps_dc_vic_in(float bl) {      // -1 = keep bl (the default blend)
    if (!ps_dc()) return bl;
    float hold = g_ps.vhold_seg ? psync_dur(g_ps.ent_att, g_ps.att_sid) : g_ps.vlag - g_ps.skip_ms / 1000.0f, b = fmaxf(PS_DC_IN, 0.85f * hold);
    if (b > 0.6f) b = 0.6f;
    return bl == 0.0f ? bl : fmaxf(b, g_ps_blend);
}
static float ps_pup_vic_blend(void) {
    {   // (a recording): the victim half of a pull-out pair (pu-drag / pu-grap / pu-fail / pu-ok) on a PUPPET starts with a cut. psync_pup_take suspends the net
        // channels, the prone net pose falls to the NPC standing idle and the 0.5 s crossfade then showed the lying victim standing up on every other screen (the
        // victim's own screen stayed lying; log lines 251418-251433 victim pelvis 0.15 -> 0.77). The locator drive and the attacker half's crossfade are untouched.
        // t2r-pullout-vic-cut-off.txt next to the exe = the old crossfade.
        static int poff = -1;
        if (poff < 0) { FILE *pf = exe_side_open("t2r-pullout-vic-cut-off.txt", "r"); poff = pf != NULL; if (pf) fclose(pf); }
        if (!poff && g_ps.kind == PS_CTXDOWN && pul_pair_name(g_ps.move)) {
            static int nlv; if (LOGCAP(nlv, 100)) xlog("psync: u%08x pull-out victim half %s on slot %d's puppet starts with a cut (blend-in 0 instead of %.2f s: the prone net pose fell to the standing idle and the crossfade showed it standing up; t2r-pullout-vic-cut-off.txt = old)", g_ps.uid, psync_name(g_ps.vic_sid), g_ps.vic, g_ps_blend);
            return 0.0f;
        }
    }
    static int off = -1;
    if (off < 0) { FILE *f = exe_side_open("t2r-no-pup-vic-cut-start.txt", "r"); off = f != NULL; if (f) fclose(f); }
    if (off || (g_ps.kind != PS_GUN_EXEC && g_ps.kind != PS_MELEE_EXEC) || g_ps.vic < 0 || g_ps.vic >= T2R_MAX_PEERS || g_peer_downed[g_ps.vic]) return -1.0f;
    xlog("psync: u%08x victim half %s on slot %d's STANDING puppet starts with a cut (animate_ blend-in 0 instead of %.2f s: the stale puppet graph collapsed the "
         "skeleton = torso gone; t2r-no-pup-vic-cut-start.txt = old blend)", g_ps.uid, psync_name(g_ps.vic_sid), g_ps.vic, g_ps_blend);
    return 0.0f;
}
static int dc_seg0_hold(uint64_t move);        // dcounter.c: a chain whose victim holds its first frame through segment 0 (the haymaker's intro)
static float dc_vic_lag_of(uint64_t move);     // dcounter.c: the victim half's start delay of a dodge-counter pair (0 = none)
static void psync_half_speed_s(int k, float v, int src) {
    uint64_t b[4] = {k ? g_ps.ent_vic : g_ps.ent_att, 0, ANIM_LAYER, k ? g_ps.vic_sid : g_ps.att_sid};
    memcpy(&b[1], &v, 4);
    mo_rate_dc(b, src);
    g_ps.rate[k] = v;
}
#define psync_half_speed(k, v) psync_half_speed_s((k), (v), MO_HERE())   // (motion.c: every caller is its own source)
// ---- play the halves of g_ps (all roles); 1 = our own half (if any) started
static int psync_play(void) {
    uint32_t self = psync_self();
    uint64_t hv = g_ps.vic != (int)self ? psync_puppet(g_ps.vic) : 0, ha = g_ps.att != (int)self ? psync_puppet(g_ps.att) : 0;
    g_ps.ent_att = g_ps.att == (int)self ? SID_PLAYER : ha;
    g_ps.ent_vic = g_ps.vic == (int)self ? SID_PLAYER : hv;
    if (!g_ps.ent_att || !g_ps.ent_vic) {
        xlog("psync: u%08x - a body has no puppet here (attacker %llx, victim %llx) - not played", g_ps.uid,
             (unsigned long long)g_ps.ent_att, (unsigned long long)g_ps.ent_vic);
        return 0;
    }
    g_ps.att_dur = psync_dur(g_ps.ent_att, g_ps.att_sid);
    g_ps.vic_dur = psync_dur(g_ps.ent_vic, g_ps.vic_sid);
    if (g_ps.att_dur <= 0 || g_ps.vic_dur <= 0) {
        xlog("psync: u%08x - clip not loaded here (%s %.2f s on the attacker, %s %.2f s on the victim) - not played", g_ps.uid,
             psync_name(g_ps.att_sid), g_ps.att_dur, psync_name(g_ps.vic_sid), g_ps.vic_dur);
        return 0;
    }
    g_ps.nseg = 0; g_ps.cur_seg = 0; g_ps.chain_shift = 0.0;
    if (g_ps.kind == PS_CTXDOWN) g_ps.nseg = cd_chain_of(g_ps.move, g_ps.seg_att, g_ps.seg_vic, g_ps.seg_spd, g_ps.seg_cut, PS_MAXSEG);   // the same table on every client (by the pair's move id)
    else if (g_ps.kind == PS_REVIVE) g_ps.nseg = rv_chain_of(g_ps.seg_att, g_ps.seg_vic, g_ps.seg_spd, g_ps.seg_cut, PS_MAXSEG);
    else if (g_ps.kind == PS_BODYSHIELD) g_ps.nseg = bs_chain_of(g_ps.move, g_ps.seg_att, g_ps.seg_vic, g_ps.seg_spd, g_ps.seg_cut, PS_MAXSEG);   // enter / hold / end (the END pair is replaced at run time)           // enter / loop / finish (the first clips are the enter pair psync_start got)
    if (ps_carrier_len_bad(g_ps.ent_att, g_ps.att_sid, "attacker half") || ps_carrier_len_bad(g_ps.ent_vic, g_ps.vic_sid, "victim half")) return 0;
    for (int i = 0; i < g_ps.nseg; i++)
        if (ps_carrier_len_bad(g_ps.ent_att, g_ps.seg_att[i], "chain attacker") || ps_carrier_len_bad(g_ps.ent_vic, g_ps.seg_vic[i], "chain victim")) return 0;
    g_ps.speed = g_ps.nseg > 0 ? g_ps.seg_spd[0] : 1.0f;
    if (g_ps.speed > 1.001f) { g_ps.att_dur /= g_ps.speed; g_ps.vic_dur /= g_ps.speed; }
    g_ps.vlag = g_ps.kind == PS_CTXDOWN && g_ps.nseg <= 1 ? dc_vic_lag_of(g_ps.move) : 0.0f; g_ps.ahold = 0.0f; g_ps.ahold_on = 0; g_ps.vlag_hold = 0; g_ps.vlag_pins = 0; g_ps.vhold_seg = g_ps.kind == PS_CTXDOWN && g_ps.nseg > 1 && (dc_seg0_hold(g_ps.move) || cd_mf_intro_move(g_ps.move));   // (v5: the duel finisher's SP intro too - SP plays it on the attacker alone)
    // Dodged attacks on high ping still looked like hits for 0.5 s: the victim may dodge until our pair START reaches it, and its
    // refusal (ABORT reason 7) came back ~10 frames later, after its body had started the hit reaction on our screen. On OUR screen the victim half of a duel
    // hit now waits one round trip (<= 170 ms) on its first frame: a dodge refusal arrives before any hit shows. t2r-duel-no-hit-wait.txt = old start.
    if (g_ps.role == 1 && g_ps.kind == PS_CTXDOWN && g_ps.nseg <= 1 && g_ps.vlag <= 0.0f && g_ps.vic >= 0 && mdu_move(g_ps.move)
        && GetFileAttributesA("t2r-duel-no-hit-wait.txt") == INVALID_FILE_ATTRIBUTES) {
        float rt = (g_ps.clk_shift > 0.0f ? psync_oneway(g_ps.vic) : 2.0f * psync_oneway(g_ps.vic)) / 1000.0f + 0.017f;   // (shared clock: one one-way already passed)
        // (A/B at 80 ms one-way: the refusal came back 183 ms after the start - past the old 170 ms cap, one frame of hit showed: + 2 frames, cap 250 ms.
        //  Hit-stop: our own half freezes on its contact frame for up to 100 ms of that wait, so the blow and the reaction meet on our screen as in SP.)
        rt += 0.017f;
        if (rt >= 0.06f) { g_ps.vlag = rt > 0.14f ? 0.14f : rt; g_ps.ahold = GetFileAttributesA("t2r-duel-no-hitstop.txt") == INVALID_FILE_ATTRIBUTES ? fminf(g_ps.vlag, 0.05f) : 0.0f;   // (not fluid): 250 ms victim freeze + 100 ms hit-stop per blow at 80 ms ping -> 140 / 50
            xlog("psync: u%08x duel hit - the victim half waits %.0f ms (round trip) for a dodge refusal, our half hit-stops %.0f ms", g_ps.uid, g_ps.vlag * 1000.0f, g_ps.ahold * 1000.0f);
            mct_hitstop_arm(); }   // melee_duel_contact.c: the wait plays both halves slowed from frame 0 up to the impact frame instead of a frozen victim + a fist moving on
    }
    if (g_ps.dur_s <= 0) g_ps.dur_s = g_ps.att_dur > g_ps.vic_dur + g_ps.vlag ? g_ps.att_dur : g_ps.vic_dur + g_ps.vlag;
    if (g_ps.nseg > 1) g_ps.dur_s = 20.0f;               // the chain's end is the owner's hand-off (ctxdown), not the clips'
    // Clashes / finishers should play client-side regarding positioning and timing of animation on both puppets: the attacker's ap put
    // OUR body where the attacker saw it one-way latency ago - the victim's own body was pulled up to 0.6 m and the puppet up to 1.15 m. For an open-ground
    // duel pair the victim re-anchors the ap on its own body (translation only, the pair's heading kept): our body starts where it stands, only the
    // attacker's puppet is pulled onto its spot, both bodies hand back to their real positions after the move. t2r-duel-ap-sender.txt = the sent ap.
    // (v5: a duel finisher with its SP intro is a 2-segment chain on the same ap - fitted the same way, from the intro's first frame + the victim's)
    if (g_ps.role == 2 && g_ps.kind == PS_CTXDOWN && (g_ps.nseg <= 1 || cd_mf_intro_move(g_ps.move)) && cd_local_move(g_ps.move) && GetFileAttributesA("t2r-duel-ap-sender.txt") == INVALID_FILE_ATTRIBUTES
        && !bq_align_vic(g_ps.att)) {   // (smooth:align, melee_beat.c: a beat RESULT's agreed align point = the START's ap is kept, no refit on our own view)
        // Stuff like that needs no client-side reactions: the pair is fitted to the two bodies as THIS screen sees them - the
        // authored attacker -> victim line turned onto our body -> the attacker's puppet line, the midpoint of the authored spots on the midpoint of the two
        // bodies. Each body moves half the gap (none of the sender's view is used but its ap height); a live test had up to 1.02 m between the screens.
        static const float id7[7] = {0, 0, 0, 0, 0, 0, 1};
        psync_bf ib; psync_bf_make(&ib, id7);
        float ca[8], cv[8], mb[16], ab[16], ph = g_ps.vic_dur > 0.0f ? fminf(0.95f, g_ps.skip_ms / 1000.0f / g_ps.vic_dur) : 0.0f, pha = g_ps.att_dur > 0.0f ? fminf(0.95f, g_ps.skip_ms / 1000.0f / g_ps.att_dur) : 0.0f;
        const float *me = player_locator(mb), *pa = g_ps.ent_att && g_ps.ent_att != SID_PLAYER ? psync_loc(g_ps.ent_att, ab) : NULL;
        if (me && pa && ps_loc_ok(me) && ps_loc_ok(pa) && psync_expected(SID_PLAYER, g_ps.vic_sid, &ib, ph, cv) && psync_expected(g_ps.ent_att, g_ps.att_sid, &ib, pha, ca)) {
            float dax = ca[0] - cv[0], daz = ca[2] - cv[2], dlx = pa[0] - me[0], dlz = pa[2] - me[2];
            if (dax * dax + daz * daz > 0.04f && dlx * dlx + dlz * dlz > 0.04f && dlx * dlx + dlz * dlz < 9.0f) {
                float th = __builtin_atan2f(dlx, dlz) - __builtin_atan2f(dax, daz);
                // (the victim got bugged into a tree and crashed; B [41729] 'ap moved 0.65 m, yaw 102 deg' vs the sender's ap yaw 44 at A [26944]):
                // the fit turned the whole pair 58 deg off the heading the ATTACKER had gated (path gate + REACT space + wall steer, A [26938]-[26940] 'clear'),
                // so our recoil (2.56 m for light-4) ran on a path nobody checked - into the tree, where the body then pinned and the controller blew up. A
                // duel -hit pair keeps the sender's heading within MDU_FIT_YAW of it: the rest of the gap is closed by the midpoint fit (both bodies half).
                if (mdu_move(g_ps.move) && GetFileAttributesA("t2r-duel-fit-free-yaw.txt") == INVALID_FILE_ATTRIBUTES) {
                    float y0 = 2.0f * __builtin_atan2f(g_ps.ap[4], g_ps.ap[6]), dy = th - y0, lim = 20.0f * 0.0174533f;
                    while (dy > 3.14159265f) dy -= 6.2831853f;
                    while (dy < -3.14159265f) dy += 6.2831853f;
                    if (dy > lim || dy < -lim) {
                        float th2 = y0 + (dy > 0.0f ? lim : -lim);
                        xlog("psync: u%08x local fit (victim): the bodies as we see them turn the pair %+.0f deg off the attacker's gated heading - kept to %+.0f (its recoil path was checked there)",
                             g_ps.uid, dy * 57.29578f, (dy > 0.0f ? lim : -lim) * 57.29578f);
                        th = th2;
                    }
                }
                float cs = __builtin_cosf(th), sn = __builtin_sinf(th);
                float mx = 0.5f * (ca[0] + cv[0]), mz = 0.5f * (ca[2] + cv[2]);        // authored midpoint (ap space)
                float rx = mx * cs + mz * sn, rz = -mx * sn + mz * cs;                    // rotated by th about +Y
                float ox = g_ps.ap[0], oz = g_ps.ap[2];
                g_ps.ap[0] = 0.5f * (me[0] + pa[0]) - rx; g_ps.ap[2] = 0.5f * (me[2] + pa[2]) - rz;
                g_ps.ap[3] = 0.0f; g_ps.ap[4] = __builtin_sinf(th * 0.5f); g_ps.ap[5] = 0.0f; g_ps.ap[6] = __builtin_cosf(th * 0.5f);
                if (g_ps.wsh_ok) { g_ps.ap[0] += g_ps.wS[0][0]; g_ps.ap[2] += g_ps.wS[0][1]; }     // the fit puts the pair on the two bodies - the attacker's wall shift comes on top
                xlog("psync: u%08x local fit (victim): pair on the two bodies as we see them - ap moved %.2f m, yaw %.0f deg; bodies %.2f m apart (authored %.2f)", g_ps.uid,
                     __builtin_sqrtf((g_ps.ap[0] - ox) * (g_ps.ap[0] - ox) + (g_ps.ap[2] - oz) * (g_ps.ap[2] - oz)), th * 57.29578f,
                     __builtin_sqrtf(dlx * dlx + dlz * dlz), __builtin_sqrtf(dax * dax + daz * daz));
            }
        }
    }
    psync_bfs();
    // puppets first: their network channels off BEFORE the half starts, so nothing pulls them off the ap
    if (g_ps.ent_att != SID_PLAYER) psync_pup_take(g_ps.att, g_ps.ent_att, g_ps.role == 3 ? "third party, attacker" : "attacker half");
    if (g_ps.ent_vic != SID_PLAYER) psync_pup_take(g_ps.vic, g_ps.ent_vic, g_ps.role == 3 ? "third party, victim" : "victim half");
    if (g_ps.kind == PS_CTXDOWN && mdu_move(g_ps.move)) {      // duel timeline: the pair confirms the predicted swing / takes over the queue of that puppet
        if (g_ps.ent_att != SID_PLAYER) dtl_note_pair((uint32_t)g_ps.att);
        if (g_ps.ent_vic != SID_PLAYER) dtl_note_pair((uint32_t)g_ps.vic);
        if (g_ps.ent_att != SID_PLAYER) mct_note_pair((uint32_t)g_ps.att);   // melee_duel_contact.c: the START vs the replica's contact frame, the warp hands over
    }
    for (int k = 0; k < 2; k++) {     // where each body stands before the start (the puppet drive blends from it)
        float b[16];
        const float *l = psync_loc(k ? g_ps.ent_vic : g_ps.ent_att, b);
        g_ps.start_ok[k] = l && ps_loc_ok(l);
        if (g_ps.start_ok[k]) memcpy(g_ps.start_loc[k], l, sizeof g_ps.start_loc[k]);
        g_ps.half_yaw_ok[k] = 0; g_ps.place_ok[k] = 0;
    }
    {   // The half blends the body from where it stands onto its authored start. A fixed 0.3 s made a player approaching along the
        // downed body's axis (the natural way: 1-2.7 m from the lateral start) slide that far in 0.25 s with a 70-80 deg yaw swing
        // (clip-analysis-1007.md). The blend now grows with the distance (+0.45 s per metre beyond 0.5 m, 0.3 .. 1.3 s) and with the
        // yaw swing; the start positions are the same on every client to a few cm, so every client lands on the same value.
        float blend = PS_BLEND;
        g_ps_off_d[0] = g_ps_off_d[1] = -1.0f;
        if (g_ps.c_att_ok && g_ps.start_ok[0]) {
            float ia0[4];
            psync_in_ap(g_ps.start_loc[0], ia0);
            float dx = ia0[0] - g_ps.c_att[0], dz = ia0[1] - g_ps.c_att[2], d = __builtin_sqrtf(dx * dx + dz * dz);
            float dy = __builtin_fabsf(uc4_wrap(ia0[3] - uc4_yaw(g_ps.c_att)));
            blend = PS_BLEND + (d > 0.5f ? 0.45f * (d - 0.5f) : 0.0f) + (dy > 30.0f ? 0.004f * (dy - 30.0f) : 0.0f);
            if (blend > 1.3f) blend = 1.3f;
            {   // shiv kills: the stab lands at ~0.4 s (the first camera-impact shake), so the attacker's alignment onto his authored spot
                // has to be a short pre-move alignment, done before it (a 1.3 m slide over 0.7 s ran through the stab). Only
                // one back shiv exists (no left / right or mirrored variant), so an approach from the other side is aligned this way.
                int mi = g_ps.kind == PS_MELEE_EXEC ? mx_by_move(g_ps.move) : -1;
                // the 2013 upgraded-melee one-shot (MX_PIPE_MOD) starts AT the blow (its victim half's head hit is frame 0): same short alignment
                if (mi >= 0 && (MX_ISSHIV(MELEE2013[mi].kind) || MELEE2013[mi].kind == MX_PIPE_MOD)) blend = PS_BLEND;
                // (ground shiv: the stabbing started before the stabber was in place): the 2013 clip is authored for an attacker that starts 1.24 m
                // beside the body and pounces - its first stab (sfx blade f13 = 0.43 s, the knife 0.24 m from the chest at 0.5 s) lands 0.4 s in, while the generic
                // 0.45 s / m blend (1.3 s at the 2.7 m a head-end E press is away) was still sliding the body in. The attacker has to be on its spot by ~0.5 s:
                // the glide runs at up to ~4.5 m/s (SP's own melee pull was measured at 4.15 m/s, ctxdown PS_SP_PULL_S), 0.30 .. 0.60 s (the clip's own approach
                // steps carry the last 0.3 m). The nearest-spot pair pick (mx_pick_near in meleeexec_2013) keeps d small. t2r-shiv-ground-slow-blend.txt = the old blend.
                if (mi >= 0 && MELEE2013[mi].kind == MX_SHIV_GROUND) {
                    FILE *sf = exe_side_open("t2r-shiv-ground-slow-blend.txt", "r");
                    if (sf) fclose(sf);
                    else { blend = d / 4.5f + 0.15f; if (blend < PS_BLEND) blend = PS_BLEND; if (blend > 0.60f) blend = 0.60f; }
                }
            }
            xlog("psync: u%08x start %.2f m / %.0f deg from the attacker's authored spot -> blend-in %.2f s", g_ps.uid, d, dy, blend);
        }
        if (g_ps.kind == PS_REVIVE && blend < RV_BLEND) blend = RV_BLEND;
        g_ps.seg_drive_bl = blend; g_ps.drive_easeout = 0;
        if (g_ps.kind == PS_CTXDOWN) {
            FILE *of = exe_side_open("t2r-cd-old-blend.txt", "r");
            if (of) fclose(of);
            else {
                // SP's 0.20 s was measured for the ATTACKER of one start (0.83 m / 42 deg -> 4.15 m/s, 210 deg/s); SP's victim keeps a continuous root.
                // (A [63884]: the victim spun 168 deg in 0.20 s, which read as a teleport): the pull lasts as long as the larger offset needs at
                // SP's attacker rate, and at 1.5 m/s / 180 deg/s for the victim half (min 0.20 s, max 0.70 s). Offsets are against each half's spot at
                // the START phase (ctxdown starts a chain into its push / intro, so the push's own root motion carries the rest).
                float pull = PS_SP_PULL_S, off_d[2] = {0, 0}, off_y[2] = {0, 0};
                static const float id7[7] = {0, 0, 0, 0, 0, 0, 1};
                psync_bf ib; psync_bf_make(&ib, id7);
                float a8[8]; ps_ap8(g_ps.ap, a8);
                for (int k = 0; k < 2; k++) {
                    float c[8], w[8], dur = k ? g_ps.vic_dur : g_ps.att_dur, ph = dur > 0.0f ? fmaxf(0.0f, g_ps.skip_ms / 1000.0f - (k ? g_ps.vlag : 0.0f)) / dur : 0.0f;
                    if (ph > 0.95f) ph = 0.95f;
                    // ps39 B (rec35a A [19752] 'victim 0.54 m / 30 deg off their spots at the start phase (467 ms in)' on a finisher whose victim half is deferred and
                    // starts from its phase 0 at the hand-over): a deferred victim half is measured where it will start. t2r-start-audit-ps38.txt = old.
                    if (k && g_ps.vhold_seg && ph > 0.0f && GetFileAttributesA("t2r-start-audit-ps38.txt") == INVALID_FILE_ATTRIBUTES) ph = 0.0f;
                    if (!g_ps.start_ok[k] || !psync_expected(k ? g_ps.ent_vic : g_ps.ent_att, k ? g_ps.vic_sid : g_ps.att_sid, &ib, ph, c)) continue;
                    ps_compose(a8, c, w);
                    const float *s = g_ps.start_loc[k];
                    off_d[k] = __builtin_sqrtf((w[0] - s[0]) * (w[0] - s[0]) + (w[2] - s[2]) * (w[2] - s[2]));
                    off_y[k] = __builtin_fabsf(uc4_wrap(uc4_yaw(w) - uc4_yaw(s)));
                    float need = k ? fmaxf(off_d[k] / 1.5f, off_y[k] / 180.0f) : fmaxf(off_d[k] / (g_ps_fin_pull ? PS_FIN_PULL_MS : 4.15f), off_y[k] / 210.0f);
                    if (need > pull) pull = need;
                }
                for (int k = 0; k < 2; k++) { g_ps_off_d[k] = g_ps.start_ok[k] ? off_d[k] : -1.0f; g_ps_off_y[k] = off_y[k]; }   // (mct_vic_blend)
                // v5: a duel finisher's SP intro is the run-in - the gap closes over the whole windup (SP: the intro's own root motion onto the sync spot)
                if (cd_mf_intro_move(g_ps.move) && g_ps.skip_ms <= 0.0f) { float im = cd_seg0_ms(g_ps.move) / 1000.0f / (g_ps.irate > 1.0f ? g_ps.irate : 1.0f); if (im > pull) pull = im; }
                // smooth:glide (duel -hit / parry pairs): a body away from its aligned start spot eases there with smoothstep over 150-250 ms (position) and turns at
                // <= 720 deg/s (never a snap); a gap > 1.2 m is logged and glides longer (up to 400 ms), never a teleport. Same locator drive as above (drive_bl, drive_easeout 0 = smoothstep).
                int glide = mdu_move(g_ps.move) && !cd_mf_intro_move(g_ps.move) && !smooth_off(1);
                if (glide) {
                    float dmax = fmaxf(off_d[0], off_d[1]), ymax = fmaxf(off_y[0], off_y[1]);
                    // cluster D (des4 [225374]: 'victim 0.00 / 148 deg -> smoothstep over 205 ms, turn <= 720 deg/s' = the victim whips round 148 deg in 12 frames):
                    // a big turn is spread (<= 420 deg/s, up to 0.45 s) so it reads as a shocked turn, not a spin. TUNING. t2r-glide-turn-old.txt = 720 deg/s, 0.40 s.
                    static int told = -1; static uint64_t tchk; if (told < 0 || GetTickCount64() - tchk > 3000) { tchk = GetTickCount64(); told = GetFileAttributesA("t2r-glide-turn-old.txt") != INVALID_FILE_ATTRIBUTES; }
                    float tp = dmax <= 1.2f ? 0.15f + 0.10f * (dmax / 1.2f) : 0.25f + 0.15f * fminf(1.0f, (dmax - 1.2f) / 1.2f), ty = ymax / (told ? 720.0f : 420.0f), old_pull = pull;
                    pull = fmaxf(tp, ty);
                    if (pull > (told ? 0.40f : 0.45f)) pull = told ? 0.40f : 0.45f;
                    xlog("smooth: glide u%08x%s: gap %.2f m / %.0f deg (attacker %.2f / %.0f, victim %.2f / %.0f) -> smoothstep over %.0f ms, turn <= %.0f deg/s (was %.0f ms quadratic ease-out)",
                         g_ps.uid, dmax > 1.2f ? " LARGE GAP (kept as a longer glide, no teleport)" : "", dmax, ymax, off_d[0], off_y[0], off_d[1], off_y[1], pull * 1000.0f, pull > 0.0f ? ymax / pull : 0.0f, old_pull * 1000.0f);
                }
                if (g_ps.role == 3 && !byst_old()) {      // cluster A: a bystander sees the bodies slide, never snap - one duration for both, <= 3.5 m/s / 360 deg/s
                    float dmx = fmaxf(off_d[0], off_d[1]), ymx = fmaxf(off_y[0], off_y[1]), want = fmaxf(0.25f, fmaxf(dmx / 3.5f, ymx / 360.0f));
                    if (want > 0.80f) want = 0.80f;
                    if (want > pull) { xlog("byst: u%08x start pull of both bodies %.0f -> %.0f ms (gap %.2f m / %.0f deg, attacker %.2f, victim %.2f; <= 3.5 m/s, 360 deg/s)", g_ps.uid, pull * 1000.0f, want * 1000.0f, dmx, ymx, off_d[0], off_d[1]); pull = want; }
                }
                {   // ps45 prone (SP recorder ep 5 / ep 8: drag -> struggle and intro -> drag both crossfade 0 -> 1 over 0.50 s smoothstep, the roots continuous): a pull-out
                    // pair (kind 8) starts over SP's crossfade on every client (melee_pullout.c pul_ps_xfade, same answer from the row name everywhere), smoothstep drive.
                    // t2r-pullout-spblend-off.txt = the old SP-pull blend.
                    float px = pul_ps_xfade(g_ps.move);
                    if (px > pull) { xlog("psync: u%08x pull-out pair %s - SP's crossfade: blend-in and locator drive %.0f ms smoothstep (the pull asked %.0f ms; ps45 prone)", g_ps.uid, psync_name(g_ps.vic_sid), px * 1000.0f, pull * 1000.0f); pull = px; glide = 1; }
                }
                if (pull > 1.00f) pull = 1.00f;     // (any victim facing - a victim turned away needs up to ~1 s at 180 deg/s)
                xlog("psync: u%08x takedown - TLOU2 SP's pull (quadratic ease-out) over %.2f s: attacker %.2f m / %.0f deg, victim %.2f m / %.0f deg off their spots at the start "
                     "phase (%.0f ms in), not the %.2f s distance blend", g_ps.uid, pull, off_d[0], off_y[0], off_d[1], off_y[1], g_ps.skip_ms, blend);
                blend = pull; g_ps.drive_easeout = glide ? 0 : 1;
            }
        }
        g_ps_blend = blend; g_ps.drive_bl = blend;
    }
    g_ps.root_bucket = -1;
    g_ps.vic_own_lethal = g_ps.ent_vic == SID_PLAYER && (g_ps.flags & PS_F_LETHAL) && (g_ps.kind == PS_GUN_EXEC || g_ps.kind == PS_MELEE_EXEC);
    g_ps.play_ms = psync_ms();
    float ph_a =g_ps.skip_ms / 1000.0f / g_ps.att_dur, ph_v = fmaxf(0.0f, g_ps.skip_ms / 1000.0f - g_ps.vlag) / g_ps.vic_dur;
    if (ph_a > 0.95f) ph_a = 0.95f;
    if (ph_v > 0.95f) ph_v = 0.95f;
    // our own half first: if the engine refuses it, nothing else plays
    int own_att = g_ps.ent_att == SID_PLAYER, own_vic = g_ps.ent_vic == SID_PLAYER;
    int duel_hit = g_ps.kind == PS_CTXDOWN && g_ps.nseg <= 1 && mdu_move(g_ps.move) && GetFileAttributesA("t2r-hit-blend-old.txt") == INVALID_FILE_ATTRIBUTES;
    if (own_att) { float ab = ps_take_blend40(0, 1, mct_own_att_blend(sptl_own_att_blend())); if (duel_hit && ab >= 0.0f && ab < MEL_MIN_BLEND) g_mel_floor_once = MEL_HIT_BLEND; g_ps.r_att = psync_animate(SID_PLAYER, g_ps.att_sid, &g_ps.bf_att, ph_a, ab); g_mel_floor_once = -1.0f; g_ps_att_bl_applied = g_ps_anim_bl; g_ps_att_bl_uid = g_ps.uid; }   // (sptl: a duel -hit half at full weight on the switch frame, like SP)
    if (ps_dc() && g_ps_blend < PS_DC_IN) g_ps_blend = PS_DC_IN;
    // The attacked should blend into the pose to ready up for the counterattack, not teleport into it - a chain's
    // victim half started at once and frozen on its first frame (speed 0) showed at full weight from the first frame (the lunge -> upright in one frame).
    // Now it is not started during the attacker's intro at all: the body plays on from its own swing while the pull moves it onto the spot, and the half
    // starts at the chain switch (contact) with psync_seg_next's 0.35 s blend. t2r-dc-vic-snap.txt = old start + freeze.
    int vdefer = g_ps.vhold_seg && GetFileAttributesA("t2r-dc-vic-snap.txt") == INVALID_FILE_ATTRIBUTES;
    p30_start();                        // ps30: the victim of a duel -hit pair holds a melee item - its weapon stays gripped in one hand through the half (melee_hitreact.c)
    if (own_vic) g_ps.r_vic = vdefer ? 1 : psync_animate(SID_PLAYER, g_ps.vic_sid, &g_ps.bf_vic, ph_v, ps_take_blend40(1, 1, mct_vic_blend(ps_dc_vic_in(ps_own_vic_blend()))));
    if ((own_att && (!g_ps.r_att || g_ps.r_att == ~0ULL)) || (own_vic && (!g_ps.r_vic || g_ps.r_vic == ~0ULL))) {
        xlog("psync: u%08x - our own half %s was refused (%llx) - move dropped", g_ps.uid, psync_name(own_att ? g_ps.att_sid : g_ps.vic_sid),
             (unsigned long long)(own_att ? g_ps.r_att : g_ps.r_vic));
        for (int s = 0; s < T2R_MAX_PEERS; s++) if (g_ps_pup[s].h) psync_pup_release(s, "own half refused", 0);
        return 0;
    }
    if (!own_att) {
        psync_layer_snap("before animate_", g_ps.ent_att);
        { float pb = ps_take_blend40(0, 0, ps_pup_att_blend()); if (duel_hit && pb >= 0.0f && pb < MEL_MIN_BLEND) g_mel_floor_once = MEL_HIT_BLEND; g_ps.r_att = psync_animate(g_ps.ent_att, g_ps.att_sid, &g_ps.bf_att, ph_a, pb); g_mel_floor_once = -1.0f; g_ps_att_bl_applied = g_ps_anim_bl; g_ps_att_bl_uid = g_ps.uid; }
        psync_layer_snap("right after animate_", g_ps.ent_att);
    }
    if (!own_vic) g_ps.r_vic = vdefer ? 1 : psync_animate(g_ps.ent_vic, g_ps.vic_sid, &g_ps.bf_vic, ph_v, ps_take_blend40(1, 0, mct_vic_blend(ps_dc_vic_in(ps_pup_vic_blend()))));
    g_ps.f_audit = g_frame;
    if (g_ps.irate > 1.0f && g_ps.r_att && g_ps.r_att != ~0ULL) psync_half_speed(0, g_ps.irate);   // (re-applied per frame in psync_tick: a speed set on the creating frame may not stick)
    if (g_ps.kind == PS_CTXDOWN && g_ps.nseg <= 1 && mdu_move(g_ps.move)) { g_ps.vrate = mdu_react_rate(); g_ps.vrate_n = 0; if (g_ps.vrate > 1.001f && g_ps.r_vic && g_ps.r_vic != ~0ULL) psync_half_speed(1, g_ps.vrate); }   // 
    if (g_ps.kind == PS_CTXDOWN && cd_mf_intro_move(g_ps.move))
        xlog("psync: u%08x FINISHER start (role %d): attacker half %s from phase %.3f at x%.2f (%.0f ms late absorbed in the windup), victim half %s %s; windup %.0f ms real to the hand-over",
             g_ps.uid, g_ps.role, psync_name(g_ps.att_sid), ph_a, g_ps.irate > 1.0f ? g_ps.irate : 1.0f, g_ps.ilate, psync_name(g_ps.vic_sid),
             vdefer ? "deferred to 120 ms before the hand-over (phase 0 there)" : "from its phase now", ph_a >= 0.9f ? 0.0f : cd_seg0_ms(g_ps.move) / (g_ps.irate > 1.0f ? g_ps.irate : 1.0f));
    g_ps.vdefer = vdefer; g_ps.vic_early = 0;
    if (vdefer) {
        g_ps.vlag_hold = 1;
        xlog("psync: u%08x victim half %s starts at the chain switch (contact, 0.35 s blend) - the body plays on from its own pose through the intro", g_ps.uid, psync_name(g_ps.vic_sid));
    } else if (g_ps.vhold_seg && g_ps.r_vic && g_ps.r_vic != ~0ULL) {
        psync_half_speed(1, 0.0f); g_ps.vlag_hold = 1;
        xlog("psync: u%08x victim half %s held on its first frame through chain segment 1 (the attacker's intro)", g_ps.uid, psync_name(g_ps.vic_sid));
    } else if (g_ps.vlag > 0.0f && g_ps.skip_ms < g_ps.vlag * 1000.0f && g_ps.r_vic && g_ps.r_vic != ~0ULL) {
        psync_half_speed(1, g_ps.hs_rate); g_ps.vlag_hold = 1;    // (hs_rate 0 = frozen; melee_duel_contact.c: both halves slowed to the impact frame)
        if (g_ps.hs_rate > 0.0f) xlog("mct: u%08x victim half %s plays at x%.2f until %.0f ms with our half (hit-confirm wait, no frozen frame)", g_ps.uid, psync_name(g_ps.vic_sid), g_ps.hs_rate, g_ps.vlag * 1000.0f);
        else xlog("psync: u%08x victim half %s held on its first frame until %.0f ms (it starts at the contact, SP's synced hit)", g_ps.uid, psync_name(g_ps.vic_sid), g_ps.vlag * 1000.0f);
    }
    if (g_ps.ahold > 0.0f && g_ps.role == 1 && g_ps.r_att && g_ps.r_att != ~0ULL && g_ps.skip_ms < g_ps.ahold * 1000.0f) { psync_half_speed(0, g_ps.hs_rate); g_ps.ahold_on = 1; }
    // a puppet half the engine refused (the clip is not in that puppet's AnimData / a stale handle): every screen used to carry on silently with the body in
    // whatever pose it had (a bystander saw a body frozen in its crouch / crawl pose with the sound and gore still running)
    for (int k = 0; k < 2; k++) {
        uint64_t r = k ? g_ps.r_vic : g_ps.r_att;
        if ((k ? own_vic : own_att) || (r && r != ~0ULL)) continue;
        xlog("psync: u%08x WARNING role %d: the %s half %s was REFUSED by animate_ on its puppet (%llx) - that body keeps its pose (clip not in the puppet's AnimData?)", g_ps.uid,
             g_ps.role, k ? "victim" : "attacker", psync_name(k ? g_ps.vic_sid : g_ps.att_sid), (unsigned long long)r);
    }
    if (g_ps.speed > 1.001f) {                                   // a sped-up move: both layers at the move's speed from the first frame
        for (int k = 0; k < 2; k++) {
            uint64_t ent = k ? g_ps.ent_vic : g_ps.ent_att, sid = k ? g_ps.vic_sid : g_ps.att_sid;
            uint64_t b[4] = {ent, 0, ANIM_LAYER, sid};
            memcpy(&b[1], &g_ps.speed, 4);
            uint64_t r = mo_rate_dc(b, MO_SRC("paired.start_speed"));
            g_ps.rate[k] = g_ps.speed;
            xlog("psync: u%08x %s half %s at x%.2f (set-animation-speed -> %llx)", g_ps.uid, k ? "victim" : "attacker", psync_name(sid), g_ps.speed, (unsigned long long)r);
        }
    }
    g_ps.start_frame = g_frame ? g_frame : 1;
    g_ps.last_sync_bucket = -1;
    float la[16], lv[16];
    const float *pa = psync_loc(g_ps.ent_att, la), *pv = psync_loc(g_ps.ent_vic, lv);
    float ia[4] = {0}, iv[4] = {0};
    if (pa) psync_in_ap(pa, ia);
    if (pv) psync_in_ap(pv, iv);
    xlog("psync: u%08x PLAY role %d kind %d - ap %.2f %.2f %.2f yaw %.0f, skip %.0f ms (phase att %.3f vic %.3f), move %.2f s, kill %.2f s%s",
         g_ps.uid, g_ps.role, g_ps.kind, g_ps.ap[0], g_ps.ap[1], g_ps.ap[2], uc4_yaw((float[]){0, 0, 0, 0, g_ps.ap[3], g_ps.ap[4], g_ps.ap[5], g_ps.ap[6]}),
         g_ps.skip_ms, ph_a, ph_v, g_ps.dur_s, g_ps.kill_s, g_ps.flags & PS_F_LETHAL ? " (lethal: the victim's client kills)" : "");
    xlog("psync: u%08x   attacker slot %d on %s: %s %.2f s -> %llx, at ap-space x %.2f z %.2f yaw %.0f before the start", g_ps.uid, g_ps.att,
         own_att ? "US" : "its puppet", psync_name(g_ps.att_sid), g_ps.att_dur, (unsigned long long)g_ps.r_att, ia[0], ia[1], ia[3]);
    xlog("psync: u%08x   victim slot %d on %s: %s %.2f s -> %llx, at ap-space x %.2f z %.2f yaw %.0f before the start", g_ps.uid, g_ps.vic,
         own_vic ? "US" : "its puppet", psync_name(g_ps.vic_sid), g_ps.vic_dur, (unsigned long long)g_ps.r_vic, iv[0], iv[1], iv[3]);
    sptl_note_pair();                                          // melee_duel_sptl.c: this exchange's halves vs SP's timeline
    return 1;
}

// ---- initiator
// ps45 item 1 (rec44a B [20025] 'psync: u001f4ce0 ABORT (pin escape)' + 'slot 0 puppet released' + 'puppet: slot 0 move over - hidden item shown again', the escape
// pair u011f7524 PLAY only at [20030] (mpn_counter at the press + 40 ms, then the path gate's rays) = the review's B pose pop 191.166 s: our pinned victim half
// and the pinner's puppet stood in their free upright poses for 5 frames; A [19983] the same on the pinner's screen: its ESC message cut the pin pair at once
// ('ABORT (pin escaped)', 'slot 1 puppet released', [19984] 'hidden item shown again') and the escape START arrived at [19988] = A 191.37 s). The pin pair
// now stays on both bodies until the escape pair takes them: the escaper keeps its victim half running until its own escape START (psync_start's "a new
// move" cut = the ABORT + START go out in the same frame), the pinner keeps its attacker half until that START (or the escaper's ABORT + 3 frames with no
// START = no escape pair: the dodge counter / the escape alone), each with a PE45_HOLD_MS fallback. t2r-pinesc-hold-ps45-old.txt = old (cut at the press).
#define PE45_HOLD_MS 350        // [TUNING ps45] > mpn_counter's 40 ms + its 250 ms path-gate wait
static struct { uint32_t uid; int side; uint64_t t0, until, abort_f; } g_pe45;      // side 2 = we escaped (our victim half held), 1 = we pinned (our attacker half held)
static int pe45_off(void) {
    static int off = -1; static uint64_t at;
    if (off < 0 || GetTickCount64() - at > 2000) { at = GetTickCount64(); int o = GetFileAttributesA("t2r-pinesc-hold-ps45-old.txt") != INVALID_FILE_ATTRIBUTES;
        if (o != off) xlog("pin escape hold (ps45): %s", o ? "OFF (t2r-pinesc-hold-ps45-old.txt): the pin pair is cut at the escape press" : "on - the pin pair stays on both bodies until the escape pair's START"); off = o; }
    return off;
}
static int pe45_held(int side) { return g_pe45.uid && g_pe45.side == side && g_ps.role == side && g_ps.uid == g_pe45.uid; }
static void pe45_arm(int side) {        // melee_duel_pin.c: at the escape (side 2) / the ESC message (side 1), instead of the cut
    uint64_t n = GetTickCount64();
    g_pe45.uid = g_ps.uid; g_pe45.side = side; g_pe45.t0 = n; g_pe45.until = n + PE45_HOLD_MS; g_pe45.abort_f = 0;
    xlog("pin escape hold (ps45): u%08x %s half held until the escape pair's START (fallback %d ms)", g_ps.uid, side == 2 ? "our pinned victim" : "our pinner attacker", PE45_HOLD_MS);
}
static void pe45_end(const char *why) {     // no escape pair came: the cut the old code made at the press, now
    if (!g_pe45.uid) return;
    uint32_t u = g_pe45.uid; int side = g_pe45.side; uint64_t t0 = g_pe45.t0; memset(&g_pe45, 0, sizeof g_pe45);
    if (!(g_ps.role == side && g_ps.uid == u)) return;
    xlog("pin escape hold (ps45): u%08x %s after %llu ms - the held pin pair is cut now", u, why, (unsigned long long)(GetTickCount64() - t0));
    psync_abort(side == 2 ? "pin escape" : "pin escaped", 1);
}
static void pe45_tick(void) {       // psync_tick
    if (!g_pe45.uid) return;
    if (!(g_ps.role == g_pe45.side && g_ps.uid == g_pe45.uid)) { memset(&g_pe45, 0, sizeof g_pe45); return; }     // (the pair ended / another move took it)
    if (g_pe45.abort_f && g_frame - g_pe45.abort_f >= 3) { pe45_end("the escaper's ABORT came without an escape START (3 frames)"); return; }
    if (GetTickCount64() >= g_pe45.until) pe45_end("no escape pair inside the fallback");
}
static int psync_start(int kind, uint32_t vic_slot, const char *att_clip, const char *vic_clip, const float *ap7,
                       float kill_s, int flags, int pair, uint64_t weapon, uint64_t move) {
    float skip0 = g_ps_start_skip_ms; g_ps_start_skip_ms = 0.0f;      // (one call only)
    if (!(skip0 > 0.0f && skip0 < 5000.0f)) skip0 = 0.0f;
    uint32_t self = psync_self();
    if (vic_slot > T2R_MAX_PEERS - 1 || vic_slot == self || !att_clip || !vic_clip || !*att_clip || !*vic_clip) return 0;
    float apx[7]; memcpy(apx, ap7, sizeof apx);
    pws_take_t pwt; pws_take(vic_slot, att_clip, vic_clip, apx, &pwt);      // pairshift.c: the shift the path gate cleared this pair with (ap moved by S_0; D(t) follows)
    ap7 = apx;
    float a8[8]; ps_ap8(ap7, a8);
    if (!ps_loc_ok(a8)) { xlog("psync: start refused - bad ap %.3g %.3g %.3g", ap7[0], ap7[1], ap7[2]); return 0; }
    if (pe45_held(2)) { xlog("pin escape hold (ps45): u%08x our held victim half handed straight to the new pair after %llu ms (ABORT + START in this frame, no free pose between)", g_ps.uid, (unsigned long long)(GetTickCount64() - g_pe45.t0)); memset(&g_pe45, 0, sizeof g_pe45); }
    if (g_ps.role) psync_abort("a new move", 1);
    memset(&g_ps, 0, sizeof g_ps);
    g_ps.role = 1; g_ps.kind = kind; g_ps.flags = flags; g_ps.pair = pair;
    if (!g_ps_counter) g_ps_counter = (uint32_t)(GetTickCount64() & 0x3fffff) << 1;     // a restarted game must not reuse the last session's uids (the victim's ring would drop the START)
    g_ps.uid = (self << 24) | (++g_ps_counter & 0xffffff);
    g_ps.att = (int)self; g_ps.vic = (int)vic_slot;
    g_ps.att_sid = fnv64(att_clip); g_ps.vic_sid = fnv64(vic_clip);
    memcpy(g_ps.ap, ap7, sizeof g_ps.ap);
    if (pwt.ok) { g_ps.wsh_ok = 1; g_ps.wsh_dyn = (uint8_t)pwt.dyn; g_ps.wtend = pwt.tend; memcpy(g_ps.wS, pwt.S, sizeof g_ps.wS); }
    float qn = __builtin_sqrtf(ap7[3] * ap7[3] + ap7[4] * ap7[4] + ap7[5] * ap7[5] + ap7[6] * ap7[6]);
    for (int i = 3; i < 7; i++) g_ps.ap[i] /= qn;
    g_ps.kill_s = kill_s; g_ps.weapon = weapon; g_ps.move = move;
    // skip0 (ctxdown): the move starts that far into its first segment - the clock, the phases, the START's move time (every client: skip = it + one-way)
    g_ps.t0 = psync_ms() - skip0; g_ps.skip_ms = skip0;
    // (netcode rework: the pair starts at the same moment on both screens): an open-ground duel pair runs on a clock one-way latency in the
    // future here. The victim gets the START that much later and plays it from frame 0, so both move clocks read the same at the same real time. Our
    // half starts now and psync_rate eases it onto the shifted clock (a short slow-down after the contact, like a hit-stop); the hand-off, the down and
    // the victim half's dodge wait all move with it. Opt-in (t2r-duel-shared-clock.txt): A/B at 80 ms the catch-up ran our own swing at 0.9x for ~1 s.
    g_ps.clk_shift = 0.0f;
    if (kind == PS_CTXDOWN && skip0 == 0.0f && cd_local_move(move) && (bq_shift_now((int)vic_slot) || GetFileAttributesA("t2r-duel-shared-clock.txt") != INVALID_FILE_ATTRIBUTES)) {   // (melee_beat.c: a beat RESULT pair starts at PLAY_AT on the victim)
        float ow = psync_oneway((int)vic_slot); if (ow > 120.0f) ow = 120.0f;
        if (ow >= 15.0f) { g_ps.t0 += ow; g_ps.clk_shift = ow; xlog("psync: u%08x shared clock - our move clock starts %.0f ms from now (the victim's START arrival)", g_ps.uid, ow); }
    }
    if (!psync_play()) { memset(&g_ps, 0, sizeof g_ps); return 0; }
    psync_send(PS_OP_START, 0, 0xff);
    g_ps.resend = 1; g_ps.start_ms = psync_ms(); g_ps.ack_cap = g_ps_ack_cap[vic_slot];
    xlog("psync: u%08x START sent to all (victim slot %u, one-way to it ~%.0f ms%s)", g_ps.uid, vic_slot, psync_oneway((int)vic_slot),
         g_ps_rtt[vic_slot] > 0 ? "" : ", not measured yet");
    return 1;
}

// ---- end / abort
static void psync_summary(const char *why) {
    xlog("psync: u%08x %s - role %d, %.0f ms (move time %.0f), frames %llu; our-view error vs the clip's placement (ap o inv(apReference)) "
         "after the blend-in: attacker max %.2f m (mean %.2f, n %d), victim max %.2f m (mean %.2f, n %d); during the blend-in max %.2f / %.2f m. "
         "Compare the 'psync sync' lines of both logs.",
         g_ps.uid, why, g_ps.role, psync_ms() - g_ps.t0 - g_ps.skip_ms, psync_ms() - g_ps.t0, (unsigned long long)(g_frame - g_ps.start_frame),
         g_ps.max_err[0], g_ps.n_err[0] ? g_ps.sum_err[0] / g_ps.n_err[0] : 0.0f, g_ps.n_err[0],
         g_ps.max_err[1], g_ps.n_err[1] ? g_ps.sum_err[1] / g_ps.n_err[1] : 0.0f, g_ps.n_err[1], g_ps.max_err_bl[0], g_ps.max_err_bl[1]);
    if (g_ps.flags & PS_F_LETHAL)
        xlog("victim root: u%08x summary - victim body vs its clip after the kill max %.2f m; our body placed by psync %u frames, layer lost %d time(s), "
             "wall holds %d", g_ps.uid, g_ps.max_err_dead[1], g_ps.own_drv_n, g_ps.lost_n[1], g_ps.wall_hits);
}
// ---- Wall-pair victim hand-off (v5-crash2, A/B v5-int12 B log 15278-15800).
// The wall pairs (duel PIN blows, wall takedowns) are authored with the victim's root 0.13-0.25 m in front of the wall frame (re/contextual-downs.md
// "authored travel": pinned at 0.13-0.25 m; SP's ap on the surface, the NPC's back on the wall, its capsule ignored during the pair). The attacker's
// hand plants on that wall (hwall), so the pair cannot be moved off the surface without breaking the contact. Our PLAYER's character controller
// cannot stand there: its capsule settles ~0.45-0.65 m in front of the surface (every pin -hit hand-off in B i10: body 0.25 -> 0.45-0.49 m, a
// 0.17-0.25 m one-frame snap; B c2: -> 0.66 m, 0.32-0.42 m). At the hand-off the engine gives the body back to the controller, which resolves the
// overlap in 1-3 frames ('dtl: SNAP slot 1 ... the engine: animate_ align / locomotion') - normally toward the room (the snap), and in i12 through
// a 0.23 m wall (292.45 -> 293.43 = 0.73 m BEHIND the surface, fall out of the level, the exe+25bcfd4 crash chain).
// The hand-off of OUR victim body from a wall pair is therefore ours: from the frame after the half ends, the body is moved from where the clip left it
// onto the room-side spot (the same xz along the wall, pushed out to WALLHO_Z in front of the surface) in steps of at most WALLHO_STEP per frame
// (smoothstep, 0.25 -> 0.50 m = 5 frames), each one a teleport-player - it moves the character controller with the body, so the controller never
// resolves the overlap on its own (no snap, no wall crossing) and locomotion cannot carry the body elsewhere in between.
// v5-int16 A/B (B [10709]-[10736]): the first version eased the body with set-object-locator for 420 ms and teleported at the end - the controller
// and the player's own run (sprint 4.4 m/s) carried the body 1.26 m away under the ease, and the final teleport was a visible 1.26-1.42 m jump.
// set-object-locator does not move the controller: only teleport-player does, so every step is one. (A teleport during the fading half: the
// attacker's abort hand-off, psync_own_att_free, does the same; the earlier bind pose was a teleport into a half still playing.)
// A body already >= WALLHO_Z in front of the surface does not overlap it: nothing is done. A new move taking the body ends the steps (its pair places
// the body). Alive and not going down only (a down / death owns the body).
// t2r-no-wallho.txt next to the exe = the engine's own resolution (the old snap).
// Safety net, after the drive: a body > 0.20 m behind the surface within 1.6 m of the hand-off spot (1.5 s) goes back to the room-side spot -
// logged as a FAULT; with the drive it should never fire.
#define WALLHO_Z 0.50f
#define WALLHO_STEP 0.06f
// (the pin still had flicker; A/B 176 B [234824]-[234989], [236284]-[236308]): every pin blow ends the previous pair with the attacker's SENDER-CUT abort and
// starts the next pair of the SAME wall in the same frame. The hand-off armed on the abort stepped our victim body out 0.28 -> 0.50 m (teleport-player) for the frame or
// two before the new pair's PLAY took it back: 'dtl: SNAP slot 1 0.20-0.25 m in 1 frame, teleport-player from ext+162c4e' x2 per blow, 5 blows = the victim pops in and out
// on every punch. A SENDER-CUT abort now waits WALLHO_CUT_WAIT frames before the first step; a new pair arriving inside it ends the hand-off with no write.
// t2r-no-wallho-wait.txt = the old immediate steps.
#define WALLHO_CUT_WAIT 3
static struct { int on, drive; uint32_t uid; uint64_t f0, f_check, f_end, f_go; int k, n; float ap[3], fwd[2], hz, hx, hy, pos[3], from[8], to[3]; } g_wallho;
static void wallho_arm(const char *why) {
    g_wallho.on = 0; g_wallho.drive = 0; g_wallho.f_go = 0;
    if (why && !strcmp(why, "a new move")) return;      // (the next pair takes the body at once: nothing to hand to the engine)
    if (g_ps.ent_vic != SID_PLAYER || g_ps.kind != PS_CTXDOWN || !cd_wall_move(g_ps.move)) return;
    if (g_downed || g_down_at || g_down_dying || local_hp() <= 0.0f || psync_own_dead_now()) return;
    if (GetFileAttributesA("t2r-no-wallho.txt") != INVALID_FILE_ATTRIBUTES) return;
    float lb[16]; const float *l = player_locator(lb);
    if (!l || !ps_loc_ok(l)) return;
    const float *q = g_ps.ap + 3;      // ap forward = q * (0,0,1) (out of the wall)
    float fx = 2.0f * (q[0] * q[2] + q[3] * q[1]), fz = 1.0f - 2.0f * (q[0] * q[0] + q[1] * q[1]), fn = __builtin_sqrtf(fx * fx + fz * fz);
    if (fn < 0.5f) return;
    g_wallho.fwd[0] = fx / fn; g_wallho.fwd[1] = fz / fn;
    memcpy(g_wallho.ap, g_ps.ap, 12);
    float dx = l[0] - g_ps.ap[0], dz = l[2] - g_ps.ap[2];
    g_wallho.hz = dx * g_wallho.fwd[0] + dz * g_wallho.fwd[1];                 // in front of the surface
    g_wallho.hx = dx * g_wallho.fwd[1] - dz * g_wallho.fwd[0];                 // along it
    g_wallho.hy = l[1];
    memcpy(g_wallho.pos, l, 12);
    memcpy(g_wallho.from, l, sizeof g_wallho.from);
    float tz = g_wallho.hz > WALLHO_Z ? g_wallho.hz : WALLHO_Z;
    g_wallho.to[0] = g_wallho.ap[0] + g_wallho.fwd[0] * tz + g_wallho.fwd[1] * g_wallho.hx;
    g_wallho.to[1] = l[1];
    g_wallho.to[2] = g_wallho.ap[2] + g_wallho.fwd[1] * tz - g_wallho.fwd[0] * g_wallho.hx;
    float sx = g_wallho.to[0] - l[0], sz = g_wallho.to[2] - l[2], sd = __builtin_sqrtf(sx * sx + sz * sz);
    g_wallho.f0 = g_frame; g_wallho.uid = g_ps.uid; g_wallho.on = 1;
    if (why && strstr(why, "SENDER-CUT") && GetFileAttributesA("t2r-no-wallho-wait.txt") == INVALID_FILE_ATTRIBUTES) g_wallho.f_go = g_frame + WALLHO_CUT_WAIT;
    if (g_wallho.hz >= WALLHO_Z || sd < 0.02f) {          // no overlap with the surface: the engine takes the body as it is (no snap to resolve)
        g_wallho.drive = 0; g_wallho.f_check = g_frame + 2; g_wallho.f_end = g_frame + 90;
        xlog("wall hand-off: u%08x our victim body %.2f m in front of the wall pair's surface - clear of it, handed to the engine as it stands", g_ps.uid, g_wallho.hz);
        return;
    }
    g_wallho.k = 0; g_wallho.n = (int)(sd / WALLHO_STEP + 0.999f); if (g_wallho.n < 3) g_wallho.n = 3;
    g_wallho.drive = 1; g_wallho.f_check = 0; g_wallho.f_end = 0;
    xlog("wall hand-off: u%08x our victim body %.2f m in front of the wall pair's surface (%.2f m along it) - stepped out to %.2f m over %d frames (teleport-player, <= %.2f m per frame: "
         "the controller never resolves the wall overlap itself)", g_ps.uid, g_wallho.hz, g_wallho.hx, tz, g_wallho.n, sd / (float)g_wallho.n * 1.5f);
}
static void wallho_tick(void) {
    if (!g_wallho.on) return;
    if (match_substate() != 6 || g_ps.role || g_downed || g_down_dying || local_hp() <= 0.0f) {
        if (g_wallho.drive) xlog("wall hand-off: u%08x drive ended early (%s) - the body is %s's", g_wallho.uid, g_ps.role ? "a new move" : "down / dead / not in a match", g_ps.role ? "the new pair" : "the engine");
        g_wallho.on = 0; g_wallho.drive = 0; return;
    }
    float lb[16]; const float *l = player_locator(lb);
    if (!l || !ps_loc_ok(l)) return;
    if (g_frame < g_wallho.f_go) return;       // (a SENDER-CUT abort: the next pin pair may take the body this frame - no step yet)
    if (g_wallho.drive) {
        g_wallho.k++;
        float u = (float)g_wallho.k / (float)g_wallho.n, w = u * u * (3.0f - 2.0f * u);
        float p[3] = {g_wallho.from[0] + (g_wallho.to[0] - g_wallho.from[0]) * w, g_wallho.from[1], g_wallho.from[2] + (g_wallho.to[2] - g_wallho.from[2]) * w};
        float ex = l[0] - p[0], ez = l[2] - p[2];
        // ps42 K1 (rec41a B [13146]-[13149], clip 45.70 s: the pin escape cut the wall pair, this stepper started its 4 frames; [13147] the test bot's own step
        // "#6 teleport 108.95 286.82" moved the body 8.4 m ([13148] 'pos-jump moved 8.36 m'); [13149] this stepper's last absolute step put it 8.2 m back - the
        // single alien frame). The steps are <= 0.09 m: a body more than 1 m off the step is somebody else's move (teleport / respawn) - the stepper ends, nothing
        // is written. t2r-wallho-far-old.txt = old. [TUNING ps42] 1.0 m
        if (ex * ex + ez * ez > 1.0f * 1.0f && GetFileAttributesA("t2r-wallho-far-old.txt") == INVALID_FILE_ATTRIBUTES) {
            xlog("wall hand-off: u%08x step %d of %d dropped - our body is %.2f m off the step (another writer moved it: teleport / respawn); the stepper ends, the body stays where it was put (ps42)",
                 g_wallho.uid, g_wallho.k, g_wallho.n, __builtin_sqrtf(ex * ex + ez * ez));
            g_wallho.on = 0; g_wallho.drive = 0; return;
        }
        mo_teleport(p, l + 4, MO_SRC("paired.wallho_step"), 0);
        if (g_wallho.k >= g_wallho.n) {
            xlog("wall hand-off: u%08x stepped out onto the room-side spot %.2f %.2f %.2f in %d frames (the body read %.2f m off the last step) - the engine's from here",
                 g_wallho.uid, p[0], p[1], p[2], g_wallho.n, __builtin_sqrtf(ex * ex + ez * ez));
            g_wallho.drive = 0; g_wallho.f_check = g_frame + 2; g_wallho.f_end = g_frame + 90;
        }
        return;
    }
    if (g_frame > g_wallho.f_end) { g_wallho.on = 0; return; }
    if (g_frame < g_wallho.f_check) return;
    float dx = l[0] - g_wallho.ap[0], dz = l[2] - g_wallho.ap[2];
    float z = dx * g_wallho.fwd[0] + dz * g_wallho.fwd[1];
    float mx = l[0] - g_wallho.pos[0], mz = l[2] - g_wallho.pos[2], moved = __builtin_sqrtf(mx * mx + mz * mz);
    if (moved > 1.6f) { g_wallho.on = 0; return; }
    if (z >= -0.20f) return;
    mo_teleport(g_wallho.to, l + 4, MO_SRC("paired.wallho_fault"), 0);
    xlog("wall hand-off: FAULT u%08x our body is %.2f m BEHIND the wall pair's surface after the hand-off (now %.2f %.2f %.2f, %.2f m below it, %llu frames after it) - "
         "teleport-player back to the room-side spot %.2f %.2f %.2f", g_wallho.uid, -z, l[0], l[1], l[2], g_wallho.hy - l[1], (unsigned long long)(g_frame - g_wallho.f0),
         g_wallho.to[0], g_wallho.to[1], g_wallho.to[2]);
    g_wallho.on = 0;
}
static void vdf_limp(const char *why);
static int g_vdf_limp_done, g_vlw_armed, g_vdf_dump_left;
static void explus_cut(const char *why);        // t2r-ext.c (explus.c): the execution sound design plus stops with a cut move
static void psync_finish(const char *why, int stop_halves) {
    if (!g_ps.role) return;
    // interrogation end (the interrogator got teleported weirdly, A [60930]-[60951]: the move ended (clip over) inside our attacker blend-out drive's window;
    // psync_finish cleared g_ps with the drive still placing the body, the engine's player state was left behind and its locomotion delta (-1.3 1.7, growing 0.5 m a
    // frame) carried the body 5.4 m). Any end, not only an abort, hands the driven body to the engine at its placed spot first.
    psync_own_att_free("move end");
    if (stop_halves) explus_cut(why);          // an aborted move: its layered sounds stop (a normal end lets the tail ring out)
    if (g_ps.kind == PS_REVIVE) rv_ps_ended(why, stop_halves);      // (g_ps is still valid: the revive's own state is reset here)
    if (g_ps.kind == PS_BODYSHIELD) bs_ps_ended(why, stop_halves);  // (bodyshield.c: the grab's own state on this client)
    g_ps_end40_ms = psync_ms(); g_ps_end40_vic = g_ps.ent_vic;      // ps40 D3: the body a victim half was on until now (ps_take_blend40)
    if (g_ps.ent_vic == SID_PLAYER) vdf_limp(why);      // limp (kept half) / the deferred Death-setup part in any case
    g_vdf_limp_done = 0; g_vlw_armed = 0; g_vdf_dump_left = 0;
    for (int s = 0; s < T2R_MAX_PEERS; s++)     // (a corpse held from an earlier move stays held: psync_corpse_tick ends it)
        if (g_ps_pup[s].h && !(g_ps_pup[s].corpse && s != g_ps.att && s != g_ps.vic)) psync_pup_release(s, why, stop_halves);
    if (g_ps.ent_att == SID_PLAYER && !g_ps.out_done[0]) psync_stop(SID_PLAYER, g_ps.att_sid, ps_out_blend());     // attacker half: always (see psync_pup_release) unless it already fades
    if (stop_halves && g_ps.ent_vic == SID_PLAYER) psync_stop(SID_PLAYER, g_ps.vic_sid, ps_out_blend());   // abort: the victim half blends out too
    if (g_ps.ent_vic == SID_PLAYER) wallho_arm(why);          // a wall pair: the engine takes the body back now - watch it does not end up behind the wall
    tc_finish(why);                                           // v5-fb2: travel clamp summary + our clipped body handed to the engine
    psync_summary(why);
    memset(&g_ps, 0, sizeof g_ps);
}
static struct { uint64_t sid, ms; float ph, dur; uint32_t uid; } g_ps47_cut;   // ps47: the -hit victim half a SENDER-CUT took from our body (melee_duel.c mdu_fw_vic_hold)
static void bb_cancel_pair(int a, int v);   // bloodbuild.c
static void psync_abort(const char *why, int notify) {
    if (!g_ps.role) return;
    // a third party's copy of a move belongs to its two players: it never broadcasts an ABORT (slot 0 watched u02000003 as a
    // third party, started its own stomp, "a new move" broadcast that uid's ABORT and slot 2's execution of us was cut mid-move)
    if (notify && g_ps.role == 3) notify = 0;
    // (low cover pin escape, then the victim teleported behind the attacker, A 42455: 1.21 m in one frame at the hand-off): an abort while
    // our attacker blend-out drive runs left the engine's player state behind; hand it the driven spot first (as the drive's own end does).
    psync_own_att_free("abort");
    dtail_abort(why);                                           // a DODGED abort - the swing clip's tail plays on the attacker (own body / bystander puppet) as well as the 0.3 s stop of the half
    dtl_note_abort(why);                                        // duel timeline: a duel pair cut before its hand-off is a TRIM
    if (g_ps.kind == PS_CTXDOWN && why && (strstr(why, "dodge") || strstr(why, "DODGED") || strstr(why, "REFUSED") || strstr(why, "BUSY") || strstr(why, "NOPLAY") || strstr(why, "never acknowledged"))) bb_cancel_pair(g_ps.att, g_ps.vic);   // bloodbuild.c: no blood for a move that never reached its kill frame
    xlog("psync: u%08x ABORT (%s)%s", g_ps.uid, why, notify ? " - sent to all" : "");
    if (notify) psync_send(PS_OP_ABORT, 0, 0xff);
    if (notify) xlog("psync: u%08x ABORT SENT reason SENDER-CUT (0): %s | move time %.0f ms, role %d kind %d", g_ps.uid, why, psync_ms() - g_ps.t0, g_ps.role, g_ps.kind);
    psync_finish(why, 1);
}

// ---- receive
// 1 = a copy we already have (same sender, uid not older than PS_SEEN_MS), else it is recorded (state st) and 0. *state = its entry's st.
static int psync_seen_st(uint32_t uid, uint32_t from, int st, int *state) {
    double now = psync_ms();
    for (int i = 0; i < 16; i++)
        if (g_ps_seen[i].uid == uid && g_ps_seen[i].from == (uint8_t)from && now - g_ps_seen[i].ms < PS_SEEN_MS) { if (state) *state = g_ps_seen[i].st; return 1; }
    g_ps_seen[g_ps_seen_i].uid = uid; g_ps_seen[g_ps_seen_i].from = (uint8_t)from; g_ps_seen[g_ps_seen_i].st = (uint8_t)st; g_ps_seen[g_ps_seen_i].ms = now;
    g_ps_seen_i = (g_ps_seen_i + 1) & 15;
    return 0;
}
static int psync_seen(uint32_t uid, uint32_t from) { return psync_seen_st(uid, from, 1, NULL); }
static void psync_seen_set(uint32_t uid, uint32_t from, int st) {
    for (int i = 0; i < 16; i++) if (g_ps_seen[i].uid == uid && g_ps_seen[i].from == (uint8_t)from) g_ps_seen[i].st = (uint8_t)st;
}
static void psync_abort_to(const psync_wire *w, int reason) {      // a refusal of w (ABORT back to everyone, with the reason)
    if (!g_send_tramp) return;
    psync_wire a = *w; a.op = PS_OP_ABORT; a.resend = (uint8_t)reason;
    xlog("psync: u%08x ABORT SENT reason %s (%d) to the attacker slot %u | guards: downed %d dying %d down_at %d exec %d running u%08x role %d", w->uid, psync_ab_name((unsigned)reason), reason, w->att, g_downed, g_down_dying, g_down_at != 0, g_exec_until != 0, g_ps.uid, g_ps.role);
    g_send_tramp(MSG_PSYNC, (uint8_t *)&a, sizeof a, 0xff);
}
static int gx_victim_begin(uint32_t slot, int pair, uint64_t move, float kill_s, uint64_t skipf);   // t2r-ext.c
static int cd_victim_begin(uint32_t slot, float end_s, uint64_t skipf);     // ctxdown.c
static void cd_victim_cancel(const char *why);
static void cd_aborted(int role, uint32_t from);
static void gx_third_party(int pair, const float *ap, float kill_s, uint64_t move);                               // t2r-ext.c
static uint32_t g_third_att_slot;
static void shiv_refund(const char *why);                // t2r-ext.c: the shiv back after a refused shiv kill
static void gx_abort(const char *why, int notify);
// the START names the weapon the executioner's clip needs in the hand (the held gun of a gun execution, the melee weapon of an armed
// one, 0 = empty hands). The executioner's own client forced it (instant draw) before sending; its weapon sync follows, but a lag shows the
// clip with the wrong prop on this screen. The puppet's current weapon is compared with the START's: a mismatch is logged ("exec weapon: MISMATCH
// (remote)") and the synced held id (peer+0x91, what winmm's give block compares) is set to it, so the puppet switches through the same path as
// any weapon switch right now. The sender's own sync restores the pre-move weapon after the move (its xr_finish), the same way.
static void psync_att_weapon(const psync_wire *w, uint32_t from) {
    typedef uint8_t *(*fn_peer)(uint32_t);
    if ((w->kind != PS_GUN_EXEC && w->kind != PS_MELEE_EXEC) || !w->weapon || w->weapon == ~0ULL || from >= T2R_MAX_PEERS) return;
    uint8_t *peer = ((fn_peer)t2r_peer)(from);
    if (!peer || IsBadWritePtr(peer + 0x91, 8)) return;
    uint64_t h = *(uint64_t *)(peer + 0x60), have = *(uint64_t *)(peer + 0x91), cur = 0;
    uint8_t *npc = h ? pst_npc(h) : NULL;
    if (npc) cur = pst_sid_of(pst_current(npc));
    if (cur == w->weapon && have == w->weapon) return;
    // (melee execution with the gun equipped in the smashing animation of a pipe): the puppet carried a pistol (6f9e0b5e..) while the
    // synced held id already was the bat (12058893..): writing peer+0x91 = the same value never re-runs winmm's give block (it compares with the last given,
    // peer+0x9e0), so the bat execution played with the gun in the hand. When the puppet's hand is wrong, the last given is cleared too (ctxdown.c
    // cd_dis_pup_give's re-give idiom): winmm destroys the held item and gives + attaches the clip's weapon this frame.
    int wrong = !cur || base_weapon(cur) != base_weapon(w->weapon);
    xlog("exec weapon: MISMATCH (remote) - slot %u's puppet carries %016llx (synced held id %016llx), the %s clip needs %016llx: synced id set to it%s",
         from, (unsigned long long)cur, (unsigned long long)have, w->kind == PS_GUN_EXEC ? "gun" : "melee", (unsigned long long)w->weapon,
         wrong && !IsBadWritePtr(peer + 0x9e0, 8) ? ", give block re-armed (wrong item in the hand)" : "");
    memcpy(peer + 0x91, &w->weapon, 8);
    if (wrong && !IsBadWritePtr(peer + 0x9e0, 8)) *(uint64_t *)(peer + 0x9e0) = 0;
}
static int psync_begin_remote(const psync_wire *w, uint32_t from, float skip_ms, const char *how) {
    uint32_t self = psync_self();
    int role = w->vic == self ? 2 : w->att == self ? 0 : 3;
    if (!role) return 0;
    {   // peer msg trust: a kind we have, and the right company - only a revive is a teammate's move on us, every other paired move on us is an enemy's
        // (g_test_same_team / friendly fire off: the dev setups put everybody on one team)
        static uint64_t bad_ms; uint64_t tn = GetTickCount64();
        if ((w->kind < PS_GUN_EXEC || w->kind > PS_BODYSHIELD) && pt_deny(PTK_psync_kind, from)) {
            if (pt_log_due(&bad_ms, tn)) xlog("psync: u%08x from slot %u has an unknown kind %u - dropped", w->uid, from, w->kind);
            return 1;
        }
        if (role == 2 && from < T2R_MAX_PEERS && !g_test_same_team && !g_ff_off && (same_team(from, self) != (w->kind == PS_REVIVE)) && pt_deny(PTK_psync_team, from)) {
            if (pt_log_due(&bad_ms, tn)) xlog("psync: u%08x kind %u from slot %u refused - %s", w->uid, w->kind, from, w->kind == PS_REVIVE ? "a revive from an enemy" : "a move on us from a teammate");
            return 1;                                                      // (no ABORT back: an honest sender never gets here, a forged one gets no echo)
        }
    }
    if (g_ps.role == 3 && role != 3) {
        // a bystander's copy of someone else's move must not make us refuse a move that is OURS (4-8 player matches: a third party watching
        // an execution used to answer a START naming it as the victim with an ABORT to all, cutting that execution): drop the copy, quietly
        xlog("psync: u%08x (a move of ours) arrives while we only watch u%08x as a third party - the watched copy is dropped", w->uid, g_ps.uid);
        psync_abort("a move of ours starts", 0);
    }
    // duel timeline (melee_duel_tl.c): a duel blow of theirs on us while our own duel blow on them runs = a trade, decided by the two contact times on the
    // shared clock (the earlier one wins on both screens; a tie -> the lower slot). Losing: our pair yields (ABORT to all, its halves blend out) and theirs plays.
    if (role == 2 && pe45_held(1) && from == (uint32_t)g_ps.vic) {      // ps45 item 1: the escaper's escape pair takes our held attacker half in this frame
        xlog("pin escape hold (ps45): u%08x our held attacker half handed straight to the escape pair u%08x after %llu ms (no free pose between)", g_ps.uid, w->uid, (unsigned long long)(GetTickCount64() - g_pe45.t0));
        memset(&g_pe45, 0, sizeof g_pe45);
        psync_abort("pin escaped", 0);
    }
    if (role == 2 && g_ps.role == 1 && dtl_trade_yield(w, from)) psync_abort("dtl: trade lost - their blow landed first", 1);
    // (melee needs blending; live 165 logs: 163 of 758 incoming STARTs were dropped this way = the next blow of a combo never
    // played, the bodies snapped when the following one did): the SAME two players' next DUEL blow, from the same attacker, replaces our lagging copy of
    // their previous one - its sender already ended it for this one ("a new move"). The running copy blends out (local abort, no ABORT sent back)
    // and the new pair starts with its normal blend-in. A START from anybody else still meets the one-move rule. t2r-ps-no-chain-replace.txt = old rule.
    if (g_ps.role && (role == 2 || role == 3) && g_ps.role == role && g_ps.att == w->att && g_ps.vic == w->vic && w->uid != g_ps.uid && g_ps.kind == PS_CTXDOWN && w->kind == PS_CTXDOWN && mdu_move(g_ps.move) && mdu_move(w->move)
        && GetFileAttributesA("t2r-ps-no-chain-replace.txt") == INVALID_FILE_ATTRIBUTES) {
        xlog("psync: u%08x from slot %u (%s) replaces u%08x of the same pair (role %d) - the running copy blends out, the next blow plays", w->uid, from, how, g_ps.uid, role);
        psync_abort("chain: the same pair's next move", 0);
    }
    // ps46b pull-out lead (melee_pullout.c PUL_LEAD_MS): the attacker starts the grapple PUL_LEAD_MS before the drag's pair end (it ended its own drag copy
    // locally), so its START reaches us while our copy of the drag still runs. The same two players' pull-out grapple / kill START replaces our running
    // pull-out drag / kill copy (local abort, the new pair crossfades in) instead of being refused as BUSY - the body is never let go between the two.
    if (g_ps.role && (role == 2 || role == 3) && g_ps.role == role && g_ps.att == w->att && g_ps.vic == w->vic && w->uid != g_ps.uid && g_ps.kind == PS_CTXDOWN && w->kind == PS_CTXDOWN) {
        const char *rn = pul_pair_name(g_ps.move), *nn = pul_pair_name(w->move);
        // (a recording: log line 252083 ABORT (contextual down hand-off), 252092 pu-fail START, 252094 "pose pop (rise): slot 3 pelvis 0.13 -> 0.84"): the grapple's
        // successor (pu-fail / pu-ok) takes the running grapple copy the same way - the victim is never let go between them. t2r-pullout-chain-hold-off.txt = old rule.
        int chg = rn && nn && !strncmp(rn, "pu-grap", 7) && (!strncmp(nn, "pu-fail", 7) || !strncmp(nn, "pu-ok", 5)) && GetFileAttributesA("t2r-pullout-chain-hold-off.txt") == INVALID_FILE_ATTRIBUTES;
        if (rn && nn && (chg || ((!strncmp(rn, "pu-drag", 7) || !strncmp(rn, "pu-kill", 7)) && (!strncmp(nn, "pu-grap", 7) || !strncmp(nn, "pu-kill", 7))))) {
            xlog("ps46b lead: u%08x %s from slot %u (%s) replaces our running copy u%08x %s at move time %.0f ms (role %d) - pull-out chain, no free pose between", w->uid, nn, from, how, g_ps.uid, rn, psync_ms() - g_ps.t0, role);
            psync_abort("pull-out chain: the next segment takes over", 0);
        }
    }
    if (g_ps.role) {
        // one move at a time (ND: the older start wins; here the running one does): the victim refuses a second
        xlog("psync: u%08x from slot %u (%s) while u%08x runs - %s", w->uid, from, how, g_ps.uid, role == 2 ? "refused (ABORT back)" : "ignored");
        if (role == 2) psync_abort_to(w, PS_AB_BUSY);
        return 1;
    }
    float apw[7], a8[8]; memcpy(apw, w->ap, sizeof apw); ps_ap8(apw, a8);
    if (!ps_loc_ok(a8) || !__builtin_isfinite(w->kill_s) || !__builtin_isfinite(w->dur_s) || w->dur_s > 30.0f || (w->kill_s > 60.0f && pt_deny(PTK_wire, from))) {
        xlog("psync: u%08x from slot %u - bad values (ap %.3g %.3g %.3g, kill %.3g, dur %.3g) - dropped", w->uid, from, w->ap[0], w->ap[1], w->ap[2], w->kill_s, w->dur_s);
        return 1;
    }
    float me[16];
    const float *ml = player_locator(me);
    if (ml && role == 2) {
        float dx = ml[0] - w->ap[0], dz = ml[2] - w->ap[2];
        if (dx * dx + dz * dz > 8.0f * 8.0f) {
            xlog("psync: u%08x - the ap is %.1f m from us (victim) - refused, ABORT back", w->uid, __builtin_sqrtf(dx * dx + dz * dz));
            psync_abort_to(w, PS_AB_FAR);
            return 1;
        }
    }
    if (skip_ms < 0) skip_ms = 0;
    // v5 (kick / hard punch finishers played right away, skipping the first half of the anim (the windup)): a duel
    // finisher's SP intro (segment 0) plays from its frame 0 on the victim's and every bystander's screen too. The START's lateness (the sender's move time +
    // one-way) is absorbed SP-style inside the windup: our move clock keeps the shared time (t0 = now - late), the attacker half runs the intro faster
    // (x intro / (intro - late), <= x1.35), so the hand-over to the -sync pair lands on the same move time as on the attacker's screen. A sender that passed
    // the intro over (its t2r-duel-fin-no-intro.txt: move time >= the intro) -> the -sync pair from its frame 0 as before.
    float fin_late = -1.0f, fin_seg0 = 0.0f;
    if ((role == 2 || role == 3) && w->kind == PS_CTXDOWN && cd_mf_intro_move(w->move)) {
        fin_seg0 = cd_seg0_ms(w->move);
        if (fin_seg0 > 0.0f && (float)w->sent_ms < fin_seg0 - 1.0f) fin_late = skip_ms < fin_seg0 - 50.0f ? skip_ms : fin_seg0 - 50.0f;
        else if (fin_seg0 > 0.0f && role == 2 && skip_ms < fin_seg0) skip_ms = fin_seg0;      // (intro passed over: the -sync pair at frame 0, the old victim start)
    }
    // (client-side timing) an open-ground duel pair starts at frame 0 on the victim too - the whole anticipation plays, no 5-frame cut-in
    // (NOT a dodge counter - the dodger plays it from p0 = 0.24 s in; the countered side at frame 0 ran 0.22 s + one-way behind, the counter
    // blow landed 225 ms before its clip showed the contact (A/B int112 'lands on us ... -225 ms'). t2r-dc-vic-from0.txt = old)
    if (role == 2 && w->kind == PS_CTXDOWN && cd_local_move(w->move) && fin_seg0 <= 0.0f && GetFileAttributesA("t2r-duel-ap-sender.txt") == INVALID_FILE_ATTRIBUTES
        && (!cd_counter_move(w->move) || GetFileAttributesA("t2r-dc-vic-from0.txt") != INVALID_FILE_ATTRIBUTES)) skip_ms = 0;
    // melee_duel_contact.c: a duel PIN blow (mp-*-wall / -low-cover-, surface frame) on us starts at frame 0 too - its replica swing reaches the contact
    // when this START arrives, so the reaction starts on the contact frame (the 5-frame skip cut the impact at +35 ms). t2r-duel-no-contact.txt = the skip
    if (role == 2 && w->kind == PS_CTXDOWN && mdu_move(w->move) && skip_ms > 1.0f && mct_pin_from0(w->move, skip_ms)) skip_ms = 0;
    if (fin_late >= 0.0f) skip_ms = 0;                     // (the halves start at phase 0; the clock shift + rate below take the lateness)
    if (w->dur_s > 0 && skip_ms > w->dur_s * 500.0f) skip_ms = w->dur_s * 500.0f;
    if (role == 2 && w->kind == PS_CTXDOWN && mdu_move(w->move) && skip_ms > 1.0f && dtl_on()) dtl_trim("a duel pair START on us", (int)skip_ms, "phase skip by the latency (t2r-duel-ap-sender.txt)");
    // smooth:noskip (live 165: START skip p50 81 ms = the receiver jumped that far into the clip): a late duel START plays from frame 0 and the halves absorb the
    // lateness with a playback rate up to x1.15 (psync_rate, g_ps.catch_ms) instead of a phase jump; our move clock keeps the shared time (t0 = now - late) like the v5
    // finisher intro. Lateness beyond PS_CATCH_MAXLAG_MS (what x1.15 absorbs in ~600 ms) is still skipped, only that remainder. t2r-smooth-noskip-off.txt = skip all of it.
    float catch_ms = 0.0f;
    int byst = role == 3 && w->kind == PS_CTXDOWN && !byst_old();
    // (brawl): a pin blow START with the pinner's windup replica running on its puppet (MDPO_BYST): no x1.2 catch-up - the half starts at the sender's move time (the
    // replica covered the lead-in; the lateness is skipped into the clip). Without a replica the catch-up below stays.
    int byst_rep = byst && mpn_byst_pair(w->move) && mpn_byst_replica(w->att);
    if (byst_rep && skip_ms > 1.0f) { static int nlc; if (LOGCAP(nlc, 100)) xlog("byst: u%08x pin blow START %.0f ms late with its windup replica running on slot %d's puppet: no catch-up, the half starts at the sender's move time (+%.0f ms)", w->uid, skip_ms, w->att, skip_ms); }
    if ((role == 2 || role == 3) && w->kind == PS_CTXDOWN && (mdu_move(w->move) || byst) && fin_late < 0.0f && skip_ms > 1.0f && !smooth_off(0) && !byst_rep) {
        float tot = skip_ms, cap = byst ? PS_CATCH_BYST_MAXLAG_MS : PS_CATCH_MAXLAG_MS;
        catch_ms = tot < cap ? tot : cap; skip_ms = tot - catch_ms;
        if (byst) xlog("byst: u%08x bystander START %.0f ms late: %.0f ms absorbed at up to x%.2f from frame 0 (old rule: %.0f ms at x1.15, %.0f ms jumped), %.0f ms still skipped", w->uid, tot, catch_ms, 1.0f + PS_CATCH_BYST_RATE, tot < PS_CATCH_MAXLAG_MS ? tot : PS_CATCH_MAXLAG_MS, tot - (tot < PS_CATCH_MAXLAG_MS ? tot : PS_CATCH_MAXLAG_MS), skip_ms);
        xlog("smooth: noskip u%08x lateness %.0f ms: %.0f ms absorbed by playing from frame 0 at up to x%.2f, %.0f ms still skipped (was a %.0f ms jump)", w->uid, tot, catch_ms, 1.0f + PS_CATCH_RATE, skip_ms, tot);
    }
    memset(&g_ps, 0, sizeof g_ps);
    g_ps.role = role; g_ps.kind = w->kind; g_ps.flags = w->flags; g_ps.pair = w->pair; g_ps.uid = w->uid;
    g_ps.att = w->att; g_ps.vic = w->vic; g_ps.att_sid = w->att_clip; g_ps.vic_sid = w->vic_clip;
    memcpy(g_ps.ap, w->ap, sizeof g_ps.ap);
    float qn = __builtin_sqrtf(g_ps.ap[3] * g_ps.ap[3] + g_ps.ap[4] * g_ps.ap[4] + g_ps.ap[5] * g_ps.ap[5] + g_ps.ap[6] * g_ps.ap[6]);
    for (int i = 3; i < 7; i++) g_ps.ap[i] /= qn;
    g_ps.kill_s = w->kill_s; g_ps.dur_s = w->dur_s; g_ps.weapon = w->weapon; g_ps.move = w->move;
    if (g_pws_rx.ok && g_pws_rx.uid == w->uid) { g_ps.wsh_ok = 1; g_ps.wsh_dyn = (uint8_t)g_pws_rx.dyn; g_ps.wtend = g_pws_rx.tend; memcpy(g_ps.wS, g_pws_rx.S, sizeof g_ps.wS); g_pws_rx.ok = 0;
        xlog("pair shift: u%08x START carries a shift profile - start shift %.2f %.2f, %s over %.2f s", w->uid, g_ps.wS[0][0], g_ps.wS[0][1], g_ps.wsh_dyn ? "sliding" : "start only", g_ps.wtend); }
    g_ps.skip_ms = skip_ms; g_ps.t0 = psync_ms() - skip_ms - catch_ms; g_ps.catch_ms = catch_ms;
    uint64_t skipf = (uint64_t)((skip_ms + catch_ms) * 0.06f + 0.5f);       // real time in 1/60 s ticks (g_t60), independent of this client's fps
    if (fin_late >= 0.0f) {                                     // (v5: the duel finisher's intro, see above)
        g_ps.t0 = psync_ms() - fin_late; g_ps.ilate = fin_late; skipf = (uint64_t)(fin_late * 0.06f + 0.5f);
        float r = fin_late >= 10.0f ? fin_seg0 / (fin_seg0 - fin_late) : 1.0f;
        g_ps.irate = r > 1.35f ? 1.35f : r > 1.0f ? r : 0.0f;
        xlog("psync: u%08x FINISHER on a late screen (role %d): %.0f ms late (its move time %u + one-way %.0f) - the SP intro (%.0f ms) plays from phase 0 at x%.2f%s",
             w->uid, role, fin_late, w->sent_ms, psync_oneway((int)from), fin_seg0, g_ps.irate > 1.0f ? g_ps.irate : 1.0f,
             r > 1.35f ? " (capped: the hand-over cuts the intro's last frames, never its start)" : "");
    }
    if (g_ps.role == 2 && ((w->kind == PS_MELEE_EXEC && GetFileAttributesA("t2r-ps-exec-dodge.txt") != INVALID_FILE_ATTRIBUTES) || w->kind == PS_CTXDOWN) && !(w->kind == PS_CTXDOWN && msq_move(w->move)) && mdg_pair_dodged(from, w->move)) {   /* (live: a shivved player got out of it by dodging): a shiv / melee execution is uninterruptible - the victim's dodge press no longer refuses its START (t2r-ps-exec-dodge.txt = old) */   // melee_dodge.c: dodged in time (not a melee sequence pair: the blow already landed, it decides by the exchange; a DUEL pair is judged here: the dodger's press before the contact reached its screen wins, see melee_duel.c)
        psync_send(PS_OP_ABORT, PS_AB_DODGED, 0xff);
        memset(&g_ps, 0, sizeof g_ps);
        return 1;
    }
    // the owner of the victim's body decides (E executions: still downed, not already executed, ...)
    if (g_ps.role == 2 && (w->kind == PS_GUN_EXEC || w->kind == PS_MELEE_EXEC)) {
        g_gx_vic_weapon = w->kind == PS_GUN_EXEC ? w->weapon : 0;     // the executioner's weapon at the E press (gore class, drop)
        int vb = gx_victim_begin(from, w->kind == PS_MELEE_EXEC ? GX_MELEE_ID : w->pair, w->move, w->kill_s, skipf);
        g_gx_vic_weapon = 0;
        if (!vb) {
            xlog("psync: u%08x - we (victim) refuse it (not downed / executed already / switched off) - ABORT back", w->uid);
            psync_send(PS_OP_ABORT, PS_AB_REFUSED, 0xff);
            memset(&g_ps, 0, sizeof g_ps);
            return 1;
        }
    }
    if (g_ps.role == 2 && w->kind == PS_CTXDOWN) {                    // contextual melee down (ctxdown.c): we are the victim, the owner of our body decides
        if (!cd_victim_begin(from, w->kill_s, skipf)) {
            psync_send(PS_OP_ABORT, PS_AB_REFUSED, 0xff);
            memset(&g_ps, 0, sizeof g_ps);
            return 1;
        }
    }
    if (g_ps.role == 2 && w->kind == PS_REVIVE) {                     // the 2013 revive (revive2013.c): we are the revived, the owner of our body decides
        if (!rv_victim_begin(from, skipf)) {
            psync_send(PS_OP_ABORT, PS_AB_REFUSED, 0xff);
            memset(&g_ps, 0, sizeof g_ps);
            return 1;
        }
    }
    if (g_ps.role == 2 && w->kind == PS_BODYSHIELD) {                 // the BODYSHIELD grab (bodyshield.c): we are the grabbed, the owner of our body decides
        if (!bs_victim_begin(from, w->uid, w->move, skipf)) {
            psync_send(PS_OP_ABORT, PS_AB_REFUSED, 0xff);
            memset(&g_ps, 0, sizeof g_ps);
            return 1;
        }
    }
    if (g_ps.role == 3 && (w->kind == PS_GUN_EXEC || w->kind == PS_MELEE_EXEC))
    { g_third_att = psync_puppet(w->att); g_third_vic = psync_puppet(w->vic); g_third_att_slot = w->att; g_third_vic_slot = w->vic;   // the two bodies' puppets here (3D sounds, bystander gore)
        gx_third_party(w->kind == PS_GUN_EXEC ? w->pair : -1, apw, w->kill_s, w->move); }
    xlog("psync: u%08x START from slot %u (%s, copy %u, its move time %u ms) - role %d, one-way %.0f ms%s -> skip %.0f ms (%llu frames)",
         w->uid, from, how, w->resend, w->sent_ms, g_ps.role, psync_oneway((int)from), g_ps_rtt[from % T2R_MAX_PEERS] > 0 ? "" : " (default)", skip_ms,
         (unsigned long long)skipf);
    psync_att_weapon(w, from);
    if (!psync_play()) {
        if (g_ps.role == 3) xlog("psync: u%08x - BYSTANDER: the halves are NOT played on this screen (see the line above); sounds / gore / scoring of the move still run, both bodies keep their poses", w->uid);
        if (g_ps.role == 2) {
            xlog("psync: u%08x - halves not played here - ABORT back", w->uid);
            psync_send(PS_OP_ABORT, PS_AB_NOPLAY, 0xff);
            if (w->kind == PS_GUN_EXEC || w->kind == PS_MELEE_EXEC) { memset(&g_ps, 0, sizeof g_ps); gx_abort("halves not played", 0); }
            if (w->kind == PS_CTXDOWN) cd_victim_cancel("halves not played here");
            if (w->kind == PS_REVIVE) rv_victim_cancel("halves not played here");
            if (w->kind == PS_BODYSHIELD) bs_victim_cancel("halves not played here");
        }
        memset(&g_ps, 0, sizeof g_ps);
    } else {
        if (g_ps.role && g_ps.kind == PS_REVIVE) rv_ps_started();
        if (g_ps.role && g_ps.kind == PS_BODYSHIELD) bs_ps_started();
        if (g_ps.role == 2) { psync_send(PS_OP_ACK, 0, (uint8_t)from); xlog("psync: u%08x ACK sent to slot %u (we play the victim half)", w->uid, from); }
    }
    return 1;
}
static int psync_receive_legacy(uint32_t att_slot, int kind, const char *att_clip, const char *vic_clip, const float *ap7,
                                float kill_s, int pair, uint64_t weapon, uint64_t move) {
    psync_wire w;
    memset(&w, 0, sizeof w);
    w.op = PS_OP_START; w.ver = 0; w.kind = (uint8_t)kind; w.flags = PS_F_LETHAL; w.att = (uint8_t)att_slot; w.vic = (uint8_t)psync_self();
    w.pair = (uint8_t)pair; w.uid = (att_slot << 24) | 0xff0000 | (uint32_t)(g_frame & 0xffff);
    w.att_clip = fnv64(att_clip); w.vic_clip = fnv64(vic_clip);
    memcpy(w.ap, ap7, 28); w.kill_s = kill_s; w.weapon = weapon; w.move = move;
    return psync_begin_remote(&w, att_slot, psync_oneway((int)att_slot), "old MSG_GUN_EXEC");
}
// the kinds' own clean-up after psync_abort (the ABORT of the other side, or our own no-ACK timeout): shiv back before its kill frame, execution
// timeline off on both roles, ctx / revive state told
static void psync_after_abort(int role, int exec, int ctx_kind, int rv_kind, uint32_t from) {
    if (g_ps_abort_reason == PS_AB_DODGED && role == 1 && (exec || ctx_kind)) mdg_pair_refused_by_dodge(from);
    if (rv_kind) rv_aborted(role, from);
    if (exec && role == 1 && g_gx.shiv && !g_gx.shiv_paid && g_gx.kill_at && g_t60 < g_gx.kill_at) xlog("shiv: kept (victim refused / aborted before the kill frame, nothing was spent)");
    if (exec && (role == 1 || role == 2)) gx_abort(role == 1 ? "the victim refused / aborted" : "the executioner aborted", 0);
    if (ctx_kind) cd_aborted(role, from);
}
static int psync_recv(uint32_t from, const uint8_t *buf, uint64_t len) {
    if (!buf || len < 1 || from > T2R_MAX_PEERS - 1) return 1;
    if (buf[0] == PS_OP_PING && len >= 9) {
        uint8_t m[10]; memcpy(m, buf, 9); m[0] = PS_OP_PONG; m[9] = 1;          // (byte 9 = this build ACKs a START)
        if (g_send_tramp) g_send_tramp(MSG_PSYNC, m, len >= 10 ? 10 : 9, (uint8_t)from);
        return 1;
    }
    if (buf[0] == PS_OP_PONG && len >= 9) {
        double t; memcpy(&t, buf + 1, 8);
        if (len >= 10 && buf[9]) g_ps_ack_cap[from] = 1;
        double rtt = psync_ms() - t;
        if (rtt > 0 && rtt < 3000) {
            float old = g_ps_rtt[from];
            g_ps_rtt[from] = old > 0 ? old * 0.75f + (float)rtt * 0.25f : (float)rtt;
            static int n[T2R_MAX_PEERS];
            if (n[from]++ % 15 == 0) xlog("psync: rtt to slot %u %.0f ms (avg %.0f)", from, rtt, g_ps_rtt[from]);
        }
        return 1;
    }
    if (len < sizeof(psync_wire)) { xlog("psync: short message op %u (%llu bytes) from slot %u", buf[0], (unsigned long long)len, from); return 1; }
    psync_wire w;
    memcpy(&w, buf, sizeof w);
    if (w.op == PS_OP_START) {
        int st = 0;
        if (psync_seen_st(w.uid, from, 0, &st)) {       // a resend of one we have: the attacker still waits for our answer, repeat it
            if (w.vic == psync_self()) {
                if (st == 0 && g_ps.role == 2 && g_ps.uid == w.uid) psync_send(PS_OP_ACK, 0, (uint8_t)from);
                else if (st == 1) psync_abort_to(&w, PS_AB_REFUSED);
            }
            return 1;
        }
        if (w.att != from || w.vic > T2R_MAX_PEERS - 1) { xlog("psync: u%08x START from slot %u names attacker %u / victim %u - dropped", w.uid, from, w.att, w.vic); return 1; }
        g_ps_ack_cap[from] = 1;
        pws_trailer_read(w.uid, buf, len);
        psync_begin_remote(&w, from, (float)w.sent_ms + psync_oneway((int)from), "START");
        if (w.vic == psync_self() && !(g_ps.role == 2 && g_ps.uid == w.uid)) psync_seen_set(w.uid, from, 1);   // refused (the ABORT went out): a copy repeats it
        return 1;
    }
    if (w.op == PS_OP_ABORT) {
        psync_seen(w.uid, w.att);                       // a late START copy of it must not start it (keyed like the START: its sender)
        if (!g_ps.role || g_ps.uid != w.uid) { xlog("psync: ABORT u%08x from slot %u (not running here)", w.uid, from); return 1; }
        // only the move's own two players can abort it (an older build's third party still broadcasts one)
        if (from != (uint32_t)g_ps.att && from != (uint32_t)g_ps.vic) { xlog("psync: ABORT u%08x from slot %u ignored - not one of its players (att %d vic %d)", w.uid, from, g_ps.att, g_ps.vic); return 1; }
        if (pe45_held(1) && from == (uint32_t)g_ps.vic) {      // ps45 item 1: the escaper's "a new move" cut comes with its escape START - held for it (pe45_tick: 3 frames)
            if (!g_pe45.abort_f) { g_pe45.abort_f = g_frame ? g_frame : 1; xlog("pin escape hold (ps45): u%08x ABORT from the escaper slot %u - the held attacker half waits up to 3 frames for its escape START", w.uid, from); }
            return 1;
        }
        int exec = g_ps.kind == PS_GUN_EXEC || g_ps.kind == PS_MELEE_EXEC, role = g_ps.role;
        int ctx_kind = g_ps.kind == PS_CTXDOWN, rv_kind = g_ps.kind == PS_REVIVE;
        char why[64]; snprintf(why, sizeof why, "slot %u aborted it (reason %s %u)", from, psync_ab_name(w.resend), w.resend);
        // ps47 (clip 18-59-03: the animation got stuck before the finisher; A [13327]-[13376]): the attacker's finisher windup cuts the running -hit pair
        // (SENDER-CUT) and nothing played on our victim body for 816 ms. The cut -hit victim half on our own body is noted here (clip + phase) so the windup's
        // arrival (melee_duel.c mdu_fw_vic_hold) can keep it playing on our body until the finisher START. Only a SENDER-CUT of a ctxdown pair on our own body.
        if (role == 2 && ctx_kind && w.resend == 0 && g_ps.vic == (int)psync_self() && g_ps.vic_sid) {
            float ph = psync_phase(SID_PLAYER, g_ps.vic_sid);
            if (ph < 0.0f && g_ps.vic_dur > 0.05f) ph = (float)((psync_ms() - g_ps.t0) / 1000.0 / g_ps.vic_dur);
            g_ps47_cut.sid = g_ps.vic_sid; g_ps47_cut.ph = ph; g_ps47_cut.dur = g_ps.vic_dur; g_ps47_cut.ms = GetTickCount64(); g_ps47_cut.uid = g_ps.uid;
        }
        psync_abort(why, 0);
        g_ps_abort_reason = w.resend;
        psync_after_abort(role, exec, ctx_kind, rv_kind, from);
        g_ps_abort_reason = 0;
        return 1;
    }
    if (w.op == PS_OP_ACK) {
        if (g_ps.role == 1 && g_ps.uid == w.uid && from == (uint32_t)g_ps.vic && !g_ps.acked) {
            g_ps.acked = 1; g_ps_ack_cap[from] = 1;
            xlog("psync: u%08x ACK from slot %u after %.0f ms (copy %d)", w.uid, from, psync_ms() - g_ps.start_ms, g_ps.resend);
        }
        return 1;
    }
    if (w.op == PS_OP_END) { xlog("psync: END u%08x from slot %u (its move time %u ms)", w.uid, from, w.sent_ms); return 1; }
    return 1;
}

// ---- per frame
// exp = the clip's placement of the half (psync_place), err = our body's distance from it (xz). Counted after the
// blend-in (the body slides there from where it stood during the first PS_BLEND s; that part goes to max_err_bl).
static void psync_body_line(int k, uint64_t ent, float ph, int blend, char *out, size_t n, float *apos) {
    float b[16], ia[4], ie[4];
    const float *l = psync_loc(ent, b);
    apos[0] = apos[1] = apos[2] = apos[3] = 0; apos[4] = 0;
    if (!l) { snprintf(out, n, "%s no locator", k ? "vic" : "att"); return; }
    psync_in_ap(l, ia);
    memcpy(apos, ia, 16); apos[4] = 1;
    if (g_ps.place_ok[k]) {
        psync_in_ap(g_ps.place[k], ie);
        // err is 3-D (a pin victim puppet 0.46 m above its clip read 'err 0.00' - y was ignored); 'gnd' = the slope grounding's
        // share of it (psync_drive), so a lift by a real slope reads as err == |gnd|, a bad lift as err without it
        float dx = ia[0] - ie[0], dz = ia[1] - ie[1], dy = ia[2] - ie[2], err = __builtin_sqrtf(dx * dx + dz * dz + dy * dy);
        float gnd = g_ps.gr_ok[k] ? g_ps.gr_dy[k] : 0.0f;
        // a lethal move's victim after the kill belongs to the death (ragdoll / death clip): not counted
        int dead = k && (g_ps.flags & PS_F_LETHAL) && g_ps.kill_s > 0 && psync_ms() - g_ps.t0 >= g_ps.kill_s * 1000.0;
        if (dead) { if (err > g_ps.max_err_dead[k]) g_ps.max_err_dead[k] = err; }   // the kept victim half after the kill: followed too now
        else if (blend) { if (err > g_ps.max_err_bl[k]) g_ps.max_err_bl[k] = err; }
        else {
            if (err > g_ps.max_err[k]) g_ps.max_err[k] = err;
            g_ps.sum_err[k] += err; g_ps.n_err[k]++;
        }
        char gs[24] = "";
        if (__builtin_fabsf(gnd) >= 0.005f) snprintf(gs, sizeof gs, " gnd %+.2f", gnd);
        snprintf(out, n, "%s ph %.3f ap(%.2f %.2f y%+.2f %4.0f) exp(%.2f %.2f y%+.2f %4.0f) err %.2f%s%s", k ? "vic" : "att", ph, ia[0], ia[1], ia[2], ia[3],
                 ie[0], ie[1], ie[2], ie[3], err, gs, blend ? " (blend-in)" : "");
    } else snprintf(out, n, "%s ph %.3f ap(%.2f %.2f y%+.2f %4.0f) exp n/a", k ? "vic" : "att", ph, ia[0], ia[1], ia[2], ia[3]);
}
static void psync_frame_log(double t, const float *ph, int blend) {
    char la[160], lv[160], ch[200];
    float pa[5], pv[5];
    psync_body_line(0, g_ps.ent_att, ph[0], blend, la, sizeof la, pa);
    psync_body_line(1, g_ps.ent_vic, ph[1], blend, lv, sizeof lv, pv);
    float rel[3] = {0}; int rok = pa[4] > 0 && pv[4] > 0;
    if (rok) {          // victim relative to the attacker, in the attacker's frame (fwd, side, yaw)
        float ya = pa[3] * 0.0174533f, dx = pv[0] - pa[0], dz = pv[1] - pa[1];
        rel[0] = dx * __builtin_sinf(ya) + dz * __builtin_cosf(ya);
        rel[1] = dx * __builtin_cosf(ya) - dz * __builtin_sinf(ya);
        rel[2] = uc4_wrap(pv[3] - pa[3]);
    }
    ch[0] = 0;
    for (int s = 0; s < T2R_MAX_PEERS; s++) if (g_ps_pup[s].h) {
        size_t l = strlen(ch);
        snprintf(ch + l, SNLEFT(ch, l), " pup%d[%s rep %ld root %ld gate %ld loc %ld drv %ld]", s, g_ps_pup[s].on ? "susp" : "NET", (long)g_ps_pup[s].rep,
                 (long)g_ps_pup[s].root, (long)g_ps_pup[s].gate, (long)g_ps_pup[s].loc, (long)g_ps_pup[s].drv);
    }
    uint64_t el = g_frame - g_ps.start_frame;
    if (dbg() ? (g_ps.log_n++ % (uint32_t)(g_ps_log_every > 0 ? g_ps_log_every : 1) == 0 || el < 10) : el < 2)
        xlog("psync u%08x r%d t=%5.0f +%llu | %s | %s | rel fwd %.2f side %.2f yaw %.0f |%s", g_ps.uid, g_ps.role, t, (unsigned long long)el, la, lv,
             rel[0], rel[1], rel[2], ch);
    int bucket = (int)(t / 100.0);
    if (bucket != g_ps.last_sync_bucket && pa[4] > 0 && pv[4] > 0 && (dbg() || bucket % 10 == 0)) {
        g_ps.last_sync_bucket = bucket;
        // the cross-client comparison line: the same t on both logs should show the same numbers (<~0.1 m, <~5 deg)
        xlog("psync sync u%08x t=%d att %.2f %.2f %.0f vic %.2f %.2f %.0f rel %.2f %.2f %.0f", g_ps.uid, bucket * 100, pa[0], pa[1], pa[3], pv[0], pv[1], pv[3],
             rel[0], rel[1], rel[2]);
    }
}
// The victim dies at the KILL frame but its 2013 half plays to its end: the engine's Death state may drop the animate_
// layer on the dead body, so from the death on this puts the half back at its current phase whenever the layer is gone.
static void vdf_dump_arm(void);
static void psync_keep_victim(const char *why) {
    if (!g_ps.role || g_ps.vic_keep || !g_ps.ent_vic || g_ps.vic_dur <= 0) return;
    g_ps.vic_keep = 1; g_ps.keep_n = 0;
    xlog("psync: u%08x victim half kept to its end after the death (%s)", g_ps.uid, why);
    if (g_ps.ent_vic == SID_PLAYER) vdf_dump_arm();      // evidence: the player's anim layers for 24 frames from the kill
}
// ---- the execution victim's own death: the engine's Death state, but NO TLOU2 death animation (re/factions2013/exec-victim-death.md)
// ROUND 2 (static RE of tlou-ii.exe; round 1 was wrong): the event round 1 withheld at Death enter (0x140b57990 ->
// [player+0x2eb0]+0x130 vfunc 0xf8, sid 0xf9f8fce6b3d7f7d6 / 0xa862692abea709ba) is "vox-event-all-death" / "vox-event-all-death-by-
// falling" = the death SCREAM (vox controller), not an animation. Withholding it stays (the execution plays its own death vox).
// The death ANIMATION is started by the player's death controller comp = [player+0x2fd0] (vtable 0x142ca7958, an anim-action
// controller: its actions live in the player's anim-action list [player+0x50b8] == [comp+0x120]). Every death-anim path of it
// (DieFromAttack vfunc 0x58 = 0x140b55000, the table death 0x140b5bb20, 0x140b5c1a0, 0x140b5bee0, generic-death vfunc 0xc0, ...)
// does 1) 0x1420280a0(comp, 0, 1) = remove EVERY action on layer 0 of the list, 2) builds a "player-move-action" whose
// FadeToState (action+0x48, vtable 0x142c8f1f8: +8 = the death state, e.g. "generic-death", +0x10 = layer "base") and wait
// object (action+0x40) play the death anim, 3) starts it with comp vfunc 0x28 (= base 0x142028660: links it into the list).
// Death Enter (0x140b58c00) additionally calls 0x140b57cf0 which does 0x142029960([player+0x50b8], 0) = remove every layer-0 action
// of the player. All of that is "the anim side of the death"; the gameplay side (dead flags, credit, respawn, death camera
// 0x140b5d730, stats) is elsewhere and untouched.
// Fix (while our own victim half is kept, fix switch on):
//   - comp vtable slot 0x28 (Start) -> vdh_start: the death action's FadeToState + wait object are detached before it starts, so it is
//     the inert move-action the engine itself uses while ragdolling (0x140b5d290): the death controller's bookkeeping runs, no death
//     anim plays.
//   - 0x1420280a0 (controller clear-all) for the death controller -> withheld.
//   - 0x142029960 (list clear-all) on our player's list -> withheld and DEFERRED: run at the end of the half.
//   - the end of the half (vdf_limp): the deferred clear, then the death controller's own ragdoll (vfunc 0x38(1, 0) = 0x140b55980)
//     = the body goes limp from the clip's last pose (round 1 set comp+0x141 so Death's Update ragdolled it, but that path also
//     posts vox-event-all-death-by-falling: a second scream).
// Evidence for the next test: per-frame dump of the player's anim layers (vdf_dump, 24 frames from the kill frame) and a DR1-3
// write watch on the layer our half plays on (vlw_arm, ~600 ms before the kill): which code removes / replaces it.
#define VDF_COMP_VT 0x142ca7958ULL
#define VDF_DEATH_STATE 0xb05f8bdc266380cdULL
static int g_vdf_off;
static uint32_t g_vdf_scream_uid;   // ps40 D1: the kept victim half of this move keeps the engine's own death scream (a blade finisher kill has no death vox of its own)
static int g_ps_corpse_keep40;      // ps40 D1: ctxdown's hand-off of a row that kills - the dead victim puppet's corpse hold is not undone by the hand-off's abort
// Death animations are force-disabled for downed players: a death from the downed state (execution, bleed-out, shot / melee while
// downed) never plays a TLOU2 death animation - for the WHOLE Death state, not just while an execution half plays (B log 23:1x: the
// death controller started its FadeToState right after the half ended -> death anim after the clip). Set by downed_death_noanim(),
// cleared once we live again (vdf_noanim_tick).
static int g_vdf_noanim, g_vdf_rag_pending, g_vdf_ragged; static uint64_t g_vdf_noanim_frame;
static int g_vdf_exec_limp;    // the body went limp at the end of an execution victim half (vdf_limp): the death controller's post-ragdoll action stays withheld
static void downed_death_noanim(const char *why) {
    du_edge_note(why);                       // death ui: the death screen starts from this frame (the lethal hit follows)
    if (!g_vdf_noanim) xlog("death: downed death (%s) - no TLOU2 death animation for this death", why);
    g_vdf_noanim = 1; g_vdf_noanim_frame = g_t60;
}                       // t2r-no-vic-deathanim-fix.txt (re-read by psync_tick every 2 s)
typedef void (*fn_vdf)(uint64_t player, uint64_t send, uint64_t flag);
static fn_vdf g_vdf_tramp;
static uint8_t *vdf_player(void) { typedef uint8_t *(*fn_me)(void); return ((fn_me)VMA(0x180050390))(); }
static uint8_t *vdf_comp(uint8_t *me) {
    if (!me || IsBadReadPtr(me + 0x2fd0, 8)) return NULL;
    uint8_t *c = *(uint8_t **)(me + 0x2fd0);
    if (!c || IsBadReadPtr(c, 0x240)) return NULL;
    if (*(uint64_t *)c != (uint64_t)GetModuleHandleW(NULL) + (VDF_COMP_VT - 0x140000000ULL)) return NULL;
    if (*(uint8_t **)(c + 0x118) != me) return NULL;
    return c;
}
static uint8_t *vdf_list(uint8_t *me) {       // the player's anim-action list (component inits get it as r8; == [comp+0x120])
    if (!me || IsBadReadPtr(me + 0x50b8, 8)) return NULL;
    return *(uint8_t **)(me + 0x50b8);
}
static uint64_t vdf_state(uint8_t *me) {      // FUN_141341430: [[player+0x98]] -> [+0x10] -> +0x18 = current state's name
    if (!me || IsBadReadPtr(me + 0x98, 8)) return 0;
    uint64_t *m = *(uint64_t **)(me + 0x98);
    if (!m || IsBadReadPtr(m, 8)) return 0;
    uint8_t *st = *(uint8_t **)m;
    if (!st || IsBadReadPtr(st + 0x10, 8)) return 0;
    uint8_t *d = *(uint8_t **)(st + 0x10);
    if (!d || IsBadReadPtr(d + 0x18, 8)) return 0;
    return *(uint64_t *)(d + 0x18);
}
static int vdf_active(void) {
    // the whole own lethal victim half, not only from the kill: a stray hit before the kill (revolver case: the attacker's
    // npc-fire-weapon shot at 2.68 s, kill 3.2 s) put us in Death early and its clear-all removed the half - the body stopped
    return !g_vdf_off && !g_vdf_limp_done && g_ps.role && (g_ps.vic_keep || g_ps.vic_own_lethal) && g_ps.ent_vic == SID_PLAYER;
}
static void vdf_stack(char *out, size_t n) {   // exe / ext return addresses of the current call (who asked)
    void *bt[10]; USHORT k = RtlCaptureStackBackTrace(1, 10, bt, NULL);
    size_t l = 0; out[0] = 0;
    for (USHORT j = 0; j < k && l + 40 < n; j++) { char w[64]; mod_off((uint64_t)bt[j], w, sizeof w); l += (size_t)snprintf(out + l, n - l, " %s", w); }
}
// --- the player's anim layers (exe: anim control = [obj+0x1b8]; layer table count +0x20, entries [+0x28] 0x20 bytes each:
// +0 layer name, +8 layer, +0x14 in use; layer +8 type (1 simple: instance [+0x58] valid while +0x94 != 0, instance+0x78 = clip,
// phase = instance vfunc 0x28; 2 state layer: instances +0x638 / count +0x640, current state = 0x1416017d0); fade fields
// +0x2c / +0x30 / +0x34 (weights), +0x48 (fade time) (FadeLayer 0x1415f6b80))
typedef struct { uint64_t name, anim, state; uint8_t *layer, *inst; int used, type, n; float w[3], fade, ph, raw[3]; uint8_t f3c, f3d; } vdf_lay;   // raw = +0x34 / +0x40 / +0x44, f3c / f3d = the bytes FadeLayer 0x1415f6b80 sets (a timed fade is refused while f3d is set)
static int vdf_layers(uint8_t *me, vdf_lay *o, int max) {
    uint8_t *ac = me && !IsBadReadPtr(me + 0x1b8, 8) ? *(uint8_t **)(me + 0x1b8) : NULL;
    if (!ac || IsBadReadPtr(ac, 0x30)) return 0;
    uint32_t cnt = *(uint32_t *)(ac + 0x20);
    uint8_t *tab = *(uint8_t **)(ac + 0x28);
    if (!tab || cnt > 64 || IsBadReadPtr(tab, (size_t)cnt * 0x20)) return 0;
    int k = 0;
    for (uint32_t i = 0; i < cnt && k < max; i++) {
        uint8_t *e = tab + (size_t)i * 0x20;
        vdf_lay *l = &o[k++];
        memset(l, 0, sizeof *l);
        l->ph = -1.0f;
        l->name = *(uint64_t *)e; l->layer = *(uint8_t **)(e + 8); l->used = e[0x14];
        if (!l->layer || IsBadReadPtr(l->layer, 0x648)) continue;
        uint8_t *L = l->layer;
        l->type = *(int32_t *)(L + 8);
        l->w[0] = *(float *)(L + 0x2c); l->w[1] = *(float *)(L + 0x30); l->w[2] = *(float *)(L + 0x34); l->fade = *(float *)(L + 0x48);
        l->raw[0] = *(float *)(L + 0x34); l->raw[1] = *(float *)(L + 0x40); l->raw[2] = *(float *)(L + 0x44); l->f3c = L[0x3c]; l->f3d = L[0x3d];
        if (l->type == 1) {
            l->n = *(int32_t *)(L + 0x94);
            l->inst = l->n ? *(uint8_t **)(L + 0x58) : NULL;
            if (l->inst && !IsBadReadPtr(l->inst, 0x80) && !IsBadReadPtr(*(uint8_t **)l->inst, 0x30) && is_code(*(void **)(*(uint8_t **)l->inst + 0x28))) {
                l->anim = *(uint64_t *)(l->inst + 0x78);
                typedef float (*fn_ph)(void *);
                l->ph = ((fn_ph)(*(void **)(*(uint8_t **)l->inst + 0x28)))(l->inst);
            }
        } else if (l->type == 2) {
            l->n = *(int32_t *)(L + 0x640);
            if (l->n) { typedef uint64_t *(*fn_st)(void *, uint64_t *); ((fn_st)((uint8_t *)GetModuleHandleW(NULL) + 0x16017d0))(L, &l->state); }
        }
    }
    return k;
}
static void psync_layer_snap(const char *tag, uint64_t ent) {
    static int nl;
    if (!ent || !LOGCAP(nl, 400)) return;
    typedef uint8_t *(*fn_proc)(uint64_t);
    uint8_t *proc = ent == SID_PLAYER ? ((uint8_t *(*)(void))VMA(0x180050390))() : ((fn_proc)VMA(0x18000A200))(ent);
    if (!proc) return;
    vdf_lay cur[48];
    int n = vdf_layers(proc, cur, 48);
    char buf[900]; size_t k = 0;
    for (int i = 0; i < n && k + 120 < sizeof buf; i++) {
        vdf_lay *L = &cur[i];
        if (!L->used && !L->anim) continue;
        k += (size_t)snprintf(buf + k, SNLEFT(buf, k), " | L%d t%d u%d w%.2f/%.2f/%.2f f%.2f r%.2f n%d %s f3c%02x f3d%02x", i, L->type, L->used,
                              L->w[0], L->w[1], L->w[2], L->fade, L->raw[2], L->n, L->anim ? (L->anim == g_ps.att_sid ? "HALF" : psync_name(L->anim)) : "-", L->f3c, L->f3d);
    }
    xlog("psync layers u%08x %s (frame %llu):%s", g_ps.uid, tag, (unsigned long long)g_frame, buf);
}
static vdf_lay g_vdf_prev[48]; static int g_vdf_prev_n;
static uint64_t g_vdf_dump_frame;
static void vdf_dump(const char *tag, int all) {
    if (!dbg()) return;
    uint8_t *me = vdf_player();
    vdf_lay cur[48];
    int n = vdf_layers(me, cur, 48);
    uint8_t *c = vdf_comp(me);
    xlog("vdf layers %s: frame %llu t=%.0f ms, %d layers, state %llx, comp +0x141 %d +0x13e %d +0x13f %d +0x142 %d, ragdoll bit %d, half %s",
         tag, (unsigned long long)g_frame, psync_ms() - g_ps.t0, n, (unsigned long long)vdf_state(me), c ? c[0x141] : -1, c ? c[0x13e] : -1,
         c ? c[0x13f] : -1, c ? c[0x142] : -1, me ? (me[0x9fd] & 1) : -1, psync_name(g_ps.vic_sid));
    for (int i = 0; i < n; i++) {
        vdf_lay *l = &cur[i], *p = i < g_vdf_prev_n ? &g_vdf_prev[i] : NULL;
        int ch = !p || p->name != l->name || p->layer != l->layer || p->used != l->used || p->inst != l->inst || p->anim != l->anim ||
                 p->state != l->state || p->n != l->n || __builtin_fabsf(p->w[0] - l->w[0]) > 0.01f || __builtin_fabsf(p->w[1] - l->w[1]) > 0.01f;
        if (!all && !ch) continue;
        xlog("vdf   L%-2d %016llx used %d %p type %d w %.2f/%.2f/%.2f fade %.2f %s n %d inst %p clip %s ph %.3f state %016llx%s%s", i,
             (unsigned long long)l->name, l->used, (void *)l->layer, l->type, l->w[0], l->w[1], l->w[2], l->fade, l->type == 1 ? "simple" : "state",
             l->n, (void *)l->inst, l->anim ? psync_name(l->anim) : "-", l->ph, (unsigned long long)l->state,
             l->anim && l->anim == g_ps.vic_sid ? "  <== our victim half" : "", p && ch ? "  (changed)" : "");
    }
    memcpy(g_vdf_prev, cur, sizeof cur[0] * (size_t)n); g_vdf_prev_n = n;
}
static void vdf_dump_arm(void) { g_vdf_dump_left = 24; g_vdf_dump_frame = 0; g_vdf_prev_n = 0; }
static void vdf_dump_tick(void) {
    if (g_vdf_dump_left <= 0 || g_frame == g_vdf_dump_frame) return;
    g_vdf_dump_frame = g_frame;
    char tag[32]; snprintf(tag, sizeof tag, "kill+%d", 24 - g_vdf_dump_left);
    vdf_dump(tag, g_vdf_dump_left == 24);
    g_vdf_dump_left--;
}
// --- DR1-3 write watch on the layer our half plays on (the wpw machinery of t2r-ext.c, dev builds): entry +0x10 (its in-use byte
// +0x14), +0x94 (instance valid) and +0x58 (instance) of the simple layer
static void vlw_arm(void) {
#ifdef T2R_RELEASE
    return;
#endif
    if (g_vlw_armed || g_wpw_addr[0]) return;
    g_vlw_armed = 1;
    uint8_t *me = vdf_player();
    uint8_t *ac = me && !IsBadReadPtr(me + 0x1b8, 8) ? *(uint8_t **)(me + 0x1b8) : NULL;
    vdf_lay ls[48];
    int n = vdf_layers(me, ls, 48);
    for (int i = 0; i < n && ac; i++) {
        if (ls[i].type != 1 || ls[i].anim != g_ps.vic_sid) continue;
        uint8_t *tab = *(uint8_t **)(ac + 0x28), *L = ls[i].layer;
        static char lb[3][48];
        snprintf(lb[0], sizeof lb[0], "victim layer %d entry+0x10 (in-use +0x14)", i);
        snprintf(lb[1], sizeof lb[1], "victim layer %d +0x94 (instance valid)", i);
        snprintf(lb[2], sizeof lb[2], "victim layer %d +0x58 (instance)", i);
        g_wpw_lbl[0] = lb[0]; g_wpw_lbl[1] = lb[1]; g_wpw_lbl[2] = lb[2];
        g_wpw_n = 0; g_wpw_printed = 0;
        InterlockedExchange(&g_wpw_ever, 1);
        g_wpw_addr[0] = (uint64_t)(tab + (size_t)i * 0x20 + 0x10); g_wpw_addr[1] = (uint64_t)(L + 0x94); g_wpw_addr[2] = (uint64_t)(L + 0x58);
        g_wpw_until = g_frame + 360;
        xlog("psync: u%08x victim layer watch: layer %d %016llx %p instance %p (%s ph %.3f) - DR1-3 armed for 360 frames (\"wpw: write to victim layer ...\")",
             g_ps.uid, i, (unsigned long long)ls[i].name, (void *)L, (void *)ls[i].inst, psync_name(ls[i].anim), ls[i].ph);
        CloseHandle(CreateThread(NULL, 0, wpw_set_thread, NULL, 0, NULL));
        return;
    }
    xlog("psync: u%08x victim layer watch: our half %s is on no simple layer of the player (%d layers) - not armed", g_ps.uid, psync_name(g_ps.vic_sid), n);
    vdf_dump("watch", 1);
}
// --- 1) the death SCREAM at Death enter (round 1 hook, relabelled)
static int dr_scream_replaced(void);                  // deathreact.c: our molotov burning death swaps the death scream
static void dr_own_burn_event(uint8_t *player);       // deathreact.c: ...for SP's burning-death event, requested the engine's way
static void vdf_hook(uint64_t player, uint64_t send, uint64_t flag) {
    uint8_t *me = vdf_player();
    if ((send & 0xff) && vdf_active() && (uint8_t *)player == me && !(g_vdf_scream_uid && g_vdf_scream_uid == g_ps.uid)) {
        uint8_t *c = vdf_comp(me);
        float ph = psync_phase(SID_PLAYER, g_ps.vic_sid);
        xlog("psync: u%08x own death SCREAM withheld at Death enter (%s): comp +0x141 %d +0x13d %d, state %llx, ragdoll bit %d, "
             "victim half layer phase %.3f at t=%.0f ms", g_ps.uid, (flag & 0xff) ? "vox-event-all-death-by-falling" : "vox-event-all-death",
             c ? c[0x141] : -1, c ? c[0x13d] : -1, (unsigned long long)vdf_state(me), me ? (me[0x9fd] & 1) : -1, ph, psync_ms() - g_ps.t0);
        vdf_dump("at Death enter", 1);
        send = 0;
    } else if ((send & 0xff) && (uint8_t *)player == me && dr_scream_replaced()) {
        xlog("burndeath: own normal death scream swapped at Death enter - the burning-death event goes through the same request (one scream)");
        send = 0;
        dr_own_burn_event((uint8_t *)player);
    } else if ((send & 0xff) && (uint8_t *)player == me && hs_recent(SID_PLAYER)) {
        xlog("headshot death: own normal death scream withheld at Death enter - SP's headshot death take replaces it");
        hs_arm(SID_PLAYER, 1, 0);
        send = 0;
    } else if (send & 0xff) {
        xlog("death vocal: headshot 0 -> engine body-shot scream (%s)", g_vdf_off ? "fix off" : g_ps.role ? "no kept victim half" : "no paired move");
    }
    g_vdf_tramp(player, send, flag);
}
// deathreact.c: our own body plays a directional TLOU2 death clip (a downed player shot dead / a standing player killed by the Military Sniper): the
// engine's death anim stays withheld, the Death enter / controller clear-alls are deferred like an execution's kept half - but the death scream
// (hook 1) is NOT touched - and the ragdoll comes from dr_release_own() at the clip's end
static int dr_hold_active(void);
static void dr_tick(void);
// --- 2) the death controller starting its death-anim action (comp vtable slot 0x28)
typedef void (*fn_vdh_start)(uint8_t *ctrl, uint64_t layer, uint8_t *action);
static fn_vdh_start g_vdh_start_orig;
static int g_vdf_withheld;
// A downed body shot dead showed every flag of a ragdoll (bit 1, Death state) and a frozen lying pose. The log has TWO withheld death-controller
// actions per death: #1 the death anim (FadeToState 5d79..., at the Death enter) and #2 FadeToState 4827... the same frame the ragdoll vfunc 0x38 ran (stack from
// the noanim tick) - the controller's reaction to the ragdoll, the state that takes the anim graph off the prone pose. An execution half never withholds it (its
// limp runs after the half, vdf_active() is off), the downed path did (g_vdf_noanim stays on until the respawn): the graph kept evaluating the prone pose under
// a ragdoll with nothing to free it. Now only actions BEFORE the ragdoll call are withheld.
// EXCEPT after an execution victim half (shiv victim, 'npc-lg-cover-low-l-hunker-enter-idle-r': body ended in SP's default death pose): there the
// body is a powered ragdoll whose motors follow the anim output, and the passed 4827... state IS that output - SP's default death pose replaced the half's
// final pose (the downed path above has no half pose to keep; its prone clip is cleared by dd_limp_tick). g_vdf_exec_limp keeps it withheld, as before c43830e5. t2r-dd-withhold-all.txt = the old behaviour.
static int vdh_withhold_all(void) {
    static int v = -1;
    if (v < 0) { FILE *f = exe_side_open("t2r-dd-withhold-all.txt", "r"); v = f != NULL; if (f) fclose(f); }
    return v;
}
static void vdh_start(uint8_t *ctrl, uint64_t layer, uint8_t *action) {
    uint8_t *me = vdf_player();
    // an action with no FadeToState is the inert move-action the ragdoll itself starts (withholding it re-queued the
    // ragdoll every frame - 152 loops, crash): only actions that would play an animation are withheld
    if (action && !IsBadWritePtr(action + 0x38, 24) && *(uint8_t **)(action + 0x48) && (vdf_active() || (g_vdf_noanim && !g_vdf_off && (!g_vdf_ragged || vdh_withhold_all() || g_vdf_exec_limp)) || dr_hold_active()) && ctrl == vdf_comp(me)) {
        uint8_t *fts = *(uint8_t **)(action + 0x48), *wait = *(uint8_t **)(action + 0x40);
        uint64_t anim = fts && !IsBadReadPtr(fts, 0x18) ? *(uint64_t *)(fts + 8) : 0, lay = fts && !IsBadReadPtr(fts, 0x18) ? *(uint64_t *)(fts + 0x10) : 0;
        // no FadeToState / wait / end objects: exactly the inert move-action the engine starts while ragdolling (0x140b5d290:
        // +0x38 = +0x40 = +0x48 = 0). The detached objects (~0.5 KB) are left alone (their owner is the action's teardown).
        *(uint8_t **)(action + 0x48) = NULL;
        *(uint8_t **)(action + 0x40) = NULL;
        *(uint8_t **)(action + 0x38) = NULL;
        g_vdf_withheld++;
        if (!vdf_active() && !g_vdf_ragged && !dr_hold_active()) g_vdf_rag_pending = 1;      // not an execution half: limp on the next frame (the corpse crawled / UC4 arms-up); a death reaction clip plays first (dr_release_own)
        char st[400]; vdf_stack(st, sizeof st);
        xlog("psync: u%08x own death ANIM withheld (#%d): death controller FadeToState %016llx on layer %016llx (action %p, layer %llu, wait %p, "
             "t=%.0f ms) from%s", g_ps.uid, g_vdf_withheld, (unsigned long long)anim, (unsigned long long)lay, (void *)action,
             (unsigned long long)layer, (void *)wait, psync_ms() - g_ps.t0, st);
    } else if (ctrl == vdf_comp(me) && g_ps.role && g_ps.ent_vic == SID_PLAYER) {
        uint8_t *fts = action && !IsBadReadPtr(action + 0x48, 8) ? *(uint8_t **)(action + 0x48) : NULL;
        xlog("psync: own death controller starts an action (%s): FadeToState %016llx", g_vdf_off ? "fix off" : g_vdf_limp_done ? "after the half" : "no kept half",
             fts && !IsBadReadPtr(fts, 0x18) ? (unsigned long long)*(uint64_t *)(fts + 8) : 0ULL);
    }
    g_vdh_start_orig(ctrl, layer, action);
}
// --- 3) the death controller's clear-all of layer-0 actions (0x1420280a0, shared anim-action controller base)
typedef void (*fn_vdh_cclear)(uint8_t *ctrl, uint64_t layer, uint64_t all);
static fn_vdh_cclear g_vdh_cclear_orig;
static void vdh_cclear(uint8_t *ctrl, uint64_t layer, uint64_t all) {
    if ((vdf_active() || dr_hold_active()) && ctrl == vdf_comp(vdf_player())) {
        char st[400]; vdf_stack(st, sizeof st);
        xlog("psync: u%08x death controller clear-all-actions (layer %d, all %d) withheld from%s", g_ps.uid, (int)layer, (int)(all & 0xff), st);
        return;
    }
    g_vdh_cclear_orig(ctrl, layer, all);
}
// --- 4) Death enter's clear-all of the player's layer-0 actions (0x142029960 from 0x140b57cf0): deferred to the end of the half
typedef void (*fn_vdh_lclear)(uint8_t *list, uint64_t layer);
static fn_vdh_lclear g_vdh_lclear_orig;
static uint8_t *g_vdf_deferred_list; static int g_vdf_deferred_layer = -1;
static void vdh_lclear(uint8_t *list, uint64_t layer) {
    if ((vdf_active() || dr_hold_active()) && list && list == vdf_list(vdf_player())) {
        char st[400]; vdf_stack(st, sizeof st);
        g_vdf_deferred_list = list; g_vdf_deferred_layer = (int)layer;
        xlog("psync: u%08x player's clear-all-actions (layer %d) deferred to the end of the victim half, from%s", g_ps.uid, (int)layer, st);
        return;
    }
    g_vdh_lclear_orig(list, layer);
}
// inline hook: the first n bytes (no rip-relative operand) move to a trampoline, the function jumps to dst
static void *vdf_inline(uint64_t va, const uint8_t *expect, int n, void *dst, const char *what, void **tramp_out) {
    uint8_t *f = (uint8_t *)GetModuleHandleW(NULL) + (va - 0x140000000ULL);
    if (n < 14 || IsBadReadPtr(f, (size_t)n) || memcmp(f, expect, (size_t)n)) { hook_miss(f, (size_t)n, "psync: exe build differs at %llx, %s hook not installed", (unsigned long long)va, what); return NULL; }
    uint8_t *t = VirtualAlloc(NULL, 64, MEM_COMMIT | MEM_RESERVE, PAGE_EXECUTE_READWRITE);
    if (!t) return NULL;
    memcpy(t, f, (size_t)n);
    t[n] = 0xff; t[n + 1] = 0x25; *(uint32_t *)(t + n + 2) = 0; *(uint64_t *)(t + n + 6) = (uint64_t)(f + n);
    if (tramp_out) *tramp_out = t;      // published before the patch: the hook calls it the moment the jump is in
    DWORD old; VirtualProtect(f, (size_t)n, PAGE_EXECUTE_READWRITE, &old);
    f[0] = 0xff; f[1] = 0x25; *(uint32_t *)(f + 2) = 0; *(uint64_t *)(f + 6) = (uint64_t)dst;
    for (int i = 14; i < n; i++) f[i] = 0x90;
    VirtualProtect(f, (size_t)n, old, &old);
    FlushInstructionCache(GetCurrentProcess(), f, (size_t)n);
    return t;
}
// ---- Player process kill watch (the no-respawn deaths): after a downed death that followed a paired move
// OUR Player process was destroyed one frame after the Death state began (owner handle guard: 'process .. id now 0', get-player 0), so winmm's respawn timer
// (it only ticks in the Death state) froze and the death screen stayed black for good. Static analysis names no caller (0x141341480 has 467), so the kill is
// watched: exe+0x1413414c0 is the one process-destroy body every route ends in (0x141341480 by handle sets +0x32 then calls it, 0x141341470 by pointer jumps to it).
// The hook only compares the object's vtable with the Player class (exe+0x2cfc988; remote players are NPC-class puppets), so it costs a load per kill and never
// calls into the engine. A Player kill logs ONE line with the call stack (tick thread or a job thread, who) and one with the last natives we invoked
// (cd_name, the dc_call ring), so a single repro answers it: 'player kill watch:'. Normal respawns log too (state Death, long after the death edge) - the
// bad one is the kill within 1-2 frames of 'death: downed death'. t2r-no-pkill-watch.txt = off.
static uint64_t (*g_pk_tramp)(uint8_t *proc, uint64_t a2, uint64_t a3, uint64_t a4);   // (all 4 register args forwarded: the hook calls functions first)
static volatile LONG g_pk_n;
static uint64_t pk_hook(uint8_t *proc, uint64_t a2, uint64_t a3, uint64_t a4) {
    if (g_pd_via_pk && pd_refuse(proc)) return 0;      // keep throw (t2r-ext.c): our in-flight throwable survives our down
    if (proc && *(uint64_t *)proc == (uint64_t)GetModuleHandleW(NULL) + 0x2cfc988ULL &&
        (g_pk_n < 30 || g_down_dying || vdf_state(proc) == VDF_DEATH_STATE)) {   // the cap spares the routine respawn kills only: a kill during a death always logs
        InterlockedIncrement(&g_pk_n);
        void *bt[18]; USHORT k = RtlCaptureStackBackTrace(1, 18, bt, NULL);
        char st[700]; size_t l = 0; st[0] = 0;
        for (USHORT j = 0; j < k && l + 40 < sizeof st; j++) { char w[64]; mod_off((uint64_t)bt[j], w, sizeof w); l += (size_t)snprintf(st + l, SNLEFT(st, l), " %s", w); }
        xlog("player kill watch: frame %llu - our Player process %p destroyed (id %x, flags +a %02x +c %02x +32 %02x, state %llx) on thread %lu%s | downed %d, downed death %d, "
             "psync role %d kind %d, exec_until %d; from%s", (unsigned long long)g_frame, (void *)proc, *(uint32_t *)(proc + 0x94), proc[0xa], proc[0xc], proc[0x32],
             (unsigned long long)vdf_state(proc), (unsigned long)GetCurrentThreadId(), GetCurrentThreadId() == g_tick_tid ? " (the tick thread)" : " (NOT the tick thread)",
             g_downed, g_down_dying, g_ps.role, g_ps.kind, g_exec_until != 0, st);
        char nb[900]; size_t m = 0; nb[0] = 0;
        LONG n = g_dcr_i;
        for (int j = 0; j < 24 && m + 48 < sizeof nb; j++) {
            const typeof(g_dcr[0]) *e = &g_dcr[(n - j) & (CD_DCR_N - 1)];
            if (!e->sid) break;
            const char *nmx = cd_name(e->sid);      // (an unknown name prints its sid: two reports showed five '?' entries right before the kill)
            if (nmx[0] == '?') m += (size_t)snprintf(nb + m, SNLEFT(nb, m), " sid%llx@%llu:%llx", (unsigned long long)e->sid, (unsigned long long)e->frame, (unsigned long long)e->a0);
            else m += (size_t)snprintf(nb + m, SNLEFT(nb, m), " %s@%llu:%llx", nmx, (unsigned long long)e->frame, (unsigned long long)e->a0);
        }
        xlog("player kill watch: last natives (newest first):%s", nb);
    }
    return g_pk_tramp(proc, a2, a3, a4);
}
static void install_pkill_watch(void) {
    FILE *f = exe_side_open("t2r-no-pkill-watch.txt", "r");
    if (f) { fclose(f); xlog("player kill watch: off (t2r-no-pkill-watch.txt)"); return; }
    // 0x1413414c0: mov [rsp+10h],rbx; mov [rsp+18h],rbp; mov [rsp+20h],rsi   (15 bytes, no rip-relative operand)
    static const uint8_t e[15] = {0x48, 0x89, 0x5c, 0x24, 0x10, 0x48, 0x89, 0x6c, 0x24, 0x18, 0x48, 0x89, 0x74, 0x24, 0x20};
    g_pk_tramp = (uint64_t (*)(uint8_t *, uint64_t, uint64_t, uint64_t))vdf_inline(0x1413414c0, e, 15, (void *)pk_hook, "player kill watch", (void **)&g_pk_tramp);
    xlog("player kill watch: %s", g_pk_tramp ? "installed (a destroyed Player process is logged with its call stack)" : "NOT installed (exe code differs)");
}
// ---- Player kill REQUEST guard ('black screen forever, kill feed still visible, Esc does nothing').
// Evidence (5 reports, 3 players, the same fingerprint in every one, 0 times in ~1300 other deaths of the same logs): a downed death 'executed by a hit while
// downed' whose Player process is DESTROYED one frame after the Death state begins, by the engine's own deferred kill, not by winmm:
//   player kill watch ... from tlou-ii.exe+1ceb88e +b0ee82 +ad7798 +1341dec +134018d +126e01b (two reports, identical stacks),
//   1ceb860 = the Player's per-frame check 'if (this[+0x9b9]) kill(this)'; the flag is set by 1cea620 (Process kill REQUEST: calls vfunc +0xce0 'can be
//   killed' and, if true, stores 1 at +0x9b9; it sits in the Player vtable at +0x6b0 and has no direct caller, so the requester is a script / virtual call).
// What follows is always the same: 'owner handle guard ... dead owner handle' (the move-stick update met the dead Player), 'death ui: HUD under the black - 0
// widgets' (the HUD and the menu page stack die with the Player: Esc logs 'pause menu opened (page 0, top was 0)' and opens nothing), and winmm's respawn
// timer, which only ticks in the Death state, never runs: 'death ui: countdown N' prints once and stops, our own respawn is never requested while the host keeps
// granting everybody else's. A Player that is destroyed 1 frame into its death is never what winmm wants (it kills the old Player itself, directly, at the
// respawn: 'cadde2 <- WINMM+509cb', not through this flag).
// This hook (a) logs the requester's call stack for every request on our Player (the first 30, and the next 60 made during a downed death), which names the
// caller that nothing could name statically, and (b) refuses the request while the Player is in a downed death (g_down_dying) in a running match, for at most
// 15 s of that life. winmm's own respawn kill is a direct call and not affected; after the 15 s the request goes through as before.
// t2r-no-killreq-guard.txt = log only, no refusal.
static void (*g_rk_tramp)(uint8_t *self);
static volatile LONG g_rk_n, g_rk_ref;
static uint64_t g_rk_life, g_rk_t0;
static int g_rk_off;
// The refusal window, shared by the kill-request hook and the physics-body removal guard below: 1 = a request on this Player now is refused.
static int rk_window(uint8_t *self, int *dead_wait_out) {
    int dying = g_down_dying && match_substate() == 6;      // (g_down_dying is set before the lethal hit goes to the engine, so the request is seen before the Death state begins)
    // (dodge into the floor, fall death at y 34, countdown ran to 2 s): a kill request from a script on a job thread
    // (exe+1c0fb3e <- 24c2c75 <- 2097c22) on the Player already in the Death state destroyed it and the respawn never came. A normal respawn makes no
    // request (winmm kills the old Player directly), so while we lie dead in a running match every request is refused, for at most 30 s of that life.
    // (v5-crash2: that requester is the physics-body removal, see brm_hook - the removal is now held back, not only the kill)
    int dead_wait = !dying && vdf_state(self) == VDF_DEATH_STATE && match_substate() == 6;
    if (dead_wait_out) *dead_wait_out = dead_wait;
    if (!dying && !dead_wait) return 0;
    // our own kill-player (the downed / execution fallbacks) is the one request we know is wanted: it ran a few ring entries ago on this thread
    static uint64_t sid_kp; if (!sid_kp) sid_kp = fnv64("kill-player");
    LONG ri = g_dcr_i;
    for (int j = 0; j < 4; j++) {
        const typeof(g_dcr[0]) *e = &g_dcr[(ri - j) & (CD_DCR_N - 1)];
        if (e->sid == sid_kp && e->tid == GetCurrentThreadId() && g_frame - e->frame < 2) { static int no; if (LOGCAP(no, 10)) xlog("player kill request: from our own kill-player call - not refused"); return 0; }
    }
    if (g_rk_life != g_spawned_frame) { g_rk_life = g_spawned_frame; g_rk_t0 = GetTickCount64(); }
    return !g_rk_off && GetTickCount64() - g_rk_t0 < (dead_wait ? 30000u : 15000u);
}
static void rk_hook(uint8_t *self) {
    uint8_t *exe = (uint8_t *)GetModuleHandleW(NULL);
    if (self && !IsBadReadPtr(self, 0xa0) && *(uint64_t *)self == (uint64_t)exe + 0x2cfc988ULL) {
        int dying = g_down_dying && match_substate() == 6;
        if (g_rk_n < 30 || (dying && g_rk_n < 90)) {
            InterlockedIncrement(&g_rk_n);
            void *bt[18]; USHORT k = RtlCaptureStackBackTrace(1, 18, bt, NULL);
            char st[700]; size_t l = 0; st[0] = 0;
            for (USHORT j = 0; j < k && l + 40 < sizeof st; j++) { char w[64]; mod_off((uint64_t)bt[j], w, sizeof w); l += (size_t)snprintf(st + l, SNLEFT(st, l), " %s", w); }
            xlog("player kill request: frame %llu - Process kill request on our Player %p (id %x, state %llx) on thread %lu%s | downed %d, downed death %d, psync role %d; from%s",
                 (unsigned long long)g_frame, (void *)self, *(uint32_t *)(self + 0x94), (unsigned long long)vdf_state(self), (unsigned long)GetCurrentThreadId(),
                 GetCurrentThreadId() == g_tick_tid ? " (the tick thread)" : " (NOT the tick thread)", g_downed, g_down_dying, g_ps.role, st);
        }
        int dead_wait = 0;
        if (rk_window(self, &dead_wait)) {
            // v5-crash2 (v5-int12 test, t2r-ext.log 16517-17057, crash exe+25bcfd4): a request made by the physics-body removal (exe+1c0fad0 ->
            // owner vfunc +0x6b0 = this function, returning to exe+1c0fb3e) comes AFTER that body was already taken out of the world. Refusing it keeps a
            // Player whose ragdoll still points at the removed bodies: the ragdoll constraint update (exe+1e14fc0 -> 25bcf10) read the NULL transform of a
            // removed body and crashed in the same frame. Such a request is never refused here: the removal itself is held back by brm_hook below (the
            // bodies stay, the Player stays, winmm's respawn kills it as usual); reaching this point means that guard did not run, and the engine's kill
            // is the only consistent outcome left (no crash; the no-respawn case at worst).
            if ((uint8_t *)__builtin_return_address(0) == exe + 0x1c0fb3eULL) {
                static int nb; if (LOGCAP(nb, 10)) xlog("player kill request: NOT refused - it comes from the physics-body removal (exe+1c0fb3e): the body is already out of the world, a refusal leaves the ragdoll on a removed body (crash exe+25bcfd4)");
            } else {
                LONG n = InterlockedIncrement(&g_rk_ref);
                if (n <= 6 || (n & 63) == 0)
                    xlog("player kill request: REFUSED #%ld - %s does not destroy the Player (the respawn timer needs it in the Death state, the HUD dies with it)",
                         (long)n, dead_wait ? "a request while dead" : "a downed death");
                return;
            }
        }
    }
    g_rk_tramp(self);
}
// ---- Physics-body removal guard (v5-crash2, v5-int12 test: EXCEPTION c0000005 at exe+25bcfd4 on the death screen, Hospital).
// The chain, read statically from tlou-ii.exe and matched with the log: a body that leaves the physics world (here: the ragdoll of our Player, dead
// since a fall out of the level - 'bb: us 293.34 8.64 -110.67' from frame 12138 - falling through the void for 11.2 s) reaches the Havok step's
// listener (exe+24c2c75 call [r9+0x10] -> exe+1c0fc10), which calls exe+1c0fad0 for the body and every body linked to it: set its motion mode
// (1c10fb0), flag it removed (+0x58 |= 0x2010000), detach it (+0x70 -> 1e0d600), then ask its OWNER process for a kill (owner +0x68, vfunc +0x6b0 =
// exe+1cea620, the request rk_hook refuses while we are dead). 49 such requests came in frames 12806-12807 ('player kill request ... from
// tlou-ii.exe+1c0fb3e tlou-ii.exe+1c0fc4a tlou-ii.exe+24c2c75 ...'), all refused, so the Player and its ragdoll lived on with removed bodies: the
// ragdoll constraint update (winmm+27358 -> exe+1e0b9fd -> 1e14a80 -> 1e14fc0) took body transforms through exe+1c0c4d0, which returns NULL for a
// removed body (index +0x54 = 0xffffff), and 25bcf10 multiplied by it (rdx = rsi = 0, 'mulps xmm11, [rsi]' at 25bcfd4).
// Refusing the kill but keeping the removal is the one inconsistent state, so the removal is held back in exactly the window the kill would be
// refused: a body owned by our Player (Player vtable) while rk_window() says 1 is left alone (no removal, no kill request). The ragdoll keeps
// valid bodies until winmm's respawn destroys the old Player the normal way. Outside that window (alive, after 30 s, guard file) = the engine as is.
static void (*g_brm_tramp)(uint8_t *body);
static void brm_hook(uint8_t *body) {
    uint8_t *exe = (uint8_t *)GetModuleHandleW(NULL);
    uint8_t *own = body && !IsBadReadPtr(body, 0x78) ? *(uint8_t **)(body + 0x68) : NULL;
    if (own && !IsBadReadPtr(own, 0xa0) && *(uint64_t *)own == (uint64_t)exe + 0x2cfc988ULL && rk_window(own, NULL)) {
        static volatile LONG n;
        LONG k = InterlockedIncrement(&n);
        if (k <= 4 || (k & 255) == 0)
            xlog("physics body guard: frame %llu - a body of our dead Player (%p, body %p, flags %08x) taken out of the physics world - removal held back #%ld (a removed body under a living Player = crash exe+25bcfd4; winmm's respawn removes it)",
                 (unsigned long long)g_frame, (void *)own, (void *)body, *(uint32_t *)(body + 0x58), (long)k);
        return;
    }
    g_brm_tramp(body);
}
static void install_killreq_guard(void) {
    // A/B (pairtest, exec gun / exec fists victim deaths + respawns on B): a normal downed death and its respawn make NO kill request on our Player,
    // so the refusal only meets the black-screen request. t2r-no-killreq-guard.txt = log only.
    FILE *f = exe_side_open("t2r-no-killreq-guard.txt", "r");
    if (f) { fclose(f); g_rk_off = 1; xlog("player kill request: guard off, log only (t2r-no-killreq-guard.txt)"); }
    // 0x1cea620: push rbx; sub rsp,20h; mov rax,[rcx]; mov rbx,rcx; call [rax+0xce0]   (18 bytes, no rip-relative operand)
    static const uint8_t e[18] = {0x40, 0x53, 0x48, 0x83, 0xec, 0x20, 0x48, 0x8b, 0x01, 0x48, 0x8b, 0xd9, 0xff, 0x90, 0xe0, 0x0c, 0x00, 0x00};
    g_rk_tramp = (void (*)(uint8_t *))vdf_inline(0x141cea620ULL, e, 18, (void *)rk_hook, "player kill request guard", (void **)&g_rk_tramp);
    xlog("player kill request: %s", g_rk_tramp ? "guard installed (logs the requester of every kill request on our Player; refuses it during a downed death)" : "NOT installed (exe code differs)");
    if (!g_rk_tramp) return;
    // 0x1c0fad0: push rbx; sub rsp,20h; vxorps xmm2,xmm2,xmm2; xor edx,edx; mov rbx,rcx   (15 bytes, no rip-relative operand; the call after it stays)
    static const uint8_t b[15] = {0x40, 0x53, 0x48, 0x83, 0xec, 0x20, 0xc5, 0xe8, 0x57, 0xd2, 0x33, 0xd2, 0x48, 0x8b, 0xd9};
    g_brm_tramp = (void (*)(uint8_t *))vdf_inline(0x141c0fad0ULL, b, 15, (void *)brm_hook, "physics body guard", (void **)&g_brm_tramp);
    xlog("physics body guard: %s", g_brm_tramp ? "installed (a body of our Player leaving the physics world while a kill request on it would be refused is not removed)" : "NOT installed (exe code differs)");
}
static void install_vdf_hook(void) {
    // mov [rsp+10h],rbx; mov [rsp+18h],rdi; push rbp; lea rbp,[rsp-100h]   (19 bytes, no rip-relative operand)
    static const uint8_t e1[19] = {0x48, 0x89, 0x5c, 0x24, 0x10, 0x48, 0x89, 0x7c, 0x24, 0x18, 0x55, 0x48, 0x8d, 0xac, 0x24, 0x00, 0xff, 0xff, 0xff};
    g_vdf_tramp = (fn_vdf)vdf_inline(0x140b57990, e1, 19, (void *)vdf_hook, "own death scream", (void **)&g_vdf_tramp);
    // 0x142029960: mov [rsp+8],rbx; mov [rsp+10h],rbp; mov [rsp+18h],rsi   (15 bytes)
    static const uint8_t e2[15] = {0x48, 0x89, 0x5c, 0x24, 0x08, 0x48, 0x89, 0x6c, 0x24, 0x10, 0x48, 0x89, 0x74, 0x24, 0x18};
    g_vdh_lclear_orig = (fn_vdh_lclear)vdf_inline(0x142029960, e2, 15, (void *)vdh_lclear, "player clear-all-actions", (void **)&g_vdh_lclear_orig);
    // 0x1420280a0: mov [rsp+18h],rbx; push rbp; push rsi; push rdi; sub rsp,40h (12 bytes), then a rip-relative mov: the 14-byte jump
    // does not fit before it -> the 12-byte form: mov rax, imm64; jmp rax (rax is free at entry)
    {
        static const uint8_t e3[12] = {0x48, 0x89, 0x5c, 0x24, 0x18, 0x55, 0x56, 0x57, 0x48, 0x83, 0xec, 0x40};
        uint8_t *f = (uint8_t *)GetModuleHandleW(NULL) + 0x20280a0;
        if (IsBadReadPtr(f, 12) || memcmp(f, e3, 12)) hook_miss(f, 12, "psync: exe build differs at 0x1420280a0, controller clear-all hook not installed");
        else {
            uint8_t *t = VirtualAlloc(NULL, 64, MEM_COMMIT | MEM_RESERVE, PAGE_EXECUTE_READWRITE);
            if (t) {
                memcpy(t, f, 12);
                t[12] = 0xff; t[13] = 0x25; *(uint32_t *)(t + 14) = 0; *(uint64_t *)(t + 18) = (uint64_t)(f + 12);
                g_vdh_cclear_orig = (fn_vdh_cclear)t;
                DWORD old; VirtualProtect(f, 12, PAGE_EXECUTE_READWRITE, &old);
                f[0] = 0x48; f[1] = 0xb8; *(uint64_t *)(f + 2) = (uint64_t)vdh_cclear; f[10] = 0xff; f[11] = 0xe0;
                VirtualProtect(f, 12, old, &old);
                FlushInstructionCache(GetCurrentProcess(), f, 12);
            }
        }
    }
    // the death controller's vtable slot 0x28 (Start an action = 0x142028660 for every anim-action controller; this vtable is the death
    // controller's own, so only it is affected)
    {
        uint64_t *slot = (uint64_t *)((uint8_t *)GetModuleHandleW(NULL) + (VDF_COMP_VT - 0x140000000ULL) + 0x28);
        uint64_t want = (uint64_t)GetModuleHandleW(NULL) + 0x2028660;
        if (IsBadReadPtr(slot, 8) || *slot != want)
            hook_fail("psync: exe build differs (death controller vtable +0x28 %llx), death anim hook not installed", IsBadReadPtr(slot, 8) ? 0ULL : (unsigned long long)*slot);
        else {
            g_vdh_start_orig = (fn_vdh_start)want;
            DWORD old; VirtualProtect(slot, 8, PAGE_READWRITE, &old);
            *slot = (uint64_t)vdh_start;
            VirtualProtect(slot, 8, old, &old);
        }
    }
    install_pkill_watch();
    install_killreq_guard();
    xlog("psync: own death hooks: scream %s, death anim (controller vtable +0x28) %s, controller clear-all %s, player clear-all %s",
         g_vdf_tramp ? "ok" : "MISSING", g_vdh_start_orig ? "ok" : "MISSING", g_vdh_cclear_orig ? "ok" : "MISSING", g_vdh_lclear_orig ? "ok" : "MISSING");
}
// the half has run out: the deferred anim side of the Death setup, then the body goes limp from its final pose (the death controller's
// ragdoll, vfunc 0x38(1, 0) = 0x140b55980)
static void vdf_limp(const char *why) {
    int act = vdf_active();
    uint8_t *me = vdf_player(), *c = vdf_comp(me);
    if (act) vdf_dump("at the end of the half", 1);
    // the deferred part of the Death setup runs whatever happened meanwhile (fix switched off, abort, ...)
    if (g_vdf_deferred_list && g_vdf_deferred_list == vdf_list(me) && g_vdh_lclear_orig) {
        g_vdh_lclear_orig(g_vdf_deferred_list, (uint64_t)(g_vdf_deferred_layer < 0 ? 0 : g_vdf_deferred_layer));
        xlog("psync: u%08x deferred clear-all-actions (layer %d) run now (%s)", g_ps.uid, g_vdf_deferred_layer, why);
    }
    g_vdf_deferred_list = NULL; g_vdf_deferred_layer = -1;
    if (!act) return;
    g_vdf_limp_done = 1;                      // from here the hooks pass everything through
    uint64_t st = vdf_state(me);
    if (c && st == VDF_DEATH_STATE) {
        typedef void (*fn_rag)(uint8_t *, uint64_t, uint64_t);
        g_vdf_exec_limp = 1;
        ((fn_rag)(*(void ***)c)[0x38 / 8])(c, 1, 0);
        xlog("psync: u%08x victim half over (%s) - Death state, death controller ragdoll (vfunc 0x38): the body goes limp from its final pose "
             "(death anims withheld during the half: %d)", g_ps.uid, why, g_vdf_withheld);
    } else xlog("psync: u%08x victim half over (%s) - NOT limp: comp %p, state %llx (Death %llx)", g_ps.uid, why, (void *)c, (unsigned long long)st, (unsigned long long)VDF_DEATH_STATE);
    g_vdf_withheld = 0;
}
// deathreact.c: the death reaction clip on our own body is over - the deferred anim side of the Death setup, then the death controller's ragdoll
// (vfunc 0x38(1, 0), as vdf_limp does at the end of an execution half). Returns 0 while the body is not in the Death state (the caller retries).
static int dr_release_own(const char *why, int *bit_out) {
    uint8_t *me = vdf_player(), *c = vdf_comp(me);
    uint64_t st = vdf_state(me);
    if (!c || st != VDF_DEATH_STATE) return 0;
    if (g_vdf_deferred_list && g_vdf_deferred_list == vdf_list(me) && g_vdh_lclear_orig) {
        g_vdh_lclear_orig(g_vdf_deferred_list, (uint64_t)(g_vdf_deferred_layer < 0 ? 0 : g_vdf_deferred_layer));
        xlog("deathreact: deferred clear-all-actions (layer %d) run now (%s)", g_vdf_deferred_layer, why);
    }
    g_vdf_deferred_list = NULL; g_vdf_deferred_layer = -1;
    typedef void (*fn_rag)(uint8_t *, uint64_t, uint64_t);
    ((fn_rag)(*(void ***)c)[0x38 / 8])(c, 1, 0);
    if (bit_out) *bit_out = me ? (me[0x9fd] & 1) : -1;
    return 1;
}
static int psync_vic_kill_passed(uint32_t slot) {
    return g_ps.role && slot < T2R_MAX_PEERS && g_ps.vic == (int)slot && (g_ps.flags & PS_F_LETHAL) && g_ps.kill_s > 0 &&
           psync_ms() - g_ps.t0 >= g_ps.kill_s * 1000.0 - 250.0;
}
static void psync_keep_tick(double t) {
    if (!g_ps.role || !(g_ps.vic_keep || g_ps.vic_own_lethal) || !g_ps.ent_vic) return;
    float dur = g_ps.vic_dur;
    if (g_ps.ent_vic == SID_PLAYER) {
        static double next_ev; static int ev_n;
        if (t < next_ev - 400.0) { next_ev = 0; ev_n = 0; }      // a new move
        if (t >= next_ev && ev_n < 12) {      // evidence for the next test: the kept half's layer and the state while it plays out
            next_ev = t + 300.0; ev_n++;
            xlog("psync: u%08x own victim half kept t=%.0f/%.0f ms: layer phase %.3f, state %llx%s", g_ps.uid, t, dur * 1000.0,
                 psync_phase(g_ps.ent_vic, g_ps.vic_sid), (unsigned long long)vdf_state(vdf_player()), g_vdf_off ? " (fix off)" : "");
        }
        if (t >= (double)dur * 1000.0 - 60.0) vdf_limp("clip end");
    }
    if (g_ps.vic_throat) return;                          // the SP throat death plays on the body now (shivdeath_tick): no half over it
    if (t >= (double)dur * 1000.0 - 80.0 || g_ps.keep_n > 12) return;
    // dropped = no layer: get-animation-phase answers -1 OR 0.000 (every 1007/1008 log: "layer phase 0.000" from Death enter on, so
    // the old "< 0" test never re-applied the half and the body showed no clip pose / no root motion for the rest of the move).
    // g_ps.lost[1] is that test against the move time (psync_tick). Throttled: one re-apply per 250 ms, 12 per move.
    if (!g_ps.lost[1] && psync_phase(g_ps.ent_vic, g_ps.vic_sid) >= 0.0f) return;
    if (psync_ms() - g_ps.keep_last < 250.0) return;
    float ph = (float)(t / 1000.0 / dur);
    if (ph > 0.97f) return;
    g_ps.keep_last = psync_ms();
    float bl = g_ps_blend;
    g_ps_blend = 0.1f;                                    // back on the clip at once (the pose under it is not the clip's)
    uint64_t r = psync_animate(g_ps.ent_vic, g_ps.vic_sid, &g_ps.bf_vic, ph, -1.0f);
    g_ps_blend = bl;
    g_ps.rate[1] = 0.0f;                                  // a new instance plays at 1.0
    xlog("psync: u%08x victim half dropped (%s, %s) - re-applied at phase %.3f -> %llx (#%d)", g_ps.uid,
         g_ps.ent_vic == SID_PLAYER ? "our body" : "puppet", g_ps.vic_keep ? "dead, half kept" : "before the kill", ph, (unsigned long long)r, ++g_ps.keep_n);
}
// downed death by a shot / melee hit / bleed-out (g_down_dying; the victim's own body kept the
// downed animation until the respawn). The death was made "like an execution" (lying overlay + clip kept, death anim withheld, the
// death controller's ragdoll vfunc 0x38 the frame after), but an execution's limp comes right after the DEFERRED clear-all of the
// player's actions at the end of its half; here the clear ran at Death enter and the body is still in the prone move mode, whose
// states keep asking for clips - and the UC4 lying overlay stayed on until the respawn, renaming them to the lying loop, so the
// body went on playing it. Hand-over: the frame after the ragdoll call, if the ragdoll bit is not set, the scripted ragdoll
// (player-go-ragdoll, as the game's own scripts limp a player) as well; once the ragdoll holds the body (bit set, or 10 frames
// at the latest) the lying overlay goes off and the own UC4 clip stops - nothing feeds the lying loop any more, the body stays limp
// from the pose it had. Executions are untouched (g_down_dying is 0 there). t2r-dd-keep-overlay.txt = the old behaviour.
static uint64_t g_dd_limp_frame, g_dd_check_frame;
static void dd_limp_tick(void) {
    if (!g_dd_limp_frame) return;
    static int keep = -1;
    if (keep < 0) { FILE *f = exe_side_open("t2r-dd-keep-overlay.txt", "r"); keep = f != NULL; if (f) fclose(f); }
    uint8_t *me = vdf_player();
    int bit = me && !IsBadReadPtr(me + 0x9fd, 1) ? (me[0x9fd] & 1) : -1;
    uint64_t el = g_frame - g_dd_limp_frame;
    if (!g_down_dying || keep) {
        if (keep) xlog("downed death: limp hand-over off (t2r-dd-keep-overlay.txt) - overlay kept until the respawn");
        g_dd_limp_frame = 0;
        return;
    }
    static int scripted;
    if (el == 0) scripted = 0;
    if (el >= 1 && !scripted && bit != 1) {
        uint64_t none = 0;
        scripted = 1;
        xlog("downed death: ragdoll bit %d after the death controller's ragdoll - player-go-ragdoll -> %llx", bit,
             (unsigned long long)dc_call(fnv64("player-go-ragdoll"), 0, &none));
    }
    if ((bit == 1 && el >= 2) || el >= 10) {
        xlog("downed death: pose handed to the ragdoll (bit %d, +%llu frames) - lying overlay off, own UC4 clip stopped", bit, (unsigned long long)el);
        if (g_uc4_down) uc4_stop(&g_uc4_me);
        {   // any scripted clip left on the clip layer (UC4 lying / knock / crawl) would keep feeding the powered ragdoll's motors the kneeling pose (frozen on all fours, bit 1)
            uint64_t sa[5] = {SID_PLAYER, ANIM_LAYER, 0, 0, 0};
            uint64_t sr = dc_call(fnv64("stop-animating"), 5, sa);
            xlog("downed death: clip layer %d cleared with no blend -> %llx", ANIM_LAYER, (unsigned long long)sr);
        }
        if (g_uc4_ov_on) uc4_ov_set(0, "downed death - limp");
        g_dd_limp_frame = 0;
        g_dd_check_frame = g_frame ? g_frame : 1;
    }
}
static void vdf_noanim_tick(void) {        // the no-death-anim mode ends once we live again (respawned)
    dd_limp_tick();
    if (g_dd_check_frame && (g_frame - g_dd_check_frame == 30 || g_frame - g_dd_check_frame == 120)) {   // evidence for the next test
        uint8_t *me = vdf_player();
        xlog("downed death: +%llu frames after the hand-over: ragdoll bit %d, state %llx, overlay %d", (unsigned long long)(g_frame - g_dd_check_frame),
             me && !IsBadReadPtr(me + 0x9fd, 1) ? (me[0x9fd] & 1) : -1, (unsigned long long)vdf_state(me), g_uc4_ov_on);
        if (g_frame - g_dd_check_frame >= 120) g_dd_check_frame = 0;
    }
    // With the death action withheld the dead downed player kept its prone state - movement keys
    // crawled the corpse in place, bleed-out showed the UC4 arms-up clip. The frame after the withheld start: the death
    // controller's own ragdoll (vfunc 0x38(1, 0), as at the end of an execution half) - limp, no animation, no input.
    static int rag_tries;
    if (g_vdf_rag_pending) {
        g_vdf_rag_pending = 0;
        uint8_t *me = vdf_player(), *c = vdf_comp(me);
        if (c && vdf_state(me) == VDF_DEATH_STATE) {
            typedef void (*fn_rag)(uint8_t *, uint64_t, uint64_t);
            g_vdf_ragged = 1;                   // once per death
            ((fn_rag)(*(void ***)c)[0x38 / 8])(c, 1, 0);
            xlog("death: downed death - death anim withheld, body ragdolled (death controller vfunc 0x38), ragdoll bit %d", me ? (me[0x9fd] & 1) : -1);
            rag_tries = 0;
            if (g_down_dying) g_dd_limp_frame = g_frame ? g_frame : 1;   // a shot / melee / bleed-out death: hand the pose over (below)
        } else {
            // not a Death state yet (or no controller): the death action was withheld, so nothing else will ragdoll this body - the
            // request stays pending and is retried every frame (bounded: a body that never reaches Death is not ours to limp)
            if (++rag_tries < 180) g_vdf_rag_pending = 1;
            else { xlog("death: downed death - ragdoll never became possible in 180 frames (comp %p, state %llx)", (void *)c, (unsigned long long)vdf_state(me)); rag_tries = 0; }
        }
    }
    if (!g_vdf_noanim) return;
    uint64_t ps = SID_PLAYER, dead = dc_call(0xe93f704f02a9ecd5ULL /* character-is-dead? */, 1, &ps);
    // the Player process was destroyed one frame into the downed death, so character-is-dead? FAILED (~0) - that was read as 'alive'
    // and the 2 s timer below gave the move stick back on the black death screen. A failed answer is UNKNOWN: nothing changes until the engine
    // answers 0 for a live player with hp (a respawned one); a body at hp <= 0 is dead whatever the script says.
    if (dead == ~0ULL) return;
    if (!(dead & 0xff) && !(local_hp() > 0.0f)) dead = 1;
    if (dead & 0xff) {
        // Shot dead while downed, the corpse still crawled in place on the victim's screen (prone locomotion
        // takes the move stick even with the body limp). Dead = no movement input, every frame as the game scripts do it
        uint64_t none = 0;
        dc_call(fnv64("player-disable-move-stick"), 0, &none);
        dc_call(fnv64("player-disable-jump"), 0, &none);
        dc_call(fnv64("player-disable-roll"), 0, &none);
        // (still crawled in place - the prone crawl reads the stick around player-disable-move-stick; the stick scale the
        // downed code uses for the crawl speed, at 0, stops the crawl input itself)
        float z = 0.0f;
        uint64_t ss[2] = {fnv64("move"), 0};
        memcpy(&ss[1], &z, sizeof z);
        dc_call(fnv64("joypad-set-stick-scale"), 2, ss);
        return;
    }
    if (g_t60 - g_vdf_noanim_frame < 120) return;      // 2 s of real time (g_t60 ticks)
    g_vdf_noanim = 0; g_vdf_ragged = 0; g_vdf_exec_limp = 0;
    xlog("death: alive again - downed no-death-anim mode off");
    {   // the stick scale zeroed while dead back to normal
        float one = 1.0f;
        uint64_t ss[2] = {fnv64("move"), 0};
        memcpy(&ss[1], &one, sizeof one);
        dc_call(fnv64("joypad-set-stick-scale"), 2, ss);
    }
    if (g_down_dying) {                        // a shot / bleed-out death kept the lying overlay and clip through the death
        g_down_dying = 0;
        if (g_uc4_down) uc4_stop(&g_uc4_me);
        if (g_uc4_ov_on) uc4_ov_set(0, "respawn after a downed death");
    }
}
// ---- smoothing: the attacker half's end (same move time on every client)
// Before: the attacker half held its clip's last pose until the LONGER half + PS_END_PAD_MS (kick pairs: the victim half is up to
// 1.3 s longer), then stop-animating 0.3 s - a frozen body for 0.12-1.4 s, then the puppet's net replay / locator came back in one
// frame (interpolation reset): the pop of the remote attacker grew with the one-way latency (the net pose / position lag behind).
// Now PS_OUT before the half's own end: our body - stop-animating(PS_OUT) while the clip still moves = the blend back to locomotion;
// a puppet - stop-animating(PS_OUT) on its half AND its net channels back (replay with a reset interpolation under the fading clip,
// pose writer, net locator through the hand-back). Its collider stays off / collision ignored until the move ends (the victim half
// still plays next to it).
// A new swing of our own while psync still places our released ATTACKER body on the old clip (its blend-out drive, psync_drive): a pin's blow 5 pressed 2 frames after blow 4's attacker release - the drive's set-object-locator every frame fought the new swing and the
// body slid to the world origin (313 -> 194 -> 0 in ~10 frames, 'pelvis -13 m', the hand-off left us out of the map). The drive ends here,
// before the swing starts: the engine gets the body at the drive's last placed spot (teleport-player, same as the drive's own end).
static void psync_own_att_free(const char *why) {
    if (g_ps.role != 1 || g_ps.ent_att != SID_PLAYER || !g_ps.out_done[0] || g_ps.att_drive_until <= 0.0) return;
    g_ps.att_drive_until = 0.0;
    int drv = g_ps.own_drv;
    if (drv && g_ps.att_last_ok && !psync_own_dead_now()) {
        // ps43 P1 (rec42a B [20895] 'paired.att_free TP 0.00 m (eng 0.64 ...)' -> [20896] 'SNAP slot 0 0.64 m ... teleport-player'): a body the engine has carried more
        // than PS_OUT_DRIVE_MAX_M from the drive's last placed spot is not on that clip any more - it stays where it is (as psync_att_out's ps41 rule at the fade's
        // start). t2r-att-free-far-old.txt = old.
        float fb43[16]; const float *fl43 = psync_loc(SID_PLAYER, fb43);
        float fd43 = fl43 && ps_loc_ok(fl43) ? __builtin_sqrtf((fl43[0] - g_ps.att_last[0]) * (fl43[0] - g_ps.att_last[0]) + (fl43[2] - g_ps.att_last[2]) * (fl43[2] - g_ps.att_last[2])) : 0.0f;
        // (Bookstore bots A [24506]-[24507]: the pull-out drag's blend-out drive ended at the grapple's lead, 'paired.att_free' turned our body 150 deg in one frame -
        // the drive's last placed spot was sampled on the drag clip's wrapped end (= its start pose, the drag turns the bodies 180 deg) and the grapple then started from a
        // flipped attacker): a placed spot whose facing is more than 30 deg off the body's is not this clip's end either - the body stays as it is.
        // t2r-att-free-yaw-old.txt = old (distance only).
        float yd16 = 0.0f;
        if (fl43 && ps_loc_ok(fl43)) { yd16 = uc4_yaw(fl43) - uc4_yaw(g_ps.att_last); while (yd16 > 180.0f) yd16 -= 360.0f; while (yd16 < -180.0f) yd16 += 360.0f; if (yd16 < 0.0f) yd16 = -yd16; }
        if (fd43 > PS_OUT_DRIVE_MAX_M && GetFileAttributesA("t2r-att-free-far-old.txt") == INVALID_FILE_ATTRIBUTES)
            xlog("psync: u%08x our attacker blend-out drive ends (%s) with the body %.2f m from its last placed spot - NOT teleported back, it stays where the engine has it (ps43 P1)", g_ps.uid, why, (double)fd43);
        else if (yd16 > 30.0f && GetFileAttributesA("t2r-att-free-yaw-old.txt") == INVALID_FILE_ATTRIBUTES)
            xlog("psync: u%08x our attacker blend-out drive ends (%s) with the body facing %.0f deg off its last placed spot (%.2f m) - NOT teleported (a wrapped clip sample; t2r-att-free-yaw-old.txt = old)", g_ps.uid, why, (double)yd16, (double)fd43);
        // (Bookstore bots A, pull-out grapple lead, both runs: 'paired.att_free' moved the body 0.00-0.01 m, then 'YAW SNAP slot 1 turned 150 deg'
        // the next frame): teleport-player restarts the engine's animation layer, and here the next pair's attacker half had just started on the body - the
        // grapple's first frame came out turned and the blend-in eased it back (the attacker snapped 90 degrees to the left on the pounce and then
        // smoothed back). A body that already stands on the drive's last placed spot needs no teleport. t2r-att-free-tp-always.txt = old.
        else if (fl43 && ps_loc_ok(fl43) && fd43 <= 0.05f && yd16 <= 5.0f && GetFileAttributesA("t2r-att-free-tp-always.txt") == INVALID_FILE_ATTRIBUTES)
            xlog("psync: u%08x our attacker blend-out drive ends (%s) with the body on its last placed spot (%.2f m, %.0f deg) - no teleport (it would restart the animation layer)", g_ps.uid, why, (double)fd43, (double)yd16);
        else mo_teleport(g_ps.att_last, g_ps.att_last + 4, MO_SRC("paired.att_free"), 0);
        g_ps.att_last_ok = 0;
    }
    g_ps.own_drv = 0;
    xlog("psync: u%08x our attacker blend-out drive ended early (%s)%s", g_ps.uid, why, drv ? ": body handed to the engine at its placed spot first" : "");
}
static void psync_att_out(double t) {
    if (g_ps.out_done[0]) return;
    g_ps.out_done[0] = 1;
    uint64_t ent = g_ps.ent_att;
    if (ent == SID_PLAYER) {
        g_ps.att_drive_until = psync_ms() + PS_OUT * 1000.0 + 120.0;     // (psync_drive: our body stays on the clip's placement through the fade)
        // ps41 (rec40a A [18764] 'execution: our half released after 3.91 s', [18765]-[18770] 'SNAP slot 1 0.15 m in 1 frame ... psync u015b8e3b kind 2 ... own drive
        // 1 out 10' six frames running, [18771] 'psync flicker ... ph 1.000 root stepped 1.751 m, its clip 0.000 m', [18772] 'hand-off probe ... the clip's end spot
        // (1.75 m away)'): the fade's drive pulls our body onto the half's placement - here the clip's END spot (its layer is gone, phase 1.000), 1.75 m from a
        // body the engine had kept in place. A body that stands more than PS_OUT_DRIVE_MAX_M from the half's placement when the fade starts was not on that
        // clip: no drive, it stays where it is and the half only fades. t2r-att-out-far-ps40.txt = old.
        {   float ob[16]; const float *ol = psync_loc(SID_PLAYER, ob);
            if (ol && ps_loc_ok(ol) && g_ps.place_ok[0] && GetFileAttributesA("t2r-att-out-far-ps40.txt") == INVALID_FILE_ATTRIBUTES) {
                float ox = ol[0] - g_ps.place[0][0], oz = ol[2] - g_ps.place[0][2], od = __builtin_sqrtf(ox * ox + oz * oz);
                if (od > PS_OUT_DRIVE_MAX_M) { g_ps.att_drive_until = 0;
                    xlog("psync: u%08x attacker half (our body) fades with NO drive - the body stands %.2f m from the half's placement (kind %d, t=%.0f ms): it was not on the clip, it stays where it is (ps41)", g_ps.uid, (double)od, g_ps.kind, t); }
            }
        }
        uint64_t r = psync_stop(SID_PLAYER, g_ps.att_sid, PS_OUT);
        // The pull-out fail clip leaves the attacker kneeling
        // over the body and this blend-out went straight to standing locomotion. It now lands in the engine crouch (player-force-crouch every frame
        // for PUL_RISE_MS, melee_pullout.c pul_rise_tick); the engine plays its own crouch -> stand after. t2r-pullout-rise-off.txt = off.
        if (g_ps.kind == PS_CTXDOWN && pul_fail_move(g_ps.move) && GetFileAttributesA("t2r-pullout-rise-off.txt") == INVALID_FILE_ATTRIBUTES) {
            uint64_t none = 0; dc_call(fnv64("player-force-crouch"), 0, &none);
            g_pul_rise_until = GetTickCount64() + PUL_RISE_MS; g_pul_rise_uid = g_ps.uid;
            xlog("pullout: fail blow over - the attacker blends out into the crouch, stands up in %d ms", PUL_RISE_MS);
        }
        float lb[16]; const float *l = player_locator(lb);
        xlog("psync: u%08x attacker half (our body) blend-out %.2f s from t=%.0f (clip end %.0f, move end %.0f) -> %llx: back to locomotion at %.2f %.2f %.2f",
             g_ps.uid, PS_OUT, t, g_ps.att_dur * 1000.0, g_ps.dur_s * 1000.0, (unsigned long long)r, l ? l[0] : 0.0f, l ? l[1] : 0.0f, l ? l[2] : 0.0f);
        return;
    }
    int s = g_ps.att;
    if (s < 0 || s > T2R_MAX_PEERS - 1 || g_ps_pup[s].h != ent || !g_ps_pup[s].on) return;
    if (psync_dead(ent)) { xlog("psync: u%08x attacker puppet dead at its blend-out - left to the death", g_ps.uid); return; }
    uint64_t r = psync_stop(ent, g_ps.att_sid, PS_OUT);
    g_ps_pup[s].early = 1;
    g_ps_pup[s].on = 0;                                       // replay / root write / pose writer / net locator back
    if (s < T2R_ENGINE_PEERS) InterlockedOr((volatile LONG *)(PA_SLOT(s) + 0x77e4), 3);
    psync_hb_arm(s, ent, "attacker half blend-out");
    xlog("psync: u%08x attacker puppet slot %d blend-out %.2f s from t=%.0f (clip end %.0f, move end %.0f) -> %llx: net replay back under the "
         "fading clip, locator handed back over the hand-back window", g_ps.uid, s, PS_OUT, t, g_ps.att_dur * 1000.0, g_ps.dur_s * 1000.0,
         (unsigned long long)r);
}
// Phase drift of a half vs the shared move time t (a hitch / a clamped frame on one client): a playback-rate nudge (<= PS_RATE_MAX,
// corrects in ~0.5 s) instead of a phase jump. Deadband 25 ms on / 10 ms off; the one-frame read lag (the layer's phase is the last
// anim update's) is taken out with this frame's dt so a steady game does nothing.
// v5-feel3: the hit-confirm wait's played clip time seeds the halves' move clock (psync_tick tk). Opt-out t2r-duel-no-hs-seed.txt, re-read every 2 s.
static int psync_hs_seed_on(void) {
    static uint64_t at; static int off = -1; static uint32_t logged_uid;
    uint64_t now = GetTickCount64();
    if (off < 0 || now - at >= 2000) { at = now; int o = GetFileAttributesA("t2r-duel-no-hs-seed.txt") != INVALID_FILE_ATTRIBUTES; if (o != off) xlog("psync: hit-confirm seed %s", o ? "OFF (t2r-duel-no-hs-seed.txt): the wait shifts the move clock by its whole length" : "ON: the move clock counts the clip time the slowed wait played"); off = o; }
    if (!off && logged_uid != g_ps.uid) { logged_uid = g_ps.uid;
        xlog("psync: u%08x hit-confirm seed: the move clock starts %.0f ms (attacker) / %.0f ms (victim) into the clips at the wait's end - played at x%.2f, no second slow-down", g_ps.uid,
             (double)(g_ps.ahold * 1000.0f * g_ps.hs_rate), (double)(g_ps.vlag * 1000.0f * g_ps.hs_rate), (double)g_ps.hs_rate); }
    return !off;
}
// ---- the slowed hold of the fist interrogation (intwarp.c): the move clock (g_ps.t0 and the exec timelines' copies) is moved forward by the time the slow-down loses,
// every frame, as a function of the shared clock only (base + iw_extra_at(real ms since the move's start)) - the same on every client; both halves play at IW_RATE inside
// the section (psync_rate keeps that rate as its base). Everything psync measures (phase = t / clip length, end, kill, blend-out) stays in clip time.
static float iw_rate_now(void) { return g_iw.on && g_iw.uid == g_ps.uid && g_iw.rate > 0.0f ? g_iw.rate : 1.0f; }
static void iw_tick(double now) {
    if (g_iw.uid != g_ps.uid) {
        int mi = g_ps.kind == PS_MELEE_EXEC ? mx_by_move(g_ps.move) : -1;
        g_iw.uid = g_ps.uid; g_iw.on = mi >= 0 && iw_name(MELEE2013[mi].name); g_iw.base = g_ps.t0; g_iw.rate = 1.0f;
        if (g_iw.on) xlog("interrogation slow-down: u%08x %s - the slowed sections %.0f..%.0f ms of the clips (eased, down to x%.2f) (kill %.0f -> %.0f ms of real time)", g_ps.uid,
                          MELEE2013[mi].name, IW_SEC[0][0], IW_SEC[1][1], (double)IW_SEC[0][2], (double)g_ps.kill_s * 1000.0, (double)g_ps.kill_s * 1000.0 + IW_EXTRA);
    }
    if (!g_iw.on) return;
    double R = now - g_iw.base, want = g_iw.base + iw_extra_at(R), d = want - g_ps.t0;
    if (d > 0.0005 || d < -0.0005) { g_ps.t0 = want; iw_copies_shift(d); }
    float rr = iw_rate_real(R);      // (eased: the rate follows the curve every few frames; exactly 1 outside the sections)
    if (rr > 0.985f) rr = 1.0f;
    if ((rr != g_iw.rate && (rr == 1.0f || g_iw.rate == 1.0f || __builtin_fabsf(rr - g_iw.rate) > 0.02f)) && g_ps.ent_att && g_ps.ent_vic) {
        static int nl; g_iw.rate = rr; psync_half_speed(0, rr); psync_half_speed(1, rr);
        if (LOGCAP(nl, 60)) xlog("interrogation slow-down: u%08x real %.0f ms = clip %.0f ms - both halves now at x%.2f", g_ps.uid, R, iw_clip_ms(R), rr);
    }
}
static void psync_rate(int k, float ph, double t) {
    uint64_t ent = k ? g_ps.ent_vic : g_ps.ent_att, sid = k ? g_ps.vic_sid : g_ps.att_sid;
    int slot = k ? g_ps.vic : g_ps.att;
    float hd = k ? g_ps.vic_dur : g_ps.att_dur;
    if (!ent || hd <= 0.2f || ph < 0.02f || ph > 0.97f || g_ps.out_done[k]) return;
    if (!k && g_ps.irate > 1.0f && g_ps.cur_seg == 0) return;          // (v5: the finisher intro's catch-up rate owns the attacker half until the hand-over)
    if (ent != SID_PLAYER && (slot < 0 || slot > T2R_MAX_PEERS - 1 || !g_ps_pup[slot].on || g_ps_pup[slot].h != ent)) return;
    float err = (float)((t - g_ps.tick_dt) / 1000.0) - ph * hd;            // + = the layer is behind the move time
    float base = (g_ps.speed > 1.001f ? g_ps.speed : 1.0f) * iw_rate_now();      // the move's own speed (ctxdown's sped-up takedowns; the interrogation's slowed hold); the drift nudge is relative to it
    float cur = g_ps.rate[k] > 0.0f ? g_ps.rate[k] : base, want = cur, a = __builtin_fabsf(err);
    float rmax = PS_RATE_MAX, gain = 2.0f;
    if (g_ps.catch_ms > 0.0f) { rmax = g_ps.role == 3 && !byst_old() ? PS_CATCH_BYST_RATE : PS_CATCH_RATE; gain = 4.0f; }       // smooth:noskip: x1.15 until the late START's lateness is absorbed (the deadband below ends it)
    if (a < 0.010f) { want = base; if (g_ps.catch_ms > 0.0f && cur != base && !g_ps.catch_n++) xlog("smooth: noskip u%08x %s half caught up (err %+.0f ms, rate back to x%.2f) at move time %.0f ms", g_ps.uid, k ? "victim" : "attacker", err * 1000.0f, base, t); }
    else if (a > 0.025f || cur != base) {
        float d = err * gain;
        want = base * (1.0f + (d > rmax ? rmax : d < -rmax ? -rmax : d));
    }
    if (__builtin_fabsf(want - cur) < 0.005f && !(want == base && cur != base)) return;
    uint64_t b[4] = {ent, 0, ANIM_LAYER, sid};
    memcpy(&b[1], &want, 4);
    uint64_t r = mo_rate_dc(b, MO_SRC("paired.drift_rate"));
    g_ps.rate[k] = want;
    if (g_ps.rate_n[k]++ < 16)
        xlog("psync: u%08x %s half on %s: phase %.3f is %+.0f ms off the move time %.0f -> playback rate %.3f (%llx)", g_ps.uid,
             k ? "victim" : "attacker", ent == SID_PLAYER ? "US" : "its puppet", ph, err * 1000.0f, t, want, (unsigned long long)r);
}
// ---- victim root (in executions our victim body did not travel the way the 2013 victim does)
// Offline (re/factions2013/t1anim/verify_victim_root.py): the shipped carriers' align / apReference channels and psync_place give the 2013
// victim align path to <= 3 cm for every pair (machete-decapitate 1.04 m, back shiv 1.81 m). In game the path was lost at the victim's
// DEATH: the Death state removes the half's layer (get-animation-phase then answers 0.000, not -1), so
//   - our own dead body was moved by nobody (the engine only applies the half's align while the layer plays) - it stopped at the kill;
//   - a placement from that 0.000 phase put a puppet back on the clip's START (the ap) unless the kick fix's phase > 0.6 test caught it
//     (machete kill 2.03 / 3.93 s = 0.52: not caught); psync_keep_tick never re-applied the half (it waited for -1).
// Now: a lost layer is told by the move time (psync_tick: lost[k]), its placement follows the move time, the dropped half is re-applied
// for the pose, and our own dead body is placed on the clip by psync like a puppet (psync_drive, smoothed take-over, wall guard).
static int psync_own_vic_needs_drive(void) {
    if (g_ps.pr_on) return 0;                            // power ragdoll on: the physics owns the body
    if (g_vdf_limp_done) return 0;                       // the half is over and the body limp: the ragdoll owns it
    // Under a truck the bodies were not synced: our own prone body in a pull-out drag stayed under the vehicle - the character
    // controller refused the clip's root motion into the truck (A [11740]-[11845]: victim ap y -1.93 held while the clip went to -0.68, err 1.24 m,
    // then a snap at 2.05 s) while the attacker's screen dragged our puppet out. psync places our live body on the clip for every pull-out pair,
    // no wall guard (the drag path is the way out); pul_vic_end hands the body to the engine with teleport-player. t2r-pullout-vdrive-off.txt = off.
    if (g_ps.kind == PS_CTXDOWN && pul_drag_move(g_ps.move) && GetFileAttributesA("t2r-pullout-vdrive-off.txt") == INVALID_FILE_ATTRIBUTES) { g_ps_pul_vdrv = 1; return 1; }
    if (g_ps.vic_keep) return 1;                         // dead at the kill frame, half kept to its end
    // alive with a lost layer: psync_keep_tick re-applies the half and the engine places us again - no locator writes on a live player
    uint8_t *me = vdf_player();
    return me && vdf_state(me) == VDF_DEATH_STATE;
}
static int psync_own_dead_now(void) { uint8_t *me = vdf_player(); return !me || vdf_state(me) == VDF_DEATH_STATE; }
// Nothing through walls: the driven victim body (a puppet, or our own dead body) moves on its clip with no collider. An async static-world
// ray (mask 0x207, kick now / read next frame) from where it was put last frame to 0.35 m beyond the new target, 0.35 m above the ground:
// a hit holds the body's x / z where it was (y and rotation follow the clip) until a ray says the way is clear again.
static void psync_wall_guard(float *t, int armed) {
    if (!armed || !g_ps.last_put_ok) { g_ps.wall_hold = 0; if (g_ps.wall_job) { ray_t(g_ps.wall_job); g_ps.wall_job = 0; } return; }
    static float wa[3], wb[3];       // the pending ray's ends
    if (g_ps.wall_job) {
        float rt = ray_t(g_ps.wall_job);
        g_ps.wall_job = 0;
        if (rt >= 0.0f && rt < 0.95f) {   // a hit on the OTHER body (the attacker's capsule, standing at the victim) is no wall
            float bb[16], hp[3];
            const float *al = psync_loc(g_ps.ent_att, bb);
            for (int i = 0; i < 3; i++) hp[i] = wa[i] + (wb[i] - wa[i]) * rt;
            if (al && (hp[0] - al[0]) * (hp[0] - al[0]) + (hp[2] - al[2]) * (hp[2] - al[2]) < 0.5f * 0.5f) rt = 1.0f;
        }
        if (rt >= 0.0f && rt < 0.95f) {
            if (!g_ps.wall_hold) {
                g_ps.wall_hold = 1; memcpy(g_ps.wall_pos, g_ps.last_put, 12);
                if (g_ps.wall_hits++ < 8) xlog("victim root: u%08x wall %.2f along the way at t=%.0f ms - body held at %.2f %.2f %.2f", g_ps.uid, rt,
                                               psync_ms() - g_ps.t0, g_ps.wall_pos[0], g_ps.wall_pos[1], g_ps.wall_pos[2]);
            }
        } else if (rt >= 0.95f && g_ps.wall_hold) {
            g_ps.wall_hold = 0;
            xlog("victim root: u%08x way clear again at t=%.0f ms - body back on its clip", g_ps.uid, psync_ms() - g_ps.t0);
        }
    }
    const float *from = g_ps.wall_hold ? g_ps.wall_pos : g_ps.last_put;
    float dx = t[0] - from[0], dz = t[2] - from[2], d = __builtin_sqrtf(dx * dx + dz * dz);
    if (d > 0.005f && d < 4.0f) {
        float a[3] = {from[0], from[1] + 0.35f, from[2]}, b[3] = {t[0] + dx / d * 0.35f, t[1] + 0.35f, t[2] + dz / d * 0.35f};
        // ignore the driven victim body itself: on the attacker's screen it is a puppet whose own capsule the ray started inside and hit
        // ("wall 0.57 along the way": the back-shiv victim held 1.8 m short of its path; B's own view, which ignores
        // SID_PLAYER = the victim, had none)
        g_ps.wall_job = world_ray_kick_ign(a, b, g_ps.ent_vic);
        memcpy(wa, a, sizeof wa); memcpy(wb, b, sizeof wb);
    }
    if (g_ps.wall_hold) { t[0] = g_ps.wall_pos[0]; t[2] = g_ps.wall_pos[2]; }
}
// the clip's placement of a half at phase ph without touching the per-frame half-yaw state (the "victim root:" authored value)
static int psync_place_at(int k, float ph, float *out) {
    float hy = g_ps.half_yaw[k]; int ok = g_ps.half_yaw_ok[k];
    int r = psync_place(k, ph, out);
    g_ps.half_yaw[k] = hy; g_ps.half_yaw_ok[k] = ok;
    return r;
}
// Female victim puppet T-posed on a male-local screen: what the puppet's anim control really holds while its half plays -
// the AnimData object it uses vs ours (generation, pointer), our own body's duration of the same clip vs the puppet's, and every layer
// of its anim control (name, type, weights, clip, phase). A layer that carries the clip with weight > 0 and a bind pose in "victim root:"
// = the sampler wrote no joints (binding / mask / retarget of that body); no such layer = the half never reached the puppet's graph.
static void psync_pup_probe_of(const char *tag, uint64_t ent, int s, uint64_t sid, const char *who) {
    if (ent == SID_PLAYER || !ent) return;
    typedef uint8_t *(*fn_proc)(uint64_t);
    uint8_t *proc = ((fn_proc)VMA(0x18000A200))(ent);
    int32_t pg = 0, mg = 0;
    const uint8_t *mine = *(uint8_t *const volatile *)VMA(0x18015BA50);
    uint64_t ov = s >= 0 && s < 8 ? pa_ovr50[s] : 0;
    int okp = ov && pa_obj_gen((const uint8_t *)ov, &pg), okm = pa_obj_gen(mine, &mg);
    float dp = psync_dur(ent, sid), dm = psync_dur(SID_PLAYER, sid);
    xlog("psync probe %s: u%08x %s puppet slot %d proc %p | AnimData: puppet's own %s (gen %d) vs ours %p (gen %d) | clip %s: %.2f s on the puppet, %.2f s on our body | gun set %s",
         tag, g_ps.uid, who, s, (void *)proc, ov ? "override" : "= ours (no override)", okp ? (int)pg : 0, (const void *)mine, okm ? (int)mg : 0,
         psync_name(sid), dp, dm, s >= 0 && s < T2R_MAX_PEERS ? (g_pa_want[s] == 2 ? "abby" : g_pa_want[s] == 1 ? "ellie" : "default") : "?");
    vdf_lay cur[48];
    int n = vdf_layers(proc, cur, 48);
    for (int i = 0; i < n; i++) {
        vdf_lay *l = &cur[i];
        if (!l->used && !l->anim) continue;
        xlog("psync probe %s:   L%-2d %016llx type %d w %.2f/%.2f/%.2f fade %.2f n %d clip %s ph %.3f state %016llx | raw +34 %.3f +40 %.3f +44 %.3f flags +3c %02x +3d %02x%s", tag, i, (unsigned long long)l->name,
             l->type, l->w[0], l->w[1], l->w[2], l->fade, l->n, l->anim ? psync_name(l->anim) : "-", l->ph, (unsigned long long)l->state,
             l->raw[0], l->raw[1], l->raw[2], l->f3c, l->f3d,
             l->anim && l->anim == sid ? "  <== the half" : "");
    }
    xlog("psync probe %s: %d layers on the puppet's anim control", tag, n);
}
static void psync_pup_probe(const char *tag) { psync_pup_probe_of(tag, g_ps.ent_vic, g_ps.vic, g_ps.vic_sid, "victim"); }
// "victim root:" every 250 ms of move time, on every screen: the authored offset (the half's placement at the move-time phase = the
// 2013 align path, ap space) vs where the body is (placed), who moves it and the phase the layer reads
static void psync_vic_root_log(double t, float ph) {
    int b = (int)(t / 250.0);
    if (b == g_ps.root_bucket || t < 0.0 || t > (double)g_ps.vic_dur * 1000.0 + 300.0) return;
    g_ps.root_bucket = b;
    if (b == 1 || b == 6) psync_pup_probe(b == 1 ? "250 ms" : "1500 ms");
    float au[8], bb[16], ia[4] = {0}, ip[4] = {0};
    float mt = g_ps.mt[1] > 1.0f ? 1.0f : g_ps.mt[1];
    int aok = g_ps.c_vic_ok && psync_place_at(1, mt, au);
    const float *l = psync_loc(g_ps.ent_vic, bb);
    if (aok) psync_in_ap(au, ia);
    if (l) psync_in_ap(l, ip);
    float dx = ip[0] - ia[0], dz = ip[1] - ia[1];
    const char *who = g_ps.ent_vic == SID_PLAYER ? (g_ps.own_drv ? "our body by psync" : "our body by the engine") :
                      g_ps.vic >= 0 && g_ps.vic < T2R_MAX_PEERS && g_ps_pup[g_ps.vic].on ? "puppet by psync" : "puppet released";
    // (male attacker, FEMALE victim puppet T-posed on the attacker's screen while the victim's own screen was fine, the
    // layer's phase advanced and the clip's part effects fired on the puppet): what the puppet's skeleton really shows, every 250 ms - the
    // head / pelvis heights over the locator and the hand joints (span, heights): bind pose = hands ~1.5 m apart at ~1.4 m; and which anim
    // table the puppet uses here (pa_ovr50: "own" = its body's AnimData differs from ours, the male / female pair case)
    char pose[200] = "";
    if (g_ps.ent_vic != SID_PLAYER && l) {
        float hd[3], pv[3], lh[3], rh[3];
        int okh = gx_joint_pos(g_ps.ent_vic, "headb", hd), okp = gx_joint_pos(g_ps.ent_vic, "pelvis", pv);
        int okl = gx_joint_pos(g_ps.ent_vic, "l_hand_prop_attachment", lh), okr = gx_joint_pos(g_ps.ent_vic, "r_hand_prop_attachment", rh);
        float span = okl && okr ? __builtin_sqrtf((lh[0] - rh[0]) * (lh[0] - rh[0]) + (lh[1] - rh[1]) * (lh[1] - rh[1]) + (lh[2] - rh[2]) * (lh[2] - rh[2])) : -1.0f;
        int sl = g_ps.vic;
        snprintf(pose, sizeof pose, " | pose: head %.2f pelvis %.2f, hands %.2f m apart at %.2f / %.2f%s | anim table %s",
                 okh ? hd[1] - l[1] : -1.0f, okp ? pv[1] - l[1] : -1.0f, span, okl ? lh[1] - l[1] : -1.0f, okr ? rh[1] - l[1] : -1.0f,
                 span > 1.2f && okl && okr && lh[1] - l[1] > 1.2f && rh[1] - l[1] > 1.2f ? " BIND POSE?" : "",
                 sl >= 0 && sl < 8 && pa_ovr50[sl] ? "= the puppet's own (other body than ours)" : "= ours");
    } else if (g_ps.ent_vic == SID_PLAYER && l) {
        // ps42 J1 MEASUREMENT (rec41a 155.5-157.6 s, A's own body in wpn-blade-wall-neck-chop: the body floats with the legs folded under it while the decoded
        // victim clip keeps both ankles 0.13-0.19 m over the root and lowers the pelvis 0.89 -> 0.23 m; the open-ground blade rows were clean): our OWN victim
        // body's pelvis / ankle heights over its root every 250 ms, to compare with the clip (S/ps42body/pose.py). Ankles well over the clip's = something
        // on our body (leg IK on the wall's collision, an overlay) lifts the feet; t2r-pair-vic-legik-off.txt = the in-game bisect for the leg IK.
        float pv[3], la[3], ra[3];
        int okp = gx_joint_pos(SID_PLAYER, "pelvis", pv), okl = gx_joint_pos(SID_PLAYER, "l_ankle", la), okr = gx_joint_pos(SID_PLAYER, "r_ankle", ra);
        snprintf(pose, sizeof pose, " | own pose: pelvis %.2f, ankles %.2f / %.2f m over the root (y %.2f)%s (ps42)", okp ? pv[1] - l[1] : -1.0f, okl ? la[1] - l[1] : -1.0f,
                 okr ? ra[1] - l[1] : -1.0f, l[1], okl && okr && la[1] - l[1] > 0.30f && ra[1] - l[1] > 0.30f ? " BOTH FEET OFF THE GROUND" : "");
    }
    xlog("victim root: u%08x r%d t=%4d %s | authored %.2f %.2f yaw %4.0f (%.2f m from the ap) | placed %.2f %.2f yaw %4.0f (%.2f m) | err %.2f m | "
         "%s, phase used %.3f move ph %.3f%s%s%s%s", g_ps.uid, g_ps.role, b * 250, psync_name(g_ps.vic_sid), ia[0], ia[1], ia[3],
         __builtin_sqrtf(ia[0] * ia[0] + ia[1] * ia[1]), ip[0], ip[1], ip[3], __builtin_sqrtf(ip[0] * ip[0] + ip[1] * ip[1]),
         aok && l ? __builtin_sqrtf(dx * dx + dz * dz) : -1.0f, who, ph, g_ps.mt[1], g_ps.lost[1] ? " LOST" : "", g_ps.vic_keep ? " dead/kept" : "",
         g_ps.wall_hold ? " WALL" : "", pose);
}
// "attacker pose:" every 250 ms of move time, for an ATTACKER half played by a puppet on this screen (the terminator-left
// executioner looked like a backpack on the floor: the attacker's chest read at the floor for the whole move while its root was placed on the
// clip to 0.00 m - the only line that looked at the attacker's skeleton was the one-frame "pose pop (collapse)", which every half start
// raises). head / chest / pelvis / hands over the locator, the half layer's weight and phase (psync_pup_probe_of at 250 ms and 1500 ms lists
// every layer of the anim control). "COLLAPSED" = pelvis and chest within 0.25 m of the locator for a clip that stands: the sampler wrote
// no usable pose while the layer runs.
// Trace: the first 45 frames of an attacker half on a puppet, every frame: pelvis / chest over the locator and every
// anim-control layer that is used or weighted (raw weight / fade fields, instance count, clip, phase, state). A collapsed start and a good one
// can then be diffed field by field. Logs "atttrace:". The dev build logs every frame; a release build keeps the first 12 frames of each
// half in memory and writes them only when one of them collapsed (6 halves per session), so player logs carry the evidence.
static void psync_att_trace(double t) {
    static uint32_t uid; static int f, flushed, nflush;
    static char keep[12][1400];
    if (g_ps.uid != uid) { uid = g_ps.uid; f = 0; flushed = 0; }
    uint64_t h = g_ps.ent_att;
    if (f > 45 || !h || h == SID_PLAYER || g_ps.att < 0 || g_ps.att >= T2R_MAX_PEERS) return;
    typedef uint8_t *(*fn_proc)(uint64_t);
    uint8_t *proc = ((fn_proc)VMA(0x18000A200))(h);
    float lb[16]; const float *l = psync_loc(h, lb);
    float ch[3], pv[3];
    int okc = gx_joint_pos(h, "spined", ch), okp = gx_joint_pos(h, "pelvis", pv);
    float cy = l && okc ? ch[1] - l[1] : -9.0f, py = l && okp ? pv[1] - l[1] : -9.0f;
    vdf_lay cur[48];
    int n = vdf_layers(proc, cur, 48);
    char buf[1200]; size_t k = 0;   // (the loop stops at ~1000 chars; 1200 + the prefix fits keep[] of 1400)
    for (int i = 0; i < n && k + 160 < 1000; i++) {    // xlog cuts a line at 1100 chars
        vdf_lay *L = &cur[i];
        if (!L->used && !L->anim && L->w[0] == 0.0f && L->w[1] == 0.0f && L->w[2] == 0.0f) continue;
        k += (size_t)snprintf(buf + k, SNLEFT(buf, k), " | L%d t%d u%d w%.2f/%.2f/%.2f f%.2f r%.2f/%.2f n%d %s ph%.3f st%04llx f3c%02x",
                              i, L->type, L->used, L->w[0], L->w[1], L->w[2], L->fade, L->raw[1], L->raw[2], L->n,
                              L->anim ? (L->anim == g_ps.att_sid ? "HALF" : psync_name(L->anim)) : "-", L->ph, (unsigned long long)(L->state & 0xffff), L->f3c);
    }
    int col = py > -1.0f && py < 0.25f && cy < 0.25f;
#ifndef T2R_RELEASE
    xlog("atttrace: u%08x f%d t=%.0f slot %d pelvis %.2f chest %.2f%s%s", g_ps.uid, f, t, g_ps.att, py, cy, col ? " COLLAPSED" : "", buf);
    (void)keep; (void)flushed; (void)nflush;
#else
    if (f < 12) {
        snprintf(keep[f], sizeof keep[f], "atttrace: u%08x f%d t=%.0f slot %d pelvis %.2f chest %.2f%s%s", g_ps.uid, f, t, g_ps.att, py, cy, col ? " COLLAPSED" : "", buf);
        if (col && !flushed && nflush < 6) {
            flushed = 1; nflush++;
            int was = g_xlog_nolimit; g_xlog_nolimit = 1;     // one half's lines share a rate-limit key
            for (int i = 0; i <= f; i++) xlog("%s", keep[i]);
            g_xlog_nolimit = was;
        } else if (flushed) { int was = g_xlog_nolimit; g_xlog_nolimit = 1; xlog("%s", keep[f]); g_xlog_nolimit = was; }
    }
#endif
    f++;
}
static void psync_att_pose_log(double t, float ph) {
    static uint32_t uid; static int bucket = -1;
    if (g_ps.uid != uid) { uid = g_ps.uid; bucket = -1; }
    int b = (int)(t / 250.0);
    if (b == bucket || t < 0.0 || t > (double)g_ps.att_dur * 1000.0 + 300.0) return;
    uint64_t h = g_ps.ent_att;
    if (!h || h == SID_PLAYER || g_ps.att < 0 || g_ps.att >= T2R_MAX_PEERS) return;
    bucket = b;
    if (b == 1 || b == 6) psync_pup_probe_of(b == 1 ? "250 ms" : "1500 ms", h, g_ps.att, g_ps.att_sid, "attacker");
    float lb[16]; const float *l = psync_loc(h, lb);
    if (!l) return;
    float hd[3], ch[3], pv[3], lh[3], rh[3];
    int okh = gx_joint_pos(h, "headb", hd), okc = gx_joint_pos(h, "spined", ch), okp = gx_joint_pos(h, "pelvis", pv);
    int okl = gx_joint_pos(h, "l_hand_prop_attachment", lh), okr = gx_joint_pos(h, "r_hand_prop_attachment", rh);
    float span = okl && okr ? __builtin_sqrtf((lh[0] - rh[0]) * (lh[0] - rh[0]) + (lh[1] - rh[1]) * (lh[1] - rh[1]) + (lh[2] - rh[2]) * (lh[2] - rh[2])) : -1.0f;
    float ph_l = psync_phase(h, g_ps.att_sid);
    float ey = okp ? pv[1] - l[1] : -1.0f, cy = okc ? ch[1] - l[1] : -1.0f;
    int collapsed = okp && okc && ey < 0.25f && cy < 0.25f && t > 400.0;
    static int ncol;
    xlog("attacker pose: u%08x r%d t=%4d %s slot %d | pose: head %.2f chest %.2f pelvis %.2f, hands %.2f m apart | half layer phase %.3f (move %.3f) | %s%s",
         g_ps.uid, g_ps.role, b * 250, psync_name(g_ps.att_sid), g_ps.att, okh ? hd[1] - l[1] : -1.0f, cy, ey, span, ph_l, ph,
         g_ps_pup[g_ps.att].on ? "puppet by psync" : "puppet released", collapsed ? " COLLAPSED (the skeleton is at the locator)" : "");
    if (collapsed && ncol++ < 6) psync_pup_probe_of("collapsed attacker", h, g_ps.att, g_ps.att_sid, "attacker");
}
// The victim half of a lethal move never runs off its end: 100 ms before it the layer is frozen (playback rate 0) on the final pose,
// so the dead body never falls back to its base (standing) pose before the ragdoll / death pose takes it (hunting rifle case: the body stood up for ~0.2 s at the end, then dropped). Every body that plays it (ours, a puppet, third party).
static void psync_vic_end_hold(double t) {
    static uint32_t done_uid;
    // (puppets only: our own body goes limp at the clip end through the death controller's ragdoll, vdf_limp, and a frozen layer on the
    // player would outlive the respawn)
    // Revive symptom (characters reset their anim pose / stand up briefly): the revive's FINISH halves differ in length (reviver 1.00 s, revived 0.83 s)
    // and the move runs to the longer one + PS_END_PAD_MS. The revived's puppet clip ended ~0.3 s before the move did, its layer vanished and the body
    // fell to the base pose (the "pose pop (collapse): pelvis 1.01 -> 0.00 ... paired-victim busy-slot" lines 60-80 frames after every FINISH start in
    // several reports, role 1 and role 3 screens). The revived half holds on its final (standing) pose until the move ends, as a
    // killed victim's does. The attacker half already fades out PS_OUT before its end (psync_att_out).
    int rv_tail = g_ps.kind == PS_REVIVE && g_ps.cur_seg == 2 && (double)g_ps.vic_dur * 1000.0 + 60.0 < g_ps.dur_s * 1000.0;
    if (!((g_ps.flags & PS_F_LETHAL) || rv_tail) || g_ps.vic_dur <= 0.2f || !g_ps.ent_vic || g_ps.ent_vic == SID_PLAYER || done_uid == g_ps.uid) return;
    if (t < (double)g_ps.vic_dur * 1000.0 - 100.0) return;
    done_uid = g_ps.uid;
    float zero = 0.0f;
    uint64_t b[4] = {g_ps.ent_vic, 0, ANIM_LAYER, g_ps.vic_sid};
    memcpy(&b[1], &zero, 4);
    uint64_t r = mo_rate_dc(b, MO_SRC("paired.vic_end_hold"));
    g_ps.rate[1] = 0.0f; g_ps.out_done[1] = 1;           // no rate correction on it any more
    psync_hold_end_pose(g_ps.ent_vic, g_ps.vic_sid, g_ps.vic_dur, "victim end hold");
    xlog("psync: u%08x victim half frozen on its final pose at t=%.0f ms (clip %.0f ms, layer phase %.3f) on %s -> %llx: no fall back to "
         "the base pose before the ragdoll", g_ps.uid, t, g_ps.vic_dur * 1000.0, psync_phase(g_ps.ent_vic, g_ps.vic_sid),
         g_ps.ent_vic == SID_PLAYER ? "our body" : "the puppet", (unsigned long long)r);
}
// corpse hold end: the puppet respawned (new handle) / lives again
static void psync_corpse_tick(double now) {
    for (int s = 0; s < T2R_MAX_PEERS; s++) {
        if (!g_ps_pup[s].corpse || (g_ps.role && (s == g_ps.att || s == g_ps.vic))) continue;
        uint64_t h = g_ps_pup[s].h;
        int same = h && psync_puppet(s) == h, dead = same && psync_dead(h);
        // (a player was invisible to others at the end of the match: a corpse hold lasted 45 s on the others' screens: the held body
        // stayed dead with its net channels suspended, the respawned player was never shown. The NETWORK saying the player is alive again
        // (peer live, not net-dead) now ends the hold too, and no hold outlives the longest respawn wait (20 s).)
        typedef uint8_t *(*fn_peer_c)(uint32_t);
        uint8_t *pe = ((fn_peer_c)t2r_peer)((uint32_t)s);
        int net_alive = pe && !IsBadReadPtr(pe, 8) && pe[4] && !pe[5] && !g_peer_downed[s];
        // (alive: only after 3 s - the held death of the attacker side lands a few frames after the hold started, psync_release_victim_pup)
        if (same && (dead || now - g_ps_pup[s].corpse_ms < 3000.0) && !(net_alive && now - g_ps_pup[s].corpse_ms > 6000.0) && now - g_ps_pup[s].corpse_ms < 20000.0) continue;
        xlog("psync: slot %d corpse hold ended after %.0f ms (%s)", s, now - g_ps_pup[s].corpse_ms,
             !same ? "puppet replaced (respawn / gone)" : !dead ? "alive again" : net_alive ? "the network says alive (respawned)" : "20 s");
        g_ps_pup[s].corpse = 0; g_ps_pup[s].on = 0;
        if (same) { if (s < T2R_ENGINE_PEERS) InterlockedOr((volatile LONG *)(PA_SLOT(s) + 0x77e4), 3); psync_stop(h, g_ps_pup[s].corpse_sid, 0.2f); }
        g_ps_pup[s].h = 0; g_ps_pup[s].proc = NULL; g_ps_pup[s].ac = NULL;
    }
}
// real-time length (ms) of the current chain segment: the shorter half, or the segment's cut (clip seconds / speed) if that is earlier
static double psync_seg_len_ms(void) {
    double l = (double)(g_ps.att_dur < g_ps.vic_dur ? g_ps.att_dur : g_ps.vic_dur) * 1000.0;
    if (g_ps.nseg > 1 && g_ps.cur_seg < g_ps.nseg - 1 && g_ps.seg_cut[g_ps.cur_seg] > 0.0f) {
        double c = (double)g_ps.seg_cut[g_ps.cur_seg] / (g_ps.speed > 1.001f ? (double)g_ps.speed : 1.0) * 1000.0;
        if (c < l) l = c;
    }
    return l;
}
// ---- chains: switch both halves to the next segment (see g_ps.nseg). Runs on every client at the same move time (the boundary = the shorter half's real-time length), so the
// halves, the puppets, the camera and the sounds stay on one clock: t0 moves forward by the boundary (t = time inside the new segment), chain_shift keeps the absolute time.
static void psync_seg_next(double now) {
    double bnd = psync_seg_len_ms();
    int i = g_ps.cur_seg + 1;
    uint64_t na = g_ps.seg_att[i], nv = g_ps.seg_vic[i];
    float spd = g_ps.seg_spd[i] > 1.001f ? g_ps.seg_spd[i] : 1.0f;
    float da = psync_dur(g_ps.ent_att, na), dv = psync_dur(g_ps.ent_vic, nv);
    if (da <= 0.0f || dv <= 0.0f) {
        xlog("psync: u%08x chain segment %d: clip not loaded (%s %.2f s, %s %.2f s) - the chain ends here", g_ps.uid, i, psync_name(na), da, psync_name(nv), dv);
        g_ps.nseg = g_ps.cur_seg + 1;       // no further switches: the last played segment runs on (the owner's hand-off ends the move)
        return;
    }
    // v5-feel2 (A v5-int8 [20696] 'FINISHER hand-over ... played 540 ms real ... its layer at phase 0.000 now', the intro is 533 ms): the switch runs on the
    // first frame at / after the boundary, so with ~20 ms frames the intro layer has often just run out (the read answers 0.000, the other one 0.955). It
    // played fully - but sptl took 0.000 for "not near its end" and the -sync main clip came in on the default blend over the ended layer instead of at
    // full weight (no 'sptl: ... at full weight on the switch' line for that finisher). At the switch a phase near 0 can only mean it ran out.
    float sptl_iph = psync_phase(g_ps.ent_att, g_ps.att_sid);
    if (sptl_iph >= 0.0f && sptl_iph < 0.05f && now - g_ps.t0 >= bnd) sptl_iph = 1.0f;
    float sptl_bl = g_ps.cur_seg == 0 && g_ps.kind == PS_CTXDOWN && cd_mf_intro_move(g_ps.move) ? sptl_seg_att_blend(sptl_iph) : -1.0f;   // (sptl: the finisher's main clip cut in)
    // (A/B clip review, verified in the frames 8.20-8.50 s: a fist finisher started mid-swing skipped 267 ms of its intro (phase 0.950, 'windup ... played
    // 3 ms real'), so the full-weight switch cut the body from the punch pose straight onto the -sync clip's frame 0 - both arms flung out for ~8 frames). The
    // SP full-weight switch assumes the intro brought the body to that pose; an intro that barely played blends the main clip in from the body's own pose.
    if (sptl_bl == 0.0f && now - g_ps.play_ms < 150) { xlog("psync: u%08x finisher intro played only %llu ms on the body - the main clip blends in over 0.25 s from the body's own pose (no cut)", g_ps.uid, (unsigned long long)(now - g_ps.play_ms)); sptl_bl = 0.25f; }
    int was_cut = g_ps.seg_cut[g_ps.cur_seg] > 0.0f;      // the previous segment was cut short (ctxdown's push at its best-matching frame, ctxcut.py)
    if (g_ps.cur_seg == 0 && g_ps.kind == PS_CTXDOWN && cd_mf_intro_move(g_ps.move)) {
        float iph = psync_phase(g_ps.ent_att, g_ps.att_sid);
        xlog("psync: u%08x FINISHER hand-over (role %d): windup %s played %.0f ms real (from phase 0, x%.2f, %.0f ms late absorbed) - its layer at phase %.3f now%s; the -sync pair from phase %.3f",
             g_ps.uid, g_ps.role, psync_name(g_ps.att_sid), now - g_ps.play_ms, g_ps.irate > 1.0f ? g_ps.irate : 1.0f, g_ps.ilate, iph, iph >= 0.0f && iph < 0.05f ? " (ran out just before this frame: played fully)" : "",
             (float)((now - g_ps.t0 - bnd) / 1000.0) > 0.0f ? (float)((now - g_ps.t0 - bnd) / 1000.0) / fmaxf(0.1f, psync_dur(g_ps.ent_att, g_ps.seg_att[g_ps.cur_seg + 1])) : 0.0f);
        g_ps.irate = 0.0f;
    }
    g_ps.t0 += bnd; g_ps.chain_shift += bnd;
    g_ps.cur_seg = i;
    g_ps.att_sid = na; g_ps.vic_sid = nv; g_ps.speed = spd;
    g_ps.att_dur = da / spd; g_ps.vic_dur = dv / spd;
    psync_bfs();                                          // the new clips' authored offsets (the ap is the same wall frame)
    double t = now - g_ps.t0;
    if (t < 0.0) t = 0.0;
    float ph_a = (float)(t / 1000.0 / g_ps.att_dur), ph_v = (float)(t / 1000.0 / g_ps.vic_dur);
    if (ph_a > 0.95f) ph_a = 0.95f;
    if (ph_v > 0.95f) ph_v = 0.95f;
    float save_bl = g_ps_blend;
    g_ps_blend = was_cut ? 0.5f : 0.35f;                  // from the previous segment's pose: an authored hand-over (intro -> main) is seamless, a cut push is 0.16-0.44 m off (0.25 s read as a teleport)
    g_ps.r_att = psync_animate(g_ps.ent_att, na, &g_ps.bf_att, ph_a, sptl_bl >= 0.0f ? sptl_bl : -1.0f);
    if (!(g_ps.vic_early && i == 1)) g_ps.r_vic = psync_animate(g_ps.ent_vic, nv, &g_ps.bf_vic, ph_v, -1.0f);
    g_ps_blend = save_bl;
    g_ps.rate[0] = g_ps.rate[1] = 0.0f;
    if (spd > 1.001f) {
        for (int k = 0; k < 2; k++) {
            uint64_t ent = k ? g_ps.ent_vic : g_ps.ent_att, sid = k ? nv : na;
            uint64_t b[4] = {ent, 0, ANIM_LAYER, sid};
            memcpy(&b[1], &spd, 4);
            mo_rate_dc(b, MO_SRC("paired.seg_speed"));
            g_ps.rate[k] = spd;
        }
    }
    g_ps.lost[0] = g_ps.lost[1] = 0; g_ps.out_done[0] = g_ps.out_done[1] = 0;
    g_ps.root_bucket = -1;
    for (int k = 0; k < 2; k++) {                         // the puppet drive blends from where each body is now
        float b[16];
        const float *l = psync_loc(k ? g_ps.ent_vic : g_ps.ent_att, b);
        g_ps.start_ok[k] = l && ps_loc_ok(l);
        if (g_ps.start_ok[k]) memcpy(g_ps.start_loc[k], l, sizeof g_ps.start_loc[k]);
        g_ps.half_yaw_ok[k] = 0; g_ps.place_ok[k] = 0;
    }
    g_ps.play_ms = now;
    g_ps.drive_bl = g_ps.seg_drive_bl > 0.0f ? g_ps.seg_drive_bl : g_ps_blend; g_ps.drive_easeout = 0;   // a segment switch keeps the distance-based drive blend (as before SP's start pull)
    xlog("psync: u%08x CHAIN segment %d/%d at %.0f ms: %s on the attacker, %s on the victim, x%.2f (%.2f / %.2f s real), phase %.2f", g_ps.uid, i + 1, g_ps.nseg,
         g_ps.chain_shift, psync_name(na), psync_name(nv), spd, g_ps.att_dur, g_ps.vic_dur, ph_a);
}
// ---- the revive chain (kind PS_REVIVE, revive2013.c): switch both halves to segment i at the move time new_t0 (the loop's restart keeps the clock exact:
// t0 + the segment length; the finish starts NOW on every client - the revive's MSG_REVIVE arrives everywhere within the one-way latency)
static void psync_rv_switch(int i, double new_t0, float blend, const char *why, float spd) {
    double now = psync_ms();
    if (!(spd > 1.001f)) spd = 1.0f;                     // (the kneel help-up's PULL runs faster so she stands as the bar fills: rvnr_chain)
    float old_pa = g_ps.ent_att ? psync_phase(g_ps.ent_att, g_ps.att_sid) : -1.0f, old_pv = g_ps.ent_vic ? psync_phase(g_ps.ent_vic, g_ps.vic_sid) : -1.0f;   // the layers we leave (-1 = already gone: the base pose showed)
    uint64_t na = g_ps.seg_att[i], nv = g_ps.seg_vic[i];
    float da = psync_dur(g_ps.ent_att, na), dv = psync_dur(g_ps.ent_vic, nv);
    if (da <= 0.0f || dv <= 0.0f) {
        xlog("psync: u%08x revive segment %d (%s): clip not loaded (%s %.2f s, %s %.2f s) - stays on the current one", g_ps.uid, i, why, psync_name(na), da, psync_name(nv), dv);
        if (i == 2) g_ps.rv_fin = 0;                    // (no finish clips: the move runs on, the owner's hand-off ends it)
        // (the seam hold froze both halves for this switch - no switch, so they play on instead of standing frozen to the hand-off)
        for (int k = 0; k < 2; k++) {
            uint64_t ent = k ? g_ps.ent_vic : g_ps.ent_att, sid = k ? g_ps.vic_sid : g_ps.att_sid;
            if (!ent || !(g_ps.rate[k] == 0.0f && g_ps.out_done[k])) continue;
            float one = 1.0f; uint64_t b[4] = {ent, 0, ANIM_LAYER, sid}; memcpy(&b[1], &one, 4);
            mo_rate_dc(b, MO_SRC("paired.rv_switch"));
            g_ps.rate[k] = 1.0f; g_ps.out_done[k] = 0;
        }
        return;
    }
    g_ps.chain_shift += new_t0 - g_ps.t0;
    g_ps.t0 = new_t0;
    g_ps.cur_seg = i; g_ps.rv_loops++;
    g_ps.att_sid = na; g_ps.vic_sid = nv; g_ps.speed = spd;
    g_ps.att_dur = da / spd; g_ps.vic_dur = dv / spd;
    if (i == 2) g_ps.dur_s = (da > dv ? da : dv) / spd;  // the move ends with its longer half
    psync_bfs();
    double t = now - g_ps.t0;
    if (t < 0.0) t = 0.0;
    float ph_a = (float)(t / 1000.0 / g_ps.att_dur), ph_v = (float)(t / 1000.0 / g_ps.vic_dur);
    if (ph_a > 0.95f) ph_a = 0.95f;
    if (ph_v > 0.95f) ph_v = 0.95f;
    float save_bl = g_ps_blend;
    g_ps_blend = blend;
    g_ps.r_att = psync_animate(g_ps.ent_att, na, &g_ps.bf_att, ph_a, -1.0f);
    g_ps.r_vic = psync_animate(g_ps.ent_vic, nv, &g_ps.bf_vic, ph_v, -1.0f);
    g_ps_blend = save_bl;
    g_ps.rate[0] = g_ps.rate[1] = 0.0f;
    if (spd > 1.001f) {                                   // both layers at the segment's speed from its first frame (as psync_seg_next)
        for (int k = 0; k < 2; k++) {
            uint64_t ent = k ? g_ps.ent_vic : g_ps.ent_att, sid = k ? nv : na;
            if (!ent) continue;
            uint64_t b[4] = {ent, 0, ANIM_LAYER, sid};
            memcpy(&b[1], &spd, 4);
            mo_rate_dc(b, MO_SRC("paired.rv_speed"));
            g_ps.rate[k] = spd;
        }
    }
    g_ps.lost[0] = g_ps.lost[1] = 0; g_ps.out_done[0] = g_ps.out_done[1] = 0;
    g_ps.root_bucket = -1;
    for (int k = 0; k < 2; k++) {                         // the puppet drive blends from where each body is now
        float b[16];
        const float *l = psync_loc(k ? g_ps.ent_vic : g_ps.ent_att, b);
        g_ps.start_ok[k] = l && ps_loc_ok(l);
        if (g_ps.start_ok[k]) memcpy(g_ps.start_loc[k], l, sizeof g_ps.start_loc[k]);
        g_ps.half_yaw_ok[k] = 0; g_ps.place_ok[k] = 0;
    }
    g_ps.play_ms = now;
    g_ps.drive_bl = blend; g_ps.drive_easeout = 0;
    xlog("psync: u%08x REVIVE segment %d/%d (%s) at %.0f ms: %s on the reviver, %s on the revived (%.2f / %.2f s real, x%.2f), phase %.2f, blend %.2f s; old layers read %.3f / %.3f before the switch",
         g_ps.uid, i + 1, g_ps.nseg, why,
         g_ps.chain_shift, psync_name(na), psync_name(nv), g_ps.att_dur, g_ps.vic_dur, spd, ph_a, blend, old_pa, old_pv);
}
// Reviving reset the pose in the middle: the revive has two seams inside the move, ENTER -> LOOP at 1.47 s and (a long hold) the LOOP
// restart, and both switch with animate_ at the first tick whose move clock passed the segment length. A non-looping carrier layer is removed by the engine the frame
// its clip time passes the clip's end (the FINISH tail of the revived's puppet fell to the base pose that way, 02c40043), and the engine's clip clock and our wall
// clock are not the same clock (frame quantisation, a playback-rate nudge of psync_rate, a skipped receiver start): when the layer ended in the frame BEFORE our tick,
// that frame showed the base pose (the bodies stand up for a frame) and animate_'s blend-in then faded in from the base pose instead of from the kneeling pose
// (a 0.35 s sink and rise). visdiag's pose-pop check is blind to this on purpose (vd_reviving: the get-up is the move's end). Same cure as the lethal victim's
// end hold (psync_vic_end_hold): RV_SEAM_FREEZE_MS before the boundary both layers are frozen on their last pose (set-animation-speed 0), so no layer can end
// before the switch and the blend starts from the real pose. The switch itself (a new animate_ on the layer) or the move's end replaces the frozen layer.
// t2r-no-revive-seam-hold.txt next to the exe = off. Log lines "revive seam:".
#define RV_SEAM_FREEZE_MS 90.0
static int rv_seam_hold_off(void) {
    static int off = -1;
    if (off < 0) { FILE *f = exe_side_open("t2r-no-revive-seam-hold.txt", "r"); off = f != NULL; if (f) fclose(f); if (off) xlog("revive seam: layer hold off (t2r-no-revive-seam-hold.txt)"); }
    return off;
}
static void psync_rv_seam_hold(double t, double len) {
    static uint32_t held_key;
    uint32_t key = g_ps.uid * 8u + (uint32_t)g_ps.cur_seg + (uint32_t)g_ps.rv_loops * 0x9e3779b1u;
    if (held_key == key || len - t > RV_SEAM_FREEZE_MS || rv_seam_hold_off()) return;
    held_key = key;
    float zero = 0.0f, ph[2];
    for (int k = 0; k < 2; k++) {
        uint64_t ent = k ? g_ps.ent_vic : g_ps.ent_att, sid = k ? g_ps.vic_sid : g_ps.att_sid;
        ph[k] = ent ? psync_phase(ent, sid) : -1.0f;
        if (!ent || ph[k] < 0.5f) continue;                   // (no layer / already wrapped: nothing to hold)
        uint64_t b[4] = {ent, 0, ANIM_LAYER, sid};
        memcpy(&b[1], &zero, 4);
        mo_rate_dc(b, MO_SRC("paired.rv_seam_hold"));
        g_ps.rate[k] = 0.0f; g_ps.out_done[k] = 1;            // psync_rate must not wind it up again
    }
    xlog("revive seam: u%08x segment %d/%d holds both halves on their last pose %.0f ms before the switch (t=%.0f of %.0f ms, layer phase reviver %.3f revived %.3f, role %d)",
         g_ps.uid, g_ps.cur_seg + 1, g_ps.nseg, len - t, t, len, ph[0], ph[1], g_ps.role);
}
static void psync_rv_chain(double now) {
    if (g_ps.nseg < 3 || rvnr_chain(now)) return;       // (the kneel help-up's own rules: revive2013.c)
    if (g_ps.cur_seg >= 2) return;
    double len = psync_seg_len_ms();
    // co-revive (several revivers finish a hold in ~2.5 s, a Reviver-skill pair in ~1.3 s): the FINISH never cuts the 1.47 s ENTER short - a completion
    // that arrives during ENTER waits for its end and then switches ENTER -> FINISH directly (no one-frame LOOP). The revive itself is booked at once (hp, stand).
    if (g_ps.rv_fin && g_ps.cur_seg == 0 && now - g_ps.t0 < len) { psync_rv_seam_hold(now - g_ps.t0, len); return; }
    if (g_ps.rv_fin) { psync_rv_switch(2, g_ps.cur_seg == 0 ? g_ps.t0 + len : now, 0.30f, "revive complete", 1.0f); return; }
    psync_rv_seam_hold(now - g_ps.t0, len);
    if (now - g_ps.t0 < len) return;
    if (g_ps.cur_seg == 0) psync_rv_switch(1, g_ps.t0 + len, 0.35f, "enter over", 1.0f);
    else if (rv_loop_tail()) psync_rv_switch(2, now, 0.30f, "loop over, revive completing", 1.0f);   // (not a second give: see rv_loop_tail)
    else psync_rv_switch(1, g_ps.t0 + len, 0.12f, "loop restart", 1.0f);   // the loop clips are seamless: the same pair again, a short cross-fade
}
// ---- the BODYSHIELD chain (kind PS_BODYSHIELD, bodyshield.c): ENTER -> HOLD, the HOLD restarted at its end (the struggle loops are s, a grab
// rarely outlasts one), and two run-time switches every client makes on the same MSG_BS message: the HOLD pair swapped (plain <-> aim shield) and the
// END pair (escape / finisher / shield death) written into segment 2 and switched to at once. Reuses the revive's switch + seam hold (same clock rules).
static int g_bs_hold_swap;                  // bodyshield.c: segment 1 was replaced (aim shield on): switch to it now if the HOLD already plays
static int g_bs_end_swap;                   // bodyshield.c: segment 2 was replaced while it plays (a finisher broken by damage -> its abort pair, a late death)
static void psync_bs_chain(double now) {
    if (g_ps.nseg < 3) return;
    if (g_ps.rv_fin && g_ps.cur_seg < 2) { g_bs_end_swap = 0; psync_rv_switch(2, now, 0.25f, "bodyshield end", 1.0f); return; }
    if (g_ps.cur_seg >= 2) { if (g_bs_end_swap) { g_bs_end_swap = 0; psync_rv_switch(2, now, 0.20f, "bodyshield end swap", 1.0f); } return; }
    double len = psync_seg_len_ms();
    if (g_bs_hold_swap && g_ps.cur_seg == 1) { g_bs_hold_swap = 0; psync_rv_switch(1, now, 0.25f, "bodyshield hold swap", 1.0f); return; }
    psync_rv_seam_hold(now - g_ps.t0, len);
    if (now - g_ps.t0 < len) return;
    if (g_ps.cur_seg == 0) { g_bs_hold_swap = 0; psync_rv_switch(1, g_ps.t0 + len, 0.30f, "bodyshield enter over", 1.0f); }
    else psync_rv_switch(1, g_ps.t0 + len, 0.15f, "bodyshield hold restart", 1.0f);
}
// Special executions always show the guns they use, to avoid anims where the executioner seems to hold nothing. Every frame of a gun / armed-melee execution the executioner's weapon (our body: the item controller's held weapon; a
// puppet on the victim's / a bystander's screen: the NPC's current weapon) gets its draw-control visibility byte (+0x1b0 -> +0x48, the byte the
// spawn fix found: 0x00 = the process is attached but not drawn) forced to 0xff. The holster gates (hfix, t2r-ext.c) keep our own body's
// gun in the hand; a puppet's carrier clip is an NPC clip whose holster actions the gates do not cover (hfix_mine = the local player's), so the
// puppet's held weapon is checked too and every state change is logged ("gun keeper:") - a weapon that is gone from the hand is named, not
// papered over. t2r-no-gun-keeper.txt next to the exe = off.
// (the revolver stayed in the wrong hand mid execution; we were the victim, attacker = slot 1's puppet, execution-revolver-left): the gun pairs
// are baked with the gun in the RIGHT hand (the 2013 gun joint sits 4.6 cm from the right palm for the whole clip, bake_t1 find_grip -> r_hand_prop), and our own body
// is made to hold it there (xr_begin: a reload ends first, instant draw into the right hand). A puppet attacker's pistol / 9mm / revolver is not: when the shooter's
// revolver was in its LEFT hand (TLOU2's reload / cylinder hold attaches it to leftHand by an anim event; the carrier clip of the pair does not re-attach) the gun stays on
// leftHand while the baked right hand mimes the grip. Before the fix nothing logged the puppet's attach point. Every frame of a pistol-class gun execution the puppet's
// weapon attach point is read; on leftHand it is attached to rightHand again (script attach, as the shiv prop) - at most 3 times a move, then one line, never fought.
// Long guns / bow / shotgun keep their own point (TLOU2 holds them on leftHand). "gun keeper: ... attach point" lines. t2r-no-gun-hand-fix.txt = off.
static int g_gk_hand_off;
static void gk_puppet_hand(uint8_t *w, uint64_t chr) {
    static int init, tries; static uint32_t uid; static int logged;
    if (!init) { init = 1; FILE *f = exe_side_open("t2r-no-gun-hand-fix.txt", "r"); g_gk_hand_off = f != NULL; if (f) fclose(f); if (g_gk_hand_off) return; }
    if (uid != g_ps.uid) { uid = g_ps.uid; tries = 0; logged = 0; }
    if (g_ps.pair < 0 || (unsigned)g_ps.pair >= GX_N || !chr) return;
    int cls = GUNEXEC_PAIRS[g_ps.pair].cls;
    if (cls != GX_PISTOL && cls != GX_9MM && cls != GX_REVOLVER) return;
    uint64_t sid = xr_wpn_ap(w);
    if (!sid) return;
    if (!logged) { logged = 1; xlog("gun keeper: attacker puppet weapon %016llx attach point %016llx %s at the start of %s", (unsigned long long)pst_sid_of(w), (unsigned long long)sid, bp_ap_name(sid), GUNEXEC_PAIRS[g_ps.pair].name); }
    if (sid != fnv64("leftHand") || tries >= 3 || IsBadReadPtr(w + 0xc0, 8)) return;
    tries++;
    uint64_t at[4] = {*(uint64_t *)(w + 0xc0), chr, fnv64("rightHand"), 0};
    uint64_t r = dc_call(fnv64("attach"), 4, at);
    uint64_t sid2 = xr_wpn_ap(w);
    xlog("gun keeper: attacker puppet weapon %016llx was on %s in the %s execution - attached to rightHand (try %d, attach -> %llx, now %s)", (unsigned long long)pst_sid_of(w),
         bp_ap_name(sid), GUNEXEC_PAIRS[g_ps.pair].name, tries, (unsigned long long)r, bp_ap_name(sid2));
}
static void psync_gun_keep(void) {
    static int off = -1;
    if (off < 0) { FILE *f = exe_side_open("t2r-no-gun-keeper.txt", "r"); off = f != NULL; if (f) fclose(f); }
    static uint32_t last_uid; static int st_own = -2, st_pup = -2, shown_own, shown_pup; static uint64_t t_start;
    if (off || !g_ps.role || (g_ps.kind != PS_GUN_EXEC && g_ps.kind != PS_MELEE_EXEC)) { last_uid = 0; return; }
    int gun = g_ps.kind == PS_GUN_EXEC;
    if (g_ps.uid != last_uid) { last_uid = g_ps.uid; st_own = st_pup = -2; shown_own = shown_pup = 0; t_start = g_frame; }
    for (int who = 0; who < 2; who++) {
        uint8_t *w = NULL; const char *nm;
        if (!who) {                                                  // our body = the executioner
            if (g_ps.role != 1 || g_ps.ent_att != SID_PLAYER) continue;
            if (g_unarm_exec || g_cd_hands_on || (!gun && (g_gx.melee && (g_gx.unarm || g_gx.shiv)))) continue;      // fists / shiv: empty hands stay
            w = player_weapon(((uint8_t *(*)(void))VMA(0x180050390))());
            nm = "our body";
        } else {                                                     // the executioner's puppet here
            if (g_ps.ent_att == SID_PLAYER) continue;
            if (!gun && (g_ps.role != 2 || g_gx.melee == 0 || g_gx.unarm || g_gx.shiv)) continue;               // a bystander's melee: g_gx is not its (fists / shiv unknown)
            uint8_t *npc = pst_npc(g_ps.ent_att);
            if (!npc) continue;
            w = pst_current(npc);
            nm = "attacker puppet";
        }
        int *st = who ? &st_pup : &st_own;
        if (who && gun && w && !g_gk_hand_off) gk_puppet_hand(w, g_ps.ent_att);
        int have = w && !IsBadReadPtr(w + 0x1b0, 8);
        if (have != *st) {
            *st = have;
            xlog("gun keeper: %s - %s weapon %016llx (process %p) at frame +%llu", gun ? "gun execution" : "melee execution", nm,
                 (unsigned long long)pst_sid_of(w), (void *)w, (unsigned long long)(g_frame - t_start));
        }
        if (!have) continue;
        uint8_t *dc = *(uint8_t **)(w + 0x1b0);
        if (dc && !IsBadWritePtr(dc + 0x48, 4) && dc[0x48] != 0xff) {
            dc[0x48] = 0xff;
            if ((who ? shown_pup++ : shown_own++) < 6)
                xlog("gun keeper: %s weapon %016llx was hidden (draw-control %p byte +0x48 -> 0xff) at frame +%llu", nm, (unsigned long long)pst_sid_of(w), (void *)dc, (unsigned long long)(g_frame - t_start));
        }
    }
}
// ---- paired-move flicker diagnostic (characters flickered in all special executions). Per frame, per half body: its root against the clip's
// placement delta (a body that steps more / less than its clip, after the blend-in), the clip time going backwards, the animation id changing mid-move,
// with the last forced anim starts / stops on that body. Lines "psync flicker:" (<= 40 per move segment, 600 per session).
static struct { float pp[2][8], lp[2][8], ph[2]; int ok[2]; uint64_t sid[2]; uint32_t key; unsigned n; } g_pf;
static unsigned g_pf_total;
static void psync_flicker_check(double t, const float *ph) {
    uint32_t key = g_ps.uid * 8u + (uint32_t)g_ps.cur_seg + (uint32_t)g_ps.rv_loops * 0x9e3779b1u;
    if (g_pf.key != key || !g_pf.key) { memset(&g_pf, 0, sizeof g_pf); g_pf.key = key; }
    double now = psync_ms();
    int blend = now - g_ps.play_ms < g_ps_blend * 1000.0 + 150.0;
    for (int k = 0; k < 2; k++) {
        uint64_t ent = k ? g_ps.ent_vic : g_ps.ent_att, sid = k ? g_ps.vic_sid : g_ps.att_sid;
        if (!ent) continue;
        float lb[16]; const float *l = psync_loc(ent, lb);
        int lok = l && ps_loc_ok(l), pok = g_ps.place_ok[k];
        char why[200]; int w = 0; why[0] = 0;
        float act = 0, ex = 0;
        if (g_pf.ok[k] && lok && pok && g_ps.tick_dt < 60.0f) {
            float ax = l[0] - g_pf.lp[k][0], ay = l[1] - g_pf.lp[k][1], az = l[2] - g_pf.lp[k][2];
            float ex_ = g_ps.place[k][0] - g_pf.pp[k][0], ey = g_ps.place[k][1] - g_pf.pp[k][1], ez = g_ps.place[k][2] - g_pf.pp[k][2];
            act = __builtin_sqrtf(ax * ax + ay * ay + az * az); ex = __builtin_sqrtf(ex_ * ex_ + ey * ey + ez * ez);
            if (!blend && __builtin_fabsf(act - ex) > 0.05f) w += snprintf(why + w, SNLEFT(why, w), " root stepped %.3f m, its clip %.3f m;", act, ex);
        }
        if (g_pf.ok[k] && ph[k] >= 0.0f && g_pf.ph[k] > 0.05f && ph[k] < g_pf.ph[k] - 0.003f && t > 200.0) w += snprintf(why + w, SNLEFT(why, w), " clip time back %.3f -> %.3f;", g_pf.ph[k], ph[k]);
        if (g_pf.sid[k] && g_pf.sid[k] != sid) w += snprintf(why + w, SNLEFT(why, w), " animation changed %s -> %s;", psync_name(g_pf.sid[k]), psync_name(sid));
        if (w && g_pf.n < 40 && g_pf_total < 600) {
            char hint[200]; fa_hint(ent, hint, sizeof hint);
            g_pf.n++; g_pf_total++;
            xlog("psync flicker: u%08x role %d body %s (%s, clip %s) t=%.0f ms frame %llu ph %.3f%s | last anims on it: %s | driven %d, own_drv %d, blend-in %d, dt %.0f ms",
                 g_ps.uid, g_ps.role, k ? "vic" : "att", ent == SID_PLAYER ? "our body" : "puppet", psync_name(sid), t, (unsigned long long)g_frame, ph[k], why, hint,
                 ent == SID_PLAYER ? g_ps.own_drv : (k == 0 ? g_ps.att : g_ps.vic) >= 0 && (k == 0 ? g_ps.att : g_ps.vic) < T2R_MAX_PEERS ? (int)g_ps_pup[k == 0 ? g_ps.att : g_ps.vic].drv : 0,
                 g_ps.own_drv, blend, (double)g_ps.tick_dt);
        }
        if (lok) memcpy(g_pf.lp[k], l, 32);
        if (pok) memcpy(g_pf.pp[k], g_ps.place[k], 32);
        g_pf.ok[k] = lok && pok; g_pf.ph[k] = ph[k]; g_pf.sid[k] = sid;
    }
}
// "psync place:" every 250 ms of a move, per puppet half: the puppet's real world position, where its clip puts it, what we last wrote, and who moved it
// since (the shiv attacker was somewhere else on the victim's screen, 39 frames after a ctxdown release of the same puppet). All world metres.
static void psync_place_log(double t, const float *ph) {
    int bucket = (int)(t / 250.0);
    if (bucket == g_ps.place_bucket) return;
    g_ps.place_bucket = bucket;
    for (int k = 0; k < 2; k++) {
        uint64_t ent = k ? g_ps.ent_vic : g_ps.ent_att;
        int slot = k ? g_ps.vic : g_ps.att;
        if (!ent || ent == SID_PLAYER || slot < 0 || slot > T2R_MAX_PEERS - 1) continue;
        float b[16], ia[4];
        const float *l = psync_loc(ent, b);
        if (!l) { xlog("psync place: u%08x r%d t=%.0f %s slot %d - no locator", g_ps.uid, g_ps.role, t, k ? "vic" : "att", slot); continue; }
        psync_in_ap(l, ia);
        int nv = -1, nm = -1, b48 = -1;      // drawn? draw control (proc+0x1b0): visibility byte +0x48 (0 = attached but not drawn), visible / total meshes
        {
            uint8_t *pr = ((uint8_t *(*)(uint64_t))VMA(0x18000A200))(ent);
            uint8_t *dc = pr && !IsBadReadPtr(pr, 0x1b8) ? *(uint8_t **)(pr + 0x1b0) : NULL;
            if (dc && !IsBadReadPtr(dc, 0x50)) { b48 = dc[0x48]; nm = coat_mesh_state(dc, 0, &nv); }
        }
        const float *e = g_ps.place[k];
        float ex = g_ps.place_ok[k] ? l[0] - e[0] : 0, ey = g_ps.place_ok[k] ? l[1] - e[1] : 0, ez = g_ps.place_ok[k] ? l[2] - e[2] : 0;
        float px = g_ps.put_ok[k] ? l[0] - g_ps.put[k][0] : 0, py = g_ps.put_ok[k] ? l[1] - g_ps.put[k][1] : 0, pz = g_ps.put_ok[k] ? l[2] - g_ps.put[k][2] : 0;
        xlog("psync place: u%08x r%d t=%.0f %s slot %d puppet %llx %s | world %.2f %.2f %.2f (ap-space %.2f %.2f yaw %.0f) | clip %.2f %.2f %.2f err %.2f m | we put %.2f %.2f %.2f, off it by %.2f m "
             "(moved by another writer if > 0.05) | phase %.3f, drive %ld, hand-back %s | drawn: dc+48 %02x, meshes %d/%d visible",
             g_ps.uid, g_ps.role, t, k ? "vic" : "att", slot, (unsigned long long)ent, g_ps_pup[slot].on ? "SUSPENDED" : "NET", l[0], l[1], l[2], ia[0], ia[1], ia[3],
             g_ps.place_ok[k] ? e[0] : 0.0f, g_ps.place_ok[k] ? e[1] : 0.0f, g_ps.place_ok[k] ? e[2] : 0.0f,
             __builtin_sqrtf(ex * ex + ey * ey + ez * ez), g_ps.put_ok[k] ? g_ps.put[k][0] : 0.0f, g_ps.put_ok[k] ? g_ps.put[k][1] : 0.0f,
             g_ps.put_ok[k] ? g_ps.put[k][2] : 0.0f, __builtin_sqrtf(px * px + py * py + pz * pz), ph[k], (long)g_ps_pup[slot].drv, g_ps_hb[slot].h ? "RUNNING" : "-", b48 & 0xff, nv, nm);
    }
}
#ifndef T2R_RELEASE
// a collapsed attacker start has the puppet's base layer (81b46a69304ee2c9, holding its base clip) EMPTY before psync
// takes it - something empties it earlier. Dev builds watch that layer on every puppet each frame and log each change of its instance
// count with the frame's context (forced clips on that body, psync / downed state), to name what empties it.
static void psync_base_watch(void) {
    static int last[T2R_MAX_PEERS] = {-1, -1, -1, -1, -1, -1, -1, -1};
    static uint64_t lasth[T2R_MAX_PEERS];
    static int nl;
    for (int s = 0; s < T2R_MAX_PEERS; s++) {
        uint64_t h = psync_puppet(s);
        if (!h || h == ~0ULL) { last[s] = -1; continue; }
        if (h != lasth[s]) { lasth[s] = h; last[s] = -1; }
        typedef uint8_t *(*fn_proc)(uint64_t);
        uint8_t *proc = ((fn_proc)VMA(0x18000A200))(h);
        if (!proc) continue;
        vdf_lay cur[48];
        int n = vdf_layers(proc, cur, 48), cnt = -2;
        for (int i = 0; i < n; i++) if (cur[i].name == 0x81b46a69304ee2c9ULL) { cnt = cur[i].n; break; }
        if (cnt == last[s]) continue;
        if (last[s] != -1 && LOGCAP(nl, 400)) {
            char hint[300] = "";
            fa_hint(h, hint, sizeof hint);
            xlog("base watch: slot %d puppet %llx base layer instances %d -> %d (frame %llu) | psync busy %d, downed %d, uc4 %d | %s", s, (unsigned long long)h,
                 last[s], cnt, (unsigned long long)g_frame, psync_busy_slot(s), g_peer_downed[s], g_uc4_pup[s].cur != NULL, hint);
        }
        last[s] = cnt;
    }
}
#endif
// POWER RAGDOLL: the executed body must play its clip fully and go ragdoll only when it touches something, keeping its movement.
// The engine has exactly that: the powered / keyframed ragdoll (Character composite ragdoll at [char+0x898],
// DC settings *default-ragdoll-keyframe-control-settings* / the dying settings, debug option "Ragdoll keyframed till the first collision"). ND's clips switch it on
// with their anim events power-ragdoll-on / power-ragdoll-off, and the player's Death update does it after the death animation's delay when [player+0x9fd] bit 0 is
// set. Our baked 2013 victim clips carry no such event, the death animation / controller actions are withheld (vdf hooks), and psync placed the root on the clip
// every frame (set-object-locator), so the body never became a physical ragdoll before the end of the half. RE (tlou-ii.exe, static):
//   EnablePowerRagdoll = 0x141ceb020 (Character*, u8 dying_mode [dl], u64 settings_sid [r8; 0 = the default of vfunc +0xde8 when dying_mode], float blend [xmm3], u8 [rsp+0x20]).
//   Call sites: the anim-event handler 0x141ce7d6f (event power-ragdoll-on 0xe39a8b26...: dl 0, settings + blend from the event, last arg 1) and the player Death helpers
//   0x140b57ba0 / 0x140b57cf0 (dl 1, settings = the qword at 0x142CA6FD8 (set at run time), blend 0.2 s (0x142b04220), last arg 0). We call it the way the anim event does:
//   dying_mode 0, settings = that global, blend 0.2, last arg 1 (the clip keeps driving the motors). Composite state: [[char+0x898]+0x68].
// From the kill frame (the victim is dead / dying) on: power ragdoll on, psync stops placing the root (and re-disabling the collider), the half keeps playing as the motors'
// target; at the half's end the old limp (vdf_limp / exkill npc-die) runs. Dev builds: on; release: only with t2r-power-ragdoll.txt (a number > 1 in it = ms of lead before the
// kill; 0 = off). Log lines: "power ragdoll:".
static int psync_pr_cfg(int *lead) {
    static int on = -1, ld; static uint64_t at; uint64_t n = GetTickCount64();
    if (on < 0 || n - at > 2000) {
        at = n;
#ifdef T2R_RELEASE
        on = 0;
#else
        on = 1;
#endif
        ld = 0;
        FILE *f = exe_side_open("t2r-power-ragdoll.txt", "r");
        if (f) {
            int v = 1; char b[32] = {0};
            if (fgets(b, sizeof b, f) && sscanf(b, "%d", &v) != 1) v = 1;
            fclose(f);
            on = v != 0; ld = v > 1 ? v : 0;
        }
    }
    if (lead) *lead = ld;
    return on;
}
static uint8_t *psync_pr_char(void) {                    // the victim's Character object
    if (g_ps.ent_vic == SID_PLAYER) return vdf_player();
    return ((uint8_t *(*)(uint64_t))VMA(0x18000A200))(g_ps.ent_vic);
}
static void psync_pr_state_log(uint8_t *c, const char *tag) {
    uint8_t *comp = c && !IsBadReadPtr(c + 0x898, 8) ? *(uint8_t **)(c + 0x898) : NULL;
    int ctype = comp && !IsBadReadPtr(comp, 0x70) ? *(int32_t *)(comp + 0x68) : -1;
    int cfl = comp && !IsBadReadPtr(comp, 8) ? comp[2] : -1;
    float blend = c && !IsBadReadPtr(c + 0x998, 8) ? *(float *)(c + 0x998) : -9.0f;
    uint64_t setg = c && !IsBadReadPtr(c + 0x9a8, 8) ? *(uint64_t *)(c + 0x9a8) : 0;
    int bit = c && !IsBadReadPtr(c + 0x9fd, 1) ? (c[0x9fd] & 3) : -1;
    xlog("power ragdoll: %s u%08x %s - composite %p type %d flags %02x, settings %016llx blend %.2f, +0x9fd bits %d, dead %d", tag, g_ps.uid,
         g_ps.ent_vic == SID_PLAYER ? "our body" : "puppet", (void *)comp, ctype, cfl, (unsigned long long)setg, (double)blend, bit,
         g_ps.ent_vic == SID_PLAYER ? psync_own_dead_now() : psync_dead(g_ps.ent_vic));
}
static void psync_pr_tick(double t) {
    int lead = 0;
    if (!g_ps.role || !g_ps.ent_vic || !(g_ps.flags & PS_F_LETHAL) || g_ps.kind == PS_REVIVE || g_ps.kill_s <= 0 || g_vdf_limp_done) return;
    if (g_ps.pr_on) {
        if (++g_ps.pr_n % 10 == 0 && g_ps.pr_n <= 600) psync_pr_state_log(psync_pr_char(), "state");
        return;
    }
    if (g_ps.pr_tried || !psync_pr_cfg(&lead)) return;
    if (t < g_ps.kill_s * 1000.0 - (double)lead) return;
    if (g_ps.ent_vic == SID_PLAYER && !g_ps.vic_keep) return;                 // our own body: from the moment it is dead
    g_ps.pr_tried = 1;
    uint8_t *c = psync_pr_char();
    uint64_t base = (uint64_t)GetModuleHandleW(NULL) - 0x140000000ULL;
    uint64_t *gset = (uint64_t *)(base + 0x142CA6FD8ULL);
    if (!c || IsBadReadPtr(c + 0x9a8, 8) || IsBadReadPtr(gset, 8)) { xlog("power ragdoll: u%08x no victim character (%p) - not enabled", g_ps.uid, (void *)c); return; }
    uint64_t settings = *gset;
    if (!settings) settings = fnv64("*follow-anim-ragdoll-control-settings*");
    psync_pr_state_log(c, "before");
    typedef uint8_t (*fn_epr)(uint8_t *, uint8_t, uint64_t, float, uint8_t);
    uint8_t r = ((fn_epr)(base + 0x141ceb020ULL))(c, 0, settings, 0.2f, 1);
    g_ps.pr_on = r ? 1 : 0; g_ps.pr_n = 0;
    xlog("power ragdoll: u%08x EnablePowerRagdoll(char %p, dying 0, settings %016llx, blend 0.20, 1) at t=%.0f ms (kill %.2f s, lead %d) -> %d - %s", g_ps.uid, (void *)c,
         (unsigned long long)settings, t, (double)g_ps.kill_s, lead, (int)r,
         r ? "the engine's keyframed ragdoll follows the clip and goes physical on contact; psync no longer places the root" : "REFUSED (the root stays placed on the clip)");
    psync_pr_state_log(c, "after");
}
static void psync_tick(void) {
    vdf_noanim_tick();
    wallho_tick();
    pe45_tick();                    // ps45 item 1: the pin escape hold's fallbacks
#ifndef T2R_RELEASE
    psync_base_watch();
#endif
    dr_tick();                      // deathreact.c: directional death clip on our body / the puppets (every frame)
    psync_gun_keep();
    // ps42 J1 bisect switch (OPT-IN, not a fix: the cause of the floating victim body is not proven): t2r-pair-vic-legik-off.txt = the engine's per-frame
    // native player-disable-leg-ik on our own body while it plays a victim half. Compare the "own pose:" ankles of the victim root lines with and without.
    if (g_ps.role == 2 && g_ps.ent_vic == SID_PLAYER) {
        static uint64_t at; static int v = -1; static uint32_t luid; uint64_t n = GetTickCount64();
        if (v < 0 || n - at > 2000) { at = n; v = GetFileAttributesA("t2r-pair-vic-legik-off.txt") != INVALID_FILE_ATTRIBUTES; }
        if (v) {
            uint64_t none = 0, r = dc_call(fnv64("player-disable-leg-ik"), 0, &none);
            if (luid != g_ps.uid) { luid = g_ps.uid; xlog("psync: u%08x own victim body: player-disable-leg-ik every frame of the half -> %llx (t2r-pair-vic-legik-off.txt, ps42 bisect)", g_ps.uid, (unsigned long long)r); }
        }
    }
    static double next_ping, next_cfg;
    double now = psync_ms();
    if (now >= next_cfg) {          // switches, re-read every 2 s
        next_cfg = now + 2000.0;
        FILE *f = exe_side_open("t2r-psync-log.txt", "r");       // log every N frames (default 1)
        int n = 1;
        if (f) { if (fscanf(f, "%d", &n) != 1) n = 1; fclose(f); }
        g_ps_log_every = n > 0 && n < 600 ? n : 1;
        f = exe_side_open("t2r-psync-no-suspend.txt", "r");      // diagnostic: puppets keep their net channels
        int ns = f != NULL;
        if (f) fclose(f);
        if (ns != g_ps_no_suspend) xlog("psync: puppet channel suspension %s (t2r-psync-no-suspend.txt)", ns ? "OFF - diagnostic only" : "on");
        g_ps_no_suspend = ns;
        f = exe_side_open("t2r-no-kick-fix.txt", "r");           // off: a finished half goes back to the clip's start placement (old)
        int kf = f == NULL;
        if (f) fclose(f);
        if (kf != g_ps_kickfix) xlog("psync: kick fix (finished half held on its last placement) %s (t2r-no-kick-fix.txt)", kf ? "on" : "OFF");
        g_ps_kickfix = kf;
        f = exe_side_open("t2r-psync-no-smooth.txt", "r");      // off: the end / correction smoothing (PS_OUT, hand-back, jump decay, rate)
        int sm = f == NULL;
        if (f) fclose(f);
        if (sm != g_ps_smooth) xlog("psync: smoothing (attacker half blend-out, net hand-back, placement jump decay, drift by rate) %s (t2r-psync-no-smooth.txt)", sm ? "on" : "OFF");
        g_ps_smooth = sm;
        f = exe_side_open("t2r-no-vic-deathanim-fix.txt", "r");   // opt-out: the victim's own TLOU2 death animation as before
        int nv = f != NULL;
        if (f) fclose(f);
        if (nv != g_vdf_off) xlog("psync: own victim death-anim fix %s (t2r-no-vic-deathanim-fix.txt)", nv ? "OFF" : "on");
        g_vdf_off = nv;
        f = exe_side_open("t2r-no-gx-nowall.txt", "r");        // opt-out: wall guard on the gun-execution victim puppet
        int gw = f == NULL;
        if (f) fclose(f);
        if (gw != g_ps_gx_nowall) xlog("gx place: victim puppet of a gun execution unguarded %s (t2r-no-gx-nowall.txt)", gw ? "on" : "OFF");
        g_ps_gx_nowall = gw;
        f = exe_side_open("t2r-no-vic-root-drive.txt", "r");      // opt-out: our dead victim body is not placed on its half by psync
        int vd = f == NULL;
        if (f) fclose(f);
        if (vd != g_ps_vic_drive) xlog("victim root: own dead victim body on its clip %s (t2r-no-vic-root-drive.txt)", vd ? "on" : "OFF");
        g_ps_vic_drive = vd;
        f = exe_side_open("t2r-no-corpse-hold.txt", "r");        // opt-out: a dead victim puppet is handed back to the network at the end
        int nc = f != NULL;
        if (f) fclose(f);
        if (nc != g_ps_no_corpse) xlog("psync: corpse hold of a dead victim puppet %s (t2r-no-corpse-hold.txt)", nc ? "OFF" : "on");
        g_ps_no_corpse = nc;
        f = exe_side_open("t2r-no-att-out-drive.txt", "r");       // opt-out: our attacker body is not placed on its clip through the blend-out
        int ao = f == NULL;
        if (f) fclose(f);
        if (ao != g_ps_att_out_drive) xlog("psync: own attacker body placed through its blend-out %s (t2r-no-att-out-drive.txt)", ao ? "on" : "OFF");
        g_ps_att_out_drive = ao;
        f = exe_side_open("t2r-no-psync-ground.txt", "r");        // opt-out: puppet halves are not re-grounded on slopes
        int gr = f == NULL;
        if (f) fclose(f);
        if (gr != g_ps_ground) xlog("psync: puppet halves grounded on slopes %s (t2r-no-psync-ground.txt)", gr ? "on" : "OFF");
        g_ps_ground = gr;
    }
    if (match_substate() == 6 && now >= next_ping && g_send_tramp) {     // RTT to every peer
        next_ping = now + PS_PING_MS;
        uint8_t m[10]; m[0] = PS_OP_PING; memcpy(m + 1, &now, 8); m[9] = 1;
        g_send_tramp(MSG_PSYNC, m, sizeof m, 0xff);
    }
    for (int s = 0; s < T2R_MAX_PEERS; s++)       // a hand-back that never got a net locator call (gate closed by winmm's own melee, puppet gone)
        if (g_ps_hb[s].h && now - g_ps_hb[s].armed > 1500.0) psync_hb_end(s, "expired");
    psync_corpse_tick(now);
    psync_abq_tick(now);
    if (!g_ps.role) return;
    if (match_substate() != 6) { psync_finish("match over", 0); return; }
    double t = now - g_ps.t0;
    if (g_ps.kind == PS_MELEE_EXEC) { iw_tick(now); t = now - g_ps.t0; }
    if (g_ps.kind == PS_REVIVE) { psync_rv_chain(now); t = now - g_ps.t0; }
    if (g_ps.kind == PS_BODYSHIELD) { psync_bs_chain(now); t = now - g_ps.t0; }
    // the victim stays in its previous animation for a bit (the whiff continues) and blends to the punch on it / slightly before:
    // the deferred victim half starts PS_VIC_EARLY_MS before the contact (its first frame = the contact pose) with a 0.3 s blend; the chain switch keeps it
    if (g_ps.vdefer && !g_ps.vic_early && g_ps.cur_seg == 0 && g_ps.nseg > 1 && t >= psync_seg_len_ms() - PS_VIC_EARLY_MS) {
        uint64_t nv = g_ps.seg_vic[1];
        uint64_t r = psync_animate(g_ps.ent_vic, nv, &g_ps.bf_vic, 0.0f, 0.3f);
        // (haymaker victim just stood there: vlag_hold stayed on for these 120 ms and its per-frame re-pin set the new layer's
        // phase 0 / speed 0 - the half sat frozen on its first frame, then the layer was lost. The early start IS the release.)
        if (r && r != ~0ULL) { g_ps.vic_early = 1; g_ps.vic_early_t = t; g_ps.r_vic = r; g_ps.vlag_hold = 0; }
        xlog("psync: u%08x victim half %s started %.0f ms before the contact (0.3 s blend from the whiff) -> %llx", g_ps.uid, psync_name(nv), psync_seg_len_ms() - t, (unsigned long long)r);
    }
    while (g_ps.kind != PS_REVIVE && g_ps.kind != PS_BODYSHIELD && g_ps.nseg > 1 && g_ps.cur_seg < g_ps.nseg - 1 && t >= psync_seg_len_ms()) {   // the next segment of a chain
        int before = g_ps.cur_seg;
        psync_seg_next(now);
        t = now - g_ps.t0;
        if (g_ps.cur_seg == before) break;               // a clip was missing: no more switching
    }
    g_ps.tick_dt = g_ps.prev_tick > 0.0 ? (float)(now - g_ps.prev_tick) : 0.0f;
    if (g_ps.tick_dt > 100.0f) g_ps.tick_dt = 100.0f;
    if (g_ps.irate > 1.0f && g_ps.cur_seg == 0 && g_ps.irate_n < 8) { psync_half_speed(0, g_ps.irate); g_ps.irate_n++; }
    if (g_ps.vrate > 1.001f && g_ps.vrate_n < 8 && g_ps.r_vic && g_ps.r_vic != ~0ULL) { psync_half_speed(1, g_ps.vrate); g_ps.vrate_n++; }   // the duel victim half's rate, re-applied on its first frames   // (the finisher intro's catch-up rate: the first frames, it may not stick on the creating one)
    g_ps.prev_tick = now;
    if (ps_dc() && g_ps.ent_vic == SID_PLAYER) {       // (the countered player snaps into the haymaker's victim pose - blend audit)
        uint64_t fr = g_frame - g_ps.f_audit;
        if (fr == 1 || fr == 4 || fr == 10 || fr == 20 || fr == 28 || fr == 34) { char tg[48]; snprintf(tg, sizeof tg, "own victim f%llu", (unsigned long long)fr); psync_layer_snap(tg, SID_PLAYER); }
    }
    if (g_ps.vlag_hold && g_ps.vhold_seg) {
        if (g_ps.cur_seg > 0) { g_ps.vlag_hold = 0; xlog("psync: u%08x victim half released at the chain switch (contact; held %d frames re-pinned)", g_ps.uid, g_ps.vlag_pins); }
    }
    if (g_ps.ahold_on && t >= g_ps.ahold * 1000.0) { g_ps.ahold_on = 0; psync_half_speed(0, g_ps.speed > 1.001f ? g_ps.speed : 1.0f); xlog("psync: u%08x hit-stop over at t=%.0f ms", g_ps.uid, t); }
    else if (g_ps.ahold_on && g_ps.hs_rate > 0.0f) psync_half_speed(0, g_ps.hs_rate);   // (melee_duel_contact.c: slowed, not frozen - the rate is re-set every frame: a speed set on the layer's first frame does not stick)
    else if (g_ps.ahold_on && psync_phase(g_ps.ent_att, g_ps.att_sid) > 0.0005f) {   // (re-pinned like the held victim half)
        float z = 0.0f; uint64_t b_[4] = {g_ps.ent_att, 0, ANIM_LAYER, g_ps.att_sid}; memcpy(&b_[1], &z, 4); dc_call(fnv64("set-animation-phase"), 4, b_); psync_half_speed(0, 0.0f); }
    if (g_ps.vlag_hold && !g_ps.vhold_seg && t >= g_ps.vlag * 1000.0) {
        g_ps.vlag_hold = 0; psync_half_speed(1, g_ps.speed > 1.001f ? g_ps.speed : 1.0f);
        xlog("psync: u%08x victim half released at t=%.0f ms (contact; held %d frames re-pinned)", g_ps.uid, t, g_ps.vlag_pins);
    } else if (g_ps.vlag_hold && g_ps.hs_rate > 0.0f && !g_ps.vhold_seg) {
        psync_half_speed(1, g_ps.hs_rate);   // (melee_duel_contact.c: the hit-confirm wait plays slowed with our half, from frame 0 - only the rate is re-set)
    } else if (g_ps.vlag_hold) {       // a speed set on the frame the layer is created does not stick (the half ran on from t=0): re-pin it every frame
        float ph = psync_phase(g_ps.ent_vic, g_ps.vic_sid);
        if (ph > 0.0005f) {
            float z = 0.0f; uint64_t b[4] = {g_ps.ent_vic, 0, ANIM_LAYER, g_ps.vic_sid};
            memcpy(&b[1], &z, 4);
            dc_call(fnv64("set-animation-phase"), 4, b);
            psync_half_speed(1, 0.0f);
            g_ps.vlag_pins++;
        }
    }
    if (g_ps_smooth && g_ps.att_dur > 2.0f * PS_OUT && t >= g_ps.att_dur * 1000.0 - PS_OUT * 1000.0 && !(g_ps.nseg > 1 && g_ps.cur_seg < g_ps.nseg - 1)) psync_att_out(t);
    // partners still there (disconnect / respawn = a new puppet)
    uint32_t self = psync_self();
    for (int k = 0; k < 2; k++) {
        int slot = k ? g_ps.vic : g_ps.att;
        uint64_t ent = k ? g_ps.ent_vic : g_ps.ent_att;
        if (slot == (int)self || ent == SID_PLAYER) continue;
        if (psync_puppet(slot) != ent) {      // disconnect / respawn: the move is over here (2013: the victim lives)
            char why[48]; snprintf(why, sizeof why, "slot %d puppet gone", slot);
            int exec = g_ps.kind == PS_GUN_EXEC || g_ps.kind == PS_MELEE_EXEC, role = g_ps.role;
            psync_abort(why, 1);
            if (exec && (role == 1 || role == 2)) gx_abort(why, 0);
            return;
        }
    }
    for (int s = 0; s < T2R_MAX_PEERS; s++) if (g_ps_pup[s].h) {
        psync_pup_cache(s);
        uint64_t h = g_ps_pup[s].h;
        if (!psync_exec_att_pup(s)) dc_call(fnv64("player-ignore-object-collision"), 1, &h);   // per-frame override (not on a hittable executioner: our swing must find it)
        if (!((g_frame - g_ps.start_frame) % 30) && !psync_reviver_pup(s) && !psync_exec_att_pup(s) && !(g_ps.pr_on && s == g_ps.vic)) { uint64_t a = h; dc_call(fnv64("npc-disable-character-collider"), 1, &a); }
        typedef uint8_t *(*fn_peer)(uint32_t);
        uint8_t *peer = ((fn_peer)t2r_peer)((uint32_t)s);
        static uint32_t warned;
        if (peer && (peer[0x4d] | peer[0x51]) && !(warned & (1u << s))) {
            warned |= 1u << s;
            xlog("psync: WARNING slot %d winmm peer lock +4d %u +51 %u during the move (its tick skips the slot entirely)", s, peer[0x4d], peer[0x51]);
        }
    }
    if (g_ps.role == 1 && !g_ps.acked) {            // START until the victim's ACK / ABORT; no answer in time = our half is cut cleanly
        double since = now - g_ps.start_ms;
        if (g_ps.resend >= 1 && g_ps.resend <= 4 && since >= PS_RESEND_MS[g_ps.resend - 1]) { psync_send(PS_OP_START, g_ps.resend, 0xff); g_ps.resend++; }
        float rtt = g_ps.vic >= 0 && g_ps.vic < T2R_MAX_PEERS && g_ps_rtt[g_ps.vic] > 0 ? g_ps_rtt[g_ps.vic] : 150.0f;
        if (g_ps.ack_cap && since >= PS_ACK_WAIT_MS + rtt) {
            int exec = g_ps.kind == PS_GUN_EXEC || g_ps.kind == PS_MELEE_EXEC, ctx_kind = g_ps.kind == PS_CTXDOWN, rv_kind = g_ps.kind == PS_REVIVE, vic = g_ps.vic;
            xlog("psync: u%08x - slot %d never answered the START (no ACK / ABORT in %.0f ms, rtt %.0f, %d copies) - our half is cut, resources refunded", g_ps.uid, vic, since, rtt, g_ps.resend);
            psync_send(PS_OP_ABORT, PS_AB_NOACK, 0xff);          // (it may have the START after all: it stops too)
            psync_fill(&g_ps_abq.w, PS_OP_ABORT, PS_AB_NOACK); g_ps_abq.n = 2; g_ps_abq.at[0] = now + 60.0; g_ps_abq.at[1] = now + 150.0;   // 2 more copies
            psync_abort("the victim never acknowledged the START", 0);
            psync_after_abort(1, exec, ctx_kind, rv_kind, (uint32_t)vic);
            return;
        }
    }
    // the clip's placement of both halves this frame; puppets are put there (psync_drive), then both bodies are logged
    float ph[2];
    for (int k = 0; k < 2; k++) {
        ph[k] = psync_phase(k ? g_ps.ent_vic : g_ps.ent_att, k ? g_ps.vic_sid : g_ps.att_sid);
        double tk = k ? t - g_ps.vlag * 1000.0 : t - g_ps.ahold * 1000.0;   // (the hit-stop shifts our attacker half by ahold)          // the half's own clock (a delayed victim half)
        // v5-feel3 (A [16238]-[16258]): mct's hit-confirm wait PLAYS both halves at hs_rate (x0.25: 35 ms of clip in the 140 ms wait), it does
        // not freeze them - but the clock above shifted both halves by the whole wait, so at its end the move time read 0 while the clips stood 35 ms in:
        // psync_rate saw 'phase -43 ms off the move time' and slowed both halves a second time (x0.91-0.95 up to t=340 ms). The clock now counts the clip
        // time the wait already played: only the unplayed part of the wait shifts it. Opt-out t2r-duel-no-hs-seed.txt.
        if (g_ps.hs_rate > 0.0f && psync_hs_seed_on()) tk += (k ? g_ps.vlag : g_ps.ahold) * 1000.0 * (double)g_ps.hs_rate;
        // v5-feel2 (the victim body jumped ~0.69 m at the finisher start; A i2 77886 / 77888 'placement jumped 0.69 / 0.72 m', i6b 12154 / 12156
        // 0.44 / 0.48 m): a finisher's deferred victim half starts PS_VIC_EARLY_MS before the hand-over, at ITS phase 0 - but its clock here still counted
        // from the move start (the attacker's intro included). The moment the intro hold was released, the lost-layer test below saw phase 0.000 against
        // a move phase of 0.085 ('layer lost at t=370 ms') and put the body 0.44-0.69 m along its clip, then the layer's real phase (0.008) put it back
        // ('psync flicker: clip time back 0.094 -> 0.008'). The half's own clock starts when it really started; segment 1 on is unchanged.
        if (k && g_ps.vdefer && g_ps.vic_early && g_ps.cur_seg == 0) tk = t - g_ps.vic_early_t;
        if (g_ps_smooth && !(k && g_ps.vlag_hold) && !(!k && g_ps.ahold_on)) psync_rate(k, ph[k], tk);
        // KICK FINISHER FIX: the left-side (kick / step-over) pairs have
        // halves of different lengths (shotgun-left 3.9 / 4.7 s, 9mm-left 4.0 / 5.1 s, bow-left 3.9 / 5.2 s; fist stomp...). Once the
        // shorter half's clip ended, get-animation-phase answers 0 / -1 (no layer), so psync_place put that body back on the clip's
        // START for the rest of the move: the attacker puppet on the victim's screen popped back ~0.9 m ("jitter: slot 0 jumped
        // 0.91 m", att ph 0.000 err 0.00 for the last 0.8 s) and the dead victim puppet on the attacker's screen did the same when
        // its half was the shorter one. A finished half now stays on the placement of its LAST frame (phase 1).
        // t2r-no-kick-fix.txt next to the exe = the old behaviour.
        if (g_ps_kickfix) {
            float hd = k ? g_ps.vic_dur : g_ps.att_dur;
            // The layer can also vanish BEFORE the measured clip end (the shotgun victim half read phase 0.938 at
            // 4.08 s, then 0.000 from 4.10 s - the engine ended the layer when the body died / the half's blend-out ran - while
            // the half is 4.35 s long): for those ~10 frames the body was placed on the clip's START (ap origin) and showed the
            // base pose ("stands upright" before the ragdoll). A half that was well into its clip and has no layer now is over.
            static uint32_t last_uid; static int lk[2]; static float phmax[2];
            uint32_t seg_key = g_ps.uid * 8u + (uint32_t)g_ps.cur_seg + (uint32_t)g_ps.rv_loops * 0x9e3779b1u;          // (a chain's next segment is a new clip: its phase starts at 0 again; the revive loop restarts too)
            if (last_uid != seg_key) { last_uid = seg_key; lk[0] = lk[1] = 0; phmax[0] = phmax[1] = 0.0f; }
            if (ph[k] > phmax[k]) phmax[k] = ph[k];
            if (hd > 0.2f && (tk >= (double)hd * 1000.0 - 30.0 || phmax[k] > 0.6f) && ph[k] < 0.5f) {
                if (!lk[k]++) xlog("kick fix: u%08x %s half's clip ended at %.2f s (phase %.3f) - body held on the clip's last placement until the move ends at %.2f s",
                                   g_ps.uid, k ? "victim" : "attacker", (double)hd, ph[k], (double)g_ps.dur_s);
                // (a recording: log lines 257957-257971 "the pu-fail victim clip is 1.83 s ... victim half's clip ended ... body held on the clip's last placement", then "pose pop (rise)
                // pelvis 0.09 -> 0.85"): the placement was held but the layer was gone, so the puppet showed its base (standing) pose until the down / death arrived. A pull-out FAIL victim half
                // on a puppet is re-applied on its end phase and frozen (psync_hold_end_pose: a fresh instance on the last frame) - the lying pose stays through the wait for the down
                // (ctxdown.c waits up to 60 ticks for it). t2r-pullout-death-hold-off.txt = old.
                if (k == 1 && g_ps.ent_vic && g_ps.ent_vic != SID_PLAYER && g_ps.kind == PS_CTXDOWN && lk[1] == 1) {
                    const char *pn5 = pul_pair_name(g_ps.move);
                    if (pn5 && !strncmp(pn5, "pu-fail", 7) && GetFileAttributesA("t2r-pullout-death-hold-off.txt") == INVALID_FILE_ATTRIBUTES) {
                        static int nfh; if (LOGCAP(nfh, 30)) xlog("psync: u%08x pull-out fail victim half ended at %.2f s - its last frame is re-applied and frozen until the down / death arrives (t2r-pullout-death-hold-off.txt = old)", g_ps.uid, (double)hd);
                        psync_hold_end_pose(g_ps.ent_vic, g_ps.vic_sid, g_ps.vic_dur, "pull-out fail hold");
                    }
                }
                if (k == 0) { g_ps_att_gone43_f = g_frame; g_ps_att_gone43_uid = g_ps.uid; }   // ps43 P1: no layer under the attacker half this frame (psync_drive's blend-out rule)
                // smoothing: a layer gone before its end continues on the move time (no jump to the last placement); == 1 at the end
                if (g_ps_smooth) { double pt = tk / ((double)hd * 1000.0); ph[k] = pt > 1.0 ? 1.0f : pt < 0.0 ? 0.0f : (float)pt; }
                else ph[k] = 1.0f;
            }
        }
        {   // lost layer (the death removed it: phase reads 0.000 / -1 while the move time is well into the half): the placement follows the
            // move time - a 0.000 phase put the body back on the clip's START (psync_vic_root_log comment). Not on the first 0.15 s of a half
            // (a receiver's skip / the first frames read 0 legitimately) and not once the half was frozen at its end.
            float hd = k ? g_ps.vic_dur : g_ps.att_dur;
            double pt = hd > 0.2f ? tk / ((double)hd * 1000.0) : 0.0;
            g_ps.mt[k] = pt > 1.0 ? 1.0f : pt < 0.0 ? 0.0f : (float)pt;
            int lost = hd > 0.2f && pt > 0.0 && tk > 150.0 && ph[k] < 0.0005f && ph[k] < g_ps.mt[k] - 0.04f && !(k && g_ps.vlag_hold) && !(!k && g_ps.ahold_on);   // (a held victim / hit-stopped attacker half reads 0 on purpose)
            if (lost && !g_ps.lost[k] && !g_ps.out_done[k] && g_ps.lost_n[k]++ < 6)
                xlog("victim root: u%08x %s half's layer lost at t=%.0f ms (phase reads %.3f, move phase %.3f, %s) - placed by the move time", g_ps.uid,
                     k ? "victim" : "attacker", t, ph[k], g_ps.mt[k], (k ? g_ps.ent_vic : g_ps.ent_att) == SID_PLAYER ? "our body" : "puppet");
            g_ps.lost[k] = lost;
            if (lost && k == 0) { g_ps_att_gone43_f = g_frame; g_ps_att_gone43_uid = g_ps.uid; }   // ps43 P1
            if (lost && ph[k] < 0.0005f) ph[k] = g_ps.mt[k];
        }
        if (k && g_ps.pr_on) { g_ps.place_ok[k] = 0; continue; }             // power ragdoll on: the physics owns the victim's root (no placement, no clamp)
        g_ps.place_ok[k] = ph[k] >= 0.0f && psync_place(k, ph[k], g_ps.place[k]);
        if (k == 0) pws_D(g_ps.wD);
        if (g_ps.place_ok[k] && (g_ps.wD[0] != 0.0f || g_ps.wD[1] != 0.0f)) { g_ps.place[k][0] += g_ps.wD[0]; g_ps.place[k][2] += g_ps.wD[1]; }   // pair shift: both halves slide together
        psync_drive(k, now);
        tc_frame(k);                    // v5-fb2: the travel clamp (never into collision, slides along it)
    }
    psync_flicker_check(t, ph);
    psync_vic_end_hold(t);
    psync_vic_root_log(t, ph[1]);
    psync_att_pose_log(t, ph[0]);
    psync_att_trace(t);
    // evidence for the own victim's death (exec-victim-death.md round 2): DR watch on our half's layer ~600 ms before the kill, layer dump
    if (g_ps.role == 2 && g_ps.ent_vic == SID_PLAYER && (g_ps.flags & PS_F_LETHAL) && g_ps.kill_s > 0 && !g_vlw_armed &&
        t >= g_ps.kill_s * 1000.0 - 600.0 && t < g_ps.kill_s * 1000.0) vlw_arm();
    vdf_dump_tick();
    psync_pr_tick(t);
    psync_keep_tick(t);
    {   // diagnostic (a NaN cast start in the engine, only the log can tell which body's locator went bad first)
        static uint32_t bad_uid; static int nb;
        for (int k = 0; k < 2; k++) {
            float lb[16];
            const float *l = psync_loc(k ? g_ps.ent_vic : g_ps.ent_att, lb);
            if (l && !ps_loc_ok(l) && (bad_uid != g_ps.uid || nb < 6)) {
                if (bad_uid != g_ps.uid) { bad_uid = g_ps.uid; nb = 0; }
                nb++;
                xlog("psync: BAD LOCATOR u%08x %s body at +%.0f ms (phase %.3f): pos %g %g %g q %g %g %g %g; clip place %.2f %.2f %.2f ok %d, "
                     "start_ok %d", g_ps.uid, k ? "victim" : "attacker", t, ph[k], l[0], l[1], l[2], l[4], l[5], l[6], l[7],
                     g_ps.place[k][0], g_ps.place[k][1], g_ps.place[k][2], g_ps.place_ok[k], g_ps.start_ok[k]);
            }
        }
    }
    psync_frame_log(t, ph, now - g_ps.play_ms < g_ps_blend * 1000.0);
    psync_place_log(t, ph);
    if (t >= g_ps.dur_s * 1000.0 + PS_END_PAD_MS) {
        if (g_ps.role == 1) psync_send(PS_OP_END, 0, 0xff);
        // the halves ran out: puppets blend back to the network (the remote body ended on the same ap path)
        psync_finish("clip over", 0);
    }
}
static int psync_duel_now(void) { return g_ps.role && g_ps.kind == PS_CTXDOWN && (mdu_move(g_ps.move) || cd_counter_move(g_ps.move)); }
