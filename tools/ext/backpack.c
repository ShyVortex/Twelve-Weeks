// backpack.c - the TAB backpack (crafting / shop) as other players see it. Included after paired.c in t2r-ext.c
// (uses its helpers: dc_call, xlog, animate_from, anim_len, psync_oneway, psync_stop, psync_dead, g_send_tramp).
//
// Own side (feature_backpack_prop in t2r-ext.c): the worn bag <-> prop hand-off runs inside the engine's own
// EnterBackpack / LeaveBackpack (the clip's enter-backpack / leave-backpack events), weapons stay slung.
// This file: the owner broadcasts its backpack phase (MSG_BACKPACK), every receiver plays the craft clips on that
// player's puppet at the owner's clip time + the one-way latency (the psync pattern).
//
// The bag-off state IS on the wire (bagoff = g_bp_hid, the
// engine's own enter / leave swap on the owner), so a receiver now takes the bag off its puppet too: the worn bag parts are hidden and a
// held bag prop (the satchel bag actor, SimpleAttachable - a puppet cannot drive a ProcessBackpack) follows the puppet's right hand through
// the intro / outro and rests on the floor in front of it during the crouch loop. Never zero bags: the worn bag goes off only once the prop
// object exists (no prop = the old on-the-back craft). The owner also sends the moment bagoff flips (it used to ride the 500 ms period only).
// Cleaned up on bag-on, death / down / paired move / respawn / match end / timeout. t2r-no-puppet-bag-off.txt = the old behaviour.
// Second pass: first choice is the SAME animated bag the
// owner has - the look's TAB prop look (BP_PROP_LOOKS, skeleton backpack-abby) spawned as a SimpleAttachable, set on the puppet's locator every
// frame (the prop bind space = the character space) and given the prop clips backpack-intro / -loop / -outro at the same moment and phase as
// the puppet's craft clip (bp_pup_play), so straps, lid, the drop to the floor and the pick-up move frame for frame. Probed at the first take-off
// (spawn ok + get-animation-duration(backpack-intro) > 0, logged "bp: ... animated bag"); if the engine will not animate it: the look's own bag
// as a rigid actor (held_bag_pak.py, HB_ACTOR) following the hand / resting on the floor; if that actor is missing: the satchel actor.
// (older text) Puppets keep their worn bag on the back for the whole anim: the TAB prop is a ProcessBackpack that the engine only
// drives from a Player - its set-parent handler (0x141158d00, event set-parent) stores the parent at +0x600 and the
// prop follows the parent Player's backpack anim state; a puppet (NPC-type character, no player anim state, no
// PlayerBackpackAnimCtrl) cannot drive one. Hiding the puppet's bag without a prop in its hands would show NO bag,
// so the puppet crouches and crafts with the bag on (the 2013 Factions craft) - never zero, never two bags.
//
// MSG_BACKPACK [u8 ver 1][u8 phase][u8 bag off][u8 seq][u32 ms since the phase began][u16 enter ms][u16 leave ms]
//   phase 0 idle, 1 open (intro -> loop), 2 closing (outro), 3 abort (death / down / match end: blend out now).
//   Sent on every change (+100 / +300 ms copies), every 500 ms while open / closing and every 3 s while idle, so a lost
//   packet or a late joiner converges to the right state within one period. enter / leave ms = where the bag swap
//   happened in the owner's clip time (log / diagnosis; 0xffff = not seen yet).
// Logs: "bp: ..." with real ms (QPC).
//
// STANCE
// the receivers always played the STANDING set (stand^craft-intro / crouch-craft-idle / stand^craft-outro + their --backpack prop
// clips) and the recorded prop root track was one track for every stance (a crouched owner's open overwrote the standing one). The game's own
// data (dc1/anim-player/player-inventory2.bin + player-overlays.bin, sp-common anim-abby-player-backpack.pak, decoded) has one set per stance:
//   stand  : stand^craft-intro (1567 ms) -> crouch-craft-idle (7400) -> stand^craft-outro (1800)
//   crouch : crouch-craft-intro (1567)   -> crouch-craft-idle (7400) -> crouch-craft-outro (1600)   (the crouch overlay remaps the stand clips)
//   prone  : prone-craft-intro (2500)    -> prone-craft-idle (10000) -> prone-craft-outro (2533)    (s_prone-inventory-* states)
//   supine : supine-craft-intro (2100)   -> supine-craft-idle (10000) -> supine-craft-outro (2333)  (the supine overlay remaps the prone clips)
// each with a "<clip>--backpack" prop clip. There is no moving set: the backpack roots the player (moving players stop, cover = crouch).
// The owner now sends its stance (sampled while idle, latched at the open, followed while open), the puppet plays that stance's clips and
// prop clips, and the recorded tracks are kept per stance (track index BPT_C(stance, clip); stand = the old indices 1..3, so old peers / files
// keep working: old receivers drop track chunks of index > 3, old senders' messages read as stand).
// MSG_BACKPACK gained one trailing byte [u8 stance] (BP_VER stays 1: an old receiver reads the first 12 bytes).

#define MSG_BACKPACK 0x5B
#define BP_VER 1
#pragma pack(push, 1)
typedef struct { uint8_t ver, phase, bagoff, seq; uint32_t el_ms; uint16_t enter_ms, leave_ms; uint8_t stance; } bp_msg_t;
#pragma pack(pop)
#define BP_MSG_V1_LEN 12                    // the message before the stance byte

enum { BPP_IDLE = 0, BPP_OPEN = 1, BPP_CLOSING = 2, BPP_ABORT = 3 };
static const char *const BPP_NAME[4] = {"idle", "open", "closing", "abort"};
enum { BPS_STAND = 0, BPS_CROUCH = 1, BPS_PRONE = 2, BPS_SUPINE = 3, BPS_N = 4 };
static const char *const BPS_NAME[BPS_N] = {"stand", "crouch", "prone", "supine"};
// lengths of the abby craft clips per stance (anim-abby-player-backpack.pak, 30 fps; the --backpack prop clips have the same frame counts)
static const double BPS_INTRO_MS[BPS_N] = {1567.0, 1567.0, 2500.0, 2100.0};
static const double BPS_LOOP_MS[BPS_N] = {7400.0, 7400.0, 10000.0, 10000.0};
static const double BPS_OUTRO_MS[BPS_N] = {1800.0, 1600.0, 2533.0, 2333.0};
#define BPT_NC (BPS_N * 3 + 1)              // track rows: 0 unused, BPT_C(stance, clip 1..3)
#define BPT_C(st, clip) ((st) * 3 + (clip))

// ---- own phase
static struct {
    int phase; double t_phase;      // bp_ms() the phase began
    uint8_t seq;
    double next_send; int copies;   // copies: change copies left (+100 / +300 ms)
    double t_change;
    uint16_t enter_ms, leave_ms;
    uint32_t seen_enter, seen_leave;
    int stance;                     // BPS_*: latched at the open (the idle sample before it), followed while open (bp_own_stance_tick)
    int st_idle;                    // last idle sample
    int st_cand, st_cand_n;         // while open: a measured stance that differs from the latched one, and how many samples in a row
    double st_next;                 // next stance sample (bp_ms)
    int rec_stop;                   // the recorder is paused (a stance read off the latched one / a reopen mid-outro, see bpt_rec_abort)
    double rec_loop_t0;             // > 0: the stance changed while open, the recorder writes the NEW stance's loop row, clock from this bp_ms()
} g_bpo = {0, 0, 0, 0, 0, 0, 0xffff, 0xffff, 0, 0, 0, 0, 0, 0, 0, 0, 0};
static int bp_own_phase_now(void) { return g_bpo.phase; }

static void bp_send(double now) {
    if (!g_send_tramp) return;
    bp_msg_t m;
    m.ver = BP_VER; m.phase = (uint8_t)g_bpo.phase; m.bagoff = (uint8_t)(g_bp_hid != 0); m.seq = g_bpo.seq;
    double el = now - g_bpo.t_phase;
    m.el_ms = el > 0 ? (uint32_t)el : 0;
    m.enter_ms = g_bpo.enter_ms; m.leave_ms = g_bpo.leave_ms;
    m.stance = (uint8_t)(g_bpo.stance & 3);
    g_send_tramp(MSG_BACKPACK, (uint8_t *)&m, sizeof m, 0xff);
}
// our stance now (the natives the stance features use elsewhere): supine before prone (a supine body may answer prone? too)
static int bp_own_stance_measure(int *raw) {
    uint64_t n = 0, pr = dc_call(fnv64("player-is-prone?"), 0, &n), su = dc_call(fnv64("player-is-supine?"), 0, &n), cr = dc_call(fnv64("player-is-crouched?"), 0, &n);
    int p = pr != ~0ULL && (pr & 0xff), u = su != ~0ULL && (su & 0xff), c = cr != ~0ULL && (cr & 0xff);
    if (raw) *raw = p | (u << 1) | (c << 2);
    return u ? BPS_SUPINE : p ? BPS_PRONE : c ? BPS_CROUCH : BPS_STAND;
}
// sampled every 100 ms while idle (the open latches the last idle sample: by the menu flag the engine may already be in its intro) and every
// 250 ms while open. While open a different measured stance replaces the latched one after 2 samples in a row, except stand -> crouch: the
// standing set's own loop IS crouch-craft-idle, so a crouch read there is the loop, not a stance change (the puppet's loop is the same clip).
// Closing / abort: no change (the outro is the one of the stance the bag was opened / followed in).
static void bpt_rec_abort(const char *why, double now);
static void bp_own_stance_tick(double now) {
    if (now < g_bpo.st_next) return;
    int raw = 0, st = bp_own_stance_measure(&raw);
    if (g_bpo.phase == BPP_IDLE) {
        g_bpo.st_next = now + 100.0;
        g_bpo.st_idle = st;
        return;
    }
    g_bpo.st_next = now + (g_bpo.phase == BPP_CLOSING ? 100.0 : 250.0);
    // A/B (stood up, then went prone, during own crouch / stand outros): the body left the clip of the latched stance, but the recorder kept
    // writing that motion into the latched stance's track (crouch outro root rose 0.7 m) and the puppets replayed it (B's crouched bag floated over its head).
    // Any read off the latched stance (but the standing loop's crouch read) pauses the recorder and drops the samples of the clip it was in. While OPEN the
    // confirmed change below then switches the recorder to the new stance's loop row (the puppets switch to that loop at the same moment); while CLOSING the
    // body is in a stance transition, not an outro, so nothing more is recorded for that close.
    if (st != g_bpo.stance && !(g_bpo.stance == BPS_STAND && st == BPS_CROUCH) && !g_bpo.rec_stop) {
        char w[96]; snprintf(w, sizeof w, "own stance read %s while %s (latched %s)", BPS_NAME[st], BPP_NAME[g_bpo.phase & 3], BPS_NAME[g_bpo.stance & 3]);
        bpt_rec_abort(w, now);
    }
    {   static int last_raw = -1, nl;
        if (raw != last_raw && nl < 200) { nl++; xlog("bp: own stance read %s (prone %d supine %d crouched %d) while %s %.0f ms in, latched %s", BPS_NAME[st], raw & 1, (raw >> 1) & 1, (raw >> 2) & 1,
                                                    BPP_NAME[g_bpo.phase & 3], now - g_bpo.t_phase, BPS_NAME[g_bpo.stance & 3]); }
        last_raw = raw; }
    if (g_bpo.phase != BPP_OPEN || st == g_bpo.stance || (g_bpo.stance == BPS_STAND && st == BPS_CROUCH)) { g_bpo.st_cand_n = 0; return; }
    if (st != g_bpo.st_cand) { g_bpo.st_cand = st; g_bpo.st_cand_n = 0; }
    if (++g_bpo.st_cand_n < 2) return;
    xlog("bp: own stance %s -> %s while open (%.0f ms in) - sent to the puppets now", BPS_NAME[g_bpo.stance & 3], BPS_NAME[st], now - g_bpo.t_phase);
    g_bpo.stance = st; g_bpo.st_cand_n = 0;
    g_bpo.rec_loop_t0 = now; g_bpo.rec_stop = 0;
    xlog("bptrack: own recorder switches to the %s loop row (clock from now, as the puppets' loop switch)", BPS_NAME[st]);
    bp_send(now);
    g_bpo.t_change = now; g_bpo.copies = 2; g_bpo.next_send = now + 100.0;
}
static void bpt_open_done(void);
static void bp_own_set(int phase, double now, const char *why) {
    if (phase == g_bpo.phase) return;
    if (phase == BPP_OPEN) {
        g_bpo.stance = g_bpo.st_idle; g_bpo.st_cand_n = 0; g_bpo.st_next = now + 250.0; g_bpo.rec_loop_t0 = 0;
        g_bpo.rec_stop = g_bpo.phase == BPP_CLOSING;   // reopened mid-outro: the intro starts from the outro's pose, not the stance's start pose - not a track
        if (g_bpo.rec_stop) xlog("bptrack: own reopen mid-outro - this open records no track samples");
    }
    if (phase == BPP_CLOSING && g_bpo.stance == BPS_STAND && bp_own_stance_measure(NULL) == BPS_CROUCH) {
        // crouched while a standing open was open (not followed: the standing loop is the crouch idle): the engine plays the CROUCH outro now
        xlog("bp: own stance stand -> crouch at the close (crouched during a standing open) - the crouch outro plays");
        g_bpo.stance = BPS_CROUCH;
    }
    xlog("bp: own phase %s -> %s at t %.0f ms (%s), stance %s", BPP_NAME[g_bpo.phase & 3], BPP_NAME[phase & 3], now, why, BPS_NAME[g_bpo.stance & 3]);
    if (phase == BPP_IDLE && (g_bpo.phase == BPP_CLOSING || g_bpo.phase == BPP_ABORT)) bpt_open_done();
    g_bpo.phase = phase; g_bpo.t_phase = now; g_bpo.seq++;
    g_bpo.t_change = now; g_bpo.copies = 2;
    bp_send(now);
    g_bpo.next_send = now + 100.0;
}
static int bp_own_dead(void) {
    uint64_t h = SID_PLAYER;
    uint64_t d = dc_call(0xe93f704f02a9ecd5ULL /* character-is-dead? */, 1, &h);
    return d != ~0ULL && (d & 0xff);
}
static void bpt_own_sample(double now);
static void bpt_send_tick(double now);
static void bp_own_tick(double now) {
    static int menu_was;
    int live = match_substate() == 6;
    int menu = live && (player_menu_active() == 1 || g_tab_open);
    int gone = !live || g_downed || bp_own_dead();
    if (g_bpo.seen_enter != g_bp_n_enter) {            // where the swap sat in our clip time (from the open)
        g_bpo.seen_enter = g_bp_n_enter;
        if (g_bpo.phase == BPP_OPEN) { double d = g_bp_t_enter - g_bpo.t_phase; g_bpo.enter_ms = d >= 0 && d < 60000 ? (uint16_t)d : 0xffff; }
    }
    if (g_bpo.seen_leave != g_bp_n_leave) {
        g_bpo.seen_leave = g_bp_n_leave;
        if (g_bpo.phase == BPP_CLOSING) { double d = g_bp_t_leave - g_bpo.t_phase; g_bpo.leave_ms = d >= 0 && d < 60000 ? (uint16_t)d : 0xffff; }
    }
    if (gone) {
        if (g_bpo.phase == BPP_OPEN || g_bpo.phase == BPP_CLOSING)
            bp_own_set(BPP_ABORT, now, !live ? "match end / not in game" : g_downed ? "downed" : "dead");
        else if (g_bpo.phase == BPP_ABORT && now - g_bpo.t_phase > 1000.0) bp_own_set(BPP_IDLE, now, "abort sent");
    } else if (menu && !menu_was) bp_own_set(BPP_OPEN, now, "menu opened = intro clip starts");
    else if (!menu && menu_was && g_bpo.phase == BPP_OPEN) bp_own_set(BPP_CLOSING, now, "menu closed = outro clip starts");
    else if (g_bpo.phase == BPP_CLOSING && ((!g_bp_hid && now - g_bpo.t_phase > (BPS_OUTRO_MS[g_bpo.stance & 3] > 1600.0 ? BPS_OUTRO_MS[g_bpo.stance & 3] - 100.0 : 1500.0))
                                            || now - g_bpo.t_phase > 4000.0))
        bp_own_set(BPP_IDLE, now, "outro over");      // (prone / supine outros are 2.3 - 2.5 s: the idle waited 1.5 s, the track recorder stopped mid-outro)
    else if (g_bpo.phase == BPP_ABORT && now - g_bpo.t_phase > 1000.0) bp_own_set(BPP_IDLE, now, "abort sent");
    menu_was = menu;
    { static int off_was;
      if ((g_bp_hid != 0) != off_was) {     // the bag swap moment: tell the puppets now (+100 / +300 ms copies), not at the next 500 ms period
          off_was = g_bp_hid != 0;
          bp_send(now);
          g_bpo.t_change = now; g_bpo.copies = 2; g_bpo.next_send = now + 100.0;
      } }
    if (live && !gone) bp_own_stance_tick(now);
    bpt_own_sample(now);
    bpt_send_tick(now);
    if (now >= g_bpo.next_send) {        // change copies at +100 / +300 ms, then the period (500 ms active, 3 s idle)
        bp_send(now);
        double period = g_bpo.phase == BPP_OPEN || g_bpo.phase == BPP_CLOSING ? 500.0 : 3000.0;
        if (g_bpo.copies == 2) { g_bpo.copies = 1; g_bpo.next_send = g_bpo.t_change + 300.0; }
        else { g_bpo.copies = 0; g_bpo.next_send = now + period; }
    }
}

