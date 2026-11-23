// gunlimit.c - per-team gun limits for t2r-ext (e.g. a Tactical Shotgun limit of 1 per team, to prevent the tac shotgun
// meta). Included from t2r-ext.c next to interrogation.c (uses its statics: loadout_t, lo_of, lo_read_obj, lo_write_obj, ...).
//
// The DAEMON is the arbiter (tools/gunlimit.py, op 0xDE / 0xDF): this file reports the limited guns of the loadout the player
// intends to spawn with (the pending pick, else the lobby object's) every 2 s in a match - 0.5 s while the loadout list is open -
// and at once when the pick changes, and shows what the daemon answers:
//   - full = limited guns the other teammates hold up to the max: every class / custom loadout containing one is dimmed in the
//     CHOOSE LOADOUT / CHANGE LOADOUT list (row cost "TOO MANY", the description starts "Too many of <GUN> on team."), and
//     selecting it is refused with a buzzer. Outside a match (GEAR UP from the main menu: g_lo_state LO_LIST / LO_EDIT, or no
//     live match) nothing is restricted.
//   - deny = a claim the daemon refused (two teammates picked at the same instant / an old pick / a custom loadout loaded at
//     match start): the server decision wins - the player is switched to the first preset class without a taken limited gun
//     (before the spawn: written at once; after it: pending for the next life) with a message.
//   - spawnkit_hook calls gl_spawn_fix() first: a loadout that would spawn with a gun the cache says is taken is swapped for that
//     fallback class before the spawn kit runs.
// The holder is released by claiming a loadout without the gun, leaving, or the match ending (the daemon prunes it).
// PRE-MATCH: the claims start the moment the match is formed (lobby countdown = team known: gl_countdown) and the
// daemon ranks them (earliest claim wins, tie = lowest slot; answers `pend` for ~0.6 s first). A refused claim switches the player to
// the first preset class without the gun BEFORE the first spawn, with "Only one Tactical Shotgun per team - a teammate already has it.
// Your loadout was switched to <CLASS>." CHOOSE LOADOUT (and GEAR UP opened during the countdown) dims 'TOO MANY' rows. gl_spawn_fix
// uses the answer gl_tick prefetched on the worker thread (gl_sync is non-blocking); no cached decision
// = a held gun is kept, else the fallback class (never risk a second gun). Log lines: "gunlimit: pre-match ...".
// Switch: t2r-no-gunlimit.txt next to the exe = off (nothing is claimed, nothing dimmed).
// The table order is the wire's bit order and must equal tools/gunlimit.py LIMITS (tools/tests/test_gunlimit.py compares).
static const struct { const char *ids[3]; int max; const char *name; } GL_TABLE[] = {
    {{"shotgun-tactical", "shotgun-tactical-supp"}, 1, "TACTICAL SHOTGUN"},
};
#define GL_N ((int)(sizeof GL_TABLE / sizeof *GL_TABLE))

static struct { int on, team; uint32_t held, deny, full, pend, asked, answered; uint64_t at, sent; } g_gl;
static uint32_t g_gl_reqmask;               // the mask of the request in flight (the reply answers exactly this)
static volatile LONG g_gl_busy, g_gl_have;
static uint8_t g_gl_req[66];
static char g_gl_rep[256];
static int g_no_gl = -1;

