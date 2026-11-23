// privlobby.c - PRIVATE MATCH (re/private-lobby-1117.md): the 4th row of the FIND MATCH mode box (modepick.c MK_PRIV) opens the private
// lobby page to1/private13; its EDIT SETTINGS / CHOOSE MAP rows open to1/private13s (tools/features/private13_widgets.py). Included from t2r-ext.c
// after friends13.c (uses modepick.c's mk_search / g_mdpk_queued, gearup13.c's gu_fade / gu_rep / gu_fit, matchflow's MF_MAPS names).
//
// Server: daemon op 0xF8 [64 token][ver 1][sub][ascii arg] -> 0xF9 "k=v ..." (tools/private_lobby.py). One request at a time on its own short
// connection (worker thread, like modepick.c's 0xBC). Subs: 1 STATE, 2 CREATE, 3 JOIN <code>, 4 LEAVE, 5 SET <key=int | pool=hex | map=int>,
// 6 TEAM <member=team>, 7 KICK <member>, 8 START, 9 RULES (in a match), 10 CANCEL.
//
// Join method: a five-letter lobby code (JOIN WITH CODE). No Steam invite, no party auto-follow (follow-ups in the doc).
// Lobby launch: the owner's START sets the lobby launching (st=1, go+1); every member's ext seeing a new go pushes the search page (mk_search: winmm
// queues the player; the daemon forms the private match from the members only). After the match the lobby page opens again by itself.
// In the match: op 0xF8 sub 9 gives the match's rules (pm=1 ...) and the pv_* hooks apply them (parts, lives, invincibility, damage model, downed system, respawn
// timer, free crafting, friendly fire, radar, match time). Gun limits, AFK removal, ping limit, late join and the map are the daemon's side.
// Off: t2r-no-private.txt next to the exe (the mode box row dims and refuses). Log: 'private:'.
#define PL_OP 0xF8
#define PL_VER 1
enum { PL_S_STATE = 1, PL_S_CREATE, PL_S_JOIN, PL_S_LEAVE, PL_S_SET, PL_S_TEAM, PL_S_KICK, PL_S_START, PL_S_RULES, PL_S_CANCEL };
#define PL_NMEM 8
#define PL_CODE_LEN 5
#define PL_AUTO 255
#define PL_MAP_VOTE (-1)
#define PL_MAP_RANDOM (-2)

// ------------------------------------------------------------------ the rules (= tools/private_lobby.py RULES, same order)
enum { PR_PARTS, PR_LIVES, PR_INV, PR_DMG, PR_DOWN, PR_RESP, PR_CRAFT, PR_FF, PR_RADAR, PR_GLIM, PR_MODE, PR_TIME, PR_TEAMS, PR_LATE, PR_MAXP, PR_AFK, PR_PING, PR_N };
typedef struct { const char *key, *label, *desc; int def, nv; int v[12]; } pr_def_t;
static const pr_def_t PR[PR_N] = {
    {"parts", "PARTS EARNED", "Every parts award of the match is multiplied by this. Clan supplies are not affected: private matches never count for the clan.", 100, 6, {50, 100, 150, 200, 300, 500}},
    {"lives", "TEAM LIVES", "Supply Raid reinforcements per team at the start of the match. 20 is the 2013 count. Interrogation ignores it.", 20, 11, {5, 10, 15, 20, 25, 30, 40, 50, 75, 100, 0}},
    {"invuln", "INVINCIBILITY", "Nobody takes damage: bullets, melee, explosives, fire and executions do nothing. For practice and messing around.", 0, 2, {0, 1}},
    {"dmg", "DAMAGE MODEL", "FACTIONS: the 2013 damage table of every gun. TLOU2: the game's own gun damage, and any headshot is a would-kill hit: a down, or a kill with DOWNED SYSTEM off.", 0, 2, {0, 1}},
    {"downed", "DOWNED SYSTEM", "ON: the 2013 downed state - a would-kill hit downs, the downed player bleeds out, crawls, gets revived or executed. OFF: a would-kill hit kills at once.", 1, 2, {1, 0}},
    {"resp", "RESPAWN TIMER", "WAVES: the 2013 respawn waves (5 to 15 seconds). Any other value is a fixed wait for everybody.", 0, 5, {0, 3, 5, 10, 15}},
    {"craft", "FREE CRAFTING", "Crafting ingredients are topped up all the time: craft as much as you like.", 0, 2, {0, 1}},
    {"ff", "FRIENDLY FIRE", "Gun and melee hits on teammates do damage.", 0, 2, {0, 1}},
    {"radar", "RADAR", "OFF hides the radar for every player in the match.", 1, 2, {1, 0}},
    {"glim", "GUN LIMITS", "The per-team limits on special guns (Military Sniper, crossbow and the others). OFF: no limits.", 1, 2, {1, 0}},
    {"mode", "MODE", "The game mode of the match.", 0, 2, {0, 1}},
    {"time", "MATCH TIME", "The Supply Raid match clock. DEFAULT keeps the mode's own time. Interrogation ignores it.", 0, 6, {0, 5, 10, 15, 20, 30}},
    {"teams", "TEAMS", "BALANCED: the server splits the lobby by skill. HOST ASSIGNS: the host sets every team on the PLAYERS tab. PLAYERS PICK: everyone picks their own.", 0, 3, {0, 1, 2}},
    {"late", "LATE JOIN", "Lobby members who join after the start go straight into the running match.", 1, 2, {1, 0}},
    {"maxp", "MAX PLAYERS", "How many players the lobby takes.", 8, 7, {2, 3, 4, 5, 6, 7, 8}},
    {"afk", "AFK REMOVAL", "Players who do nothing for a long time are removed from the match.", 0, 2, {0, 1}},
    {"ping", "PING LIMIT", "Players over the ping limit are removed from the match.", 0, 2, {0, 1}},
};
static const int PR_TAB0[] = {PR_PARTS, PR_LIVES, PR_INV, PR_DMG, PR_DOWN, PR_RESP, PR_CRAFT, PR_FF, PR_RADAR, PR_GLIM};
static const int PR_TAB1[] = {PR_MODE, PR_TIME, PR_TEAMS, PR_LATE, PR_MAXP, PR_AFK, PR_PING};
#define PR_NT0 ((int)(sizeof PR_TAB0 / sizeof PR_TAB0[0]))
#define PR_NT1 ((int)(sizeof PR_TAB1 / sizeof PR_TAB1[0]))
static void pr_text(int i, int v, char *b, size_t n) {
    switch (i) {
    case PR_PARTS: snprintf(b, n, "%d%%", v); break;
    case PR_LIVES: if (v) snprintf(b, n, "%d", v); else snprintf(b, n, "UNLIMITED"); break;
    case PR_DMG: snprintf(b, n, "%s", v ? "TLOU2" : "FACTIONS"); break;
    case PR_RESP: if (v) snprintf(b, n, "%d SEC", v); else snprintf(b, n, "WAVES"); break;
    case PR_MODE: snprintf(b, n, "%s", v >= 0 && v < MODE_N ? MODE_TAB[v].label : "?"); break;
    case PR_TIME: if (v) snprintf(b, n, "%d MIN", v); else snprintf(b, n, "DEFAULT"); break;
    case PR_TEAMS: snprintf(b, n, "%s", v == 1 ? "HOST ASSIGNS" : v == 2 ? "PLAYERS PICK" : "BALANCED"); break;
    case PR_MAXP: snprintf(b, n, "%d", v); break;
    default: snprintf(b, n, "%s", v ? "ON" : "OFF"); break;
    }
    for (char *p = b; *p; p++) if (*p >= 'a' && *p <= 'z') *p = (char)(*p - 32);
}
static int pr_step(int i, int v, int d) {       // the next / previous allowed value (wraps)
    int k = 0;
    for (; k < PR[i].nv; k++) if (PR[i].v[k] == v) break;
    if (k >= PR[i].nv) k = 0;
    return PR[i].v[(k + PR[i].nv + d) % PR[i].nv];
}

// ------------------------------------------------------------------ state from the server
typedef struct {
    int ok, in, own, me, st, go, n, map;
    unsigned long long pool, av;
    int r[PR_N];
    char err[16], code[8];
    char nm[PL_NMEM][24];
    int tm[PL_NMEM], host[PL_NMEM];
} pl_state_t;
static struct {
    pl_state_t s;
    int have, fails, go_seen, launches, reopen, reopen_wait, menu_seen, reopen_push;
    uint64_t reopen_t0;
    uint64_t poll_at, msg_until, reply_ms;
    char msg[160];
    int q_n, q_sub[8]; char q_arg[8][48];          // queued writes, in order (a write to the same key replaces the waiting one)
    unsigned seq, set_seq, inflight_seq;           // poll replies sent before the last write are not believed (no flicker of an optimistic value)
    int inflight_sub, want_create;
} PL;
static struct { int on; int r[PR_N]; char mid[16]; uint64_t poll_at; int asked; } g_pvr;   // the match's private rules (in a match)
static volatile LONG g_pl_busy, g_pl_have;
static uint8_t g_pl_req[64 + 3 + 48];
static int g_pl_req_len;
static char g_pl_rep[1400];

