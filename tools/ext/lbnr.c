// lbnr.c - to1/leaderboard (MULTIPLAYER > LEADERBOARDS) in the No Return frame (tools/features/leaderboard_nr_widgets.py).
// The table itself is filled by winmm (daemon op 0x14 -> anim-group.table.row<r>_onlineid / _wins / _losses / _ratio / _elo): this file only
//   - places the frame once per page instance: breadcrumb TWELVE WEEKS | LEADERBOARDS, one boxed BACK prompt (a click on it = back, like the key);
//   - shows lbMe<r> (fill, accent bar, YOU chip) over the row whose name is ours (t2r-name.txt; winmm's name writes are noted in settext_hook:
//     lbnr_note), and hides nothing else.
// Included after mfnr.c (mfnr_is_me); feature_lbnr runs once a frame from the PF list.

#define LBNR_ROWS 10
static uint64_t g_lb_w[LBNR_ROWS];               // row<r>_onlineid widget handles (resolved while the page is up)
static char g_lb_n[LBNR_ROWS][48];                // the last text winmm wrote into each
static volatile int g_lb_up;

static void lbnr_note(uint64_t w, const char *t) {         // settext_hook: every text write
    if (!g_lb_up || !w) return;
    for (int i = 0; i < LBNR_ROWS; i++)
        if (g_lb_w[i] == w) { snprintf(g_lb_n[i], sizeof g_lb_n[i], "%s", t ? t : ""); return; }
}

static void feature_lbnr(void) {
    static uint64_t P_LB, res_at, own_at;
    static unsigned gen = ~0u;
    static int placed, last_pad = -1;
    if (!P_LB) P_LB = page_id("leaderboard");
    uint64_t top = top_page();
    if (top != P_LB) {
        if (g_lb_up) { g_lb_up = 0; placed = 0; last_pad = -1; memset(g_lb_w, 0, sizeof g_lb_w); memset(g_lb_n, 0, sizeof g_lb_n); }
        return;
    }
    uint64_t now = GetTickCount64();
    if (!g_lb_up || gen != g_ui_gen || now - res_at > 3000) {   // (re)resolve the name widgets: a rebuilt page instance has new handles
        g_settext_in = 1;
        for (int r = 0; r < LBNR_ROWS; r++) {
            char p[64];
            snprintf(p, sizeof p, "anim-group.table.row%d_onlineid", r);
            uint64_t w = ui_w(p);
            if (w != g_lb_w[r]) { g_lb_w[r] = w; g_lb_n[r][0] = 0; }
        }
        g_settext_in = 0;
        if (!g_lb_up || gen != g_ui_gen) { placed = 0; last_pad = -1; }
        g_lb_up = 1; gen = g_ui_gen; res_at = now;
    }
    if (!placed) { placed = 1; nr_header("TWELVE WEEKS", "LEADERBOARDS"); }
    if (last_pad != g_pad_mode) {
        last_pad = g_pad_mode;
        nr_prompt_t it[1] = {{"menu:back", "menu:back", "BACK", 1}};
        nr_prompts(it, 1);
    }
    if (g_click_edge && nr_prompt_hover() == 0) { ui_sfx("sfx-menu-back"); pop_page(); return; }
    if (now - own_at >= 250) {                               // our own row
        own_at = now;
        for (int r = 0; r < LBNR_ROWS; r++) {
            char p[64];
            int me = g_lb_n[r][0] && mfnr_is_me(g_lb_n[r]);
            snprintf(p, sizeof p, "anim-group.table.lbMe%d", r);
            ui_visible(p, me);
            if (me) { char c[80]; snprintf(c, sizeof c, "anim-group.table.lbMe%d.lbMe%dYo", r, r); nr_chip(c, loc_tr("YOU"), 1700.0f, 0.0f, 25.5f); }      // (the chip box is built at its template width: sized to the text here)
        }
    }
}
