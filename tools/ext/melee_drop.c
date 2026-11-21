// melee_drop.c (v5-dis4, A/B: pin deaths and other forms of dying should also drop the melee, so a disarm that did not trigger still lets the
// killer take the weapon; an enemy with a melee weapon did not take it out when punched).
//
// ROOT CAUSES (A/B logs, t2r-ext.log):
//  1. No killed player ever dropped a melee weapon: the only killed-player melee drop was drop_melee_pickup(g_peer_melee[slot]) inside the post-death
//     sweep, and g_peer_melee[slot] is set only when THAT slot had finished US with a melee finisher (msg 0x10) - a random weapon of that style's pool,
//     never the weapon the dead player carried, never its durability. Both logs: 0 "melee drop: killed player drops" lines over 15 deaths of melee
//     carriers (A 49118: A died holding 7919a42b after B's pin; B 39713 / 45927 ...), and the sweep itself never logged "died: clearing" once.
//  2. The disarm finisher read only the weapon IN the victim's hand (winmm's peer record +0x91). A victim carrying its melee weapon stowed (a gun in
//     the hand, or emptied hands for the hit pair) got the plain fist kill: A 45378 fist-nose-break-kill on B (clip: B's red crowbar on its
//     backpack, the pistol in its hand; B 38587 "our gun put away for it", 39150 "wpose: no weapon"), POOL = the 5 plain fist kills only.
//
// FIX:
//  - MSG_MOWN 0xA6 [u8 ver 1][u64 carried melee weapon (MELEE_TAB base id, 0 = none)][i16 durability, -1 unknown][u8 seq]: every client tells the
//    others which droppable melee weapon it carries (held or stowed; the machete and the knives never count) and its durability - on a change, else
//    every 2 s, never while dead (a respawn's empty inventory cannot overwrite the dying player's weapon). Receivers keep the value last seen while that
//    slot was alive.
//  - Death drop: on every screen but the victim's own, every death of a slot that carried one (pin kill, finisher, shot, downed kill, bleed-out, ...)
//    spawns THAT weapon at its body with ITS durability (spawn-item-pickup count) 20 frames after the death, or once no paired move / execution holds
//    the body (max 200 frames). The old pool drop (g_peer_melee) stays only for a peer that never sent MSG_MOWN (an older build).
//  - Disarm: a victim with no melee in the hand that carries one (its MSG_MOWN) gets the disarm rows of that weapon's class (cd_fin_pick); its own
//    client draws the weapon into the hand at the disarm's START (cd_dis_tick role 2; SP's defender holds its weapon), so the take frame and the
//    hand-off work as with a held weapon. The disarm hand-off forgets the victim's carried weapon on every screen (no drop of a weapon already taken).
// Opt-outs (re-read every 2 s): t2r-no-mown-drop.txt = the old pool drop (MSG_MOWN still sent), t2r-dis-held-only.txt = disarms only of a held weapon.
// Log: "melee own:", "melee drop:".
#define MSG_MOWN 0xA6
#define MOWN_FRESH_MS 6000      // a carried-weapon report older than this (no heartbeat) is not trusted
#define MOWN_DROP_DELAY 20      // frames after the death (no pair on the body)
#define MOWN_DROP_MAX 200       // frames: a body held by a paired move / execution drops at the latest here
static struct {
    uint64_t sid, rx_ms;          // the last report
    int16_t dur;
    uint64_t a_sid, a_ms;         // the report as it was while the slot was alive
    int16_t a_dur;
    uint64_t forget_sid, forget_ms;   // a disarm took it: reports of this weapon are ignored for 5 s (a heartbeat sent before the victim's removal)
    int was_dead, pend;           // pend 1 = drop its weapon, 2 = the old pool drop (g_peer_melee)
    uint64_t died_t60, drop_h, chk_t60;
    char drop_n[32];
    uint64_t swept_t60;           // v5-mown2: the post-death sweep's last pass on this slot
    int hold;                     // v5-mown2: our drop lies at the body - no more sweeps of it this death
} g_mown[T2R_MAX_PEERS];
static int mown_file(const char *f, int *v, uint64_t *at) {
    if (*v < 0 || GetTickCount64() - *at > 2000) { *at = GetTickCount64(); int o = GetFileAttributesA(f) != INVALID_FILE_ATTRIBUTES;
        if (o != *v && *v >= 0) xlog("melee own: %s %s", f, o ? "found - opt-out ON" : "gone - opt-out off"); *v = o; }
    return *v;
}
static int mown_off(void) { static int v = -1; static uint64_t at; return mown_file("t2r-no-mown-drop.txt", &v, &at); }
static int mown_dis_held_only(void) { static int v = -1; static uint64_t at; return mown_file("t2r-dis-held-only.txt", &v, &at); }
// v5-mown2: the post-death sweep vs our death drop (t2r-mown-no-sweep-wait.txt = drop without waiting, the sweep runs its whole window as before)
static int mown_sweep_off(void) { static int v = -1; static uint64_t at; return mown_file("t2r-mown-no-sweep-wait.txt", &v, &at); }
static int mown_sweep_hold(int s) { return s >= 0 && s < T2R_MAX_PEERS && g_mown[s].hold && !mown_sweep_off(); }
static void mown_swept(int s) { if (s >= 0 && s < T2R_MAX_PEERS) g_mown[s].swept_t60 = g_t60; }