static DWORD WINAPI pl_worker(LPVOID arg) {
    (void)arg;
    HMODULE ws = LoadLibraryA("ws2_32.dll");
    t2r_sin a;
    t2r_net net;
    LONG res = 2;
    if (ws && hm_server(&a) && t2r_net_load(&net, ws)) {
        uint8_t frame[3 + sizeof g_pl_req];
        int n = g_pl_req_len + 1;
        frame[0] = (uint8_t)n; frame[1] = (uint8_t)(n >> 8); frame[2] = PL_OP;
        memcpy(frame + 3, g_pl_req, (size_t)g_pl_req_len);
        static char rep[sizeof g_pl_rep + 8];
        int got = t2r_rpc(&net, &a, frame, n + 2, rep, (int)sizeof rep - 1, 2000, 2500, 2500, NULL);
        int ln = got >= 3 ? (rep[0] & 0xff) + ((rep[1] & 0xff) << 8) : 0;
        if (ln >= 1 && got >= ln + 2 && (uint8_t)rep[2] == 0xF9 && ln - 1 < (int)sizeof g_pl_rep) {
            memcpy(g_pl_rep, rep + 3, (size_t)ln - 1);
            g_pl_rep[ln - 1] = 0;
            res = 1;
            srv_mark_alive();
        }
    }
    InterlockedExchange(&g_pl_have, res);
    InterlockedExchange(&g_pl_busy, 0);
    return 0;
}
static int pl_ask(int sub, const char *arg) {           // 1 = a request went out
    static char tok[65];
    if (!tok[0] && !clan_token(tok)) { tok[0] = 0; return 0; }
    if (g_pl_have || InterlockedCompareExchange(&g_pl_busy, 1, 0)) return 0;
    memcpy(g_pl_req, tok, 64);
    g_pl_req[64] = PL_VER; g_pl_req[65] = (uint8_t)sub;
    size_t al = arg ? strlen(arg) : 0;
    if (al > 47) al = 47;
    if (al) memcpy(g_pl_req + 66, arg, al);
    g_pl_req_len = 66 + (int)al;
    PL.inflight_sub = sub; PL.inflight_seq = ++PL.seq;
    if (sub != PL_S_STATE && sub != PL_S_RULES) PL.set_seq = PL.inflight_seq;
    HANDLE h = CreateThread(NULL, 0, pl_worker, NULL, 0, NULL);
    if (!h) { InterlockedExchange(&g_pl_busy, 0); return 0; }
    CloseHandle(h);
    return 1;
}
static void pl_queue(int sub, const char *arg) {
    if (!arg) arg = "";
    const char *eq = strchr(arg, '=');
    size_t kl = eq ? (size_t)(eq - arg) + 1 : strlen(arg) + 1;     // "key=" (or the whole argument)
    int at = PL.q_n;
    for (int i = 0; i < PL.q_n; i++) if (PL.q_sub[i] == sub && (sub == PL_S_SET || sub == PL_S_TEAM) && !strncmp(PL.q_arg[i], arg, kl)) { at = i; break; }
    if (at >= 8) { memmove(PL.q_sub, PL.q_sub + 1, 7 * sizeof PL.q_sub[0]); memmove(PL.q_arg, PL.q_arg + 1, 7 * sizeof PL.q_arg[0]); at = 7; PL.q_n = 7; }
    PL.q_sub[at] = sub;
    snprintf(PL.q_arg[at], sizeof PL.q_arg[at], "%s", arg);
    if (at == PL.q_n) PL.q_n++;
    PL.poll_at = 0;
}
static const char *pl_err_text(const char *e) {
    if (!strcmp(e, "nocode")) return "NO LOBBY WITH THAT CODE";
    if (!strcmp(e, "started")) return "THAT MATCH HAS STARTED AND LATE JOIN IS OFF";
    if (!strcmp(e, "full")) return "THAT LOBBY IS FULL";
    if (!strcmp(e, "busy")) return "NOT POSSIBLE WHILE YOUR LOBBY IS STARTING OR PLAYING";
    if (!strcmp(e, "notowner")) return "ONLY THE HOST CAN DO THAT";
    if (!strcmp(e, "badvalue") || !strcmp(e, "badrule")) return "THAT VALUE IS NOT ALLOWED";
    if (!strcmp(e, "emptypool")) return "THE MAP POOL NEEDS AT LEAST ONE MAP";
    if (!strcmp(e, "teamsauto")) return "TEAMS ARE BALANCED BY THE SERVER - CHANGE TEAMS ON THE MATCH TAB";
    if (!strcmp(e, "notallowed")) return "ONLY THE HOST CAN CHANGE THAT PLAYER'S TEAM";
    if (!strcmp(e, "inmatch")) return "A MEMBER IS STILL IN ANOTHER MATCH";
    if (!strcmp(e, "off")) return "PRIVATE MATCHES ARE OFF ON THIS SERVER";
    if (!strcmp(e, "notin")) return "YOU ARE NOT IN A LOBBY";
    return "SOMETHING WENT WRONG - TRY AGAIN";
}
static void pl_msg(const char *t, int good) {
    snprintf(PL.msg, sizeof PL.msg, "<font color=\"#%s\">%s</font>", good ? "7CB494" : "F2625A", t);
    PL.msg_until = GetTickCount64() + 5000;
}
static int pl_parse_state(const char *t, pl_state_t *o) {
    memset(o, 0, sizeof *o);
    for (int i = 0; i < PR_N; i++) o->r[i] = PR[i].def;
    o->map = PL_MAP_VOTE;
    for (int k = 0; k < PL_NMEM; k++) o->tm[k] = PL_AUTO;
    char k[16], v[48];
    int n, got = 0;
    while (sscanf(t, " %15[^= ]=%47s%n", k, v, &n) == 2) {
        t += n; got++;
        if (!strcmp(k, "ok")) o->ok = atoi(v);
        else if (!strcmp(k, "err")) snprintf(o->err, sizeof o->err, "%s", v);
        else if (!strcmp(k, "in")) o->in = atoi(v);
        else if (!strcmp(k, "code")) snprintf(o->code, sizeof o->code, "%s", v);
        else if (!strcmp(k, "own")) o->own = atoi(v);
        else if (!strcmp(k, "me")) o->me = atoi(v);
        else if (!strcmp(k, "st")) o->st = atoi(v);
        else if (!strcmp(k, "go")) o->go = atoi(v);
        else if (!strcmp(k, "n")) o->n = atoi(v) < 0 ? 0 : atoi(v) > PL_NMEM ? PL_NMEM : atoi(v);
        else if (!strcmp(k, "map")) o->map = atoi(v);
        else if (!strcmp(k, "pool")) o->pool = strtoull(v, NULL, 16);
        else if (!strcmp(k, "av")) o->av = strtoull(v, NULL, 16);
        else if ((k[0] == 'p' || k[0] == 't' || k[0] == 'h') && k[1] >= '0' && k[1] <= '9' && !k[2]) {
            int m = k[1] - '0';
            if (m >= PL_NMEM) continue;
            if (k[0] == 'p') { snprintf(o->nm[m], sizeof o->nm[m], "%s", v); for (char *c = o->nm[m]; *c; c++) if (*c == '_') *c = ' '; }
            else if (k[0] == 't') o->tm[m] = atoi(v);
            else o->host[m] = atoi(v);
        } else for (int i = 0; i < PR_N; i++) if (!strcmp(k, PR[i].key)) { o->r[i] = atoi(v); break; }
    }
    return got;
}
static int pl_off(void) {
#ifdef T2R_RELEASE
    // public release (private matches are locked for it): the PRIVATE MATCH row is greyed out in the release ext; the live daemon
    // also runs with T2R_PRIVATE=0. Test builds (no -DT2R_RELEASE) keep the row, t2r-no-private.txt greys it there.
    static int said; if (!said) { said = 1; xlog("private: off (release build)"); }
    return 1;
#endif
    static int off = -1;
    if (off < 0) { FILE *f = exe_side_open("t2r-no-private.txt", "r"); off = f != NULL; if (f) fclose(f); if (off) xlog("private: off (t2r-no-private.txt)"); }
    return off;
}
static uint64_t pl_lobby_id(void) { static uint64_t id; if (!id) id = page_id("private13"); return id; }
static uint64_t pl_set_id(void) { static uint64_t id; if (!id) id = page_id("private13s"); return id; }

