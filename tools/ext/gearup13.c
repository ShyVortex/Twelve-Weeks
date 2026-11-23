// gearup13.c - the 2013-layout GEAR UP page
// .
// Included after skills.c / gunlimit.c (it uses their loadout helpers). The widgets are tools/features/gearup13_widgets.py (page to1/gearup13, built
// from the same Builder as to1/matchflow); like the match flow pages this one is driven ENTIRELY from the tick - no winmm page handler runs for it -
// and every text / icon / visibility goes through the dedup writers (ui_text, ui_image, ui_visible, w_alpha: no per-frame rewrites, no flicker).
//
// Two views in ONE page (a second instance of a page on the stack breaks it):
//   LIST  the 6 custom loadouts g_lo[] + the 8 CLASSES presets, the focused loadout's gear and points on the right (2013factionsloadout4).
//         CREATE LOADOUT under the custom loadouts adds one (up to N_CUSTOM_MAX: a name box, then the new loadout's edit view).
//         SELECT on a class equips it; on a custom loadout it equips it and opens the edit view; pre-match (CHOOSE LOADOUT) / mid-match (CHANGE
//         LOADOUT) it only equips (mid-match through g_lo_pending, the lobby object keeps this life's loadout: lo_snap_tick).
//   EDIT  CUSTOM LOADOUT n (2013factionsloadout1): 7 slots (small, large, 4 skills, purchasable) | the focused slot's options listed at once |
//         the hovered option's details. A click / SELECT on an option equips it and STAYS in the options list (no page change); every change is
//         written straight into the lobby object (+0x2c58 guns, sk_slot_set skills) and into g_lo[active] / t2r-loadout.txt.
// Keys: W / S (menu-up / down) move, A / D (menu-left / right) slots <-> options (a skill's level inside the options), SELECT / left click
// equips, menu-back / Esc / right click: options -> slots -> list -> out. Mouse: hover focuses, click equips, wheel scrolls the options.
// t2r-no-gearup13.txt next to the exe: off (the old picker-skill flow runs unchanged). Log prefix "gearup13:".
// The list (the old layout in the new style; gearup13_widgets.py): the old three columns in the No Return frame - a vertical
// list (the custom loadouts + CREATE LOADOUT in a window of GU_VISC rows that scrolls, G.coff = the first shown; then the classes), the gear rows, the
// details. lsRow0..6 are the custom window's rows, lsRow7..14 the classes. G.lst / G.pv / g_gu_hov_lst are list POSITIONS: the custom slots
// 0..g_lo_n-1, then CREATE LOADOUT (g_lo_n), then the classes (gu_pos_idx / gu_idx_pos map them to loadout indexes; gu_pos_row / gu_pos_col to the block
// and the row in it). Up / down = the next / previous position (wraps), left / right = the other block (the row in it kept in G.wcol). The prompts are
// nrui.c's boxed ones (gu_prompts), the header its breadcrumb (gu_title).
#define GU_VISC 7                                // custom rows on screen (gearup13_widgets.py LIST_VISC): the customs + CREATE LOADOUT scroll in it
#define GU_N_ROWW (GU_VISC + 8)                  // lsRow widgets: the custom window + the 8 classes (gearup13_widgets.py LIST_W)
#define GU_SLOTS 7
#define GU_OPT_ROWS 9
#define GU_LP_TOTAL 13
#define GU_MAX_OPT 80
#define GU_NONE_ICON "streaming/t2r/icons/blocked.png"
#define GU_EMPTY_ICON "hud/weapon-cross/empty-slot.svg"
enum { GS_SMALL, GS_LARGE, GS_SK1, GS_SK2, GS_SK3, GS_SK4, GS_PURCH };       // the slot column's order (2013factionsloadout1)
enum { GO_NONE, GO_GUN, GO_PURCH, GO_SKILL };
typedef struct { int kind; uint32_t row; uint32_t base; int supp; int sj; } gu_opt_t;   // gun: table row, its base row, suppressed row?, its suppressed row (-1); skill: row = skill id
static gu_opt_t g_gu_opt[GU_MAX_OPT];
static int g_gu_nopt;
static int g_gu_lvl[SK_COUNT];                  // the level shown (and equipped on a click) per skill
static int g_gu_hov_lst = -1, g_gu_hov_slot = -1, g_gu_hov_opt = -1, g_gu_hov_lvl = -1, g_gu_hov_back, g_gu_hov_sel, g_gu_hov_rst, g_gu_hov_tg, g_gu_hov_ren;   // gu13_scan (once a frame, from the click gate)
static struct {
    int up, view, col, lst, slot, opt, off, dirty; uint64_t click_f;        // view 0 list / 1 edit, col 0 slots / 1 options, lst = focused loadout, slot / opt / off = edit focus + options window
    int h_sel, h_u, h_d, h_l, h_r, h_back, h_esc, h_act, h_r_key;         // held states of the menu actions (edges)
    uint64_t t_u, t_d, enter_ms, back_f, sfx_ms;
    int det_key, det_ph, det_hold, view_anim, pre_i; uint64_t det_t0, view_t0;     // animation state (gu_anim_tick)
    int pv, pv_want, pv_ph, pv_ign, pv_lasthov, pv_lastlst, pv_lastwant; float pv_a; uint64_t pv_t0, pv_chg;   // list preview: shown row / wanted row / tween phase (0 idle, 1 out, 2 in)
    int stage, closing, hv_slot, hv_opt, mm_last, h_nx, h_e;        // h_nx / h_e: menu-next / the E key (RENAME)        // mm_last / hv_*: the mouse state of the last frame (hover acts on a change)
    int coff, cloff, wcol;                                           // the first tile column shown in row 0 / row 1 (customs + CREATE scroll sideways), the column up / down keeps
} G;
static struct { int ok, view, col, slot, opt, off; } g_gu_keep;    // the edit view's place, kept across the engine's own pop + our push on menu-back
// RENAME state (the name being typed: code points, cursor, the pad's held states; see the RENAME section)
// mode 0: RENAME on the edit view; 1: the CREATE LOADOUT name box on the list; 2: RENAME of the focused custom loadout on the list (slot = its custom slot; 0 uses the active one). sel: the prefilled default is selected (the first letter typed replaces it),
// dflt: the text is still the prefilled default (saved as "" = the default label, so it follows the language)
static struct { int on, mode, sel, dflt, n, cur, pad, slot, h_u, h_d, h_l, h_r, h_sel, h_act, h_back, h_nx; uint32_t cp[LO_NM_MAX]; uint64_t t_u, t_d, t0, f0, click_f; } GN;
static volatile LONG g_kt_on;               // 1 = a name is typed: the keyboard hook eats the keys (kt_ll_proc)
static volatile LONG g_kt_enter;            // 1 = only Enter is eaten (chat.c: the in-game chat can open; Enter reaches kt_next, never the game or the menu)

static uint64_t gu13_page_id(void) { static uint64_t id; if (!id) id = page_id("gearup13"); return id; }
static int gu_npos(void) { return g_lo_n + 1 + N_CLASSES; }
static int gu_pos_idx(int pos) {                 // list position -> loadout index (-1: CREATE LOADOUT / nothing)
    if (pos < 0) return -1;
    if (pos < g_lo_n) return lo_slot_idx(pos);
    if (pos == g_lo_n) return -1;
    return pos - g_lo_n - 1 < N_CLASSES ? N_CUSTOM + pos - g_lo_n - 1 : -1;
}
static int gu_idx_pos(int idx) {
    if (lo_custom(idx)) return lo_slot(idx);
    return lo_cls(idx) >= 0 ? g_lo_n + 1 + lo_cls(idx) : 0;
}
static int gu_row_len(int row) { return row == 0 ? g_lo_n + 1 : N_CLASSES; }       // row 0: the customs + the CREATE LOADOUT tile
static int gu_pos_row(int pos) { return pos <= g_lo_n ? 0 : 1; }
static int gu_pos_col(int pos) { return pos <= g_lo_n ? pos : pos - g_lo_n - 1; }
static int gu_rc_pos(int row, int col) { return row == 0 ? col : g_lo_n + 1 + col; }
static int gu_wid_pos(int w) {                   // lsRow widget -> list position (-1: none)
    if (w < 0 || w >= GU_N_ROWW) return -1;
    if (w < GU_VISC) return G.coff + w <= g_lo_n ? G.coff + w : -1;
    return w - GU_VISC < N_CLASSES ? g_lo_n + 1 + w - GU_VISC : -1;
}
static void gu_scroll_to(int pos) {             // keep the focused custom row inside the window of GU_VISC (the classes always fit)
    if (pos >= 0 && gu_pos_row(pos) == 0) {
        if (pos < G.coff) G.coff = pos;
        if (pos >= G.coff + GU_VISC) G.coff = pos - GU_VISC + 1;
    }
    const int mx = gu_row_len(0) > GU_VISC ? gu_row_len(0) - GU_VISC : 0;
    if (G.coff > mx) G.coff = mx;
    if (G.coff < 0) G.coff = 0;
    G.cloff = 0;
}

// ------------------------------------------------------------------ data helpers (real tables, no mock text)
static void gu_read_cur(loadout_t *l) {         // the lobby object's loadout (what the edit view changes); the 4th skill = g_sk4_cur via sk4_slot
    memset(l->w, 0xff, sizeof l->w);
    memset(l->k, 0, sizeof l->k);
    lo_read_obj(l);
}
static int gu_ws(int s) { return s == GS_LARGE ? 0 : s == GS_SMALL ? 1 : 2; }          // slot -> lobby weapon slot (0 large, 1 small, 2 purchasable)
static const char *gu_head(int s) {
    static const char *const H[GU_SLOTS] = {"SMALL FIREARM", "LARGE FIREARM", "SURVIVAL SKILL 1", "SURVIVAL SKILL 2", "SURVIVAL SKILL 3", "SURVIVAL SKILL 4", "PURCHASABLE"};
    return H[s];
}
static const char *gu_none_name(int s) {
    static const char *const N[GU_SLOTS] = {"NO SMALL FIREARM", "NO LARGE FIREARM", "NOTHING", "NOTHING", "NOTHING", "NOTHING", "NO PURCHASABLE"};
    return N[s];
}
static const char *gu_str(const char *s) { return s && !IsBadReadPtr(s, 1) ? s : ""; }
static void gu_cost_str(char *b, size_t n, int lp) { if (lp > 0) snprintf(b, n, "%d LP", lp); else snprintf(b, n, "FREE"); }
static const uint8_t *gu_row(int ws, uint32_t idx) {   // a gun / purchasable table row (a blank row when out of range)
    if (ws == 2) { const uint32_t *cnt = (const uint32_t *)VMA(0x1800A0DA4); return idx < cnt[2] ? lo_purch_tab() + idx * 0x40 : weapon_row(0, ~0u); }
    return weapon_row(ws, idx);
}
static int gu_row_ok(int ws, uint32_t idx) { return idx < ((const uint32_t *)VMA(0x1800A0DA4))[ws] && !(ws == 0 && !g_large_tab); }
static int gu_row_cost(int ws, uint32_t idx) { return gu_row_ok(ws, idx) ? (int)*(const uint32_t *)(gu_row(ws, idx) + 0x18) : 0; }
static const sk_rec_t *gu_sk_rec(uint64_t v) { return (const sk_rec_t *)sk_lookup(v); }
static uint64_t gu_sk_val(const loadout_t *l, int k) { return sk_norm(k < 3 ? l->k[k] : *sk4_slot(l)); }   // skill row k (0..3) of a loadout
// What a slot of loadout l holds: name, icon, LP cost (0 + NULL name = empty)
static const char *gu_slot_item(int s, const loadout_t *l, const char **icon, int *cost) {
    *icon = GU_NONE_ICON; *cost = 0;
    if (s == GS_SK1 || s == GS_SK2 || s == GS_SK3 || s == GS_SK4) {
        const sk_rec_t *r = gu_sk_rec(gu_sk_val(l, s - GS_SK1));
        if (!r) return NULL;
        *icon = r->icon; *cost = (int)r->cost;
        return r->name;
    }
    int ws = gu_ws(s);
    const char *ic = NULL, *nm = lo_weapon_name(ws, l->w[ws], &ic);
    if (!nm) return NULL;
    *icon = ic ? ic : GU_EMPTY_ICON; *cost = gu_row_cost(ws, l->w[ws]);
    return nm;
}
// the loadout shown for list row r: the live lobby loadout for the custom loadout being edited (g_lo[] catches up twice a second), else the saved one
static const loadout_t *gu_list_lo(int r, loadout_t *tmp) {
    if (r == g_lo_active && lo_slot(r) >= 0 && g_lo_state != LO_MATCH && match_substate() != 6) { gu_read_cur(tmp); return tmp; }
    return lo_of(r);
}
static int gu_left_lp(const loadout_t *l) { return 13 - lo_cost(l); }
static void gu_lp_str(char *b, size_t n, int left) {      // "7 | 13": the points left | the total (No Return count style; no red any more)
    snprintf(b, n, "%d | %d", left < 0 ? 0 : left, GU_LP_TOTAL);
}

// ------------------------------------------------------------------ the options of a slot
static void gu_add(int kind, uint32_t row, uint32_t base, int supp, int sj) {
    if (g_gu_nopt >= GU_MAX_OPT) return;
    g_gu_opt[g_gu_nopt++] = (gu_opt_t){kind, row, base, supp, sj};
}
static void gu_build_opts(int s) {
    g_gu_nopt = 0;
    if (s != GS_SMALL) gu_add(GO_NONE, 0xffffffffu, 0, 0, -1);    // a secondary must be picked - no NO SMALL FIREARM row (lo_fix_small)
    if (s == GS_SMALL || s == GS_LARGE) {
        int ws = gu_ws(s);
        if (ws == 0 && (!g_large_tab || !g_picker_base[0])) return;
        // one row per gun; a gun with a suppressed variant keeps it in sj and the details panel's UNSUPPRESSED / SUPPRESSED toggle switches to it
        for (uint32_t i = 0; i < g_picker_base[ws] && i < 40; i++) gu_add(GO_GUN, i, i, 0, supp_row(ws, i));
    } else if (s == GS_PURCH) {
        const uint32_t n = ((const uint32_t *)VMA(0x1800A0DA4))[2];
        for (uint32_t i = 0; i < n && i < 40; i++) gu_add(GO_PURCH, i, i, 0, -1);
    } else {
        for (int id = 1; id < SK_COUNT; id++) gu_add(GO_SKILL, (uint32_t)id, 0, 0, -1);
    }
}
static void gu_lvl_reset(void) {                // each skill shows its equipped level, else its first level that does something
    for (int id = 1; id < SK_COUNT; id++) {
        g_gu_lvl[id] = 1;
        for (int k = 0; k < SK[id].nlv; k++) if (SK[id].avail >> k & 1) { g_gu_lvl[id] = k + 1; break; }
        int in = sk_in_slot(id);
        if (in >= 0) g_gu_lvl[id] = sk_lv(sk_norm(sk_slot_get(in)));
    }
}
static int gu_opt_eq(int s, const gu_opt_t *o, const loadout_t *cur) {   // is this option what the slot holds now?
    if (o->kind == GO_NONE) {
        if (s >= GS_SK1 && s <= GS_SK4) return !gu_sk_val(cur, s - GS_SK1);
        return cur->w[gu_ws(s)] == 0xffffffffu || !gu_row_ok(gu_ws(s), cur->w[gu_ws(s)]);
    }
    if (o->kind == GO_SKILL) return sk_in_slot((int)o->row) == s - GS_SK1 && sk_lv(gu_sk_val(cur, s - GS_SK1)) == g_gu_lvl[o->row];
    return cur->w[gu_ws(s)] == o->row || (o->sj >= 0 && cur->w[gu_ws(s)] == (uint32_t)o->sj);       // either variant counts as the gun
}
// the variant of a gun option the slot holds now: 1 = suppressed, 0 = plain, -1 = this gun is not equipped (neither toggle button is the active one)
static int gu_opt_var(int s, const gu_opt_t *o, const loadout_t *cur) {
    if (!o || o->kind != GO_GUN || o->sj < 0) return -1;
    uint32_t w = cur->w[gu_ws(s)];
    return w == (uint32_t)o->sj ? 1 : w == o->row ? 0 : -1;
}
static uint32_t gu_opt_row_now(int s, const gu_opt_t *o, const loadout_t *cur) { return gu_opt_var(s, o, cur) == 1 ? (uint32_t)o->sj : o->row; }
static int gu_eq_index(int s, const loadout_t *cur) {    // the equipped option (the NONE row when nothing is; a skill: the row of the equipped skill whatever its shown level)
    if (s >= GS_SK1 && s <= GS_SK4) {
        int id = sk_id(gu_sk_val(cur, s - GS_SK1));
        for (int i = 0; i < g_gu_nopt; i++) if (g_gu_opt[i].kind == GO_SKILL && (int)g_gu_opt[i].row == id) return i;
        return 0;
    }
    for (int i = 0; i < g_gu_nopt; i++) if (gu_opt_eq(s, &g_gu_opt[i], cur)) return i;
    return 0;
}
static void gu_focus_opt(int i) {                // option i is the focus: the window follows
    if (i < 0) i = 0;
    if (i >= g_gu_nopt) i = g_gu_nopt - 1;
    G.opt = i;
    if (G.opt < G.off) G.off = G.opt;
    else if (G.opt >= G.off + GU_OPT_ROWS) G.off = G.opt - GU_OPT_ROWS + 1;
    if (G.off > g_gu_nopt - GU_OPT_ROWS) G.off = g_gu_nopt > GU_OPT_ROWS ? g_gu_nopt - GU_OPT_ROWS : 0;
    if (G.off < 0) G.off = 0;
    G.dirty = 1;
}
static void gu_enter_slot(int s) {                // slot s is the focus: its options listed, the equipped one focused
    loadout_t cur;
    gu_read_cur(&cur);
    G.slot = s;
    if (s >= GS_SK1 && s <= GS_SK4) gu_lvl_reset();
    gu_build_opts(s);
    G.off = 0;
    gu_focus_opt(gu_eq_index(s, &cur));
}

