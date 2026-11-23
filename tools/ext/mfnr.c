// mfnr.c - the map vote (to1/matchflow, stage 1) in the No Return frame (re/ui-redesign-1117/PROPOSAL.md; widgets: tools/features/matchflow_widgets.py,
// frame: nr_style.py / nrui.c). Included after nrui.c; t2r-ext.c's feature_matchflow calls these:
//   mfnr_stage(stage)               a stage came up: the frame (backdrop dim, breadcrumb FOUND MATCH | MAP VOTE, week block, prompts) is shown for the vote
//                                   only - the booster stage keeps its own backdrop (bgDark / bgLight)
//   mfnr_vote_fill(m, focus)        map tiles (N | M votes + thin bar, YOUR VOTE chip, focus = thin white frame), the roster rows, the section counts
//   mfnr_clan_fill()                week block (top right), SURVIVORS n, HEALTHY / HUNGRY / SICK as N | total bars, NEEDED PER DAY
//   mfnr_timer(s)                   the countdown number (double buffered twin) + a thin bar of the time left
//   mfnr_prompts_tick(&last, m)     boxed prompts SWITCH / VOTE (VOTE at 40 % once the vote is closed), pad version through g_pad_mode
//   mfnr_prompt_hit()               the mouse is over the VOTE prompt (the click gate lets the select through)
// Colours: white / grey text, accent #D9D86A only for our own row and the vote we cast (YOUR VOTE).
// Widget space 3840 x 2160; the numbers below = matchflow_widgets.py LX0 / LX1 / RX0 / RX1 / VY / TY / GCW ...

#define MFNR_LX0 148.0f
#define MFNR_LX1 2740.0f
#define MFNR_RX0 2940.0f
#define MFNR_RX1 3700.0f
#define MFNR_VY 420.0f                       // the vote's header row and the clan block's header row
#define MFNR_TW 840.0f                       // tile width = (LX1 - LX0 - 2 * 36) / 3
#define MFNR_TIH 472.0f                      // tile art height (16:9)
#define MFNR_TSTRIP 130.0f
#define MFNR_GW 440.0f                       // grid cell width
#define MFNR_GIH 247.0f
#define MFNR_GSTRIP 84.0f
#define MFNR_RMAPW 440.0f                    // roster row: the voted map's name box at the right end (matchflow_widgets.py _roster map_w), 2 x 4 roster
#define MFNR_GRMAPW 250.0f                   //   ... the grid mode's one-column roster
#define MFNR_RMAPPT 30.0f
#define MFNR_RNAMEW 581.0f                   // roster row: the name's box (matchflow_widgets.py _roster: check x - 20 - rank x - badge), 2 x 4 roster
#define MFNR_GRNAMEW 271.0f                  //   ... grid mode (long names shrink instead of running into the map name)
#define MFNR_RNAMEPT 36.0f
#define MFNR_RROWW 1260.0f                   // roster row width (matchflow_widgets.py RCOLW), 2 x 4 roster
#define MFNR_GRROWW 760.0f                   //   ... grid mode (RX1 - RX0)

static int g_mfnr_tot;                       // the longest countdown seen this vote (the bar's full length)
static int g_mfnr_can;                       // the VOTE prompt is live (a vote is open)

static void mfnr_frame_vis(int on) {         // the nr_style frame parts that sit under anim-group
    ui_visible("anim-group.bgDim", on);
    ui_visible("anim-group.bgVig", on);
    ui_visible("anim-group.hdPar", on); ui_visible("anim-group.hdDiv", on); ui_visible("anim-group.hdPage", on); ui_visible("anim-group.hdRule", on);
    nr_week_visible(on);
    ui_visible("anim-group.pbar", on);
}
static void mfnr_stage(int stage) {
    int on = stage == 1;
    mfnr_frame_vis(on);
    ui_visible("anim-group.bgDark", stage >= 2);
    ui_visible("anim-group.bgLight", stage >= 2);
    if (on) { g_mfnr_tot = 0; nr_header("FOUND MATCH", "MAP VOTE"); }
}

static void mfnr_timer(int s) {
    char b[24];
    if (s < 0) s = 0;
    if (s > g_mfnr_tot) g_mfnr_tot = s;
    snprintf(b, sizeof b, "00:%02d", s);
    ui_text_db("anim-group.vote.voteTimer", b);
    nr_bar("anim-group.vote.voteHead.vtTmF", MFNR_LX0, MFNR_LX1, MFNR_VY + 42.0f + 3.0f, g_mfnr_tot > 0 ? (float)s / (float)g_mfnr_tot : 0.0f);
}

