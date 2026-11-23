// Offline test of padact.h (anti-AFK pad input on any joypad).
// Build: gcc -std=gnu2x -O2 -o padact_test padact_test.c && ./padact_test
#include <stdio.h>
#include <string.h>
#include <stdint.h>
#include <math.h>
#include "../padact.h"
static int fails;
#define CHECK(c, ...) do { if (!(c)) { fails++; printf("FAIL line %d: ", __LINE__); printf(__VA_ARGS__); printf("\n"); } } while (0)
static const float REST[4] = {0, 0, 0, 0};
int main(void) {
    padact_t t; memset(&t, 0, sizeof t);
    char jpA, jpB, padA, padB, padB2;            // addresses only
    uint64_t ms = 1000;
    // a new source: baseline only, even with buttons held (a held button at match start is no new input)
    CHECK(!padact_note(&t, &jpA, &padA, 0x40, REST, ms), "first call of a source must not count");
    CHECK(!padact_note(&t, &jpA, &padA, 0x40, REST, ms += 16), "same mask must not count");
    CHECK(t.act_ms == 0 && t.act_n == 0, "no activity yet");
    //: a joypad that is NOT the learned one (there is none in pad mode) - its button change counts
    CHECK(!padact_note(&t, &jpB, &padB, 0, REST, ms += 16), "jpB baseline");
    CHECK(padact_note(&t, &jpB, &padB, 0x200, REST, ms += 16), "button press on a second joypad must count");
    CHECK(t.act_ms == ms && t.act_n == 1, "act_ms %llu act_n %u", (unsigned long long)t.act_ms, t.act_n);
    CHECK(padact_note(&t, &jpB, &padB, 0, REST, ms += 16), "release counts too");
    // sticks: past 0.3 counts on any joypad, rest noise and NaN do not
    float lx[4] = {0.31f, 0, 0, 0}, noise[4] = {0.12f, -0.2f, 0.29f, -0.29f}, rs[4] = {0, 0, 0, -0.9f}, nan4[4] = {NAN, NAN, NAN, NAN};
    CHECK(padact_note(&t, &jpA, &padA, 0x40, lx, ms += 16), "left stick past 0.3");
    CHECK(padact_note(&t, &jpB, &padB, 0, rs, ms += 16), "right stick on the second joypad");
    CHECK(!padact_note(&t, &jpA, &padA, 0x40, noise, ms += 16), "stick noise under 0.3");
    CHECK(!padact_note(&t, &jpA, &padA, 0x40, nan4, ms += 16), "NaN sticks");
    // two Pads feeding one joypad on alternate frames (different masks): not activity by themselves
    padact_t u; memset(&u, 0, sizeof u);
    int acts = 0;
    for (int f = 0; f < 600; f++) acts += padact_note(&u, &jpA, (f & 1) ? (void *)&padB2 : (void *)&padA, (f & 1) ? 0x80 : 0x0, REST, 1000 + f * 16);
    CHECK(acts == 0, "alternating pads on one joypad gave %d activity calls", acts);
    // idle: 90 s of unchanged input on every source = no activity
    padact_t v; memset(&v, 0, sizeof v);
    acts = 0;
    for (int f = 0; f < 90 * 60; f++) { acts += padact_note(&v, &jpA, &padA, 0x40, noise, f * 16 + 1); acts += padact_note(&v, &jpB, &padB, 0, REST, f * 16 + 2); }
    CHECK(acts == 0 && v.act_ms == 0, "idle pads gave %d activity calls", acts);
    // table full: the oldest source is reused, recent ones keep their baseline
    padact_t w; memset(&w, 0, sizeof w);
    char many[PADACT_N + 2];
    for (int i = 0; i < PADACT_N + 2; i++) CHECK(!padact_note(&w, &jpA, &many[i], 1, REST, 5), "new source %d is baseline", i);
    CHECK(!padact_note(&w, &jpA, &many[PADACT_N + 1], 1, REST, 6), "newest source kept its baseline");
    CHECK(padact_note(&w, &jpA, &many[PADACT_N + 1], 3, REST, 7), "newest source change counts");
    CHECK(w.act_ms == 7, "act_ms");
    // a timestamp of 0 still marks activity (act_ms 0 means none)
    padact_t z; memset(&z, 0, sizeof z);
    padact_note(&z, &jpA, &padA, 0, REST, 0);
    CHECK(padact_note(&z, &jpA, &padA, 1, REST, 0) && z.act_ms != 0, "act at t=0");
    // Steam Input path: a command's answer per joypad
    padact_ans_t a[2]; memset(a, 0, sizeof a);
    CHECK(!padact_answer(a, &jpA, 1), "first answer is a baseline (a button held at the first read is no new input)");
    CHECK(!padact_answer(a, &jpA, 1), "same answer");
    CHECK(padact_answer(a, &jpA, 0), "release = input");
    CHECK(padact_answer(a, &jpA, 5), "press (any non-zero answer) = input");
    // two joypads read alternately with different steady answers: no input
    CHECK(!padact_answer(a, &jpB, 0), "jpB baseline");
    acts = 0;
    for (int f = 0; f < 1000; f++) { acts += padact_answer(a, &jpA, 1); acts += padact_answer(a, &jpB, 0); }
    CHECK(acts == 0, "alternating joypads with steady answers gave %d", acts);
    // a third joypad is not tracked (never a flip)
    char jpC;
    acts = 0;
    for (int f = 0; f < 10; f++) acts += padact_answer(a, &jpC, f & 1);
    CHECK(acts == 0, "third joypad gave %d", acts);
    CHECK(!padact_answer(a, NULL, 1), "NULL joypad");
    // idle 90 s on the command path: no input
    padact_ans_t b[2]; memset(b, 0, sizeof b);
    acts = 0;
    for (int f = 0; f < 90 * 60; f++) acts += padact_answer(b, &jpA, 0);
    CHECK(acts == 0, "idle command answers gave %d", acts);
    printf("%s (%d failures)\n", fails ? "FAILED" : "padact_test: all passed", fails);
    return fails != 0;
}
