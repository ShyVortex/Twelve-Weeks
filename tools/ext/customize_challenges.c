// customize_challenges.c - CUSTOMIZE | CHALLENGES (to1/customize-challenges) and the first-visit CHALLENGES tip on the CUSTOMIZE page.
// Widgets: tools/features/customize_challenges_widgets.py (the page; the tip is built into the CUSTOMIZE page by customize_widgets.py).
// Doc: re/customize-1117.md "Challenges page". Included by customize.c (uses g_cz, cz_* and the shared No Return frame helpers of nrui.c).
//
// Page: the No Return frame (CUSTOMIZE | CHALLENGES, Q / E = WLF / SERAPHITES), one row per category that has unlocks (the faction's worn
// sex), a line of tiles per row (the item's picture: colour when unlocked, the dark greyscale copy + a padlock while locked; a thin
// progress bar under each), ONE focus outline, a detail column (the big picture, the challenge, N | M, "Unlocks:" + the item chip).
// Arrows / stick / d-pad move in both axes (the column is kept between rows), the wheel scrolls the rows, hover focuses, SELECT / a click
// equips an unlocked item (the same choice as the CUSTOMIZE page, saved at once), BACK / Esc returns to CUSTOMIZE.
// The way in: the CHALLENGES prompt on the CUSTOMIZE page (C on the keyboard, X on the pad, a click) and the tip's line.

#define CZC_COLS 6
#define CZC_ROWS 3
#define CZC_X0 148.0f
#define CZC_TW 300.0f
#define CZC_TH 275.0f
#define CZC_TGAP 24.0f
#define CZC_X1 (CZC_X0 + CZC_COLS * CZC_TW + (CZC_COLS - 1) * CZC_TGAP)
#define CZC_ROW_Y0 440.0f
#define CZC_ROW_P 440.0f
#define CZC_TILE_DY 46.0f
#define CZC_BAR_DY (CZC_TH + 16.0f)
#define CZC_SB_X (CZC_X1 + 60.0f)
#define CZC_D_X0 2300.0f
#define CZC_D_X1 3700.0f
#define CZC_D_TITLE_Y (400.0f + 715.0f + 70.0f)
#define CZC_MAXIT 48
#define CZC_SEC_PT 36.0f                         // nr_style.pt(24)
#define CZC_CHIP_PT 30.0f                        // nr_style.pt(20)
#define CZC_TIP_X1 2870.0f
#define CZC_TIP_CONT_PT 42.0f                    // nr_style.pt(28)

static const char *const CZC_TAB[CZ_NFAC] = {"WLF", "SERAPHITES"};
static struct {
    int up, quiet, closing, back_f;
    uint64_t enter_ms, key;
    int fac;
    int nrow, rcat[CZ_NWEAR], rn[CZ_NWEAR], rk[CZ_NWEAR][CZC_MAXIT];   // the rows: category, item count, item indexes (list order)
    int fr, fc, row0, off[CZ_NWEAR], want;       // focus row / item, first row on screen, each row's first item, the column kept between rows
    int hv_r, hv_c, hv_tab, hv_q, hv_e, hv_pb;
    int h_sel, h_u, h_d, h_l, h_r, h_back, h_esc, h_pv, h_nx, h_q, h_e;
    uint64_t t_u, t_d, t_l, t_r;
} CZC;

static uint64_t czc_page_id(void) { static uint64_t id; if (!id) id = page_id("customize-challenges"); return id; }
static int czc_sex(int fac) { return g_cz.sex[fac] < CZ_NSEX ? g_cz.sex[fac] : 0; }

// the rows of a faction + sex: every category before SEX with at least one item that has a challenge
static int czc_rows_of(int fac, int sex, int *rcat, int *rn, int rk[][CZC_MAXIT]) {
    int nr = 0;
    for (int c = 0; c < CZ_NWEAR; c++) {
        int n = 0;
        for (int k = 0; k < cz_count(fac, sex, c) && n < CZC_MAXIT; k++) {
            const cz_item_t *it = cz_item(fac, sex, c, k);
            if (it && it->uk && it->uk < CZ_NCHAL && !cz_plain_kind(CZ_CHAL[it->uk].kind) && !cz_story_mask_off(it)) rk[nr][n++] = k;     // (OG / KELLIE: not a challenge)
        }
        if (n) { rcat[nr] = c; rn[nr] = n; nr++; }
    }
    return nr;
}
static void czc_build(void) { CZC.nrow = czc_rows_of(CZC.fac, czc_sex(CZC.fac), CZC.rcat, CZC.rn, CZC.rk); }
// challenges done / total of a faction (both sexes: the tip's card) or of the shown rows (the page)
static void czc_count(int fac, int both, int *done, int *tot) {
    int rc[CZ_NWEAR], rn[CZ_NWEAR], rk[CZ_NWEAR][CZC_MAXIT];
    *done = *tot = 0;
    for (int s = 0; s < CZ_NSEX; s++) {
        if (!both && s != czc_sex(fac)) continue;
        int nr = czc_rows_of(fac, s, rc, rn, rk);
        for (int r = 0; r < nr; r++)
            for (int i = 0; i < rn[r]; i++) { (*tot)++; if (cz_unlocked(&g_cz, cz_item(fac, s, rc[r], rk[r][i]))) (*done)++; }
    }
}

