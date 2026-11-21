// achieve.c - achievements, the client half (included from t2r-ext.c after feature_clan's helpers). The daemon is the only one that unlocks
// (tools/achievements.py, re/achievements-1117/list.md); the ext only COUNTS what it sees in a match and shows what the daemon says.
//
// Counters of the match (g_ach_cnt, achievement-only labels 64..127 = achievements.py L_*):
//   64..72  Special Execution of ours with a melee weapon group in hand (crowbar, hammer, machete, hatchet, bat, 2x4, pipe, wrench, club)
//   73      Special Execution of ours with bare hands (fists / neck break; not the interrogation, not the shiv)
//   74      we went down to our own molotov            75 bow headshot down from 40 m+          76 melee blows we dodged
//   88      crossbow headshot down from 40 m+            89 our dodge counter's blow landed (dcounter.c)
//   77      pins escaped                              78 pins escaped at 10 health or less      79..84, 87 award labels (Last One Standing ...)
//   85      lockboxes we opened (Interrogation)       86 items crafted ("Craft" award)          90 we were executed
// Match end: op 0xA9 [token][u32 seq][u8 n][n x (u8 label, u16 count)] with every non-zero mission counter (g_mis_cnt 1..63) and the labels above,
// sent ~1.5 s after the 0xE2 match report and re-sent until the daemon answers (it dedupes per match). Reply 0xA9 / 0xAA = the achievement table
// (achievements.wire_text): parsed into g_ach under g_clan_cs. Newly unlocked ones (unlock time above the newest one seen, t2r-ach-seen.txt next to
// the exe) are queued for the unlock toast (achieve_ui.c). t2r-no-achievements.txt next to the exe: nothing is counted or sent. Log prefix "ach:".
#define ACH_LAB_N 128
#define ACH_MAX 96
#define ACH_TOAST_Q 8
enum { ACH_L_SE0 = 64, ACH_L_FISTS = 73, ACH_L_OWN_MOLOTOV = 74, ACH_L_BOW_TELL = 75, ACH_L_DODGE = 76, ACH_L_PIN = 77, ACH_L_PIN_LOW = 78,
       ACH_L_LAST = 79, ACH_L_STREAK_STOP = 80, ACH_L_HURT = 81, ACH_L_RETAL = 82, ACH_L_REVENGE = 83, ACH_L_RAPID = 84, ACH_L_LOCKBOX = 85,
       ACH_L_CRAFT = 86, ACH_L_COMEBACK = 87, ACH_L_XBOW_TELL = 88, ACH_L_COUNTER = 89, ACH_L_EXECUTED = 90 };
typedef struct { char id[20], group[10], title[48], desc[112]; uint32_t t; int prog, goal, hidden; } ach_row_t;
typedef struct { int ok, n, unlocked; ach_row_t r[ACH_MAX]; } ach_t;
static ach_t g_ach;                               // guarded by g_clan_cs
static volatile LONG g_ach_ver;                   // replies parsed
static int g_ach_cnt[ACH_LAB_N];                  // this match's achievement-only counters
static uint64_t g_ach_gx_w;                       // the weapon in hand when our melee execution started
static uint32_t g_ach_hs_vic = 0xFF; static uint64_t g_ach_hs_t60;    // our last headshot down (victim, frame): the bow test in mis_down_book
static struct { uint8_t pl[250]; int len, pend, tries, seq; uint64_t at; LONG ver0; } g_ach_rep;
static struct { char title[48], desc[112], id[20]; } g_ach_toast[ACH_TOAST_Q];
static volatile LONG g_ach_toast_n;               // queued (written by the worker under g_clan_cs, taken by achieve_ui.c)
typedef struct { char id[20], title[48], desc[112]; } ach_new_t;
static ach_new_t g_ach_new[ACH_TOAST_Q];   // unlocked since the match started: the post-match UNLOCKS stage (pmunlock.c)
static volatile LONG g_ach_new_n;                 // (worker under g_clan_cs; emptied by pmu_match_start)
static uint32_t g_ach_seen_t = 0xFFFFFFFFu;       // newest unlock time already shown (0xFFFFFFFF = not read yet)
// Live unlocks (shown the moment they are unlocked, not at the end of the match): during the match
// ach_live_tick compares the table (progress / goal, op 0xAA) plus this match's counters with the goals of ach_live.h (tools/achievements.py
// --ext-header). The moment one is crossed it sends op 0xAB (the counters so far); the daemon books them (achievements.book_live) and answers
// with the table, which queues the card like any unlock (achieve_ui.c shows it on the match HUD). Only when the daemon's table says it takes
// op 0xAB (last line "LIVE 1"); the daemon decides every unlock, the match-end report books the rest (wins, streaks, clan, ranks) as before.
#include "ach_live.h"
static volatile LONG g_ach_live_ok;               // the last table ended with "LIVE 1"
static uint16_t g_ach_live_base[ACH_LAB_N];       // this match's counts the table already holds (the counters of the last answered op 0xAB)
static uint16_t g_ach_live_sent[ACH_LAB_N];       // the counters of the op 0xAB in flight
static struct { uint8_t tries; uint64_t at; } g_ach_live_try[ACH_LIVE_N];