// Name fit (names stuck out when they were too long): the name widgets (gearup13_widgets.tlm) pivot at
// their left middle, so w_scale shrinks a too-long name toward its left edge, centred in the row. Width estimate per character at
// point size pt: capitals / digits 0.80 pt (detail_title: 32.2 units at 40), lower case 0.62 pt, space 0.40 pt; floor 0.6.
static float gu_cw(const unsigned char *q) { return *q == ' ' ? 0.40f : (*q >= 'a' && *q <= 'z') || *q >= 0x80 ? 0.62f : 0.80f; }
static float gu_est(const char *t, float pt) {          // estimated width of t (translated, colour tags ignored) at point size pt
    const char *tr = loc_tr(t ? t : "");
    float est = 0.0f;
    int tag = 0;
    for (const unsigned char *q = (const unsigned char *)(tr ? tr : t ? t : ""); *q; q++) {
        if (*q == '<') tag = 1;
        if (tag) { if (*q == '>') tag = 0; continue; }
        if ((*q & 0xC0) == 0x80) continue;
        est += gu_cw(q);
    }
    return est * pt;
}
static struct { uint64_t w; float s; } g_gu_fit[192];     // per widget handle: the scale last written (cleared with the page: a rebuilt page can reuse a freed handle at scale 1)
#define c g_gu_fit
// w_scale with a per-handle cache (raw: re-applied on every fill, no cache hit: the option / slot names are re-asserted)
static void gu_set_scale(uint64_t w, float sc, int raw) {
    int k, fr = -1;
    for (k = 0; k < 192 && c[k].w != w; k++) if (fr < 0 && !c[k].w) fr = k;
    if (!raw && k < 192 && c[k].s == sc) return;    // already at this scale
    if (k == 192) { k = fr >= 0 ? fr : (int)(w >> 4) % 192; c[k].w = w; }
    c[k].s = sc;
    w_scale(w, sc, sc);
}
static int g_gu_grey;      // 1: the next gu_fit writes its text in the grey (an unfocused row / tile: white and grey are the page's two text colours)
static void gu_fit(const char *path, const char *t, float box, float pt) {
    if (!t) t = "";
    const char *tr = loc_tr(t);
    const char *src = tr ? tr : t;
    float est = 0.0f;
    int tag = 0;
    for (const unsigned char *q = (const unsigned char *)src; *q; q++) {
        if (*q == '<') tag = 1;
        if (tag) { if (*q == '>') tag = 0; continue; }
        if ((*q & 0xC0) == 0x80) continue;
        est += gu_cw(q);
    }
    est *= pt;
    // option / slot names are written past the dedup and their scale re-applied on every fill: a row's name widget (the 7th visible one, every tab)
    // stayed blank while the cache believed it already held its text / scale
    int raw = strstr(path, "opNm") || strstr(path, "slNm");
    float sc = est > box ? box / est : 1.0f;
    if (sc < 0.6f) sc = 0.6f;
    // even at the smallest scale too wide (a long name in a narrow row): cut it with "..." so it never reaches the cost or the frame.
    // Only plain names (the coloured tags are short and never this long). The full name stays in the details panel.
    char cut[96], wb[260];
    const char *fin = t;
    if (est * sc > box * 1.02f && !strchr(src, '<')) {
        float lim = box / (pt * 0.6f) - 3 * 0.80f, acc = 0.0f;   // width budget in "pt units" minus the three dots
        size_t n = 0;
        for (const unsigned char *q = (const unsigned char *)src; *q && n < sizeof cut - 4; q++) {
            if ((*q & 0xC0) != 0x80) { acc += gu_cw(q); if (acc > lim) break; }
            cut[n++] = (char)*q;
        }
        while (n > 0 && ((unsigned char)cut[n - 1] & 0xC0) == 0x80) n--;      // never half a UTF-8 sequence
        if (n > 0 && ((unsigned char)cut[n - 1] & 0x80) && ((unsigned char)cut[n - 1] & 0xC0) == 0xC0) n--;
        while (n > 0 && cut[n - 1] == ' ') n--;
        memcpy(cut + n, "...", 4);
        fin = cut;
    }
    if (g_gu_grey && fin[0] && !strchr(fin, '<')) { snprintf(wb, sizeof wb, "<font color=\"#8C8C8C\">%s</font>", fin); fin = wb; }
    if (raw) ui_text_raw(path, fin); else ui_text(path, fin);
    uint64_t w = ui_w(path);
    if (!w) return;
    gu_set_scale(w, sc, raw);
}
// fit with the grey (grey != 0) or the white text colour
static void gu_fitc(const char *path, const char *t, float box, float pt, int grey) { g_gu_grey = grey; gu_fit(path, t, box, pt); g_gu_grey = 0; }
#undef c

// ------------------------------------------------------------------ focus fades (the tick-driven page has none of the engine's focus motion)
// Focus frames / fills / arrows fade in and out with a short exponential ease instead of popping: the row that loses the focus fades out while the
// new one fades in (a crossfade, ~150 ms). Per widget handle; a write happens only when the quantised alpha changes (no flicker, no per-frame writes).
#define GU_FADERS 128
#define GU_FQ 24
// keyed by the widget PATH, not the handle (the 7th option row's name was blank in every tab, log "ui alpha 0: widget <opNm6>"
// from this tick every 6 s): widget handles are recycled when the engine rebuilds / re-pushes the page, so a fader that kept a handle from an
// earlier resolution kept writing its alpha 0 to whatever widget owns that handle now - the 7th row's name. The handle is re-resolved on every
// gu_fade call and an entry that no fill has touched for 200 frames is dropped without a write.
static struct { uint64_t ph, w, seen; float a, t, mx; int q; char path[72]; } g_gf[GU_FADERS];
// w_alpha SETS the widget's alpha (it replaces the colour alpha baked by the page builder), so a fade must top out at the baked value:
// fill 14 / frame 180 / arrow 220 of 255 (gearup13_widgets.py HILITE_A / FOCUS_A). Fading to 1.0 drew the highlight as a solid white bar.
static float gu_fade_max(const char *path) {
    size_t n = strlen(path);
    if (n >= 8 && strstr(path, "Fill")) return 14.0f / 255.0f;
    if (strstr(path, "Frame")) return 180.0f / 255.0f;
    if (strstr(path, "Arrow")) return 220.0f / 255.0f;
    return 1.0f;
}
static uint64_t g_gf_ms;
static void gu_fade(const char *path, int on) {
    uint64_t w = ui_w(path);
    if (!w) return;
    uint64_t ph = 1469598103934665603ULL;
    for (const char *c = path; *c; c++) ph = (ph ^ (uint8_t)*c) * 1099511628211ULL;
    int i, fr = -1;
    for (i = 0; i < GU_FADERS && g_gf[i].ph != ph; i++) if (fr < 0 && !g_gf[i].ph) fr = i;
    if (i == GU_FADERS) {
        if (fr < 0) { ui_visible(path, on); return; }            // (table full: the plain switch)
        i = fr; g_gf[i].ph = ph; g_gf[i].w = w; snprintf(g_gf[i].path, sizeof g_gf[i].path, "%s", path);
        { static int tr = -1; if (tr < 0) { FILE *f = exe_side_open("t2r-gu-trace.txt", "r"); tr = f != NULL; if (f) fclose(f); }
          if (tr) xlog("gearup13: gu trace: fader %d %s = %llx", i, path, (unsigned long long)w); } g_gf[i].a = 0.0f; g_gf[i].q = -1; g_gf[i].mx = gu_fade_max(path);
    }
    if (g_gf[i].w != w) {                                          // the path resolves to another widget now: start that one over
        static int nl; if (LOGCAP(nl, 20)) xlog("gearup13: fader %s moved from widget %llx to %llx", path, (unsigned long long)g_gf[i].w, (unsigned long long)w);
        g_gf[i].w = w; g_gf[i].q = -1;
    }
    g_gf[i].seen = g_frame;
    g_gf[i].t = on ? 1.0f : 0.0f;
}
static void gu_fade_reset(void) { memset(g_gf, 0, sizeof g_gf); g_gf_ms = 0; }
static void gu_fade_reassert(void) { for (int i = 0; i < GU_FADERS; i++) g_gf[i].q = -1; }
static void gu_fade_tick(uint64_t now) {
    float dt = g_gf_ms ? (float)(now - g_gf_ms) : 16.0f;
    g_gf_ms = now;
    if (dt > 50.0f) dt = 50.0f;
    float k = 1.0f - expf(-dt / 45.0f);
    for (int i = 0; i < GU_FADERS; i++) {
        if (!g_gf[i].w) continue;
        if (g_frame - g_gf[i].seen > 200) { memset(&g_gf[i], 0, sizeof g_gf[i]); continue; }   // no fill has asked for it lately: its handle may belong to another widget now
        float d = g_gf[i].t - g_gf[i].a;
        g_gf[i].a = fabsf(d) < 0.03f ? g_gf[i].t : g_gf[i].a + d * k;
        int q = (int)(g_gf[i].a * GU_FQ + 0.5f);
        if (q == g_gf[i].q) continue;
        g_gf[i].q = q;
        uint64_t cw = ui_w(g_gf[i].path);                          // a write is rare: resolve the path again, never trust a kept handle
        if (!cw) continue;
        g_gf[i].w = cw;
        w_visible(g_gf[i].w, q > 0);
        w_alpha(g_gf[i].w, (float)q / GU_FQ * g_gf[i].mx);
    }
}

// ------------------------------------------------------------------ animation (everything switched 0 -> 1 instantly)
// The engine's own menus animate with per-widget keyframe tracks (widget json "animation": keyframes + labels, e.g. animations/fade-default:
// labels off^active / active^off over 10 frames) that its menu scripts start; no DC native to start a label is known to this mod, so the page keeps
// its OWN small tweens, frame-time based (GetTickCount64), eased out, written through the same setters (w_alpha / w_pivot: both skip a repeat
// value). Nothing is written while nothing animates. t2r-gu-noanim.txt next to the exe = no tweens (the plain instant page).
static int gu_noanim(void) {
    static int on = -1; static uint64_t chk;
    uint64_t n = GetTickCount64();
    if (on < 0 || n - chk > 5000) { chk = n; FILE *f = exe_side_open("t2r-gu-noanim.txt", "r"); on = f != NULL; if (f) fclose(f); }
    return on;
}
static float gu_ease(float t) { if (t <= 0.0f) return 0.0f; if (t >= 1.0f) return 1.0f; float u = 1.0f - t; return 1.0f - u * u * u; }   // ease-out cubic
// a group's alpha + horizontal slide (the group's pivot is its own top left: 0 = in place)
static void gu_grp(const char *path, float a, float dx) {
    uint64_t w = ui_w(path);
    if (!w) return;
    w_alpha(w, a);
    w_pivot(w, dx, 0.0f);
}
// a leaf widget (text / image) inside a group: alpha only. Its pivotAs is its own layout position, NOT a 0-based offset like a group's, so a pivot write of
// (dx, 0) sent every previewed text and icon to the top left corner of the page.
static void gu_leaf(const char *path, float a) {
    uint64_t w = ui_w(path);
    if (w) w_alpha(w, a);
}
// text pops: a value that changed (LP numbers, EQUIPPED / state words, costs) fades in quickly instead of switching
#define GU_POPS 40
static struct { uint64_t w, h, t0; } g_gu_pop[GU_POPS];
static void gu_pop(const char *path, const char *text) {
    uint64_t w = ui_w(path);
    if (!w || !text) return;
    uint64_t h = 1469598103934665603ULL;
    for (const char *p = text; *p; p++) h = (h ^ (uint8_t)*p) * 1099511628211ULL;
    int i, fr = -1;
    for (i = 0; i < GU_POPS && g_gu_pop[i].w != w; i++) if (fr < 0 && !g_gu_pop[i].w) fr = i;
    if (i == GU_POPS) { if (fr < 0) return; g_gu_pop[fr].w = w; g_gu_pop[fr].h = h; g_gu_pop[fr].t0 = 0; return; }    // (first sight: no pop)
    if (g_gu_pop[i].h != h) { g_gu_pop[i].h = h; if (!gu_noanim()) g_gu_pop[i].t0 = GetTickCount64(); }
}
static void gu_anim_tick(uint64_t now) {
    if (gu_noanim()) { G.det_hold = 0; if (G.view == 0 && G.pv != G.pv_want) { G.pv = G.pv_want; G.dirty = 1; } return; }
    // ---- view change (list <-> edit): the incoming group fades in with a 14 unit slide, 170 ms
    if (G.view_anim) {
        float p = gu_ease((float)(now - G.view_t0) / 170.0f);
        gu_grp(G.view ? "anim-group.ed" : "anim-group.lst", p, (1.0f - p) * 14.0f);
        if (p >= 1.0f) G.view_anim = 0;
    }
    // ---- details panel: the old content fades out fast (80 ms, the refill of the details waits), the new fades in with a 8 unit slide (150 ms)
    if (G.view == 1) {
        int key = (G.slot + 1) * 1000 + (G.opt + 1);
        if (G.det_key == -1) G.det_key = key;
        else if (key != G.det_key && G.det_ph != 1) { G.det_key = key; G.det_ph = 1; G.det_t0 = now; G.det_hold = 1; }
        else if (key != G.det_key) G.det_key = key;                              // (changed again during the fade-out: the refill uses the latest)
        if (G.det_ph == 1) {
            float p = (float)(now - G.det_t0) / 80.0f;
            gu_grp("anim-group.ed.dt", 1.0f - gu_ease(p), 0.0f);
            if (p >= 1.0f) { G.det_ph = 2; G.det_t0 = now; G.det_hold = 0; G.dirty = 1; }
        } else if (G.det_ph == 2) {
            float p = gu_ease((float)(now - G.det_t0) / 150.0f);
            gu_grp("anim-group.ed.dt", p, (1.0f - p) * 8.0f);
            if (p >= 1.0f) G.det_ph = 0;
        }
    } else G.det_key = -1;
    // ---- list view: the right panel previews the hovered loadout (or the focused one), quick out 80 ms, in 150 ms with an 8 unit slide
    if (G.view == 0) {
        static const char *const PV[] = {"lgIc0","lgIc1","lgIc2","lgNm0","lgNm1","lgNm2","lskIc0","lskIc1","lskIc2","lskIc3","lskNm0","lskNm1","lskNm2","lskNm3","lsName","lsDesc","lsCur","lsLP","lsPerk"};
        float a = -1.0f;
        if (G.pv < 0) G.pv = G.pv_want;
        if (G.pv_ph == 0 && G.pv_want != G.pv && now - G.pv_chg >= 60) { G.pv_ph = 1; G.pv_t0 = now; }
        if (G.pv_ph == 1) {
            float p = (float)(now - G.pv_t0) / 80.0f;
            a = G.pv_a * (1.0f - gu_ease(p));
            if (p >= 1.0f) { G.pv = G.pv_want; G.pv_ph = 2; G.pv_t0 = now; G.dirty = 1; a = 0.0f; }
        } else if (G.pv_ph == 2) {
            float p = gu_ease((float)(now - G.pv_t0) / 150.0f);
            a = p;
            if (G.pv_want != G.pv && now - G.pv_chg >= 60) { G.pv_ph = 1; G.pv_t0 = now; G.pv_a = a; a = G.pv_a; }   // retarget from where the fade-in is
            else if (p >= 1.0f) { G.pv_ph = 0; a = 1.0f; }
        }
        if (a >= 0.0f) {
            if (G.pv_ph != 1) G.pv_a = a;
            char pp[160];
            for (unsigned i = 0; i < sizeof PV / sizeof PV[0]; i++) { snprintf(pp, sizeof pp, "anim-group.lst.%s", PV[i]); gu_leaf(pp, a); }
        }
    } else if (G.pv_ph) {                                    // left the list mid-tween: the panel is back to plain
        static const char *const PV2[] = {"lgIc0","lgIc1","lgIc2","lgNm0","lgNm1","lgNm2","lskIc0","lskIc1","lskIc2","lskIc3","lskNm0","lskNm1","lskNm2","lskNm3","lsName","lsDesc","lsCur","lsLP","lsPerk"};
        char pp[160];
        for (unsigned i = 0; i < sizeof PV2 / sizeof PV2[0]; i++) { snprintf(pp, sizeof pp, "anim-group.lst.%s", PV2[i]); gu_leaf(pp, 1.0f); }
        G.pv_ph = 0; G.pv = -1;
    }
    // ---- text pops
    for (int i = 0; i < GU_POPS; i++) {
        if (!g_gu_pop[i].w || !g_gu_pop[i].t0) continue;
        float p = (float)(now - g_gu_pop[i].t0) / 140.0f;
        if (p >= 1.0f) { w_alpha(g_gu_pop[i].w, 1.0f); g_gu_pop[i].t0 = 0; continue; }
        w_alpha(g_gu_pop[i].w, 0.2f + 0.8f * gu_ease(p));
    }
}
// Icon residency (icons updated with a noticeable delay): the engine streams a texture in when a widget first shows it, so the first
// selection of each item showed a blank / the old icon for a while. Every icon the page can show is put on a tiny always-visible widget of the
// page (pre0..pre95, a few per frame after the page opens) so the textures are requested while the page is still fading in.
#define GU_PRE_N 96
static void gu_preload_tick(void) {
    static const char *const AMMO[] = {"hud/weapons/ammo/ammo-arrow-explosive_small.png", "hud/weapons/ammo/ammo-arrow_small.png",
        "hud/weapons/ammo/ammo-firethrower_health-hud.png", "hud/weapons/ammo/ammo-shotgun_small.png", "hud/weapons/ammo/ammo-pistol-light.png",
        "hud/weapons/ammo/ammo-rifle-light.png"};
    if (G.pre_i < 0) return;
    // A client crashed in the engine 35 frames after the page opened (EXCEPTION c0000005 at exe+13ac870 on a non-tick thread, an icon path and an 80x80
    // size in the registers) right after this pool shipped: off until proven safe; t2r-gu-preload.txt next to the exe turns it on for tests
    static int on = -1;
    if (on < 0) { FILE *f = exe_side_open("t2r-gu-preload.txt", "r"); on = f != NULL; if (f) fclose(f); }
    if (!on) { G.pre_i = -1; return; }
    const uint32_t *cnt = (const uint32_t *)VMA(0x1800A0DA4);
    int a = (int)cnt[0], b = (int)cnt[1], c = (int)cnt[2], nsk = SK_COUNT - 1;
    for (int n = 0; n < 8 && G.pre_i >= 0; n++) {
        int i = G.pre_i++;
        const char *ic = NULL;
        if (i >= GU_PRE_N || i >= a + b + c + nsk + 6) { G.pre_i = -1; break; }
        if (i < a) { if (gu_row_ok(0, (uint32_t)i)) ic = *(const char **)(gu_row(0, (uint32_t)i) + 8); }
        else if (i < a + b) ic = *(const char **)(gu_row(1, (uint32_t)(i - a)) + 8);
        else if (i < a + b + c) ic = *(const char **)(gu_row(2, (uint32_t)(i - a - b)) + 8);
        else if (i < a + b + c + nsk) ic = SK[i - a - b - c + 1].icon;
        else ic = AMMO[i - a - b - c - nsk];
        if (ic && !IsBadReadPtr(ic, 1) && ic[0]) { char p[64]; snprintf(p, sizeof p, "anim-group.pre.pre%d", i); ui_image(p, ic); }
    }
}