// ------------------------------------------------------------------ in-match rules (pv_*: called from the t2r-ext hooks)
static int pv_live(void) { return g_pvr.on && match_substate() == 6; }
// (private matches work with one player): winmm's state-6 tick leaves the session with "Could not connect to the match - returning to menu" when a
// running match has no peer 30 s after its start (lobby ctx +0x1b0 == 2, GetTickCount64() - ctx+0x2cb8 > 30000; re/decomp_match.c; +0x2cb8 is written at the match
// start and read only by that check). A private match keeps that start time fresh, so a host alone in it plays on.
static void pv_solo_keep(uint64_t now) {
    if (!pv_live()) return;
    uint8_t *lo = lobby_obj();
    if (!lo || IsBadWritePtr(lo + 0x2cb8, 8) || lo[0x2ca4]) return;
    *(volatile uint64_t *)(lo + 0x2cb8) = now;
    // The match clock, the respawn-wave timers and the time-out / elimination end live in TickMatchAuthority FUN_180034050 (overtime.c), which
    // winmm's frame FUN_18004c2f0 calls only while a peer is connected (FUN_18005da70): alone, the clock froze at the start and the match never
    // ended (A: 00:00 on the HUD, remaining 300 of 300 s). The host alone runs it here, once per frame, with winmm's own frame time;
    // a peer joining hands it back to winmm in the same frame (this check runs before winmm's call, on the same thread: t2r_tick is called from
    // FUN_180063370 at the top of FUN_18004c2f0).
    typedef char (*b_fn)(void);
    if (*(volatile uint8_t *)VMA(0x180177F40) == 1 && *(volatile uint8_t *)VMA(0x180167854) && !((b_fn)VMA(0x18005DA70))()) {
        float dt = ((float (*)(void))VMA(0x18000B4F0))();
        if (dt > 0.0f && dt < 0.5f) ((void (*)(float))VMA(0x180034050))(dt);
        static char said2[sizeof g_pvr.mid];
        if (strcmp(said2, g_pvr.mid)) { snprintf(said2, sizeof said2, "%s", g_pvr.mid); xlog("private: alone in private match %s - the match clock and its end run from here (dt %.4f)", g_pvr.mid, (double)dt); }
    }
    static char said[sizeof g_pvr.mid]; if (strcmp(said, g_pvr.mid)) { snprintf(said, sizeof said, "%s", g_pvr.mid); xlog("private: no-peer 30 s leave switched off for private match %s (ctx+0x2cb8 kept fresh)", g_pvr.mid); }
}
static int pv_rule(int i) { return pv_live() ? g_pvr.r[i] : PR[i].def; }
static int pv_parts(int amount, uint32_t slot, int own) {      // award_hook: the engine's awards of OUR slot (our own bonus rows follow from the scaled amount)
    if (own || amount <= 0 || slot != *(uint32_t *)VMA(0x180138090) || !pv_live()) return amount;
    int pct = g_pvr.r[PR_PARTS];
    if (pct == 100 || pct <= 0 || pct > 1000) return amount;
    int a = (amount * pct + 50) / 100;
    return a > 0 ? a : 1;
}
static int pv_tlou2_dmg(void) { return pv_rule(PR_DMG) == 1; }
static void pv_tlou2_damage(uint8_t *di) {      // TLOU2 damage model: the engine's own gun damage; a headshot = the would-kill hit (a down; a kill with DOWNED SYSTEM off)
    g_fgd_head = di[0x9b4] == 9;
    if (g_fgd_head && base_weapon_is_gun(*(uint64_t *)(di + 0x20))) {
        static int n;
        if (n++ < 40) xlog("private: TLOU2 damage - headshot (engine %.1f) -> 199", (double)*(float *)(di + 0x40));
        *(float *)(di + 0x40) = 199.0f;
    }
}
// INVINCIBILITY: recv_hit_hook drops every hit on us (the victim's side, like the intro guard: bullets, melee, explosions, fire, executions)
static int pv_invuln(void) { return pv_rule(PR_INV) == 1; }
// DOWNED SYSTEM off: t2r-ext's DOWNED_ON is this test - no would-kill cap / prediction hold on the attacker, no down rules on the victim: a would-kill hit kills
static int pv_downed_off(void) { return pv_rule(PR_DOWN) == 0; }
static int pv_resp_secs(void) { int s = pv_rule(PR_RESP); return s > 0 && s <= 60 ? s : 0; }
static int pv_radar_off(void) { return pv_rule(PR_RADAR) == 0; }
static int pv_ff_on(void) { return pv_rule(PR_FF) == 1; }
// TEAM LIVES / MATCH TIME: once per match when the Supply Raid clock runs (lobby +0x2b84 / +0x2b88 team lives, +0x2b8c duration, +0x2b90 remaining,
// +0x2b94 running, +0x2ca4 over - test_clock2_tick's fields); every peer does it, the host's event 6 carries its values to the clients. Lives 0 =
// unlimited: both teams are kept at 99. Not in Interrogation.
static void pv_clock_tick(void) {
    static int lives_done, time_done;
    uint8_t *lo = match_substate() == 6 ? lobby_obj() : NULL;
    if (!lo || !g_pvr.on) { lives_done = time_done = 0; return; }
    if (r13_int_mode() || IsBadWritePtr(lo + 0x2b84, 0x14) || !lo[0x2b94] || lo[0x2ca4]) return;
    float *tm = (float *)(lo + 0x2b8c);
    int32_t *lv = (int32_t *)(lo + 0x2b84);
    int want = g_pvr.r[PR_LIVES];
    if (want == 0) { if (lv[0] < 50) lv[0] = 99; if (lv[1] < 50) lv[1] = 99; lives_done = 1; }
    else if (!lives_done && want != PR[PR_LIVES].def && tm[0] > 0.0f && tm[0] - tm[1] < 10.0f && want >= 1 && want <= 200) {
        xlog("private: team lives %d / %d -> %d", lv[0], lv[1], want);
        lv[0] = lv[1] = want; lives_done = 1;
    }
    int mins = g_pvr.r[PR_TIME];
    if (!time_done && mins > 0 && mins <= 60 && tm[0] >= 30.0f && tm[0] <= 3600.0f) {
        float want_s = (float)mins * 60.0f, el = tm[0] - tm[1];
        time_done = 1;
        if (el < 10.0f) { tm[1] = want_s - el; tm[0] = want_s; xlog("private: match clock -> %d min", mins); }
        else xlog("private: match clock left alone (joined %.0f s in)", (double)el);
    }
}
static void pv_craft_tick(void) {                 // FREE CRAFTING: the six ingredients kept at 3 (every 60 frames, alive, not in the spawn routine)
    if (!pv_live() || g_pvr.r[PR_CRAFT] != 1 || g_in_spawn || g_frame % 60) return;
    uint64_t me = SID_PLAYER;
    uint64_t dead = dc_call(0xe93f704f02a9ecd5ULL /* character-is-dead? */, 1, &me);
    if (dead == ~0ULL || (dead & 0xff)) return;
    for (int i = 0; i < 6; i++) {
        uint64_t have = inv_qty(KEEP_ING[i]);
        if (have < 3) dc_direct(0x7258db3b9e03e625ULL /* player-inventory-add-item-quantity */, KEEP_ING[i], 3 - have, 0);
    }
}
static void pv_parse(const char *t) {
    int r[PR_N], pm = 0;
    char mid[16] = "";
    for (int i = 0; i < PR_N; i++) r[i] = PR[i].def;
    char k[16], v[24];
    int n;
    while (sscanf(t, " %15[^= ]=%23s%n", k, v, &n) == 2) {
        t += n;
        if (!strcmp(k, "pm")) pm = atoi(v);
        else if (!strcmp(k, "mid")) snprintf(mid, sizeof mid, "%s", v);
        else for (int i = 0; i < PR_N; i++) if (!strcmp(k, PR[i].key)) { r[i] = atoi(v); break; }
    }
    if (pm != g_pvr.on || strcmp(mid, g_pvr.mid)) {
        char b[200]; int o = 0;
        for (int i = 0; i < PR_N && o < (int)sizeof b - 16; i++) if (r[i] != PR[i].def) o += snprintf(b + o, sizeof b - o, " %s=%d", PR[i].key, r[i]);
        b[o] = 0;
        xlog("private: match %s %s%s", mid[0] ? mid : "-", pm ? "is a private match, rules:" : "is not a private match", pm ? (o ? b : " all default") : "");
    }
    g_pv_last_priv = pm;
    g_pvr.on = pm; memcpy(g_pvr.r, r, sizeof r); snprintf(g_pvr.mid, sizeof g_pvr.mid, "%s", mid);
}
static void pv_tick(uint64_t now) {
    if (match_substate() != 6 && g_mf_code_now < 100) { g_pvr.on = 0; g_pvr.mid[0] = 0; g_pvr.asked = 0; g_pvr.poll_at = 0; }
    else if (now >= g_pvr.poll_at && pl_ask(PL_S_RULES, "")) g_pvr.poll_at = now + (g_pvr.asked++ < 3 ? 3000 : 15000);
    g_ff_off = g_ff_file || pv_ff_on();
    pv_craft_tick();
}

// ------------------------------------------------------------------ shared page helpers
static void pl_text(const char *p, const char *t) { ui_text(p, t); }
static void pl_vis(const char *p, int on) { ui_visible(p, on); }
static void pl_focus(const char *path) { uint64_t a[1] = {ui_w(path)}; if (a[0]) dc_call(fnv64("menu2-set-focus-to-component"), 1, a); }
static int pl_focused(const char *path) { typedef char (*fn_focus)(uint64_t); uint64_t w = ui_w(path); return w && ((fn_focus)VMA(0x180068BF0))(w) != 0; }
static void pl_sfx(uint64_t now) { static uint64_t last; if (now - last >= 60) { last = now; ui_sfx("sfx-cycle"); } }
static const char *pl_map_label(int map, char *b, size_t n) {
    if (map == PL_MAP_VOTE) snprintf(b, n, "VOTE FROM POOL");
    else if (map == PL_MAP_RANDOM) snprintf(b, n, "RANDOM FROM POOL");
    else snprintf(b, n, "%s", mf_map_name(map));
    return b;
}
static int pl_maps(int *idx, int max) {            // the maps the grid lists: every map all members can play (av), else the whole built-in list
    int n = 0;
    unsigned long long av = PL.s.av ? PL.s.av : ((1ULL << MF_NMAPS) - 1);
    for (int i = 0; i < 64 && n < max; i++) if (av >> i & 1) idx[n++] = i;
    return n;
}
static int pl_pool_n(void) { int idx[32], n = pl_maps(idx, 32), c = 0; for (int i = 0; i < n; i++) if (PL.s.pool >> idx[i] & 1) c++; return c; }

// ------------------------------------------------------------------ the lobby page (to1/private13)
static const char *const PL_ROWS[5] = {"anim-group.menuList.StartMatch", "anim-group.menuList.ChooseMap", "anim-group.menuList.EditSettings",
                                      "anim-group.menuList.JoinCode", "anim-group.menuList.LeaveLobby"};
