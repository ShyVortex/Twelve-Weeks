// Offline test of peerresync.h (the "new peer seen" resync scheduler, re/jip-state-resync-1019.md).
// Build: gcc -std=gnu2x -O2 -o peerresync_test peerresync_test.c && ./peerresync_test
#include <stdio.h>
#include <string.h>
#include <stdint.h>
#include "../peerresync.h"
static int fails;
#define CHECK(c, ...) do { if (!(c)) { fails++; printf("FAIL line %d: ", __LINE__); printf(__VA_ARGS__); printf("\n"); } } while (0)
// drive the scheduler like the tick does: est[] = the slots' state this frame; returns the slots handed out this frame
static int frame(rs_t *r, const int *est, uint64_t now, uint32_t own, uint32_t *out) {
    for (uint32_t s = 0; s < RS_N; s++) rs_seen(r, s, est[s], now, own);
    return rs_next(r, now, out);
}
int main(void) {
    rs_t r; rs_reset(&r);
    int est[RS_N] = {0};
    uint32_t sl;
    // 1. nobody there: nothing ever handed out
    for (uint64_t t = 0; t < 10000; t += 16) CHECK(!frame(&r, est, t, 1, &sl), "nothing to resync with an empty roster");
    // 2. a JIP joiner (slot 5) turns up at t=20000: first resync after 700 ms, second 2800 ms later, then never again
    est[1] = 1; est[0] = 1;                       // established teammates seen at once (we are slot 1, own slot is skipped)
    est[5] = 1;
    int n5 = 0; uint64_t t5[4] = {0}, tmax = 0;
    for (uint64_t t = 20000; t < 40000; t += 16) {
        while (frame(&r, est, t, 1, &sl)) { if (sl == 5 && n5 < 4) t5[n5++] = t; if (sl == 1) CHECK(0, "own slot handed out"); }
        tmax = t;
    }
    CHECK(n5 == 2, "slot 5 gets exactly 2 resyncs, got %d", n5);
    CHECK(t5[0] >= 20700 && t5[0] < 20700 + 40 + 2 * RS_GAP_MS, "first resync ~700 ms after the join: %llu", (unsigned long long)t5[0]);
    CHECK(t5[1] >= 20000 + 3500 && t5[1] < 20000 + 3500 + 40 + 2 * RS_GAP_MS, "second resync ~3500 ms after the join: %llu", (unsigned long long)t5[1]);
    (void)tmax;
    // 3. one slot per call: three slots due in the same frame are handed out over three calls
    rs_reset(&r); memset(est, 0, sizeof est); est[2] = est[3] = est[4] = 1;
    uint64_t t = 1000; for (uint32_t s = 0; s < RS_N; s++) rs_seen(&r, s, est[s], t, 7);
    t += 800; int got = 0, calls = 0; uint32_t seen_mask = 0;
    while (rs_next(&r, t, &sl) && calls++ < 10) { got++; seen_mask |= 1u << sl; }
    CHECK(got == 1, "three due slots, one per call and RS_GAP_MS apart: the same instant hands out one, got %d", got);
    uint64_t prev = t; int spaced = 1;
    for (uint64_t tt = t + 1; tt < t + 600; tt++) if (rs_next(&r, tt, &sl)) { got++; seen_mask |= 1u << sl; if (tt - prev < RS_GAP_MS) spaced = 0; prev = tt; }
    CHECK(got == 3 && seen_mask == 0x1c, "all three due slots are served over time: got %d mask %x", got, seen_mask);
    CHECK(spaced, "handed-out slots are at least RS_GAP_MS apart");
    CHECK(prev - t <= 2 * RS_GAP_MS + 2, "three slots take <= 2 gaps: %llu ms", (unsigned long long)(prev - t));
    // 4. a peer that leaves loses its pending resyncs; coming back re-arms it
    rs_reset(&r); memset(est, 0, sizeof est); est[2] = 1;
    rs_seen(&r, 2, 1, 5000, 7);
    est[2] = 0; rs_seen(&r, 2, 0, 5100, 7);
    CHECK(!rs_next(&r, 9000, &sl), "a slot that left is not served");
    est[2] = 1; rs_seen(&r, 2, 1, 9100, 7);
    CHECK(!rs_next(&r, 9500, &sl) && rs_next(&r, 9800, &sl) && sl == 2, "a returning slot is served 700 ms after it came back");
    // 5. flapping: a link that goes away and comes back every 100 ms keeps pushing the schedule back, never produces a burst
    rs_reset(&r); memset(est, 0, sizeof est);
    int handed = 0;
    for (t = 0; t < 5000; t += 100) { est[3] = (t / 100) % 2 == 0; rs_seen(&r, 3, est[3], t, 7); while (rs_next(&r, t, &sl)) handed++; }
    CHECK(handed == 0, "a slot that flaps every 100 ms is never due (handed %d)", handed);
    // 6. host migration done: rs_all re-arms every slot that is established right now, not the empty ones
    rs_reset(&r); memset(est, 0, sizeof est); est[0] = est[2] = 1;
    for (uint32_t s = 0; s < RS_N; s++) rs_seen(&r, s, est[s], 100, 7);
    for (t = 100; t < 6000; t += 16) while (rs_next(&r, t, &sl)) ;      // the join schedule runs out
    CHECK(!rs_next(&r, 6000, &sl), "join schedule is over");
    rs_all(&r, 7000);
    got = 0; seen_mask = 0;
    for (t = 7000; t < 12000; t += 16) while (rs_next(&r, t, &sl)) { got++; seen_mask |= 1u << sl; }
    CHECK(got == 4 && seen_mask == 0x5, "after a migration every present slot gets 2 resyncs (%d, mask %x)", got, seen_mask);
    // 7. own slot is never established for us; out-of-range slots are ignored
    rs_reset(&r); CHECK(!rs_seen(&r, 3, 1, 10, 3), "own slot ignored"); CHECK(!rs_seen(&r, 9, 1, 10, 3), "slot >= RS_N ignored");
    printf(fails ? "peerresync_test: %d FAILED\n" : "peerresync_test: all passed\n", fails);
    return fails != 0;
}
