// ---------------------------------------------------------------- 2013 Last One Standing / Sudden Death (Supply Raid)
// Data: re lms-2013-spec.md (TLOU1 PS3 patch1 DC scripts ss-comp-tdm-tickets-count, ss-comp-player-highlight,
// ss-region-spawn-pickups, ss-comp-tdm-mode). Included after interrogation.c / overtime.c (unity build).
//
// Team count (2013 net-get-team-count) = the team's respawn pool + its players not yet eliminated. A downed player still counts
// (a down is not a death; 2013's downed handling is native and not readable). With lives left a dead player waiting for its
// respawn is part of the pool, so the one-player states need the pool at 0 (count == alive players then).
//
// HUD states (ticket-count-state, run on every kill / spawn; here when the counts change and stay for 0.4 s; first match wins,
// each state entered once while it holds, a new state drops the old state's pending steps like a DC `go`):
//   our count > 1 and enemy count == 1  -> "Last enemy left, hunt them down!" (7 s)
//   both counts == 1                    -> after 1.5 s "One vs One!", Last One Standing award if it was not paid yet
//   our count == 1                      -> after 5 s "Last One Standing" (7 s) + the enemy highlight, 5 s later the award
//   our pool == 8                       -> "Only 8 Reinforcements Left" (only when the match started with more)
//   our pool == 0                       -> after 5 s "Sudden Death" (7 s) + the enemy highlight
//   (enemy pool == 0: the few-enemies vox, already in the vox code)
// Award: stat 0x4fa98037, 2013 *net-tdm-stat-rewards* 500 parts, scaled to 100 like the old end-of-match "Survived" it replaces
// (economy). Paid once per match, only to the last player of the team while not killed. t2r-no-survived-bonus.txt = off.
// Enemy highlight (ss-comp-player-highlight): 5 s after the event every enemy is marked for the local player: fade in 3 s, full 5 s,
// fade out 3 s, hidden 20 s, repeating to the match end (31 s cycle). Each event restarts the cycle. Drawn as the marked red name
// tag (feature_nametags: through walls, any range; 2013 drew a red 'marked-man' icon 2.1 m over the enemy).
// Uber box (ss-region-spawn-pickups 'last-man-standing?): the first time our team count reaches 1 (once per match) the next box we
// open holds the uber set instead of its normal plan (supplybox.c b13_fill_begin).
// Late join (ss-comp-tdm-mode @ff0 + team-performance-items): parts at the first spawn and an fgc step at the boxes.
// t2r-no-lms.txt next to the exe = the HUD states, highlight and uber box off. Log 'lms: ...'.

static struct {
    int armed;                     // a match is running and both pools were read once
    int lives0;                    // our pool at the match start
    int key[4], key_seen[4];       // counts (ours, theirs) + pools (ours, theirs): the last evaluated / last seen
    uint64_t key_at;               // when key_seen last changed
    int st;                        // current state (LMS_*), 0 none
    uint64_t st_t0;                // when it was entered
    int steps;                     // steps of the current state already done (bit mask)
    int paid;                      // Last One Standing paid (flag 0xde355e68)
    int box_sent;                  // the uber-box trigger fired (flag 0xc123d27b / 0xda0bdf03, our team)
    uint64_t hl_t0;                // enemy highlight: cycle start (0 = off)
    int late_done;                 // late-join parts paid / checked
    float late_elapsed;            // seconds of the match gone when we first spawned as a late joiner (-1 = not a late joiner)
    int late_fgc_done;             // the late-join fgc step was used by a box
} g_lms = {.late_elapsed = -1.0f};
enum { LMS_NONE, LMS_HUNT, LMS_1V1, LMS_LAST, LMS_LOW8, LMS_SD };
static const char *const LMS_NAMES[] = {"none", "hunt them down", "one vs one", "last one standing", "8 reinforcements left", "sudden death"};