static void mfnr_prompts_tick(int *last, const mf_t *m) {
    int grid = m->ok && m->n > 3, can = m->ok && m->st == 1;
    int key = (g_pad_mode ? 1 : 0) | (grid ? 2 : 0) | (can ? 4 : 0);
    if (*last == key) return;
    *last = key;
    g_mfnr_can = can;
    nr_prompt_t it[2] = {{grid ? "W A S D" : "A / D", "menu:prev+menu:next", "SWITCH", 1}, {"menu:select", "menu:select", "VOTE", can}};
    nr_prompts(it, 2);
}
static int mfnr_prompt_hit(void) { return g_mfnr_can && nr_prompt_hover() == 1; }

// one map cell. base "anim-group.vote.voteTiles" / "...voteGrid", pre "tile" / "g": widgets <pre>k group, <pre>kImg / Shade / Fo / Name / Ct / VbF / Yv
static void mfnr_cell(const char *base, const char *pre, int k, int mi, int votes, int pc, int on, int mine, int grid) {
    char p[176], b[96];
    float w = grid ? MFNR_GW : MFNR_TW, ih = grid ? MFNR_GIH : MFNR_TIH, strip = grid ? MFNR_GSTRIP : MFNR_TSTRIP, pad = grid ? 16.0f : 24.0f;
    float pt = grid ? 27.0f : 39.0f, ny_ct_pt = grid ? 24.0f : 33.0f;
    (void)strip; (void)ny_ct_pt;
    snprintf(p, sizeof p, "%s.%s%d.%s%dName", base, pre, k, pre, k);
    nr_fit(p, mf_map_name(mi), w - 2.0f * pad - 150.0f, pt);
    snprintf(p, sizeof p, "%s.%s%d.%s%dImg", base, pre, k, pre, k);
    snprintf(b, sizeof b, "streaming/menus/to1/map-pvp-%s.png", mf_map_img(mi));
    ui_image(p, b);
    snprintf(p, sizeof p, "%s.%s%d.%s%dFo", base, pre, k, pre, k); ui_visible(p, on);
    snprintf(p, sizeof p, "%s.%s%d.%s%dShade", base, pre, k, pre, k); ui_visible(p, !on);
    snprintf(p, sizeof p, "%s.%s%d.%s%dYv", base, pre, k, pre, k); ui_visible(p, mine);
    if (mine) { size_t n = strlen(p); snprintf(p + n, sizeof p - n, ".%s%dYv", pre, k); nr_chip(p, loc_tr("YOUR VOTE"), 0.0f, 0.0f, grid ? 19.5f : 27.0f); }      // (the chip box is built at its template width: sized to the text here)
    {   // Part I map (img "p1-..."): the white PART I box top right of the art (like the OG badge on OG customize items)
        int p1 = strncmp(mf_map_img(mi), "p1-", 3) == 0;
        snprintf(p, sizeof p, "%s.%s%d.%s%dP1", base, pre, k, pre, k); ui_visible(p, p1);
        if (p1) { size_t n = strlen(p); snprintf(p + n, sizeof p - n, ".%s%dP1", pre, k); nr_chip(p, "PART I", 0.0f, w - (grid ? 10.0f : 16.0f), grid ? 19.5f : 27.0f); }      // right-aligned at the art's edge
    }
    if (pc < votes) pc = votes;
    if (pc < 1) pc = 1;
    snprintf(b, sizeof b, votes ? "%d | %d" : "<font color=\"#8C8C8C\">%d | %d</font>", votes, pc);
    snprintf(p, sizeof p, "%s.%s%d.%s%dCt", base, pre, k, pre, k); ui_text(p, b);
    snprintf(p, sizeof p, "%s.%s%d.%s%dVbF", base, pre, k, pre, k);
    nr_bar(p, pad, w - pad, ih + strip - (grid ? 24.0f : 34.0f) + (grid ? 2.5f : 3.0f), (float)votes / (float)pc);
}

