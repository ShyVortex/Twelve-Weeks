// Dragon's Buckshot (GEAR UP purchasable; re/weapons-1117.md 3.3): Abby's Double Barrel (weapon id DRAGON_ID = shotgun-dragon, a data clone of
// shotgun-baserri-over-under: same model, anims, sounds, firearm def; base_weapon() answers the Double Barrel for it, so the shot's damage is the
// DB's own 2013 curve, SG_2013) whose shells set the target alight.
// Included from t2r-ext.c after deathreact.c (uses its BD_FX particle list).
//
// Shooter side (authoritative, like the flamethrower ticks of flame2013.c):
//   dragon_note_sent(): every type-3 hit WE send passes hr_send_hit; a Dragon shell hit (weapon DRAGON_ID, not one of our burn ticks, damage > 0) on a
//   standing enemy ignites that slot: the burn ticks DG_TICK_DMG every DG_TICK_S for DG_DUR_S (a new hit restarts the time, never stacks).
//   Each tick is our normal hit packet (weapon DRAGON_ID, ammo DG_AMMO = the kill feed names the Dragon), after the victim's armour absorb
//   (armor_absorb_peer, like every gun hit). The burn stops when the victim goes DOWN (executions stay E on the downed: the burn never takes the
//   down's execution away), dies, respawns, or the match ends.
//   MSG_DRAGON 0xB7 [u8 victim slot][u8 burn tenths of a second] to everyone at ignite / refresh / stop (0 = out).
// Every screen (the shooter's too): the victim burns - a puppet gets the engine's own burn state (npc-set-on-fire "person-on-fire", the one SP's
// fire uses; feature_puppet_no_burn leaves it lit while dragon_burning), our own body the hand-spawned fire groups of deathreact.c (BD_FX). Both
// are put out when the burn ends.
// Numbers: TLOU2 has no player incendiary shell data and 2013 had no incendiary ammo. The burn RATE is 2013's own fire damage to players,
// *molotov-flame-damage-online* 20 hp/s (explosions.bin, EX13_FIRE_DPS): 10 hp every 0.5 s. Its LENGTH (2.0 s = 40 hp) is a balance choice:
// a point-blank shell (DB cap 60) + the full burn = 100 = a down after ~2 s (the plain DB's 2nd shell downs at 0.9 s); a mid-range shell + burn
// does not. Tunable: t2r-dragon.txt "dmg tick_s dur_s" next to the exe. t2r-no-dragon-burn.txt = shells only (no burn, no fx).
#define MSG_DRAGON 0xB7
#define DG_AMMO "ammo-dragon-fire"
static float g_dg_dmg = 10.0f, g_dg_tick = 0.5f, g_dg_dur = 2.0f;
static int g_dg_off = -1;
static uint64_t g_dg_cfg_frame;
static struct { uint64_t until_ms, next_ms, h; int ticks; float total; } g_dg_shoot[T2R_MAX_PEERS];   // our burns on other slots (shooter side)
static struct { uint64_t until_ms, h; int lit, nh; uint64_t fx[BD_MAXH]; } g_dg_vis[BD_N];          // what burns on our screen (slot, or T2R_US = us)
static int g_dg_sending_tick;                  // our own burn tick is passing hr_send_hit (no re-ignite)

static void dragon_cfg(void) {
    if (g_dg_off >= 0 && g_frame - g_dg_cfg_frame < 120) return;
    g_dg_cfg_frame = g_frame ? g_frame : 1;
    FILE *f = exe_side_open("t2r-no-dragon-burn.txt", "r");
    int off = f != NULL; if (f) fclose(f);
    if (off != g_dg_off) xlog("dragon: burn %s (t2r-no-dragon-burn.txt)", off ? "OFF - shells only" : "on");
    g_dg_off = off;
    f = exe_side_open("t2r-dragon.txt", "r");
    if (f) {
        float d, t, u;
        if (fscanf(f, "%f %f %f", &d, &t, &u) == 3 && d >= 0 && d < 200 && t >= 0.1f && t <= 5 && u >= 0 && u <= 20) {
            if (d != g_dg_dmg || t != g_dg_tick || u != g_dg_dur) xlog("dragon: t2r-dragon.txt - burn %.0f every %.2f s for %.1f s", d, t, u);
            g_dg_dmg = d; g_dg_tick = t; g_dg_dur = u;
        }
        fclose(f);
    }
}
static int dragon_is_gun(uint64_t w) { return w && w == fnv64(DRAGON_ID); }
static int dragon_burning(uint32_t slot) { return slot < T2R_MAX_PEERS && g_dg_vis[slot].until_ms && GetTickCount64() < g_dg_vis[slot].until_ms; }