static int lms_off(void) {
    static int off = -1; static uint64_t chk;
    uint64_t now = GetTickCount64();
    if (off < 0 || now - chk > 3000) { chk = now; FILE *f = exe_side_open("t2r-no-lms.txt", "r"); off = f != NULL; if (f) fclose(f); }
    return off;
}
// enemy highlight alpha now (0..1), for the name tags
static float lms_hl_alpha(void) {
    if (!g_lms.hl_t0 || match_substate() != 6) return 0.0f;
    uint64_t now = GetTickCount64();
    if (now < g_lms.hl_t0) return 0.0f;
    uint64_t t = (now - g_lms.hl_t0) % 31000;
    if (t < 3000) return (float)t / 3000.0f;
    if (t < 8000) return 1.0f;
    if (t < 11000) return 1.0f - (float)(t - 8000) / 3000.0f;
    return 0.0f;
}
static int lms_slot_up(uint32_t s, uint32_t me) {
    if (s == me) return !fig_slot_dead(me, me);
    uint8_t *p = ((uint8_t *(*)(uint32_t))t2r_peer)(s);
    if (!p || !*(uint64_t *)(p + 0x60) || !p[4]) return 0;
    return !fig_slot_dead(s, me) && g_peer_downed[s] != 2 && !g_puppet_dead_here[s];
}
// alive players: n[0] ours (us included), n[1] theirs
static void lms_alive(int n[2]) {
    uint32_t me = *(uint32_t *)VMA(0x180138090);
    n[0] = n[1] = 0;
    for (uint32_t s = 0; s < T2R_MAX_PEERS; s++) {
        if (!lms_slot_up(s, me)) continue;
        n[s == me || is_teammate(s) ? 0 : 1]++;
    }
}
static int lms_count(int pool, int alive) { return pool <= 0 ? alive : pool + alive; }
// 2013 team-count difference, ours - theirs (Supply Raid: count; Interrogation: team interrogations). 0 when unknown.
static int lms_team_diff(void) {
    if (r13_int_mode()) {
        int t = g_int.team;
        return g_int.ok && g_int.on && (t == 0 || t == 1) ? g_int.p[t] - g_int.p[t ^ 1] : 0;
    }
    uint8_t *lo = lobby_obj();
    if (!lo || match_substate() != 6) return 0;
    int al = ((int (*)(void *))VMA(0x18004C120))(lo), en = ((int (*)(void *))VMA(0x18004C150))(lo);
    if (al <= -1000 || en <= -1000) return 0;
    int n[2]; lms_alive(n);
    return lms_count(al, n[0]) - lms_count(en, n[1]);
}
// supplybox.c: the 2013 team adjustment (evaluate-group-choice): diff >= 5 -> 2, >= 3 -> 1, <= -5 -> -2, <= -3 -> -1. A team that is behind
// gets the lower group (more loot), as the outnumbered step; the late-join step once per match.
static int lms_fgc_adjust(int *team_out, int *late_out) {
    int d = lms_team_diff();
    int a = d >= 5 ? 2 : d >= 3 ? 1 : d <= -5 ? -2 : d <= -3 ? -1 : 0;
    *team_out = a;
    *late_out = 0;
    if (g_lms.late_elapsed >= 0.0f && !g_lms.late_fgc_done) {
        float e = g_lms.late_elapsed;
        *late_out = e >= 480.0f ? -4 : e >= 360.0f ? -3 : e >= 240.0f ? -2 : e >= 120.0f ? -1 : 0;
    }
    return d;
}
// the box used the late-join step (2013 'late-join-pickups-done?): applied at one box only
static void lms_late_fgc_used(void) { g_lms.late_fgc_done = 1; }
// supplybox.c: the 2013 fgc step 'below a floor' rules of team-performance-items (-3 if fgc > -3 ...), -4 always
static int lms_late_apply(int fgc, int late) {
    if (late == -4) return fgc - 4;
    if (late < 0 && fgc > late) return late;
    return fgc;
}
static void lms_popup(const char *t) { msg_hook(t, 7.0f, 0, 0); xlog("lms: popup \"%s\"", t); }
static void lms_hl_start(uint64_t at, const char *why) {
    g_lms.hl_t0 = at;
    xlog("lms: enemy highlight from %llu ms on (%s): 3 s in, 5 s on, 3 s out, 20 s off, to the match end", (unsigned long long)(at - GetTickCount64()), why);
}
static void lms_award(const char *why) {
    if (g_lms.paid) return;
    uint32_t me = *(uint32_t *)VMA(0x180138090);
    if (me > T2R_MAX_PEERS - 1 || fig_slot_dead(me, me)) { xlog("lms: Last One Standing not paid (%s): we are down for good", why); return; }
    g_lms.paid = 1;
    if (!took_part()) { xlog("lms: Last One Standing not paid (%s): we took no part in the match (t2r-idle-pays-old.txt = old rule)", why); return; }
    if (GetFileAttributesA("t2r-no-survived-bonus.txt") != INVALID_FILE_ATTRIBUTES) { xlog("lms: Last One Standing not paid (t2r-no-survived-bonus.txt)"); return; }
    xlog("lms: Last One Standing +100 (%s)", why);
    award(100, me, "Last One Standing");
}
// late join parts (2013 stat 0x405271b1, 100 parts per point): minutes gone minus 1, + 2 / 4 / 6 when the enemy has 1 / 2 / 3 more
// players spawned. Once per match, at our first spawn as a late joiner.
static void lms_late_join(uint8_t *lo) {
    if (g_lms.late_done) return;
    if (g_jip_late_ans == 0) return;                   // no answer yet
    g_lms.late_done = 1;
    if (g_jip_late_ans != 2) return;
    uint32_t me = *(uint32_t *)VMA(0x180138090);
    if (me > T2R_MAX_PEERS - 1 || IsBadReadPtr(lo + 0x2b8c, 12)) return;
    float dur = *(float *)(lo + 0x2b8c), rem = *(float *)(lo + 0x2b90);
    float el = dur > 0.0f && rem >= 0.0f && rem <= dur ? dur - rem : 0.0f;
    g_lms.late_elapsed = el;
    int pts = (int)__builtin_roundf(el / 60.0f - 1.0f);
    int d = b13_team_diff();
    if (d >= 1 && d <= 3) pts += 2 * d;
    xlog("lms: late join - %.0f s of %.0f s gone, enemy - ally players %d -> %d point(s)%s", el, dur, d, pts, pts > 0 ? "" : ", no parts");
    if (pts > 0) award(100 * pts, me, "Late Join Bonus");
}
static void lms_tick(void) {
    uint64_t now = GetTickCount64();
    if (match_substate() != 6) {
        if (g_lms.armed || g_lms.late_done || g_lms.late_elapsed >= 0.0f) { memset(&g_lms, 0, sizeof g_lms); g_lms.late_elapsed = -1.0f; }
        g_lms_box = 0;
        return;
    }
    uint8_t *lo = lobby_obj();
    if (!lo) return;
    {   // our first spawn this match (alive once)
        uint32_t me = *(uint32_t *)VMA(0x180138090);
        if (!g_lms.late_done && me < T2R_MAX_PEERS && !fig_slot_dead(me, me)) lms_late_join(lo);
    }
    if (r13_int_mode() || lms_off()) return;           // Interrogation: 999 lives, the count never reaches these states (2013 the same)
    if (g_frame % 6) goto steps;
    {
        int al = ((int (*)(void *))VMA(0x18004C120))(lo), en = ((int (*)(void *))VMA(0x18004C150))(lo);
        if (al <= -1000 || en <= -1000) return;
        int n[2]; lms_alive(n);
        if (!g_lms.armed) {
            if (n[0] < 1 || n[1] < 1) return;          // both teams have someone in the match
            g_lms.armed = 1; g_lms.lives0 = al;
            for (int i = 0; i < 4; i++) g_lms.key[i] = g_lms.key_seen[i] = -99;
            xlog("lms: match on - pools %d / %d, alive %d / %d", al, en, n[0], n[1]);
        }
        int k[4] = {lms_count(al, n[0]), lms_count(en, n[1]), al, en};
        if (memcmp(k, g_lms.key_seen, sizeof k)) { memcpy(g_lms.key_seen, k, sizeof k); g_lms.key_at = now; }
        if (now - g_lms.key_at < 400 || !memcmp(k, g_lms.key, sizeof k)) goto steps;
        memcpy(g_lms.key, k, sizeof k);
        int cT = k[0], cE = k[1];
        int st = LMS_NONE;
        if (cT > 1 && cE == 1 && en <= 0) st = LMS_HUNT;
        else if (cT == 1 && cE == 1 && al <= 0 && en <= 0) st = LMS_1V1;
        else if (cT == 1 && al <= 0) st = LMS_LAST;
        else if (al == 8 && g_lms.lives0 > 8) st = LMS_LOW8;
        // (all player nametags were constantly visible in a 4v4 at 0:0): a pool that reads 0 from the match start (no reinforcement count on this
        // server / mode, or the getter has no value) armed Sudden Death and its every-enemy highlight from the first poll. 2013's Sudden Death is the pool
        // RUNNING OUT: only a pool that started above 0 enters it. t2r-lms-sd-pool0.txt = old rule.
        else if (al == 0 && (g_lms.lives0 > 0 || GetFileAttributesA("t2r-lms-sd-pool0.txt") != INVALID_FILE_ATTRIBUTES)) st = LMS_SD;
        xlog("lms: counts ours %d (pool %d, alive %d) theirs %d (pool %d, alive %d) -> %s%s", cT, al, n[0], cE, en, n[1], LMS_NAMES[st],
             st && st == g_lms.st ? " (already)" : st ? "" : " (state kept)");
        if (cT == 1 && al <= 0 && !g_lms.box_sent) {
            g_lms.box_sent = 1;
            uint32_t me = *(uint32_t *)VMA(0x180138090);
            if (!fig_slot_dead(me, me)) { g_lms_box = 1; xlog("lms: our team is on its last life - the next box we open is the Last Man Standing box"); }
        }
        if (st && st != g_lms.st) { g_lms.st = st; g_lms.st_t0 = now; g_lms.steps = 0; }
    }
steps:
    if (!g_lms.st) return;
    {
        uint64_t t = now - g_lms.st_t0;
        int *s = &g_lms.steps;
        switch (g_lms.st) {
        case LMS_HUNT: if (!(*s & 1)) { *s |= 1; lms_popup("Last enemy left, hunt them down!"); } break;
        case LMS_LOW8: if (!(*s & 1)) { *s |= 1; lms_popup("Only 8 Reinforcements Left"); } break;
        case LMS_1V1:
            if (t >= 1500 && !(*s & 1)) { *s |= 1; lms_popup("One vs One!"); lms_award("one vs one"); }
            break;
        case LMS_LAST:
            if (t >= 5000 && !(*s & 1)) { *s |= 1; lms_popup("Last One Standing"); lms_hl_start(now + 5000, "last one standing"); }
            if (t >= 10000 && !(*s & 2)) { *s |= 2; lms_award("last one standing"); }
            break;
        case LMS_SD:
            if (t >= 5000 && !(*s & 1)) { *s |= 1; lms_popup("Sudden Death"); lms_hl_start(now + 5000, "sudden death: no reinforcements"); }
            break;
        }
    }
}
