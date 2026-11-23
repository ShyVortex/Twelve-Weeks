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

// player roles (tools/roles.py: 1 OG, 2 admin, 3 dev, 4 lead dev): the badge in the role's colour - the symbol image rank-<k>-r<1..4>.png (tools/models/rank_icons.py
// tinted, each with a baked glow; the lead dev has its own pink r4; the Discord role colours: admin green, dev blue, lead pink) and the weeks number in the same colour. 0 / unknown = the plain chalk badge.
static inline int rank13_role_tint(int role) { return (role >= 1 && role <= 4) ? role : 0; }
static inline const char *rank13_role_hex(int role) {
    switch (rank13_role_tint(role)) { case 1: return "#f2c14e"; case 2: return "#2ecc71"; case 3: return "#206694"; case 4: return "#ff537d"; default: return NULL; }
}
static inline void rank13_role_path(char *o, size_t n, int rk, int role) {
    int s = rank13_sym(rk) < 0 ? 0 : rank13_sym(rk), t = rank13_role_tint(role);
    if (t) snprintf(o, n, "streaming/t2r/icons/rank-%d-r%d.png", s, t); else rank13_path(o, n, rk);
}

// draw: the image widget `icon` shows the symbol of `rk`, the text widget `num` the weeks (superscript at the symbol's top-right, rank_badge_widgets.py); rk < 0 (unknown /
// older daemon) hides both. the weeks widget is shown explicitly (ui_visible): the widgets are created hidden and only the symbol was ever switched on, so the number
// stayed invisible (the weeks did not show at all).
static void rank_ui_role(const char *icon, const char *num, int rk, int wk, int role) {
    int s = rank13_sym(rk);
    if (s < 0) { ui_visible(icon, 0); ui_text(num, ""); ui_visible(num, 0); return; }
    char p[64], t[64];
    rank13_role_path(p, sizeof p, s, role);
    ui_image(icon, p);
    ui_visible(icon, 1);
    const char *hx = rank13_role_hex(role);
    if (hx) snprintf(t, sizeof t, "<font color=%c%s%c>%d</font>", 34, hx, 34, rank13_weeks(wk));
    else snprintf(t, sizeof t, "%d", rank13_weeks(wk));
    ui_text(num, t);
    ui_visible(num, 1);
}
static void rank_ui(const char *icon, const char *num, int rk, int wk) { rank_ui_role(icon, num, rk, wk, 0); }
