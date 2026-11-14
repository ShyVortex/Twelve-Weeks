// harness of tools/ext/int_phase_spawn.h (lockbox-phase respawn selection); run by test_int_phase.py. Fake map: boxes at x=0 (target) and x=100 (home), spawns along x.
#include <stdio.h>
#include <string.h>
#include "../ext/int_phase_spawn.h"
static int fails;
#define CHECK(c, ...) do { if (!(c)) { fails++; printf("FAIL line %d: ", __LINE__); printf(__VA_ARGS__); printf("\n"); } } while (0)
int main(void) {
    float target[3] = {0, 0, 0}, home[3] = {100, 0, 0};
    ips_cand c[12]; int n = 0;
    for (int x = 10; x <= 100; x += 10) { c[n].pos[0] = (float)x; c[n].pos[1] = 0; c[n].pos[2] = 0; c[n].ok = 1; n++; }   // R0..R9 at 10..100 m from the target
    const char *how;
    // attacker 1v1 near the target: always the middle (50 m -> index 4), either rnd
    for (unsigned r = 0; r < 2; r++) { int i = ips_pick(1, 1, 1, 0, 1, c, n, target, home, r, &how); CHECK(i == 4, "1v1 attacker middle got %d", i); }
    // attacker 4v4: rnd odd = middle, even = own side (100 m = index 9)
    CHECK(ips_pick(1, 4, 4, 0, 1, c, n, target, home, 1, &how) == 4, "4v4 attacker middle");
    CHECK(ips_pick(1, 4, 4, 0, 1, c, n, target, home, 0, &how) == 9, "4v4 attacker own side");
    // attacker killed away from the box: normal pick
    CHECK(ips_pick(1, 4, 4, 0, 0, c, n, target, home, 0, &how) == -1, "attacker far from the box = normal");
    // defender 4v4: far from the box (index 9)
    CHECK(ips_pick(2, 4, 4, 0, 0, c, n, target, home, 0, &how) == 9, "4v4 defender far");
    // defender 2v2: close = run 5..10 s = 19.2..38.5 m -> 30 m (index 2, 5.9... 7.8 s); middle on odd rnd
    int i = ips_pick(2, 2, 2, 0, 0, c, n, target, home, 0, &how); CHECK(i == 2 && ips_run(c[i].pos, target) >= 5.0f && ips_run(c[i].pos, target) <= 10.0f, "2v2 defender close got %d (%s)", i, how);
    CHECK(ips_pick(2, 2, 2, 0, 0, c, n, target, home, 1, &how) == 4, "2v2 defender middle");
    CHECK(ips_pick(2, 1, 1, 0, 0, c, n, target, home, 0, &how) == 2, "1v1 defender close");
    // never on top of the box: the 10 m spawn (2.6 s) is not chosen as 'close' even when it is the only ok one near; the nearest-window one is
    for (int k = 0; k < n; k++) c[k].ok = k <= 1;      // only 10 and 20 m left (2.6 s, 5.2 s): 20 m wins
    CHECK(ips_pick(2, 2, 2, 0, 0, c, n, target, home, 0, &how) == 1, "close picks the 5.2 s spawn over the 2.6 s one");
    for (int k = 0; k < n; k++) c[k].ok = 1;
    // streak: a defender killed twice in a row gets the far spawn even in 1v1
    CHECK(ips_pick(2, 1, 1, 2, 0, c, n, target, home, 0, &how) == 9, "streak = far");
    CHECK(ips_pick(2, 2, 2, 1, 0, c, n, target, home, 0, &how) == 2, "streak 1 = still close");
    // unsafe spawns (ok = 0) are never chosen; nothing ok = -1
    c[9].ok = 0; CHECK(ips_pick(2, 4, 4, 0, 0, c, n, target, home, 0, &how) == 8, "far skips a blocked spawn");
    for (int k = 0; k < n; k++) c[k].ok = 0;
    CHECK(ips_pick(2, 4, 4, 0, 0, c, n, target, home, 0, &how) == -1, "no ok candidate = -1");
    printf(fails ? "FAILED %d\n" : "OK\n", fails);
    return fails != 0;
}
