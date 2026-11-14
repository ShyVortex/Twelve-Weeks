// clan13.h - the pure core of the in-game CLAN page (clan13.c): parse of the daemon's op 0xB7 text (tools/clan_ingame.py), the journal's story-thread grouping and
// the text clipper. No engine calls: tests/clan13_test.c compiles it alone against the daemon's real output.
#ifndef CLAN13_H
#define CLAN13_H
#include <stdio.h>
#include <string.h>
#include <stdlib.h>

#define C13_NP 40
#define C13_NJ 24
#define C13_NL 72                      // timeline one-liners of the journal (<= 3 under each of <= 24 stories)
#define C13_NS 5
#define C13_NM 8
#define C13_NT 32
#define C13_NU 4
#define C13_NX 12                      // players of a raid's MATCH STATS list (section 5)
#define C13_ND 86                      // the journal's day entries of a clan run (section 6: day 0 = the founding .. day 84), oldest first
#define C13_NG 48                      // paragraphs of the days of ONE week (section 6 carries the text of the week that was asked for)
typedef struct { char name[28], role[28], st, stw[20], expr[14], pid[24], bond[28], bondty[20], tag[160], lately[176], icon[14]; } cl13_p_t;
typedef struct { long id; char cap[64], title[96], body[1720], tone[8], arc[16]; int step, day, week; char pid[24], who[28]; int fresh, more; } cl13_j_t;
typedef struct { long card; int day, fresh; char text[104]; } cl13_l_t;       // a one-liner under the story with id `card` (the journal holds stories, the one-liners are small timeline rows between them)
typedef struct { char label[20]; int stock, days, need; } cl13_s_t;
typedef struct { int day; char map[32]; int win, sup, need, fresh; int got[5], needc[5]; } cl13_m_t;
typedef struct { int day, fresh; char qty[12], name[64], icon[20]; } cl13_t_t;
typedef struct { char name[28], role[28], state[12], stw[24], pid[24], line[160]; } cl13_u_t;
typedef struct { int day, dow, week; long id; char title[80], tone[8], map[36]; int win, sup, need, h, u, s, dn, fresh; } cl13_d_t;      // a day entry of the journal (ONE entry per clan day; h = -1: counts unknown, an entry from before the day entries)
typedef struct { int day; char cap[48], text[760]; } cl13_g_t;       // a paragraph of a day entry: its caption (THE RAID / SUPPLIES / THE CAMP / the event's name / NOTES) and text
typedef struct { char name[28]; int team, me, kills, downs, deaths, revives, execs, heads, parts, left, head, rk, wk; } cl13_x_t;      // a player of the raid's match (-1 = not reported; kills = enemies downed, downs = times downed; head = the face's pool model id, 0 = none / an older daemon)
typedef struct {
    int have[8];                       // sections that arrived (1 roster, 2 journal (old rows), 3 raids, 4 status, 5 match stats, 6 the journal's week pages)
    int nd, ng, jweek, jtop;           // section 6: entries, paragraphs, the week the paragraphs are of, the newest week with an entry
    cl13_d_t d[C13_ND]; cl13_g_t g[C13_NG];
    int xday, xwin, xn; char xmap[32]; cl13_x_t x[C13_NX];       // section 5: the raid on day xday, its map / verdict, its players
    int ok, week, dow, morale, alive, worst, done, won, lost, maxsz; char fk, label[28];
    int np, nj, nl, ns, nm, nt, nu;
    cl13_p_t p[C13_NP]; cl13_j_t j[C13_NJ]; cl13_l_t l[C13_NL]; cl13_s_t s[C13_NS]; cl13_m_t m[C13_NM]; cl13_t_t t[C13_NT]; cl13_u_t u[C13_NU];
} cl13_t;

