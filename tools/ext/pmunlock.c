// pmunlock.c - the post-match UNLOCKS stage (the post-match summary screens show newly achieved achievements in the match and new
// unlocks (for clothing)). Stage 3 of to1/clan-postmatch (t2r-ext pm_tick): after the day result, only when the match unlocked something.
// Widgets: tools/features/clan_widgets.py build_postmatch_page group "unlocks" (PM_U_*). Included after customize.c (uses g_cz, cz_*, czc_sex,
// the achievement page's aui_ach and the unlock card's queue ACC). Log prefix "pmu:".
//
//   ACHIEVEMENTS (left)  the ones the daemon's table reply after the match says are new (achieve.c ach_parse puts them in g_ach_new as well as
//                        in the toast queue; g_ach_new is emptied when a match starts). The page lists them instead of the unlock card: the
//                        card does not run on the post-match page (achieve_ui.c ACHC_PAGES) and the listed ones leave its queue (achc_drop).
//   NEW UNLOCKS (right)  CUSTOMIZE items of each faction's worn sex that are unlocked now and were locked when the match started (pmu_match_start
//                        takes that picture of the profile); the clan's faction first. Items not in multiplayer yet (tier > 1) are left out.
// PMU_ROWS tiles a column (accent bar = new), "+N MORE ..." under a full column, a grey line in a column with nothing new. The rows come in
// one after another (PMU_STAG ms apart); the first select during that shows them all, the next one closes the page.
#define PMU_ROWS 4
#define PMU_MAXG 24
#define PMU_Y0 530.0f                                  // = clan_widgets PM_U_Y0 / PM_U_DY / PM_U_TX / PM_SEC_Y
#define PMU_DY 250.0f
#define PMU_TX 280.0f
#define PMU_SEC_Y 470.0f
#define PMU_STAG 140
#define PMU_FADE 260
static struct { uint8_t was[CZ_NFAC][CZ_NSEX][CZ_NWEAR][CZC_MAXIT]; int have; } g_czu;
static struct {
    int na, ng, ngt;                                   // achievements, gear rows kept, gear new in all
    ach_new_t a[ACH_TOAST_Q];
    struct { uint8_t f, s, c, k; } g[PMU_MAXG];
    uint64_t built_at;
    int fac_first;
} PMU;

static void pmu_match_start(void) {                    // feature_clan, when a match starts: what is unlocked now
    EnterCriticalSection(&g_clan_cs);
    InterlockedExchange(&g_ach_new_n, 0);
    LeaveCriticalSection(&g_clan_cs);
    cz_load();
    memset(g_czu.was, 0, sizeof g_czu.was);
    int n = 0;
    for (int f = 0; f < CZ_NFAC; f++)
        for (int s = 0; s < CZ_NSEX; s++)
            for (int c = 0; c < CZ_NWEAR; c++)
                for (int k = 0; k < cz_count(f, s, c) && k < CZC_MAXIT; k++)
                    if (cz_unlocked(&g_cz, cz_item(f, s, c, k))) { g_czu.was[f][s][c][k] = 1; n++; }
    g_czu.have = 1;
    xlog("pmu: match start - %d items unlocked before it", n);
}

static void pmu_build(int fac_first) {                 // the lists as they are now (the achievement reply can land while the page is up)
    PMU.built_at = GetTickCount64();
    PMU.fac_first = fac_first;
    PMU.na = 0;
    if (!ach_off()) {
        EnterCriticalSection(&g_clan_cs);
        for (LONG i = 0; i < g_ach_new_n && PMU.na < ACH_TOAST_Q; i++) PMU.a[PMU.na++] = g_ach_new[i];
        LeaveCriticalSection(&g_clan_cs);
    }
    PMU.ng = PMU.ngt = 0;
    if (!g_czu.have || !cz_enabled()) return;
    for (int fi = 0; fi < CZ_NFAC; fi++) {
        int f = fi == 0 ? fac_first : 1 - fac_first, s = czc_sex(f);
        for (int c = 0; c < CZ_NWEAR; c++)
            for (int k = 0; k < cz_count(f, s, c) && k < CZC_MAXIT; k++) {
                const cz_item_t *it = cz_item(f, s, c, k);
                if (!it || !it->uk || it->tier > 1 || g_czu.was[f][s][c][k] || !cz_unlocked(&g_cz, it) || cz_story_mask_off(it)) continue;
                PMU.ngt++;
                if (PMU.ng < PMU_MAXG) { PMU.g[PMU.ng].f = (uint8_t)f; PMU.g[PMU.ng].s = (uint8_t)s; PMU.g[PMU.ng].c = (uint8_t)c; PMU.g[PMU.ng].k = (uint8_t)k; PMU.ng++; }
            }
    }
}
static int pmu_fac(const clan_t *c) { return c->fac == 2 ? 1 : 0; }    // clan faction 1 WLF / 2 Seraphites -> customize 0 / 1
static int pmu_count(const clan_t *c) {                // stage 2: anything for stage 3? (rebuilt every 250 ms)
    if (GetTickCount64() - PMU.built_at > 250 || PMU.fac_first != pmu_fac(c)) pmu_build(pmu_fac(c));
    return PMU.na + PMU.ngt;
}