static struct {
    int up, h_sel, h_back, h_u, h_d, h_l, h_r, hk[256], code_open, cur, dirty, focus_set;
    char code[PL_CODE_LEN + 1];
    uint64_t enter_ms, bs_ms, code_ms, last_root;
    char err[80];
} PLL;
static struct { int valid, cur; char code[PL_CODE_LEN + 1]; } PLK;   // the code box carried over the engine's pop on Backspace / B (the page is pushed again)
static int g_pl_smode;                            // the settings page opens as 0 EDIT SETTINGS / 1 CHOOSE MAP
static void pl_open(const char *why) {             // from the mode box: our lobby, or a new one
    if (pl_off()) { ui_deny("PRIVATE MATCHES ARE OFF"); return; }
    PL.want_create = 1; PL.poll_at = 0;
    PL.go_seen = -1;
    xlog("private: lobby page opened (%s)", why);
    push_page("to1/private13");
}
static int pl_code_ok(char c) { return (c >= 'A' && c <= 'Z' && c != 'I' && c != 'O') || (c >= '2' && c <= '9'); }
static const char PL_ALPHA[] = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789";
static void pl_code_open(void) {
    PLL.code_open = 1; PLL.cur = 0; memset(PLL.code, 0, sizeof PLL.code); PLL.err[0] = 0; PLL.code_ms = GetTickCount64();
    for (int vk = 8; vk < 0xC0; vk++) PLL.hk[vk] = (GetAsyncKeyState(vk) & 0x8000) != 0;
    PLL.dirty = 1;
    xlog("private: JOIN WITH CODE opened");
}
static void pl_code_close(const char *why) { PLL.code_open = 0; PLL.dirty = 1; xlog("private: JOIN WITH CODE closed (%s)", why); }
static void pl_code_send(void) {
    int n = (int)strlen(PLL.code);
    if (n < PL_CODE_LEN) { ui_sfx("sfx-menu-error"); snprintf(PLL.err, sizeof PLL.err, "THE CODE HAS 5 LETTERS"); PLL.dirty = 1; return; }
    if (PL.s.in && !strcmp(PL.s.code, PLL.code)) { pl_code_close("own code"); return; }
    pl_queue(PL_S_JOIN, PLL.code);
    ui_sfx("sfx-select");
    snprintf(PLL.err, sizeof PLL.err, "JOINING...");
    PLL.dirty = 1;
}
static void pl_code_fill(void) {
    char p[96], c[4];
    for (int k = 0; k < PL_CODE_LEN; k++) {
        snprintf(p, sizeof p, "anim-group.cdBox.cdPanel.cdCell%d.cdCh%d", k, k);
        c[0] = PLL.code[k] ? PLL.code[k] : 0; c[1] = 0;
        if (!c[0] && k == PLL.cur && g_pad_mode) { c[0] = 'A'; }               // (the pad's letter picker starts at A, drawn dim until it is taken)
        pl_text(p, c[0] ? c : "");
        snprintf(p, sizeof p, "anim-group.cdBox.cdPanel.cdCell%d.cdCellCur%d", k, k);
        pl_vis(p, k == PLL.cur);
    }
    pl_text("anim-group.cdBox.cdPanel.cdErr", PLL.err);
    pl_text("anim-group.cdBox.cdPanel.cdKeys", g_pad_mode ? "UP / DOWN  LETTER     LEFT / RIGHT  MOVE     A  JOIN     B  CANCEL" : "TYPE THE CODE     ENTER  JOIN     ESC  CANCEL");
}
static void pl_code_tick(uint64_t now, int up, int down, int left, int right, int sel, int back, int esc) {
    int foc = game_focused();
    if (foc) {
        for (int vk = 'A'; vk <= 'Z'; vk++) if (ne_key_edge(vk, &PLL.hk[vk]) && pl_code_ok((char)vk) && PLL.cur < PL_CODE_LEN) { PLL.code[PLL.cur++] = (char)vk; PLL.dirty = 1; }
        for (int vk = '0'; vk <= '9'; vk++) if (ne_key_edge(vk, &PLL.hk[vk])) {
            char c = (char)vk == '0' ? 'O' : (char)vk == '1' ? 'I' : (char)vk;     // (0 / 1 typed for O / I: not in the code alphabet)
            if (pl_code_ok(c) && PLL.cur < PL_CODE_LEN) { PLL.code[PLL.cur++] = c; PLL.dirty = 1; }
        }
        if (GetAsyncKeyState(VK_BACK) & 0x8000) PLL.bs_ms = now;
        if (ne_key_edge(VK_BACK, &PLL.hk[VK_BACK]) && PLL.cur > 0) { PLL.code[--PLL.cur] = 0; PLL.err[0] = 0; PLL.dirty = 1; }
        if (ne_key_edge(VK_RETURN, &PLL.hk[VK_RETURN])) { pl_code_send(); return; }
        if (esc) { pl_code_close("Esc"); return; }
        if ((GetAsyncKeyState(VK_CONTROL) & 0x8000) && ne_key_edge('V', &PLL.hk['V'])) {
            if (OpenClipboard(NULL)) {
                HANDLE h = GetClipboardData(CF_TEXT);
                const char *t = h ? (const char *)GlobalLock(h) : NULL;
                if (t) { PLL.cur = 0; memset(PLL.code, 0, sizeof PLL.code); for (; *t && PLL.cur < PL_CODE_LEN; t++) { char c = *t >= 'a' && *t <= 'z' ? (char)(*t - 32) : *t; if (c == '0') c = 'O'; if (c == '1') c = 'I'; if (pl_code_ok(c)) PLL.code[PLL.cur++] = c; } GlobalUnlock(h); PLL.dirty = 1; }
                CloseClipboard();
            }
        }
    }
    if (g_pad_mode) {                                  // the pad: up / down pick the letter of the current cell, left / right move, A joins when full, else takes the letter
        int k = PLL.cur < PL_CODE_LEN ? PLL.cur : PL_CODE_LEN - 1;
        char c = PLL.code[k] ? PLL.code[k] : 'A';
        const char *at = strchr(PL_ALPHA, c);
        int ai = at ? (int)(at - PL_ALPHA) : 0, na = (int)sizeof PL_ALPHA - 1;
        if (up || down) { ai = (ai + (up ? na - 1 : 1)) % na; PLL.code[k] = PL_ALPHA[ai]; if (PLL.cur < k) PLL.cur = k; pl_sfx(now); PLL.dirty = 1; }
        if (left && PLL.cur > 0) { PLL.cur--; pl_sfx(now); PLL.dirty = 1; }
        if (right && PLL.cur < PL_CODE_LEN - 1 && PLL.code[PLL.cur]) { PLL.cur++; pl_sfx(now); PLL.dirty = 1; }
        if (sel) {
            if (!PLL.code[k]) PLL.code[k] = 'A';
            if ((int)strlen(PLL.code) >= PL_CODE_LEN) pl_code_send();
            else if (PLL.cur < PL_CODE_LEN - 1) { PLL.cur++; pl_sfx(now); PLL.dirty = 1; }
        }
    }
    if (back && !(PLL.bs_ms && now - PLL.bs_ms < 300)) pl_code_close("back");
}
static void pl_lobby_fill(void) {
    const pl_state_t *s = &PL.s;
    char b[96], p[96];
    pl_text("anim-group.gameTitle", "MULTIPLAYER");
    pl_text("anim-group.menuTitle", "PRIVATE MATCH");
    // the rows
    const char *start = !s->in ? "START MATCH" : s->st == 1 ? (s->own ? "CANCEL START" : "STARTING...") : s->st == 2 ? (s->r[PR_LATE] ? "JOIN MATCH" : "MATCH RUNNING") : "START MATCH";
    pl_text("anim-group.menuList.StartMatch.label0", start);
    pl_text("anim-group.menuList.ChooseMap.label0", s->own ? "CHOOSE MAP" : "VIEW MAP");
    pl_text("anim-group.menuList.EditSettings.label0", s->own ? "EDIT SETTINGS" : "VIEW SETTINGS");
    pl_text("anim-group.menuList.JoinCode.label0", "JOIN WITH CODE");
    pl_text("anim-group.menuList.LeaveLobby.label0", "LEAVE LOBBY");
    int start_ok = s->in && ((s->own && s->st != 2) || (s->st == 2 && s->r[PR_LATE]));
    w_alpha(ui_w(PL_ROWS[0]), start_ok ? 1.0f : 0.4f);
    w_alpha(ui_w(PL_ROWS[4]), s->in ? 1.0f : 0.4f);
    // code
    pl_text("anim-group.codeBox.cdLabel", "LOBBY CODE");
    pl_text("anim-group.codeBox.cdCode", s->in ? s->code : "-----");
    // members
    snprintf(b, sizeof b, "LOBBY %d / %d", s->in ? s->n : 0, s->r[PR_MAXP]);
    pl_text("anim-group.lobbyPanel.lobbyCount", b);
    for (int k = 0; k < PL_NMEM; k++) {
        int on = s->in && k < s->n;
        snprintf(p, sizeof p, "anim-group.lobbyPanel.plRow%d", k); pl_vis(p, on);
        if (!on) continue;
        int t = s->tm[k];
        snprintf(p, sizeof p, "anim-group.lobbyPanel.plRow%d.plNm%d", k, k);
        snprintf(b, sizeof b, k == s->me ? "<font color=\"#E8DFC8\">%s</font>" : "%s", s->nm[k][0] ? s->nm[k] : "PLAYER"); pl_text(p, b);
        snprintf(p, sizeof p, "anim-group.lobbyPanel.plRow%d.plTabB%d", k, k); pl_vis(p, t == 0);
        snprintf(p, sizeof p, "anim-group.lobbyPanel.plRow%d.plTabR%d", k, k); pl_vis(p, t == 1);
        snprintf(p, sizeof p, "anim-group.lobbyPanel.plRow%d.plHostBg%d", k, k); pl_vis(p, s->host[k]);
        snprintf(p, sizeof p, "anim-group.lobbyPanel.plRow%d.plHost%d", k, k); pl_vis(p, s->host[k]);
        snprintf(p, sizeof p, "anim-group.lobbyPanel.plRow%d.plTm%d", k, k);
        pl_text(p, s->r[PR_TEAMS] == 0 ? "BALANCED" : t == 0 ? "BLUE" : t == 1 ? "RED" : "NO TEAM");
    }
    pl_text("anim-group.lobbyPanel.plWait", !PL.have ? "CONNECTING..." : !s->in ? "" : s->n < 2 ? "SHARE THE CODE - FRIENDS JOIN WITH JOIN WITH CODE" : "");
    // MATCH SETUP
    pl_text("anim-group.smBox.smHead", "MATCH SETUP");
    int line = 0;
    char v[48];
    #define PL_SM(key, val) do { if (line < 8) { snprintf(p, sizeof p, "anim-group.smBox.smK%d", line); pl_text(p, key); snprintf(p, sizeof p, "anim-group.smBox.smV%d", line); pl_text(p, val); line++; } } while (0)
    pr_text(PR_MODE, s->r[PR_MODE], v, sizeof v); PL_SM("MODE", v);
    if (s->map >= 0) PL_SM("MAP", mf_map_name(s->map));
    else { snprintf(v, sizeof v, "%s (%d MAPS)", s->map == PL_MAP_RANDOM ? "RANDOM" : "VOTE", pl_pool_n()); PL_SM("MAP", v); }
    int changed = 0;
    for (int i = 0; i < PR_N; i++) {
        if (i == PR_MODE || s->r[i] == PR[i].def) continue;
        changed++;
        pr_text(i, s->r[i], v, sizeof v); PL_SM(PR[i].label, v);
    }
    if (!changed) PL_SM("RULES", "DEFAULT");
    for (; line < 8; line++) { snprintf(p, sizeof p, "anim-group.smBox.smK%d", line); pl_text(p, ""); snprintf(p, sizeof p, "anim-group.smBox.smV%d", line); pl_text(p, ""); }
    #undef PL_SM
    // the status line
    const char *st;
    if (PL.msg_until && GetTickCount64() < PL.msg_until) st = PL.msg;
    else if (!PL.have) st = PL.fails >= 2 ? "NO ANSWER FROM THE SERVER" : "CONNECTING...";
    else if (!s->in) st = "NOT IN A LOBBY";
    else if (s->st == 1) st = "STARTING - SEARCHING FOR THE MATCH";
    else if (s->st == 2) st = s->r[PR_LATE] ? "THE MATCH IS RUNNING - JOIN MATCH TAKES YOU IN" : "THE MATCH IS RUNNING";
    else if (s->own) st = s->n < 2 ? "YOU ARE THE HOST - YOU CAN ALSO START ALONE" : "YOU ARE THE HOST";
    else st = "WAITING FOR THE HOST TO START";
    pl_text("anim-group.stTx", st);
    // the code box
    pl_vis("anim-group.cdBox", PLL.code_open);
    if (PLL.code_open) {
        pl_text("anim-group.cdBox.cdPanel.cdTitle", "JOIN WITH CODE");
        pl_text("anim-group.cdBox.cdPanel.cdSub", "TYPE THE LOBBY CODE YOUR FRIEND SEES");
        pl_code_fill();
    }
}
// Load gate (process limit): when the match is found (lobby phase 2, the search page on the stack, not yet in the match), the mod
// pages still on top are closed one per top before the map load. Private pages always. CLAN / PLAYER STATS / ACHIEVEMENTS / LEADERBOARDS
// only with the match flow off: with it on, its vote / booster stage closes them (feature_matchflow). CUSTOMIZE / CHALLENGES close
// themselves (customize.c): never listed here, two pops of one top would take a second page. Runs every frame: a page that is not
// ours on top (CUSTOMIZE) is waited out, then the pages under it are closed while the match is still loading. lo_choose waits while one of these is on top, so CHOOSE LOADOUT never covers one.
static int pl_gate_page(uint64_t top) {
    static const char *names[] = {"private13s", "private13", "clan13x", "clanach", "clan13", "leaderboard"};
    static uint64_t ids[6];
    if (!ids[0]) for (int i = 0; i < 6; i++) ids[i] = page_id(names[i]);
    int n = g_no_matchflow ? 6 : 2;
    for (int i = 0; i < n; i++) if (top && top == ids[i]) return 1;
    // The stock OPTIONS stack (options-menu-ingame and the sub-pages above it, e.g. the controls page) opened over FIND MATCH while
    // searching: no other code closes it, so the match flow / CHOOSE LOADOUT pushed over it and the map load ran with it on the stack.
    // A client crashed on the CHOOSE LOADOUT push with OPTIONS > controls > a sub-page stacked ("We have more than 10000 Processes!",
    // exe+144afc0 in ProcessMgr::OnProcessSpawned under Process::SpawnProcess). Its pages close one per top like the mod pages; never
    // the search page itself (pl_match_found needs it on the stack, and it is never the top here).
    {   static uint64_t P_OI, P_OM, P_FM2;
        if (!P_OI) { P_OI = page_id("options-menu-ingame"); P_OM = page_id("options-menu-multiplayer"); P_FM2 = page_id("find-match-menu"); }
        if (top && top != P_FM2 && (top == P_OI || top == P_OM || page_on_stack(P_OI) || page_on_stack(P_OM))) return 1;
    }
    return 0;
}
static int pl_match_found(void) {
    static uint64_t P_FM;
    if (!P_FM) P_FM = page_id("find-match-menu");
    uint8_t *o = lobby_obj();
    return o && !IsBadReadPtr(o + 0x1b4, 4) && *(int *)(o + 0x1b4) == 2 && match_substate() != 6 && page_on_stack(P_FM);
}
// Never two pops for one page instance. The menu queue can hold a pop while the stack is busy, so the guard is the queue + g_ui_gen
// (bumped when one of our stack ops RUNS), not a frame count (same guard as feature_matchflow's page close):
//   a pop still queued                          -> wait;
//   same top, g_ui_gen == at the request        -> the pop never ran (queue full, dropped) -> pop again, with a log line;
//   same top, g_ui_gen == request + 1           -> it ran, the stack has not shown the new top yet -> wait;
//   same top, g_ui_gen >= request + 2 / new top -> a new page instance -> pop it;
//   a pop that RAN but left the same top for 2 s (the stack ignored it) -> popped again, with a log line.
static void pl_load_gate(uint64_t top) {
    static uint64_t popped_top, ran_f;
    static unsigned req_gen;
    if (!pl_gate_page(top) || !pl_match_found()) { popped_top = 0; ran_f = 0; return; }
    int queued = 0;
    for (int i = 0; i < g_mq_n; i++) if (g_mq[i].pop) queued = 1;
    int ran_only = top == popped_top && g_ui_gen == req_gen + 1;
    if (!ran_only) ran_f = 0; else if (!ran_f) ran_f = g_frame;
    if (ran_only && g_frame - ran_f > 120) { xlog("private: %s still on top 2 s after its pop ran - popped again", page_name(top)); ran_only = 0; ran_f = 0; }
    if (queued || ran_only) return;
    if (top == popped_top && g_ui_gen == req_gen) xlog("private: the pop of %s never ran (menu queue) - popped again", page_name(top));
    popped_top = top; req_gen = g_ui_gen;
    pop_page();
    xlog("private: match found - closed the menu page %s before the map load (process budget, %d processes before the pop)", page_name(top), mf_procs());
}
static int pl_gate_holds(uint64_t top) { return pl_gate_page(top) && pl_match_found(); }   // lo_choose: wait, a page is still to close
static void pl_launch_search(const char *why) {
    g_mdpk_queued = PL.s.r[PR_MODE] >= 0 && PL.s.r[PR_MODE] < MODE_N ? PL.s.r[PR_MODE] : 0;      // (the loading screen / vote page label)
    g_mdpk_mm = -1;
    PL.launches++; PL.reopen = 1;
    // The lobby / settings pages are closed before the search page. Each Gui2 page keeps its engine processes through the map load
    // (lobby page about +160, settings page +416; the load adds about 2060 on top of the menu's ~7300). With mod pages
    // stacked, a client hit the engine's 10000-process limit ("We have more than 10000 Processes!") on the load. The lobby page
    // comes back after the match (PL.reopen).
    uint64_t top = top_page();
    int pops = 0;
    if (top == pl_set_id() || top == pl_lobby_id()) pops = page_on_stack(pl_set_id()) + page_on_stack(pl_lobby_id());
    if (PLL.code_open) pl_code_close("the match launches");
    for (int i = 0; i < pops; i++) pop_page();
    xlog("private: search page pushed (%s, lobby %s, mode %s, %d lobby page(s) closed first)", why, PL.s.code, MODE_TAB[g_mdpk_queued].key, pops);
    mk_search();
}
static void pl_lobby_act(int row) {
    const pl_state_t *s = &PL.s;
    switch (row) {
    case 0:
        if (!s->in) { ui_deny("NOT IN A LOBBY"); return; }
        if (s->st == 2) { if (s->r[PR_LATE]) { ui_sfx("sfx-select"); pl_launch_search("join the running match"); } else ui_deny("THE MATCH IS RUNNING AND LATE JOIN IS OFF"); return; }
        if (!s->own) { ui_deny("ONLY THE HOST CAN START THE MATCH"); return; }
        ui_sfx("sfx-select");
        pl_queue(s->st == 1 ? PL_S_CANCEL : PL_S_START, "");
        return;
    case 1: case 2:
        if (!s->in) { ui_deny("NOT IN A LOBBY"); return; }
        ui_sfx("sfx-select");
        g_pl_smode = row == 1;
        push_page("to1/private13s");
        return;
    case 3: ui_sfx("sfx-open"); pl_code_open(); return;
    case 4:
        if (!s->in) { pop_page(); return; }
        ui_sfx("sfx-select");
        pl_queue(PL_S_LEAVE, "");
        PL.s.in = 0; PL.reopen = 0;
        xlog("private: LEAVE LOBBY");
        pop_page();
        return;
    }
}
static void pl_lobby_tick(uint64_t now) {
    uint64_t root = ui_w("anim-group");
    if (!root) return;
    if (!PLL.up || root != PLL.last_root) {            // a fresh page instance
        int keep = PLK.valid;
        memset(&PLL, 0, sizeof PLL);
        PLL.up = 1; PLL.enter_ms = now; PLL.last_root = root; PLL.dirty = 1;
        PLL.h_sel = PLL.h_back = PLL.h_u = PLL.h_d = PLL.h_l = PLL.h_r = 1;
        for (int vk = 8; vk < 0xC0; vk++) PLL.hk[vk] = (GetAsyncKeyState(vk) & 0x8000) != 0;
        if (keep) { PLL.code_open = 1; PLL.cur = PLK.cur; memcpy(PLL.code, PLK.code, sizeof PLL.code); PLK.valid = 0; PLL.bs_ms = now; }
    }
    if (!PLL.focus_set && now - PLL.enter_ms > 100) { PLL.focus_set = 1; pl_focus(PL_ROWS[PLL.code_open ? 3 : 0]); }
    int sel = menu_edge(0x6695c5b7921bb5ddULL /* menu-select */, &PLL.h_sel);
    int back = menu_edge(fnv64("menu-back"), &PLL.h_back);
    int up = menu_edge(fnv64("menu-up"), &PLL.h_u), down = menu_edge(fnv64("menu-down"), &PLL.h_d);
    int left = menu_edge(fnv64("menu-left"), &PLL.h_l), right = menu_edge(fnv64("menu-right"), &PLL.h_r);
    static int h_esc;
    int esc_now = game_focused() && (GetAsyncKeyState(VK_ESCAPE) & 0x8000) != 0, esc = esc_now && !h_esc;
    h_esc = esc_now;
    int click = g_click_edge;
    if (PLL.code_open) {
        if (!pl_focused(PL_ROWS[3])) pl_focus(PL_ROWS[3]);          // modal: the menu's own focus never walks off while the box is up
        if (sel && ui_select_is_mouse()) sel = 0;
        pl_code_tick(now, up, down, left, right, sel, back, esc);
        if (click && !ui_mouse_over("anim-group.cdBox.cdPanel", 1)) pl_code_close("click outside");
    } else if (now - PLL.enter_ms > 200) {
        int row = -1;
        for (int k = 0; k < 5 && row < 0; k++) {
            if (click && ui_mouse_over(PL_ROWS[k], 1)) row = k;
            else if (sel && pl_focused(PL_ROWS[k]) && !ui_select_is_mouse()) row = k;
        }
        if (row >= 0) pl_lobby_act(row);
    }
    { static int lpd = -1; if (lpd != g_pad_mode) { lpd = g_pad_mode; PLL.dirty = 1; } }
    if (PLL.dirty || !(g_frame % 20)) { PLL.dirty = 0; pl_lobby_fill(); }
}