static void cl13_cp(char *d, size_t n, const char *s) { if (!n) return; size_t l = strlen(s); if (l >= n) l = n - 1; memcpy(d, s, l); d[l] = 0; }
// split a line in place at TABs: f[i] = the fields (empty ones too); returns the count
static int cl13_fields(char *line, char **f, int max) {
    int n = 0;
    char *p = line;
    while (n < max) {
        f[n++] = p;
        char *t = strchr(p, '\t');
        if (!t) break;
        *t = 0; p = t + 1;
    }
    return n;
}
static void cl13_nums(const char *s, int *o, int n) {
    for (int i = 0; i < n; i++) { char *e; o[i] = (int)strtol(s, &e, 10); s = *e ? e + 1 : e; }
}
// parse one reply (section sec) into d; the text is modified. Returns the number of rows read (-1 = not a valid reply).
static int cl13_parse(cl13_t *d, int sec, char *text) {
    if (sec < 1 || sec > 6) return -1;
    char *f[24];
    int rows = 0;
    if (!text[0]) { d->have[sec] = 1; if (sec == 5) { d->xday = 0; d->xn = 0; } else if (sec == 6) { d->nd = d->ng = 0; d->jweek = d->jtop = 0; } else d->ok = 0; return 0; }          // an empty reply: no clan / no story (section 5: an older daemon)
    if (sec == 1) d->np = 0; else if (sec == 2) d->nj = d->nl = 0; else if (sec == 4) d->nu = 0; else if (sec == 5) { d->xn = 0; d->xday = 0; } else if (sec == 6) { d->nd = d->ng = 0; d->jweek = d->jtop = 0; } else d->ns = d->nm = d->nt = 0;
    int got_h = 0;
    for (char *ln = text; ln && *ln;) {
        char *nl = strchr(ln, '\n');
        if (nl) *nl = 0;
        int nf = cl13_fields(ln, f, 24);
        char k = f[0][0];
        if (k == 'X' && nf >= 5 && sec == 5) {
            d->xday = atoi(f[1]); cl13_cp(d->xmap, sizeof d->xmap, f[2]); d->xwin = f[3][0] == '1' ? 1 : f[3][0] == '0' ? 0 : -1;
            rows++;
        } else if (k == 'Q' && nf >= 12 && sec == 5 && d->xn < C13_NX) {
            cl13_x_t *x = &d->x[d->xn++];
            memset(x, 0, sizeof *x);
            cl13_cp(x->name, sizeof x->name, f[1]); x->team = atoi(f[2]); x->me = atoi(f[3]) != 0; x->kills = atoi(f[4]); x->downs = atoi(f[5]); x->deaths = atoi(f[6]);
            x->revives = atoi(f[7]); x->execs = atoi(f[8]); x->heads = atoi(f[9]); x->parts = atoi(f[10]); x->left = atoi(f[11]) != 0; x->head = nf >= 13 ? atoi(f[12]) : 0;
            x->rk = nf >= 15 ? atoi(f[13]) : -1; x->wk = nf >= 15 ? atoi(f[14]) : 0;       // 2013 rank symbol + weeks survived in total
            rows++;
        } else if (k == 'K' && nf >= 3 && sec == 6) {
            d->jweek = atoi(f[1]); d->jtop = atoi(f[2]);
            rows++;
        } else if (k == 'D' && nf >= 16 && sec == 6 && d->nd < C13_ND) {
            cl13_d_t *e = &d->d[d->nd++];
            memset(e, 0, sizeof *e);
            e->day = atoi(f[1]); e->dow = atoi(f[2]); e->week = atoi(f[3]); e->id = atol(f[4]); cl13_cp(e->title, sizeof e->title, f[5]); cl13_cp(e->tone, sizeof e->tone, f[6]);
            cl13_cp(e->map, sizeof e->map, f[7]); e->win = f[8][0] == '1' ? 1 : f[8][0] == '0' ? 0 : -1; e->sup = atoi(f[9]); e->need = atoi(f[10]);
            e->h = atoi(f[11]); e->u = atoi(f[12]); e->s = atoi(f[13]); e->dn = atoi(f[14]); e->fresh = atoi(f[15]) != 0;
            rows++;
        } else if (k == 'G' && nf >= 4 && sec == 6 && d->ng < C13_NG) {
            cl13_g_t *g = &d->g[d->ng++];
            g->day = atoi(f[1]); cl13_cp(g->cap, sizeof g->cap, f[2]); cl13_cp(g->text, sizeof g->text, f[3]);
            rows++;
        } else if (k == 'H' && nf >= 8) {
            d->done = nf >= 12 ? atoi(f[8]) : 0; d->won = nf >= 12 ? atoi(f[9]) : 0; d->lost = nf >= 12 ? atoi(f[10]) : 0; d->maxsz = nf >= 12 ? atoi(f[11]) : 0;
            d->ok = 1; d->week = atoi(f[1]); d->dow = atoi(f[2]); d->fk = f[3][0]; d->morale = atoi(f[4]); cl13_cp(d->label, sizeof d->label, f[5]);
            d->alive = atoi(f[6]); d->worst = atoi(f[7]); got_h = 1;
        } else if (k == 'P' && nf >= 12 && sec == 1 && d->np < C13_NP) {
            cl13_p_t *p = &d->p[d->np++];
            memset(p, 0, sizeof *p);
            cl13_cp(p->name, sizeof p->name, f[1]); cl13_cp(p->role, sizeof p->role, f[2]); p->st = f[3][0]; cl13_cp(p->stw, sizeof p->stw, f[4]);
            cl13_cp(p->expr, sizeof p->expr, f[5]); cl13_cp(p->pid, sizeof p->pid, f[6]); cl13_cp(p->bond, sizeof p->bond, f[7]); cl13_cp(p->bondty, sizeof p->bondty, f[8]);
            cl13_cp(p->tag, sizeof p->tag, f[9]); cl13_cp(p->lately, sizeof p->lately, f[10]); cl13_cp(p->icon, sizeof p->icon, f[11]);
            rows++;
        } else if (k == 'J' && nf >= 13 && sec == 2 && d->nj < C13_NJ) {
            cl13_j_t *j = &d->j[d->nj++];
            memset(j, 0, sizeof *j);
            j->id = atol(f[1]); cl13_cp(j->cap, sizeof j->cap, f[2]); cl13_cp(j->title, sizeof j->title, f[3]); cl13_cp(j->body, sizeof j->body, f[4]);
            cl13_cp(j->tone, sizeof j->tone, f[5]); cl13_cp(j->arc, sizeof j->arc, f[6]); j->step = atoi(f[7]); j->day = atoi(f[8]); j->week = atoi(f[9]);
            cl13_cp(j->pid, sizeof j->pid, f[10]); cl13_cp(j->who, sizeof j->who, f[11]); j->fresh = atoi(f[12]) != 0; j->more = nf >= 14 ? atoi(f[13]) : 0;
            rows++;
        } else if (k == 'L' && nf >= 5 && sec == 2 && d->nl < C13_NL) {
            cl13_l_t *l = &d->l[d->nl++];
            memset(l, 0, sizeof *l);
            l->card = atol(f[1]); l->day = atoi(f[2]); cl13_cp(l->text, sizeof l->text, f[3]); l->fresh = atoi(f[4]) != 0;
            rows++;
        } else if (k == 'S' && nf >= 5 && sec == 3 && d->ns < C13_NS) {
            cl13_s_t *s = &d->s[d->ns++];
            cl13_cp(s->label, sizeof s->label, f[1]); s->stock = atoi(f[2]); s->days = atoi(f[3]); s->need = atoi(f[4]);
            rows++;
        } else if (k == 'U' && nf >= 7 && sec == 4 && d->nu < C13_NU) {
            cl13_u_t *u = &d->u[d->nu++];
            memset(u, 0, sizeof *u);
            cl13_cp(u->name, sizeof u->name, f[1]); cl13_cp(u->role, sizeof u->role, f[2]); cl13_cp(u->state, sizeof u->state, f[3]); cl13_cp(u->stw, sizeof u->stw, f[4]);
            cl13_cp(u->pid, sizeof u->pid, f[5]); cl13_cp(u->line, sizeof u->line, f[6]);
            rows++;
        } else if (k == 'M' && nf >= 9 && sec == 3 && d->nm < C13_NM) {
            cl13_m_t *m = &d->m[d->nm++];
            memset(m, 0, sizeof *m);
            m->day = atoi(f[1]); cl13_cp(m->map, sizeof m->map, f[2]); m->win = f[3][0] == '1' ? 1 : f[3][0] == '0' ? 0 : -1; m->sup = atoi(f[4]); m->need = atoi(f[5]);
            m->fresh = atoi(f[6]) != 0; cl13_nums(f[7], m->got, 5); cl13_nums(f[8], m->needc, 5);
            rows++;
        } else if (k == 'T' && nf >= 6 && sec == 3 && d->nt < C13_NT) {
            cl13_t_t *t = &d->t[d->nt++];
            t->day = atoi(f[1]); cl13_cp(t->qty, sizeof t->qty, f[2]); cl13_cp(t->name, sizeof t->name, f[3]); cl13_cp(t->icon, sizeof t->icon, f[4]); t->fresh = atoi(f[5]) != 0;
            rows++;
        }
        ln = nl ? nl + 1 : NULL;
    }
    if (!got_h) return -1;
    d->have[sec] = 1;
    return rows;
}

