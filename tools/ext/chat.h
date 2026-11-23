// chat.h - the pure core of the in-game chat (chat.c): text cleaning, the peer packet, the party chat reply reader. No engine calls (tests compile it alone).
#ifndef CHAT_H
#define CHAT_H
#include <stdint.h>
#include <string.h>
#include <stdlib.h>
#include "friends13.h"                       // fj_* (the small JSON reader)

#define CH_MAXC 200                          // characters of one line (= social.py MSG_LEN)
#define CH_BUF 420                           // bytes of one line (UTF-8; = the daemon's 0xD8 argument cap)
#define CH_PKT_VER 1
enum { CH_MATCH, CH_TEAM, CH_PARTY, CH_NCH };

// one UTF-8 character at s (n bytes left) -> code point; *len = its bytes (a broken sequence = 1 byte, U+FFFD)
static uint32_t ch_u8(const unsigned char *s, size_t n, int *len) {
    uint32_t c = s[0];
    int l = c < 0x80 ? 1 : c >= 0xF0 ? 4 : c >= 0xE0 ? 3 : c >= 0xC0 ? 2 : 0;
    if (!l || (size_t)l > n) { *len = 1; return 0xFFFD; }
    if (l == 1) { *len = 1; return c; }
    c &= 0x3F >> (l - 1);
    for (int i = 1; i < l; i++) { if ((s[i] & 0xC0) != 0x80) { *len = 1; return 0xFFFD; } c = (c << 6) | (s[i] & 0x3F); }
    *len = l;
    return c;
}
static int ch_put8(char *o, size_t cap, size_t *k, uint32_t cp) {
    char b[4]; int l;
    if (cp < 0x80) { b[0] = (char)cp; l = 1; }
    else if (cp < 0x800) { b[0] = (char)(0xC0 | cp >> 6); b[1] = (char)(0x80 | (cp & 63)); l = 2; }
    else { b[0] = (char)(0xE0 | cp >> 12); b[1] = (char)(0x80 | (cp >> 6 & 63)); b[2] = (char)(0x80 | (cp & 63)); l = 3; }
    if (*k + (size_t)l >= cap) return 0;
    memcpy(o + *k, b, (size_t)l); *k += (size_t)l;
    return 1;
}
// a character the chat draws: the nametag font's letters (Latin, below U+0250; Polish etc. stay), no control characters, never '<' '>' (the text widgets read
// markup; a stray '<' in a drawn name crashed the game, nametaglt-1122) and never '|' (the notice wire's separator)
static int ch_ok(uint32_t cp) { return cp >= 0x20 && cp < 0x250 && cp != 0x7F && !(cp >= 0x80 && cp < 0xA0) && cp != '<' && cp != '>' && cp != '|'; }
// in (n bytes, not necessarily NUL ended) -> out: drawable characters only, runs of spaces made one, trimmed, at most maxc characters. Returns the characters kept.
static int ch_clean(const char *in, size_t n, char *out, size_t cap, int maxc) {
    size_t k = 0; int nc = 0, sp = 0;
    const unsigned char *s = (const unsigned char *)in;
    if (cap) out[0] = 0;
    while (n && *s) {
        int l; uint32_t cp = ch_u8(s, n, &l);
        s += l; n -= (size_t)l;
        if (cp == '\t' || cp == '\n' || cp == '\r') cp = ' ';
        if (cp == 0x2018 || cp == 0x2019) cp = '\''; else if (cp == 0x201C || cp == 0x201D) cp = '"'; else if (cp == 0x2013 || cp == 0x2014) cp = '-';
        if (!ch_ok(cp)) continue;
        if (cp == ' ') { sp = nc > 0; continue; }
        if (nc >= maxc) break;
        if (sp) { if (nc + 1 >= maxc || !ch_put8(out, cap, &k, ' ')) break; nc++; sp = 0; }
        if (!ch_put8(out, cap, &k, cp)) break;
        nc++;
    }
    if (cap) out[k] = 0;
    return nc;
}
// The slur filter. A word is a run of letters, digits, '@', '$' and UTF-8 letters. It is lowercased, and look-alike
// digits / symbols are read as letters (0 o, 1 i, 3 e, 4 a, 5 s, 7 t, @ a, $ s). The word is checked as typed (CHB_RAW entries) and with doubled letters made one
// ("niiigaa" -> "niga", "faggot" -> "fagot"; the other entries). A word that matches is drawn as one '*' per character. chat.c applies it to every line it shows
// (ours, received, party) and friends13.c to the friend messages, so lines from older clients are filtered too.
enum { CHB_WORD, CHB_START, CHB_ANY, CHB_RAW = 4 };          // CHB_WORD: the whole word (a plural -s / -es too); CHB_START: the word starts with it; CHB_ANY: anywhere
typedef struct { const char *w; int mode; } ch_bad_t;
static const ch_bad_t CH_BAD[] = {
    {"nigg", CHB_START | CHB_RAW}, {"coon", CHB_WORD | CHB_RAW},
    {"niga", CHB_START}, {"fag", CHB_START}, {"dyke", CHB_WORD}, {"trany", CHB_START}, {"tranie", CHB_START}, {"retard", CHB_START}, {"chink", CHB_WORD},
    {"gok", CHB_WORD}, {"spic", CHB_WORD}, {"spick", CHB_WORD}, {"kike", CHB_WORD}, {"wetback", CHB_START}, {"beaner", CHB_START}, {"paki", CHB_WORD},
    {"raghead", CHB_ANY}, {"towelhead", CHB_ANY}, {"czarnuch", CHB_START}, {"ciota", CHB_WORD},
};
static int ch_word_ch(unsigned char c) { return (c >= 'a' && c <= 'z') || (c >= 'A' && c <= 'Z') || (c >= '0' && c <= '9') || c == '@' || c == '$' || c >= 0x80; }
static char ch_leet(unsigned char c) {
    if (c >= 'A' && c <= 'Z') return (char)(c + 32);
    switch (c) { case '0': return 'o'; case '1': return 'i'; case '3': return 'e'; case '4': return 'a'; case '5': return 's'; case '7': return 't';
                 case '@': return 'a'; case '$': return 's'; default: return (char)c; }
}
static int ch_bad_hit(const char *t, const ch_bad_t *b) {
    size_t n = strlen(t), wl = strlen(b->w);
    switch (b->mode & 3) {
    case CHB_WORD: return !strncmp(t, b->w, wl) && (n == wl || (n == wl + 1 && t[wl] == 's') || (n == wl + 2 && t[wl] == 'e' && t[wl + 1] == 's'));
    case CHB_START: return !strncmp(t, b->w, wl);
    default: return strstr(t, b->w) != NULL;
    }
}
static int ch_bad_word(const char *w, size_t n) {          // 1 = the word w (n bytes) is a slur
    char raw[64], col[64]; size_t k = 0, c = 0;
    if (n >= sizeof raw) return 0;
    for (size_t i = 0; i < n; i++) { char x = ch_leet((unsigned char)w[i]); raw[k++] = x; if (!c || col[c - 1] != x) col[c++] = x; }
    raw[k] = 0; col[c] = 0;
    for (size_t i = 0; i < sizeof CH_BAD / sizeof CH_BAD[0]; i++) if (ch_bad_hit((CH_BAD[i].mode & CHB_RAW) ? raw : col, &CH_BAD[i])) return 1;
    return 0;
}
// in place; returns the words starred
static int ch_censor(char *s) {
    char o[CH_BUF + 96]; size_t k = 0; int hits = 0;
    size_t n = strlen(s);
    if (n >= sizeof o) return 0;
    for (size_t i = 0; i < n;) {
        if (!ch_word_ch((unsigned char)s[i])) { o[k++] = s[i++]; continue; }
        size_t j = i; while (j < n && ch_word_ch((unsigned char)s[j])) j++;
        if (ch_bad_word(s + i, j - i)) { for (size_t q = i; q < j; q++) if (((unsigned char)s[q] & 0xC0) != 0x80) o[k++] = '*'; hits++; }
        else { memcpy(o + k, s + i, j - i); k += j - i; }
        i = j;
    }
    o[k] = 0;
    if (hits) memcpy(s, o, k + 1);
    return hits;
}
// the peer packet (MSG_CHAT): [u8 ver][u8 chan 0 match / 1 team][u16 seq][u16 bytes][text]; returns the packet length (0 = nothing to send)
static int ch_pkt_build(uint8_t *o, size_t cap, int chan, uint16_t seq, const char *text) {
    size_t tl = strlen(text);
    if (tl > CH_BUF - 1) { tl = CH_BUF - 1; while (tl > 0 && ((unsigned char)text[tl] & 0xC0) == 0x80) tl--; }
    if (!tl || cap < 6 + tl || (chan != CH_MATCH && chan != CH_TEAM)) return 0;
    o[0] = CH_PKT_VER; o[1] = (uint8_t)chan; o[2] = (uint8_t)seq; o[3] = (uint8_t)(seq >> 8); o[4] = (uint8_t)tl; o[5] = (uint8_t)(tl >> 8);
    memcpy(o + 6, text, tl);
    return (int)(6 + tl);
}
// a received packet -> chan / seq / the cleaned text; 0 = malformed
static int ch_pkt_parse(const uint8_t *b, size_t len, int *chan, uint16_t *seq, char *out, size_t cap) {
    size_t tl = b && len >= 6 ? (size_t)(b[4] | b[5] << 8) : 0;
    if (!b || len < 7 || b[0] != CH_PKT_VER || b[1] > CH_TEAM || !tl || tl > CH_BUF || tl + 6 > len) return 0;
    *chan = b[1]; *seq = (uint16_t)(b[2] | b[3] << 8);
    return ch_clean((const char *)b + 6, tl, out, cap, CH_MAXC) > 0;
}
// the party chat part of an op 0xD9 reply (social.py S_PCHAT / S_PSAY): {"pchat":{"lines":[{"id","name","t","me","age"}],"last":N}}
#define CH_PL_MAX 20
typedef struct { int id, me, age; char name[40], t[CH_BUF]; } ch_pl_t;
typedef struct { int ok, has, last, n, lk; char err[16]; ch_pl_t l[CH_PL_MAX]; } ch_pchat_t;      // lk: the LOBBY channel's key (S_LSAY / S_LCHAT replies)
static int ch_pchat_parse(ch_pchat_t *d, const char *text, size_t len) {
    fj_t j = {text, text + len, 0};
    char k[16];
    memset(d, 0, sizeof *d);
    if (!fj_eat(&j, '{')) return 0;
    while (fj_key(&j, k, sizeof k)) {
        if (!strcmp(k, "ok")) d->ok = fj_int(&j);
        else if (!strcmp(k, "lk")) d->lk = fj_int(&j);
        else if (!strcmp(k, "err")) fj_str(&j, d->err, sizeof d->err);
        else if (!strcmp(k, "pchat")) {
            char k2[16];
            if (!fj_eat(&j, '{')) { j.bad = 1; break; }
            d->has = 1;
            while (fj_key(&j, k2, sizeof k2)) {
                if (!strcmp(k2, "last")) d->last = fj_int(&j);
                else if (!strcmp(k2, "lines")) {
                    if (!fj_eat(&j, '[')) { j.bad = 1; break; }
                    while (fj_more(&j)) {
                        ch_pl_t t; char k3[16], raw[CH_BUF];
                        memset(&t, 0, sizeof t); raw[0] = 0;
                        if (!fj_eat(&j, '{')) { j.bad = 1; break; }
                        while (fj_key(&j, k3, sizeof k3)) {
                            if (!strcmp(k3, "id")) t.id = fj_int(&j);
                            else if (!strcmp(k3, "me")) t.me = fj_int(&j);
                            else if (!strcmp(k3, "age")) t.age = fj_int(&j);
                            else if (!strcmp(k3, "name")) { char nm[64]; fj_str(&j, nm, sizeof nm); ch_clean(nm, strlen(nm), t.name, sizeof t.name, 24); }
                            else if (!strcmp(k3, "t")) fj_str(&j, raw, sizeof raw);
                            else fj_skip(&j);
                            if (j.bad) break;
                        }
                        ch_clean(raw, strlen(raw), t.t, sizeof t.t, CH_MAXC);
                        if (t.t[0] && d->n < CH_PL_MAX) d->l[d->n++] = t;
                        if (j.bad) break;
                    }
                } else fj_skip(&j);
                if (j.bad) break;
            }
        } else fj_skip(&j);
        if (j.bad) return 0;
    }
    return !j.bad;
}
#endif