// our own name (t2r-name.txt), refreshed every 3 s: the roster row of the player at this screen is shown in the accent
static int mfnr_is_me(const char *nm) {
    static char ln[16]; static uint64_t at;
    uint64_t now = GetTickCount64();
    if (!at || now - at > 3000) { char tg[6]; at = now; ne_local_load(ln, tg); }
    if (!ln[0] || !nm || !nm[0]) return 0;
    size_t a = strlen(nm), b = strlen(ln);
    if (a == b) return !_stricmp(nm, ln);
    return a > b + 1 && (nm[a - b - 1] == ' ' || nm[a - b - 1] == ']') && !_stricmp(nm + a - b, ln);     // "[TAG] name"
}

static void mfnr_roster(const mf_t *m, int have, int grid) {
    char p[176], b[112];
    int ord[8], tts[8], no = 0;                           // our own team on top, the enemy below; the server's order inside each group
    for (int i = 0; i < 8 && i < m->pc; i++) tts[i] = mf_team_tab(m->p[i]);
    for (int pass = 0; pass < 3; pass++)
        for (int i = 0; i < 8 && i < m->pc; i++) if ((tts[i] == 1 ? 0 : tts[i] == 0 ? 1 : 2) == pass) ord[no++] = i;
    const char *RG = grid ? "anim-group.vote.voteGrid.voteGridRoster" : "anim-group.vote.voteRoster", *RP = grid ? "gros" : "ros";
    int nv = 0;
    for (int i = 0; i < 8 && i < m->pc; i++) nv += m->pv[i] ? 1 : 0;
    for (int r = 0; r < 8; r++) {
        snprintf(p, sizeof p, "%s.%s%d", RG, RP, r);
        ui_visible(p, have && r < m->pc);
        if (!have || r >= m->pc) continue;
        int s = ord[r];                                   // the source player shown in row r
        snprintf(p, sizeof p, "%s.%s%d.%s%dName", RG, RP, r, RP, r);
        if (mfnr_is_me(m->p[s])) snprintf(b, sizeof b, "<font color=\"#D9D86A\">%s</font>", m->p[s]);
        else if (tts[s] == 2) snprintf(b, sizeof b, "<font color=\"#8C8C8C\">%s</font>", m->p[s]);
        else snprintf(b, sizeof b, "%s", m->p[s]);
        nr_fit(p, b, grid ? MFNR_GRNAMEW : MFNR_RNAMEW, MFNR_RNAMEPT);
        { char ri[112], rn[112]; snprintf(ri, sizeof ri, "%s.%s%d.%s%dRk", RG, RP, r, RP, r); snprintf(rn, sizeof rn, "%s.%s%d.%s%dRn", RG, RP, r, RP, r); rank_ui(ri, rn, m->pk[s], m->pw[s]); }      // rank badge (rank13.h; the vote state carries it)
        snprintf(p, sizeof p, "%s.%s%d.%s%dCk", RG, RP, r, RP, r);
        ui_visible(p, m->pv[s]);
        {   // the player name at the start, the check + the name of the map this player voted for at the row's end
            int me = mfnr_is_me(m->p[s]), o = me && m->my >= 0 ? m->my : m->po[s];      // (our own row: the vote we just sent counts at once)
            const char *mn = o >= 0 && o < m->n && (m->pv[s] || me) ? mf_map_name(m->m[o]) : "";
            snprintf(p, sizeof p, "%s.%s%d.%s%dMap", RG, RP, r, RP, r);
            if (me && mn[0]) snprintf(b, sizeof b, "<font color=\"#D9D86A\">%s</font>", mn);
            else snprintf(b, sizeof b, "%s", mn);
            float box = grid ? MFNR_GRMAPW : MFNR_RMAPW;
            nr_fit(p, b, box, MFNR_RMAPPT);
            snprintf(p, sizeof p, "%s.%s%d.%s%dCk", RG, RP, r, RP, r);
            if (me && m->my >= 0) ui_visible(p, 1);
            if (mn[0]) {                                  // the map name is right aligned at the row's end: the check goes just before its text
                float e = nr_est(b, MFNR_RMAPPT), sc = e > box && e > 0.0f ? box / e : 1.0f;
                if (sc < 0.6f) sc = 0.6f;
                w_pivot(ui_w(p), (grid ? MFNR_GRROWW : MFNR_RROWW) - 16.0f - nr_tw(b, MFNR_RMAPPT) * sc - 16.0f - 38.0f, 22.0f);   // (matchflow_widgets.ck_x; y = row 78 / 2 - 17)
            }
        }
        snprintf(p, sizeof p, "%s.%s%d.%s%dTabB", RG, RP, r, RP, r); ui_visible(p, tts[s] == 1);
        snprintf(p, sizeof p, "%s.%s%d.%s%dTabR", RG, RP, r, RP, r); ui_visible(p, tts[s] == 2);
    }
    snprintf(b, sizeof b, "%d | %d VOTED", nv, m->pc);
    if (grid) nr_section("anim-group.vote.voteGrid.voteGridRoster.vtGp", MFNR_RX0, MFNR_RX1, 1040.0f, "PLAYERS", b, 36.0f);
    else nr_section("anim-group.vote.voteRoster.vtPl", MFNR_LX0, MFNR_LX1, 1210.0f, "PLAYERS", b, 36.0f);
}

