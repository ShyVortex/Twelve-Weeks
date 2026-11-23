// friends13.c - the in-game FRIENDS / PARTY panel
// . Included after clan13.c (it reuses gearup13.c's fit / fade / repeat helpers). Log prefix "friendsui:".
//
// WHERE: a button strip "P  FRIENDS" (key tile P, a red badge with the number of friend requests + party invites waiting, and "n ONLINE" / "PARTY 2/4") sits directly ABOVE the LOBBY
// box on the right of the MP menu (to1/main-menu) and of FIND MATCH (to1/find-match-menu): x 2500..3682, y 266..386 of the 3840 x 2160 canvas (tools/features/friends13_widgets.py;
// MP menu layout: it was under the box, the CHAT panel sits there now).
// P (keyboard), the gamepad's menu-next (RB) or a click on the strip opens the page to1/friends13 (only on those two pages, never once the pre-match sequence / a match runs).
//
// PAGE (redesign: the shared No Return frame, breadcrumb MULTIPLAYER | FRIENDS, tile rows, one focus outline, boxed prompts): left PARTY (members with LEADER / READY / presence, then READY and LEAVE / DISBAND), right FRIENDS (ADD FRIEND typed in place, party invites, friend requests, friends online first,
// requests you sent). Keys: W / S / arrows / stick move, A / D / Tab / Q / E / LB / RB switch the list, Enter / SELECT does the row's main action (INVITE, ACCEPT, JOIN, MAKE LEADER,
// READY, LEAVE, type a name), X / Delete / the pad's menu-action the second one (REMOVE, DECLINE, KICK, CANCEL), R = ready, L = leave the party, P / Esc / BACK close.
// ADD FRIEND: Enter on the first row opens a text field over it (animated underline, blinking caret, placeholder): letters, digits, space - _ . : [ ], Ctrl+V pastes, Left / Right / Home / End
// move the caret, Backspace / Delete erase (the engine's pop of the page on Backspace is undone, see feature_friends13), Enter sends, Esc cancels typing, a second Esc closes (
// text fits its boxes, rows come in staggered, the page fades out on close, requests / invites pop up as a bottom-right card with Y / N, the toast block below).
//
// DATA: the daemon's friends service (tools/social.py), op 0xD8 [token][ver 1][lang][sub][arg] -> 0xD9 JSON, asked by this file's own short connection (like notice.c), parsed by friends13.h.
// The state is read every 3 s while the page is up, every 15 s on the menus otherwise (never in a match); an action goes first and its reply is the fresh state. A newly arrived
// friend request / party invite that no server notice announced pops as a toast (ntf_push) on the menus; notice.c keeps the server lines of a running match until the match is over.
// t2r-no-ingame-friends.txt next to the exe: off (no button, no page, no poll).
#include "friends13.h"
static void ntf_sound(void);                           // notify.c: the toast chime
#define FR_NL 6
#define FR_RROWS 7
#define FR_NPM 4
static int g_fr_off = -1;
static fr13_t g_f13;                                   // the last state (main thread only)
static uint64_t fr_page_id(void) { static uint64_t id; if (!id) id = page_id("friends13"); return id; }
static int fr13_enabled(void) {
    if (g_fr_off < 0) { FILE *f = exe_side_open("t2r-no-ingame-friends.txt", "r"); g_fr_off = f != NULL; if (f) fclose(f); xlog("friendsui: in-game FRIENDS panel %s", g_fr_off ? "off (t2r-no-ingame-friends.txt)" : "on"); }
    return !g_fr_off;
}
#define FRT(en, pl) (nt_pl() ? (pl) : (en))
// ------------------------------------------------------------------ MESSAGES
// . The page's third list (Tab / the bumpers cycle PARTY - FRIENDS - MESSAGES; M on a friend row opens that friend's chat):
// the recent conversations first (social.py "recent", newest first), then every other friend (a pad reaches anyone); the picked one's thread (S_CHAT, sub 14, asked while the list is up),
// the quick replies (1 - 4, a click, or the pad's left / right + ACTION) and a typing line (chat.c's editor over gearup13.c's key catcher: the game sees no key while it is open).
// Without a party the block sits under the NO PARTY text; with a party it takes the PARTY rows' place while it is the picked list. Widgets: friends13_widgets.messages (group "msg").
#define FR_ARGMAX 480                                  // bytes of one request's argument (S_MSG = "<friend id>\n<text>"; the daemon passes 420)
#define FM_MSG_ARG 420
#define FM_X 148.0f
#define FM_W 1676.0f
#define FM_Y_TOP 470.0f                                // the section's centre line: with a party (the PARTY rows' place) ...
#define FM_Y_LOW 760.0f                                // ... and without one (under the NO PARTY text)
#define FM_NV 5                                        // conversation tiles
#define FM_TY 54.0f
#define FM_TDY 146.0f
#define FM_TW 560.0f
#define FM_TH 130.0f
#define FM_PX 600.0f                                   // the thread panel (group-local)
#define FM_PW 1076.0f
#define FM_PH 646.0f
#define FM_NTL 5                                       // thread lines drawn (two text lines each)
#define FM_LDY 124.0f
#define FM_QLY 724.0f                                  // QUICK REPLY label centre, the chips' top, their point size / height
#define FM_QY 752.0f
#define FM_QPT 30.0f
#define FM_QH 46.0f
#define FM_QGAP 16.0f
#define FM_QTX_DN 3.0f                                 // the chip texts' centre line below the chip's (the caps sit high on the box's centre)
#define FM_FY 826.0f                                   // the typing line
#define FM_FH 96.0f
#define FM_NQ 4
typedef struct { char id[40], name[40], t[140], st[12]; int me, unread; } fm_ent_t;
static fm_ent_t g_fm_e[FR_NRC + FR_NF];
static int g_fm_n;
static struct {
    char with[40], wname[40];                          // the open conversation: friend id / name
    fr_th_t th[FR_NTH]; int nth, have_th;              // its lines (the last S_CHAT / S_MSG reply for it; our own sent line is added at once)
    int send_pending, inflight, fetch, held_at_parse;
    char send_arg[FR_ARGMAX];
    uint64_t sel_ms;
    int qf, hv_q, hv_fld;                              // the pad's quick reply; the chip / the field under the cursor
    float qx[FM_NQ], qw[FM_NQ], gy;
    ced_t ed;
} M13;
static int g_fr_from_pause;                             // fr13_open_from_pause: the next fr_enter opens on MESSAGES when something is unread
static void fm_reply(const fr13_t *d, int inflight);
static int fm_held(void);
static int fm_avail(void);
static int fm_shown(float *my);
static void fm_fill(void);
static void fm_type_stop(void);
static const char *fm_quick(int k, int shown);
// ------------------------------------------------------------------ the network (own short connection per request, one at a time)
static volatile LONG g_fr_busy, g_fr_have;            // have: 1 = a reply is in g_fr_rep, 2 = connected but no valid answer, 3 = no connection
static char g_fr_rep[60000];                           // (a S_CHAT reply carries up to 24000 bytes of thread on top of the state)
static volatile LONG g_fr_replen;
static struct { uint8_t pl[64 + 3 + FR_ARGMAX]; int n; } g_fr_job;
static DWORD WINAPI fr_worker(LPVOID arg) {
    (void)arg;
    HMODULE ws = LoadLibraryA("ws2_32.dll");
    t2r_sin a;
    t2r_net net;
    LONG res = 3;
    if (ws && hm_server(&a) && t2r_net_load(&net, ws)) {
        static uint8_t frame[3 + sizeof g_fr_job.pl];
        static char rep[sizeof g_fr_rep + 16];
        int n = g_fr_job.n + 1;
        frame[0] = (uint8_t)n; frame[1] = (uint8_t)(n >> 8); frame[2] = 0xD8;
        memcpy(frame + 3, g_fr_job.pl, (size_t)g_fr_job.n);
        int sent = 0;
        int got = t2r_rpc(&net, &a, frame, n + 2, rep, (int)sizeof rep - 1, 2500, 3500, 3500, &sent);
        if (sent) res = 2;
        int ln = got >= 3 ? (rep[0] & 0xff) + ((rep[1] & 0xff) << 8) : 0;
        if (ln >= 2 && got >= ln + 2 && (uint8_t)rep[2] == 0xD9 && ln - 1 < (int)sizeof g_fr_rep) {
            memcpy(g_fr_rep, rep + 3, (size_t)ln - 1);
            InterlockedExchange(&g_fr_replen, ln - 1);
            res = 1;
            srv_mark_alive();
        }
    }
    InterlockedExchange(&g_fr_have, res);
    InterlockedExchange(&g_fr_busy, 0);
    return 0;
}
static int fr_start(int sub, const char *arg) {       // 1 = a request went out
    static char tok[65];
    if (g_fr_busy) return 0;
    if (!tok[0] && !clan_token(tok)) { tok[0] = 0; return 0; }
    memcpy(g_fr_job.pl, tok, 64);
    g_fr_job.pl[64] = 1; g_fr_job.pl[65] = (uint8_t)nt_pl(); g_fr_job.pl[66] = (uint8_t)sub;
    size_t al = arg ? strlen(arg) : 0;
    if (al > FR_ARGMAX) al = FR_ARGMAX;
    if (al) memcpy(g_fr_job.pl + 67, arg, al);
    g_fr_job.n = 67 + (int)al;
    InterlockedExchange(&g_fr_busy, 1);
    HANDLE h = CreateThread(NULL, 0, fr_worker, NULL, 0, NULL);
    if (!h) { InterlockedExchange(&g_fr_busy, 0); return 0; }
    CloseHandle(h);
    return 1;
}
// ------------------------------------------------------------------ state
enum { A_NONE, A_TYPE, A_INVITE, A_ACCEPT, A_JOIN, A_DECLINE_P, A_DECLINE_R, A_REMOVE, A_CANCEL, A_PROMOTE, A_KICK, A_READY, A_LEAVE, A_ADD };
static struct {
    int have, fails, ok_once, dead, ver;
    uint64_t next_poll, ok_at;
    int act_pending, act_sub, act_inflight;            // a queued write (sub / arg), the write whose reply is awaited (sub; 0 none)
    char act_arg[64];
    int act_code;                                      // the A_* of the write in flight (for the message)
    int nf_before;
    uint64_t tseen[32]; int ntseen;                    // friend request / party invite ids a toast was already made for (hashes)
    char msg[200]; uint64_t msg_until;
    int last_badge, last_nf, last_nm, last_ni, last_npi;
} N13;
static struct {
    int up, closing, dirty, col, foc[3], off[3], typing, blen, stage;      // col: 0 PARTY, 1 FRIENDS, 2 MESSAGES
    char buf[40];
    uint64_t enter_ms, back_f, sfx_ms, t_u, t_d, bs_t0;
    int h_sel, h_u, h_d, h_l, h_r, h_back, h_esc, h_pv, h_nx, h_act, hk[256], h_click;
    int hv_col, hv_row, hv_back, hv_sel, hv_act, hv_sw;
    uint64_t click_f;                                  // frame of the last click (the engine's menu-select that rides on a mouse click is dropped, like gear up)
    int caret;                                         // typing: byte offset of the caret in buf (always on a character boundary)
    uint64_t typ_ms, edit_ms, bs_ms, close_ms, rep_t[4];   // typing started / last edit (caret stays solid) / a Backspace was last seen down / the close fade began / key-repeat timers (left, right, backspace, delete)
    float inp_a, ph_a;                                 // the text field's and the placeholder's smoothed alpha
    uint64_t rw[2][8];                                 // row group handles (re-resolved with every fill)
    float rfx[2][8];                                   // focus nudge of a row (0..1)
    int rq[2][8], rqx[2][8];                           // last written alpha / x step of a row (-1 = nothing written yet)
    int ul_q, gl_q, ia_q, pa_q;                        // last written steps of the field's underline / glow / group alpha / placeholder alpha
} F13;
static struct { int valid; int typing, blen, caret, col, foc[3], off[3]; char buf[40]; uint64_t typ_ms; } K13;   // typing state carried over the engine's pop on Backspace (the page is pushed again)
static const char *fr_err(const char *c) {
    if (!strcmp(c, "self")) return FRT("THAT IS YOU", "TO TY");
    if (!strcmp(c, "unknown")) return FRT("NO PLAYER WITH THAT NAME OR STEAM ID (THEY MUST HAVE PLAYED ONCE)", "NIE ZNALEZIONO GRACZA O TEJ NAZWIE LUB ID STEAM");
    if (!strcmp(c, "ambiguous")) return FRT("MORE THAN ONE PLAYER HAS THAT NAME - USE THE STEAM ID", "KILKU GRACZY MA TĄ NAZWĘ - UŻYJ ID STEAM");
    if (!strcmp(c, "already")) return FRT("YOU ARE ALREADY FRIENDS", "JESTEŚCIE JUŻ ZNAJOMYMI");
    if (!strcmp(c, "pending")) return FRT("YOU ALREADY SENT THIS PLAYER A REQUEST", "ZAPROSZENIE JUŻ WYSŁANE");
    if (!strcmp(c, "limit")) return FRT("THE LIMIT OF FRIENDS OR OPEN REQUESTS IS REACHED", "OSIĄGNIĘTO LIMIT ZNAJOMYCH LUB ZAPROSZEŃ");
    if (!strcmp(c, "expired")) return FRT("THAT REQUEST OR INVITE IS NO LONGER VALID", "TO ZAPROSZENIE JEST JUŻ NIEAKTUALNE");
    if (!strcmp(c, "rate")) return FRT("TOO MANY ACTIONS - WAIT A MOMENT", "ZA DUŻO AKCJI - POCZEKAJ CHWILĘ");
    if (!strcmp(c, "notfriend")) return FRT("YOU CAN ONLY INVITE FRIENDS", "ZAPRASZAĆ MOŻNA TYLKO ZNAJOMYCH");
    if (!strcmp(c, "offline")) return FRT("THAT FRIEND IS OFFLINE", "TEN ZNAJOMY JEST OFFLINE");
    if (!strcmp(c, "notleader")) return FRT("ONLY THE PARTY LEADER CAN DO THAT", "TYLKO LIDER GRUPY MOŻE TO ZROBIĆ");
    if (!strcmp(c, "full")) return FRT("THE PARTY IS FULL", "GRUPA JEST PEŁNA");
    if (!strcmp(c, "notmember")) return FRT("THAT PLAYER IS NOT IN YOUR PARTY", "TEN GRACZ NIE JEST W TWOJEJ GRUPIE");
    if (!strcmp(c, "noparty")) return FRT("YOU ARE NOT IN A PARTY", "NIE MASZ GRUPY");
    if (!strcmp(c, "match")) return FRT("NOT POSSIBLE DURING A MATCH", "NIEMOŻLIWE W TRAKCIE MECZU");
    return FRT("SOMETHING WENT WRONG - TRY AGAIN", "COŚ POSZŁO NIE TAK - SPRÓBUJ PONOWNIE");
}
static void fr_msg(const char *text, int good) {
    snprintf(N13.msg, sizeof N13.msg, "<font color=\"#F0F0F0\">%s</font>", text);       // (the page has two text colours, the message is white, good or not)
    (void)good;
    N13.msg_until = GetTickCount64() + 6000;
    F13.dirty = 1;
}
static const char *fr_ok_text(int code, int became_friends) {
    switch (code) {
    case A_ADD: return became_friends ? FRT("FRIEND ADDED", "ZNAJOMY DODANY") : FRT("FRIEND REQUEST SENT", "ZAPROSZENIE WYSŁANE");
    case A_ACCEPT: return FRT("REQUEST ACCEPTED", "ZAPROSZENIE PRZYJĘTE");
    case A_INVITE: return FRT("PARTY INVITE SENT", "ZAPROSZENIE DO GRUPY WYSŁANE");
    case A_JOIN: return FRT("YOU JOINED THE PARTY", "DOŁĄCZASZ DO GRUPY");
    case A_LEAVE: return FRT("YOU LEFT THE PARTY", "OPUSZCZASZ GRUPĘ");
    case A_PROMOTE: return FRT("NEW PARTY LEADER", "NOWY LIDER GRUPY");
    case A_KICK: return FRT("REMOVED FROM THE PARTY", "USUNIĘTO Z GRUPY");
    case A_REMOVE: return FRT("FRIEND REMOVED", "ZNAJOMY USUNIĘTY");
    case A_DECLINE_R: case A_DECLINE_P: case A_CANCEL: return FRT("DONE", "GOTOWE");
    default: return "";
    }
}
static void ft_push(int kind, const char *id, const char *name, const char *text, float secs, uint64_t delay_ms);
static int fr_toast_enabled(void);
enum { FT_REQ, FT_PINV, FT_GOOD, FT_BAD, FT_INFO };
// ------------------------------------------------------------------ toasts for what the server notices did not announce (and the dedupe against them)
static struct { char t[300]; uint64_t at; } g_fr_pl[8];
static int g_fr_pl_n;
static void fr13_note_seen(const char *text) {        // notice.c: a friends / party line was shown or queued
    snprintf(g_fr_pl[g_fr_pl_n & 7].t, sizeof g_fr_pl[0].t, "%s", text ? text : "");
    g_fr_pl[g_fr_pl_n & 7].at = GetTickCount64();
    g_fr_pl_n++;
}
static int fr_noted(const char *name) {
    uint64_t now = GetTickCount64();
    for (int i = 0; i < 8; i++) if (g_fr_pl[i].t[0] && now - g_fr_pl[i].at < 600000 && name[0] && strstr(g_fr_pl[i].t, name)) return 1;
    return 0;
}
static uint64_t fr_h(const char *kind, const char *id) {
    uint64_t h = 1469598103934665603ULL;
    for (const char *p = kind; *p; p++) h = (h ^ (uint8_t)*p) * 1099511628211ULL;
    for (const char *p = id; *p; p++) h = (h ^ (uint8_t)*p) * 1099511628211ULL;
    return h;
}
static int fr_tseen(uint64_t h) { for (int i = 0; i < 32 && i < N13.ntseen; i++) if (N13.tseen[i] == h) return 1; return 0; }
static void fr_toasts(const fr13_t *d, int panel_up) {
    int shown = 0;
    for (int k = 0; k < 2; k++) {
        int n = k ? d->npi : d->ni;
        for (int i = 0; i < n; i++) {
            const fr_r_t *r = k ? &d->pinv[i] : &d->in[i];
            uint64_t h = fr_h(k ? "i" : "r", r->id);
            if (fr_tseen(h)) continue;
            N13.tseen[N13.ntseen++ & 31] = h;
            if (panel_up) continue;
            if (fr_toast_enabled()) {                                // the card: Y accepts / joins, N declines (an old backlog shows 3 at most, the badge counts the rest)
                if (shown >= 3) continue;
                ft_push(k ? FT_PINV : FT_REQ, r->id, r->name, "", k ? 16.0f : 12.0f, 0);
                shown++;
                continue;
            }
            if (shown >= 2 || fr_noted(r->name)) continue;
            char m[200];
            if (k) snprintf(m, sizeof m, FRT("PARTY: %s invited you to a party. Press P to open FRIENDS and join.", "GRUPA: %s zaprasza cię do grupy. Wciśnij P, aby otworzyć ZNAJOMYCH i dołączyć."), r->name);
            else snprintf(m, sizeof m, FRT("%s sent you a friend request. Press P to open FRIENDS.", "%s wysyła ci zaproszenie do znajomych. Wciśnij P, aby otworzyć ZNAJOMYCH."), r->name);
            if (ntf_push(NTF_SERVER, m, 9.0f)) { shown++; xlog("friendsui: toast \"%s\"", m); }
        }
    }
}
// t2r-ext.c feature_join_in_progress: the [0xA8] note tag of the in-match clock poll moved = a friends / party note waits.
// The notice line (MESSAGE FROM / PARTY ...) is fetched now and the friends state asked once (in a match it is otherwise not polled): its invite / request card.
static int g_fr_poke;
static void fr13_note_poke(int tag) {
    g_nt_ask_now = 1;
    g_fr_poke = 1; N13.next_poll = 0;
    xlog("friendsui: note tag %d from the clock poll - notice line + friends state asked now", tag);
}
static void fr_net_tick(uint64_t now, int panel_up, int menu_ok) {
    LONG have = InterlockedExchange(&g_fr_have, 0);
    if (have == 1) {
        static fr13_t tmp;
        if (fr13_parse(&tmp, g_fr_rep, (size_t)g_fr_replen)) {
            for (int i = 0; i < tmp.nrc; i++) ch_censor(tmp.rc[i].t);          // chat.h slur filter: friend messages too
            for (int i = 0; i < tmp.nth; i++) ch_censor(tmp.th[i].t);
            if (N13.act_inflight) {
                if (!tmp.ok) { fr_msg(fr_err(tmp.err), 0); ui_sfx("sfx-menu-error"); xlog("friendsui: action %d refused: %s", N13.act_inflight, tmp.err); if (!panel_up && fr_toast_enabled()) ft_push(FT_BAD, "", "", fr_err(tmp.err), 5.5f, 0); }
                else { const char *ok_t = fr_ok_text(N13.act_code, tmp.nf > N13.nf_before); fr_msg(ok_t, 1); xlog("friendsui: action %d ok", N13.act_inflight); if (!panel_up && fr_toast_enabled() && ok_t[0]) ft_push(FT_GOOD, "", "", ok_t, 4.5f, 0); }
                N13.act_inflight = 0;
            }
            fm_reply(&tmp, M13.inflight); M13.inflight = 0; M13.held_at_parse = fm_held();
            if (N13.have && tmp.unread_total > g_f13.unread_total) g_nt_ask_now = 1;    // a new message: its notice line (the toast) is fetched at once (notice.c)
            g_f13 = tmp; N13.have = 1; N13.ver++; N13.ok_at = now; N13.fails = 0; N13.ok_once = 1;
            if (g_f13.nf != N13.last_nf || g_f13.nm != N13.last_nm || g_f13.ni != N13.last_ni || g_f13.npi != N13.last_npi) {
                N13.last_nf = g_f13.nf; N13.last_nm = g_f13.nm; N13.last_ni = g_f13.ni; N13.last_npi = g_f13.npi;
                xlog("friendsui: state: %d friends, %d requests in, %d out, %d party invites, party of %d%s", g_f13.nf, g_f13.ni, g_f13.no, g_f13.npi, g_f13.nm, g_f13.me_leader ? " (leader)" : "");
            }
            fr_toasts(&g_f13, panel_up);
            F13.dirty = 1;
        } else { xlog("friendsui: the reply did not parse (%ld bytes)", (long)g_fr_replen); N13.act_inflight = 0; M13.inflight = 0; N13.next_poll = now + 10000; }
    } else if (have == 2 || have == 3) {
        N13.fails++;
        if (N13.act_inflight) { fr_msg(FRT("NO ANSWER FROM THE SERVER", "SERWER NIE ODPOWIADA"), 0); if (!panel_up && fr_toast_enabled()) ft_push(FT_BAD, "", "", FRT("NO ANSWER FROM THE SERVER", "SERWER NIE ODPOWIADA"), 5.5f, 0); N13.act_inflight = 0; }
        if (M13.inflight) { fr_msg(FRT("MESSAGE NOT SENT - NO ANSWER FROM THE SERVER", "NIE WYSŁANO - SERWER NIE ODPOWIADA"), 0); M13.inflight = 0; }
        N13.next_poll = now + (N13.fails < 3 ? 6000 : 20000);
        // (no "older server - not asking again" latch any more. Every live server answers op 0xD8; the latch fired on a game started
        //  during a daemon restart (3 polls without a reply) and left FRIENDS on THE SERVER DID NOT ANSWER for the whole session.
        //  Failed polls back off to 20 s and opening the page asks again at once.)
        if (N13.fails == 3) xlog("friendsui: the server did not answer op 0xD8 3 times - asking every 20 s");
        F13.dirty = 1;
    }
    if (N13.dead || g_fr_busy) return;
    if (N13.act_pending) {
        if (fr_start(N13.act_sub, N13.act_arg)) { N13.act_pending = 0; N13.act_inflight = N13.act_sub; }
        return;
    }
    if (M13.send_pending) {                                                  // a message (S_MSG; its reply carries the thread)
        if (fr_start(13, M13.send_arg)) { M13.send_pending = 0; M13.inflight = 1; }
        return;
    }
    int th = panel_up && M13.with[0] && (F13.col == 2 || !g_f13.has_party);    // the MESSAGES block is up: S_CHAT (the state + the open thread) instead of S_STATE
    if (th && M13.fetch && now - M13.sel_ms >= 200) {
        if (fr_start(14, M13.with)) { M13.fetch = 0; N13.next_poll = now + 3000; }
        return;
    }
    if (!(menu_ok || panel_up || g_fr_poke) || now < N13.next_poll) return;              // (the page over the ESC menu polls in a match too; g_fr_poke: one poll for a new note)
    g_fr_poke = 0;
    if (fr_start(th ? 14 : 1, th ? M13.with : "")) N13.next_poll = now + (panel_up ? 3000 : g_f13.has_party ? 2500 : 15000);     // (in a party the ready tabs / the leader's search follow within a few seconds)
}
static void fr_act_queue(int code, int sub, const char *arg) {
    N13.act_sub = sub; snprintf(N13.act_arg, sizeof N13.act_arg, "%s", arg ? arg : "");
    N13.act_code = code; N13.act_pending = 1; N13.nf_before = g_f13.nf;
    ui_sfx("sfx-select");
    xlog("friendsui: action %d (sub %d %s)", code, sub, sub == 3 ? "<typed>" : N13.act_arg);
}
// ------------------------------------------------------------------ the toast (notifications in the bottom right corner for friend invites and party invites)
// ONE card (widgets frToast, friends13_widgets.add_toast: x 2480..3720, y 1760..1940 of the 3840 x 2160 canvas = bottom right, inset 120 from the right edge, above the footer, below the
// FRIENDS strip) on the MP menu and FIND MATCH while the menu is really showing (the same moments as the strip). Friend requests and party invites carry the sender's name and the keys
// Y (accept / join) and N (decline) - or a click on the chip; everything else the server says about friends / party (notice lines kind p) is a plain card. More than one waiting: one after the other,
// the card says "+n". Timing: slide in from the right (170 units) + fade over 260 ms (ease-out cubic); hold 12 s (request) / 16 s (party invite) / 4.5 s (result) / the server's seconds (info),
// a progress line under the card runs out meanwhile and stands still while the cursor is on the card; slide out 70 units + fade over 220 ms (ease-in). The card never shows over the FRIENDS page
// (its items are on the list), leaves the moment the menu stops showing (the rest of its time waits) and is never drawn in a match (lines wait for the match end, notice.c).
// t2r-no-friend-toast.txt next to the exe: the old one-line toasts (ntf_push) instead.
#define FT_N 6
#define FT_X 2480.0f
#define FT_Y 1760.0f
#define FT_W 1240.0f
#define FT_H 180.0f
#define FT_IN_MS 260.0f
#define FT_OUT_MS 220.0f
// FT_REQ, FT_PINV, FT_GOOD, FT_BAD, FT_INFO (enum above) = the order of the accent bars tAc0..4
typedef struct { int kind; char id[40], name[36], text[160]; float secs; uint64_t ready_at; } ft_item_t;
static ft_item_t g_ftq[FT_N];
static int g_ftqn, g_ft_off = -1, g_ft_missing;
static struct { int st; ft_item_t it; uint64_t t0, t_out, last; float left_ms, total_ms; int hov, hy, hn, hky, hkn, qa, qx, qb; uint64_t gw; uint64_t cool; int hide, hud; } T13;   // st: 0 idle, 1 in, 2 hold, 3 out
static int fr_toast_enabled(void) {
    if (g_ft_off < 0) { FILE *f = exe_side_open("t2r-no-friend-toast.txt", "r"); g_ft_off = f != NULL; if (f) fclose(f); xlog("friendsui: friend / party toast card %s", g_ft_off ? "off (t2r-no-friend-toast.txt)" : "on"); }
    return !g_ft_off && !g_ft_missing;
}
static float ft_ease(float k) { if (k < 0.0f) k = 0.0f; if (k > 1.0f) k = 1.0f; return 1.0f - (1.0f - k) * (1.0f - k) * (1.0f - k); }
static const char *ft_p(const char *leaf) { static char b[4][64]; static int n; char *o = b[n++ & 3]; if (!leaf) return "anim-group.frToast"; snprintf(o, 64, "anim-group.frToast.%s", leaf); return o; }
// the same card in a match:
// a copy of frToast on the HUD page (to1/currency-hud: frHud > frToast at FT_HY, friends13_widgets.add_friends_toast), found through hud_widget. g_ft_hud
// picks which copy the ft_* helpers below write; it follows the card (T13.hud) once one shows. No cursor on the HUD: Y / N only (not while typing in the chat).
#define FT_HY 1500.0f
static int g_ft_hud, g_ft_hud_missing;
static uint64_t ft_w(const char *leaf) { return g_ft_hud ? hud_widget("frHud", "frToast", leaf) : ui_w(ft_p(leaf)); }
static void ft_vis(const char *leaf, int on) { if (!g_ft_hud) { ui_visible(ft_p(leaf), on); return; } uint64_t w = ft_w(leaf); if (w) w_visible(w, on); }
static void ft_txt(const char *leaf, const char *t) { if (!g_ft_hud) { ui_text(ft_p(leaf), t); return; } uint64_t w = ft_w(leaf); if (w) chw_set_hud(w, t); }
static void ft_img(const char *leaf, const char *img) { if (!g_ft_hud) { ui_image(ft_p(leaf), img); return; } uint64_t w = ft_w(leaf); if (w) ((fn_settext_t)VMA(0x180068260))(w, img); }
static void ft_fit(const char *leaf, const char *t, float box, float pt) {     // gu_fit for either copy (the HUD copy: scale only, the names are short)
    if (!g_ft_hud) { gu_fit(ft_p(leaf), t, box, pt); return; }
    uint64_t w = ft_w(leaf);
    if (!w) return;
    const char *tr = loc_tr(t);
    const char *src = tr ? tr : t;
    float est = 0.0f;
    for (const unsigned char *q = (const unsigned char *)src; *q; q++) if ((*q & 0xC0) != 0x80) est += gu_cw(q);
    est *= pt;
    float sc = est > box ? box / est : 1.0f;
    if (sc < 0.6f) sc = 0.6f;
    chw_set_hud(w, src);
    w_scale(w, sc, sc);
}
static float ft_y(void) { return g_ft_hud ? FT_HY : FT_Y; }
static int fr_menu_vis(void) { return !g_veil_on && !g_pm.pending && g_lo_state == LO_NONE && ms_on_menu() && g_mf_code_now < 100 && !g_mh_load && !g_mh_st && !g_ls_own; }
static int ft_act(int kind) { return kind == FT_REQ || kind == FT_PINV; }
static int ft_pending(const ft_item_t *it) {              // an actionable card is only worth showing while the request / invite still waits on the server
    if (!ft_act(it->kind) || !N13.have) return 1;
    if (it->kind == FT_REQ) { for (int i = 0; i < g_f13.ni; i++) if (!strcmp(g_f13.in[i].id, it->id)) return 1; }
    else for (int i = 0; i < g_f13.npi; i++) if (!strcmp(g_f13.pinv[i].id, it->id)) return 1;
    return 0;
}
static void ft_push(int kind, const char *id, const char *name, const char *text, float secs, uint64_t delay_ms) {
    for (int i = 0; i < g_ftqn; i++) {                    // the same card is not queued twice
        if (g_ftq[i].kind == kind && (id[0] ? !strcmp(g_ftq[i].id, id) : !strcmp(g_ftq[i].text, text))) return;
    }
    if (T13.st && T13.it.kind == kind && (id[0] ? !strcmp(T13.it.id, id) : !strcmp(T13.it.text, text))) return;
    if (g_ftqn >= FT_N) {                                 // full: the oldest plain card gives way, else the oldest
        int k = 0;
        for (int i = 0; i < g_ftqn; i++) if (!ft_act(g_ftq[i].kind)) { k = i; break; }
        memmove(g_ftq + k, g_ftq + k + 1, sizeof g_ftq[0] * (size_t)(g_ftqn - k - 1)); g_ftqn--;
    }
    ft_item_t *q = &g_ftq[g_ftqn++];
    memset(q, 0, sizeof *q);
    q->kind = kind; q->secs = secs; q->ready_at = GetTickCount64() + delay_ms;
    snprintf(q->id, sizeof q->id, "%s", id); snprintf(q->name, sizeof q->name, "%s", name); snprintf(q->text, sizeof q->text, "%s", text);
    xlog("friendsui: toast queued kind %d \"%s\" \"%.80s\" %.1f s", kind, name, text, secs);
}
// notice.c: a friends / party line of the server (kind p). 1 = the card takes it (it then waits for the state poll, so a request line is dropped when its own card shows), 0 = the old toast
static int fr13_toast_line(const char *text, float secs) {
    if (!fr13_enabled() || !fr_toast_enabled() || !text || !text[0]) return 0;
    char t[160];
    size_t n = strlen(text);
    if (n >= sizeof t) { n = 96; while (n > 0 && ((unsigned char)text[n] & 0xC0) == 0x80) n--; memcpy(t, text, n); memcpy(t + n, "...", 4); }
    else memcpy(t, text, n + 1);
    // 1.8 s wait: a request / invite line gives way to its own card (Y / N) when the state poll brings it. A message has no card - it shows at once.
    int msg = !strncmp(t, "MESSAGE FROM ", 13) || !strncmp(t, "WIADOMOŚĆ OD ", sizeof "WIADOMOŚĆ OD " - 1);
    ft_push(FT_INFO, "", "", t, secs >= 2.0f && secs < 60.0f ? secs : 6.0f, msg ? 0 : 1800);
    N13.next_poll = 0;                                      // ask for the state now: its request / invite card (with the Y / N keys) replaces the line
    return 1;
}
static int ft_names_pending(const char *text) {
    for (int i = 0; i < g_f13.ni; i++) if (g_f13.in[i].name[0] && strstr(text, g_f13.in[i].name)) return 1;
    for (int i = 0; i < g_f13.npi; i++) if (g_f13.pinv[i].name[0] && strstr(text, g_f13.pinv[i].name)) return 1;
    return 0;
}
static void ft_flush_old(void) {                         // no toast widgets in this pak: the queued cards go the old way
    for (int i = 0; i < g_ftqn; i++) {
        char m[200];
        const ft_item_t *q = &g_ftq[i];
        if (q->kind == FT_REQ) snprintf(m, sizeof m, FRT("%s sent you a friend request. Press P to open FRIENDS.", "%s wysyła ci zaproszenie do znajomych. Wciśnij P, aby otworzyć ZNAJOMYCH."), q->name);
        else if (q->kind == FT_PINV) snprintf(m, sizeof m, FRT("PARTY: %s invited you to a party. Press P to open FRIENDS and join.", "GRUPA: %s zaprasza cię do grupy. Wciśnij P, aby otworzyć ZNAJOMYCH i dołączyć."), q->name);
        else snprintf(m, sizeof m, "%s", q->text);
        ntf_push(NTF_SERVER, m, q->secs);
    }
    g_ftqn = 0;
}
static const char *ft_icon(int kind) { return kind == FT_REQ ? "streaming/t2r/icons/notify-revive.png" : kind == FT_BAD ? "streaming/t2r/icons/notify-warn.png" : "streaming/t2r/icons/notify-info.png"; }
static void ft_fill(void) {                               // the card's texts / bars for T13.it (the widgets are hidden or at alpha 0 meanwhile)
    const ft_item_t *it = &T13.it;
    int act = ft_act(it->kind);
    for (int k = 0; k < 5; k++) { char l[8]; snprintf(l, sizeof l, "tAc%d", k); ft_vis(l, k == it->kind); }
    ft_img("tIc", ft_icon(it->kind));
    ft_txt("tKick", it->kind == FT_REQ ? FRT("FRIEND REQUEST", "ZAPROSZENIE DO ZNAJOMYCH") : it->kind == FT_PINV ? FRT("PARTY INVITE", "ZAPROSZENIE DO GRUPY") : FRT("FRIENDS", "ZNAJOMI"));
    ft_vis("tName", act); ft_vis("tSub", act); ft_vis("tInfo", !act);
    if (act) {
        ft_fit("tName", it->name, 640.0f, 54.0f);
        ft_fit("tSub", it->kind == FT_REQ ? FRT("WANTS TO BE YOUR FRIEND", "CHCE ZOSTAĆ TWOIM ZNAJOMYM") : FRT("INVITES YOU TO A PARTY", "ZAPRASZA CIĘ DO GRUPY"), 650.0f, 33.0f);
        ft_txt("tInfo", "");
    } else { ft_txt("tName", ""); ft_txt("tSub", ""); ft_txt("tInfo", it->text); }
    static const char *const CH[2] = {"Y", "N"};
    for (int c = 0; c < 2; c++) {
        char l[12];
        snprintf(l, sizeof l, "tKe%s", CH[c]); ft_vis(l, act);
        snprintf(l, sizeof l, "tKt%s", CH[c]); ft_vis(l, act);
        snprintf(l, sizeof l, "tLb%s", CH[c]); ft_vis(l, act);
        const char *lab = !act ? "" : c == 0 ? (it->kind == FT_REQ ? FRT("ACCEPT", "PRZYJMIJ") : FRT("JOIN", "DOŁĄCZ")) : FRT("DECLINE", "ODRZUĆ");
        ft_fit(l, lab, 232.0f, 38.0f);
    }
    char m[16];
    snprintf(m, sizeof m, "+%d", g_ftqn);
    ft_txt("tMore", g_ftqn > 0 ? m : "");
    w_scale(ft_w("tBar"), 1.0f, 1.0f);
    T13.qa = T13.qx = T13.qb = -1;
}
static int ft_cursor(float *rx0, float *ry0) {            // the cursor relative to the card's resting place (canvas units); 0 = no cursor in the window
    float cx, cy;
    if (g_ft_hud || !ui_cursor_canvas(&cx, &cy)) return 0;      // (no cursor on the HUD copy)
    *rx0 = cx - FT_X; *ry0 = cy - FT_Y;
    return 1;
}
static int fr_toast_hit(void) {                           // the cursor is on a showing actionable card (a click there is not for the menu button under it)
    float x, y;
    return (T13.st == 1 || T13.st == 2) && !T13.hud && ft_act(T13.it.kind) && ft_cursor(&x, &y) && x >= 0 && x <= FT_W && y >= 0 && y <= FT_H;
}
static void ft_end(uint64_t now) {                        // the card is over: hidden now when this page still has it, else (another page on top) the next menu moment hides it
    int was = g_ft_hud;
    g_ft_hud = T13.hud;                                     // (the copy the card was on)
    uint64_t g = ft_w(NULL);
    if (g) { w_alpha(g, 0.0f); ft_vis(NULL, 0); T13.hide = 0; } else T13.hide = 1;
    g_ft_hud = was;
    T13.st = 0; T13.cool = now + 350;
}
static void ft_tick(uint64_t now, int panel, int on_page, int hud) {
    if (!fr13_enabled()) return;
    if (!fr_toast_enabled()) { if (g_ftqn) ft_flush_old(); return; }
    if (hud && g_ft_hud_missing) { if (g_ftqn) ft_flush_old(); return; }   // (an older widget pak: no HUD copy - the one-line toasts in a match)
    if (!T13.st) g_ft_hud = hud;                            // (a showing card stays on its copy; a switch of copy below ends it)
    if (panel) {                                            // the FRIENDS page shows them all: no card on top of it, the actionable ones are done
        int k = 0;
        for (int i = 0; i < g_ftqn; i++) if (!ft_act(g_ftq[i].kind)) g_ftq[k++] = g_ftq[i];
        g_ftqn = k;
        if (T13.st && ft_act(T13.it.kind)) ft_end(now);
        T13.last = 0;
    }
    int ok = !panel && (hud ? 1 : on_page && fr_menu_vis());
    if (T13.st && T13.hud != hud) ok = 0;                   // menu <-> match while a card shows: it ends, the rest of its time waits
    float dt = T13.last ? (float)(now - T13.last) : 16.0f;
    T13.last = now;
    if (dt > 100.0f) dt = 100.0f;
    if (T13.st && !ok) {                                    // the menu stopped showing: the card goes at once, what is left of its time waits for the next menu moment
        ft_item_t it = T13.it;
        float left = T13.left_ms;
        ft_end(now);
        if (left > 1500.0f && ft_pending(&it) && g_ftqn < FT_N) { memmove(g_ftq + 1, g_ftq, sizeof g_ftq[0] * (size_t)g_ftqn); g_ftq[0] = it; g_ftq[0].secs = left / 1000.0f; g_ftq[0].ready_at = 0; g_ftqn++; }
        return;
    }
    if (!T13.st) {
        if (!ok || now < T13.cool) return;
        if (T13.hide) ft_end(now);
        int pick = -1;
        for (int i = 0; i < g_ftqn && pick < 0; i++) {
            ft_item_t *q = &g_ftq[i];
            if (now < q->ready_at) continue;
            if (!ft_pending(q) || (q->kind == FT_INFO && N13.have && ft_names_pending(q->text))) {        // gone from the server / announced by its own card
                xlog("friendsui: toast dropped (%s) \"%s\"", ft_act(q->kind) ? "no longer pending" : "its request card shows", ft_act(q->kind) ? q->name : q->text);
                memmove(g_ftq + i, g_ftq + i + 1, sizeof g_ftq[0] * (size_t)(g_ftqn - i - 1)); g_ftqn--; i--;
                continue;
            }
            pick = i;
        }
        if (pick < 0) return;
        static int miss, miss_h;
        uint64_t gw = ft_w(NULL);
        if (!gw && hud) { if (++miss_h > 240) { g_ft_hud_missing = 1; xlog("friendsui: no frHud/frToast on the HUD page (older gui2-widgets.pak) - one-line toasts in a match"); ft_flush_old(); } return; }
        if (!gw) { if (++miss > 240) { g_ft_missing = 1; xlog("friendsui: no frToast widgets on this page (older gui2-widgets.pak) - the old one-line toasts stay"); ft_flush_old(); } return; }
        if (hud) miss_h = 0; else miss = 0;
        T13.it = g_ftq[pick];
        memmove(g_ftq + pick, g_ftq + pick + 1, sizeof g_ftq[0] * (size_t)(g_ftqn - pick - 1)); g_ftqn--;
        T13.gw = gw; T13.st = 1; T13.t0 = now; T13.hud = hud;
        T13.total_ms = T13.left_ms = T13.it.secs * 1000.0f;
        T13.hky = (GetAsyncKeyState('Y') & 0x8000) != 0; T13.hkn = (GetAsyncKeyState('N') & 0x8000) != 0;     // held on arrival = no press
        ft_fill();
        w_alpha(gw, 0.0f);
        w_pivot(gw, FT_X + 85.0f, ft_y());                  // (the slide-in's first place; the HUD copy's group is not where the menu one is)
        ft_vis(NULL, 1);
        ntf_sound();
        xlog("friendsui: toast shown kind %d \"%s\" %.1f s%s", T13.it.kind, T13.it.name[0] ? T13.it.name : T13.it.text, (double)T13.it.secs, hud ? " (HUD, in a match)" : "");
        return;
    }
    uint64_t gw = ft_w(NULL);
    if (!gw) { T13.st = 0; return; }
    if (gw != T13.gw) { T13.gw = gw; ft_fill(); ft_vis(NULL, 1); }          // the page was rebuilt under us
    int act = ft_act(T13.it.kind);
    float cx, cy;
    int cur = ft_cursor(&cx, &cy);
    int hov = cur && cx >= 0 && cx <= FT_W && cy >= 0 && cy <= FT_H;
    int hy = act && hov && cx >= 852 && cx <= 852 + 340 && cy >= 26 && cy <= 88, hn = act && hov && cx >= 852 && cx <= 852 + 340 && cy >= 98 && cy <= 160;
    if (!hud) { gu_fade(ft_p("tFillY"), hy); gu_fade(ft_p("tFillN"), hn); gu_fade_tick(now); }
    if (T13.st != 3) {
        if (!hov) T13.left_ms -= dt;                         // the cursor on the card stops the clock
        if (T13.st == 1 && (float)(now - T13.t0) >= FT_IN_MS) T13.st = 2;
        int kok = game_focused() && !(hud && g_ch_ed.on);   // (in a match: not while the chat's typing line has the keys)
        int ky = kok && ne_key_edge('Y', &T13.hky), kn = kok && ne_key_edge('N', &T13.hkn);
        int cl = g_click_edge && act && (hy || hn);
        if (cl) { ky = hy; kn = hn; }
        if (act && (ky || kn)) {
            const ft_item_t *it = &T13.it;
            if (ky) { if (it->kind == FT_REQ) fr_act_queue(A_ACCEPT, 4, it->id); else fr_act_queue(A_JOIN, 7, it->id); }
            else { if (it->kind == FT_REQ) fr_act_queue(A_DECLINE_R, 5, it->id); else fr_act_queue(A_DECLINE_P, 8, it->id); }
            xlog("friendsui: toast %s \"%s\" (%s)", ky ? "accepted" : "declined", it->name, cl ? "click" : "key");
            T13.st = 3; T13.t_out = now;
        } else if (T13.left_ms <= 0.0f) { T13.st = 3; T13.t_out = now; }
        else if (act && !ft_pending(&T13.it)) { T13.st = 3; T13.t_out = now; }          // answered somewhere else / expired
    }
    float a, dx;
    if (T13.st == 1) { float e = ft_ease((float)(now - T13.t0) / FT_IN_MS); a = e; dx = (1.0f - e) * 170.0f; }
    else if (T13.st == 2) { a = 1.0f; dx = 0.0f; }
    else {
        float p = (float)(now - T13.t_out) / FT_OUT_MS;
        if (p >= 1.0f) { ft_end(now); return; }
        a = 1.0f - p; dx = p * p * 70.0f;
    }
    int qa = (int)(a * 32.0f + 0.5f), qx = (int)(dx * 2.0f + 0.5f);
    if (qa != T13.qa) { T13.qa = qa; w_alpha(gw, (float)qa / 32.0f); }
    if (qx != T13.qx) { T13.qx = qx; w_pivot(gw, FT_X + (float)qx * 0.5f, ft_y()); }
    float frac = T13.total_ms > 0.0f ? T13.left_ms / T13.total_ms : 0.0f;
    if (frac < 0.0f) frac = 0.0f;
    int qb = (int)(frac * 200.0f + 0.5f);
    if (qb != T13.qb) { T13.qb = qb; w_scale(ft_w("tBar"), (float)qb / 200.0f > 0.002f ? (float)qb / 200.0f : 0.002f, 1.0f); }
    if (!(g_frame % 90)) { T13.qa = T13.qx = -1; }          // re-asserted twice a second (the engine's own page animations never fight it long)
}
// ------------------------------------------------------------------ rows
static int fr_left_n(void) { return g_f13.has_party ? g_f13.nm + 2 : 0; }
static int fr_right_rows(fr_row_t *r) { return fr13_rows(&g_f13, r, 1 + FR_NPI + 2 * FR_RROWS + FR_NF); }
static int fr_my_ready(void) { for (int i = 0; i < g_f13.nm; i++) if (g_f13.m[i].me) return g_f13.m[i].ready; return 0; }
// the actions of a row: *pri / *sec = A_* (A_NONE when there is none)
static void fr_row_actions(int col, int idx, const fr_row_t *rows, int nrows, int *pri, int *sec) {
    *pri = *sec = A_NONE;
    if (col == 0) {
        if (idx < g_f13.nm) { if (g_f13.me_leader && !g_f13.m[idx].me) { *pri = A_PROMOTE; *sec = A_KICK; } }
        else if (idx == g_f13.nm) *pri = g_f13.me_leader ? A_NONE : A_READY;       // (the leader starts the search, he has nothing to ready up)
        else if (idx == g_f13.nm + 1) *pri = A_LEAVE;
        return;
    }
    if (idx < 0 || idx >= nrows) return;
    switch (rows[idx].kind) {
    case FR_K_ADD: *pri = A_TYPE; break;
    case FR_K_PINV: *pri = A_JOIN; *sec = A_DECLINE_P; break;
    case FR_K_REQ: *pri = A_ACCEPT; *sec = A_DECLINE_R; break;
    case FR_K_FRIEND: *pri = fr13_can_invite(&g_f13, &g_f13.f[rows[idx].idx]) ? A_INVITE : A_NONE; *sec = A_REMOVE; break;
    case FR_K_OUT: *sec = A_CANCEL; break;
    }
}
static const char *fr_label(int a) {
    switch (a) {
    case A_TYPE: return FRT("ADD A FRIEND", "DODAJ ZNAJOMEGO");
    case A_INVITE: return FRT("INVITE TO PARTY", "ZAPROŚ DO GRUPY");
    case A_ACCEPT: return FRT("ACCEPT", "PRZYJMIJ");
    case A_JOIN: return FRT("JOIN PARTY", "DOŁĄCZ DO GRUPY");
    case A_DECLINE_P: case A_DECLINE_R: return FRT("DECLINE", "ODRZUĆ");
    case A_REMOVE: return FRT("REMOVE FRIEND", "USUŃ ZNAJOMEGO");
    case A_CANCEL: return FRT("CANCEL REQUEST", "ANULUJ ZAPROSZENIE");
    case A_PROMOTE: return FRT("MAKE LEADER", "ZOSTAŃ LIDEREM");
    case A_KICK: return FRT("KICK", "WYRZUĆ");
    case A_READY: return fr_my_ready() ? FRT("UNREADY", "NIEGOTOWY") : FRT("READY UP", "GOTOWY");
    case A_LEAVE: return g_f13.me_leader ? FRT("DISBAND PARTY", "ROZWIĄŻ GRUPĘ") : FRT("LEAVE PARTY", "OPUŚĆ GRUPĘ");
    default: return "";
    }
}
// Redesign: the rows are flat tiles on the shared No Return frame (nrui.c; widgets friends13_widgets.py row()): lRow<i> / rRow<i> with Bg, Fill (hover / focus lift), Ed (the accent edge:
// your own row / a ready member), the rank badge, Nm, Yu (YOU), St, Ac (the action, shown on the focused row only) and three chips placed right to left: Cw white (INVITE / REQUEST),
// Ca accent (READY), Cg grey (LEADER / NOT READY / IN YOUR PARTY). ONE outline (frFo, nr_frame_at) marks the focused row of either list.
#define FR_LX 148.0f
#define FR_RX 2004.0f
#define FR_COLW 1676.0f
#define FR_ROWH 136.0f
#define FR_RY0 524.0f
#define FR_RDY 152.0f
#define FR_SEC_Y 470.0f
#define FR_NAME_CY 46.0f
#define FR_NAME_PT 39.0f
#define FR_SM_PT 24.0f
static const float FR_LY[FR_NL] = {524.0f, 676.0f, 828.0f, 980.0f, 1176.0f, 1328.0f};
typedef struct { const char *name, *st, *ac, *cg, *ca, *cw; int me, edge, wide; } fr_rd_t;       // wide: no action text on the row, the status line may run long
static void fr_status_word(const char *st, char *out, size_t n) {
    int p = fr13_presence(st);
    const char *w = p == 4 ? FRT("IN A MATCH", "W MECZU") : p == 3 ? FRT("SEARCHING FOR A MATCH", "SZUKA MECZU") : p == 2 ? FRT("IN THE MENU", "W MENU") : p == 1 ? FRT("IN THE LAUNCHER", "W LAUNCHERZE") : FRT("OFFLINE", "OFFLINE");
    if (p > 0) snprintf(out, n, "<font color=\"#F0F0F0\">%s</font>", w);      // online = white, offline = the row's grey
    else snprintf(out, n, "%s", w);
}
static void fr_rp(char *b, size_t n, int col, int i, const char *leaf) { snprintf(b, n, "anim-group.%s.%cRow%d.%c%s%d", col ? "rt" : "lf", col ? 'r' : 'l', i, col ? 'r' : 'l', leaf, i); }
static int g_fr_player = 1;                          // 1 except while fr_set_row draws a real player row (not an action row): a badge even for a name the rank table lacks
#define RKB_RES46 104.0f                              // = rank_badge_widgets.reserved(40, 68) = 104: the width the badge takes in front of a 39 pt name
static void fr_chip(const char *g, int col, int i, const char *kind, const char *t, float *right) {     // one chip of a row: shown when t is set, placed left of *right
    char b[200], p[216];
    snprintf(b, sizeof b, "%s.%c%s%d", g, col ? 'r' : 'l', kind, i);
    int on = t && t[0];
    snprintf(p, sizeof p, "%sBg", b); ui_visible(p, on);
    snprintf(p, sizeof p, "%sTx", b); ui_visible(p, on);
    if (on) *right -= nr_chip(b, t, 0.0f, *right, FR_SM_PT) + 10.0f;
}
static void fr_set_row(int col, int i, const fr_rd_t *d, int foc, int hov) {          // d NULL = the row is hidden
    char p[160], g[96];
    snprintf(g, sizeof g, "anim-group.%s.%cRow%d", col ? "rt" : "lf", col ? 'r' : 'l', i);
    int vis = d != NULL;
    ui_visible(g, vis);
    F13.rw[col][i] = vis ? ui_w(g) : 0;
    if (!vis) return;
    snprintf(p, sizeof p, "%s.%cEd%d", g, col ? 'r' : 'l', i); ui_visible(p, d->edge);
    // rank badge (rankbadge.c; widgets rank_badge_widgets.py, a 39 pt name): a PLAYER row shows the badge and its name moves right by the badge's width; an action row ("ADD A FRIEND" ...) keeps the plain layout
    int rk = -1, wk = 0, has = d->name && rkb_lookup(d->name, &rk, &wk);
    if (!has && g_fr_player && d->name && d->name[0] && g_rkb_ver > 0) { has = 1; rk = 0; wk = 0; }      // a party member / inviter the table does not list yet: the lowest rank
    { char ri[160], rn[160]; snprintf(ri, sizeof ri, "%s.%cRk%d", g, col ? 'r' : 'l', i); snprintf(rn, sizeof rn, "%s.%cRn%d", g, col ? 'r' : 'l', i); rank_ui(ri, rn, has ? rk : -1, wk); }
    // every line is measured against its box (the widgets pivot at the edge they align to): a long name / status / action shrinks toward that edge, a name that still does not fit gets "..."
    float res = has ? RKB_RES46 : 0.0f, nx = 36.0f + res, nbox = 1100.0f - res - (d->me ? 160.0f : 0.0f);
    fr_rp(p, sizeof p, col, i, "Nm"); w_pivot(ui_w(p), nx, FR_NAME_CY); gu_fit(p, d->name, nbox, FR_NAME_PT);
    fr_rp(p, sizeof p, col, i, "Yu");
    if (d->me) {                                      // YOU in the accent after the name (the player stats' own row)
        float w = nr_tw(d->name, FR_NAME_PT), wf = 24.0f * (float)strlen(d->name);
        if (w < wf) w = wf;
        if (w > nbox) w = nbox;
        ui_text(p, FRT("<font color=\"#D9D86A\">YOU</font>", "<font color=\"#D9D86A\">TY</font>"));
        w_pivot(ui_w(p), nx + w + 36.0f, FR_NAME_CY);
    } else ui_text(p, "");
    fr_rp(p, sizeof p, col, i, "St"); gu_fit(p, d->st, d->wide ? 1560.0f : 1000.0f, FR_SM_PT);
    fr_rp(p, sizeof p, col, i, "Ac"); gu_fit(p, foc || hov ? d->ac : "", 560.0f, FR_SM_PT);
    float right = FR_COLW - 24.0f;
    fr_chip(g, col, i, "Cw", d->cw, &right);
    fr_chip(g, col, i, "Ca", d->ca, &right);
    fr_chip(g, col, i, "Cg", d->cg, &right);
    fr_rp(p, sizeof p, col, i, "Fill"); gu_fade(p, foc || hov);
}
static void fr_window(int n) {                        // the right list's window and focus
    int rows = FR_RROWS;
    if (n <= 0) { F13.foc[1] = 0; F13.off[1] = 0; return; }
    if (F13.foc[1] >= n) F13.foc[1] = n - 1;
    if (F13.foc[1] < 0) F13.foc[1] = 0;
    if (F13.foc[1] < F13.off[1]) F13.off[1] = F13.foc[1];
    if (F13.foc[1] >= F13.off[1] + rows) F13.off[1] = F13.foc[1] - rows + 1;
    if (F13.off[1] > n - rows) F13.off[1] = n - rows;
    if (F13.off[1] < 0) F13.off[1] = 0;
}
enum { FR_PR_SEL, FR_PR_ACT, FR_PR_SW, FR_PR_BACK };     // the boxed prompts of the page, left to right (nr_prompts items)
static int g_fr_pr[4], g_fr_npr;
static void fr_fill(void) {
    char a[200], b[200];
    nr_header(FRT("MULTIPLAYER", "TRYB WIELOOSOBOWY"), FRT("FRIENDS", "ZNAJOMI"));
    int show = N13.have;
    const char *ld = "";
    if (!show) ld = !g_fr_busy && N13.fails >= 2 ? FRT("THE SERVER DID NOT ANSWER", "SERWER NIE ODPOWIADA") : FRT("LOADING YOUR FRIENDS", "WCZYTYWANIE ZNAJOMYCH");
    ui_text("anim-group.ldTx", ld);
    ui_visible("anim-group.ldTx", !show);
    ui_visible("anim-group.lf", show && !(g_f13.has_party && F13.col == 2 && fm_avail()));     // (with a party, MESSAGES takes the PARTY rows' place while it is the picked list)
    ui_visible("anim-group.rt", show);
    nr_prompt_t it[4];
    int np = 0;
    if (!show) {
        ui_text("anim-group.hd.hdMe", ""); ui_text("anim-group.hd.hdId", ""); ui_text("anim-group.msgTx", ""); ui_text("anim-group.keyTx", "");
        nr_frame_at("anim-group.frFo", 0.0f, 0.0f, 0.0f, 0.0f, 0);
        ui_visible("anim-group.msg", 0);
        it[0] = (nr_prompt_t){"menu:back", NULL, FRT("BACK", "WSTECZ"), 1}; g_fr_pr[0] = FR_PR_BACK; g_fr_npr = 1;
        nr_prompts(it, 1);
        return;
    }
    gu_fit("anim-group.hd.hdMe", g_f13.me_name, 1300.0f, 42.0f);
    snprintf(a, sizeof a, FRT("YOUR FRIEND ID  %s", "TWOJE ID  %s"), g_f13.me_id);
    gu_fit("anim-group.hd.hdId", a, 1400.0f, 30.0f);
    // ---- left: PARTY
    int ln = fr_left_n();
    if (F13.foc[0] >= ln) F13.foc[0] = ln ? ln - 1 : 0;
    if (!ln && F13.col == 0) F13.col = 1;
    snprintf(a, sizeof a, "%d / %d%s", g_f13.nm, g_f13.pmax ? g_f13.pmax : 4, g_f13.searching ? FRT("  |  SEARCHING", "  |  SZUKA MECZU") : "");
    { int un = fr13_unread_total(); if (g_f13.has_party && un > 0) { size_t l = strlen(a); snprintf(a + l, sizeof a - l, FRT("  |  %d NEW MESSAGES - TAB", "  |  NOWE WIADOMOŚCI: %d - TAB"), un); } }
    nr_section("anim-group.lf.lSec", FR_LX, FR_LX + FR_COLW, FR_SEC_Y, FRT("PARTY", "GRUPA"), g_f13.has_party ? a : "", 36.0f);
    ui_text("anim-group.lf.lNone", FRT("NO PARTY YET. INVITE A FRIEND FROM THE LIST ON THE RIGHT - A PARTY QUEUES TOGETHER AND PLAYS ON ONE TEAM.", "JESZCZE NIE MASZ GRUPY. ZAPROŚ ZNAJOMEGO Z LISTY PO PRAWEJ - GRUPA SZUKA MECZU RAZEM I GRA W JEDNEJ DRUŻYNIE."));
    ui_visible("anim-group.lf.lNone", !ln);
    fr_row_t rows[1 + FR_NPI + 2 * FR_RROWS + FR_NF];
    int nr = fr_right_rows(rows);
    for (int i = 0; i < FR_NL; i++) {
        int foc = F13.col == 0 && F13.foc[0] == i, hov = F13.hv_col == 0 && F13.hv_row == i;
        if (i >= ln) { fr_set_row(0, i, NULL, 0, 0); continue; }
        int pri, sec; fr_row_actions(0, i, rows, nr, &pri, &sec);
        fr_rd_t d;
        memset(&d, 0, sizeof d);
        if (i < g_f13.nm) {
            const fr_m_t *m = &g_f13.m[i];
            fr_status_word(m->status, b, sizeof b);
            d.name = m->name; d.st = b; d.ac = fr_label(pri); d.me = m->me;
            d.edge = m->ready || m->leader || m->me;                                  // no edge = not ready
            d.cg = m->leader ? FRT("LEADER", "LIDER") : m->ready ? "" : FRT("NOT READY", "NIEGOTOWY");
            d.ca = m->ready && !m->leader ? FRT("READY", "GOTOWY") : "";
            fr_set_row(0, i, &d, foc, hov);
        } else if (i == g_f13.nm) {
            d.wide = 1;
            if (g_f13.me_leader) { d.name = FRT("YOU START THE SEARCH", "TY ZACZYNASZ SZUKANIE"); d.st = FRT("FIND MATCH ON THE MP MENU - THE PARTY GOES IN ONCE EVERYONE IS READY", "ZNAJDŹ MECZ W MENU MP - GRUPA IDZIE RAZEM, GDY WSZYSCY SĄ GOTOWI"); }
            else { d.name = fr_label(A_READY); d.st = FRT("THE LEADER STARTS THE SEARCH AND THE READY PARTY GOES IN TOGETHER", "LIDER ZACZYNA SZUKANIE, A GOTOWA GRUPA IDZIE RAZEM"); d.edge = fr_my_ready(); }
            g_fr_player = 0; fr_set_row(0, i, &d, g_f13.me_leader ? 0 : foc, g_f13.me_leader ? 0 : hov); g_fr_player = 1;
        } else {
            d.wide = 1;
            d.name = fr_label(A_LEAVE); d.st = g_f13.me_leader ? FRT("THE PARTY ENDS FOR EVERYONE", "GRUPA KOŃCZY SIĘ DLA WSZYSTKICH") : FRT("YOU STAY A FRIEND OF EVERYONE IN IT", "ZOSTAJESZ ZNAJOMYM WSZYSTKICH Z GRUPY");
            g_fr_player = 0; fr_set_row(0, i, &d, foc, hov); g_fr_player = 1;
        }
    }
    // ---- right: FRIENDS
    fr_window(nr);
    int on = 0;
    for (int i = 0; i < g_f13.nf; i++) if (fr13_presence(g_f13.f[i].status) > 0) on++;
    snprintf(a, sizeof a, FRT("%d ONLINE  |  %d FRIENDS", "%d ONLINE  |  %d ZNAJOMYCH"), on, g_f13.nf);
    nr_section("anim-group.rt.rSec", FR_RX, FR_RX + FR_COLW, FR_SEC_Y, FRT("FRIENDS", "ZNAJOMI"), a, 36.0f);
    for (int i = 0; i < FR_RROWS; i++) {
        int idx = F13.off[1] + i;
        int foc = F13.col == 1 && F13.foc[1] == idx, hov = F13.hv_col == 1 && F13.hv_row == i;
        if (idx >= nr) { fr_set_row(1, i, NULL, 0, 0); continue; }
        int pri, sec; fr_row_actions(1, idx, rows, nr, &pri, &sec);
        const fr_row_t *r = &rows[idx];
        fr_rd_t d;
        memset(&d, 0, sizeof d);
        d.ac = fr_label(pri);
        if (r->kind == FR_K_ADD) {
            if (F13.typing) { fr_set_row(1, i, NULL, 0, 0); continue; }                // the text field (fr_inp_tick) sits over this slot
            d.name = FRT("ADD A FRIEND", "DODAJ ZNAJOMEGO"); d.st = FRT("BY PLAYER NAME OR STEAM ID", "PO NAZWIE GRACZA LUB ID STEAM"); d.ac = FRT("TYPE A NAME", "WPISZ NAZWĘ");
            g_fr_player = 0; fr_set_row(1, i, &d, foc, hov); g_fr_player = 1;
            continue;
        } else if (r->kind == FR_K_PINV) {
            d.name = g_f13.pinv[r->idx].name; d.st = FRT("INVITED YOU TO A PARTY", "ZAPRASZA CIĘ DO GRUPY"); d.cw = FRT("INVITE", "ZAPROSZENIE");
        } else if (r->kind == FR_K_REQ) {
            d.name = g_f13.in[r->idx].name; d.st = FRT("WANTS TO BE YOUR FRIEND", "CHCE ZOSTAĆ TWOIM ZNAJOMYM"); d.cw = FRT("REQUEST", "PROŚBA");
        } else if (r->kind == FR_K_FRIEND) {
            const fr_f_t *x = &g_f13.f[r->idx];
            fr_status_word(x->status, b, sizeof b);
            d.name = x->name; d.st = b; d.cg = x->party ? FRT("IN YOUR PARTY", "W TWOJEJ GRUPIE") : "";
        } else {
            d.name = g_f13.out[r->idx].name; d.st = FRT("REQUEST SENT - WAITING FOR AN ANSWER", "ZAPROSZENIE WYSŁANE - CZEKA NA ODPOWIEDŹ");
        }
        fr_set_row(1, i, &d, foc, hov);
    }
    int more = nr - (F13.off[1] + FR_RROWS);
    snprintf(a, sizeof a, more > 0 ? FRT("+ %d MORE", "+ JESZCZE %d") : "", more);
    ui_text("anim-group.rt.rMore", more > 0 ? a : "");
    nr_scroll_v("anim-group.rt.rSc", 3694.0f, FR_RY0, FR_RY0 + FR_RDY * (float)FR_RROWS, FR_RDY * (float)FR_RROWS, F13.off[1], FR_RROWS, nr);
    // ---- MESSAGES
    fm_fill();
    // ---- the focus outline
    {
        int fc = F13.col, fi = F13.foc[fc], fon = !F13.typing && (fc == 2 ? g_fm_n > 0 : fc ? nr > 0 : ln > 0);
        float fx = fc == 2 ? FM_X : fc ? FR_RX : FR_LX, fy = 0.0f, fw = fc == 2 ? FM_TW : FR_COLW, fh = fc == 2 ? FM_TH : FR_ROWH, my = 0.0f;
        if (fc == 2) {
            if (!fm_shown(&my)) fon = 0;
            else if (M13.ed.on) { fx = FM_X + FM_PX; fy = my + FM_FY; fw = FM_PW; fh = FM_FH; fon = 1; }
            else { int s = fi - F13.off[2]; if (s < 0 || s >= FM_NV) fon = 0; else fy = my + FM_TY + FM_TDY * (float)s; }
        } else if (fc) { int s = fi - F13.off[1]; if (s < 0 || s >= FR_RROWS) fon = 0; else fy = FR_RY0 + FR_RDY * (float)s; }
        else { if (fi < 0 || fi >= FR_NL) fon = 0; else fy = FR_LY[fi]; }
        nr_frame_at("anim-group.frFo", fx, fy, fw, fh, fon);
    }
    // ---- status line, key hints, prompts
    uint64_t now = GetTickCount64();
    gu_fit("anim-group.msgTx", N13.msg_until > now ? N13.msg : "", 3500.0f, 33.0f);
    gu_fit("anim-group.keyTx", M13.ed.on ? FRT("ENTER SEND     ESC STOP TYPING     CTRL+V PASTE     LEFT / RIGHT / HOME / END MOVE     BACKSPACE / DELETE ERASE", "ENTER WYŚLIJ     ESC KONIEC PISANIA     CTRL+V WKLEJ     STRZAŁKI / HOME / END PRZESUWAJĄ     BACKSPACE / DELETE KASUJE")
                                          : F13.col == 2 && !F13.typing ? (g_pad_mode ? FRT("STICK / D-PAD  PICK A CHAT     LEFT / RIGHT  QUICK REPLY     THE PROMPTS BELOW DO IT     BUMPERS  SWITCH LIST     BACK  CLOSE", "GAŁKA / KRZYŻAK WYBIERZ ROZMOWĘ     LEWO / PRAWO SZYBKA ODPOWIEDŹ     PRZYCISKI NA DOLE WYKONUJĄ     ZDERZAKI ZMIEŃ LISTĘ     WSTECZ ZAMKNIJ")
                                                                        : FRT("CLICK OR W / S PICK A CHAT     ENTER TYPE     1 - 4 QUICK REPLY     TAB SWITCH LIST     P OR ESC CLOSE", "KLIKNIJ LUB W / S WYBIERZ ROZMOWĘ     ENTER PISZ     1 - 4 SZYBKA ODPOWIEDŹ     TAB ZMIEŃ LISTĘ     P LUB ESC ZAMKNIJ"))
                                          : F13.typing ? FRT("ENTER SEND     ESC CANCEL     CTRL+V PASTE     LEFT / RIGHT / HOME / END MOVE     BACKSPACE / DELETE ERASE", "ENTER WYŚLIJ     ESC ANULUJ     CTRL+V WKLEJ     STRZAŁKI / HOME / END PRZESUWAJĄ     BACKSPACE / DELETE KASUJE")
                                          : g_pad_mode ? FRT("STICK / D-PAD  SELECT     THE PROMPTS BELOW DO IT     BUMPERS  SWITCH LIST     BACK  CLOSE", "GAŁKA / KRZYŻAK ZAZNACZ     PRZYCISKI NA DOLE WYKONUJĄ     ZDERZAKI ZMIEŃ LISTĘ     WSTECZ ZAMKNIJ")
                                          : FRT("CLICK OR W / S SELECT     ENTER OR THE PROMPT BELOW DOES IT     X SECOND ACTION     M MESSAGE     R READY     L LEAVE PARTY     TAB SWITCH LIST     P OR ESC CLOSE", "KLIKNIJ LUB W / S ZAZNACZ     ENTER LUB PRZYCISK NA DOLE WYKONUJE     X DRUGA AKCJA     M WIADOMOŚĆ     R GOTOWY     L OPUŚĆ GRUPĘ     TAB ZMIEŃ LISTĘ     P LUB ESC ZAMKNIJ"), 3500.0f, 24.0f);
    int pri = A_NONE, sec = A_NONE;
    int col = F13.col, idx = F13.foc[col];
    if (col == 2) {                                                         // MESSAGES: TYPE / SEND and the quick reply (the pad's SELECT sends it: a pad has no keyboard)
        static char ql[96];
        snprintf(ql, sizeof ql, FRT("SEND \"%s\"", "WYŚLIJ \"%s\""), fm_quick(M13.qf, 1));
        int w = M13.with[0] != 0;
        it[np] = (nr_prompt_t){"menu:select", NULL, M13.ed.on ? FRT("SEND", "WYŚLIJ") : g_pad_mode ? ql : FRT("TYPE A MESSAGE", "NAPISZ WIADOMOŚĆ"), w}; g_fr_pr[np++] = FR_PR_SEL;
        it[np] = (nr_prompt_t){"menu:action", NULL, g_pad_mode ? FRT("ACTION", "AKCJA") : ql, w && !g_pad_mode && !M13.ed.on}; g_fr_pr[np++] = FR_PR_ACT;
        it[np] = (nr_prompt_t){"menu:prev+menu:next", NULL, FRT("SWITCH LIST", "ZMIEŃ LISTĘ"), !M13.ed.on}; g_fr_pr[np++] = FR_PR_SW;
        it[np] = (nr_prompt_t){"menu:back", NULL, FRT("BACK", "WSTECZ"), 1}; g_fr_pr[np++] = FR_PR_BACK;
        g_fr_npr = np;
        nr_prompts(it, np);
        return;
    }
    fr_row_actions(col, idx, rows, nr, &pri, &sec);
    if (F13.typing) { pri = A_NONE; sec = A_NONE; }
    it[np] = (nr_prompt_t){"menu:select", NULL, F13.typing ? FRT("SEND", "WYŚLIJ") : pri != A_NONE ? fr_label(pri) : FRT("SELECT", "WYBIERZ"), F13.typing || pri != A_NONE}; g_fr_pr[np++] = FR_PR_SEL;
    it[np] = (nr_prompt_t){"menu:action", NULL, sec != A_NONE ? fr_label(sec) : FRT("ACTION", "AKCJA"), sec != A_NONE}; g_fr_pr[np++] = FR_PR_ACT;
    it[np] = (nr_prompt_t){"menu:prev+menu:next", NULL, FRT("SWITCH LIST", "ZMIEŃ LISTĘ"), (ln != 0 || fm_avail()) && !F13.typing}; g_fr_pr[np++] = FR_PR_SW;
    it[np] = (nr_prompt_t){"menu:back", NULL, FRT("BACK", "WSTECZ"), 1}; g_fr_pr[np++] = FR_PR_BACK;
    g_fr_npr = np;
    nr_prompts(it, np);
}
// ------------------------------------------------------------------ the mouse
static void fr_scan(void) {
    float cx, cy;
    F13.hv_col = F13.hv_row = -1; F13.hv_back = F13.hv_sel = F13.hv_act = F13.hv_sw = 0;
    M13.hv_q = -1; M13.hv_fld = 0;
    if (!ui_cursor_canvas(&cx, &cy)) return;
    int ln = fr_left_n();
    float my;
    if (fm_shown(&my)) {                                         // MESSAGES: the conversation tiles, the quick reply chips, the typing line
        float lx = cx - FM_X, ly = cy - my;
        for (int i = 0; i < FM_NV && F13.off[2] + i < g_fm_n; i++) if (lx >= 0.0f && lx <= FM_TW && ly >= FM_TY + FM_TDY * (float)i && ly <= FM_TY + FM_TDY * (float)i + FM_TH) F13.hv_col = 2, F13.hv_row = i;
        for (int k = 0; k < FM_NQ; k++) if (M13.qw[k] > 0.0f && lx >= M13.qx[k] && lx <= M13.qx[k] + M13.qw[k] && ly >= FM_QY && ly <= FM_QY + FM_QH) M13.hv_q = k;
        if (M13.with[0] && lx >= FM_PX && lx <= FM_PX + FM_PW && ly >= FM_FY && ly <= FM_FY + FM_FH) M13.hv_fld = 1;
        if (g_f13.has_party) ln = 0;                             // (the PARTY rows are hidden under it)
    }
    if (cx >= FR_LX && cx <= FR_LX + FR_COLW) for (int i = 0; i < ln && i < FR_NL; i++) if (cy >= FR_LY[i] && cy <= FR_LY[i] + FR_ROWH) F13.hv_col = 0, F13.hv_row = i;
    if (cx >= FR_RX && cx <= FR_RX + FR_COLW) for (int i = 0; i < FR_RROWS; i++) if (cy >= FR_RY0 + FR_RDY * (float)i && cy <= FR_RY0 + FR_RDY * (float)i + FR_ROWH) F13.hv_col = 1, F13.hv_row = i;
    if (F13.hv_col == 1) { fr_row_t rows[1 + FR_NPI + 2 * FR_RROWS + FR_NF]; if (F13.off[1] + F13.hv_row >= fr_right_rows(rows)) F13.hv_col = F13.hv_row = -1; }
    int ph = nr_prompt_hover();                                  // the boxed prompts are the action buttons (select only moves, like gear up)
    if (ph >= 0 && ph < g_fr_npr) {
        int r = g_fr_pr[ph];
        F13.hv_sel = r == FR_PR_SEL; F13.hv_act = r == FR_PR_ACT; F13.hv_sw = r == FR_PR_SW; F13.hv_back = r == FR_PR_BACK;
    }
}
static int fr13_click_hit(void) {
    if (!F13.up) return 0;
    fr_scan();
    return F13.hv_row >= 0 || F13.hv_back || F13.hv_sel || F13.hv_act || F13.hv_sw || M13.hv_q >= 0 || M13.hv_fld;
}
// ------------------------------------------------------------------ text entry
// The ADD FRIEND field: a real one-line editor. Typed: letters, digits, space - _ . : [ ] (Ctrl+V pastes the same set); Left / Right / Home / End move the caret, Backspace / Delete (and Ctrl+Backspace for a
// word) erase with key repeat, Enter sends, Esc cancels typing (a second Esc closes the page). Backspace is also the engine's menu-back: it pops the page by itself, so the page is pushed
// again the same frame with the text, the caret and the focus intact (the names page does the same, feature_names; the pad's B / a right click still cancel).
#define FR_BUFMAX 31
static int fr_okch(unsigned char c) { return c >= 0x80 || (c >= '0' && c <= '9') || (c >= 'A' && c <= 'Z') || (c >= 'a' && c <= 'z') || c == ' ' || c == '-' || c == '_' || c == '.' || c == ':' || c == '[' || c == ']'; }
static void fr_edited(void) { F13.edit_ms = GetTickCount64(); F13.dirty = 1; }
static int fr_prev_ch(int i) { if (i > 0) i--; while (i > 0 && ((unsigned char)F13.buf[i] & 0xC0) == 0x80) i--; return i; }
static int fr_next_ch(int i) { if (i < F13.blen) i++; while (i < F13.blen && ((unsigned char)F13.buf[i] & 0xC0) == 0x80) i++; return i; }
static void fr_cut(int from, int to) {                 // erase buf[from..to), the caret goes to from
    if (from < 0 || to > F13.blen || from >= to) return;
    memmove(F13.buf + from, F13.buf + to, (size_t)(F13.blen - to + 1));
    F13.blen -= to - from; F13.caret = from; fr_edited();
}
static void fr_ins(const char *t, int n) {              // insert n bytes at the caret (whole characters only)
    if (n <= 0 || F13.blen + n > FR_BUFMAX) return;
    memmove(F13.buf + F13.caret + n, F13.buf + F13.caret, (size_t)(F13.blen - F13.caret + 1));
    memcpy(F13.buf + F13.caret, t, (size_t)n);
    F13.blen += n; F13.caret += n; fr_edited();
}
static void fr_buf_add(char ch) { if (ch == ' ' && !F13.caret) return; fr_ins(&ch, 1); }
static void fr_typing_start(void) {
    F13.typing = 1; F13.blen = 0; F13.caret = 0; F13.buf[0] = 0;
    F13.col = 1; F13.foc[1] = 0; F13.off[1] = 0;
    F13.typ_ms = F13.edit_ms = GetTickCount64(); F13.ul_q = F13.gl_q = -1;
    for (int vk = 8; vk < 0xC0; vk++) F13.hk[vk] = (GetAsyncKeyState(vk) & 0x8000) != 0;      // whatever is held now is no new press
    F13.hk[VK_RETURN] = 1;
    F13.dirty = 1;
}
static void fr_typing_stop(void) {
    F13.typing = 0; F13.blen = 0; F13.caret = 0; F13.buf[0] = 0; F13.dirty = 1;
    for (int vk = 8; vk < 0xC0; vk++) F13.hk[vk] = (GetAsyncKeyState(vk) & 0x8000) != 0;
}
static void fr_paste(void) {
    if (!OpenClipboard(NULL)) return;
    HANDLE h = GetClipboardData(CF_UNICODETEXT);
    if (h) {
        const wchar_t *w = (const wchar_t *)GlobalLock(h);
        if (w) {
            char u[200];
            int n = WideCharToMultiByte(CP_UTF8, 0, w, (int)wcsnlen(w, 40), u, (int)sizeof u - 1, NULL, NULL);
            GlobalUnlock(h);
            for (int i = 0; i < n; ) {                  // whole characters of the allowed set (no markup characters can get into the field)
                int l = 1;
                unsigned char c = (unsigned char)u[i];
                if (c >= 0xF0) l = 4; else if (c >= 0xE0) l = 3; else if (c >= 0xC0) l = 2;
                if (i + l > n) break;
                if (fr_okch(c) && !(c == ' ' && !F13.caret)) { if (F13.blen + l > FR_BUFMAX) break; fr_ins(u + i, l); }
                i += l;
            }
        }
    }
    CloseClipboard();
}
static int fr_krep(int vk, int slot, uint64_t now) {   // a key's press + repeat (first after 400 ms, then every 45 ms)
    int on = (GetAsyncKeyState(vk) & 0x8000) != 0, fire = 0;
    if (on && !F13.hk[vk]) { fire = 1; F13.rep_t[slot] = now + 400; }
    else if (on && now >= F13.rep_t[slot]) { fire = 1; F13.rep_t[slot] = now + 45; }
    F13.hk[vk] = on;
    return fire;
}
static void fr_typing_tick(uint64_t now) {
    int shift = (GetAsyncKeyState(VK_SHIFT) & 0x8000) != 0, ctrl = (GetAsyncKeyState(VK_CONTROL) & 0x8000) != 0;
    for (int vk = 'A'; vk <= 'Z'; vk++) {
        if (!ne_key_edge(vk, &F13.hk[vk])) continue;
        if (ctrl) { if (vk == 'V') fr_paste(); continue; }
        fr_buf_add((char)(shift ? vk : vk + 32));
    }
    for (int vk = '0'; vk <= '9'; vk++) if (ne_key_edge(vk, &F13.hk[vk]) && !shift && !ctrl) fr_buf_add((char)vk);
    for (int vk = VK_NUMPAD0; vk <= VK_NUMPAD9; vk++) if (ne_key_edge(vk, &F13.hk[vk])) fr_buf_add((char)('0' + vk - VK_NUMPAD0));
    if (ne_key_edge(VK_SPACE, &F13.hk[VK_SPACE])) fr_buf_add(' ');
    if (ne_key_edge(0xBD, &F13.hk[0xBD])) fr_buf_add(shift ? '_' : '-');
    if (ne_key_edge(0xBE, &F13.hk[0xBE])) fr_buf_add('.');
    if (ne_key_edge(0xBA, &F13.hk[0xBA]) && shift) fr_buf_add(':');
    if (ne_key_edge(0xDB, &F13.hk[0xDB]) && !shift) fr_buf_add('[');
    if (ne_key_edge(0xDD, &F13.hk[0xDD]) && !shift) fr_buf_add(']');
    if ((GetAsyncKeyState(VK_BACK) & 0x8000)) F13.bs_ms = now;
    if (fr_krep(VK_BACK, 2, now)) {
        if (ctrl) { int to = F13.caret; while (to > 0 && F13.buf[to - 1] == ' ') to--; while (to > 0 && F13.buf[to - 1] != ' ') to--; fr_cut(to, F13.caret); }
        else fr_cut(fr_prev_ch(F13.caret), F13.caret);
    }
    if (fr_krep(VK_DELETE, 3, now)) fr_cut(F13.caret, fr_next_ch(F13.caret));
    if (fr_krep(VK_LEFT, 0, now)) { F13.caret = fr_prev_ch(F13.caret); fr_edited(); }
    if (fr_krep(VK_RIGHT, 1, now)) { F13.caret = fr_next_ch(F13.caret); fr_edited(); }
    if (ne_key_edge(VK_HOME, &F13.hk[VK_HOME])) { F13.caret = 0; fr_edited(); }
    if (ne_key_edge(VK_END, &F13.hk[VK_END])) { F13.caret = F13.blen; fr_edited(); }
    ne_key_edge(VK_UP, &F13.hk[VK_UP]); ne_key_edge(VK_DOWN, &F13.hk[VK_DOWN]);        // (held state kept current)
}
// the field's look, every frame it is up: alpha in / out (about 170 ms), the underline growing from the centre (260 ms, ease-out cubic), a faint glow breathing on it, the placeholder fading out
// with the first character (about 150 ms), the caret = a "|" in the text drawn in a grey that pulses between the card and the text colour (solid for 450 ms after every edit, then a 1.06 s cosine
// blink; same glyph width in every state, so the text never jitters). Writes only when a quantised value changes.
static void fr_inp_tick(uint64_t now) {
    static uint64_t last;
    float dt = last ? (float)(now - last) : 16.0f;
    last = now;
    if (dt > 60.0f) dt = 60.0f;
    float tg = F13.typing ? 1.0f : 0.0f;
    F13.inp_a += (tg - F13.inp_a) * (1.0f - expf(-dt / (F13.typing ? 55.0f : 45.0f)));
    if (fabsf(tg - F13.inp_a) < 0.02f) F13.inp_a = tg;
    uint64_t g = ui_w("anim-group.rt.inp");
    int on = g && (F13.inp_a > 0.0f || F13.typing);
    if (g) ui_visible("anim-group.rt.inp", on);
    if (!on) return;
    int qa = (int)(F13.inp_a * 24.0f + 0.5f);
    if (qa != F13.ia_q) { F13.ia_q = qa; w_alpha(g, (float)qa / 24.0f); }
    float p = F13.typing ? ft_ease((float)(now - F13.typ_ms) / 260.0f) : 1.0f;
    float sx = p > 0.001f ? p : 0.001f;
    int qs = (int)(sx * 64.0f + 0.5f);
    if (qs != F13.ul_q) { F13.ul_q = qs; uint64_t u = ui_w("anim-group.rt.inp.inpUl"); w_scale(u, sx, 1.0f); w_alpha(u, 0.94f); w_scale(ui_w("anim-group.rt.inp.inpGlow"), sx, 1.0f); }
    float pulse = 0.5f + 0.5f * sinf((float)(now % 100000) / 380.0f);
    int qg = F13.typing ? (int)(p * (0.05f + 0.05f * pulse) * 60.0f + 0.5f) : 0;
    if (qg != F13.gl_q) { F13.gl_q = qg; w_alpha(ui_w("anim-group.rt.inp.inpGlow"), (float)qg / 60.0f); }
    float pt = (F13.typing && F13.blen == 0) ? 1.0f : 0.0f;
    F13.ph_a += (pt - F13.ph_a) * (1.0f - expf(-dt / 40.0f));
    if (fabsf(pt - F13.ph_a) < 0.02f) F13.ph_a = pt;
    int qp = (int)(F13.ph_a * 24.0f + 0.5f);
    if (qp != F13.pa_q) { F13.pa_q = qp; uint64_t ph = ui_w("anim-group.rt.inp.inpPh"); w_alpha(ph, (float)qp / 24.0f); w_visible(ph, qp > 0); }
    if (!F13.typing) return;                                // (fading out: the card keeps the last text)
    gu_fit("anim-group.rt.inp.inpLbl", FRT("ADD A FRIEND  -  PLAYER NAME OR STEAM ID", "DODAJ ZNAJOMEGO  -  NAZWA GRACZA LUB ID STEAM"), 1060.0f, 24.0f);
    gu_fit("anim-group.rt.inp.inpPh", FRT("TYPE A NAME OR A STEAM ID", "WPISZ NAZWĘ LUB ID STEAM"), 1060.0f, 39.0f);
    gu_fit("anim-group.rt.inp.inpKey", FRT("ENTER SENDS", "ENTER WYSYŁA"), 410.0f, 24.0f);
    char c[32];
    snprintf(c, sizeof c, "%d / %d", F13.blen, FR_BUFMAX);
    ui_text("anim-group.rt.inp.inpCnt", c);
    uint64_t t = now - F13.edit_ms;
    float lv = t < 450 ? 1.0f : 0.5f + 0.5f * cosf((float)(t - 450) * (6.2831853f / 1060.0f));
    int lq = (int)(lv * 5.0f + 0.5f);
    unsigned grey = 0x1A + (unsigned)((0xF0 - 0x1A) * lq / 5);
    char tx[120];
    snprintf(tx, sizeof tx, "%.*s<font color=\"#%02X%02X%02X\">|</font>%s", F13.caret, F13.buf, grey, grey, grey, F13.buf + F13.caret);
    gu_fit("anim-group.rt.inp.inpTx", tx, 1090.0f, 45.0f);
}
// ------------------------------------------------------------------ the page
static void fr_sfx(void) { uint64_t now = GetTickCount64(); if (now - F13.sfx_ms >= 60) { F13.sfx_ms = now; ui_sfx("sfx-cycle"); } }
// ------------------------------------------------------------------ MESSAGES: list, thread, sending, input
static int fm_avail(void) { return N13.have && ui_w("anim-group.msg") != 0; }
static int fm_shown(float *my) {                       // the block is on screen (and where its section line is)
    if (!fm_avail()) return 0;
    if (!g_f13.has_party) { *my = FM_Y_LOW; return 1; }
    if (F13.col == 2) { *my = FM_Y_TOP; return 1; }
    return 0;
}
static int fm_list_build(void) {
    int n = 0, cap = (int)(sizeof g_fm_e / sizeof g_fm_e[0]);
    for (int i = 0; i < g_f13.nrc && n < cap; i++) {
        const fr_rc_t *r = &g_f13.rc[i];
        fm_ent_t *e = &g_fm_e[n++];
        memset(e, 0, sizeof *e);
        snprintf(e->id, sizeof e->id, "%s", r->id);
        ch_clean(r->name, strlen(r->name), e->name, sizeof e->name, 24);
        ch_clean(r->t, strlen(r->t), e->t, sizeof e->t, 60);
        e->me = r->me; e->unread = r->unread;
        for (int k = 0; k < g_f13.nf; k++) if (!strcmp(g_f13.f[k].id, r->id)) { snprintf(e->st, sizeof e->st, "%s", g_f13.f[k].status); if (!e->name[0]) ch_clean(g_f13.f[k].name, strlen(g_f13.f[k].name), e->name, sizeof e->name, 24); }
    }
    for (int k = 0; k < g_f13.nf && n < cap; k++) {     // every other friend after the conversations
        int dup = 0;
        for (int i = 0; i < g_f13.nrc && !dup; i++) dup = !strcmp(g_f13.rc[i].id, g_f13.f[k].id);
        if (dup) continue;
        fm_ent_t *e = &g_fm_e[n++];
        memset(e, 0, sizeof *e);
        snprintf(e->id, sizeof e->id, "%s", g_f13.f[k].id);
        ch_clean(g_f13.f[k].name, strlen(g_f13.f[k].name), e->name, sizeof e->name, 24);
        snprintf(e->st, sizeof e->st, "%s", g_f13.f[k].status);
    }
    g_fm_n = n;
    return n;
}
static int fm_find(const char *id) { for (int i = 0; i < g_fm_n; i++) if (!strcmp(g_fm_e[i].id, id)) return i; return -1; }
static void fm_window(int n) {
    if (n <= 0) { F13.foc[2] = 0; F13.off[2] = 0; return; }
    if (F13.foc[2] >= n) F13.foc[2] = n - 1;
    if (F13.foc[2] < 0) F13.foc[2] = 0;
    if (F13.foc[2] < F13.off[2]) F13.off[2] = F13.foc[2];
    if (F13.foc[2] >= F13.off[2] + FM_NV) F13.off[2] = F13.foc[2] - FM_NV + 1;
    if (F13.off[2] > n - FM_NV) F13.off[2] = n - FM_NV;
    if (F13.off[2] < 0) F13.off[2] = 0;
}
static void fm_type_stop(void) {
    if (!M13.ed.on) return;
    ced_stop(&M13.ed);
    for (int vk = 8; vk < 0xC0; vk++) F13.hk[vk] = (GetAsyncKeyState(vk) & 0x8000) != 0;      // (keys typed meanwhile are no new presses)
    F13.h_esc = 1; F13.dirty = 1;
    xlog("friendsui: message typing closed");
}
static void fm_type_start(void) {
    if (M13.ed.on || !M13.with[0]) return;
    ced_start(&M13.ed);
    F13.dirty = 1;
    ui_sfx("sfx-select");
    xlog("friendsui: typing a message");
}
static void fm_pick(int idx) {                         // the conversation at list index idx becomes the open one (its thread is asked for)
    if (idx < 0 || idx >= g_fm_n) return;
    const fm_ent_t *e = &g_fm_e[idx];
    if (!strcmp(M13.with, e->id)) return;
    if (M13.ed.on && M13.ed.len) fm_type_stop();       // (half a message never goes to another friend)
    snprintf(M13.with, sizeof M13.with, "%s", e->id);
    snprintf(M13.wname, sizeof M13.wname, "%s", e->name);
    M13.nth = 0; M13.have_th = 0; M13.fetch = 1; M13.sel_ms = GetTickCount64();
    F13.dirty = 1;
}
static void fm_open_id(const char *id) {               // M on a friend row: that friend's chat
    fm_list_build();
    int i = fm_find(id);
    if (i < 0) return;
    F13.col = 2; F13.foc[2] = i; fm_window(g_fm_n);
    fm_pick(i);
    F13.dirty = 1;
    ui_sfx("sfx-select");
}
// a quick reply chip at x, w wide (group-local), its text centred (friends13_widgets: the chip texts are centre aligned with a centre pivot)
static void fm_chip(const char *base, const char *t, float x, float w) {
    char p[128]; float px, py;
    float by = 0.0f; int hb = 0;
    snprintf(p, sizeof p, "%sBg", base);
    uint64_t r = ui_w(p);
    if (r && w_pivot_get(r, &px, &py)) { w_pivot(r, x, py); w_scale(r, w / NR_CHIP_W0, 1.0f); by = py; hb = 1; }
    snprintf(p, sizeof p, "%sTx", base); ui_text(p, t);
    r = ui_w(p);
    // the text's centre line FM_QTX_DN below the chip's (caps 1 px from the chip top, 9 px from its bottom = 6 units high)
    if (r && w_pivot_get(r, &px, &py)) w_pivot(r, x + w / 2.0f, hb ? by + FM_QTX_DN : py);
}
static const char *fm_quick(int k, int shown) {
    static const char *const EN[FM_NQ] = {"GG", "ONE MORE?", "INVITE ME", "REVIVE ME"}, *const PL[FM_NQ] = {"GG", "JESZCZE JEDEN?", "ZAPROŚ MNIE", "OŻYW MNIE"};     // (REVIVE ME, was AFTER THIS MATCH)
    static const char *const ENs[FM_NQ] = {"gg", "one more?", "invite me", "revive me"}, *const PLs[FM_NQ] = {"gg", "jeszcze jeden?", "zaproś mnie", "ożyw mnie"};
    if (k < 0 || k >= FM_NQ) k = 0;
    return shown ? (nt_pl() ? PL[k] : EN[k]) : (nt_pl() ? PLs[k] : ENs[k]);
}
static void fm_send(const char *text) {
    char t[CH_BUF];
    if (!M13.with[0] || !text || ch_clean(text, strlen(text), t, sizeof t, CH_MAXC) <= 0) return;
    if (M13.send_pending || M13.inflight) { fr_msg(FRT("SENDING - WAIT A MOMENT", "WYSYŁANIE - CHWILĘ"), 0); ui_sfx("sfx-menu-error"); return; }
    size_t cap = FM_MSG_ARG - strlen(M13.with) - 1, tl = strlen(t);
    if (tl > cap) { tl = cap; while (tl > 0 && ((unsigned char)t[tl] & 0xC0) == 0x80) tl--; t[tl] = 0; }
    snprintf(M13.send_arg, sizeof M13.send_arg, "%s\n%s", M13.with, t);
    M13.send_pending = 1;
    if (M13.nth >= FR_NTH) { memmove(&M13.th[0], &M13.th[1], sizeof M13.th[0] * (FR_NTH - 1)); M13.nth = FR_NTH - 1; }
    fr_th_t *l = &M13.th[M13.nth++];
    snprintf(l->t, sizeof l->t, "%s", t); l->me = 1; l->age = 0;
    M13.have_th = 1;
    ui_sfx("sfx-select");
    F13.dirty = 1;
    xlog("friendsui: message queued (%d bytes)", (int)tl);
}
static void fm_send_typed(void) {
    if (M13.ed.len) fm_send(M13.ed.b);
    memset(M13.ed.b, 0, sizeof M13.ed.b); M13.ed.len = M13.ed.caret = M13.ed.nch = 0; M13.ed.edit = GetTickCount64();   // (the line stays open for the next one)
    F13.dirty = 1;
}
static void fm_reply(const fr13_t *d, int inflight) {  // fr_net_tick: a reply came; its thread (if it is the open conversation's) and the result of a send
    if (d->has_chat && M13.with[0] && !strcmp(d->chat_with, M13.with) && !M13.send_pending) {
        memcpy(M13.th, d->th, sizeof M13.th); M13.nth = d->nth; M13.have_th = 1; F13.dirty = 1;
    }
    if (inflight) {
        if (!d->ok) {
            fr_msg(!strcmp(d->err, "rate") ? FRT("TOO MANY MESSAGES - WAIT A MOMENT", "ZA DUŻO WIADOMOŚCI - POCZEKAJ CHWILĘ")
                 : !strcmp(d->err, "notfriend") ? FRT("YOU CAN ONLY MESSAGE FRIENDS", "WIADOMOŚCI MOŻNA PISAĆ TYLKO DO ZNAJOMYCH") : fr_err(d->err), 0);
            ui_sfx("sfx-menu-error");
            xlog("friendsui: message refused: %s", d->err);
        } else xlog("friendsui: message sent");
    }
}
static int fm_held(void) {                             // friend messages notice.c holds until the match is over (it shows them then)
    int n = 0;
    for (int q = 0; q < g_nt_pqn; q++) if (!strncmp(g_nt_pq[q], "MESSAGE FROM ", 13) || !strncmp(g_nt_pq[q], "WIADOMOŚĆ OD ", sizeof "WIADOMOŚĆ OD " - 1)) n++;
    return n;
}
static int fr13_unread_total(void) {                   // chat.c: the P FRIENDS badge on the ESC menu
    int u = N13.have ? g_f13.unread_total : 0, h = fm_held() - M13.held_at_parse;
    return u + (h > 0 ? h : 0);
}
static void fm_age(int age, char *o, size_t n) {
    if (age < 60) snprintf(o, n, "%s", FRT("NOW", "TERAZ"));
    else if (age < 3600) snprintf(o, n, FRT("%d MIN AGO", "%d MIN TEMU"), age / 60);
    else if (age < 86400) snprintf(o, n, FRT("%d H AGO", "%d GODZ. TEMU"), age / 3600);
    else snprintf(o, n, FRT("%d D AGO", "%d DNI TEMU"), age / 86400);
}
// The typing line and its n / 200 counter flickered on every key: both are
// double buffered like the in-game chat (chat.c chtw: the new text goes into the twin "<leaf>B", which shows while the old one stays, the old hidden 2 frames
// later). The typed text no longer shrinks to fit: like the chat's typing line it shows the window around the caret (ced_view) at its full size.
#define FM_FTX_PT 39.0f                                 // friends13_widgets mFTx nr.pt(26)
#define FM_FTX_W (FM_PW - 340.0f)
static chtw_t g_fm_tw[2 + 2 * FM_NTL];                  // mFTx, mFCnt, then mThN0 / mThT0 .. (the thread's lines shift on every message in or out)
static uint64_t g_fm_tw_key;
static void fm_set_fit(uint64_t w, const char *t, float pt, float box) {    // (a text wider than its box is scaled down, as gu_fit did)
    float e = nr_twf(t, pt), sc = e > box ? box / e : 1.0f;
    if (sc < 0.6f) sc = 0.6f;
    w_scale(w, sc, sc);
    chw_set_menu(w, t);
}
static void fm_set_ftx(uint64_t w, const char *t) { fm_set_fit(w, t, FM_FTX_PT, FM_FTX_W); }      // the grey ENTER OR CLICK hint is wider than the line
static void fm_set_thn(uint64_t w, const char *t) { fm_set_fit(w, t, 24.0f, FM_PW - 80.0f); }    // a thread line's who + when
// Once per page instance (the handle is the path's hash, the same on every open: the open time and the page-op counter tell them apart). Round 1 also keyed on
// the widget OBJECT (g2_find), and a lookup that missed for a frame re-bound the twins mid-typing - a bind writes its start text into both, which was "", so
// the line went blank for 1 - 2 frames (a clip, frames 655 / 665 / 709 / 990 / 1007). Now a re-bind starts from the text already asked for.
static void fm_tw_bind(void) {
    uint64_t a = ui_w("anim-group.msg.mF.mFTx");
    if (!a) return;
    uint64_t key = a ^ ((uint64_t)g_ui_gen << 40) ^ F13.enter_ms;
    if (key == g_fm_tw_key) return;
    static uint64_t bound_open;
    int fresh = !g_fm_tw[0].a || bound_open != F13.enter_ms;        // a new open starts empty; a re-bind of the same open keeps its texts
    bound_open = F13.enter_ms; g_fm_tw_key = key;
    static char keep[2 + 2 * FM_NTL][CH_BUF + 96];
    for (int i = 0; i < 2 + 2 * FM_NTL; i++) snprintf(keep[i], sizeof keep[i], "%s", fresh ? "" : g_fm_tw[i].want);
    chtw_bind(&g_fm_tw[0], a, ui_w("anim-group.msg.mF.mFTxB"), fm_set_ftx, keep[0], 1);
    chtw_bind(&g_fm_tw[1], ui_w("anim-group.msg.mF.mFCnt"), ui_w("anim-group.msg.mF.mFCntB"), chw_set_menu, keep[1], 1);
    for (int k = 0; k < FM_NTL; k++) {
        char p[64], pb[64];
        snprintf(p, sizeof p, "anim-group.msg.mTh.mThN%d", k); snprintf(pb, sizeof pb, "%sB", p);
        chtw_bind(&g_fm_tw[2 + 2 * k], ui_w(p), ui_w(pb), fm_set_thn, keep[2 + 2 * k], 1);
        snprintf(p, sizeof p, "anim-group.msg.mTh.mThT%d", k); snprintf(pb, sizeof pb, "%sB", p);
        chtw_bind(&g_fm_tw[3 + 2 * k], ui_w(p), ui_w(pb), chw_set_menu, keep[3 + 2 * k], 1);
    }
    { static int n; if (LOGCAP(n, 6)) xlog("friends page: typing line twins bound (mFTxB %s, mFCntB %s)", g_fm_tw[0].b ? "yes" : "MISSING", g_fm_tw[1].b ? "yes" : "MISSING"); }
}
static void fm_tw_tick(void) { fm_tw_bind(); for (int i = 0; i < 2 + 2 * FM_NTL; i++) chtw_tick(&g_fm_tw[i]); }
static void fm_field(uint64_t now) {                   // the typing line (every frame while typing: the caret blinks)
    float my;
    if (!fm_shown(&my)) return;
    char b[CH_BUF + 96];
    if (M13.ed.on) ced_view(&M13.ed, b, sizeof b, now, FM_FTX_W * CH_FIT_FLD, FM_FTX_PT);
    else if (M13.with[0]) snprintf(b, sizeof b, "<font color=\"#8C8C8C\">%s</font>", FRT("ENTER OR CLICK TO TYPE A MESSAGE", "ENTER LUB KLIKNIJ, ABY NAPISAĆ"));
    else b[0] = 0;
    fm_tw_bind();
    chtw_text(&g_fm_tw[0], b);
    if (M13.ed.on) {                                    // the n / 200 counter with every key (it was only written on a full fill and lagged: "9 / 200" at 21 characters)
        snprintf(b, sizeof b, "%d / %d", M13.ed.nch, CH_MAXC);
        chtw_text(&g_fm_tw[1], b);
    }
}
static void fm_fill(void) {
    float my;
    uint64_t g = ui_w("anim-group.msg");
    if (!g) return;
    int on = fm_shown(&my);
    ui_visible("anim-group.msg", on);
    if (!on) return;
    if (my != M13.gy) { M13.gy = my; w_pivot(g, FM_X, my); }
    int n = fm_list_build();
    { int i = M13.with[0] ? fm_find(M13.with) : -1; if (i >= 0) F13.foc[2] = i; }      // the outline follows the open chat when the list reorders (a new message moves it to the top)
    fm_window(n);
    char a[220], p[96], b[600];
    int un = fr13_unread_total();
    if (un > 0) snprintf(a, sizeof a, FRT("%d NEW  |  FRIENDS ONLY", "NOWE: %d  |  TYLKO ZNAJOMI"), un); else snprintf(a, sizeof a, "%s", FRT("FRIENDS ONLY", "TYLKO ZNAJOMI"));
    nr_section("anim-group.msg.msSec", 0.0f, FM_W, 0.0f, FRT("MESSAGES", "WIADOMOŚCI"), a, 36.0f);
    for (int i = 0; i < FM_NV; i++) {
        int idx = F13.off[2] + i;
        snprintf(p, sizeof p, "anim-group.msg.mR%d", i);
        ui_visible(p, idx < n);
        if (idx >= n) continue;
        const fm_ent_t *e = &g_fm_e[idx];
        int open = M13.with[0] && !strcmp(e->id, M13.with), hov = F13.hv_col == 2 && F13.hv_row == i;
        snprintf(p, sizeof p, "anim-group.msg.mR%d.mRNm%d", i, i); gu_fit(p, e->name, FM_TW - 120.0f, 36.0f);
        if (e->t[0]) snprintf(b, sizeof b, "%s%s", e->me ? FRT("YOU: ", "TY: ") : "", e->t);
        else fr_status_word(e->st, b, sizeof b);
        snprintf(p, sizeof p, "anim-group.msg.mR%d.mRLt%d", i, i); gu_fit(p, b, FM_TW - 56.0f, 24.0f);
        int ub = e->unread > 0 && !open;
        snprintf(p, sizeof p, "anim-group.msg.mR%d.mRUb%d", i, i); ui_visible(p, ub);
        snprintf(p, sizeof p, "anim-group.msg.mR%d.mRUt%d", i, i); ui_visible(p, ub);
        if (ub) { char c[8]; snprintf(c, sizeof c, "%d", e->unread > 9 ? 9 : e->unread); ui_text(p, c); }
        snprintf(p, sizeof p, "anim-group.msg.mR%d.mREd%d", i, i); ui_visible(p, open);
        snprintf(p, sizeof p, "anim-group.msg.mR%d.mRFill%d", i, i); gu_fade(p, open || hov);
    }
    int more = n - (F13.off[2] + FM_NV);
    if (more > 0) snprintf(a, sizeof a, FRT("+ %d MORE", "+ JESZCZE %d"), more); else a[0] = 0;
    ui_text("anim-group.msg.mMore", a);
    // the thread: the newest FM_NTL lines, oldest at the top
    const char *empty = !n ? FRT("NO FRIENDS YET - ADD ONE ON THE RIGHT", "NIE MASZ JESZCZE ZNAJOMYCH - DODAJ KOGOŚ PO PRAWEJ")
                      : !M13.with[0] ? FRT("PICK A CHAT ON THE LEFT", "WYBIERZ ROZMOWĘ PO LEWEJ")
                      : !M13.have_th ? FRT("LOADING", "WCZYTYWANIE")
                      : !M13.nth ? FRT("NO MESSAGES YET - SAY HI", "BRAK WIADOMOŚCI - NAPISZ COŚ") : "";
    gu_fit("anim-group.msg.mTh.mThE", empty, FM_PW - 80.0f, 33.0f);
    int start = M13.nth > FM_NTL ? M13.nth - FM_NTL : 0;
    fm_tw_bind();
    for (int k = 0; k < FM_NTL; k++) {
        int idx = start + k;
        if (!M13.with[0] || idx >= M13.nth) { chtw_text(&g_fm_tw[2 + 2 * k], ""); chtw_text(&g_fm_tw[3 + 2 * k], ""); continue; }
        const fr_th_t *l = &M13.th[idx];
        char ag[32]; fm_age(l->age, ag, sizeof ag);
        snprintf(b, sizeof b, "<font color=\"%s\">%s</font>   %s", l->me ? "#D9D86A" : "#B4B4B4", l->me ? FRT("YOU", "TY") : M13.wname, ag);
        chtw_text(&g_fm_tw[2 + 2 * k], b);
        char t[CH_BUF];
        int full = ch_clean(l->t, strlen(l->t), t, sizeof t, CH_MAXC);
        if (full > 130) { ch_clean(l->t, strlen(l->t), t, sizeof t - 4, 127); strcat(t, "..."); }
        chtw_text(&g_fm_tw[3 + 2 * k], t);
    }
    // quick replies: the four chips fill the panel's width (the last one ends at its right edge, like the thread box and the typing line; the room left
    // over is shared out evenly), each text centred in its chip; the white one is the chip under the cursor, else the picked one (keyboard left / right, the pad)
    snprintf(a, sizeof a, "%s", g_pad_mode ? FRT("QUICK REPLY  -  LEFT / RIGHT, ACTION SENDS", "SZYBKA ODPOWIEDŹ  -  LEWO / PRAWO, AKCJA WYSYŁA") : FRT("QUICK REPLY  -  1 - 4", "SZYBKA ODPOWIEDŹ  -  1 - 4"));
    gu_fit("anim-group.msg.mQL", M13.with[0] ? a : "", FM_PW, 24.0f);
    float x = FM_PX, nat[FM_NQ], sum = 0.0f;
    for (int k = 0; k < FM_NQ; k++) { nat[k] = nr_twf(fm_quick(k, 1), FM_QPT) + 32.0f; sum += nat[k]; }
    float extra = (FM_PW - FM_QGAP * (FM_NQ - 1) - sum) / FM_NQ;
    for (int k = 0; k < FM_NQ; k++) {
        char bd[64], bw[64];
        snprintf(bd, sizeof bd, "anim-group.msg.mQ%d", k); snprintf(bw, sizeof bw, "anim-group.msg.mQ%dF", k);
        int vis = M13.with[0] != 0, hi = vis && (M13.hv_q >= 0 ? M13.hv_q == k : M13.qf == k);
        char q1[80], q2[80];
        snprintf(q1, sizeof q1, "%sBg", bd); ui_visible(q1, vis && !hi); snprintf(q2, sizeof q2, "%sTx", bd); ui_visible(q2, vis && !hi);
        snprintf(q1, sizeof q1, "%sBg", bw); ui_visible(q1, hi); snprintf(q2, sizeof q2, "%sTx", bw); ui_visible(q2, hi);
        if (!vis) { M13.qw[k] = 0.0f; continue; }
        float w = k == FM_NQ - 1 ? FM_PX + FM_PW - x : nat[k] + extra;
        fm_chip(bd, fm_quick(k, 1), x, w); fm_chip(bw, fm_quick(k, 1), x, w);
        M13.qx[k] = x; M13.qw[k] = w;
        x += w + FM_QGAP;
    }
    // the typing line
    ui_visible("anim-group.msg.mF", M13.with[0] != 0);
    ui_visible("anim-group.msg.mF.mFUl", M13.ed.on);
    gu_fit("anim-group.msg.mF.mFKey", M13.ed.on ? FRT("ENTER SENDS", "ENTER WYSYŁA") : "", 300.0f, 24.0f);
    snprintf(b, sizeof b, "%d / %d", M13.ed.nch, CH_MAXC);
    fm_tw_bind();
    chtw_text(&g_fm_tw[1], M13.ed.on ? b : "");
    fm_field(GetTickCount64());
}
// the MESSAGES list's input (fr_page_tick, while it is the picked list or a tile was clicked)
static void fm_input(int sel, int up, int down, int left, int right, int wn, int click, int act, int foc_win) {
    int n = fm_list_build(), foc = F13.foc[2], moved = 0;
    if (click && F13.hv_col == 2 && F13.hv_row >= 0) { foc = F13.off[2] + F13.hv_row; F13.col = 2; moved = 1; }
    if (up && n) { foc = (foc + n - 1) % n; moved = 1; }
    if (down && n) { foc = (foc + 1) % n; moved = 1; }
    if (wn && n) { foc -= wn; if (foc < 0) foc = 0; if (foc >= n) foc = n - 1; moved = 1; }
    if (moved && n) { if (foc >= n) foc = n - 1; F13.foc[2] = foc; fm_window(n); fm_pick(foc); fr_sfx(); F13.dirty = 1; }
    if (left) { M13.qf = (M13.qf + FM_NQ - 1) % FM_NQ; fr_sfx(); F13.dirty = 1; }
    if (right) { M13.qf = (M13.qf + 1) % FM_NQ; fr_sfx(); F13.dirty = 1; }
    int q = -1;
    if (foc_win) for (int k = 0; k < FM_NQ; k++) if (ne_key_edge('1' + k, &F13.hk['1' + k]) | ne_key_edge(VK_NUMPAD1 + k, &F13.hk[VK_NUMPAD1 + k])) q = k;
    if (click && M13.hv_q >= 0) q = M13.hv_q;
    if (act && q < 0) q = M13.qf;
    if (q >= 0 && M13.with[0]) { M13.qf = q; fm_send(fm_quick(q, 0)); }
    if ((sel || (click && M13.hv_fld)) && M13.with[0]) fm_type_start();
    else if (sel && !M13.with[0] && n) { F13.foc[2] = foc; fm_pick(foc); }
    else if (sel) ui_sfx("sfx-menu-error");
}
static int fr_col_step(int col, int dir, int ln) {          // the next list for Tab / the bumpers: PARTY (with a party) - FRIENDS - MESSAGES (with the widgets)
    for (int k = 0; k < 3; k++) { col = (col + 3 + dir) % 3; if (col == 1 || (col == 0 && ln) || (col == 2 && fm_avail())) return col; }
    return 1;
}
static void fr_enter(void) {
    int restore = K13.valid, from_pause = g_fr_from_pause;
    uint64_t now = GetTickCount64();
    if (M13.ed.on) ced_stop(&M13.ed);
    g_fr_from_pause = 0;
    memset(&F13, 0, sizeof F13);
    F13.up = 1; F13.enter_ms = now; F13.dirty = 1; F13.col = g_f13.has_party ? 0 : 1; F13.hv_col = F13.hv_row = -1;
    F13.h_sel = F13.h_u = F13.h_d = F13.h_l = F13.h_r = F13.h_back = F13.h_esc = F13.h_pv = F13.h_nx = F13.h_act = F13.h_click = 1;
    F13.t_u = F13.t_d = ~0ULL;
    for (int vk = 8; vk < 0xC0; vk++) F13.hk[vk] = (GetAsyncKeyState(vk) & 0x8000) != 0;      // held when it opens
    memset(F13.rq, -1, sizeof F13.rq); memset(F13.rqx, -1, sizeof F13.rqx);
    F13.ul_q = F13.gl_q = F13.ia_q = F13.pa_q = -1;
    M13.hv_q = -1; M13.gy = -1.0f; M13.fetch = M13.with[0] != 0; M13.sel_ms = 0;
    if (from_pause && fr13_unread_total() > 0 && fm_avail()) F13.col = 2;     // P on the ESC menu with an unread message: straight to MESSAGES
    N13.next_poll = 0; N13.msg_until = 0;
    gu_fade_reset(); memset(g_gu_fit, 0, sizeof g_gu_fit);
    w_alpha(ui_w("anim-group"), 0.0f);
    if (restore) {                                         // pushed again after the engine's pop on Backspace: same text, caret, focus; no entrance
        F13.typing = K13.typing; F13.blen = K13.blen; F13.caret = K13.caret; F13.col = K13.col;
        memcpy(F13.foc, K13.foc, sizeof F13.foc); memcpy(F13.off, K13.off, sizeof F13.off); memcpy(F13.buf, K13.buf, sizeof F13.buf);
        F13.typ_ms = K13.typ_ms; F13.edit_ms = now; F13.inp_a = F13.typing ? 1.0f : 0.0f; F13.ph_a = F13.typing && !F13.blen ? 1.0f : 0.0f;
        F13.enter_ms = now - 800; F13.bs_ms = now; F13.rep_t[2] = now + 400;
        K13.valid = 0;
        xlog("friendsui: page up again (text kept, %d characters, caret %d)", F13.blen, F13.caret);
        return;
    }
    xlog("friendsui: page up");
}
static void fr_close(const char *how) {
    fm_type_stop();
    if (F13.closing) return;
    F13.closing = 1; F13.close_ms = GetTickCount64();
    xlog("friendsui: back (%s)", how);
}
// social.py: S_STATE 1, S_SEARCH 2, S_ADD 3, S_ACCEPT 4, S_REMOVE 5, S_INVITE 6, S_JOIN 7, S_DECLINE 8, S_LEAVE 9, S_KICK 10, S_PROMOTE 11, S_READY 12
static void fr_do(int code, int col, int idx, const fr_row_t *rows, int nr) {
    if (code == A_NONE) return;
    char id[44] = "";
    if (col == 0 && idx < g_f13.nm) snprintf(id, sizeof id, "%s", g_f13.m[idx].id);
    else if (col == 1 && idx >= 0 && idx < nr) {
        const fr_row_t *r = &rows[idx];
        if (r->kind == FR_K_PINV) snprintf(id, sizeof id, "%s", g_f13.pinv[r->idx].id);
        else if (r->kind == FR_K_REQ) snprintf(id, sizeof id, "%s", g_f13.in[r->idx].id);
        else if (r->kind == FR_K_FRIEND) snprintf(id, sizeof id, "%s", g_f13.f[r->idx].id);
        else if (r->kind == FR_K_OUT) snprintf(id, sizeof id, "%s", g_f13.out[r->idx].id);
    }
    switch (code) {
    case A_TYPE: fr_typing_start(); ui_sfx("sfx-select"); break;
    case A_INVITE: fr_act_queue(code, 6, id); break;
    case A_ACCEPT: fr_act_queue(code, 4, id); break;
    case A_JOIN: fr_act_queue(code, 7, id); break;
    case A_DECLINE_P: fr_act_queue(code, 8, id); break;
    case A_DECLINE_R: case A_REMOVE: case A_CANCEL: fr_act_queue(code, 5, id); break;
    case A_PROMOTE: fr_act_queue(code, 11, id); break;
    case A_KICK: fr_act_queue(code, 10, id); break;
    case A_READY: fr_act_queue(code, 12, fr_my_ready() ? "0" : "1"); break;
    case A_LEAVE: fr_act_queue(code, 9, ""); break;
    default: break;
    }
}
static void fr_send_typed(void) {
    while (F13.blen > 0 && F13.buf[F13.blen - 1] == ' ') { F13.blen--; F13.buf[F13.blen] = 0; }
    if (F13.blen < 2) { fr_msg(FRT("TYPE AT LEAST 2 CHARACTERS", "WPISZ CO NAJMNIEJ 2 ZNAKI"), 0); ui_sfx("sfx-menu-error"); F13.caret = F13.blen; fr_edited(); return; }
    char t[40];
    snprintf(t, sizeof t, "%s", F13.buf);
    fr_act_queue(A_ADD, 3, t);
    fr_typing_stop();
}
static void fr_page_alpha(float f) {
    static int lq = -1; static uint64_t le;
    if (F13.enter_ms != le) { le = F13.enter_ms; lq = -1; }
    int q = (int)(f * 24.0f + 0.5f);
    if (q != lq) { lq = q; w_alpha(ui_w("anim-group"), (float)q / 24.0f); }
}
// the rows come in one after the other (50 ms apart, the right list 90 ms later; 240 ms each, ease-out cubic: a fade); the rows stand still (the one focus outline, frFo, would not follow a slide);
// everything is written only when its quantised step changes
static void fr_rows_anim(uint64_t now) {
    for (int col = 0; col < 2; col++) for (int i = 0; i < (col ? FR_RROWS : FR_NL); i++) {
        uint64_t h = F13.rw[col][i];
        if (!h) continue;
        float p = ft_ease(((float)(now - F13.enter_ms) - (float)(50 * i + 90 * col)) / 240.0f);
        int q = (int)(p * 24.0f + 0.5f);
        if (q != F13.rq[col][i]) { F13.rq[col][i] = q; w_alpha(h, (float)q / 24.0f); }
    }
}
static void fr_page_tick(uint64_t now, uint64_t top) {
    (void)top;
    if (!F13.up) fr_enter();
    if (F13.closing) {                                                      // leaving: the page fades out over 170 ms (ease-out), then pops
        if (F13.closing == 1) {
            float p = (float)(now - F13.close_ms) / 170.0f;
            if (p >= 1.0f) { F13.closing = 2; pop_page(); }
            else fr_page_alpha(1.0f - ft_ease(p));
            gu_fade_tick(now);
        }
        return;
    }
    // ---- input
    int sel = menu_edge(0x6695c5b7921bb5ddULL /* menu-select */, &F13.h_sel);
    int up = gu_rep(&F13.h_u, &F13.t_u, fnv64("menu-up")), down = gu_rep(&F13.h_d, &F13.t_d, fnv64("menu-down"));
    int left = menu_edge(fnv64("menu-left"), &F13.h_l), right = menu_edge(fnv64("menu-right"), &F13.h_r);
    int back = menu_edge(fnv64("menu-back"), &F13.h_back);
    int bp = MENU_PREV_TAB(&F13.h_pv), bn = MENU_NEXT_TAB(&F13.h_nx);
    int pad_act = menu_edge_pad("menu-action", &F13.h_act);
    int esc_now = game_focused() && (GetAsyncKeyState(VK_ESCAPE) & 0x8000) != 0, esc = esc_now && !F13.h_esc;
    F13.h_esc = esc_now;
    int foc_win = game_focused();
    int click = g_click_edge;
    fr_scan();
    int wn = wheel_notches();
    if (F13.typing) {
        if (foc_win) fr_typing_tick(now);
        // Backspace is menu-back too: it edits here (and the engine's pop of the page is undone, feature_friends13); only the pad's B / a right click cancel typing
        int kb_bs = (GetAsyncKeyState(VK_BACK) & 0x8000) || (F13.bs_ms && now - F13.bs_ms < 300);
        int pad_back = back && !kb_bs;
        if (esc || pad_back) { fr_typing_stop(); esc = 0; }
        else if (foc_win && ne_key_edge(VK_RETURN, &F13.hk[VK_RETURN])) fr_send_typed();
        else if (click && F13.hv_sel) fr_send_typed();                                  // the SEND prompt
        else if (click && !F13.hv_back && !(F13.hv_col == 1 && F13.hv_row == 0 && F13.off[1] == 0)) fr_typing_stop();     // a click anywhere else leaves the field
        back = 0;
        if (!F13.hv_back) click = 0;
        sel = up = down = left = right = bp = bn = pad_act = wn = 0;
    }
    if (M13.ed.on) {                                                        // typing a message: the key catcher has every key (Enter sends, Esc stops); a pad's B stops too
        int r = foc_win ? ced_tick(&M13.ed) : CED_NONE;
        if (!foc_win) fm_type_stop();
        else if (r == CED_SEND) fm_send_typed();
        else if (r == CED_CANCEL || back) fm_type_stop();
        else if (click && F13.hv_sel) fm_send_typed();                                  // the SEND prompt
        else if (click && M13.hv_q >= 0) fm_send(fm_quick(M13.hv_q, 0));
        else if (click && !M13.hv_fld && !F13.hv_back) fm_type_stop();                  // a click anywhere else leaves the line
        fm_field(now);
        esc = back = 0;
        if (!F13.hv_back) click = 0;
        sel = up = down = left = right = bp = bn = pad_act = wn = 0;
    }
    if (esc || (click && F13.hv_back)) { fr_close(esc ? "Esc" : "BACK clicked"); return; }
    if (back) F13.back_f = g_frame ? g_frame : 1;                        // the engine pops a pushed page on menu-back by itself; judged 6 frames later
    if (F13.back_f && g_frame >= F13.back_f + 6) { F13.back_f = 0; if (top_page() == fr_page_id()) { fr_close("menu-back"); return; } }
    int kp = foc_win && !F13.typing && !M13.ed.on && ne_key_edge('P', &F13.hk['P']);
    if (kp) { fr_close("P"); return; }
    fr_row_t rows[1 + FR_NPI + 2 * FR_RROWS + FR_NF];
    int nr = fr_right_rows(rows), ln = fr_left_n();
    int kx = 0, kr = 0, kl = 0, ktab = 0, km = 0;
    if (foc_win && !F13.typing && !M13.ed.on) {
        km = ne_key_edge('M', &F13.hk['M']);
        kx = ne_key_edge('X', &F13.hk['X']) | ne_key_edge(VK_DELETE, &F13.hk[VK_DELETE]);
        kr = ne_key_edge('R', &F13.hk['R']);
        kl = ne_key_edge('L', &F13.hk['L']);
        ktab = ne_key_edge(VK_TAB, &F13.hk[VK_TAB]) | ne_key_edge('Q', &F13.hk['Q']) | ne_key_edge('E', &F13.hk['E']);
    }
    if (!N13.have) { sel = up = down = 0; kx = kr = kl = km = 0; }
    // a click on a row ONLY moves the selection;
    // an action happens by ENTER / the pad's SELECT / X / the pad's ACTION or a click on the prompt in the footer (the prompt names the action). The menu-select the
    // engine raises with a mouse click is dropped (a few frames after any click).
    if (click) F13.click_f = g_frame ? g_frame : 1;
    if (sel && F13.click_f && g_frame - F13.click_f <= 8) { sel = 0; xlog("friendsui: menu-select ignored: it came with a click (select only moves)"); }
    int sw = ktab || bp || bn || ((left || right) && F13.col != 2) || (click && F13.hv_sw);      // (on MESSAGES left / right pick the quick reply)
    if (sw && N13.have) {
        int c = fr_col_step(F13.col, bp || left ? -1 : 1, ln);
        if (c != F13.col) {
            F13.col = c;
            if (c == 2) { fm_list_build(); fm_window(g_fm_n); if (!M13.with[0] && g_fm_n) fm_pick(F13.foc[2]); }
            fr_sfx();
        }
        F13.dirty = 1; sel = up = down = wn = left = right = 0;
    }
    if (F13.col == 2 ? !(click && F13.hv_row >= 0 && F13.hv_col != 2) : (click && (F13.hv_col == 2 || M13.hv_q >= 0 || M13.hv_fld))) {     // (a chip / typing line click: whichever list is picked)
        if (click && F13.col != 2) { F13.col = 2; F13.dirty = 1; }
        fm_input(sel && !g_pad_mode, up, down, left, right, wn, click, kx || pad_act || (sel && g_pad_mode), foc_win);
        if (sel || kx || pad_act || up || down) F13.dirty = 1;
    } else {
    int col = F13.col, n = col ? nr : ln;                               // (col 2 here only with a click on a PARTY / FRIENDS row: the click below picks that list)
    int foc = F13.foc[col];
    if (up && n) { foc = (foc + n - 1) % n; fr_sfx(); }
    if (down && n) { foc = (foc + 1) % n; fr_sfx(); }
    if (wn && n) { foc -= wn; if (foc < 0) foc = 0; if (foc >= n) foc = n - 1; fr_sfx(); }
    int clk_row = 0;
    if (click && F13.hv_row >= 0) {
        int ci = F13.hv_col, ri = F13.hv_col ? F13.off[1] + F13.hv_row : F13.hv_row;
        col = ci; F13.col = col; foc = ri; n = col ? nr : ln; fr_sfx(); clk_row = 1;
    }
    if (click && !clk_row && F13.hv_sel && !F13.typing) sel = 1;        // the footer prompt (primary action of the focused row)
    if (click && !clk_row && F13.hv_act && !F13.typing) pad_act = 1;    // the footer prompt (second action)
    if (foc >= n) foc = n ? n - 1 : 0;
    if (foc != F13.foc[col] || col != F13.col) { F13.foc[col] = foc; F13.col = col; F13.dirty = 1; }
    int pri, sec;
    fr_row_actions(col, F13.foc[col], rows, nr, &pri, &sec);
    if (sel) { if (pri != A_NONE) fr_do(pri, col, F13.foc[col], rows, nr); else if (n) ui_sfx("sfx-menu-error"); }
    if (kx || pad_act) { if (sec != A_NONE) fr_do(sec, col, F13.foc[col], rows, nr); }
    if (kr && g_f13.has_party && !g_f13.me_leader) fr_do(A_READY, 0, g_f13.nm, rows, nr);
    if (kl && g_f13.has_party) fr_do(A_LEAVE, 0, g_f13.nm + 1, rows, nr);
    if (km && col == 1 && F13.foc[1] < nr && rows[F13.foc[1]].kind == FR_K_FRIEND) fm_open_id(g_f13.f[rows[F13.foc[1]].idx].id);     // M: a message to the focused friend
    if (sel || kx || pad_act || kr || kl || up || down || sw) F13.dirty = 1;
    }
    static const uint32_t OFF_MS[] = {33, 100, 250, 670, 1500, 3000};
    if (F13.stage < (int)(sizeof OFF_MS / sizeof OFF_MS[0]) && now - F13.enter_ms >= OFF_MS[F13.stage]) { F13.stage++; F13.dirty = 1; gu_fade_reassert(); }
    {   // the hover highlight follows the cursor
        static int lh = -9, lc = -9;
        static int lq = -9, lf = -9;
        if (lh != F13.hv_row || lc != F13.hv_col) { lh = F13.hv_row; lc = F13.hv_col; F13.dirty = 1; }
        if (lq != M13.hv_q || lf != M13.hv_fld) {                    // (a quick reply chip under the cursor never lit up - its hover set no redraw)
            if (M13.hv_q >= 0 && M13.hv_q != lq) { M13.qf = M13.hv_q; fr_sfx(); }     // like the rows: the chip under the cursor becomes the picked one
            lq = M13.hv_q; lf = M13.hv_fld; F13.dirty = 1;
        }
    }
    if (N13.msg_until && now > N13.msg_until) { N13.msg_until = 0; F13.dirty = 1; }
    { static int lpd = -1; if (lpd != g_pad_mode) { lpd = g_pad_mode; F13.dirty = 1; } }       // the key hint line follows the device in use
    if (F13.dirty || !(g_frame % 90)) { F13.dirty = 0; fr_fill(); }
    fr_inp_tick(now);
    fr_rows_anim(now);
    gu_fade_tick(now);
    {   // page fade-in: 0 -> 1 over 220 ms (ease-out), in 1/24 steps
        float f = ft_ease((float)(now - F13.enter_ms) / 220.0f);
        fr_page_alpha(f);
    }
}
// ------------------------------------------------------------------ the button on the MP menu / FIND MATCH
static int g_fr_held_p, g_fr_h_nx;                     // P / menu-next as of the last frame either the button or the page looked (closing the page with P must not reopen it)
static int fr_btn_cursor(void) {                       // the cursor is over the strip (canvas units = friends13_widgets BTN_*)
    float cx, cy;
    return ui_cursor_canvas(&cx, &cy) && cx >= 2500.0f && cx <= 3682.0f && cy >= 266.0f && cy <= 386.0f;      // (above the lobby box, BTN_Y 266)
}
static int fr13_btn_over(void) { return g_fr_off == 0 && (fr_btn_cursor() || fr_toast_hit()); }
// Before FIND MATCH is pressed the lobby shows the party members in its rows instead of 1/8: winmm fills the
// lobby rows from its name vector only while searching (session state 3, re/decomp_cd.c); on the MP menu it writes row 0 (us) alone. The party mates
// go into rows 1.. here, and the count follows; a party that ends clears them once.
static void fr_lobby_party_rows(void) {
    static int shown;
    int st = *(volatile int *)VMA(0x180167968), want = N13.have && g_f13.has_party && st >= 0 && st <= 2 && fr_menu_vis();   // idle / connecting / connected only: from searching (3) on winmm owns the rows (a found player's row went blank, then showed our mate)
    char p[96], a[24];
    if (!want) {
        if (shown && st >= 0 && st <= 2) { for (int r = 1; r <= shown; r++) { snprintf(p, sizeof p, "anim-group.lobbyPanel.lobbyList.Player%d.nameLabel", r); ui_text(p, ""); }
                     ui_text("anim-group.lobbyPanel.lobbyCount", "1 / 8"); }
        shown = 0;                                       // searching / matched: never touch winmm's rows
        return;
    }
    int r = 1;
    for (int i = 0; i < g_f13.nm && r < 8; i++) {
        if (g_f13.m[i].me || !g_f13.m[i].name[0]) continue;
        snprintf(p, sizeof p, "anim-group.lobbyPanel.lobbyList.Player%d.nameLabel", r++);
        ui_text(p, g_f13.m[i].name);
    }
    for (int k = r; k <= shown; k++) { snprintf(p, sizeof p, "anim-group.lobbyPanel.lobbyList.Player%d.nameLabel", k); ui_text(p, ""); }
    if (r - 1 != shown) xlog("friendsui: lobby list shows %d party mate%s before FIND MATCH", r - 1, r == 2 ? "" : "s");
    shown = r - 1;
    snprintf(a, sizeof a, "%d / 8", r);
    ui_text("anim-group.lobbyPanel.lobbyCount", a);
}
// ------------------------------------------------------------------ the party rule + the lobby tabs
// Party members do not search, they only ready up (their find match button becomes ready up): a NON-leader member's FIND MATCH row reads READY UP / UNREADY; the press is
// a ready toggle (op 0xD8 sub 12), never a search - fr_search_gate (called by t2r-ext's mmreq hook, the moment the engine sends the search request) says so and the page is popped
// again; the daemon (social.py search_gate) refuses to queue such a member as well. The LEADER's FIND MATCH searches for the whole party, but only when every member is ready
// (otherwise a deny note names who is not). While the leader searches, a READY member's client pushes the search page by itself (autofind's push: winmm's page tick starts the
// search) so the party queues together; a member who backs out of that search is set unready. Ready flags reset when a match forms (daemon start_match).
// Rework (the ready-up system was unintuitive and bug-prone):
// - a member's press is handled on the MP menu itself (modepick -> fr_member_ready_press): the ready toggle, no search page at all;
// - the leader is never held back: FIND MATCH always searches, the daemon waits for the members (PARTY-WAIT) and every READY member's client follows;
// - members join a party READY and stay ready after a match (daemon), so the usual round is: the leader presses FIND MATCH, everyone goes in.
static uint64_t g_pq_auto;                              // GetTickCount64 of our own follow-the-leader push (its mmreq must go through); also set by move_rejoin_tick
static int fr_in_party(void) { return N13.have && g_f13.has_party && g_f13.nm >= 2; }
// 0 = the search request goes on; 1 = a member's READY UP / UNREADY press (toggled here, the caller pops the page); 2 = the leader is held back (a mate is not ready)
static int ch_in_party(void) { return fr_in_party(); }          // chat.c: the PARTY tab can send
static int fr13_page_up(void) { return F13.up; }        // t2r-ext.c menu_hud_hide_tick: no health / ammo ring under the page (it showed over the page opened from ESC)
static void fr13_open_from_pause(void) {                       // chat.c: P (the pad's menu-next) on the ESC menu: the FRIENDS page over the match
    static uint64_t last;
    uint64_t now = GetTickCount64();
    if (F13.up || top_page() == fr_page_id() || now - last < 800) return;
    last = now; g_fr_from_pause = 1; N13.next_poll = 0;
    xlog("friendsui: P on the ESC menu - pushing to1/friends13 over the match");
    push_page("to1/friends13");
}
static int fr_party_member(void) { return fr_in_party() && !g_f13.me_leader; }
static int fr_search_gate(void) {
    if (!fr_in_party()) return 0;
    uint64_t now = GetTickCount64();
    if (g_f13.me_leader) {
        for (int i = 0; i < g_f13.nm; i++) {
            const fr_m_t *m = &g_f13.m[i];
            if (!m->me && !m->leader && !m->ready) xlog("friendsui: leader searches, %s is not ready yet (the daemon waits for it)", m->name);
        }
        return 0;
    }
    if (g_pq_auto && now - g_pq_auto < 8000) { g_pq_auto = 0; return 0; }
    xlog("friendsui: a member's search request outside the follow-the-leader push - page popped, ready state unchanged");
    return 1;
}
// a member's FIND MATCH (READY UP / UNREADY) press on the MP menu: the toggle only (the row label follows the party state)
static void fr_member_ready_press(void) {
    static uint64_t last;
    uint64_t now = GetTickCount64();
    if (now - last < 600) return;                         // (one press = one toggle: a held key or a double click never flips it back)
    last = now;
    int r = fr_my_ready();
    fr_act_queue(A_READY, 12, r ? "0" : "1");
    xlog("friendsui: member's FIND MATCH = %s%s", r ? "UNREADY" : "READY UP", !r && g_f13.lsearch ? " (the leader searches: we follow)" : "");
}
static void fr_party_tick(uint64_t now, uint64_t top, uint64_t p_main) {
    static int lat, in, pr;
    static uint64_t pushed_at;
    static char lab_set;
    int mem = fr_in_party() && !g_f13.me_leader && fr_menu_vis();
    if (mem || lab_set) {                                  // the menu row: FIND MATCH -> READY UP / UNREADY for a member
        const char *t = mem ? (fr_my_ready() ? FRT("UNREADY", "NIEGOTOWY") : FRT("READY UP", "GOTOWY")) : "FIND MATCH";
        if (top == p_main) { ui_text("anim-group.menuList.FindMatch.label0", t); lab_set = mem; }
    }
    // The party did not queue people: the daemon acks every FIND MATCH with the SEARCHING state before its party gate decides, so a request it then refuses
    // (member while the leader is not queued yet, leader while its ready flags differ) left the page up as a fake search: rows "<name>
    {
        static uint64_t fake_t0;
        int me_p = -1;
        for (int i = 0; i < g_f13.nm; i++) if (g_f13.m[i].me) me_p = fr13_presence(g_f13.m[i].status);
        static uint64_t P_FM; if (!P_FM) P_FM = page_id("find-match-menu");
        if (fr_in_party() && top == P_FM && me_p >= 0 && me_p < 3 && now - g_pq_auto > 9000) {
            if (!fake_t0) fake_t0 = now;
            else if (now - fake_t0 > 9000) { fake_t0 = 0; g_mm_back = 1; lat = 0; in = 0; xlog("friendsui: search page up for 9 s but the daemon has us queued nowhere - popped (a retry follows if the leader searches)"); }
        } else fake_t0 = 0;
    }
    int r = fr_my_ready();
    if (r && !pr) lat = 0;
    pr = r;
    int ls = mem && g_f13.lsearch;
    if (!ls) { lat = 0; in = 0; return; }
    int st = *(volatile int *)VMA(0x180167968);
    if (in) {
        if (top == p_main && st < 3 && now - pushed_at > 4000) { in = 0; fr_act_queue(A_READY, 12, "0"); xlog("friendsui: member left the party search - unready"); }
        return;
    }
    if (lat || !r || top != p_main || st != 2 || match_substate() == 6) return;
    lat = 1; in = 1; pushed_at = now; g_pq_auto = now;
    push_page_now("to1/find-match-menu");
    xlog("friendsui: the leader searches and we are ready - search page pushed (the party queues together)");
}
enum { TB_NONE, TB_GREY, TB_GREEN, TB_BLUE, TB_RED };
static void fr_lobby_tabs(void) {
    static int last[8] = {-1, -1, -1, -1, -1, -1, -1, -1};
    static unsigned gen = ~0u;
    static uint64_t when;
    int kind[8] = {0};
    int st = *(volatile int *)VMA(0x180167968);
    uint8_t *lo = lobby_obj();
    int fidx[8], fen[8], fn = st >= 3 && top_page() != page_id("main-menu") ? lobby_rows_sorted(lo, fidx, fen) : -1;
    if (fn >= 0) {
        kind[0] = TB_BLUE;
        for (int k = 0; k < fn; k++) kind[k + 1] = fen[k] ? TB_RED : TB_BLUE;
    } else if (st == 3 && top_page() == page_id("find-match-menu") && g_rq_back + g_rq_post > 0) {
    } else if (st >= 3 && top_page() == page_id("find-match-menu")) {
        kind[0] = TB_BLUE;
        for (int r = 1; r < 8; r++) kind[r] = g_srch_tab[r] == 1 ? TB_BLUE : g_srch_tab[r] == 2 ? TB_RED : g_srch_tab[r] == 3 ? TB_GREY : TB_NONE;
    } else if (fr_in_party()) {
        kind[0] = fr_my_ready() || g_f13.me_leader ? TB_GREEN : TB_GREY;
        if (st <= 2) {
            int r = 1;
            for (int i = 0; i < g_f13.nm && r < 8; i++) {
                if (g_f13.m[i].me || !g_f13.m[i].name[0]) continue;
                kind[r++] = g_f13.m[i].ready ? TB_GREEN : TB_GREY;
            }
        }
    }
    uint64_t now = GetTickCount64();
    int same = 1;
    for (int i = 0; i < 8; i++) if (kind[i] != last[i]) same = 0;
    if (same && gen == g_ui_gen && now - when < 1000) return;
    static const char *const LEAF[5] = {"", "tabGrey", "tabGreen", "tabBlue", "tabRed"};
    char p[112];
    for (int r = 0; r < 8; r++)
        for (int k = 1; k <= 4; k++) { snprintf(p, sizeof p, "anim-group.lobbyPanel.lobbyList.Player%d.%s", r, LEAF[k]); ui_visible(p, kind[r] == k); }
    memcpy(last, kind, sizeof last); gen = g_ui_gen; when = now;
}
static void fr_lobby_names(void) {
    int idx[8], en[8], st = *(volatile int *)VMA(0x180167968);
    int n = st >= 3 && top_page() != page_id("main-menu") ? lobby_rows_sorted(lobby_obj(), idx, en) : -1;
    if (n <= 0) return;
    uint8_t *lo = lobby_obj();
    for (int k = 0; k < n; k++) {
        char p[96], nm[0x32];
        snprintf(p, sizeof p, "anim-group.lobbyPanel.lobbyList.Player%d.nameLabel", k + 1);
        snprintf(nm, sizeof nm, "%.48s", (const char *)lo + 0x1d + idx[k] * 0x32 + 1);
        if (nm[0]) ui_text(p, nm);
    }
}
static int fr_row_names(char nm[8][48], int me[8]) {
    int used = 0;
    int st = *(volatile int *)VMA(0x180167968);
    uint8_t *lo = lobby_obj();
    int fidx[8], fen[8], fn = st >= 3 ? lobby_rows_sorted(lo, fidx, fen) : -1;
    if (fn >= 0) {
        me[0] = 1;
        for (int k = 0; k < fn; k++) snprintf(nm[k + 1], sizeof nm[0], "%.40s", (const char *)lo + 0x1d + fidx[k] * 0x32 + 1);
        used = fn + 1;
    } else if (st >= 3 && top_page() == page_id("find-match-menu")) {
        me[0] = 1; used = 8;
        for (int r = 1; r < 8; r++) snprintf(nm[r], sizeof nm[0], "%s", g_srch_name[r]);
    } else {
        me[0] = 1; used = 1;
        if (fr_in_party() && st <= 2) {
            int r = 1;
            for (int i = 0; i < g_f13.nm && r < 8; i++) {
                if (g_f13.m[i].me || !g_f13.m[i].name[0]) continue;
                snprintf(nm[r++], sizeof nm[0], "%.40s", g_f13.m[i].name);
            }
            used = r;
        }
    }
    return used;
}
static void fr_lobby_ranks(void) {
    static char last[8][48]; static int lastme[8]; static unsigned gen = ~0u; static uint64_t when; static LONG ver = -1;
    char nm[8][48] = {{0}}; int me[8] = {0};
    int used = fr_row_names(nm, me);
    uint64_t now = GetTickCount64();
    LONG v = g_rkb_ver;
    int same = gen == g_ui_gen && ver == v && now - when < 1000 && !memcmp(last, nm, sizeof last);
    for (int i = 0; i < 8 && same; i++) if (lastme[i] != me[i]) same = 0;
    if (same) return;
    for (int r = 0; r < 8; r++) {
        char base[96]; snprintf(base, sizeof base, "anim-group.lobbyPanel.lobbyList.Player%d", r);
        if (r >= used) { char i[120], n[120]; snprintf(i, sizeof i, "%s.rkIcon", base); snprintf(n, sizeof n, "%s.rkNum", base); rank_ui(i, n, -1, 0); continue; }
        rkb_draw_at(base, "rkIcon", "rkNum", nm[r], me[r]);
    }
    memcpy(last, nm, sizeof last); memcpy(lastme, me, sizeof lastme); gen = g_ui_gen; ver = v; when = now;
}
// (party - not searching)" suffix is cut off in t2r-ext.c srch_name_write; the grey / green gradient is fr_lobby_tabs.
// (lobby panel) the empty rows of a lobby: no name, no spinner, a small grey OPEN in lbSt (design A; the template's SEARCHING + spinner otherwise)
static int fr_seat_text(const char *n) { return !n || !n[0] || !strcmp(n, "SEARCHING") || !strcmp(n, "SZUKANIE") || strstr(n, "OPEN SEAT") || strstr(n, "WOLNE MIEJSCE"); }
static void fr_lobby_open_seats(int lobby) {
    static int was[8]; static unsigned gen = ~0u; static uint64_t at;
    uint64_t now = GetTickCount64();
    if (!lobby && !was[1] && !was[2] && !was[3] && !was[4] && !was[5] && !was[6] && !was[7]) return;
    if (gen == g_ui_gen && now - at < 500) return;
    gen = g_ui_gen; at = now;
    char p[112];
    for (int r = 1; r < 8; r++) {
            int seat = lobby && fr_seat_text(g_srch_name[r]);      // (the text itself: t2r-ext.c srch_name_write swaps winmm's own "SEARCHING" writes)
        snprintf(p, sizeof p, "anim-group.lobbyPanel.lobbyList.Player%d.spinner", r);
        w_alpha(ui_w(p), seat ? 0.0f : 1.0f);
        was[r] = seat;
    }
}
// (lobby panel) the header's right side: NEXT MATCH IN m:ss (the count of searchers otherwise, winmm's / fr_lobby_party_rows' "n / 8")
static void fr_lobby_head(int lobby) {
    g_lobby_ui = lobby;
    if (!lobby) { g_lobby_head[0] = 0; return; }       // (winmm's next "n / 8" write shows again)
    g_lobby_cnt_w = ui_w("anim-group.lobbyPanel.lobbyCount");
    char a[160];
    if (g_rq_left > 0) snprintf(a, sizeof a, "<font color=\"#8C8C8C\">%s</font>   %d:%02d", FRT("NEXT MATCH IN", "NASTĘPNY MECZ ZA"), g_rq_left / 60, g_rq_left % 60);
    else snprintf(a, sizeof a, "<font color=\"#8C8C8C\">%s</font>", FRT("STARTING", "START"));
    if (strcmp(a, g_lobby_head)) { snprintf(g_lobby_head, sizeof g_lobby_head, "%s", a); ui_text_raw("anim-group.lobbyPanel.lobbyCount", a); }      // (once per change; winmm's per-frame writes are swapped)
}
static void fr_lobby_party_marks(void) {
    static int last[8][3]; static unsigned gen = ~0u; static uint64_t when;
    int mk[8][3] = {{0}};                                  // [row] = {party? 0/1, lead? 0/1, ready line 0 none / 1 READY / 2 NOT READY / 3 IN SUMMARY}
    if (fr_in_party()) {
        char nm[8][48] = {{0}}; int me[8] = {0};
        int used = fr_row_names(nm, me), st = *(volatile int *)VMA(0x180167968);
        int found = st >= 3 && top_page() != page_id("main-menu") && lobby_rows_sorted(lobby_obj(), (int[8]){0}, (int[8]){0}) >= 0;
        for (int r = 0; r < used && r < 8; r++) {
            const fr_m_t *m = NULL;
            if (me[r]) { for (int i = 0; i < g_f13.nm; i++) if (g_f13.m[i].me) m = &g_f13.m[i]; }
            else if (nm[r][0]) { for (int i = 0; i < g_f13.nm && !m; i++) if (!g_f13.m[i].me && g_f13.m[i].name[0] && !_stricmp(g_f13.m[i].name, nm[r])) m = &g_f13.m[i]; }
            if (!m) continue;
            mk[r][0] = 1; mk[r][1] = m->leader != 0;
            int idle = st <= 2 || g_srch_tab[r] == 3;      // menu, or a mate that is not in the search
            mk[r][2] = found || !idle ? 0 : (m->leader || m->ready) ? 1 : 2;
        }
    }
    // (lobby panel mockup) while our search is a lobby's the status is one line right aligned (lbSt): READY (members back, us = row 0), IN SUMMARY (still on
    // the post-match screens), NEW (from the queue); the party's two-line tag gives way to it, the party bar stays (daemon searching_frame ' (lobby)' / ' (summary)' / ' (new)')
    int lst[8] = {0};
    int lobby = *(volatile int *)VMA(0x180167968) == 3 && top_page() == page_id("find-match-menu") && g_rq_back + g_rq_post > 0;
    if (lobby) {
        lst[0] = 1;
        for (int r = 1; r < 8; r++) { lst[r] = g_srch_lob[r] ? g_srch_lob[r] : fr_seat_text(g_srch_name[r]) ? 4 : 0; mk[r][2] = 0; }      // (4 = an open seat: OPEN)
        mk[0][2] = 0;
    }
    fr_lobby_open_seats(lobby);
    fr_lobby_head(lobby);
    {
        static int lls[8] = {-1, -1, -1, -1, -1, -1, -1, -1}; static unsigned lsg = ~0u;
        if (memcmp(lls, lst, sizeof lst) || lsg != g_ui_gen) {
            memcpy(lls, lst, sizeof lst); lsg = g_ui_gen;
            char q[112];
            for (int r = 0; r < 8; r++) {
                snprintf(q, sizeof q, "anim-group.lobbyPanel.lobbyList.Player%d.lbSt", r);
                ui_visible(q, lst[r] != 0);
                if (lst[r] == 1) ui_text(q, FRT("<font color=\"#B4B6BA\">READY</font>", "<font color=\"#B4B6BA\">GOTOWY</font>"));
                else if (lst[r] == 2) ui_text(q, FRT("<font color=\"#6E7074\">IN SUMMARY</font>", "<font color=\"#6E7074\">W PODSUMOWANIU</font>"));
                else if (lst[r] == 3) ui_text(q, FRT("<font color=\"#8FB88A\">NEW</font>", "<font color=\"#8FB88A\">NOWY</font>"));
                else if (lst[r] == 4) ui_text(q, FRT("<font color=\"#5A5C60\">OPEN</font>", "<font color=\"#5A5C60\">WOLNE</font>"));
            }
        }
    }
    uint64_t now = GetTickCount64();
    if (gen == g_ui_gen && now - when < 1000 && !memcmp(last, mk, sizeof last)) return;
    char p[112];
    for (int r = 0; r < 8; r++) {
        const char *b = "anim-group.lobbyPanel.lobbyList.Player";
        snprintf(p, sizeof p, "%s%d.partyBar", b, r); ui_visible(p, mk[r][0]);
        snprintf(p, sizeof p, "%s%d.pmRole", b, r); ui_visible(p, mk[r][0] && !lobby);      // (a lobby: the bar only, lbSt has the status)
        if (mk[r][0]) ui_text(p, mk[r][1] ? FRT("PARTY LEAD", "LIDER GRUPY") : FRT("PARTY", "GRUPA"));
        snprintf(p, sizeof p, "%s%d.pmReady", b, r); ui_visible(p, mk[r][2] == 1); if (mk[r][2] == 1) ui_text(p, FRT("READY", "GOTOWY"));
        snprintf(p, sizeof p, "%s%d.pmNot", b, r); ui_visible(p, mk[r][2] >= 2);
        if (mk[r][2] == 2) ui_text(p, FRT("NOT READY", "NIEGOTOWY")); else if (mk[r][2] == 3) ui_text(p, FRT("IN SUMMARY", "W PODSUMOWANIU"));
    }
    memcpy(last, mk, sizeof last); gen = g_ui_gen; when = now;
}
static void fr_button_tick(uint64_t now) {
    static int armed, last_vis = -1;
    static uint64_t last_open;
    fr_lobby_party_rows();
    fr_lobby_names();
    fr_lobby_tabs();
    fr_lobby_ranks();
    fr_lobby_party_marks();
    { static uint64_t P_MAIN; if (!P_MAIN) P_MAIN = page_id("main-menu"); fr_party_tick(now, top_page(), P_MAIN); }
    // the strip also stays up on FIND MATCH while the search runs (substate past the menu's
    // 1 / 2, before the match flow): it shows the party / online count and the badge there; P / click open the page only where they always did (fr_menu_vis)
    static uint64_t P_FMB; if (!P_FMB) P_FMB = page_id("find-match-menu");
    int open_ok = fr_menu_vis();
    int visible = open_ok || (top_page() == P_FMB && match_substate() != 6 && !g_mf_code_now && !g_veil_on && !g_pm.pending && g_lo_state == LO_NONE
                              && !g_mh_load && !g_mh_st && !g_ls_own);
    {   // written again on a page change too (MP menu -> FIND MATCH kept visible at 1, so the new page's strip stayed at its template's hidden)
        static uint64_t vis_top; static unsigned vis_gen; uint64_t tp = top_page();
        if (visible != last_vis || tp != vis_top || vis_gen != g_ui_gen) { last_vis = visible; vis_top = tp; vis_gen = g_ui_gen; ui_visible("anim-group.friendsBtn", visible); }
    }
    if (!visible) return;
    int hov = fr_btn_cursor();
    int badge = N13.have ? fr13_badge(&g_f13) : 0;
    char a[40];
    ui_text("anim-group.friendsBtn.frLabel", FRT("FRIENDS", "ZNAJOMI"));
    if (!N13.have) a[0] = 0;
    else if (g_f13.has_party) snprintf(a, sizeof a, FRT("PARTY %d/%d", "GRUPA %d/%d"), g_f13.nm, g_f13.pmax ? g_f13.pmax : 4);
    else { int on = 0; for (int i = 0; i < g_f13.nf; i++) if (fr13_presence(g_f13.f[i].status) > 0) on++; snprintf(a, sizeof a, "%d ONLINE", on); }
    ui_text("anim-group.friendsBtn.frSub", a);
    ui_visible("anim-group.friendsBtn.frBadgeBg", badge > 0);
    ui_visible("anim-group.friendsBtn.frBadge", badge > 0);
    if (badge > 0) { snprintf(a, sizeof a, "%d", badge > 9 ? 9 : badge); ui_text("anim-group.friendsBtn.frBadge", a); }
    gu_fade("anim-group.friendsBtn.frFill", hov);
    if (badge != N13.last_badge) { N13.last_badge = badge; xlog("friendsui: button badge %d", badge); }
    int kp = game_focused() && (GetAsyncKeyState('P') & 0x8000) != 0, edge = kp && !g_fr_held_p;
    g_fr_held_p = kp;
    int pad = MENU_NEXT_TAB(&g_fr_h_nx);        // RB on the pad; never on the first look (a button held on arrival)
    if (game_focused() && (GetAsyncKeyState('E') & 0x8000)) pad = 0;       // (menu-next-tab is E on the keyboard: on the MP menu only P opens the page from the keyboard)
    if (!armed) { armed = 1; pad = 0; edge = 0; }
    int clk = g_click_edge && hov;
    if (!open_ok) return;                       // (searching: the strip is information only)
    if (!(edge || pad || clk) || now - last_open < 1200) return;
    last_open = now;
    xlog("friendsui: %s on the MP menu - pushing to1/friends13", clk ? "click" : edge ? "P" : "menu-next (pad)");
    push_page("to1/friends13");
}
// ------------------------------------------------------------------ the driver
static void feature_friends13(void) {
    g_fr13_up = 0;
    rkb_tick(GetTickCount64());                          // the rank table poll + the scoreboard badges (rankbadge.c), menu or match
    if (!fr13_enabled()) return;
    static uint64_t P_MAIN, P_FM, P_PAUSE;
    if (!P_MAIN) { P_MAIN = page_id("main-menu"); P_FM = page_id("find-match-menu"); P_PAUSE = page_id("pause-menu"); }
    uint64_t now = GetTickCount64(), top = top_page();
    int in_match = match_substate() == 6;
    int panel = top == fr_page_id();
    if (panel) fm_tw_tick();                             // (the typing line's twins swap every frame the page is up)
    fr_net_tick(now, panel, !in_match && ms_on_menu());
    ft_tick(now, panel, !in_match && (top == P_MAIN || top == P_FM), in_match && !panel && !hud_hidden() && !g_veil_on);
    if (!panel) {
        if (M13.ed.on) fm_type_stop();                   // (the key catcher never outlives the page)
        if (F13.up) {
            F13.up = 0;
            xlog("friendsui: page left (top now %s)", page_name(top));
            // Backspace while typing is the engine's menu-back: it popped the page. Undo that: the text is saved and the page pushed again (at most 8 times in 3 s)
            static uint64_t win0; static int cnt;
            int bs_now = (GetAsyncKeyState(VK_BACK) & 0x8000) != 0;
            if (F13.typing && !F13.closing && game_focused() && (bs_now || (F13.bs_ms && now - F13.bs_ms < 400)) && (top == P_MAIN || top == P_FM || top == P_PAUSE)) {
                if (now - win0 > 3000) { win0 = now; cnt = 0; }
                if (cnt++ < 8) {
                    if (bs_now && !F13.hk[VK_BACK]) fr_cut(fr_prev_ch(F13.caret), F13.caret);            // the press the page had not seen yet
                    K13.valid = 1; K13.typing = 1; K13.blen = F13.blen; K13.caret = F13.caret; K13.col = F13.col; K13.typ_ms = F13.typ_ms;
                    memcpy(K13.foc, F13.foc, sizeof K13.foc); memcpy(K13.off, F13.off, sizeof K13.off); memcpy(K13.buf, F13.buf, sizeof K13.buf);
                    F13.typing = 0;
                    push_page_now("to1/friends13");
                    xlog("friendsui: the engine popped the page on Backspace - pushed again (text kept)");
                    return;
                }
            }
            F13.typing = 0;
        }
        if (in_match) return;
        if (top == P_MAIN || top == P_FM) fr_button_tick(now);
        return;
    }
    g_fr13_up = 1;
    fr_page_tick(now, top);
    g_fr_held_p = game_focused() && (GetAsyncKeyState('P') & 0x8000) != 0;
    g_fr_h_nx = F13.h_nx;
}
