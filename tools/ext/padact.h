// padact.h - "did the player touch a pad?" for the anti-AFK (afk.c). Pure C: tests/padact_test.c compiles this file.
//
// (live 195, Bubba on a pad): removed for inactivity twice while playing. The pad check counted a Pad only when
// Joypad::Update ran for g_padi.jp, the joypad the command-reader hook learned. In pad mode the engine's command entry (exe 0x158f370)
// takes another path (0x14c0800 -> 0x1591190) and never calls the hooked reader (0x158eb70), so nothing was learned, g_padi.jp stayed
// NULL and every stick / button was invisible to the AFK count (0 'padinj: learned' lines in the whole 195 log; the keyboard players on
// the same build learn 10-34 commands).
// Now every Joypad::Update call is looked at, whatever joypad it is for. A (joypad, Pad) pair is one source; its first call only sets the
// baseline (no activity), then a changed button mask or a stick past PADACT_STICK counts as input. Keying on the pair (not the joypad
// alone) keeps two Pads that feed one joypad on alternate frames from looking like a changed mask on every frame.
#ifndef PADACT_H
#define PADACT_H
#include <stdint.h>
#include <math.h>
#define PADACT_N 8             // sources tracked (a full table reuses the oldest slot)
#define PADACT_STICK 0.3f      // a stick past this counts as input (rest noise of a worn stick stays well below)
typedef struct {
    struct { const void *jp, *pad; uint64_t bm, seen; } s[PADACT_N];
    uint64_t seq;              // call counter (oldest-slot reuse)
    uint64_t act_ms;           // last activity, 0 = none yet
    int act_src;               // the slot of the last activity
    unsigned act_n;            // activity calls (a source that never rests shows here)
} padact_t;
// one Joypad::Update call: `bm` = Pad+0x528, `st` = the 4 stick floats (left x, y, right x, y). 1 = input on this call.
static inline int padact_note(padact_t *t, const void *jp, const void *pad, uint64_t bm, const float st[4], uint64_t now_ms) {
    int k = -1, old = 0;
    t->seq++;
    for (int i = 0; i < PADACT_N; i++) {
        if (t->s[i].jp == jp && t->s[i].pad == pad && t->s[i].seen) { k = i; break; }
        if (t->s[i].seen < t->s[old].seen) old = i;
    }
    int act = 0;
    if (k < 0) { k = old; t->s[k].jp = jp; t->s[k].pad = pad; t->s[k].bm = bm; }   // a new source: baseline only
    else if (bm != t->s[k].bm) { act = 1; t->s[k].bm = bm; }
    t->s[k].seen = t->seq;
    for (int i = 0; i < 4; i++) if (fabsf(st[i]) > PADACT_STICK) act = 1;          // (NaN compares false: no input)
    if (act) { t->act_ms = now_ms ? now_ms : 1; t->act_src = k; t->act_n++; }
    return act;
}
// Steam Input command path (padinject.c padinj_si_hook): one watched command's answer on one joypad. Two joypads are kept per command (the engine
// alternates two on the reader); the first answer on a joypad is its baseline. 1 = the answer changed (a button pressed or released).
typedef struct { const void *jp; int last; } padact_ans_t;
static inline int padact_answer(padact_ans_t s[2], const void *jp, int answer) {
    int k = s[0].jp == jp ? 0 : s[1].jp == jp ? 1 : !s[0].jp ? 0 : !s[1].jp ? 1 : -1;
    if (k < 0 || !jp) return 0;                         // a third joypad: not tracked (no flips from alternating sources)
    int a = answer ? 1 : 0;
    if (s[k].jp != jp) { s[k].jp = jp; s[k].last = a; return 0; }
    if (s[k].last == a) return 0;
    s[k].last = a; return 1;
}
#endif
