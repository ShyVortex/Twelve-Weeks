// rank13.h - the 2013 Factions rank next to a player name: one chalk symbol (rank-0..9.png = tools/models/rank_icons.py) + the weeks survived in total (0..999).
// Server: tools/clan.py rank_of -> state text " wk=<weeks> rk=<symbol> dt=<days>" (op 0xE1) and the 'Q' rows of clan_ingame section 5 (fields 14 / 15).
// Included in t2r-ext.c after ui_text / ui_image (rank_ui) and before clan13.c; the pure helpers (rank13_clamp, rank13_path) also compile on their own.
#pragma once
#include <stdio.h>

#define RANK13_SYMBOLS 10
#define RANK13_MAX_WEEKS 999
static inline int rank13_sym(int rk) { return rk < 0 ? -1 : rk >= RANK13_SYMBOLS ? RANK13_SYMBOLS - 1 : rk; }      // -1 = unknown (no rank drawn)
static inline int rank13_weeks(int wk) { return wk < 0 ? 0 : wk > RANK13_MAX_WEEKS ? RANK13_MAX_WEEKS : wk; }
static inline void rank13_path(char *o, size_t n, int rk) { snprintf(o, n, "streaming/t2r/icons/rank-%d.png", rank13_sym(rk) < 0 ? 0 : rank13_sym(rk)); }

// draw: the image widget `icon` shows the symbol of `rk`, the text widget `num` the weeks (superscript at the symbol's top-right, rank_badge_widgets.py); rk < 0 (unknown /
// older daemon) hides both. The weeks widget is shown explicitly (ui_visible): the widgets are created hidden and only the symbol was ever switched on, so the number
// stayed invisible.
static void rank_ui(const char *icon, const char *num, int rk, int wk) {
    int s = rank13_sym(rk);
    if (s < 0) { ui_visible(icon, 0); ui_text(num, ""); ui_visible(num, 0); return; }
    char p[64], t[16];
    rank13_path(p, sizeof p, s);
    ui_image(icon, p);
    ui_visible(icon, 1);
    snprintf(t, sizeof t, "%d", rank13_weeks(wk));
    ui_text(num, t);
    ui_visible(num, 1);
}