// ------------------------------------------------------------------ the settings page (to1/private13s): tabs GAME RULES / MATCH / MAP POOL / PLAYERS, or CHOOSE MAP
#define PS_NROW 10
#define PS_GRID 20
static struct {
    int up, tab, foc, gfoc, dirty, h_sel, h_back, h_l, h_r, h_pv, h_nx, h_act, hv, ghv, thv, hk_x;
    uint64_t enter_ms, t_u, t_d, t_l, t_r, last_root;
    int h_u, h_d, h_lr, h_rr;
} PS;
static int ps_rows(int *ids) {                        // the rule ids of the current tab (rows 0..n-1)
    if (PS.tab == 0) { memcpy(ids, PR_TAB0, sizeof PR_TAB0); return PR_NT0; }
    if (PS.tab == 1) { memcpy(ids, PR_TAB1, sizeof PR_TAB1); return PR_NT1; }
    return 0;
}
static int ps_is_grid(void) { return g_pl_smode == 1 || PS.tab == 2; }
static int ps_count(void) {                           // focusable items of the view
    if (ps_is_grid()) { int idx[PS_GRID]; return pl_maps(idx, PS_GRID) + (g_pl_smode == 1 ? 2 : 0); }
    if (PS.tab == 3) return PL.s.in ? PL.s.n : 0;
    int ids[PS_NROW]; return ps_rows(ids);
}
static void ps_set_rule(int i, int v) {
    char a[40];
    snprintf(a, sizeof a, "%s=%d", PR[i].key, v);
    PL.s.r[i] = v;                                     // optimistic (the reply corrects it)
    pl_queue(PL_S_SET, a);
    xlog("private: SET %s", a);
}
static int ps_can_team(int k) {
    int t = PL.s.r[PR_TEAMS];
    return (t == 1 && PL.s.own) || (t == 2 && (PL.s.own || k == PL.s.me));
}
static void ps_change(int d, uint64_t now) {          // left / right / select on the focused item
    if (!PL.s.in) return;
    if (PS.tab == 3 && g_pl_smode == 0) {
        int k = PS.foc;
        if (k < 0 || k >= PL.s.n) return;
        if (PL.s.r[PR_TEAMS] == 0) { ui_deny("TEAMS ARE BALANCED BY THE SERVER - CHANGE TEAMS ON THE MATCH TAB"); return; }
        if (!ps_can_team(k)) { ui_deny(PL.s.r[PR_TEAMS] == 1 ? "ONLY THE HOST ASSIGNS TEAMS" : "YOU CAN ONLY PICK YOUR OWN TEAM"); return; }
        int t = PL.s.tm[k], order[3] = {PL_AUTO, 0, 1}, oi = t == 0 ? 1 : t == 1 ? 2 : 0;
        t = order[(oi + 3 + d) % 3];
        PL.s.tm[k] = t;
        char a[16]; snprintf(a, sizeof a, "%d=%d", k, t);
        pl_queue(PL_S_TEAM, a); pl_sfx(now);
        return;
    }
    if (!PL.s.own) { ui_deny("ONLY THE HOST CAN CHANGE THE SETTINGS"); return; }
    int ids[PS_NROW], n = ps_rows(ids);
    if (PS.foc < 0 || PS.foc >= n) return;
    int i = ids[PS.foc];
    ps_set_rule(i, pr_step(i, PL.s.r[i], d));
    pl_sfx(now);
    PS.dirty = 1;
}
static void ps_grid_pick(int f, uint64_t now) {       // select on a grid item
    (void)now;
    if (!PL.s.in) return;
    if (!PL.s.own) { ui_deny("ONLY THE HOST CAN CHANGE THE MAP"); return; }
    int idx[PS_GRID], n = pl_maps(idx, PS_GRID);
    char a[40];
    if (g_pl_smode == 1) {                               // CHOOSE MAP: a map / VOTE / RANDOM
        int m = f < n ? idx[f] : f == n ? PL_MAP_VOTE : PL_MAP_RANDOM;
        if (m >= 0) PL.s.pool |= 1ULL << m;              // (a chosen map out of the pool joins it: the server's set() does the same)
        PL.s.map = m;
        snprintf(a, sizeof a, "map=%d", m);
        pl_queue(PL_S_SET, a);
        ui_sfx("sfx-select");
        xlog("private: map -> %d", m);
    } else {                                             // MAP POOL: toggle
        if (f >= n) return;
        unsigned long long np = PL.s.pool ^ (1ULL << idx[f]);
        int left = 0; for (int i = 0; i < n; i++) if (np >> idx[i] & 1) left++;
        if (!left) { ui_deny("THE MAP POOL NEEDS AT LEAST ONE MAP"); return; }
        PL.s.pool = np;
        snprintf(a, sizeof a, "pool=%llx", np);
        pl_queue(PL_S_SET, a);
        ui_sfx("sfx-select");
    }
    PS.dirty = 1;
}
static void ps_action(uint64_t now) {                 // menu:action / X: RESET TO DEFAULT, ALL MAPS, KICK
    (void)now;
    if (!PL.s.in) return;
    if (PS.tab == 3 && g_pl_smode == 0) {
        int k = PS.foc;
        if (!PL.s.own) { ui_deny("ONLY THE HOST CAN REMOVE PLAYERS"); return; }
        if (k == PL.s.me || k < 0 || k >= PL.s.n) { ui_sfx("sfx-menu-error"); return; }
        char a[8]; snprintf(a, sizeof a, "%d", k);
        pl_queue(PL_S_KICK, a); ui_sfx("sfx-select");
        xlog("private: KICK member %d", k);
        return;
    }
    if (!PL.s.own) { ui_deny("ONLY THE HOST CAN CHANGE THE SETTINGS"); return; }
    if (ps_is_grid()) {
        int idx[PS_GRID], n = pl_maps(idx, PS_GRID);
        unsigned long long all = 0; for (int i = 0; i < n; i++) all |= 1ULL << idx[i];
        char a[40]; snprintf(a, sizeof a, "pool=%llx", all);
        PL.s.pool = all; pl_queue(PL_S_SET, a); ui_sfx("sfx-select");
    } else {
        int ids[PS_NROW], n = ps_rows(ids);
        if (PS.foc >= 0 && PS.foc < n) { ps_set_rule(ids[PS.foc], PR[ids[PS.foc]].def); ui_sfx("sfx-select"); }
    }
    PS.dirty = 1;
}
static void ps_fill(void) {
    const pl_state_t *s = &PL.s;
    char p[112], b[160], v[48];
    int grid = ps_is_grid();
    snprintf(b, sizeof b, "PRIVATE MATCH  -  CODE %s", s->in ? s->code : "-----");
    pl_text("anim-group.hd.hdKick", b);
    pl_text("anim-group.hd.hdTitle", g_pl_smode == 1 ? "CHOOSE MAP" : s->own ? "EDIT SETTINGS" : "SETTINGS");
    pl_text("anim-group.hd.hdNote", s->own ? "" : "ONLY THE HOST CAN CHANGE THESE");
    pl_vis("anim-group.tabs", g_pl_smode == 0);
    static const char *const TABS[4] = {"GAME RULES", "MATCH", "MAP POOL", "PLAYERS"};
    for (int k = 0; k < 4; k++) {
        snprintf(p, sizeof p, "anim-group.tabs.tab%d", k);
        snprintf(b, sizeof b, k == PS.tab ? "%s" : "<font color=\"#8D897B\">%s</font>", TABS[k]); pl_text(p, b);
        snprintf(p, sizeof p, "anim-group.tabs.tabU%d", k); pl_vis(p, k == PS.tab);
    }
    // rows
    int ids[PS_NROW], n = grid ? 0 : PS.tab == 3 ? (s->in ? s->n : 0) : ps_rows(ids);
    pl_vis("anim-group.rw", !grid);
    pl_vis("anim-group.inf", !grid);
    for (int k = 0; k < PS_NROW; k++) {
        int on = k < n;
        snprintf(p, sizeof p, "anim-group.rw.row%d", k); pl_vis(p, on);
        if (!on) continue;
        int foc = k == PS.foc, hov = k == PS.hv;
        snprintf(p, sizeof p, "anim-group.rw.row%d.rFill%d", k, k); gu_fade(p, foc || hov);
        snprintf(p, sizeof p, "anim-group.rw.row%d.rFrame%d", k, k); gu_fade(p, foc);
        int editable;
        if (PS.tab == 3) {
            snprintf(b, sizeof b, "%s%s", s->nm[k][0] ? s->nm[k] : "PLAYER", s->host[k] ? "  (HOST)" : k == s->me ? "  (YOU)" : "");
            int t = s->tm[k];
            snprintf(v, sizeof v, "%s", s->r[PR_TEAMS] == 0 ? "BALANCED" : t == 0 ? "BLUE" : t == 1 ? "RED" : "NO TEAM");
            editable = s->r[PR_TEAMS] != 0 && ps_can_team(k);
            snprintf(p, sizeof p, "anim-group.rw.row%d.rDot%d", k, k); pl_vis(p, 0);
        } else {
            int i = ids[k];
            snprintf(b, sizeof b, "%s", PR[i].label);
            pr_text(i, s->r[i], v, sizeof v);
            editable = s->own;
            snprintf(p, sizeof p, "anim-group.rw.row%d.rDot%d", k, k); pl_vis(p, s->r[i] != PR[i].def);
        }
        snprintf(p, sizeof p, "anim-group.rw.row%d.rLb%d", k, k); pl_text(p, b);
        snprintf(p, sizeof p, "anim-group.rw.row%d.rVal%d", k, k); pl_text(p, v);
        snprintf(p, sizeof p, "anim-group.rw.row%d.rL%d", k, k); pl_vis(p, editable);
        snprintf(p, sizeof p, "anim-group.rw.row%d.rR%d", k, k); pl_vis(p, editable);
    }
    // the info column
    if (!grid) {
        if (PS.tab == 3) {
            int k = PS.foc;
            pl_text("anim-group.inf.infName", k >= 0 && k < n ? s->nm[k] : "");
            pl_text("anim-group.inf.infDesc", s->r[PR_TEAMS] == 0 ? "Teams are balanced by the server when the match starts. Change TEAMS on the MATCH tab to pick them here." :
                    s->r[PR_TEAMS] == 1 ? "The host sets every player's team. NO TEAM players are put where there is room." : "Every player picks their own team. NO TEAM players are put where there is room.");
            pl_text("anim-group.inf.infDef", s->own && k != s->me ? (g_pad_mode ? "X  REMOVE FROM THE LOBBY" : "X  REMOVE FROM THE LOBBY") : "");
        } else if (PS.foc >= 0 && PS.foc < n) {
            int i = ids[PS.foc];
            pl_text("anim-group.inf.infName", PR[i].label);
            pl_text("anim-group.inf.infDesc", PR[i].desc);
            pr_text(i, PR[i].def, v, sizeof v);
            snprintf(b, sizeof b, "DEFAULT: %s", v); pl_text("anim-group.inf.infDef", b);
        }
    }
    // the map grid
    pl_vis("anim-group.mg", grid);
    if (grid) {
        int idx[PS_GRID], nm = pl_maps(idx, PS_GRID);
        for (int k = 0; k < PS_GRID; k++) {
            int on = k < nm;
            snprintf(p, sizeof p, "anim-group.mg.m%d", k); pl_vis(p, on);
            if (!on) continue;
            int m = idx[k], inpool = (s->pool >> m & 1) != 0;
            snprintf(p, sizeof p, "anim-group.mg.m%d.m%dImg", k, k);
            snprintf(b, sizeof b, "streaming/menus/to1/map-pvp-%s.png", mf_map_img(m)); ui_image(p, b);
            snprintf(p, sizeof p, "anim-group.mg.m%d.m%dName", k, k); pl_text(p, mf_map_name(m));
            snprintf(p, sizeof p, "anim-group.mg.m%d.m%dOff", k, k); pl_vis(p, !inpool);
            snprintf(p, sizeof p, "anim-group.mg.m%d.m%dCk", k, k); pl_vis(p, inpool);
            snprintf(p, sizeof p, "anim-group.mg.m%d.m%dSt", k, k); pl_text(p, inpool ? "" : "NOT IN POOL");
            snprintf(p, sizeof p, "anim-group.mg.m%d.m%dSel", k, k); pl_vis(p, g_pl_smode == 1 && s->map == m);
            snprintf(p, sizeof p, "anim-group.mg.m%d.m%dFrame", k, k); pl_vis(p, PS.gfoc == k || PS.ghv == k);
        }
        int pn = pl_pool_n();
        snprintf(b, sizeof b, "%d OF %d MAPS IN THE POOL", pn, nm); pl_text("anim-group.mg.mgCount", b);
        int f = PS.gfoc;
        pl_text("anim-group.mg.mgFoc", f >= 0 && f < nm ? mf_map_name(idx[f]) : f == nm ? "VOTE FROM POOL" : f == nm + 1 ? "RANDOM FROM POOL" : "");
        for (int k = 0; k < 2; k++) {
            snprintf(p, sizeof p, "anim-group.mg.mo%d", k); pl_vis(p, g_pl_smode == 1);
            snprintf(p, sizeof p, "anim-group.mg.mo%d.moCk%d", k, k); pl_vis(p, g_pl_smode == 1 && s->map == (k ? PL_MAP_RANDOM : PL_MAP_VOTE));
            snprintf(p, sizeof p, "anim-group.mg.mo%d.moFill%d", k, k); gu_fade(p, g_pl_smode == 1 && (PS.gfoc == nm + k || PS.ghv == nm + k));
        }
        pl_text("anim-group.mg.mgHelp", g_pl_smode == 1 ? "Pick the map of the next match, or let the lobby vote / the server pick at random from the pool. Greyed maps are not in the pool: picking one adds it." :
                "Select a map to put it in the pool or take it out. VOTE and RANDOM pick from the pool only. Maps a member's game cannot load are not listed.");
    }
    // footer
    pl_text("anim-group.pBackTx", "BACK");
    pl_text("anim-group.pSelTx", grid ? (g_pl_smode == 1 ? "CHOOSE" : "IN / OUT OF POOL") : "CHANGE");
    pl_vis("anim-group.pPrevIc", g_pl_smode == 0); pl_vis("anim-group.pNextIc", g_pl_smode == 0); pl_vis("anim-group.pTabTx", g_pl_smode == 0);
    pl_text("anim-group.pTabTx", "TABS");
    const char *act = PS.tab == 3 && g_pl_smode == 0 ? (s->own ? "REMOVE PLAYER" : "") : grid ? (s->own ? "ALL MAPS" : "") : (s->own ? "RESET TO DEFAULT" : "");
    pl_text("anim-group.pActTx", act);
    pl_vis("anim-group.pActIc", act[0] != 0);
    pl_text("anim-group.msgTx", PL.msg_until && GetTickCount64() < PL.msg_until ? PL.msg : "");
}
static void ps_tick(uint64_t now) {
    uint64_t root = ui_w("anim-group");
    if (!root) return;
    if (!PS.up || root != PS.last_root) {
        memset(&PS, 0, sizeof PS);
        PS.up = 1; PS.enter_ms = now; PS.last_root = root; PS.dirty = 1; PS.hv = PS.ghv = PS.thv = -1;
        PS.h_sel = PS.h_back = PS.h_l = PS.h_r = PS.h_pv = PS.h_nx = PS.h_act = 1; PS.hk_x = 1;
        PS.t_u = PS.t_d = PS.t_l = PS.t_r = ~0ULL; PS.h_u = PS.h_d = PS.h_lr = PS.h_rr = 1;
        gu_fade_reset();
        if (g_pl_smode == 1) { int idx[PS_GRID], n = pl_maps(idx, PS_GRID); PS.gfoc = n; for (int i = 0; i < n; i++) if (idx[i] == PL.s.map) PS.gfoc = i; if (PL.s.map == PL_MAP_RANDOM) PS.gfoc = n + 1; }
        xlog("private: settings page up (%s)", g_pl_smode ? "CHOOSE MAP" : "EDIT SETTINGS");
    }
    int sel = menu_edge(0x6695c5b7921bb5ddULL /* menu-select */, &PS.h_sel);
    int up = gu_rep(&PS.h_u, &PS.t_u, fnv64("menu-up")), down = gu_rep(&PS.h_d, &PS.t_d, fnv64("menu-down"));
    int left = gu_rep(&PS.h_lr, &PS.t_l, fnv64("menu-left")), right = gu_rep(&PS.h_rr, &PS.t_r, fnv64("menu-right"));
    int pv = MENU_PREV_TAB(&PS.h_pv), nx = MENU_NEXT_TAB(&PS.h_nx);
    int act = menu_edge_pad("menu-action", &PS.h_act);
    if (game_focused()) act |= ne_key_edge('X', &PS.hk_x);
    int click = g_click_edge;
    if (sel && ui_select_is_mouse()) sel = 0;          // (a click acts through the hit tests at its press)
    if (now - PS.enter_ms < 150) sel = up = down = left = right = pv = nx = act = click = 0;
    int grid = ps_is_grid(), n = ps_count();
    char p[112];
    // tabs: bumpers, Q / E, a click on a tab
    if (g_pl_smode == 0) {
        int tclick = -1;
        if (click) for (int k = 0; k < 4 && tclick < 0; k++) { snprintf(p, sizeof p, "anim-group.tabs.tabHit%d", k); if (ui_mouse_over(p, 1)) tclick = k; }
        if (game_focused()) { static int hq = 1, he = 1; pv |= ne_key_edge('Q', &hq); nx |= ne_key_edge('E', &he); }
        int nt = tclick >= 0 ? tclick : pv ? (PS.tab + 3) % 4 : nx ? (PS.tab + 1) % 4 : PS.tab;
        if (nt != PS.tab) { PS.tab = nt; PS.foc = 0; PS.gfoc = 0; PS.dirty = 1; pl_sfx(now); grid = ps_is_grid(); n = ps_count(); click = 0; }
    }
    if (click && ui_mouse_over("anim-group.pBackHit", 1)) { ui_sfx("sfx-cycle"); pop_page(); return; }
    if (click && ui_mouse_over("anim-group.pActHit", 1)) { ps_action(now); click = 0; }
    if (grid) {
        int idx[PS_GRID], nm = pl_maps(idx, PS_GRID), f = PS.gfoc;
        int hv = -1;
        for (int k = 0; k < nm && hv < 0; k++) { snprintf(p, sizeof p, "anim-group.mg.m%d.m%dHit", k, k); if (ui_mouse_over(p, 1)) hv = k; }
        if (g_pl_smode == 1) for (int k = 0; k < 2 && hv < 0; k++) { snprintf(p, sizeof p, "anim-group.mg.mo%d.moHit%d", k, k); if (ui_mouse_over(p, 1)) hv = nm + k; }
        if (hv != PS.ghv) { PS.ghv = hv; PS.dirty = 1; }
        if (f >= nm) {                                   // on VOTE / RANDOM (right column)
            if (up && f == nm + 1) f = nm;
            if (down && f == nm) f = nm + 1;
            if (left && nm) f = nm - 1 < 4 ? nm - 1 : 4;     // (back to the grid's first row, last column)
        } else {
            if (left && f % 5) f--;
            if (right) { if (f % 5 < 4 && f + 1 < nm) f++; else if (g_pl_smode == 1) f = nm; }
            if (up && f >= 5) f -= 5;
            if (down) { if (f + 5 < nm) f += 5; else if (g_pl_smode == 1) f = nm + 1; }
        }
        if (f != PS.gfoc) { PS.gfoc = f; PS.dirty = 1; pl_sfx(now); }
        if (click && hv >= 0) { PS.gfoc = hv; ps_grid_pick(hv, now); }
        else if (sel && PS.gfoc >= 0 && PS.gfoc < n) ps_grid_pick(PS.gfoc, now);
    } else {
        int hv = -1, side = 0;
        for (int k = 0; k < n && k < PS_NROW && hv < 0; k++) {
            snprintf(p, sizeof p, "anim-group.rw.row%d.rHitL%d", k, k);
            if (ui_mouse_over(p, 1)) { hv = k; side = -1; break; }
            snprintf(p, sizeof p, "anim-group.rw.row%d.rHitR%d", k, k);
            if (ui_mouse_over(p, 1)) { hv = k; side = 1; break; }
            snprintf(p, sizeof p, "anim-group.rw.row%d.rHit%d", k, k);
            if (ui_mouse_over(p, 1)) hv = k;
        }
        if (hv != PS.hv) { PS.hv = hv; PS.dirty = 1; }
        int f = PS.foc;
        if (up && n) { f = (f + n - 1) % n; pl_sfx(now); }
        if (down && n) { f = (f + 1) % n; pl_sfx(now); }
        { int wn = wheel_notches(); if (wn && n) { f -= wn; if (f < 0) f = 0; if (f >= n) f = n - 1; pl_sfx(now); } }
        if (click && hv >= 0) f = hv;
        if (f != PS.foc) { PS.foc = f; PS.dirty = 1; }
        if (left) ps_change(-1, now);
        if (right || sel) ps_change(1, now);
        if (click && hv >= 0 && side) ps_change(side, now);
        if (click && hv >= 0 && !side && PS.tab != 3) ps_change(1, now);
    }
    if (act) ps_action(now);
    { static int lpd = -1; if (lpd != g_pad_mode) { lpd = g_pad_mode; PS.dirty = 1; } }
    if (PS.dirty || !(g_frame % 20)) { PS.dirty = 0; ps_fill(); }
    gu_fade_tick(now);
}

