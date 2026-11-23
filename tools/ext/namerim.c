// namerim.c - the lead dev's hot pink name outline on the MENU name widgets (only rank badges changed colour, not name tags).
// The roles work (tools/roles.py role 4 =, #ff537d since (Discord Creator pink), the name keeps its own colour) drew the
// rim only on the in-match overhead tags (t2r-ext.c feature_nametags_draw: 8 offset glyph copies). The lead dev never sees their own overhead tag, and the menu
// name texts (MP menu LOBBY rows, the ESC scoreboard, the end-of-match scoreboard) had no rim at all, so on their own screen only the rank badge changed colour.
// gui2 text widgets have no outline colour of their own, so the rim is 8 hidden pink text widgets per name (tools/features/rank_badge_widgets.add_name_rims: clones
// of the name at offsets (dx, dy) * R, depth just below it, the same parent). Here: a row whose player has role 4 gets the name's shown text (markup stripped) in its
// 8 rims and shows them; every other row keeps them hidden. A rim follows its name's place and scale (the scoreboard moves / shrinks names at runtime, sbteam.c).
// Included after friends13.c (fr_row_names) and rankbadge.c (rkb_role_of, g_rkb_sbw / g_rkb_sbn); rankbadge.c rkb_tick calls nrim_tick (menu or match). The text each
// lobby name widget shows is noted in settext_hook (nrim_note). Opt-out: t2r-no-namerim.txt next to the exe.
#define NRIM_N 8
static const float NRIM_DX[NRIM_N] = {1, 0.7071f, 0, -0.7071f, -1, -0.7071f, 0, 0.7071f}, NRIM_DY[NRIM_N] = {0, 0.7071f, 1, 0.7071f, 0, -0.7071f, -1, -0.7071f};
#define NRIM_R 1.0f                                   // = rank_badge_widgets.RIM_R (canvas units; the widget clones carry the same offsets). 2.0 was too thick
static int mfnr_is_me(const char *nm);                // mfnr.c: the name is ours (the scoreboard's own row)

static int nrim_off(void) {                           // t2r-no-namerim.txt next to the exe = rims never shown
    static int off = -1; static uint64_t chk;
    return ov_off("t2r-no-namerim.txt", &off, &chk);
}
static void nrim_strip(char *o, size_t n, const char *t) {      // the name without <font ...> / <scale> markup (the rim's colour is its own tint)
    size_t k = 0;
    for (const char *p = t ? t : ""; *p && k + 1 < n; p++) {
        if (*p == '<') { const char *e = strchr(p, '>'); if (e) { p = e; continue; } }
        o[k++] = *p;
    }
    o[k] = 0;
}
static int nrim_scale_get(uint64_t w, float *sx, float *sy) {   // the rect transform's scale (transform + 0x30, what gui2-rxfm-set-scale-ps writes; w_scale)
    uint64_t g[1] = {w};
    uint64_t xf = w ? dc_call(SID_GUI2_GET_WIDGET_TRANSFORM, 1, g) : 0;
    if (!xf || xf == ~0ULL || IsBadReadPtr((void *)(uintptr_t)(xf + 0x30), 8)) return 0;
    *sx = *(const float *)(uintptr_t)(xf + 0x30); *sy = *(const float *)(uintptr_t)(xf + 0x34);
    return __builtin_isfinite(*sx) && __builtin_isfinite(*sy) && *sx > 0.05f && *sx < 20.0f && *sy > 0.05f && *sy < 20.0f;
}

// ---- the lobby rows: the text each Player<r>.nameLabel shows (settext_hook -> nrim_note, after srch_name_write cut its tags)
static uint64_t g_nrim_lw[8];
static char g_nrim_lt[8][64];
static uint64_t g_nrim_lat;                           // g_frame of the last handle lookup
// live 186 (no pink outline on the own lobby row, badge pink): the page writes each row's name ONCE when it builds the row, usually before the next
// handle lookup (at most twice a second), so the write found no known handle and was dropped, and the lookup then cleared the new row's text. The other rows fall
// back to the roster names (fr_row_names); row 0 (us) has none, so its rim got '' and stayed hidden. Now the engine's writes to widgets we do not know yet are kept
// in a small ring, and a lookup that finds a new row handle takes that row's text from it.
#define NRIM_PEND 128
static struct { uint64_t w; char t[64]; } g_nrim_pend[NRIM_PEND];
static unsigned g_nrim_pi;
static char g_nrim_mt[64];                            // the last engine write that shows OUR name (t2r-name.txt; mfnr_is_me): row 0's text when its own write was missed
static void nrim_lobby_resolve(void) {
    g_settext_in = 1;
    for (int r = 0; r < 8; r++) {
        char p[96]; snprintf(p, sizeof p, "anim-group.lobbyPanel.lobbyList.Player%d.nameLabel", r);
        uint64_t w = ui_w(p);
        if (w != g_nrim_lw[r]) {                      // a rebuilt row: its old text is gone; its first text may already have been written (the newest write wins)
            g_nrim_lw[r] = w; g_nrim_lt[r][0] = 0;
            for (unsigned k = 1; w && k <= NRIM_PEND; k++) {
                unsigned i = (g_nrim_pi - k) % NRIM_PEND;
                if (g_nrim_pend[i].w == w) { snprintf(g_nrim_lt[r], sizeof g_nrim_lt[r], "%s", g_nrim_pend[i].t); break; }
            }
        }
    }
    g_settext_in = 0;
    g_nrim_lat = g_frame;
}
static void nrim_note(uint64_t w, const char *t) {
    if (!w || g_settext_in) return;
    for (int pass = 0; pass < 2; pass++) {
        for (int r = 0; r < 8; r++) if (g_nrim_lw[r] == w) { snprintf(g_nrim_lt[r], sizeof g_nrim_lt[r], "%s", t ? t : ""); return; }
        if (match_substate() == 6) return;
        if (!pass && !g_ui_own) {                     // the engine's / winmm's write (ui_text's own writes are never a lobby name): kept for the next lookup
            unsigned i = g_nrim_pi++ % NRIM_PEND;
            g_nrim_pend[i].w = w; snprintf(g_nrim_pend[i].t, sizeof g_nrim_pend[i].t, "%s", t ? t : "");
            if (t && mfnr_is_me(t)) snprintf(g_nrim_mt, sizeof g_nrim_mt, "%s", t);
        }
        if (pass || g_frame - g_nrim_lat < 30) return;
        nrim_lobby_resolve();                         // a write to a widget we do not know: maybe a row was rebuilt (at most twice a second)
    }
}