// ---- the journal list: one card per story (arc), its newest step; rows without an arc are single cards. idx[] = indices into d->j in order (newest first)
static int cl13_cards(const cl13_t *d, int *idx, int max) {
    int n = 0;
    for (int i = 0; i < d->nj && n < max; i++) {
        int dup = 0;
        if (d->j[i].arc[0]) for (int k = 0; k < n; k++) if (!strcmp(d->j[idx[k]].arc, d->j[i].arc)) { dup = 1; break; }
        if (!dup) idx[n++] = i;
    }
    return n;
}
// the steps of card j (oldest -> newest), at most max (the newest ones); a card without an arc is its own single step
static int cl13_thread(const cl13_t *d, int j, int *idx, int max) {
    int all[C13_NJ], n = 0;
    if (j < 0 || j >= d->nj) return 0;
    if (!d->j[j].arc[0]) { idx[0] = j; return 1; }
    for (int i = d->nj - 1; i >= 0; i--) if (!strcmp(d->j[i].arc, d->j[j].arc)) all[n++] = i;      // rows are newest first: walking back = oldest first
    // by step number (a stable insertion sort: equal steps keep the row order)
    for (int a = 1; a < n; a++) { int v = all[a], b = a - 1; while (b >= 0 && d->j[all[b]].step > d->j[v].step) { all[b + 1] = all[b]; b--; } all[b + 1] = v; }
    int from = n > max ? n - max : 0, o = 0;
    for (int i = from; i < n; i++) idx[o++] = all[i];
    return o;
}