#include "bp_track.h"
#ifndef BPTR_H_N   // a header from the old log tool (tools/bp_track_make.py) has no root rows
static const struct { uint8_t c; uint16_t i; float v[7]; } BPTR_H[] = {{0, 0, {0, 0, 0, 0, 0, 0, 1}}};
#define BPTR_H_N 0
#endif
// ---- puppets
enum { BPC_NONE = 0, BPC_INTRO = 1, BPC_LOOP = 2, BPC_OUTRO = 3 };
static const char *const BPC_NAME[4] = {"none", "intro", "loop", "outro"};
// ---- recorded own-body prop track (our OWN bag open animation is right, the bystander's is not -> replay ours on the puppet).
// Every frame while OUR bag prop is out, the prop's spinec joint is read in the body locator's yaw frame and stored per clip (1 intro, 2 loop, 3 outro) and 25 ms step
// (the clip time = our phase clock, the same clock the puppets derive their clip start from: msg el_ms). The puppets then place the prop so that ITS spinec is at
// body locator + R(yaw) * track(clip, clip time): the bag's travel in front of the body comes from the real own animation, not from a guessed channel.
// t2r-bp-record.txt next to the exe = also log every sample ("bptrack: clip C idx I rel x y z look L"), tools/bp_track_make.py turns the log into bp_track.h.
// The look does not matter: every look's prop is the backpack-abby skeleton playing the same Abby clips (male + female alike, IsAbby forced while the bag is off).
#define BPT_DT 25.0
#define BPT_N 320
// The track was
// only learned from the VIEWER's own opens and the recorder flag was never set (bp_track.h empty), so A, who never opened its own bag, had no track and B's bag on A
// fell back to the spinec follow (log: no "bptrack: slot" line all session). Now, with no flag:
//   - every own open is recorded (as before) and saved next to the exe (t2r-bp-track.bin), loaded at start: the local track survives restarts;
//   - the owner streams its samples to every peer while it records (MSG_BACKPACK ver 0x54 chunks, one per 50 ms) and resends the whole track after each close
//     (lost packets, late joiners); the receiver keeps it per slot = the bag on another player follows that player's own recorded body-relative path;
//   - per clip the puppet latches its source at the clip start: the owner's track when complete, else our own, else the spinec follow (logged).
static float g_bpt[BPT_NC][BPT_N][3]; static uint8_t g_bpt_ok[BPT_NC][BPT_N]; static int g_bpt_init, g_bpt_live;
static float g_bptp[T2R_MAX_PEERS][BPT_NC][BPT_N][3]; static uint8_t g_bptp_ok[T2R_MAX_PEERS][BPT_NC][BPT_N];   // per owner slot, from its chunks
static uint8_t g_bpt_dirty[BPT_NC][BPT_N];      // own samples not yet sent
static int g_bpt_nrx[T2R_MAX_PEERS];
static int g_bpt_open_n[BPT_NC];           // own samples recorded in the current open, per track row
#define BPT_FILE "t2r-bp-track.bin"
#define BPT_MAGIC 0x31545042u              // "BPT1" = rows 0..3 only (stand, before)
#define BPT_MAGIC2 0x32545042u             // "BPT2" = BPT_NC rows (per stance)
static void bptr_load(void);
static void bpt_load_header(void) {
    if (g_bpt_init) return;
    g_bpt_init = 1;
    // bp_track.h = built-in tracks of every stance (tools/bp_track_from_bin.py, recorded A/B opens): a crouched / prone owner's bag is placed on the
    // first open in that stance too, before any own open or owner stream of it exists (first crouch / prone open = spinec follow, bag off the hands)
    for (int k = 0; k < BPT_H_N; k++) if (BPT_H[k].c >= 1 && BPT_H[k].c < BPT_NC && BPT_H[k].i < BPT_N) { memcpy(g_bpt[BPT_H[k].c][BPT_H[k].i], BPT_H[k].v, 12); g_bpt_ok[BPT_H[k].c][BPT_H[k].i] = 1; }
    int nf = 0;
    FILE *f = exe_side_open(BPT_FILE, "rb");
    if (f) {
        uint32_t mg = 0;
        static float tb[BPT_NC][BPT_N][3]; static uint8_t okb[BPT_NC][BPT_N];
        int rows = 0;
        memset(okb, 0, sizeof okb);
        if (fread(&mg, 4, 1, f) == 1) rows = mg == BPT_MAGIC2 ? BPT_NC : mg == BPT_MAGIC ? 4 : 0;
        if (rows && fread(okb, (size_t)rows * BPT_N, 1, f) == 1 && fread(tb, (size_t)rows * BPT_N * 12, 1, f) == 1)
            for (int c = 1; c < rows; c++) for (int i = 0; i < BPT_N; i++)
                if (okb[c][i] && tb[c][i][0] == tb[c][i][0] && fabsf(tb[c][i][0]) < 3.0f && fabsf(tb[c][i][1]) < 3.0f && fabsf(tb[c][i][2]) < 3.0f) {
                    memcpy(g_bpt[c][i], tb[c][i], 12); g_bpt_ok[c][i] = 1; g_bpt_dirty[c][i] = 1; nf++; }
        fclose(f);
    }
    xlog("bptrack: %d recorded samples from bp_track.h, %d from %s (own opens of earlier sessions, sent to the peers)", BPT_H_N, nf, BPT_FILE);
    bptr_load();
}
// gap-tolerant read: between the nearest recorded samples around the clip time, held at the first / last one outside them
static int bpt_get_t(const float (*tb)[3], const uint8_t *ok, double ms, float *out) {
    if (ms < 0) ms = 0;
    double f = ms / BPT_DT; int i = (int)f; if (i > BPT_N - 1) i = BPT_N - 1;
    int a = i, b = i + 1;
    while (a >= 0 && !ok[a]) a--;
    while (b < BPT_N && !ok[b]) b++;
    if (a < 0 && b >= BPT_N) return 0;
    if (a < 0) { memcpy(out, tb[b], 12); return 1; }
    if (b >= BPT_N) { memcpy(out, tb[a], 12); return 1; }
    float t = (float)((f - a) / (double)(b - a)); if (t < 0) t = 0; if (t > 1) t = 1;
    for (int k = 0; k < 3; k++) out[k] = tb[a][k] + (tb[b][k] - tb[a][k]) * t;
    return 1;
}
// usable = at least 16 samples (400 ms) and no hole over 200 ms between the first and the last
static int bpt_complete(const uint8_t *ok, int *n_out) {
    int n = 0, last = -1, gap = 0;
    for (int i = 0; i < BPT_N; i++) if (ok[i]) { if (last >= 0 && i - last > gap) gap = i - last; last = i; n++; }
    if (n_out) *n_out = n;
    return n >= 16 && gap <= 8;
}
static int bpt_get(int clip, double ms, float *out) {
    bpt_load_header();
    if (clip < 1 || clip >= BPT_NC) return 0;
    return bpt_get_t((const float (*)[3])g_bpt[clip], g_bpt_ok[clip], ms, out);
}
static void bpt_save(void) {
    FILE *f = exe_side_open(BPT_FILE, "wb");
    if (!f) { xlog("bptrack: cannot write %s", BPT_FILE); return; }
    uint32_t mg = BPT_MAGIC2;
    fwrite(&mg, 4, 1, f); fwrite(g_bpt_ok, sizeof g_bpt_ok, 1, f); fwrite(g_bpt, sizeof g_bpt, 1, f);
    fclose(f);
}
// MSG_BACKPACK track chunk: [u8 0x54][u8 clip][u16 first idx][u8 n][u8 0] then n x {u8 has, i16 x, i16 y, i16 z} (mm, body yaw frame).
// Old receivers drop it (ver != BP_VER).
#define BPT_VER 0x54
#define BPT_CHUNK 24
static int bptr_send_one(void);
static void bpt_send_tick(double now) {
    static double next; static int alt;
    if (!g_send_tramp || now < next || match_substate() != 6) return;
    if ((alt++ & 1) && bptr_send_one()) { next = now + 50.0; return; }      // the root track (the one the puppets replay) and the spinec track take turns
    for (int c = 1; c < BPT_NC; c++) {
        int i0 = 0; while (i0 < BPT_N && !g_bpt_dirty[c][i0]) i0++;
        if (i0 >= BPT_N) continue;
        uint8_t b[6 + BPT_CHUNK * 7]; int n = 0;
        b[0] = BPT_VER; b[1] = (uint8_t)c; b[2] = (uint8_t)(i0 & 0xff); b[3] = (uint8_t)(i0 >> 8); b[5] = 0;
        for (int i = i0; i < BPT_N && n < BPT_CHUNK; i++, n++) {
            uint8_t *e = b + 6 + n * 7; int16_t q[3] = {0, 0, 0};
            e[0] = g_bpt_ok[c][i];
            if (e[0]) for (int k = 0; k < 3; k++) q[k] = (int16_t)lrintf(g_bpt[c][i][k] * 1000.0f);
            memcpy(e + 1, q, 6);
            g_bpt_dirty[c][i] = 0;
        }
        b[4] = (uint8_t)n;
        g_send_tramp(MSG_BACKPACK, b, (uint64_t)(6 + n * 7), 0xff);
        next = now + 50.0;
        return;
    }
    if (bptr_send_one()) next = now + 50.0;
}
static void bpt_net_recv(int s, const uint8_t *b, uint64_t len) {
    if (len < 6 || b[1] < 1 || b[1] >= BPT_NC) return;
    int c = b[1], i0 = b[2] | (b[3] << 8), n = b[4];
    if (len < (uint64_t)(6 + n * 7) || i0 + n > BPT_N) return;
    for (int j = 0; j < n; j++) {
        const uint8_t *e = b + 6 + j * 7; int16_t q[3]; memcpy(q, e + 1, 6);
        if (!e[0]) continue;            // a hole in the owner's track: keep what we had there
        g_bptp_ok[s][c][i0 + j] = 1;
        for (int k = 0; k < 3; k++) g_bptp[s][c][i0 + j][k] = q[k] / 1000.0f;
    }
    if (!g_bpt_nrx[s]++ || g_bpt_nrx[s] % 50 == 0) {
        int nn; bpt_complete(g_bptp_ok[s][c], &nn);
        xlog("bptrack: slot %d track chunk %d (clip %d idx %d+%d, that clip now %d samples)", s, g_bpt_nrx[s], c, i0, n, nn);
    }
}
// ---- ROOT track. The spinec track put the prop where the owner's prop SPINEC was by feedback
// (move the root by target - the spinec read back): the joint read is a frame behind the root we set, so in the fast part of the intro / outro the prop trailed its
// target (A log: "off target 30.8 cm" at 594 ms) - lag - and only the spinec POSITION was replayed, not the prop's orientation - offset. The prop plays the same
// "<clip>--backpack" clip on both screens, so what has to be copied is only where the engine puts the prop's ROOT on the owner (the prop is parented to the player
// there): its full locator (position + rotation) relative to the body locator, per clip and 25 ms, sampled from the owner's ProcessBackpack locator. The puppet sets its
// prop root to body locator * that, open loop, every frame at its own clip time (no feedback, no read-back) - the clip moves the bag the same way on both screens.
// Wire: MSG_BACKPACK ver 0x55 chunks [u8 0x55][u8 clip][u16 idx][u8 n][u8 0] + n x {u8 has, i16 pos x y z mm, i16 quat x y z w * 32767}; t2r-bp-root.bin next to the exe.
#define BPTR_FILE "t2r-bp-root.bin"
#define BPTR_MAGIC 0x31525042u             // "BPR1" = rows 0..3 only (stand, before)
#define BPTR_MAGIC2 0x32525042u            // "BPR2" = BPT_NC rows (per stance)
#define BPTR_VER 0x55
#define BPTR_CHUNK 16
static float g_bptr[BPT_NC][BPT_N][7]; static uint8_t g_bptr_ok[BPT_NC][BPT_N], g_bptr_dirty[BPT_NC][BPT_N];
static float g_bptrp[T2R_MAX_PEERS][BPT_NC][BPT_N][7]; static uint8_t g_bptrp_ok[T2R_MAX_PEERS][BPT_NC][BPT_N];
static int g_bptr_open_n[BPT_NC], g_bptr_nrx[T2R_MAX_PEERS], g_bptr_live;
static int bptr_valid(const float *v) {
    float n = v[3] * v[3] + v[4] * v[4] + v[5] * v[5] + v[6] * v[6];
    return __builtin_isfinite(v[0] + v[1] + v[2] + n) && fabsf(v[0]) < 3.0f && fabsf(v[1]) < 3.0f && fabsf(v[2]) < 3.0f && n > 0.8f && n < 1.2f;
}
static void bptr_load(void) {
    int nf = 0, nh = 0;
    for (int k = 0; k < BPTR_H_N; k++) if (BPTR_H[k].c >= 1 && BPTR_H[k].c < BPT_NC && BPTR_H[k].i < BPT_N && bptr_valid(BPTR_H[k].v)) {
        memcpy(g_bptr[BPTR_H[k].c][BPTR_H[k].i], BPTR_H[k].v, 28); g_bptr_ok[BPTR_H[k].c][BPTR_H[k].i] = 1; nh++; }
    FILE *f = exe_side_open(BPTR_FILE, "rb");
    if (f) {
        uint32_t mg = 0;
        static float tb[BPT_NC][BPT_N][7]; static uint8_t okb[BPT_NC][BPT_N];
        int rows = 0;
        memset(okb, 0, sizeof okb);
        if (fread(&mg, 4, 1, f) == 1) rows = mg == BPTR_MAGIC2 ? BPT_NC : mg == BPTR_MAGIC ? 4 : 0;
        if (rows && fread(okb, (size_t)rows * BPT_N, 1, f) == 1 && fread(tb, (size_t)rows * BPT_N * 28, 1, f) == 1)
            for (int c = 1; c < rows; c++) for (int i = 0; i < BPT_N; i++)
                if (okb[c][i] && bptr_valid(tb[c][i])) { memcpy(g_bptr[c][i], tb[c][i], 28); g_bptr_ok[c][i] = 1; g_bptr_dirty[c][i] = 1; nf++; }
        fclose(f);
    }
    xlog("bptrack: %d root samples from bp_track.h, %d from %s (own opens of earlier sessions, sent to the peers)", nh, nf, BPTR_FILE);
}
static void bptr_save(void) {
    FILE *f = exe_side_open(BPTR_FILE, "wb");
    if (!f) { xlog("bptrack: cannot write %s", BPTR_FILE); return; }
    uint32_t mg = BPTR_MAGIC2;
    fwrite(&mg, 4, 1, f); fwrite(g_bptr_ok, sizeof g_bptr_ok, 1, f); fwrite(g_bptr, sizeof g_bptr, 1, f);
    fclose(f);
}
// gap tolerant as bpt_get_t; the rotation is blended in the same hemisphere and renormalised
static int bptr_get_t(const float (*tb)[7], const uint8_t *ok, double ms, float *out) {
    if (ms < 0) ms = 0;
    double f = ms / BPT_DT; int i = (int)f; if (i > BPT_N - 1) i = BPT_N - 1;
    int a = i, b = i + 1;
    while (a >= 0 && !ok[a]) a--;
    while (b < BPT_N && !ok[b]) b++;
    if (a < 0 && b >= BPT_N) return 0;
    if (a < 0) { memcpy(out, tb[b], 28); return 1; }
    if (b >= BPT_N) { memcpy(out, tb[a], 28); return 1; }
    float t = (float)((f - a) / (double)(b - a)); if (t < 0) t = 0; if (t > 1) t = 1;
    float sg = tb[a][3] * tb[b][3] + tb[a][4] * tb[b][4] + tb[a][5] * tb[b][5] + tb[a][6] * tb[b][6] < 0 ? -1.0f : 1.0f;
    for (int k = 0; k < 3; k++) out[k] = tb[a][k] + (tb[b][k] - tb[a][k]) * t;
    float n = 0;
    for (int k = 3; k < 7; k++) { out[k] = tb[a][k] + (sg * tb[b][k] - tb[a][k]) * t; n += out[k] * out[k]; }
    n = sqrtf(n); if (n < 1e-3f) return 0;
    for (int k = 3; k < 7; k++) out[k] /= n;
    return 1;
}
// world locator (pos xyzw, quat xyzw) of a process (its bound frame +0x100, 0x14133db30)
static int bptr_proc_loc(uint8_t *pr, float *l8) {
    typedef const float *(*fn_loc)(void *, float *);
    if (!pr || IsBadReadPtr(pr + 0x100, 0x50)) return 0;
    float a[16];
    const float *p = ((fn_loc)((uint8_t *)GetModuleHandleW(NULL) + 0x133db30))(pr + 0x100, a);
    if (!p || IsBadReadPtr(p, 32)) return 0;
    memcpy(l8, p, 32);
    float n = l8[4] * l8[4] + l8[5] * l8[5] + l8[6] * l8[6] + l8[7] * l8[7];
    return __builtin_isfinite(l8[0] + l8[1] + l8[2] + n) && n > 0.8f && n < 1.2f;
}
// owner: the prop root relative to the body locator: p = conj(qb) (p_prop - p_body), q = conj(qb) q_prop
static void bptr_own_sample(uint8_t *pr, const float *loc, int clip, int i) {
    float l8[8];
    if (!bptr_proc_loc(pr, l8)) { static int nb; if (nb++ < 3) xlog("bptrack: own prop root locator unreadable (proc %p)", (void *)pr); return; }
    float cq[4] = {-loc[4], -loc[5], -loc[6], loc[7]}, d[3] = {l8[0] - loc[0], l8[1] - loc[1], l8[2] - loc[2]}, v[7];
    qrotv(cq, d, v);
    bp_qmul(cq, l8 + 4, v + 3);
    if (!bptr_valid(v)) return;
    memcpy(g_bptr[clip][i], v, 28); g_bptr_ok[clip][i] = 1; g_bptr_dirty[clip][i] = 1; g_bptr_open_n[clip]++; g_bptr_live++;
    static int nl; if (nl < 8 && (i % 10) == 0) { nl++; xlog("bptrack: own prop root clip %d idx %d rel pos %.3f %.3f %.3f quat %.3f %.3f %.3f %.3f", clip, i, v[0], v[1], v[2], v[3], v[4], v[5], v[6]); }
}
static int bptr_send_one(void) {
    for (int c = 1; c < BPT_NC; c++) {
        int i0 = 0; while (i0 < BPT_N && !g_bptr_dirty[c][i0]) i0++;
        if (i0 >= BPT_N) continue;
        uint8_t b[6 + BPTR_CHUNK * 15]; int n = 0;
        b[0] = BPTR_VER; b[1] = (uint8_t)c; b[2] = (uint8_t)(i0 & 0xff); b[3] = (uint8_t)(i0 >> 8); b[5] = 0;
        for (int i = i0; i < BPT_N && n < BPTR_CHUNK; i++, n++) {
            uint8_t *e = b + 6 + n * 15; int16_t q[7] = {0};
            e[0] = g_bptr_ok[c][i];
            if (e[0]) {
                for (int k = 0; k < 3; k++) q[k] = (int16_t)lrintf(g_bptr[c][i][k] * 1000.0f);
                for (int k = 3; k < 7; k++) q[k] = (int16_t)lrintf(g_bptr[c][i][k] * 32767.0f);
            }
            memcpy(e + 1, q, 14);
            g_bptr_dirty[c][i] = 0;
        }
        b[4] = (uint8_t)n;
        g_send_tramp(MSG_BACKPACK, b, (uint64_t)(6 + n * 15), 0xff);
        return 1;
    }
    return 0;
}
static void bptr_net_recv(int s, const uint8_t *b, uint64_t len) {
    if (len < 6 || b[1] < 1 || b[1] >= BPT_NC) return;
    int c = b[1], i0 = b[2] | (b[3] << 8), n = b[4];
    if (len < (uint64_t)(6 + n * 15) || i0 + n > BPT_N) return;
    for (int j = 0; j < n; j++) {
        const uint8_t *e = b + 6 + j * 15; int16_t q[7]; memcpy(q, e + 1, 14);
        if (!e[0]) continue;
        float v[7];
        for (int k = 0; k < 3; k++) v[k] = q[k] / 1000.0f;
        for (int k = 3; k < 7; k++) v[k] = q[k] / 32767.0f;
        if (!bptr_valid(v)) continue;
        memcpy(g_bptrp[s][c][i0 + j], v, 28); g_bptrp_ok[s][c][i0 + j] = 1;
    }
    if (!g_bptr_nrx[s]++ || g_bptr_nrx[s] % 50 == 0) {
        int nn; bpt_complete(g_bptrp_ok[s][c], &nn);
        xlog("bptrack: slot %d root chunk %d (clip %d idx %d+%d, that clip now %d samples)", s, g_bptr_nrx[s], c, i0, n, nn);
    }
}
static void bptr_open_done(void) {
    int n[BPT_NC] = {0}, b = BPT_C(g_bpo.stance & 3, 0);
    for (int c = 1; c < BPT_NC; c++) { bpt_complete(g_bptr_ok[c], &n[c]); for (int i = 0; i < BPT_N; i++) if (g_bptr_ok[c][i]) g_bptr_dirty[c][i] = 1; }
    xlog("bptrack: own %s open root samples intro %d / loop %d / outro %d (%s root track now %d / %d / %d), saved to %s", BPS_NAME[g_bpo.stance & 3],
         g_bptr_open_n[b + 1], g_bptr_open_n[b + 2], g_bptr_open_n[b + 3], BPS_NAME[g_bpo.stance & 3], n[b + 1], n[b + 2], n[b + 3], BPTR_FILE);
    memset(g_bptr_open_n, 0, sizeof g_bptr_open_n);
    if (g_bptr_live) bptr_save();
}
// own close: log what this open recorded, save it, resend the whole track (lost chunks, late joiners)
static void bpt_open_done(void) {
    bpt_load_header();
    int n[BPT_NC] = {0}, b = BPT_C(g_bpo.stance & 3, 0);
    for (int c = 1; c < BPT_NC; c++) { bpt_complete(g_bpt_ok[c], &n[c]); for (int i = 0; i < BPT_N; i++) if (g_bpt_ok[c][i]) g_bpt_dirty[c][i] = 1; }
    xlog("bptrack: own %s open recorded intro %d / loop %d / outro %d samples (%s track now %d / %d / %d), saved to %s, resending to the peers", BPS_NAME[g_bpo.stance & 3],
         g_bpt_open_n[b + 1], g_bpt_open_n[b + 2], g_bpt_open_n[b + 3], BPS_NAME[g_bpo.stance & 3], n[b + 1], n[b + 2], n[b + 3], BPT_FILE);
    memset(g_bpt_open_n, 0, sizeof g_bpt_open_n);
    if (g_bpt_live) bpt_save();
    bptr_open_done();
}
static int bpt_rec_on(void) {
    static int v = -1; static uint64_t at;
    uint64_t n = GetTickCount64();
    if (v < 0 || n - at > 3000) { at = n; FILE *f = exe_side_open("t2r-bp-record.txt", "r"); v = f != NULL; if (f) fclose(f); }
    return v;
}
static int bpt_off(void) { static int v = -1; if (v < 0) { FILE *f = exe_side_open("t2r-no-bp-track.txt", "r"); v = f != NULL; if (f) fclose(f); } return v; }
// the row this open is writing and its contents before this open's first sample in it: bpt_rec_abort puts them back
static int g_bpt_snap_row = -1; static double g_bpt_snap_t;
static float g_bpt_snap[BPT_N][3], g_bptr_snap[BPT_N][7]; static uint8_t g_bpt_snap_ok[BPT_N], g_bptr_snap_ok[BPT_N];
static void bpt_snap_take(int row, double t_phase) {
    if (row == g_bpt_snap_row && t_phase == g_bpt_snap_t) return;
    g_bpt_snap_row = row; g_bpt_snap_t = t_phase;
    memcpy(g_bpt_snap, g_bpt[row], sizeof g_bpt_snap); memcpy(g_bpt_snap_ok, g_bpt_ok[row], sizeof g_bpt_snap_ok);
    memcpy(g_bptr_snap, g_bptr[row], sizeof g_bptr_snap); memcpy(g_bptr_snap_ok, g_bptr_ok[row], sizeof g_bptr_snap_ok);
}
static void bpt_rec_abort(const char *why, double now) {
    if (g_bpo.rec_stop) return;
    g_bpo.rec_stop = 1;
    int row = g_bpt_snap_row, n = row >= 1 && row < BPT_NC ? g_bpt_open_n[row] : 0;
    if (n > 0) {
        memcpy(g_bpt[row], g_bpt_snap, sizeof g_bpt_snap); memcpy(g_bpt_ok[row], g_bpt_snap_ok, sizeof g_bpt_snap_ok);
        memcpy(g_bptr[row], g_bptr_snap, sizeof g_bptr_snap); memcpy(g_bptr_ok[row], g_bptr_snap_ok, sizeof g_bptr_snap_ok);
        for (int i = 0; i < BPT_N; i++) { g_bpt_dirty[row][i] = g_bpt_ok[row][i]; g_bptr_dirty[row][i] = g_bptr_ok[row][i]; }
        g_bpt_open_n[row] = 0; g_bptr_open_n[row] = 0;
    }
    xlog("bptrack: own recording paused (%s, %s %.0f ms in): %d samples of track row %d dropped (the row is back to before this open)",
         why, BPP_NAME[g_bpo.phase & 3], now - g_bpo.t_phase, n, row);
}
// our side: sample (called every frame from bp_own_tick)
static void bpt_own_sample(double now) {
    if ((g_bpo.phase != BPP_OPEN && g_bpo.phase != BPP_CLOSING) || !g_bp_hid || bpt_off() || g_bpo.rec_stop) return;
    bp_state_t bs = bp_state();
    if (!bs.ctrl || bs.vis != 1 || IsBadReadPtr(bs.ctrl + 0x198, 8)) return;
    uint8_t *hh = *(uint8_t **)(bs.ctrl + 0x198), *pr = (hh && !IsBadReadPtr(hh, 16)) ? *(uint8_t **)(hh + 8) : NULL;
    uint64_t ph = (pr && !IsBadReadPtr(pr, 0xd0)) ? *(uint64_t *)(pr + 0xc0) : 0;
    if (!ph) return;
    double el = now - g_bpo.t_phase; int clip; double ms; int st = g_bpo.stance & 3;
    if (g_bpo.phase == BPP_CLOSING) { clip = BPC_OUTRO; ms = el; }
    else if (g_bpo.rec_loop_t0 > 0) { clip = BPC_LOOP; ms = fmod(now - g_bpo.rec_loop_t0, BPS_LOOP_MS[st]); }   // stance changed while open: the new stance's loop
    else if (el < BPS_INTRO_MS[st]) { clip = BPC_INTRO; ms = el; }
    else { clip = BPC_LOOP; ms = fmod(el - BPS_INTRO_MS[st], BPS_LOOP_MS[st]); }
    clip = BPT_C(st, clip);                  // the stance's own track row (stand = the old rows 1..3)
    float lb[16]; const float *loc = player_locator(lb);
    float pj[3], pq[4];
    if (!loc || !xbx_loc(ph, "spinec", pj, pq)) return;
    float yw = 2.0f * atan2f(loc[5], loc[7]), cs = cosf(yw), sn = sinf(yw);
    float dx = pj[0] - loc[0], dz = pj[2] - loc[2];
    float r[3] = {dx * cs - dz * sn, pj[1] - loc[1], dx * sn + dz * cs};
    if (fabsf(r[0]) > 3.0f || fabsf(r[1]) > 3.0f || fabsf(r[2]) > 3.0f) return;
    int i = (int)(ms / BPT_DT + 0.5); if (i < 0 || i >= BPT_N) return;
    bpt_load_header();
    bpt_snap_take(clip, g_bpo.t_phase);
    memcpy(g_bpt[clip][i], r, 12); g_bpt_ok[clip][i] = 1; g_bpt_live++; g_bpt_dirty[clip][i] = 1; g_bpt_open_n[clip]++;
    bptr_own_sample(pr, loc, clip, i);
    if (bpt_rec_on()) xlog("bptrack: clip %d idx %d rel %.4f %.4f %.4f look %s", clip, i, r[0], r[1], r[2], look_name(bp_player_look(bp_me())));
}
// the player's states (dc1/anim-player/player-inventory2.bin): inventory-intro = stand^craft-intro, inventory-loop =
// crouch-craft-idle, inventory-outro = stand^craft-outro (character column; the prop column is backpack-*). The puppet
// resolves the overlay name itself; first clip its anim tables know (get-animation-duration > 0) wins, logged.
// one set per stance (the owner's stance from MSG_BACKPACK; see the head of this file). A stance whose intro the puppet's tables do not
// know falls back to the standing set (logged once per slot and stance).
static const char *const BP_CLIPS[BPS_N][4][4] = {
    {{NULL},
     {"abby-stand^craft-intro", "stand^craft-intro", "abby-lg-stand^craft-intro", "lg-stand^craft-intro"},
     {"abby-crouch-craft-idle", "crouch-craft-idle", NULL, NULL},
     {"abby-stand^craft-outro", "stand^craft-outro", "abby-lg-stand^craft-outro", "lg-stand^craft-outro"}},
    {{NULL},
     {"abby-crouch-craft-intro", "crouch-craft-intro", "abby-lg-crouch-craft-intro", "lg-crouch-craft-intro"},
     {"abby-crouch-craft-idle", "crouch-craft-idle", NULL, NULL},
     {"abby-crouch-craft-outro", "crouch-craft-outro", "abby-lg-crouch-craft-outro", "lg-crouch-craft-outro"}},
    {{NULL},
     {"abby-prone-craft-intro", "prone-craft-intro", NULL, NULL},
     {"abby-prone-craft-idle", "prone-craft-idle", NULL, NULL},
     {"abby-prone-craft-outro", "prone-craft-outro", NULL, NULL}},
    {{NULL},
     {"abby-supine-craft-intro", "supine-craft-intro", "abby-lg-supine-craft-intro", "lg-supine-craft-intro"},
     {"abby-supine-craft-idle", "supine-craft-idle", NULL, NULL},
     {"abby-supine-craft-outro", "supine-craft-outro", "abby-lg-supine-craft-outro", "lg-supine-craft-outro"}}};