static void mfnr_vote_fill(const mf_t *m0, int focus) {
    mf_t ml = *m0;
    const mf_t *m = &ml;
    { int lv = g_mf_lv;                                   // the vote we sent counts at once (no checkmark waiting for a reply that may be lost)
      if (lv >= 0 && lv < ml.n && ml.st == 1 && ml.my != lv && ml.m[lv] == g_mf_lvmap) {
          if (ml.my >= 0 && ml.my < ml.n && ml.v[ml.my] > 0) ml.v[ml.my]--;
          if (ml.v[lv] < 8) ml.v[lv]++;
          ml.my = lv;
      } }
    int have = m->ok && m->st >= 1 && m->n > 0, grid = have && m->n > 3;
    ui_visible("anim-group.vote.voteWait", !have);
    ui_visible("anim-group.vote.voteHead", have);
    ui_visible("anim-group.vote.voteTiles", have && !grid);
    ui_visible("anim-group.vote.voteGrid", grid);
    ui_visible("anim-group.vote.voteRoster", have && !grid);
    db_visible(ui_w("anim-group.vote.voteTimer"), ui_w("anim-group.vote.voteTimerB"), have);
    if (have) nr_section("anim-group.vote.voteHead.vtMap", MFNR_LX0, MFNR_LX1 - 250.0f, MFNR_VY, "VOTE FOR A MAP", "", 36.0f);
    int pc = m->pc;
    if (grid) {
        for (int k = 0; k < MF_GRID; k++) {
            char p[96];
            snprintf(p, sizeof p, "anim-group.vote.voteGrid.g%d", k);
            ui_visible(p, k < m->n);
            if (k >= m->n) continue;
            int on = m->st == 2 ? m->m[k] == m->w : k == focus;
            mfnr_cell("anim-group.vote.voteGrid", "g", k, m->m[k], m->v[k], pc, on, m->my == k, 1);
        }
    } else {
        for (int k = 0; k < 3 && have; k++) {
            char p[96];
            snprintf(p, sizeof p, "anim-group.vote.voteTiles.tile%d", k);
            ui_visible(p, k < m->n);
            if (k >= m->n) continue;
            int on = m->st == 2 ? m->m[k] == m->w : k == focus;
            mfnr_cell("anim-group.vote.voteTiles", "tile", k, m->m[k], m->v[k], pc, on, m->my == k, 0);
        }
    }
    mfnr_roster(m, have, grid);
}

static void mfnr_clan_fill(void) {                  // week block top right + the clan block of the right column
    clan_t c = clan_get();
    char b[64];
    if (!c.ok) return;
    int d = c.day < 84 ? c.day : 83;
    nr_week(d / 7 + 1, d % 7 + 1, d);
    ui_text("anim-group.vote.voteSub", mf_mode_label());
    int tot = c.h + c.hu + c.s, v3[3] = {c.h, c.hu, c.s};
    static const char K3[3] = {'H', 'U', 'S'};
    snprintf(b, sizeof b, "%d", tot);
    nr_section("anim-group.vote.vtSv", MFNR_RX0, MFNR_RX1, MFNR_VY, "SURVIVORS", b, 36.0f);
    for (int k = 0; k < 3; k++) {
        char p[64];
        snprintf(p, sizeof p, "anim-group.vote.vs%cN", K3[k]);
        snprintf(b, sizeof b, "%d | %d", v3[k], tot);
        ui_text(p, b);
        snprintf(p, sizeof p, "anim-group.vote.vs%cF", K3[k]);
        nr_bar(p, MFNR_RX0, MFNR_RX1, 510.0f + 96.0f * (float)k + 36.0f + 3.0f, tot > 0 ? (float)v3[k] / (float)tot : 0.0f);
    }
    snprintf(b, sizeof b, "%d", c.need);
    ui_text("anim-group.vote.voteNeeded", b);
}