// ------------------------------------------------------------------ shared pieces of the redesigned page (nrui.c frame, No Return look)
// the boxed prompts: what a click on each one does (gu13_scan_real reads it back through nr_prompt_hover)
enum { GPA_NONE, GPA_BACK, GPA_SEL, GPA_RST, GPA_REN };
static int g_gu_pact[NR_NPROMPT], g_gu_pon[NR_NPROMPT], g_gu_npa;
static void gu_prompts_put(const nr_prompt_t *it, const int *act, int n) {
    g_gu_npa = n > NR_NPROMPT ? NR_NPROMPT : n;
    for (int k = 0; k < g_gu_npa; k++) { g_gu_pact[k] = act[k]; g_gu_pon[k] = it[k].on; }
    nr_prompts(it, n);
}
// the prompts of the view in use (the device's own glyphs for the menu commands, plain key text in a white box for W / S, A / D and the like)
static void gu_prompts(void) {
    nr_prompt_t it[NR_NPROMPT];
    int act[NR_NPROMPT], n = 0;
#define GP(KB, PAD, LB, ON, A) do { it[n] = (nr_prompt_t){(KB), (PAD), (LB), (ON)}; act[n++] = (A); } while (0)
    if (GN.on) {                                   // the name box: DELETE (a letter), SAVE / CREATE, CANCEL
        GP("BKSP", "menu:action", "DELETE", 1, GPA_RST);
        GP("ENTER", "menu:select", GN.mode == 1 ? "CREATE" : "SAVE", 1, GPA_SEL);
        GP("ESC", "menu:back", "CANCEL", 1, GPA_BACK);
    } else if (G.view == 1) {
        const gu_opt_t *o = G.opt >= 0 && G.opt < g_gu_nopt ? &g_gu_opt[G.opt] : NULL;
        if (G.col == 0) GP("D", "RIGHT", "OPTIONS", 1, GPA_NONE);
        else if (o && o->kind == GO_SKILL && SK[o->row].nlv > 1) GP("A / D", "LEFT / RIGHT", "LEVEL", 1, GPA_NONE);
        else if (o && o->kind == GO_GUN && o->sj >= 0) GP("A / D", "LEFT / RIGHT", "SUPPRESSOR", 1, GPA_NONE);
        else GP("A", "LEFT", "SLOTS", 1, GPA_NONE);
        GP("W / S", "D-PAD", "MOVE", 1, GPA_NONE);
        GP("menu:next", "menu:next", "RENAME", 1, GPA_REN);
        GP("R", "menu:action", "RESET LOADOUT", 1, GPA_RST);
        GP("menu:select", "menu:select", G.col == 0 ? "CHOOSE" : "EQUIP", 1, GPA_SEL);
        GP("menu:back", "menu:back", "BACK", 1, GPA_BACK);
    } else {
        const int idx = gu_pos_idx(G.lst), cr = G.lst == g_lo_n;
        const int can_new = g_lo_n < N_CUSTOM_MAX && g_lo_state == LO_LIST, cust = idx >= 0 && lo_slot(idx) >= 0 && g_lo_state == LO_LIST;
        GP("W A S D", "D-PAD", "MOVE", 1, GPA_NONE);
        GP("menu:select", "menu:select", cr ? "CREATE" : cust ? "EDIT" : "EQUIP", cr ? can_new : 1, GPA_SEL);
        GP("menu:next", "menu:next", "RENAME", cust, GPA_REN);
        GP("menu:back", "menu:back", "BACK", 1, GPA_BACK);
    }
#undef GP
    gu_prompts_put(it, act, n);
}
// an EQUIPPED chip (nr_style.chip / nrui.c nr_chip: the accent box built at NR_CHIP_W0 with a left-middle pivot): sized to its (translated) text and put at x
// (right_edge: x is its right end), at the middle line the page template gave it
#define GU_CHIP_PT 30.0f
static void gu_chip(const char *base, const char *text, float x, int right_edge) {
    char p[160];
    snprintf(p, sizeof p, "%sBg", base); ui_visible(p, 1);
    snprintf(p, sizeof p, "%sTx", base); ui_visible(p, 1);
    nr_chip(base, text, right_edge ? 0.0f : x, right_edge ? x : 0.0f, GU_CHIP_PT);
}
static void gu_chip_off(const char *base) {
    char p[160];
    snprintf(p, sizeof p, "%sBg", base); ui_visible(p, 0);
    snprintf(p, sizeof p, "%sTx", base); ui_visible(p, 0);
}
// a multi-line text shrunk (about its top left: the box scales with it, so the wrap stays and only the line count decides) so it ends inside avail units
static void gu_desc_fit(const char *path, const char *t, float box_w, float pt, float avail) {
    if (!t) t = "";
    ui_text(path, t);
    uint64_t w = ui_w(path);
    if (!w) return;
    const char *tr = loc_tr(t), *q = tr ? tr : t;
    int lines = 0;
    for (;;) {
        const char *e = strchr(q, '\n');
        char tmp[400];
        size_t n = e ? (size_t)(e - q) : strlen(q);
        if (n >= sizeof tmp) n = sizeof tmp - 1;
        memcpy(tmp, q, n); tmp[n] = 0;
        lines += n ? (int)ceilf(gu_est(tmp, pt) * 1.12f / box_w) : 1;
        if (!e) break;
        q = e + 1;
    }
    float sc = lines > 0 && avail > 0.0f ? avail / ((float)lines * pt * 1.7f) : 1.0f;
    if (sc > 1.0f) sc = 1.0f;
    if (sc < 0.72f) sc = 0.72f;
    gu_set_scale(w, sc, 0);
}
static const char *gu_nofont(const char *s, char *o, size_t n) {         // s without its <...> tags (the gun limit's red "Too many of ..." line: white and grey only)
    size_t k = 0;
    int tag = 0;
    for (; *s && k + 1 < n; s++) {
        if (*s == '<') { tag = 1; continue; }
        if (tag) { if (*s == '>') tag = 0; continue; }
        o[k++] = *s;
    }
    o[k] = 0;
    return o;
}
static void gu_nb_fill(void) {                  // the name box's hint line (the keys are boxed prompts now)
    ui_text("anim-group.nb.nbHint", GN.pad ? "UP / DOWN  LETTER     LEFT / RIGHT  MOVE" : "TYPE A NAME");
}

// ------------------------------------------------------------------ list view
#define GU_LX1 1180.0f                           // the list column's right edge (gearup13_widgets.py LX1)
#define GU_LSB_X 1210.0f                         // the custom window's scroll bar: x, track top / bottom (LSB_X, ROW_Y[0], + 6 rows of 92 + 80)
#define GU_ROW_Y0 352.0f
#define GU_ROW_Y1 984.0f
#define GU_GNM_W 820.0f                          // a gear row's name box (GX1 - GX0 - GTX - 40)
static void gu_fill_list(void) {
    char p[160], b[240], nm[48];
    loadout_t tmp;
    gu_scroll_to(G.lst);
    const int can_new = g_lo_n < N_CUSTOM_MAX && g_lo_state == LO_LIST;
    for (int w = 0; w < GU_N_ROWW; w++) {
        const int pos = gu_wid_pos(w), i = gu_pos_idx(pos), is_new = pos >= 0 && pos == g_lo_n;
        snprintf(p, sizeof p, "anim-group.lst.lsRow%d", w);
        ui_visible(p, pos >= 0);
        if (pos < 0) continue;
        const int foc = pos == G.lst;
        int blocked = 0;
        char pn[160], pt_[160];
        snprintf(pn, sizeof pn, "anim-group.lst.lsRow%d.lsName%d", w, w);
        snprintf(pt_, sizeof pt_, "anim-group.lst.lsRow%d.lsTag%d", w, w);
        if (is_new) {                                  // the CREATE LOADOUT row: a plus and the count n | 12 (the old page's row)
            gu_fitc(pn, "+ CREATE LOADOUT", 640.0f, 33.0f, !foc);
            snprintf(b, sizeof b, "%d | %d", g_lo_n, N_CUSTOM_MAX);
            ui_text(pt_, b);
        } else if (i >= 0) {
            blocked = gl_row_blocked(i, NULL);
            gu_fitc(pn, lo_name(i, nm, sizeof nm), 640.0f, 33.0f, !foc);
            if (blocked) ui_text(pt_, "<font color=\"#F0F0F0\">TOO MANY</font>");
            else ui_text(pt_, i == g_lo_active ? "<font color=\"#D9D86A\">EQUIPPED</font>" : "");
        }
        snprintf(p, sizeof p, "anim-group.lst.lsRow%d.ls%dFill", w, w); gu_fade(p, pos == G.lst || pos == g_gu_hov_lst);
        snprintf(p, sizeof p, "anim-group.lst.lsRow%d.ls%dFo", w, w); gu_fade(p, foc);
        snprintf(p, sizeof p, "anim-group.lst.lsRow%d", w); w_alpha(ui_w(p), blocked || (is_new && !can_new) ? 0.35f : 1.0f);
    }
    nr_section("anim-group.lst.lsSecC", NR_L0, GU_LX1, 300.0f, "CUSTOM LOADOUTS", "", 36.0f);
    nr_section("anim-group.lst.lsSecL", NR_L0, GU_LX1, 1060.0f, "CLASSES", "", 36.0f);
    // the custom window's scroll bar (more than GU_VISC customs + CREATE LOADOUT): gearup13_widgets.py scroll_v lsSc, thumb built at 0.7 of the track
    nr_scroll_v("anim-group.lst.lsSc", GU_LSB_X, GU_ROW_Y0, GU_ROW_Y1, (GU_ROW_Y1 - GU_ROW_Y0) * 0.7f, G.coff, GU_VISC, gu_row_len(0));
    ui_visible("anim-group.nb", GN.on && GN.mode != 0);
    if (GN.on) gu_nb_fill();
    const int pvp = G.pv >= 0 && G.pv < gu_npos() ? G.pv : G.lst;     // the previewed list position (hover / focus, tweened in gu_anim_tick)
    const int pv = gu_pos_idx(pvp), pv_new = pv < 0;                 // (CREATE LOADOUT: an empty loadout, its own text)
    static const loadout_t nl = {{0xffffffffu, 0, 0xffffffffu}, {0, 0, 0}};   // what CREATE LOADOUT makes (gu_create): the 9mm only
    const loadout_t *l = pv_new ? &nl : gu_list_lo(pv, &tmp);
    // the 7 gear cells: small, large, purchasable (2013 order), then the four skills
    static const int GS3[3] = {GS_SMALL, GS_LARGE, GS_PURCH};
    for (int k = 0; k < 3; k++) {
        const char *ic; int cost;
        const char *n = gu_slot_item(GS3[k], l, &ic, &cost);             // (guns only: nl is no g_lo[] slot, its 4th skill would read the lobby's)
        snprintf(p, sizeof p, "anim-group.lst.lgIc%d", k); ui_image(p, n ? ic : GU_NONE_ICON);
        snprintf(p, sizeof p, "anim-group.lst.lgNm%d", k); gu_fit(p, n ? n : gu_none_name(GS3[k]), GU_GNM_W, 42.0f);
    }
    for (int k = 0; k < 4; k++) {
        const char *ic; int cost;
        const char *n = pv_new ? NULL : gu_slot_item(GS_SK1 + k, l, &ic, &cost);
        snprintf(p, sizeof p, "anim-group.lst.lskIc%d", k); ui_image(p, n ? ic : GU_EMPTY_ICON);
        snprintf(p, sizeof p, "anim-group.lst.lskNm%d", k); gu_fit(p, n ? n : "", GU_GNM_W, 39.0f);
    }
    gu_fit("anim-group.lst.lsName", pv_new ? "CREATE LOADOUT" : lo_name(pv, nm, sizeof nm), 1000.0f, 60.0f);
    int n = 0;
    if (pv_new) snprintf(b, sizeof b, "%s", g_lo_n >= N_CUSTOM_MAX ? "You have the most custom loadouts there can be."
                                             : g_lo_state != LO_LIST ? "New loadouts are made in GEAR UP from the menu."
                                             : "Make a new custom loadout. SELECT to name it, then choose its gear.");
    else {
        { char gp[120], gq[120]; n += snprintf(b + n, SNLEFT(b, n), "%s", gu_nofont(gl_detail_prefix(pv, gp, sizeof gp), gq, sizeof gq)); }
        snprintf(b + n, SNLEFT(b, n), "%s", lo_cls(pv) >= 0 ? CLASSES[lo_cls(pv)].desc : "Your own loadout. SELECT to change its gear.");
    }
    gu_desc_fit("anim-group.lst.lsDesc", b, 1000.0f, 36.0f, 560.0f);
    // the clan's supply perks (clanperk.c): "YOUR CLAN SENT: medkit x2 (Tyler), ..." under the equipped loadout's gear rows (its own line)
    gu_fit("anim-group.lst.lsPerk", pv == g_lo_active ? cp_gearup_line() : "", 1160.0f, 30.0f);
    ui_text("anim-group.lst.lsCur", pv == g_lo_active ? "THIS IS YOUR CURRENT LOADOUT" : "");     // (2013: under the gear of the equipped loadout)
    const int left = pv_new ? GU_LP_TOTAL - lo_cost(&nl) + sk4_cost(&nl) : gu_left_lp(l);
    gu_lp_str(b, sizeof b, left);
    ui_text("anim-group.lst.lsLP", b);        // (no text pop: the panel tween covers the change)
    nr_bar("anim-group.lst.lsLBF", 2700.0f, 3700.0f, 1243.0f, (float)(left < 0 ? 0 : left) / (float)GU_LP_TOTAL);
    gu_prompts();
}