#define BPP_BLEND 0.25f
static struct {
    int phase;                      // the owner's last phase
    uint8_t seq; double rx_ms;      // last message (bp_ms)
    double ct_rx;                   // the owner's clip time (ms in phase) at rx, latency-corrected
    int clip; double t0; float dur; // playing clip, its time 0 (bp_ms), length (s)
    int stance;                     // the owner's stance (BPS_*, last message)
    int cst;                        // the stance of the clip that plays (= stance, or BPS_STAND when the puppet has no clips of that stance)
    uint64_t st_h; int8_t st_ok[BPS_N]; // per puppet body: that stance's intro is known (1) / not (0) / not probed (-1 after a body change)
    const char *name;
    uint64_t h;                     // puppet handle the clip runs on
    int warned_none;
    int want_off;                   // the owner's last bagoff
    int pmode;                      // 1 = animated TAB prop look, 2 = rigid per-look bag, 3 = satchel (hand follow)
    int off;                        // 1 = we took this puppet's worn bag off and hold the prop
    uint64_t prop;                  // held bag prop object (0 = none)
    int path; double probe_t; float lid0[3];  // joint probe of the waiting prop
    uint8_t *proc;                  // its ProcessBackpack (only while the prop waits for its clips)
    uint8_t was_vis[BP_NPARTS];     // worn parts shown at the take-off
    float floor_pos[3]; int floor_ok;   // where the bag rests during the crouch loop
    int tsrc, tsrc_clip; double tsrc_t0;     // track replay: source latched at the clip start (0 none = spinec follow, 1 the owner's track, 2 our own)
    int rsrc, rsrc_clip; double rsrc_t0;     // root track replay: the same, for the root track (preferred over the spinec track)
    int ready; double t_off, enter_pred;     // prop spawned + animating early, waiting for the swap moment; when the puppet's bag went off; the owner's swap clip time
    float last_set[3]; uint64_t last_prop;   // track replay: where we put the prop last frame (its spinec read then gives the clip's own offset)
    float bpoff[3]; int bpoff_st;      // open-offset fix: constant world correction (body spinec - prop spinec at the first clip frame), 0 = unmeasured, 1 = applied, 2 = off/unreadable
    double t_hide, t_proof;         // last re-assert of the hidden parts / last proof log
} g_bpp[T2R_MAX_PEERS];
static uint64_t bp_puppet(int slot) {
    typedef uint8_t *(*fn_peer)(uint32_t);
    uint8_t *peer = slot >= 0 && slot < T2R_MAX_PEERS ? ((fn_peer)t2r_peer)((uint32_t)slot) : NULL;
    return peer && !IsBadReadPtr(peer + 0x60, 8) ? *(uint64_t *)(peer + 0x60) : 0;
}

