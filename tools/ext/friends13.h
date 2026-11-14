// friends13.h - the pure core of the in-game FRIENDS / PARTY panel (friends13.c): a small JSON reader for the daemon's op 0xD9 reply (tools/social.py _state) and the
// list the panel shows. No engine calls: tests/friends13_test.c compiles it alone against the daemon's real output.
#ifndef FRIENDS13_H
#define FRIENDS13_H
#include <stdio.h>
#include <string.h>
#include <stdlib.h>
#include <stdint.h>

#define FR_NF 100
#define FR_NR 30
#define FR_NPI 8
#define FR_NM 8
typedef struct { char id[40], name[36], status[12]; int party; } fr_f_t;
typedef struct { char id[40], name[36]; } fr_r_t;
typedef struct { char id[40], name[36], status[12]; int leader, ready, me; } fr_m_t;
typedef struct {
    int ok; char err[16];
    char me_id[40], me_name[36];
    int nf, ni, no, npi, nm, has_party, me_leader, pmax, searching, lsearch;
    fr_f_t f[FR_NF];
    fr_r_t in[FR_NR], out[FR_NR], pinv[FR_NPI];
    fr_m_t m[FR_NM];
} fr13_t;

typedef struct { const char *p, *e; int bad; } fj_t;
static void fj_ws(fj_t *j) { while (j->p < j->e && (*j->p == ' ' || *j->p == '\n' || *j->p == '\t' || *j->p == '\r')) j->p++; }
static int fj_eat(fj_t *j, char c) { fj_ws(j); if (j->p < j->e && *j->p == c) { j->p++; return 1; } return 0; }
static void fj_put8(char *o, size_t n, size_t *k, unsigned cp) {
    char b[4]; int l;
    if (cp < 0x80) { b[0] = (char)cp; l = 1; }
    else if (cp < 0x800) { b[0] = (char)(0xC0 | cp >> 6); b[1] = (char)(0x80 | (cp & 63)); l = 2; }
    else { b[0] = (char)(0xE0 | cp >> 12); b[1] = (char)(0x80 | (cp >> 6 & 63)); b[2] = (char)(0x80 | (cp & 63)); l = 3; }
    if (*k + l < n) { memcpy(o + *k, b, l); *k += l; }
}
// a string value into out (cut at a character boundary when too long); 0 when the value is no string
static int fj_str(fj_t *j, char *out, size_t n) {
    size_t k = 0;
    if (out && n) out[0] = 0;
    fj_ws(j);
    if (j->p >= j->e || *j->p != '"') { j->bad = 1; return 0; }
    j->p++;
    while (j->p < j->e && *j->p != '"') {
        unsigned cp = (unsigned char)*j->p++;
        if (cp == '\\' && j->p < j->e) {
            char c = *j->p++;
            if (c == 'n') cp = '\n'; else if (c == 't') cp = '\t';
            else if (c == 'u' && j->e - j->p >= 4) { char h[5] = {j->p[0], j->p[1], j->p[2], j->p[3], 0}; cp = (unsigned)strtoul(h, NULL, 16); j->p += 4; if (cp >= 0xD800 && cp < 0xE000) cp = '?'; }
            else cp = (unsigned char)c;
            if (out) fj_put8(out, n, &k, cp);
            continue;
        }
        if (out && k + 1 < n) out[k++] = (char)cp;
    }
    if (j->p < j->e) j->p++; else j->bad = 1;
    if (out && n) {
        out[k] = 0;
        size_t q = k;                                         // never half a UTF-8 sequence at the cut
        while (q > 0 && ((unsigned char)out[q - 1] & 0xC0) == 0x80) q--;
        if (q > 0) { unsigned char lead = (unsigned char)out[q - 1]; size_t need = lead >= 0xF0 ? 4 : lead >= 0xE0 ? 3 : lead >= 0xC0 ? 2 : 1; if (k - (q - 1) < need) out[q - 1] = 0; }
    }
    return 1;
}
static int fj_int(fj_t *j) {                                  // number / true / false / null as an int
    fj_ws(j);
    if (j->p >= j->e) { j->bad = 1; return 0; }
    if (!strncmp(j->p, "true", 4 > j->e - j->p ? (size_t)(j->e - j->p) : 4)) { j->p += 4; return 1; }
    if (!strncmp(j->p, "false", 5 > j->e - j->p ? (size_t)(j->e - j->p) : 5)) { j->p += 5; return 0; }
    if (!strncmp(j->p, "null", 4 > j->e - j->p ? (size_t)(j->e - j->p) : 4)) { j->p += 4; return 0; }
    char *q; long v = strtol(j->p, &q, 10);
    if (q == j->p) { j->bad = 1; return 0; }
    j->p = q;
    if (j->p < j->e && (*j->p == '.' || *j->p == 'e' || *j->p == 'E')) while (j->p < j->e && strchr("0123456789.eE+-", *j->p)) j->p++;
    return (int)v;
}
static void fj_skip(fj_t *j) {
    fj_ws(j);
    if (j->p >= j->e) { j->bad = 1; return; }
    if (*j->p == '"') { fj_str(j, NULL, 0); return; }
    if (*j->p == '{' || *j->p == '[') {
        char open = *j->p, close = open == '{' ? '}' : ']';
        j->p++;
        for (;;) {
            fj_ws(j);
            if (j->p >= j->e) { j->bad = 1; return; }
            if (*j->p == close) { j->p++; return; }
            if (*j->p == ',') { j->p++; continue; }
            if (open == '{') { fj_str(j, NULL, 0); if (!fj_eat(j, ':')) { j->bad = 1; return; } }
            fj_skip(j);
            if (j->bad) return;
        }
    }
    fj_int(j);
}
// next key of an object (the '{' already eaten): 1 = key read and the ':' eaten, 0 = '}' (eaten) or an error
static int fj_key(fj_t *j, char *key, size_t n) {
    fj_ws(j);
    if (j->p < j->e && *j->p == ',') { j->p++; fj_ws(j); }
    if (j->p >= j->e) { j->bad = 1; return 0; }
    if (*j->p == '}') { j->p++; return 0; }
    if (!fj_str(j, key, n) || !fj_eat(j, ':')) { j->bad = 1; return 0; }
    return 1;
}
static int fj_more(fj_t *j) {                                // next element of an array (the '[' eaten): 1 = one follows, 0 = ']' (eaten) or an error
    fj_ws(j);
    if (j->p < j->e && *j->p == ',') { j->p++; fj_ws(j); }
    if (j->p >= j->e) { j->bad = 1; return 0; }
    if (*j->p == ']') { j->p++; return 0; }
    return 1;
}
static void fr_rd_r(fj_t *j, fr_r_t *r) {                    // {"id":..,"name":..,..}
    char k[16];
    memset(r, 0, sizeof *r);
    if (!fj_eat(j, '{')) { j->bad = 1; return; }
    while (fj_key(j, k, sizeof k)) {
        if (!strcmp(k, "id")) fj_str(j, r->id, sizeof r->id);
        else if (!strcmp(k, "name")) fj_str(j, r->name, sizeof r->name);
        else fj_skip(j);
    }
}
static void fr_rd_f(fj_t *j, fr_f_t *f) {
    char k[16];
    memset(f, 0, sizeof *f);
    if (!fj_eat(j, '{')) { j->bad = 1; return; }
    while (fj_key(j, k, sizeof k)) {
        if (!strcmp(k, "id")) fj_str(j, f->id, sizeof f->id);
        else if (!strcmp(k, "name")) fj_str(j, f->name, sizeof f->name);
        else if (!strcmp(k, "status")) fj_str(j, f->status, sizeof f->status);
        else if (!strcmp(k, "party")) f->party = fj_int(j);
        else fj_skip(j);
    }
}
static void fr_rd_m(fj_t *j, fr_m_t *m) {
    char k[16];
    memset(m, 0, sizeof *m);
    if (!fj_eat(j, '{')) { j->bad = 1; return; }
    while (fj_key(j, k, sizeof k)) {
        if (!strcmp(k, "id")) fj_str(j, m->id, sizeof m->id);
        else if (!strcmp(k, "name")) fj_str(j, m->name, sizeof m->name);
        else if (!strcmp(k, "status")) fj_str(j, m->status, sizeof m->status);
        else if (!strcmp(k, "leader")) m->leader = fj_int(j);
        else if (!strcmp(k, "ready")) m->ready = fj_int(j);
        else if (!strcmp(k, "me")) m->me = fj_int(j);
        else fj_skip(j);
    }
}
// the whole reply (text of len bytes, not necessarily NUL ended) -> d; returns 1 on success. d->ok = the reply's "ok" (a refused write still carries the fresh state)
static int fr13_parse(fr13_t *d, const char *text, size_t len) {
    fj_t j = {text, text + len, 0};
    char k[16];
    memset(d, 0, sizeof *d);
    if (!fj_eat(&j, '{')) return 0;
    while (fj_key(&j, k, sizeof k)) {
        if (!strcmp(k, "ok")) d->ok = fj_int(&j);
        else if (!strcmp(k, "err")) fj_str(&j, d->err, sizeof d->err);
        else if (!strcmp(k, "max")) d->pmax = fj_int(&j);
        else if (!strcmp(k, "me")) {
            char k2[16];
            if (!fj_eat(&j, '{')) { j.bad = 1; break; }
            while (fj_key(&j, k2, sizeof k2)) {
                if (!strcmp(k2, "id")) fj_str(&j, d->me_id, sizeof d->me_id);
                else if (!strcmp(k2, "name")) fj_str(&j, d->me_name, sizeof d->me_name);
                else fj_skip(&j);
            }
        } else if (!strcmp(k, "friends") || !strcmp(k, "in") || !strcmp(k, "out") || !strcmp(k, "pinv")) {
            int which = k[0] == 'f' ? 0 : k[0] == 'i' ? 1 : k[0] == 'o' ? 2 : 3;
            if (!fj_eat(&j, '[')) { j.bad = 1; break; }
            while (fj_more(&j)) {
                if (which == 0) { fr_f_t t; fr_rd_f(&j, &t); if (d->nf < FR_NF) d->f[d->nf++] = t; }
                else { fr_r_t t; fr_rd_r(&j, &t); if (which == 1 && d->ni < FR_NR) d->in[d->ni++] = t; else if (which == 2 && d->no < FR_NR) d->out[d->no++] = t; else if (which == 3 && d->npi < FR_NPI) d->pinv[d->npi++] = t; }
                if (j.bad) break;
            }
        } else if (!strcmp(k, "party")) {
            fj_ws(&j);
            if (j.p < j.e && *j.p == 'n') { fj_skip(&j); continue; }                  // null: no party
            char k2[16];
            if (!fj_eat(&j, '{')) { j.bad = 1; break; }
            d->has_party = 1;
            while (fj_key(&j, k2, sizeof k2)) {
                if (!strcmp(k2, "meLeader")) d->me_leader = fj_int(&j);
                else if (!strcmp(k2, "searching")) d->searching = fj_int(&j);
                else if (!strcmp(k2, "lsearch")) d->lsearch = fj_int(&j);      // the party LEADER is searching (members' clients follow, friends13.c fr_party_tick)
                else if (!strcmp(k2, "max")) d->pmax = fj_int(&j);
                else if (!strcmp(k2, "members")) {
                    if (!fj_eat(&j, '[')) { j.bad = 1; break; }
                    while (fj_more(&j)) { fr_m_t t; fr_rd_m(&j, &t); if (d->nm < FR_NM) d->m[d->nm++] = t; if (j.bad) break; }
                } else fj_skip(&j);
                if (j.bad) break;
            }
            if (d->nm == 0) d->has_party = 0;
        } else fj_skip(&j);
        if (j.bad) return 0;
    }
    return !j.bad && d->me_id[0] != 0;
}

