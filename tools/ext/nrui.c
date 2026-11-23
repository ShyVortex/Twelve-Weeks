// nrui.c - the shared No Return page frame of the UI redesign (re/ui-redesign-1117/PROPOSAL.md, re/ui-refs-1117/STYLE.md).
// Widgets: tools/features/nr_style.py (frame / section / bar / tile / chip). Included before gearup13.c, so GEAR UP, the CLAN pages and the pages
// of other branches (achievements, customize) all fill the same frame:
//   nr_header("WLF CLAN", "OVERVIEW")      breadcrumb hdPar | hdDiv | hdPage + hdRule, placed from the measured (translated) widths
//   nr_week(week, day, survived)           wkDay / wkSv / wkBarF, the top right block
//   nr_prompts(items, n)                   boxed key prompts pb0.., right to left from x 3700 (unavailable ones at 40 %)
//   nr_clan_tabs(active, hover)            the Q / E strip tb0..: the 5 clan tabs + the registered extension pages (nr_clan_xtab_add)
// Widget space 3840 x 2160. Every write goes through the deduped setters (ui_text / w_pivot / w_scale / w_alpha skip a repeat value).

#define NR_R1 3700.0f
#define NR_L0 148.0f
#define NR_HEAD_PT 54.0f
#define NR_RULE_W0 1000.0f            // nr_style.RULE_W0: the template width of every scaled rule / fill
#define NR_HAIR 4.0f                  // nr_style.HAIR: hairline thickness (gui2 drops a rect thinner than 1 screen px)
#define NR_TAB_PT 36.0f
#define NR_TAB_Y 270.0f
#define NR_PROMPT_PT 36.0f
#define NR_PROMPT_KEY_PT 24.0f
#define NR_PROMPT_Y 2000.0f
#define NR_PROMPT_H 88.0f
#define NR_PB_W0 400.0f               // nr_style.PB_W0
#define NR_NPROMPT 6
#define NR_MAX_TABS 8
#define NR_WK_X0 (NR_R1 - 760.0f)
#define NR_WK_W 760.0f

static float nr_cw(const unsigned char *q) { return *q == ' ' ? 0.40f : (*q >= 'a' && *q <= 'z') || *q >= 0x80 ? 0.62f : 0.80f; }
static float nr_est(const char *t, float pt) {          // = gearup13.c gu_est: the estimated width of t (translated, colour tags skipped)
    const char *tr = loc_tr(t ? t : "");
    float est = 0.0f;
    int tag = 0;
    for (const unsigned char *q = (const unsigned char *)(tr ? tr : t ? t : ""); *q; q++) {
        if (*q == '<') tag = 1;
        if (tag) { if (*q == '>') tag = 0; continue; }
        if ((*q & 0xC0) == 0x80) continue;
        est += nr_cw(q);
    }
    return est * pt;
}
static float nr_tw(const char *t, float pt) { return nr_est(t, pt) * 1.06f; }     // nr_style: est * 1.06 (the tracking)
// A finer per-character width (the prompt boxes / quick reply chips had room left at their right; long chat lines ran out of the box): the game's
// menu face (DINPro Medium, core.psarc fonts/seriffont-Medium.otf) advance widths for ' ' .. '~', in the units of nr_cw (x pt x 1.06 = widget units), scaled to the
// in-game width of "TYPE A MESSAGE" at 36 pt (388 units, screenshot). Other characters (Polish letters etc.): 0.66.
// Used where a box is fitted to its text (nr_prompts' labels, the friends page chips, the chat rows); nr_cw / nr_est stay for the rest of the layouts.
static const float NR_CWF[95] = {
    0.308f, 0.427f, 0.570f, 0.863f, 0.781f, 1.082f, 0.938f, 0.330f, 0.407f, 0.407f, 0.623f, 0.685f,
    0.349f, 0.547f, 0.357f, 0.488f, 0.685f, 0.685f, 0.685f, 0.685f, 0.685f, 0.685f, 0.685f, 0.685f,
    0.685f, 0.685f, 0.389f, 0.389f, 0.685f, 0.685f, 0.685f, 0.657f, 0.946f, 0.803f, 0.852f, 0.807f,
    0.856f, 0.775f, 0.752f, 0.834f, 0.888f, 0.378f, 0.650f, 0.845f, 0.737f, 1.045f, 0.928f, 0.830f,
    0.808f, 0.830f, 0.842f, 0.758f, 0.719f, 0.867f, 0.725f, 1.119f, 0.743f, 0.699f, 0.709f, 0.446f,
    0.488f, 0.446f, 0.734f, 0.734f, 0.642f, 0.681f, 0.710f, 0.623f, 0.710f, 0.692f, 0.421f, 0.705f,
    0.727f, 0.339f, 0.339f, 0.704f, 0.400f, 1.127f, 0.730f, 0.690f, 0.710f, 0.710f, 0.564f, 0.641f,
    0.439f, 0.730f, 0.605f, 0.955f, 0.646f, 0.601f, 0.603f, 0.523f, 0.434f, 0.523f, 0.737f,
};
static float nr_cwf(const unsigned char *q) { return *q >= 32 && *q < 127 ? NR_CWF[*q - 32] : *q >= 0x80 ? 0.66f : 0.0f; }
static float nr_twf(const char *t, float pt) {          // = nr_tw with nr_cwf (translated, colour tags skipped)
    const char *tr = loc_tr(t ? t : "");
    float est = 0.0f;
    int tag = 0;
    for (const unsigned char *q = (const unsigned char *)(tr ? tr : t ? t : ""); *q; q++) {
        if (*q == '<') tag = 1;
        if (tag) { if (*q == '>') tag = 0; continue; }
        if ((*q & 0xC0) == 0x80) continue;
        est += nr_cwf(q);
    }
    return est * pt * 1.06f;
}