// ---- the puppet's bag off / held prop
static int bp_pup_off_disabled(void) {
    static int v = -1;
    if (v < 0) { FILE *f = exe_side_open("t2r-no-puppet-bag-off.txt", "r"); v = f != NULL; if (f) fclose(f); }
    return v;
}
static void bp_prop_pose(uint64_t o, const float *pos, const float *loc8) {
    static __attribute__((aligned(16))) psync_bf ring[8]; static unsigned n;
    psync_bf *bf = &ring[n++ & 7];
    float yaw = 2.0f * atan2f(loc8[5], loc8[7]);
    float a[7] = {pos[0], pos[1], pos[2], 0.0f, sinf(yaw * 0.5f), 0.0f, cosf(yaw * 0.5f)};
    psync_bf_make(bf, a);
    set_obj_loc(o, bf);
}
static void bp_pup_prop_kill(int s, int live) {
    if (g_bpp[s].prop && live) { uint64_t o = g_bpp[s].prop; dc_call(fnv64("kill-entity"), 1, &o); }
    g_bpp[s].prop = 0; g_bpp[s].floor_ok = 0; g_bpp[s].pmode = 0; g_bpp[s].bpoff_st = 0; g_bpp[s].ready = 0;
}
// bag back on the puppet: the parts that were shown at the take-off, the prop gone
static void bp_pup_bag_on(int s, uint64_t h, int live, const char *why) {
    if (!g_bpp[s].off && !g_bpp[s].prop) return;
    uint8_t *dc = live && h ? gvis_dc(h) : NULL;
    g_bp_pup_off[s] = 0;                       // the armour rig re-asserts its copy / original pair from here
    if (dc) for (int i = 0; i < BP_NPARTS; i++) if (g_bpp[s].was_vis[i]) bp_dc_show(dc, g_bp_part_sid[i]);
    bp_pup_prop_kill(s, live);
    if (g_bpp[s].off) xlog("bp: slot %d puppet bag back on (%s) at t %.0f ms", s, why, bp_ms());
    g_bpp[s].off = 0;
}
// the puppet's look -> its pool row (FACTION_LOOKS / FACTION_LOOKS_WINTER, winter crew keep the base bag)
static const char *const BP_HB_ACTOR[2][8] = {
    {"mp-t2r-hb-sm000000", "mp-t2r-hb-sm000000", "mp-t2r-hb-sm000000", "mp-t2r-hb-sm000000", "mp-t2r-hb-sm000000", "mp-t2r-hb-sm000000", "mp-t2r-hb-sf00000000", "mp-t2r-hb-sf00000000"},
    {"mp-t2r-hb-m1100000000000", "mp-t2r-hb-m0800000000000", "mp-t2r-hb-m1200000000000", "mp-t2r-hb-m0500000000000", "mp-t2r-hb-m1300000000000", "mp-t2r-hb-m1400000000000",
     "mp-t2r-hb-f130000000000000", "mp-t2r-hb-f120000000000000"}};
