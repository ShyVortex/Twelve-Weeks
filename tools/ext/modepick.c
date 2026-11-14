// modepick.c - the game mode choice for FIND MATCH: SUPPLY RAID / INTERROGATION, each with the live number of players searching in
// that mode. Included from t2r-ext.c right after interrogation.c (uses t2r-ext's statics).
//
// Layout (sketch re/modepick-sketch-1102.jpg, tools/features/modepick_widgets.py): ON the MP main menu, right after the FIND MATCH row an arrow
// and a box open on the right with the modes stacked in it (anim-group.modeBox: modeList.Mode<k> = the SAME native button widget as FIND MATCH, cnt<k> =
// the dim "<n> SEARCHING" text). No page is pushed: the menu stays fully visible.
// Flow: FIND MATCH has no action tag any more. Select (menu-select / pad A) while FIND MATCH has the focus, or a click on it, opens the box (shown, the
// mode rows enabled, focus moved onto the last / default mode). While it is open the ENGINE's own vertical-container focus moves between the mode rows
// (up / down, stick, d-pad); mouse hover moves the focus like the picker lists do; select / click on a mode sends op 0xBC [token][1][mode] to the daemon
// (tools/modeq.py stores it), waits for the ack (2.5 s at most: an old daemon never answers and the search simply goes on as Supply Raid) and pushes
// to1/find-match-menu - winmm's page tick then starts the search itself (mmreq_hook; friends13's party auto-search does the same). Back / left / focus
// leaving the rows / another page on top closes the box and the focus returns to FIND MATCH.
// While open the box polls op 0xBC [token][0][0] every 1.5 s: reply 0xBD "q0=<n> q1=<n> mode=<m> forced=<0|1>" (players searching right now per mode).
// A party member's press is the ready toggle (fr_search_gate): FIND MATCH goes straight to the search page, no box; a leader's pick is the party's mode.
// Off: t2r-no-modepick.txt next to the exe (FIND MATCH pushes the search page directly), t2r-test-autofind.txt (A/B autofind pushes the search page
// itself and a select on FIND MATCH goes straight on: Supply Raid unless the daemon's T2R_MODE forces another). Log: 'modepick:'.
#include "modes.h"                 // MODE_N + MODE_TAB, generated from tools/modes.json (python tools/gen_modes.py): a new mode is a new row there
#define MK_OP 0xBC
// QUICK MATCH: a third row after the real modes (index MODE_N, not in modes.json): "any mode". The daemon takes it as mode 255 and puts the
// player in every mode's queue; it announces that with "any=1" in its 0xBD reply (an old daemon never does: the row then falls back to the default mode
// and logs it). The match's real mode reaches the client like any other (r13_int_mode / the loading screen) - the row is only a queue preference.
#define MK_N (MODE_N + 1)
#define MK_ANY 255

static struct {
    int fade_dir, open, shown, h_sel, h_back, h_l, h_u, h_d, sel, dirty, hov;
    uint64_t open_frame, last_box;
    int q[MK_N], forced, have, mode, anyok, qa;  // last counts, T2R_MODE forced, we have an answer, the daemon's idea of our mode
    int chosen, sent, pick;        // a pick is being sent / acknowledged
    uint64_t chosen_at, poll_at, fill_at, fade_t0, cycle_ms;
} g_mdpk;
static volatile LONG g_mkq_busy, g_mkq_have;
static uint8_t g_mkq_req[70];
static int g_mkq_req_len;
static char g_mkq_rep[128];