// ------------------------------------------------------------------ text helpers
// UTF-8 lower case for ASCII + the Polish capitals (the challenge line in sentence case, STYLE.md)
static void czc_lower(char *s) {
    unsigned char *q = (unsigned char *)s;
    while (*q) {
        if (*q >= 'A' && *q <= 'Z') { *q += 32; q++; continue; }
        if (q[1] && ((q[0] == 0xC4 && (q[1] == 0x84 || q[1] == 0x86 || q[1] == 0x98)) || (q[0] == 0xC5 && (q[1] == 0x81 || q[1] == 0x83 || q[1] == 0x9A || q[1] == 0xB9 || q[1] == 0xBB)))) { q[1]++; q += 2; continue; }
        if (q[0] == 0xC3 && q[1] == 0x93) { q[1] = 0xB3; q += 2; continue; }       // O-acute -> o-acute
        q++;
    }
}
static void czc_title_case(char *s, size_t n) {    // "capitol hill shops" -> "Capitol Hill Shops" (n bytes from s)
    for (size_t i = 0; i < n; i++) if ((i == 0 || s[i - 1] == ' ') && s[i] >= 'a' && s[i] <= 'z') s[i] -= 32;
}
// the challenge line of item it: translated, sentence case, map names keep their capitals, a full stop
static void czc_line(const cz_item_t *it, char *out, int cap) {
    out[0] = 0;
    if (!it || !it->uk || it->uk >= CZ_NCHAL) return;
    const cz_chal_t *c = &CZ_CHAL[it->uk];
    char t[160];
    const char *map = c->kind == CZK_MAPWINS && it->um < CZ_NUMAP ? CZ_UMAP_NAME[it->um] : NULL;
    if (c->kind == CZK_SAFES && it->un == 1) snprintf(t, sizeof t, "CRACK A SAFE IN INTERROGATION");
    else if (map && it->un == 1) snprintf(t, sizeof t, "WIN A MATCH ON %s", map);
    else if (c->kind == CZK_WEEKS && it->un == 1) snprintf(t, sizeof t, "SURVIVE A WEEK");
    else if (c->kind == CZK_FLAWLESS && it->un == 1) snprintf(t, sizeof t, "WIN A MATCH WITHOUT DYING");
    else if (map) snprintf(t, sizeof t, c->line, (unsigned)it->un, map);
    else snprintf(t, sizeof t, c->line, (unsigned)it->un);
    snprintf(out, (size_t)cap, "%s", loc_tr(t));
    czc_lower(out);
    if (out[0] >= 'a' && out[0] <= 'z') out[0] -= 32;
    if (map) {
        char m[64]; snprintf(m, sizeof m, "%s", map); czc_lower(m);
        char *p = strstr(out, m);
        if (p) czc_title_case(p, strlen(m));
    }
    size_t n = strlen(out);
    if (n && n + 1 < (size_t)cap && out[n - 1] != '.') { out[n] = '.'; out[n + 1] = 0; }
}
// the reward chip: "TORSO - FIELD JACKET"; a label that starts with its category's word stays alone ("FACE 05", not "FACE - FACE 05")
static void czc_chip_text(int cat, const cz_item_t *it, char *out, int cap) {
    const char *lb = it ? it->label : "", *cl = CZ_CAT_LABEL[cat];
    char w1[32]; int n = 0;
    while (lb[n] && lb[n] != ' ' && n < 31) { w1[n] = lb[n]; n++; }
    w1[n] = 0;
    int same = 0;
    for (const char *q = cl; *q && !same; ) {
        const char *e = strchr(q, ' '); size_t l = e ? (size_t)(e - q) : strlen(q);
        if (l == strlen(w1) && !strncmp(q, w1, l)) same = 1;
        q = e ? e + 1 : q + l;
    }
    char a[64]; snprintf(a, sizeof a, "%s", loc_tr(cl));
    if (same) snprintf(out, (size_t)cap, "%s", loc_tr(lb));
    else snprintf(out, (size_t)cap, "%s - %s", a, loc_tr(lb));
}