static int gl_off(void) {
    if (g_no_gl < 0) {
        FILE *f = exe_side_open("t2r-no-gunlimit.txt", "r");
        g_no_gl = f != NULL;
        if (f) fclose(f);
        xlog("gunlimit: %s", g_no_gl ? "off (t2r-no-gunlimit.txt)" : "on - per-team gun limits arbitrated by the server");
    }
    return g_no_gl;
}
static DWORD WINAPI gl_worker(LPVOID arg) {
    (void)arg;
    HMODULE ws = LoadLibraryA("ws2_32.dll");
    t2r_sin a;
    t2r_net net;
    LONG res = 2;
    if (ws && hm_server(&a) && t2r_net_load(&net, ws)) {
        uint8_t frame[3 + sizeof g_gl_req];
        int n = (int)sizeof g_gl_req + 1;
        frame[0] = (uint8_t)n; frame[1] = 0; frame[2] = 0xDE;
        memcpy(frame + 3, g_gl_req, sizeof g_gl_req);
        char rep[sizeof g_gl_rep];
        int got = t2r_rpc(&net, &a, frame, n + 2, rep, (int)sizeof rep - 1, 2000, 2000, 2000, NULL);   // (the old plain connect() blocked ~21 s on a dead tunnel)
        int ln = got >= 3 ? (rep[0] & 0xff) + ((rep[1] & 0xff) << 8) : 0;
        if (ln >= 1 && got >= ln + 2 && (uint8_t)rep[2] == 0xDF && ln < (int)sizeof g_gl_rep) {
            memcpy(g_gl_rep, rep + 3, ln - 1);
            g_gl_rep[ln - 1] = 0;
            res = 1;
            srv_mark_alive();
        }
    }
    InterlockedExchange(&g_gl_have, res);
    InterlockedExchange(&g_gl_busy, 0);
    return 0;
}
static int gl_ask(uint32_t mask) {          // 1 = request started
    static char tok[65];
    if (!tok[0] && !clan_token(tok)) { tok[0] = 0; return 0; }
    if (g_gl_have || InterlockedCompareExchange(&g_gl_busy, 1, 0)) return 0;
    memcpy(g_gl_req, tok, 64);
    g_gl_req[64] = (uint8_t)mask; g_gl_req[65] = (uint8_t)(mask >> 8);
    HANDLE h = CreateThread(NULL, 0, gl_worker, NULL, 0, NULL);
    if (!h) { InterlockedExchange(&g_gl_busy, 0); return 0; }
    CloseHandle(h);
    g_gl.asked = mask;
    g_gl_reqmask = mask;
    return 1;
}