// ------------------------------------------------------------------ edit view
static void gu_fill_slots(const loadout_t *cur) {      // the ladder: rectangle thumbnails joined by a line, label / name / N LP, a thin bar under each
    char p[160], b[48];
    for (int s = 0; s < GU_SLOTS; s++) {
        const char *ic; int cost;
        const char *n = gu_slot_item(s, cur, &ic, &cost);
        const int act = s == G.slot;
        snprintf(p, sizeof p, "anim-group.ed.sl%d.slTh%d.slIc%d", s, s, s); ui_image(p, n ? ic : GU_NONE_ICON); w_alpha(ui_w(p), act ? 1.0f : 0.6f);
        snprintf(p, sizeof p, "anim-group.ed.sl%d.slNm%d", s, s); gu_fitc(p, n ? n : gu_none_name(s), 480.0f, 45.0f, !act);
        snprintf(p, sizeof p, "anim-group.ed.sl%d.slCo%d", s, s);
        if (n && cost > 0) snprintf(b, sizeof b, "%d LP", cost); else snprintf(b, sizeof b, "FREE");
        gu_fitc(p, b, 190.0f, 39.0f, !act);
        snprintf(p, sizeof p, "anim-group.ed.sl%d.slB%dF", s, s); nr_bar(p, 304.0f, 972.0f, 160.0f, n && cost > 0 ? (float)cost / (float)GU_LP_TOTAL : 0.0f);
        snprintf(p, sizeof p, "anim-group.ed.sl%d.slTh%d.sl%dFill", s, s, s); gu_fade(p, act || s == g_gu_hov_slot);
        snprintf(p, sizeof p, "anim-group.ed.sl%d.slTh%d.sl%dFo", s, s, s); gu_fade(p, act);
        snprintf(p, sizeof p, "anim-group.ed.sl%d.slRuT%d", s, s); gu_fade(p, act);
        snprintf(p, sizeof p, "anim-group.ed.sl%d.slRuB%d", s, s); gu_fade(p, act);
    }
}
// one option row's texts: name, cost / state word, icon, equipped, dimmed
typedef struct { char nm[80], co[40]; const char *ic; int eq, dim; } gu_orow_t;
static void gu_opt_row(int s, const gu_opt_t *o, const loadout_t *cur, gu_orow_t *r) {
    memset(r, 0, sizeof *r);
    r->ic = GU_NONE_ICON;
    r->eq = gu_opt_eq(s, o, cur);
    if (o->kind == GO_NONE) {
        snprintf(r->nm, sizeof r->nm, "%s", gu_none_name(s));
        snprintf(r->co, sizeof r->co, "%s", r->eq ? "EQUIPPED" : "FREE");
        return;
    }
    int cost = 0;
    loadout_t t = *cur;
    if (o->kind == GO_SKILL) {
        int id = (int)o->row, lv = g_gu_lvl[id], sk = s - GS_SK1, in = sk_in_slot(id);
        cost = SK[id].cost[lv - 1];
        snprintf(r->nm, sizeof r->nm, "%s%s%s", SK[id].name, SK[id].nlv > 1 ? " " : "", SK[id].nlv > 1 ? SK_ROMAN[lv] : "");
        r->ic = SK[id].icon;
        if (!(SK[id].avail >> (lv - 1) & 1)) { snprintf(r->co, sizeof r->co, "LOCKED"); r->dim = 1; }
        else if (in >= 0 && in != sk) { snprintf(r->co, sizeof r->co, "IN SKILL %d", in + 1); r->dim = 1; }
        else if (r->eq) snprintf(r->co, sizeof r->co, "EQUIPPED");
        else { gu_cost_str(r->co, sizeof r->co, cost); r->dim = sk_cost_with(sk, SK_V(id, lv)) > 13; }
        return;
    }
    int ws = gu_ws(s);
    // one row per gun: the plain gun's name and icon whichever variant is equipped (the toggle / details show the variant)
    const uint8_t *row = gu_row(ws, o->kind == GO_GUN && o->sj >= 0 ? o->row : gu_opt_row_now(s, o, cur));
    snprintf(r->nm, sizeof r->nm, "%s", gu_str(*(const char **)row));
    r->ic = *(const char **)(row + 8) ? *(const char **)(row + 8) : GU_EMPTY_ICON;
    cost = (int)*(const uint32_t *)(row + 0x18);
    if (r->eq) snprintf(r->co, sizeof r->co, "EQUIPPED");
    else {
        gu_cost_str(r->co, sizeof r->co, cost);
        t.w[ws] = o->row;
        r->dim = lo_cost(&t) > 13;
    }
}
static void gu_dump_handles(void);
#define GU_OPT_NAME_X 236.0f         // gearup13_widgets.py OPT_NAME_X / OPT_CO_R: the option row's name left edge, cost right edge (relative to the row)
#define GU_OPT_CO_R 1184.0f
#define GU_OPT_H 144.0f
#define GU_SB_X 2528.0f              // the options' scroll bar (SB_X, SB_Y0, SB_Y1): the thumb is moved + scaled
#define GU_SB_Y0 392.0f
#define GU_SB_Y1 1784.0f
static void gu_fill_opts(const loadout_t *cur) {
    char p[160];
    nr_section("anim-group.ed.edHd", 1272.0f, 2500.0f, 300.0f, gu_head(G.slot), "", 45.0f);
    for (int k = 0; k < GU_OPT_ROWS; k++) {
        int i = G.off + k;
        snprintf(p, sizeof p, "anim-group.ed.op%d", k);
        ui_visible(p, i < g_gu_nopt);
        if (i >= g_gu_nopt) continue;
        gu_orow_t r;
        gu_opt_row(G.slot, &g_gu_opt[i], cur, &r);
        int foc = G.col == 1 && i == G.opt;
        char eqb[160];
        snprintf(eqb, sizeof eqb, "anim-group.ed.op%d.opEq%d", k, k);
        snprintf(p, sizeof p, "anim-group.ed.op%d.opNm%d", k, k);
        {   // the cost / state word is fitted first (right pivot: "ZABLOKOWANE" shrinks toward the row end), the name gets what is left of the row;
            // the equipped row has the EQUIPPED chip there instead (its width: the translated text at the chip's size)
            float cw = r.eq ? nr_est("EQUIPPED", GU_CHIP_PT) * 1.06f + 32.0f : gu_est(r.co, 36.0f);
            if (cw > 250.0f) cw = 250.0f * 1.0f;
            else if (cw < 70.0f) cw = 70.0f;
            gu_fitc(p, r.nm, GU_OPT_CO_R - GU_OPT_NAME_X - cw - 30.0f, 42.0f, !foc);
        }
        snprintf(p, sizeof p, "anim-group.ed.op%d.opCo%d", k, k); gu_fit(p, r.eq ? "" : r.co, 250.0f, 36.0f); gu_pop(p, r.co);
        snprintf(p, sizeof p, "anim-group.ed.op%d.opIc%d", k, k); ui_image(p, r.ic); w_alpha(ui_w(p), foc ? 1.0f : 0.55f);
        if (r.eq) gu_chip(eqb, "EQUIPPED", GU_OPT_CO_R, 1); else gu_chip_off(eqb);
        snprintf(p, sizeof p, "anim-group.ed.op%d.op%dFill", k, k); gu_fade(p, foc || i == g_gu_hov_opt);
        snprintf(p, sizeof p, "anim-group.ed.op%d.op%dFo", k, k); gu_fade(p, foc);
        snprintf(p, sizeof p, "anim-group.ed.op%d", k); w_alpha(ui_w(p), r.dim ? 0.45f : 1.0f);
    }
    {   // the scroll bar: shown only when there are more options than rows (hairline track + a white thumb, its height / top follow the window)
        const int sb = g_gu_nopt > GU_OPT_ROWS;
        ui_visible("anim-group.ed.opSbT", sb); ui_visible("anim-group.ed.opSbH", sb);
        if (sb) {
            uint64_t th = ui_w("anim-group.ed.opSbH");
            if (th) {
                w_scale(th, 1.0f, (float)GU_OPT_ROWS / (float)g_gu_nopt);
                w_pivot(th, GU_SB_X - 2.0f, GU_SB_Y0 + (GU_SB_Y1 - GU_SB_Y0) * (float)G.off / (float)g_gu_nopt);
            }
        }
    }
    gu_dump_handles();
}
// dev (t2r-gu-trace.txt next to the exe): the 7th visible option row's name stays blank in every tab. Logs every page widget handle once
// per page and flags two paths that resolve to the same widget (a write to one would overwrite the other).
static void gu_dump_handles(void) {
    static int done;
    if (done) return;
    FILE *f = exe_side_open("t2r-gu-trace.txt", "r");
    if (!f) return;
    fclose(f);
    done = 1;
    static const char *SUB[] = {"opNm", "opCo", "opIc", "opEq", "opHit"};
    char paths[96][80]; uint64_t hw[96]; int n = 0;
    for (int k = 0; k < GU_OPT_ROWS; k++) {
        snprintf(paths[n], 80, "anim-group.ed.op%d", k); hw[n] = ui_w(paths[n]); n++;
        for (int j = 0; j < 5; j++) { snprintf(paths[n], 80, "anim-group.ed.op%d.%s%d", k, SUB[j], k); hw[n] = ui_w(paths[n]); n++; }
    }
    static const char *DT[] = {"anim-group.ed.dt.dtIc", "anim-group.ed.dt.dtNm", "anim-group.ed.dt.dtCo", "anim-group.ed.dt.dtDesc", "anim-group.ed.dt.dtVar",
                               "anim-group.ed.edHdTx", "anim-group.ed.opSbH", "anim-group.ed.lpN"};
    for (int j = 0; j < 8 && n < 96; j++) { snprintf(paths[n], 80, "%s", DT[j]); hw[n] = ui_w(paths[n]); n++; }
    for (int i = 0; i < n; i++) {
        xlog("gearup13: gu trace: handle %s = %llx", paths[i], (unsigned long long)hw[i]);
        for (int j = 0; j < i; j++) if (hw[i] && hw[i] == hw[j]) xlog("gearup13: gu trace: SAME WIDGET %s == %s (%llx)", paths[i], paths[j], (unsigned long long)hw[i]);
    }
}
// the HUD ammo icon of a purchasable's ammo (the textures the in-game weapon cross / ammo counter use), by weapon id
static const char *gu_ammo_icon(const char *id) {
    if (!id) return "hud/weapons/ammo/ammo-rifle-light.png";
    if (strstr(id, "explosive")) return "hud/weapons/ammo/ammo-arrow-explosive_small.png";
    if (strstr(id, "bow")) return "hud/weapons/ammo/ammo-arrow_small.png";
    if (strstr(id, "flame")) return "hud/weapons/ammo/ammo-firethrower_health-hud.png";
    if (strstr(id, "shotgun")) return "hud/weapons/ammo/ammo-shotgun_small.png";
    if (strstr(id, "pistol") || strstr(id, "revolver")) return "hud/weapons/ammo/ammo-pistol-light.png";
    return "hud/weapons/ammo/ammo-rifle-light.png";
}
static void gu_fill_details(const loadout_t *cur) {
    char p[128], b[700];
    const gu_opt_t *o = G.opt >= 0 && G.opt < g_gu_nopt ? &g_gu_opt[G.opt] : NULL;
    int s = G.slot, show_st = 0, show_lv = 0, show_tg = 0, tgv = -1, show_pu = 0;
    unsigned pu_cost = 0, pu_acost = 0, pu_start = 0; const char *pu_ic = GU_NONE_ICON, *pu_am = NULL;
    char tg_co[2][24] = {"", ""};
    int v[4] = {0, 0, 0, 0};
    const char *nm = "", *ic = GU_NONE_ICON, *ds = "", *var = "";
    char cs[40] = "", vr[96] = "";
    if (!o || o->kind == GO_NONE) {
        nm = gu_none_name(s);
        snprintf(b, sizeof b, "%s", s == GS_PURCH ? "No purchasable: you keep your points for the other slots."
                                  : s >= GS_SK1 && s <= GS_SK4 ? "Nothing in this survival skill slot: the points stay for the rest of the loadout."
                                  : "Nothing in this slot: the points stay for the rest of the loadout.");
        ds = b; snprintf(cs, sizeof cs, "FREE");
    } else if (o->kind == GO_SKILL) {
        int id = (int)o->row, lv = g_gu_lvl[id];
        nm = SK[id].name; ic = SK[id].icon;
        snprintf(cs, sizeof cs, (SK[id].avail >> (lv - 1) & 1) ? "%s  %u LP" : "%s  LOCKED", SK_ROMAN[lv], SK[id].cost[lv - 1]);
        show_lv = 1;
    } else {
        int ws = gu_ws(s);
        const uint32_t er = gu_opt_row_now(s, o, cur);
        const uint8_t *row = gu_row(ws, er), *base = gu_row(ws, o->base);
        nm = gu_str(*(const char **)row);
        ic = *(const char **)(row + 8) ? *(const char **)(row + 8) : GU_EMPTY_ICON;
        gu_cost_str(cs, sizeof cs, (int)*(const uint32_t *)(row + 0x18));
        if (o->kind == GO_GUN) {
            const char *d0 = gu_str(*(const char **)(row + 0x28));
            if (o->sj >= 0 && er == (uint32_t)o->sj) snprintf(b, sizeof b, "%s%sHides shots from appearing on enemy radar.", d0, d0[0] ? "\n" : "");
            else snprintf(b, sizeof b, "%s", d0);
            ds = b;
            stat_values(gu_str(*(const char **)(base + 0x10)), v);
            show_st = 1;
            if (o->sj >= 0) {                      // the toggle under the description: UNSUPPRESSED / SUPPRESSED with their prices
                show_tg = 1;
                tgv = gu_opt_var(s, o, cur);
                gu_cost_str(tg_co[0], sizeof tg_co[0], gu_row_cost(ws, o->row));
                gu_cost_str(tg_co[1], sizeof tg_co[1], gu_row_cost(ws, (uint32_t)o->sj));
            }
        } else {                                   // purchasable: its blurb + what it costs in a match (the picker's text, feature_purch_details)
            const char *d0 = gu_str(*(const char **)(row + 0x30));
            uint32_t start = *(const uint32_t *)(row + 0x1c), wcost = *(const uint32_t *)(row + 0x20), acost = *(const uint32_t *)(row + 0x24), per = *(const uint32_t *)(row + 0x28);
            // the prices are a block of widgets (dtPu: item -> parts, ammo -> parts, Starts with: ammo n), the text keeps one sentence
            start = spawn_start_rounds(gu_str(*(const char **)(row + 0x10)), start);
            snprintf(b, sizeof b, "%s%sOnce bought it is yours again at every spawn.", d0, d0[0] ? "\n\n" : "");
            show_pu = 1; pu_cost = wcost; pu_acost = (acost && per) ? acost : 0; pu_start = pu_acost || start ? start : 0; pu_ic = ic;
            pu_am = gu_ammo_icon(gu_str(*(const char **)(row + 0x10)));
            ds = b;
        }
    }
    (void)cur;
    var = vr;
    const int deq = o && gu_opt_eq(s, o, cur);                  // the shown option is what the slot holds: the EQUIPPED chip next to the cost
    ui_image("anim-group.ed.dt.dtIc", ic);
    gu_fit("anim-group.ed.dt.dtNm", nm, 1040.0f, 63.0f);
    ui_text("anim-group.ed.dt.dtCo", cs);
    if (deq) gu_chip("anim-group.ed.dt.dtEq", "EQUIPPED", 2660.0f + nr_est(cs, 42.0f) * 1.06f + 28.0f, 0); else gu_chip_off("anim-group.ed.dt.dtEq");
    // the text must end above the next block (toggle 1080 / stats 1330 / the price block): shrunk to fit when long
    gu_desc_fit("anim-group.ed.dt.dtDesc", show_lv ? "" : ds, 1040.0f, 39.0f, show_tg ? 200.0f : show_pu ? 420.0f : show_st ? 420.0f : 900.0f);
    ui_text("anim-group.ed.dt.dtVar", var);
    ui_visible("anim-group.ed.dt.dtSt", show_st);
    ui_visible("anim-group.ed.dt.dtTg", show_tg);
    ui_visible("anim-group.ed.dt.dtPu", show_pu);
    if (show_pu) {
        char nb[24];
        ui_image("anim-group.ed.dt.dtPu.puRow0.puIc0", pu_ic);
        snprintf(nb, sizeof nb, "%u", pu_cost); ui_text("anim-group.ed.dt.dtPu.puRow0.puN0", nb);
        ui_visible("anim-group.ed.dt.dtPu.puRow0", pu_cost != 0);
        ui_visible("anim-group.ed.dt.dtPu.puRow1", pu_acost != 0);
        if (pu_acost) { ui_image("anim-group.ed.dt.dtPu.puRow1.puIc1", pu_am); snprintf(nb, sizeof nb, "%u", pu_acost); ui_text("anim-group.ed.dt.dtPu.puRow1.puN1", nb); }
        ui_visible("anim-group.ed.dt.dtPu.puStLb", pu_start != 0); ui_visible("anim-group.ed.dt.dtPu.puStIc", pu_start != 0); ui_visible("anim-group.ed.dt.dtPu.puStN", pu_start != 0);
        if (pu_start) { ui_text("anim-group.ed.dt.dtPu.puStLb", "Starts with:"); ui_image("anim-group.ed.dt.dtPu.puStIc", pu_am); snprintf(nb, sizeof nb, "%u", pu_start); ui_text("anim-group.ed.dt.dtPu.puStN", nb); }
    }
    for (int k = 0; k < 2; k++) {                 // the suppressor toggle: the chosen box framed + white, the other grey
        snprintf(p, sizeof p, "anim-group.ed.dt.dtTg.tgB%d.tgNm%d", k, k); gu_fitc(p, k ? "SUPPRESSED" : "UNSUPPRESSED", 440.0f, 30.0f, !(show_tg && tgv == k));
        snprintf(p, sizeof p, "anim-group.ed.dt.dtTg.tgB%d.tgCo%d", k, k); ui_text(p, tg_co[k]);
        snprintf(p, sizeof p, "anim-group.ed.dt.dtTg.tgB%d.tg%dFo", k, k); gu_fade(p, show_tg && tgv == k);
        snprintf(p, sizeof p, "anim-group.ed.dt.dtTg.tgB%d.tg%dFill", k, k); gu_fade(p, show_tg && (tgv == k || g_gu_hov_tg == k));
    }
    ui_visible("anim-group.ed.dt.dtLv", show_lv);
    if (show_st)                                  // 4 thin bars with their N | 10 counts
        for (int st = 0; st < 4; st++) {
            char nb[24];
            snprintf(nb, sizeof nb, "%d | 10", v[st]);
            snprintf(p, sizeof p, "anim-group.ed.dt.dtSt.stN%d", st); ui_text(p, nb);
            snprintf(p, sizeof p, "anim-group.ed.dt.dtSt.st%dF", st); nr_bar(p, 2660.0f, 3700.0f, 1352.0f + 128.0f * (float)st + 39.0f, (float)v[st] / 10.0f);
        }
    if (show_lv) {
        int id = (int)o->row, sk = s - GS_SK1, lv = g_gu_lvl[id], in = sk_in_slot(id);
        uint64_t curv = gu_sk_val(cur, sk);
        for (int k = 0; k < 3; k++) {
            int on = k < SK[id].nlv;
            char hd[96];
            if (!on) hd[0] = 0;
            else if (!(SK[id].avail >> k & 1)) snprintf(hd, sizeof hd, "%s  -  LOCKED", SK_ROMAN[k + 1]);
            else if (in == sk && sk_lv(curv) == k + 1) snprintf(hd, sizeof hd, "%s  -  %u LP  -  EQUIPPED", SK_ROMAN[k + 1], SK[id].cost[k]);
            else snprintf(hd, sizeof hd, "%s  -  %u LP", SK_ROMAN[k + 1], SK[id].cost[k]);
            snprintf(p, sizeof p, "anim-group.ed.dt.dtLv.lvHd%d", k); ui_text(p, hd);
            snprintf(p, sizeof p, "anim-group.ed.dt.dtLv.lvTx%d", k); ui_text(p, on ? gu_str(SK[id].desc[k]) : "");
            float a = (k + 1 == lv || k == g_gu_hov_lvl) ? 1.0f : 0.45f;
            snprintf(p, sizeof p, "anim-group.ed.dt.dtLv.lvHd%d", k); w_alpha(ui_w(p), on ? a : 0.0f);
            snprintf(p, sizeof p, "anim-group.ed.dt.dtLv.lvTx%d", k); w_alpha(ui_w(p), on ? a : 0.0f);
        }
    }
}
static void gu_fill_edit(void) {
    loadout_t cur;
    char b[96];
    gu_read_cur(&cur);
    gu_fill_slots(&cur);
    gu_fill_opts(&cur);
    if (!G.det_hold) gu_fill_details(&cur);
    const int left = gu_left_lp(&cur);
    gu_lp_str(b, sizeof b, left);
    ui_text("anim-group.ed.lpN", b); gu_pop("anim-group.ed.lpN", b);
    nr_bar("anim-group.ed.lpBF", 2660.0f, 3700.0f, 355.0f, (float)(left < 0 ? 0 : left) / (float)GU_LP_TOTAL);     // the LP bar (13 segments: its ticks are static)
    ui_visible("anim-group.nb", GN.on);          // RENAME: the NAME YOUR LOADOUT box (as CREATE LOADOUT's)
    if (GN.on) gu_nb_fill();
    gu_prompts();
}

