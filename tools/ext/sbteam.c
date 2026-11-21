// ---------------------------------------------------------------- the scoreboards (ESC page + scoreboard page) in the No Return frame, our team on top
// In game, in the ESC menu the own team is always on the blue side above, with the faction corresponding to the own faction, and the enemy in the red team.
// winmm fills the two fixed blocks of to1/pause-menu and to1/scoreboard (names scoreboard.team0_* on top, team1_* below) by the roster team index, so a player of team 1
// saw his own team in the lower block. The two blocks have the same layout 520 canvas units apart (tools/features/pause_restyle_widgets.py PNR_D), so when our team
// is team 1 the two blocks swap places (gui2-rxfm-set-pivot-as on every member, w_pivot): the block of our team is the upper one, always. The colour follows the PLACE
// (sbBlue / sbRed = thin edge bars, static), the block's texts are white / grey. Which state the page is in is read from the two team name widgets (team0 above team1
// = not swapped), so the move is relative and repeatable and works on any page of this layout (the pause page and the scoreboard page differ in their y).
// redesign (the frame of PLAYER STATS, widgets: pause_restyle_widgets.add_pause_nr):
//   - breadcrumb <MODE> | MENU / SCOREBOARD (nr_header), once per page instance;
//   - per block: the "US" / "THE ENEMY" tag after the faction name (winmm's team<t>_name), the section rule from the tag to SBT_RULE_END, the team totals
//     team<t>_tot_<col> (the sum of the rows' numbers, noted in settext_hook: sbt_note) in the grey section row;
//   - per row: the own row (name = ours, mfnr_is_me) = accent edge bar team<t>_row<r>_me + the YOU tag + a lighter tile; a name wider than SBT_NAME_BOX is shrunk about its
//     left end; the rank badge is rankbadge.c's;
//   - the lives (the score banner copy's allyLives / enemyLives, noted too): sbLvA beside the upper block, sbLvE beside the lower one (ally = our team = the upper block).
// Log 'sbteam: ...'. Off: t2r-no-sbteam.txt (no swap; the frame's own parts still fill).
#define SBT_X0 148.0f
#define SBT_PT 39.0f                      // nr_style.pt(26): the names / numbers
#define SBT_TAG_PT 27.0f                  // nr_style.pt(18): the US / THE ENEMY tag
#define SBT_NAME_X 282.0f                 // pause_restyle_widgets.pnr_name_x(): PNR_BADGE_X + rank_badge_widgets.reserved(PNR_PT, 64)
#define SBT_NAME_BOX 900.0f               // PNR_NAME_BOX
#define SBT_RULE_END 1400.0f              // PNR_RULE_END
static int sbt_off(void) {
    static int off = -1; static uint64_t chk;
    return ov_off("t2r-no-sbteam.txt", &off, &chk);
}
static int sbt_pos(uint64_t w, float *x, float *y) {
    uint64_t g[1] = {w};
    uint64_t xf = dc_call(SID_GUI2_GET_WIDGET_TRANSFORM, 1, g);
    if (!xf || xf == ~0ULL || IsBadReadPtr((void *)(uintptr_t)xf, 0x28)) return 0;
    const float *p = (const float *)(uintptr_t)(xf + 0x20);
    *x = p[0]; *y = p[1];
    return 1;
}
// ---- what winmm writes into the rows (settext_hook -> sbt_note): name, parts, downs, executions, deaths, revives of the 2 x 4 rows, the 2 team names, the banner copy's lives
static const char *const SBT_NUMS[5] = {"parts", "downs", "executions", "deaths", "revives"};
static const char *const SBT_COLS[5] = {"parts", "downs", "executions", "deaths", "revives"};      // tot_<col> (same order as SBT_NUMS)
static uint64_t g_sbw[2][4][6];                                  // [team][row][0 name, 1.. SBT_NUMS]
static char g_sbt[2][4][6][48];
static uint64_t g_sbtn[2]; static char g_sbtname[2][64];
static uint64_t g_sblv[2]; static char g_sblvt[2][16];
static volatile int g_sbn_up; static volatile LONG g_sbn_ver;
static int g_sbn_pause, g_sbn_frame;                              // this page instance: the pause page (pauseTimer) / carries the frame (hdPar)
static void sbt_note(uint64_t w, const char *t) {                 // settext_hook: every text write
    if (!g_sbn_up || !w) return;
    for (int tm = 0; tm < 2; tm++) {
        for (int r = 0; r < 4; r++)
            for (int k = 0; k < 6; k++)
                if (g_sbw[tm][r][k] == w) { snprintf(g_sbt[tm][r][k], sizeof g_sbt[tm][r][k], "%s", t ? t : ""); InterlockedIncrement(&g_sbn_ver); return; }
        if (g_sbtn[tm] == w) { snprintf(g_sbtname[tm], sizeof g_sbtname[tm], "%s", t ? t : ""); InterlockedIncrement(&g_sbn_ver); return; }
        if (g_sblv[tm] == w) { snprintf(g_sblvt[tm], sizeof g_sblvt[tm], "%s", t ? t : ""); InterlockedIncrement(&g_sbn_ver); return; }
    }
}
static void sbt_resolve(void) {                                   // a new page instance: new handles, nothing noted yet
    g_sbn_up = 0;
    memset(g_sbw, 0, sizeof g_sbw); memset(g_sbt, 0, sizeof g_sbt); memset(g_sbtn, 0, sizeof g_sbtn); memset(g_sbtname, 0, sizeof g_sbtname);
    memset(g_sblv, 0, sizeof g_sblv); memset(g_sblvt, 0, sizeof g_sblvt);
    g_settext_in = 1;
    for (int tm = 0; tm < 2; tm++) {
        char p[120];
        for (int r = 0; r < 4; r++) {
            snprintf(p, sizeof p, "anim-group.scoreboard.team%d_row%d_name", tm, r); g_sbw[tm][r][0] = ui_w(p);
            for (int k = 0; k < 5; k++) { snprintf(p, sizeof p, "anim-group.scoreboard.team%d_row%d_%s", tm, r, SBT_NUMS[k]); g_sbw[tm][r][1 + k] = ui_w(p); }
        }
        snprintf(p, sizeof p, "anim-group.scoreboard.team%d_name", tm); g_sbtn[tm] = ui_w(p);
        g_sblv[tm] = ui_w(tm ? "anim-group.scoreBanner.fader.teamPanel.enemyLives" : "anim-group.scoreBanner.fader.teamPanel.allyLives");
    }
    g_sbn_pause = ui_w("anim-group.pauseTimer") != 0;
    g_sbn_frame = ui_w("anim-group.hdPar") != 0;
    g_settext_in = 0;
    g_sbn_up = 1;
}
static void sbt_forget(void) { g_sbn_up = 0; }                    // the page is gone: its next instance starts at the template places
// ---- the block swap
static const char *const SBT_BLK[] = {"name", "tag", "rl", "tot_downs", "tot_executions", "tot_revives", "tot_deaths", "tot_parts"};
static const char *const SBT_ROW[] = {"bg", "name", "parts", "downs", "executions", "deaths", "revives", "ping", "input", "rkIcon", "rkNum", "me", "tag"};
static int sbt_shift(const char *path, float dy) {
    g_settext_in = 1; uint64_t w = ui_w(path); g_settext_in = 0;
    float x, y;
    if (!w || !sbt_pos(w, &x, &y)) return 0;
    w_pivot(w, x, y + dy);
    return 1;
}
static void sbt_swap(int want) {
    float x0, y0, x1, y1;
    if (!g_sbtn[0] || !g_sbtn[1] || !sbt_pos(g_sbtn[0], &x0, &y0) || !sbt_pos(g_sbtn[1], &x1, &y1)) return;
    int cur = y0 > y1 + 1.0f;                                   // team 0's name below team 1's = the blocks are swapped
    float d = fabsf(y1 - y0);
    if (cur == want || d < 50.0f) return;
    int n = 0;
    for (int tm = 0; tm < 2; tm++) {
        float dy = (float)(want - cur) * d * (tm == 0 ? 1.0f : -1.0f);
        char p[120];
        for (unsigned k = 0; k < sizeof SBT_BLK / sizeof *SBT_BLK; k++) { snprintf(p, sizeof p, "anim-group.scoreboard.team%d_%s", tm, SBT_BLK[k]); n += sbt_shift(p, dy); }
        for (int r = 0; r < 4; r++)
            for (unsigned k = 0; k < sizeof SBT_ROW / sizeof *SBT_ROW; k++) { snprintf(p, sizeof p, "anim-group.scoreboard.team%d_row%d_%s", tm, r, SBT_ROW[k]); n += sbt_shift(p, dy); }
    }
    xlog("sbteam: our team is team %d - %s block on top (%d widgets placed)", want, want ? "team 1" : "team 0", n);
}
// ---- the frame's live parts
static int sbt_num(const char *t) { return t && *t ? atoi(t) : 0; }
static void sbt_live(int our, uint64_t now) {
    static LONG last_ver = -1; static uint64_t last_at; static int last_our = -2;
    static int me[2][4]; static char fitn[2][4][48]; static char tnm[2][96]; static int sum[2][5];
    static unsigned gen = ~0u;
    if (gen != g_ui_gen) {                                      // a new page instance: every cache starts over
        gen = g_ui_gen; last_ver = -1; last_our = -2;
        memset(me, 0xff, sizeof me); memset(fitn, 0, sizeof fitn); memset(tnm, 0, sizeof tnm); memset(sum, 0xff, sizeof sum);
    }
    if (last_ver == g_sbn_ver && last_our == our && now - last_at < 1500) return;
    last_ver = g_sbn_ver; last_our = our; last_at = now;
    char p[128], b[96];
    for (int tm = 0; tm < 2; tm++) {
        int any = 0, tot[5] = {0, 0, 0, 0, 0};
        for (int r = 0; r < 4; r++) {
            const char *nm = g_sbt[tm][r][0];
            int mine = nm[0] && mfnr_is_me(nm);
            for (int k = 0; k < 5; k++) { const char *v = g_sbt[tm][r][1 + k]; if (v[0]) { any = 1; tot[k] += sbt_num(v); } }
            if (me[tm][r] != mine) {                            // the own row: accent bar, a lighter tile, the YOU tag
                me[tm][r] = mine; fitn[tm][r][0] = 0;
                snprintf(p, sizeof p, "anim-group.scoreboard.team%d_row%d_me", tm, r); ui_visible(p, mine);
                snprintf(p, sizeof p, "anim-group.scoreboard.team%d_row%d_bg", tm, r);
                uint64_t bg = ui_w(p); if (bg) w_alpha(bg, mine ? 215.0f / 255.0f : 175.0f / 255.0f);
                snprintf(p, sizeof p, "anim-group.scoreboard.team%d_row%d_tag", tm, r);
                snprintf(b, sizeof b, "<font color=%c#D9D86A%c>%s</font>", 34, 34, loc_tr("YOU"));
                ui_text(p, mine ? b : ""); ui_visible(p, mine);
            }
            if (nm[0] && strcmp(fitn[tm][r], nm)) {             // a name wider than its room is shrunk about its left end; the YOU tag follows its end
                snprintf(fitn[tm][r], sizeof fitn[tm][r], "%s", nm);
                float e = nr_tw(nm, SBT_PT), s = e > SBT_NAME_BOX ? SBT_NAME_BOX / e : 1.0f;
                if (s < 0.6f) s = 0.6f;
                snprintf(p, sizeof p, "anim-group.scoreboard.team%d_row%d_name", tm, r);
                uint64_t w = ui_w(p); if (w) w_scale(w, s, s);
                if (mine) {
                    snprintf(p, sizeof p, "anim-group.scoreboard.team%d_row%d_tag", tm, r);
                    uint64_t tg = ui_w(p); float px, py;
                    if (tg && w_pivot_get(tg, &px, &py)) w_pivot(tg, SBT_NAME_X + e * s + 28.0f, py);
                }
            }
        }
        for (int k = 0; k < 5; k++) {                           // the team totals (empty until a number has been written)
            int v = any ? tot[k] : -2;
            if (sum[tm][k] == v) continue;
            sum[tm][k] = v;
            snprintf(p, sizeof p, "anim-group.scoreboard.team%d_tot_%s", tm, SBT_COLS[k]);
            snprintf(b, sizeof b, "%d", v);
            ui_text(p, v >= 0 ? b : "");
        }
        {                                                       // US / THE ENEMY after the faction name, the rule from there to SBT_RULE_END
            const char *tn = g_sbtname[tm];
            const char *tag = tm == our ? "US" : "THE ENEMY";
            snprintf(b, sizeof b, "%s|%s", tn, tag);
            if (strcmp(tnm[tm], b)) {
                snprintf(tnm[tm], sizeof tnm[tm], "%s", b);
                snprintf(p, sizeof p, "anim-group.scoreboard.team%d_tag", tm); ui_text(p, tag);
                uint64_t w = ui_w(p); float px, py;
                float xt = SBT_X0 + (tn[0] ? nr_tw(tn, SBT_PT) : 0.0f) + 36.0f;
                if (w && w_pivot_get(w, &px, &py)) {
                    w_pivot(w, xt, py);
                    snprintf(p, sizeof p, "anim-group.scoreboard.team%d_rl", tm);
                    float xa = xt + nr_tw(tag, SBT_TAG_PT) + 40.0f;
                    nr_rule(p, xa, py, SBT_RULE_END - xa);
                }
            }
        }
    }
    {                                                           // the lives: sbLvA beside the upper block (ally = ours), sbLvE beside the lower one
        int have = g_sblvt[0][0] || g_sblvt[1][0];
        ui_visible("anim-group.scoreboard.sbLvAl", have); ui_visible("anim-group.scoreboard.sbLvEl", have);
        ui_visible("anim-group.scoreboard.sbLvA", have); ui_visible("anim-group.scoreboard.sbLvE", have);
        if (have) { ui_text("anim-group.scoreboard.sbLvA", g_sblvt[0]); ui_text("anim-group.scoreboard.sbLvE", g_sblvt[1]); }
    }
}
static void sbt_tick(uint64_t now, uint64_t probe) {
    static uint64_t res_probe; static unsigned res_gen = ~0u; static int hdr_done;
    if (probe != res_probe || res_gen != g_ui_gen || !g_sbn_up) {
        sbt_resolve(); res_probe = probe; res_gen = g_ui_gen; hdr_done = 0;
    }
    int swap = 0, known = 0;
    if (!sbt_off() && match_substate() >= 3) {
        uint32_t me = *(uint32_t *)VMA(0x180138090);
        uint8_t *lo = lobby_obj();
        if (me < T2R_MAX_PEERS && lo && !IsBadReadPtr(lo, 0x1b8) && lo[0x1a] > 0 && lo[0x1a] <= 8) {
            for (int i = 0; i < lo[0x1a]; i++) if (lo[0x1d + i * 0x32] == me) { known = 1; swap = lo[0x1d + i * 0x32 + 0x31] & 1; }
        }
    }
    if (!known) swap = 0;
    sbt_swap(swap);
    if (g_sbn_frame && !hdr_done) {                             // the breadcrumb: the match's mode | MENU or SCOREBOARD
        hdr_done = 1;
        const char *md = mf_mode_label();
        nr_header(md && md[0] ? md : "TWELVE WEEKS", g_sbn_pause ? "MENU" : "SCOREBOARD");
    }
    if (g_sbn_frame) sbt_live(swap, now);
}