// ---- the journal's week pages: the entries of one week (indices into d->d, oldest first) and the paragraphs of one day (indices into d->g, in reading order)
static int cl13_week_rows(const cl13_t *d, int week, int *idx, int max) {
    int n = 0;
    for (int i = 0; i < d->nd && n < max; i++) if (d->d[i].week == week) idx[n++] = i;
    return n;
}
static int cl13_day_paras(const cl13_t *d, int day, int *idx, int max) {
    int n = 0;
    for (int i = 0; i < d->ng && n < max; i++) if (d->g[i].day == day) idx[n++] = i;
    return n;
}

// ---- clip text into a box: greedy word wrap with est(text, pt) = estimated width; at most maxlines lines, the cut ends in "..."
typedef float (*cl13_est_fn)(const char *, float);
static void cl13_clip(char *dst, size_t n, const char *src, float boxw, float pt, int maxlines, cl13_est_fn est) {
    if (!n) return;
    dst[0] = 0;
    if (!src || !*src) return;
    char line[256], word[128];
    size_t o = 0, ll = 0;
    int lines = 1, cut = 0;
    float sp = est(" ", pt);
    float lw = 0.0f;
    line[0] = 0;
    const char *p = src;
    while (*p && !cut) {
        while (*p == ' ') p++;
        size_t wl = 0;
        while (*p && *p != ' ' && wl < sizeof word - 1) word[wl++] = *p++;
        word[wl] = 0;
        if (!wl) break;
        float ww = est(word, pt);
        if (ll && lw + sp + ww > boxw) {                       // a new line
            if (lines >= maxlines) { cut = 1; break; }
            lines++;
            if (o + 1 < n) dst[o++] = ' ';
            ll = 0; lw = 0.0f; line[0] = 0;
        }
        if (o + wl + 5 >= n) { cut = 1; break; }
        if (ll) { dst[o++] = ' '; lw += sp; line[ll++] = ' '; }
        memcpy(dst + o, word, wl); o += wl;
        if (ll + wl < sizeof line - 1) { memcpy(line + ll, word, wl); ll += wl; line[ll] = 0; }
        lw += ww;
    }
    dst[o] = 0;
    if (cut || *p) {                                           // text was left over: end the last line with "..." (a word dropped until the dots fit)
        char tmp[300];
        for (;;) {
            snprintf(tmp, sizeof tmp, "%s...", line);
            if (est(tmp, pt) <= boxw || !ll) break;
            char *sp_ = strrchr(line, ' ');
            if (!sp_) { ll = 0; line[0] = 0; break; }
            size_t keep = (size_t)(sp_ - line);
            dst[o - (ll - keep)] = 0; o -= ll - keep;
            line[keep] = 0; ll = keep;
        }
        while (o > 0 && (dst[o - 1] == ' ' || dst[o - 1] == ',' || dst[o - 1] == ';')) dst[--o] = 0;
        if (o + 4 < n) { memcpy(dst + o, "...", 4); }
    }
}

