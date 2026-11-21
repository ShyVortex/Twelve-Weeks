// 2013 Factions FLAMETHROWER on TLOU2's own flamethrower (weapon id `flamethrower`, Abby's).
// Included from t2r-ext.c (after explosives2013.c). Everything here is OFFLINE-WRITTEN, nothing of it has run in the game yet: every number
// that is not read from a data file is marked INFERRED, every log line below names what to look for in an A/B test.
//
// What the engine does with the gun (read from the game's files): ProcessWeaponFlamethrower (weapon-art def +0x08), a firearm def with
// interval 0.025 s and a magazine of 100 (firearm def +0x98), anim states flamethrower-fire-start / -loop / -end, flame stream = the particle
// groups flamethrower-fire-shell / -muzzle / -ignition-fire / -drip-flames / -initial-liquid (pak68 part-actor-flamethrower), damage by
// FlameBalls (flame-balls.cpp) and the `flamethrower-burn` explosion-settings. weapon-damages.bin `flamethrower`: 0 for every target kind
// except one that is 1 (read with tools/features, dc_data_patches.verify_flame) - the engine's flame deals no direct damage. So the engine
// flame is cosmetic + local; the 2013 numbers are applied here:
//   2013 data (TLOU1 PS3 net10.bin `flamethrower` d5078efe; tools/re/t1dc.py; Factions_MP.wiki):
//     firearm def: interval 0 (continuous), magazine i100 (+0x70), range field +0x5c = 6.5 (the other guns 48..200: INFERRED = range in metres)
//     *net-weapon-damage-settings* flamethrower: kind `player` cde4b742 = 75, `default` f19e22dc = 10000, `object` 62dab966 = 180
//     wiki: 2 LP, 240 parts, starting ammunition 30, magazine 100, ammo 30 for 360; "[..] Flamethrowers [..] will instantly kill enemies rather than
//     incapacitate them" (so: no down - the hit that would down kills; see recv_hit_hook)
//     net10 *ammo* flamethrower max 100
// Shooter side (this file): while the flamethrower is held and FIRING (player-is-firing? or the clip dropping) a damage tick of FL_DMG (75, the
// `player` damage) goes to every enemy puppet inside the flame volume every FL_TICK_S (0.1 s, INFERRED from the firearm def's 0.1 at +0x148),
// as our normal type-3 hit (weapon `flamethrower`, ammo `ammo-flamethrower`), after the same armour absorb as every gun hit
// (armor_absorb_peer: vest), with a clear line (world ray), no teammates (friendly fire), none after the match ended, none on a respawning /
// dead puppet. The volume: a cone from the muzzle along the camera's aim, FL_RANGE (6.5 m) long, lateral radius FL_R0 + FL_SPREAD * distance
// (INFERRED: 0.30 m + 0.14 / m; the flame's real shape is the engine's particle collision).
// Victim side: recv_hit_hook turns the hit that would down us into a kill (like the Military Sniper); dmg_probe zeroes every engine damage event
// that names the flamethrower (our own engine flame on a puppet, a puppet's engine flame on us) so only these ticks hurt.
// Peers (MSG_FLAME 0x90): [u8 on] sent on the edge and every 0.25 s while firing; the receiver notes the sender as flaming for 0.8 s. The
// engine already replicates every shot (winmm NEVT_FIRE_SHOT -> npc-fire-weapon on the puppet) - whether that makes the puppet's flamethrower
// flame is unverified, so npc-fire-weapon is hooked to SEE it: while a puppet is flaming (MSG_FLAME) and no engine fire on it was seen for 0.5 s,
// flame_fx_tick spawns the flame particles at its weapon hand joint itself (fallback; t2r-no-flame-fx.txt = never).
// Switches: t2r-no-flame.txt next to the exe = the whole feature off (no damage, no message), T2R_FLAME=0 at build = not built (no row, no
// MP level adds), t2r-old-purchasables.txt = no row. Tunables: t2r-flame.txt "dmg tick_s range r0 spread" (re-read when it changes).
#define MSG_FLAME 0x90             // peer msg (ours): [u8 1 firing / 0 stopped] - the sender's flamethrower flame
#define FLAME_START_CLIP 30        // wiki: starting ammunition 30 (the magazine of 100 is the tank's size; the clip starts at 30)
static float g_fl_dmg = 20.0f, g_fl_tick = 0.25f,   /* 75 / 0.1 s killed in 0.12 s - now ~1.25 s from full (tunable t2r-flame.txt) */ g_fl_range = 6.5f, g_fl_r0 = 0.30f, g_fl_spread = 0.14f;
static int g_fl_fx_off = -1;
static uint64_t g_fl_cfg_chk;
static struct { uint64_t t60; uint8_t on; } g_fl_peer[T2R_MAX_PEERS];       // MSG_FLAME state per slot
static uint64_t g_fl_eng[T2R_MAX_PEERS];                                    // g_t60 of the last engine npc-fire-weapon seen on that slot's puppet
static uint64_t g_fl_hit_t60[T2R_MAX_PEERS];                                // our last flame tick on that slot's puppet (g_t60)
static fn_dccall g_fl_fire_orig;                                            // npc-fire-weapon (hooked to see the engine's puppet fire)
static int g_fl_stat_ticks, g_fl_stat_hits, g_fl_stat_blocked, g_fl_stat_armour; static float g_fl_stat_dmg;
static int g_fl_firing, g_fl_dbg_isf, g_fl_dbg_clip;
static uint64_t g_fl_ray_job[T2R_MAX_PEERS], g_fl_ray_frame[T2R_MAX_PEERS], g_fl_next_ms[T2R_MAX_PEERS], g_fl_mark_ms[T2R_MAX_PEERS];
static uint64_t g_fl_send_t60; static int g_fl_off_sends;