// one name widget + its 8 rims (paths "<rim_fmt>" with %d = 0..7): show = the rim text (NULL / "" = hidden)
typedef struct { char txt[64]; int on; unsigned gen; uint64_t nw; float px, py, sx, sy; } nrim_row_t;
static void nrim_apply(nrim_row_t *S, uint64_t name_w, const char *rim_fmt, const char *show) {
    char p[160], s[64];
    nrim_strip(s, sizeof s, show);
    int on = s[0] != 0 && name_w != 0;
    // a new page instance (our page op, or the engine rebuilt the row: a new name widget handle) has fresh, hidden rims: everything is written again
    if (S->gen != g_ui_gen || S->nw != name_w) { memset(S, 0, sizeof *S); S->gen = g_ui_gen; S->nw = name_w; S->on = -1; }
    if (on == S->on && (!on || !strcmp(S->txt, s))) {
        if (!on) return;
    } else {
        for (int i = 0; i < NRIM_N; i++) {
            snprintf(p, sizeof p, rim_fmt, i);
            if (on) ui_text(p, s);
            ui_visible(p, on);
        }
        S->on = on; snprintf(S->txt, sizeof S->txt, "%s", s);
        S->px = S->py = S->sx = S->sy = -1e9f;        // place them again below
        static int nl; if (LOGCAP(nl, 12)) xlog("namerim: %s rim (%s) on '%s'", on ? "pink" : "no", rim_fmt, s);
        if (!on) return;
    }
    float x, y, sx = 1.0f, sy = 1.0f;                 // follow the name: its place (+ the rim offset) and its scale
    if (!w_pivot_get(name_w, &x, &y)) return;
    nrim_scale_get(name_w, &sx, &sy);
    if (x == S->px && y == S->py && sx == S->sx && sy == S->sy) return;
    S->px = x; S->py = y; S->sx = sx; S->sy = sy;
    for (int i = 0; i < NRIM_N; i++) {
        snprintf(p, sizeof p, rim_fmt, i);
        uint64_t w = ui_w(p);
        if (!w) continue;
        w_pivot(w, x + NRIM_DX[i] * NRIM_R, y + NRIM_DY[i] * NRIM_R);
        w_scale(w, sx, sy);
    }
}

static int nrim_role_me(void) { clan_t c = clan_get(); return c.ok ? c.ro : 0; }

static void nrim_tick(uint64_t now) {
    static uint64_t next;
    if (now < next) return;
    next = now + 150;
    int off = nrim_off();
    // lobby rows (MP menu / find match; lobby-row + find-match-row): row r shows the name fr_row_names lists (row 0 = us: our own role from the clan state)
    static nrim_row_t LS[8];
    if (match_substate() != 6) {
        if (g_frame - g_nrim_lat > 30) nrim_lobby_resolve();
        char nm[8][48] = {{0}}; int me[8] = {0};
        int used = fr_row_names(nm, me);
        for (int r = 0; r < 8; r++) {
            const char *shown = g_nrim_lt[r][0] ? g_nrim_lt[r] : nm[r][0] ? nm[r] : me[r] ? g_nrim_mt : "";
            int ro = r >= used || rkb_placeholder(shown) ? 0 : me[r] ? nrim_role_me() : rkb_role_of(shown);
            char f[96]; snprintf(f, sizeof f, "anim-group.lobbyPanel.lobbyList.Player%d.nmRim%%d", r);
            nrim_apply(&LS[r], g_nrim_lw[r], f, !off && ro == 4 ? shown : NULL);
        }
    }
    // scoreboards (ESC page + end of match): the name widgets rankbadge.c rkb_sb_tick found, the texts it noted
    static nrim_row_t SS[8];
    for (int k = 0; k < 8; k++) {
        const char *nm = g_rkb_sbn[k];
        if (!g_rkb_sbw[k]) continue;                                         // no scoreboard up: its rims went with the page (a new one = new handles, nrim_apply starts over)
        int ro = !nm[0] || !strncmp(nm, "PLAYER ", 7) || !strcmp(nm, "-") ? 0 : mfnr_is_me(nm) ? nrim_role_me() : rkb_role_of(nm);
        char f[96]; snprintf(f, sizeof f, "anim-group.scoreboard.team%d_row%d_nmRim%%d", k / 4, k % 4);
        nrim_apply(&SS[k], g_rkb_sbw[k], f, !off && ro == 4 ? nm : NULL);
    }
}