// a rule / bar fill built at NR_RULE_W0 with its pivot at the left middle: move its left end to x and make it w long
static void nr_rule(const char *path, float x, float y, float w) {
    uint64_t r = ui_w(path);
    if (!r) return;
    if (w < 2.0f) w = 2.0f;
    w_pivot(r, x, y);
    w_scale(r, w / NR_RULE_W0, 1.0f);
}
// a bar fill (nr_style.bar <name>F, x0..x1): frac 0..1; hidden at 0
static void nr_bar(const char *path_f, float x0, float x1, float y_mid, float frac) {
    uint64_t r = ui_w(path_f);
    if (!r) return;
    if (frac < 0.0f) frac = 0.0f; if (frac > 1.0f) frac = 1.0f;
    w_visible(r, frac > 0.004f);
    if (frac <= 0.004f) return;
    w_pivot(r, x0, y_mid);
    w_scale(r, (x1 - x0) * frac / NR_RULE_W0, 1.0f);
}
// a text widget shrunk (about its own pivot: nr_style.lm = left or right middle) so it fits box; never below 0.6
static void nr_fit(const char *path, const char *t, float box, float pt) {
    ui_text(path, t ? t : "");
    uint64_t w = ui_w(path);
    if (!w) return;
    float e = nr_est(t, pt), s = e > box && e > 0.0f ? box / e : 1.0f;
    if (s < 0.6f) s = 0.6f;
    w_scale(w, s, s);
}