#define PMU_P(x) "anim-group.unlocks." x
static void pmu_fill(const clan_t *c) {
    char p[96], b[200], t[200];
    pmu_build(pmu_fac(c));
    for (int i = 0; i < PMU.na; i++) achc_drop(PMU.a[i].id);
    snprintf(b, sizeof b, "%d", PMU.na);
    pmnr_section(PMU_P("pmSecUa"), PMN_LX0, PMN_LX1, PMU_SEC_Y, "ACHIEVEMENTS", PMU.na ? b : "");
    snprintf(b, sizeof b, "%d", PMU.ngt);
    pmnr_section(PMU_P("pmSecUc"), PMN_RX0, PMN_RX1, PMU_SEC_Y, "NEW UNLOCKS", PMU.ngt ? b : "");
    const float twa = PMN_LX1 - PMN_LX0 - PMU_TX - 50.0f, twc = PMN_RX1 - PMN_RX0 - PMU_TX - 50.0f;
    for (int k = 0; k < PMU_ROWS; k++) {
        int on = k < PMU.na;
        snprintf(p, sizeof p, PMU_P("pmUa%d"), k); ui_visible(p, on);
        if (on) {
            snprintf(p, sizeof p, PMU_P("pmUa%d.pmUa%dTi"), k, k); pmnr_fit(p, aui_ach(PMU.a[k].id, 0, PMU.a[k].title, t, sizeof t), twa, 39.0f);
            snprintf(p, sizeof p, PMU_P("pmUa%d.pmUa%dDs"), k, k); ui_text(p, aui_ach(PMU.a[k].id, 1, PMU.a[k].desc, t, sizeof t));
            snprintf(p, sizeof p, PMU_P("pmUa%d.pmUa%dIc"), k, k); snprintf(b, sizeof b, "streaming/t2r/ach/%s.png", PMU.a[k].id); ui_image(p, b);
        }
        on = k < PMU.ng;
        snprintf(p, sizeof p, PMU_P("pmUc%d"), k); ui_visible(p, on);
        if (!on) continue;
        const int f = PMU.g[k].f, s = PMU.g[k].s, cat = PMU.g[k].c;
        const cz_item_t *it = cz_item(f, s, cat, PMU.g[k].k);
        snprintf(p, sizeof p, PMU_P("pmUc%d.pmUc%dTi"), k, k); pmnr_fit(p, loc_tr(it->label), twc, 39.0f);
        snprintf(t, sizeof t, "%s", loc_tr(CZ_CAT_LABEL[cat]));
        snprintf(b, sizeof b, "%s  |  %s", loc_tr(CZ_FAC_NAME[f]), t);
        snprintf(p, sizeof p, PMU_P("pmUc%d.pmUc%dSub"), k, k); ui_text(p, b);
        snprintf(p, sizeof p, PMU_P("pmUc%d.pmUc%dCh"), k, k); pmnr_fit(p, loc_tr(CZ_CHAL[it->uk].title), twc, 30.0f);
        snprintf(p, sizeof p, PMU_P("pmUc%d.pmUc%dPic"), k, k); ui_visible(p, it->pic != NULL);
        if (it->pic) { snprintf(b, sizeof b, "streaming/t2r/icons/%s.png", it->pic); ui_image(p, b); }
        snprintf(p, sizeof p, PMU_P("pmUc%d.pmUc%dIc"), k, k); ui_visible(p, it->pic == NULL);
        if (!it->pic) {
            const char *ic = cat == CZ_MELEE ? (strstr(it->label, "KNIFE") ? "cz-knife" : "cz-fists") : CZ_ICON[cat];
            snprintf(b, sizeof b, "streaming/t2r/icons/%s.png", ic); ui_image(p, b);
        }
    }
    ui_visible(PMU_P("pmUaNone"), PMU.na == 0);
    ui_visible(PMU_P("pmUcNone"), PMU.ngt == 0);
    // the foot lines sit under the column's last tile (lm boxes: pivot = left middle, 60 high)
    ui_visible(PMU_P("pmUaMore"), PMU.na > PMU_ROWS);
    if (PMU.na > PMU_ROWS) { snprintf(b, sizeof b, "+%d MORE IN CLAN | ACHIEVEMENTS", PMU.na - PMU_ROWS); ui_text(PMU_P("pmUaMore"), b); }
    ui_visible(PMU_P("pmUcFoot"), PMU.ngt > 0);
    if (PMU.ngt > PMU_ROWS) snprintf(b, sizeof b, "+%d MORE  |  EQUIP THEM IN CUSTOMIZE", PMU.ngt - PMU_ROWS);
    else snprintf(b, sizeof b, "EQUIP THEM IN CUSTOMIZE");
    ui_text(PMU_P("pmUcFoot"), b);
    {
        int ng = PMU.ngt < PMU_ROWS ? PMU.ngt : PMU_ROWS;
        uint64_t w = ui_w(PMU_P("pmUcFoot"));
        if (w) w_pivot(w, PMN_RX0, PMU_Y0 + ng * PMU_DY + 20.0f + 30.0f);
    }
    xlog("pmu: unlocks page - %d achievement(s), %d item(s) (%d listed)", PMU.na, PMU.ngt, PMU.ng);
}
static void pmu_frame(const clan_t *c, uint64_t el) {  // stage 3, every frame: the rows come in one after another; a late reply refills
    char p[96];
    int na = PMU.na, ngt = PMU.ngt;
    if (GetTickCount64() - PMU.built_at > 250) {
        pmu_build(pmu_fac(c));
        if (PMU.na != na || PMU.ngt != ngt) pmu_fill(c);
    }
    for (int k = 0; k < PMU_ROWS; k++) {
        float a = el <= (uint64_t)(k * PMU_STAG) ? 0.0f : (float)(el - (uint64_t)(k * PMU_STAG)) / PMU_FADE;
        if (a > 1.0f) a = 1.0f;
        snprintf(p, sizeof p, PMU_P("pmUa%d"), k); w_alpha(ui_w(p), a);
        snprintf(p, sizeof p, PMU_P("pmUc%d"), k); w_alpha(ui_w(p), a);
    }
}
static uint64_t pmu_anim_ms(void) { return (uint64_t)((PMU_ROWS - 1) * PMU_STAG + PMU_FADE); }
