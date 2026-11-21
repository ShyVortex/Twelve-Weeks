// Offline harness for tools/ext/p1side.h.   gcc -std=gnu2x -O1 -o p1side_harness.exe p1side_harness.c      (MSYS2 UCRT64)
//   p1side_harness.exe <side dir> <manifest crc hex> <expect ok 0|1> [rel path to find]
// Runs p1s_check on the tree, prints "CHECK <0|1> <why>"; when ok and a rel path is given, looks it up and prints "FIND <size> read <n> <first 8 bytes hex>"
// (and "TAIL" = the last 4 bytes, "PASTEND" = a read past the end), "NOFIND" for a path that is not in the manifest.
#include <windows.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdint.h>
#define P1S_LOG(...) (printf(__VA_ARGS__), printf("\n"))
#define P1S_HARNESS                     // (ext-only read hooks stay out: p1side.h)
#include "../ext/p1side.h"

int main(int argc, char **argv) {
    if (argc < 4) return 2;
    char why[160] = "";
    int ok = p1s_check(argv[1], (uint32_t)strtoul(argv[2], NULL, 16), 0, why, sizeof why);
    printf("CHECK %d %s\n", ok, why);
    if (ok != atoi(argv[3])) return 1;
    // malformed manifests must be refused, never crash
    const char *z64 = "0000000000000000000000000000000000000000000000000000000000000000";
    char bad[8][400];
    snprintf(bad[0], sizeof bad[0], "%s", "");
    snprintf(bad[1], sizeof bad[1], "p1side 1 1 5\n");
    snprintf(bad[2], sizeof bad[2], "p1side 1 1 5\n../x\t5\t%s\n", z64);
    snprintf(bad[3], sizeof bad[3], "p1side 1 2 5\na\t5\t%s\n", z64);
    snprintf(bad[4], sizeof bad[4], "p1side 1 1 5\na\\b\t5\t%s\n", z64);
    snprintf(bad[5], sizeof bad[5], "p1side 1 1 5\nC:/a\t5\t%s\n", z64);
    snprintf(bad[6], sizeof bad[6], "p1side 1 2 10\na\t5\t%s\na\t5\t%s\n", z64, z64);
    snprintf(bad[7], sizeof bad[7], "p1side 1 1 5\na\t5x\t%s\n", z64);
    for (int i = 0; i < 8; i++) {
        p1s_entry *e = NULL;
        int n = p1s_parse(bad[i], strlen(bad[i]), "C:\\x", 0, &e, NULL);
        if (n >= 0) { printf("BADACCEPT %d\n", i); return 3; }
    }
    printf("BADREFUSED 8\n");
    if (ok && argc > 4) {
        g_p1s_ok = 1;                         // (p1s_ok() would run p1s_scan against the harness exe's own folder)
        const p1s_entry *e = p1s_find(argv[4]);
        if (!e) { printf("NOFIND\n"); return 0; }
        uint8_t b[8] = {0};
        int64_t g = p1s_read(e, 0, b, 8);
        printf("FIND %llu read %lld", (unsigned long long)e->size, (long long)g);
        for (int i = 0; i < g; i++) printf(" %02x", b[i]);
        uint8_t t[4] = {0};
        g = p1s_read(e, e->size >= 4 ? e->size - 4 : 0, t, 4);
        printf("\nTAIL %lld", (long long)g);
        for (int i = 0; i < g; i++) printf(" %02x", t[i]);
        printf("\nPASTEND %lld\n", (long long)p1s_read(e, e->size + 10, t, 4));
        if (!p1s_find("pak68/not-there.pak")) printf("NOFIND-OK\n");
    }
    return 0;
}