// ------------------------------------------------------------------ focus / scrolling
static int czc_row_ok(int r) { return r >= 0 && r < CZC.nrow; }
static void czc_keep_visible(void) {
    if (!CZC.nrow) { CZC.fr = CZC.fc = CZC.row0 = 0; return; }
    if (CZC.fr >= CZC.nrow) CZC.fr = CZC.nrow - 1;
    if (CZC.fr < 0) CZC.fr = 0;
    int n = CZC.rn[CZC.fr];
    if (CZC.fc >= n) CZC.fc = n - 1;
    if (CZC.fc < 0) CZC.fc = 0;
    if (CZC.fr < CZC.row0) CZC.row0 = CZC.fr;
    if (CZC.fr >= CZC.row0 + CZC_ROWS) CZC.row0 = CZC.fr - CZC_ROWS + 1;
    int *o = &CZC.off[CZC.fr];
    if (CZC.fc < *o) *o = CZC.fc;
    if (CZC.fc >= *o + CZC_COLS) *o = CZC.fc - CZC_COLS + 1;
}
static void czc_move_row(int d) {                  // up / down: the next row, the same screen column (the item there, or its last)
    int r = CZC.fr + d;
    if (!czc_row_ok(r)) return;
    CZC.fr = r;
    int c = CZC.want, n = CZC.rn[r];
    CZC.fc = CZC.off[r] + c;
    if (CZC.fc >= n) CZC.fc = n - 1;
    ui_sfx("sfx-cycle");
}
static void czc_set_fac(int f, const char *why) {
    f = (f % CZ_NFAC + CZ_NFAC) % CZ_NFAC;
    if (f == CZC.fac) return;
    CZC.fac = f;
    czc_build();
    CZC.fr = CZC.fc = CZC.row0 = CZC.want = 0;
    memset(CZC.off, 0, sizeof CZC.off);
    ui_sfx("sfx-cycle");
    xlog("customize: challenges of %s (%s)", CZ_FAC_NAME[f], why);
}
static void czc_equip(const char *why) {
    if (!czc_row_ok(CZC.fr)) return;
    const int fac = CZC.fac, sex = czc_sex(fac), cat = CZC.rcat[CZC.fr], k = CZC.rk[CZC.fr][CZC.fc];
    const cz_item_t *it = cz_item(fac, sex, cat, k);
    if (!it || !cz_unlocked(&g_cz, it)) { ui_deny(NULL); return; }
    if (it->tier > 1) { ui_deny(loc_tr("NOT IN MULTIPLAYER YET")); return; }
    if (g_cz.it[fac][sex][cat] == k) return;
    g_cz.it[fac][sex][cat] = (uint8_t)k;
    cz_save();
    cz_net_changed();
    ui_sfx("sfx-select");
    CZC.key = 0;
    xlog("customize: %s %s %s = %s (challenges page, %s)", CZ_FAC_NAME[fac], CZ_SEX_KEY[sex], CZ_CAT_LABEL[cat], it->label, why);
}

// ------------------------------------------------------------------ hover (canvas geometry = the widget file)
static void czc_tile_xy(int r, int c, float *x, float *y) { *x = CZC_X0 + c * (CZC_TW + CZC_TGAP); *y = CZC_ROW_Y0 + r * CZC_ROW_P + CZC_TILE_DY; }
static void czc_scan(void) {
    float cx, cy;
    CZC.hv_r = CZC.hv_c = CZC.hv_tab = CZC.hv_pb = -1; CZC.hv_q = CZC.hv_e = 0;
    CZC.hv_pb = nr_prompt_hover();
    for (int k = 0; k < CZ_NFAC; k++) { char p[48]; snprintf(p, sizeof p, "anim-group.tabs.tbHit%d", k); if (ui_mouse_over(p, 1)) CZC.hv_tab = k; }
    CZC.hv_q = ui_mouse_over("anim-group.tabs.tbQHit", 1);
    CZC.hv_e = ui_mouse_over("anim-group.tabs.tbEHit", 1);
    if (g_pad_mode || !ui_cursor_canvas(&cx, &cy)) return;
    for (int r = 0; r < CZC_ROWS; r++) {
        int ri = CZC.row0 + r;
        if (!czc_row_ok(ri)) break;
        for (int c = 0; c < CZC_COLS; c++) {
            float x, y; czc_tile_xy(r, c, &x, &y);
            if (cx >= x && cx < x + CZC_TW && cy >= y && cy < y + CZC_TH && CZC.off[ri] + c < CZC.rn[ri]) { CZC.hv_r = ri; CZC.hv_c = CZC.off[ri] + c; }
        }
    }
}
static int czc_click_hit(void) {
    if (!CZC.up || CZC.quiet) return 0;
    czc_scan();
    return CZC.hv_r >= 0 || CZC.hv_tab >= 0 || CZC.hv_q || CZC.hv_e || CZC.hv_pb >= 0;
}