// ---- glides (UI navigation and scrolling were choppy): the focus outline and the scroll
// thumb used to jump to their new place in one frame. They now ease there (exponential, NR_GL_TAU_MS; frame-time based on the performance counter),
// written every frame by nr_glide_tick (t2r_tick, after the pages) only while one moves. A newly shown outline / a rebuilt page snaps (no glide in
// from where an old page left it). t2r-gu-noanim.txt = no glides (the plain page).
static int gu_noanim(void);            // gearup13.c
#define NR_NGL 12
#define NR_GL_TAU_MS 38.0f
enum { NR_GL_FRAME = 1, NR_GL_THUMB = 2 };
typedef struct { char base[72]; int kind; uint64_t h; float c[4], t[4]; } nr_gl_t;
static nr_gl_t g_nr_gl[NR_NGL];
static int g_nr_gl_moving;
static void nr_frame_draw(const char *base, const float *v) {
    char p[128];
    static const char S[4] = {'T', 'B', 'L', 'R'};
    float x = v[0], y = v[1], w = v[2], h = v[3];
    for (int k = 0; k < 4; k++) {
        snprintf(p, sizeof p, "%s%c", base, S[k]);
        uint64_t r = ui_w(p);
        if (!r) continue;
        w_visible(r, 1);
        if (k == 0) { w_pivot(r, x, y + 2.0f); w_scale(r, w / 100.0f, 1.0f); }
        else if (k == 1) { w_pivot(r, x, y + h - 2.0f); w_scale(r, w / 100.0f, 1.0f); }
        else { w_pivot(r, k == 2 ? x : x + w - 4.0f, y); w_scale(r, 1.0f, h / 100.0f); }
    }
}
static void nr_thumb_draw(const char *base, const float *v) {      // v = x, y, length, built height
    char p[128];
    snprintf(p, sizeof p, "%sH", base);
    uint64_t r = ui_w(p);
    if (!r) return;
    w_pivot(r, v[0], v[1]);
    w_scale(r, 1.0f, v[2] / (v[3] > 1.0f ? v[3] : 1.0f));
}
static void nr_gl_drop(const char *base) { for (int i = 0; i < NR_NGL; i++) if (g_nr_gl[i].base[0] && !strcmp(g_nr_gl[i].base, base)) g_nr_gl[i].base[0] = 0; }
// target t for base (h = the handle of one of its widgets: another handle = a rebuilt page -> snap); returns the slot (its c = what to draw now)
static nr_gl_t *nr_gl_set(const char *base, int kind, uint64_t h, const float *t) {
    nr_gl_t *g = NULL, *fr = NULL;
    for (int i = 0; i < NR_NGL; i++) {
        if (g_nr_gl[i].base[0] && !strcmp(g_nr_gl[i].base, base)) { g = &g_nr_gl[i]; break; }
        if (!fr && !g_nr_gl[i].base[0]) fr = &g_nr_gl[i];
    }
    int snap = 0;
    if (!g) { g = fr ? fr : &g_nr_gl[0]; snprintf(g->base, sizeof g->base, "%s", base); snap = 1; }
    if (g->h != h || g->kind != kind || gu_noanim()) snap = 1;
    g->h = h; g->kind = kind;
    for (int k = 0; k < 4; k++) { g->t[k] = t[k]; if (snap) g->c[k] = t[k]; }
    if (!snap) g_nr_gl_moving = 1;
    return g;
}
static void nr_glide_tick(void) {
    static LARGE_INTEGER f, last;
    LARGE_INTEGER now;
    if (!f.QuadPart) QueryPerformanceFrequency(&f);
    QueryPerformanceCounter(&now);
    float dt = last.QuadPart ? (float)((double)(now.QuadPart - last.QuadPart) * 1000.0 / (double)f.QuadPart) : 16.0f;
    last = now;
    if (!g_nr_gl_moving) return;
    if (dt > 100.0f) dt = 100.0f;
    float k = 1.0f - expf(-dt / NR_GL_TAU_MS);
    int moving = 0;
    for (int i = 0; i < NR_NGL; i++) {
        nr_gl_t *g = &g_nr_gl[i];
        if (!g->base[0]) continue;
        int done = 1;
        for (int j = 0; j < 4; j++) {
            float d = g->t[j] - g->c[j];
            if (d > 0.5f || d < -0.5f) { g->c[j] += d * k; done = 0; } else g->c[j] = g->t[j];
        }
        if (g->kind == NR_GL_FRAME) {           // (the page is gone / rebuilt: stop, the next nr_frame_at snaps)
            char p[96]; snprintf(p, sizeof p, "%sT", g->base);
            if (ui_w(p) != g->h) { g->base[0] = 0; continue; }
            nr_frame_draw(g->base, g->c);
        } else {
            char p[96]; snprintf(p, sizeof p, "%sH", g->base);
            if (ui_w(p) != g->h) { g->base[0] = 0; continue; }
            nr_thumb_draw(g->base, g->c);
        }
        if (!done) moving = 1;
    }
    g_nr_gl_moving = moving;
}
// a movable focus outline (nr_style.focus_frame <base>T/B/L/R, thickness th) around the box x, y, w, h; on 0 hides it. It glides to a new place.
static void nr_frame_at(const char *base, float x, float y, float w, float h, int on) {
    char p[128];
    static const char S[4] = {'T', 'B', 'L', 'R'};
    if (!on) {
        nr_gl_drop(base);                       // (shown again later: it snaps there)
        for (int k = 0; k < 4; k++) { snprintf(p, sizeof p, "%s%c", base, S[k]); uint64_t r = ui_w(p); if (r) w_visible(r, 0); }
        return;
    }
    snprintf(p, sizeof p, "%sT", base);
    uint64_t r = ui_w(p);
    if (!r) return;
    float t[4] = {x, y, w, h};
    nr_frame_draw(base, nr_gl_set(base, NR_GL_FRAME, r, t)->c);
}
// a vertical scroll thumb (nr_style.scroll_v <base>H at track x, top-left pivot, built at height h0): rows first .. first + shown of n; hidden when all fit.
// It glides like the focus outline.
static void nr_scroll_v(const char *base, float x, float y0, float y1, float h0, int first, int shown, int n) {
    char p[128];
    int on = n > shown && n > 0;
    snprintf(p, sizeof p, "%sT", base); ui_visible(p, on);
    snprintf(p, sizeof p, "%sH", base); ui_visible(p, on);
    if (!on) { nr_gl_drop(base); return; }
    uint64_t r = ui_w(p);
    if (!r) return;
    float a = (float)first / (float)n, b = (float)(first + shown) / (float)n, len = (y1 - y0) * (b - a);
    if (len < 8.0f) len = 8.0f;
    float t[4] = {x - 2.0f, y0 + (y1 - y0) * a, len, h0};
    nr_thumb_draw(base, nr_gl_set(base, NR_GL_THUMB, r, t)->c);
}

