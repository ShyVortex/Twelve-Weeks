// clan13.c - the in-game CLAN page. Included after gearup13.c (it reuses its fit / fade / repeat helpers). The widgets are tools/features/clan13_widgets.py
// (page to1/clan13, built from the same Builder as to1/gearup13: same backdrop, fonts, colours, footer prompts); like the match flow and GEAR UP pages this one is driven
// ENTIRELY from the tick and every text / icon / visibility goes through the dedup writers (ui_text, ui_image, ui_visible, w_alpha: no per-frame rewrites of a value).
// The look target is the launcher's CLAN tab (clan-cast-proof4.mp4): WLF / WEEK n: DAY n with the day-progress line, STATUS UPDATES, SUPPLIES, CAMP MORALE, SURVIVORS grid, RAIDS.
//
// Data: daemon op 0xB6 [token][lang][section][seen journal id][seen raid day] -> 0xB7 (tools/clan_ingame.py; parsed by clan13.h into g_cl13 by the clan worker):
// section 1 ROSTER, 2 JOURNAL, 3 RAIDS + supplies, 4 STATUS UPDATES, 5 MATCH STATS of one raid (the raid's day in the "seen raid day" slot; asked only when the list is opened). The page asks the sections the open tab needs first, then the others, again every 30 s, and shows LOADING /
// the server error until they are there.
// Tabs of ONE page (a second instance of a page on the stack breaks it; a widget page cannot clip a scroll): OVERVIEW (status cards, supplies, camp morale), SURVIVORS (4 x 5 grid
// + the focused member), RAIDS (4 rows + the focused raid), JOURNAL (week pages - < WEEK n OF 12 > with one row per clan day, and the focused day's entry: headline,
// the day's facts, its paragraphs; daemon section 6, tools/clan_journal.py. Left / right (A / D, arrows, d-pad, stick) or a click on < > turn the week, up / down / wheel / click pick
// the day and run on into the next week at the ends).
// Keys: W / S move (OVERVIEW and SURVIVORS: up / down by row), Q / E and the bumpers LB / RB (menu-prev / next) change tab, A / D / the arrow keys / stick / d-pad move across a grid row,
// SELECT on a status card = the journal, menu-back / Esc = out. F / the pad's menu-action (Triangle / Y), SELECT (Enter / A) and the PLAYER STATS button in the RAIDS header = the player stats of the focused raid (US / THE ENEMY, "MOST <stat>" awards, faces; t2r-clan-xs-old.txt = the old flat MATCH STATS list) (section 5: every player of that
// match with team and stats; F / BACK / Esc / B closes the list, not the page). Mouse: hover lights, click focuses / opens a tab, wheel scrolls.
//
// MOTION (re/clan-ui-motion.md, translated to what a widget page can do: alpha + position + scale written per frame by a small tween table, all eased out with the launcher's
// curve): the page fades in 220 ms and out 140 ms; a tab's blocks enter staggered (left / right / up 96 units + fade, 560 ms, step 45-110 ms, spread capped at 720 ms); the old tab
// fades out in 90 ms; bars grow from their left edge (header day line, camp morale, raid bars: 900 ms), supply numbers and the stock days count up (700 ms), the raid verdict pops;
// the detail panels (focused member / raid / journal thread) cross-fade (80 ms out, 150 ms in with an 8 unit slide) when the selection changes; focus fills / frames ease
// (gu_fade); every NEW thing is simply part of its row's entrance. t2r-gu-noanim.txt = no tweens (the plain page).
// Portraits: the head of the member in the asked expression (streaming/t2r/icons/c13p-<model>_<expr>.png), soft edges baked in, no tile; t2r-no-clan-portraits.txt = none.
// Entry: the CLAN row of the MP main menu / FINDING MATCH menu with a living clan (select / click, cl13_open_check, called from feature_clan). NEW markers: the highest journal id / raid day seen is kept in
// t2r-clan13-seen.txt next to the exe. t2r-no-clan13.txt next to the exe: off. Log prefix "clan13:".
#define C13_ST 4
#define C13_OVST 2                       // the overview shows the newest 2 status cards (one row): the rest is in the journal; room for SUPPLIES / CAMP / RECENT below
#define C13_SV_N 20
#define C13_JD_ROWS 7                    // JOURNAL: day rows of the shown week (clan13_widgets.py NJD) and their geometry
#define C13_JD_Y0 540.0f
#define C13_JD_DY 176.0f
#define C13_JD_H 166.0f
#define C13_JP 5                         // paragraph slots of the reading pane (NJP); pane x / width, first paragraph top, bottom limit, body point size, line pitch, caption height, gap
#define C13_JT_X 2400.0f                  // = clan13_widgets.py JT_* (the detail column right of the week rows)
#define C13_JT_W 1300.0f
#define C13_JT_Y0 900.0f
#define C13_JT_Y1 1880.0f
#define C13_JT_PT 33.0f
#define C13_JT_LINE 57.0f                // (the game's menu face: a line is ~1.71 x the point size tall - measured on CHOOSE YOUR SIDE, tools/features/widget_preview.py)
#define C13_JT_CAP_H 44.0f
#define C13_JT_GAP 30.0f
#define C13_RDS_ROWS 4
#define C13_NTAB 5
#define C13_GR 14                        // 2D views: rows per tab grid (roles / weeks)
#define C13_MS_ROWS 8
#define NBAR_C 4
#define C13_REFRESH_MS 30000
#define C13_XF_MS 150                    // a tab switch: the old tab fades out while the new one fades in (NR: ~9 frames, a true crossfade; nothing is written or replayed)
#define C13_GATE_MS 100                  // the page's first reveal waits for the preloaded art (NR re-sets an image ~100 ms after the first set)
// Gui2 image budget (t2r-ext.c g2_filled): the engine keeps at most 32 different on-screen images. The page itself (backdrops,
// glyphs, a tab's portraits and icons) plus the 32 always-visible preload widgets went past that with a big roster (37 members: the guard evicted a drawn
// image every 1-3 frames from 0.6 s after the page opened) and the overflowing images took turns vanishing (the clan page flicker). Now the strip preloads in waves while the table has room and
// is hidden for the rest of the visit once the table is nearly full; a tab crossfade (two tabs drawn) is cut short when the table is nearly full.
#define C13_G2_RETIRE 24                 // filled slots at which the preload strip goes away
#define C13_PRE_WAVE 6                   // preload images asked per wave
#define C13_PRE_GAP_F 20                 // frames between waves
#define C13_G2_XFCUT 30                  // filled slots at which a running tab crossfade ends at once
#define C13_DET_GAP_MS 400               // detail panel: no new cross-fade within this time after the last one ended (held W / S repeats every 110 ms: the panel strobed ~9 times a second)
enum { T_OV, T_SV, T_RD, T_JR, T_MS };
static int cl13_flicker_old(void) {      // t2r-clan13-flicker-old.txt next to the exe: the old behaviour (strip always drawn, crossfade always full, a detail cross-fade on every focus step)
    static int on = -1; static uint64_t chk;
    uint64_t n = GetTickCount64();
    if (on < 0 || n - chk > 5000) {
        chk = n; FILE *f = exe_side_open("t2r-clan13-flicker-old.txt", "r"); int o = f != NULL; if (f) fclose(f);
        if (o != on) xlog("clan13: image budget / detail rate cap %s", o ? "OFF (t2r-clan13-flicker-old.txt)" : "on");
        on = o;
    }
    return on;
}
static int g_cl13_off = -1;
static uint64_t cl13_page_id(void) { static uint64_t id; if (!id) id = page_id("clan13"); return id; }
static int g_c13_test; static uint64_t g_c13_test_ms;   // t2r-clan-test.txt (cl13_open_check)
static uint64_t cl13x_page_id(void) { static uint64_t id; if (!id) id = page_id("clan13x"); return id; }   // PLAYER STATS (its own page: clan13.widget is at gui2's single page limit)
static struct { int on, seen, post, h_sel; uint64_t f0; int h_act, h_f, h_esc; } g_c13x;                                   // the stats page was pushed / reached the top
#define C13_FXMAX 140
typedef struct { char path[104]; float bx, by; int kind; float delay; uint64_t w; int done; } c13fx_t;      // an entrance: kind 1 left, 2 right, 3 up, 4 down, 5 pop (fade + small rise), 6 fade
typedef struct { char path[104]; float frac, delay; uint64_t w; int done; float kx, ky; int pin; } c13gr_t;  // a bar growing from its left edge (pin: also moves a marker leaf at kx, ky)
typedef struct { char path[104]; int val, from, cur; char fin[96]; float delay; uint64_t t0, wr_f; int done; } c13cn_t;   // a number counting (cur = what the widget shows, -1 none yet), its final text; lives for the whole page visit (not per tab entrance)
static struct {
    int ms_auto, up, tab, prev_tab, foc[C13_NTAB], off[C13_NTAB], dirty, closing, stage;
    uint64_t enter_ms, back_f, click_f, sfx_ms, t_u, t_d, t_l, t_r, t0, tab_t0, out_t0;
    int h_sel, h_u, h_d, h_l, h_r, h_back, h_esc, h_pv, h_nx, h_ka, h_kd;
    int hv_row, hv_tab, hv_back, hv_sel, hv_prev, hv_next;                  // the element under the cursor (cl13_scan)
    uint64_t next_ask[8], ok_at[8]; int seen_ver[8], ask_ver[8], tries[8];
    int jw, jr_init, hv_jp, hv_jn;                                  // JOURNAL: the week shown (0 = the newest), the first fill put the focus on the newest entry, the cursor is over < / >
    int xs_open, xs_day, xs_win, xs_got, xs_wait, xs_tries, h_act, h_f, hv_act; uint64_t xs_next, xs_t0; int xs_post; char xs_map[32];      // (xs_post: the page is the POST-MATCH SCOREBOARD, cl13_post_open) the MATCH STATS list of a raid (F / the pad's menu-action on RAIDS)
    long seen_jid; int seen_day; int seen_loaded;
    cl13_t *V;                                                      // the snapshot the page draws from
    int played[C13_NTAB];                                           // the tab's entrance has run this visit (entrances and counts play ONCE per Clan UI opening, not on every tab switch)
    int fx_pending, fx_first, shown_prev;                           // an entrance is wanted after the next fill; the page's first one also brings in the header
    int hd_done;                                                    // the header's day-progress bar grew once this visit: later fills (tab switches) write it plain
    int det_key, det_ph, det_hold; uint64_t det_t0;                 // detail panel cross-fade
    int nfx, ngr, ncn; c13fx_t fx[C13_FXMAX]; c13gr_t gr[48]; c13cn_t cn[24];
    int pre_i, pre_ic, intro_played, sw, quiet, hd_shown;          // icons preloaded; the page's one entrance has run; tab switches so far; closing (no more writes); the header showed data
    int pre_ick, pre_off, g2_peak, g2_peak_tab, xf_cut; uint64_t pre_wave_f, det_last; LONG ev0;      // Gui2 image budget (cl13_g2_tick): icons preloaded so far, the strip retired,
                                                                    // the visit's table peak, crossfades cut short, the last preload wave, the end of the last detail cross-fade, evictions at entry
    int fr[C13_NTAB], fc[C13_NTAB], roff[C13_NTAB], want[C13_NTAB], coff[C13_NTAB][C13_GR], hv_r, hv_c, hv_pb, hv_tb;   // 2D views: focus row / column, row window, wanted column, column window per row; under the cursor: tile (row in the window, column), prompt, tab
    int ms_rows[10], ms_n, ms_chosen, ms_tries, ms_init; uint64_t ms_chosen_at;                 // the MISSIONS tab: the pick (the same 0xEF choice feature_missions always sent)
} C13;
static cl13_t g_cl13_view;                                          // (the snapshot's storage: 45 KB, not on the stack)
static int cl13_enabled(void) {
    if (g_cl13_off < 0) { FILE *f = exe_side_open("t2r-no-clan13.txt", "r"); g_cl13_off = f != NULL; if (f) fclose(f); xlog("clan13: in-game CLAN page %s", g_cl13_off ? "off (t2r-no-clan13.txt)" : "on"); }
    return !g_cl13_off;
}
static int cl13_portraits_on(void) {                                  // ON by default; t2r-no-clan-portraits.txt = off
    static int on = -1; static uint64_t chk;
    uint64_t n = GetTickCount64();
    if (on < 0 || n - chk > 5000) { chk = n; FILE *f = exe_side_open("t2r-no-clan-portraits.txt", "r"); on = f == NULL; if (f) fclose(f); }
    return on;
}
static void cl13_sfx(void) {                                          // the menu's focus sound, at most every 150 ms (NR's hfx-ui-cycle floor)
    uint64_t now = GetTickCount64();
    if (now - C13.sfx_ms >= 150) { C13.sfx_ms = now; ui_sfx("sfx-cycle"); }
}
// ------------------------------------------------------------------ small writers
static float cl13_est(const char *t, float pt) { return gu_est(t, pt); }
#define cl13_text(fmt, i, t) do { char p_[128]; snprintf(p_, sizeof p_, fmt, (i)); ui_text(p_, (t)); } while (0)
// gu_est (GEAR UP's per-character widths) runs about 8 % under the game's real menu face with letter spacing (the overlap audit measures the real face): every fit and clip here leaves that margin
// Polish letters were capitalized in the clan UI: the journal headline arrives upper case (daemon str.upper(), so Ą Ć Ę Ł Ń Ó Ś Ź Ż too) and was shown
// as a sentence by lowering only A-Z: the Polish capitals (UTF-8 C3 93, C4 84.., C5 81..) stayed capital inside the lowercase words. The pairs differ by +1 in the
// second byte (same length), so the case is flipped in place. up = 1: lower -> upper (mission names / units in capitals), 0: upper -> lower.
static void cl13_case_pl(char *s, int up) {
    for (uint8_t *p = (uint8_t *)s; *p; p++) {
        if (p[0] == 0xC3 && (p[1] == (up ? 0xB3 : 0x93))) { p[1] = up ? 0x93 : 0xB3; p++; continue; }
        if (p[0] == 0xC4 && p[1]) {
            static const uint8_t L[] = {0x85, 0x87, 0x99};                                  // ą ć ę (capitals = lower - 1)
            for (unsigned i = 0; i < sizeof L; i++) if (p[1] == (up ? L[i] : L[i] - 1)) { p[1] = up ? L[i] - 1 : L[i]; break; }
            p++; continue;
        }
        if (p[0] == 0xC5 && p[1]) {
            static const uint8_t L[] = {0x82, 0x84, 0x9B, 0xBA, 0xBC};                      // ł ń ś ź ż
            for (unsigned i = 0; i < sizeof L; i++) if (p[1] == (up ? L[i] : L[i] - 1)) { p[1] = up ? L[i] - 1 : L[i]; break; }
            p++; continue;
        }
    }
}
// a headline as a sentence: the first letter stays, the rest lower case (ASCII and Polish)
static void cl13_lower_tail(char *t) {
    uint8_t *q = (uint8_t *)t;
    if (*q) { q++; while ((*q & 0xC0) == 0x80) q++; }                                       // (the first character may be a 2-byte Polish capital)
    for (char *r = (char *)q; *r; r++) if (*r >= 'A' && *r <= 'Z') *r = (char)(*r + 32);
    cl13_case_pl((char *)q, 0);
}
static void cl13_fit(const char *path, const char *t, float box, float pt) { gu_fit(path, t, box * 0.92f, pt); }
static void cl13_clipped(const char *path, const char *src, float boxw, float pt, int lines) {
    char b[700];
    cl13_clip(b, sizeof b, src ? src : "", boxw * 0.88f, pt, lines, cl13_est);
    ui_text(path, b);
}
static void cl13_clipped_long(const char *path, const char *src, float boxw, float pt, int lines) {     // the journal's detail pane: a whole day entry (~1500 chars) wrapped in up to `lines` lines
    static char b[2200];
    cl13_clip(b, sizeof b, src ? src : "", boxw * 0.88f, pt, lines, cl13_est);
    ui_text(path, b);
}
static int g_cl13_pic_logged;                                       // one "portrait <path>" line per page open
// Portrait gate (a blue square for ~4 frames; NR re-sets the image ~100 ms after the first set): a new slot stays hidden until 100 ms after its image was set, then the SAME image is
// set again (bypassing the write dedup) and the slot is shown. A slot whose face changes later (focus, refresh) swaps the image only - no visibility toggle - and gets the 100 ms re-set too.
typedef struct { char path[120]; char img[100]; uint64_t set_ms; int st; } c13pic_t;      // st 0 hidden, waiting for its re-set; 1 shown; 2 shown, re-set due
static c13pic_t g_c13_pic[48];
static int g_c13_npic;
static void cl13_pic_reset(void) { g_c13_npic = 0; }
static void cl13_pic_tick(uint64_t now) {
    for (int i = 0; i < g_c13_npic; i++) {
        c13pic_t *q = &g_c13_pic[i];
        if (q->st == 1 || !q->img[0] || now - q->set_ms < 100) continue;
        g_ui_text_raw = 1; ui_image(q->path, q->img); g_ui_text_raw = 0;
        if (q->st == 0) ui_visible(q->path, 1);
        q->st = 1;
    }
}
static void cl13_pic(const char *base, const char *pid) {          // the portrait slot "<base>Im": the member's head in the expression asked (the daemon fitted it to what the head has), else nothing
    char p[200], img[160], a[16], s[16], m[16], e[20];
    snprintf(p, sizeof p, "%sIm", base);
    c13pic_t *q = NULL;
    for (int i = 0; i < g_c13_npic; i++) if (!strcmp(g_c13_pic[i].path, p)) { q = &g_c13_pic[i]; break; }
    if (!cl13_portraits_on() || !pid || !pid[0] || sscanf(pid, "%15[^/]/%15[^/]/%15[^/]/%19s", a, s, m, e) != 4) {
        ui_visible(p, 0);
        if (q) { q->img[0] = 0; q->st = 0; }                        // (a face that comes later is gated again)
        return;
    }
    snprintf(img, sizeof img, "streaming/t2r/icons/c13p-%s_%s.png", m, e);   // = make_icons.clan13_portraits
    if (!g_cl13_pic_logged) { g_cl13_pic_logged = 1; xlog("clan13: portrait %s (from id %s)", img, pid); }
    if (!q) {
        if (g_c13_npic >= 48 || strlen(p) >= sizeof q->path || strlen(img) >= sizeof q->img) { ui_image(p, img); ui_visible(p, 1); return; }
        q = &g_c13_pic[g_c13_npic++];
        snprintf(q->path, sizeof q->path, "%s", p); q->img[0] = 0; q->st = 0; q->set_ms = 0;
        ui_visible(p, 0);
    }
    if (strcmp(q->img, img)) {                                      // a new face for the slot
        snprintf(q->img, sizeof q->img, "%s", img);
        ui_image(p, img);
        q->set_ms = GetTickCount64();
        if (q->st == 1) q->st = 2;                                  // (shown already: swap only, the re-set follows)
    }
}
static int cl13_dow(int d) { return d > 0 ? (d - 1) % 7 + 1 : 0; }      // a clan day (1..) as the day of its week: the header says WEEK n: DAY d
// the launcher's status look (clan-status.js): text colour, the 10 tile colours are in the widgets; names in clan_status.NAMES order
static const char *const C13_STN[10] = {"healthy", "hungry", "sad", "sick", "dead", "injured", "recovered", "new", "depressed", "shock"};
static const char *const C13_STTXT[10] = {"7FD07A", "F0B429", "7FA8F5", "F2625A", "A9AFB8", "F29A4A", "7FD07A", "55C6E8", "9DB0C4", "DCE7F0"};
static const char *const C13_STICON[10] = {"healthbar", "food", "person", "pills", "person", "bandage", "medicine", "person", "person", "person"};
static int cl13_stidx(const char *n) { for (int i = 0; i < 10; i++) if (!strcmp(n, C13_STN[i])) return i; return 1; }
static int cl13_pcode(char st) { return st == 'u' ? 1 : st == 's' ? 3 : st == 'd' ? 8 : st == 'k' ? 9 : 0; }       // roster state letter -> status index
static int cl13_pbar(char st) { return st == 'h' ? 0 : st == 'u' ? 1 : st == 's' ? 2 : st == 'd' ? 3 : 4; }
static void cl13_days_text(char *b, size_t n, int d) { if (d == 1) snprintf(b, n, "1 DAY"); else snprintf(b, n, "%d DAYS", d); }
static const char *cl13_tr(const char *en, char *b, size_t n) { const char *t = loc_tr(en); if (t && t != b) snprintf(b, n, "%s", t); return b; }      // (b may be en itself)
static void cl13_icon(const char *path, const char *id) {
    char img[96];
    snprintf(img, sizeof img, "streaming/t2r/icons/c13-%s.png", id && id[0] ? id : "keepsake");
    ui_image(path, img);
}
// ------------------------------------------------------------------ the tween table (entrances, growing bars, counting numbers)
static float cl13_eo(float t) { if (t <= 0.0f) return 0.0f; if (t >= 1.0f) return 1.0f; float u = 1.0f - t; return 1.0f - u * u * u * u; }       // ease out (about the launcher's cubic-bezier(.16, 1, .3, 1))
static int cl13_anim_off(void) { return gu_noanim(); }
static void cl13_fx_add(const char *path, float bx, float by, int kind, float delay) {
    if (C13.nfx >= C13_FXMAX) return;
    c13fx_t *f = &C13.fx[C13.nfx++];
    snprintf(f->path, sizeof f->path, "%s", path); f->bx = bx; f->by = by; f->kind = kind; f->delay = delay; f->w = 0; f->done = 0;
}
// where a number / bar / entrance stands NOW: while an entrance runs (or is about to) the value goes through the table, afterwards it is written plain
static int cl13_busy(uint64_t now) { return !cl13_anim_off() && (C13.fx_pending || (!C13.sw && now - C13.t0 < 2600)); }      // (the one entrance of the visit; after the first tab switch numbers and bars are written plain)
static void cl13_grow(const char *path, float frac, float delay, int pin, float kx, float ky) {
    uint64_t now = GetTickCount64();
    if (frac < 0.0f) frac = 0.0f;
    if (frac > 1.0f) frac = 1.0f;
    if (!cl13_busy(now)) {
        uint64_t w = ui_w(path);
        if (w) w_scale(w, frac < 0.004f ? 0.004f : frac, 1.0f);
        return;
    }
    for (int i = 0; i < C13.ngr; i++) if (!strcmp(C13.gr[i].path, path)) { C13.gr[i].frac = frac; return; }      // (a refill: the target moves, the timing stays)
    if (C13.ngr >= 48) return;
    c13gr_t *g = &C13.gr[C13.ngr++];
    snprintf(g->path, sizeof g->path, "%s", path); g->frac = frac; g->delay = delay; g->w = 0; g->done = 0; g->pin = pin; g->kx = kx; g->ky = ky;
}
// A number is never hidden or blanked while it changes: the widget keeps showing its last value and is only re-written when the integer moves, at most every 3rd frame
// (a gui2 text written every frame misses draws - the same engine trait as the post-match parts counter). The first appearance counts up from 0 inside the
// entrance; a later change of the value (a refresh) counts from what is shown to the new value. The table lives for the whole visit, so a tab switch never restarts it.
static void cl13_count(const char *path, int val, const char *fin, float delay) {
    uint64_t now = GetTickCount64();
    c13cn_t *c = NULL;
    for (int i = 0; i < C13.ncn; i++) if (!strcmp(C13.cn[i].path, path)) { c = &C13.cn[i]; break; }
    if (!c) {
        if (C13.ncn >= 24) { ui_text(path, fin); return; }
        c = &C13.cn[C13.ncn++];
        memset(c, 0, sizeof *c);
        snprintf(c->path, sizeof c->path, "%s", path); c->cur = -1; c->val = val; c->done = 1;
        if (cl13_busy(now) && val >= 2) { c->from = 0; c->delay = delay; c->t0 = now; c->done = 0; }
    } else if (c->val != val && !cl13_anim_off()) {
        c->from = c->cur >= 0 ? c->cur : 0; c->delay = 0.0f; c->t0 = now; c->done = val < 2;
    }
    c->val = val; snprintf(c->fin, sizeof c->fin, "%s", fin);
    if (c->done) { ui_text(path, fin); c->cur = val; }
}
static void cl13_fx_reset(void) { C13.nfx = C13.ngr = 0; }
static void cl13_fx_tick(uint64_t now) {
    const float DUR = 560.0f, DIST = 96.0f;
    for (int i = 0; i < C13.nfx; i++) {
        c13fx_t *f = &C13.fx[i];
        if (f->done) continue;
        if (!f->w) f->w = ui_w(f->path);
        if (!f->w) continue;
        float p = ((float)(now - C13.t0) - f->delay) / DUR;
        float e = cl13_eo(p), a = e;
        float dx = 0.0f, dy = 0.0f, inv = 1.0f - e;
        if (f->kind == 1) dx = -inv * DIST; else if (f->kind == 2) dx = inv * DIST; else if (f->kind == 3) dy = inv * DIST * 0.6f; else if (f->kind == 4) dy = -inv * DIST * 0.5f; else if (f->kind == 5) dy = inv * 28.0f;
        int q = (int)(a * 24.0f + 0.5f);
        w_alpha(f->w, (float)q / 24.0f);
        if (f->kind >= 1 && f->kind <= 5) w_pivot(f->w, f->bx + dx, f->by + dy);
        if (p >= 1.0f) { f->done = 1; w_alpha(f->w, 1.0f); if (f->kind >= 1 && f->kind <= 5) w_pivot(f->w, f->bx, f->by); }
    }
    for (int i = 0; i < C13.ngr; i++) {
        c13gr_t *g = &C13.gr[i];
        if (g->done) continue;
        if (!g->w) g->w = ui_w(g->path);
        if (!g->w) continue;
        float p = ((float)(now - C13.t0) - g->delay) / 900.0f, fr = g->frac * cl13_eo(p);
        w_scale(g->w, fr < 0.004f ? 0.004f : fr, 1.0f);
        if (g->pin) { uint64_t pw = ui_w("anim-group.ov.ovCamp.mo.moPin"); if (pw) w_pivot(pw, g->kx + g->pin * fr * 1.0f - 5.0f, g->ky); }
        if (p >= 1.0f) g->done = 1;
    }
    for (int i = 0; i < C13.ncn; i++) {
        c13cn_t *c = &C13.cn[i];
        if (c->done) continue;
        float p = ((float)(now - c->t0) - c->delay) / 700.0f;
        if (p >= 1.0f) { ui_text(c->path, c->fin); c->cur = c->val; c->done = 1; continue; }
        if (p < 0.0f) p = 0.0f;
        int v = c->from + (int)((float)(c->val - c->from) * cl13_eo(p) + 0.5f);
        if (v == c->cur) continue;      // (NR writes the number every frame while it counts; here: every frame the integer moved, never blanked)
        char b[120]; const char *d0 = c->fin; while (*d0 && (*d0 < '0' || *d0 > '9')) d0++;
        const char *d1 = d0; while (*d1 >= '0' && *d1 <= '9') d1++;
        snprintf(b, sizeof b, "%.*s%d%s", (int)(d0 - c->fin), c->fin, v, d1);       // (the final text's own markup around the number: no colour change or width jump when it lands)
        ui_text(c->path, b); c->cur = v; c->wr_f = g_frame;
    }
}
// ------------------------------------------------------------------ requests
static void cl13_seen_load(void) {
    C13.seen_jid = 0; C13.seen_day = 0; C13.seen_loaded = 1;
    FILE *f = exe_side_open("t2r-clan13-seen.txt", "r");
    if (!f) return;
    char b[64] = {0};
    if (fgets(b, sizeof b, f)) { cl13_seen_t s; cl13_seen_parse(b, &s); C13.seen_jid = s.jid; C13.seen_day = s.day; }
    fclose(f);
}
static void cl13_seen_save(void) {                                  // everything on the screen counts as seen once the page is left
    if (!C13.V) return;
    long jid = C13.seen_jid; int day = C13.seen_day;
    for (int i = 0; i < C13.V->nj; i++) if (C13.V->j[i].id > jid) jid = C13.V->j[i].id;
    for (int i = 0; i < C13.V->nd; i++) if (C13.V->d[i].id > jid) jid = C13.V->d[i].id;
    for (int i = 0; i < C13.V->nm; i++) if (C13.V->m[i].day > day) day = C13.V->m[i].day;
    if (jid == C13.seen_jid && day == C13.seen_day) return;
    FILE *f = exe_side_open("t2r-clan13-seen.txt", "w");
    if (f) { fprintf(f, "%ld %d\n", jid, day); fclose(f); }
}
static int cl13_ask(int sec) {                                      // 1 = a request went out
    uint8_t ex[9];
    ex[0] = (uint8_t)feed_lang(); ex[1] = (uint8_t)sec;
    long id = C13.seen_jid; int day = sec == 5 ? C13.xs_day : sec == 6 ? C13.jw : C13.seen_day;      // (section 6, the journal's week pages: the week whose text is wanted, 0 = the newest)       // section 5 (a raid's match stats) reuses the "seen raid day" slot for the raid's day
    ex[2] = (uint8_t)id; ex[3] = (uint8_t)(id >> 8); ex[4] = (uint8_t)(id >> 16); ex[5] = (uint8_t)(id >> 24);
    ex[6] = (uint8_t)day; ex[7] = (uint8_t)(day >> 8);
    ex[8] = 1;                                                      // capability: our reply buffer is 64 KB (older builds read 24 KB and drop anything bigger)
    return clan_send(0xB6, ex, 9);
}
static void cl13_net_tick(uint64_t now) {
    static const int ORD[C13_NTAB][4] = {{4, 3, 1, 2}, {1, 4, 3, 2}, {3, 1, 4, 2}, {6, 2, 1, 3}, {4, 1, 3, 2}};      // (the MISSIONS tab was missing: its zeroed row asked for section 0 over and over, every reply 'did not parse')      // the tab's sections first
    for (int s = 1; s <= 6; s++) {                                      // replies that arrived: the page's snapshot (a lock + 45 KB copy, only on a change)
        if ((int)g_cl13_ver[s] != C13.seen_ver[s]) {
            C13.seen_ver[s] = (int)g_cl13_ver[s];
            EnterCriticalSection(&g_clan_cs);
            int chg = memcmp(&g_cl13_view, &g_cl13, sizeof g_cl13_view) != 0;      // (a refresh with the same content changes nothing on screen: no refill)
            if (chg) memcpy(&g_cl13_view, &g_cl13, sizeof g_cl13_view);
            LeaveCriticalSection(&g_clan_cs);
            C13.ok_at[s] = now; C13.tries[s] = 0; if (chg || s == 5) C13.dirty = 1;
            if (s == 5 && C13.xs_open && C13.xs_wait) {                 // the answer to our match stats request (xday 0 = an empty reply: an older daemon)
                C13.xs_wait = 0;
                C13.xs_got = g_cl13_view.xday == C13.xs_day || g_cl13_view.xday == 0;
                if (!C13.xs_got) C13.xs_next = now;                     // the reply of another raid (opened and closed quickly): ask again
                else if (C13.xs_post && g_cl13_view.xn == 0 && now - C13.xs_t0 < 25000) { C13.xs_got = 0; C13.xs_tries = 0; C13.xs_next = now + 2500; xlog("clan13: post-match scoreboard: the server has no stats of day %d yet - asking again", C13.xs_day); }      // (the server books the match when the host's end arrives)
                xlog("clan13: match stats of day %d: %d player(s) (reply for day %d)", C13.xs_day, g_cl13_view.xn, g_cl13_view.xday);
            }
        }
    }
    if (C13.xs_open && !C13.xs_got && !C13.xs_wait && !g_clan_busy && g_loc_probed && now >= C13.xs_next) {
        if (C13.xs_tries >= 4) { C13.xs_got = 1; g_cl13_view.xday = 0; g_cl13_view.xn = 0; C13.dirty = 1; xlog("clan13: match stats of day %d: no answer after %d tries", C13.xs_day, C13.xs_tries); }
        else if (cl13_ask(5)) { C13.xs_wait = 1; C13.xs_tries++; C13.xs_next = now + 3000; xlog("clan13: asked match stats of day %d (try %d)", C13.xs_day, C13.xs_tries); }
    }
    if (C13.xs_wait && now >= C13.xs_next) C13.xs_wait = 0;             // (no reply within 3 s: asked again)
    if (g_clan_busy || !g_loc_probed) return;
    for (int k = 0; k < 4; k++) {
        int s = ORD[C13.tab][k];
        int need = !g_cl13_view.have[s] || now - C13.ok_at[s] >= C13_REFRESH_MS;
        if (!need || now < C13.next_ask[s]) continue;
        if (cl13_ask(s)) {
            C13.next_ask[s] = now + (g_cl13_view.have[s] ? 5000 : 2500);     // (re-asked until it came)
            C13.ask_ver[s] = (int)g_cl13_ver[s];
            C13.tries[s]++;
            static int nl; if (LOGCAP(nl, 30)) xlog("clan13: asked section %d (try %d)", s, C13.tries[s]);
        }
        break;                                                          // one request at a time
    }
}
// ------------------------------------------------------------------ filling
static const char *g_c13_hd_page;                                       // (the stats page: its own breadcrumb page name)
static void cl13_header(const cl13_t *V) {
    char pg[160], t[96];
    snprintf(t, sizeof t, "%s", g_c13_hd_page ? g_c13_hd_page : nr_clan_tab_label(C13.tab)); cl13_tr(t, t, sizeof t);
    snprintf(pg, sizeof pg, "%s", t);
    {   // opened over FIND MATCH: the search runs under the page - say so (fix1025-clanopen)
        static uint64_t PFM2;
        if (!PFM2) PFM2 = page_id("find-match-menu");
        if (PFM2 && page_on_stack(PFM2)) { size_t n = strlen(pg); snprintf(pg + n, SNLEFT(pg, n), "<font color=\"#8C8C8C\">   -   %s%.*s</font>", loc_tr("SEARCHING FOR A MATCH"), (int)((GetTickCount64() / 500) % 4), "..."); }
    }
    nr_header(V->fk == 'S' ? "SERAPHITE CLAN" : "WLF CLAN", pg);
    int wk = V->week, dw = V->dow;
    if (C13.xs_post) { int d = C13.xs_day - 1; d = d < 0 ? 0 : d > 83 ? 83 : d; wk = d / 7 + 1; dw = d % 7 + 1; }      // post-match: the day just played, the same numbers as the supply counter (pm_fill; the clan's own day has moved on by now)
    nr_week(wk, dw, V->done);
}
// ------------------------------------------------------------------ the 2D views: rows of tiles, a row window + a column window per row, ONE focus outline per tab
// Grid of a tab: row r has ncol[r] items, item[r][c] = the index into the tab's data (roster member, raid, day entry, mission row, status update).
typedef struct { int nrow, ncol[C13_GR], item[C13_GR][C13_NP]; int key[C13_GR]; } c13grid_t;
static c13grid_t g_c13g;                                              // (rebuilt for the shown tab by cl13_grid)
static const int C13_VROWS[C13_NTAB] = {1, 3, 2, 3, 8}, C13_VCOLS[C13_NTAB] = {4, 7, 3, 7, 1};
static void cl13_jw_follow(const char *why);
static void cl13_ms_upper(char *d, size_t n, const char *src);
static void cl13_grid(int tab, c13grid_t *G) {
    const cl13_t *V = C13.V;
    memset(G, 0, sizeof *G);
    if (!V) return;
    if (tab == T_OV) { G->nrow = V->nu > 0; G->ncol[0] = V->nu < C13_ST ? V->nu : C13_ST; for (int i = 0; i < G->ncol[0]; i++) G->item[0][i] = i; }
    else if (tab == T_SV) {                                            // a row per role, in the roster's order of first appearance
        for (int i = 0; i < V->np; i++) {
            int r = 0;
            for (; r < G->nrow; r++) if (!strcmp(V->p[G->item[r][0]].role, V->p[i].role)) break;
            if (r == G->nrow) { if (G->nrow >= C13_GR) r = C13_GR - 1; else G->nrow++; }
            if (G->ncol[r] < C13_NP) G->item[r][G->ncol[r]++] = i;
        }
    } else if (tab == T_RD) {                                          // a row per week of the raids (the list is newest first)
        for (int i = 0; i < V->nm; i++) {
            int wk = V->m[i].day > 0 ? (V->m[i].day - 1) / 7 + 1 : 1;
            if (!G->nrow || G->key[G->nrow - 1] != wk) { if (G->nrow >= C13_GR) break; G->key[G->nrow++] = wk; }
            int r = G->nrow - 1;
            G->item[r][G->ncol[r]++] = i;
        }
    } else if (tab == T_JR) {                                          // a row per week, newest first
        int top = V->jtop > 0 ? V->jtop : 1;
        for (int wk = top; wk >= 1 && G->nrow < C13_GR; wk--) {
            int idx[C13_ND], n = cl13_week_rows(V, wk, idx, C13_ND);
            if (n <= 0) continue;
            int r = G->nrow++;
            G->key[r] = wk;
            for (int c = 0; c < n && c < C13_NP; c++) G->item[r][G->ncol[r]++] = idx[c];
        }
    } else if (tab == T_MS) { G->nrow = C13.ms_n < C13_GR ? C13.ms_n : C13_GR; for (int r = 0; r < G->nrow; r++) { G->ncol[r] = 1; G->item[r][0] = r; } }
}
// keep the focus on an item and both windows around it; returns the focused item (-1: none)
static int cl13_gwin(int tab, const c13grid_t *G) {
    int vr = C13_VROWS[tab], vc = C13_VCOLS[tab];
    if (G->nrow <= 0) { C13.fr[tab] = C13.fc[tab] = C13.roff[tab] = 0; return -1; }
    if (C13.fr[tab] >= G->nrow) C13.fr[tab] = G->nrow - 1;
    if (C13.fr[tab] < 0) C13.fr[tab] = 0;
    int r = C13.fr[tab];
    if (C13.fc[tab] >= G->ncol[r]) C13.fc[tab] = G->ncol[r] - 1;
    if (C13.fc[tab] < 0) C13.fc[tab] = 0;
    if (r < C13.roff[tab]) C13.roff[tab] = r;
    if (r >= C13.roff[tab] + vr) C13.roff[tab] = r - vr + 1;
    if (C13.roff[tab] > G->nrow - vr) C13.roff[tab] = G->nrow - vr;
    if (C13.roff[tab] < 0) C13.roff[tab] = 0;
    for (int q = 0; q < G->nrow && q < C13_GR; q++) {
        int *co = &C13.coff[tab][q], n = G->ncol[q];
        if (q == r) { if (C13.fc[tab] < *co) *co = C13.fc[tab]; if (C13.fc[tab] >= *co + vc) *co = C13.fc[tab] - vc + 1; }
        if (*co > n - vc) *co = n - vc;
        if (*co < 0) *co = 0;
    }
    return G->item[r][C13.fc[tab]];
}
// a 2D step (dr rows / dc columns); the column is remembered across rows (want); the journal runs on into the next / previous week at a row's ends
static int cl13_gstep(int tab, int dr, int dc) {
    c13grid_t *G = &g_c13g;
    cl13_grid(tab, G);
    if (G->nrow <= 0) return 0;
    int r = C13.fr[tab], c = C13.fc[tab], r0 = r, c0 = c;
    if (dc) {
        c += dc;
        if (tab == T_JR && c >= G->ncol[r] && r > 0) { r--; c = 0; }
        else if (tab == T_JR && c < 0 && r + 1 < G->nrow) { r++; c = G->ncol[r] - 1; }
        if (c < 0) c = 0;
        if (c >= G->ncol[r]) c = G->ncol[r] - 1;
        C13.want[tab] = c;
    }
    if (dr) {
        r += dr;
        if (r < 0) r = 0;
        if (r >= G->nrow) r = G->nrow - 1;
        c = C13.want[tab] < G->ncol[r] ? C13.want[tab] : G->ncol[r] - 1;
    }
    if (r == r0 && c == c0) return 0;
    C13.fr[tab] = r; C13.fc[tab] = c;
    if (tab == T_JR && r != r0) cl13_jw_follow("week row");
    C13.dirty = 1; cl13_sfx();
    return 1;
}
// a tile's alpha / text colour for focused or hovered vs the rest
static void cl13_tile_bg(const char *grp, int lit) { char p[160]; snprintf(p, sizeof p, "%sBg", grp); w_alpha(ui_w(p), (lit ? (float)215 : (float)175) / 255.0f); }
static void cl13_lit_text(const char *path, const char *t, int lit, float box, float pt) {
    char b[300];
    if (lit) snprintf(b, sizeof b, "%s", t); else snprintf(b, sizeof b, "<font color=\"#8C8C8C\">%s</font>", t);
    if (box > 0.0f) cl13_fit(path, b, box, pt); else ui_text(path, b);
}
static void cl13_upper(char *d, size_t n, const char *s) { cl13_ms_upper(d, n, s ? s : ""); }
static int cl13_hv_is(int tab, int r, int c) { return C13.tab == tab && C13.hv_r == r && C13.hv_c == c; }
static void cl13_chip(const char *base, const char *t, float x, float right, float pt) { nr_chip(base, t, x, right, pt); }      // nr_style.chip
#define C13_NREC 4
static void cl13_fill_ov(const cl13_t *V) {
    char b[200], p[200], t[120];
    c13grid_t *G = &g_c13g; cl13_grid(T_OV, G);
    int f = cl13_gwin(T_OV, G), n = G->ncol[0];
    nr_section("anim-group.ov.ovSt", 148.0f, 2380.0f, 452.0f, "STATUS UPDATES", V->nu ? "SINCE YOU LAST LOOKED" : "NOTHING NEW SINCE YOU LAST LOOKED", 36.0f);
    for (int i = 0; i < C13_ST; i++) {
        snprintf(p, sizeof p, "anim-group.ov.stRow%d", i);
        ui_visible(p, i < n);
        if (i >= n) continue;
        const cl13_u_t *u = &V->u[i];
        int lit = i == C13.fc[T_OV] || cl13_hv_is(T_OV, 0, i);
        cl13_tile_bg(p, lit);
        snprintf(b, sizeof b, "%s.stPt%d", p, i); cl13_pic(b, u->pid);
        snprintf(b, sizeof b, "%s.stPt%dIm", p, i); w_alpha(ui_w(b), lit ? 1.0f : 0.6f);
        cl13_upper(t, sizeof t, u->name);
        snprintf(b, sizeof b, "%s.stName%d", p, i); cl13_lit_text(b, t, lit, 300.0f, 30.0f);
        snprintf(b, sizeof b, "%s.stNew%d", p, i); ui_visible(b, i < 2);
    }
    nr_frame_at("anim-group.ov.ovFo", 148.0f + 372.0f * (float)C13.fc[T_OV], 508.0f, 340.0f, 356.0f, n > 0 && C13.tab == T_OV);
    ui_visible("anim-group.ov.ovDt", f >= 0);
    if (f >= 0 && !C13.det_hold) {                                   // the focused update
        const cl13_u_t *u = &V->u[f];
        int si = cl13_stidx(u->state);
        cl13_upper(t, sizeof t, u->name);
        snprintf(b, sizeof b, "%s  |  %s", u->role, t);
        nr_section("anim-group.ov.ovDt.ovDs", 2520.0f, 3700.0f, 452.0f, b, "", 36.0f);
        cl13_pic("anim-group.ov.ovDt.ovDt", u->pid);
        ui_text("anim-group.ov.ovDt.ovDtRole", u->role);
        cl13_fit("anim-group.ov.ovDt.ovDtName", t, 620.0f, 63.0f);
        ui_visible("anim-group.ov.ovDt.ovDtIc", si != 0); if (si) cl13_icon("anim-group.ov.ovDt.ovDtIc", C13_STICON[si]);
        ui_text("anim-group.ov.ovDt.ovDtWord", u->stw);
        w_pivot(ui_w("anim-group.ov.ovDt.ovDtWord"), si ? 3144.0f : 3080.0f, 772.0f);
        ui_visible("anim-group.ov.ovDt.ovDtNew", f < 2); ui_visible("anim-group.ov.ovDt.ovDtNewTx", f < 2);
        cl13_clipped("anim-group.ov.ovDt.ovDtLine", u->line, 1180.0f, 36.0f, 3);
        cl13_chip("anim-group.ov.ovDt.ovDtRd", loc_tr("READ IN THE JOURNAL"), 2520.0f, 0.0f, 30.0f);
    }
    // supplies
    int any_stock = 0; for (int k = 0; k < V->ns; k++) if (V->s[k].stock > 0) any_stock = 1;
    int last = V->ns && any_stock && V->worst >= 0;
    if (last) { ui_text("anim-group.ov.ovLastLb", "THE STOCK LASTS"); cl13_days_text(b, sizeof b, V->worst); cl13_count("anim-group.ov.ovLast", V->worst, b, 520.0f); }
    else { ui_text("anim-group.ov.ovLastLb", ""); ui_text("anim-group.ov.ovLast", ""); }
    nr_section("anim-group.ov.ovSu", 148.0f, last ? 2380.0f - nr_tw(loc_tr("THE STOCK LASTS"), 30.0f) - nr_tw(b, 51.0f) - 80.0f : 2380.0f, 952.0f, "SUPPLIES", "", 36.0f);
    w_pivot(ui_w("anim-group.ov.ovLastLb"), 2380.0f - nr_tw(b, 51.0f) - 40.0f, 952.0f);
    ui_text("anim-group.ov.ovSupNone", V->ns ? "" : "NO SUPPLIES BOOKED YET - THEY ARE COUNTED AFTER EACH RAID");
    static const char *const CAT[5] = {"food", "water", "medicine", "ammo", "materials"};
    for (int k = 0; k < 5; k++) {
        int has = k < V->ns;
        snprintf(p, sizeof p, "anim-group.ov.tlRow%d", k); ui_visible(p, has);
        if (!has) continue;
        const cl13_s_t *s = &V->s[k];
        snprintf(b, sizeof b, "%s.tlIc%d", p, k); cl13_icon(b, CAT[k]);
        snprintf(b, sizeof b, "%s.tlLb%d", p, k); ui_text(b, s->label);
        snprintf(b, sizeof b, "%s.tlNum%d", p, k);
        if (s->stock > 0) { char v[32]; snprintf(v, sizeof v, "%d", s->stock); cl13_count(b, s->stock, v, 600.0f + 70.0f * k); }
        else { snprintf(t, sizeof t, "<font color=\"#8C8C8C\">%s</font>", loc_tr("NONE")); ui_text(b, t); }
        char d[40] = ""; if (s->days >= 0 && s->need > 0) cl13_days_text(d, sizeof d, s->days); else if (s->stock > 0) snprintf(d, sizeof d, "IN CAMP");
        snprintf(b, sizeof b, "%s.tlDays%d", p, k); ui_text(b, d);
        float fr = s->need > 0 ? (float)(s->days < 0 ? 0 : s->days) / 7.0f : s->stock > 0 ? 1.0f : 0.0f;   // (the bar: days of stock out of a week)
        snprintf(b, sizeof b, "%s.tlBar%dF", p, k); nr_bar(b, 28.0f, 312.0f, 213.0f, fr);
    }
    // camp: the morale line, its word; campaigns / clans lost / largest clan / the 2013 rank
    nr_section("anim-group.ov.ovCa", 148.0f, 2380.0f, 1412.0f, "CAMP", "", 36.0f);
    int v = V->morale < 0 ? 0 : V->morale > 100 ? 100 : V->morale;
    int band = v >= 70 ? 3 : v >= 50 ? 2 : v >= 30 ? 1 : 0;           // grim, strained, steady, hopeful
    nr_bar("anim-group.ov.moF", 528.0f, 1668.0f, 1494.0f, (float)(v < 3 ? 3 : v) / 100.0f);
    w_pivot(ui_w("anim-group.ov.moPin"), 528.0f + 1140.0f * (float)v / 100.0f - 3.0f, 1472.0f);
    ui_text("anim-group.ov.moWord", band == 3 ? "HOPEFUL" : band == 2 ? "STEADY" : band == 1 ? "STRAINED" : "GRIM");
    snprintf(b, sizeof b, "%d", V->won); ui_text("anim-group.ov.ovCs0", b);
    snprintf(b, sizeof b, "%d", V->lost); ui_text("anim-group.ov.ovCs1", b);
    snprintf(b, sizeof b, "%d", V->maxsz > V->alive ? V->maxsz : V->alive); ui_text("anim-group.ov.ovCs2", b);
    { clan_t rc = clan_get(); int on = rc.ok && rc.wk > 0;            // 2013 rank number: weeks survived in total (was the header's line)
      ui_visible("anim-group.ov.ovCs3Lb", on); ui_visible("anim-group.ov.ovCs3", on);
      if (on) { snprintf(b, sizeof b, rc.wk == 1 ? "%d WEEK" : "%d WEEKS", rc.wk); ui_text("anim-group.ov.ovCs3", b); } }
    // recently in camp: the newest journal headlines with their day
    int nrec = 0, recs[C13_NREC];
    for (int i = 0; i < V->nj && nrec < C13_NREC; i++) if (V->j[i].title[0]) recs[nrec++] = i;
    nr_section("anim-group.ov.ovRc", 2520.0f, 3700.0f, 1380.0f, nrec ? "RECENTLY IN CAMP" : "", "", 36.0f);
    for (int i = 0; i < C13_NREC; i++) {
        snprintf(p, sizeof p, "anim-group.ov.ovRecLn%d", i); ui_visible(p, i < nrec);
        snprintf(p, sizeof p, "anim-group.ov.ovRecDay%d", i);
        if (i < nrec) { snprintf(b, sizeof b, "DAY %d", V->j[recs[i]].day); ui_text(p, b); } else ui_text(p, "");
        snprintf(p, sizeof p, "anim-group.ov.ovRecTx%d", i);
        if (i < nrec) { snprintf(t, sizeof t, "%s", V->j[recs[i]].title); cl13_lower_tail(t); cl13_fit(p, t, 980.0f, 39.0f); }
        else ui_text(p, "");
    }
}
static void cl13_fill_sv_detail(const cl13_t *V, int f) {
    if (f < 0 || f >= V->np) return;
    const cl13_p_t *m = &V->p[f];
    char b[300], t[96];
    snprintf(b, sizeof b, m->st != 'h' ? "%s  |  %s" : "%s", m->role, m->stw);
    nr_section("anim-group.sv.svDt.svDs", 2580.0f, 3700.0f, 452.0f, b, "", 36.0f);
    cl13_pic("anim-group.sv.svDt.svDt", m->pid);
    ui_text("anim-group.sv.svDt.svDtRole", m->role);
    cl13_upper(t, sizeof t, m->name); cl13_fit("anim-group.sv.svDt.svDtName", t, 600.0f, 63.0f);
    ui_text("anim-group.sv.svDt.svDtSub", m->st != 'h' ? m->stw : "");
    cl13_clipped("anim-group.sv.svDt.svDtTag", m->tag, 1120.0f, 36.0f, 3);
    nr_section("anim-group.sv.svDt.svDc", 2580.0f, 3700.0f, 1232.0f, m->bond[0] ? "CLOSE TO" : "", "", 36.0f);
    const char *bp = "";
    for (int i = 0; i < V->np; i++) if (!strcmp(V->p[i].name, m->bond)) { bp = V->p[i].pid; break; }
    cl13_pic("anim-group.sv.svDt.svDtB", m->bond[0] ? bp : "");
    cl13_upper(t, sizeof t, m->bond); cl13_fit("anim-group.sv.svDt.svDtBond", t, 900.0f, 42.0f);
    ui_visible("anim-group.sv.svDt.svDtBtBg", m->bondty[0] != 0); ui_visible("anim-group.sv.svDt.svDtBtTx", m->bondty[0] != 0);
    if (m->bondty[0]) { cl13_upper(t, sizeof t, m->bondty); cl13_chip("anim-group.sv.svDt.svDtBt", t, 2780.0f, 0.0f, 27.0f); }
    nr_section("anim-group.sv.svDt.svDl", 2580.0f, 3700.0f, 1560.0f, m->lately[0] ? "LATELY" : "", "", 36.0f);
    cl13_clipped("anim-group.sv.svDt.svDtLately", m->lately, 1120.0f, 36.0f, 4);
}
static int cl13_plural(char *o, size_t n, const char *role) {         // a role row's header: GUARD -> GUARDS (English only; a translated roster keeps the word)
    size_t l = strlen(role);
    if (g_loc_cur < 0 && l && role[l - 1] != 'S' && role[l - 1] != 's') return snprintf(o, n, "%sS", role);
    return snprintf(o, n, "%s", role);
}
static void cl13_fill_sv(const cl13_t *V) {
    char b[200], p[200], t[96], g[96];
    c13grid_t *G = &g_c13g; cl13_grid(T_SV, G);
    int f = cl13_gwin(T_SV, G);
    snprintf(b, sizeof b, "%d", V->np); ui_text("anim-group.sv.svCount", b);
    w_pivot(ui_w("anim-group.sv.svCount"), 148.0f + nr_tw(loc_tr("SURVIVORS"), 39.0f) + 80.0f, 452.0f);
    for (int vr = 0; vr < 3; vr++) {
        int r = C13.roff[T_SV] + vr;
        snprintf(g, sizeof g, "anim-group.sv.svR%d", vr);
        ui_visible(g, r < G->nrow);
        if (r >= G->nrow) continue;
        int nc = G->ncol[r], co = C13.coff[T_SV][r];
        cl13_plural(t, sizeof t, V->p[G->item[r][0]].role);
        if (nc > 7) snprintf(b, sizeof b, "%d-%d | %d", co + 1, co + 7 < nc ? co + 7 : nc, nc); else snprintf(b, sizeof b, "%d", nc);
        snprintf(p, sizeof p, "%s.svS%d", g, vr); nr_section(p, 148.0f, 2420.0f, 0.0f, t, b, 36.0f);
        for (int c = 0; c < 7; c++) {
            int ci = co + c;
            snprintf(p, sizeof p, "%s.sv%d_%d", g, vr, c);
            ui_visible(p, ci < nc);
            if (ci >= nc) continue;
            const cl13_p_t *m = &V->p[G->item[r][ci]];
            int foc = r == C13.fr[T_SV] && ci == C13.fc[T_SV], lit = foc || cl13_hv_is(T_SV, vr, c);
            cl13_tile_bg(p, lit);
            snprintf(b, sizeof b, "%s.sv%d_%dP", p, vr, c); cl13_pic(b, m->pid);
            snprintf(b, sizeof b, "%s.sv%d_%dPIm", p, vr, c); w_alpha(ui_w(b), lit ? 1.0f : m->st == 'h' ? 0.6f : 0.75f);
            snprintf(b, sizeof b, "%s.sv%d_%dSb", p, vr, c); ui_visible(b, m->st != 'h'); if (m->st != 'h') w_alpha(ui_w(b), m->st == 'u' || m->st == 's' ? 0.9f : 0.47f);
            cl13_upper(t, sizeof t, m->name);
            snprintf(b, sizeof b, "%s.sv%d_%dN", p, vr, c); cl13_lit_text(b, t, lit, 290.0f, 28.0f);
            snprintf(b, sizeof b, "%s.sv%d_%dW", p, vr, c); ui_text(b, m->st != 'h' ? m->stw : "");
            snprintf(b, sizeof b, "%s.sv%d_%dD", p, vr, c); ui_visible(b, 0);
        }
    }
    int fv = C13.fr[T_SV] - C13.roff[T_SV], fcv = C13.fc[T_SV] - C13.coff[T_SV][C13.fr[T_SV] < C13_GR ? C13.fr[T_SV] : 0];
    nr_frame_at("anim-group.sv.svFo", 148.0f + 308.0f * (float)fcv, 564.0f + 428.0f * (float)fv + 44.0f, 280.0f, 248.0f, f >= 0 && C13.tab == T_SV);
    nr_scroll_v("anim-group.sv.svSb", 2448.0f, 540.0f, 1860.0f, 660.0f, C13.roff[T_SV], 3, G->nrow);
    { int sh = G->nrow < 3 ? G->nrow : 3; snprintf(b, sizeof b, "%d | %d GROUPS", C13.roff[T_SV] + sh, G->nrow); ui_text("anim-group.sv.svFoot", G->nrow > 3 ? b : ""); }
    ui_visible("anim-group.sv.svDt", f >= 0);
    if (!C13.det_hold) cl13_fill_sv_detail(V, f);
}
static const char *const C13_CAT_ICON[5] = {"food", "water", "medicine", "ammo", "materials"};
static void cl13_fill_rd_detail(const cl13_t *V, int f) {
    if (f < 0 || f >= V->nm) return;
    const cl13_m_t *m = &V->m[f];
    char b[200], p[200], t[96];
    cl13_upper(t, sizeof t, m->map);
    snprintf(b, sizeof b, "%s  |  %s", t, loc_tr("SUPPLIES BROUGHT HOME"));
    nr_section("anim-group.rds.rdDt.rdDs", 2180.0f, 3700.0f, 452.0f, b, "", 36.0f);
    snprintf(b, sizeof b, "%d", m->sup);
    cl13_count("anim-group.rds.rdDt.rdDtBig", m->sup, b, 120.0f);
    w_pivot(ui_w("anim-group.rds.rdDt.rdDtOf"), 2180.0f + nr_tw(b, 114.0f) + 28.0f, 632.0f);
    snprintf(b, sizeof b, "| %d NEEDED", m->need); ui_text("anim-group.rds.rdDt.rdDtOf", b);
    int ok = m->sup >= m->need;
    if (ok) snprintf(b, sizeof b, m->sup > m->need ? "ENOUGH, +%d OVER" : "ENOUGH", m->sup - m->need);
    else snprintf(b, sizeof b, "SHORT BY %d", m->need - m->sup);
    cl13_chip("anim-group.rds.rdDt.rdVd", loc_tr(b), 0.0f, 3700.0f, 36.0f);
    static const int CI[NBAR_C] = {0, 1, 2, 4};
    for (int k = 0; k < NBAR_C; k++) {
        int ci = CI[k], got = m->got[ci], need = m->needc[ci], mx = got > need ? got : need;
        if (mx < 1) mx = 1;
        float y = 800.0f + 124.0f * (float)k;
        snprintf(p, sizeof p, "anim-group.rds.rdDt.rdBIc%d", k); cl13_icon(p, C13_CAT_ICON[ci]);
        cl13_text("anim-group.rds.rdDt.rdBLb%d", k, ci == 0 ? "FOOD" : ci == 1 ? "WATER" : ci == 2 ? "MEDICINE" : "MATERIALS");
        if (need) snprintf(b, sizeof b, "%d | %d", got, need); else snprintf(b, sizeof b, "%d", got);
        cl13_text("anim-group.rds.rdDt.rdBNum%d", k, b);
        if (need > 0 && got > need) snprintf(b, sizeof b, "+%d", got - need); else b[0] = 0;
        cl13_text("anim-group.rds.rdDt.rdBDelta%d", k, b);
        snprintf(p, sizeof p, "anim-group.rds.rdDt.rdB%dF", k); nr_bar(p, 2620.0f, 3420.0f, y, (float)got / (float)mx);
        snprintf(p, sizeof p, "anim-group.rds.rdDt.rdBNeed%d", k);
        ui_visible(p, need > 0);
        if (need > 0) w_pivot(ui_w(p), 2620.0f + 800.0f * (float)need / (float)mx - 1.0f, y - 18.0f);
    }
    int ln = 0;
    for (int i = 0; i < V->nt && ln < 4; i++) if (V->t[i].day == m->day) {
        char g[96], q[200];
        snprintf(g, sizeof g, "anim-group.rds.rdDt.ltRow%d", ln);
        ui_visible(g, 1);
        snprintf(q, sizeof q, "%s.ltIc%d", g, ln); cl13_icon(q, V->t[i].icon);
        snprintf(b, sizeof b, "x%s", V->t[i].qty);
        snprintf(q, sizeof q, "%s.ltQty%d", g, ln); ui_text(q, b);
        snprintf(q, sizeof q, "%s.ltNm%d", g, ln); cl13_fit(q, V->t[i].name, 560.0f, 28.0f);
        snprintf(q, sizeof q, "%s.ltNew%d", g, ln); ui_visible(q, V->t[i].fresh);
        ln++;
    }
    for (int k = ln; k < 4; k++) { snprintf(p, sizeof p, "anim-group.rds.rdDt.ltRow%d", k); ui_visible(p, 0); }
    nr_section("anim-group.rds.rdDt.rdLs", 2180.0f, 3700.0f, 1360.0f, ln ? "BROUGHT HOME" : "", "", 36.0f);
}
static void cl13_fill_rd(const cl13_t *V) {
    char b[200], p[200], t[96], g[96];
    c13grid_t *G = &g_c13g; cl13_grid(T_RD, G);
    int f = cl13_gwin(T_RD, G);
    ui_text("anim-group.rds.rdHint", V->nm ? "SELECT A RAID TO SEE WHAT IT BROUGHT HOME" : "NO RAIDS YET - PLAY A MATCH TO SEND A PARTY OUT");
    ui_visible("anim-group.rds.rdDt", f >= 0);
    for (int vr = 0; vr < 2; vr++) {
        int r = C13.roff[T_RD] + vr;
        snprintf(g, sizeof g, "anim-group.rds.rdR%d", vr);
        ui_visible(g, r < G->nrow);
        if (r >= G->nrow) continue;
        int nc = G->ncol[r], co = C13.coff[T_RD][r];
        snprintf(t, sizeof t, "WEEK %d", G->key[r]); cl13_tr(t, t, sizeof t);
        if (nc > 3) snprintf(b, sizeof b, "%d-%d | %d", co + 1, co + 3 < nc ? co + 3 : nc, nc); else snprintf(b, sizeof b, "%d", nc);
        snprintf(p, sizeof p, "%s.rdS%d", g, vr); nr_section(p, 148.0f, 2020.0f, 0.0f, t, b, 36.0f);
        for (int c = 0; c < 3; c++) {
            int ci = co + c;
            snprintf(p, sizeof p, "%s.rd%d_%d", g, vr, c);
            ui_visible(p, ci < nc);
            if (ci >= nc) continue;
            const cl13_m_t *m = &V->m[G->item[r][ci]];
            int foc = r == C13.fr[T_RD] && ci == C13.fc[T_RD], lit = foc || cl13_hv_is(T_RD, vr, c);
            cl13_tile_bg(p, lit);
            snprintf(b, sizeof b, "DAY %d", cl13_dow(m->day)); { char q[200]; snprintf(q, sizeof q, "%s.rd%d_%dDy", p, vr, c); ui_text(q, b); }
            { char q[200]; snprintf(q, sizeof q, "%s.rd%d_%dD", p, vr, c); ui_visible(q, m->fresh); }
            cl13_upper(t, sizeof t, m->map);
            { char q[200]; snprintf(q, sizeof q, "%s.rd%d_%dM", p, vr, c); cl13_lit_text(q, t, lit, 536.0f, 39.0f); }
            { char q[200]; snprintf(q, sizeof q, "%s.rd%d_%dW", p, vr, c); ui_text(q, m->win == 1 ? "MATCH WON" : m->win == 0 ? "MATCH LOST" : ""); }
            snprintf(b, sizeof b, "%d | %d", m->sup, m->need);
            { char q[200]; snprintf(q, sizeof q, "%s.rd%d_%dN", p, vr, c); cl13_lit_text(q, b, lit, 0.0f, 0.0f); }
            { char q[200]; snprintf(q, sizeof q, "%s.rd%d_%dBF", p, vr, c); nr_bar(q, 32.0f, 568.0f, 393.0f, m->need > 0 ? (float)m->sup / (float)m->need : 1.0f); }
        }
    }
    int fv = C13.fr[T_RD] - C13.roff[T_RD], fcv = C13.fc[T_RD] - C13.coff[T_RD][C13.fr[T_RD] < C13_GR ? C13.fr[T_RD] : 0];
    nr_frame_at("anim-group.rds.rdFo", 148.0f + 632.0f * (float)fcv, 564.0f + 540.0f * (float)fv + 48.0f, 600.0f, 432.0f, f >= 0 && C13.tab == T_RD);
    nr_scroll_v("anim-group.rds.rdSb", 2048.0f, 540.0f, 1600.0f, 530.0f, C13.roff[T_RD], 2, G->nrow);
    C13.foc[T_RD] = f < 0 ? 0 : f;                                     // (the raid PLAYER STATS opens: cl13_xs_open reads foc[T_RD])
    if (!C13.det_hold) cl13_fill_rd_detail(V, f);
}
// ------------------------------------------------------------------ MISSIONS: the old to1/mission-choose pick in the clan page's look (the choice sent is still op 0xEF [mission id])
static int cl13_pick_due(void);
static void cl13_ms_rows(void) {
    meta_t m = meta_get();
    int n = 0;
    if (cl13_pick_due() || C13.ms_chosen) {
        for (int id = 1; id <= 6; id++) if (MIS[id].live && m.mr[id] < 5) C13.ms_rows[n++] = id;      // (a mission completed 5 times is greyed out, 2013 list)
        if (!n) for (int id = 1; id <= 6; id++) if (MIS[id].live) C13.ms_rows[n++] = id;
        for (int k = 0; k < 3 && n < C13_MS_ROWS; k++)                                                 // + the random weapon-execution missions the server rolled for this choice
            if (m.p[k] > 0 && MIS_IS_EXEC(m.p[k]) && MIS_VALID(m.p[k]) && m.mr[m.p[k]] < 5) C13.ms_rows[n++] = m.p[k];
    }
    if (n != C13.ms_n) { C13.ms_n = n; if (C13.fr[T_MS] >= n) C13.fr[T_MS] = n ? n - 1 : 0; xlog("clan13: missions: %d rows (weapon-execution offers %d / %d / %d)", n, m.p[0], m.p[1], m.p[2]); }
}
static void cl13_ms_upper(char *d, size_t n, const char *src) { size_t i = 0; for (; src[i] && i + 1 < n; i++) d[i] = src[i] >= 'a' && src[i] <= 'z' ? (char)(src[i] - 32) : src[i]; d[i] = 0; cl13_case_pl(d, 1); }
// The MISSIONS tab shows the current mission status instead of MISSION PICKED (no need to back out and read the small clan UI at the bottom left). With a mission running the tab is its status page: the three tiers as the rows (goal,
// DONE / how many to go), the detail pane with the live count (the server's + this match's own g_mis_cnt, like the HUD widget), the day of three,
// what the tiers pay the running event and how many times it was done before.
static int cl13_ms_running(void) { meta_t m = meta_get(); return m.ok && MIS_VALID(m.mi) && !C13.ms_n; }
// the running mission's icon (layout A): a weapon-specific mission shows that weapon's own HUD icon (the death banner's table, death_ui.c: stock TLOU2 guns/ + the mod's
// streaming/t2r/icons), the others the matching icon of the mod's skill set (round TLOU2-style badges) or the launcher's clan icons (c13-*)
static const char *cl13_ms_icon(int id) {
    switch (id) {
    case 1: return "streaming/t2r/icons/skill-damage-marker.png";                    // down enemies: the downed-target chevron badge
    case 2: case 7: return "streaming/t2r/icons/skill-executioner.png";
    case 3: return "streaming/t2r/icons/skill-reviver.png";
    case 4: return "streaming/t2r/icons/skill-sharpshooter.png";
    case 5: return "streaming/t2r/icons/c13-binoculars.png";
    case 6: return "streaming/t2r/icons/skill-firstaid.png";
    case 8: return "streaming/t2r/icons/c13-molotov.png";
    case 9: return "streaming/t2r/icons/c13-pipebomb.png";
    case 10: return "streaming/t2r/icons/skill-crafter.png";
    case 11: return "streaming/t2r/icons/skill-brawler.png";
    case 12: return "streaming/t2r/icons/c13-shiv.png";
    case 13: return "streaming/t2r/icons/skill-hawk.png";
    case 14: case 48:
#if defined(T2R_COLT_BUILT) && T2R_COLT_BUILT
        return "streaming/t2r/icons/colt.png";
#else
        return "hud/weapons/guns/pistol-beretta/beretta.png";
#endif
    case 15: case 49: return "hud/weapons/guns/pistol-revolver-taurus/revolver-brl.png";
    case 16: case 52: return "streaming/t2r/icons/shorty.png";
    case 17: case 41: return "hud/weapons/guns/rifle-remington-bolt/remington-bolt.png";
    case 18: case 44: return "streaming/t2r/icons/m14.png";
    case 19: case 47: return "streaming/t2r/icons/burst-rifle.png";
    case 20: case 42: return "hud/weapons/guns/bow-ellie/bow.png";
    case 40: return "hud/weapons/guns/rifle-vepr/vepr-scp.png";
    case 43: return "hud/weapons/guns/rifle-mpx5/mpx5.png";
    case 45: return "streaming/t2r/icons/tac-shotgun.png";
    case 46: return "streaming/t2r/icons/frontier.png";
    case 50: return "hud/weapons/guns/pistol-glock/glock.png";
    case 51: return "streaming/t2r/icons/cz75.png";
    }
    return "streaming/t2r/icons/skill-damage-marker.png";
}
#define C13_RUN_BAR_L 384.0f             // the running view's progress bar (clan13_widgets.py BAR_L / BAR_W2 / BAR_T)
#define C13_RUN_BAR_W 3072.0f
#define C13_RUN_BAR_T 982.0f
#define C13_RUN_Y 559.0f
#define C13_MS_TX 452.0f
static void cl13_ladder(int pick, int id, int cnt, int reached, const char *un, int atk, int sur, int es, int size, int rep) {      // the 3 tiers (running: the left column; the pick list: the focused mission's tiers at the right)
    meta_t m = meta_get();
    char b[200], p[200], t[96];
    uint64_t lg = ui_w("anim-group.ms.msLad");
    if (lg) w_pivot(lg, pick ? 1872.0f : 0.0f, pick ? 380.0f : 0.0f);
    for (int k = 0; k < 3; k++) {
        int goal = mis_goal_m(&m, id, k), st = pick ? (k == 0 ? 1 : 2) : k < reached ? 0 : k == reached ? 1 : 2, bo = mis_boost(rep, k);
        float y = 580.0f + 300.0f * (float)k;
        snprintf(p, sizeof p, "anim-group.ms.msLad.msPi%d", k);
        snprintf(b, sizeof b, "streaming/t2r/icons/c13-ms-%s.png", st == 0 ? "check" : st == 1 ? "cur" : "lock"); ui_image(p, b);
        snprintf(p, sizeof p, "anim-group.ms.msLad.msTl%d", k); snprintf(b, sizeof b, "TIER %d", k + 1); ui_text(p, b);
        snprintf(p, sizeof p, "anim-group.ms.msLad.msTg%d", k);
        if (!pick && st == 1 && cnt < goal) snprintf(b, sizeof b, "%d TO GO", goal - cnt); else b[0] = 0;
        ui_text(p, b);
        snprintf(t, sizeof t, "%d %s", goal, un);
        snprintf(p, sizeof p, "anim-group.ms.msLad.msGo%d", k); cl13_lit_text(p, t, pick || st == 1, 900.0f, 45.0f);
        snprintf(p, sizeof p, "anim-group.ms.msLad.msCn%d", k);
        if (pick) b[0] = 0; else snprintf(b, sizeof b, "%d | %d", st == 2 ? 0 : cnt < goal ? cnt : goal, goal);
        cl13_lit_text(p, b, st != 2, 0.0f, 0.0f);
        char rw[2][48] = {{0}, {0}}; int nr = 0;
        if (atk) snprintf(rw[nr++], 48, "LOSE %d%%", ev_loss_pct(es, k + 1));
        else if (sur) { int sv = mis_growth(size, k); snprintf(rw[nr++], 48, sv == 1 ? "+%d SURVIVOR" : "+%d SURVIVORS", sv); }
        snprintf(rw[nr++], 48, pick ? (bo == 1 ? "+%d BOOSTER" : "+%d BOOSTERS") : "x%d BOOSTERS", bo);
        float x = C13_MS_TX + nr_tw(loc_tr("Unlocks:"), 33.0f) + 24.0f;
        for (int q = 0; q < 2; q++) {
            char base[96]; snprintf(base, sizeof base, "anim-group.ms.msLad.msC%d_%d", q, k);
            snprintf(p, sizeof p, "%sBg", base); ui_visible(p, q < nr); w_alpha(ui_w(p), st == 2 ? 0.55f : 1.0f);
            snprintf(p, sizeof p, "%sTx", base); ui_visible(p, q < nr);
            if (q < nr) { char tr[64]; cl13_tr(rw[q], tr, sizeof tr); cl13_chip(base, tr, x, 0.0f, 30.0f); x += nr_tw(tr, 30.0f) + 32.0f + 24.0f; }
        }
        snprintf(p, sizeof p, "anim-group.ms.msLad.msB%dF", k);
        nr_bar(p, C13_MS_TX, 1800.0f, y + 253.0f, pick || st == 2 || goal <= 0 ? 0.0f : (float)(cnt < goal ? cnt : goal) / (float)goal);
        if (st == 1) nr_frame_at("anim-group.ms.msLad.msFo", 148.0f, y, 256.0f, 164.0f, !pick);
    }
}
static void cl13_fill_ms_run(void) {
    char b[240], p[170], u[100], un[40];
    clan_t c = clan_get(); meta_t m = meta_get();
    int id = m.mi, cnt = m.mp + g_mis_cnt[id], rep = m.mr[id], top = mis_goal_m(&m, id, 2), reached = 0;
    for (int k = 0; k < 3; k++) if (cnt >= mis_goal_m(&m, id, k)) reached = k + 1;
    int match = 3 - m.ml + 1;                                          // the match we are in (the day calc of the old view)
    if (match < 1) match = 1; else if (match > 3) match = 3;
    cl13_ms_upper(u, sizeof u, MIS[id].name); cl13_ms_upper(un, sizeof un, MIS[id].unit);
    int size = c.h + c.hu + c.s, es = ev_win_start(c.day), ek = es >= 0 ? ev_kind_at(es) : 0;
    int atk = m.mev && ek == 2, sur = m.mev && ek == 1;
    ui_text("anim-group.ms.msTitle", "CURRENT MISSION");
    ui_text("anim-group.ms.msSub", "");
    for (int i = 0; i < C13_MS_ROWS; i++) { snprintf(p, sizeof p, "anim-group.ms.msRow%d", i); ui_visible(p, 0); }
    ui_text("anim-group.ms.msRep", ""); ui_text("anim-group.ms.msRep2", ""); ui_text("anim-group.ms.msStatus", "");
    ui_visible("anim-group.ms.msPrg", 1); ui_visible("anim-group.ms.msLad", 1);
    ui_visible("anim-group.ms.msRunIc", 1); ui_visible("anim-group.ms.msRunNm", 1); ui_visible("anim-group.ms.msPrgDay", 1);
    ui_image("anim-group.ms.msRunIc", cl13_ms_icon(id));
    cl13_fit("anim-group.ms.msRunNm", u, 1180.0f, 69.0f);
    if (reached >= 3) snprintf(b, sizeof b, "COMPLETE");
    else snprintf(b, sizeof b, "%s", atk ? "ENEMY ATTACK - THE FURTHER YOU GET, THE FEWER YOU LOSE" : sur ? "NEW SURVIVORS - THE FURTHER YOU GET, THE MORE JOIN" : "THE FURTHER YOU GET, THE MORE BOOSTERS");
    cl13_clipped("anim-group.ms.msPrgDay", loc_tr(b), 1180.0f, 30.0f, 2);
    snprintf(b, sizeof b, "%d | 3", match); ui_text("anim-group.ms.msPrg.msRunMatch", b);
    for (int k = 0; k < 3; k++) {
        snprintf(p, sizeof p, "anim-group.ms.msPrg.msRunPip%d", k);
        snprintf(b, sizeof b, "streaming/t2r/icons/c13-ms-pip%d.png", k + 1 < match ? 1 : k + 1 == match ? 2 : 0);      // played: filled, this one: ringed + dot, left: outline
        ui_image(p, b);
    }
    snprintf(b, sizeof b, "%d", cnt); ui_text("anim-group.ms.msPrg.msPrgNum", b);
    ui_text("anim-group.ms.msPrg.msPrgLb", un);
    w_pivot(ui_w("anim-group.ms.msPrg.msPrgLb"), 2020.0f + nr_tw(b, 135.0f) + 40.0f, 1224.0f);
    nr_bar("anim-group.ms.msPrg.msBarF", 2020.0f, 3700.0f, 1360.0f, top > 0 ? (float)(cnt < top ? cnt : top) / (float)top : 1.0f);
    for (int k = 0; k < 3; k++) {
        int goal = mis_goal_m(&m, id, k);
        float x = 2020.0f + (top > 0 ? 1680.0f * (float)goal / (float)top : 0.0f);
        snprintf(p, sizeof p, "anim-group.ms.msPrg.msTk%d", k);
        uint64_t w = ui_w(p); if (w) { w_pivot(w, x - 2.0f, 1344.0f); w_alpha(w, cnt >= goal ? 1.0f : 0.47f); }
        snprintf(p, sizeof p, "anim-group.ms.msPrg.msTkLb%d", k);
        snprintf(b, sizeof b, "%d", goal); cl13_lit_text(p, b, cnt >= goal, 0.0f, 0.0f);
        w = ui_w(p); if (w) w_pivot(w, x - 100.0f, 1408.0f);
    }
    cl13_ladder(0, id, cnt, reached, un, atk, sur, es, size, rep);
    if (rep > 0) snprintf(b, sizeof b, "NOTHING IS PAID BELOW TIER 1 - COMPLETED %d TIME%s BEFORE: GOALS ARE HIGHER", rep, rep == 1 ? "" : "S");
    else snprintf(b, sizeof b, "NOTHING IS PAID BELOW TIER 1");
    ui_text("anim-group.ms.msPrg.msFoot", b);
}
static void cl13_fill_ms(const cl13_t *V) {
    (void)V;
    if (cl13_ms_running() && GetFileAttributesA("t2r-clan-ms-old.txt") == INVALID_FILE_ATTRIBUTES) { cl13_fill_ms_run(); return; }
    char b[200], p[170], u[100], un[40];
    clan_t c = clan_get(); meta_t m = meta_get();
    c13grid_t *G = &g_c13g; cl13_grid(T_MS, G);
    cl13_gwin(T_MS, G);
    C13.foc[T_MS] = C13.fr[T_MS];
    ui_visible("anim-group.ms.msPrg", 0);
    ui_text("anim-group.ms.msTitle", "CHOOSE A MISSION");
    ui_text("anim-group.ms.msSub", C13.ms_n ? "YOU HAVE 3 MATCHES TO COMPLETE YOUR MISSION" : "");
    w_pivot(ui_w("anim-group.ms.msSub"), 148.0f + nr_tw(loc_tr("CHOOSE A MISSION"), 39.0f) + 60.0f, 464.0f);
    ui_visible("anim-group.ms.msLad", C13.ms_n > 0); ui_visible("anim-group.ms.msRunIc", C13.ms_n > 0); ui_visible("anim-group.ms.msRunNm", C13.ms_n > 0); ui_visible("anim-group.ms.msPrgDay", C13.ms_n > 0);
    for (int i = 0; i < C13_MS_ROWS; i++) {
        char g[96];
        snprintf(g, sizeof g, "anim-group.ms.msRow%d", i);
        ui_visible(g, i < C13.ms_n);
        if (i >= C13.ms_n) continue;
        int id = C13.ms_rows[i], rep = m.mr[id], lit = i == C13.fr[T_MS] || cl13_hv_is(T_MS, i, 0);
        cl13_tile_bg(g, lit);
        cl13_ms_upper(u, sizeof u, MIS[id].name);
        snprintf(p, sizeof p, "%s.msNm%d", g, i); cl13_lit_text(p, u, lit, 1200.0f, 39.0f);
        snprintf(b, sizeof b, "DONE %dX", rep);
        snprintf(p, sizeof p, "%s.msRp%d", g, i); ui_text(p, rep ? b : "");
    }
    if (!C13.ms_n) return;
    nr_frame_at("anim-group.ms.msLad.msFo", 148.0f - 1872.0f, 560.0f + 128.0f * (float)C13.fr[T_MS] - 380.0f, 1660.0f, 112.0f, C13.tab == T_MS);     // (the outline lives in the ladder group, which sits at its pick offset)
    int id = C13.ms_rows[C13.fr[T_MS]], rep = m.mr[id];
    cl13_ms_upper(u, sizeof u, MIS[id].name); cl13_ms_upper(un, sizeof un, MIS[id].unit);
    ui_image("anim-group.ms.msRunIc", cl13_ms_icon(id));
    cl13_fit("anim-group.ms.msRunNm", u, 1180.0f, 69.0f);
    cl13_clipped("anim-group.ms.msPrgDay", loc_tr("3 MATCHES - THE FURTHER YOU GET, THE MORE YOU WIN"), 1180.0f, 30.0f, 2);
    int size = c.h + c.hu + c.s, es = ev_win_start(c.day), ek = es >= 0 ? ev_kind_at(es) : 0;
    cl13_ladder(1, id, -1, 0, un, ek == 2, ek != 2, es, size, rep);
    if (ek == 2) snprintf(b, sizeof b, "NO MARK: LOSE %d%%", ev_loss_pct(es, 0)); else snprintf(b, sizeof b, "NOTHING IS PAID BELOW THE FIRST TIER.");
    ui_text("anim-group.ms.msRep", b);
    if (rep > 0) snprintf(b, sizeof b, "COMPLETED %d TIME%s BEFORE: THE GOALS ARE HIGHER.", rep, rep == 1 ? "" : "S"); else b[0] = 0;
    ui_text("anim-group.ms.msRep2", b);
    ui_text("anim-group.ms.msStatus", C13.ms_chosen ? "MISSION STARTED" : "");
}
// ------------------------------------------------------------------ JOURNAL: week pages. The left column is ONE week
// (< WEEK n OF 12 >, its won / lost count) with a row per clan day - day, headline, map, verdict, supplies / need; the right pane is the focused day: headline, two lines of facts
// (raid, supplies, the clan's counts after the day) and the entry's paragraphs, each under its caption. The paragraphs are wrapped HERE (cl13_wrap: explicit line breaks at 88 % of the
// box, so the engine never wraps again and the line count is known) and stacked by their real heights. Data: section 6 (every day's index row + the text of the shown week).
static int cl13_jw(const cl13_t *V) { int top = V && V->jtop > 0 ? V->jtop : 1; return C13.jw >= 1 && C13.jw <= top ? C13.jw : top; }      // the week shown (C13.jw 0 = the newest)
static void cl13_jw_follow(const char *why) {                        // the journal's focused row is a week: its paragraphs are asked for at once
    const cl13_t *V = C13.V;
    c13grid_t G; cl13_grid(T_JR, &G);
    if (!V || C13.fr[T_JR] < 0 || C13.fr[T_JR] >= G.nrow) return;
    int w = G.key[C13.fr[T_JR]];
    if (w == cl13_jw(V)) return;
    C13.jw = w; C13.next_ask[6] = 0; C13.ok_at[6] = 0; C13.det_key = -1;
    xlog("clan13: journal week %d of %d (%s)", w, V->jtop, why);
}
static size_t cl13_app(char *b, size_t cap, size_t o, const char *fmt, ...) {      // append to b at o, never past cap; returns the new length
    if (o + 1 >= cap) return o;
    va_list ap; va_start(ap, fmt);
    int k = vsnprintf(b + o, cap - o, fmt, ap);
    va_end(ap);
    if (k < 0) return o;
    return o + (size_t)k < cap ? o + (size_t)k : cap - 1;
}
static void cl13_fill_jr_day(const cl13_t *V, const cl13_d_t *e) {
    static const char *const PC[C13_JP] = {"anim-group.jrn.jtPane.jtCap0", "anim-group.jrn.jtPane.jtCap1", "anim-group.jrn.jtPane.jtCap2", "anim-group.jrn.jtPane.jtCap3", "anim-group.jrn.jtPane.jtCap4"};
    static const char *const PB[C13_JP] = {"anim-group.jrn.jtPane.jtBo0", "anim-group.jrn.jtPane.jtBo1", "anim-group.jrn.jtPane.jtBo2", "anim-group.jrn.jtPane.jtBo3", "anim-group.jrn.jtPane.jtBo4"};
    char b[600], t[96], v[96];
    if (!e) return;
    int wk = cl13_jw(V);
    if (e->day > 0) snprintf(b, sizeof b, "%s %d  |  %s %d", loc_tr("WEEK"), wk, loc_tr("DAY"), e->dow); else snprintf(b, sizeof b, "%s 1  |  %s", loc_tr("WEEK"), loc_tr("THE START"));
    nr_section("anim-group.jrn.jtPane.jtS", 2400.0f, 3700.0f, 464.0f, b, "", 36.0f);
    cl13_fit("anim-group.jrn.jtPane.jtTitle", e->title, 1300.0f, 57.0f);
    size_t o = 0;                                                       // facts, line 1: the raid and the supplies (grey labels, white values)
    b[0] = 0;
    if (e->map[0]) {
        cl13_upper(t, sizeof t, e->map);
        v[0] = 0; if (e->win >= 0) snprintf(v, sizeof v, "   <font color=\"#8C8C8C\">%s</font>", loc_tr(e->win ? "WON" : "LOST"));
        o = cl13_app(b, sizeof b, o, "<font color=\"#8C8C8C\">%s</font>   %s%s", loc_tr("RAID"), t, v);
    }
    if (e->need > 0) o = cl13_app(b, sizeof b, o, "%s<font color=\"#8C8C8C\">%s</font>   %d | %d", o ? "      " : "", loc_tr("SUPPLIES"), e->sup, e->need);
    ui_text("anim-group.jrn.jtPane.jtF0", b);
    b[0] = 0; o = 0;                                                    // line 2: the clan after the day (an entry from before the day entries has no counts)
    if (e->h >= 0) {
        int n = e->h + e->u + e->s;
        o = cl13_app(b, sizeof b, o, "%d <font color=\"#8C8C8C\">%s</font>", n, loc_tr("SURVIVORS"));
        if (e->dn) o = cl13_app(b, sizeof b, o, " (%+d)", e->dn);
        o = cl13_app(b, sizeof b, o, "      %d <font color=\"#8C8C8C\">%s</font>", e->h, loc_tr("HEALTHY"));
        o = cl13_app(b, sizeof b, o, "      %d <font color=\"#8C8C8C\">%s</font>", e->u, loc_tr("HUNGRY"));
        o = cl13_app(b, sizeof b, o, "      %d <font color=\"#8C8C8C\">%s</font>", e->s, loc_tr("SICK"));
    }
    g_ui_text_raw = 1; ui_text("anim-group.jrn.jtPane.jtF1", b); g_ui_text_raw = 0;     // (pre-translated pieces: the line itself is no table entry)
    int pi[C13_NG], np = V->jweek == wk ? cl13_day_paras(V, e->day, pi, C13_NG) : 0, wait = V->jweek != wk;      // (the text of another week is on its way: LOADING)
    float y = C13_JT_Y0;
    static char src[4200], out[2400];
    for (int k = 0; k < C13_JP; k++) {
        int room = (int)((C13_JT_Y1 - y - C13_JT_CAP_H) / C13_JT_LINE);
        int on = (k < np || (wait && k == 0)) && room >= 1;
        ui_visible(PC[k], on); ui_visible(PB[k], on);
        if (!on) continue;
        const char *cap = "";
        if (wait) snprintf(src, sizeof src, "%s", loc_tr("LOADING..."));
        else {
            cap = V->g[pi[k]].cap;
            size_t so = cl13_app(src, sizeof src, 0, "%s", V->g[pi[k]].text);
            if (k == C13_JP - 1) for (int q = C13_JP; q < np; q++) so = cl13_app(src, sizeof src, so, "\n\n%s", V->g[pi[q]].text);      // more paragraphs than slots (two matches on one clan day): the rest follows here
        }
        int n = cl13_wrap(out, sizeof out, src, C13_JT_W * 0.88f, C13_JT_PT, room, cl13_est);
        uint64_t wc = ui_w(PC[k]), wb = ui_w(PB[k]);
        if (wc) w_pivot(wc, C13_JT_X, y);
        if (wb) w_pivot(wb, C13_JT_X, y + C13_JT_CAP_H);
        ui_text(PC[k], cap); ui_text(PB[k], out);
        y += C13_JT_CAP_H + (float)n * C13_JT_LINE + C13_JT_GAP;
    }
}
static void cl13_fill_jr(const cl13_t *V) {
    char b[260], p[200], t[160], g[96];
    c13grid_t *G = &g_c13g; cl13_grid(T_JR, G);
    if (!C13.jr_init && G->nrow) { C13.jr_init = 1; C13.fr[T_JR] = 0; C13.fc[T_JR] = G->ncol[0] - 1; C13.want[T_JR] = C13.fc[T_JR]; }      // the tab opens on the newest entry
    int f = cl13_gwin(T_JR, G);
    cl13_jw_follow("fill");
    for (int vr = 0; vr < 3; vr++) {
        int r = C13.roff[T_JR] + vr;
        snprintf(g, sizeof g, "anim-group.jrn.jrR%d", vr);
        ui_visible(g, r < G->nrow);
        if (r >= G->nrow) continue;
        int nc = G->ncol[r], co = C13.coff[T_JR][r], act = r == C13.fr[T_JR], won = 0, lost = 0;
        for (int c = 0; c < nc; c++) { const cl13_d_t *e = &V->d[G->item[r][c]]; if (e->win == 1) won++; else if (e->win == 0) lost++; }
        snprintf(t, sizeof t, act ? "%s %d  <font color=\"#8C8C8C\">%s</font>" : "<font color=\"#8C8C8C\">%s %d  %s</font>", loc_tr("WEEK"), G->key[r], loc_tr("OF 12"));
        snprintf(b, sizeof b, "%d | %d  %s", won, lost, loc_tr("WON | LOST"));
        snprintf(p, sizeof p, "%s.jrS%d", g, vr);
        g_ui_text_raw = 1; nr_section(p, 148.0f, 2260.0f, 0.0f, t, b, 36.0f); g_ui_text_raw = 0;
        for (int c = 0; c < 7; c++) {
            int ci = co + c;
            snprintf(p, sizeof p, "%s.jd%d_%d", g, vr, c);
            ui_visible(p, ci < nc);
            if (ci >= nc) continue;
            const cl13_d_t *e = &V->d[G->item[r][ci]];
            int foc = act && ci == C13.fc[T_JR], lit = foc || cl13_hv_is(T_JR, vr, c);
            char q[220];
            cl13_tile_bg(p, lit);
            snprintf(q, sizeof q, "%s.jd%d_%dDy", p, vr, c);
            if (e->day > 0) { snprintf(b, sizeof b, "DAY %d", e->dow); ui_text(q, b); } else ui_text(q, "THE START");
            snprintf(q, sizeof q, "%s.jd%d_%dD", p, vr, c); ui_visible(q, e->fresh);
            if (e->map[0]) cl13_upper(t, sizeof t, e->map); else snprintf(t, sizeof t, "%s", e->title);
            snprintf(q, sizeof q, "%s.jd%d_%dM", p, vr, c); cl13_lit_text(q, t, lit, 232.0f, 22.0f);
            snprintf(q, sizeof q, "%s.jd%d_%dW", p, vr, c);
            if (e->win >= 0) cl13_lit_text(q, loc_tr(e->win ? "WON" : "LOST"), lit || (act && e->win == 1), 0.0f, 0.0f); else ui_text(q, "");
            snprintf(q, sizeof q, "%s.jd%d_%dB", p, vr, c); ui_visible(q, e->win >= 0);
            if (e->win >= 0) w_alpha(ui_w(q), e->win == 1 ? (act ? 0.9f : 0.43f) : 0.16f);
        }
    }
    int fv = C13.fr[T_JR] - C13.roff[T_JR], fcv = C13.fc[T_JR] - C13.coff[T_JR][C13.fr[T_JR] < C13_GR ? C13.fr[T_JR] : 0];
    nr_frame_at("anim-group.jrn.jrFo", 148.0f + 304.0f * (float)fcv, 464.0f + 476.0f * (float)fv + 52.0f, 280.0f, 352.0f, f >= 0 && C13.tab == T_JR);
    nr_scroll_v("anim-group.jrn.jrSb", 2288.0f, 464.0f, 1860.0f, 698.0f, C13.roff[T_JR], 3, G->nrow);
    ui_visible("anim-group.jrn.jtPane", f >= 0);
    if (f >= 0 && !C13.det_hold) cl13_fill_jr_day(V, &V->d[f]);
}
static int cl13_rows_of(int tab) {                                   // the tab has something to focus
    if (!C13.V) return 0;
    c13grid_t G; cl13_grid(tab, &G);
    return G.nrow;
}
// the sections a tab needs before it can be shown
static int cl13_have(const cl13_t *V, int tab) {
    if (tab == T_OV) return V->have[1] && V->have[2] && V->have[3] && V->have[4];
    if (tab == T_SV) return V->have[1];
    if (tab == T_MS) return meta_get().ok;                              // the pick runs on the booster / mission data (op 0xE8), not on the clan sections
    if (tab == T_RD) return V->have[3];
    return V->have[6];                                                   // (the journal's week pages)
}
static int cl13_pick_due(void) {                                     // a mission is to be chosen now (feature_missions' offer rule): the clan is alive, none runs, an event is in its three matches
    clan_t c = clan_get(); meta_t m = meta_get();
    return c.ok && c.st == 1 && c.fac && m.ok && !m.mi && ev_win_start(c.day) >= 0;
}
static const char *cl13_msg(const cl13_t *V) {
    if (C13.tab == T_MS) {
        static char b[120];
        meta_t m = meta_get();
        if (!m.ok) return "LOADING THE MISSIONS";
        if (cl13_ms_running() && GetFileAttributesA("t2r-clan-ms-old.txt") == INVALID_FILE_ATTRIBUTES) return "";   // (the running mission's status page, cl13_fill_ms_run)
        if (m.mi && MIS_VALID(m.mi) && !C13.ms_chosen) { snprintf(b, sizeof b, "MISSION RUNNING: %s", MIS[m.mi].name); for (char *q = b + 17; *q; q++) if (*q >= 'a' && *q <= 'z') *q = (char)(*q - 32); return b; }
        if (!C13.ms_n && !C13.ms_chosen) return "NO MISSION TO CHOOSE RIGHT NOW - THE NEXT CLAN EVENT BRINGS ONE";
        return "";
    }
    if (!cl13_have(V, C13.tab)) return !g_clan_busy && g_clan_fail >= 2 ? "THE SERVER DID NOT ANSWER" : "LOADING THE CLAN";
    if (!V->ok) return "YOU HAVE NO CLAN YET";
    if (C13.tab == T_SV && V->np == 0) return "THE CLAN HAS NO MEMBERS YET";
    if (C13.tab == T_JR && V->nd == 0) return "NOTHING IS WRITTEN IN THE JOURNAL YET";
    return "";
}
// ------------------------------------------------------------------ the entrance script of the shown tab (what comes from where and when: re/clan-ui-motion.md section 4)
static void cl13_fx_build(const cl13_t *V) {
    (void)V;
    cl13_fx_reset();
    if (C13.fx_first) cl13_fx_add("anim-group.tabs", 0.0f, 0.0f, 6, 60.0f);
    static const char *const G[C13_NTAB] = {"anim-group.ov", "anim-group.sv", "anim-group.rds", "anim-group.jrn", "anim-group.ms"};
    static const char *const D[C13_NTAB] = {"anim-group.ov.ovDt", "anim-group.sv.svDt", "anim-group.rds.rdDt", "anim-group.jrn.jtPane", "anim-group.ms.msPrg"};
    char p[120];
    if (C13.tab == T_SV || C13.tab == T_RD || C13.tab == T_JR) {      // the tile rows come in from the left one after another, the detail column from the right
        static const char *const R[C13_NTAB] = {"", "anim-group.sv.svR%d", "anim-group.rds.rdR%d", "anim-group.jrn.jrR%d", ""};
        static const float Y0[C13_NTAB] = {0, 564, 564, 464, 0}, DY[C13_NTAB] = {0, 428, 540, 476, 0};
        for (int r = 0; r < C13_VROWS[C13.tab]; r++) { snprintf(p, sizeof p, R[C13.tab], r); cl13_fx_add(p, 0.0f, Y0[C13.tab] + DY[C13.tab] * (float)r, 1, 80.0f + 90.0f * (float)r); }
        static const char *const FO[C13_NTAB] = {"", "anim-group.sv.svFo", "anim-group.rds.rdFo", "anim-group.jrn.jrFo", ""};      // the focus outline fades in with its row (it was up at full strength before its tile)
        int fv = C13.fr[C13.tab] - C13.roff[C13.tab]; if (fv < 0) fv = 0; if (fv >= C13_VROWS[C13.tab]) fv = C13_VROWS[C13.tab] - 1;
        for (int k = 0; k < 4; k++) { snprintf(p, sizeof p, "%s%c", FO[C13.tab], "TBLR"[k]); cl13_fx_add(p, 0.0f, 0.0f, 6, 80.0f + 90.0f * (float)fv + 120.0f); }      // (four side rects: nr_frame_at)
    } else cl13_fx_add(G[C13.tab], 0.0f, 0.0f, 1, 60.0f);
    if (C13.tab != T_OV && C13.tab != T_MS) cl13_fx_add(D[C13.tab], 0.0f, 0.0f, 2, 300.0f);
    uint64_t now = GetTickCount64();
    C13.t0 = now;
    for (int i = 0; i < C13.nfx; i++) {                                // invisible until their turn (no flash at full strength first)
        uint64_t w = ui_w(C13.fx[i].path);
        C13.fx[i].w = w;
        if (w) { w_alpha(w, 0.0f); if (C13.fx[i].kind != 6) w_pivot(w, C13.fx[i].bx + (C13.fx[i].kind == 1 ? -96.0f : C13.fx[i].kind == 2 ? 96.0f : 0.0f), C13.fx[i].by); }
    }
    C13.hd_done = 1;
    C13.fx_pending = 0; C13.fx_first = 0; C13.played[C13.tab] = 1; C13.intro_played = 1;
    ui_sfx("sfx-hud-rl-score-screen-enter");                            // the NR screen-enter cue
}
// ------------------------------------------------------------------ MATCH STATS: every player of the focused raid's match (F / the pad's menu-action on RAIDS; daemon op 0xB6 section 5)
static void cl13_xs_num(char *o, size_t n, int v) { if (v < 0) snprintf(o, n, "0"); else snprintf(o, n, "%d", v); }
// ------------------------------------------------------------------ PLAYER STATS = the SCOREBOARD (proposal A)
// One table: a column-head row (PLAYER AWARD DOWNS EXECUTIONS REVIVES HEADSHOTS DEATHS PARTS), a section row per team (US / THE ENEMY, MATCH WON / LOST, the team totals in the same
// columns), then one row per player (rank badge, name, YOU / LEFT, MOST <STAT> for a stat's leader, five stat columns, PARTS). A stat's leader shows its number in the stat's colour;
// a zero / unreported value is a dim "0"; a player who LEFT is dimmed. The row pool is flat (C13_NX groups xpRow<k>, US rows first); every row is placed by the ext (design = clan13_widgets.py XP_*):
// up to 8 players on a 112 pitch (104 high), more on an 80 pitch (76 high) so that 12 fit. The entrance (NR post-score spec, re/nr_ui_1102/nr-ui-behaviours.md): the head row fades in,
// then the rows reveal top to bottom from 250 ms after the page opened, 120 ms apart (alpha + a 24 unit slide from the left, 180 ms), each row's numbers counting up from 0 over 450 ms (PARTS 700 ms);
// the count is written only when its integer moves, at most every 50 ms, and a number is never blanked. A data refresh only writes what changed (ui_text dedups by content).
#define C13_XP_X0 148.0f                                                // = clan13_widgets.py XP_X0 / XP_SEC_Y; section row -> its first player row; gap after a section
#define C13_XP_SEC_Y 560
#define C13_XP_HD_GAP 100
#define C13_XP_SEC_GAP 40
static struct {
    uint64_t t0; uint32_t sig; int snd, endsnd, fin, n, cnt[2], pitch, rh, top[C13_NAW], tot[2][C13_NAW], win, mine;
    int si[C13_NX], ssec[C13_NX], sfirst[2]; float ry[C13_NX], secy[2];
} XP;
static const int XP_COLSTAT[5] = {0, 1, 2, 3, 5};                      // the five stat columns -> stat index (DOWNS EXECUTIONS REVIVES HEADSHOTS DEATHS); PARTS = stat 4
static void cl13_xp_reset(void) { memset(&XP, 0, sizeof XP); }
static void cl13_xp_thou(char *o, size_t n, int v) { if (v >= 1000) snprintf(o, n, "%d %03d", v / 1000, v % 1000); else snprintf(o, n, "%d", v); }
// one number cell (white / grey only): 0 grey, a player who left grey, else white (the award column names the leaders)
static void cl13_xp_cell(char *o, size_t n, int v, int stat, int leader, int fin, int left) {
    (void)stat; (void)leader; (void)fin;
    if (v <= 0) { snprintf(o, n, "<font color=\"#8C8C8C\">0</font>"); return; }      // a zero is "0", never "-"
    char d[24]; cl13_xp_thou(d, sizeof d, v);
    if (left) snprintf(o, n, "<font color=\"#8C8C8C\">%s</font>", d);
    else snprintf(o, n, "%s", d);
}
// the static part of a row slot (what does not move with the clock): the tile, the own row's accent edge, rank badge, name, YOU / LEFT, award
static void cl13_xp_slot_static(const cl13_t *V, int k, const cl13_aw_t *aw) {
    char g[64], p[96], b[200], t1[96], t2[96];
    const cl13_x_t *x = &V->x[XP.si[k]];
    snprintf(g, sizeof g, "anim-group.mst2.xpRow%d", k);
    int compact = XP.rh < 100;
    float by = compact ? 14.0f : 0.0f, sy = compact ? (float)XP.rh / 104.0f : 1.0f;
    snprintf(p, sizeof p, "%s.xpBg%d", g, k); { uint64_t w = ui_w(p); if (w) { w_pivot(w, 0.0f, by); w_scale(w, 1.0f, sy); w_alpha(w, (x->me ? 215.0f : 175.0f) / 255.0f); } }
    snprintf(p, sizeof p, "%s.xpMe%d", g, k); ui_visible(p, x->me); { uint64_t w = ui_w(p); if (w) { w_pivot(w, 0.0f, by); w_scale(w, 1.0f, sy); } }
    { char ri[120], rn[120]; snprintf(ri, sizeof ri, "%s.xpRk%d", g, k); snprintf(rn, sizeof rn, "%s.xpRn%d", g, k); rank_ui(ri, rn, x->rk, x->wk); }
    snprintf(p, sizeof p, "%s.xpNm%d", g, k);
    cl13_fit(p, x->name, 740.0f - (x->me || x->left ? 150.0f : 0.0f), 39.0f);
    if (x->left) { snprintf(b, sizeof b, "<font color=\"#8C8C8C\">%s</font>", x->name); ui_text(p, b); } else ui_text(p, x->name);
    snprintf(p, sizeof p, "%s.xpTg%d", g, k);
    if (x->me || x->left) {
        float w = nr_tw(x->name, 39.0f), wf = 24.0f * (float)strlen(x->name); if (w < wf) w = wf; if (w > 740.0f - 150.0f) w = 740.0f - 150.0f;   // (the floor keeps a clear gap: the game's face runs wider than the estimate on short names)
        cl13_tr(x->me ? "YOU" : "LEFT", t1, sizeof t1);
        snprintf(b, sizeof b, "<font color=\"#%s\">%s</font>", x->me ? "D9D86A" : "8C8C8C", t1); ui_text(p, b);
        uint64_t tw = ui_w(p); if (tw) w_pivot(tw, 171.0f + w + 36.0f, 52.0f);
    } else ui_text(p, "");
    const cl13_aw_t *a = &aw[XP.si[k]];
    snprintf(p, sizeof p, "%s.xpAw%d", g, k);
    if (a->stat >= 0 && a->lead && !x->left) {
        cl13_tr("MOST", t1, sizeof t1); cl13_tr(cl13_aw_word(a->stat), t2, sizeof t2);
        snprintf(b, sizeof b, "%s %s", t1, t2); g_ui_text_raw = 1; ui_text(p, b); g_ui_text_raw = 0;
    } else ui_text(p, "");
    snprintf(p, sizeof p, "%s.xpPm%d", g, k); ui_visible(p, x->me);
    snprintf(p, sizeof p, "%s.xpP%d", g, k); ui_visible(p, !x->me);
}
// the numbers of one slot at count fraction f / fp (PARTS), fin = the final strings
static void cl13_xp_slot_nums(const cl13_t *V, int k, float f, float fp, int fin) {
    char g[64], p[96], b[100];
    const cl13_x_t *x = &V->x[XP.si[k]];
    snprintf(g, sizeof g, "anim-group.mst2.xpRow%d", k);
    for (int c = 0; c < 5; c++) {
        int s = XP_COLSTAT[c], v = cl13_xv(x, s), shown = fin ? v : (int)((float)v * f + 0.5f);
        cl13_xp_cell(b, sizeof b, shown, s, s != 5 && v > 0 && v == XP.top[s], fin, x->left);
        snprintf(p, sizeof p, "%s.xpV%d_%d", g, c, k); ui_text(p, b);
    }
    int pv = x->parts, ps = fin ? pv : (int)((float)pv * fp + 0.5f);
    cl13_xp_cell(b, sizeof b, ps, 4, 0, fin, x->left);
    snprintf(p, sizeof p, "%s.%s%d", g, x->me ? "xpPm" : "xpP", k); ui_text(p, b);
}
static void cl13_xp_sec_nums(int sec, float f, float fp, int fin) {
    char p[96], b[40];
    for (int c = 0; c < 5; c++) {
        int v = XP.tot[sec][XP_COLSTAT[c]], shown = fin ? v : (int)((float)v * f + 0.5f);
        if (shown > 0) cl13_xp_thou(b, sizeof b, shown); else snprintf(b, sizeof b, "0");
        snprintf(p, sizeof p, "anim-group.mst2.xpSec%d.xpT%d_%d", sec, c, sec); ui_text(p, b);
    }
    int v = XP.tot[sec][4], shown = fin ? v : (int)((float)v * fp + 0.5f);
    if (shown > 0) cl13_xp_thou(b, sizeof b, shown); else snprintf(b, sizeof b, "0");
    snprintf(p, sizeof p, "anim-group.mst2.xpSec%d.xpTP%d", sec, sec); ui_text(p, b);
}
static float cl13_xp_q(float a) { int q = (int)(a * 24.0f + 0.5f); return (float)q / 24.0f; }
static int cl13_xp_busy(void) { return XP.sig && !XP.fin; }            // the entrance / the count is running: the page's tick fills every frame
static void cl13_fill_xp(const cl13_t *V, int on) {
    if (!g_c13x.seen) return;                                           // (only the stats page itself fills it: the clan page under it has none of these widgets, and its clock must not start early)
    ui_visible("anim-group.mst2", on);
    if (!on) return;
    char b[260], t1[96], p[220];
    int n = C13.xs_got && V->xday == C13.xs_day ? V->xn : 0, mine = -1;
    for (int i = 0; i < n; i++) if (V->x[i].me) mine = V->x[i].team;
    snprintf(b, sizeof b, "DAY %d", C13.xs_post ? (C13.xs_day - 1 < 0 ? 0 : C13.xs_day - 1 > 83 ? 83 : C13.xs_day - 1) % 7 + 1 : cl13_dow(C13.xs_day)); cl13_tr(b, t1, sizeof t1);
    snprintf(b, sizeof b, "%s   -   %s", t1, C13.xs_map);
    ui_text("anim-group.mst2.xpSub", b);
    const char *em = !C13.xs_got ? "LOADING..." : n ? "" : "NO PLAYER STATS WERE RECORDED FOR THIS MATCH.\nONLY MATCHES PLAYED AFTER THE LATEST SERVER UPDATE ARE LISTED.";
    ui_text("anim-group.mst2.xpEmpty", em);
    ui_visible("anim-group.mst2.xpEmpty", em[0] != 0);
    ui_visible("anim-group.mst2.xpHead", n > 0);
    if (n <= 0) {                                                       // nothing to show (yet): the table is empty
        ui_visible("anim-group.mst2.xpSec0", 0); ui_visible("anim-group.mst2.xpSec1", 0);
        for (int k = 0; k < C13_NX; k++) { snprintf(p, sizeof p, "anim-group.mst2.xpRow%d", k); ui_visible(p, 0); }
        XP.sig = 0; XP.n = 0;
        return;
    }
    uint64_t now = GetTickCount64();
    uint32_t sig = 2166136261u;
    for (size_t i = 0; i < (size_t)n * sizeof(cl13_x_t); i++) sig = (sig ^ ((const uint8_t *)V->x)[i]) * 16777619u;
    sig = (sig ^ (uint32_t)(mine + 3)) * 16777619u; sig = (sig ^ (uint32_t)(C13.xs_win + 3)) * 16777619u; sig = (sig ^ (uint32_t)n) * 16777619u;
    if (sig == XP.sig && XP.fin) return;                                // nothing moved, nothing counting: no writes at all
    if (!XP.t0) XP.t0 = now;
    int anim = !cl13_anim_off();
    if (sig != XP.sig) {                                                // a new (or refreshed) data set: order, place and write the static parts
        cl13_aw_t aw[C13_NX]; memset(aw, 0, sizeof aw);
        cl13_awards(V->x, n, aw);
        memset(XP.top, 0, sizeof XP.top); memset(XP.tot, 0, sizeof XP.tot);
        for (int i = 0; i < n; i++) for (int s = 0; s < C13_NAW; s++) { int v = cl13_xv(&V->x[i], s); if (v > XP.top[s]) XP.top[s] = v; if (v > 0) XP.tot[cl13_sect(&V->x[i], mine)][s] += v; }
        int idx[2][C13_NX], k = 0;
        XP.cnt[0] = cl13_order(V->x, n, mine, 0, idx[0]); XP.cnt[1] = cl13_order(V->x, n, mine, 1, idx[1]);
        XP.n = XP.cnt[0] + XP.cnt[1]; XP.win = C13.xs_win; XP.mine = mine;
        XP.pitch = XP.n <= 8 ? 112 : 80; XP.rh = XP.n <= 8 ? 104 : 76;
        int y = C13_XP_SEC_Y;
        for (int sec = 0; sec < 2; sec++) {
            XP.sfirst[sec] = k; XP.secy[sec] = (float)y;
            if (!XP.cnt[sec]) continue;
            int r0 = y + C13_XP_HD_GAP;
            for (int r = 0; r < XP.cnt[sec]; r++, k++) { XP.si[k] = idx[sec][r]; XP.ssec[k] = sec; XP.ry[k] = (float)(r0 + r * XP.pitch - (XP.rh < 100 ? 14 : 0)); }
            y = r0 + XP.cnt[sec] * XP.pitch + C13_XP_SEC_GAP;
        }
        for (int sec = 0; sec < 2; sec++) {
            char g[64], hd[96];
            snprintf(g, sizeof g, "anim-group.mst2.xpSec%d", sec);
            ui_visible(g, XP.cnt[sec] > 0);
            uint64_t gw = ui_w(g);
            if (gw) w_pivot(gw, 0.0f, XP.secy[sec] - (float)C13_XP_SEC_Y);
            cl13_tr(mine < 0 ? (sec ? "TEAM 2" : "TEAM 1") : sec ? "THE ENEMY" : "US", hd, sizeof hd);
            snprintf(p, sizeof p, "%s.xpHd%d", g, sec); ui_text(p, hd);
            const char *tg = "";
            if (mine >= 0 && (C13.xs_win == 0 || C13.xs_win == 1)) tg = (C13.xs_win == 1) == (sec == 0) ? "MATCH WON" : "<font color=\"#8C8C8C\">MATCH LOST</font>";
            snprintf(p, sizeof p, "%s.xpTag%d", g, sec); ui_text(p, tg);
            float tx = C13_XP_X0 + nr_tw(hd, 39.0f) + 40.0f, rx = tx + (tg[0] ? nr_tw(tg, 27.0f) + 40.0f : 0.0f);
            uint64_t tw = ui_w(p); if (tw) w_pivot(tw, tx, (float)C13_XP_SEC_Y);   // (the group carries the y offset)
            snprintf(p, sizeof p, "%s.xpRule%d", g, sec); nr_rule(p, rx, (float)C13_XP_SEC_Y, C13_XP_X0 + 1980.0f - 320.0f - rx);      // the hairline up to the totals
        }
        for (int q = 0; q < C13_NX; q++) {
            snprintf(p, sizeof p, "anim-group.mst2.xpRow%d", q);
            if (q < XP.n) {
                cl13_xp_slot_static(V, q, aw);
                uint64_t rw = ui_w(p);
                if (rw && !XP.fin && anim) { w_alpha(rw, 0.0f); w_pivot(rw, C13_XP_X0 - 24.0f, XP.ry[q]); }
                ui_visible(p, 1);
            } else ui_visible(p, 0);
        }
        XP.sig = sig;
    }
    // ---- the clock: the head row at once, slot k from 250 + 120 k ms
    float el0 = (float)(now - XP.t0);
    float last = 250.0f + 120.0f * (float)(XP.n > 0 ? XP.n - 1 : 0) + 800.0f;
    int fin = !anim || el0 >= last;
    uint64_t hw = ui_w("anim-group.mst2.xpHead");
    if (hw) w_alpha(hw, fin ? 1.0f : cl13_xp_q(cl13_eo(el0 / 220.0f)));
    float qel = (float)(((now - XP.t0) / 50) * 50);                     // the count moves in 50 ms steps (a gui2 text written every frame misses draws)
    for (int sec = 0; sec < 2; sec++) {
        if (!XP.cnt[sec]) continue;
        float tk = 250.0f + 120.0f * (float)XP.sfirst[sec], e = fin ? 1.0f : cl13_eo((el0 - tk) / 180.0f);
        char g[64]; snprintf(g, sizeof g, "anim-group.mst2.xpSec%d", sec);
        uint64_t gw = ui_w(g); if (gw) w_alpha(gw, fin ? 1.0f : cl13_xp_q(e));
        cl13_xp_sec_nums(sec, cl13_eo((qel - tk) / 450.0f), cl13_eo((qel - tk) / 700.0f), fin);
    }
    for (int k = 0; k < XP.n; k++) {
        float tk = 250.0f + 120.0f * (float)k, e = fin ? 1.0f : cl13_eo((el0 - tk) / 180.0f);
        char g[64]; snprintf(g, sizeof g, "anim-group.mst2.xpRow%d", k);
        uint64_t rw = ui_w(g);
        if (rw) { w_alpha(rw, fin ? 1.0f : cl13_xp_q(e)); w_pivot(rw, C13_XP_X0 - 24.0f * (1.0f - e), XP.ry[k]); }
        cl13_xp_slot_nums(V, k, cl13_eo((qel - tk) / 450.0f), cl13_eo((qel - tk) / 700.0f), fin);
    }
    if (g_c13x.post && anim && !XP.snd) { XP.snd = 1; pms_count_start((int)(last - 250.0f)); }       // post-match: No Return's rolling count while the numbers run
    if (fin && !XP.fin && g_c13x.post && anim) { pms_count_cut(60); pms_play(PMSK_END); }              // ... and its accent when they land
    if (fin) XP.fin = 1;
}
static void cl13_fill_xs(const cl13_t *V, int show) {
    cl13_fill_xp(V, show && C13.xs_open);
}
static void cl13_xs_open(const char *how) {
    const cl13_t *V = C13.V;
    int f = C13.foc[T_RD];
    if (C13.xs_open || !V || f < 0 || f >= V->nm) return;
    C13.xs_open = 1; C13.xs_day = V->m[f].day; C13.xs_win = V->m[f].win; C13.xs_got = C13.xs_wait = 0; C13.xs_tries = 0; C13.xs_next = 0;
    snprintf(C13.xs_map, sizeof C13.xs_map, "%s", V->m[f].map);
    cl13_xp_reset();
    g_cl13_view.xday = 0; g_cl13_view.xn = 0; g_cl13_view.have[5] = 0;       // (the snapshot may still hold another raid's list)
    C13.dirty = 1; cl13_sfx();
    g_c13x.on = 1; g_c13x.seen = 0; g_c13x.f0 = g_frame; g_c13x.h_act = g_c13x.h_f = g_c13x.h_esc = 1;   // (keys held from the press that opened it do not close it)
    push_page("to1/clan13x");
    xlog("clan13: match stats opened for the raid of day %d (%s) - pushing to1/clan13x", C13.xs_day, how);
}
static void cl13_xs_close(const char *how) {
    g_c13x.on = 0;
    if (!C13.xs_open) return;
    C13.xs_open = 0; C13.xs_wait = 0; C13.dirty = 1; cl13_sfx();
    xlog("clan13: match stats closed (%s)", how);
}
// ------------------------------------------------------------------ POST-MATCH SCOREBOARD: the same page as PLAYER STATS, pushed by feature_clan (t2r-ext.c) on the MP menu after a clan
// match, before the supply counter. Data: the day's match stats from the daemon (section 5, asked again until the server has booked the match). It counts up with
// No Return's rolling count sound; confirm / Enter / pad A / click CONTINUE: the first press finishes the count, the next one leaves. Back / Esc / F leave at once.
static int cl13_post_open(int day, int won, const char *map) {
    if (!cl13_enabled() || g_c13x.on) return 0;
    uint64_t now = GetTickCount64();
    memset(&C13, 0, sizeof C13);
    C13.V = &g_cl13_view;
    C13.enter_ms = now; C13.dirty = 1; C13.prev_tab = -1; C13.fx_first = 1; C13.det_key = -1; C13.t0 = now;
    C13.t_u = C13.t_d = C13.t_l = C13.t_r = ~0ULL; C13.hv_row = C13.hv_tab = -1;
    C13.h_sel = C13.h_u = C13.h_d = C13.h_l = C13.h_r = C13.h_back = C13.h_esc = C13.h_pv = C13.h_nx = C13.h_ka = C13.h_kd = C13.h_act = C13.h_f = 1;
    cl13_seen_load();
    for (int s = 1; s <= 6; s++) C13.seen_ver[s] = (int)g_cl13_ver[s];
    memset(&g_cl13_view, 0, sizeof g_cl13_view);
    cl13_pic_reset();
    cl13_xp_reset();
    C13.xs_open = 1; C13.xs_post = 1; C13.xs_t0 = now; C13.xs_day = day + 1;      // the server books a match under the clan's day AFTER it (clan_chronicle log d = days done once resolved); day = days done before (t2r-ext g_pm.day) - tools/tests/test_clan_post_day.py
     C13.xs_win = won; C13.xs_got = C13.xs_wait = 0; C13.xs_tries = 0; C13.xs_next = 0;
    snprintf(C13.xs_map, sizeof C13.xs_map, "%s", map && map[0] ? map : "MATCH");
    g_c13x.on = 1; g_c13x.post = 1; g_c13x.seen = 0; g_c13x.f0 = g_frame; g_c13x.h_act = g_c13x.h_f = g_c13x.h_esc = g_c13x.h_sel = 1;
    push_page("to1/clan13x");
    xlog("clan13: post-match scoreboard for day %d (%s, %s) - pushing to1/clan13x", day, C13.xs_map, won == 1 ? "won" : won == 0 ? "lost" : "no result");
    return 1;
}
static int cl13_post_active(void) { return g_c13x.on && g_c13x.post; }
static void cl13_post_end(const char *how) {
    if (!g_c13x.post) return;
    g_c13x.on = 0; g_c13x.post = 0; C13.xs_open = 0; C13.xs_post = 0; C13.xs_wait = 0;
    pms_count_cut(80);
    xlog("clan13: post-match scoreboard closed (%s)", how);
}
// the boxed prompts of the shown tab (nrui.c nr_prompts) and what a click on each does
enum { C13A_NONE, C13A_JOURNAL, C13A_TABS, C13A_BACK, C13A_STATS, C13A_PICK, C13A_DAY, C13A_WEEK };
static int g_c13_pa[NR_NPROMPT], g_c13_npa;
static void cl13_prompts(const cl13_t *V, int show) {
    nr_prompt_t it[NR_NPROMPT]; int n = 0;
    #define C13P(kb_, pad_, lb_, on_, a_) do { it[n].kb = kb_; it[n].pad = pad_; it[n].label = lb_; it[n].on = on_; g_c13_pa[n] = a_; n++; } while (0)
    int t = C13.tab;
    if (show && t == T_OV) C13P("menu:select", NULL, "JOURNAL", V->nu > 0, C13A_JOURNAL);
    if (show && t == T_RD) C13P("menu:action", NULL, "PLAYER STATS", V->nm > 0 && !C13.xs_open, C13A_STATS);
    if (show && t == T_JR) { C13P("A / D", "LEFT / RIGHT", "DAY", V->nd > 1, C13A_DAY); C13P("W / S", "UP / DOWN", "WEEK", V->jtop > 1, C13A_WEEK); }
    if (show && t == T_MS && !cl13_ms_running()) C13P("menu:select", NULL, C13.ms_chosen ? "MISSION STARTED" : "SELECT", C13.ms_n > 0 && !C13.ms_chosen, C13A_PICK);
    C13P("menu:prev+menu:next", NULL, "TABS", 1, C13A_TABS);
    C13P("menu:back", NULL, "BACK", 1, C13A_BACK);
    #undef C13P
    g_c13_npa = n;
    nr_prompts(it, n);
}
static void cl13_fill(void) {
    const cl13_t *V = C13.V;
    cl13_ms_rows();
    const char *msg = cl13_msg(V);
    ui_text("anim-group.ldTx", msg);
    ui_visible("anim-group.ldTx", msg[0] != 0);
    int show = !msg[0];
    if (show && !C13.shown_prev && !C13.intro_played) C13.fx_pending = 1;                    // the content just became visible (data came / first look): its entrance
    C13.shown_prev = show;
    int fading = C13.prev_tab >= 0 && GetTickCount64() - C13.tab_t0 < C13_XF_MS;
    ui_visible("anim-group.ov", show && (C13.tab == T_OV || (fading && C13.prev_tab == T_OV)));
    ui_visible("anim-group.sv", show && (C13.tab == T_SV || (fading && C13.prev_tab == T_SV)));
    ui_visible("anim-group.rds", show && (C13.tab == T_RD || (fading && C13.prev_tab == T_RD)));
    ui_visible("anim-group.jrn", show && (C13.tab == T_JR || (fading && C13.prev_tab == T_JR)));
    ui_visible("anim-group.ms", show && (C13.tab == T_MS || (fading && C13.prev_tab == T_MS)));
    nr_clan_tabs(C13.tab, C13.hv_tb);
    cl13_prompts(V, show);
    if (!show) {      // (an empty MISSIONS tab's message also blanked the WEEK / DAY header - keep it when the clan itself is loaded)
        if (V && V->ok && cl13_have(V, T_OV)) { cl13_header(V); nr_week_visible(1); }
        else if (!C13.hd_shown) { char t[64]; nr_header("CLAN", cl13_tr(nr_clan_tab_label(C13.tab), t, sizeof t)); nr_week_visible(0); }      // (never blanked once it showed values)
        cl13_fill_xs(V, 0); return;
    }
    cl13_header(V); nr_week_visible(1); C13.hd_shown = 1;
    if (C13.tab == T_OV) cl13_fill_ov(V); else if (C13.tab == T_SV) cl13_fill_sv(V); else if (C13.tab == T_RD) cl13_fill_rd(V); else if (C13.tab == T_MS) cl13_fill_ms(V); else cl13_fill_jr(V);
    cl13_fill_xs(V, 1);
    if (C13.fx_pending) cl13_fx_build(V);
}
// ------------------------------------------------------------------ the mouse: geometry of the rows (canvas units, = clan13_widgets.py) so the gaps between rows count
// ------------------------------------------------------------------ the mouse: the tile under the cursor (canvas units, = clan13_widgets.py), the tab strip, the prompts
static void cl13_scan(void) {
    static float lcx = -1.0f, lcy = -1.0f; static int lkey = -1; static uint64_t lfr;
    float cx, cy;
    if (!ui_cursor_canvas(&cx, &cy)) { C13.hv_r = C13.hv_c = C13.hv_pb = -1; C13.hv_tb = -1; lkey = -1; return; }
    int key = C13.tab | C13.roff[C13.tab] << 3 | g_c13_npa << 10;
    if (cx == lcx && cy == lcy && key == lkey && g_frame - lfr < 15) return;
    lcx = cx; lcy = cy; lkey = key; lfr = g_frame;
    C13.hv_r = C13.hv_c = -1;
    C13.hv_tb = nr_clan_tab_hover();
    C13.hv_pb = nr_prompt_hover();
    if (C13.xs_open || !C13.V) return;
    c13grid_t G; cl13_grid(C13.tab, &G);
    int t = C13.tab;
    float x0 = 148.0f, dx = 0.0f, w = 0.0f, y0 = 0.0f, dy = 0.0f, h = 0.0f; int vr = C13_VROWS[t], vc = C13_VCOLS[t];
    if (t == T_OV) { dx = 372.0f; w = 340.0f; y0 = 508.0f; h = 356.0f; }
    else if (t == T_SV) { dx = 308.0f; w = 280.0f; y0 = 564.0f + 44.0f; dy = 428.0f; h = 248.0f + 110.0f; }      // (the name / state under the portrait counts)
    else if (t == T_RD) { dx = 632.0f; w = 600.0f; y0 = 564.0f + 48.0f; dy = 540.0f; h = 432.0f; }
    else if (t == T_JR) { dx = 304.0f; w = 280.0f; y0 = 464.0f + 52.0f; dy = 476.0f; h = 352.0f; }
    else if (t == T_MS) { if (cl13_ms_running()) return; dx = 0.0f; w = 1660.0f; y0 = 560.0f; dy = 128.0f; h = 112.0f; }
    for (int r = 0; r < vr; r++) {
        int gr = (t == T_MS ? 0 : C13.roff[t]) + r;
        if (gr >= G.nrow) break;
        float ty = y0 + dy * (float)r;
        if (cy < ty || cy > ty + h) continue;
        for (int c = 0; c < vc; c++) {
            int gc = (gr < C13_GR ? C13.coff[t][gr] : 0) + c;
            if (gc >= G.ncol[gr]) break;
            float tx = x0 + dx * (float)c;
            if (cx >= tx && cx <= tx + w) { C13.hv_r = r; C13.hv_c = c; return; }
        }
    }
}
static int cl13_hv_item(int *gr, int *gc) {                          // the grid cell under the hovered tile (0: none)
    if (C13.hv_r < 0 || C13.hv_c < 0) return 0;
    c13grid_t G; cl13_grid(C13.tab, &G);
    int r = (C13.tab == T_MS ? 0 : C13.roff[C13.tab]) + C13.hv_r;
    if (r >= G.nrow) return 0;
    int c = (r < C13_GR ? C13.coff[C13.tab][r] : 0) + C13.hv_c;
    if (c >= G.ncol[r]) return 0;
    *gr = r; *gc = c;
    return 1;
}
// the click gate (ui_click_gate_tick): the cursor is over something clickable
// the click gate (ui_click_gate_tick): the cursor is over something clickable
static int cl13_click_hit(void) {
    if (!C13.up || !C13.V) return 0;
    cl13_scan();
    int r, c;
    return cl13_hv_item(&r, &c) || C13.hv_tb != -1 || C13.hv_pb >= 0 || C13.xs_open;
}
static const char *const C13_GRP[C13_NTAB] = {"anim-group.ov", "anim-group.sv", "anim-group.rds", "anim-group.jrn", "anim-group.ms"};
// A switch can come while the last one's fade-out / entrances still run (Q / E held, bumpers hammered): everything that was left half way is put back to its resting state first
// (full alpha, base position), so a tab that is switched to later never starts from a stale alpha 0 / partial fade (content went blank on fast switching).
static void cl13_settle(void) {
    for (int k = 0; k < C13_NTAB; k++) { uint64_t g = ui_w(C13_GRP[k]); if (g) w_alpha(g, 1.0f); }
    for (int i = 0; i < C13.nfx; i++) {
        c13fx_t *f = &C13.fx[i];
        uint64_t w = f->w ? f->w : ui_w(f->path);
        if (!w) continue;
        w_alpha(w, 1.0f);
        if (f->kind >= 1 && f->kind <= 5) w_pivot(w, f->bx, f->by);
    }
    const char *dp[4] = {"anim-group.ov.ovDt", "anim-group.sv.svDt", "anim-group.rds.rdDt", "anim-group.jrn.jtPane"};
    for (int k = 0; k < 4; k++) gu_grp(dp[k], 1.0f, 0.0f);
    cl13_fx_reset();
}
static void cl13_set_tab(int t, const char *why) {
    t = (t % C13_NTAB + C13_NTAB) % C13_NTAB;
    if (t == C13.tab) return;
    cl13_settle();
    C13.prev_tab = C13.tab; C13.tab = t; C13.tab_t0 = GetTickCount64();
    C13.sw++; if (C13.intro_played) C13.fx_pending = 0;         // (intros play once per opening - a switch is a crossfade of two filled tabs)
    C13.dirty = 1; C13.det_key = -1; C13.det_ph = 0; C13.det_hold = 0; cl13_sfx();
    xlog("clan13: tab %d (%s)", t, why);
}
static int g_c13_want_tab = -1;                                     // nr_clan_go from an extension tab page: the clan page opens on this tab
static void cl13_go_tab(int tab, const char *why) {                  // nrui.c nr_clan_go: tab 0..4 of the clan page, from the clan page itself or from an extension tab page
    if (tab < 0 || tab >= C13_NTAB) return;
    if (C13.up && top_page() == cl13_page_id()) { cl13_set_tab(tab, why); return; }
    g_c13_want_tab = tab;
    xlog("clan13: tab %d from another page (%s) - pushing to1/clan13", tab, why);
    push_page("to1/clan13");
}
static struct { uint64_t until; int apply, tab, fr[C13_NTAB], fc[C13_NTAB], roff[C13_NTAB]; } g_c13_resume;      // closing the match stats with menu-back (the pad's B / Circle): the engine pops the page on it, it is pushed again
static void cl13_enter(void) {
    memset(&C13, 0, sizeof C13);
    C13.V = &g_cl13_view;
    C13.up = 1; C13.enter_ms = GetTickCount64(); C13.dirty = 1; C13.prev_tab = -1; C13.fx_first = 1; C13.det_key = -1;
    C13.h_sel = C13.h_u = C13.h_d = C13.h_l = C13.h_r = C13.h_back = C13.h_esc = C13.h_pv = C13.h_nx = C13.h_ka = C13.h_kd = C13.h_act = C13.h_f = 1;      // whatever is held when the page opens
    C13.t_u = C13.t_d = C13.t_l = C13.t_r = ~0ULL;
    C13.hv_r = C13.hv_c = C13.hv_pb = C13.hv_tb = -1;
    C13.t0 = C13.enter_ms;
    cl13_seen_load();
    for (int s = 1; s <= 6; s++) { C13.seen_ver[s] = (int)g_cl13_ver[s]; }
    if (!g_c13_resume.apply) memset(&g_cl13_view, 0, sizeof g_cl13_view);      // the snapshot starts empty: LOADING until this visit's replies are here (a stale roster would flash); back from the stats page the last good one stays
    cl13_pic_reset();
    gu_fade_reset(); memset(g_gu_fit, 0, sizeof g_gu_fit);
    if (g_c13_resume.apply) {                                         // the engine popped the page on the menu-back that closed the match stats: back on the same tab and tile
        g_c13_resume.apply = 0; g_c13_resume.until = 0;
        C13.intro_played = 1; C13.fx_first = 0; C13.hd_done = 1; C13.sw = 1; C13.hd_shown = 1;       // (no second intro for the same opening)
        C13.tab = g_c13_resume.tab; memcpy(C13.fr, g_c13_resume.fr, sizeof C13.fr); memcpy(C13.fc, g_c13_resume.fc, sizeof C13.fc);
        memcpy(C13.roff, g_c13_resume.roff, sizeof C13.roff); memcpy(C13.want, g_c13_resume.fc, sizeof C13.want); C13.jr_init = 1;
    }
    if (g_c13_want_tab >= 0) { C13.tab = g_c13_want_tab; g_c13_want_tab = -1; }
    if (cl13_pick_due()) { C13.tab = T_MS; xlog("clan13: a mission is to be chosen - opening on MISSIONS"); }      // nobody misses the pick (no pick pending: the page opens as usual)
    w_alpha(ui_w("anim-group"), 0.0f);                                // the page fades in (the end of feature_clan13)
    g_cl13_pic_logged = 0;
    C13.ev0 = g_g2_evicts; ui_visible("anim-group.pre", 1);           // (the image budget starts over: the strip is back until the table fills up)
    xlog("clan13: page up");
}
static void cl13_close(const char *how) {
    if (C13.closing || C13.out_t0 || C13.quiet) return;
    xlog("clan13: back (%s)", how);
    // NR 1.3 (exit: ghost of the page + empty frames): the engine's own page transition carries the page out, so everything we drive is put back to rest NOW, in the frame of the
    // pop, and from here on nothing of ours writes alpha / position on this page (quiet): the exit starts from a settled page instead of one that is mid-entrance / mid-crossfade.
    cl13_settle();
    w_alpha(ui_w("anim-group"), 1.0f);
    C13.quiet = 1;
    C13.back_f = g_frame ? g_frame : 1;                               // the engine pops a pushed menu page on menu-back by itself; Esc it does not: judged 6 frames after the press
    // Our own 140 ms fade to alpha 0 + pop left ~10 empty frames and then the engine's page-exit transition replayed the clan page ghosted over
    // the main menu coming in. No private fade any more: the page is popped at full alpha (as menu-back does) and the engine's transition carries it out.
    if (strcmp(how, "menu-back") && top_page() == cl13_page_id()) { pop_page(); C13.closing = 1; C13.back_f = 0; cl13_seen_save(); xlog("clan13: closed"); }
}
// detail cross-fade (as GEAR UP's details panel): the old content fades out fast, the refill waits, the new fades in with a small slide
static const char *cl13_det_path(void) { return C13.tab == T_OV ? "anim-group.ov.ovDt" : C13.tab == T_SV ? "anim-group.sv.svDt" : C13.tab == T_RD ? "anim-group.rds.rdDt" : C13.tab == T_JR ? "anim-group.jrn.jtPane" : NULL; }
static void cl13_det_tick(uint64_t now) {
    const char *dp = cl13_det_path();
    int key = C13.tab * 10000 + C13.fr[C13.tab] * 100 + C13.fc[C13.tab];
    if (!dp || cl13_anim_off() || C13.fx_pending || now - C13.t0 < 1500) { C13.det_key = dp ? key : -1; C13.det_hold = 0; C13.det_ph = 0; return; }
    if (C13.det_key == -1) C13.det_key = key;
    // A new cross-fade only from rest and not within C13_DET_GAP_MS of the last one: a focus step during a running one, or a quick next step, refills the panel in
    // place at full alpha (det_hold 0: the fill writes it) - held W / S used to restart the fade-out on every 110 ms repeat (a large panel strobing ~9 times a second).
    else if (key != C13.det_key && (cl13_flicker_old() ? C13.det_ph != 1 : C13.det_ph == 0 && (!C13.det_last || now - C13.det_last >= C13_DET_GAP_MS))) { C13.det_key = key; C13.det_ph = 1; C13.det_t0 = now; C13.det_hold = 1; }
    else if (key != C13.det_key) { C13.det_key = key; if (C13.det_ph == 0) C13.det_last = now; }     // (a refill in place also restarts the quiet time: no fade while the keys keep coming)
    if (C13.det_ph == 1) {
        float p = (float)(now - C13.det_t0) / 80.0f;
        gu_grp(dp, 1.0f - cl13_eo(p), 0.0f);
        if (p >= 1.0f) { C13.det_ph = 2; C13.det_t0 = now; C13.det_hold = 0; C13.dirty = 1; }
    } else if (C13.det_ph == 2) {
        float p = cl13_eo((float)(now - C13.det_t0) / 150.0f);
        gu_grp(dp, p, (1.0f - p) * 8.0f);
        if (p >= 1.0f) { C13.det_ph = 0; C13.det_last = now; gu_grp(dp, 1.0f, 0.0f); }
    }
}
static void cl13_preload_tick(void) {                              // the portraits / icons the page can show go through the tiny always-visible pre<n> widgets (the engine streams a texture in when a widget first shows it)
    if (!C13.V) return;
    int old = cl13_flicker_old(), budget = 8;
    if (!old) {                                                         // the Gui2 image budget (C13_G2_RETIRE): waves while the table has room, then the strip goes away
        if (C13.pre_off) return;
        int f = g2_filled();
        if (f < 0) old = 1;                                             // (table not found: as before)
        else if (f >= C13_G2_RETIRE) {
            ui_visible("anim-group.pre", 0); C13.pre_off = 1;
            xlog("clan13: preload strip retired - Gui2 image table %d/32 filled (%d icons, %d portraits preloaded)", f, C13.pre_ick, C13.pre_i);
            return;
        } else {
            if (C13.pre_wave_f && g_frame - C13.pre_wave_f < C13_PRE_GAP_F) return;
            if (f > C13_G2_RETIRE - C13_PRE_WAVE) return;               // (no room for a whole wave now)
            budget = C13_PRE_WAVE;
        }
    }
    int asked = 0;
    if (!C13.pre_ic) {      // every icon the page can show (pre22..pre31; the page reveals only after C13_GATE_MS): no icon streams in while the page is already visible
        static const char *const IC[10] = {"food", "water", "medicine", "ammo", "materials", "healthbar", "person", "pills", "bandage", "keepsake"};
        if (!ui_w("anim-group.pre.pre31")) return;
        for (; C13.pre_ick < 10 && (old || asked < budget); C13.pre_ick++, asked++) {
            char path[60], img[80];
            snprintf(path, sizeof path, "anim-group.pre.pre%d", 22 + C13.pre_ick);
            snprintf(img, sizeof img, "streaming/t2r/icons/c13-%s.png", IC[C13.pre_ick]);
            ui_image(path, img);
        }
        if (C13.pre_ick >= 10) C13.pre_ic = 1;
        if (!old) { if (asked) C13.pre_wave_f = g_frame; if (!C13.pre_ic || asked >= budget) return; }
    }
    if (!cl13_portraits_on()) return;
    const cl13_t *V = C13.V;
    for (int n = 0; n < (old ? 8 : budget - asked); n++) {
        int i = C13.pre_i;
        if (i >= V->np + V->nu || i >= 22) break;       // (the counter moves only when there is something to preload: it used to run past the end while the snapshot was still empty, so nothing was ever preloaded)
        C13.pre_i++;
        if (!old) C13.pre_wave_f = g_frame;
        const char *pid = i < V->nu ? V->u[i].pid : V->p[i - V->nu].pid;
        char a[16], s[16], m[16], e[20], path[60], img[120];
        if (sscanf(pid, "%15[^/]/%15[^/]/%15[^/]/%19s", a, s, m, e) != 4) continue;
        snprintf(path, sizeof path, "anim-group.pre.pre%d", i % 22);
        snprintf(img, sizeof img, "streaming/t2r/icons/c13p-%s_%s.png", m, e);
        ui_image(path, img);
    }
}
// the PLAYER STATS page on top of the clan page: the net (section 5 answer), the fill, and its keys (menu-back pops it by itself; Esc / F / the
// pad's menu-action / a click on BACK pop it here). Back on to1/clan13 the list counts as closed.
static int anim_on_xp(void) { return !cl13_anim_off(); }
static void cl13x_tick(void) {
    uint64_t now = GetTickCount64();
    int first = !g_c13x.seen;
    g_c13x.seen = 1;
    cl13_net_tick(now);
    const cl13_t *V = C13.V;
    int post = g_c13x.post;
    if (first && post) pms_play(PMSK_ENTER);
    if (V && (C13.dirty || g_frame % 6 == 0)) {
        g_c13_hd_page = post ? "POST-MATCH" : "PLAYER STATS";
        cl13_header(V);
        g_c13_hd_page = NULL;
        cl13_fill_xp(V, 1);
        nr_prompt_t it[1] = {{post ? "menu:select" : "menu:back", NULL, post ? "CONTINUE" : "BACK", 1}};      // post-match: one prompt, CONTINUE (confirm)
        nr_prompts(it, 1);
    } else if (V && cl13_xp_busy()) cl13_fill_xp(V, 1);                   // the entrance / the counts run every frame
    int f_now = game_focused() && (GetAsyncKeyState('F') & 0x8000) != 0, esc_now = game_focused() && (GetAsyncKeyState(VK_ESCAPE) & 0x8000) != 0;
    int act = menu_edge(fnv64("menu-action"), &g_c13x.h_act) | (f_now && !g_c13x.h_f), esc = esc_now && !g_c13x.h_esc;
    int sel = post ? menu_edge(0x6695c5b7921bb5ddULL /* menu-select */, &g_c13x.h_sel) : 0;
    g_c13x.h_f = f_now; g_c13x.h_esc = esc_now;
    int clk = g_click_edge && nr_prompt_hover() == 0;
    // (A/B: A AFK-kicked, the host gone, "nobody left to host - match ends"): the server never booked the match, every ask for its
    // stats came back with 0 players, and the empty scoreboard waited for a key for 29 min (the MP menu's 10 min watchdog does not run while this
    // page is on top). A post-match scoreboard with nothing to show closes itself once the asking is over (25 s / 4 tries): the supply counter
    // follows as after a CONTINUE. t2r-test-autofind.txt (A/B automation, no input): a scoreboard WITH stats closes itself 8 s after its count.
    if (post && g_frame > g_c13x.f0 + 10) {
        const char *why = NULL;
        if (C13.xs_got && !C13.xs_wait && V && V->xn == 0) why = "no stats of the match on the server";
        else if (g_test_autofind && !cl13_xp_busy() && now - C13.xs_t0 > 8000 && C13.xs_got) why = "t2r-test-autofind.txt";
        if (why) {
            pop_page();
            xlog("clan13: match stats page closed (%s)", why);
            cl13_post_end(why);
            return;
        }
    }
    if (sel && g_frame > g_c13x.f0 + 10 && post && cl13_xp_busy() && anim_on_xp()) {       // the first confirm finishes the count (NR locks input until it is done; ours skips it)
        XP.t0 = now - 100000; cl13_sfx(); sel = 0;
    } else if (clk && post && cl13_xp_busy() && anim_on_xp()) { XP.t0 = now - 100000; clk = 0; }
    if ((act || esc || clk || sel) && g_frame > g_c13x.f0 + 10) {
        cl13_sfx(); pop_page();
        xlog("clan13: match stats page closed (%s)", sel ? "confirm" : act ? "F / action" : esc ? "Esc" : "BACK / CONTINUE clicked");
        if (post) cl13_post_end(sel ? "confirm" : act ? "F / action" : esc ? "Esc" : "click");
    }
}
static void cl13_tab_step(int d, const char *why) {                  // Q / E: the clan's 5 tabs, then the extension tabs (achievements, customize: nrui.c registry), round
    int n = nr_clan_ntabs(), t = ((C13.tab + d) % n + n) % n;
    if (t < C13_NTAB) cl13_set_tab(t, why); else nr_clan_go(t, why);
}
static void cl13_pick_send(const char *why) {                         // the mission pick: the same op 0xEF feature_missions always sent
    if (C13.tab != T_MS || !C13.ms_n || C13.ms_chosen || g_clan_busy || C13.fr[T_MS] >= C13.ms_n) return;
    uint8_t id = (uint8_t)C13.ms_rows[C13.fr[T_MS]];
    if (clan_send(0xEF, &id, 1)) { C13.ms_chosen = 1; C13.ms_chosen_at = GetTickCount64(); C13.ms_tries = 1; C13.dirty = 1; ui_sfx("sfx-select"); xlog("clan13: missions: chose %s (%s)", MIS[id].name, why); }
}
static void feature_clan13(void) {
    g_cl13_up = 0;
    if (!cl13_enabled()) return;
    uint64_t top = top_page();
    if (g_c13x.on && g_c13x.post && top != cl13x_page_id() && (g_c13x.seen ? g_frame > g_c13x.f0 + 10 : g_frame > g_c13x.f0 + 120)) cl13_post_end(g_c13x.seen ? "page popped (menu-back)" : "never reached the top");
    if (g_c13x.on && top == cl13x_page_id() && top) { g_cl13_up = 1; cl13x_tick(); return; }   // (the clan page stays "up" under its stats page)
    if (top != cl13_page_id()) {
        if (C13.up) {
            C13.up = 0; cl13_seen_save(); xlog("clan13: page left (top now %s)", page_name(top));
            xlog("clan13: Gui2 image table peak %d/32 (tab %d), %ld evictions this visit, preload strip %s, %d crossfades cut short%s", C13.g2_peak, C13.g2_peak_tab,
                 (long)(g_g2_evicts - C13.ev0), C13.pre_off ? "retired" : "kept", C13.xf_cut, cl13_flicker_old() ? " (t2r-clan13-flicker-old.txt)" : "");
            if (g_c13_resume.until && g_frame <= g_c13_resume.until && top) { g_c13_resume.apply = 1; push_page_now("to1/clan13"); xlog("clan13: the engine popped the page on the back that closed the match stats - pushed again"); }
        }
        if (nr_clan_xtab_route(top)) g_cl13_up = 1;                     // an extension tab page (achievements / customize) is on top: the clan stays up under it
        if (g_c13_resume.until && g_frame > g_c13_resume.until) g_c13_resume.until = 0;
        return;
    }
    g_cl13_up = 1;
    if (!C13.up) {
        cl13_enter();
        if (g_ce_journal_tab) { g_ce_journal_tab = 0; C13.tab = T_JR; C13.dirty = 1; xlog("clan13: opened on the journal (clan end screen)"); }
    }
#ifndef T2R_RELEASE
    {   // dev (A/B screenshots): t2r-clan-test.txt written while the page is up = switch here (cl13_open_check only reads it on the MP menu)
        static uint64_t tchk; uint64_t tn = GetTickCount64();
        if (tn - tchk > 500) { tchk = tn; FILE *f = exe_side_open("t2r-clan-test.txt", "r");
            if (f) { char b[16] = {0}; if (!fgets(b, sizeof b, f)) b[0] = 0; fclose(f); DeleteFileA("t2r-clan-test.txt");
                g_c13_test = !strncmp(b, "stats", 5) ? 2 : !strncmp(b, "tab", 3) && b[3] >= '0' && b[3] <= '4' ? 10 + b[3] - '0' : 1; g_c13_test_ms = tn - 1600;
                xlog("clan13: t2r-clan-test.txt on the open page (%d)", g_c13_test); } }
    }
#endif
    if (g_c13_test && GetTickCount64() - g_c13_test_ms > 1500) {
        if (g_c13_test >= 10) { int t = g_c13_test - 10; g_c13_test = 0; if (C13.tab != t) cl13_set_tab(t, "t2r-clan-test.txt"); }
        else if (C13.tab != T_RD) { cl13_set_tab(T_RD, "t2r-clan-test.txt"); C13.fr[T_RD] = C13.fc[T_RD] = 0; }
        else if (g_c13_test == 2 && C13.V && C13.V->nm > 0 && GetTickCount64() - g_c13_test_ms > 3000) { g_c13_test = 0; cl13_xs_open("t2r-clan-test.txt"); }
        else if (g_c13_test == 1 || GetTickCount64() - g_c13_test_ms > 15000) g_c13_test = 0;
    }
    if (C13.xs_open && (g_c13x.seen || g_frame > g_c13x.f0 + 90)) {      // back from the stats page (or it never came up): the list is closed
        cl13_xs_close(g_c13x.seen ? "stats page popped" : "stats page never reached the top");
    }
    uint64_t now = GetTickCount64();
    if (C13.closing) return;
    cl13_net_tick(now);
    // ---- input
    int sel = menu_edge(0x6695c5b7921bb5ddULL /* menu-select */, &C13.h_sel);
    int up = gu_rep(&C13.h_u, &C13.t_u, fnv64("menu-up")), down = gu_rep(&C13.h_d, &C13.t_d, fnv64("menu-down"));
    int left = gu_rep(&C13.h_l, &C13.t_l, fnv64("menu-left")), right = gu_rep(&C13.h_r, &C13.t_r, fnv64("menu-right"));      // (the stick / d-pad repeat like the keys)
    int back = menu_edge(fnv64("menu-back"), &C13.h_back);
    int f_now = game_focused() && (GetAsyncKeyState('F') & 0x8000) != 0, act_k = f_now && !C13.h_f;
    C13.h_f = f_now;
    int act = menu_edge(fnv64("menu-action"), &C13.h_act) || act_k;                 // F / the pad's menu-action (Triangle / Y): the match stats of the focused raid
    int esc_now = game_focused() && (GetAsyncKeyState(VK_ESCAPE) & 0x8000) != 0, esc = esc_now && !C13.h_esc;
    C13.h_esc = esc_now;
    int wn = wheel_notches();
    { static int lpd = -1; if (lpd != g_pad_mode) { lpd = g_pad_mode; C13.dirty = 1; } }       // the prompts follow the device in use
    cl13_scan();
    int click = g_click_edge;
    int pa = click && C13.hv_pb >= 0 && C13.hv_pb < g_c13_npa ? g_c13_pa[C13.hv_pb] : C13A_NONE;     // a click on a prompt = its key
    if (pa) click = 0;
    if (C13.xs_open) {                                                  // the match stats list is up: it owns the keys; F again / BACK / Esc / B closes it (the page stays)
        if (back || esc || act || pa == C13A_BACK) {
            if (back) {                                                 // (the engine pops the page on menu-back by itself: pushed again at once, same tab and tile)
                g_c13_resume.until = g_frame + 10; g_c13_resume.tab = C13.tab;
                memcpy(g_c13_resume.fr, C13.fr, sizeof C13.fr); memcpy(g_c13_resume.fc, C13.fc, sizeof C13.fc); memcpy(g_c13_resume.roff, C13.roff, sizeof C13.roff);
            }
            cl13_xs_close(act ? "action" : esc ? "Esc" : back ? "menu-back" : "BACK clicked");
            back = esc = 0;
        }
        act = 0; up = down = left = right = 0; sel = 0; click = 0; wn = 0; pa = 0;
    } else if ((act || pa == C13A_STATS) && C13.tab == T_RD && C13.V && C13.V->nm > 0 && now - C13.enter_ms >= 500 && !C13.out_t0) { cl13_xs_open(pa ? "PLAYER STATS clicked" : act_k ? "F" : "menu-action"); act = 0; pa = 0; }
    if (back || esc || pa == C13A_BACK) { cl13_close(esc ? "Esc" : pa ? "BACK clicked" : "menu-back"); back = esc = 0; sel = 0; click = 0; pa = 0; }
    if (C13.back_f && !C13.out_t0 && g_frame >= C13.back_f + 6) {
        C13.back_f = 0;
        if (top_page() == cl13_page_id() && !C13.closing) { pop_page(); C13.closing = 1; cl13_seen_save(); xlog("clan13: closed"); return; }
    }
    if (C13.quiet) return;                                              // leaving: the engine transition owns the page (no fade-in, crossfade, entrance or preload writes any more)
    int t = C13.tab;
    // MOVE: W / S / the arrows / the stick / the d-pad: up / down = the row (SURVIVORS: role, RAIDS / JOURNAL: week, MISSIONS: mission), left / right = the tile in the row
    // (the journal runs on into the next / previous week at a row's ends); the wheel scrolls rows. TABS: Q / E and the bumpers (menu-prev / menu-next); Q + a bumper in one frame = ONE step.
    if (C13.V) {
        if (up) cl13_gstep(t, -1, 0);
        if (down) cl13_gstep(t, 1, 0);
        if (left) cl13_gstep(t, 0, -1);
        if (right) cl13_gstep(t, 0, 1);
        for (int k = wn < 0 ? -wn : wn; k > 0; k--) cl13_gstep(t, wn > 0 ? -1 : 1, 0);      // one row per notch (a fast spin moved one row a frame)
    }
    int kq = game_focused() && (GetAsyncKeyState('Q') & 0x8000) != 0, ke = game_focused() && (GetAsyncKeyState('E') & 0x8000) != 0;
    int tab_l = kq && !C13.h_ka, tab_r = ke && !C13.h_kd;
    C13.h_ka = kq; C13.h_kd = ke;
    int bp = menu_edge(fnv64("menu-prev"), &C13.h_pv), bn = menu_edge(fnv64("menu-next"), &C13.h_nx);
    if (C13.xs_open) tab_l = tab_r = bp = bn = 0;
    if (tab_l || bp) cl13_tab_step(-1, bp ? "left bumper" : "Q");
    else if (tab_r || bn) cl13_tab_step(1, bn ? "right bumper" : "E");
    if (pa == C13A_TABS) cl13_tab_step(1, "TABS clicked");
    if (pa == C13A_JOURNAL && C13.V->nu) cl13_set_tab(T_JR, "JOURNAL clicked");
    if (pa == C13A_DAY) cl13_gstep(T_JR, 0, 1);
    if (pa == C13A_WEEK) cl13_gstep(T_JR, 1, 0);
    if (pa == C13A_PICK) cl13_pick_send("SELECT clicked");
    if (pa) { C13.click_f = g_frame; sel = 0; }
    if (click) {
        int gr, gc;
        if (C13.hv_tb >= 0) { nr_clan_go(C13.hv_tb, "tab clicked"); C13.click_f = g_frame; sel = 0; }
        else if (C13.hv_tb == -2) { cl13_tab_step(-1, "Q clicked"); C13.click_f = g_frame; sel = 0; }
        else if (C13.hv_tb == -3) { cl13_tab_step(1, "E clicked"); C13.click_f = g_frame; sel = 0; }
        else if (C13.V && cl13_hv_item(&gr, &gc)) {
            int again = gr == C13.fr[t] && gc == C13.fc[t];
            if (!again) { C13.fr[t] = gr; C13.fc[t] = gc; C13.want[t] = gc; if (t == T_JR) cl13_jw_follow("click"); C13.dirty = 1; cl13_sfx(); xlog("clan13: click on tile %d,%d (tab %d)", gr, gc, t); }
            else if (t == T_OV) cl13_set_tab(T_JR, "card clicked again");
            else if (t == T_RD && C13.V->nm > 0) cl13_xs_open("raid clicked again");
            else if (t == T_MS) cl13_pick_send("clicked again");
            C13.click_f = g_frame; sel = 0;
        }
    }
    if (sel && C13.click_f && g_frame - C13.click_f <= 8) sel = 0;        // the click already acted
    if (g_test_autofind && C13.tab == T_MS && C13.ms_n && !C13.ms_chosen && !C13.ms_auto && now - C13.enter_ms >= 3000) { C13.ms_auto = 1; sel = 1; xlog("test autofind: mission picked"); }   // A/B test aid: the first mission 3 s after the page opened on MISSIONS (the old picker's auto-pick never ran: the clan page owns the pick)
    if (sel && C13.tab == T_OV && C13.V->nu) cl13_set_tab(T_JR, "select");
    if (sel && C13.tab == T_RD && C13.V->nm > 0 && !C13.xs_open && now - C13.enter_ms >= 500) cl13_xs_open("select");
    if (sel && C13.tab == T_MS) cl13_pick_send("select");
    if (C13.ms_chosen) {                                                  // the choice waits for the server's reply (m.mi): asked again after 6 s, given up after 12 s (as the old page)
        meta_t mm = meta_get();
        if (mm.mi) {                                                      // (the page stays on MISSIONS and turns into the running mission's status page)
            int stay = !g_test_autofind && GetFileAttributesA("t2r-clan-ms-old.txt") == INVALID_FILE_ATTRIBUTES;
            xlog("clan13: missions: %s running - %s", MIS[mm.mi].name, stay ? "the tab shows its status" : "closing");
            C13.ms_chosen = 0; C13.dirty = 1; if (!stay) cl13_close("mission chosen"); }
        else if (!g_clan_busy && now - C13.ms_chosen_at >= 6000) {
            if (C13.ms_tries < 2 && C13.fr[T_MS] < C13.ms_n) { uint8_t id = (uint8_t)C13.ms_rows[C13.fr[T_MS]]; if (clan_send(0xEF, &id, 1)) { C13.ms_tries++; C13.ms_chosen_at = now; xlog("clan13: missions: no answer for 6 s - asking again"); } }
            else { xlog("clan13: missions: the server never answered the choice - back to the page"); C13.ms_chosen = 0; C13.dirty = 1; }
        }
    }
    // ---- fill: on a change, twice a second, and at the page's first moments (its widgets may be built a frame late)
    static const uint32_t OFF_MS[] = {33, 100, 250, 670, 1500, 3000};
    if (C13.stage < (int)(sizeof OFF_MS / sizeof OFF_MS[0]) && now - C13.enter_ms >= OFF_MS[C13.stage]) { C13.stage++; C13.dirty = 1; gu_fade_reassert(); }
    {   // the hover highlight follows the cursor
        static int lh = -9, lt = -9, lb = -9;
        int hh = C13.hv_r * 64 + C13.hv_c, hb = C13.tab | (C13.hv_pb + 1) << 4;
        if (lh != hh || lt != C13.hv_tb || lb != hb) { lh = hh; lt = C13.hv_tb; lb = hb; C13.dirty = 1; }
    }
    {   // the Gui2 image budget: the visit's peak (logged when the page is left) and a crossfade that would draw more images than the engine keeps ends at once
        int g2 = g2_filled();
        if (g2 > C13.g2_peak) { C13.g2_peak = g2; C13.g2_peak_tab = C13.tab; }
        if (g2 >= C13_G2_XFCUT && C13.prev_tab >= 0 && now - C13.tab_t0 < C13_XF_MS && !cl13_flicker_old()) {
            C13.tab_t0 = now - C13_XF_MS; C13.xf_cut++;
            static int nl; if (LOGCAP(nl, 20)) xlog("clan13: crossfade %d -> %d cut short - Gui2 image table %d/32 filled", C13.prev_tab, C13.tab, g2);
        }
    }
    if (C13.prev_tab >= 0 && now - C13.tab_t0 >= C13_XF_MS) {      // the crossfade is over: the old tab is hidden (by the fill), the new one rests at full alpha
        uint64_t og = ui_w(C13_GRP[C13.prev_tab]), ng = ui_w(C13_GRP[C13.tab]);
        if (og) w_alpha(og, 1.0f);
        if (ng) w_alpha(ng, 1.0f);
        C13.prev_tab = -1; C13.dirty = 1;
    }
    cl13_det_tick(now);
    if (C13.dirty || !(g_frame % 90)) { C13.dirty = 0; cl13_fill(); }
    if (C13.prev_tab >= 0) {                                            // the tab we leave fades out
        const char *const *GP = C13_GRP;
        float p = (float)(now - C13.tab_t0) / (float)C13_XF_MS;
        if (!cl13_anim_off()) { w_alpha(ui_w(GP[C13.prev_tab]), p >= 1.0f ? 1.0f : 1.0f - cl13_eo(p)); w_alpha(ui_w(GP[C13.tab]), p >= 1.0f ? 1.0f : cl13_eo(p)); }
    }
    gu_fade_tick(now);
    cl13_fx_tick(now);
    cl13_preload_tick();
    cl13_pic_tick(now);
    {   // page fade-in: 0 -> 1 over 220 ms (after the art gate), in 1/24 steps
        static int last_q = -1; static uint64_t last_enter;
        if (C13.enter_ms != last_enter) { last_enter = C13.enter_ms; last_q = -1; }
        float f = now < C13.enter_ms + C13_GATE_MS ? 0.0f : (float)(now - C13.enter_ms - C13_GATE_MS) / 220.0f;
        if (f > 1.0f) f = 1.0f;
        f = 1.0f - (1.0f - f) * (1.0f - f);
        int q = (int)(f * 24.0f + 0.5f);
        if (q != last_q) { last_q = q; w_alpha(ui_w("anim-group"), (float)q / 24.0f); }
    }
}
// ------------------------------------------------------------------ the way in: C or the pad's menu-action on the MP main menu with a living clan (called from feature_clan)
static void cl13_open_check(void) {
    static int h_act, armed;
    // the way in is the CLAN row of the MP menu list (modepick_widgets.add_clan_row, same native button as FIND MATCH): select on it (Enter / pad A) or a click.
    // The F key / the pad's menu-action and the "OPEN THE CLAN" hint are gone. Keyboard, pad and mouse all work through the menu row.
    int pad = 0;
    if (!cl13_enabled()) ui_visible("anim-group.menuList.Clan", 0);
    else {
        int sel = menu_edge(0x6695c5b7921bb5ddULL /* menu-select */, &h_act);
        int clk = g_click_edge && ui_mouse_over("anim-group.menuList.Clan", 1);
        if (!armed) { armed = 1; sel = 0; }                           // a button held on arrival does not open it
        if (g_mdpk.open || g_mdpk.chosen) { sel = 0; clk = 0; }       // (the mode box is modal: its clicks / selects are its own, never the CLAN row's)
        if ((sel && mk_focused("anim-group.menuList.Clan") && mk_sel_for("anim-group.menuList.Clan")) || clk) pad = 1;
        if (pad) xlog("clan13 open: via %s, LBUTTON %d, cursor over CLAN %d, FIND MATCH %d, focused CLAN %d, click edge %d", clk ? "click at press" : "select (key/pad)", g_lb_now,
            ui_mouse_over("anim-group.menuList.Clan", 1), ui_mouse_over("anim-group.menuList.FindMatch", 1), mk_focused("anim-group.menuList.Clan"), g_click_edge);
    }
    int test = 0;                                                     // dev (screenshots with no keyboard focus): t2r-clan-test.txt next to the exe =
    { static uint64_t tchk; uint64_t tn = GetTickCount64();           // open the page, RAIDS tab, newest raid, PLAYER STATS ("stats") or just the page ("open"); deleted once used
      if (tn - tchk > 1000) { tchk = tn; FILE *f = exe_side_open("t2r-clan-test.txt", "r"); if (f) { char b[16] = {0}; fgets(b, sizeof b, f); fclose(f); test = !strncmp(b, "stats", 5) ? 2 : !strncmp(b, "tab", 3) && b[3] >= '0' && b[3] <= '4' ? 10 + b[3] - '0' : 1; } } }      // "tab0".."tab4" = that tab (A/B screenshots)
    if (!(pad || test) || !cl13_enabled() || g_lo_state != LO_NONE) return;
    // fix1025-clanopen: never once the pre-match sequence (vote / gear up / loading) or a match is running, or while a clan screen is due
    if (g_mf_code_now >= 100 || g_mh_load || g_mh_st || g_ls_own || !ms_on_menu() || g_pm.pending) return;
    static uint64_t last;
    uint64_t now = GetTickCount64();
    if (now - last < 1500) return;
    last = now;
    if (test) { g_c13_test = test; g_c13_test_ms = now; DeleteFileA("t2r-clan-test.txt"); }
    xlog("clan13: %s - pushing to1/clan13", test ? "t2r-clan-test.txt" : "CLAN row of the MP menu selected");
    if (pad) ui_sfx("sfx-select");
    push_page("to1/clan13");
}