// ---- wrap text for a box whose line count must be KNOWN (the journal's reading pane stacks its paragraphs): greedy word wrap by est() like cl13_clip, but the lines
// are joined by a line break, so the engine never wraps them a second time (boxw = the width the caller allows, already under the widget's). A line break in the
// source ends the line, two leave a blank line. At most maxlines lines, the cut ends in "...". Returns the number of lines written.
static int cl13_wrap(char *dst, size_t n, const char *src, float boxw, float pt, int maxlines, cl13_est_fn est) {
    if (!n) return 0;
    dst[0] = 0;
    if (!src || !*src || maxlines < 1) return 0;
    char line[320], word[128];
    size_t o = 0, ll = 0;
    int lines = 1, cut = 0;
    float sp = est(" ", pt), lw = 0.0f;
    line[0] = 0;
    const char *p = src;
    while (*p && !cut) {
        int brk = 0;
        while (*p == ' ' || *p == '\n') { if (*p == '\n') brk++; p++; }
        if (!*p) break;
        size_t wl = 0;
        while (*p && *p != ' ' && *p != '\n' && wl < sizeof word - 1) word[wl++] = *p++;
        word[wl] = 0;
        float ww = est(word, pt);
        int nl = !o ? 0 : brk > 1 ? 2 : brk == 1 ? 1 : (ll && lw + sp + ww > boxw) ? 1 : 0;
        if (nl) {
            if (lines + nl > maxlines || o + (size_t)nl + 5 >= n) { cut = 1; break; }
            for (int k = 0; k < nl; k++) dst[o++] = '\n';
            lines += nl; ll = 0; lw = 0.0f; line[0] = 0;
        }
        if (o + wl + 6 >= n) { cut = 1; break; }
        if (ll) { dst[o++] = ' '; lw += sp; if (ll < sizeof line - 1) line[ll++] = ' '; }
        memcpy(dst + o, word, wl); o += wl;
        if (ll + wl < sizeof line - 1) { memcpy(line + ll, word, wl); ll += wl; line[ll] = 0; }
        lw += ww;
    }
    dst[o] = 0;
    if (cut) {                                                 // text was left over: the last line ends in "..." (words dropped until the dots fit)
        char tmp[340];
        for (;;) {
            snprintf(tmp, sizeof tmp, "%s...", line);
            if (est(tmp, pt) <= boxw || !ll) break;
            char *sp_ = strrchr(line, ' ');
            if (!sp_) { o -= ll; dst[o] = 0; ll = 0; line[0] = 0; break; }
            size_t keep = (size_t)(sp_ - line);
            o -= ll - keep; dst[o] = 0;
            line[keep] = 0; ll = keep;
        }
        while (o > 0 && (dst[o - 1] == ' ' || dst[o - 1] == ',' || dst[o - 1] == ';')) dst[--o] = 0;
        if (o + 4 < n) memcpy(dst + o, "...", 4);
    }
    return lines;
}

// ---- NEW markers: the highest journal id / raid day seen (clan13.c keeps them in t2r-clan13-seen.txt)
typedef struct { long jid; int day; } cl13_seen_t;
static int cl13_seen_parse(const char *txt, cl13_seen_t *s) { s->jid = 0; s->day = 0; return txt && sscanf(txt, "%ld %d", &s->jid, &s->day) >= 1; }