// ---- the right-hand list: ADD FRIEND, party invites, friend requests, friends (the daemon already sorts them online first), requests you sent
enum { FR_K_ADD, FR_K_PINV, FR_K_REQ, FR_K_FRIEND, FR_K_OUT };
typedef struct { int kind, idx; } fr_row_t;
static int fr13_rows(const fr13_t *d, fr_row_t *out, int cap) {
    int n = 0;
    if (n < cap) { out[n].kind = FR_K_ADD; out[n].idx = 0; n++; }
    for (int i = 0; i < d->npi && n < cap; i++) { out[n].kind = FR_K_PINV; out[n].idx = i; n++; }
    for (int i = 0; i < d->ni && n < cap; i++) { out[n].kind = FR_K_REQ; out[n].idx = i; n++; }
    for (int i = 0; i < d->nf && n < cap; i++) { out[n].kind = FR_K_FRIEND; out[n].idx = i; n++; }
    for (int i = 0; i < d->no && n < cap; i++) { out[n].kind = FR_K_OUT; out[n].idx = i; n++; }
    return n;
}
// the red badge on the button: friend requests + party invites waiting for the player
static int fr13_badge(const fr13_t *d) { return d->ni + d->npi; }
// the presence of a friend as the panel words it: 0 offline, 1 launcher, 2 menu, 3 searching, 4 in a match
static int fr13_presence(const char *st) { return !strcmp(st, "match") ? 4 : !strcmp(st, "search") ? 3 : !strcmp(st, "menu") ? 2 : !strcmp(st, "launcher") ? 1 : 0; }
// a friend can be invited when it is online (any presence but offline), is not in my party already, and I am the leader or have no party
static int fr13_can_invite(const fr13_t *d, const fr_f_t *f) { return fr13_presence(f->status) > 0 && !f->party && (!d->has_party || d->me_leader) && (d->nm < (d->pmax ? d->pmax : 4)); }
#endif
