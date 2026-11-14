// compile + sanity check of the generated move table: gcc -std=gnu2x -O2 -I../ext movestest.c -o movestest && ./movestest
#include <stdio.h>
#include <string.h>
#include "mv3.h"
#include "mv3_moves.h"
static uint64_t fnv(const char *s) { uint64_t h = 0xcbf29ce484222325ULL; while (*s) h = (h ^ (uint8_t)*s++) * 0x100000001b3ULL; return h; }
int main(void) {
    int bad = 0;
    // fnv64 = the ext's fnv64_rt: known pairs from the C source (SID_PLAYER is not a clip; these are)
    if (fnv("player") != 0x4580fab03b7eb9c0ULL) { printf("fnv mismatch (SID_PLAYER)\n"); bad++; }
    if (fnv("get-animation-duration") == 0) bad++;
    for (int i = 0; i < MV3_MOVES_N; i++) {
        const mv3_move *m = &MV3_MOVES[i];
        if (fnv(m->name) != m->sid) { printf("%d %s: sid\n", i, m->name); bad++; }
        if (m->pair && fnv(m->pair) != m->pair_sid) { printf("%d %s: pair sid\n", i, m->name); bad++; }
        if (m->kind <= MV3_K_SWING3 && !(m->hit0_f < m->hit1_f && m->hit1_f <= m->chain0_f && m->chain0_f < m->chain1_f && m->chain1_f <= m->dur_f)) { printf("%d %s: swing window order\n", i, m->name); bad++; }
        if (m->kind == MV3_K_DODGE && !(m->iframe1_f > m->iframe0_f && m->cancel_f <= m->dur_f)) { printf("%d %s: dodge\n", i, m->name); bad++; }
        if (!m->dur_f) { printf("%d %s: no length\n", i, m->name); bad++; }
    }
    for (int ws = 0; ws < MV3_WS_N; ws++) for (int s = 0; s < 3; s++) {
        int a = mv3_move_find(MV3_K_SWING1, ws, 0, s), b = mv3_move_find(MV3_K_SWING1 + s, ws, 0, 0);
        if (a < 0 || a != b || MV3_MOVES[a].wset != ws) { printf("swing lookup ws %d step %d: %d %d\n", ws, s, a, b); bad++; }
    }
    for (int d = 0; d < 4; d++) { if (mv3_move_find(MV3_K_DODGE, MV3_WS_KNIFE, d, 0) < 0) { printf("no dodge dir %d\n", d); bad++; } if (mv3_dodge_find(d, 0, 1, 0) < 0) { printf("no dodge_find %d\n", d); bad++; } }
    for (int d = 0; d < 4; d++) for (int st = 0; st < 3; st++) if (mv3_react_find(d, st, 0) < 0) { printf("no react %d %d\n", d, st); bad++; }
    if (mv3_move_find(MV3_K_COUNTER, MV3_WS_FIST, 3, 0) < 0 || mv3_move_find(MV3_K_SWING1, 9, 0, 0) != -1) bad++;
    int32_t f, r, pf = -1000000; mv3_move_rm_at(MV3_M_FIST_SWING1, 0, &f, &r); if (f || r) bad++;
    for (int k = 1; k <= MV3_MOVES[MV3_M_FIST_SWING1].hit0_f; k++) { mv3_move_rm_at(MV3_M_FIST_SWING1, k, &f, &r); if (f < pf - 30) bad++; pf = f; }
    printf("fist swing 1 root at contact: %d mm fwd, %d mm right\n", (int)f, (int)r);
    printf("%d moves, %d problems\n", MV3_MOVES_N, bad);
    printf("%-36s %5s %5s %5s %5s %5s %5s %6s %6s\n", "FIST", "dur", "hit0", "hit1", "ch0", "ch1", "cncl", "reach", "rootF");
    for (int s = 0; s < 3; s++) { const mv3_move *m = &MV3_MOVES[mv3_move_find(MV3_K_SWING1, MV3_WS_FIST, 0, s)];
        printf("%-36s %5d %5d %5d %5d %5d %5d %6.2f %6.2f\n", m->name, m->dur_f, m->hit0_f, m->hit1_f, m->chain0_f, m->chain1_f, m->cancel_f, m->reach, m->root_fwd); }
    return bad != 0;
}