// ------------------------------------------------------------------ the driver (every frame)
static void pl_reply(uint64_t now) {
    LONG h = g_pl_have;
    if (!h) return;
    int sub = PL.inflight_sub;
    unsigned seq = PL.inflight_seq;
    if (h == 1) {
        PL.fails = 0; PL.reply_ms = now;
        if (sub == PL_S_RULES) pv_parse(g_pl_rep);
        else {
            pl_state_t s;
            pl_parse_state(g_pl_rep, &s);
            if (sub == PL_S_STATE && seq < PL.set_seq) { /* an answer from before our last write: not believed */ }
            else {
                int was_in = PL.s.in;
                if (!s.av && PL.s.av && s.in) s.av = PL.s.av;
                PL.s = s; PL.have = 1;
                if (s.err[0]) { pl_msg(pl_err_text(s.err), 0); if (sub == PL_S_JOIN) { snprintf(PLL.err, sizeof PLL.err, "%s", pl_err_text(s.err)); PLL.dirty = 1; } xlog("private: %d -> err %s", sub, s.err); }
                else if (sub == PL_S_JOIN) { pl_msg("JOINED THE LOBBY", 1); if (PLL.code_open) pl_code_close("joined"); PL.go_seen = s.go; xlog("private: joined lobby %s (%d members)", s.code, s.n); }
                else if (sub == PL_S_CREATE) xlog("private: lobby %s created", s.code);
                else if (sub == PL_S_START) pl_msg("STARTING", 1);
                if (was_in != s.in) xlog("private: %s lobby %s", s.in ? "in" : "left the", s.in ? s.code : "");
                // a launch: a new go while the lobby is launching takes this member to the search page
                if (s.in && s.st == 1 && s.go != PL.go_seen) {
                    PL.go_seen = s.go;
                    if (match_substate() != 6 && ms_on_menu()) pl_launch_search("the host started");
                } else if (s.st != 1) PL.go_seen = s.go;
                if (PL.want_create && sub == PL_S_STATE) {
                    PL.want_create = 0;
                    if (!s.in) pl_queue(PL_S_CREATE, "");
                }
                if (PL.reopen_wait && s.in) { PL.reopen_wait = 0; PL.reopen_push = 1; PL.reopen_t0 = now; }     // pushed by feature_privlobby once the post-match pages are done
                else if (PL.reopen_wait) PL.reopen_wait = 0;
                PLL.dirty = 1; PS.dirty = 1;
            }
        }
    } else {
        PL.fails++;
        if (sub == PL_S_JOIN) { snprintf(PLL.err, sizeof PLL.err, "NO ANSWER FROM THE SERVER"); PLL.dirty = 1; }
        if (sub != PL_S_STATE && sub != PL_S_RULES) pl_msg("NO ANSWER FROM THE SERVER - TRY AGAIN", 0);
    }
    InterlockedExchange(&g_pl_have, 0);
}
static void feature_privlobby(void) {
    static uint64_t P_MAIN;
    if (!P_MAIN) P_MAIN = page_id("main-menu");
    uint64_t now = GetTickCount64(), top = top_page();
    pl_reply(now);
    pl_load_gate(top);                            // match found: mod pages on top closed before the map load
    int on_lobby = top == pl_lobby_id(), on_set = top == pl_set_id(), in_match = match_substate() == 6;
    if (in_match || g_mf_code_now >= 100) {
        pv_tick(now);
        pv_solo_keep(now);
        if (PL.s.in) PL.reopen = 1;
        PLL.up = 0; PS.up = 0;
        return;
    }
    pv_tick(now);
    // back from a private match: once the MP menu is on top again, ask, and open the lobby page if we are still in the lobby
    if (PL.reopen && top == P_MAIN && ms_on_menu()) { PL.reopen = 0; PL.reopen_wait = 1; PL.poll_at = 0; }
    // the lobby page waits for the clan post-match pages (scoreboard to1/clan13x, supply counter). Pushed over the scoreboard it covered it, clan13 closed
    // it as "page popped" and LEAVE LOBBY then dropped the player onto that dead scoreboard page with no way out.
    if (PL.reopen_push) {
        if (!PL.s.in || now - PL.reopen_t0 > 120000) PL.reopen_push = 0;
        else if (top == P_MAIN && ms_on_menu() && !g_pm.pending && !cl13_post_active() && g_mq_n == 0) {
            PL.reopen_push = 0; push_page("to1/private13");
            xlog("private: back from the match - lobby page again (%llu ms after the lobby answer)", (unsigned long long)(now - PL.reopen_t0));
        }
    }
    // a post-match scoreboard page nobody owns any more (clan13 closed it while it was covered): popped so the menu below comes back
    static uint64_t dead0;
    if (top == cl13x_page_id() && !g_c13x.on && g_mq_n == 0) {
        if (!dead0) dead0 = now;
        else if (now - dead0 > 1000) { dead0 = 0; pop_page(); xlog("private: closed post-match scoreboard page left on top - popped"); }
    } else dead0 = 0;
    // the lobby page left while the code box was up: the engine popped it on Backspace / B - pushed again (at most 8 times in 3 s)
    if (!on_lobby && PLL.up) {
        PLL.up = 0;
        static uint64_t win0; static int cnt;
        if (PLL.code_open && top == P_MAIN && game_focused()) {
            if (now - win0 > 3000) { win0 = now; cnt = 0; }
            if (cnt++ < 8) {
                int bs = (GetAsyncKeyState(VK_BACK) & 0x8000) || (PLL.bs_ms && now - PLL.bs_ms < 400);
                if (bs) {
                    if (!PLL.hk[VK_BACK] && PLL.cur > 0) PLL.code[--PLL.cur] = 0;
                    PLK.valid = 1; PLK.cur = PLL.cur; memcpy(PLK.code, PLL.code, sizeof PLK.code);
                }                                         // (B on the pad: the box closes, the page comes back without it)
                push_page_now("to1/private13");
                xlog("private: the engine popped the lobby page (%s) - pushed again", bs ? "Backspace while typing" : "back while the code box was up");
                return;
            }
        }
    }
    if (!on_set) PS.up = 0;
    if (!pl_off() && !g_pl_busy && !g_pl_have) {      // one request at a time: a queued write first, else the poll
        if (PL.q_n) {
            if (pl_ask(PL.q_sub[0], PL.q_arg[0])) { PL.q_n--; memmove(PL.q_sub, PL.q_sub + 1, (size_t)PL.q_n * sizeof PL.q_sub[0]); memmove(PL.q_arg, PL.q_arg + 1, (size_t)PL.q_n * sizeof PL.q_arg[0]); }
        }
        else if (now >= PL.poll_at && (on_lobby || on_set || PL.s.in || PL.want_create || PL.reopen_wait) && ms_on_menu()) {
            if (pl_ask(PL_S_STATE, "")) PL.poll_at = now + (on_lobby || on_set ? 1200 : 2500);
        }
    }
    if (on_lobby) pl_lobby_tick(now);
    else if (on_set) ps_tick(now);
}