static DWORD WINAPI mkq_worker(LPVOID arg) {
    (void)arg;
    HMODULE ws = LoadLibraryA("ws2_32.dll");
    t2r_sin a;
    t2r_net net;
    LONG res = 2;
    if (ws && hm_server(&a) && t2r_net_load(&net, ws)) {
        uint8_t frame[3 + sizeof g_mkq_req];
        int n = g_mkq_req_len + 1;
        frame[0] = (uint8_t)n; frame[1] = 0; frame[2] = MK_OP;
        memcpy(frame + 3, g_mkq_req, g_mkq_req_len);
        char rep[sizeof g_mkq_rep];
        int got = t2r_rpc(&net, &a, frame, n + 2, rep, (int)sizeof rep - 1, 2000, 2000, 2000, NULL);
        int ln = got >= 3 ? (rep[0] & 0xff) + ((rep[1] & 0xff) << 8) : 0;
        if (ln >= 1 && got >= ln + 2 && (uint8_t)rep[2] == 0xBD && ln < (int)sizeof g_mkq_rep) {
            memcpy(g_mkq_rep, rep + 3, ln - 1);
            g_mkq_rep[ln - 1] = 0;
            res = 1;
        }
    }
    InterlockedExchange(&g_mkq_have, res);
    InterlockedExchange(&g_mkq_busy, 0);
    return 0;
}
static int mkq_ask(uint8_t sub, uint8_t mode) {     // 1 = request started
    static char tok[65];
    if (!tok[0] && !clan_token(tok)) { tok[0] = 0; return 0; }
    if (g_mkq_have || InterlockedCompareExchange(&g_mkq_busy, 1, 0)) return 0;
    memcpy(g_mkq_req, tok, 64);
    g_mkq_req[64] = sub; g_mkq_req[65] = mode;
    g_mkq_req_len = 66;
    HANDLE h = CreateThread(NULL, 0, mkq_worker, NULL, 0, NULL);
    if (!h) { InterlockedExchange(&g_mkq_busy, 0); return 0; }
    CloseHandle(h);
    return 1;
}
static int g_mdpk_mm = -1;          // the real mode of this player's match (-1 = not known yet); reset when a search starts / the match is left
static void mkq_parse(const char *t) {     // "q0=<n> q1=<n> .. mode=<m> forced=<0|1>"
    int q[MODE_N] = {0}, m = 0, f = 0, got = 0, ao = 0, qa = 0, mm = -1;
    char k[16];
    int v, n;
    while (sscanf(t, " %15[^= ]=%d%n", k, &v, &n) == 2) {
        if (k[0] == 'q' && k[1] >= '0' && k[1] <= '9') { int i = atoi(k + 1); if (i >= 0 && i < MODE_N) { q[i] = v; got++; } }
        else if (!strcmp(k, "mode")) m = v;
        else if (!strcmp(k, "forced")) f = v;
        else if (!strcmp(k, "any")) ao = v;
        else if (!strcmp(k, "qa")) qa = v;
        else if (!strcmp(k, "mm")) mm = v;          // the mode of the match this player is in (daemon, from the match assignment on)
        t += n;
    }
    if (mm >= 0 && mm < MODE_N) g_mdpk_mm = mm;
    if (got) { memcpy(g_mdpk.q, q, sizeof q); g_mdpk.mode = m; g_mdpk.anyok = ao; g_mdpk.qa = qa; g_mdpk.forced = f; g_mdpk.have = 1; g_mdpk.dirty = 1; }
}
static int mk_off(void) {
    static int off = -1;
    if (off < 0) { FILE *f = exe_side_open("t2r-no-modepick.txt", "r"); off = f != NULL; if (f) fclose(f); if (off) xlog("modepick: off (t2r-no-modepick.txt)"); }
    return off;
}
static int fr_party_member(void);                 // friends13.c: in a party and not its leader
static void fr_member_ready_press(void);          // friends13.c: a member's FIND MATCH press = the READY UP / UNREADY toggle
static int modepick_gate(void) { return 0; }      // (the search request is never held back any more: the box sits in front of the search page, mmreq_hook still asks)
// ---- widgets
#define MK_BOX "anim-group.modeBox"
#define MK_ROW "anim-group.modeBox.modeRow%d.mpHit%d"          // (hover target of a row; ui_mouse_row takes the index twice)
#define MK_FM "anim-group.menuList.FindMatch"
static void gu_fade(const char *path, int on);                     // gearup13.c (the clan page's selection fade)
static void gu_fade_tick(uint64_t now);
static int mk_focused(const char *path) {
    typedef char (*fn_focus)(uint64_t);
    uint64_t w = ui_w(path);
    return w && ((fn_focus)VMA(0x180068BF0))(w) != 0;
}
// Bug: pressing lmb on quick match opened the clan ui. The left button sends menu-select, and "select while row X is focused" fired for the
// FOCUSED row wherever the cursor was - focus still on CLAN (keyboard / pad / last hover) + a click on FIND MATCH opened CLAN (and the reverse). With the
// left button as the only select source (Space / Enter not down) the select counts for a row only while the cursor is over THAT row.
// Follow-up (A/B 178-dev2: clicking quick match with the mouse still opened the clan ui): the earlier check read the button at the moment the select edge
// was seen - a select the engine reports on RELEASE (button already up), or a frame after a short tap, passed as "keyboard" and opened the focused CLAN row.
// Now a select counts for the focused row only when it is NOT the mouse's (ui_select_is_mouse: button down or released < 350 ms ago, Space / Return not
// down); a click acts through g_click_edge + a hit test at the press (the callers' `click && hovered` terms). The dev line proves the source per decision.
static int mk_sel_for(const char *path) {
    static int n;
    int ms = ui_select_is_mouse();
    if (n++ < 60) xlog("select check %s: source %s, LBUTTON %d (up %llu ms ago), cursor over it %d, focused %d, cursor over FIND MATCH %d / CLAN %d -> %s", path, ms ? "mouse" : "key/pad",
        g_lb_now, (unsigned long long)(g_lb_up_ms ? GetTickCount64() - g_lb_up_ms : 0), ui_mouse_over(path, 1), mk_focused(path), ui_mouse_over("anim-group.menuList.FindMatch", 1),
        ui_mouse_over("anim-group.menuList.Clan", 1), ms ? "ignored (the click acts at its press)" : "counts");
    return !ms;
}
static void mk_focus(const char *path) { uint64_t a[1] = {ui_w(path)}; if (a[0]) dc_call(fnv64("menu2-set-focus-to-component"), 1, a); }
// The rows are plain gui2 widgets in the clan overview's row look (card / edge / focus fill + frame, live text); the selection is ours: the engine's
// focus stays on FIND MATCH while the box is open (it is the box's parent), up / down / hover / select / click act on g_mdpk.sel.
static int mk_disabled(int k);
static void mk_sel_fade(int on) {
    char p[96];
    for (int k = 0; k < MK_N; k++) {
        snprintf(p, sizeof p, "anim-group.modeBox.modeRow%d.mpFill%d", k, k); gu_fade(p, on && k == g_mdpk.sel && !mk_disabled(k));
        snprintf(p, sizeof p, "anim-group.modeBox.modeRow%d.mpFrame%d", k, k); gu_fade(p, on && k == g_mdpk.sel && !mk_disabled(k));
    }
}
// The box and its arrow fade in / out over MK_FADE_MS (5 frames at 60 fps, ease out; as in NR: choice panels move, they do not pop). anim = 0: at once (a page change,
// a fresh page instance: nothing visible may be left behind). The fade writes alpha on the box group only (a child of the menu, never on a page root).
#define MK_FADE_MS 90
static float mk_eo(float t) { if (t <= 0.0f) return 0.0f; if (t >= 1.0f) return 1.0f; float u = 1.0f - t; return 1.0f - u * u * u; }
static void mk_alpha(float a) { w_alpha(ui_w(MK_BOX), a); w_alpha(ui_w("anim-group.modeArrow"), a); }
static void mk_show(int on, int anim) {
    if (!on && anim && g_mdpk.fade_dir < 0) return;                    // (already on its way out)
    if (!on && anim && !g_mdpk.shown) return;
    if (!on && !anim && top_page() != page_id("main-menu")) {            // ui_visible resolves against the TOP page: a page covering the menu cannot be reached, so `shown` stays set
        g_mdpk.fade_dir = 0;                                              // and the hide is repeated the moment the menu is on top again (nothing may stay up behind the player's back)
        g_mdpk.shown = 1;      // pick -> search page -> back left the box up at its fade alpha: mk_close's fade had already cleared `shown`, so the retry never ran
        return;
    }
    g_mdpk.shown = on;
    if (!anim) { g_mdpk.fade_dir = 0; mk_alpha(1.0f); ui_visible(MK_BOX, on); ui_visible("anim-group.modeArrow", on); return; }
    g_mdpk.fade_dir = on ? 1 : -1; g_mdpk.fade_t0 = GetTickCount64();
    if (on) { mk_alpha(0.0f); ui_visible(MK_BOX, 1); ui_visible("anim-group.modeArrow", 1); }
}
static void mk_fade_tick(uint64_t now) {
    if (!g_mdpk.fade_dir) return;
    float p = (float)(now - g_mdpk.fade_t0) / (float)MK_FADE_MS;
    if (p >= 1.0f) {
        if (g_mdpk.fade_dir < 0) { ui_visible(MK_BOX, 0); ui_visible("anim-group.modeArrow", 0); g_mdpk.shown = 0; }
        mk_alpha(1.0f); g_mdpk.fade_dir = 0; return;
    }
    mk_alpha(g_mdpk.fade_dir > 0 ? mk_eo(p) : 1.0f - mk_eo(p));
}
static void mk_cycle_sfx(uint64_t now) {                              // the focus sound: user moves only, 150 ms floor (NR hfx-ui-cycle)
    if (now - g_mdpk.cycle_ms >= 150) { g_mdpk.cycle_ms = now; ui_sfx("sfx-cycle"); }
}
// a row that cannot be picked (the daemon forces another mode): 40 % and never the selected look
static int mk_disabled(int k) { return g_mdpk.have && g_mdpk.forced && (k != g_mdpk.mode || k >= MODE_N); }   // (QUICK MATCH is off while a mode is forced)
static void mk_close(const char *why, int refocus) {
    if (!g_mdpk.open) { if (g_mdpk.shown) mk_show(0, 1); return; }
    g_mdpk.open = 0; g_mdpk.chosen = g_mdpk.sent = 0;
    mk_show(0, 1);
    if (refocus) mk_focus(MK_FM);
    xlog("modepick: box closed (%s)", why);
}
static void mk_fill(void) {                                           // never blank: a count not known yet is "...", none searching is a dim "0 SEARCHING"
    char p[96], t[48];
    for (int k = 0; k < MK_N; k++) {
        snprintf(p, sizeof p, "anim-group.modeBox.modeRow%d.mpNm%d", k, k); ui_text(p, k < MODE_N ? MODE_TAB[k].label : "QUICK MATCH");
        snprintf(p, sizeof p, "anim-group.modeBox.modeRow%d.mpCntG%d.mpCnt%d", k, k, k);     // (the number; the NR man icon sits left of it in the same group)
        if (!g_mdpk.have) snprintf(t, sizeof t, "...");
        else snprintf(t, sizeof t, "%d", k < MODE_N ? g_mdpk.q[k] : g_mdpk.qa);     // (QUICK MATCH: everybody searching)
        ui_text(p, t);
        snprintf(p, sizeof p, "anim-group.modeBox.modeRow%d.mpCntG%d", k, k);
        w_alpha(ui_w(p), g_mdpk.have && (k < MODE_N ? g_mdpk.q[k] : g_mdpk.qa) > 0 ? 1.0f : 0.5f);
        snprintf(p, sizeof p, "anim-group.modeBox.modeRow%d", k);
        w_alpha(ui_w(p), mk_disabled(k) ? 0.4f : 1.0f);
    }
}
// (A: FINDING MATCH with a stale lobby, never queued): winmm's FIND MATCH (FUN_180057110) does NOTHING while the session state
// [0x180167968] is 3 (searching) or 4 - it only appends the 0x01 in state 1/2 and opens a new socket in 0/5 (re/mm-boot.md). A's session had been
// left in state 3 with the searching flag 0 since tick 6184 (the aborted re-adopted match, 'menu link: ... 2 -> 3 ... searching flag 0'), so
// the box's search page showed the spinner and the old lobby while no 0x01 ever went out (daemon: no MATCHMAKE / ANNOUNCE for Alpha; Esc on the
// page = FUN_180057800 reset it, the second try worked). We are on the main menu here (the feature returns early otherwise), so a state 3 with
// no searching flag is a leftover: leave it the way the page's own cancel does (FUN_180057800: 0x02, close, state 0) before the page is pushed.
static void mk_search(void) {                      // on to the search page (winmm's tick starts the request)
    volatile int *ss = (volatile int *)VMA(0x180167968);
    if (*ss == 3 && !*(volatile uint8_t *)VMA(0x180189bb3) && match_substate() != 6) {
        xlog("modepick: stale session state 3 (searching flag 0) on the main menu - leaving it before the search (FUN_180057800)");
        ((void (*)(void))VMA(0x180057800))();
    }
    push_page("to1/find-match-menu");
}
// the mode of the match we are in / about to play: the server's answer once the match is live, else the mode the daemon filed us under when we picked (MODEQ)
static int g_mdpk_queued = -1;      // mode of the last search this player started from the box (-1 = none)
static const char *mf_mode_label(void) {
    static char b[24];
    const char *l = "SUPPLY RAID";
    int quick_pending = 0;
    // (still SUPPLY RAID on the loading screen after picking Interrogation): g_int.ok is already set by the menu-time
    // poll ("on=0", no match yet), so a server "no" before the match is live won the label; only a server "yes" is taken as is,
    // otherwise the mode this player picked in the box, and the server's "no" only when there is no pick
    // (sometimes it said supply raid when loading into interrogation, QUICK MATCH / join in progress): the daemon names the match's mode from the
    // assignment on (mm=), that comes first; a QUICK MATCH whose mode is not known yet shows no mode instead of the default
    if (g_mdpk_mm >= 0 && g_mdpk_mm < MODE_N) l = MODE_TAB[g_mdpk_mm].label;
    else if (g_int.ok && r13_int_mode()) l = "INTERROGATION";
    else if (g_mdpk_queued >= MODE_N && !(g_int.ok && match_substate() == 6)) quick_pending = 1;
    else if (g_mdpk_queued >= 0 && g_mdpk_queued < MODE_N) l = MODE_TAB[g_mdpk_queued].label;   // the mode this player queued for
    // (QUICK MATCH = no pick of its own: the server's yes above names Interrogation, any other match is the default mode)
    else if (g_mdpk.have && g_mdpk.mode >= 0 && g_mdpk.mode < MODE_N) l = MODE_TAB[g_mdpk.mode].label;
    if (quick_pending) l = "";
    size_t k = 0;
    for (; l[k] && k < sizeof b - 1; k++) b[k] = (char)(l[k] >= 'a' && l[k] <= 'z' ? l[k] - 32 : l[k]);
    b[k] = 0;
    return b;
}
static void feature_modepick(void) {
    static uint64_t P_MAIN;
    if (!P_MAIN) P_MAIN = page_id("main-menu");
    if (g_mkq_have) {                                   // a reply (or a failure) came back
        LONG h = g_mkq_have;
        if (h == 1) {
            mkq_parse(g_mkq_rep);
            if (g_mdpk.chosen && g_mdpk.sent) g_mdpk.chosen = 2;           // the ack of our pick
        }
        InterlockedExchange(&g_mkq_have, 0);
    }
    uint64_t now = GetTickCount64(), top = top_page();
    {   // the match's own mode (mm=): asked until known while a search / a match is running; forgotten once the main menu is back with no match
        static uint64_t mm_at;
        int ms = match_substate();
        if (top == P_MAIN && ms == 0) g_mdpk_mm = -1;
        else if (g_mdpk_mm < 0 && (g_mdpk_queued >= 0 || ms >= 4) && !g_mdpk.open && now >= mm_at && mkq_ask(0, 0)) mm_at = now + 1000;
    }
    // no timers: the box lives exactly while the main menu is the top page and the player has not picked / backed out. Leaving the page (another page on
    // top, a match) hides it at once; ui_visible resolves against the top page, so when that cannot reach the box (a page covers it) `shown` stays set and
    // the hide is repeated the moment the main menu is on top again (the old state kept it visible until FIND MATCH was pressed twice).
    if (match_substate() == 6 || top != P_MAIN) {
        if (g_mdpk.open) xlog("modepick: box closed (%s)", match_substate() == 6 ? "match" : "another page on top");
        g_mdpk.open = 0; g_mdpk.chosen = g_mdpk.sent = 0;
        if (g_mdpk.shown || g_mdpk.fade_dir) mk_show(0, 0);             // at once, no fade: the page is leaving
        return;
    }
    uint64_t box = ui_w(MK_BOX);
    if (!box) return;                                   // (the page's widgets are not built yet)
    if (box != g_mdpk.last_box) {                       // a fresh page instance: closed, the edges seeded as held (no stale press)
        g_mdpk.last_box = box; g_mdpk.open = 0; g_mdpk.chosen = 0;
        g_mdpk.h_sel = g_mdpk.h_back = g_mdpk.h_l = g_mdpk.h_u = g_mdpk.h_d = 1;
        mk_show(0, 0);
    }
    mk_fade_tick(now);
    int sel = menu_edge(0x6695c5b7921bb5ddULL /* menu-select */, &g_mdpk.h_sel);
    int back = menu_edge(fnv64("menu-back"), &g_mdpk.h_back), left = menu_edge(fnv64("menu-left"), &g_mdpk.h_l);
    int up = menu_edge(fnv64("menu-up"), &g_mdpk.h_u), down = menu_edge(fnv64("menu-down"), &g_mdpk.h_d);
    int click = g_click_edge;
    if (!g_mdpk.open) {
        if (g_mdpk.shown && !g_mdpk.fade_dir) mk_show(0, 0);   // (stale visible box from a page change: never left up while closed)
        int fm_foc = mk_focused(MK_FM), fm_hov = ui_mouse_over(MK_FM, 1);
        if (!((sel && fm_foc && mk_sel_for(MK_FM)) || (click && fm_hov))) return;
        if (g_steam_only && !steam_connected()) return;  // FIND MATCH is disabled while Steam is down (feature_steam_status_text)
        if (fr_party_member() && !g_test_autofind) {
            // (the ready up system needed to be more intuitive): a member's FIND MATCH row is READY UP / UNREADY and nothing else - no search
            // page (it used to open one the daemon never queued: a fake search for minutes, and a second press flipped the player back to UNREADY). While the
            // leader searches, READY UP takes the player into that search by itself (fr_party_tick's follow-the-leader push).
            ui_sfx("sfx-select"); fr_member_ready_press();
            return;
        }
        if (mk_off() || g_test_autofind) {
            ui_sfx("sfx-select"); mk_search();
            xlog("modepick: FIND MATCH -> search page directly (%s)", mk_off() ? "off" : "autofind");
            return;
        }
        g_mdpk.open = 1; g_mdpk.open_frame = g_frame; g_mdpk.dirty = 1; g_mdpk.chosen = g_mdpk.sent = 0; g_mdpk.poll_at = 0; g_mdpk.hov = -1;
        g_mdpk.sel = g_mdpk.mode >= 0 && g_mdpk.mode < MK_N ? g_mdpk.mode : 0;
        mk_fill();
        mk_show(1, 1);
        mk_sel_fade(1);
        ui_sfx("sfx-open");
        xlog("modepick: box opened (row %d)", g_mdpk.sel);
        return;
    }
    // ---- open
    gu_fade_tick(now);
    if (g_frame <= g_mdpk.open_frame + 1) return;        // (the press that opened it)
    if (!mk_focused(MK_FM)) mk_focus(MK_FM);             // the box is modal: up / down / the mouse resting on another row never take the focus off its parent
    if (g_mdpk.chosen) {                                 // a pick: waiting for the server's ack
        if (g_mdpk.chosen == 1 && !g_mdpk.sent && g_mdpk.pick >= MODE_N && !g_mdpk.anyok) {      // protocol check: no "any=1" from the daemon = an old daemon
            xlog("modepick: daemon does not know QUICK MATCH (no any=1) - searching in the default mode %s", MODE_TAB[0].key);
            g_mdpk.pick = 0;
        }
        if (g_mdpk.chosen == 1 && !g_mdpk.sent && mkq_ask(1, (uint8_t)(g_mdpk.pick >= MODE_N ? MK_ANY : g_mdpk.pick))) g_mdpk.sent = 1;
        if (g_mdpk.chosen == 2 || now - g_mdpk.chosen_at > 2500) {
            if (g_mdpk.chosen == 1) xlog("modepick: no ack from the server in 2.5 s - searching anyway");
            xlog("modepick: search page pushed (mode %s)", g_mdpk.pick < MODE_N ? MODE_TAB[g_mdpk.pick].key : "any");
            g_mdpk_mm = -1;
            g_mdpk_queued = g_mdpk.pick;                 // the label of this search's loading screen / vote page / title card
            g_mdpk.chosen = 0;
            mk_close("picked", 0);
            mk_search();
        }
        return;
    }
    if (back || left) { mk_cycle_sfx(now); mk_close(back ? "back" : "left", 1); return; }
    int hv = ui_mouse_row(MK_ROW, MK_N, &g_mdpk.hov);       // hover moves the selection (no sound: only the player's up / down keys and pad moves cycle)
    if (hv >= 0 && !mk_disabled(hv)) g_mdpk.sel = hv;
    if (up) for (int k = g_mdpk.sel - 1; k >= 0; k--) if (!mk_disabled(k)) { g_mdpk.sel = k; mk_cycle_sfx(now); break; }
    if (down) for (int k = g_mdpk.sel + 1; k < MK_N; k++) if (!mk_disabled(k)) { g_mdpk.sel = k; mk_cycle_sfx(now); break; }
    if (mk_disabled(g_mdpk.sel)) for (int k = 0; k < MK_N; k++) if (!mk_disabled(k)) { g_mdpk.sel = k; break; }
    int over = -1;
    if (click) { char p[112]; for (int k = 0; k < MK_N && over < 0; k++) { snprintf(p, sizeof p, MK_ROW, k, k, k); if (ui_mouse_over(p, 1)) over = k; } }
    if (click && over < 0) { mk_close("click outside", 0); return; }
    if (sel && ui_select_is_mouse()) sel = 0;                // (a click picks through `over` at its press; its select edge - press or release - must not pick the highlighted row)
    if ((sel || over >= 0) && over >= 0 && mk_disabled(over)) { ui_sfx("sfx-menu-error"); sel = 0; over = -1; }
    if (sel || over >= 0) {
        if (over >= 0) g_mdpk.sel = over;
        g_mdpk.chosen = 1; g_mdpk.sent = 0; g_mdpk.chosen_at = now; g_mdpk.pick = g_mdpk.sel;
        // feedback within 100 ms - the sound, the picked row lit and the box on its way out in this frame; the search page follows on the server's ack
        ui_sfx("sfx-select");
        mk_sel_fade(1); gu_fade_tick(now);
        mk_show(0, 1);
        xlog("modepick: picked %s", g_mdpk.sel < MODE_N ? MODE_TAB[g_mdpk.sel].label : "QUICK MATCH");
        return;
    }
    mk_sel_fade(1);
    if (now >= g_mdpk.poll_at && mkq_ask(0, 0)) g_mdpk.poll_at = now + 1500;
    if (g_mdpk.dirty || now - g_mdpk.fill_at > 500) { g_mdpk.dirty = 0; g_mdpk.fill_at = now; mk_fill(); }
}