// a chip (nr_style.chip <base>Bg built at NR_CHIP_W0 with a left-middle pivot, <base>Tx left aligned): the box sized to t; right > 0 = right aligned at right (x ignored)
#define NR_CHIP_W0 100.0f
static float nr_chip(const char *base, const char *t, float x, float right, float pt) {
    char p[128];
    float w = nr_tw(t, pt) + 32.0f, px, py;
    if (right > 0.0f) x = right - w;
    snprintf(p, sizeof p, "%sTx", base); ui_text(p, t ? t : "");
    uint64_t r = ui_w(p);
    if (r && w_pivot_get(r, &px, &py)) w_pivot(r, x + 16.0f, py);
    snprintf(p, sizeof p, "%sBg", base);
    r = ui_w(p);
    if (r && w_pivot_get(r, &px, &py)) { w_pivot(r, x, py); w_scale(r, w / NR_CHIP_W0, 1.0f); }
    return w;
}

// ------------------------------------------------------------------ header + week
static void nr_header(const char *parent, const char *page) {
    char tp[160];
    snprintf(tp, sizeof tp, "%s", parent ? parent : "");
    ui_text("anim-group.hdPar", tp);
    float x = NR_L0 + nr_tw(tp, NR_HEAD_PT) + 52.0f;
    uint64_t d = ui_w("anim-group.hdDiv");
    if (d) w_pivot(d, x, 168.0f - 34.0f);
    uint64_t pg = ui_w("anim-group.hdPage");
    if (pg) w_pivot(pg, x + 52.0f, 168.0f);
    ui_text("anim-group.hdPage", page ? page : "");
    float x2 = x + 52.0f + nr_tw(page, NR_HEAD_PT) + 52.0f;
    nr_rule("anim-group.hdRule", x2, 168.0f, NR_R1 - x2);
}
static void nr_week(int week, int day, int survived) {
    char b[96];
    snprintf(b, sizeof b, "WEEK %d: DAY %d", week, day);
    ui_text("anim-group.wkDay", b);
    snprintf(b, sizeof b, "DAYS SURVIVED %d | 84", survived);
    ui_text("anim-group.wkSv", b);
    nr_bar("anim-group.wkBarF", NR_WK_X0, NR_WK_X0 + NR_WK_W, 352.0f + 3.0f, (float)survived / 84.0f);
}
static void nr_week_visible(int on) {
    ui_visible("anim-group.wkDay", on); ui_visible("anim-group.wkSv", on); ui_visible("anim-group.wkBarT", on); ui_visible("anim-group.wkBarF", on);
    char p[48];
    for (int k = 1; k < 12; k++) { snprintf(p, sizeof p, "anim-group.wkTk%d", k); ui_visible(p, on); }
}