// ------------------------------------------------------------------ equipping (real data: the lobby object, sk_slot_set, the saved loadout)
static void gu_commit(void) {                    // an edit is done: the custom loadout is saved NOW (feature_loadout_persist only looks twice a second - a class picked
    loadout_t cur;                               // right after would overwrite the lobby object first)
    gu_read_cur(&cur);
    uint8_t *ob = lobby_obj();
    if (ob) *(uint64_t *)(ob + 0x2c70) = cur.k[0] | cur.k[1] | cur.k[2];
    lj_user_edit();
    if (lo_slot(g_lo_active) >= 0 && lo_valid(&cur)) { g_lo[lo_slot(g_lo_active)] = cur; lo_save(); xlog("gearup13: custom %d saved (%d LP)", lo_slot(g_lo_active) + 1, lo_cost(&cur)); }
    G.dirty = 1;
}
static void gu_sfx(const char *name) { ui_sfx(name); }
static void gu_equip(int s, const gu_opt_t *o) {
    loadout_t cur;
    uint8_t *ob = lobby_obj();
    gu_read_cur(&cur);
    if (!ob) return;
    if (o->kind == GO_SKILL) {
        int sk = s - GS_SK1, id = (int)o->row, lv = g_gu_lvl[id];
        uint64_t v = SK_V(id, lv), now = sk_norm(sk_slot_get(sk));
        int other = sk_in_slot(id);
        char dm[160];
        if (!(SK[id].avail >> (lv - 1) & 1)) { snprintf(dm, sizeof dm, "%s %s is not available yet.", SK[id].name, SK_ROMAN[lv]); ui_deny(dm); xlog("gearup13: skill %d %s %s refused (locked)", sk + 1, SK[id].name, SK_ROMAN[lv]); return; }
        if (other >= 0 && other != sk) { snprintf(dm, sizeof dm, "%s is already in Survival Skill %d.", SK[id].name, other + 1); ui_deny(dm); xlog("gearup13: skill %d %s refused (in skill %d)", sk + 1, SK[id].name, other + 1); return; }
        if (now == v) { gu_sfx("sfx-select"); xlog("gearup13: select ignored: skill %d already holds %s %s", sk + 1, SK[id].name, SK_ROMAN[lv]); return; }
        if (sk_cost_with(sk, v) > 13) { ui_deny_lp(SK[id].name, (int)SK[id].cost[lv - 1], 13 - sk_cost_with(sk, 0)); xlog("gearup13: skill %d %s %s refused (points)", sk + 1, SK[id].name, SK_ROMAN[lv]); return; }
        sk_slot_set(sk, v);
        sk_sound(1);
        xlog("gearup13: skill %d = %s %s", sk + 1, SK[id].name, SK_ROMAN[lv]);
    } else if (o->kind == GO_NONE && s >= GS_SK1 && s <= GS_SK4) {
        int sk = s - GS_SK1;
        if (!sk_norm(sk_slot_get(sk))) { gu_sfx("sfx-select"); xlog("gearup13: select ignored: skill %d is already empty", sk + 1); return; }
        sk_slot_set(sk, 0);
        gu_sfx("sfx-select");
        xlog("gearup13: skill %d emptied", sk + 1);
    } else {
        int ws = gu_ws(s);
        uint32_t want = o->kind == GO_NONE ? 0xffffffffu : o->row;
        if (cur.w[ws] == want || (o->kind == GO_NONE && !gu_row_ok(ws, cur.w[ws]))) { gu_sfx("sfx-select"); xlog("gearup13: select ignored: slot %d already holds row %u", ws, want); return; }     // already what the slot holds
        loadout_t t = cur;
        t.w[ws] = want;
        if (lo_cost(&t) > 13) {
            t.w[ws] = 0xffffffffu;
            const uint8_t *row = gu_row(ws, want);
            ui_deny_lp(gu_str(*(const char **)row), (int)*(const uint32_t *)(row + 0x18), 13 - lo_cost(&t));
            xlog("gearup13: slot %d row %u refused (points: %d LP)", ws, want, lo_cost(&cur));
            return;
        }
        *(uint32_t *)(ob + 0x2c58 + 4 * ws) = want;
        gu_sfx("sfx-select");
        xlog("gearup13: %s = row %d (%s)", ws == 0 ? "large" : ws == 1 ? "small" : "purchasable", (int)want, want == 0xffffffffu ? "none" : gu_str(*(const char **)gu_row(ws, want)));
    }
    gu_commit();
}

// the suppressed / plain variant of the focused gun: equipped like a click on an option (same lobby write + save), the options list stays
static void gu_set_variant(int s, const gu_opt_t *o, int v) {
    gu_opt_t t = *o;
    if (v && o->sj >= 0) t.row = (uint32_t)o->sj;
    gu_equip(s, &t);
}
// RESET LOADOUT (2013 edit page, square): the custom loadout back to its empty default (9mm only, no skills) - the same lobby-object write + commit
// path a click on an option uses. There is no engine action known for it: the prompt listens to menu-action, the R key and a click on the prompt.
static void gu_reset(void) {
    loadout_t d;
    memset(&d, 0, sizeof d);
    d.w[0] = 0xffffffffu; d.w[1] = 0; d.w[2] = 0xffffffffu;
    loadout_t cur;
    gu_read_cur(&cur);
    if (cur.w[0] == d.w[0] && cur.w[1] == d.w[1] && cur.w[2] == d.w[2] && !(cur.k[0] | cur.k[1] | cur.k[2]) && !sk_norm(sk_slot_get(3))) { gu_sfx("sfx-select"); return; }
    lo_write_obj(&d);
    sk_slot_set(3, 0);
    gu_sfx("sfx-select");
    xlog("gearup13: custom %d reset to the empty loadout", g_lo_active + 1);
    gu_commit();
    gu_enter_slot(G.slot);                         // the options of the focused slot again, the equipped one focused
}

// ------------------------------------------------------------------ list actions
static void gu_to_edit(void) {
    G.view = 1; G.col = 0; G.closing = 0; G.view_anim = !gu_noanim(); G.view_t0 = GetTickCount64(); G.det_key = -1; G.det_ph = 0; G.det_hold = 0;
    gu_enter_slot(GS_LARGE);
    G.dirty = 1;
    ui_visible("anim-group.lst", 0);
    ui_visible("anim-group.ed", 1);
    xlog("gearup13: edit view (custom %d)", lo_slot(g_lo_active) + 1);
}
static void gu_to_list(const char *why) {
    G.view_anim = !gu_noanim(); G.view_t0 = GetTickCount64();
    G.view = 0; G.col = 0; G.lst = gu_idx_pos(g_lo_active); gu_scroll_to(G.lst); G.wcol = gu_pos_col(G.lst);
    G.dirty = 1;
    ui_visible("anim-group.lst", 1);
    ui_visible("anim-group.ed", 0);
    xlog("gearup13: list view (%s)", why);
}
static void gu_list_select(int r, int edit) {      // edit 0: only choose the loadout (mouse first click), 1: choose + open the editor
    char b[48];
    if (!lo_custom(r) && lo_cls(r) < 0) return;
    if (gl_pick_refused(r)) return;                  // gunlimit.c: a gun limited per team that a teammate has taken - denied buzzer + message, nothing equipped
    const loadout_t *l = lo_of(r);
    if (g_lo_state != LO_MATCH && lo_cls(r) >= 0 && !lo_valid(l)) {
        ui_deny("That loadout can't be equipped right now.");
        xlog("gearup13: %s refused by lo_valid (%d LP)", lo_name(r, b, sizeof b), lo_cost(l));
        return;
    }
    g_lo_active = r;
    // mid-match: winmm's store / our box ammo read the lobby object, so the pick waits for the next spawn (lo_snap_tick keeps this life's loadout)
    if (g_lo_state == LO_MATCH) g_lo_pending = r + 1;
    else if (lo_valid(l)) lo_write_obj(l);
    else lo_write_obj_forced(l);                     // (a custom loadout with an unresolved row: edit it anyway)
    lo_save();
    gu_sfx("sfx-select");
    xlog("gearup13: %s selected (state %d, %d LP)", lo_name(r, b, sizeof b), g_lo_state, lo_cost(l));
    if (g_lo_state == LO_MATCH) {                   // applies at the next respawn (2013)
        pop_page();                                 // the list
        pop_page();                                 // the pause menu under it: back to the game
        g_lo_state = LO_NONE;
        G.closing = 1;
        char m[96];
        snprintf(m, sizeof m, "%s equipped - you'll spawn with it next life", lo_name(r, b, sizeof b));
        msg_hook(m, 3.0f, 0, 0);
        return;
    }
    if (edit && lo_slot(r) >= 0 && g_lo_state == LO_LIST) gu_to_edit();
    else G.dirty = 1;
}
static void gn_create_begin(void);
// a list position chosen (SELECT / click): CREATE LOADOUT opens the name box, anything else is gu_list_select
static void gu_pos_select(int pos, int edit) {
    if (pos != g_lo_n) { gu_list_select(gu_pos_idx(pos), edit); return; }
    if (g_lo_n >= N_CUSTOM_MAX) { ui_deny("You have the most custom loadouts there can be."); xlog("gearup13: CREATE LOADOUT refused (%d custom loadouts)", g_lo_n); return; }
    if (g_lo_state != LO_LIST) { ui_deny("New loadouts are made in GEAR UP from the menu."); xlog("gearup13: CREATE LOADOUT refused (state %d)", g_lo_state); return; }
    gn_create_begin();
}
// CREATE LOADOUT confirmed in the name box: a new custom slot (9mm only, no skills), named, equipped, and its editor opened
static void gu_create(const char *nm) {
    if (g_lo_n >= N_CUSTOM_MAX) return;
    const int k = g_lo_n;
    g_lo[k] = (loadout_t){{0xffffffffu, 0, 0xffffffffu}, {0, 0, 0}};
    *sk4_slot(&g_lo[k]) = 0;
    g_lo_n++;
    lo_nm_set(k, "", "create (clean slot)");
    lo_nm_set(k, nm, "gear up create");
    lo_save();
    sk4_save();
    lj_user_edit();                                  // (t2r-loadout.json gets the new loadout on the next lj_tick: the launcher adopts it)
    xlog("gearup13: custom %d created (%d custom loadouts)", k + 1, g_lo_n);
    gu_list_select(lo_slot_idx(k), 1);
    G.lst = gu_idx_pos(g_lo_active); gu_scroll_to(G.lst);
}

// ------------------------------------------------------------------ mouse (from the click gate, once a frame)
static int gu13_scan_real(void);
// perf: the scan armed + hit-tested ~30 widgets by path string EVERY frame (2 engine script calls + 3 name lookups each). The answer only changes when the
// cursor moves, a button is down, or the layout / focus changes, so it is reused (and the cursor outside the window = nothing hovered, no widget touched);
// a full re-scan at least every 15 frames (arms new rows too).
static int gu13_scan(void) {
    static float lcx = -1.0f, lcy = -1.0f; static int lkey = -1, lhit; static uint64_t lfr;
    static struct { int lst, slot, opt, lvl, back, sel, rst, tg, ren; } sv;
    float cx, cy;
    if (!ui_cursor_canvas(&cx, &cy)) {
        g_gu_hov_lst = g_gu_hov_slot = g_gu_hov_opt = g_gu_hov_lvl = g_gu_hov_tg = -1; g_gu_hov_back = g_gu_hov_sel = g_gu_hov_rst = g_gu_hov_ren = 0;
        lkey = -1;
        return 0;
    }
    int key = G.view | G.off << 1 | G.opt << 9 | g_gu_nopt << 17 | G.slot << 25 | G.coff << 28;
    if (cx == lcx && cy == lcy && key == lkey && !G.dirty && g_frame - lfr < 15 && !(GetAsyncKeyState(VK_LBUTTON) & 0x8000)) {
        g_gu_hov_lst = sv.lst; g_gu_hov_slot = sv.slot; g_gu_hov_opt = sv.opt; g_gu_hov_lvl = sv.lvl; g_gu_hov_back = sv.back; g_gu_hov_sel = sv.sel; g_gu_hov_rst = sv.rst; g_gu_hov_tg = sv.tg; g_gu_hov_ren = sv.ren;
        return lhit;
    }
    lhit = gu13_scan_real(); lcx = cx; lcy = cy; lkey = key; lfr = g_frame;
    sv.lst = g_gu_hov_lst; sv.slot = g_gu_hov_slot; sv.opt = g_gu_hov_opt; sv.lvl = g_gu_hov_lvl; sv.back = g_gu_hov_back; sv.sel = g_gu_hov_sel; sv.rst = g_gu_hov_rst; sv.tg = g_gu_hov_tg; sv.ren = g_gu_hov_ren;
    return lhit;
}
// The nearest clickable rect to the cursor (canvas units, distance 0 = inside). kind: 0 list row / 1 slot / 2 option (idx = row index in the full list) /
// 3 level line / 4 toggle button. Rows are laid out with gaps (option rows 18 units, slots 15) and a click that lands in one hit NOTHING: a live log
// had "click ignored: nothing under the cursor" while the lists were being clicked. A click within GU_SNAP of a rect now counts as on it.
#define GU_SNAP 36.0f
static float gu_nearest(float cx, float cy, int *kind, int *idx, char *nm, size_t nmn, float *rc) {
    float best = 1e9f;
    char p[96];       // (the widget paths are < 60 chars; 96 = the caller's nm buffer, so the copy below cannot truncate)
    *kind = -1; *idx = -1;
    if (nm) nm[0] = 0;
#define GU_CAND(K, I, ...) do { snprintf(p, sizeof p, __VA_ARGS__); uint64_t w_ = ui_w(p); float x0, y0, x1, y1;         if (w_ && ui_rect_ss(w_, &x0, &y0, &x1, &y1) && x1 > x0 && y1 > y0) {             float dx = cx < x0 ? x0 - cx : cx > x1 ? cx - x1 : 0.0f, dy = cy < y0 ? y0 - cy : cy > y1 ? cy - y1 : 0.0f, d = sqrtf(dx * dx + dy * dy);             if (d < best) { best = d; *kind = (K); *idx = (I); if (nm) snprintf(nm, nmn, "%s", p); if (rc) { rc[0] = x0; rc[1] = y0; rc[2] = x1; rc[3] = y1; } } } } while (0)
    if (G.view == 0) {
        for (int w = 0; w < GU_N_ROWW; w++) if (gu_wid_pos(w) >= 0) GU_CAND(0, gu_wid_pos(w), "anim-group.lst.lsRow%d.lsHit%d", w, w);
    } else {
        for (int s_ = 0; s_ < GU_SLOTS; s_++) GU_CAND(1, s_, "anim-group.ed.sl%d.slHit%d", s_, s_);
        for (int k = 0; k < GU_OPT_ROWS && G.off + k < g_gu_nopt; k++) GU_CAND(2, G.off + k, "anim-group.ed.op%d.opHit%d", k, k);
        const gu_opt_t *o = G.opt >= 0 && G.opt < g_gu_nopt ? &g_gu_opt[G.opt] : NULL;
        if (o && o->kind == GO_SKILL) for (int k = 0; k < SK[o->row].nlv && k < 3; k++) GU_CAND(3, k, "anim-group.ed.dt.dtLv.lvHit%d", k);
        if (o && o->kind == GO_GUN && o->sj >= 0) for (int k = 0; k < 2; k++) GU_CAND(4, k, "anim-group.ed.dt.dtTg.tgB%d.tgHit%d", k, k);
    }
#undef GU_CAND
    return best;
}
static int gu13_scan_real(void) {
    char p[128];
    int hit = 0;
    g_gu_hov_lst = g_gu_hov_slot = g_gu_hov_opt = g_gu_hov_lvl = -1;
    {   // the boxed prompts (nrui.c: laid out by gu_prompts): the one under the cursor. SELECT acts even while it is dimmed (CREATE LOADOUT says why it can't); the others only when available
        const int ph = nr_prompt_hover(), pa = ph >= 0 && ph < g_gu_npa && (g_gu_pon[ph] || g_gu_pact[ph] == GPA_SEL) ? g_gu_pact[ph] : GPA_NONE;
        g_gu_hov_back = pa == GPA_BACK; g_gu_hov_sel = pa == GPA_SEL; g_gu_hov_rst = pa == GPA_RST; g_gu_hov_ren = pa == GPA_REN;
    }
    g_gu_hov_tg = -1;
    if (G.view == 0) {
        for (int w = 0; w < GU_N_ROWW; w++) {
            if (gu_wid_pos(w) < 0) continue;
            snprintf(p, sizeof p, "anim-group.lst.lsRow%d.lsHit%d", w, w);
            if (ui_mouse_over(p, 1)) { g_gu_hov_lst = gu_wid_pos(w); break; }
        }
        hit = g_gu_hov_lst >= 0;
    } else {
        for (int s = 0; s < GU_SLOTS; s++) { snprintf(p, sizeof p, "anim-group.ed.sl%d.slHit%d", s, s); if (ui_mouse_over(p, 1)) { g_gu_hov_slot = s; break; } }
        for (int k = 0; k < GU_OPT_ROWS && G.off + k < g_gu_nopt; k++) { snprintf(p, sizeof p, "anim-group.ed.op%d.opHit%d", k, k); if (ui_mouse_over(p, 1)) { g_gu_hov_opt = G.off + k; break; } }
        const gu_opt_t *o = G.opt >= 0 && G.opt < g_gu_nopt ? &g_gu_opt[G.opt] : NULL;
        if (o && o->kind == GO_SKILL)
            for (int k = 0; k < SK[o->row].nlv && k < 3; k++) { snprintf(p, sizeof p, "anim-group.ed.dt.dtLv.lvHit%d", k); if (ui_mouse_over(p, 1)) { g_gu_hov_lvl = k; break; } }
        if (o && o->kind == GO_GUN && o->sj >= 0)
            for (int k = 0; k < 2; k++) { snprintf(p, sizeof p, "anim-group.ed.dt.dtTg.tgB%d.tgHit%d", k, k); if (ui_mouse_over(p, 1)) { g_gu_hov_tg = k; break; } }
        hit = g_gu_hov_slot >= 0 || g_gu_hov_opt >= 0 || g_gu_hov_lvl >= 0 || g_gu_hov_tg >= 0;
    }
    if (g_gu_hov_sel || g_gu_hov_rst || g_gu_hov_ren) hit = 1;
    if (!hit && !g_gu_hov_back) {                    // between rows: snap to the nearest rect within GU_SNAP
        float cx, cy, rc[4]; int kd, ix;
        if (ui_cursor_canvas(&cx, &cy) && gu_nearest(cx, cy, &kd, &ix, NULL, 0, rc) <= GU_SNAP && kd >= 0) {
            if (kd == 0) g_gu_hov_lst = ix; else if (kd == 1) g_gu_hov_slot = ix; else if (kd == 2) g_gu_hov_opt = ix; else if (kd == 3) g_gu_hov_lvl = ix; else g_gu_hov_tg = ix;
            hit = 1;
        }
    }
    return hit;
}

