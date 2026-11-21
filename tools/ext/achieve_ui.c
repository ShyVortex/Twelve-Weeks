// achieve_ui.c - the in-game ACHIEVEMENTS page (to1/clanach, tools/features/achieve_widgets.py): the 6th tab of the CLAN strip, registered with
// nrui.c nr_clan_xtab_add (Q / E and a click on the tab walk the clan's 5 tabs, then this one). Included after clan13.c. The data is the daemon's
// table (achieve.c g_ach, op 0xAA asked again on every opening); nothing is decided here. No Return style (re/ui-refs-1117/STYLE.md):
//
//   frame   breadcrumb WLF CLAN | ACHIEVEMENTS, the clan tab strip, the week block, the boxed prompts (nrui.c)
//   rows    one per group with entries (MELEE MASTERY, WEAPON FEATS, SKILL, MILESTONES, CLAN, HIDDEN): caps header + "N | M" + hairline, then up
//           to AUI_COLS tiles (unlocked art / dark locked art + padlock / dark "?" for a hidden one), a thin progress bar under counter ones and
//           the yellow-green dot on one unlocked since the last visit (t2r-ach-ui-seen.txt). AUI_ROWS rows on screen; the rows scroll up / down,
//           a row scrolls left / right; up / down keep the column.
//   focus   ONE white outline (nr_frame_at) on the focused tile
//   detail  UNLOCKED N | M (p%) + bar, the big icon, group, title, description, N | M + bar, Status: chip (UNLOCKED <date> / LOCKED / HIDDEN)
//
// Keys: the stick / d-pad / arrows / WASD move, the wheel moves a row, Q / E and LB / RB (menu-prev / menu-next) change the clan tab. Mouse: hover +
// click on tiles, tabs and prompts. Back: menu-back (the engine pops the page itself), Esc, F, a click on BACK: back on the clan page, the tab and
// tile it was on (clan13.c g_c13_resume). Log prefix "achui:".
#define AUI_NG 6
#define AUI_ROWS 3
#define AUI_COLS 6
#define AUI_X0 148.0f
#define AUI_TW 300.0f
#define AUI_TP 324.0f                                  // tile pitch (TW + TGAP)
#define AUI_X1 2068.0f
#define AUI_RY0 440.0f                                 // first row's header line
#define AUI_RP 440.0f                                  // row pitch
#define AUI_TDY 46.0f                                  // header line -> tile top
#define AUI_BDY 316.0f                                 // tile top -> its bar
#define AUI_SBX 2128.0f
#define AUI_SBY0 420.0f
#define AUI_SBY1 1690.0f
#define AUI_DX0 2300.0f
#define AUI_DX1 3700.0f
#define AUI_DTY 1290.0f                                // detail title line
#define AUI_NI 40                                      // max entries in one group
static const char *const AUI_GRP[AUI_NG] = {"melee", "weapon", "skill", "stats", "clan", "secret"};
static const char *const AUI_LBL[AUI_NG] = {"MELEE MASTERY", "WEAPON FEATS", "SKILL", "MILESTONES", "CLAN", "HIDDEN"};
static uint64_t achui_page_id(void) { static uint64_t id; if (!id) id = page_id("clanach"); return id; }
static struct {
    int on, seen, dirty, nr, grp[AUI_NG], cnt[AUI_NG], item[AUI_NG][AUI_NI], un[AUI_NG];
    int row0, off[AUI_NG], fr, fc, want, hv_r, hv_c, hv_tb, hv_pb;
    int h_back, h_esc, h_f, h_ka, h_kd, h_pv, h_nx, h_u, h_d, h_l, h_r, h_sel;
    int ret_tab, ret_fr[C13_NTAB], ret_fc[C13_NTAB], ret_roff[C13_NTAB];
    uint64_t t_u, t_d, t_l, t_r, f0, ask_at;
    uint32_t seen_t;
    LONG ver;
} AUI;
static ach_t g_aui_v;                                  // the table as last copied (main thread only)
static int g_aui_fr = -1, g_aui_fc;                    // (the focused tile stays for the session)
static int achui_avail(void) { return !ach_off(); }
static int achui_on(void) { return AUI.on; }
static uint32_t achui_seen_load(void) {
    FILE *f = exe_side_open("t2r-ach-ui-seen.txt", "r");
    unsigned v = 0;
    if (f) { if (fscanf(f, "%u", &v) != 1) v = 0; fclose(f); }
    return v;
}
static void achui_seen_save(void) {                    // the newest unlock time seen on the page: the NEW dots of the next visit
    uint32_t m = AUI.seen_t;
    for (int i = 0; i < g_aui_v.n; i++) if (g_aui_v.r[i].t > m) m = g_aui_v.r[i].t;
    if (m == AUI.seen_t) return;
    FILE *f = exe_side_open("t2r-ach-ui-seen.txt", "w");
    if (f) { fprintf(f, "%u\n", m); fclose(f); }
}
static void achui_open(const char *why) {
    if (AUI.on) return;
    memset(&AUI, 0, sizeof AUI);
    AUI.on = 1; AUI.f0 = g_frame; AUI.dirty = 1; AUI.ver = -1; AUI.hv_r = AUI.hv_c = AUI.hv_tb = AUI.hv_pb = -1;
    AUI.fr = g_aui_fr; AUI.fc = g_aui_fc; AUI.want = g_aui_fc;
    AUI.h_back = AUI.h_esc = AUI.h_f = AUI.h_ka = AUI.h_kd = AUI.h_pv = AUI.h_nx = AUI.h_u = AUI.h_d = AUI.h_l = AUI.h_r = AUI.h_sel = 1;   // whatever opened it is held
    AUI.t_u = AUI.t_d = AUI.t_l = AUI.t_r = ~0ULL;
    AUI.ret_tab = C13.tab < C13_NTAB ? C13.tab : 0;    // (the clan page's tab and tiles: where Back returns)
    memcpy(AUI.ret_fr, C13.fr, sizeof AUI.ret_fr); memcpy(AUI.ret_fc, C13.fc, sizeof AUI.ret_fc); memcpy(AUI.ret_roff, C13.roff, sizeof AUI.ret_roff);
    AUI.seen_t = achui_seen_load();
    cl13_sfx();
    push_page("to1/clanach");
    xlog("achui: opened (%s) - pushing to1/clanach", why);
}
// leaving the page: the clan page under it comes back on `tab` (its own tiles as they were, no second intro: g_c13_resume)
static void achui_resume(int tab) {
    g_c13_resume.apply = 1; g_c13_resume.until = g_frame + 10; g_c13_resume.tab = tab;
    memcpy(g_c13_resume.fr, AUI.ret_fr, sizeof g_c13_resume.fr); memcpy(g_c13_resume.fc, AUI.ret_fc, sizeof g_c13_resume.fc);
    memcpy(g_c13_resume.roff, AUI.ret_roff, sizeof g_c13_resume.roff);
}
static void achui_left(const char *how) {
    if (!AUI.on) return;
    AUI.on = 0;
    g_aui_fr = AUI.fr; g_aui_fc = AUI.fc;
    achui_seen_save();
    xlog("achui: closed (%s)", how);
}
static void achui_copy(void) {
    if (g_ach_ver == AUI.ver) return;
    EnterCriticalSection(&g_clan_cs);
    memcpy(&g_aui_v, &g_ach, sizeof g_aui_v);
    LeaveCriticalSection(&g_clan_cs);
    AUI.ver = g_ach_ver; AUI.dirty = 1;
}
static void achui_rows(void) {                         // the non-empty groups in AUI_GRP order, their entries in table order
    const ach_t *A = &g_aui_v;
    int cnt[AUI_NG] = {0}, un[AUI_NG] = {0}, it[AUI_NG][AUI_NI];
    for (int i = 0; i < A->n; i++)
        for (int k = 0; k < AUI_NG; k++)
            if (!strcmp(A->r[i].group, AUI_GRP[k])) { if (cnt[k] < AUI_NI) { it[k][cnt[k]++] = i; if (A->r[i].t) un[k]++; } break; }
    AUI.nr = 0;
    for (int k = 0; k < AUI_NG; k++) {
        if (!cnt[k]) continue;
        int r = AUI.nr++;
        AUI.grp[r] = k; AUI.cnt[r] = cnt[k]; AUI.un[r] = un[k];
        memcpy(AUI.item[r], it[k], sizeof(int) * (size_t)cnt[k]);
    }
    if (AUI.fr < 0) AUI.fr = 0;
    if (AUI.fr >= AUI.nr) AUI.fr = AUI.nr ? AUI.nr - 1 : 0;
    if (AUI.nr && AUI.fc >= AUI.cnt[AUI.fr]) AUI.fc = AUI.cnt[AUI.fr] - 1;
    if (AUI.fc < 0) AUI.fc = 0;
}
static void achui_follow(void) {                       // the row window and the focused row's column window follow the focus
    if (AUI.fr < AUI.row0) AUI.row0 = AUI.fr;
    if (AUI.fr >= AUI.row0 + AUI_ROWS) AUI.row0 = AUI.fr - AUI_ROWS + 1;
    if (AUI.row0 > AUI.nr - AUI_ROWS) AUI.row0 = AUI.nr - AUI_ROWS;
    if (AUI.row0 < 0) AUI.row0 = 0;
    int *o = &AUI.off[AUI.fr];
    if (AUI.fc < *o) *o = AUI.fc;
    if (AUI.fc >= *o + AUI_COLS) *o = AUI.fc - AUI_COLS + 1;
    if (*o > AUI.cnt[AUI.fr] - AUI_COLS) *o = AUI.cnt[AUI.fr] - AUI_COLS;
    if (*o < 0) *o = 0;
}
static void achui_icon(char *b, size_t n, const ach_row_t *r) {
    if (r->t) snprintf(b, n, "streaming/t2r/ach/%s.png", r->id);
    else if (r->hidden) snprintf(b, n, "streaming/t2r/ach/hidden.png");
    else snprintf(b, n, "streaming/t2r/ach/%s-l.png", r->id);
}
static float aui_alpha(int foc, int locked, int hidden) {       // = achieve_widgets.tile_alpha
    int a = hidden ? (foc ? 140 : 95) : foc ? 255 : !locked ? 205 : 165;
    return (float)a / 255.0f;
}
static void aui_scroll_h(const char *base, float x0, float x1, float y_mid, int first, int shown, int n) {     // nr_style.scroll_h <base>T / H
    char p[96];
    int on = n > shown;
    snprintf(p, sizeof p, "%sT", base); ui_visible(p, on);
    snprintf(p, sizeof p, "%sH", base); ui_visible(p, on);
    if (!on) return;
    float a = (float)first / (float)n, b = (float)(first + shown) / (float)n;
    if (b > 1.0f) b = 1.0f;
    nr_rule(p, x0 + (x1 - x0) * a, y_mid, (x1 - x0) * (b - a));
}
static const char *aui_tr(const char *en, char *b, size_t n) { const char *t = loc_tr(en); snprintf(b, n, "%s", t ? t : en); return b; }
// an achievement's title / description in the active language: the loc key "ach.<id>.title" / "ach.<id>.desc" (tools/loc/pl/13-achievements.txt),
// else the daemon's English (the wire format stays English; a new or renamed achievement shows in English until its keys exist)
static const char *aui_ach(const char *id, int desc, const char *en, char *b, size_t n) {
    char k[96]; snprintf(k, sizeof k, desc ? "ach.%s.desc" : "ach.%s.title", id);
    const char *t = loc_tr(k);
    snprintf(b, n, "%s", t && t != k && strcmp(t, k) ? t : en);
    return b;
}
#if __has_include("customize_ach.h")
#include "customize_ach.h"                             // CZ_ACH_UNLOCKS {achievement id, item label} (customize_items.py --header)
#define ACH_HAVE_CZ 1
#endif
static const char *ach_unlocks(const char *id, char *b, size_t n) {    // the CUSTOMIZE items this achievement unlocks, ", "-joined ("" = none)
    b[0] = 0;
#ifdef ACH_HAVE_CZ
    size_t L = 0;
    for (size_t i = 0; i < CZ_ACH_NUNLOCKS; i++)
        if (CZ_ACH_UNLOCKS[i].ach && CZ_ACH_UNLOCKS[i].label && !strcmp(CZ_ACH_UNLOCKS[i].ach, id)) {
            int w = snprintf(b + L, n - L, "%s%s", L ? ", " : "", CZ_ACH_UNLOCKS[i].label);
            if (w < 0 || (size_t)w >= n - L) break;
            L += (size_t)w;
        }
#else
    (void)id; (void)n;
#endif
    return b;
}
static void achui_fill(void) {
    const ach_t *A = &g_aui_v;
    char p[96], t[160], im[96], tr[96], at[160];
    achui_rows();
    achui_follow();
    const cl13_t *V = &g_cl13_view;                    // the frame: the clan page's own snapshot (it stays under this page)
    nr_header(V->ok && V->fk == 'S' ? "SERAPHITE CLAN" : "WLF CLAN", aui_tr("ACHIEVEMENTS", tr, sizeof tr));
    if (V->ok) { nr_week(V->week, V->dow, V->done); nr_week_visible(1); } else nr_week_visible(0);
    nr_clan_tabs(nr_clan_tab_of_page(achui_page_id()), AUI.hv_tb);
    {   // (the pad moves the rows with the d-pad / stick: no ROWS key prompt there)
        static char l0[48], l1[48], l2[48];
        nr_prompt_t pr[3] = {{"menu:prev+menu:next", NULL, aui_tr("CLAN TABS", l0, sizeof l0), 1}, {"W / S", NULL, aui_tr("ROWS", l1, sizeof l1), AUI.nr > AUI_ROWS},
                             {"menu:back", NULL, aui_tr("BACK", l2, sizeof l2), 1}};
        if (g_pad_mode) { pr[1] = pr[2]; nr_prompts(pr, 2); } else nr_prompts(pr, 3);
    }
    int ok = A->ok && A->n > 0;
    ui_visible("anim-group.ldTx", !ok);
    if (!ok) ui_text("anim-group.ldTx", aui_tr("LOADING...", tr, sizeof tr));
    ui_visible("anim-group.rows", ok);
    ui_visible("anim-group.det", ok);
    if (!ok) return;
    int focus_on = 0;
    for (int r = 0; r < AUI_ROWS; r++) {
        int ri = AUI.row0 + r, on = ri < AUI.nr;
        float y = AUI_RY0 + AUI_RP * (float)r, ty = y + AUI_TDY;
        snprintf(p, sizeof p, "anim-group.rows.rw%dTx", r); ui_visible(p, on);
        snprintf(p, sizeof p, "anim-group.rows.rw%dRt", r); ui_visible(p, on);
        snprintf(p, sizeof p, "anim-group.rows.rw%dRl", r); ui_visible(p, on);
        if (on) {
            snprintf(t, sizeof t, "%d | %d", AUI.un[ri], AUI.cnt[ri]);
            snprintf(p, sizeof p, "anim-group.rows.rw%d", r);
            nr_section(p, AUI_X0, AUI_X1, y, aui_tr(AUI_LBL[AUI.grp[ri]], tr, sizeof tr), t, 36.0f);
        }
        snprintf(p, sizeof p, "anim-group.rows.rs%d", r);
        aui_scroll_h(p, AUI_X0, AUI_X1, ty + AUI_BDY + 30.0f + 1.0f, on ? AUI.off[ri] : 0, AUI_COLS, on ? AUI.cnt[ri] : 0);
        for (int c = 0; c < AUI_COLS; c++) {
            int k = on ? AUI.off[ri] + c : 0, vis = on && k < AUI.cnt[ri];
            float x = AUI_X0 + AUI_TP * (float)c;
            snprintf(p, sizeof p, "anim-group.rows.t%d_%d", r, c); ui_visible(p, vis);
            const ach_row_t *e = vis ? &A->r[AUI.item[ri][k]] : NULL;
            int bar = e && e->goal > 1 && !(e->hidden && !e->t);
            snprintf(p, sizeof p, "anim-group.rows.t%d_%dBT", r, c); ui_visible(p, bar);
            snprintf(p, sizeof p, "anim-group.rows.t%d_%dBF", r, c);
            if (!bar) ui_visible(p, 0);
            if (!e) continue;
            int lk = !e->t, hid = e->hidden && !e->t, f = ri == AUI.fr && k == AUI.fc;
            if (bar) { nr_bar(p, x, x + AUI_TW, ty + AUI_BDY + 2.0f, e->t ? 1.0f : (float)e->prog / (float)e->goal); w_alpha(ui_w(p), f ? 1.0f : 150.0f / 255.0f); }
            achui_icon(im, sizeof im, e);
            snprintf(p, sizeof p, "anim-group.rows.t%d_%d.t%d_%dP", r, c, r, c); ui_image(p, im); w_alpha(ui_w(p), aui_alpha(f || (ri == AUI.hv_r && k == AUI.hv_c), lk, hid));
            snprintf(p, sizeof p, "anim-group.rows.t%d_%d.t%d_%dL", r, c, r, c); ui_visible(p, lk && !hid); if (lk && !hid) w_alpha(ui_w(p), f ? 1.0f : 170.0f / 255.0f);
            snprintf(p, sizeof p, "anim-group.rows.t%d_%d.t%d_%dBg", r, c, r, c); w_alpha(ui_w(p), (float)(f ? 215 : 175) / 255.0f);
            snprintf(p, sizeof p, "anim-group.rows.t%d_%d.t%d_%dN", r, c, r, c); ui_visible(p, e->t && e->t > AUI.seen_t);
            if (f) { nr_frame_at("anim-group.rows.foc", x - 6.0f, ty - 6.0f, AUI_TW + 12.0f, AUI_TW + 12.0f, 1); focus_on = 1; }
        }
    }
    if (!focus_on) nr_frame_at("anim-group.rows.foc", 0, 0, 0, 0, 0);
    nr_scroll_v("anim-group.rows.sbV", AUI_SBX, AUI_SBY0, AUI_SBY1, AUI_SBY1 - AUI_SBY0, AUI.row0, AUI_ROWS, AUI.nr);
    // ---- the detail column
    int tot = A->n, un = 0;
    for (int i = 0; i < A->n; i++) if (A->r[i].t) un++;
    snprintf(t, sizeof t, "%d | %d  (%d%%)", un, tot, tot ? un * 100 / tot : 0);
    nr_section("anim-group.det.dTot", AUI_DX0, AUI_DX1, AUI_RY0, aui_tr("UNLOCKED", tr, sizeof tr), t, 36.0f);
    nr_bar("anim-group.det.dTotBF", AUI_DX0, AUI_DX1, AUI_RY0 + 34.0f + 3.0f, tot ? (float)un / (float)tot : 0.0f);
    const ach_row_t *e = AUI.nr ? &A->r[AUI.item[AUI.fr][AUI.fc]] : NULL;
    ui_visible("anim-group.det.dArt", e != NULL);
    if (!e) { ui_visible("anim-group.det.dUnl", 0); return; }
    int lk = !e->t, hid = e->hidden && !e->t;
    achui_icon(im, sizeof im, e);
    ui_image("anim-group.det.dArt", im); w_alpha(ui_w("anim-group.det.dArt"), hid ? 140.0f / 255.0f : 1.0f);
    ui_visible("anim-group.det.dLock", lk && !hid);
    ui_text("anim-group.det.dGrp", aui_tr(AUI_LBL[AUI.grp[AUI.fr]], tr, sizeof tr));
    nr_fit("anim-group.det.dTitle", hid ? "?" : aui_ach(e->id, 0, e->title, at, sizeof at), AUI_DX1 - AUI_DX0, NR_HEAD_PT);
    ui_text("anim-group.det.dDesc", hid ? aui_tr("Hidden achievement. Keep playing.", tr, sizeof tr) : aui_ach(e->id, 1, e->desc, at, sizeof at));
    int bar = !hid;                                    // every shown achievement: N | M + bar (a one-match goal: 0 | 1 / 1 | 1)
    ui_visible("anim-group.det.dBarT", bar); ui_visible("anim-group.det.dCnt", bar);
    if (!bar) ui_visible("anim-group.det.dBarF", 0);
    else {
        int gl = e->goal > 0 ? e->goal : 1, pg = e->t ? gl : e->prog < gl ? e->prog : gl;
        nr_bar("anim-group.det.dBarF", AUI_DX0, AUI_DX1 - 300.0f, AUI_DTY + 230.0f + 3.0f, (float)pg / (float)gl);
        snprintf(t, sizeof t, "%d | %d", pg, gl); ui_text("anim-group.det.dCnt", t);
    }
    if (e->t) {
        static const char *const MO[12] = {"JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"};
        time_t tt = (time_t)e->t; struct tm *lt = localtime(&tt);
        char mo[16];
        if (lt) snprintf(t, sizeof t, "%s %02d %s %d", aui_tr("UNLOCKED", tr, sizeof tr), lt->tm_mday, aui_tr(MO[lt->tm_mon % 12], mo, sizeof mo), lt->tm_year + 1900);
        else snprintf(t, sizeof t, "%s", aui_tr("UNLOCKED", tr, sizeof tr));
    } else snprintf(t, sizeof t, "%s", aui_tr(hid ? "HIDDEN" : "LOCKED", tr, sizeof tr));
    {   // the status chip: accent box when unlocked (STYLE: chip = accent when done), grey when locked, dark when hidden (three chips, one shown)
        static const char *const CH[3] = {"anim-group.det.dChip", "anim-group.det.dChipA", "anim-group.det.dChipD"};
        int ci = e->t ? 1 : hid ? 2 : 0;
        char q[64];
        for (int i = 0; i < 3; i++) {
            snprintf(q, sizeof q, "%sBg", CH[i]); ui_visible(q, i == ci);
            snprintf(q, sizeof q, "%sTx", CH[i]); ui_visible(q, i == ci);
        }
        nr_chip(CH[ci], t, AUI_DX0 + 170.0f, 0.0f, 30.0f);
    }
    ui_text("anim-group.det.dSt", aui_tr("Status:", tr, sizeof tr));
    {   // the CUSTOMIZE items it unlocks (the line's loc key "UNLOCKS: %s" translates the item label as a text capture)
        char u[160], ul[200];
        int on = !hid && ach_unlocks(e->id, u, sizeof u)[0];
        ui_visible("anim-group.det.dUnl", on);
        if (on) { snprintf(ul, sizeof ul, "UNLOCKS: %s", u); ui_text("anim-group.det.dUnl", ul); }
    }
}
static void achui_scan(void) {
    float cx, cy;
    AUI.hv_r = AUI.hv_c = -1;
    AUI.hv_tb = nr_clan_tab_hover();
    AUI.hv_pb = nr_prompt_hover();
    if (!ui_cursor_canvas(&cx, &cy) || cx < AUI_X0 || cy < AUI_RY0 + AUI_TDY) return;
    int c = (int)((cx - AUI_X0) / AUI_TP), r = (int)((cy - AUI_RY0 - AUI_TDY) / AUI_RP);
    float ox = cx - AUI_X0 - AUI_TP * (float)c, oy = cy - AUI_RY0 - AUI_TDY - AUI_RP * (float)r;
    if (c >= AUI_COLS || r >= AUI_ROWS || ox > AUI_TW || oy > AUI_TW) return;
    int ri = AUI.row0 + r;
    if (ri >= AUI.nr || AUI.off[ri] + c >= AUI.cnt[ri]) return;
    AUI.hv_r = ri; AUI.hv_c = AUI.off[ri] + c;
}
static int achui_click_hit(void) {                     // the click gate (ui_click_gate_tick)
    if (!AUI.on) return 0;
    achui_scan();
    return AUI.hv_r >= 0 || AUI.hv_tb != -1 || AUI.hv_pb >= 0;
}
// another clan tab: 0..4 = the clan page under this one on that tab (popped back to it); further extension tabs open over the clan page
static void achui_go(int tab, const char *why) {
    int n = nr_clan_ntabs(), me = nr_clan_tab_of_page(achui_page_id());
    tab = (tab % n + n) % n;
    if (tab == me) return;
    cl13_sfx();
    achui_resume(tab < C13_NTAB ? tab : AUI.ret_tab);
    pop_page();
    achui_left(why);
    if (tab >= C13_NTAB) nr_clan_go(tab, why);
    xlog("achui: tab %d (%s)", tab, why);
}
static void achui_tick(void) {
    uint64_t now = GetTickCount64();
    if (!AUI.seen) { AUI.seen = 1; AUI.ask_at = now; xlog("achui: page up"); }
    if (AUI.ask_at && now >= AUI.ask_at && !g_clan_busy) {          // a fresh table on every opening (asked again until one is here)
        if (ach_ask()) AUI.ask_at = 0; else AUI.ask_at = now + 500;
    }
    if (!AUI.ask_at && AUI.ver == g_ach_ver && !g_aui_v.ok && now - g_ach_rep.at > 3000 && g_frame % 180 == 0) AUI.ask_at = now;
    achui_copy();
    { static int lpd = -1; if (lpd != g_pad_mode) { lpd = g_pad_mode; AUI.dirty = 1; } }   // the prompts follow the device in use
    int up = gu_rep(&AUI.h_u, &AUI.t_u, fnv64("menu-up")), down = gu_rep(&AUI.h_d, &AUI.t_d, fnv64("menu-down"));
    int left = gu_rep(&AUI.h_l, &AUI.t_l, fnv64("menu-left")), right = gu_rep(&AUI.h_r, &AUI.t_r, fnv64("menu-right"));
    int back = menu_edge(fnv64("menu-back"), &AUI.h_back);
    menu_edge(0x6695c5b7921bb5ddULL /* menu-select */, &AUI.h_sel);
    int f_now = game_focused() && (GetAsyncKeyState('F') & 0x8000) != 0, f = f_now && !AUI.h_f; AUI.h_f = f_now;
    int esc_now = game_focused() && (GetAsyncKeyState(VK_ESCAPE) & 0x8000) != 0, esc = esc_now && !AUI.h_esc; AUI.h_esc = esc_now;
    int kq = game_focused() && (GetAsyncKeyState('Q') & 0x8000) != 0, ke = game_focused() && (GetAsyncKeyState('E') & 0x8000) != 0;
    int tab_l = kq && !AUI.h_ka, tab_r = ke && !AUI.h_kd; AUI.h_ka = kq; AUI.h_kd = ke;
    int bp = menu_edge(fnv64("menu-prev"), &AUI.h_pv), bn = menu_edge(fnv64("menu-next"), &AUI.h_nx);
    int wn = wheel_notches();
    int ohv = AUI.hv_r * 4096 + AUI.hv_c * 64 + (AUI.hv_tb + 4) * 8 + AUI.hv_pb + 1;
    achui_scan();
    if (AUI.hv_r * 4096 + AUI.hv_c * 64 + (AUI.hv_tb + 4) * 8 + AUI.hv_pb + 1 != ohv) AUI.dirty = 1;
    int early = g_frame <= AUI.f0 + 10, click = g_click_edge && !early;
    int pb = click ? AUI.hv_pb : -1;                   // a click on a prompt = its key (0 CLAN TABS, 1 ROWS, 2 BACK; the mouse = keyboard prompts)
    if (!early && (back || esc || f || pb == 2)) {
        cl13_sfx();
        achui_resume(AUI.ret_tab);
        if (back) xlog("achui: menu-back");                           // the engine pops the page itself (achui_route sees it go)
        else { pop_page(); achui_left(esc ? "Esc" : f ? "F" : "BACK clicked"); }
        return;
    }
    if (!early) {
        int me = nr_clan_tab_of_page(achui_page_id());
        if (tab_l || bp || (click && AUI.hv_tb == -2)) { achui_go(me - 1, bp ? "left bumper" : tab_l ? "Q" : "Q clicked"); return; }
        if (tab_r || bn || pb == 0 || (click && AUI.hv_tb == -3)) { achui_go(me + 1, bn ? "right bumper" : tab_r ? "E" : "E clicked"); return; }
        if (click && AUI.hv_tb >= 0 && AUI.hv_tb != me) { achui_go(AUI.hv_tb, "tab clicked"); return; }
    }
    int fr = AUI.fr, fc = AUI.fc;
    if (AUI.nr) {
        if (wn > 0) up = 1;
        if (wn < 0) down = 1;
        if (up && fr > 0) { fr--; fc = AUI.want - AUI.off[AUI.fr] + AUI.off[fr]; }      // (the same screen column in the row above)
        if (down && fr + 1 < AUI.nr) { fr++; fc = AUI.want - AUI.off[AUI.fr] + AUI.off[fr]; }
        if (fr != AUI.fr) { if (fc >= AUI.cnt[fr]) fc = AUI.cnt[fr] - 1; if (fc < 0) fc = 0; }
        if (left && fc > 0) { fc--; AUI.want = fc; }
        if (right && fc + 1 < AUI.cnt[fr]) { fc++; AUI.want = fc; }
        if (click && AUI.hv_r >= 0) { fr = AUI.hv_r; fc = AUI.want = AUI.hv_c; }
    }
    if ((fr != AUI.fr || fc != AUI.fc) && AUI.nr) {
        AUI.fr = fr; AUI.fc = fc; AUI.dirty = 1; cl13_sfx();
    }
    if (AUI.dirty || g_frame % 30 == 0) { AUI.dirty = 0; achui_fill(); }
}
// the page is on top -> its tick; it left the top (menu-back popped it, or it never came up) -> closed (the clan page resumes under it)
static int achui_route(uint64_t top) {
    // A match load closes the page first: each Gui2 page keeps its engine processes through the map load (menu ~7300, the load
    // ~+2060, engine limit 10000: "We have more than 10000 Processes!"). The page never pops itself: with the match flow on,
    // feature_matchflow pops the clan pages (this one included, nr_clan_xtab_route); with the flow off, the private lobby's load gate
    // (pl_load_gate) does. Only a log line here.
    {   static int lst = -1; uint8_t *o = lobby_obj(); int st = o ? o[0x2b80] : -1;
        if (st != lst && st >= 4 && st <= 6 && page_on_stack(achui_page_id()))
            xlog("achui pop skipped: %s owns (state %d, top %llx)", g_no_matchflow ? "pl gate" : "matchflow", st, (unsigned long long)top);
        lst = st;
    }
    if (!AUI.on) return 0;
    if (top && top == achui_page_id()) { achui_tick(); return 1; }
    if (AUI.seen && top && page_on_stack(achui_page_id())) return 1;   // a page over it: paused, ticks again once it is back on top
    if (AUI.seen || g_frame > AUI.f0 + 120) {
        achui_left(AUI.seen ? "page popped" : "never reached the top");
        if (top && top != cl13_page_id() && g_c13_resume.until && g_frame <= g_c13_resume.until && !page_on_stack(cl13_page_id())) {      // (menu-back popped the clan page too: it comes back)
            push_page("to1/clan13"); xlog("achui: the clan page went with it - pushed again");
        }
    }
    return AUI.on;
}
static void achui_frame(void) {                        // once a frame (achc_tick): the tab registration + the page
    static int reg;
    if (!reg) { reg = 1; int t = nr_clan_xtab_add("ACHIEVEMENTS", achui_avail, achui_open, achui_page_id); xlog("achui: clan tab %d", t); }
    achui_route(top_page());
}
// ------------------------------------------------------------------ the unlock card (styled like the game's top-left notifications such as New Journal
// Entry added; the text says Unlocked Achievement: (achievement)). The widget is TLOU2's own SP card hud-notifications/new-item-root + hud-tutorial/tutorial-bg,
// copied onto the menu pages (achieve_widgets.add_ach_card: group achNt, top centre, 0.8 size). The SP root timeline cannot run on a page, so it is played here:
// slide + fade in 0.3 s, hold 4.5 s, fade out 0.9 s, its chime (achc_chime). One card at a time from the
// queue achieve.c fills (unlocks newer than t2r-ach-seen.txt); it runs while one of the card pages is on top, or during a match on the HUD (the
// live unlocks; the same card in hud-root). Elsewhere the time stops and the card is written again in the next place. Log "achui: card".
#define ACHC_IN 300.0f
#define ACHC_HOLD 4500.0f
#define ACHC_OUT 900.0f
#define ACHC_X 1440.0f                                 // = achieve_widgets.CARD_X / CARD_Y / CARD_S (X: the widget's start; each card is placed at ACHC_CX): the empty band at the top centre of every card
#define ACHC_Y 115.0f                                  // page (right of the page title, above the clan tabs, left of the week / ONLINE block);
#define ACHC_S 0.8f                                    // at the SP spot (left edge, y 300) it covered the WEEK n: DAY n header of the main menu
#define ACHC_NP 4                                    // (the menu card pages; ACHC_NP is also the match HUD's bit in shown_mask)
#define ACHC_CX 1920.0f                                // the icon + text centred on the screen
#define ACHC_ICON_L 128.0f                             // and the box sized + centred round them. Card units (before ACHC_S): the icon's left edge (fader margin),
#define ACHC_TEXT_L 324.0f                             // the text's (icon 146 + flow spacing 50), measured on an A/B screenshot
#define ACHC_BOX_W 1112.0f                             // achNtBg's own width (achieve_widgets: fader 1048 + 64, no overhang), its pivot x 32 = centre at 556
#define ACHC_TXT_K 1.06f                               // on-screen text width / gu_est (screenshot: "Unlocked Achievement: RANK 1" 789 units, est 744)
// The card's chime (the SP journal event is quiet and play-sound takes no volume, so the chime is
// the MP rewards level-up sound): ui-mp-meta-rewards-level-up of gbl-hud-rl.bnk, ripped by
// tools/rip_ach_chime.py, played 2D through the PCM mixer once when a card starts (menu page or match HUD). ACHC_CHIME_RMS = the level of its
// loudest 0.4 s at full sfx volume (the post-match count loop sits at ~0.03); it follows the game's sfx slider. Log "achui: chime".
#include "ach_chime.h"
__asm__(".section .rdata,\"dr\"\n.balign 4\n.globl achc_chime_blob\nachc_chime_blob:\n.incbin \"ach_chime.pcm\"\n.text\n");
extern const int16_t achc_chime_blob[];
#define ACHC_CHIME_RMS 0.06f
static void achc_chime(const char *id) {
    static int nl;
    float g = ACHC_CHIME_RMS / ACH_CHIME_LOUD * sfx_user_volume();
    int ok = pcm_play_rate(achc_chime_blob, ACH_CHIME_N, g, ACH_CHIME_RATE);
    if (LOGCAP(nl, 40)) xlog("achui: chime for %s (gain %.2f) -> %s", id, (double)g, ok ? "playing" : "mixer refused");
}
typedef struct { char title[48], desc[112], id[20]; } achc_item_t;
static struct { int n, st, snd, shown_mask; achc_item_t q[ACH_TOAST_Q]; uint64_t t0, last, page; float tw; } ACC;   // tw: the card's text width
// (not on clan-postmatch: its UNLOCKS stage lists the match's achievements, pmunlock.c; a card waits for the next card page)
static const char *const ACHC_PAGES[ACHC_NP] = {"main-menu", "find-match-menu", "clan13x", "clanach"};
static int achc_page_idx(uint64_t top) {
    static uint64_t id[ACHC_NP];
    if (!top) return -1;
    for (int i = 0; i < ACHC_NP; i++) { if (!id[i]) id[i] = page_id(ACHC_PAGES[i]); if (id[i] == top) return i; }
    return -1;
}
// Where the card is: on a card
// page (under its anim-group), or during a match on the HUD (the same card in hud-root: achieve_widgets.add_ach_card_hud), where achieve.c's
// live unlocks arrive. achc_w resolves a card widget in the current place; the texts are written once per card and place, so straight
// through the engine setters (the ui_text cache is told, like ui_text does).
static int g_achc_hud;
static uint64_t achc_w(const char *rel) {
    char p[96];
    if (g_achc_hud) { snprintf(p, sizeof p, "achNt%s", rel); return hudw(p); }
    snprintf(p, sizeof p, "anim-group.achNt%s", rel);
    return ui_w(p);
}
static void achc_set(const char *rel, const char *s, int image) {
    uint64_t w = achc_w(rel);
    if (!w) return;
    g_ui_own = 1;
    ((fn_settext_t)VMA(image ? 0x180068260 : 0x180064450))(w, s);     // (the text hook translates the frame: loc template)
    g_ui_own = 0;
    ui_wc_forget(image ? g_ui_ic : g_ui_tc, w);
}
static void achc_show(int on) {
    uint64_t a[2] = {achc_w(""), (uint64_t)on};
    if (a[0] && ui_prop_due(1, a[0], 0x200000000ULL | (uint64_t)(on != 0))) dc_call(0xccf99aa7589d1af9ULL /* gui2-set-widget-visible */, 2, a);
}
static void achc_write(const achc_item_t *it) {
    char t[160], im[96], a[160];
    snprintf(t, sizeof t, "Unlocked Achievement: %s", aui_ach(it->id, 0, it->title, a, sizeof a));
    achc_set(".achNtFd.achNtGr.achNtTg.achNtName", t, 0);
    float tw = gu_est(t, 41.0f), sc = tw > 1000.0f ? 1000.0f / tw : 1.0f;   // a 740 fit box shrank most titles below
    if (sc < 0.6f) sc = 0.6f;                                               // the description's size; 1000 now, the box grows with the text
    uint64_t nw = achc_w(".achNtFd.achNtGr.achNtTg.achNtName");
    if (nw) w_scale(nw, sc, sc);
    if (tw > 1000.0f) tw = 1000.0f;
    const char *ds = aui_ach(it->id, 1, it->desc, a, sizeof a);
    float dw = gu_est(ds, 41.0f); if (dw > 740.0f) dw = 740.0f;
    char u[160], d2[300];
    if (ach_unlocks(it->id, u, sizeof u)[0]) {        // second line: the CUSTOMIZE items it unlocks (loc splits at the newline)
        snprintf(d2, sizeof d2, "%s\nUNLOCKS: %s", ds, u);
        float uw = gu_est(d2 + strlen(ds) + 1, 41.0f); if (uw > 740.0f) uw = 740.0f;
        if (uw > dw) dw = uw;
        ds = d2;
    }
    ACC.tw = ACHC_TXT_K * (tw > dw ? tw : dw);
    achc_set(".achNtFd.achNtGr.achNtTg.achNtAct", ds, 0);
    snprintf(im, sizeof im, "streaming/t2r/ach/%s.png", it->id);
    achc_set(".achNtFd.achNtGr.achNtIc", im, 1);
}
static void achc_drop(const char *id) {            // the post-match UNLOCKS stage lists it: no card for it
    for (int i = 0; i < ACC.n; i++) {
        if (strcmp(ACC.q[i].id, id)) continue;
        if (i == 0 && ACC.st) { achc_show(0); ACC.st = 0; ACC.shown_mask = 0; }   // (achc_w: the place it is in now)
        memmove(ACC.q + i, ACC.q + i + 1, sizeof ACC.q[0] * (size_t)(ACC.n - i - 1)); ACC.n--; i--;
    }
}
static void achc_tick(void) {
    achui_frame();
    if (ach_off()) return;
    uint64_t now = GetTickCount64();
    if (g_ach_toast_n) {                               // the worker's queue -> ours
        EnterCriticalSection(&g_clan_cs);
        for (LONG i = 0; i < g_ach_toast_n && ACC.n < ACH_TOAST_Q; i++) {
            achc_item_t *d = &ACC.q[ACC.n++];
            snprintf(d->title, sizeof d->title, "%s", g_ach_toast[i].title); snprintf(d->desc, sizeof d->desc, "%s", g_ach_toast[i].desc);
            snprintf(d->id, sizeof d->id, "%s", g_ach_toast[i].id);
        }
        InterlockedExchange(&g_ach_toast_n, 0);
        LeaveCriticalSection(&g_clan_cs);
    }
    {   // test aid (A/B screenshots): t2r-ach-test.txt next to the exe, one achievement id per line -> their cards (again whenever the file is saved again)
        static uint64_t chk; static FILETIME mt;
        if (now - chk > 2000) {
            chk = now;
            WIN32_FILE_ATTRIBUTE_DATA fa;
            if (GetFileAttributesExA("t2r-ach-test.txt", GetFileExInfoStandard, &fa) && CompareFileTime(&fa.ftLastWriteTime, &mt)) {
                mt = fa.ftLastWriteTime;
                FILE *f = exe_side_open("t2r-ach-test.txt", "r");
                char ln[64];
                while (f && fgets(ln, sizeof ln, f) && ACC.n < ACH_TOAST_Q) {
                    ln[strcspn(ln, "\r\n ")] = 0;
                    if (!ln[0]) continue;
                    achc_item_t *d = &ACC.q[ACC.n++];
                    snprintf(d->id, sizeof d->id, "%s", ln); snprintf(d->title, sizeof d->title, "%s", ln); d->desc[0] = 0;
                    EnterCriticalSection(&g_clan_cs);
                    for (int i = 0; i < g_ach.n; i++) if (!strcmp(g_ach.r[i].id, ln)) { snprintf(d->title, sizeof d->title, "%s", g_ach.r[i].title); snprintf(d->desc, sizeof d->desc, "%s", g_ach.r[i].desc); }
                    LeaveCriticalSection(&g_clan_cs);
                    xlog("achui: test card %s queued (t2r-ach-test.txt)", ln);
                }
                if (f) fclose(f);
            }
        }
    }
    // the place: the match HUD while the match runs (its hud-root has the card), else a card page on top. ACHC_NP = the HUD's bit in shown_mask;
    // key = what the card was last written into (a page id, or the HUD of this match: hud-root is rebuilt per level)
    static int was_match; static uint64_t hud_gen;
    int inm = match_substate() == 6;
    if (inm && !was_match) hud_gen++;
    was_match = inm;
    g_achc_hud = 1;
    int hud = inm && achc_w("") != 0;
    g_achc_hud = hud;
    uint64_t top = hud ? 0x4855440000000000ULL + hud_gen : top_page();
    int pi = hud ? ACHC_NP : achc_page_idx(top);
    uint64_t dt = ACC.last ? now - ACC.last : 0; ACC.last = now;
    if (pi < 0) { if (ACC.st) ACC.t0 += dt; return; }          // not a card page: the card's time stands still
    uint64_t root = achc_w("");
    if (!ACC.st) {
        if (ACC.shown_mask & (1 << pi)) { if (root) achc_show(0); ACC.shown_mask &= ~(1 << pi); }   // a card left over on a page under the one it ended on
        if (!ACC.n || !root) return;
        ACC.st = 1; ACC.t0 = now; ACC.snd = 0; ACC.page = 0;
        xlog("achui: card %s (%s), %d queued, on the %s", ACC.q[0].id, ACC.q[0].title, ACC.n - 1, hud ? "match HUD" : "menu page");
    }
    if (!root) { ACC.t0 += dt; return; }
    if (ACC.page != top) {                              // a new card page / match HUD: written while hidden, shown on the next frame
        achc_show(0); achc_write(&ACC.q[0]); ACC.page = top; ACC.t0 += dt; return;
    }
    float e = now > ACC.t0 ? (float)(now - ACC.t0) : 0.0f;   // t0 can sit a tick ahead of now (the dt added on the first frame; 16 ms timer steps): no wrap
    if (e >= ACHC_IN + ACHC_HOLD + ACHC_OUT) {
        achc_show(0); ACC.shown_mask &= ~(1 << pi);
        memmove(ACC.q, ACC.q + 1, sizeof ACC.q[0] * (size_t)(ACC.n - 1)); ACC.n--; ACC.st = 0;
        return;
    }
    if (!ACC.snd) { ACC.snd = 1; achc_chime(ACC.q[0].id); }
    float a = e < ACHC_IN ? e / ACHC_IN : e < ACHC_IN + ACHC_HOLD ? 1.0f : 1.0f - (e - ACHC_IN - ACHC_HOLD) / ACHC_OUT;
    float u = e < ACHC_IN ? 1.0f - e / ACHC_IN : 0.0f;
    float cl = ACHC_ICON_L, cr = ACHC_TEXT_L + ACC.tw, cc = (cl + cr) / 2;    // the icon + text span (card units)
    float bw = (cr - cl) / 0.6f; if (bw < 900.0f) bw = 900.0f;             // the box: the content inside its middle 60% (the mask is near full there)
    uint64_t bg = achc_w(".achNtFd.achNtBg");
    if (bg) { w_scale(bg, bw / ACHC_BOX_W, 1.0f); w_pivot(bg, 32.0f + cc - ACHC_BOX_W / 2, 0.0f); }   // (scaled about its centre pivot)
    w_scale(root, ACHC_S, ACHC_S);
    w_pivot(root, ACHC_CX - ACHC_S * cc - 90.0f * u * u * u, ACHC_Y);  // (ease out: the card slides in from the left as the SP sweep reveals it)
    w_alpha(root, a);
    achc_show(1); ACC.shown_mask |= 1 << pi;
}