// ------------------------------------------------------------------ prompts
// kb: the key (an engine glyph id "menu:select" / "menu:back" / "menu:action" / "menu:prev" / "menu:next", two ids joined by '+' for a pair
// such as "menu:prev+menu:next", or plain key text "W / S" drawn in a white box); pad: the same for the controller (NULL = kb). A menu:* glyph is
// the device's own picture (the keyboard key in a white box, the pad button), so most prompts pass one id for both.
typedef struct { const char *kb, *pad, *label; int on; } nr_prompt_t;
static float g_nr_pb_x0[NR_NPROMPT], g_nr_pb_x1[NR_NPROMPT];   // laid out boxes (canvas x), for the hover test
static int g_nr_pb_n;
static void nr_prompts(const nr_prompt_t *it, int n) {
    char p[64];
    float x = NR_R1;
    if (n > NR_NPROMPT) n = NR_NPROMPT;
    g_nr_pb_n = n;
    for (int k = 0; k < NR_NPROMPT; k++) {
        snprintf(p, sizeof p, "anim-group.pbar.pb%d", k);
        if (k >= n) { ui_visible(p, 0); continue; }
        const nr_prompt_t *q = &it[n - 1 - k];               // right to left: the last item sits at the right edge
        const char *key = g_pad_mode && q->pad ? q->pad : q->kb ? q->kb : "";
        char k1[48] = "", k2[48] = "";
        int glyph = !strncmp(key, "menu:", 5);
        if (glyph) {
            const char *plus = strchr(key, '+');
            if (plus) { snprintf(k1, sizeof k1, "%.*s", (int)(plus - key), key); snprintf(k2, sizeof k2, "%s", plus + 1); }
            else snprintf(k1, sizeof k1, "%s", key);
        }
        float kw = glyph ? (k2[0] ? 136.0f : 64.0f) : nr_tw(key, NR_PROMPT_KEY_PT) + 28.0f;
        if (!glyph && kw < 60.0f) kw = 60.0f;
        float lw = nr_twf(q->label, NR_PROMPT_PT);
        float tot = 18.0f + kw + 22.0f + lw + 26.0f;            // (the label centred between the key and the box's right edge - was + 34 with the coarser width)
        ui_visible(p, 1);
        w_pivot(ui_w(p), x - tot, NR_PROMPT_Y - NR_PROMPT_H / 2.0f);
        g_nr_pb_x0[k] = x - tot; g_nr_pb_x1[k] = x;
        float ea = q->on ? 70.0f / 255.0f : 30.0f / 255.0f;
        static const char *const S4[4] = {"T", "B", "L", "R"};
        for (int s = 0; s < 4; s++) {
            snprintf(p, sizeof p, "anim-group.pbar.pb%d.pb%d%s", k, k, S4[s]);
            uint64_t w = ui_w(p);
            if (!w) continue;
            w_alpha(w, ea);
            if (s < 2) w_scale(w, tot / NR_PB_W0, 1.0f);
            if (s == 3) w_pivot(w, tot - NR_HAIR, 0.0f);
        }
        snprintf(p, sizeof p, "anim-group.pbar.pb%d.pb%dKg", k, k);  ui_visible(p, glyph); if (glyph) { ui_image(p, k1); w_alpha(ui_w(p), q->on ? 1.0f : 0.4f); }
        snprintf(p, sizeof p, "anim-group.pbar.pb%d.pb%dKg2", k, k); ui_visible(p, glyph && k2[0]); if (glyph && k2[0]) { ui_image(p, k2); w_alpha(ui_w(p), q->on ? 1.0f : 0.4f); }
        snprintf(p, sizeof p, "anim-group.pbar.pb%d.pb%dKb", k, k);
        ui_visible(p, !glyph);
        if (!glyph) { uint64_t w = ui_w(p); w_scale(w, kw / 100.0f, 1.0f); w_alpha(w, q->on ? 1.0f : 0.4f); }
        snprintf(p, sizeof p, "anim-group.pbar.pb%d.pb%dKt", k, k);
        ui_visible(p, !glyph);
        if (!glyph) {
            ui_text(p, key);
            uint64_t w = ui_w(p);
            w_pivot(w, 18.0f + kw / 2.0f - 50.0f, 16.0f);       // (a 100 wide centred box: its left edge so its centre is the key box's)
        }
        snprintf(p, sizeof p, "anim-group.pbar.pb%d.pb%dTx", k, k);
        {
            char lb[96];
            snprintf(lb, sizeof lb, q->on ? "%s" : "<font color=\"#585858\">%s</font>", q->label ? q->label : "");
            ui_text(p, lb);
            w_pivot(ui_w(p), 18.0f + kw + 22.0f, NR_PROMPT_H / 2.0f);
        }
        x -= tot + 28.0f;
    }
}
// the prompt under the mouse: index into the items passed to nr_prompts (0 = the first item), -1 = none
static int nr_prompt_hover(void) {
    float cx, cy;
    if (g_pad_mode || !ui_cursor_canvas(&cx, &cy)) return -1;
    if (cy < NR_PROMPT_Y - NR_PROMPT_H / 2.0f - 6.0f || cy > NR_PROMPT_Y + NR_PROMPT_H / 2.0f + 6.0f) return -1;
    for (int k = 0; k < g_nr_pb_n; k++) if (cx >= g_nr_pb_x0[k] && cx <= g_nr_pb_x1[k]) return g_nr_pb_n - 1 - k;
    return -1;
}

