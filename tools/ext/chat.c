// chat.c - in-game chat
// "the chat should only show what tab youve selected"; "enter to trigger, t is default mark button, chat should also be
// toggleable in mp settings"). Proposal + mockups: re/chat-proposal-1123. Included after gearup13.c (its keyboard catcher kt_*) and before friends13.c. Log prefix "chat:".
//
// TABS: MATCH (everyone in the match), TEAM (our team), PARTY (our party, in or out of this match). The box shows ONLY the picked tab; Tab switches while typing.
//   MATCH / TEAM lines travel peer to peer (MSG_CHAT 0xC7, chat.h ch_pkt_*), each sent 3 times (0 / 150 / 450 ms; receivers drop a seq they had); a TEAM line from a
//   player of the other team is dropped on arrival. A copy goes to the server for the report log (social.py S_MLOG). PARTY lines go through the server (S_PSAY;
//   S_PCHAT polled every 2 s in a match while we are in a party).
// HUD (to1/currency-hud, chat_widgets.add_chat_hud: chatHud > chatBox, between the lives counter and the parts counter):
//   typing  faint box, CHAT label, MATCH / TEAM / PARTY (the picked one underlined in its colour), the tab's last 5 lines, the typing line, the key hint;
//   idle    a fainter, smaller box with the tab's newest 3 lines; it fades out 8 s after the last line (a new line brings it back).
// ESC menu (to1/pause-menu, chat_widgets.add_pause_chat: pzChat in CLAN NEWS's place): CHAT section, the tabs, 4 lines, the typing line; the bottom prompt P FRIENDS
//   (with a red badge for unread friend messages) opens the FRIENDS page over the match.
// MP menu + FIND MATCH (MP menu layout mockup; to1/main-menu + to1/find-match-menu mnChat under the LOBBY box, chat_widgets.add_menu_chat): CHAT with the
//   PARTY tab only, 4 lines, the typing line. In a party Enter opens the typing line there (the menu's Enter select is eaten only then; SPACE still selects); without
//   a party the field says how to get one (P FRIENDS) and Enter stays the menu's. The party's lines are polled every 2 s on these pages too.
// KEYS: Enter opens the typing line (the HUD in a match, or the ESC menu); the keyboard catcher then eats every key (the game sees none: the character stands still,
//   Esc does not open the menu). Enter sends, Esc closes, Tab switches tabs, Backspace / Delete / arrows / Home / End edit, Ctrl+V pastes. Enter itself is eaten while
//   the chat can open (it never reaches the game or the ESC menu's buttons; SPACE still selects there). Pads: no typing in the HUD (the FRIENDS page has quick replies).
// OFF: OPTIONS > MULTIPLAYER > DISABLE CHAT (a child row of DISABLE MP UI: g_mp_hide[3]) or t2r-no-chat.txt next to the exe: no box, no ESC block, Enter is the game's,
//   nothing is received or shown.
#include "chat.h"
#define MSG_CHAT 0xC7
#define CH_KEEP 40                                   // lines kept per tab
#define CH_IDLE_MS 8000
#define CH_FADE_MS 600
#define CH_PARTY_POLL_MS 2000
static int imm_roster_name(uint32_t slot, char *out, size_t on);     // immersion.c
static int fr13_enabled(void);                                       // friends13.c: the in-game FRIENDS page is on
static void fr13_open_from_pause(void);                             // friends13.c: the FRIENDS page over the ESC menu
static int fr13_unread_total(void);                                  // friends13.c: unread friend messages (last state + lines held during the match)
// (lobby panel) CH_LOBBY: a 4th line store, shown only on the MP menu / FIND MATCH panel (the HUD / ESC menu tabs stay the CH_NCH first three)
#define CH_LOBBY 3
#define CH_NALL 4
static const char *const CH_TAB[CH_NALL] = {"MATCH", "TEAM", "PARTY", "LOBBY"};
static const char *const CH_TABPL[CH_NALL] = {"MECZ", "DRUŻYNA", "GRUPA", "LOBBY"};
static const char *const CH_COL[CH_NALL] = {"#D7D7D7", "#48A8D8", "#D9D86A", "#8FB0C8"};
static const char *ch_tab(int c) { return nt_pl() ? CH_TABPL[c] : CH_TAB[c]; }
typedef struct { char who[48], t[CH_BUF]; const char *col; uint64_t ms; } ch_line_t;
static struct {
    ch_line_t l[CH_NALL][CH_KEEP]; int n[CH_NALL];
    int tab, dot[CH_NALL];                           // the picked tab; a tab got a line while another one was picked
    uint64_t last_ms[CH_NALL];                       // newest line per tab (the idle box fades CH_IDLE_MS after it)
    unsigned gen;                                    // bumped with every change (the widgets are rewritten when it moves)
} CHS;
static int g_ch_off_file = -1;
static int chat_on(void) {
    if (g_ch_off_file < 0) { FILE *f = exe_side_open("t2r-no-chat.txt", "r"); g_ch_off_file = f != NULL; if (f) fclose(f); xlog("chat: %s", g_ch_off_file ? "off (t2r-no-chat.txt)" : "on"); }
    return !g_ch_off_file && !g_mp_hide[3];
}
static void ch_add(int tab, const char *who, const char *col, const char *text) {
    if (tab < 0 || tab >= CH_NALL || !text || !text[0]) return;
    if (CHS.n[tab] >= CH_KEEP) { memmove(&CHS.l[tab][0], &CHS.l[tab][1], sizeof CHS.l[tab][0] * (CH_KEEP - 1)); CHS.n[tab] = CH_KEEP - 1; }
    ch_line_t *l = &CHS.l[tab][CHS.n[tab]++];
    snprintf(l->who, sizeof l->who, "%s", who ? who : "");
    snprintf(l->t, sizeof l->t, "%s", text);
    ch_censor(l->who); ch_censor(l->t);              // (chat.h: every shown line, ours and received)
    l->col = col ? col : "#E6E6E6";
    l->ms = CHS.last_ms[tab] = GetTickCount64();
    if (tab != CHS.tab) CHS.dot[tab] = 1;
    CHS.gen++;
}
static void ch_clear_match(void) {                   // a new match: MATCH / TEAM start empty (PARTY keeps its history)
    CHS.n[CH_MATCH] = CHS.n[CH_TEAM] = 0; CHS.dot[CH_MATCH] = CHS.dot[CH_TEAM] = 0; CHS.last_ms[CH_MATCH] = CHS.last_ms[CH_TEAM] = 0; CHS.gen++;
}
// ---- keeping the text inside the box (long lines ran past the box's right edge). Widths are nrui.c's estimate (nr_cwf x pt x 1.06), read with a
// margin: CH_FIT of the text widget's width.
#define CH_FIT 0.94f
#define CH_FIT_FLD 0.98f                             // the typing line: its limit is already a gap short of the tab name
static float ch_tw(const char *s, int n, float pt) {
    float w = 0.0f;
    for (int i = 0; i < n && s[i]; i++) if (((unsigned char)s[i] & 0xC0) != 0x80) w += nr_cwf((const unsigned char *)s + i);
    return w * pt * 1.06f;
}
// A sent line as rows of at most maxw (broken at spaces; a word longer than a row is cut). Row 0 carries the name. Returns the rows (at most CH_LROWS).
#define CH_LROWS 8
typedef char ch_row_t[CH_BUF + 96];
static int ch_line_rows(const ch_line_t *l, float maxw, float pt, ch_row_t *out) {
    char pre[64] = "";
    if (l->who[0]) snprintf(pre, sizeof pre, "%s: ", l->who);
    const char *t = l->t;
    int n = (int)strlen(t), at = 0, nr = 0;
    while (at < n && nr < CH_LROWS) {
        float room = maxw - (nr ? 0.0f : ch_tw(pre, (int)strlen(pre), pt));
        int end = at, brk = -1;
        while (end < n) {
            int nx = end + 1; while (nx < n && ((unsigned char)t[nx] & 0xC0) == 0x80) nx++;
            if (ch_tw(t + at, nx - at, pt) > room) break;
            if (t[end] == ' ') brk = end;
            end = nx;
        }
        if (end < n) {                                   // the row is full: break at its last space (else cut the word)
            if (brk > at) end = brk;
            else if (end == at) { end++; while (end < n && ((unsigned char)t[end] & 0xC0) == 0x80) end++; }
        }
        if (!nr && l->who[0]) snprintf(out[nr], sizeof out[nr], "<font color=%c%s%c>%s:</font> %.*s", 34, l->col, 34, l->who, end - at, t + at);
        else snprintf(out[nr], sizeof out[nr], "%.*s", end - at, t + at);
        nr++;
        at = end; while (at < n && t[at] == ' ') at++;
    }
    if (!nr) { if (l->who[0]) snprintf(out[0], sizeof out[0], "<font color=%c%s%c>%s:</font>", 34, l->col, 34, l->who); else out[0][0] = 0; nr = 1; }
    return nr;
}
// The tab's newest rows, bottom aligned: rows[nrows - 1] = the newest line's last row; rows above the oldest shown one are "".
static void ch_tab_rows(int tab, float maxw, float pt, ch_row_t *rows, int nrows) {
    static ch_row_t lr[CH_LROWS];
    for (int k = 0; k < nrows; k++) rows[k][0] = 0;
    int k = nrows;
    for (int idx = CHS.n[tab] - 1; idx >= 0 && k > 0; idx--) {
        int m = ch_line_rows(&CHS.l[tab][idx], maxw, pt, lr);
        for (int r = m - 1; r >= 0 && k > 0; r--) memcpy(rows[--k], lr[r], sizeof lr[r]);
    }
}
// ------------------------------------------------------------------ MATCH / TEAM: peer messages
static uint16_t g_ch_seq;
static struct { uint8_t b[6 + CH_BUF]; int len, k; uint64_t t0; } g_ch_rs[4];   // resends of our newest lines (copy 2 at +150 ms, copy 3 at +450 ms)
static struct { uint16_t seq[16]; int n; } g_ch_seen[T2R_MAX_PEERS];
static void ch_own_name(char *o, size_t n) { char ln[16], lt[6]; if (ne_local_load(ln, lt) && ln[0]) { char c[40]; ch_clean(ln, strlen(ln), c, sizeof c, 24); snprintf(o, n, "%s", c); } else snprintf(o, n, "%s", nt_pl() ? "TY" : "YOU"); }
static void ch_mlog(int chan, const char *text);
static void ch_send_peer(int chan, const char *text) {
    uint8_t b[6 + CH_BUF];
    int len = ch_pkt_build(b, sizeof b, chan, ++g_ch_seq, text);
    if (!len) return;
    char me[40]; ch_own_name(me, sizeof me);
    ch_add(chan, me, "#D9D86A", text);               // our own line: shown at once (the broadcast never comes back to us)
    if (!g_send_tramp || match_substate() != 6) { xlog("chat: %s line kept local (no match session)", CH_TAB[chan]); return; }
    g_send_tramp(MSG_CHAT, b, (uint64_t)len, 0xff);
    for (int i = 0; i < 4; i++) if (!g_ch_rs[i].len) { memcpy(g_ch_rs[i].b, b, (size_t)len); g_ch_rs[i].len = len; g_ch_rs[i].k = 1; g_ch_rs[i].t0 = GetTickCount64(); break; }
    ch_mlog(chan, text);
    xlog("chat: sent %s line (%d bytes, seq %u)", CH_TAB[chan], len - 6, (unsigned)g_ch_seq);
}
static void ch_resend_tick(uint64_t now) {
    for (int i = 0; i < 4; i++) {
        if (!g_ch_rs[i].len) continue;
        uint64_t due = g_ch_rs[i].t0 + (g_ch_rs[i].k == 1 ? 150 : 450);
        if (now < due) continue;
        if (g_send_tramp && match_substate() == 6) g_send_tramp(MSG_CHAT, g_ch_rs[i].b, (uint64_t)g_ch_rs[i].len, 0xff);
        if (++g_ch_rs[i].k >= 3) g_ch_rs[i].len = 0;
    }
}
static void ch_recv(uint32_t slot, const uint8_t *buf, uint64_t len) {
    int chan; uint16_t seq; char t[CH_BUF];
    if (slot >= T2R_MAX_PEERS || !ch_pkt_parse(buf, (size_t)len, &chan, &seq, t, sizeof t)) return;
    for (int i = 0; i < 16 && i < g_ch_seen[slot].n; i++) if (g_ch_seen[slot].seq[i] == seq) return;    // a resent copy
    g_ch_seen[slot].seq[g_ch_seen[slot].n++ & 15] = seq;
    if (!chat_on()) return;
    uint32_t me = *(uint32_t *)VMA(0x180138090);
    int mate = same_team(slot, me);
    if (chan == CH_TEAM && !mate) { static int n; if (LOGCAP(n, 10)) xlog("chat: TEAM line from enemy slot %u dropped", slot); return; }
    char nm[40], who[48];
    imm_roster_name(slot, nm, sizeof nm);
    ch_clean(nm, strlen(nm), who, sizeof who, 24);
    ch_add(chan, who, mate ? "#48A8D8" : "#E04848", t);
    static int nl; if (LOGCAP(nl, 60)) xlog("chat: %s line from slot %u (%s)", CH_TAB[chan], slot, who);
}
// ------------------------------------------------------------------ PARTY + the report log copy: the server (op 0xD8, own short connection, one request at a time)
static volatile LONG g_ch_busy, g_ch_have;
static char g_ch_rep[24000];
static volatile LONG g_ch_replen;
static struct { uint8_t pl[64 + 3 + CH_BUF + 4]; int n, sub; } g_ch_job;
static DWORD WINAPI ch_worker(LPVOID arg) {
    (void)arg;
    HMODULE ws = LoadLibraryA("ws2_32.dll");
    t2r_sin a; t2r_net net;
    LONG res = 3;
    if (ws && hm_server(&a) && t2r_net_load(&net, ws)) {
        static uint8_t frame[3 + sizeof g_ch_job.pl];
        static char rep[sizeof g_ch_rep + 16];
        int n = g_ch_job.n + 1;
        frame[0] = (uint8_t)n; frame[1] = (uint8_t)(n >> 8); frame[2] = 0xD8;
        memcpy(frame + 3, g_ch_job.pl, (size_t)g_ch_job.n);
        int sent = 0;
        int got = t2r_rpc(&net, &a, frame, n + 2, rep, (int)sizeof rep - 1, 2500, 3000, 3000, &sent);
        if (sent) res = 2;
        int ln = got >= 3 ? (rep[0] & 0xff) + ((rep[1] & 0xff) << 8) : 0;
        if (ln >= 2 && got >= ln + 2 && (uint8_t)rep[2] == 0xD9 && ln - 1 < (int)sizeof g_ch_rep) {
            memcpy(g_ch_rep, rep + 3, (size_t)ln - 1);
            InterlockedExchange(&g_ch_replen, ln - 1);
            res = 1;
        }
    }
    InterlockedExchange(&g_ch_have, res);
    InterlockedExchange(&g_ch_busy, 0);
    return 0;
}
static int ch_rpc(int sub, const char *arg) {        // 1 = a request went out
    static char tok[65];
    if (g_ch_busy) return 0;
    if (!tok[0] && !clan_token(tok)) { tok[0] = 0; return 0; }
    memcpy(g_ch_job.pl, tok, 64);
    g_ch_job.pl[64] = 1; g_ch_job.pl[65] = (uint8_t)nt_pl(); g_ch_job.pl[66] = (uint8_t)sub;
    size_t al = arg ? strlen(arg) : 0;
    if (al > CH_BUF) al = CH_BUF;
    if (al) memcpy(g_ch_job.pl + 67, arg, al);
    g_ch_job.n = 67 + (int)al; g_ch_job.sub = sub;
    InterlockedExchange(&g_ch_busy, 1);
    HANDLE h = CreateThread(NULL, 0, ch_worker, NULL, 0, NULL);
    if (!h) { InterlockedExchange(&g_ch_busy, 0); return 0; }
    CloseHandle(h);
    return 1;
}
#define CH_S_PSAY 15
#define CH_S_PCHAT 16
#define CH_S_MLOG 17
#define CH_S_LSAY 18                                 // the LOBBY channel (social.py S_LSAY / S_LCHAT)
#define CH_S_LCHAT 19
static int g_ch_lobby_last = -1, g_ch_lobby_lk;
static uint64_t g_ch_lpoll_at;
static int ch_in_lobby(void) { return g_rq_back + g_rq_post > 0; }      // our search is a lobby's (requeue.c's last 0xBD answer)
static void ch_lobby_lines(const ch_pchat_t *d) {
    if (d->lk && d->lk != g_ch_lobby_lk) { g_ch_lobby_lk = d->lk; g_ch_lobby_last = -1; CHS.n[CH_LOBBY] = 0; CHS.gen++; }   // another lobby: its own lines only
    for (int i = 0; i < d->n; i++) {
        if (d->l[i].id <= g_ch_lobby_last) continue;
        char me[40];
        if (d->l[i].me) ch_own_name(me, sizeof me);
        ch_add(CH_LOBBY, d->l[i].me ? me : d->l[i].name, d->l[i].me ? "#D9D86A" : "#E6E6E6", d->l[i].t);
    }
    if (d->last > g_ch_lobby_last) g_ch_lobby_last = d->last;
}
static struct { int sub; char arg[CH_BUF + 4]; } g_ch_q[6];          // writes waiting for the connection (party lines, log copies)
static int g_ch_qn, g_ch_party_last = -1;
static uint64_t g_ch_poll_at;
static void ch_q(int sub, const char *arg) {
    if (g_ch_qn >= 6) { memmove(&g_ch_q[0], &g_ch_q[1], sizeof g_ch_q[0] * 5); g_ch_qn = 5; }
    g_ch_q[g_ch_qn].sub = sub; snprintf(g_ch_q[g_ch_qn].arg, sizeof g_ch_q[0].arg, "%s", arg); g_ch_qn++;
}
static void ch_mlog(int chan, const char *text) { char a[CH_BUF + 4]; snprintf(a, sizeof a, "%c\n%s", chan == CH_TEAM ? 't' : 'm', text); ch_q(CH_S_MLOG, a); }
static int ch_in_party(void);
static int g_ch_menu_up;                             // the MP menu / FIND MATCH CHAT panel is on screen (the party lines are polled there too)
static void ch_party_lines(const ch_pchat_t *d) {
    for (int i = 0; i < d->n; i++) {
        if (d->l[i].id <= g_ch_party_last) continue;
        char me[40];
        if (d->l[i].me) ch_own_name(me, sizeof me);
        ch_add(CH_PARTY, d->l[i].me ? me : d->l[i].name, d->l[i].me ? "#D9D86A" : "#E6E6E6", d->l[i].t);
    }
    if (d->last > g_ch_party_last) g_ch_party_last = d->last;
}
static void ch_net_tick(uint64_t now, int in_match) {
    LONG have = InterlockedExchange(&g_ch_have, 0);
    if (have == 1) {
        static ch_pchat_t d;
        if (ch_pchat_parse(&d, g_ch_rep, (size_t)g_ch_replen)) {
            int lob = g_ch_job.sub == CH_S_LSAY || g_ch_job.sub == CH_S_LCHAT;
            if (lob && !d.ok && d.err[0]) ch_add(CH_LOBBY, "", NULL, !strcmp(d.err, "rate") ? (nt_pl() ? "ZA DUŻO WIADOMOŚCI - POCZEKAJ CHWILĘ" : "TOO MANY MESSAGES - WAIT A MOMENT")
                                                     : (nt_pl() ? "NIE WYSŁANO - LOBBY SIĘ SKOŃCZYŁO" : "NOT SENT - THE LOBBY IS OVER"));
            if (lob) { if (d.has) ch_lobby_lines(&d); }
            else if (!d.ok && d.err[0]) {
                static int n; if (LOGCAP(n, 20)) xlog("chat: server refused sub %d: %s", g_ch_job.sub, d.err);
                if (g_ch_job.sub == CH_S_PSAY) ch_add(CH_PARTY, "", NULL, !strcmp(d.err, "rate") ? (nt_pl() ? "ZA DUŻO WIADOMOŚCI - POCZEKAJ CHWILĘ" : "TOO MANY MESSAGES - WAIT A MOMENT")
                                                                   : !strcmp(d.err, "noparty") ? (nt_pl() ? "NIE MASZ GRUPY" : "YOU ARE NOT IN A PARTY") : (nt_pl() ? "NIE WYSŁANO" : "NOT SENT"));
            }
            if (d.has && !lob) ch_party_lines(&d);
        }
    }
    if (g_ch_busy) return;
    if (g_ch_qn) {
        if (ch_rpc(g_ch_q[0].sub, g_ch_q[0].arg)) { memmove(&g_ch_q[0], &g_ch_q[1], sizeof g_ch_q[0] * (size_t)(g_ch_qn - 1)); g_ch_qn--; }
        return;
    }
    if (g_ch_menu_up && !in_match && ch_in_lobby() && now >= g_ch_lpoll_at) {          // the LOBBY lines, every 2 s on the MP menu / FIND MATCH
        g_ch_lpoll_at = now + CH_PARTY_POLL_MS;
        char a[16]; snprintf(a, sizeof a, "%d", g_ch_lobby_last < 0 ? 0 : g_ch_lobby_last);
        if (ch_rpc(CH_S_LCHAT, a)) return;
    }
    if ((in_match || g_ch_menu_up) && ch_in_party() && now >= g_ch_poll_at) {
        g_ch_poll_at = now + CH_PARTY_POLL_MS;
        char a[16]; snprintf(a, sizeof a, "%d", g_ch_party_last < 0 ? 0 : g_ch_party_last);
        ch_rpc(CH_S_PCHAT, a);
    }
}
static void ch_send(int tab, const char *text) {
    char t[CH_BUF];
    if (ch_clean(text, strlen(text), t, sizeof t, CH_MAXC) <= 0) return;
    if (tab == CH_LOBBY) {
        ch_q(CH_S_LSAY, t);
        g_ch_lpoll_at = GetTickCount64() + CH_PARTY_POLL_MS;   // (the LSAY reply carries the lobby's lines, ours included)
        xlog("chat: lobby line queued (%d bytes)", (int)strlen(t));
        return;
    }
    if (tab == CH_PARTY) {
        if (!ch_in_party()) { ch_add(CH_PARTY, "", NULL, nt_pl() ? "NIE MASZ GRUPY - ZAPROŚ ZNAJOMEGO NA STRONIE ZNAJOMYCH" : "YOU ARE NOT IN A PARTY - INVITE A FRIEND ON THE FRIENDS PAGE"); return; }
        ch_q(CH_S_PSAY, t);
        g_ch_poll_at = GetTickCount64() + CH_PARTY_POLL_MS;    // (the PSAY reply carries the party's lines, ours included)
        xlog("chat: party line queued (%d bytes)", (int)strlen(t));
        return;
    }
    ch_send_peer(tab, t);
}
// ------------------------------------------------------------------ the line editor (keys through gearup13.c's catcher: kt_keepalive / kt_next)
typedef struct { int on; char b[CH_BUF]; int len, caret, nch, sc; uint64_t t0, edit; } ced_t;     // sc: the first byte the field shows (ced_view)
enum { CED_NONE, CED_SEND, CED_CANCEL, CED_TAB };
static int ced_prev(const ced_t *e, int i) { if (i > 0) i--; while (i > 0 && ((unsigned char)e->b[i] & 0xC0) == 0x80) i--; return i; }
static int ced_next(const ced_t *e, int i) { if (i < e->len) i++; while (i < e->len && ((unsigned char)e->b[i] & 0xC0) == 0x80) i++; return i; }
static int ced_count(const char *s, int n) { int c = 0; for (int i = 0; i < n; i++) if (((unsigned char)s[i] & 0xC0) != 0x80) c++; return c; }
static void ced_cut(ced_t *e, int from, int to) {
    if (from < 0) from = 0;
    if (to > e->len) to = e->len;
    if (from >= to) return;
    memmove(e->b + from, e->b + to, (size_t)(e->len - to) + 1);
    e->len -= to - from; e->caret = from; e->nch = ced_count(e->b, e->len); e->edit = GetTickCount64();
}
static void ced_put(ced_t *e, uint32_t cp) {
    if (!ch_ok(cp) || e->nch >= CH_MAXC) return;
    char u[4]; size_t k = 0;
    if (!ch_put8(u, sizeof u + 1, &k, cp) || e->len + (int)k >= CH_BUF - 1) return;
    memmove(e->b + e->caret + k, e->b + e->caret, (size_t)(e->len - e->caret) + 1);
    memcpy(e->b + e->caret, u, k);
    e->len += (int)k; e->caret += (int)k; e->nch++; e->edit = GetTickCount64();
}
static void ced_paste(ced_t *e) {
    if (!OpenClipboard(NULL)) return;
    HANDLE h = GetClipboardData(CF_UNICODETEXT);
    const WCHAR *w = h ? (const WCHAR *)GlobalLock(h) : NULL;
    for (int i = 0; w && w[i] && i < 400; i++) { uint32_t c = w[i]; if (c >= 0xD800 && c < 0xE000) continue; ced_put(e, c == '\n' || c == '\r' || c == '\t' ? ' ' : c); }
    if (w) GlobalUnlock(h);
    CloseClipboard();
}
static void ced_start(ced_t *e) {
    memset(e, 0, sizeof *e);
    e->on = 1; e->t0 = e->edit = GetTickCount64();
    kt_raw_install();
    InterlockedExchange(&g_kt_on, 1);
    kt_keepalive();
    int vk; uint32_t ch; while (kt_next(&vk, &ch)) {}     // (keys of before: dropped)
}
static void ced_stop(ced_t *e) { e->on = 0; InterlockedExchange(&g_kt_on, 0); }
static int ced_tick(ced_t *e) {
    if (!e->on) return CED_NONE;
    kt_keepalive();
    int vk, r = CED_NONE; uint32_t ch;
    int ctl = (GetAsyncKeyState(VK_CONTROL) & 0x8000) != 0;
    while (r == CED_NONE && kt_next(&vk, &ch)) {
        switch (vk) {
        case VK_RETURN: r = CED_SEND; break;
        case VK_ESCAPE: r = CED_CANCEL; break;
        case VK_TAB: r = CED_TAB; break;
        case VK_BACK:
            if (ctl) { int to = e->caret; while (to > 0 && e->b[to - 1] == ' ') to--; while (to > 0 && e->b[to - 1] != ' ') to--; ced_cut(e, to, e->caret); }
            else ced_cut(e, ced_prev(e, e->caret), e->caret);
            break;
        case VK_DELETE: ced_cut(e, e->caret, ced_next(e, e->caret)); break;
        case VK_LEFT: e->caret = ced_prev(e, e->caret); e->edit = GetTickCount64(); break;
        case VK_RIGHT: e->caret = ced_next(e, e->caret); e->edit = GetTickCount64(); break;
        case VK_HOME: e->caret = 0; e->edit = GetTickCount64(); break;
        case VK_END: e->caret = e->len; e->edit = GetTickCount64(); break;
        default:
            if (ctl && vk == 'V') ced_paste(e);
            else if (!ctl && ch >= 0x20) ced_put(e, ch);
            break;
        }
    }
    return r;
}
// the text with the caret: a '|' solid for 450 ms after an edit, then blinking
static void ced_show(const ced_t *e, char *o, size_t n, uint64_t now) {
    int car = now - e->edit < 450 || ((now - e->edit) / 530) % 2 == 0;
    snprintf(o, n, "%.*s%s%s", e->caret, e->b, car ? "|" : "<font color=\"#262626\">|</font>", e->b + e->caret);
}
// the same, kept inside a field maxw wide (the typed text ran over the tab name at the field's right; it may run up to just before that name:
// ch_fld_w): the part around the caret that fits;
// the field scrolls as the caret moves (e->sc), and shows as much of the start as fits when the text gets shorter again
static void ced_view(ced_t *e, char *o, size_t n, uint64_t now, float maxw, float pt) {
    maxw *= CH_FIT_FLD;
    float cw = ch_tw("|", 1, pt);
    if (e->sc > e->caret) e->sc = e->caret;
    if (e->sc > e->len) e->sc = e->len;
    while (e->sc < e->caret && ch_tw(e->b + e->sc, e->caret - e->sc, pt) + cw > maxw) e->sc = ced_next(e, e->sc);
    while (e->sc > 0) { int p = ced_prev(e, e->sc); if (ch_tw(e->b + p, e->len - p, pt) + cw > maxw) break; e->sc = p; }
    int end = e->caret;
    while (end < e->len) { int nx = ced_next(e, end); if (ch_tw(e->b + e->sc, nx - e->sc, pt) + cw > maxw) break; end = nx; }
    int car = now - e->edit < 450 || ((now - e->edit) / 530) % 2 == 0;
    snprintf(o, n, "%.*s%s%.*s", e->caret - e->sc, e->b + e->sc, car ? "|" : "<font color=\"#262626\">|</font>", end - e->caret, e->b + e->caret);
}
// ------------------------------------------------------------------ Enter: eaten while the chat can open (the catcher's Enter-only mode, gearup13.c g_kt_enter)
static ced_t g_ch_ed;                                // the one typing line (HUD or ESC menu)
static int g_ch_where;                               // 1 = typing in the HUD, 2 = in the ESC menu, 3 = on the MP menu / FIND MATCH (PARTY only)
static int ch_enter_pressed(int armed) {
    InterlockedExchange(&g_kt_enter, armed ? 1 : 0);
    if (!armed) return 0;
    kt_raw_install();
    kt_keepalive();
    int vk, hit = 0; uint32_t ch;
    while (kt_next(&vk, &ch)) if (vk == VK_RETURN) hit = 1;
    return hit;
}
static void ch_open(int where) {
    ced_start(&g_ch_ed);
    g_ch_where = where;
    CHS.dot[CHS.tab] = 0; CHS.gen++;
    xlog("chat: typing (%s, tab %s)", where == 1 ? "HUD" : where == 2 ? "ESC menu" : "MP menu", CH_TAB[CHS.tab]);
}
static void ch_close(const char *why) { if (!g_ch_ed.on) return; ced_stop(&g_ch_ed); g_ch_where = 0; CHS.gen++; xlog("chat: typing closed (%s)", why); }
static void ch_switch_tab(int dir) { CHS.tab = (CHS.tab + CH_NCH + dir) % CH_NCH; CHS.dot[CHS.tab] = 0; CHS.gen++; ui_sfx("sfx-cycle"); }
static int ch_edit_tick(void) {                      // 1 = the editor consumed the frame
    int r = ced_tick(&g_ch_ed);
    if (r == CED_SEND) {
        if (g_ch_ed.len) ch_send(CHS.tab, g_ch_ed.b);
        ch_close("Enter");
        return 1;
    }
    if (r == CED_CANCEL) { ch_close("Esc"); return 1; }
    if (r == CED_TAB && g_ch_where != 3) ch_switch_tab((GetAsyncKeyState(VK_SHIFT) & 0x8000) ? -1 : 1);
    if (r == CED_TAB && g_ch_where == 3 && ch_in_party() && ch_in_lobby()) {      // the MP menu panel: PARTY <-> LOBBY (only both when both exist)
        CHS.tab = CHS.tab == CH_LOBBY ? CH_PARTY : CH_LOBBY; CHS.dot[CHS.tab] = 0; CHS.gen++; ui_sfx("sfx-cycle");
    }
    if (g_ch_ed.on) CHS.gen++;                       // (the caret blinks)
    return g_ch_ed.on;
}
// ------------------------------------------------------------------ HUD box (currency-hud chatHud > chatBox; the widgets are re-found for every match page)
#define CHB_TAB_PT 30.0f                             // = chat_widgets HB_TAB_PT / HB_TAB_R / HB_UL_Y (box-local)
#define CHB_UL_Y 70.0f
#define CHB_LINE_PT 40.0f                            // = chat_widgets HB_LINE_PT; a line row is HB_W - 2 HB_LX wide, the typing text HB_W - 260
#define CHB_LINE_W 1012.0f
#define CHB_FLD_X 36.0f                              // the typing text's left edge; the tab name (chFch, CHB_FCH_PT) is right aligned at CHB_FCH_R
#define CHB_FCH_R 1040.0f
#define CHB_FCH_PT 28.0f
#define CH_FLD_GAP 28.0f                             // room between the typed text and the tab name
// how wide the typed text may get: up to just before the picked tab's name
static float ch_fld_w(float x0, float name_r, float name_pt, int tab) { return name_r - nr_twf(ch_tab(tab), name_pt) - CH_FLD_GAP - x0; }
// The tabs: each name was right aligned in a fixed
// slot, so the gaps between them differed with the names' widths, and the underline (the coarse nr_tw width) was shorter than the name. Now they are packed from
// the right margin (= the CHAT label's left margin, HB_LX) with one gap between names, measured with the font's widths (nr_twf), and the underline spans the
// picked name exactly. The ESC menu block does the same (ch_tabs_pack).
#define CHB_TABS_R 1044.0f                           // HB_W - HB_LX
#define CHB_TAB_YC 44.0f                             // chat_widgets HB_TAB_Y + HB_TAB_H / 2 (the names' pivot line)
#define CH_TAB_GAP 1.5f                              // the gap between two names, in ems of the tab point size (30 pt: 45 units)
// x of each name's right end, right to left from r; returns the leftmost name's left end. t3 = the drawn texts (with an unread " *"), names = the bare names.
static float ch_tabs_pack(char t3[CH_NCH][96], float r, float pt, float *right, float *namew) {
    for (int c = CH_NCH - 1; c >= 0; c--) {
        right[c] = r;
        namew[c] = nr_twf(ch_tab(c), pt);
        r -= nr_twf(t3[c], pt) + (c ? CH_TAB_GAP * pt : 0.0f);
    }
    return r;
}
// The preview (idle) box: its newest 3 rows sat one row above the box's bottom with the tab name under them; now
// they are CHB_IDLE_DY lower (the newest row on the box's bottom padding) and the tab name sits at the box's top right (chat_widgets chIdl).
#define CHB_ROW_Y(k) (116.0f + 62.0f * (k))          // chat_widgets HB_LINE_Y0 + k HB_LINE_DY + HB_LINE_H / 2 (a row's pivot line)
#define CHB_IDLE_DY 36.0f
enum { CW_BOX, CW_BG, CW_BGI, CW_LBL, CW_T0, CW_T1, CW_T2, CW_U0, CW_U1, CW_U2, CW_L0, CW_L1, CW_L2, CW_L3, CW_L4, CW_FLD, CW_FU0, CW_FU1, CW_FU2, CW_FTX, CW_FCH, CW_HINT, CW_IDL, CW_N };
static const char *const CW_LEAF[CW_N] = {NULL, "chBg", "chBgI", "chLbl", "chT0", "chT1", "chT2", "chU0", "chU1", "chU2", "chL0", "chL1", "chL2", "chL3", "chL4",
                                          "chFld", "chFu0", "chFu1", "chFu2", "chFtx", "chFch", "chHint", "chIdl"};