static int bp_pup_row(int s, int *pool, int *idx) {
    const char *ls = g_fl_spawn_str[s];
    if (!ls[0]) return 0;
    for (int t = 0; t < 2; t++)
        for (int i = 0; i < FL_N && i < 8; i++) {
            const char *a = FACTION_LOOKS[t][i], *b = FACTION_LOOKS_WINTER[t][i];
            if ((a && !strncmp(ls, a, strlen(a))) || (b && !strncmp(ls, b, strlen(b)))) { *pool = t; *idx = i; return 1; }
        }
    return 0;
}
static const char *bp_prop_look_of(int pool, int idx) {
    bp_tables();
    for (int i = 0; i < BP_NPROP; i++) if (!strcmp(BP_PROP_LOOKS[i][0], FACTION_LOOKS[pool][idx])) return (g_bp_always[i] || g_bp_fl_on) ? BP_PROP_LOOKS[i][1] : NULL;
    return NULL;
}
static uint64_t bp_spawn_prop(const char *art) {
    uint64_t a[9] = {fnv64(art), fnv64("SimpleAttachable"), 0, 0, 1, 0, 0, 0, 0};
    uint64_t o = dc_call(fnv64("spawn-object"), 9, a);
    return o && o != ~0ULL ? o : 0;
}
// THE REAL THING (a SimpleAttachable spawned from a look name has no anim set - "plays no backpack-intro"): the engine's own prop spawn
// for the local player, exe 0x140afd7f0 (PlayerBackpackAnimCtrl, this = controller: +0x118 player, +0x190 pending, +0x198 prop handle ptr, +0x1a0 gen;
// rdx = the player's world locator, 32 bytes). It builds a ProcessBackpack spawn (art group at [rsp+0x198]: our detour bp_pick answers g_bp_spawn_art),
// spawns it (0x1414cd790), sends it set-parent(player) + the hide message and stores the handle at ctrl+0x198. Run here on a COPY of our own controller (so
// the player behind +0x118 is a real Player: the vfuncs +0xb18 / +0x3a8 / +0x390 and the parent link are valid; our real controller's state is untouched)
// with the puppet's locator. The prop is then not the puppet's - it is parented to our body - but the puppet never drives it either way: we set its
// locator on the puppet every frame and play backpack-intro / -loop / -outro on it ourselves (it has the backpack-abby skeleton + anim set, which the
// SimpleAttachable did not). ShowObject (0xc2f7fb66d732410b, what EnterBackpack sends) makes it visible.
typedef void (*fn_bp_real_spawn)(void *ctrl, const float *loc8);
typedef void *(*fn_bp_send)(void *, void *, uint64_t, void *, void *, void *, void *, void *);
static uint64_t bp_spawn_real(const float *loc8, uint64_t art, uint8_t **proc_out) {
    static __attribute__((aligned(32))) uint8_t cc[0x300];
    uint8_t *me = bp_me(), *c = me ? bp_ctrl_of(me) : NULL;
    if (!c || IsBadReadPtr(c, 0x1f0)) return 0;
    memcpy(cc, c, 0x1f0);
    *(uint64_t *)(cc + 0x198) = 0; *(uint32_t *)(cc + 0x1a0) = 0;
    cc[0x190] = 1;
    __attribute__((aligned(32))) float lc[8];
    memcpy(lc, loc8, 32);
    uint8_t *exe = (uint8_t *)GetModuleHandleW(NULL);
    g_bp_spawn_art = art ? art : fnv64("backpack-abby");
    ((fn_bp_real_spawn)(exe + 0xafd7f0))(cc, lc);
    g_bp_spawn_art = 0;
    uint8_t *slot = *(uint8_t **)(cc + 0x198);
    if (!slot || IsBadReadPtr(slot, 16)) return 0;
    uint8_t *proc = *(uint8_t **)(slot + 8);
    if (!proc || IsBadReadPtr(proc, 0xd0) || *(uint32_t *)(proc + 0x94) != *(uint32_t *)(cc + 0x1a0)) return 0;
    *proc_out = proc;
    if (*(uint8_t **)(proc + 0x80) != slot) xlog("bp: spawned prop process %p: proc+0x80 %p is not its handle slot %p (events would be dropped)", (void *)proc, *(void **)(proc + 0x80), (void *)slot);
    return *(uint64_t *)(proc + 0xc0);
}
static void bp_send_msg2(uint8_t *proc, uint64_t msg, void *arg) {
    static __attribute__((aligned(16))) uint8_t z[6][16], tgt[16], out[0x40];
    // (B crashed twice at exe+1573557 = the event sender's slot read `mov rdi,[rdi+8]`, right after "bp: ... path A ... shown"):
    // the cached process pointer can be stale (the prop process freed / its memory reused), so proc+0x80 held garbage. Send only when
    // the process still owns its handle slot (slot readable and slot+8 points back at this process), else drop the message.
    if (!proc || IsBadReadPtr(proc, 0xd0)) return;
    uint8_t *slot = *(uint8_t **)(proc + 0x80);
    if (!slot || IsBadReadPtr(slot, 16) || *(uint8_t **)(slot + 8) != proc || !*(uint32_t *)(proc + 0x94)) {
        static int nl; if (nl < 20) { nl++; xlog("bp: event %llx to a stale prop process %p dropped (slot %p)", (unsigned long long)msg, (void *)proc, (void *)slot); }
        return;
    }
    memset(z, 0, sizeof z); memset(out, 0, sizeof out);
    *(uint64_t *)tgt = *(uint64_t *)(proc + 0x80); *(uint32_t *)(tgt + 8) = *(uint32_t *)(proc + 0x94); *(uint32_t *)(tgt + 12) = 0;
    ((fn_bp_send)((uint8_t *)GetModuleHandleW(NULL) + 0x15734d0))(out, z[0], msg, tgt, arg ? arg : z[1], z[2], z[3], z[4]);
}
static void bp_send_msg(uint8_t *proc, uint64_t msg) { bp_send_msg2(proc, msg, NULL); }
// the spawn parents the prop to our player (set-parent 0xe93d6ecbdf018772, argument built by 0x1414cfc60 from the player's handle): so that the prop's per-frame
// update never reads OUR backpack state, the same message again with a null handle
static void bp_prop_unparent(uint8_t *proc) {
    typedef void *(*fn_harg)(void *, void *);
    static __attribute__((aligned(16))) uint8_t nul[16], arg[0x20];
    memset(nul, 0, sizeof nul); memset(arg, 0, sizeof arg);
    ((fn_harg)((uint8_t *)GetModuleHandleW(NULL) + 0x14cfc60))(arg, nul);
    bp_send_msg2(proc, 0xe93d6ecbdf018772ULL, arg);
}
// path B (night26 RE: the player state graph's prop column - inventory-intro/loop/outro -> backpack-intro/loop/outro - drives the ProcessBackpack through its PARENT: the
// prop handler 0x141158d00 stores set-parent's target at +0x600 and the prop reads that parent's state through its vfunc +0x870; bp_prop_unparent removed that link): the same
// set-parent message with the PUPPET as the target (handle = {proc+0x80, proc+0x94}, what the engine builds for the player at 0x140afda6b)
static int bp_prop_parent_puppet(uint8_t *proc, uint64_t puppet_h) {
    typedef void *(*fn_harg)(void *, void *);
    typedef uint8_t *(*fn_proc)(uint64_t);
    static __attribute__((aligned(16))) uint8_t tgt[16], arg[0x20];
    uint8_t *pp = puppet_h ? ((fn_proc)VMA(0x18000A200))(puppet_h) : NULL;
    if (!pp || IsBadReadPtr(pp, 0xa0) || !proc || IsBadReadPtr(proc, 0xd0)) return 0;
    memset(tgt, 0, sizeof tgt); memset(arg, 0, sizeof arg);
    *(uint64_t *)tgt = *(uint64_t *)(pp + 0x80); *(uint32_t *)(tgt + 8) = *(uint32_t *)(pp + 0x94);
    ((fn_harg)((uint8_t *)GetModuleHandleW(NULL) + 0x14cfc60))(arg, tgt);
    bp_send_msg2(proc, 0xe93d6ecbdf018772ULL, arg);
    return 1;
}
static int bp_parent_optout(void) {
    static int v = -1;
    if (v < 0) { FILE *f = exe_side_open("t2r-no-puppet-bag-parent.txt", "r"); v = f != NULL; if (f) fclose(f); }
    return v;
}
static int bp_rigid_optin(void) {
    static int v = -1;
    if (v < 0) { FILE *f = exe_side_open("t2r-puppet-bag-rigid.txt", "r"); v = f != NULL; if (f) fclose(f); }
    return v;
}
// the animated prop sits on the puppet's locator (its bind space is the character space)
static void bp_prop_on_body(uint64_t o, const float *loc8) {
    static __attribute__((aligned(16))) psync_bf ring[8]; static unsigned n;
    psync_bf *bf = &ring[n++ & 7];
    psync_bf_from_loc(bf, loc8);
    set_obj_loc(o, bf);
}
// THE PROP'S CLIP NAMES (night26 RE): the state graph's prop column says "backpack-intro/loop/outro" (player-inventory2.bin +0x28) but those sids are resolved
// through the player's anim overlay; no such clip is in any table (get-animation-duration read 0.00 s for 2 s on the prop, so animate_ on them cannot work).
// The real clips are in sp-common's anim-abby-player-backpack.pak (already loaded: the own body plays its abby-* craft clips from it) as "<character clip>--backpack"
// (abby-stand^craft-intro--backpack, abby-crouch-craft-idle--backpack, abby-stand^craft-outro--backpack, ...), authored for the backpack-abby skeleton.
// The first candidate the prop's get-animation-duration knows wins (logged once per slot and clip); none known = the first one is tried anyway.
static const char *bp_prop_clip_name(int s, int clip, uint64_t prop) {
    static char cache[T2R_MAX_PEERS][BPS_N][4][96]; static char cand[96];
    clip &= 3;
    if (!clip) return NULL;
    int st = g_bpp[s].cst & 3;
    if (cache[s][st][clip][0]) return cache[s][st][clip];
    // the stance's own prop clip (anim-abby-player-backpack.pak: every stance clip has its "--backpack" twin), then the old standing names
    static const char *const FS[BPS_N][4] = {
        {NULL, "abby-stand^craft-intro--backpack", "abby-crouch-craft-idle--backpack", "abby-stand^craft-outro--backpack"},
        {NULL, "abby-crouch-craft-intro--backpack", "abby-crouch-craft-idle--backpack", "abby-crouch-craft-outro--backpack"},
        {NULL, "abby-prone-craft-intro--backpack", "abby-prone-craft-idle--backpack", "abby-prone-craft-outro--backpack"},
        {NULL, "abby-supine-craft-intro--backpack", "abby-supine-craft-idle--backpack", "abby-supine-craft-outro--backpack"}};
    static const char *const FB[4][4] = {{NULL}, {"abby-stand^craft-intro--backpack", "abby-crouch-craft-intro--backpack", "backpack-intro", NULL},
        {"abby-crouch-craft-idle--backpack", "abby-crouch-craft-generic^idle--backpack", "backpack-loop", NULL}, {"abby-stand^craft-outro--backpack", "abby-crouch-craft-outro--backpack", "backpack-outro", NULL}};
    const char *list[8]; int n = 0;
    static char own[96];
    // (the -lg- body clips have no --backpack twin: their prop clip is the plain stance one)
    if (clip == (g_bpp[s].clip & 3) && g_bpp[s].name && strlen(g_bpp[s].name) < 80 && !strstr(g_bpp[s].name, "-lg-")) { snprintf(own, sizeof own, "%s--backpack", g_bpp[s].name); list[n++] = own; }
    if (!n || strcmp(own, FS[st][clip])) list[n++] = FS[st][clip];
    for (int i = 0; FB[clip][i]; i++) if (strcmp(FB[clip][i], FS[st][clip])) list[n++] = FB[clip][i];
    const char *pick = NULL;
    for (int i = 0; i < n; i++) {
        float L = anim_len(prop, list[i]);
        xlog("bp: slot %d prop clip candidate %s: duration %.2f s%s", s, list[i], L, L > 0 ? " - USED" : "");
        if (L > 0) { pick = list[i]; break; }
    }
    if (!pick) { pick = list[0]; xlog("bp: slot %d no prop clip candidate has a duration - trying %s anyway", s, pick); }
    snprintf(cand, sizeof cand, "%s", pick);
    strcpy(cache[s][st][clip], cand);
    xlog("bp: slot %d %s prop clip for the %s %s: %s", s, BPS_NAME[st], BPS_NAME[st], BPC_NAME[clip], cand);
    return cache[s][st][clip];
}
// prop clip in step with the puppet's craft clip `clip` at phase ph
static void bp_prop_clip(int s, int clip, float ph, float blend) {
    if (g_bpp[s].pmode != 1 || !g_bpp[s].prop || !(clip & 3)) return;
    const char *nm = bp_prop_clip_name(s, clip, g_bpp[s].prop);
    uint64_t r = animate_from(g_bpp[s].prop, nm, blend, ph);
    static int nl; if (nl < 40) { nl++; xlog("bp: slot %d bag prop %s from phase %.2f blend %.2f -> %llx", s, nm, ph, blend, (unsigned long long)r); }
}
// the owner took the bag off: the prop first, then the worn parts go (no prop = no change)
// go = 0: get the prop ready (spawned, its clip taking) but keep the worn bag on; go = 1: the swap
static void bp_pup_bag_off(int s, uint64_t h, double now, int go) {
    static int bad, abad;
    uint8_t *dc = gvis_dc(h);
    if (!dc || bad >= 3) return;
    float hp[3], hq[4], lb[16];
    const float *loc = puppet_locator(h, lb);
    if (!loc) return;
    int pool = 0, idx = 0, row = bp_pup_row(s, &pool, &idx);
    const char *plook = row ? bp_prop_look_of(pool, idx) : NULL;
    uint64_t o = 0; int mode = 0;
    if (abad < 3) {
        if (!g_bpp[s].clip) return;                       // the craft clip has not started here yet: the prop would stand in its bind pose
        if (g_bpp[s].prop) {                              // spawned on an earlier tick, hidden, waiting for the clips to take
            o = g_bpp[s].prop;
            // (get-animation-duration is a character-clip query: it read 0.00 s on this prop for 2 s in the night26 logs, so it is no gate. The gate is the clip itself:
            // animate_ answers a live layer and the prop's joints are readable. Until then the prop stays HIDDEN - shown unanimated it stands in its bind pose at shoulder height beside the puppet = a second bag)
            float jp[3] = {g_bpp[s].lid0[0], g_bpp[s].lid0[1], g_bpp[s].lid0[2]}, jq[4];
            uint64_t r = 0; int moved = g_bpp[s].ready;
            if (!moved && g_bpp[s].probe_t > 0 && now - g_bpp[s].probe_t >= 66.0 && xbx_loc(o, "lid_a", jp, jq)) {      // the pose of the clip put on 66 ms (4 frames) ago: did a joint move?
                float d = fabsf(jp[0] - g_bpp[s].lid0[0]) + fabsf(jp[1] - g_bpp[s].lid0[1]) + fabsf(jp[2] - g_bpp[s].lid0[2]);
                moved = d > 0.003f; r = 1;
                if (!moved) g_bpp[s].probe_t = 0;
            }
            if (!moved && g_bpp[s].probe_t <= 0) {
                { g_bpp[s].prop = o; r = animate_from(o, bp_prop_clip_name(s, BPC_INTRO, o), 0.0f, 0.5f); g_bpp[s].prop = o; }
                if (r && r != ~0ULL && xbx_loc(o, "lid_a", jp, jq)) { memcpy(g_bpp[s].lid0, jp, 12); g_bpp[s].probe_t = now; }
            }
            if (!moved && g_bpp[s].path == 0 && now - g_bpp[s].t_proof >= 700.0 && !bp_parent_optout()) {      // path A (animate_ on the unparented prop) did not move a joint: path B, the puppet as its parent
                g_bpp[s].path = bp_prop_parent_puppet(g_bpp[s].proc, h) ? 2 : 1;
                g_bpp[s].probe_t = 0;
                xlog("bp: slot %d path A (animate_ on the unparented prop) moved nothing in %.0f ms - %s", s, now - g_bpp[s].t_proof, g_bpp[s].path == 2 ? "path B: the prop now has the puppet as its parent (set-parent), probing again" : "path B not possible (no puppet process)");
            }
            if (moved && !go) {          // ready before the swap moment: hidden on the body until then
                if (!g_bpp[s].ready) xlog("bp: slot %d prop ready (its clip took after %.0f ms), waiting for the swap at clip %.0f ms", s, now - g_bpp[s].t_proof, g_bpp[s].enter_pred);
                g_bpp[s].ready = 1;
                bp_prop_on_body(o, loc);
                return;
            }
            if (moved) {
                g_bpp[s].ready = 0;
                xlog("bp: slot %d real prop took its craft clip via path %s after %.0f ms (lid_a moved %.3f m) - shown", s, g_bpp[s].path == 2 ? "B (puppet parent)" : "A (animate_ direct)", now - g_bpp[s].t_proof, (double)(fabsf(jp[0] - g_bpp[s].lid0[0]) + fabsf(jp[1] - g_bpp[s].lid0[1]) + fabsf(jp[2] - g_bpp[s].lid0[2])));
                {   // (bystanders: 'the backpack just disappears'): the stale-process guard dropped EVERY ShowObject ('event c2f7fb66 to a stale prop process
                    // ... dropped (slot 0)') - the spawn-time process pointer is stale by now, so the opened bag was never shown. Resolve the live process from the prop's handle.
                    typedef uint8_t *(*fn_proc2)(uint64_t);
                    uint8_t *pp = ((fn_proc2)VMA(0x18000A200))(o);
                    if (pp && !IsBadReadPtr(pp, 0xd0) && *(uint64_t *)(pp + 0xc0) == o) g_bpp[s].proc = pp;
                    else xlog("bp: slot %d prop handle %llx did not resolve to a live process (cached %p)", s, (unsigned long long)o, (void *)g_bpp[s].proc);
                    if (g_bpp[s].proc && !IsBadReadPtr(g_bpp[s].proc, 0xd0)) bp_send_msg(g_bpp[s].proc, 0xc2f7fb66d732410bULL);     // ShowObject
                }
                {   // the art the shown prop really wears vs the puppet look's pick
                    uint64_t pa = obj_look(o), want = plook ? fnv64(plook) : 0;
                    xlog("bp: slot %d shown prop art %llx (%s), puppet look %s wants %s%s", s, (unsigned long long)pa, look_name(pa), g_fl_spawn_str[s], plook ? plook : "backpack-abby",
                         want && pa == want ? " - match" : " - MISMATCH");
                }
                mode = 1; g_bpp[s].prop = 0; g_bpp[s].probe_t = 0;
            } else if (now - g_bpp[s].t_proof < 2000.0) { bp_prop_on_body(o, loc); return; }
            else { xlog("bp: slot %d the real prop never animated (lid_a did not move) in 2 s (animate_ %llx, try %d) - killed, the bag stays on the back", s, (unsigned long long)r, ++abad); dc_call(fnv64("kill-entity"), 1, &o); o = 0; g_bpp[s].prop = 0; g_bpp[s].probe_t = 0; }
        } else {
        uint8_t *proc = NULL;
        o = bp_spawn_real(loc, plook ? fnv64(plook) : 0, &proc);      // the puppet look's own TAB prop art (BP_PROP_LOOKS, the pick bp_pick makes for our look), else backpack-abby
        if (o) {
            bp_prop_unparent(proc);
            xlog("bp: slot %d real ProcessBackpack (art %s, parent cleared) spawned hidden: proc %p handle %llx", s, plook ? plook : "backpack-abby", (void *)proc, (unsigned long long)o);
            g_bpp[s].prop = o; g_bpp[s].proc = proc; g_bpp[s].t_proof = now; g_bpp[s].probe_t = 0; g_bpp[s].pmode = 0; g_bpp[s].path = 0;
            bp_prop_on_body(o, loc);
            return;
        } else xlog("bp: slot %d real ProcessBackpack spawn gave no object (try %d) - the bag stays on the back", s, ++abad);
        }
    }
    if (!mode && bp_rigid_optin()) {                      // (opt-in only, t2r-puppet-bag-rigid.txt: night21 showed the rigid bag floating at hip height)
        if (!xbx_loc(h, "r_hand_prop_attachment", hp, hq)) return;
        const char *art = row ? BP_HB_ACTOR[pool][idx] : ISP_SAT_ACTOR;
        o = bp_spawn_prop(art);
        if (o) mode = row ? 2 : 3;
        if (!o) { xlog("bp: slot %d rigid bag prop %s failed (try %d)", s, art, ++bad); return; }
    }
    if (!mode) return;                                    // nothing animated: the worn bag stays on the back (old behaviour)
    g_bpp[s].prop = o; g_bpp[s].pmode = mode; g_bpp[s].floor_ok = 0; g_bpp[s].bpoff_st = 0;
    if (mode == 1) {
        bp_prop_on_body(o, loc);
        double el = now - g_bpp[s].t0;
        float ph = g_bpp[s].dur > 0 ? (float)(el / (g_bpp[s].dur * 1000.0)) : 0.0f;
        ph -= (float)(int)ph; if (ph > 0.98f) ph = 0.98f; if (ph < 0) ph = 0;
        bp_prop_clip(s, g_bpp[s].clip, ph, 0.0f);
    } else {
        hp[1] -= 0.45f;      // the bag hangs from the hand (origin = underside)
        bp_prop_pose(o, hp, loc);
    }
    for (int i = 0; i < BP_NPARTS; i++) {
        if (!g_bp_part_sid[i]) g_bp_part_sid[i] = fnv64(BP_PARTS[i]);
        int ix = bp_dc_find(dc, g_bp_part_sid[i]);
        g_bpp[s].was_vis[i] = ix >= 0 && !bp_dc_hidden(dc, ix);
        if (ix >= 0) bp_dc_hide(dc, g_bp_part_sid[i]);
    }
    g_bp_pup_off[s] = 1; g_bpp[s].off = 1; g_bpp[s].t_hide = now; g_bpp[s].t_off = now;
    xlog("bp: slot %d puppet bag OFF at t %.0f ms - worn parts hidden, %s %llx (look %s)", s, now,
         mode == 1 ? "animated bag (TAB prop look, clips in step)" : mode == 2 ? "rigid per-look bag at the hand" : "satchel at the hand", (unsigned long long)o, g_fl_spawn_str[s]);
}
// The animated bag was offset from where the worn bag was (a pop): measure at the first clip frame the world delta between the body's spinec (the worn bag
// rides it) and the prop's spinec (root as fallback), log it ("backpack: open offset ..."), and keep it as a constant correction on the prop's locator for the whole clip.
// Clamped to 15 cm. t2r-no-bp-offset-fix.txt = off (measure + log only).
static int bp_offfix_off(void) {
    static int v = -1;
    if (v < 0) { FILE *f = exe_side_open("t2r-no-bp-offset-fix.txt", "r"); v = f != NULL; if (f) fclose(f); }
    return v;
}
static void bp_pup_open_offset(int s, uint64_t h, const float *loc, double now) {
    float c[16]; memcpy(c, loc, sizeof c);
    {   // root track (see bptr_*): prop root = body locator * owner's recorded root-relative locator at the puppet's own clip time, open loop
        int cl = g_bpp[s].clip ? BPT_C(g_bpp[s].cst & 3, g_bpp[s].clip & 3) : 0; double ems = now - g_bpp[s].t0;   // the track row of the stance that plays
        if (g_bpp[s].clip == BPC_LOOP && g_bpp[s].dur > 0) ems = fmod(ems, g_bpp[s].dur * 1000.0);
        if (cl >= 1 && cl < BPT_NC && (g_bpp[s].rsrc_clip != cl || g_bpp[s].rsrc_t0 != g_bpp[s].t0)) {
            bpt_load_header();
            int np = 0, nl = 0, pk = bpt_complete(g_bptrp_ok[s][cl], &np), lk = bpt_complete(g_bptr_ok[cl], &nl);
            g_bpp[s].rsrc = bpt_off() ? 0 : pk ? 1 : lk ? 2 : 0; g_bpp[s].rsrc_clip = cl; g_bpp[s].rsrc_t0 = g_bpp[s].t0;
            static int nlog;
            if (nlog < 60) { nlog++; xlog("bptrack: slot %d %s %s root source %s (owner's root track %d samples, own %d)", s, BPS_NAME[g_bpp[s].cst & 3], BPC_NAME[g_bpp[s].clip & 3],
                                          g_bpp[s].rsrc == 1 ? "OWNER ROOT" : g_bpp[s].rsrc == 2 ? "own root" : "none - spinec track / follow", np, nl); }
        }
        float r7[7]; int got = 0;
        if (cl >= 1 && cl < BPT_NC && g_bpp[s].rsrc == 1) got = bptr_get_t((const float (*)[7])g_bptrp[s][cl], g_bptrp_ok[s][cl], ems, r7);
        else if (cl >= 1 && cl < BPT_NC && g_bpp[s].rsrc == 2) got = bptr_get_t((const float (*)[7])g_bptr[cl], g_bptr_ok[cl], ems, r7);
        if (got) {
            float pw[3], q[4];
            qrotv(loc + 4, r7, pw);
            bp_qmul(loc + 4, r7 + 3, q);
            float qn = sqrtf(q[0] * q[0] + q[1] * q[1] + q[2] * q[2] + q[3] * q[3]);
            if (qn > 0.5f) {
                c[0] = loc[0] + pw[0]; c[1] = loc[1] + pw[1]; c[2] = loc[2] + pw[2]; c[3] = 1.0f;
                for (int k = 0; k < 4; k++) c[4 + k] = q[k] / qn;
                {   // proof every 250 ms: the prop spinec (pose of the last frame) vs the owner's recorded spinec path at that clip time, when one is there
                    static double tl[T2R_MAX_PEERS];
                    if (now - tl[s] >= 250.0) {
                        tl[s] = now; float tr[3], pj[3], pq[4], er = -1.0f;
                        int ht = g_bpp[s].rsrc == 1 ? bpt_get_t((const float (*)[3])g_bptp[s][cl], g_bptp_ok[s][cl], ems - 16.7, tr) : bpt_get(cl, ems - 16.7, tr);
                        if (ht && xbx_loc(g_bpp[s].prop, "spinec", pj, pq)) {
                            float yw = 2.0f * atan2f(loc[5], loc[7]), cs = cosf(yw), sn = sinf(yw);
                            float w[3] = {loc[0] + tr[0] * cs + tr[2] * sn, loc[1] + tr[1], loc[2] - tr[0] * sn + tr[2] * cs};
                            er = sqrtf((pj[0] - w[0]) * (pj[0] - w[0]) + (pj[1] - w[1]) * (pj[1] - w[1]) + (pj[2] - w[2]) * (pj[2] - w[2]));
                        }
                        xlog("bptrack: slot %d clip %d at %.0f ms (%s root): root rel %.3f %.3f %.3f, prop spinec off the owner's spinec path %.1f cm", s, cl, ems,
                             g_bpp[s].rsrc == 1 ? "owner" : "own", r7[0], r7[1], r7[2], er * 100.0f);
                    }
                }
                bp_prop_on_body(g_bpp[s].prop, c);
                return;
            }
        }
    }
    {   // replay of our own recorded open/close animation (bpt_*): prop spinec = body locator + R(yaw) * track(clip, clip time)
        float tr[3]; double ems = now - g_bpp[s].t0;
        if (g_bpp[s].clip == BPC_LOOP && g_bpp[s].dur > 0) ems = fmod(ems, g_bpp[s].dur * 1000.0);
        int cl = g_bpp[s].clip ? BPT_C(g_bpp[s].cst & 3, g_bpp[s].clip & 3) : 0;
        if (cl >= 1 && cl < BPT_NC && (g_bpp[s].tsrc_clip != cl || g_bpp[s].tsrc_t0 != g_bpp[s].t0)) {
            bpt_load_header();
            int np = 0, nl = 0, pk = bpt_complete(g_bptp_ok[s][cl], &np), lk = bpt_complete(g_bpt_ok[cl], &nl);
            g_bpp[s].tsrc = bpt_off() ? 0 : pk ? 1 : lk ? 2 : 0; g_bpp[s].tsrc_clip = cl; g_bpp[s].tsrc_t0 = g_bpp[s].t0;
            static int nlog;
            if (nlog < 60) { nlog++; xlog("bptrack: slot %d %s %s source %s (owner's track %d samples, own %d)", s, BPS_NAME[g_bpp[s].cst & 3], BPC_NAME[g_bpp[s].clip & 3],
                                          g_bpp[s].tsrc == 1 ? "OWNER TRACK" : g_bpp[s].tsrc == 2 ? "own track" : "none - spinec follow", np, nl); }
        }
        int got = 0;
        if (cl >= 1 && cl < BPT_NC && g_bpp[s].tsrc == 1) got = bpt_get_t((const float (*)[3])g_bptp[s][cl], g_bptp_ok[s][cl], ems, tr);
        else if (cl >= 1 && cl < BPT_NC && g_bpp[s].tsrc == 2) got = bpt_get(cl, ems, tr);
        if (got) {
            float yw = 2.0f * atan2f(loc[5], loc[7]), cs = cosf(yw), sn = sinf(yw), pj[3], pq[4];
            float w[3] = {loc[0] + tr[0] * cs + tr[2] * sn, loc[1] + tr[1], loc[2] - tr[0] * sn + tr[2] * cs};
            if (g_bpp[s].last_prop == g_bpp[s].prop && xbx_loc(g_bpp[s].prop, "spinec", pj, pq)) {
                for (int k = 0; k < 3; k++) c[k] = g_bpp[s].last_set[k] + w[k] - pj[k];
                float dx = c[0] - loc[0], dy = c[1] - loc[1], dz = c[2] - loc[2], dl = sqrtf(dx * dx + dy * dy + dz * dz);
                if (dl > 1.0f) for (int k = 0; k < 3; k++) c[k] = loc[k] + (c[k] - loc[k]) / dl;
            }
            memcpy(g_bpp[s].last_set, c, 12); g_bpp[s].last_prop = g_bpp[s].prop;
            {   // proof every 250 ms: the target vs where the prop spinec is now (set last frame), in cm
                static double tl[T2R_MAX_PEERS];
                if (now - tl[s] >= 250.0) {
                    tl[s] = now; float pj2[3], pq2[4], er = -1.0f;
                    if (xbx_loc(g_bpp[s].prop, "spinec", pj2, pq2)) er = sqrtf((pj2[0] - w[0]) * (pj2[0] - w[0]) + (pj2[1] - w[1]) * (pj2[1] - w[1]) + (pj2[2] - w[2]) * (pj2[2] - w[2]));
                    xlog("bptrack: slot %d clip %d at %.0f ms (%s): prop spinec -> body + track %.3f %.3f %.3f, off target %.1f cm", s, cl, ems,
                         g_bpp[s].tsrc == 1 ? "owner" : "own", tr[0], tr[1], tr[2], er * 100.0f);
                }
            }
            bp_prop_on_body(g_bpp[s].prop, c);
            return;
        }
    }
    if (g_bpp[s].bpoff_st == 0 && g_bpp[s].clip) {
        bp_prop_on_body(g_bpp[s].prop, loc);       // pose it uncorrected, then read the joints next tick
        g_bpp[s].bpoff_st = -1;
        return;
    }
    if (g_bpp[s].bpoff_st == -1) {
        float bp_[3], bq[4], pp[3], pq[4]; const char *jn = "spinec";
        int ok = xbx_loc(h, jn, bp_, bq) && xbx_loc(g_bpp[s].prop, jn, pp, pq);
        if (!ok) { jn = "root"; ok = xbx_loc(h, jn, bp_, bq) && xbx_loc(g_bpp[s].prop, jn, pp, pq); }
        if (ok) {
            float d[3] = {bp_[0] - pp[0], bp_[1] - pp[1], bp_[2] - pp[2]};
            float L = sqrtf(d[0] * d[0] + d[1] * d[1] + d[2] * d[2]);
            if (L > 0.15f) { float k = 0.15f / L; d[0] *= k; d[1] *= k; d[2] *= k; }
            { float yw = 2.0f * atan2f(loc[5], loc[7]), cs = cosf(yw), sn = sinf(yw);      // the prop root that puts the prop spinec on the body spinec, stored in the body's yaw frame (= the prop parented to the body joint with a fixed offset)
              float wx = loc[0] + d[0] - bp_[0], wz = loc[2] + d[2] - bp_[2];
              g_bpp[s].bpoff[0] = wx * cs - wz * sn; g_bpp[s].bpoff[2] = wx * sn + wz * cs; g_bpp[s].bpoff[1] = d[1]; }
            xlog("backpack: open offset slot %d joint %s: body %.3f %.3f %.3f prop %.3f %.3f %.3f delta %.3f %.3f %.3f (%.1f cm)%s", s, jn, bp_[0], bp_[1], bp_[2], pp[0], pp[1], pp[2], d[0], d[1], d[2], L * 100.0f, L > 0.15f ? " CLAMPED" : "");
            g_bpp[s].bpoff_st = bp_offfix_off() ? 2 : 1;
        } else { xlog("backpack: open offset slot %d unreadable (joint locators) - no correction", s); g_bpp[s].bpoff_st = 2; }
    }
    if (g_bpp[s].bpoff_st == 1) {
        // ROOT CAUSE night46 (bystander bag moved only up/down): the prop root was pinned to the network locator while the body's crouch lean (spine travel) is not in the bag clip.
        // The engine parents the prop to the body (set-parent -> follows the player); here the prop root is parented to the puppet's spinec joint: root xz = spinec xz + the fixed start offset (body yaw frame),
        // height = locator + the start delta; the clip plays on top. Bound to 0.6 m from the locator.
        float bj[3], bq[4];
        if (xbx_loc(h, "spinec", bj, bq)) {
            float yw = 2.0f * atan2f(loc[5], loc[7]), cs = cosf(yw), sn = sinf(yw);
            float x = bj[0] + g_bpp[s].bpoff[0] * cs + g_bpp[s].bpoff[2] * sn, z = bj[2] - g_bpp[s].bpoff[0] * sn + g_bpp[s].bpoff[2] * cs;
            float dx = x - loc[0], dz = z - loc[2], dl = sqrtf(dx * dx + dz * dz);
            if (dl > 0.6f) { x = loc[0] + dx * 0.6f / dl; z = loc[2] + dz * 0.6f / dl; }
            c[0] = x; c[2] = z;
        }
        c[1] += g_bpp[s].bpoff[1];
    }
    bp_prop_on_body(g_bpp[s].prop, c);
}
// every frame while off: animated = on the puppet's locator; rigid = hand (intro / outro) or floor (loop); the hidden parts re-asserted every 200 ms
static void bp_pup_bag_tick(int s, uint64_t h, double now) {
    float hp[3], hq[4], lb[16];
    const float *loc = puppet_locator(h, lb);
    if (!loc) return;
    if (g_bpp[s].pmode == 1) {
        bp_pup_open_offset(s, h, loc, now);
        if (now - g_bpp[s].t_proof >= 500.0) {          // proof the bag clip plays: expected clip phase + a prop joint that moves with it
            g_bpp[s].t_proof = now;
            float jp[3], jq[4], root[3] = {loc[0], loc[1], loc[2]};
            int okj = xbx_loc(g_bpp[s].prop, "lid_a", jp, jq);
            double el = now - g_bpp[s].t0; float dur = g_bpp[s].dur;
            xlog("bp: slot %d bag prop %s at %.0f / %.0f ms of its clip; lid_a %s %.2f %.2f %.2f (rel. puppet %.2f %.2f %.2f)", s, (g_bpp[s].clip & 3) ? bp_prop_clip_name(s, g_bpp[s].clip, g_bpp[s].prop) : "-",
                 el, (double)dur * 1000.0, okj ? "at" : "unreadable", okj ? jp[0] : 0, okj ? jp[1] : 0, okj ? jp[2] : 0, okj ? jp[0] - root[0] : 0, okj ? jp[1] - root[1] : 0, okj ? jp[2] - root[2] : 0);
        }
    }
    else if (g_bpp[s].clip == BPC_LOOP) {
        if (!g_bpp[s].floor_ok) {
            if (!xbx_loc(h, "r_hand_prop_attachment", hp, hq)) return;
            g_bpp[s].floor_pos[0] = hp[0]; g_bpp[s].floor_pos[2] = hp[2]; g_bpp[s].floor_pos[1] = loc[1] + 0.004f; g_bpp[s].floor_ok = 1;
        }
        bp_prop_pose(g_bpp[s].prop, g_bpp[s].floor_pos, loc);
    } else {
        g_bpp[s].floor_ok = 0;
        if (xbx_loc(h, "r_hand_prop_attachment", hp, hq)) { hp[1] -= 0.45f; bp_prop_pose(g_bpp[s].prop, hp, loc); }
    }
    if (now - g_bpp[s].t_hide > 200.0) {
        g_bpp[s].t_hide = now;
        uint8_t *dc = gvis_dc(h);
        if (dc) for (int i = 0; i < BP_NPARTS; i++) {
            int idx = bp_dc_find(dc, g_bp_part_sid[i]);
            if (idx >= 0 && !bp_dc_hidden(dc, idx)) bp_dc_hide(dc, g_bp_part_sid[i]);
        }
    }
}
static void bp_pup_stop(int s, float blend, const char *why) {
    if (g_bpp[s].clip && g_bpp[s].h && g_bpp[s].name) psync_stop(g_bpp[s].h, fnv64(g_bpp[s].name), blend);
    if (g_bpp[s].clip) xlog("bp: slot %d puppet %s stopped (%s), blend %.2f s at t %.0f ms", s, BPC_NAME[g_bpp[s].clip & 3], why, blend, bp_ms());
    g_bpp[s].clip = BPC_NONE; g_bpp[s].name = NULL;
}
// the first clip of stance st / clip the puppet's tables know (0 = none), its length in *dur
static const char *bp_clip_find(uint64_t h, int st, int clip, float *dur) {
    *dur = 0;
    for (int i = 0; i < 4 && BP_CLIPS[st & 3][clip & 3][i]; i++) if ((*dur = anim_len(h, BP_CLIPS[st & 3][clip & 3][i])) > 0) return BP_CLIPS[st & 3][clip & 3][i];
    *dur = 0;
    return NULL;
}
// the stance the puppet plays for the owner's stance: that one when the puppet knows its intro (probed once per body), else standing
static int bp_pup_stance(int s, uint64_t h) {
    int st = g_bpp[s].stance & 3;
    if (st == BPS_STAND) return st;
    if (g_bpp[s].st_h != h) { g_bpp[s].st_h = h; memset(g_bpp[s].st_ok, -1, sizeof g_bpp[s].st_ok); }
    if (g_bpp[s].st_ok[st] < 0) {
        float d; const char *nm = bp_clip_find(h, st, BPC_INTRO, &d);
        g_bpp[s].st_ok[st] = nm != NULL;
        xlog("bp: slot %d puppet %llx %s craft set: %s", s, (unsigned long long)h, BPS_NAME[st], nm ? nm : "NOT KNOWN - the standing set plays");
    }
    return g_bpp[s].st_ok[st] ? st : BPS_STAND;
}
// start `clip` on the puppet at clip time ct (ms); 0 = nothing playable
static int bp_pup_play(int s, uint64_t h, int clip, double ct, float blend, double now) {
    const char *nm = NULL; float dur = 0;
    int st = bp_pup_stance(s, h);
    SUBT0(al);
    nm = bp_clip_find(h, st, clip, &dur);
    if (!nm && st != BPS_STAND) { st = BPS_STAND; nm = bp_clip_find(h, st, clip, &dur); }
    SUBT1(al, "bp_net: puppet anim_len lookups");
    if (!nm) {
        if (!g_bpp[s].warned_none++) xlog("bp: slot %d puppet %llx knows no %s %s craft clip (%s / %s) - no backpack anim on it", s,
                                         (unsigned long long)h, BPS_NAME[st], BPC_NAME[clip], BP_CLIPS[st][clip][0], BP_CLIPS[st][clip][1]);
        return 0;
    }
    g_bpp[s].cst = st;              // before bp_prop_clip: the prop clip name is the one of this stance
    if (ct < 0) ct = 0;
    float ph = (float)(ct / (dur * 1000.0));
    if (clip == BPC_LOOP) ph -= (float)(int)ph;
    if (ph > 0.98f) ph = 0.98f;
    uint64_t r;
    SUBP("bp_net: puppet animate_from", r = animate_from(h, nm, blend, ph));
    g_bpp[s].clip = clip; g_bpp[s].name = nm; g_bpp[s].dur = dur; g_bpp[s].h = h;
    g_bpp[s].t0 = now - (double)ph * dur * 1000.0;
    if (r && r != ~0ULL) bp_prop_clip(s, clip, ph, blend);
    xlog("bp: slot %d puppet %s %s %s (%.2f s) from %.0f ms (phase %.2f), blend %.2f, at t %.0f ms -> %llx (owner stance %s)",
         s, BPS_NAME[st], BPC_NAME[clip], nm, dur, (double)ph * dur * 1000.0, ph, blend, now, (unsigned long long)r, BPS_NAME[g_bpp[s].stance & 3]);
    return r && r != ~0ULL;
}
// bring the puppet to what the owner's phase / clip time says (late joiner, lost packets, phase change)
static void bp_pup_sync(int s, uint64_t h, double now) {
    double ct = g_bpp[s].ct_rx + (now - g_bpp[s].rx_ms);
    int ph = g_bpp[s].phase;
    if (ph == BPP_OPEN) {
        // the owner changed stance while open (e.g. crouch <-> prone): the loop of the new stance (an intro plays out; the loop after it takes the new stance)
        if (g_bpp[s].clip == BPC_LOOP && g_bpp[s].cst != bp_pup_stance(s, h)) {
            xlog("bp: slot %d owner stance %s while the %s loop plays - switching loops", s, BPS_NAME[g_bpp[s].stance & 3], BPS_NAME[g_bpp[s].cst & 3]);
            bp_pup_play(s, h, BPC_LOOP, 0, BPP_BLEND, now);
            return;
        }
        if (g_bpp[s].clip == BPC_INTRO || g_bpp[s].clip == BPC_LOOP) return;
        if (g_bpp[s].clip == BPC_OUTRO) { bp_pup_play(s, h, BPC_INTRO, 0, BPP_BLEND, now); return; }   // reopened mid-outro
        float di; bp_clip_find(h, bp_pup_stance(s, h), BPC_INTRO, &di);
        if (di > 0 && ct >= di * 1000.0 - 150.0) bp_pup_play(s, h, BPC_LOOP, ct - di * 1000.0, BPP_BLEND, now);   // joined late: already in the loop
        else bp_pup_play(s, h, BPC_INTRO, ct, BPP_BLEND, now);
    } else if (ph == BPP_CLOSING) {
        if (g_bpp[s].clip == BPC_OUTRO) return;
        float d; bp_clip_find(h, bp_pup_stance(s, h), BPC_OUTRO, &d);
        if (g_bpp[s].clip == BPC_NONE && (d <= 0 || ct >= d * 1000.0 - 250.0)) return;   // the outro is already over on the owner
        bp_pup_play(s, h, BPC_OUTRO, ct, 0.2f, now);
    } else if (ph == BPP_ABORT) {
        bp_pup_stop(s, 0.2f, "owner aborted (death / down / match end)");
    } else if (ph == BPP_IDLE && (g_bpp[s].clip == BPC_INTRO || g_bpp[s].clip == BPC_LOOP)) {
        bp_pup_play(s, h, BPC_OUTRO, 0, 0.2f, now);      // the closing was lost: stand up from the start of the outro
    }
}
static void bp_net_recv(uint32_t slot, const uint8_t *buf, uint64_t len) {
    if (slot > T2R_MAX_PEERS - 1 || !buf) return;
    if (len >= 6 && buf[0] == BPT_VER) { if (slot != *(uint32_t *)VMA(0x180138090)) bpt_net_recv((int)slot, buf, len); return; }
    if (len >= 6 && buf[0] == BPTR_VER) { if (slot != *(uint32_t *)VMA(0x180138090)) bptr_net_recv((int)slot, buf, len); return; }
    if (len < BP_MSG_V1_LEN) return;
    bp_msg_t m; memset(&m, 0, sizeof m); memcpy(&m, buf, len < sizeof m ? (size_t)len : sizeof m);   // an old sender has no stance byte = stand
    if (m.ver != BP_VER || m.phase > BPP_ABORT) return;
    if (slot == *(uint32_t *)VMA(0x180138090)) return;
    double now = bp_ms();
    int s = (int)slot, changed = m.phase != g_bpp[s].phase || m.seq != g_bpp[s].seq;
    float ow = psync_oneway(s);
    g_bpp[s].rx_ms = now;
    g_bpp[s].ct_rx = (double)m.el_ms + ow;
    if ((m.stance & 3) != g_bpp[s].stance) {
        xlog("bp: slot %d rx owner stance %s -> %s (phase %s, %u ms in)", s, BPS_NAME[g_bpp[s].stance & 3], BPS_NAME[m.stance & 3], BPP_NAME[m.phase & 3], m.el_ms);
        g_bpp[s].stance = m.stance & 3;
    }
    if (changed)
        xlog("bp: slot %d rx phase %s (seq %u, %u ms into it, one-way ~%.0f ms, owner bag %s, swap at enter %d / leave %d ms) at t %.0f ms; puppet %s",
             s, BPP_NAME[m.phase & 3], m.seq, m.el_ms, ow, m.bagoff ? "off" : "on", m.enter_ms == 0xffff ? -1 : m.enter_ms,
             m.leave_ms == 0xffff ? -1 : m.leave_ms, now, BPC_NAME[g_bpp[s].clip & 3]);
    g_bpp[s].phase = m.phase; g_bpp[s].seq = m.seq;
    g_bpp[s].want_off = m.bagoff != 0;
    if (m.enter_ms != 0xffff && m.enter_ms > 0 && m.enter_ms < 1500) g_bpp[s].enter_pred = m.enter_ms;
}
static void bp_pup_tick(double now) {
    int live = match_substate() == 6;
    uint32_t me = *(uint32_t *)VMA(0x180138090);
    for (int s = 0; s < T2R_MAX_PEERS; s++) {
        if ((uint32_t)s == me) continue;
        if (!g_bpp[s].clip && g_bpp[s].phase == BPP_IDLE && !g_bpp[s].off && !g_bpp[s].prop) continue;
        uint64_t h = live ? bp_puppet(s) : 0;
        if ((g_bpp[s].clip || g_bpp[s].off) && g_bpp[s].h && g_bpp[s].h != h) {            // new body (respawn) / gone: the clip died with the old one; a held prop / hidden worn bag too (no clip between two phases)
            xlog("bp: slot %d puppet changed %llx -> %llx mid %s - state cleared", s, (unsigned long long)g_bpp[s].h,
                 (unsigned long long)h, BPC_NAME[g_bpp[s].clip & 3]);
            g_bpp[s].clip = BPC_NONE; g_bpp[s].name = NULL; g_bpp[s].phase = BPP_IDLE;
            g_bp_pup_off[s] = 0; bp_pup_prop_kill(s, live); g_bpp[s].off = 0; g_bpp[s].want_off = 0;
            continue;
        }
        if (!h) { g_bpp[s].phase = BPP_IDLE; g_bp_pup_off[s] = 0; bp_pup_prop_kill(s, live); g_bpp[s].off = 0; g_bpp[s].want_off = 0; continue; }
        // B was in its backpack when A pulled it out; the menu closed at the
        // drag start and here the close played the STANDING craft outro on B's puppet over the drag's victim half (A [21343], layer lost at 257 ms)
        // - B stood through the drag on A's screen. A puppet in a paired move (psync / pull-out) plays no craft clip: the pair owns its body.
        const char *clr = !live ? "match end" : g_peer_downed[s] ? "downed" : psync_dead(h) ? "dead" : (psync_busy_slot((uint32_t)s) || pul_puppet_busy((uint32_t)s)) ? "in a paired move" : NULL;
        if (clr) { bp_pup_stop(s, 0.2f, clr); bp_pup_bag_on(s, h, live, clr); g_bpp[s].phase = BPP_IDLE; g_bpp[s].want_off = 0; continue; }
        if ((g_bpp[s].phase == BPP_OPEN || g_bpp[s].phase == BPP_CLOSING) && now - g_bpp[s].rx_ms > 2500.0) {
            xlog("bp: slot %d no backpack message for %.0f ms while %s - taken as closed", s, now - g_bpp[s].rx_ms, BPP_NAME[g_bpp[s].phase]);
            g_bpp[s].phase = BPP_IDLE; g_bpp[s].want_off = 0;
        }
        bp_pup_sync(s, h, now);
        if (!bp_pup_off_disabled()) {
            // A took B's bag off 329 ms after the open (B: 133 ms) - it waited for B's bag-off message, then spawned the prop and probed its
            // clip for 150 ms with the worn bag still on. Now the prop is readied as soon as the intro starts here and the swap happens at the owner's own swap clip time
            // (enter ms of its last open, 135 ms before one is known) on the puppet's clip clock, or at the owner's bag-off message if that comes first.
            if (g_bpp[s].enter_pred <= 0) g_bpp[s].enter_pred = 135.0;
            int early = g_bpp[s].phase == BPP_OPEN && g_bpp[s].clip == BPC_INTRO;
            int go = g_bpp[s].want_off || (early && now - g_bpp[s].t0 >= g_bpp[s].enter_pred);
            if ((g_bpp[s].want_off || early) && !g_bpp[s].off) bp_pup_bag_off(s, h, now, go);
            else if (!g_bpp[s].off && g_bpp[s].prop && !g_bpp[s].want_off) { xlog("bp: slot %d readied prop not used (no swap in the intro) - removed", s); bp_pup_prop_kill(s, live); }
            else if (!g_bpp[s].want_off && g_bpp[s].off && !(g_bpp[s].phase == BPP_OPEN && now - g_bpp[s].t_off < 800.0)) bp_pup_bag_on(s, h, live, "owner's bag back on");
            if (g_bpp[s].off && g_bpp[s].prop) bp_pup_bag_tick(s, h, now);
        }
        if (!g_bpp[s].clip) continue;
        double el = now - g_bpp[s].t0, len = g_bpp[s].dur * 1000.0;
        if (g_bpp[s].clip == BPC_INTRO && el >= len - 150.0) {
            if (g_bpp[s].phase == BPP_OPEN) bp_pup_play(s, h, BPC_LOOP, 0, 0.2f, now);
        } else if (g_bpp[s].clip == BPC_LOOP && el >= len - 150.0) {
            bp_pup_play(s, h, BPC_LOOP, 0, 0.15f, now);
        } else if (g_bpp[s].clip == BPC_OUTRO && el >= len - 250.0) {
            bp_pup_stop(s, 0.25f, "outro done");
            if (g_bpp[s].phase == BPP_CLOSING) g_bpp[s].phase = BPP_IDLE;
        }
    }
}
static void bp_net_tick(void) {
    double now = bp_ms();
    SUBP("bp_net: own tick", bp_own_tick(now));
    SUBP("bp_net: puppets tick", bp_pup_tick(now));
}