// ---- which limited guns a loadout carries (bit i = GL_TABLE[i]); the rows' weapon ids are what the spawn kit gives
static const char *gl_row_id(int slot, uint32_t row) {
    const uint32_t *cnt = (const uint32_t *)VMA(0x1800A0DA4);
    if (slot < 0 || slot > 2 || row == 0xffffffffu || row >= cnt[slot]) return NULL;
    const uint8_t *r = slot == 2 ? lo_purch_tab() + row * 0x40
                     : slot == 0 && !g_large_tab ? (const uint8_t *)VMA(0x1800A0DB0) + row * 0x38 : weapon_row(slot, row);
    return r ? *(const char **)(r + 0x10) : NULL;
}
static uint32_t gl_mask(const loadout_t *l) {
    uint32_t m = 0;
    for (int s = 0; s < 3; s++) {
        const char *id = gl_row_id(s, l->w[s]);
        if (!id) continue;
        for (int i = 0; i < GL_N; i++)
            for (int k = 0; k < 3 && GL_TABLE[i].ids[k]; k++)
                if (!strcmp(id, GL_TABLE[i].ids[k])) m |= 1u << i;
    }
    return m;
}
static uint32_t gl_intended(void) {         // the limited guns of the loadout the player will spawn with
    if (g_lo_pending) return gl_mask(lo_of(g_lo_pending - 1));
    loadout_t cur;
    memset(&cur, 0xff, sizeof cur.w);
    lo_read_obj(&cur);
    return gl_mask(&cur);
}
// this life's loadout (the lobby object's, not a pending pick) carries a Tactical Shotgun (GL_TABLE row 0); re-read once a second (skills.c sprint meter)
static int gl_life_has_tac(void) {
    static uint64_t at; static int v;
    uint64_t now = GetTickCount64();
    if (now - at < 1000) return v;
    at = now;
    loadout_t cur;
    memset(&cur, 0xff, sizeof cur.w);
    lo_read_obj(&cur);
    v = (gl_mask(&cur) & 1u) != 0;
    return v;
}
static int gl_countdown(void) {              // the match is formed and counting down (vote / CHOOSE LOADOUT / booster stages): the team is known
    uint8_t *o = lobby_obj();
    return o && *(int *)(o + 0x1b4) == 2;
}
static int gl_in_match_ctx(void) { return g_lo_state == LO_CHOOSE || g_lo_state == LO_MATCH || match_substate() >= 3 || gl_countdown(); }
static int gl_active(void) {                // the restriction is shown / enforced: a live match, a fresh daemon answer, not GEAR UP
    return !gl_off() && g_gl.on && GetTickCount64() - g_gl.at < 8000 &&
           ((g_lo_state != LO_LIST && g_lo_state != LO_EDIT) || (g_lo_state == LO_LIST && gl_countdown()));   // GEAR UP during the match countdown is pre-match: restricted
}
static uint32_t gl_blocked(const loadout_t *l) { return gl_active() ? gl_mask(l) & g_gl.full : 0; }
static const char *gl_name_of(uint32_t m) {
    for (int i = 0; i < GL_N; i++) if (m >> i & 1) return GL_TABLE[i].name;
    return NULL;
}
// list rows: 1 + the gun's display name when the row's loadout holds a gun a teammate has taken
static int gl_row_blocked(int row, const char **name) {
    uint32_t b = gl_blocked(lo_of(row));
    if (name) *name = gl_name_of(b);
    return b != 0;
}
// first preset class (then custom loadout) with none of the blocked guns; -1 = none
static int gl_fallback(uint32_t blocked) {
    for (int r = N_CUSTOM; r < N_CUSTOM + N_CLASSES; r++) {
        const loadout_t *l = lo_of(r);
        if (!(gl_mask(l) & blocked) && lo_valid(l)) return r;
    }
    for (int k = 0; k < g_lo_n; k++) {         // (custom slots: the created ones too)
        const int r = lo_slot_idx(k);
        const loadout_t *l = lo_of(r);
        if (l->w[0] != 0xffffffffu && !(gl_mask(l) & blocked) && lo_valid(l)) return r;
    }
    return -1;
}
#define GL_SAY_HOLD_MS 20000u
static struct { char m[160]; float secs; uint64_t until; } g_gl_say;      // a refusal said on the menu, waiting for the notice panel (gl_say)
static int dn_page_ok(uint64_t tp);                                          // denynote.c
static void gl_say(uint32_t blocked, int to) {
    char m[160], b[40];
    const char *nm = gl_name_of(blocked);
    if (to >= 0) {
        char t[48]; int k = 0, up = 1;          // "TACTICAL SHOTGUN" -> "Tactical Shotgun"
        for (const char *c = nm ? nm : "?"; *c && k < 46; c++, k++) { t[k] = up ? *c : (*c >= 'A' && *c <= 'Z' ? *c + 32 : *c); up = *c == ' '; }
        t[k] = 0;
        int mx = 1;
        for (int i = 0; i < GL_N; i++) if (nm && !strcmp(nm, GL_TABLE[i].name)) mx = GL_TABLE[i].max;
        snprintf(m, sizeof m, "Only %s %s per team - a teammate already has %s. Your loadout was switched to %s.",
                 mx == 1 ? "one" : "a few", t, mx == 1 ? "it" : "them", lo_name(to, b, sizeof b));
    }
    else snprintf(m, sizeof m, "Too many of %s on team.", nm ? nm : "?");
    const float secs = to >= 0 ? 6.0f : 4.0f;
    if (dn_show(m, secs)) return;
    if (match_substate() == 6) { msg_hook(m, secs, 0, 0); return; }
    // (+ Coco, same minute): the pre-match refusal comes while the FIND MATCH page is up - no notice widgets there, and the old
    // fallback (msg_hook -> winmm's HUD message, one shared text id) drew the text table's "Placeholder text. " x100 over the whole menu and
    // the CHOOSE LOADOUT page after it. On the menu the notice waits for a page with the notice panel (CHOOSE LOADOUT comes ~2 s later), gl_tick.
    snprintf(g_gl_say.m, sizeof g_gl_say.m, "%s", m);
    g_gl_say.secs = secs;
    g_gl_say.until = GetTickCount64() + GL_SAY_HOLD_MS;
    xlog("gunlimit: notice held for the loadout page (page 0x%llx has no notice panel, substate %d)", (unsigned long long)top_page(), (int)match_substate());
}
// gl_tick: a held menu notice shows once a page with the notice panel is up; dropped after GL_SAY_HOLD_MS or when the match HUD takes over
static void gl_say_held_tick(uint64_t now) {
    if (!g_gl_say.until) return;
    if (now >= g_gl_say.until || match_substate() == 6) {
        xlog("gunlimit: held notice dropped (%s) - \"%.100s\"", now >= g_gl_say.until ? "no notice panel came" : "the match started", g_gl_say.m);
        g_gl_say.until = 0;
        return;
    }
    uint64_t tp = top_page();
    if (!tp || !dn_page_ok(tp)) return;
    if (dn_show(g_gl_say.m, g_gl_say.secs)) { xlog("gunlimit: held notice shown on the loadout page"); g_gl_say.until = 0; }
}
// the server said no (or the cache says taken at the spawn): put the player on the fallback class. Before the first spawn the
// lobby object is written now; once in the game the pick waits for the next life like any mid-match pick.
static void gl_switch(uint32_t blocked, const char *why) {
    int r = gl_fallback(blocked);
    xlog("gunlimit: %s%s - %s taken on the team, %s", gl_countdown() || (match_substate() != 6 && g_lo_state != LO_MATCH) ? "pre-match " : "", why, gl_name_of(blocked) ? gl_name_of(blocked) : "?",
         r >= 0 ? "switching loadout" : "no allowed loadout to switch to");
    if (r < 0) { gl_say(blocked, -1); return; }
    g_lo_active = r;
    if (match_substate() == 6 || g_lo_state == LO_MATCH) g_lo_pending = r + 1;
    else { g_lo_pending = 0; lo_write_obj(lo_of(r)); }
    lo_save();
    g_gl.asked = ~0u;                         // claim the new loadout at once
    gl_say(blocked, r);
}
static void gl_apply_reply(void);
// Spawn-time decision from the cache - NEVER waits (the old synchronous gl_sync slept up to 2.5 s on the game thread when the
// daemon was slow / unreachable). The claims are prefetched asynchronously by gl_tick (worker thread; as soon as the match is formed /
// the loadout changes / every 0.25-2 s), so by the first spawn the answer is normally cached. 1 = decided (the cache answers for the
// loadout we are about to spawn with), 0 = server unreachable / no token (no restriction without the server), -1 = no usable decision
// yet (no answer / still being ranked `pend`): the caller keeps a gun the server already granted, else switches to the fallback.
static volatile LONG g_gl_failed_at;         // low 32 bits of GetTickCount64 of the last failed request (0 = none)
static volatile LONG g_gl_fails;             // failed requests in a row (reset by an answer): the 'recent failure' window and the ask interval grow with it
static void gl_note_fail(void) { LONG t = (LONG)GetTickCount64(); InterlockedExchange(&g_gl_failed_at, t ? t : 1); InterlockedIncrement(&g_gl_fails); }
static const char *g_gl_path = "";           // decision path of the last gl_sync (for the log)
static int gl_sync(void) {
    uint32_t want = gl_intended();
    if (!want) { g_gl_path = "no limited gun"; return 1; }
    if (InterlockedCompareExchange(&g_gl_have, 0, 0)) {          // a finished request nobody has applied yet: apply it now (no waiting)
        LONG res = InterlockedExchange(&g_gl_have, 0);
        if (res == 1) gl_apply_reply();
        else { gl_note_fail(); g_gl_path = "drained failed reply"; return 0; }
        want = gl_intended();                                    // (a switch may have changed the loadout)
        if (!want) { g_gl_path = "switched to a loadout without a limited gun"; return 1; }
    }
    if (g_gl.answered == want && GetTickCount64() - g_gl.at < 4000) {
        if (!g_gl.on) { g_gl_path = "cached: limits off"; return 1; }
        if (!(want & g_gl.pend)) { g_gl_path = "cached: server answered"; return 1; }   // granted / refused (full, handled by the caller)
        g_gl.answered = ~0u;                                     // still being ranked: ask again now (the spawn waits briefly for it)
        g_gl_path = "cached answer still pending (ranking)";
        if (!g_gl_busy && !g_gl_have && gl_ask(want)) g_gl.sent = GetTickCount64();
        return -1;
    }
    LONG fa = g_gl_failed_at;
    if (fa && (uint32_t)((LONG)GetTickCount64() - fa) < (4000u << (g_gl_fails > 3 ? 2 : g_gl_fails > 1 ? 1 : 0))) { g_gl_path = "recent failed request (server unreachable)"; return 0; }
    if (!g_gl_busy && !g_gl_have) {                              // nothing in flight: start the claim for the next life / retry, do not wait for it
        if (!gl_ask(want)) { g_gl_path = "no clan token"; return 0; }
        g_gl.sent = GetTickCount64();
        g_gl_path = "no cached answer, claim started (async)";
        return -1;
    }
    g_gl_path = "no cached answer, request in flight";
    return -1;
}
static void gl_spawn_fix(void) {            // spawnkit_hook, before the kit: a loadout with a taken gun never spawns
    if (gl_off() || !gl_in_match_ctx()) return;
    if (!gl_intended()) return;
    int r = gl_sync();
    if (r < 0 && (g_gl_busy || g_gl_have)) {    // a reachable daemon answers in ~0.1-0.6 s (settle window); a short bounded wait
        ULONGLONG t0 = GetTickCount64();        // beats stripping the player's pick. An unreachable daemon is caught by g_gl_failed_at above (no wait).
        while (r < 0 && GetTickCount64() - t0 < 700) {   // a first claim is answered `pend` for ~0.6 s (settle window) - keep draining / re-asking inside the 700 ms,
            if (InterlockedCompareExchange(&g_gl_have, 0, 0)) { r = gl_sync(); continue; }   // (gl_sync re-asks on pend); one round trip alone ended in a stripped pick
            if (!g_gl_busy) break;                    // nothing in flight any more (no clan token / failed ask): the fallback below decides
            Sleep(5);
        }
        if (r < 0) xlog("gunlimit: spawn waited %llu ms for the daemon (%s)", (unsigned long long)(GetTickCount64() - t0), g_gl_path);
    }
    uint32_t want = gl_intended();
    if (r < 0 && want && (want & g_gl.held) == want) {   // a slow answer must not strip a gun the server already granted us
        xlog("gunlimit: pre-match - no daemon decision at the spawn (%s), but mask %u is already held - kept", g_gl_path, want);
        return;
    }
    if (r < 0) {
        xlog("gunlimit: pre-match - no daemon decision at the spawn (%s; loadout mask %u): not risking a second limited gun", g_gl_path, want);
        gl_switch(want, "no server decision at the spawn");
        return;
    }
    uint32_t b = want & g_gl.full & ~g_gl.held;
    if (r == 1 && g_gl.on && (want & g_gl.pend)) b |= want & g_gl.pend;
    if (b) gl_switch(b, "spawn");
    else if (r == 1 && g_gl.on) xlog("gunlimit: pre-match - spawn loadout cleared by the server (mask %u, held %u)", want, g_gl.held);
}
static void gl_buzz(void) {                 // refused selection: the game's own menu error (gui2-game.bin sfx-menu-error, gbl-menu bank - loaded in menus)
    ui_deny(NULL);                            // the shared denied sound (one play per 300 ms; the message follows from gl_say)
}
static void gl_denied_pick(uint32_t blocked) {
    gl_buzz();
    gl_say(blocked, -1);
    static int nl; if (LOGCAP(nl, 20)) xlog("gunlimit: pick refused - %s is taken on the team", gl_name_of(blocked) ? gl_name_of(blocked) : "?");
}
static int gl_pick_refused(int row) {       // lo_list_page, on a selection: 1 = refuse (denied feedback given)
    uint32_t b = gl_blocked(lo_of(row));
    if (!b) return 0;
    gl_denied_pick(b);
    return 1;
}