// ---- MATCH STATS: the one headline award of every player ("MOST <X>", a role word, a face for it) and the two team sections. Pure, tested in tests/clan13_test.c.
// Stats: 0 DOWNS (enemies downed), 1 EXECUTIONS, 2 REVIVES, 3 HEADSHOTS, 4 PARTS, 5 DEATHS. A player LEADS a stat when he is its only holder of the match's top value (> 0; deaths: >= 2).
// Pass 1 hands the rarer stats out first (executions, revives, headshots, deaths, downs, parts) - a player gets at most one, so the list reads like different people did different things.
// Pass 2: whoever has none gets the stat he is best at relative to the match's top (deaths and parts weigh a little less); nothing reported / all zero = no award (stat -1).
#define C13_NAW 6
typedef struct { int stat, lead; } cl13_aw_t;
static int cl13_xv(const cl13_x_t *x, int s) { return s == 0 ? x->kills : s == 1 ? x->execs : s == 2 ? x->revives : s == 3 ? x->heads : s == 4 ? x->parts : x->deaths; }
static void cl13_awards(const cl13_x_t *x, int n, cl13_aw_t *aw) {
    static const int ORDER[C13_NAW] = {1, 2, 3, 5, 0, 4};
    static const float WT[C13_NAW] = {1.0f, 1.0f, 1.0f, 1.0f, 0.9f, 0.7f};     // (index = stat)
    int top[C13_NAW] = {0};
    for (int i = 0; i < n; i++) { aw[i].stat = -1; aw[i].lead = 0; for (int s = 0; s < C13_NAW; s++) if (cl13_xv(&x[i], s) > top[s]) top[s] = cl13_xv(&x[i], s); }
    for (int k = 0; k < C13_NAW; k++) {
        int s = ORDER[k], who = -1, holders = 0;
        if (top[s] < (s == 5 ? 2 : 1)) continue;
        for (int i = 0; i < n; i++) if (cl13_xv(&x[i], s) == top[s]) { holders++; who = i; }
        if (holders == 1 && aw[who].stat < 0) { aw[who].stat = s; aw[who].lead = 1; }
    }
    for (int i = 0; i < n; i++) {
        if (aw[i].stat >= 0) continue;
        float best = 0.0f;
        for (int k = 0; k < C13_NAW; k++) {
            int s = ORDER[k], v = cl13_xv(&x[i], s);
            if (v <= 0 || top[s] <= 0) continue;
            float r = (float)v / (float)top[s] * WT[s];
            if (r > best + 0.0001f) { best = r; aw[i].stat = s; }
        }
    }
}
static const char *cl13_aw_word(int s) { static const char *const W[C13_NAW] = {"DOWNS", "EXECUTIONS", "REVIVES", "HEADSHOTS", "PARTS", "DEATHS"}; return s >= 0 && s < C13_NAW ? W[s] : ""; }
static const char *cl13_aw_role(int s, int lead) {
    static const char *const L[C13_NAW] = {"KILLER", "EXECUTIONER", "MEDIC", "MARKSMAN", "RAIDER", "CANNON FODDER"};
    static const char *const A[C13_NAW] = {"FIGHTER", "FINISHER", "SUPPORT", "SHOT", "SCAVENGER", "ROOKIE"};
    return s < 0 || s >= C13_NAW ? "SURVIVOR" : lead ? L[s] : A[s];
}
// the face of an award (the pool's expressions: neutral happy dead angry perk = the calm smirk); only a stat's leader makes the face
static const char *cl13_aw_expr(int s, int lead) { return !lead ? "neutral" : s == 0 || s == 1 ? "angry" : s == 2 || s == 3 ? "perk" : s == 4 ? "happy" : s == 5 ? "dead" : "neutral"; }
// which of the two sections a player stands in: ours first (mine = the asker's team, -1 = unknown: team 0 first, headings TEAM 1 / TEAM 2)
static int cl13_sect(const cl13_x_t *x, int mine) { return mine >= 0 ? (x->team == mine ? 0 : 1) : (x->team == 1 ? 1 : 0); }
// order the player indexes of one section: most parts first, then most downs (unreported = -1 last)
static int cl13_order(const cl13_x_t *x, int n, int mine, int sect, int *idx) {
    int m = 0;
    for (int i = 0; i < n; i++) if (cl13_sect(&x[i], mine) == sect) idx[m++] = i;
    for (int a = 1; a < m; a++) {
        int t = idx[a], b = a;
        while (b > 0 && (x[idx[b - 1]].parts < x[t].parts || (x[idx[b - 1]].parts == x[t].parts && x[idx[b - 1]].kills < x[t].kills))) { idx[b] = idx[b - 1]; b--; }
        idx[b] = t;
    }
    return m;
}

#endif
