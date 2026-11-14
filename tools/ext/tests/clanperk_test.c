// Offline check of clanperk.h (clan supply perks: parse of the daemon's tail, spawn plan, report packing, card text, summary).
// Build: gcc -std=gnu2x -O2 -o clanperk_test clanperk_test.c && ./clanperk_test   (exit 0 = all pass)
#include <stdio.h>
#include "../clanperk.h"
static int fails;
#define CK(c, ...) do { if (!(c)) { printf("FAIL line %d: ", __LINE__); printf(__VA_ARGS__); printf("\n"); fails++; } } while (0)
int main(void) {
    cp_state_t s;
    // the exact tail tools/clan_perks.wire_text sends, behind a normal state text
    const char *t = "v=1 fac=1 st=1 day=9 h=8 hu=0 s=1 lmh=77 ag1=3 ag2=6 ag3=9 pk=3 pkc0=1 pkn0=2 pkg0=1 pkl0=1 pkr0=1 pkc1=2 pkn1=9 pkg1=0 pkl1=3 pkr1=5 pkc2=4 pkn2=1 pkg2=0 pkl2=1 pkr2=2 pkm0=Lila_B pkm1=Wendy pkm2=Arnaldo";
    cp_parse_tail(t, &s);
    CK(s.n == 3, "three perks (%d)", s.n);
    CK(s.p[CP_MEDKIT].cat == 1 && s.p[CP_MEDKIT].cap == 2 && s.p[CP_MEDKIT].female == 1 && !strcmp(s.p[CP_MEDKIT].name, "Lila B"), "medkit: %d %d %s", s.p[0].cat, s.p[0].cap, s.p[0].name);
    CK(s.p[CP_CLIP].cat == 2 && s.p[CP_CLIP].cap == 3, "clip cap clamped to the per-match maximum 3 (daemon sent 9): %d", s.p[1].cap);
    CK(s.p[CP_STAMINA].cat == 4 && s.p[CP_STAMINA].cap == 1 && s.p[CP_STAMINA].look == 1, "stamina in its own slot");
    CK(!s.p[CP_PARTS].cat && !s.p[CP_BLEED].cat, "perks not granted stay empty");
    // an old daemon: no keys at all -> nothing, never garbage
    cp_parse_tail("v=1 fac=1 st=1 day=9 lmh=77 ag1=3", &s);
    CK(s.n == 0 && !s.p[0].cat, "old daemon: no perks");
    cp_parse_tail(NULL, &s); CK(s.n == 0, "NULL text");
    // malformed: count above 5, category 9, cap 0, a name with no number, a huge token
    cp_parse_tail("pk=99 pkc0=9 pkn0=1 pkc1=2 pkn1=0 pkc2=3 pkn2=2 pkm2=X pkx=1 pkc7=1", &s);
    CK(s.n == 1 && s.p[CP_PARTS].cat == 3 && !strcmp(s.p[CP_PARTS].name, "X"), "malformed tokens skipped, valid kept (%d)", s.n);
    char big[400]; memset(big, 'a', sizeof big - 1); big[sizeof big - 1] = 0;
    cp_parse_tail(big, &s); CK(s.n == 0, "a giant token is ignored");
    cp_parse_tail("pk=1 pkc0=1 pkn0=2 pkm0=ABCDEFGHIJKLMNOPQRSTUVWXYZABCDEF", &s);
    CK(s.n == 1 && strlen(s.p[0].name) == 23, "names are cut to 23 chars");
    cp_parse_tail("pk=1 pkc0=1 pkn0=2", &s);
    CK(!strcmp(s.p[0].name, "Your clan"), "no name sent: 'Your clan'");
    // when the help comes: struggling = 2 lives lost in a row, or 1 while 4+ behind / the clan lost 2+ matches, or the first spawn after 3+ lost matches
    CK(cp_struggling(0, 0, 0, 1) == CP_WHY_NONE && cp_struggling(1, 0, 0, 2) == CP_WHY_NONE && cp_struggling(1, 3, 1, 2) == CP_WHY_NONE, "no help while fine");
    CK(cp_struggling(2, 0, 0, 3) == CP_WHY_BAD2 && cp_struggling(5, 0, 0, 9) == CP_WHY_BAD2, "2 lives lost in a row: help");
    CK(cp_struggling(1, 4, 0, 2) == CP_WHY_BEHIND && cp_struggling(1, 0, 2, 2) == CP_WHY_BEHIND && cp_struggling(0, 9, 9, 2) == CP_WHY_NONE, "1 life lost + behind / loss streak: help; none without a lost life");
    CK(cp_struggling(0, 0, 3, 1) == CP_WHY_STREAK && cp_struggling(0, 0, 3, 2) == CP_WHY_NONE && cp_struggling(0, 0, 2, 1) == CP_WHY_NONE, "3 lost matches: the first spawn of the match");
    CK(cp_grant_due(1, 1000, 0) && !cp_grant_due(0, 1000, 0) && !cp_grant_due(1, 50000, 1000) && cp_grant_due(1, 91001, 1000), "one grant per streak, 90 s apart");
    cp_parse_tail("pk=3 pks=4 pkc0=1 pkn0=2 pkc1=2 pkn1=3 pkc2=3 pkn2=2 pkm0=Tyler", &s);
    CK(s.n == 3 && s.streak == 4, "pks = the loss streak");
    cp_parse_tail("pk=1 pks=77 pkc0=1 pkn0=2", &s); CK(s.streak == 9, "streak clamps to 9");
    cp_parse_tail("pk=1 pkc0=1 pkn0=2", &s); CK(s.streak == 0, "no pks: 0");
    {   int used0[CP_N] = {0}, used1[CP_N] = {1, 0, 0, 0, 0};
        cp_parse_tail("pk=3 pkc0=1 pkn0=2 pkc1=2 pkn1=3 pkc2=3 pkn2=2", &s);
        CK(cp_pick_item(&s, used0, 7) == CP_MEDKIT, "medkit first");
        CK(cp_pick_item(&s, used1, 7) == CP_CLIP, "then the one used least (clip)");
        CK(cp_pick_item(&s, used0, 6) == CP_CLIP, "medkit not applicable (carrying 2): clip");
        CK(cp_pick_item(&s, used0, 0) == -1, "nothing applicable");
        int full[CP_N] = {2, 3, 2, 0, 0};
        CK(cp_pick_item(&s, full, 7) == -1, "all caps used");
        cp_parse_tail("pk=1 pkc0=4 pkn0=1", &s);
        CK(cp_pick_item(&s, used0, 7) == -1, "stamina is passive: never a streak grant");
    }
    CK(cp_clip_extra(30, 40, 0) == 30 && cp_clip_extra(0, 0, 0) == 6 && cp_clip_extra(30, 50, 60) == 10 && cp_clip_extra(30, 60, 60) == 0 && cp_clip_extra(30, 70, 60) == 0, "clip: one magazine, capped by the reserve cap");
    // packing
    int u[CP_N] = {2, 3, 1, 1, 2}, l31, l32;
    cp_pack_uses(u, &l31, &l32);
    CK(l31 == (2 | (3 << 4) | (1 << 8)) && l32 == (1 | (2 << 4)), "labels 31/32: %x %x", l31, l32);
    int u2[CP_N] = {99, -4, 0, 0, 0};
    cp_pack_uses(u2, &l31, &l32);
    CK(l31 == 15 && l32 == 0, "uses clamp to a nibble");
    // card text
    char b[120];
    cp_card_text(b, sizeof b, "Tyler", 1, 0, 0); CK(!strcmp(b, "TYLER PROVIDED YOU WITH A MEDKIT"), "%s", b);
    cp_card_text(b, sizeof b, "Dina", 2, 1, 1); CK(!strcmp(b, "DINA PRZYSLALA CI ZAPASOWY MAGAZYNEK"), "%s", b);
    cp_card_text(b, sizeof b, "Tyler", 1, 0, 1); CK(!strcmp(b, "TYLER PRZYSLAL CI APTECZKE"), "%s", b);
    cp_card_text(b, sizeof b, NULL, 5, 0, 0); CK(!strcmp(b, "YOUR CLAN BOUGHT YOU TIME"), "%s", b);
    cp_card_text(b, 12, "Tyler", 1, 0, 0); CK(strlen(b) == 11, "truncates safely");
    // summary
    cp_parse_tail(t, &s);
    cp_summary(b, sizeof b, &s, 0);
    CK(!strcmp(b, "medkit x2 (Lila B), clip x3 (Wendy), sprint recovery x1 (Arnaldo)"), "%s", b);
    cp_summary(b, 20, &s, 0); CK(strlen(b) < 20, "summary fits its buffer");
    // voice gate
    CK(cp_voice_due(5000, 0) && !cp_voice_due(19999, 0 + 1) && cp_voice_due(21001, 1000) && !cp_voice_due(20999, 1000), "one voice line per 20 s");
    printf(fails ? "%d FAILED\n" : "all clanperk checks pass\n", fails);
    return fails != 0;
}