// ---- list page look: dimmed rows + the message, re-asserted every few frames
static uint32_t g_gl_dim;                  // rows we have dimmed
static void gl_list_style(int entered) {
    static uint64_t last;
    if (!entered && g_frame - last < 6) return;
    last = g_frame;
    char p[96];
    for (int r = 0; r < N_CUSTOM + N_CLASSES; r++) {
        int bl = gl_row_blocked(r, NULL);
        if (!bl && !(g_gl_dim >> r & 1)) continue;
        snprintf(p, sizeof p, "anim-group.list.contents.Skill%d", r);
        uint64_t w = ui_w(p);
        if (!w) continue;
        w_alpha(w, bl ? 0.35f : 1.0f);
        snprintf(p, sizeof p, "anim-group.list.contents.Skill%d.costText", r);
        ui_text(p, bl ? "<font color=\"#d23c32\">TOO MANY</font>" : r == g_lo_active ? (lo_r3() ? R3_EQUIPPED : "EQUIPPED") : "");
        if (bl) g_gl_dim |= 1u << r; else g_gl_dim &= ~(1u << r);
    }
}
// description text for a blocked row, prepended by lo_list_detail
static const char *gl_detail_prefix(int row, char *o, size_t n) {
    const char *nm;
    if (!gl_row_blocked(row, &nm)) return "";
    snprintf(o, n, "<font color=\"#d23c32\">Too many of %s on team.</font>\n\n", nm);
    return o;
}