static int ach_off(void) {
    static int v = -1; static uint64_t at; uint64_t n = GetTickCount64();
    if (v < 0 || n - at > 5000) { at = n ? n : 1; v = GetFileAttributesA("t2r-no-achievements.txt") != INVALID_FILE_ATTRIBUTES; }
    return v;
}
static void ach_note(int lab, int n) {
    if (lab <= 0 || lab >= ACH_LAB_N || n <= 0 || ach_off()) return;
    if (match_substate() != 6) return;
    g_ach_cnt[lab] += n;
    static int nl; if (LOGCAP(nl, 200)) xlog("ach: label %d +%d (now %d this match)", lab, n, g_ach_cnt[lab]);
}
static int ach_melee_group(uint64_t w) {          // the Special Execution weapon label of a held melee weapon id, 0 = none
    static const struct { const char *n; int lab; } T[] = {
        {"crowbar", 64}, {"hammer-modern", 65}, {"hammer-scar", 65}, {"hammer", 65}, {"machete", 66}, {"machete-scar", 66},
        {"tomahawk", 67}, {"hatchet-modern", 67}, {"hatchet", 67}, {"baseball-bat", 68}, {"two-by-four", 69}, {"lead-pipe", 70}, {"short-pipe", 70},
        {"pipe-wrench", 71}, {"club-1h-police", 72}, {"club-1h-scar", 72}};
    static uint64_t h[sizeof T / sizeof T[0]];
    if (!h[0]) for (size_t i = 0; i < sizeof T / sizeof T[0]; i++) h[i] = fnv64(T[i].n);
    if (!w || w == ~0ULL) return 0;
    for (size_t i = 0; i < sizeof T / sizeof T[0]; i++) if (h[i] == w) return T[i].lab;
    uint64_t b = base_weapon(w);
    for (size_t i = 0; i < sizeof T / sizeof T[0]; i++) if (h[i] == b) return T[i].lab;
    return 0;
}
static void ach_exec_begin(int role) {            // gx_melee_begin / the gun execution start: role 1 = we execute, 2 = we are executed
    if (role == 1) g_ach_gx_w = xr_held();
    else if (role == 2) ach_note(ACH_L_EXECUTED, 1);
}
static void ach_award_label(const char *lab) {   // one of OUR awards (mis_book)
    if (!lab || !lab[0]) return;
    if (!strcmp(lab, "Special Execution")) {
        if (g_gx.role != 1 || g_gx.shiv || g_gx.upg) return;
        if (g_gx.melee && g_gx.unarm && !g_gx.gshiv) { ach_note(ACH_L_FISTS, 1); return; }
        if (g_gx.melee && !g_gx.unarm) {
            int l = ach_melee_group(g_ach_gx_w);
            if (!l) l = ach_melee_group(xr_held());
            if (l) ach_note(l, 1);
            else { static int nl; if (LOGCAP(nl, 20)) xlog("ach: Special Execution with weapon %llx - no melee group", (unsigned long long)g_ach_gx_w); }
        }
        return;
    }
    static const struct { const char *n; int lab; } A[] = {{"Last One Standing", ACH_L_LAST}, {"Streak Stopped", ACH_L_STREAK_STOP}, {"Kill While Hurt", ACH_L_HURT},
        {"Retaliation", ACH_L_RETAL}, {"Team Revenge", ACH_L_REVENGE}, {"Rapid Kill", ACH_L_RAPID}, {"Craft", ACH_L_CRAFT}, {"Comeback Bonus", ACH_L_COMEBACK}};
    for (size_t i = 0; i < sizeof A / sizeof *A; i++) if (!strcmp(lab, A[i].n)) { ach_note(A[i].lab, 1); return; }
}
static void ach_headshot_down(uint32_t victim) { g_ach_hs_vic = victim; g_ach_hs_t60 = g_t60 ? g_t60 : 1; }
static void ach_long_down(int mis, uint64_t b, uint32_t victim, float d) {   // mis_down_book: a gun / bow down of ours at distance d (b = base weapon)
    static uint64_t xbow;
    if (!xbow) xbow = fnv64("crossbow");
    int lab = mis == 20 ? ACH_L_BOW_TELL : b == xbow ? ACH_L_XBOW_TELL : 0;      // Ellie's bow (mission 20) / the crossbow
    if (lab && d >= 40.0f && victim == g_ach_hs_vic && g_ach_hs_t60 && g_t60 - g_ach_hs_t60 < 120) { g_ach_hs_vic = 0xFF; ach_note(lab, 1); }
}
static void ach_own_down(uint32_t downer, uint32_t me, uint64_t w) {   // kf_down_local: we went down
    if (downer == me && w == 0x2a3164cb4a1c95d9ULL) ach_note(ACH_L_OWN_MOLOTOV, 1);
}
static void ach_dodge(void) {                     // mdg_dodge_ok_cue on our own body: one dodged blow (the cue's own 600 ms dedupe is not ours)
    static uint64_t last; uint64_t n = GetTickCount64();
    if (last && n - last < 400) return;
    last = n;
    ach_note(ACH_L_DODGE, 1);
}
static void ach_pin_escape(void) {
    ach_note(ACH_L_PIN, 1);
    float hp = local_hp();
    if (hp > 0.0f && hp <= 10.0f) ach_note(ACH_L_PIN_LOW, 1);
}
static void ach_match_reset(void) {
    memset(g_ach_cnt, 0, sizeof g_ach_cnt); g_ach_gx_w = 0; g_ach_hs_vic = 0xFF;
    memset(g_ach_live_base, 0, sizeof g_ach_live_base); memset(g_ach_live_sent, 0, sizeof g_ach_live_sent); memset(g_ach_live_try, 0, sizeof g_ach_live_try);
}
static int ach_cnt_now(int id) {                  // this match's count of label id (the ext's mission counters 1..63, the achievement ones 64..127)
    if (id <= 0 || id >= ACH_LAB_N) return 0;
    int v = id >= 64 ? g_ach_cnt[id] : id < MIS_N ? g_mis_cnt[id] : 0;
    return v < 0 ? 0 : v > 65535 ? 65535 : v;
}
static int ach_live_skip(int id) { return id == 21 || id == 22 || id == 23 || id == 24 || id == 33; }   // = achievements.LIVE_SKIP (0xE2 only)
static const ach_row_t *ach_row(const char *id) {   // under g_clan_cs
    for (int i = 0; i < g_ach.n; i++) if (!strcmp(g_ach.r[i].id, id)) return &g_ach.r[i];
    return NULL;
}
#define T2R_ACH_EARNED 1                          // customize.c: ach_earned() exists (its achievement items, customize_ach.h)
static int ach_earned(const char *id) {           // any thread (customize unlocks): 1 unlocked, 0 locked or unknown id, -1 no table yet (count as locked)
    int r = -1;
    EnterCriticalSection(&g_clan_cs);
    if (g_ach.ok) { const ach_row_t *e = ach_row(id); r = e && e->t ? 1 : 0; }
    LeaveCriticalSection(&g_clan_cs);
    return r;
}
static int ach_live_hit(int i) {                  // under g_clan_cs: rule i of ach_live.h is reached by the table + this match (and still locked)
    const ach_row_t *r = ach_row(ACH_LIVE[i].id);
    if (!r || r->t) return 0;
    int lab = ACH_LIVE[i].lab, goal = ACH_LIVE[i].goal;
    if (ACH_LIVE[i].kind == 2) return ach_cnt_now(lab) >= goal;
    if (ACH_LIVE[i].kind == 0) return r->prog + ach_cnt_now(lab) - g_ach_live_base[lab] >= goal;
    int n = 0;                                    // kind 1: JACK OF ALL BLADES - the weapons with a Special Execution, lifetime (their own rows) or now
    for (int j = 0; j < ACH_LIVE_SE_N; j++) {
        int w = ACH_LIVE_SE[j], had = 0;
        for (int k = 0; k < ACH_LIVE_N; k++)
            if (ACH_LIVE[k].kind == 0 && ACH_LIVE[k].lab == w) { const ach_row_t *q = ach_row(ACH_LIVE[k].id); had = q && (q->prog > 0 || q->t); break; }
        if (had || ach_cnt_now(w) > 0) n++;
    }
    return n >= goal;
}
static void ach_live_tick(uint64_t now) {         // every 0.5 s in the match: a crossed goal -> op 0xAB (one at a time, 3 tries per achievement, 5 s apart)
    static uint64_t at;
    static int nl;
    if (!g_ach_live_ok || match_substate() != 6 || now - at < 500) return;
    at = now;
    if (g_clan_busy || g_ach_rep.pend) return;
    int due = -1;
    EnterCriticalSection(&g_clan_cs);
    if (g_ach.ok)
        for (int i = 0; i < ACH_LIVE_N && due < 0; i++)
            if (g_ach_live_try[i].tries < 3 && (!g_ach_live_try[i].at || now - g_ach_live_try[i].at > 5000) && ach_live_hit(i)) due = i;
    LeaveCriticalSection(&g_clan_cs);
    if (due < 0) return;
    uint8_t pl[250]; int n = 0, o = 1;
    uint16_t snap[ACH_LAB_N] = {0};
    for (int id = 1; id < ACH_LAB_N && o + 3 <= (int)sizeof pl; id++) {
        int v = ach_live_skip(id) ? 0 : ach_cnt_now(id);
        if (v <= 0) continue;
        uint16_t c = (uint16_t)v; snap[id] = c;
        pl[o] = (uint8_t)id; memcpy(pl + o + 1, &c, 2); o += 3; n++;
    }
    pl[0] = (uint8_t)n;
    if (!clan_send(0xAB, pl, o)) return;
    g_ach_live_try[due].tries++; g_ach_live_try[due].at = now;
    EnterCriticalSection(&g_clan_cs); memcpy(g_ach_live_sent, snap, sizeof snap); LeaveCriticalSection(&g_clan_cs);
    if (LOGCAP(nl, 60)) xlog("ach: live - %s reached (try %d), op ab with %d counters", ACH_LIVE[due].id, g_ach_live_try[due].tries, n);
}
static void ach_live_ack(void) {                  // the worker parsed the op 0xAB answer: the table now holds what that report carried
    EnterCriticalSection(&g_clan_cs); memcpy(g_ach_live_base, g_ach_live_sent, sizeof g_ach_live_base); LeaveCriticalSection(&g_clan_cs);
}
static void ach_match_over(void) {                // feature_clan: the 0xE2 report was just built (g_mis_cnt is the match's)
    if (ach_off()) return;
    uint8_t *p = g_ach_rep.pl;
    int n = 0, o = 5;
    for (int id = 1; id < ACH_LAB_N && o + 3 <= (int)sizeof g_ach_rep.pl; id++) {
        int v = id < MIS_N ? g_mis_cnt[id] : 0;
        if (id >= 64) v = g_ach_cnt[id];
        if (v <= 0) continue;
        uint16_t c = (uint16_t)(v > 65535 ? 65535 : v);
        p[o] = (uint8_t)id; memcpy(p + o + 1, &c, 2); o += 3; n++;
    }
    g_ach_rep.seq++;
    memcpy(p, &g_ach_rep.seq, 4); p[4] = (uint8_t)n;
    g_ach_rep.len = o; g_ach_rep.pend = 1; g_ach_rep.tries = 0; g_ach_rep.at = GetTickCount64() + 1500; g_ach_rep.ver0 = g_ach_ver;
    xlog("ach: match over, %d counters queued for op a9", n);
}
static int ach_ask(void) { return clan_send(0xAA, NULL, 0); }
static void ach_tick(uint64_t now) {              // feature_clan, every frame
    static uint64_t ask_at;
    static int asked;
    if (ach_off()) return;
    ach_live_tick(now);
    if (g_ach_rep.pend) {
        if (g_ach_ver != g_ach_rep.ver0 && g_ach_rep.tries > 0) { g_ach_rep.pend = 0; xlog("ach: op a9 answered after %d try(s)", g_ach_rep.tries); }
        else if (now >= g_ach_rep.at && !g_clan_busy) {
            if (clan_send(0xA9, g_ach_rep.pl, g_ach_rep.len)) { g_ach_rep.tries++; g_ach_rep.at = now + 8000; }
            else g_ach_rep.at = now + 500;
            if (g_ach_rep.tries >= 12) { g_ach_rep.pend = 0; xlog("ach: op a9 gave up after %d tries", g_ach_rep.tries); }
        }
        return;
    }
    if (!asked && now >= ask_at && !g_clan_busy && match_substate() != 6) {     // the table once per session (baseline for the toast); the page re-asks itself
        if (ach_ask()) asked = 1;
        else ask_at = now + 3000;
    }
}
static uint32_t ach_seen_read(void) {
    FILE *f = exe_side_open("t2r-ach-seen.txt", "r");
    unsigned v = 0;
    if (f) { if (fscanf(f, "%u", &v) != 1) v = 0; fclose(f); return (uint32_t)v; }
    return 0xFFFFFFFEu;                            // no file: the first table is the baseline (nothing toasted for old unlocks)
}
static void ach_seen_write(uint32_t t) { FILE *f = exe_side_open("t2r-ach-seen.txt", "w"); if (f) { fprintf(f, "%u\n", (unsigned)t); fclose(f); } }
static void ach_parse(const char *t) {            // worker thread: achievements.wire_text
    static ach_t a;
    memset(&a, 0, sizeof a);
    if (strncmp(t, "ACH ", 4)) { xlog("ach: reply without a table (%d bytes)", (int)strlen(t)); return; }
    int tot = 0;
    if (sscanf(t + 4, "%d %d", &a.unlocked, &tot) != 2) return;
    const char *s = strchr(t, '\n');
    LONG live = 0;                                    // the daemon's last line "LIVE 1": it takes op 0xAB (live unlocks)
    while (s && *s == '\n' && a.n < ACH_MAX) {
        s++;
        const char *e = strchr(s, '\n');
        if (!e) break;
        char ln[400]; size_t L = (size_t)(e - s) < sizeof ln - 1 ? (size_t)(e - s) : sizeof ln - 1;
        memcpy(ln, s, L); ln[L] = 0;
        char *f[8]; int k = 0; char *c = ln; f[k++] = c;
        while (*c && k < 8) { if (*c == '|') { *c = 0; f[k++] = c + 1; } c++; }
        if (k == 1 && !strcmp(ln, "LIVE 1")) live = 1;
        if (k == 8) {
            ach_row_t *r = &a.r[a.n++];
            snprintf(r->id, sizeof r->id, "%s", f[0]); snprintf(r->group, sizeof r->group, "%s", f[1]);
            r->t = (uint32_t)strtoul(f[2], NULL, 10); r->prog = atoi(f[3]); r->goal = atoi(f[4]); r->hidden = atoi(f[5]);
            snprintf(r->title, sizeof r->title, "%s", f[6]); snprintf(r->desc, sizeof r->desc, "%s", f[7]);
        }
        s = e;
    }
    a.ok = 1;
    if (live != g_ach_live_ok) { InterlockedExchange(&g_ach_live_ok, live); xlog("ach: live unlocks %s (daemon %s op ab)", live ? "on" : "off", live ? "takes" : "has no"); }
    if (g_ach_seen_t == 0xFFFFFFFFu) g_ach_seen_t = ach_seen_read();
    uint32_t newest = 0;
    for (int i = 0; i < a.n; i++) if (a.r[i].t > newest) newest = a.r[i].t;
    EnterCriticalSection(&g_clan_cs);
    memcpy(&g_ach, &a, sizeof a);
    if (g_ach_seen_t == 0xFFFFFFFEu) g_ach_seen_t = newest;                          // first table ever: baseline
    else
        for (int i = 0; i < a.n; i++)
            if (a.r[i].t > g_ach_seen_t && g_ach_toast_n < ACH_TOAST_Q) {
                LONG q = g_ach_toast_n;
                snprintf(g_ach_toast[q].title, sizeof g_ach_toast[q].title, "%s", a.r[i].title);
                snprintf(g_ach_toast[q].desc, sizeof g_ach_toast[q].desc, "%s", a.r[i].desc);
                snprintf(g_ach_toast[q].id, sizeof g_ach_toast[q].id, "%s", a.r[i].id);
                InterlockedIncrement(&g_ach_toast_n);
                if (g_ach_new_n < ACH_TOAST_Q) {
                    LONG m = g_ach_new_n;
                    snprintf(g_ach_new[m].id, sizeof g_ach_new[m].id, "%s", a.r[i].id);
                    snprintf(g_ach_new[m].title, sizeof g_ach_new[m].title, "%s", a.r[i].title);
                    snprintf(g_ach_new[m].desc, sizeof g_ach_new[m].desc, "%s", a.r[i].desc);
                    InterlockedIncrement(&g_ach_new_n);
                }
                xlog("ach: UNLOCKED %s \"%s\" - toast queued", a.r[i].id, a.r[i].title);
            }
    if (newest > g_ach_seen_t || g_ach_seen_t == 0) g_ach_seen_t = newest;
    LeaveCriticalSection(&g_clan_cs);
    ach_seen_write(g_ach_seen_t);
    InterlockedIncrement(&g_ach_ver);
    static int nl; if (LOGCAP(nl, 30)) xlog("ach: table %d / %d unlocked (%d rows)", a.unlocked, tot, a.n);
}