// ---- visuals (every screen)
static void dragon_fx_off(int idx, const char *why) {
    if (idx < 0 || idx >= BD_N || !g_dg_vis[idx].until_ms) return;
    for (int k = 0; k < g_dg_vis[idx].nh; k++) { uint64_t a[2] = {g_dg_vis[idx].fx[k], 0}; dc_call(fnv64("kill-particles"), 2, a); }
    if (g_dg_vis[idx].lit && idx != T2R_US) {
        typedef void *(*fn_proc)(uint64_t);
        uint64_t a[1] = {g_dg_vis[idx].h};
        if (g_dg_vis[idx].h && ((fn_proc)VMA(0x18000A200))(g_dg_vis[idx].h)) dc_call(fnv64("npc-put-out-fire"), 1, a);
    }
    xlog("dragon: %s %d burn out (%s), %d fire groups killed", idx == T2R_US ? "own body" : "slot", idx == T2R_US ? 0 : idx, why, g_dg_vis[idx].nh);
    memset(&g_dg_vis[idx], 0, sizeof g_dg_vis[idx]);
}
static void dragon_fx_on(int idx, uint64_t ent, float secs) {
    if (idx < 0 || idx >= BD_N || !ent || g_dg_off) return;
    uint64_t now = GetTickCount64();
    if (g_dg_vis[idx].until_ms && g_dg_vis[idx].h == ent) { g_dg_vis[idx].until_ms = now + (uint64_t)(secs * 1000.0f); return; }   // refresh
    dragon_fx_off(idx, "new burn");
    g_dg_vis[idx].h = ent; g_dg_vis[idx].until_ms = now + (uint64_t)(secs * 1000.0f);
    int ok = 0;
    if (idx != T2R_US) {          // a puppet: the engine's own burn state (fire fx + its burning loop), as SP's fire lights a person
        uint64_t a[3] = {ent, 0, fnv64("person-on-fire")};
        dc_call(fnv64("npc-set-on-fire"), 3, a);
        uint64_t p1 = ent, on = dc_call(fnv64("npc-is-on-fire?"), 1, &p1);
        g_dg_vis[idx].lit = on != ~0ULL && (on & 0xff);
    }
    if (!g_dg_vis[idx].lit)        // our own body (the engine burn would also hurt us) or a puppet the engine did not light: the fire groups by hand
        for (size_t i = 0; i < sizeof BD_FX / sizeof *BD_FX && g_dg_vis[idx].nh < BD_MAXH; i++) {
            uint64_t r = armor_fx_spawn(fnv64(BD_FX[i].p), ent, BD_FX[i].j);
            if (r && r != ~0ULL) { g_dg_vis[idx].fx[g_dg_vis[idx].nh++] = r; ok++; }
        }
    static int n;
    if (LOGCAP(n, 60)) xlog("dragon: %s %d set alight for %.1f s - engine burn state %s, %d fire groups by hand", idx == T2R_US ? "own body" : "slot",
                            idx == T2R_US ? 0 : idx, secs, g_dg_vis[idx].lit ? "ON" : "off", ok);
}
static void dragon_send(uint32_t victim, float secs) {
    if (!g_send_tramp) return;
    int t = (int)(secs * 10.0f + 0.5f); if (t < 0) t = 0; if (t > 250) t = 250;
    uint8_t m[2] = {(uint8_t)victim, (uint8_t)t};
    g_send_tramp(MSG_DRAGON, m, 2, 0xff);
}
static void dragon_show(uint32_t victim, float secs) {       // victim's slot -> our screen
    typedef uint8_t *(*fn_peer)(uint32_t);
    uint32_t me = *(uint32_t *)VMA(0x180138090);
    if (victim == me) { if (secs > 0) dragon_fx_on(T2R_US, SID_PLAYER, secs); else dragon_fx_off(T2R_US, "put out"); return; }
    if (victim >= T2R_MAX_PEERS) return;
    uint8_t *peer = ((fn_peer)t2r_peer)(victim);
    uint64_t h = peer ? *(uint64_t *)(peer + 0x60) : 0;
    if (secs > 0 && h) dragon_fx_on((int)victim, h, secs);
    else dragon_fx_off((int)victim, "put out");
}
static void dragon_recv(uint32_t from, const uint8_t *buf, uint64_t len) {
    if (from >= T2R_MAX_PEERS || !buf || len < 2 || match_substate() != 6) return;
    static int n;
    if (LOGCAP(n, 40)) xlog("dragon: slot %u says slot %u burns %.1f s", from, buf[0], buf[1] / 10.0f);
    dragon_show(buf[0], buf[1] / 10.0f);
}