static int flame_is_gun(uint64_t w) { return w && w != ~0ULL && base_weapon(w) == fnv64(FLAME_ID); }
static int flame_hit_recent(uint32_t slot) { return slot < T2R_MAX_PEERS && g_fl_hit_t60[slot] && g_t60 - g_fl_hit_t60[slot] < 90; }   // (feature_puppet_no_burn: keep their burning)
static void flame_cfg(void) {
    if (g_fl_off >= 0 && g_frame - g_fl_cfg_chk < 120) return;
    g_fl_cfg_chk = g_frame ? g_frame : 1;
    FILE *f = exe_side_open("t2r-no-flame.txt", "r");
    int off = f != NULL; if (f) fclose(f);
    if (off != g_fl_off) xlog("flame: %s (t2r-no-flame.txt)", off ? "OFF - no damage ticks, no MSG_FLAME" : "on");
    g_fl_off = off;
    f = exe_side_open("t2r-no-flame-fx.txt", "r");
    g_fl_fx_off = f != NULL; if (f) fclose(f);
    f = exe_side_open("t2r-flame.txt", "r");
    if (f) {
        float d, t, r, r0, sp;
        if (fscanf(f, "%f %f %f %f %f", &d, &t, &r, &r0, &sp) == 5 && d > 0 && d < 1000 && t >= 0.02f && t < 2 && r > 0.5f && r < 40 && r0 >= 0 && r0 < 5 && sp >= 0 && sp < 2) {
            if (d != g_fl_dmg || t != g_fl_tick || r != g_fl_range || r0 != g_fl_r0 || sp != g_fl_spread)
                xlog("flame: t2r-flame.txt - tick %.0f dmg every %.2f s, range %.1f m, cone radius %.2f m + %.2f / m", d, t, r, r0, sp);
            g_fl_dmg = d; g_fl_tick = t; g_fl_range = r; g_fl_r0 = r0; g_fl_spread = sp;
        }
        fclose(f);
    }
}
// the engine's puppet fire (winmm replays every shot of a remote player as npc-fire-weapon on its puppet).
// A/B (run 6, B [56066]-[56077]): the replay on a puppet holding the flamethrower crashed the victim 10 frames later -
// EXCEPTION c0000005 at tlou-ii.exe+117efa2 on a job thread, a read of [rsi+0x2f88] with rsi = 0. The caller (exe+0x1191488) takes the weapon's
// owner through the NPC class cast 0x140da5c20 and passes the result on unchecked; a player puppet is not an NPC class object, so the flamethrower's
// NPC fire path gets NULL (no TLOU2 NPC carries a flamethrower: that path never saw any other owner). The replay draws no flame on a puppet
// anyway (clip; flame_fx_tick draws the stream), so for a flamethrower puppet it is swallowed here. Other guns pass unchanged.
// t2r-flame-npc-fire.txt next to the exe = let it through (crash test only).
static int g_fl_npc_fire_ok = -1;
static void flame_npc_fire_hook(uint64_t *ret, int argc, uint64_t *argv, uint64_t sec) {
    typedef uint8_t *(*fn_peer)(uint32_t);
    if (argc >= 1 && g_t60) {
        uint64_t h = argv[0];
        for (uint32_t sl = 0; sl < T2R_MAX_PEERS; sl++) {
            uint8_t *peer = ((fn_peer)t2r_peer)(sl);
            if (peer && peer[4] && *(uint64_t *)(peer + 0x60) == h) {
                uint64_t held = 0; memcpy(&held, peer + 0x91, 8);
                if (flame_is_gun(held)) {
                    static int n;
                    if (g_fl_npc_fire_ok < 0) { FILE *f = exe_side_open("t2r-flame-npc-fire.txt", "r"); g_fl_npc_fire_ok = f != NULL; if (f) fclose(f); }
                    if (!g_fl_eng[sl] && n++ < 6)
                        xlog("flame: slot %u fires its flamethrower - the engine's npc-fire-weapon replay on its puppet is %s", sl,
                             g_fl_npc_fire_ok ? "let through (t2r-flame-npc-fire.txt: crash test)" : "swallowed (NPC fire path on a non-NPC owner = crash exe+117efa2)");
                    g_fl_eng[sl] = g_t60;
                    if (!g_fl_npc_fire_ok) { if (ret) ret[0] = 0; return; }
                }
                break;
            }
        }
    }
    g_fl_fire_orig(ret, argc, argv, sec);
}
static void flame_install_once(void) {
    static int done;
    if (done) return;
    done = 1;
    g_fl_fire_orig = hook_rec8(fnv64("npc-fire-weapon"), flame_npc_fire_hook);
    xlog("flame: npc-fire-weapon %s (puppet flame fallback %s)", g_fl_fire_orig ? "hooked (engine puppet fire is noted)" : "NOT hookable (no rec+8 entry)",
         g_fl_fire_orig ? "armed" : "left to the engine");
}
// the aim: camera direction through the reticle; origin = the held flamethrower's world position + 0.6 m along the aim (the muzzle end), else our
// locator + 1.4 m
static int flame_aim(float O[3], float D[3]) {
    typedef uint8_t *(*fn_me)(void);
    uint64_t none = 0, rd = dc_call(fnv64("camera-get-dir-through-reticle"), 0, &none);
    if (!rd || rd == ~0ULL || IsBadReadPtr((void *)rd, 12)) return 0;
    memcpy(D, (void *)rd, 12);
    float l = __builtin_sqrtf(D[0] * D[0] + D[1] * D[1] + D[2] * D[2]);
    if (!(l > 0.5f) || !(l < 1.5f)) return 0;
    D[0] /= l; D[1] /= l; D[2] /= l;
    uint8_t *me = ((fn_me)VMA(0x180050390))();
    float t[8];
    uint8_t *w = player_weapon(me);
    if (w && proc_world(w, t) && t[0] == t[0] && t[1] == t[1] && t[2] == t[2]) { O[0] = t[0]; O[1] = t[1]; O[2] = t[2]; }
    else {
        float b[16];
        const float *pl = player_locator(b);
        if (!pl) return 0;
        O[0] = pl[0]; O[1] = pl[1] + 1.4f; O[2] = pl[2];
    }
    O[0] += D[0] * 0.6f; O[1] += D[1] * 0.6f; O[2] += D[2] * 0.6f;
    return 1;
}
// shooter: firing = the engine says so, or the clip dropped in the last 0.25 s (the flame drains 1 round per 0.025 s)
static int g_fl_prev_clip = -1; static uint64_t g_fl_drop_f;
static int flame_firing(void) {
    int clip = ammo_clip();
    if (clip >= 0 && g_fl_prev_clip >= 0 && clip < g_fl_prev_clip) g_fl_drop_f = g_frame ? g_frame : 1;
    g_fl_prev_clip = clip;
    uint64_t none = 0, r = dc_call(fnv64("player-is-firing?"), 0, &none);
    int isf = r != ~0ULL && (r & 0xff);
    g_fl_dbg_isf = isf; g_fl_dbg_clip = clip;
    if (clip == 0) return 0;
    return (g_fl_drop_f && g_frame - g_fl_drop_f <= 15) || isf;
}
static void flame_send(int on) {
    if (!g_send_tramp) return;
    uint8_t m[1] = {(uint8_t)on};
    g_send_tramp(MSG_FLAME, m, 1, 0xff);
}
static void flame_recv(uint32_t from, const uint8_t *buf, uint64_t len) {
    if (from >= T2R_MAX_PEERS || !buf || len < 1) return;
    static int n;
    if (g_fl_peer[from].on != (buf[0] != 0) && n++ < 30) xlog("flame: slot %u flamethrower %s", from, buf[0] ? "FIRING" : "stopped");
    g_fl_peer[from].on = buf[0] != 0;
    g_fl_peer[from].t60 = g_t60 ? g_t60 : 1;
}
// one damage tick on a puppet: the hit packet (armour absorbed first), the hit marker
static void flame_hit(uint32_t sl, uint8_t *peer, uint8_t *proc, float along, float lat) {
    uint64_t w = fnv64(FLAME_ID), ammo = fnv64("ammo-flamethrower");
    float d0 = g_fl_dmg, d = armor_absorb_peer(sl, 0, 0, d0);
    uint8_t m[0x16];
    memcpy(m, &w, 8); memcpy(m + 8, &ammo, 8); memcpy(m + 16, &d, 4);
    m[20] = 0; m[21] = 0;
    hr_send_hit(m, sizeof m, (uint8_t)sl);
    g_fl_hit_t60[sl] = g_t60 ? g_t60 : 1;
    dr_note_shot(sl, w, d);      // deathreact.c: our last flame tick on that puppet (its burning death plays the flame's side when it dies)
    g_fl_stat_ticks++; g_fl_stat_dmg += d; if (d < d0 - 0.01f) g_fl_stat_armour++;
    uint64_t now = GetTickCount64();
    if (now - g_fl_mark_ms[sl] >= 350) { g_fl_mark_ms[sl] = now; tac_hit_marker(proc, 0, w, d); }
    static int n;
    if (LOGCAP(n, 120)) xlog("flame: tick on slot %u - %.0f (armour took %.0f), %.1f m along the flame, %.2f m off its axis, their hp %.1f", sl, d, d0 - d, along, lat, puppet_hp(sl, *(uint64_t *)(peer + 0x60)));
}
static void flame_scan(const float *O, const float *D) {
    typedef uint8_t *(*fn_peer)(uint32_t);
    typedef void *(*fn_proc)(uint64_t);
    uint32_t me = *(uint32_t *)VMA(0x180138090);
    uint64_t now = GetTickCount64();
    for (uint32_t sl = 0; sl < T2R_MAX_PEERS; sl++) {
        if (sl == me) continue;
        uint8_t *peer = ((fn_peer)t2r_peer)(sl);
        uint64_t h = peer ? *(uint64_t *)(peer + 0x60) : 0;
        if (!h || !peer[4] || peer[5] || (is_teammate(sl) && !g_ff_off) || g_puppet_dead_here[sl] || g_grace_dead[sl] || g_t60 < g_grace_until[sl]) { g_fl_ray_job[sl] = 0; continue; }
        uint8_t *proc = ((fn_proc)VMA(0x18000A200))(h);
        float pp[3];
        if (!proc || !proc_pos(proc, pp)) { g_fl_ray_job[sl] = 0; continue; }
        static const float STAND[3] = {0.35f, 0.95f, 1.5f}, LIE[1] = {0.25f};
        int np = g_peer_downed[sl] == 1 ? 1 : 3;
        float bestk = 1e9f, bp[3] = {0}, bal = 0, blat = 0;
        for (int k = 0; k < np; k++) {
            float p[3] = {pp[0], pp[1] + (np == 1 ? LIE[0] : STAND[k]), pp[2]};
            float v[3] = {p[0] - O[0], p[1] - O[1], p[2] - O[2]};
            float al = v[0] * D[0] + v[1] * D[1] + v[2] * D[2];
            if (al < 0.0f || al > g_fl_range) continue;
            float px = v[0] - al * D[0], py = v[1] - al * D[1], pz = v[2] - al * D[2];
            float lat = __builtin_sqrtf(px * px + py * py + pz * pz), lim = g_fl_r0 + g_fl_spread * al;
            if (lat > lim) continue;
            float kk = lat / lim;
            if (kk < bestk) { bestk = kk; memcpy(bp, p, 12); bal = al; blat = lat; }
        }
        if (bestk > 1e8f) { g_fl_ray_job[sl] = 0; continue; }
        if (now < g_fl_next_ms[sl]) continue;
        // line of sight (muzzle -> the body point): the ray is kicked on one frame, its verdict read on the next (as winmm's own shot check does)
        if (!g_fl_ray_job[sl]) {
            if (g_fl_ray_frame[sl] == g_frame) continue;
            g_fl_ray_job[sl] = world_ray_kick(O, bp);
            g_fl_ray_frame[sl] = g_frame;
            if (g_fl_ray_job[sl]) continue;                                // (no job = the ray service refused: counts as clear, never a hidden block)
        } else {
            if (g_fl_ray_frame[sl] == g_frame) continue;
            float t = ray_t(g_fl_ray_job[sl]);
            g_fl_ray_job[sl] = 0;
            // A/B run 8 (A 1.5 m in front of B, every ray "a wall is 54-68% of the way", 0 ticks in a 2.8 s stream): at close range the ray
            // meets the victim's own body collision 0.3-0.5 m before the body point. A hit within FL_BODY_R of the point is the body, not a wall
            // (as the shot check's body radius skip).
            float rl = __builtin_sqrtf((bp[0] - O[0]) * (bp[0] - O[0]) + (bp[1] - O[1]) * (bp[1] - O[1]) + (bp[2] - O[2]) * (bp[2] - O[2]));
            if (t >= 0.0f && t < 0.95f && (1.0f - t) * rl > 0.6f) {
                g_fl_stat_blocked++;
                g_fl_next_ms[sl] = now + 60;
                static int nb;
                if (LOGCAP(nb, 20)) xlog("flame: slot %u in the cone but a wall is %.0f%% of the way - no tick", sl, t * 100.0f);
                continue;
            }
        }
        g_fl_next_ms[sl] = now + (uint64_t)(g_fl_tick * 1000.0f);
        flame_hit(sl, peer, proc, bal, blat);
        g_fl_stat_hits++;
    }
}
static void flame_stat_end(const char *why) {
    xlog("flame: stream over (%s) - %d ticks (%d with armour absorbing), %.0f damage sent, %d blocked by walls", why, g_fl_stat_ticks, g_fl_stat_armour, g_fl_stat_dmg, g_fl_stat_blocked);
    g_fl_stat_ticks = g_fl_stat_hits = g_fl_stat_blocked = g_fl_stat_armour = 0; g_fl_stat_dmg = 0;
}
// receiver, fallback: a flaming puppet whose engine fire we never see gets the flame particles spawned at its weapon hand joint
static void flame_fx_tick(void) {
    // the engine's npc-fire-weapon replay draws NO flame on the puppet; the stream is ours: flamethrower-fire-shell at the
    // puppet's weapon hand every 0.1 s while it fires, each one KILLED after 0.25 s (kill-particles) so none stays in the world and burns (in earlier captures
    // unkilled shells hung in the air and set players alight). If a kill ever fails, the shell is not spawned again.
    typedef uint8_t *(*fn_peer)(uint32_t);
    static uint64_t next[T2R_MAX_PEERS]; static int nl, kill_bad;
    static struct { uint64_t h, t60; } live[64]; static int nlive;
    uint32_t me = *(uint32_t *)VMA(0x180138090);
    for (int i = 0; i < nlive; ) {                      // expire our stream pieces
        if (g_t60 - live[i].t60 >= 15) {
            uint64_t hh = live[i].h, r = dc_call(fnv64("kill-particles"), 1, &hh);
            if (r == ~0ULL && !kill_bad) { kill_bad = 1; xlog("flame: kill-particles refused the stream handle %llx - stream spawning OFF (an unkillable piece would stay)",(unsigned long long)hh); }
            live[i] = live[--nlive];
        } else i++;
    }
    if (g_fl_fx_off || !g_fl_fire_orig) return;
    for (uint32_t sl = 0; sl < T2R_MAX_PEERS; sl++) {
        if (sl == me || !g_fl_peer[sl].on || g_t60 - g_fl_peer[sl].t60 > 48) { if (sl != me && g_fl_peer[sl].on && g_t60 - g_fl_peer[sl].t60 > 48) g_fl_peer[sl].on = 0; continue; }
        uint8_t *peer = ((fn_peer)t2r_peer)(sl);
        uint64_t h = peer ? *(uint64_t *)(peer + 0x60) : 0;
        if (!h || !peer[4] || peer[5]) continue;
        uint64_t held = 0; memcpy(&held, peer + 0x91, 8);
        if (!flame_is_gun(held)) continue;
        if (g_t60 < next[sl]) continue;
        next[sl] = g_t60 + 6;
        // the muzzle flame kept looping after the puppet stopped - it is a looping effect too: killed after 0.25 s like the shell.
        // Both pieces are spawned ONLY when their handle can be kept for the kill. Before, the muzzle was spawned even with the list full
        // (24 handles: 4+ players flaming at once, each ~6 live pieces) or after a refused kill, and such a muzzle was never killed - a flame that
        // stays on a bystander's screen after the shooter stopped. The list now holds 64 (7 shooters x 6 pieces with room).
        uint64_t r1 = 0, r2 = 0;
        if (kill_bad || nlive >= (int)(sizeof live / sizeof *live) - 1) {
            static int nf; if (LOGCAP(nf, 6)) xlog("flame: slot %u flaming but no stream spawned (%s)", sl, kill_bad ? "kill-particles refused earlier" : "kill list full");
            continue;
        }
        r1 = armor_fx_spawn(fnv64("flamethrower-fire-muzzle"), h, "r_hand_prop");
        if (r1 && r1 != ~0ULL) { live[nlive].h = r1; live[nlive].t60 = g_t60; nlive++; }
        {
            r2 = armor_fx_spawn(fnv64("flamethrower-fire-shell"), h, "r_hand_prop");
            if (r2 && r2 != ~0ULL) { live[nlive].h = r2; live[nlive].t60 = g_t60; nlive++; }
        }
        if (LOGCAP(nl, 12)) xlog("flame: slot %u flaming - our stream at r_hand_prop: muzzle -> %llx, shell -> %llx (killed after 0.25 s)", sl, (unsigned long long)r1, (unsigned long long)r2);
    }
}
// after the spawn kit: the clip starts at the wiki's 30 (the tank holds 100)
static void flame_after_spawn(void) {
    g_fl_prev_clip = -1; g_fl_drop_f = 0;                  // the clip set below is no shot
    if (g_fl_off > 0) return;
    for (int i = 0; i < g_spawn_ngun; i++)
        if (flame_is_gun(g_spawn_guns[i])) {
            uint64_t a[2] = {(uint64_t)FLAME_START_CLIP, g_spawn_guns[i]};
            uint64_t r = dc_call(fnv64("set-player-weapon-clip-ammo"), 2, a);
            uint64_t w = g_spawn_guns[i], a1[2] = {w, 0};
            uint64_t cl = dc_call(fnv64("get-player-weapon-ammo-in-clip"), 1, a1);
            xlog("flame: spawn - clip set to %d (wiki: starting ammunition 30, magazine 100) -> %llx, clip now %lld", FLAME_START_CLIP, (unsigned long long)r, (long long)(cl == ~0ULL ? -1 : (int64_t)(uint32_t)cl));
        }
}
static void flame_tick(void) {
    flame_cfg();
    if (match_substate() != 6) {
        if (g_fl_firing) { g_fl_firing = 0; flame_stat_end("left the match"); }
        memset(g_fl_peer, 0, sizeof g_fl_peer); memset(g_fl_eng, 0, sizeof g_fl_eng); memset(g_fl_ray_job, 0, sizeof g_fl_ray_job);
        flame_fx_tick();                // no peer flames now: only expires (kills) the stream shells still alive
        return;
    }
    flame_install_once();
    if (g_fl_off) { if (g_fl_firing) { g_fl_firing = 0; flame_send(0); } return; }
    flame_fx_tick();
    uint64_t cw = current_weapon();
    int held = flame_is_gun(cw);
    if (!held) { g_fl_prev_clip = -1; g_fl_drop_f = 0; }
    int fire = 0;
    float O[3], D[3];
    if (held && !g_downed && !g_down_dying && !g_ff_ended && !psync_active() && local_hp() > 0) fire = flame_firing();
    if (fire != g_fl_firing) {
        g_fl_firing = fire;
        xlog("flame: our flamethrower %s (player-is-firing? %d, clip %d)", fire ? "FIRING" : "stopped", g_fl_dbg_isf, g_fl_dbg_clip);
        flame_send(fire);
        g_fl_send_t60 = g_t60; g_fl_off_sends = fire ? 0 : 2;
        if (!fire) flame_stat_end("trigger released / empty / switched");
    } else if (fire && g_t60 - g_fl_send_t60 >= 15) { flame_send(1); g_fl_send_t60 = g_t60; }       // keep-alive (the receiver expires it after 0.8 s)
    else if (!fire && g_fl_off_sends > 0) { g_fl_off_sends--; flame_send(0); }                       // the stop twice more (a lossy relay)
    if (fire && flame_aim(O, D)) flame_scan(O, D);
}