// ------------------------------------------------------------------ fill (only on a change of what is shown)
static void czc_scroll_h(const char *base, float x0, float x1, float y_mid, int first, int shown, int n) {
    char p[96];
    int on = n > shown;
    snprintf(p, sizeof p, "%sT", base); ui_visible(p, on);
    snprintf(p, sizeof p, "%sH", base); ui_visible(p, on);
    if (!on) return;
    float a = (float)first / (float)n, w = (x1 - x0) * (float)shown / (float)n;
    if (w < 8.0f) w = 8.0f;
    uint64_t h = ui_w(p);
    if (h) { w_pivot(h, x0 + (x1 - x0) * a, y_mid); w_scale(h, w / NR_RULE_W0, 1.0f); }
}
static void czc_fill(void) {
    const int fac = CZC.fac, sex = czc_sex(fac);
    uint64_t key = (uint64_t)fac | (uint64_t)CZC.fr << 2 | (uint64_t)(CZC.fc & 0xff) << 6 | (uint64_t)CZC.row0 << 14 | (uint64_t)(CZC.hv_tab + 1) << 18 |
                   (uint64_t)(CZC.hv_pb + 1 & 7) << 20 | (uint64_t)(g_pad_mode & 1) << 23 | (uint64_t)(g_cz_gen & 0xff) << 24 | (uint64_t)(CZC.hv_q | CZC.hv_e << 1) << 32 | 1ULL << 63;
    for (int r = 0; r < CZ_NWEAR; r++) key ^= (uint64_t)(CZC.off[r] & 0x3f) << (36 + 4 * r % 24);
    key ^= (uint64_t)g_cz.it[fac][sex][0] * 0x9E3779B97F4A7C15ULL ^ (uint64_t)g_cz.it[fac][sex][1] * 0xC2B2AE3D27D4EB4FULL ^ (uint64_t)g_cz.it[fac][sex][2] << 40 ^
           (uint64_t)g_cz.it[fac][sex][3] << 48 ^ (uint64_t)g_cz.it[fac][sex][4] << 56 ^ (uint64_t)g_cz.it[fac][sex][5] << 44;
    if (key == CZC.key) return;
    CZC.key = key;
    char p[128], b[192];
    nr_header(loc_tr("CUSTOMIZE"), loc_tr("CHALLENGES"));
    {   // the Q / E strip: WLF / SERAPHITES (nr_clan_tabs' layout: the Q glyph, labels 80 apart, the E glyph)
        float x = NR_L0 + 108.0f, ax = x, aw = 100.0f;
        for (int k = 0; k < NR_MAX_TABS; k++) {
            snprintf(p, sizeof p, "anim-group.tabs.tb%d", k); ui_visible(p, k < CZ_NFAC);
            snprintf(p, sizeof p, "anim-group.tabs.tbHit%d", k); ui_visible(p, k < CZ_NFAC);
            if (k >= CZ_NFAC) continue;
            const char *lb = loc_tr(CZC_TAB[k]);
            float w = nr_tw(lb, NR_TAB_PT) + 8.0f;
            snprintf(b, sizeof b, k == fac || k == CZC.hv_tab ? "%s" : "<font color=\"#8C8C8C\">%s</font>", lb);
            snprintf(p, sizeof p, "anim-group.tabs.tb%d", k); ui_text(p, b); w_pivot(ui_w(p), x, NR_TAB_Y);
            snprintf(p, sizeof p, "anim-group.tabs.tbHit%d", k); w_pivot(ui_w(p), x - 30.0f, NR_TAB_Y - 60.0f);
            if (k == fac) { ax = x; aw = w; }
            x += w + 80.0f;
        }
        float ex = x - 80.0f + 28.0f;
        w_pivot(ui_w("anim-group.tabs.tbE"), ex + 30.0f, NR_TAB_Y);
        w_pivot(ui_w("anim-group.tabs.tbEHit"), ex + 30.0f, NR_TAB_Y);
        uint64_t u = ui_w("anim-group.tabs.tbU");
        if (u) { w_pivot(u, ax, NR_TAB_Y + 38.0f); w_scale(u, aw / 100.0f, 1.0f); }
    }
    {
        int d, t; czc_count(fac, 0, &d, &t);
        snprintf(b, sizeof b, "%s %d | %d", loc_tr("COMPLETED"), d, t);
        ui_text("anim-group.chTot", b);
    }
    for (int r = 0; r < CZC_ROWS; r++) {
        const int ri = CZC.row0 + r, on = czc_row_ok(ri);
        snprintf(p, sizeof p, "anim-group.rows.rw%dTx", r); ui_visible(p, on);
        snprintf(p, sizeof p, "anim-group.rows.rw%dRt", r); ui_visible(p, on);
        snprintf(p, sizeof p, "anim-group.rows.rw%dRl", r); ui_visible(p, on);
        const int cat = on ? CZC.rcat[ri] : 0, n = on ? CZC.rn[ri] : 0, off = on ? CZC.off[ri] : 0;
        if (on) {
            int d = 0;
            for (int i = 0; i < n; i++) if (cz_unlocked(&g_cz, cz_item(fac, sex, cat, CZC.rk[ri][i]))) d++;
            char rt[32]; snprintf(rt, sizeof rt, "%d | %d", d, n);
            snprintf(p, sizeof p, "anim-group.rows.rw%d", r);
            nr_section(p, CZC_X0, CZC_X1, CZC_ROW_Y0 + r * CZC_ROW_P, loc_tr(CZ_CAT_LABEL[cat]), rt, CZC_SEC_PT);
        }
        for (int c = 0; c < CZC_COLS; c++) {
            const int k = off + c, ton = on && k < n;
            char g[48]; snprintf(g, sizeof g, "anim-group.rows.t%d_%d", r, c);
            ui_visible(g, ton);
            snprintf(p, sizeof p, "anim-group.rows.t%d_%dBT", r, c); ui_visible(p, ton);
            snprintf(p, sizeof p, "anim-group.rows.t%d_%dBF", r, c);
            if (!ton) { ui_visible(p, 0); continue; }
            const int ki = CZC.rk[ri][k];
            const cz_item_t *it = cz_item(fac, sex, cat, ki);
            const int lk = !cz_unlocked(&g_cz, it), f = ri == CZC.fr && k == CZC.fc;
            float x, y; czc_tile_xy(r, c, &x, &y);
            uint32_t pr = cz_progress(&g_cz, it);
            nr_bar(p, x, x + CZC_TW, y + CZC_BAR_DY + 2.0f, it->un ? (float)(pr < it->un ? pr : it->un) / (float)it->un : 1.0f);
            w_alpha(ui_w(p), f ? 1.0f : 150.0f / 255.0f);
            snprintf(p, sizeof p, "%s.t%d_%dP", g, r, c); ui_visible(p, it->pic != NULL);
            if (it->pic) {
                snprintf(b, sizeof b, lk ? "streaming/t2r/icons/czg-%s.png" : "streaming/t2r/icons/%s.png", lk ? it->pic + 4 : it->pic);
                ui_image(p, b); w_alpha(ui_w(p), f ? 1.0f : lk ? 200.0f / 255.0f : 150.0f / 255.0f);
            }
            snprintf(p, sizeof p, "%s.t%d_%dI", g, r, c); ui_visible(p, it->pic == NULL);
            if (!it->pic) {
                const char *ic = cat == CZ_MELEE ? (strstr(it->label, "KNIFE") ? "cz-knife" : "cz-fists") : CZ_ICON[cat];
                snprintf(b, sizeof b, "streaming/t2r/icons/%s.png", ic); ui_image(p, b); w_alpha(ui_w(p), f ? 1.0f : lk ? 90.0f / 255.0f : 150.0f / 255.0f);
            }
            snprintf(p, sizeof p, "%s.t%d_%dL", g, r, c); ui_visible(p, lk); if (lk) w_alpha(ui_w(p), f ? 1.0f : 170.0f / 255.0f);
            snprintf(p, sizeof p, "%s.t%d_%dBg", g, r, c); w_alpha(ui_w(p), (f ? 215.0f : 175.0f) / 255.0f);
            snprintf(p, sizeof p, "%s.t%d_%dN", g, r, c); ui_visible(p, 0);       // (NEW dots: not tracked yet)
        }
        snprintf(p, sizeof p, "anim-group.rows.rs%d", r);
        czc_scroll_h(p, CZC_X0, CZC_X1, CZC_ROW_Y0 + r * CZC_ROW_P + CZC_TILE_DY + CZC_BAR_DY + 30.0f + 1.0f, off, CZC_COLS, on ? n : 0);
    }
    {   // the focus outline
        int r = CZC.fr - CZC.row0, c = CZC.fc - (czc_row_ok(CZC.fr) ? CZC.off[CZC.fr] : 0), on = czc_row_ok(CZC.fr) && r >= 0 && r < CZC_ROWS && c >= 0 && c < CZC_COLS;
        float x = 0, y = 0; if (on) czc_tile_xy(r, c, &x, &y);
        nr_frame_at("anim-group.rows.foc", x - 6.0f, y - 6.0f, CZC_TW + 12.0f, CZC_TH + 12.0f, on);
    }
    nr_scroll_v("anim-group.rows.sbV", CZC_SB_X, CZC_ROW_Y0 - 20.0f, CZC_ROW_Y0 + (CZC_ROWS - 1) * CZC_ROW_P + CZC_TILE_DY + CZC_BAR_DY + 8.0f,
                CZC_ROW_Y0 + (CZC_ROWS - 1) * CZC_ROW_P + CZC_TILE_DY + CZC_BAR_DY + 8.0f - (CZC_ROW_Y0 - 20.0f), CZC.row0, CZC_ROWS, CZC.nrow);
    // the detail column
    int eq_on = 0;
    if (czc_row_ok(CZC.fr)) {
        const int cat = CZC.rcat[CZC.fr], ki = CZC.rk[CZC.fr][CZC.fc];
        const cz_item_t *it = cz_item(fac, sex, cat, ki);
        const int lk = !cz_unlocked(&g_cz, it), worn = g_cz.it[fac][sex][cat] == ki;
        ui_visible("anim-group.det.dArt", it->pic != NULL); ui_visible("anim-group.det.dIc", it->pic == NULL);
        if (it->pic) { snprintf(b, sizeof b, "streaming/t2r/icons/%s.png", it->pic); ui_image("anim-group.det.dArt", b); w_alpha(ui_w("anim-group.det.dArt"), lk ? 150.0f / 255.0f : 1.0f); }
        else {
            const char *ic = cat == CZ_MELEE ? (strstr(it->label, "KNIFE") ? "cz-knife" : "cz-fists") : CZ_ICON[cat];
            snprintf(b, sizeof b, "streaming/t2r/icons/%s.png", ic); ui_image("anim-group.det.dIc", b);
        }
        ui_visible("anim-group.det.dLock", 0);
        nr_fit("anim-group.det.dTitle", loc_tr(CZ_CHAL[it->uk].title), CZC_D_X1 - CZC_D_X0, NR_HEAD_PT);
        czc_line(it, b, sizeof b); ui_text("anim-group.det.dDesc", b);
        uint32_t pr = cz_progress(&g_cz, it); if (pr > it->un) pr = it->un;
        nr_bar("anim-group.det.dBarF", CZC_D_X0, CZC_D_X1 - 260.0f, CZC_D_TITLE_Y + 210.0f + 3.0f, it->un ? (float)pr / (float)it->un : 1.0f);
        snprintf(b, sizeof b, "%u | %u", (unsigned)pr, (unsigned)it->un); ui_text("anim-group.det.dCnt", b);
        ui_text("anim-group.det.dUnl", loc_tr("Unlocks:"));
        czc_chip_text(cat, it, b, sizeof b);
        float cx0 = CZC_D_X0 + nr_tw(loc_tr("Unlocks:"), 33.0f) + 30.0f;
        nr_chip("anim-group.det.dChip", b, cx0, 0.0f, CZC_CHIP_PT); nr_chip("anim-group.det.dChipA", b, cx0, 0.0f, CZC_CHIP_PT);
        ui_visible("anim-group.det.dChipBg", lk); ui_visible("anim-group.det.dChipTx", lk);
        ui_visible("anim-group.det.dChipABg", !lk); ui_visible("anim-group.det.dChipATx", !lk);
        ui_text("anim-group.det.dState", loc_tr(lk ? "LOCKED" : worn ? "EQUIPPED" : it->tier > 1 ? "NOT IN MULTIPLAYER YET" : "UNLOCKED"));
        eq_on = !lk && !worn && it->tier <= 1;
    }
    ui_visible("anim-group.det", czc_row_ok(CZC.fr));
    const nr_prompt_t pr[3] = {{"menu:prev+menu:next", NULL, loc_tr("SWITCH FACTION"), 1}, {"menu:select", NULL, loc_tr("EQUIP"), eq_on},
                               {"menu:back", NULL, loc_tr("BACK"), 1}};
    nr_prompts(pr, 3);
}