// ---- v5-mown2: pickup durability ledger (pickups were forced to full durability although they spawn at 1).
// The engine ignores spawn-item-pickup's count for a melee weapon: every melee pickup is taken at health 1 (A 17560 / B 14860 / B 36520
// "full-condition: health 1" for x10 box spawns), and feature_melee_full_condition then set EVERY pickup to the class max - also a disarmed weapon
// whose durability the disarm had just set (A 44435 "durability 10 -> 5 (the victim's)", A 44440 "health 5 -> set 10"). Now each melee pickup WE spawn
// is written down with the durability it stands for (box / item spot = the class max, a death drop = the dead player's weapon's), and a disarm hand-off
// names the victim's; at the pickup edge full-condition sets THAT durability (pdur_pick: the hand-off first, else the vanished ledger pickup of the
// same weapon nearest to us, else the class max as before). t2r-no-pickup-dur.txt = always the class max (old rule). Log: "pickup dur:".
#define PDUR_N 24
static struct { uint64_t h, base, born; int dur; float pos[3]; } g_pdur[PDUR_N];
static struct { uint64_t base; int dur; uint64_t until_ms; } g_pdur_want;
static struct { uint64_t base; int dur; } g_pdur_last;          // the last pickup's weapon + the durability it was set to (a stowed weapon's report)
static int pdur_off(void) { static int v = -1; static uint64_t at; return mown_file("t2r-no-pickup-dur.txt", &v, &at); }
static void pdur_set_last(uint64_t w, int dur) { g_pdur_last.base = base_weapon(w) ? base_weapon(w) : w; g_pdur_last.dur = dur; }
static void pdur_note(uint64_t h, uint64_t item, int dur, const float *pos, const char *why) {
    if (!h || h == ~0ULL || !melee_dur_w(base_weapon(item) ? base_weapon(item) : item) || dur <= 0 || !pos) return;
    int k = -1;
    for (int i = 0; i < PDUR_N && k < 0; i++) if (!g_pdur[i].h || g_t60 - g_pdur[i].born > 18000) k = i;
    if (k < 0) { k = 0; for (int i = 1; i < PDUR_N; i++) if (g_pdur[i].born < g_pdur[k].born) k = i; }
    g_pdur[k].h = h; g_pdur[k].base = base_weapon(item) ? base_weapon(item) : item; g_pdur[k].dur = dur; g_pdur[k].born = g_t60;
    memcpy(g_pdur[k].pos, pos, 12);
    static int nl; if (LOGCAP(nl, 60)) xlog("pickup dur: %llx spawned as pickup %llx with durability %d (%s) at %.1f %.1f %.1f", (unsigned long long)item, (unsigned long long)h, dur, why, pos[0], pos[1], pos[2]);
}
static void pdur_want(uint64_t w, int dur, const char *why) {
    if (!w || w == ~0ULL || dur <= 0) return;
    g_pdur_want.base = base_weapon(w) ? base_weapon(w) : w; g_pdur_want.dur = dur; g_pdur_want.until_ms = GetTickCount64() + 4000;
    xlog("pickup dur: %llx comes to us with durability %d (%s) - the pickup edge keeps it", (unsigned long long)w, dur, why);
}
// at the pickup edge of weapon w: the durability it should have (0 = unknown: the class max)
static int pdur_pick(uint64_t w, char *why, size_t wl) {
    if (pdur_off() || !w || w == ~0ULL) return 0;
    uint64_t b = base_weapon(w) ? base_weapon(w) : w;
    if (g_pdur_want.base == b && GetTickCount64() < g_pdur_want.until_ms) {
        int d = g_pdur_want.dur; g_pdur_want.base = 0; snprintf(why, wl, "the disarm hand-off"); return d;
    }
    typedef uint8_t *(*fn_me)(void); typedef const float *(*fn_loc)(void *, float *);
    uint8_t *me = ((fn_me)VMA(0x180050390))(); float mb[16];
    const float *mp = me ? ((fn_loc)((uint8_t *)GetModuleHandleW(NULL) + 0x133db30))(me + 0x100, mb) : NULL;
    int best = -1; float bd = 1e9f;
    for (int i = 0; i < PDUR_N; i++) {
        if (!g_pdur[i].h || g_pdur[i].base != b || drops_alive(g_pdur[i].h)) continue;     // (still lying there: not the one we took)
        float d2 = 0.0f;
        if (mp) { float dx = mp[0] - g_pdur[i].pos[0], dy = mp[1] - g_pdur[i].pos[1], dz = mp[2] - g_pdur[i].pos[2]; d2 = dx * dx + dy * dy + dz * dz; }
        if (d2 < bd) { bd = d2; best = i; }
    }
    if (best < 0 || (mp && bd > 6.0f * 6.0f)) { snprintf(why, wl, "no ledger pickup of it gone near us"); return 0; }
    int d = g_pdur[best].dur;
    snprintf(why, wl, "ledger pickup %llx, %.1f m away", (unsigned long long)g_pdur[best].h, mp ? sqrtf(bd) : -1.0f);
    g_pdur[best].h = 0;
    return d;
}
// the carried droppable melee weapon of slot s as its own client reported it (0 = none / unknown / stale / dead)
static uint64_t mown_peer(int s) {
    if (s < 0 || s >= T2R_MAX_PEERS || g_grace_dead[s] || !g_mown[s].sid || !g_mown[s].rx_ms || GetTickCount64() - g_mown[s].rx_ms > MOWN_FRESH_MS) return 0;
    return g_mown[s].sid;
}
static int mown_peer_dur(int s) { return mown_peer(s) ? g_mown[s].dur : -1; }
static void mown_forget(int s, uint64_t w) {
    if (s < 0 || s >= T2R_MAX_PEERS) return;
    uint64_t b = w ? base_weapon(w) : 0;
    if (g_mown[s].sid || g_mown[s].a_sid) xlog("melee own: slot %d's %llx forgotten (a disarm took it) - no death drop of it", s, (unsigned long long)(g_mown[s].a_sid ? g_mown[s].a_sid : g_mown[s].sid));
    g_mown[s].sid = g_mown[s].a_sid = 0; g_mown[s].forget_sid = b ? b : w; g_mown[s].forget_ms = GetTickCount64();
    if (g_mown[s].pend == 1) g_mown[s].pend = 0;
}
// a melee weapon that drops / can be disarmed: MELEE_TAB with an SP disarm class (no machete, no knife, no fists); *nm = its MELEE_TAB name
static int mown_droppable(uint64_t w, const char **nm) { const char *n = NULL; int ok = w && w != ~0ULL && cd_dis_class(w, &n) != 0 && n; if (nm) *nm = ok ? n : NULL; return ok; }
static uint64_t mown_self(int16_t *dur) {
    uint64_t cw = current_weapon(); if (cw == ~0ULL) cw = 0;
    uint64_t w = xr_melee_weapon(cw);
    const char *n = NULL;
    if (!mown_droppable(w, &n) && g_last_melee && w != g_last_melee) { uint64_t none = 0, has = dc_call(fnv64("has-weapon?"), 1, &g_last_melee); (void)none; if (has != ~0ULL && (has & 0xff)) w = g_last_melee; }   // (a knife in the hand, the club stowed)
    // v5-mown2: a stowed weapon was only known through g_last_melee (set while it is HELD): a pickup never drawn, or a stale g_last_melee (an old
    // weapon disarmed / broken / swapped), reported nothing or the wrong weapon. Stowed = ask the inventory (has-weapon? of each MELEE_TAB row, at
    // most once a second). t2r-mown-hand-only.txt = the old rule.
    static int ho = -1; static uint64_t ho_at;
    if (!mown_file("t2r-mown-hand-only.txt", &ho, &ho_at)) {
        int held = cw && (cw == w || base_weapon(cw) == base_weapon(w));
        if (w && !held && mown_droppable(w, NULL)) { uint64_t ww = w, has = dc_call(fnv64("has-weapon?"), 1, &ww); if (has != ~0ULL && !(has & 0xff)) w = 0; }   // (stale: not in the inventory)
        static uint64_t scan_at, scan_w;
        if (!mown_droppable(w, NULL)) {
            if (GetTickCount64() - scan_at > 1000) {
                scan_at = GetTickCount64(); uint64_t prev = scan_w; scan_w = 0;
                uint64_t none = 0, anym = dc_call(0x79763b864843c645ULL /* player-has-non-basic-melee-weapon? */, 0, &none);
                if (anym != ~0ULL && (anym & 0xff))
                    for (size_t i = 0; i < sizeof MELEE_TAB / sizeof *MELEE_TAB && !scan_w; i++) {
                        uint64_t id = fnv64(MELEE_TAB[i].n);
                        if (!mown_droppable(id, NULL)) continue;
                        uint64_t has = dc_call(fnv64("has-weapon?"), 1, &id);
                        if (has != ~0ULL && (has & 0xff)) scan_w = id;
                    }
                if (scan_w != prev) { static int nl; if (LOGCAP(nl, 30)) xlog("melee own: inventory scan - %s %llx carried stowed (never held this life / g_last_melee %llx)", scan_w ? "melee weapon" : "no droppable melee", (unsigned long long)scan_w, (unsigned long long)g_last_melee); }
            }
            w = scan_w;
        } else scan_w = 0;
    }
    if (!mown_droppable(w, &n)) { *dur = 0; return 0; }
    uint64_t b = fnv64(n);
    int full = melee_dur_name(n); int64_t d = -1;
    if (cw && (cw == w || base_weapon(cw) == base_weapon(w))) { uint64_t none = 0, hp = dc_call(SID_GET_WEAPON_HEALTH, 0, &none); if (hp != ~0ULL && (int64_t)hp > 0 && (int64_t)hp < 1000) d = (int64_t)hp - (wb_lent(cw) && hp > 1 ? 1 : 0); }   // (wpnbreak.c's lent point is not durability - the others never see 2)
    else if (g_last_melee && base_weapon(g_last_melee) == base_weapon(w) && g_last_melee_hp > 0) d = g_last_melee_hp;
    else if (g_pdur_last.base && g_pdur_last.base == base_weapon(w) && g_pdur_last.dur > 0) d = g_pdur_last.dur;   // a stowed pickup never held: the durability it was picked up with
    if (full > 0 && d > full) d = full;
    *dur = (int16_t)d;
    return b;
}
static void mown_send_tick(void) {
    static uint64_t last_sid, last_ms, last_chk; static int16_t last_dur = -2; static uint8_t seq;
    uint64_t now = GetTickCount64();
    if (!g_send_tramp || now - last_chk < 250) return;
    last_chk = now;
    if ((local_hp() <= 0.0f && !g_downed) || g_in_spawn) return;        // dead / respawning: the receivers keep what we carried alive (downed: still sent)
    int16_t d = -1; uint64_t w = mown_self(&d);
    if (w == last_sid && d == last_dur && now - last_ms < 2000) return;
    if (w != last_sid || d != last_dur) { static int nl; if (LOGCAP(nl, 60)) xlog("melee own: we carry %s (%llx), durability %d - sent (MSG_MOWN)", w ? (melee_class_of(w, NULL) >= 0 ? "a melee weapon" : "?") : "no droppable melee weapon", (unsigned long long)w, (int)d); }
    uint8_t m[12]; m[0] = 1; memcpy(m + 1, &w, 8); memcpy(m + 9, &d, 2); m[11] = seq++;
    g_send_tramp(MSG_MOWN, m, sizeof m, 0xff);
    last_sid = w; last_dur = d; last_ms = now;
}
static void mown_recv(uint32_t slot, const uint8_t *b, uint64_t len) {
    if (slot >= T2R_MAX_PEERS || !b || len < 11 || b[0] != 1) return;
    uint64_t w; int16_t d; memcpy(&w, b + 1, 8); memcpy(&d, b + 9, 2);
    if (w && !mown_droppable(w, NULL)) w = 0;                               // (an id we do not know as a droppable melee: nothing)
    if (w && g_mown[slot].forget_sid == w && GetTickCount64() - g_mown[slot].forget_ms < 5000) return;
    if (w != g_mown[slot].sid || d != g_mown[slot].dur) { static int nl; if (LOGCAP(nl, 80)) xlog("melee own: slot %u carries %llx, durability %d", slot, (unsigned long long)w, (int)d); }
    g_mown[slot].sid = w; g_mown[slot].dur = d; g_mown[slot].rx_ms = GetTickCount64();
}
static uint64_t drop_melee_named(const float *pos, const char *name, int count, const char *why);
static void mdrop_tick(void) {
    typedef uint8_t *(*fn_peer)(uint32_t);
    static int in_match;
    if (match_substate() != 6) { if (in_match) { memset(g_mown, 0, sizeof g_mown); in_match = 0; } return; }
    in_match = 1;
    mown_send_tick();
    uint32_t me = *(uint32_t *)VMA(0x180138090);
    uint64_t now = GetTickCount64();
    for (uint32_t s = 0; s < T2R_MAX_PEERS; s++) {
        if (s == me) continue;
        uint8_t *peer = ((fn_peer)t2r_peer)(s);
        if (!peer || !peer[4]) continue;                                   // (no puppet this frame: the state waits - g_grace_dead is not updated either)
        int dead = g_grace_dead[s] != 0;
        if (!dead && g_mown[s].rx_ms && now - g_mown[s].rx_ms < MOWN_FRESH_MS) { g_mown[s].a_sid = g_mown[s].sid; g_mown[s].a_dur = g_mown[s].dur; g_mown[s].a_ms = now; }
        if (dead && !g_mown[s].was_dead) {
            g_mown[s].died_t60 = g_t60; g_mown[s].pend = 0; g_mown[s].hold = 0;
            const char *n = NULL;
            if (!mown_off() && g_mown[s].a_sid && now - g_mown[s].a_ms < 60000 && mown_droppable(g_mown[s].a_sid, &n)) {   // (the last report while it lived: a bleed-out can be 15 s after it)
                g_mown[s].pend = 1; snprintf(g_mown[s].drop_n, sizeof g_mown[s].drop_n, "%s", n);
                xlog("melee drop: slot %u died carrying %s (durability %d) - its weapon drops at the body", s, n, (int)g_mown[s].a_dur);
            } else if (g_peer_melee[s] >= 0 && (mown_off() || !g_mown[s].a_ms)) {
                g_mown[s].pend = 2;
                xlog("melee drop: slot %u died - %s: the old pool drop (style %d)", s, mown_off() ? "t2r-no-mown-drop.txt" : "no MSG_MOWN from it (older build)", (int)g_peer_melee[s]);
            } else xlog("melee drop: slot %u died - %s", s, g_mown[s].a_ms ? "it carried no droppable melee weapon" : "no MSG_MOWN from it, no finisher style seen: nothing drops");
        }
        g_mown[s].was_dead = dead;
        if (!dead) { g_mown[s].pend = 0; g_mown[s].hold = 0; continue; }
        if (g_mown[s].pend) {
            uint64_t age = g_t60 - g_mown[s].died_t60;
            int busy = psync_busy_slot(s) || gx_busy_slot(s);
            if (age < MOWN_DROP_DELAY || (busy && age < MOWN_DROP_MAX)) continue;
            // v5-mown2: the post-death sweep (feature_no_puppet_drops: kill-dropped-weapons-in-sphere, 5 m, from 20 / 200 ticks to 420 after the death)
            // never ran before this build (g_grace_dead was never set); our drop waits for its first pass, the later passes skip this slot (mown_sweep_hold)
            if (g_mown[s].pend == 1 && g_no_drops && !mown_sweep_off() && g_mown[s].swept_t60 < g_mown[s].died_t60 && age < 480) continue;
            const float *pos = kill_body_locator(s);
            if (!pos) { if (age < MOWN_DROP_MAX + 60) continue; xlog("melee drop: slot %u - no body position %llu frames after the death: nothing dropped", s, (unsigned long long)age); g_mown[s].pend = 0; continue; }
            float p[3] = {pos[0], pos[1], pos[2]};
            if (g_mown[s].pend == 1) {
                int full = melee_dur_name(g_mown[s].drop_n), d = g_mown[s].a_dur > 0 ? g_mown[s].a_dur : full;
                if (full > 0 && d > full) d = full;
                char why[64]; snprintf(why, sizeof why, "slot %u's own weapon, %llu frames after its death%s", s, (unsigned long long)age, busy ? " (pair cap)" : "");
                g_mown[s].drop_h = drop_melee_named(p, g_mown[s].drop_n, d, why);
                g_mown[s].chk_t60 = g_t60 + 120;
                g_mown[s].hold = 1;                                                // the sweep leaves this body alone from here (mown_sweep_hold)
            } else if (g_peer_melee[s] >= 0) drop_melee_pickup(p, g_peer_melee[s]);
            g_peer_melee[s] = -1;
            g_mown[s].pend = 0; g_mown[s].a_sid = 0;
        }
        if (g_mown[s].chk_t60 && g_t60 >= g_mown[s].chk_t60) {
            g_mown[s].chk_t60 = 0;
            xlog("melee drop: slot %u's %s %s 2 s after the spawn (handle %llx)", s, g_mown[s].drop_n, drops_alive(g_mown[s].drop_h) ? "still lies there" : "is GONE (taken or removed)", (unsigned long long)g_mown[s].drop_h);
        }
    }
}