// ---- shooter side
static void dragon_stop(uint32_t sl, const char *why) {
    if (sl >= T2R_MAX_PEERS || !g_dg_shoot[sl].until_ms) return;
    xlog("dragon: our burn on slot %u ends (%s) - %d ticks, %.0f damage sent", sl, why, g_dg_shoot[sl].ticks, g_dg_shoot[sl].total);
    memset(&g_dg_shoot[sl], 0, sizeof g_dg_shoot[sl]);
    dragon_send(sl, 0); dragon_show(sl, 0);
}
// hr_send_hit: every type-3 hit we send (winmm's own shot hits, our shotgun fixes)
static void dragon_note_sent(const uint8_t *buf, uint64_t len, uint32_t slot) {
    if (g_dg_sending_tick || !buf || len < 20 || slot >= T2R_MAX_PEERS) return;
    uint64_t w, ammo; float d;
    memcpy(&w, buf, 8); memcpy(&ammo, buf + 8, 8); memcpy(&d, buf + 16, 4);
    if (!dragon_is_gun(w) || ammo == fnv64(DG_AMMO) || !(d > 0.0f) || d >= 100000.0f) return;
    dragon_cfg();
    if (g_dg_off || g_dg_dur <= 0 || g_dg_dmg <= 0 || match_substate() != 6) return;
    typedef uint8_t *(*fn_peer)(uint32_t);
    uint8_t *peer = ((fn_peer)t2r_peer)(slot);
    uint64_t h = peer ? *(uint64_t *)(peer + 0x60) : 0;
    if (!h || g_peer_downed[slot] || g_puppet_dead_here[slot] || (is_teammate(slot) && !g_ff_off)) return;
    uint64_t now = GetTickCount64();
    int fresh = !g_dg_shoot[slot].until_ms;
    if (fresh) { memset(&g_dg_shoot[slot], 0, sizeof g_dg_shoot[slot]); g_dg_shoot[slot].next_ms = now + (uint64_t)(g_dg_tick * 1000.0f); }
    g_dg_shoot[slot].h = h;
    g_dg_shoot[slot].until_ms = now + (uint64_t)(g_dg_dur * 1000.0f);
    xlog("dragon: shell hit %.1f on slot %u - %s, burn %.0f every %.2f s for %.1f s", d, slot, fresh ? "set alight" : "burn restarted", g_dg_dmg, g_dg_tick, g_dg_dur);
    dragon_send(slot, g_dg_dur); dragon_show(slot, g_dg_dur);
}
static void dragon_tick(void) {
    typedef uint8_t *(*fn_peer)(uint32_t);
    typedef void *(*fn_proc)(uint64_t);
    dragon_cfg();
    uint64_t now = GetTickCount64();
    int inmatch = match_substate() == 6;
    for (uint32_t sl = 0; sl < T2R_MAX_PEERS; sl++) {
        if (!g_dg_shoot[sl].until_ms) continue;
        uint8_t *peer = ((fn_peer)t2r_peer)(sl);
        uint64_t h = peer ? *(uint64_t *)(peer + 0x60) : 0;
        if (!inmatch || g_dg_off) { dragon_stop(sl, inmatch ? "burn switched off" : "left the match"); continue; }
        if (h != g_dg_shoot[sl].h || !peer[4] || peer[5] || g_puppet_dead_here[sl] || g_grace_dead[sl]) { dragon_stop(sl, "dead / respawned"); continue; }
        if (g_peer_downed[sl]) { dragon_stop(sl, "went down - the execution stays theirs to take"); continue; }
        if (now >= g_dg_shoot[sl].until_ms) { dragon_stop(sl, "burnt out"); continue; }
        if (now < g_dg_shoot[sl].next_ms) continue;
        g_dg_shoot[sl].next_ms = now + (uint64_t)(g_dg_tick * 1000.0f);
        uint8_t *proc = ((fn_proc)VMA(0x18000A200))(h);
        uint64_t w = fnv64(DRAGON_ID), ammo = fnv64(DG_AMMO);
        float d0 = g_dg_dmg, d = armor_absorb_peer(sl, 0, 0, d0);
        uint8_t m[0x16];
        memcpy(m, &w, 8); memcpy(m + 8, &ammo, 8); memcpy(m + 16, &d, 4); m[20] = 0; m[21] = 0;
        g_dg_sending_tick = 1;
        hr_send_hit(m, sizeof m, (uint8_t)sl);
        g_dg_sending_tick = 0;
        dr_note_shot(sl, w, d);
        if (proc) tac_hit_marker(proc, 0, w, d);
        g_dg_shoot[sl].ticks++; g_dg_shoot[sl].total += d;
        static int n;
        if (LOGCAP(n, 120)) xlog("dragon: burn tick on slot %u - %.0f (armour took %.0f), their hp %.1f", sl, d, d0 - d, puppet_hp(sl, h));
    }
    // our screen: burns that ran out / bodies that went away
    for (int i = 0; i < BD_N; i++) {
        if (!g_dg_vis[i].until_ms) continue;
        int own = i == T2R_US;
        if (!inmatch) { dragon_fx_off(i, "left the match"); continue; }
        if (now >= g_dg_vis[i].until_ms) { dragon_fx_off(i, "burnt out"); continue; }
        if (own) { if (local_hp() <= 0 || g_downed) dragon_fx_off(i, g_downed ? "we went down" : "we died"); continue; }
        uint8_t *pe = ((fn_peer)t2r_peer)((uint32_t)i);
        uint64_t cur = pe ? *(uint64_t *)(pe + 0x60) : 0;
        if (cur != g_dg_vis[i].h || !((fn_proc)VMA(0x18000A200))(g_dg_vis[i].h) || g_puppet_dead_here[i] || g_peer_downed[i]) dragon_fx_off(i, "body gone / down / dead");
    }
}