// ---- flicker-free texts (60 fps clips / /). Engine trait: a gui2 text whose string changes draws nothing for a frame
// while its glyphs are rebuilt. Round 1 (hidden twins swapped by VISIBILITY after 3 frames) still blanked one frame at every swap: a hidden widget does not build
// its glyphs until it is shown. And key repeat (Backspace held) kept pushing the swap back, so the text jumped by 5 - 12 characters at a time.
// Round 2 (both twins visible, the spare at alpha 0.01) still blanked the swap frame (clip: one empty frame every 3 while Backspace was held): a text
// that is not drawn - hidden, or at an alpha the renderer skips - does not build its glyphs, so a twin always draws nothing on its FIRST shown frame.
// Now the swap OVERLAPS: the new string goes into the spare twin, which is shown at once while the old one stays on screen; CHTW_LEAD frames later (the new one
// has drawn by then) the old one is hidden. Each frame at least one built text is on screen; for CHTW_LEAD frames both draw (typing: the old string is a prefix of
// the new, so the overlap is not seen; Backspace: the removed letter lingers 2 frames). A newer string waits for the old twin to be hidden (newest kept).
#define CHTW_LEAD 2
#define CHTW_LEAD_MENU 4                             // a menu page's text (the ESC block, the FRIENDS page): its glyphs may take longer than the HUD's (DB_SETTLE / banner)
typedef void (*chtw_set_t)(uint64_t, const char *);
static void chw_set_hud(uint64_t w, const char *t);
typedef struct {
    uint64_t a, b; chtw_set_t set;
    int shb, pend, vis, lead;                        // b is the front twin / the back twin was written and shown, the front waits to be hidden / the leaf should show
    uint64_t at;
    char want[CH_BUF + 96], wr[CH_BUF + 96];         // the newest string asked for / the one written into the back twin
} chtw_t;
static void chtw_show(chtw_t *t) {
    if (!t->b) { w_visible(t->a, t->vis); return; }
    w_visible(t->shb ? t->b : t->a, t->vis);
    w_visible(t->shb ? t->a : t->b, t->vis && t->pend);
}
// a fresh page instance: both twins get the text at once (nothing is on screen yet), the front shown, the back hidden
static void chtw_bind(chtw_t *t, uint64_t a, uint64_t b, chtw_set_t set, const char *init, int vis) {
    memset(t, 0, sizeof *t);
    t->a = a; t->b = b; t->set = set; t->vis = vis; t->lead = set == chw_set_hud ? CHTW_LEAD : CHTW_LEAD_MENU;
    if (!a) return;
    snprintf(t->want, sizeof t->want, "%s", init ? init : "");
    set(a, t->want); w_alpha(a, 1.0f);
    if (b) { set(b, t->want); w_alpha(b, 1.0f); }
    chtw_show(t);
}
static void chtw_write(chtw_t *t) {
    snprintf(t->wr, sizeof t->wr, "%s", t->want);
    t->set(t->shb ? t->a : t->b, t->wr);
    t->pend = 1; t->at = g_frame;
    chtw_show(t);                                    // the back twin shows now, under / over the front one (its first frame draws nothing)
}
static void chtw_text(chtw_t *t, const char *s) {
    if (!t->a || !strcmp(t->want, s)) return;
    snprintf(t->want, sizeof t->want, "%s", s);
    if (!t->b) { t->set(t->a, t->want); return; }
    if (!t->pend) chtw_write(t);                     // (else it waits: neither twin is touched while both are on screen)
}
static void chtw_vis(chtw_t *t, int on) { if (!t->a || t->vis == on) return; t->vis = on; chtw_show(t); }
static void chtw_tick(chtw_t *t) {
    if (!t->a || !t->b || !t->pend || g_frame - t->at < (uint64_t)t->lead) return;
    t->pend = 0; t->shb = !t->shb;                   // the back twin is the front now; the old front is hidden
    chtw_show(t);
    if (strcmp(t->want, t->wr)) chtw_write(t);       // a newer string came meanwhile
}
// An EMPTY string written to a gui2 text leaves the old text on screen, so the widget pak's preview lines were never cleared:
// every blank write is one space instead.
static void chw_set_hud(uint64_t w, const char *t) { ((void (*)(uint64_t, const char *))VMA(0x18000DE90))(w, t && t[0] ? t : " "); }
static void chw_set_menu(uint64_t w, const char *t) { ((fn_settext_t)VMA(0x180064450))(w, t && t[0] ? t : " "); }
// ---- the HUD leaves
static struct {
    uint64_t page, w[CW_N]; int miss; uint64_t retry; char txt[CW_N][CH_BUF + 96]; int vis[CW_N]; int aq; unsigned gen; int mode;
    chtw_t tw[CW_N];                                 // the double-buffered leaves (chw_has_twin)
} CHW;
static int chw_has_twin(int i) { return (i >= CW_L0 && i <= CW_L4) || i == CW_FTX; }
static void chw_text(int i, const char *t) {
    if (!CHW.w[i]) return;
    if (chw_has_twin(i)) { chtw_text(&CHW.tw[i], t); return; }
    if (!strcmp(CHW.txt[i], t)) return;
    snprintf(CHW.txt[i], sizeof CHW.txt[i], "%s", t);
    chw_set_hud(CHW.w[i], t);
}
static void chw_vis(int i, int on) {
    if (!CHW.w[i] || CHW.vis[i] == on + 1) return;
    CHW.vis[i] = on + 1;
    if (chw_has_twin(i)) chtw_vis(&CHW.tw[i], on); else w_visible(CHW.w[i], on);
}
static void ch_hud_twins(void) { for (int i = CW_L0; i < CW_N; i++) if (chw_has_twin(i)) chtw_tick(&CHW.tw[i]); }
static int ch_hud_resolve(void) {
    uint64_t page = *(uint64_t *)VMA(0x180189BA0);
    if (page == CHW.page && CHW.w[CW_BOX]) return 1;
    if (page == CHW.page && CHW.miss && GetTickCount64() < CHW.retry) return 0;
    memset(&CHW, 0, sizeof CHW);
    CHW.page = page; CHW.aq = -1;
    CHW.w[CW_BOX] = hud_widget("chatHud", "chatBox", NULL);
    if (!CHW.w[CW_BOX]) { CHW.miss = 1; CHW.retry = GetTickCount64() + 3000; static int n; if (LOGCAP(n, 3)) xlog("chat: HUD widgets chatHud/chatBox not found (old widget pak?)"); return 0; }
    int ntw = 0;
    for (int i = 1; i < CW_N; i++) {
        CHW.w[i] = hud_widget("chatHud", "chatBox", CW_LEAF[i]);
        if (!CHW.w[i] || !chw_has_twin(i)) continue;
        char tn[16]; snprintf(tn, sizeof tn, "%sB", CW_LEAF[i]);
        uint64_t b = hud_widget("chatHud", "chatBox", tn);
        // a fresh page shows its template texts: blank them
        chtw_bind(&CHW.tw[i], CHW.w[i], b, chw_set_hud, "", 0);
        CHW.vis[i] = 1;                              // (= hidden; ch_hud_tick shows what the mode needs)
        ntw += b != 0;
    }
    xlog("chat: HUD box found (%d leaves, %d twins)", (int)(CW_N - 1), ntw);
    return 1;
}
static void ch_tabs_text(char out[CH_NCH][96]) {
    for (int c = 0; c < CH_NCH; c++) {
        int on = c == CHS.tab;
        snprintf(out[c], 96, "<font color=%c%s%c>%s%s</font>", 34, on ? CH_COL[c] : "#6E7074", 34, ch_tab(c), !on && CHS.dot[c] ? " *" : "");
    }
}
static void ch_hud_tick(uint64_t now, int show) {
    if (!show) { if (CHW.w[CW_BOX] && CHW.page == *(uint64_t *)VMA(0x180189BA0)) chw_vis(CW_BOX, 0); return; }   // (a handle of an older match page is never touched)
    if (!ch_hud_resolve()) return;
    ch_hud_twins();
    int typing = g_ch_ed.on && g_ch_where == 1;
    int tab = CHS.tab;
    uint64_t age = CHS.last_ms[tab] ? now - CHS.last_ms[tab] : ~0ULL;
    float a = typing ? 1.0f : age < CH_IDLE_MS ? 1.0f : age < CH_IDLE_MS + CH_FADE_MS ? 1.0f - (float)(age - CH_IDLE_MS) / CH_FADE_MS : 0.0f;
    if (!typing && (!CHS.n[tab] || g_mp_ui_off || g_buyhint_active)) a = 0.0f;   // (DISABLE MP UI / the buy hint in the same spot: no idle box; typing still shows it)
    int q = (int)(a * 20.0f + 0.5f);
    if (q != CHW.aq) { w_alpha(CHW.w[CW_BOX], q / 20.0f); CHW.aq = q; }
    chw_vis(CW_BOX, q > 0);
    if (q <= 0) return;
    if (CHW.gen == CHS.gen && CHW.mode == typing + 1) return;
    CHW.gen = CHS.gen; CHW.mode = typing + 1;
    for (int i = CW_BG; i < CW_N; i++) {                                 // what each mode shows
        int on = 1;
        if (i == CW_BGI || i == CW_IDL) on = !typing;
        else if (i == CW_BG || i == CW_LBL || (i >= CW_T0 && i <= CW_T2) || i == CW_FLD || i == CW_FTX || i == CW_FCH || i == CW_HINT) on = typing;
        else if (i >= CW_U0 && i <= CW_U2) on = typing && i - CW_U0 == tab;
        else if (i >= CW_FU0 && i <= CW_FU2) on = typing && i - CW_FU0 == tab;
        else if (i == CW_L0 || i == CW_L1) on = typing;
        chw_vis(i, on);
    }
    int nl = typing ? 5 : 3;
    char b[CH_BUF + 96];
    static ch_row_t rows[5];
    ch_tab_rows(tab, CHB_LINE_W * CH_FIT, CHB_LINE_PT, rows + 5 - nl, nl);     // the newest rows at the bottom (L4 = newest); a long line takes several rows
    for (int k = 2; k < 5; k++) {                                        // the rows the preview uses: lower while previewing (CHB_IDLE_DY)
        float y = CHB_ROW_Y(k) + (typing ? 0.0f : CHB_IDLE_DY);
        if (CHW.tw[CW_L0 + k].a) w_pivot(CHW.tw[CW_L0 + k].a, 32.0f, y);
        if (CHW.tw[CW_L0 + k].b) w_pivot(CHW.tw[CW_L0 + k].b, 32.0f, y);
    }
    for (int k = 0; k < 5; k++) chw_text(CW_L0 + k, k < 5 - nl ? "" : rows[k]);
    if (typing) {
        char t3[CH_NCH][96]; ch_tabs_text(t3);
        float rx[CH_NCH], nw[CH_NCH];
        ch_tabs_pack(t3, CHB_TABS_R, CHB_TAB_PT, rx, nw);
        for (int c = 0; c < CH_NCH; c++) {
            chw_text(CW_T0 + c, t3[c]);
            if (CHW.w[CW_T0 + c]) w_pivot(CHW.w[CW_T0 + c], rx[c], CHB_TAB_YC);
        }
        if (CHW.w[CW_U0 + tab]) {                                        // the picked tab's underline: exactly under its name (the name is the text's left part)
            float x = rx[tab] - nr_twf(t3[tab], CHB_TAB_PT);
            w_pivot(CHW.w[CW_U0 + tab], x, CHB_UL_Y);
            w_scale(CHW.w[CW_U0 + tab], nw[tab] / NR_RULE_W0, 1.0f);
        }
        chw_text(CW_LBL, nt_pl() ? "CZAT" : "CHAT");
        char ed[CH_BUF + 64]; ced_view(&g_ch_ed, ed, sizeof ed, now, ch_fld_w(CHB_FLD_X, CHB_FCH_R, CHB_FCH_PT, tab), CHB_LINE_PT);
        chw_text(CW_FTX, ed);
        snprintf(b, sizeof b, "<font color=%c%s%c>%s</font>", 34, CH_COL[tab], 34, ch_tab(tab));
        chw_text(CW_FCH, b);
        // the keys in white, what they do in grey, one even gap between the pairs
#define CHK(k) "<font color=\"#E8E8E8\">" k "</font>"
        chw_text(CW_HINT, nt_pl() ? CHK("ENTER") " WYŚLIJ      " CHK("TAB") " ZMIEŃ KANAŁ      " CHK("ESC") " ZAMKNIJ"
                                  : CHK("ENTER") " SEND      " CHK("TAB") " SWITCH TAB      " CHK("ESC") " CLOSE");
#undef CHK
    } else {
        snprintf(b, sizeof b, "<font color=%c%s%c>%s</font>", 34, CH_COL[tab], 34, ch_tab(tab));
        chw_text(CW_IDL, b);
    }
}
// ------------------------------------------------------------------ ESC menu block (to1/pause-menu pzChat, in CLAN NEWS's place) + the P FRIENDS prompt
#define PC_W 1060.0f                                 // pause_restyle_widgets PNR_NEWS width
#define PC_TABS_X0 600.0f                            // chat_widgets PC_TABS_X0: the section rule ends here (the tabs sit right of it)
#define PC_LINE_PT 31.5f                             // chat_widgets: the lines nr.pt(21), PC_W - 56 wide; the typing text nr.pt(18), PC_W - 230 wide
#define PC_LINE_W 1004.0f
#define PC_FLD_PT 27.0f
#define PC_FLD_X 34.0f                               // chat_widgets pcFtx left edge; pcFch right aligned at PC_W - 26, nr.pt(16)
#define PC_FCH_R 1034.0f
#define PC_FCH_PT 24.0f
#define PC_UL_Y 58.0f                                // = chat_widgets PC_UL_Y / PC_TAB_R / the tab point size nr.pt(17)
#define PC_TAB_PT 25.5f
#define PC_TAB_YC 30.0f                              // chat_widgets PC_SEC_Y (the names' pivot line)
#define PC_TABS_R 1060.0f                            // = PC_W: the block's right edge (the section rule's right end)
static uint64_t g_ch_pause_grp;
static int g_ch_pause_up;
static chtw_t g_ch_ptw[5];                           // ESC menu: pcL0..3, pcFtx (double buffered like the HUD leaves)
static void ch_pause_bind(void) {
    char p[64], pb[64];
    for (int k = 0; k < 5; k++) {
        if (k < 4) snprintf(p, sizeof p, "anim-group.pzChat.pcL%d", k); else snprintf(p, sizeof p, "anim-group.pzChat.pcFtx");
        snprintf(pb, sizeof pb, "%sB", p);
        chtw_bind(&g_ch_ptw[k], ui_w(p), ui_w(pb), chw_set_menu, "", 1);
    }
}
static int ch_pause_owns(void) { return chat_on() && ui_w("anim-group.pzChat") != 0; }   // clancard.c: the CLAN NEWS rows stay hidden (the chat sits there)
static void ch_pause_tick(uint64_t now, int on_pause) {
    uint64_t g = on_pause ? ui_w("anim-group.pzChat") : 0;
    g_ch_pause_up = g != 0;
    if (!g) { g_ch_pause_grp = 0; if (g_ch_where == 2) ch_close("ESC menu left"); return; }
    for (int k = 0; k < 5; k++) chtw_tick(&g_ch_ptw[k]);
    static unsigned lgen; static unsigned ugen; static uint64_t at;
    int typing = g_ch_ed.on && g_ch_where == 2;
    if (g != g_ch_pause_grp || ugen != g_ui_gen) {
        g_ch_pause_grp = g; ugen = g_ui_gen; lgen = ~0u;
        ch_pause_bind();                             // (g_ch_pause_grp is 0 after every close: the handle is the path's hash, the same on each open)
        {   // the section rule ends one tab gap before the leftmost tab (the tabs are packed from the right edge, ch_tabs_pack)
            char t0[CH_NCH][96]; float rx[CH_NCH], nw[CH_NCH];
            for (int c = 0; c < CH_NCH; c++) snprintf(t0[c], 96, "%s", ch_tab(c));
            float x0 = ch_tabs_pack(t0, PC_TABS_R, PC_TAB_PT, rx, nw) - CH_TAB_GAP * PC_TAB_PT;
            nr_section("anim-group.pzChat.pcSec", 0.0f, x0 > 300.0f ? x0 : PC_TABS_X0, 30.0f, nt_pl() ? "CZAT" : "CHAT", "", 36.0f);
        }
        w_visible(g, 1);
    }
    if (lgen == CHS.gen && now - at < 1000) return;
    lgen = CHS.gen; at = now;
    int tab = CHS.tab;
    char b[CH_BUF + 96], p[64];
    char t3[CH_NCH][96]; ch_tabs_text(t3);
    float rx[CH_NCH], nw[CH_NCH];
    ch_tabs_pack(t3, PC_TABS_R, PC_TAB_PT, rx, nw);
    for (int c = 0; c < CH_NCH; c++) {
        snprintf(p, sizeof p, "anim-group.pzChat.pcT%d", c); ui_text(p, t3[c]);
        { uint64_t tw = ui_w(p); if (tw) w_pivot(tw, rx[c], PC_TAB_YC); }
        snprintf(p, sizeof p, "anim-group.pzChat.pcU%d", c); ui_visible(p, c == tab);
        if (c == tab) nr_rule(p, rx[c] - nr_twf(t3[c], PC_TAB_PT), PC_UL_Y, nw[c]);
        snprintf(p, sizeof p, "anim-group.pzChat.pcFu%d", c); ui_visible(p, c == tab);
    }
    static ch_row_t rows[4];
    ch_tab_rows(tab, PC_LINE_W * CH_FIT, PC_LINE_PT, rows, 4);
    for (int k = 0; k < 4; k++) chtw_text(&g_ch_ptw[k], rows[k]);
    if (typing) { ced_view(&g_ch_ed, b, sizeof b, now, ch_fld_w(PC_FLD_X, PC_FCH_R, PC_FCH_PT, tab), PC_FLD_PT); chtw_text(&g_ch_ptw[4], b); }
    else chtw_text(&g_ch_ptw[4], nt_pl() ? "<font color=\"#6E7074\">ENTER - PISZ,  TAB - ZMIEŃ</font>" : "<font color=\"#6E7074\">ENTER to type,  TAB switch</font>");
    snprintf(b, sizeof b, "<font color=%c%s%c>%s</font>", 34, CH_COL[tab], 34, ch_tab(tab));
    ui_text("anim-group.pzChat.pcFch", b);
}
// clancard.c cc_pause_layout: the boxed prompts of the ESC menu (P FRIENDS first when the in-game FRIENDS page exists) and its unread badge
static int ch_pause_prompts(nr_prompt_t *it) {
    int n = 0;
    if (fr13_enabled()) it[n++] = (nr_prompt_t){"P", "menu:next", nt_pl() ? "ZNAJOMI" : "FRIENDS", 1};
    it[n++] = (nr_prompt_t){"menu:select", "menu:select", "SELECT", 1};
    it[n++] = (nr_prompt_t){"menu:back", "menu:back", "BACK", 1};
    return n;
}
static void ch_pause_badge(void) {                   // the red unread count at the P FRIENDS box's top right (pzPBadge)
    static int last = -1; static float lx = -1.0f; static unsigned lg = ~0u;
    int on = fr13_enabled() && g_nr_pb_n >= 3, k = g_nr_pb_n - 1;       // P FRIENDS = item 0 = the leftmost box (index n - 1)
    int u = on ? fr13_unread_total() : 0;
    if (u == last && (!on || g_nr_pb_x1[k] == lx) && lg == g_ui_gen) return;
    last = u; lx = on ? g_nr_pb_x1[k] : -1.0f; lg = g_ui_gen;
    ui_visible("anim-group.pzPBadge", u > 0);
    if (u <= 0) return;
    char t[8]; snprintf(t, sizeof t, "%d", u > 9 ? 9 : u);
    ui_text("anim-group.pzPBadge.pzPBadgeTx", t);
    w_pivot(ui_w("anim-group.pzPBadge"), g_nr_pb_x1[k] - 30.0f, NR_PROMPT_Y - NR_PROMPT_H / 2.0f - 22.0f);
}
// ------------------------------------------------------------------ MP menu / FIND MATCH panel (mnChat, chat_widgets.add_menu_chat; PARTY only)
#define MC_LINE_PT 30.0f                             // = chat_widgets MC_LINE_PT; a line row is MC_W - 2 MC_LX = 1070 wide
#define MC_LINE_W 1070.0f
#define MC_FLD_X 64.0f                               // chat_widgets mcFtx left edge; mcFch right aligned at MC_W - 60, 26 pt
#define MC_FCH_R 1122.0f
#define MC_FCH_PT 26.0f
#define MC_TAB_R 1126.0f                             // chat_widgets MC_W - MC_LX: the tab names' right end
#define MC_TAB_PT 30.0f                              // chat_widgets MC_TAB_PT
#define MC_HDR_H 88.0f                               // chat_widgets MC_HDR
#define MC_UL_Y (MC_HDR_H / 2.0f + 24.0f)            // chat_widgets MC_UL_Y
static uint64_t g_ch_menu_grp;
static chtw_t g_ch_mtw[5];                           // mcL0..3, mcFtx (double buffered)
static void ch_menu_bind(void) {
    char p[64], pb[64];
    for (int k = 0; k < 5; k++) {
        if (k < 4) snprintf(p, sizeof p, "anim-group.mnChat.mcL%d", k); else snprintf(p, sizeof p, "anim-group.mnChat.mcFtx");
        snprintf(pb, sizeof pb, "%sB", p);
        chtw_bind(&g_ch_mtw[k], ui_w(p), ui_w(pb), chw_set_menu, "", 1);
    }
}
static int g_ch_mtab = CH_PARTY;                      // the menu panel's tab: CH_PARTY / CH_LOBBY
static void ch_menu_tabs(int lobby) {                  // PARTY (and LOBBY in a lobby) right aligned in the header, the picked one coloured + underlined
    static int ll = -1, lt = -1; static unsigned lg = ~0u; static uint64_t ltp;
    uint64_t tp = top_page();                          // (the handles are path hashes: the same on the MP menu and FIND MATCH - a page change re-writes)
    if (ll == lobby && lt == g_ch_mtab && lg == g_ui_gen && ltp == tp) return;
    ll = lobby; lt = g_ch_mtab; lg = g_ui_gen; ltp = tp;
    char t[128];
    float r = MC_TAB_R, wl = nr_twf(ch_tab(CH_LOBBY), MC_TAB_PT), wp = nr_twf(ch_tab(CH_PARTY), MC_TAB_PT);
    float rp = lobby ? r - wl - CH_TAB_GAP * MC_TAB_PT : r;
    snprintf(t, sizeof t, "<font color=%c%s%c>%s</font>", 34, g_ch_mtab == CH_PARTY ? CH_COL[CH_PARTY] : "#6E7074", 34, ch_tab(CH_PARTY));
    ui_text("anim-group.mnChat.mcT0", t);
    w_pivot(ui_w("anim-group.mnChat.mcT0"), rp, MC_HDR_H / 2.0f);
    ui_visible("anim-group.mnChat.mcU0", g_ch_mtab == CH_PARTY);
    w_pivot(ui_w("anim-group.mnChat.mcU0"), rp - wp, MC_UL_Y);
    ui_visible("anim-group.mnChat.mcT1", lobby);
    ui_visible("anim-group.mnChat.mcU1", lobby && g_ch_mtab == CH_LOBBY);
    if (lobby) {
        snprintf(t, sizeof t, "<font color=%c%s%c>%s</font>", 34, g_ch_mtab == CH_LOBBY ? CH_COL[CH_LOBBY] : "#6E7074", 34, ch_tab(CH_LOBBY));
        ui_text("anim-group.mnChat.mcT1", t);
    }
}
static void ch_menu_tick(uint64_t now, int on) {
    uint64_t g = on ? ui_w("anim-group.mnChat") : 0;
    g_ch_menu_up = g != 0;
    if (!g) { g_ch_menu_grp = 0; return; }
    int lobby = ch_in_lobby();
    {   // the panel's tab: LOBBY while in a lobby (PARTY without one), unless the player picked one with TAB while typing (CHS.tab while where == 3)
        static int was_lobby;
        if (g_ch_ed.on && g_ch_where == 3) g_ch_mtab = CHS.tab == CH_LOBBY && lobby ? CH_LOBBY : CH_PARTY;
        else if (lobby != was_lobby) g_ch_mtab = lobby ? CH_LOBBY : CH_PARTY;
        else if (!lobby) g_ch_mtab = CH_PARTY;
        was_lobby = lobby;
    }
    for (int k = 0; k < 5; k++) chtw_tick(&g_ch_mtw[k]);
    static unsigned lgen, ugen; static uint64_t at; static int lparty = -1;
    int typing = g_ch_ed.on && g_ch_where == 3;
    int party = ch_in_party();
    static int lmt = -1;
    if (lmt != g_ch_mtab) { lmt = g_ch_mtab; lgen = ~0u; at = 0; }
    if (g != g_ch_menu_grp || ugen != g_ui_gen) {
        g_ch_menu_grp = g; ugen = g_ui_gen; lgen = ~0u;
        ch_menu_bind();
        ui_text("anim-group.mnChat.mcHdr", nt_pl() ? "CZAT" : "CHAT");
        w_visible(g, 1);
    }
    ch_menu_tabs(lobby);
    int mt = g_ch_mtab;
    if (lgen == CHS.gen && party == lparty && now - at < 1000) return;
    lgen = CHS.gen; lparty = party; at = now;
    char b[CH_BUF + 96];
    static ch_row_t rows[4];
    ch_tab_rows(mt, MC_LINE_W * CH_FIT, MC_LINE_PT, rows, 4);
    for (int k = 0; k < 4; k++) chtw_text(&g_ch_mtw[k], rows[k]);
    ui_visible("anim-group.mnChat.mcFu", typing);
    if (typing) { ced_view(&g_ch_ed, b, sizeof b, now, ch_fld_w(MC_FLD_X, MC_FCH_R, MC_FCH_PT, mt), MC_LINE_PT); chtw_text(&g_ch_mtw[4], b); }
    else if (mt == CH_LOBBY) chtw_text(&g_ch_mtw[4], nt_pl() ? "<font color=\"#6E7074\">ENTER - PISZ DO LOBBY</font>" : "<font color=\"#6E7074\">ENTER to chat with the lobby</font>");
    else if (party) chtw_text(&g_ch_mtw[4], nt_pl() ? "<font color=\"#6E7074\">ENTER - PISZ DO GRUPY</font>" : "<font color=\"#6E7074\">ENTER to chat with your party</font>");
    else chtw_text(&g_ch_mtw[4], nt_pl() ? "<font color=\"#6E7074\">BRAK GRUPY - P ZNAJOMI, BY ZAPROSIĆ</font>" : "<font color=\"#6E7074\">NO PARTY - P FRIENDS TO INVITE</font>");
    if (typing) { snprintf(b, sizeof b, "<font color=%c%s%c>%s</font>", 34, CH_COL[mt], 34, ch_tab(mt)); ui_text("anim-group.mnChat.mcFch", b); }
    else ui_text("anim-group.mnChat.mcFch", "");
}
// the menu side of the driver: the panel, Enter (only in a party), the typing line there
static void ch_menu_drive(uint64_t now, int in_match) {
    static uint64_t P_MM, P_FM;
    if (!P_MM) { P_MM = page_id("main-menu"); P_FM = page_id("find-match-menu"); }
    uint64_t top = top_page();
    int on = chat_on() && !in_match && (top == P_MM || top == P_FM);
    int foc = game_focused();
    int party = on && ch_in_party(), lobby = on && ch_in_lobby();
    if (g_ch_ed.on && g_ch_where == 3) {
        if (!on) ch_close("MP menu left");
        else if (!foc) ch_close("game lost focus");
        else if (!party && !lobby) ch_close("not in a party or a lobby any more");
        else ch_edit_tick();
    } else if (ch_enter_pressed(on && (party || lobby) && foc && !g_ch_ed.on)) {
        CHS.tab = g_ch_mtab == CH_LOBBY && lobby ? CH_LOBBY : party ? CH_PARTY : CH_LOBBY;
        ch_open(3);
    }
    ch_menu_tick(now, on);
}
// ------------------------------------------------------------------ the driver (main tick)
static uint64_t ch_pause_page(void) { static uint64_t id; if (!id) id = page_id("pause-menu"); return id; }
static void feature_chat(void) {
    uint64_t now = GetTickCount64();
    int in_match = match_substate() == 6;
    static int was_in;
    if (in_match != was_in) { was_in = in_match; if (in_match) { ch_clear_match(); memset(g_ch_seen, 0, sizeof g_ch_seen); } else ch_close("match over"); }
    ch_resend_tick(now);
    ch_net_tick(now, in_match);
    int en = chat_on() && in_match;
    if (!en) {
        if (g_ch_where != 3) ch_close("chat off / not in a match");
        ch_hud_tick(now, 0); g_ch_pause_up = 0;
        ch_menu_drive(now, in_match);                // the MP menu / FIND MATCH panel; it also arms or drops Enter
        return;
    }
    if (g_ch_where == 3) ch_close("match started");
    g_ch_menu_up = 0;
    if (CHS.tab >= CH_NCH) CHS.tab = 0;              // (LOBBY is the menu panel's only - the match box starts on MATCH)
    uint64_t top = top_page();
    int on_pause = top == ch_pause_page();
    int hud = !hud_menu_up();
    int foc = game_focused();
    if (g_ch_ed.on) {
        if (!foc) ch_close("game lost focus");
        else if ((g_ch_where == 1 && !hud) || (g_ch_where == 2 && !on_pause)) ch_close("page changed");
        else ch_edit_tick();
    } else if (ch_enter_pressed(foc && (hud || on_pause))) {
        ch_open(hud ? 1 : 2);
    }
    if (on_pause && !g_ch_ed.on && foc) {            // P on the ESC menu: the FRIENDS page over the match
        static int hp, hn;
        int pad = MENU_NEXT_TAB(&hn);
        if (GetAsyncKeyState('E') & 0x8000) pad = 0;     // (menu-next-tab is E on the keyboard: only P opens the page from the keyboard, as on the MP menu)
        if ((ne_key_edge('P', &hp) || pad) && fr13_enabled()) { ui_sfx("sfx-select"); fr13_open_from_pause(); }
    }
    ch_hud_tick(now, hud);
    ch_pause_tick(now, on_pause);
    if (on_pause) ch_pause_badge();
}