static void gl_apply_reply(void) {
    char k[16], v[32];
    int n;
    const char *t = g_gl_rep;
    int on = 0, team = 0;
    uint32_t held = 0, deny = 0, full = 0, pend = 0;
    while (sscanf(t, " %15[^= ]=%31s%n", k, v, &n) == 2) {
        int x = atoi(v);
        if (!strcmp(k, "on")) on = x;
        else if (!strcmp(k, "team")) team = x & 1;
        else if (!strcmp(k, "mask")) held = (uint32_t)x;
        else if (!strcmp(k, "deny")) deny = (uint32_t)x;
        else if (!strcmp(k, "full")) full = (uint32_t)x;
        else if (!strcmp(k, "pend")) pend = (uint32_t)x;
        t += n;
    }
    uint32_t prev_full = g_gl.full;
    InterlockedExchange(&g_gl_fails, 0);
    g_gl.on = on; g_gl.at = GetTickCount64(); g_gl.team = team; g_gl.held = held; g_gl.deny = deny; g_gl.full = on ? full : 0;
    g_gl.pend = on ? pend : 0; g_gl.answered = g_gl_reqmask;
    if (on && deny && gl_countdown()) xlog("gunlimit: pre-match - the server refused our claim (mask %u, team %d)", deny, team);
    if (on && prev_full != g_gl.full) xlog("gunlimit: team %d - taken by teammates: %u (we hold %u)", team, g_gl.full, held);
    if (on && deny && (gl_intended() & deny)) gl_switch(deny, "the server refused our claim");
}
static void gl_tick(void) {
    if (gl_off()) return;
    uint64_t now = GetTickCount64();
    gl_say_held_tick(now);
    if (InterlockedCompareExchange(&g_gl_have, 0, 0)) {
        LONG res = InterlockedExchange(&g_gl_have, 0);
        if (res == 1) gl_apply_reply();            // (a failed request: the cache just ages out, no restriction without the server)
        else gl_note_fail();
    }
    if (!gl_in_match_ctx()) {
        if (g_gl.on || g_gl.asked) { g_gl.on = 0; g_gl.full = 0; g_gl.asked = 0; g_gl.held = 0; xlog("gunlimit: left the match context - restriction off"); }
        return;
    }
    uint32_t want = gl_intended();
    int list_open = g_lo_state == LO_CHOOSE || g_lo_state == LO_MATCH;
    uint64_t every = (g_gl.pend & want) ? 250 : list_open ? 500 : gl_countdown() ? 1000 : 2000;   // (a claim still being ranked pre-match: ask again shortly)
    if (g_gl_fails >= 3) {                       // daemon unreachable: jittered backoff (2 s -> 10 s) instead of a connection every 0.25-2 s
        uint64_t bo = t2r_backoff_ms((int)g_gl_fails - 2, 2000, 10000);
        if (every < bo) every = bo;
    }
    if ((want != g_gl.asked || now - g_gl.sent >= every) && !g_gl_busy && !g_gl_have && gl_ask(want)) g_gl.sent = now;
}