// ------------------------------------------------------------------ the driver
#define GU_REP_FIRST_MS 260      // navigation felt choppy and scrolling laggy: was 400 / 110 ms; NR's own lists repeat about this fast
#define GU_REP_MS 75
static int gu_rep(int *held, uint64_t *t0, uint64_t sid) {      // menu action edge + key repeat (first after GU_REP_FIRST_MS, then every GU_REP_MS)
    uint64_t now = GetTickCount64();
    int on = ((char (*)(uint64_t))VMA(0x180068AF0))(sid) != 0, fire = 0;
    if (on && !*held) { fire = 1; *t0 = now + GU_REP_FIRST_MS; }
    else if (on && *held && now >= *t0) { fire = 1; *t0 = now + GU_REP_MS; }
    *held = on;
    return fire;
}
static void gu_cycle(void) {                     // focus moved: the menu's focus sound (sfx-cycle), at most every 60 ms
    uint64_t now = GetTickCount64();
    if (now - G.sfx_ms >= 60) { G.sfx_ms = now; ui_sfx("sfx-cycle"); }
}
// ------------------------------------------------------------------ RENAME (custom loadouts can be named both in game and in the launcher)
// The edit view's title becomes the name being typed (t2r-ext.c lo_nm_*: one cleaning rule with the launcher). Started by the RENAME prompt
// (menu-next: RB / the bumper glyph; the E key; a click on the prompt). While a name is typed:
//   keyboard  a low-level keyboard hook (kt_*) eats every key down (the engine sees none: W / S / Backspace / Esc / Enter do not move the menu
//             or pop the page) and turns it into text with the player's own layout (ToUnicodeEx: AltGr Polish letters work). Enter saves,
//             Esc cancels, Backspace / Delete, Left / Right / Home / End move the cursor. Modifiers, Alt+Tab and the Windows key pass through.
//   pad       up / down change the letter under the cursor (GN_PAD letters), left / right move it, SELECT saves, the menu-action button
//             deletes, menu-back cancels (the footer prompts read SAVE / DELETE / CANCEL with the device's own glyphs).
//   mouse     a click on SAVE saves, on CANCEL cancels, on DELETE deletes (the RENAME prompt hides while a name is typed).
// The hook lives only while a name is typed (+1.5 s), and passes everything through once the page stops polling it (500 ms): a stuck page can
// never leave the keyboard dead. The ups of eaten downs are eaten too (the engine never sees an up without its down).
static volatile LONG g_kt_state;
static volatile ULONGLONG g_kt_seen;
static struct { volatile LONG w, r; struct { uint16_t vk, ch; } q[64]; } g_kt;
static volatile uint8_t g_kt_down[256];
static void kt_push(int vk, uint16_t ch) {     // (two producers: the hook thread and the game thread's raw input; a key reaches only one of them)
    static volatile LONG lock;
    while (InterlockedCompareExchange(&lock, 1, 0)) YieldProcessor();
    LONG w = g_kt.w;
    if (w - g_kt.r < 64) { g_kt.q[w & 63].vk = (uint16_t)vk; g_kt.q[w & 63].ch = ch; InterlockedExchange(&g_kt.w, w + 1); }
    InterlockedExchange(&lock, 0);
}
static int kt_fg(void) { DWORD pid = 0; GetWindowThreadProcessId(GetForegroundWindow(), &pid); return pid == GetCurrentProcessId(); }
static LRESULT CALLBACK kt_ll_proc(int code, WPARAM wp, LPARAM lp) {
    if (code == HC_ACTION) {
        const KBDLLHOOKSTRUCT *k = (const KBDLLHOOKSTRUCT *)lp;
        int vk = (int)(k->vkCode & 0xFF);
        int down = wp == WM_KEYDOWN || wp == WM_SYSKEYDOWN, up = wp == WM_KEYUP || wp == WM_SYSKEYUP;
        if (up && g_kt_down[vk]) { g_kt_down[vk] = 0; return 1; }
        int mod = vk == VK_SHIFT || vk == VK_LSHIFT || vk == VK_RSHIFT || vk == VK_CONTROL || vk == VK_LCONTROL || vk == VK_RCONTROL || vk == VK_MENU ||
                  vk == VK_LMENU || vk == VK_RMENU || vk == VK_LWIN || vk == VK_RWIN || vk == VK_CAPITAL || vk == VK_NUMLOCK;
        int ctl = (GetAsyncKeyState(VK_CONTROL) & 0x8000) != 0, alt = (GetAsyncKeyState(VK_MENU) & 0x8000) != 0;
        int win = ((GetAsyncKeyState(VK_LWIN) | GetAsyncKeyState(VK_RWIN)) & 0x8000) != 0;
        if (down && !mod && (g_kt_on || (g_kt_enter && vk == VK_RETURN)) && GetTickCount64() - g_kt_seen < 500 && !(alt && !ctl) && !win && kt_fg()) {
            BYTE ks[256];
            memset(ks, 0, sizeof ks);
            if (GetAsyncKeyState(VK_SHIFT) & 0x8000) ks[VK_SHIFT] = ks[VK_LSHIFT] = 0x80;
            if (ctl) ks[VK_CONTROL] = ks[VK_LCONTROL] = 0x80;
            if (alt) ks[VK_MENU] = ks[VK_RMENU] = 0x80;
            if (GetKeyState(VK_CAPITAL) & 1) ks[VK_CAPITAL] = 1;
            WCHAR wb[4] = {0};
            HKL hkl = GetKeyboardLayout(GetWindowThreadProcessId(GetForegroundWindow(), NULL));
            int r = ToUnicodeEx((UINT)vk, k->scanCode, ks, wb, 4, 4 /* do not change the keyboard state (dead keys) */, hkl);
            kt_push(vk, r == 1 ? (uint16_t)wb[0] : 0);
            g_kt_down[vk] = 1;
            return 1;
        }
    }
    return CallNextHookEx(NULL, code, wp, lp);
}
static DWORD WINAPI kt_thread(void *arg) {
    (void)arg;
    HHOOK h = SetWindowsHookExW(WH_KEYBOARD_LL, kt_ll_proc, GetModuleHandleW(NULL), 0);
    xlog("gearup13: rename keyboard hook %s", h ? "installed" : "FAILED");
    MSG m;
    if (h) SetTimer(NULL, 1, 250, NULL);
    while (h && GetMessageW(&m, NULL, 0, 0) > 0) {
        if (m.message == WM_TIMER && GetTickCount64() - g_kt_seen > 1500) break;
        TranslateMessage(&m); DispatchMessageW(&m);
    }
    if (h) UnhookWindowsHookEx(h);
    InterlockedExchange(&g_kt_state, 0);
    return 0;
}
// While a name is typed, the keyboard only types (no menu navigation by letter keys) until Enter: the game reads the keyboard through raw
// input (tlou-ii.exe imports RegisterRawInputDevices + GetRawInputData, no DirectInput / GetAsyncKeyState). On some systems the hook above was
// installed but never ate a key (W / S walked the letters as menu-up / down, Esc popped as menu-back). So the game's own read is gated too:
// its GetRawInputData import is pointed here, and while a name is typed every keyboard down (and the up of an eaten down) becomes text for the
// box and reaches the game as "no key" (VKey 0xFF, overrun make code). Modifiers, Alt+key, the Windows key and the ups of keys the game saw
// down pass. Mouse and pad input are untouched. A key the hook ate never comes here (no double letters). Log 'gearup13: raw input gate ...'.
static volatile uint8_t g_kt_rdown[256];
typedef UINT (WINAPI *fn_grid)(HRAWINPUT, UINT, LPVOID, PUINT, UINT);
static fn_grid g_grid_real;
static int kt_raw_eat(RAWKEYBOARD *kb) {
    int vk = kb->VKey & 0xFF, up = (kb->Flags & RI_KEY_BREAK) != 0;
    if (!vk || vk == 0xFF) return 0;
    if (up) { if (g_kt_rdown[vk]) { g_kt_rdown[vk] = 0; return 1; } return 0; }
    if (!(g_kt_on || (g_kt_enter && vk == VK_RETURN)) || GetTickCount64() - g_kt_seen >= 500) return 0;
    int mod = vk == VK_SHIFT || vk == VK_LSHIFT || vk == VK_RSHIFT || vk == VK_CONTROL || vk == VK_LCONTROL || vk == VK_RCONTROL || vk == VK_MENU ||
              vk == VK_LMENU || vk == VK_RMENU || vk == VK_LWIN || vk == VK_RWIN || vk == VK_CAPITAL || vk == VK_NUMLOCK;
    if (mod) return 0;
    int ctl = (GetAsyncKeyState(VK_CONTROL) & 0x8000) != 0, alt = (GetAsyncKeyState(VK_MENU) & 0x8000) != 0;
    int win = ((GetAsyncKeyState(VK_LWIN) | GetAsyncKeyState(VK_RWIN)) & 0x8000) != 0;
    if ((alt && !ctl) || win) return 0;
    BYTE ks[256];
    memset(ks, 0, sizeof ks);
    if (GetAsyncKeyState(VK_SHIFT) & 0x8000) ks[VK_SHIFT] = ks[VK_LSHIFT] = 0x80;
    if (ctl) ks[VK_CONTROL] = ks[VK_LCONTROL] = 0x80;
    if (alt) ks[VK_MENU] = ks[VK_RMENU] = 0x80;
    if (GetKeyState(VK_CAPITAL) & 1) ks[VK_CAPITAL] = 1;
    WCHAR wb[4] = {0};
    UINT sc = kb->MakeCode | ((kb->Flags & RI_KEY_E0) ? 0xE000 : 0);
    int r = ToUnicodeEx((UINT)vk, sc, ks, wb, 4, 4, GetKeyboardLayout(0));
    kt_push(vk, r == 1 ? (uint16_t)wb[0] : 0);
    g_kt_rdown[vk] = 1;
    static int n; if (LOGCAP(n, 3)) xlog("gearup13: raw input gate - key %02x taken for the name (the hook did not see it)", vk);
    return 1;
}
static UINT WINAPI kt_grid_hook(HRAWINPUT h, UINT cmd, LPVOID data, PUINT sz, UINT hs) {
    UINT r = g_grid_real(h, cmd, data, sz, hs);
    if (cmd != RID_INPUT || !data || r == (UINT)-1 || r < sizeof(RAWINPUTHEADER) + sizeof(RAWKEYBOARD)) return r;
    RAWINPUT *ri = (RAWINPUT *)data;
    if (ri->header.dwType == RIM_TYPEKEYBOARD && kt_raw_eat(&ri->data.keyboard)) {
        ri->data.keyboard.VKey = 0xFF; ri->data.keyboard.MakeCode = KEYBOARD_OVERRUN_MAKE_CODE; ri->data.keyboard.Message = 0;
    }
    return r;
}
static void kt_raw_install(void) {                // once: the game's GetRawInputData import -> kt_grid_hook
    static int done;
    if (done) return;
    done = 1;
    uint8_t *b = (uint8_t *)GetModuleHandleW(NULL);
    FARPROC real = GetProcAddress(GetModuleHandleA("user32.dll"), "GetRawInputData");
    const IMAGE_NT_HEADERS64 *nt = (const IMAGE_NT_HEADERS64 *)(b + ((const IMAGE_DOS_HEADER *)b)->e_lfanew);
    IMAGE_DATA_DIRECTORY dd = nt->OptionalHeader.DataDirectory[IMAGE_DIRECTORY_ENTRY_IMPORT];
    void **slot = NULL;
    for (const IMAGE_IMPORT_DESCRIPTOR *id = dd.VirtualAddress ? (const IMAGE_IMPORT_DESCRIPTOR *)(b + dd.VirtualAddress) : NULL; id && id->Name && !slot; id++) {
        if (_stricmp((const char *)(b + id->Name), "user32.dll")) continue;
        IMAGE_THUNK_DATA64 *ft = (IMAGE_THUNK_DATA64 *)(b + id->FirstThunk);
        const IMAGE_THUNK_DATA64 *ot = id->OriginalFirstThunk ? (const IMAGE_THUNK_DATA64 *)(b + id->OriginalFirstThunk) : NULL;
        for (int i = 0; ft[i].u1.Function && !slot; i++) {
            if (ot && !IMAGE_SNAP_BY_ORDINAL64(ot[i].u1.Ordinal) && !strcmp((const char *)((const IMAGE_IMPORT_BY_NAME *)(b + ot[i].u1.AddressOfData))->Name, "GetRawInputData"))
                slot = (void **)&ft[i].u1.Function;
            else if (real && (FARPROC)ft[i].u1.Function == real) slot = (void **)&ft[i].u1.Function;
        }
    }
    if (!slot) { xlog("gearup13: raw input gate NOT installed (no GetRawInputData import found) - only the keyboard hook eats keys"); return; }
    DWORD old;
    if (!VirtualProtect(slot, sizeof *slot, PAGE_READWRITE, &old)) { xlog("gearup13: raw input gate NOT installed (import not writable)"); return; }
    g_grid_real = (fn_grid)*slot;
    InterlockedExchangePointer(slot, (void *)kt_grid_hook);
    VirtualProtect(slot, sizeof *slot, old, &old);
    xlog("gearup13: raw input gate installed (import at exe+%llx, was %p, user32 %p)", (unsigned long long)((uint8_t *)slot - b), (void *)g_grid_real, (void *)real);
}
static void kt_keepalive(void) {            // every frame while a name is typed
    g_kt_seen = GetTickCount64();
    if (!g_kt_state && InterlockedCompareExchange(&g_kt_state, 1, 0) == 0) {
        HANDLE t = CreateThread(NULL, 0, kt_thread, NULL, 0, NULL);
        if (t) CloseHandle(t); else InterlockedExchange(&g_kt_state, 0);
    }
}
static int kt_next(int *vk, uint32_t *ch) {
    LONG r = g_kt.r;
    if (r == g_kt.w) return 0;
    *vk = g_kt.q[r & 63].vk; *ch = g_kt.q[r & 63].ch;
    InterlockedExchange(&g_kt.r, r + 1);
    return 1;
}