// ------------------------------------------------------------------ page lifecycle
static void czc_open(const char *why) {
    if (top_page() == czc_page_id()) return;
    xlog("customize: CHALLENGES opened (%s) - pushing to1/customize-challenges", why);
    ui_sfx("sfx-select");
    push_page("to1/customize-challenges");
}
static void czc_enter(void) {
    memset(&CZC, 0, sizeof CZC);
    cz_load();
    CZC.up = 1; CZC.enter_ms = GetTickCount64();
    CZC.h_sel = CZC.h_u = CZC.h_d = CZC.h_l = CZC.h_r = CZC.h_back = CZC.h_esc = CZC.h_pv = CZC.h_nx = CZC.h_q = CZC.h_e = 1;   // held on arrival = not a press
    CZC.t_u = CZC.t_d = CZC.t_l = CZC.t_r = ~0ULL;
    CZC.fac = CZ.fac >= 0 && CZ.fac < CZ_NFAC ? CZ.fac : 0;      // the faction being edited on CUSTOMIZE
    czc_build();
    for (int r = 0; r < CZC.nrow; r++) if (CZC.rcat[r] == CZ.cat) CZC.fr = r;     // open on the category CUSTOMIZE was showing
    czc_keep_visible();
    w_alpha(ui_w("anim-group"), 0.0f);
    xlog("customize: challenges page up (%s, %d rows)", CZ_FAC_NAME[CZC.fac], CZC.nrow);
}
static void czc_close(const char *how) {
    if (CZC.closing || CZC.quiet) return;
    xlog("customize: challenges back (%s)", how);
    w_alpha(ui_w("anim-group"), 1.0f);
    CZC.quiet = 1;
    CZC.back_f = g_frame ? (int)g_frame : 1;      // the engine pops a pushed page on menu-back itself; Esc / a click it does not (judged 6 frames later)
    if (strcmp(how, "menu-back") && top_page() == czc_page_id()) { pop_page(); CZC.closing = 1; CZC.back_f = 0; }
}
static void czc_tick(void) {
    if (!CZC.up) czc_enter();
    if (CZC.closing) return;
    uint64_t now = GetTickCount64();
    int sel = menu_edge(0x6695c5b7921bb5ddULL /* menu-select */, &CZC.h_sel);
    int up = gu_rep(&CZC.h_u, &CZC.t_u, fnv64("menu-up")), down = gu_rep(&CZC.h_d, &CZC.t_d, fnv64("menu-down"));
    int left = gu_rep(&CZC.h_l, &CZC.t_l, fnv64("menu-left")), right = gu_rep(&CZC.h_r, &CZC.t_r, fnv64("menu-right"));
    int back = menu_edge(fnv64("menu-back"), &CZC.h_back);
    int esc_now = game_focused() && (GetAsyncKeyState(VK_ESCAPE) & 0x8000) != 0, esc = esc_now && !CZC.h_esc;
    CZC.h_esc = esc_now;
    int kq = game_focused() && (GetAsyncKeyState('Q') & 0x8000) != 0, ke = game_focused() && (GetAsyncKeyState('E') & 0x8000) != 0;
    int tab_l = (kq && !CZC.h_q) || menu_edge(fnv64("menu-prev"), &CZC.h_pv), tab_r = (ke && !CZC.h_e) || menu_edge(fnv64("menu-next"), &CZC.h_nx);
    CZC.h_q = kq; CZC.h_e = ke;
    int wn = wheel_notches();
    czc_scan();
    int click = g_click_edge;
    if (back || esc || (click && CZC.hv_pb == 2)) czc_close(esc ? "Esc" : back ? "menu-back" : "BACK clicked");
    if (CZC.back_f && g_frame >= (uint64_t)CZC.back_f + 6) {
        CZC.back_f = 0;
        if (top_page() == czc_page_id() && !CZC.closing) { pop_page(); CZC.closing = 1; xlog("customize: challenges closed"); return; }
    }
    if (CZC.quiet) return;
    if (tab_l || (click && CZC.hv_q)) czc_set_fac(CZC.fac - 1, "previous");
    else if (tab_r || (click && CZC.hv_e) || (click && CZC.hv_pb == 0)) czc_set_fac(CZC.fac + 1, "next");
    else if (click && CZC.hv_tab >= 0) czc_set_fac(CZC.hv_tab, "tab clicked");
    if (czc_row_ok(CZC.fr)) {
        if (up) czc_move_row(-1);
        if (down) czc_move_row(1);
        if (left && CZC.fc > 0) { CZC.fc--; ui_sfx("sfx-cycle"); }
        if (right && CZC.fc + 1 < CZC.rn[CZC.fr]) { CZC.fc++; ui_sfx("sfx-cycle"); }
        if (left || right) { czc_keep_visible(); CZC.want = CZC.fc - CZC.off[CZC.fr]; }
        if (wn) {                                       // the wheel: the rows (a row under the cursor with more tiles than fit: that row)
            if (CZC.nrow > CZC_ROWS) {
                int r0 = CZC.row0 - wn, mx = CZC.nrow - CZC_ROWS;
                CZC.row0 = r0 < 0 ? 0 : r0 > mx ? mx : r0;
                if (CZC.fr < CZC.row0) czc_move_row(CZC.row0 - CZC.fr);
                if (CZC.fr >= CZC.row0 + CZC_ROWS) czc_move_row(CZC.row0 + CZC_ROWS - 1 - CZC.fr);
            } else if (CZC.hv_r >= 0 && CZC.rn[CZC.hv_r] > CZC_COLS) {
                int *o = &CZC.off[CZC.hv_r], o2 = *o - wn, mx = CZC.rn[CZC.hv_r] - CZC_COLS;
                *o = o2 < 0 ? 0 : o2 > mx ? mx : o2;
            }
        }
        czc_keep_visible();
        { static int lr = -2, lc = -2; if ((CZC.hv_r != lr || CZC.hv_c != lc) && CZC.hv_r >= 0 && g_pad_mode == 0) { CZC.fr = CZC.hv_r; CZC.fc = CZC.hv_c; CZC.want = CZC.fc - CZC.off[CZC.fr]; } lr = CZC.hv_r; lc = CZC.hv_c; }   // hover = focus (mouse)
        if (click && CZC.hv_r >= 0) czc_equip("clicked");
        else if ((sel || (click && CZC.hv_pb == 1)) && now - CZC.enter_ms > 300) czc_equip(sel ? "select" : "EQUIP clicked");
    }
    czc_fill();
    {   // page fade-in over 220 ms
        float f = (float)(now - CZC.enter_ms) / 220.0f;
        if (f > 1.0f) f = 1.0f;
        static int lq = -1; int q = (int)(f * 24.0f + 0.5f);
        if (now - CZC.enter_ms < 40) lq = -1;
        if (q != lq) { lq = q; w_alpha(ui_w("anim-group"), (float)q / 24.0f); }
    }
}