// ------------------------------------------------------------------ section header (nr_style.section): the rule between the title and the right text
static void nr_section(const char *base, float x0, float x1, float y, const char *title, const char *right, float title_pt) {
    char p[128];
    snprintf(p, sizeof p, "%sTx", base); ui_text(p, title ? title : "");
    snprintf(p, sizeof p, "%sRt", base); ui_text(p, right ? right : "");
    float xa = x0 + nr_tw(title, title_pt) + 40.0f;
    float xb = x1 - (right && right[0] ? nr_tw(right, 33.0f) + 40.0f : 0.0f);
    snprintf(p, sizeof p, "%sRl", base); nr_rule(p, xa, y, xb - xa);
}

// ------------------------------------------------------------------ the clan tab strip + extension pages
// The 5 clan tabs live on to1/clan13 (clan13.c). Other pages register as further tabs (achievements, customize): Q / E walks through all of them and
// the clan stays "up" (g_cl13_up) while one of them is on top.
typedef struct { const char *label; int (*avail)(void); void (*open)(const char *why); uint64_t (*page)(void); } nr_xtab_t;
#define NR_NXTAB 3
static nr_xtab_t g_nr_xtab[NR_NXTAB];
static int g_nr_nxtab;
static const char *const NR_CLAN_TABS[5] = {"OVERVIEW", "SURVIVORS", "RAIDS", "JOURNAL", "MISSIONS"};
static int nr_clan_xtab_add(const char *label, int (*avail)(void), void (*open)(const char *why), uint64_t (*page)(void)) {
    for (int i = 0; i < g_nr_nxtab; i++) if (g_nr_xtab[i].open == open) return 5 + i;
    if (g_nr_nxtab >= NR_NXTAB) return -1;
    g_nr_xtab[g_nr_nxtab] = (nr_xtab_t){label, avail, open, page};
    return 5 + g_nr_nxtab++;
}
static int nr_xtab_on(int i) { return i >= 0 && i < g_nr_nxtab && (!g_nr_xtab[i].avail || g_nr_xtab[i].avail()); }
static int nr_clan_ntabs(void) { int n = 5; for (int i = 0; i < g_nr_nxtab; i++) if (nr_xtab_on(i)) n++; return n; }
static int nr_xtab_of(int tab) {                      // tab index (>= 5) -> registry entry, skipping unavailable ones
    int t = 5;
    for (int i = 0; i < g_nr_nxtab; i++) if (nr_xtab_on(i)) { if (t == tab) return i; t++; }
    return -1;
}
static const char *nr_clan_tab_label(int tab) { if (tab < 5) return tab >= 0 ? NR_CLAN_TABS[tab] : ""; int i = nr_xtab_of(tab); return i >= 0 ? g_nr_xtab[i].label : ""; }
static int nr_clan_xtab_route(uint64_t top) {        // 1 = an extension tab page is the top page
    for (int i = 0; i < g_nr_nxtab; i++) if (g_nr_xtab[i].page && top && g_nr_xtab[i].page() == top) return 1;
    return 0;
}
static int nr_clan_tab_of_page(uint64_t top) {       // the tab index of an extension page on top, -1 = none
    int t = 5;
    for (int i = 0; i < g_nr_nxtab; i++) if (nr_xtab_on(i)) { if (g_nr_xtab[i].page && g_nr_xtab[i].page() == top) return t; t++; }
    return -1;
}
static void cl13_go_tab(int tab, const char *why);    // clan13.c: open the clan page on tab 0..4 (from any page)
static void nr_clan_go(int tab, const char *why) {
    int n = nr_clan_ntabs();
    tab = (tab % n + n) % n;
    if (tab < 5) { cl13_go_tab(tab, why); return; }
    int i = nr_xtab_of(tab);
    if (i >= 0 && g_nr_xtab[i].open) g_nr_xtab[i].open(why);
}
static float g_nr_tabx[NR_MAX_TABS], g_nr_tabw[NR_MAX_TABS];
static int g_nr_ntab;
static void nr_clan_tabs(int active, int hover) {
    char p[64];
    int n = nr_clan_ntabs();
    if (n > NR_MAX_TABS) n = NR_MAX_TABS;
    g_nr_ntab = n;
    float x = NR_L0 + 108.0f;
    for (int k = 0; k < NR_MAX_TABS; k++) {
        snprintf(p, sizeof p, "anim-group.tabs.tb%d", k);
        ui_visible(p, k < n);
        snprintf(p, sizeof p, "anim-group.tabs.tbHit%d", k);
        ui_visible(p, k < n);
        if (k >= n) continue;
        const char *lb = nr_clan_tab_label(k);
        float w = nr_tw(lb, NR_TAB_PT) + 8.0f;
        g_nr_tabx[k] = x; g_nr_tabw[k] = w;
        char tx[96];
        snprintf(tx, sizeof tx, k == active || k == hover ? "%s" : "<font color=\"#8C8C8C\">%s</font>", lb);
        snprintf(p, sizeof p, "anim-group.tabs.tb%d", k);
        ui_text(p, tx);
        w_pivot(ui_w(p), x, NR_TAB_Y);
        snprintf(p, sizeof p, "anim-group.tabs.tbHit%d", k);
        w_pivot(ui_w(p), x - 30.0f, NR_TAB_Y - 60.0f);
        x += w + 80.0f;
    }
    float ex = x - 80.0f + 28.0f;
    w_pivot(ui_w("anim-group.tabs.tbE"), ex + 30.0f, NR_TAB_Y);
    w_pivot(ui_w("anim-group.tabs.tbEHit"), ex + 30.0f, NR_TAB_Y);
    if (active >= 0 && active < n) {                   // tbU: template width 100 (nr_style.tabs)
        uint64_t u = ui_w("anim-group.tabs.tbU");
        ui_visible("anim-group.tabs.tbU", 1);
        if (u) { w_pivot(u, g_nr_tabx[active], NR_TAB_Y + 38.0f); w_scale(u, g_nr_tabw[active] / 100.0f, 1.0f); }
    }
    else ui_visible("anim-group.tabs.tbU", 0);
}
// the tab under the mouse (-1 none), -2 = the Q glyph, -3 = the E glyph
static int nr_clan_tab_hover(void) {
    float cx, cy;
    if (g_pad_mode || !ui_cursor_canvas(&cx, &cy) || cy < NR_TAB_Y - 60.0f || cy > NR_TAB_Y + 60.0f) return -1;
    if (cx >= NR_L0 - 20.0f && cx <= NR_L0 + 80.0f) return -2;
    for (int k = 0; k < g_nr_ntab; k++) if (cx >= g_nr_tabx[k] - 30.0f && cx <= g_nr_tabx[k] + g_nr_tabw[k] + 30.0f) return k;
    if (g_nr_ntab > 0) { float ex = g_nr_tabx[g_nr_ntab - 1] + g_nr_tabw[g_nr_ntab - 1] + 28.0f; if (cx >= ex - 20.0f && cx <= ex + 80.0f) return -3; }
    return -1;
}