static const char GN_PAD_UTF8[] = " ABCDEFGHIJKLMNOPQRSTUVWXYZ\xC4\x84\xC4\x86\xC4\x98\xC5\x81\xC5\x83\xC3\x93\xC5\x9A\xC5\xB9\xC5\xBB" "0123456789-.'!?#&+";
static uint32_t g_gn_pad[64]; static int g_gn_npad;
static int gn_ok(uint32_t c) {               // a letter the name can hold (upper case already)
    char o[8]; int n = lo_nm_put(o, 0, c); o[n] = 0;
    char t[LO_NM_BYTES + 2];
    return c != ' ' ? lo_nm_clean(o, t, -1) == 1 : 1;
}
static int gn_bytes(void) { int b = 0; for (int i = 0; i < GN.n; i++) b += GN.cp[i] < 0x80 ? 1 : 2; return b; }
static void gn_utf8(char *out, int from, int to) {     // cp[from..to) -> UTF-8
    int o = 0;
    for (int i = from; i < to && i < GN.n; i++) o = lo_nm_put(out, o, GN.cp[i]);
    out[o] = 0;
}
static int gn_insert(uint32_t c) {
    c = lo_nm_up(c);
    if (!c || !gn_ok(c)) return 0;
    if (GN.n >= LO_NM_MAX || gn_bytes() + (c < 0x80 ? 1 : 2) > LO_NM_BYTES) { ui_sfx("sfx-menu-error"); return 0; }
    memmove(&GN.cp[GN.cur + 1], &GN.cp[GN.cur], (size_t)(GN.n - GN.cur) * sizeof GN.cp[0]);
    GN.cp[GN.cur++] = c; GN.n++;
    return 1;
}
static void gn_delete(int before) {
    int at = before ? GN.cur - 1 : GN.cur;
    if (at < 0 || at >= GN.n) return;
    memmove(&GN.cp[at], &GN.cp[at + 1], (size_t)(GN.n - at - 1) * sizeof GN.cp[0]);
    GN.n--;
    if (before) GN.cur--;
}
static void gn_pad_letter(int dir) {          // pad up / down: the letter under the cursor walks GN_PAD (at the end: a new letter)
    if (!g_gn_npad) { const uint8_t *p = (const uint8_t *)GN_PAD_UTF8; while (*p && g_gn_npad < 64) p = lo_nm_dec(p, &g_gn_pad[g_gn_npad++]); }
    if (GN.cur >= GN.n) {
        if (!gn_insert(dir > 0 ? 'A' : '+')) return;
        GN.cur--;
        return;
    }
    int k = 0;
    for (int i = 0; i < g_gn_npad; i++) if (g_gn_pad[i] == GN.cp[GN.cur]) { k = i; break; }
    for (int t = 0; t < g_gn_npad; t++) {
        k = (k + (dir > 0 ? 1 : g_gn_npad - 1)) % g_gn_npad;
        uint32_t c = g_gn_pad[k];
        int w = (c < 0x80 ? 1 : 2) - (GN.cp[GN.cur] < 0x80 ? 1 : 2);
        if (gn_bytes() + w <= LO_NM_BYTES) { GN.cp[GN.cur] = c; return; }
    }
}
static void gn_start(int mode, int slot, const char *init, const char *how) {
    const uint8_t *p = (const uint8_t *)init;
    memset(&GN, 0, sizeof GN);
    GN.mode = mode; GN.slot = slot;
    while (*p && GN.n < LO_NM_MAX) p = lo_nm_dec(p, &GN.cp[GN.n++]);
    GN.cur = GN.n;
    GN.sel = GN.dflt = mode == 1 && GN.n > 0;
    GN.on = 1; GN.t0 = GetTickCount64(); GN.f0 = GN.click_f = g_frame;
    GN.pad = how[0] == 'p';
    GN.h_u = GN.h_d = GN.h_l = GN.h_r = GN.h_sel = GN.h_act = GN.h_back = GN.h_nx = 1;     // whatever is held now
    GN.t_u = GN.t_d = ~0ULL;
    g_kt.r = g_kt.w;
    kt_raw_install();
    InterlockedExchange(&g_kt_on, 1);
    kt_keepalive();
    ui_sfx("sfx-select");
    G.dirty = 1;
    if (mode == 1) xlog("gearup13: CREATE LOADOUT name box (custom %d, %s)", g_lo_n + 1, how);
    else xlog("gearup13: rename custom %d started (%s)", GN.slot + 1, how);
}
// RENAME
// RENAME used to type into the page title in place (an unnamed loadout started EMPTY, a named one appended at its end), while CREATE LOADOUT
// (loadouts 7-12) opens the NAME YOUR LOADOUT box with the name selected. RENAME now opens the same box: prefilled with the loadout's name (an unnamed
// one: its default label CUSTOM LOADOUT n, in the player's language), all selected - typing replaces it, Backspace empties it, the arrows keep it.
// The default label kept untouched saves as the default (an empty name), as in CREATE LOADOUT.
static void gn_begin(const char *how, int mode, int k) {      // mode 0: the edit view's (k = the active custom slot), 2: the list's (k = the focused custom slot)
    lo_nm_load();
    char d[32], c[LO_NM_BYTES + 2];
    const int dflt = k < 0 || !g_lo_nm[k][0];
    if (dflt) {
        snprintf(d, sizeof d, "CUSTOM LOADOUT %d", k + 1);
        const char *tr = loc_tr(d);
        lo_nm_clean(tr ? tr : d, c, -1);
    }
    gn_start(mode, k, dflt ? c : g_lo_nm[k], how);
    GN.sel = GN.n > 0;
    GN.dflt = dflt && GN.n > 0;
}
static void gn_create_begin(void) {              // CREATE LOADOUT: the box opens on the default name, selected
    char d[32], c[LO_NM_BYTES + 2];
    snprintf(d, sizeof d, "CUSTOM LOADOUT %d", g_lo_n + 1);
    const char *tr = loc_tr(d);                  // (in the player's language; kept unchanged it is saved as the default label)
    lo_nm_clean(tr ? tr : d, c, -1);
    gn_start(1, -1, c, G.h_sel ? "menu-select" : "click");
}
static void gn_unsel(int clear) {                // the prefilled default stops being selected (clear: it is replaced)
    if (!GN.sel) return;
    GN.sel = 0;
    if (clear) { GN.n = GN.cur = 0; }
}
static void gn_end(int save, const char *how) {
    if (!GN.on) return;
    InterlockedExchange(&g_kt_on, 0);
    GN.on = 0;
    const int mode = GN.mode;
    char nm[LO_NM_BYTES * 2 + 8];
    gn_utf8(nm, 0, GN.n);
    if (GN.dflt) nm[0] = 0;                      // (the default untouched: the default label)
    if (save && mode == 1) gu_create(nm);
    else if (save) {
        if (lo_nm_set(GN.slot, nm, "gear up")) lj_user_edit();      // (t2r-loadout.json is rewritten by the next lj_tick: the launcher adopts the name)
    }
    ui_sfx("sfx-select");
    // the menu edges seen while typing belong to the name: start every held state over
    G.h_sel = G.h_u = G.h_d = G.h_l = G.h_r = G.h_back = G.h_act = G.h_esc = G.h_r_key = 1;
    G.t_u = G.t_d = ~0ULL;
    G.dirty = 1;
    if (mode == 1) xlog("gearup13: CREATE LOADOUT %s (%s)", save ? "confirmed" : "cancelled", how);
    else xlog("gearup13: rename custom %d %s (%s)", GN.slot + 1, save ? "saved" : "cancelled", how);
}
// one frame of typing; returns 1 while the name owns the input (the rest of the page's input is skipped)
static int gn_tick(int click) {
    if (!GN.on) return 0;
    if (GN.mode == 0 && (G.view != 1 || g_lo_state != LO_LIST || lo_slot(g_lo_active) < 0)) { gn_end(0, "edit view left"); return 0; }
    if (GN.mode == 2 && (G.view != 0 || g_lo_state != LO_LIST || GN.slot < 0 || GN.slot >= g_lo_n)) { gn_end(0, "list left"); return 0; }
    if (GN.mode == 1 && (G.view != 0 || g_lo_state != LO_LIST || g_lo_n >= N_CUSTOM_MAX)) { gn_end(0, "list left"); return 0; }
    kt_keepalive();
    int vk; uint32_t ch; int moved = 0;
    while (kt_next(&vk, &ch)) {
        moved = 1; GN.pad = 0;
        if (vk == VK_RETURN) { gn_end(1, "Enter"); return 1; }
        if (vk == VK_ESCAPE) { gn_end(0, "Esc"); return 1; }
        if (vk == VK_BACK || vk == VK_DELETE) { if (GN.sel) gn_unsel(1); else gn_delete(vk == VK_BACK); GN.dflt = 0; }
        else if (vk == VK_LEFT) { gn_unsel(0); if (GN.cur > 0) GN.cur--; }
        else if (vk == VK_RIGHT) { gn_unsel(0); if (GN.cur < GN.n) GN.cur++; }
        else if (vk == VK_HOME) { gn_unsel(0); GN.cur = 0; }
        else if (vk == VK_END) { gn_unsel(0); GN.cur = GN.n; }
        else if (ch >= 0x20) { uint32_t u = lo_nm_up(ch); if (u && gn_ok(u)) { gn_unsel(1); GN.dflt = 0; } gn_insert(ch); }
    }
    // the pad (the keyboard's menu actions never reach the engine while the hook eats them)
    int up = gu_rep(&GN.h_u, &GN.t_u, fnv64("menu-up")), dn = gu_rep(&GN.h_d, &GN.t_d, fnv64("menu-down"));
    int lf = menu_edge(fnv64("menu-left"), &GN.h_l), rt = menu_edge(fnv64("menu-right"), &GN.h_r);
    int sel = menu_edge(0x6695c5b7921bb5ddULL /* menu-select */, &GN.h_sel), act = menu_edge_pad("menu-action", &GN.h_act);
    int back = menu_edge(fnv64("menu-back"), &GN.h_back), nx = MENU_NEXT_TAB(&GN.h_nx);
    if (click) GN.click_f = g_frame;
    if (sel && g_frame - GN.click_f <= 8) sel = 0;           // (a left click also sends menu-select, sometimes a frame late: the click alone decides)
    if (!g_pad_mode) up = dn = lf = rt = act = back = nx = sel = 0;   // (the keyboard only types; letters by up / down are the pad's)
    if (up || dn || lf || rt || act) { GN.pad = 1; moved = 1; }
    if (up || dn || act) GN.dflt = 0;
    if (act && GN.sel) { gn_unsel(1); act = 0; }   // (DELETE on the selected default: the box empties)
    if (up || dn || lf || rt) gn_unsel(0);
    if (up) gn_pad_letter(1);
    if (dn) gn_pad_letter(-1);
    if (lf && GN.cur > 0) GN.cur--;
    if (rt && GN.cur < GN.n) GN.cur++;
    if (act) gn_delete(GN.cur >= GN.n);
    if (moved) { ui_sfx("sfx-cycle"); GN.t0 = GetTickCount64(); G.dirty = 1; }
    if (back) { g_gu13_repush_until = g_frame + 10; gn_end(0, "menu-back"); return 1; }     // (the engine may pop the page on menu-back: it comes back on the same view)
    if ((sel && !click) || nx) { gn_end(1, nx ? "menu-next" : "menu-select"); return 1; }
    if (click && g_gu_hov_sel) { gn_end(1, "SAVE clicked"); return 1; }
    if (click && g_gu_hov_rst) { GN.dflt = 0; if (GN.sel) gn_unsel(1); else gn_delete(GN.cur >= GN.n); ui_sfx("sfx-cycle"); GN.t0 = GetTickCount64(); G.dirty = 1; return 1; }
    if (click && g_gu_hov_back) { gn_end(0, "CANCEL clicked"); return 1; }
    return 1;
}
// the title while typing: the name with the cursor (a blinking _ at the end, the letter under it in blue inside the name)
static void gn_text(char *t, size_t tn) {      // the name with the cursor (a blinking _ at the end, the letter under it in blue; the selected default all blue)
    char a[LO_NM_BYTES * 2 + 8], c[8], z[LO_NM_BYTES * 2 + 8];
    int blink = ((GetTickCount64() - GN.t0) / 530) & 1;
    if (GN.sel) { gn_utf8(a, 0, GN.n); snprintf(t, tn, "<font color=%c#8C8C8C%c>%s</font>%s", 34, 34, a, blink ? " " : "_"); return; }
    gn_utf8(a, 0, GN.cur);
    if (GN.cur < GN.n) { int n = lo_nm_put(c, 0, GN.cp[GN.cur]); c[n] = 0; gn_utf8(z, GN.cur + 1, GN.n); }
    else { snprintf(c, sizeof c, "%s", blink ? " " : "_"); z[0] = 0; }
    snprintf(t, tn, "%s<font color=%c#8C8C8C%c>%s</font>%s", a, 34, 34, c, z);
}
static void gn_title(void) {                     // CREATE LOADOUT and RENAME: the NAME YOUR LOADOUT box's field
    char t[256];
    gn_text(t, sizeof t);
    ui_text_raw("anim-group.nb.nbField", t);
}
// the breadcrumb (nrui.c nr_header: GEAR UP | the page). It re-places the divider / rule from the measured widths, so it is written only when the text changes
static void gu_head_set(const char *page) {
    static char last[160]; static uint64_t lent, lfr;
    if (!strcmp(last, page) && lent == G.enter_ms && g_frame - lfr < 90) return;
    snprintf(last, sizeof last, "%s", page); lent = G.enter_ms; lfr = g_frame;
    nr_header("GEAR UP", page);
}
static void gu_title(void) {
    char b[96];
    if (GN.on) gn_title();                       // (the name box: the page title stays)
    if (G.view == 1) { gu_head_set(lo_name(g_lo_active, b, sizeof b)); return; }
    if (g_lo_state == LO_CHOOSE) {
        uint8_t *o = lobby_obj();
        int secs = o ? *(int *)(o + 0x1b8) : 0;
        meta_t mt = meta_get();                      // the booster stage + loading follow: MATCH STARTS IN keeps counting the real time to the level start
        int left = (secs >= 100 ? secs - 100 : secs) + (mt.ok ? mt.mf : 0);
        if (left > 99) left = 99;
        snprintf(b, sizeof b, "CHOOSE LOADOUT - <font color=%c#F0F0F0%c>00:%02d</font>", 34, 34, left);     // (the tag keeps the words translatable)
        gu_head_set(b);
        return;
    }
    gu_head_set(g_lo_state == LO_MATCH ? "CHANGE LOADOUT" : "CHOOSE LOADOUT");
}
static void gu_enter(void) {
    memset(&G, 0, sizeof G);
    G.up = 1; G.enter_ms = GetTickCount64();
    G.h_sel = G.h_u = G.h_d = G.h_l = G.h_r = G.h_back = 1;       // whatever is held when the page opens
    G.t_u = G.t_d = ~0ULL;
    G.h_esc = 1; G.h_act = 1; G.h_r_key = 1; G.h_nx = 1; G.h_e = 1;
    if (GN.on) { InterlockedExchange(&g_kt_on, 0); GN.on = 0; xlog("gearup13: rename dropped (page up again)"); }
    G.hv_slot = G.hv_opt = -1; G.det_key = -1; G.pre_i = 0; G.pv = -1; G.pv_ign = -1; G.pv_lasthov = -1; G.pv_lastlst = -1; G.pv_lastwant = -1;
    g_gu_hov_lst = g_gu_hov_slot = g_gu_hov_opt = g_gu_hov_lvl = -1; g_gu_hov_back = g_gu_hov_sel = g_gu_hov_rst = 0; g_gu_hov_tg = -1;   // (the scan of this frame read the previous instance's view)
    G.lst = gu_idx_pos(g_lo_active); gu_scroll_to(G.lst);
    G.dirty = 1;
    if (g_lo_state == LO_NONE && match_substate() != 6) g_lo_state = LO_LIST;
    gu_fade_reset(); memset(g_gu_fit, 0, sizeof g_gu_fit);
    w_alpha(ui_w("anim-group"), 0.0f);                // the page fades in (see the end of feature_gearup13); an instance the match horn faded out starts at 0 as well
    ui_visible("anim-group.lst", 1);
    ui_visible("anim-group.ed", 0);
    ui_visible("anim-group.nb", 0);
    G.wcol = gu_pos_col(G.lst);
    xlog("gearup13: page up (state %d, active %d)", g_lo_state, g_lo_active);
    if (g_gu_keep.ok) {                              // pushed again after the engine's own pop on menu-back: the edit view where it was
        g_gu_keep.ok = 0;
        if (g_gu_keep.view == 1 && lo_slot(g_lo_active) >= 0 && g_lo_state == LO_LIST) {
            G.view = 1; G.closing = 0;
            gu_enter_slot(g_gu_keep.slot);
            G.col = g_gu_keep.col;
            gu_focus_opt(g_gu_keep.opt);
            ui_visible("anim-group.lst", 0);
            ui_visible("anim-group.ed", 1);
            xlog("gearup13: edit view restored (slot %d, %s)", G.slot, G.col ? "options" : "slots");
        }
    }
}
static void gu_back(const char *how) {
    if (G.view == 1) {
        if (G.col == 1) { G.col = 0; G.dirty = 1; gu_cycle(); xlog("gearup13: back to the slots (%s)", how); return; }
        gu_to_list(how);
        gu_cycle();
        return;
    }
    // list: the engine pops a pushed menu page on menu-back by itself; Esc it does not. Judged 6 frames after the press (a second pop would take the page under with it)
    G.back_f = g_frame ? g_frame : 1;
    xlog("gearup13: back from the list (%s)", how);
}
static void gu_log_miss(const char *where) {      // a click that hit nothing: everything needed to see why
    float cx = -1, cy = -1, rc[4] = {0, 0, 0, 0}; int kd, ix; char nm[96];
    POINT pt = {-1, -1}; RECT cr = {0, 0, 0, 0};
    HWND hw = GetForegroundWindow();
    if (hw) { GetCursorPos(&pt); ScreenToClient(hw, &pt); GetClientRect(hw, &cr); }
    int in = ui_cursor_canvas(&cx, &cy);
    float d = in ? gu_nearest(cx, cy, &kd, &ix, nm, sizeof nm, rc) : -1.0f;
    xlog("gearup13: click ignored: nothing under the cursor (%s; client px %ld,%ld of %ldx%ld; canvas %.0f,%.0f in %d; view %d col %d slot %d opt %d off %d nopt %d; nearest %s [%.0f,%.0f-%.0f,%.0f] dist %.0f)",
         where, (long)pt.x, (long)pt.y, (long)cr.right, (long)cr.bottom, cx, cy, in, G.view, G.col, G.slot, G.opt, G.off, g_gu_nopt, in ? nm : "-", rc[0], rc[1], rc[2], rc[3], d);
}
static void feature_gearup13(void) {
    g_gu13_up = 0;
    if (!g_gu13) return;
    uint64_t top = top_page();
#ifndef T2R_RELEASE
    // dev (A/B screenshots with no input): t2r-gu-test.txt next to the exe = open GEAR UP from the MP menu ("list"), or open it on the
    // first custom loadout's edit view ("edit"); the file is removed once used
    static int gu_test_edit; static uint64_t gu_test_at;
    { static uint64_t chk; uint64_t tn = GetTickCount64();
      if (tn - chk > 1000) { chk = tn; FILE *f = exe_side_open("t2r-gu-test.txt", "r");
        if (f) { char b[16] = {0}; if (!fgets(b, sizeof b, f)) b[0] = 0; fclose(f);
          if (g_lo_state == LO_NONE && ms_on_menu() && top != gu13_page_id()) {
              DeleteFileA("t2r-gu-test.txt"); gu_test_edit = !strncmp(b, "edit", 4); gu_test_at = tn; g_lo_state = LO_LIST; push_page_now(PAGE_LIST_NAME);
              xlog("gearup13: t2r-gu-test.txt - list opened from the menu%s", gu_test_edit ? ", edit view next" : ""); } } } }
#endif
    if (top != gu13_page_id()) {
        if (G.up) {
            G.up = 0;
            xlog("gearup13: page left (top now %s, state %d)", page_name(top), g_lo_state);
            gn_end(0, "page left");
            // menu-back in the edit view is a native pop of the page: come back on the list
            if (g_gu13_repush_until && g_frame <= g_gu13_repush_until && (g_lo_state == LO_LIST) && top) {
                g_gu_keep = (typeof(g_gu_keep)){1, G.view, G.col, G.slot, G.opt, G.off};
                push_page_now("to1/gearup13");
                xlog("gearup13: the engine popped the page on back - pushed again (list view)");
            }
            g_gu13_repush_until = 0;
        }
        if (g_gu13_repush_until && g_frame > g_gu13_repush_until) g_gu13_repush_until = 0;
        return;
    }
    g_gu13_up = 1;
    if (!G.up) gu_enter();
#ifndef T2R_RELEASE
    if (gu_test_edit && G.view == 0 && g_lo_state == LO_LIST && g_lo_n > 0 && GetTickCount64() - gu_test_at > 7000) { gu_test_edit = 0; xlog("gearup13: t2r-gu-test.txt - edit view of custom 1"); gu_pos_select(0, 1); }
#endif
    uint64_t now = GetTickCount64();
    // ---- closing (a mid-match pick pops two pages: nothing more to read from this one)
    if (G.closing) return;
    if ((g_lo_state == LO_CHOOSE || g_lo_state == LO_MATCH) && G.view == 1) gu_to_list("pre-match / mid-match: equip only");
    // ---- input
    int sel = menu_edge(0x6695c5b7921bb5ddULL /* menu-select */, &G.h_sel);
    int up = gu_rep(&G.h_u, &G.t_u, fnv64("menu-up")), down = gu_rep(&G.h_d, &G.t_d, fnv64("menu-down"));
    int left = menu_edge(fnv64("menu-left"), &G.h_l), right = menu_edge(fnv64("menu-right"), &G.h_r);
    int back = menu_edge(fnv64("menu-back"), &G.h_back);
    int rst_a = menu_edge_pad("menu-action", &G.h_act);
    int r_now = game_focused() && (GetAsyncKeyState('R') & 0x8000) != 0, rst_k = r_now && !G.h_r_key;
    G.h_r_key = r_now;
    int esc_now = game_focused() && (GetAsyncKeyState(VK_ESCAPE) & 0x8000) != 0, esc = esc_now && !G.h_esc;
    G.h_esc = esc_now;
    int wn = wheel_notches();
    { static int lpd = -1; if (lpd != g_pad_mode) { lpd = g_pad_mode; G.dirty = 1; } }       // the hint line follows the device in use
    int click = g_click_edge, lbtn_back = click && g_gu_hov_back;
    int mouse = g_mouse_mode;
    int ren_nx = MENU_NEXT_TAB(&G.h_nx);
    int e_now = game_focused() && (GetAsyncKeyState('E') & 0x8000) != 0, ren_k = e_now && !G.h_e;
    G.h_e = e_now;
    const int typing = gn_tick(click);              // RENAME owns the input while a name is typed
    if (typing) sel = up = down = left = right = back = esc = lbtn_back = rst_a = rst_k = click = wn = 0;
    if (!typing && G.view == 1 && g_lo_state == LO_LIST && lo_slot(g_lo_active) >= 0 && (ren_nx || ren_k || (click && g_gu_hov_ren))) {
        gn_begin(ren_nx ? "pad: menu-next" : click ? "click on RENAME" : "E key", 0, lo_slot(g_lo_active));
        sel = up = down = left = right = back = esc = lbtn_back = rst_a = rst_k = click = wn = 0;
    }
    // RENAME on the list (the focused custom loadout; the prompt is dimmed on a class / the CREATE tile)
    if (!typing && !GN.on && G.view == 0 && g_lo_state == LO_LIST && gu_pos_idx(G.lst) >= 0 && lo_slot(gu_pos_idx(G.lst)) >= 0 && (ren_nx || ren_k || (click && g_gu_hov_ren))) {
        gn_begin(ren_nx ? "pad: menu-next" : click ? "click on RENAME" : "E key", 2, lo_slot(gu_pos_idx(G.lst)));
        sel = up = down = left = right = back = esc = lbtn_back = rst_a = rst_k = click = wn = 0;
    }
    if (back || esc || lbtn_back) {
        if (G.view == 1 && back) g_gu13_repush_until = g_frame + 10;     // (the engine may pop the page itself on menu-back)
        gu_back(esc ? "Esc" : lbtn_back ? "BACK clicked" : "menu-back");
        back = esc = lbtn_back = 0; sel = 0;
    }
    if (G.back_f && g_frame >= G.back_f + 6 && !GN.on) {
        G.back_f = 0;
        if (top_page() == gu13_page_id() && G.view == 0 && !G.closing) { pop_page(); G.closing = 1; xlog("gearup13: list closed"); return; }
    }
    if (G.view == 0) {
        // the old page's list: up / down = the previous / next position (wraps through customs, CREATE LOADOUT, classes), left / right = the other block
        if (up || down) {
            const int n = gu_npos();
            G.lst = (G.lst + (down ? 1 : n - 1)) % n; G.wcol = gu_pos_col(G.lst); gu_scroll_to(G.lst); G.dirty = 1; gu_cycle();
        }
        if (left || right) {
            const int row = 1 - gu_pos_row(G.lst), n = gu_row_len(row);
            const int col = G.wcol < n ? G.wcol : n - 1;
            G.lst = gu_rc_pos(row, col); gu_scroll_to(G.lst); G.dirty = 1; gu_cycle();
        }
        if (wn && gu_row_len(0) > GU_VISC) {          // wheel: scroll the custom window (the focus stays in view)
            int c = G.coff - wn, mx = gu_row_len(0) - GU_VISC;
            G.coff = c < 0 ? 0 : c > mx ? mx : c;
            if (gu_pos_row(G.lst) == 0 && (G.lst < G.coff || G.lst >= G.coff + GU_VISC)) { G.lst = G.lst < G.coff ? G.coff : G.coff + GU_VISC - 1; G.wcol = G.lst; }
            G.dirty = 1;
        }
        if (click && g_gu_hov_lst >= 0 && !lbtn_back) {
            // click selects (the right panel + the chosen loadout), a click on the already chosen custom loadout opens its editor
            const int hi = gu_pos_idx(g_gu_hov_lst);
            const int again = hi >= 0 && hi == g_lo_active && g_gu_hov_lst == G.lst && lo_slot(hi) >= 0 && g_lo_state == LO_LIST;
            G.lst = g_gu_hov_lst; G.wcol = gu_pos_col(G.lst); G.dirty = 1; G.click_f = g_frame; sel = 0;
            xlog("gearup13: click on list row %d: %s", G.lst, G.lst == g_lo_n ? "CREATE LOADOUT" : again ? "already selected, edit" : "select");
            gu_pos_select(G.lst, again);
        }
        if (sel && G.click_f && g_frame - G.click_f <= 8) { xlog("gearup13: menu-select ignored: the click already acted"); sel = 0; }
        if (sel) { xlog("gearup13: select on list row %d (keyboard / pad)", G.lst); gu_pos_select(G.lst, 1); }
        if (g_lo_state == LO_MATCH && lo_owns_purchasable() && gu_pos_idx(G.lst) >= 0) {   // rule: a different class costs the purchasable
            loadout_t c;
            memset(&c, 0xff, sizeof c.w);
            lo_read_obj(&c);
            if (c.w[2] != lo_of(gu_pos_idx(G.lst))->w[2]) {
                static int last_logged = -2;
                g_lo_warn_frame = g_frame ? g_frame : 1;
                if (last_logged != G.lst) { last_logged = G.lst; xlog("gearup13: purchasable warning shown for row %d (different class, purchasable owned)", G.lst); }
            }
        }
    } else {
        const int nopt = g_gu_nopt;
        if (rst_a || rst_k || (click && g_gu_hov_rst)) { gu_reset(); sel = 0; }
        if (wn && nopt > GU_OPT_ROWS) {              // wheel: scroll the options window; a focus pushed out follows to the edge
            int off = G.off - wn;
            if (off < 0) off = 0;
            if (off > nopt - GU_OPT_ROWS) off = nopt - GU_OPT_ROWS;
            G.off = off;
            if (G.opt < off) G.opt = off;
            else if (G.opt >= off + GU_OPT_ROWS) G.opt = off + GU_OPT_ROWS - 1;
            G.dirty = 1;
        }
        // hover changes NOTHING but its own light highlight: focus, tab, column, details and skill level move only on a click or the keyboard / pad
        // a click is acted on HERE, on the element under the cursor, whatever the focus is: the engine's menu-select edge (sel) can arrive a frame late,
        // be latched high by the previous click, or find the focus elsewhere (a level line clicked while the SLOTS column had the focus only moved to the
        // options; the focus kept where the keyboard left it equipped the wrong row). sel of the same click is then dropped.
        if (click && !lbtn_back) {
            const gu_opt_t *co = G.opt >= 0 && G.opt < nopt ? &g_gu_opt[G.opt] : NULL;
            if (g_gu_hov_lvl >= 0 && co && co->kind == GO_SKILL) {
                int old_lv = g_gu_lvl[co->row], nlv = g_gu_hov_lvl + 1;
                g_gu_lvl[co->row] = nlv;                                     // (tried: a level the player can't have is denied and never selected)
                if (nlv != old_lv && (!(SK[co->row].avail >> (nlv - 1) & 1) || sk_cost_with(G.slot - GS_SK1, SK_V(co->row, nlv)) > 13)) {
                    gu_equip(G.slot, co);                                    // (the denied feedback: message + buzzer)
                    g_gu_lvl[co->row] = old_lv; sel = 0; G.click_f = g_frame;
                    xlog("gearup13: click on level %d of %s: denied, marker stays on %d", nlv, SK[co->row].name, old_lv);
                } else {
                g_gu_lvl[co->row] = nlv; G.col = 1; G.dirty = 1;
                xlog("gearup13: click on level %d of %s: applied", g_gu_hov_lvl + 1, SK[co->row].name);
                gu_equip(G.slot, co); sel = 0; G.click_f = g_frame;
                }
            } else if (g_gu_hov_tg >= 0 && co && co->kind == GO_GUN && co->sj >= 0) {
                G.col = 1; G.click_f = g_frame;                          // (equipped below with the toggle code)
                xlog("gearup13: click on the %s button: applied", g_gu_hov_tg ? "SUPPRESSED" : "UNSUPPRESSED");
            } else if (g_gu_hov_opt >= 0) {
                G.col = 1; gu_focus_opt(g_gu_hov_opt);
                xlog("gearup13: click on option %d (%s): applied", g_gu_hov_opt, gu_head(G.slot));
                gu_equip(G.slot, &g_gu_opt[G.opt]); sel = 0; G.click_f = g_frame;
            } else if (g_gu_hov_slot >= 0) {
                xlog("gearup13: click on slot %d: options column", g_gu_hov_slot);
                if (g_gu_hov_slot != G.slot) gu_enter_slot(g_gu_hov_slot);
                G.col = 1; G.dirty = 1; sel = 0; G.click_f = g_frame; gu_sfx("sfx-select");
            } else if (!g_gu_hov_rst && !g_gu_hov_back && !g_gu_hov_ren) gu_log_miss("view 1");
        }
        if (sel && G.click_f && g_frame - G.click_f <= 8) { xlog("gearup13: menu-select ignored: the click already acted (%d frames ago)", (int)(g_frame - G.click_f)); sel = 0; }
        if (G.col == 0) {
            if (up) { gu_enter_slot((G.slot + GU_SLOTS - 1) % GU_SLOTS); gu_cycle(); }
            if (down) { gu_enter_slot((G.slot + 1) % GU_SLOTS); gu_cycle(); }
            if (right) { G.col = 1; G.dirty = 1; gu_cycle(); }
            if (sel) { G.col = 1; G.dirty = 1; gu_sfx("sfx-select"); xlog("gearup13: options of %s", gu_head(G.slot)); }
        } else {
            const gu_opt_t *o = G.opt >= 0 && G.opt < nopt ? &g_gu_opt[G.opt] : NULL;
            int skl_multi = o && o->kind == GO_SKILL && SK[o->row].nlv > 1;
            if (up && nopt) { gu_focus_opt((G.opt + nopt - 1) % nopt); gu_cycle(); }
            if (down && nopt) { gu_focus_opt((G.opt + 1) % nopt); gu_cycle(); }
            loadout_t vc;
            gu_read_cur(&vc);
            int has_tg = o && o->kind == GO_GUN && o->sj >= 0;
            int tgv = has_tg ? gu_opt_var(G.slot, o, &vc) : -1;
            if (has_tg) {                             // A / D: UNSUPPRESSED / SUPPRESSED of the focused gun (never leaves the options column)
                if (left && tgv != 0) { gu_set_variant(G.slot, o, 0); gu_cycle(); }
                if (right && tgv != 1) { gu_set_variant(G.slot, o, 1); gu_cycle(); }
                left = right = 0;
                if (click && g_gu_hov_tg >= 0) { if (tgv != g_gu_hov_tg) gu_set_variant(G.slot, o, g_gu_hov_tg); sel = 0; }
            }
            if (skl_multi) {                          // A / D: the level of the focused skill (the points / lock show on the lines)
                int id = (int)o->row;
                if (left && g_gu_lvl[id] > 1) { g_gu_lvl[id]--; G.dirty = 1; gu_cycle(); }
                else if (left && g_gu_lvl[id] <= 1) { G.col = 0; G.dirty = 1; gu_cycle(); }
                if (right && g_gu_lvl[id] < SK[id].nlv) { g_gu_lvl[id]++; G.dirty = 1; gu_cycle(); }
            } else if (left) { G.col = 0; G.dirty = 1; gu_cycle(); }
            if (sel && o) { xlog("gearup13: select on option %d (keyboard / pad / late edge)", G.opt); gu_equip(G.slot, o); }
        }
    }
    // ---- fill: on a change, twice a second, and at the page's first moments (its widgets may be built a frame late)
    static const uint32_t OFF_MS[] = {33, 100, 250, 670, 1500, 3000};
    if (G.stage < (int)(sizeof OFF_MS / sizeof OFF_MS[0]) && now - G.enter_ms >= OFF_MS[G.stage]) { G.stage++; G.dirty = 1; gu_fade_reassert(); }
    {   // the hover highlight follows the cursor: a changed hovered element refills (fades only)
        static int lh[4] = {-9, -9, -9, -9}; static unsigned lv;
        if (lh[0] != g_gu_hov_lst || lh[1] != g_gu_hov_slot || lh[2] != g_gu_hov_opt || lh[3] != g_gu_hov_tg || lv != (unsigned)G.view) {
            lh[0] = g_gu_hov_lst; lh[1] = g_gu_hov_slot; lh[2] = g_gu_hov_opt; lh[3] = g_gu_hov_tg; lv = (unsigned)G.view; G.dirty = 1;
        }
    }
    if (G.view == 0) {   // which loadout the right panel previews: the hovered row, else the focused one (a keyboard / pad move wins until the mouse enters another row)
        int hv = -1;                                 // hover only highlights, the details follow the focus / click (G.lst)
        if (G.pv_lastlst != G.lst) { G.pv_lastlst = G.lst; if (G.pv_lastwant >= 0) G.pv_ign = hv; }
        if (hv != G.pv_lasthov) { G.pv_lasthov = hv; if (hv != G.pv_ign) G.pv_ign = -2; }
        int want = hv >= 0 && hv != G.pv_ign && G.pv_ign == -2 ? hv : G.lst;
        if (want != G.pv_lastwant) { G.pv_chg = G.pv_ign == -2 ? now : now - 60; G.pv_lastwant = want; }
        G.pv_want = want;
        if (G.pv < 0) G.pv = want;
    } else G.pv = -1;
    if (G.dirty || !(g_frame % 90)) {
        G.dirty = 0;
        if (G.view == 0) gu_fill_list(); else gu_fill_edit();
    }
    gu_fade_tick(now);
    gu_anim_tick(now);
    gu_preload_tick();
    {   // page fade-in: 0 -> 1 over 220 ms, in 1/24 steps (written only when the step changes)
        static int last_q = -1; static uint64_t last_enter;
        if (G.enter_ms != last_enter) { last_enter = G.enter_ms; last_q = -1; }
        float f = (float)(now - G.enter_ms) / 220.0f;
        if (f > 1.0f) f = 1.0f;
        f = 1.0f - (1.0f - f) * (1.0f - f);
        int q = (int)(f * 24.0f + 0.5f);
        if (q != last_q) { last_q = q; w_alpha(ui_w("anim-group"), (float)q / 24.0f); }
    }
    gu_title();
}