// ------------------------------------------------------------------ the first-visit tip on the CUSTOMIZE page (group czTip)
// Shown over the page the first time CUSTOMIZE opens (profile flag chtip); the grid, tabs and the page's own text are hidden under it
// (gui2's image budget: the tip's four portraits replace the twelve card pictures). SELECT / BACK / Esc / a click on CONTINUE closes it.
static const char *const CZC_TIP_HIDE[] = {"grid", "tabs", "title", "titleDiv", "titleSub", "titleRule", "secName", "secRule", "mdlName", "pHint", "req", "logoF", "logoB",
                                           "chkF", "chkB", "pBackIc", "pBackTx", "pSelIc", "pSelTx", "pSwIc", "pSwTx", "pChKb", "pChKt", "pChTx", "pZmKb", "pZmKt", "pZmTx"};
static int g_czc_tip;                               // 1 = the tip is up on the CUSTOMIZE page
static void czc_tip_show(int on) {
    char p[64];
    g_czc_tip = on;
    ui_visible("anim-group.czTip", on);
    for (size_t i = 0; i < sizeof CZC_TIP_HIDE / sizeof CZC_TIP_HIDE[0]; i++) { snprintf(p, sizeof p, "anim-group.%s", CZC_TIP_HIDE[i]); ui_visible(p, !on); }
    if (!on) return;
    for (int k = 0; k < CZ_NFAC; k++) {
        int d, t; czc_count(k, 1, &d, &t);
        char b[32]; snprintf(b, sizeof b, "%d | %d", d, t);
        snprintf(p, sizeof p, "anim-group.czTip.tipC%d.tipC%dCt", k, k); ui_text(p, b);
        snprintf(p, sizeof p, "anim-group.czTip.tipC%d.tipC%dNm", k, k); ui_text(p, loc_tr(CZC_TAB[k]));
    }
    ui_text("anim-group.czTip.tipTitle", loc_tr("CHALLENGES"));
    ui_text("anim-group.czTip.tipLine1", loc_tr("Completing <font color=\"#ffffff\">Challenges</font> will permanently unlock new outfits, headwear, faces and more."));
    ui_text("anim-group.czTip.tipLine2", loc_tr("You can view your <font color=\"#ffffff\">Challenges</font> any time from the <font color=\"#ffffff\">CUSTOMIZE</font> page."));
    const char *ct = loc_tr("CONTINUE");
    ui_text("anim-group.czTip.tipCont", ct);
    float lw = nr_tw(ct, CZC_TIP_CONT_PT);
    w_pivot(ui_w("anim-group.czTip.tipKey"), CZC_TIP_X1 - lw - 22.0f - 32.0f, 1816.0f);
    xlog("customize: CHALLENGES tip shown (first visit)");
}
static void czc_tip_done(const char *how) {
    czc_tip_show(0);
    g_cz.flags |= CZF_CHTIP;
    cz_save();
    CZ.key = 0;
    ui_sfx("sfx-select");
    xlog("customize: CHALLENGES tip closed (%s)", how);
}
